"""
The oracle of ``backtesting/research/tradeiq_ind.py``: PORT B of the TradeIQ indicators, kept as it was written.

Two engineers ported the four indicators (QQE MOD, Bjorgum TSI, AlgoAlpha's Volume Weighted RSI, Laguerre RSI) and the
reference lines (RSI 14, SMA 200, ATR 14) from their Pine sources independently. ``tradeiq_ind.py`` keeps port A's
arithmetic (numpy); this file is port B (numba bar loops, ``cache=False``, so nothing is written to disk), with its own
reading of every Pine detail, and after it port B's second transcription, the "Pine VM": a plain-Python bar-by-bar
loop with one state object per Pine call site, written from the Pine text. ``tests/test_tradeiq_ind.py`` requires the
module to equal both, bit for bit, on synthetic series and on the real bars (``PORTING.md`` in
``backtest_results/tradeiq_rsi`` explains the reconciliation).

Only the first two paragraphs of this docstring and the heading of the Pine VM section are new; the code is port B's,
unchanged (port B's NOTES.md, which its summary below mentions, is not in the repository: PORTING.md carries what
matters of it). Its conventions where they differ from the module's: the QQE colour is NaN (not GRAY) on the bars where the smoothed RSI is na; ``table()`` names the
lines its own way (``rsi14``, ``vwrsi_range_score``, ``qqe_tl_p``, ...); the alternatives ``ema(seed="sma")``,
``hma(half="round")`` and ``cross(how="over_or_under")`` exist only to measure the readings of DEVIATIONS 11, 12 and
14. Port B's own summary of itself follows.

TradeIQ RSI study - indicator port B (written independently of port A).

What this is
------------
The four TradingView indicators of the TradeIQ video (QQE MOD, Bjorgum TSI, AlgoAlpha Volume Weighted RSI,
Laguerre RSI) and the study's reference lines (RSI 14, SMA 200, Wilder ATR 14), ported from their Pine sources
bar by bar with Pine's series semantics:

* the history of a series before the first bar is na, so ``x[1]`` on bar 0 is na;
* arithmetic with na gives na; ``nz(x)`` replaces na with 0; a comparison with na is false, so
  ``cond ? a : b`` takes ``b``;
* a variable declared without ``var`` is re-initialised on every bar; its history (``v[1]``) is the value it
  ended the previous bar with;
* Pine v5 divides two ``const int`` values as integers (``2/3 == 0``) and keeps the fraction when an operand
  is input / simple / series (TradingView, "To Pine v6" migration guide, "Fractional division of constants").

Inputs are 1-D arrays, one value per bar, oldest first (cast to float64). Outputs are float64 arrays with
NaN where Pine gives na; the cross helpers return bool arrays. The recursive and windowed helpers are
explicit bar loops in the operation order of the "same on pine" code of TradingView's reference, so the
arithmetic is the documented one. Every source, reading and open point is in NOTES.md next to this file.

Pine helpers   sma, ema, rma, wma, hma, stdev, change, math_sum, crossover, crossunder, cross, hist (x[k]),
               rsi (ta.rsi), true_range (ta.tr(true)), atr (ta.atr)
Indicators     rsi14, larsi, vwrsi (+ range_score), bjorgum_tsi, qqe_mod, sma200, atr14
All of them    table(high, low, close, volume) -> {name: array}
"""

from __future__ import annotations

import math
from typing import Dict, NamedTuple

import numpy as np
from numba import njit

__all__ = [
    "sma", "ema", "rma", "wma", "hma", "stdev", "change", "math_sum", "crossover", "crossunder", "cross",
    "hist", "rsi", "true_range", "atr",
    "rsi14", "larsi", "vwrsi", "range_score", "bjorgum_tsi", "qqe_mod", "sma200", "atr14", "table",
    "VWRSI", "TSI", "QQE", "BLUE", "RED", "GRAY",
]

BLUE, RED, GRAY = 1.0, -1.0, 0.0          # QQE MOD bar colour codes (NaN: no bar, the RSI is na)


# ───────────────────────────── input checks ─────────────────────────────

def _arr(x, name: str = "x") -> np.ndarray:
    a = np.ascontiguousarray(x, dtype=np.float64)
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
    return a


