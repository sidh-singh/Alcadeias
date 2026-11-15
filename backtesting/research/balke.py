"""
René Balke's (BM Trading GmbH) public strategies, re-built from their public descriptions and run on this suite's data,
costs and accounts, next to the final ten's leaders.

    python -m backtesting.research.balke run       the accounts (backtest_results/balke/)
    python -m backtesting.research.balke report    BALKE.md tables and charts

These are re-implementations from what he publishes (product descriptions, videos, posts), not his code: where a rule
or a default is not public, the choice made here is stated next to it (``ASSUMED``). His Expert Advisors may behave
differently in details.

Windows and accounts are the final ten's (``final10.py``): fresh $2,000 accounts on 8 years (13 Nov 2018 - 13 Nov 2026),
5 years, Nov 2018 - Dec 2020 and the last year; the M1-bar simulator of ``external.py`` (signals on closed bars, fills at
the next M1 open, buys at the ask, stops before targets inside a bar); no swap; the bot's unit rule unless a row says
otherwise. Server time is taken as New York + 7 h (the usual MetaTrader broker clock), as in ``external.london_breakout``.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..config import REPO_ROOT
from . import external as X
from . import final10 as F

OUT = REPO_ROOT / "backtest_results" / "balke"
SYMBOLS = ("XAUUSDm", "BTCUSDm")
DAY = 86400
NY = X.NY


@dataclass
class Row:
    """One replicated strategy and sizing on one symbol."""
    key: str
    name: str
    build: Callable[[X.Market], X.Built]
    variant: str = "standalone"                 # "standalone" (bot unit rule) or "risk-sized" (the source's own sizing)
    symbols: Sequence[str] = SYMBOLS
    source: str = ""
    assumed: str = ""
    spread_pct: Optional[float] = None          # a cost scenario: every bar's spread set to this % of its price
    multi: bool = False                         # every signal is its own trade (several positions at once)


ROWS: List[Row] = []                            # filled in below, from the research


def server_clock(m: X.Market) -> np.ndarray:
    """Wall-clock seconds of every M1 bar on a New-York + 7 h server clock (as if it were UTC)."""
    return m.local(NY) + 7 * 3600


def server_to_utc(loc_s: np.ndarray) -> np.ndarray:
    """Server wall-clock seconds -> UTC. A time the server clock skips (09:00 - 09:59 on the US spring-forward
    Sunday) maps to the first time that exists, as an EA waiting for ``time >= T`` acts then; a repeated time (the
    fall-back night) maps to its first occurrence."""
    loc = np.asarray(loc_s, np.int64) - 7 * 3600
    if len(loc) == 0:
        return np.zeros(0, np.int64)
    idx = pd.DatetimeIndex(pd.to_datetime(loc, unit="s")).tz_localize(NY, ambiguous=np.ones(len(loc), bool),
                                                                       nonexistent="shift_forward")
    return idx.tz_convert("UTC").tz_localize(None).values.astype("datetime64[s]").astype(np.int64)


# ───────────────────────────── markets outside the engine's list (index CFDs) ─────────────────────────────

# ASSUMED: Exness's contract for these CFDs is 1 lot = 1 x the index in USD, minimum 0.01 lot (not published in a
# readable form). His index strategies size by notional, so the contract only changes the lot rounding.
INDEX_SPECS = {"USTECm": dict(contract_size=1.0, digits=2), "US30m": dict(contract_size=1.0, digits=2)}
INDEX_HISTORY_FROM = "2020-06-01"
INDEX_WINDOWS = {"since 2020": ("2020-07-01", F.DATA_END), "5y": F.WINDOWS["5y"], "1y": F.WINDOWS["1y"]}


class SpecMarket(X.Market):
    """``external.Market`` for a symbol the engine does not list, with its contract given here."""

    def __init__(self, symbol: str, m1: Dict[str, np.ndarray], contract_size: float, digits: int,
                 around_the_clock: bool = False):
        self.symbol = symbol
        self.k = contract_size * 0.01
        self.tick = 10.0 ** (-digits)
        self.around_the_clock = around_the_clock
        self.t = np.ascontiguousarray(m1["t"], np.int64)
        self.o = np.ascontiguousarray(m1["o"], np.float64)
        self.h = np.ascontiguousarray(m1["h"], np.float64)
        self.l = np.ascontiguousarray(m1["l"], np.float64)
        self.c = np.ascontiguousarray(m1["c"], np.float64)
        self.sp = np.ascontiguousarray(m1["spread_mean"], np.float64)
        self.n = np.ascontiguousarray(m1["n"], np.float64)
        self._bars = {}
        self._local = {}


def load(symbol: str) -> X.Market:
    if symbol in INDEX_SPECS:
        from ..data import store
        m1 = store.load_m1(symbol, INDEX_HISTORY_FROM, F.DATA_END)
        if not m1 or len(m1["t"]) == 0:
            raise FileNotFoundError(f"no M1 bars for {symbol} in the store (python -m backtesting data --symbols {symbol} ...)")
        return SpecMarket(symbol, m1, **INDEX_SPECS[symbol])
    return X.load_market(symbol, earliest=F.HISTORY_FROM[symbol], end=F.DATA_END)


def windows_for(symbol: str) -> Dict[str, tuple]:
    """The final ten's windows; the index data starts in mid-2020, so the indices (and, for the portfolio, every
    market) also run from July 2020."""
    if symbol in INDEX_SPECS:
        return dict(INDEX_WINDOWS)
    return {**F.WINDOWS, "since 2020": INDEX_WINDOWS["since 2020"]}


# ───────────────────────────── his four strategies (Four Edge EA, settings files of 10 Oct 2026) ─────────────────────

def _days(loc: np.ndarray) -> np.ndarray:
    return loc // DAY


def _weekday(day: np.ndarray) -> np.ndarray:
    return (day + 3) % 7                         # 0 = Monday (1 Jan 1970 was a Thursday)


def range_breakout(m: X.Market, start: tuple, end: tuple, close: tuple, stop: str, stop_value: float, risk_pct: float,
                   weekdays_only: bool = True, min_range_pct: float = 0.0, max_range_pct: float = 100.0) -> X.Built:
    """
    Range Breakout (Four Edge module): the highest and lowest price between ``start`` and ``end`` (server time); at
    ``end`` a buy stop at the range high and a sell stop at the range low (no buffer); the first fill cancels the other
    (MaxTrades 1); a side whose level price has already passed when the orders go in is skipped; stop ``stop`` =
    "factor" (x the range from the entry, 1.0 = the opposite side) or "percent" (of the entry price); no target; pending
    orders deleted and the position closed at ``close``. Risk ``risk_pct`` of balance at the stop.
    ASSUMED: the range uses the M1 bars that open in [start, end) (the bar opening at ``end`` has no prices yet when the
    orders go in); a session needs quotes in at least half of its window's minutes; high and low are bid prices, a buy
    stop triggers on the ask (as MT5 does).
    """
    loc = server_clock(m)
    day = _days(loc)
    minute = (loc % DAY) // 60
    s_min, e_min, c_min = start[0] * 60 + start[1], end[0] * 60 + end[1], close[0] * 60 + close[1]
    in_rng = (minute >= s_min) & (minute < e_min)
    if weekdays_only:
        in_rng &= _weekday(day) <= 4
    idx = np.flatnonzero(in_rng)
    if not len(idx):
        raise ValueError("no bars inside the range window")
    g = day[idx]
    first = np.flatnonzero(np.diff(g, prepend=g[0] - 1) != 0)
    H = np.maximum.reduceat(m.h[idx], first)
    L = np.minimum.reduceat(m.l[idx], first)
    cnt = np.diff(np.append(first, len(idx)))
    last = idx[np.append(first[1:] - 1, len(idx) - 1)]
    D = g[first]
    px, spr = m.c[last], m.sp[last]
    rng = H - L
    ok = (cnt >= 0.5 * (e_min - s_min)) & (rng > 0) & (rng >= min_range_pct / 100.0 * px) & (rng <= max_range_pct / 100.0 * px)
    buy_ok = ok & (px + spr < H)                 # the ask has not reached the buy-stop level yet
    sell_ok = ok & (px > L)
    t_order = server_to_utc(D * DAY + e_min * 60)
    t_close = server_to_utc(D * DAY + c_min * 60)
    good = (t_order > 0) & (t_close > t_order)
    part = dict(dt=t_order[good], bstop=np.where(buy_ok, H, np.nan)[good], sstop=np.where(sell_ok, L, np.nan)[good])
    if stop == "factor":
        part.update(bsl=(H - stop_value * rng)[good], ssl=(L + stop_value * rng)[good])
    elif stop == "percent":
        part.update(slf=stop_value / 100.0)
    else:
        raise ValueError(stop)
    plan = X.merge_plans(m, [part, dict(dt=t_close[good], xl=True, xs=True)], orders=True)
    return X.Built(plan, plan, X.Sizing("risk", rf=risk_pct / 100.0, label=f"{risk_pct:g}% of balance at the stop"))


def atr_breakout(m: X.Market, period: int = 200, mult: float = 2.5, proximity: float = 0.25, tp_pct: float = 2.0,
                 sl_pct: float = 0.5, risk_pct: float = 0.5) -> X.Built:
    """
    ATR (Candle) Breakout (Four Edge module, live on gold since Mar 2026): at each new H1 candle, if the last closed
    candle's range is larger than ATR(``period``) x ``mult`` and it closed within ``proximity`` of its range from its
    extreme, trade in its direction (bullish: buy, bearish: sell) at the next candle's open; target ``tp_pct``% and
    stop ``sl_pct``% of the entry price; no time exit. Risk ``risk_pct``% of balance at the stop.
    ASSUMED: ATR is MetaTrader's (a simple average of the true range) and includes the signal candle; bullish / bearish
    = close above / below the open; one position at a time (a signal while a trade is open is not taken).
    """
    b = m.bars("H1")
    tr = X.true_range(b.h, b.l, b.c)
    atr = pd.Series(tr).rolling(period, min_periods=period).mean().to_numpy()
    rng = b.h - b.l
    big = np.isfinite(atr) & (rng > mult * atr)
    bull = (b.c > b.o) & ((b.h - b.c) <= proximity * rng)
    bear = (b.c < b.o) & ((b.c - b.l) <= proximity * rng)
    want = np.where(big & bull, 1, np.where(big & bear, -1, 0))
    keep = want != 0
    plan = X.make_plan(m, b.tc[keep], want=want[keep], slf=sl_pct / 100.0, tpr=tp_pct / sl_pct)
    return X.Built(plan, plan, X.Sizing("risk", rf=risk_pct / 100.0, label=f"{risk_pct:g}% of balance at the stop"))


# ASSUMED: his index entries are at the session start (01:05 server = 18:05 New York, five minutes after his broker's
# daily reopen). Exness's US index CFDs reopen at 18:00 New York in winter but at 18:30 in US summer time, so the
# entry is the first quote at or after his time, if one comes within this long.
SESSION_WAIT_S = 90 * 60


def _session_opens(m: X.Market, hm: tuple, weekdays_only: bool, wait_s: int = SESSION_WAIT_S):
    """(server day, UTC time) of the first M1 bar at or after the time ``hm`` of each server day, within ``wait_s``."""
    loc = server_clock(m)
    day = _days(loc)
    sec = loc % DAY
    t0 = (hm[0] * 60 + hm[1]) * 60
    ok = (sec >= t0) & (sec < t0 + wait_s)
    if weekdays_only:
        ok &= _weekday(day) <= 4
    idx = np.flatnonzero(ok)
    if not len(idx):
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    first = idx[np.flatnonzero(np.diff(day[idx], prepend=day[idx][0] - 1) != 0)]
    return day[first], m.t[first]


def _session_days(m: X.Market, hm: tuple, weekdays_only: bool) -> np.ndarray:
    return _session_opens(m, hm, weekdays_only)[0]


def go_long(m: X.Market, open_hm: tuple = (1, 5), close_hm: tuple = (22, 55), notional: float = 1.0,
            weekdays_only: bool = True) -> X.Built:
    """
    Go Long (Four Edge module, his index CFDs): every trading day a market buy at ``open_hm`` server time (on Exness
    data: the first quote at or after it, see ``SESSION_WAIT_S``), closed at ``close_hm`` the same day; no stop, no
    target. Position value ``notional`` x balance (his files: RiskPercent 100 with no stop = 100% of balance). One
    attempt a day.
    """
    days, t_open = _session_opens(m, open_hm, weekdays_only)
    t_close = server_to_utc(days * DAY + (close_hm[0] * 60 + close_hm[1]) * 60)
    plan = X.merge_plans(m, [dict(dt=t_open, want=1, expo=notional), dict(dt=t_close, xl=True)], live_s=X.LIVE_S)
    return X.Built(plan, plan, X.Sizing("expo", label=f"{notional * 100:.0f}% of balance in notional"))


def server_day_closes(m: X.Market):
    """Close of every server day (New York + 7 h) and the UTC time from which it is known (the day's last M1 close)."""
    loc = server_clock(m)
    day = _days(loc)
    last = np.flatnonzero(np.diff(day, append=day[-1] + 1) != 0)
    return day[last], m.c[last], m.t[last] + 60


def turnaround_tuesday(m: X.Market, sma: int, open_hm: tuple = (1, 5), close_hm: tuple = (22, 55),
                       notional: float = 0.5) -> X.Built:
    """
    Turnaround Tuesday (Four Edge module, his index CFDs): on Monday at ``open_hm`` server time, buy if the price is
    below the SMA(``sma``) of daily closes; close on Tuesday at ``close_hm``; no stop, no target; position value
    ``notional`` x balance (his files: RiskPercent 50 with no stop). One attempt a week.
    ASSUMED: daily bars are server days; the MA is MetaTrader's at shift 0 (the last ``sma`` - 1 closed days and the
    current price); the price compared is the first bid at or after the open time (the open of the bar it fills in).
    """
    days, opens = _session_opens(m, open_hm, True)
    mondays = days[_weekday(days) == 0]
    t_open = opens[_weekday(days) == 0]
    dday, dclose, _ = server_day_closes(m)
    want = np.zeros(len(mondays), np.int64)
    for i, (d, t) in enumerate(zip(mondays, t_open)):
        prior = dclose[dday < d]
        if len(prior) < sma - 1:
            continue
        j = int(np.searchsorted(m.t, t, side="left"))               # the bar the order fills in
        if j >= len(m):
            continue
        price = m.o[j]                                              # the first bid at or after the open time
        ma = (prior[-(sma - 1):].sum() + price) / sma
        want[i] = 1 if price < ma else 0
    t_close = server_to_utc((mondays + 1) * DAY + (close_hm[0] * 60 + close_hm[1]) * 60)
    plan = X.merge_plans(m, [dict(dt=t_open, want=want, expo=notional), dict(dt=t_close, xl=True)], live_s=X.LIVE_S)
    return X.Built(plan, plan, X.Sizing("expo", label=f"{notional * 100:.0f}% of balance in notional"))


def buy_hold(m: X.Market, notional: float = 1.0) -> X.Built:
    """A reference, not his: long ``notional`` x the balance from the start of every window to its end."""
    starts = sorted({store_s(w[0]) for w in INDEX_WINDOWS.values()} | {store_s(w[0]) for w in F.WINDOWS.values()})
    plan = X.make_plan(m, np.asarray(starts, np.int64), want=1, expo=notional)
    return X.Built(plan, plan, X.Sizing("expo", label=f"{notional * 100:.0f}% of balance in notional"))


def store_s(when: str) -> int:
    from ..data import store
    return int(store.to_ms(when) // 1000)


# his published settings (IC Trading server time, files of 10 Oct 2026), and the side tests outside his markets
ROWS += [
    Row("rb_xau", "Range Breakout (his gold settings)",
        lambda m: range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0), "risk-sized", ("XAUUSDm",),
        "Four Edge file RangeBreakout_XAUUSD_200005: range 03:05-06:05, delete/close 18:55, SL 1% of price, risk 1%"),
    Row("rb_xau", "Range Breakout (his gold settings)",
        lambda m: range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0), "standalone", ("XAUUSDm",)),
    Row("rb_btc", "Range Breakout (his BTC settings)",
        lambda m: range_breakout(m, (5, 0), (9, 0), (20, 0), "factor", 1.0, 1.0, weekdays_only=False), "risk-sized",
        ("BTCUSDm",), "Four Edge file RangeBreakout_BTCUSD_200007: range 05:00-09:00, delete/close 20:00, SL = opposite side, risk 1%, every day"),
    Row("rb_btc", "Range Breakout (his BTC settings)",
        lambda m: range_breakout(m, (5, 0), (9, 0), (20, 0), "factor", 1.0, 1.0, weekdays_only=False), "standalone",
        ("BTCUSDm",)),
    # every signal is traded, also while earlier trades are open (his hedging account): the signals here come to
    # about 140 a year on gold, his 2015-2026 test made 1,552 trades in about eleven years
    Row("atr", "ATR Breakout (his gold settings)", lambda m: atr_breakout(m), "risk-sized", ("XAUUSDm", "BTCUSDm"),
        "Four Edge file ATRBreakout_XAUUSD_400001: H1, ATR 200 x 2.5, close within 25%, TP 2%, SL 0.5%, risk 0.5% "
        "(he runs it on gold only)", multi=True),
    Row("atr", "ATR Breakout (his gold settings)", lambda m: atr_breakout(m), "standalone", ("XAUUSDm", "BTCUSDm"),
        multi=True),
    Row("atr", "ATR Breakout (his gold settings), one position at a time", lambda m: atr_breakout(m), "risk-sized",
        ("XAUUSDm",), "as above, but a signal that comes while a trade is open is not taken"),
    Row("rb_us30", "Range Breakout (his US30 settings)",
        lambda m: range_breakout(m, (11, 0), (13, 0), (18, 0), "factor", 1.0, 0.5), "risk-sized", ("US30m",),
        "Four Edge file RangeBreakout_US30_200004: range 11:00-13:00, delete/close 18:00, SL = opposite side, risk 0.5%"),
    Row("gl", "Go Long (his index settings)", lambda m: go_long(m), "risk-sized", ("US30m", "USTECm"),
        "Four Edge files GoLong_US30_100001 / GoLong_USTEC_100002: buy 01:05, close 22:55, no stop, 100% of balance"),
    Row("tt_us30", "Turnaround Tuesday (his US30 settings, SMA 25)", lambda m: turnaround_tuesday(m, 25), "risk-sized",
        ("US30m",), "Four Edge file TurnaroundTuesday_US30_300001: Monday 01:05 if below D1 SMA 25, close Tuesday 22:55, 50%"),
    Row("tt_ustec", "Turnaround Tuesday (his USTEC settings, SMA 9)", lambda m: turnaround_tuesday(m, 9), "risk-sized",
        ("USTECm",), "Four Edge file TurnaroundTuesday_USTEC_300002: Monday 01:05 if below D1 SMA 9, close Tuesday 22:55, 50%"),
    Row("bh", "Buy and hold the index (reference, not his)", lambda m: buy_hold(m), "risk-sized", ("US30m", "USTECm"),
        "long 100% of the balance in notional for the whole window, no swap"),
    # a cost scenario: BTC at a raw-account spread (his BTC test reportedly used 0.01 - 0.02% of price)
    Row("rb_btc", "Range Breakout (his BTC settings) at a 0.02% spread",
        lambda m: range_breakout(m, (5, 0), (9, 0), (20, 0), "factor", 1.0, 1.0, weekdays_only=False), "risk-sized",
        ("BTCUSDm",), "as above, every bar's spread set to 0.02% of the price", spread_pct=0.02),
    # outside his markets, on the bot's unit rule: what his index rules would do on gold and BTC
    Row("gl_side", "Go Long on gold / BTC (not his market)", lambda m: go_long(m, weekdays_only=m.symbol != "BTCUSDm"),
        "standalone", ("XAUUSDm", "BTCUSDm"), "his US-index times, the bot's unit rule"),
    Row("tt_side", "Turnaround Tuesday on gold / BTC, SMA 25 (not his market)", lambda m: turnaround_tuesday(m, 25),
        "standalone", ("XAUUSDm", "BTCUSDm"), "his US30 settings, the bot's unit rule"),
]


