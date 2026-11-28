"""
The oracle of ``backtesting/research/tradeiq2_ind_ha.py``: PORT B of LunqFX's "Heikin Ashi Candles, Trend Strength &
Trend Age Stats" (TradeIQ study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.8).

What this is
------------
A literal, bar-by-bar transcription of the script's Pine v6 logic in plain Python (no numpy in the bar loop, no
numba), written to be obviously correct rather than fast. It was written from the Pine source and the study's
specification (``maps/orb_session_swing_ha.md`` section 4) only, without seeing port A. Line numbers ``l.NN`` refer to
the 327-line copy "Heikin Ashi Candles Trend Indicator.txt" of the study's source folder (third-party code: it is cited,
never copied). About 90 of its lines compute something (l.20-28 inputs, l.79-94 candles and phases, l.99-160 streaks
and events, l.166-184 statistics, l.204-212 the rare age); the rest draw candles, labels and the panel, or raise
alerts (l.290-303), which read only the series ported here.

How the transcription works: Pine runs the script once per bar, oldest bar first. Each Pine variable is one Python
variable with the script's name; a ``var`` variable (l.99-111, 205) keeps its value from bar to bar and starts at its
declared value; a variable declared without ``var`` (``haO`` l.80, ``flip``, ``evFirstSt``, ``evInd`` l.115-117) is
re-initialised on every bar, and its history ``x[1]`` is the value it ended the previous bar with (na before the first
bar). The script reads history only as ``haO[1]``, ``haC[1]`` (l.81), ``dir[1]`` and ``body[1]`` (l.94); they are
kept as ``prev_*`` variables. The two Pine arrays ``bullL`` / ``bearL`` (l.99-100) are Python lists, ``push`` is
``append`` and ``shift`` is ``pop(0)``; ``a = sDir == 1 ? bullL : bearL`` (l.129) is a reference to one of them, as a
Pine array id is.

The contract (identical in both ports, compared key by key)
-----------------------------------------------------------
``heikin_ashi(o, h, l, c, strong_tol=0.05, doji_max=0.25, ahead_n=5, rare_pct=90, min_streaks=50)`` returns a dict.
The inputs are the chart's bars, oldest first (the bid OHLC; the script reads no volume). The defaults are the
script's inputs (l.20 ``strongTol``, l.22 ``dojiMax``, l.26 ``aheadN``, l.28 ``rarePct``) and PREREG 6.8's minimum of
50 finished streaks for the rare age. Per-bar arrays of len(bars), bar 0 = the first bar given (``KEYS``):

==================  =======  ==========================================================================================
key                 dtype    value at bar t
==================  =======  ==========================================================================================
ha_c                float64  ``haC = (open + high + low + close) / 4.0`` (l.79), summed left to right
ha_o                float64  ``haO`` (l.80-81): ``(open + close) / 2.0`` on bar 0 (``haO[1]`` is na), then
                             ``(haO[1] + haC[1]) / 2.0``
ha_h                float64  ``math.max(high, math.max(haO, haC))`` (l.82)
ha_l                float64  ``math.min(low, math.min(haO, haC))`` (l.83)
dir                 int8     ``haC >= haO ? 1 : -1`` (l.85): a tie (body 0) is bullish
phase               int8     the script's own codes (comment l.92): 0 STRONG, 1 STEADY, 2 WEAK, 3 INDECISION, decided
                             in the script's order (l.93-94), first match wins: INDECISION if ``rng > 0 and body <=
                             dojiMax * rng and math.min(upW, loW) >= 0.1 * rng``; else STRONG if ``oppW <= strongTol *
                             rng`` (oppW = the wick against the colour, l.90); else WEAK if ``dir == dir[1] and body <
                             body[1]``; else STEADY. ``rng = haH - haL``, ``body = math.abs(haC - haO)``, ``upW = haH -
                             math.max(haO, haC)``, ``loW = math.min(haO, haC) - haL`` (l.86-89)
flip                bool     ``sDir != 0 and dir != sDir`` (l.115): a colour change against the previous bar; False on
                             bar 0
age                 int32    the current streak's age after the bar (l.123, 145, 151): 1 on bar 0 and on a flip bar,
                             else the previous age + 1
strong_run          int32    ``strongRun`` after this bar's update (l.157), the panel's "STRONG in a row" (l.277): the
                             consecutive STRONG candles of the current streak ending at bar t (reset at a flip, l.147)
weak_run            int32    not in the script (PREREG 6.8 M3, "2 consecutive WEAK candles"): the consecutive WEAK
                             candles of the current streak ending at bar t; 0 on any non-WEAK bar and on a flip bar
ev_ind              bool     ``evInd`` (l.156): an INDECISION candle while ``strongRun >= 2`` BEFORE this bar's update,
                             i.e. right after 2 or more consecutive STRONG candles of the same streak; False on a flip
                             bar (``strongRun`` was reset at l.147, before l.156)
ev_first_strong     bool     ``evFirstSt`` (l.158-160): the streak's first STRONG candle (``strongAt == 0``); it can be
                             the flip bar (``strongAt`` was reset at l.146) and bar 0
pct_below           float64  ``pctBelow(curA, age)`` (l.166-173, 206, 210) evaluated at EVERY bar: 100 x the share of
                             the finished streaks of the current streak's colour (as the script keeps them, at most
                             5000, see reading 9) that are strictly shorter than ``age``. NaN (Pine's na) while no
                             finished streak of that colour exists
rare_now            bool     ``rareNow`` (l.210-212) evaluated at EVERY bar as if it were the last bar (PREREG 6.8), AND
                             at least ``min_streaks`` finished streaks of that colour: ``pNow >= rarePct`` while
                             ``pPrev = pctBelow(curA, age - 1) < rarePct``; at most once per streak
==================  =======  ==========================================================================================

and ``streaks``: a pandas DataFrame of the FINISHED streaks, one row per flip, in order (``STREAK_COLUMNS``):
``start_bar`` (int64; bar 0 or the flip bar that began it), ``end_bar`` (int64; the bar before the flip that ended
it), ``dir`` (int8; its colour, ``sDir`` before l.144), ``length`` (int32; ``age`` pushed at l.130, = end_bar -
start_bar + 1), ``had_strong`` (bool; ``strongAt > 0`` at l.133), ``strong_at`` (int32; ``strongAt``, the age of its
first STRONG candle, 0 = none), ``ran_5_after_strong`` (bool; ``age - strongAt >= aheadN`` at l.136/139, with the
``ahead_n`` given; False without a STRONG candle). Every finished streak is listed, also those the 5000 cap has
dropped from the statistics. The streak still running at the last bar is not finished and not listed.

What is known when (no look-ahead)
----------------------------------
Every per-bar value at bar t is computed from bars 0 .. t only, so it is known at bar t's close and never changes
afterwards (no ``request.security``, no lookahead, no pivots; the script's header says so, l.10-11). On TradingView a
realtime bar is recomputed on every tick, and a colour, a phase or an event can change before the bar closes; on
closed bars, which is all we use, it is final (the alerts fire once per bar close, l.291-298). A streak's row in
``streaks`` is known at the close of its flip bar ``end_bar + 1``: a streak cannot be known to have ended before a
candle of the other colour has closed. The statistics at bar t use only the streaks finished at or before bar t;
those of the current colour all ended before the current streak began (colours alternate).
``tests/test_tradeiq2_ind_ha_b.py`` checks all of this by truncation.

The Pine readings (each one is a choice; the alternatives are named)
--------------------------------------------------------------------
1. ``haO``'s start (l.80-81). ``float haO = na`` is not a ``var``: it is re-declared na on every bar and immediately
   assigned, so ``haO[1]`` is the previous bar's final value and is na only on the first bar, which takes
   ``(open + close) / 2.0``. The first bar is the first bar GIVEN (the study's data start: gold 2016-01-03 with the
   2016 warm-up months, ``tradeiq2_market.data_start``; BTC 2018-01-01), not TradingView's first loaded bar. The
   recursion halves any difference of seeds every bar, so after about 50-60 bars the candles are bit-identical to
   those of any other start (51-57 bars at worst on our six charts; tested). Other Heikin Ashi scripts seed with
   ``open`` or with ``nz(haO[1])``; this one does not.
2. The colour (l.85): ``haC >= haO`` is bullish, so a body of exactly 0 is bullish, also right after a bear streak (it
   is then a flip to bull).
3. The order of the phase tests (l.93-94): the ternary chain is evaluated left to right, INDECISION first. With
   ``strongTol <= 0.1`` (the default is 0.05) a doji (both wicks >= 0.1 rng) cannot be STRONG anyway; with 0.1 <
   ``strongTol`` <= 0.3 (the input's range) the order decides. A doji whose body is smaller than the previous bar's
   is INDECISION, never WEAK, and a STRONG candle with a smaller body is STRONG, never WEAK.
4. A zero-range candle (``haH == haL``, so haO == haC == high == low): ``isDoji`` needs ``rng > 0``, and ``oppW = 0 <=
   strongTol * 0``, so it is STRONG (and bullish by the tie).
5. WEAK (l.94): ``dir == dir[1]`` compares with the previous BAR's colour, which is the streak's colour (``sDir`` at
   the bar's start), so a flip bar is never WEAK; ``body < body[1]`` is strict and compares with the previous bar's
   body whatever that bar's phase (STRONG, STEADY, WEAK or INDECISION). On bar 0 ``dir[1]`` and ``body[1]`` are na
   and both comparisons are false: not WEAK.
6. ``strongRun`` (l.147, 156-157): reset to 0 in the flip branch BEFORE ``evInd`` is evaluated, so ``evInd`` is false
   on every flip bar and a STRONG run of the previous streak never counts. ``evInd`` reads the run of the bars before
   this one; ``strong_run`` is the value after this bar's update.
7. ``evFirstSt`` (l.146, 158-160): ``strongAt`` is reset at the flip before l.158, so a STRONG flip bar is its streak's
   first STRONG candle, at age 1. It also fires on bar 0 when bar 0 is STRONG: the first streak starts there
   (l.121-125, ``strongAt`` starts at 0).
8. Streak lengths (l.126-139): pushed at the flip bar into the FINISHED streak's colour (``sDir`` before l.144); the
   length is ``age`` before the reset. The first streak, which starts at the first bar given, is pushed like any
   other although its true start is earlier (left-censored): the script does so. Alternative: leave it out of the
   statistics. Measured on the study's bars to 2024-06-30 (Development = the harness's decision bars of
   2019-2022): that changes ``rare_now`` on 11 gold 4H bars (its first streak is 12 bars long) and 1 gold 1D bar in
   Development, none in 2023-2024H1, and nothing on the other four charts. With study 1's later gold start
   (2017-01-03) it is gold 1D only (a first streak of 12 days): 4 Development bars and 4 in 2023-2024H1.
9. The cap (l.131-132): ``if a.size() > 5000: a.shift()`` keeps each colour's 5000 most recent lengths, and the
   statistics (``pct_below``, ``rare_now``'s count) use those. Kept, as the script's (``KEEP``). Alternative: no cap
   ("all history"); ``_transcribe(..., keep=None)`` exists only to measure it. Measured on the study's bars to
   2024-06-30: the cap binds only on 1H, from the 5001st streak of a colour: BTC from 2022-04-21, gold from
   2022-11-28 (from 2023-11-27 with study 1's later gold start; 4H and 1D never reach 5000). From then on
   ``pct_below`` differs (BTC 1H on 4,500 Development bars and 9,659 in 2023-2024H1; gold 1H on 398 and 6,594), but
   ``rare_now`` on no bar: the age at which 90% is reached is the same. The ``SN`` / ``SK`` counters (l.133-139) are
   not capped.
10. ``rareNow`` causally (l.204-212). The script evaluates it only on the last bar (``barstate.islast``), so on
    TradingView it is false on every historical bar and its alert works only live. As PREREG 6.8 registers, it is
    evaluated here at every bar t as if t were the last bar, with the arrays as they are at bar t's close (a push on
    a flip bar goes to the other colour). That is the value the live alert computes at that bar's close, so the
    ``var`` of l.205 (kept between assignments) changes nothing. Within a streak the current colour's array does not
    change, so ``pctBelow(curA, age)`` does not decrease with the age and the crossing happens at most once per
    streak; ``pPrev`` equals the previous bar's ``pct_below``. The clauses ``na(pPrev)`` and ``age == 1`` of l.212
    cannot change the result (``pPrev`` is na only when ``pNow`` is; at age 1 ``pNow`` is 0 < ``rarePct`` >= 50).
11. ``min_streaks`` (PREREG 6.8: "rare-age rules need at least 50 finished streaks of that colour"): ``rare_now`` is
    False while fewer than ``min_streaks`` streaks of the current colour have finished, all of them counted, also
    those the cap of reading 9 has dropped (the count of the current colour cannot change inside a streak, so the
    gate opens only at a flip). With the script's cap of 5000 above the plan's 50 this equals "the array holds at
    least ``min_streaks`` lengths"; the two differ only with a private ``keep`` below ``min_streaks``, where this
    port first counted the array and was aligned with port A at the reconciliation (``porting/ha.md``).
    ``pct_below`` is not gated; it is NaN only while that array is empty (Pine's na, l.173): on the bars before the
    second flip. On the study's bars the gate is open from 2016-01-27 (gold 1H), 2016-04-19 (gold 4H), 2017-11-07
    (gold 1D), 2018-01-18 (BTC 1H), 2018-03-08 (BTC 4H) and 2019-02-03 / 04 (BTC 1D, bear / bull).
12. ``pctBelow``'s arithmetic (l.173): ``100.0 * c / n`` left to right, i.e. ``(100.0 * c) / n``: an exact 90% is
    exactly 90.0. The count is strict (``x < v``): "longer than X% of past streaks" (l.218).
13. The statistics depend on the first bar given: the script's panel shows "more history, better numbers" (the
    video). The caller passes all bars from the data start (PREREG 6.8).
14. A missing price (NaN, inf) is refused: the script's handling of an na price (``haO`` would re-seed, l.81) is not
    ported, and our bars have none.

Not ported (display only): the extreme bar and price of a streak (``exBar`` / ``exPx``, l.110-111, 124-125, 148-154)
that place the length labels, the labels, the age label, the panel's text and histogram, the candles' colours. The
panel's other numbers are reproduced by ``survive`` (l.176-184) and ``strong_continuation`` (l.282-284) from the
``streaks`` frame, for the calibration check (PREREG 8, claim 5); they are not part of the compared contract.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "heikin_ashi", "pct_below_scan", "survive", "strong_continuation", "lengths_known_at",
    "KEYS", "STREAK_COLUMNS", "KEEP", "STRONG", "STEADY", "WEAK", "INDECISION", "PHASE_NAMES",
]

NAN = float("nan")

# the phase codes of the script (comment l.92)
STRONG, STEADY, WEAK, INDECISION = 0, 1, 2, 3
PHASE_NAMES = {STRONG: "STRONG", STEADY: "STEADY", WEAK: "WEAK", INDECISION: "INDECISION"}

KEEP = 5000                                     # l.131: each colour keeps at most 5000 finished lengths

KEYS = ("ha_o", "ha_h", "ha_l", "ha_c", "dir", "phase", "flip", "age", "strong_run", "weak_run",
        "ev_ind", "ev_first_strong", "pct_below", "rare_now")
DTYPES = {"ha_o": np.float64, "ha_h": np.float64, "ha_l": np.float64, "ha_c": np.float64,
          "dir": np.int8, "phase": np.int8, "flip": np.bool_, "age": np.int32, "strong_run": np.int32,
          "weak_run": np.int32, "ev_ind": np.bool_, "ev_first_strong": np.bool_, "pct_below": np.float64,
          "rare_now": np.bool_}
STREAK_COLUMNS = ("start_bar", "end_bar", "dir", "length", "had_strong", "strong_at", "ran_5_after_strong")
STREAK_DTYPES = {"start_bar": np.int64, "end_bar": np.int64, "dir": np.int8, "length": np.int32,
                 "had_strong": np.bool_, "strong_at": np.int32, "ran_5_after_strong": np.bool_}


# ───────────────────────────── Pine value helpers ─────────────────────────────

def is_na(x) -> bool:
    return x != x


def pmax(a: float, b: float) -> float:
    """``math.max`` of two non-na floats."""
    return a if a >= b else b


def pmin(a: float, b: float) -> float:
    """``math.min`` of two non-na floats."""
    return a if a <= b else b


# ───────────────────────────── input checks ─────────────────────────────

def _prices(o, h, l, c) -> Tuple[List[float], List[float], List[float], List[float]]:
    """The four price arrays as Python lists of floats (copies: the inputs are never changed)."""
    out = []
    n = None
    for name, x in (("o", o), ("h", h), ("l", l), ("c", c)):
        a = np.asarray(x, dtype=np.float64)
        if a.ndim != 1:
            raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
        if n is None:
            n = a.size
        elif a.size != n:
            raise ValueError(f"{name}: {a.size} bars, the other prices have {n}")
        if not bool(np.all(np.isfinite(a))):
            raise ValueError(f"{name}: NaN or inf at bar {int(np.argmin(np.isfinite(a)))}; the script's handling of "
                             "an na price is not ported (reading 14)")
        out.append([float(v) for v in a.tolist()])
    return out[0], out[1], out[2], out[3]


def _float_in(x, lo: float, hi: float, name: str) -> float:
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: a number is expected")
    f = float(x)
    if not (lo <= f <= hi):
        raise ValueError(f"{name}: {x!r} is outside the input's range [{lo}, {hi}]")
    return f


def _int_in(x, lo: int, hi: Optional[int], name: str) -> int:
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: an integer is expected")
    f = float(x)
    if not math.isfinite(f) or f != math.floor(f):      # finiteness first: math.floor(inf) raises OverflowError
        raise ValueError(f"{name}: an integer is expected, got {x!r}")
    i = int(f)
    if i < lo or (hi is not None and i > hi):
        raise ValueError(f"{name}: {x!r} is outside the input's range [{lo}, {hi if hi is not None else 'inf'}]")
    return i


# ───────────────────────────── the statistics helpers (l.166-184) ─────────────────────────────

def pct_below_scan(a: Sequence[int], v: int) -> float:
    """``pctBelow(a, v)`` (l.166-173): 100 x the share of the lengths in ``a`` that are strictly below ``v``, computed
    as ``(100.0 * c) / n`` (left to right); NaN (na) when ``a`` is empty. A literal scan of the whole array."""
    n = len(a)
    c = 0
    if n > 0:
        for x in a:
            if x < v:
                c += 1
    return 100.0 * c / n if n > 0 else NAN


def survive(a: Sequence[int], A: int, X: int) -> Tuple[int, int]:
    """``survive(a, A, X)`` (l.176-184): (r, g) = the lengths in ``a`` that reached age A (x >= A), and those of them
    that reached A + X. The panel's "reached A -> went X+ more" is 100 g / r (l.281). Panel only."""
    r = 0
    g = 0
    for x in a:
        if x >= A:
            r += 1
            if x >= A + X:
                g += 1
    return r, g


