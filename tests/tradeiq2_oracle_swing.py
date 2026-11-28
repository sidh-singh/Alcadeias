"""
The oracle of ``backtesting/research/tradeiq2_ind_swing.py``: PORT B of BigBeluga's "Swing Profile" (TradeIQ study 2,
``backtest_results/tradeiq_2027/PREREG.md`` section 6.4).

What this is
------------
A literal, bar-by-bar transcription of the script's Pine v6 logic in plain Python (no numpy in the bar loop, no numba),
written to be obviously correct rather than fast. It was written from the Pine source and the study's specification
(``maps/orb_session_swing_ha.md`` section 3) only, without seeing port A. Line numbers ``l.NN`` refer to the 424-line
plain-text copy "Swing Profile Indicator.txt" of the study's source folder (third-party code, CC BY-NC-SA 4.0: it is
cited, never copied). About 45 lines compute something (l.11, l.57-85, l.90-141, l.144-154, l.183-187, and the same
algorithm again for the forming leg, l.200-246 and l.307-351); the rest draws lines, boxes, polylines and labels.

Reconciled with port A on 28 Nov 2026 (``tests/test_tradeiq2_ind_swing.py``; the notes are
``backtest_results/tradeiq_2027/porting/swing.md``): bit for bit on every key of the 1H / 4H / 1D bars of both
symbols to 2024-06-30. Two changes here, neither of which moves a value of the real bars: ``f_dir`` and ``legs.dir``
are int8 (they were int64), and a bin-count quotient that overflows to infinity is not computable (``_bin_count``)
instead of raising OverflowError.

How the transcription works: Pine runs the script once per bar, oldest bar first. The three call sites that keep
state across bars (``ta.highest`` l.66, ``ta.lowest`` l.67, ``ta.atr`` l.85) are objects here (``Highest``,
``Lowest``, ``Atr``), each called once per bar exactly where the script calls it; all three are in the global scope,
so they see every bar (no conditional-execution issue). The ``var`` state (``isDownMove`` l.61, ``highSwing`` /
``lowSwing`` l.57-58) is kept in plain variables, updated in the script's statement order. The two profile blocks
(the finished leg l.105-141, the forming leg l.214-246 / l.319-351, which are the same arithmetic) are one function,
``leg_profile``, that follows the Pine loops statement by statement, in the same order of floating-point operations.

Pine value rules used throughout: ``na`` is NaN (a missing swing index is ``None`` inside, -1 in the output);
arithmetic with na gives na; a comparison with na is false (Python's NaN comparisons are false too, so ``high ==
highestSwingHigh`` is false while ``ta.highest`` is still na).

The contract (identical in both ports, compared key by key)
-----------------------------------------------------------
``swing_profile(o, h, l, c, v, swing_len=50, atr_len=200, bin_mult=0.5)`` returns a dict. The inputs are the chart's
bars, oldest first: the bid OHLC and the volume (gold: the tick volume; BTC: Binance BTCUSDT spot volume, PREREG 2).
``swing_len`` is the script's only input that changes a number (``swingLen``, l.11; TradingView's ``minval = 10`` is a
limit of its input dialog and is not enforced, so that the hand-made tests can use short windows); ``atr_len`` and
``bin_mult`` are the constants 200 and 0.5 of l.85. Per-bar keys (arrays of len(bars), bar 0 = the first bar given):

==============  =======  ===========================================================================================
key             dtype    value at bar t (after all of bar t's statements)
==============  =======  ===========================================================================================
is_down_move    bool     ``isDownMove`` (l.61, l.69-72): True after a bar whose high is the ``swing_len``-bar high,
                         False after one whose low is the ``swing_len``-bar low; the low wins on a bar that is both
hs_bar          int64    ``highSwing.index`` (l.57, l.75-77): the bar of the last CONFIRMED swing high; -1 if none
hs_price        float64  ``highSwing.price`` = high[hs_bar]; NaN if none
ls_bar          int64    ``lowSwing.index`` (l.58, l.80-82); -1 if none
ls_price        float64  ``lowSwing.price`` = low[ls_bar]; NaN if none
flip            bool     ``isDownMove != isDownMove[1]`` (l.90): a finished leg is computed on this bar
f_dir           int8     the FORMING leg's direction: +1 if hs_bar > ls_bar (an up leg: older low, newer high), -1 if
                         hs_bar < ls_bar, 0 if either swing is missing or both are on the same bar (reading R13).
                         int8 like every direction code of the study (int64 before the reconciliation)
f_lo, f_hi      float64  min / max of the two stored swing prices (``swingBottom`` / ``swingTop``, l.214-215); NaN
                         if either swing is missing. They do not depend on the ATR
f_poc           float64  the forming leg's POC (l.249-258 as on the chart's last bar): the level of the bin whose
                         volume equals the maximum, ``math.avg(binLow, binHigh)``; ties -> the tied bin nearest
                         this bar's close (PREREG 6.4), an exact distance tie -> the lower bin. NaN when not
                         computable: the ATR is na, a swing is missing, ``binCount == 0`` (R8), or the profile holds
                         no volume (R9)
f_poc_ties      int64    the number of bins tied at the maximum (>= 1 where f_poc exists, else 0)
f_delta_pct     float64  (buy - sell) / total of the forming leg's bins (l.288-291 without its ``* 100``: R5); buy =
                         the volume of bars with close > open, every other bar (a doji too) is sell (l.243-246).
                         NaN when not computable or when total == 0
f_total         float64  the sum of the forming leg's volume bins (``volumeBins.sum()``, l.288): every bar's volume
                         is counted once per bin it lands in (R6). NaN when not computable
==============  =======  ===========================================================================================

``legs``: a ``pandas.DataFrame`` of the FINISHED legs, one row per bar where ``flip`` is True, in bar order, with the
columns ``LEG_COLUMNS``: ``flip_bar`` (int64, as start_bar and end_bar); ``dir`` (int8; +1: the up leg, finished by a
flip to a new ``swing_len``-bar low, ``isDownMove`` turning false, drawn lime with "▲", l.99 / l.181; -1: the down
leg, finished by a flip to a new high);
``start_bar`` / ``end_bar`` (the older and the newer of the two stored swing bars, both included in the profile; -1
when a swing is missing); ``lo`` / ``hi`` (the swing prices' min / max); ``poc`` (ties -> the tied bin nearest the
flip bar's close); ``poc_all`` (a tuple of all tied bin levels, ascending; ``()`` when there is no POC); ``delta_pct``;
``total``; ``fifty`` = (lo + hi) / 2; ``atr_at_flip`` = ``ta.atr(atr_len)`` on the flip bar (the bin size is
``bin_mult`` times it). Rows whose profile is not computable keep their flip bar, dir, swing bars and prices, and have
NaN / ``()`` in the profile columns (and NaN in ``atr_at_flip`` while the ATR is na).

The profile (l.105-141, l.144-154, l.183-187), for a pair of stored swings and a bin size ``priceBinSize = ta.atr(200)
* 0.5`` taken on the bar where it is computed (the flip bar for a finished leg, the current bar for the forming one):
``binCount = int(|H - L| / priceBinSize)`` (truncated), ``binStep = |H - L| / binCount`` (so binStep >= the bin size
and the bins tile [lo, hi] exactly), bin k spans [lo + k * binStep, lo + k * binStep + binStep]; every bar from the
older swing to the newer swing, both included, adds its volume to every bin whose midpoint ``lo + (k * binStep) +
(binStep / 2)`` lies strictly within one binStep of its close: two bins (its own and the nearer neighbour), one when
the close is exactly on a midpoint, in the outer half of an edge bin or less than half a step outside the range, none
when it is half a step or more outside (the edge midpoint is half a step inside the edge). Between the two swings the
closes stay inside the range in practice: a lower low or higher high there would have been stored as a swing.

What is known when (no look-ahead)
----------------------------------
Every value at bar t is computed from bars 0 .. t only and never changes afterwards: ``ta.highest`` / ``ta.lowest`` /
``ta.atr`` read bars up to t; a swing point at bar t - 1 is stored on bar t, one bar after it prints (l.75-82 compare
bar t with bar t - 1), so the newer swing of any profile is at most bar t - 1; the profile reads the bars between the
two stored swings only. A finished leg's POC and delta are known at its flip bar's close (when the opposite extreme
prints, a median of about 25-30 bars after the leg's newer swing); the chart draws them back over the leg, which is
look-ahead if read before the flip bar. The forming leg is what the chart shows on its last bar (``barstate.islast``,
l.207 / l.313); here it is evaluated as if every bar were the last one, with the swings stored by then and that bar's
ATR, which is legitimate at that bar's close. On the realtime bar TradingView recomputes on every tick; closed bars,
all we use, are final. No ``request.security``, no ``varip``, no signals and no alerts. ``tests/
test_tradeiq2_ind_swing_b.py`` checks the causality by truncation.

The Pine readings (each one is a choice; the alternatives are named)
--------------------------------------------------------------------
R1. ``ta.highest(swingLen)`` / ``ta.lowest(swingLen)`` (l.66-67) are the ONE-argument forms, whose source is ``high``
    / ``low`` (not the close), the current bar included. Warm-up: na until the call has seen ``swing_len`` bars (bars 0
    .. swing_len - 2 are na, as ``ta.sma``; PineTS does the same). Alternative: the extreme of the bars available
    so far. Only the first ``swing_len - 1`` bars of the history differ, and the swing state is overwritten at the
    next extremes, so nothing after the warm-up can change.
R2. The order of l.69-72: ``if high == highestSwingHigh`` sets ``isDownMove`` true, THEN ``if low == lowestSwingLow``
    sets it false, so on a bar that is both the window's high and its low the LOW wins (isDownMove = false). The
    equalities are exact float comparisons; the window's extreme is one of its values, so a high equal to an earlier
    window high (a double top) also counts.
R3. The confirmation (l.75, l.80) is ``high[1] == highestSwingHigh[1] and high < highestSwingHigh``: bar t - 1 was
    its window's high and bar t's high is STRICTLY lower than bar t's window high, i.e. than high[t - 1]. A next high
    equal to it confirms nothing; the later of two equal highs is then the candidate and is stored when a strictly
    lower high follows. The stored index is ``bar_index[1]`` and the price ``high[1]``. Mirror for lows (strict
    ``>``). Each newer confirmation overwrites the stored point; nothing ever clears it.
R4. Statement order within a bar: l.69-72 (direction), l.75-82 (swings), l.85 (ATR), l.90 (flip). A swing confirmed
    ON the flip bar (bar t - 1 an extreme, bar t the opposite extreme with a strictly lower high / higher low) is
    stored before the finished leg is computed, so it is that leg's end. ``isDownMove[1]`` on bar 0 is false (Pine
    v6: the history of a bool before the first bar is false; with na the comparison would be false as well, and bar
    0 cannot set ``isDownMove`` true under R1 anyway).
R5. ``f_delta_pct`` / ``delta_pct`` are the FRACTION (buy - sell) / total, as the study's contract writes it; the
    script's tooltip multiplies it by 100 (l.187, l.291) for display. Same sign, so it cannot change the FD filter or
    claim 12; only the units differ (a port that keeps the ``* 100`` differs by that factor, not in logic).
R6. "Total", "buy" and "sell" are the script's bin sums (``volumeBins.sum()`` etc., l.184-187): a bar's volume is
    counted once per bin it lands in (usually twice, once at a midpoint or in an edge bin's outer half), not once per
    bar. Alternative: the leg's plain volume (each bar once), which weighs bars differently and can flip the sign of a
    small delta.
R7. Floating-point order, transcribed: the bars are visited from the NEWER swing back to the older one (the loop
    ``for i = barOffset to (lastSwingIndex - prevSwingIndex) + barOffset`` over ``close[i]``, l.125-129), bins
    k = 0 up (l.131); each bin's volume is accumulated in that bar order; ``array.sum`` adds the bins in index order
    with plain double additions (Pine's summation algorithm is not documented; sequential is the plain reading); the
    bin midpoint is ``(swingBottom + (k * binStep)) + (binStep / 2)`` (l.132). With integer volumes (gold's ticks)
    every sum is exact and the order is immaterial; with fractional volumes (BTC's Binance volume) it moves the last
    bits of ``total`` / ``delta``. A tie of two bins that hold the same bars is exact in any consistent order.
R8. Not computable (NaN profile, the run continues): the ATR is na (the first ``atr_len - 1`` bars), a swing is
    missing (the first legs), ``binCount == 0`` (|H - L| smaller than the bin size), or ``binCount`` above Pine's
    array limit of 100,000 elements (a quotient that overflows to infinity included: ``_bin_count``). On TradingView
    these are runtime errors that stop the whole script
    (``array.new<float>(na)``; ``for k = 0 to binCount - 1`` counts DOWN from 0 to -1 when binCount == 0 and
    ``volumeBins.get(0)`` on an empty array fails at l.149), so there is no Pine value to copy; the spec (3.3) and the
    contract skip them.
R9. A profile with no volume in any bin (every bar's volume 0, or no close within reach of a bin) has no POC: the
    ratio ``volumeBins.get(k) / volumeBins.max()`` is 0 / 0 = na, never 1, so no POC line is drawn (l.149-154);
    ``f_poc`` is NaN with 0 ties, ``f_total`` = 0.0 and the delta NaN.
R10. The POC level is the drawn line's price, ``math.avg(binLow, binHigh)`` with ``binLow = swingBottom + (k *
    binStep)``, ``binHigh = binLow + binStep`` (l.146-147, l.154), computed as ``(binLow + binHigh) / 2``.
    Alternative: the bin-assignment midpoint of l.132, ``binLow + binStep / 2``; the two can differ in the last bit.
R11. POC ties (several bins equal to the maximum; the script draws a line for each, l.153): the tied bin nearest the
    close of the bar where the profile is read (PREREG 6.4; the spec's "the first one a pullback reaches"), by
    ``|level - close|``; an exact distance tie goes to the LOWER bin (the first in k order). ``volumeRatio == 1``
    holds exactly when the bin equals the maximum (a correctly rounded x / max is 1 only for x == max).
R12. ``int()`` (l.110) truncates toward zero; the quotient is >= 0, so it is the floor (not a rounding).
R13. Equal swing bars (one bar that was both its window's high and low, confirmed both ways by the next bar): the
    forming leg has no direction, ``f_dir`` = 0; its profile is that single bar. A finished leg's ``dir`` comes from
    the flip (the script's colour and arrow, l.99 / l.181), never from the order of the swing bars, so a leg whose
    older swing is not the one the direction implies keeps the flip's dir, with start_bar / end_bar the older / newer
    swing bar. That needs a bar that is both extremes: e.g. a flip bar that is both, ending a run of window highs
    that was never confirmed, so the stored high is older than the stored low (BTC 1H, 2022-09-21 18:00 UTC).
R14. The history: TradingView runs this script on the last 2,000 bars only (``calc_bars_count = 2000``, l.6), so on a
    live chart the ATR(200) is seeded about 1,800 bars before the current bar. The port runs on the whole history
    given (from the data start, as study 1's ports), the only reading that is the same for every bar. The ATR then
    differs by about 1e-4 of the seed's error, which can move ``binCount`` by one where |H - L| / binSize is that
    close to an integer. ``max_bars_back = 5000`` (l.6) would be a runtime error for a leg reaching more than 5,000
    bars back; the port has no limit (real legs reach a few hundred bars back).
R15. ``ta.atr(200)`` is Pine's reference ``pine_atr`` / ``pine_rma``: true range ``high - low`` on bar 0, else
    ``math.max(math.max(high - low, |high - close[1]|), |low - close[1]|)``; seeded on bar ``atr_len - 1`` with
    ``ta.sma`` in ``pine_sma``'s order (sum of tr[i] / length, the newest first), then ``alpha * tr + (1 - alpha) *
    sum[1]`` with alpha = 1 / length: study 1's verified arithmetic, bit for bit (tested against
    ``tests/tradeiq_oracle.py``). ``external.wilder_atr`` updates in another order and differs in the last bits.
R16. Display only, not ported: the zigzag, the boxes, the polylines, the labels, the heat map, the colours, and the
    moving-average block (l.408-424). Its ``plot(ma(...))`` at l.424 does call ``ma()``, but with the default type
    "None" the ``switch`` has no matching arm and no default, so it returns na and nothing is plotted.

What the readings change on our bars
------------------------------------
Measured on 28 Nov 2026 with this file on study 1's 1H / 4H bars of both symbols from the data start (gold 2017-01,
BTC 2018-01) to 2024-06-30, gold with its tick volume and BTC with Binance's volume (indicator values and event counts
only; no rule was run; the alternatives were injected from scratch code without changing this file). "2019-2022" means
bars that open on or after 2019-01-01 and close by 2023-01-01; "2019-2024H1" runs to 2024-07-01.

* Events in 2019-2022 (finished legs up / down): gold 1H 159 / 159, 4H 44 / 44; BTC 1H 229 / 229, 4H 54 / 54. Every
  leg is computable (from 2019 on both swings and the ATR always exist; no binCount 0, no empty profile). POC ties in
  2.2% / 0% / 2.8% / 0.9% of the legs (gold 1H, 4H, BTC 1H, 4H), never more than two tied bins; a median of 19-20
  bins; the newer swing is a median of 25-28 bars before the flip (90th percentile 48-56); the flip bar's close is
  already past the finished leg's POC in 66-72% of the legs.
* R1: the partial-window warm-up changes the first 108-272 bars of each history only (to 2017-01-26 on gold,
  2018-02-15 on BTC), nothing from 2019.
* R10: l.132's midpoint differs from the drawn level in the last bit on about a quarter of the bars with a POC (gold
  1H 6,007 of 23,591 bars and 87 of 318 legs in 2019-2022), by at most 4.6e-13 (gold) / 1.5e-11 (BTC). No bar with
  the touch-and-hold shape (low <= POC < close, or high >= POC > close) changes on any of the four series in
  2019-2024H1. Bit-for-bit comparisons of ``f_poc`` / ``poc`` / ``poc_all`` need both ports to use the same formula.
* R11: no exact distance tie between two tied bins on any flip bar in 2019-2024H1.
* R6: the plain per-bar delta has the other sign than the script's bin-sum delta on 1 of 318 gold 1H legs (a down
  leg) and 1 of 108 BTC 4H legs (an up leg) in 2019-2022; none on gold 4H or BTC 1H.
* R7: gold's tick volumes are integers, so every order gives the same bits. BTC (Binance): the oldest-first order
  changes the last bits of ``f_total`` on 15,255 1H and 3,933 4H bars in 2019-2024H1 (numpy's pairwise sums: 21,069
  / 5,311), never the sign of a delta and never a POC.
* R13: two same-bar episodes on gold 1H (bars 2019-05-01 18:00 and 2022-09-21 18:00 UTC; 46 bars with f_dir 0 in
  2019-2022) and four on BTC 1H (115 bars; 29 more in 2023-2024H1), none on 4H. On those bars 2 / 6 (gold) and 34 /
  15 (BTC) bars have the touch-and-hold shape of a long / short, so a port that gave them a direction would add W1
  triggers there. BTC 1H also has two one-bar legs and one leg whose older swing is the high although its flip (a
  bar that is both extremes, 2022-09-21 18:00) makes it an up leg; one more of each in 2023-2024H1.
* R14: restarting the ATR 2,000 bars before each bar moves it by at most 1.6e-4 (relative) and changes binCount on
  4 (gold 1H), 4 (gold 4H), 13 (BTC 1H) and 6 (BTC 4H) bars in 2019-2024H1, never on a flip bar. The deepest look-back
  of any profile is 475 bars, far below ``max_bars_back`` (5,000).
* R15: ``external.wilder_atr`` differs from ``pine_rma`` in the last bits on about 95% of the bars (at most 5.3e-15
  relative) and never changes a binCount.
* BTC's volume (PREREG 2): with Exness tick volume instead of Binance's, 154 of 458 1H legs and 34 of 108 4H legs in
  2019-2022 would have another POC, and 35 / 6 another delta sign.
* Cross-check with the spec's probe (``study2/work/probe_swing_ha.py``, an independent transcription of the same
  legs), read only after this file and its tests were finished, run on the same bars 2019-2024H1 (1H / 4H / 1D, tick
  volume, and Binance's for BTC): the same flip bars, swing bars, directions and numbers of tied bins on every leg of
  every series; the same deltas bit for bit with tick volume (within 1e-12 with Binance's); the same single POCs
  within 1e-9 (the probe takes l.132's midpoint, R10), and the probe's POC (the lowest tied bin) is the lowest of
  this file's tied set. Its published counts (legs per year 77.2 / 21.3 / 2.6 on gold, 117.0 / 26.9 / 4.7 on BTC
  with tick volume) come out the same.

``tests/test_tradeiq2_ind_swing_b.py`` holds a hand-computed test of each trap of the spec (3.6), the readings' tests,
an independent vectorised formulation, truncation invariance and the real-bar smoke check.
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np
import pandas as pd

__all__ = ["swing_profile", "leg_profile", "Profile", "Highest", "Lowest", "Atr", "KEYS", "LEG_COLUMNS",
           "PINE_ARRAY_MAX"]

NAN = float("nan")
PINE_ARRAY_MAX = 100_000          # Pine's limit on the number of elements of an array (R8)

KEYS = ("is_down_move", "hs_bar", "hs_price", "ls_bar", "ls_price", "flip",
        "f_dir", "f_lo", "f_hi", "f_poc", "f_poc_ties", "f_delta_pct", "f_total")
LEG_COLUMNS = ("flip_bar", "dir", "start_bar", "end_bar", "lo", "hi", "poc", "poc_all", "delta_pct", "total", "fifty",
               "atr_at_flip")


def is_na(x) -> bool:
    return x != x


# ───────────────────────────── the call sites that keep state (Pine built-ins) ─────────────────────────────

class Highest:
    """``ta.highest(length)`` (l.66): the one-argument form, whose source is ``high``. Called once per bar with that
    bar's high; returns the largest of the last ``length`` highs, the current one included; na until ``length``
    highs have been seen (R1). The inputs are finite, so "na values are ignored" never applies."""

    def __init__(self, length: int):
        self.n = int(length)
        self.src: List[float] = []

    def __call__(self, x: float) -> float:
        self.src.append(x)
        if len(self.src) < self.n:
            return NAN
        m = self.src[-1]
        for i in range(1, self.n):              # high[0] .. high[length - 1]
            y = self.src[-1 - i]
            if y > m:
                m = y
        return m


class Lowest:
    """``ta.lowest(length)`` (l.67): the source is ``low``; the smallest of the last ``length`` lows; na until then."""

    def __init__(self, length: int):
        self.n = int(length)
        self.src: List[float] = []

    def __call__(self, x: float) -> float:
        self.src.append(x)
        if len(self.src) < self.n:
            return NAN
        m = self.src[-1]
        for i in range(1, self.n):
            y = self.src[-1 - i]
            if y < m:
                m = y
        return m


class Atr:
    """``ta.atr(length)`` (l.85) as TradingView's reference ``pine_atr`` / ``pine_rma`` (R15)::

        trueRange = na(high[1]) ? high - low : math.max(math.max(high - low, math.abs(high - close[1])),
                                                         math.abs(low - close[1]))
        sum := na(sum[1]) ? ta.sma(trueRange, length) : alpha * trueRange + (1 - alpha) * nz(sum[1])

    with alpha = 1 / length and ``ta.sma`` as ``pine_sma`` (``sum := sum + x[i] / length`` for i = 0 .. length - 1,
    the newest first): na on bars 0 .. length - 2, the plain mean of the first ``length`` true ranges on bar
    length - 1, then the recursion. Called once per bar with that bar's high, low and close."""

    def __init__(self, length: int):
        self.n = int(length)
        self.alpha = 1 / self.n
        self.tr: List[float] = []
        self.close1 = NAN                       # close[1]
        self.sum1 = NAN                         # sum[1]

    def __call__(self, high: float, low: float, close: float) -> float:
        if is_na(self.close1):                  # na(high[1]): the first bar
            tr = high - low
        else:
            a = high - low
            b = abs(high - self.close1)
            m = a if a >= b else b              # math.max (no na here)
            d = abs(low - self.close1)
            tr = m if m >= d else d
        self.close1 = close
        self.tr.append(tr)
        if is_na(self.sum1):
            if len(self.tr) < self.n:
                s = NAN
            else:
                s = 0.0
                for i in range(self.n):         # pine_sma: sum := sum + x[i] / y
                    s = s + self.tr[-1 - i] / self.n
        else:
            s = self.alpha * tr + (1 - self.alpha) * self.sum1
        self.sum1 = s
        return s


