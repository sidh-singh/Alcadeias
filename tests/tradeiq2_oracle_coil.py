"""
The oracle of ``backtesting/research/tradeiq2_ind_coil.py``: PORT B of the coil breakout (COIL) of TradeIQ study 2
(``backtest_results/tradeiq_2027/PREREG.md`` section 6.9, l.434-465).

What this is
------------
TradeIQ's "Coil Breakout AI" is private and has no source (PREREG l.18-19, 26). The rule is the study's own and is
defined by PREREG 6.9 alone: the squeeze (l.442), the coil and its box (l.443), the armed window (l.444), the breakout
(l.445) and the ADX grade (l.461); plus the contract the two ports share (below), which makes 6.9 precise. Its Pine
parts are TradingView built-ins, transcribed here from TradingView's reference text (the "same on Pine" code of
``ta.sma``, ``ta.stdev``, ``ta.rma``, ``ta.atr`` and the definition of ``ta.tr``) and, for ``ta.dmi``, whose reference
gives no code, from TradingView's built-in "Directional Movement Index" indicator script, which computes the same
triple (+DI, -DI, ADX). Third-party code is described and cited by its identifiers, never copied.

This is a literal, bar-by-bar transcription in plain Python (no numpy in the bar loops, no numba), written to be
obviously correct rather than fast; it was written from PREREG 6.9 and the contract only, without seeing port A. Pine
runs a script once per bar, oldest bar first; here each Pine call site of a built-in is one object (``Sma``,
``Stdev``, ``Rma``, ``TrueRange``, ``Change``, ``Fixnan``) called once per bar, which keeps what that call site keeps
in Pine, and each ``var`` variable of the rule is one Python variable that keeps its value from bar to bar. Python
floats are IEEE-754 doubles, as Pine's are, and every sum is formed in the order of the reference code, so the
numbers are the reference's to the last bit (they equal study 1's verified primitives, ``tests/tradeiq_oracle.py``,
bit for bit; tested).

Pine semantics used: the history of a series before bar 0 is na (``x[1]`` is na on bar 0); arithmetic with na gives
na; a comparison with na is false (so an ``and`` of comparisons is false while any band is na); ``nz(x)`` is 0 for na.

The contract (identical in both ports, compared key by key)
-----------------------------------------------------------
``coil(o, h, l, c, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5, min_bars=6, armed_bars=12)`` returns a dict of
per-bar arrays of len(bars), bar 0 = the first bar given (``KEYS``). The inputs are the chart's bid OHLC, oldest
first. The open is not read by the rule (it is in the signature so that both ports take the same bars); volume is not
read either (the VOL grade, PREREG l.460, is the study's, at the breakout bar).

==========  =======  ===================================================================================================
key         dtype    value at bar t
==========  =======  ===================================================================================================
squeeze_on  bool     ``(basis + dev < ma + kc_mult * atr) and (basis - dev > ma - kc_mult * atr)`` with ``basis =
                     ta.sma(close, bb_len)``, ``dev = bb_mult * ta.stdev(close, bb_len)`` (population), ``ma =
                     ta.sma(close, kc_len)`` and ``atr = ta.atr(kc_len)`` (PREREG l.442). False while a band is na
                     (bars 0 .. max(bb_len, kc_len) - 2: 0-18 with the defaults)
run_len     int64    the number of consecutive squeeze_on bars ending at bar t; 0 when squeeze_on is False
armed       bool     a coil is armed at bar t: its run (>= min_bars squeeze bars, PREREG l.443) ended on an earlier
                     bar e, t is one of the bars e + 1 .. e + armed_bars (l.444), and the coil has neither broken out
                     on a bar before t nor been replaced on a bar at or before t (readings 1-4). The breakout bar
                     itself is armed (reading 1)
box_hi      float64  the armed coil's box at the armed bars: the highest high and the lowest low of ALL the bars of
box_lo               its run (l.443; reading 5); NaN where ``armed`` is False
breakout    int8     +1 at the first armed bar whose close is > box_hi, -1 at the first whose close is < box_lo
                     (strict, l.445), else 0; at most once per coil
bo_box_hi   float64  the broken coil's box at the breakout bars (equal to box_hi / box_lo there); NaN elsewhere
bo_box_lo
adx         float64  ``adx(h, l, c)``: Pine ``ta.dmi(14, 14)``'s ADX (PREREG l.461); NaN on bars 0-26 (reading 11)
==========  =======  ===================================================================================================

``adx(h, l, c, di_len=14, adx_len=14)`` returns that ADX alone as a float64 array.

Helpers outside the compared contract (they keep the tests readable): ``squeeze_lines`` (the bands and squeeze_on),
``coil_from_squeeze`` (the coil logic on a given squeeze series: the bar loop ``coil`` uses), ``dmi`` (the full
``ta.dmi`` triple) and the Pine call-site classes.

The rule, as transcribed (one pass per bar t, in this order)
-------------------------------------------------------------
::

    squeeze_on = (basis + dev < ma + kc) and (basis - dev > ma - kc)        kc = kc_mult * ta.atr(kc_len)
    run_len    = squeeze_on ? run_len[1] + 1 : 0
    run box    = squeeze_on ? (run_len == 1 ? (high, low) : (max(run_hi[1], high), min(run_lo[1], low))) : (na, na)
    if squeeze_on and run_len == min_bars:      a newer run became a coil: the armed coil, if any, is dropped
    if not squeeze_on and run_len[1] >= min_bars:      the run ended on bar t - 1: its coil is armed from bar t
        box = run box[1], count = 0
    if a coil is armed:                         armed[t] = True; count += 1 (bar t is its count-th armed bar)
        breakout = close > box_hi ? +1 : close < box_lo ? -1 : 0
        if breakout != 0 or count == armed_bars:   the coil is disarmed after bar t (used, or its window is over)

What is known when (no look-ahead)
----------------------------------
Every value at bar t is computed from bars 0 .. t only and is final at bar t's close; nothing is ever revised (no
``request.security``, no pivots, no future bar). A coil's box is complete at the close of its run's last squeeze bar
e, but that e was the last one is known only at the close of bar e + 1 (the first bar whose bands are no longer
inside the channel), which is why the coil is armed from bar e + 1 and why that bar's own close is already tested.
A run still open at the last bar given is not armed (not known to have ended). The breakout at bar t is known at bar
t's close, when the study decides (PREREG l.96-97: it fills at the next M1 open). ``tests/test_tradeiq2_ind_coil_b.py``
checks this by truncation: the outputs up to bar T do not change when the bars after T are removed.

The readings (each one is a choice; the alternative is named, and whether it can change a signal on our bars)
---------------------------------------------------------------------------------------------------------------
Measured on study 1's 1H / 4H / 1D bars of both symbols from the data start to 2024-06-30 (indicator values and event
counts only; no rule was run): see ``MEASURED`` at the end of this docstring for the numbers.

1. The breakout bar is armed (``armed`` and ``box_*`` hold there, equal to ``bo_box_*``); the coil is disarmed after
   it. Alternative: ``armed`` False on the breakout bar (the state after the bar). It changes ``armed`` / ``box_*``
   on breakout bars only, never ``breakout`` or ``bo_box_*``: it cannot change a signal.
2. Replacement (l.444, "until a new coil replaces it"): a newer run replaces the armed coil on the bar on which its
   run_len reaches min_bars, BEFORE that bar's close is tested, so the old coil is not armed on that bar and cannot
   break out on it. Why: ``armed[t]`` is a function of the squeeze series up to and including bar t, as on the first
   armed bar (armed because squeeze_on[t] is False), and only then is close[t] tested. Alternative: test the old box
   on that bar first, then replace. It differs only when the newer run's min_bars-th bar (a squeeze bar) closes
   outside the old box: see ``MEASURED``.
3. A newer run that has not (yet) reached min_bars does not touch the armed coil: its squeeze bars are armed bars,
   they count towards the armed_bars window and they can be breakout bars. Alternative: any new squeeze bar disarms
   the coil, or only non-squeeze bars can break out. The contract says "until a newer run reaches min_bars"; how
   often a breakout falls on a squeeze bar is in ``MEASURED``.
4. The window: armed on bars e + 1 .. e + armed_bars, every bar counted (squeeze bars of a shorter newer run
   included), e + 1 being the first non-squeeze bar after the run; a breakout on the 12th armed bar counts, on the
   13th not. Alternatives: count only non-squeeze bars, or start the count at the run's min_bars-th bar. Both would
   change signals; the contract fixes this reading.
5. The box spans ALL the bars of the run (a run longer than min_bars widens it), only those bars (the first armed
   bar is not in it), highs and lows (not closes). Alternatives: the first or the last min_bars bars, or closes. Each
   would change signals; the contract fixes this reading.
6. Strict comparisons: ``close > box_hi`` / ``close < box_lo`` (a close exactly at an edge is no breakout) and the
   bands strictly inside the channel (``<`` / ``>``: bands touching the channel, e.g. sd = atr = 0 on flat bars, is no
   squeeze). Alternative: ``>=`` / ``<=``. Ties of the close with an edge on an armed bar do occur on our bars (both
   symbols quote to fixed decimals); their count is in ``MEASURED``. A tie of the bands is practically impossible
   with real ranges.
7. ``ta.stdev`` with its default ``biased = true``: the population deviation (divides by the length), around
   ``ta.sma``, with the reference's ``SUM()`` zeroing of a deviation at or below 1e-10 (its 1e-4 branch returning 15
   is a documentation slip and is not copied; study 1's PORTING.md item 7). Alternative: the sample deviation
   (pandas' default, n - 1): it narrows the squeeze and changes signals (``MEASURED``).
8. The channel width: ``ta.atr(kc_len)`` = ``ta.rma(ta.tr(true), kc_len)``: Wilder's RMA with alpha = 1/20, seeded on
   bar 19 with the simple mean of the first 20 true ranges, the first of which is high - low (``ta.tr(true)``; the
   reference's ``pine_atr``), PREREG l.135 and l.442. Its basis is ``ta.sma(close, kc_len)``, the same series as the
   Bollinger basis with the defaults. Alternatives: the classic TTM/LazyBear squeeze's SMA of the true range, or
   Pine's ``ta.kc`` (EMA basis, EMA of the range). Each changes signals (``MEASURED`` for the SMA).
9. The squeeze is evaluated literally, as two band comparisons. With equal bases it reduces to ``bb_mult * sd <
   kc_mult * atr`` in exact arithmetic; the two can differ only when the two sides are within an ulp of the basis
   (``MEASURED``).
10. The RMAs start at the first bar given (with study 1's loader gold's first bar opens 2017-01-03 00:00 UTC, BTC's
    2018-01-01 00:00): TradingView would start them at its own first bar. The difference decays as (19/20)^n for the
    ATR(20) and (13/14)^n for the DMI: by 2019 it is below the last bit on 1H and 4H, and on 1D a relative trace of
    order 1e-10 (gold) to 1e-7 (BTC) remains, which could flip a squeeze only that close to a tie (``MEASURED``: the
    closest approach is 4e-6 of the ATR, and a later start changes nothing).
11. ``ta.dmi(di_len, adx_len)``, from the built-in DMI script: ``up = ta.change(high)``, ``down = -ta.change(low)``
    (na on bar 0, so +DM / -DM are na there, not 0); ``plusDM = up > down and up > 0 ? up : 0`` and the mirror (a tie
    up == down gives 0 to both); ``trur = ta.rma(ta.tr, di_len)`` with ``ta.tr`` = ``ta.tr(false)``, na on bar 0;
    ``plus = fixnan(100 * ta.rma(plusDM, di_len) / trur)`` (left to right: (100 * rma) / trur), ``minus`` alike;
    ``adx = 100 * ta.rma(math.abs(plus - minus) / (sum == 0 ? 1 : sum), adx_len)`` with ``sum = plus + minus``. So
    +DM, -DM and the true range all start on bar 1, their RMAs on bar di_len (14), DX on bar 14 and the ADX on bar
    di_len + adx_len - 1 = 27. Alternatives: ``ta.tr(true)`` for trur (as ``ta.atr``): +DI and -DI change, but DX is
    a ratio in which trur cancels, so the ADX changes only in its last bits (``MEASURED``); DX in percent before the
    RMA (TradingView's help-centre wording): equal in exact arithmetic, last bits only. Neither can change ADX >= 20
    except at an exact tie.
12. ``fixnan`` (+DI / -DI): it replaces an na by the last value; the only na after bar 13 is 0 / 0 when trur is 0,
    i.e. when every true range so far is 0 (flat bars from the start). Never on our bars. A zero divisor gives na
    (Pine): only 0 / 0 can occur, because +DM and -DM never exceed the true range.
13. A missing price (NaN, inf) is refused (``ValueError``): Pine's handling of an na price inside the series is not
    ported, and our bars have none.

MEASURED
--------
Study 1's bars through its guarded loader (``tradeiq_market.load(symbol, end="2024-07-01").tbars(tf)``, guard closed),
indicator values and event counts only, 28 Nov 2026. Bars: gold 1H 44,190, 4H 11,955, 1D 1,932 (from 2017-01-03);
BTC 1H 56,840, 4H 14,225, 1D 2,372 (from 2018-01-01). The oracle takes 0.7 s on gold 1H and 1.2 s on BTC 1H.

Events of bars closing in 2019-2022 (close time in [2019-01-01, 2023-01-01) UTC). A coil is counted by its first
armed bar and ends in a breakout, an expiry (12 armed bars) or a replacement:

=======  ==========  ===========  ==============  =======  ========  ===============  ===============  ==============
series   squeeze     coils armed  breakouts L/S   expired  replaced  on armed bar 1   on armed bar 12  on a squeeze
         bars                                                                                          bar (reading 3)
=======  ==========  ===========  ==============  =======  ========  ===============  ===============  ==============
gold 1H  6,983       430          193 / 145       69       23        187              7                11
gold 4H  1,634       91           47 / 28         12       4         25               1                1
gold 1D  291         16           8 / 7           1        0         8                0                0
BTC 1H   14,324      707          275 / 246       122      64        289              12               19
BTC 4H   2,915       161          72 / 57         26       6         72               3                6
BTC 1D   484         27           14 / 9          2        2         11               1                2
=======  ==========  ===========  ==============  =======  ========  ===============  ===============  ==============

The readings, measured over the whole span to 2024-06-30 unless a window is named:

- Reading 2 (the replacement bar): the alternative (test the old box first) adds a breakout on 7 replacement bars
  whose close lies outside the old box: BTC 1H 5 in 2019-2022 (2021-09-18 05:00 long, 2022-03-03 16:00 short,
  2022-09-30 15:00 long, 2022-10-07 07:00 short, 2022-11-28 00:00 short; bar close times UTC), BTC 1D 1 in
  2019-2022 (2022-08-20 short), gold 1H 1 in 2023-2024H1 (2023-06-07 14:00 long); none on gold 4H / 1D or BTC 4H.
  It CAN change signals.
- Reading 6 (ties): a close exactly at a box edge on an armed bar: none from 2019 on any series; before 2019 one on
  gold 1H and one on gold 4H, where ``>=`` would change 2 and 1 breakout bars (2017-2018: warm-up here, the gold
  Early exam's window later).
- Reading 7 (sample stdev): 2019-2022 squeeze bars that change: gold 514 / 122 / 15 (1H / 4H / 1D), BTC 697 / 190 / 40;
  breakout bars that change: gold 85 / 18 / 2, BTC 119 / 27 / 9.
- Reading 8 (an SMA of the true range for the channel): squeeze bars that change: gold 1,672 / 332 / 39, BTC 2,501 /
  571 / 155; breakout bars: gold 272 / 42 / 10, BTC 332 / 96 / 19.
- Reading 9 (two band comparisons against ``dev < kc_mult * atr``): no bar differs on any series.
- Reading 10: the closest approach of a band to the channel from 2019, as a share of the ATR: gold 4.2e-5 / 2.1e-4 /
  8.0e-4, BTC 3.5e-5 / 8.5e-5 / 4.0e-6. Starting the bars 2,000 / 500 / 100 bars later leaves the ATR from 2019
  bit-identical on 1H and 4H and within 5.1e-11 (gold 1D) and 6.2e-7 (BTC 1D) relative; no squeeze or breakout from
  2019 changes.
- Reading 11: ``ta.tr(true)`` for trur leaves the ADX from 2019 bit-identical on five series and within 1.4e-14 on BTC
  1D; DX in percent before the RMA moves it by at most 5.7e-14. Neither changes ``adx >= 20`` on any bar from 2019;
  the ADX comes closest to 20 at 1.5e-4 (BTC 4H). The ADX first exists on bar 27 on all six series.
- Reading 12 (fixnan): trur is never 0 after bar 13 on our bars; fixnan never acts.

Reconciliation with port A (28 Nov 2026)
----------------------------------------
``tests/test_tradeiq2_ind_coil.py`` runs both ports on the study's 1H / 4H / 1D bars of both symbols (gold from
2016-01-03, BTC from 2018-01-01, to 2024-06-30), on gold from study 1's start (2017-01-03, the bars measured above),
on synthetic bars with random inputs and short series, and on every hand case of either port's own tests: every key is
equal bit for bit. No mismatch was found and the arithmetic needed no change (both follow the reference code's order).
Reading 1 (the breakout bar is armed) and reading 2 (the replacement bar) are port A's readings too. The study's bars
give the same values as the bars measured above on every bar closing from 2019, but for the last bit of ten 1D ADX
values. Notes: ``backtest_results/tradeiq_2027/porting/coil.md``.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

__all__ = [
    "coil", "adx", "dmi", "squeeze_lines", "coil_from_squeeze",
    "Sma", "Stdev", "Rma", "TrueRange", "Atr", "Change", "Fixnan", "pdiv", "is_na",
    "KEYS", "DTYPES", "LINE_KEYS",
]

NAN = float("nan")

KEYS = ("squeeze_on", "run_len", "armed", "box_hi", "box_lo", "breakout", "bo_box_hi", "bo_box_lo", "adx")
DTYPES = {"squeeze_on": np.bool_, "run_len": np.int64, "armed": np.bool_, "box_hi": np.float64,
          "box_lo": np.float64, "breakout": np.int8, "bo_box_hi": np.float64, "bo_box_lo": np.float64,
          "adx": np.float64}
# squeeze_lines' series (not part of the compared contract)
LINE_KEYS = ("basis", "dev", "ma", "atr", "upper_bb", "lower_bb", "upper_kc", "lower_kc")


# ───────────────────────────── Pine values ─────────────────────────────

def is_na(x) -> bool:
    """Pine's ``na(x)`` for a float: NaN is the only na value here."""
    return x != x


