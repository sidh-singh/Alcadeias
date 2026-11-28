"""
PORT B (the oracle) of the Market Structure Dashboard (Flux Charts): a literal, bar-by-bar transcription of its bias.

Study 2 of the TradeIQ research, ``backtest_results/tradeiq_2027/PREREG.md`` (frozen): the dashboard is its section
6.2, it is used again in 6.10 (STK) and it is the subject of claims 13 and 14 of section 8. As in study 1, two
engineers port the script independently from the Pine source. Port A is ``backtesting/research/tradeiq2_ind_msd.py``
(the fast one the study runs). This file is port B: plain Python, one object per Pine call site holding the state that
call site keeps in Pine (``var``), every statement evaluated bar by bar in Pine's order, written to be obviously
correct rather than fast. It is the reference port A is checked against. It imports nothing from the repository (not
``tradeiq_ind.py``, no ``tradeiq2_ind_*`` module), only numpy and the standard library. Its tests are
``tests/test_tradeiq2_ind_msd_b.py``.

``Lnnn`` is a line of the Pine source "Market Structure Dashboard Pine Script.txt" (1,749 lines, ``//@version=6``,
MPL-2.0, (c) fluxchart). The source is third-party code and is not in the repository; only line numbers and identifiers
are cited.

The contract (the same function names and output keys in both ports, so they can be compared mechanically)
-----------------------------------------------------------------------------------------------------------
``structure_dashboard(rows, chart_tf, model="A")`` returns a dict of numpy arrays, one value per chart bar:

* ``rows``: ``{'1H' | '4H' | '1D' | '1W': bars}``; ``bars`` has numpy arrays ``t`` (open time, UTC s), ``tc`` (close
  time, strictly increasing), ``o``, ``h``, ``l``, ``c`` (bid). The chart's bars are ``rows[chart_tf]``. The 1H / 4H /
  1D bars are study 1's (``tradeiq_market.TMarket.tbars``); the weekly bars come from ``weekly_bars`` below.
* ``chart_tf`` in {'1H', '4H', '1D'}. The active rows are those at or above the chart (``tfActive``, L692): 1H chart:
  1H, 4H, 1D, 1W; 4H chart: 4H, 1D, 1W; 1D chart: 1D, 1W. Only those must be in ``rows``.
* ``label`` (int8): +2 BULLISH, +1 LEAN BULL, 0 NEUTRAL, -1 LEAN BEAR, -2 BEARISH (L1343-1344, in integers).
* ``score`` (int64, ``biasPoints``), ``max_score`` (int64, ``maxScore``: 44 / 36 / 28 on 1H / 4H / 1D).
* per active row ``r``: ``s_<r>`` (int64, the row's score -4..+4, before its weight), ``struct_<r>``, ``ob_<r>``,
  ``fvg_<r>``, ``swing_<r>`` (int8, -1 / 0 / +1: the four factors after ``dirScore``).
* ``bos`` (int8): +1 at a bullish break of structure of the chart row on this bar, -1 at a bearish one, else 0;
  ``bos_trend`` (int8): the side of the most recent break, 0 before the first.
* Only ``model="A"`` exists here; model B (the forming higher-timeframe bar, claim 14) is port A's alone.
* Optional keywords (not part of the comparison): ``mintick`` (``syminfo.mintick``; by default taken from the chart
  bars' ``mintick`` or ``symbol`` attribute: 0.001 gold, 0.01 BTC) and ``ties`` (the pivot tie reading, R1).

``weekly_bars(day_bars, end_s=None)``: the ISO (Monday-start) weeks of the merged 1D bars (R8); ``end_s``, the data's
end, keeps a last week that is still forming from being read as closed.
``calc_all(bars)``: one row's state on its own bars (used by the tests and for counts).

What is computed
----------------
1. **One row** (``Row``): the script's ``calcAll()`` (L684-690) on the bars of one timeframe, as
   ``request.security(syminfo.tickerid, tf, calcAll())`` runs it (L695-701). The globals that ``calcAll`` reads
   (L247-254: ``pivotHigh``, ``pivotLow``, ``_green``, ``_red``, ``bullFVG``, ``bearFVG``) are evaluated in the row's
   own context, then its call sites, each with its own ``var`` state:

   * ``calcSwingHL`` (L333-366): the last two confirmed pivot highs and lows; ``swingH = currH``, ``swingL = currL``.
   * ``calcStructure`` (L369-425): ``highType`` = +1 when a new pivot high is above the previous one, else -1 (a tie is
     LH, L384); ``lowType`` likewise (L393); both start at 0. The "real-time" override (L398-417) compares the row
     close with ``prevL`` / ``prevH``, the pivot BEFORE the latest one (not ``currL`` / ``currH``), and does not
     persist. ``structureBias`` = +1 when both overridden types are +1, -1 when both are -1, else 0 (L419-423).
   * ``calcOrderBlock(6)`` (L568-586): ``trackPivotBreaks`` (L537-565) first stores a new pivot (L544-550), THEN tests
     the break: bullish when ``close > lastPH and close[1] <= lastPH`` (``isBreakAbove``, L325), after which the pivot
     is spent (``na``, L556-557); bearish the mirror (L326, L559-563). On a break ``detectOB`` (L509-524) searches the
     bars ``bar_index - i`` for ``i = 0 .. max(0, min(barsBack, 50))``, ``barsBack = bar_index - pivotBar - 1``
     (L485, L510): the bars after the pivot bar up to the break bar, at most 51. ``findLowestCandle`` (L483-490) keeps
     the lowest low with a strict ``<`` scanning back from the break bar (a tie goes to the most recent bar) and the
     zone is that candle's high..low; ``findHighestCandle`` (L492-499) the mirror. The zone is dropped when it overlaps
     a zone of the same direction already in the array, touching included (``top >= ob.bottom and bottom <= ob.top``,
     L504), else it is ``unshift``-ed and ``limitArraySize`` pops the oldest when there are more than 6 (L475-477,
     L523-524). Then ``mitigateOBs`` (L455-463) removes bullish zones with ``close < bottom`` and bearish ones with
     ``close > top`` (by the CLOSE), and ``findNearestZone`` (L426-453) gives ``obNearDir``.
   * ``calcFVG(6)`` (L611-623): ``detectFVGSignal`` (L589-609) on the patterns of L251-254, i.e. candles k-3, k-2, k-1
     seen on bar k (``low[1] > high[3]``, ``_green[2]``, ``low[1] < high[2]``, ``low[2] < high[3]``; ``_green`` is
     ``close > open or close > close[1]``); the zone is ``unshift``-ed with no overlap test and capped at 6 BEFORE
     ``mitigateFVGs`` (L465-473) removes bullish gaps with ``low < bottom`` and bearish ones with ``high > top`` (by
     the WICK, on the detection bar too); ``findNearestZone`` gives ``fvgNearDir``.
   * ``findNearestZone`` (L426-453), on the row's close: the smallest ``|top - close|`` over bullish zones and
     ``|bottom - close|`` over bearish ones, each with a strict ``<`` from the sentinel 100000.0 (the newest zone wins a
     tie); +1 when the bullish one is strictly smaller and below 100000, else -1 when the bearish one is below 100000,
     else 0 (a bull/bear tie is bearish).
   * ``calcTrend`` (EMA 9, L328-331) is not ported: the EMA factor is off by default (L121), so it enters neither the
     points nor the maximum (L718-719, L733-734).

2. **The merge (model A)**: at chart bar i a row shows the outputs of its last bar with ``tc_row <= tc_chart[i]``
   (exactly ``tradeiq_market.htf_at``); the chart's own row is the chart bar itself. Before its first closed bar a row
   is na: ``dirScore(na)`` is 0 (L703) and the swing factor of na swings is 0 (R4).

3. **The bias** (L703-737, L1323-1346), in the chart's context:

   * the swing factor ``swingBiasDir`` (L705-708) is called at L1330, outside ``request.security``, so it uses the
     CHART close and the chart symbol's ``syminfo.mintick`` against the row's merged ``swingH`` / ``swingL``:
     ``swingRange = max(swingH - swingL, mintick)``, ``swingPct = (close - swingL) / swingRange * 100``,
     ``swingPct < 0 ? -1 : swingPct > 100 ? 1 : swingPct < 30 ? 1 : swingPct > 70 ? -1 : 0``;
   * the row score ``dirScore(structBias) + dirScore(obNearDir) + dirScore(fvgNearDir) + swingDir`` (L710-722, the
     four default factors of L118-122), times the row's weight (L64-88: 1H 2, 4H 2, D 3, W 4);
   * ``biasPoints`` = the sum over the active rows, ``maxScore`` = the sum of weight x 4 (L1333-1340): 44, 36, 28;
   * the label (L1343-1344): ``biasPct = biasPoints / maxScore * 100``; > 50 BULLISH, > 20 LEAN BULL, < -50 BEARISH,
     < -20 LEAN BEAR, else NEUTRAL, all strict. In integers: BULLISH iff 2p > m, LEAN BULL iff 5p > m, the mirrors for
     bearish. Both are computed on every bar and must agree (R5).

4. **bos / bos_trend**: the chart row's ``trackPivotBreaks`` (L537-565; the same as the chart-timeframe call at L633).

Readings (R1-R16; where Pine is ambiguous, where the harness decides, or where a trap is easy to fall into)
------------------------------------------------------------------------------------------------------------
"Measured" below: with this port on study 1's bars to 2024-06-30, labels of chart bars closing in 2019-2022 (gold
23,591 / 6,386 / 1,032 bars on the 1H / 4H / 1D charts, BTC 35,017 / 8,757 / 1,460).

* R1 Pivot ties (L249-250, ``ta.pivothigh(high, 5, 5)`` / ``ta.pivotlow(low, 5, 5)``): TradingView does not document
  ties. Reading: strict on both sides (PREREG 6.2): the candidate ``src[5]`` must be strictly above (below) each of the
  5 bars before it and the 5 after it; na on the first 10 bars of a row. The alternatives ``ties="ties_left"``
  (equal to an older bar allowed), ``"ties_right"`` and ``"ties_both"`` exist only to measure the reading. Measured:
  allowing ties on both sides adds 7 highs and 3 lows to gold's 5,463 1H pivots (data start to 2024-06), 2 highs on
  gold 4H, 2 highs on BTC 1H, none on D or W, and changes 16 gold and 7 BTC 1H-chart labels of 2019-2022, none on the
  4H or 1D charts.
* R2 Bool history before the first bar (``_green[2]``, L253): false (v6 bools are never na). Unreachable: the FVG
  patterns also need ``high[3]``, which is na on the first three bars.
* R3 The swing factor's ``close`` and ``mintick`` are the chart's (L1330 is outside ``request.security``). Not
  ambiguous in Pine; listed because it is the spec's risk 3. Measured: the row's own close instead would change 2,629
  gold and 2,902 BTC 1H-chart labels (709 / 711 on 4H, 73 / 70 on 1D).
* R4 na arithmetic: ``math.max(na, mintick)`` is na (L706), so the swing factor is 0 while either swing is na (every
  comparison with na is false, L708); ``dirScore(na)`` is 0. ``tfActive`` (L692) depends on the timeframes only, so a
  row before its first closed bar still counts in ``maxScore`` (L1338-1339).
* R5 Division (L1343): v6 divides two ints with a fractional result (and ``biasPoints`` is a series int, so even v5
  would). The label is computed in integers; the float formula is evaluated too and an AssertionError is raised if
  they differ (they cannot: 50% falls on p = 22/44, 18/36, 14/28 where p/m = 0.5 exactly, and 20% on no integer p).
* R6 Loops: ``for i = obCount - 1 to 0`` (L458, L468) counts down (Pine steps by -1 when from > to), so
  ``array.remove`` inside it is safe; every loop bound is a local fixed before the loop.
* R7 The merge (L695-701, ``lookahead_off``, historical bars): ``tc_row <= tc_chart`` (study 1's convention, as the
  plan requires). TradingView shows a closed higher-timeframe bar from the last chart bar inside it; that is the same
  chart bar whenever a chart bar ends at the row bar's close, and one bar later here otherwise (gold's Friday ends
  before 24:00 UTC, so its D and W rows reach a 1H chart at the first Sunday bar; data holes). Measured: merging at the
  last chart bar inside the row bar instead changes 47 gold 1H-chart labels (3 on 4H, 0 on 1D) and 2 / 1 / 0 on BTC.
* R8 Weekly bars: a day bar belongs to the ISO week of its last second (``tc - 1``), so gold's Sunday stub, merged
  into Monday by ``day_bars``, starts the new week, as on TradingView; the weekly ``tc`` is its last day bar's ``tc``,
  the open time its first day bar's ``t``. Alternative: the week of the day bar's open time ``t``, which would put
  every gold Monday (opened by the Sunday stub) into the previous week (measured: 4,073 gold 1H-chart labels, 1,249
  on 4H, 244 on 1D; none on BTC). A short Friday that ``day_bars`` merges into the next Monday falls into the next
  week (2 gold weeks to 2024-06; TradingView keeps it in its own week). The trailing week is complete only when the
  day bars end at a week boundary; the study's bars end on 2024-07-01 00:00 UTC, a Monday. With ``end_s`` before
  the end of the last ISO week, that week closes at its ISO end (``complete`` False), as port A and the harness.
* R9 ``syminfo.mintick``: 0.001 on gold, 0.01 on BTC (the Exness digits; also TradingView's OANDA:XAUUSD and
  BINANCE:BTCUSDT). It matters only for a range of less than one tick, i.e. an inverted range (R10). Measured: ten
  times the tick changes no label.
* R10 Inverted ranges (the last pivot high below the last pivot low): ``swingRange`` is one tick, so the factor is
  the side of ``swingL`` the chart close is on (-1 below, +1 at or above it, 0 / -1 / +1 within one tick). Literal.
  Measured: 0.61% of gold's 1H row bars and 0.21% of BTC's (0-2.2% on the other rows).
* R11 Day and 4H boundaries are UTC and a UTC day with fewer than 360 M1 bars is merged into the next (the harness),
  not TradingView's 17:00 New York roll for gold; logged by the spec. Not measured.
* R12 Path dependence: the rows start at our data start (gold 2017-01, BTC 2018-01); the 6-slot arrays and old zones
  carry state, and TradingView's history starts earlier. Measured (the spec's check, every row recomputed from the
  data start + 6 months): gold's rows agree from 2018-08-18 and no label of 2019-2022 differs; BTC's D and W rows agree
  only from 2019-06-27 and 2019-07-01, and 849 / 260 / 60 BTC labels of 2019 differ on the 1H / 4H / 1D charts, the
  last on 2019-06-30.
* R13 Order within a bar (L573-586, L614-621): the overlap test sees the order blocks before this bar's mitigation;
  the FVG cap pops before mitigation; a bullish break is handled before a bearish one (at most one break per bar:
  both need ``lastPL <= close[1] <= lastPH < close < lastPL``). Literal.
* R14 ``isBreakAbove`` / ``isBreakBelow`` read the row's ``close[1]``: na on the row's first bar, so no break there.
* R15 The structure strings (L385-396) and the swing-label overlay (L664, L677: ``<``, so a tie is "HH" / "HL" there
  while ``calcStructure`` counts it LH / LL) are display only and not ported.
* R16 The EMA factor is off (L121) and not ported; the alerts, sessions, killzones, volume / volatility states and
  the PDH / PWH / PMH levels (L1111-1293, L1636-1749) do not enter the bias and are not ported.

What is known when (no look-ahead)
----------------------------------
* A row bar k's outputs depend on that row's bars 0..k only. A pivot of bar p is known at the close of bar p + 5
  (``swingLength`` 5, L126), and is na before; a break and its order block at the break bar's close (the earliest is
  p + 6: on bar p + 5 the close is below a strict pivot high); an FVG of candles k-3..k-1 at the close of bar k.
* The outputs at chart bar i depend only on chart bars 0..i and on row bars that closed at or before ``tc_chart[i]``
  (model A). Every bar is read through ``Series[k]`` with k >= 0: there is no way to read a later bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = [
    "structure_dashboard", "weekly_bars", "calc_all", "active_rows", "max_score_of", "label_of",
    "swing_bias_dir", "dir_score", "pivot", "find_nearest_zone", "mitigate_obs", "mitigate_fvgs", "limit_array_size",
    "find_lowest_candle", "find_highest_candle", "has_overlapping_ob", "detect_fvg_signal", "iso_week_of",
    "iso_week_end",
    "Series", "ZoneBlock", "SwingData", "PivotData", "CandleSearch", "CalcSwingHL", "CalcStructure", "CalcOrderBlock",
    "CalcFVG", "Row", "WeeklyBars",
    "NA", "ROWS", "CHARTS", "WEIGHT", "ROW_SECONDS", "SWING_LENGTH", "OB_LOOKBACK", "FVG_LOOKBACK", "FACTOR_COUNT",
    "SENTINEL", "MINTICK", "TIES", "LABELS",
]

NA = float("nan")

ROWS = ("1H", "4H", "1D", "1W")
CHARTS = ("1H", "4H", "1D")
# timeframe.in_seconds() of the rows "60", "240", "D", "W" (L74-88) and of the charts
ROW_SECONDS = {"1H": 3600, "4H": 14400, "1D": 86400, "1W": 7 * 86400}
# default weights tf4Weight .. tf7Weight (L76, L80, L84, L88); tf1-tf3 (1m, 5m, 15m) are never active on our charts
WEIGHT = {"1H": 2, "4H": 2, "1D": 3, "1W": 4}
SWING_LENGTH = 5          # swingLength (L126): ta.pivothigh / ta.pivotlow (5, 5)
OB_LOOKBACK = 6           # obLookback (L165), the cap of calcOrderBlock's array (L688)
FVG_LOOKBACK = 6          # fvgLookback (L172), the cap of calcFVG's array (L689)
# the default bias factors (L118-122): structure, order block, FVG and swing on, EMA off
BIAS_USE = {"struct": True, "ob": True, "fvg": True, "ema": False, "swing": True}
FACTOR_COUNT = sum(1 for v in BIAS_USE.values() if v)        # biasFactorCount() (L725-737): 4
SENTINEL = 100000.0       # findNearestZone's starting distance (L427-428, L446, L449)
OB_SEARCH_CAP = 50        # math.min(barsBack, 50) (L485, L494)
MINTICK = {"XAUUSDm": 0.001, "BTCUSDm": 0.01}               # syminfo.mintick (R9)
TIES = ("strict", "ties_left", "ties_right", "ties_both")    # R1; "strict" is the study's reading
LABELS = {2: "BULLISH", 1: "LEAN BULL", 0: "NEUTRAL", -1: "LEAN BEAR", -2: "BEARISH"}


# ───────────────────────────── Pine values and series ─────────────────────────────

def na(x) -> bool:
    """Pine's ``na(x)``: a float na is NaN here, an int na (``lastPHBar``) is None."""
    return x is None or x != x


