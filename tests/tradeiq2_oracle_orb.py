"""
PORT B (the oracle) of "Ultimate Opening Range Breakout [LuxAlgo]": a literal, bar-by-bar transcription of the
script's opening range, its breakouts, its one-label-per-side signals, its target hit counts and its own trailing-stop
trade.

Study 2 of the TradeIQ research, ``backtest_results/tradeiq_2027/PREREG.md`` (frozen): the script is its section 6.5
and claims 6-9 of section 8. As in study 1, two engineers port the script independently from the Pine source. Port A
is ``backtesting/research/tradeiq2_ind_orb.py`` (the one the study runs). This file is port B: plain Python, the
script's ``var`` state in one small object, every statement of l.147-286 evaluated bar by bar in the script's order,
written to be obviously correct rather than fast. It is the reference port A is checked against. It imports nothing
of the study's indicator code (not ``tradeiq_ind.py``, no ``tradeiq2_ind_*`` module) and nothing of the repository:
its Pine primitives are written below from TradingView's "same on pine" reference code, and its clocks come from the
standard library (``zoneinfo``, America/New_York). Its tests are ``tests/test_tradeiq2_ind_orb_b.py``.

The two ports were reconciled (``tests/test_tradeiq2_ind_orb.py``; what was found and decided:
``backtest_results/tradeiq_2027/porting/orb.md``): on the study's M5 and M15 bars of both symbols and on synthetic bars
they return the same outputs, floats bit for bit and the same ``days`` frame. The reconciliation changed three things
here: ``isNewDay`` on bar 0 is false (R4), the ``days`` frame has port A's columns, codes and dtypes, and a wiped
session's ``start_bar`` is the first bar of the range the reset wiped (R12); the contract's inputs are exactly port
A's (``CLOCKS``, ``DAY_SETS``, ``DAY_BOUNDARIES`` with R3's alternative 'clock0', ``v=None``).

``l.NNN`` is a line of the Pine source "LuxAlgo Ultimate Opening Range Breakout Indicator.txt" (484 lines,
``//@version=6``, CC BY-NC-SA 4.0, (c) LuxAlgo). The source is third-party code and is not in the repository; only
line numbers and identifiers are cited.

The contract (the same function name, inputs, output keys, columns and dtypes in both ports)
-------------------------------------------------------------------------------------------
``orb(t, o, h, l, c, v, tf_min, sess=(570, 600), window_end=1020, clock='ny', days='weekdays', trail_mult=2.0,
multiples=(1.0, 2.0, 3.0), day_boundary='auto', symbol=None)`` -> ``dict``.

Inputs:

* ``t``: the chart bars' OPEN times (UTC epoch seconds of an integer dtype, strictly increasing, on the ``tf_min``
  grid); ``o``, ``h``, ``l``, ``c``: the bid OHLC; ``v``: the volume (gold: the tick count; BTC: Binance volume or the
  tick count), or ``None`` (Pine's na volume: ``hv`` is False everywhere). No NaN.
* ``tf_min``: the chart timeframe in minutes (5 or 15 in the study; any divisor of 1440 is accepted, e.g. 60 for an
  information-only check that no range forms at 1H).
* ``sess = (start, end)``: the session ``sessionInput`` (l.33) in minutes of the session clock, [start, end):
  09:30-10:00 = (570, 600), the default; the COMEX variant ORB-CX 08:20-08:50 = (500, 530). ``window_end``: the end of
  the display window ``plottingSession`` (l.216-224): ``stopTimeType`` "New York Close" = "1700" = 1020; the window
  starts at the session's start (``orStartTime``, l.216).
* ``clock``: the clock of the session, the window and their weekdays (``timezoneInput``, l.35). 'ny' =
  America/New_York with daylight saving (the corrected version, PREREG 6.5); 'utc-5' = the script's literal default,
  a fixed UTC-5 all year (``CLOCKS``).
* ``days``: the session's weekdays (``sessionDays``, l.34). 'weekdays' = "23456" (Monday-Friday of the session clock;
  the study's choice); 'all' = "1234567" (the script's default; PREREG's BTC 7-day control) (``DAY_SETS``).
* ``trail_mult``: ``trailMult`` (l.61, 2.0). ``multiples``: the three extension factors ``f1..f3`` (l.187-189),
  "Multiples" 1/2/3 by default ("Fibonacci" = (0.382, 0.618, 1.0)).
* ``day_boundary``: the day of ``isNewDay`` (l.88), the EXCHANGE's trading day (reading R3): 'ny17' = the day starts
  at 17:00 New York (TradingView's FX and metal CFD feeds: gold), 'utc0' = at 00:00 UTC (crypto exchanges: BTC).
  'auto' picks by ``symbol``: a name starting with BTC or ETH -> 'utc0', any other -> 'ny17'; 'auto' without a
  symbol raises. 'clock0' = midnight of the session clock, R3's alternative reading, only to measure what it changes.
  Only 'clock0' depends on ``clock``.

Output keys (one value per bar unless stated; every value is the one the script holds at the END of the bar, after
all its statements):

  =================  ==============================================================================================
  ``in_session``     bool: the bar's open time is inside the session on an allowed weekday (l.87)
  ``new_day``        bool: ``isNewDay`` (l.88), the first bar of a new exchange day (bar 0: False, R4)
  ``or_high``        float: the opening range's high, FINAL: NaN until the first bar after the session, then the
  ``or_low``         range until the next reset (l.147); NaN again from the reset on (R6). The script's forming
                     range during the session is ``orb_series()['or_high_live']``
  ``session_ended``  bool: ``sessionEnded`` (l.92, 150, 182): from the first bar after the session to the next reset
  ``breakout_up``    bool: ``ta.crossover(close, orHigh) and not inSession and sessionEnded`` (l.243): the alert
  ``breakout_dn``    condition (l.480-481), every cross; and the mirror with ``ta.crossunder(close, orLow)`` (l.244)
  ``label_up``       bool: the script's signal label (l.252-254 / l.263-265): a breakout while ``canSignalUp/Dn``
  ``label_dn``       and ``displayAllowed``; at most one per side per day
  ``hv``             bool: ``volume > ta.sma(volume, 20)`` (l.238-239), the current bar included; False while the SMA
                     is na (bars 0-18)
  ``atr``            float: ``ta.atr(14)`` (``trailAtrLen``, l.62 and 236); NaN on bars 0-12
  ``active_dir``     int8: ``activeDir`` (l.123): +1 long, -1 short, 0 flat
  ``trail``          float: ``trailStop`` (l.122): the trade's trailing stop, NaN while flat
  ``days``           pandas.DataFrame, one row per session the script counts (``totalSessions += 1``, l.181-183),
                     in order; columns ``DAY_COLUMNS`` below
  =================  ==============================================================================================

``days`` columns (bars are indices into the inputs; -1 = none; every integer column int64):

  ========================  ===================================================================================
  ``day``                   the session clock's date of the range's first bar, as an epoch day number (days since
                            1970-01-01; weekday ``(day + 3) % 7``, 0 = Monday)
  ``start_bar``             the first bar of the range: the last bar on which l.147 reset while in session
                            (also for a wiped range, R12)
  ``end_bar``               the last in-session bar
  ``post_bar``              the first bar after the session (``end_bar + 1``), where l.181 counts the session
  ``span_end``              the bar of the first reset (l.147) after ``post_bar``: ``sessionEnded`` holds on
                            [``post_bar``, ``span_end``); ``len(t)`` if the data end first
  ``or_high``, ``or_low``   the final range as the script holds it after the session (NaN: R12); ``width`` =
  ``width``                 ``or_high - or_low``
  ``u1`` .. ``u3``,         the levels ``or_high + width * f_k`` and ``or_low - width * f_k`` (``getExt``,
  ``d1`` .. ``d3``          l.139-142, 191-193), absolute prices
  ``first_breakout_side``   +1 / -1 / 0 and the bar of the first ``breakout_up`` / ``breakout_dn`` (the alert
  ``first_breakout_bar``    condition) from the first bar after the session to the next reset (R13)
  ``label_up_bar``,         the bar of the day's bull / bear label
  ``label_dn_bar``
  ``hit_u1`` .. ``hit_u3``  bool: the script's "reached today" flags (l.195-214): ``high >= u_k`` (``low <= d_k``) on
  ``hit_d1`` .. ``hit_d3``  any bar from the first bar after the session to the next reset, breakout or not
  ``hit_u1_bar`` ..         the bar on which the script counted that hit (``countU1 += 1``)
  ``hit_d3_bar``
  ``trade_side``,           the script's own trade of that session (l.255-286), the first one: +1 / -1 (0: none);
  ``entry_bar``,            the label bar; the price the script books, ``orHigh`` for a long and ``orLow`` for a
  ``entry_price``,          short (l.257, 268: NOT the breakout close); the bar it ends; the price the script books,
  ``exit_bar``,             the bar's close (l.277, 284); why (``EXIT_REASONS``): 'trail' (``close < trailStop``, a
  ``exit_price``,           short ``close > trailStop``), 'window' (``not displayAllowed``), 'reset' (dropped,
  ``exit_reason``           unbooked, by the reset of l.246 on a new day: exit_price NaN), 'open' (still open at the
                            end of the data: -1, NaN), '' (no trade)
  ``trade2_side``,          the same for the session's second trade (the opposite side, opened after the first one
  ``entry2_bar`` ..         closed; R14); 0 / -1 / NaN / '' when there is none
  ``exit2_reason``
  ========================  ===================================================================================

Not part of the comparison: ``orb_series()`` (the contract's arrays plus every other per-bar variable of the script:
the live range, the six levels, ``displayAllowed``, ``canSignalUp/Dn``, ``entryPrice``, ``totalSessions``, the six
counts, the clocks), the Pine primitives ``pine_sma``, ``pine_rma``, ``pine_tr``, ``pine_atr``, and the clock
helpers ``session_clock``, ``exchange_day``, ``day_boundary_of``.

What is computed, statement by statement (the script's order; ``[1]`` is the value at the end of the previous bar)
-------------------------------------------------------------------------------------------------------------------
1. **Clock** (l.87-88, 225). ``inSession`` = the bar's open time, on the session clock, has a minute of day in
   [start, end) and an allowed weekday; ``displayAllowed`` = the same with [start, window_end). ``isNewDay`` = the
   exchange day of the bar's open differs from the previous bar's.
2. **Reset** (l.147-163), if ``isNewDay or (inSession and not inSession[1])``: ``orHigh``, ``orLow`` := na,
   ``sessionEnded`` := false, the six ``dayReached`` flags := false, ``entryPrice`` := na. (The volume map, the
   profile anchors, ``dynamicTickSize`` and the optimizer arrays are reset too; they draw only, not ported.)
3. **Range** (l.166-171), if ``inSession``: ``orHigh := na(orHigh) ? high : math.max(orHigh, high)``, ``orLow`` the
   mirror with ``low`` (``srcInput`` "High/Low", the default; l.167-168).
4. **Session end** (l.181-183), if ``not inSession and inSession[1]``: ``sessionEnded := true``,
   ``totalSessions += 1``.
5. **Levels** (l.185-193): ``orRange = orHigh - orLow``; ``u_k = orHigh + orRange * f_k``, ``d_k = orLow - orRange *
   f_k`` (``getExt``, l.139-142; na while the range is na).
6. **Hit counts** (l.195-214), if ``sessionEnded``: for k = 1, 2, 3, ``not na(u_k) and high >= u_k and not
   dayReachedU_k`` -> ``countU_k += 1``, ``dayReachedU_k := true``; then the same for ``low <= d_k``.
7. **Breakouts** (l.243-244): ``ta.crossover(close, orHigh)`` = ``close > orHigh and close[1] <= orHigh[1]`` (false
   when any of them is na), ``and not inSession and sessionEnded``; the mirror with ``ta.crossunder(close, orLow)`` =
   ``close < orLow and close[1] >= orLow[1]``.
8. **Daily gates** (l.246-250), if ``isNewDay or inSession``: ``canSignalUp``, ``canSignalDn`` := true,
   ``activeDir`` := 0, ``trailStop`` := na. A trade still open here vanishes unbooked (R11).
9. **Bull label** (l.252-261), if ``breakoutUp and canSignalUp and displayAllowed``: the label, ``canSignalUp :=
   false``; and if ``activeDir == 0``: ``activeDir := 1``, ``entryPrice := orHigh``, ``trailStop := low - (atr *
   trailMult)``.
10. **Bear label** (l.263-272), the mirror: ``entryPrice := orLow``, ``trailStop := high + (atr * trailMult)``. It
    runs BEFORE the trail exit below, so a bear breakout on the bar on which an open long exits uses up the bear
    label and opens nothing.
11. **Long trail** (l.274-279), if ``activeDir == 1``: ``trailStop := math.max(nz(trailStop[1], low - (atr *
    trailMult)), low - (atr * trailMult))``; if ``close < trailStop or not displayAllowed``: the exit at the close
    (``totalProfit += close - entryPrice``), ``activeDir := 0``, ``trailStop := na``.
12. **Short trail** (l.281-286), if ``activeDir == -1``: ``math.min(nz(trailStop[1], high + ...), high + ...)``; exit
    on ``close > trailStop or not displayAllowed``.

Not ported, because no output reads them: the volume profile (l.84 ``atrVal = ta.atr(200)``, l.109-112, 157-179,
341-368), the stop optimizer (l.117-120, 162-163, 259-261, 270-272, 288-304: off by default and display only), the
plots, labels and dashboard (l.309-476; their numbers are ``totalSessions`` and the counts, which ``orb_series``
gives), ``totalProfit`` (l.114, 277, 284: no profit is computed here), the "Target 3 Reached" alerts (l.482-483),
``srcInput`` "Close" (l.167-168) and ``stopPlotting`` false (l.225).

What is known when (no look-ahead)
----------------------------------
Every value of bar i uses bars 0..i only. ``in_session``, ``new_day`` and ``session_ended`` are functions of the open
times of bars i-1 and i and of the earlier state: known at bar i's OPEN. ``or_high`` / ``or_low`` are final at the
close of the session's last bar and appear from the first bar after the session, so a rule may read them from that
bar's open. ``breakout_*``, ``label_*``, ``hv`` (the bar's own volume), ``atr``, ``trail`` and ``active_dir`` read
the bar's close, high, low and volume: known at bar i's CLOSE, the earliest decision time; an order can fill at the
next M1 open at the earliest (PREREG 4). In ``days``: a row exists from its ``post_bar`` on (bars cut at T keep the
rows whose ``post_bar`` < T); the range at ``end_bar``'s close, each hit, breakout, label, entry and exit at its bar's
close, ``span_end`` at its open. Nothing repaints: no ``request.security``,
no lookahead, no pivots, no ``barstate`` branch that changes a signal (l.341 and l.391 draw only). Removing the bars
after T leaves everything decided by T unchanged (tests).

Pine readings where the semantics are not spelled out (R1-R16; the tests pin each choice)
-----------------------------------------------------------------------------------------
R1.  Session membership (l.87, 225), ``time(timeframe.period, "HHMM-HHMM:days", tz)``: a bar is in the session when
     its OPEN time is in [start, end) of the session clock (TradingView's session test is on the bar's time, the end
     is exclusive). Alternatives: the bar overlaps the session; the whole bar is inside it (Session Hunter's
     ``f_in``). On M5 and M15 with 09:30-10:00 the three agree (the bars tile the session). They differ for ORB-CX
     (08:20-08:50) on M15: open time -> the 08:30 and 08:45 bars (a range of 08:30-09:00; the first bar after the
     session is 09:00); overlap -> 08:15-09:00; whole bar -> 08:30-08:45 only. On M5 08:20 and 08:50 are on the
     grid and the readings agree. ``tf_min`` is used only to check that the open times are on the grid. Size on
     gold's M15 bars of 2019-2022 (1,030 COMEX sessions): the whole-bar reading would change 784 ranges and 489 first
     breakouts, the overlap reading 795 ranges and 193 first breakouts.
R2.  The weekday of the session days (l.34) is the session clock's weekday of the bar's open (Pine's ``dayofweek``
     in the given timezone, 1 = Sunday). The session and the window never cross midnight, so it is the session's
     date; for 09:30-17:00 the New York, UTC-5 and UTC dates are the same, so the two clocks agree on it.
R3.  ``isNewDay = ta.change(time("D", "", timezoneInput)) != 0`` (l.88): with an empty session string the timezone
     argument does not move the daily bar, so the day is the EXCHANGE's day (the spec's reading): 17:00 New York for
     gold (TradingView's FX / metal sessions run 17:00-17:00 New York, daylight saving included), 00:00 UTC for BTC.
     A bar starts a new day when the exchange day of its open time differs from the previous bar's: on gold the
     first bar at or after 17:00 New York, i.e. the reopen after the 17:00-18:00 break, and the Sunday open; on BTC
     the first bar at or after 00:00 UTC. Alternative: midnight of the session clock (00:00 UTC-5 / New York),
     ``day_boundary='clock0'``, for measurement only.
     It changes signals: it decides when the hit window and ``sessionEnded`` stop, and on gold it drops every trade
     still open at the 17:00 break (R11), which midnight would book as a 'window' exit at the reopen: in 2019-2022
     125 of gold's 993 first trades on M5 and 689 of 968 on M15. On BTC the 00:00 UTC day drops none.
R4.  ``isNewDay`` on bar 0, where ``time("D")[1]`` is na: FALSE, a comparison with na is false (study 1's reading of
     every comparison with na, port A's, and the other study-2 ports'; TradingView's reference only warns against
     comparing with na). This port was written with TRUE (``na != 0`` under IEEE NaN semantics) and took port A's
     reading in the reconciliation. It changes nothing but ``new_day[0]``: on bar 0 every variable still has its
     initial value, and an in-session bar 0 resets anyway (R5).
R5.  ``inSession[1]`` on bar 0 is false (Pine v6: a bool is never na). Bar 0 only; nothing changes either way.
R6.  The contract's ``or_high`` / ``or_low`` are the FINAL range: NaN on the session's own bars (where the script's
     ``orHigh`` holds the forming range) and NaN before the session. Alternative: the script's literal ``orHigh``,
     equal on every bar from the session's end on. No signal changes: the breakouts and hit counts are computed from
     the literal series, which ``orb_series()['or_high_live']`` exposes.
R7.  ``ta.crossover(close, orHigh)`` reads ``orHigh[1]``, the value at the end of the previous bar (on the first bar
     after the session: the range including the last session bar; later: the same constant range), and is false
     when any of the four values is na. Alternative: ``close[1] <= orHigh`` (the current level): identical on every
     bar where ``sessionEnded`` holds, so no signal changes. On the first bar after the session ``close[1] <=
     orHigh[1]`` always holds (the last session bar's high is in the range), so a first post-session bar that closes
     above the range is a breakout.
R8.  ``ta.sma(volume, 20)`` (l.238) uses pine_sma's arithmetic, ``sum := sum + x[i] / 20`` from the newest value (i =
     0) to the oldest, as study 1 (``tests/tradeiq_oracle.py``); alternative: the sum divided by 20 (TradingView does
     not publish its built-in's arithmetic). The two differ in the last bit only, so ``hv`` can differ only when the
     bar's volume equals the window's mean exactly (20 * volume == the window's sum). With tick volumes (integers)
     that happens: in 2019-2022 on one labelled breakout of BTC (M5 and M15 each) and one of gold's M15 UTC-5
     control; none of gold's New York-clock labels and none with BTC's Binance volume (the study's BTC volume).
R9.  ``ta.atr(14)`` = ``ta.rma(ta.tr(true), 14)``: the true range is ``high - low`` on bar 0 (``na(high[1])``), the RMA
     is seeded with the pine_sma of the first 14 true ranges (na on bars 0-12), then ``alpha * tr + (1 - alpha) *
     prev`` with ``alpha = 1 / 14``. Alternative: a true range of na on bar 0 (the ATR starts a bar later). Only the
     first bars of the input differ; no session is that early in the study's data.
R10. ``nz(trailStop[1], ...)`` on the entry bar (l.275): ``trailStop[1]`` is the previous bar's value, which is always
     na there (a flat bar ends with ``trailStop`` na, and no entry can happen on a reset bar), so the trail of the
     entry bar is ``low - atr * trailMult`` (a short: ``high + ...``), the value l.258 / l.269 set. Alternative: the
     value just assigned by l.258: the same number. No signal changes.
R11. Exit labels (labels only; the script books every exit at the close): 'trail' when ``close < trailStop`` (the
     first operand of l.276; a short ``close > trailStop``, l.283), else 'window' (``not displayAllowed``). A trade
     still open when l.246 resets ``activeDir`` (a new day: on gold the reopen after 17:00 New York) is dropped
     without being booked: 'reset', ``exit_bar`` = the reset bar, ``exit_price`` NaN. Alternative: book it at the
     previous close (as Session Hunter does). The script books nothing (``totalProfit`` is unchanged), so neither does
     this port. Both exit conditions hold on 8 (M5) and 18 (M15) of BTC's exits in 2019-2022, none of gold's.
R12. ``days`` has one row per session END (l.181), exactly the sessions in ``totalSessions``. A row's range is the
     script's after the session; it is NaN only when the first bar after the session is itself a new day (a data gap
     from inside the session into the next exchange day): the reset of l.147 wipes the range on that bar, yet l.181
     still counts the session. Its ``start_bar`` / ``end_bar`` are still the session's bars (the range the reset
     wiped; this port first gave -1 there and took port A's reading in the reconciliation) and its span runs from
     ``post_bar`` to the next reset. A run of session bars that the next exchange day
     interrupts (a gap from one day's session into the next day's) restarts the range on the new day's first bar
     (l.147) and the first day is never counted. In the study's bars to 2024-06-30 the second never occurs and the
     first once: gold's COMEX session (08:20-08:50) on M5 on 2021-03-02, where Exness's data stop after the 08:20
     bar and resume on the next exchange day (Wednesday 19:00 EST); on M15 that day has no session at all (its 08:15
     bar opens before 08:20). The 09:30 session has neither (tests).
R13. ``first_breakout_side`` / ``_bar`` is the first ``breakout_up`` or ``breakout_dn`` (the script's alert condition,
     gated by neither ``canSignal`` nor ``displayAllowed``) from the first bar after the session to the next reset.
     Alternative: the first label (the same bar unless no breakout happens before the window ends and one happens
     after it, possible on BTC in the evening: 6 sessions of 2019-2022 on M5 and 6 on M15; gold none). The labels
     are in ``label_up_bar`` / ``label_dn_bar``. Both sides
     cannot break out on one bar (``close > orHigh >= orLow > close`` is impossible).
R14. A session can carry two script trades: the first label opens one (if flat); a label of the other side opens a
     second only if the first has already closed on an earlier bar (l.255, 266). The same side cannot trade twice
     (``canSignal``). So ``days`` has columns for the first (``trade_side`` ..) and the second (``trade2_side``
     ..) trade.
R15. The display window's end (``targetEndTime``, l.218-224) is read on the session clock, like the session: 17:00
     UTC-5 with the literal clock, i.e. 18:00 New York in summer.
R16. Pine's na semantics: arithmetic with na gives na, a comparison with na is false, ``math.max`` / ``math.min`` with
     an na argument give na (``pmax``, ``pmin``), ``nz(x, y)`` = y when x is na. Float arithmetic is IEEE double, as
     Pine's, with the script's operation order (``orHigh + orRange * f``, ``low - (atrTrail * trailMult)``).

Two consequences of the statement order that are not readings but are easy to port wrongly: the hit counts (l.195)
include the first bar after the session and are gated by neither a breakout nor the display window (on BTC they run
to 00:00 UTC); and the in-session half of l.246 (``or inSession``) is redundant for every configuration of the study,
because a new day always lies between two sessions; a test pins it on one where it is not (two sessions in one UTC
day across the March daylight-saving weekend).
"""

