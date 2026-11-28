"""
"Wyckoff [theUltimator5]" (Pine v6, 3,199 lines): the script's engine ``f_engine`` on the chart timeframe, port A,
the production port of study 2 (``backtest_results/tradeiq_2027/PREREG.md`` section 6.3).

    from backtesting.research import tradeiq2_ind_wyckoff as W
    out = W.wyckoff(b.o, b.h, b.l, b.c, vol, b.t)                    # a dict of per-bar arrays (CONTRACT_KEYS)
    out = W.wyckoff(b.o, b.h, b.l, b.c, vol, b.t, mintick=mk.tick)   # the symbol's syminfo.mintick (see below)

Line numbers ``(Lnnnn)`` are those of the owner's copy of the source (the study's scratch ``src/Wyckoff Indicator
Code.txt``). The copy is third-party code and is not in the repository. The specification is the study's scratch map
``maps/wyckoff.md``. Port B (``tests/tradeiq2_oracle_wyckoff.py``) is written by another engineer from the same
sources, independently; this module was written without reading it.

Checks (``tests/test_tradeiq2_ind_wyckoff_a.py``; real bars up to 2024-06-30 only): a hand-computed case for every
trap of the specification's risk list; no look-ahead (truncation); the mirror of negated prices; the compiled kernel
equal to its plain Python body (and, with ``NUMBA_DISABLE_JIT=1``, to pure CPython on the real 4H bars); every
cross-check vector of the specification reproduced (the Standard entries of gold 1H / 4H and BTC 4H, their counts,
the climax and excursion counts, the stop geometry, the start-invariance). After this module was finished, the
specification's unreviewed scratch port was run on the same bars as a count check only: 28 counters (every event
bit, seeds, resets by reason, demotions, provisional excursions, entries per mode and side) agree on all 12 series
(gold tick and no volume, BTC Binance and tick volume, 1H / 4H / 1D), over the whole history and over 2019-2022.

Reconciliation with port B (``tests/test_tradeiq2_ind_wyckoff.py``; the study's ``porting/wyckoff.md``): on the real
bars of both symbols from the study's data start (gold 2016-01-03, BTC 2018-01-01) to 2024-06-30, 1H / 4H / 1D, gold
on tick volume and without volume, BTC on Binance and on Exness tick volume, every output below is identical to port
B's, floats bit for bit, and so are the engine's internal series (the bar measurements, the trend score, the pivot
length, the pivots, the reset codes, the maturity, the alert bits). The one change it made here: the campaign id is
now the seed bar (``s.startBar``), port B's convention, in place of a counter. Each bar of the 28 counters above
also falls on the same bar as in the scratch port (all 12 series, the whole span).

What it computes
----------------
One pass of ``f_engine(true)`` (L1060-1764) from the first bar given (``bar_index`` 0), every input at the script's
default (``entryStrictness`` "Standard", ATR-adaptive swings). Each bar runs the state machine in the order of
L1162-1747: retire (L1182-1234), climax seed (L1254-1275), absorption (L1278-1290), the AR (L1292-1311), the pivot
events (terminal test, A to B, Phase B tests and the opposite edge, traversals, the test after a spring, the LPS;
L1313-1529), the spring / UTAD probe (L1531-1610), the SOS (L1613-1641), B to D or departure (L1643-1676), the late SOS
(L1678-1693), Phase E (L1696-1727) and the entry check (L1729-1747). The three entry modes come from the same pass:
``s.entryTime`` (the one-entry-per-campaign slot) is read only by the entry check itself (L1729), so three slots, each
cleared with the campaign (``WS.new()``) and kept by a demotion, give exactly what three runs of the script would.

Not ported, because no output depends on them: the preliminary support / supply (L1237-1252, L1272-1275; it feeds the
label and the BIT_PS bit, which no alert reads), the campaign context ``ctxBull`` / ``ctxBear`` and ``regimeBar``
(type and display only), the pivot triplets, scores, times and prices kept only for labels, the higher-timeframe scan
(L1766-1770, L1897-2008: display and stored labels only; the alerts are chart-timeframe only) and every drawing.

Outputs (``wyckoff``; arrays of ``len(c)``; the state at each bar's close)
-------------------------------------------------------------------------
* ``phase`` int8 (0 none, 1 A, 2 B, 3 C, 4 D, 5 E), ``outcome`` int8 (+1 accumulation, -1 distribution, 0 none),
  ``campaign`` int32: the campaign's id, the bar index (from 0, the first bar given) of the climax that seeded it, the
  script's own ``s.startBar`` (L734); -1 while there is none. Every seed, re-seeds included, is a new ``WS`` on its
  own bar (at most one seed per bar, L1265), so the id is unique; starting the bars k bars later lowers every id by
  k. (Port A first numbered campaigns 0, 1, 2, ...; the reconciliation with port B adopted ``s.startBar``.)
* ``range_lo`` / ``range_hi``: ``s.rangeLow`` / ``s.rangeHigh``. ``hard_lo`` / ``hard_hi``: the script's own
  ``f_hardLevel`` (L723-729), the level its invalidation tests (L1199-1215): for a long the spring's extreme when the
  campaign holds an accumulation outcome from a spring, otherwise ``min(origLow, rangeLow)``; for a short the UTAD's
  extreme, otherwise ``max(origHigh, rangeHigh)``. On a selling-climax campaign ``rangeLow`` (the robust edge of the
  secondary tests, L690-698) is never below ``origLow`` (the climax low), so the hard level of a long without a spring
  is the climax low, not the robust edge. NaN where the script has na.
* Event bits (bool): ``ev_sc``, ``ev_bc``, ``ev_ar``, ``ev_st``, ``ev_spring``, ``ev_utad``, ``ev_test``,
  ``ev_ctest``, ``ev_sos``, ``ev_sow``, ``ev_lps``, ``ev_lpsy``, ``ev_phase_e``: the bits of ``sig`` (``cMask``, the
  alerts L3188-3197) on the bar whose close makes the event known. The labels are drawn earlier: an ST, test, CTest
  or LPS at its pivot, ``pLen`` bars back; a spring at its extreme; the climax at the climax bar.
* ``climax`` int8 / ``climax_px``: +1 on the bar a selling climax is confirmed (absorption, L1280-1288), -1 for a
  buying climax; the climax bar's low / high on those bars, NaN elsewhere.
* ``exc`` int8 / ``exc_px``: +1 on the recovery bar of a spring (L1574), confirmed (``f_excFromPend``) or
  provisional (L1576-1586, Phase B not yet mature), -1 for a UTAD; the excursion's extreme on those bars. The bar on
  which a later breakout adopts a provisional spring (L1654-1660, ``ev_spring`` and ``ev_sos`` together) is not a
  recovery bar: its excursion was flagged at its own recovery bar.
* ``entry_std`` / ``entry_agg`` / ``entry_con`` int8: +1 / -1 on the bar where the entry alert fires (L2236-2238,
  L3198-3199: ``s.entryTime == time`` after the bar) in Standard / Aggressive / Conservative mode. The direction is
  the outcome at that close.
* ``in_cde`` bool: the bar's campaign holds an outcome in Phases C-E at the close AND was not demoted during the bar
  (``f_demoteToB``, L1210-1218, can be followed on the same bar by a new terminal test or spring). PREREG 6.3's exit
  X-S of a trade entered at bar i is then the first bar j > i where ``not (in_cde[j] and campaign[j] == campaign[i]
  and outcome[j] == outcome[i])``: a reset, a re-seed, a demotion or an outcome change. Equivalently (port B's form;
  the two agree at every entry on the real bars), the first j > i with ``in_cde[j]`` False: a campaign gains an
  outcome only from Phase B or none, and the outcome never changes side within Phases C-E (a spring after a terminal
  test keeps its side, L1540-1546), so ``in_cde`` is False on every bar where the campaign or the outcome changes.

What is known when
------------------
Bar i's outputs are the engine state after bar i's close and depend on bars 0..i only (``_commit`` =
``barstate.isconfirmed`` (L1795) is true on every closed bar). The engine has no look-ahead; its pivots are confirmed
``pLen`` bars after the pivot bar, and every pivot event is reported on the confirming bar.

They do depend on where the bars start: ``regime`` (L1093) is set by every Phase E and never cleared, and
``lastPLBar`` / ``lastPHBar`` survive every reset. Gold 4H started 300 or 500 bars before 2019 differs from the run
from the data start until 2022-01 (entries included); with 1,000 bars or more, and for 1H and 1D with 300, the
2019-2022 outputs are identical. Run from the data start (gold 4H then has 3,186 bars before 2019).

Speed: about 0.3 s for a 1H series of 57,000 bars, after a first compilation of about 25 s (cached by numba).

Pine readings (for the study's PORTING notes)
---------------------------------------------
* ``ta.pivothigh`` / ``ta.pivotlow`` (L1106-1107) with the series length ``pLen``: the candidate ``pLen`` bars back
  must be strictly above (below) every other high (low) of the ``2 pLen + 1`` bars; na before ``2 pLen`` bars exist.
  TradingView does not document ties; strict on both sides is the study's reading (also for the Market Structure
  Dashboard). ``pLen`` comes from the state at the start of the bar (L1105) and the length is applied as it is on that
  bar. ``_phS[o]`` in ``f_priorTrendScore`` (L593-594) is the history of that series: each bar's value computed with
  its own ``pLen``.
* ``for k = n - 1 to 0`` (L590) counts down: closes and pivots are visited oldest first.
* ``ta.sma``, ``ta.atr``, ``math.sum`` are study 1's verified primitives (``tradeiq_ind``); ``ta.highest`` /
  ``ta.lowest`` are na until ``length`` bars exist (as ``ta.sma``); ``nz`` falls back as written (L1068-1072,
  L1109-1114).
* ``math.round`` rounds ties up (``f_excursionRecoveryLimit(6)`` = 5, ``liveLen`` at ``4 * aRatio = 2.5`` is 3), as
  ``floor(x) + (x - floor(x) >= 0.5)``; ``int()`` truncates (``f_phaseCToDMinBars(7)`` = 3).
* Multiplications and additions keep the source's left-to-right order (e.g. ``avgEffPrev * 1.8 * relaxK``,
  ``disp + erPart + swingPart + smaPart``, ``e1 + e2 + e3 - max - min`` in ``f_robustEdge``).
* ``syminfo.mintick`` is the ``mintick`` argument: 0.001 for XAUUSDm and 0.01 for BTCUSDm (the repository's digits,
  ``external.Market.tick``; ``MINTICK``). It is only a floor in ``math.max(., mintick)``, which binds on bars with
  ``high == low`` (41 gold 1H bars, 3 gold 4H bars and 2 BTC 1H bars up to the hold-out start). Swapping 0.001 and
  0.01 changes no output on any of our series.
* The tie rule of the pivots: accepting an equal neighbour on the newer side adds one secondary test and one spring
  on gold 1H (Validation, 2023-09-13..19), on the older side one secondary test on gold 4H without volume (2018-11);
  no entry changes on any series.
* The hold of a campaign (``in_cde``) breaks on a demotion even when the same bar re-enters Phase C (it happens
  once: BTC 1H on Binance volume, 2023-11-22 00:00, the Standard long of 2023-11-17 19:00).
* ``timeframe.in_seconds`` (L961) is ``tf_seconds`` (default: the smallest step between two open times). It only
  scales ``ageBars`` in the readiness count, which is 0 on every bar where an entry can fire (each trigger bit is set
  together with ``f_setEvent``, which stamps ``lastEventTime = time``), so it cannot change an output.
* ``nz(volume)`` (L1063): a NaN volume counts as 0. ``no_vol=True`` passes zero volume: ``ta.cum(volume) <= 0`` keeps
  the script's own fallback ``effort = range`` on every bar.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np
from numba import njit
from numpy.lib.stride_tricks import sliding_window_view

from . import tradeiq_ind as I

__all__ = ["wyckoff", "CONTRACT_KEYS", "EVENT_BITS", "MINTICK", "FIELDS"]

NAN = math.nan

# ───────────────────────────── the script's constants (L53-264; only those the engine reads) ─────────────────────────

PIVOT_LEN = 4                      # pivotLen (L57)
SWING_MIN, SWING_MAX = 2, 10       # adaptiveSwingMin / Max (L59-60)
MINTICK = {"XAUUSDm": 0.001, "BTCUSDm": 0.01}   # syminfo.mintick: the repository's digits (config.SPECS)
DEFAULT_MINTICK = 0.001

DIR_ACCUM, DIR_DIST = 1, -1
PH_NONE, PH_A, PH_B, PH_C, PH_D, PH_E = 0, 1, 2, 3, 4, 5
REGIME_MARKUP, REGIME_MARKDOWN = 1, -1
TEST_NONE, TEST_GOOD, TEST_POOR, TEST_FAILED = 0, 1, 2, 3

EV_SC, EV_BC, EV_AR, EV_ST, EV_SPRING, EV_UTAD, EV_TEST = 1, 2, 3, 4, 5, 6, 7
EV_SOS, EV_SOW, EV_LPS, EV_LPSY, EV_CTEST_ACC, EV_CTEST_DST, EV_MARKUP, EV_MARKDOWN = 8, 9, 10, 11, 12, 13, 14, 15

BIT_PS, BIT_SC, BIT_BC, BIT_AR, BIT_ST = 1, 2, 4, 8, 16
BIT_SPRING, BIT_UTAD, BIT_TEST, BIT_SOS, BIT_SOW = 32, 64, 128, 256, 512
BIT_LPS, BIT_LPSY, BIT_E, BIT_CTEST = 1024, 2048, 4096, 16384

RS_INVALID, RS_ABSORB, RS_NORANGE, RS_DEPART, RS_STALE, RS_EEND = 0, 1, 2, 3, 4, 6

EVENT_BITS = {"ev_sc": BIT_SC, "ev_bc": BIT_BC, "ev_ar": BIT_AR, "ev_st": BIT_ST, "ev_spring": BIT_SPRING,
              "ev_utad": BIT_UTAD, "ev_test": BIT_TEST, "ev_ctest": BIT_CTEST, "ev_sos": BIT_SOS, "ev_sow": BIT_SOW,
              "ev_lps": BIT_LPS, "ev_lpsy": BIT_LPSY, "ev_phase_e": BIT_E}

CONTRACT_KEYS = ("phase", "outcome", "campaign", "range_lo", "range_hi", "hard_lo", "hard_hi",
                 *EVENT_BITS, "climax", "climax_px", "exc", "exc_px", "entry_std", "entry_agg", "entry_con", "in_cde")

# entry modes (L1730-1732), in the kernel's order: Standard 60 / 6 / 50, Aggressive 55 / 5 / 50, Conservative
# 75 / 7 / 60 (minimum confidence, minimum readiness, validation floor; the floor 50 is max(45, 60 - 10))
MODES = ("std", "agg", "con")

# ───────────────────────────── the campaign state WS (L366-483), as a float array ─────────────────────────────
# Only the fields the engine reads. na is NaN; bool and int fields are stored as floats (bar indices, counts and
# epoch milliseconds are exact in float64). WS.new() is a copy of the template.

FIELDS = (
    "STOP", "OUTC", "PHASE", "EV", "START", "PIVLEN", "BIRTH",
    "CLBAR", "CLPX", "CLEFF", "CLSPR", "CLATR", "ABSORBED",
    "OHI", "OLO", "RHI", "RLO",
    "ARRUNPX", "ARRUNBAR", "AROK", "ARBAR",
    "STCOUNT", "STN", "STEFF", "STSPR", "LGEFF", "LGSPR", "STBAR", "STPX",
    "EDGE1", "EDGE2", "EDGE3",
    "OPPCOUNT", "OPN", "OPEFF", "OPSPR", "OPLASTBAR", "OPLASTPX",
    "TRAV", "LZONE", "LZONEBAR", "LASTBAD",
    "BSTART", "CREADY", "DSTART", "ESTART",
    "PEND", "PENDEDGE", "PENDSTART", "PENDEXTBAR", "PENDEXT", "PENDEFF", "PENDSPR", "PENDCOOL",
    "PROVEDGE", "PROVBAR", "PROVPX", "PROVEFF", "PROVSPR",
    "EXC", "EXCTESTED", "EXCBAR", "EXCPX", "EXCEFF", "EXCSPR",
    "TESTTIME", "TESTSCORE", "STRBAR", "LPSBAR", "LASTEVTIME", "LASTACT",
    "CFPRIOR", "CFCLIMAX", "CFAR", "CFST", "CFEXC", "CFTEST", "CFSTRENGTH", "CFLPS", "CFACCEPT",
)
(STOP, OUTC, PHASE, EV, START, PIVLEN, BIRTH,
 CLBAR, CLPX, CLEFF, CLSPR, CLATR, ABSORBED,
 OHI, OLO, RHI, RLO,
 ARRUNPX, ARRUNBAR, AROK, ARBAR,
 STCOUNT, STN, STEFF, STSPR, LGEFF, LGSPR, STBAR, STPX,
 EDGE1, EDGE2, EDGE3,
 OPPCOUNT, OPN, OPEFF, OPSPR, OPLASTBAR, OPLASTPX,
 TRAV, LZONE, LZONEBAR, LASTBAD,
 BSTART, CREADY, DSTART, ESTART,
 PEND, PENDEDGE, PENDSTART, PENDEXTBAR, PENDEXT, PENDEFF, PENDSPR, PENDCOOL,
 PROVEDGE, PROVBAR, PROVPX, PROVEFF, PROVSPR,
 EXC, EXCTESTED, EXCBAR, EXCPX, EXCEFF, EXCSPR,
 TESTTIME, TESTSCORE, STRBAR, LPSBAR, LASTEVTIME, LASTACT,
 CFPRIOR, CFCLIMAX, CFAR, CFST, CFEXC, CFTEST, CFSTRENGTH, CFLPS, CFACCEPT) = range(len(FIELDS))
NF = len(FIELDS)
_ZERO_FIELDS = ("STOP", "OUTC", "PHASE", "EV", "ABSORBED", "AROK", "STCOUNT", "STN", "STEFF", "STSPR",
                "OPPCOUNT", "OPN", "OPEFF", "OPSPR", "TRAV", "LZONE", "PEND", "PENDEDGE", "PROVEDGE", "EXC",
                "EXCTESTED", "TESTSCORE", "CFPRIOR", "CFCLIMAX", "CFAR", "CFST", "CFEXC", "CFTEST", "CFSTRENGTH",
                "CFLPS", "CFACCEPT")
TEMPLATE = np.full(NF, NAN)
TEMPLATE[[FIELDS.index(k) for k in _ZERO_FIELDS]] = 0.0

# the variables outside WS (L1093-1101), as G: regime, lastPLBar, lastPHBar, and the current campaign's three entry
# slots (1 once that mode's s.entryTime is set; WS.new() frees them)
G_REGIME, G_LASTPL, G_LASTPH, G_USED = 0, 1, 2, 3
NG = 6

# the stateless per-bar series, packed as columns of P (shape n x NR)
_ROWS = ("O", "H", "L", "C", "T", "SPR", "EFF", "AVGRAW", "AVG", "AVGPREV", "ATRRAW", "A", "APREV", "CPOS", "RELE",
         "REFF", "RLOW", "RHIGH", "EFFHI", "NEWLOW", "NEWHIGH", "LIVE", "PRE", "TBVALID", "TBBASE", "TBSMA", "TBN",
         "TBE", "HIC2", "LOC2", "HIC3", "LOC3", "HIC5", "LOC5", "MBSOS", "MBSOW", "RES3UP", "RES3DN", "SOS", "SOW",
         "C1", "C2")
(R_O, R_H, R_L, R_C, R_T, R_SPR, R_EFF, R_AVGRAW, R_AVG, R_AVGPREV, R_ATRRAW, R_A, R_APREV, R_CPOS, R_RELE,
 R_REFF, R_RLOW, R_RHIGH, R_EFFHI, R_NEWLOW, R_NEWHIGH, R_LIVE, R_PRE, R_TBVALID, R_TBBASE, R_TBSMA, R_TBN,
 R_TBE, R_HIC2, R_LOC2, R_HIC3, R_LOC3, R_HIC5, R_LOC5, R_MBSOS, R_MBSOW, R_RES3UP, R_RES3DN, R_SOS, R_SOW,
 R_C1, R_C2) = range(len(_ROWS))
NR = len(_ROWS)

# debug columns of the kernel (tests and PORTING notes)
_DEBUG = ("plen", "trend", "ph", "pl", "new_ph", "new_pl", "reset", "reset_late", "demoted", "mature1", "conf", "val")
(D_PLEN, D_TREND, D_PH, D_PL, D_NEWPH, D_NEWPL, D_RESET, D_RESETLATE, D_DEMOTED, D_MATURE1, D_CONF,
 D_VAL) = range(len(_DEBUG))
ND = len(_DEBUG)


# ───────────────────────────── Pine helpers (scalars; numba) ─────────────────────────────

@njit(cache=True)
def _nz(x, y):
    """``nz(x, y)``."""
    return y if x != x else x


@njit(cache=True)
def _pmax(a, b):
    """``math.max(a, b)``: na if either is na."""
    if a != a or b != b:
        return np.nan
    return a if a >= b else b


@njit(cache=True)
def _pmin(a, b):
    """``math.min(a, b)``: na if either is na."""
    if a != a or b != b:
        return np.nan
    return a if a <= b else b


@njit(cache=True)
def _round(x):
    """``math.round(x)``: the nearest integer, ties up (``floor(x) + (x - floor(x) >= 0.5)``; ``x - floor(x)`` is
    exact). Returns a float."""
    f = np.floor(x)
    return f + 1.0 if x - f >= 0.5 else f


@njit(cache=True)
def _clamp(v, lo, hi):
    """``f_clamp`` (L561-562): ``math.max(lo, math.min(hi, v))``."""
    return _pmax(lo, _pmin(hi, v))


@njit(cache=True)
def _phase_a_min(p):
    """``f_phaseAMinBars`` (L651-652)."""
    return max(6, max(p, 1) * 2)


@njit(cache=True)
def _phase_b_min(p, r_atr):
    """``f_phaseBMinBars`` (L654-658): ``max(30, min(round(max(6p, rangeATR * p * 1.00)), 60))``."""
    pp = max(p, 1)
    raw = int(_round(_pmax(float(pp * 6), r_atr * float(pp) * 1.00)))
    return max(30, min(raw, 60))


@njit(cache=True)
def _phase_c_to_d_min(p):
    """``f_phaseCToDMinBars`` (L660-661): ``max(3, int(max(p, 1) / 2))``, the division truncated."""
    return max(3, max(p, 1) // 2)


@njit(cache=True)
def _phase_d_min(p):
    """``f_phaseDMinBars`` (L663-664)."""
    return max(4, max(p, 1))


@njit(cache=True)
def _rec_limit(p):
    """``f_excursionRecoveryLimit`` (L666-667): ``max(3, int(math.round(max(p, 1) * 0.75)))``."""
    return max(3, int(_round(max(p, 1) * 0.75)))


@njit(cache=True)
def _idle_limit(phase, has_ar, p):
    """``f_phaseIdleLimit`` (L669-680); -1 stands for na (Phases E and none)."""
    pp = max(p, 1)
    if phase == PH_A:
        return max(45, pp * 6) if has_ar else max(30, pp * 4)
    if phase == PH_B:
        return max(125, pp * 20)
    if phase == PH_C:
        return max(50, pp * 8)
    if phase == PH_D:
        return max(100, pp * 16)
    return -1


@njit(cache=True)
def _character_improving(n, eff_sum, spr_sum, last_e, last_s):
    """``f_phaseBCharacterImproving`` (L682-688)."""
    if n >= 2 and last_e == last_e and last_s == last_s:
        avg_e = eff_sum / n
        avg_s = spr_sum / n
        return last_e <= avg_e and last_s <= avg_s * 1.05
    return False


@njit(cache=True)
def _robust_edge(e1, e2, e3, orig, is_low):
    """``f_robustEdge`` (L690-698): the median of three as ``e1 + e2 + e3 - max - min``, else the mean with the
    original edge; never inside the original edge's side."""
    med = np.nan
    if e1 == e1 and e2 == e2 and e3 == e3:
        med = e1 + e2 + e3 - _pmax(e1, _pmax(e2, e3)) - _pmin(e1, _pmin(e2, e3))
    elif e1 == e1 and e2 == e2:
        med = ((e1 + e2) / 2.0 + orig) / 2.0
    elif e1 == e1:
        med = (e1 + orig) / 2.0
    if med != med:
        return orig
    return _pmax(orig, med) if is_low else _pmin(orig, med)