# ───────────────────────────── running ─────────────────────────────

def _plan_of(b: X.Built, variant: str):
    if variant == "risk-sized":
        if b.risk is None:
            raise ValueError("this strategy has no risk-sized plan")
        return b.risk, b.risk_sizing
    return b.plan, X.BOT


def with_spread(m: X.Market, spread_pct: float) -> X.Market:
    """A copy of the market whose every M1 bar has a spread of ``spread_pct``% of its close (a cost scenario)."""
    c = SpecMarket.__new__(SpecMarket)
    c.__dict__.update({k: v for k, v in m.__dict__.items() if k not in ("_bars", "_local", "sp")})
    c.sp = np.ascontiguousarray(m.c * spread_pct / 100.0)
    c._bars, c._local = {}, {}
    return c


# ───────────────────────────── several positions at once (a hedging account) ─────────────────────────────

@njit(cache=True)
def _multi_kernel(c, h, l, sp, k, eix, epx, xix, xpx, why, d, risk, expo, mode, rf, a_ix, z_ix, bnd, bal0, step_up,
                  unit_max):
    """
    ``external._account_kernel`` for trades that may overlap: each trade is sized from the balance (closed trades
    only, as MT5's balance) when it opens; the equity is marked at the close of every M1 bar for the running peak and
    at the bar's worst price for the trough (an exit bar as the single-position kernel marks it). Exits at a bar's
    open (a signal, a gap through the stop or target) are booked before anything opens on that bar, as the
    single-position kernel books a trade before it sizes the next. Trades are sorted by entry bar. mode 0: the bot's
    unit rule, 1: ``rf`` of the balance over the trade's risk distance, 2: the trade's exposure x the balance of
    notional; whole units of 0.01 lot, rounded down (zero size = skipped). A wipe-out books the balance as the loss,
    shared by the open trades in proportion to their worst marks.
    """
    nt = eix.shape[0]
    nb = bnd.shape[0]
    steps = np.zeros(nt)
    pnl = np.zeros(nt)
    eqb = np.full(nb, np.nan)
    opened = np.empty(nt, np.int64)
    bal = bal0
    peak = bal0
    maxdd = 0.0
    wiped = False
    wipe_ix = -1
    bi = 0
    nxt = 0
    n_open = 0
    eq_close = bal0
    for j in range(a_ix, z_ix):
        while bi < nb and bnd[bi] <= j:
            eqb[bi] = eq_close
            bi += 1
        # 1. exits at this bar's open
        if n_open > 0:
            before = bal
            m = 0
            booked = False
            for q in range(n_open):
                i = opened[q]
                if j == xix[i] and (why[i] == 1 or why[i] == 5 or why[i] == 6):
                    pnl[i] = steps[i] * k * d[i] * (xpx[i] - epx[i])
                    bal += pnl[i]
                    booked = True
                else:
                    opened[m] = i
                    m += 1
            if booked and bal <= 0.0:                   # wiped by exits at the open: they lose what was there
                tot = bal - before
                for q in range(nt):
                    if j == xix[q] and steps[q] > 0 and (why[q] == 1 or why[q] == 5 or why[q] == 6) and tot < 0.0:
                        pnl[q] = pnl[q] / tot * (-before)
                wiped = True
                wipe_ix = j
                bal = 0.0
                maxdd = 1.0
                n_open = 0
                eq_close = 0.0
                break
            n_open = m
            if booked and n_open == 0:
                if (peak - bal) / peak > maxdd:
                    maxdd = (peak - bal) / peak
                if bal > peak:
                    peak = bal
        # 2. entries at this bar's open, sized from the balance
        while nxt < nt and eix[nxt] <= j:
            i = nxt
            nxt += 1
            s = 0.0
            if mode == 0:
                s = min(math.floor(bal / step_up) + 1.0, unit_max)
            elif mode == 1:
                if risk[i] > 0:
                    s = math.floor(rf * bal / (risk[i] * k) + 1e-9)
            else:
                if expo[i] == expo[i] and expo[i] > 0:
                    s = math.floor(expo[i] * bal / (epx[i] * k) + 1e-9)
            if s > 0 and eix[i] == j:
                steps[i] = s
                opened[n_open] = i
                n_open += 1
        if n_open == 0:
            eq_close = bal
            continue
        # 3. the rest of the bar: stops, targets and the window's end inside it, the marks of the others
        uc_keep = 0.0
        uw = 0.0
        realized = 0.0
        keep = 0
        for q in range(n_open):
            i = opened[q]
            s = steps[i]
            if j == xix[i]:
                mw = xpx[i]
                if why[i] == 3 or why[i] == 4:
                    mw = l[j] if d[i] == 1 else h[j] + sp[j]
                uw += s * k * d[i] * (mw - epx[i])
                realized += s * k * d[i] * (xpx[i] - epx[i])
            else:
                mc = c[j] if d[i] == 1 else c[j] + sp[j]
                mw = l[j] if d[i] == 1 else h[j] + sp[j]
                uc_keep += s * k * d[i] * (mc - epx[i])
                uw += s * k * d[i] * (mw - epx[i])
                keep += 1
        if keep > 0 and bal + realized + uc_keep > peak:
            peak = bal + realized + uc_keep
        ew = bal + uw
        if ew <= 0.0:
            tot = 0.0
            for q in range(n_open):
                i = opened[q]
                mw = l[j] if d[i] == 1 else h[j] + sp[j]
                if j == xix[i] and not (why[i] == 3 or why[i] == 4):
                    mw = xpx[i]
                pnl[i] = steps[i] * k * d[i] * (mw - epx[i])
                tot += pnl[i]
            if tot < 0.0:
                for q in range(n_open):
                    i = opened[q]
                    pnl[i] = pnl[i] / tot * (-bal)
            wiped = True
            wipe_ix = j
            bal = 0.0
            maxdd = 1.0
            n_open = 0
            eq_close = 0.0
            break
        if (peak - ew) / peak > maxdd:
            maxdd = (peak - ew) / peak
        if keep < n_open:
            bal += realized
            m = 0
            for q in range(n_open):
                i = opened[q]
                if j == xix[i]:
                    pnl[i] = steps[i] * k * d[i] * (xpx[i] - epx[i])
                else:
                    opened[m] = i
                    m += 1
            n_open = m
        eq_close = bal + uc_keep
        if eq_close > peak:
            peak = eq_close
    while bi < nb:
        eqb[bi] = eq_close
        bi += 1
    return steps, pnl, bal, maxdd, wiped, wipe_ix, nxt, eqb