from __future__ import annotations

import math
from array import array
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NAN = math.nan
NY = ZoneInfo("America/New_York")
DAY_S = 86400

ATR_LEN = 14            # l.62 trailAtrLen (the trail's ATR, l.236)
VOL_LEN = 20            # l.238 ta.sma(volume, 20)
CLOCKS = ("ny", "utc-5")
DAY_SETS = ("weekdays", "all")
DAY_BOUNDARIES = ("auto", "ny17", "utc0", "clock0")
# the exit labels of the days frame: no trade, the trail, the window, dropped by the reset, still open at the end
EXIT_REASONS = ("", "trail", "window", "reset", "open")

BAR_KEYS = ("in_session", "new_day", "or_high", "or_low", "session_ended", "breakout_up", "breakout_dn", "label_up",
            "label_dn", "hv", "atr", "active_dir", "trail")
KEYS = BAR_KEYS + ("days",)
_TRADE = ("side", "entry_bar", "entry_price", "exit_bar", "exit_price", "exit_reason")
TRADE1_COLUMNS = ("trade_side", "entry_bar", "entry_price", "exit_bar", "exit_price", "exit_reason")
TRADE2_COLUMNS = ("trade2_side", "entry2_bar", "entry2_price", "exit2_bar", "exit2_price", "exit2_reason")
HIT_NAMES = ("u1", "u2", "u3", "d1", "d2", "d3")
DAY_COLUMNS = (("day", "start_bar", "end_bar", "post_bar", "span_end", "or_high", "or_low", "width")
               + HIT_NAMES
               + ("first_breakout_side", "first_breakout_bar", "label_up_bar", "label_dn_bar")
               + tuple("hit_" + k for k in HIT_NAMES) + tuple("hit_" + k + "_bar" for k in HIT_NAMES)
               + TRADE1_COLUMNS + TRADE2_COLUMNS)