@njit(cache=True)
def _test_class(near, holds, close_ok, e, sp, c_e, c_s):
    """``f_testClass`` (L640-649)."""
    r = TEST_NONE
    if near:
        if not holds:
            r = TEST_FAILED
        elif close_ok and e <= c_e * 0.90 and sp <= c_s * 0.90:
            r = TEST_GOOD
        else:
            r = TEST_POOR
    return r


@njit(cache=True)
def _structure_confidence(prior, climax, ar, st, c_done, strength, lps, accept):
    """``f_structureConfidence`` (L615-616)."""
    return ((10 if prior else 0) + (15 if climax else 0) + (10 if ar else 0) + (15 if st else 0)
            + (15 if c_done else 0) + (15 if strength else 0) + (10 if lps else 0) + (10 if accept else 0))


@njit(cache=True)
def _validation_score(trend, absorbed, range_atr, st, opp, trav, clean, cause, terminal, strength, lps, accept):
    """``f_validationScore`` (L618-633)."""
    v = 0
    at = abs(trend)
    if at >= 35.0:
        v += 10
    elif at >= 15.0:
        v += 5
    if absorbed:
        v += 15
    if range_atr >= 1.5 and range_atr <= 8.0:
        v += 10
    elif range_atr >= 1.5 * 0.75 and range_atr <= 8.0 * 1.5:
        v += 5
    if st >= 2:
        v += 15
    elif st >= 1:
        v += 8
    if opp >= 1 and trav >= 2:
        v += 15
    elif opp >= 1 or trav >= 1:
        v += 8
    if clean:
        v += 10
    if cause >= 3.0:
        v += 10
    elif cause >= 1.5:
        v += 5
    if terminal:
        v += 10
    if strength:
        v += 3
    if lps:
        v += 2
    return min(v, 100)


