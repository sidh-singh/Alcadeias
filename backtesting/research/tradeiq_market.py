"""
TradeIQ's four RSI replacements on gold and BTC: the data and the execution harness.

    python -B -m backtesting.research.tradeiq_market fetch-binance [--last-day 2026-11-26]
    python -B -m backtesting.research.tradeiq_market check-binance
    python -B -m backtesting.research.tradeiq_market profile XAUUSDm|BTCUSDm

The plan is ``backtest_results/tradeiq_rsi/PREREG.md`` (frozen) with ``DEVIATIONS.md``; the data end is in ``DATA.md``.
Existing modules are imported, never edited: the bars, plans, fills, stops and the account are ``external.py``'s.

What it gives the study
-----------------------
* ``load(symbol)``: the M1 bid bars of the tick store from the symbol's data start (gold 2017-01, BTC 2018-01) as an
  ``external.Market`` (``external.load_market`` with its ``earliest`` argument, wrapped as ``TMarket``).
  ``TMarket.tbars('1H' | '4H' | '1D')``: the bars exactly as ``external.tf_bars`` / ``external.day_bars`` build them
  (UTC boundaries; a UTC day with fewer than 360 M1 bars is merged into the next day), with their open and close
  times, the bid OHLC, the tick volume (the sum of the M1 tick counts ``n``) and the tick-weighted mean spread.
  ``binance_volume(market, tf)``: BTC only, the BTCUSDT spot volume of Binance's public archive on the same bars.
* ``run(market, bars, state, start, end, stop=None, cost=1.0)``: a target state per signal bar (+1 long, 0 flat,
  -1 short, decided at that bar's close) executed over one window by ``external.make_plan`` / ``external.run_path``:
  a decision fills at the open of the first M1 bar at or after the bar's close, a buy at the ask (bid + that M1 bar's
  mean spread), a sell at the bid; a stop (S1: a price distance per bar, set from the entry fill, never moved) is
  checked on every M1 bar, a gap through it fills at the open, and one extra spread of the stop's M1 bar is charged on
  every stop fill (the silver study's 2.2 rule for stop exits); ``cost=1.5`` multiplies every spread by 1.5 (fills,
  the stop slippage, the short's stop trigger on the ask, the marks of a short; DEVIATIONS 27). DEVIATIONS 1-3:
  after a stop the variant stays flat until its state changes; the window's first bar takes the state at its close;
  what is open at the window's end is closed at the close of its last M1 bar.
* ``metrics(run)``: PREREG 7 per 0.01 lot (``external.metrics`` where its definitions match, plus the rest);
  ``buy_and_hold``: the reference; ``account_curve(run)``: PREREG 8, ``external.account`` with the bot's unit rule.
* The hold-out guard: every path that loads, serves or scores data goes through ``_guard``, which raises
  ``HoldOutError`` for anything at or after 2024-07-01 00:00 UTC unless ``FINALISTS.md`` and ``FINALISTS.md.sha256``
  exist in the study folder and the hash matches. While it is closed ``load`` serves the data up to that instant only,
  so nothing after it is even in memory.

Decisions where the plan is silent (DEVIATIONS 4-7 hold the ones that can move a result)
-----------------------------------------------------------------------------------------
* The window's first bar is the first signal bar that closes after the window's start. A decision whose fill bar is
  at or after the window's end is not executed.
* Each decision is stamped with the open time of its fill bar, not with the bar's close. ``external._path_kernel``
  lets an entry follow an exit at the same M1 open only when the decision time is not earlier than that open; with
  close-time stamps a flip whose close has no quote (a weekend, gold's daily break, a missing minute) would close the
  old side and open the new one a signal bar later. The stamp is read nowhere else (no pause, no quote-age limit).
  The same stamp lets the new state enter at an open where a gap stop has just closed the old side (DEVIATIONS 4).
* The tick volume of a bar is the sum of its M1 tick counts; its mean spread is weighted by ticks (as
  ``store.resample_bars``). Binance: the base-asset volume (BTC) of the kline whose open time is the 1H bar's open; an
  hour with no kline (an exchange outage) has volume 0 and is counted in ``missing``; 4H and 1D are the sums over our
  1H bars inside each bar; Binance hours inside our own data holes belong to no bar (DEVIATIONS 5).
* Times are ISO strings, Timestamps (UTC) or epoch seconds (int).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import resource
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..config import REPO_ROOT
from ..data import store
from . import external as X

SYMBOLS = ("XAUUSDm", "BTCUSDm")
DATA_START = {"XAUUSDm": "2017-01-01", "BTCUSDm": "2018-01-01"}
# the last tick of the store after the November 2026 month was downloaded again on 28 Nov 2026 (DATA.md)
LAST_TICK = {"XAUUSDm": "2026-11-25 23:59:59.968", "BTCUSDm": "2026-11-26 23:59:59.006"}
# the data end, exclusive: the end of the minute of the last tick
DATA_END = {"XAUUSDm": "2026-11-26", "BTCUSDm": "2026-11-27"}
HOLDOUT_START = "2024-07-01"            # the first instant of the hold-out (PREREG 3)
WINDOWS: Dict[str, Tuple[str, Optional[str]]] = {
    "dev": ("2019-01-01", "2023-01-01"),
    "val": ("2023-01-01", HOLDOUT_START),
    "devval": ("2019-01-01", HOLDOUT_START),
    "holdout": (HOLDOUT_START, None),          # None: the symbol's data end
    "full": ("2019-01-01", None),              # PREREG 8: 2019-01-01 to the data end
}
TFS: Dict[str, Tuple[str, int]] = {"1H": ("H1", 3600), "4H": ("H4", 14400), "1D": ("D1", 86400)}
STUDY_DIR = REPO_ROOT / "backtest_results" / "tradeiq_rsi"
DAY = 86400
WEEK = 7 * DAY
REASONS = {X.WHY_SIGNAL: "signal", X.WHY_STOP: "stop", X.WHY_GAP_STOP: "gap stop", X.WHY_END: "end",
           X.WHY_TARGET: "target", X.WHY_GAP_TARGET: "gap target"}


def s_of(x) -> int:
    """UTC epoch seconds of an ISO string, a Timestamp or epoch seconds (int)."""
    if isinstance(x, (int, np.integer)):
        return int(x)
    return int(store.to_ms(x) // 1000)


def utc(s) -> pd.Timestamp:
    return pd.Timestamp(int(s), unit="s", tz="UTC")


CUT_S = s_of(HOLDOUT_START)
DATA_END_S = {k: s_of(v) for k, v in DATA_END.items()}


def window(name: str, symbol: str) -> Tuple[str, str]:
    """(start, end) of a named window, end exclusive; the hold-out ends at the symbol's data end."""
    a, z = WINDOWS[name]
    return a, (DATA_END[symbol] if z is None else z)


