"""
The oracle of ``backtesting/research/tradeiq2_ind_ribbon.py``: PORT B of BOSWaves' "Trend Target Ribbon" (TradeIQ
study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.1).

What this is
------------
A literal, bar-by-bar transcription of the script's Pine v6 logic in plain Python (no numpy in the bar loop, no
numba), written to be obviously correct rather than fast. It was written from the Pine source and the study's
specification only, without seeing port A. Line numbers ``L..`` refer to the 775-line copy "BOSWaves Trend Target
Ribbon.txt" of the study's source folder (third-party code: it is cited, never copied). About 60 of the 775 lines
compute something; the rest draw lines, boxes, labels and colours.

How the transcription works: Pine runs the script once per bar, oldest bar first. Every Pine call site that keeps
state across bars (``ta.alma``, ``ta.stdev``, ``ta.atr`` and the ``ta.sma`` / ``ta.rma`` inside them, ``ta.lowest``,
``ta.highest``) is one object here, called once per EXECUTION of that call site, exactly where the script calls it.
A call site inside an ``if`` or a ternary branch is called only when that branch runs, so it sees only the values of
its own executions, as TradingView does ("a local call stores values only for the bars where it runs"; ``x[1]`` of
such a call "reaches back to the last execution": TradingView's compiler warning CW10003 and its execution-model
page). The arithmetic of each built-in follows the "same on pine" code of TradingView's reference manual, in its
order of operations.

Pine value rules used throughout: ``na`` is NaN; arithmetic with na gives na; ``math.max`` / ``math.min`` /
``math.abs`` of na give na (``pmax``, ``pmin``); a comparison with na is false, so ``atr > 0 ? a : b`` takes ``b``
while the ATR is na; ``nz(x, y)`` replaces na by y.

The contract (identical in both ports, compared key by key)
-----------------------------------------------------------
``ribbon(o, h, l, c, alma_len=34, alma_offset=0.85, alma_sigma=6.0, dev_len=34, dev_mult=0.65, slope_len=3,
slope_min=0.08, atr_len=14, stop_lookback=12, min_stop_atr=0.75, max_stop_atr=3.0, edge_mult=0.55)`` returns a dict
of arrays of len(bars), bar 0 = the first bar given:

==================  =======  ==========================================================================================
key                 dtype    value at bar t (first value with the defaults; bars counted from 0)
==================  =======  ==========================================================================================
alma                float64  ``ta.alma(close, 34, 0.85, 6.0)``, floor = false (L88). NaN before bar 33
dev                 float64  ``ta.stdev(close, 34)``, population (L89). NaN before bar 33
atr                 float64  ``ta.atr(14)``: Wilder RMA of the true range, seeded with an SMA (L90). NaN before bar 13
slope               float64  ``atr > 0 ? (alma - alma[3]) / atr : 0.0`` (L92): 0.0 on bars 0-12 (the ATR is na, so
                             ``atr > 0`` is false), NaN on bars 13-35 (``alma[3]`` is na), a value from bar 36
conviction          float64  ``max(0, min(1, |slope| * 2 + |close - alma| / atr * 0.35))`` (L120-123, the distance
                             term is also 0.0 while the ATR is na): 0.0 on bars 0-12, NaN on 13-35, a value from 36
edge_up, edge_dn    float64  ``alma + dev * 0.55`` (the bear ribbon's edge, L127) and ``alma - dev * 0.55`` (the bull
                             ribbon's edge, L126); display only. NaN before bar 33
bull_setup          bool     ``slope > 0.08 and close > alma + dev * 0.65`` (L94, L97), strict; false while na
bear_setup          bool     ``slope < -0.08 and close < alma - dev * 0.65`` (L95, L98), strict; false while na
trend               int8     ``var int trend`` (L100-110): 0 before the first setup, then +1 / -1; never 0 again
flip                int8     +1 on a bull flip bar (``bullFlip``), -1 on a bear flip bar (``bearFlip``), else 0
risk_long           float64  the INTENDED stop distance at every bar, as if the bar were a bull flip (the reading
                             PREREG 6.1 registers): raw = close - min(low[t-12 .. t-1]); risk = min(max(nz(raw,
                             0.75 atr), 0.75 atr), 3 atr) (L319-328). A missing raw (t < 12) becomes 0.75 atr; NaN
                             while the ATR is na (bars 0-12)
risk_short          float64  the same for a bear flip: raw = max(high[t-12 .. t-1]) - close
risk_long_lit       float64  the stop distance TradingView LITERALLY computes (RIB-LIT): on bull flip bars only, NaN
                             elsewhere; see "The stop" below
risk_short_lit      float64  the same on bear flip bars (``ta.highest`` of the highs of earlier bear-flip bars)
==================  =======  ==========================================================================================

The inputs are the chart's bars, oldest first: the bid OHLC (``src = close``, L14). ``o`` is not read by the script
(nothing uses ``open``); it is accepted so that both ports share one signature. Every length is an integer >= 1.

What is known when (no look-ahead)
----------------------------------
Every value at bar t is computed from bars 0 .. t only, so it is known at bar t's close and never changes afterwards:
no ``request.security``, no ``barstate``, no pivots, no ``varip`` (on the realtime bar TradingView recomputes on
every tick and a flip can appear and vanish before the close; on closed bars, which is all we use, it is final). The
flip is decided at the flip bar's close and the script's entry is that close (L310). ``risk_*`` at bar t reads
close[t], atr[t] and the lows / highs of bars t-12 .. t-1; ``risk_*_lit`` reads close[t], atr[t] and the lows / highs
of earlier flip bars. ``tests/test_tradeiq2_ind_ribbon_b.py`` checks this by truncation.

The Pine readings (each one is a choice; the alternatives are named)
--------------------------------------------------------------------
1. ``ta.alma`` (L88; TradingView's reference ``pine_alma``): m = offset * (length - 1) = 0.85 * 33 = 28.05, NOT
   floored (the script passes no ``floor`` argument and it defaults to false; floored, m = 28); s = length / sigma =
   34 / 6; weight_i = exp(-1 * (i - m)^2 / (2 * s^2)), i = 0 .. 33, applied to ``series[length - 1 - i]``: i = 33 is
   the current bar (0.683 of the peak weight), the peak is 4.95 bars back, and the lag on a linear ramp is
   6.6607021454 bars (reversed weights would give 26.34). ``norm`` and ``sum`` are accumulated in the reference's
   order, i = 0 (the oldest bar) first, and the result is sum / norm. The weights depend only on i, m and s, so they
   are computed once per call site (the reference recomputes them on every call with the same result). na until the
   call has 34 values (``series[33]`` is na before that).
2. ``ta.stdev`` (L89; reference ``pine_stdev``): biased = true by default, i.e. the POPULATION deviation (divide by
   34, not 33). avg = ``ta.sma(src, 34)`` with the reference ``pine_sma`` order (sum of x[i] / 34, i = 0 the newest
   first); for i = 0 .. 33 the deviation ``SUM(src[i], -avg)`` is 0 when its magnitude is at most 1e-10; the squares
   are added newest first; sqrt(sum / 34). The reference's ``SUM`` also returns 15 for some small deviations, a
   documentation slip that study 1 did not copy (its PORTING.md, item 7); it is not copied here either.
3. ``ta.atr`` (L90; reference ``pine_atr`` and ``pine_rma``): the true range of bar 0 is high - low (``na(high[1])``),
   later max(max(high - low, |high - close[1]|), |low - close[1]|); ``sum := na(sum[1]) ? ta.sma(tr, 14) : alpha * tr
   + (1 - alpha) * nz(sum[1])`` with alpha = 1 / 14. The ``ta.sma`` sits in a ternary branch, so it runs only while
   ``sum[1]`` is na (bars 0-13), which are exactly the 14 values a call on every bar would see: the seed is the plain
   mean of the first 14 true ranges, on bar 13.
4. ``slopeScore`` (L92) and ``distanceScore`` (L120) are 0.0, not na, while the ATR is na (the comparison ``atr > 0``
   with na is false). They are na where the ATR exists but ``alma`` or ``alma[3]`` does not. ``alma[3]`` is the
   global series ``alma`` three bars back (no scope issue).
5. The setups (L97-98) are strict inequalities and false whenever a term is na. The trend (L100-110) is a ``var int``
   starting at 0; ``if trend != 1 and bullSetup`` is tested before ``else if trend != -1 and bearSetup`` (with the
   inputs' ranges the two setups exclude each other, so the order cannot matter there). Closed form: the trend at bar
   t is the side of the most recent setup bar <= t; a flip is the first setup bar of the other side; nothing ever
   sets the trend back to 0 (not a stop, not anything).
6. The stop (L315-328). ``structureStop = positionDir == 1 ? ta.lowest(low, stopLookback)[1] : ta.highest(high,
   stopLookback)[1]`` is inside ``if flip`` (L281) AND inside a ternary, so on TradingView:

   * LITERAL (``risk_*_lit``): ``ta.lowest`` runs only on bull flips and ``ta.highest`` only on bear flips. Each buffers
     only the values of its own executions, and ``[1]`` is the result of its previous execution. So the k-th bull
     flip's structure low is the minimum of the lows of the bull-flip bars k-12 .. k-1 (the previous up to 12 bull
     flips), and the first bull flip of the history has none: ``nz`` gives 0.75 ATR. Bear flips mirror this with the
     highs of earlier bear-flip bars. The values also depend on where the chart's history starts (here: the first
     bar given). Window rule: a call returns the min (max) of the last ``length`` non-na values it has seen, from
     bar_index length - 1 on, even with fewer values (PineTS's ``ta.lowest`` / ``ta.highest``, which says it follows
     TradingView; this cannot be checked without TradingView). Alternative, kept only to be measured
     (``_ribbon_vm(lit_full=True)``): na until the call has seen ``length`` values, which floors the first 12 flips of
     each side at 0.75 ATR. A third reading, ``[1]`` as the call's value on the previous BAR, would make the structure
     level na on every flip (one side never flips on two bars in a row), i.e. 0.75 ATR always.
   * INTENDED (``risk_*``; the script's tooltip at L34, "bars back used to locate swing structure", and the video's
     "a stop below the last swing low"; registered in PREREG 6.1): the same expression evaluated on every bar, i.e.
     min(low[t-12 .. t-1]) for a long and max(high[t-12 .. t-1]) for a short, the 12 bars before the flip bar (na
     before bar 12).

   Both: rawRisk = close - structureStop (long) or structureStop - close (short), with entryPrice := close (L310);
   riskDist = math.min(math.max(nz(rawRisk, atr * 0.75), atr * 0.75), atr * 3.0) (L323-328); a negative raw risk
   (the close beyond the structure level) also becomes 0.75 ATR. The risk is a DISTANCE from the flip bar's close;
   the script's absolute stop is close - dir * riskDist (L330). PREREG 6.1 sets the stop riskDist from the fill.
7. Display-only parts are not ported, except the ribbon edges (``edge_up`` / ``edge_dn``, L125-128, for a possible
   "close back through the edge" exit) and the conviction (L120-123, for a possible conviction floor).

What the readings change on our bars
------------------------------------
Measured on 28 Nov 2026 with this file on study 1's 1H / 4H / 1D bars of both symbols, from the data start to
2024-06-30 (indicator values and counts only; no rule was run). "2019-2022" means bars that open on or after
2019-01-01 and close by 2023-01-01.

* Flips in 2019-2022 (bull / bear): gold 1H 429 / 429, 4H 124 / 124, 1D 17 / 17; BTC 1H 636 / 636, 4H 161 / 161,
  1D 24 / 25. The intended stop sits at the 3-ATR cap on 44-62% of them and never at the floor; the literal one at
  the cap on 71-78% and at the floor on 13-22%; the two are equal on 34-47%.
* Of the readings, only 1 and 2 can move a flip: a floored m would change the flip value on 2-52 bars per series in
  2019-2022, a sample stdev on 0-32. The reference's "15" slip would change 25 deviation values on gold 1H and 3 on
  4H, and move one gold 1H flip by one bar on 2018-09-25 (nothing from 2019). The 1e-10 zeroing never fires on real
  bars (the smallest 34-bar deviation is 0.70 USD).
* The literal stop's alternatives touch only the first 12 flips of each side: with ``lit_full`` the literal stop of 4
  (gold 1D) and 8 (BTC 1D) flips in 2019-2022 changes, and none on 1H or 4H. The "previous bar" reading of ``[1]``
  would change it on 78-87% of the flips of 2019-2022.
* Ties: from bar 36 on, no series comes closer to a threshold than |slope -+ 0.08| = 1.1e-5 (gold 1D), or |close -
  band| = 1.2e-8 of the price (BTC 1H; in dollars the closest is 2.5e-5 USD on gold 1H). That is at least a million
  times the rounding a different order of summation can produce, so the two ports' arithmetic cannot change a setup.

Outside the contract
--------------------
``script_positions`` transcribes the script's own position bookkeeping (L180-187, L215-277, L281-330, L419-422,
L495-501, L580, L620-631): the entry at the flip bar's close, the stop checked from the bar AFTER the entry bar, the
freeze of the old position on a flip bar (it runs before, and instead of, a stop check), the target check marks
(which also run on the entry bar, on the part of the bar before the entry close), and the absence of any reset
after a stop. It is what the chart draws; the study's harness executes on M1 bars instead. It exists for the trap
tests and as a reference for the harness, and is not compared between the ports.

``_ribbon_vm`` is the bar loop itself; its keyword arguments ``floor``, ``biased`` and ``lit_full`` select the
alternative readings above, only to measure them. ``ribbon`` is ``_ribbon_vm`` with the script's readings.

Reconciliation with port A (28 Nov 2026)
----------------------------------------
``tests/test_tradeiq2_ind_ribbon.py`` runs both ports on the study's 1H / 4H / 1D bars of both symbols (gold from
2016-01-03, BTC from 2018-01-01, to 2024-06-30) and on synthetic bars with random inputs inside the script's input
ranges: every key is equal bit for bit. The arithmetic needed no change (both follow the reference code's order).
The one mismatch was port A's, and this file was right: ``Extreme``'s na while bar_index < length - 1 also holds for
the literal call sites, so a flip before bar ``stop_lookback - 1`` (other inputs only) leaves na for the next flip's
``[1]``. Port A ignored that part of the rule; it now applies it. Notes: ``backtest_results/tradeiq_2027/porting/
ribbon.md``.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

__all__ = [
    "KEYS", "NAN", "is_na", "nz", "pmax", "pmin",
    "Sma", "Stdev", "Rma", "Atr", "Alma", "Extreme",
    "ribbon", "script_positions",
]

NAN = float("nan")

KEYS = ("alma", "dev", "atr", "slope", "conviction", "edge_up", "edge_dn", "bull_setup", "bear_setup", "trend",
        "flip", "risk_long", "risk_short", "risk_long_lit", "risk_short_lit")

_FLOAT_KEYS = ("alma", "dev", "atr", "slope", "conviction", "edge_up", "edge_dn",
               "risk_long", "risk_short", "risk_long_lit", "risk_short_lit")


# ───────────────────────────── Pine values ─────────────────────────────

def is_na(x) -> bool:
    """``na(x)``: NaN is Pine's na."""
    return x != x