def pine_max(a: float, b: float) -> float:
    """``math.max(a, b)``: na when either is na (Python's ``max`` would depend on the argument order)."""
    if na(a) or na(b):
        return NA
    return a if a >= b else b


class Series:
    """
    A Pine series of one script context: ``s.push(x)`` appends this bar's value, ``s[k]`` is the value k bars back
    (``s[0]`` this bar's), and before the first bar it is ``na_value`` (na for floats, false for v6 bools, R2). A
    negative k (a later bar) is refused, so nothing can read ahead.
    """
    __slots__ = ("_v", "_na")

    def __init__(self, na_value=NA):
        self._v: List = []
        self._na = na_value

    def push(self, x) -> None:
        self._v.append(x)

    def __getitem__(self, k: int):
        if k < 0:
            raise IndexError("a series is read k >= 0 bars back only")
        n = len(self._v)
        return self._v[n - 1 - k] if k < n else self._na

    def __len__(self) -> int:
        return len(self._v)


# ───────────────────────────── the script's types (L257-301) ─────────────────────────────

class ZoneBlock:
    """``type ZoneBlock`` (L258-262): an order block or a fair value gap."""
    __slots__ = ("dir", "top", "bottom", "barIdx")

    def __init__(self, dir: int, top: float, bottom: float, barIdx: int):
        self.dir = dir
        self.top = top
        self.bottom = bottom
        self.barIdx = barIdx

    def __repr__(self) -> str:
        return f"ZoneBlock(dir={self.dir}, top={self.top}, bottom={self.bottom}, barIdx={self.barIdx})"


