"""
Reference engine: the *real* live loop, run against a simulated MT5 terminal.

Nothing of the strategy is re-implemented here. ``run_reference`` imports this
branch's own ``app.py`` (and through it ``strategy.py``, ``indicator.py``,
``mt5_helper.py``, ``constants.py``), swaps the ``MetaTrader5`` module for ``SimMT5``
-- a small in-memory terminal that serves bars, ticks, positions and fills from real
Exness ticks -- swaps the clock for a simulated one, and then calls the untouched
``MT5TradingBot.process_symbol``.

Every decision it makes is therefore, by construction, the decision the live bot would
make on that tick stream. It is slow (the live code recomputes every indicator over
500 bars in Python on every iteration), so it is used as ground truth: the test-suite
replays windows of ticks through both engines and requires identical signals, fills
and balance.

What is simulated (and so is a modelling choice, shared with the fast engine):
  * bars are built from Bid ticks on UTC boundaries, forming bar included;
  * a market order fills at the current ask (buy) / bid (sell); a close fills at the
    opposite side; position profit is (price diff x lots x contract), rounded to cents;
  * the loop's own sleeps are the only thing that advances time (1 s per iteration,
    +0.1 s inside buy()/sell(), +ORDER_COOLDOWN_SECONDS after a ladder add).

Demo branches. A demo branch implements the levers of the backtest designs behind a set of
constants (``CONTRACT_NAMES``, a block at the end of its ``constants.py``) and isolates itself on a
shared account with a magic number, an order comment and a virtual balance. When the live root
defines those constants, ``_apply_config`` drives them from the ``BacktestConfig`` (see
``design_constants``) instead of refusing the design, and the simulated terminal serves what such a
branch reads: magic numbers and comments on orders, positions and deals, the deal history, the
contract size and volume limits of the symbol, closed bars (``copy_rates_from_pos`` from any
position) and a fuller account record. ``engine/demo_parity.py`` puts it together.
"""

from __future__ import annotations

import copy
import fnmatch
import math
import numbers
import sys
import tempfile
import time as _real_time
import types
from collections import namedtuple
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import kernels as K
from ..config import FIBO, BacktestConfig, REPO_ROOT, TF_SECONDS
from ..data import store

RATES_DTYPE = np.dtype([("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"),
                        ("close", "<f8"), ("tick_volume", "<u8"), ("spread", "<i4"),
                        ("real_volume", "<u8")])

# MetaTrader5 package constants (values as published by the real module)
_MT5_TF = {"M1": 1, "M2": 2, "M3": 3, "M5": 5, "M10": 10, "M15": 15, "M30": 30,
           "H1": 16385, "H2": 16386, "H4": 16388, "H6": 16390, "H8": 16392, "H12": 16396,
           "D1": 16408}
_TF_BY_CODE = {v: k for k, v in _MT5_TF.items()}

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# The records the MetaTrader5 package returns are named tuples with these fields (in this order).
Tick = namedtuple("Tick", "time bid ask last volume time_msc flags volume_real")
TradePosition = namedtuple("TradePosition", "ticket time time_msc time_update time_update_msc type magic identifier "
                                            "reason volume price_open sl tp price_current swap profit symbol comment "
                                            "external_id")
TradeDeal = namedtuple("TradeDeal", "ticket order time time_msc type entry magic position_id reason volume price "
                                    "commission swap profit fee symbol comment external_id")
TradeRequest = namedtuple("TradeRequest", "action magic order symbol volume price stoplimit sl tp deviation type "
                                          "type_filling type_time expiration comment position position_by")
OrderSendResult = namedtuple("OrderSendResult", "retcode deal order volume price bid ask comment request_id "
                                                "retcode_external request")
OrderCheckResult = namedtuple("OrderCheckResult", "retcode balance equity profit margin margin_free margin_level "
                                                  "comment request")
AccountInfo = namedtuple("AccountInfo", "login trade_mode leverage limit_orders margin_so_mode trade_allowed "
                                        "trade_expert margin_mode currency_digits fifo_close balance credit profit "
                                        "equity margin margin_free margin_level margin_so_call margin_so_so "
                                        "margin_initial margin_maintenance assets liabilities commission_blocked "
                                        "name server currency company")
SymbolInfo = namedtuple("SymbolInfo", "name path description visible select trade_mode digits point spread "
                                      "trade_contract_size trade_tick_size trade_tick_value trade_tick_value_profit "
                                      "trade_tick_value_loss volume_min volume_max volume_step volume_limit "
                                      "trade_stops_level trade_freeze_level filling_mode order_mode expiration_mode "
                                      "currency_base currency_profit currency_margin swap_long swap_short bid ask "
                                      "time")
TerminalInfo = namedtuple("TerminalInfo", "community_account community_connection connected dlls_allowed "
                                          "trade_allowed tradeapi_disabled email_enabled ftp_enabled "
                                          "notifications_enabled mqid build maxbars codepage ping_last "
                                          "community_balance retransmission company name language path data_path "
                                          "commondata_path")

# The MetaTrader5 package refuses a request whose comment is longer than this (order_send returns None).
MAX_COMMENT_LEN = 31


class _End(BaseException):
    """Raised by the simulated clock to leave the live loop (not an Exception on purpose:
    process_symbol swallows every Exception and keeps looping)."""


class _Restart(BaseException):
    """Raised by the simulated clock at a scheduled restart: the bot process 'dies' and is started again."""


def _round2(x: float) -> float:
    return math.floor(x * 100.0 + 0.5) / 100.0 if x >= 0 else -math.floor(-x * 100.0 + 0.5) / 100.0


class SimClock:
    """
    Stands in for the ``time`` module inside the live modules. Simulated time advances only
    through ``sleep``; every reading of the clock (``time``, ``perf_counter``, ``monotonic``,
    the ``*_ns`` forms, and ``gmtime`` / ``localtime`` / ``strftime`` / ``ctime`` without an
    explicit time) reads it. Anything else of the ``time`` module that a live module asks for
    and that does not read the wall clock is passed through; the rest raises AttributeError,
    which the live loop prints as an error (so a reading of the real clock cannot go unnoticed).
    """

    _PASS_THROUGH = ("struct_time", "timezone", "altzone", "daylight", "tzname", "mktime", "strptime",
                     "process_time", "process_time_ns", "thread_time", "thread_time_ns", "get_clock_info")

    def __init__(self, start_ms: int, end_ms: int, restarts_ms: Optional[List[int]] = None):
        self.now_ms = int(start_ms)
        self.end_ms = int(end_ms)
        self.restarts_ms = sorted(int(x) for x in (restarts_ms or []))

    def time(self) -> float:
        return self.now_ms / 1000.0

    def perf_counter(self) -> float:
        return self.now_ms / 1000.0

    def monotonic(self) -> float:
        return self.now_ms / 1000.0

    def time_ns(self) -> int:
        return self.now_ms * 1_000_000

    def perf_counter_ns(self) -> int:
        return self.now_ms * 1_000_000

    def monotonic_ns(self) -> int:
        return self.now_ms * 1_000_000

    def gmtime(self, secs=None):
        return _real_time.gmtime(self.time() if secs is None else secs)

    def localtime(self, secs=None):
        return _real_time.localtime(self.time() if secs is None else secs)

    def strftime(self, fmt, t=None):
        return _real_time.strftime(fmt, self.localtime() if t is None else t)

    def ctime(self, secs=None):
        return _real_time.ctime(self.time() if secs is None else secs)

    def asctime(self, t=None):
        return _real_time.asctime(self.localtime() if t is None else t)

    def __getattr__(self, name):
        if name in SimClock._PASS_THROUGH:
            return getattr(_real_time, name)
        raise AttributeError(f"the simulated clock has no time.{name} (it would read the real clock)")

    def sleep(self, seconds: float) -> None:
        self.now_ms += int(round(float(seconds) * 1000.0))
        if self.now_ms >= self.end_ms:
            raise _End()
        if self.restarts_ms and self.now_ms >= self.restarts_ms[0]:
            self.restarts_ms.pop(0)
            raise _Restart()


