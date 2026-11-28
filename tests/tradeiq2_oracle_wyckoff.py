"""
PORT B (the oracle) of "Wyckoff [theUltimator5]" (TradingView, Pine v6), for study 2 of the TradeIQ research
(``backtest_results/tradeiq_2027/PREREG.md`` 6.3; the specification is the study's ``maps/wyckoff.md``).

Port A is ``backtesting/research/tradeiq2_ind_wyckoff.py``; this file was written independently of it, from the Pine
source and the specification only. It is the reference port A is checked against, so it is written to be obviously
correct rather than fast: one plain-Python loop over the bars, one history list per Pine series, every ``ta.*``
built-in re-derived from that history on every bar, and the script's engine ``f_engine`` (source lines 1060-1764)
transcribed statement by statement in the script's own order, with its own names. Line numbers below refer to the
study's copy of the source (``Wyckoff Indicator Code.txt``, 3,199 lines). The Pine source is third-party code and is
not reproduced here: only its identifiers and line numbers are cited.

What is computed
----------------
``wyckoff(o, h, l, c, v, t, no_vol=False)`` runs the engine on the chart timeframe only (the call of line 1795), from
the first bar given, every input at the script's default (lines 7-31; only ``entryStrictness``, line 28, reaches the
engine, and the three modes are evaluated side by side, see "Entries" below). It returns a dict of arrays, one value
per bar, each taken at the CLOSE of the bar, after the whole engine has run on it:

=================  =======  ==========================================================================================
key                dtype    meaning
=================  =======  ==========================================================================================
phase              int8     ``s.phase``: 0 none, 1 A, 2 B, 3 C, 4 D, 5 E (lines 193-198)
outcome            int8     ``s.outcome``: +1 accumulation, -1 distribution, 0 none
campaign           int32    the bar index of the climax that seeded the campaign (``s.startBar``, line 734), -1 none
range_lo/range_hi  float    ``s.rangeLow`` / ``s.rangeHigh`` (NaN while na)
hard_lo/hard_hi    float    ``f_hardLevel(s, DIR_ACCUM)`` / ``f_hardLevel(s, DIR_DIST)`` (lines 723-729): the spring
                            (UTAD) extreme when the campaign has one and holds that outcome, otherwise
                            min(origLow, rangeLow) (max(origHigh, rangeHigh)); NaN when na
ev_sc ... ev_lpsy  bool     the bar's alert bits ``sig`` (lines 242-255, 3188-3197): ev_sc / ev_bc = BIT_SC / BIT_BC
ev_phase_e                  ("climax confirmed", the absorption bar), ev_ar, ev_st, ev_spring, ev_utad, ev_test,
                            ev_ctest (BIT_CTEST, either side), ev_sos, ev_sow, ev_lps, ev_lpsy, ev_phase_e (BIT_E).
                            True on the bar where the event becomes KNOWN (the bar whose close sets the bit), never
                            on the bar where the script later draws it
climax/climax_px   int8/f   +1 on a BIT_SC bar, -1 on a BIT_BC bar; climax_px = the climax bar's extreme
                            (``s.climaxPrice``) on those bars, NaN elsewhere
exc/exc_px         int8/f   +1 / -1 on the recovery bar of a spring / UTAD probe (lines 1574-1591), whether it is
                            stored as provisional (Phase B not mature, 1576-1586) or confirmed (``f_excFromPend``);
                            exc_px = the probe's extreme (``s.pendExt``) at that bar. A provisional spring adopted
                            later (B -> D, 1655-1660) sets ev_spring on the adoption bar but no exc there (its
                            recovery bar was earlier). Later extensions of an untested spring (1598-1610) move
                            hard_lo, not exc_px
entry_std/agg/con  int8     +1 / -1 on the bar where the script's entry alert fires (lines 2236-2238, 3198-3199) with
                            ``entryStrictness`` = Standard / Aggressive / Conservative, 0 otherwise
in_cde             bool     the campaign holds an outcome in Phases C-E at the bar's close AND no outcome was lost
                            during the bar (no reset, re-seed or demotion of a campaign that held one). For the X-S
                            exit: a trade entered at bar i leaves at the close of the first bar j > i with
                            ``in_cde[j] == False`` (any break of the entry's campaign or outcome makes that bar False,
                            and a new outcome can only appear after such a bar). It differs from "outcome != 0" only
                            on a bar that loses an outcome and gains one again: on our bars once, BTC 1H (Binance)
                            2023-11-22 00:00, a Phase D demotion and a spring on the same bar (the campaign of the
                            2023-11-17 19:00 Standard long)
=================  =======  ==========================================================================================

Inputs: ``o, h, l, c`` the bid OHLC; ``v`` the volume (gold: tick volume; BTC: Binance volume,
``tradeiq_market.binance_volume(mk, tf)[0]``; NaN is read as 0, ``nz(volume)``, line 1063); ``t`` the bar OPEN times
in UTC epoch seconds (as ``TBars.t``; Pine's ``time`` is that times 1000). ``no_vol=True`` passes zero volume: the
script's own fallback, effort = the bar's range (lines 1064-1066). ``mintick`` (keyword): ``syminfo.mintick``, used
only as a floor in ``max(x, syminfo.mintick)``; default None = the coarsest decimal grid all the prices lie on (0.001
on our gold bars, 0.01 on BTC, equal to ``backtesting/config.py``'s digits); pass ``mk.tick`` to be explicit. It
only reaches a value on bars with high == low (spr = mintick; to mid-2024: 41 gold 1H, 3 gold 4H, 2 BTC 1H bars).

What is known when (no look-ahead)
----------------------------------
Every output at bar i is a function of bars 0..i only: the loop sees the bars one at a time, every series reference
``x[k]`` reads the history list k entries back, and pivots are reported pLen bars after the pivot bar (they are known
at the close of bar ``pivBar + pLen``, line 1106-1108). The state only advances inside ``if _commit`` (line 1162) and
``_commit = barstate.isconfirmed`` (line 1795) is true on every historical bar, so a backtest may act on the outputs
at the close of their bar. The script's labels, phase letters, schematics and higher-timeframe override (lines
1766-3184) are drawn back in time or chosen on the last bar; none of them is ported (spec section 2). The only
whole-series inputs are the two defaults: ``mintick`` (the price grid) and the bar spacing used for
``timeframe.in_seconds`` (the modal difference of ``t``); neither can change an output on a regular series (see the
readings).

The Pine readings chosen (where the semantics were not spelled out)
--------------------------------------------------------------------
* na is NaN for int and float fields alike; arithmetic propagates it and every comparison with it is false (Pine's
  rule; Python's float comparisons with NaN are false too). ``nz(x, y)`` returns y for na. ``math.max/min`` return na
  when an argument is na (``pmax``/``pmin``; no engine call can see one, all are guarded). ``!=`` is only applied to
  ints and bools in the engine, so Python's ``nan != x`` never arises.
* ``math.round`` rounds half up, towards +infinity (``pround``; Pine: "ties rounding up"; e.g. recLimit at p = 6 is
  round(4.5) = 5, Python's ``round`` gives 4). Its arguments in the engine are never negative. ``int()`` truncates
  towards zero. Pine v6 divides int by int with a fractional result (``f_hasBit`` line 565, ``f_phaseCToDMinBars``
  line 661); every such quotient is wrapped in ``int()``, so v5's integer division would give the same values.
* ``ta.sma(x, n)``: TradingView's reference code, ``sum += x[i] / n`` for i = 0..n-1 (newest first), na until n bars
  exist (as ``tests/tradeiq_oracle.py``). ``math.sum``: the same without the division. ``ta.highest/lowest(x, n)``:
  na until n bars exist, else the extreme of the last n values. ``ta.cum``: running sum.
* ``ta.atr(14)``: ``ta.rma`` of the true range, TR of bar 0 = high - low (TradingView's reference ``pine_atr``), the
  RMA seeded with the SMA of the first 14 TRs (na before), then ``alpha * tr + (1 - alpha) * prev`` with
  alpha = 1 / 14. ``a = nz(atrRaw, spr)`` (line 1071) is the engine's ATR; ``aPrev`` and ``avgEffPrev`` are the
  previous bar's raw values with the current bar's fallbacks (lines 1069, 1072).
* ``ta.pivothigh(high, pLen, pLen)`` with a series length (lines 1105-1107): evaluated on every bar with that bar's
  pLen, statelessly: the bar pLen bars back is a pivot high when its high is STRICTLY above every high of the pLen bars
  on each side (pivot low: strictly below every low); na when fewer than 2 * pLen + 1 bars exist. TradingView does not
  document ties; strict on both sides is the reading the study logged for the dashboard's pivots (PREREG 6.2). The
  private option ``_ties="nonstrict"`` (>= / <=) exists only to measure the reading.
* ``for k = n - 1 to 0`` (line 590) counts DOWN in Pine (from > to), so ``f_priorTrendScore`` walks its window oldest
  first; ``_phS[o]`` / ``_plS[o]`` are the pivot values as reported o bars back, each found with its own bar's pLen.
* Line 1592 ``recAge > recLimit2 or not depthOK and depth > a * springMaxPenATR`` is
  ``recAge > recLimit2 or ((not depthOK) and depth > 2.5a)``: Pine's precedence is not > and > or.
* Pine v6 evaluates ``and`` / ``or`` lazily; no condition in the engine has a side effect or a ``ta.*`` call, so the
  evaluation order cannot matter.
* Entries (lines 1729-1747): the check writes only ``s.entryTime/entryPrice/entryKind``, which nothing else in the
  engine reads (``na(s.entryTime)`` gates the check itself), so the three strictness modes are evaluated in ONE pass,
  each with its own slot, in place of three runs of the script; the test file checks this against single-mode runs.
  The alert fires when ``int(cEntryT) == time`` (line 2236), i.e. on the bar whose close set the slot, in the
  direction of ``s.outcome`` at that close (``cOut``, lines 2237-2238).
* ``timeframe.in_seconds(timeframe.period)`` (the readiness age, line 961) is the modal spacing of ``t``. It cannot
  change an entry: every entry trigger needs a TEST/CTEST/SOS/SOW/LPS/LPSY bit, each set together with
  ``f_setEvent`` on the same bar, so the age is 0 bars whenever it matters.
* Display-only state (``ctxBull/ctxBear``, the PS/PSY fields, the pivot triplets, ``outCount``, the reset counters)
  is ported too, so the state object is the script's; none of it reaches an output.

Known path dependence (spec risk 12): ``regime`` / ``regimeBar`` (line 1093-1094), the preliminary support fields and
``lastPLBar`` / ``lastPHBar`` live outside the campaign and are never reset, so outputs depend on where the bars start
(gold 4H started 300 bars before 2019 changes events up to 2022-01-04; 1,000 bars or more change nothing). The
regime acts through the Phase E gate (an LPS / LPSY is required after an opposite regime, lines 1702 and 1716) and the
display context: the 25-bar ``ageOKBull`` / ``ageOKBear`` gates (1175-1176) can never block, because Phase C or a
B -> D adoption needs a mature Phase B, at least 6 + 30 = 36 bars after the climax.

Cross-checks made after this port was finished (counts and event geometry only, no profit or loss): every Standard
entry vector of the specification (section 6) is reproduced; on all six main series (gold tick volume, BTC Binance
volume; 1H / 4H / 1D; bars to 2024-06-30) the counts of every alert bit, of the provisional excursions and of the
entries per mode and side equal those of the scratch port ``work/wy_port.py``; the stop distances at the entries
(Standard Test n = 18, median 2.75 ATR; Aggressive SOS n = 14, 4.84; LPS n = 7, 6.79) are the specification's.

Reconciliation with port A (``tests/test_tradeiq2_ind_wyckoff.py``; the study's ``porting/wyckoff.md``): on the real
bars of both symbols from the study's data start (gold 2016-01-03, BTC 2018-01-01) to 2024-06-30, 1H / 4H / 1D, gold
on tick volume and without volume, BTC on Binance and on Exness tick volume, every output above is identical to port
A's, floats bit for bit. So are the engine's internal series this port traces (``Engine.trace``: the bar
measurements, the pivot length, the pivots, the prior-trend score, the reset codes, the maturity, the alert mask). The
one exception is the mask's BIT_PS bit (preliminary support or supply): port A does not port it, and nothing in the
script reads it. The only contract difference, the campaign id, was settled on this port's ``s.startBar``; port A
changed. Nothing in this file had to change.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Dict, Optional, Sequence

import numpy as np

__all__ = [
    "wyckoff", "OUTPUT_KEYS", "EVENT_BITS", "MODES",
    "na", "nz", "pmax", "pmin", "pround", "ptrunc",
    "ta_sma", "ta_sum", "ta_highest", "ta_lowest", "ta_pivothigh", "ta_pivotlow",
    "f_priorTrendScore", "f_structureConfidence", "f_validationScore", "f_causeUnits", "f_testClass",
    "f_phaseAMinBars", "f_phaseBMinBars", "f_phaseCToDMinBars", "f_phaseDMinBars", "f_excursionRecoveryLimit",
    "f_phaseIdleLimit", "f_phaseBCharacterImproving", "f_robustEdge", "f_hardLevel", "f_validationWS", "f_matureWS",
    "f_entryReadinessWS", "f_confWS", "WS", "Bar", "Engine", "infer_mintick",
]

NAN = float("nan")

# ───────────────────────────── the script's constants (lines 53-264) ─────────────────────────────
pivotLen = 4
adaptiveSwingMin = 2
adaptiveSwingMax = 10
adaptiveSwingVolLen = 50
trendLen = 25
priorTrendMaxBars = 200
priorTrendPivotFactor = 8.0
priorTrendStrong = 35.0
priorTrendNeutral = 15.0
continuationTrendLen = 200
oppositeCycleMinBars = 25
extremeLen = 30
phaseAMinBars = 6
phaseAAfterArMaxBars = 45
phaseBIdleMaxBars = 125
phaseCIdleMaxBars = 50
phaseAPrematureDepartureBars = 3
phaseAPrematureDepartureTRFrac = 0.30
phaseAPrematureDepartureATR = 0.75
structureInvalidationATR = 0.50
structureInvalidationBars = 2
phaseBDepartureBars = 3
phaseBDepartureTRFrac = 0.35
phaseBDepartureATR = 0.75
phaseDFailBars = 3
phaseEMaxBars = 300
volLen = 50
atrLen = 14
climaxVolMult = 1.8
climaxSpreadMult = 1.5
relaxedClimaxFactor = 0.80
prelimVolMult = 1.25
prelimExtremeATR = 0.75
prelimEfficiencyLookback = 10
prelimEfficiencyRatio = 0.80
prelimMinScore = 4
scCloseMin = 0.35
bcCloseMax = 0.65
climaxMinScore = 5
climaxAbsorptionMinBars = 3
climaxAbsorptionMaxBars = 8
climaxAbsorptionExtremeATR = 0.50
climaxAbsorptionReboundATR = 0.35
climaxAbsorptionVolFloor = 0.90
minARATR = 2.0
maxARBars = 30
arMaxExtensionATR = 15.0
boundaryTolATR = 0.75
stMaxVolRatio = 0.90
stMaxSpreadRatio = 0.90
stMinScore = 4
minPhaseBBars = 30
minPhaseBTests = 2
minPhaseBOppositeTests = 1
minPhaseBTraversals = 2
phaseBZoneFrac = 0.25
phaseBRangeMinATR = 1.5
phaseBRangeMaxATR = 8.0
phaseBBadTestCooldownFactor = 2.0
phaseBEdgeExpansionCap = 0.15
terminalTestMinBarsAfterST = 3
terminalTestVolRatio = 0.85
terminalTestSpreadRatio = 0.85
terminalTestOtherMaxRatio = 1.05
excursionRecoveryBars = 3
springMinPenATR = 0.15
springMaxPenATR = 2.5
springCloseMin = 0.55
utadCloseMax = 0.45
springEffortMaxMult = 1.50
excursionMinScore = 3
testTolATR = 1.25
testMaxVolRatio = 0.80
testMaxSpreadRatio = 0.80
testExtremeToleranceATR = 0.15
testMinScore = 2
phaseCToDMinBars = 3
phaseDMinBars = 4
phaseDValidationMin = 60
phaseDDominanceFrac = 0.65
breakATR = 0.15
strengthVolMult = 1.15
strengthSpreadATR = 1.15
sosCloseMin = 0.65
sowCloseMax = 0.35
strengthMinScore = 3
sosMultiBarLen = 5
sosMultiBarATR = 2.0
sosMultiBarEffort = 1.10
lpsBoundaryATR = 1.50
lpsVolMult = 1.00
lpsSpreadATR = 1.00
lpsMinScore = 2
confirmBars = 3
directAcceptanceBars = 5
directAcceptanceConfidence = 75
minConfidencePhaseC = 45
minConfidencePhaseD = 55
entryMinConfidenceConservative = 75
entryMinConfidenceStandard = 60
entryMinConfidenceAggressive = 55
entryMinTestsConservative = 7
entryMinTestsStandard = 6
entryMinTestsAggressive = 5

DIR_NONE, DIR_ACCUM, DIR_DIST = 0, 1, -1
REGIME_NONE, REGIME_MARKUP, REGIME_MARKDOWN = 0, 1, -1
PHASE_NONE, PHASE_A, PHASE_B, PHASE_C, PHASE_D, PHASE_E = 0, 1, 2, 3, 4, 5
(EV_NONE, EV_SC, EV_BC, EV_AR, EV_ST, EV_SPRING, EV_UTAD, EV_TEST, EV_SOS, EV_SOW, EV_LPS, EV_LPSY, EV_CTEST_ACC,
 EV_CTEST_DST, EV_MARKUP, EV_MARKDOWN) = range(16)
TEST_NONE, TEST_GOOD, TEST_POOR, TEST_FAILED = 0, 1, 2, 3
ENTRY_NONE, ENTRY_TEST, ENTRY_STRENGTH, ENTRY_LPS, ENTRY_PHASE_E = 0, 1, 2, 3, 4
BIT_PS, BIT_SC, BIT_BC, BIT_AR, BIT_ST = 1, 2, 4, 8, 16
BIT_SPRING, BIT_UTAD, BIT_TEST, BIT_SOS, BIT_SOW = 32, 64, 128, 256, 512
BIT_LPS, BIT_LPSY, BIT_E, BIT_CTEST = 1024, 2048, 4096, 16384
RS_INVALID, RS_ABSORB, RS_NORANGE, RS_DEPART, RS_STALE, RS_DEMOTE, RS_EEND = range(7)

MODES = ("Standard", "Aggressive", "Conservative")          # entryStrictness options (line 28)
ENTRY_KEY = {"Standard": "entry_std", "Aggressive": "entry_agg", "Conservative": "entry_con"}
EVENT_BITS = {"ev_sc": BIT_SC, "ev_bc": BIT_BC, "ev_ar": BIT_AR, "ev_st": BIT_ST, "ev_spring": BIT_SPRING,
              "ev_utad": BIT_UTAD, "ev_test": BIT_TEST, "ev_ctest": BIT_CTEST, "ev_sos": BIT_SOS,
              "ev_sow": BIT_SOW, "ev_lps": BIT_LPS, "ev_lpsy": BIT_LPSY, "ev_phase_e": BIT_E}
OUTPUT_KEYS = ("phase", "outcome", "campaign", "range_lo", "range_hi", "hard_lo", "hard_hi", *EVENT_BITS,
               "climax", "climax_px", "exc", "exc_px", "entry_std", "entry_agg", "entry_con", "in_cde")


# ───────────────────────────── Pine values and arithmetic ─────────────────────────────

def na(x) -> bool:
    """Pine ``na(x)``: this port stores every na (int or float) as NaN."""
    return x is None or (isinstance(x, float) and x != x)


def nz(x, y=0.0):
    """Pine ``nz(x, y)``: y when x is na."""
    return y if na(x) else x


def pmax(a, b):
    """Pine ``math.max(a, b)``: na when either is na."""
    if na(a) or na(b):
        return NAN
    return a if a >= b else b


def pmin(a, b):
    """Pine ``math.min(a, b)``: na when either is na."""
    if na(a) or na(b):
        return NAN
    return a if a <= b else b


def pround(x) -> int:
    """Pine ``math.round(x)``: the nearest integer, ties rounding up (towards +infinity): pround(4.5) == 5,
    pround(2.5) == 3, pround(-2.5) == -2. ``x - floor(x) >= 0.5`` avoids floor(x + 0.5)'s error at
    0.49999999999999994."""
    if na(x):
        raise ValueError("math.round of na: not reachable in the engine")
    f = math.floor(x)
    return int(f) + (1 if x - f >= 0.5 else 0)


def ptrunc(x) -> int:
    """Pine ``int(x)``: truncation towards zero."""
    if na(x):
        raise ValueError("int() of na: not reachable in the engine")
    return int(math.trunc(x))


def f_clamp(v, lo, hi):
    """f_clamp (line 561): math.max(lo, math.min(hi, v))."""
    return pmax(lo, pmin(hi, v))


def f_hasBit(mask: int, bit: int) -> bool:
    """f_hasBit (line 564): int(mask / bit) % 2 == 1."""
    return ptrunc(mask / bit) % 2 == 1


def f_addBit(mask: int, bit: int) -> int:
    """f_addBit (line 567)."""
    return mask if f_hasBit(mask, bit) else mask + bit


# ───────────────────────────── Pine built-ins on a history list ─────────────────────────────
# A history list holds a series' value on every bar so far, oldest first; its last element is the current bar.

def at(s: list, k: int):
    """``s[k]``: the value k bars back (k = 0: the current bar); na before the first bar."""
    i = len(s) - 1 - k
    return s[i] if 0 <= i < len(s) else NAN


def ta_sma(s: list, n: int):
    """``ta.sma(x, n)``: sum of x[i] / n for i = 0 .. n - 1 (newest first); na until n bars exist."""
    if len(s) < n:
        return NAN
    acc = 0.0
    for i in range(n):
        acc = acc + s[len(s) - 1 - i] / n
    return acc


def ta_sum(s: list, n: int):
    """``math.sum(x, n)``: sum of x[i] for i = 0 .. n - 1 (newest first); na until n bars exist."""
    if len(s) < n:
        return NAN
    acc = 0.0
    for i in range(n):
        acc = acc + s[len(s) - 1 - i]
    return acc


def ta_highest(s: list, n: int):
    """``ta.highest(x, n)``: the highest of the last n values; na until n bars exist."""
    if len(s) < n:
        return NAN
    best = s[len(s) - 1]
    for i in range(1, n):
        x = s[len(s) - 1 - i]
        if x > best:
            best = x
    return best


def ta_lowest(s: list, n: int):
    """``ta.lowest(x, n)``: the lowest of the last n values; na until n bars exist."""
    if len(s) < n:
        return NAN
    best = s[len(s) - 1]
    for i in range(1, n):
        x = s[len(s) - 1 - i]
        if x < best:
            best = x
    return best


def ta_pivothigh(s: list, left: int, right: int, ties: str = "strict"):
    """``ta.pivothigh(x, left, right)``: x[right] when it is above each of the ``left`` values before it and each of
    the ``right`` values after it (strictly; ``ties="nonstrict"``: at least as high), else na. na while fewer than
    left + right + 1 bars exist."""
    if len(s) < left + right + 1:
        return NAN
    center = at(s, right)
    for k in range(0, left + right + 1):
        if k == right:
            continue
        x = at(s, k)
        if (x >= center) if ties == "strict" else (x > center):
            return NAN
    return center


def ta_pivotlow(s: list, left: int, right: int, ties: str = "strict"):
    """``ta.pivotlow(x, left, right)``: the mirror of ``ta_pivothigh``."""
    if len(s) < left + right + 1:
        return NAN
    center = at(s, right)
    for k in range(0, left + right + 1):
        if k == right:
            continue
        x = at(s, k)
        if (x <= center) if ties == "strict" else (x < center):
            return NAN
    return center


# ───────────────────────────── the script's helpers (lines 561-975) ─────────────────────────────

class Bar:
    """The built-ins the helpers read on the current bar: ``bar_index``, ``time`` (ms), ``open``, ``high``, ``low``,
    ``close``, ``syminfo.mintick`` and ``timeframe.in_seconds(timeframe.period)``."""
    __slots__ = ("bar_index", "time", "open", "high", "low", "close", "mintick", "tf_secs")

    def __init__(self, bar_index, time, open_, high, low, close, mintick, tf_secs):
        self.bar_index, self.time = bar_index, time
        self.open, self.high, self.low, self.close = open_, high, low, close
        self.mintick, self.tf_secs = mintick, tf_secs


def f_priorTrendScore(E: "Engine", _n: int, _endOff: int) -> float:
    """f_priorTrendScore(trendBars, trendEnd, a, ph, pl, longSma) (lines 573-613), on the engine's histories of
    close, a (``_atrS``), ph, pl and longSma; the current bar is the last element of each."""
    n = max(_n, 2)
    e = max(_endOff, 0)
    cEnd = at(E.close, e)
    cStart = at(E.close, e + n)
    score = 0.0
    if not na(cEnd) and not na(cStart):
        unitA = pmax(nz(at(E.a, e), at(E.a, 0)), E.mintick)
        net = cEnd - cStart
        disp = f_clamp(net / (unitA * math.sqrt(n)), -3.0, 3.0) * 15.0
        path = 0.0
        hh = 0
        ll = 0
        lh = 0
        hl = 0
        lastPH = NAN
        lastPL = NAN
        for k in range(n - 1, -1, -1):                       # for k = n - 1 to 0 (counts down)
            o = e + k
            path += abs(nz(at(E.close, o)) - nz(at(E.close, o + 1), nz(at(E.close, o))))
            vph = at(E.ph, o)
            vpl = at(E.pl, o)
            if not na(vph):
                if not na(lastPH):
                    hh += 1 if vph > lastPH else 0
                    lh += 1 if vph < lastPH else 0
                lastPH = vph
            if not na(vpl):
                if not na(lastPL):
                    hl += 1 if vpl > lastPL else 0
                    ll += 1 if vpl < lastPL else 0
                lastPL = vpl
        er = abs(net) / path if path > 0 else 0.0
        erPart = (1.0 if net >= 0 else -1.0) * er * 25.0
        swings = hh + ll + lh + hl
        swingPart = float(hh + hl - lh - ll) / swings * 20.0 if swings > 0 else 0.0
        smaEnd = at(E.longSma, e)
        smaStart = at(E.longSma, e + n)
        if not na(smaEnd) and not na(smaStart):
            smaPart = 10.0 if smaEnd > smaStart else (-10.0 if smaEnd < smaStart else 0.0)
        else:
            smaPart = 0.0
        score = f_clamp(disp + erPart + swingPart + smaPart, -100.0, 100.0)
    return score


def f_structureConfidence(_prior, _climax, _ar, _st, _cDone, _strength, _lps, _accept) -> int:
    """f_structureConfidence (lines 615-616)."""
    return ((10 if _prior else 0) + (15 if _climax else 0) + (10 if _ar else 0) + (15 if _st else 0)
            + (15 if _cDone else 0) + (15 if _strength else 0) + (10 if _lps else 0) + (10 if _accept else 0))


def f_validationScore(_trend, _absorbed, _rangeATR, _st, _opp, _trav, _clean, _cause, _terminal, _strength, _lps,
                      _accept) -> int:
    """f_validationScore (lines 618-633). ``_accept`` is a parameter the body never reads (as in the script)."""
    v = 0
    v += 10 if abs(_trend) >= priorTrendStrong else (5 if abs(_trend) >= priorTrendNeutral else 0)
    v += 15 if _absorbed else 0
    if _rangeATR >= phaseBRangeMinATR and _rangeATR <= phaseBRangeMaxATR:
        v += 10
    elif _rangeATR >= phaseBRangeMinATR * 0.75 and _rangeATR <= phaseBRangeMaxATR * 1.5:
        v += 5
    v += 15 if _st >= minPhaseBTests else (8 if _st >= 1 else 0)
    v += 15 if (_opp >= 1 and _trav >= 2) else (8 if (_opp >= 1 or _trav >= 1) else 0)
    v += 10 if _clean else 0
    v += 10 if _cause >= 3.0 else (5 if _cause >= 1.5 else 0)
    v += 10 if _terminal else 0
    v += 3 if _strength else 0
    v += 2 if _lps else 0
    return min(v, 100)


def f_causeUnits(_trav, _bAge, _p, _rangeATR) -> float:
    """f_causeUnits (lines 635-638)."""
    timeUnits = float(_bAge) / pmax(float(_p) * 6.0, 1.0)
    widthBonus = 0.5 if _rangeATR >= phaseBRangeMinATR else 0.0
    return timeUnits + float(_trav) * 0.5 + widthBonus


def f_testClass(_near, _holds, _closeOK, _e, _sp, _cE, _cS) -> int:
    """f_testClass (lines 640-649)."""
    r = TEST_NONE
    if _near:
        if not _holds:
            r = TEST_FAILED
        elif _closeOK and _e <= _cE * stMaxVolRatio and _sp <= _cS * stMaxSpreadRatio:
            r = TEST_GOOD
        else:
            r = TEST_POOR
    return r


def f_phaseAMinBars(_p) -> int:
    """f_phaseAMinBars (lines 651-652)."""
    return max(phaseAMinBars, max(_p, 1) * 2)


def f_phaseBMinBars(_p, _rangeATR) -> int:
    """f_phaseBMinBars (lines 654-658): clamp(round(max(6p, rangeATR * p)), 30, 60)."""
    p = max(_p, 1)
    raw = ptrunc(pround(pmax(float(p * 6), _rangeATR * float(p) * 1.00)))
    return max(minPhaseBBars, min(raw, minPhaseBBars * 2))


def f_phaseCToDMinBars(_p) -> int:
    """f_phaseCToDMinBars (lines 660-661): max(3, int(max(p, 1) / 2))."""
    return max(phaseCToDMinBars, ptrunc(max(_p, 1) / 2))


def f_phaseDMinBars(_p) -> int:
    """f_phaseDMinBars (lines 663-664)."""
    return max(phaseDMinBars, max(_p, 1))


def f_excursionRecoveryLimit(_p) -> int:
    """f_excursionRecoveryLimit (lines 666-667): max(3, int(round(max(p, 1) * 0.75)))."""
    return max(excursionRecoveryBars, ptrunc(pround(max(_p, 1) * 0.75)))


def f_phaseIdleLimit(_phase, _hasAR, _p):
    """f_phaseIdleLimit (lines 669-680); na (NaN) in Phases none and E."""
    p = max(_p, 1)
    lim = NAN
    if _phase == PHASE_A:
        lim = max(phaseAAfterArMaxBars, p * 6) if _hasAR else max(maxARBars, p * 4)
    elif _phase == PHASE_B:
        lim = max(phaseBIdleMaxBars, p * 20)
    elif _phase == PHASE_C:
        lim = max(phaseCIdleMaxBars, p * 8)
    elif _phase == PHASE_D:
        lim = max(phaseCIdleMaxBars * 2, p * 16)
    return lim


def f_phaseBCharacterImproving(_n, _effSum, _sprSum, _lastE, _lastS) -> bool:
    """f_phaseBCharacterImproving (lines 682-688)."""
    ok = False
    if _n >= 2 and not na(_lastE) and not na(_lastS):
        avgE = _effSum / _n
        avgS = _sprSum / _n
        ok = _lastE <= avgE and _lastS <= avgS * 1.05
    return ok


def f_robustEdge(_e1, _e2, _e3, _orig, _isLow):
    """f_robustEdge (lines 690-698): the median of three edges (computed as e1 + e2 + e3 - max - min, the script's
    arithmetic), or the average with the original edge when fewer exist, never beyond the original edge."""
    med = NAN
    if not na(_e1) and not na(_e2) and not na(_e3):
        med = _e1 + _e2 + _e3 - pmax(_e1, pmax(_e2, _e3)) - pmin(_e1, pmin(_e2, _e3))
    elif not na(_e1) and not na(_e2):
        med = ((_e1 + _e2) / 2.0 + _orig) / 2.0
    elif not na(_e1):
        med = (_e1 + _orig) / 2.0
    return _orig if na(med) else (pmax(_orig, med) if _isLow else pmin(_orig, med))


def f_typeFrom(_stop, _out, _bull, _bear) -> int:
    """f_typeFrom (lines 700-702); display only."""
    if _out == DIR_ACCUM:
        return 2 if (_stop == DIR_DIST or _bull) else 1
    if _out == DIR_DIST:
        return -2 if (_stop == DIR_ACCUM or _bear) else -1
    return 0


# ───────────────────────────── the campaign state (lines 354-483) ─────────────────────────────

class PivotTriplet:
    """type PivotTriplet (lines 354-363); display only."""
    __slots__ = ("b1", "t1", "p1", "b2", "t2", "p2", "b3", "t3", "p3")

    def __init__(self):
        for k in self.__slots__:
            setattr(self, k, NAN)


class WS:
    """type WS (lines 366-483), every field at its Pine default (na = NaN). The entry fields are one slot per
    strictness mode (see the module docstring)."""

    def __init__(self):
        self.stopSide = 0
        self.outcome = 0
        self.phase = 0
        self.ev = 0
        self.startBar = NAN
        self.pivLen = NAN
        self.birthTrend = NAN
        self.ctxBull = False
        self.ctxBear = False
        self.climaxBar = NAN
        self.climaxTime = NAN
        self.climaxPrice = NAN
        self.climaxEff = NAN
        self.climaxSpr = NAN
        self.climaxATR = NAN
        self.climaxScore = 0
        self.absorbed = False
        self.psTime = NAN
        self.psPrice = NAN
        self.psScore = 0
        self.origHigh = NAN
        self.origLow = NAN
        self.rangeHigh = NAN
        self.rangeLow = NAN
        self.arRunPrice = NAN
        self.arRunBar = NAN
        self.arRunTime = NAN
        self.arOK = False
        self.arBar = NAN
        self.arTime = NAN
        self.arPrice = NAN
        self.stCount = 0
        self.stN = 0
        self.stEffSum = 0.0
        self.stSprSum = 0.0
        self.lastGoodEff = NAN
        self.lastGoodSpr = NAN
        self.stBar = NAN
        self.stTime = NAN
        self.stPrice = NAN
        self.stHist = None
        self.stScore = 0
        self.edge1 = NAN
        self.edge2 = NAN
        self.edge3 = NAN
        self.oppCount = 0
        self.opN = 0
        self.opEffSum = 0.0
        self.opSprSum = 0.0
        self.opLastBar = NAN
        self.opLastPrice = NAN
        self.opHist = None
        self.travCount = 0
        self.lastZone = 0
        self.lastZoneBar = NAN
        self.lastBadBar = NAN
        self.bStartBar = NAN
        self.bStartTime = NAN
        self.cStartTime = NAN
        self.cReadyBar = NAN
        self.dStartBar = NAN
        self.dStartTime = NAN
        self.eStartBar = NAN
        self.eStartTime = NAN
        self.pend = False
        self.pendEdge = 0
        self.pendStartBar = NAN
        self.pendExtBar = NAN
        self.pendExt = NAN
        self.pendExtTime = NAN
        self.pendEff = NAN
        self.pendSpr = NAN
        self.pendCoolBar = NAN
        self.provEdge = 0
        self.provBar = NAN
        self.provPrice = NAN
        self.provTime = NAN
        self.provEff = NAN
        self.provSpr = NAN
        self.provScore = 0
        self.exc = False
        self.excTested = False
        self.excBar = NAN
        self.excPrice = NAN
        self.excTime = NAN
        self.excEff = NAN
        self.excSpr = NAN
        self.excScore = 0
        self.testTime = NAN
        self.testPrice = NAN
        self.testScore = 0
        self.strBar = NAN
        self.strTime = NAN
        self.strPrice = NAN
        self.strScore = 0
        self.lpsTime = NAN
        self.lpsPrice = NAN
        self.lpsBar = NAN
        self.lpsScore = 0
        self.entryTime = {m: NAN for m in MODES}
        self.entryPrice = {m: NAN for m in MODES}
        self.entryKind = {m: ENTRY_NONE for m in MODES}
        self.outCount = 0
        self.lastEventBar = NAN
        self.lastEventTime = NAN
        self.lastEventPrice = NAN
        self.lastActBar = NAN
        self.cfPrior = False
        self.cfClimax = False
        self.cfAR = False
        self.cfST = False
        self.cfExc = False
        self.cfTest = False
        self.cfStrength = False
        self.cfLPS = False
        self.cfAccept = False


def f_setEvent(s: WS, _ev: int, B: Bar) -> bool:
    """f_setEvent (lines 705-711)."""
    s.ev = _ev
    s.lastEventBar = B.bar_index
    s.lastEventTime = B.time
    s.lastEventPrice = B.close
    s.lastActBar = B.bar_index
    return True


def f_rangeATRWS(s: WS, _atrNow, B: Bar) -> float:
    """f_rangeATRWS (lines 720-721): the range height in climax ATRs, 0 while the range is not known."""
    if not na(s.rangeHigh) and not na(s.rangeLow):
        return abs(s.rangeHigh - s.rangeLow) / pmax(nz(s.climaxATR, _atrNow), B.mintick)
    return 0.0


def f_hardLevel(s: WS, _side: int):
    """f_hardLevel (lines 723-729)."""
    if _side == DIR_ACCUM:
        if s.exc and s.outcome == DIR_ACCUM and not na(s.excPrice):
            return s.excPrice
        return s.rangeLow if na(s.origLow) else pmin(s.origLow, nz(s.rangeLow, s.origLow))
    if s.exc and s.outcome == DIR_DIST and not na(s.excPrice):
        return s.excPrice
    return s.rangeHigh if na(s.origHigh) else pmax(s.origHigh, nz(s.rangeHigh, s.origHigh))


def f_seed(s: WS, _side, _score, _pLen, _trend, _bull, _bear, _atrNow, _effNow, _sprNow, B: Bar) -> bool:
    """f_seed (lines 731-753)."""
    s.stopSide = _side
    s.phase = PHASE_A
    s.startBar = B.bar_index
    s.pivLen = _pLen
    s.birthTrend = _trend
    s.ctxBull = _bull
    s.ctxBear = _bear
    s.climaxBar = B.bar_index
    s.climaxTime = B.time
    s.climaxPrice = B.low if _side == DIR_ACCUM else B.high
    s.climaxEff = _effNow
    s.climaxSpr = _sprNow
    s.climaxATR = _atrNow
    s.climaxScore = _score
    if _side == DIR_ACCUM:
        s.origLow = B.low
        s.rangeLow = B.low
    else:
        s.origHigh = B.high
        s.rangeHigh = B.high
    s.cfPrior = True
    return f_setEvent(s, EV_SC if _side == DIR_ACCUM else EV_BC, B)


def f_freezeAR(s: WS) -> bool:
    """f_freezeAR (lines 755-766)."""
    s.arBar = s.arRunBar
    s.arTime = s.arRunTime
    s.arPrice = s.arRunPrice
    s.cfAR = True
    if s.stopSide == DIR_ACCUM:
        s.origHigh = s.arRunPrice
        s.rangeHigh = s.arRunPrice
    else:
        s.origLow = s.arRunPrice
        s.rangeLow = s.arRunPrice
    return True


def f_initPivotHistory(s: WS) -> bool:
    """f_initPivotHistory (lines 768-773)."""
    if s.stHist is None:
        s.stHist = PivotTriplet()
    if s.opHist is None:
        s.opHist = PivotTriplet()
    return True


def _push_triplet(h: PivotTriplet, _pb, _t, _price) -> None:
    # the triplet bookkeeping of f_registerST / f_registerOpp (lines 786-797, 817-828); display only
    if na(h.t1):
        h.b1, h.t1, h.p1 = _pb, _t, _price
    elif na(h.t2) and _pb > nz(h.b1, -1):
        h.b2, h.t2, h.p2 = _pb, _t, _price
    elif na(h.t3) and _pb > nz(h.b2, nz(h.b1, -1)):
        h.b3, h.t3, h.p3 = _pb, _t, _price


def f_registerST(s: WS, _price, _t, _pb, _e, _sp, _score, B: Bar) -> bool:
    """f_registerST (lines 775-807)."""
    s.stCount = s.stCount + 1
    s.stN = s.stN + 1
    s.stEffSum = s.stEffSum + _e
    s.stSprSum = s.stSprSum + _sp
    s.lastGoodEff = _e
    s.lastGoodSpr = _sp
    s.stBar = _pb
    s.stTime = _t
    s.stPrice = _price
    f_initPivotHistory(s)
    _push_triplet(s.stHist, _pb, _t, _price)
    s.stScore = _score
    s.edge3 = s.edge2
    s.edge2 = s.edge1
    s.edge1 = _price
    if s.stopSide == DIR_ACCUM:
        s.rangeLow = f_robustEdge(s.edge1, s.edge2, s.edge3, s.origLow, True)
    else:
        s.rangeHigh = f_robustEdge(s.edge1, s.edge2, s.edge3, s.origHigh, False)
    s.cfST = True
    return f_setEvent(s, EV_ST, B)


def f_registerOpp(s: WS, _price, _t, _pb, _e, _sp, B: Bar) -> bool:
    """f_registerOpp (lines 809-830)."""
    s.oppCount = s.oppCount + 1
    s.opN = s.opN + 1
    s.opEffSum = s.opEffSum + _e
    s.opSprSum = s.opSprSum + _sp
    s.opLastBar = _pb
    s.opLastPrice = _price
    f_initPivotHistory(s)
    _push_triplet(s.opHist, _pb, _t, _price)
    s.lastActBar = B.bar_index
    return True


def f_clearTerminal(s: WS) -> bool:
    """f_clearTerminal (lines 832-848)."""
    s.exc = False
    s.excTested = False
    s.excBar = NAN
    s.excPrice = NAN
    s.excTime = NAN
    s.excEff = NAN
    s.excSpr = NAN
    s.excScore = 0
    s.testTime = NAN
    s.testPrice = NAN
    s.testScore = 0
    s.cfExc = False
    s.cfTest = False
    s.cReadyBar = NAN
    s.cStartTime = NAN
    return True


def f_excFromPend(s: WS, _score, B: Bar) -> bool:
    """f_excFromPend (lines 850-866)."""
    s.exc = True
    s.excTested = False
    s.excBar = s.pendExtBar
    s.excPrice = s.pendExt
    s.excTime = s.pendExtTime
    s.excEff = s.pendEff
    s.excSpr = s.pendSpr
    s.excScore = _score
    s.cfExc = True
    s.outcome = s.pendEdge
    s.cStartTime = s.pendExtTime
    s.phase = PHASE_C
    s.cReadyBar = NAN
    s.pend = False
    s.provEdge = 0
    return f_setEvent(s, EV_SPRING if s.outcome == DIR_ACCUM else EV_UTAD, B)


def f_adoptProv(s: WS) -> bool:
    """f_adoptProv (lines 868-881)."""
    s.exc = True
    s.excTested = False
    s.excBar = s.provBar
    s.excPrice = s.provPrice
    s.excTime = s.provTime
    s.excEff = s.provEff
    s.excSpr = s.provSpr
    s.excScore = s.provScore
    s.cfExc = True
    s.outcome = s.provEdge
    s.cStartTime = s.provTime
    s.provEdge = 0
    return True


def f_enterCTest(s: WS, _outc, _t, _price, _score, B: Bar) -> bool:
    """f_enterCTest (lines 883-893)."""
    s.phase = PHASE_C
    s.outcome = _outc
    s.cStartTime = _t
    s.cReadyBar = B.bar_index
    s.testTime = _t
    s.testPrice = _price
    s.testScore = _score
    s.cfTest = True
    s.pend = False
    return f_setEvent(s, EV_CTEST_ACC if _outc == DIR_ACCUM else EV_CTEST_DST, B)


def f_promoteD(s: WS, _outc, _score, _price, B: Bar) -> bool:
    """f_promoteD (lines 895-907)."""
    s.outcome = _outc
    s.phase = PHASE_D
    s.dStartBar = B.bar_index
    s.dStartTime = B.time
    s.strBar = B.bar_index
    s.strTime = B.time
    s.strPrice = _price
    s.strScore = _score
    s.cfStrength = True
    s.pend = False
    s.outCount = 0
    return f_setEvent(s, EV_SOS if _outc == DIR_ACCUM else EV_SOW, B)


def f_demoteToB(s: WS, B: Bar) -> bool:
    """f_demoteToB (lines 909-930). It does not touch the entry slots (spec risk 9)."""
    f_clearTerminal(s)
    s.outcome = DIR_NONE
    s.phase = PHASE_B
    s.strBar = NAN
    s.strTime = NAN
    s.strPrice = NAN
    s.strScore = 0
    s.lpsTime = NAN
    s.lpsPrice = NAN
    s.lpsBar = NAN
    s.lpsScore = 0
    s.dStartBar = NAN
    s.dStartTime = NAN
    s.cfStrength = False
    s.cfLPS = False
    s.provEdge = 0
    s.pend = False
    s.outCount = 0
    s.lastBadBar = B.bar_index
    s.lastActBar = B.bar_index
    return True


def f_confWS(s: WS) -> int:
    """f_confWS (lines 932-934)."""
    cDone = s.cfTest or (s.cfExc and s.cfStrength)
    return f_structureConfidence(s.cfPrior, s.cfClimax, s.cfAR, s.cfST, cDone, s.cfStrength, s.cfLPS, s.cfAccept)


def f_validationWS(s: WS, _p, _trendNow, _atrNow, B: Bar) -> int:
    """f_validationWS (lines 936-943)."""
    rATR = f_rangeATRWS(s, _atrNow, B)
    bAge = max(B.bar_index - s.bStartBar, 0) if not na(s.bStartBar) else 0
    badAge = -1 if na(s.lastBadBar) else B.bar_index - s.lastBadBar
    clean = badAge < 0 or badAge >= ptrunc(pround(_p * phaseBBadTestCooldownFactor))
    cause = f_causeUnits(s.travCount, bAge, _p, rATR)
    terminal = (s.cfTest and (not s.exc or s.excTested)) or (s.cfExc and s.cfStrength)
    if s.stopSide == DIR_NONE:
        return 0
    return f_validationScore(nz(s.birthTrend, _trendNow), s.absorbed, rATR, s.stCount, s.oppCount, s.travCount,
                             clean, cause, terminal, s.cfStrength, s.cfLPS, s.cfAccept)


def f_matureWS(s: WS, _p, _atrNow, B: Bar) -> bool:
    """f_matureWS (lines 945-956)."""
    rATR = f_rangeATRWS(s, _atrNow, B)
    bAge = B.bar_index - s.bStartBar if not na(s.bStartBar) else 0
    bMin = f_phaseBMinBars(_p, rATR)
    badAge = -1 if na(s.lastBadBar) else B.bar_index - s.lastBadBar
    clean = badAge < 0 or badAge >= ptrunc(pround(_p * phaseBBadTestCooldownFactor))
    opp = minPhaseBOppositeTests <= 0 or s.oppCount >= minPhaseBOppositeTests
    trav = minPhaseBTraversals <= 0 or s.travCount >= minPhaseBTraversals
    ch = f_phaseBCharacterImproving(s.stN, s.stEffSum, s.stSprSum, s.lastGoodEff, s.lastGoodSpr)
    support = (1 if opp else 0) + (1 if trav else 0) + (1 if clean else 0) + (1 if ch else 0)
    sane = rATR >= phaseBRangeMinATR * 0.75 and rATR <= phaseBRangeMaxATR * 2.0
    return s.phase == PHASE_B and bAge >= bMin and s.stCount >= minPhaseBTests and sane and support >= 2


def f_entryReadinessWS(s: WS, _minConf, _valFloor, _atrNow, B: Bar) -> int:
    """f_entryReadinessWS (lines 958-974). Its validation term uses nz(s.pivLen, pivotLen) and s.birthTrend
    (line 971), not the entry check's arguments; inside a campaign both are always set, so the values agree."""
    bull = s.outcome == DIR_ACCUM
    if na(s.rangeHigh) or na(s.rangeLow):
        distATR = 99.0
    elif bull:
        distATR = (B.close - s.rangeHigh) / pmax(_atrNow, B.mintick)
    else:
        distATR = (s.rangeLow - B.close) / pmax(_atrNow, B.mintick)
    if not na(s.lastEventTime):
        ageBars = (float(B.time) - s.lastEventTime) / pmax(float(B.tf_secs) * 1000.0, 1.0)
    else:
        ageBars = 999.0
    terminal = (s.exc and s.excTested) or (not s.exc and s.cfTest)
    conf = f_confWS(s)
    r = 0
    r += 1 if s.outcome != DIR_NONE else 0
    r += 1 if s.phase >= PHASE_C else 0
    r += 1 if terminal else 0
    r += 1 if s.cfStrength else 0
    r += 1 if s.cfLPS else 0
    r += 1 if conf >= _minConf else 0
    r += 1 if f_validationWS(s, nz(s.pivLen, pivotLen), s.birthTrend, _atrNow, B) >= _valFloor else 0
    r += 1 if distATR <= 2.0 else 0
    r += 1 if ageBars <= 50.0 else 0
    return r