def pdiv(a: float, b: float) -> float:
    """Pine's ``a / b``: na when an operand is na or the divisor is 0 (reading 12)."""
    if is_na(a) or is_na(b) or b == 0:
        return NAN
    return a / b


# ───────────────────────────── Pine call sites (one object per call site, called once per bar) ─────────────────────

class Sma:
    """``ta.sma(x, n)``: the reference's ``pine_sma``: ``sum := sum + x[i] / n`` for i = 0 (this bar) .. n - 1, so each
    term is divided by n before it is added, newest first. na while fewer than n bars exist or any of the last n
    values is na (a leading na delays the first value: the same as "na values are ignored" for a leading na)."""

    def __init__(self, n: int):
        self.n = n
        self.src: List[float] = []

    def push(self, x: float) -> None:
        self.src.append(x)

    def value(self) -> float:
        n = self.n
        if len(self.src) < n:
            return NAN
        s = 0.0
        for i in range(n):
            v = self.src[-1 - i]                      # x[i]
            if is_na(v):
                return NAN
            s = s + v / n
        return s

    def __call__(self, x: float) -> float:
        self.push(x)
        return self.value()


class Stdev:
    """``ta.stdev(x, n)`` with ``biased = true`` (population): the reference's ``pine_stdev``: ``avg = ta.sma(x, n)``;
    for i = 0 .. n - 1: ``d = SUM(x[i], -avg)``, where ``SUM`` returns 0 when ``|x[i] + (-avg)| <= 1e-10`` (its
    ``isZero``); ``ss := ss + d * d``; result ``math.sqrt(ss / n)``. The reference's 1e-4 branch, which returns 15, is
    not copied (reading 7)."""

    def __init__(self, n: int):
        self.n = n
        self.src: List[float] = []
        self.sma = Sma(n)                             # ta.stdev's own ta.sma call

    def __call__(self, x: float) -> float:
        self.src.append(x)
        avg = self.sma(x)
        if is_na(avg):
            return NAN
        ss = 0.0
        for i in range(self.n):
            d = self.src[-1 - i] + (-avg)             # SUM(src[i], -avg)
            if abs(d) <= 1e-10:                       # isZero(res, 1e-10) -> 0
                d = 0.0
            ss = ss + d * d
        return math.sqrt(ss / self.n)