# ───────────────────────────── the hold-out guard ─────────────────────────────

class HoldOutError(PermissionError):
    """A request reached into the hold-out (PREREG 3) before FINALISTS.md and its sha256 were frozen."""


def finalists_frozen() -> bool:
    """True when FINALISTS.md and FINALISTS.md.sha256 both exist in the study folder and the hash matches."""
    f, h = Path(STUDY_DIR) / "FINALISTS.md", Path(STUDY_DIR) / "FINALISTS.md.sha256"
    try:
        body = f.read_bytes()
        want = h.read_text(encoding="utf-8").split()
    except OSError:
        return False
    return bool(want) and hashlib.sha256(body).hexdigest() == want[0].strip().lower()


def _guard(end_s, what: str) -> None:
    """
    THE hold-out check; every path that loads, serves or scores data calls it. ``end_s`` is the exclusive end (UTC
    seconds) of what the request touches: a minute opening at t touches [t, t + 60), a bar touches up to its close.
    Anything past HOLDOUT_START raises unless FINALISTS.md is frozen.
    """
    end_s = int(end_s)
    if end_s > CUT_S and not finalists_frozen():
        raise HoldOutError(f"{what}: reaches {utc(end_s)}, past the hold-out start {HOLDOUT_START} 00:00 UTC, and "
                           f"{Path(STUDY_DIR) / 'FINALISTS.md'} with a matching sha256 does not exist")


# ───────────────────────────── the market and its bars ─────────────────────────────

@dataclass(frozen=True, eq=False)
class TBars:
    """Bars of one timeframe of a TMarket (external's construction plus the volume and the spread)."""
    symbol: str
    tf: str
    t: np.ndarray          # open time, UTC s
    tc: np.ndarray         # close time: the bar may be read from this instant on
    i0: np.ndarray         # first M1 bar
    i1: np.ndarray         # last M1 bar
    ex: np.ndarray         # the M1 bar whose open fills an order decided at tc (len(market): not in the data)
    o: np.ndarray          # bid OHLC
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    vol: np.ndarray        # tick volume: the sum of the M1 tick counts
    spread: np.ndarray     # mean spread, weighted by ticks
    n_m1: np.ndarray       # M1 bars in the bar
    complete: np.ndarray   # the bar's close is inside the data
    m1_t: np.ndarray = field(repr=False)   # the market's M1 times (the bars belong to that market)

    def __len__(self) -> int:
        return int(len(self.t))

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame({"open_time": pd.to_datetime(self.t, unit="s", utc=True),
                             "close_time": pd.to_datetime(self.tc, unit="s", utc=True),
                             "open": self.o, "high": self.h, "low": self.l, "close": self.c, "tick_volume": self.vol,
                             "spread": self.spread, "m1_bars": self.n_m1, "complete": self.complete})


class TMarket(X.Market):
    """
    external.Market over the study's span. ``end_s``: the exclusive end of the span it holds. ``cost``: 1.0 for the
    market itself; ``costed(1.5)`` is a copy that shares everything but the spread, used for the execution: the fills,
    the stop slippage, a short's stop trigger on the ask and the marks of a short (DEVIATIONS 27).
    """

    def __init__(self, symbol: str, m1: Dict[str, np.ndarray], end_s: Optional[int] = None):
        super().__init__(symbol, m1)
        if len(self.t) == 0:
            raise ValueError(f"{symbol}: no M1 bars")
        if len(self.t) > 1 and not bool(np.all(np.diff(self.t) > 0)):
            raise ValueError(f"{symbol}: M1 times must increase")
        last = int(self.t[-1]) + 60
        self.end_s = last if end_s is None else int(end_s)
        if last > self.end_s:
            raise ValueError(f"{symbol}: M1 bars past the market's end {utc(self.end_s)}")
        _guard(last, f"{symbol} M1 bars")
        self.cost = 1.0
        self._tb: Dict[str, TBars] = {}
        self._costed: Dict[float, "TMarket"] = {}
        self._binance = None

    def tbars(self, tf: str) -> TBars:
        if self.cost != 1.0:
            raise ValueError("bars come from the market itself, not from a cost copy")
        _guard(int(self.t[-1]) + 60, f"{self.symbol} {tf} bars")
        if tf not in self._tb:
            key, _ = TFS[tf]
            b = self.bars(key)
            if len(b) == 0:
                raise ValueError(f"{self.symbol}: no {tf} bars")
            if not (np.all(b.i0[1:] == b.i1[:-1] + 1) and np.all(b.i1 >= b.i0)):
                raise AssertionError(f"{self.symbol} {tf}: bars do not tile the M1 bars")
            top = int(b.i1[-1]) + 1
            vol = np.add.reduceat(self.n[:top], b.i0)
            spv = np.add.reduceat(self.sp[:top] * self.n[:top], b.i0)
            with np.errstate(divide="ignore", invalid="ignore"):
                spread = np.where(vol > 0, spv / vol, np.nan)
            self._tb[tf] = TBars(self.symbol, tf, b.t, b.tc, b.i0, b.i1, b.ex, b.o, b.h, b.l, b.c, vol, spread,
                                 (b.i1 - b.i0 + 1).astype(np.int64), b.tc <= self.end_s, self.t)
        return self._tb[tf]

    def costed(self, mult: float) -> "TMarket":
        """The same market with the spread of every M1 bar times ``mult`` (shares the bars and clocks). Everything
        ``run`` executes on it sees that spread: the fills, the stop slippage, a short's stop trigger (the high + the
        spread) and a short's marks (DEVIATIONS 27). The bars and the indicators come from the market itself."""
        mult = float(mult)
        if self.cost != 1.0:
            raise ValueError("cost copies are made from the market itself")
        if mult == 1.0:
            return self
        if mult < 0 or not math.isfinite(mult):
            raise ValueError(f"cost multiplier {mult}")
        if mult not in self._costed:
            cm = object.__new__(TMarket)
            cm.__dict__.update(self.__dict__)
            cm.sp = np.ascontiguousarray(self.sp * mult, np.float64)
            cm.cost = mult
            cm._tb, cm._costed, cm._binance = {}, {}, None
            self._costed[mult] = cm
        return self._costed[mult]

    def nbytes(self) -> int:
        return int(sum(getattr(self, k).nbytes for k in ("t", "o", "h", "l", "c", "sp", "n")))


