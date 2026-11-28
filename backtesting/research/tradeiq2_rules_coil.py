"""
Coil breakout (COIL) as rules (study 2, PREREG 6.9): our own version of TradeIQ's private "Coil Breakout AI", the
rule rows of the coil module for the driver (``tradeiq2.py``), ``variants(symbol)`` and ``build(variant, ctx)``.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_coil as C
    mk = M.load("BTCUSDm", end="2024-07-01")
    ctx = M.Context(mk)
    vs = C.variants("BTCUSDm")             # 36 rows: 30 COIL-RIB + 3 COIL-MA + 3 COIL-0
    ex = C.build(vs[0], ctx)               # a tradeiq2_market.Exec (market entries, one position at a time)
    res = M.run_variant(ctx, vs[0], ex)    # Development, Validation and D+V at x1.0 and x1.5

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen; read with ``DEVIATIONS.md``): section 4 (execution
and the rules for absolute levels, lines 93-131), 5 (the ATR, the filters and how they apply, lines 133-162), 6.9 (the
coil, lines 434-465), 7 (families and eligibility, lines 502-573) and claim 20 of section 8. There is NO Pine source:
the script is private (PREREG lines 18-19 and 26), so the rule is the plan's own text, built from the video's
description ("the candles get smaller and the range gets tighter ... when the coil breaks with the trend ... a grade
from the breakout candle's size and volume ... entry, stop, 1, 2, 3R and a trend trail to get out", PREREG 436-439).
The squeeze, the coil, its box, its 12 armed bars, the breakout and the ADX are the reconciled port
``tradeiq2_ind_coil`` (port A, equal bit for bit to port B on the study's 1H / 4H / 1D bars of both symbols;
``porting/coil.md``). This module adds what the port leaves to the study (``porting/coil.md`` section 1, item 6): the
trend filters, the BIG and VOL grades, the stop and the exits. The ribbon trend is ``tradeiq2_filters.ribbon_trend``
(the reconciled ``tradeiq2_ind_ribbon``), F1 ``tradeiq2_filters``, the ATR(14) ``tradeiq2_market.atr14`` (``ctx.atr``),
the volume the harness's (``ctx.volume``: gold tick volume, BTC Binance BTCUSDT spot volume, PREREG 2), and the
execution ``tradeiq2_market`` (study 1's fills, stops, marks and scores). Nothing is tuned: every number is the plan's.

The grid (per symbol; XAUUSDm and BTCUSDm only, none on the claim markets: PREREG 8 claim 20 says the script cannot
be tested and the COIL rows test the idea on BTC and gold)
--------------------------------------------------------------------------------------------------------------------
======== ======================================================================================== ===== ==========
family   rows (script COIL)                                                                        n     eligible
======== ======================================================================================== ===== ==========
COIL     COIL-RIB x {X-TR, X-3R} x {none, BIG, VOL, ADX, ALL3} x {1H, 4H, 1D}                      30    yes
COIL     COIL-MA x X-TR x none x {1H, 4H, 1D}                                                      3     yes
COIL     COIL-0 x X-TR x none x {1H, 4H, 1D}                                                       3     yes
======== ======================================================================================== ===== ==========

PREREG 6.9 marks no row "not eligible" or "information only", so all 36 are eligible (``info`` is empty). Ids:
``symbol|tf|COIL|rule|exit|grade`` (e.g. ``BTCUSDm|4H|COIL|COIL-RIB|X-3R|ALL3``, ``XAUUSDm|1D|COIL|COIL-0|X-TR|none``):
the PREREG's own names, so the driver pairs rows by swapping one token (claim 20: a grade -> ``none``; X-3R -> X-TR;
COIL-MA / COIL-RIB -> COIL-0). ``params``: rule, filter (``ribbon`` / ``F1`` / ``F0``), exit, grade, stop.

What a row does (an EVENT rule, PREREG 5 and 6.9)
------------------------------------------------
* SIGNAL (PREREG 441-445; the port). ``squeeze_on``: SMA(20) +- 2 population stdev(close, 20) strictly inside
  SMA(20) +- 1.5 ``ta.atr(20)``. A coil is a run of at least 6 squeeze bars; its box the highest high and lowest low of
  ALL the run's bars. It is armed from the first bar after the run (where the squeeze fires) for 12 bars, until its
  breakout or until a newer run reaches 6 bars. The breakout is the first armed close strictly above the box (long,
  +1) or below it (short, -1), once per coil (the port's ``breakout``, ``bo_box_hi`` / ``bo_box_lo``; its readings are
  ``porting/coil.md`` section 8).
* ENTRY. At the breakout: decided at the breakout bar's close, filled at the open of the first M1 bar at or after that
  close, a buy at the ask, a sell at the bid (PREREG 96-98). At most one trade per coil: the port marks one breakout
  per coil and each breakout is one candidate, tagged with its coil's ordinal (``tag``: coils counted from the data
  start, so every trade names its coil). A breakout the trend filter or the grade refuses opens nothing, and its coil
  is spent (reading 7). One position at a time (PREREG 110): a breakout decided while a trade is open is skipped (the
  harness counts it as ``busy``); the open trade keeps its own exits (reading 8).
* TREND FILTER AT THE BREAKOUT (PREREG 447-450), checked at the breakout bar's close (``tradeiq2_filters.gate_entries``;
  PREREG 152-157: on an event rule the filter must agree at the decision close and never closes an open trade):
  - COIL-RIB: the Trend Target Ribbon's trend of the SAME timeframe on the breakout's side (+1 for a long, -1 for a
    short; 0 before the ribbon's first setup allows neither). It is not PREREG 5's FR, which reads the higher
    timeframe's ribbon (reading 10).
  - COIL-MA: F1, the MA200 of the same timeframe: a long only while the close is above SMA(close, 200), a short only
    while below (strict; neither during the MA's warm-up).
  - COIL-0: none.
* GRADES (PREREG 458-462; "the three the video says helped"), read at the breakout bar, inclusive ("at least"):
  - BIG: the breakout bar's range, high - low, >= 1.5 x ATR(14) of that bar (reading 4).
  - VOL: the breakout bar's volume >= 1.5 x ``ta.sma(volume, 20)``, the breakout bar included (reading 5): gold's tick
    volume, BTC's Binance volume (``ctx.volume``; 0 in an hour without a Binance kline, study 1's reading).
  - ADX: the port's ``ta.dmi(14, 14)`` ADX >= 20 (NaN, on bars 0-26, fails).
  - ALL3: all three. ``none``: no grade.
* STOP (PREREG 453). The distance from the breakout close to the opposite box edge (a long's: close - box low; a
  short's: box high - close), clamped to [0.75, 3] x ATR(14) of the breakout bar: ``min(max(raw, 0.75 ATR), 3 ATR)``
  (``stop_distance``). It is set from the actual FILL ("set from the fill") and never moves; 1R = that distance.
* EXITS (PREREG 454-456):
  - X-TR, the trend trail: exit at the close of the first bar b after the breakout bar whose close is below the
    highest close since the entry minus 3 x ATR(14) of bar b (a long; a short's close above the lowest close since the
    entry plus 3 x ATR(14)), or at the stop. "Since the entry" = the closes of the bars after the breakout bar, from
    the bar that holds the fill to b (reading 1). The level is recomputed every bar, not ratcheted (reading 2), and the
    comparison is strict ("falls below"). The exit is decided at b's close and filled at the next M1 open (a signal
    exit, no extra spread); the stop is checked on every M1 bar from the fill (PREREG 99-100), so a bar that reaches
    the stop is stopped inside it before its close can trigger the trail.
  - X-3R: X-TR plus a target at 3R = 3 x the stop distance from the fill, a limit touched inside an M1 bar (the bid
    high of a long, the ask low of a short; the stop wins an M1 bar that touches both, PREREG 101).
  After the stop, the target or the trail the rule is flat until the next breakout (PREREG 130-131: "an event rule
  waits for its next event"). A window starts flat and waits for the first breakout decided inside it; what is open at
  its end closes at its last M1 close (the harness, DEVIATIONS 3).

The rules for absolute levels (PREREG 117-122)
---------------------------------------------
No level of the coil is absolute. The stop is a DISTANCE measured at the breakout close and set from the fill, the
target a multiple of it, and the trail a close-based exit decision (``Entries.exit_bar``), not a stop level. So:
the harness gets ``stop_dist`` and ``target_r`` (never ``stop_level`` / ``target_level``), no entry can be "at or
beyond its stop or target" at its fill (``dropped_stop`` and ``dropped_target`` stay 0), also when the fill gaps
through the opposite box edge (reading 11), no stop is ever tightened, and the x1.5 run sets the stop and the target
from its own fill (its own spread): only the fill moves, the distance does not.

What is known when (no look-ahead)
----------------------------------
A decision at bar t reads bars 0 .. t of its own timeframe only. The breakout, its box and its coil's ordinal are the
port's (bars up to t; ``porting/coil.md`` "Timing"); the stop the close, the box and the ATR(14) of t; the grades t's
high, low, volume, ATR(14), volume SMA (bars t-19 .. t) and ADX; COIL-RIB the ribbon's trend at t's close (closes, highs
and lows up to t); COIL-MA the close and SMA(200) of t. The trail's decision at bar b reads the closes of bars e+1 .. b
(e the entry's breakout bar) and b's ATR(14). Each decision fills at the next M1 open. ``Entries.exit_bar`` holds,
per entry, the first bar at which the trail decides to exit (found by scanning forward), so the array as a whole
spans the future, but every decision it encodes is taken at a close with the data up to that close; removing the
bars after T changes no entry decided at or before T and no exit decided at or before T (tested on synthetic and
real bars).

Readings where the plan leaves a choice (proposed for DEVIATIONS.md)
------------------------------------------------------------------------
Counts are Development decisions (bars closing after 2019-01-01 and filled before 2023-01-01) on the study's bars,
"gold 1H / 4H / 1D; BTC 1H / 4H / 1D", over every port breakout (COIL-0 before the one-position rule): event geometry
and timing only, no profit or loss. The breakouts are 338 / 75 / 15; 521 / 129 / 23 (porting/coil.md section 6).

1. "The highest close since the entry" (X-TR): the entry is the fill at the first M1 open after the breakout close
   (PREREG 96-98), so the closes since the entry are those of the bars after the breakout bar; the breakout close (the
   decision) is not one of them. Counting it as the trail's first close would move the trail exit of 36 / 7 / 0;
   45 / 14 / 0 breakouts, each earlier.
2. The trail's ATR and its form: ``close < highest close - 3 x ta.atr(14)``, evaluated at each bar with that bar's
   ATR(14) (PREREG 5's ATR on the signal timeframe), the level not ratcheted. These are the plan's words for X-TR,
   while ORB's O1 trail (PREREG 312-313) says explicitly "max of the previous trail and ...". A ratchet would move
   111 / 20 / 5; 173 / 56 / 15 trail exits (each earlier); the breakout bar's ATR held fixed 211 / 35 / 8;
   295 / 77 / 19.
3. Strictness: the trail exits on a close strictly below (a short's: above) its level ("falls below"); the grades are
   inclusive ("at least"). No breakout of either symbol from the data start to 2024-06-30 sits exactly on a grade's
   threshold; the nearest are 2.5e-4 of the threshold for BIG (BTC 1H), 3.2e-4 for VOL (gold 1H) and 0.0014 ADX points
   (BTC 1H), so no order of the float operations can move a grade.
4. BIG: "the breakout bar's range" is high - low (not the true range), against the ATR(14) of the breakout bar itself
   (``ta.atr(14)`` on that bar, its own true range included).
5. VOL: ``volume >= 1.5 * ta.sma(volume, 20)`` on the breakout bar, the bar included in its own average (Pine's
   reading on the bar, as PREREG 6.5's HV "the bar included" and Session Hunter's ``vAvg``). BTC: Binance volume,
   whose hours without a kline count 0 (study 1's reading of its 1h klines; ``ctx.volume``). 6 / 6 / 2 BTC breakout
   bars in Development (1 / 0 / 0 in Validation) have 1-5 hours without a kline in their 20-bar window; none from 2019
   on the breakout bar itself (two in the 2018 warm-up). Read literally, a bar whose 20-bar window has no volume at
   all would pass (0 >= 0); no breakout bar has such a window.
6. ADX: the port's ADX at the breakout bar (TradingView's built-in DMI script; ``porting/coil.md`` reading 8); NaN
   fails (it exists from bar 27, long before the first coil).
7. A breakout the trend filter or the grade refuses opens nothing and spends its coil: the plan's breakout is the
   FIRST close beyond the box, once per coil (PREREG 445), and the filter and the grades are read "at the breakout"
   (PREREG 447, 458), so a later close beyond the same box is no new event.
8. A breakout decided while a trade is open is skipped (one position per variant, PREREG 110), whatever its side:
   the plan gives the coil no opposite-signal exit or reversal, so the open trade keeps its stop, target and trail.
9. A stop needs a finite ATR(14) > 0 at the breakout bar; a breakout without one would open nothing. None exists on
   the study's bars of either symbol from the data start to 2024-06-30 (every breakout has one, tested): the ATR(14)
   exists from bar 13, the first squeeze from bar 19.
10. COIL-RIB's "the ribbon's trend (same timeframe)" is ``tradeiq2_filters.ribbon_trend`` of the signal timeframe
    itself, +1 or -1 from the ribbon's first setup on (0 before it, allowing neither); not PREREG 5's FR (the higher
    timeframe's ribbon, except on 1D). It is read at the breakout bar's close, the decision close of PREREG 5 (lines
    152-157), so a ribbon setup on the breakout bar itself counts: the breakout bar flips the ribbon to the breakout's
    side on 23 / 7 / 0; 54 / 11 / 1 breakouts, which the trend of the bar before the breakout would refuse. The ribbon
    agrees with 319 / 67 / 15; 498 / 123 / 22 breakouts (94-100%), so COIL-RIB keeps nearly every breakout.
11. "Set from the fill": the stop is the distance measured at the breakout close, placed from the actual fill. An
    entry whose fill gaps through the opposite box edge is still taken, with the stop that distance from the fill; no
    absolute box-edge level exists to drop it (PREREG 117-122 never acts here). On the study's bars to 2024-06-30 no
    fill lies at or beyond a stop drawn from the breakout close (close -/+ the distance) or beyond the opposite box
    edge, so this reading moves nothing there (one gold 1H Development fill lies back inside the box).
12. The 3R target is 3 x the stop distance from the fill (the harness's ``target_r``), as the stop is set from the
    fill; a long's target is touched by the bid high, a short's by the ask low (PREREG 101's limit).

Event counts for the plan (Development, counts only; before the one-position rule)
---------------------------------------------------------------------------------
Breakouts each row's gates keep, "gold 1H / 4H / 1D; BTC 1H / 4H / 1D": COIL-0 338 / 75 / 15; 521 / 129 / 23. COIL-MA
236 / 58 / 11; 399 / 99 / 12. COIL-RIB x none 319 / 67 / 15; 498 / 123 / 22, x BIG 159 / 33 / 4; 294 / 63 / 14, x VOL
101 / 21 / 1; 351 / 74 / 12, x ADX 177 / 42 / 7; 314 / 79 / 15, x ALL3 49 / 11 / 0; 173 / 37 / 8 (the same for X-TR and
X-3R). PREREG 5's minimum (30 Development trades on 1H and 4H, 15 on 1D) is therefore out of reach before any trade is
skipped for gold 4H VOL and ALL3, gold 1D COIL-MA and every graded gold 1D row, and BTC 1D COIL-MA, BIG, VOL and ALL3;
gold 1D COIL-0 and COIL-RIB x none, and BTC 1D COIL-RIB x ADX, have exactly 15, so a single breakout skipped while a
trade is open takes them below it. The trail holds a position a median of 29 / 23 / 32; 33 / 26 / 36 bars from the
breakout bar to its exit decision (before the stop and the one-position rule).
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from . import tradeiq_ind as I
from . import tradeiq2_filters as F
from . import tradeiq2_ind_coil as CI
from . import tradeiq2_market as M

__all__ = ["MODULE", "COIL_PARAMS", "TFS", "RULES", "EXITS", "GRADES", "RULE_FILTER", "variants", "build", "describe",
           "warm", "plan_counts", "coil_of", "coil_ids", "stop_distance", "trail_exits", "grade_masks", "grade_mask",
           "trend_gate", "breakouts", "coil_entries", "coil_exec", "breakout_table"]

MODULE = "tradeiq2_rules_coil"              # the Context cache's module key
COIL_PARAMS: Dict[str, str] = {"series": "coil"}            # the port with the plan's settings (cache key)
TFS = ("1H", "4H", "1D")                    # PREREG 6.9
RULES = ("COIL-RIB", "COIL-MA", "COIL-0")   # PREREG 6.9 "Trend filter at the breakout"
EXITS = ("X-TR", "X-3R")
GRADES = ("none", "BIG", "VOL", "ADX", "ALL3")
RULE_FILTER = {"COIL-RIB": "ribbon", "COIL-MA": "F1", "COIL-0": "F0"}     # params["filter"] (the driver's column)
FAMILY = SCRIPT = "COIL"                    # PREREG 7: the family COIL; "COIL and STK ... count as one each"
STOP_FLOOR_ATR = 0.75                       # "a distance clamped to [0.75, 3] ATR(14)"
STOP_CAP_ATR = 3.0
TRAIL_ATR = 3.0                             # X-TR: "the highest close since the entry minus 3 ATR"
TARGET_R = 3.0                              # X-3R: "X-TR plus a 3R target"
BIG_ATR = 1.5                               # BIG: "range is at least 1.5 ATR"
VOL_MULT = 1.5                              # VOL: "volume is at least 1.5 x SMA(20) of volume"
VOL_LEN = 20
ADX_MIN = 20.0                              # ADX: "ta.dmi(14, 14) ADX is at least 20"
STOP_NAME = "opposite box edge, 0.75-3 ATR(14)"

RULE_WORDS = {
    "COIL-RIB": "the Trend Target Ribbon's trend of the same timeframe on the breakout's side at the breakout's close",
    "COIL-MA": "F1: a long only while the close is above the MA200 (SMA 200) of the same timeframe, a short only "
               "while below, at the breakout's close",
    "COIL-0": "no trend filter",
}
EXIT_WORDS = {
    "X-TR": "exit at the close when it falls below the highest close since the entry minus 3 x ATR(14) (a short's: "
            "rises above the lowest close plus 3 x ATR(14)), filled at the next M1 open, or at the stop",
    "X-3R": "all out at 3R (3 x the stop distance from the fill), else the trend trail (the close below the highest "
            "close since the entry minus 3 x ATR(14), a short's mirrored) or the stop",
}
GRADE_WORDS = {
    "none": "no grade",
    "BIG": "BIG: the breakout bar's range (high - low) is at least 1.5 x ATR(14)",
    "VOL": "VOL: the breakout bar's volume is at least 1.5 x its 20-bar average, the bar included (gold tick volume, "
           "BTC Binance volume)",
    "ADX": "ADX: ta.dmi(14, 14)'s ADX is at least 20",
    "ALL3": "ALL3: BIG, VOL and ADX together",
}


def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _check_tf(tf: str) -> None:
    if tf not in TFS:
        raise ValueError(f"{tf}: the coil rules run on {', '.join(TFS)} (PREREG 6.9)")


def _check(name: str, value: str, allowed: Sequence[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} {value!r}: one of {', '.join(allowed)} (PREREG 6.9)")


# ───────────────────────────── the pieces, on plain arrays ─────────────────────────────

def coil_ids(armed, box_hi, box_lo) -> np.ndarray:
    """
    Per bar, the ordinal of the coil armed at that bar (0 = the first coil of the series), -1 where none is armed.
    A coil starts at an armed bar whose bar before is not armed or holds another box (the port never arms two coils on
    adjacent bars: a newer run disarms the old coil when it reaches 6 bars, before its own coil can arm, so the box
    test is a safeguard). Causal: bar t reads ``armed`` and the box up to t.
    """
    a = np.asarray(armed, bool)
    hi, lo = np.asarray(box_hi, np.float64), np.asarray(box_lo, np.float64)
    if not (a.shape == hi.shape == lo.shape) or a.ndim != 1:
        raise ValueError("armed, box_hi and box_lo must be 1-D series of one length")
    prev = np.zeros_like(a)
    prev[1:] = a[:-1]
    with np.errstate(invalid="ignore"):
        other = np.zeros_like(a)
        other[1:] = (hi[1:] != hi[:-1]) | (lo[1:] != lo[:-1])
    start = a & (~prev | other)
    return np.where(a, np.cumsum(start) - 1, -1).astype(np.int64)


def stop_distance(close, box_hi, box_lo, side, atr, floor: float = STOP_FLOOR_ATR,
                  cap: float = STOP_CAP_ATR) -> np.ndarray:
    """
    PREREG 6.9's stop as a price distance (1R): the distance from the breakout close to the opposite box edge, ``raw =
    close - box_lo`` for a long (+1) and ``box_hi - close`` for a short (-1), clamped as ``min(max(raw, 0.75 ATR),
    3 ATR)`` with the ATR(14) of the breakout bar (the order of the ribbon's riskDist, PREREG 6.1). NaN where the ATR
    or the box is missing. The harness sets it from the actual fill (``Entries.stop_dist``).
    """
    close, hi, lo, atr = (np.asarray(x, np.float64) for x in (close, box_hi, box_lo, atr))
    d = np.asarray(side, np.int64)
    raw = np.where(d == 1, close - lo, hi - close)
    return np.minimum(np.maximum(raw, floor * atr), cap * atr)


def trail_exits(close, atr, bar, side, mult: float = TRAIL_ATR) -> np.ndarray:
    """
    X-TR's exit decision per entry (PREREG 6.9): for an entry at breakout bar e of side +1, the first bar b > e with
    ``close[b] < max(close[e+1 .. b]) - mult * atr[b]``; of side -1, the first b > e with ``close[b] > min(close[e+1 ..
    b]) + mult * atr[b]``; -1 when the bars end first. The closes since the entry start with the bar after the breakout
    bar (the fill is at the next M1 open after its close; reading 1); the level uses each bar's own ATR and is not
    ratcheted (reading 2); strict. A NaN ATR decides nothing. Decided at b's close (the harness fills the exit at the
    next M1 open). The bars are scanned forward in growing chunks (numpy), so the cost is the holding time.
    """
    c, a = np.asarray(close, np.float64), np.asarray(atr, np.float64)
    bar, side = np.asarray(bar, np.int64).ravel(), np.asarray(side, np.int64).ravel()
    if c.shape != a.shape or c.ndim != 1:
        raise ValueError("close and atr must be 1-D series of one length")
    if bar.shape != side.shape:
        raise ValueError("bar and side must have one length")
    if len(bar) and (bar.min() < 0 or bar.max() >= len(c)):
        raise ValueError("an entry's bar is outside the series")
    if not np.all(np.isin(side, (-1, 1))):
        raise ValueError("side must be +1 or -1")
    n = len(c)
    out = np.full(len(bar), -1, np.int64)
    with np.errstate(invalid="ignore"):
        for k in range(len(bar)):
            e, d = int(bar[k]), int(side[k])
            lo, step, ext = e + 1, 64, None
            while lo < n:
                hi = min(n, lo + step)
                seg = c[lo:hi]
                if d == 1:
                    run = np.maximum.accumulate(seg) if ext is None else np.maximum(np.maximum.accumulate(seg), ext)
                    hit = seg < run - mult * a[lo:hi]
                else:
                    run = np.minimum.accumulate(seg) if ext is None else np.minimum(np.minimum.accumulate(seg), ext)
                    hit = seg > run + mult * a[lo:hi]
                j = np.flatnonzero(hit)
                if len(j):
                    out[k] = lo + int(j[0])
                    break
                ext, lo, step = float(run[-1]), hi, min(step * 4, 1 << 16)
    return out


def grade_masks(high, low, atr, volume, adx) -> Dict[str, np.ndarray]:
    """
    PREREG 6.9's grades per bar (read at a breakout bar), inclusive: BIG ``high - low >= 1.5 * atr``; VOL ``volume >=
    1.5 * ta.sma(volume, 20)`` (study 1's ``tradeiq_ind.sma``, ``pine_sma``: the bar and the 19 before it; NaN, so
    False, on bars 0-18); ADX ``adx >= 20``; ALL3 the three together; ``none`` True. A comparison with NaN is False.
    """
    h, l, a, v, x = (np.asarray(z, np.float64) for z in (high, low, atr, volume, adx))
    n = len(h)
    if any(z.shape != (n,) for z in (l, a, v, x)):
        raise ValueError("high, low, atr, volume and adx must be 1-D series of one length")
    vs = I.sma(v, VOL_LEN) if n else np.zeros(0)
    with np.errstate(invalid="ignore"):
        big = (h - l) >= BIG_ATR * a
        vol = v >= VOL_MULT * vs
        adx_ok = x >= ADX_MIN
    return {"none": np.ones(n, bool), "BIG": big, "VOL": vol, "ADX": adx_ok, "ALL3": big & vol & adx_ok}


# ───────────────────────────── the indicators (cached in the Context) ─────────────────────────────

def coil_of(ctx: M.Context, tf: str) -> Dict[str, np.ndarray]:
    """``tradeiq2_ind_coil.coil(o, h, l, c)`` of ``ctx.bars(tf)`` with the plan's settings (bid OHLC of the study's
    bars), read-only, cached as (MODULE, symbol, tf, COIL_PARAMS). Every value of bar t is known at its close."""
    _check_tf(tf)

    def make():
        b = ctx.bars(tf)
        out = CI.coil(b.o, b.h, b.l, b.c)
        if tuple(out) != CI.KEYS or any(len(v) != len(b) for v in out.values()):
            raise AssertionError("the coil port's contract changed")
        return {k: _ro(v) for k, v in out.items()}
    return ctx.get(MODULE, tf, COIL_PARAMS, make)


def grade_mask(ctx: M.Context, tf: str, grade: str) -> np.ndarray:
    """The grade's mask per bar of ``tf`` (``grade_masks`` on the bars, ``ctx.atr(tf)``, ``ctx.volume(tf)`` and the
    port's ADX), read-only, cached. Only VOL and ALL3 read the volume (BTC: the Binance klines)."""
    _check_tf(tf)
    _check("grade", grade, GRADES)

    def make():
        b = ctx.bars(tf)
        n = len(b)
        if grade == "none":
            return _ro(np.ones(n, bool))
        if grade == "ALL3":
            return _ro(grade_mask(ctx, tf, "BIG") & grade_mask(ctx, tf, "VOL") & grade_mask(ctx, tf, "ADX"))
        nan = np.full(n, np.nan)
        atr = np.asarray(ctx.atr(tf), np.float64)
        vol = np.asarray(ctx.volume(tf), np.float64) if grade == "VOL" else np.zeros(n)
        adx = coil_of(ctx, tf)["adx"] if grade == "ADX" else nan
        return _ro(grade_masks(b.h, b.l, atr, vol, adx)[grade])
    return ctx.get(MODULE, tf, {"series": "grade", "grade": grade}, make)