@njit(cache=True)
def _cause_units(trav, b_age, p, r_atr):
    """``f_causeUnits`` (L635-638)."""
    time_units = float(b_age) / max(float(p) * 6.0, 1.0)
    width_bonus = 0.5 if r_atr >= 1.5 else 0.0
    return time_units + float(trav) * 0.5 + width_bonus


# ───────────────────────────── campaign helpers (L705-974; S is the WS array) ─────────────────────────────

@njit(cache=True)
def _range_atr(S, atr_now, mintick):
    """``f_rangeATRWS`` (L720-721)."""
    if S[RHI] == S[RHI] and S[RLO] == S[RLO]:
        return abs(S[RHI] - S[RLO]) / _pmax(_nz(S[CLATR], atr_now), mintick)
    return 0.0


@njit(cache=True)
def _hard_level(S, side):
    """``f_hardLevel`` (L723-729)."""
    if side == DIR_ACCUM:
        if S[EXC] != 0.0 and S[OUTC] == DIR_ACCUM and S[EXCPX] == S[EXCPX]:
            return S[EXCPX]
        if S[OLO] != S[OLO]:
            return S[RLO]
        return _pmin(S[OLO], _nz(S[RLO], S[OLO]))
    if S[EXC] != 0.0 and S[OUTC] == DIR_DIST and S[EXCPX] == S[EXCPX]:
        return S[EXCPX]
    if S[OHI] != S[OHI]:
        return S[RHI]
    return _pmax(S[OHI], _nz(S[RHI], S[OHI]))


@njit(cache=True)
def _conf(S):
    """``f_confWS`` (L932-934)."""
    c_done = S[CFTEST] != 0.0 or (S[CFEXC] != 0.0 and S[CFSTRENGTH] != 0.0)
    return _structure_confidence(S[CFPRIOR] != 0.0, S[CFCLIMAX] != 0.0, S[CFAR] != 0.0, S[CFST] != 0.0, c_done,
                                 S[CFSTRENGTH] != 0.0, S[CFLPS] != 0.0, S[CFACCEPT] != 0.0)


@njit(cache=True)
def _validation(S, p, trend_now, atr_now, bar, mintick):
    """``f_validationWS`` (L936-943)."""
    r_atr = _range_atr(S, atr_now, mintick)
    bs = S[BSTART]
    b_age = max(bar - bs, 0.0) if bs == bs else 0.0
    lb = S[LASTBAD]
    bad_age = -1.0 if lb != lb else bar - lb
    clean = bad_age < 0.0 or bad_age >= _round(p * 2.0)
    cause = _cause_units(S[TRAV], b_age, p, r_atr)
    terminal = ((S[CFTEST] != 0.0 and (S[EXC] == 0.0 or S[EXCTESTED] != 0.0))
                or (S[CFEXC] != 0.0 and S[CFSTRENGTH] != 0.0))
    if S[STOP] == 0.0:
        return 0
    return _validation_score(_nz(S[BIRTH], trend_now), S[ABSORBED] != 0.0, r_atr, S[STCOUNT], S[OPPCOUNT], S[TRAV],
                             clean, cause, terminal, S[CFSTRENGTH] != 0.0, S[CFLPS] != 0.0, S[CFACCEPT] != 0.0)


@njit(cache=True)
def _mature(S, p, atr_now, bar, mintick):
    """``f_matureWS`` (L945-956)."""
    r_atr = _range_atr(S, atr_now, mintick)
    bs = S[BSTART]
    b_age = bar - bs if bs == bs else 0.0
    b_min = _phase_b_min(p, r_atr)
    lb = S[LASTBAD]
    bad_age = -1.0 if lb != lb else bar - lb
    clean = bad_age < 0.0 or bad_age >= _round(p * 2.0)
    opp = S[OPPCOUNT] >= 1
    trav = S[TRAV] >= 2
    ch = _character_improving(S[STN], S[STEFF], S[STSPR], S[LGEFF], S[LGSPR])
    support = (1 if opp else 0) + (1 if trav else 0) + (1 if clean else 0) + (1 if ch else 0)
    sane = r_atr >= 1.5 * 0.75 and r_atr <= 8.0 * 2.0
    return S[PHASE] == PH_B and b_age >= b_min and S[STCOUNT] >= 2 and sane and support >= 2


@njit(cache=True)
def _readiness(S, min_conf, val_floor, atr_now, bar, close, tm, tfms, mintick):
    """``f_entryReadinessWS`` (L958-974). Its validation is taken with ``nz(s.pivLen, pivotLen)`` and
    ``s.birthTrend`` (L971), not with the entry check's ``nz(s.pivLen, liveLen)`` and ``trendScore`` (L1733)."""
    bull = S[OUTC] == DIR_ACCUM
    if S[RHI] != S[RHI] or S[RLO] != S[RLO]:
        dist_atr = 99.0
    elif bull:
        dist_atr = (close - S[RHI]) / _pmax(atr_now, mintick)
    else:
        dist_atr = (S[RLO] - close) / _pmax(atr_now, mintick)
    le = S[LASTEVTIME]
    age_bars = (tm - le) / max(tfms, 1.0) if le == le else 999.0
    terminal = (S[EXC] != 0.0 and S[EXCTESTED] != 0.0) or (S[EXC] == 0.0 and S[CFTEST] != 0.0)
    conf = _conf(S)
    pv = S[PIVLEN]
    p_r = PIVOT_LEN if pv != pv else int(pv)
    r = 0
    if S[OUTC] != 0.0:
        r += 1
    if S[PHASE] >= PH_C:
        r += 1
    if terminal:
        r += 1
    if S[CFSTRENGTH] != 0.0:
        r += 1
    if S[CFLPS] != 0.0:
        r += 1
    if conf >= min_conf:
        r += 1
    if _validation(S, p_r, S[BIRTH], atr_now, bar, mintick) >= val_floor:
        r += 1
    if dist_atr <= 2.0:
        r += 1
    if age_bars <= 50.0:
        r += 1
    return r


@njit(cache=True)
def _set_event(S, ev, bar, tm):
    """``f_setEvent`` (L705-711); ``lastEventBar`` / ``lastEventPrice`` are display only."""
    S[EV] = ev
    S[LASTEVTIME] = tm
    S[LASTACT] = bar


@njit(cache=True)
def _seed(S, side, p_len, trend, atr_now, eff_now, spr_now, bar, tm, high, low):
    """``f_seed`` (L731-753) on a fresh WS."""
    S[STOP] = side
    S[PHASE] = PH_A
    S[START] = bar
    S[PIVLEN] = p_len
    S[BIRTH] = trend
    S[CLBAR] = bar
    S[CLPX] = low if side == DIR_ACCUM else high
    S[CLEFF] = eff_now
    S[CLSPR] = spr_now
    S[CLATR] = atr_now
    if side == DIR_ACCUM:
        S[OLO] = low
        S[RLO] = low
    else:
        S[OHI] = high
        S[RHI] = high
    S[CFPRIOR] = 1.0
    _set_event(S, EV_SC if side == DIR_ACCUM else EV_BC, bar, tm)


@njit(cache=True)
def _freeze_ar(S):
    """``f_freezeAR`` (L755-766)."""
    S[ARBAR] = S[ARRUNBAR]
    S[CFAR] = 1.0
    if S[STOP] == DIR_ACCUM:
        S[OHI] = S[ARRUNPX]
        S[RHI] = S[ARRUNPX]
    else:
        S[OLO] = S[ARRUNPX]
        S[RLO] = S[ARRUNPX]


@njit(cache=True)
def _register_st(S, price, pb, e, sp, bar, tm):
    """``f_registerST`` (L775-807)."""
    S[STCOUNT] += 1.0
    S[STN] += 1.0
    S[STEFF] = S[STEFF] + e
    S[STSPR] = S[STSPR] + sp
    S[LGEFF] = e
    S[LGSPR] = sp
    S[STBAR] = pb
    S[STPX] = price
    S[EDGE3] = S[EDGE2]
    S[EDGE2] = S[EDGE1]
    S[EDGE1] = price
    if S[STOP] == DIR_ACCUM:
        S[RLO] = _robust_edge(S[EDGE1], S[EDGE2], S[EDGE3], S[OLO], True)
    else:
        S[RHI] = _robust_edge(S[EDGE1], S[EDGE2], S[EDGE3], S[OHI], False)
    S[CFST] = 1.0
    _set_event(S, EV_ST, bar, tm)


@njit(cache=True)
def _register_opp(S, price, pb, e, sp, bar):
    """``f_registerOpp`` (L809-830): no ``f_setEvent``."""
    S[OPPCOUNT] += 1.0
    S[OPN] += 1.0
    S[OPEFF] = S[OPEFF] + e
    S[OPSPR] = S[OPSPR] + sp
    S[OPLASTBAR] = pb
    S[OPLASTPX] = price
    S[LASTACT] = bar


@njit(cache=True)
def _clear_terminal(S):
    """``f_clearTerminal`` (L832-848)."""
    S[EXC] = 0.0
    S[EXCTESTED] = 0.0
    S[EXCBAR] = np.nan
    S[EXCPX] = np.nan
    S[EXCEFF] = np.nan
    S[EXCSPR] = np.nan
    S[TESTTIME] = np.nan
    S[TESTSCORE] = 0.0
    S[CFEXC] = 0.0
    S[CFTEST] = 0.0
    S[CREADY] = np.nan


@njit(cache=True)
def _exc_from_pend(S, bar, tm):
    """``f_excFromPend`` (L850-866)."""
    S[EXC] = 1.0
    S[EXCTESTED] = 0.0
    S[EXCBAR] = S[PENDEXTBAR]
    S[EXCPX] = S[PENDEXT]
    S[EXCEFF] = S[PENDEFF]
    S[EXCSPR] = S[PENDSPR]
    S[CFEXC] = 1.0
    S[OUTC] = S[PENDEDGE]
    S[PHASE] = PH_C
    S[CREADY] = np.nan
    S[PEND] = 0.0
    S[PROVEDGE] = 0.0
    _set_event(S, EV_SPRING if S[OUTC] == DIR_ACCUM else EV_UTAD, bar, tm)


@njit(cache=True)
def _adopt_prov(S):
    """``f_adoptProv`` (L868-881)."""
    S[EXC] = 1.0
    S[EXCTESTED] = 0.0
    S[EXCBAR] = S[PROVBAR]
    S[EXCPX] = S[PROVPX]
    S[EXCEFF] = S[PROVEFF]
    S[EXCSPR] = S[PROVSPR]
    S[CFEXC] = 1.0
    S[OUTC] = S[PROVEDGE]
    S[PROVEDGE] = 0.0


@njit(cache=True)
def _enter_ctest(S, outc, p_time, score, bar, tm):
    """``f_enterCTest`` (L883-893)."""
    S[PHASE] = PH_C
    S[OUTC] = outc
    S[CREADY] = bar
    S[TESTTIME] = p_time
    S[TESTSCORE] = score
    S[CFTEST] = 1.0
    S[PEND] = 0.0
    _set_event(S, EV_CTEST_ACC if outc == DIR_ACCUM else EV_CTEST_DST, bar, tm)


@njit(cache=True)
def _promote_d(S, outc, bar, tm):
    """``f_promoteD`` (L895-907)."""
    S[OUTC] = outc
    S[PHASE] = PH_D
    S[DSTART] = bar
    S[STRBAR] = bar
    S[CFSTRENGTH] = 1.0
    S[PEND] = 0.0
    _set_event(S, EV_SOS if outc == DIR_ACCUM else EV_SOW, bar, tm)