class SwingData:
    """``type SwingData`` (L264-268); ``SwingData.new()`` leaves every field na."""
    __slots__ = ("prevH", "currH", "prevL", "currL")

    def __init__(self):
        self.prevH = NA
        self.currH = NA
        self.prevL = NA
        self.currL = NA


class PivotData:
    """``type PivotData`` (L270-274); ``PivotData.new()`` leaves every field na."""
    __slots__ = ("lastPH", "lastPHBar", "lastPL", "lastPLBar")

    def __init__(self):
        self.lastPH = NA
        self.lastPHBar: Optional[int] = None
        self.lastPL = NA
        self.lastPLBar: Optional[int] = None


class CandleSearch:
    """``type CandleSearch`` (L282-286)."""
    __slots__ = ("price", "otherPrice", "barIdx", "barsBack")

    def __init__(self, price: float, otherPrice: float, barIdx: int, barsBack: int):
        self.price = price
        self.otherPrice = otherPrice
        self.barIdx = barIdx
        self.barsBack = barsBack


# ───────────────────────────── ta.pivothigh / ta.pivotlow (L249-250) ─────────────────────────────

def _beats(c: float, x: float, kind: str, equal_ok: bool) -> bool:
    if kind == "high":
        return c >= x if equal_ok else c > x
    return c <= x if equal_ok else c < x