class _InstanceCheck(type):
    """Metaclass of the simulated datetime / date: ``isinstance`` and ``issubclass`` answer as for the real class."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls.__real__)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls.__real__)


def _sim_datetime_classes(clock: SimClock):
    """A ``datetime`` and a ``date`` class whose ``now`` / ``utcnow`` / ``today`` read the simulated clock."""

    class _SimDatetime(datetime, metaclass=_InstanceCheck):
        __real__ = datetime

        @classmethod
        def now(cls, tz=None):
            # (aware UTC also when no zone is given: what the live helper has always been served here)
            return datetime.fromtimestamp(clock.now_ms / 1000.0, tz=tz or timezone.utc)

        @classmethod
        def utcnow(cls):
            return datetime.fromtimestamp(clock.now_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)

        @classmethod
        def today(cls):
            return datetime.fromtimestamp(clock.now_ms / 1000.0)

    class _SimDate(date, metaclass=_InstanceCheck):
        __real__ = date

        @classmethod
        def today(cls):
            return datetime.fromtimestamp(clock.now_ms / 1000.0).date()

    return _SimDatetime, _SimDate


def _patch_clocks(mod, clock: SimClock, sim_dt, sim_date) -> None:
    """Point every reference a live module holds to the real clock (``time``, ``datetime``, ``date``,
    ``from time import time, sleep, ...``, ``import datetime``) at the simulated one."""
    import datetime as _datetime_module

    timers = ((_real_time.time, clock.time), (_real_time.sleep, clock.sleep),
              (_real_time.perf_counter, clock.perf_counter), (_real_time.monotonic, clock.monotonic),
              (_real_time.time_ns, clock.time_ns))
    shim = None
    for name, val in list(vars(mod).items()):
        if name.startswith("__"):
            continue
        if val is _real_time:
            setattr(mod, name, clock)
        elif val is datetime:
            setattr(mod, name, sim_dt)
        elif val is date:
            setattr(mod, name, sim_date)
        elif val is _datetime_module:
            if shim is None:
                shim = types.ModuleType("datetime")
                shim.__dict__.update({k: v for k, v in vars(_datetime_module).items() if not k.startswith("__")})
                shim.datetime, shim.date = sim_dt, sim_date
            setattr(mod, name, shim)
        else:
            for real_fn, sim_fn in timers:
                if val is real_fn:
                    setattr(mod, name, sim_fn)
                    break


def _epoch_s(x) -> int:
    """A time argument of the MetaTrader5 package (a datetime or seconds since 1970) as whole seconds.
    A naive datetime is read as local time, as the real package reads it."""
    if hasattr(x, "timestamp"):
        return int(math.floor(x.timestamp()))
    return int(x)


def _group_match(symbol: str, group: Optional[str]) -> bool:
    """MT5 group filter: comma-separated patterns with * and ?, a leading ! excludes."""
    if not group:
        return True
    pats = [p.strip() for p in str(group).split(",") if p.strip()]
    inc = [p for p in pats if not p.startswith("!")]
    exc = [p[1:] for p in pats if p.startswith("!")]
    if any(fnmatch.fnmatchcase(symbol, p) for p in exc):
        return False
    return not inc or any(fnmatch.fnmatchcase(symbol, p) for p in inc)


class _Bars:
    """Growing OHLC bar arrays for one timeframe, built tick by tick from Bid."""

    def __init__(self, tf_s: int, cap: int):
        self.tf_s = tf_s
        self.t = np.zeros(cap, np.int64)
        self.o = np.zeros(cap)
        self.h = np.zeros(cap)
        self.l = np.zeros(cap)
        self.c = np.zeros(cap)
        self.v = np.zeros(cap, np.uint64)
        self.n = 0
        self.cur = -1

    def seed(self, bars: Dict[str, np.ndarray]) -> None:
        k = len(bars["t"])
        self.t[:k], self.o[:k], self.h[:k], self.l[:k], self.c[:k] = \
            bars["t"], bars["o"], bars["h"], bars["l"], bars["c"]
        self.v[:k] = bars["n"].astype(np.uint64)
        self.n = k
        self.cur = int(bars["t"][-1] // self.tf_s) if k else -1

    def on_tick(self, t_s: int, price: float) -> None:
        b = t_s // self.tf_s
        if b != self.cur:
            i = self.n
            self.t[i] = b * self.tf_s
            self.o[i] = self.h[i] = self.l[i] = self.c[i] = price
            self.v[i] = 1
            self.n += 1
            self.cur = b
        else:
            i = self.n - 1
            if price > self.h[i]:
                self.h[i] = price
            if price < self.l[i]:
                self.l[i] = price
            self.c[i] = price
            self.v[i] += 1

    def last(self, count: int, upto_t: Optional[int] = None, skip: int = 0) -> np.ndarray:
        """The last ``count`` bars (oldest first), leaving out the newest ``skip`` (0 = the forming bar is included)."""
        n = self.n
        if upto_t is not None:
            n = int(np.searchsorted(self.t[:self.n], upto_t, side="right"))
        n = max(0, n - int(skip))
        lo = max(0, n - int(count))
        out = np.zeros(n - lo, RATES_DTYPE)
        out["time"], out["open"], out["high"] = self.t[lo:n], self.o[lo:n], self.h[lo:n]
        out["low"], out["close"], out["tick_volume"] = self.l[lo:n], self.c[lo:n], self.v[lo:n]
        return out

    def between(self, t_from: int, t_to: int) -> np.ndarray:
        """Bars whose open time is in [t_from, t_to] (seconds)."""
        lo = int(np.searchsorted(self.t[:self.n], t_from, side="left"))
        hi = int(np.searchsorted(self.t[:self.n], t_to, side="right"))
        return self.last(max(hi - lo, 0), upto_t=None, skip=self.n - hi)


class SimMT5:
    """The slice of the ``MetaTrader5`` module that app.py and mt5_helper.py use."""

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_SLTP = 6
    TRADE_ACTION_MODIFY = 7
    TRADE_ACTION_REMOVE = 8
    TRADE_ACTION_CLOSE_BY = 10
    ORDER_TIME_GTC = 0
    ORDER_TIME_DAY = 1
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_INVALID = 10013
    TRADE_RETCODE_INVALID_VOLUME = 10014
    TRADE_RETCODE_MARKET_CLOSED = 10018
    TRADE_RETCODE_NO_MONEY = 10019
    TRADE_RETCODE_PRICE_OFF = 10021
    TRADE_RETCODE_INVALID_CLOSE_VOLUME = 10038
    TRADE_RETCODE_CLOSE_ONLY = 10044
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    DEAL_TYPE_BALANCE = 2
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_OUT_BY = 3
    DEAL_REASON_CLIENT = 0
    DEAL_REASON_EXPERT = 3
    POSITION_REASON_CLIENT = 0
    POSITION_REASON_EXPERT = 3
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ACCOUNT_MARGIN_MODE_EXCHANGE = 1
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2
    COPY_TICKS_ALL = -1
    SYMBOL_TRADE_MODE_DISABLED = 0
    SYMBOL_TRADE_MODE_FULL = 4

    def __init__(self, symbol: str, t_ms: np.ndarray, bid: np.ndarray, ask: np.ndarray,
                 clock: SimClock, warm_m1: Dict[str, np.ndarray], contract_size: float,
                 leverage: float, balance: float, warm_bars: int = 600,
                 close_only_break_ms: int = 0, close_only_weekend_ms: int = 0, after_ms: Optional[int] = None,
                 digits: int = 2, volume_min: float = 0.01, volume_step: float = 0.01, volume_max: float = 200.0,
                 own_balance: Optional[float] = None, history: Optional[Sequence[dict]] = None,
                 margin_mode: int = 2):
        """
        Broker-side rules, the same ones the fast engine applies, so that the live code is
        exercised against them and the two engines can be compared with them switched on:

        * an order sent more than a second after the last quote before a session break is
          answered "market closed" (the bot's own liveness rule lets it try for three minutes);
        * for ``close_only_break_ms`` after a session break ends (``close_only_weekend_ms``
          after a break of a day or more) closes are accepted and new orders refused;
        * a new order the free margin cannot carry is refused.

        Account and history. ``balance`` is the account's balance at the start; ``own_balance`` the
        part of it that belongs to the bot under test (default: all of it), which moves only with
        the bot's own fills (``final_balance`` of a replay). ``history`` holds deals made before the
        replay (deposits, other bots' trades; dicts with the keys of ``add_history_deal``): they are
        served by ``history_deals_get`` and do not move the balance again.

        Not modelled: pending orders, broker-side SL / TP execution (the levels are stored and
        served, never triggered), swaps, commissions. A request of that kind is answered "invalid"
        and recorded in ``unsupported`` (the replay reports it as an error).
        """
        self.symbol = symbol
        self.t_ms, self.bid, self.ask = t_ms, bid, ask
        self.clock = clock
        self.contract = float(contract_size)
        self.leverage = float(leverage)
        self.balance = float(balance)
        self.own_balance = float(balance if own_balance is None else own_balance)
        self.digits = int(digits)
        self.point = 10.0 ** -self.digits
        self.volume_min, self.volume_step, self.volume_max = float(volume_min), float(volume_step), float(volume_max)
        self.margin_mode = int(margin_mode)
        self.ptr = -1
        self.positions: List[dict] = []
        self.deals: List[dict] = []          # the fills of the bot under test (what parity compares)
        self.history: List[dict] = []        # every deal of the account, as history_deals_get serves them
        self._ticket = 1000                  # orders and positions (a position's ticket is its opening order's)
        self._deal_ticket = 2_000_000
        self._scheduled: List[dict] = []     # deals of others still to happen (schedule_deal)
        self._last_error = (1, "Success")
        self.rejects = 0
        self.refused = {"market_closed": 0, "close_only": 0, "no_money": 0, "invalid_volume": 0}
        self.invalid_requests = 0            # order_send answered None (a field the real package refuses)
        self.unsupported: List[str] = []     # requests this terminal cannot model
        # time of the first quote after the replayed rows: rows that stop half an hour or more before it
        # stopped with a closed market (None: nothing is known to follow, the last quote stays tradable)
        self.after_ms = int(after_ms) if after_ms is not None else (int(t_ms[-1]) if len(t_ms) else 0)
        self.close_only_break_ms = int(close_only_break_ms)
        self.close_only_weekend_ms = int(close_only_weekend_ms)
        self.reopen_until = -(1 << 60)
        for name, code in _MT5_TF.items():
            setattr(self, f"TIMEFRAME_{name}", code)
        span_s = int((t_ms[-1] - t_ms[0]) // 1000) + 1 if len(t_ms) else 0
        self.bars: Dict[str, _Bars] = {}
        for name, tf_s in TF_SECONDS.items():
            b = _Bars(tf_s, warm_bars + span_s // tf_s + 64)
            if warm_m1 and len(warm_m1["t"]):
                wb = store.resample_bars(warm_m1, tf_s)
                b.seed({k: v[-warm_bars:] for k, v in wb.items()})
            self.bars[name] = b
        for d in sorted(history or [], key=lambda d: int(d["t_ms"])):
            self.add_history_deal(**d)

    # ── time advance: the terminal knows every tick up to "now" ──
    def _sync(self) -> None:
        now = self.clock.now_ms
        t_ms, bid = self.t_ms, self.bid
        n = len(t_ms)
        p = self.ptr
        bars = list(self.bars.values())
        while p + 1 < n and t_ms[p + 1] <= now:
            p += 1
            if p > 0:
                gap = int(t_ms[p] - t_ms[p - 1])
                if gap >= 86_400_000:
                    self.reopen_until = int(t_ms[p]) + self.close_only_weekend_ms
                elif gap >= K.SESSION_BREAK_MS:
                    self.reopen_until = int(t_ms[p]) + self.close_only_break_ms
            ts = int(t_ms[p] // 1000)
            px = float(bid[p])
            for b in bars:
                b.on_tick(ts, px)
        self.ptr = p
        while self._scheduled and self._scheduled[0]["t_ms"] <= now:
            self.add_history_deal(**self._scheduled.pop(0), book=True)

    def schedule_deal(self, **deal) -> None:
        """A deal of someone else on this account that happens at ``deal['t_ms']`` during the replay
        (``add_history_deal`` keywords): from then on it is in the history and in the balance."""
        self._scheduled.append(dict(deal))
        self._scheduled.sort(key=lambda d: int(d["t_ms"]))

    def _quote(self):
        """(bid, ask) in force now, or (nan, nan) before the first quote."""
        self._sync()
        if self.ptr < 0:
            return math.nan, math.nan
        return float(self.bid[self.ptr]), float(self.ask[self.ptr])

    # ── session / account ──
    def initialize(self, *a, **k):
        return True

    def login(self, *a, **k):
        return True

    def shutdown(self):
        return True

    def version(self):
        return (5, 0, 0)

    def last_error(self):
        return self._last_error

    def terminal_info(self):
        return TerminalInfo(community_account=False, community_connection=False, connected=True,
                            dlls_allowed=False, trade_allowed=True, tradeapi_disabled=False, email_enabled=False,
                            ftp_enabled=False, notifications_enabled=False, mqid=False, build=0, maxbars=100000,
                            codepage=0, ping_last=0, community_balance=0.0, retransmission=0.0, company="SimMT5",
                            name="SimMT5", language="English", path="", data_path="", commondata_path="")

    def _floating(self) -> float:
        self._sync()
        if self.ptr < 0:
            return 0.0
        b, a = float(self.bid[self.ptr]), float(self.ask[self.ptr])
        return sum(self._pos_profit(p, b, a) for p in self.positions)

    def _pos_profit(self, p: dict, b: float, a: float) -> float:
        if p["type"] == 0:
            return _round2((b - p["price_open"]) * p["volume"] * self.contract)
        return _round2((p["price_open"] - a) * p["volume"] * self.contract)

    def _margin(self) -> float:
        return sum(p["volume"] * self.contract * p["price_open"] / self.leverage for p in self.positions)

    def account_info(self):
        profit = self._floating()
        equity = self.balance + profit
        margin = self._margin()
        return AccountInfo(
            login=0, trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, leverage=int(self.leverage), limit_orders=0,
            margin_so_mode=0, trade_allowed=True, trade_expert=True, margin_mode=self.margin_mode,
            currency_digits=2, fifo_close=False,
            balance=self.balance, credit=0.0, profit=profit, equity=equity, margin=margin,
            margin_free=equity - margin, margin_level=(equity / margin * 100.0) if margin > 0 else 0.0,
            margin_so_call=0.0, margin_so_so=0.0, margin_initial=0.0, margin_maintenance=0.0, assets=0.0,
            liabilities=0.0, commission_blocked=0.0, name="SimMT5", server="SimMT5", currency="USD",
            company="SimMT5")

    # ── symbols / ticks / rates ──
    def symbol_info(self, symbol):
        if symbol != self.symbol:
            return None
        b, a = self._quote()
        t = int(self.t_ms[self.ptr] // 1000) if self.ptr >= 0 else 0
        spread = int(round((a - b) / self.point)) if self.ptr >= 0 else 0
        tick_value = self.point * self.contract
        return SymbolInfo(
            name=symbol, path=symbol, description=symbol, visible=True, select=True,
            trade_mode=self.SYMBOL_TRADE_MODE_FULL, digits=self.digits, point=self.point, spread=spread,
            trade_contract_size=self.contract, trade_tick_size=self.point, trade_tick_value=tick_value,
            trade_tick_value_profit=tick_value, trade_tick_value_loss=tick_value,
            volume_min=self.volume_min, volume_max=self.volume_max, volume_step=self.volume_step, volume_limit=0.0,
            trade_stops_level=0, trade_freeze_level=0, filling_mode=3, order_mode=127, expiration_mode=15,
            currency_base=symbol[:3], currency_profit="USD", currency_margin="USD", swap_long=0.0, swap_short=0.0,
            bid=b, ask=a, time=t)

    def symbol_select(self, symbol, enable=True):
        return symbol == self.symbol

    def symbols_get(self, pattern=None):
        return ()

    def symbol_info_tick(self, symbol):
        if symbol != self.symbol:
            return None
        self._sync()
        if self.ptr < 0:
            return None
        i = self.ptr
        return Tick(time=int(self.t_ms[i] // 1000), bid=float(self.bid[i]), ask=float(self.ask[i]), last=0.0,
                    volume=0, time_msc=int(self.t_ms[i]), flags=6, volume_real=0.0)

    def _tf(self, timeframe) -> _Bars:
        return self.bars[_TF_BY_CODE[int(timeframe)]]

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        """``count`` bars ending ``start_pos`` bars before the newest (0 = the forming bar is the last row)."""
        if symbol != self.symbol:
            return None
        if int(start_pos) < 0 or int(count) < 0:
            self._last_error = (-2, "Invalid arguments")
            return None
        self._sync()
        return self._tf(timeframe).last(int(count), skip=int(start_pos))

    def copy_rates_from(self, symbol, timeframe, date_from, count):
        if symbol != self.symbol:
            return None
        self._sync()
        return self._tf(timeframe).last(int(count), upto_t=_epoch_s(date_from))

    def copy_rates_range(self, symbol, timeframe, date_from, date_to):
        if symbol != self.symbol:
            return None
        self._sync()
        return self._tf(timeframe).between(_epoch_s(date_from), _epoch_s(date_to))

    def copy_ticks_from(self, symbol, date_from, count, flags):
        return None   # only used to "warm" the feed and for a stale-M1 rebuild that cannot occur here

    # ── history ──
    def add_history_deal(self, t_ms, type, entry, profit=0.0, magic=0, volume=0.0, price=0.0, symbol=None,
                         comment="", position_id=0, order=0, swap=0.0, commission=0.0, fee=0.0, reason=0,
                         book: bool = False) -> int:
        """
        Put a deal into the account's history (a deposit, a trade of another bot or of the owner).
        ``book=True`` also moves the balance by its result (a deal happening now; the starting
        balance already holds those of the past). Returns the deal ticket.
        """
        self._deal_ticket += 1
        sym = ("" if int(type) not in (0, 1) else self.symbol) if symbol is None else str(symbol)
        self.history.append(dict(ticket=self._deal_ticket, order=int(order), t_ms=int(t_ms), type=int(type),
                                 entry=int(entry), magic=int(magic), position_id=int(position_id), reason=int(reason),
                                 volume=float(volume), price=float(price), commission=float(commission),
                                 swap=float(swap), profit=float(profit), fee=float(fee), symbol=sym,
                                 comment=str(comment)))
        if book:
            self.balance += float(profit) + float(swap) + float(commission) + float(fee)
        return self._deal_ticket

    def _deal_tuple(self, d: dict) -> TradeDeal:
        return TradeDeal(ticket=d["ticket"], order=d["order"], time=d["t_ms"] // 1000, time_msc=d["t_ms"],
                         type=d["type"], entry=d["entry"], magic=d["magic"], position_id=d["position_id"],
                         reason=d["reason"], volume=d["volume"], price=d["price"], commission=d["commission"],
                         swap=d["swap"], profit=d["profit"], fee=d["fee"], symbol=d["symbol"], comment=d["comment"],
                         external_id="")

    def history_deals_get(self, date_from=None, date_to=None, group=None, ticket=None, position=None):
        """
        Deals of the account, oldest first, as the MetaTrader5 package serves them: by time
        (``date_from <= time <= date_to``, whole seconds; naive datetimes are local time, as for the
        real package), optionally narrowed by a ``group`` of symbols; or every deal of one order
        (``ticket``) or of one position (``position``). A closing deal has the opposite type of
        its position (a buy is closed by a sell) and the magic number and comment of the request
        that closed it.
        """
        self._sync()
        if ticket is not None:
            sel = [d for d in self.history if d["order"] == int(ticket)]
        elif position is not None:
            sel = [d for d in self.history if d["position_id"] == int(position)]
        else:
            if date_from is None or date_to is None:
                self._last_error = (-2, "Invalid arguments")
                return None
            a, b = _epoch_s(date_from), _epoch_s(date_to)
            sel = [d for d in self.history if a <= d["t_ms"] // 1000 <= b]
            if group:
                sel = [d for d in sel if _group_match(d["symbol"], group)]
        return tuple(self._deal_tuple(d) for d in sel)

    def history_deals_total(self, date_from, date_to):
        deals = self.history_deals_get(date_from, date_to)
        return len(deals) if deals is not None else 0

    def history_orders_get(self, *a, **k):
        return ()

    def history_orders_total(self, *a, **k):
        return 0

    def orders_get(self, *a, **k):
        return ()   # no pending orders on this terminal

    def orders_total(self):
        return 0

    # ── positions / orders ──
    def add_position(self, type, volume, price_open, t_ms=None, magic=0, comment="", sl=0.0, tp=0.0) -> int:
        """Open a position that the bot under test did not open (another bot's, the owner's).
        Its opening deal goes into the history; the balance does not move. Returns its ticket."""
        self._ticket += 1
        t = int(self.clock.now_ms if t_ms is None else t_ms)
        p = dict(ticket=self._ticket, type=int(type), volume=float(volume), price_open=float(price_open), time=t,
                 magic=int(magic), comment=str(comment), sl=float(sl), tp=float(tp), reason=self.POSITION_REASON_CLIENT,
                 foreign=True)
        self.positions.append(p)
        self.add_history_deal(t, type=int(type), entry=self.DEAL_ENTRY_IN, magic=int(magic), volume=float(volume),
                              price=float(price_open), comment=str(comment), position_id=p["ticket"],
                              order=p["ticket"], reason=self.DEAL_REASON_CLIENT)
        return p["ticket"]

    def _position_tuple(self, p: dict, b: float, a: float) -> TradePosition:
        profit = self._pos_profit(p, b, a) if not math.isnan(b) else 0.0
        return TradePosition(
            ticket=p["ticket"], time=p["time"] // 1000, time_msc=p["time"], time_update=p["time"] // 1000,
            time_update_msc=p["time"], type=p["type"], magic=p.get("magic", 0), identifier=p["ticket"],
            reason=p.get("reason", self.POSITION_REASON_EXPERT), volume=p["volume"], price_open=p["price_open"],
            sl=p.get("sl", 0.0), tp=p.get("tp", 0.0), price_current=(b if p["type"] == 0 else a), swap=0.0,
            profit=profit, symbol=self.symbol, comment=p.get("comment", ""), external_id="")

    def positions_get(self, symbol=None, group=None, ticket=None, **k):
        """Open positions: all of them, or those of one ``symbol``, of a ``group`` of symbols, or one ``ticket``."""
        self._sync()
        if symbol is not None and symbol != self.symbol:
            return ()
        if group is not None and not _group_match(self.symbol, group):
            return ()
        if self.ptr < 0:
            return ()
        b, a = float(self.bid[self.ptr]), float(self.ask[self.ptr])
        return tuple(self._position_tuple(p, b, a) for p in self.positions
                     if ticket is None or p["ticket"] == int(ticket))

    def positions_total(self):
        return len(self.positions)

    @staticmethod
    def _bad_field(request: dict) -> Optional[str]:
        """The first field of a request the MetaTrader5 package itself would refuse (order_send -> None)."""
        if "comment" in request and (not isinstance(request["comment"], str)
                                     or len(request["comment"]) > MAX_COMMENT_LEN):
            return "comment"
        if "magic" in request:
            m = request["magic"]
            if isinstance(m, bool) or not isinstance(m, numbers.Integral) or not 0 <= int(m) < 2 ** 64:
                return "magic"
        if "volume" in request and (isinstance(request["volume"], bool)
                                    or not isinstance(request["volume"], numbers.Real)):
            return "volume"
        return None

    def _result(self, retcode, deal=0, order=0, volume=0.0, price=0.0, comment="", request=None):
        b, a = (float(self.bid[self.ptr]), float(self.ask[self.ptr])) if self.ptr >= 0 else (0.0, 0.0)
        req = None
        if request is not None:
            base = dict(action=0, magic=0, order=0, symbol="", volume=0.0, price=0.0, stoplimit=0.0, sl=0.0, tp=0.0,
                        deviation=0, type=0, type_filling=0, type_time=0, expiration=0, comment="", position=0,
                        position_by=0)
            base.update({k: v for k, v in request.items() if k in base})
            req = TradeRequest(**base)
        return OrderSendResult(retcode=retcode, deal=deal, order=order, volume=volume, price=price, bid=b, ask=a,
                               comment=comment, request_id=0, retcode_external=0, request=req)

    def order_check(self, request: dict):
        acct = self.account_info()
        return OrderCheckResult(retcode=0, balance=acct.balance, equity=acct.equity, profit=acct.profit,
                                margin=acct.margin, margin_free=acct.margin_free, margin_level=acct.margin_level,
                                comment="Done", request=None)

    def _unsupported(self, request: dict, why: str):
        self.unsupported.append(f"{self.clock.now_ms}: {why}: {request}")
        return self._result(self.TRADE_RETCODE_INVALID, comment=why, request=request)

    def order_send(self, request: dict):
        self._last_error = (1, "Success")
        if not isinstance(request, dict):
            self._last_error = (-2, 'Invalid "request" argument')
            self.invalid_requests += 1
            return None
        bad = self._bad_field(request)
        if bad:
            self._last_error = (-2, f'Invalid "{bad}" argument')
            self.invalid_requests += 1
            return None
        self._sync()
        i = self.ptr
        if i < 0:
            return self._result(self.TRADE_RETCODE_PRICE_OFF, comment="No prices", request=request)
        action = int(request.get("action", self.TRADE_ACTION_DEAL))
        if action == self.TRADE_ACTION_SLTP:
            return self._modify_sltp(request)
        if action != self.TRADE_ACTION_DEAL:
            return self._unsupported(request, "SimMT5 executes market deals and SL/TP changes only")
        if request.get("symbol", self.symbol) != self.symbol:
            return self._unsupported(request, f"SimMT5 has quotes for {self.symbol} only")
        b, a = float(self.bid[i]), float(self.ask[i])
        now = self.clock.now_ms
        refuse = lambda code, why: self._result(code, comment=why, request=request)
        next_t = int(self.t_ms[i + 1]) if i + 1 < len(self.t_ms) else self.after_ms
        if next_t - int(self.t_ms[i]) >= K.SESSION_BREAK_MS and now - int(self.t_ms[i]) > K.SESSION_CLOSE_GRACE_MS:
            self.rejects += 1
            self.refused["market_closed"] += 1
            return refuse(self.TRADE_RETCODE_MARKET_CLOSED, "Market closed")
        magic = int(request.get("magic", 0))
        comment = request.get("comment", "")
        if "position" in request:
            return self._close(request, b, a, now, i, magic, comment)
        if now < self.reopen_until:
            self.rejects += 1
            self.refused["close_only"] += 1
            return refuse(self.TRADE_RETCODE_CLOSE_ONLY, "Only position closing is allowed")
        typ = int(request["type"])
        if typ not in (self.ORDER_TYPE_BUY, self.ORDER_TYPE_SELL):
            return self._unsupported(request, "a market deal is a buy or a sell")
        vol = _round2(float(request["volume"]))
        steps = vol / self.volume_step
        if vol < self.volume_min - 1e-9 or vol > self.volume_max + 1e-9 or abs(steps - round(steps)) > 1e-6:
            self.rejects += 1
            self.refused["invalid_volume"] += 1
            return refuse(self.TRADE_RETCODE_INVALID_VOLUME, "Invalid volume")
        price = a if typ == self.ORDER_TYPE_BUY else b
        equity = self.balance + sum(self._pos_profit(p, b, a) for p in self.positions)
        if vol * self.contract * price / self.leverage > equity - self._margin():
            self.rejects += 1
            self.refused["no_money"] += 1
            return refuse(self.TRADE_RETCODE_NO_MONEY, "No money")
        self._ticket += 1
        ticket = self._ticket
        self.positions.append(dict(ticket=ticket, type=typ, volume=vol, price_open=price, time=now, magic=magic,
                                   comment=comment, sl=float(request.get("sl", 0.0) or 0.0),
                                   tp=float(request.get("tp", 0.0) or 0.0), reason=self.POSITION_REASON_EXPERT,
                                   foreign=False))
        deal = self.add_history_deal(now, type=typ, entry=self.DEAL_ENTRY_IN, magic=magic, volume=vol, price=price,
                                     comment=comment, position_id=ticket, order=ticket, reason=self.DEAL_REASON_EXPERT)
        self.deals.append(dict(t_ms=now, tick_ms=int(self.t_ms[i]), entry="in", type=typ, volume=vol,
                               price=price, profit=0.0, ticket=ticket, open_t_ms=now,
                               price_open=price, balance=self.balance, deal=deal, order=ticket, magic=magic,
                               comment=comment, symbol=self.symbol, position_id=ticket))
        return self._result(self.TRADE_RETCODE_DONE, deal=deal, order=ticket, volume=vol, price=price,
                            comment="Request executed", request=request)

    def _close(self, request: dict, b: float, a: float, now: int, i: int, magic: int, comment: str):
        """A deal against an open position: closes it, or the requested part of it."""
        for k, p in enumerate(self.positions):
            if p["ticket"] != request["position"]:
                continue
            if "type" in request and int(request["type"]) != 1 - p["type"]:
                return self._result(self.TRADE_RETCODE_INVALID, comment="Invalid request", request=request)
            vol = p["volume"]
            if request.get("volume") is not None:
                want = _round2(float(request["volume"]))
                if want > p["volume"] + 1e-9 or want <= 0.0:
                    return self._result(self.TRADE_RETCODE_INVALID_CLOSE_VOLUME, comment="Invalid close volume",
                                        request=request)
                vol = min(want, p["volume"])
            price = b if p["type"] == 0 else a
            part = dict(p, volume=vol)
            profit = self._pos_profit(part, price, price)
            self.balance += profit
            self.own_balance += profit
            self._ticket += 1
            order = self._ticket
            deal = self.add_history_deal(now, type=1 - p["type"], entry=self.DEAL_ENTRY_OUT, profit=profit,
                                         magic=magic, volume=vol, price=price, comment=comment,
                                         position_id=p["ticket"], order=order, reason=self.DEAL_REASON_EXPERT)
            self.deals.append(dict(t_ms=now, tick_ms=int(self.t_ms[i]), entry="out", type=p["type"],
                                   volume=vol, price=price, profit=profit, ticket=p["ticket"],
                                   open_t_ms=p["time"], price_open=p["price_open"], balance=self.balance,
                                   deal=deal, order=order, magic=magic, comment=comment, symbol=self.symbol,
                                   position_id=p["ticket"], position_magic=p.get("magic", 0),
                                   foreign=bool(p.get("foreign", False))))
            if vol >= p["volume"] - 1e-9:
                del self.positions[k]
            else:
                p["volume"] = _round2(p["volume"] - vol)
            return self._result(self.TRADE_RETCODE_DONE, deal=deal, order=order, volume=vol, price=price,
                                comment="Request executed", request=request)
        return self._result(self.TRADE_RETCODE_INVALID, comment="Position not found", request=request)

    def _modify_sltp(self, request: dict):
        """TRADE_ACTION_SLTP: new SL / TP of a position. The levels are kept and served, never executed."""
        for p in self.positions:
            if p["ticket"] == request.get("position"):
                p["sl"] = float(request.get("sl", 0.0) or 0.0)
                p["tp"] = float(request.get("tp", 0.0) or 0.0)
                return self._result(self.TRADE_RETCODE_DONE, order=p["ticket"], comment="Request executed",
                                    request=request)
        return self._result(self.TRADE_RETCODE_INVALID, comment="Position not found", request=request)


_LIVE_MODULES = ("MetaTrader5", "constants", "strategy", "indicator", "mt5_helper", "app")


def _from_root(mod, root: Path) -> bool:
    f = getattr(mod, "__file__", None)
    if not f:
        return False
    try:
        return Path(f).resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


@contextmanager
def live_code(live_root: Path, sim: SimMT5):
    """
    Import the live modules from ``live_root`` with ``MetaTrader5`` replaced by ``sim``.

    Besides the six known modules, every other module the live code imports from ``live_root``
    (a demo branch's own helpers) is listed in ``extra`` and removed again afterwards, so the
    next replay -- possibly of another checkout -- imports its own. No bytecode is written into
    ``live_root`` while it is imported.
    """
    root = Path(live_root).resolve()
    saved = {n: sys.modules.get(n) for n in _LIVE_MODULES}
    for n in _LIVE_MODULES:
        sys.modules.pop(n, None)
    before = set(sys.modules)
    sys.modules["MetaTrader5"] = sim  # type: ignore[assignment]
    sys.path.insert(0, str(root))
    no_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True

    def extras():
        return {n: m for n, m in list(sys.modules.items())
                if n not in before and n not in _LIVE_MODULES and n.split(".")[0] not in ("backtesting", "tests")
                and _from_root(m, root)}

    try:
        import app  # noqa: F401  (pulls in strategy, indicator, mt5_helper, constants)
        ns = {n: sys.modules[n] for n in _LIVE_MODULES if n in sys.modules}
        yield types.SimpleNamespace(**ns, extra=extras())
    finally:
        sys.dont_write_bytecode = no_bytecode
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        for n in extras():
            sys.modules.pop(n, None)
        for n in _LIVE_MODULES:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


def _live_modules(mods) -> list:
    """Every live module of a ``live_code`` namespace (not the simulated terminal)."""
    out = [getattr(mods, n) for n in ("constants", "strategy", "indicator", "mt5_helper", "app") if hasattr(mods, n)]
    out += list((getattr(mods, "extra", None) or {}).values())
    return out


def _hhmm(week_min: int):
    d, rem = divmod(int(week_min), 1440)
    return _DAY_NAMES[d % 7], f"{rem // 60:02d}:{rem % 60:02d}"


def _scalar_weights(w: dict, what: str) -> dict:
    out = {}
    for tf, (r, m) in w.items():
        if r != m:
            raise ValueError(f"the live strategy has one weight per timeframe; {what}[{tf}] has rsi {r} != macd {m}")
        out[tf] = int(r) if float(r).is_integer() else r
    return out


# ───────────────────────────── the demo contract ─────────────────────────────
# A demo branch implements the levers of the backtest designs behind these constants (a block at the
# end of its constants.py sets its design; the defaults reproduce the live bot v3.9.2). In a reference
# replay each is set from the BacktestConfig field of the same meaning (design_constants).
CONTRACT_NAMES = ("DESIGN_NAME", "FORCE_CLOSE_ENABLED", "TREND_TF", "VOL_TF", "VOL_LEN", "TARGET_USD_PER_UNIT",
                  "STOP_LOSS_USD_PER_UNIT", "TARGET_VOL", "STOP_VOL", "VOL_CAP_USD_PER_UNIT", "LOSS_COOLDOWN_S",
                  "MAX_ADDS", "LADDER_TRIGGER", "LADDER_TFS", "LADDER_GAP_VOL", "LADDER_MULTIPLIERS", "STRATEGY",
                  "ORDER_COMMENT", "VIRTUAL_START_BALANCE", "VIRTUAL_START_DATE")
# the ladder triggers a demo branch implements
CONTRACT_LADDER_TRIGGERS = ("rsi_level", "macd_turn")


def contract_of(constants_module) -> bool:
    """
    True if a live ``constants`` module implements the demo contract. A module that defines only
    part of it is an error (a misspelt or forgotten name would otherwise leave a lever at a
    value nobody set).
    """
    present = [n for n in CONTRACT_NAMES if hasattr(constants_module, n)]
    if not present:
        return False
    missing = [n for n in CONTRACT_NAMES if not hasattr(constants_module, n)]
    if missing:
        raise ValueError(f"the live constants.py defines part of the demo contract only; missing: {', '.join(missing)}")
    return True


def _fibo_multipliers(cfg: BacktestConfig) -> bool:
    """Whether the adds this configuration can make are the live Fibonacci sizes."""
    m = [float(x) for x in cfg.ladder_multipliers] or [1.0]
    padded = m + [m[-1]] * 64          # the fast engine repeats the last element
    return all(padded[i] == float(FIBO[i]) for i in range(min(cfg.n_ladder_adds + 1, len(FIBO))))


def slope_timeframes(cfg: BacktestConfig) -> List[str]:
    """
    The timeframes a demo branch computes RSI / MACD pivot slopes for under ``cfg``: the open and
    force-close (agreement) sections (and the book section on netting), the trend timeframe (its
    MACD signal line), and the tiers' timeframes when an add is released by their MACD vote.
    """
    tfs = list(cfg.open_weights) + list(cfg.fc_weights)
    if cfg.book_enabled:
        tfs = list(cfg.open_weights) + list(cfg.book_weights) + list(cfg.fc_weights)
    if cfg.trend_tf:
        tfs.append(cfg.trend_tf)
    if cfg.ladder_trigger == "macd_turn":
        tfs += list(cfg.ladder_tfs[:cfg.n_ladder_adds])
    return ["TIMEFRAME_" + tf for tf in dict.fromkeys(tfs)]


def design_constants(cfg: BacktestConfig) -> Dict[str, object]:
    """
    The constants a demo branch must hold to run ``cfg``: the contract's (``CONTRACT_NAMES``, except
    ``DESIGN_NAME`` and ``ORDER_COMMENT``, which only label the bot) and the live bot's own that the
    design sets (scores, thresholds, indicators, cooldowns). ``VIRTUAL_START_*`` size the bot like the
    backtest: ``initial_balance``, counted from the UTC day the window starts.
    """
    if cfg.target_usd_per_unit is None:
        target, hedge = None, None
    else:
        target, hedge = "live", (int(cfg.target_usd_per_unit) if float(cfg.target_usd_per_unit).is_integer()
                                 else float(cfg.target_usd_per_unit))
    start = datetime.fromtimestamp(store.to_ms(cfg.start) / 1000.0, tz=timezone.utc)
    d: Dict[str, object] = {
        "OPEN_SCORE_WEIGHTS": _scalar_weights(cfg.open_weights, "open_weights"),
        "FORCE_CLOSE_SCORE_WEIGHTS": _scalar_weights(cfg.fc_weights, "fc_weights"),
        "SLOPE_TIMEFRAMES": slope_timeframes(cfg),
        "ENTRY_S": cfg.entry_s, "ENTRY_AGREE_S": cfg.entry_agree_s,
        "LADDER_S": cfg.ladder_s, "FORCE_CLOSE_S": cfg.force_close_s,
        "RSI_OVERSOLD": cfg.rsi_oversold, "RSI_OVERBOUGHT": cfg.rsi_overbought,
        "RSI_LENGTH": cfg.rsi_length, "MACD_FAST": cfg.macd_fast, "MACD_SLOW": cfg.macd_slow,
        "MACD_SIGNAL": cfg.macd_signal, "PEAK_LOOKBACK": cfg.peak_lookback, "PIVOT_WIDTH": cfg.pivot_width,
        "RSI_PEAK_OB": cfg.rsi_peak_ob, "RSI_PEAK_OS": cfg.rsi_peak_os,
        "REENTRY_COOLDOWN_SECONDS": cfg.reentry_cooldown_s,
        "ORDER_COOLDOWN_SECONDS": cfg.add_order_delay_ms / 1000.0,
        "MARKET_LOOKBACK_MINUTES": cfg.market_lookback_s / 60.0,
        "FORCE_CLOSE_ENABLED": bool(cfg.force_close_enabled),
        "TREND_TF": cfg.trend_tf,
        "VOL_TF": cfg.vol_tf,
        "VOL_LEN": int(cfg.vol_len),
        "TARGET_USD_PER_UNIT": target,
        "STOP_LOSS_USD_PER_UNIT": cfg.stop_loss_usd_per_unit,
        "TARGET_VOL": float(cfg.target_vol),
        "STOP_VOL": float(cfg.stop_vol),
        "VOL_CAP_USD_PER_UNIT": float(cfg.vol_cap_usd_per_unit),
        "LOSS_COOLDOWN_S": float(cfg.loss_cooldown_s),
        "MAX_ADDS": int(cfg.max_adds) if cfg.ladder_enabled else 0,
        "LADDER_TRIGGER": cfg.ladder_trigger,
        "LADDER_TFS": list(cfg.ladder_tfs),
        "LADDER_GAP_VOL": float(cfg.ladder_gap_vol),
        "LADDER_MULTIPLIERS": None if _fibo_multipliers(cfg) else [float(x) for x in cfg.ladder_multipliers],
        "STRATEGY": "basket",
        "VIRTUAL_START_BALANCE": float(cfg.initial_balance),
        "VIRTUAL_START_DATE": start.strftime("%Y-%m-%d"),
    }
    if hedge is not None:
        d["STRATEGY_HEDGE"] = hedge
    if cfg.book_enabled:
        d.update(BOOK_S=cfg.book_s, BOOK_SCORE_WEIGHTS=_scalar_weights(cfg.book_weights, "book_weights"),
                 PROFIT_PROTECT_USD_PER_UNIT=cfg.profit_protect_usd_per_unit)
    return d


def contract_overrides(c) -> Dict[str, object]:
    """
    The BacktestConfig fields a demo branch's contract constants hold (the inverse of ``design_constants``).
    ``BacktestConfig.live(symbol, repo_root=<branch>, **contract_overrides(constants))`` is then the design
    the branch runs: ``live()`` reads the classic constants (scores, thresholds, indicators, cooldowns),
    these add the levers.
    """
    tf = lambda x: None if x is None else str(x).replace("TIMEFRAME_", "")
    num = lambda x: None if x is None else float(x)
    target = c.TARGET_USD_PER_UNIT
    target = float(c.STRATEGY_HEDGE) if target == "live" else num(target)
    mult = c.LADDER_MULTIPLIERS
    return dict(force_close_enabled=bool(c.FORCE_CLOSE_ENABLED), trend_tf=tf(c.TREND_TF), vol_tf=tf(c.VOL_TF),
                vol_len=int(c.VOL_LEN), target_usd_per_unit=target, stop_loss_usd_per_unit=num(c.STOP_LOSS_USD_PER_UNIT),
                target_vol=float(c.TARGET_VOL), stop_vol=float(c.STOP_VOL),
                vol_cap_usd_per_unit=float(c.VOL_CAP_USD_PER_UNIT), loss_cooldown_s=float(c.LOSS_COOLDOWN_S),
                max_adds=int(c.MAX_ADDS), ladder_trigger=str(c.LADDER_TRIGGER),
                ladder_tfs=[tf(t) for t in c.LADDER_TFS], ladder_gap_vol=float(c.LADDER_GAP_VOL),
                ladder_multipliers=list(FIBO) if mult is None else [float(x) for x in mult])


def _uncovered_levers(cfg: BacktestConfig) -> List[str]:
    """The settings of ``cfg`` that neither the live bot nor the demo contract has (each must be off)."""
    checks = (
        ("slope_on_closed_bars", cfg.slope_on_closed_bars), ("ladder_on_closed_bars", cfg.ladder_on_closed_bars),
        ("min_hold_s", cfg.min_hold_s), ("fc_confirm_s", cfg.fc_confirm_s), ("entry_confirm_s", cfg.entry_confirm_s),
        ("ladder_min_gap", cfg.ladder_min_gap), ("ladder_min_interval_s", cfg.ladder_min_interval_s),
        ("max_hold_s", cfg.max_hold_s), ("target_per_lot", cfg.target_per_lot),
        ("entry_hours_utc", cfg.entry_hours_utc is not None),
        ("allow_long", not cfg.allow_long), ("allow_short", not cfg.allow_short),
        ("fc_grey_fill", cfg.fc_grey_fill), ("open_grey_fill", not cfg.open_grey_fill),
        ("agree_weights", cfg.agree_weights is not None),
        ("trend_mode", cfg.trend_tf is not None and cfg.trend_mode != 1),
        ("entry_max_spread", cfg.entry_max_spread),
        ("daily_loss_limit_usd_per_unit", cfg.daily_loss_limit_usd_per_unit),
        ("trail_gap_usd_per_unit", cfg.trail_gap_usd_per_unit), ("trail_gap_vol", cfg.trail_gap_vol),
        ("entry_rsi_block_tfs", cfg.entry_rsi_block_tfs is not None), ("fc_rsi_tfs", cfg.fc_rsi_tfs is not None),
        ("ladder_trigger", cfg.n_ladder_adds > 0 and cfg.ladder_trigger not in CONTRACT_LADDER_TRIGGERS),
    )
    return [name for name, on in checks if on]


def _check_replayable(cfg: BacktestConfig) -> None:
    """What the simulated terminal and clock cannot reproduce, whatever the live code."""
    if cfg.spread_mult != 1.0 or cfg.extra_spread or cfg.slippage or cfg.commission_per_lot or cfg.latency_ms:
        raise ValueError("the reference engine fills at the raw quote with no extra costs")
    if cfg.poll_interval_ms != 1000 or cfg.poll_jitter_ms:
        raise ValueError("the live loop sleeps exactly 1 s per iteration (and its work takes no simulated time)")
    if cfg.open_order_delay_ms not in (0, 100):
        raise ValueError("the sleep inside the live buy()/sell() is fixed at 0.1 s")
    if cfg.stop_out_level != 0.0:
        raise ValueError("the simulated terminal has no stop-out; keep stop_out_level at 0 for a reference run")
    if cfg.fixed_units:
        raise ValueError("the live unit is always derived from the balance")


def _apply_contract(mods, cfg: BacktestConfig) -> Dict[str, object]:
    """Drive a demo branch's contract constants (and the classic ones) from ``cfg``, in every live module."""
    c, s = mods.constants, mods.strategy
    if str(getattr(c, "STRATEGY", "basket")) != "basket":
        raise ValueError(f"this branch runs STRATEGY={c.STRATEGY!r}: the fast engine has no counterpart of it, "
                         f"so it cannot be replayed poll by poll against the kernel")
    is_netting = hasattr(s, "BOOK_SCORE_WEIGHTS")
    if cfg.book_enabled != is_netting:
        raise ValueError(f"config variant ({'netting' if cfg.book_enabled else 'hedging'}) does not match "
                         f"the live strategy.py under test ({'netting' if is_netting else 'hedging'})")
    if is_netting and cfg.target_usd_per_unit is not None:
        raise ValueError("the live netting variant has no fixed target")
    if is_netting and not cfg.book_grey_fill:
        raise ValueError("the live book score always grey-fills")
    uncovered = _uncovered_levers(cfg)
    if uncovered:
        raise ValueError(f"not part of the live code nor of the demo contract: {', '.join(uncovered)}")
    _check_replayable(cfg)
    values = design_constants(cfg)
    live = _live_modules(mods)
    for name, value in values.items():
        for m in live:
            if hasattr(m, name) or m is c:
                setattr(m, name, value)       # one object for all modules, as `from constants import NAME` shares it
    return values


def _apply_config(mods, cfg: BacktestConfig) -> Dict[str, object]:
    """
    Push a BacktestConfig into the live modules' own constants (they are read at call time).

    A demo branch (its constants.py defines ``CONTRACT_NAMES``) has every lever of the designs: its
    constants are set from ``cfg`` (``design_constants``); returns what was set. Any other branch is the
    live bot, which has only its own constants: a configuration it cannot run is refused (returns {}).
    """
    if getattr(mods, "constants", None) is not None and contract_of(mods.constants):
        return _apply_contract(mods, cfg)
    s, a, h = mods.strategy, mods.app, mods.mt5_helper
    is_netting = hasattr(s, "BOOK_SCORE_WEIGHTS")
    if cfg.book_enabled != is_netting:
        raise ValueError(f"config variant ({'netting' if cfg.book_enabled else 'hedging'}) does not match "
                         f"the live strategy.py under test ({'netting' if is_netting else 'hedging'})")
    if not is_netting and cfg.target_usd_per_unit != 1.0:
        raise ValueError("the live hedging target is fixed at $1 x unit (close_threshold=units)")
    if cfg.ladder_tfs != ["M1", "M5", "M15", "H1", "H4"] or not cfg.ladder_enabled:
        raise ValueError("the live ladder tiers are hard-coded M1/M5/M15/H1/H4")
    if list(cfg.ladder_multipliers[:6]) != [1, 2, 3, 5, 8, 13]:
        raise ValueError("the live ladder is Fibonacci 1,2,3,5,8,13")
    for name in ("slope_on_closed_bars", "ladder_on_closed_bars"):
        if getattr(cfg, name):
            raise ValueError(f"{name} is an experimental lever the live code does not have")
    if (cfg.min_hold_s or cfg.fc_confirm_s or cfg.entry_confirm_s or cfg.ladder_min_gap
            or cfg.ladder_min_interval_s or cfg.max_hold_s or cfg.target_per_lot
            or cfg.stop_loss_usd_per_unit is not None or cfg.entry_hours_utc is not None
            or not cfg.allow_long or not cfg.allow_short or cfg.max_adds < 5
            or cfg.fc_grey_fill or not cfg.open_grey_fill or not cfg.force_close_enabled):
        raise ValueError("experimental levers are not part of the live code")
    if cfg.spread_mult != 1.0 or cfg.extra_spread or cfg.slippage or cfg.commission_per_lot or cfg.latency_ms:
        raise ValueError("the reference engine fills at the raw quote with no extra costs")
    if cfg.poll_interval_ms != 1000 or cfg.poll_jitter_ms:
        raise ValueError("the live loop sleeps exactly 1 s per iteration (and its work takes no simulated time)")
    if cfg.open_order_delay_ms not in (0, 100):
        raise ValueError("the sleep inside the live buy()/sell() is fixed at 0.1 s")
    if is_netting and cfg.target_usd_per_unit is not None:
        raise ValueError("the live netting variant has no fixed target")
    if is_netting and not cfg.book_grey_fill:
        raise ValueError("the live book score always grey-fills")
    if cfg.stop_out_level != 0.0:
        raise ValueError("the simulated terminal has no stop-out; keep stop_out_level at 0 for a reference run")
    if cfg.fixed_units:
        raise ValueError("the live unit is always derived from the balance")

    s.ENTRY_S, s.ENTRY_AGREE_S = cfg.entry_s, cfg.entry_agree_s
    s.LADDER_S, s.FORCE_CLOSE_S = cfg.ladder_s, cfg.force_close_s
    s.RSI_OVERSOLD, s.RSI_OVERBOUGHT = cfg.rsi_oversold, cfg.rsi_overbought
    s.OPEN_SCORE_WEIGHTS = _scalar_weights(cfg.open_weights, "open_weights")
    s.FORCE_CLOSE_SCORE_WEIGHTS = _scalar_weights(cfg.fc_weights, "fc_weights")
    union = list(s.OPEN_SCORE_WEIGHTS) + list(s.FORCE_CLOSE_SCORE_WEIGHTS)
    if is_netting:
        s.BOOK_S = cfg.book_s
        s.BOOK_SCORE_WEIGHTS = _scalar_weights(cfg.book_weights, "book_weights")
        s.PROFIT_PROTECT_USD_PER_UNIT = cfg.profit_protect_usd_per_unit
        union = list(s.OPEN_SCORE_WEIGHTS) + list(s.BOOK_SCORE_WEIGHTS) + list(s.FORCE_CLOSE_SCORE_WEIGHTS)
    a.SLOPE_TIMEFRAMES = ["TIMEFRAME_" + tf for tf in dict.fromkeys(union)]
    a.RSI_LENGTH = cfg.rsi_length
    a.MACD_FAST, a.MACD_SLOW, a.MACD_SIGNAL = cfg.macd_fast, cfg.macd_slow, cfg.macd_signal
    a.PEAK_LOOKBACK, a.PIVOT_WIDTH = cfg.peak_lookback, cfg.pivot_width
    a.RSI_PEAK_OB, a.RSI_PEAK_OS = cfg.rsi_peak_ob, cfg.rsi_peak_os
    a.REENTRY_COOLDOWN_SECONDS = cfg.reentry_cooldown_s
    a.ORDER_COOLDOWN_SECONDS = cfg.add_order_delay_ms / 1000.0
    a.MARKET_LOOKBACK_MINUTES = cfg.market_lookback_s / 60.0
    return {}


def ladder_rsi_columns(ladder_tfs: Sequence[str]) -> List[str]:
    """Trace columns of the ladder tiers' RSI: ``rsi_<TF>``, or ``rsi_<q>_<TF>`` for a timeframe that several tiers use."""
    tfs = list(ladder_tfs)
    return [f"rsi_{q}_{tf}" if tfs.count(tf) > 1 else f"rsi_{tf}" for q, tf in enumerate(tfs)]


@dataclass
class ReferenceResult:
    cfg: BacktestConfig
    trace: pd.DataFrame          # one row per loop iteration
    deals: pd.DataFrame          # every fill the simulated terminal executed for the bot under test
    events: List[dict]           # what the bot logged (BUY_EXECUTED, CLOSE_BUY, ...)
    final_balance: float         # the bot's own: initial_balance + the result of its own fills
    final_equity: float
    iterations: int
    errors: List[str] = field(default_factory=list)
    rejects: int = 0
    refused: Dict[str, int] = field(default_factory=dict)   # orders the simulated broker refused, by reason
    history: Optional[pd.DataFrame] = None                  # every deal of the account, as history_deals_get has them
    account_balance: float = math.nan                       # the simulated account's balance at the end
    contract: Dict[str, object] = field(default_factory=dict)   # the demo-contract constants set (empty: live bot)
    invalid_requests: int = 0                               # requests the MetaTrader5 package would refuse (-> None)


_SIG = {"DO_NOTHING": 0, "BUY": 1, "SELL": 2, "CLOSE_BUY": 3, "CLOSE_SELL": 4, "BUY_MORE": 5, "SELL_MORE": 6}

# the live constants naming the bot's output directory (a replay points them at its own directory)
_OUTPUT_NAMES = ("OUTPUT_DIR",)


def run_reference(cfg: BacktestConfig, live_root: Path = REPO_ROOT, mode: str = "ticks",
                  warm_bars: int = 600, store_dir: Path = store.DEFAULT_STORE_DIR,
                  progress=None, hook=None, restart_at=None,
                  account_balance: Optional[float] = None, history: Optional[Sequence[dict]] = None,
                  positions: Optional[Sequence[dict]] = None, scheduled: Optional[Sequence[dict]] = None,
                  output_dir: Optional[Path] = None, trace_keys: Sequence[str] = ()) -> ReferenceResult:
    """
    Replay [cfg.start, cfg.end) through the live code found in ``live_root``.

    ``mode='ticks'`` feeds every tick (the truthful input). ``mode='sec'`` feeds the
    per-second series, which a 1 s poll on whole seconds cannot tell apart from ticks.

    Fault injection (used by tests/test_live_fault_injection.py; both default to off):

    ``hook(sim, clock)``  called once before the loop starts; wrap methods of the simulated
                          terminal to make it misbehave (a failed read, a rejected order ...).
    ``restart_at``        times (anything ``store.to_ms`` accepts) at which the bot process is
                          restarted: a new ``MT5TradingBot`` with fresh in-memory state takes
                          over, while the terminal keeps its positions and balance.

    The account (used by engine/demo_parity.py to check a demo branch's isolation; all default to
    an account that holds this bot alone):

    ``account_balance``   the account's balance at the start (default ``cfg.initial_balance``). The
                          bot's own balance -- what ``final_balance`` reports and the fast engine
                          is compared with -- starts at ``cfg.initial_balance`` either way.
    ``history``           deals made before the window (``SimMT5.add_history_deal`` keywords). A
                          deposit dated 30 days before the window makes up the rest of the balance.
    ``positions``         positions already open when the window starts (``SimMT5.add_position``
                          keywords; ``price_open`` defaults to the first quote).
    ``scheduled``         deals of others that happen during the window (``SimMT5.schedule_deal``).
    ``output_dir``        the live code's OUTPUT_DIR (default: a temporary directory), so whatever a
                          branch writes or reads there stays inside the replay and survives restarts.
    ``trace_keys``        further keys of the bot's analysis data to record per poll (columns ``x_<key>``).
    """
    start_ms, end_ms = store.to_ms(cfg.start), store.to_ms(cfg.end)
    rows = (store.load_ticks if mode == "ticks" else store.load_sec)(cfg.symbol, start_ms, end_ms, store_dir)
    if not rows:
        raise ValueError(f"no {mode} data for {cfg.symbol} in the requested window")
    span = store.data_span(cfg.symbol, store_dir)
    max_tf = max(TF_SECONDS.values())
    warm_from = max(store.to_ms(span[0]), start_ms - int(warm_bars * max_tf * 1000 * 1.7))
    warm_m1 = store.load_m1(cfg.symbol, warm_from, start_ms, store_dir) if warm_from < start_ms else {}

    clock = SimClock(start_ms, end_ms, [store.to_ms(x) for x in (restart_at or [])])
    # Like the fast engine, begin at the first poll that can see a tick: before that the
    # simulated terminal has history bars but no quote, a state a running terminal never has.
    first_tick = int(rows["t_ms"][0])
    if first_tick > start_ms:
        clock.now_ms = start_ms + -(-(first_tick - start_ms) // cfg.poll_interval_ms) * cfg.poll_interval_ms
    from .fast import _PRE_MS, _next_quote_ms, _silences
    acct0 = float(cfg.initial_balance if account_balance is None else account_balance)
    past = [dict(d) for d in (history or [])]
    shared = account_balance is not None or bool(past) or bool(positions) or bool(scheduled)
    if shared:
        held = sum(float(d.get("profit", 0.0)) + float(d.get("swap", 0.0)) + float(d.get("commission", 0.0))
                   + float(d.get("fee", 0.0)) for d in past)
        past.append(dict(t_ms=start_ms - 30 * 86_400_000, type=SimMT5.DEAL_TYPE_BALANCE, entry=SimMT5.DEAL_ENTRY_IN,
                         profit=acct0 - held, symbol="", comment="deposit"))
    sim = SimMT5(cfg.symbol, rows["t_ms"], rows["bid"], rows["ask"], clock, warm_m1,
                 cfg.spec.contract_size, cfg.effective_leverage, acct0, warm_bars,
                 close_only_break_ms=int(round(cfg.close_only_after_break_s * 1000)),
                 close_only_weekend_ms=int(round(cfg.close_only_after_weekend_s * 1000)),
                 after_ms=_next_quote_ms(cfg.symbol, end_ms, store_dir),
                 digits=cfg.spec.digits, volume_min=cfg.spec.min_lot, volume_step=cfg.spec.lot_step,
                 own_balance=float(cfg.initial_balance), history=past)
    for p in positions or []:
        p = dict(p)
        if "price_open" not in p:
            p["price_open"] = float(rows["ask"][0] if int(p["type"]) == 0 else rows["bid"][0])
        p.setdefault("t_ms", start_ms - 3_600_000)
        sim.add_position(**p)
    for d in scheduled or []:
        sim.schedule_deal(**d)
    # a run that starts just after a session break inherits the broker's close-only window, as in the fast engine
    pre = store.load_sec(cfg.symbol, start_ms - _PRE_MS, start_ms, store_dir) if warm_from < start_ms else {}
    pre_t = np.asarray(pre["t_ms"], np.int64) if pre and len(pre["t_ms"]) else np.zeros(0, np.int64)
    gaps = _silences(warm_m1, rows["t_ms"], np.concatenate([pre_t, np.asarray(rows["t_ms"][:1], np.int64)]))
    past_gaps = gaps[gaps[:, 1] <= max(start_ms, first_tick)] if len(gaps) else gaps
    if len(past_gaps):
        length = int(past_gaps[-1][1] - past_gaps[-1][0])
        if length >= 86_400_000:
            sim.reopen_until = int(past_gaps[-1][1]) + sim.close_only_weekend_ms
        elif length >= K.SESSION_BREAK_MS:
            sim.reopen_until = int(past_gaps[-1][1]) + sim.close_only_break_ms

    trace_rows: List[tuple] = []
    events: List[dict] = []
    errors: List[str] = []
    state = {"iter_t": start_ms}
    tmp = tempfile.TemporaryDirectory(prefix="simmt5_output_") if output_dir is None else None
    out_dir = str(Path(tmp.name if tmp is not None else output_dir))

    try:
        with live_code(live_root, sim) as mods:
            contract = _apply_config(mods, cfg)
            app, helper_mod = mods.app, mods.mt5_helper
            sim_dt, sim_date = _sim_datetime_classes(clock)
            live = _live_modules(mods)
            for m in live:
                _patch_clocks(m, clock, sim_dt, sim_date)
                for name in _OUTPUT_NAMES:
                    if hasattr(m, name):
                        setattr(m, name, out_dir)

            def _print(*args, **kwargs):
                msg = " ".join(str(x) for x in args)
                if "Error:" in msg or "WARNING" in msg:
                    errors.append(f"{clock.now_ms}: {msg}")

            for m in live:
                m.print = _print

            sd, st = _hhmm(cfg.window_start_min)
            ed, et = _hhmm(cfg.window_end_min)

            def _new_bot():
                """A freshly started bot process: all of process_symbol's local state starts over."""
                bot = app.MT5TradingBot(mode="demo", target_symbol=cfg.symbol)
                bot.symbols_config = {
                    "brake": 1 if cfg.brake else 0, "mtqty": cfg.mtqty,
                    "trading_window": {"enabled": bool(cfg.window_enabled), "start_day": sd, "start_time": st,
                                       "end_day": ed, "end_time": et},
                    "symbols": [{"symbol": cfg.symbol, "is_active": True,
                                 "step_up_balance": cfg.step_up_balance, "unit_max_limit": cfg.unit_max_limit}],
                }
                bot.symbols = [cfg.symbol]
                bot.symbol_configs = {cfg.symbol: bot.symbols_config["symbols"][0]}
                bot.symbol_map = {cfg.symbol: cfg.symbol}
                bot.position_helper = helper_mod.MT5PositionHelper(sim)
                bot.mt5_initialized = True
                bot._save_symbol_data = _save_symbol_data
                bot._save_account_data = lambda *a, **k: None
                bot._save_daily_trades = lambda *a, **k: None
                bot._save_historical_summary = lambda *a, **k: None
                bot._log_event = _log_event
                return bot

            # the first MT5 call of every iteration marks the iteration's timestamp
            real_select = sim.symbol_select

            def _select(symbol, enable=True):
                state["iter_t"] = clock.now_ms
                return real_select(symbol, enable)

            sim.symbol_select = _select

            ladder_keys = ["TIMEFRAME_" + tf for tf in cfg.ladder_tfs]
            extra_keys = list(trace_keys)

            def _save_symbol_data(symbol, data):
                an = data.get("analysis", {})
                sig = data.get("signal", {})
                code = _SIG[sig.get("buy_status", "DO_NOTHING")] or _SIG[sig.get("sell_status", "DO_NOTHING")]
                pos = data.get("positions", {})
                nb, ns = pos.get("buy", {}).get("count", 0), pos.get("sell", {}).get("count", 0)
                pr = pos.get("buy", {}).get("total_profit", 0) if nb else pos.get("sell", {}).get("total_profit", 0)
                rsi = an.get("rsi_mtf", {}) or {}
                trace_rows.append((
                    state["iter_t"], code, bool(an.get("candle_fresh", False)),
                    an.get("open_score", np.nan), an.get("fc_score", np.nan), an.get("book_score", np.nan),
                    nb - ns, pr, an.get("unit_times", 0), bool(an.get("entry_allowed", False)),
                    *[rsi.get(k, np.nan) for k in ladder_keys],
                    *[an.get(k) for k in extra_keys],
                ))
                if progress is not None and len(trace_rows) % 5000 == 0:
                    progress(len(trace_rows), state["iter_t"])

            def _log_event(symbol, event, tag, details=None, server_time=None):
                events.append({"t_ms": clock.now_ms, "iter_t": state["iter_t"], "event": event, "tag": tag,
                               "details": {k: v for k, v in (details or {}).items() if k != "response"}})

            if hook is not None:
                hook(sim, clock)

            restarts = 0
            while True:
                try:
                    _new_bot().process_symbol(cfg.symbol)
                    break
                except _Restart:
                    restarts += 1
                    events.append({"t_ms": clock.now_ms, "iter_t": clock.now_ms, "event": "PROCESS_RESTART",
                                   "tag": "SIM", "details": {"restart": restarts}})
                except _End:
                    break

            acct = sim.account_info()
    finally:
        if tmp is not None:
            tmp.cleanup()

    errors += [f"unsupported request {u}" for u in sim.unsupported]
    cols = ["t_ms", "signal", "fresh", "open_score", "fc_score", "book_score", "n_pos", "profit",
            "units", "entry_allowed"] + ladder_rsi_columns(cfg.ladder_tfs) + [f"x_{k}" for k in extra_keys]
    trace = pd.DataFrame(trace_rows, columns=cols)
    deals = pd.DataFrame(sim.deals) if sim.deals else pd.DataFrame(
        columns=["t_ms", "tick_ms", "entry", "type", "volume", "price", "profit", "ticket",
                 "open_t_ms", "price_open", "balance", "deal", "order", "magic", "comment", "symbol", "position_id"])
    hist = pd.DataFrame(sim.history) if sim.history else pd.DataFrame(
        columns=["ticket", "order", "t_ms", "type", "entry", "magic", "position_id", "reason", "volume", "price",
                 "commission", "swap", "profit", "fee", "symbol", "comment"])
    if not shared:
        final_balance, final_equity = float(sim.balance), float(acct.equity)
    else:
        own = [p for p in sim.positions if not p.get("foreign")]
        b, a = sim._quote()
        final_balance = float(sim.own_balance)
        final_equity = final_balance + (sum(sim._pos_profit(p, b, a) for p in own) if not math.isnan(b) else 0.0)
    return ReferenceResult(cfg=cfg, trace=trace, deals=deals, events=events,
                           final_balance=final_balance, final_equity=final_equity,
                           iterations=len(trace), errors=errors, rejects=sim.rejects, refused=dict(sim.refused),
                           history=hist, account_balance=float(sim.balance), contract=dict(contract),
                           invalid_requests=sim.invalid_requests)