def load(symbol: str, end=None, store_dir: Path = store.DEFAULT_STORE_DIR) -> TMarket:
    """
    The M1 bars of ``symbol`` from its data start to ``end`` (exclusive). ``end=None``: the study's data end once
    FINALISTS.md is frozen, until then the hold-out start. An explicit ``end`` past the hold-out start raises while
    the hold-out is closed; an ``end`` past the study's data end raises always.
    """
    if symbol not in DATA_START:
        raise ValueError(f"{symbol}: not in this study ({', '.join(SYMBOLS)})")
    if end is None:
        end_s = DATA_END_S[symbol] if finalists_frozen() else CUT_S
    else:
        end_s = s_of(end)
    if end_s > DATA_END_S[symbol]:
        raise ValueError(f"{symbol}: {utc(end_s)} is past the study's data end {DATA_END[symbol]} (DATA.md)")
    _guard(end_s, f"load {symbol} to {utc(end_s)}")
    m = X.load_market(symbol, Path(store_dir), earliest=DATA_START[symbol], end=str(utc(end_s).tz_localize(None)))
    mk = TMarket(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp, "n": m.n}, end_s)
    if end_s == DATA_END_S[symbol] and Path(store_dir) == store.DEFAULT_STORE_DIR:
        span = store.data_span(symbol, store_dir)
        if span is None or span[1] < pd.Timestamp(LAST_TICK[symbol], tz="UTC"):
            raise ValueError(f"{symbol}: the store ends before the study's last tick {LAST_TICK[symbol]}")
    return mk


def htf_at(htf: TBars, values, ltf: TBars, default=np.nan) -> np.ndarray:
    """``values`` of the last higher-timeframe bar CLOSED at each lower-timeframe bar's close (PREREG 6, F2)."""
    return X.value_at(htf.tc, np.asarray(values, np.float64), ltf.tc, default)


def s1_stop(bars: TBars, mult: float = 3.0, n: int = 14) -> np.ndarray:
    """S1: ``mult`` x Wilder ATR(n) of the signal timeframe, per bar (NaN until the ATR exists)."""
    return mult * X.wilder_atr(bars.h, bars.l, bars.c, n)


# ───────────────────────────── the execution adapter ─────────────────────────────

@njit(cache=True)
def _unit_marks(c, h, l, sp, k, d, eix, xix, epx, xpx, why, ia, iz):
    """
    The equity of one unit (0.01 lot) over the M1 bars [ia, iz), USD from 0 at ia, marked as
    external._account_kernel marks an account (one unit, no wipe-out): ``ec`` at the close mark of each bar (bid for
    a long, ask for a short), ``ew`` the worst mark inside it (the low, or the high + spread; an exit's own price on
    its bar, the bar's extreme for an exit at the close), ``pos`` the side held through the bar (an exit at the open
    or inside a bar ends the holding before that bar; the exit at the window's end after it). The max drawdown is
    taken against the running peak: the close mark of every bar a position outlives first, then that bar's worst; the
    balance after each exit.
    """
    n = iz - ia
    ec = np.zeros(n)
    ew = np.full(n, np.inf)
    pos = np.zeros(n, np.int8)
    bal = 0.0
    peak = 0.0
    maxdd = 0.0
    jn = ia
    for i in range(d.shape[0]):
        e = eix[i]
        x = xix[i]
        s = d[i]
        ep = epx[i]
        while jn < e:
            ec[jn - ia] = bal
            if bal < ew[jn - ia]:
                ew[jn - ia] = bal
            jn += 1
        for j in range(e, x + 1):
            if j == x:
                mc = xpx[i]
                if why[i] == 3 or why[i] == 4:
                    mw = l[j] if s == 1 else h[j] + sp[j]
                else:
                    mw = xpx[i]
            else:
                mc = c[j] if s == 1 else c[j] + sp[j]
                mw = l[j] if s == 1 else h[j] + sp[j]
            uc = k * s * (mc - ep)
            uw = k * s * (mw - ep)
            if j < x and bal + uc > peak:
                peak = bal + uc
            w = bal + uw
            if peak - w > maxdd:
                maxdd = peak - w
            ec[j - ia] = bal + uc
            if w < ew[j - ia]:
                ew[j - ia] = w
            if j < x or why[i] == 4:                        # an exit at the window's end is held through its bar
                pos[j - ia] = s
        bal += k * s * (xpx[i] - ep)
        if bal > peak:
            peak = bal
        if x + 1 > jn:
            jn = x + 1
    while jn < iz:
        ec[jn - ia] = bal
        if bal < ew[jn - ia]:
            ew[jn - ia] = bal
        jn += 1
    return ec, ew, pos, bal, maxdd


@dataclass(eq=False)
class Run:
    """One state series executed over one window, per 0.01 lot."""
    symbol: str
    tf: str
    start: str
    end: str
    a_s: int
    z_s: int
    ia: int                    # first M1 bar of the window
    iz: int                    # end (exclusive)
    cost: float
    stopped: bool              # S1 (a stop distance was given)
    m: TMarket                 # the market the fills were made on (the cost copy)
    path: X.Path_              # external's path, the stop slippage included in the exit prices
    trades: pd.DataFrame
    ec: np.ndarray             # per-unit equity at each M1 bar's close mark, USD from 0 at the window start
    ew: np.ndarray             # the worst mark inside each M1 bar
    pos: np.ndarray            # side held through each M1 bar
    net: float
    max_dd: float              # USD per unit, against the running peak (external's convention)
    n_decisions: int = 0


def _states(state, n: int) -> np.ndarray:
    st = np.asarray(state)
    if st.shape != (n,):
        raise ValueError(f"state has shape {st.shape}, the bars {n}")
    if st.dtype.kind not in "iub":
        if not np.all(np.isfinite(st)):
            raise ValueError("state holds NaN / inf")
    if not np.all(np.isin(st, (-1, 0, 1))):
        raise ValueError("state must be +1 (long), 0 (flat) or -1 (short)")
    return st.astype(np.int64)


def _stop_slippage(m: TMarket, p: X.Path_) -> X.Path_:
    """One extra spread of the fill's M1 bar (x the cost of ``m``) against every stop and gap-stop exit."""
    if len(p) and int(p.nleg.max()) > 1:
        raise AssertionError("pyramids are not part of this study")
    hit = (p.why == X.WHY_STOP) | (p.why == X.WHY_GAP_STOP)
    xpx = p.xpx.copy()
    xpx[hit] -= p.dir[hit] * m.sp[p.xix[hit]]
    return replace(p, xpx=xpx)