class Rma:
    """``ta.rma(x, n)``: the reference's ``pine_rma``: alpha = 1 / n; ``sum := na(sum[1]) ? ta.sma(x, n) : alpha * x +
    (1 - alpha) * nz(sum[1])``. The SMA seed is evaluated only while ``sum[1]`` is na (its value is used only then);
    its source history is kept on every bar, so the seed is the SMA of the last n values, as in Pine."""

    def __init__(self, n: int):
        self.alpha = 1 / n
        self.sma = Sma(n)
        self.prev = NAN                               # sum[1]

    def __call__(self, x: float) -> float:
        self.sma.push(x)
        if is_na(self.prev):
            v = self.sma.value()
        else:
            v = self.alpha * x + (1 - self.alpha) * self.prev
        self.prev = v
        return v


class TrueRange:
    """``ta.tr(handle_na)``: ``max(max(high - low, |high - close[1]|), |low - close[1]|)``; on bar 0 (close[1] na) it
    is ``high - low`` with ``handle_na = true`` (the reference's ``pine_atr``) and na with ``handle_na = false`` (the
    variable ``ta.tr``, which the DMI script reads)."""

    def __init__(self, handle_na: bool):
        self.handle_na = bool(handle_na)
        self.prev_close = NAN                         # close[1]

    def __call__(self, high: float, low: float, close: float) -> float:
        pc = self.prev_close
        if is_na(pc):
            v = (high - low) if self.handle_na else NAN
        else:
            a = high - low
            b = abs(high - pc)
            v = a if a >= b else b                    # math.max(high - low, math.abs(high - close[1]))
            d = abs(low - pc)
            v = v if v >= d else d                    # math.max(., math.abs(low - close[1]))
        self.prev_close = close
        return v