# ───────────────────────────── the profile of one leg (l.105-141, l.144-154, l.183-187) ─────────────────────────────

class Profile(NamedTuple):
    """One leg's volume profile; ``ok`` False when it is not computable (R8; then every other field but
    ``bin_count`` is empty / NaN). ``tied`` holds the POC levels of the bins equal to the maximum, ascending."""
    ok: bool
    bin_count: int
    bin_step: float
    bottom: float
    top: float
    prev_bar: int
    last_bar: int
    volume_bins: Tuple[float, ...]
    buy_bins: Tuple[float, ...]
    sell_bins: Tuple[float, ...]
    tied: Tuple[float, ...]
    total: float
    buy: float
    sell: float
    delta: float


def _array_sum(a) -> float:
    """``array.sum``: the elements added in index order with plain double additions (R7)."""
    s = 0.0
    for x in a:
        s = s + x
    return s


def _array_max(a) -> float:
    """``array.max`` of a non-empty array without na."""
    m = a[0]
    for x in a:
        if x > m:
            m = x
    return m


def _not_computable(bin_count: int = 0) -> Profile:
    return Profile(False, bin_count, NAN, NAN, NAN, -1, -1, (), (), (), (), NAN, NAN, NAN, NAN)


def _bin_count(span: float, price_bin_size: float) -> int:
    """l.110 ``int(math.abs(H - L) / priceBinSize)``, truncated (R12), for a bin size > 0. A quotient that overflows to
    infinity (a bin size near zero) has no integer value: it is returned as PINE_ARRAY_MAX + 1, i.e. above Pine's
    array limit, so it is not computable (R8) instead of raising OverflowError."""
    q = span / price_bin_size
    return int(q) if q != math.inf else PINE_ARRAY_MAX + 1