def _trades(m: TMarket, p: X.Path_) -> pd.DataFrame:
    k = m.k
    hit = (p.why == X.WHY_STOP) | (p.why == X.WHY_GAP_STOP)
    entry_t = m.t[p.eix]
    exit_t = m.t[p.xix] + np.where(p.why == X.WHY_END, 60, 0)
    return pd.DataFrame({
        "entry_time": pd.to_datetime(entry_t, unit="s", utc=True),
        "exit_time": pd.to_datetime(exit_t, unit="s", utc=True),
        "side": p.dir.astype(np.int64),
        "entry": p.epx,
        "exit": p.xpx,
        "reason": [REASONS[int(w)] for w in p.why],
        "pnl": k * p.dir * (p.xpx - p.epx),
        "slippage": np.where(hit, k * m.sp[p.xix], 0.0),
        "hold_h": (exit_t - entry_t) / 3600.0,
        "entry_ix": p.eix,
        "exit_ix": p.xix,
    })


def _window_ix(mk: TMarket, start, end) -> Tuple[int, int, int, int]:
    a_s, z_s = s_of(start), s_of(end)
    if not a_s < z_s:
        raise ValueError(f"empty window {start} .. {end}")
    _guard(z_s, f"window {utc(a_s)} .. {utc(z_s)}")
    if a_s < int(mk.t[0]) or z_s > mk.end_s:
        raise ValueError(f"window {utc(a_s)} .. {utc(z_s)} is outside the data held "
                         f"({utc(mk.t[0])} .. {utc(mk.end_s)})")
    ia = int(np.searchsorted(mk.t, a_s, side="left"))
    iz = int(np.searchsorted(mk.t, z_s, side="left"))
    if iz <= ia:
        raise ValueError(f"no M1 bar in {utc(a_s)} .. {utc(z_s)}")
    return a_s, z_s, ia, iz


def run(mk: TMarket, bars: TBars, state, start, end, stop=None, cost: float = 1.0) -> Run:
    """
    Execute a target state per bar of ``bars`` (+1 / 0 / -1, decided at the bar's close) over [start, end).
    ``stop``: None (S0) or a price distance per bar (S1), taken at the entry's decision bar and set from the entry
    fill. ``cost``: the spread multiplier (1.0, or 1.5 for the stress).
    """
    if not isinstance(mk, TMarket) or mk.cost != 1.0:
        raise TypeError("run() takes the TMarket itself (load()); the cost copy is made here")
    _guard(int(mk.t[-1]) + 60, f"{mk.symbol} market")
    if not isinstance(bars, TBars) or bars.m1_t is not mk.t:
        raise ValueError("the bars do not belong to this market (use market.tbars(tf))")
    a_s, z_s, ia, iz = _window_ix(mk, start, end)
    st = _states(state, len(bars))
    sl_all = None
    if stop is not None:
        sl_all = np.asarray(stop, np.float64)
        if sl_all.shape != (len(bars),):
            raise ValueError(f"stop has shape {sl_all.shape}, the bars {len(bars)}")
    cm = mk.costed(cost)
    sel = np.flatnonzero((bars.tc > a_s) & (bars.ex < iz))
    if len(sel) == 0:
        dt = np.zeros(0, np.int64)
        want = xl = xs = sl = np.zeros(0)
    else:
        if not np.all(np.diff(sel) == 1):
            raise AssertionError("window bars are not contiguous")
        s = st[sel]
        prev = np.where(sel >= 1, st[np.maximum(sel - 1, 0)], 0)
        changed = s != prev
        changed[0] = True                                   # DEVIATIONS 2: the window's first bar takes the state
        want = np.where(changed, s, 0)                      # DEVIATIONS 1: entries only where the state changes
        xl, xs = s != 1, s != -1
        dt = mk.t[bars.ex[sel]]                             # stamped at the fill bar's open (see the docstring)
        if sl_all is None:
            sl = np.full(len(sel), np.nan)
        else:
            sl = sl_all[sel]
            bad = (want != 0) & ~(np.isfinite(sl) & (sl > 0))
            if bad.any():
                b = int(sel[np.flatnonzero(bad)[0]])
                raise ValueError(f"no valid stop distance at the entry decided at {utc(bars.tc[b])}: {sl_all[b]}")
    plan = X.make_plan(cm, dt, want=want, xl=xl, xs=xs, sl=sl)
    if len(plan) != len(sel) or (len(sel) and not np.array_equal(plan.dx, bars.ex[sel])):
        raise AssertionError("a decision does not fill at its bar's execution M1 bar")
    p = _stop_slippage(cm, X.run_path(cm, plan, ia, iz))
    ec, ew, pos, bal, maxdd = _unit_marks(cm.c, cm.h, cm.l, cm.sp, cm.k, p.dir, p.eix, p.xix, p.epx, p.xpx, p.why,
                                          ia, iz)
    tr = _trades(cm, p)
    net = float(bal)
    if abs(net - float(tr.pnl.sum())) > 1e-6 * max(1.0, abs(net)):
        raise AssertionError("the equity curve and the trades disagree")
    return Run(mk.symbol, bars.tf, str(utc(a_s)), str(utc(z_s)), a_s, z_s, ia, iz, float(cost), sl_all is not None,
               cm, p, tr, ec, ew, pos, net, float(maxdd), int(len(sel)))


# ───────────────────────────── scores (PREREG 7) ─────────────────────────────

