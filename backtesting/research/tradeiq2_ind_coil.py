"""
Coil breakout (COIL), port A: the study's own version of TradeIQ's private "Coil Breakout AI". For every chart bar it
gives the Bollinger-inside-Keltner squeeze, the length of the current squeeze run, the coil that is armed (a run of
at least 6 squeeze bars, with its box), the coil's breakout, and Pine's ``ta.dmi(14, 14)`` ADX for the ADX grade.

    from backtesting.research import tradeiq_market as TM, tradeiq2_ind_coil as COIL
    mk = TM.load("BTCUSDm", end="2024-07-01")
    b = mk.tbars("4H")                                    # 1H, 4H and 1D: the timeframes of PREREG 6.9
    out = COIL.coil(b.o, b.h, b.l, b.c)                   # the plan's settings
    out["breakout"]    # int8 per bar: +1 the first close above the armed coil's box, -1 below it, 0 neither
    out["bo_box_lo"]   # the broken box's low at breakout bars (a long's stop side), NaN elsewhere
    out["adx"]         # ta.dmi(14, 14)'s ADX (the ADX grade: >= 20)

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 5, 6.9, 7 and claim 20 of section 8). There is no
Pine source: the script is private (PREREG 1), so the rule is the plan's own definition (PREREG 6.9), made precise by
the study's contract below. Nothing here is a port of TradeIQ's code; the only TradingView code it reproduces is the
platform's documented built-ins (``ta.sma``, ``ta.stdev``, ``ta.atr``, ``ta.rma``, ``ta.change``, ``ta.tr``,
``fixnan``, ``ta.dmi``). Port A (this module, the production port) and port B (``tests/tradeiq2_oracle_coil.py``) were
written independently from the plan and the contract. The volume grade, the BIG grade, the trend filters, the stop
and the exits of PREREG 6.9 are the study's (they read the bars, this module's ``breakout`` and ``bo_box_*`` and the
ADX); they are not computed here.

Reconciled with port B on 28 Nov 2026 (``tests/test_tradeiq2_ind_coil.py``; the porting notes are
``backtest_results/tradeiq_2027/porting/coil.md``): on the 1H, 4H and 1D bars of both symbols from the study's data
start (gold 2016-01-03, BTC 2018-01-01) to 2024-06-30, and on gold from study 1's start (2017-01-03), every key is
equal bit for bit; so are 25,000 random synthetic cases (other inputs, short series, flat and constant markets) and
every hand case of either port's own tests run through the other port. No mismatch was found, and no arithmetic
needed aligning. The counts quoted below were measured on study 1's bars; the study's bars give the same values on
every bar closing from 2019, but for the last bit of ten 1D ADX values.

The contract (both ports)
-------------------------
``coil(o, h, l, c, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5, min_bars=6, armed_bars=12)`` returns a dict with
exactly the keys ``KEYS``, each an array of ``len(c)`` values, one per bar, oldest first, each known at the bar's close:

=============== ======= ===================================================================================
key             dtype   value (defaults shown)
=============== ======= ===================================================================================
``squeeze_on``  bool    ``sma(c,20) + 2*stdev(c,20) < sma(c,20) + 1.5*atr(20)`` and
                        ``sma(c,20) - 2*stdev(c,20) > sma(c,20) - 1.5*atr(20)``; False on bars 0-18 (na)
``run_len``     int64   consecutive ``squeeze_on`` bars ending at this bar (0 where ``squeeze_on`` is False)
``armed``       bool    a coil is armed at this bar: its breakout is tested at this bar's close
``box_hi``      float64 the armed coil's box: the highest high of its run's bars; NaN where not ``armed``
``box_lo``      float64 the lowest low of its run's bars; NaN where not ``armed``
``breakout``    int8    +1 ``close > box_hi``, -1 ``close < box_lo`` (strict), on an armed bar; 0 otherwise
``bo_box_hi``   float64 ``box_hi`` at breakout bars (the box that broke), NaN elsewhere
``bo_box_lo``   float64 ``box_lo`` at breakout bars, NaN elsewhere
``adx``         float64 ``adx(h, l, c)``: ``ta.dmi(14, 14)``'s ADX, 0..100; NaN on bars 0-26
=============== ======= ===================================================================================

``adx(h, l, c, di_len=14, adx_len=14)`` returns the ADX alone (NaN before bar ``di_len + adx_len - 1``).
``o`` is checked (same length, finite) but not read: the rule reads the close, the high and the low.

What is computed on each bar
----------------------------
1. The Bollinger band: ``basis = ta.sma(close, 20)``, ``dev = 2.0 * ta.stdev(close, 20)``, ``basis + dev`` and
   ``basis - dev``, TradingView's ``ta.bb`` (``pine_bb``). ``ta.stdev``'s ``biased`` is true by default: the
   POPULATION deviation (divided by 20, not 19). Study 1's verified primitives ``tradeiq_ind.sma`` / ``stdev``
   (TradingView's ``pine_sma`` / ``pine_stdev`` order of operations, a deviation of at most 1e-10 counted as 0).
2. The Keltner channel of the plan (PREREG 6.9: "SMA(20) +- 1.5 ATR(20)"; PREREG 5: ATR = ``ta.atr``):
   ``ta.sma(close, kc_len) + 1.5 * ta.atr(kc_len)`` and ``- 1.5 * ta.atr(kc_len)``. ``ta.atr`` is Wilder's RMA of
   ``ta.tr(true)`` seeded with the SMA of the first 20 true ranges (``pine_rma``), the true range of bar 0 being
   high - low (``tradeiq_ind.atr``). This is NOT TradingView's ``ta.kc``, whose basis is an EMA and whose width is an
   EMA of the true range, and not LazyBear's squeeze, whose width is an SMA of the true range. With the defaults the
   two bases are the same SMA array.
3. ``squeeze_on = bbUpper < kcUpper and bbLower > kcLower``, both strict and evaluated as written: the two sums and
   the two differences are formed and then compared (not the simplified ``2 * stdev < 1.5 * atr``). A comparison
   with na is false, so ``squeeze_on`` is False until the SMA, the deviation and the ATR all exist (bar 19 for 20 / 20)
   and on any bar where a line is na. A dead market (zero ranges, constant closes: both widths 0) is no squeeze.
4. ``run_len``: ``squeeze_on ? run_len[1] + 1 : 0``, counted in chart bars (a weekend or a data hole between two bars
   does not break a run: bars are consecutive on the chart, as on TradingView).
5. A coil is a run of at least ``min_bars`` (6) consecutive squeeze bars. Its box is the highest high and the lowest
   low of ALL the run's bars (the whole run, however long; not its last 6 bars; not the closes; not the bar after it).
   The run of exactly 5 bars is no coil; the run of 6 is one.
6. Arming: the coil becomes armed on the first bar after the run's last squeeze bar (the first bar whose
   ``squeeze_on`` is False; this is when the run is known to have ended) and stays armed for ``armed_bars`` (12) bars,
   that first bar included: bars e+1 .. e+12 for a run ending at bar e. The count is in bars and does not pause on
   squeeze bars of a newer run. It stops earlier
   * at its breakout: the breakout bar is armed (the close is tested while armed) and the bars after it are not;
   * when a NEWER run reaches ``min_bars`` (``run_len == min_bars`` on a bar after the coil's run ended): that run is
     a coil from this bar on and replaces the armed one AT this bar, i.e. the old coil is no longer armed on the
     bar where the newer run reaches 6 bars, and cannot break out there. The newer coil is armed only after its own
     run ends (step 6 again), with its own box. A newer run that ends before reaching 6 bars replaces nothing: the
     old coil stays armed through those squeeze bars and can break out on one of them.
   At most one coil is armed on any bar (a run that arms has replaced, when it reached 6 bars, whatever was armed).
7. The breakout: on an armed bar, ``close > box_hi`` is +1 (long), else ``close < box_lo`` is -1 (short); strict, so a
   close exactly at an edge is no breakout; a wick beyond the box is no breakout (the close decides). Once per
   coil: after its breakout the coil is done (neither side again). ``bo_box_hi`` / ``bo_box_lo`` are the box at the
   breakout bar (PREREG 6.9's stop is the opposite edge: ``bo_box_lo`` for a long, ``bo_box_hi`` for a short).
8. The ADX: ``[_, _, adx] = ta.dmi(14, 14)``, as TradingView documents it in its built-in "Directional Movement
   Index" script (whose ADX the built-in "Average Directional Index" script computes the same way), statement by
   statement:

       up = ta.change(high)                                   high - high[1], na on bar 0
       down = -ta.change(low)                                 -(low - low[1]), na on bar 0
       plusDM = na(up) ? na : (up > down and up > 0 ? up : 0)
       minusDM = na(down) ? na : (down > up and down > 0 ? down : 0)
       trur = ta.rma(ta.tr, diLength)
       plus = fixnan(100 * ta.rma(plusDM, diLength) / trur)
       minus = fixnan(100 * ta.rma(minusDM, diLength) / trur)
       sum = plus + minus
       adx = 100 * ta.rma(math.abs(plus - minus) / (sum == 0 ? 1 : sum), adxSmoothing)

   * ``ta.tr`` (the variable) is ``ta.tr(false)``: na on bar 0, where ``close[1]`` is na (``ta.atr`` uses
     ``ta.tr(true)`` instead). So ``trur``'s RMA starts at bar 1 and its first value, at bar ``diLength`` (14), is
     the SMA of the true ranges of bars 1-14, as are those of ``plusDM`` / ``minusDM``: +DI and -DI from bar 14,
     the ADX from bar 14 + 14 - 1 = 27. +DI and -DI divide by the same ``trur``, which cancels in DX: the ADX
     depends on the true range only through rounding (and through ``fixnan`` while ``trur`` is 0).
   * The directional movements are strict: a tie ``up == down`` gives 0 to both; an inside bar gives 0 to both.
   * ``100 * rma / trur`` is evaluated left to right; 0 / 0 (a flat start: no true range yet) is na, and ``fixnan``
     carries the last non-na value forward (na while there is none). ``sum == 0`` (no directional movement at all)
     divides by 1, so DX is 0 there, not na.
   * ``ta.rma`` is ``pine_rma`` (seeded with the SMA of its first ``length`` non-na values, then
     ``alpha * src + (1 - alpha) * prev``, alpha = 1 / length): study 1's verified ``tradeiq_ind.rma``.

What is known when (no look-ahead)
----------------------------------
Every value of bar t uses bars 0 .. t only and is final at the bar's close: the squeeze reads the closes t-19 .. t
and the true ranges up to t; ``run_len`` the squeeze up to t; a coil's box the highs and lows of its run (bars before
the arming bar); the arming bar is known to end the run at its own close (its ``squeeze_on`` is False), which is
also when its breakout is tested; the breakout compares the close of t with that box; a replacement is known at the
close of the bar where the newer run reaches 6 bars. There is no ``request.security``, no pivot, no repainting state:
removing the bars after t changes nothing up to t (tested). The study decides at the breakout bar's close and fills
at the next M1 open (PREREG 4).

Readings where the plan, the contract or the platform leave a choice
--------------------------------------------------------------------
Each effect is a count of bars closing in 2019-2022 on study 1's 1H / 4H / 1D bars (data start to 2024-06-30), as
"gold 1H / 4H / 1D; BTC 1H / 4H / 1D": counts only, no profit or loss. The breakouts in 2019-2022 are 338 / 75 / 15
(gold) and 521 / 129 / 23 (BTC); "changes N breakouts" counts the bars whose +1 / -1 / 0 would differ.

* Replacement precedence (step 6): on the bar where a newer run reaches 6 bars the old coil is no longer armed. The
  other order (test the old coil first, replace after the bar) adds a breakout wherever that bar closes beyond the
  old, unbroken box: 0 / 0 / 0; 5 / 0 / 1. It can change a signal, rarely.
* What replaces (step 6): the contract's "a newer run reaches min_bars". Replacing only when the newer coil ARMS (its
  run ends) keeps the old coil armed through the newer run's bars from its 6th on and adds 3 / 1 / 0; 8 / 1 / 1
  breakouts. Can change signals; the contract fixes it.
* A newer run shorter than 6 bars (step 6) neither replaces nor pauses the armed coil, which can break out on one of
  its squeeze bars: 11 / 1 / 0; 19 / 6 / 2 breakouts fall on squeeze bars. A reading that disarms (or pauses) the
  coil on squeeze bars would remove or move them. Can change signals; the contract fixes it.
* The box over the whole run (step 5). A box over the run's last 6 bars changes 278 / 71 / 12; 548 / 121 / 25 boxes
  and 80 / 13 / 2; 112 / 22 / 5 breakouts; over its first 6 bars 214 / 87 / 9; 454 / 110 / 21 breakouts. Can change
  signals; the contract fixes it.
* The arming bar (step 6) is the first bar after the run, where the squeeze fires; it holds 187 / 25 / 8; 289 / 72 /
  11 of the breakouts. Arming from the bar after it changes 370 / 50 / 15; 556 / 144 / 22 breakouts. Can change
  signals; the contract fixes it.
* The 12 armed bars include the arming bar (step 6): the 12th armed bar holds 7 / 1 / 0; 12 / 3 / 1 breakouts, which
  an 11-bar window would lose; a 13-bar window would add 7 / 2 / 0; 3 / 3 / 0. Can change signals; the contract
  fixes it.
* The breakout bar is armed (``armed`` and ``box_*`` set on it, nothing after it): only the meaning of the ``armed``
  array. Cannot change a signal.
* Strict breakout (step 7): no armed bar of any of the six series closes exactly at a box edge in 2019-2022, so
  ``>=`` / ``<=`` would change nothing on our bars (they could elsewhere: the box and the close are prices compared
  without arithmetic, so only exact ties matter).
* The squeeze is strict and as written (step 3). No bar of either symbol has a Bollinger band exactly on a Keltner
  band (to 2024-06-30), and the simplified ``2 * stdev < 1.5 * atr`` differs from the written form on no bar. The
  closest any bar comes to the threshold, ``|1.5 atr - 2 sd| / (1.5 atr)``, is 2.7e-6 (BTC 1D; 2.3e-5 or more
  elsewhere from 2019), far above rounding: no order of the float operations can move a squeeze bar. Cannot change a
  signal on our bars.
* ``ta.stdev``'s population deviation (step 1; the contract and ``ta.stdev``'s default). The sample deviation is
  sqrt(20 / 19) = 1.026 times larger, so it removes the squeeze bars with a margin under 2.6 %: it changes 514 / 122 /
  15; 697 / 190 / 40 squeeze bars and 85 / 18 / 2; 119 / 27 / 9 breakouts. Can change signals; fixed.
* The Keltner channel is the SMA(20) +- 1.5 ``ta.atr(20)`` (step 2; the plan). TradingView's ``ta.kc(close, 20,
  1.5)`` (EMA basis, EMA of the true range) would change 3,268 / 708 / 117; 5,652 / 1,258 / 290 squeeze bars (of
  6,983 / 1,634 / 291; 14,324 / 2,915 / 484) and 312 / 68 / 14; 508 / 129 / 24 breakouts; an SMA of the true range
  (LazyBear) 1,672 / 332 / 39; 2,501 / 571 / 155 squeeze bars and 272 / 42 / 10; 332 / 96 / 19 breakouts. Can change
  signals; the plan fixes it.
* The Keltner basis length off the plan's settings (step 2): ``ta.sma(close, kc_len)``; with bb_len = kc_len = 20 it
  is the Bollinger basis itself. Cannot change a signal with the plan's settings.
* ``ta.atr(20)``'s seed (the SMA of the first 20 true ranges, bar 0's true range high - low; PREREG 5) against the
  first true range: the ATR forgets it as (19/20)^n (from 2019 at most 1.4e-8 relative, BTC 1D) and no squeeze bar
  from 2019 differs. Cannot change a signal.
* ``ta.dmi``'s true range (step 8): ``ta.tr`` (na on bar 0) as the documented script has it, not ``ta.tr(true)``. The
  ADX does not depend on it but for rounding: +DI and -DI divide by the same ``trur``, which cancels in DX; the two
  readings differ by at most 1.4e-14 from 2019 (BTC 1D; 0 elsewhere). Cannot change a signal.
* ``ta.dmi``'s directional-movement ties (step 8): ``up == down > 0`` gives 0 to both, as documented. Such ties occur
  on 1 / 0 / 0; 1 / 0 / 0 bars in 2019-2022. Giving a tie to +DM moves the ADX for a while after each, by up to 1.3
  (gold 1H) and 4.8 (BTC 1H) from 2019 to 2024-06-30, and flips the ADX >= 20 grade on 4 BTC 1H bars in 2019-2022,
  none of them a breakout bar. Cannot change a signal on our bars (the grade is read at breakout bars).
* ``ta.dmi``'s ``fixnan`` and ``sum == 0`` guard never act after the warm-up on our bars (``trur`` > 0 and +DI + -DI >
  0 on every bar from 14). The ADX equals ``ladder_ind.adx`` (another study's Wilder ADX, another order of
  operations) to 1e-13 on all six series, and the closest a breakout bar's ADX comes to 20 from 2019 is 0.0014 (BTC
  1H): no implementation's rounding can flip a grade. Cannot change a signal on our bars.
* The bars are the study's (bid OHLC on UTC boundaries; a short UTC day merged into the next, PREREG 2), not
  TradingView's: squeezes and breakouts can differ from a TradingView chart, most on 1D.
Nothing is tuned: every setting is the plan's (bb 20 / 2.0, kc 20 / 1.5, 6 bars, 12 bars, ADX 14 / 14).

Speed: the squeeze and the ADX are numpy (study 1's primitives; their RMAs are Python loops over the bars), the
run / coil / breakout state machine is one numba loop (``cache=True``). A 1H series of 57,000 bars takes about 0.05 s
after the first compilation.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np
from numba import njit

from . import tradeiq_ind as I

__all__ = ["KEYS", "DEFAULTS", "coil", "adx"]

NAN = math.nan

KEYS = ("squeeze_on", "run_len", "armed", "box_hi", "box_lo", "breakout", "bo_box_hi", "bo_box_lo", "adx")

DEFAULTS: Dict[str, float] = {      # PREREG 6.9 (and 5 for the ADX's ta.dmi(14, 14))
    "bb_len": 20,                   # "SMA(20) +- 2 stdev(close, 20)"
    "bb_mult": 2.0,
    "kc_len": 20,                   # "SMA(20) +- 1.5 ATR(20)"
    "kc_mult": 1.5,
    "min_bars": 6,                  # "a coil is at least 6 consecutive squeeze_on bars"
    "armed_bars": 12,               # "it stays armed for 12 bars after its last squeeze bar"
    "di_len": 14,                   # "Pine ta.dmi(14, 14) ADX"
    "adx_len": 14,
}


# ───────────────────────────── input checks ─────────────────────────────

def _series(x, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)              # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    return a


def _bars(named) -> Tuple[np.ndarray, ...]:
    """The price series as float64 copies of one length, every value finite (bars are complete)."""
    out = tuple(_series(x, k) for x, k in named)
    n = len(out[-1])
    if any(len(a) != n for a in out):
        raise ValueError(f"{', '.join(k for _, k in named)}: series of equal length are expected, got "
                         f"{', '.join(str(len(a)) for a in out)}")
    for a, (_, k) in zip(out, named):
        if not np.isfinite(a).all():
            raise ValueError(f"{k}: na or an infinite value at bar {int(np.argmax(~np.isfinite(a)))}; bars are "
                             "expected to be complete")
    return out


def _int(n, name: str) -> int:
    """A length / count: an integer >= 1 (an integral float is accepted)."""
    if isinstance(n, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {n!r}")
    f = float(n)
    if not (f >= 1.0 and f.is_integer()):
        raise ValueError(f"{name}: an integer >= 1 is expected, got {n!r}")
    return int(f)


def _mult(x, name: str) -> float:
    """A band multiplier: a finite number >= 0."""
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {x!r}")
    f = float(x)
    if not (math.isfinite(f) and f >= 0.0):
        raise ValueError(f"{name}: a finite number >= 0 is expected, got {x!r}")
    return f


# ───────────────────────────── the squeeze ─────────────────────────────

def _bands(h: np.ndarray, l: np.ndarray, c: np.ndarray, bb_len: int, bb_mult: float, kc_len: int,
           kc_mult: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(bb_up, bb_lo, kc_up, kc_lo)``: ``ta.sma(close, bb_len) +- bb_mult * ta.stdev(close, bb_len)`` (``pine_bb``:
    ``dev = mult * stdev``, then ``basis + dev`` / ``basis - dev``) and ``ta.sma(close, kc_len) +- kc_mult *
    ta.atr(kc_len)`` (steps 1-2 of the module docstring). NaN where a line does not exist yet."""
    basis = I.sma(c, bb_len)
    dev = bb_mult * I.stdev(c, bb_len)
    kc_basis = basis if kc_len == bb_len else I.sma(c, kc_len)
    rng = kc_mult * I.atr(h, l, c, kc_len)
    return basis + dev, basis - dev, kc_basis + rng, kc_basis - rng