def nz(x, y=0.0):
    """``nz(x, y)``: y when x is na."""
    return y if is_na(x) else x


def pmax(a, b):
    """``math.max(a, b)``: na when either is na."""
    if is_na(a) or is_na(b):
        return NAN
    return a if a >= b else b


def pmin(a, b):
    """``math.min(a, b)``: na when either is na."""
    if is_na(a) or is_na(b):
        return NAN
    return a if a <= b else b


def _back(values: List[float], i: int) -> float:
    """``x[i]`` of a call site's argument whose values (oldest first) end with the current execution's; na before
    the first execution."""
    j = len(values) - 1 - i
    return values[j] if j >= 0 else NAN


def _pine_sum(fst: float, snd: float) -> float:
    """The reference's ``SUM(fst, snd)`` inside ``pine_stdev``: fst + snd, and 0 when its magnitude is at most 1e-10
    (the reference's "15" for other small values is a documentation slip and is not copied; reading 2)."""
    res = fst + snd
    if is_na(res):
        return NAN
    return 0.0 if abs(res) <= 1e-10 else res


def _length(n, name: str) -> int:
    if isinstance(n, (bool, np.bool_)):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    f = float(n)
    if not (f >= 1.0 and f == math.floor(f)):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    return int(f)


# ───────────────────────────── Pine call sites ─────────────────────────────
# One object per call site; each call is one execution of that call site and passes the argument's current value.

