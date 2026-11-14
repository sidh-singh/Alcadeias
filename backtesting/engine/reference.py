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
"""

from __future__ import annotations

import math
import sys
import types
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import BacktestConfig, REPO_ROOT, TF_SECONDS
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


class _End(BaseException):
    """Raised by the simulated clock to leave the live loop (not an Exception on purpose:
    process_symbol swallows every Exception and keeps looping)."""


class _Restart(BaseException):
    """Raised by the simulated clock at a scheduled restart: the bot process 'dies' and is started again."""


def _round2(x: float) -> float:
    return math.floor(x * 100.0 + 0.5) / 100.0 if x >= 0 else -math.floor(-x * 100.0 + 0.5) / 100.0


class SimClock:
    """Stands in for the ``time`` module inside app.py / mt5_helper.py."""

    def __init__(self, start_ms: int, end_ms: int, restarts_ms: Optional[List[int]] = None):
        self.now_ms = int(start_ms)
        self.end_ms = int(end_ms)
        self.restarts_ms = sorted(int(x) for x in (restarts_ms or []))

    def time(self) -> float:
        return self.now_ms / 1000.0

    def perf_counter(self) -> float:
        return self.now_ms / 1000.0

    def sleep(self, seconds: float) -> None:
        self.now_ms += int(round(float(seconds) * 1000.0))
        if self.now_ms >= self.end_ms:
            raise _End()
        if self.restarts_ms and self.now_ms >= self.restarts_ms[0]:
            self.restarts_ms.pop(0)
            raise _Restart()


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

    def last(self, count: int, upto_t: Optional[int] = None) -> np.ndarray:
        n = self.n
        if upto_t is not None:
            n = int(np.searchsorted(self.t[:self.n], upto_t, side="right"))
        lo = max(0, n - count)
        out = np.zeros(n - lo, RATES_DTYPE)
        out["time"], out["open"], out["high"] = self.t[lo:n], self.o[lo:n], self.h[lo:n]
        out["low"], out["close"], out["tick_volume"] = self.l[lo:n], self.c[lo:n], self.v[lo:n]
        return out


class SimMT5:
    """The slice of the ``MetaTrader5`` module that app.py and mt5_helper.py use."""

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_NO_MONEY = 10019
    COPY_TICKS_ALL = -1
    SYMBOL_TRADE_MODE_DISABLED = 0

    def __init__(self, symbol: str, t_ms: np.ndarray, bid: np.ndarray, ask: np.ndarray,
                 clock: SimClock, warm_m1: Dict[str, np.ndarray], contract_size: float,
                 leverage: float, balance: float, warm_bars: int = 600):
        self.symbol = symbol
        self.t_ms, self.bid, self.ask = t_ms, bid, ask
        self.clock = clock
        self.contract = float(contract_size)
        self.leverage = float(leverage)
        self.balance = float(balance)
        self.ptr = -1
        self.positions: List[dict] = []
        self.deals: List[dict] = []
        self._ticket = 1000
        self.rejects = 0
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

    # ── time advance: the terminal knows every tick up to "now" ──
    def _sync(self) -> None:
        now = self.clock.now_ms
        t_ms, bid = self.t_ms, self.bid
        n = len(t_ms)
        p = self.ptr
        bars = list(self.bars.values())
        while p + 1 < n and t_ms[p + 1] <= now:
            p += 1
            ts = int(t_ms[p] // 1000)
            px = float(bid[p])
            for b in bars:
                b.on_tick(ts, px)
        self.ptr = p

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
        return (1, "Success")

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
        return types.SimpleNamespace(
            login=0, server="SimMT5", leverage=int(self.leverage),
            balance=self.balance, equity=equity, margin=margin, margin_free=equity - margin,
            margin_level=(equity / margin * 100.0) if margin > 0 else 0.0, profit=profit)

    # ── symbols / ticks / rates ──
    def symbol_info(self, symbol):
        if symbol != self.symbol:
            return None
        return types.SimpleNamespace(name=symbol, visible=True, select=True, trade_mode=4)

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
        return types.SimpleNamespace(time=int(self.t_ms[i] // 1000), time_msc=int(self.t_ms[i]),
                                     bid=float(self.bid[i]), ask=float(self.ask[i]), last=0.0, volume=0)

    def _tf(self, timeframe) -> _Bars:
        return self.bars[_TF_BY_CODE[int(timeframe)]]

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        if symbol != self.symbol:
            return None
        self._sync()
        b = self._tf(timeframe)
        if start_pos != 0:
            raise NotImplementedError("the live code only ever asks from position 0")
        return b.last(int(count))

    def copy_rates_from(self, symbol, timeframe, date_from, count):
        if symbol != self.symbol:
            return None
        self._sync()
        ts = int(date_from.timestamp()) if hasattr(date_from, "timestamp") else int(date_from)
        return self._tf(timeframe).last(int(count), upto_t=ts)

    def copy_ticks_from(self, symbol, date_from, count, flags):
        return None   # only used to "warm" the feed and for a stale-M1 rebuild that cannot occur here

    def history_deals_get(self, *a, **k):
        return ()

    # ── positions / orders ──
    def positions_get(self, symbol=None, **k):
        self._sync()
        if symbol is not None and symbol != self.symbol:
            return ()
        if self.ptr < 0:
            return ()
        b, a = float(self.bid[self.ptr]), float(self.ask[self.ptr])
        return tuple(types.SimpleNamespace(
            ticket=p["ticket"], type=p["type"], volume=p["volume"], price_open=p["price_open"],
            symbol=self.symbol, profit=self._pos_profit(p, b, a), time=p["time"] // 1000, swap=0.0)
            for p in self.positions)

    def order_send(self, request: dict):
        self._sync()
        i = self.ptr
        b, a = float(self.bid[i]), float(self.ask[i])
        now = self.clock.now_ms
        if "position" in request:
            for k, p in enumerate(self.positions):
                if p["ticket"] == request["position"]:
                    price = b if p["type"] == 0 else a
                    profit = self._pos_profit(p, price, price)
                    self.balance += profit
                    self.deals.append(dict(t_ms=now, tick_ms=int(self.t_ms[i]), entry="out", type=p["type"],
                                           volume=p["volume"], price=price, profit=profit, ticket=p["ticket"],
                                           open_t_ms=p["time"], price_open=p["price_open"], balance=self.balance))
                    del self.positions[k]
                    return types.SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, price=price,
                                                 volume=p["volume"], order=p["ticket"], deal=len(self.deals))
            return types.SimpleNamespace(retcode=10013, price=0.0, volume=0.0, order=0, deal=0)
        typ = int(request["type"])
        vol = _round2(float(request["volume"]))
        price = a if typ == self.ORDER_TYPE_BUY else b
        equity = self.balance + sum(self._pos_profit(p, b, a) for p in self.positions)
        if vol * self.contract * price / self.leverage > equity - self._margin():
            self.rejects += 1
            return types.SimpleNamespace(retcode=self.TRADE_RETCODE_NO_MONEY, price=0.0, volume=0.0, order=0, deal=0)
        self._ticket += 1
        self.positions.append(dict(ticket=self._ticket, type=typ, volume=vol, price_open=price, time=now))
        self.deals.append(dict(t_ms=now, tick_ms=int(self.t_ms[i]), entry="in", type=typ, volume=vol,
                               price=price, profit=0.0, ticket=self._ticket, open_t_ms=now,
                               price_open=price, balance=self.balance))
        return types.SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, price=price, volume=vol,
                                     order=self._ticket, deal=len(self.deals))


_LIVE_MODULES = ("MetaTrader5", "constants", "strategy", "indicator", "mt5_helper", "app")


@contextmanager
def live_code(live_root: Path, sim: SimMT5):
    """Import the live modules from ``live_root`` with ``MetaTrader5`` replaced by ``sim``."""
    root = str(Path(live_root).resolve())
    saved = {n: sys.modules.get(n) for n in _LIVE_MODULES}
    for n in _LIVE_MODULES:
        sys.modules.pop(n, None)
    sys.modules["MetaTrader5"] = sim  # type: ignore[assignment]
    sys.path.insert(0, root)
    try:
        import app  # noqa: F401  (pulls in strategy, indicator, mt5_helper, constants)
        yield types.SimpleNamespace(**{n: sys.modules[n] for n in _LIVE_MODULES if n in sys.modules})
    finally:
        try:
            sys.path.remove(root)
        except ValueError:
            pass
        for n in _LIVE_MODULES:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


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


def _apply_config(mods, cfg: BacktestConfig) -> None:
    """Push a BacktestConfig into the live modules' own constants (they are read at call time)."""
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
    if cfg.poll_interval_ms != 1000:
        raise ValueError("the live loop sleeps exactly 1 s per iteration")
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