@njit(cache=True)
def _demote_to_b(S, bar):
    """``f_demoteToB`` (L909-930): keeps ``entryTime`` (the entry slots), ``ev`` and ``lastEventTime``."""
    _clear_terminal(S)
    S[OUTC] = 0.0
    S[PHASE] = PH_B
    S[STRBAR] = np.nan
    S[LPSBAR] = np.nan
    S[DSTART] = np.nan
    S[CFSTRENGTH] = 0.0
    S[CFLPS] = 0.0
    S[PROVEDGE] = 0.0
    S[PEND] = 0.0
    S[LASTBAD] = bar
    S[LASTACT] = bar


# ───────────────────────────── the engine, bar by bar ─────────────────────────────

@njit(cache=True)
def _kernel(P, PHC, PLC, TPL, S, G, start, stop, mintick, tfms,
            o_phase, o_outc, o_camp, o_rlo, o_rhi, o_hlo, o_hhi, o_sig, o_clpx, o_exc, o_excpx, o_entry, o_incde,
            o_dbg):
    """
    ``f_engine(true)`` over bars [start, stop) of P, from the state (S, G); writes bar t's outputs at t and leaves the
    final state in (S, G). The pivot history read by ``f_priorTrendScore`` is the one recorded from ``start`` on.
    """
    n = P.shape[0]
    ph_cnt = np.zeros(n, np.int64)          # pivot highs (non-na ph) at bars start..t
    pl_cnt = np.zeros(n, np.int64)
    ph_up = np.zeros(n + 1, np.int64)       # among consecutive pivot highs: rises / falls up to the k-th
    ph_dn = np.zeros(n + 1, np.int64)
    pl_up = np.zeros(n + 1, np.int64)
    pl_dn = np.zeros(n + 1, np.int64)
    ph_k = 0
    pl_k = 0
    ph_last = np.nan
    pl_last = np.nan
    regime = G[G_REGIME]
    last_pl_bar = G[G_LASTPL]
    last_ph_bar = G[G_LASTPH]
    used = np.zeros(3, np.bool_)
    for m in range(3):
        used[m] = G[G_USED + m] != 0.0
    for t in range(start, stop):
        bar = float(t)
        tm = P[t, R_T]
        a = P[t, R_A]
        hi = P[t, R_H]
        lo = P[t, R_L]
        cl = P[t, R_C]
        eff = P[t, R_EFF]
        spr = P[t, R_SPR]
        live = int(P[t, R_LIVE])
        # L1105-1114: the pivot length from the state at the start of the bar, the pivots and their bar's values
        if S[PHASE] != PH_NONE:
            pv = S[PIVLEN]
            p_len = live if pv != pv else int(pv)
        else:
            p_len = live
        ph = PHC[t, p_len]
        pl = PLC[t, p_len]
        if ph == ph:
            if ph_k > 0:
                ph_up[ph_k] = ph_up[ph_k - 1] + (1 if ph > ph_last else 0)
                ph_dn[ph_k] = ph_dn[ph_k - 1] + (1 if ph < ph_last else 0)
            ph_last = ph
            ph_k += 1
        ph_cnt[t] = ph_k
        if pl == pl:
            if pl_k > 0:
                pl_up[pl_k] = pl_up[pl_k - 1] + (1 if pl > pl_last else 0)
                pl_dn[pl_k] = pl_dn[pl_k - 1] + (1 if pl < pl_last else 0)
            pl_last = pl
            pl_k += 1
        pl_cnt[t] = pl_k
        piv_bar = bar - p_len
        j = t - p_len
        if j >= 0:
            p_a = _pmax(_nz(P[j, R_ATRRAW], a), mintick)
            p_eff = P[j, R_EFF]
            p_spr = _pmax(P[j, R_H] - P[j, R_L], mintick)
            p_cpos = (P[j, R_C] - P[j, R_L]) / p_spr
            p_avg = _nz(P[j, R_AVGRAW], P[t, R_AVG])
            p_time = P[j, R_T]
        else:
            p_a = _pmax(a, mintick)
            p_eff = eff
            p_spr = _pmax(hi - lo, mintick)
            p_cpos = (cl - lo) / p_spr
            p_avg = P[t, R_AVG]
            p_time = tm
        # L1116-1122, f_priorTrendScore (L573-613): its stateless parts are in TBBASE / TBSMA, the swing part reads
        # the pivots of bars t-e-n+1 .. t-e, oldest first
        trend = 0.0
        if P[t, R_TBVALID] != 0.0:
            nn = int(P[t, R_TBN])
            ee = int(P[t, R_TBE])
            w_lo = t - ee - nn + 1
            w_hi = t - ee
            ia = ph_cnt[w_lo - 1]
            ib = ph_cnt[w_hi] - 1
            hh = 0
            lh = 0
            if ib > ia:
                hh = ph_up[ib] - ph_up[ia]
                lh = ph_dn[ib] - ph_dn[ia]
            ia = pl_cnt[w_lo - 1]
            ib = pl_cnt[w_hi] - 1
            hl = 0
            ll = 0
            if ib > ia:
                hl = pl_up[ib] - pl_up[ia]
                ll = pl_dn[ib] - pl_dn[ia]
            swings = hh + ll + lh + hl
            swing_part = float(hh + hl - lh - ll) / swings * 20.0 if swings > 0 else 0.0
            trend = _clamp(P[t, R_TBBASE] + swing_part + P[t, R_TBSMA], -100.0, 100.0)
        down_trend = trend <= -15.0
        up_trend = trend >= 15.0
        strong_trend = abs(trend) >= 35.0
        sig = 0
        demoted = False
        clpx_out = np.nan
        exc_out = 0
        excpx_out = np.nan

        # ── L1164-1179: the snapshot at the start of the commit ──
        p0 = live if S[PIVLEN] != S[PIVLEN] else int(S[PIVLEN])
        rk0 = S[RHI] == S[RHI] and S[RLO] == S[RLO]
        r_h0 = S[RHI]
        r_l0 = S[RLO]
        r_ht0 = _pmax(r_h0 - r_l0, mintick) if rk0 else np.nan
        r_mid0 = (r_h0 + r_l0) / 2.0 if rk0 else np.nan
        probe_open = S[PEND] != 0.0 and bar - S[PENDSTART] <= _rec_limit(p0)
        struct_age = bar - S[START] if S[START] == S[START] else 0.0
        age_ok_bull = regime != REGIME_MARKDOWN or struct_age >= 25
        age_ok_bear = regime != REGIME_MARKUP or struct_age >= 25
        hard_bull0 = _hard_level(S, DIR_ACCUM)
        hard_bear0 = _hard_level(S, DIR_DIST)
        reset_why = -1

        # ── L1182-1234: retire structures that no longer fit ──
        if S[PHASE] == PH_A:
            a_age = bar - S[CLBAR]
            a_inv_acc = S[STOP] == DIR_ACCUM and P[t, R_HIC2] < S[CLPX] - a * 0.50
            a_inv_dst = S[STOP] == DIR_DIST and P[t, R_LOC2] > S[CLPX] + a * 0.50
            a_absorb_exp = S[ABSORBED] == 0.0 and a_age > 8
            a_no_ar = S[AROK] == 0.0 and a_age > 30
            a_over_ext = (S[AROK] != 0.0 and S[ARRUNPX] == S[ARRUNPX]
                          and abs(S[ARRUNPX] - S[CLPX]) / _pmax(_nz(S[CLATR], a), mintick) > 15.0)
            a_depart = False
            if a_age > 30 and rk0:
                a_buf = _pmax(r_ht0 * 0.30, a * 0.75)
                a_depart = ((S[STOP] == DIR_ACCUM and P[t, R_LOC3] > r_h0 + a_buf)
                            or (S[STOP] == DIR_DIST and P[t, R_HIC3] < r_l0 - a_buf))
            if a_inv_acc or a_inv_dst:
                reset_why = RS_INVALID
            elif a_absorb_exp:
                reset_why = RS_ABSORB
            elif a_no_ar or a_over_ext or a_depart:
                reset_why = RS_NORANGE
        if S[PHASE] == PH_C and not probe_open and reset_why < 0:
            c_bull_dead = (S[OUTC] == DIR_ACCUM and hard_bull0 == hard_bull0
                           and P[t, R_HIC2] < hard_bull0 - a * 0.50)
            c_bear_dead = (S[OUTC] == DIR_DIST and hard_bear0 == hard_bear0
                           and P[t, R_LOC2] > hard_bear0 + a * 0.50)
            if c_bull_dead or c_bear_dead:
                reset_why = RS_INVALID
        if S[PHASE] == PH_D and rk0 and reset_why < 0:
            if S[OUTC] == DIR_ACCUM:
                if hard_bull0 == hard_bull0 and P[t, R_HIC2] < hard_bull0 - a * 0.50:
                    reset_why = RS_INVALID
                elif P[t, R_HIC3] < r_mid0:
                    _demote_to_b(S, bar)
                    demoted = True
            elif S[OUTC] == DIR_DIST:
                if hard_bear0 == hard_bear0 and P[t, R_LOC2] > hard_bear0 + a * 0.50:
                    reset_why = RS_INVALID
                elif P[t, R_LOC3] > r_mid0:
                    _demote_to_b(S, bar)
                    demoted = True
        if S[PHASE] == PH_E and rk0 and reset_why < 0:
            e_fail = P[t, R_HIC3] < r_mid0 if S[OUTC] == DIR_ACCUM else P[t, R_LOC3] > r_mid0
            e_old = S[ESTART] == S[ESTART] and bar - S[ESTART] > 300
            if e_fail or e_old:
                reset_why = RS_EEND
        idle_lim = _idle_limit(int(S[PHASE]), S[AROK] != 0.0, p0)
        if (reset_why < 0 and not probe_open and idle_lim >= 0 and S[LASTACT] == S[LASTACT]
                and bar - S[LASTACT] > idle_lim):
            reset_why = RS_STALE
        if reset_why >= 0:
            S[:] = TPL
            used[:] = False

        # ── L1254-1275: seed a new climax ──
        relax_k = 0.80 if strong_trend else 1.0
        vol_hit = eff >= P[t, R_AVGPREV] * 1.8 * relax_k
        spr_hit = spr >= P[t, R_APREV] * 1.5 * relax_k
        eff_hi = P[t, R_EFFHI]
        exceptional = (eff_hi == eff_hi and eff >= eff_hi) or spr >= P[t, R_APREV] * 1.5 * 1.5
        new_low = P[t, R_NEWLOW] != 0.0
        new_high = P[t, R_NEWHIGH] != 0.0
        cpos = P[t, R_CPOS]
        sc_sc = ((1 if down_trend else 0) + (1 if new_low else 0) + (1 if vol_hit else 0) + (1 if spr_hit else 0)
                 + (1 if cpos >= 0.35 else 0) + (1 if exceptional else 0))
        bc_sc = ((1 if up_trend else 0) + (1 if new_high else 0) + (1 if vol_hit else 0) + (1 if spr_hit else 0)
                 + (1 if cpos <= 0.65 else 0) + (1 if exceptional else 0))
        seed_open = S[PHASE] == PH_NONE or S[PHASE] == PH_E
        can_sc = seed_open or (S[PHASE] == PH_A and S[STOP] == DIR_ACCUM and lo < S[CLPX])
        can_bc = seed_open or (S[PHASE] == PH_A and S[STOP] == DIR_DIST and hi > S[CLPX])
        is_sc = can_sc and down_trend and new_low and vol_hit and spr_hit and sc_sc >= 5
        is_bc = can_bc and up_trend and new_high and vol_hit and spr_hit and bc_sc >= 5
        if is_sc != is_bc:
            S[:] = TPL
            used[:] = False
            _seed(S, DIR_ACCUM if is_sc else DIR_DIST, P[t, R_PRE], trend, a, eff, spr, bar, tm, hi, lo)

        # ── L1278-1290: confirm the stopping action ──
        if S[PHASE] == PH_A and S[ABSORBED] == 0.0 and S[CLBAR] == S[CLBAR]:
            abs_age = bar - S[CLBAR]
            if abs_age >= 3 and abs_age <= 8:
                effort_ok = P[t, R_REFF] >= P[t, R_AVG] * 0.90
                acc_abs = (S[STOP] == DIR_ACCUM and P[t, R_RLOW] >= S[CLPX] - S[CLATR] * 0.50
                           and cl >= S[CLPX] + S[CLATR] * 0.35)
                dst_abs = (S[STOP] == DIR_DIST and P[t, R_RHIGH] <= S[CLPX] + S[CLATR] * 0.50
                           and cl <= S[CLPX] - S[CLATR] * 0.35)
                if effort_ok and (acc_abs or dst_abs):
                    S[ABSORBED] = 1.0
                    S[CFCLIMAX] = 1.0
                    S[LASTACT] = bar
                    sig |= BIT_SC if S[STOP] == DIR_ACCUM else BIT_BC
                    clpx_out = S[CLPX]

        # ── L1292-1311: build the AR ──
        if (S[PHASE] == PH_A and S[ARBAR] != S[ARBAR] and S[CLBAR] == S[CLBAR] and bar > S[CLBAR]
                and bar - S[CLBAR] <= 30):
            if S[STOP] == DIR_ACCUM:
                if S[ARRUNPX] != S[ARRUNPX] or hi > S[ARRUNPX]:
                    S[ARRUNPX] = hi
                    S[ARRUNBAR] = bar
                if S[AROK] == 0.0 and S[ARRUNPX] - S[CLPX] >= a * 2.0:
                    S[AROK] = 1.0
            else:
                if S[ARRUNPX] != S[ARRUNPX] or lo < S[ARRUNPX]:
                    S[ARRUNPX] = lo
                    S[ARRUNBAR] = bar
                if S[AROK] == 0.0 and S[CLPX] - S[ARRUNPX] >= a * 2.0:
                    S[AROK] = 1.0
        if S[PHASE] == PH_A and S[AROK] != 0.0 and S[ABSORBED] != 0.0 and S[ARBAR] != S[ARBAR]:
            if S[STOP] == DIR_ACCUM:
                S[RHI] = S[ARRUNPX]
                S[OHI] = S[ARRUNPX]
            else:
                S[RLO] = S[ARRUNPX]
                S[OLO] = S[ARRUNPX]

        # ── L1313-1326: the pivots of this bar ──
        p1 = live if S[PIVLEN] != S[PIVLEN] else int(S[PIVLEN])
        rk1 = S[RHI] == S[RHI] and S[RLO] == S[RLO]
        r_h1 = S[RHI]
        r_l1 = S[RLO]
        orig_ht1 = _pmax(_nz(S[OHI], r_h1) - _nz(S[OLO], r_l1), mintick) if rk1 else np.nan
        mature1 = _mature(S, p1, a, bar, mintick)
        new_pl = pl == pl and (last_pl_bar != last_pl_bar or piv_bar > last_pl_bar)
        new_ph = ph == ph and (last_ph_bar != last_ph_bar or piv_bar > last_ph_bar)
        if new_pl:
            last_pl_bar = piv_bar
        if new_ph:
            last_ph_bar = piv_bar
        pl_used = False
        ph_used = False

        # L1328-1369: terminal test (B -> C without an excursion), the low side first
        if new_pl and S[PHASE] == PH_B and mature1 and rk1:
            lo_ref_st = S[STOP] == DIR_ACCUM
            t_ref_n = S[STN] if lo_ref_st else S[OPN]
            t_ref_bar = S[STBAR] if lo_ref_st else S[OPLASTBAR]
            t_ref_px = S[STPX] if lo_ref_st else S[OPLASTPX]
            if t_ref_n > 0 and t_ref_bar == t_ref_bar:
                t_ref_eff = (S[STEFF] if lo_ref_st else S[OPEFF]) / t_ref_n
                t_ref_spr = (S[STSPR] if lo_ref_st else S[OPSPR]) / t_ref_n
                t_later = piv_bar >= t_ref_bar + 3
                t_near = pl <= r_l1 + p_a * 1.25
                t_holds = pl >= _pmin(_nz(S[OLO], r_l1), r_l1) - p_a * 0.15
                t_higher = t_ref_px != t_ref_px or pl >= t_ref_px - p_a * 0.15
                tq_v = p_eff <= t_ref_eff * 0.85
                tq_s = p_spr <= t_ref_spr * 0.85
                tn_v = p_eff <= t_ref_eff * 1.05
                tn_s = p_spr <= t_ref_spr * 1.05
                t_sc = (1 if tq_v else 0) + (1 if tq_s else 0) + (1 if p_cpos >= 0.50 else 0)
                if (t_later and t_near and t_holds and t_higher and ((tq_v and tn_s) or (tq_s and tn_v))
                        and t_sc >= 2):
                    _enter_ctest(S, DIR_ACCUM, p_time, t_sc, bar, tm)
                    sig |= BIT_CTEST
                    pl_used = True
        if new_ph and S[PHASE] == PH_B and mature1 and rk1:
            hi_ref_st = S[STOP] == DIR_DIST
            u_ref_n = S[STN] if hi_ref_st else S[OPN]
            u_ref_bar = S[STBAR] if hi_ref_st else S[OPLASTBAR]
            u_ref_px = S[STPX] if hi_ref_st else S[OPLASTPX]
            if u_ref_n > 0 and u_ref_bar == u_ref_bar:
                u_ref_eff = (S[STEFF] if hi_ref_st else S[OPEFF]) / u_ref_n
                u_ref_spr = (S[STSPR] if hi_ref_st else S[OPSPR]) / u_ref_n
                u_later = piv_bar >= u_ref_bar + 3
                u_near = ph >= r_h1 - p_a * 1.25
                u_holds = ph <= _pmax(_nz(S[OHI], r_h1), r_h1) + p_a * 0.15
                u_lower = u_ref_px != u_ref_px or ph <= u_ref_px + p_a * 0.15
                uq_v = p_eff <= u_ref_eff * 0.85
                uq_s = p_spr <= u_ref_spr * 0.85
                un_v = p_eff <= u_ref_eff * 1.05
                un_s = p_spr <= u_ref_spr * 1.05
                u_sc = (1 if uq_v else 0) + (1 if uq_s else 0) + (1 if p_cpos <= 0.50 else 0)
                if (u_later and u_near and u_holds and u_lower and ((uq_v and un_s) or (uq_s and un_v))
                        and u_sc >= 2):
                    _enter_ctest(S, DIR_DIST, p_time, u_sc, bar, tm)
                    sig |= BIT_CTEST
                    ph_used = True

        # L1371-1410: A -> B, the first secondary test (the AR is frozen)
        if (new_pl and not pl_used and S[PHASE] == PH_A and S[STOP] == DIR_ACCUM and S[ABSORBED] != 0.0
                and S[AROK] != 0.0 and S[ARRUNBAR] == S[ARRUNBAR] and piv_bar > S[ARRUNBAR]):
            a_zone_top = S[OLO] + (S[ARRUNPX] - S[OLO]) * 0.25
            a_near = abs(pl - S[OLO]) <= p_a * 0.75 or pl <= a_zone_top
            a_holds = pl >= S[OLO] - p_a * 0.75
            a_close = p_cpos >= 0.45
            a_tc = _test_class(a_near, a_holds, a_close, p_eff, p_spr, S[CLEFF], S[CLSPR])
            a_sc = ((1 if a_near else 0) + (1 if p_eff <= S[CLEFF] * 0.90 else 0)
                    + (1 if p_spr <= S[CLSPR] * 0.90 else 0) + (1 if a_holds else 0) + (1 if a_close else 0) + 1)
            a_age_ok = piv_bar - S[START] >= _phase_a_min(p1)
            a_space = piv_bar - S[ARRUNBAR] >= max(2, p1)
            if a_near:
                S[LASTACT] = bar
            if a_tc == TEST_GOOD and a_sc >= 4 and a_age_ok and a_space:
                _freeze_ar(S)
                _register_st(S, pl, piv_bar, p_eff, p_spr, bar, tm)
                S[PHASE] = PH_B
                S[BSTART] = piv_bar
                sig |= BIT_AR | BIT_ST
                pl_used = True
        if (new_ph and not ph_used and S[PHASE] == PH_A and S[STOP] == DIR_DIST and S[ABSORBED] != 0.0
                and S[AROK] != 0.0 and S[ARRUNBAR] == S[ARRUNBAR] and piv_bar > S[ARRUNBAR]):
            a_zone_bot = S[OHI] - (S[OHI] - S[ARRUNPX]) * 0.25
            a_near = abs(ph - S[OHI]) <= p_a * 0.75 or ph >= a_zone_bot
            a_holds = ph <= S[OHI] + p_a * 0.75
            a_close = p_cpos <= 0.55
            a_tc = _test_class(a_near, a_holds, a_close, p_eff, p_spr, S[CLEFF], S[CLSPR])
            a_sc = ((1 if a_near else 0) + (1 if p_eff <= S[CLEFF] * 0.90 else 0)
                    + (1 if p_spr <= S[CLSPR] * 0.90 else 0) + (1 if a_holds else 0) + (1 if a_close else 0) + 1)
            a_age_ok = piv_bar - S[START] >= _phase_a_min(p1)
            a_space = piv_bar - S[ARRUNBAR] >= max(2, p1)
            if a_near:
                S[LASTACT] = bar
            if a_tc == TEST_GOOD and a_sc >= 4 and a_age_ok and a_space:
                _freeze_ar(S)
                _register_st(S, ph, piv_bar, p_eff, p_spr, bar, tm)
                S[PHASE] = PH_B
                S[BSTART] = piv_bar
                sig |= BIT_AR | BIT_ST
                ph_used = True

        # L1412-1462: Phase B tests at the climax edge, and the opposite edge
        rk1 = S[RHI] == S[RHI] and S[RLO] == S[RLO]
        if new_pl and not pl_used and S[PHASE] == PH_B and rk1 and piv_bar > S[BSTART]:
            b_ht = _pmax(S[RHI] - S[RLO], mintick)
            if S[STOP] == DIR_ACCUM:
                b_near = (abs(pl - S[RLO]) <= p_a * 0.75 or abs(pl - S[OLO]) <= p_a * 0.75
                          or pl <= S[RLO] + b_ht * 0.25)
                b_holds = pl >= S[OLO] - p_a * 0.75
                b_close = p_cpos >= 0.45
                b_tc = _test_class(b_near, b_holds, b_close, p_eff, p_spr, S[CLEFF], S[CLSPR])
                b_sc = ((1 if b_near else 0) + (1 if p_eff <= S[CLEFF] * 0.90 else 0)
                        + (1 if p_spr <= S[CLSPR] * 0.90 else 0) + (1 if b_holds else 0) + (1 if b_close else 0)
                        + 1)
                b_is_prov = (S[PROVEDGE] == DIR_ACCUM and S[PROVBAR] == S[PROVBAR]
                             and abs(piv_bar - S[PROVBAR]) <= p1)
                if b_near:
                    S[LASTACT] = bar
                if b_tc == TEST_FAILED and not b_is_prov:
                    S[LASTBAD] = piv_bar
                elif b_tc == TEST_GOOD and b_sc >= 4:
                    _register_st(S, pl, piv_bar, p_eff, p_spr, bar, tm)
                    sig |= BIT_ST
            else:
                if pl < S[RLO] and pl >= _nz(S[OLO], S[RLO]) - orig_ht1 * 0.15:
                    S[RLO] = pl
                o_ht = _pmax(S[RHI] - S[RLO], mintick)
                o_near = pl <= S[RLO] + p_a * 0.75 or pl <= S[RLO] + o_ht * 0.25
                o_inside = pl >= _nz(S[OLO], S[RLO]) - orig_ht1 * 0.15
                o_ctrl = p_eff <= S[CLEFF] * 1.20 and p_spr <= S[CLSPR] * 1.20
                if o_near and o_inside and o_ctrl and (S[OPLASTBAR] != S[OPLASTBAR] or piv_bar > S[OPLASTBAR]):
                    _register_opp(S, pl, piv_bar, p_eff, p_spr, bar)
        if new_ph and not ph_used and S[PHASE] == PH_B and rk1 and piv_bar > S[BSTART]:
            b_ht = _pmax(S[RHI] - S[RLO], mintick)
            if S[STOP] == DIR_DIST:
                h_near = (abs(ph - S[RHI]) <= p_a * 0.75 or abs(ph - S[OHI]) <= p_a * 0.75
                          or ph >= S[RHI] - b_ht * 0.25)
                h_holds = ph <= S[OHI] + p_a * 0.75
                h_close = p_cpos <= 0.55
                h_tc = _test_class(h_near, h_holds, h_close, p_eff, p_spr, S[CLEFF], S[CLSPR])
                h_sc = ((1 if h_near else 0) + (1 if p_eff <= S[CLEFF] * 0.90 else 0)
                        + (1 if p_spr <= S[CLSPR] * 0.90 else 0) + (1 if h_holds else 0) + (1 if h_close else 0)
                        + 1)
                h_is_prov = (S[PROVEDGE] == DIR_DIST and S[PROVBAR] == S[PROVBAR]
                             and abs(piv_bar - S[PROVBAR]) <= p1)
                if h_near:
                    S[LASTACT] = bar
                if h_tc == TEST_FAILED and not h_is_prov:
                    S[LASTBAD] = piv_bar
                elif h_tc == TEST_GOOD and h_sc >= 4:
                    _register_st(S, ph, piv_bar, p_eff, p_spr, bar, tm)
                    sig |= BIT_ST
            else:
                if ph > S[RHI] and ph <= _nz(S[OHI], S[RHI]) + orig_ht1 * 0.15:
                    S[RHI] = ph
                o_ht = _pmax(S[RHI] - S[RLO], mintick)
                o_near = ph >= S[RHI] - p_a * 0.75 or ph >= S[RHI] - o_ht * 0.25
                o_inside = ph <= _nz(S[OHI], S[RHI]) + orig_ht1 * 0.15
                o_ctrl = p_eff <= S[CLEFF] * 1.20 and p_spr <= S[CLSPR] * 1.20
                if o_near and o_inside and o_ctrl and (S[OPLASTBAR] != S[OPLASTBAR] or piv_bar > S[OPLASTBAR]):
                    _register_opp(S, ph, piv_bar, p_eff, p_spr, bar)

        # L1465-1475: traversals between the bottom and top quarters (every new pivot, used or not)
        if S[PHASE] == PH_B and S[RHI] == S[RHI] and S[RLO] == S[RLO]:
            tv_ht = _pmax(S[RHI] - S[RLO], mintick)
            lo_zone = new_pl and pl <= S[RLO] + tv_ht * 0.25
            hi_zone = new_ph and ph >= S[RHI] - tv_ht * 0.25
            zone_now = 0
            if lo_zone != hi_zone:
                zone_now = -1 if lo_zone else 1
            if zone_now != 0 and (S[LZONEBAR] != S[LZONEBAR] or piv_bar > S[LZONEBAR]):
                if S[LZONE] != 0.0 and zone_now != S[LZONE]:
                    S[TRAV] += 1.0
                    S[LASTACT] = bar
                S[LZONE] = zone_now
                S[LZONEBAR] = piv_bar

        # L1477-1502: the test of a spring / UTAD
        if (new_pl and S[PHASE] == PH_C and S[OUTC] == DIR_ACCUM and S[EXC] != 0.0 and S[EXCTESTED] == 0.0
                and piv_bar > S[EXCBAR] and S[RLO] == S[RLO]):
            x_near = pl <= S[RLO] + p_a * 1.25
            x_keep = pl >= S[EXCPX] - p_a * 0.15
            x_sc = ((1 if p_eff <= S[EXCEFF] * 0.80 else 0) + (1 if p_spr <= S[EXCSPR] * 0.80 else 0)
                    + (1 if p_cpos >= 0.50 else 0))
            if x_near and x_keep and x_sc >= 2:
                S[EXCTESTED] = 1.0
                S[CREADY] = bar
                S[TESTTIME] = p_time
                S[TESTSCORE] = x_sc
                S[CFTEST] = 1.0
                _set_event(S, EV_TEST, bar, tm)
                sig |= BIT_TEST
        if (new_ph and S[PHASE] == PH_C and S[OUTC] == DIR_DIST and S[EXC] != 0.0 and S[EXCTESTED] == 0.0
                and piv_bar > S[EXCBAR] and S[RHI] == S[RHI]):
            x_near = ph >= S[RHI] - p_a * 1.25
            x_keep = ph <= S[EXCPX] + p_a * 0.15
            x_sc = ((1 if p_eff <= S[EXCEFF] * 0.80 else 0) + (1 if p_spr <= S[EXCSPR] * 0.80 else 0)
                    + (1 if p_cpos <= 0.50 else 0))
            if x_near and x_keep and x_sc >= 2:
                S[EXCTESTED] = 1.0
                S[CREADY] = bar
                S[TESTTIME] = p_time
                S[TESTSCORE] = x_sc
                S[CFTEST] = 1.0
                _set_event(S, EV_TEST, bar, tm)
                sig |= BIT_TEST

        # L1504-1529: LPS / LPSY (re-recorded by every later qualifying pivot)
        if (new_pl and S[PHASE] == PH_D and S[OUTC] == DIR_ACCUM and S[STRBAR] == S[STRBAR]
                and piv_bar > S[STRBAR] and S[RHI] == S[RHI]):
            l_hard = _hard_level(S, DIR_ACCUM)
            l_side = l_hard == l_hard and pl > l_hard - p_a * 0.15
            l_creek = pl >= S[RHI] - p_a * 1.50
            l_sc = ((1 if p_eff <= p_avg * 1.00 else 0) + (1 if p_spr <= p_a * 1.00 else 0)
                    + (1 if p_cpos >= 0.45 else 0))
            if l_side and l_creek and l_sc >= 2:
                S[LPSBAR] = bar
                S[CFLPS] = 1.0
                _set_event(S, EV_LPS, bar, tm)
                sig |= BIT_LPS
        if (new_ph and S[PHASE] == PH_D and S[OUTC] == DIR_DIST and S[STRBAR] == S[STRBAR]
                and piv_bar > S[STRBAR] and S[RLO] == S[RLO]):
            y_hard = _hard_level(S, DIR_DIST)
            y_side = y_hard == y_hard and ph < y_hard + p_a * 0.15
            y_ice = ph <= S[RLO] + p_a * 1.50
            y_sc = ((1 if p_eff <= p_avg * 1.00 else 0) + (1 if p_spr <= p_a * 1.00 else 0)
                    + (1 if p_cpos <= 0.55 else 0))
            if y_side and y_ice and y_sc >= 2:
                S[LPSBAR] = bar
                S[CFLPS] = 1.0
                _set_event(S, EV_LPSY, bar, tm)
                sig |= BIT_LPSY

        # ── L1531-1610: Spring, UTAD ──
        p2 = live if S[PIVLEN] != S[PIVLEN] else int(S[PIVLEN])
        rk2 = S[RHI] == S[RHI] and S[RLO] == S[RLO]
        r_h2 = S[RHI]
        r_l2 = S[RLO]
        rec_limit2 = _rec_limit(p2)
        mature2 = _mature(S, p2, a, bar, mintick)
        b_age2 = bar - S[BSTART] if S[BSTART] == S[BSTART] else 0.0
        probe_b = S[PHASE] == PH_B and S[STCOUNT] >= 1 and b_age2 >= max(3, p2 * 2)
        probe_c_lo = S[PHASE] == PH_C and S[OUTC] == DIR_ACCUM and S[EXC] == 0.0
        probe_c_hi = S[PHASE] == PH_C and S[OUTC] == DIR_DIST and S[EXC] == 0.0
        if rk2 and S[PEND] == 0.0 and (S[PENDCOOL] != S[PENDCOOL] or bar > S[PENDCOOL]):
            pen_lo = r_l2 - lo
            pen_hi = hi - r_h2
            ok_lo = (probe_b or probe_c_lo) and pen_lo >= a * 0.15 and pen_lo <= a * 2.5
            ok_hi = (probe_b or probe_c_hi) and pen_hi >= a * 0.15 and pen_hi <= a * 2.5
            if ok_lo != ok_hi:
                S[PEND] = 1.0
                S[PENDEDGE] = DIR_ACCUM if ok_lo else DIR_DIST
                S[PENDSTART] = bar
                S[PENDEXTBAR] = bar
                S[PENDEXT] = lo if ok_lo else hi
                S[PENDEFF] = eff
                S[PENDSPR] = spr
        if S[PEND] != 0.0 and rk2 and (S[PHASE] == PH_B or S[PHASE] == PH_C):
            if S[PENDEDGE] == DIR_ACCUM and lo < S[PENDEXT]:
                S[PENDEXT] = lo
                S[PENDEXTBAR] = bar
                S[PENDEFF] = _pmax(_nz(S[PENDEFF], 0.0), eff)
                S[PENDSPR] = _pmax(_nz(S[PENDSPR], 0.0), spr)
            elif S[PENDEDGE] == DIR_DIST and hi > S[PENDEXT]:
                S[PENDEXT] = hi
                S[PENDEXTBAR] = bar
                S[PENDEFF] = _pmax(_nz(S[PENDEFF], 0.0), eff)
                S[PENDSPR] = _pmax(_nz(S[PENDSPR], 0.0), spr)
            rec_age = bar - S[PENDSTART]
            if S[PENDEDGE] == DIR_ACCUM:
                recovered = cl > r_l2
                depth = r_l2 - S[PENDEXT]
                rec_sc = ((1 if cpos >= 0.55 else 0) + (1 if eff <= P[t, R_AVG] * 1.50 else 0)
                          + (1 if cl > P[t, R_O] else 0) + (1 if spr >= a * 0.50 else 0))
            else:
                recovered = cl < r_h2
                depth = S[PENDEXT] - r_h2
                rec_sc = ((1 if cpos <= 0.45 else 0) + (1 if eff <= P[t, R_AVG] * 1.50 else 0)
                          + (1 if cl < P[t, R_O] else 0) + (1 if spr >= a * 0.50 else 0))
            depth_ok = depth >= a * 0.15 and depth <= a * 2.5
            if recovered and depth_ok and rec_age <= rec_limit2 and rec_sc >= 3:
                probe_edge = S[PENDEDGE]
                exc_out = int(probe_edge)
                excpx_out = S[PENDEXT]
                if S[PHASE] == PH_B and not mature2:
                    S[PROVEDGE] = probe_edge
                    S[PROVBAR] = S[PENDEXTBAR]
                    S[PROVPX] = S[PENDEXT]
                    S[PROVEFF] = S[PENDEFF]
                    S[PROVSPR] = S[PENDSPR]
                    S[LASTACT] = bar
                    S[PEND] = 0.0
                else:
                    if S[PHASE] == PH_C:
                        _clear_terminal(S)
                    _exc_from_pend(S, bar, tm)
                    sig |= BIT_SPRING if probe_edge == DIR_ACCUM else BIT_UTAD
            elif rec_age > rec_limit2 or (not depth_ok and depth > a * 2.5):
                if S[PHASE] == PH_B:
                    S[LASTBAD] = bar
                S[PEND] = 0.0
                S[PENDCOOL] = bar + p2
        if S[PHASE] == PH_C and S[EXC] != 0.0 and S[EXCTESTED] == 0.0 and rk2:
            if S[OUTC] == DIR_ACCUM and lo < S[EXCPX] and lo >= r_l2 - a * 2.5:
                S[EXCPX] = lo
                S[EXCBAR] = bar
                S[EXCEFF] = _pmax(_nz(S[EXCEFF], 0.0), eff)
                S[EXCSPR] = _pmax(_nz(S[EXCSPR], 0.0), spr)
            elif S[OUTC] == DIR_DIST and hi > S[EXCPX] and hi <= r_h2 + a * 2.5:
                S[EXCPX] = hi
                S[EXCBAR] = bar
                S[EXCEFF] = _pmax(_nz(S[EXCEFF], 0.0), eff)
                S[EXCSPR] = _pmax(_nz(S[EXCSPR], 0.0), spr)

        # ── L1613-1641: SOS / SOW, C -> D ──
        if S[PHASE] == PH_C and rk2 and S[PEND] == 0.0:
            c_min_d = _phase_c_to_d_min(p2)
            c_formal = S[EXC] == 0.0 or S[EXCTESTED] != 0.0
            c_anchor = S[CREADY] if S[CREADY] == S[CREADY] else S[EXCBAR]
            c_age_ready = c_anchor == c_anchor and bar - c_anchor >= c_min_d
            c_val = _validation(S, p2, trend, a, bar, mintick)
            c_val_d = c_val if c_formal else min(100, c_val + 13)
            c_conf = _conf(S)
            c_conf_d = c_conf if c_formal else min(100, c_conf + 30)
            c_ht = _pmax(r_h2 - r_l2, mintick)
            if c_age_ready and c_val_d >= 60 and c_conf_d >= 45:
                if S[OUTC] == DIR_ACCUM and age_ok_bull:
                    dom_up = r_l2 + c_ht * 0.65
                    brk_up = cl > r_h2 + a * 0.15
                    if c_formal:
                        dom_ok = brk_up or (cl >= dom_up and P[t, R_C1] >= dom_up)
                    else:
                        dom_ok = brk_up or (cl >= dom_up and P[t, R_C1] >= dom_up and P[t, R_C2] >= dom_up)
                    req = 3 if c_formal else 2
                    q_up = P[t, R_SOS] >= req or P[t, R_MBSOS] != 0.0 or (not c_formal and P[t, R_RES3UP] >= 1.0)
                    if dom_ok and q_up:
                        _promote_d(S, DIR_ACCUM, bar, tm)
                        sig |= BIT_SOS
                elif S[OUTC] == DIR_DIST and age_ok_bear:
                    dom_dn = r_h2 - c_ht * 0.65
                    brk_dn = cl < r_l2 - a * 0.15
                    if c_formal:
                        dom_ok = brk_dn or (cl <= dom_dn and P[t, R_C1] <= dom_dn)
                    else:
                        dom_ok = brk_dn or (cl <= dom_dn and P[t, R_C1] <= dom_dn and P[t, R_C2] <= dom_dn)
                    req = 3 if c_formal else 2
                    q_dn = P[t, R_SOW] >= req or P[t, R_MBSOW] != 0.0 or (not c_formal and P[t, R_RES3DN] >= 1.0)
                    if dom_ok and q_dn:
                        _promote_d(S, DIR_DIST, bar, tm)
                        sig |= BIT_SOW

        # ── L1643-1676: B -> D directly (adopting a provisional excursion), or departure ──
        reset_late = -1
        if S[PHASE] == PH_B and rk2 and S[PEND] == 0.0:
            d_ht = _pmax(r_h2 - r_l2, mintick)
            d_buf = _pmax(d_ht * 0.35, a * 0.75)
            up_acc = cl > r_h2 + a * 0.15 and P[t, R_C1] > r_h2 + a * 0.15
            dn_acc = cl < r_l2 - a * 0.15 and P[t, R_C1] < r_l2 - a * 0.15
            up_sus = P[t, R_LOC3] > r_h2 + d_buf
            dn_sus = P[t, R_HIC3] < r_l2 - d_buf
            up_go = (up_acc and (P[t, R_SOS] >= 3 or P[t, R_MBSOS] != 0.0)) or up_sus
            dn_go = (dn_acc and (P[t, R_SOW] >= 3 or P[t, R_MBSOW] != 0.0)) or dn_sus
            prov_limit = _idle_limit(PH_C, True, p2)
            if up_go and not dn_go:
                up_prov = (S[PROVEDGE] == DIR_ACCUM and S[PROVBAR] == S[PROVBAR]
                           and bar - S[PROVBAR] <= prov_limit)
                if age_ok_bull and up_prov and mature2:
                    _adopt_prov(S)
                    _promote_d(S, DIR_ACCUM, bar, tm)
                    sig |= BIT_SPRING | BIT_SOS
                elif up_sus and not up_prov:
                    reset_late = RS_DEPART
            elif dn_go and not up_go:
                dn_prov = (S[PROVEDGE] == DIR_DIST and S[PROVBAR] == S[PROVBAR]
                           and bar - S[PROVBAR] <= prov_limit)
                if age_ok_bear and dn_prov and mature2:
                    _adopt_prov(S)
                    _promote_d(S, DIR_DIST, bar, tm)
                    sig |= BIT_UTAD | BIT_SOW
                elif dn_sus and not dn_prov:
                    reset_late = RS_DEPART
        if reset_late >= 0:
            S[:] = TPL
            used[:] = False

        # ── L1678-1693: a later SOS / SOW after the LPS / LPSY ──
        if S[PHASE] == PH_D and S[OUTC] == DIR_ACCUM and S[EV] == EV_LPS and S[RHI] == S[RHI]:
            if cl > S[RHI] + a * 0.15 and P[t, R_RELE] >= 1.15 and cpos >= 0.65:
                S[STRBAR] = bar
                _set_event(S, EV_SOS, bar, tm)
                sig |= BIT_SOS
        if S[PHASE] == PH_D and S[OUTC] == DIR_DIST and S[EV] == EV_LPSY and S[RLO] == S[RLO]:
            if cl < S[RLO] - a * 0.15 and P[t, R_RELE] >= 1.15 and cpos <= 0.35:
                S[STRBAR] = bar
                _set_event(S, EV_SOW, bar, tm)
                sig |= BIT_SOW

        # ── L1696-1727: acceptance into Phase E ──
        if S[PHASE] == PH_D and S[RHI] == S[RHI] and S[RLO] == S[RLO]:
            e_conf = _conf(S)
            d_age = bar - S[DSTART] if S[DSTART] == S[DSTART] else 0.0
            d_min = _phase_d_min(live if S[PIVLEN] != S[PIVLEN] else int(S[PIVLEN]))
            if S[OUTC] == DIR_ACCUM:
                e_opp_ok = regime != REGIME_MARKDOWN or S[CFLPS] != 0.0
                e_std = (S[CFLPS] != 0.0 and S[LPSBAR] == S[LPSBAR] and bar - S[LPSBAR] >= 3 and d_age >= d_min
                         and P[t, R_LOC3] > S[RHI] and e_conf >= 55)
                e_dir = (S[CFLPS] == 0.0 and d_age >= max(d_min, 5) and P[t, R_LOC5] > S[RHI]
                         and e_conf >= 75)
                if (e_std or e_dir) and e_opp_ok:
                    S[CFACCEPT] = 1.0
                    S[PHASE] = PH_E
                    S[ESTART] = bar
                    regime = REGIME_MARKUP
                    _set_event(S, EV_MARKUP, bar, tm)
                    sig |= BIT_E
            elif S[OUTC] == DIR_DIST:
                e_opp_ok = regime != REGIME_MARKUP or S[CFLPS] != 0.0
                e_std = (S[CFLPS] != 0.0 and S[LPSBAR] == S[LPSBAR] and bar - S[LPSBAR] >= 3 and d_age >= d_min
                         and P[t, R_HIC3] < S[RLO] and e_conf >= 55)
                e_dir = (S[CFLPS] == 0.0 and d_age >= max(d_min, 5) and P[t, R_HIC5] < S[RLO]
                         and e_conf >= 75)
                if (e_std or e_dir) and e_opp_ok:
                    S[CFACCEPT] = 1.0
                    S[PHASE] = PH_E
                    S[ESTART] = bar
                    regime = REGIME_MARKDOWN
                    _set_event(S, EV_MARKDOWN, bar, tm)
                    sig |= BIT_E

        # ── L1729-1747: the entry check, once per campaign and mode ──
        e_val = -1
        if S[OUTC] != 0.0:
            conf = _conf(S)
            e_val = _validation(S, live if S[PIVLEN] != S[PIVLEN] else int(S[PIVLEN]), trend, a, bar, mintick)
            test_bit = (sig & (BIT_TEST | BIT_CTEST)) != 0
            strength_bit = (sig & (BIT_SOS | BIT_SOW)) != 0
            lps_bit = (sig & (BIT_LPS | BIT_LPSY)) != 0
            for m in range(3):
                if used[m]:
                    continue
                if m == 0:
                    min_conf, min_tests, floor = 60, 6, 50
                elif m == 1:
                    min_conf, min_tests, floor = 55, 5, 50
                else:
                    min_conf, min_tests, floor = 75, 7, 60
                ready = _readiness(S, min_conf, floor, a, bar, cl, tm, tfms, mintick)
                quality = conf >= min_conf and e_val >= floor and ready >= min_tests
                if m == 0:
                    fire = (test_bit and quality and S[TESTSCORE] >= 2) or (lps_bit and quality)
                elif m == 1:
                    fire = (test_bit and quality) or (strength_bit and quality and S[TESTTIME] != S[TESTTIME])
                else:
                    fire = lps_bit and quality
                if fire:
                    used[m] = True
                    o_entry[t, m] = int(S[OUTC])

        # ── the bar's outputs ──
        o_phase[t] = int(S[PHASE])
        o_outc[t] = int(S[OUTC])
        o_camp[t] = int(S[START]) if S[PHASE] != PH_NONE and S[START] == S[START] else -1   # s.startBar
        o_rlo[t] = S[RLO]
        o_rhi[t] = S[RHI]
        o_hlo[t] = _hard_level(S, DIR_ACCUM)
        o_hhi[t] = _hard_level(S, DIR_DIST)
        o_sig[t] = sig
        o_clpx[t] = clpx_out
        o_exc[t] = exc_out
        o_excpx[t] = excpx_out
        o_incde[t] = S[PHASE] >= PH_C and S[OUTC] != 0.0 and not demoted
        o_dbg[t, D_PLEN] = p_len
        o_dbg[t, D_TREND] = trend
        o_dbg[t, D_PH] = ph
        o_dbg[t, D_PL] = pl
        o_dbg[t, D_NEWPH] = 1.0 if new_ph else 0.0
        o_dbg[t, D_NEWPL] = 1.0 if new_pl else 0.0
        o_dbg[t, D_RESET] = reset_why
        o_dbg[t, D_RESETLATE] = reset_late
        o_dbg[t, D_DEMOTED] = 1.0 if demoted else 0.0
        o_dbg[t, D_MATURE1] = 1.0 if mature1 else 0.0
        o_dbg[t, D_CONF] = _conf(S) if S[STOP] != 0.0 else 0.0
        o_dbg[t, D_VAL] = e_val
    G[G_REGIME] = regime
    G[G_LASTPL] = last_pl_bar
    G[G_LASTPH] = last_ph_bar
    for m in range(3):
        G[G_USED + m] = 1.0 if used[m] else 0.0