def leg_profile(o, c, v, t: int, hs_index: Optional[int], hs_price: float, ls_index: Optional[int], ls_price: float,
                price_bin_size: float) -> Profile:
    """
    The profile of the leg between the stored swing high (``hs_index``, ``hs_price``) and swing low as the script
    computes it on bar ``t`` with ``priceBinSize`` = ``price_bin_size`` (l.105-141 for a finished leg, l.214-246 for
    the forming one: the same statements). ``o``, ``c``, ``v`` are sequences of the bars' open, close and volume;
    only bars ``prev .. last`` (the two swing bars, both included) are read, so the result does not depend on ``t``
    (it only fixes the offsets ``i`` of ``close[i]``, which the loop reproduces). The POC levels (l.144-154) and the
    sums (l.183-187) come with it; the choice among tied POCs is ``nearest`` (it needs the reading bar's close).
    """
    if hs_index is None or ls_index is None:            # a swing missing: na arithmetic (R8)
        return _not_computable()
    if not (price_bin_size > 0):                        # the ATR is na (or zero): na / inf bin count (R8)
        return _not_computable()
    swing_bottom = min(hs_price, ls_price)              # l.106 math.min
    swing_top = max(hs_price, ls_price)                 # l.107 math.max
    bin_count = _bin_count(abs(hs_price - ls_price), price_bin_size)    # l.110 int() truncates (R12)
    if bin_count == 0 or bin_count > PINE_ARRAY_MAX:    # a runtime error on TradingView (R8)
        return _not_computable(bin_count)
    bin_step = abs(hs_price - ls_price) / bin_count     # l.111
    last_swing_index = max(hs_index, ls_index)          # l.113
    prev_swing_index = min(hs_index, ls_index)          # l.114
    volume_bins = [0.0] * bin_count                     # l.117 array.new<float>(binCount, 0.)
    buy_volume_bins = [0.0] * bin_count                 # l.119
    sell_volume_bins = [0.0] * bin_count                # l.120
    bar_offset = t - last_swing_index                   # l.122
    for i in range(bar_offset, (last_swing_index - prev_swing_index) + bar_offset + 1):   # l.125, both ends included
        candle_close = c[t - i]                         # l.127 close[i]
        candle_open = o[t - i]                          # l.128 open[i]
        candle_vol = v[t - i]                           # l.129 volume[i]
        for k in range(bin_count):                      # l.131 for k = 0 to binCount - 1
            bin_mid_price = swing_bottom + (k * bin_step) + (bin_step / 2)    # l.132
            if abs(bin_mid_price - candle_close) < bin_step:                  # l.134, strict
                volume_bins[k] = volume_bins[k] + candle_vol                  # l.136
                if candle_close > candle_open:                                # l.138
                    buy_volume_bins[k] = buy_volume_bins[k] + candle_vol      # l.139
                else:                                                         # a doji is sell
                    sell_volume_bins[k] = sell_volume_bins[k] + candle_vol    # l.141
    vmax = _array_max(volume_bins)
    tied = []
    for k in range(bin_count):                          # l.144
        bin_low = swing_bottom + (k * bin_step)         # l.146
        bin_high = bin_low + bin_step                   # l.147
        volume_ratio = volume_bins[k] / vmax if vmax != 0 else NAN    # l.149; 0 / 0 is na (R9)
        if volume_ratio == 1:                           # l.153, the POC line(s)
            tied.append((bin_low + bin_high) / 2)       # l.154 math.avg(binLow, binHigh) (R10)
    total = _array_sum(volume_bins)                     # l.184
    buy = _array_sum(buy_volume_bins)                   # l.185
    sell = _array_sum(sell_volume_bins)                 # l.186
    delta = (buy - sell) / total if total != 0 else NAN    # l.187 without its * 100 (R5)
    return Profile(True, bin_count, bin_step, swing_bottom, swing_top, prev_swing_index, last_swing_index,
                   tuple(volume_bins), tuple(buy_volume_bins), tuple(sell_volume_bins), tuple(tied), total, buy, sell,
                   delta)