def trend_gate(ctx: M.Context, tf: str, rule: str) -> Tuple[np.ndarray, np.ndarray]:
    """(allow_long, allow_short) per bar of ``tf`` for the rule's trend filter, read at the breakout's close:
    COIL-RIB ``ribbon_trend(tf) == +1`` / ``== -1`` (the same timeframe's ribbon, cached here), COIL-MA ``ctx.allow(tf,
    'F1')``, COIL-0 ``ctx.allow(tf, 'F0')``."""
    _check_tf(tf)
    _check("rule", rule, RULES)
    if rule == "COIL-MA":
        return ctx.allow(tf, "F1")
    if rule == "COIL-0":
        return ctx.allow(tf, "F0")

    def make():
        tr = np.asarray(F.ribbon_trend(ctx, tf), np.float64)
        if tr.shape != (len(ctx.bars(tf)),):
            raise AssertionError(f"the ribbon trend has shape {tr.shape}, the bars {len(ctx.bars(tf))}")
        with np.errstate(invalid="ignore"):
            return _ro(tr == 1.0), _ro(tr == -1.0)
    return ctx.get(MODULE, tf, {"series": "ribbon-gate"}, make)


def breakouts(ctx: M.Context, tf: str) -> Dict[str, np.ndarray]:
    """
    Every breakout of the port on ``tf`` (before any filter or grade), one row each, read-only, cached: ``bar``,
    ``side`` (+1 / -1), ``coil`` (the coil's ordinal, ``coil_ids``), ``close``, ``box_hi`` / ``box_lo`` (the broken
    box), ``atr`` (ATR(14) of the bar), ``raw`` (the distance to the opposite edge), ``stop`` (``stop_distance``) and
    ``trail`` (``trail_exits``: X-TR's exit bar, -1 none).
    """
    _check_tf(tf)

    def make():
        b = ctx.bars(tf)
        co = coil_of(ctx, tf)
        atr = np.asarray(ctx.atr(tf), np.float64)
        k = np.flatnonzero(co["breakout"] != 0).astype(np.int64)
        d = co["breakout"][k].astype(np.int64)
        close, hi, lo = b.c[k], co["bo_box_hi"][k], co["bo_box_lo"][k]
        out = {"bar": k, "side": d, "coil": coil_ids(co["armed"], co["box_hi"], co["box_lo"])[k],
               "close": close.astype(np.float64), "box_hi": hi, "box_lo": lo, "atr": atr[k],
               "raw": np.where(d == 1, close - lo, hi - close), "stop": stop_distance(close, hi, lo, d, atr[k]),
               "trail": trail_exits(b.c, atr, k, d)}
        if len(k) and (out["coil"] < 0).any():
            raise AssertionError("a breakout on a bar where no coil is armed")
        return {key: _ro(v) for key, v in out.items()}
    return ctx.get(MODULE, tf, {"series": "breakouts"}, make)