# ───────────────────────────── the engine (lines 1060-1764), one bar per call ─────────────────────────────

class Engine:
    """``f_engine(true)`` on the chart timeframe: call ``step`` once per bar, oldest first. The ``var`` state of
    lines 1091-1103 lives on the object; ``self.s`` is the campaign ``WS``. ``modes``: the entry strictness modes
    evaluated (all three by default); ``ties``: the pivot tie reading ("strict", or "nonstrict" to measure it)."""

    def __init__(self, mintick: float, tf_secs: float, modes: Sequence[str] = MODES, ties: str = "strict"):
        if not (mintick > 0):
            raise ValueError("syminfo.mintick must be > 0")
        for m in modes:
            if m not in MODES:
                raise ValueError(f"unknown entry strictness {m!r}")
        if ties not in ("strict", "nonstrict"):
            raise ValueError(f"unknown pivot tie reading {ties!r}")
        self.mintick = float(mintick)
        self.tf_secs = float(tf_secs)
        self.modes = tuple(modes)
        self.ties = ties
        # the built-in series
        self.open, self.high, self.low, self.close, self.time = [], [], [], [], []
        # f_engine's own series (each history list is one Pine series)
        self.cumVol = 0.0                                    # ta.cum(rawVol)
        self.eff, self.avgEffRaw, self.tr, self.atrRaw, self.a = [], [], [], [], []
        self.lowest30, self.highest30, self.effHi30 = [], [], []
        self.liveLen, self.ph, self.pl, self.longSma = [], [], [], []
        self.dnEffc, self.upEffc, self.dnSma10, self.upSma10 = [], [], [], []
        # var state (lines 1091-1103)
        self.s = WS()
        f_initPivotHistory(self.s)
        self.regime = REGIME_NONE
        self.regimeBar = NAN
        self.prelimBar = NAN
        self.prelimTime = NAN
        self.prelimPrice = NAN
        self.prelimDir = DIR_NONE
        self.prelimScore = 0
        self.lastPLBar = NAN
        self.lastPHBar = NAN
        self.rsCounts = [0] * 7
        self.lastResetWhy = -1
        self.lost = False
        # the port's own inspection hook, not Pine: a dict receives the bar's locals when set (the tests use it)
        self.trace: Optional[dict] = None

    # -- the port's bookkeeping, not Pine: a campaign that held an outcome lost it during this bar (in_cde)
    def _lose(self, s: WS) -> None:
        if s.outcome != DIR_NONE:
            self.lost = True

    def step(self, o: float, h: float, l: float, c: float, v: float, t_ms: int) -> Dict[str, object]:
        """Run the engine on one bar (open time ``t_ms`` in ms) and return the outputs at its close."""
        mt = self.mintick
        bar_index = len(self.close)
        self.open.append(o)
        self.high.append(h)
        self.low.append(l)
        self.close.append(c)
        self.time.append(t_ms)
        B = Bar(bar_index, t_ms, o, h, l, c, mt, self.tf_secs)
        self.lost = False
        climax_flag, climax_px, exc_flag, exc_px = 0, NAN, 0, NAN

        # Bar measurements (lines 1062-1089)
        rawVol = nz(v)
        self.cumVol = self.cumVol + rawVol
        noVol = self.cumVol <= 0.0
        spr = pmax(h - l, mt)
        eff = spr if noVol else rawVol
        self.eff.append(eff)
        avgEffRaw = ta_sma(self.eff, volLen)
        self.avgEffRaw.append(avgEffRaw)
        avgEff = nz(avgEffRaw, eff)
        avgEffPrev = nz(at(self.avgEffRaw, 1), avgEff)
        # ta.atr(atrLen): pine_atr's true range (high - low on bar 0) and pine_rma
        if na(at(self.high, 1)):
            trueRange = h - l
        else:
            c1 = at(self.close, 1)
            trueRange = pmax(pmax(h - l, abs(h - c1)), abs(l - c1))
        self.tr.append(trueRange)
        rmaPrev = at(self.atrRaw, 0)                       # sum[1]: the last bar's value (not yet appended)
        if na(rmaPrev):
            atrRaw = ta_sma(self.tr, atrLen)
        else:
            alpha = 1.0 / atrLen
            atrRaw = alpha * trueRange + (1.0 - alpha) * nz(rmaPrev)
        self.atrRaw.append(atrRaw)
        a = nz(atrRaw, spr)
        aPrev = nz(at(self.atrRaw, 1), a)
        self.a.append(a)
        unit = pmax(a, mt)
        cPos = (c - l) / spr
        relE = eff / pmax(avgEff, 1e-10)
        sprATR = spr / unit
        recentEff = ta_sma(self.eff, climaxAbsorptionMinBars)
        recentLow = ta_lowest(self.low, climaxAbsorptionMinBars)
        recentHigh = ta_highest(self.high, climaxAbsorptionMinBars)
        self.lowest30.append(ta_lowest(self.low, extremeLen))
        self.highest30.append(ta_highest(self.high, extremeLen))
        self.effHi30.append(ta_highest(self.eff, extremeLen))
        priorLo = at(self.lowest30, 1)
        priorHi = at(self.highest30, 1)
        effHiPrior = at(self.effHi30, 1)
        newLow = not na(priorLo) and l <= priorLo
        newHigh = not na(priorHi) and h >= priorHi
        aBase = ta_sma(self.a, adaptiveSwingVolLen)
        aRatio = a / aBase if nz(aBase) > 0.0 else 1.0
        adaptLen = max(adaptiveSwingMin, min(adaptiveSwingMax, ptrunc(pround(pivotLen * aRatio))))
        liveLen = adaptLen                                   # swingModeInput == "ATR Adaptive" (line 58)
        self.liveLen.append(liveLen)
        preLen = nz(at(self.liveLen, 3), liveLen)

        s = self.s
        f_initPivotHistory(s)                                # line 1092

        # Pivots with the length of the state at the start of the bar (lines 1105-1114)
        pLen = nz(s.pivLen, liveLen) if s.phase != PHASE_NONE else liveLen
        ph = ta_pivothigh(self.high, pLen, pLen, self.ties)
        pl = ta_pivotlow(self.low, pLen, pLen, self.ties)
        self.ph.append(ph)
        self.pl.append(pl)
        pivBar = bar_index - pLen
        pA = pmax(nz(at(self.atrRaw, pLen), a), mt)
        pEff = nz(at(self.eff, pLen), eff)
        pSpr = pmax(nz(at(self.high, pLen), h) - nz(at(self.low, pLen), l), mt)
        pCPos = (nz(at(self.close, pLen), c) - nz(at(self.low, pLen), l)) / pSpr
        pAvgEff = nz(at(self.avgEffRaw, pLen), avgEff)
        pTime = float(nz(at(self.time, pLen), t_ms))

        # Trend and context (lines 1116-1124)
        longSma = ta_sma(self.close, continuationTrendLen)
        self.longSma.append(longSma)
        trendBars = max(trendLen, min(priorTrendMaxBars, ptrunc(pround(liveLen * priorTrendPivotFactor))))
        trendEnd = max(2, min(8, ptrunc(pround(liveLen * 0.75))))
        trendScore = f_priorTrendScore(self, trendBars, trendEnd)
        downTrend = trendScore <= -priorTrendNeutral
        upTrend = trendScore >= priorTrendNeutral
        strongTrend = abs(trendScore) >= priorTrendStrong
        longBull = (nz(at(self.close, 1)) > nz(at(self.longSma, 1))
                    and nz(at(self.longSma, 1)) > nz(at(self.longSma, 20)))
        longBear = (not na(at(self.longSma, 20)) and nz(at(self.close, 1)) < nz(at(self.longSma, 1))
                    and nz(at(self.longSma, 1)) < nz(at(self.longSma, 20)))

        # Effort, closes and strength (lines 1126-1160)
        effort2 = pmax(relE, 0.01) * pmax(sprATR, 0.01)
        dnEffc = pmax(nz(at(self.close, 1), c) - c, 0.0) / unit / effort2
        upEffc = pmax(c - nz(at(self.close, 1), c), 0.0) / unit / effort2
        self.dnEffc.append(dnEffc)
        self.upEffc.append(upEffc)
        self.dnSma10.append(ta_sma(self.dnEffc, prelimEfficiencyLookback))
        self.upSma10.append(ta_sma(self.upEffc, prelimEfficiencyLookback))
        dnBase = at(self.dnSma10, 1)
        upBase = at(self.upSma10, 1)
        dnAbsorb = not na(dnBase) and dnEffc <= dnBase * prelimEfficiencyRatio
        upAbsorb = not na(upBase) and upEffc <= upBase * prelimEfficiencyRatio
        nearRecentLow = not na(priorLo) and l <= priorLo + a * prelimExtremeATR
        nearRecentHigh = not na(priorHi) and h >= priorHi - a * prelimExtremeATR

        hiCInv = ta_highest(self.close, structureInvalidationBars)
        loCInv = ta_lowest(self.close, structureInvalidationBars)
        hiCDep = ta_highest(self.close, phaseBDepartureBars)
        loCDep = ta_lowest(self.close, phaseBDepartureBars)
        hiCA = ta_highest(self.close, phaseAPrematureDepartureBars)
        loCA = ta_lowest(self.close, phaseAPrematureDepartureBars)
        hiCConf = ta_highest(self.close, confirmBars)
        loCConf = ta_lowest(self.close, confirmBars)
        hiCDir = ta_highest(self.close, directAcceptanceBars)
        loCDir = ta_lowest(self.close, directAcceptanceBars)
        hiCFail = ta_highest(self.close, phaseDFailBars)
        loCFail = ta_lowest(self.close, phaseDFailBars)
        mbLow = ta_lowest(self.low, sosMultiBarLen)
        mbHigh = ta_highest(self.high, sosMultiBarLen)
        mbEffRatio = ta_sum(self.eff, sosMultiBarLen) / pmax(avgEff * sosMultiBarLen, 1e-10)
        mbSOS = (c - mbLow) / unit >= sosMultiBarATR and mbEffRatio >= sosMultiBarEffort and cPos >= 0.50
        mbSOW = (mbHigh - c) / unit >= sosMultiBarATR and mbEffRatio >= sosMultiBarEffort and cPos <= 0.50
        res3Up = pmax(c - nz(at(self.close, 3), c), 0.0) / unit
        res3Dn = pmax(nz(at(self.close, 3), c) - c, 0.0) / unit
        sosScore = ((1 if relE >= strengthVolMult else 0) + (1 if sprATR >= strengthSpreadATR else 0)
                    + (1 if cPos >= sosCloseMin else 0) + (1 if (c > o and c - o >= a * 0.50) else 0))
        sowScore = ((1 if relE >= strengthVolMult else 0) + (1 if sprATR >= strengthSpreadATR else 0)
                    + (1 if cPos <= sowCloseMax else 0) + (1 if (c < o and o - c >= a * 0.50) else 0))
        close1 = nz(at(self.close, 1), c)
        close2 = nz(at(self.close, 2), c)
        ctxBars = max(priorTrendMaxBars, continuationTrendLen) * 2
        sig = 0

        # if _commit (line 1162): barstate.isconfirmed, true on every historical bar
        p0 = nz(s.pivLen, liveLen)
        rk0 = not na(s.rangeHigh) and not na(s.rangeLow)
        rH0 = s.rangeHigh
        rL0 = s.rangeLow
        rHt0 = pmax(rH0 - rL0, mt) if rk0 else NAN
        rMid0 = (rH0 + rL0) / 2.0 if rk0 else NAN
        probeOpen = s.pend and bar_index - s.pendStartBar <= f_excursionRecoveryLimit(p0)
        structAge = bar_index - s.startBar if not na(s.startBar) else 0
        ageOKBull = self.regime != REGIME_MARKDOWN or structAge >= oppositeCycleMinBars
        ageOKBear = self.regime != REGIME_MARKUP or structAge >= oppositeCycleMinBars
        hardBull0 = f_hardLevel(s, DIR_ACCUM)
        hardBear0 = f_hardLevel(s, DIR_DIST)
        resetWhy = -1

        # Retire structures that no longer fit (lines 1181-1234)
        if s.phase == PHASE_A:
            aClimaxAge = bar_index - s.climaxBar
            aInvAcc = s.stopSide == DIR_ACCUM and hiCInv < s.climaxPrice - a * structureInvalidationATR
            aInvDst = s.stopSide == DIR_DIST and loCInv > s.climaxPrice + a * structureInvalidationATR
            aAbsorbExp = not s.absorbed and aClimaxAge > climaxAbsorptionMaxBars
            aNoAR = not s.arOK and aClimaxAge > maxARBars
            aOverExt = (s.arOK and not na(s.arRunPrice)
                        and abs(s.arRunPrice - s.climaxPrice) / pmax(nz(s.climaxATR, a), mt) > arMaxExtensionATR)
            aBuf = pmax(rHt0 * phaseAPrematureDepartureTRFrac, a * phaseAPrematureDepartureATR) if rk0 else NAN
            aDepart = aClimaxAge > maxARBars and rk0 and ((s.stopSide == DIR_ACCUM and loCA > rH0 + aBuf)
                                                          or (s.stopSide == DIR_DIST and hiCA < rL0 - aBuf))
            if aInvAcc or aInvDst:
                resetWhy = RS_INVALID
            elif aAbsorbExp:
                resetWhy = RS_ABSORB
            elif aNoAR or aOverExt or aDepart:
                resetWhy = RS_NORANGE

        if s.phase == PHASE_C and not probeOpen and resetWhy < 0:
            cBullDead = (s.outcome == DIR_ACCUM and not na(hardBull0)
                         and hiCInv < hardBull0 - a * structureInvalidationATR)
            cBearDead = (s.outcome == DIR_DIST and not na(hardBear0)
                         and loCInv > hardBear0 + a * structureInvalidationATR)
            if cBullDead:
                resetWhy = RS_INVALID
            elif cBearDead:
                resetWhy = RS_INVALID

        if s.phase == PHASE_D and rk0 and resetWhy < 0:
            if s.outcome == DIR_ACCUM:
                if not na(hardBull0) and hiCInv < hardBull0 - a * structureInvalidationATR:
                    resetWhy = RS_INVALID
                elif hiCFail < rMid0:
                    self._lose(s)
                    f_demoteToB(s, B)
                    self.rsCounts[RS_DEMOTE] += 1
            elif s.outcome == DIR_DIST:
                if not na(hardBear0) and loCInv > hardBear0 + a * structureInvalidationATR:
                    resetWhy = RS_INVALID
                elif loCFail > rMid0:
                    self._lose(s)
                    f_demoteToB(s, B)
                    self.rsCounts[RS_DEMOTE] += 1

        if s.phase == PHASE_E and rk0 and resetWhy < 0:
            eFail = hiCFail < rMid0 if s.outcome == DIR_ACCUM else loCFail > rMid0
            eOld = phaseEMaxBars > 0 and not na(s.eStartBar) and bar_index - s.eStartBar > phaseEMaxBars
            if eFail or eOld:
                resetWhy = RS_EEND

        idleLim = f_phaseIdleLimit(s.phase, s.arOK, p0)
        if (resetWhy < 0 and not probeOpen and not na(idleLim) and not na(s.lastActBar)
                and bar_index - s.lastActBar > idleLim):
            resetWhy = RS_STALE

        if resetWhy >= 0:
            self.rsCounts[resetWhy] += 1
            self.lastResetWhy = resetWhy
            self._lose(s)
            s = self.s = WS()
            f_initPivotHistory(s)

        # Track preliminary support/supply (lines 1236-1252); display only
        if s.phase == PHASE_NONE or s.phase == PHASE_E:
            psSc = ((1 if downTrend else 0) + (1 if nearRecentLow else 0) + (1 if relE >= prelimVolMult else 0)
                    + (1 if sprATR >= 0.80 else 0) + (1 if cPos >= 0.45 else 0) + (1 if dnAbsorb else 0))
            psySc = ((1 if upTrend else 0) + (1 if nearRecentHigh else 0) + (1 if relE >= prelimVolMult else 0)
                     + (1 if sprATR >= 0.80 else 0) + (1 if cPos <= 0.55 else 0) + (1 if upAbsorb else 0))
            psStale = na(self.prelimBar) or bar_index - self.prelimBar > extremeLen
            if (downTrend and nearRecentLow and relE >= prelimVolMult and psSc >= prelimMinScore
                    and (self.prelimDir != DIR_ACCUM or psStale or psSc >= self.prelimScore)):
                self.prelimBar = bar_index
                self.prelimTime = t_ms
                self.prelimPrice = l
                self.prelimDir = DIR_ACCUM
                self.prelimScore = psSc
            elif (upTrend and nearRecentHigh and relE >= prelimVolMult and psySc >= prelimMinScore
                  and (self.prelimDir != DIR_DIST or psStale or psySc >= self.prelimScore)):
                self.prelimBar = bar_index
                self.prelimTime = t_ms
                self.prelimPrice = h
                self.prelimDir = DIR_DIST
                self.prelimScore = psySc

        # Seed new climaxes (lines 1254-1275)
        relaxK = relaxedClimaxFactor if strongTrend else 1.0
        volHit = eff >= avgEffPrev * climaxVolMult * relaxK
        sprHit = spr >= aPrev * climaxSpreadMult * relaxK
        exceptional = (not na(effHiPrior) and eff >= effHiPrior) or spr >= aPrev * climaxSpreadMult * 1.5
        scSc = ((1 if downTrend else 0) + (1 if newLow else 0) + (1 if volHit else 0) + (1 if sprHit else 0)
                + (1 if cPos >= scCloseMin else 0) + (1 if exceptional else 0))
        bcSc = ((1 if upTrend else 0) + (1 if newHigh else 0) + (1 if volHit else 0) + (1 if sprHit else 0)
                + (1 if cPos <= bcCloseMax else 0) + (1 if exceptional else 0))
        seedOpen = s.phase == PHASE_NONE or s.phase == PHASE_E
        canSC = seedOpen or (s.phase == PHASE_A and s.stopSide == DIR_ACCUM and l < s.climaxPrice)
        canBC = seedOpen or (s.phase == PHASE_A and s.stopSide == DIR_DIST and h > s.climaxPrice)
        isSC = canSC and downTrend and newLow and volHit and sprHit and scSc >= climaxMinScore
        isBC = canBC and upTrend and newHigh and volHit and sprHit and bcSc >= climaxMinScore
        if isSC != isBC:
            seedSide = DIR_ACCUM if isSC else DIR_DIST
            recentMarkup = (self.regime == REGIME_MARKUP and not na(self.regimeBar)
                            and bar_index - self.regimeBar <= ctxBars)
            recentMarkdown = (self.regime == REGIME_MARKDOWN and not na(self.regimeBar)
                              and bar_index - self.regimeBar <= ctxBars)
            self._lose(s)
            s = self.s = WS()
            f_initPivotHistory(s)
            f_seed(s, seedSide, scSc if isSC else bcSc, preLen, trendScore, recentMarkup or longBull,
                   recentMarkdown or longBear, a, eff, spr, B)
            if (self.prelimDir == seedSide and not na(self.prelimBar) and self.prelimBar < bar_index
                    and bar_index - self.prelimBar <= extremeLen):
                s.psTime = self.prelimTime
                s.psPrice = self.prelimPrice
                s.psScore = self.prelimScore

        # Confirm stopping action and build the AR (lines 1277-1311)
        if s.phase == PHASE_A and not s.absorbed and not na(s.climaxBar):
            absAge = bar_index - s.climaxBar
            if absAge >= climaxAbsorptionMinBars and absAge <= climaxAbsorptionMaxBars:
                effortOK = recentEff >= avgEff * climaxAbsorptionVolFloor
                accAbs = (s.stopSide == DIR_ACCUM
                          and recentLow >= s.climaxPrice - s.climaxATR * climaxAbsorptionExtremeATR
                          and c >= s.climaxPrice + s.climaxATR * climaxAbsorptionReboundATR)
                dstAbs = (s.stopSide == DIR_DIST
                          and recentHigh <= s.climaxPrice + s.climaxATR * climaxAbsorptionExtremeATR
                          and c <= s.climaxPrice - s.climaxATR * climaxAbsorptionReboundATR)
                if effortOK and (accAbs or dstAbs):
                    s.absorbed = True
                    s.cfClimax = True
                    s.lastActBar = bar_index
                    sig = f_addBit(sig, BIT_SC if s.stopSide == DIR_ACCUM else BIT_BC)
                    if not na(s.psTime):
                        sig = f_addBit(sig, BIT_PS)
                    climax_flag = 1 if s.stopSide == DIR_ACCUM else -1
                    climax_px = s.climaxPrice

        if (s.phase == PHASE_A and na(s.arBar) and not na(s.climaxBar) and bar_index > s.climaxBar
                and bar_index - s.climaxBar <= maxARBars):
            if s.stopSide == DIR_ACCUM:
                if na(s.arRunPrice) or h > s.arRunPrice:
                    s.arRunPrice = h
                    s.arRunBar = bar_index
                    s.arRunTime = t_ms
                s.arOK = s.arOK or s.arRunPrice - s.climaxPrice >= a * minARATR
            else:
                if na(s.arRunPrice) or l < s.arRunPrice:
                    s.arRunPrice = l
                    s.arRunBar = bar_index
                    s.arRunTime = t_ms
                s.arOK = s.arOK or s.climaxPrice - s.arRunPrice >= a * minARATR
        if s.phase == PHASE_A and s.arOK and s.absorbed and na(s.arBar):
            if s.stopSide == DIR_ACCUM:
                s.rangeHigh = s.arRunPrice
                s.origHigh = s.arRunPrice
            else:
                s.rangeLow = s.arRunPrice
                s.origLow = s.arRunPrice

        # Pivot events (lines 1313-1529)
        p1 = nz(s.pivLen, liveLen)
        rk1 = not na(s.rangeHigh) and not na(s.rangeLow)
        rH1 = s.rangeHigh
        rL1 = s.rangeLow
        origHt1 = pmax(nz(s.origHigh, rH1) - nz(s.origLow, rL1), mt) if rk1 else NAN
        mature1 = f_matureWS(s, p1, a, B)
        newPL = not na(pl) and (na(self.lastPLBar) or pivBar > self.lastPLBar)
        newPH = not na(ph) and (na(self.lastPHBar) or pivBar > self.lastPHBar)
        if newPL:
            self.lastPLBar = pivBar
        if newPH:
            self.lastPHBar = pivBar
        plUsed = False
        phUsed = False

        # terminal test at support (CTest, lines 1328-1348)
        if newPL and s.phase == PHASE_B and mature1 and rk1:
            loRefST = s.stopSide == DIR_ACCUM
            tRefN = s.stN if loRefST else s.opN
            tRefBar = s.stBar if loRefST else s.opLastBar
            tRefPrice = s.stPrice if loRefST else s.opLastPrice
            if tRefN > 0 and not na(tRefBar):
                tRefEff = (s.stEffSum if loRefST else s.opEffSum) / tRefN
                tRefSpr = (s.stSprSum if loRefST else s.opSprSum) / tRefN
                tLater = pivBar >= tRefBar + terminalTestMinBarsAfterST
                tNear = pl <= rL1 + pA * testTolATR
                tHolds = pl >= pmin(nz(s.origLow, rL1), rL1) - pA * testExtremeToleranceATR
                tHigher = na(tRefPrice) or pl >= tRefPrice - pA * testExtremeToleranceATR
                tqV = pEff <= tRefEff * terminalTestVolRatio
                tqS = pSpr <= tRefSpr * terminalTestSpreadRatio
                tnV = pEff <= tRefEff * terminalTestOtherMaxRatio
                tnS = pSpr <= tRefSpr * terminalTestOtherMaxRatio
                tSc = (1 if tqV else 0) + (1 if tqS else 0) + (1 if pCPos >= 0.50 else 0)
                if tLater and tNear and tHolds and tHigher and ((tqV and tnS) or (tqS and tnV)) and tSc >= testMinScore:
                    f_enterCTest(s, DIR_ACCUM, pTime, pl, tSc, B)
                    sig = f_addBit(sig, BIT_CTEST)
                    plUsed = True
        # terminal test at resistance (lines 1349-1369)
        if newPH and s.phase == PHASE_B and mature1 and rk1:
            hiRefST = s.stopSide == DIR_DIST
            uRefN = s.stN if hiRefST else s.opN
            uRefBar = s.stBar if hiRefST else s.opLastBar
            uRefPrice = s.stPrice if hiRefST else s.opLastPrice
            if uRefN > 0 and not na(uRefBar):
                uRefEff = (s.stEffSum if hiRefST else s.opEffSum) / uRefN
                uRefSpr = (s.stSprSum if hiRefST else s.opSprSum) / uRefN
                uLater = pivBar >= uRefBar + terminalTestMinBarsAfterST
                uNear = ph >= rH1 - pA * testTolATR
                uHolds = ph <= pmax(nz(s.origHigh, rH1), rH1) + pA * testExtremeToleranceATR
                uLower = na(uRefPrice) or ph <= uRefPrice + pA * testExtremeToleranceATR
                uqV = pEff <= uRefEff * terminalTestVolRatio
                uqS = pSpr <= uRefSpr * terminalTestSpreadRatio
                unV = pEff <= uRefEff * terminalTestOtherMaxRatio
                unS = pSpr <= uRefSpr * terminalTestOtherMaxRatio
                uSc = (1 if uqV else 0) + (1 if uqS else 0) + (1 if pCPos <= 0.50 else 0)
                if uLater and uNear and uHolds and uLower and ((uqV and unS) or (uqS and unV)) and uSc >= testMinScore:
                    f_enterCTest(s, DIR_DIST, pTime, ph, uSc, B)
                    sig = f_addBit(sig, BIT_CTEST)
                    phUsed = True

        # A -> B: the first ST after the AR (lines 1371-1410)
        if (newPL and not plUsed and s.phase == PHASE_A and s.stopSide == DIR_ACCUM and s.absorbed and s.arOK
                and not na(s.arRunBar) and pivBar > s.arRunBar):
            aZoneTop = s.origLow + (s.arRunPrice - s.origLow) * phaseBZoneFrac
            aNearL = abs(pl - s.origLow) <= pA * boundaryTolATR or pl <= aZoneTop
            aHoldsL = pl >= s.origLow - pA * boundaryTolATR
            aCloseL = pCPos >= 0.45
            aTcL = f_testClass(aNearL, aHoldsL, aCloseL, pEff, pSpr, s.climaxEff, s.climaxSpr)
            aScL = ((1 if aNearL else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0)
                    + (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if aHoldsL else 0)
                    + (1 if aCloseL else 0) + 1)
            aAgeL = pivBar - s.startBar >= f_phaseAMinBars(p1)
            aSpaceL = pivBar - s.arRunBar >= max(2, p1)
            if aNearL:
                s.lastActBar = bar_index
            if aTcL == TEST_GOOD and aScL >= stMinScore and aAgeL and aSpaceL:
                f_freezeAR(s)
                f_registerST(s, pl, pTime, pivBar, pEff, pSpr, aScL, B)
                s.phase = PHASE_B
                s.bStartBar = pivBar
                s.bStartTime = pTime
                sig = f_addBit(sig, BIT_AR)
                sig = f_addBit(sig, BIT_ST)
                plUsed = True
        if (newPH and not phUsed and s.phase == PHASE_A and s.stopSide == DIR_DIST and s.absorbed and s.arOK
                and not na(s.arRunBar) and pivBar > s.arRunBar):
            aZoneBot = s.origHigh - (s.origHigh - s.arRunPrice) * phaseBZoneFrac
            aNearH = abs(ph - s.origHigh) <= pA * boundaryTolATR or ph >= aZoneBot
            aHoldsH = ph <= s.origHigh + pA * boundaryTolATR
            aCloseH = pCPos <= 0.55
            aTcH = f_testClass(aNearH, aHoldsH, aCloseH, pEff, pSpr, s.climaxEff, s.climaxSpr)
            aScH = ((1 if aNearH else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0)
                    + (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if aHoldsH else 0)
                    + (1 if aCloseH else 0) + 1)
            aAgeH = pivBar - s.startBar >= f_phaseAMinBars(p1)
            aSpaceH = pivBar - s.arRunBar >= max(2, p1)
            if aNearH:
                s.lastActBar = bar_index
            if aTcH == TEST_GOOD and aScH >= stMinScore and aAgeH and aSpaceH:
                f_freezeAR(s)
                f_registerST(s, ph, pTime, pivBar, pEff, pSpr, aScH, B)
                s.phase = PHASE_B
                s.bStartBar = pivBar
                s.bStartTime = pTime
                sig = f_addBit(sig, BIT_AR)
                sig = f_addBit(sig, BIT_ST)
                phUsed = True

        # Phase B tests at both edges (lines 1412-1462)
        rk1 = not na(s.rangeHigh) and not na(s.rangeLow)
        if newPL and not plUsed and s.phase == PHASE_B and rk1 and pivBar > s.bStartBar:
            bHt = pmax(s.rangeHigh - s.rangeLow, mt)
            if s.stopSide == DIR_ACCUM:
                bNear = (abs(pl - s.rangeLow) <= pA * boundaryTolATR or abs(pl - s.origLow) <= pA * boundaryTolATR
                         or pl <= s.rangeLow + bHt * phaseBZoneFrac)
                bHolds = pl >= s.origLow - pA * boundaryTolATR
                bClose = pCPos >= 0.45
                bTc = f_testClass(bNear, bHolds, bClose, pEff, pSpr, s.climaxEff, s.climaxSpr)
                bSc = ((1 if bNear else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0)
                       + (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if bHolds else 0)
                       + (1 if bClose else 0) + 1)
                bIsProv = s.provEdge == DIR_ACCUM and not na(s.provBar) and abs(pivBar - s.provBar) <= p1
                if bNear:
                    s.lastActBar = bar_index
                if bTc == TEST_FAILED and not bIsProv:
                    s.lastBadBar = pivBar
                elif bTc == TEST_GOOD and bSc >= stMinScore:
                    f_registerST(s, pl, pTime, pivBar, pEff, pSpr, bSc, B)
                    sig = f_addBit(sig, BIT_ST)
            else:
                if pl < s.rangeLow and pl >= nz(s.origLow, s.rangeLow) - origHt1 * phaseBEdgeExpansionCap:
                    s.rangeLow = pl
                oHtL = pmax(s.rangeHigh - s.rangeLow, mt)
                oNearL = pl <= s.rangeLow + pA * boundaryTolATR or pl <= s.rangeLow + oHtL * phaseBZoneFrac
                oInsideL = pl >= nz(s.origLow, s.rangeLow) - origHt1 * phaseBEdgeExpansionCap
                oCtrlL = pEff <= s.climaxEff * 1.20 and pSpr <= s.climaxSpr * 1.20
                if oNearL and oInsideL and oCtrlL and (na(s.opLastBar) or pivBar > s.opLastBar):
                    f_registerOpp(s, pl, pTime, pivBar, pEff, pSpr, B)
        if newPH and not phUsed and s.phase == PHASE_B and rk1 and pivBar > s.bStartBar:
            bHtH = pmax(s.rangeHigh - s.rangeLow, mt)
            if s.stopSide == DIR_DIST:
                hNear = (abs(ph - s.rangeHigh) <= pA * boundaryTolATR or abs(ph - s.origHigh) <= pA * boundaryTolATR
                         or ph >= s.rangeHigh - bHtH * phaseBZoneFrac)
                hHolds = ph <= s.origHigh + pA * boundaryTolATR
                hClose = pCPos <= 0.55
                hTc = f_testClass(hNear, hHolds, hClose, pEff, pSpr, s.climaxEff, s.climaxSpr)
                hSc = ((1 if hNear else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0)
                       + (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if hHolds else 0)
                       + (1 if hClose else 0) + 1)
                hIsProv = s.provEdge == DIR_DIST and not na(s.provBar) and abs(pivBar - s.provBar) <= p1
                if hNear:
                    s.lastActBar = bar_index
                if hTc == TEST_FAILED and not hIsProv:
                    s.lastBadBar = pivBar
                elif hTc == TEST_GOOD and hSc >= stMinScore:
                    f_registerST(s, ph, pTime, pivBar, pEff, pSpr, hSc, B)
                    sig = f_addBit(sig, BIT_ST)
            else:
                if ph > s.rangeHigh and ph <= nz(s.origHigh, s.rangeHigh) + origHt1 * phaseBEdgeExpansionCap:
                    s.rangeHigh = ph
                oHtH = pmax(s.rangeHigh - s.rangeLow, mt)
                oNearH = ph >= s.rangeHigh - pA * boundaryTolATR or ph >= s.rangeHigh - oHtH * phaseBZoneFrac
                oInsideH = ph <= nz(s.origHigh, s.rangeHigh) + origHt1 * phaseBEdgeExpansionCap
                oCtrlH = pEff <= s.climaxEff * 1.20 and pSpr <= s.climaxSpr * 1.20
                if oNearH and oInsideH and oCtrlH and (na(s.opLastBar) or pivBar > s.opLastBar):
                    f_registerOpp(s, ph, pTime, pivBar, pEff, pSpr, B)

        # Traversals of the range (lines 1464-1475): every new pivot counts, plUsed / phUsed or not
        if s.phase == PHASE_B and not na(s.rangeHigh) and not na(s.rangeLow):
            tvHt = pmax(s.rangeHigh - s.rangeLow, mt)
            loZoneP = newPL and pl <= s.rangeLow + tvHt * phaseBZoneFrac
            hiZoneP = newPH and ph >= s.rangeHigh - tvHt * phaseBZoneFrac
            zoneNow = (-1 if loZoneP else 1) if loZoneP != hiZoneP else 0
            if zoneNow != 0 and (na(s.lastZoneBar) or pivBar > s.lastZoneBar):
                if s.lastZone != 0 and zoneNow != s.lastZone:
                    s.travCount = s.travCount + 1
                    s.lastActBar = bar_index
                s.lastZone = zoneNow
                s.lastZoneBar = pivBar

        # Test of a spring / UTAD (lines 1477-1502)
        if (newPL and s.phase == PHASE_C and s.outcome == DIR_ACCUM and s.exc and not s.excTested
                and pivBar > s.excBar and not na(s.rangeLow)):
            xNearL = pl <= s.rangeLow + pA * testTolATR
            xKeepL = pl >= s.excPrice - pA * testExtremeToleranceATR
            xScL = ((1 if pEff <= s.excEff * testMaxVolRatio else 0)
                    + (1 if pSpr <= s.excSpr * testMaxSpreadRatio else 0) + (1 if pCPos >= 0.50 else 0))
            if xNearL and xKeepL and xScL >= testMinScore:
                s.excTested = True
                s.cReadyBar = bar_index
                s.testTime = pTime
                s.testPrice = pl
                s.testScore = xScL
                s.cfTest = True
                f_setEvent(s, EV_TEST, B)
                sig = f_addBit(sig, BIT_TEST)
        if (newPH and s.phase == PHASE_C and s.outcome == DIR_DIST and s.exc and not s.excTested
                and pivBar > s.excBar and not na(s.rangeHigh)):
            xNearH = ph >= s.rangeHigh - pA * testTolATR
            xKeepH = ph <= s.excPrice + pA * testExtremeToleranceATR
            xScH = ((1 if pEff <= s.excEff * testMaxVolRatio else 0)
                    + (1 if pSpr <= s.excSpr * testMaxSpreadRatio else 0) + (1 if pCPos <= 0.50 else 0))
            if xNearH and xKeepH and xScH >= testMinScore:
                s.excTested = True
                s.cReadyBar = bar_index
                s.testTime = pTime
                s.testPrice = ph
                s.testScore = xScH
                s.cfTest = True
                f_setEvent(s, EV_TEST, B)
                sig = f_addBit(sig, BIT_TEST)

        # LPS / LPSY (lines 1504-1529)
        if (newPL and s.phase == PHASE_D and s.outcome == DIR_ACCUM and not na(s.strBar) and pivBar > s.strBar
                and not na(s.rangeHigh)):
            lHard = f_hardLevel(s, DIR_ACCUM)
            lSide = not na(lHard) and pl > lHard - pA * testExtremeToleranceATR
            lCreek = pl >= s.rangeHigh - pA * lpsBoundaryATR
            lSc = ((1 if pEff <= pAvgEff * lpsVolMult else 0) + (1 if pSpr <= pA * lpsSpreadATR else 0)
                   + (1 if pCPos >= 0.45 else 0))
            if lSide and lCreek and lSc >= lpsMinScore:
                s.lpsTime = pTime
                s.lpsPrice = pl
                s.lpsBar = bar_index
                s.lpsScore = lSc
                s.cfLPS = True
                f_setEvent(s, EV_LPS, B)
                sig = f_addBit(sig, BIT_LPS)
        if (newPH and s.phase == PHASE_D and s.outcome == DIR_DIST and not na(s.strBar) and pivBar > s.strBar
                and not na(s.rangeLow)):
            yHard = f_hardLevel(s, DIR_DIST)
            ySide = not na(yHard) and ph < yHard + pA * testExtremeToleranceATR
            yIce = ph <= s.rangeLow + pA * lpsBoundaryATR
            ySc = ((1 if pEff <= pAvgEff * lpsVolMult else 0) + (1 if pSpr <= pA * lpsSpreadATR else 0)
                   + (1 if pCPos <= 0.55 else 0))
            if ySide and yIce and ySc >= lpsMinScore:
                s.lpsTime = pTime
                s.lpsPrice = ph
                s.lpsBar = bar_index
                s.lpsScore = ySc
                s.cfLPS = True
                f_setEvent(s, EV_LPSY, B)
                sig = f_addBit(sig, BIT_LPSY)

        # Springs and UTADs (lines 1531-1610)
        p2 = nz(s.pivLen, liveLen)
        rk2 = not na(s.rangeHigh) and not na(s.rangeLow)
        rH2 = s.rangeHigh
        rL2 = s.rangeLow
        recLimit2 = f_excursionRecoveryLimit(p2)
        mature2 = f_matureWS(s, p2, a, B)
        bAge2 = bar_index - s.bStartBar if not na(s.bStartBar) else 0
        probeB = s.phase == PHASE_B and s.stCount >= 1 and bAge2 >= max(3, p2 * 2)
        probeCLo = s.phase == PHASE_C and s.outcome == DIR_ACCUM and not s.exc
        probeCHi = s.phase == PHASE_C and s.outcome == DIR_DIST and not s.exc
        if rk2 and not s.pend and (na(s.pendCoolBar) or bar_index > s.pendCoolBar):
            penLo = rL2 - l
            penHi = h - rH2
            okLo = (probeB or probeCLo) and penLo >= a * springMinPenATR and penLo <= a * springMaxPenATR
            okHi = (probeB or probeCHi) and penHi >= a * springMinPenATR and penHi <= a * springMaxPenATR
            if okLo != okHi:
                s.pend = True
                s.pendEdge = DIR_ACCUM if okLo else DIR_DIST
                s.pendStartBar = bar_index
                s.pendExtBar = bar_index
                s.pendExt = l if okLo else h
                s.pendExtTime = t_ms
                s.pendEff = eff
                s.pendSpr = spr
        if s.pend and rk2 and (s.phase == PHASE_B or s.phase == PHASE_C):
            if s.pendEdge == DIR_ACCUM and l < s.pendExt:
                s.pendExt = l
                s.pendExtBar = bar_index
                s.pendExtTime = t_ms
                s.pendEff = pmax(nz(s.pendEff), eff)
                s.pendSpr = pmax(nz(s.pendSpr), spr)
            elif s.pendEdge == DIR_DIST and h > s.pendExt:
                s.pendExt = h
                s.pendExtBar = bar_index
                s.pendExtTime = t_ms
                s.pendEff = pmax(nz(s.pendEff), eff)
                s.pendSpr = pmax(nz(s.pendSpr), spr)
            recAge = bar_index - s.pendStartBar
            recovered = c > rL2 if s.pendEdge == DIR_ACCUM else c < rH2
            depth = rL2 - s.pendExt if s.pendEdge == DIR_ACCUM else s.pendExt - rH2
            depthOK = depth >= a * springMinPenATR and depth <= a * springMaxPenATR
            if s.pendEdge == DIR_ACCUM:
                recSc = ((1 if cPos >= springCloseMin else 0) + (1 if eff <= avgEff * springEffortMaxMult else 0)
                         + (1 if c > o else 0) + (1 if spr >= a * 0.50 else 0))
            else:
                recSc = ((1 if cPos <= utadCloseMax else 0) + (1 if eff <= avgEff * springEffortMaxMult else 0)
                         + (1 if c < o else 0) + (1 if spr >= a * 0.50 else 0))
            if recovered and depthOK and recAge <= recLimit2 and recSc >= excursionMinScore:
                probeEdge = s.pendEdge
                exc_flag = 1 if probeEdge == DIR_ACCUM else -1
                exc_px = s.pendExt
                if s.phase == PHASE_B and not mature2:
                    s.provEdge = probeEdge
                    s.provBar = s.pendExtBar
                    s.provPrice = s.pendExt
                    s.provTime = s.pendExtTime
                    s.provEff = s.pendEff
                    s.provSpr = s.pendSpr
                    s.provScore = recSc
                    s.lastActBar = bar_index
                    s.pend = False
                else:
                    if s.phase == PHASE_C:
                        f_clearTerminal(s)
                    f_excFromPend(s, recSc, B)
                    sig = f_addBit(sig, BIT_SPRING if probeEdge == DIR_ACCUM else BIT_UTAD)
            elif recAge > recLimit2 or ((not depthOK) and depth > a * springMaxPenATR):
                if s.phase == PHASE_B:
                    s.lastBadBar = bar_index
                s.pend = False
                s.pendCoolBar = bar_index + p2

        if s.phase == PHASE_C and s.exc and not s.excTested and rk2:
            if s.outcome == DIR_ACCUM and l < s.excPrice and l >= rL2 - a * springMaxPenATR:
                s.excPrice = l
                s.excBar = bar_index
                s.excTime = t_ms
                s.excEff = pmax(nz(s.excEff), eff)
                s.excSpr = pmax(nz(s.excSpr), spr)
            elif s.outcome == DIR_DIST and h > s.excPrice and h <= rH2 + a * springMaxPenATR:
                s.excPrice = h
                s.excBar = bar_index
                s.excTime = t_ms
                s.excEff = pmax(nz(s.excEff), eff)
                s.excSpr = pmax(nz(s.excSpr), spr)

        # SOS / SOW: C -> D (lines 1612-1641)
        if s.phase == PHASE_C and rk2 and not s.pend:
            cMinD = f_phaseCToDMinBars(p2)
            cFormal = not s.exc or s.excTested
            cAnchor = s.cReadyBar if not na(s.cReadyBar) else s.excBar
            cAgeReady = not na(cAnchor) and bar_index - cAnchor >= cMinD
            cVal = f_validationWS(s, p2, trendScore, a, B)
            cValD = cVal if cFormal else min(100, cVal + 13)
            cConf = f_confWS(s)
            cConfD = cConf if cFormal else min(100, cConf + 30)
            cHt = pmax(rH2 - rL2, mt)
            if cAgeReady and cValD >= phaseDValidationMin and cConfD >= minConfidencePhaseC:
                if s.outcome == DIR_ACCUM and ageOKBull:
                    domUp = rL2 + cHt * phaseDDominanceFrac
                    brkUp = c > rH2 + a * breakATR
                    if cFormal:
                        domOKUp = brkUp or (c >= domUp and close1 >= domUp)
                    else:
                        domOKUp = brkUp or (c >= domUp and close1 >= domUp and close2 >= domUp)
                    reqUp = strengthMinScore if cFormal else max(2, strengthMinScore - 1)
                    qUp = sosScore >= reqUp or mbSOS or ((not cFormal) and res3Up >= 1.0)
                    if domOKUp and qUp:
                        f_promoteD(s, DIR_ACCUM, sosScore, h, B)
                        sig = f_addBit(sig, BIT_SOS)
                elif s.outcome == DIR_DIST and ageOKBear:
                    domDn = rH2 - cHt * phaseDDominanceFrac
                    brkDn = c < rL2 - a * breakATR
                    if cFormal:
                        domOKDn = brkDn or (c <= domDn and close1 <= domDn)
                    else:
                        domOKDn = brkDn or (c <= domDn and close1 <= domDn and close2 <= domDn)
                    reqDn = strengthMinScore if cFormal else max(2, strengthMinScore - 1)
                    qDn = sowScore >= reqDn or mbSOW or ((not cFormal) and res3Dn >= 1.0)
                    if domOKDn and qDn:
                        f_promoteD(s, DIR_DIST, sowScore, l, B)
                        sig = f_addBit(sig, BIT_SOW)

        # B -> D directly with a provisional excursion, or a departure (lines 1643-1676)
        resetLate = -1
        if s.phase == PHASE_B and rk2 and not s.pend:
            dHt = pmax(rH2 - rL2, mt)
            dBuf = pmax(dHt * phaseBDepartureTRFrac, a * phaseBDepartureATR)
            upAcc = c > rH2 + a * breakATR and close1 > rH2 + a * breakATR
            dnAcc = c < rL2 - a * breakATR and close1 < rL2 - a * breakATR
            upSus = loCDep > rH2 + dBuf
            dnSus = hiCDep < rL2 - dBuf
            upGo = (upAcc and (sosScore >= strengthMinScore or mbSOS)) or upSus
            dnGo = (dnAcc and (sowScore >= strengthMinScore or mbSOW)) or dnSus
            provLimit = f_phaseIdleLimit(PHASE_C, True, p2)
            if upGo and not dnGo:
                upProv = s.provEdge == DIR_ACCUM and not na(s.provBar) and bar_index - s.provBar <= provLimit
                if ageOKBull and upProv and mature2:
                    f_adoptProv(s)
                    f_promoteD(s, DIR_ACCUM, sosScore, h, B)
                    sig = f_addBit(sig, BIT_SPRING)
                    sig = f_addBit(sig, BIT_SOS)
                elif upSus and not upProv:
                    resetLate = RS_DEPART
            elif dnGo and not upGo:
                dnProv = s.provEdge == DIR_DIST and not na(s.provBar) and bar_index - s.provBar <= provLimit
                if ageOKBear and dnProv and mature2:
                    f_adoptProv(s)
                    f_promoteD(s, DIR_DIST, sowScore, l, B)
                    sig = f_addBit(sig, BIT_UTAD)
                    sig = f_addBit(sig, BIT_SOW)
                elif dnSus and not dnProv:
                    resetLate = RS_DEPART
        if resetLate >= 0:
            self.rsCounts[resetLate] += 1
            self.lastResetWhy = resetLate
            self._lose(s)
            s = self.s = WS()
            f_initPivotHistory(s)

        # A later SOS / SOW after an LPS / LPSY (lines 1678-1693)
        if s.phase == PHASE_D and s.outcome == DIR_ACCUM and s.ev == EV_LPS and not na(s.rangeHigh):
            if c > s.rangeHigh + a * breakATR and relE >= strengthVolMult and cPos >= sosCloseMin:
                s.strBar = bar_index
                s.strTime = t_ms
                s.strPrice = h
                s.strScore = sosScore
                f_setEvent(s, EV_SOS, B)
                sig = f_addBit(sig, BIT_SOS)
        if s.phase == PHASE_D and s.outcome == DIR_DIST and s.ev == EV_LPSY and not na(s.rangeLow):
            if c < s.rangeLow - a * breakATR and relE >= strengthVolMult and cPos <= sowCloseMax:
                s.strBar = bar_index
                s.strTime = t_ms
                s.strPrice = l
                s.strScore = sowScore
                f_setEvent(s, EV_SOW, B)
                sig = f_addBit(sig, BIT_SOW)

        # Acceptance into Phase E (lines 1695-1727)
        if s.phase == PHASE_D and not na(s.rangeHigh) and not na(s.rangeLow):
            eConf = f_confWS(s)
            dAge = bar_index - s.dStartBar if not na(s.dStartBar) else 0
            dMin = f_phaseDMinBars(nz(s.pivLen, liveLen))
            if s.outcome == DIR_ACCUM:
                s.outCount = s.outCount + 1 if c > s.rangeHigh else 0
                eOppOKU = self.regime != REGIME_MARKDOWN or s.cfLPS
                eStdU = (s.cfLPS and not na(s.lpsBar) and bar_index - s.lpsBar >= confirmBars and dAge >= dMin
                         and loCConf > s.rangeHigh and eConf >= minConfidencePhaseD)
                eDirU = (not s.cfLPS and dAge >= max(dMin, directAcceptanceBars) and loCDir > s.rangeHigh
                         and eConf >= directAcceptanceConfidence)
                if (eStdU or eDirU) and eOppOKU:
                    s.cfAccept = True
                    s.phase = PHASE_E
                    s.eStartBar = bar_index
                    s.eStartTime = t_ms
                    self.regime = REGIME_MARKUP
                    self.regimeBar = bar_index
                    f_setEvent(s, EV_MARKUP, B)
                    sig = f_addBit(sig, BIT_E)
            elif s.outcome == DIR_DIST:
                s.outCount = s.outCount + 1 if c < s.rangeLow else 0
                eOppOKD = self.regime != REGIME_MARKUP or s.cfLPS
                eStdD = (s.cfLPS and not na(s.lpsBar) and bar_index - s.lpsBar >= confirmBars and dAge >= dMin
                         and hiCConf < s.rangeLow and eConf >= minConfidencePhaseD)
                eDirD = (not s.cfLPS and dAge >= max(dMin, directAcceptanceBars) and hiCDir < s.rangeLow
                         and eConf >= directAcceptanceConfidence)
                if (eStdD or eDirD) and eOppOKD:
                    s.cfAccept = True
                    s.phase = PHASE_E
                    s.eStartBar = bar_index
                    s.eStartTime = t_ms
                    self.regime = REGIME_MARKDOWN
                    self.regimeBar = bar_index
                    f_setEvent(s, EV_MARKDOWN, B)
                    sig = f_addBit(sig, BIT_E)

        # Entry check (lines 1729-1747), once per strictness mode, each with its own slot
        entries = {}
        for mode in self.modes:
            if na(s.entryTime[mode]) and s.outcome != DIR_NONE:
                eMinConf = (entryMinConfidenceConservative if mode == "Conservative"
                            else entryMinConfidenceStandard if mode == "Standard" else entryMinConfidenceAggressive)
                eMinTests = (entryMinTestsConservative if mode == "Conservative"
                             else entryMinTestsStandard if mode == "Standard" else entryMinTestsAggressive)
                eValFloor = phaseDValidationMin if mode == "Conservative" else max(45, phaseDValidationMin - 10)
                eVal = f_validationWS(s, nz(s.pivLen, liveLen), trendScore, a, B)
                eReady = f_entryReadinessWS(s, eMinConf, eValFloor, a, B)
                eQuality = f_confWS(s) >= eMinConf and eVal >= eValFloor and eReady >= eMinTests
                testBit = f_hasBit(sig, BIT_TEST) or f_hasBit(sig, BIT_CTEST)
                strengthBit = f_hasBit(sig, BIT_SOS) or f_hasBit(sig, BIT_SOW)
                lpsBit = f_hasBit(sig, BIT_LPS) or f_hasBit(sig, BIT_LPSY)
                aggressiveTestTrig = mode == "Aggressive" and testBit and eQuality
                aggressiveStrengthFallback = mode == "Aggressive" and strengthBit and eQuality and na(s.testTime)
                standardTestTrig = mode == "Standard" and testBit and eQuality and s.testScore >= testMinScore
                standardLpsFallback = mode == "Standard" and lpsBit and eQuality
                conservativeLpsTrig = mode == "Conservative" and lpsBit and eQuality
                if (aggressiveTestTrig or aggressiveStrengthFallback or standardTestTrig or standardLpsFallback
                        or conservativeLpsTrig):
                    s.entryTime[mode] = t_ms
                    s.entryPrice[mode] = c
                    s.entryKind[mode] = (ENTRY_LPS if (standardLpsFallback or conservativeLpsTrig)
                                         else (ENTRY_STRENGTH if aggressiveStrengthFallback else ENTRY_TEST))
            # the alert (lines 2236-2238): the slot was set on this bar
            cEntryT, cEntryKind = s.entryTime[mode], s.entryKind[mode]
            now = not na(cEntryT) and ptrunc(cEntryT) == t_ms and cEntryKind != ENTRY_NONE
            entries[mode] = (1 if s.outcome == DIR_ACCUM else -1 if s.outcome == DIR_DIST else 0) if now else 0

        if self.trace is not None:
            self.trace.clear()
            self.trace.update(
                bar_index=bar_index, eff=eff, spr=spr, avgEff=avgEff, avgEffPrev=avgEffPrev, atrRaw=atrRaw, a=a,
                aPrev=aPrev, cPos=cPos, relE=relE, priorLo=priorLo, priorHi=priorHi, newLow=newLow, newHigh=newHigh,
                liveLen=liveLen, preLen=preLen, pLen=pLen, ph=ph, pl=pl, pivBar=pivBar, pA=pA, newPL=newPL,
                newPH=newPH, trendBars=trendBars, trendEnd=trendEnd, trendScore=trendScore, volHit=volHit,
                sprHit=sprHit, isSC=isSC, isBC=isBC, probeOpen=probeOpen, resetWhy=resetWhy, resetLate=resetLate,
                mature1=mature1, mature2=mature2, recLimit2=recLimit2, sosScore=sosScore, sowScore=sowScore,
                sig=sig, lost=self.lost)

        return {
            "phase": s.phase, "outcome": s.outcome,
            "campaign": int(s.startBar) if s.phase != PHASE_NONE else -1,
            "range_lo": s.rangeLow, "range_hi": s.rangeHigh,
            "hard_lo": f_hardLevel(s, DIR_ACCUM), "hard_hi": f_hardLevel(s, DIR_DIST),
            "sig": sig, "climax": climax_flag, "climax_px": climax_px, "exc": exc_flag, "exc_px": exc_px,
            "entries": entries, "in_cde": s.outcome != DIR_NONE and not self.lost,
        }