def every_signal(m: X.Market, plan: X.PathPlan, a_ix: int, z_ix: int) -> X.Path_:
    """The trades of ``plan`` when every signal is taken, also while earlier trades are open: the plan runs as lanes of
    one position each (``external.run_path``), and the signals a lane cannot take because its position is still open
    go to the next lane. A trade's own course does not depend on the others (fixed stop and target, no time exit)."""
    keep = (plan.dx >= a_ix) & (plan.dx < z_ix)
    rest = X.select(plan, keep)
    parts = []
    while len(rest):
        p = X.run_path(m, rest, a_ix, z_ix)
        if not len(p):
            break
        if not np.isin(p.eix, rest.dx).all():
            raise RuntimeError("a lane entered away from its signal's bar")
        parts.append(p)
        rest = X.select(rest, ~np.isin(rest.dx, p.eix))
    if not parts:
        return X.run_path(m, X.select(plan, np.zeros(len(plan), np.bool_)), a_ix, z_ix)
    if any(int(p.nleg.max()) > 1 for p in parts):
        raise ValueError("every_signal does not handle pyramids")
    for p in parts:
        if len(p.leix) != len(p) or not (p.leg0 == np.arange(len(p))).all():
            raise RuntimeError("unexpected leg layout")
    cat = {f: np.concatenate([getattr(p, f) for p in parts]) for f in X.Path_.__dataclass_fields__}
    order = np.argsort(cat["eix"], kind="stable")
    cat = {f: v[order] for f, v in cat.items()}
    cat["leg0"] = np.arange(len(order), dtype=cat["leg0"].dtype)
    return X.Path_(**cat)


def multi_account(m: X.Market, plan: X.PathPlan, sizing: X.Sizing, a_ix: int, z_ix: int):
    """``final10._bar_account`` for strategies whose every signal is its own trade (several positions at once)."""
    if sizing.brake or sizing.cap_lev:
        raise ValueError("multi_account: no brake or leverage cap")
    p = every_signal(m, plan, a_ix, z_ix)
    bnd = F._day_bounds(m, a_ix, z_ix)
    steps, pnl, bal, dd, wiped, wix, n_done, eqb = _multi_kernel(
        m.c, m.h, m.l, m.sp, m.k, p.eix, p.epx, p.xix, p.xpx, p.why, p.dir, p.risk, p.expo, X._MODE[sizing.mode],
        float(sizing.rf), int(a_ix), int(z_ix), np.asarray(bnd[1:-1], np.int64), X.ACCOUNT, X.STEP_UP,
        float(X.UNIT_MAX))
    done = np.arange(len(steps)) < n_done
    sel = np.flatnonzero(done & (steps > 0))
    res = X.Result(pnl[sel], p.dir[sel], p.eix[sel], p.xix[sel], int((done & (steps == 0)).sum()), float(bal),
                   float(dd), bool(wiped), int(m.t[wix]) if wiped else None,
                   np.concatenate([[X.ACCOUNT], eqb, [bal]]), orders=int(len(sel)))
    trades = pd.DataFrame()
    if len(sel):
        ts = lambda i: F._ts(m.t[min(i, len(m) - 1)])
        trades = pd.DataFrame({"open_time": [ts(i) for i in p.eix[sel]], "close_time": [ts(i) for i in p.xix[sel]],
                               "side": np.where(p.dir[sel] > 0, "BUY", "SELL"), "entry": p.epx[sel], "exit": p.xpx[sel],
                               "lots": steps[sel] * 0.01, "legs": p.nleg[sel],
                               "why": [X.WHY_NAMES.get(int(w), str(w)) for w in p.why[sel]], "pnl": pnl[sel]})
    daily = pd.Series(res.blocks[:-1], index=[F._ts(m.t[i]) if i < len(m) else F._ts(m.t[-1]) for i in bnd[:-1]])
    daily.iloc[0] = X.ACCOUNT
    return res, daily, trades