# ───────────────────────────── the stateless series (numpy) ─────────────────────────────

def _arr(x, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)          # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    return a


def _nz_arr(x: np.ndarray, y) -> np.ndarray:
    return np.where(np.isnan(x), y, x)


def pine_round(x) -> np.ndarray:
    """``math.round`` on an array: ties up (see ``_round``)."""
    x = np.asarray(x, np.float64)
    f = np.floor(x)
    return np.where(x - f >= 0.5, f + 1.0, f)


def highest(x, n: int) -> np.ndarray:
    """``ta.highest(x, n)``: the largest of the last n values; na until n values exist."""
    x = np.asarray(x, np.float64)
    out = np.full(len(x), NAN)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).max(axis=1)
    return out


def lowest(x, n: int) -> np.ndarray:
    """``ta.lowest(x, n)``: the smallest of the last n values; na until n values exist."""
    x = np.asarray(x, np.float64)
    out = np.full(len(x), NAN)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).min(axis=1)
    return out


def adaptive_len(a) -> np.ndarray:
    """``liveLen`` (L1085-1088): ``clamp(int(math.round(pivotLen * a / ta.sma(a, 50))), 2, 10)``, with
    ``aRatio = 1`` while ``nz(aBase)`` is not above 0 (the first 49 bars), so 4 there."""
    a = np.asarray(a, np.float64)
    a_base = I.sma(a, 50)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(_nz_arr(a_base, 0.0) > 0.0, a / a_base, 1.0)
    return np.clip(pine_round(PIVOT_LEN * ratio), SWING_MIN, SWING_MAX)


