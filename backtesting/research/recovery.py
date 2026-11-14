"""
Loss-recovery and position-management mechanisms, compared on identical entries.

    python -m backtesting.research.recovery run    [--symbols XAUUSDm BTCUSDm] [--periods DEV CONFIRM] [--cache DIR]
    python -m backtesting.research.recovery tables [--update backtest_results/improve/recovery_mechanisms.md]

``run`` writes ``backtest_results/improve/recovery_mechanisms.csv`` (one row per symbol, period, entry
list and mechanism), ``recovery_mechanisms_halfyears.csv`` (the same by half-year) and
``recovery_mechanisms_gaps.csv`` (price jumps over market closures); ``tables`` prints them as
markdown, or refreshes the tables of the report in place. The report itself is
``backtest_results/improve/recovery_mechanisms.md``.

The question
------------
The live bot averages down with a Fibonacci ladder and has no stop. What else can be done with a
position that goes wrong, and what does each choice do to the result? Every mechanism below is applied
to the SAME list of entry times and directions, so the differences between rows are differences
between mechanisms and nothing else.

The model
---------
* Prices are M1 bid bars; ``ask = bid + the bar's mean spread``. A buy is filled at the ask, a sell at
  the bid. P/L in USD = price difference x units x USD per 1.00 of price (one unit = 0.01 lot: 1.00
  for gold, 0.01 for BTC). Nothing is rounded.
* An entry is made at the close of an M15 bar. From the next M1 bar on the price is taken to run
  open -> unfavourable extreme -> favourable extreme -> close, so a stop is always met before a
  target of the same bar. A level the open has already passed is filled at the open (gaps count).
  The true order inside a bar is not known, so ``run`` repeats everything with the two other
  readings (favourable extreme first; the shortest path through the bar) and stores those
  expectancies next to the result: a conclusion that changes with the reading is not a conclusion.
* Rules that need an indicator (ladder tiers, signal-released adds, the unlock of a hedge) are
  evaluated at the close of an M1 bar and filled at that close.
* Every quantity used at the close of a bar is computed from bars that had closed by then: a slower
  timeframe is read from its last closed bar, or, for the RSI the live ladder reads, from its forming
  bar with the current M1 close as its provisional close (which is what the live bot does).
  ``tests/test_recovery_sim.py`` checks this by truncating the history.
* Distances are multiples of the H1 ATR(14) of the last closed H1 bar at the entry, so a mechanism has
  the same shape on both symbols and in calm and wild markets. ``R`` in the tables is the value of one
  such ATR on one unit.

Periods
-------
Each period is self-contained: its first month only warms the indicators up, and a basket still open
when the period ends is closed at the last bar. DEV is where everything here was defined; CONFIRM is
run once, unchanged, to see whether the picture holds.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..analysis.signal import live_indicator, votes
from ..config import DATA_HOLE_QUARANTINE_S, REPO_ROOT, SYMBOLS, load_live_constants
from ..data import store

OUT = REPO_ROOT / "backtest_results" / "improve"

# load from / first entry / end (exclusive), all 00:00 UTC
PERIODS: Dict[str, Tuple[str, str, str]] = {
    "DEV": ("2025-07-01", "2025-08-01", "2026-11-13"),
    "CONFIRM": ("2024-01-01", "2024-02-01", "2025-07-01"),
}
LISTS: Dict[str, str] = {
    "trend": "votes agree, with the H1 trend",
    "votes": "votes agree, no trend filter",
    "random": "random time and direction",
}
ACCOUNT = 2000.0                 # the account the sequence of baskets is replayed on, USD
ATR_LENGTH = 14
LADDER_TFS = (60, 300, 900, 3600, 14400)       # the live ladder's tiers: M1, M5, M15, H1, H4
RANDOM_SEED = 20260101
RANDOM_ENTRY_PROB = 0.5          # chance that a flat random trader enters at an M15 close
LIVENESS_S = 180                 # an order needs a quote within three minutes (the bot's own rule)
OVERSHOOT_USD = 0.01             # a basket counts as "beyond its budget" when it lost this much more than the budget


def usd_per_point(symbol: str) -> float:
    """USD of P/L per 1.00 of price on one unit (0.01 lot)."""
    return SYMBOLS[symbol].contract_size * 0.01


# ───────────────────────────── what is known at each M1 close ─────────────────────────────

@dataclass
class Frame:
    """
    M1 bars and, for every bar, what a trader knows at its close.

    ``o h l c`` are bid prices, ``sp`` the spread used for the bar. ``atr`` and ``trend`` come from
    the last closed H1 bar; ``rsi[i]`` is the RSI of the forming bar of ladder tier ``i``; ``ev`` holds
    the events of closed M5 / M15 bars (rows: M5 MACD histogram turn, M15 turn, M5 RSI leaving
    oversold / overbought, M15 the same; +1 favours longs, -1 shorts); ``vote`` is +1 / -1 where an
    M15 bar closes with both of the bot's votes agreeing. ``session`` is a calendar, known in advance,
    for a market that closes: 2 from Friday 20:30 UTC to Monday 00:00 (the weekend), 1 from 20:30 to
    23:05 UTC on the other days (around the daily break), else 0; always 0 for a market that never
    closes. ``live`` and ``hole`` look at the TIME of the next bar only: an order needs an open
    market, and a silence of hours in a market that never closes is missing history.
    """
    symbol: str
    k: float
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sp: np.ndarray
    atr: np.ndarray
    trend: np.ndarray
    rsi: np.ndarray
    ev: np.ndarray
    vote: np.ndarray
    m15_close: np.ndarray
    session: np.ndarray
    live: np.ndarray
    hole: np.ndarray
    ok: np.ndarray               # an entry may be made at this close (indicators warm, market open, no recent hole)

    def __len__(self) -> int:
        return int(len(self.t))

    @classmethod
    def synthetic(cls, o, h, l, c, spread=0.0, atr=1.0, k: float = 1.0, symbol: str = "TEST", **features) -> "Frame":
        """A frame from hand-made bars (tests, worked examples). Features default to "nothing happens"."""
        o, h, l, c = (np.asarray(x, np.float64) for x in (o, h, l, c))
        n = len(c)

        def arr(v, dtype):
            return np.array(np.broadcast_to(np.asarray(v, dtype), (n,)))

        f = dict(
            t=np.arange(n, dtype=np.int64) * 60, sp=arr(spread, np.float64), atr=arr(atr, np.float64),
            trend=np.zeros(n, np.int8), rsi=np.full((len(LADDER_TFS), n), 50.0), ev=np.zeros((4, n), np.int8),
            vote=np.zeros(n, np.int8), m15_close=np.ones(n, bool), session=np.zeros(n, np.int8), live=np.ones(n, bool),
            hole=np.zeros(n, bool), ok=np.ones(n, bool),
        )
        for name, v in features.items():
            f[name] = np.array(np.broadcast_to(np.asarray(v, f[name].dtype), f[name].shape))
        return cls(symbol=symbol, k=float(k), o=o, h=h, l=l, c=c, **f)


@njit(cache=True)
def _wilder(x: np.ndarray, length: int) -> np.ndarray:
    """Wilder's average (RMA) seeded with the mean of the first ``length`` values, as ``indicator.py`` seeds it."""
    n = x.shape[0]
    out = np.full(n, np.nan)
    if n < length:
        return out
    acc = 0.0
    for i in range(length):
        acc += x[i]
    out[length - 1] = acc / length
    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + x[i]) / length
    return out


def wilder_gain_loss(close: np.ndarray, length: int) -> Tuple[np.ndarray, np.ndarray]:
    """The two averages behind RSI at every closed bar (NaN until the seed is complete)."""
    d = np.diff(np.asarray(close, np.float64))
    ag = np.concatenate([[np.nan], _wilder(np.maximum(d, 0.0), length)])
    al = np.concatenate([[np.nan], _wilder(np.maximum(-d, 0.0), length)])
    return ag, al


def rsi_from(ag: np.ndarray, al: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - 100.0 / (1.0 + ag / al)
    return np.where(al == 0.0, 100.0, r)


def forming_rsi(price: np.ndarray, bar_of: np.ndarray, close: np.ndarray, ag: np.ndarray, al: np.ndarray,
                length: int) -> np.ndarray:
    """
    RSI of a still-forming bar: the averages of the last CLOSED bar advanced by one step to ``price``.
    ``bar_of[j]`` is the index of the slower bar that holds M1 bar ``j``; only bars before it are read.
    """
    p = bar_of - 1
    ok = p >= 0
    pc = np.where(ok, p, 0)
    d = price - close[pc]
    g = (ag[pc] * (length - 1) + np.maximum(d, 0.0)) / length
    ls = (al[pc] * (length - 1) + np.maximum(-d, 0.0)) / length
    return np.where(ok, rsi_from(g, ls), np.nan)


def wilder_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, length: int = ATR_LENGTH) -> np.ndarray:
    h, l, c = (np.asarray(x, np.float64) for x in (h, l, c))
    prev = np.concatenate([[c[0]], c[:-1]]) if len(c) else c
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    if len(tr):
        tr[0] = h[0] - l[0]
    return _wilder(tr, length)


FLAT_FROM_MIN = 20 * 60 + 30         # 20:30 UTC: half an hour before gold's earliest daily and weekly close
FLAT_UNTIL_MIN = 23 * 60 + 5         # 23:05 UTC: just after its latest reopening


