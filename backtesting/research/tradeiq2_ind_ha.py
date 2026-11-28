"""
Heikin Ashi Candles, Trend Strength & Trend Age Stats (LunqFX), port A: the Heikin Ashi candles, their colour and
phase, the colour streaks and their events, and the panel's trend-age statistics computed causally at every bar.

    from backtesting.research import tradeiq_market as TM, tradeiq2_ind_ha as HA
    mk = TM.load("XAUUSDm", end="2024-07-01")
    b = mk.tbars("4H")                                   # 1H, 4H and 1D: the timeframes of PREREG 6.8
    out = HA.heikin_ashi(b.o, b.h, b.l, b.c)             # the script's defaults, PREREG 6.8's minimum of 50 streaks
    out["flip"]              # bool: the candle's colour differs from the previous candle's (M1, HA-H1 exit, HA-H2)
    out["ev_first_strong"]   # bool: the streak's first STRONG candle (HA-H1 entry)
    out["ev_ind"]            # bool: INDECISION right after >= 2 STRONG candles of the streak (M2)
    out["weak_run"]          # int32: consecutive WEAK candles of the streak (M3 tightens where it reaches 2)
    out["rare_now"]          # bool: the streak reached its rare age, the 90th percentile (M4)
    out["streaks"]           # DataFrame of the finished streaks (the claim-5 calibration)

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 2, 5, 6.8, 7 and claims 3-5 of section 8); the
specification is section 4 of the study's map ``orb_session_swing_ha.md``. The script is "Heikin Ashi Candles, Trend
Strength & Trend Age Stats [LunqFX]" (Pine v6, 327 lines). Line numbers (l.) are those of the plain-text copy the
study ported from; the source itself is not in this repository. Port A (this module, the production port) and port B
(``tests/tradeiq2_oracle_ha.py``) were written independently from the source and the specification. About 110 of the
script's lines compute anything (l.20-28, 79-160, 166-184, 204-212); the rest draws candles, labels and the panel.

The contract (both ports)
-------------------------
``heikin_ashi(o, h, l, c, strong_tol=0.05, doji_max=0.25, ahead_n=5, rare_pct=90, min_streaks=50, keep=KEEP)``
returns a dict
with exactly the keys ``KEYS``. Every key but ``streaks`` is an array of ``len(c)`` values, one per bar, oldest first,
each the value at the bar's close:

=================== ======= ==================================================================================
key                 dtype   value (the script's names; defaults shown)
=================== ======= ==================================================================================
``ha_o``            float64 ``haO`` (l.80-81): ``(open + close) / 2.0`` on bar 0, then ``(haO[1] + haC[1]) / 2.0``
``ha_h``            float64 ``haH = math.max(high, math.max(haO, haC))`` (l.82)
``ha_l``            float64 ``haL = math.min(low, math.min(haO, haC))`` (l.83)
``ha_c``            float64 ``haC = (open + high + low + close) / 4.0`` (l.79)
``dir``             int8    ``dir = haC >= haO ? 1 : -1`` (l.85): +1 bullish, -1 bearish; a tie is bullish
``phase``           int8    the script's own codes (l.92): ``STRONG`` 0, ``STEADY`` 1, ``WEAK`` 2, ``INDECISION`` 3;
                            the first test that holds wins, in the order INDECISION, STRONG, WEAK, STEADY (l.94)
``flip``            bool    ``flip = sDir != 0 and dir != sDir`` (l.115): the colour differs from the previous
                            bar's; False on bar 0
``age``             int32   ``age`` (l.107, 123, 145, 151): candles in the current streak, this one included; 1 on
                            bar 0 and on every flip bar
``strong_run``      int32   ``strongRun`` after l.157 (the panel's "STRONG in a row"): consecutive STRONG candles
                            of the current streak ending at this bar; 0 when this candle is not STRONG
``weak_run``        int32   not in the script (PREREG 6.8, M3): consecutive WEAK candles of the current streak
                            ending at this bar; 0 at a flip and at any candle that is not WEAK
``ev_ind``          bool    ``evInd`` (l.156): an INDECISION candle with ``strongRun >= 2`` before it, i.e. right
                            after 2 or more consecutive STRONG candles of the same streak; never on a flip bar
``ev_first_strong`` bool    ``evFirstSt`` (l.158-160): the streak's first STRONG candle; it can be the flip bar
``pct_below``       float64 ``pctBelow(curA, age)`` (l.166-173, 206, 210): the percentage of the finished streaks of
                            the current colour (the last 5,000 kept by default, l.131-132; every one with
                            ``keep=None``) shorter than ``age``, computed as
                            ``100.0 * c / n``; NaN while the colour has no finished streak
``rare_now``        bool    ``rareNow`` (l.209-212) evaluated at every bar, not only on the last one:
                            ``pct_below >= rare_pct`` and the previous age's percentage ``< rare_pct``; also False
                            while fewer than ``min_streaks`` streaks of the colour have finished (PREREG 6.8)
=================== ======= ==================================================================================

Every per-bar array has a value on every bar; ``pct_below`` is NaN exactly on the bars whose colour has no finished
streak yet (the first bars of the data).

``streaks`` is a DataFrame of the finished streaks, one row each in the order they finished, with the columns
``STREAK_COLUMNS``: ``start_bar`` and ``end_bar`` (int64: the streak's first and last bar, so ``length = end_bar -
start_bar + 1``; the streak is known at the close of bar ``end_bar + 1``, its flip bar), ``dir`` (int8),
``length`` (int32: the ``age`` pushed at l.130), ``had_strong`` (bool: ``strongAt > 0``), ``strong_at`` (int32:
``strongAt``, the age of its first STRONG candle, 0 = none) and ``ran_5_after_strong`` (bool: ``age - strongAt >=
aheadN`` for a streak with a STRONG candle, the ``bullSK`` / ``bearSK`` increment of l.136 / l.139; "5" is the
default ``ahead_n``). The unfinished last streak is not in it; the first streak is, counted from bar 0 like every
other, as the script counts it.

Inputs: ``o, h, l, c`` are 1-D sequences of one length without NaN or infinities (copied, never modified). The
script's inputs keep their bounds (l.20-28): ``strong_tol`` in [0, 0.3], ``doji_max`` in [0.05, 0.5], ``ahead_n`` an
integer in [1, 50], ``rare_pct`` an integer in [50, 99]; ``min_streaks`` (the plan's, not the script's) an integer
>= 0, where 0 or 1 gives the script's own rule (a percentage exists once one streak has finished).

What the script computes on each bar, in its order
--------------------------------------------------
1. Heikin Ashi (l.79-83): ``haC = (open + high + low + close) / 4.0`` (added left to right, then divided);
   ``float haO = na`` then ``haO := na(haO[1]) ? (open + close) / 2.0 : (haO[1] + haC[1]) / 2.0``. ``haO`` is not a
   ``var`` but ``haO[1]`` is the value the previous bar ended with, so this is the usual recursion, started at
   ``(open + close) / 2`` on the chart's first bar. It forgets its start at a rate of 2^-n. ``haH`` / ``haL`` are
   the bar's high / low widened to include the HA body.
2. Colour and shape (l.85-90): ``dir = haC >= haO ? 1 : -1``, so a tie (a zero HA body) is bullish;
   ``rng = haH - haL``, ``body = math.abs(haC - haO)``, ``upW = haH - math.max(haO, haC)``,
   ``loW = math.min(haO, haC) - haL``; ``oppW`` is the wick against the colour (``loW`` for a bullish candle, so for
   a tie too).
3. Phase (l.93-94), the first test that holds:
   - INDECISION (3): ``rng > 0 and body <= dojiMax * rng and math.min(upW, loW) >= 0.1 * rng``;
   - STRONG (0): ``oppW <= strongTol * rng``; a zero-range candle (``rng == 0``, which needs O = H = L = C = haO)
     is STRONG, as ``0 <= 0`` holds;
   - WEAK (2): ``dir == dir[1] and body < body[1]``: the same colour as the previous candle and a smaller body than
     the previous candle's, whatever that candle's phase; on bar 0 both comparisons are with na, so false;
   - STEADY (1): everything else.
   With the defaults INDECISION and STRONG exclude each other (a doji's opposite wick is at least 0.1 > 0.05 of the
   range), so their order only matters for ``strong_tol > 0.1``; WEAK after both matters always.
4. Streaks (l.99-160), the ``var`` state ``sDir`` (0 before bar 0), ``age``, ``strongAt``, ``strongRun``:
   - bar 0 (``sDir == 0``): the first streak starts, ``age = 1``;
   - a flip (``sDir != 0 and dir != sDir``): the finished streak's ``age`` is pushed into the array of ITS colour
     (``sDir == 1 ? bullL : bearL``, l.129-130), the array's oldest entry is dropped once it holds more than 5,000
     (l.131-132); if it had a STRONG candle, ``SN += 1`` and ``SK += 1`` when ``age - strongAt >= aheadN``
     (l.133-139); then ``sDir = dir``, ``age = 1``, ``strongAt = 0``, ``strongRun = 0`` (l.144-147);
   - otherwise ``age += 1`` (l.151).
   Then, on every bar, in this order: ``evInd := phase == 3 and strongRun >= 2`` (l.156), so a flip bar never has
   it (``strongRun`` was just reset); ``strongRun := phase == 0 ? strongRun + 1 : 0`` (l.157); ``if phase == 0 and
   strongAt == 0: strongAt := age, evFirstSt := true`` (l.158-160), which a STRONG flip bar meets at age 1. The
   labels' extreme bar and price (``exBar``, ``exPx``, l.110-111, 124-125, 148-154) are display only, not ported.
   Because ``sDir`` always equals the previous candle's ``dir``, a flip is exactly a change of colour, and a WEAK
   candle (same colour as the previous one) is never a flip bar.
5. Statistics (l.166-173, 204-212): ``curA = sDir == 1 ? bullL : bearL`` is the array of the CURRENT streak's colour.
   Pushes only go to the colour of the streak that ends, so ``curA`` does not change during a streak: its percentage
   ``pctBelow(curA, age)`` grows with the age, and the rare-age crossing happens at most once per streak.
   ``rareNow := not na(pNow) and pNow >= rarePct and (na(pPrev) or pPrev < rarePct or age == 1)`` with
   ``pPrev = age > 1 ? pctBelow(curA, age - 1) : 0.0``. In the script this runs only ``if barstate.islast``
   (l.209), so on a chart's history ``rareNow`` is always false and the rare-age alert (l.295-296) only works live.
   PREREG 6.8 computes it causally at every bar instead: ``rare_now[t]`` is what the script says when bar t is the
   chart's last bar (its state at t does not depend on later bars), i.e. what its alert says at t's close. As
   ``pctBelow(curA, 1)`` is 0, it never fires at age 1, and ``na(pPrev)`` implies ``na(pNow)``.
   ``survive(a, A, X)`` (l.176-184) and SK / SN feed only the panel (l.280-284); they are here as ``survive`` and
   ``panel_at``, for the plan's calibration check (claim 5).

What is known when (no look-ahead)
----------------------------------
Every per-bar value of bar t uses bars 0 .. t only and is final at t's close: the HA candle reads the bar's OHLC and
the previous HA candle, the phase the previous candle's colour and body, the streak state the bars before, the
statistics the streaks finished by t (a streak finishes at the close of its flip bar, ``end_bar + 1``, and goes to
the array of its own colour, which the current streak does not read until the colour comes back). No
``request.security``, no ``lookahead``, no ``varip``; the script's header (l.10-11) says the same. Removing the bars
after t changes nothing up to t (tested), and ``streaks`` then lists exactly the streaks finished by t. What does
depend on the bars given is the start: the HA recursion for its first few dozen bars, and the statistics for good,
because they count the streaks since bar 0 (the video's "more history, better numbers", tr.78).

Readings where the source, the platform or the plan leaves a choice
-------------------------------------------------------------------
Measured on the study's 1H / 4H / 1D bars of both symbols, from ``tradeiq2_market.data_start`` (gold 2016-01-03, with
the 2016 warm-up months; BTC 2018-01-01) to 2024-06-30: read with ``external.load_market(..., end="2024-07-01")`` and
built by study 1's ``TMarket.tbars``, which is what ``tradeiq2_market.load`` serves. Counted are the bars where the
other reading gives another value, over Development (the harness's decision bars: closing after 2019-01-01 00:00 and
filled before 2023-01-01 00:00) and Validation (closing after 2023-01-01 00:00): counts only, no profit or loss. The
Development event counts of this reading are: gold 1H / 4H / 1D 5,866 / 1,554 / 260 flips, 481 / 150 / 15
``rare_now``; BTC 9,211 / 2,229 / 350 flips, 871 / 201 / 30 ``rare_now`` (``backtest_results/tradeiq_2027/porting/
ha.md`` has the rest; ports A and B are identical bit for bit on these bars, ``tests/test_tradeiq2_ind_ha.py``).

* The 5,000-streak cap (l.131-132): the port's default keeps it as written (``KEEP``, the reconciled contract,
  which study 3 calls). ``heikin_ashi(..., keep=None)`` keeps every finished streak since the first bar: that is
  PREREG 6.8's "using all history from the data start" as study 2 reads it (DEVIATIONS HA-R10, replacing HA-P1),
  and study 2's rule module calls it so; ports A and B agree bit for bit with it (``tests/test_tradeiq2_ind_ha.py``,
  section 4). The cap binds only on 1H: gold's from 2022-11-28, BTC's from 2022-04-21 (both colours; gold's from
  2023-11-27 with study 1's later start, 2017-01-03); never on 4H or 1D before 2024-07. With every streak kept,
  ``pct_below`` differs on 398 gold / 4,500 BTC 1H bars of Development and on 6,594 / 9,659 of Validation, but
  ``rare_now`` on none: the cap changes no signal on our bars.
* ``rareNow`` at every bar (PREREG 6.8, spec 4.2) instead of on the last bar only (l.209): on a chart's history the
  script has no rare-age event at all, so every ``rare_now`` event (M4) is this reading's.
* ``min_streaks`` = 50 (PREREG 6.8; the script needs one finished streak), counted over every finished streak of the
  colour, kept by the cap or not: the plan's "50 finished streaks of that colour". With the cap of 5,000 above 50 it
  is the same as counting the array; the two differ only with a private ``keep`` below ``min_streaks`` (port B
  counted the array and was aligned with this reading at the reconciliation). Every colour has 50 finished streaks
  by 2016-01-27 (gold 1H), 2016-04-19 (gold 4H), 2017-11-07 (gold 1D), 2018-01-18 (BTC 1H), 2018-03-08 (BTC 4H),
  2019-02-04 (BTC 1D; bear 2019-02-03); the script's own rule changes ``rare_now`` only in the warm-up, on no bar of
  Development or Validation of any series.
* The history's start (the chart's first bar) is the first bar given. The statistics count every streak since then,
  the first one included although its true start is unknown, so ``pct_below`` and ``rare_now`` depend on it; the
  candles, colours, phases and every other event do not, after a few weeks (the HA recursion forgets its start as
  2^-n). Gold from 2016-01-03 (the study's start) instead of 2017-01-03 (study 1's): the HA candle differs only until
  2017-01-04 (1H), 2017-01-11 (4H), 2017-03-04 (1D), bit for bit; in Development ``rare_now`` differs on 12 / 12 / 10
  bars (1H / 4H / 1D; in Validation 0 / 0 / 2), ``pct_below`` on most bars, nothing else. Leaving the first,
  left-censored streak out of the statistics changes ``rare_now`` on 11 gold 4H bars and 1 gold 1D bar of
  Development (4 gold 1D bars with study 1's start), on none of the other series. A start one year later than study
  1's (gold 2018-01-02 against 2017-01-03: ``rare_now`` differs on 12 / 49 / 28 Development bars; BTC 2019-01-01
  against 2018-01-01: 296 / 312 / 28, and the HA candles of the first days of 2019 differ, which moves 1 / 4 / 0
  flips). So both ports must be fed the same bars; the study fixes the start. TradingView's chart start is unknown
  (the spec's "not testable").
* A tie ``haC == haO`` is bullish (l.85: ``>=``). No bar of the six series has an exact tie (data start to 2024-06),
  so the tie rule cannot change a signal on our bars (it is tested on synthetic bars).
* Zero-range candles (``rng == 0``) are STRONG as written; none occurs on the six series, so this cannot change a
  signal on our bars either.
* ``dir == dir[1]`` and ``body < body[1]`` on bar 0 compare with na: false (no WEAK on bar 0), Pine's rule for a
  comparison with na. Bar 0 is warm-up; no signal can depend on it.
* The arithmetic follows the script's order: ``haC`` summed left to right then divided by 4.0; each threshold is the
  input times ``rng`` (``dojiMax * rng``, ``0.1 * rng``, ``strongTol * rng``), not a ratio of wick to range; the
  percentage is ``(100.0 * c) / n``. The ratio form of the thresholds gives the same phase on every bar of the six
  series to 2024-06 (the wick against the colour is exactly 0 on 40-48 % of them, where both forms agree; elsewhere
  no wick, body or body difference comes closer to its threshold than 4e-10 of the price, against rounding errors
  of about 1e-16); the percentage's order cannot move ``rare_now`` (with n <= 5,000 an exact quotient below 90 is at
  least 1/n below it, far above rounding, and an exact 90 % is exactly 90.0 in both forms; it occurs on 3 gold 4H
  bars and 1 gold 1D bar of Development, each a rare-age bar under ``>=``). Kept as written so that the ports agree
  bit for bit.
* The bars are the study's (bid OHLC on UTC boundaries; a UTC day with fewer than 360 M1 bars merged into the next,
  PREREG 2), not TradingView's: colours can differ from a TradingView chart, most on 1D, whose gold bars close at
  the New York close.
Everything else follows the source literally; nothing is tuned (every default is the script's).

Speed: the HA recursion and the streak state machine are numba loops (``cache=True``): about 4 ms for BTC's 56,840
1H bars, after a first compilation of about 1.5 s (then cached by numba).
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
import pandas as pd
from numba import njit

__all__ = ["KEYS", "STREAK_COLUMNS", "STRONG", "STEADY", "WEAK", "INDECISION", "PHASE_NAMES", "KEEP", "DOJI_WICK",
           "heikin_ashi", "pct_below_of", "survive", "kept_lengths", "panel_at"]

KEYS = ("ha_o", "ha_h", "ha_l", "ha_c", "dir", "phase", "flip", "age", "strong_run", "weak_run", "ev_ind",
        "ev_first_strong", "pct_below", "rare_now", "streaks")
STREAK_COLUMNS = ("start_bar", "end_bar", "dir", "length", "had_strong", "strong_at", "ran_5_after_strong")

STRONG, STEADY, WEAK, INDECISION = 0, 1, 2, 3          # l.92: "phases: 0 STRONG · 1 STEADY · 2 WEAK · 3 INDECISION"
PHASE_NAMES = ("STRONG", "STEADY", "WEAK", "INDECISION")  # indexed by the code (l.245, l.272)
KEEP = 5000                                            # l.131-132: an array keeps its last 5,000 finished streaks
DOJI_WICK = 0.1                                        # l.93: both wicks of an INDECISION candle >= 0.1 * rng


# ───────────────────────────── input checks ─────────────────────────────

def _series(x, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)              # a copy: the caller's array is never modified
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D series is expected, got shape {a.shape}")
    return a


def _int_in(x, name: str, lo: int, hi: Optional[int] = None) -> int:
    """An ``input.int``: an integer in [lo, hi] (an integral float such as 5.0 is accepted)."""
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {x!r}")
    f = float(x)
    if not (math.isfinite(f) and f.is_integer() and f >= lo and (hi is None or f <= hi)):
        raise ValueError(f"{name}: an integer in [{lo}, {'inf' if hi is None else hi}] is expected, got {x!r}")
    return int(f)


def _float_in(x, name: str, lo: float, hi: float) -> float:
    """An ``input.float`` with its ``minval`` / ``maxval``."""
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected, got {x!r}")
    f = float(x)
    if not (math.isfinite(f) and lo <= f <= hi):
        raise ValueError(f"{name}: a number in [{lo}, {hi}] is expected (the script's input bounds), got {x!r}")
    return f


# ───────────────────────────── the bar loops (numba) ─────────────────────────────

@njit(cache=True)
def _ha_open(o, c, hac):
    """l.80-81: ``(open + close) / 2.0`` on bar 0, then ``(haO[1] + haC[1]) / 2.0``."""
    n = o.shape[0]
    hao = np.empty(n)
    if n > 0:
        hao[0] = (o[0] + c[0]) / 2.0
        for t in range(1, n):
            hao[t] = (hao[t - 1] + hac[t - 1]) / 2.0
    return hao


@njit(cache=True)
def _streak_kernel(d, ph, ahead_n, rare_pct, min_streaks, keep):
    """
    l.99-160 and l.204-212 per bar. The two arrays ``bullL`` / ``bearL`` are kept as a FIFO of their last ``keep``
    lengths (``push`` then ``shift`` past ``keep``) plus a count of the kept streaks by length, so that
    ``pctBelow(curA, age)`` is an O(1) update: ``curA`` does not change during a streak (only the colour of a
    streak that ends receives a push), hence the number of its entries below ``age`` grows by the count of the
    entries equal to ``age - 1`` at each new candle of the streak, and is 0 at age 1 (every length is >= 1).
    Colour index 0 = bullish, 1 = bearish.
    """
    n = d.shape[0]
    flip = np.zeros(n, np.bool_)
    age = np.zeros(n, np.int32)
    srun = np.zeros(n, np.int32)
    wrun = np.zeros(n, np.int32)
    evi = np.zeros(n, np.bool_)
    evf = np.zeros(n, np.bool_)
    pct = np.full(n, np.nan)
    rare = np.zeros(n, np.bool_)
    s_start = np.zeros(n, np.int64)
    s_dir = np.zeros(n, np.int8)
    s_len = np.zeros(n, np.int32)
    s_at = np.zeros(n, np.int32)
    ns = 0
    cnt = np.zeros((2, n + 2), np.int64)        # kept finished streaks of each colour, by length
    ring = np.zeros((2, keep + 1), np.int64)    # the kept lengths in push order (a spare slot: push, then shift)
    head = np.zeros(2, np.int64)
    size = np.zeros(2, np.int64)
    total = np.zeros(2, np.int64)               # every finished streak of each colour, kept or not
    sdir = 0                                    # var int sDir = 0 (l.106)
    a = 0                                       # var int age = 0 (l.107)
    strong_at = 0                               # var int strongAt = 0 (l.108)
    strong_run = 0                              # var int strongRun = 0 (l.109)
    weak_run = 0
    start = 0
    below = 0                                   # kept streaks of the current colour shorter than the age
    for t in range(n):
        dt = d[t]
        f = sdir != 0 and dt != sdir            # l.115
        if sdir == 0:                           # l.121-125: the chart's first bar
            sdir = dt
            a = 1
            start = t
        elif f:                                 # l.126-149
            k = 0 if sdir == 1 else 1           # a = sDir == 1 ? bullL : bearL: the colour of the streak that ends
            s_start[ns] = start
            s_dir[ns] = sdir
            s_len[ns] = a
            s_at[ns] = strong_at
            ns += 1
            pos = (head[k] + size[k]) % (keep + 1)
            ring[k, pos] = a                    # a.push(age)
            size[k] += 1
            total[k] += 1
            cnt[k, a] += 1
            if size[k] > keep:                  # if a.size() > 5000: a.shift()
                cnt[k, ring[k, head[k]]] -= 1
                head[k] = (head[k] + 1) % (keep + 1)
                size[k] -= 1
            sdir = dt
            a = 1
            strong_at = 0
            strong_run = 0
            weak_run = 0
            start = t
        else:                                   # l.150-151
            a += 1
        p = ph[t]
        evi[t] = p == 3 and strong_run >= 2     # l.156, after the flip's reset
        strong_run = strong_run + 1 if p == 0 else 0     # l.157
        if p == 0 and strong_at == 0:           # l.158-160
            strong_at = a
            evf[t] = True
        weak_run = weak_run + 1 if p == 2 else 0
        flip[t] = f
        age[t] = a
        srun[t] = strong_run
        wrun[t] = weak_run
        k = 0 if sdir == 1 else 1               # curA = sDir == 1 ? bullL : bearL (l.206)
        m = size[k]
        below_prev = below
        if a == 1:
            below = 0
        else:
            below += cnt[k, a - 1]
        if m > 0:                               # pctBelow: n > 0 ? 100.0 * c / n : na (l.173)
            p_now = 100.0 * below / m
            pct[t] = p_now
            p_prev = 100.0 * below_prev / m if a > 1 else 0.0            # l.211
            rare[t] = (total[k] >= min_streaks and p_now >= rare_pct
                       and (p_prev < rare_pct or a == 1))                 # l.212, at every bar
    return flip, age, srun, wrun, evi, evf, pct, rare, s_start[:ns], s_dir[:ns], s_len[:ns], s_at[:ns]


# ───────────────────────────── the indicator ─────────────────────────────

def heikin_ashi(o, h, l, c, strong_tol=0.05, doji_max=0.25, ahead_n=5, rare_pct=90,
                min_streaks=50, keep: Optional[int] = KEEP) -> Dict[str, object]:
    """
    The script on one chart's bars (bid OHLC, oldest first, no na), with its defaults and the plan's minimum of 50
    finished streaks for a rare age: a dict with the keys ``KEYS`` (the module docstring defines each one).
    ``strong_tol`` / ``doji_max`` / ``ahead_n`` / ``rare_pct`` are the script's inputs ``strongTol`` (l.20),
    ``dojiMax`` (l.22), ``aheadN`` (l.26) and ``rarePct`` (l.28). ``keep`` is the cap of l.131-132 on each colour's
    array of finished lengths: the script's ``KEEP`` = 5,000 by default (the reconciled contract); ``keep=None``
    keeps every finished streak since the first bar (``_heikin_ashi(..., keep=None)``, the plan's "all history",
    which the study-2 rule module uses). It moves only ``pct_below`` and ``rare_now``.
    """
    return _heikin_ashi(o, h, l, c, strong_tol, doji_max, ahead_n, rare_pct, min_streaks, keep)


def _heikin_ashi(o, h, l, c, strong_tol, doji_max, ahead_n, rare_pct, min_streaks,
                 keep: Optional[int] = KEEP) -> Dict[str, object]:
    """``heikin_ashi`` with the streak cap as an argument: ``keep=None`` keeps every finished streak (the "all
    history" reading of the plan, measured in the module docstring); the contract is ``keep=KEEP``."""
    o, h, l, c = (_series(x, k) for x, k in ((o, "o"), (h, "h"), (l, "l"), (c, "c")))
    n = len(c)
    if not len(o) == len(h) == len(l) == n:
        raise ValueError(f"o, h, l, c: series of equal length are expected, got {len(o)}, {len(h)}, {len(l)}, {n}")
    for x, k in ((o, "o"), (h, "h"), (l, "l"), (c, "c")):
        if not np.isfinite(x).all():
            raise ValueError(f"{k}: na or an infinite value at bar {int(np.argmax(~np.isfinite(x)))}; bars are "
                             "expected to be complete")
    strong_tol = _float_in(strong_tol, "strong_tol", 0.0, 0.3)       # l.20: minval 0.0, maxval 0.3
    doji_max = _float_in(doji_max, "doji_max", 0.05, 0.5)            # l.22: minval 0.05, maxval 0.5
    ahead_n = _int_in(ahead_n, "ahead_n", 1, 50)                     # l.26: minval 1, maxval 50
    rare_pct = _int_in(rare_pct, "rare_pct", 50, 99)                 # l.28: minval 50, maxval 99
    min_streaks = _int_in(min_streaks, "min_streaks", 0)
    keep = n + 1 if keep is None else _int_in(keep, "keep", 1)

    hac = (o + h + l + c) / 4.0                                      # l.79
    hao = _ha_open(o, c, hac)                                        # l.80-81
    hah = np.maximum(h, np.maximum(hao, hac))                        # l.82
    hal = np.minimum(l, np.minimum(hao, hac))                        # l.83
    d = np.where(hac >= hao, 1, -1).astype(np.int8)                  # l.85: a tie is bullish
    rng = hah - hal                                                  # l.86
    body = np.abs(hac - hao)                                         # l.87
    upw = hah - np.maximum(hao, hac)                                 # l.88
    low = np.minimum(hao, hac) - hal                                 # l.89
    oppw = np.where(d == 1, low, upw)                                # l.90
    doji = (rng > 0.0) & (body <= doji_max * rng) & (np.minimum(upw, low) >= DOJI_WICK * rng)    # l.93
    strong = oppw <= strong_tol * rng                                # l.94: 0 <= 0 on a zero range
    weak = np.zeros(n, np.bool_)
    weak[1:] = (d[1:] == d[:-1]) & (body[1:] < body[:-1])            # l.94: dir[1] / body[1] are na on bar 0
    phase = np.where(doji, INDECISION, np.where(strong, STRONG, np.where(weak, WEAK, STEADY))).astype(np.int8)

    (flip, age, srun, wrun, evi, evf, pct, rare,
     s_start, s_dir, s_len, s_at) = _streak_kernel(d, phase, ahead_n, rare_pct, min_streaks, keep)
    had = s_at > 0
    streaks = pd.DataFrame({
        "start_bar": s_start.astype(np.int64),
        "end_bar": (s_start + s_len.astype(np.int64) - 1).astype(np.int64),
        "dir": s_dir.astype(np.int8),
        "length": s_len.astype(np.int32),
        "had_strong": had,
        "strong_at": s_at.astype(np.int32),
        "ran_5_after_strong": had & (s_len.astype(np.int64) - s_at >= ahead_n),
    }, columns=list(STREAK_COLUMNS))

    return {
        "ha_o": hao, "ha_h": hah, "ha_l": hal, "ha_c": hac,
        "dir": d, "phase": phase, "flip": flip, "age": age, "strong_run": srun, "weak_run": wrun,
        "ev_ind": evi, "ev_first_strong": evf, "pct_below": pct, "rare_now": rare,
        "streaks": streaks,
    }


# ───────────────────────────── the panel's helpers (l.166-184, 242-284) ─────────────────────────────

def pct_below_of(lengths, v) -> float:
    """``pctBelow(a, v)`` (l.166-173): ``100.0 * c / n`` with c the entries ``< v``; NaN when ``a`` is empty."""
    a = np.asarray(lengths, dtype=np.int64)
    n = len(a)
    if n == 0:
        return math.nan
    return 100.0 * int(np.count_nonzero(a < int(v))) / n


def survive(lengths, a_age, x_more):
    """``survive(a, A, X)`` (l.176-184): ``(r, g)`` = the streaks that reached ``A`` (length >= A) and, of them, those
    that reached ``A + X``. The panel prints ``100.0 * g / r`` (l.281: "reached A → went X+ more")."""
    a = np.asarray(lengths, dtype=np.int64)
    a_age, x_more = int(a_age), int(x_more)
    return int(np.count_nonzero(a >= a_age)), int(np.count_nonzero(a >= a_age + x_more))


def kept_lengths(streaks: pd.DataFrame, bar: int, d: int, keep: Optional[int] = KEEP) -> np.ndarray:
    """The array ``bullL`` (``d = 1``) or ``bearL`` (``d = -1``) as the script holds it at the close of bar ``bar``:
    the lengths of the streaks of that colour finished by then (``end_bar < bar``: pushed at the flip bar
    ``end_bar + 1``), oldest first, the last ``keep`` of them (l.129-132; ``keep=None``: all)."""
    s = streaks[(streaks["dir"] == int(d)) & (streaks["end_bar"] < int(bar))]
    v = s["length"].to_numpy(np.int64)
    return v if keep is None or len(v) <= keep else v[len(v) - keep:]


def panel_at(out: Dict[str, object], bar: int, ahead_n: int = 5) -> Dict[str, float]:
    """
    The numbers the panel shows at the close of bar ``bar`` (l.242-284) for the colour of that bar's streak:
    ``n`` (finished streaks in its array), ``age``, ``pct_below`` (l.243), ``reached`` / ``went`` (``survive(curA,
    age, aheadN)``, l.280-281) and ``sn`` / ``sk`` (``bullSN`` / ``bullSK`` or the bear ones, l.282-284: every
    finished streak of the colour with a STRONG candle, and of them those that ran ``ahead_n`` or more candles
    after it). ``ahead_n`` is the script's ``aheadN``; ``went`` and ``sk`` are both computed with it here, from the
    streaks' ``length`` and ``strong_at`` (the ``ran_5_after_strong`` column is not read).
    """
    bar = int(bar)
    d = int(out["dir"][bar])
    age = int(out["age"][bar])
    st = out["streaks"]
    arr = kept_lengths(st, bar, d)
    reached, went = survive(arr, age, ahead_n)
    s = st[(st["dir"] == d) & (st["end_bar"] < bar)]
    had = s["had_strong"].to_numpy(bool)
    ran = had & (s["length"].to_numpy(np.int64) - s["strong_at"].to_numpy(np.int64) >= int(ahead_n))
    return {"dir": d, "n": len(arr), "age": age, "pct_below": pct_below_of(arr, age), "reached": reached,
            "went": went, "sn": int(had.sum()), "sk": int(ran.sum())}
