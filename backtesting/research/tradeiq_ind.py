"""
TradeIQ's four RSI replacements and the study's reference lines, ported from their Pine sources (PREREG section 5).

    from backtesting.research import tradeiq_ind as I
    lines = I.compute_all(bars.h, bars.l, bars.c, bars.vol)        # every line the study reads, by name

The plan is ``backtest_results/tradeiq_rsi/PREREG.md`` with ``DEVIATIONS.md``; ``PORTING.md`` there explains each
indicator step by step and how this module was reconciled from two independent ports (port A, whose arithmetic this
module keeps, and port B, kept as the oracle ``tests/tradeiq_oracle.py``). On the 1H, 4H and 1D bars of XAUUSDm and
BTCUSDm up to the hold-out start the two ports and this module give the same floats, bit for bit, on every line from
the first bar, but for the QQE colour on the first six bars, where port B has no value and this module says GRAY
(DEVIATIONS 10).

The scripts (the copies the owner sent; quoted line numbers are theirs)
-----------------------------------------------------------------------
* ``plain_rsi``      TradingView's ``ta.rsi(close, 14)``.
* ``laguerre_rsi``   "Laguerre RSI" (Ehlers; KivancOzbilgic, Pine v5): ``100 * LaRSI``.
* ``vwrsi``          "Volume Weighted Relative Strength Index [AlgoAlpha]" (Pine v5): the RSI line and the
                     consolidation score ``range_score`` (above 0 = chopping) with its histogram ``score * 50``.
* ``bjorgum_tsi``    "Bjorgum TSI" (Pine v5), speed "Fast": ``ta.tsi(close, 5, 25) * 100`` and its signal
                     ``ta.ema(tsi, 14)`` (line 95 of the public script; the owner's copy ends at line 94).
* ``qqe_mod``        "QQE MOD" (Mihkel00; the owner's copy is a Pine v6 rewrite): both smoothed RSIs, bands, trend
                     directions and trend lines, the Bollinger band, the bar colour (BLUE 1 / RED -1 / GRAY 0) and the
                     white line. ``qqe_bands`` (the band and trend logic) and ``qqe_colour`` (the colour rule) are its
                     parts, callable on their own.
* ``ma200``, ``atr14``  ``ta.sma(close, 200)`` and ``ta.atr(14)`` (the stop variant S1).

Pine semantics reproduced
-------------------------
* One value per bar, oldest first; ``x[1]`` (``hist``) is na on the first bar; arithmetic with na is na; a comparison
  with na is false, so ``cond ? a : b`` takes ``b``; ``math.max`` / ``math.min`` of na are na. None of the scripts
  declares ``var``: every ``x = 0.0`` / ``x := ...`` pair is evaluated anew on each bar and ``x[1]`` is the value the
  previous bar ended with.
* The arithmetic follows the order of the "same on pine" code of TradingView's reference: ``ta.sma`` adds
  ``x[i] / length`` from this bar back; ``ta.wma`` weighs ``x[i]`` by ``(length - i) * length``; ``ta.stdev`` is the
  population one around ``ta.sma`` with deviations of at most 1e-10 counted as 0; ``ta.ema`` / ``ta.rma`` update as
  ``alpha * src + (1 - alpha) * prev`` with alpha ``2 / (length + 1)`` / ``1 / length``.
* ``ta.ema`` is seeded with its first value (PREREG 5, TradingView's ``pine_ema``); ``seed="sma"`` gives what
  TradingView's runtime appears to do (na for ``length - 1`` values, then their mean), only to measure that the choice
  changes nothing from 2019 (DEVIATIONS 11). ``ta.rma`` is seeded with the SMA of its first ``length`` values.
* ``ta.hma(x, n) = wma(2 * wma(x, floor(n / 2)) - wma(x, n), floor(sqrt(n)))`` (DEVIATIONS 12).
* ``ta.cross(a, b)``: ``a > b`` differs from the previous bar's ``a > b`` (all four values non-na).
* ``ta.rsi``: 100 when the average loss is 0, 0 when the average gain is 0, else ``100 - 100 / (1 + up / down)``.
* Pine v5 divides two ``const int`` as integers: AlgoAlpha's ``(2/3)`` is 0 (DEVIATIONS 13).
* An na INSIDE a series given to a moving average or a cross (after its first value) raises ``ValueError``:
  TradingView only says such values are "ignored", and the study's inputs never contain one (an hour without a Binance
  kline has volume 0, DEVIATIONS 5). Leading na (the warm-up of whatever is fed in) is handled as Pine does.

Inputs are 1-D sequences (copied to float64, never modified); outputs are float64 arrays of the same length with NaN
where Pine gives na; the cross helpers return bool arrays and the QQE colour an int8 array. Element i depends on bars
0..i only.

First bar with a value (bar 0 = the first bar given): RSI 14 and VWRSI 14; LaRSI 0; consolidation score 45; TSI and
its signal 1; QQE smoothed RSIs 6, bands and trend lines 7, Bollinger band 56 (the colour is GRAY before it exists);
trend directions at their first cross; MA200 199; ATR14 13.
"""