# ───────────────────────────── Pine's na semantics (R16) ─────────────────────────────

def isna(x) -> bool:
    """Pine ``na(x)`` for a float."""
    return x != x


def nz(x, y=0.0):
    """Pine ``nz(x, y)``: ``y`` when ``x`` is na, else ``x``."""
    return y if isna(x) else x


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
    """``ta.sma(x, n)`` as pine_sma: ``sum := sum + x[i] / n`` for i = 0 (this bar) .. n - 1, so the bar itself is in
    the window (R8); na until n values exist, and na when one of them is na."""
    xs = _floats(x, "x")
    out = [NAN] * len(xs)
    for t in range(n - 1, len(xs)):
        s = 0.0
        for i in range(n):
            s = s + xs[t - i] / n
        out[t] = s
    return np.asarray(out, dtype=np.float64)


def pine_rma(x, n: int) -> np.ndarray:
    """``ta.rma(x, n)`` as pine_rma: ``sum := na(sum[1]) ? ta.sma(x, n) : alpha * x + (1 - alpha) * nz(sum[1])`` with
    ``alpha = 1 / n``: na until the SMA exists, seeded with it."""
    xs = _floats(x, "x")
    seed = pine_sma(xs, n).tolist()
    alpha = 1 / n
    out = [NAN] * len(xs)
    prev = NAN
    for t in range(len(xs)):
        if isna(prev):
            val = seed[t]
        else:
            val = alpha * xs[t] + (1 - alpha) * nz(prev)
        out[t] = val
        prev = val
    return np.asarray(out, dtype=np.float64)