def pivot(src: Series, bar_index: int, left: int, right: int, kind: str, ties: str = "strict") -> float:
    """
    ``ta.pivothigh(src, left, right)`` (``kind="high"``) or ``ta.pivotlow`` (``kind="low"``) on the current bar:
    ``src[right]`` when that bar is a pivot, else na. A pivot high is above each of the ``right`` newer bars
    (``src[0] .. src[right - 1]``) and each of the ``left`` older bars (``src[right + 1] .. src[left + right]``);
    na until the whole window exists (``bar_index >= left + right``). Ties (R1): ``"strict"`` on both sides (the
    study's reading); ``"ties_left"`` / ``"ties_right"`` / ``"ties_both"`` allow an equal value on that side.
    """
    if ties not in TIES:
        raise ValueError(f"ties: one of {TIES}, got {ties!r}")
    if bar_index < left + right:
        return NA
    c = src[right]
    eq_newer = ties in ("ties_right", "ties_both")
    eq_older = ties in ("ties_left", "ties_both")
    for k in range(0, right):
        if not _beats(c, src[k], kind, eq_newer):
            return NA
    for k in range(right + 1, left + right + 1):
        if not _beats(c, src[k], kind, eq_older):
            return NA
    return c


# ───────────────────────────── the script's functions (L321-623) ─────────────────────────────

def is_break_above(x: "Row", level: float) -> bool:
    """``isBreakAbove(level) => not na(level) and close > level and close[1] <= level`` (L325)."""
    return (not na(level)) and x.close[0] > level and x.close[1] <= level


def is_break_below(x: "Row", level: float) -> bool:
    """``isBreakBelow(level) => not na(level) and close < level and close[1] >= level`` (L326)."""
    return (not na(level)) and x.close[0] < level and x.close[1] >= level


class CalcSwingHL:
    """
    ``calcSwingHL()`` (L333-366), one call site with its own ``var`` state. ``step`` returns ``swing.currH``,
    ``swing.currL`` (the bias reads these two), the reclaim flags, and whether a pivot high / low arrived.
    """

    def __init__(self):
        self.swing = SwingData()                 # var SwingData swing = SwingData.new()     (L334)
        self.lowBroken = False                   # var bool lowBroken = false                (L335)
        self.highBroken = False                  # var bool highBroken = false               (L336)
        self.swingBias = 0                       # var int swingBias = 0                     (L360)

    def step(self, pivotHigh: float, pivotLow: float, high: float, low: float, close: float):
        swing = self.swing
        newSwingH = not na(pivotHigh)                                                        # L338
        newSwingL = not na(pivotLow)                                                         # L339
        if newSwingH:                                                                        # L341-344
            swing.prevH = swing.currH
            swing.currH = pivotHigh
            self.highBroken = False
        if newSwingL:                                                                        # L345-348
            swing.prevL = swing.currL
            swing.currL = pivotLow
            self.lowBroken = False
        if low < swing.currL:                                                                # L351-352
            self.lowBroken = True
        if high > swing.currH:                                                               # L353-354
            self.highBroken = True
        reclaimedLow = self.lowBroken and close > swing.currL                                # L357
        reclaimedHigh = self.highBroken and close < swing.currH                              # L358
        if newSwingH:                                                                        # L361-364
            self.swingBias = 1
        if newSwingL:
            self.swingBias = -1
        return swing.currH, swing.currL, bool(reclaimedLow), bool(reclaimedHigh), newSwingH, newSwingL


class CalcStructure:
    """
    ``calcStructure()`` (L369-425), one call site with its own ``var`` state (its own copy of the pivot sequence).
    ``step`` returns ``rtHighType``, ``rtLowType`` and ``structureBias``. The structure strings (L373-396) are display
    only and not kept (R15).
    """

    def __init__(self):
        self.swing = SwingData()                 # var SwingData swing = SwingData.new()     (L370)
        self.highType = 0                        # var int highType = 0                      (L377)
        self.lowType = 0                         # var int lowType = 0                       (L378)

    def step(self, pivotHigh: float, pivotLow: float, close: float):
        swing = self.swing
        if not na(pivotHigh):                                                                # L380-387
            swing.prevH = swing.currH
            swing.currH = pivotHigh
            if not na(swing.prevH):
                self.highType = 1 if swing.currH > swing.prevH else -1                       # a tie is LH (L384)
        if not na(pivotLow):                                                                 # L389-396
            swing.prevL = swing.currL
            swing.currL = pivotLow
            if not na(swing.prevL):
                self.lowType = 1 if swing.currL > swing.prevL else -1                        # a tie is LL (L393)
        rtHighType = self.highType                                                           # L399
        rtLowType = self.lowType                                                             # L400
        if (not na(swing.prevL)) and close < swing.prevL:                         # L406-410: prevL, not currL
            rtLowType = -1
        if (not na(swing.prevH)) and close > swing.prevH:                         # L413-417: prevH, not currH
            rtHighType = 1
        structureBias = 0                                                                    # L419-423
        if rtHighType == 1 and rtLowType == 1:
            structureBias = 1
        elif rtHighType == -1 and rtLowType == -1:
            structureBias = -1
        return rtHighType, rtLowType, structureBias


def find_nearest_zone(zones: Sequence[ZoneBlock], close: float) -> Tuple[int, float]:
    """``findNearestZone(zones)`` (L426-453) with the context's ``close``: (nearestDir, nearestDist)."""
    nearestBullDist = SENTINEL                                                               # L427
    nearestBearDist = SENTINEL                                                               # L428
    zoneCount = len(zones)                                                                   # L430
    if zoneCount > 0:
        for i in range(0, zoneCount):                                             # for i = 0 to zoneCount - 1
            zone = zones[i]
            if zone.dir == 1:
                dist = zone.top - close                                                      # L435
                if abs(dist) < abs(nearestBullDist):                                         # strict: the newest wins
                    nearestBullDist = dist
            else:
                dist = zone.bottom - close                                                   # L439
                if abs(dist) < abs(nearestBearDist):
                    nearestBearDist = dist
    nearestDir = 0                                                                           # L443-444
    nearestDist = 0.0
    if abs(nearestBullDist) < abs(nearestBearDist) and abs(nearestBullDist) < SENTINEL:      # L446
        nearestDir = 1
        nearestDist = nearestBullDist
    elif abs(nearestBearDist) < SENTINEL:                                                    # L449: a tie is bearish
        nearestDir = -1
        nearestDist = nearestBearDist
    return nearestDir, nearestDist