class Atr:
    """``ta.atr(n)`` = ``ta.rma(ta.tr(true), n)`` (the reference's ``pine_atr``)."""

    def __init__(self, n: int):
        self.tr = TrueRange(handle_na=True)
        self.rma = Rma(n)

    def __call__(self, high: float, low: float, close: float) -> float:
        return self.rma(self.tr(high, low, close))


class Change:
    """``ta.change(x)`` = x - x[1]; na on bar 0."""

    def __init__(self):
        self.prev = NAN

    def __call__(self, x: float) -> float:
        v = x - self.prev
        self.prev = x
        return v


class Fixnan:
    """``fixnan(x)``: x, or the last non-na value of x when x is na (na while there is none)."""

    def __init__(self):
        self.last = NAN

    def __call__(self, x: float) -> float:
        if not is_na(x):
            self.last = x
        return self.last


# ───────────────────────────── input checks ─────────────────────────────

def _prices(arrays: Sequence, names: Sequence[str]) -> List[List[float]]:
    """The price arrays as Python lists of floats (copies: the inputs are never changed); 1-D, equal lengths, finite."""
    out = []
    n = None
    for name, x in zip(names, arrays):
        a = np.asarray(x, dtype=np.float64)
        if a.ndim != 1:
            raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
        if n is None:
            n = a.size
        elif a.size != n:
            raise ValueError(f"{name}: {a.size} bars, the other prices have {n}")
        if not bool(np.all(np.isfinite(a))):
            raise ValueError(f"{name}: NaN or inf at bar {int(np.argmin(np.isfinite(a)))}; Pine's handling of an na "
                             "price is not ported (reading 13)")
        out.append([float(v) for v in a.tolist()])
    return out