# ───────────────────────────── the rule ─────────────────────────────

def coil_entries(ctx: M.Context, tf: str, rule: str = "COIL-0", exit: str = "X-TR", grade: str = "none") -> M.Entries:
    """
    The market entries of one COIL row: every breakout with a stop (``breakouts``; reading 9), its ``stop_dist``, the
    trail's ``exit_bar``, ``target_r`` 3 for X-3R, ``tag`` = its coil; kept where the rule's trend filter allows its
    side at the breakout bar (``tradeiq2_filters.gate_entries``) and its grade holds there.
    """
    _check_tf(tf)
    _check("rule", rule, RULES)
    _check("exit", exit, EXITS)
    _check("grade", grade, GRADES)
    if rule != "COIL-RIB" and grade != "none":
        raise ValueError(f"{rule} has no grades (PREREG 6.9: COIL-MA and COIL-0 x X-TR x none)")
    T = breakouts(ctx, tf)
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(T["stop"]) & (T["stop"] > 0)
    E = M.entries(T["bar"][ok], T["side"][ok], stop_dist=T["stop"][ok],
                  target_r=TARGET_R if exit == "X-3R" else None, exit_bar=T["trail"][ok], tag=T["coil"][ok])
    E = F.gate_entries(E, *trend_gate(ctx, tf, rule))
    g = grade_mask(ctx, tf, grade)
    return E.take(g[E.bar]) if len(E) else E