def _squeeze(bb_up, bb_lo, kc_up, kc_lo) -> np.ndarray:
    """``bbUpper < kcUpper and bbLower > kcLower`` (step 3): strict; False where any line is na."""
    with np.errstate(invalid="ignore"):
        return (bb_up < kc_up) & (bb_lo > kc_lo)


# ───────────────────────────── the coil state machine (numba) ─────────────────────────────

@njit(cache=True)
def _machine(sq, h, l, c, min_bars, armed_bars):
    """
    Steps 4-7 of the module docstring, bar by bar. State at the start of bar t: the current run's length and extremes,
    and the armed coil (its box and the number of bars it has left, this bar included; 0 = no coil armed). On bar t:

    1. a squeeze bar extends the run (its first bar sets the extremes); when the run reaches ``min_bars`` it is a
       coil, and the armed coil (an older one) is replaced: ``left = 0`` from this bar;
       a bar without squeeze ends the run; a run of ``min_bars`` or more arms its coil here with ``armed_bars`` bars
       and its box;
    2. if a coil is armed (``left > 0``) the bar is armed; its close is tested against the box (+1 above, else -1
       below, strict); a breakout disarms the coil, otherwise one armed bar is used up.
    """
    n = sq.shape[0]
    run_len = np.zeros(n, np.int64)
    armed = np.zeros(n, np.bool_)
    box_hi = np.full(n, np.nan)
    box_lo = np.full(n, np.nan)
    breakout = np.zeros(n, np.int8)
    bo_hi = np.full(n, np.nan)
    bo_lo = np.full(n, np.nan)
    run = 0                 # the current run of squeeze bars
    run_hi = 0.0            # its highest high and lowest low (valid while run > 0)
    run_lo = 0.0
    left = 0                # armed bars the armed coil has left, this one included
    bhi = 0.0               # the armed coil's box (valid while left > 0)
    blo = 0.0
    for t in range(n):
        if sq[t]:
            if run == 0:
                run_hi = h[t]
                run_lo = l[t]
            else:
                if h[t] > run_hi:
                    run_hi = h[t]
                if l[t] < run_lo:
                    run_lo = l[t]
            run += 1
            if run == min_bars:             # a newer run becomes a coil: it replaces the armed one, from this bar
                left = 0
        else:
            if run >= min_bars:             # the run ended on the bar before: its coil is armed from this bar
                bhi = run_hi
                blo = run_lo
                left = armed_bars
            run = 0
        run_len[t] = run
        if left > 0:
            armed[t] = True
            box_hi[t] = bhi
            box_lo[t] = blo
            if c[t] > bhi:
                breakout[t] = 1
            elif c[t] < blo:
                breakout[t] = -1
            if breakout[t] != 0:            # once per coil
                bo_hi[t] = bhi
                bo_lo[t] = blo
                left = 0
            else:
                left -= 1
    return run_len, armed, box_hi, box_lo, breakout, bo_hi, bo_lo


