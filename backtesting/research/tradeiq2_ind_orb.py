"""
Ultimate Opening Range Breakout [LuxAlgo] (Pine v6, CC BY-NC-SA 4.0, (c) LuxAlgo), port A: the opening range, its
close-based breakouts, the script's one label per side per day, its target hit counts and its own ATR-trailed trade,
rebuilt bar by bar from the chart bars.

    from backtesting.research import tradeiq2_ind_orb as ORB
    out = ORB.orb(bars.t, bars.o, bars.h, bars.l, bars.c, vol, 5, symbol="XAUUSDm")   # M5, New York clock
    out["label_up"], out["or_high"], out["days"]          # per bar, and one row per session

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 2, 4, 5, 6.5, 7 and claims 6-9 of section 8); the
specification is section 1 (and 0) of the study's map ``orb_session_swing_ha.md``. Line numbers ("l.") are those of
the plain-text copy of the owner's script (485 lines with the closing comment); the source itself is not in this
repository. Port A (this module, the production port) and port B (``tests/tradeiq2_oracle_orb.py``) were written
independently from the source and the specification, then reconciled: on the study's M5 and M15 bars of both
symbols (data start to 2024-06-30) and on synthetic bars they return the same outputs, floats bit for bit and the
same ``days`` frame (``tests/test_tradeiq2_ind_orb.py``; what was found and decided:
``backtest_results/tradeiq_2027/porting/orb.md``).

The contract (both ports)
-------------------------
``orb(t, o, h, l, c, v, tf_min, sess=(570, 600), window_end=1020, clock='ny', days='weekdays', trail_mult=2.0,
multiples=(1.0, 2.0, 3.0), day_boundary='auto', symbol=None)`` -> dict.

Inputs: chart bars of ``tf_min`` minutes (5 or 15 in the study; any whole number of minutes that divides a day is
accepted, e.g. 60, where no bar opens inside 09:30-10:00 and no range ever forms) with open times ``t`` (UTC epoch
seconds, an integer dtype, strictly increasing, on the ``tf_min`` grid), the bid ``o, h, l, c`` and the volume ``v``
(tick volume; Binance volume for BTC, PREREG 2), read only by ``hv`` (``None``: no volume, Pine's na volume, so
``hv`` is False everywhere). ``o`` is not read: the script's default range source "High/Low" (l.37, 167-168) uses
only the high and the low. NaN or infinite prices or volumes are refused.

* ``sess``: (start, end) minutes of the session clock, the session ``"0930-1000"`` (l.33) by default; the COMEX
  variant of PREREG 6.5 is (500, 530). ``window_end``: the end of the display window (l.56-58, 216-225), 1020 =
  "New York Close" = "1700". The window starts at the session start (``orStartTime``, l.216). Both are [start, end).
* ``clock``: ``'ny'`` = America/New_York with daylight saving (the corrected version, PREREG 6.5); ``'utc-5'`` = the
  script's literal default timezone "UTC-5" (l.35), a fixed offset without daylight saving (PREREG 6.5's control).
* ``days``: ``'weekdays'`` (Monday-Friday of the session clock's date: "23456" in Pine's 1 = Sunday numbering, the
  plan's version) or ``'all'`` (the script's "1234567", l.34). It restricts the session and the display window alike
  (both strings end with ``":" + sessionDays``, l.87 and 225).
* ``trail_mult``: the trailing stop's ATR multiple (l.61); the ATR length is the script's 14 (l.62).
* ``multiples``: the three extension multiples (l.40-42, 187-189); "Fibonacci" is (0.382, 0.618, 1.0).
* ``day_boundary``: when the script's ``isNewDay`` (l.88) fires, see "The day reset" below: ``'ny17'`` (17:00
  New York, daylight saving included), ``'utc0'`` (00:00 UTC), ``'clock0'`` (midnight of the session clock: an
  alternative reading, not the script's; only to measure what the reading changes) or ``'auto'``: ``'utc0'`` for a
  crypto ``symbol`` (a name starting with BTC or ETH), ``'ny17'`` for every other symbol (gold, FX, index CFDs).
  ``'auto'`` needs ``symbol``.

Output, per bar (numpy arrays of len(t)):

* ``in_session`` bool: the bar OPENS inside the session on an allowed day (``inSession``, l.87).
* ``new_day`` bool: ``isNewDay`` (l.88); False on the first bar (``ta.change`` is na there).
* ``or_high``, ``or_low`` float64: the range, final from the first bar after the session: the script's ``orHigh`` /
  ``orLow`` on every bar where ``sessionEnded`` holds (from the first post-session bar up to the bar before the next
  reset), NaN on every other bar (before and during the session, and after the reset). While the session runs the
  script's own variables hold the forming range (max of the highs so far); it is not exposed, by the contract.
* ``session_ended`` bool: the script's ``sessionEnded`` at the end of the bar (l.150, 181-182).
* ``breakout_up``, ``breakout_dn`` bool: ``ta.crossover(close, orHigh) and not inSession and sessionEnded`` and the
  mirror with ``ta.crossunder(close, orLow)`` (l.243-244). These are also the alert conditions (l.480-481): every
  cross, gated by neither the display window nor the one-label rule.
* ``label_up``, ``label_dn`` bool: the script's labels (l.252, 263): a breakout while ``canSignalUp`` (resp. Dn) and
  ``displayAllowed``; at most one per side per session span.
* ``hv`` bool: ``volume > ta.sma(volume, 20)`` (l.238-239), the current bar included; False while the SMA is na
  (the first 19 bars) and where ``v`` is None. The label's "(HV)" / "(LV)" suffix (l.240).
* ``atr`` float64: ``ta.atr(14)`` (l.236, ``trailAtrLen``), study 1's verified ``tradeiq_ind.atr``; NaN on the first
  13 bars.
* ``active_dir`` int8: the script's ``activeDir`` at the end of the bar (1 long, -1 short, 0 none).
* ``trail`` float64: the script's ``trailStop`` at the end of the bar (NaN when no trade is open, and on the exit bar,
  where l.279 / 286 set it to na).

and ``days``: a ``pandas.DataFrame``, one row per session THE SCRIPT COUNTS (``totalSessions += 1``, l.181-183: a
range whose session reached its first post-session bar), in time order, with the columns of ``DAY_COLUMNS``. A
range the data end cuts before its session ends, or one that a new day restarts inside the session (a data hole from
one day's session into the next day's), is not a row, as the script never counts it.

* ``day`` int64: the session clock's calendar date of the range's first bar (epoch day number, days since
  1970-01-01; its weekday is ``(day + 3) % 7``, 0 = Monday).
* ``start_bar``, ``end_bar`` int64: the first and the last bar of the range: the in-session bars from the last
  reset (l.147) that fired on an in-session bar to the last in-session bar before the session ends.
* ``post_bar`` int64: the first bar after the session (``end_bar + 1``), where ``sessionEnded`` is set and
  ``totalSessions`` counts the session (l.181-183).
* ``span_end`` int64: the first bar after ``post_bar`` where l.147 resets (a new day or the next session's first
  bar): ``sessionEnded`` holds exactly on [``post_bar``, ``span_end``); ``len(t)`` when the data end first.
* ``or_high``, ``or_low``, ``width`` float64: the range the script holds from ``post_bar`` on (final: the high and
  the low of the in-session bars) and ``orRange = orHigh - orLow`` (l.185); ``u1..u3``, ``d1..d3`` float64: the
  script's levels ``orHigh + orRange * mult`` and ``orLow - orRange * mult`` (``getExt``, l.139-142, 191-193) for
  the three ``multiples``, as absolute prices. All NaN for a WIPED session: when ``post_bar`` is itself a new day
  (a data hole from inside the session into the next exchange day), l.147's reset on that bar runs before l.181,
  so the script counts the session with an na range, on which nothing can break out or be hit. On the study's bars
  to 2024-06-30 this happens once, to gold's COMEX range on M5 on 2021-03-02 (never to the 09:30 session).
* ``first_breakout_side`` int64 (+1 up, -1 down, 0 none) and ``first_breakout_bar`` int64 (-1 none): the first bar of
  the span with ``breakout_up`` or ``breakout_dn`` (not gated by the display window or the labels).
* ``label_up_bar``, ``label_dn_bar`` int64: the span's labelled breakouts (-1 none).
* ``hit_u1..hit_u3``, ``hit_d1..hit_d3`` bool: the script's ``dayReachedU1..D3`` (l.195-214), i.e. whether the span
  added 1 to ``countU1..countD3``: a high at or above u_k (a low at or below d_k) on a bar where ``sessionEnded``
  holds, from the first post-session bar (included) to the next reset, whatever the breakouts did; and
  ``hit_u1_bar..hit_d3_bar`` int64, the bar where each was counted (-1 none). The dashboard's rate of a level is the
  sum of its column over the rows divided by their number (l.374-379, 425-455): ``len(days)`` is ``totalSessions``.
* The script's own trades (l.252-286; at most two per span: the first label always opens one, and a second, on the
  other side, opens only if the first was closed by its trail before that side's label): ``trade_side`` (+1 / -1 /
  0 none), ``entry_bar`` (the label bar, -1 none), ``entry_price`` (the script books ``orHigh`` for a long and
  ``orLow`` for a short, l.257 / 268: not the breakout close, not a fill), ``exit_bar``, ``exit_price`` (the exit
  bar's close, l.277 / 284), ``exit_reason``: 'trail' (``close < trailStop``, resp. ``>``), 'window' (the first bar
  outside the display window: ``not displayAllowed``), 'reset' (the trade vanishes at the next reset, l.246-250,
  unbooked: ``exit_bar`` is the reset bar and ``exit_price`` is NaN), 'open' (still open at the last bar: -1, NaN) or
  '' (no trade); and the same six for the second trade: ``trade2_side``, ``entry2_bar``, ``entry2_price``,
  ``exit2_bar``, ``exit2_price``, ``exit2_reason``. When the close is below the trail outside the window, the reason
  is 'trail' (the first condition of l.276's ``or``). No profit is computed here.

What the script computes on each bar, in its order
--------------------------------------------------
1. Clock (l.87-88). ``inSession = not na(time(timeframe.period, "0930-1000:1234567", "UTC-5"))``: Pine's ``time``
   with a session returns the bar's open time when that open lies inside the session ([start, end), on a listed day
   of the session's timezone), na otherwise. So membership is by the bar's OPEN: on M5 the bars opening 09:30 ..
   09:55, on M15 09:30 and 09:45 (both cover exactly 09:30-10:00); the bar opening at 10:00 is outside; on 1H no bar
   opens inside 09:30-10:00, so no range forms. For the COMEX variant (08:20-08:50) the M15 bars opening 08:30 and
   08:45 are inside, so on M15 that range covers 08:30-09:00 (on M5: 08:20-08:50 exactly).
   ``isNewDay = ta.change(time("D", "", timezoneInput)) != 0``: the open time of the daily bar the chart bar belongs
   to changed. That is the exchange's trading day (see "The day reset").
2. Reset (l.147-164) on ``isNewDay or (inSession and not inSession[1])`` (``inSession[1]`` is false on the first
   bar): orHigh, orLow := na; sessionEnded := false; the six "reached today" flags := false; entryPrice := na (the
   volume profile's state is display only). It does NOT touch canSignal, activeDir or trailStop (step 8 does).
3. Range (l.166-171), on each in-session bar: ``orHigh := na(orHigh) ? high : math.max(orHigh, high)``, orLow
   mirrored.
4. Session end (l.181-183): ``not inSession and inSession[1]`` -> sessionEnded := true, totalSessions += 1, on the
   first bar after the session (also when that bar is a new day whose reset has just wiped the range: then the levels
   are na, nothing breaks out or counts; possible only across a data hole).
5. Levels (l.185-193) ``u_k = orHigh + orRange * f_k``, ``d_k = orLow - orRange * f_k``; hit counts (l.195-214): while
   sessionEnded, the first bar with ``high >= u_k`` (``low <= d_k``) sets the day's flag and adds 1 to the count. So
   the 10:00 bar counts, a level can count on a day without any breakout, and up and down can both count.
6. Display window (l.216-225): ``displayAllowed`` = the bar opens inside "0930-1700" (session start to
   ``window_end``) of the same timezone and days (``stopPlotting`` true, "New York Close").
7. ``atrTrail = ta.atr(14)`` (l.236); ``isHV = volume > ta.sma(volume, 20)`` (l.238-239);
   ``breakoutUp = ta.crossover(close, orHigh) and not inSession and sessionEnded`` (l.243), i.e.
   ``close > orHigh and close[1] <= orHigh[1]``, with ``orHigh[1]`` the previous bar's value; breakoutDn mirrored
   (l.244). On the first post-session bar ``close[1] <= orHigh[1]`` always holds (the last session bar's close lies
   inside its own range), so a 10:00 bar that closes beyond the range is a breakout. A close exactly at orHigh is not
   one, and the next close above it is.
8. Daily gates (l.246-250) on ``isNewDay or inSession``: canSignalUp, canSignalDn := true; activeDir := 0;
   trailStop := na. This runs BEFORE the exit checks of step 10, so a trade still open at a reset vanishes unbooked:
   on gold (day at 17:00 New York, no bars 17:00-18:00) the first bar outside the display window is the 18:00 reopen,
   a new day, so every gold trade still open at the break is dropped, in winter and in summer; on BTC (day at 00:00
   UTC) the 17:00 bar exits by the window rule at its close.
9. Labels and entries (l.252-272): ``breakoutUp and canSignalUp and displayAllowed`` -> label, canSignalUp := false
   and, only if no trade is open (``activeDir == 0``), a long: entryPrice := orHigh, trailStop := low - atr * mult.
   Then the bear branch, the mirror (entryPrice := orLow, trailStop := high + atr * mult). An opposite breakout while
   a trade is open is labelled but not traded.
10. Trailing stops (l.274-286), long first, then short: ``trailStop := math.max(nz(trailStop[1], low - atr * mult),
    low - atr * mult)`` and exit (booked at the close, l.277) when ``close < trailStop or not displayAllowed``; the
    short mirrored with ``math.min`` / ``high + atr * mult`` / ``close > trailStop``. The bear branch (step 9) runs
    BEFORE the long's exit test, so a bear breakout on the bar where the long's trail exits uses up the bear label
    and no short opens that day. ``trailStop[1]`` is the previous bar's final value; on an entry bar it is always na
    (every bar that ends without a trade ends with trailStop na: l.250, 279, 286), so the ``nz`` fallback gives the
    entry bar's own ``low - atr * mult``. A wick through the trail does not exit (the test is on the close) and the
    trail never moves against the trade (max / min with the previous value). While the ATR is na (the first 13 bars)
    the trail is na and only the window rule or a reset can end a trade.
11. Not ported, because no signal depends on them: the stop optimizer (l.288-304, off by default), ``totalProfit``
    (l.277, 284), the volume profile and ``ta.atr(200)`` (l.84, 109-111, 157-179, 341-368), the drawing, the labels'
    text and the dashboard (l.309-476), the "Target 3 Reached" alerts (l.482-483, ``ta.cross`` either way).

The day reset (``isNewDay``, l.88)
----------------------------------
``time("D", "", tz)`` is the open time of the chart bar's DAILY bar. Its session argument is empty, so the symbol's
own session defines that bar; the timezone argument only interprets a session string and cannot move the daily bar's
boundary. On TradingView the daily bar of FX, metal and index CFD feeds starts at 17:00 New York (daylight saving
included; gold's Sunday reopen at about 18:05 New York starts Monday's bar) and that of crypto exchanges at 00:00
UTC. ``'auto'`` follows that: gold 17:00 New York, BTC 00:00 UTC (the map, 1.1 step 1). The alternative reading,
midnight of the timezone argument (``'clock0'``), is offered only to measure what the reading changes: it moves no
breakout or label inside 10:00-17:00 (the reset is after 17:00 either way), but it changes the script's own trade
bookkeeping (gold's trades would exit by the window rule at the 18:00 reopen instead of vanishing), the raw
breakouts after 17:00 (unlabelled) and the span over which the hits are counted, hence O4's causal hit rates.

What is known when (no look-ahead; element i depends on bars 0..i only)
-----------------------------------------------------------------------
* ``in_session``, ``new_day``: from the bar's open time alone (known at its open).
* ``or_high`` / ``or_low`` on the first post-session bar depend on the session bars only: known at the close of the
  session's last bar; the script itself learns that the session has ended on the next bar.
* ``breakout_*``, ``label_*``, ``hv``, ``atr``, ``active_dir``, ``trail``: at the close of the bar (``t + 60 *
  tf_min``). The earliest real fill of a label is the next M1 open (PREREG 4); the script's booking at orHigh is
  optimistic by the distance from orHigh to the breakout close plus the gap to that open, and the harness re-measures
  every absolute level from the actual fill (PREREG 4's rules for absolute levels; the map's kernel trap, 0.4).
* A ``days`` row exists from its ``post_bar`` on (bars cut at T keep the rows whose ``post_bar`` < T) and holds bar
  indices: each field is known at the close of the bar it names; the row is complete at ``span_end``. A study that
  uses hit rates causally counts only rows whose ``span_end`` precedes its decision.

Readings where the Pine is ambiguous (the map, 1.6 "Risks")
-----------------------------------------------------------
* Session membership by the bar's open (above); the session's end is exclusive.
* ``isNewDay`` on the first bar, where ``ta.change`` is na: false. A comparison with na is false, as study 1 read
  every comparison with na and as the other study-2 ports do (TradingView's reference only warns against comparing
  with na). It changes only ``new_day[0]``: on bar 0 every variable still has its initial value and an in-session
  bar 0 resets anyway (``inSession[1]`` is false there). Port B was written with true (IEEE ``NaN != 0``) and took
  this reading in the reconciliation.
* The session days are those of the session clock's date at the bar's open. With the literal UTC-5 clock that date
  equals New York's for every window of the study (all lie between 08:20 and 18:00 New York).
* ``ta.crossover`` with na: as documented, ``a > b and a[1] <= b[1]``, false where a value is na. TradingView's
  runtime is recorded to compare with the last bar where both were non-na (``tradeiq_ind._cross_inputs``); they agree
  here, because a breakout needs sessionEnded, and wherever sessionEnded holds the previous bar's orHigh exists (it
  was an in-session or a post-session bar of the same range).
* ``trailStop[1]`` on the entry bar is na, as shown above, so reading the just-assigned value instead gives the same
  trail; the misreading that matters is a stale trail (a port that does not set trailStop back to na on exits and
  resets): a later trade's trail would start from the old trade's level, tighter than its own (the same day's
  second trade) or already crossed (a trade after an earlier day's opposite one), an exit on its entry bar.
* The ATR is study 1's ``tradeiq_ind.atr`` (``alpha * tr + (1 - alpha) * prev``). The harness's ``atr14`` uses
  ``external.wilder_atr`` (``(prev * 13 + tr) / 14``); the two agree to about 2e-15 relative. On the M5 / M15 bars of
  both symbols to 2024-06-30 the trail's floats differ in the last bits on a few hundred bars, but no entry or exit
  moves; only an exact tie of the close with the trail could move one.
* ``ta.sma(volume, 20)`` is study 1's ``tradeiq_ind.sma`` (``pine_sma``'s order of addition). Tick volumes are
  integers, so the volume often equals its mean exactly; another order of addition (a rolling mean) moves the HV tag
  of a few bars there (on BTC's tick volume in 2019-2022, one label per timeframe).
* The days frame's first breakout is the first raw crossing of the span (the alerts' condition): on BTC, whose span
  lasts to 00:00 UTC, it can come after 17:00 New York without a label (6 sessions in 2019-2022); on gold it is always
  the first label.
* The days frame holds the sessions the script counts, with the range the script holds after the session: a session
  whose range a reset on its own end bar wiped is a row with NaN levels, as it is one of ``totalSessions`` (the
  reconciliation took port B's reading; this port first kept the range of the session bars there, and a span end at
  the wiping reset). A range that never reaches a post-session bar is not a row (this port first listed it with
  ``ended`` false; the column is gone).
* A session with missing bars (a data hole inside it) keeps the range of the bars it has, as the script does. On the
  study's bars to 2024-06-30: gold's 09:30 session on 2016-05-18 (warm-up) and the COMEX session on 2021-03-02 (M5,
  wiped) and 2023-11-22 (M5 and M15); none for BTC.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from numba import njit

from . import external as X
from . import tradeiq_ind as I

__all__ = [
    "SESSION", "COMEX_SESSION", "WINDOW_END", "TRAIL_MULT", "ATR_LEN", "VOL_LEN", "MULTIPLES", "FIB_MULTIPLES",
    "CLOCKS", "DAY_SETS", "DAY_BOUNDARIES", "EXIT_REASONS", "BAR_KEYS", "KEYS", "DAY_COLUMNS",
    "clock_seconds", "session_masks", "day_boundary_of", "day_keys", "new_days", "orb",
]

NAN = math.nan
DAY = 86400
SESSION = (570, 600)                 # "0930-1000" (l.33), minutes of the session clock
COMEX_SESSION = (500, 530)           # 08:20-08:50 New York, PREREG 6.5 ORB-CX
WINDOW_END = 1020                    # stopTimeType "New York Close" -> "1700" (l.57, 218-219)
TRAIL_MULT = 2.0                     # trailMult (l.61)
ATR_LEN = 14                         # trailAtrLen (l.62)
VOL_LEN = 20                         # ta.sma(volume, 20) (l.238)
MULTIPLES = (1.0, 2.0, 3.0)          # extType "Multiples" (l.39-42)
FIB_MULTIPLES = (0.382, 0.618, 1.0)  # extType "Fibonacci" (l.187-189)
CLOCKS = ("ny", "utc-5")
DAY_SETS = ("weekdays", "all")
DAY_BOUNDARIES = ("auto", "ny17", "utc0", "clock0")
UTC_MINUS_5_S = -5 * 3600            # the literal "UTC-5" (l.35)
NY17_SHIFT_S = 7 * 3600              # 17:00 New York + 7 h = midnight: the trading day that starts at 17:00
EXIT_REASONS = ("", "trail", "window", "reset", "open")     # codes 0..4 of the kernel
_CRYPTO_PREFIXES = ("BTC", "ETH")

BAR_KEYS = ("in_session", "new_day", "or_high", "or_low", "session_ended", "breakout_up", "breakout_dn",
            "label_up", "label_dn", "hv", "atr", "active_dir", "trail")
KEYS = BAR_KEYS + ("days",)
_HIT = ("u1", "u2", "u3", "d1", "d2", "d3")
DAY_COLUMNS = (("day", "start_bar", "end_bar", "post_bar", "span_end", "or_high", "or_low", "width")
               + _HIT
               + ("first_breakout_side", "first_breakout_bar", "label_up_bar", "label_dn_bar")
               + tuple(f"hit_{k}" for k in _HIT) + tuple(f"hit_{k}_bar" for k in _HIT)
               + ("trade_side", "entry_bar", "entry_price", "exit_bar", "exit_price", "exit_reason",
                  "trade2_side", "entry2_bar", "entry2_price", "exit2_bar", "exit2_price", "exit2_reason"))


# ───────────────────────────── the clocks ─────────────────────────────

def clock_seconds(t, clock: str) -> np.ndarray:
    """UTC epoch seconds -> wall-clock seconds of the session clock, as epoch seconds of that clock: ``'ny'`` =
    America/New_York with daylight saving (``external.local_seconds``), ``'utc-5'`` = UTC - 5 h all year."""
    t = np.asarray(t, np.int64)
    if clock == "ny":
        return X.local_seconds(t, X.NY)
    if clock == "utc-5":
        return t + UTC_MINUS_5_S
    raise ValueError(f"clock: one of {CLOCKS}, got {clock!r}")


def session_masks(t, sess: Tuple[int, int] = SESSION, window_end: int = WINDOW_END, clock: str = "ny",
                  days: str = "weekdays", local: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """(``inSession``, ``displayAllowed``) per bar (l.87, 225): the bar's OPEN, as a minute of the session clock,
    lies in [sess[0], sess[1]) / [sess[0], window_end), on a weekday of that clock's date when ``days`` is
    'weekdays'. ``local``: the bars' clock seconds when already computed."""
    s0, s1 = _session(sess)
    w1 = _window_end(window_end, s0)
    if days not in DAY_SETS:
        raise ValueError(f"days: one of {DAY_SETS}, got {days!r}")
    loc = clock_seconds(t, clock) if local is None else np.asarray(local, np.int64)
    minute = (loc // 60) % 1440
    ok = np.ones(len(loc), np.bool_) if days == "all" else ((loc // DAY + 3) % 7) < 5
    ins = ok & (minute >= s0) & (minute < s1)
    disp = ok & (minute >= s0) & (minute < w1)
    return ins, disp


def day_boundary_of(symbol: Optional[str]) -> str:
    """``'auto'``'s choice: 'utc0' (00:00 UTC, crypto exchanges) for a symbol whose name starts with BTC or ETH,
    'ny17' (17:00 New York, FX / metal / index CFD feeds) for any other."""
    if not symbol:
        raise ValueError("day_boundary='auto' needs the symbol (or pass 'ny17' / 'utc0' / 'clock0')")
    return "utc0" if str(symbol).upper().startswith(_CRYPTO_PREFIXES) else "ny17"


def day_keys(t, day_boundary: str, clock: str = "ny", local: Optional[np.ndarray] = None,
             ny: Optional[np.ndarray] = None) -> np.ndarray:
    """The trading day of each bar as an integer key: 'ny17' the New York date of (New York wall clock + 7 h), so the
    day starts at 17:00 New York; 'utc0' the UTC date; 'clock0' the session clock's date. ``local`` / ``ny``: the
    bars' session-clock / New York seconds when already computed."""
    t = np.asarray(t, np.int64)
    if day_boundary == "ny17":
        nys = X.local_seconds(t, X.NY) if ny is None else np.asarray(ny, np.int64)
        return (nys + NY17_SHIFT_S) // DAY
    if day_boundary == "utc0":
        return t // DAY
    if day_boundary == "clock0":
        loc = clock_seconds(t, clock) if local is None else np.asarray(local, np.int64)
        return loc // DAY
    raise ValueError(f"day_boundary: one of {DAY_BOUNDARIES[1:]} here, got {day_boundary!r}")


def new_days(key) -> np.ndarray:
    """``ta.change(key) != 0``: True where the key differs from the previous bar's; False on the first bar."""
    key = np.asarray(key)
    out = np.zeros(len(key), np.bool_)
    if len(key) > 1:
        out[1:] = key[1:] != key[:-1]
    return out


# ───────────────────────────── input checks ─────────────────────────────

def _int(x, name: str) -> int:
    if isinstance(x, (bool, np.bool_)):
        raise ValueError(f"{name}: an integer is expected, got {x!r}")
    f = float(x)
    if not f.is_integer():
        raise ValueError(f"{name}: an integer is expected, got {x!r}")
    return int(f)


def _session(sess) -> Tuple[int, int]:
    try:
        s0, s1 = sess
    except (TypeError, ValueError):
        raise ValueError(f"sess: (start, end) minutes, got {sess!r}") from None
    s0, s1 = _int(s0, "sess[0]"), _int(s1, "sess[1]")
    if not 0 <= s0 < s1 <= 1440:
        raise ValueError(f"sess: 0 <= start < end <= 1440 (a session inside one day), got {(s0, s1)}")
    return s0, s1


def _window_end(window_end, s0: int) -> int:
    w1 = _int(window_end, "window_end")
    if not s0 < w1 <= 1440:
        raise ValueError(f"window_end: after the session start ({s0}) and at most 1440, got {w1}")
    return w1


def _series(x, n: int, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)              # a copy: the caller's array is never modified
    if a.shape != (n,):
        raise ValueError(f"{name}: shape {a.shape}, expected ({n},)")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name}: NaN or inf in the bars")
    return a


def _times(t, tf_min: int) -> np.ndarray:
    a = np.asarray(t)
    if a.ndim != 1:
        raise ValueError(f"t: a 1-D series is expected, got shape {a.shape}")
    if a.dtype.kind not in "iu":
        raise ValueError(f"t: integer epoch seconds are expected, got dtype {a.dtype}")
    a = a.astype(np.int64)
    if len(a) > 1 and not bool(np.all(np.diff(a) > 0)):
        raise ValueError("t: bar open times must increase strictly")
    if len(a) and bool(np.any(a % (60 * tf_min) != 0)):
        raise ValueError(f"t: open times off the {tf_min}-minute grid (chart bars of tf_min minutes, open times)")
    return a


# ───────────────────────────── the script, bar by bar ─────────────────────────────

@njit(cache=True)
def _kernel(ins, nd, disp, h, l, c, atr, mult, tm, n_rows):
    """
    l.147-286 of the script, bar by bar, in its order (see the module docstring, steps 2-10). ``ins`` / ``nd`` /
    ``disp``: inSession, isNewDay, displayAllowed; ``atr``: ta.atr(14); ``mult``: the three multiples; ``tm``:
    trailMult. Returns the per-bar series (the variables' values at the end of each bar) and one record per range
    started on an in-session bar (``n_rows`` of them; ``_days_frame`` keeps those whose session ended, ``r_post >=
    0``): its bars, range, hits, first breakout, labels and the script's up to two trades (exit codes: 0 none,
    1 trail, 2 window, 3 reset, 4 open).
    """
    n = h.shape[0]
    orh_v = np.full(n, np.nan)
    orl_v = np.full(n, np.nan)
    end_v = np.zeros(n, np.bool_)
    bu_v = np.zeros(n, np.bool_)
    bd_v = np.zeros(n, np.bool_)
    lu_v = np.zeros(n, np.bool_)
    ld_v = np.zeros(n, np.bool_)
    dir_v = np.zeros(n, np.int8)
    trail_v = np.full(n, np.nan)

    r_start = np.full(n_rows, -1, np.int64)
    r_end = np.full(n_rows, -1, np.int64)
    r_post = np.full(n_rows, -1, np.int64)
    r_span = np.full(n_rows, n, np.int64)
    r_orh = np.full(n_rows, np.nan)
    r_orl = np.full(n_rows, np.nan)
    r_hit = np.full((n_rows, 6), -1, np.int64)
    r_fb = np.full(n_rows, -1, np.int64)
    r_fbs = np.zeros(n_rows, np.int64)
    r_lu = np.full(n_rows, -1, np.int64)
    r_ld = np.full(n_rows, -1, np.int64)
    r_side = np.zeros((n_rows, 2), np.int64)
    r_ebar = np.full((n_rows, 2), -1, np.int64)
    r_epx = np.full((n_rows, 2), np.nan)
    r_xbar = np.full((n_rows, 2), -1, np.int64)
    r_xpx = np.full((n_rows, 2), np.nan)
    r_why = np.zeros((n_rows, 2), np.int64)
    r_ntr = np.zeros(n_rows, np.int64)

    orh = np.nan                      # var float orHigh (l.90)
    orl = np.nan                      # var float orLow (l.91)
    ended = False                     # var bool sessionEnded (l.92)
    reached = np.zeros(6, np.bool_)   # dayReachedU1..U3, D1..D3 (l.102-107)
    can_up = True                     # var bool canSignalUp (l.125)
    can_dn = True                     # var bool canSignalDn (l.126)
    adir = 0                          # var int activeDir (l.123)
    trail = np.nan                    # var float trailStop (l.122)
    orh1 = np.nan                     # orHigh[1], orLow[1], trailStop[1]: the previous bar's final values
    orl1 = np.nan
    trail1 = np.nan
    ins1 = False                      # inSession[1]: false on the first bar
    r = -1                            # the current session's record
    tr_r = -1                         # the record and slot of the open trade
    tr_k = -1
    for i in range(n):
        # l.147-164: the reset; it ends the span of the last session that has ended (r_post set on an earlier bar).
        # A reset on a session's own end bar (a new day after a data hole) runs before that bar's l.181, so it
        # wipes the range and the span starts after it: that span ends at the next reset.
        if nd[i] or (ins[i] and not ins1):
            if r >= 0 and r_post[r] >= 0 and r_span[r] == n:
                r_span[r] = i
            orh = np.nan
            orl = np.nan
            ended = False
            for k in range(6):
                reached[k] = False
            if ins[i]:
                r += 1
                if r >= n_rows:
                    raise ValueError("more sessions than counted")
                r_start[r] = i
        # l.166-171: the range ("High/Low" source)
        if ins[i]:
            if orh != orh or h[i] > orh:
                orh = h[i]
            if orl != orl or l[i] < orl:
                orl = l[i]
            r_end[r] = i
            r_orh[r] = orh
            r_orl[r] = orl
        # l.181-183: the session end; the row keeps the range the script holds from here on (na when this bar's
        # reset has just wiped it)
        if (not ins[i]) and ins1:
            ended = True
            r_post[r] = i
            r_orh[r] = orh
            r_orl[r] = orl
        # l.185-214: the levels and the hit counts
        if ended:
            rng = orh - orl
            for k in range(3):
                u = orh + rng * mult[k]
                if u == u and h[i] >= u and not reached[k]:
                    reached[k] = True
                    r_hit[r, k] = i
            for k in range(3):
                d = orl - rng * mult[k]
                if d == d and l[i] <= d and not reached[3 + k]:
                    reached[3 + k] = True
                    r_hit[r, 3 + k] = i
        # l.243-244: ta.crossover(close, orHigh) / ta.crossunder(close, orLow), comparisons with na are false
        bu = (c[i] > orh) and i > 0 and (c[i - 1] <= orh1) and (not ins[i]) and ended
        bd = (c[i] < orl) and i > 0 and (c[i - 1] >= orl1) and (not ins[i]) and ended
        if (bu or bd) and r >= 0 and r_fb[r] < 0:
            r_fb[r] = i
            r_fbs[r] = 1 if bu else -1
        # l.246-250: the daily gates, before the exits: an open trade vanishes unbooked
        if nd[i] or ins[i]:
            can_up = True
            can_dn = True
            if adir != 0:
                r_xbar[tr_r, tr_k] = i
                r_why[tr_r, tr_k] = 3
            adir = 0
            trail = np.nan
        # l.252-261: the bull label and entry
        if bu and can_up and disp[i]:
            lu_v[i] = True
            can_up = False
            r_lu[r] = i
            if adir == 0:
                adir = 1
                trail = l[i] - (atr[i] * tm)
                k = r_ntr[r]
                if k >= 2:
                    raise ValueError("a third trade in one session span")
                r_ntr[r] = k + 1
                r_side[r, k] = 1
                r_ebar[r, k] = i
                r_epx[r, k] = orh
                tr_r = r
                tr_k = k
        # l.263-272: the bear label and entry, BEFORE the long's exit test
        if bd and can_dn and disp[i]:
            ld_v[i] = True
            can_dn = False
            r_ld[r] = i
            if adir == 0:
                adir = -1
                trail = h[i] + (atr[i] * tm)
                k = r_ntr[r]
                if k >= 2:
                    raise ValueError("a third trade in one session span")
                r_ntr[r] = k + 1
                r_side[r, k] = -1
                r_ebar[r, k] = i
                r_epx[r, k] = orl
                tr_r = r
                tr_k = k
        # l.274-279: the long's trail, math.max(nz(trailStop[1], x), x) (na if either is na), exit at the close
        if adir == 1:
            x = l[i] - (atr[i] * tm)
            a = trail1 if trail1 == trail1 else x
            if a != a or x != x:
                trail = np.nan
            else:
                trail = a if a > x else x
            if c[i] < trail or not disp[i]:
                r_xbar[tr_r, tr_k] = i
                r_xpx[tr_r, tr_k] = c[i]
                r_why[tr_r, tr_k] = 1 if c[i] < trail else 2
                adir = 0
                trail = np.nan
        # l.281-286: the short's trail, the mirror
        if adir == -1:
            x = h[i] + (atr[i] * tm)
            a = trail1 if trail1 == trail1 else x
            if a != a or x != x:
                trail = np.nan
            else:
                trail = a if a < x else x
            if c[i] > trail or not disp[i]:
                r_xbar[tr_r, tr_k] = i
                r_xpx[tr_r, tr_k] = c[i]
                r_why[tr_r, tr_k] = 1 if c[i] > trail else 2
                adir = 0
                trail = np.nan
        orh_v[i] = orh
        orl_v[i] = orl
        end_v[i] = ended
        bu_v[i] = bu
        bd_v[i] = bd
        dir_v[i] = adir
        trail_v[i] = trail
        orh1 = orh
        orl1 = orl
        trail1 = trail
        ins1 = ins[i]
    if adir != 0:
        r_why[tr_r, tr_k] = 4
    return (orh_v, orl_v, end_v, bu_v, bd_v, lu_v, ld_v, dir_v, trail_v,
            r_start, r_end, r_post, r_span, r_orh, r_orl, r_hit, r_fb, r_fbs, r_lu, r_ld,
            r_side, r_ebar, r_epx, r_xbar, r_xpx, r_why)


# ───────────────────────────── the contract ─────────────────────────────

def _days_frame(loc: np.ndarray, rec, mult: np.ndarray) -> pd.DataFrame:
    """The kernel's records as the ``days`` frame: only the sessions the script counts (``totalSessions += 1``,
    l.181-183), i.e. the records whose session reached its first post-session bar."""
    keep = rec[2] >= 0                                          # r_post
    (r_start, r_end, r_post, r_span, r_orh, r_orl, r_hit, r_fb, r_fbs, r_lu, r_ld,
     r_side, r_ebar, r_epx, r_xbar, r_xpx, r_why) = (np.ascontiguousarray(x[keep]) for x in rec)
    width = r_orh - r_orl                                       # orRange (l.185)
    reasons = np.asarray(EXIT_REASONS, dtype=object)
    cols: Dict[str, np.ndarray] = {
        "day": (loc[r_start] // DAY).astype(np.int64) if len(r_start) else np.zeros(0, np.int64),
        "start_bar": r_start, "end_bar": r_end, "post_bar": r_post, "span_end": r_span,
        "or_high": r_orh, "or_low": r_orl, "width": width,
    }
    for k in range(3):                                          # getExt (l.139-142, 191-193)
        cols[f"u{k + 1}"] = r_orh + width * mult[k]
    for k in range(3):
        cols[f"d{k + 1}"] = r_orl - width * mult[k]
    cols.update({"first_breakout_side": r_fbs, "first_breakout_bar": r_fb, "label_up_bar": r_lu,
                 "label_dn_bar": r_ld})
    for j, k in enumerate(_HIT):
        cols[f"hit_{k}"] = r_hit[:, j] >= 0
    for j, k in enumerate(_HIT):
        cols[f"hit_{k}_bar"] = r_hit[:, j].copy()
    for s, (side, eb, ep, xb, xp, why) in enumerate(
            (("trade_side", "entry_bar", "entry_price", "exit_bar", "exit_price", "exit_reason"),
             ("trade2_side", "entry2_bar", "entry2_price", "exit2_bar", "exit2_price", "exit2_reason"))):
        cols[side] = r_side[:, s].copy()
        cols[eb] = r_ebar[:, s].copy()
        cols[ep] = r_epx[:, s].copy()
        cols[xb] = r_xbar[:, s].copy()
        cols[xp] = r_xpx[:, s].copy()
        cols[why] = reasons[r_why[:, s]]
    df = pd.DataFrame(cols)
    return df[list(DAY_COLUMNS)]


def orb(t, o, h, l, c, v, tf_min, sess=SESSION, window_end=WINDOW_END, clock="ny", days="weekdays",
        trail_mult=TRAIL_MULT, multiples=MULTIPLES, day_boundary="auto", symbol=None) -> Dict[str, object]:
    """
    The script on chart bars (see the module docstring for the inputs, the outputs and the readings): per-bar
    series under ``BAR_KEYS`` and the per-session frame under ``"days"``. Element i of every series depends on bars
    0..i only.
    """
    tf = _int(tf_min, "tf_min")
    if tf < 1 or 1440 % tf:
        raise ValueError(f"tf_min: a whole number of minutes that divides a day (1440), got {tf_min!r}")
    tt = _times(t, tf)
    n = len(tt)
    oo, hh, ll, cc = (_series(x, n, name) for x, name in ((o, "o"), (h, "h"), (l, "l"), (c, "c")))
    del oo                                                      # "High/Low" source: the open is not read (l.167)
    vv = None if v is None else _series(v, n, "v")
    if clock not in CLOCKS:
        raise ValueError(f"clock: one of {CLOCKS}, got {clock!r}")
    if days not in DAY_SETS:
        raise ValueError(f"days: one of {DAY_SETS}, got {days!r}")
    tm = float(trail_mult)
    if not (math.isfinite(tm) and tm > 0):
        raise ValueError(f"trail_mult: a positive number, got {trail_mult!r}")
    mult = np.array([float(m) for m in multiples], np.float64)
    if mult.shape != (3,) or not np.all(np.isfinite(mult)) or np.any(mult < 0):
        raise ValueError(f"multiples: three numbers >= 0 (l.40-42), got {multiples!r}")
    if day_boundary not in DAY_BOUNDARIES:
        raise ValueError(f"day_boundary: one of {DAY_BOUNDARIES}, got {day_boundary!r}")
    boundary = day_boundary_of(symbol) if day_boundary == "auto" else day_boundary

    ny = X.local_seconds(tt, X.NY) if (clock == "ny" or boundary == "ny17") else None
    loc = ny if clock == "ny" else clock_seconds(tt, clock)
    ins, disp = session_masks(tt, sess, window_end, clock, days, local=loc)
    nd = new_days(day_keys(tt, boundary, clock, local=loc, ny=ny))
    ins1 = np.zeros(n, np.bool_)
    ins1[1:] = ins[:-1]
    n_rows = int(np.count_nonzero(ins & (nd | ~ins1)))          # in-session bars where l.147's reset fires

    atr = I.atr(hh, ll, cc, ATR_LEN) if n else np.zeros(0)
    if vv is None or n == 0:
        hv = np.zeros(n, np.bool_)
    else:
        vs = I.sma(vv, VOL_LEN)
        with np.errstate(invalid="ignore"):
            hv = vv > vs                                        # na SMA: false (LV)

    (orh_v, orl_v, end_v, bu_v, bd_v, lu_v, ld_v, dir_v, trail_v, *rec) = _kernel(
        ins, nd, disp, hh, ll, cc, atr, mult, tm, n_rows)
    or_high = np.where(end_v, orh_v, np.nan)
    or_low = np.where(end_v, orl_v, np.nan)
    out: Dict[str, object] = {
        "in_session": ins, "new_day": nd, "or_high": or_high, "or_low": or_low, "session_ended": end_v,
        "breakout_up": bu_v, "breakout_dn": bd_v, "label_up": lu_v, "label_dn": ld_v, "hv": np.asarray(hv, np.bool_),
        "atr": atr, "active_dir": dir_v, "trail": trail_v,
    }
    out["days"] = _days_frame(loc, rec, mult)
    return out