def pivots(x, length: int, high: bool, ties: str = "strict") -> np.ndarray:
    """
    ``ta.pivothigh(x, length, length)`` (``high``) or ``ta.pivotlow``: on bar t, x[t - length] if it is strictly
    above (below) the other 2 * length values of x[t - 2 length .. t], else na; na before bar 2 * length. ``ties``
    measures the undocumented tie rule only: "left" accepts equal values on the left (older) side, "right" on the
    right (newer) side; the port uses "strict".
    """
    x = np.asarray(x, np.float64)
    m, L = len(x), int(length)
    out = np.full(m, NAN)
    w = 2 * L + 1
    if L < 1 or m < w:
        return out
    win = sliding_window_view(x, w)
    cen = win[:, L][:, None]
    left, right = win[:, :L], win[:, L + 1:]
    if ties not in ("strict", "left", "right"):
        raise ValueError(f"ties: 'strict', 'left' or 'right', got {ties!r}")
    if high:
        ok_l = (cen >= left) if ties == "left" else (cen > left)
        ok_r = (cen >= right) if ties == "right" else (cen > right)
    else:
        ok_l = (cen <= left) if ties == "left" else (cen < left)
        ok_r = (cen <= right) if ties == "right" else (cen < right)
    ok = ok_l.all(axis=1) & ok_r.all(axis=1)
    out[w - 1:] = np.where(ok, win[:, L], NAN)
    return out