def nearest(tied, close: float) -> float:
    """The tied POC level nearest ``close``; an exact distance tie goes to the lower level (R11); NaN if none."""
    best, best_d = NAN, math.inf
    for p in tied:                                      # ascending
        d = abs(p - close)
        if d < best_d:
            best, best_d = p, d
    return best


# ───────────────────────────── the script, bar by bar ─────────────────────────────

def _inputs(o, h, l, c, v):
    arrs = []
    for name, x in (("o", o), ("h", h), ("l", l), ("c", c), ("v", v)):
        a = np.asarray(x, dtype=np.float64)
        if a.ndim != 1:
            raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
        if not np.all(np.isfinite(a)):
            raise ValueError(f"{name}: every value must be finite (na bars are not ported)")
        arrs.append(a)
    if len({len(a) for a in arrs}) != 1:
        raise ValueError("o, h, l, c, v: equal lengths are expected")
    if np.any(arrs[4] < 0):
        raise ValueError("v: volumes must be >= 0")
    return arrs


def _length(x, name: str) -> int:
    if isinstance(x, (bool, np.bool_)) or float(x) != math.floor(float(x)) or float(x) < 1:
        raise ValueError(f"{name}: an integer >= 1 is expected, got {x!r}")
    return int(x)


def _run(o, h, l, c, v, swing_len: int = 50, atr_len: int = 200, bin_mult: float = 0.5, memo: bool = True):
    """The bar loop. ``memo``: the forming leg's profile is a pure function of the two stored swings, binCount and
    the bars between the swings, which never change, so the bars of one swing pair reuse the profile of each binCount
    they meet (an exact memo, emptied when a new swing is stored; only the choice among tied POCs, which reads the
    bar's own close, is made on every bar). ``memo=False`` recomputes the profile on every bar and gives identical
    results (tested)."""
    O, Hh, Ll, C, V = _inputs(o, h, l, c, v)
    swing_len = _length(swing_len, "swing_len")
    atr_len = _length(atr_len, "atr_len")
    bin_mult = float(bin_mult)
    if not (bin_mult > 0 and math.isfinite(bin_mult)):
        raise ValueError(f"bin_mult: a positive number is expected, got {bin_mult!r}")
    n = len(C)
    o_, h_, l_, c_, v_ = O.tolist(), Hh.tolist(), Ll.tolist(), C.tolist(), V.tolist()

    highest = Highest(swing_len)                        # l.66
    lowest = Lowest(swing_len)                          # l.67
    atr = Atr(atr_len)                                  # l.85
    highest_hist: List[float] = []                      # highestSwingHigh[k]
    lowest_hist: List[float] = []                       # lowestSwingLow[k]
    is_down_move = False                                # l.61 var isDownMove = false
    is_down_move_1 = False                              # isDownMove[1]: false before bar 0 (R4)
    high_swing_index: Optional[int] = None              # l.57 var highSwing = SwingData.new(na, na)
    high_swing_price = NAN
    low_swing_index: Optional[int] = None               # l.58
    low_swing_price = NAN

    out = {
        "is_down_move": np.zeros(n, dtype=bool), "hs_bar": np.full(n, -1, dtype=np.int64),
        "hs_price": np.full(n, NAN), "ls_bar": np.full(n, -1, dtype=np.int64), "ls_price": np.full(n, NAN),
        "flip": np.zeros(n, dtype=bool), "f_dir": np.zeros(n, dtype=np.int8), "f_lo": np.full(n, NAN),
        "f_hi": np.full(n, NAN), "f_poc": np.full(n, NAN), "f_poc_ties": np.zeros(n, dtype=np.int64),
        "f_delta_pct": np.full(n, NAN), "f_total": np.full(n, NAN),
    }
    rows = []
    cache: Dict[int, Profile] = {}                      # binCount -> profile, for the swing pair ``cache_pair``
    cache_pair = None

    for t in range(n):
        high, low, close = h_[t], l_[t], c_[t]
        highest_swing_high = highest(high)              # l.66
        lowest_swing_low = lowest(low)                  # l.67
        highest_hist.append(highest_swing_high)
        lowest_hist.append(lowest_swing_low)

        if high == highest_swing_high:                  # l.69 (false while na)
            is_down_move = True                         # l.70
        if low == lowest_swing_low:                     # l.71: tested second, so the low wins (R2)
            is_down_move = False                        # l.72

        # l.75: high[1] == highestSwingHigh[1] and high < highestSwingHigh (high[1] is na on bar 0)
        if t >= 1 and h_[t - 1] == highest_hist[t - 1] and high < highest_swing_high:
            high_swing_index = t - 1                    # l.76 bar_index[1]
            high_swing_price = h_[t - 1]                # l.77 high[1]
        # l.80: low[1] == lowestSwingLow[1] and low > lowestSwingLow
        if t >= 1 and l_[t - 1] == lowest_hist[t - 1] and low > lowest_swing_low:
            low_swing_index = t - 1                     # l.81
            low_swing_price = l_[t - 1]                 # l.82

        atr_t = atr(high, low, close)
        price_bin_size = atr_t * bin_mult               # l.85 ta.atr(200) * 0.5

        flip = is_down_move != is_down_move_1           # l.90

        # The profile of the current pair at this bar: the finished leg on a flip bar (l.105-187) and the forming leg
        # as on the chart's last bar (l.214-291 / l.319-393) are the same statements on the same pair and bin size.
        prof = None
        pair = (high_swing_index, high_swing_price, low_swing_index, low_swing_price)
        keyed = memo and high_swing_index is not None and low_swing_index is not None and price_bin_size > 0
        if keyed:
            if cache_pair != pair:                      # a new swing was stored: the old profiles never recur
                cache.clear()
                cache_pair = pair
            bc = _bin_count(abs(high_swing_price - low_swing_price), price_bin_size)    # l.110, as leg_profile
            prof = cache.get(bc)
        if prof is None:
            prof = leg_profile(o_, c_, v_, t, high_swing_index, high_swing_price, low_swing_index, low_swing_price,
                               price_bin_size)
            if keyed:
                cache[bc] = prof
        poc = nearest(prof.tied, close) if prof.ok else NAN

        both = high_swing_index is not None and low_swing_index is not None
        lo = min(high_swing_price, low_swing_price) if both else NAN
        hi = max(high_swing_price, low_swing_price) if both else NAN

        out["is_down_move"][t] = is_down_move
        out["hs_bar"][t] = -1 if high_swing_index is None else high_swing_index
        out["hs_price"][t] = high_swing_price
        out["ls_bar"][t] = -1 if low_swing_index is None else low_swing_index
        out["ls_price"][t] = low_swing_price
        out["flip"][t] = flip
        if both and high_swing_index != low_swing_index:
            out["f_dir"][t] = 1 if high_swing_index > low_swing_index else -1
        out["f_lo"][t] = lo
        out["f_hi"][t] = hi
        if prof.ok:
            out["f_poc"][t] = poc
            out["f_poc_ties"][t] = len(prof.tied)
            out["f_delta_pct"][t] = prof.delta
            out["f_total"][t] = prof.total

        if flip:                                        # l.90-194: the finished leg
            rows.append({
                "flip_bar": t,
                "dir": -1 if is_down_move else 1,       # isDownMove true: the DOWN leg is finished (l.99, l.181)
                "start_bar": min(high_swing_index, low_swing_index) if both else -1,
                "end_bar": max(high_swing_index, low_swing_index) if both else -1,
                "lo": lo, "hi": hi,
                "poc": poc,
                "poc_all": prof.tied,
                "delta_pct": prof.delta,
                "total": prof.total,
                "fifty": (lo + hi) / 2 if both else NAN,
                "atr_at_flip": atr_t,
            })
        is_down_move_1 = is_down_move

    out["legs"] = _legs_frame(rows)
    return out