def coil_exec(ctx: M.Context, tf: str, rule: str = "COIL-0", exit: str = "X-TR", grade: str = "none",
              label: str = "") -> M.Exec:
    """The EVENTS Exec of one COIL row: ``coil_entries`` as market entries, one position at a time; no per-bar exit
    masks, no legs, no tightening (the trail is each entry's ``exit_bar``)."""
    return M.event_exec(tf, entries=coil_entries(ctx, tf, rule, exit, grade), label=label)


# ───────────────────────────── the grid ─────────────────────────────

def _v(symbol: str, tf: str, rule: str, exit: str, grade: str) -> M.Variant:
    return M.Variant(f"{symbol}|{tf}|{FAMILY}|{rule}|{exit}|{grade}", symbol, tf, SCRIPT, FAMILY, True, "",
                     {"rule": rule, "filter": RULE_FILTER[rule], "exit": exit, "grade": grade, "stop": STOP_NAME})


def variants(symbol: str) -> List[M.Variant]:
    """
    EXACTLY the rows of PREREG 6.9 for ``symbol`` (the module docstring's table): 36 on XAUUSDm and on BTCUSDm, in the
    order COIL-RIB (timeframe, exit, grade), COIL-MA (timeframe), COIL-0 (timeframe); none on the claim markets. All
    eligible (PREREG 6.9 marks none "not eligible" or "information only"). Raises for a symbol not of this study.
    """
    if symbol not in M.ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(M.ALL_SYMBOLS)})")
    if symbol not in M.SYMBOLS:
        return []
    out = [_v(symbol, tf, "COIL-RIB", ex, g) for tf in TFS for ex in EXITS for g in GRADES]
    out += [_v(symbol, tf, rule, "X-TR", "none") for rule in ("COIL-MA", "COIL-0") for tf in TFS]
    return out