def trend_parts(c, a, sma200, live, mintick: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                                                               np.ndarray]:
    """
    The parts of ``f_priorTrendScore(trendBars, trendEnd, a, ph, pl, longSma)`` (L573-613, L1117-1119) that do not
    depend on the pivots: per bar ``n`` = trendBars, ``e`` = trendEnd, ``valid`` (close[e + n] exists), ``base`` =
    ``disp + erPart`` and ``smaPart``, with the source's order of operations (the path is summed oldest first, as the
    loop ``for k = n - 1 to 0`` adds it).
    """
    c = np.asarray(c, np.float64)
    m = len(c)
    L = np.asarray(live, np.int64)
    tb_n = np.clip(pine_round(L * 8.0).astype(np.int64), 25, 200)        # L1117: priorTrendPivotFactor 8, 25..200
    tb_e = np.clip(pine_round(L * 0.75).astype(np.int64), 2, 8)           # L1118
    idx = np.arange(m)
    valid = idx - tb_e - tb_n >= 0
    d = np.zeros(m)
    if m > 1:
        d[1:] = np.abs(c[1:] - c[:-1])                                   # |close[o] - close[o + 1]|, at bar t - o
    base = np.zeros(m)
    sma_part = np.zeros(m)
    for lv in np.unique(L):
        rows = np.flatnonzero((L == lv) & valid)
        if not len(rows):
            continue
        nn, ee = int(tb_n[rows[0]]), int(tb_e[rows[0]])
        c_end, c_start = c[rows - ee], c[rows - ee - nn]
        unit_a = np.maximum(a[rows - ee], mintick)                       # max(nz(_atrS[e], _atrS), mintick)
        net = c_end - c_start
        disp = np.maximum(-3.0, np.minimum(3.0, net / (unit_a * math.sqrt(nn)))) * 15.0
        path = np.zeros(len(rows))
        for k in range(nn - 1, -1, -1):
            path = path + d[rows - ee - k]
        with np.errstate(divide="ignore", invalid="ignore"):
            er = np.where(path > 0, np.abs(net) / path, 0.0)
        er_part = np.where(net >= 0, 1.0, -1.0) * er * 25.0
        base[rows] = disp + er_part
        s_end, s_start = sma200[rows - ee], sma200[rows - ee - nn]
        both = ~np.isnan(s_end) & ~np.isnan(s_start)
        with np.errstate(invalid="ignore"):
            sgn = np.where(s_end > s_start, 10.0, np.where(s_end < s_start, -10.0, 0.0))
        sma_part[rows] = np.where(both, sgn, 0.0)
    return tb_n, tb_e, valid, base, sma_part