def _length(x, name: str) -> int:
    """A Pine length / count input: an integer >= 1 (an integral float is accepted)."""
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: an integer is expected")
    f = float(x)
    if not math.isfinite(f) or f != math.floor(f) or f < 1:
        raise ValueError(f"{name}: an integer >= 1 is expected, got {x!r}")
    return int(f)


def _mult(x, name: str) -> float:
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected")
    f = float(x)
    if not math.isfinite(f) or f < 0:
        raise ValueError(f"{name}: a finite number >= 0 is expected, got {x!r}")
    return f


def _flags(x, n: int, name: str) -> List[bool]:
    a = np.asarray(x)
    if a.ndim != 1 or a.size != n:
        raise ValueError(f"{name}: a 1-D array of {n} values is expected, got shape {a.shape}")
    if a.dtype != np.bool_:
        if not bool(np.all((a == 0) | (a == 1))):
            raise ValueError(f"{name}: booleans (or 0 / 1) are expected")
    return [bool(v) for v in a.tolist()]


# ───────────────────────────── the squeeze (PREREG l.442) ─────────────────────────────

def squeeze_lines(h, l, c, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5) -> Dict[str, np.ndarray]:
    """The Bollinger bands, the Keltner channel and ``squeeze_on``, bar by bar (``LINE_KEYS`` + ``squeeze_on``):

        basis = ta.sma(close, bb_len)          dev = bb_mult * ta.stdev(close, bb_len)
        ma    = ta.sma(close, kc_len)          atr = ta.atr(kc_len)
        upper_bb = basis + dev, lower_bb = basis - dev, upper_kc = ma + kc_mult * atr, lower_kc = ma - kc_mult * atr
        squeeze_on = upper_bb < upper_kc and lower_bb > lower_kc        (false while any of them is na)
    """
    H, L, C = _prices((h, l, c), ("h", "l", "c"))
    n_bb, n_kc = _length(bb_len, "bb_len"), _length(kc_len, "kc_len")
    m_bb, m_kc = _mult(bb_mult, "bb_mult"), _mult(kc_mult, "kc_mult")
    basis_site, dev_site = Sma(n_bb), Stdev(n_bb)           # the call sites, one object each
    ma_site, atr_site = Sma(n_kc), Atr(n_kc)
    out: Dict[str, list] = {k: [] for k in LINE_KEYS + ("squeeze_on",)}
    for t in range(len(C)):
        close = C[t]
        basis = basis_site(close)
        dev = m_bb * dev_site(close)
        ma = ma_site(close)
        atr = atr_site(H[t], L[t], close)
        upper_bb = basis + dev
        lower_bb = basis - dev
        upper_kc = ma + m_kc * atr
        lower_kc = ma - m_kc * atr
        sq = (upper_bb < upper_kc) and (lower_bb > lower_kc)        # a comparison with na is false
        for k, v in zip(LINE_KEYS, (basis, dev, ma, atr, upper_bb, lower_bb, upper_kc, lower_kc)):
            out[k].append(v)
        out["squeeze_on"].append(sq)
    res = {k: np.array(out[k], dtype=np.float64) for k in LINE_KEYS}
    res["squeeze_on"] = np.array(out["squeeze_on"], dtype=np.bool_)
    return res