def mitigate_obs(obs: List[ZoneBlock], close: float) -> None:
    """``mitigateOBs(obs)`` (L455-463): by the CLOSE; the loop counts down, so removing is safe (R6)."""
    obCount = len(obs)
    if obCount > 0:
        for i in range(obCount - 1, -1, -1):                                                 # for i = obCount - 1 to 0
            ob = obs[i]
            if ob.dir == 1 and close < ob.bottom:
                del obs[i]                                                                   # obs.remove(i)
            elif ob.dir == -1 and close > ob.top:
                del obs[i]


def mitigate_fvgs(fvgs: List[ZoneBlock], low: float, high: float) -> None:
    """``mitigateFVGs(fvgs)`` (L465-473): by the WICK (``low`` / ``high`` of the bar)."""
    fvgCount = len(fvgs)
    if fvgCount > 0:
        for i in range(fvgCount - 1, -1, -1):                                                # for i = fvgCount - 1 to 0
            fvg = fvgs[i]
            if fvg.dir == 1 and low < fvg.bottom:
                del fvgs[i]
            elif fvg.dir == -1 and high > fvg.top:
                del fvgs[i]


def limit_array_size(arr: List[ZoneBlock], maxSize: int) -> None:
    """``limitArraySize(arr, maxSize)`` (L475-477): one ``pop()``, the last element, i.e. the oldest zone."""
    if len(arr) > maxSize:
        arr.pop()


def find_lowest_candle(x: "Row", barsBack: int) -> CandleSearch:
    """``findLowestCandle(barsBack)`` (L483-490): the bar with the lowest low among ``low[0] .. low[n]``,
    ``n = max(0, min(barsBack, 50))``, strict ``<`` from the current bar back (a tie keeps the most recent bar)."""
    search = CandleSearch(x.low[0], x.high[0], x.bar_index, barsBack)                        # L484
    for i in range(0, max(0, min(barsBack, OB_SEARCH_CAP)) + 1):                  # for i = 0 to ... (inclusive)
        if x.low[i] < search.price:
            search.price = x.low[i]
            search.otherPrice = x.high[i]
            search.barIdx = x.bar_index - i
    return search


def find_highest_candle(x: "Row", barsBack: int) -> CandleSearch:
    """``findHighestCandle(barsBack)`` (L492-499): the mirror of ``find_lowest_candle`` on the highs."""
    search = CandleSearch(x.high[0], x.low[0], x.bar_index, barsBack)                        # L493
    for i in range(0, max(0, min(barsBack, OB_SEARCH_CAP)) + 1):
        if x.high[i] > search.price:
            search.price = x.high[i]
            search.otherPrice = x.low[i]
            search.barIdx = x.bar_index - i
    return search


def has_overlapping_ob(dir: int, top: float, bottom: float, obs: Sequence[ZoneBlock]) -> bool:
    """``hasOverlappingOB`` (L501-507): a zone of the same direction with ``top >= ob.bottom and bottom <= ob.top``."""
    overlaps = False
    for ob in obs:
        if ob.dir == dir and top >= ob.bottom and bottom <= ob.top:
            overlaps = True
            break
    return overlaps


class CalcOrderBlock:
    """
    ``calcOrderBlock(maxOBs)`` (L568-586) with ``trackPivotBreaks`` (L537-565) and ``detectOB`` (L509-524), one call
    site with its own ``var`` state. ``step`` returns (bullBreak, bearBreak, nearestDir, nearestDist, created,
    rejected): the order block created on this bar (a ZoneBlock or None) and the direction of a break whose zone was
    rejected by the overlap test (0 if none).
    """

    def __init__(self, maxOBs: int = OB_LOOKBACK):
        self.maxOBs = maxOBs
        self.pivot = PivotData()                 # var PivotData pivot = PivotData.new()     (L569)
        self.obs: List[ZoneBlock] = []           # var array<ZoneBlock> obs = array.new<>()  (L570)

    def track_pivot_breaks(self, x: "Row"):
        """``trackPivotBreaks(pivot)`` (L537-565): the new pivot is stored BEFORE the break is tested."""
        pivot_ = self.pivot
        bullBreak = False                                                                    # L538-541
        bearBreak = False
        bullBar = 0
        bearBar = 0
        if not na(x.pivotHigh[0]):                                                           # L544-546
            pivot_.lastPH = x.pivotHigh[0]
            pivot_.lastPHBar = x.bar_index - x.swingLength
        if not na(x.pivotLow[0]):                                                            # L548-550
            pivot_.lastPL = x.pivotLow[0]
            pivot_.lastPLBar = x.bar_index - x.swingLength
        if is_break_above(x, pivot_.lastPH) and not na(pivot_.lastPHBar):                    # L553-557
            bullBreak = True
            bullBar = pivot_.lastPHBar
            pivot_.lastPH = NA
            pivot_.lastPHBar = None
        if is_break_below(x, pivot_.lastPL) and not na(pivot_.lastPLBar):                    # L559-563
            bearBreak = True
            bearBar = pivot_.lastPLBar
            pivot_.lastPL = NA
            pivot_.lastPLBar = None
        return bullBreak, bullBar, bearBreak, bearBar

    def detect_ob(self, x: "Row", dir: int, pivotBar: int):
        """``detectOB(dir, pivotBar, obs, maxOBs, result)`` (L509-524): (created ZoneBlock or None, the candidate)."""
        barsBack = x.bar_index - pivotBar - 1                                                # L510
        search = find_lowest_candle(x, barsBack) if dir > 0 else find_highest_candle(x, barsBack)
        newTop = search.otherPrice if dir > 0 else search.price                              # L513
        newBottom = search.price if dir > 0 else search.otherPrice                           # L514
        cand = ZoneBlock(dir, newTop, newBottom, search.barIdx)
        if not has_overlapping_ob(dir, newTop, newBottom, self.obs):                         # L516
            self.obs.insert(0, cand)                                                         # obs.unshift (L523)
            limit_array_size(self.obs, self.maxOBs)                                          # L524
            return cand, cand
        return None, cand

    def step(self, x: "Row"):
        bullBreak, bullBar, bearBreak, bearBar = self.track_pivot_breaks(x)                  # L573
        created = None
        rejected = 0
        if bullBreak:                                                                        # L577-578
            made, _ = self.detect_ob(x, 1, bullBar)
            created = made if made is not None else created
            rejected = 1 if made is None else rejected
        if bearBreak:                                                                        # L580-581
            made, _ = self.detect_ob(x, -1, bearBar)
            created = made if made is not None else created
            rejected = -1 if made is None else rejected
        mitigate_obs(self.obs, x.close[0])                                                   # L583
        nearestDir, nearestDist = find_nearest_zone(self.obs, x.close[0])                    # L584
        return bullBreak, bearBreak, nearestDir, nearestDist, created, rejected