def series(o, h, l, c, v, t, no_vol: bool = False, mintick: float = DEFAULT_MINTICK,
           pivot_ties: str = "strict") -> Dict[str, np.ndarray]:
    """
    Every per-bar series of ``f_engine`` that does not depend on the campaign state (L1063-1158, the trend score's
    stateless parts, the pivot candidates of every length 2..10), by name. ``P`` packs them for the kernel.
    """
    o, h, l, c = _arr(o, "open"), _arr(h, "high"), _arr(l, "low"), _arr(c, "close")
    n = len(c)
    if not len(o) == len(h) == len(l) == n:
        raise ValueError("open, high, low, close: series of equal length are expected")
    if np.isnan(o).any() or np.isnan(h).any() or np.isnan(l).any() or np.isnan(c).any():
        raise ValueError("prices: na is not expected")
    tt = _arr(t, "t")
    if len(tt) != n:
        raise ValueError("t: one open time per bar is expected")
    if no_vol:
        raw = np.zeros(n)
    else:
        raw = _nz_arr(_arr(v, "volume"), 0.0)                               # L1063: nz(volume)
        if len(raw) != n:
            raise ValueError("volume: one value per bar is expected")
    mintick = float(mintick)
    with np.errstate(invalid="ignore", divide="ignore"):
        no_v = np.cumsum(raw) <= 0.0                                     # L1064: ta.cum(rawVol) <= 0
        spr = np.maximum(h - l, mintick)                                 # L1065
        eff = np.where(no_v, spr, raw)                                   # L1066
        avg_raw = I.sma(eff, 50)                                         # L1067
        avg = _nz_arr(avg_raw, eff)                                      # L1068
        avg_prev = _nz_arr(I.hist(avg_raw, 1), avg)                      # L1069
        atr_raw = I.atr(h, l, c, 14)                                     # L1070
        a = _nz_arr(atr_raw, spr)                                        # L1071
        a_prev = _nz_arr(I.hist(atr_raw, 1), a)                          # L1072
        unit = np.maximum(a, mintick)                                    # L1073
        cpos = (c - l) / spr                                             # L1074
        rel_e = eff / np.maximum(avg, 1e-10)                             # L1075
        spr_atr = spr / unit                                             # L1076
        recent_eff = I.sma(eff, 3)                                       # L1077-1079
        recent_low = lowest(l, 3)
        recent_high = highest(h, 3)
        prior_lo = I.hist(lowest(l, 30), 1)                              # L1080-1082
        prior_hi = I.hist(highest(h, 30), 1)
        eff_hi_prior = I.hist(highest(eff, 30), 1)
        new_low = ~np.isnan(prior_lo) & (l <= prior_lo)                  # L1083-1084
        new_high = ~np.isnan(prior_hi) & (h >= prior_hi)
        live = adaptive_len(a)                                           # L1085-1088
        pre = _nz_arr(I.hist(live, 3), live)                             # L1089
        sma200 = I.sma(c, 200)                                           # L1116
        tb_n, tb_e, tb_valid, tb_base, tb_sma = trend_parts(c, a, sma200, live, mintick)
        mb_low = lowest(l, 5)                                            # L1148-1152
        mb_high = highest(h, 5)
        mb_eff = I.math_sum(eff, 5) / np.maximum(avg * 5, 1e-10)
        mb_sos = ((c - mb_low) / unit >= 2.0) & (mb_eff >= 1.10) & (cpos >= 0.50)
        mb_sow = ((mb_high - c) / unit >= 2.0) & (mb_eff >= 1.10) & (cpos <= 0.50)
        c3 = _nz_arr(I.hist(c, 3), c)
        res3_up = np.maximum(c - c3, 0.0) / unit                         # L1153-1154
        res3_dn = np.maximum(c3 - c, 0.0) / unit
        sos = ((rel_e >= 1.15).astype(np.int64) + (spr_atr >= 1.15) + (cpos >= 0.65)    # L1155-1156
               + ((c > o) & (c - o >= a * 0.50)))
        sow = ((rel_e >= 1.15).astype(np.int64) + (spr_atr >= 1.15) + (cpos <= 0.35)
               + ((c < o) & (o - c >= a * 0.50)))
    cols = {"O": o, "H": h, "L": l, "C": c, "T": tt * 1000.0, "SPR": spr, "EFF": eff, "AVGRAW": avg_raw, "AVG": avg,
            "AVGPREV": avg_prev, "ATRRAW": atr_raw, "A": a, "APREV": a_prev, "CPOS": cpos, "RELE": rel_e,
            "REFF": recent_eff, "RLOW": recent_low, "RHIGH": recent_high, "EFFHI": eff_hi_prior,
            "NEWLOW": new_low, "NEWHIGH": new_high, "LIVE": live, "PRE": pre, "TBVALID": tb_valid,
            "TBBASE": tb_base, "TBSMA": tb_sma, "TBN": tb_n, "TBE": tb_e, "HIC2": highest(c, 2),
            "LOC2": lowest(c, 2), "HIC3": highest(c, 3), "LOC3": lowest(c, 3), "HIC5": highest(c, 5),
            "LOC5": lowest(c, 5), "MBSOS": mb_sos, "MBSOW": mb_sow, "RES3UP": res3_up, "RES3DN": res3_dn,
            "SOS": sos, "SOW": sow, "C1": _nz_arr(I.hist(c, 1), c), "C2": _nz_arr(I.hist(c, 2), c)}
    P = np.empty((n, NR))
    for k, name in enumerate(_ROWS):
        P[:, k] = np.asarray(cols[name], np.float64)
    phc = np.full((n, SWING_MAX + 1), NAN)
    plc = np.full((n, SWING_MAX + 1), NAN)
    for L in range(SWING_MIN, SWING_MAX + 1):
        phc[:, L] = pivots(h, L, True, pivot_ties)
        plc[:, L] = pivots(l, L, False, pivot_ties)
    out = {k.lower(): np.asarray(v_) for k, v_ in cols.items()}
    out.update({"unit": unit, "spr_atr": spr_atr, "sma200": sma200, "prior_lo": prior_lo, "prior_hi": prior_hi,
                "no_vol": no_v, "mb_eff": mb_eff, "P": P, "PHC": phc, "PLC": plc})
    return out


def infer_tf_seconds(t) -> float:
    """``timeframe.in_seconds(timeframe.period)`` from the open times: their smallest positive step (3600 when
    there are fewer than two bars). It only scales the readiness count's ``ageBars``, which cannot change an output
    (module docstring)."""
    tt = np.asarray(t, np.float64)
    d = np.diff(tt)
    d = d[d > 0]
    return float(d.min()) if len(d) else 3600.0


def new_state() -> Tuple[np.ndarray, np.ndarray]:
    """The state before the first bar: ``WS.new()`` and the variables outside it (regime none, no pivot yet, the
    entry slots free)."""
    G = np.zeros(NG)
    G[G_LASTPL] = NAN
    G[G_LASTPH] = NAN
    return TEMPLATE.copy(), G


def run(pre: Dict[str, np.ndarray], S: np.ndarray, G: np.ndarray, start: int = 0, stop=None,
        mintick: float = DEFAULT_MINTICK, tf_seconds: float = 3600.0, python: bool = False) -> Dict[str, np.ndarray]:
    """The kernel over bars [start, stop) of ``pre`` (``series``) from the state (S, G), modified in place; every
    output and the debug columns, NaN / 0 outside the span. ``python``: run the kernel's plain Python body (with the
    compiled helpers), a check of the compilation."""
    P = np.ascontiguousarray(pre["P"], np.float64)
    n = P.shape[0]
    stop = n if stop is None else int(stop)
    if not 0 <= int(start) <= stop <= n:
        raise ValueError(f"span [{start}, {stop}) outside the {n} bars")
    if S.shape != (NF,) or G.shape != (NG,):
        raise ValueError("S and G: the arrays of new_state()")
    phase = np.zeros(n, np.int8)
    outc = np.zeros(n, np.int8)
    camp = np.full(n, -1, np.int32)
    rlo, rhi, hlo, hhi = (np.full(n, NAN) for _ in range(4))
    sig = np.zeros(n, np.int64)
    clpx = np.full(n, NAN)
    exc = np.zeros(n, np.int8)
    excpx = np.full(n, NAN)
    entry = np.zeros((n, 3), np.int8)
    incde = np.zeros(n, np.bool_)
    dbg = np.full((n, ND), NAN)
    kernel = getattr(_kernel, "py_func", _kernel) if python else _kernel
    kernel(P, np.ascontiguousarray(pre["PHC"]), np.ascontiguousarray(pre["PLC"]), TEMPLATE, S, G, int(start), stop,
           float(mintick), float(tf_seconds) * 1000.0, phase, outc, camp, rlo, rhi, hlo, hhi, sig, clpx, exc, excpx,
           entry, incde, dbg)
    out: Dict[str, np.ndarray] = {"phase": phase, "outcome": outc, "campaign": camp, "range_lo": rlo,
                                  "range_hi": rhi, "hard_lo": hlo, "hard_hi": hhi}
    for k, b in EVENT_BITS.items():
        out[k] = (sig & b) != 0
    out["climax"] = (out["ev_sc"].astype(np.int8) - out["ev_bc"].astype(np.int8)).astype(np.int8)
    out["climax_px"] = clpx
    out["exc"] = exc
    out["exc_px"] = excpx
    for m, name in enumerate(MODES):
        out[f"entry_{name}"] = np.ascontiguousarray(entry[:, m])
    out["in_cde"] = incde
    out["sig"] = sig
    for k, name in enumerate(_DEBUG):
        out[f"dbg_{name}"] = dbg[:, k]
    return out


def wyckoff(o, h, l, c, v, t, no_vol: bool = False, *, mintick: float = DEFAULT_MINTICK,
            tf_seconds=None) -> Dict[str, np.ndarray]:
    """
    The script's engine on the chart timeframe from the first bar given, every input at its default: the per-bar
    outputs of the module docstring (exactly ``CONTRACT_KEYS``).

    ``o, h, l, c``: the bid OHLC; ``v``: the volume the script reads (gold: tick volume; BTC: Binance volume,
    ``tradeiq_market.binance_volume``), NaN counted as 0; ``t``: the bars' open times, UTC seconds; ``no_vol``: zero
    volume, the script's fallback (effort = range). ``mintick``: ``syminfo.mintick`` (``MINTICK[symbol]``; the
    default is gold's). ``tf_seconds``: the chart's timeframe (default: the smallest step of ``t``), immaterial.
    """
    pre = series(o, h, l, c, v, t, no_vol=no_vol, mintick=mintick)
    tf = infer_tf_seconds(t) if tf_seconds is None else float(tf_seconds)
    S, G = new_state()
    out = run(pre, S, G, 0, None, mintick=mintick, tf_seconds=tf)
    return {k: out[k] for k in CONTRACT_KEYS}