# ───────────────────────────── the coil, its box, the armed window and the breakout (PREREG l.443-445) ─────────────

def coil_from_squeeze(squeeze_on, h, l, c, min_bars=6, armed_bars=12) -> Dict[str, np.ndarray]:
    """The coil logic on a given squeeze series (the bar loop ``coil`` runs on ``squeeze_lines``' squeeze_on). Returns
    the contract's keys but ``adx``. See the module docstring ("The rule, as transcribed") and readings 1-6."""
    H, L, C = _prices((h, l, c), ("h", "l", "c"))
    n = len(C)
    SQ = _flags(squeeze_on, n, "squeeze_on")
    minBars = _length(min_bars, "min_bars")
    armedBars = _length(armed_bars, "armed_bars")

    # the rule's var state
    runLen = 0                  # consecutive squeeze bars ending at the current bar
    runHi = NAN                 # the forming box of the current run
    runLo = NAN
    armed = False               # a coil is armed
    boxHi = NAN                 # the armed coil's box
    boxLo = NAN
    count = 0                   # armed bars of the armed coil so far, this bar included

    keys = ("squeeze_on", "run_len", "armed", "box_hi", "box_lo", "breakout", "bo_box_hi", "bo_box_lo")
    out: Dict[str, list] = {k: [] for k in keys}
    for t in range(n):
        sq = SQ[t]
        prevLen, prevHi, prevLo = runLen, runHi, runLo          # runLen[1], runHi[1], runLo[1]
        if sq:
            runLen = prevLen + 1
            if runLen == 1:
                runHi, runLo = H[t], L[t]
            else:
                runHi = prevHi if prevHi >= H[t] else H[t]      # math.max(runHi[1], high)
                runLo = prevLo if prevLo <= L[t] else L[t]      # math.min(runLo[1], low)
            if runLen == minBars:
                armed = False                                   # a newer run became a coil: it replaces (reading 2)
        else:
            runLen = 0
            runHi, runLo = NAN, NAN
            if prevLen >= minBars:                              # the run ended on bar t - 1 (reading 4)
                armed = True
                boxHi, boxLo = prevHi, prevLo
                count = 0

        isArmed = armed
        bo = 0
        if armed:
            count += 1                                          # bar t is the count-th armed bar
            if C[t] > boxHi:                                    # strict (reading 6)
                bo = 1
            elif C[t] < boxLo:
                bo = -1
            if bo != 0 or count == armedBars:
                armed = False                                   # used (once per coil) or the window is over

        out["squeeze_on"].append(sq)
        out["run_len"].append(runLen)
        out["armed"].append(isArmed)
        out["box_hi"].append(boxHi if isArmed else NAN)
        out["box_lo"].append(boxLo if isArmed else NAN)
        out["breakout"].append(bo)
        out["bo_box_hi"].append(boxHi if bo != 0 else NAN)
        out["bo_box_lo"].append(boxLo if bo != 0 else NAN)
    return {k: np.array(out[k], dtype=DTYPES[k]) for k in keys}