class Sma:
    """``ta.sma(x, length)``, the reference ``pine_sma``: ``sum := sum + x[i] / y`` for i = 0 .. y - 1 (i = 0 the
    newest value); na until the call site has seen ``length`` values (an na ``x[i]`` makes the sum na)."""

    def __init__(self, length):
        self.n = _length(length, "sma length")
        self.x: List[float] = []

    def __call__(self, x: float) -> float:
        self.x.append(x)
        total = 0.0
        for i in range(self.n):
            total = total + _back(self.x, i) / self.n
        return total


class Stdev:
    """``ta.stdev(src, length, biased)``, the reference ``pine_stdev`` (reading 2): biased = true (the default) is the
    population deviation (divide by length); ``biased=False`` divides by length - 1 (only to measure the trap)."""

    def __init__(self, length, biased: bool = True):
        self.n = _length(length, "stdev length")
        self.biased = bool(biased)
        self.src: List[float] = []
        self.sma = Sma(self.n)                      # avg = ta.sma(src, length)

    def __call__(self, x: float) -> float:
        self.src.append(x)
        avg = self.sma(x)
        sum_sq = 0.0                                # sumOfSquareDeviations = 0.0
        for i in range(self.n):
            d = _pine_sum(_back(self.src, i), -avg)  # sum = SUM(src[i], -avg)
            sum_sq = sum_sq + d * d
        if is_na(sum_sq):
            return NAN
        return math.sqrt(sum_sq / self.n) if self.biased else math.sqrt(sum_sq / (self.n - 1))