def strong_continuation(streaks: pd.DataFrame, d: int, upto_flip_bar: Optional[int] = None) -> Tuple[int, int]:
    """The script's counters (``bullSN`` / ``bullSK`` for d = +1, ``bearSN`` / ``bearSK`` for d = -1; l.101-104,
    133-139), shown in the panel as "after 1st STRONG -> 5+ more" = SK / SN (l.282-284): SN = the finished streaks of
    colour d that had a STRONG candle, SK = those of them that ran ``ahead_n`` or more candles after their first
    STRONG candle. Counted over every finished streak whose flip bar (``end_bar + 1``) is at or before
    ``upto_flip_bar`` (all of them if None): the counters are not capped. Panel only."""
    s = streaks
    if upto_flip_bar is not None:
        s = s[s["end_bar"] + 1 <= int(upto_flip_bar)]
    s = s[(s["dir"] == d) & s["had_strong"]]
    return int(len(s)), int(s["ran_5_after_strong"].sum())


def lengths_known_at(streaks: pd.DataFrame, d: int, t: int, keep: Optional[int] = KEEP) -> List[int]:
    """The script's array of colour d (``bullL`` for +1, ``bearL`` for -1) as it is at the close of bar t: the lengths
    of the finished streaks of colour d whose flip bar (``end_bar + 1``) is at or before t, oldest first, the last
    ``keep`` of them (l.130-132). For the calibration check (PREREG 8, claim 5) and the tests."""
    s = streaks[(streaks["dir"] == d) & (streaks["end_bar"] + 1 <= int(t))]
    out = [int(x) for x in s["length"].tolist()]
    if keep is not None and len(out) > keep:
        out = out[len(out) - keep:]
    return out