def _span_s(a: str, z: str) -> tuple:
    from ..data import store
    return store.to_ms(a) // 1000, store.to_ms(z) // 1000


ALL_SYMBOLS = ("XAUUSDm", "BTCUSDm", "US30m", "USTECm")
ACCOUNT_SMALL = 2000.0                       # this suite's account
ACCOUNT_LARGE = 10000.0                      # his sizing without the 0.01-lot minimum distorting it


def run(symbols: Sequence[str] = ALL_SYMBOLS, out: Path = OUT, log=print) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        runs, years, curves, trades = [], [], [], []
        try:
            m = load(sym)
        except FileNotFoundError as e:
            log(f"{sym}: skipped ({e})")
            continue
        log(f"{sym}: {len(m):,} M1 bars")
        built: Dict[str, X.Built] = {}
        wins = windows_for(sym)
        for row in [r for r in ROWS if sym in r.symbols]:
            key = (row.key, row.spread_pct)
            if key not in built:
                mk = m if row.spread_pct is None else with_spread(m, row.spread_pct)
                built[key] = (row.build(mk), mk)
            b, mk = built[key]
            plan, sizing = _plan_of(b, row.variant)
            # his own sizing also on a $10,000 account: on $2,000 the 0.01-lot minimum skips most of his trades at
            # today's prices (his live accounts hold 5,000 and 50,000 EUR)
            accounts = (ACCOUNT_SMALL,) if row.variant == "standalone" else (ACCOUNT_SMALL, ACCOUNT_LARGE)
            for acct in accounts:
                label = row.name + (" (bot unit rule)" if row.variant == "standalone" else
                                    f" (his sizing: {sizing.label}, ${acct:,.0f} account)")
                for w, (wa, wz) in wins.items():
                    a_s, z_s = _span_s(wa, wz)
                    a_ix, z_ix = int(np.searchsorted(m.t, a_s)), int(np.searchsorted(m.t, z_s))
                    saved = X.ACCOUNT
                    X.ACCOUNT = float(acct)
                    try:
                        if row.multi:
                            res, daily, tr = multi_account(mk, plan, sizing, a_ix, z_ix)
                        else:
                            res, daily, tr = F._bar_account(X, mk, plan, sizing, a_ix, z_ix)
                    finally:
                        X.ACCOUNT = saved
                    k = ACCOUNT_SMALL / acct                     # the metrics are computed per $2,000, then scaled back
                    met = F.account_metrics(daily * k, res.final * k, res.max_dd * 100.0, a_s, z_s, res.trades_pnl * k,
                                            res.wiped, pd.Timestamp(res.wipe_t, unit="s", tz="UTC") if res.wiped else None)
                    for col in ("final_equity", "net", "avg_trade", "worst_trade", "best_trade"):
                        if pd.notna(met.get(col)):
                            met[col] = round(met[col] / k, 2)
                    met.update(skipped_trades=int(res.skipped), account=acct)
                    ident = dict(symbol=sym, label=label, key=row.key, variant=row.variant, window=w, start=wa, end=wz,
                                 spread_pct=row.spread_pct, multi=row.multi, strategy=row.name,
                                 sizing="bot unit rule" if row.variant == "standalone" else f"his sizing, ${acct:,.0f}")
                    runs.append({**ident, **met})
                    if w == ("since 2020" if sym in INDEX_SPECS else "8y"):     # the years of the longest account
                        for y in F.yearly(daily * k, res.final * k, a_s, z_s):
                            for col in ("start_equity", "end_equity", "pnl"):
                                y[col] = round(y[col] / k, 2)
                            years.append({**ident, **y, "account": acct})
                    curves.append(pd.DataFrame({"symbol": sym, "label": label, "window": w, "time": daily.index,
                                                "equity": daily.to_numpy()}))
                    if len(tr):
                        trades.append(tr.assign(symbol=sym, label=label, window=w))
                    log(f"  {sym} {label:90s} {w:10s} final {res.final:10.2f}  DD {res.max_dd * 100:5.1f}%  "
                        f"trades {len(res.trades_pnl):5d}" + (f"  skipped {res.skipped}" if res.skipped else ""))
        pd.DataFrame(runs).to_csv(out / f"runs_{sym}.csv", index=False)
        pd.DataFrame(years).to_csv(out / f"years_{sym}.csv", index=False)
        pd.concat(curves, ignore_index=True).to_csv(out / f"equity_{sym}.csv.gz", index=False)
        if trades:
            pd.concat(trades, ignore_index=True).to_csv(out / f"trades_{sym}.csv.gz", index=False)


# ───────────────────────────── the write-up ─────────────────────────────

WINDOW_NAMES = {**F.WINDOW_NAMES, "since 2020": "Jul 2020 - Nov 2026"}
WINDOW_SHORT = {"8y": "8 years", "5y": "5 years", "new": "Nov 2018 - Dec 2020", "1y": "last year",
                "since 2020": "Jul 2020 - Nov 2026"}
MAIN_WINDOW = {"XAUUSDm": "8y", "BTCUSDm": "8y", "US30m": "since 2020", "USTECm": "since 2020"}
MARKET = {"XAUUSDm": "Gold (XAUUSDm)", "BTCUSDm": "BTC (BTCUSDm)", "US30m": "Dow Jones 30 (US30m)",
          "USTECm": "Nasdaq 100 (USTECm)"}
SIZING_ORDER = {"his sizing, $10,000": 0, "his sizing, $2,000": 1, "bot unit rule": 2}
# the final ten's leaders on the same windows (fresh $2,000 accounts, backtest_results/final10/results.csv)
BENCH = {"XAUUSDm": ("V3-lite", "Top 2"), "BTCUSDm": ("Turtle + bot votes", "Turtle, 1% risk", "Top 2")}
BENCH_NOTE = {"V3-lite": "our gold leader, as the bot runs it", "Top 2": "our lowest-drawdown design",
              "Turtle + bot votes": "the final ten's BTC leader on the bot's unit rule",
              "Turtle, 1% risk": "the Turtle sized by risk, like his"}
# his Four Edge instances this study can run (8 of his 14), each on its own $10,000 account with his sizing
PORTFOLIO = (("XAUUSDm", "Range Breakout (his gold settings)"), ("XAUUSDm", "ATR Breakout (his gold settings)"),
             ("BTCUSDm", "Range Breakout (his BTC settings)"), ("US30m", "Range Breakout (his US30 settings)"),
             ("US30m", "Go Long (his index settings)"), ("USTECm", "Go Long (his index settings)"),
             ("US30m", "Turnaround Tuesday (his US30 settings, SMA 25)"),
             ("USTECm", "Turnaround Tuesday (his USTEC settings, SMA 9)"))
PORTFOLIO_WINDOWS = ("since 2020", "5y", "1y")


def load_runs(out: Path = OUT) -> pd.DataFrame:
    d = pd.concat([pd.read_csv(p) for p in sorted(Path(out).glob("runs_*.csv"))], ignore_index=True)
    d["bench"] = False
    order = {}
    for r in ROWS:
        order.setdefault(r.name, len(order))
    d["_ord"] = d["strategy"].map(order).fillna(99) * 10 + d["sizing"].map(SIZING_ORDER).fillna(9)
    return d


def benchmarks() -> pd.DataFrame:
    f = F.OUT / "results.csv"
    if not f.exists():
        return pd.DataFrame()
    b = pd.read_csv(f)
    b = b[~b["group"].isin(["supplement", "warm"])]
    keep = pd.concat([b[(b["symbol"] == s) & b["name"].isin(n)] for s, n in BENCH.items()])
    keep = keep.assign(strategy=keep["name"], bench=True, account=2000.0,
                       sizing=np.where(keep["name"].str.contains("1% risk"), "1% risk, $2,000", "bot unit rule"),
                       _ord=1000 + keep["name"].map({n: i for s in BENCH.values() for i, n in enumerate(s)}))
    return keep


NOT_HIS = {("BTCUSDm", "ATR Breakout (his gold settings)")}       # his rules on a market he does not trade them on


def display_name(symbol: str, strategy: str) -> str:
    if (symbol, strategy) not in NOT_HIS:
        return strategy
    return strategy[:-1] + ", not his market)" if strategy.endswith(")") else strategy + " (not his market)"


def _row_name(r) -> str:
    if r["bench"]:
        return f"*{r['strategy']}* (final ten: {BENCH_NOTE.get(r['strategy'], '')})"
    return display_name(r["symbol"], r["strategy"])


def _growth(r, w: str) -> float:
    return r["cagr_pct"] if w != "1y" else r["return_pct"]


def _ratio(g: float, dd: float) -> str:
    return f"{g / max(dd, 0.01):.2f}".replace("-", "−")


SYMBOL_ORDER = {s: i for i, s in enumerate(("XAUUSDm", "BTCUSDm", "US30m", "USTECm"))}


def _notes(r) -> str:
    notes = []
    if r.get("wiped") is True or r.get("wiped") == "True":
        notes.append(f"wiped {r['wiped_at']}")
    elif r["final_equity"] < 50:
        notes.append("account destroyed")
    sk = r.get("skipped_trades", 0)
    if pd.notna(sk) and sk > 0:
        n_sig = int(sk + r["trades"])
        notes.append(("barely traded: " if sk > r["trades"] else "") + f"{int(sk):,} of {n_sig:,} trades too small for 0.01 lot")
    return "; ".join(notes)


