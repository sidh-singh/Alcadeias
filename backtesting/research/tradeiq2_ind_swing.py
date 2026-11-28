"""
Swing Profile (BigBeluga), port A: the 50-bar swing legs, their volume profile, point of control (POC) and buy/sell
delta, for the leg that is still forming at every bar and for every leg a direction flip finishes.

    from backtesting.research import tradeiq_market as TM, tradeiq2_ind_swing as SP
    mk = TM.load("XAUUSDm", end="2024-07-01")
    b = mk.tbars("1H")                                    # 1H and 4H: the timeframes of PREREG 6.4
    vol = b.vol.astype(float)                             # gold: tick volume; BTC: TM.binance_volume(mk, "1H")[0]
    out = SP.swing_profile(b.o, b.h, b.l, b.c, vol)       # the script's defaults (50, ATR 200, bins of 0.5 ATR)
    out["f_poc"]       # the forming leg's POC at every bar, from the swing points confirmed by that bar's close
    out["legs"]        # one row per direction flip: the finished leg, known from its flip bar's close on

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 2, 5, 6.4, 7 and claims 11-12 of section 8); the
specification is the study's map of the script (``orb_session_swing_ha.md``, section 3). The script is "Swing Profile
[BigBeluga]" (Pine v6, CC BY-NC-SA 4.0, (c) BigBeluga). Line numbers (l.) are those of the owner's plain-text copy
(l.1-424); the source itself is not in this repository. Port A (this module, the production port) and port B
(``tests/tradeiq2_oracle_swing.py``) were written independently from the source and the specification. About 80 of
the script's lines compute anything (l.11, 57-85, 90-141 and the forming-leg copy l.200-246 / 307-351); the rest
draws boxes, polylines, labels and lines. l.408-424 (a moving-average input block whose ``ma()`` is plotted with
the type "None", i.e. na) and every colour, style and size input change no number.

Reconciled with port B on 28 Nov 2026 (``tests/test_tradeiq2_ind_swing.py``; the notes are
``backtest_results/tradeiq_2027/porting/swing.md``): bit for bit on every key of the 1H / 4H / 1D bars of both
symbols to 2024-06-30. One change here: a leg needing more than 100,000 bins is not computable (reading 5); this
port used to compute up to 1,000,000 and raise above.

The contract (both ports)
-------------------------
``swing_profile(o, h, l, c, v, swing_len=50, atr_len=200, bin_mult=0.5)`` returns a dict with exactly the keys
``KEYS``. Every array has ``len(c)`` values, one per bar, oldest first; bar t's value is the state at bar t's close.

================ ======= ===================================================================================
key              dtype   value
================ ======= ===================================================================================
``is_down_move`` bool    ``isDownMove`` (l.61, 69-72): true from a bar that is a new ``swing_len``-bar high, false
                         from one that is a new ``swing_len``-bar low; the low wins on a bar that is both
``hs_bar``       int64   the stored swing high ``highSwing`` (l.75-77): its bar, -1 while none is stored
``hs_price``     float64 its price (the bar's high), NaN while none
``ls_bar``       int64   the stored swing low ``lowSwing`` (l.80-82), -1 while none
``ls_price``     float64 its price (the bar's low), NaN while none
``flip``         bool    ``isDownMove != isDownMove[1]`` (l.90): a leg is finished at this bar's close
``f_dir``        int8    the forming leg's geometry: +1 if the stored swing high is newer than the stored swing low
                         (the leg went up), -1 if older, 0 if either is missing or both are the same bar
``f_lo``         float64 ``swingBottom = math.min(highSwing.price, lowSwing.price)`` (l.214), NaN if a swing is
                         missing
``f_hi``         float64 ``swingTop = math.max(...)`` (l.215), NaN if a swing is missing
``f_poc``        float64 the forming leg's POC with this bar's ATR: the level of the bin with the most volume; among
                         tied bins the one nearest this bar's close. NaN when not computable: the ATR is na, a swing
                         is missing, ``binCount == 0`` or above Pine's array limit of 100,000 (reading 5), or the
                         leg's bins hold no volume at all
``f_poc_ties``   int64   the number of bins tied at the maximum (1 = no tie); 0 where ``f_poc`` is NaN
``f_delta_pct``  float64 ``(buy - sell) / total`` of the forming leg's bins, a fraction in [-1, 1] (the script's label
                         shows it times 100, l.291); NaN where there are no bins or the bins are empty
``f_total``      float64 ``volumeBins.sum()`` (l.288): the bins' total, NaN where there are no bins
``legs``         frame   the FINISHED legs, one row per flip bar (``LEG_COLUMNS``), oldest first
================ ======= ===================================================================================

``legs`` columns: ``flip_bar`` (int64), ``dir`` (int8: +1 = the up leg, finished by a flip to false, i.e. by a new
``swing_len``-bar low; -1 = the down leg, finished by a flip to true), ``start_bar`` / ``end_bar`` (int64:
``prevSwingIndex`` / ``lastSwingIndex``, the older and the newer of the two stored swing bars, both inside the
profile; -1 when a swing is missing), ``lo`` / ``hi`` (float64: ``swingBottom`` / ``swingTop``), ``poc`` (the POC;
ties go to the tied bin nearest the FLIP bar's close), ``poc_all`` (object: every tied POC level as a tuple, ascending;
``()`` when none), ``delta_pct``, ``total`` (as the forming leg's), ``fifty`` (``(lo + hi) / 2``, the placebo level of
PREREG 6.4) and ``atr_at_flip`` (``ta.atr(atr_len)`` at the flip bar; the bins are ``bin_mult`` times it). A row
whose leg cannot be computed (a swing missing, the ATR na, ``binCount == 0`` or above 100,000) is kept with NaN
values: on the study's bars that happens only in the first weeks of each series (reading 5).

A finished leg's row equals the forming leg of its flip bar (the same stored points, the same bar's ATR, the same
close for the tie rule), apart from ``dir``, which is the flip's side and not the geometry (reading 11 below).

What the script computes on each bar, in its order
--------------------------------------------------
1. ``highestSwingHigh = ta.highest(swingLen)``, ``lowestSwingLow = ta.lowest(swingLen)`` (l.66-67). The one-argument
   forms read ``high`` and ``low``; the current bar is in the window (bars t-49 .. t).
2. ``if high == highestSwingHigh: isDownMove := true``; then ``if low == lowestSwingLow: isDownMove := false``
   (l.69-72). A tie with an older bar of the window counts (``==``). On a bar that is both, the second assignment
   wins: false.
3. ``if high[1] == highestSwingHigh[1] and high < highestSwingHigh`` then ``highSwing := (bar_index[1], high[1])``
   (l.75-77): the previous bar was a ``swingLen``-bar high and this bar is not one. A swing is stored one bar late,
   with the index of the bar before; of two equal highs in a row the later one is stored (the first fails the strict
   ``<``). Every newer qualifying bar overwrites the stored point. The swing low mirrors this with ``>`` (l.80-82).
4. ``priceBinSize = ta.atr(200) * 0.5`` (l.85): study 1's verified ``tradeiq_ind.atr`` (``pine_atr``: Wilder's RMA
   seeded with the SMA of the first 200 true ranges, the first true range high - low), times ``bin_mult``.
5. On a flip (l.90), the leg between the stored ``highSwing`` and ``lowSwing`` is profiled (l.106-141):

       swingBottom = math.min(H, L)          swingTop = math.max(H, L)              H, L: the stored prices
       binCount    = int(math.abs(H - L) / priceBinSize)                            truncation (floor for >= 0)
       binStep     = math.abs(H - L) / binCount
       for i = bar_index - lastSwingIndex to bar_index - prevSwingIndex             bars last, last-1, .., prev
           for k = 0 to binCount - 1
               binMidPrice = swingBottom + (k * binStep) + (binStep / 2)
               if math.abs(binMidPrice - close[i]) < binStep                        strict
                   volumeBins[k] += volume[i]
                   close[i] > open[i] ? buyVolumeBins[k] += volume[i] : sellVolumeBins[k] += volume[i]

   So a bar's volume goes to every bin whose midpoint is less than one step from its close: two bins (the one
   holding the close and the nearer neighbour), one when the close is exactly on a midpoint, one in the outer half of
   the top or bottom bin, also for a close less than half a step outside the leg, and none from half a step outside
   on. A doji (close == open) counts as sell. Bars after the newer swing, up to the flip bar, are not read.
6. The POC is every bin with ``volumeBins.get(k) / volumeBins.max() == 1`` (l.149, 153), drawn at
   ``math.avg(binLow, binHigh)`` (l.154) with ``binLow = swingBottom + (k * binStep)``, ``binHigh = binLow +
   binStep`` (l.146-147). The tooltip shows ``volumeBins.sum()``, the buy and sell sums and ``(buy - sell) / total *
   100`` (l.183-187).
7. On every bar the script also clears and, on the last bar only (``barstate.islast``, l.207 / 313), redraws the
   FORMING leg with the same algorithm on the currently stored pair and the current ATR (l.214-246 and the identical
   l.319-351; the two branches differ only in where the label sits, l.293 / 395).

How this module computes it
---------------------------
* ``swings`` (steps 1-3) is exact array logic: ``ta.highest`` / ``ta.lowest`` as sliding-window extremes (na for the
  first ``swing_len - 1`` bars), ``isDownMove`` as the side of the latest bar with an event (a bar with both events
  counts as a low), the stored points as the latest confirmation at or before each bar.
* ``_forming_kernel`` (numba) profiles the forming leg at every bar with exactly the script's float operations, in its
  order: the bars from the newer swing back to the older one, each bin accumulating its bars in that order. Instead of
  testing all ``binCount`` bins per bar it tests the five bins around ``floor((close - swingBottom) / binStep)`` with
  the script's own comparison, which contains every bin that can pass it (the passing bins are the one or two whose
  midpoint is within one step; the tests check the result against the all-bins loop bit for bit).
* The ``legs`` rows are the forming leg of each flip bar; ``poc_all`` comes from ``leg_profile`` on the same numbers.

What is known when (no look-ahead)
----------------------------------
* ``is_down_move[t]``, ``flip[t]``: the window t-49 .. t and the state of bar t-1, known at t's close. A flip is
  final at its bar's close (no ``request.security``, no ``varip``; on TradingView's realtime bar it can appear and
  vanish inside the bar).
* ``hs_* [t]`` / ``ls_* [t]``: a swing at bar j is known only from bar j + 1's close (one-bar confirmation).
* ``f_*[t]``: the stored points at t (both at bars <= t - 1), the bars between them, the ATR and the close of t.
  It keeps changing until the next flip (the ATR moves the bins every bar; a newer confirmation moves the leg), but
  every value is known at t's close.
* A ``legs`` row exists from its ``flip_bar``'s close on. Its POC and delta are NOT known before that bar, even though
  the script draws them back over the leg's span ``[start_bar, end_bar]``: using a finished leg's POC before its flip
  bar is look-ahead. On the study's 1H / 4H bars of 2019-2022 the flip comes a median 25-28 bars after the leg's
  newer swing (90th percentile 48-56), and at the flip the close is already past the finished leg's POC in the new
  direction in 66-72 % of the legs.
* Removing the bars after t changes nothing up to t (tested): every output at t reads bars 0 .. t only.

Readings where the source or the platform leaves a choice
---------------------------------------------------------
Counts are of bars or flips closing in 2019-2022 on study 1's 1H / 4H bars (gold from 2017-01-03 with its tick
volume, BTC from 2018-01-01 with Binance's volume), with the defaults; counts only, no profit or loss. The study's
own bars start gold on 2016-01-03 (``tradeiq2_market.load``); from 2019 on that changes no value on 1H and only the
last bits of ``atr_at_flip`` on 4H (56 of 117 legs of 2019-2022, at most 6.4e-9 relative; the reconciliation,
``backtest_results/tradeiq_2027/porting/swing.md``).

1. ``ta.highest`` / ``ta.lowest`` are na until ``swing_len`` bars exist (TradingView's rule for a call on every bar);
   the comparisons with na are false, so nothing happens before bar ``swing_len - 1``. The alternative (the extreme
   of the bars available) gives another state only on the first 108-272 bars of each series (to 2017-01 on gold,
   2018-02 on BTC; 153-299 bars, to 2016-03 on gold, on the study's bars from 2016): after the first events the two
   readings have the same state.
2. Pine v6 bools are never na: ``isDownMove[1]`` on bar 0 is false, so bar 0 is no flip (``isDownMove`` starts false
   and cannot change on bar 0 when ``swing_len > 1``).
3. ``calc_bars_count = 2000`` (l.6), TradingView's display limit, is not emulated: the script runs from the first bar
   given (study 1's ``load``: gold 2017-01, BTC 2018-01). On TradingView the ATR(200) would be re-seeded 2,000 bars
   before the chart's last bar, which moves with the chart; the seed's weight decays as (199/200)^n. Measured with a
   2,000-bar chart ending at the bar that computes the profile: the ATR differs from ours by at most 1.4e-4 (median
   5e-6, relative) at the 1H / 4H flips; no finished leg changes its bin count; 1 of 1,500 sampled BTC 1H forming bars
   does (and its POC moves), none of gold's.
4. ``max_bars_back = 5000`` (l.6): a profile reading more than 5,000 bars back would stop the script. Here there is no
   limit; on the study's bars to 2024-06-30 no flip reads further back than 475 bars (BTC 4H; BTC 1H 426, gold 1H 430
   from 2017 and 452 from 2016, gold 4H 317) and no forming leg further than 475 (BTC 4H; BTC 1H 427), so the limit
   is never reached.
5. A leg that cannot be profiled: the ATR na (the first ``atr_len - 1`` bars), a swing missing (the first legs),
   ``binCount == 0`` (a leg shorter than one bin), or ``binCount`` above 100,000, Pine's limit on the size of an array
   (``array.new<float>(binCount, 0.)``, l.117; a bin size near zero, e.g. an ATR that decays towards 0 on flat bars).
   The script would divide by zero, loop 0 to -1 or exceed the array limit (runtime errors that stop it on
   TradingView); here its POC, ties, delta and total are NaN / 0 / NaN / NaN and its row is kept. On the study's bars
   they occur only in the first weeks of the data: the last such leg closes 2016-03-14 (gold 4H; 2017-02-02 from
   study 1's start) and 2018-02-14 (BTC 4H); every bar from 2019 on has a forming POC, and no forming or finished
   leg of the 1H / 4H / 1D bars to 2024-06-30 needs more than 111 bins (BTC 1H).
   (Before the reconciliation this port raised above 1,000,000 bins and computed the legs in between; port B's
   reading, the array limit, is the script's: ``backtest_results/tradeiq_2027/porting/swing.md``.)
6. A leg whose bins hold no volume (possible only with zero volume on every bar of it): ``volumeRatio`` is 0 / 0, no
   bin equals 1, so there is no POC; the total is 0 and the delta NaN. Never on the study's bars.
7. The POC test ``volumeBins.get(k) / volumeBins.max() == 1`` (l.153) is evaluated as ``volumeBins[k] ==
   max``. For a positive maximum the two are the same for every float (y / x rounds to 1 only when y == x). Volumes
   are added newest bar first, as l.125 loops; two bins that received the same bars therefore tie bit for bit.
8. The POC level is the drawn line's ``math.avg(binLow, binHigh)`` = ``(binLow + binHigh) / 2`` (l.146-147, 154),
   not ``binMidPrice`` (l.132, the assignment's midpoint). The two differ in the last bits on a fifth to a quarter of
   the forming bars, which could matter only to a price exactly equal to the POC: no comparison of a bar's low, high or
   close with the POC changes between the two in 2019-2022.
9. Ties (l.153 draws a line for every tied bin): the PREREG's rule picks the tied bin nearest the close of the bar
   that uses it (the forming bar, or the flip bar for a finished leg), by ``|level - close|``; at an exactly equal
   distance the lower bin. ``poc_all`` keeps every tied level. Ties (two bins that hold the same bars, typically in a
   fast part of the leg): 2.2 % / 0 % of gold's 1H / 4H legs, 2.8 % / 0.9 % of BTC's, and 0.1-3.4 % of the forming
   bars. The nearest tied bin is not the lowest one in 4 (gold 1H), 9 (BTC 1H) and 1 (BTC 4H) legs; an exactly equal
   distance never occurs.
10. Delta and total are the sums of the BINS (l.184-187), as the tooltip shows them: a bar counted in two bins counts
   twice, an edge bar once and a bar outside the bins not at all. They are not the leg's raw bar volume. The sums run
   over k ascending (``array.sum``'s order is not documented); with gold's integer tick volumes any order gives the
   same numbers, with BTC's Binance volumes another order could move the last bit. The delta is returned as a
   fraction, not times 100. The raw bars' delta (each bar once) has another sign than the bins' on 1 gold 1H leg and
   1 BTC 4H leg.
11. ``dir`` of a finished leg is the flip's side (l.99, 181: a flip to false draws the lime up leg). The stored points
   are normally in that order (the newer swing is the leg's end), but when the flip bar is itself both a new high and
   a new low the stored pair can be the previous leg's. In 2019-2022 this happens once: BTC 1H, the FOMC hour
   2022-09-21 18:00 UTC comes one bar after a new high (a flip to true at 17:00) and is both extremes, so it finishes
   the same stored pair again with dir +1 (two consecutive rows with the same pair, POC and delta). Two more BTC 1H
   flips (2019-03-15 12:00, 2020-08-05 12:00) finish a pair whose two swings are one outside bar (start_bar ==
   end_bar). ``f_dir`` is the geometry, and 0 when both stored swings are the same bar (an outside bar that was both
   a new high and a new low, confirmed on both sides by the next bar): 46 gold 1H bars (2 episodes) and 115 BTC 1H
   bars (4 episodes) of 2019-2022, none on 4H.
12. The forming leg (l.200-403) is drawn on the last bar only. The plan computes it at every bar as if that bar were
   the last closed bar: the script's own values for a chart that ends there. TradingView's intrabar updates of the
   realtime bar are not modelled (closed bars only).
13. The source is the bid OHLC of the study's bars (UTC boundaries, a short UTC day merged into the next; PREREG 2) and
   the volume is gold's tick volume and BTC's Binance BTCUSDT spot volume (an hour without a kline has volume 0).
   TradingView's own bars and volume of these symbols differ, so swing points and POCs can differ from its chart.
Everything else follows the source literally; nothing is tuned (every default is the script's).
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from numba import njit
from numpy.lib.stride_tricks import sliding_window_view

from . import tradeiq_ind as I

__all__ = ["KEYS", "LEG_COLUMNS", "DEFAULTS", "PINE_ARRAY_MAX", "highest", "lowest", "swings", "leg_profile",
           "swing_profile"]

NAN = math.nan

KEYS = ("is_down_move", "hs_bar", "hs_price", "ls_bar", "ls_price", "flip", "f_dir", "f_lo", "f_hi", "f_poc",
        "f_poc_ties", "f_delta_pct", "f_total", "legs")

LEG_COLUMNS = ("flip_bar", "dir", "start_bar", "end_bar", "lo", "hi", "poc", "poc_all", "delta_pct", "total", "fifty",
               "atr_at_flip")

DEFAULTS: Dict[str, float] = {      # the script's inputs and constants
    "swing_len": 50,                # l.11 "Swing Length" (minval 10)
    "atr_len": 200,                 # l.85 ta.atr(200) (a constant of the script, not an input)
    "bin_mult": 0.5,                # l.85 "* 0.5" (a constant)
}

PINE_ARRAY_MAX = 100_000            # Pine's limit on the size of an array: more bins is not computable (reading 5)


# ───────────────────────────── input checks ─────────────────────────────

def _series(x, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)              # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    return a


def _int(n, name: str) -> int:
    """A Pine length: an integer >= 1 (an integral float is accepted). The script's input refuses a swing length
    below 10 (l.11); shorter ones are accepted here for hand-made tests."""
    if isinstance(n, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {n!r}")
    f = float(n)
    if not (f >= 1.0 and f.is_integer()):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    return int(f)


def _positive(x, name: str) -> float:
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {x!r}")
    f = float(x)
    if not (math.isfinite(f) and f > 0.0):
        raise ValueError(f"{name}: a finite number > 0 is expected, got {x!r}")
    return f


def _bars(o, h, l, c, v) -> Tuple[np.ndarray, ...]:
    o, h, l, c, v = (_series(x, k) for x, k in ((o, "o"), (h, "h"), (l, "l"), (c, "c"), (v, "v")))
    n = len(c)
    if not len(o) == len(h) == len(l) == len(v) == n:
        raise ValueError(f"o, h, l, c, v: series of equal length are expected, got {len(o)}, {len(h)}, {len(l)}, "
                         f"{n}, {len(v)}")
    for x, k in ((o, "o"), (h, "h"), (l, "l"), (c, "c"), (v, "v")):
        if not np.isfinite(x).all():
            raise ValueError(f"{k}: na or an infinite value at bar {int(np.argmax(~np.isfinite(x)))}; bars are "
                             "expected to be complete (an hour without a Binance kline has volume 0)")
    if (v < 0).any():
        raise ValueError(f"v: a negative volume at bar {int(np.argmax(v < 0))}")
    return o, h, l, c, v


# ───────────────────────────── l.66-82: the swing points and the direction ─────────────────────────────

def _extreme(x: np.ndarray, length: int, low: bool) -> np.ndarray:
    out = np.full(len(x), NAN)
    if len(x) >= length:
        win = sliding_window_view(x, length)
        out[length - 1:] = win.min(axis=1) if low else win.max(axis=1)
    return out


def highest(x, length) -> np.ndarray:
    """``ta.highest(x, length)`` called on every bar: the highest of the last ``length`` values, this bar included;
    na for the first ``length - 1`` bars. The series must not contain na (bars never do)."""
    return _extreme(_series(x, "x"), _int(length, "length"), False)


def lowest(x, length) -> np.ndarray:
    """``ta.lowest(x, length)`` called on every bar (see ``highest``)."""
    return _extreme(_series(x, "x"), _int(length, "length"), True)


def swings(h, l, swing_len: int = 50) -> Dict[str, np.ndarray]:
    """
    l.66-82 and l.90 on every bar: ``is_down_move``, the stored swing points and ``flip`` (as in ``swing_profile``),
    plus ``new_high`` / ``new_low`` (bool: ``high == ta.highest(swingLen)`` / ``low == ta.lowest(swingLen)``, l.69 /
    l.71), ``highest`` / ``lowest`` (the two window extremes, NaN for the first ``swing_len - 1`` bars) and
    ``hs_set`` / ``ls_set`` (bool: a swing high / low is confirmed at this bar's close, its index is this bar - 1).
    """
    h, l = _series(h, "h"), _series(l, "l")
    if len(h) != len(l):
        raise ValueError(f"h, l: series of equal length are expected, got {len(h)}, {len(l)}")
    L = _int(swing_len, "swing_len")
    n = len(h)
    hh = _extreme(h, L, False)                                        # l.66 ta.highest(swingLen) reads high
    ll = _extreme(l, L, True)                                         # l.67 ta.lowest(swingLen) reads low
    with np.errstate(invalid="ignore"):
        new_high = h == hh                                            # l.69 (na compares false)
        new_low = l == ll                                             # l.71
    idx = np.arange(n, dtype=np.int64)
    # l.69-72: isDownMove keeps its value until a bar with an event; on a bar with both, l.72 runs last: false
    ev = np.where(new_low, 0, np.where(new_high, 1, -1))
    last_ev = np.maximum.accumulate(np.where(ev >= 0, idx, -1)) if n else idx
    is_down = (last_ev >= 0) & (ev[np.maximum(last_ev, 0)] == 1)
    before = np.zeros(n, dtype=bool)                                  # isDownMove[1]: false on bar 0 (v6 bool)
    before[1:] = is_down[:-1]
    flip = is_down != before                                          # l.90
    # l.75-82: bar t-1 was a swingLen-bar extreme and bar t is strictly inside the window's extreme
    hs_set = np.zeros(n, dtype=bool)
    ls_set = np.zeros(n, dtype=bool)
    with np.errstate(invalid="ignore"):
        hs_set[1:] = new_high[:-1] & (h[1:] < hh[1:])
        ls_set[1:] = new_low[:-1] & (l[1:] > ll[1:])
    hs_bar = np.maximum.accumulate(np.where(hs_set, idx - 1, -1)) if n else idx
    ls_bar = np.maximum.accumulate(np.where(ls_set, idx - 1, -1)) if n else idx
    hs_price = np.where(hs_bar >= 0, h[np.maximum(hs_bar, 0)], NAN) if n else np.zeros(0)
    ls_price = np.where(ls_bar >= 0, l[np.maximum(ls_bar, 0)], NAN) if n else np.zeros(0)
    return {"is_down_move": is_down, "hs_bar": hs_bar.astype(np.int64), "hs_price": hs_price.astype(np.float64),
            "ls_bar": ls_bar.astype(np.int64), "ls_price": ls_price.astype(np.float64), "flip": flip,
            "new_high": new_high, "new_low": new_low, "highest": hh, "lowest": ll, "hs_set": hs_set,
            "ls_set": ls_set}


# ───────────────────────────── l.106-154: one leg's profile ─────────────────────────────

@njit(cache=True)
def _accumulate(o, c, v, bottom, step, nb, prev, last, vol, buy, sell):
    """l.125-141: the bars ``last`` down to ``prev`` (Pine's i = bar_index - last .. bar_index - prev), each bar's
    volume to every bin whose midpoint ``swingBottom + (k * binStep) + (binStep / 2)`` is less than ``binStep``
    from its close; buy when close > open, else sell. Only the bins k0 - 2 .. k0 + 2 around k0 = floor((close -
    bottom) / step) are tested, with the script's own expression: every bin that can pass is among them."""
    half = step / 2.0
    for j in range(last, prev - 1, -1):
        cc = c[j]
        x = (cc - bottom) / step
        if not (x > -3.0 and x < nb + 3.0):              # 3+ steps outside the leg (a bin needs < 0.5): skip
            continue
        k0 = int(math.floor(x))
        ka = k0 - 2
        if ka < 0:
            ka = 0
        kz = k0 + 3
        if kz > nb:
            kz = nb
        if ka >= kz:
            continue
        vv = v[j]
        up = cc > o[j]
        for k in range(ka, kz):
            mid = bottom + (k * step) + half
            if abs(mid - cc) < step:
                vol[k] = vol[k] + vv
                if up:
                    buy[k] = buy[k] + vv
                else:
                    sell[k] = sell[k] + vv


@njit(cache=True)
def _poc(vol, bottom, step, close):
    """l.149-154 and the PREREG's tie rule: the bins equal to the maximum, the level ``math.avg(binLow, binHigh)`` of
    the one nearest ``close`` (the lower one at an equal distance). Returns (level, ties, bin); (NaN, 0, -1) when the
    maximum is not positive (no volume in any bin)."""
    nb = len(vol)
    mx = vol[0]
    for k in range(1, nb):
        if vol[k] > mx:
            mx = vol[k]
    if not mx > 0.0:
        return np.nan, 0, -1
    ties = 0
    best_k = -1
    best_d = np.inf
    best = np.nan
    for k in range(nb):
        if vol[k] == mx:
            ties += 1
            bin_low = bottom + (k * step)
            bin_high = bin_low + step
            level = (bin_low + bin_high) / 2.0
            d = abs(level - close)
            if d < best_d:
                best_d = d
                best_k = k
                best = level
    return best, ties, best_k


@njit(cache=True)
def _sums(vol, buy, sell):
    """``volumeBins.sum()`` and ``(buyVolumeBins.sum() - sellVolumeBins.sum()) / volumeBins.sum()`` (l.184-187), the
    sums over k ascending; the delta is NaN when the total is 0."""
    st = 0.0
    sb = 0.0
    ss = 0.0
    for k in range(len(vol)):
        st = st + vol[k]
        sb = sb + buy[k]
        ss = ss + sell[k]
    delta = (sb - ss) / st if st > 0.0 else np.nan
    return st, delta


@njit(cache=True)
def _n_bins(hp, lp, bin_size, max_bins):
    """``binCount = int(math.abs(H - L) / priceBinSize)`` (l.110) and ``binStep`` (l.111); (0, NaN) when not computable:
    a bin size that is na or not positive, ``binCount == 0``, or ``binCount > max_bins`` (Pine's array limit; the
    quotient is tested before the conversion, so an infinite one is not computable either: int(x) > max_bins exactly
    when x >= max_bins + 1)."""
    if not bin_size > 0.0:
        return 0, np.nan
    rng = abs(hp - lp)
    x = rng / bin_size
    if not x < max_bins + 1.0:
        return 0, np.nan
    nb = int(x)
    if nb < 1:
        return 0, np.nan
    return nb, rng / nb


@njit(cache=True)
def _forming_kernel(o, c, v, hsb, hsp, lsb, lsp, bin_size, max_bins,
                    f_lo, f_hi, f_poc, f_ties, f_delta, f_total, f_nb):
    """The forming leg (l.214-246 with the POC of l.254-258) at every bar t: the stored pair of bar t, bar t's bin size
    and bar t's close for the tie rule."""
    n = len(c)
    for t in range(n):
        hb = hsb[t]
        lb = lsb[t]
        if hb < 0 or lb < 0:
            continue
        hp = hsp[t]
        lp = lsp[t]
        bottom = min(hp, lp)
        f_lo[t] = bottom
        f_hi[t] = max(hp, lp)
        nb, step = _n_bins(hp, lp, bin_size[t], max_bins)
        if nb < 1:
            continue
        f_nb[t] = nb
        vol = np.zeros(nb)
        buy = np.zeros(nb)
        sell = np.zeros(nb)
        _accumulate(o, c, v, bottom, step, nb, min(hb, lb), max(hb, lb), vol, buy, sell)
        level, ties, _ = _poc(vol, bottom, step, c[t])
        f_poc[t] = level
        f_ties[t] = ties
        st, delta = _sums(vol, buy, sell)
        f_total[t] = st
        f_delta[t] = delta


def leg_profile(o, c, v, hs_bar: int, hs_price: float, ls_bar: int, ls_price: float, bin_size: float,
                close: float) -> Dict[str, object]:
    """
    The profile of one leg (l.106-154), as the flip block and the forming block compute it: the swing pair (bar and
    price of the stored high and low), the bin size (``ta.atr(200) * 0.5`` of the bar that computes it) and that bar's
    close (for the tie rule). Returns ``lo``, ``hi``, ``n_bins`` (``binCount``, 0 when not computable), ``step``,
    ``vol`` / ``buy`` / ``sell`` (the bins, low to high), ``poc``, ``poc_bin``, ``poc_all`` (tuple of the tied
    levels, ascending), ``poc_ties``, ``delta_pct`` and ``total``; NaN / 0 / () where not computable, as in
    ``swing_profile``.
    """
    o, c, v = _series(o, "o"), _series(c, "c"), _series(v, "v")
    hs_bar, ls_bar = int(hs_bar), int(ls_bar)
    out: Dict[str, object] = {"lo": NAN, "hi": NAN, "n_bins": 0, "step": NAN, "vol": np.zeros(0), "buy": np.zeros(0),
                              "sell": np.zeros(0), "poc": NAN, "poc_bin": -1, "poc_all": (), "poc_ties": 0,
                              "delta_pct": NAN, "total": NAN}
    if hs_bar < 0 or ls_bar < 0:
        return out
    if max(hs_bar, ls_bar) >= len(c):
        raise ValueError("a swing bar is past the bars given")
    hp, lp = float(hs_price), float(ls_price)
    bottom = min(hp, lp)
    out["lo"], out["hi"] = bottom, max(hp, lp)
    bs = float(bin_size)
    nb, step = _n_bins(hp, lp, bs, float(PINE_ARRAY_MAX))
    if nb < 1:
        return out
    vol, buy, sell = np.zeros(nb), np.zeros(nb), np.zeros(nb)
    _accumulate(o, c, v, bottom, step, nb, min(hs_bar, ls_bar), max(hs_bar, ls_bar), vol, buy, sell)
    level, ties, k = _poc(vol, bottom, step, float(close))
    st, delta = _sums(vol, buy, sell)
    mx = vol.max()
    tied = []
    if mx > 0.0:
        for kk in np.flatnonzero(vol == mx).tolist():
            bin_low = bottom + (kk * step)
            tied.append((bin_low + (bin_low + step)) / 2.0)
    out.update({"n_bins": int(nb), "step": float(step), "vol": vol, "buy": buy, "sell": sell, "poc": float(level),
                "poc_bin": int(k), "poc_all": tuple(tied), "poc_ties": int(ties), "delta_pct": float(delta),
                "total": float(st)})
    return out


# ───────────────────────────── the indicator ─────────────────────────────

def _empty_legs() -> pd.DataFrame:
    return pd.DataFrame({"flip_bar": np.zeros(0, np.int64), "dir": np.zeros(0, np.int8),
                         "start_bar": np.zeros(0, np.int64), "end_bar": np.zeros(0, np.int64),
                         "lo": np.zeros(0), "hi": np.zeros(0), "poc": np.zeros(0),
                         "poc_all": pd.Series([], dtype=object), "delta_pct": np.zeros(0), "total": np.zeros(0),
                         "fifty": np.zeros(0), "atr_at_flip": np.zeros(0)})


def swing_profile(o, h, l, c, v, swing_len: int = 50, atr_len: int = 200,
                  bin_mult: float = 0.5) -> Dict[str, object]:
    """
    Swing Profile on one chart's bars (bid OHLC and volume, oldest first, no na; volume >= 0), with the script's
    defaults: a dict with the keys ``KEYS`` (the module docstring defines each one and gives its source lines).
    ``swing_len`` is ``swingLen`` (l.11), ``atr_len`` and ``bin_mult`` the constants of ``ta.atr(200) * 0.5`` (l.85).
    Inputs are copied, never modified.
    """
    o, h, l, c, v = _bars(o, h, l, c, v)
    L = _int(swing_len, "swing_len")
    A = _int(atr_len, "atr_len")
    mult = _positive(bin_mult, "bin_mult")
    n = len(c)
    sw = swings(h, l, L)
    atr = I.atr(h, l, c, A)                                           # l.85 ta.atr(200)
    bin_size = atr * mult                                             # l.85 * 0.5

    f_lo, f_hi, f_poc = np.full(n, NAN), np.full(n, NAN), np.full(n, NAN)
    f_delta, f_total = np.full(n, NAN), np.full(n, NAN)
    f_ties = np.zeros(n, np.int64)
    f_nb = np.zeros(n, np.int64)
    hsb, lsb = sw["hs_bar"], sw["ls_bar"]
    if n:
        _forming_kernel(o, c, v, hsb, sw["hs_price"], lsb, sw["ls_price"], bin_size, float(PINE_ARRAY_MAX),
                        f_lo, f_hi, f_poc, f_ties, f_delta, f_total, f_nb)
    both = (hsb >= 0) & (lsb >= 0)
    f_dir = np.where(both, np.sign(hsb - lsb), 0).astype(np.int8)

    fb = np.flatnonzero(sw["flip"])
    if len(fb):
        start = np.where(both[fb], np.minimum(hsb[fb], lsb[fb]), -1).astype(np.int64)
        end = np.where(both[fb], np.maximum(hsb[fb], lsb[fb]), -1).astype(np.int64)
        lo, hi = f_lo[fb], f_hi[fb]
        poc_all = []
        for t in fb.tolist():
            if f_nb[t] > 0:
                p = leg_profile(o, c, v, int(hsb[t]), float(sw["hs_price"][t]), int(lsb[t]), float(sw["ls_price"][t]),
                                float(bin_size[t]), float(c[t]))
                poc_all.append(p["poc_all"])
            else:
                poc_all.append(())
        legs = pd.DataFrame({
            "flip_bar": fb.astype(np.int64),
            "dir": np.where(sw["is_down_move"][fb], -1, 1).astype(np.int8),
            "start_bar": start, "end_bar": end, "lo": lo, "hi": hi, "poc": f_poc[fb],
            "poc_all": pd.Series(poc_all, dtype=object),
            "delta_pct": f_delta[fb], "total": f_total[fb], "fifty": (lo + hi) / 2.0, "atr_at_flip": atr[fb]})
    else:
        legs = _empty_legs()

    return {
        "is_down_move": sw["is_down_move"], "hs_bar": hsb, "hs_price": sw["hs_price"], "ls_bar": lsb,
        "ls_price": sw["ls_price"], "flip": sw["flip"],
        "f_dir": f_dir, "f_lo": f_lo, "f_hi": f_hi, "f_poc": f_poc, "f_poc_ties": f_ties, "f_delta_pct": f_delta,
        "f_total": f_total, "legs": legs,
    }