def _legs_frame(rows) -> pd.DataFrame:
    cols = {k: [r[k] for r in rows] for k in LEG_COLUMNS}
    ints = ("flip_bar", "start_bar", "end_bar")
    data = {}
    for k in LEG_COLUMNS:
        if k in ints:
            data[k] = np.asarray(cols[k], dtype=np.int64)
        elif k == "dir":
            data[k] = np.asarray(cols[k], dtype=np.int8)
        elif k == "poc_all":
            a = np.empty(len(rows), dtype=object)
            for i, x in enumerate(cols[k]):
                a[i] = tuple(x)
            data[k] = a
        else:
            data[k] = np.asarray(cols[k], dtype=np.float64)
    return pd.DataFrame(data, columns=list(LEG_COLUMNS))


def swing_profile(o, h, l, c, v, swing_len: int = 50, atr_len: int = 200, bin_mult: float = 0.5) -> Dict[str, object]:
    """
    BigBeluga's Swing Profile on the bars given (oldest first): the per-bar arrays ``KEYS`` and the finished legs
    ``legs`` (a DataFrame with ``LEG_COLUMNS``), as the module docstring's contract describes. ``o``, ``h``, ``l``,
    ``c``: the bid OHLC; ``v``: the volume (>= 0); all finite and of equal length. ``swing_len``: ``swingLen``
    (l.11); ``atr_len`` / ``bin_mult``: the bin size ``ta.atr(atr_len) * bin_mult`` (l.85: 200 and 0.5).
    """
    return _run(o, h, l, c, v, swing_len, atr_len, bin_mult, memo=True)