_CANON: Dict[str, Dict[str, M.Variant]] = {}


def _canonical(symbol: str) -> Dict[str, M.Variant]:
    if symbol not in _CANON:
        _CANON[symbol] = {v.id: v for v in variants(symbol)}
    return _CANON[symbol]


def _row(variant: M.Variant) -> M.Variant:
    v = _canonical(variant.symbol).get(variant.id) if variant.symbol in M.ALL_SYMBOLS else None
    if v is None or (v.tf, v.family, v.script) != (variant.tf, variant.family, variant.script):
        raise ValueError(f"{variant.id}: not a row of PREREG 6.9 (tradeiq2_rules_coil.variants)")
    return v


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The ``tradeiq2_market.Exec`` of one row of ``variants`` (looked up by its id; the settings are the canonical
    row's): ``coil_exec``. The Exec's label is the id."""
    v = _row(variant)
    if v.symbol != ctx.symbol:
        raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
    p = dict(v.params)
    return coil_exec(ctx, v.tf, p["rule"], p["exit"], p["grade"], label=v.id)


def describe(variant: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    v = _row(variant)
    p = dict(v.params)
    return (f"Our coil breakout {p['rule']} (PREREG 6.9; TradeIQ's Coil Breakout AI is private) on {v.tf} bars of the "
            "bid (UTC): a coil is at least 6 consecutive bars whose Bollinger band (SMA 20 +- 2 population stdev) lies "
            "inside the Keltner channel (SMA 20 +- 1.5 ATR 20); its box spans the run's highest high and lowest low; "
            "it is armed for 12 bars from the first bar after the run, until a newer coil replaces it; the first close "
            "above the box opens a long, below it a short (once per coil), decided at that close and filled at the "
            f"open of the next M1 bar; trend filter: {RULE_WORDS[p['rule']]}; grade: {GRADE_WORDS[p['grade']]}; stop: "
            "the distance from the breakout close to the opposite box edge, clamped to 0.75-3 x ATR(14), set from the "
            f"fill and never moved; {EXIT_WORDS[p['exit']]}. One position at a time: a breakout while a trade is open "
            "is skipped")


def warm(ctx: M.Context, variants_: Sequence[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, every array the given rows read: the coil, the
    breakouts with their stops and trails, the trend gates (the ribbon, F1) and the grades (with the volume)."""
    for v in variants_:
        v = _row(v)
        p = dict(v.params)
        breakouts(ctx, v.tf)
        trend_gate(ctx, v.tf, p["rule"])
        grade_mask(ctx, v.tf, p["grade"])


def plan_counts(symbol: str) -> Dict[Tuple[str, bool], int]:
    """The rows ``variants(symbol)`` gives per (family, eligible), for the grid check."""
    out: Dict[Tuple[str, bool], int] = {}
    for v in variants(symbol):
        out[(v.family, bool(v.eligible))] = out.get((v.family, bool(v.eligible)), 0) + 1
    return out


def breakout_table(ctx: M.Context, tf: str, volume: bool = True) -> pd.DataFrame:
    """
    Event geometry for reports and checks (no profit or loss): per port breakout of ``tf``, its bar, close time, side,
    coil, close, box, ATR(14), the raw and the clamped stop in ATR (and whether the floor or the cap acted), the bar's
    range in ATR, the grades (``volume=False`` skips VOL and ALL3, which read the volume), the ribbon trend and F1 at
    the bar, and the trail's exit bar with the bars held to it.
    """
    T = breakouts(ctx, tf)
    b = ctx.bars(tf)
    k = T["bar"]
    with np.errstate(invalid="ignore", divide="ignore"):
        rib_l, rib_s = trend_gate(ctx, tf, "COIL-RIB")
        ma_l, ma_s = trend_gate(ctx, tf, "COIL-MA")
        long_ = T["side"] == 1
        out = pd.DataFrame({
            "bar": k, "close_time": pd.to_datetime(b.tc[k], unit="s", utc=True), "side": T["side"],
            "coil": T["coil"], "close": T["close"], "box_hi": T["box_hi"], "box_lo": T["box_lo"], "atr": T["atr"],
            "raw_atr": T["raw"] / T["atr"], "stop_atr": T["stop"] / T["atr"],
            "capped": T["raw"] > STOP_CAP_ATR * T["atr"], "floored": T["raw"] < STOP_FLOOR_ATR * T["atr"],
            "range_atr": (b.h[k] - b.l[k]) / T["atr"],
            "BIG": grade_mask(ctx, tf, "BIG")[k], "ADX": grade_mask(ctx, tf, "ADX")[k],
            "adx": coil_of(ctx, tf)["adx"][k],
            "ribbon_ok": np.where(long_, rib_l[k], rib_s[k]), "f1_ok": np.where(long_, ma_l[k], ma_s[k]),
            "trail_bar": T["trail"], "held_bars": np.where(T["trail"] >= 0, T["trail"] - k, -1),
        })
        if volume:
            out["VOL"] = grade_mask(ctx, tf, "VOL")[k]
            out["ALL3"] = grade_mask(ctx, tf, "ALL3")[k]
    return out
