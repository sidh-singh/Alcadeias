"""
PORT B (the oracle) of "Session Hunter [TradeIQ]": a literal, bar-by-bar transcription of its five setups, its seven
confirmations and its own trade manager.

Study 2 of the TradeIQ research, ``backtest_results/tradeiq_2027/PREREG.md`` (frozen): the script is its section 6.6
and claim 10 of section 8. As in study 1, two engineers port the script independently from the Pine source. Port A is
``backtesting/research/tradeiq2_ind_session.py`` (the fast one the study runs). This file is port B: plain Python, one
small object per Pine ``var`` / UDT holding the state the script keeps, every statement evaluated bar by bar in the
script's order, written to be obviously correct rather than fast. It is the reference port A is checked against. It
imports nothing of the study's indicator code (not ``tradeiq_ind.py``, no ``tradeiq2_ind_*`` module): its Pine
primitives are written below from TradingView's "same on pine" reference code, and the only repository function it
calls is ``external.local_seconds`` (the New York wall clock). Its tests are ``tests/test_tradeiq2_ind_session_b.py``.

``Lnnn`` is a line of the Pine source "TradeIQ Session Hunter Indicator.txt" (535 lines, ``//@version=6``, MPL-2.0,
(c) TradeIQ). The source is third-party code and is not in the repository; only line numbers and identifiers are cited.

Reconciled with port A (``tests/test_tradeiq2_ind_session.py``; the record is
``backtest_results/tradeiq_2027/porting/session.md``): on the real M5 and M15 bars of both symbols, from their data
start to 2024-06-30, the two ports give the same event tables, per-bar series and 1H EMA, bit for bit, for every
configuration the plan runs. The reconciliation changed no number of either port. It aligned the contract (the exit
columns' names and labels below, which port A had named first) and reading R1, which this port now reads as port A
does.

The contract (the same function names and output keys in both ports, so they can be compared mechanically)
-----------------------------------------------------------------------------------------------------------
``session_hunter(t, o, h, l, c, v, tf_min, htf_dir, setups=('AS','LS','PD','AB','OR'), conf=('FVG','HTF'),
monday_friday_levels=False, min_stop_atr=0.5)`` -> ``pandas.DataFrame``, one row per signal, in bar order and, on one
bar, in the script's order AS, LS, PD, AB, OR (L412-421):

* inputs: chart bars of ``tf_min`` minutes (5 or 15; 60 works too, information only) with open times ``t`` (UTC
  seconds, strictly increasing), the bid ``o``, ``h``, ``l``, ``c`` and the volume ``v`` (read only by 'RV'); ``htf_dir``
  one value per bar for the 'HTF' confirmation: +1 / -1 / 0 (NaN counts as 0). The script's own series is
  ``htf_ema_dir(t, c, h1_bars)`` below; the study passes others for its F2 / F3 rows.
* ``setups``: the switched-on setups (``eAS`` .. ``eOR``, L100-104): 'AS' Asia sweep, 'LS' London sweep, 'PD'
  previous-day sweep, 'AB' Asia breakout, 'OR' opening-range breakout. ``conf``: the switched-on confirmations
  (``cFVG`` .. ``cDB``, L105-111): 'FVG', 'MSS', 'HTF', 'PD' (premium / discount vs the midnight open), 'RV'
  (relative volume), 'TIGHT' (the range under 50% of the average day), 'YC' (yesterday's candle). Every other input is
  the script's default: ``htfLen`` 200 (L61), ``rvK`` 1.5 (L64), ``adrPct`` 50 (L66), ``tp2`` 2.0 (L78), ``cost`` 0 (L82);
  ``min_stop_atr`` is ``minStop`` (L81, default 0.5).
* ``monday_friday_levels=True``: the logged variant (PREREG 6.6, information only) in which the first weekday after a
  weekend pseudo-day keeps ``pWk`` true, so Monday's PD setup and 'YC' read Friday's levels. False: the script.
* columns:

  ======================  =====================================================================================
  ``setup``               'AS' | 'LS' | 'PD' | 'AB' | 'OR'
  ``bar``                 the signal bar (index into the inputs); the signal is known at its close
  ``t_signal``            that close: ``t[bar] + 60 * tf_min`` (UTC s)
  ``dir``                 +1 long, -1 short
  ``stop``                the absolute stop level after the minimum-stop rule (``f_new``, L400-402)
  ``tgt_ref``             the opposite liquidity level (L403): the far side of the swept range for a fade, the
                          broken side plus one range width for a breakout
  ``r_hi``, ``r_lo``      the range the setup traded (``rH``, ``rL`` of ``f_new``, L413-421)
  ``entry_bar``           ``bar + 1``: the bar whose open is the entry (L427), whether or not it exists
  ``cancelled``           None, or why the entry was dropped on ``entry_bar`` (L428-435): 'closeT' (that bar is in
                          16:00-20:00 New York), 'new_day' (it starts a new trading day), 'risk<=0' (its open equals
                          the stop), 'open_beyond_stop' (its open is beyond the stop). None also when ``entry_bar``
                          is not in the data (the decision is still pending).
  ``exit_bar_<m>``        for each exit mode ``m`` of the script's trade manager (L436-492): 'hold' = "Hold to
  ``exit_price_<m>``      16:00 NY" (E1), 'tp2' = "At TP2" (E2), 'liq' = "Opposite liquidity" (E3). The bar on which
  ``exit_reason_<m>``     the script books the exit, the exit price, why ('new_day': at the previous bar's close on
  ``R_<m>``               the first bar of the next day; 'closeT': at the open of the first bar from 16:00; 'stop':
                          at the stop level; 'target': at the target level) and ``R = (d * (x - e) - 2 * cost) / risk``
                          with ``e`` the entry bar's open (the bid open) and ``cost`` 0 (L482). No exit: -1, NaN, NaN,
                          and the reason says why: None (``cancelled`` is set), 'pending' (``entry_bar`` is not in
                          the data yet), 'open' (entered and still open at the last bar), 'cancel_lt_1R' (E3 only:
                          its own cancel, L437, the target less than 1R from the entry open).
  ======================  =====================================================================================

``htf_ema_dir(t, c_chart, h1_bars, length=200)`` -> int8 array: sign(close - htfE) per chart bar, 0 where htfE is na.
``htfE`` = ``htf_ema(t, h1_bars, length=200, seed='first')`` = ``request.security(syminfo.tickerid, "60",
ta.ema(close, 200)[1], lookahead = barmerge.lookahead_on)`` (L145): with ``lookahead_on`` the chart bar gets the value
of ``ema[1]`` on the 1H bar that contains its open, i.e. the EMA200 of the last 1H bar CLOSED AT OR BEFORE THE CHART
BAR'S OPEN (``h1_bars.tc <= t``). ``h1_bars``: any object with numpy arrays ``tc`` (close times, strictly
increasing) and ``c``: study 1's ``tradeiq_market.TMarket.tbars('1H')``. ``htf_ema_at_open`` is the same function
under its first name.

Also compared with port A: ``session_series`` (every per-bar series the rules read) against port A's ``clock``,
``shared_series`` and ``day_state``. Not part of the contract: the Pine primitives ``pine_sma``, ``pine_rma``,
``pine_tr``, ``pine_atr``, ``pine_ema``, ``pine_highest``, ``pine_lowest`` and ``ny_clock``.

Inputs refused (``ValueError``), as in port A: open times that are not strictly increasing, series of another length,
non-finite prices, an unknown setup or confirmation, a string instead of a sequence of names, a ``tf_min`` that is not
a whole number >= 1, a ``min_stop_atr`` that is not a finite number > 0, ``v=None`` with 'RV', ``htf_dir=None`` with
'HTF' (``v`` and ``htf_dir`` may be None otherwise). The inputs are never modified.

What is computed, statement by statement (all on the chart's bars)
-----------------------------------------------------------------
1. **Clock** (L127-140). ``nyMin`` = hour * 60 + minute of the bar's OPEN time in America/New_York (daylight saving
   included). ``dk`` = year * 10000 + month * 100 + day of ``time + 4h`` in New York, so a trading day runs from 20:00 to
   20:00 New York and the Asian session (20:00-24:00) belongs to the next day; ``dow`` = Pine's ``dayofweek`` of the
   same instant (Sunday 1 .. Saturday 7) and ``weekday`` = Monday to Friday. ``newDay = dk != dk[1]``. ``f_in(s0, s1)``
   = the WHOLE bar is inside the window: ``nyMin >= s0 and nyMin + tfMin <= s1``. Asia ``nyMin >= 1200 and nyMin +
   tfMin <= 1440``; London f_in(120, 300); New York f_in(420, 660); PM f_in(810, 960) (display only); the opening range
   f_in(570, 600) only when ``tfMin < 60``; ``closeT`` = 16:00 <= nyMin < 20:00.
2. **Shared series** (L143-152). ``atr`` = ``ta.atr(14)`` = ``ta.rma(ta.tr(true), 14)`` (the true range is high - low on
   bar 0; the RMA is seeded with the SMA of its first 14 values). ``vAvg`` = ``ta.sma(volume, 20)``. ``fvgUp`` = ``low >
   high[2] or low[1] > high[3] or low[2] > high[4] or low[3] > high[5]`` (a gap in any of the last four three-bar groups;
   never checked for being filled) and ``fvgDn`` its mirror. ``hi5`` = ``ta.highest(high, 5)[1]`` = max(high[1..5]),
   ``lo5`` = min(low[1..5]) (the ``[1]`` leaves the current bar out).
3. **Day state** (L190-213), on ``newDay``: if the finished day was a weekday (``dWk``) its range ``dH - dL`` is pushed to
   ``ranges`` (the last 10 are kept) and ``pdh``, ``pdl``, ``pO``, ``pC`` take its high, low, open and last close
   (``close[1]``); otherwise they keep their values. ``pWk := dWk``. Then ``dH``, ``dL``, ``dO`` restart from this bar,
   ``dWk := weekday``, and the midnight open ``mo``, the six session levels, the three done flags and the five setup
   states (``St``) are reset. Otherwise ``dH``, ``dL`` extend. ``adr`` = the mean of ``ranges`` once it holds 5 or more.
   ``mo`` = the open of the first bar of the day with ``nyMin < 1200`` (from 00:00 New York; on a day that starts
   later, its first bar).
4. **Sessions** (L216-233): ``asH/asL``, ``loH/loL``, ``oH/oL`` accumulate over the session's bars; ``asDone``, ``loDone``,
   ``oDone`` are set on the first bar after an Asia / London / opening-range bar (``inAsia[1] and not inAsia``).
5. **Setups** (L360-364), each with its own ``St`` (one lane, at most one signal a day):

   * AS ``f_rev(stAS, asDone ? asH : na, asL, f_in(120, 300))``, LS ``f_rev(stLS, loDone ? loH : na, loL, f_in(420,
     660))``, PD ``f_rev(stPD, pdh, pdl, f_in(120, 660))`` only while ``pWk``, AB ``f_brk(stAB, asDone ? asH : na, asL,
     f_in(120, 300))``, OR ``f_brk(stOR, oDone ? oH : na, oL, f_in(600, 720))`` only when ``tfMin < 60``.
   * ``f_rev`` (L331-347), inside the window on a weekday while neither ``done`` nor ``dead`` and ``rH > rL``: a high
     above ``rH`` sets ``sH`` and extends ``upEx`` (the running max of those highs, window bars only); a low below ``rL``
     sets ``sL`` and extends ``dnEx``; both swept -> ``dead`` for the day; otherwise a close strictly inside (rL, rH)
     gives -1 if the high was swept, else +1 if the low was, and the signal fires when ``f_conf`` passes (then
     ``done``). The sweep and the close back inside may be on different bars; a price already beyond the level when
     the window opens counts as a sweep; a bar that fails the confirmations does not end the setup.
   * ``f_brk`` (L350-358): the first close outside the range inside the window (+1 above ``rH``, -1 below ``rL``) that
     passes ``f_conf`` sets ``done``; it is a signal only if ``|close - (rH + rL) / 2| <= 4 * atr``.
   * ``f_conf`` (L312-328): every switched-on confirmation must hold: FVG ``dd > 0 ? fvgUp : fvgDn``; MSS ``dd > 0 ?
     close > hi5 : close < lo5``; HTF ``not na(htfE) and dd * (close - htfE) > 0``, here ``dd * htf_dir > 0``; PD ``not
     na(mo) and dd * (mo - close) > 0``; RV ``volume >= 1.5 * vAvg``; TIGHT ``not na(adr) and rH - rL < 50 / 100.0 *
     adr``; YC ``pWk and dd * (pC - pO) > 0``.
6. **New trade** (``f_new``, L399-410): stop = ``upEx`` (short) / ``dnEx`` (long) for a fade, the midpoint ``(rH + rL) /
   2`` for a breakout; if ``|close - stop| < minStop * atr`` the stop becomes ``close - dd * minStop * atr`` (from the
   SIGNAL bar's close). ``tgtRef`` = ``rev ? (dd < 0 ? rL : rH) : (dd > 0 ? rH : rL) + dd * (rH - rL)``.
7. **Trade manager** (L424-492), on every bar after the signals of that bar, over the open trades from the newest to
   the oldest (``for i = open_.size() - 1 to 0``), one manager per exit mode:

   * on the first bar after the signal (``bar_index > T.sb``): cancelled if that bar is ``closeT`` or ``newDay``;
     else ``e = open``, ``risk = |open - stop|``, cancelled if ``risk <= 0 or d * (open - stop) <= 0`` (the open at or
     beyond the stop: the spec's fill-beyond-stop trap is the script's own rule); the target is none (hold),
     ``open + d * tp2 * risk`` (tp2) or ``tgtRef`` (liq; cancelled if ``d * (tgt - open) < risk``);
   * on every live bar, the entry bar included, the first that applies: (1) ``newDay`` after the entry bar: exit at
     ``close[1]``; (2) ``closeT`` after the entry bar: exit at the open; (3) the stop touched (``low <= stop`` /
     ``high >= stop``): exit AT the stop, a gap included; (4) the target touched: exit at the target.

What is known when
------------------
Every series of bar i uses bars 0..i only (``htf_dir`` must be known at bar i's close; the script's own is known at its
OPEN). A signal and its stop / target are known at the close of the signal bar (``t_signal``); ``cancelled`` and the
entry at ``entry_bar``'s open; an exit on its bar (a 'new_day' exit is booked on the first bar of the new day at the
previous bar's close, as the script books it). Nothing repaints: no pivots, no ``barstate`` branches, and
``request.security`` with ``[1]`` and ``lookahead_on`` reads only closed 1H bars. Removing the bars after T leaves
every output decided by T unchanged (tests).

Pine readings where the semantics are not spelled out (R1-R10; the tests pin each choice)
----------------------------------------------------------------------------------------
R1. ``newDay`` on bar 0, where ``dk[1]`` is na (L133): FALSE, a comparison with na is false (study 1's reading of
    every comparison with na, port A's, and the other study-2 ports'; TradingView's reference only warns against
    comparing with na and does not say what it gives). Then ``math.max(dH, high)`` stays na (``math.max`` of an na is
    na) and the first, usually partial day never feeds ``pdh/pdl``, ``ranges`` or ``pWk``. This port was written with
    the other reading, TRUE (na as an IEEE NaN, so ``!=`` is true: the first day is a day of its own and can be
    "yesterday" for the second), and took port A's in the reconciliation; ``_run(first_bar_new_day=True)`` keeps it, to
    measure it. Only the first two trading days of the input can differ: on M5 / M15 bars that start on 2019-01-01, one
    PD signal of BTC (2019-01-01, whose "yesterday" would be the 19:00-20:00 stub of 2018-12-31) and none of gold; on
    the study's bars, which start on a weekend pseudo-day of both symbols (Sunday 2016-01-03 18:00 / 2017-12-31 19:00
    New York), nothing at all (``tests/test_tradeiq2_ind_session.py``).
R2. ``ta.ema`` (L145) is seeded with the first close (TradingView's ``pine_ema``, study 1's reading); alternative: na
    for 199 bars, then the SMA of the first 200 (``htf_ema_at_open(seed="sma")``). With 1H bars from 2017 (gold) /
    2018 (BTC) the two give the same htfE from 2019 on (tests).
R3. ``ta.highest`` / ``ta.lowest`` (L148, L152) are na until ``length`` bars exist (as ``ta.sma``); alternative: the
    partial window. Only bars 0-5 of the input can differ.
R4. ``ranges.avg()`` (L211) = the sequential sum of the stored ranges, oldest first, divided by their number;
    alternative: another summation order (numpy's pairwise sum). A last-bit difference could only flip 'TIGHT' on an
    exact tie.
R5. On an entry bar that is both ``closeT`` and ``newDay`` (a data gap into 16:00-20:00 of a later day) the cancel is
    labelled 'closeT' (the first operand of ``closeT or newDay``, L428); on ``open == stop`` 'risk<=0' (the first
    operand of L433). The script cancels both ways alike: labels only.
R6. A 'new_day' exit (L454-455) is booked on the new day's first bar (``exit_bar``) at the previous bar's close
    (``exit_price = close[exit_bar - 1]``), as the script books it.
R7. ``monday_friday_levels``: ``pWk := dWk or pWk``, i.e. a finished non-weekday pseudo-day keeps the previous weekday's
    ``pWk`` (and ``pdh/pdl/pO/pC`` keep that weekday's values, as in the script), so the first weekday after a weekend
    (Monday, or Tuesday when Monday has no bars) reads the last weekday's levels.
R8. ``ta.sma`` (L144) and the RMA seed: TradingView's ``pine_sma`` arithmetic, ``sum := sum + x[i] / y`` from the newest
    value (i = 0) to the oldest; the RMA ``alpha * src + (1 - alpha) * sum[1]``, ``alpha = 1 / 14`` (study 1's reading,
    which ``tests/tradeiq_oracle.py`` verified bit for bit).
R9. Pine v6: a ``bool`` series is never na, so ``inAsia[1]`` on bar 0 is false (L225-227); ``and`` / ``or`` short-
    circuit, which changes nothing here (``f_conf`` has no side effects); only the selected branch of ``?:`` runs, so
    an off setup's ``St`` is never touched (L360-364).
R10. The 1H history ``request.security`` computes the EMA on (L145): every 1H bar the caller passes (the study passes
    its own market's 1H bars from the data start, gold 2016-01 and BTC 2018-01); a TradingView chart may load 1H bars
    only from about its own first bar. With 1H bars cut at a chart start of 2019-01-02 the htfE values differ until
    mid-2019: measured in the reconciliation on the study's bars, the 'HTF' signs differ on 536 / 182 gold bars (M5 /
    M15, the last on 2019-02-26) and 539 / 183 BTC bars (the last on 2019-01-06), and 10 / 10 (gold) and 6 / 5 (BTC)
    K2 signals of 2019-2022, all before 2019-01-24.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from backtesting.research import external as X       # the New York clock only (local_seconds)

NY = "America/New_York"                               # L12
NAN = math.nan

SETUPS = ("AS", "LS", "PD", "AB", "OR")                # the script's order of f_new (L412-421)
SETUP_NAMES = {"AS": "Asia sweep", "LS": "London sweep", "PD": "PD sweep", "AB": "Asia breakout", "OR": "OR breakout"}
CONFIRMATIONS = ("FVG", "MSS", "HTF", "PD", "RV", "TIGHT", "YC")
MODES = ("hold", "tp2", "liq")
CANCELS = ("closeT", "new_day", "open_beyond_stop", "risk<=0")      # port A's order (labels, L428-435)
EXITS = ("stop", "target", "closeT", "new_day")                    # the exits the managers book (L454-461)
LIQ_CANCEL = "cancel_lt_1R"                                         # E3's own cancel (L437)
OPEN = "open"                                                       # entered, still open at the last bar
PENDING = "pending"                                                 # the entry bar is not in the data yet
EXIT_REASONS = EXITS + (OPEN, LIQ_CANCEL, PENDING)                  # every exit_reason_<m> but None (port A's)

# the script's defaults (the inputs this port does not expose)
ATR_LEN = 14          # L143 ta.atr(14)
VOL_LEN = 20          # L144 ta.sma(volume, 20)
HTF_LEN = 200         # L61 htfLen
RV_K = 1.5            # L64 rvK
ADR_PCT = 50          # L66 adrPct
TP2 = 2.0             # L78 tp2
COST = 0.0            # L82 cost
RANGES_KEPT = 10      # L193
ADR_MIN = 5           # L211
BRK_ATR = 4           # L356

COLUMNS = ("setup", "bar", "t_signal", "dir", "stop", "tgt_ref", "r_hi", "r_lo", "entry_bar", "cancelled") + tuple(
    f"{k}_{m}" for m in MODES for k in ("exit_bar", "exit_price", "exit_reason", "R"))


def isna(x) -> bool:
    """Pine ``na(x)`` for a float."""
    return x != x


def pmax(a: float, b: float) -> float:
    """Pine ``math.max`` of two floats: na when either is na."""
    if isna(a) or isna(b):
        return NAN
    return a if a >= b else b


def pmin(a: float, b: float) -> float:
    """Pine ``math.min`` of two floats: na when either is na."""
    if isna(a) or isna(b):
        return NAN
    return a if a <= b else b


# ───────────────────────────── Pine primitives (TradingView's "same on pine" code) ─────────────────────────────

def _floats(x, name: str) -> List[float]:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1:
        raise ValueError(f"{name}: a 1-D array is expected, got shape {a.shape}")
    return a.tolist()


def pine_sma(x, n: int) -> np.ndarray:
    """``ta.sma(x, n)``: pine_sma, ``sum := sum + x[i] / n`` for i = 0 (this bar) .. n - 1; na until n values exist."""
    xs = _floats(x, "x")
    out = [NAN] * len(xs)
    for t in range(n - 1, len(xs)):
        s = 0.0
        for i in range(n):
            s = s + xs[t - i] / n
        out[t] = s
    return np.asarray(out, dtype=np.float64)


def pine_rma(x, n: int) -> np.ndarray:
    """``ta.rma(x, n)``: pine_rma, ``sum := na(sum[1]) ? ta.sma(x, n) : alpha * x + (1 - alpha) * nz(sum[1])``,
    ``alpha = 1 / n``."""
    xs = _floats(x, "x")
    seed = pine_sma(xs, n).tolist()
    alpha = 1 / n
    out = [NAN] * len(xs)
    prev = NAN
    for t in range(len(xs)):
        if isna(prev):
            val = seed[t]
        else:
            val = alpha * xs[t] + (1 - alpha) * prev
        out[t] = val
        prev = val
    return np.asarray(out, dtype=np.float64)


def pine_tr(h, l, c) -> np.ndarray:
    """``ta.tr(true)``: high - low on bar 0 (``na(high[1])``), else max(max(high - low, |high - close[1]|),
    |low - close[1]|) (the reference's pine_atr)."""
    H, L, C = _floats(h, "high"), _floats(l, "low"), _floats(c, "close")
    out = [NAN] * len(H)
    for t in range(len(H)):
        if t == 0:
            out[t] = H[t] - L[t]
        else:
            out[t] = max(max(H[t] - L[t], abs(H[t] - C[t - 1])), abs(L[t] - C[t - 1]))
    return np.asarray(out, dtype=np.float64)


def pine_atr(h, l, c, n: int = ATR_LEN) -> np.ndarray:
    """``ta.atr(n)`` = ``ta.rma(ta.tr(true), n)``: na on bars 0 .. n - 2."""
    return pine_rma(pine_tr(h, l, c), n)


def pine_ema(x, n: int, seed: str = "first") -> np.ndarray:
    """``ta.ema(x, n)``, ``alpha = 2 / (n + 1)``. ``seed="first"`` (R2, pine_ema): ``sum := na(sum[1]) ? x : alpha * x +
    (1 - alpha) * nz(sum[1])``. ``seed="sma"`` (the alternative, to measure R2 only): na until n values, then their
    pine_sma, then the same recursion."""
    xs = _floats(x, "x")
    alpha = 2 / (n + 1)
    out = [NAN] * len(xs)
    if seed == "first":
        prev = NAN
        for t in range(len(xs)):
            if isna(prev):
                val = xs[t]
            else:
                val = alpha * xs[t] + (1 - alpha) * prev
            out[t] = val
            prev = val
    elif seed == "sma":
        sm = pine_sma(xs, n).tolist()
        prev = NAN
        for t in range(len(xs)):
            if isna(prev):
                val = sm[t]
            else:
                val = alpha * xs[t] + (1 - alpha) * prev
            out[t] = val
            prev = val
    else:
        raise ValueError(f"seed: 'first' or 'sma', got {seed!r}")
    return np.asarray(out, dtype=np.float64)


def pine_highest(x, n: int) -> np.ndarray:
    """``ta.highest(x, n)``: the max of the last n values (this bar included); na until n values exist (R3)."""
    xs = _floats(x, "x")
    out = [NAN] * len(xs)
    for t in range(n - 1, len(xs)):
        m = xs[t]
        for i in range(1, n):
            m = pmax(m, xs[t - i])
        out[t] = m
    return np.asarray(out, dtype=np.float64)


def pine_lowest(x, n: int) -> np.ndarray:
    """``ta.lowest(x, n)``: the min of the last n values (this bar included); na until n values exist (R3)."""
    xs = _floats(x, "x")
    out = [NAN] * len(xs)
    for t in range(n - 1, len(xs)):
        m = xs[t]
        for i in range(1, n):
            m = pmin(m, xs[t - i])
        out[t] = m
    return np.asarray(out, dtype=np.float64)


def hist(x, k: int = 1) -> np.ndarray:
    """``x[k]``: the value k bars back, na on the first k bars."""
    xs = _floats(x, "x")
    out = [NAN] * len(xs)
    for t in range(k, len(xs)):
        out[t] = xs[t - k]
    return np.asarray(out, dtype=np.float64)


# ───────────────────────────── the New York clock (L127-133) ─────────────────────────────

def ny_clock(t) -> Dict[str, np.ndarray]:
    """
    Per bar: ``ny_min`` = ``hour(time, TZ) * 60 + minute(time, TZ)`` of the bar's OPEN (L128); ``dk`` = ``year(t4, TZ)
    * 10000 + month(t4, TZ) * 100 + dayofmonth(t4, TZ)`` with ``t4 = time + 4h`` (L129-130); ``dow`` =
    ``dayofweek(t4, TZ)``, Sunday 1 .. Saturday 7 (L131); ``weekday`` = Monday .. Friday (L132). New York wall-clock
    times come from ``external.local_seconds`` (America/New_York, daylight saving included).
    """
    ts = np.asarray(t, dtype=np.int64)
    if ts.ndim != 1:
        raise ValueError("t: a 1-D array is expected")
    loc = X.local_seconds(ts, NY)
    loc4 = X.local_seconds(ts + 4 * 3600, NY)
    sod = loc % 86400
    ny_min = (sod // 3600) * 60 + (sod % 3600) // 60
    d4 = pd.DatetimeIndex(pd.to_datetime(loc4, unit="s"))
    dk = d4.year.to_numpy(np.int64) * 10000 + d4.month.to_numpy(np.int64) * 100 + d4.day.to_numpy(np.int64)
    dow = (d4.dayofweek.to_numpy(np.int64) + 1) % 7 + 1          # pandas Monday 0 .. Sunday 6 -> Pine Sunday 1 ..
    weekday = (dow >= 2) & (dow <= 6)                            # dayofweek.monday = 2 .. dayofweek.friday = 6
    return {"ny_min": ny_min.astype(np.int64), "dk": dk, "dow": dow, "weekday": weekday}


# ───────────────────────────── the 1H EMA200 (L145) ─────────────────────────────

def htf_ema_at_open(t, h1_bars, length: int = HTF_LEN, seed: str = "first") -> np.ndarray:
    """
    htfE per chart bar: ``ta.ema(close, length)`` on the 1H bars, taken from the last 1H bar with ``tc <= t`` (the chart
    bar's OPEN). That is ``request.security(.., "60", ta.ema(close, length)[1], lookahead_on)``: the 1H bar containing
    the open is the one after it, and its ``[1]`` is it. NaN before the first closed 1H bar. ``seed``: R2.
    """
    ts = np.asarray(t, dtype=np.int64).tolist()
    tc = np.asarray(h1_bars.tc, dtype=np.int64)
    if tc.ndim != 1 or len(tc) != len(h1_bars.c):
        raise ValueError("h1_bars: tc and c of one length expected")
    if len(tc) > 1 and not bool(np.all(np.diff(tc) > 0)):
        raise ValueError("h1_bars.tc must increase strictly")
    ema = pine_ema(h1_bars.c, length, seed).tolist()
    tcl = tc.tolist()
    out = [NAN] * len(ts)
    k = -1
    for i, ti in enumerate(ts):
        while k + 1 < len(tcl) and tcl[k + 1] <= ti:
            k += 1
        out[i] = ema[k] if k >= 0 else NAN
    return np.asarray(out, dtype=np.float64)


htf_ema = htf_ema_at_open          # the contract's name (port A's ``htf_ema``)


def htf_ema_dir(t, c_chart, h1_bars, length: int = HTF_LEN) -> np.ndarray:
    """The script's HTF direction per chart bar: +1 when ``close > htfE``, -1 when ``close < htfE``, 0 when they are
    equal or htfE is na (so ``dd * htf_dir > 0`` is exactly L319's ``not na(htfE) and dd * (close - htfE) > 0``)."""
    e = htf_ema_at_open(t, h1_bars, length).tolist()
    cs = _floats(c_chart, "c_chart")
    if len(cs) != len(e):
        raise ValueError("t and c_chart: equal lengths expected")
    out = []
    for ci, ei in zip(cs, e):
        if isna(ei):
            out.append(0)
        elif ci - ei > 0:
            out.append(1)
        elif ci - ei < 0:
            out.append(-1)
        else:
            out.append(0)
    return np.asarray(out, dtype=np.int8)


# ───────────────────────────── the script's objects ─────────────────────────────

class St:
    """``type St`` (L176-182): the state of one setup for one day."""
    __slots__ = ("sH", "sL", "upEx", "dnEx", "done", "dead")

    def __init__(self):
        self.sH = False
        self.sL = False
        self.upEx = NAN
        self.dnEx = NAN
        self.done = False
        self.dead = False


class Trade:
    """``type Trade`` (L367-388), the fields the trade manager reads; ``row`` points at the signal's output row."""
    __slots__ = ("d", "nm", "stop", "tgtRef", "sb", "e", "tgt", "risk", "live", "x0", "row")

    def __init__(self, d: int, nm: str, stop: float, tgtRef: float, sb: int, row: int):
        self.d = d
        self.nm = nm
        self.stop = stop
        self.tgtRef = tgtRef
        self.sb = sb
        self.e = NAN
        self.tgt = NAN
        self.risk = NAN
        self.live = False
        self.x0 = -1
        self.row = row


# ───────────────────────────── the bar loop ─────────────────────────────

_SERIES_KEYS = ("new_day", "in_asia", "in_lon", "in_ny", "in_or", "close_t", "d_h", "d_l", "d_o", "pdh", "pdl", "p_o",
                "p_c", "p_wk", "d_wk", "mo", "adr", "as_h", "as_l", "lo_h", "lo_l", "o_h", "o_l", "as_done", "lo_done",
                "o_done", "s_AS", "s_LS", "s_PD", "s_AB", "s_OR")
_BOOL_SERIES = frozenset(("new_day", "in_asia", "in_lon", "in_ny", "in_or", "close_t", "p_wk", "d_wk", "as_done",
                          "lo_done", "o_done"))

def _names(x, allowed: Sequence[str], what: str) -> frozenset:
    if isinstance(x, str):
        raise ValueError(f"{what}: a sequence of names is expected, got the string {x!r}")
    got = frozenset(x)
    bad = sorted(got - set(allowed))
    if bad:
        raise ValueError(f"{what}: unknown {bad}; allowed {list(allowed)}")
    return got


def _check_inputs(t, o, h, l, c, v, tf_min, htf_dir, need_v: bool, need_htf: bool):
    """The contract's input checks (the same as port A's). ``v`` / ``htf_dir`` may be None unless 'RV' / 'HTF' reads
    them; then they stand for zeros, which nothing reads."""
    ts = np.asarray(t)
    if ts.ndim != 1:
        raise ValueError("t: a 1-D array is expected")
    if not np.issubdtype(ts.dtype, np.integer):
        if not bool(np.all(np.asarray(ts, np.float64) == np.floor(np.asarray(ts, np.float64)))):
            raise ValueError("t: integer UTC seconds expected")
    ts = ts.astype(np.int64)
    n = len(ts)
    if n > 1 and not bool(np.all(np.diff(ts) > 0)):
        raise ValueError("t must increase strictly")
    if v is None:
        if need_v:
            raise ValueError("v: the 'RV' confirmation reads the volume")
        v = np.zeros(n)
    if htf_dir is None:
        if need_htf:
            raise ValueError("htf_dir: the 'HTF' confirmation needs a direction per bar (htf_ema_dir)")
        htf_dir = np.zeros(n)
    cols = [_floats(a, nm) for a, nm in ((o, "o"), (h, "h"), (l, "l"), (c, "c"), (v, "v"), (htf_dir, "htf_dir"))]
    if any(len(a) != n for a in cols):
        raise ValueError("t, o, h, l, c, v, htf_dir: equal lengths expected")
    if not all(bool(np.isfinite(np.asarray(a, np.float64)).all()) for a in (o, h, l, c)):
        raise ValueError("o, h, l, c: finite prices are expected")
    if isinstance(tf_min, (bool, np.bool_)) or int(tf_min) != tf_min or int(tf_min) < 1:
        raise ValueError(f"tf_min: a positive whole number of minutes expected, got {tf_min!r}")
    return ts, cols, int(tf_min)


def _run(t, o, h, l, c, v, tf_min, htf_dir, setups=SETUPS, conf=("FVG", "HTF"), monday_friday_levels=False,
         min_stop_atr=0.5, *, first_bar_new_day: bool = False, want_series: bool = False):
    """The whole script on the bars: returns (rows: list of dicts in ``COLUMNS`` order, series: dict or None)."""
    on = _names(setups, SETUPS, "setups")
    cf = _names(conf, CONFIRMATIONS, "conf")
    ts, (O, H, L, C, V, HTF), tf = _check_inputs(t, o, h, l, c, v, tf_min, htf_dir, "RV" in cf, "HTF" in cf)
    minStop = float(min_stop_atr)
    if not (minStop > 0 and math.isfinite(minStop)):                      # the input's minval is 0.1 (L81)
        raise ValueError("min_stop_atr: a finite positive number expected")
    mfl = bool(monday_friday_levels)
    n = len(ts)

    eAS, eLS, ePD, eAB, eOR = ("AS" in on), ("LS" in on), ("PD" in on), ("AB" in on), ("OR" in on)
    cFVG, cMSS, cHTF, cPDz = ("FVG" in cf), ("MSS" in cf), ("HTF" in cf), ("PD" in cf)
    cRV, cADR, cDB = ("RV" in cf), ("TIGHT" in cf), ("YC" in cf)

    # ── clock (L127-133)
    clk = ny_clock(ts)
    NYMIN = clk["ny_min"].tolist()
    DK = clk["dk"].tolist()
    WEEKDAY = clk["weekday"].tolist()

    # ── shared series (L143-152), each from bars 0..i only
    ATR = pine_atr(H, L, C, ATR_LEN).tolist()
    VAVG = pine_sma(V, VOL_LEN).tolist()
    HI5 = hist(pine_highest(H, 5), 1).tolist()
    LO5 = hist(pine_lowest(L, 5), 1).tolist()
    FVGUP = [False] * n
    FVGDN = [False] * n
    for i in range(n):
        # high[k] / low[k] are na for k > i, and a comparison with na is false
        FVGUP[i] = ((i >= 2 and L[i] > H[i - 2]) or (i >= 3 and L[i - 1] > H[i - 3])
                    or (i >= 4 and L[i - 2] > H[i - 4]) or (i >= 5 and L[i - 3] > H[i - 5]))
        FVGDN[i] = ((i >= 2 and H[i] < L[i - 2]) or (i >= 3 and H[i - 1] < L[i - 3])
                    or (i >= 4 and H[i - 2] < L[i - 4]) or (i >= 5 and H[i - 3] < L[i - 5]))

    # ── var state (L155-188)
    dH = dL = dO = NAN
    pdh = pdl = pO = pC = NAN
    pWk = False
    mo = NAN
    asH = asL = loH = loL = oH = oL = NAN
    asDone = loDone = oDone = False
    ranges: List[float] = []
    dWk = False
    stAS, stLS, stPD, stAB, stOR = St(), St(), St(), St(), St()
    open_ = {m: [] for m in MODES}            # one trade manager per exit mode (L390)
    rows: List[dict] = []
    general_cancel: Dict[str, Dict[int, str]] = {m: {} for m in MODES}
    prev_inAsia = prev_inLon = prev_inOR = False      # R9: bool[1] on bar 0 is false

    S = None
    if want_series:                                   # numpy arrays, filled bar by bar (lists of floats cost 4x more)
        S = {k: np.zeros(n, bool) if k in _BOOL_SERIES else np.zeros(n, np.int64) if k.startswith("s_")
             else np.full(n, NAN) for k in _SERIES_KEYS}

    for i in range(n):
        hi, lo, op, cl = H[i], L[i], O[i], C[i]
        nyMin = NYMIN[i]
        weekday = WEEKDAY[i]

        # ── clock (L133-140)
        newDay = (DK[i] != DK[i - 1]) if i > 0 else first_bar_new_day           # R1
        inAsia = nyMin >= 1200 and nyMin + tf <= 1440
        inLon = nyMin >= 120 and nyMin + tf <= 300 and nyMin < 1440
        inNY = nyMin >= 420 and nyMin + tf <= 660 and nyMin < 1440
        inOR = (nyMin >= 570 and nyMin + tf <= 600 and nyMin < 1440) and tf < 60
        closeT = nyMin >= 960 and nyMin < 1200

        # ── day state (L190-213)
        if newDay:
            if not isna(dH) and dWk:
                ranges.append(dH - dL)
                if len(ranges) > RANGES_KEPT:
                    ranges.pop(0)
            pdh = dH if dWk else pdh
            pdl = dL if dWk else pdl
            pO = dO if dWk else pO
            pC = (C[i - 1] if i > 0 else NAN) if dWk else pC
            pWk = (dWk or pWk) if mfl else dWk                                   # R7 / L199
            dH = hi
            dL = lo
            dO = op
            dWk = weekday
            mo = NAN
            asH = asL = loH = loL = oH = oL = NAN
            asDone = loDone = oDone = False
            stAS, stLS, stPD, stAB, stOR = St(), St(), St(), St(), St()
        else:
            dH = pmax(dH, hi)
            dL = pmin(dL, lo)
        if len(ranges) >= ADR_MIN:                                                # R4
            tot = 0.0
            for r in ranges:
                tot = tot + r
            adr = tot / len(ranges)
        else:
            adr = NAN
        if isna(mo) and nyMin < 1200:
            mo = op

        # ── sessions (L216-233)
        if inAsia:
            asH = hi if isna(asH) else pmax(asH, hi)
            asL = lo if isna(asL) else pmin(asL, lo)
        if inLon:
            loH = hi if isna(loH) else pmax(loH, hi)
            loL = lo if isna(loL) else pmin(loL, lo)
        if inOR:
            oH = hi if isna(oH) else pmax(oH, hi)
            oL = lo if isna(oL) else pmin(oL, lo)
        asEnd = prev_inAsia and not inAsia
        loEnd = prev_inLon and not inLon
        orEnd = prev_inOR and not inOR
        if asEnd:
            asDone = True
        if loEnd:
            loDone = True
        if orEnd:
            oDone = True

        # ── confirmations (L312-328)
        def f_conf(dd: int, rH: float, rL: float) -> bool:
            ok = True
            if cFVG:
                ok = ok and (FVGUP[i] if dd > 0 else FVGDN[i])
            if cMSS:
                ok = ok and ((cl > HI5[i]) if dd > 0 else (cl < LO5[i]))
            if cHTF:
                ok = ok and dd * HTF[i] > 0                    # = not na(htfE) and dd * (close - htfE) > 0
            if cPDz:
                ok = ok and (not isna(mo)) and dd * (mo - cl) > 0
            if cRV:
                ok = ok and V[i] >= RV_K * VAVG[i]
            if cADR:
                ok = ok and (not isna(adr)) and rH - rL < ADR_PCT / 100.0 * adr
            if cDB:
                ok = ok and pWk and dd * (pC - pO) > 0
            return bool(ok)

        # fade a sweep of [rH, rL] inside the window (L331-347)
        def f_rev(s: St, rH: float, rL: float, win: bool) -> int:
            sig = 0
            if win and weekday and not s.done and not s.dead and not isna(rH) and not isna(rL) and rH > rL:
                if hi > rH:
                    s.sH = True
                    s.upEx = hi if isna(s.upEx) else pmax(s.upEx, hi)
                if lo < rL:
                    s.sL = True
                    s.dnEx = lo if isna(s.dnEx) else pmin(s.dnEx, lo)
                if s.sH and s.sL:
                    s.dead = True
                elif cl < rH and cl > rL:
                    dd = -1 if s.sH else (1 if s.sL else 0)
                    if dd != 0 and f_conf(dd, rH, rL):
                        sig = dd
                        s.done = True
            return sig

        # follow a close outside [rH, rL] inside the window (L350-358)
        def f_brk(s: St, rH: float, rL: float, win: bool) -> int:
            sig = 0
            if win and weekday and not s.done and not isna(rH) and not isna(rL) and rH > rL:
                dd = 1 if cl > rH else (-1 if cl < rL else 0)
                if dd != 0 and f_conf(dd, rH, rL):
                    s.done = True
                    if abs(cl - (rH + rL) / 2) <= BRK_ATR * ATR[i]:
                        sig = dd
            return sig

        # ── the five setups (L360-364)
        win_lon = nyMin >= 120 and nyMin + tf <= 300 and nyMin < 1440            # f_in(120, 300)
        win_ny = nyMin >= 420 and nyMin + tf <= 660 and nyMin < 1440             # f_in(420, 660)
        win_pd = nyMin >= 120 and nyMin + tf <= 660 and nyMin < 1440             # f_in(120, 660)
        win_or = nyMin >= 600 and nyMin + tf <= 720 and nyMin < 1440             # f_in(600, 720)
        sAS = f_rev(stAS, asH if asDone else NAN, asL, win_lon) if eAS else 0
        sLS = f_rev(stLS, loH if loDone else NAN, loL, win_ny) if eLS else 0
        sPD = f_rev(stPD, pdh, pdl, win_pd) if (ePD and pWk) else 0
        sAB = f_brk(stAB, asH if asDone else NAN, asL, win_lon) if eAB else 0
        sOR = f_brk(stOR, oH if oDone else NAN, oL, win_or) if (eOR and tf < 60) else 0

        # ── new trades (L399-421)
        def f_new(dd: int, code: str, s: St, rH: float, rL: float, rev: bool) -> None:
            stop = (s.upEx if dd < 0 else s.dnEx) if rev else (rH + rL) / 2
            if abs(cl - stop) < minStop * ATR[i]:
                stop = cl - dd * minStop * ATR[i]
            ref = (rL if dd < 0 else rH) if rev else ((rH if dd > 0 else rL) + dd * (rH - rL))
            k = len(rows)
            row = {"setup": code, "bar": i, "t_signal": int(ts[i]) + 60 * tf, "dir": dd, "stop": stop,
                   "tgt_ref": ref, "r_hi": rH, "r_lo": rL, "entry_bar": i + 1, "cancelled": None}
            for m in MODES:
                row[f"exit_bar_{m}"] = -1
                row[f"exit_price_{m}"] = NAN
                row[f"exit_reason_{m}"] = None
                row[f"R_{m}"] = NAN
            rows.append(row)
            for m in MODES:
                open_[m].append(Trade(dd, SETUP_NAMES[code], stop, ref, i, k))

        if sAS != 0:
            f_new(sAS, "AS", stAS, asH, asL, True)
        if sLS != 0:
            f_new(sLS, "LS", stLS, loH, loL, True)
        if sPD != 0:
            f_new(sPD, "PD", stPD, pdh, pdl, True)
        if sAB != 0:
            f_new(sAB, "AB", stAB, asH, asL, False)
        if sOR != 0:
            f_new(sOR, "OR", stOR, oH, oL, False)

        # ── manage open trades, one manager per exit mode (L424-492)
        for m in MODES:
            lst = open_[m]
            if len(lst) > 0:
                for k in range(len(lst) - 1, -1, -1):
                    T = lst[k]
                    if isna(T.e) and i > T.sb:
                        if closeT or newDay:
                            del lst[k]
                            general_cancel[m][T.row] = "closeT" if closeT else "new_day"        # R5
                            continue
                        T.e = op
                        T.risk = abs(op - T.stop)
                        if T.risk <= 0 or T.d * (op - T.stop) <= 0:
                            del lst[k]
                            general_cancel[m][T.row] = "risk<=0" if T.risk <= 0 else "open_beyond_stop"
                            continue
                        if m == "tp2":
                            T.tgt = op + T.d * TP2 * T.risk
                        elif m == "liq":
                            T.tgt = T.tgtRef
                        else:
                            T.tgt = NAN
                        if m == "liq" and T.d * (T.tgt - op) < T.risk:
                            del lst[k]
                            rows[T.row]["exit_reason_liq"] = LIQ_CANCEL
                            continue
                        T.live = True
                        T.x0 = i
                    if T.live:
                        x = NAN
                        why = None
                        if newDay and i > T.x0:
                            x = C[i - 1]
                            why = "new_day"
                        elif closeT and i > T.x0:
                            x = op
                            why = "closeT"
                        elif (lo <= T.stop) if T.d > 0 else (hi >= T.stop):
                            x = T.stop
                            why = "stop"
                        elif (not isna(T.tgt)) and ((hi >= T.tgt) if T.d > 0 else (lo <= T.tgt)):
                            x = T.tgt
                            why = "target"
                        if not isna(x):
                            R = (T.d * (x - T.e) - 2 * COST) / T.risk
                            row = rows[T.row]
                            row[f"exit_bar_{m}"] = i
                            row[f"exit_price_{m}"] = x
                            row[f"exit_reason_{m}"] = why
                            row[f"R_{m}"] = R
                            del lst[k]

        if S is not None:
            for key, val in zip(_SERIES_KEYS, (newDay, inAsia, inLon, inNY, inOR, closeT, dH, dL, dO, pdh, pdl, pO, pC,
                                               pWk, dWk, mo, adr, asH, asL, loH, loL, oH, oL, asDone, loDone, oDone,
                                               sAS, sLS, sPD, sAB, sOR)):
                S[key][i] = val

        prev_inAsia, prev_inLon, prev_inOR = inAsia, inLon, inOR

    # what is still in a manager after the last bar: entered and not out ('open'), or its entry bar is not in the data
    # yet ('pending', a signal on the last bar)
    for m in MODES:
        for T in open_[m]:
            rows[T.row][f"exit_reason_{m}"] = OPEN if T.live else PENDING

    # the entry decisions before the exit mode matters (L428-435) are the same in the three managers
    for k, row in enumerate(rows):
        got = {general_cancel[m].get(k) for m in MODES}
        if len(got) != 1:
            raise AssertionError(f"the managers disagree on the entry of signal {k}: {got}")
        row["cancelled"] = got.pop()

    series = None
    if S is not None:
        series = {"t": ts.copy(), "ny_min": clk["ny_min"], "dk": clk["dk"], "dow": clk["dow"],
                  "weekday": clk["weekday"], "atr": np.asarray(ATR, np.float64), "vavg": np.asarray(VAVG, np.float64),
                  "fvg_up": np.asarray(FVGUP, bool), "fvg_dn": np.asarray(FVGDN, bool),
                  "hi5": np.asarray(HI5, np.float64), "lo5": np.asarray(LO5, np.float64)}
        series.update(S)
    return rows, series


def _frame(rows: List[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    ints = ["bar", "t_signal", "dir", "entry_bar"] + [f"exit_bar_{m}" for m in MODES]
    floats = ["stop", "tgt_ref", "r_hi", "r_lo"] + [f"{k}_{m}" for m in MODES for k in ("exit_price", "R")]
    for col in ints:
        df[col] = df[col].astype(np.int64)
    for col in floats:
        df[col] = df[col].astype(np.float64)
    for col in ["setup", "cancelled"] + [f"exit_reason_{m}" for m in MODES]:
        df[col] = df[col].astype(object)
        df[col] = df[col].where(df[col].notna(), None)
    return df


def session_hunter(t, o, h, l, c, v, tf_min, htf_dir, setups=SETUPS, conf=("FVG", "HTF"),
                   monday_friday_levels=False, min_stop_atr=0.5) -> pd.DataFrame:
    """The script's signals and its own trade manager's decisions on chart bars of ``tf_min`` minutes: one row per
    signal, columns ``COLUMNS`` (see the module docstring for every column, reading and timing)."""
    rows, _ = _run(t, o, h, l, c, v, tf_min, htf_dir, setups, conf, monday_friday_levels, min_stop_atr)
    return _frame(rows)


def session_series(t, o, h, l, c, v, tf_min, htf_dir, setups=SETUPS, conf=("FVG", "HTF"),
                   monday_friday_levels=False, min_stop_atr=0.5, *, first_bar_new_day: bool = False
                   ) -> Dict[str, np.ndarray]:
    """Every per-bar series the rules read, as the script holds it when the setups run on that bar (after the day
    state, the midnight open and the sessions of the bar): the clock (``ny_min``, ``dk``, ``dow``, ``weekday``,
    ``new_day``, ``in_asia``, ``in_lon``, ``in_ny``, ``in_or``, ``close_t``), ``atr``, ``vavg``, ``fvg_up``, ``fvg_dn``,
    ``hi5``, ``lo5``, the day state (``d_h``, ``d_l``, ``d_o``, ``d_wk``, ``pdh``, ``pdl``, ``p_o``, ``p_c``, ``p_wk``,
    ``mo``, ``adr``), the sessions (``as_h`` .. ``o_l``, ``as_done``, ``lo_done``, ``o_done``) and each setup's signal
    ``s_AS`` .. ``s_OR`` (+1 / -1 / 0). Not part of the comparison contract."""
    _, s = _run(t, o, h, l, c, v, tf_min, htf_dir, setups, conf, monday_friday_levels, min_stop_atr,
                first_bar_new_day=first_bar_new_day, want_series=True)
    return s