class Rma:
    """``ta.rma(src, length)``, the reference ``pine_rma`` (reading 3): ``sum := na(sum[1]) ? ta.sma(src, length) :
    alpha * src + (1 - alpha) * nz(sum[1])``, alpha = 1 / length. The ``ta.sma`` is a call site in the ternary's first
    branch: it runs only on the executions where ``sum[1]`` is na."""

    def __init__(self, length):
        n = _length(length, "rma length")
        self.alpha = 1 / n
        self.prev = NAN                             # sum[1]
        self.sma = Sma(n)

    def __call__(self, x: float) -> float:
        if is_na(self.prev):
            v = self.sma(x)
        else:
            v = self.alpha * x + (1 - self.alpha) * nz(self.prev)
        self.prev = v
        return v


class Atr:
    """``ta.atr(length)``, the reference ``pine_atr`` (reading 3): ``trueRange = na(high[1]) ? high - low :
    math.max(math.max(high - low, math.abs(high - close[1])), math.abs(low - close[1]))``; ``ta.rma(trueRange,
    length)``."""

    def __init__(self, length):
        self.rma = Rma(length)
        self.h1 = NAN                               # high[1]
        self.c1 = NAN                               # close[1]
        self.tr = NAN                               # the last true range (for the tests)

    def __call__(self, h: float, l: float, c: float) -> float:
        if is_na(self.h1):
            tr = h - l
        else:
            tr = pmax(pmax(h - l, abs(h - self.c1)), abs(l - self.c1))
        self.h1, self.c1, self.tr = h, c, tr
        return self.rma(tr)