from __future__ import annotations

import math
from typing import Dict, NamedTuple

import numpy as np

__all__ = [
    "BLUE", "RED", "GRAY", "STDEV_EPS",
    "hist", "change", "sma", "math_sum", "wma", "hma", "ema", "rma", "stdev", "rsi", "tsi",
    "crossover", "crossunder", "cross", "true_range", "atr",
    "plain_rsi", "laguerre_rsi", "range_score", "vwrsi", "VWRSI", "bjorgum_tsi", "TSI", "qqe_bands", "QQEBands",
    "qqe_colour", "qqe_mod", "QQE",
    "ma200", "atr14", "compute_all",
]

NAN = math.nan
BLUE, RED, GRAY = 1, -1, 0              # QQE MOD bar colours
STDEV_EPS = 1e-10                       # ta.stdev's reference code: a deviation of at most this counts as 0


# ───────────────────────────── input checks ─────────────────────────────

def _arr(x, name: str = "x") -> np.ndarray:
    a = np.array(x, dtype=np.float64)              # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    return a


def _series_or_level(x, n: int, name: str) -> np.ndarray:
    """A series of length n, or a number standing for a constant series (``ta.crossover(rsi, 30)``)."""
    if np.ndim(x) == 0:
        if n < 0:
            raise ValueError("at least one of the two arguments must be a series")
        return np.full(n, float(x))
    a = _arr(x, name)
    if len(a) != n:
        raise ValueError(f"{name}: {len(a)} values against {n}")
    return a


def _pair_length(a, b) -> int:
    """The length of the series among the two arguments of a cross (-1 when both are numbers)."""
    if np.ndim(a) != 0:
        return len(a)
    return len(b) if np.ndim(b) != 0 else -1