def main_table(d: pd.DataFrame, symbol: str, window: str, sizings: Optional[Sequence[str]] = None) -> str:
    t = d[(d["symbol"] == symbol) & (d["window"] == window)]
    if sizings is not None:
        t = t[t["sizing"].isin(sizings) | t["bench"]]
    t = t.sort_values("_ord")
    g = "Growth / year" if window != "1y" else "Return"
    head = ["Strategy", "Sizing", "Final equity", g, "Max DD", "÷ DD", "Trades", "Win rate", "Profit factor",
            "Losing months", "Notes"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, r in t.iterrows():
        gr = _growth(r, window)
        lines.append("| " + " | ".join([
            _row_name(r), r["sizing"], F._usd0(r["final_equity"]), F._pct(gr, True), F._pct(r["max_dd_pct"]),
            _ratio(gr, r["max_dd_pct"]), f"{int(r['trades']):,}", F._pct(r["win_rate_pct"]),
            "n/a" if pd.isna(r["profit_factor"]) else f"{r['profit_factor']:.2f}",
            f"{int(r['losing_months'])} of {int(r['months'])}", _notes(r)]) + " |")
    return "\n".join(lines)


def windows_table(d: pd.DataFrame, symbol: str, sizings: Optional[Sequence[str]] = None) -> str:
    wins = [w for w in windows_for(symbol)]
    t = d[d["symbol"] == symbol]
    if sizings is not None:
        t = t[t["sizing"].isin(sizings) | t["bench"]]
    keys = t.drop_duplicates(["strategy", "sizing"]).sort_values("_ord")[["symbol", "strategy", "sizing", "bench"]]
    head = ["Strategy", "Sizing"] + [WINDOW_SHORT[w] for w in wins]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, k in keys.iterrows():
        cells = []
        for w in wins:
            x = t[(t["strategy"] == k["strategy"]) & (t["sizing"] == k["sizing"]) & (t["window"] == w)]
            if x.empty:
                cells.append("–")
                continue
            r = x.iloc[0]
            gr = _growth(r, w)
            flag = " ⚠" if pd.notna(r.get("skipped_trades")) and r["skipped_trades"] > r["trades"] else ""
            cells.append(f"{F._pct(gr, True)}{'/yr' if w != '1y' else ''} · DD {F._pct(r['max_dd_pct'])}{flag}")
        lines.append("| " + " | ".join([_row_name(k), k["sizing"]] + cells) + " |")
    return "\n".join(lines)


def years_frame(out: Path = OUT, sizings: Sequence[str] = ("his sizing, $10,000",)) -> pd.DataFrame:
    y = pd.concat([pd.read_csv(p) for p in sorted(Path(out).glob("years_*.csv")) if p.stat().st_size > 2],
                  ignore_index=True)
    y = y[y["sizing"].isin(sizings)]
    y.loc[y["start_equity"] < 0.025 * y["account"], "return_pct"] = np.nan      # destroyed (under $50 per $2,000)
    y["row"] = [display_name(sy, st) for sy, st in zip(y["symbol"], y["strategy"])]
    y["row"] = y["row"] + " · " + y["symbol"].str.replace("m$", "", regex=True) + " · " + y["sizing"]
    y["_so"] = y["symbol"].map(SYMBOL_ORDER)
    return y.sort_values("_so", kind="stable")


def years_md(out: Path, symbols: Sequence[str], sizings: Sequence[str]) -> str:
    y = years_frame(out, sizings)
    y = y[y["symbol"].isin(symbols)]
    if y.empty:
        return "*(no runs yet)*"
    piv = y.pivot_table(index="row", columns="year", values="return_pct", aggfunc="first", dropna=False)
    order = {}
    for _, r in y.iterrows():
        order.setdefault(r["row"], len(order))
    piv = piv.loc[sorted(piv.index, key=lambda i: order[i])]
    cols = list(piv.columns)
    names = [f"{c} (from 13 Nov)" if c == 2018 else f"{c} (to 13 Nov)" if c == 2026 else str(c) for c in cols]
    lines = ["| Strategy · market · sizing | " + " | ".join(names) + " |", "|" + "---|" * (len(cols) + 1)]
    for row, vals in piv.iterrows():
        lines.append(f"| {row} | " + " | ".join("–" if pd.isna(v) else F._pct(v, True) for v in vals) + " |")
    return "\n".join(lines)


def load_curves(out: Path = OUT) -> pd.DataFrame:
    return pd.concat([pd.read_csv(p, parse_dates=["time"]) for p in sorted(Path(out).glob("equity_*.csv.gz"))],
                     ignore_index=True)


def _curve(curves: pd.DataFrame, d: pd.DataFrame, symbol: str, strategy: str, sizing: str, window: str) -> pd.Series:
    """Daily equity of one account (the start of every UTC day) with its final equity at the window's end."""
    lab = d[(d["symbol"] == symbol) & (d["strategy"] == strategy) & (d["sizing"] == sizing) & (d["window"] == window)
            & d["spread_pct"].isna()]
    if lab.empty:
        return pd.Series(dtype=float)
    r = lab.iloc[0]
    c = curves[(curves["symbol"] == symbol) & (curves["label"] == r["label"]) & (curves["window"] == window)]
    s = pd.Series(c["equity"].to_numpy(), index=pd.DatetimeIndex(c["time"]).tz_convert("UTC").normalize())
    s = s[~s.index.duplicated(keep="first")]
    end = pd.Timestamp(r["end"], tz="UTC")
    return pd.concat([s, pd.Series([r["final_equity"]], index=[end])])


def portfolio(d: pd.DataFrame, curves: pd.DataFrame, window: str, sizing: str = "his sizing, $10,000"):
    """His instances on one account, approximately: every instance's daily return on its own account (his sizing,
    which scales each trade with the balance) added up day by day and compounded. Marked once a day, so its
    drawdown is a lower bound of the intraday one."""
    rets, used = [], []
    for sym, strat in PORTFOLIO:
        s = _curve(curves, d, sym, strat, sizing, window)
        if len(s) < 2:
            continue
        rets.append(s.pct_change().fillna(0.0).rename(f"{strat} · {sym}"))
        used.append((sym, strat))
    if not rets:
        return None
    R = pd.concat(rets, axis=1).fillna(0.0).sort_index()
    rp = R.sum(axis=1)
    eq = ACCOUNT_LARGE * (1.0 + rp).cumprod()
    a, z = windows_for("US30m").get(window, F.WINDOWS.get(window))
    years = (pd.Timestamp(z) - pd.Timestamp(a)).total_seconds() / F.YEAR_S
    dd = float((1.0 - eq / eq.cummax()).max() * 100.0)
    final = float(eq.iloc[-1])
    ret = (final / ACCOUNT_LARGE - 1.0) * 100.0
    cagr = ((final / ACCOUNT_LARGE) ** (1.0 / years) - 1.0) * 100.0 if final > 0 else -100.0
    contrib = {c: float((ACCOUNT_LARGE * (1.0 + R[c]).cumprod()).iloc[-1]) for c in R.columns}
    corr = R.corr()
    return dict(window=window, used=used, equity=eq, final=final, return_pct=ret, cagr_pct=cagr, max_dd_pct=dd,
                contrib=contrib, R=R, corr=corr)


def live_weeks(d: pd.DataFrame, curves: pd.DataFrame, start: str = "2026-06-30") -> str:
    """The instances over the weeks of his Four Edge-only live account (from ``start`` to the data's end), each on its
    own account and all together (daily returns added up), as text."""
    p = portfolio(d, curves, "1y")
    if p is None or len(p["used"]) != len(PORTFOLIO):
        raise KeyError("live weeks: the portfolio lacks instances")
    R = p["R"]
    w = R[R.index >= pd.Timestamp(start, tz="UTC")]
    tot = (float((1.0 + w.sum(axis=1)).prod()) - 1.0) * 100.0
    short = {"Range Breakout (his gold settings)": "Range Breakout", "ATR Breakout (his gold settings)": "ATR Breakout",
             "Range Breakout (his BTC settings)": "Range Breakout", "Range Breakout (his US30 settings)": "Range Breakout",
             "Go Long (his index settings)": "Go Long", "Turnaround Tuesday (his US30 settings, SMA 25)": "Turnaround Tuesday",
             "Turnaround Tuesday (his USTEC settings, SMA 9)": "Turnaround Tuesday"}
    by = {}
    for col in w.columns:
        strat, sym = col.split(" · ")
        by.setdefault(sym, []).append(f"{short.get(strat, strat)} {F._pct((float((1.0 + w[col]).prod()) - 1.0) * 100.0, True)}")
    names = {"XAUUSDm": "gold", "BTCUSDm": "BTC", "US30m": "US30", "USTECm": "USTEC"}
    return (f"{F._pct(tot, True)} for the 8 together; " + "; ".join(f"{names[s]}: {', '.join(v)}" for s, v in by.items()))


def portfolio_md(d: pd.DataFrame, curves: pd.DataFrame) -> str:
    rows = [p for p in (portfolio(d, curves, w) for w in PORTFOLIO_WINDOWS) if p is not None]
    if not rows:
        return "*(the index runs are missing)*"
    head = ["Window", "Instances", "Final (per $10,000)", "Growth / year", "Return", "Max DD (daily marks)",
            "Growth ÷ DD"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for p in rows:
        g = p["cagr_pct"] if p["window"] != "1y" else p["return_pct"]
        lines.append("| " + " | ".join([WINDOW_SHORT[p["window"]], str(len(p["used"])), F._usd0(p["final"]),
                                        F._pct(p["cagr_pct"], True) if p["window"] != "1y" else "–",
                                        F._pct(p["return_pct"], True), F._pct(p["max_dd_pct"]),
                                        _ratio(g, p["max_dd_pct"])]) + " |")
    first = rows[0]
    eq = first["equity"]                       # equity at the start of every day, the final at the window's end
    years_ = sorted(set(eq.index.year))
    by_year = []
    for y in years_:
        start = ACCOUNT_LARGE if y == years_[0] else float(eq[eq.index.year == y].iloc[0])
        later = eq[eq.index.year > y]
        end = float(later.iloc[0]) if len(later) else first["final"]
        by_year.append((y, (end / start - 1.0) * 100.0))
    lines += ["", f"The {WINDOW_SHORT[first['window']]} portfolio by calendar year (2020 from 1 Jul, 2026 to 13 Nov): "
              + ", ".join(f"{y} {F._pct(r, True)}" for y, r in by_year) + "."]
    lines += ["", f"Each instance alone over {WINDOW_SHORT[first['window']]} (its own $10,000 account, his sizing; "
              "daily marks):", "", "| Instance | Final | Growth / year |", "|---|---|---|"]
    yrs = (pd.Timestamp(INDEX_WINDOWS[first["window"]][1]) - pd.Timestamp(INDEX_WINDOWS[first["window"]][0])
           ).total_seconds() / F.YEAR_S if first["window"] in INDEX_WINDOWS else 1.0
    for c, v in first["contrib"].items():
        lines.append(f"| {c} | {F._usd0(v)} | {F._pct(((v / ACCOUNT_LARGE) ** (1 / yrs) - 1) * 100, True)} |")
    return "\n".join(lines)


def _bench_series(bench: pd.DataFrame, symbol: str, name: str, window: str) -> pd.Series:
    c = bench[(bench["symbol"] == symbol) & (bench["name"] == name) & (bench["window"] == window)]
    s = pd.Series(c["equity"].to_numpy(), index=pd.DatetimeIndex(c["time"]).tz_convert("UTC").normalize())
    return s[~s.index.duplicated(keep="first")]


def per_unit(trades: pd.DataFrame, start: float = ACCOUNT_SMALL) -> pd.DataFrame:
    """One strategy's closed trades (one position or basket at a time) as P&L per unit of the bot's unit rule. The
    units each trade had are re-derived from its own account's closed balance: min(balance // 2,500 + 1, 10)."""
    t = trades.sort_values("open_time").reset_index(drop=True)
    bal, ppu = start, []
    for r in t.itertuples():
        u = min(int(bal // X.STEP_UP) + 1, X.UNIT_MAX)
        ppu.append(r.pnl / u)
        bal += r.pnl
    return t.assign(ppu=ppu)


def replay_units(streams: Sequence[pd.DataFrame], split: int, start: float = ACCOUNT_SMALL) -> Tuple[float, float]:
    """Closed trades of several strategies on one account with the bot's unit rule: each trade gets
    min((balance / split) // 2,500 + 1, 10) units from the closed balance when it opens (``split`` = 2: the account is
    shared out half and half), and units x its P&L per unit when it closes. Returns the final balance and the max
    drawdown of the closed balance, in %."""
    ev = []
    for si, t in enumerate(streams):
        for r in t.itertuples():
            ev.append((r.open_time, 1, si, r.Index))
            ev.append((r.close_time, 0, si, r.Index))
    ev.sort(key=lambda e: (e[0], e[1]))                     # at the same instant a close comes before an open
    bal, peak, mdd, units = start, start, 0.0, {}
    for _, kind, si, ix in ev:
        if kind == 1:
            units[(si, ix)] = min(int(bal / split // X.STEP_UP) + 1, X.UNIT_MAX)
        else:
            bal += units.pop((si, ix)) * streams[si].at[ix, "ppu"]
            peak = max(peak, bal)
            mdd = max(mdd, (peak - bal) / peak)
    return bal, mdd * 100.0


def _times(t: pd.DataFrame) -> pd.DataFrame:
    for col in ("open_time", "close_time"):
        t[col] = pd.to_datetime(t[col], utc=True)
    return t


def _bench_trades(symbol: str, name: str, window: str) -> pd.DataFrame:
    files = sorted(F.OUT.glob(f"trades_{symbol}_*.csv.gz"))
    t = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    return _times(t[(t["label"] == name) & (t["window"] == window)].copy())


def combo(d: pd.DataFrame, curves: pd.DataFrame, window: str, partner: str = "V3-lite",
          strategy: str = "Range Breakout (his gold settings)", symbol: str = "XAUUSDm") -> Optional[dict]:
    """His gold Range Breakout next to one of our designs, both on the bot's unit rule ($2,000): the correlation of
    their daily and monthly returns (from the daily equity), and the two on one account, replayed trade by trade
    with the unit rule on their closed trades: half the account each (units from half the balance) or both at full
    size. Each alone is replayed the same way, so the four accounts are measured alike (drawdown of the closed
    balance)."""
    rb = _curve(curves, d, symbol, strategy, "bot unit rule", window)
    ours = _bench_series(_bench_curves(), symbol, partner, window)
    if len(rb) < 2 or len(ours) < 2:
        return None
    R = pd.concat([rb.pct_change(), ours.pct_change()], axis=1, keys=["his", "ours"]).fillna(0.0).sort_index()
    M = (1.0 + R).groupby(R.index.tz_localize(None).to_period("M")).prod() - 1.0
    lab = d[(d["symbol"] == symbol) & (d["strategy"] == strategy) & (d["sizing"] == "bot unit rule")
            & (d["window"] == window) & d["spread_pct"].isna()]["label"].iloc[0]
    tr = pd.read_csv(OUT / f"trades_{symbol}.csv.gz")
    his = per_unit(_times(tr[(tr["label"] == lab) & (tr["window"] == window)].copy()))
    our = per_unit(_bench_trades(symbol, partner, window))
    return dict(window=window, corr_d=float(R["his"].corr(R["ours"])), corr_m=float(M["his"].corr(M["ours"])),
                his=replay_units([his], 1), ours=replay_units([our], 1), half=replay_units([his, our], 2),
                both=replay_units([his, our], 1), n_ours=len(our))


def combo_md(d: pd.DataFrame, curves: pd.DataFrame, partner: str = "V3-lite") -> str:
    head = ["Window", "Correlation of daily / monthly returns", "His Range Breakout alone", f"{partner} alone",
            "Half the account each", "Both at full size, one account"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for w in ("8y", "5y", "new", "1y"):
        c = combo(d, curves, w, partner)
        if c is None:
            continue
        f = lambda x: f"{F._usd0(x[0])}, DD {F._pct(x[1])}"
        lines.append("| " + " | ".join([WINDOW_SHORT[w], f"{c['corr_d']:.2f} / {c['corr_m']:.2f}".replace("-", "−"),
                                        f(c["his"]), f(c["ours"]), f(c["half"]), f(c["both"])]) + " |")
    return "\n".join(lines)


def spread_by_year(symbol: str = "BTCUSDm") -> pd.Series:
    from ..data import store
    m1 = store.load_m1(symbol, F.HISTORY_FROM.get(symbol, INDEX_HISTORY_FROM), F.DATA_END)
    t = pd.to_datetime(m1["t"], unit="s", utc=True)
    s = pd.Series(np.asarray(m1["spread_mean"]) / np.asarray(m1["c"]) * 100.0, index=t)
    return s.groupby(s.index.year).median()


def spread_md(symbols: Sequence[str] = ("BTCUSDm",)) -> str:
    """Median spread per year, as a % of the price, one row per symbol."""
    rows = {sym: spread_by_year(sym) for sym in symbols}
    years = sorted({y for s in rows.values() for y in s.index})
    out = ["| Year | " + " | ".join(str(y) for y in years) + " |", "|" + "---|" * (len(years) + 1)]
    for sym, s in rows.items():
        name = {"BTCUSDm": "BTC", "US30m": "US30", "USTECm": "USTEC"}.get(sym, sym)
        out.append(f"| Median {name} spread, % of price | "
                   + " | ".join(f"{s[y]:.3f}%" if y in s.index else "–" for y in years) + " |")
    return "\n".join(out)


def value(d: pd.DataFrame, spec: str) -> str:
    """``SYMBOL|STRATEGY|SIZING|WINDOW|COLUMN[|spread]``: one figure of the runs, formatted for the text."""
    sym, strat, sizing, window, col, *rest = spec.split("|")
    t = d[(d["symbol"] == sym) & (d["strategy"] == strat) & (d["sizing"] == sizing) & (d["window"] == window)]
    t = t[t["spread_pct"].notna()] if rest and rest[0] == "spread" else t[t["spread_pct"].isna()]
    if len(t) != 1:
        raise KeyError(f"{spec}: {len(t)} rows")
    v = t.iloc[0][col]
    if col in ("final_equity", "net", "avg_trade", "worst_trade", "best_trade"):
        return F._usd0(v)
    if col in ("cagr_pct", "return_pct"):
        return F._pct(v, True)
    if col in ("max_dd_pct", "win_rate_pct"):
        return F._pct(v)
    if col == "profit_factor":
        return f"{v:.2f}"
    if col in ("trades", "skipped_trades", "months", "losing_months"):
        return f"{int(v):,}"
    if col == "trades_per_year":
        return f"{v:.0f}"
    return str(v)


def trade_stats(out: Path, d: pd.DataFrame, spec: str) -> str:
    """``SYMBOL|STRATEGY|SIZING|WINDOW|FROM|TO[|close]``: the trades of one account opened (or closed) in
    [FROM, TO), as text."""
    sym, strat, sizing, window, a, z, *by = spec.split("|")
    col = "close_time" if by and by[0] == "close" else "open_time"
    lab = d[(d["symbol"] == sym) & (d["strategy"] == strat) & (d["sizing"] == sizing) & (d["window"] == window)
            & d["spread_pct"].isna()]["label"]
    if len(lab) != 1:
        raise KeyError(spec)
    tr = pd.read_csv(Path(out) / f"trades_{sym}.csv.gz", parse_dates=["open_time", "close_time"])
    tr = tr[(tr["label"] == lab.iloc[0]) & (tr["window"] == window)]
    tr = tr[(tr[col] >= pd.Timestamp(a, tz="UTC")) & (tr[col] < pd.Timestamp(z, tz="UTC"))]
    won, lost = tr[tr["pnl"] > 0], tr[tr["pnl"] < 0]
    pf = won["pnl"].sum() / -lost["pnl"].sum() if len(lost) else float("nan")
    return (f"{len(tr)} trades, {len(won)} won ({F._pct(len(won) / max(len(tr), 1) * 100)}), "
            f"profit factor {pf:.2f}")


def atr_overlap(out: Path, d: pd.DataFrame, window: str = "8y") -> str:
    """The ATR trades a one-position account cannot take (signals while a trade is open) against the ones it takes,
    in multiples of the risk (the 0.5% stop), from the two trade lists of the $10,000 accounts."""
    tr = pd.read_csv(Path(out) / "trades_XAUUSDm.csv.gz", parse_dates=["open_time"])
    lab = lambda s: d[(d["symbol"] == "XAUUSDm") & (d["strategy"] == s) & (d["sizing"] == "his sizing, $10,000")
                      & (d["window"] == window)]["label"].iloc[0]
    every = tr[(tr["label"] == lab("ATR Breakout (his gold settings)")) & (tr["window"] == window)]
    one = tr[(tr["label"] == lab("ATR Breakout (his gold settings), one position at a time")) & (tr["window"] == window)]
    r = np.where(every["side"] == "BUY", 1.0, -1.0) * (every["exit"] - every["entry"]) / (0.005 * every["entry"])
    first = every["open_time"].isin(set(one["open_time"])).to_numpy()
    pf = lambda x: x[x > 0].sum() / -x[x < 0].sum()
    return (f"profit factor {pf(r[~first]):.2f} in multiples of the risk, {np.mean(r[~first]):+.2f} R a trade, "
            f"against {pf(r[first]):.2f} and {np.mean(r[first]):+.2f} R for the {int(first.sum())} it takes")


def bench_value(spec: str) -> str:
    """``SYMBOL|NAME|WINDOW|COLUMN`` from the final ten's results."""
    sym, name, window, col = spec.split("|")
    b = benchmarks()
    t = b[(b["symbol"] == sym) & (b["name"] == name) & (b["window"] == window)]
    if len(t) != 1:
        raise KeyError(spec)
    v = t.iloc[0][col]
    return F._usd0(v) if col == "final_equity" else F._pct(v, col in ("cagr_pct", "return_pct")) \
        if col.endswith("_pct") else f"{v:.2f}" if col == "profit_factor" else str(v)


def fill(template: str, out: Path, d: pd.DataFrame, curves: pd.DataFrame) -> str:
    """Replace ``{{main:SYMBOL:WINDOW[:SIZING+...]}}``, ``{{windows:SYMBOL[:SIZING+...]}}``,
    ``{{years:SYMBOL,...:SIZING+...}}``, ``{{combo[:PARTNER]}}``, ``{{c:WINDOW:PARTNER:KEY}}``, ``{{portfolio}}``, ``{{spread}}``, ``{{v:SPEC}}``, ``{{b:SPEC}}`` and
    ``{{p:WINDOW:COLUMN}}`` in the write-up."""
    import re
    ports = {}

    def sub(mt):
        kind, _, rest = mt.group(1).partition(":")
        if kind == "v":
            return value(d, rest)
        if kind == "b":
            return bench_value(rest)
        if kind == "p":
            w, col = rest.split(":")
            if w not in ports:
                ports[w] = portfolio(d, curves, w)
            p = ports[w]
            if p is None or len(p["used"]) != len(PORTFOLIO):
                raise KeyError(f"{mt.group(0)}: the portfolio lacks instances "
                               f"({0 if p is None else len(p['used'])} of {len(PORTFOLIO)})")
            return F._usd0(p[col]) if col == "final" else F._pct(p[col], col != "max_dd_pct")
        if kind == "main":
            sym, w, *sz = rest.split(":")
            return main_table(d, sym, w, sz[0].split("+") if sz else None)
        if kind == "windows":
            sym, *sz = rest.split(":")
            return windows_table(d, sym, sz[0].split("+") if sz else None)
        if kind == "years":
            syms, sz = rest.split(":")
            return years_md(out, syms.split(","), sz.split("+"))
        if kind == "portfolio":
            return portfolio_md(d, curves)
        if kind == "t":
            return trade_stats(out, d, rest)
        if kind == "atroverlap":
            return atr_overlap(out, d)
        if kind == "liveweeks":
            return live_weeks(d, curves)
        if kind == "combo":
            return combo_md(d, curves, rest or "V3-lite")
        if kind == "c":
            w, partner, key = rest.split(":")
            cb = combo(d, curves, w, partner)
            if key.startswith("corr"):
                return f"{cb[key]:.2f}".replace("-", "−")
            what, col = key.split(".")
            return F._usd0(cb[what][0]) if col == "final" else F._pct(cb[what][1])
        if kind == "spread":
            return spread_md(rest.split(",") if rest else ("BTCUSDm",))
        raise KeyError(mt.group(0))
    return re.sub(r"\{\{([^}]+)\}\}", sub, template)


# charts -------------------------------------------------------------------------------------------------------------

def _bench_curves() -> pd.DataFrame:
    files = sorted(F.OUT.glob("equity_*_*.csv.gz"))
    if not files:
        return pd.DataFrame()
    c = pd.concat([pd.read_csv(p, parse_dates=["time"]) for p in files], ignore_index=True)
    c["name"] = c["label"].map(F.display)
    return c


def _spread_labels(ys_px: List[float], height_px: float, gap: float = 15.0) -> List[float]:
    """Vertical pixel positions for end-of-line labels: as close to their lines as possible, ``gap`` apart."""
    order = np.argsort(ys_px)
    pos = np.asarray(ys_px, float)[order].copy()
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + gap)
    if len(pos) and pos[-1] > height_px - gap / 2:
        pos[-1] = height_px - gap / 2
        for i in range(len(pos) - 2, -1, -1):
            pos[i] = min(pos[i], pos[i + 1] - gap)
    out = np.empty(len(pos))
    out[order] = pos
    return out.tolist()


def figure_equity(d: pd.DataFrame, curves: pd.DataFrame, symbol: str, panels: Sequence[tuple], window: str):
    """One panel per account kind, each line one strategy; a line keeps its colour in both panels. ``panels``:
    (title, [(strategy, sizing, spread?, colour index, short name), ...]); lines end in their names."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from ..viz import theme as T
    bench = _bench_curves()
    height, margin = 520, dict(l=70, r=24, t=70, b=40)
    fig = make_subplots(rows=1, cols=len(panels), subplot_titles=[p[0] for p in panels], horizontal_spacing=0.06)
    shown = set()
    t_lo, t_hi = None, None
    for ci, (title, lines) in enumerate(panels, 1):
        ends = []
        for strat, sizing, spread, color_i, short in lines:
            if sizing == "final ten":
                c = bench[(bench["symbol"] == symbol) & (bench["name"] == strat) & (bench["window"] == window)]
                if c.empty:
                    continue
                x, y, start = c["time"], c["equity"], 2000.0
            else:
                t = d[(d["symbol"] == symbol) & (d["strategy"] == strat) & (d["sizing"] == sizing) & (d["window"] == window)]
                t = t[t["spread_pct"].notna()] if spread else t[t["spread_pct"].isna()]
                if t.empty:
                    continue
                r = t.iloc[0]
                c = curves[(curves["symbol"] == symbol) & (curves["label"] == r["label"]) & (curves["window"] == window)]
                if c.empty:
                    continue
                x, y, start = c["time"], c["equity"], float(r["account"])
            y = y.clip(lower=start * 0.01)
            t_lo = x.min() if t_lo is None else min(t_lo, x.min())
            t_hi = x.max() if t_hi is None else max(t_hi, x.max())
            color = T.SERIES[color_i] if color_i >= 0 else T.CONTEXT
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=color, width=2), name=short,
                                     legendgroup=short, showlegend=short not in shown,
                                     hovertemplate="<b>$%{y:,.0f}</b> %{x|%d %b %Y}<extra>" + short + "</extra>"),
                          row=1, col=ci)
            shown.add(short)
            ends.append((x.iloc[-1], float(y.iloc[-1]), short, float(y.min()), float(y.max())))
        if not ends:
            continue
        lo = min(e[3] for e in ends) * 0.9
        hi = max(e[4] for e in ends) * 1.1
        ticks = F._log_ticks(lo, hi)
        fig.update_yaxes(T.axis(type="log", range=[np.log10(lo), np.log10(hi)], tickvals=ticks,
                                ticktext=[f"${v:,.0f}" for v in ticks]), row=1, col=ci)
        h_px = height - margin["t"] - margin["b"]
        px = [(np.log10(e[1]) - np.log10(lo)) / (np.log10(hi) - np.log10(lo)) * h_px for e in ends]
        for (xe, ye, short, _, _), p0, p1 in zip(ends, px, _spread_labels(px, h_px)):
            fig.add_annotation(x=xe, y=np.log10(ye), text=short, showarrow=False, xanchor="left", xshift=6,
                               yshift=p1 - p0, font=dict(color=T.INK_2, size=11),
                               xref=f"x{'' if ci == 1 else ci}", yref=f"y{'' if ci == 1 else ci}")
        start_line = 10000.0 if "10,000" in title else 2000.0
        fig.add_hline(y=start_line, line=dict(color=T.AXIS, width=1), row=1, col=ci)
    if t_lo is not None:
        span = t_hi - t_lo
        years = [pd.Timestamp(f"{y}-01-01", tz=t_lo.tz) for y in range(t_lo.year + 1, t_hi.year + 1)]
        step = 2 if len(years) > 5 else 1
        fig.update_xaxes(T.axis(range=[t_lo, t_hi + span * 0.3], tickvals=years[::step],
                                ticktext=[str(v.year) for v in years[::step]]))
    fig.update_layout(**T.plotly_layout(height=height, hovermode="closest", margin=margin))
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0))
    for a in fig.layout.annotations:
        if a.text in [p[0] for p in panels]:
            a.font = dict(color=T.INK, size=13)
    return fig


def figure_portfolio(d: pd.DataFrame, curves: pd.DataFrame, window: str = "since 2020"):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from ..viz import theme as T
    p = portfolio(d, curves, window)
    if p is None:
        return None
    eq = p["equity"]
    dd = (eq / eq.cummax() - 1.0) * 100.0
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
    fig.add_trace(go.Scatter(x=eq.index, y=eq, mode="lines", line=dict(color=T.SERIES[0], width=2),
                             name=f"{len(p['used'])} instances on one account",
                             hovertemplate="<b>$%{y:,.0f}</b> %{x|%d %b %Y}<extra></extra>"), row=1, col=1)
    fig.add_hline(y=ACCOUNT_LARGE, line=dict(color=T.AXIS, width=1), row=1, col=1)
    fig.add_trace(go.Scatter(x=dd.index, y=dd, mode="lines", line=dict(color=T.DOWN, width=1.5), fill="tozeroy",
                             fillcolor="rgba(217,74,74,0.18)", name="below the peak",
                             hovertemplate="<b>%{y:.1f}%</b> %{x|%d %b %Y}<extra>below the peak</extra>"), row=2, col=1)
    ticks = F._log_ticks(float(eq.min()) * 0.9, float(eq.max()) * 1.1)
    fig.update_yaxes(T.axis(type="log", tickvals=ticks, ticktext=[f"${v:,.0f}" for v in ticks], title_text="equity"),
                     row=1, col=1)
    fig.update_yaxes(T.axis(title_text="% below the peak", ticksuffix="%"), row=2, col=1)
    fig.update_xaxes(T.axis())
    fig.update_layout(**T.plotly_layout(height=620, hovermode="x unified", margin=dict(l=70, r=20, t=40, b=30)))
    return fig


def figure_spread():
    import plotly.graph_objects as go
    from ..viz import theme as T
    s = spread_by_year("BTCUSDm")
    fig = go.Figure(go.Bar(x=[str(y) for y in s.index], y=s.to_numpy(), marker=dict(color=T.SERIES[0]),
                           text=[f"{v:.3f}%" for v in s.to_numpy()], textposition="outside",
                           textfont=dict(color=T.INK_2, size=11),
                           hovertemplate="<b>%{y:.3f}%</b> of the price in %{x}<extra></extra>"))
    fig.add_hline(y=0.02, line=dict(color=T.INK_MUTED, width=1, dash="dot"))      # named in the subtitle
    fig.update_yaxes(T.axis(title_text="median spread, % of the price", ticksuffix="%",
                            range=[0, float(s.max()) * 1.18]))
    fig.update_xaxes(T.axis(showgrid=False))
    fig.update_layout(**T.plotly_layout(height=380, hovermode="closest", margin=dict(l=70, r=20, t=30, b=40),
                                        bargap=0.35))
    return fig


def figure_years(out: Path):
    import plotly.graph_objects as go
    from ..viz import theme as T
    y = years_frame(out)
    if y.empty:
        return None
    piv = y.pivot_table(index="row", columns="year", values="return_pct", aggfunc="first", dropna=False)
    order = {}
    for _, r in y.iterrows():
        order.setdefault(r["row"], len(order))
    piv = piv.loc[sorted(piv.index, key=lambda i: order[i])]
    z = piv.to_numpy(dtype=float)
    cap = 40.0

    def blend(c1, c2, f):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{int(round(x + (yv - x) * f)):02x}" for x, yv in zip(a, b))
    mid = T.SURFACE_2
    scale = [[0.0, blend(mid, T.DOWN, 0.8)], [0.5, mid], [1.0, blend(mid, T.UP, 0.8)]]
    text = [[("–" if not np.isfinite(v) else "0%" if round(v) == 0 else f"{int(round(v)):+d}%".replace("-", "−"))
             for v in row] for row in z]
    names = [r.replace(" · his sizing, $10,000", "") for r in piv.index]
    cols = [f"{c}" for c in piv.columns]
    fig = go.Figure(go.Heatmap(z=np.clip(z, -cap, cap), x=cols, y=names, colorscale=scale, zmid=0, zmin=-cap, zmax=cap,
                               text=text, texttemplate="%{text}", textfont=dict(color=T.INK, size=11), customdata=z,
                               xgap=2, ygap=2, hovertemplate="<b>%{customdata:+.1f}%</b> in %{x}<br>%{y}<extra></extra>",
                               colorbar=dict(title=dict(text="return in the year", font=dict(color=T.INK_MUTED, size=11)),
                                             ticksuffix="%", tickfont=dict(color=T.INK_MUTED, size=10), outlinewidth=0)))
    fig.update_yaxes(T.axis(autorange="reversed", showgrid=False))
    fig.update_xaxes(T.axis(side="top", showgrid=False))
    fig.update_layout(**T.plotly_layout(height=80 + 34 * len(names), hovermode="closest",
                                        margin=dict(l=420, r=20, t=40, b=20)))
    return fig


EQUITY_PANELS = {
    "XAUUSDm": [("his sizing, $10,000 account",
                 [("Range Breakout (his gold settings)", "his sizing, $10,000", False, 0, "Range Breakout"),
                  ("ATR Breakout (his gold settings)", "his sizing, $10,000", False, 1, "ATR Breakout"),
                  ("ATR Breakout (his gold settings), one position at a time", "his sizing, $10,000", False, 2,
                   "ATR, one at a time")]),
                ("the bot's unit rule, $2,000 account",
                 [("Range Breakout (his gold settings)", "bot unit rule", False, 0, "Range Breakout"),
                  ("ATR Breakout (his gold settings)", "bot unit rule", False, 1, "ATR Breakout"),
                  ("V3-lite", "final ten", False, 3, "V3-lite"), ("Top 2", "final ten", False, 4, "Top 2")])],
    "BTCUSDm": [("his sizing, $10,000 account",
                 [("Range Breakout (his BTC settings)", "his sizing, $10,000", False, 0, "Range Breakout"),
                  ("Range Breakout (his BTC settings) at a 0.02% spread", "his sizing, $10,000", True, 2,
                   "Range Breakout, 0.02% spread"),
                  ("ATR Breakout (his gold settings)", "his sizing, $10,000", False, 1, "ATR Breakout (not his market)")]),
                ("the bot's unit rule, $2,000 account",
                 [("Range Breakout (his BTC settings)", "bot unit rule", False, 0, "Range Breakout"),
                  ("ATR Breakout (his gold settings)", "bot unit rule", False, 1, "ATR Breakout (not his market)"),
                  ("Turtle + bot votes", "final ten", False, 3, "Turtle + bot votes"),
                  ("Top 2", "final ten", False, 4, "Top 2")])],
    "US30m": [("his sizing, $10,000 account",
               [("Go Long (his index settings)", "his sizing, $10,000", False, 0, "Go Long"),
                ("Turnaround Tuesday (his US30 settings, SMA 25)", "his sizing, $10,000", False, 1, "Turnaround Tuesday"),
                ("Range Breakout (his US30 settings)", "his sizing, $10,000", False, 2, "Range Breakout"),
                ("Buy and hold the index (reference, not his)", "his sizing, $10,000", False, -1, "buy and hold")])],
    "USTECm": [("his sizing, $10,000 account",
                [("Go Long (his index settings)", "his sizing, $10,000", False, 0, "Go Long"),
                 ("Turnaround Tuesday (his USTEC settings, SMA 9)", "his sizing, $10,000", False, 1, "Turnaround Tuesday"),
                 ("Buy and hold the index (reference, not his)", "his sizing, $10,000", False, -1, "buy and hold")])],
}


def report(out: Path = OUT, images: bool = True, log=print) -> pd.DataFrame:
    out = Path(out)
    d = load_runs(out)
    b = benchmarks()
    allr = pd.concat([d, b], ignore_index=True) if len(b) else d
    allr.to_csv(out / "results.csv", index=False)
    curves = load_curves(out)
    tpl = out / "BALKE.template.md"
    if tpl.exists():
        (out / "BALKE.md").write_text(fill(tpl.read_text(), out, allr, curves))
        log(f"wrote {out / 'BALKE.md'}")
    if images:
        for sym, panels in EQUITY_PANELS.items():
            if not (d["symbol"] == sym).any():
                continue
            w = MAIN_WINDOW[sym]
            F._write_fig(figure_equity(d, curves, sym, panels, w), out, f"equity_{sym}",
                         f"{MARKET[sym]} · his strategies · {WINDOW_NAMES[w]}",
                         "log scale; each panel is its own account kind, the line marks its starting balance; "
                         "a strategy keeps its colour in both panels" if len(panels) > 1 else
                         "log scale; the line marks the $10,000 starting balance; buy and hold: 100% of the balance "
                         "in the index all the time, no swap")
            log(f"  chart equity {sym}")
        fp = figure_portfolio(d, curves)
        if fp is not None:
            n_used = len(portfolio(d, curves, "since 2020")["used"])
            F._write_fig(fp, out, "portfolio", "His instances together on one $10,000 account · Jul 2020 - Nov 2026",
                         f"{n_used} of his 14 Four Edge instances, his sizing; daily returns added up and compounded "
                         "(an approximation of one shared account), marked once a day")
        F._write_fig(figure_spread(), out, "btc_spread", "BTC spread on Exness, by year",
                     "median over all M1 bars of the bar's mean spread, as a % of the price; dotted line: 0.02%, "
                     "the cost scenario of §5.3")
        fy = figure_years(out)
        if fy is not None:
            F._write_fig(fy, out, "years", "Return in each calendar year · his sizing, $10,000 account",
                         "gold and BTC: the 8-year account (2018: from 13 Nov); indices: from 1 Jul 2020; "
                         "2026: to 13 Nov")
    return allr


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.balke")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--symbols", nargs="+", default=list(ALL_SYMBOLS))
    rp = sub.add_parser("report")
    rp.add_argument("--no-images", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.symbols)
    elif a.cmd == "report":
        report(images=not a.no_images)


if __name__ == "__main__":
    main()
