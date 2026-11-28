"""
Market Structure Dashboard (Flux Charts), port A: the dashboard's TREND BIAS, its row scores and the chart row's
breaks of structure, rebuilt for every chart bar from the bars (the script draws its table on the last bar only and
keeps no history, so the bias has to be recomputed).

    from backtesting.research import tradeiq_market as TM, tradeiq2_ind_msd as MSD
    mk = TM.load("XAUUSDm", end="2024-07-01")
    rows = MSD.rows_for(mk)                       # '1H', '4H', '1D' (study 1's bars) and '1W' (weekly_bars)
    out = MSD.structure_dashboard(rows, "4H")     # model A: each higher row from its last CLOSED bar
    out["label"]                                  # int8 per 4H bar: -2 BEARISH, -1 LEAN BEAR, 0, +1 LEAN BULL, +2 BULLISH

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 2, 5, 6.2, 6.10, 7, 8 claims 13-14); the
specification is the study's map of the script (``structure.md``). The script is "Market Structure Dashboard | Flux
Charts" (Pine v6, MPL-2.0, (c) fluxchart). Line numbers below are those of the owner's copy (1,749 lines); the source
itself is not in this repository. Port A (this module, the production port) and port B
(``tests/tradeiq2_oracle_msd.py``) were written independently from the source and the specification.

The contract (both ports)
-------------------------
``structure_dashboard(rows, chart_tf, model="A")`` -> dict of arrays, one value per chart bar (``rows[chart_tf]``):

* ``label`` int8: -2 BEARISH, -1 LEAN BEAR, 0 NEUTRAL, +1 LEAN BULL, +2 BULLISH.
* ``score`` int64 (the script's ``biasPoints``), ``max_score`` int64 (``maxScore``; constant: 44 on 1H, 36 on 4H, 28
  on 1D).
* per active row r ('1H', '4H', '1D', '1W' at or above the chart): ``s_<r>`` int64, the row's unweighted score
  struct + ob + fvg + swing in [-4, 4]; ``struct_<r>``, ``ob_<r>``, ``fvg_<r>``, ``swing_<r>`` int8 in {-1, 0, +1}.
* ``bos`` int8: +1 where the chart row has a bullish break of structure at this bar, -1 bearish, else 0;
  ``bos_trend`` int8: the side of the most recent break (0 before the first).

``rows`` maps '1H', '4H', '1D', '1W' to bar objects with numpy arrays ``t`` (open, UTC s), ``tc`` (close), ``o``,
``h``, ``l``, ``c`` (bid): ``tradeiq_market.TBars`` for 1H / 4H / 1D, ``weekly_bars`` for 1W. Rows below the chart are
ignored. ``mintick`` (``syminfo.mintick``) is taken from the chart bars' ``symbol`` (0.001 gold, 0.01 BTC: the store's
price digits) unless given.

What one row computes (``calcAll``, lines 684-690, run on that row's own bars)
------------------------------------------------------------------------------
``request.security(syminfo.tickerid, tf, calcAll())`` (lines 695-701) evaluates ``calcAll`` and every global series it
reads (``pivotHigh``, ``pivotLow``, ``_green``, ``_red``, ``bullFVG``, ``bearFVG``, lines 248-254) on the row's bars,
with one set of ``var`` state per call site and per row. Per row bar k, in Pine's order:

(a) Pivots, lines 249-250: ``ta.pivothigh(high, 5, 5)`` is ``high[k-5]`` when it is STRICTLY above the 5 highs before
    and the 5 highs after it (PREREG 6.2: strict on both sides; TradingView does not document ties), known at the close
    of bar k; na before bar 10. ``ta.pivotlow`` likewise with strictly lower lows.
(b) ``calcSwingHL`` (lines 333-366): on a new pivot ``prevH <- currH``, ``currH <- pivot`` (lows likewise); the row's
    ``swingH``/``swingL`` are ``currH``/``currL``. (The break / reclaim flags of lines 351-358 feed only the display and
    the alerts; they are returned by ``row_values`` for information.) ``calcStructure`` keeps its own ``SwingData``
    (line 370) but updates it from the same pivots in the same way, so its prev/curr pivots equal these.
(c) ``calcStructure`` (lines 369-425): on a new pivot high with a previous one, ``highType = currH > prevH ? 1 : -1``
    (an equal high is -1, "LH"); lows: ``currL > prevL ? 1 : -1``. Both start at 0. The real-time override (lines
    398-417) is applied on every bar and never stored: ``close < prevL`` makes the low type -1 and ``close > prevH``
    the high type +1, against the pivot BEFORE the latest one (``prevL``/``prevH``, not ``currL``/``currH``; ported as
    written). ``structBias`` = +1 if both are +1, -1 if both are -1, else 0.
(d) ``calcOrderBlock(obLookback = 6)`` (lines 568-586): ``trackPivotBreaks`` (lines 537-565) first stores a new pivot
    as ``lastPH`` with ``lastPHBar = k - 5`` (overwriting an unbroken one), THEN tests ``close > lastPH and close[1] <=
    lastPH`` (``isBreakAbove``, line 325); a break clears the pivot (each pivot breaks once). A bull break from pivot bar
    p searches ``low[i]``, i = 0 .. max(0, min(k - p - 1, 50)) (lines 483-490), for the lowest low with a strict ``<``
    from the current bar back (a tie keeps the most recent bar); the zone is that candle's high / low. Bear breaks
    mirror it with the highest high. A zone that overlaps a zone of the same side (``top >= ob.bottom and bottom <=
    ob.top``, touching counts, lines 501-507) is dropped; else it is unshifted (newest first) and the array is cut to 6
    by ``pop()``-ing the oldest (lines 475-477). Then, every bar, bull zones with ``close < bottom`` and bear zones with
    ``close > top`` are removed (by the CLOSE, lines 455-463), and ``findNearestZone`` gives the direction.
(e) ``calcFVG(fvgLookback = 6)`` (lines 611-623, pattern lines 251-254): on bars k-3, k-2, k-1 (found on bar k):
    ``bullFVG = low[1] > high[3] and _green[2] and low[1] < high[2] and low[2] < high[3]`` with ``_green = close > open
    or close > close[1]``, zone top ``low[1]``, bottom ``high[3]``; ``bearFVG`` mirrors it (top ``low[3]``, bottom
    ``high[1]``). A new gap is unshifted with no overlap test, the array is cut to 6 BEFORE the mitigation, and the
    mitigation is by the WICK (``low < bottom`` / ``high > top``, lines 465-473), on the detection bar too.
(f) ``findNearestZone`` (lines 426-453): both best distances start at the price 100000.0; a bull zone's distance is
    ``top - close``, a bear zone's ``bottom - close``; the smallest ``|d|`` per side wins with a strict ``<`` (the
    newest on a tie); +1 if ``|bull| < |bear| and |bull| < 100000``, else -1 if ``|bear| < 100000``, else 0 (a bull /
    bear tie is -1; a zone 100000 or more away from the close is invisible).
The order block and the FVG arrays hold both sides together; the caps of 6 are the inputs ``obLookback`` /
``fvgLookback`` of "Visual Overlays" (lines 165, 172), passed to the bias's arrays at lines 688-689.

The chart (lines 692, 703-737, 1323-1346)
-----------------------------------------
* Active rows: ``timeframe.in_seconds() <= timeframe.in_seconds(tf)`` (line 692): on 1H the rows 1H, 4H, D, W
  (weights 2, 2, 3, 4, lines 76-88); on 4H 4H, D, W; on 1D D, W. Lower rows count neither in the points nor in the
  maximum (lines 1336-1340). Factors: structure, order block, FVG and swing (EMA trend off, line 121): 4.
* The chart row ("60" on a 1H chart) is the chart's own bar. A higher row (model A, what TradingView shows on
  historical bars with the default ``lookahead_off``): the values of its last CLOSED bar, merged at the chart bar where
  ``tc_row <= tc_chart`` (exactly ``tradeiq_market.htf_at``); before its first closed bar a row is na: its factors
  score 0 (``dirScore``, line 703), but it counts in ``maxScore`` (line 1339).
* The swing factor (``swingBiasDir``, lines 705-708) is computed OUTSIDE ``request.security`` (line 1330): the CHART
  close against the row's swing high / low: ``range = math.max(swingH - swingL, syminfo.mintick)`` (one tick when the
  last pivot high is below the last pivot low), ``pct = (close - swingL) / range * 100``; ``pct < 0 ? -1 : pct > 100 ?
  1 : pct < 30 ? 1 : pct > 70 ? -1 : 0``; na swings give 0.
* ``biasPoints = sum(w * s_r)``, ``maxScore = 4 * sum(w)``; the label (line 1344) compares ``biasPct = biasPoints /
  maxScore * 100`` strictly with 50 / 20 / -50 / -20. Computed here in integers (BULLISH ``2p > m``, LEAN BULL ``5p >
  m``, BEARISH ``2p < -m``, LEAN BEAR ``5p < -m``), which gives the float formula's label for every reachable score
  (tested): 50% exactly (22/44, 18/36, 14/28) is LEAN, and 20% is not reachable (44, 36, 28 are not multiples of 5).
* ``bos`` / ``bos_trend``: ``trackPivotBreaks`` of the chart row (the same as the chart-level call of line 633).

Model B (optional; not part of the comparison): what the live dashboard shows at a chart close T. On realtime bars a
higher row is computed on its FORMING bar: the state committed at its last closed bar plus one tentative update
(Pine rolls ``var`` state back on every tick) with the forming bar so far: its open, the high and the low of the chart
bars inside it up to T, and the chart close at T (the chart bars tile the higher bar, so this is the M1 aggregate).
Here a chart bar inside a higher bar (``t_row <= t_chart`` and ``tc_chart <= tc_row``) always takes that tentative
update, also at the higher bar's last chart bar, where it reproduces the committed bar (the tests check B == A at every
higher-timeframe close). Chart bars outside every higher bar (only after the last day bar at a data end) take the
committed values. Model B reads only the chart bars up to T and the higher bars' spans [t, tc), never a forming bar's
own high, low or close.

What is known when (no look-ahead)
----------------------------------
Every value of chart bar j uses bars up to its close ``tc[j]`` only: the chart row's bar j, each higher row's last bar
with ``tc <= tc[j]`` (model A) and the chart close. Pivots arrive 5 row bars after the pivot bar (5 weeks on the
weekly row); an order block is known at the close of its break bar, an FVG one bar after its third candle. A row's
state depends on its whole path from the data start (the 6-slot arrays and old zones carry state): compare start dates
before scoring (``convergence``).

Readings where the source or the platform leaves a choice (PORTING notes)
-------------------------------------------------------------------------
* Pivot ties (lines 249-250): strict on both sides (the plan's reading). Alternatives (``>=`` on one side) add a few
  pivots on 1H / 4H (none on D / W per the map's probe).
* Day and week boundaries: UTC (the harness), not TradingView's 17:00 New York roll for gold. Weekly bars are the ISO
  (Monday-start) weeks of the merged 1D bars, grouped by the week of ``tc - 1 s``, closing at the last day bar's close
  (``weekly_bars``; the map's construction): gold's Sunday stub is part of Monday's day bar and so of the new week.
* The merge at ``tc_row <= tc_chart``: with a data hole at the end of a higher bar, its value arrives at the next chart
  bar after its close (TradingView might show it on the last chart bar inside it).
* ``syminfo.mintick``: the Exness feed's tick, 0.001 (gold) / 0.01 (BTC); it matters only for ranges under one tick.
* Everything else follows the source literally; nothing is tuned (all inputs are the script's defaults).

The ``ta.ema(close, 9)`` trend column (lines 248, 328-331; off in the bias) is given by ``row_values`` with study 1's
verified ``tradeiq_ind.ema``. The volume and volatility states, sessions, kill zones, PDH / PWH / PMH levels and the
alerts (lines 1111-1293, 1636-1749) do not enter the bias and are not ported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Mapping, Optional, Tuple

import numpy as np
from numba import njit

from . import tradeiq_ind as I

__all__ = [
    "CHART_TFS", "ROWS", "ACTIVE_ROWS", "WEIGHTS", "N_FACTORS", "MAX_SCORE", "LABELS", "MINTICK",
    "SWING_LENGTH", "OB_LOOKBACK", "FVG_LOOKBACK", "SEARCH_CAP", "SENTINEL", "EMA_LENGTH",
    "WBars", "weekly_bars", "rows_for", "row_values", "swing_factor", "label_of", "structure_dashboard",
    "convergence",
]

NAN = math.nan
DAY = 86400

SWING_LENGTH = 5            # line 126: "Swing Length" (pivots 5 left, 5 right)
OB_LOOKBACK = 6             # line 165 (the cap of the order-block array the bias reads, line 688)
FVG_LOOKBACK = 6            # line 172 (the cap of the FVG array, line 689)
SEARCH_CAP = 50             # lines 485, 494: ``math.min(barsBack, 50)``
SENTINEL = 100000.0         # lines 427-428, 446, 449: the starting "best distance", a price
EMA_LENGTH = 9              # line 125 (EMA trend column; not in the bias, line 121)

ROWS = ("1H", "4H", "1D", "1W")
CHART_TFS = ("1H", "4H", "1D")
ACTIVE_ROWS: Dict[str, Tuple[str, ...]] = {"1H": ("1H", "4H", "1D", "1W"), "4H": ("4H", "1D", "1W"), "1D": ("1D", "1W")}
WEIGHTS: Dict[str, int] = {"1H": 2, "4H": 2, "1D": 3, "1W": 4}       # tf4..tf7 weights, lines 76, 80, 84, 88
N_FACTORS = 4                                                         # biasFactorCount() with the defaults (118-122)
MAX_SCORE: Dict[str, int] = {tf: N_FACTORS * sum(WEIGHTS[r] for r in rows) for tf, rows in ACTIVE_ROWS.items()}
LABELS: Dict[int, str] = {2: "BULLISH", 1: "LEAN BULL", 0: "NEUTRAL", -1: "LEAN BEAR", -2: "BEARISH"}
MINTICK: Dict[str, float] = {"XAUUSDm": 0.001, "BTCUSDm": 0.01}      # 10 ** -digits of backtesting.config.SYMBOLS

# the row state (float64 slots; na = NaN)
_CH, _PH, _CL, _PL, _HT, _LT, _HB, _LB, _LPH, _LPHB, _LPL, _LPLB = range(12)
_NSTATE = 12


# ───────────────────────────── the row kernel (numba) ─────────────────────────────

@njit(cache=True)
def _unshift(z, nz, d, top, bottom, bar, cap):
    """``array.unshift(ZoneBlock.new(d, top, bottom, bar))`` then ``limitArraySize`` (lines 475-477): if the size
    exceeds ``cap``, ``pop()`` removes the last (the oldest) zone. ``z`` has cap + 1 rows."""
    for i in range(nz, 0, -1):
        for f in range(4):
            z[i, f] = z[i - 1, f]
    z[0, 0] = d
    z[0, 1] = top
    z[0, 2] = bottom
    z[0, 3] = bar
    nz += 1
    if nz > cap:
        nz -= 1
    return nz


@njit(cache=True)
def _remove(z, nz, i):
    """``array.remove(i)``."""
    for j in range(i, nz - 1):
        for f in range(4):
            z[j, f] = z[j + 1, f]
    return nz - 1


@njit(cache=True)
def _nearest(z, nz, close):
    """``findNearestZone`` (lines 426-453) on zones 0..nz-1 (newest first): -1 / 0 / +1."""
    bull = SENTINEL
    bear = SENTINEL
    for i in range(nz):
        if z[i, 0] == 1.0:
            d = z[i, 1] - close
            if abs(d) < abs(bull):
                bull = d
        else:
            d = z[i, 2] - close
            if abs(d) < abs(bear):
                bear = d
    if abs(bull) < abs(bear) and abs(bull) < SENTINEL:
        return 1
    if abs(bear) < SENTINEL:
        return -1
    return 0


@njit(cache=True)
def _detect_ob(d, pivot_bar, k, h, l, h0, l0, z, nz, cap):
    """``detectOB`` (lines 509-524) at bar k (whose high / low are h0 / l0; earlier bars from h / l): the extreme
    candle of bars k - max(0, min(k - pivot_bar - 1, 50)) .. k (``findLowestCandle`` / ``findHighestCandle``, lines
    483-499, strict comparison from the current bar back), rejected if it overlaps a zone of the same side (touching
    included, lines 501-507), else unshifted and capped. Returns (size, top, bottom); top / bottom NaN if rejected."""
    bars_back = k - pivot_bar - 1
    lim = max(0, min(bars_back, SEARCH_CAP))
    idx = k
    if d > 0:
        price = l0
        other = h0
        for i in range(1, lim + 1):                      # i = 0 is the current bar itself: low[0] < low is false
            li = l[k - i]
            if li < price:
                price = li
                other = h[k - i]
                idx = k - i
        top = other
        bottom = price
    else:
        price = h0
        other = l0
        for i in range(1, lim + 1):
            hi = h[k - i]
            if hi > price:
                price = hi
                other = l[k - i]
                idx = k - i
        top = price
        bottom = other
    for i in range(nz):
        if z[i, 0] == d and top >= z[i, 2] and bottom <= z[i, 1]:
            return nz, NAN, NAN
    nz = _unshift(z, nz, float(d), top, bottom, float(idx), cap)
    return nz, top, bottom


@njit(cache=True)
def _step(k, o, h, l, c, o0, h0, l0, c0, st, obz, fvz, cnt, sl, mob, mfv):
    """
    One execution of ``calcAll`` (minus the EMA) on row bar k, whose OHLC is (o0, h0, l0, c0); bars before k are read
    from o / h / l / c (never index k or later). Mutates the state (st, obz, fvz, cnt).
    """
    # (a) ta.pivothigh / ta.pivotlow (lines 249-250), strict on both sides; the 5th right bar is the current bar
    ph = NAN
    pl = NAN
    p = k - sl
    if p - sl >= 0:
        hp = h[p]
        lp = l[p]
        okh = True
        okl = True
        for i in range(1, sl + 1):
            if not hp > h[p - i]:
                okh = False
            if not lp < l[p - i]:
                okl = False
            q = p + i
            if q == k:
                hq = h0
                lq = l0
            else:
                hq = h[q]
                lq = l[q]
            if not hp > hq:
                okh = False
            if not lp < lq:
                okl = False
        if okh:
            ph = hp
        if okl:
            pl = lp
    new_h = ph == ph
    new_l = pl == pl

    # (b) calcSwingHL (lines 333-366); calcStructure's own SwingData (lines 380-396) takes the same values
    if new_h:
        st[_PH] = st[_CH]
        st[_CH] = ph
        st[_HB] = 0.0
    if new_l:
        st[_PL] = st[_CL]
        st[_CL] = pl
        st[_LB] = 0.0
    if l0 < st[_CL]:                                        # a comparison with na is false
        st[_LB] = 1.0
    if h0 > st[_CH]:
        st[_HB] = 1.0
    rec_low = st[_LB] == 1.0 and c0 > st[_CL]
    rec_high = st[_HB] == 1.0 and c0 < st[_CH]

    # (c) calcStructure (lines 369-425)
    if new_h and st[_PH] == st[_PH]:
        st[_HT] = 1.0 if st[_CH] > st[_PH] else -1.0        # an equal high is "LH"
    if new_l and st[_PL] == st[_PL]:
        st[_LT] = 1.0 if st[_CL] > st[_PL] else -1.0
    rt_low = st[_LT]
    rt_high = st[_HT]
    if st[_PL] == st[_PL] and c0 < st[_PL]:                 # the override against prevL / prevH (lines 406, 413)
        rt_low = -1.0
    if st[_PH] == st[_PH] and c0 > st[_PH]:
        rt_high = 1.0
    struct = 0
    if rt_high == 1.0 and rt_low == 1.0:
        struct = 1
    elif rt_high == -1.0 and rt_low == -1.0:
        struct = -1

    # (d) calcOrderBlock (lines 568-586): trackPivotBreaks (lines 537-565) sets the new pivot BEFORE the break test
    if new_h:
        st[_LPH] = ph
        st[_LPHB] = k - sl
    if new_l:
        st[_LPL] = pl
        st[_LPLB] = k - sl
    c1 = c[k - 1] if k >= 1 else NAN
    bull_bar = -1
    bear_bar = -1
    lph = st[_LPH]
    if lph == lph and c0 > lph and c1 <= lph and st[_LPHB] == st[_LPHB]:
        bull_bar = int(st[_LPHB])
        st[_LPH] = NAN
        st[_LPHB] = NAN
    lpl = st[_LPL]
    if lpl == lpl and c0 < lpl and c1 >= lpl and st[_LPLB] == st[_LPLB]:
        bear_bar = int(st[_LPLB])
        st[_LPL] = NAN
        st[_LPLB] = NAN
    nob = cnt[0]
    new_top = NAN
    new_bot = NAN
    if bull_bar >= 0:
        nob, new_top, new_bot = _detect_ob(1, bull_bar, k, h, l, h0, l0, obz, nob, mob)
    if bear_bar >= 0:
        nob, t2, b2 = _detect_ob(-1, bear_bar, k, h, l, h0, l0, obz, nob, mob)
        if t2 == t2:
            new_top = t2
            new_bot = b2
    i = nob - 1                                             # mitigateOBs (lines 455-463): by the close
    while i >= 0:
        if obz[i, 0] == 1.0 and c0 < obz[i, 2]:
            nob = _remove(obz, nob, i)
        elif obz[i, 0] == -1.0 and c0 > obz[i, 1]:
            nob = _remove(obz, nob, i)
        i -= 1
    ob_dir = _nearest(obz, nob, c0)
    cnt[0] = nob

    # (e) calcFVG (lines 611-623) with the pattern of lines 251-254 on bars k-3 .. k-1
    fdir = 0
    ftop = NAN
    fbot = NAN
    if k >= 3:
        g2 = c[k - 2] > o[k - 2] or c[k - 2] > c[k - 3]     # _green[2]
        r2 = c[k - 2] < o[k - 2] or c[k - 2] < c[k - 3]     # _red[2]
        if l[k - 1] > h[k - 3] and g2 and l[k - 1] < h[k - 2] and l[k - 2] < h[k - 3]:
            fdir = 1
            ftop = l[k - 1]
            fbot = h[k - 3]
        if h[k - 1] < l[k - 3] and r2 and h[k - 1] > l[k - 2] and h[k - 2] > l[k - 3]:
            fdir = -1
            ftop = l[k - 3]
            fbot = h[k - 1]
    nfv = cnt[1]
    if fdir != 0:
        nfv = _unshift(fvz, nfv, float(fdir), ftop, fbot, float(k - 3), mfv)   # capped BEFORE the mitigation
    i = nfv - 1                                             # mitigateFVGs (lines 465-473): by the wick
    while i >= 0:
        if fvz[i, 0] == 1.0 and l0 < fvz[i, 2]:
            nfv = _remove(fvz, nfv, i)
        elif fvz[i, 0] == -1.0 and h0 > fvz[i, 1]:
            nfv = _remove(fvz, nfv, i)
        i -= 1
    fvg_dir = _nearest(fvz, nfv, c0)
    cnt[1] = nfv

    bos = 1 if bull_bar >= 0 else (-1 if bear_bar >= 0 else 0)
    return (ph, pl, st[_CH], st[_CL], struct, ob_dir, fvg_dir, bos, new_top, new_bot, fdir, rec_low, rec_high,
            int(rt_high), int(rt_low), nob, nfv)


@njit(cache=True)
def _row_kernel(o, h, l, c, sl, mob, mfv, pk, po, phh, pll, pc):
    """
    ``calcAll`` over a row's bars 0..n-1 (committed), and the tentative "peeks" j: the step of bar ``pk[j]`` (0..n,
    non-decreasing) with OHLC (po[j], phh[j], pll[j], pc[j]) from the state committed after bar pk[j] - 1, nothing
    committed (model B's forming bar).
    """
    n = len(c)
    m = len(pk)
    a_ph = np.full(n, NAN)
    a_pl = np.full(n, NAN)
    a_sh = np.full(n, NAN)
    a_sl = np.full(n, NAN)
    a_st = np.zeros(n, np.int8)
    a_ob = np.zeros(n, np.int8)
    a_fv = np.zeros(n, np.int8)
    a_bos = np.zeros(n, np.int8)
    a_ntop = np.full(n, NAN)
    a_nbot = np.full(n, NAN)
    a_fnew = np.zeros(n, np.int8)
    a_rl = np.zeros(n, np.bool_)
    a_rh = np.zeros(n, np.bool_)
    a_ht = np.zeros(n, np.int8)
    a_lt = np.zeros(n, np.int8)
    a_nob = np.zeros(n, np.int8)
    a_nfv = np.zeros(n, np.int8)
    b_sh = np.full(m, NAN)
    b_sl = np.full(m, NAN)
    b_st = np.zeros(m, np.int8)
    b_ob = np.zeros(m, np.int8)
    b_fv = np.zeros(m, np.int8)
    st = np.full(_NSTATE, NAN)
    st[_HT] = 0.0
    st[_LT] = 0.0
    st[_HB] = 0.0
    st[_LB] = 0.0
    obz = np.zeros((mob + 1, 4))
    fvz = np.zeros((mfv + 1, 4))
    cnt = np.zeros(2, np.int64)
    j = 0
    for k in range(n + 1):
        while j < m and pk[j] == k:
            st2 = st.copy()
            ob2 = obz.copy()
            fv2 = fvz.copy()
            cn2 = cnt.copy()
            r = _step(k, o, h, l, c, po[j], phh[j], pll[j], pc[j], st2, ob2, fv2, cn2, sl, mob, mfv)
            b_sh[j] = r[2]
            b_sl[j] = r[3]
            b_st[j] = r[4]
            b_ob[j] = r[5]
            b_fv[j] = r[6]
            j += 1
        if k == n:
            break
        r = _step(k, o, h, l, c, o[k], h[k], l[k], c[k], st, obz, fvz, cnt, sl, mob, mfv)
        a_ph[k] = r[0]
        a_pl[k] = r[1]
        a_sh[k] = r[2]
        a_sl[k] = r[3]
        a_st[k] = r[4]
        a_ob[k] = r[5]
        a_fv[k] = r[6]
        a_bos[k] = r[7]
        a_ntop[k] = r[8]
        a_nbot[k] = r[9]
        a_fnew[k] = r[10]
        a_rl[k] = r[11]
        a_rh[k] = r[12]
        a_ht[k] = r[13]
        a_lt[k] = r[14]
        a_nob[k] = r[15]
        a_nfv[k] = r[16]
    return (a_ph, a_pl, a_sh, a_sl, a_st, a_ob, a_fv, a_bos, a_ntop, a_nbot, a_fnew, a_rl, a_rh, a_ht, a_lt, a_nob,
            a_nfv, b_sh, b_sl, b_st, b_ob, b_fv)


@njit(cache=True)
def _forming(ct, ctc, co, ch, cl, cc, rt, rtc):
    """
    Model B's forming higher bar of each chart bar j: the last row bar k with ``rt[k] <= ct[j]``, if the chart bar lies
    inside it (``ctc[j] <= rtc[k]``), with the OHLC of the chart bars inside it up to j (open of the first, running
    high and low, close of j). k = -1 when the chart bar is inside no row bar; -2 when it straddles a row bar's close.
    """
    n = len(ct)
    nr = len(rt)
    kf = np.full(n, -1, np.int64)
    fo = np.full(n, NAN)
    fh = np.full(n, NAN)
    fl = np.full(n, NAN)
    fc = np.full(n, NAN)
    kk = -1
    cur = -1
    hi = NAN
    lo = NAN
    op = NAN
    for j in range(n):
        while kk + 1 < nr and rt[kk + 1] <= ct[j]:
            kk += 1
        if kk < 0:
            continue
        if ctc[j] <= rtc[kk]:
            if kk != cur:
                cur = kk
                op = co[j]
                hi = ch[j]
                lo = cl[j]
            else:
                if ch[j] > hi:
                    hi = ch[j]
                if cl[j] < lo:
                    lo = cl[j]
            kf[j] = kk
            fo[j] = op
            fh[j] = hi
            fl[j] = lo
            fc[j] = cc[j]
        elif ct[j] < rtc[kk]:
            kf[j] = -2
    return kf, fo, fh, fl, fc


# ───────────────────────────── inputs ─────────────────────────────

def _arrays(bars, name: str) -> Tuple[np.ndarray, ...]:
    """(t, tc, o, h, l, c) of a bar object, checked: equal lengths, times increasing, tc > t, no NaN prices."""
    try:
        t = np.ascontiguousarray(bars.t, np.int64)
        tc = np.ascontiguousarray(bars.tc, np.int64)
        o, h, l, c = (np.ascontiguousarray(getattr(bars, f), np.float64) for f in ("o", "h", "l", "c"))
    except AttributeError as e:
        raise ValueError(f"{name}: a bar object with t, tc, o, h, l, c is expected ({e})") from None
    n = len(t)
    if not all(x.ndim == 1 and len(x) == n for x in (tc, o, h, l, c)):
        raise ValueError(f"{name}: t, tc, o, h, l, c must be 1-D arrays of one length")
    if n > 1 and not (np.all(np.diff(t) > 0) and np.all(np.diff(tc) > 0)):
        raise ValueError(f"{name}: bar times must increase")
    if n and not np.all(tc > t):
        raise ValueError(f"{name}: a bar closes at or before its open")
    if n and not (np.isfinite(o).all() and np.isfinite(h).all() and np.isfinite(l).all() and np.isfinite(c).all()):
        raise ValueError(f"{name}: na prices are not ported")
    return t, tc, o, h, l, c


def _run_row(bars, name: str, peeks=None):
    _, _, o, h, l, c = _arrays(bars, name)
    if peeks is None:
        pk = np.zeros(0, np.int64)
        po = ph = pl = pc = np.zeros(0)
    else:
        pk, po, ph, pl, pc = peeks
        if len(pk) > 1 and not np.all(np.diff(pk) >= 0):
            raise AssertionError("peeks must be sorted by bar")
    return _row_kernel(o, h, l, c, SWING_LENGTH, OB_LOOKBACK, FVG_LOOKBACK, np.ascontiguousarray(pk, np.int64),
                       np.ascontiguousarray(po, np.float64), np.ascontiguousarray(ph, np.float64),
                       np.ascontiguousarray(pl, np.float64), np.ascontiguousarray(pc, np.float64))


def _mintick(rows: Mapping[str, object], chart_tf: str, mintick: Optional[float]) -> float:
    if mintick is not None:
        v = float(mintick)
        if not (v > 0 and math.isfinite(v)):
            raise ValueError(f"mintick {mintick!r}")
        return v
    sym = getattr(rows[chart_tf], "symbol", None)
    if sym not in MINTICK:
        raise ValueError(f"no syminfo.mintick for the chart bars' symbol {sym!r}: pass mintick=")
    return MINTICK[sym]


# ───────────────────────────── weekly bars ─────────────────────────────

@dataclass(frozen=True, eq=False)
class WBars:
    """Weekly bars built from day bars (``weekly_bars``)."""
    symbol: Optional[str]
    tf: str
    t: np.ndarray            # open: the open of the week's first day bar (gold: Sunday 00:00 UTC, the stub's day)
    tc: np.ndarray           # close: the close of the week's last day bar (a forming last week: its ISO week end)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    vol: Optional[np.ndarray]
    d0: np.ndarray           # first and last day bar of the week
    d1: np.ndarray
    week_start: np.ndarray   # Monday 00:00 UTC of the ISO week
    complete: np.ndarray     # False only for a last week that could still receive day bars (see ``end_s``)

    def __len__(self) -> int:
        return int(len(self.t))


def weekly_bars(day_bars, end_s=None) -> WBars:
    """
    The dashboard's weekly row (PREREG 2): the ISO (Monday-start, UTC) weeks of the merged day bars
    (``tradeiq_market`` 1D bars: a UTC day with fewer than 360 M1 bars is merged into the next full day). A day bar
    belongs to the week of ``tc - 1 s`` (the map's construction): gold's Sunday stub, merged into Monday's day bar,
    starts the new week; BTC's weeks run Monday 00:00 to Monday 00:00. A week opens with its first day bar (t, o) and
    closes with its last (tc, c); the high and low are the extremes of its day bars.

    ``end_s`` (optional): the exclusive end of the data the day bars come from. If it is before the ISO end (the next
    Monday 00:00 UTC) of the last week, that week may still receive day bars: it is returned as forming, with
    ``complete`` False and ``tc`` set to that ISO end, so ``htf_at`` (model A) never reads it before it can be
    complete. (A cut inside gold's weekend is the one case where this is conservative: the day bars cannot show that
    no day of that week is still to come.) Without ``end_s`` every week is taken as complete, which is right for data
    that ends on a Monday 00:00 UTC (the study's 2024-07-01).
    """
    t = np.asarray(day_bars.t, np.int64)
    tc = np.asarray(day_bars.tc, np.int64)
    o, h, l, c = (np.asarray(getattr(day_bars, f), np.float64) for f in ("o", "h", "l", "c"))
    vol = getattr(day_bars, "vol", None)
    sym = getattr(day_bars, "symbol", None)
    if len(t) == 0:
        z, zi = np.zeros(0), np.zeros(0, np.int64)
        return WBars(sym, "1W", zi, zi, z, z, z, z, None if vol is None else z, zi, zi, zi, np.zeros(0, bool))
    if len(t) > 1 and not (np.all(np.diff(t) > 0) and np.all(np.diff(tc) > 0)):
        raise ValueError("day bar times must increase")
    day = (tc - 1) // DAY
    week = (day + 3) // 7                              # epoch day 0 (1970-01-01) is a Thursday: weeks from Monday
    first = np.flatnonzero(np.diff(week, prepend=week[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(week) - 1)
    wk = week[first]
    start = (wk * 7 - 3) * DAY                          # Monday 00:00 UTC
    wtc = tc[last].copy()
    complete = np.ones(len(first), bool)
    if end_s is not None:
        iso_end = int(start[-1]) + 7 * DAY
        if int(end_s) < iso_end:
            complete[-1] = False
            wtc[-1] = iso_end
    wvol = None if vol is None else np.add.reduceat(np.asarray(vol, np.float64), first)
    return WBars(sym, "1W", t[first].copy(), wtc, o[first].copy(), np.maximum.reduceat(h, first),
                 np.minimum.reduceat(l, first), c[last].copy(), wvol, first.astype(np.int64), last.astype(np.int64),
                 start.astype(np.int64), complete)


def rows_for(mk) -> Dict[str, object]:
    """The four rows of a ``tradeiq_market.TMarket``: its 1H, 4H, 1D bars and their weekly bars (``end_s`` = the
    market's end)."""
    d = mk.tbars("1D")
    return {"1H": mk.tbars("1H"), "4H": mk.tbars("4H"), "1D": d, "1W": weekly_bars(d, end_s=getattr(mk, "end_s", None))}


# ───────────────────────────── one row, the swing factor, the label ─────────────────────────────

def row_values(bars) -> Dict[str, np.ndarray]:
    """
    ``calcAll`` per bar of one row (its own bars; committed values, known at each bar's close):
    ``pivot_high`` / ``pivot_low`` (the pivot price reported on this bar, NaN if none), ``swing_h`` / ``swing_l``
    (currH / currL, NaN until the first pivot), ``struct`` (structBias), ``ob`` / ``fvg`` (the nearest zone's side),
    ``bos`` (+1 / -1 break of structure on this bar), ``ob_top`` / ``ob_bottom`` (the order block created on this bar,
    NaN if none or rejected as overlapping), ``fvg_new`` (the side of a gap found on this bar), ``high_type`` /
    ``low_type`` (the types after the override), ``reclaim_low`` / ``reclaim_high`` (display and alerts only),
    ``n_ob`` / ``n_fvg`` (zones held after the mitigation), ``trend`` (EMA trend column: close > ta.ema(close, 9) ?
    1 : -1, lines 328-331, with study 1's ``tradeiq_ind.ema``; not in the bias).
    """
    r = _run_row(bars, "bars")
    _, _, _, _, _, c = _arrays(bars, "bars")
    ema = I.ema(c, EMA_LENGTH)
    keys = ("pivot_high", "pivot_low", "swing_h", "swing_l", "struct", "ob", "fvg", "bos", "ob_top", "ob_bottom",
            "fvg_new", "reclaim_low", "reclaim_high", "high_type", "low_type", "n_ob", "n_fvg")
    out = dict(zip(keys, r[:17]))
    out["trend"] = np.where(c > ema, 1, -1).astype(np.int8)
    return out


def swing_factor(close, swing_h, swing_l, mintick: float) -> np.ndarray:
    """``swingBiasDir`` (lines 705-708), int8: ``range = math.max(swingH - swingL, mintick)`` (na if a swing is na),
    ``pct = (close - swingL) / range * 100``, then ``pct < 0 ? -1 : pct > 100 ? 1 : pct < 30 ? 1 : pct > 70 ? -1 :
    0`` (comparisons with na are false: 0)."""
    c = np.asarray(close, np.float64)
    sh = np.asarray(swing_h, np.float64)
    sl = np.asarray(swing_l, np.float64)
    with np.errstate(invalid="ignore"):
        rng = np.maximum(sh - sl, float(mintick))      # NaN propagates, as math.max with na
        pct = (c - sl) / rng * 100.0
        out = np.where(pct < 0, -1, np.where(pct > 100, 1, np.where(pct < 30, 1, np.where(pct > 70, -1, 0))))
    return out.astype(np.int8)


def label_of(points, max_score: int) -> np.ndarray:
    """The label of line 1344 in integers, int8: +2 BULLISH (2p > m), +1 LEAN BULL (5p > m), -2 BEARISH (2p < -m),
    -1 LEAN BEAR (5p < -m), 0 NEUTRAL. Equal to the float rule ``biasPct = p / m * 100`` against 50 / 20 / -50 / -20
    for every integer |p| <= m (tested)."""
    p = np.asarray(points, np.int64)
    m = int(max_score)
    if m <= 0:
        raise ValueError("maxScore must be positive (the script shows N/A)")
    lab = np.zeros(p.shape, np.int8)
    lab[5 * p > m] = 1
    lab[2 * p > m] = 2
    lab[5 * p < -m] = -1
    lab[2 * p < -m] = -2
    return lab


# ───────────────────────────── the dashboard ─────────────────────────────

def structure_dashboard(rows: Mapping[str, object], chart_tf: str, model: str = "A",
                        mintick: Optional[float] = None) -> Dict[str, np.ndarray]:
    """
    The bias of the dashboard on every bar of ``rows[chart_tf]`` (see the module docstring for the contract and the
    semantics). ``model``: "A" (closed higher bars, what TradingView shows on historical bars; the study's model) or
    "B" (the forming higher bar, what the live dashboard shows at each chart close; claim 14).
    """
    if chart_tf not in ACTIVE_ROWS:
        raise ValueError(f"chart_tf: one of {', '.join(CHART_TFS)}, got {chart_tf!r}")
    if model not in ("A", "B"):
        raise ValueError(f"model: 'A' or 'B', got {model!r}")
    names = ACTIVE_ROWS[chart_tf]
    missing = [r for r in names if r not in rows]
    if missing:
        raise ValueError(f"rows: {', '.join(missing)} missing for a {chart_tf} chart")
    ct, ctc, co, ch, cl, cc = _arrays(rows[chart_tf], chart_tf)
    n = len(ct)
    tick = _mintick(rows, chart_tf, mintick)
    out: Dict[str, np.ndarray] = {}
    points = np.zeros(n, np.int64)
    m = 0
    bos = None
    for r in names:
        bars = rows[r]
        rt, rtc, _, _, _, _ = _arrays(bars, r)
        w = WEIGHTS[r]
        m += w * N_FACTORS
        peeks = None
        if model == "B" and r != chart_tf:
            kf, fo, fh, fl, fc = _forming(ct, ctc, co, ch, cl, cc, rt, rtc)
            if np.any(kf == -2):
                j = int(np.flatnonzero(kf == -2)[0])
                raise ValueError(f"{chart_tf} bar {j} straddles the close of a {r} bar: the rows do not nest")
            inside = np.flatnonzero(kf >= 0)
            peeks = (kf[inside], fo[inside], fh[inside], fl[inside], fc[inside])
        res = _run_row(bars, r, peeks)
        a_sh, a_sl, a_st, a_ob, a_fv, a_bos = res[2], res[3], res[4], res[5], res[6], res[7]
        if r == chart_tf:
            if not np.array_equal(rtc, ctc):
                raise AssertionError("the chart row is the chart's own bars")
            bos = a_bos
        idx = np.searchsorted(rtc, ctc, side="right") - 1           # htf_at: the last row bar with tc <= the chart's tc
        ok = idx >= 0                                                # before it the row is na: 0, swings na
        struct = np.zeros(n, np.int8)
        ob = np.zeros(n, np.int8)
        fvg = np.zeros(n, np.int8)
        sh = np.full(n, NAN)
        sl = np.full(n, NAN)
        struct[ok], ob[ok], fvg[ok] = a_st[idx[ok]], a_ob[idx[ok]], a_fv[idx[ok]]
        sh[ok], sl[ok] = a_sh[idx[ok]], a_sl[idx[ok]]
        if peeks is not None and len(inside):
            struct[inside], ob[inside], fvg[inside] = res[19], res[20], res[21]
            sh[inside], sl[inside] = res[17], res[18]
        swing = swing_factor(cc, sh, sl, tick)
        s = struct.astype(np.int64) + ob + fvg + swing
        points += w * s
        out[f"s_{r}"] = s
        out[f"struct_{r}"] = struct
        out[f"ob_{r}"] = ob
        out[f"fvg_{r}"] = fvg
        out[f"swing_{r}"] = swing
    out["score"] = points
    out["max_score"] = np.full(n, m, np.int64)
    out["label"] = label_of(points, m)
    bos = np.asarray(bos, np.int8)
    last = np.maximum.accumulate(np.where(bos != 0, np.arange(n), -1)) if n else np.zeros(0, np.int64)
    out["bos"] = bos
    out["bos_trend"] = np.where(last >= 0, bos[np.maximum(last, 0)], 0).astype(np.int8)
    return out


def convergence(bars, skip_s: int) -> Dict[str, object]:
    """
    The plan's convergence check (map, section 3) for one row: the row computed from its first bar and from its first
    bar at or after ``t[0] + skip_s``; returns the open time of the first bar after which (struct, ob, fvg, swing_h,
    swing_l) agree on every bar (``first_agree``; None if the last bar disagrees) and how many bars disagree.
    """
    t, tc, o, h, l, c = _arrays(bars, "bars")
    a = int(np.searchsorted(t, int(t[0]) + int(skip_s), side="left"))
    if a >= len(t):
        raise ValueError("skip_s leaves no bar")
    late = SimpleNamespace(t=t[a:], tc=tc[a:], o=o[a:], h=h[a:], l=l[a:], c=c[a:])
    full, part = row_values(bars), row_values(late)
    diff = np.zeros(len(t) - a, bool)
    for k in ("struct", "ob", "fvg"):
        diff |= full[k][a:] != part[k]
    for k in ("swing_h", "swing_l"):
        x, y = full[k][a:], part[k]
        diff |= ~((x == y) | (np.isnan(x) & np.isnan(y)))
    bad = np.flatnonzero(diff)
    if len(bad) == 0:
        first = int(t[a])
    elif bad[-1] + 1 < len(diff):
        first = int(t[a + bad[-1] + 1])
    else:
        first = None
    return {"start": int(t[0]), "late_start": int(t[a]), "first_agree": first, "n_disagree": int(len(bad))}