def _length(n, name: str = "length") -> int:
    """A Pine ``length`` argument: an integer >= 1. An integral float (5.0, from ``length/2``) is accepted; a fractional
    one is refused, because what Pine does with it is not documented."""
    if isinstance(n, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {n!r}")
    f = float(n)
    if not (f >= 1.0 and f.is_integer()):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    return int(f)


def _first_valid(a: np.ndarray) -> int:
    ok = np.flatnonzero(~np.isnan(a))
    return int(ok[0]) if ok.size else len(a)


def _leading_na_only(a: np.ndarray, name: str) -> int:
    """The first non-na bar of ``a``; ValueError when an na follows it (see the module docstring)."""
    f = _first_valid(a)
    if f < len(a) and np.isnan(a[f:]).any():
        bad = f + int(np.argmax(np.isnan(a[f:])))
        raise ValueError(f"{name}: na at bar {bad} after the first value at bar {f}; Pine's handling of an na "
                         "inside the series is not ported")
    return f


# ───────────────────────────── Pine helpers (ta.*, math.*) ─────────────────────────────

def hist(x, k: int = 1) -> np.ndarray:
    """The history reference ``x[k]``: the value k bars back, na on the first k bars."""
    a = _arr(x)
    k = int(k)
    if k < 0:
        raise ValueError("x[k] needs k >= 0: Pine cannot look into the future")
    if k == 0:
        return a
    out = np.full(len(a), NAN)
    if k < len(a):
        out[k:] = a[:-k]
    return out


def change(x) -> np.ndarray:
    """``ta.change(x)`` = ``x - x[1]``: na on the first bar and wherever x or x[1] is na."""
    a = _arr(x)
    return a - hist(a, 1)


def _window(y: np.ndarray, n: int, i: int) -> np.ndarray:
    """``y[i]`` (i bars back) for every bar that has a full window of n values: y[n-1-i : len(y)-i]."""
    return y[n - 1 - i:len(y) - i]


def sma(x, length) -> np.ndarray:
    """``ta.sma(x, length)``, as ``pine_sma``: ``sum := sum + x[i] / length`` for i = 0 (this bar) .. length - 1.
    na until ``length`` values exist."""
    a, n = _arr(x), _length(length)
    f = _leading_na_only(a, "ta.sma")
    out = np.full(len(a), NAN)
    y = a[f:]
    if len(y) >= n:
        acc = np.zeros(len(y) - n + 1)
        for i in range(n):
            acc = acc + _window(y, n, i) / n
        out[f + n - 1:] = acc
    return out


def math_sum(x, length) -> np.ndarray:
    """``math.sum(x, length)``: the sum of the last ``length`` values, added from this bar back; na until then."""
    a, n = _arr(x), _length(length)
    f = _leading_na_only(a, "math.sum")
    out = np.full(len(a), NAN)
    y = a[f:]
    if len(y) >= n:
        acc = np.zeros(len(y) - n + 1)
        for i in range(n):
            acc = acc + _window(y, n, i)
        out[f + n - 1:] = acc
    return out


def wma(x, length) -> np.ndarray:
    """``ta.wma(x, length)``, as ``pine_wma``: ``weight = (length - i) * length``, ``norm += weight``,
    ``sum += x[i] * weight`` for i = 0 (this bar) .. length - 1, then ``sum / norm``."""
    a, n = _arr(x), _length(length)
    f = _leading_na_only(a, "ta.wma")
    out = np.full(len(a), NAN)
    y = a[f:]
    if len(y) >= n:
        norm = 0.0
        acc = np.zeros(len(y) - n + 1)
        for i in range(n):
            weight = float((n - i) * n)
            norm = norm + weight
            acc = acc + _window(y, n, i) * weight
        out[f + n - 1:] = acc / norm
    return out


def hma(x, length) -> np.ndarray:
    """``ta.hma(x, length)`` = ``wma(2 * wma(x, floor(length / 2)) - wma(x, length), floor(sqrt(length)))``: the
    formula of TradingView's built-in "Hull Moving Average" script, whose ``length/2`` and ``math.floor(math.sqrt(..))``
    TradingView's own output confirms for odd lengths (DEVIATIONS 12: ``ta.hma(p, 5)`` uses 2 and 2)."""
    n = _length(length)
    if n < 2:
        raise ValueError("ta.hma needs a length of at least 2 (its half length would be 0)")
    a = _arr(x)
    raw = 2.0 * wma(a, n // 2) - wma(a, n)
    return wma(raw, math.isqrt(n))


def _recursion(a: np.ndarray, alpha: float, start: int, seed: float) -> np.ndarray:
    """``out[start] = seed``, then ``alpha * a[t] + (1 - alpha) * out[t - 1]``; na before ``start``."""
    out = np.full(len(a), NAN)
    if start >= len(a):
        return out
    beta = 1.0 - alpha
    prev = float(seed)
    res = [prev]
    for v in a[start + 1:].tolist():
        prev = alpha * v + beta * prev
        res.append(prev)
    out[start:] = res
    return out


def ema(x, length, seed: str = "first") -> np.ndarray:
    """``ta.ema(x, length)``, alpha = 2 / (length + 1). ``seed="first"`` (PREREG 5): ``pine_ema``'s
    ``sum := na(sum[1]) ? src : alpha * src + (1 - alpha) * nz(sum[1])``, so the first non-na value starts it.
    ``seed="sma"``: na until ``length`` values, then their ``ta.sma``, then the same update (what TradingView's
    runtime appears to do; used only to measure that the choice is immaterial, DEVIATIONS 11)."""
    a, n = _arr(x), _length(length)
    f = _leading_na_only(a, "ta.ema")
    alpha = 2.0 / (n + 1.0)
    if seed == "first":
        return _recursion(a, alpha, f, a[f] if f < len(a) else NAN)
    if seed == "sma":
        start = f + n - 1
        return _recursion(a, alpha, start, sma(a, n)[start] if start < len(a) else NAN)
    raise ValueError(f"seed: 'first' or 'sma', got {seed!r}")


def rma(x, length) -> np.ndarray:
    """``ta.rma(x, length)`` (Wilder), as ``pine_rma``: ``sum := na(sum[1]) ? ta.sma(src, length) : alpha * src +
    (1 - alpha) * nz(sum[1])``, alpha = 1 / length: na until ``length`` values, seeded with their SMA."""
    a, n = _arr(x), _length(length)
    f = _leading_na_only(a, "ta.rma")
    start = f + n - 1
    return _recursion(a, 1.0 / n, start, sma(a, n)[start] if start < len(a) else NAN)


def stdev(x, length, biased: bool = True) -> np.ndarray:
    """``ta.stdev(x, length, biased=true)``, as ``pine_stdev``: ``avg = ta.sma(src, length)``; for i = 0 .. length - 1
    the deviation ``src[i] + -avg`` (0 when its magnitude is at most 1e-10, the reference's ``isZero``), squares added
    from this bar back; ``math.sqrt(sum / length)`` (``length - 1`` when not biased). The reference's ``SUM()`` also
    returns 15 for deviations in (1e-10, 1e-4], plainly a documentation slip: not reproduced."""
    a, n = _arr(x), _length(length)
    if not biased and n < 2:
        raise ValueError("the unbiased ta.stdev needs a length of at least 2")
    f = _leading_na_only(a, "ta.stdev")
    out = np.full(len(a), NAN)
    y = a[f:]
    if len(y) >= n:
        avg = sma(y, n)[n - 1:]
        ss = np.zeros(len(y) - n + 1)
        for i in range(n):
            d = _window(y, n, i) + (-avg)
            d = np.where(np.abs(d) <= STDEV_EPS, 0.0, d)
            ss = ss + d * d
        out[f + n - 1:] = np.sqrt(ss / (n if biased else n - 1))
    return out


def _rsi_formula(up: np.ndarray, down: np.ndarray) -> np.ndarray:
    """``down == 0 ? 100 : up == 0 ? 0 : 100 - (100 / (1 + up / down))`` (TradingView's RSI script; AlgoAlpha line 46).
    It differs from the reference's ``pine_rsi`` only when both averages are 0 (100 here, na there)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - (100.0 / (1.0 + up / down))
    return np.where(down == 0.0, 100.0, np.where(up == 0.0, 0.0, r))


def rsi(x, length) -> np.ndarray:
    """``ta.rsi(x, length)``: ``ta.rma`` of the gains ``math.max(x - x[1], 0)`` and of the losses
    ``math.max(x[1] - x, 0)``, combined by ``_rsi_formula``. Valid from bar ``length`` (``length`` changes)."""
    a, n = _arr(x), _length(length)
    ch = change(a)
    with np.errstate(invalid="ignore"):
        up = rma(np.maximum(ch, 0.0), n)
        down = rma(np.maximum(-ch, 0.0), n)
    return _rsi_formula(up, down)


def tsi(x, short_length, long_length, ema_seed: str = "first") -> np.ndarray:
    """``ta.tsi(x, short_length, long_length)`` (in [-1, 1]; the reference gives no formula): TradingView's TSI script,
    ``ta.ema(ta.ema(pc, long), short) / ta.ema(ta.ema(math.abs(pc), long), short)`` with ``pc = ta.change(x)``.
    0 / 0 (no move yet) is na."""
    a = _arr(x)
    s, lg = _length(short_length, "short_length"), _length(long_length, "long_length")
    pc = change(a)
    num = ema(ema(pc, lg, ema_seed), s, ema_seed)
    den = ema(ema(np.abs(pc), lg, ema_seed), s, ema_seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den
    r[den == 0.0] = NAN
    return r


def _cross_inputs(a, b, name: str):
    """The two arguments of a cross as series of one length; a number stands for a constant level. An na inside a
    series is refused: the documented definitions compare with the previous bar, TradingView's runtime (as recorded)
    with the last bar where both were non-na, and the study's lines only ever have leading na."""
    n = _pair_length(a, b)
    x, y = _series_or_level(a, n, "a"), _series_or_level(b, n, "b")
    _leading_na_only(x, name + " (first argument)")
    _leading_na_only(y, name + " (second argument)")
    return n, x, y


def crossover(a, b) -> np.ndarray:
    """``ta.crossover(a, b)``: ``a > b`` on this bar and ``a <= b`` on the previous one (false where any is na).
    Either argument may be a number (a constant level)."""
    n, x, y = _cross_inputs(a, b, "ta.crossover")
    out = np.zeros(n, dtype=bool)
    with np.errstate(invalid="ignore"):
        out[1:] = (x[1:] > y[1:]) & (x[:-1] <= y[:-1])
    return out


def crossunder(a, b) -> np.ndarray:
    """``ta.crossunder(a, b)``: ``a < b`` on this bar and ``a >= b`` on the previous one (false where any is na)."""
    n, x, y = _cross_inputs(a, b, "ta.crossunder")
    out = np.zeros(n, dtype=bool)
    with np.errstate(invalid="ignore"):
        out[1:] = (x[1:] < y[1:]) & (x[:-1] >= y[:-1])
    return out


def cross(a, b) -> np.ndarray:
    """``ta.cross(a, b)`` ("the two series have crossed each other"; no formula in the reference): ``a > b`` on this bar
    differs from ``a > b`` on the previous bar, all four values non-na. It differs from crossover-or-crossunder only
    when a == b exactly on one of the two bars, which never happens in the QQE on the study's bars (DEVIATIONS 14)."""
    n, x, y = _cross_inputs(a, b, "ta.cross")
    out = np.zeros(n, dtype=bool)
    ok = ~(np.isnan(x[1:]) | np.isnan(y[1:]) | np.isnan(x[:-1]) | np.isnan(y[:-1]))
    with np.errstate(invalid="ignore"):
        out[1:] = ok & ((x[1:] > y[1:]) != (x[:-1] > y[:-1]))
    return out


def true_range(high, low, close) -> np.ndarray:
    """``ta.tr(true)``, as ``pine_atr``'s ``na(high[1]) ? high - low : math.max(math.max(high - low,
    math.abs(high - close[1])), math.abs(low - close[1]))``."""
    h, lo, c = _arr(high, "high"), _arr(low, "low"), _arr(close, "close")
    if not len(h) == len(lo) == len(c):
        raise ValueError("high, low, close: series of equal length are expected")
    c1 = hist(c, 1)
    tr = np.maximum(np.maximum(h - lo, np.abs(h - c1)), np.abs(lo - c1))
    if len(tr):
        tr[0] = h[0] - lo[0]
    return tr


def atr(high, low, close, length) -> np.ndarray:
    """``ta.atr(length)`` = ``ta.rma(ta.tr(true), length)``: valid from bar ``length - 1``."""
    return rma(true_range(high, low, close), _length(length))


def _pmax(a: float, b: float) -> float:
    """``math.max(a, b)``: na if either is na."""
    return NAN if (a != a or b != b) else (a if a > b else b)


def _pmin(a: float, b: float) -> float:
    return NAN if (a != a or b != b) else (a if a < b else b)


# ───────────────────────────── the indicators ─────────────────────────────

def plain_rsi(close, length: int = 14) -> np.ndarray:
    """The plain RSI the four replacements are measured against: ``ta.rsi(close, 14)``."""
    return rsi(close, length)


def laguerre_rsi(close, alpha: float = 0.2) -> np.ndarray:
    """Laguerre RSI (Ehlers; KivancOzbilgic's script), the plotted line ``100 * LaRSI`` (line 30), 0..100.

    Lines 10-27 per bar, with ``gamma = 1 - alpha`` and ``nz(L[1])`` = 0 on the first bar:
    ``L0 := (1 - gamma) * src + gamma * nz(L0[1])``; ``L1 := -gamma * L0 + nz(L0[1]) + gamma * nz(L1[1])``; L2 and L3
    alike; ``cu`` / ``cd`` add the positive / negative steps L0-L1, L1-L2, L2-L3; ``temp = cu + cd == 0 ? -1 : cu + cd``;
    ``LaRSI = temp == -1 ? 0 : cu / temp``. ``(1 - gamma)`` is computed as written (0.19999999999999996, not alpha).
    Never na: the filter starts from 0 (a transient that fades as 0.8^n); an na source gives 0, as the ternaries do."""
    src = _arr(close, "close").tolist()
    gamma = 1.0 - float(alpha)
    g1 = 1.0 - gamma
    out = np.empty(len(src))
    p0 = p1 = p2 = p3 = NAN                                 # L0[1] .. L3[1]: na on the first bar
    for i, s in enumerate(src):
        z0 = 0.0 if p0 != p0 else p0
        z1 = 0.0 if p1 != p1 else p1
        z2 = 0.0 if p2 != p2 else p2
        z3 = 0.0 if p3 != p3 else p3
        l0 = g1 * s + gamma * z0
        l1 = -gamma * l0 + z0 + gamma * z1
        l2 = -gamma * l1 + z1 + gamma * z2
        l3 = -gamma * l2 + z2 + gamma * z3
        cu = ((l0 - l1) if l0 > l1 else 0.0) + ((l1 - l2) if l1 > l2 else 0.0) + ((l2 - l3) if l2 > l3 else 0.0)
        cd = ((l1 - l0) if l0 < l1 else 0.0) + ((l2 - l1) if l1 < l2 else 0.0) + ((l3 - l2) if l2 < l3 else 0.0)
        temp = -1.0 if cu + cd == 0 else cu + cd
        out[i] = 100.0 * (0.0 if temp == -1 else cu / temp)
        p0, p1, p2, p3 = l0, l1, l2, l3
    return out


def range_score(src, length: int = 10) -> np.ndarray:
    """AlgoAlpha's consolidation score ``range_score(src, length)`` (lines 15-30), >= 0, above 0 = chopping:

        dir = src > 50 ? 1 : -1                  an na source is not > 50: -1
        t = dir + dir[1] == 0 ? 1 : 0            1 on a bar whose side of 50 differs from the previous bar's
        w = dist / math.sum(dist, length)        dist = 1: na on the first length - 1 bars, then 1 / length
        p = ta.sma(t * w, length)
        v = length / 2                           input int / const int keeps its fraction in v5: 5 for 10
        f = ta.hma(p, v) * (v + ((2/3) * v))     2/3 is const int / const int = 0 in v5, so f = 5 * hma (DEVIATIONS 13)
        math.max(ta.hma(f, length * 2), 0)

    Exactly 0 once the source has kept one side of 50 for 37 bars (the support of a flip). Valid from bar 45 whatever
    the source's na prefix. An odd ``length`` would give ``ta.hma`` a fractional length and is refused. On five BTC bars
    up to the hold-out start the value before the clamp is -2.6e-19 where exact arithmetic gives 0; the clamp makes it
    0, the exact answer, but another order of addition could make it +2.6e-19 (DEVIATIONS 18)."""
    s = _arr(src, "src")
    n = _length(length)
    if n % 2:
        raise ValueError("an odd consolidation length gives ta.hma a fractional length; only even lengths are ported")
    m = len(s)
    with np.errstate(invalid="ignore"):
        direction = np.where(s > 50.0, 1.0, -1.0)
    t = np.zeros(m)
    t[1:] = np.where(direction[1:] + direction[:-1] == 0.0, 1.0, 0.0)
    w = 1.0 / math_sum(np.ones(m), n)
    p = sma(t * w, n)
    v = n / 2
    f = hma(p, v) * (v + (0 * v))
    with np.errstate(invalid="ignore"):
        return np.maximum(hma(f, n * 2), 0.0)


class VWRSI(NamedTuple):
    rsi: np.ndarray            # the RSI line, 0..100 (line 46)
    up: np.ndarray             # pine_vwrma(math.max(ta.change(src), 0), 14) (line 44)
    down: np.ndarray           # pine_vwrma(-math.min(ta.change(src), 0), 14) (line 45)
    score: np.ndarray          # range_score(rsi, 10): > 0 = consolidating
    hist: np.ndarray           # the plotted "Consolidation Strength" columns: score * 50 (line 58)


def vwrsi(close, volume, length: int = 14, range_len: int = 10) -> VWRSI:
    """AlgoAlpha's Volume Weighted RSI (lines 41-46, 58): ``pine_vwrma(x, y) = ta.rma(x * volume, y) /
    ta.rma(volume, y)`` of the gains and of the losses, combined as TradingView's RSI script does, and the consolidation
    score of that RSI. The volume average starts one bar before the gain and loss averages (the change is na on the
    first bar); it divides both, so the line does not depend on it but for rounding. A bar with volume 0 leaves the
    line unchanged. ``volume`` must not contain na (the study's volumes: tick counts, or Binance volume with 0 for an
    hour without a kline, DEVIATIONS 5)."""
    c = _arr(close, "close")
    v = _series_or_level(volume, len(c), "volume")
    if np.isnan(v).any():
        raise ValueError("volume: na is not expected (an hour without a Binance kline has volume 0, DEVIATIONS 5)")
    n = _length(length)
    ch = change(c)
    with np.errstate(invalid="ignore"):
        gain = np.maximum(ch, 0.0)
        loss = -np.minimum(ch, 0.0)
    rv = rma(v, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        up = rma(gain * v, n) / rv
        down = rma(loss * v, n) / rv
    r = _rsi_formula(up, down)
    score = range_score(r, range_len)
    return VWRSI(r, up, down, score, score * 50.0)


class TSI(NamedTuple):
    tsi: np.ndarray            # ta.tsi(close, 5, 25) * 100, -100..100 (zero line)
    signal: np.ndarray         # ta.ema(tsi, 14)


def bjorgum_tsi(close, short: int = 5, long: int = 25, signal: int = 14, ema_seed: str = "first") -> TSI:
    """Bjorgum TSI, speed "Fast" (lines 90-95 of the public script): ``tsi = ta.tsi(close, shortvar, longvar) * 100``
    with short 5 and long 25, and ``tsl = ta.ema(tsi, signalvar)`` with 14. Both valid from bar 1."""
    t = tsi(close, short, long, ema_seed) * 100.0
    return TSI(t, ema(t, signal, ema_seed))


class QQE(NamedTuple):
    rsi: np.ndarray            # ta.rsi(close, 6), shared by the two QQEs (same settings)
    srsi1: np.ndarray          # primaryRSI = ta.ema(ta.rsi(close, 6), 5), 0..100
    long1: np.ndarray          # the primary longBand / shortBand (factor 3.0)
    short1: np.ndarray
    trend1: np.ndarray         # the primary trendDirection: 1, -1, NaN before its first cross
    line1: np.ndarray          # primaryQQETrendLine (0..100 scale)
    srsi2: np.ndarray          # secondaryRSI (equal to srsi1)
    long2: np.ndarray          # the secondary bands (factor 1.61)
    short2: np.ndarray
    trend2: np.ndarray
    line2: np.ndarray          # secondaryQQETrendLine
    bb_basis: np.ndarray       # ta.sma(primaryQQETrendLine - 50, 50)
    bb_upper: np.ndarray       # basis + 0.35 * ta.stdev(primaryQQETrendLine - 50, 50)
    bb_lower: np.ndarray
    color: np.ndarray          # int8: BLUE 1, RED -1, GRAY 0 (neither; also before the band exists)
    white: np.ndarray          # the white line: secondaryQQETrendLine - 50


class QQEBands(NamedTuple):
    long: np.ndarray           # longBand
    short: np.ndarray          # shortBand
    trend: np.ndarray          # trendDirection: 1, -1, NaN before the first cross
    line: np.ndarray           # qqeTrendLine = trendDirection == 1 ? longBand : shortBand


def qqe_bands(smoothed_rsi, delta) -> QQEBands:
    """Lines 43-57 of QQE MOD's ``calculateQQE``, given the smoothed RSI and the band distance ``atrDelta``: the long
    band ratchets up while the RSI stays above it, the short band down while the RSI stays below it; the direction
    turns to 1 when the RSI crosses the previous short band (tested first), to -1 when the previous long band crosses
    the RSI, else keeps its previous value (na before the first cross: the copy has no ``nz``); the trend line is the
    long band in direction 1, else the short band."""
    srsi = _arr(smoothed_rsi, "smoothed_rsi")
    d = _series_or_level(delta, len(srsi), "delta")
    new_short = srsi + d                                             # line 43
    new_long = srsi - d                                              # line 44
    m = len(srsi)
    lb, sb = np.empty(m), np.empty(m)
    sm, nl, ns = srsi.tolist(), new_long.tolist(), new_short.tolist()
    lb1 = sb1 = s1 = NAN                                             # longBand[1], shortBand[1], smoothedRsi[1]
    for i in range(m):
        s = sm[i]
        # line 45: smoothedRsi[1] > longBand[1] and smoothedRsi > longBand[1] ? math.max(longBand[1], newLongBand)
        lv = _pmax(lb1, nl[i]) if (s1 > lb1 and s > lb1) else nl[i]
        # line 46: smoothedRsi[1] < shortBand[1] and smoothedRsi < shortBand[1] ? math.min(shortBand[1], newShortBand)
        sv = _pmin(sb1, ns[i]) if (s1 < sb1 and s < sb1) else ns[i]
        lb[i], sb[i] = lv, sv
        lb1, sb1, s1 = lv, sv, s
    long_cross = cross(hist(lb, 1), srsi)                            # line 47: ta.cross(longBand[1], smoothedRsi)
    short_cross = cross(srsi, hist(sb, 1))                           # line 49: ta.cross(smoothedRsi, shortBand[1])
    trend = np.empty(m)
    td = NAN                                                         # trendDirection[1] on the first bar: na
    for i in range(m):                                               # lines 49-54: the short-band cross is tested first
        if short_cross[i]:
            td = 1.0
        elif long_cross[i]:
            td = -1.0
        trend[i] = td                                                # else trendDirection := trendDirection[1]
    line = np.where(trend == 1.0, lb, sb)                            # line 57: na == 1 is false -> shortBand
    return QQEBands(lb, sb, trend, line)


def _qqe_line(close: np.ndarray, rsi_length, smoothing, factor: float, ema_seed: str):
    """``calculateQQE(rsiLength, smoothingFactor, qqeFactor, source)``, lines 28-58 of QQE MOD."""
    n = _length(rsi_length, "rsi_length")
    wilders_length = n * 2 - 1                                       # line 29
    r = rsi(close, n)                                                # line 30
    srsi = ema(r, smoothing, ema_seed)                               # line 31
    atr_rsi = np.abs(hist(srsi, 1) - srsi)                           # line 32: math.abs(smoothedRsi[1] - smoothedRsi)
    delta = ema(atr_rsi, wilders_length, ema_seed) * float(factor)   # lines 33-34, 42
    b = qqe_bands(srsi, delta)
    return r, srsi, b.long, b.short, b.trend, b.line


def qqe_mod(close, rsi_length_primary: int = 6, rsi_smoothing_primary: int = 5, qqe_factor_primary: float = 3.0,
            rsi_length_secondary: int = 6, rsi_smoothing_secondary: int = 5, qqe_factor_secondary: float = 1.61,
            threshold_secondary: float = 3.0, bollinger_length: int = 50, bollinger_multiplier: float = 0.35,
            ema_seed: str = "first") -> QQE:
    """QQE MOD (the owner's v6 copy) with its defaults: the primary and secondary QQE (lines 62, 65), the Bollinger
    band on the primary trend line - 50 (lines 68-71) and the bar colour of the plan (PREREG 5), which is the script's
    "QQE Up Signal" / "QQE Down Signal" columns (lines 85-86):
    BLUE when ``secondaryRSI - 50 > 3 and primaryRSI - 50 > bollingerUpper``, RED when ``secondaryRSI - 50 < -3 and
    primaryRSI - 50 < bollingerLower``, GRAY otherwise (also on the bars before the band exists, where the comparisons
    are with na). The white line is ``secondaryQQETrendLine - 50`` (line 81). The primary threshold input is unused by
    the script and is not a parameter here."""
    c = _arr(close, "close")
    r, s1, lb1, sb1, tr1, ln1 = _qqe_line(c, rsi_length_primary, rsi_smoothing_primary, qqe_factor_primary, ema_seed)
    _, s2, lb2, sb2, tr2, ln2 = _qqe_line(c, rsi_length_secondary, rsi_smoothing_secondary, qqe_factor_secondary,
                                          ema_seed)
    x = ln1 - 50.0
    basis = sma(x, bollinger_length)
    dev = float(bollinger_multiplier) * stdev(x, bollinger_length)
    upper = basis + dev
    lower = basis - dev
    color = qqe_colour(s1, s2, upper, lower, threshold_secondary)
    return QQE(r, s1, lb1, sb1, tr1, ln1, s2, lb2, sb2, tr2, ln2, basis, upper, lower, color, ln2 - 50.0)


def qqe_colour(primary_rsi, secondary_rsi, bollinger_upper, bollinger_lower, threshold: float = 3.0) -> np.ndarray:
    """The plan's QQE bar colour (PREREG 5), the conditions of the "QQE Up Signal" / "QQE Down Signal" columns
    (lines 85-86): BLUE where ``secondaryRSI - 50 > threshold and primaryRSI - 50 > bollingerUpper``, RED where
    ``secondaryRSI - 50 < -threshold and primaryRSI - 50 < bollingerLower`` (both strict), GRAY elsewhere, also where a
    value is na (a comparison with na is false). int8."""
    p50 = _arr(primary_rsi, "primary_rsi") - 50.0
    s50 = _series_or_level(secondary_rsi, len(p50), "secondary_rsi") - 50.0
    upper = _series_or_level(bollinger_upper, len(p50), "bollinger_upper")
    lower = _series_or_level(bollinger_lower, len(p50), "bollinger_lower")
    th = float(threshold)
    with np.errstate(invalid="ignore"):
        blue = (s50 > th) & (p50 > upper)
        red = (s50 < -th) & (p50 < lower)
    return np.where(blue, BLUE, np.where(red, RED, GRAY)).astype(np.int8)


def ma200(close, length: int = 200) -> np.ndarray:
    """The 200-period simple moving average of the close, ``ta.sma(close, 200)``: valid from bar 199."""
    return sma(close, length)


def atr14(high, low, close, length: int = 14) -> np.ndarray:
    """Wilder's ATR(14), ``ta.atr(14)``, for the stop variant S1: valid from bar 13 (the first true range is
    high - low). ``tradeiq_market.s1_stop`` computes the same quantity with ``external.wilder_atr``, whose update
    order differs; the two agree to about 1e-16 relative, so a study should take the stop from one of them only."""
    return atr(high, low, close, length)


def compute_all(high, low, close, volume, ema_seed: str = "first") -> Dict[str, np.ndarray]:
    """Every line the study reads, with the scripts' defaults, by name."""
    c = _arr(close, "close")
    vw = vwrsi(c, volume)
    ts = bjorgum_tsi(c, ema_seed=ema_seed)
    q = qqe_mod(c, ema_seed=ema_seed)
    return {
        "rsi": plain_rsi(c),
        "larsi": laguerre_rsi(c),
        "vwrsi": vw.rsi,
        "vwrsi_score": vw.score,
        "vwrsi_hist": vw.hist,
        "tsi": ts.tsi,
        "tsi_signal": ts.signal,
        "qqe_srsi1": q.srsi1,
        "qqe_srsi2": q.srsi2,
        "qqe_line1": q.line1,
        "qqe_line2": q.line2,
        "qqe_bb_basis": q.bb_basis,
        "qqe_bb_upper": q.bb_upper,
        "qqe_bb_lower": q.bb_lower,
        "qqe_color": q.color,
        "qqe_white": q.white,
        "ma200": ma200(c),
        "atr14": atr14(high, low, c),
    }