def detect_fvg_signal(x: "Row") -> Tuple[int, float, float, int]:
    """``detectFVGSignal()`` (L589-609): (fvgDir, fvgTop, fvgBottom, fvgBar) of the gap seen on this bar."""
    fvgDir = 0
    fvgTop = 0.0
    fvgBottom = 0.0
    fvgBar = 0
    if x.bullFVG[0]:                                                                         # L596-600
        fvgDir = 1
        fvgTop = x.low[1]
        fvgBottom = x.high[3]
        fvgBar = x.bar_index - 3
    if x.bearFVG[0]:                                                                         # L603-607
        fvgDir = -1
        fvgTop = x.low[3]
        fvgBottom = x.high[1]
        fvgBar = x.bar_index - 3
    return fvgDir, fvgTop, fvgBottom, fvgBar


class CalcFVG:
    """``calcFVG(maxFVGs)`` (L611-623), one call site with its own ``var`` array. ``step`` takes the signal of
    ``detect_fvg_signal`` and the bar's low, high and close; it returns (nearestDir, nearestDist)."""

    def __init__(self, maxFVGs: int = FVG_LOOKBACK):
        self.maxFVGs = maxFVGs
        self.fvgs: List[ZoneBlock] = []          # var array<ZoneBlock> fvgs = array.new<>() (L612)

    def step(self, signal: Tuple[int, float, float, int], low: float, high: float, close: float):
        fvgDir, fvgTop, fvgBottom, fvgBar = signal                                           # L614
        if fvgDir != 0:                                                                      # L616-618
            self.fvgs.insert(0, ZoneBlock(fvgDir, fvgTop, fvgBottom, fvgBar))                # unshift
            limit_array_size(self.fvgs, self.maxFVGs)                                        # the cap BEFORE ...
        mitigate_fvgs(self.fvgs, low, high)                                                  # ... the mitigation (L620)
        return find_nearest_zone(self.fvgs, close)                                           # L621


# ───────────────────────────── one row: calcAll() in the row's context ─────────────────────────────

class Row:
    """
    One dashboard row: the script evaluated on the bars of one timeframe, as ``request.security(syminfo.tickerid,
    tf, calcAll())`` evaluates it (L695-701). ``step(o, h, l, c)`` runs one bar: the built-in series, the globals of
    L249-254 in this context, then ``calcAll()``'s call sites (L685-689) in their order, and returns that bar's
    outputs. Only bars already pushed can be read.
    """

    def __init__(self, ties: str = "strict"):
        if ties not in TIES:
            raise ValueError(f"ties: one of {TIES}, got {ties!r}")
        self.ties = ties
        self.swingLength = SWING_LENGTH
        self.bar_index = -1
        self.open = Series()
        self.high = Series()
        self.low = Series()
        self.close = Series()
        self.pivotHigh = Series()                                                            # L249
        self.pivotLow = Series()                                                             # L250
        self._green = Series(False)                                                          # L251 (R2)
        self._red = Series(False)                                                            # L252
        self.bullFVG = Series(False)                                                         # L253
        self.bearFVG = Series(False)                                                         # L254
        self.calcSwingHL = CalcSwingHL()                                                     # L686
        self.calcStructure = CalcStructure()                                                 # L687
        self.calcOrderBlock = CalcOrderBlock(OB_LOOKBACK)                                    # L688
        self.calcFVG = CalcFVG(FVG_LOOKBACK)                                                 # L689

    def step(self, o: float, h: float, l: float, c: float) -> Dict[str, object]:
        self.bar_index += 1
        self.open.push(o)
        self.high.push(h)
        self.low.push(l)
        self.close.push(c)
        open_, high, low, close = self.open, self.high, self.low, self.close
        # the globals, evaluated in this row's context (L249-254)
        self.pivotHigh.push(pivot(high, self.bar_index, self.swingLength, self.swingLength, "high", self.ties))
        self.pivotLow.push(pivot(low, self.bar_index, self.swingLength, self.swingLength, "low", self.ties))
        self._green.push(bool(close[0] > open_[0] or close[0] > close[1]))
        self._red.push(bool(close[0] < open_[0] or close[0] < close[1]))
        self.bullFVG.push(bool(low[1] > high[3] and self._green[2] and low[1] < high[2] and low[2] < high[3]))
        self.bearFVG.push(bool(high[1] < low[3] and self._red[2] and high[1] > low[2] and high[2] > low[3]))
        ph, pl = self.pivotHigh[0], self.pivotLow[0]
        # calcAll() (L684-690); calcTrend is not ported (R16)
        swingH, swingL, reclaimLow, reclaimHigh, newH, newL = self.calcSwingHL.step(ph, pl, high[0], low[0], close[0])
        rtHighType, rtLowType, structBias = self.calcStructure.step(ph, pl, close[0])
        bullBreak, bearBreak, obNearDir, obNearDist, created, rejected = self.calcOrderBlock.step(self)
        signal = detect_fvg_signal(self)
        fvgNearDir, fvgNearDist = self.calcFVG.step(signal, low[0], high[0], close[0])
        return {
            "swing_h": swingH, "swing_l": swingL, "struct": structBias,
            "ob_dir": obNearDir, "ob_dist": obNearDist, "fvg_dir": fvgNearDir, "fvg_dist": fvgNearDist,
            "bull_break": bullBreak, "bear_break": bearBreak,
            "pivot_high": ph, "pivot_low": pl, "high_type": rtHighType, "low_type": rtLowType,
            "reclaim_low": reclaimLow, "reclaim_high": reclaimHigh,
            "new_ob": 0 if created is None else created.dir, "ob_rejected": rejected,
            "new_fvg": signal[0], "n_ob": len(self.calcOrderBlock.obs), "n_fvg": len(self.calcFVG.fvgs),
        }


_ROW_KEYS_FLOAT = ("swing_h", "swing_l", "ob_dist", "fvg_dist", "pivot_high", "pivot_low")
_ROW_KEYS_BOOL = ("bull_break", "bear_break", "reclaim_low", "reclaim_high")


def _bars(b, what: str) -> Tuple[List[int], List[int], List[float], List[float], List[float], List[float]]:
    """Plain lists of a bar object's t, tc, o, h, l, c; tc must increase strictly (the merge searches it)."""
    cols = []
    for k in ("t", "tc", "o", "h", "l", "c"):
        if not hasattr(b, k):
            raise ValueError(f"{what}: the bars have no '{k}'")
        cols.append(np.asarray(getattr(b, k)))
    n = len(cols[0])
    if any(len(a) != n for a in cols) or any(a.ndim != 1 for a in cols):
        raise ValueError(f"{what}: t, tc, o, h, l, c must be 1-D arrays of one length")
    t = [int(v) for v in cols[0]]
    tc = [int(v) for v in cols[1]]
    o, h, l, c = ([float(v) for v in a] for a in cols[2:])
    for k in range(1, n):
        if not tc[k] > tc[k - 1]:
            raise ValueError(f"{what}: tc must increase strictly (bar {k})")
    for k in range(n):
        if na(o[k]) or na(h[k]) or na(l[k]) or na(c[k]):
            raise ValueError(f"{what}: na price at bar {k}")
    return t, tc, o, h, l, c