class Alma:
    """``ta.alma(series, length, offset, sigma, floor)``, the reference ``pine_alma`` (reading 1)::

        m = offset * (windowsize - 1)          // math.floor(...) when floor = true
        s = windowsize / sigma
        for i = 0 to windowsize - 1
            weight = math.exp(-1 * math.pow(i - m, 2) / (2 * math.pow(s, 2)))
            norm := norm + weight
            sum := sum + series[windowsize - i - 1] * weight
        sum / norm
    """

    def __init__(self, length, offset: float, sigma: float, floor: bool = False):
        self.n = _length(length, "alma length")
        m = float(offset) * (self.n - 1)
        if floor:
            m = float(math.floor(m))
        s = self.n / float(sigma)
        self.m, self.s = m, s
        self.w = [math.exp(-1 * math.pow(i - m, 2) / (2 * math.pow(s, 2))) for i in range(self.n)]
        norm = 0.0
        for i in range(self.n):
            norm = norm + self.w[i]
        self.norm = norm
        self.x: List[float] = []

    def __call__(self, x: float) -> float:
        self.x.append(x)
        total = 0.0
        for i in range(self.n):
            total = total + _back(self.x, self.n - i - 1) * self.w[i]
        return total / self.norm


class Extreme:
    """``ta.lowest(source, length)`` (``mode="min"``) or ``ta.highest(source, length)`` (``mode="max"``) at ONE call
    site (reading 6).

    The call site keeps the source values of its own executions and the results of its own executions. An execution's
    result is the min (max) of the last ``length`` non-na values the call site has seen, na while the chart's
    bar_index < length - 1 (PineTS, after TradingView); ``prev()`` right after an execution is ``call(...)[1]``, the
    result of the previous execution (na before the second). A call site that runs on every bar therefore gives the
    plain ``ta.lowest`` of the last ``length`` bars. ``full=True`` is the measured alternative: na until the call
    site has seen ``length`` values.
    """

    def __init__(self, length, mode: str, full: bool = False):
        if mode not in ("min", "max"):
            raise ValueError(f"mode: 'min' or 'max', got {mode!r}")
        self.n = _length(length, "lookback")
        self.mode = mode
        self.full = bool(full)
        self.seen: List[float] = []
        self.results: List[float] = []

    def __call__(self, x: float, bar_index: int) -> float:
        if not is_na(x):
            self.seen.append(x)
        if bar_index < self.n - 1 or not self.seen or (self.full and len(self.seen) < self.n):
            r = NAN
        else:
            window = self.seen[-self.n:]
            r = window[0]
            for v in window[1:]:
                if (v < r) if self.mode == "min" else (v > r):
                    r = v
        self.results.append(r)
        return r

    def prev(self) -> float:
        return self.results[-2] if len(self.results) >= 2 else NAN


