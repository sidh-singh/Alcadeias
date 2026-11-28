"""
"Harmonic & Chart Patterns [AI-AlgoCode]" (Pine v6, 830 lines): the zigzag, the 38 pattern predicates, the confirmed
alerts and the forming detection, port A, the production port of study 2 (``backtest_results/tradeiq_2027/PREREG.md``
section 6.7, rows HP-HF / HP-HC / HP-CF / HP-CS / HP-CC / HP-DRAWN).

    from backtesting.research import tradeiq2_ind_patterns as HP
    out = HP.patterns(b.h, b.l, b.c)                 # depth 5, every other input at the script's default
    out["confirmed"], out["forming"], out["swings"]  # pandas DataFrames (columns below)

Line numbers ``(Lnnn)`` are those of the owner's copy of the source (the study's scratch ``src/Harmonic and Chart
Patterns Script.txt``, sha256 in ``SOURCE_SHA256``). The copy is third-party code and is not in the repository: only
its 38 names, its 144 ratio constants and the dispatch of ``check`` are here, as a table GENERATED from the source text
by ``parse_pine_source`` / ``render_tables`` (``python -B -m backtesting.research.tradeiq2_ind_patterns tables
<source>``), never retyped; ``tests/test_tradeiq2_ind_patterns_a.py`` regenerates it from the source when the file is
present. The specification is the study's scratch map ``maps/ribbon_patterns.md`` part B. Port B
(``tests/tradeiq2_oracle_patterns.py``) is written by another engineer from the same sources, independently; this
module was written without reading it.

Reconciled with port B on 28 Nov 2026 (``tests/test_tradeiq2_ind_patterns.py``; the porting notes are
``backtest_results/tradeiq_2027/porting/patterns.md``): on the 1H, 4H and 1D bars of both symbols from the study's data
start to 2024-06-30, the swings, every per-bar array, every column of the confirmed and forming tables, ``drawn`` and
``armed`` on ``forming_q`` are equal bit for bit, and so on synthetic bars with ties, outside bars and depths 2-50.
No mismatch was found, and this module's behaviour is unchanged.

What it computes, in the script's order on each bar
----------------------------------------------------
1. **The zigzag** (L535-572; inputs ``depth`` 5 L19, ``devPct`` 0 L21). ``isHi = ta.highestbars(high, depth) == 0``:
   the bar's high is the highest of the last ``depth`` bars, itself included; ``isLo`` with the lows. Then, in this
   order: ``if isHi``: with the last swing a high (``zdir == 1``) a strictly higher high moves it to this bar (price,
   bar, close), otherwise (``zdir != 1``) a new high is unshifted; ``if isLo``, with the ``zdir`` the high branch may
   just have changed: with the last swing a low a strictly lower low moves it, otherwise a new low is unshifted, but
   only if the newest swing is not on this bar (``pivB.get(0) != bar_index``, L562: a guard on the low side only). So
   the swings alternate strictly; an outside bar is a high only (its low is dropped even when it is lower than the
   current swing low), except when the last swing is a high that this bar does not exceed (then the bar is a new low).
   ``devPct`` 0 makes the size test ``abs(..) >= pivP.get(0) * 0 / 100`` always true (kept literally). The script keeps
   60 swings (L569-572); this port keeps them all (every later read is of the 12 newest; ``n_piv`` is the script's
   count). ``pivC`` is the close of the bar that last set the swing. Only the newest swing can move; it is fixed when
   the next one is added.
2. **The confirmed detection** (L780-795): on a bar where a swing was added and ``pivP.size() >= 12``,
   ``detect(makeQ(1), pivC.get(1))``: the 11 swings before the new one, Q[0] = point D = the swing just fixed, with
   the close of D's bar as ``c0``. Every enabled pattern (all 38, L105-115) is checked in registry order (L525-531);
   the FIRST hit (``hits.get(0)``) is drawn and decides ``bullConf`` / ``bearConf`` and the alert (L793-795, L824-827).
   The overlap gate (L785, ``overlaps`` L767-777) only decides whether the pattern is drawn; the alert fires anyway.
3. **The forming detection** (L798-813), which the script runs on the last bar only (on every tick in real time),
   emulated here at EVERY bar close on the zigzag state after that bar (PREREG 6.7: what a live user sees at that
   close): ``if pivP.size() >= 11``, ``detect(makeQ(0), close)``, Q[0] = the live swing. It can change or vanish on a
   later bar; nothing found later is used.
4. **The plan levels** (``planLevels`` L694-718; inputs L35-41), for every hit with its own id: harmonic (ids 0-21):
   AD = |Q3 - Q0|, entry = Q0 (D), SL = D - dir*0.13*AD, TP1 = D + dir*0.382*AD, TP2 = D + dir*0.618*AD (na when
   AD = 0, ``if ad > 0``); chart (22-37): h = |Q1 - Q2|, entry = Q2 (p2, the neckline), SL = p2 - dir*0.5*h,
   TP1 = p2 + dir*h, TP2 = p2 + dir*1.618*h (na when h = 0). Q3 is used whatever the pattern: for the 5-0 (6 points,
   Q5..Q0 = X A B C D E) it is the pattern's B, not its A. The PRZ (D +- 0.06 AD) is drawn only and not returned.

The predicates (L293-480), transcribed mechanically (``P.get(k)`` -> ``P[..., k]``), strict inequalities kept
-----------------------------------------------------------------------------------------------------------------
* ``inR(bear, A, B, mn, mx, d)`` (L293-294) is ``(A - B) * mn + B < d < (A - B) * mx + B`` when ``bear``, else
  ``B - (B - A) * mx < d < B - (B - A) * mn``, both strict, the bounds computed in exactly that floating-point form.
  It is r = (d - B) / (A - B) in (mn, mx) AND A > B when ``bear``, A < B when not: with the other orientation the
  interval is empty, so the test is always false. Its orientation is the script's, not "fixed".
* Harmonics: ``pcBat`` (L296-297; Bat, ALT Bat, Butterfly, Crab, Gartley, Deep Crab), ``pcShark`` (L299-305),
  ``pcABCD`` (L307-308; 4 points), ``pc50`` (L310-317; 6 points), ``pc3Drives`` (L319-320). Each id calls them with
  its own constants (the generated ``CALLS``, parsed from ``check`` L484-505). Bullish windows are NOT the mirror of
  the bearish ones (e.g. Bat XD 0.3-1.8 bearish, 0.5-2.5 bullish) and are not textbook.
* Chart patterns (L322-480; ids 22-37) read P[1..8] and ``c0`` only, never P[0]; their last conjunct is the breakout
  ``c0 < p2`` (bearish) or ``c0 > p2`` (bullish), and ``c0`` appears nowhere else (``armed`` evaluates the rest).
  Predicates 28-33 (wedges, expanding triangles, pennants) never compare two adjacent swings, so they do not pin which
  swings are highs and also pass with the alternation shifted by one; they are kept literally.
* ``dirOf`` (L117-125), ``ptsOf`` (L128-142): ``DIR``, ``PTS``.

Pine readings chosen where the semantics are not documented
-----------------------------------------------------------
* ``ta.highestbars`` / ``ta.lowestbars`` ties: the NEWEST bar among equal values (PineTS's reading, the spec's
  sources), so a high equal to the window's highest is ``isHi``. ``zigzag(..., tie="oldest")`` gives the alternative
  (an equal earlier value wins) for measurement only. Both are na before bar ``depth - 1`` (``na == 0`` is false).
* ``or`` short-circuits (Pine v6 evaluates ``and`` / ``or`` lazily), so ``pivP.get(0)`` is never read on an empty
  array (L550, L562-563).
* The forming instance: the pattern id plus the bar indexes of its fixed swings Q1..Q(n-1) (the live D excluded). The
  fixed swings cannot change and a key cannot come back once its D is fixed, so an instance lives while its D is the
  live swing; ``first_bar_of_instance`` marks the first bar of the whole history where the key is seen (a key that
  vanishes and reappears while D is still live is the same instance, not a new first bar).

Outputs of ``patterns`` (``n`` = number of bars; bar indexes count from 0 = the first bar given)
-----------------------------------------------------------------------------------------------
* ``swings``: DataFrame, every swing ever added, oldest first, as of the last bar: ``bar``, ``price``,
  ``close_at_set`` (pivC), ``is_high``, ``born_bar`` (the bar on which it was added), ``fixed_bar`` (the bar on which
  the next swing was added and this one stopped moving; -1 for the live one).
* Per bar (arrays of ``n``, the state after the bar's close): ``n_swings`` (swings so far), ``added`` (a swing was
  added on this bar), ``n_piv`` (the script's ``pivP.size()``, capped at 60), ``is_hi`` / ``is_lo`` (the two
  ``ta.*bars == 0`` tests), ``live_bar`` / ``live_price`` (the newest swing; -1 / NaN before the first),
  ``forming_q`` (n x 11, ``makeQ(0)``: the swing prices the forming detection reads, Q[0] = live D; NaN rows while
  ``pivP.size() < 11``) and ``forming_qbar`` (their bar indexes; -1 rows).
* ``confirmed``: DataFrame, one row per hit of every confirmed detection, sorted by (``t_bar``, ``id``):
  ``t_bar`` (the bar at whose close it is known: the bar where the next swing was added), ``id`` (0-37), ``name``,
  ``kind`` ('harmonic' for ids 0-21, 'chart' for 22-37), ``dir`` (+1 bullish, -1 bearish), ``first_hit`` (the first
  hit in registry order: the one drawn and alerted), ``n_hits`` (hits of that detection), ``n_pts`` (``ptsOf``),
  ``c0`` (the close the detection read: pivC[1], the close of D's bar), ``close`` (the close of ``t_bar``), ``p0`` ..
  ``p8`` (Q[k]: the pattern's swing prices, Q0 = D, NaN for k >= n_pts), ``b0`` .. ``b8`` (their bars, -1 beyond),
  ``unit`` (AD for a harmonic, h for a chart pattern), ``entry``, ``sl``, ``tp1``, ``tp2`` (the script's plan for
  that id; NaN when ``unit`` is 0) and ``drawn`` (the first hit passed the overlap gate and is drawn; the alert is not
  gated). The direction of the alert is that of the first hit.
* ``forming``: DataFrame, one row per (bar, hit) of the forming detection at every bar close, the same columns but
  ``drawn`` (``c0`` = ``close`` = that bar's close; ``p0`` / ``b0`` = the live D at that close), plus
  ``instance_key`` (a tuple: id, then the bars of Q1 .. Q(n_pts-1), newest first) and ``first_bar_of_instance``.

Known when: everything in a row with ``t_bar`` = T, and every per-bar value at T, depends on bars 0..T only (the
tests remove the bars after T and compare). Prices are the bid OHLC of the chart timeframe; no volume, no session, no
higher timeframe. Inputs must be finite 1-D float series of equal length (``ValueError`` otherwise).

Facts of the script found while porting (each has a test)
---------------------------------------------------------
* Bear Gartley (id 4) can never fire: with X = 1, A = 0 its XD is xb*(ac + (1 - ac)*bd), whose supremum over the open
  XB, AC and BD windows is 0.618*(0.382 + 0.618*3.618) = 1.61788, below the XD window's lower edge 1.618 (L210-217).
* Bull ALT AB=CD (19) has exactly Bull AB=CD's windows (L258-261 = L266-269): it fires with 18, never as a first hit.
  The bullish and bearish Shark, AB=CD and 5-0 windows are mirror images; the other 8 bear / bull pairs differ.
* An instance in the sense of ``instance_key`` counts every hit's id; the specification's "distinct instances per
  year" (B2) are the distinct keys of the FIRST-hit rows, about 0.63 times as many on our bars.

Checks (``tests/test_tradeiq2_ind_patterns_a.py``; real bars up to 2024-06-30 only)
------------------------------------------------------------------------------------
A hand-computed case for every trap of the specification's risk list; the table regenerated from the source text; the
38 predicates equal to the source's text transliterated at test time (random, exact-boundary and one-ulp sets); a
literal bar-by-bar emulation of the Pine (newest-first lists, unshift / pop at 60, makeQ, detect) equal to this port
on random bars (with and without ties) and on the real daily bars; no look-ahead (truncation); the compiled zigzag
equal to its Python body; the start-offset convergence on the real 1H / 4H bars. After this module was finished, the
20 statistics printed by the specification's unreviewed scratch probe (its ``probe_out.json``; only those numbers
were read: swings, confirmations by family and by first-hit id, multi-id and two-direction shares, chart hits, the
D-to-confirmation delay, the R from D and the close beyond the neckline at the decision close, the forming share,
instances by family, chart instances by direction and live-swing side) were recomputed from this port for bars
closing in 2019-2022: equal on all 6 series and both tie readings, but for one BTC 4H swing on the bar that closes at
2023-01-01 00:00, which the probe counts in 2022 (it selects bars by open time) and this count does not.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

__all__ = [
    "SOURCE_SHA256", "SOURCE_LINES", "NAMES", "RATIOS", "CALLS",
    "DEPTH", "DEV_PCT", "HIST_MAX", "SL_K", "TP1_K", "TP2_K", "CSL_K", "CTP1_K", "CTP2_K", "PLAN_BARS",
    "MAX_SWINGS", "N_Q", "N_IDS", "DIR", "PTS", "KIND", "dir_of", "pts_of",
    "in_r", "pc_bat", "pc_shark", "pc_abcd", "pc_50", "pc_3drives", "pc_double_top", "pc_double_bottom",
    "pc_head_shoulders", "pc_inv_head_shoulders", "pc_triple_top", "pc_triple_bottom", "pc_bear_rising_wedge",
    "pc_bull_rising_wedge", "pc_bear_exp_triangle", "pc_bull_exp_triangle", "pc_bull_pennant", "pc_bear_pennant",
    "pc_bull_falling_wedge_t", "pc_bear_rising_wedge_t", "pc_bull_flag", "pc_bear_flag",
    "check", "detect", "hit_matrix", "armed", "make_q", "plan_levels", "overlaps",
    "zigzag", "patterns", "parse_pine_source", "render_tables",
]

NAN = float("nan")

# ───────────────────────────── the script's inputs at their defaults ─────────────────────────────

DEPTH = 5              # L19 "Depth" (minval 2, maxval 50)
DEV_PCT = 0.0          # L21 "Minimum swing, %": 0 = no filter
HIST_MAX = 15          # L26 confirmed patterns kept on the chart (the overlap gate looks at these)
SL_K, TP1_K, TP2_K = 0.13, 0.382, 0.618          # L35-37 harmonic plan, x AD
PLAN_BARS = 30                                   # L38 the plan horizon (drawn only)
CSL_K, CTP1_K, CTP2_K = 0.5, 1.0, 1.618          # L39-41 chart plan, x h
MAX_SWINGS = 60        # L569: pivP keeps 60 swings
N_Q = 11               # L576: makeQ returns 11 swings
N_IDS = 38
N_PTS_MAX = 9          # the largest ptsOf (wedges and expanding triangles)

# >>> GENERATED: do not edit by hand. `python -B -m backtesting.research.tradeiq2_ind_patterns tables <source>`
# from the owner's copy of "Harmonic & Chart Patterns [AI-AlgoCode]" (third-party code, not in the repository):
# NAMES from L96-103, the 144 ratio constants from L146-289, the dispatch of `check` from L484-521.
SOURCE_SHA256 = "34baf5b07cf3ca46f849cd5439b9ba9af76c7722bcf5837f4da8daea43e3d8e3"
SOURCE_LINES = {"names": (96, 103), "ratios": (146, 289), "check": (484, 521)}
NAMES = (                                       # L96-103, ids 0-37
    "Bear Bat", "Bear ALT Bat", "Bear Butterfly", "Bear Crab",
    "Bear Gartley", "Bear Deep Crab", "Bear Shark", "Bear AB=CD",
    "Bear ALT AB=CD", "Bear 5-0", "Bear Three Drives", "Bull Bat",
    "Bull ALT Bat", "Bull Butterfly", "Bull Crab", "Bull Gartley",
    "Bull Deep Crab", "Bull Shark", "Bull AB=CD", "Bull ALT AB=CD",
    "Bull 5-0", "Bull Three Drives", "Double Top", "Double Bottom",
    "Head & Shoulders", "Inv. Head & Shoulders", "Triple Top", "Triple Bottom",
    "Rising Wedge", "Bull Rising Wedge", "Bear Expanding Triangle", "Bull Expanding Triangle",
    "Bull Pennant", "Bear Pennant", "Bull Falling Wedge", "Bear Rising Wedge",
    "Bull Flag", "Bear Flag",
)
RATIOS = {                                      # L146-289, in the source's order
    "Bearish_Bat_XB_min": 0.382,                # L146
    "Bearish_Bat_XB_max": 0.70,                 # L147
    "Bearish_Bat_AC_min": 0.382,                # L148
    "Bearish_Bat_AC_max": 1.886,                # L149
    "Bearish_Bat_BD_min": 0.618,                # L150
    "Bearish_Bat_BD_max": 2.618,                # L151
    "Bearish_Bat_XD_min": 0.3,                  # L152
    "Bearish_Bat_XD_max": 1.8,                  # L153
    "Bullish_Bat_XB_min": 0.282,                # L154
    "Bullish_Bat_XB_max": 0.70,                 # L155
    "Bullish_Bat_AC_min": 0.282,                # L156
    "Bullish_Bat_AC_max": 1.886,                # L157
    "Bullish_Bat_BD_min": 0.618,                # L158
    "Bullish_Bat_BD_max": 2.618,                # L159
    "Bullish_Bat_XD_min": 0.5,                  # L160
    "Bullish_Bat_XD_max": 2.5,                  # L161
    "Bearish_ALT_Bat_XB_min": 0.182,            # L162
    "Bearish_ALT_Bat_XB_max": 0.50,             # L163
    "Bearish_ALT_Bat_AC_min": 0.282,            # L164
    "Bearish_ALT_Bat_AC_max": 0.986,            # L165
    "Bearish_ALT_Bat_BD_min": 1.0,              # L166
    "Bearish_ALT_Bat_BD_max": 3.168,            # L167
    "Bearish_ALT_Bat_XD_min": 1.0,              # L168
    "Bearish_ALT_Bat_XD_max": 3.0,              # L169
    "Bullish_ALT_Bat_XB_min": 0.182,            # L170
    "Bullish_ALT_Bat_XB_max": 0.50,             # L171
    "Bullish_ALT_Bat_AC_min": 0.282,            # L172
    "Bullish_ALT_Bat_AC_max": 1.386,            # L173
    "Bullish_ALT_Bat_BD_min": 0.618,            # L174
    "Bullish_ALT_Bat_BD_max": 2.018,            # L175
    "Bullish_ALT_Bat_XD_min": 0.2,              # L176
    "Bullish_ALT_Bat_XD_max": 2.5,              # L177
    "Bearish_Butterfly_XB_min": 0.3,            # L178
    "Bearish_Butterfly_XB_max": 0.786,          # L179
    "Bearish_Butterfly_AC_min": 0.182,          # L180
    "Bearish_Butterfly_AC_max": 0.986,          # L181
    "Bearish_Butterfly_BD_min": 1.0,            # L182
    "Bearish_Butterfly_BD_max": 2.24,           # L183
    "Bearish_Butterfly_XD_min": 1.0,            # L184
    "Bearish_Butterfly_XD_max": 2.41,           # L185
    "Bullish_Butterfly_XB_min": 0.382,          # L186
    "Bullish_Butterfly_XB_max": 0.70,           # L187
    "Bullish_Butterfly_AC_min": 0.282,          # L188
    "Bullish_Butterfly_AC_max": 1.886,          # L189
    "Bullish_Butterfly_BD_min": 1.0,            # L190
    "Bullish_Butterfly_BD_max": 2.018,          # L191
    "Bullish_Butterfly_XD_min": 0.2,            # L192
    "Bullish_Butterfly_XD_max": 3.5,            # L193
    "Bearish_Crab_XB_min": 0.282,               # L194
    "Bearish_Crab_XB_max": 0.818,               # L195
    "Bearish_Crab_AC_min": 0.482,               # L196
    "Bearish_Crab_AC_max": 0.986,               # L197
    "Bearish_Crab_BD_min": 1.618,               # L198
    "Bearish_Crab_BD_max": 3.618,               # L199
    "Bearish_Crab_XD_min": 1.118,               # L200
    "Bearish_Crab_XD_max": 3.618,               # L201
    "Bullish_Crab_XB_min": 0.482,               # L202
    "Bullish_Crab_XB_max": 0.80,                # L203
    "Bullish_Crab_AC_min": 0.282,               # L204
    "Bullish_Crab_AC_max": 2.886,               # L205
    "Bullish_Crab_BD_min": 1.5,                 # L206
    "Bullish_Crab_BD_max": 2.5,                 # L207
    "Bullish_Crab_XD_min": 0.2,                 # L208
    "Bullish_Crab_XD_max": 2.5,                 # L209
    "Bearish_Gartley_XB_min": 0.382,            # L210
    "Bearish_Gartley_XB_max": 0.618,            # L211
    "Bearish_Gartley_AC_min": 0.382,            # L212
    "Bearish_Gartley_AC_max": 0.886,            # L213
    "Bearish_Gartley_BD_min": 2.618,            # L214
    "Bearish_Gartley_BD_max": 3.618,            # L215
    "Bearish_Gartley_XD_min": 1.618,            # L216
    "Bearish_Gartley_XD_max": 2.618,            # L217
    "Bullish_Gartley_XB_min": 0.182,            # L218
    "Bullish_Gartley_XB_max": 0.50,             # L219
    "Bullish_Gartley_AC_min": 0.282,            # L220
    "Bullish_Gartley_AC_max": 2.286,            # L221
    "Bullish_Gartley_BD_min": 1.2,              # L222
    "Bullish_Gartley_BD_max": 2.7,              # L223
    "Bullish_Gartley_XD_min": 0.2,              # L224
    "Bullish_Gartley_XD_max": 2.5,              # L225
    "Bearish_Deep_Crab_XB_min": 0.282,          # L226
    "Bearish_Deep_Crab_XB_max": 0.818,          # L227
    "Bearish_Deep_Crab_AC_min": 0.282,          # L228
    "Bearish_Deep_Crab_AC_max": 0.886,          # L229
    "Bearish_Deep_Crab_BD_min": 1.618,          # L230
    "Bearish_Deep_Crab_BD_max": 3.618,          # L231
    "Bearish_Deep_Crab_XD_min": 0.618,          # L232
    "Bearish_Deep_Crab_XD_max": 2.618,          # L233
    "Bullish_Deep_Crab_XB_min": 0.382,          # L234
    "Bullish_Deep_Crab_XB_max": 0.70,           # L235
    "Bullish_Deep_Crab_AC_min": 0.282,          # L236
    "Bullish_Deep_Crab_AC_max": 1.286,          # L237
    "Bullish_Deep_Crab_BD_min": 1.5,            # L238
    "Bullish_Deep_Crab_BD_max": 3.7,            # L239
    "Bullish_Deep_Crab_XD_min": 0.6,            # L240
    "Bullish_Deep_Crab_XD_max": 2.5,            # L241
    "Bearish_Shark_AC_min": 1.0,                # L242
    "Bearish_Shark_AC_max": 3.618,              # L243
    "Bearish_Shark_BD_min": 1.0,                # L244
    "Bearish_Shark_BD_max": 3.24,               # L245
    "Bearish_Shark_XD_min": 0.886,              # L246
    "Bearish_Shark_XD_max": 2.13,               # L247
    "Bullish_Shark_AC_min": 1.0,                # L248
    "Bullish_Shark_AC_max": 3.618,              # L249
    "Bullish_Shark_BD_min": 1.0,                # L250
    "Bullish_Shark_BD_max": 3.24,               # L251
    "Bullish_Shark_XD_min": 0.886,              # L252
    "Bullish_Shark_XD_max": 2.13,               # L253
    "Bearish_Trend_AC_min": 0.382,              # L254
    "Bearish_Trend_AC_max": 0.886,              # L255
    "Bearish_Trend_BD_min": 1.13,               # L256
    "Bearish_Trend_BD_max": 2.618,              # L257
    "Bullish_Trend_AC_min": 0.382,              # L258
    "Bullish_Trend_AC_max": 0.886,              # L259
    "Bullish_Trend_BD_min": 1.13,               # L260
    "Bullish_Trend_BD_max": 2.618,              # L261
    "Bearish_ALT_Trend_AC_min": 0.382,          # L262
    "Bearish_ALT_Trend_AC_max": 0.886,          # L263
    "Bearish_ALT_Trend_BD_min": 1.27,           # L264
    "Bearish_ALT_Trend_BD_max": 1.618,          # L265
    "Bullish_ALT_Trend_AC_min": 0.382,          # L266
    "Bullish_ALT_Trend_AC_max": 0.886,          # L267
    "Bullish_ALT_Trend_BD_min": 1.13,           # L268
    "Bullish_ALT_Trend_BD_max": 2.618,          # L269
    "BullishPattern_AC_min": 1.0,               # L270
    "BullishPattern_AC_max": 3.618,             # L271
    "BullishPattern_BD_min": 1.0,               # L272
    "BullishPattern_BD_max": 3.24,              # L273
    "BullishPattern_CE_min": 0.886,             # L274
    "BullishPattern_CE_max": 2.13,              # L275
    "BearishPattern_AC_min": 1.0,               # L276
    "BearishPattern_AC_max": 3.618,             # L277
    "BearishPattern_BD_min": 1.0,               # L278
    "BearishPattern_BD_max": 3.24,              # L279
    "BearishPattern_CE_min": 0.886,             # L280
    "BearishPattern_CE_max": 2.13,              # L281
    "Bearish_Tree_Drives_AC_min": 1.0,          # L282
    "Bearish_Tree_Drives_AC_max": 2.5,          # L283
    "Bearish_Tree_Drives_BD_min": 1.5,          # L284
    "Bearish_Tree_Drives_BD_max": 3.5,          # L285
    "Bullish_Tree_Drives_AC_min": 1.0,          # L286
    "Bullish_Tree_Drives_AC_max": 1.5,          # L287
    "Bullish_Tree_Drives_BD_min": 1.5,          # L288
    "Bullish_Tree_Drives_BD_max": 2.5,          # L289
}
CALLS = {                                       # the cases of check, L484-521
    0: ("pcBat", True, (                        # L484
        "Bearish_Bat_XB_min", "Bearish_Bat_XB_max",
        "Bearish_Bat_AC_min", "Bearish_Bat_AC_max",
        "Bearish_Bat_BD_min", "Bearish_Bat_BD_max",
        "Bearish_Bat_XD_min", "Bearish_Bat_XD_max",
    )),
    1: ("pcBat", True, (                        # L485
        "Bearish_ALT_Bat_XB_min", "Bearish_ALT_Bat_XB_max",
        "Bearish_ALT_Bat_AC_min", "Bearish_ALT_Bat_AC_max",
        "Bearish_ALT_Bat_BD_min", "Bearish_ALT_Bat_BD_max",
        "Bearish_ALT_Bat_XD_min", "Bearish_ALT_Bat_XD_max",
    )),
    2: ("pcBat", True, (                        # L486
        "Bearish_Butterfly_XB_min", "Bearish_Butterfly_XB_max",
        "Bearish_Butterfly_AC_min", "Bearish_Butterfly_AC_max",
        "Bearish_Butterfly_BD_min", "Bearish_Butterfly_BD_max",
        "Bearish_Butterfly_XD_min", "Bearish_Butterfly_XD_max",
    )),
    3: ("pcBat", True, (                        # L487
        "Bearish_Crab_XB_min", "Bearish_Crab_XB_max",
        "Bearish_Crab_AC_min", "Bearish_Crab_AC_max",
        "Bearish_Crab_BD_min", "Bearish_Crab_BD_max",
        "Bearish_Crab_XD_min", "Bearish_Crab_XD_max",
    )),
    4: ("pcBat", True, (                        # L488
        "Bearish_Gartley_XB_min", "Bearish_Gartley_XB_max",
        "Bearish_Gartley_AC_min", "Bearish_Gartley_AC_max",
        "Bearish_Gartley_BD_min", "Bearish_Gartley_BD_max",
        "Bearish_Gartley_XD_min", "Bearish_Gartley_XD_max",
    )),
    5: ("pcBat", True, (                        # L489
        "Bearish_Deep_Crab_XB_min", "Bearish_Deep_Crab_XB_max",
        "Bearish_Deep_Crab_AC_min", "Bearish_Deep_Crab_AC_max",
        "Bearish_Deep_Crab_BD_min", "Bearish_Deep_Crab_BD_max",
        "Bearish_Deep_Crab_XD_min", "Bearish_Deep_Crab_XD_max",
    )),
    6: ("pcShark", True, (                      # L490
        "Bearish_Shark_AC_min", "Bearish_Shark_AC_max",
        "Bearish_Shark_BD_min", "Bearish_Shark_BD_max",
        "Bearish_Shark_XD_min", "Bearish_Shark_XD_max",
    )),
    7: ("pcABCD", True, (                       # L491
        "Bearish_Trend_AC_min", "Bearish_Trend_AC_max",
        "Bearish_Trend_BD_min", "Bearish_Trend_BD_max",
    )),
    8: ("pcABCD", True, (                       # L492
        "Bearish_ALT_Trend_AC_min", "Bearish_ALT_Trend_AC_max",
        "Bearish_ALT_Trend_BD_min", "Bearish_ALT_Trend_BD_max",
    )),
    9: ("pc50", True, (                         # L493
        "BearishPattern_AC_min", "BearishPattern_AC_max",
        "BearishPattern_BD_min", "BearishPattern_BD_max",
        "BearishPattern_CE_min", "BearishPattern_CE_max",
    )),
    10: ("pc3Drives", True, (                   # L494
        "Bearish_Tree_Drives_AC_min", "Bearish_Tree_Drives_AC_max",
        "Bearish_Tree_Drives_BD_min", "Bearish_Tree_Drives_BD_max",
    )),
    11: ("pcBat", False, (                      # L495
        "Bullish_Bat_XB_min", "Bullish_Bat_XB_max",
        "Bullish_Bat_AC_min", "Bullish_Bat_AC_max",
        "Bullish_Bat_BD_min", "Bullish_Bat_BD_max",
        "Bullish_Bat_XD_min", "Bullish_Bat_XD_max",
    )),
    12: ("pcBat", False, (                      # L496
        "Bullish_ALT_Bat_XB_min", "Bullish_ALT_Bat_XB_max",
        "Bullish_ALT_Bat_AC_min", "Bullish_ALT_Bat_AC_max",
        "Bullish_ALT_Bat_BD_min", "Bullish_ALT_Bat_BD_max",
        "Bullish_ALT_Bat_XD_min", "Bullish_ALT_Bat_XD_max",
    )),
    13: ("pcBat", False, (                      # L497
        "Bullish_Butterfly_XB_min", "Bullish_Butterfly_XB_max",
        "Bullish_Butterfly_AC_min", "Bullish_Butterfly_AC_max",
        "Bullish_Butterfly_BD_min", "Bullish_Butterfly_BD_max",
        "Bullish_Butterfly_XD_min", "Bullish_Butterfly_XD_max",
    )),
    14: ("pcBat", False, (                      # L498
        "Bullish_Crab_XB_min", "Bullish_Crab_XB_max",
        "Bullish_Crab_AC_min", "Bullish_Crab_AC_max",
        "Bullish_Crab_BD_min", "Bullish_Crab_BD_max",
        "Bullish_Crab_XD_min", "Bullish_Crab_XD_max",
    )),
    15: ("pcBat", False, (                      # L499
        "Bullish_Gartley_XB_min", "Bullish_Gartley_XB_max",
        "Bullish_Gartley_AC_min", "Bullish_Gartley_AC_max",
        "Bullish_Gartley_BD_min", "Bullish_Gartley_BD_max",
        "Bullish_Gartley_XD_min", "Bullish_Gartley_XD_max",
    )),
    16: ("pcBat", False, (                      # L500
        "Bullish_Deep_Crab_XB_min", "Bullish_Deep_Crab_XB_max",
        "Bullish_Deep_Crab_AC_min", "Bullish_Deep_Crab_AC_max",
        "Bullish_Deep_Crab_BD_min", "Bullish_Deep_Crab_BD_max",
        "Bullish_Deep_Crab_XD_min", "Bullish_Deep_Crab_XD_max",
    )),
    17: ("pcShark", False, (                    # L501
        "Bullish_Shark_AC_min", "Bullish_Shark_AC_max",
        "Bullish_Shark_BD_min", "Bullish_Shark_BD_max",
        "Bullish_Shark_XD_min", "Bullish_Shark_XD_max",
    )),
    18: ("pcABCD", False, (                     # L502
        "Bullish_Trend_AC_min", "Bullish_Trend_AC_max",
        "Bullish_Trend_BD_min", "Bullish_Trend_BD_max",
    )),
    19: ("pcABCD", False, (                     # L503
        "Bullish_ALT_Trend_AC_min", "Bullish_ALT_Trend_AC_max",
        "Bullish_ALT_Trend_BD_min", "Bullish_ALT_Trend_BD_max",
    )),
    20: ("pc50", False, (                       # L504
        "BullishPattern_AC_min", "BullishPattern_AC_max",
        "BullishPattern_BD_min", "BullishPattern_BD_max",
        "BullishPattern_CE_min", "BullishPattern_CE_max",
    )),
    21: ("pc3Drives", False, (                  # L505
        "Bullish_Tree_Drives_AC_min", "Bullish_Tree_Drives_AC_max",
        "Bullish_Tree_Drives_BD_min", "Bullish_Tree_Drives_BD_max",
    )),
    22: ("pcDoubleTop", None, ()),              # L506
    23: ("pcDoubleBottom", None, ()),           # L507
    24: ("pcHeadShoulders", None, ()),          # L508
    25: ("pcInvHeadShoulders", None, ()),       # L509
    26: ("pcTripleTop", None, ()),              # L510
    27: ("pcTripleBottom", None, ()),           # L511
    28: ("pcBearRisingWedge", None, ()),        # L512
    29: ("pcBullRisingWedge", None, ()),        # L513
    30: ("pcBearExpTriangle", None, ()),        # L514
    31: ("pcBullExpTriangle", None, ()),        # L515
    32: ("pcBullPennant", None, ()),            # L516
    33: ("pcBearPennant", None, ()),            # L517
    34: ("pcBullFallingWedgeT", None, ()),      # L518
    35: ("pcBearRisingWedgeT", None, ()),       # L519
    36: ("pcBullFlag", None, ()),               # L520
    37: ("pcBearFlag", None, ()),               # L521
}
# <<< GENERATED


# ───────────────────────────── the registry (L95-142) ─────────────────────────────

def dir_of(pid: int) -> int:
    """``dirOf`` (L117-125): -1 for ids 0-10 and 22, 24, 26, 28, 30, 33, 35, 37; +1 otherwise."""
    pid = int(pid)
    d = 1
    if pid <= 10:
        d = -1
    elif pid <= 21:
        d = 1
    elif pid in (22, 24, 26, 28, 30, 33, 35, 37):
        d = -1
    return d


def pts_of(pid: int) -> int:
    """``ptsOf`` (L128-142): the number of zigzag points a pattern uses, D included."""
    pid = int(pid)
    n = 5
    if pid in (7, 8, 18, 19):
        n = 4
    elif pid in (9, 20):
        n = 6
    elif pid in (22, 23):
        n = 5
    elif 24 <= pid <= 27:
        n = 7
    elif 28 <= pid <= 31:
        n = 9
    elif pid >= 32:
        n = 8
    return n


DIR = np.array([dir_of(i) for i in range(N_IDS)], np.int64)
PTS = np.array([pts_of(i) for i in range(N_IDS)], np.int64)
KIND = tuple("harmonic" if i <= 21 else "chart" for i in range(N_IDS))


# ───────────────────────────── the predicates (L293-480) ─────────────────────────────
# P: the 11 swings of makeQ, newest first (P[..., 0] = point D); a (..., 11) array evaluates many sets at once.
# The result is a numpy bool (array). `bear` is always a literal of the source (a Python bool).

def in_r(bear: bool, A, B, mn, mx, d):
    """``inR`` (L293-294), literally: ``bear ? (d < (A - B) * mx + B and d > (A - B) * mn + B) : (d < B - (B - A) * mn
    and d > B - (B - A) * mx)``. Strict; false whenever A, B have the other orientation (the interval is empty)."""
    if bear:
        return (d < (A - B) * mx + B) & (d > (A - B) * mn + B)
    return (d < B - (B - A) * mn) & (d > B - (B - A) * mx)


def _p(P, *ks):
    return tuple(P[..., k] for k in ks)


def pc_bat(P, bear, xb0, xb1, ac0, ac1, bd0, bd1, xd0, xd1):
    """``pcBat`` (L296-297): XB, AC, BD and XD windows (Bat, ALT Bat, Butterfly, Crab, Gartley, Deep Crab)."""
    p0, p1, p2, p3, p4 = _p(P, 0, 1, 2, 3, 4)
    return (in_r(bear, p4, p3, xb0, xb1, p2) & in_r(bear, p2, p3, ac0, ac1, p1) & in_r(bear, p2, p1, bd0, bd1, p0)
            & in_r(bear, p4, p3, xd0, xd1, p0))


def pc_shark(P, bear, ac0, ac1, bd0, bd1, xd0, xd1):
    """``pcShark`` (L299-305)."""
    p0, p1, p2, p3, p4 = _p(P, 0, 1, 2, 3, 4)
    if bear:
        return (in_r(False, p3, p2, ac0, ac1, p1) & in_r(True, p2, p1, bd0, bd1, p0)
                & in_r(True, p4, p3, xd0, xd1, p0) & (p4 > p3) & (p4 > p2))
    return (in_r(True, p3, p2, ac0, ac1, p1) & in_r(False, p2, p1, bd0, bd1, p0)
            & in_r(False, p4, p3, xd0, xd1, p0) & (p4 < p3) & (p4 < p2))


def pc_abcd(P, bear, ac0, ac1, bd0, bd1):
    """``pcABCD`` (L307-308): 4 points (AB=CD, ALT AB=CD)."""
    p0, p1, p2, p3 = _p(P, 0, 1, 2, 3)
    return in_r(bear, p2, p3, ac0, ac1, p1) & in_r(bear, p2, p1, bd0, bd1, p0)


def pc_50(P, bear, ac0, ac1, bd0, bd1, ce0, ce1):
    """``pc50`` (L310-317): 6 points; Q5..Q0 = X A B C D E."""
    p0, p1, p2, p3, p4, p5 = _p(P, 0, 1, 2, 3, 4, 5)
    if bear:
        return (in_r(True, p4, p3, ac0, ac1, p2) & in_r(False, p3, p2, bd0, bd1, p1)
                & in_r(True, p2, p1, ce0, ce1, p0) & (p5 < p4) & (p5 < p3))
    return (in_r(False, p4, p3, ac0, ac1, p2) & in_r(True, p3, p2, bd0, bd1, p1)
            & in_r(False, p2, p1, ce0, ce1, p0) & (p5 > p4) & (p5 > p3))


def pc_3drives(P, bear, ac0, ac1, ce0, ce1):
    """``pc3Drives`` (L319-320)."""
    p0, p1, p2, p3, p4 = _p(P, 0, 1, 2, 3, 4)
    return in_r(bear, p4, p3, ac0, ac1, p2) & in_r(bear, p2, p1, ce0, ce1, p0)


def pc_double_top(P, c0):
    """``pcDoubleTop`` (L322-327), id 22."""
    p1, p2, p3, p4 = _p(P, 1, 2, 3, 4)
    return ((p3 - p4) / 2 > p3 - p2) & in_r(True, p3, p2, 0.8, 1.2, p1) & (p4 < p2) & (p2 < p1) & (c0 < p2)


def pc_double_bottom(P, c0):
    """``pcDoubleBottom`` (L329-334), id 23."""
    p1, p2, p3, p4 = _p(P, 1, 2, 3, 4)
    return ((p4 - p3) / 2 > p2 - p3) & in_r(False, p3, p2, 0.8, 1.2, p1) & (p4 > p2) & (p2 > p1) & (c0 > p2)


def pc_head_shoulders(P, c0):
    """``pcHeadShoulders`` (L336-343), id 24."""
    p1, p2, p3, p4, p5, p6 = _p(P, 1, 2, 3, 4, 5, 6)
    return (((p5 - p6) / 2 > p5 - p4) & (p1 < p3) & in_r(True, p5, p4, 1.2, 2.5, p3)
            & in_r(False, p4, p3, 0.8, 1.2, p2) & (c0 < p2))


def pc_inv_head_shoulders(P, c0):
    """``pcInvHeadShoulders`` (L345-352), id 25."""
    p1, p2, p3, p4, p5, p6 = _p(P, 1, 2, 3, 4, 5, 6)
    return (((p6 - p5) / 2 > p4 - p5) & (p1 > p3) & in_r(False, p5, p4, 1.2, 2.5, p3)
            & in_r(True, p4, p3, 0.8, 1.2, p2) & (c0 > p2))


def pc_triple_top(P, c0):
    """``pcTripleTop`` (L354-361), id 26."""
    p1, p2, p3, p4, p5, p6 = _p(P, 1, 2, 3, 4, 5, 6)
    return (((p5 - p6) / 1.5 > p5 - p4) & (p1 < p3) & in_r(True, p5, p4, 0.8, 1.2, p3)
            & in_r(False, p4, p3, 0.8, 1.2, p2) & (c0 < p2))


def pc_triple_bottom(P, c0):
    """``pcTripleBottom`` (L363-370), id 27."""
    p1, p2, p3, p4, p5, p6 = _p(P, 1, 2, 3, 4, 5, 6)
    return (((p6 - p5) / 1.5 > p4 - p5) & (p1 > p3) & in_r(False, p5, p4, 0.8, 1.2, p3)
            & in_r(True, p4, p3, 0.8, 1.2, p2) & (c0 > p2))


def pc_bear_rising_wedge(P, c0):
    """``pcBearRisingWedge`` (L372-381), id 28 (does not pin the alternation)."""
    p1, p2, p3, p4, p5, p6, p7, p8 = _p(P, 1, 2, 3, 4, 5, 6, 7, 8)
    return ((p8 < p6) & (p6 < p4) & (p4 < p2) & (p7 < p5) & (p5 < p3) & (p3 < p1) & (p7 - p6 > p5 - p4)
            & (p5 - p4 > p3 - p2) & (c0 < p2))


def pc_bull_rising_wedge(P, c0):
    """``pcBullRisingWedge`` (L383-392), id 29 (does not pin the alternation)."""
    p1, p2, p3, p4, p5, p6, p7, p8 = _p(P, 1, 2, 3, 4, 5, 6, 7, 8)
    return ((p8 > p6) & (p6 > p4) & (p4 > p2) & (p7 > p5) & (p5 > p3) & (p3 > p1) & (p6 - p7 > p4 - p5)
            & (p4 - p5 > p2 - p3) & (c0 > p2))


def pc_bear_exp_triangle(P, c0):
    """``pcBearExpTriangle`` (L394-403), id 30 (does not pin the alternation)."""
    p1, p2, p3, p4, p5, p6, p7, p8 = _p(P, 1, 2, 3, 4, 5, 6, 7, 8)
    return ((p8 < p6) & (p6 < p4) & (p4 < p2) & (p7 < p5) & (p5 < p3) & (p3 < p1) & (p7 - p6 < p5 - p4)
            & (p5 - p4 < p3 - p2) & (c0 < p2))


def pc_bull_exp_triangle(P, c0):
    """``pcBullExpTriangle`` (L405-414), id 31 (does not pin the alternation)."""
    p1, p2, p3, p4, p5, p6, p7, p8 = _p(P, 1, 2, 3, 4, 5, 6, 7, 8)
    return ((p8 > p6) & (p6 > p4) & (p4 > p2) & (p7 > p5) & (p5 > p3) & (p3 > p1) & (p6 - p7 < p4 - p5)
            & (p4 - p5 < p2 - p3) & (c0 > p2))


def pc_bull_pennant(P, c0):
    """``pcBullPennant`` (L416-424), id 32 (does not pin the alternation)."""
    p1, p2, p3, p4, p5, p6, p7 = _p(P, 1, 2, 3, 4, 5, 6, 7)
    return ((p6 - p7) / 1.2 > p6 - p5) & (p6 > p4) & (p4 > p2) & (p5 < p3) & (p3 < p1) & (c0 > p2)


def pc_bear_pennant(P, c0):
    """``pcBearPennant`` (L426-434), id 33 (does not pin the alternation)."""
    p1, p2, p3, p4, p5, p6, p7 = _p(P, 1, 2, 3, 4, 5, 6, 7)
    return ((p7 - p6) / 1.2 > p5 - p6) & (p6 < p4) & (p4 < p2) & (p5 > p3) & (p3 > p1) & (c0 < p2)


def pc_bull_falling_wedge_t(P, c0):
    """``pcBullFallingWedgeT`` (L436-444), id 34."""
    p1, p2, p3, p4, p5, p6, p7 = _p(P, 1, 2, 3, 4, 5, 6, 7)
    return (((p6 - p7) / 1.2 > p6 - p5) & (p6 > p5) & (p2 > p5) & (p6 > p4) & (p4 > p2) & (p5 > p3) & (p3 > p1)
            & ((p6 - p5) / 1.7 > p2 - p1) & (c0 > p2))


def pc_bear_rising_wedge_t(P, c0):
    """``pcBearRisingWedgeT`` (L446-454), id 35."""
    p1, p2, p3, p4, p5, p6, p7 = _p(P, 1, 2, 3, 4, 5, 6, 7)
    return (((p7 - p6) / 1.2 > p5 - p6) & (p6 < p5) & (p2 < p5) & (p6 < p4) & (p4 < p2) & (p5 < p3) & (p3 < p1)
            & ((p5 - p6) / 1.7 > p1 - p2) & (c0 < p2))


def pc_bull_flag(P, c0):
    """``pcBullFlag`` (L456-467), id 36."""
    p1, p2, p3, p4, p5, p6, p7 = _p(P, 1, 2, 3, 4, 5, 6, 7)
    max_p = (p6 - p5) * 1.2
    min_p = (p6 - p5) * 0.8
    pp = p2 - p1
    return (((p6 - p7) / 1.2 > p6 - p5) & (p6 > p5) & (p2 > p5) & (p6 > p4) & (p4 > p2) & (p5 > p3) & (p3 > p1)
            & (pp < max_p) & (pp > min_p) & (c0 > p2))


def pc_bear_flag(P, c0):
    """``pcBearFlag`` (L469-480), id 37."""
    p1, p2, p3, p4, p5, p6, p7 = _p(P, 1, 2, 3, 4, 5, 6, 7)
    max_p = (p5 - p6) * 1.2
    min_p = (p5 - p6) * 0.8
    pp = p1 - p2
    return (((p7 - p6) / 1.2 > p5 - p6) & (p6 < p5) & (p2 < p5) & (p6 < p4) & (p4 < p2) & (p5 < p3) & (p3 < p1)
            & (pp < max_p) & (pp > min_p) & (c0 < p2))


# the Pine function names of `check` (L484-521) -> the ports above
_PINE_FUNCS = {
    "pcBat": pc_bat, "pcShark": pc_shark, "pcABCD": pc_abcd, "pc50": pc_50, "pc3Drives": pc_3drives,
    "pcDoubleTop": pc_double_top, "pcDoubleBottom": pc_double_bottom, "pcHeadShoulders": pc_head_shoulders,
    "pcInvHeadShoulders": pc_inv_head_shoulders, "pcTripleTop": pc_triple_top, "pcTripleBottom": pc_triple_bottom,
    "pcBearRisingWedge": pc_bear_rising_wedge, "pcBullRisingWedge": pc_bull_rising_wedge,
    "pcBearExpTriangle": pc_bear_exp_triangle, "pcBullExpTriangle": pc_bull_exp_triangle,
    "pcBullPennant": pc_bull_pennant, "pcBearPennant": pc_bear_pennant,
    "pcBullFallingWedgeT": pc_bull_falling_wedge_t, "pcBearRisingWedgeT": pc_bear_rising_wedge_t,
    "pcBullFlag": pc_bull_flag, "pcBearFlag": pc_bear_flag,
}


def _dispatch():
    """id -> (function, bear or None, the constants' values), from the generated CALLS and RATIOS."""
    out = []
    for pid in range(N_IDS):
        fname, bear, keys = CALLS[pid]
        out.append((_PINE_FUNCS[fname], bear, tuple(float(RATIOS[k]) for k in keys)))
    return tuple(out)


_DISPATCH = _dispatch()


def _q_array(P) -> np.ndarray:
    q = np.asarray(P, dtype=np.float64)
    if q.shape[-1:] != (N_Q,):
        raise ValueError(f"P: the 11 swings of makeQ are expected on the last axis, got shape {q.shape}")
    return q


def check(pid: int, P, c0):
    """``check(id, P, c0)`` (L482-522): the predicate of pattern ``pid`` on the swings P (makeQ order, P[..., 0] = D)
    with the close ``c0`` (read by the chart patterns only). Scalars or arrays (``P`` (..., 11), ``c0`` broadcast)."""
    pid = int(pid)
    if not 0 <= pid < N_IDS:
        return False                                                  # L522: `=> false`
    fn, bear, args = _DISPATCH[pid]
    q = _q_array(P)
    if bear is None:
        return fn(q, np.asarray(c0, dtype=np.float64))
    return fn(q, bear, *args)


def hit_matrix(Q, c0) -> np.ndarray:
    """``check`` of every id on many swing sets: a (m, 38) bool array for Q (m, 11) and c0 (m,)."""
    q = _q_array(Q)
    if q.ndim != 2:
        raise ValueError("hit_matrix: Q must be (m, 11)")
    c = np.broadcast_to(np.asarray(c0, dtype=np.float64), (q.shape[0],))
    out = np.zeros((q.shape[0], N_IDS), dtype=bool)
    for pid in range(N_IDS):
        out[:, pid] = check(pid, q, c)
    return out


def detect(Q, c0) -> List[int]:
    """``detect(Q, c0)`` (L525-531) on one swing set: every id whose predicate holds, in registry order (all 38 are
    enabled at the defaults, L105-115). ``hits[0]`` is the one the script draws and alerts."""
    q = _q_array(Q)
    if q.ndim != 1:
        raise ValueError("detect: one swing set of 11 values is expected (use hit_matrix for many)")
    return [pid for pid in range(N_IDS) if bool(check(pid, q, c0))]


def armed(pid: int, P):
    """A chart pattern's predicate without its breakout conjunct (for HP-CS: "every condition except the close"):
    ``check`` with c0 = +inf for a bullish id (``c0 > p2`` holds) and -inf for a bearish one (``c0 < p2`` holds);
    c0 is read nowhere else in L322-480."""
    pid = int(pid)
    if not 22 <= pid < N_IDS:
        raise ValueError(f"armed: chart pattern ids are 22-37, got {pid}")
    return check(pid, P, np.inf if DIR[pid] > 0 else -np.inf)


def make_q(piv_newest_first, s: int) -> np.ndarray:
    """``makeQ(s)`` (L575-580) literally: ``q[k] = pivP.get(math.min(s + k, n - 1))`` for k = 0..10, ``n`` the number
    of swings (newest first). With the script's guards (>= 12 swings for s = 1, >= 11 for s = 0) the clamp never
    binds; it does with fewer swings."""
    p = np.asarray(piv_newest_first, dtype=np.float64)
    n = len(p)
    if n == 0:
        raise ValueError("makeQ on an empty swing list reads pivP.get(-1): a runtime error in Pine")
    return np.array([p[min(int(s) + k, n - 1)] for k in range(N_Q)], dtype=np.float64)


def plan_levels(pid, Q):
    """``planLevels(id, Q)`` (L694-718) without the PRZ: ``(unit, entry, sl, tp1, tp2)``, unit = AD = |Q3 - Q0| for a
    harmonic (ids 0-21), h = |Q1 - Q2| for a chart pattern; NaN levels when the unit is not > 0. The arithmetic is the
    script's: ``Q0 - dir * slK * ad`` evaluated left to right. ``pid`` and ``Q`` may be arrays ((m,), (m, 11))."""
    ids = np.asarray(pid, dtype=np.int64)
    q = _q_array(Q)
    d = DIR[ids].astype(np.float64)
    harm = ids <= 21
    ad = np.abs(q[..., 3] - q[..., 0])
    h = np.abs(q[..., 1] - q[..., 2])
    unit = np.where(harm, ad, h)
    base = np.where(harm, q[..., 0], q[..., 2])
    ksl = np.where(harm, SL_K, CSL_K)
    k1 = np.where(harm, TP1_K, CTP1_K)
    k2 = np.where(harm, TP2_K, CTP2_K)
    ok = unit > 0
    with np.errstate(invalid="ignore"):
        entry = np.where(ok, base, NAN)
        sl = np.where(ok, base - d * ksl * unit, NAN)
        tp1 = np.where(ok, base + d * k1 * unit, NAN)
        tp2 = np.where(ok, base + d * k2 * unit, NAN)
    if np.ndim(unit) == 0:
        return float(unit), float(entry), float(sl), float(tp1), float(tp2)
    return unit, entry, sl, tp1, tp2


def overlaps(drawn: Sequence[Tuple[int, int]], a: int, b: int) -> bool:
    """``overlaps(a, b)`` (L767-777) against the drawn patterns (first bar, D's bar): the overlap of [a, b] and
    [pa, pb] is more than half of the shorter one. Drawing only: the alert is not gated (L785 vs L793-795)."""
    hit = False
    for pa, pb in drawn:
        lo = max(a, pa)
        hi = min(b, pb)
        ln = min(b - a, pb - pa)
        if hi > lo and ln > 0 and float(hi - lo) / ln > 0.5:
            hit = True
    return hit


# ───────────────────────────── the zigzag (L535-572) ─────────────────────────────

@njit(cache=True)
def _zigzag_kernel(h, l, c, depth, dev_pct, newest):
    """One pass of L540-572 over every bar. Swings are kept oldest first, all of them (the script pops the 61st,
    L569-572, which no later read can see). ``newest``: the tie rule of ta.highestbars / ta.lowestbars."""
    n = h.shape[0]
    sp = np.empty(n, np.float64)          # pivP (chronological here)
    sb = np.empty(n, np.int64)            # pivB
    sc = np.empty(n, np.float64)          # pivC: the close of the bar that last set the swing
    shi = np.zeros(n, np.bool_)           # the swing is a high
    sborn = np.empty(n, np.int64)         # the bar on which it was added
    is_hi = np.zeros(n, np.bool_)
    is_lo = np.zeros(n, np.bool_)
    added = np.zeros(n, np.bool_)
    count = np.zeros(n, np.int64)
    live_p = np.full(n, np.nan)
    live_b = np.full(n, -1, np.int64)
    cnt = 0
    zdir = 0                               # L538: 1 = the last swing is a high, -1 = a low
    for t in range(n):
        # L541-542: ta.highestbars(high, depth) == 0, ta.lowestbars(low, depth) == 0; na before bar depth - 1
        hi = False
        lo = False
        if t >= depth - 1:
            hi = True
            lo = True
            ht = h[t]
            lt = l[t]
            for j in range(t - depth + 1, t):
                if newest:                 # the newest of equal values wins: an equal earlier value does not block
                    if h[j] > ht:
                        hi = False
                    if l[j] < lt:
                        lo = False
                else:                      # the oldest wins: an equal earlier value takes the offset
                    if h[j] >= ht:
                        hi = False
                    if l[j] <= lt:
                        lo = False
        is_hi[t] = hi
        is_lo[t] = lo
        add = False
        if hi:                                                        # L544-555
            if zdir == 1:
                if h[t] > sp[cnt - 1]:
                    sp[cnt - 1] = h[t]
                    sb[cnt - 1] = t
                    sc[cnt - 1] = c[t]
            elif cnt == 0 or abs(h[t] - sp[cnt - 1]) >= sp[cnt - 1] * dev_pct / 100.0:
                sp[cnt] = h[t]
                sb[cnt] = t
                sc[cnt] = c[t]
                shi[cnt] = True
                sborn[cnt] = t
                cnt += 1
                zdir = 1
                add = True
        if lo:                                                        # L556-568, with the zdir set just above
            if zdir == -1:
                if l[t] < sp[cnt - 1]:
                    sp[cnt - 1] = l[t]
                    sb[cnt - 1] = t
                    sc[cnt - 1] = c[t]
            elif cnt == 0 or sb[cnt - 1] != t:                         # the guard of the low side only
                if cnt == 0 or abs(sp[cnt - 1] - l[t]) >= sp[cnt - 1] * dev_pct / 100.0:
                    sp[cnt] = l[t]
                    sb[cnt] = t
                    sc[cnt] = c[t]
                    shi[cnt] = False
                    sborn[cnt] = t
                    cnt += 1
                    zdir = -1
                    add = True
        added[t] = add
        count[t] = cnt
        if cnt > 0:
            live_p[t] = sp[cnt - 1]
            live_b[t] = sb[cnt - 1]
    return (sp[:cnt].copy(), sb[:cnt].copy(), sc[:cnt].copy(), shi[:cnt].copy(), sborn[:cnt].copy(),
            is_hi, is_lo, added, count, live_p, live_b)


def _series(x, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)                 # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    if not np.isfinite(a).all():
        raise ValueError(f"{name}: na or inf at bar {int(np.argmax(~np.isfinite(a)))}; the bars must be complete")
    return a


def _depth(depth) -> int:
    if isinstance(depth, (bool, np.bool_)) or float(depth) != int(depth) or not 2 <= int(depth) <= 50:
        raise ValueError(f"depth: an integer in [2, 50] is expected (the input's minval / maxval), got {depth!r}")
    return int(depth)


def zigzag(h, l, c, depth: int = DEPTH, tie: str = "newest", dev_pct: float = DEV_PCT) -> Dict[str, np.ndarray]:
    """The zigzag of L535-572 on every bar. ``tie``: "newest" (the reading of this port) or "oldest" (for measuring
    the alternative only). ``dev_pct`` other than 0 is the script's minimum-swing filter (not used by the study).

    Returns the swing arrays (oldest first, as of the last bar): ``sw_price``, ``sw_bar``, ``sw_close``,
    ``sw_is_high``, ``sw_born``, ``sw_fixed``; and per bar: ``is_hi``, ``is_lo``, ``added``, ``n_swings``, ``n_piv``,
    ``live_price``, ``live_bar``."""
    hh, ll, cc = _series(h, "high"), _series(l, "low"), _series(c, "close")
    if not len(hh) == len(ll) == len(cc):
        raise ValueError("high, low, close: series of equal length are expected")
    if tie not in ("newest", "oldest"):
        raise ValueError(f"tie: 'newest' or 'oldest', got {tie!r}")
    sp, sb, sc, shi, sborn, is_hi, is_lo, added, count, live_p, live_b = _zigzag_kernel(
        hh, ll, cc, _depth(depth), float(dev_pct), tie == "newest")
    fixed = np.full(len(sp), -1, np.int64)
    fixed[:-1] = sborn[1:]
    return {"sw_price": sp, "sw_bar": sb, "sw_close": sc, "sw_is_high": shi, "sw_born": sborn, "sw_fixed": fixed,
            "is_hi": is_hi, "is_lo": is_lo, "added": added, "n_swings": count,
            "n_piv": np.minimum(count, MAX_SWINGS), "live_price": live_p, "live_bar": live_b}


def _gather(z: Dict[str, np.ndarray], rows: np.ndarray, s: int) -> Tuple[np.ndarray, np.ndarray]:
    """makeQ(s) (with its clamp) after each bar of ``rows``: prices and bars, newest first. Index 0 of pivP is the
    live swing (its value at that bar); every older one is fixed, so its final value is its value at that bar."""
    cnt = z["n_swings"][rows]
    npiv = np.minimum(cnt, MAX_SWINGS)
    idx = np.minimum(int(s) + np.arange(N_Q)[None, :], npiv[:, None] - 1)       # L579: math.min(s + k, n - 1)
    chrono = cnt[:, None] - 1 - idx
    q = z["sw_price"][chrono]
    qb = z["sw_bar"][chrono]
    live = idx == 0
    q = np.where(live, z["live_price"][rows][:, None], q)
    qb = np.where(live, z["live_bar"][rows][:, None], qb)
    return q, qb


_COLS_P = tuple(f"p{k}" for k in range(N_PTS_MAX))
_COLS_B = tuple(f"b{k}" for k in range(N_PTS_MAX))


def _rows(t_bar: np.ndarray, Q: np.ndarray, QB: np.ndarray, c0: np.ndarray, close: np.ndarray) -> pd.DataFrame:
    """One row per hit of the detections given (one per row of Q), sorted by (t_bar, id)."""
    H = hit_matrix(Q, c0) if len(Q) else np.zeros((0, N_IDS), bool)
    r, ids = np.nonzero(H)
    n_hits = H.sum(axis=1)
    first = np.argmax(H, axis=1)
    npts = PTS[ids]
    k = np.arange(N_PTS_MAX)
    inside = k[None, :] < npts[:, None]
    P = np.where(inside, Q[r][:, :N_PTS_MAX], NAN)
    B = np.where(inside, QB[r][:, :N_PTS_MAX], -1)
    unit, entry, sl, tp1, tp2 = plan_levels(ids, Q[r]) if len(r) else (np.zeros(0),) * 5
    cols = {"t_bar": t_bar[r].astype(np.int64), "id": ids.astype(np.int64),
            "name": np.array([NAMES[i] for i in ids], dtype=object),
            "kind": np.array([KIND[i] for i in ids], dtype=object),
            "dir": DIR[ids].astype(np.int64), "first_hit": ids == first[r], "n_hits": n_hits[r].astype(np.int64),
            "n_pts": npts.astype(np.int64), "c0": c0[r].astype(np.float64), "close": close[r].astype(np.float64)}
    for j in range(N_PTS_MAX):
        cols[_COLS_P[j]] = P[:, j]
    for j in range(N_PTS_MAX):
        cols[_COLS_B[j]] = B[:, j].astype(np.int64)
    cols.update(unit=np.asarray(unit, np.float64), entry=np.asarray(entry, np.float64),
                sl=np.asarray(sl, np.float64), tp1=np.asarray(tp1, np.float64), tp2=np.asarray(tp2, np.float64))
    return pd.DataFrame(cols)


def _drawn(conf: pd.DataFrame) -> np.ndarray:
    """L785-792: a confirmed first hit is drawn unless it overlaps one of the (at most HIST_MAX) drawn patterns; the
    drawn list keeps the newest HIST_MAX. Only the first hit of a detection is ever a candidate."""
    out = np.zeros(len(conf), dtype=bool)
    drawn: List[Tuple[int, int]] = []
    fh = np.flatnonzero(conf["first_hit"].to_numpy())
    bars = conf[list(_COLS_B)].to_numpy()
    npts = conf["n_pts"].to_numpy()
    for i in fh:
        a, b = int(bars[i, npts[i] - 1]), int(bars[i, 0])          # p.xs: oldest point first, last = D
        if not overlaps(drawn, a, b):
            out[i] = True
            drawn.append((a, b))
            if len(drawn) > HIST_MAX:
                drawn.pop(0)
    return out


def patterns(h, l, c, depth: int = DEPTH) -> Dict[str, object]:
    """The script on every bar (see the module docstring for every key and column): the zigzag, the confirmed
    detections (L780-795) and the forming detection at every bar close (L798-813), with the plan levels."""
    z = zigzag(h, l, c, depth)
    cc = np.array(c, dtype=np.float64)
    n = len(cc)
    cnt = z["n_swings"]
    sw = pd.DataFrame({"bar": z["sw_bar"], "price": z["sw_price"], "close_at_set": z["sw_close"],
                       "is_high": z["sw_is_high"], "born_bar": z["sw_born"], "fixed_bar": z["sw_fixed"]})

    # the forming detection at every close: makeQ(0), c0 = close, while pivP.size() >= 11 (L807-808)
    frows = np.flatnonzero(np.minimum(cnt, MAX_SWINGS) >= 11)
    fq = np.full((n, N_Q), NAN)
    fqb = np.full((n, N_Q), -1, np.int64)
    if len(frows):
        q, qb = _gather(z, frows, 0)
        fq[frows], fqb[frows] = q, qb
    forming = _rows(frows, fq[frows], fqb[frows], cc[frows], cc[frows])
    if len(forming):
        bcols = forming[list(_COLS_B)].to_numpy()
        keys = [(int(i),) + tuple(int(x) for x in bb[1:m]) for i, bb, m in
                zip(forming["id"].to_numpy(), bcols, forming["n_pts"].to_numpy())]
    else:
        keys = []
    forming["instance_key"] = pd.Series(keys, dtype=object)
    forming["first_bar_of_instance"] = ~forming["instance_key"].duplicated(keep="first").to_numpy(bool)

    # the confirmed detection: a swing added on this bar and pivP.size() >= 12; makeQ(1), c0 = pivC.get(1) (L780-781)
    crows = np.flatnonzero(z["added"] & (np.minimum(cnt, MAX_SWINGS) >= 12))
    if len(crows):
        cq, cqb = _gather(z, crows, 1)
        c0 = z["sw_close"][cnt[crows] - 2]
    else:
        cq, cqb, c0 = np.zeros((0, N_Q)), np.zeros((0, N_Q), np.int64), np.zeros(0)
    confirmed = _rows(crows, cq, cqb, c0, cc[crows])
    confirmed["drawn"] = _drawn(confirmed)

    return {"swings": sw, "n_swings": cnt, "added": z["added"], "n_piv": z["n_piv"], "is_hi": z["is_hi"],
            "is_lo": z["is_lo"], "live_bar": z["live_bar"], "live_price": z["live_price"],
            "forming_q": fq, "forming_qbar": fqb, "confirmed": confirmed, "forming": forming}


# ───────────────────────────── the generator of the table (from the source text) ─────────────────────────────

_RE_RATIO = re.compile(r"^([A-Za-z_]\w*) = ([0-9]+(?:\.[0-9]+)?)$")
_RE_CASE_HARM = re.compile(r"^\s+(\d+) => (\w+)\(P, (true|false), ([A-Za-z_0-9, ]+)\)$")
_RE_CASE_CHART = re.compile(r"^\s+(\d+) => (\w+)\(P, c0\)$")


def parse_pine_source(text: str) -> Dict[str, object]:
    """The registry names (``NAMES = array.from(...)``), the ratio constants (every line of the region "Ratios",
    in order) and the dispatch of ``check`` (its ``switch``), read from the script's text with strict patterns: any
    line in those regions that does not match raises ``ValueError``. Returns ``names`` (38 strings), ``ratios`` (name
    -> (source text of the value, line)), ``calls`` (id -> (function, bear or None, constant names, line)),
    ``lines`` (the line ranges) and ``sha256`` of the text."""
    lines = text.split("\n")
    out: Dict[str, object] = {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}

    # NAMES (L96-103)
    i0 = next(i for i, s in enumerate(lines) if s.startswith("var array<string> NAMES = array.from("))
    i1 = i0
    while not lines[i1].rstrip().endswith(")"):
        i1 += 1
    names = re.findall(r'"([^"]*)"', "\n".join(lines[i0:i1 + 1]))
    if len(names) != N_IDS:
        raise ValueError(f"NAMES: {len(names)} names, 38 expected")
    out["names"] = tuple(names)

    # the ratio constants (L146-289)
    r0 = next(i for i, s in enumerate(lines) if s.startswith("//#region") and "Ratios" in s)
    r1 = next(i for i in range(r0 + 1, len(lines)) if lines[i].startswith("//#endregion"))
    ratios: Dict[str, Tuple[str, int]] = {}
    for i in range(r0 + 1, r1):
        m = _RE_RATIO.match(lines[i])
        if not m:
            raise ValueError(f"line {i + 1}: not a ratio constant: {lines[i]!r}")
        if m.group(1) in ratios:
            raise ValueError(f"line {i + 1}: {m.group(1)} defined twice")
        ratios[m.group(1)] = (m.group(2), i + 1)

    # the dispatch of check (L482-522)
    k0 = next(i for i, s in enumerate(lines) if s.startswith("check(int id, array<float> P, float c0) =>"))
    if lines[k0 + 1].strip() != "switch id":
        raise ValueError(f"line {k0 + 2}: `switch id` expected")
    calls: Dict[int, Tuple[str, Optional[bool], Tuple[str, ...], int]] = {}
    i = k0 + 2
    while lines[i].strip() != "=> false":
        s = lines[i]
        m = _RE_CASE_HARM.match(s)
        if m:
            keys = tuple(x.strip() for x in m.group(4).split(","))
            missing = [k for k in keys if k not in ratios]
            if missing:
                raise ValueError(f"line {i + 1}: unknown constants {missing}")
            calls[int(m.group(1))] = (m.group(2), m.group(3) == "true", keys, i + 1)
        else:
            m = _RE_CASE_CHART.match(s)
            if not m:
                raise ValueError(f"line {i + 1}: not a case of check: {s!r}")
            calls[int(m.group(1))] = (m.group(2), None, (), i + 1)
        i += 1
    if sorted(calls) != list(range(N_IDS)):
        raise ValueError(f"check: cases {sorted(calls)}, 0-37 expected")
    used = {k for v in calls.values() for k in v[2]}
    if used != set(ratios):
        raise ValueError(f"constants never used by check: {sorted(set(ratios) - used)}")
    out["ratios"] = ratios
    out["calls"] = calls
    out["lines"] = {"names": (i0 + 1, i1 + 1), "ratios": (r0 + 2, r1), "check": (k0 + 3, i)}
    return out


def render_tables(parsed: Dict[str, object]) -> str:
    """The Python source of the generated block of this module (between its GENERATED markers)."""
    ln = parsed["lines"]
    w = []
    w.append(f'SOURCE_SHA256 = "{parsed["sha256"]}"')
    w.append("SOURCE_LINES = {" + ", ".join(f'"{k}": ({a}, {b})' for k, (a, b) in ln.items()) + "}")
    w.append("NAMES = (".ljust(48) + f"# L{ln['names'][0]}-{ln['names'][1]}, ids 0-37")
    names = parsed["names"]
    for j in range(0, len(names), 4):
        w.append("    " + " ".join(f'"{x}",' for x in names[j:j + 4]))
    w.append(")")
    w.append("RATIOS = {".ljust(48) + f"# L{ln['ratios'][0]}-{ln['ratios'][1]}, in the source's order")
    for k, (txt, i) in parsed["ratios"].items():
        w.append(f'    "{k}": {txt},'.ljust(48) + f"# L{i}")
    w.append("}")
    w.append("CALLS = {".ljust(48) + f"# the cases of check, L{ln['check'][0]}-{ln['check'][1]}")
    for pid, (fn, bear, keys, i) in sorted(parsed["calls"].items()):
        if bear is None:
            w.append(f'    {pid}: ("{fn}", None, ()),'.ljust(48) + f"# L{i}")
        else:
            w.append(f'    {pid}: ("{fn}", {bear}, ('.ljust(48) + f"# L{i}")
            for j in range(0, len(keys), 2):
                w.append("        " + " ".join(f'"{x}",' for x in keys[j:j + 2]))
            w.append("    )),")
    w.append("}")
    return "\n".join(w)


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -B -m backtesting.research.tradeiq2_ind_patterns")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tables", help="print the generated block of this module from the Pine source text")
    t.add_argument("source", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "tables":
        print(render_tables(parse_pine_source(a.source.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main(sys.argv[1:])