def calc_all(bars, ties: str = "strict") -> Dict[str, np.ndarray]:
    """
    One row on its own bars: the outputs of ``Row.step`` for every bar, as arrays (floats NaN where Pine is na).
    ``swing_h`` / ``swing_l`` / ``struct`` / ``ob_dir`` / ``fvg_dir`` are what the bias reads; ``bull_break`` /
    ``bear_break`` the breaks of structure; ``new_ob`` / ``new_fvg`` the direction of the zone created / detected on
    the bar (an FVG may be mitigated on that same bar); ``ob_rejected`` a break whose zone overlapped.
    """
    _, _, o, h, l, c = _bars(bars, "calc_all")
    row = Row(ties)
    out: Dict[str, list] = {}
    for k in range(len(c)):
        r = row.step(o[k], h[k], l[k], c[k])
        for name, v in r.items():
            out.setdefault(name, []).append(v)
    if not out:
        names = ("swing_h", "swing_l", "struct", "ob_dir", "ob_dist", "fvg_dir", "fvg_dist", "bull_break",
                 "bear_break", "pivot_high", "pivot_low", "high_type", "low_type", "reclaim_low", "reclaim_high",
                 "new_ob", "ob_rejected", "new_fvg", "n_ob", "n_fvg")
        out = {name: [] for name in names}
    res: Dict[str, np.ndarray] = {}
    for name, v in out.items():
        if name in _ROW_KEYS_FLOAT:
            res[name] = np.asarray(v, np.float64)
        elif name in _ROW_KEYS_BOOL:
            res[name] = np.asarray(v, bool)
        elif name in ("n_ob", "n_fvg"):
            res[name] = np.asarray(v, np.int64)
        else:
            res[name] = np.asarray(v, np.int8)
    return res


# ───────────────────────────── the chart: merge and bias ─────────────────────────────

def active_rows(chart_tf: str) -> Tuple[str, ...]:
    """``tfActive(enabled, tf) => enabled and timeframe.in_seconds() <= timeframe.in_seconds(tf)`` (L692)."""
    if chart_tf not in CHARTS:
        raise ValueError(f"chart_tf: one of {CHARTS}, got {chart_tf!r}")
    return tuple(r for r in ROWS if ROW_SECONDS[chart_tf] <= ROW_SECONDS[r])


def max_score_of(chart_tf: str) -> int:
    """``maxScore`` (L1334-1339): the sum of weight x factorCount over the active rows."""
    m = 0
    for r in active_rows(chart_tf):
        if WEIGHT[r] > 0:
            m += WEIGHT[r] * FACTOR_COUNT
    return m


def dir_score(d) -> int:
    """``dirScore(dir) => dir > 0 ? 1 : dir < 0 ? -1 : 0`` (L703); na gives 0."""
    if na(d):
        return 0
    return 1 if d > 0 else (-1 if d < 0 else 0)


def swing_bias_dir(swingH: float, swingL: float, close: float, mintick: float) -> int:
    """``swingBiasDir(swingH, swingL)`` (L705-708) with the CHART's close and ``syminfo.mintick`` (R3, R4, R10)."""
    swingRange = pine_max(swingH - swingL, mintick)                                          # L706 (na if a swing is)
    swingPct = (close - swingL) / swingRange * 100                                           # L707
    if na(swingPct):
        return 0                                                                             # every comparison false
    if swingPct < 0:
        return -1
    if swingPct > 100:
        return 1
    if swingPct < 30:
        return 1
    if swingPct > 70:
        return -1
    return 0


def label_of(points: int, max_score: int) -> int:
    """
    The bias label (L1343-1344) as an int: +2 BULLISH, +1 LEAN BULL, 0 NEUTRAL, -1 LEAN BEAR, -2 BEARISH. Computed
    in integers (2p > m, 5p > m and mirrors) and checked against the script's float formula (R5).
    """
    p, m = int(points), int(max_score)
    if m <= 0:
        raise ValueError("maxScore == 0 is the script's 'N/A' (no active row), which the defaults cannot reach")
    if 2 * p > m:
        lab = 2
    elif 5 * p > m:
        lab = 1
    elif 2 * p < -m:
        lab = -2
    elif 5 * p < -m:
        lab = -1
    else:
        lab = 0
    biasPct = (p / m) * 100                                                                  # L1343
    lit = 2 if biasPct > 50 else 1 if biasPct > 20 else -2 if biasPct < -50 else -1 if biasPct < -20 else 0
    if lit != lab:
        raise AssertionError(f"integer label {lab} != float label {lit} at {p}/{m}")
    return lab


def _resolve_mintick(chart, mintick: Optional[float]) -> float:
    if mintick is not None:
        v = float(mintick)
    elif getattr(chart, "mintick", None) is not None:
        v = float(chart.mintick)
    elif getattr(chart, "symbol", None) in MINTICK:
        v = MINTICK[chart.symbol]
    else:
        raise ValueError("syminfo.mintick: pass mintick=, or chart bars with a 'mintick' attribute or a 'symbol' in "
                         f"{sorted(MINTICK)}")
    if not v > 0:
        raise ValueError(f"mintick must be > 0, got {v}")
    return v


