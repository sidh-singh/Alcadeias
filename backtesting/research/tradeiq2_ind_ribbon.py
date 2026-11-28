"""
Trend Target Ribbon (BOSWaves), port A: the ribbon's trend, its flips and the stop distance of the position a flip
opens, for every chart bar.

    from backtesting.research import tradeiq2_market as M2, tradeiq2_ind_ribbon as RIB
    mk = M2.load("BTCUSDm", end="2024-07-01")             # the study's bars (gold from 2016-01-03, BTC 2018-01-01)
    b = mk.tbars("4H")                                    # 1H, 4H and 1D: the timeframes of PREREG 6.1
    out = RIB.ribbon(b.o, b.h, b.l, b.c)                  # the script's defaults
    out["flip"]        # int8 per bar: +1 bull flip (the "Bull Trend" alert, L768-771), -1 bear flip, 0 neither
    out["trend"]       # int8: +1 / -1 from the first setup on, 0 before it
    out["risk_long"]   # price distance: the 1R of a long that a bull flip at this bar would open (intended stop)

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 2, 5, 6.1, 6.10, 7 and claims 1-3 of section 8);
the specification is the study's map of the script (``ribbon_patterns.md``, part A). The script is "Trend Target
Ribbon [BOSWaves]" (Pine v6, MPL-2.0, (c) BOSWaves). Line numbers (L...) are those of the owner's copy (L1-776); the
source itself is not in this repository. Port A (this module, the production port) and port B
(``tests/tradeiq2_oracle_ribbon.py``) were written independently from the source and the specification. About 60
of the script's lines compute anything (L14-38, 88-114, 120-128, 310-330, 419-422, 495-501, 620-631, 752-776); the
rest draws lines, boxes, labels and colours.

Reconciled with port B on 28 Nov 2026 (``tests/test_tradeiq2_ind_ribbon.py``; the porting notes are
``backtest_results/tradeiq_2027/porting/ribbon.md``): on the 1H, 4H and 1D bars of both symbols from the study's data
start to 2024-06-30, every key is equal bit for bit, and so on synthetic bars with random inputs inside the script's
input ranges. The one mismatch was this port's: the literal stop's ``ta.lowest`` / ``ta.highest`` gave a value when
it ran before ``bar_index`` ``stop_lookback - 1``, where the documented reading (PineTS) says na. It is fixed
(``_previous_calls``); it is reachable only with inputs that allow a flip before that bar, never with the defaults.

The contract (both ports)
-------------------------
``ribbon(o, h, l, c, alma_len=34, alma_offset=0.85, alma_sigma=6.0, dev_len=34, dev_mult=0.65, slope_len=3,
slope_min=0.08, atr_len=14, stop_lookback=12, min_stop_atr=0.75, max_stop_atr=3.0, edge_mult=0.55)`` returns a dict
with exactly the keys ``KEYS``, each an array of ``len(c)`` values, one per bar, oldest first:

=================== ======= ================================================================================
key                 dtype   value (the script's names; defaults shown)
=================== ======= ================================================================================
``alma``            float64 ``ta.alma(close, 34, 0.85, 6.0)`` (L88); first value at bar 33
``dev``             float64 ``ta.stdev(close, 34)``, the population one (L89); first value at bar 33
``atr``             float64 ``ta.atr(14)`` (L90); first value at bar 13
``slope``           float64 ``slopeScore = atr > 0 ? (alma - alma[3]) / atr : 0.0`` (L92): 0.0 on bars 0-12,
                            NaN on bars 13-35, values from bar 36
``conviction``      float64 ``clamp(|slope| * 2 + |close - alma| / atr * 0.35, 0, 1)`` (L120-123): 0.0 on bars
                            0-12, NaN on bars 13-35, values in [0, 1] from bar 36
``edge_up``         float64 ``alma + dev * 0.55``: the ribbon edge drawn in a bear trend (L127)
``edge_dn``         float64 ``alma - dev * 0.55``: the ribbon edge drawn in a bull trend (L126)
``bull_setup``      bool    ``slope > 0.08 and close > alma + dev * 0.65`` (L94, L97), strict
``bear_setup``      bool    ``slope < -0.08 and close < alma - dev * 0.65`` (L95, L98), strict
``trend``           int8    ``trend`` (L100-110): +1 / -1, 0 before the first setup; it never returns to 0
``flip``            int8    +1 on a ``bullFlip`` bar, -1 on a ``bearFlip`` bar, 0 otherwise (L102-114)
``risk_long``       float64 the INTENDED stop distance of a long opened at this bar's close, at every bar
``risk_short``      float64 the same for a short
``risk_long_lit``   float64 the TradingView-LITERAL stop distance, on bull-flip bars only, NaN elsewhere
``risk_short_lit``  float64 the same on bear-flip bars
=================== ======= ================================================================================

``o`` is checked (same length, finite) but not read: the script's only price source is the close (``src``, L14) and
``ta.atr`` reads high, low and close. The first-value bars above are for the defaults; in general alma from
``alma_len - 1``, dev from ``dev_len - 1``, the edges from both, atr and the risks from ``atr_len - 1``, the slope and
the conviction from ``alma_len - 1 + slope_len``, and 0.0 (not NaN) on the bars before the ATR's first value.

What the script computes on each bar, in its order
--------------------------------------------------
1. ``alma = ta.alma(src, almaLen, almaOffset, almaSigma)`` (L88), ``floor`` left at its default false (four arguments
   are passed). TradingView's reference: ``m = offset * (length - 1)`` = 0.85 * 33 = 28.05, NOT floored (floored it
   would be 28); ``s = length / sigma`` = 34 / 6; for i = 0 .. 33, ``weight = math.exp(-1 * math.pow(i - m, 2) /
   (2 * math.pow(s, 2)))``, ``norm += weight``, ``sum += src[length - i - 1] * weight``; ``sum / norm``. Weight i
   applies to ``close[33 - i]``: i = 33 is the current bar (0.68 of the peak weight) and the peak is 5 bars back
   (i = 28). On a linear ramp the line lags 6.6607021454 bars (reversed weights would lag 26.34, floored m 6.69).
   Computed here in that order: the weights with Python's ``math.exp`` / ``math.pow`` (C libm, scalar; numpy's
   vectorised exp can differ in the last bit), the sum over i ascending, then one division.
2. ``dev = ta.stdev(src, devLen)`` (L89), ``biased`` left at true: the population deviation. Study 1's verified
   ``tradeiq_ind.stdev`` (TradingView's ``pine_stdev`` order, deviations of at most 1e-10 counted as 0).
3. ``atr = ta.atr(atrLen)`` (L90): Wilder's RMA of the true range, seeded with the SMA of the first 14 true ranges;
   the true range of bar 0 is high - low. Study 1's verified ``tradeiq_ind.atr``.
4. ``slopeScore = atr > 0 ? (alma - alma[slopeLen]) / atr : 0.0`` (L92). ``alma[3]`` is the global series (computed
   on every bar), so it has no scope issue. While the ATR is na (bars 0-12) the test ``atr > 0`` is false and the
   slope is 0.0, not na.
5. ``upperConfirm = alma + dev * devMult``, ``lowerConfirm = alma - dev * devMult`` (L94-95); ``bullSetup =
   slopeScore > slopeMin and close > upperConfirm``, ``bearSetup = slopeScore < -slopeMin and close <
   lowerConfirm`` (L97-98). Both strict; a comparison with na is false. The two are mutually exclusive whenever
   ``slopeMin >= 0`` (its input minimum, L28), so the else-if order of L105-110 never matters; a negative
   ``slope_min`` is refused.
6. ``var int trend = 0`` (L100); ``if trend != 1 and bullSetup: trend := 1, bullFlip := true``; ``else if trend != -1
   and bearSetup: trend := -1, bearFlip := true`` (L105-110). Closed form used here (equal for exclusive setups):
   ``trend`` at bar t is the side of the most recent setup bar at or before t (0 before the first), and a flip is a
   setup bar whose side differs from the trend of the bar before. Nothing else writes ``trend``: a stopped-out
   position (L498-580) does not reset it, so after a stop the next flip is always to the other side, and flips
   alternate sides.
7. ``distanceScore = atr > 0 ? math.abs(close - alma) / atr : 0.0`` (L120); ``conviction = math.max(0.0,
   math.min(1.0, math.abs(slopeScore) * 2.0 + distanceScore * 0.35))`` (L122-123); math.min / math.max of na are na.
   It sets only the brightness of the ribbon and the candles (L136-137, L167-176).
8. ``ribbonEdge = bull ? alma - dev * 0.55 : bear ? alma + dev * 0.55 : alma`` (L125-128), display only; the plots
   hide alma, mid and edge on flip bars (L132-134). Both edges are returned on every bar, whatever the trend.

The stop of a flip's position (L310-330)
----------------------------------------
On a flip the script opens a position: ``entryPrice := close`` (L310), ``positionDir := bull ? 1 : -1`` (L312),

    structureStop = positionDir == 1 ? ta.lowest(low, stopLookback)[1] : ta.highest(high, stopLookback)[1]  L315-317
    rawRisk       = entryPrice - structureStop (long), structureStop - entryPrice (short)                  L319-321
    riskDist      = math.min(math.max(nz(rawRisk, atr * 0.75), atr * 0.75), atr * 3.0)                     L323-328
    stopPrice     = entryPrice - positionDir * riskDist                                                  L330

and four targets ``entryPrice + positionDir * riskDist * k``, k = 1..4 (L419-422), which close nothing (they get a
check mark, L626-631). ``riskDist`` is 1R. The arrays here are distances in price units, measured from the close.

* INTENDED (``risk_long`` / ``risk_short``; PREREG 6.1, every eligible RIB row): the input's tooltip (L33-34,
  "bars back used to locate swing structure") and the video ("a stop below the last swing low") describe
  ``ta.lowest(low, 12)[1]`` evaluated on every bar: the lowest low of the 12 bars BEFORE the bar (t-12 .. t-1; the
  highest high for a short). Computed at every bar as if that bar were a flip of that side, the per-bar stop distance
  the harness takes (spec A5): ``raw = close - min(low[t-12 .. t-1])``, ``risk = min(max(raw, 0.75 atr), 3 atr)``; a
  missing raw (t < 12) becomes 0.75 atr; NaN while the ATR is na. With the defaults raw exists from bar 12 and the ATR
  from bar 13, so the missing-raw branch only shows when ``stop_lookback >= atr_len``.
* LITERAL (``risk_long_lit`` / ``risk_short_lit``; RIB-LIT, a sensitivity row, not eligible): what TradingView
  computes. L315-317 sit inside ``if flip`` (L281) and inside a ternary, which runs only its taken branch (hence
  Pine's warning to call such functions on every bar), so ``ta.lowest`` runs only on bull-flip bars and
  ``ta.highest`` only on bear-flip bars. A call in a local scope stores only the values of the bars where it runs
  (TradingView's CW10003 page and "Time series in scopes": ``ta.sma`` inside an ``if`` "averages the last 20 executed
  values"), so each call site keeps its own buffer of the lows (highs) it was called with, and ``[1]`` is that call's
  result at its PREVIOUS execution ("reaches back to the last execution"). The k-th bull flip's structure stop is
  therefore the lowest of the lows of the previous up to 12 bull-flip bars, and the first bull flip's is na, so its
  risk is 0.75 ATR. The call's window rule is PineTS's account of TradingView: na while the chart's bar_index is
  below ``stop_lookback - 1`` (11), from that bar on the extreme of the values it holds even when it holds fewer than
  12. With the defaults every flip is at bar 36 or later, so only the second half applies; an execution before that
  bar (possible only with other inputs) has an na result, and the next execution's ``[1]`` is then na (0.75 ATR).
  Shorts mirror this with the highs of the bear-flip bars. NaN on every other bar. Unlike every other output it depends on where
  the bars start (the first flips of each side).

What is known when (no look-ahead)
----------------------------------
Every value of bar t uses bars 0 .. t only and is known at the bar's close: the ALMA and the deviation read the closes
t-33 .. t, the ATR the bars up to t, the slope ``alma[t-3]``, the intended risk the lows / highs of bars t-12 .. t-1
and the close and ATR of t, the literal risk the lows / highs of earlier flip bars of the same side. A flip is final at
its bar's close: no ``request.security``, no ``barstate`` branch, no pivots, no ``varip`` (on TradingView's realtime
bar a flip can appear and vanish inside the bar; on closed bars it never changes). Removing the bars after t changes
nothing up to t (tested). The trend has no long memory: from the first setup on it is a function of the setups only.

Readings where the source or the platform leaves a choice (logged for PORTING.md)
---------------------------------------------------------------------------------
The effects below count flips (or stops) of the Development decision bars (2019-2022) of the 1H / 4H / 1D bars of
both symbols that the other reading does not reproduce: counts only, no profit or loss. The study's bars start gold
on 2016-01-03 (``tradeiq2_market``), study 1's on 2017-01-03; the counts are the same on both but where stated.

* The stop's scope (L315-317): both readings are returned; the plan pre-registers the intended one (PREREG 6.1) and
  runs the literal one as RIB-LIT. They agree on 34-47 % of the flips. No reading of the stop changes a flip.
* Inside the literal reading (each changes stops, never a flip):
  - a local ``ta.lowest`` with fewer than 12 buffered values returns the extreme of what it has (the contract;
    PineTS's account of TradingView). Na until 12 values would give 0.75 ATR to the first 12 flips of each side: in
    2019-2022 that moves no 1H / 4H stop, 8 of BTC's 49 1D stops, and none of gold's 34 1D stops on the study's
    bars (4 on study 1's, which have fewer flips before 2019);
  - the call buffers the values it is called with; reading the chart's last 12 bars at each call instead changes
    35-45 % of the stops; evaluating both branches of the ternary on every flip changes 17-25 %; ``[1]`` as the
    previous BAR (na unless the call ran there) would make every literal stop 0.75 ATR (78-87 % change);
  - the bars start at the data start given. Any gold start from 2016-01 to 2018-01 gives the same 2019-2022 stops
    (to 1e-9 relative; the ATR's seed leaves differences below that), a start in 2018-07 changes 4 of gold's 34 1D
    stops; a BTC start 3 or 6 months after 2018-01-01 changes 1 or 3 of its 49 1D stops; none on 1H / 4H.
    TradingView's own chart start is unknown.
* ``ta.alma``'s ``floor`` (default false: m = 28.05; floored m = 28 loses 2-6 % of the flips per series) and its
  weight orientation (weight i on ``close[33 - i]``, TradingView's reference; reversed weights lose nearly all);
  ``ta.stdev``'s ``biased`` (default true: population; the sample deviation loses 0-2 %). Documented defaults, listed
  because a wrong choice moves flips.
* ``ta.atr``'s seed: the SMA of the first 14 true ranges, the bar-0 true range high - low (``pine_rma`` /
  ``pine_atr``; PREREG 5). It decays as (13/14)^n: seeded with the first true range instead, the ATR is the same from
  2019 to the last bit on five of the six series (3e-12 relative on BTC 1D) and no flip moves.
* The slope and the distance score are 0.0, not na, while the ATR is na (``atr > 0`` is false): warm-up bars only,
  where no setup is possible (the ALMA is na until bar 33).
* Strict thresholds (L97-98), as written. The closest margins on the study's bars to 2024-06-30 (|slope -+ 0.08| >=
  1e-5 where the band holds, |close - band| >= 1.8e-6 ATR where the slope holds) are far above rounding, so the order
  of the float operations cannot move a setup.
* The source is the bid close of the study's bars (UTC boundaries, a short UTC day merged into the next; PREREG 2),
  not TradingView's own bars of the same symbol: flips can differ from a TradingView chart, most on 4H and 1D, whose
  bar boundaries may differ.
Everything else follows the source literally; nothing is tuned (every default is the script's).
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from . import tradeiq_ind as I

__all__ = ["KEYS", "DEFAULTS", "alma", "lowest", "highest", "ribbon"]

NAN = math.nan

KEYS = ("alma", "dev", "atr", "slope", "conviction", "edge_up", "edge_dn", "bull_setup", "bear_setup", "trend", "flip",
        "risk_long", "risk_short", "risk_long_lit", "risk_short_lit")

DEFAULTS: Dict[str, float] = {      # the script's inputs (line of each input.*)
    "alma_len": 34,                 # L16 "ALMA Length"
    "alma_offset": 0.85,            # L18 "ALMA Offset"
    "alma_sigma": 6.0,              # L20 "ALMA Sigma"
    "dev_len": 34,                  # L22 "Deviation Length"
    "dev_mult": 0.65,               # L24 "Trend Confirmation"
    "slope_len": 3,                 # L26 "Slope Length"
    "slope_min": 0.08,              # L28 "Minimum Slope"
    "atr_len": 14,                  # L30 "ATR Length"
    "stop_lookback": 12,            # L33 "Stop Structure Lookback"
    "min_stop_atr": 0.75,           # L35 "Minimum Stop ATR"
    "max_stop_atr": 3.0,            # L37 "Maximum Stop ATR"
    "edge_mult": 0.55,              # L126-127: the ribbon edge's constant (not an input)
}


# ───────────────────────────── input checks ─────────────────────────────

def _series(x, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)              # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    return a


def _int(n, name: str) -> int:
    """A Pine length / offset argument: an integer >= 1 (an integral float is accepted)."""
    if isinstance(n, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {n!r}")
    f = float(n)
    if not (f >= 1.0 and f.is_integer()):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    return int(f)


def _num(x, name: str, lo: float = -math.inf) -> float:
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {x!r}")
    f = float(x)
    if not (math.isfinite(f) and f >= lo):
        raise ValueError(f"{name}: a finite number >= {lo} is expected, got {x!r}")
    return f


# ───────────────────────────── Pine primitives not in tradeiq_ind ─────────────────────────────

def alma(x, length: int = 34, offset: float = 0.85, sigma: float = 6.0, floor: bool = False) -> np.ndarray:
    """
    ``ta.alma(x, length, offset, sigma, floor)`` as TradingView's reference ``pine_alma``:

        m = floor ? math.floor(offset * (length - 1)) : offset * (length - 1)
        s = length / sigma
        for i = 0 to length - 1
            weight = math.exp(-1 * math.pow(i - m, 2) / (2 * math.pow(s, 2)))
            norm := norm + weight
            sum := sum + x[length - i - 1] * weight
        sum / norm

    Weight i multiplies ``x[length - 1 - i]`` (i = length - 1 is the current bar). Same operations in the same order:
    the weights and their norm in Python floats (C libm ``exp`` / ``pow``), then for each i ascending one multiply and
    one add over all bars at once, then one division. na until ``length`` values exist; an na inside the window gives
    na (arithmetic with na), as the reference does.
    """
    a = _series(x, "x")
    n = _int(length, "length")
    off = _num(offset, "offset")
    sg = _num(sigma, "sigma")
    if not sg > 0.0:
        raise ValueError(f"sigma: a positive number is expected, got {sigma!r}")
    m = float(math.floor(off * (n - 1))) if floor else off * (n - 1)
    s = n / sg
    w = [math.exp(-1 * math.pow(i - m, 2) / (2 * math.pow(s, 2))) for i in range(n)]
    norm = 0.0
    for wi in w:
        norm = norm + wi
    out = np.full(len(a), NAN)
    k = len(a) - n + 1                             # bars with a full window: n - 1 .. len - 1
    if k > 0:
        acc = np.zeros(k)
        for i in range(n):                         # x[length - 1 - i] of bar t = a[t - (n - 1) + i]
            acc = acc + a[i:i + k] * w[i]
        out[n - 1:] = acc / norm
    return out


def _extreme(x, length, name: str, low: bool) -> np.ndarray:
    a = _series(x, name)
    n = _int(length, "length")
    out = np.full(len(a), NAN)
    if len(a) >= n:
        win = sliding_window_view(a, n)
        out[n - 1:] = win.min(axis=1) if low else win.max(axis=1)
    return out


def lowest(x, length) -> np.ndarray:
    """``ta.lowest(x, length)`` called on every bar: the lowest of the last ``length`` values, this bar included; na
    until ``length`` values exist (for a call on every bar this is also TradingView's newer "from bar_index
    length - 1" rule). The series must not contain na (bars never do; NaN would propagate through ``min``)."""
    return _extreme(x, length, "x", True)


def highest(x, length) -> np.ndarray:
    """``ta.highest(x, length)`` called on every bar: the highest of the last ``length`` values (see ``lowest``)."""
    return _extreme(x, length, "x", False)


def _previous_calls(values: np.ndarray, length: int, low: bool, bars=None) -> np.ndarray:
    """
    ``ta.lowest(v, length)[1]`` (``low``) or ``ta.highest(v, length)[1]`` for a call that runs only on some bars, at
    each of its executions j = 0, 1, ...: the call's buffer holds the values it was called with; its result at
    execution i is na while the chart's ``bar_index`` (``bars[i]``) is below ``length - 1``, otherwise the extreme of
    the last ``length`` values it holds (fewer while fewer exist: PineTS's account of TradingView, the reading both
    ports document); ``[1]`` is the result of execution j - 1. So at execution j: the extreme of
    ``values[max(0, j - length) : j]`` when ``bars[j - 1] >= length - 1``, else na; na at the first execution.
    ``bars=None`` means every execution is at ``bar_index >= length - 1`` (as every flip is with the script's defaults:
    the first flip is at bar 36 or later, the window rule needs bar 11).

    Reconciliation (``tests/test_tradeiq2_ind_ribbon.py``): this port first ignored the ``bar_index`` part of the rule.
    Port B applies it. It matters only for inputs where a flip can come before bar ``stop_lookback - 1`` (e.g.
    ``alma_len=5, stop_lookback=50``), never with the defaults.
    """
    k = len(values)
    out = np.full(k, NAN)
    if k > 1:
        pad = np.concatenate((np.full(length, np.inf if low else -np.inf), values))
        win = sliding_window_view(pad, length)[:k]          # window j = values[j - length : j], padded
        ext = win.min(axis=1) if low else win.max(axis=1)
        if bars is None:
            out[1:] = ext[1:]
        else:
            ready = np.asarray(bars, np.int64)[:-1] >= length - 1     # execution j - 1 had a result
            out[1:] = np.where(ready, ext[1:], NAN)
    return out


def _risk(raw: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """``math.min(math.max(nz(raw, lo), lo), hi)`` (L326-328): na wherever ``lo`` or ``hi`` is na."""
    with np.errstate(invalid="ignore"):
        return np.minimum(np.maximum(np.where(np.isnan(raw), lo, raw), lo), hi)


def _trend(bull: np.ndarray, bear: np.ndarray):
    """L100-110 for mutually exclusive setups: ``trend`` = the side of the most recent setup (0 before the first), a
    flip = a setup whose side differs from the previous bar's trend (the ``var`` starts at 0 before bar 0)."""
    n = len(bull)
    side = np.zeros(n, np.int8)
    side[bull] = 1
    side[bear] = -1
    last = np.maximum.accumulate(np.where(side != 0, np.arange(n), -1)) if n else np.zeros(0, np.int64)
    trend = np.where(last >= 0, side[np.maximum(last, 0)], 0).astype(np.int8)
    before = np.zeros(n, np.int8)
    before[1:] = trend[:-1]
    flip = np.where((side != 0) & (side != before), side, 0).astype(np.int8)
    return trend, flip


# ───────────────────────────── the ribbon ─────────────────────────────

def ribbon(o, h, l, c, alma_len=34, alma_offset=0.85, alma_sigma=6.0, dev_len=34, dev_mult=0.65, slope_len=3,
           slope_min=0.08, atr_len=14, stop_lookback=12, min_stop_atr=0.75, max_stop_atr=3.0,
           edge_mult=0.55) -> Dict[str, np.ndarray]:
    """
    The Trend Target Ribbon on one chart's bars (bid OHLC, oldest first, no na), with the script's defaults: a dict
    with the keys ``KEYS`` (the module docstring has each one's definition, first value and source lines).

    The trend, the setups and the flips depend only on the closes, highs and lows up to each bar; the intended risks
    are computed at every bar; the literal risks only on the flip bars of their side. Inputs are copied, never
    modified. Lengths are integers >= 1; ``slope_min`` must be >= 0 (its input minimum, L28), which keeps the two
    setups exclusive.
    """
    o, h, l, c = (_series(x, k) for x, k in ((o, "o"), (h, "h"), (l, "l"), (c, "c")))
    n = len(c)
    if not len(o) == len(h) == len(l) == n:
        raise ValueError(f"o, h, l, c: series of equal length are expected, got {len(o)}, {len(h)}, {len(l)}, {n}")
    for x, k in ((o, "o"), (h, "h"), (l, "l"), (c, "c")):
        if not np.isfinite(x).all():
            raise ValueError(f"{k}: na or an infinite value at bar {int(np.argmax(~np.isfinite(x)))}; bars are "
                             "expected to be complete")
    alma_len, dev_len, slope_len, atr_len, stop_lookback = (
        _int(v, k) for v, k in ((alma_len, "alma_len"), (dev_len, "dev_len"), (slope_len, "slope_len"),
                                (atr_len, "atr_len"), (stop_lookback, "stop_lookback")))
    dev_mult, min_stop_atr, max_stop_atr, edge_mult = (
        _num(v, k) for v, k in ((dev_mult, "dev_mult"), (min_stop_atr, "min_stop_atr"),
                                (max_stop_atr, "max_stop_atr"), (edge_mult, "edge_mult")))
    slope_min = _num(slope_min, "slope_min", 0.0)

    al = alma(c, alma_len, alma_offset, alma_sigma)                        # L88
    dev = I.stdev(c, dev_len)                                              # L89
    atr = I.atr(h, l, c, atr_len)                                          # L90
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = atr > 0.0                                                    # na > 0 is false
        slope = np.where(pos, (al - I.hist(al, slope_len)) / atr, 0.0)    # L92
        upper = al + dev * dev_mult                                        # L94
        lower = al - dev * dev_mult                                        # L95
        bull = (slope > slope_min) & (c > upper)                           # L97
        bear = (slope < -slope_min) & (c < lower)                          # L98
        distance = np.where(pos, np.abs(c - al) / atr, 0.0)               # L120
        conviction = np.maximum(0.0, np.minimum(1.0, np.abs(slope) * 2.0 + distance * 0.35))   # L122-123
        edge_up = al + dev * edge_mult                                     # L127 (bear trend)
        edge_dn = al - dev * edge_mult                                     # L126 (bull trend)
    trend, flip = _trend(bull, bear)                                       # L100-114

    lo_risk = atr * min_stop_atr                                           # L323
    hi_risk = atr * max_stop_atr                                           # L324
    # intended: ta.lowest(low, 12)[1] / ta.highest(high, 12)[1] as global series, at every bar (L315-321)
    risk_long = _risk(c - I.hist(lowest(l, stop_lookback), 1), lo_risk, hi_risk)
    risk_short = _risk(I.hist(highest(h, stop_lookback), 1) - c, lo_risk, hi_risk)
    # literal: one buffer per call site, fed on the flip bars of its side only; [1] = the previous execution's result
    risk_long_lit = np.full(n, NAN)
    risk_short_lit = np.full(n, NAN)
    fb = np.flatnonzero(flip == 1)
    risk_long_lit[fb] = _risk(c[fb] - _previous_calls(l[fb], stop_lookback, True, fb), lo_risk[fb], hi_risk[fb])
    fs = np.flatnonzero(flip == -1)
    risk_short_lit[fs] = _risk(_previous_calls(h[fs], stop_lookback, False, fs) - c[fs], lo_risk[fs], hi_risk[fs])

    return {
        "alma": al, "dev": dev, "atr": atr, "slope": slope, "conviction": conviction,
        "edge_up": edge_up, "edge_dn": edge_dn,
        "bull_setup": bull, "bear_setup": bear, "trend": trend, "flip": flip,
        "risk_long": risk_long, "risk_short": risk_short,
        "risk_long_lit": risk_long_lit, "risk_short_lit": risk_short_lit,
    }