def _length(n, name: str = "length") -> int:
    """A Pine ``length`` argument: an integer >= 1 (an integral float is accepted)."""
    if isinstance(n, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected")
    f = float(n)
    if not (f >= 1.0 and f == math.floor(f)):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    return int(f)


def _leading_na_only(a: np.ndarray, name: str) -> None:
    """The moving averages are ported for a source whose na values all come first (the warm-up of whatever is
    fed in). TradingView documents that its averages "ignore" na values; how a value of the output looks on an
    na bar inside the series is not documented, so an na after the first valid value is refused, not guessed."""
    bad = np.isnan(a)
    if not bad.any() or bad.all():
        return
    first = int(np.argmin(bad))
    if bad[first:].any():
        where = first + int(np.argmax(bad[first:]))
        raise ValueError(f"{name}: na (NaN) at bar {where} after the first valid value at bar {first}; "
                         "Pine's handling of an na inside the series is not ported")


# ───────────────────────────── bar loops ─────────────────────────────

@njit(cache=False)
def _first_valid(x):
    for i in range(x.size):
        if not np.isnan(x[i]):
            return i
    return x.size


@njit(cache=False)
def _sma_k(x, n):
    # pine_sma(x, y) => sum = 0.0 ; for i = 0 to y - 1: sum := sum + x[i] / y
    out = np.full(x.size, np.nan)
    f = _first_valid(x)
    for t in range(f + n - 1, x.size):
        s = 0.0
        for i in range(n):
            s = s + x[t - i] / n
        out[t] = s
    return out


@njit(cache=False)
def _sum_k(x, n):
    out = np.full(x.size, np.nan)
    f = _first_valid(x)
    for t in range(f + n - 1, x.size):
        s = 0.0
        for i in range(n):
            s = s + x[t - i]
        out[t] = s
    return out


@njit(cache=False)
def _wma_k(x, n):
    # pine_wma(x, y) => for i = 0 to y - 1: weight = (y - i) * y ; norm += weight ; sum += x[i] * weight ; sum / norm
    out = np.full(x.size, np.nan)
    f = _first_valid(x)
    for t in range(f + n - 1, x.size):
        norm = 0.0
        s = 0.0
        for i in range(n):
            weight = (n - i) * n
            norm = norm + weight
            s = s + x[t - i] * weight
        out[t] = s / norm
    return out


@njit(cache=False)
def _stdev_k(x, n, avg, biased):
    # pine_stdev: avg = ta.sma(src, length) ; for i: sum = SUM(src[i], -avg) ; sumsq += sum * sum ;
    # math.sqrt(sumsq / length). SUM(fst, snd) returns 0 when |fst + snd| <= 1e-10, else fst + snd.
    out = np.full(x.size, np.nan)
    for t in range(x.size):
        a = avg[t]
        if np.isnan(a):
            continue
        ss = 0.0
        for i in range(n):
            d = x[t - i] + (-a)
            if abs(d) <= 1e-10:
                d = 0.0
            ss = ss + d * d
        if biased:
            out[t] = math.sqrt(ss / n)
        else:
            out[t] = math.sqrt(ss / (n - 1))
    return out


@njit(cache=False)
def _ema_first_k(x, alpha):
    # pine_ema: sum := na(sum[1]) ? src : alpha * src + (1 - alpha) * nz(sum[1])
    out = np.empty(x.size)
    prev = np.nan
    for t in range(x.size):
        if np.isnan(prev):
            v = x[t]
        else:
            v = alpha * x[t] + (1.0 - alpha) * prev
        out[t] = v
        prev = v
    return out


@njit(cache=False)
def _ema_sma_k(x, n, alpha):
    # alternative seed (not the documented one; for the sensitivity check only): na until n values,
    # then their simple mean, then the same recursion
    out = np.full(x.size, np.nan)
    f = _first_valid(x)
    if f + n - 1 >= x.size:
        return out
    s = 0.0
    for i in range(n):
        s = s + x[f + n - 1 - i] / n
    prev = s
    out[f + n - 1] = s
    for t in range(f + n, x.size):
        prev = alpha * x[t] + (1.0 - alpha) * prev
        out[t] = prev
    return out


@njit(cache=False)
def _rma_k(x, seed, alpha):
    # pine_rma: sum := na(sum[1]) ? ta.sma(src, length) : alpha * src + (1 - alpha) * nz(sum[1])
    out = np.empty(x.size)
    prev = np.nan
    for t in range(x.size):
        if np.isnan(prev):
            v = seed[t]
        else:
            v = alpha * x[t] + (1.0 - alpha) * prev
        out[t] = v
        prev = v
    return out


@njit(cache=False)
def _larsi_k(src, alpha):
    gamma = 1.0 - alpha                       # gamma = 1 - alpha
    n = src.size
    out = np.empty(n)
    p0 = np.nan                               # L0[1] .. L3[1]: na before the first bar
    p1 = np.nan
    p2 = np.nan
    p3 = np.nan
    for t in range(n):
        s = src[t]
        z0 = 0.0 if np.isnan(p0) else p0      # nz(L0[1])
        z1 = 0.0 if np.isnan(p1) else p1
        z2 = 0.0 if np.isnan(p2) else p2
        z3 = 0.0 if np.isnan(p3) else p3
        l0 = (1.0 - gamma) * s + gamma * z0                   # L0 := (1 - gamma) * src + gamma * nz(L0[1])
        l1 = -gamma * l0 + z0 + gamma * z1                     # L1 := -gamma * L0 + nz(L0[1]) + gamma * nz(L1[1])
        l2 = -gamma * l1 + z1 + gamma * z2
        l3 = -gamma * l2 + z2 + gamma * z3
        cu = ((l0 - l1) if l0 > l1 else 0.0) + ((l1 - l2) if l1 > l2 else 0.0) + ((l2 - l3) if l2 > l3 else 0.0)
        cd = ((l1 - l0) if l0 < l1 else 0.0) + ((l2 - l1) if l1 < l2 else 0.0) + ((l3 - l2) if l2 < l3 else 0.0)
        temp = -1.0 if cu + cd == 0.0 else cu + cd             # temp = cu + cd == 0 ? -1 : cu + cd
        la = 0.0 if temp == -1.0 else cu / temp                # LaRSI = temp == -1 ? 0 : cu / temp
        out[t] = 100.0 * la                                    # plot(100 * LaRSI)
        p0 = l0
        p1 = l1
        p2 = l2
        p3 = l3
    return out


@njit(cache=False)
def _qqe_bands_k(srsi, new_long, new_short):
    # longBand := smoothedRsi[1] > longBand[1] and smoothedRsi > longBand[1] ? math.max(longBand[1], newLongBand) : newLongBand
    # shortBand := smoothedRsi[1] < shortBand[1] and smoothedRsi < shortBand[1] ? math.min(shortBand[1], newShortBand) : newShortBand
    n = srsi.size
    lb = np.empty(n)
    sb = np.empty(n)
    lb1 = np.nan
    sb1 = np.nan
    s1 = np.nan
    for t in range(n):
        s = srsi[t]
        if s1 > lb1 and s > lb1:
            nl = new_long[t]
            lb[t] = lb1 if lb1 >= nl else nl
        else:
            lb[t] = new_long[t]
        if s1 < sb1 and s < sb1:
            ns = new_short[t]
            sb[t] = sb1 if sb1 <= ns else ns
        else:
            sb[t] = new_short[t]
        lb1 = lb[t]
        sb1 = sb[t]
        s1 = s
    return lb, sb


@njit(cache=False)
def _trend_k(up_cross, down_cross):
    # if ta.cross(smoothedRsi, shortBand[1]) -> 1 ; else if longBandCross -> -1 ; else trendDirection[1] (na on bar 0)
    n = up_cross.size
    out = np.empty(n)
    prev = np.nan
    for t in range(n):
        if up_cross[t]:
            v = 1.0
        elif down_cross[t]:
            v = -1.0
        else:
            v = prev
        out[t] = v
        prev = v
    return out


# ───────────────────────────── Pine helpers ─────────────────────────────

def hist(x, k: int = 1) -> np.ndarray:
    """``x[k]``: the value k bars back; na on the first k bars."""
    a = _arr(x)
    k = int(k)
    if k < 0:
        raise ValueError("k >= 0 expected")
    out = np.full(a.size, np.nan)
    if k == 0:
        return a.copy()
    if a.size > k:
        out[k:] = a[:-k]
    return out


def change(x) -> np.ndarray:
    """``ta.change(x)`` = x - x[1]; na on bar 0 and wherever x or x[1] is na."""
    a = _arr(x)
    out = np.full(a.size, np.nan)
    if a.size > 1:
        out[1:] = a[1:] - a[:-1]
    return out


def sma(x, length) -> np.ndarray:
    """``ta.sma``: mean of the last ``length`` values (pine_sma's order: sum of x[i] / length, i = 0 first);
    na until ``length`` valid values exist."""
    a = _arr(x)
    n = _length(length)
    _leading_na_only(a, "sma")
    return _sma_k(a, n)


def math_sum(x, length) -> np.ndarray:
    """``math.sum``: sliding sum of the last ``length`` values; na until ``length`` valid values exist."""
    a = _arr(x)
    n = _length(length)
    _leading_na_only(a, "math_sum")
    return _sum_k(a, n)


def ema(x, length, seed: str = "first") -> np.ndarray:
    """``ta.ema`` with alpha = 2 / (length + 1). ``seed="first"`` (the plan's and the reference's
    pine_ema): the first valid source value starts the average. ``seed="sma"``: na until ``length`` values,
    seeded with their mean (an alternative reading, used only to measure its effect; see NOTES.md)."""
    a = _arr(x)
    n = _length(length)
    _leading_na_only(a, "ema")
    alpha = 2 / (n + 1)
    if seed == "first":
        return _ema_first_k(a, alpha)
    if seed == "sma":
        return _ema_sma_k(a, n, alpha)
    raise ValueError(f"seed: 'first' or 'sma', got {seed!r}")


def rma(x, length) -> np.ndarray:
    """``ta.rma`` (Wilder), alpha = 1 / length, seeded with ``ta.sma(x, length)`` on the first bar it exists."""
    a = _arr(x)
    n = _length(length)
    _leading_na_only(a, "rma")
    return _rma_k(a, _sma_k(a, n), 1 / n)


def wma(x, length) -> np.ndarray:
    """``ta.wma``: weights length, length - 1, ..., 1 on the newest .. oldest value (pine_wma's arithmetic)."""
    a = _arr(x)
    n = _length(length)
    _leading_na_only(a, "wma")
    return _wma_k(a, n)


def _hma_lengths(length, half: str = "floor"):
    L = float(length)
    if not (L >= 2.0) or not math.isfinite(L):
        raise ValueError(f"hma: length >= 2 expected, got {length!r}")
    if half == "floor":
        h = math.floor(L / 2)
    elif half == "round":                       # Pine's math.round: ties round up
        h = math.floor(L / 2 + 0.5)
    else:
        raise ValueError(f"half: 'floor' or 'round', got {half!r}")
    return int(h), int(math.floor(L)), int(math.floor(math.sqrt(L)))


def hma(x, length, half: str = "floor") -> np.ndarray:
    """``ta.hma`` = wma(2 * wma(x, length / 2) - wma(x, length), floor(sqrt(length))), the formula of
    TradingView's built-in "Hull moving average" script. The half length is floored (``half="round"``: Pine's
    math.round, for the sensitivity check only); a non-integral ``length`` is floored for the full WMA."""
    a = _arr(x)
    _leading_na_only(a, "hma")
    h, full, root = _hma_lengths(length, half)
    raw = 2.0 * _wma_k(a, h) - _wma_k(a, full)
    return _wma_k(raw, root)


def stdev(x, length, biased: bool = True) -> np.ndarray:
    """``ta.stdev`` (default biased = population, divides by length), around ``ta.sma``; deviations of at most
    1e-10 count as 0 (the reference's SUM/isZero)."""
    a = _arr(x)
    n = _length(length)
    _leading_na_only(a, "stdev")
    if not biased and n < 2:
        raise ValueError("stdev: the unbiased estimate needs length >= 2")
    return _stdev_k(a, n, _sma_k(a, n), bool(biased))


def crossover(a, b) -> np.ndarray:
    """``ta.crossover``: a > b now and a <= b on the previous bar (false where any of them is na)."""
    x, y = _arr(a, "a"), _arr(b, "b")
    out = np.zeros(x.size, dtype=bool)
    if x.size > 1:
        with np.errstate(invalid="ignore"):
            out[1:] = (x[1:] > y[1:]) & (x[:-1] <= y[:-1])
    return out


def crossunder(a, b) -> np.ndarray:
    """``ta.crossunder``: a < b now and a >= b on the previous bar (false where any of them is na)."""
    x, y = _arr(a, "a"), _arr(b, "b")
    out = np.zeros(x.size, dtype=bool)
    if x.size > 1:
        with np.errstate(invalid="ignore"):
            out[1:] = (x[1:] < y[1:]) & (x[:-1] >= y[:-1])
    return out


def cross(a, b, how: str = "gt_change") -> np.ndarray:
    """``ta.cross`` (no formula in TradingView's reference). ``how="gt_change"``: ``a > b`` differs from the
    previous bar's ``a > b``, all four values valid (PineTS's reading). ``how="over_or_under"``: crossover or
    crossunder. They differ only when a == b exactly on one of the two bars (NOTES.md)."""
    x, y = _arr(a, "a"), _arr(b, "b")
    if how == "over_or_under":
        return crossover(x, y) | crossunder(x, y)
    if how != "gt_change":
        raise ValueError(f"how: 'gt_change' or 'over_or_under', got {how!r}")
    out = np.zeros(x.size, dtype=bool)
    if x.size > 1:
        ok = ~(np.isnan(x[1:]) | np.isnan(y[1:]) | np.isnan(x[:-1]) | np.isnan(y[:-1]))
        with np.errstate(invalid="ignore"):
            out[1:] = ok & ((x[1:] > y[1:]) != (x[:-1] > y[:-1]))
    return out


def _rsi_from(up: np.ndarray, down: np.ndarray) -> np.ndarray:
    # rsi = down == 0 ? 100 : up == 0 ? 0 : 100 - (100 / (1 + up / down))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - (100.0 / (1.0 + up / down))
    r = np.where(up == 0.0, 0.0, r)
    return np.where(down == 0.0, 100.0, r)


def rsi(x, length) -> np.ndarray:
    """``ta.rsi``: ta.rma of the upward and downward changes; down == 0 gives 100, up == 0 gives 0 (as
    TradingView's built-in RSI script writes it). Valid from bar ``length``."""
    a = _arr(x)
    n = _length(length)
    ch = change(a)
    with np.errstate(invalid="ignore"):
        u = np.maximum(ch, 0.0)                 # math.max(change, 0); na stays na
        d = -np.minimum(ch, 0.0)                # -math.min(change, 0)
    return _rsi_from(rma(u, n), rma(d, n))


def true_range(high, low, close) -> np.ndarray:
    """``ta.tr(true)``: high - low on the first bar, else max(high - low, |high - close[1]|, |low - close[1]|)."""
    h, l, c = _arr(high, "high"), _arr(low, "low"), _arr(close, "close")
    if not (h.size == l.size == c.size):
        raise ValueError("high, low, close: equal lengths expected")
    tr = h - l
    if c.size > 1:
        c1 = c[:-1]
        tr[1:] = np.maximum(np.maximum(h[1:] - l[1:], np.abs(h[1:] - c1)), np.abs(l[1:] - c1))
    return tr


def atr(high, low, close, length) -> np.ndarray:
    """``ta.atr(length)`` = ta.rma(true range, length) (the reference's pine_atr)."""
    return rma(true_range(high, low, close), length)


# ───────────────────────────── the indicators ─────────────────────────────

def rsi14(close) -> np.ndarray:
    """The plain RSI(14) on the close (TradingView's built-in RSI script)."""
    return rsi(close, 14)


def sma200(close) -> np.ndarray:
    return sma(close, 200)


def atr14(high, low, close) -> np.ndarray:
    return atr(high, low, close, 14)


def larsi(close, alpha: float = 0.2) -> np.ndarray:
    """Laguerre RSI (Ehlers / KivancOzbilgic): ``100 * LaRSI`` (0..100). Never na: nz() starts the four filter
    stages at 0 on the first bar (an na source gives 0, as the script's ternaries do)."""
    return _larsi_k(_arr(close, "close"), float(alpha))


class VWRSI(NamedTuple):
    rsi: np.ndarray            # the RSI line (0..100)
    up: np.ndarray             # pine_vwrma(max(change, 0), length)
    down: np.ndarray           # pine_vwrma(-min(change, 0), length)
    range_score: np.ndarray    # range_score(rsi, range_len); > 0 = consolidating
    consolidation: np.ndarray  # the "Consolidation Strength" histogram = range_score * 50


def range_score(src, length: int = 10, hma_half: str = "floor") -> np.ndarray:
    """AlgoAlpha's ``range_score(src, length)`` (Pine v5):

        dir = src > 50 ? 1 : -1                 an na src is not > 50: -1
        t = dir + dir[1] == 0 ? 1 : 0           0 on bar 0 (dir[1] is na)
        w = dist / math.sum(dist, length)       dist = 1: na on the first length - 1 bars, then 1 / length
        p = ta.sma(t * w, length)
        v = length / 2                          input int / const int: the fraction is kept (5 for 10)
        f = ta.hma(p, v) * (v + ((2/3) * v))    2/3 is const int / const int = 0 in v5, so f = hma * v
        math.max(ta.hma(f, length * 2), 0)
    """
    s = _arr(src, "src")
    L = _length(length)
    n = s.size
    with np.errstate(invalid="ignore"):
        d = np.where(s > 50.0, 1.0, -1.0)
    t = np.zeros(n)
    if n > 1:
        t[1:] = np.where(d[1:] + d[:-1] == 0.0, 1.0, 0.0)
    w = 1 / math_sum(np.ones(n), L)
    p = sma(t * w, L)
    v = L / 2
    f = hma(p, v, half=hma_half) * (v + ((2 // 3) * v))
    with np.errstate(invalid="ignore"):
        return np.maximum(hma(f, L * 2, half=hma_half), 0.0)


def vwrsi(close, volume, length: int = 14, range_len: int = 10, hma_half: str = "floor") -> VWRSI:
    """AlgoAlpha's Volume Weighted RSI: ``pine_vwrma(x, y) = ta.rma(x * volume, y) / ta.rma(volume, y)``
    of the upward and downward close changes, combined as the built-in RSI; and its consolidation score."""
    c, v = _arr(close, "close"), _arr(volume, "volume")
    if c.size != v.size:
        raise ValueError("close, volume: equal lengths expected")
    n = _length(length)
    ch = change(c)
    with np.errstate(invalid="ignore"):
        u = np.maximum(ch, 0.0)
        d = -np.minimum(ch, 0.0)
    rv = rma(v, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        up = rma(u * v, n) / rv
        down = rma(d * v, n) / rv
    r = _rsi_from(up, down)
    rs = range_score(r, range_len, hma_half=hma_half)
    return VWRSI(r, up, down, rs, rs * 50.0)


class TSI(NamedTuple):
    tsi: np.ndarray            # ta.tsi(close, short, long) * 100 (zero line)
    signal: np.ndarray         # ta.ema(tsi, signal) (the plan's assumption; the copy of the script ends before it)


def bjorgum_tsi(close, short: int = 5, long: int = 25, signal: int = 14, ema_seed: str = "first") -> TSI:
    """Bjorgum TSI, speed "Fast": ``ta.tsi(close, 5, 25) * 100``, ta.tsi being TradingView's TSI:
    ema(ema(change, long), short) / ema(ema(|change|, long), short). A zero denominator (no price change yet)
    is na."""
    c = _arr(close, "close")
    pc = change(c)
    num = ema(ema(pc, long, ema_seed), short, ema_seed)
    den = ema(ema(np.abs(pc), long, ema_seed), short, ema_seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = num / den
    ratio[den == 0.0] = np.nan
    tsi = ratio * 100.0
    return TSI(tsi, ema(tsi, signal, ema_seed))


class QQE(NamedTuple):
    rsi_p: np.ndarray          # primaryRSI = ta.ema(ta.rsi(close, 6), 5) (0..100)
    rsi_s: np.ndarray          # secondaryRSI (same inputs: equal to rsi_p)
    tl_p: np.ndarray           # primaryQQETrendLine (0..100 scale)
    tl_s: np.ndarray           # secondaryQQETrendLine
    trend_p: np.ndarray        # trendDirection of the primary: 1, -1, NaN before its first cross
    trend_s: np.ndarray
    long_p: np.ndarray         # longBand / shortBand of the primary and the secondary
    short_p: np.ndarray
    long_s: np.ndarray
    short_s: np.ndarray
    bb_basis: np.ndarray       # ta.sma(tl_p - 50, 50)
    bb_upper: np.ndarray       # basis + 0.35 * ta.stdev(tl_p - 50, 50)
    bb_lower: np.ndarray
    white: np.ndarray          # tl_s - 50 (the plotted "Secondary QQE Trend Line")
    up: np.ndarray             # "QQE Up Signal" plot: rsi_s - 50 on BLUE bars, else NaN
    down: np.ndarray           # "QQE Down Signal" plot: rsi_s - 50 on RED bars, else NaN
    color: np.ndarray          # 1 BLUE, -1 RED, 0 GRAY (neither), NaN where rsi_s is na


def _qqe_line(close: np.ndarray, rsi_len: int, smoothing: int, factor: float, ema_seed: str, cross_how: str):
    """calculateQQE(rsiLength, smoothingFactor, qqeFactor, source) of the QQE MOD script."""
    wilders = _length(rsi_len) * 2 - 1                       # wildersLength = rsiLength * 2 - 1
    srsi = ema(rsi(close, rsi_len), smoothing, ema_seed)     # smoothedRsi = ta.ema(ta.rsi(source, rsiLength), smoothingFactor)
    atr_rsi = np.abs(hist(srsi, 1) - srsi)                   # math.abs(smoothedRsi[1] - smoothedRsi)
    dyn = ema(atr_rsi, wilders, ema_seed) * factor           # ta.ema(atrRsi, wildersLength) * qqeFactor
    new_short = srsi + dyn
    new_long = srsi - dyn
    lb, sb = _qqe_bands_k(srsi, new_long, new_short)
    long_cross = cross(hist(lb, 1), srsi, how=cross_how)     # ta.cross(longBand[1], smoothedRsi)
    short_cross = cross(srsi, hist(sb, 1), how=cross_how)    # ta.cross(smoothedRsi, shortBand[1])
    trend = _trend_k(short_cross, long_cross)
    tl = np.where(trend == 1.0, lb, sb)                      # trendDirection == 1 ? longBand : shortBand
    return srsi, tl, trend, lb, sb


def qqe_mod(close, rsi_len_p: int = 6, smoothing_p: int = 5, factor_p: float = 3.0,
            rsi_len_s: int = 6, smoothing_s: int = 5, factor_s: float = 1.61, threshold_s: float = 3.0,
            bb_len: int = 50, bb_mult: float = 0.35, ema_seed: str = "first", cross_how: str = "gt_change") -> QQE:
    """QQE MOD (Mihkel00, the Pine v6 copy) with its defaults. The primary threshold input (3.0) is not used
    by the script and is not a parameter here."""
    c = _arr(close, "close")
    rp, tlp, trp, lbp, sbp = _qqe_line(c, rsi_len_p, smoothing_p, factor_p, ema_seed, cross_how)
    rs, tls, trs, lbs, sbs = _qqe_line(c, rsi_len_s, smoothing_s, factor_s, ema_seed, cross_how)
    x = tlp - 50.0
    basis = sma(x, bb_len)
    dev = bb_mult * stdev(x, bb_len)
    upper = basis + dev
    lower = basis - dev
    with np.errstate(invalid="ignore"):
        is_up = (rs - 50.0 > threshold_s) & (rp - 50.0 > upper)
        is_dn = (rs - 50.0 < -threshold_s) & (rp - 50.0 < lower)
    color = np.where(is_up, BLUE, np.where(is_dn, RED, GRAY))
    color[np.isnan(rs)] = np.nan
    up = np.where(is_up, rs - 50.0, np.nan)
    down = np.where(is_dn, rs - 50.0, np.nan)
    return QQE(rp, rs, tlp, tls, trp, trs, lbp, sbp, lbs, sbs, basis, upper, lower, tls - 50.0, up, down, color)


def table(high, low, close, volume) -> Dict[str, np.ndarray]:
    """Every line the study uses, by name (for the value-by-value comparison of the two ports)."""
    q = qqe_mod(close)
    vw = vwrsi(close, volume)
    ts = bjorgum_tsi(close)
    return {
        "rsi14": rsi14(close),
        "larsi": larsi(close),
        "vwrsi": vw.rsi,
        "vwrsi_range_score": vw.range_score,
        "vwrsi_consolidation": vw.consolidation,
        "tsi": ts.tsi,
        "tsi_signal": ts.signal,
        "qqe_rsi_p": q.rsi_p,
        "qqe_rsi_s": q.rsi_s,
        "qqe_tl_p": q.tl_p,
        "qqe_tl_s": q.tl_s,
        "qqe_bb_basis": q.bb_basis,
        "qqe_bb_upper": q.bb_upper,
        "qqe_bb_lower": q.bb_lower,
        "qqe_white": q.white,
        "qqe_color": q.color,
        "sma200": sma200(close),
        "atr14": atr14(high, low, close),
    }


# ==================== port B's Pine VM, from its tests: a second, plain-Python transcription ====================

NAN = float("nan")


# One object per Pine call site, called once per bar, keeping what that call site keeps in Pine.
# Series histories are lists indexed by bar; `at(s, t, k)` is s[k] on bar t (na before bar 0).

def is_na(x):
    return x != x


def nz(x):
    return 0.0 if is_na(x) else x


def at(s, t, k):
    i = t - k
    return s[i] if 0 <= i < len(s) else NAN


def pmax(a, b):
    return NAN if is_na(a) or is_na(b) else (a if a >= b else b)


def pmin(a, b):
    return NAN if is_na(a) or is_na(b) else (a if a <= b else b)


def pdiv(a, b):
    return NAN if is_na(a) or is_na(b) or b == 0 else a / b


class Sma:
    def __init__(self, n):
        self.n, self.src = n, []

    def __call__(self, x):
        self.src.append(x)
        if len(self.src) < self.n:
            return NAN
        s = 0.0
        for i in range(self.n):                       # sum := sum + x[i] / y
            s = s + self.src[-1 - i] / self.n
        return s


class Sum:
    def __init__(self, n):
        self.n, self.src = n, []

    def __call__(self, x):
        self.src.append(x)
        if len(self.src) < self.n:
            return NAN
        s = 0.0
        for i in range(self.n):
            s = s + self.src[-1 - i]
        return s


class Ema:
    def __init__(self, n):
        self.a, self.prev = 2 / (n + 1), NAN

    def __call__(self, x):                            # na(sum[1]) ? src : alpha * src + (1 - alpha) * nz(sum[1])
        v = x if is_na(self.prev) else self.a * x + (1 - self.a) * nz(self.prev)
        self.prev = v
        return v


class Rma:
    def __init__(self, n):
        self.a, self.prev, self.sma = 1 / n, NAN, Sma(n)

    def __call__(self, x):
        s = self.sma(x)
        v = s if is_na(self.prev) else self.a * x + (1 - self.a) * nz(self.prev)
        self.prev = v
        return v


class Wma:
    def __init__(self, n):
        self.n, self.src = n, []

    def __call__(self, x):
        self.src.append(x)
        if len(self.src) < self.n:
            return NAN
        norm = 0.0
        s = 0.0
        for i in range(self.n):
            weight = (self.n - i) * self.n
            norm = norm + weight
            s = s + self.src[-1 - i] * weight
        return s / norm


class Hma:
    def __init__(self, length):
        self.w1 = Wma(int(math.floor(length / 2)))
        self.w2 = Wma(int(math.floor(length)))
        self.w3 = Wma(int(math.floor(math.sqrt(length))))

    def __call__(self, x):
        return self.w3(2 * self.w1(x) - self.w2(x))


class Stdev:
    def __init__(self, n):
        self.n, self.src, self.sma = n, [], Sma(n)

    def __call__(self, x):
        self.src.append(x)
        avg = self.sma(x)
        if is_na(avg):
            return NAN
        ss = 0.0
        for i in range(self.n):
            d = self.src[-1 - i] + -avg
            d = 0.0 if abs(d) <= 1e-10 else d
            ss = ss + d * d
        return math.sqrt(ss / self.n)


class Change:
    def __init__(self):
        self.prev = NAN

    def __call__(self, x):
        v = x - self.prev
        self.prev = x
        return v


class Cross:                                          # a > b on this bar differs from a > b on the last bar
    def __init__(self):
        self.pa = self.pb = NAN

    def __call__(self, a, b):
        ok = not (is_na(a) or is_na(b) or is_na(self.pa) or is_na(self.pb))
        r = ok and ((a > b) != (self.pa > self.pb))
        self.pa, self.pb = a, b
        return r


def rsi_guard(up, down):                              # down == 0 ? 100 : up == 0 ? 0 : 100 - (100 / (1 + up / down))
    if down == 0:
        return 100.0
    if up == 0:
        return 0.0
    return 100 - (100 / (1 + up / down)) if not (is_na(up) or is_na(down)) else NAN


class Rsi:                                            # ta.rsi(x, n)
    def __init__(self, n):
        self.ch, self.ru, self.rd = Change(), Rma(n), Rma(n)

    def __call__(self, x):
        c = self.ch(x)
        return rsi_guard(self.ru(pmax(c, 0)), self.rd(-pmin(c, 0)))


def vm_rsi14(close):
    r = Rsi(14)
    return np.array([r(c) for c in close])


def vm_larsi(close, alpha=0.2):
    gamma = 1 - alpha
    L0, L1, L2, L3, out = [], [], [], [], []
    for t, src in enumerate(close):
        L0.append((1 - gamma) * src + gamma * nz(at(L0, t, 1)))
        L1.append(-gamma * L0[t] + nz(at(L0, t, 1)) + gamma * nz(at(L1, t, 1)))
        L2.append(-gamma * L1[t] + nz(at(L1, t, 1)) + gamma * nz(at(L2, t, 1)))
        L3.append(-gamma * L2[t] + nz(at(L2, t, 1)) + gamma * nz(at(L3, t, 1)))
        cu = (L0[t] - L1[t] if L0[t] > L1[t] else 0) + (L1[t] - L2[t] if L1[t] > L2[t] else 0) + \
             (L2[t] - L3[t] if L2[t] > L3[t] else 0)
        cd = (L1[t] - L0[t] if L0[t] < L1[t] else 0) + (L2[t] - L1[t] if L1[t] < L2[t] else 0) + \
             (L3[t] - L2[t] if L2[t] < L3[t] else 0)
        temp = -1 if cu + cd == 0 else cu + cd
        LaRSI = 0 if temp == -1 else cu / temp
        out.append(100 * LaRSI)
    return np.array(out, dtype=float)


class RangeScore:                                     # range_score(src, int length), Pine v5
    def __init__(self, length):
        self.length, self.dir = length, []
        self.sum, self.sma = Sum(length), Sma(length)
        self.h1, self.h2 = Hma(length / 2), Hma(length * 2)

    def __call__(self, src):
        t = len(self.dir)
        d = 1 if src > 50 else -1
        self.dir.append(d)
        dist = 1
        tt = 1 if d + at(self.dir, t, 1) == 0 else 0
        w = pdiv(dist, self.sum(dist))
        p = self.sma(tt * w)
        v = self.length / 2
        f = self.h1(p) * (v + ((2 // 3) * v))         # v5: 2/3 of two const ints is 0
        return pmax(self.h2(f), 0)


def vm_vwrsi(close, volume, length=14, range_len=10):
    ch_up, ch_dn = Change(), Change()                 # ta.change(rsiSourceInput) is called twice
    rxu, rvu, rxd, rvd = Rma(length), Rma(length), Rma(length), Rma(length)
    calls = [RangeScore(range_len)]
    out_rsi, out_rs = [], []
    for c, vol in zip(close, volume):
        up = pdiv(rxu(pmax(ch_up(c), 0) * vol), rvu(vol))
        down = pdiv(rxd(-pmin(ch_dn(c), 0) * vol), rvd(vol))
        r = rsi_guard(up, down)
        out_rsi.append(r)
        out_rs.append(calls[0](r))
    return np.array(out_rsi, dtype=float), np.array(out_rs, dtype=float)


def vm_tsi(close, short=5, long=25, signal=14):
    ch = Change()
    e1, e2, e3, e4, es = Ema(long), Ema(short), Ema(long), Ema(short), Ema(signal)
    tsi, sig = [], []
    for c in close:
        pc = ch(c)
        v = pdiv(e2(e1(pc)), e4(e3(abs(pc)))) * 100   # ta.tsi(close, short, long) * 100
        tsi.append(v)
        sig.append(es(v))
    return np.array(tsi, dtype=float), np.array(sig, dtype=float)


class QqeLine:                                        # calculateQQE(rsiLength, smoothingFactor, qqeFactor, source)
    def __init__(self, rsiLength, smoothingFactor, qqeFactor):
        self.wildersLength = rsiLength * 2 - 1
        self.qqeFactor = qqeFactor
        self.rsi, self.e1, self.e2 = Rsi(rsiLength), Ema(smoothingFactor), Ema(self.wildersLength)
        self.cross_long, self.cross_short = Cross(), Cross()
        self.smoothedRsi, self.longBand, self.shortBand, self.trendDirection = [], [], [], []

    def __call__(self, source):
        t = len(self.smoothedRsi)
        rsi = self.rsi(source)
        smoothedRsi = self.e1(rsi)
        self.smoothedRsi.append(smoothedRsi)
        atrRsi = abs(at(self.smoothedRsi, t, 1) - smoothedRsi)
        smoothedAtrRsi = self.e2(atrRsi)
        dynamicAtrRsi = smoothedAtrRsi * self.qqeFactor
        atrDelta = dynamicAtrRsi
        newShortBand = smoothedRsi + atrDelta
        newLongBand = smoothedRsi - atrDelta
        lb1, sb1, s1 = at(self.longBand, t, 1), at(self.shortBand, t, 1), at(self.smoothedRsi, t, 1)
        longBand = pmax(lb1, newLongBand) if (s1 > lb1 and smoothedRsi > lb1) else newLongBand
        shortBand = pmin(sb1, newShortBand) if (s1 < sb1 and smoothedRsi < sb1) else newShortBand
        self.longBand.append(longBand)
        self.shortBand.append(shortBand)
        longBandCross = self.cross_long(lb1, smoothedRsi)
        if self.cross_short(smoothedRsi, sb1):
            trendDirection = 1
        elif longBandCross:
            trendDirection = -1
        else:
            trendDirection = at(self.trendDirection, t, 1)
        self.trendDirection.append(trendDirection)
        qqeTrendLine = longBand if trendDirection == 1 else shortBand
        return qqeTrendLine, smoothedRsi


def vm_qqe(close):
    prim, sec = QqeLine(6, 5, 3.0), QqeLine(6, 5, 1.61)
    bsma, bstd = Sma(50), Stdev(50)
    cols = {k: [] for k in ("tl_p", "rsi_p", "tl_s", "rsi_s", "basis", "upper", "lower", "color", "white")}
    for c in close:
        tl_p, r_p = prim(c)
        tl_s, r_s = sec(c)
        basis = bsma(tl_p - 50)
        dev = 0.35 * bstd(tl_p - 50)
        upper, lower = basis + dev, basis - dev
        if is_na(r_s):
            color = NAN
        elif r_s - 50 > 3.0 and r_p - 50 > upper:
            color = 1.0
        elif r_s - 50 < -3.0 and r_p - 50 < lower:
            color = -1.0
        else:
            color = 0.0
        for k, v in zip(cols, (tl_p, r_p, tl_s, r_s, basis, upper, lower, color, tl_s - 50)):
            cols[k].append(v)
    return {k: np.array(v, dtype=float) for k, v in cols.items()}
