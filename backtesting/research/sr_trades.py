"""
Support and resistance as a trading rule, measured against placebo levels.

    python -m backtesting.research.sr_trades run    DEV [--sets all | base,"wide stop",...] [--symbols ...] [--out DIR]
    python -m backtesting.research.sr_trades tables DEV [CONFIRM] [--out DIR]     # markdown tables from the stored runs
    python -m backtesting.research.sr_trades levels DEV [--symbols ...]           # how many levels there are, and how dense

The results and what they mean are in ``backtest_results/improve/sr_trades.md``.

The question is whether higher-timeframe support / resistance levels, traded the way a chartist
trades them, make money after the spread, and whether the levels themselves are what makes it.

How it works
------------
* Bars. M1 bid bars from the tick store are aggregated here to M15, H1, H4, D1 (UTC days; a day
  with under six hours of quotes, such as gold's Sunday evening, is merged into the next day) and
  W1 (weeks starting Sunday 00:00 UTC, as the terminal draws them).
* Levels. Swing highs and lows on H1, H4 and D1 (a bar whose high is above the k bars before it
  and not below the k bars after it; known only when the k-th bar after it has closed), the
  previous day's high and low and the previous week's high and low. Levels that fall within a
  small distance of each other are one zone; the zone remembers which sources it holds.
* Level state. A zone is support while price is above it and resistance while price is below.
  An H1 close beyond the zone is a break and turns its role; a second break retires it. A zone is
  "armed" once an M1 bar has closed a set distance away from it, so that the next arrival is a
  real return and not a wiggle.
* Events. TOUCH: an M1 bar reaches an armed zone from its current side. REVERSAL: an M15 bar
  reaches the zone and closes back beyond the level in the bounce direction. BREAK: an H1 bar
  closes beyond the zone.
* Rules. Each rule is a filter on those events (trend, flat market, confirmations) plus one
  common stop / target geometry in units of the H1 ATR. See ``RULES``.
* Simulator. One position at a time per rule; entry at the close of the event's M1 bar (or, as a
  variant, at the touch itself), at the ask for a buy and the bid for a sell; from the next bar on
  the stop is checked before the target inside every M1 bar; optional time stop.
* Placebo. The same zones (same times, same lifetimes, same sources) moved to prices that are not
  levels: each zone shifted up or down by a random 1 to 3 ATR, away from every real zone live at
  that moment. The same rules are run on several such sets. If real levels do no better than the
  placebo levels, the level is not what produces the result.

Every number a decision uses comes from bars that had closed by the decision time (the close of an
M1 bar); ``tests/test_sr_trades.py`` checks that by recomputing on truncated history.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from numba import njit

from ..data import store

UNIT_USD = {"XAUUSDm": 1.0, "BTCUSDm": 0.01}          # USD per 1.0 of price on a 0.01 lot
SYMBOLS = ("XAUUSDm", "BTCUSDm")

# [start, end) in UTC. Nothing before EARLIEST is ever read.
PERIODS = {"DEV": ("2025-07-01", "2026-11-13"), "CONFIRM": ("2024-01-01", "2025-07-01")}
EARLIEST = "2024-01-01"
WARMUP_DAYS = 31            # the first days of a period only warm the indicators and the level book up

DAY, WEEK = 86400, 604800
WEEK_SHIFT = 3 * DAY        # 1970-01-04 was a Sunday: weeks are counted from Sunday 00:00 UTC

SRC_H1, SRC_H4, SRC_D1, SRC_PD, SRC_PW = 0, 1, 2, 3, 4
SRC_NAMES = ("H1 swing", "H4 swing", "D1 swing", "previous day", "previous week")
EV_TOUCH, EV_REV, EV_BREAK = 0, 1, 2
EXIT_STOP, EXIT_TARGET, EXIT_TIME, EXIT_END = 1, 2, 3, 4


# ───────────────────────────── parameters ─────────────────────────────

@dataclass(frozen=True)
class LevelParams:
    """How levels are found. Distances are in units of the H1 ATR at the moment a level becomes known."""
    k_h1: int = 5            # bars on each side of an H1 swing
    k_h4: int = 3
    k_d1: int = 2
    life_h1_d: float = 5.0   # days a swing level stays on the chart after it is confirmed
    life_h4_d: float = 20.0
    life_d1_d: float = 90.0
    merge_w: float = 0.15    # levels this close to an existing zone join it
    day_min_bars: int = 360  # a UTC day with fewer M1 bars is merged into the next day


@dataclass(frozen=True)
class Params:
    """How levels are traded. Widths are in units of the H1 ATR of the last closed H1 bar."""
    zone_w: float = 0.15       # half-width of the zone around a level
    arm_w: float = 1.0         # an M1 close this far from the level arms it for the next arrival
    stop_w: float = 0.35       # the stop sits this far beyond the far edge of the zone
    target_r: float = 2.0      # target = this multiple of the risk (entry to stop)
    max_hold_h: float = 24.0   # time stop in hours (0 = none)
    spread_cap_w: float = 0.10  # no entry on a bar whose mean spread is wider than this
    min_risk_w: float = 0.10   # no entry when the stop would be nearer than this ...
    max_risk_w: float = 1.50   # ... or farther than this (a close that has already run away)
    trend: str = "H4"          # "H4": sign of the H4 MACD(12,26,9) signal line; "D1": D1 close against its 20-bar EMA
    adx_flat: float = 20.0     # "flat" = H4 ADX(14) below this
    rsi_low: float = 35.0      # RSI confirmation: M15 RSI(14) below this for a buy ...
    rsi_high: float = 65.0     # ... above this for a sell
    entry: str = "close"       # "close": a market order at the close of the event's M1 bar;
                               # "touch": bounces and retests are entered the moment the bid reaches the zone


@dataclass(frozen=True)
class Rule:
    """A filter on level events. ``breaks`` is how often the zone had been broken before the event."""
    key: str
    label: str
    event: int = EV_TOUCH
    breaks: int = 0
    trend: int = 0             # +1 only with the trend, -1 only against it, 0 either
    flat: bool = False         # only while the higher timeframe is flat
    first_return: bool = False  # only the first arrival since the break
    rsi: bool = False          # RSI confirmation at the event
    div: bool = False          # RSI divergence against the previous M15 swing
    min_src: int = 1           # at least this many level sources in the zone
    touches: int = -1          # 0: never touched before; 1: touched at least once before; -1: either
    tf_class: int = 0          # the highest timeframe in the zone: 1 = H1 swing / previous day only,
                               # 2 = an H4 swing, 3 = a D1 swing or a previous-week level; 0 = any


def _confirmations(base: Rule) -> List[Rule]:
    """The rule once more with each of the six confirmations a chartist would add."""
    k, l = base.key, base.label
    return [
        replace(base, key=k + ".rsi", label=l + " + M15 RSI below 35 / above 65", rsi=True),
        replace(base, key=k + ".div", label=l + " + RSI divergence", div=True),
        replace(base, key=k + ".rev", label=l + " + M15 reversal bar as the trigger", event=EV_REV),
        replace(base, key=k + ".src2", label=l + " + zone holds 2 or more sources", min_src=2),
        replace(base, key=k + ".fresh", label=l + " + first touch of the level", touches=0),
        replace(base, key=k + ".tested", label=l + " + level touched before", touches=1),
    ]


def _by_timeframe(base: Rule) -> List[Rule]:
    """The rule on one class of level at a time, by the highest timeframe the zone holds."""
    k, l = base.key, base.label
    return [
        replace(base, key=k + ".h1", label=l + ", level from H1 swings / previous day only", tf_class=1),
        replace(base, key=k + ".h4", label=l + ", level holds an H4 swing", tf_class=2),
        replace(base, key=k + ".d1", label=l + ", level holds a D1 swing or a weekly high / low", tf_class=3),
    ]


_A = Rule("a", "Bounce with the trend", trend=+1)
_B2 = Rule("b2", "Bounce, any trend")
_D = Rule("d", "Breakout on the H1 close", event=EV_BREAK)
RULES: Tuple[Rule, ...] = (
    _A,
    Rule("b1", "Bounce against the trend", trend=-1),
    _B2,
    Rule("c", "Break and retest", breaks=1, first_return=True),
    Rule("c+", "Break and retest, with the trend", breaks=1, first_return=True, trend=+1),
    _D,
    Rule("d+", "Breakout on the H1 close, with the trend", event=EV_BREAK, trend=+1),
    Rule("e", "Range fade (H4 flat)", flat=True),
    *_confirmations(_A),
    *_confirmations(_B2),
    *_by_timeframe(_B2),
    *_by_timeframe(_D),
)
RULE_BY_KEY = {r.key: r for r in RULES}

# The parameter sets tried on DEV: the base and one change at a time around it.
PARAM_SETS: Dict[str, Tuple[LevelParams, Params]] = {
    "base": (LevelParams(), Params()),
    "target 0.25R": (LevelParams(), Params(target_r=0.25)),
    "target 1R": (LevelParams(), Params(target_r=1.0)),
    "target 3R": (LevelParams(), Params(target_r=3.0)),
    "wide stop": (LevelParams(), Params(stop_w=0.85)),
    "wide zone": (LevelParams(), Params(zone_w=0.30)),
    "narrow zone": (LevelParams(), Params(zone_w=0.05, stop_w=0.45)),
    "hold 72h": (LevelParams(), Params(max_hold_h=72.0)),
    "trend D1": (LevelParams(), Params(trend="D1")),
    "major swings": (LevelParams(k_h1=8, k_h4=5, k_d1=3), Params()),
    "arm 0.5": (LevelParams(), Params(arm_w=0.5)),
    "enter on the touch": (LevelParams(), Params(entry="touch")),
}
# The base rules and parameters against another choice of placebo prices: the shift alone, no draw rejected.
PLACEBO_SETS: Dict[str, Dict[str, float]] = {"plain placebo": dict(sep_real=0.0, sep_placebo=0.0)}
ALL_SETS: Tuple[str, ...] = tuple(PARAM_SETS) + tuple(PLACEBO_SETS)


# ───────────────────────────── bars ─────────────────────────────

@dataclass
class Bars:
    """Bars of one timeframe. ``tc`` is the time from which a bar is closed and may be used."""
    t: np.ndarray
    tc: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray

    def __len__(self) -> int:
        return len(self.t)


def _aggregate(t: np.ndarray, o, h, l, c, bucket: np.ndarray, t_open: np.ndarray, t_close: np.ndarray) -> Bars:
    """OHLC of consecutive M1 bars sharing a bucket id; ``t_open`` / ``t_close`` are given per M1 bar."""
    if len(t) == 0:
        z = np.zeros(0)
        return Bars(np.zeros(0, np.int64), np.zeros(0, np.int64), z, z, z, z)
    first = np.flatnonzero(np.diff(bucket, prepend=bucket[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bucket) - 1)
    return Bars(t_open[first].astype(np.int64), t_close[first].astype(np.int64), o[first].copy(),
                np.maximum.reduceat(h, first), np.minimum.reduceat(l, first), c[last].copy())


def tf_bars(m1: Dict[str, np.ndarray], tf_s: int) -> Bars:
    """Bars on plain UTC boundaries (M15, H1, H4), as the terminal builds them from the bid."""
    b = m1["t"] // tf_s
    return _aggregate(m1["t"], m1["o"], m1["h"], m1["l"], m1["c"], b, b * tf_s, b * tf_s + tf_s)


def week_bars(m1: Dict[str, np.ndarray]) -> Bars:
    """Weeks from Sunday 00:00 UTC."""
    b = (m1["t"] - WEEK_SHIFT) // WEEK
    return _aggregate(m1["t"], m1["o"], m1["h"], m1["l"], m1["c"], b, b * WEEK + WEEK_SHIFT, b * WEEK + WEEK_SHIFT + WEEK)


def day_bars(m1: Dict[str, np.ndarray], min_bars: int = 360) -> Bars:
    """
    UTC days. A day with fewer than ``min_bars`` M1 bars (gold's Sunday evening, a holiday stub) is
    not a day of its own: it is merged into the next full day, and the merged bar closes when that
    day ends. Short days after the last full day form no bar yet.
    """
    t = m1["t"]
    if len(t) == 0:
        return tf_bars(m1, DAY)
    day = t // DAY
    first = np.flatnonzero(np.diff(day, prepend=day[0] - 1) != 0)
    count = np.diff(np.append(first, len(day)))
    days = day[first]
    group = np.empty(len(days), np.int64)
    opens, closes = [], []
    g, start = 0, -1
    for d in range(len(days)):
        if start < 0:
            start = int(days[d])
        group[d] = g
        if count[d] >= min_bars:
            opens.append(start * DAY)
            closes.append((int(days[d]) + 1) * DAY)
            g, start = g + 1, -1
    per_bar = np.repeat(group, count)
    keep = per_bar < g
    per_bar = per_bar[keep]
    if len(per_bar) == 0:
        z = np.zeros(0)
        return Bars(np.zeros(0, np.int64), np.zeros(0, np.int64), z, z, z, z)
    opens, closes = np.asarray(opens, np.int64), np.asarray(closes, np.int64)
    return _aggregate(t[keep], m1["o"][keep], m1["h"][keep], m1["l"][keep], m1["c"][keep],
                      per_bar, opens[per_bar], closes[per_bar])


def last_closed(tc: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Index of the last bar closed by each time in ``T`` (-1 where none has closed yet)."""
    return np.searchsorted(tc, T, side="right") - 1


# ───────────────────────────── indicators ─────────────────────────────

@njit(cache=True)
def _rma(x, n):
    """Wilder's moving average, seeded with the plain mean of the first n values."""
    m = x.shape[0]
    out = np.full(m, np.nan)
    if m < n:
        return out
    s = 0.0
    for j in range(n):
        s += x[j]
    out[n - 1] = s / n
    for j in range(n, m):
        out[j] = (out[j - 1] * (n - 1) + x[j]) / n
    return out


@njit(cache=True)
def _ema(x, n, first):
    """EMA seeded with the plain mean of the n values starting at ``first``; NaN before the seed."""
    m = x.shape[0]
    out = np.full(m, np.nan)
    seed = first + n - 1
    if m <= seed:
        return out
    s = 0.0
    for j in range(first, seed + 1):
        s += x[j]
    out[seed] = s / n
    a = 2.0 / (n + 1.0)
    for j in range(seed + 1, m):
        out[j] = a * x[j] + (1.0 - a) * out[j - 1]
    return out


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder's average true range. The value of bar j uses bars up to j only."""
    if len(c) == 0:
        return np.zeros(0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h, pc) - np.minimum(l, pc)
    tr[0] = h[0] - l[0]
    return _rma(tr, n)


def macd_signal(c: np.ndarray, fast: int = 12, slow: int = 26, sig: int = 9) -> np.ndarray:
    """Signal line of the MACD (EMAs seeded with a plain mean, as the live indicator does)."""
    m = _ema(c, fast, 0) - _ema(c, slow, 0)
    return _ema(np.nan_to_num(m), sig, slow - 1) if len(c) else m


@njit(cache=True)
def adx(h, l, c, n=14):
    """Wilder's ADX. NaN until 2n bars have closed."""
    m = c.shape[0]
    out = np.full(m, np.nan)
    if m < 2 * n + 1:
        return out
    tr_s = 0.0
    p_s = 0.0
    m_s = 0.0
    dx_sum = 0.0
    prev = np.nan
    for j in range(1, m):
        up = h[j] - h[j - 1]
        dn = l[j - 1] - l[j]
        p = up if (up > dn and up > 0.0) else 0.0
        q = dn if (dn > up and dn > 0.0) else 0.0
        tr = max(h[j], c[j - 1]) - min(l[j], c[j - 1])
        if j <= n:
            tr_s += tr
            p_s += p
            m_s += q
            if j < n:
                continue
        else:
            tr_s += tr - tr_s / n
            p_s += p - p_s / n
            m_s += q - m_s / n
        if tr_s <= 0.0:
            dx = 0.0
        else:
            pdi = 100.0 * p_s / tr_s
            mdi = 100.0 * m_s / tr_s
            dx = 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0.0 else 0.0
        if j < 2 * n - 1:
            dx_sum += dx
        elif j == 2 * n - 1:
            dx_sum += dx
            prev = dx_sum / n
            out[j] = prev
        else:
            prev = (prev * (n - 1) + dx) / n
            out[j] = prev
    return out


@njit(cache=True)
def _rsi_state(c, n):
    """Wilder average gain and loss after each closed bar (NaN until n changes are known)."""
    m = c.shape[0]
    ag = np.full(m, np.nan)
    al = np.full(m, np.nan)
    if m <= n:
        return ag, al
    g = 0.0
    lo = 0.0
    for j in range(1, n + 1):
        d = c[j] - c[j - 1]
        if d > 0.0:
            g += d
        else:
            lo -= d
    ag[n] = g / n
    al[n] = lo / n
    for j in range(n + 1, m):
        d = c[j] - c[j - 1]
        ag[j] = (ag[j - 1] * (n - 1) + (d if d > 0.0 else 0.0)) / n
        al[j] = (al[j - 1] * (n - 1) + (-d if d < 0.0 else 0.0)) / n
    return ag, al


def _rsi_value(ag: np.ndarray, al: np.ndarray) -> np.ndarray:
    """RSI from the average gain and loss (100 when there is no loss, 50 when nothing moved)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - 100.0 / (1.0 + ag / al)
    return np.where(al == 0.0, np.where(ag == 0.0, 50.0, 100.0), r)


def swing_points(h: np.ndarray, l: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Indices of swing highs and swing lows. Bar j is a swing high when its high is above the highs
    of the k bars before it and not below the highs of the k bars after it (mirror for lows).
    The swing at j is known only once bar j + k has closed.
    """
    n = len(h)
    if n < 2 * k + 1:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    win = np.lib.stride_tricks.sliding_window_view
    j = np.arange(k, n - k)
    left_h, right_h = win(h, k)[: n - 2 * k].max(axis=1), win(h, k)[k + 1:].max(axis=1)
    left_l, right_l = win(l, k)[: n - 2 * k].min(axis=1), win(l, k)[k + 1:].min(axis=1)
    hi = j[(h[k: n - k] > left_h) & (h[k: n - k] >= right_h)]
    lo = j[(l[k: n - k] < left_l) & (l[k: n - k] <= right_l)]
    return hi, lo


@njit(cache=True)
def _divergence_state(h, l, rsi, k):
    """
    For each closed M15 bar j, as known at its close: the last confirmed swing low / high (index,
    -1 if none), the RSI trough / peak around that swing, and the lowest low and lowest RSI (highest
    high and highest RSI) of the bars after the swing's confirmation, up to and including j.
    """
    n = h.shape[0]
    lo_idx = np.full(n, -1)
    hi_idx = np.full(n, -1)
    lo_rsi = np.full(n, np.nan)
    hi_rsi = np.full(n, np.nan)
    leg_low = np.full(n, np.inf)
    leg_high = np.full(n, -np.inf)
    leg_rsi_lo = np.full(n, np.inf)
    leg_rsi_hi = np.full(n, -np.inf)
    cur_lo = -1
    cur_hi = -1
    cur_lo_rsi = np.nan
    cur_hi_rsi = np.nan
    run_low = np.inf
    run_high = -np.inf
    run_rsi_lo = np.inf
    run_rsi_hi = -np.inf
    for j in range(n):
        q = j - k
        new_lo = False
        new_hi = False
        if q >= k:
            is_lo = True
            is_hi = True
            for u in range(1, k + 1):
                if not (l[q] < l[q - u]) or not (l[q] <= l[q + u]):
                    is_lo = False
                if not (h[q] > h[q - u]) or not (h[q] >= h[q + u]):
                    is_hi = False
            if is_lo:
                new_lo = True
                cur_lo = q
                m = np.inf
                for u in range(q - k, q + k + 1):
                    if rsi[u] < m:
                        m = rsi[u]
                cur_lo_rsi = m
                run_low = np.inf
                run_rsi_lo = np.inf
            if is_hi:
                new_hi = True
                cur_hi = q
                m = -np.inf
                for u in range(q - k, q + k + 1):
                    if rsi[u] > m:
                        m = rsi[u]
                cur_hi_rsi = m
                run_high = -np.inf
                run_rsi_hi = -np.inf
        if cur_lo >= 0 and not new_lo:
            if l[j] < run_low:
                run_low = l[j]
            if rsi[j] < run_rsi_lo:
                run_rsi_lo = rsi[j]
        if cur_hi >= 0 and not new_hi:
            if h[j] > run_high:
                run_high = h[j]
            if rsi[j] > run_rsi_hi:
                run_rsi_hi = rsi[j]
        lo_idx[j] = cur_lo
        hi_idx[j] = cur_hi
        lo_rsi[j] = cur_lo_rsi
        hi_rsi[j] = cur_hi_rsi
        leg_low[j] = run_low
        leg_high[j] = run_high
        leg_rsi_lo[j] = run_rsi_lo
        leg_rsi_hi[j] = run_rsi_hi
    return lo_idx, hi_idx, lo_rsi, hi_rsi, leg_low, leg_high, leg_rsi_lo, leg_rsi_hi


@njit(cache=True)
def _running_extremes(bucket, h, l):
    """Highest high and lowest low of the M1 bars of the same bucket up to and including each bar."""
    n = h.shape[0]
    hi = np.empty(n)
    lo = np.empty(n)
    for i in range(n):
        if i > 0 and bucket[i] == bucket[i - 1]:
            hi[i] = h[i] if h[i] > hi[i - 1] else hi[i - 1]
            lo[i] = l[i] if l[i] < lo[i - 1] else lo[i - 1]
        else:
            hi[i] = h[i]
            lo[i] = l[i]
    return hi, lo


# ───────────────────────────── frames ─────────────────────────────

@dataclass
class Frames:
    """
    Everything a decision at the close of an M1 bar may use, per M1 bar. ``T`` is the decision
    time (bar open + 60 s); every higher-timeframe value is that of the last bar closed by ``T``.
    """
    symbol: str
    t: np.ndarray
    T: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    spread: np.ndarray
    atr: np.ndarray            # H1 ATR(14)
    trend_h4: np.ndarray       # sign of the H4 MACD signal line (0 while unknown)
    trend_d1: np.ndarray       # sign of D1 close minus its 20-bar EMA (0 while unknown)
    adx_h4: np.ndarray
    rsi15: np.ndarray          # M15 RSI(14), the forming bar valued at this M1 close
    bull_div: np.ndarray       # lower low than the previous M15 swing low on a higher RSI low
    bear_div: np.ndarray
    h1_new: np.ndarray         # an H1 bar has closed since the previous M1 close
    h1_c: np.ndarray           # close of the last closed H1 bar
    m15_new: np.ndarray
    m15_o: np.ndarray
    m15_h: np.ndarray
    m15_l: np.ndarray
    m15_c: np.ndarray
    h1: Bars
    h4: Bars
    d1: Bars
    w1: Bars
    h1_atr: np.ndarray         # ATR per H1 bar (for sizing a level when it becomes known)
    eval_start: int            # entries are taken from here ...
    eval_end: int              # ... up to here (epoch s)

    def __len__(self) -> int:
        return len(self.t)


def _take(values: np.ndarray, idx: np.ndarray, fill=np.nan) -> np.ndarray:
    """``values[idx]`` with ``fill`` where the index is -1 (no bar has closed yet)."""
    out = np.full(len(idx), fill, dtype=np.result_type(values.dtype, type(fill)))
    ok = idx >= 0
    out[ok] = values[idx[ok]]
    return out


def _new_flag(idx: np.ndarray) -> np.ndarray:
    """True on the M1 bars at whose close a further bar of the slower timeframe has become available."""
    out = np.zeros(len(idx), np.bool_)
    if len(idx) > 1:
        out[1:] = (idx[1:] != idx[:-1]) & (idx[1:] >= 0)
    return out


def build_frames(symbol: str, m1: Dict[str, np.ndarray], lp: LevelParams = LevelParams(),
                 eval_start: Optional[int] = None, eval_end: Optional[int] = None,
                 rsi_len: int = 14, div_k: int = 3, div_lookback: int = 48, div_margin: float = 2.0) -> Frames:
    """Bars of every timeframe and the per-M1 decision context, from M1 bars alone."""
    t = np.asarray(m1["t"], np.int64)
    o, h, l, c = (np.asarray(m1[k], np.float64) for k in ("o", "h", "l", "c"))
    spread = np.asarray(m1["spread_mean"], np.float64)
    T = t + 60
    m15, h1, h4 = tf_bars(m1, 900), tf_bars(m1, 3600), tf_bars(m1, 14400)
    d1, w1 = day_bars(m1, lp.day_min_bars), week_bars(m1)

    i_h1, i_h4, i_d1, i_15 = (last_closed(b.tc, T) for b in (h1, h4, d1, m15))
    h1_atr = atr(h1.h, h1.l, h1.c)
    sig = macd_signal(h4.c)
    trend_h4 = np.nan_to_num(np.sign(_take(sig, i_h4))).astype(np.int8)
    d1_dev = d1.c - _ema(d1.c, 20, 0) if len(d1) else np.zeros(0)
    trend_d1 = np.nan_to_num(np.sign(_take(d1_dev, i_d1))).astype(np.int8)
    adx_h4 = _take(adx(h4.h, h4.l, h4.c, 14), i_h4)

    # M15 RSI with the forming bar valued at the M1 close (equal to the closed-bar RSI on a bar close)
    ag, al = _rsi_state(m15.c, rsi_len)
    rsi_closed = _rsi_value(ag, al)
    d = c - _take(m15.c, i_15)
    ag_now = (_take(ag, i_15) * (rsi_len - 1) + np.maximum(d, 0.0)) / rsi_len
    al_now = (_take(al, i_15) * (rsi_len - 1) + np.maximum(-d, 0.0)) / rsi_len
    rsi15 = _rsi_value(ag_now, al_now)

    # divergence against the previous M15 swing, the current leg including the forming bar
    lo_idx, hi_idx, lo_rsi, hi_rsi, leg_low, leg_high, leg_rsi_lo, leg_rsi_hi = _divergence_state(
        m15.h, m15.l, np.nan_to_num(rsi_closed, nan=50.0), div_k)
    forming = (t % 900) != 840                      # this M1 bar does not end its M15 bar
    run_hi, run_lo = _running_extremes(t // 900, h, l)
    sw_lo, sw_hi = _take(lo_idx, i_15, -1), _take(hi_idx, i_15, -1)
    low_now = np.where(forming, np.minimum(_take(leg_low, i_15, np.inf), run_lo), _take(leg_low, i_15, np.inf))
    high_now = np.where(forming, np.maximum(_take(leg_high, i_15, -np.inf), run_hi), _take(leg_high, i_15, -np.inf))
    rsi_lo_now = np.where(forming, np.fmin(_take(leg_rsi_lo, i_15, np.inf), rsi15), _take(leg_rsi_lo, i_15, np.inf))
    rsi_hi_now = np.where(forming, np.fmax(_take(leg_rsi_hi, i_15, -np.inf), rsi15), _take(leg_rsi_hi, i_15, -np.inf))
    with np.errstate(invalid="ignore"):
        bull = (sw_lo >= 0) & (i_15 - sw_lo <= div_lookback) & (low_now < _take(m15.l, sw_lo)) \
            & np.isfinite(rsi_lo_now) & (rsi_lo_now > _take(lo_rsi, i_15) + div_margin)
        bear = (sw_hi >= 0) & (i_15 - sw_hi <= div_lookback) & (high_now > _take(m15.h, sw_hi)) \
            & np.isfinite(rsi_hi_now) & (rsi_hi_now < _take(hi_rsi, i_15) - div_margin)

    return Frames(
        symbol=symbol, t=t, T=T, o=o, h=h, l=l, c=c, spread=spread,
        atr=_take(h1_atr, i_h1), trend_h4=trend_h4, trend_d1=trend_d1, adx_h4=adx_h4, rsi15=rsi15,
        bull_div=bull, bear_div=bear,
        h1_new=_new_flag(i_h1), h1_c=_take(h1.c, i_h1),
        m15_new=_new_flag(i_15), m15_o=_take(m15.o, i_15), m15_h=_take(m15.h, i_15),
        m15_l=_take(m15.l, i_15), m15_c=_take(m15.c, i_15),
        h1=h1, h4=h4, d1=d1, w1=w1, h1_atr=h1_atr,
        eval_start=int(t[0]) if eval_start is None else int(eval_start),
        eval_end=int(T[-1]) + 1 if eval_end is None else int(eval_end),
    )


def load_frames(symbol: str, period: str, lp: LevelParams = LevelParams()) -> Frames:
    """Frames of one of the named periods, read from the tick store."""
    a, z = PERIODS[period]
    if store.to_ms(a) < store.to_ms(EARLIEST):
        raise ValueError(f"nothing before {EARLIEST} may be read")
    m1 = store.load_m1(symbol, store.to_ms(a), store.to_ms(z))
    if not m1:
        raise FileNotFoundError(f"no M1 bars for {symbol} in {a} .. {z}")
    start = store.to_ms(a) // 1000
    return build_frames(symbol, m1, lp, eval_start=start + WARMUP_DAYS * DAY, eval_end=store.to_ms(z) // 1000)


# ───────────────────────────── levels and zones ─────────────────────────────

@dataclass
class Zones:
    """
    Zones in the order they were founded, and the levels that joined them.

    ``price`` / ``t`` / ``atr``: the founding level's price, the time it became known and the H1 ATR
    then. ``expire``: when the last level of the zone has aged out. ``j_*``: one row per level, in
    time order: when it became known, the zone it joined (or founded), its source and its own expiry.
    """
    price: np.ndarray
    t: np.ndarray
    atr: np.ndarray
    expire: np.ndarray
    kind: np.ndarray           # +1 founded by a high, -1 by a low
    j_t: np.ndarray
    j_zone: np.ndarray
    j_src: np.ndarray
    j_exp: np.ndarray

    def __len__(self) -> int:
        return len(self.price)


def raw_levels(fr: Frames, lp: LevelParams = LevelParams()) -> Dict[str, np.ndarray]:
    """
    Every level with the time it becomes known: swing highs / lows of H1, H4 and D1 (known when the
    k-th bar after the swing has closed), the high and low of each finished day (valid until the
    next day has finished) and of each finished week (valid until the next week has finished).
    """
    rows: List[Tuple[int, float, int, int, int]] = []          # t_known, price, source, kind, expiry

    def swings(b: Bars, k: int, src: int, life_d: float) -> None:
        hi, lo = swing_points(b.h, b.l, k)
        for idx, price, kind in ((hi, b.h, 1), (lo, b.l, -1)):
            for j in idx:
                known = int(b.tc[j + k])
                rows.append((known, float(price[j]), src, kind, known + int(life_d * DAY)))

    def previous(b: Bars, src: int, default_life: int) -> None:
        for j in range(len(b)):
            known = int(b.tc[j])
            expiry = int(b.tc[j + 1]) if j + 1 < len(b) else known + default_life
            rows.append((known, float(b.h[j]), src, 1, expiry))
            rows.append((known, float(b.l[j]), src, -1, expiry))

    swings(fr.h1, lp.k_h1, SRC_H1, lp.life_h1_d)
    swings(fr.h4, lp.k_h4, SRC_H4, lp.life_h4_d)
    swings(fr.d1, lp.k_d1, SRC_D1, lp.life_d1_d)
    previous(fr.d1, SRC_PD, 30 * DAY)
    previous(fr.w1, SRC_PW, 30 * DAY)

    a = np.array(rows, dtype=np.float64).reshape(-1, 5)
    t_known = a[:, 0].astype(np.int64)
    at = _take(fr.h1_atr, last_closed(fr.h1.tc, t_known))
    ok = np.isfinite(at) & (at > 0)
    a, t_known, at = a[ok], t_known[ok], at[ok]
    order = np.lexsort((a[:, 1], a[:, 3], a[:, 2], t_known))
    a, t_known, at = a[order], t_known[order], at[order]
    return {"t": t_known, "price": a[:, 1].copy(), "src": a[:, 2].astype(np.int64),
            "kind": a[:, 3].astype(np.int64), "expire": a[:, 4].astype(np.int64), "atr": at}


def build_zones(raw: Dict[str, np.ndarray], lp: LevelParams = LevelParams()) -> Zones:
    """
    Group levels into zones, in time order. A level that becomes known within ``merge_w`` ATR of a
    zone that has not aged out joins it (the nearest one); otherwise it founds a new zone at its
    own price. A zone keeps the price of its founding level.
    """
    zp: List[float] = []
    zt: List[int] = []
    za: List[float] = []
    ze: List[int] = []
    zk: List[int] = []
    alive: List[int] = []
    j_zone = np.empty(len(raw["t"]), np.int64)
    for r in range(len(raw["t"])):
        t, p, a, e = int(raw["t"][r]), float(raw["price"][r]), float(raw["atr"][r]), int(raw["expire"][r])
        alive = [q for q in alive if ze[q] > t]
        best, best_d = -1, lp.merge_w * a
        for q in alive:
            dist = abs(zp[q] - p)
            if dist < best_d or (dist == best_d and best < 0):
                best, best_d = q, dist
        if best < 0:
            best = len(zp)
            zp.append(p); zt.append(t); za.append(a); ze.append(e); zk.append(int(raw["kind"][r]))
            alive.append(best)
        elif e > ze[best]:
            ze[best] = e
        j_zone[r] = best
    return Zones(np.asarray(zp, np.float64), np.asarray(zt, np.int64), np.asarray(za, np.float64),
                 np.asarray(ze, np.int64), np.asarray(zk, np.int64),
                 raw["t"].copy(), j_zone, raw["src"].copy(), raw["expire"].copy())


def placebo_prices(z: Zones, seed: int, live: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None,
                   lo: float = 1.0, hi: float = 3.0, sep_real: float = 0.5, sep_placebo: float = 0.15,
                   tries: int = 200) -> np.ndarray:
    """
    A price that is not a level for every zone: the zone's own price moved up or down (a coin flip)
    by a random ``lo`` .. ``hi`` ATR, redrawn until it lies at least ``sep_real`` ATR from every
    real zone that is live at the moment the zone is founded and ``sep_placebo`` ATR from every
    placebo zone founded earlier that has not aged out.

    ``live`` = (zone, from, to): the spans during which the real zones were live, as
    ``scan_events`` reports them (``Events.lives``). Without it every real zone that has not aged
    out counts as live. Only what is known at the founding time is looked at, so a placebo price
    carries no knowledge of later levels. A zone for which no free price is found in ``tries``
    draws keeps the last draw.
    """
    rng = np.random.default_rng(seed)
    n = len(z)
    out = np.empty(n)
    if live is None:
        live = (np.arange(n), z.t, z.expire)
    live_price, live_from, live_to = z.price[live[0]], live[1], live[2]
    alive: List[int] = []
    for q in range(n):
        t, a = int(z.t[q]), float(z.atr[q])
        alive = [u for u in alive if z.expire[u] > t]
        real = live_price[(live_from <= t) & (live_to > t) & (live[0] != q)]
        fake = out[alive]
        p = z.price[q]
        for _ in range(tries):
            p = z.price[q] + (1.0 if rng.random() < 0.5 else -1.0) * rng.uniform(lo, hi) * a
            if (len(real) == 0 or np.abs(real - p).min() >= sep_real * a) and \
                    (len(fake) == 0 or np.abs(fake - p).min() >= sep_placebo * a):
                break
        out[q] = p
        alive.append(q)
    return out


# ───────────────────────────── events ─────────────────────────────

@njit(cache=True)
def _grow(E):
    """The event table with twice the room."""
    out = np.empty((E.shape[0] * 2, E.shape[1]))
    out[: E.shape[0]] = E
    return out


@njit(cache=True)
def _scan(T, h, l, c, atr, h1_new, h1_c, m15_new, m15_o, m15_h, m15_l, m15_c,
          z_price, j_t, j_zone, j_src, j_exp, zone_w, arm_w):
    """
    Walk the M1 bars once and report what happens at the zones.

    Per M1 bar, for every live zone, in this order: a TOUCH when the bar reaches the armed zone from
    its current side; a REVERSAL when an M15 bar that has just closed reached the zone and closed
    back beyond the level and beyond its own open, in the bounce direction; a BREAK when an H1 bar
    that has just closed lies beyond the far edge of the zone (the zone changes side; the second
    break retires it); arming when the M1 close is ``arm_w`` ATR away on the current side; expiry.
    Levels that became known by the close of this bar join afterwards, so a bar never trades a
    level it could not have known.

    Returns the events (one row each: bar, zone, type, direction, breaks so far, touches so far,
    touches since the last break, bit mask of the zone's sources, the extreme price reached towards
    the level since it was last armed), the spans during which each zone was live (zone, from, to)
    and three density counters.
    """
    n = T.shape[0]
    nz = z_price.shape[0]
    nj = j_t.shape[0]
    alive = np.zeros(nz, np.bool_)
    side = np.zeros(nz, np.int64)
    nbreak = np.zeros(nz, np.int64)
    ntouch = np.zeros(nz, np.int64)
    ntouch_side = np.zeros(nz, np.int64)
    armed = np.zeros(nz, np.bool_)
    armed_rev = np.zeros(nz, np.bool_)
    expire = np.zeros(nz, np.int64)
    mask = np.zeros(nz, np.int64)
    ext = np.zeros(nz, np.float64)
    active = np.empty(max(nz, 1), np.int64)
    na = 0
    E = np.empty((4096, 9))
    ne = 0
    lives = np.empty((nj + 1, 3), np.int64)      # a zone starts a new life at most once per level that joins it
    nl = 0
    life = np.zeros(nz, np.int64)
    jp = 0
    bars_seen = 0
    live_sum = 0
    near_sum = 0
    in_zone = 0
    for i in range(n):
        A = atr[i]
        if A > 0.0:
            z = zone_w * A
            arm = arm_w * A
            bars_seen += 1
            live_sum += na
            inside = False
            k = 0
            while k < na:
                q = active[k]
                L = z_price[q]
                s = side[q]
                dead = False
                dist = c[i] - L
                if dist < 0.0:
                    dist = -dist
                if dist <= 3.0 * A:
                    near_sum += 1
                if dist <= z:
                    inside = True
                if s > 0:
                    if l[i] < ext[q]:
                        ext[q] = l[i]
                    touched = l[i] <= L + z
                else:
                    if h[i] > ext[q]:
                        ext[q] = h[i]
                    touched = h[i] >= L - z
                if armed[q] and touched:
                    if ne == E.shape[0]:
                        E = _grow(E)
                    E[ne, 0] = i; E[ne, 1] = q; E[ne, 2] = 0; E[ne, 3] = s; E[ne, 4] = nbreak[q]
                    E[ne, 5] = ntouch[q]; E[ne, 6] = ntouch_side[q]; E[ne, 7] = mask[q]; E[ne, 8] = ext[q]
                    ne += 1
                    armed[q] = False
                    ntouch[q] += 1
                    ntouch_side[q] += 1
                if m15_new[i] and armed_rev[q]:
                    if s > 0:
                        rev = m15_l[i] <= L + z and m15_c[i] > L and m15_c[i] > m15_o[i]
                    else:
                        rev = m15_h[i] >= L - z and m15_c[i] < L and m15_c[i] < m15_o[i]
                    if rev:
                        if ne == E.shape[0]:
                            E = _grow(E)
                        E[ne, 0] = i; E[ne, 1] = q; E[ne, 2] = 1; E[ne, 3] = s; E[ne, 4] = nbreak[q]
                        E[ne, 5] = ntouch[q]; E[ne, 6] = ntouch_side[q]; E[ne, 7] = mask[q]; E[ne, 8] = ext[q]
                        ne += 1
                        armed_rev[q] = False
                if h1_new[i] and s * (h1_c[i] - L) < -z:
                    if ne == E.shape[0]:
                        E = _grow(E)
                    E[ne, 0] = i; E[ne, 1] = q; E[ne, 2] = 2; E[ne, 3] = -s; E[ne, 4] = nbreak[q]
                    E[ne, 5] = ntouch[q]; E[ne, 6] = ntouch_side[q]; E[ne, 7] = mask[q]; E[ne, 8] = ext[q]
                    ne += 1
                    nbreak[q] += 1
                    if nbreak[q] >= 2:
                        dead = True
                    else:
                        s = -s
                        side[q] = s
                        armed[q] = False
                        armed_rev[q] = False
                        ntouch_side[q] = 0
                        ext[q] = c[i]
                if not dead and s * (c[i] - L) >= arm:
                    armed[q] = True
                    armed_rev[q] = True
                    ext[q] = c[i]
                if T[i] >= expire[q]:
                    dead = True
                if dead:
                    alive[q] = False
                    lives[life[q], 2] = T[i]
                    na -= 1
                    active[k] = active[na]
                else:
                    k += 1
            if inside:
                in_zone += 1
        while jp < nj and j_t[jp] <= T[i]:
            q = j_zone[jp]
            if alive[q]:
                if j_exp[jp] > expire[q]:
                    expire[q] = j_exp[jp]
                mask[q] |= 1 << j_src[jp]
            elif j_exp[jp] > T[i]:
                alive[q] = True
                active[na] = q
                na += 1
                life[q] = nl
                lives[nl, 0] = q
                lives[nl, 1] = T[i]
                lives[nl, 2] = np.iinfo(np.int64).max
                nl += 1
                L = z_price[q]
                side[q] = 1 if c[i] >= L else -1
                nbreak[q] = 0
                ntouch[q] = 0
                ntouch_side[q] = 0
                mask[q] = 1 << j_src[jp]
                expire[q] = j_exp[jp]
                far = A > 0.0 and abs(c[i] - L) >= arm_w * A
                armed[q] = far
                armed_rev[q] = far
                ext[q] = c[i]
            jp += 1
    return E[:ne], lives[:nl], bars_seen, live_sum, near_sum, in_zone


@dataclass
class Events:
    """What happened at the zones, one entry per event, in bar order (see ``_scan``)."""
    bar: np.ndarray
    zone: np.ndarray
    type: np.ndarray
    dir: np.ndarray
    breaks: np.ndarray
    touches: np.ndarray
    touches_side: np.ndarray
    n_src: np.ndarray
    mask: np.ndarray           # bit mask of the sources in the zone at the event
    ext: np.ndarray
    price: np.ndarray          # the level's price
    density: Dict[str, float]
    lives: Tuple[np.ndarray, np.ndarray, np.ndarray]     # zone, from, to: when each zone was live

    def __len__(self) -> int:
        return len(self.bar)


def scan_events(fr: Frames, z: Zones, prices: Optional[np.ndarray] = None, p: Params = Params()) -> Events:
    """The level events of a period, at the zones' own prices or at ``prices`` (placebo)."""
    zp = z.price if prices is None else np.asarray(prices, np.float64)
    E, lives, seen, live, near, inside = _scan(fr.T, fr.h, fr.l, fr.c, fr.atr, fr.h1_new, fr.h1_c, fr.m15_new,
                                        fr.m15_o, fr.m15_h, fr.m15_l, fr.m15_c, zp,
                                        z.j_t, z.j_zone, z.j_src, z.j_exp, p.zone_w, p.arm_w)
    col = lambda k: E[:, k].astype(np.int64)
    m = col(7)
    n_src = sum(((m >> b) & 1) for b in range(5)) if len(m) else m
    seen = max(seen, 1)
    return Events(col(0), col(1), col(2), col(3), col(4), col(5), col(6), np.asarray(n_src, np.int64), m, E[:, 8].copy(),
                  zp[col(1)] if len(E) else np.zeros(0),
                  {"live_zones": live / seen, "zones_within_3_atr": near / seen, "share_of_time_in_a_zone": inside / seen},
                  (lives[:, 0].copy(), lives[:, 1].copy(), lives[:, 2].copy()))


# ───────────────────────────── simulator ─────────────────────────────

def market_fill(bid, spread, direction):
    """Price of a market order sent at a bid quote: a buy is filled at the ask (bid + spread), a sell at the bid."""
    return np.where(direction > 0, bid + spread, bid)


@njit(cache=True)
def simulate(t, o, h, l, c, spread, e_bar, e_dir, e_price, e_inbar, e_stop, e_target, max_hold_s):
    """
    Bar-level trade simulator, one position at a time.

    Candidates (``e_bar`` ascending, direction +1 buy / -1 sell, entry, stop and target prices) are
    taken in order; one that arrives while a position is open is skipped. Bars hold BID prices and
    the ask is the bid plus the bar's mean spread.

    * Entry: at ``e_price`` on bar ``e_bar`` (see ``market_fill``). With ``e_inbar`` 0 the order was
      sent at the close of that bar, so the bar itself can no longer stop it. With ``e_inbar`` 1 it
      was filled inside the bar: if the same bar also reaches the stop the trade is stopped there,
      and its target is not credited in that bar.
    * From the next bar on, per bar and in this order -
        buy : open <= stop -> out at the open (a gap);  low <= stop -> out at the stop;
              high >= target -> out at the target;
        sell: the same on the ask side;
      so a bar that reaches both the stop and the target counts as stopped. A target is never
      filled better than its price.
    * Time stop: at the close of the first bar ending ``max_hold_s`` or more after the close of the
      entry bar (0 = no time stop); a buy is sold at the bid, a sell bought back at the ask.
    * A position still open at the end of the data is closed at the last close.

    Returns per trade: candidate index, entry bar, exit bar, entry price, exit price, exit reason
    (1 stop, 2 target, 3 time, 4 end of data).
    """
    n = t.shape[0]
    m = e_bar.shape[0]
    cand = np.empty(m, np.int64)
    b_in = np.empty(m, np.int64)
    b_out = np.empty(m, np.int64)
    p_in = np.empty(m, np.float64)
    p_out = np.empty(m, np.float64)
    why = np.empty(m, np.int64)
    nt = 0
    free_from = 0
    for k in range(m):
        i = e_bar[k]
        if i < free_from or i >= n - 1:
            continue
        d = e_dir[k]
        stop = e_stop[k]
        target = e_target[k]
        t_in = t[i] + 60
        j = i
        px = 0.0
        reason = 0
        if e_inbar[k] != 0:
            if d > 0:
                if l[i] <= stop:
                    px = stop; reason = 1
            elif h[i] + spread[i] >= stop:
                px = stop; reason = 1
        if reason == 0:
            j = i + 1
            while j < n:
                if d > 0:
                    if o[j] <= stop:
                        px = o[j]; reason = 1
                    elif l[j] <= stop:
                        px = stop; reason = 1
                    elif h[j] >= target:
                        px = target; reason = 2
                else:
                    sp = spread[j]
                    if o[j] + sp >= stop:
                        px = o[j] + sp; reason = 1
                    elif h[j] + sp >= stop:
                        px = stop; reason = 1
                    elif l[j] + sp <= target:
                        px = target; reason = 2
                if reason == 0 and max_hold_s > 0 and t[j] + 60 - t_in >= max_hold_s:
                    px = c[j] if d > 0 else c[j] + spread[j]
                    reason = 3
                if reason != 0:
                    break
                j += 1
            if reason == 0:
                j = n - 1
                px = c[j] if d > 0 else c[j] + spread[j]
                reason = 4
        cand[nt] = k; b_in[nt] = i; b_out[nt] = j; p_in[nt] = e_price[k]; p_out[nt] = px; why[nt] = reason
        nt += 1
        free_from = j
    return cand[:nt], b_in[:nt], b_out[:nt], p_in[:nt], p_out[:nt], why[:nt]


# ───────────────────────────── rules ─────────────────────────────

@dataclass
class Trades:
    """Closed trades of one rule. ``pnl`` is in price units per unit traded; ``r`` in multiples of the risk."""
    t_in: np.ndarray
    t_out: np.ndarray
    dir: np.ndarray
    pnl: np.ndarray
    risk: np.ndarray
    why: np.ndarray
    n_candidates: int = 0
    zone: Optional[np.ndarray] = None      # the zone each trade was taken at
    cost: Optional[np.ndarray] = None      # the spread paid on the round trip, in price units

    def __len__(self) -> int:
        return len(self.t_in)

    @property
    def r(self) -> np.ndarray:
        return self.pnl / self.risk


def level_class(mask: np.ndarray) -> np.ndarray:
    """Highest timeframe among a zone's sources: 3 = D1 swing or weekly level, 2 = H4 swing, 1 = H1 swing / previous day."""
    major = (mask & ((1 << SRC_D1) | (1 << SRC_PW))) != 0
    return np.where(major, 3, np.where((mask & (1 << SRC_H4)) != 0, 2, 1))


def candidates(fr: Frames, ev: Events, rule: Rule, p: Params = Params()):
    """
    The entries a rule wants, before the one-position limit:
    (bar, direction, stop, target, risk, zone, entry price, filled inside the bar).

    Common to every rule: the stop lies ``zone_w + stop_w`` ATR beyond the level on the losing
    side; the target is ``target_r`` times the distance from entry to stop; no entry on a bar whose
    spread exceeds ``spread_cap_w`` ATR, whose stop distance is outside ``min_risk_w`` ..
    ``max_risk_w`` ATR, or outside the evaluated span.

    ``entry="close"``: a market order at the close of the event's M1 bar. A bounce or retest also
    needs that bar to close no further than the far edge of the zone (the level has not already
    given way), a breakout needs the close beyond the zone.

    ``entry="touch"``: bounces and retests are entered the moment the bid reaches the near edge of
    the zone (at the open, if the bar opens beyond it), whatever the bar does next. The order is
    sent inside the bar, so the ATR, the trend and every confirmation are those of the previous M1
    close. Reversal-bar and breakout entries stay at the close of their bar.
    """
    i, d, L = ev.bar, ev.dir, ev.price
    on_touch = p.entry == "touch" and rule.event == EV_TOUCH
    k = np.maximum(i - 1, 0) if on_touch else i           # the bar whose close is the latest thing known
    A = fr.atr[k]
    c = fr.c[i]
    z = p.zone_w * A
    stop = L - d * (p.zone_w + p.stop_w) * A
    if on_touch:
        edge = L + d * z
        quote = np.where(d > 0, np.minimum(edge, fr.o[i]), np.maximum(edge, fr.o[i]))
        entry = market_fill(quote, fr.spread[i], d)
    else:
        entry = market_fill(c, fr.spread[i], d)
    risk = d * (entry - stop)
    ok = (ev.type == rule.event) & (ev.breaks == rule.breaks)
    ok &= (fr.T[i] >= fr.eval_start) & (fr.T[i] < fr.eval_end)
    ok &= (fr.spread[i] <= p.spread_cap_w * A) & (risk >= p.min_risk_w * A) & (risk <= p.max_risk_w * A)
    if rule.event == EV_BREAK:
        ok &= d * (c - L) > z
    elif on_touch:
        ok &= np.where(d > 0, fr.l[i] <= edge, fr.h[i] >= edge)      # the edge as it was known before the bar was reached
    else:
        ok &= d * (c - L) >= -z
    if rule.event == EV_REV:
        ok &= d * (ev.ext - stop) > 0            # the visit never reached the stop
    if rule.first_return:
        ok &= ev.touches_side == 0
    if rule.trend:
        tr = fr.trend_h4[k] if p.trend == "H4" else fr.trend_d1[k]
        ok &= d * tr * rule.trend > 0
    if rule.flat:
        ok &= fr.adx_h4[k] < p.adx_flat
    if rule.rsi:
        r = fr.rsi15[k]
        ok &= ((d > 0) & (r < p.rsi_low)) | ((d < 0) & (r > p.rsi_high))
    if rule.div:
        ok &= ((d > 0) & fr.bull_div[k]) | ((d < 0) & fr.bear_div[k])
    if rule.min_src > 1:
        ok &= ev.n_src >= rule.min_src
    if rule.touches == 0:
        ok &= ev.touches == 0
    elif rule.touches == 1:
        ok &= ev.touches >= 1
    if rule.tf_class:
        ok &= level_class(ev.mask) == rule.tf_class
    s = np.flatnonzero(ok)
    return (i[s], d[s], stop[s], (entry + d * p.target_r * risk)[s], risk[s], ev.zone[s], entry[s],
            np.full(len(s), 1 if on_touch else 0, np.int64))


def run_rule(fr: Frames, ev: Events, rule: Rule, p: Params = Params()) -> Trades:
    """Simulate one rule on one set of events."""
    bar, d, stop, target, risk, zone, entry, inbar = candidates(fr, ev, rule, p)
    k, b_in, b_out, p_in, p_out, why = simulate(fr.t, fr.o, fr.h, fr.l, fr.c, fr.spread, bar, d, entry, inbar,
                                                stop, target, p.max_hold_h * 3600.0)
    dd = d[k]
    cost = np.where(dd > 0, fr.spread[b_in], fr.spread[b_out])        # a buy pays it on the way in, a sell on the way out
    return Trades(fr.T[b_in], fr.T[b_out], dd, dd * (p_out - p_in), risk[k], why, n_candidates=len(bar),
                  zone=zone[k], cost=cost)


# ───────────────────────────── statistics ─────────────────────────────

def half_year(t: np.ndarray) -> np.ndarray:
    """'2026H1' style labels for epoch seconds."""
    d = t.astype("datetime64[s]").astype("datetime64[M]")
    year = d.astype("datetime64[Y]").astype(int) + 1970
    month = d.astype(int) % 12 + 1
    return np.array([f"{y}H{1 if m <= 6 else 2}" for y, m in zip(year, month)], dtype=object)


def _week(t: np.ndarray) -> np.ndarray:
    """Number of the week (from Sunday 00:00 UTC) each time falls in."""
    return (t - WEEK_SHIFT) // WEEK


def _worst_run(pnl: np.ndarray) -> Tuple[int, float]:
    """Longest run of consecutive losing trades and the sum it lost."""
    best_n, best_sum, n, s = 0, 0.0, 0, 0.0
    for x in pnl:
        if x < 0:
            n, s = n + 1, s + x
            if n > best_n or (n == best_n and s < best_sum):
                best_n, best_sum = n, s
        else:
            n, s = 0, 0.0
    return best_n, best_sum


def _week_bootstrap(values: np.ndarray, week: np.ndarray, n_boot: int = 2000, seed: int = 7) -> Tuple[float, float, float]:
    """
    Standard error and 95 % interval of the mean per trade, resampling whole weeks so that trades
    of the same week (which share one market path) stay together.
    """
    if len(values) < 2:
        return float("nan"), float("nan"), float("nan")
    wk, inv = np.unique(week, return_inverse=True)
    s = np.bincount(inv, weights=values, minlength=len(wk))
    c = np.bincount(inv, minlength=len(wk)).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(wk), size=(n_boot, len(wk)))
    tot = c[pick].sum(axis=1)
    means = s[pick].sum(axis=1) / np.where(tot > 0, tot, np.nan)
    means = means[np.isfinite(means)]
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(means.std(ddof=1)), float(lo), float(hi)


def summarize(tr: Trades, unit: float, days: float) -> Dict[str, object]:
    """The figures of one rule over one span: USD per 0.01 lot and multiples of risk."""
    n = len(tr)
    out: Dict[str, object] = {"n": n, "candidates": tr.n_candidates}
    if n == 0:
        return out
    usd, r = tr.pnl * unit, tr.r
    win = usd > 0
    se_r, lo_r, hi_r = _week_bootstrap(r, _week(tr.t_in))
    se_usd, lo_usd, hi_usd = _week_bootstrap(usd, _week(tr.t_in))
    run_n, run_usd = _worst_run(usd)
    out.update(
        win_rate=float(win.mean()),
        avg_win=float(usd[win].mean()) if win.any() else 0.0,
        avg_loss=float(usd[~win].mean()) if (~win).any() else 0.0,
        exp_usd=float(usd.mean()), se_usd=se_usd, lo_usd=lo_usd, hi_usd=hi_usd,
        exp_r=float(r.mean()), se_r=se_r, lo_r=lo_r, hi_r=hi_r,
        total_usd=float(usd.sum()), per_quarter_usd=float(usd.sum() / (days / 91.3125)),
        worst_run=run_n, worst_run_usd=run_usd,
        avg_risk_usd=float((tr.risk * unit).mean()),
        cost_r=float((tr.cost / tr.risk).mean()) if tr.cost is not None else float("nan"),
        stop=float((tr.why == EXIT_STOP).mean()), target=float((tr.why == EXIT_TARGET).mean()),
        timed=float((tr.why >= EXIT_TIME).mean()),
        long_n=int((tr.dir > 0).sum()), long_r=float(r[tr.dir > 0].mean()) if (tr.dir > 0).any() else float("nan"),
        short_n=int((tr.dir < 0).sum()), short_r=float(r[tr.dir < 0].mean()) if (tr.dir < 0).any() else float("nan"),
    )
    halves = half_year(tr.t_in)
    out["halves"] = {}
    for hy in sorted(set(halves)):
        m = halves == hy
        se = float(r[m].std(ddof=1) / math.sqrt(m.sum())) if m.sum() > 1 else float("nan")
        out["halves"][hy] = {"n": int(m.sum()), "exp_r": float(r[m].mean()), "se_r": se, "total_usd": float(usd[m].sum())}
    return out


def compare_with_placebo(real: Trades, fakes: Sequence[Trades], unit: float, n_boot: int = 2000, seed: int = 11,
                         outward: Optional[Sequence[np.ndarray]] = None) -> Dict[str, object]:
    """
    Real levels against placebo levels, in multiples of risk per trade (and USD per 0.01 lot).

    ``diff_r``: mean of the real trades minus the mean of all placebo trades. Its interval comes from
    resampling whole weeks, the same weeks for both, so the market path the two share cancels.
    ``beaten_by``: how many placebo sets did at least as well as the real levels; with no effect the
    real set would rank anywhere among them.
    ``outward`` (one flag per zone and set: the placebo price lies beyond the swing, away from the
    range it came from) splits the placebo trades into prices beyond the extreme and prices inside
    the range.
    """
    out: Dict[str, object] = {"sets": len(fakes)}
    set_means = [float(f.r.mean()) for f in fakes if len(f)]
    if len(real) == 0 or not set_means:
        return out
    fr_r = np.concatenate([f.r for f in fakes])
    fr_usd = np.concatenate([f.pnl * unit for f in fakes])
    fr_w = np.concatenate([_week(f.t_in) for f in fakes])
    rr, ru, rw = real.r, real.pnl * unit, _week(real.t_in)
    wk = np.unique(np.concatenate([rw, fr_w]))
    pos = lambda w: np.searchsorted(wk, w)
    agg = lambda v, w: np.bincount(pos(w), weights=v, minlength=len(wk))
    cnt = lambda w: np.bincount(pos(w), minlength=len(wk)).astype(float)
    rs, rc, fs, fc = agg(rr, rw), cnt(rw), agg(fr_r, fr_w), cnt(fr_w)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(wk), size=(n_boot, len(wk)))
    with np.errstate(divide="ignore", invalid="ignore"):
        diff = rs[pick].sum(axis=1) / rc[pick].sum(axis=1) - fs[pick].sum(axis=1) / fc[pick].sum(axis=1)
    diff = diff[np.isfinite(diff)]
    lo, hi = np.quantile(diff, [0.025, 0.975])
    real_mean = float(rr.mean())
    out.update(
        placebo_n=int(round(len(fr_r) / len(fakes))), placebo_r=float(fr_r.mean()), placebo_usd=float(fr_usd.mean()),
        placebo_set_sd=float(np.std(set_means, ddof=1)) if len(set_means) > 1 else float("nan"),
        placebo_set_min=float(min(set_means)), placebo_set_max=float(max(set_means)),
        diff_r=real_mean - float(fr_r.mean()), diff_se=float(diff.std(ddof=1)), diff_lo=float(lo), diff_hi=float(hi),
        diff_usd=float(ru.mean()) - float(fr_usd.mean()),
        beaten_by=int(sum(m >= real_mean for m in set_means)),
        real_win=float((rr > 0).mean()), placebo_win=float((fr_r > 0).mean()),
    )
    if outward is not None:
        flag = np.concatenate([o[f.zone] for o, f in zip(outward, fakes)])
        for name, m in (("beyond", flag), ("inside", ~flag)):
            out[f"placebo_{name}_n"] = int(round(m.sum() / len(fakes)))
            out[f"placebo_{name}_r"] = float(fr_r[m].mean()) if m.any() else float("nan")
    real_half = half_year(real.t_in)
    fake_half = np.concatenate([half_year(f.t_in) for f in fakes])
    out["halves"] = {}
    for hy in sorted(set(real_half) | set(fake_half)):
        a, b = real_half == hy, fake_half == hy
        if a.any() and b.any():
            out["halves"][hy] = {"real_r": float(rr[a].mean()), "placebo_r": float(fr_r[b].mean()),
                                 "diff_r": float(rr[a].mean() - fr_r[b].mean()), "n": int(a.sum())}
    return out


# ───────────────────────────── experiment ─────────────────────────────

def run_symbol(symbol: str, period: str, lp: LevelParams = LevelParams(), p: Params = Params(),
               n_placebo: int = 30, rules: Sequence[Rule] = RULES, placebo_kw: Optional[Dict[str, float]] = None,
               log=print) -> Dict[str, object]:
    """Every rule on the real levels and on ``n_placebo`` placebo sets (seeds 1 .. n), for one symbol and period."""
    t0 = time.time()
    fr = load_frames(symbol, period, lp)
    unit = UNIT_USD[symbol]
    days = (fr.eval_end - fr.eval_start) / DAY
    raw = raw_levels(fr, lp)
    zones = build_zones(raw, lp)
    ev = scan_events(fr, zones, None, p)
    fake_px = [placebo_prices(zones, seed, ev.lives, **(placebo_kw or {})) for seed in range(1, n_placebo + 1)]
    fake_ev = [scan_events(fr, zones, px, p) for px in fake_px]
    outward = [(px - zones.price) * zones.kind > 0 for px in fake_px]       # above a high, below a low
    res: Dict[str, object] = {
        "symbol": symbol, "period": period, "level_params": asdict(lp), "params": asdict(p),
        "span": [int(fr.eval_start), int(fr.eval_end)], "days": days, "m1_bars": len(fr),
        "levels": {SRC_NAMES[s]: int((raw["src"] == s).sum()) for s in range(5)}, "zones": len(zones),
        "density": ev.density,
        "placebo_density": {k: float(np.mean([f.density[k] for f in fake_ev])) for k in ev.density},
        "events": {"touch": int((ev.type == EV_TOUCH).sum()), "reversal": int((ev.type == EV_REV).sum()),
                   "break": int((ev.type == EV_BREAK).sum())},
        "atr_usd_mean": float(np.nanmean(fr.atr[fr.T >= fr.eval_start]) * unit),
        "spread_usd_median": float(np.median(fr.spread[fr.T >= fr.eval_start]) * unit),
        "rules": {},
    }
    for rule in rules:
        real = run_rule(fr, ev, rule, p)
        fakes = [run_rule(fr, f, rule, p) for f in fake_ev]
        s = summarize(real, unit, days)
        s["placebo"] = compare_with_placebo(real, fakes, unit, outward=outward)
        res["rules"][rule.key] = s
    log(f"{period} {symbol}: {len(fr):,} M1 bars, {len(zones)} zones, {len(ev)} events, "
        f"{len(rules)} rules x (1 + {n_placebo}) level sets in {time.time() - t0:.0f}s")
    return res


def default_out() -> Path:
    """Where runs are stored: ``SR_TRADES_OUT``, or ``data/sr_trades`` in the repository."""
    env = os.environ.get("SR_TRADES_OUT")
    return Path(env) if env else store.REPO_ROOT / "data" / "sr_trades"


def run(period: str, symbols: Sequence[str] = SYMBOLS, sets: Sequence[str] = ("base",), out: Optional[Path] = None,
        n_placebo: int = 30, log=print) -> None:
    """Run the named parameter sets on a period and store one JSON file per symbol and set."""
    out = Path(out) if out else default_out()
    out.mkdir(parents=True, exist_ok=True)
    for name in sets:
        lp, p = PARAM_SETS.get(name) or PARAM_SETS["base"]
        for sym in symbols:
            res = run_symbol(sym, period, lp, p, n_placebo=n_placebo, placebo_kw=PLACEBO_SETS.get(name), log=log)
            res["set"] = name
            (out / f"{period}_{sym}_{name.replace(' ', '_')}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def months_present(symbol: str, period: str) -> Tuple[int, int]:
    """(months of the period found in the store, months the period has)."""
    a, z = PERIODS[period]
    lo, hi = np.datetime64(a, "M"), np.datetime64(np.datetime64(z, "D") - 1, "M")
    want = [(int(str(m)[:4]), int(str(m)[5:7])) for m in np.arange(lo, hi + 1)]
    have = set(store.available_months(symbol))
    return sum(m in have for m in want), len(want)


# ───────────────────────────── tables ─────────────────────────────

MAIN_RULES = ("a", "b1", "b2", "c", "c+", "d", "d+", "e")
CONFIRMATION_RULES = ("a", "a.rsi", "a.div", "a.rev", "a.src2", "a.fresh", "a.tested",
                      "b2", "b2.rsi", "b2.div", "b2.rev", "b2.src2", "b2.fresh", "b2.tested")
TIMEFRAME_RULES = ("b2", "b2.h1", "b2.h4", "b2.d1", "d", "d.h1", "d.h4", "d.d1")


def _load(out: Path, period: str, sym: str, name: str = "base") -> Optional[dict]:
    """A stored run, or None when it has not been made."""
    f = out / f"{period}_{sym}_{name.replace(' ', '_')}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _f(x, nd=2, sign=True) -> str:
    """A number for a table: signed by default, with a real minus sign; "-" where there is none."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}").replace("-", "\u2212")


def _pm(x, se, nd=2) -> str:
    """'value ± standard error' for a table."""
    return f"{_f(x, nd)} ± {_f(se, nd, False)}" if x is not None else "-"


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A markdown table."""
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def _name(key: str) -> str:
    """'key: label' of a rule, as the tables show it."""
    return f"{key}: {RULE_BY_KEY[key].label}"


def table_rules(res: dict, keys: Sequence[str] = tuple(r.key for r in RULES)) -> str:
    """Per rule: trades, win rate, average win and loss, expectancy after spread, total per quarter, worst losing run."""
    rows = []
    for k in keys:
        s = res["rules"].get(k) or {}
        if not s.get("n"):
            rows.append([_name(k), 0] + ["-"] * 10)
            continue
        rows.append([_name(k), s["n"], _f(s["avg_risk_usd"], 2, False), f"{100 * s['win_rate']:.0f}%", _f(s["avg_win"]), _f(s["avg_loss"]),
                     _pm(s["exp_usd"], s["se_usd"]), _pm(s["exp_r"], s["se_r"]), _f(s["cost_r"], 2, False),
                     _f(s["per_quarter_usd"], 0), f"{s['worst_run']} ({_f(s['worst_run_usd'], 0)})",
                     f"{100 * s['stop']:.0f} / {100 * s['target']:.0f} / {100 * s['timed']:.0f}"])
    return _table(["Rule", "Trades", "Risk per trade $ (1R)", "Win", "Avg win $", "Avg loss $", "Expectancy $ ± SE", "Expectancy R ± SE",
                   "Spread paid, R", "$ per quarter", "Worst losing run: trades ($)", "Exit by stop / target / time, %"], rows)


def table_placebo(res: dict, keys: Sequence[str] = tuple(r.key for r in RULES)) -> str:
    """Per rule: the real levels against the placebo sets."""
    rows = []
    for k in keys:
        s = res["rules"].get(k) or {}
        pl = s.get("placebo") or {}
        if not s.get("n") or "diff_r" not in pl:
            rows.append([_name(k), s.get("n", 0)] + ["-"] * 9)
            continue
        rows.append([_name(k), s["n"], f"{100 * pl['real_win']:.0f}%", _f(s["exp_r"]), pl["placebo_n"],
                     f"{100 * pl['placebo_win']:.0f}%", _f(pl["placebo_r"]), _pm(pl["diff_r"], pl["diff_se"]),
                     f"{_f(pl['diff_lo'])} .. {_f(pl['diff_hi'])}", f"{pl['beaten_by']} of {pl['sets']}",
                     f"{_f(pl.get('placebo_inside_r'))} / {_f(pl.get('placebo_beyond_r'))}"])
    return _table(["Rule", "Real trades", "Real win", "Real R", "Placebo trades per set", "Placebo win", "Placebo R",
                   "Real − placebo, R ± SE", "95 % interval", "Placebo sets at least as good",
                   "Placebo R: price inside the range / beyond the swing"], rows)


def table_halves(results: Sequence[dict], keys: Sequence[str] = tuple(r.key for r in RULES)) -> str:
    """Per rule: expectancy in R and number of trades for every half-year of the given runs."""
    halves = sorted({hy for res in results for s in res["rules"].values() for hy in (s.get("halves") or {})})
    rows = []
    for k in keys:
        cells = []
        for hy in halves:
            x = next((res["rules"][k]["halves"][hy] for res in results
                      if hy in (res["rules"].get(k, {}).get("halves") or {})), None)
            cells.append(f"{_f(x['exp_r'])} ({x['n']})" if x else "-")
        rows.append([_name(k)] + cells)
    return _table(["Rule"] + list(halves), rows)


def table_halves_placebo(results: Sequence[dict], keys: Sequence[str]) -> str:
    """Per rule and half-year: expectancy at real levels minus expectancy at placebo levels, in R."""
    halves = sorted({hy for res in results for s in res["rules"].values() for hy in ((s.get("placebo") or {}).get("halves") or {})})
    rows = []
    for k in keys:
        cells = []
        for hy in halves:
            x = next((res["rules"][k]["placebo"]["halves"][hy] for res in results
                      if hy in ((res["rules"].get(k, {}).get("placebo") or {}).get("halves") or {})), None)
            cells.append(f"{_f(x['diff_r'])} ({x['n']})" if x else "-")
        rows.append([_name(k)] + cells)
    return _table(["Rule"] + list(halves), rows)


def table_side_by_side(results: Dict[str, dict], keys: Sequence[str]) -> str:
    """One symbol, the periods next to each other: trades, expectancy, total per quarter, real minus placebo."""
    periods = list(results)
    head = ["Rule"]
    for per in periods:
        head += [f"{per}: trades", "R ± SE", "$ per trade", "$ per quarter", "real − placebo, R ± SE", "placebo sets at least as good"]
    rows = []
    for k in keys:
        row = [_name(k)]
        for per in periods:
            s = results[per]["rules"].get(k) or {}
            pl = s.get("placebo") or {}
            if not s.get("n"):
                row += [0, "-", "-", "-", "-", "-"]
                continue
            row += [s["n"], _pm(s["exp_r"], s["se_r"]), _f(s["exp_usd"]), _f(s["per_quarter_usd"], 0),
                    _pm(pl.get("diff_r"), pl.get("diff_se")) if "diff_r" in pl else "-",
                    f"{pl['beaten_by']} of {pl['sets']}" if "beaten_by" in pl else "-"]
        rows.append(row)
    return _table(head, rows)


def table_long_short(results: Dict[str, dict], keys: Sequence[str]) -> str:
    """Buys and sells apart: trades and expectancy in R."""
    periods = list(results)
    head = ["Rule"] + [c for per in periods for c in (f"{per}: buys", "R", "sells", "R")]
    rows = []
    for k in keys:
        row = [_name(k)]
        for per in periods:
            s = results[per]["rules"].get(k) or {}
            row += [s.get("long_n", 0), _f(s.get("long_r")), s.get("short_n", 0), _f(s.get("short_r"))] if s.get("n") else [0, "-", 0, "-"]
        rows.append(row)
    return _table(head, rows)


def _pooled(parts: Sequence[Tuple[int, float, float]]) -> Tuple[int, float, float]:
    """Trade-weighted mean and its standard error over independent groups of (trades, mean, standard error)."""
    parts = [(n, m, se) for n, m, se in parts if n and m is not None and math.isfinite(m)]
    n = sum(p[0] for p in parts)
    if not n:
        return 0, float("nan"), float("nan")
    mean = sum(p[0] * p[1] for p in parts) / n
    se = math.sqrt(sum((p[0] * p[2]) ** 2 for p in parts if math.isfinite(p[2]))) / n
    return n, mean, se


def table_pooled(by_symbol: Dict[str, Dict[str, dict]], keys: Sequence[str]) -> str:
    """Both symbols together, in multiples of risk (the only unit the two share), period by period."""
    periods = list(next(iter(by_symbol.values())))
    head = ["Rule"]
    for per in periods:
        head += [f"{per}: trades", "R ± SE", "real − placebo, R ± SE"]
    rows = []
    for k in keys:
        row = [_name(k)]
        for per in periods:
            ss = [by_symbol[sym][per]["rules"].get(k) or {} for sym in by_symbol if per in by_symbol[sym]]
            n, m, se = _pooled([(s.get("n", 0), s.get("exp_r"), s.get("se_r", float("nan"))) for s in ss])
            _, dm, dse = _pooled([(s.get("n", 0), (s.get("placebo") or {}).get("diff_r"),
                                   (s.get("placebo") or {}).get("diff_se", float("nan"))) for s in ss])
            row += [n, _pm(m, se), _pm(dm, dse)]
        rows.append(row)
    return _table(head, rows)


def table_facts(by_symbol: Dict[str, Dict[str, dict]]) -> str:
    """What each run covered: span, bars, volatility and spread, levels, zones, how dense they are, events."""
    day = lambda x: str(np.datetime64(int(x), "s").astype("datetime64[D]"))
    rows = []
    for sym, results in by_symbol.items():
        for per, res in results.items():
            lv, d, pd_, ev = res["levels"], res["density"], res["placebo_density"], res["events"]
            rows.append([sym, per, f"{day(res['span'][0])} .. {day(res['span'][1] - 1)}", f"{res['m1_bars']:,}",
                         f"{res['atr_usd_mean']:.2f}", f"{res['spread_usd_median']:.2f}",
                         " / ".join(str(lv[n]) for n in SRC_NAMES), res["zones"], f"{d['live_zones']:.1f}",
                         f"{d['zones_within_3_atr']:.1f}",
                         f"{100 * d['share_of_time_in_a_zone']:.0f}% / {100 * pd_['share_of_time_in_a_zone']:.0f}%",
                         f"{ev['touch']} / {ev['reversal']} / {ev['break']}"])
    return _table(["Symbol", "Period", "Entries taken", "M1 bars read", "Mean H1 ATR, $ per 0.01 lot", "Median spread, $",
                   "Levels: H1 swing / H4 swing / D1 swing / previous day / previous week", "Zones", "Zones live on average",
                   "... of them within 3 ATR of price", "Time price spends inside a zone: real / placebo",
                   "Events: touch / reversal bar / break"], rows)


def table_bounce_frequency(out: Path, periods: Sequence[str], symbols: Sequence[str] = SYMBOLS,
                           sets: Sequence[str] = ("target 0.25R", "target 1R", "base"), key: str = "b2") -> str:
    """How often a bounce reaches its target before its stop, at real levels and at placebo levels, by target size."""
    rows = []
    for name in sets:
        target = PARAM_SETS[name][1].target_r
        for sym in symbols:
            for per in periods:
                res = _load(out, per, sym, name)
                s = ((res or {}).get("rules") or {}).get(key) or {}
                pl = s.get("placebo") or {}
                if not s.get("n") or "real_win" not in pl:
                    continue
                rows.append([f"{target:g} × the risk", sym, per, s["n"], f"{100 * pl['real_win']:.0f}%", f"{100 * pl['placebo_win']:.0f}%",
                             f"{100 / (1 + target):.0f}%", _f(s["exp_r"]), _f(pl["placebo_r"])])
    return _table(["Target", "Symbol", "Period", "Trades at real levels", "Won at real levels", "Won at placebo levels",
                   "Won by a coin-flip market", "R at real levels", "R at placebo levels"], rows)


def table_sets(out: Path, period: str, sym: str, keys: Sequence[str]) -> str:
    """The parameter sets side by side: trades, expectancy in R, real minus placebo and the placebo sets at least as good."""
    rows = []
    for name in ALL_SETS:
        res = _load(out, period, sym, name)
        if not res:
            continue
        cells = []
        for k in keys:
            s = res["rules"].get(k) or {}
            pl = s.get("placebo") or {}
            cells.append(f"{s['n']}: {_f(s['exp_r'])} / {_f(pl.get('diff_r'))} ({pl.get('beaten_by', '-')})" if s.get("n") else "-")
        rows.append([name] + cells)
    return _table(["Parameter set"] + list(keys), rows)


def tables(periods: Sequence[str], out: Optional[Path] = None, symbols: Sequence[str] = SYMBOLS) -> str:
    """Every table of the report, as markdown, from the stored runs."""
    out = Path(out) if out else default_out()
    by_symbol = {sym: {per: res for per in periods if (res := _load(out, per, sym))} for sym in symbols}
    by_symbol = {sym: r for sym, r in by_symbol.items() if r}
    parts: List[str] = ["### What was run", table_facts(by_symbol), ""]
    if len(by_symbol) > 1:
        parts += ["### Both symbols together, in multiples of risk", table_pooled(by_symbol, MAIN_RULES), ""]
    for sym, results in by_symbol.items():
        parts += [f"### {sym}: the rules, period by period", table_side_by_side(results, MAIN_RULES), ""]
        parts += [f"### {sym}: half-year by half-year, R per trade (trades)", table_halves(list(results.values()), MAIN_RULES), ""]
        parts += [f"### {sym}: real minus placebo, half-year by half-year, R per trade (real trades)",
                  table_halves_placebo(list(results.values()), MAIN_RULES), ""]
        parts += [f"### {sym}: buys and sells apart", table_long_short(results, MAIN_RULES), ""]
        for per, res in results.items():
            parts += [f"### {sym}, {per}: every rule in USD per 0.01 lot", table_rules(res), ""]
            parts += [f"### {sym}, {per}: real levels against placebo levels", table_placebo(res), ""]
        parts += [f"### {sym}: confirmations", table_side_by_side(results, CONFIRMATION_RULES), ""]
        parts += [f"### {sym}: by the timeframe of the level", table_side_by_side(results, TIMEFRAME_RULES), ""]
        parts += [f"### {sym}: confirmations and level timeframe, half-year by half-year, R per trade (trades)",
                  table_halves(list(results.values()), [k for k in CONFIRMATION_RULES + TIMEFRAME_RULES if k not in MAIN_RULES]), ""]
        if any(_load(out, "DEV", sym, n) for n in ALL_SETS if n != "base"):
            parts += [f"### {sym}, DEV: the parameter sets (trades: R / real − placebo (placebo sets at least as good))",
                      table_sets(out, "DEV", sym, MAIN_RULES), ""]
    parts += ["### How often a bounce works, by target size (rule b2)", table_bounce_frequency(out, periods, list(by_symbol)), ""]
    return "\n".join(parts)


def _utf8_console() -> None:
    """The tables hold characters a legacy console code page cannot encode; write UTF-8 and never raise."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Command line: ``run``, ``tables`` and ``levels`` (see the top of this file)."""
    _utf8_console()
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.sr_trades", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the rules on one period and store the figures")
    r.add_argument("period", choices=list(PERIODS))
    r.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    r.add_argument("--sets", default="base", help="comma-separated parameter sets, or 'all'")
    r.add_argument("--placebo", type=int, default=30, help="number of placebo level sets")
    r.add_argument("--out", default=None)
    t = sub.add_parser("tables", help="markdown tables from the stored runs")
    t.add_argument("periods", nargs="+", choices=list(PERIODS))
    t.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    t.add_argument("--out", default=None)
    lv = sub.add_parser("levels", help="count the levels and how dense they are")
    lv.add_argument("period", choices=list(PERIODS))
    lv.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    a = ap.parse_args(argv)
    if a.cmd == "run":
        for sym in a.symbols:
            have, want = months_present(sym, a.period)
            if have < want:
                raise SystemExit(f"{sym}: only {have} of the {want} months of {a.period} are in the store")
        sets = list(ALL_SETS) if a.sets == "all" else [s.strip() for s in a.sets.split(",")]
        unknown = [s for s in sets if s not in ALL_SETS]
        if unknown:
            raise SystemExit(f"unknown parameter set {unknown}; known: {', '.join(ALL_SETS)}")
        run(a.period, a.symbols, sets, a.out, a.placebo)
    elif a.cmd == "tables":
        print(tables(a.periods, a.out, a.symbols))
    else:
        for sym in a.symbols:
            for name, (lp, p) in PARAM_SETS.items():
                if name not in ("base", "major swings", "wide zone"):
                    continue
                fr = load_frames(sym, a.period, lp)
                raw = raw_levels(fr, lp)
                zones = build_zones(raw, lp)
                ev = scan_events(fr, zones, None, p)
                print(f"{sym} {name}: levels {dict((SRC_NAMES[s], int((raw['src'] == s).sum())) for s in range(5))}, "
                      f"zones {len(zones)}, " + ", ".join(f"{k} {v:.2f}" for k, v in ev.density.items()))


if __name__ == "__main__":
    main()