# ───────────────────────────── ta.dmi (PREREG l.461) ─────────────────────────────

def dmi(h, l, c, di_len=14, adx_len=14) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``ta.dmi(di_len, adx_len)`` -> (+DI, -DI, ADX), as TradingView's built-in DMI script computes them (reading 11):

        up = ta.change(high)                  down = -ta.change(low)
        plusDM  = na(up) ? na : (up > down and up > 0 ? up : 0)
        minusDM = na(down) ? na : (down > up and down > 0 ? down : 0)
        trur  = ta.rma(ta.tr, di_len)                                   ta.tr = ta.tr(false): na on bar 0
        plus  = fixnan(100 * ta.rma(plusDM, di_len) / trur)             minus alike
        adx   = 100 * ta.rma(math.abs(plus - minus) / (plus + minus == 0 ? 1 : plus + minus), adx_len)
    """
    H, L, C = _prices((h, l, c), ("h", "l", "c"))
    n_di, n_adx = _length(di_len, "di_len"), _length(adx_len, "adx_len")
    up_site, down_site = Change(), Change()
    tr_site = TrueRange(handle_na=False)
    trur_site, plus_site, minus_site = Rma(n_di), Rma(n_di), Rma(n_di)
    plus_fix, minus_fix = Fixnan(), Fixnan()
    adx_site = Rma(n_adx)
    P: List[float] = []
    M: List[float] = []
    A: List[float] = []
    for t in range(len(C)):
        up = up_site(H[t])
        down = -down_site(L[t])
        plusDM = NAN if is_na(up) else (up if (up > down and up > 0) else 0.0)
        minusDM = NAN if is_na(down) else (down if (down > up and down > 0) else 0.0)
        trur = trur_site(tr_site(H[t], L[t], C[t]))
        plus = plus_fix(pdiv(100 * plus_site(plusDM), trur))
        minus = minus_fix(pdiv(100 * minus_site(minusDM), trur))
        s = plus + minus
        dx = pdiv(abs(plus - minus), 1.0 if s == 0 else s)
        A.append(100 * adx_site(dx))
        P.append(plus)
        M.append(minus)
    return (np.array(P, dtype=np.float64), np.array(M, dtype=np.float64), np.array(A, dtype=np.float64))


def adx(h, l, c, di_len=14, adx_len=14) -> np.ndarray:
    """Pine ``ta.dmi(di_len, adx_len)``'s ADX (the third value of ``dmi``); NaN before bar di_len + adx_len - 1."""
    return dmi(h, l, c, di_len, adx_len)[2]


# ───────────────────────────── the contract ─────────────────────────────

def coil(o, h, l, c, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5, min_bars=6,
         armed_bars=12) -> Dict[str, np.ndarray]:
    """The coil breakout of PREREG 6.9 on the chart's bars: the contract's per-bar arrays (``KEYS``; module
    docstring). The ADX is ``ta.dmi(14, 14)``'s, as PREREG l.461 fixes it."""
    _prices((o, h, l, c), ("o", "h", "l", "c"))                 # the open is checked, not read
    lines = squeeze_lines(h, l, c, bb_len, bb_mult, kc_len, kc_mult)
    res = coil_from_squeeze(lines["squeeze_on"], h, l, c, min_bars, armed_bars)
    res["adx"] = adx(h, l, c, 14, 14)
    return {k: res[k] for k in KEYS}