# ───────────────────────────── the public function ─────────────────────────────

def infer_mintick(*prices) -> float:
    """``syminfo.mintick`` read from the data: 10^-d for the smallest d in 0..8 such that every price is a multiple
    of 10^-d (within 1e-6 of a grid step); 1e-8 when none is."""
    px = np.concatenate([np.asarray(p, np.float64).ravel() for p in prices])
    px = px[np.isfinite(px)]
    for d in range(0, 9):
        q = px * 10.0 ** d
        if np.all(np.abs(q - np.round(q)) <= 1e-6):
            return 10.0 ** (-d)
    return 1e-8


def _bar_seconds(t: np.ndarray) -> float:
    """``timeframe.in_seconds(timeframe.period)``: the most frequent positive spacing of the open times."""
    d = np.diff(np.asarray(t, np.int64))
    d = d[d > 0]
    if len(d) == 0:
        return 1.0
    return float(Counter(d.tolist()).most_common(1)[0][0])


def wyckoff(o, h, l, c, v, t, no_vol: bool = False, *, mintick: Optional[float] = None,
            _modes: Sequence[str] = MODES, _ties: str = "strict") -> Dict[str, np.ndarray]:
    """The engine of "Wyckoff [theUltimator5]" on the chart timeframe, every input at its default; see the module
    docstring for the inputs, the outputs and the readings. ``_modes`` / ``_ties`` exist for the tests and the
    sensitivity checks only (a mode left out gives all-zero entries)."""
    o, h, l, c = (np.asarray(x, np.float64) for x in (o, h, l, c))
    n = len(c)
    if not (len(o) == len(h) == len(l) == n):
        raise ValueError("o, h, l, c must have the same length")
    t = np.asarray(t)
    if len(t) != n:
        raise ValueError("t must have one open time per bar")
    if t.dtype.kind not in "iuf":
        raise ValueError("t: UTC epoch seconds (int or float) expected")
    t = t.astype(np.int64)
    if no_vol or v is None:
        v = np.zeros(n)
    v = np.asarray(v, np.float64)
    if len(v) != n:
        raise ValueError("v must have one value per bar")
    if mintick is None:
        mintick = infer_mintick(o, h, l, c)
    eng = Engine(float(mintick), _bar_seconds(t), modes=_modes, ties=_ties)
    out = {
        "phase": np.zeros(n, np.int8), "outcome": np.zeros(n, np.int8), "campaign": np.full(n, -1, np.int32),
        "range_lo": np.full(n, np.nan), "range_hi": np.full(n, np.nan),
        "hard_lo": np.full(n, np.nan), "hard_hi": np.full(n, np.nan),
        **{k: np.zeros(n, bool) for k in EVENT_BITS},
        "climax": np.zeros(n, np.int8), "climax_px": np.full(n, np.nan),
        "exc": np.zeros(n, np.int8), "exc_px": np.full(n, np.nan),
        "entry_std": np.zeros(n, np.int8), "entry_agg": np.zeros(n, np.int8), "entry_con": np.zeros(n, np.int8),
        "in_cde": np.zeros(n, bool),
    }
    ol, hl, ll, cl, vl, tl = o.tolist(), h.tolist(), l.tolist(), c.tolist(), v.tolist(), t.tolist()
    for i in range(n):
        r = eng.step(ol[i], hl[i], ll[i], cl[i], vl[i], int(tl[i]) * 1000)
        out["phase"][i] = r["phase"]
        out["outcome"][i] = r["outcome"]
        out["campaign"][i] = r["campaign"]
        out["range_lo"][i] = r["range_lo"]
        out["range_hi"][i] = r["range_hi"]
        out["hard_lo"][i] = r["hard_lo"]
        out["hard_hi"][i] = r["hard_hi"]
        sig = r["sig"]
        for k, bit in EVENT_BITS.items():
            out[k][i] = f_hasBit(sig, bit)
        out["climax"][i] = r["climax"]
        out["climax_px"][i] = r["climax_px"]
        out["exc"][i] = r["exc"]
        out["exc_px"][i] = r["exc_px"]
        for mode, d in r["entries"].items():
            out[ENTRY_KEY[mode]][i] = d
        out["in_cde"][i] = r["in_cde"]
    return out