# ───────────────────────────── the script ─────────────────────────────

def _inputs(o, h, l, c):
    arrs = []
    for name, x in (("o", o), ("h", h), ("l", l), ("c", c)):
        a = np.asarray(x, dtype=np.float64)
        if a.ndim != 1:
            raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
        if not np.all(np.isfinite(a)):
            raise ValueError(f"{name}: every price must be finite (Pine's handling of an na bar is not ported)")
        arrs.append(a)
    if len({a.size for a in arrs}) != 1:
        raise ValueError("o, h, l, c: equal lengths expected")
    return arrs


def _ribbon_vm(o, h, l, c, alma_len=34, alma_offset=0.85, alma_sigma=6.0, dev_len=34, dev_mult=0.65, slope_len=3,
               slope_min=0.08, atr_len=14, stop_lookback=12, min_stop_atr=0.75, max_stop_atr=3.0, edge_mult=0.55,
               floor: bool = False, biased: bool = True, lit_full: bool = False) -> Dict[str, np.ndarray]:
    """The bar loop. ``floor``, ``biased`` and ``lit_full`` are the alternative readings 1, 2 and 6 (measurement
    only); the defaults are the script's. Each statement cites the Pine line it transcribes."""
    _, H, L, C = _inputs(o, h, l, c)
    n = C.size
    slope_len = _length(slope_len, "slope_len")
    dev_mult, slope_min, edge_mult = float(dev_mult), float(slope_min), float(edge_mult)
    min_stop_atr, max_stop_atr = float(min_stop_atr), float(max_stop_atr)

    alma_site = Alma(alma_len, alma_offset, alma_sigma, floor)     # L88  ta.alma(src, almaLen, almaOffset, almaSigma)
    dev_site = Stdev(dev_len, biased)                               # L89  ta.stdev(src, devLen)
    atr_site = Atr(atr_len)                                         # L90  ta.atr(atrLen)
    low_every = Extreme(stop_lookback, "min")                       # INTENDED: L316's ta.lowest run on every bar
    high_every = Extreme(stop_lookback, "max")                      # INTENDED: L317's ta.highest run on every bar
    low_flip = Extreme(stop_lookback, "min", lit_full)              # LITERAL: L316, runs on bull flips only
    high_flip = Extreme(stop_lookback, "max", lit_full)             # LITERAL: L317, runs on bear flips only

    out = {k: np.full(n, np.nan) for k in _FLOAT_KEYS}
    out["bull_setup"] = np.zeros(n, dtype=bool)
    out["bear_setup"] = np.zeros(n, dtype=bool)
    out["trend"] = np.zeros(n, dtype=np.int8)
    out["flip"] = np.zeros(n, dtype=np.int8)

    alma_series: List[float] = []                                   # the global series `alma` (for alma[slopeLen])
    trend = 0                                                       # L100  var int trend = 0
    for t in range(n):
        high, low, close = float(H[t]), float(L[t]), float(C[t])
        alma = alma_site(close)                                     # L88
        dev = dev_site(close)                                       # L89
        atr = atr_site(high, low, close)                            # L90
        alma_series.append(alma)
        alma_k = _back(alma_series, slope_len)                      # alma[slopeLen]
        slope = (alma - alma_k) / atr if atr > 0 else 0.0           # L92
        upper = alma + dev * dev_mult                               # L94  upperConfirm
        lower = alma - dev * dev_mult                               # L95  lowerConfirm
        bull_setup = slope > slope_min and close > upper            # L97
        bear_setup = slope < -slope_min and close < lower           # L98
        bull_flip = False                                           # L102
        bear_flip = False                                           # L103
        if trend != 1 and bull_setup:                               # L105
            trend = 1                                               # L106
            bull_flip = True                                        # L107
        elif trend != -1 and bear_setup:                            # L108
            trend = -1                                              # L109
            bear_flip = True                                        # L110
        bull = trend == 1                                           # L112
        flip = bull_flip or bear_flip                               # L114
        distance = abs(close - alma) / atr if atr > 0 else 0.0      # L120  distanceScore
        conviction = pmax(0.0, pmin(1.0, abs(slope) * 2.0 + distance * 0.35))   # L122-123

        minimum_risk = atr * min_stop_atr                           # L323
        maximum_risk = atr * max_stop_atr                           # L324

        # INTENDED structure levels: ta.lowest(low, stopLookback)[1] / ta.highest(high, stopLookback)[1] on every bar
        low_every(low, t)
        high_every(high, t)
        raw_long = close - low_every.prev()                         # L320  entryPrice - structureStop
        raw_short = high_every.prev() - close                       # L321  structureStop - entryPrice
        out["risk_long"][t] = pmin(pmax(nz(raw_long, minimum_risk), minimum_risk), maximum_risk)    # L326-328
        out["risk_short"][t] = pmin(pmax(nz(raw_short, minimum_risk), minimum_risk), maximum_risk)

        # LITERAL: inside `if flip` (L281) and inside the ternary of L315-317
        if flip:
            position_dir = 1 if bull else -1                        # L312
            if position_dir == 1:                                   # L315
                low_flip(low, t)                                    # L316  ta.lowest(low, stopLookback) executes
                structure_stop = low_flip.prev()                    #       ...[1]: its previous execution's result
                raw = close - structure_stop                        # L320
                out["risk_long_lit"][t] = pmin(pmax(nz(raw, minimum_risk), minimum_risk), maximum_risk)
            else:
                high_flip(high, t)                                  # L317
                structure_stop = high_flip.prev()
                raw = structure_stop - close                        # L321
                out["risk_short_lit"][t] = pmin(pmax(nz(raw, minimum_risk), minimum_risk), maximum_risk)

        out["alma"][t] = alma
        out["dev"][t] = dev
        out["atr"][t] = atr
        out["slope"][t] = slope
        out["conviction"][t] = conviction
        out["edge_up"][t] = alma + dev * edge_mult                  # L127  (bear: alma + dev * 0.55)
        out["edge_dn"][t] = alma - dev * edge_mult                  # L126  (bull: alma - dev * 0.55)
        out["bull_setup"][t] = bull_setup
        out["bear_setup"][t] = bear_setup
        out["trend"][t] = trend
        out["flip"][t] = 1 if bull_flip else (-1 if bear_flip else 0)
    return {k: out[k] for k in KEYS}