# ───────────────────────────── the script, bar by bar ─────────────────────────────

def heikin_ashi(o, h, l, c, strong_tol: float = 0.05, doji_max: float = 0.25, ahead_n: int = 5, rare_pct: int = 90,
                min_streaks: int = 50) -> Dict[str, object]:
    """The script's candles, phases, streaks, events and causal statistics; see the module docstring for the contract
    (``KEYS`` per bar, plus ``streaks``) and the readings."""
    return _transcribe(o, h, l, c, strong_tol, doji_max, ahead_n, rare_pct, min_streaks, keep=KEEP)


def _transcribe(o, h, l, c, strong_tol: float = 0.05, doji_max: float = 0.25, ahead_n: int = 5, rare_pct: int = 90,
                min_streaks: int = 50, keep: Optional[int] = KEEP) -> Dict[str, object]:
    """The bar loop. ``keep`` is the cap of l.131 (5000); ``keep=None`` (no cap) is the alternative of reading 9 and
    exists only to measure it."""
    opens, highs, lows, closes = _prices(o, h, l, c)
    strongTol = _float_in(strong_tol, 0.0, 0.3, "strong_tol")          # l.20: minval 0.0, maxval 0.3
    dojiMax = _float_in(doji_max, 0.05, 0.5, "doji_max")              # l.22: minval 0.05, maxval 0.5
    aheadN = _int_in(ahead_n, 1, 50, "ahead_n")                       # l.26: minval 1, maxval 50
    rarePct = _int_in(rare_pct, 50, 99, "rare_pct")                   # l.28: minval 50, maxval 99
    minStreaks = _int_in(min_streaks, 0, None, "min_streaks")         # PREREG 6.8
    if keep is not None:
        keep = _int_in(keep, 1, None, "keep")
    nbars = len(opens)

    out = {k: [] for k in KEYS}
    rows = []

    # the history the script reads: haO[1], haC[1] (l.81), dir[1], body[1] (l.94); na before bar 0
    prev_haO = NAN
    prev_haC = NAN
    prev_dir = None                     # an int series: na before bar 0
    prev_body = NAN

    # l.99-111: var state
    bullL: List[int] = []
    bearL: List[int] = []
    bullSN = 0
    bullSK = 0
    bearSN = 0
    bearSK = 0
    sDir = 0
    age = 0
    strongAt = 0
    strongRun = 0
    # ours: the start bar of the current streak (for the streaks frame), the WEAK run (PREREG M3) and the number of
    # finished streaks of each colour, the cap's dropped ones included (PREREG 6.8's minimum, reading 11)
    start_bar = 0
    weakRun = 0
    bullN = 0
    bearN = 0

    for t in range(nbars):
        open_, high, low, close = opens[t], highs[t], lows[t], closes[t]

        # l.79-83: Heikin Ashi
        haC = (open_ + high + low + close) / 4.0
        if is_na(prev_haO):
            haO = (open_ + close) / 2.0
        else:
            haO = (prev_haO + prev_haC) / 2.0
        haH = pmax(high, pmax(haO, haC))
        haL = pmin(low, pmin(haO, haC))

        # l.85-90
        dir_ = 1 if haC >= haO else -1
        rng = haH - haL
        body = abs(haC - haO)
        upW = haH - pmax(haO, haC)
        loW = pmin(haO, haC) - haL
        oppW = loW if dir_ == 1 else upW

        # l.93-94: first match wins (INDECISION, STRONG, WEAK, STEADY)
        isDoji = rng > 0 and body <= dojiMax * rng and pmin(upW, loW) >= 0.1 * rng
        same_dir = prev_dir is not None and dir_ == prev_dir           # dir == dir[1]: false while dir[1] is na
        smaller = (not is_na(prev_body)) and body < prev_body          # body < body[1]: false while body[1] is na
        if isDoji:
            phase = INDECISION
        elif oppW <= strongTol * rng:
            phase = STRONG
        elif same_dir and smaller:
            phase = WEAK
        else:
            phase = STEADY

        # l.115-118
        flip = sDir != 0 and dir_ != sDir
        evFirstSt = False
        evInd = False

        # l.121-154
        if sDir == 0:
            sDir = dir_
            age = 1
            start_bar = t
        elif flip:
            a = bullL if sDir == 1 else bearL                           # l.129: a reference to one of the arrays
            a.append(age)                                               # l.130
            if keep is not None and len(a) > keep:                      # l.131-132
                a.pop(0)
            if sDir == 1:                                               # ours (reading 11): every finished streak
                bullN += 1
            else:
                bearN += 1
            ran = False
            if strongAt > 0:                                            # l.133-139
                ran = age - strongAt >= aheadN
                if sDir == 1:
                    bullSN += 1
                    bullSK += 1 if ran else 0
                else:
                    bearSN += 1
                    bearSK += 1 if ran else 0
            rows.append((start_bar, t - 1, sDir, age, strongAt > 0, strongAt, ran))
            sDir = dir_                                                 # l.144-147
            age = 1
            strongAt = 0
            strongRun = 0
            start_bar = t
        else:
            age += 1                                                    # l.151

        # l.156-160
        evInd = phase == INDECISION and strongRun >= 2
        strongRun = strongRun + 1 if phase == STRONG else 0
        if phase == STRONG and strongAt == 0:
            strongAt = age
            evFirstSt = True

        # ours: consecutive WEAK candles of the current streak (a flip bar is never WEAK, reading 5)
        if phase == WEAK:
            weakRun = 1 if flip else weakRun + 1
        else:
            weakRun = 0

        # l.204-212, evaluated at every bar as if it were the last one (reading 10)
        curA = bullL if sDir == 1 else bearL                            # l.206
        pNow = pct_below_scan(curA, age)                                # l.210
        pPrev = pct_below_scan(curA, age - 1) if age > 1 else 0.0       # l.211
        rareNow = (not is_na(pNow)) and pNow >= rarePct and (is_na(pPrev) or pPrev < rarePct or age == 1)
        rare = rareNow and (bullN if sDir == 1 else bearN) >= minStreaks   # PREREG 6.8 (reading 11)

        out["ha_o"].append(haO)
        out["ha_h"].append(haH)
        out["ha_l"].append(haL)
        out["ha_c"].append(haC)
        out["dir"].append(dir_)
        out["phase"].append(phase)
        out["flip"].append(flip)
        out["age"].append(age)
        out["strong_run"].append(strongRun)
        out["weak_run"].append(weakRun)
        out["ev_ind"].append(evInd)
        out["ev_first_strong"].append(evFirstSt)
        out["pct_below"].append(pNow)
        out["rare_now"].append(rare)

        prev_haO, prev_haC, prev_dir, prev_body = haO, haC, dir_, body

    res: Dict[str, object] = {k: np.array(out[k], dtype=DTYPES[k]) for k in KEYS}
    frame = pd.DataFrame(rows, columns=list(STREAK_COLUMNS))
    res["streaks"] = frame.astype(STREAK_DTYPES) if len(frame) else pd.DataFrame(
        {k: np.array([], dtype=v) for k, v in STREAK_DTYPES.items()})
    return res