def pine_tr(h, l, c) -> np.ndarray:
    """``ta.tr(true)`` as in pine_atr: ``na(high[1]) ? high - low : math.max(math.max(high - low, math.abs(high -
    close[1])), math.abs(low - close[1]))``: high - low on bar 0 (R9)."""
    H, L, C = _floats(h, "high"), _floats(l, "low"), _floats(c, "close")
    out = [NAN] * len(H)
    for t in range(len(H)):
        if t == 0:
            out[t] = H[t] - L[t]
        else:
            out[t] = pmax(pmax(H[t] - L[t], abs(H[t] - C[t - 1])), abs(L[t] - C[t - 1]))
    return np.asarray(out, dtype=np.float64)


def pine_atr(h, l, c, n: int = ATR_LEN) -> np.ndarray:
    """``ta.atr(n)`` = ``ta.rma(ta.tr(true), n)``: na on bars 0 .. n - 2 (R9)."""
    return pine_rma(pine_tr(h, l, c), n)


# ───────────────────────────── the clocks (l.35, 87, 88, 225) ─────────────────────────────

def _clock_offset(clock: str):
    """'ny' -> None (America/New_York), 'utc-5' -> -18000 (seconds east of UTC: the script's "UTC-5", l.35). The
    contract has these two clocks only (``CLOCKS``); any other value is refused, as by port A."""
    if not isinstance(clock, str) or clock not in CLOCKS:
        raise ValueError(f"clock: one of {CLOCKS}, got {clock!r}")
    return None if clock == "ny" else -5 * 3600