def session_calendar(time_s: np.ndarray) -> np.ndarray:
    """
    Where a market with closures is about to close, closed, or just reopening, by the clock alone:
    2 = the weekend (Friday 20:30 UTC to Monday 00:00), 1 = the daily break (20:30 to 23:05 UTC), 0 = neither.
    """
    time_s = np.asarray(time_s, np.int64)
    dow = (time_s // 86400 + 3) % 7                      # 0 = Monday
    minute = (time_s % 86400) // 60
    weekend = (dow >= 5) | ((dow == 4) & (minute >= FLAT_FROM_MIN))
    daily = (minute >= FLAT_FROM_MIN) & (minute < FLAT_UNTIL_MIN)
    return np.where(weekend, 2, np.where(daily, 1, 0)).astype(np.int8)


def has_closures(symbol: str) -> bool:
    """True for an instrument with real closures (gold); False for one that trades around the clock (BTC)."""
    return symbol in SYMBOLS and SYMBOLS[symbol].data_hole_s == 0


def _m1_index_of_close(t: np.ndarray, close_time: np.ndarray) -> np.ndarray:
    """Index of the M1 bar that ends exactly at ``close_time`` (-1 where the market had no quote in that minute)."""
    j = np.searchsorted(t, close_time - 60)
    hit = (j < len(t)) & (t[np.minimum(j, len(t) - 1)] == close_time - 60)
    return np.where(hit, j, -1)


def build_frame(symbol: str, m1: Dict[str, np.ndarray], live_root: Path = REPO_ROOT) -> Frame:
    """
    Everything the mechanisms read, for every M1 bar, from the M1 bars alone. A pure function of the
    bars given: the value at bar ``j`` depends on bars ``0..j`` only (``live`` and ``hole`` also on the
    time of bar ``j + 1``).
    """
    t = np.asarray(m1["t"], np.int64)
    n = len(t)
    c = np.asarray(m1["c"], np.float64)
    close_t = t + 60
    cst = load_live_constants(live_root)
    ind = live_indicator(live_root)
    bars = {60: m1}
    for tf in (300, 900, 3600, 14400):
        bars[tf] = store.resample_bars(m1, tf)

    rsi = np.full((len(LADDER_TFS), n), np.nan)
    for i, tf in enumerate(LADDER_TFS):
        bc = np.asarray(bars[tf]["c"], np.float64)
        ag, al = wilder_gain_loss(bc, int(cst.RSI_LENGTH))
        bar_of = np.searchsorted(np.asarray(bars[tf]["t"], np.int64), t, side="right") - 1
        rsi[i] = forming_rsi(c, bar_of, bc, ag, al, int(cst.RSI_LENGTH))

    h1 = bars[3600]
    sig = ind.calculate_macd(pd.Series(np.asarray(h1["c"], np.float64)), fast=cst.MACD_FAST, slow=cst.MACD_SLOW,
                             signal=cst.MACD_SIGNAL)["signal"].to_numpy(float)
    atr_h1 = wilder_atr(h1["h"], h1["l"], h1["c"])
    closed = np.searchsorted(np.asarray(h1["t"], np.int64) + 3600, close_t, side="right") - 1   # last H1 bar closed by now
    has = closed >= 0
    pick = np.where(has, closed, 0)
    atr = np.where(has, atr_h1[pick], np.nan)
    s = np.where(has, sig[pick], np.nan)
    trend = np.where(np.isfinite(s), np.sign(s), 0.0).astype(np.int8)

    m15 = bars[900]
    v = votes(pd.Series(np.asarray(m15["c"], np.float64)), live_root)
    agree = np.where((v["macd"] == 1) & (v["rsi"] == 1), 1, np.where((v["macd"] == -1) & (v["rsi"] == -1), -1, 0))
    vote = np.zeros(n, np.int8)
    m15_close = np.zeros(n, bool)
    j15 = _m1_index_of_close(t, np.asarray(m15["t"], np.int64) + 900)
    vote[j15[j15 >= 0]] = agree[j15 >= 0]
    m15_close[j15[j15 >= 0]] = True

    ev = np.zeros((4, n), np.int8)
    for i, tf in enumerate((300, 900)):
        cs = pd.Series(np.asarray(bars[tf]["c"], np.float64))
        hist = ind.calculate_macd(cs, fast=cst.MACD_FAST, slow=cst.MACD_SLOW, signal=cst.MACD_SIGNAL)["hist"].to_numpy(float)
        r = rsi_from(*wilder_gain_loss(cs.to_numpy(), int(cst.RSI_LENGTH)))
        turn = np.zeros(len(hist), np.int8)
        cross = np.zeros(len(hist), np.int8)
        with np.errstate(invalid="ignore"):
            turn[2:][(hist[2:] > hist[1:-1]) & (hist[1:-1] <= hist[:-2])] = 1
            turn[2:][(hist[2:] < hist[1:-1]) & (hist[1:-1] >= hist[:-2])] = -1
            cross[1:][(r[:-1] <= cst.RSI_OVERSOLD) & (r[1:] > cst.RSI_OVERSOLD)] = 1
            cross[1:][(r[:-1] >= cst.RSI_OVERBOUGHT) & (r[1:] < cst.RSI_OVERBOUGHT)] = -1
        jj = _m1_index_of_close(t, np.asarray(bars[tf]["t"], np.int64) + tf)
        ev[i][jj[jj >= 0]] = turn[jj >= 0]
        ev[2 + i][jj[jj >= 0]] = cross[jj >= 0]

    session = session_calendar(close_t) if has_closures(symbol) else np.zeros(n, np.int8)
    gap = np.diff(t, append=t[-1] if n else 0)            # seconds to the next bar; 0 at the last one (unknown)
    live = (gap > 0) & (gap <= LIVENESS_S)
    hole_s = SYMBOLS[symbol].data_hole_s if symbol in SYMBOLS else 0.0
    hole = (gap >= hole_s) if hole_s > 0 else np.zeros(n, bool)
    resumed = np.zeros(n, np.int64)                       # time the history last resumed after a hole
    if n > 1:
        resumed[1:] = np.where(hole[:-1], t[1:], 0)
    resumed = np.maximum.accumulate(resumed)
    quarantined = (resumed > 0) & (t - resumed < DATA_HOLE_QUARANTINE_S)
    ok = live & ~quarantined & np.isfinite(atr) & (atr > 0) & np.isfinite(rsi).all(axis=0)

    return Frame(symbol=symbol, k=usd_per_point(symbol) if symbol in SYMBOLS else 1.0, t=t,
                 o=np.asarray(m1["o"], np.float64), h=np.asarray(m1["h"], np.float64), l=np.asarray(m1["l"], np.float64),
                 c=c, sp=np.asarray(m1["spread_mean"], np.float64), atr=atr, trend=trend, rsi=np.ascontiguousarray(rsi),
                 ev=ev, vote=vote, m15_close=m15_close, session=session, live=live, hole=hole, ok=ok)


def load_frame(symbol: str, period: str, cache_dir: Optional[Path] = None,
               store_dir: Path = store.DEFAULT_STORE_DIR) -> Tuple[Frame, int]:
    """
    The frame of a period and the time (epoch s) from which entries are allowed. With ``cache_dir`` the
    frame is stored there and read back on the next call, whatever has changed since: empty the
    directory after changing this module or the tick store.
    """
    load, first, end = PERIODS[period]
    first_s = store.to_ms(first) // 1000
    path = Path(cache_dir) / f"recovery_frame_{symbol}_{period}.npz" if cache_dir else None
    if path is not None and path.exists():
        with np.load(path) as z:
            return Frame(symbol=symbol, k=usd_per_point(symbol), **{name: z[name] for name in z.files}), first_s
    m1 = store.load_m1(symbol, store.to_ms(load), store.to_ms(end), store_dir)
    if not m1 or len(m1["t"]) == 0:
        raise FileNotFoundError(f"no M1 bars for {symbol} in {load} .. {end}")
    frame = build_frame(symbol, m1)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **{name: getattr(frame, name) for name in frame.__dataclass_fields__ if name not in ("symbol", "k")})
    return frame, first_s


def months_available(symbol: str, period: str, store_dir: Path = store.DEFAULT_STORE_DIR) -> bool:
    """True when every month of the period is in the tick store."""
    load, _, end = PERIODS[period]
    have = set(store.available_months(symbol, store_dir))
    a, z = pd.Timestamp(load), pd.Timestamp(end) - pd.Timedelta(seconds=1)
    return all((p.year, p.month) in have for p in pd.period_range(a, z, freq="M"))


# ───────────────────────────── the basket simulator ─────────────────────────────
#
# One basket = everything opened from one entry until all of it is closed. Three kernels share the
# conventions of the module docstring:
#
#   _run_directional   positions on one side: fixed and trailing stops, targets, adds against or with
#                      the move, the live RSI ladder, scale-out, stop-and-reverse
#   _run_lock          a hedge lock and the close-and-re-enter sequence it is equivalent to
#   _run_zone          zone recovery: alternating, growing opposite positions
#
# Inside a kernel prices are seen from the basket's own side: ``y`` is the price at which the basket
# could be closed right now (the bid for a long basket, minus the ask for a short one), so "up" is
# always good and the price paid to add is always ``y + spread``. Each kernel returns
# (P/L, worst floating P/L, bar of the close, largest position, units opened, spread paid, adds, reason).

P_FAMILY = 0            # 0 directional, 1 lock, 2 zone
P_STOP_ATR = 1          # price stop, ATR below the first fill (0 = none)
P_TGT_ATR = 2           # price target, ATR above the first fill (0 = none)
P_TGT_AVG_ATR = 3       # target this many ATR above the AVERAGE entry (0 = none)
P_TGT_USD = 4           # basket target in USD (0 = none)
P_STOP_USD = 5          # basket stop in USD (0 = none)
P_STOP_BUDGET_ATR = 6   # basket stop in USD = this many ATR on one unit (0 = none); with P_STOP_USD the smaller applies
P_ADD_MODE = 7          # 0 none, 1 price level against the basket, 2 price level in its favour, 3 RSI tiers, 4 signal event
P_ADD_MAX = 8           # number of adds allowed
P_ADD_STEP_ATR = 9      # level spacing (modes 1, 2); least adverse distance from the last fill (mode 4)
P_ADD_SIGNAL = 10       # mode 4: row of Frame.ev that releases an add
P_RSI_OS = 11           # mode 3: a long basket adds at or below this RSI
P_RSI_OB = 12           # mode 3: a short basket adds at or above this RSI
P_TRAIL_ATR = 13        # trailing stop distance behind the best price (0 = none)
P_TRAIL_FROM_START = 14  # 1 = the stop trails from the entry on, 0 = only after the scale-out
P_BE_TRIG_ATR = 15      # move the stop to the entry price after this favourable move (0 = never)
P_SCALE_ATR = 16        # close P_SCALE_FRAC of the basket after this favourable move (0 = never)
P_SCALE_FRAC = 17
P_REV_MAX = 18          # stop-and-reverse: number of reversals allowed
P_REV_MULT = 19         # size of a reversed position relative to the one it replaces
P_LOCK_MODE = 20        # 1 hedge lock, unlocked by a vote signal; 2 close, re-enter on that signal; 3 hedge lock, both legs closed later
P_LOCK_BARS = 21        # mode 3: M1 bars the lock is held
P_STOP2_ATR = 22        # stop of the leg kept after the unlock / of the re-entry
P_TGT2_ATR = 23         # its target
P_ZONE_ATR = 24         # zone recovery: distance between the two edges
P_ZONE_LEGS = 25        # zone recovery: positions allowed, the first included
P_FLAT = 26             # 1 = flat over the weekend, 2 = flat over every closure (Frame.session): none opened, an open one closed
P_PATH = 27             # order inside a bar: 0 unfavourable extreme first (the result), 1 favourable first, 2 shortest path
N_PARAMS = 28

PATH_UNFAVOURABLE_FIRST, PATH_FAVOURABLE_FIRST, PATH_SHORTEST = 0, 1, 2
OTHER_READINGS = {"favourable_first": PATH_FAVOURABLE_FIRST, "shortest_path": PATH_SHORTEST}

R_TARGET, R_STOP, R_BUDGET, R_END, R_MAX_LEGS, R_UNLOCK, R_CLOSURE, R_NOT_TAKEN = 1, 2, 3, 4, 5, 6, 7, 8
REASONS = {R_TARGET: "target", R_STOP: "stop", R_BUDGET: "budget", R_END: "end", R_MAX_LEGS: "max_legs", R_UNLOCK: "unlock",
           R_CLOSURE: "closure", R_NOT_TAKEN: "not_taken"}
_GUARD = 200            # events allowed inside one bar segment


@njit(cache=True)
def _dist_down(level: float, ya: float, yb: float) -> float:
    """How far along the move ya -> yb a "price at or below level" event happens (0 = already true, -1 = not on this move)."""
    if level >= ya:
        return 0.0
    if yb < ya and level >= yb:
        return ya - level
    return -1.0