# ───────────────────────────── the ADX (ta.dmi) ─────────────────────────────

def _tr_na(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """``ta.tr`` = ``ta.tr(false)``: ``math.max(math.max(high - low, math.abs(high - close[1])), math.abs(low -
    close[1]))`` with na on bar 0 (``close[1]`` is na and ``math.max`` of na is na)."""
    c1 = I.hist(c, 1)
    return np.maximum(np.maximum(h - l, np.abs(h - c1)), np.abs(l - c1))


def _fixnan(x: np.ndarray) -> np.ndarray:
    """``fixnan(x)``: every na replaced by the last non-na value before it; na while there is none."""
    ok = ~np.isnan(x)
    last = np.maximum.accumulate(np.where(ok, np.arange(len(x)), -1)) if len(x) else np.zeros(0, np.int64)
    return np.where(last >= 0, x[np.maximum(last, 0)], NAN)


def _dmi(h: np.ndarray, l: np.ndarray, c: np.ndarray, di_len: int,
         adx_len: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``[plus, minus, adx] = ta.dmi(di_len, adx_len)``, statement by statement as step 8 of the module docstring
    (TradingView's built-in "Directional Movement Index" script)."""
    up = I.change(h)                                                       # up = ta.change(high)
    down = -I.change(l)                                                    # down = -ta.change(low)
    with np.errstate(invalid="ignore"):
        plus_dm = np.where(np.isnan(up), NAN, np.where((up > down) & (up > 0.0), up, 0.0))
        minus_dm = np.where(np.isnan(down), NAN, np.where((down > up) & (down > 0.0), down, 0.0))
    trur = I.rma(_tr_na(h, l, c), di_len)                                  # trur = ta.rma(ta.tr, len)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus = _fixnan(100.0 * I.rma(plus_dm, di_len) / trur)              # fixnan(100 * ta.rma(plusDM, len) / trur)
        minus = _fixnan(100.0 * I.rma(minus_dm, di_len) / trur)
        s = plus + minus                                                   # sum = plus + minus
        # math.abs(plus - minus) / (sum == 0 ? 1 : sum)
        dx = np.abs(plus - minus) / np.where(s == 0.0, 1.0, s)
    return plus, minus, 100.0 * I.rma(dx, adx_len)                         # adx = 100 * ta.rma(..., lensig)


def adx(h, l, c, di_len=14, adx_len=14) -> np.ndarray:
    """
    The ADX of ``ta.dmi(di_len, adx_len)`` (PREREG 6.9's ADX grade reads ``ta.dmi(14, 14)``), per bar, 0..100: NaN
    before bar ``di_len + adx_len - 1`` (27 with the defaults; later on a series that starts with bars of no range).
    Step 8 of the module docstring has the definition. Inputs are bid highs, lows and closes, finite, of one length.
    """
    h, l, c = _bars(((h, "h"), (l, "l"), (c, "c")))
    return _dmi(h, l, c, _int(di_len, "di_len"), _int(adx_len, "adx_len"))[2]


# ───────────────────────────── the coil ─────────────────────────────

def coil(o, h, l, c, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5, min_bars=6,
         armed_bars=12) -> Dict[str, np.ndarray]:
    """
    The coil breakout of PREREG 6.9 on one chart's bars (bid OHLC, oldest first, finite): a dict with the keys
    ``KEYS`` (the module docstring has each one's definition and the readings). The ``adx`` key is ``adx(h, l, c)``
    with the plan's 14 / 14. Inputs are copied, never modified; lengths and bar counts are integers >= 1, the
    multipliers finite numbers >= 0.
    """
    o, h, l, c = _bars(((o, "o"), (h, "h"), (l, "l"), (c, "c")))
    bb_len, kc_len, min_bars, armed_bars = (_int(v, k) for v, k in ((bb_len, "bb_len"), (kc_len, "kc_len"),
                                                                     (min_bars, "min_bars"),
                                                                     (armed_bars, "armed_bars")))
    bb_mult, kc_mult = _mult(bb_mult, "bb_mult"), _mult(kc_mult, "kc_mult")
    sq = _squeeze(*_bands(h, l, c, bb_len, bb_mult, kc_len, kc_mult))
    run_len, armed, box_hi, box_lo, breakout, bo_hi, bo_lo = _machine(sq, h, l, c, np.int64(min_bars),
                                                                      np.int64(armed_bars))
    return {
        "squeeze_on": sq, "run_len": run_len, "armed": armed, "box_hi": box_hi, "box_lo": box_lo,
        "breakout": breakout, "bo_box_hi": bo_hi, "bo_box_lo": bo_lo,
        "adx": _dmi(h, l, c, DEFAULTS["di_len"], DEFAULTS["adx_len"])[2],
    }