def _local_seconds(t: Sequence[int], offset) -> List[int]:
    """UTC epoch seconds -> wall-clock seconds of the clock (as if that clock were UTC)."""
    if offset is None:
        return [ti + int(datetime.fromtimestamp(ti, NY).utcoffset().total_seconds()) for ti in t]
    return [ti + offset for ti in t]


def session_clock(t, clock: str = "ny") -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The session clock of each bar's OPEN time ``t``: (minute of the day 0..1439, the local date as an epoch day
    number, Pine's ``dayofweek`` 1 = Sunday .. 7 = Saturday). 'ny' is America/New_York with daylight saving; 'utc-5'
    a fixed UTC-5 (R1, R2)."""
    ts = [int(x) for x in np.asarray(t, dtype=np.int64).tolist()]
    loc = _local_seconds(ts, _clock_offset(clock))
    minute = [(s % DAY_S) // 60 for s in loc]
    day = [s // DAY_S for s in loc]
    dow = [(d + 4) % 7 + 1 for d in day]            # epoch day 0, 1970-01-01, was a Thursday (dayofweek 5)
    return (np.asarray(minute, np.int64), np.asarray(day, np.int64), np.asarray(dow, np.int64))


def day_boundary_of(day_boundary: str = "auto", symbol: Optional[str] = None) -> str:
    """'ny17' (the exchange day starts at 17:00 New York: gold, FX, CFDs), 'utc0' (00:00 UTC: crypto) or 'clock0'
    (midnight of the session clock: R3's alternative reading, for measurement only); 'auto' picks by ``symbol``
    (BTC / ETH -> 'utc0', anything else -> 'ny17') and needs one (R3)."""
    if not isinstance(day_boundary, str) or day_boundary not in DAY_BOUNDARIES:
        raise ValueError(f"day_boundary: one of {DAY_BOUNDARIES}, got {day_boundary!r}")
    if day_boundary == "auto":
        if not symbol:
            raise ValueError("day_boundary='auto' needs the symbol (gold: 17:00 New York, BTC: 00:00 UTC)")
        return "utc0" if str(symbol).upper().startswith(("BTC", "ETH")) else "ny17"
    return day_boundary


def exchange_day(t, boundary: str, clock: str = "ny") -> np.ndarray:
    """The exchange's trading day of each bar's open time (``time("D")`` of l.88, R3), as an epoch day number:
    'ny17': the New York date of (New York wall-clock time + 7 h), so a day runs 17:00-17:00 New York; 'utc0': the
    UTC date; 'clock0': the date of the session clock ``clock`` (the alternative reading). ``boundary`` must be
    explicit ('auto' needs a symbol: ``day_boundary_of``)."""
    ts = [int(x) for x in np.asarray(t, dtype=np.int64).tolist()]
    b = day_boundary_of(boundary)
    if b == "utc0":
        return np.asarray([ti // DAY_S for ti in ts], np.int64)
    if b == "clock0":
        return np.asarray([s // DAY_S for s in _local_seconds(ts, _clock_offset(clock))], np.int64)
    loc = _local_seconds(ts, None)
    return np.asarray([(s + 7 * 3600) // DAY_S for s in loc], np.int64)


def _days_set(days) -> frozenset:
    """The session days as Pine ``dayofweek`` numbers (1 = Sunday .. 7 = Saturday): 'weekdays' = "23456", 'all' =
    "1234567" (the script's default, l.34). The contract has these two only (``DAY_SETS``)."""
    if not isinstance(days, str) or days not in DAY_SETS:
        raise ValueError(f"days: one of {DAY_SETS}, got {days!r}")
    if days == "weekdays":
        return frozenset((2, 3, 4, 5, 6))          # "23456": Monday .. Friday
    return frozenset(range(1, 8))                  # "1234567"


# ───────────────────────────── the script ─────────────────────────────

class _Trade:
    """One trade of the script (l.255-286): what it books and when ('open' until it ends)."""
    __slots__ = _TRADE

    def __init__(self, d: int, bar: int, price: float):
        self.side, self.entry_bar, self.entry_price = d, bar, price
        self.exit_bar, self.exit_price, self.exit_reason = -1, NAN, "open"


class _Session:
    """One counted session (a row of ``days``) and what happens from its end to the next reset."""

    def __init__(self, day: int, start_bar: int, end_bar: int, or_high: float, or_low: float):
        self.day, self.start_bar, self.end_bar, self.post_bar = day, start_bar, end_bar, end_bar + 1
        self.or_high, self.or_low = or_high, or_low
        self.first_side, self.first_bar = 0, -1
        self.hit_bar = {k: -1 for k in HIT_NAMES}
        self.label_up_bar = self.label_dn_bar = -1
        self.trades: List[_Trade] = []
        self.span_end = -1                  # the next reset (l.147) after the session's end; -1 until it comes


class _Vars:
    """The script's ``var`` state that the signals read (l.90-126), with its initial values."""

    def __init__(self):
        self.orHigh = NAN                       # l.90
        self.orLow = NAN                        # l.91
        self.sessionEnded = False               # l.92
        self.totalSessions = 0                  # l.94
        self.countU = [0, 0, 0]                 # l.95-97
        self.countD = [0, 0, 0]                 # l.98-100
        self.dayReachedU = [False, False, False]    # l.102-104
        self.dayReachedD = [False, False, False]    # l.105-107
        self.entryPrice = NAN                   # l.115
        self.trailStop = NAN                    # l.122
        self.activeDir = 0                      # l.123
        self.canSignalUp = True                 # l.125
        self.canSignalDn = True                 # l.126


def _check_inputs(t, o, h, l, c, v, tf_min, sess, window_end, trail_mult, multiples):
    ta = np.asarray(t)
    if ta.ndim != 1:
        raise ValueError(f"t: a 1-D array is expected, got shape {ta.shape}")
    if not np.issubdtype(ta.dtype, np.integer):
        raise ValueError(f"t: UTC epoch seconds of an integer dtype are expected, got {ta.dtype}")
    n = len(ta)
    cols = {}
    for name, x in (("o", o), ("h", h), ("l", l), ("c", c), ("v", v)):
        if name == "v" and x is None:               # no volume: Pine's na volume, so isHV is false (l.239)
            cols[name] = [NAN] * n
            continue
        a = np.asarray(x, dtype=np.float64)
        if a.ndim != 1 or len(a) != n:
            raise ValueError(f"{name}: a 1-D array of the length of t ({n}) is expected, got shape {a.shape}")
        if not np.isfinite(a).all():
            raise ValueError(f"{name}: NaN or infinite values are not ported")
        cols[name] = a.tolist()
    ts = [int(x) for x in np.asarray(ta, dtype=np.int64).tolist()]
    if isinstance(tf_min, bool) or int(tf_min) != tf_min or int(tf_min) < 1 or 1440 % int(tf_min):
        raise ValueError(f"tf_min: a whole number of minutes dividing a day, got {tf_min!r}")
    step = int(tf_min) * 60
    for i in range(n):
        if i and ts[i] <= ts[i - 1]:
            raise ValueError(f"t: open times must increase strictly (bar {i})")
        if ts[i] % step:
            raise ValueError(f"t: bar {i} opens off the {int(tf_min)}-minute grid")
    try:
        a, b = (int(x) for x in sess)
    except (TypeError, ValueError):
        raise ValueError(f"sess: (start, end) in minutes, got {sess!r}") from None
    if not (0 <= a < b <= 1440) or (a, b) != tuple(sess):
        raise ValueError(f"sess: whole minutes with 0 <= start < end <= 1440, got {sess!r}")
    if int(window_end) != window_end or not (a < int(window_end) <= 1440):
        raise ValueError(f"window_end: a whole minute after the session's start, at most 1440, got {window_end!r}")
    tm = float(trail_mult)
    if not (math.isfinite(tm) and tm > 0):
        raise ValueError(f"trail_mult: a positive number, got {trail_mult!r}")
    f = [float(x) for x in multiples]
    if len(f) != 3 or not all(math.isfinite(x) and x >= 0 for x in f):
        raise ValueError(f"multiples: three numbers >= 0 (l.40-42), got {multiples!r}")
    return ts, cols, (a, b), int(window_end), tm, f


_BOOL_KEYS = ("session_ended", "breakout_up", "breakout_dn", "label_up", "label_dn", "can_up", "can_dn")
_INT_KEYS = ("total_sessions",) + tuple("count_" + k for k in HIT_NAMES)
_OUT_KEYS = (("or_high", "or_low", "or_high_live", "or_low_live") + _BOOL_KEYS
             + ("active_dir", "trail", "entry_price", "u1", "u2", "u3", "d1", "d2", "d3") + _INT_KEYS)
_TYPECODE = {**{k: "b" for k in _BOOL_KEYS}, "active_dir": "b", **{k: "q" for k in _INT_KEYS}}


def _run(t, o, h, l, c, v, tf_min, sess=(570, 600), window_end=1020, clock="ny", days="weekdays",
         trail_mult=2.0, multiples=(1.0, 2.0, 3.0), day_boundary="auto", symbol=None, *,
         first_bar_new_day: bool = False) -> Dict[str, object]:
    """The script, bar by bar. Returns every per-bar series (``orb_series``) and the ``days`` frame.
    ``first_bar_new_day=True`` is R4's alternative reading (``isNewDay`` true on bar 0, IEEE ``NaN != 0``), kept only
    to measure that it changes nothing but ``new_day[0]``; it is not part of the contract."""
    ts, col, (s0, s1), w1, trailMult, (f1, f2, f3) = _check_inputs(t, o, h, l, c, v, tf_min, sess, window_end,
                                                                     trail_mult, multiples)
    H, L, C, V = col["h"], col["l"], col["c"], col["v"]           # the open is read only by srcInput "Close"
    n = len(ts)
    allowed = _days_set(days)
    boundary = day_boundary_of(day_boundary, symbol)

    # ── series computed on every bar (they do not depend on the state) ──
    minute, lday, dow = session_clock(ts, clock)
    inSess = [bool(dow[i] in allowed and s0 <= minute[i] < s1) for i in range(n)]            # l.87 (R1, R2)
    display = [bool(dow[i] in allowed and s0 <= minute[i] < w1) for i in range(n)]           # l.225 (R1, R15)
    dkey = exchange_day(ts, boundary, clock).tolist()
    newDay = [dkey[i] != dkey[i - 1] if i > 0 else bool(first_bar_new_day) for i in range(n)]  # l.88 (R3, R4)
    atrTrail = pine_atr(H, L, C, ATR_LEN).tolist()                                           # l.236 (R9)
    volSMA = pine_sma(V, VOL_LEN).tolist()                                                   # l.238 (R8)
    isHV = [bool(V[i] > volSMA[i]) for i in range(n)]                                        # l.239 (na -> false)
    f = (f1, f2, f3)

    # the end-of-bar values, in compact buffers ('d' float64, 'b' int8 for bools and activeDir, 'q' int64 counts)
    out = {k: array(_TYPECODE.get(k, "d")) for k in _OUT_KEYS}

    s = _Vars()
    rows: List[_Session] = []
    cur: Optional[_Session] = None          # the counted session whose post-session period is running
    open_trade: Optional[_Trade] = None
    range_start = -1                        # the range's first bar: the last bar where l.147 fired in session (R12)
    # the histories the script reads with [1]: the values at the end of the previous bar
    inSession_1, close_1, orHigh_1, orLow_1, trailStop_1 = False, NAN, NAN, NAN, NAN       # R5

    for i in range(n):
        inSession, isNewDay = inSess[i], newDay[i]
        high, low, close = H[i], L[i], C[i]

        # l.147-163: the reset
        if isNewDay or (inSession and not inSession_1):
            s.orHigh = NAN
            s.orLow = NAN
            s.sessionEnded = False
            s.dayReachedU = [False, False, False]
            s.dayReachedD = [False, False, False]
            s.entryPrice = NAN
            if cur is not None:
                cur.span_end = i
                cur = None
            if inSession:
                range_start = i

        # l.166-171: the range ("High/Low")
        if inSession:
            currentHigh, currentLow = high, low
            s.orHigh = currentHigh if isna(s.orHigh) else pmax(s.orHigh, currentHigh)
            s.orLow = currentLow if isna(s.orLow) else pmin(s.orLow, currentLow)

        # l.181-183: the session end
        if not inSession and inSession_1:
            s.sessionEnded = True
            s.totalSessions += 1
            cur = _Session(int(lday[range_start]), range_start, i - 1, s.orHigh, s.orLow)
            rows.append(cur)

        # l.185-193: the levels
        orRange = s.orHigh - s.orLow
        u = [s.orHigh + orRange * fk for fk in f]
        d = [s.orLow - orRange * fk for fk in f]

        # l.195-214: the hit counts (unconditional)
        if s.sessionEnded:
            for k in range(3):
                if not isna(u[k]) and high >= u[k] and not s.dayReachedU[k]:
                    s.countU[k] += 1
                    s.dayReachedU[k] = True
                    cur.hit_bar[HIT_NAMES[k]] = i
            for k in range(3):
                if not isna(d[k]) and low <= d[k] and not s.dayReachedD[k]:
                    s.countD[k] += 1
                    s.dayReachedD[k] = True
                    cur.hit_bar[HIT_NAMES[3 + k]] = i

        # l.225: displayAllowed (stopPlotting true)
        displayAllowed = display[i]

        # l.243-244: the breakouts (R7)
        crossover = (not (isna(close) or isna(s.orHigh) or isna(close_1) or isna(orHigh_1))
                     and close > s.orHigh and close_1 <= orHigh_1)
        crossunder = (not (isna(close) or isna(s.orLow) or isna(close_1) or isna(orLow_1))
                      and close < s.orLow and close_1 >= orLow_1)
        breakoutUp = crossover and not inSession and s.sessionEnded
        breakoutDn = crossunder and not inSession and s.sessionEnded
        if (breakoutUp or breakoutDn) and cur.first_bar < 0:
            cur.first_side, cur.first_bar = (1 if breakoutUp else -1), i

        # l.246-250: the daily gates; a trade still open vanishes unbooked (R11)
        if isNewDay or inSession:
            s.canSignalUp = True
            s.canSignalDn = True
            if s.activeDir != 0:
                open_trade.exit_bar, open_trade.exit_reason = i, "reset"
                open_trade = None
            s.activeDir = 0
            s.trailStop = NAN

        # l.252-261: the bull label and the long
        labelUp = False
        if breakoutUp and s.canSignalUp and displayAllowed:
            labelUp = True
            cur.label_up_bar = i
            s.canSignalUp = False
            if s.activeDir == 0:
                s.activeDir = 1
                s.entryPrice = s.orHigh
                s.trailStop = low - (atrTrail[i] * trailMult)
                open_trade = _Trade(1, i, s.entryPrice)
                cur.trades.append(open_trade)

        # l.263-272: the bear label and the short (before the trail exit)
        labelDn = False
        if breakoutDn and s.canSignalDn and displayAllowed:
            labelDn = True
            cur.label_dn_bar = i
            s.canSignalDn = False
            if s.activeDir == 0:
                s.activeDir = -1
                s.entryPrice = s.orLow
                s.trailStop = high + (atrTrail[i] * trailMult)
                open_trade = _Trade(-1, i, s.entryPrice)
                cur.trades.append(open_trade)

        # l.274-279: the long's trail and exit (R10, R11)
        if s.activeDir == 1:
            stop_now = low - (atrTrail[i] * trailMult)
            s.trailStop = pmax(nz(trailStop_1, stop_now), stop_now)
            if close < s.trailStop or not displayAllowed:
                open_trade.exit_bar, open_trade.exit_price = i, close
                open_trade.exit_reason = "trail" if close < s.trailStop else "window"
                open_trade = None
                s.activeDir = 0
                s.trailStop = NAN

        # l.281-286: the short's trail and exit
        if s.activeDir == -1:
            stop_now = high + (atrTrail[i] * trailMult)
            s.trailStop = pmin(nz(trailStop_1, stop_now), stop_now)
            if close > s.trailStop or not displayAllowed:
                open_trade.exit_bar, open_trade.exit_price = i, close
                open_trade.exit_reason = "trail" if close > s.trailStop else "window"
                open_trade = None
                s.activeDir = 0
                s.trailStop = NAN

        # the end of the bar: what the bar shows, and the histories for the next one
        final = s.sessionEnded
        out["or_high"].append(s.orHigh if final else NAN)
        out["or_low"].append(s.orLow if final else NAN)
        out["or_high_live"].append(s.orHigh)
        out["or_low_live"].append(s.orLow)
        out["session_ended"].append(s.sessionEnded)
        out["breakout_up"].append(breakoutUp)
        out["breakout_dn"].append(breakoutDn)
        out["label_up"].append(labelUp)
        out["label_dn"].append(labelDn)
        out["active_dir"].append(s.activeDir)
        out["trail"].append(s.trailStop)
        out["entry_price"].append(s.entryPrice)
        out["can_up"].append(s.canSignalUp)
        out["can_dn"].append(s.canSignalDn)
        out["total_sessions"].append(s.totalSessions)
        for k in range(3):
            out["u%d" % (k + 1)].append(u[k])
            out["d%d" % (k + 1)].append(d[k])
            out["count_u%d" % (k + 1)].append(s.countU[k])
            out["count_d%d" % (k + 1)].append(s.countD[k])
        inSession_1, close_1, orHigh_1, orLow_1, trailStop_1 = inSession, close, s.orHigh, s.orLow, s.trailStop

    res: Dict[str, object] = {
        "in_session": np.asarray(inSess, dtype=bool),
        "new_day": np.asarray(newDay, dtype=bool),
        "display": np.asarray(display, dtype=bool),
        "hv": np.asarray(isHV, dtype=bool),
        "atr": np.asarray(atrTrail, dtype=np.float64),
        "vol_sma": np.asarray(volSMA, dtype=np.float64),
        "local_minute": minute,
        "local_day": lday,
        "dow": dow,
        "exchange_day": np.asarray(dkey, dtype=np.int64),
    }
    for k, buf in out.items():
        if k in _BOOL_KEYS:
            res[k] = np.array(buf, dtype=np.int8).astype(bool)
        elif k == "active_dir":
            res[k] = np.array(buf, dtype=np.int8)
        elif k in _INT_KEYS:
            res[k] = np.array(buf, dtype=np.int64)
        else:
            res[k] = np.array(buf, dtype=np.float64)
    del out
    res["days"] = _frame(rows, n, f)
    return res


def _frame(rows: List[_Session], n: int, f: Tuple[float, float, float]) -> pd.DataFrame:
    """The ``days`` frame (columns ``DAY_COLUMNS``; dtypes fixed even when it is empty). ``n``: the number of bars
    (``span_end`` of a span the data end before its next reset); ``f``: the three multiples of the levels."""
    def trade(r: _Session, j: int, key: str):
        if len(r.trades) <= j:
            return {"side": 0, "entry_bar": -1, "entry_price": NAN, "exit_bar": -1, "exit_price": NAN,
                    "exit_reason": ""}[key]
        return getattr(r.trades[j], key)

    hi = [r.or_high for r in rows]
    lo = [r.or_low for r in rows]
    width = [x - y for x, y in zip(hi, lo)]                     # orRange (l.185)
    data = {
        "day": pd.Series([r.day for r in rows], dtype=np.int64),
        "start_bar": pd.Series([r.start_bar for r in rows], dtype=np.int64),
        "end_bar": pd.Series([r.end_bar for r in rows], dtype=np.int64),
        "post_bar": pd.Series([r.post_bar for r in rows], dtype=np.int64),
        "span_end": pd.Series([r.span_end if r.span_end >= 0 else n for r in rows], dtype=np.int64),
        "or_high": pd.Series(hi, dtype=np.float64),
        "or_low": pd.Series(lo, dtype=np.float64),
        "width": pd.Series(width, dtype=np.float64),
    }
    for k in range(3):                                          # getExt (l.139-142, 191-193)
        data["u%d" % (k + 1)] = pd.Series([x + w * f[k] for x, w in zip(hi, width)], dtype=np.float64)
    for k in range(3):
        data["d%d" % (k + 1)] = pd.Series([y - w * f[k] for y, w in zip(lo, width)], dtype=np.float64)
    data["first_breakout_side"] = pd.Series([r.first_side for r in rows], dtype=np.int64)
    data["first_breakout_bar"] = pd.Series([r.first_bar for r in rows], dtype=np.int64)
    data["label_up_bar"] = pd.Series([r.label_up_bar for r in rows], dtype=np.int64)
    data["label_dn_bar"] = pd.Series([r.label_dn_bar for r in rows], dtype=np.int64)
    for k in HIT_NAMES:
        data["hit_" + k] = pd.Series([r.hit_bar[k] >= 0 for r in rows], dtype=bool)
    for k in HIT_NAMES:
        data["hit_" + k + "_bar"] = pd.Series([r.hit_bar[k] for r in rows], dtype=np.int64)
    for j, names in ((0, TRADE1_COLUMNS), (1, TRADE2_COLUMNS)):
        for key, name in zip(_TRADE, names):
            vals = [trade(r, j, key) for r in rows]
            if key in ("side", "entry_bar", "exit_bar"):
                data[name] = pd.Series(vals, dtype=np.int64)
            elif key == "exit_reason":
                data[name] = pd.Series(vals, dtype=object)
            else:
                data[name] = pd.Series(vals, dtype=np.float64)
    return pd.DataFrame(data, columns=list(DAY_COLUMNS))


def orb(t, o, h, l, c, v, tf_min, sess=(570, 600), window_end=1020, clock="ny", days="weekdays", trail_mult=2.0,
        multiples=(1.0, 2.0, 3.0), day_boundary="auto", symbol=None) -> Dict[str, object]:
    """
    The script on chart bars: the contract's per-bar arrays (``KEYS`` without 'days') and the ``days`` frame (see the
    module docstring for every input, key and column, the statement order and the readings R1-R16).

    ``t``: bar OPEN times (UTC s, strictly increasing, on the ``tf_min`` grid); ``o``, ``h``, ``l``, ``c``, ``v``: bid
    OHLC and volume; ``tf_min``: 5 or 15; ``sess``: the session in minutes of the session clock, [start, end);
    ``window_end``: the display window's end (17:00 = 1020); ``clock``: 'ny' (New York with daylight saving) or
    'utc-5' (the script's fixed default); ``days``: 'weekdays' or 'all'; ``day_boundary``: 'auto' (by ``symbol``),
    'ny17' (gold: 17:00 New York) or 'utc0' (BTC: 00:00 UTC).
    """
    r = _run(t, o, h, l, c, v, tf_min, sess, window_end, clock, days, trail_mult, multiples, day_boundary, symbol)
    return {k: r[k] for k in KEYS}


def orb_series(t, o, h, l, c, v, tf_min, sess=(570, 600), window_end=1020, clock="ny", days="weekdays",
               trail_mult=2.0, multiples=(1.0, 2.0, 3.0), day_boundary="auto", symbol=None) -> Dict[str, object]:
    """
    Everything ``orb`` returns plus the script's other per-bar variables at the end of each bar (not part of the
    comparison; for the reconciliation and the tests): ``or_high_live`` / ``or_low_live`` (the script's ``orHigh`` /
    ``orLow``, forming during the session), ``u1`` .. ``d3`` (l.191-193), ``display`` (``displayAllowed``),
    ``can_up`` / ``can_dn``, ``entry_price``, ``total_sessions``, ``count_u1`` .. ``count_d3`` (the dashboard's
    numbers, l.374-379 and 425-455: the hit rate the script shows on bar i is ``count / total_sessions``, today
    included), ``vol_sma``, the session clock (``local_minute``, ``local_day``, ``dow``) and ``exchange_day``.
    """
    return _run(t, o, h, l, c, v, tf_min, sess, window_end, clock, days, trail_mult, multiples, day_boundary, symbol)