def _edges_weeks(a_s: int, z_s: int) -> np.ndarray:
    """The window's start, every Saturday 00:00 UTC strictly inside it, its end."""
    d0 = (a_s // DAY) * DAY
    first = d0 + ((5 - ((d0 // DAY + 3) % 7)) % 7) * DAY           # (epoch day + 3) % 7: 0 = Monday, 5 = Saturday
    t = np.arange(first, z_s, WEEK, dtype=np.int64)
    t = t[(t > a_s) & (t < z_s)]
    return np.concatenate([[a_s], t, [z_s]]).astype(np.int64)


def _edges_quarters(a_s: int, z_s: int) -> np.ndarray:
    """The window's start, every calendar-quarter start strictly inside it, its end."""
    q = pd.date_range(utc(a_s).tz_localize(None).normalize(), utc(z_s).tz_localize(None), freq="QS")
    t = np.asarray([x.value // 10**9 for x in q], np.int64)
    t = t[(t > a_s) & (t < z_s)]
    return np.concatenate([[a_s], t, [z_s]]).astype(np.int64)


def _edges_days(a_s: int, z_s: int) -> np.ndarray:
    t = np.arange((a_s // DAY + 1) * DAY, z_s, DAY, dtype=np.int64)
    return np.concatenate([[a_s], t, [z_s]]).astype(np.int64)


def eq_at(r: Run, T) -> np.ndarray:
    """Per-unit equity at the instants T: the close mark of the last M1 bar of the window opening before each."""
    _guard(r.z_s, f"{r.symbol} run")
    i = np.searchsorted(r.m.t[r.ia:r.iz], np.asarray(T, np.int64), side="left") - 1
    return np.where(i >= 0, r.ec[np.maximum(i, 0)], 0.0)


def weekly_pnl(r: Run) -> Tuple[np.ndarray, np.ndarray]:
    """(week starts, per-unit P/L of each week): weeks from Saturday 00:00 UTC, the partial first and last included.
    The edges depend on the window only, so the weeks of all variants of a window line up (for SPA)."""
    e = _edges_weeks(r.a_s, r.z_s)
    return e[:-1], np.diff(eq_at(r, e))


def quarter_pnl(r: Run) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(quarter starts, per-unit P/L of each calendar quarter, whether a position was held in it)."""
    e = _edges_quarters(r.a_s, r.z_s)
    ix = np.searchsorted(r.m.t[r.ia:r.iz], e, side="left")
    held = np.asarray([bool(np.any(r.pos[ix[i]:ix[i + 1]] != 0)) for i in range(len(e) - 1)])
    return e[:-1], np.diff(eq_at(r, e)), held


def unit_curve(r: Run) -> pd.DataFrame:
    """Daily per-unit equity (close mark at each UTC midnight) and the worst mark of the day before it."""
    e = _edges_days(r.a_s, r.z_s)
    ix = np.searchsorted(r.m.t[r.ia:r.iz], e, side="left")
    worst = np.full(len(e), np.nan)
    worst[0] = 0.0
    for i in range(1, len(e)):
        if ix[i] > ix[i - 1]:
            worst[i] = float(r.ew[ix[i - 1]:ix[i]].min())
    return pd.DataFrame({"time": pd.to_datetime(e, unit="s", utc=True), "equity": eq_at(r, e), "worst": worst})


def _longest_run(x: np.ndarray) -> int:
    best = cur = 0
    for v in x:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def metrics(r: Run) -> Dict[str, object]:
    """
    PREREG 7 for one run, per 0.01 lot, after costs. external.metrics gives what it defines the same way (net,
    trades, win rate, average win and loss, profit factor, worst trade, the quarter blocks); the rest is added:
    max drawdown and profit / max drawdown, the share of positive calendar quarters (all quarters of the window,
    marked at the close mark with open positions), the annualised weekly Sharpe (and its raw value, skew and kurtosis
    for the deflated Sharpe), average holding time, time in the market (share of the window's M1 bars with a position),
    the longest losing streak (consecutive trades with P/L < 0), the long and short sides, the stop exits.
    """
    _guard(r.z_s, f"{r.symbol} run")
    tr = r.trades
    pnl = tr.pnl.to_numpy(np.float64)
    q0, qp, held = quarter_pnl(r)
    qe = _edges_quarters(r.a_s, r.z_s)
    res = X.Result(trades_pnl=pnl, trades_dir=tr.side.to_numpy(), trades_eix=tr.entry_ix.to_numpy(),
                   trades_xix=tr.exit_ix.to_numpy(), skipped=0, final=X.ACCOUNT + r.net, max_dd=np.nan,
                   wiped=False, wipe_t=None, blocks=X.ACCOUNT + eq_at(r, qe), orders=2 * len(pnl))
    base = X.metrics(res, r.start, r.end)
    keep = ("quarters", "net", "net_per_q", "trades", "trades_per_q", "win_rate", "avg_win", "avg_loss",
            "profit_factor", "worst_trade", "blocks", "losing_blocks", "n_blocks")
    out: Dict[str, object] = {"symbol": r.symbol, "tf": r.tf, "start": r.start, "end": r.end, "cost": r.cost,
                              "stop": "S1" if r.stopped else "S0"}
    out.update({k: base[k] for k in keep})
    _, wk = weekly_pnl(r)
    sd = float(np.std(wk, ddof=1)) if len(wk) > 2 else 0.0
    sr = float(np.mean(wk) / sd) if sd > 0 else 0.0
    wkv = pd.Series(wk)
    out.update(
        net_exact=r.net,
        max_dd=r.max_dd,
        profit_dd=(r.net / r.max_dd) if r.max_dd > 0 else np.nan,
        n_q=int(len(qp)),
        pos_q=int((qp > 0).sum()),
        pos_q_share=float((qp > 0).mean()) if len(qp) else np.nan,
        n_q_exposed=int(held.sum()),
        weeks=int(len(wk)),
        sharpe_w=sr * math.sqrt(52.0),
        sr_w_raw=sr,
        skew_w=float(wkv.skew()) if len(wk) > 3 else 0.0,
        kurt_w=float(wkv.kurt() + 3.0) if len(wk) > 3 else 3.0,
        avg_hold_h=float(tr.hold_h.mean()) if len(tr) else np.nan,
        time_in_mkt=float((r.pos != 0).mean()),
        max_losing_streak=_longest_run(pnl < 0),
        wins=int((pnl > 0).sum()),
        losses=int((pnl < 0).sum()),
        best_trade=float(pnl.max()) if len(pnl) else np.nan,
        n_long=int((tr.side > 0).sum()),
        n_short=int((tr.side < 0).sum()),
        long_pnl=float(pnl[tr.side.to_numpy() > 0].sum()),
        short_pnl=float(pnl[tr.side.to_numpy() < 0].sum()),
        n_stops=int(tr.reason.isin(["stop", "gap stop"]).sum()),
        slippage=float(tr.slippage.sum()),
    )
    return out


def buy_and_hold(mk: TMarket, start, end, cost: float = 1.0) -> Dict[str, float]:
    """The reference: 0.01 lot bought at the ask at the window's first M1 open, sold at the bid at its last close."""
    if not isinstance(mk, TMarket) or mk.cost != 1.0:
        raise TypeError("buy_and_hold() takes the TMarket itself")
    a_s, z_s, ia, iz = _window_ix(mk, start, end)
    cm = mk.costed(cost)
    plan = X.make_plan(cm, np.asarray([mk.t[ia]], np.int64), want=np.asarray([1]))
    p = X.run_path(cm, plan, ia, iz)
    _, _, _, bal, maxdd = _unit_marks(cm.c, cm.h, cm.l, cm.sp, cm.k, p.dir, p.eix, p.xix, p.epx, p.xpx, p.why, ia, iz)
    return {"bh_net": float(bal), "bh_max_dd": float(maxdd), "bh_profit_dd": float(bal / maxdd) if maxdd > 0 else np.nan,
            "bh_entry": float(p.epx[0]), "bh_exit": float(p.xpx[0])}


def account_curve(r: Run, sizing: X.Sizing = X.BOT) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """
    PREREG 8: the run's trades on a $2,000 account with the bot's unit rule (unit = floor(balance / 2,500) + 1, at
    most 10, set when a position opens), marked at the worst price of each M1 bar, wiped at equity 0
    (``external.account``). Returns the equity at every UTC midnight (close-marked) and a summary.
    """
    _guard(r.z_s, f"{r.symbol} run")
    e = _edges_days(r.a_s, r.z_s)
    bnd = np.concatenate([[r.ia], r.ia + np.searchsorted(r.m.t[r.ia:r.iz], e[1:-1], side="left"), [r.iz]])
    res = X.account(r.m, r.path, sizing, bnd.astype(np.int64))
    curve = pd.DataFrame({"time": pd.to_datetime(e, unit="s", utc=True), "equity": res.blocks})
    unit = r.trades.pnl.to_numpy()[: len(res.trades_pnl)]
    with np.errstate(divide="ignore", invalid="ignore"):
        units = np.where(np.abs(unit) > 1e-9, res.trades_pnl / unit, np.nan)
    summary = {"start_equity": X.ACCOUNT, "final": res.final, "net": res.final - X.ACCOUNT,
               "max_dd_pct": res.max_dd * 100.0, "wiped": res.wiped,
               "wiped_at": str(utc(res.wipe_t)) if res.wiped else "", "trades": int(len(res.trades_pnl)),
               "skipped": int(res.skipped), "max_units": float(np.nanmax(np.round(units))) if np.isfinite(units).any() else np.nan}
    return curve, summary


# ───────────────────────────── Binance BTCUSDT spot volume (BTC only) ─────────────────────────────

BINANCE_URL = "https://data.binance.vision/data/spot"
BINANCE_DIR = REPO_ROOT / "data" / "raw" / "binance"
BINANCE_PATH = "klines/BTCUSDT/1h"
BINANCE_FROM = (2018, 1)
BINANCE_LAST_DAY = "2026-11-26"           # the BTC data end's day (DATA.md)
_UA = "Mozilla/5.0 (compatible; kline-history-client)"      # generic; nothing identifying is sent
HOUR_MS = 3_600_000


def _binance_files(last_day: str = BINANCE_LAST_DAY, root: Path = BINANCE_DIR) -> List[Tuple[str, int, int, str, Path]]:
    """(label, period start s, period end s, url, local path): monthly zips from 2018-01 up to the month before
    ``last_day``'s, then daily zips of that month up to ``last_day``."""
    d_last = pd.Timestamp(last_day).date()
    out = []
    y, m = BINANCE_FROM
    while (y, m) < (d_last.year, d_last.month):
        name = f"BTCUSDT-1h-{y:04d}-{m:02d}.zip"
        a = s_of(f"{y:04d}-{m:02d}-01")
        z = s_of(f"{y + (m == 12):04d}-{m % 12 + 1:02d}-01")
        out.append((f"{y:04d}-{m:02d}", a, z, f"{BINANCE_URL}/monthly/{BINANCE_PATH}/{name}",
                    Path(root) / "spot" / "monthly" / BINANCE_PATH / name))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    d = date(d_last.year, d_last.month, 1)
    while d <= d_last:
        name = f"BTCUSDT-1h-{d.isoformat()}.zip"
        a = s_of(d.isoformat())
        out.append((d.isoformat(), a, a + DAY, f"{BINANCE_URL}/daily/{BINANCE_PATH}/{name}",
                    Path(root) / "spot" / "daily" / BINANCE_PATH / name))
        d += timedelta(days=1)
    return out


def _http(url: str, retries: int = 5, timeout: float = 60.0) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, OSError):
            if attempt == retries - 1:
                raise
        time.sleep(2.0 * (attempt + 1))
    raise RuntimeError("unreachable")


def _checksum_ok(path: Path) -> bool:
    ck = path.with_name(path.name + ".CHECKSUM")
    if not (path.exists() and ck.exists()):
        return False
    want = ck.read_text(encoding="utf-8").split()
    return bool(want) and hashlib.sha256(path.read_bytes()).hexdigest() == want[0].lower()


def _csv_of(path: Path) -> bytes:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{path.name}: {len(names)} CSV files inside")
        return z.read(names[0])


def _to_ms(t: np.ndarray) -> Tuple[np.ndarray, int]:
    """Binance stamps in ms, or in microseconds in the files from 2025 on: detected per row by magnitude."""
    t = np.asarray(t, np.int64)
    us = t > 10**14
    return np.where(us, t // 1000, t), int(us.sum())


def read_klines(path: Path, times_only: bool = False) -> Dict[str, np.ndarray]:
    """One Binance kline zip: open time (ms), OHLC, base volume (BTC), quote volume, trades; ``us`` rows in us."""
    raw = _csv_of(Path(path))
    cols = [0, 6] if times_only else [0, 1, 2, 3, 4, 5, 6, 7, 8]
    df = pd.read_csv(io.BytesIO(raw), header=None, usecols=cols, dtype=str)
    if len(df) and not str(df.iloc[0, 0]).strip().isdigit():         # a header row
        df = df.iloc[1:]
    ot, n_us = _to_ms(df[0].astype(np.int64).to_numpy())
    ct, _ = _to_ms(df[6].astype(np.int64).to_numpy())
    out = {"open_ms": ot, "close_ms": ct, "us_rows": np.asarray(n_us)}
    if not times_only:
        for i, k in ((1, "open"), (2, "high"), (3, "low"), (4, "close"), (5, "volume"), (7, "quote_volume")):
            out[k] = df[i].astype(np.float64).to_numpy()
        out["trades"] = df[8].astype(np.int64).to_numpy()
    return out


def fetch_binance(last_day: str = BINANCE_LAST_DAY, root: Path = BINANCE_DIR, force: bool = False,
                  log=print) -> pd.DataFrame:
    """
    Download every 1h kline zip of BTCUSDT spot from 2018-01 to ``last_day`` with its .CHECKSUM (sha256 verified)
    into ``root`` (the URL's layout), and check each file's times (only the time columns are read): open times
    increasing and inside the file's period, distinct once floored to the hour; counted, not refused: open times off
    the whole hour (after Binance's February 2018 outage) and klines that do not close at the hour's last ms (the hour
    of an outage). Writes and returns the inventory.
    """
    rows = []
    for label, a, z, url, path in _binance_files(last_day, root):
        path.parent.mkdir(parents=True, exist_ok=True)
        ck = path.with_name(path.name + ".CHECKSUM")
        got = "cached"
        if force or not _checksum_ok(path):
            want = _http(url + ".CHECKSUM").decode("utf-8")
            body = _http(url)
            if hashlib.sha256(body).hexdigest() != want.split()[0].lower():
                body = _http(url)
                if hashlib.sha256(body).hexdigest() != want.split()[0].lower():
                    raise IOError(f"{path.name}: sha256 does not match its CHECKSUM")
            part = path.with_name(path.name + ".part")
            part.write_bytes(body)
            part.replace(path)
            ck.write_text(want, encoding="utf-8")
            got = "downloaded"
        if not _checksum_ok(path):
            raise IOError(f"{path.name}: sha256 does not match its CHECKSUM")
        k = read_klines(path, times_only=True)
        ot, ct = k["open_ms"], k["close_ms"]
        hour = (ot // HOUR_MS) * HOUR_MS
        ok = (bool(np.all(np.diff(ot) > 0)) and bool(np.all(np.diff(hour) > 0))
              and bool(np.all((ot >= a * 1000) & (ot < z * 1000))))
        rows.append({"file": path.name, "period": label, "status": got, "sha256_ok": True, "rows": int(len(ot)),
                     "expected_hours": int((z - a) // 3600), "us_rows": int(k["us_rows"]), "times_ok": ok,
                     "off_hour": int((ot % HOUR_MS != 0).sum()), "short_close": int((ct != ot + HOUR_MS - 1).sum()),
                     "first": str(pd.Timestamp(int(ot[0]), unit="ms")) if len(ot) else "",
                     "last": str(pd.Timestamp(int(ot[-1]), unit="ms")) if len(ot) else ""})
        if got == "downloaded":
            log(f"  {path.name}: {len(ot)} hours, {'us' if k['us_rows'] else 'ms'} stamps, times {'ok' if ok else 'BAD'}")
    inv = pd.DataFrame(rows)
    Path(root).mkdir(parents=True, exist_ok=True)
    inv.to_csv(Path(root) / "BTCUSDT_1h_inventory.csv", index=False)
    return inv


def load_binance(end=None, start=None, root: Path = BINANCE_DIR,
                 last_day: str = BINANCE_LAST_DAY) -> Dict[str, np.ndarray]:
    """
    The hourly klines of the hours in [start, end) (``end=None``: the BTC data end once FINALISTS.md is frozen,
    until then the hold-out start). Only the files of that span are opened. ``t``: the UTC hour (s) a kline opens in
    (DEVIATIONS 8: the 43 klines of 9-11 Feb 2018 that open off the whole hour are floored to it); ``off_hour``:
    those klines.
    """
    if end is None:
        end_s = DATA_END_S["BTCUSDm"] if finalists_frozen() else CUT_S
    else:
        end_s = s_of(end)
    a_s = 0 if start is None else s_of(start)
    _guard(end_s, f"Binance klines to {utc(end_s)}")
    parts = []
    for label, a, z, url, path in _binance_files(last_day, root):
        if a >= end_s:
            break
        if z <= a_s:
            continue
        if not path.exists():
            raise FileNotFoundError(f"{path}: run `python -B -m backtesting.research.tradeiq_market fetch-binance`")
        parts.append(read_klines(path))
    if not parts:
        raise FileNotFoundError(f"no Binance klines under {root}")
    k = {key: np.concatenate([p[key] for p in parts]) for key in parts[0] if key != "us_rows"}
    ot = k.pop("open_ms")
    k.pop("close_ms")
    t = (ot // HOUR_MS) * 3600
    k["off_hour"] = ot % HOUR_MS != 0
    order = np.argsort(t, kind="stable")
    t = t[order]
    k = {key: v[order] for key, v in k.items()}
    if len(t) > 1 and not bool(np.all(np.diff(t) > 0)):
        raise ValueError("Binance klines: two klines in one hour")
    keep = (t >= a_s) & (t + 3600 <= end_s)
    return {"t": t[keep], **{key: v[keep] for key, v in k.items()}}


def binance_volume(mk: TMarket, tf: str, root: Path = BINANCE_DIR) -> Tuple[np.ndarray, np.ndarray]:
    """
    BTCUSDT spot volume (BTC) on ``mk.tbars(tf)`` and, per bar, the number of its 1H bars without a Binance kline
    (their volume is 0: no trade took place on Binance in that hour). Aligned on our 1H bars by UTC open time; 4H and
    1D are the sums over the 1H bars inside each bar.
    """
    if not mk.symbol.startswith("BTC"):
        raise ValueError("the Binance volume is for BTC only")
    h1 = mk.tbars("1H")
    if mk._binance is None:
        mk._binance = load_binance(end=mk.end_s, start=(int(mk.t[0]) // 3600) * 3600, root=root)
    kl = mk._binance
    j = np.searchsorted(kl["t"], h1.t)
    jj = np.minimum(j, len(kl["t"]) - 1)
    hit = (j < len(kl["t"])) & (kl["t"][jj] == h1.t)
    v1 = np.where(hit, kl["volume"][jj], 0.0)
    miss1 = (~hit).astype(np.int64)
    if tf == "1H":
        return v1, miss1
    hb = mk.tbars(tf)
    own = np.searchsorted(hb.i0, h1.i0, side="right") - 1
    oo = np.maximum(own, 0)
    inside = (own >= 0) & (h1.i1 <= hb.i1[oo])
    straddle = (own >= 0) & (h1.i0 <= hb.i1[oo]) & (h1.i1 > hb.i1[oo])
    if straddle.any():
        raise AssertionError(f"{tf}: a 1H bar straddles a {tf} bar boundary")
    vol = np.bincount(own[inside], weights=v1[inside], minlength=len(hb))
    miss = np.bincount(own[inside], weights=miss1[inside], minlength=len(hb)).astype(np.int64)
    return vol, miss


def binance_check(mk: TMarket, root: Path = BINANCE_DIR) -> Dict[str, object]:
    """
    PREREG 2's check of the Binance volume on the span ``mk`` holds: bar times, gaps, and the correlation of Binance
    and Exness 1H closes (levels; also log returns at lags -2..2 h, the best of which must be lag 0).
    """
    h1 = mk.tbars("1H")
    kl = load_binance(end=mk.end_s, start=(int(mk.t[0]) // 3600) * 3600, root=root)
    a = max(int(kl["t"][0]), int(h1.t[0]))
    t = kl["t"]
    gaps = []
    d = np.diff(t)
    for i in np.flatnonzero(d != 3600):
        gaps.append({"after": str(utc(t[i])), "before": str(utc(t[i + 1])), "missing_hours": int(d[i] // 3600 - 1)})
    j = np.searchsorted(t, h1.t)
    jj = np.minimum(j, len(t) - 1)
    hit = (j < len(t)) & (t[jj] == h1.t)
    in_span = h1.t >= a
    ours_missing = h1.t[in_span & ~hit]
    theirs = np.isin(t, h1.t)
    e_c, b_c = h1.c[hit], kl["close"][jj[hit]]
    corr = float(np.corrcoef(e_c, b_c)[0, 1])
    years = pd.to_datetime(h1.t[hit], unit="s").year
    per_year = {int(y): float(np.corrcoef(e_c[years == y], b_c[years == y])[0, 1]) for y in np.unique(years)}
    # log returns on the regular hourly grid (NaN where either side has no hour), Exness at t against Binance at t - L
    g0 = min(int(t[0]), int(h1.t[0]))
    n_g = (max(int(t[-1]), int(h1.t[-1])) - g0) // 3600 + 1
    E = np.full(n_g, np.nan)
    Bn = np.full(n_g, np.nan)
    E[(h1.t - g0) // 3600] = h1.c
    Bn[(t - g0) // 3600] = kl["close"]
    re, rb = np.diff(np.log(E)), np.diff(np.log(Bn))
    lags = {}
    for L in (-2, -1, 0, 1, 2):
        x, y = (re[L:], rb[:len(rb) - L]) if L >= 0 else (re[:L], rb[-L:])
        ok = np.isfinite(x) & np.isfinite(y)
        lags[L] = float(np.corrcoef(x[ok], y[ok])[0, 1])
    rel = np.abs(b_c / e_c - 1.0)
    out = {
        "span": f"{utc(h1.t[0])} .. {utc(mk.end_s)}",
        "binance_hours": int(len(t)), "exness_1h_bars": int(len(h1)), "matched": int(hit.sum()),
        "exness_bars_without_kline": int(len(ours_missing)),
        "exness_bars_without_kline_list": [str(utc(x)) for x in ours_missing[:200]],
        "klines_outside_exness_bars": int((~theirs).sum()),
        "binance_gaps": gaps,
        "klines_off_the_hour": int(kl["off_hour"].sum()),
        "klines_off_the_hour_span": (f"{utc(t[kl['off_hour']][0])} .. {utc(t[kl['off_hour']][-1])}"
                                     if kl["off_hour"].any() else ""),
        "times_increasing": bool(np.all(d > 0)),
        "corr_close": corr, "corr_close_by_year": per_year,
        "corr_logret_by_lag_h": lags, "best_lag_h": int(max(lags, key=lags.get)),
        "median_abs_rel_diff": float(np.median(rel)), "p99_abs_rel_diff": float(np.quantile(rel, 0.99)),
    }
    out["passes"] = bool(out["corr_close"] > 0.999 and out["best_lag_h"] == 0 and out["times_increasing"])
    return out


# ───────────────────────────── command line ─────────────────────────────

def _rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if r > 1e7 else r / 1e3          # bytes on macOS, kB on Linux


def profile(symbol: str, log=print) -> Dict[str, float]:
    """Time and memory to load one symbol and run one variant (a placeholder state, not one of the study's rules; no
    result is printed)."""
    out = {}
    t0 = time.time()
    mk = load(symbol)
    out["load_s"] = time.time() - t0
    out["m1_bars"] = len(mk)
    out["market_mb"] = mk.nbytes() / 1e6
    out["rss_after_load_mb"] = _rss_mb()
    t0 = time.time()
    bars = {tf: mk.tbars(tf) for tf in TFS}
    out["bars_s"] = time.time() - t0
    b = bars["1H"]
    rng = np.random.default_rng(20261128)
    flips = np.cumsum(rng.random(len(b)) < 0.05)
    state = np.where(flips % 3 == 0, 1, np.where(flips % 3 == 1, -1, 0))       # a placeholder, not a study rule
    stop = s1_stop(b)
    a, z = window("dev", symbol)
    t0 = time.time()
    run(mk, b, state, a, z, stop=stop, cost=1.0)
    out["first_run_s_with_compile"] = time.time() - t0
    t0 = time.time()
    r1 = run(mk, b, state, a, z, stop=stop, cost=1.0)
    r15 = run(mk, b, state, a, z, stop=stop, cost=1.5)
    out["run_1h_dev_x1_and_x15_s"] = time.time() - t0
    t0 = time.time()
    metrics(r1)
    metrics(r15)
    out["metrics_x2_s"] = time.time() - t0
    t0 = time.time()
    account_curve(r1)
    out["account_curve_s"] = time.time() - t0
    out["trades_in_run"] = int(len(r1.trades))
    out["rss_peak_mb"] = _rss_mb()
    return out


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.tradeiq_market")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch-binance", help="download and verify the Binance BTCUSDT 1h klines")
    f.add_argument("--last-day", default=BINANCE_LAST_DAY)
    f.add_argument("--force", action="store_true")
    sub.add_parser("check-binance", help="PREREG 2's check of the Binance volume on the open span")
    p = sub.add_parser("profile", help="time and memory of loading one symbol and running one variant")
    p.add_argument("symbol", choices=SYMBOLS)
    args = ap.parse_args(argv)
    if args.cmd == "fetch-binance":
        inv = fetch_binance(args.last_day, force=args.force)
        print(inv.groupby("status").size().to_string())
        print(f"{len(inv)} files, {int(inv.rows.sum())} hours, {int((inv.us_rows > 0).sum())} files with us stamps "
              f"(first {inv.loc[inv.us_rows > 0, 'period'].min() if (inv.us_rows > 0).any() else '-'}), "
              f"times ok in all: {bool(inv.times_ok.all())}, hours short of the calendar: "
              f"{int((inv.expected_hours - inv.rows).sum())}")
    elif args.cmd == "check-binance":
        mk = load("BTCUSDm")
        print(json.dumps(binance_check(mk), indent=1, default=str))
    elif args.cmd == "profile":
        print(json.dumps(profile(args.symbol), indent=1))


if __name__ == "__main__":
    main()