@dataclass
class ReferenceResult:
    cfg: BacktestConfig
    trace: pd.DataFrame          # one row per loop iteration
    deals: pd.DataFrame          # every fill the simulated terminal executed
    events: List[dict]           # what the bot logged (BUY_EXECUTED, CLOSE_BUY, ...)
    final_balance: float
    final_equity: float
    iterations: int
    errors: List[str] = field(default_factory=list)
    rejects: int = 0


_SIG = {"DO_NOTHING": 0, "BUY": 1, "SELL": 2, "CLOSE_BUY": 3, "CLOSE_SELL": 4, "BUY_MORE": 5, "SELL_MORE": 6}


def run_reference(cfg: BacktestConfig, live_root: Path = REPO_ROOT, mode: str = "ticks",
                  warm_bars: int = 600, store_dir: Path = store.DEFAULT_STORE_DIR,
                  progress=None, hook=None, restart_at=None) -> ReferenceResult:
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
    sim = SimMT5(cfg.symbol, rows["t_ms"], rows["bid"], rows["ask"], clock, warm_m1,
                 cfg.spec.contract_size, cfg.effective_leverage, cfg.initial_balance, warm_bars)

    trace_rows: List[tuple] = []
    events: List[dict] = []
    errors: List[str] = []
    state = {"iter_t": start_ms}

    with live_code(live_root, sim) as mods:
        _apply_config(mods, cfg)
        app, helper_mod = mods.app, mods.mt5_helper

        class _SimDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromtimestamp(clock.now_ms / 1000.0, tz=tz or timezone.utc)

        helper_mod.datetime = _SimDatetime
        helper_mod.time = clock
        app.time = clock

        def _print(*args, **kwargs):
            msg = " ".join(str(x) for x in args)
            if "Error:" in msg or "WARNING" in msg:
                errors.append(f"{clock.now_ms}: {msg}")

        app.print = _print

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

    cols = ["t_ms", "signal", "fresh", "open_score", "fc_score", "book_score", "n_pos", "profit",
            "units", "entry_allowed"] + [f"rsi_{tf}" for tf in cfg.ladder_tfs]
    trace = pd.DataFrame(trace_rows, columns=cols)
    deals = pd.DataFrame(sim.deals) if sim.deals else pd.DataFrame(
        columns=["t_ms", "tick_ms", "entry", "type", "volume", "price", "profit", "ticket",
                 "open_t_ms", "price_open", "balance"])
    return ReferenceResult(cfg=cfg, trace=trace, deals=deals, events=events,
                           final_balance=float(sim.balance), final_equity=float(acct.equity),
                           iterations=len(trace), errors=errors, rejects=sim.rejects)