@njit(cache=True)
def _dist_up(level: float, ya: float, yb: float) -> float:
    if level <= ya:
        return 0.0
    if yb > ya and level <= yb:
        return level - ya
    return -1.0


@njit(cache=True)
def _low_first(path, long_exposure, o, c):
    """Whether the low of a bar is taken before its high, for a basket that currently gains when the price rises (or not)."""
    if path == PATH_SHORTEST:
        return c >= o                   # a bar that closes up dipped first; one that closes down rose first
    if path == PATH_FAVOURABLE_FIRST:
        return not long_exposure
    return long_exposure


@njit(cache=True)
def _fits_budget(realized, units, cost_sum, y, u, s, k, budget):
    """True when ``u`` more units, bought now and paying the spread at once, leave the basket inside its budget."""
    return realized + k * (units * y - cost_sum) - k * u * s > -budget


@njit(cache=True)
def _run_directional(e, d0, P, mult, o, h, l, c, sp, atr, rsi, ev, session, hole, k):
    n = c.shape[0]
    A = atr[e]
    path = int(P[P_PATH])
    flat_from = 3 - int(P[P_FLAT]) if P[P_FLAT] > 0.0 else 99       # the lowest Frame.session value that must be flat
    if session[e] >= flat_from:
        return 0.0, 0.0, e, 0.0, 0.0, 0.0, 0, R_NOT_TAKEN
    stop_atr, tgt_atr, tgt_avg, tgt_usd = P[P_STOP_ATR], P[P_TGT_ATR], P[P_TGT_AVG_ATR] * A, P[P_TGT_USD]
    budget = np.inf
    if P[P_STOP_USD] > 0.0:
        budget = P[P_STOP_USD]
    if P[P_STOP_BUDGET_ATR] > 0.0:
        budget = min(budget, P[P_STOP_BUDGET_ATR] * A * k)
    add_mode, add_max, step, sig = int(P[P_ADD_MODE]), int(P[P_ADD_MAX]), P[P_ADD_STEP_ATR] * A, int(P[P_ADD_SIGNAL])
    trail = P[P_TRAIL_ATR] * A
    trail_on = trail > 0.0 and P[P_TRAIL_FROM_START] > 0.0
    be_at, scale_at, frac = P[P_BE_TRIG_ATR] * A, P[P_SCALE_ATR] * A, P[P_SCALE_FRAC]
    rev_max, rev_mult = int(P[P_REV_MAX]), P[P_REV_MULT]

    d = int(d0)
    s = sp[e]
    y = c[e] if d == 1 else -(c[e] + s)
    first = y + s                       # price paid by the first fill
    base = 1.0
    units, cost_sum, last, n_adds = base, base * first, first, 0     # cost_sum = sum(units x price paid)
    realized, spread_paid, volume, max_units = 0.0, 0.5 * s * k * base, base, base
    stop_y = first - stop_atr * A if stop_atr > 0.0 else -np.inf
    tgt_y = first + tgt_atr * A if tgt_atr > 0.0 else np.inf
    best = y
    be_done, scaled, revs = be_at <= 0.0, scale_at <= 0.0, 0
    mae = k * (units * y - cost_sum)
    reason, j = 0, e
    while True:
        # ── the close of bar j: adds released by an indicator ──
        s = sp[j]
        y = c[j] if d == 1 else -(c[j] + s)
        if add_mode == 3:
            while n_adds < add_max:
                r = rsi[n_adds, j]
                if (d == 1 and r <= P[P_RSI_OS]) or (d == -1 and r >= P[P_RSI_OB]):
                    u = mult[n_adds + 1]
                    if not _fits_budget(realized, units, cost_sum, y, u, s, k, budget):
                        add_max = n_adds          # the budget cannot carry another add: the ladder ends here
                        break
                    units += u
                    cost_sum += u * (y + s)
                    last = y + s
                    n_adds += 1
                    volume += u
                    spread_paid += 0.5 * s * k * u
                else:
                    break
        elif add_mode == 4:
            if n_adds < add_max and ev[sig, j] == d and y + s <= last - step:
                u = mult[n_adds + 1]
                if _fits_budget(realized, units, cost_sum, y, u, s, k, budget):
                    units += u
                    cost_sum += u * (y + s)
                    last = y + s
                    n_adds += 1
                    volume += u
                    spread_paid += 0.5 * s * k * u
                else:
                    add_max = n_adds
        max_units = max(max_units, units)
        mae = min(mae, realized + k * (units * y - cost_sum))
        if j == n - 1 or hole[j] or session[j] >= flat_from:
            # the history ends here or goes silent, or the market is about to close: out at this quote
            realized += k * (units * y - cost_sum)
            spread_paid += 0.5 * s * k * units
            reason = R_CLOSURE if session[j] >= flat_from else R_END
            break

        # ── bar j + 1: open -> unfavourable extreme -> favourable extreme -> close ──
        j += 1
        s = sp[j]
        x1, x2 = (l[j], h[j]) if _low_first(path, d == 1, o[j], c[j]) else (h[j], l[j])
        closed = False
        for seg in range(3):
            if seg == 0:
                a, b = o[j], x1
            elif seg == 1:
                a, b = x1, x2
            else:
                a, b = x2, c[j]
            yb = 0.0
            for _ in range(_GUARD):
                ya = a if d == 1 else -(a + s)
                yb = b if d == 1 else -(b + s)
                best = max(best, ya)
                if trail_on:
                    stop_y = max(stop_y, best - trail)
                avg = cost_sum / units
                kind, dist, sgn = 0, np.inf, 0.0
                # stops first, so that a stop and anything else at the same price resolve to the stop
                x = _dist_down(stop_y, ya, yb)
                if 0.0 <= x < dist:
                    kind, dist, sgn = 1, x, -1.0
                if budget < np.inf:
                    x = _dist_down(avg - (budget + realized) / (k * units), ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 2, x, -1.0
                x = _dist_up(tgt_y, ya, yb)
                if 0.0 <= x < dist:
                    kind, dist, sgn = 3, x, 1.0
                if tgt_avg > 0.0:
                    x = _dist_up(avg + tgt_avg, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 3, x, 1.0
                if tgt_usd > 0.0:
                    x = _dist_up(avg + (tgt_usd - realized) / (k * units), ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 3, x, 1.0
                if not be_done:
                    x = _dist_up(first + be_at, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 4, x, 1.0
                if not scaled:
                    x = _dist_up(first + scale_at, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 5, x, 1.0
                if add_mode == 1 and n_adds < add_max:
                    x = _dist_down(first - (n_adds + 1) * step - s, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 6, x, -1.0
                if add_mode == 2 and n_adds < add_max:
                    x = _dist_up(first + (n_adds + 1) * step - s, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 6, x, 1.0
                if kind == 0:
                    break
                yh = ya + sgn * dist                  # where on the move it happens
                if kind <= 3:                         # stop, budget or target: everything is closed here
                    realized += k * (units * yh - cost_sum)
                    spread_paid += 0.5 * s * k * units
                    if kind == 1 and revs < rev_max:  # stop and reverse: the opposite position, opened at the same quote
                        xr = yh if d == 1 else -yh - s
                        d = -d
                        revs += 1
                        base *= rev_mult
                        y = xr if d == 1 else -(xr + s)
                        first = y + s
                        units, cost_sum, last, n_adds = base, base * first, first, 0
                        stop_y = first - stop_atr * A
                        tgt_y = first + tgt_atr * A if tgt_atr > 0.0 else np.inf
                        best = y
                        volume += base
                        spread_paid += 0.5 * s * k * base
                        max_units = max(max_units, base)
                        mae = min(mae, realized + k * (units * y - cost_sum))
                        a = xr
                        continue
                    units, cost_sum = 0.0, 0.0
                    mae = min(mae, realized)
                    reason = R_TARGET if kind == 3 else (R_STOP if kind == 1 else R_BUDGET)
                    closed = True
                    break
                if kind == 4:                         # break-even: the stop moves to the price paid
                    be_done = True
                    stop_y = max(stop_y, first)
                elif kind == 5:                       # scale-out: part is closed, the rest is protected and trailed
                    realized += k * frac * (units * yh - cost_sum)
                    spread_paid += 0.5 * s * k * frac * units
                    units *= 1.0 - frac
                    cost_sum *= 1.0 - frac
                    scaled = True
                    stop_y = max(stop_y, first)
                    trail_on = trail > 0.0
                else:                                 # an add at a price level
                    u = mult[n_adds + 1]
                    if not _fits_budget(realized, units, cost_sum, yh, u, s, k, budget):
                        add_max = n_adds
                        a = yh if d == 1 else -yh - s
                        continue
                    units += u
                    cost_sum += u * (yh + s)
                    last = yh + s
                    n_adds += 1
                    volume += u
                    spread_paid += 0.5 * s * k * u
                    max_units = max(max_units, units)
                mae = min(mae, realized + k * (units * yh - cost_sum))
                a = yh if d == 1 else -yh - s
            if closed:
                break
            best = max(best, yb)
            mae = min(mae, realized + k * (units * yb - cost_sum))
        if closed:
            break
    return realized, mae, j, max_units, volume, spread_paid, n_adds, reason


@njit(cache=True)
def _leg_pl(side, price, x, s, k):
    """P/L of one unit bought (side +1, at the ask) or sold (side -1, at the bid) at ``price``, closed at bid ``x``."""
    if side == 1:
        return (x - price) * k
    return (price - x - s) * k


@njit(cache=True)
def _run_lock(e, d0, P, o, h, l, c, sp, atr, vote, hole, k):
    n = c.shape[0]
    mode, hold, path = int(P[P_LOCK_MODE]), int(P[P_LOCK_BARS]), int(P[P_PATH])
    A = atr[e]
    d = int(d0)
    s = sp[e]
    # leg 1 is the entry (later: the leg that was kept, or the re-entry); leg 2 is the hedge. side 0 = not open.
    side1, px1 = d, (c[e] + s if d == 1 else c[e])
    side2, px2 = 0, 0.0
    y = c[e] if d == 1 else -(c[e] + s)
    ref = y + s
    stop_y, tgt_y = ref - P[P_STOP_ATR] * A, ref + P[P_TGT_ATR] * A
    stage, lock_bar = 0, -1             # 0 first trade, 1 locked (or flat, waiting), 2 the trade after the unlock
    realized, spread_paid, volume, max_units = 0.0, 0.5 * s * k, 1.0, 1.0
    mae = -s * k
    reason, j = 0, e
    while True:
        # ── the close of bar j ──
        s = sp[j]
        x = c[j]
        if stage == 1:
            if mode == 3:
                if j - lock_bar >= hold:
                    realized += _leg_pl(side1, px1, x, s, k) + _leg_pl(side2, px2, x, s, k)
                    spread_paid += s * k
                    reason = R_UNLOCK
                    break
            elif vote[j] != 0:
                v = int(vote[j])
                if mode == 1:           # unlock: the leg against the signal is closed, the other one stays
                    if side1 == v:
                        realized += _leg_pl(side2, px2, x, s, k)
                    else:
                        realized += _leg_pl(side1, px1, x, s, k)
                        side1, px1 = side2, px2
                    side2 = 0
                else:                   # the same thing without a hedge: a new position in the direction of the signal
                    side1, px1 = v, (x + s if v == 1 else x)
                    volume += 1.0
                spread_paid += 0.5 * s * k
                d = v
                y = x if d == 1 else -(x + s)
                ref = y + s
                stop_y, tgt_y = ref - P[P_STOP2_ATR] * atr[j], ref + P[P_TGT2_ATR] * atr[j]
                stage = 2
        f = realized
        if side1 != 0:
            f += _leg_pl(side1, px1, x, s, k)
        if side2 != 0:
            f += _leg_pl(side2, px2, x, s, k)
        mae = min(mae, f)
        if j == n - 1 or hole[j]:
            if side1 != 0:
                spread_paid += 0.5 * s * k
            if side2 != 0:
                spread_paid += 0.5 * s * k
            realized = f
            reason = R_END
            break

        # ── bar j + 1 (only a single open position has a stop and a target) ──
        j += 1
        s = sp[j]
        if stage == 1:
            continue
        x1, x2 = (l[j], h[j]) if _low_first(path, d == 1, o[j], c[j]) else (h[j], l[j])
        closed = False
        for seg in range(3):
            if seg == 0:
                a, b = o[j], x1
            elif seg == 1:
                a, b = x1, x2
            else:
                a, b = x2, c[j]
            ya = a if d == 1 else -(a + s)
            yb = b if d == 1 else -(b + s)
            kind, dist, sgn = 0, np.inf, 0.0
            xd = _dist_down(stop_y, ya, yb)
            if 0.0 <= xd < dist:
                kind, dist, sgn = 1, xd, -1.0
            xd = _dist_up(tgt_y, ya, yb)
            if 0.0 <= xd < dist:
                kind, dist, sgn = 3, xd, 1.0
            if kind == 0:
                mae = min(mae, realized + _leg_pl(side1, px1, b, s, k))
                continue
            yh = ya + sgn * dist
            xr = yh if d == 1 else -yh - s
            if kind == 1 and stage == 0 and mode != 2:   # the stop level is reached: lock instead of closing
                side2, px2 = -side1, (xr if side1 == 1 else xr + s)
                volume += 1.0
                max_units = 2.0
                spread_paid += 0.5 * s * k
                stage, lock_bar = 1, j
                mae = min(mae, realized + _leg_pl(side1, px1, xr, s, k) + _leg_pl(side2, px2, xr, s, k))
                break
            realized += _leg_pl(side1, px1, xr, s, k)
            spread_paid += 0.5 * s * k
            side1 = 0
            mae = min(mae, realized)
            if kind == 1 and stage == 0:                 # mode 2: closed, now waiting for the signal
                stage, lock_bar = 1, j
                break
            reason = R_TARGET if kind == 3 else R_STOP
            closed = True
            break
        if closed:
            break
    return realized, mae, j, max_units, volume, spread_paid, 0, reason


@njit(cache=True)
def _run_zone(e, d0, P, o, h, l, c, sp, atr, hole, k):
    n = c.shape[0]
    A = atr[e]
    zone, tgt, max_legs = P[P_ZONE_ATR] * A, P[P_TGT_ATR] * A, int(P[P_ZONE_LEGS])
    path = int(P[P_PATH])
    d = int(d0)
    s = sp[e]
    y = c[e] if d == 1 else -(c[e] + s)
    up = y + s                          # upper edge: the price paid by the first leg
    lo = up - zone                      # lower edge: where the first opposite leg is sold
    with_u, with_sum = 1.0, up          # legs in the entry direction: units, sum(units x price paid)
    opp_u, opp_sum = 0.0, 0.0           # opposite legs: units, sum(units x price received)
    phase, legs = 1, 1                  # phase +1: the last leg is in the entry direction
    realized, spread_paid, volume, max_units = 0.0, 0.5 * s * k, 1.0, 1.0
    mae = -s * k
    reason, j = 0, e
    while True:
        s = sp[j]
        y = c[j] if d == 1 else -(c[j] + s)
        f = k * ((with_u * y - with_sum) + (opp_sum - opp_u * (y + s)))
        mae = min(mae, f)
        if j == n - 1 or hole[j]:
            realized = f
            spread_paid += 0.5 * s * k * (with_u + opp_u)
            reason = R_END
            break
        j += 1
        s = sp[j]
        # by default towards the edge that forces the next, larger leg first
        x1, x2 = (l[j], h[j]) if _low_first(path, (d == 1) == (phase == 1), o[j], c[j]) else (h[j], l[j])
        closed = False
        for seg in range(3):
            if seg == 0:
                a, b = o[j], x1
            elif seg == 1:
                a, b = x1, x2
            else:
                a, b = x2, c[j]
            yb = 0.0
            for _ in range(_GUARD):
                ya = a if d == 1 else -(a + s)
                yb = b if d == 1 else -(b + s)
                kind, dist, sgn = 0, np.inf, 0.0
                if phase == 1:
                    x = _dist_down(lo, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 1, x, -1.0
                    x = _dist_up(up + tgt, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 3, x, 1.0
                else:
                    x = _dist_up(up - s, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 1, x, 1.0
                    x = _dist_down(lo - tgt - s, ya, yb)
                    if 0.0 <= x < dist:
                        kind, dist, sgn = 3, x, -1.0
                if kind == 0:
                    break
                yh = ya + sgn * dist
                if kind == 3 or legs >= max_legs:      # a target, or the edge with no leg left: everything is closed
                    realized = k * ((with_u * yh - with_sum) + (opp_sum - opp_u * (yh + s)))
                    spread_paid += 0.5 * s * k * (with_u + opp_u)
                    mae = min(mae, realized)
                    reason = R_TARGET if kind == 3 else R_MAX_LEGS
                    closed = True
                    break
                # the next leg is as large as it takes for its own target to pay what the first trade aimed for
                if phase == 1:
                    u = (tgt + with_u * (zone + tgt)) / tgt - opp_u
                    opp_u += u
                    opp_sum += u * yh
                    phase = -1
                else:
                    u = (tgt + opp_u * (zone + tgt)) / tgt - with_u
                    with_u += u
                    with_sum += u * (yh + s)
                    phase = 1
                legs += 1
                volume += u
                spread_paid += 0.5 * s * k * u
                max_units = max(max_units, with_u + opp_u)
                mae = min(mae, k * ((with_u * yh - with_sum) + (opp_sum - opp_u * (yh + s))))
                a = yh if d == 1 else -yh - s
            if closed:
                break
            mae = min(mae, k * ((with_u * yb - with_sum) + (opp_sum - opp_u * (yb + s))))
        if closed:
            break
    return realized, mae, j, max_units, volume, spread_paid, legs - 1, reason


@njit(cache=True)
def _simulate(idx, dirs, P, mult, o, h, l, c, sp, atr, rsi, ev, vote, session, hole, k):
    out = np.zeros((idx.shape[0], 8))
    fam = int(P[P_FAMILY])
    for i in range(idx.shape[0]):
        if fam == 0:
            r = _run_directional(idx[i], dirs[i], P, mult, o, h, l, c, sp, atr, rsi, ev, session, hole, k)
        elif fam == 1:
            r = _run_lock(idx[i], dirs[i], P, o, h, l, c, sp, atr, vote, hole, k)
        else:
            r = _run_zone(idx[i], dirs[i], P, o, h, l, c, sp, atr, hole, k)
        out[i, 0], out[i, 1], out[i, 2], out[i, 3] = r[0], r[1], r[2], r[3]
        out[i, 4], out[i, 5], out[i, 6], out[i, 7] = r[4], r[5], r[6], r[7]
    return out


@njit(cache=True)
def _flat_entries(cand, ok, P, mult, o, h, l, c, sp, atr, rsi, ev, session, hole, k):
    """Walk the candidates in time order and take one whenever the previous basket of mechanism ``P`` has closed."""
    n = c.shape[0]
    taken = np.zeros(n, np.bool_)
    free = 0
    for j in range(n - 1):
        if cand[j] != 0 and ok[j] and j >= free:
            r = _run_directional(j, cand[j], P, mult, o, h, l, c, sp, atr, rsi, ev, session, hole, k)
            taken[j] = True
            free = r[2]
    return taken


# ───────────────────────────── mechanisms ─────────────────────────────

@dataclass
class Mechanism:
    """One row of the comparison. ``rule`` marks a rule on the SEQUENCE of reference trades instead of a simulator setting."""
    name: str
    group: str
    position: str                # largest position it can hold, in units of 0.01 lot
    worst: str                   # worst loss one basket can produce by design (R = one ATR on one unit); gaps come on top
    params: Dict[int, float] = field(default_factory=dict)
    mult: Sequence[float] = (1.0,) * 8
    control: str = ""            # the row it is compared with in the "change" columns (default: the reference)
    rule: str = ""               # "martingale", "anti-martingale", "daily-limit"
    rule_value: float = 0.0
    twin: str = ""               # a row that must produce the same P/L, entry by entry

    def vector(self) -> np.ndarray:
        p = np.zeros(N_PARAMS)
        for slot, value in self.params.items():
            p[slot] = float(value)
        return p

    def budget(self, risk: np.ndarray) -> np.ndarray:
        """
        The loss in USD a basket of this mechanism is built not to exceed, given ``risk`` (the value of
        one ATR on one unit at each entry); NaN where the rules set no such amount. A basket that
        loses more was carried past its stop by a gap.
        """
        p = self.vector()
        risk = np.asarray(risk, np.float64)
        out = np.full(len(risk), np.nan)
        if self.rule or p[P_FAMILY] != 0:
            return out
        if p[P_STOP_USD] > 0 or p[P_STOP_BUDGET_ATR] > 0:                 # a budget on the whole basket
            out = np.full(len(risk), p[P_STOP_USD] if p[P_STOP_USD] > 0 else np.inf)
            if p[P_STOP_BUDGET_ATR] > 0:
                out = np.minimum(out, p[P_STOP_BUDGET_ATR] * risk)
        elif p[P_STOP_ATR] > 0 and p[P_ADD_MODE] == 0:
            # one unit behind its stop (break-even and trailing only ever tighten it); with a reversal, both trades
            out = p[P_STOP_ATR] * risk * (1.0 + p[P_REV_MAX] * p[P_REV_MULT])
        return out


REFERENCE = "Fixed stop 1 ATR, target 1 ATR (reference)"
LIVE_MULT = (1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 0.0, 0.0)
SMALL_TARGET_ATR = 0.5           # "a small profit over the average entry"
LOCK_HOLD_BARS = 240             # the timed hedge lock is held for four hours of M1 bars
CAPPED_LADDER = "Budget 3 R but never more than $60, 2 adds 0.5 ATR apart"


def level_spacing(budget_atr: float, adds: int) -> float:
    """
    Spacing (in ATR) of ``adds`` equal adds so that the stop sits one more spacing beyond the last add
    and the whole basket then loses exactly ``budget_atr`` ATR on one unit.
    """
    return 2.0 * budget_atr / ((adds + 1) * (adds + 2))


def zone_sizes(zone_atr: float, tgt_atr: float, legs: int) -> List[float]:
    """The leg sizes of a zone recovery (the first leg is 1): each makes its own target pay what the first aimed for."""
    with_u, opp_u, out = 1.0, 0.0, [1.0]
    for i in range(1, legs):
        if i % 2:
            u = (tgt_atr + with_u * (zone_atr + tgt_atr)) / tgt_atr - opp_u
            opp_u += u
        else:
            u = (tgt_atr + opp_u * (zone_atr + tgt_atr)) / tgt_atr - with_u
            with_u += u
        out.append(u)
    return out


def zone_worst(zone_atr: float, tgt_atr: float, legs: int) -> float:
    """Loss in R when the edge is reached with no leg left (spread not included)."""
    sizes = zone_sizes(zone_atr, tgt_atr, legs)
    last_side = sum(sizes[(legs - 1) % 2::2])
    return last_side * zone_atr


def mechanisms() -> List[Mechanism]:
    """The fixed list of mechanisms. Nothing in it was tuned: these are the textbook forms at round numbers."""
    m: List[Mechanism] = []

    g = "Single position, fixed stop and target"
    m.append(Mechanism(REFERENCE, g, "1", "1 R", {P_STOP_ATR: 1, P_TGT_ATR: 1}))
    m.append(Mechanism("Fixed stop 2 ATR, target 2 ATR", g, "1", "2 R", {P_STOP_ATR: 2, P_TGT_ATR: 2}))
    m.append(Mechanism("Fixed stop 1 ATR, target 2 ATR", g, "1", "1 R", {P_STOP_ATR: 1, P_TGT_ATR: 2}))
    m.append(Mechanism("Fixed stop 2 ATR, target 1 ATR", g, "1", "2 R", {P_STOP_ATR: 2, P_TGT_ATR: 1}))
    m.append(Mechanism("Fixed stop $20, target $20 (the V2 exit)", g, "1", "$20", {P_STOP_USD: 20, P_TGT_USD: 20}))

    g = "Live ladder: adds x2, 3, 5, 8, 13 at RSI 35 / 65 of M1, M5, M15, H1, H4; target $1 for the basket"
    live = {P_TGT_USD: 1, P_ADD_MODE: 3, P_ADD_MAX: 5, P_RSI_OS: 35, P_RSI_OB: 65}
    m.append(Mechanism("Live ladder, no stop", g, "32", "no limit", dict(live), LIVE_MULT))
    m.append(Mechanism("Live ladder, basket stop $60", g, "32", "$60", {**live, P_STOP_USD: 60}, LIVE_MULT))
    m.append(Mechanism("Live ladder, basket stop $200", g, "32", "$200", {**live, P_STOP_USD: 200}, LIVE_MULT))

    g = "Averaging down inside a fixed budget: equal lots at price levels, target 0.5 ATR over the average entry"
    for budget, adds in ((1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4)):
        p = {P_TGT_AVG_ATR: SMALL_TARGET_ATR, P_STOP_BUDGET_ATR: budget}
        control = f"Budget {budget} R, no add"
        if adds:
            step = level_spacing(budget, adds)
            p.update({P_ADD_MODE: 1, P_ADD_MAX: adds, P_ADD_STEP_ATR: step})
            name = f"Budget {budget} R, {adds} add{'s' if adds > 1 else ''} {step:.2g} ATR apart"
        else:
            name = control
        m.append(Mechanism(name, g, str(adds + 1), f"{budget} R", p, control=control if adds else ""))
    m.append(Mechanism(CAPPED_LADDER, g, "3", "3 R, at most $60",
                       {P_TGT_AVG_ATR: SMALL_TARGET_ATR, P_STOP_BUDGET_ATR: 3, P_STOP_USD: 60, P_ADD_MODE: 1, P_ADD_MAX: 2,
                        P_ADD_STEP_ATR: level_spacing(3, 2)}, control="Budget 3 R, no add"))
    for level, label in ((1, "the weekend"), (2, "every market closure")):
        m.append(Mechanism(f"{CAPPED_LADDER}, flat over {label}", g, "3", "3 R, at most $60",
                           {P_TGT_AVG_ATR: SMALL_TARGET_ATR, P_STOP_BUDGET_ATR: 3, P_STOP_USD: 60, P_ADD_MODE: 1, P_ADD_MAX: 2,
                            P_ADD_STEP_ATR: level_spacing(3, 2), P_FLAT: level}, control=CAPPED_LADDER))

    g = "Averaging down released by a signal: 2 equal adds, each at least 0.5 ATR beyond the last fill, budget 3 R"
    for i, label in enumerate(("M5 MACD histogram turns", "M15 MACD histogram turns",
                               "M5 RSI comes back through 35 / 65", "M15 RSI comes back through 35 / 65")):
        m.append(Mechanism(f"Add when the {label}", g, "3", "3 R",
                           {P_TGT_AVG_ATR: SMALL_TARGET_ATR, P_STOP_BUDGET_ATR: 3, P_ADD_MODE: 4, P_ADD_MAX: 2,
                            P_ADD_STEP_ATR: 0.5, P_ADD_SIGNAL: i}, control="Budget 3 R, no add"))

    g = "Stops that follow the price (single position)"
    m.append(Mechanism("Break-even at +0.5 ATR (stop 1, target 1)", g, "1", "1 R",
                       {P_STOP_ATR: 1, P_TGT_ATR: 1, P_BE_TRIG_ATR: 0.5}))
    m.append(Mechanism("Break-even at +1 ATR (stop 1, target 2)", g, "1", "1 R",
                       {P_STOP_ATR: 1, P_TGT_ATR: 2, P_BE_TRIG_ATR: 1}, control="Fixed stop 1 ATR, target 2 ATR"))
    m.append(Mechanism("Trailing stop 1 ATR, no target", g, "1", "1 R",
                       {P_STOP_ATR: 1, P_TRAIL_ATR: 1, P_TRAIL_FROM_START: 1}))
    m.append(Mechanism("Trailing stop 2 ATR, no target", g, "1", "2 R",
                       {P_STOP_ATR: 2, P_TRAIL_ATR: 2, P_TRAIL_FROM_START: 1}, control="Fixed stop 2 ATR, target 2 ATR"))
    m.append(Mechanism("Scale-out: half at +1 ATR, rest trailed by 1 ATR", g, "1", "1 R",
                       {P_STOP_ATR: 1, P_SCALE_ATR: 1, P_SCALE_FRAC: 0.5, P_TRAIL_ATR: 1},
                       control="Trailing stop 1 ATR, no target"))

    g = "Averaging up (pyramiding): equal adds every 1 ATR in profit, trailing stop 1 ATR on the basket"
    for adds in (2, 4):
        m.append(Mechanism(f"Pyramid, {adds} adds", g, str(adds + 1), "1 R",
                           {P_STOP_ATR: 1, P_TRAIL_ATR: 1, P_TRAIL_FROM_START: 1, P_ADD_MODE: 2, P_ADD_MAX: adds,
                            P_ADD_STEP_ATR: 1}, control="Trailing stop 1 ATR, no target"))

    g = "Hedge lock: at -1 ATR the opposite position is opened instead of closing"
    lock = {P_FAMILY: 1, P_STOP_ATR: 1, P_TGT_ATR: 1, P_STOP2_ATR: 1, P_TGT2_ATR: 1}
    m.append(Mechanism("Hedge lock, unlocked by the next vote signal", g, "2 (1 long + 1 short)", "2 R + spreads",
                       {**lock, P_LOCK_MODE: 1}, twin="Close at -1 ATR, re-enter on the next vote signal"))
    m.append(Mechanism("Close at -1 ATR, re-enter on the next vote signal", g, "1", "2 R + spreads", {**lock, P_LOCK_MODE: 2}))
    m.append(Mechanism("Hedge lock, both legs closed 4 h later", g, "2 (1 long + 1 short)", "1 R + 1 spread",
                       {**lock, P_LOCK_MODE: 3, P_LOCK_BARS: LOCK_HOLD_BARS}))

    g = "Zone recovery: alternating, growing opposite positions until one side's target is reached"
    for zone, legs in ((1.0, 4), (0.5, 4)):
        sizes = zone_sizes(zone, 1.0, legs)
        m.append(Mechanism(f"Zone {zone:g} ATR, target 1 ATR, legs " + " / ".join(f"{u:.3g}" for u in sizes), g,
                           f"{sum(sizes):.3g} (both sides)", f"{zone_worst(zone, 1.0, legs):.3g} R + spreads",
                           {P_FAMILY: 2, P_ZONE_ATR: zone, P_TGT_ATR: 1, P_ZONE_LEGS: legs}))

    g = "Stop and reverse: at -1 ATR the position is closed and the opposite one opened (stop 1, target 1), once"
    m.append(Mechanism("Stop and reverse, same size", g, "1", "2 R",
                       {P_STOP_ATR: 1, P_TGT_ATR: 1, P_REV_MAX: 1, P_REV_MULT: 1}))
    m.append(Mechanism("Stop and reverse, double size", g, "2", "3 R",
                       {P_STOP_ATR: 1, P_TGT_ATR: 1, P_REV_MAX: 1, P_REV_MULT: 2}))

    g = "Size of the NEXT basket (the reference trade, re-sized by what the last one did)"
    m.append(Mechanism("Martingale: double after a loss, up to x8", g, "8", "8 R (15 R over four losses)",
                       rule="martingale", rule_value=8))
    m.append(Mechanism("Anti-martingale: double after a win, up to x8", g, "8", "8 R", rule="anti-martingale", rule_value=8))

    g = "Daily loss limit (the reference trade; no new basket that UTC day once the day has lost this much)"
    m.append(Mechanism("Daily loss limit 1 R", g, "1", "1 R a basket, about 1 R a day", rule="daily-limit", rule_value=1))
    m.append(Mechanism("Daily loss limit 2 R", g, "1", "1 R a basket, about 2 R a day", rule="daily-limit", rule_value=2))
    return m


RESULT_COLUMNS = ["pnl", "mae", "close_idx", "max_units", "volume", "spread_paid", "adds", "reason"]


def simulate(frame: Frame, idx: Sequence[int], dirs: Sequence[int], mech: Mechanism,
             path: int = PATH_UNFAVOURABLE_FIRST) -> pd.DataFrame:
    """
    Every entry (bar index, +1 long / -1 short) run through one mechanism, each on its own.
    ``path`` is the order assumed inside a bar; anything but the default exists only to measure how
    much a result depends on that order.

    Columns: pnl and mae (worst floating result) in USD for a base size of one unit, close_idx,
    max_units (largest position held, both sides counted), volume (units opened), spread_paid (USD),
    adds, reason, plus entry_idx, dir, entry_time, risk (the USD value of one ATR on one unit at the entry).
    """
    if mech.rule:
        raise ValueError(f"{mech.name!r} is a rule on a sequence of baskets; use evaluate()")
    idx = np.asarray(idx, np.int64)
    dirs = np.asarray(dirs, np.int8)
    mult = np.zeros(8)
    mult[:len(mech.mult)] = mech.mult
    vec = mech.vector()
    vec[P_PATH] = float(path)
    raw = _simulate(idx, dirs, vec, mult, frame.o, frame.h, frame.l, frame.c, frame.sp, frame.atr,
                    frame.rsi, frame.ev, frame.vote, frame.session, frame.hole, frame.k)
    df = pd.DataFrame(raw, columns=RESULT_COLUMNS)
    for col in ("close_idx", "adds", "reason"):
        df[col] = df[col].astype(np.int64)
    df.insert(0, "entry_idx", idx)
    df.insert(1, "dir", dirs.astype(np.int64))
    df["entry_time"] = frame.t[idx] + 60
    df["close_time"] = frame.t[df["close_idx"].to_numpy()] + 60
    df["risk"] = frame.atr[idx] * frame.k
    df["budget"] = mech.budget(df["risk"].to_numpy())
    df["size"] = 1.0
    df["taken"] = df["reason"] != R_NOT_TAKEN
    return df


# ───────────────────────────── entry lists ─────────────────────────────

def _uniform(t: np.ndarray, seed: int) -> np.ndarray:
    """A reproducible uniform number in [0, 1) for every timestamp: a function of (time, seed), not of the data loaded."""
    z = t.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15) + np.uint64(seed)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    z = z ^ (z >> np.uint64(31))
    return (z >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def entry_candidates(frame: Frame, kind: str, seed: int = RANDOM_SEED) -> np.ndarray:
    """+1 / -1 at every M1 close at which the list ``kind`` would enter if it were flat, else 0."""
    if kind == "votes":
        return frame.vote.copy()
    if kind == "trend":
        return np.where(frame.vote == frame.trend, frame.vote, 0).astype(np.int8)
    if kind == "random":
        with np.errstate(over="ignore"):
            go = frame.m15_close & (_uniform(frame.t, seed) < RANDOM_ENTRY_PROB)
            side = np.where(_uniform(frame.t, seed + 1) < 0.5, 1, -1)
        return np.where(go, side, 0).astype(np.int8)
    raise KeyError(kind)


def entry_list(frame: Frame, kind: str, first_s: int = 0, seed: int = RANDOM_SEED) -> Tuple[np.ndarray, np.ndarray]:
    """
    The fixed list of entries of ``kind``: bar indices and directions.

    An entry is made at an M15 close at which the signal stands and no basket is open. "No basket is
    open" has to mean the same for every mechanism, or they would not see the same entries, so it is
    read off the reference trade (stop 1 ATR, target 1 ATR): the next entry is the first signal after
    the reference trade of the previous one has closed.
    """
    cand = entry_candidates(frame, kind, seed)
    ok = frame.ok & (frame.t + 60 >= first_s)
    ref = mechanisms()[0]
    taken = _flat_entries(cand, ok, ref.vector(), np.ones(8), frame.o, frame.h, frame.l, frame.c, frame.sp, frame.atr,
                          frame.rsi, frame.ev, frame.session, frame.hole, frame.k)
    idx = np.flatnonzero(taken)
    return idx, cand[idx].astype(np.int8)


# ───────────────────────────── rules on the sequence of baskets ─────────────────────────────

def resize_by_outcome(base: pd.DataFrame, rule: str, cap: float) -> pd.DataFrame:
    """
    Martingale (double after a loss) or anti-martingale (double after a win) sizing of the next basket.
    The size goes back to 1 after the opposite outcome and never exceeds ``cap``.
    """
    out = base.copy()
    size = np.ones(len(base))
    cur = 1.0
    for i, pnl in enumerate(base["pnl"].to_numpy()):
        size[i] = cur
        grow = pnl < 0 if rule == "martingale" else pnl > 0
        cur = min(cur * 2.0, cap) if grow else 1.0
    for col in ("pnl", "mae", "max_units", "volume", "spread_paid", "budget"):
        out[col] = base[col].to_numpy() * size
    out["size"] = size
    return out


def daily_loss_limit(base: pd.DataFrame, limit_r: float) -> pd.DataFrame:
    """No new basket on a UTC day once the baskets entered that day have lost ``limit_r`` R in total (R of each at its own entry)."""
    out = base.copy()
    day = (base["entry_time"].to_numpy() // 86400).astype(np.int64)
    r = (base["pnl"] / base["risk"]).to_numpy()
    taken = np.ones(len(base), bool)
    cur_day, lost = -1, 0.0
    for i in range(len(base)):
        if day[i] != cur_day:
            cur_day, lost = day[i], 0.0
        if lost <= -limit_r + 1e-9:
            taken[i] = False
            continue
        lost += r[i]
    for col in ("pnl", "mae", "volume", "spread_paid"):
        out[col] = np.where(taken, base[col].to_numpy(), 0.0)
    out["taken"] = taken
    return out


def evaluate(frame: Frame, idx: np.ndarray, dirs: np.ndarray, mechs: Optional[List[Mechanism]] = None,
             path: int = PATH_UNFAVOURABLE_FIRST) -> Dict[str, pd.DataFrame]:
    """Every mechanism on one entry list: name -> one row per entry."""
    mechs = mechs or mechanisms()
    res: Dict[str, pd.DataFrame] = {}
    for mech in mechs:
        if not mech.rule:
            res[mech.name] = simulate(frame, idx, dirs, mech, path)
    for mech in mechs:
        if mech.rule == "daily-limit":
            res[mech.name] = daily_loss_limit(res[REFERENCE], mech.rule_value)
        elif mech.rule:
            res[mech.name] = resize_by_outcome(res[REFERENCE], mech.rule, mech.rule_value)
    return res


# ───────────────────────────── statistics ─────────────────────────────

def week_of(time_s: np.ndarray) -> np.ndarray:
    """Calendar week (Monday to Sunday, UTC) as an integer."""
    return (np.asarray(time_s, np.int64) // 86400 + 3) // 7


def clustered_se(x: np.ndarray, cluster: np.ndarray) -> float:
    """
    Standard error of the mean of ``x`` when observations of the same cluster (calendar week) move
    together: baskets that overlap in time are not independent, and treating them as if they were
    would make every result look more certain than it is.
    """
    x = np.asarray(x, np.float64)
    n = len(x)
    if n < 2:
        return float("nan")
    dev = pd.Series(x - x.mean()).groupby(np.asarray(cluster)).sum().to_numpy()
    g = len(dev)
    if g < 2:
        return float("nan")
    return float(math.sqrt(g / (g - 1.0) * float((dev ** 2).sum())) / n)


def account_replay(df: pd.DataFrame, account: float = ACCOUNT) -> Dict[str, object]:
    """
    The baskets traded in time order on an account of ``account`` USD at the base size, one basket at
    a time: an entry that arrives while the previous basket is still open is skipped, as the bot would.
    Drawdown is measured from the highest closed balance to the lowest equity, floating loss included;
    the account is wiped when equity reaches zero. ``acct_wiped_by`` says how: "one basket" when the
    last basket alone lost at least half of the starting account, "many losses" when it bled out.
    """
    bal = peak = float(account)
    dd, free, taken = 0.0, -1, 0
    wiped_at, wiped_by = None, ""
    for e, z, pnl, mae, ok, tm in zip(df["entry_idx"].to_numpy(), df["close_idx"].to_numpy(), df["pnl"].to_numpy(),
                                      df["mae"].to_numpy(), df["taken"].to_numpy(), df["entry_time"].to_numpy()):
        if not ok or e < free:
            continue
        taken += 1
        low = bal + min(mae, 0.0)
        dd = max(dd, peak - low)
        if low <= 0.0 or bal + pnl <= 0.0:
            wiped_at = pd.Timestamp(int(tm), unit="s").strftime("%Y-%m-%d")
            wiped_by = "one basket" if min(mae, pnl) <= -0.5 * account else "many losses"
            dd, bal = peak, 0.0
            break
        bal += pnl
        dd = max(dd, peak - bal)
        peak = max(peak, bal)
        free = z
    return {"acct_taken": taken, "acct_net": round(bal - account, 2), "acct_max_dd": round(dd, 2),
            "acct_wiped": wiped_at is not None, "acct_wiped_on": wiped_at or "", "acct_wiped_by": wiped_by}


def _summary(df: pd.DataFrame, ctrl: Optional[pd.DataFrame]) -> Dict[str, float]:
    t = df[df["taken"]]
    pnl = t["pnl"].to_numpy()
    n = len(pnl)
    out: Dict[str, float] = {"n": n}
    if n == 0:
        return out
    wk = week_of(t["entry_time"].to_numpy())
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross = pnl + t["spread_paid"].to_numpy()
    out.update(
        exp=float(pnl.mean()), se=clustered_se(pnl, wk),
        win_pct=float((pnl > 0).mean() * 100.0),
        avg_win=float(wins.mean()) if len(wins) else 0.0, avg_loss=float(losses.mean()) if len(losses) else 0.0,
        worst=float(pnl.min()), p01=float(np.percentile(pnl, 1)), best=float(pnl.max()),
        worst_mae=float(t["mae"].min()),
        max_units=float(t["max_units"].max()), avg_units_opened=float(t["volume"].mean()),
        spread_paid=float(t["spread_paid"].mean()), gross=float(gross.mean()), gross_se=clustered_se(gross, wk),
        exp_per_r=float((pnl / t["risk"].to_numpy()).mean()),
        risk_usd=float(t["risk"].median()), risk_p95=float(np.percentile(t["risk"], 95)), risk_max=float(t["risk"].max()),
        hold_h=float(np.median(t["close_time"].to_numpy() - t["entry_time"].to_numpy()) / 3600.0),
        open_at_end_pct=float((t["reason"] == R_END).mean() * 100.0),
        total=float(pnl.sum()),
    )
    budget = t["budget"].to_numpy()
    if np.isfinite(budget).all():
        over = -pnl - budget                                          # what a basket lost beyond what it was built to lose
        out.update(budget_max=float(budget.max()), over_budget_n=int((over > OVERSHOOT_USD).sum()),
                   over_budget_max=float(max(over.max(), 0.0)))
    if ctrl is not None:
        diff = df["pnl"].to_numpy() - ctrl["pnl"].to_numpy()        # per signal; a basket not taken counts as zero
        out["chg"] = float(diff.mean())
        out["chg_se"] = clustered_se(diff, week_of(df["entry_time"].to_numpy()))
    return out


def closure_gaps(frame: Frame) -> List[dict]:
    """
    How far the price jumped while the market was closed: the part of a loss no stop can prevent.
    A silence of half an hour or more is a closure; one of more than a day is a weekend or a holiday.
    """
    gap = np.diff(frame.t)
    at = np.flatnonzero((gap >= 1800) & ~frame.hole[:-1] & np.isfinite(frame.atr[:-1]))
    jump = np.abs(frame.o[at + 1] - frame.c[at])
    out = []
    for label, pick in (("daily break", gap[at] <= 86400), ("weekend or holiday", gap[at] > 86400)):
        x, r = jump[pick], jump[pick] / frame.atr[at][pick]
        if len(x):
            out.append({"closure": label, "n": int(len(x)), "median_usd": float(np.median(x) * frame.k),
                        "p99_usd": float(np.percentile(x, 99) * frame.k), "max_usd": float(x.max() * frame.k),
                        "median_r": float(np.median(r)), "p99_r": float(np.percentile(r, 99)), "max_r": float(r.max())})
    return out


def half_year(time_s: np.ndarray) -> np.ndarray:
    ts = pd.to_datetime(np.asarray(time_s, np.int64), unit="s")
    return np.array([f"{y} H{1 if mth <= 6 else 2}" for y, mth in zip(ts.year, ts.month)], dtype=object)


def summarise(res: Dict[str, pd.DataFrame], mechs: List[Mechanism], keys: Dict[str, str]) -> Tuple[List[dict], List[dict]]:
    """Per-mechanism rows for the two result files: the whole period, and each half-year of it."""
    rows, halves = [], []
    for order, mech in enumerate(mechs):
        df = res[mech.name]
        ctrl = res.get(mech.control or REFERENCE) if mech.name != REFERENCE else None
        row = {**keys, "order": order, "mechanism": mech.name, "group": mech.group, "position": mech.position,
               "worst_by_design": mech.worst, "control": (mech.control or REFERENCE) if ctrl is not None else "",
               **_summary(df, ctrl), **account_replay(df)}
        added = (df["adds"] > 0).to_numpy()
        if ctrl is not None and not mech.rule and added.any():
            # the baskets in which this mechanism added at least once, against the same baskets under the row it is compared with
            a, b = df["pnl"].to_numpy()[added], ctrl["pnl"].to_numpy()[added]
            row.update(added_n=int(added.sum()), added_exp=float(a.mean()), added_win_pct=float((a > 0).mean() * 100.0),
                       added_ctrl_exp=float(b.mean()), added_ctrl_win_pct=float((b > 0).mean() * 100.0),
                       added_chg_se=clustered_se(a - b, week_of(df["entry_time"].to_numpy()[added])))
        if mech.twin:       # entry by entry against the row that must pay the same (baskets cut off by the end of the period aside)
            done = (df["reason"] != R_END).to_numpy()
            diff = np.abs(df["pnl"].to_numpy() - res[mech.twin]["pnl"].to_numpy())[done]
            row["twin_max_abs_diff"] = float(diff.max()) if len(diff) else 0.0
        rows.append(row)
        hy = half_year(df["entry_time"].to_numpy())
        for label in sorted(set(hy)):
            s = _summary(df[hy == label], None)
            halves.append({**keys, "order": order, "mechanism": mech.name, "half": label,
                           **{q: s.get(q, float("nan")) for q in ("n", "exp", "se", "win_pct", "worst", "total")}})
    return rows, halves


# ───────────────────────────── run and report ─────────────────────────────

def _merge(path: Path, new: pd.DataFrame) -> pd.DataFrame:
    """Replace the (symbol, period) blocks just computed in the stored file and keep the others."""
    if path.exists():
        old = pd.read_csv(path, keep_default_na=False, na_values=[""])
        done = set(map(tuple, new[["symbol", "period"]].drop_duplicates().to_numpy()))
        old = old[[key not in done for key in map(tuple, old[["symbol", "period"]].to_numpy())]]
        new = pd.concat([old, new], ignore_index=True)
    new["_p"] = new["period"].map({name: i for i, name in enumerate(PERIODS)})
    new["_l"] = new["list"].map({name: i for i, name in enumerate(LISTS)}).fillna(0)
    new = new.sort_values(["symbol", "_p", "_l", "order"] + (["half"] if "half" in new.columns else []), kind="stable")
    return new.drop(columns=["_p", "_l"]).reset_index(drop=True)


def run(symbols: Sequence[str], periods: Sequence[str], out: Path = OUT, cache_dir: Optional[Path] = None, log=print) -> None:
    """Every mechanism on every entry list of every symbol and period asked for; the two result files are updated."""
    mechs = mechanisms()
    rows, halves, gaps = [], [], []
    for sym in symbols:
        for per in periods:
            if not months_available(sym, per):
                log(f"{sym} {per}: the tick store does not hold every month of {PERIODS[per][0]} .. {PERIODS[per][2]}; skipped")
                continue
            frame, first_s = load_frame(sym, per, cache_dir)
            gaps += [{"symbol": sym, "period": per, "list": "", "order": i, **g} for i, g in enumerate(closure_gaps(frame))]
            for kind in LISTS:
                idx, dirs = entry_list(frame, kind, first_s)
                res = evaluate(frame, idx, dirs, mechs)
                r, hv = summarise(res, mechs, {"symbol": sym, "period": per, "list": kind})
                # the same again with the two other readings of the order inside a bar: how much hangs on that convention
                for tag, path in OTHER_READINGS.items():
                    other, _ = summarise(evaluate(frame, idx, dirs, mechs, path), mechs, {})
                    for row, alt in zip(r, other):
                        row.update({f"{col}_{tag}": alt.get(col, float("nan")) for col in ("exp", "acct_net", "acct_wiped")})
                rows += r
                halves += hv
                log(f"{sym} {per} {kind}: {len(idx)} entries, reference {r[0]['exp']:+.3f} USD per entry (s.e. {r[0]['se']:.3f})")
                if cache_dir:
                    pd.concat([d.assign(mechanism=name) for name, d in res.items()], ignore_index=True) \
                        .to_csv(Path(cache_dir) / f"recovery_baskets_{sym}_{per}_{kind}.csv.gz", index=False)
    if not rows:
        return
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("recovery_mechanisms.csv", rows), ("recovery_mechanisms_halfyears.csv", halves),
                       ("recovery_mechanisms_gaps.csv", gaps)):
        if data:
            path = out / name
            _merge(path, pd.DataFrame(data)).to_csv(path, index=False, float_format="%.6g")
            log(f"wrote {path}")


def _usd(x: float, digits: int = 2) -> str:
    """A signed USD amount; whole dollars once it is large."""
    if x != x:
        return "n/a"
    return f"{x:+,.0f}" if abs(x) >= 100 else f"{x:+.{digits}f}"


def _rows(d: pd.DataFrame, name: str) -> Dict[str, pd.Series]:
    """The row of one mechanism in each period that has been run."""
    out = {}
    for per in PERIODS:
        hit = d[(d["mechanism"] == name) & (d["period"] == per)]
        if len(hit):
            out[per] = hit.iloc[0]
    return out


def _cell(per: Dict[str, pd.Series], fmt) -> str:
    """One table cell holding the DEV and the CONFIRM value."""
    return " / ".join(fmt(per[name]) if name in per else "n/a" for name in PERIODS)


def _md(header: List[str], body: List[List[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _names(d: pd.DataFrame) -> List[str]:
    return list(d.sort_values("order")["mechanism"].drop_duplicates())


def table_main(d: pd.DataFrame, symbol: str, kind: str) -> str:
    """One entry list of one symbol: every mechanism, DEV / CONFIRM in each cell."""
    d = d[(d["symbol"] == symbol) & (d["list"] == kind)]
    header = ["Mechanism", "Baskets", "Expectancy per entry (± s.e.)", "Win %", "Worst basket", "1st percentile",
              "Largest position held", "Worst floating loss", "$2,000 account: result", "deepest drawdown", "emptied"]
    body, group = [], None
    for name in _names(d):
        per = _rows(d, name)
        first = next(iter(per.values()))
        if first["group"] != group:
            group = first["group"]
            body.append([f"**{group}**"] + [""] * (len(header) - 1))
        body.append([
            name, _cell(per, lambda r: f"{int(r['n']):,}"),
            _cell(per, lambda r: _usd(r["exp"])) + " (± " + _cell(per, lambda r: f"{r['se']:.2f}") + ")",
            _cell(per, lambda r: f"{r['win_pct']:.0f}"), _cell(per, lambda r: _usd(r["worst"], 1)),
            _cell(per, lambda r: _usd(r["p01"], 1)), _cell(per, lambda r: f"{r['max_units']:.3g}"),
            _cell(per, lambda r: _usd(r["worst_mae"], 1)), _cell(per, lambda r: _usd(r["acct_net"], 0)),
            _cell(per, lambda r: f"{r['acct_max_dd']:,.0f}"),
            _cell(per, lambda r: f"{r['acct_wiped_on']}, {r['acct_wiped_by']}" if r["acct_wiped"] else "no")])
    ref = _rows(d, REFERENCE)
    def risk(col):
        return _cell(ref, lambda r: "$" + format(r[col], ".2f"))

    note = (f"Entries: {_cell(ref, lambda r: format(int(r['n']), ','))}. One R (the ATR of the entry hour on 0.01 lot): median "
            f"{risk('risk_usd')}, 95th percentile {risk('risk_p95')}, largest {risk('risk_max')}. "
            f"Every cell is DEV / CONFIRM; amounts in USD for a base size of 0.01 lot; position in units of 0.01 lot.")
    return note + "\n\n" + _md(header, body)


SYMBOL_LABEL = {"XAUUSDm": "Gold", "BTCUSDm": "BTC"}

# the rows of the one-page summary: one or two of each family
SUMMARY_ROWS = (
    REFERENCE, "Fixed stop $20, target $20 (the V2 exit)", "Live ladder, no stop", "Live ladder, basket stop $200",
    "Budget 3 R, no add", "Budget 3 R, 2 adds 0.5 ATR apart", CAPPED_LADDER + ", flat over every market closure",
    "Add when the M15 RSI comes back through 35 / 65", "Trailing stop 1 ATR, no target", "Pyramid, 2 adds",
    "Hedge lock, unlocked by the next vote signal", "Zone 0.5 ATR, target 1 ATR, legs 1 / 2.5 / 3.75 / 5.62",
    "Martingale: double after a loss, up to x8", "Daily loss limit 2 R",
)


def table_summary(d: pd.DataFrame, kind: str) -> str:
    """One entry list, both symbols side by side, a few rows of each family; DEV / CONFIRM in each cell."""
    d = d[d["list"] == kind]
    symbols = [sym for sym in SYMBOLS if (d["symbol"] == sym).any()] or sorted(d["symbol"].unique())
    header = ["Mechanism"]
    for sym in symbols:
        who = SYMBOL_LABEL.get(sym, sym)
        header += [f"{who}: expectancy per entry (± s.e.)", f"{who}: win %", f"{who}: worst basket", f"{who}: worst floating loss",
                   f"{who}: $2,000 account emptied"]
    body = []
    for name in SUMMARY_ROWS:
        row = [name]
        for sym in symbols:
            per = _rows(d[d["symbol"] == sym], name)
            row += [_cell(per, lambda r: _usd(r["exp"])) + " (± " + _cell(per, lambda r: f"{r['se']:.2f}") + ")",
                    _cell(per, lambda r: f"{r['win_pct']:.0f}"), _cell(per, lambda r: _usd(r["worst"], 0)),
                    _cell(per, lambda r: _usd(r["worst_mae"], 0)), _cell(per, lambda r: r["acct_wiped_by"] if r["acct_wiped"] else "no")]
        body.append(row)
    return _md(header, body)


def table_overview(d: pd.DataFrame) -> str:
    """Every mechanism across all symbols, entry lists and periods at once: what stays the same and what does not."""
    cells = d.groupby(["symbol", "period", "list"]).ngroups
    symbols = [sym for sym in SYMBOLS if (d["symbol"] == sym).any()] or sorted(d["symbol"].unique())
    names = " / ".join(SYMBOL_LABEL.get(sym, sym) for sym in symbols)
    header = ["Mechanism", "Win %, lowest to highest", "Expectancy per entry in % of the median R, lowest to highest",
              f"Expectancy above zero (of {cells})", "Units opened per entry", f"Worst basket, {names}",
              f"Worst floating loss, {names}", f"$2,000 account emptied (of {cells})", "of which by one basket"]
    body, group = [], None
    for name in _names(d):
        g = d[d["mechanism"] == name]
        if g["group"].iloc[0] != group:
            group = g["group"].iloc[0]
            body.append([f"**{group}**"] + [""] * (len(header) - 1))
        r = g["exp"] / g["risk_usd"] * 100.0           # in units of the cell's median R, so that gold and BTC share one scale
        body.append([
            name, f"{g['win_pct'].min():.0f} to {g['win_pct'].max():.0f}", f"{r.min():+.1f} to {r.max():+.1f}",
            str(int((g["exp"] > 0).sum())), f"{g['avg_units_opened'].min():.1f} to {g['avg_units_opened'].max():.1f}",
            " / ".join(_usd(g[g["symbol"] == sym]["worst"].min(), 0) for sym in symbols),
            " / ".join(_usd(g[g["symbol"] == sym]["worst_mae"].min(), 0) for sym in symbols),
            str(int(g["acct_wiped"].sum())), str(int((g["acct_wiped_by"] == "one basket").sum()))])
    return _md(header, body)


def table_cost(d: pd.DataFrame, symbol: str, kind: str = "random") -> str:
    """Where the result of each mechanism comes from: the spread it pays against what it makes before the spread."""
    d = d[(d["symbol"] == symbol) & (d["list"] == kind)]
    header = ["Mechanism", "Units opened per entry", "Spread paid per entry", "Result before spread (± s.e.)", "Result after spread"]
    body = []
    for name in _names(d):
        per = _rows(d, name)
        body.append([name, _cell(per, lambda r: f"{r['avg_units_opened']:.2f}"), _cell(per, lambda r: f"{r['spread_paid']:.2f}"),
                     _cell(per, lambda r: _usd(r["gross"])) + " (± " + _cell(per, lambda r: f"{r['gross_se']:.2f}") + ")",
                     _cell(per, lambda r: _usd(r["exp"]))])
    return _md(header, body)


def table_halves(hv: pd.DataFrame, symbol: str, kind: str) -> str:
    """Expectancy per entry by half-year (entries of the list in the header)."""
    hv = hv[(hv["symbol"] == symbol) & (hv["list"] == kind)]
    cols = [(per, hf) for per in PERIODS for hf in sorted(hv[hv["period"] == per]["half"].unique())]
    ref = hv[hv["order"] == 0]
    header = ["Mechanism"] + [f"{per} {hf} (n={int(ref[(ref['period'] == per) & (ref['half'] == hf)]['n'].iloc[0]):,})"
                              for per, hf in cols]
    body = []
    for name in _names(hv):
        cells = []
        for per, hf in cols:
            r = hv[(hv["mechanism"] == name) & (hv["period"] == per) & (hv["half"] == hf)]
            cells.append(f"{_usd(r['exp'].iloc[0])} (± {r['se'].iloc[0]:.2f})" if len(r) and r["n"].iloc[0] > 0 else "n/a")
        body.append([name] + cells)
    return _md(header, body)


def table_change(d: pd.DataFrame, symbol: str, kind: str) -> str:
    """What each mechanism changes against the row it is compared with, entry by entry."""
    d = d[(d["symbol"] == symbol) & (d["list"] == kind) & d["control"].notna()]
    header = ["Mechanism", "Compared with", "Change in expectancy per entry (± s.e.)"]
    body = []
    for name in _names(d):
        per = _rows(d, name)
        body.append([name, str(next(iter(per.values()))["control"]),
                     _cell(per, lambda r: _usd(r["chg"])) + " (± " + _cell(per, lambda r: f"{r['chg_se']:.2f}") + ")"])
    return _md(header, body)


def table_order(d: pd.DataFrame, symbol: str, kind: str) -> str:
    """How much the expectancy, and the fate of the account, depend on the order assumed inside a bar (* = account wiped)."""
    d = d[(d["symbol"] == symbol) & (d["list"] == kind)]
    header = ["Mechanism", "Unfavourable extreme first (the result)", "Favourable extreme first", "Shortest path", "Widest gap"]
    tags = [""] + [f"_{tag}" for tag in OTHER_READINGS]
    body = []
    for name in _names(d):
        per = _rows(d, name)
        body.append([name] + [_cell(per, lambda r, t=t: _usd(r["exp" + t]) + ("*" if r["acct_wiped" + t] else "")) for t in tags]
                    + [_cell(per, lambda r: f"{max(r['exp' + t] for t in tags) - min(r['exp' + t] for t in tags):.2f}")])
    return _md(header, body)


def table_design(d: pd.DataFrame) -> str:
    """The mechanisms with the largest position and the worst loss each can produce by its own rules."""
    d = d.drop_duplicates("mechanism").sort_values("order")
    header = ["Mechanism", "Largest position (x 0.01 lot)", "Worst loss of one basket by design"]
    body, group = [], None
    for _, r in d.iterrows():
        if r["group"] != group:
            group = r["group"]
            body.append([f"**{group}**", "", ""])
        body.append([r["mechanism"], str(r["position"]), str(r["worst_by_design"])])
    return _md(header, body)


def table_adds(d: pd.DataFrame, symbol: str, kind: str) -> str:
    """Only the baskets in which a mechanism added: how they ended with the adds and how the same baskets ended without."""
    d = d[(d["symbol"] == symbol) & (d["list"] == kind) & d["added_n"].notna()]
    header = ["Mechanism", "Compared with", "Baskets with an add", "Won without the adds, %", "Won with them, %",
              "Mean result without", "Mean result with", "Difference (± s.e.)"]
    body = []
    for name in _names(d):
        per = _rows(d, name)
        body.append([name, str(next(iter(per.values()))["control"]), _cell(per, lambda r: f"{int(r['added_n']):,}"),
                     _cell(per, lambda r: f"{r['added_ctrl_win_pct']:.0f}"), _cell(per, lambda r: f"{r['added_win_pct']:.0f}"),
                     _cell(per, lambda r: _usd(r["added_ctrl_exp"])), _cell(per, lambda r: _usd(r["added_exp"])),
                     _cell(per, lambda r: _usd(r["added_exp"] - r["added_ctrl_exp"]))
                     + " (± " + _cell(per, lambda r: f"{r['added_chg_se']:.2f}") + ")"])
    return _md(header, body)


def table_budget(d: pd.DataFrame, symbol: str) -> str:
    """For the mechanisms built around a fixed loss: how often a basket lost more than that, and by how much (the three lists together)."""
    d = d[(d["symbol"] == symbol) & d["over_budget_n"].notna()]
    header = ["Mechanism", "Baskets", "Largest budget of one basket", "Baskets that lost more than their budget",
              "Largest loss beyond the budget", "Worst basket"]
    body = []
    for name in _names(d):
        per = {p: d[(d["mechanism"] == name) & (d["period"] == p)] for p in PERIODS if ((d["mechanism"] == name) & (d["period"] == p)).any()}
        body.append([name, _cell(per, lambda g: f"{int(g['n'].sum()):,}"), _cell(per, lambda g: f"${g['budget_max'].max():,.0f}"),
                     _cell(per, lambda g: f"{int(g['over_budget_n'].sum()):,}"), _cell(per, lambda g: f"${g['over_budget_max'].max():,.2f}"),
                     _cell(per, lambda g: _usd(g["worst"].min(), 1))])
    return _md(header, body)


def table_gaps(g: pd.DataFrame, symbol: str) -> str:
    """Price jumps over market closures, in USD on 0.01 lot and in R (the ATR of the hour before the closure)."""
    g = g[g["symbol"] == symbol]
    header = ["Closure", "Period", "Closures", "Median jump", "99th percentile", "Largest", "Largest, in R"]
    body = [[r["closure"], r["period"], f"{int(r['n']):,}", f"${r['median_usd']:.2f}", f"${r['p99_usd']:.2f}", f"${r['max_usd']:.2f}",
             f"{r['max_r']:.1f}"] for _, r in g.iterrows()]
    return _md(header, body)


TABLES = {"main": table_main, "cost": table_cost, "change": table_change, "order": table_order, "adds": table_adds}


def render(tag: str, out: Path = OUT) -> str:
    """
    The table named by a marker of the report: ``design``, ``overview``, ``summary:list``, ``main:SYMBOL:list``, ``cost:SYMBOL[:list]``,
    ``change:SYMBOL:list``, ``adds:SYMBOL:list``, ``order:SYMBOL:list``, ``halves:SYMBOL:list``, ``gaps:SYMBOL``
    or ``budget:SYMBOL``.
    """
    d = pd.read_csv(out / "recovery_mechanisms.csv", keep_default_na=False, na_values=[""])
    for col in ("acct_wiped_on", "acct_wiped_by"):
        d[col] = d[col].fillna("")
    parts = tag.split(":")
    if parts[0] == "design":
        return table_design(d)
    if parts[0] == "summary":
        return table_summary(d, parts[1])
    if parts[0] == "overview":
        return table_overview(d)
    if parts[0] == "halves":
        return table_halves(pd.read_csv(out / "recovery_mechanisms_halfyears.csv"), parts[1], parts[2])
    if parts[0] == "gaps":
        return table_gaps(pd.read_csv(out / "recovery_mechanisms_gaps.csv"), parts[1])
    if parts[0] == "budget":
        return table_budget(d, parts[1])
    return TABLES[parts[0]](d, *parts[1:])


_MARK = re.compile(r"(<!-- table (?P<tag>[^ ]+) -->\n).*?(<!-- /table -->)", re.S)


def update_report(path: Path, out: Path = OUT) -> int:
    """Rewrite every ``<!-- table TAG --> ... <!-- /table -->`` block of the report from the result files."""
    text = Path(path).read_text(encoding="utf-8")
    new, count = _MARK.subn(lambda mt: mt.group(1) + render(mt.group("tag"), out) + "\n" + mt.group(3), text)
    Path(path).write_text(new, encoding="utf-8")
    return count


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.recovery", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="simulate every mechanism on every entry list and write the result files")
    r.add_argument("--symbols", nargs="+", default=["XAUUSDm", "BTCUSDm"])
    r.add_argument("--periods", nargs="+", default=list(PERIODS), choices=list(PERIODS))
    r.add_argument("--cache", type=Path, default=None,
                   help="directory in which the frames are kept between runs and the per-basket results are written "
                        "(empty it after changing the code or the tick store)")
    r.add_argument("--out", type=Path, default=OUT)
    t = sub.add_parser("tables", help="print the tables, or refresh them inside the report")
    t.add_argument("--update", type=Path, default=None, help="report whose table blocks are rewritten in place")
    t.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.symbols, a.periods, a.out, a.cache)
    elif a.update:
        print(f"{update_report(a.update, a.out)} tables refreshed in {a.update}")
    else:
        d = pd.read_csv(a.out / "recovery_mechanisms.csv")
        for sym in d["symbol"].unique():
            for kind in LISTS:
                print(f"\n## {sym}: {LISTS[kind]}\n\n{render(f'main:{sym}:{kind}', a.out)}")


if __name__ == "__main__":
    main()