def structure_dashboard(rows: Dict[str, object], chart_tf: str, model: str = "A", mintick: Optional[float] = None,
                        ties: str = "strict") -> Dict[str, np.ndarray]:
    """
    The dashboard's TREND BIAS per chart bar under model A (see the module docstring for the contract and readings).
    Each active row is computed on its own bars (``Row``), merged at the chart bar where ``tc_row <= tc_chart``,
    scored with the chart close, weighted and summed into the label.
    """
    if model != "A":
        raise ValueError(f"model {model!r}: port B ports model A only (model B is port A's, not compared)")
    act = active_rows(chart_tf)
    for r in act:
        if r not in rows:
            raise ValueError(f"rows: the active row {r!r} of a {chart_tf} chart is missing")
    chart = rows[chart_tf]
    tick = _resolve_mintick(chart, mintick)
    _, ch_tc, _, _, _, ch_c = _bars(chart, f"rows[{chart_tf!r}]")
    n = len(ch_tc)
    m = max_score_of(chart_tf)
    points = [0] * n
    out: Dict[str, np.ndarray] = {}
    per_row: Dict[str, Dict[str, list]] = {}
    for r in act:
        st = calc_all(rows[r], ties)
        _, tc_r, _, _, _, _ = _bars(rows[r], f"rows[{r!r}]")
        cols = {"s": [0] * n, "struct": [0] * n, "ob": [0] * n, "fvg": [0] * n, "swing": [0] * n}
        j = -1                                       # the row's last bar closed at the chart bar's close
        for i in range(n):
            while j + 1 < len(tc_r) and tc_r[j + 1] <= ch_tc[i]:
                j += 1
            if r == chart_tf and j != i:
                raise AssertionError("the chart row must be the chart bar itself")
            if j < 0:                                # before the row's first closed bar: na (R4)
                structBias = obNearDir = fvgNearDir = NA
                swingH = swingL = NA
            else:
                structBias = int(st["struct"][j])
                obNearDir = int(st["ob_dir"][j])
                fvgNearDir = int(st["fvg_dir"][j])
                swingH = float(st["swing_h"][j])
                swingL = float(st["swing_l"][j])
            f_struct = dir_score(structBias) if BIAS_USE["struct"] else 0                    # L712-713
            f_ob = dir_score(obNearDir) if BIAS_USE["ob"] else 0                             # L714-715
            f_fvg = dir_score(fvgNearDir) if BIAS_USE["fvg"] else 0                          # L716-717
            f_swing = swing_bias_dir(swingH, swingL, ch_c[i], tick) if BIAS_USE["swing"] else 0   # L720-721, L1330
            score = f_struct + f_ob + f_fvg + f_swing
            cols["s"][i] = score
            cols["struct"][i] = f_struct
            cols["ob"][i] = f_ob
            cols["fvg"][i] = f_fvg
            cols["swing"][i] = f_swing
            if WEIGHT[r] > 0:                                                                # L1338
                points[i] += score * WEIGHT[r]                                               # calcBiasForTf (L722)
        per_row[r] = cols
        if r == chart_tf:
            bull, bear = st["bull_break"], st["bear_break"]
    labels = [label_of(points[i], m) for i in range(n)]
    out["label"] = np.asarray(labels, np.int8)
    out["score"] = np.asarray(points, np.int64)
    out["max_score"] = np.full(n, m, np.int64)
    for r in act:
        cols = per_row[r]
        out[f"s_{r}"] = np.asarray(cols["s"], np.int64)
        for f in ("struct", "ob", "fvg", "swing"):
            out[f"{f}_{r}"] = np.asarray(cols[f], np.int8)
    bos = [0] * n
    trend = [0] * n
    side = 0
    for i in range(n):
        if bool(bull[i]) and bool(bear[i]):
            raise AssertionError("two breaks on one bar (R13 says this cannot happen)")
        if bool(bull[i]):
            bos[i] = 1
            side = 1
        elif bool(bear[i]):
            bos[i] = -1
            side = -1
        trend[i] = side
    out["bos"] = np.asarray(bos, np.int8)
    out["bos_trend"] = np.asarray(trend, np.int8)
    return out


# ───────────────────────────── weekly bars ─────────────────────────────

@dataclass(frozen=True, eq=False)
class WeeklyBars:
    """ISO weeks of day bars (``weekly_bars``). ``d0`` / ``d1``: the first and last day bar of each week."""
    symbol: Optional[str]
    tf: str
    t: np.ndarray           # the first day bar's open time
    tc: np.ndarray          # the last day bar's close time (a forming last week: the end of its ISO week)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    d0: np.ndarray
    d1: np.ndarray
    complete: np.ndarray    # False only for a last week the data end cuts before the end of its ISO week (``end_s``)

    def __len__(self) -> int:
        return int(len(self.t))


def iso_week_of(ts: int) -> Tuple[int, int]:
    """(ISO year, ISO week) of the UTC instant ``ts`` (s): the Monday-start week."""
    y, w, _ = datetime.fromtimestamp(int(ts), tz=timezone.utc).isocalendar()
    return int(y), int(w)


def iso_week_end(key: Tuple[int, int]) -> int:
    """The end of ISO week ``(year, week)``: the next Monday 00:00 UTC, in epoch seconds."""
    monday = datetime.fromisocalendar(int(key[0]), int(key[1]), 1).replace(tzinfo=timezone.utc)
    return int(monday.timestamp()) + 7 * 86400


def weekly_bars(day_bars, end_s: Optional[int] = None) -> WeeklyBars:
    """
    The weekly bars of the dashboard's W row (PREREG 2; R8): consecutive day bars whose last second (``tc - 1``) falls
    in the same ISO (Monday-start) week form one bar. Its open is the first day bar's open (and open time), its high /
    low the extremes of its day bars, its close the last day bar's close, and its ``tc`` the last day bar's ``tc``.
    With study 1's merged 1D bars this puts gold's Sunday stub (merged into Monday) into the new week, and a short
    Friday merged into the next Monday into the following week; BTC's weeks start on Monday 00:00 UTC.

    ``end_s`` (optional, added at the reconciliation with port A): the exclusive end, UTC s, of the data the day bars
    were built from. When it falls before the end of the last bar's ISO week (the next Monday 00:00 UTC), that week can
    still receive day bars: it is returned with ``complete`` False and its ``tc`` set to that Monday 00:00, so the merge
    of model A (``tc_row <= tc_chart``) never shows it as closed (PREREG 5: higher-timeframe values come from the last
    CLOSED bar). Without ``end_s`` every week counts as complete, which is right only for data that end at a week
    boundary, such as the study's bars before the hold-out (they end on Monday 2024-07-01 00:00 UTC).
    """
    t, tc, o, h, l, c = _bars(day_bars, "weekly_bars")
    groups: List[List[int]] = []
    keys: List[Tuple[int, int]] = []
    for k in range(len(tc)):
        key = iso_week_of(tc[k] - 1)
        if not keys or key != keys[-1]:
            if keys and not key > keys[-1]:
                raise AssertionError("ISO weeks must increase with tc")
            keys.append(key)
            groups.append([k, k])
        else:
            groups[-1][1] = k
    wt, wtc, wo, wh, wl, wc, d0, d1 = [], [], [], [], [], [], [], []
    for a, z in groups:
        wt.append(t[a])
        wtc.append(tc[z])
        wo.append(o[a])
        hi = h[a]
        lo = l[a]
        for k in range(a + 1, z + 1):
            hi = h[k] if h[k] > hi else hi
            lo = l[k] if l[k] < lo else lo
        wh.append(hi)
        wl.append(lo)
        wc.append(c[z])
        d0.append(a)
        d1.append(z)
    complete = [True] * len(groups)
    if end_s is not None and groups:
        week_end = iso_week_end(keys[-1])
        if int(end_s) < week_end:                    # the data stop inside the last week: it is still forming
            wtc[-1] = week_end
            complete[-1] = False
    return WeeklyBars(getattr(day_bars, "symbol", None), "1W", np.asarray(wt, np.int64), np.asarray(wtc, np.int64),
                      np.asarray(wo, np.float64), np.asarray(wh, np.float64), np.asarray(wl, np.float64),
                      np.asarray(wc, np.float64), np.asarray(d0, np.int64), np.asarray(d1, np.int64),
                      np.asarray(complete, bool))
