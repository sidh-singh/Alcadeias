"""
PORT B (the oracle) of "Harmonic & Chart Patterns [AI-AlgoCode]" (TradingView, Pine v6), for study 2 of the TradeIQ
research (``backtest_results/tradeiq_2027/PREREG.md`` 6.7; the specification is the study's ``maps/ribbon_patterns.md``
part B).

Port A is ``backtesting/research/tradeiq2_ind_patterns.py``. This file was written independently of it, from the Pine
source and the specification only. It is the reference that port A is checked against, so it is written to be
obviously correct rather than fast:
- one plain-Python loop over the bars;
- the script's three ``var`` arrays kept exactly as Pine keeps them (``unshift`` / ``set`` / ``pop``);
- ``ta.highestbars`` / ``ta.lowestbars`` re-derived from the bar history on every bar;
- the 38 predicates transcribed statement by statement (``P.get(k)`` -> ``P[k]``), keeping the script's own names.

``Lnnn`` refers to a line of the study's copy of the source (``Harmonic and Chart Patterns Script.txt``, 830 lines).
The Pine source is third-party code and is not reproduced here. Only identifiers, line numbers and the generated table
of its constants appear (see "Generated tables").

What is computed
----------------
``patterns(h, l, c, depth=5)`` runs the script on the chart timeframe from the first bar given (bar index 0). Every
input is at its default (L19-92): depth 5, devPct 0, all 38 patterns enabled, and the plan multipliers of L35-41.
``h, l, c`` are the bid high, low and close. The script reads nothing else: no open, volume, time or session. The
result is a dict:

=============  ==============================================================================================
key            value
=============  ==============================================================================================
swings         DataFrame, one row per zigzag swing, oldest first, as it stands after the last bar. Columns:
               ``bar`` (int), ``price`` (pivP), ``close_at_set`` (pivC: the close of the bar that last set the
               swing), ``is_high`` (bool; the swings alternate). The last row is the live swing.
               The script itself keeps only the newest 60 swings (L569-572). This list is NOT capped, because
               nothing the script computes reads past the 12th-newest swing: makeQ reads indexes <= 11 (L578-579)
               and newPat reads indexes <= 9 (L609-612). Each swing keeps its final state.
n_swings       int64 per bar: the number of swings after that bar's update. Uncapped, consistent with
               ``swings``; the script's ``pivP.size()`` is min(n_swings, 60). Both gates (>= 12, >= 11) read the
               same either way.
added          bool per bar: a swing was unshifted on that bar (the script's ``added``, L540, L555, L568).
confirmed      DataFrame, one row per hit of each CONFIRMED detection (L780-795): on a bar with ``added`` and at
               least 12 swings, ``detect(makeQ(1), pivC.get(1))``. D = the swing that has just been fixed.
forming        DataFrame, one row per (bar, hit) of the FORMING detection (L802-813), ``detect(makeQ(0), close)``
               with at least 11 swings, evaluated at EVERY bar close on the zigzag state after that bar (PREREG
               6.7). D = the live swing.
=============  ==============================================================================================

Columns of ``confirmed`` and ``forming``, sorted by (t_bar, id):

=====================  ======================================================================================
t_bar                  the bar at whose close the row is known (confirmed: the bar where the NEXT swing appears)
id, name               the pattern id 0-37 and its NAMES entry (L96-103)
kind                   'harmonic' for id <= 21, else 'chart' (the script's split, L617 / L628 / L702)
dir                    dirOf(id) (L117-125): +1 bullish, -1 bearish
first_hit              True for the first hit in registry order: the one the script draws, alerts and names
                       (``hits.get(0)``, L783 / L810)
n_hits                 the number of hits of the detection (the script's ``extra`` is n_hits - 1)
n_pts                  ptsOf(id) (L128-142): the number of swings the pattern uses
xs, ys                 tuples: the pattern's swing bar indexes and prices, oldest first, the last = D (Pat.xs /
                       Pat.ys as newPat fills them, L606-613)
d_bar, d_price         xs[-1], ys[-1]: point D (fixed for confirmed rows, live for forming rows)
c0                     the close that the chart predicates read: pivC[1] for confirmed (L781), close for forming
                       (L808)
entry, sl, tp1, tp2    planLevels(id, makeQ(s)) (L694-718), s = 1 confirmed, s = 0 forming:
                       harmonic: AD = |Q3 - Q0|, entry = D, sl = D - dir*0.13*AD, tp1 = D + dir*0.382*AD,
                       tp2 = D + dir*0.618*AD;
                       chart: h = |Q1 - Q2|, entry = p2, sl = p2 - dir*0.5*h, tp1 = p2 + dir*h,
                       tp2 = p2 + dir*1.618*h.
                       NaN where the script gives na: AD == 0 (harmonic) or h == 0 (chart)
instance_key           (forming only) (id, pivB[1], ..., pivB[n_pts - 1]): the id and the bar indexes of the
                       pattern's FIXED swings, newest first, excluding the live D (pivB[0])
first_bar_of_instance  (forming only) True on the first bar where that instance_key is detected
=====================  ======================================================================================

What is known when (no look-ahead)
----------------------------------
Every output at bar i is a function of bars 0..i only. The loop sees one bar at a time, and the only history it reads
is the last ``depth`` highs and lows (ta.highestbars / ta.lowestbars) and its own arrays.
- A confirmed row is known at the close of ``t_bar``. Its swing points lie in the past: D is a median of 3 bars back
  (spec B2). The script draws the pattern back at D, so the drawn bar must never be used for timing.
- A forming row is what a live user sees at the close of ``t_bar``: the forming pattern of L802-813 recomputed on that
  bar's state. Its D is live and can move or vanish on later bars. Those later bars never change the row.
- ``swings`` is the state after the last bar. Its last swing is live; all the others are fixed.
- The display code is not ported: the drawing, L584-692, except newPat's point lists (L606-613, ported as xs / ys);
  the overlap gate L767-777 / L785; histMax; and the plan drawing L720-759 / L814-820. The overlap gate only decides whether a confirmed pattern is drawn; ``bullConf`` /
  ``bearConf`` and the alert (L793-795, L824-827) fire for every detection with a hit, so ``confirmed`` holds every
  one. ``drawn_mask`` re-derives the gate (display only) for the test that shows it gates no alert.

The Pine readings chosen (where the semantics are not spelled out)
-------------------------------------------------------------------
The measurements below are counts only, on our bars closing in 2019-2022 (tradeiq_market 1H / 4H / 1D, loaded with
end="2024-07-01"). There is no profit or loss.

R1  ``ta.highestbars(high, depth) == 0`` (L541) / ``ta.lowestbars`` (L542): the offset of the extreme of the last
    ``depth`` values, current bar included. Ties go to the NEWEST bar, so the current bar is "the highest" when it
    equals an earlier high of the window (PineTS, quoted by the spec, line 23). TradingView does not document ties.
    The private option ``_ties="oldest"`` exists only to measure the alternative. The oldest-bar reading adds one
    confirmed detection to the 950 on gold 1H, and 5 of the 2,025 forming first bars differ (symmetric difference).
    It moves 2 gold 4H swings without changing any event, and changes nothing else on gold or BTC.
R2  ``ta.highestbars`` is na before ``depth`` bars exist (PineTS: a value from bar_index length-1 on), and
    ``na == 0`` is false. So no swing can start before bar depth-1. This and the chart's start in general change
    only the first bars. Started 300 or 1,000 bars later, the zigzag rejoins the full run within 4-12 bars, and the
    events agree from the late run's first event on (45-169 bars after its start). Our bars start in 2016 (gold,
    the study's loader; 2017 in study 1's) and 2018 (BTC), so neither can change a 2019+ event.
R3  The forming detection runs at every bar close, on the state after that bar (PREREG 6.7). The script itself
    computes it only ``if barstate.islast`` (L802), i.e. on the last bar and on every real-time tick. A forming
    pattern that shows and vanishes inside one bar is not seen; that cannot be measured with bars.
R4  A forming instance is (id, the bar indexes of its fixed swings). Its first bar is the first bar on which it is
    detected. If it vanishes and comes back (a chart pattern whose close moves back over p2, or a live D that moves
    out of a window and then back in), the return is the same instance, not a new first bar. Returns are rare. On
    gold 1H, 30 of 2,025 instances come back (37 returns), and on BTC 1H 40 of 2,799 (53 returns). On 4H it is
    gold 12 (13), BTC 13 (14); on 1D gold 0, BTC 2 (2).
R5  Arithmetic is IEEE double, with Pine's left-to-right order kept in every expression. For example
    ``dir * slK * ad`` = ``(dir * slK) * ad`` (L706); since dir is +-1 the other grouping gives the same bits. Pine
    v6 ``and`` is lazy, but no predicate has a side effect, so evaluation order cannot matter.
R6  Inputs must be finite. Our bars have no na, and Pine's handling of an na high or low inside the series is not
    ported.
R7  ``first_bar_of_instance`` is per hit: an instance's first bar is its first row as ANY hit, first in registry
    order or not. The script draws only the first hit (L810), and the specification's instance counts (B2: gold 1H
    321 a year) are of first-hit rows, by the first bar on which the instance is the first hit. Both come from the
    same columns (``instance_key``, ``first_hit``). They differ a lot for harmonics: gold 1H has 1,865 harmonic
    instances over all hits and 1,144 as first hits. The study decides which one its rules use (PREREG 6.7 says
    "the first bar of each forming instance").

Facts of the script that the port keeps (they are not readings):
- The Bear Gartley (id 4) can never fire. Its XD window starts at 1.618, but XB <= 0.618, AC >= 0.382 and
  BD <= 3.618 give XD = XB (AC + BD (1 - AC)) < 0.618 * (0.382 + 3.618 * 0.618) = 0.618 * 2.617924 = 1.61788.
- The Bull ALT AB=CD (19) has the same windows as the Bull AB=CD (18), so it always hits together with 18 and is
  never the first hit.
- No plan level is na on our bars: AD and h were never 0.

None of these touches the spec's porting traps (spec B6 "Risks"), which are kept literally:
- the orientation of ``inR`` and the predicates 28-33, whose alternation is not pinned;
- strict inequalities;
- the first-hit order;
- the gates >= 12 for confirmed and >= 11 for forming;
- c0 = pivC[1] for confirmed and close for forming;
- highs before lows in the zigzag, with the ``pivB[0] != bar_index`` guard on lows only (L562);
- makeQ's index clamp (L579). Under the two gates it never binds;
- the plan's Q3 for the 5-0 (the label "B" of its XABCDE drawing, L658);
- an overlap gate that gates no alert.

Generated tables
----------------
NAMES (L96-103), the 144 ratio constants (L146-289) and the argument lists of the 22 harmonic cases of ``check``
(L484-505) are not typed by hand. ``generate_tables`` parses them from the Pine text. It reads the study's .txt copy,
or the owner's .rtf original, whose lines carry a trailing backslash. ``generated_block`` prints them as the Python
block between the GENERATED markers below:

    python3 -B tests/tradeiq2_oracle_patterns.py generate "<path to the Pine source>"

``tests/test_tradeiq2_ind_patterns_b.py`` regenerates the block from the source when the file is on the machine, and
skips that check when it is absent. The bullish windows are not the mirror of the bearish ones; for example, Bat XD
is 0.3-1.8 bearish and 0.5-2.5 bullish.

Reconciliation with port A (28 Nov 2026)
----------------------------------------
``tests/test_tradeiq2_ind_patterns.py`` runs both ports on the study's 1H / 4H / 1D bars of both symbols (gold from
2016-01-03 and from 2017-01-03, BTC from 2018-01-01, to 2024-06-30) and on synthetic bars with ties, outside bars and
depths 2-50. The swings, ``n_swings``, ``added``, every column of ``confirmed`` and ``forming`` (``xs`` / ``ys`` read as
port A's newest-first points), ``drawn_mask`` and the chart predicates without their breakout conjunct are equal bit
for bit, and so is the zigzag state ``Script`` holds after each bar. No mismatch was found; only this docstring was
corrected (the source's line count, the bars' start, and the arithmetic of the Bear Gartley bound). Notes:
``backtest_results/tradeiq_2027/porting/patterns.md``.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "patterns", "drawn_mask", "Script",
    "inR", "pcBat", "pcShark", "pcABCD", "pc50", "pc3Drives",
    "pcDoubleTop", "pcDoubleBottom", "pcHeadShoulders", "pcInvHeadShoulders", "pcTripleTop", "pcTripleBottom",
    "pcBearRisingWedge", "pcBullRisingWedge", "pcBearExpTriangle", "pcBullExpTriangle",
    "pcBullPennant", "pcBearPennant", "pcBullFallingWedgeT", "pcBearRisingWedgeT", "pcBullFlag", "pcBearFlag",
    "check", "detect", "dirOf", "ptsOf", "kindOf", "planLevels", "ta_highestbars", "ta_lowestbars",
    "generate_tables", "generated_block", "source_lines", "read_source",
    "NAMES", "RATIOS", "HARMONIC_CALLS", "EN", "SWING_COLUMNS", "ROW_COLUMNS", "FORMING_COLUMNS",
]

# ───────────────────────────── inputs (their defaults) ─────────────────────────────

DEPTH = 5                                   # L19 depth
DEV_PCT = 0.0                               # L21 devPct: abs(x) >= 0 always holds, so no filter
SHOW_FORMING = True                         # L25 showForming (gates the forming detection, L807)
HIST_MAX = 15                               # L26 histMax (display: the drawn history; drawn_mask only)
SL_K, TP1_K, TP2_K = 0.13, 0.382, 0.618     # L35-37 slK, tp1K, tp2K
PLAN_BARS = 30                              # L38 planBars (display; PREREG 6.7 takes it as the time stop)
CSL_K, CTP1_K, CTP2_K = 0.5, 1.0, 1.618     # L39-41 cslK, ctp1K, ctp2K
MAX_SWINGS = 60                             # L569: the arrays keep at most 60 swings
N_IDS = 38                                  # L527: for id = 0 to 37

# ───────────────────────────── generated tables ─────────────────────────────

# BEGIN GENERATED
# Written by generate_tables() from the Pine source; do not edit by hand. Regenerate with
#     python3 -B tests/tradeiq2_oracle_patterns.py generate "<Harmonic and Chart Patterns Script.txt>"
# NAMES: source lines 96-103; RATIOS: the 144 constants of lines 146-289;
# HARMONIC_CALLS: the harmonic cases of check(), lines 484-505 (id: (function, bear, its constants)).
NAMES = (
    "Bear Bat", "Bear ALT Bat", "Bear Butterfly", "Bear Crab", "Bear Gartley", "Bear Deep Crab",
    "Bear Shark", "Bear AB=CD", "Bear ALT AB=CD", "Bear 5-0", "Bear Three Drives", "Bull Bat",
    "Bull ALT Bat", "Bull Butterfly", "Bull Crab", "Bull Gartley", "Bull Deep Crab", "Bull Shark",
    "Bull AB=CD", "Bull ALT AB=CD", "Bull 5-0", "Bull Three Drives", "Double Top", "Double Bottom",
    "Head & Shoulders", "Inv. Head & Shoulders", "Triple Top", "Triple Bottom", "Rising Wedge", "Bull Rising Wedge",
    "Bear Expanding Triangle", "Bull Expanding Triangle", "Bull Pennant", "Bear Pennant", "Bull Falling Wedge", "Bear Rising Wedge",
    "Bull Flag", "Bear Flag",
)
RATIOS = {
    "Bearish_Bat_XB_min": 0.382,
    "Bearish_Bat_XB_max": 0.70,
    "Bearish_Bat_AC_min": 0.382,
    "Bearish_Bat_AC_max": 1.886,
    "Bearish_Bat_BD_min": 0.618,
    "Bearish_Bat_BD_max": 2.618,
    "Bearish_Bat_XD_min": 0.3,
    "Bearish_Bat_XD_max": 1.8,
    "Bullish_Bat_XB_min": 0.282,
    "Bullish_Bat_XB_max": 0.70,
    "Bullish_Bat_AC_min": 0.282,
    "Bullish_Bat_AC_max": 1.886,
    "Bullish_Bat_BD_min": 0.618,
    "Bullish_Bat_BD_max": 2.618,
    "Bullish_Bat_XD_min": 0.5,
    "Bullish_Bat_XD_max": 2.5,
    "Bearish_ALT_Bat_XB_min": 0.182,
    "Bearish_ALT_Bat_XB_max": 0.50,
    "Bearish_ALT_Bat_AC_min": 0.282,
    "Bearish_ALT_Bat_AC_max": 0.986,
    "Bearish_ALT_Bat_BD_min": 1.0,
    "Bearish_ALT_Bat_BD_max": 3.168,
    "Bearish_ALT_Bat_XD_min": 1.0,
    "Bearish_ALT_Bat_XD_max": 3.0,
    "Bullish_ALT_Bat_XB_min": 0.182,
    "Bullish_ALT_Bat_XB_max": 0.50,
    "Bullish_ALT_Bat_AC_min": 0.282,
    "Bullish_ALT_Bat_AC_max": 1.386,
    "Bullish_ALT_Bat_BD_min": 0.618,
    "Bullish_ALT_Bat_BD_max": 2.018,
    "Bullish_ALT_Bat_XD_min": 0.2,
    "Bullish_ALT_Bat_XD_max": 2.5,
    "Bearish_Butterfly_XB_min": 0.3,
    "Bearish_Butterfly_XB_max": 0.786,
    "Bearish_Butterfly_AC_min": 0.182,
    "Bearish_Butterfly_AC_max": 0.986,
    "Bearish_Butterfly_BD_min": 1.0,
    "Bearish_Butterfly_BD_max": 2.24,
    "Bearish_Butterfly_XD_min": 1.0,
    "Bearish_Butterfly_XD_max": 2.41,
    "Bullish_Butterfly_XB_min": 0.382,
    "Bullish_Butterfly_XB_max": 0.70,
    "Bullish_Butterfly_AC_min": 0.282,
    "Bullish_Butterfly_AC_max": 1.886,
    "Bullish_Butterfly_BD_min": 1.0,
    "Bullish_Butterfly_BD_max": 2.018,
    "Bullish_Butterfly_XD_min": 0.2,
    "Bullish_Butterfly_XD_max": 3.5,
    "Bearish_Crab_XB_min": 0.282,
    "Bearish_Crab_XB_max": 0.818,
    "Bearish_Crab_AC_min": 0.482,
    "Bearish_Crab_AC_max": 0.986,
    "Bearish_Crab_BD_min": 1.618,
    "Bearish_Crab_BD_max": 3.618,
    "Bearish_Crab_XD_min": 1.118,
    "Bearish_Crab_XD_max": 3.618,
    "Bullish_Crab_XB_min": 0.482,
    "Bullish_Crab_XB_max": 0.80,
    "Bullish_Crab_AC_min": 0.282,
    "Bullish_Crab_AC_max": 2.886,
    "Bullish_Crab_BD_min": 1.5,
    "Bullish_Crab_BD_max": 2.5,
    "Bullish_Crab_XD_min": 0.2,
    "Bullish_Crab_XD_max": 2.5,
    "Bearish_Gartley_XB_min": 0.382,
    "Bearish_Gartley_XB_max": 0.618,
    "Bearish_Gartley_AC_min": 0.382,
    "Bearish_Gartley_AC_max": 0.886,
    "Bearish_Gartley_BD_min": 2.618,
    "Bearish_Gartley_BD_max": 3.618,
    "Bearish_Gartley_XD_min": 1.618,
    "Bearish_Gartley_XD_max": 2.618,
    "Bullish_Gartley_XB_min": 0.182,
    "Bullish_Gartley_XB_max": 0.50,
    "Bullish_Gartley_AC_min": 0.282,
    "Bullish_Gartley_AC_max": 2.286,
    "Bullish_Gartley_BD_min": 1.2,
    "Bullish_Gartley_BD_max": 2.7,
    "Bullish_Gartley_XD_min": 0.2,
    "Bullish_Gartley_XD_max": 2.5,
    "Bearish_Deep_Crab_XB_min": 0.282,
    "Bearish_Deep_Crab_XB_max": 0.818,
    "Bearish_Deep_Crab_AC_min": 0.282,
    "Bearish_Deep_Crab_AC_max": 0.886,
    "Bearish_Deep_Crab_BD_min": 1.618,
    "Bearish_Deep_Crab_BD_max": 3.618,
    "Bearish_Deep_Crab_XD_min": 0.618,
    "Bearish_Deep_Crab_XD_max": 2.618,
    "Bullish_Deep_Crab_XB_min": 0.382,
    "Bullish_Deep_Crab_XB_max": 0.70,
    "Bullish_Deep_Crab_AC_min": 0.282,
    "Bullish_Deep_Crab_AC_max": 1.286,
    "Bullish_Deep_Crab_BD_min": 1.5,
    "Bullish_Deep_Crab_BD_max": 3.7,
    "Bullish_Deep_Crab_XD_min": 0.6,
    "Bullish_Deep_Crab_XD_max": 2.5,
    "Bearish_Shark_AC_min": 1.0,
    "Bearish_Shark_AC_max": 3.618,
    "Bearish_Shark_BD_min": 1.0,
    "Bearish_Shark_BD_max": 3.24,
    "Bearish_Shark_XD_min": 0.886,
    "Bearish_Shark_XD_max": 2.13,
    "Bullish_Shark_AC_min": 1.0,
    "Bullish_Shark_AC_max": 3.618,
    "Bullish_Shark_BD_min": 1.0,
    "Bullish_Shark_BD_max": 3.24,
    "Bullish_Shark_XD_min": 0.886,
    "Bullish_Shark_XD_max": 2.13,
    "Bearish_Trend_AC_min": 0.382,
    "Bearish_Trend_AC_max": 0.886,
    "Bearish_Trend_BD_min": 1.13,
    "Bearish_Trend_BD_max": 2.618,
    "Bullish_Trend_AC_min": 0.382,
    "Bullish_Trend_AC_max": 0.886,
    "Bullish_Trend_BD_min": 1.13,
    "Bullish_Trend_BD_max": 2.618,
    "Bearish_ALT_Trend_AC_min": 0.382,
    "Bearish_ALT_Trend_AC_max": 0.886,
    "Bearish_ALT_Trend_BD_min": 1.27,
    "Bearish_ALT_Trend_BD_max": 1.618,
    "Bullish_ALT_Trend_AC_min": 0.382,
    "Bullish_ALT_Trend_AC_max": 0.886,
    "Bullish_ALT_Trend_BD_min": 1.13,
    "Bullish_ALT_Trend_BD_max": 2.618,
    "BullishPattern_AC_min": 1.0,
    "BullishPattern_AC_max": 3.618,
    "BullishPattern_BD_min": 1.0,
    "BullishPattern_BD_max": 3.24,
    "BullishPattern_CE_min": 0.886,
    "BullishPattern_CE_max": 2.13,
    "BearishPattern_AC_min": 1.0,
    "BearishPattern_AC_max": 3.618,
    "BearishPattern_BD_min": 1.0,
    "BearishPattern_BD_max": 3.24,
    "BearishPattern_CE_min": 0.886,
    "BearishPattern_CE_max": 2.13,
    "Bearish_Tree_Drives_AC_min": 1.0,
    "Bearish_Tree_Drives_AC_max": 2.5,
    "Bearish_Tree_Drives_BD_min": 1.5,
    "Bearish_Tree_Drives_BD_max": 3.5,
    "Bullish_Tree_Drives_AC_min": 1.0,
    "Bullish_Tree_Drives_AC_max": 1.5,
    "Bullish_Tree_Drives_BD_min": 1.5,
    "Bullish_Tree_Drives_BD_max": 2.5,
}
HARMONIC_CALLS = {
    0: ("pcBat", True, (
        "Bearish_Bat_XB_min", "Bearish_Bat_XB_max",
        "Bearish_Bat_AC_min", "Bearish_Bat_AC_max",
        "Bearish_Bat_BD_min", "Bearish_Bat_BD_max",
        "Bearish_Bat_XD_min", "Bearish_Bat_XD_max",
    )),
    1: ("pcBat", True, (
        "Bearish_ALT_Bat_XB_min", "Bearish_ALT_Bat_XB_max",
        "Bearish_ALT_Bat_AC_min", "Bearish_ALT_Bat_AC_max",
        "Bearish_ALT_Bat_BD_min", "Bearish_ALT_Bat_BD_max",
        "Bearish_ALT_Bat_XD_min", "Bearish_ALT_Bat_XD_max",
    )),
    2: ("pcBat", True, (
        "Bearish_Butterfly_XB_min", "Bearish_Butterfly_XB_max",
        "Bearish_Butterfly_AC_min", "Bearish_Butterfly_AC_max",
        "Bearish_Butterfly_BD_min", "Bearish_Butterfly_BD_max",
        "Bearish_Butterfly_XD_min", "Bearish_Butterfly_XD_max",
    )),
    3: ("pcBat", True, (
        "Bearish_Crab_XB_min", "Bearish_Crab_XB_max",
        "Bearish_Crab_AC_min", "Bearish_Crab_AC_max",
        "Bearish_Crab_BD_min", "Bearish_Crab_BD_max",
        "Bearish_Crab_XD_min", "Bearish_Crab_XD_max",
    )),
    4: ("pcBat", True, (
        "Bearish_Gartley_XB_min", "Bearish_Gartley_XB_max",
        "Bearish_Gartley_AC_min", "Bearish_Gartley_AC_max",
        "Bearish_Gartley_BD_min", "Bearish_Gartley_BD_max",
        "Bearish_Gartley_XD_min", "Bearish_Gartley_XD_max",
    )),
    5: ("pcBat", True, (
        "Bearish_Deep_Crab_XB_min", "Bearish_Deep_Crab_XB_max",
        "Bearish_Deep_Crab_AC_min", "Bearish_Deep_Crab_AC_max",
        "Bearish_Deep_Crab_BD_min", "Bearish_Deep_Crab_BD_max",
        "Bearish_Deep_Crab_XD_min", "Bearish_Deep_Crab_XD_max",
    )),
    6: ("pcShark", True, (
        "Bearish_Shark_AC_min", "Bearish_Shark_AC_max",
        "Bearish_Shark_BD_min", "Bearish_Shark_BD_max",
        "Bearish_Shark_XD_min", "Bearish_Shark_XD_max",
    )),
    7: ("pcABCD", True, (
        "Bearish_Trend_AC_min", "Bearish_Trend_AC_max",
        "Bearish_Trend_BD_min", "Bearish_Trend_BD_max",
    )),
    8: ("pcABCD", True, (
        "Bearish_ALT_Trend_AC_min", "Bearish_ALT_Trend_AC_max",
        "Bearish_ALT_Trend_BD_min", "Bearish_ALT_Trend_BD_max",
    )),
    9: ("pc50", True, (
        "BearishPattern_AC_min", "BearishPattern_AC_max",
        "BearishPattern_BD_min", "BearishPattern_BD_max",
        "BearishPattern_CE_min", "BearishPattern_CE_max",
    )),
    10: ("pc3Drives", True, (
        "Bearish_Tree_Drives_AC_min", "Bearish_Tree_Drives_AC_max",
        "Bearish_Tree_Drives_BD_min", "Bearish_Tree_Drives_BD_max",
    )),
    11: ("pcBat", False, (
        "Bullish_Bat_XB_min", "Bullish_Bat_XB_max",
        "Bullish_Bat_AC_min", "Bullish_Bat_AC_max",
        "Bullish_Bat_BD_min", "Bullish_Bat_BD_max",
        "Bullish_Bat_XD_min", "Bullish_Bat_XD_max",
    )),
    12: ("pcBat", False, (
        "Bullish_ALT_Bat_XB_min", "Bullish_ALT_Bat_XB_max",
        "Bullish_ALT_Bat_AC_min", "Bullish_ALT_Bat_AC_max",
        "Bullish_ALT_Bat_BD_min", "Bullish_ALT_Bat_BD_max",
        "Bullish_ALT_Bat_XD_min", "Bullish_ALT_Bat_XD_max",
    )),
    13: ("pcBat", False, (
        "Bullish_Butterfly_XB_min", "Bullish_Butterfly_XB_max",
        "Bullish_Butterfly_AC_min", "Bullish_Butterfly_AC_max",
        "Bullish_Butterfly_BD_min", "Bullish_Butterfly_BD_max",
        "Bullish_Butterfly_XD_min", "Bullish_Butterfly_XD_max",
    )),
    14: ("pcBat", False, (
        "Bullish_Crab_XB_min", "Bullish_Crab_XB_max",
        "Bullish_Crab_AC_min", "Bullish_Crab_AC_max",
        "Bullish_Crab_BD_min", "Bullish_Crab_BD_max",
        "Bullish_Crab_XD_min", "Bullish_Crab_XD_max",
    )),
    15: ("pcBat", False, (
        "Bullish_Gartley_XB_min", "Bullish_Gartley_XB_max",
        "Bullish_Gartley_AC_min", "Bullish_Gartley_AC_max",
        "Bullish_Gartley_BD_min", "Bullish_Gartley_BD_max",
        "Bullish_Gartley_XD_min", "Bullish_Gartley_XD_max",
    )),
    16: ("pcBat", False, (
        "Bullish_Deep_Crab_XB_min", "Bullish_Deep_Crab_XB_max",
        "Bullish_Deep_Crab_AC_min", "Bullish_Deep_Crab_AC_max",
        "Bullish_Deep_Crab_BD_min", "Bullish_Deep_Crab_BD_max",
        "Bullish_Deep_Crab_XD_min", "Bullish_Deep_Crab_XD_max",
    )),
    17: ("pcShark", False, (
        "Bullish_Shark_AC_min", "Bullish_Shark_AC_max",
        "Bullish_Shark_BD_min", "Bullish_Shark_BD_max",
        "Bullish_Shark_XD_min", "Bullish_Shark_XD_max",
    )),
    18: ("pcABCD", False, (
        "Bullish_Trend_AC_min", "Bullish_Trend_AC_max",
        "Bullish_Trend_BD_min", "Bullish_Trend_BD_max",
    )),
    19: ("pcABCD", False, (
        "Bullish_ALT_Trend_AC_min", "Bullish_ALT_Trend_AC_max",
        "Bullish_ALT_Trend_BD_min", "Bullish_ALT_Trend_BD_max",
    )),
    20: ("pc50", False, (
        "BullishPattern_AC_min", "BullishPattern_AC_max",
        "BullishPattern_BD_min", "BullishPattern_BD_max",
        "BullishPattern_CE_min", "BullishPattern_CE_max",
    )),
    21: ("pc3Drives", False, (
        "Bullish_Tree_Drives_AC_min", "Bullish_Tree_Drives_AC_max",
        "Bullish_Tree_Drives_BD_min", "Bullish_Tree_Drives_BD_max",
    )),
}
# END GENERATED

# L105-115: every pattern is enabled by default (each use*/en* input of L48-92 defaults to true).
EN = (True,) * N_IDS

SWING_COLUMNS = ("bar", "price", "close_at_set", "is_high")
ROW_COLUMNS = ("t_bar", "id", "name", "kind", "dir", "first_hit", "n_hits", "n_pts", "xs", "ys", "d_bar", "d_price",
               "c0", "entry", "sl", "tp1", "tp2")
FORMING_COLUMNS = ROW_COLUMNS + ("instance_key", "first_bar_of_instance")


# ───────────────────────────── the generator of the tables ─────────────────────────────

_NAMES_OPEN = "var array<string> NAMES = array.from("
_RATIO_RE = re.compile(r"^((?:Bearish|Bullish)\w*_(?:min|max)) = (\d+(?:\.\d+)?)$")
_CALL_RE = re.compile(r"^\s*(\d+) => (pcBat|pcShark|pcABCD|pc50|pc3Drives)\(P, (true|false), ([A-Za-z0-9_, ]+)\)$")
_N_ARGS = {"pcBat": 8, "pcShark": 6, "pcABCD": 4, "pc50": 6, "pc3Drives": 4}


def read_source(path) -> str:
    """The text of a Pine source file, decoded from its bytes WITHOUT newline translation. The .rtf original ends
    some lines in a carriage return before RTF's backslash-newline, and Python's universal newlines would turn that
    carriage return into an extra line."""
    return Path(path).read_bytes().decode("utf-8", errors="replace")


def source_lines(text: str) -> List[str]:
    """The Pine source as a list of lines (no line ends). The owner's .rtf original is accepted:
    - its RTF header is dropped (everything before ``//@version=``);
    - its lines end in a backslash and a line feed (RTF's paragraph break), some with a carriage return before the
      backslash. The carriage returns are dropped, the text is split at the line feeds, and the trailing backslash
      is removed. The lines then match the .txt copy line for line;
    - lines with RTF escapes (comments with non-ASCII characters) are left as they are. The parser does not read
      them."""
    if not text.lstrip().startswith("{\\rtf"):
        return text.splitlines()
    lines = text.replace("\r", "").split("\n")
    k = next(i for i, s in enumerate(lines) if "//@version=" in s)
    lines = lines[k:]
    lines[0] = lines[0][lines[0].index("//@version="):]
    return [s[:-1] if s.endswith("\\") else s for s in lines]


def generate_tables(text: str):
    """
    Parse the script's tables from its Pine text. It returns ``(names, ratios, calls, spans)``:
    - ``names``: the 38 strings of ``NAMES`` (L96-103);
    - ``ratios``: {constant name: (float value, literal text)}, the 144 constants of the ratio region (L146-289), in
      source order;
    - ``calls``: {id: (function, bear, (constant names...))}, the 22 harmonic cases of ``check`` (L484-505);
    - ``spans``: {"names" | "ratios" | "calls": (first line, last line)}, 1-based line numbers in ``text``.

    It raises ValueError when a count or a cross-reference does not hold: 38 names, 144 distinct constants (each
    used by exactly one call), ids 0-21 each exactly once, and the right number of arguments per function.
    """
    lines = source_lines(text)
    # NAMES: from the array.from( line to its closing parenthesis
    k0 = next(i for i, s in enumerate(lines) if s.strip().startswith(_NAMES_OPEN))
    k1 = k0
    while not lines[k1].rstrip().endswith(")"):
        k1 += 1
    names = re.findall(r'"([^"]*)"', "\n".join(lines[k0:k1 + 1]))
    # the ratio constants: every "Bearish..._min/_max = number" / "Bullish..." line
    ratios: Dict[str, Tuple[float, str]] = {}
    r_lines = []
    for i, s in enumerate(lines):
        m = _RATIO_RE.match(s.strip())
        if m:
            if m.group(1) in ratios:
                raise ValueError(f"ratio constant {m.group(1)} defined twice")
            ratios[m.group(1)] = (float(m.group(2)), m.group(2))
            r_lines.append(i)
    # the harmonic cases of check()
    calls: Dict[int, Tuple[str, bool, Tuple[str, ...]]] = {}
    c_lines = []
    for i, s in enumerate(lines):
        m = _CALL_RE.match(s)
        if m:
            cid, fn, bear = int(m.group(1)), m.group(2), m.group(3) == "true"
            args = tuple(a.strip() for a in m.group(4).split(","))
            if cid in calls:
                raise ValueError(f"check case {cid} appears twice")
            if len(args) != _N_ARGS[fn]:
                raise ValueError(f"check case {cid}: {fn} takes {_N_ARGS[fn]} constants, got {len(args)}")
            calls[cid] = (fn, bear, args)
            c_lines.append(i)
    if len(names) != N_IDS:
        raise ValueError(f"NAMES: {len(names)} strings, 38 expected")
    if len(ratios) != 144:
        raise ValueError(f"{len(ratios)} ratio constants, 144 expected")
    if sorted(calls) != list(range(22)):
        raise ValueError(f"harmonic check cases {sorted(calls)}, 0-21 expected")
    used = [a for _, _, args in calls.values() for a in args]
    if sorted(used) != sorted(ratios):
        raise ValueError("the harmonic check cases do not use each ratio constant exactly once")
    if r_lines != list(range(r_lines[0], r_lines[0] + len(r_lines))):
        raise ValueError("the ratio constants are not one contiguous block")
    spans = {"names": (k0 + 1, k1 + 1), "ratios": (r_lines[0] + 1, r_lines[-1] + 1),
             "calls": (c_lines[0] + 1, c_lines[-1] + 1)}
    return names, ratios, calls, spans


def generated_block(text: str) -> str:
    """The Python block between the GENERATED markers, written from the Pine text by ``generate_tables``. Values are
    written as their literal text in the source, so Python parses each one to the same double that Pine does."""
    names, ratios, calls, spans = generate_tables(text)
    out = ["# BEGIN GENERATED",
           "# Written by generate_tables() from the Pine source; do not edit by hand. Regenerate with",
           '#     python3 -B tests/tradeiq2_oracle_patterns.py generate "<Harmonic and Chart Patterns Script.txt>"',
           f"# NAMES: source lines {spans['names'][0]}-{spans['names'][1]}; RATIOS: the 144 constants of lines "
           f"{spans['ratios'][0]}-{spans['ratios'][1]};",
           f"# HARMONIC_CALLS: the harmonic cases of check(), lines {spans['calls'][0]}-{spans['calls'][1]} "
           "(id: (function, bear, its constants)).",
           "NAMES = ("]
    for i in range(0, N_IDS, 6):
        out.append("    " + " ".join(f'"{n}",' for n in names[i:i + 6]))
    out.append(")")
    out.append("RATIOS = {")
    for k, (_, lit) in ratios.items():
        out.append(f'    "{k}": {lit},')
    out.append("}")
    out.append("HARMONIC_CALLS = {")
    for cid in range(22):
        fn, bear, args = calls[cid]
        out.append(f'    {cid}: ("{fn}", {bear}, (')
        for j in range(0, len(args), 2):
            out.append("        " + " ".join(f'"{a}",' for a in args[j:j + 2]))
        out.append("    )),")
    out.append("}")
    out.append("# END GENERATED")
    return "\n".join(out) + "\n"


# ───────────────────────────── the registry (L95-142) ─────────────────────────────

def dirOf(id: int) -> int:                                                                         # L117-125
    d = 1
    if id <= 10:
        d = -1
    elif id <= 21:
        d = 1
    elif id == 22 or id == 24 or id == 26 or id == 28 or id == 30 or id == 33 or id == 35 or id == 37:
        d = -1
    return d


def ptsOf(id: int) -> int:                                                                         # L128-142
    n = 5
    if id == 7 or id == 8 or id == 18 or id == 19:
        n = 4
    elif id == 9 or id == 20:
        n = 6
    elif id == 22 or id == 23:
        n = 5
    elif id >= 24 and id <= 27:
        n = 7
    elif id >= 28 and id <= 31:
        n = 9
    elif id >= 32:
        n = 8
    return n


def kindOf(id: int) -> str:
    """'harmonic' for ids 0-21, 'chart' for 22-37: the split the script uses for colours, drawing and the plan
    (L617, L628, L702)."""
    return "harmonic" if id <= 21 else "chart"


# ───────────────────────────── the pattern rules (L292-531) ─────────────────────────────
# P[0] = point D (the latest swing of the set), P[1] = C, ... (L292). Strict inequalities, the script's orientation.

def inR(bear: bool, A: float, B: float, mn: float, mx: float, d: float) -> bool:                  # L293-294
    if bear:
        return d < (A - B) * mx + B and d > (A - B) * mn + B
    return d < B - (B - A) * mn and d > B - (B - A) * mx


def pcBat(P, bear, xb0, xb1, ac0, ac1, bd0, bd1, xd0, xd1) -> bool:                                # L296-297
    return (inR(bear, P[4], P[3], xb0, xb1, P[2]) and inR(bear, P[2], P[3], ac0, ac1, P[1])
            and inR(bear, P[2], P[1], bd0, bd1, P[0]) and inR(bear, P[4], P[3], xd0, xd1, P[0]))


def pcShark(P, bear, ac0, ac1, bd0, bd1, xd0, xd1) -> bool:                                        # L299-305
    p0, p1, p2, p3, p4 = P[0], P[1], P[2], P[3], P[4]
    if bear:
        return (inR(False, p3, p2, ac0, ac1, p1) and inR(True, p2, p1, bd0, bd1, p0)
                and inR(True, p4, p3, xd0, xd1, p0) and p4 > p3 and p4 > p2)
    return (inR(True, p3, p2, ac0, ac1, p1) and inR(False, p2, p1, bd0, bd1, p0)
            and inR(False, p4, p3, xd0, xd1, p0) and p4 < p3 and p4 < p2)


def pcABCD(P, bear, ac0, ac1, bd0, bd1) -> bool:                                                    # L307-308
    return inR(bear, P[2], P[3], ac0, ac1, P[1]) and inR(bear, P[2], P[1], bd0, bd1, P[0])


def pc50(P, bear, ac0, ac1, bd0, bd1, ce0, ce1) -> bool:                                           # L310-317
    p0, p1, p2, p3, p4, p5 = P[0], P[1], P[2], P[3], P[4], P[5]
    if bear:
        return (inR(True, p4, p3, ac0, ac1, p2) and inR(False, p3, p2, bd0, bd1, p1)
                and inR(True, p2, p1, ce0, ce1, p0) and p5 < p4 and p5 < p3)
    return (inR(False, p4, p3, ac0, ac1, p2) and inR(True, p3, p2, bd0, bd1, p1)
            and inR(False, p2, p1, ce0, ce1, p0) and p5 > p4 and p5 > p3)


def pc3Drives(P, bear, ac0, ac1, ce0, ce1) -> bool:                                                # L319-320
    return inR(bear, P[4], P[3], ac0, ac1, P[2]) and inR(bear, P[2], P[1], ce0, ce1, P[0])


def pcDoubleTop(P, c0) -> bool:                                                                    # L322-327
    p1, p2, p3, p4 = P[1], P[2], P[3], P[4]
    return (p3 - p4) / 2 > p3 - p2 and inR(True, p3, p2, 0.8, 1.2, p1) and p4 < p2 and p2 < p1 and c0 < p2


def pcDoubleBottom(P, c0) -> bool:                                                                 # L329-334
    p1, p2, p3, p4 = P[1], P[2], P[3], P[4]
    return (p4 - p3) / 2 > p2 - p3 and inR(False, p3, p2, 0.8, 1.2, p1) and p4 > p2 and p2 > p1 and c0 > p2


def pcHeadShoulders(P, c0) -> bool:                                                                # L336-343
    p1, p2, p3, p4, p5, p6 = P[1], P[2], P[3], P[4], P[5], P[6]
    return ((p5 - p6) / 2 > p5 - p4 and p1 < p3 and inR(True, p5, p4, 1.2, 2.5, p3)
            and inR(False, p4, p3, 0.8, 1.2, p2) and c0 < p2)


def pcInvHeadShoulders(P, c0) -> bool:                                                             # L345-352
    p1, p2, p3, p4, p5, p6 = P[1], P[2], P[3], P[4], P[5], P[6]
    return ((p6 - p5) / 2 > p4 - p5 and p1 > p3 and inR(False, p5, p4, 1.2, 2.5, p3)
            and inR(True, p4, p3, 0.8, 1.2, p2) and c0 > p2)


def pcTripleTop(P, c0) -> bool:                                                                    # L354-361
    p1, p2, p3, p4, p5, p6 = P[1], P[2], P[3], P[4], P[5], P[6]
    return ((p5 - p6) / 1.5 > p5 - p4 and p1 < p3 and inR(True, p5, p4, 0.8, 1.2, p3)
            and inR(False, p4, p3, 0.8, 1.2, p2) and c0 < p2)


def pcTripleBottom(P, c0) -> bool:                                                                 # L363-370
    p1, p2, p3, p4, p5, p6 = P[1], P[2], P[3], P[4], P[5], P[6]
    return ((p6 - p5) / 1.5 > p4 - p5 and p1 > p3 and inR(False, p5, p4, 0.8, 1.2, p3)
            and inR(True, p4, p3, 0.8, 1.2, p2) and c0 > p2)


def pcBearRisingWedge(P, c0) -> bool:                                                              # L372-381
    p1, p2, p3, p4, p5, p6, p7, p8 = P[1], P[2], P[3], P[4], P[5], P[6], P[7], P[8]
    return (p8 < p6 and p6 < p4 and p4 < p2 and p7 < p5 and p5 < p3 and p3 < p1
            and p7 - p6 > p5 - p4 and p5 - p4 > p3 - p2 and c0 < p2)


def pcBullRisingWedge(P, c0) -> bool:                                                              # L383-392
    p1, p2, p3, p4, p5, p6, p7, p8 = P[1], P[2], P[3], P[4], P[5], P[6], P[7], P[8]
    return (p8 > p6 and p6 > p4 and p4 > p2 and p7 > p5 and p5 > p3 and p3 > p1
            and p6 - p7 > p4 - p5 and p4 - p5 > p2 - p3 and c0 > p2)


def pcBearExpTriangle(P, c0) -> bool:                                                              # L394-403
    p1, p2, p3, p4, p5, p6, p7, p8 = P[1], P[2], P[3], P[4], P[5], P[6], P[7], P[8]
    return (p8 < p6 and p6 < p4 and p4 < p2 and p7 < p5 and p5 < p3 and p3 < p1
            and p7 - p6 < p5 - p4 and p5 - p4 < p3 - p2 and c0 < p2)


def pcBullExpTriangle(P, c0) -> bool:                                                              # L405-414
    p1, p2, p3, p4, p5, p6, p7, p8 = P[1], P[2], P[3], P[4], P[5], P[6], P[7], P[8]
    return (p8 > p6 and p6 > p4 and p4 > p2 and p7 > p5 and p5 > p3 and p3 > p1
            and p6 - p7 < p4 - p5 and p4 - p5 < p2 - p3 and c0 > p2)


def pcBullPennant(P, c0) -> bool:                                                                  # L416-424
    p1, p2, p3, p4, p5, p6, p7 = P[1], P[2], P[3], P[4], P[5], P[6], P[7]
    return (p6 - p7) / 1.2 > p6 - p5 and p6 > p4 and p4 > p2 and p5 < p3 and p3 < p1 and c0 > p2


def pcBearPennant(P, c0) -> bool:                                                                  # L426-434
    p1, p2, p3, p4, p5, p6, p7 = P[1], P[2], P[3], P[4], P[5], P[6], P[7]
    return (p7 - p6) / 1.2 > p5 - p6 and p6 < p4 and p4 < p2 and p5 > p3 and p3 > p1 and c0 < p2


def pcBullFallingWedgeT(P, c0) -> bool:                                                            # L436-444
    p1, p2, p3, p4, p5, p6, p7 = P[1], P[2], P[3], P[4], P[5], P[6], P[7]
    return ((p6 - p7) / 1.2 > p6 - p5 and p6 > p5 and p2 > p5 and p6 > p4 and p4 > p2 and p5 > p3 and p3 > p1
            and (p6 - p5) / 1.7 > p2 - p1 and c0 > p2)


def pcBearRisingWedgeT(P, c0) -> bool:                                                             # L446-454
    p1, p2, p3, p4, p5, p6, p7 = P[1], P[2], P[3], P[4], P[5], P[6], P[7]
    return ((p7 - p6) / 1.2 > p5 - p6 and p6 < p5 and p2 < p5 and p6 < p4 and p4 < p2 and p5 < p3 and p3 < p1
            and (p5 - p6) / 1.7 > p1 - p2 and c0 < p2)


def pcBullFlag(P, c0) -> bool:                                                                     # L456-467
    p1, p2, p3, p4, p5, p6, p7 = P[1], P[2], P[3], P[4], P[5], P[6], P[7]
    maxP = (p6 - p5) * 1.2
    minP = (p6 - p5) * 0.8
    pp = p2 - p1
    return ((p6 - p7) / 1.2 > p6 - p5 and p6 > p5 and p2 > p5 and p6 > p4 and p4 > p2 and p5 > p3 and p3 > p1
            and pp < maxP and pp > minP and c0 > p2)


def pcBearFlag(P, c0) -> bool:                                                                     # L469-480
    p1, p2, p3, p4, p5, p6, p7 = P[1], P[2], P[3], P[4], P[5], P[6], P[7]
    maxP = (p5 - p6) * 1.2
    minP = (p5 - p6) * 0.8
    pp = p1 - p2
    return ((p7 - p6) / 1.2 > p5 - p6 and p6 < p5 and p2 < p5 and p6 < p4 and p4 < p2 and p5 < p3 and p3 < p1
            and pp < maxP and pp > minP and c0 < p2)


_HARMONIC_FUNCS = {"pcBat": pcBat, "pcShark": pcShark, "pcABCD": pcABCD, "pc50": pc50, "pc3Drives": pc3Drives}
_CHART_FUNCS = {22: pcDoubleTop, 23: pcDoubleBottom, 24: pcHeadShoulders, 25: pcInvHeadShoulders,      # L506-521
                26: pcTripleTop, 27: pcTripleBottom, 28: pcBearRisingWedge, 29: pcBullRisingWedge,
                30: pcBearExpTriangle, 31: pcBullExpTriangle, 32: pcBullPennant, 33: pcBearPennant,
                34: pcBullFallingWedgeT, 35: pcBearRisingWedgeT, 36: pcBullFlag, 37: pcBearFlag}


def check(id: int, P: Sequence[float], c0: float) -> bool:                                         # L482-522
    """``check(id, P, c0)``: ids 0-21 call their harmonic function with the constants of HARMONIC_CALLS (generated
    from L484-505), ids 22-37 their chart predicate (L506-521); any other id is false (L522)."""
    if 0 <= id <= 21:
        fn, bear, args = HARMONIC_CALLS[id]
        return _HARMONIC_FUNCS[fn](P, bear, *[RATIOS[a] for a in args])
    f = _CHART_FUNCS.get(id)
    return False if f is None else f(P, c0)


def detect(Q: Sequence[float], c0: float) -> List[int]:                                            # L525-531
    """Every enabled id whose predicate holds, in registry order (``hits.get(0)`` is the one the script uses)."""
    hits = []
    for id in range(0, N_IDS):
        if EN[id]:
            if check(id, Q, c0):
                hits.append(id)
    return hits


def planLevels(id: int, Q: Sequence[float]) -> Tuple[float, float, float, float, float, float]:   # L694-718
    """The trade plan from the swings Q (Q[0] = D): (entry, sl, tp1, tp2, prz_lo, prz_hi); na (NaN) when the
    pattern's size is 0. The PRZ (harmonics only) is drawn, never traded."""
    dir = dirOf(id)
    e = sl = t1 = t2 = zl = zh = math.nan
    if id <= 21:
        ad = abs(Q[3] - Q[0])
        if ad > 0:
            e = Q[0]
            sl = Q[0] - dir * SL_K * ad
            t1 = Q[0] + dir * TP1_K * ad
            t2 = Q[0] + dir * TP2_K * ad
            zl = Q[0] - 0.06 * ad
            zh = Q[0] + 0.06 * ad
    else:
        h = abs(Q[1] - Q[2])
        if h > 0:
            e = Q[2]
            sl = Q[2] - dir * CSL_K * h
            t1 = Q[2] + dir * CTP1_K * h
            t2 = Q[2] + dir * CTP2_K * h
    return e, sl, t1, t2, zl, zh


# ───────────────────────────── Pine primitives ─────────────────────────────

def _extreme_bars(hist: Sequence[float], length: int, higher: bool, ties: str) -> Optional[int]:
    """The offset (0 = the current bar, -k = k bars back) of the highest (``higher``) or lowest value of the last
    ``length`` values of ``hist`` (oldest first, the last = the current bar); None (na) when fewer than ``length``
    values exist (R2). ``ties='newest'``: the most recent of equal values wins (R1; scanning back from the current
    bar, a value must beat the best strictly); ``'oldest'``: the earliest wins (the alternative, measured only)."""
    if ties not in ("newest", "oldest"):
        raise ValueError(f"ties: 'newest' or 'oldest', got {ties!r}")
    n = len(hist)
    if n < length:
        return None
    best = hist[n - 1]
    best_off = 0
    for off in range(1, length):
        v = hist[n - 1 - off]
        if higher:
            better = v > best if ties == "newest" else v >= best
        else:
            better = v < best if ties == "newest" else v <= best
        if better:
            best, best_off = v, off
    return -best_off


def ta_highestbars(hist: Sequence[float], length: int, ties: str = "newest") -> Optional[int]:
    """``ta.highestbars(source, length)`` on the current bar (``hist`` = the series to it, oldest first)."""
    return _extreme_bars(hist, length, True, ties)


def ta_lowestbars(hist: Sequence[float], length: int, ties: str = "newest") -> Optional[int]:
    """``ta.lowestbars(source, length)`` on the current bar (``hist`` = the series to it, oldest first)."""
    return _extreme_bars(hist, length, False, ties)


def _pine_get(a: List, i: int):
    """``array.get``: Pine accepts a negative index (from the end); outside the array it is a runtime error."""
    if not -len(a) <= i < len(a):
        raise IndexError(f"array.get: index {i} out of bounds, array size {len(a)}")
    return a[i]


# ───────────────────────────── the script, bar by bar ─────────────────────────────

class Step:
    """What one bar's close produced: ``added``, and the hit rows of the confirmed and forming detections."""
    __slots__ = ("added", "confirmed", "forming")

    def __init__(self):
        self.added = False
        self.confirmed: List[dict] = []
        self.forming: List[dict] = []


class Script:
    """
    The script's state and its per-bar statements in its own order:
    1. the zigzag, L540-572;
    2. the confirmed detection, L780-795;
    3. the forming detection of L802-813, run at every bar (R3).
    ``step(high, low, close)`` executes one bar and returns a ``Step``. ``pivP`` / ``pivB`` / ``pivC`` / ``zdir`` are
    the script's ``var`` arrays (newest first, at most 60). ``log`` holds every swing ever added, oldest first, each
    as [bar, price, close, is_high] in its current state (the last one is live).
    """

    def __init__(self, depth: int = DEPTH, ties: str = "newest"):
        if isinstance(depth, bool) or int(depth) != depth or not 2 <= int(depth) <= 50:
            raise ValueError(f"depth: an integer 2-50 is expected (L19), got {depth!r}")
        if ties not in ("newest", "oldest"):
            raise ValueError(f"ties: 'newest' or 'oldest', got {ties!r}")
        self.depth = int(depth)
        self.ties = ties
        self.bar_index = -1
        self.high: List[float] = []
        self.low: List[float] = []
        self.pivP: List[float] = []          # L535
        self.pivB: List[int] = []            # L536
        self.pivC: List[float] = []          # L537
        self.zdir = 0                        # L538
        self.log: List[list] = []
        self.seen_instances = set()

    # L575-580
    def makeQ(self, s: int) -> List[float]:
        q = [0.0] * 11
        n = len(self.pivP)
        for k in range(0, 11):
            q[k] = _pine_get(self.pivP, min(s + k, n - 1))
        return q

    def _unshift(self, price: float, close: float, is_high: bool) -> None:
        self.pivP.insert(0, price)
        self.pivB.insert(0, self.bar_index)
        self.pivC.insert(0, close)
        self.log.append([self.bar_index, price, close, is_high])

    def _set0(self, price: float, close: float) -> None:
        self.pivP[0] = price
        self.pivB[0] = self.bar_index
        self.pivC[0] = close
        self.log[-1][0:3] = [self.bar_index, price, close]

    def step(self, high: float, low: float, close: float) -> Step:
        self.bar_index += 1
        bar_index = self.bar_index
        self.high.append(high)
        self.low.append(low)
        out = Step()
        pivP, pivB = self.pivP, self.pivB

        # ── ZigZag (L540-572) ──
        added = False                                                                              # L540
        isHi = ta_highestbars(self.high, self.depth, self.ties) == 0                               # L541 (na == 0: false)
        isLo = ta_lowestbars(self.low, self.depth, self.ties) == 0                                 # L542
        if isHi:                                                                                   # L544
            if self.zdir == 1:                                                                     # L545
                if high > pivP[0]:                                                                 # L546
                    self._set0(high, close)                                                        # L547-549
            elif len(pivP) == 0 or abs(high - pivP[0]) >= pivP[0] * DEV_PCT / 100:                 # L550
                self._unshift(high, close, True)                                                   # L551-553
                self.zdir = 1                                                                      # L554
                added = True                                                                       # L555
        if isLo:                                                                                   # L556
            if self.zdir == -1:                                                                    # L557
                if low < pivP[0]:                                                                  # L558
                    self._set0(low, close)                                                         # L559-561
            elif len(pivB) == 0 or pivB[0] != bar_index:                                           # L562
                if len(pivP) == 0 or abs(pivP[0] - low) >= pivP[0] * DEV_PCT / 100:                # L563
                    self._unshift(low, close, False)                                               # L564-566
                    self.zdir = -1                                                                 # L567
                    added = True                                                                   # L568
        if len(pivP) > MAX_SWINGS:                                                                 # L569-572
            self.pivP.pop()
            self.pivB.pop()
            self.pivC.pop()
        out.added = added

        # ── confirmed patterns (L780-795): the new swing fixes the previous one, which is point D ──
        if added and len(self.pivP) >= 12:                                                         # L780
            Q = self.makeQ(1)
            c0 = _pine_get(self.pivC, 1)
            hits = detect(Q, c0)                                                                   # L781
            out.confirmed = self._rows(hits, 1, Q, c0, forming=False)

        # ── the forming pattern (L802-813), at every bar close (R3) ──
        if SHOW_FORMING and len(self.pivP) >= 11:                                                  # L807
            Q = self.makeQ(0)
            hits = detect(Q, close)                                                                # L808
            out.forming = self._rows(hits, 0, Q, close, forming=True)
        return out

    def _rows(self, hits: List[int], s: int, Q: List[float], c0: float, forming: bool) -> List[dict]:
        rows = []
        for j, id in enumerate(hits):
            n = ptsOf(id)
            xs, ys = [], []
            for jj in range(0, n):                                                                 # newPat, L609-612
                k = s + n - 1 - jj
                xs.append(_pine_get(self.pivB, k))
                ys.append(_pine_get(self.pivP, k))
            e, sl, t1, t2, _, _ = planLevels(id, Q)
            r = {"t_bar": self.bar_index, "id": id, "name": NAMES[id], "kind": kindOf(id), "dir": dirOf(id),
                 "first_hit": j == 0, "n_hits": len(hits), "n_pts": n, "xs": tuple(xs), "ys": tuple(ys),
                 "d_bar": xs[-1], "d_price": ys[-1], "c0": c0, "entry": e, "sl": sl, "tp1": t1, "tp2": t2}
            if forming:
                key = (id,) + tuple(_pine_get(self.pivB, k) for k in range(1, n))                  # R4
                r["instance_key"] = key
                r["first_bar_of_instance"] = key not in self.seen_instances
                self.seen_instances.add(key)
            rows.append(r)
        return rows


# ───────────────────────────── the whole series ─────────────────────────────

def _series(x, name: str) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name}: every value must be finite (R6)")
    return a


_DTYPES = {"t_bar": "int64", "id": "int64", "name": "object", "kind": "object", "dir": "int64", "first_hit": "bool",
           "n_hits": "int64", "n_pts": "int64", "xs": "object", "ys": "object", "d_bar": "int64",
           "d_price": "float64", "c0": "float64", "entry": "float64", "sl": "float64", "tp1": "float64",
           "tp2": "float64", "instance_key": "object", "first_bar_of_instance": "bool"}


def _frame(rows: List[dict], columns: Tuple[str, ...]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(columns)) if rows else pd.DataFrame({k: [] for k in columns})
    return df.astype({k: _DTYPES[k] for k in columns}).reset_index(drop=True)


def patterns(h, l, c, depth: int = DEPTH, *, _ties: str = "newest") -> Dict[str, object]:
    """
    Run the script over the bars (``h, l, c``: the bid high, low and close, oldest first). It returns the dict that
    the module docstring describes: ``swings``, ``n_swings``, ``added``, ``confirmed``, ``forming``. ``_ties``
    (private) only measures reading R1.
    """
    h, l, c = _series(h, "h"), _series(l, "l"), _series(c, "c")
    if not (len(h) == len(l) == len(c)):
        raise ValueError(f"h, l, c: lengths {len(h)}, {len(l)}, {len(c)} differ")
    sc = Script(depth, _ties)
    n = len(h)
    n_swings = np.zeros(n, np.int64)
    added = np.zeros(n, bool)
    conf: List[dict] = []
    form: List[dict] = []
    for i in range(n):
        st = sc.step(float(h[i]), float(l[i]), float(c[i]))
        n_swings[i] = len(sc.log)
        added[i] = st.added
        conf.extend(st.confirmed)
        form.extend(st.forming)
    sw = pd.DataFrame({"bar": np.array([s[0] for s in sc.log], np.int64),
                       "price": np.array([s[1] for s in sc.log], np.float64),
                       "close_at_set": np.array([s[2] for s in sc.log], np.float64),
                       "is_high": np.array([s[3] for s in sc.log], bool)}, columns=list(SWING_COLUMNS))
    return {"swings": sw, "n_swings": n_swings, "added": added,
            "confirmed": _frame(conf, ROW_COLUMNS), "forming": _frame(form, FORMING_COLUMNS)}


def drawn_mask(confirmed: pd.DataFrame, hist_max: int = HIST_MAX) -> np.ndarray:
    """
    DISPLAY ONLY: for each confirmed detection (its first-hit row, in t_bar order), would the script draw it?
    ``overlaps`` (L767-777) compares the pattern's span [xs[0], xs[-1]] with every pattern still in ``pats``. It is a
    hit when their intersection is longer than half of the shorter span. A detection that overlaps is not drawn and
    is not pushed (L785-788); ``pats`` keeps the newest ``histMax`` (L790-792). The alert fires either way (L793-795),
    which is why ``confirmed`` keeps every detection; this mask exists only so a test can show that.
    """
    first = confirmed[confirmed["first_hit"]].sort_values("t_bar")
    pats: List[Tuple[int, int]] = []
    out = []
    for xs in first["xs"]:
        a, b = int(xs[0]), int(xs[-1])
        hit = False
        for pa, pb in pats:
            lo = max(a, pa)
            hi = min(b, pb)
            ln = min(b - a, pb - pa)
            if hi > lo and ln > 0 and float(hi - lo) / ln > 0.5:
                hit = True
        if not hit:
            pats.append((a, b))
            if len(pats) > hist_max:
                pats.pop(0)
        out.append(not hit)
    return np.array(out, bool)


def _main(argv: Sequence[str]) -> int:
    if len(argv) == 2 and argv[0] == "generate":
        sys.stdout.write(generated_block(read_source(argv[1])))
        return 0
    sys.stderr.write('usage: python3 -B tests/tradeiq2_oracle_patterns.py generate "<Pine source>"\n')
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