def ribbon(o, h, l, c, alma_len=34, alma_offset=0.85, alma_sigma=6.0, dev_len=34, dev_mult=0.65, slope_len=3,
           slope_min=0.08, atr_len=14, stop_lookback=12, min_stop_atr=0.75, max_stop_atr=3.0,
           edge_mult=0.55) -> Dict[str, np.ndarray]:
    """BOSWaves' Trend Target Ribbon on the bars (o, h, l, c), oldest first: the contract of the module docstring,
    a dict with the keys ``KEYS``, every array of len(bars)."""
    return _ribbon_vm(o, h, l, c, alma_len=alma_len, alma_offset=alma_offset, alma_sigma=alma_sigma, dev_len=dev_len,
                      dev_mult=dev_mult, slope_len=slope_len, slope_min=slope_min, atr_len=atr_len,
                      stop_lookback=stop_lookback, min_stop_atr=min_stop_atr, max_stop_atr=max_stop_atr,
                      edge_mult=edge_mult)


def script_positions(o, h, l, c, stop: str = "literal", target_count: int = 4, **params) -> List[dict]:
    """
    The script's own position bookkeeping, as the chart draws it (outside the comparison contract). ``stop="literal"``
    is the stop TradingView computes (``risk_*_lit``); ``stop="intended"`` the registered one (``risk_*``).
    ``params`` are ``ribbon``'s inputs. One dict per position, in order:

    * ``dir`` (+1 / -1), ``entry_bar``, ``entry`` (the flip bar's close, L310), ``risk`` (riskDist), ``stop`` (the
      absolute level entry - dir * risk, L330), ``targets`` (entry + dir * risk * k, k = 1 .. target_count, L422);
    * ``hit_bar``: per target, the first bar on which the script's check mark ``targetHit`` became true (L626-631),
      None if never. The check runs on the entry bar too (the "Active Position" block, L495, runs after "New Position"
      on the same bar and its stop test needs ``bar_index > entryBar``), so the entry bar's high (low) can tick a
      target before the entry close;
    * ``end_bar`` and ``end``: "stop" when ``low <= stop`` (long) / ``high >= stop`` (short) on a bar after the entry
      bar (L498-501, L580); "flip" when the next flip freezes it (L215-277, which runs before the stop test and makes
      it skip: the flip bar's own low / high is not checked against the old stop); None while still open at the last
      bar. After a stop nothing opens until the next flip (no reset of the trend; L100-110 never read the position).
    """
    if stop not in ("literal", "intended"):
        raise ValueError(f"stop: 'literal' or 'intended', got {stop!r}")
    k = _length(target_count, "target_count")
    if not 2 <= k <= 4:                                             # L39  input.int(4, minval = 2, maxval = 4)
        raise ValueError(f"target_count: 2 .. 4 (the script's input range), got {target_count!r}")
    _, H, L, C = _inputs(o, h, l, c)
    r = ribbon(o, h, l, c, **params)
    risk_l = r["risk_long_lit"] if stop == "literal" else r["risk_long"]
    risk_s = r["risk_short_lit"] if stop == "literal" else r["risk_short"]

    entry_price = NAN                                               # L180  var float entryPrice = na
    stop_price = NAN                                                # L181
    risk_dist = NAN                                                 # L182
    entry_bar: Optional[int] = None                                 # L184
    position_dir = 0                                                # L185
    position_ended = True                                           # L187
    target_hit = [False] * 4                                        # L205  array.new<bool>(4, false)
    n_targets = 0                                                   # targetGlow.size()
    positions: List[dict] = []
    cur: Optional[dict] = None
    for t in range(C.size):
        flip = int(r["flip"][t]) != 0
        if flip and not is_na(entry_price) and not position_ended:  # L215  Freeze Position
            cur["end_bar"], cur["end"] = t, "flip"
            position_ended = True                                   # L277
        if flip:                                                    # L281  New Position
            n_targets = 0                                           # L301-305  targetGlow.clear() ...
            for i in range(4):                                      # L307-308
                target_hit[i] = False
            entry_price = float(C[t])                               # L310
            entry_bar = t                                           # L311
            position_dir = 1 if int(r["trend"][t]) == 1 else -1     # L312
            position_ended = False                                  # L313
            risk_dist = float(risk_l[t] if position_dir == 1 else risk_s[t])   # L315-328
            stop_price = entry_price - position_dir * risk_dist     # L330
            targets = tuple(entry_price + position_dir * risk_dist * (i + 1) for i in range(k))   # L421-422
            n_targets = k                                           # L475  targetGlow.push(glow), k times
            cur = {"dir": position_dir, "entry_bar": t, "entry": entry_price, "risk": risk_dist, "stop": stop_price,
                   "targets": targets, "hit_bar": [None] * k, "end_bar": None, "end": None}
            positions.append(cur)
        if not is_na(entry_price) and not position_ended and n_targets > 0:   # L495  Active Position
            if position_dir == 1:                                   # L498-501
                stopped_now = t > entry_bar and float(L[t]) <= stop_price
            else:
                stopped_now = t > entry_bar and float(H[t]) >= stop_price
            if stopped_now:                                         # L503
                cur["end_bar"], cur["end"] = t, "stop"
                position_ended = True                               # L580
            else:
                for i in range(n_targets):                          # L620
                    target_price = entry_price + position_dir * risk_dist * (i + 1)    # L621
                    hit = target_hit[i]                             # L624
                    hit = hit or (float(H[t]) >= target_price if position_dir == 1 else float(L[t]) <= target_price)
                    target_hit[i] = hit                             # L631
                    if hit and cur["hit_bar"][i] is None:
                        cur["hit_bar"][i] = t
    return positions
