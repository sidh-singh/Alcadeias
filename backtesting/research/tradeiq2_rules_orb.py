"""
Ultimate Opening Range Breakout [LuxAlgo] as rules (study 2, PREREG 6.5 and claims 6-9 of section 8): the rule rows of
the ORB module for the driver (``tradeiq2.py``), ``variants(symbol)`` and ``build(variant, ctx)``, and the functions of
claims 6-9 (``claim6`` .. ``claim9``).

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_orb as R
    mk = M.load("XAUUSDm", end="2024-07-01")
    ctx = M.Context(mk)
    vs = R.variants("XAUUSDm")             # 82 rows: 72 eligible + 10 controls (not eligible)
    ex = R.build(vs[0], ctx)               # a tradeiq2_market.Exec (EVENTS: market entries, or stop orders for O5)
    res = M.run_variant(ctx, vs[0], ex)    # Development, Validation and D+V at x1.0 and x1.5

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen; read with ``DEVIATIONS.md``): sections 4 (execution,
the rules for absolute levels), 5 (the filters and how they apply to event rules), 6.5 (the rows), 7 (families,
eligibility) and claims 6-9 of section 8. The signals are the reconciled port ``tradeiq2_ind_orb`` (port A, equal bit
for bit to port B on the study's M5 / M15 bars of both symbols in every configuration used here;
``backtest_results/tradeiq_2027/porting/orb.md``), the filters ``tradeiq2_filters``, the execution ``tradeiq2_market``
(study 1's fills, stops, marks and scores) and, for TIGHT only, Session Hunter's day state from the reconciled port
``tradeiq2_ind_session``. Nothing is tuned: every input of the script is its default (the session "0930-1000", the
"High/Low" source, the multiples 1 / 2 / 3, the display window to "New York Close" = 17:00, the trail 2 x ATR(14), the
volume SMA(20)) unless the plan says otherwise. Line numbers (l.) are those of the owner's plain-text copy of the
script (Pine v6, CC BY-NC-SA 4.0, (c) LuxAlgo; third-party code, cited here, never copied); "SH l." are Session
Hunter's.

The grid
--------
Per symbol (PREREG 6.5 "Size"; ``variants`` gives exactly these rows):

=============================================================================== ======== ===== ========================
rows                                                                             gold     BTC   eligible
=============================================================================== ======== ===== ========================
O1-O5 x F0, HV, F2-4H, F2-1D, HV+F2-4H x M5, M15                                 50       50    yes
O1-O5 x LO x M5, M15                                                             10       -     yes (gold only)
ORB-CX: O1, O5 x F0, F2-4H x M5, M15                                             8        -     yes (gold only)
TIGHT: O1, O5 (F0) x M5, M15                                                     4        4     yes
LV only: O1-O4 x M5, M15 (claim 7)                                               8        8     no (control)
the script's literal UTC-5 clock: O1 x F0 x M5, M15 (claim 9)                    2        2     no (control)
BTC on all 7 days: O1 x F0 x M5, M15                                             -        2     no (control)
=============================================================================== ======== ===== ========================

Gold 82 (72 eligible), BTC 66 (54 eligible); the claim markets have no ORB row. Family and script: ORB (PREREG 7: "the
ORB rows, including ORB-CX and TIGHT"). Ids (``|``-separated tokens; the driver pairs rows by swapping one token):
``symbol|tf|ORB|rule|filter`` with filter in F0, HV, F2-4H, F2-1D, HV+F2-4H, LO, LV, and a last token for the other
versions: ``...|O1|F0|ORB-CX``, ``...|O5|F2-4H|ORB-CX``, ``...|O1|F0|TIGHT``, ``...|O1|F0|UTC-5``, ``...|O1|F0|7D``.
So HV -> LV (claim 7), O4 -> O2 / O3 (claim 8), F2-4H / F2-1D -> F0 (the driver's vs_f0, also within ORB-CX) and a
version token dropped (the plan's main row) each give the row's partner.

What a row does (an EVENT rule: PREREG 5's filters gate the entry and close no trade, except HV on O5, reading 7)
----------------------------------------------------------------------------------------------------------------
* THE RANGE AND THE BREAKOUTS are the port's, run on the chart bars ``ctx.bars('M5' | 'M15')`` (the bid OHLC) with the
  volume of PREREG 2 (``ctx.volume``: gold's tick volume, BTC's Binance BTCUSDT spot 5m volume): the range is the high
  and low of the bars that OPEN in 09:30-10:00 New York (daylight saving included, the plan's clock) on New York
  weekdays (l.87, 166-171; on M5 the bars 09:30 .. 09:55, on M15 09:30 and 09:45); a breakout is the script's
  ``ta.crossover(close, orHigh)`` / ``ta.crossunder(close, orLow)`` after the session (l.243-244); a LABEL is the first
  breakout of each side in the display window 09:30-17:00 (l.252, 263; ``canSignalUp`` / ``canSignalDn``: one per side
  and day). The labels are the market rules' candidates. The day reset is the exchange's (the port's 'auto': 17:00 New
  York for gold, 00:00 UTC for BTC); it falls after every decision of a row.
* DECISION WINDOW AND FLAT TIME (PREREG 6.5). A label is a candidate when its bar closes at or before 16:00 New York of
  the session's date. Every trade's last exit decision is the close of the FLAT BAR: the last chart bar of that date
  closing at or before 16:55 New York (M5: the bar opening 16:50; M15: the bar opening 16:30), filled at the next M1
  open; when no M1 bar opens at that close (an early close, a data hole) it is booked at the close of the flat bar's
  last M1 bar instead, before the break (the harness's ``close_gap``; reading 3). A label at or after the flat bar
  (possible only on an early close) is not a candidate.
* O1, the script's trade: a market entry at the label (decided at its close, filled at the next M1 open: a buy at the
  ask, a sell at the bid), out at the close of the first bar whose close is below the trail, ``max(trail[1], low -
  2 x ATR(14))`` from the label bar on (l.258, 274-279: ``math.max(nz(trailStop[1], x), x)``; a short mirrors it with
  ``min`` and ``high + 2 x ATR``, l.269, 281-286), else at the flat time; no other stop, so no R. One position at a
  time, in the script's order: a label on the bar where the open trade's trail exits is used up while the trade is
  still open (l.263 runs before l.276), so it opens nothing. With F0 these are exactly the script's own trades
  (``days.trade_side`` / ``entry_bar`` / ``exit_bar`` of the port, before the flat time: tested).
* O2 / O3: a market entry at the label; target T1 = ``u1`` / ``d1`` (the range edge + 1 range width, l.187-193) for O2,
  T2 = ``u2`` / ``d2`` (2 widths) for O3; stop at the far side of the range (a long's ``orLow``, a short's
  ``orHigh``); else the flat time. Both levels are absolute: the harness measures them from the ACTUAL fill
  (|fill - level|), drops an entry whose fill is at or beyond its stop or its target (PREREG 4), and the x1.5 run
  recomputes all of it on its own spreads. One position at a time (the harness: a label while a trade is open is
  "busy"); a trade stopped inside a bar is flat at that bar's close, so a label there opens the next trade.
* O4, the video's "use the hit rates to pick your target": as O2 with the target T_k, k the furthest of 1-3 whose
  hit rate after past breakouts of the trade's side is at least 50%, once at least 60 past sessions have a label of
  that side decided by 16:00 New York (else T1; reading 5): ``o4_targets``.
* O5: at the close of the range's last bar (10:00 New York; the bar before the first post-session bar) a buy stop at
  ``orHigh`` and a sell stop at ``orLow``, one cancels the other, cancelled at 16:00 New York (the first M1 bar opening
  at or after it); a buy fills once the ask reaches the level, at max(level, ask at the open), a sell once the bid
  does, at min(level, bid at the open) (PREREG 4); the stop at the far side (absolute, from the actual fill); exits as
  O1: the trail starting at the chart bar that holds the fill (its low - 2 x ATR, its close-based exit from the next
  bar on) and the flat time (reading 6). At most one trade a day.
* FILTERS (PREREG 6.5 / 5), checked at the label's decision close (O1-O4): F0 none; HV the label bar's volume above
  ``ta.sma(volume, 20)`` with that bar included (the port's ``hv``, l.238-239: strict, an na SMA is LV); LV its
  complement (the claim-7 control); F2-4H / F2-1D the last CLOSED 4H / 1D bar's close against its MA200
  (``ctx.allow``); HV+F2-4H both; LO long only (gold). A refused label opens nothing (and, one label per side and day,
  that side has no other candidate that day); the trade a filter lets in keeps its own exits. O5: F2-4H, F2-1D and LO
  are checked at the orders' placement close (``tradeiq2_filters.gate_orders``: a refused side is not placed); HV is
  checked at the close of the chart bar that holds the fill, the first moment that breakout bar's volume is known, and
  an LV fill bar closes the trade there (reading 7).
* TIGHT (our own; Session Hunter's tight-range test, SH l.65-66, 191-194, 211, 324-325): a session is traded (O1, O5,
  F0) only when its width is below 50% of Session Hunter's ``adr``, the mean high-low range of the last (up to) 10
  finished weekday trading days of its clock (20:00-20:00 New York; at least 5 needed), read at the range's last bar
  (``tradeiq2_ind_session.day_state``; reading 8).
* ORB-CX (our own, gold): the COMEX-open range 08:20-08:50 New York (``tradeiq2_ind_orb.COMEX_SESSION``; on M15 the bars
  opening 08:30 and 08:45, i.e. 08:30-09:00, as the script's bar-open membership gives); O5's orders are active from
  that range's end to 16:00 (reading 9). The decision window and the flat time are unchanged.
* THE CONTROLS (not eligible): LV only (O1-O4); the script's literal fixed UTC-5 clock (O1 x F0: the range, the display
  window and the session days on UTC-5, an hour late from March to November; the 16:00 cut and the 16:55 flat time stay
  New York times, reading 10); BTC on all 7 days (O1 x F0, the 09:30 New York range also on Saturdays and Sundays).
* TAGS: every entry and order carries its session's New York date (an epoch day number) as ``tag``.

What is known when (no look-ahead)
----------------------------------
The range is final at the close of the session's last bar and the port's labels, ``hv`` and ATR at the close of their
bar (they read bars 0 .. i). The 16:00 cut and the flat time are clock times fixed in advance; the flat bar of a
session is the last bar closing at or before 16:55, and while the data end lies before that instant it is unknown
(``flat_bar`` -1: no exit row, the harness runs the trade to the window's end). A trail exit at bar k reads bars e .. k.
``close_gap`` decides nothing: it only says where an exit decided at a bar's close is booked when no M1 bar opens at
that close (the harness looks for the gap); O2-O5's rows carry it from the start, O1's is known with its exit. That
booking does take one fact as known before the bars show it: on an early close the bars show which bar is the flat bar
only at 16:55 and the gap only at the reopen, so booking at the flat bar's last M1 close takes both from the market's
published early-close hours (harness reading 15). A data hole could not be known then (BTC's 5 sessions to
2024-06-30, none in Development).
O4's rates count only sessions before the decision's (each complete by its own flat bar, the day before or earlier).
TIGHT's ``adr`` reads finished trading days. The orders are placed at the range's close with its levels. The port
counts a session on its first post-session bar (``post_bar``, where the script's ``sessionEnded`` turns true), which
opens at the instant the range's last bar closes (10:00), so an order exists in the data once that bar does, and it can
fill only from that bar's first M1 bar on: nothing is filled before the bar that tells the session ended (after a data
hole the order is live from the first bar after it). The HV check of an O5 fill reads its bar at that bar's close.
Removing the bars after T changes no entry or exit decided at a bar closing at or before T, and no order whose
post-session bar opens before T (tested on synthetic and on real bars).

Readings where the plan leaves a choice (deviation paragraphs, for DEVIATIONS.md)
--------------------------------------------------------------------------------
1. THE CANDIDATES ARE THE SCRIPT'S LABELS. "Breakout: the script's crossover of the close from 10:00 on; one label per
   side per day" is read as the port's ``label_up`` / ``label_dn``: the first crossover of each side in the display
   window, decided at its bar's close. A later re-cross of the same side (an alert, l.480-481, not a label) is never a
   candidate, also when the first one was refused by a filter or was busy.
2. "NO NEW TRADE WHILE ONE IS OPEN" IS THE ROW'S OWN POSITION. One position at a time, the row's own trade. With F0, O1
   is the script's trade logic exactly. Under a filter, a refused label opens nothing and blocks nothing: the other
   side's later label may then open a trade, which the script itself (whose refused trade would still be open in its
   own bookkeeping) would not. The script's order ("the bear branch evaluated before the trail exit") is applied to O1
   and O5: a label on the bar whose close exits the open trade by its trail finds the trade still open and opens
   nothing. O2-O4 have no close-based exit before the flat time: a trade stopped or at its target inside a bar is flat
   at that bar's close.
3. THE FLAT TIME. "Everything is flat at the last chart-bar close at or before 16:55 New York" is the exit decision at
   the close of that bar of the session's New York date (the FLAT BAR), filled at the next M1 open as every decision
   of the study (PREREG 4): on a normal day the 16:55 M1 open (M5) or 16:45 (M15). When no M1 bar opens at the flat
   bar's close (an early close: a US holiday on gold, a data hole on BTC), that open is the reopen, and a fill there
   would hold the trade over the break the flat time is there for ("because gold's daily break starts at 17:00").
   Such an exit is booked at the close of the flat bar's last M1 bar instead, at the bid for a long and the ask for a
   short, with no extra spread, read as a time exit (the harness's ``close_gap``, its reading 15); a stop or a target
   touched before that close still wins. The flag is set on every row whose own exit decision is the flat bar: every
   O2-O4 entry, every O5 order (its ``exit_bar`` and the cap of its trail), and each O1 entry whose trail has not
   fired before the flat bar (a trail firing on the flat bar's own close is the same decision). An O1 trail exit
   decided at an earlier bar keeps the next-M1-open fill, also when a hole follows that bar. The harness's flag is per
   order, so O5's exits cannot be told apart: an O5 exit decided at an earlier bar (its trail, or HV's LV fill bar) is
   also booked at that bar's last M1 close when no M1 bar opens at its close. Counted on the study's bars to
   2024-06-30: the flat bar is followed by a gap in 92 of gold's 2,181 09:30 sessions (91 close early, their flat bar
   closing 15 minutes or more before 16:55; one misses the M1 bar at the flat bar's close) and in 5 of BTC's 1,693
   (data holes); a bar from 10:00 to before the flat bar is followed by a gap in 22 / 15 gold sessions (M5 / M15; 27 /
   17 on ORB-CX) and 13 / 10 BTC sessions. In Development (2019-2022) the flag books the flat exit of 18 / 14 / 23 /
   14 / 12 trades of gold's O1-O5 x F0 rows on M5 and 28 / 16 / 24 / 16 / 21 on M15 (x1.5: the same, but O5 11 and
   20), each of them held to the reopen before; none on BTC, where no Development flat bar is followed by a gap. In
   Development no O1 trail exit on the New York rows is decided at an earlier bar followed by a gap; on gold's ORB-CX
   M5 O1 x F0 and x F2-4H rows one trade each (4 Aug 2021: the trail exits at the 10:00 bar's close, after which
   no M1 bar opens until 10:06) keeps the next M1 open, as designed. No exit of any O5 row is booked at an earlier bar's
   close (the one planned case, ORB-CX M5 O5 on 4 Aug 2021, had ended before that close). A label
   decided at or after the flat bar (only on an early close; at most one per configuration to 2024-06-30) is not a
   candidate: its fill would come after the flat time.
4. O2 / O3 LEVELS. T1 / T2 are the script's ``u1`` / ``u2`` (``d1`` / ``d2``) of its default "Multiples" (l.39-42,
   187-193); the far side is the range's other edge. Both are absolute levels re-measured from the actual fill (PREREG
   4), so R = the P/L over |fill - far side|. A zero-width range (never seen on the study's bars) gives a target at the
   edge, which every fill is beyond: dropped by the harness.
5. O4'S HIT RATES. A past session's breakout of a side is its label of that side decided by 16:00 (every such label,
   whatever the row's filter, taken or busy). Its target T_k counts as hit when a chart bar AFTER the label bar, up to
   and including the session's flat bar, reaches it (high >= u_k, low <= d_k): the trade's own horizon, from the first
   bar it can act on. Rate_k = hits / past breakouts of that side, over the sessions before the decision's; with fewer
   than 60 past breakouts, or no level at 50% or more, the target is T1. The rates are monotone (u3 reached implies u2
   and u1), so "the furthest whose rate is at least 50%" is unambiguous. The script's own dashboard (unconditional,
   l.195-214) is not used for the target; claim 8 compares the two. The port's count (``porting/orb.md`` reading 4,
   DEVIATIONS ORB-P4: a target's first touch from the 10:00 bar to the day reset, over the sessions the script
   counts) is the dashboard's, read by claim 8 alone (``hit_rate_stats``); O4 and its LV control read this one
   (``after_hits``), whose bars all lie before the day reset, so the reset (ORB-P2) moves no O4 target.
6. O5'S ORDERS AND TRAIL. Placed at the close of the range's last bar, live from the next M1 open (the first
   post-session bar's open, 10:00) until 16:00. The buy stop triggers on the ASK reaching ``orHigh`` (a bid range, a
   real stop order), the sell stop on the bid reaching ``orLow``; when both are reached in one M1 bar the side nearer
   the open fills (the harness). "Exits as O1": the trail starts at the chart bar that holds the fill, as O1's starts
   at its label bar (that bar's low - 2 x ATR, the bar's full low), and its first possible exit is that bar's next
   close. The plan's
   stop at the far side applies on top (O5 has a stop, so an R). A session of zero width, or without a bar after the
   range before 16:55, places no order. One order a day, so one trade a day.
7. HV ON O5. HV is "the breakout bar's volume above the SMA(20) of volume, the bar included". A stop order fills inside
   a bar whose volume is known only at its close, and nothing at the placement (10:00) describes it. Read: the
   breakout bar of a touch entry is the chart bar that holds the fill; at its close the trade is kept if that bar is HV
   and closed (at the next M1 open; at that bar's last M1 close when no M1 bar opens at its close, the order's
   ``close_gap``, reading 3) if it is LV. This uses the plan's definition on the plan's bar at the first moment
   it exists, at the cost of PREREG 5's "the filter does not close an open trade" for this one case. The alternative, a
   pure gate on the fill by the last closed bar's HV (``tradeiq2_filters.fill_masks``), reads another bar's volume.
   F2-4H, F2-1D and LO on O5 are checked at the placement close (the order is the decision).
8. TIGHT. "Skip ranges wider than 50% of the mean range of the last 10 weekday sessions (Session Hunter's tight-range
   idea)" is read as Session Hunter's code: its ``ranges`` holds the high-low range of each finished weekday trading
   day (its day key: the New York date of time + 4h) and keeps the last 10; ``adr`` is their mean once 5 exist; the test
   is ``rH - rL < adrPct / 100 * adr`` with adrPct 50 (strict; na adr fails). Here rH - rL is the ORB's width and adr
   is read at the range's last bar. "Wider than 50%" -> skipped at a tie, as SH l.325. The other reading, the mean
   WIDTH of the last 10 opening ranges, is not Session Hunter's computation. Counted from the data start to
   2024-06-30 (no profit or loss): 93% of gold's and 98% of BTC's 09:30 ranges pass, so TIGHT trades almost every
   session.
9. ORB-CX's O5 window. "Active 10:00-16:00" is the 09:30 range's; the COMEX range ends at 08:50 (M5) or 09:00 (M15), so
   its orders are live from that end to 16:00. Its decision window and flat time are the plan's.
10. THE UTC-5 CONTROL changes only the script's clock (l.35, 87, 225: the range, the display window and the weekday
    test on the UTC-5 date). The 16:00 cut and the 16:55 flat time are New York times (gold's break), not the script's,
    so they stay. Its day reset stays the exchange's.
11. NO R FOR O1. O1 has no stop ("No other stop"), so its trades carry no R (``risk`` is not supplied).
12. BTC's HV tag reads Binance BTCUSDT spot 5m volume on M5 and its sum over our M5 bars on M15 (PREREG 2); a bar
    without a Binance kline has volume 0.

Claims (PREREG 8; the driver's ``EXTRAS`` find ``claim6`` .. ``claim9``)
------------------------------------------------------------------------
Event geometry only (no profit or loss is computed here; claims 7 and 9 also read the driver's results rows):
6. "A break of the range often sets the direction for the day": per symbol and timeframe, over the window's complete
   sessions with a label decided by 16:00, the share whose 16:00 close (the close of the last chart bar closing at or
   before 16:00 New York) is beyond the range on the side of the first such label; "often" = more than half. Also:
   beyond the first breakout's side more often than beyond the other side.
7. "Take the breakouts that come with high volume": HV against LV, same rule (O1-O4 x M5, M15 from the results: HV makes
   more net in most pairs); for information, the 16:00 close and T1's after-breakout hit share after HV and LV labels.
8. "The hit rates count every day, not a win rate": per symbol, timeframe and level T1-T3 (both sides pooled), the
   dashboard's unconditional rate over the window's sessions (the port's ``hit_*`` flags, l.195-214) against O4's
   after-breakout rate; they "differ" when a two-proportion z-test rejects equality at 5% (|z| > 1.96). The driver adds
   O4 against O2 and O3.
9. "The UTC-5 default is an hour late in summer": the literal clock's range starts at 10:30 New York on every
   daylight-saving session and at 09:30 on every other (geometry), and O1 x F0 on New York time against the literal
   clock (results: the New York clock makes more net on both timeframes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from . import tradeiq2_filters as F
from . import tradeiq2_ind_orb as ORB
from . import tradeiq2_ind_session as SHI
from . import tradeiq2_market as M

__all__ = [
    "MODULE", "SCRIPT", "FAMILY", "TFS", "TF_MIN", "RULES", "FILTER_SETS", "LO", "LV", "NY", "CX", "UTC5", "D7",
    "TIGHT", "VERSIONS", "ENTRY_END", "FLAT_AT", "TARGET_K", "O4_MIN_DAYS", "O4_MIN_RATE", "TIGHT_FRAC", "Version",
    "Row", "vid", "variants", "plan_counts", "build", "describe", "warm", "orb_output", "sessions", "candidates",
    "trail_exits", "session_adr", "tight_sessions", "after_hits", "o4_choice", "o4_targets", "entry_allow", "o1_trades",
    "o1_entries", "target_entries", "o5_orders", "o5_on_fill", "event_table", "breakout_days", "direction_stats",
    "hit_rate_stats", "clock_stats", "claim6", "claim7", "claim8", "claim9",
]

MODULE = "tradeiq2_rules_orb"           # the Context cache's module key
SCRIPT = "ORB"
FAMILY = "ORB"                          # PREREG 7: "ORB, including ORB-CX and TIGHT"
TFS = ("M5", "M15")                     # PREREG 6.5
TF_MIN = {"M5": 5, "M15": 15}
RULES = ("O1", "O2", "O3", "O4", "O5")
FILTER_SETS = ("F0", "HV", "F2-4H", "F2-1D", "HV+F2-4H")   # PREREG 6.5's five filter sets
LO, LV = "LO", "LV"                     # long only (gold); the LV-only control (claim 7)
ENTRY_FILTERS = FILTER_SETS + (LO, LV)
NY, CX, UTC5, D7 = "NY", "ORB-CX", "UTC-5", "7D"           # the plan's version, gold's COMEX range, two controls
TIGHT = "TIGHT"
ENTRY_END = 16 * 60                     # 16:00 New York: the last decision close
FLAT_AT = 16 * 60 + 55                  # 16:55 New York: flat at the last chart-bar close at or before it
TARGET_K = {"O2": 1, "O3": 2}           # T1, T2 (O4 chooses per entry)
O4_MIN_DAYS = 60                        # PREREG 6.5: "Past days only, with at least 60 of them" (reading 5: 60
                                        # past sessions with a label of the side decided by 16:00 New York)
O4_MIN_RATE = 0.5                       # "... whose hit rate ... is at least 50%"
TIGHT_FRAC = SHI.ADR_PCT / 100.0        # Session Hunter's adrPct 50 (SH l.66, 325), as it computes it
TRAIL_MULT = ORB.TRAIL_MULT             # 2.0 (l.61)
Z_CRIT = 1.96                           # claim 8: a two-sided two-proportion z-test at 5%

INFO_LV = "control (claim 7): LV breakouts only; not eligible"
INFO_UTC5 = "control (claim 9): the script's literal UTC-5 clock; not eligible"
INFO_7D = "control: BTC on all 7 days; not eligible"


@dataclass(frozen=True)
class Version:
    """One configuration of the port: the session (minutes of its clock), the clock and the session days."""
    name: str
    sess: Tuple[int, int]
    clock: str
    days: str
    words: str


VERSIONS: Dict[str, Version] = {
    NY: Version(NY, ORB.SESSION, "ny", "weekdays",
                "the 09:30-10:00 New York range (daylight saving included) on New York weekdays"),
    CX: Version(CX, ORB.COMEX_SESSION, "ny", "weekdays",
                "the COMEX-open range 08:20-08:50 New York (ORB-CX; on M15 the bars opening 08:30 and 08:45) on "
                "New York weekdays"),
    UTC5: Version(UTC5, ORB.SESSION, "utc-5", "weekdays",
                  "the 09:30-10:00 range on the script's literal fixed UTC-5 clock (10:30-11:00 New York from March "
                  "to November) on its weekdays"),
    D7: Version(D7, ORB.SESSION, "ny", "all",
                "the 09:30-10:00 New York range on every day of the week (BTC on all 7 days)"),
}


@dataclass(frozen=True)
class Row:
    """One planned row of PREREG 6.5: its rule, its filter set, its version and whether only tight ranges trade."""
    rule: str
    filt: str
    version: str = NY
    tight: bool = False
    eligible: bool = True
    info: str = ""


def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _hhmm(m: int) -> str:
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def _check_tf(tf: str) -> None:
    if tf not in TFS:
        raise ValueError(f"{tf}: the ORB's rules run on {', '.join(TFS)} (PREREG 6.5)")


def _version(version: str) -> Version:
    if version not in VERSIONS:
        raise ValueError(f"{version}: one of {', '.join(VERSIONS)}")
    return VERSIONS[version]


# ───────────────────────────── the grid (PREREG 6.5) ─────────────────────────────

def _rows(symbol: str) -> List[Tuple[str, Row]]:
    """(timeframe, row) for every planned row of ``symbol``, in the grid's order."""
    gold = symbol == M.GOLD
    out: List[Tuple[str, Row]] = []
    for tf in TFS:                                                   # 2 x 5 x 5 = 50
        for rule in RULES:
            for f in FILTER_SETS:
                out.append((tf, Row(rule, f)))
    if gold:
        for tf in TFS:                                               # LO (gold only): 10
            for rule in RULES:
                out.append((tf, Row(rule, LO)))
        for tf in TFS:                                               # ORB-CX (gold only): 8
            for rule in ("O1", "O5"):
                for f in ("F0", "F2-4H"):
                    out.append((tf, Row(rule, f, CX)))
    for tf in TFS:                                                   # TIGHT: 4
        for rule in ("O1", "O5"):
            out.append((tf, Row(rule, "F0", tight=True)))
    for tf in TFS:                                                   # controls: LV only (O1-O4): 8
        for rule in ("O1", "O2", "O3", "O4"):
            out.append((tf, Row(rule, LV, eligible=False, info=INFO_LV)))
    for tf in TFS:                                                   # the literal UTC-5 clock (O1): 2
        out.append((tf, Row("O1", "F0", UTC5, eligible=False, info=INFO_UTC5)))
    if symbol == M.BTC:
        for tf in TFS:                                               # BTC on all 7 days (O1): 2
            out.append((tf, Row("O1", "F0", D7, eligible=False, info=INFO_7D)))
    return out


def vid(symbol: str, tf: str, row: Row) -> str:
    """The row's id: ``symbol|tf|ORB|rule|filter`` plus ``|ORB-CX`` / ``|UTC-5`` / ``|7D`` and ``|TIGHT``."""
    rest = [row.rule, row.filt]
    if row.version != NY:
        rest.append(row.version)
    if row.tight:
        rest.append(TIGHT)
    return "|".join([symbol, tf, SCRIPT] + rest)


def _params(tf: str, row: Row) -> Dict[str, object]:
    ver = VERSIONS[row.version]
    return {"rule": row.rule, "filter": row.filt, "version": row.version, "range": "tight" if row.tight else "every",
            "session": f"{_hhmm(ver.sess[0])}-{_hhmm(ver.sess[1])}", "clock": ver.clock, "days": ver.days,
            "entry": "stop orders (one cancels the other)" if row.rule == "O5" else "market at the label",
            "stop": "none" if row.rule == "O1" else "far side",
            "target": {"O1": "none", "O2": "T1", "O3": "T2", "O4": "hit rate", "O5": "none"}[row.rule],
            "exit": "trail" if row.rule in ("O1", "O5") else "target or stop",
            "entry_until": _hhmm(ENTRY_END), "flat_at": _hhmm(FLAT_AT)}


_PLAN: Dict[str, Dict[str, Tuple[str, Row]]] = {}


def _plan(symbol: str) -> Dict[str, Tuple[str, Row]]:
    if symbol not in _PLAN:
        _PLAN[symbol] = {vid(symbol, tf, r): (tf, r) for tf, r in _rows(symbol)}
    return _PLAN[symbol]


def variants(symbol: str) -> List[M.Variant]:
    """EXACTLY the rows of PREREG 6.5 for ``symbol`` (the module docstring's grid): 82 on XAUUSDm (72 eligible), 66 on
    BTCUSDm (54 eligible), none on the claim markets. Raises for a symbol that is not the study's."""
    if symbol not in M.ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(M.ALL_SYMBOLS)})")
    if symbol not in M.SYMBOLS:
        return []
    return [M.Variant(vid(symbol, tf, r), symbol, tf, SCRIPT, FAMILY, r.eligible, r.info, _params(tf, r))
            for tf, r in _rows(symbol)]


def plan_counts(symbol: str) -> Dict[Tuple[str, bool], int]:
    """The rows ``variants(symbol)`` gives per (family, eligible), for the grid check."""
    out: Dict[Tuple[str, bool], int] = {}
    for v in variants(symbol):
        out[(v.family, bool(v.eligible))] = out.get((v.family, bool(v.eligible)), 0) + 1
    return out


def _row_of(variant: M.Variant) -> Tuple[str, Row]:
    """The planned (timeframe, row) of a variant; ValueError for anything the plan does not have."""
    plan = _plan(variant.symbol) if variant.symbol in M.SYMBOLS else {}
    if variant.id not in plan:
        raise ValueError(f"{variant.id}: not a row of PREREG 6.5 (tradeiq2_rules_orb.variants)")
    tf, row = plan[variant.id]
    if variant.tf != tf or variant.family != FAMILY or variant.script != SCRIPT:
        raise ValueError(f"{variant.id}: its timeframe / family / script ({variant.tf}, {variant.family}, "
                         f"{variant.script}) are not the plan's ({tf}, {FAMILY}, {SCRIPT})")
    return tf, row


# ───────────────────────────── the indicator arrays (cached in the Context) ─────────────────────────────

def orb_output(ctx: M.Context, tf: str, version: str = NY) -> Dict[str, object]:
    """
    The reconciled port on ``ctx.bars(tf)`` for one version (``VERSIONS``): ``tradeiq2_ind_orb.orb`` with the bid OHLC,
    the volume of PREREG 2 (``ctx.volume``), the version's session, clock and days, the script's defaults otherwise
    and the exchange's day reset ('auto' for the symbol). Per-bar keys read-only, plus the ``days`` frame. Cached.
    """
    _check_tf(tf)
    ver = _version(version)

    def make():
        b = ctx.bars(tf)
        v = np.asarray(ctx.volume(tf), np.float64)
        out = ORB.orb(b.t, b.o, b.h, b.l, b.c, v, TF_MIN[tf], sess=ver.sess, clock=ver.clock, days=ver.days,
                      symbol=ctx.symbol)
        for k in ORB.BAR_KEYS:
            out[k] = _ro(out[k])
        return out
    return ctx.get(MODULE, tf, {"series": "orb", "version": version}, make)


def sessions(ctx: M.Context, tf: str, version: str = NY) -> Dict[str, np.ndarray]:
    """
    One entry per session the script counts (the port's ``days`` rows, in time order), read-only, cached: the port's
    bars and levels (``start_bar``, ``end_bar``, ``post_bar``, ``span_end``, ``or_high``, ``or_low``, ``width``,
    ``u1``-``u3``, ``d1``-``d3``, ``label_up_bar``, ``label_dn_bar``), ``valid`` (finite levels: a session a reset
    wiped has none), ``day`` (the New York date of the range's first bar, an epoch day), ``t0`` (that bar's open,
    UTC s), ``entry_end_s`` / ``flat_cut_s`` (16:00 / 16:55 New York of that date, UTC s), ``flat_bar`` (the last
    bar closing at or before ``flat_cut_s``; -1 while the data end lies before it) and ``bar16`` (the last bar closing
    at or before 16:00; -1 likewise).
    """
    _check_tf(tf)
    _version(version)

    def make():
        b = ctx.bars(tf)
        d = orb_output(ctx, tf, version)["days"]
        start = d["start_bar"].to_numpy(np.int64)
        day = np.asarray(M.ny_date(b.t[start]), np.int64) if len(start) else np.zeros(0, np.int64)
        entry_end = np.asarray(M.utc_of_ny(day, ENTRY_END), np.int64) if len(day) else np.zeros(0, np.int64)
        flat_cut = np.asarray(M.utc_of_ny(day, FLAT_AT), np.int64) if len(day) else np.zeros(0, np.int64)
        if np.any(entry_end < 0) or np.any(flat_cut < 0):
            raise AssertionError("16:00 / 16:55 New York does not exist on a session's date")
        end_s = int(ctx.mk.end_s)
        flat = np.where(flat_cut <= end_s, np.searchsorted(b.tc, flat_cut, side="right") - 1, -1).astype(np.int64)
        bar16 = np.where(entry_end <= end_s, np.searchsorted(b.tc, entry_end, side="right") - 1, -1).astype(np.int64)
        out = {"day": day, "t0": b.t[start].astype(np.int64), "entry_end_s": entry_end, "flat_cut_s": flat_cut,
               "flat_bar": flat, "bar16": bar16}
        for k in ("start_bar", "end_bar", "post_bar", "span_end", "label_up_bar", "label_dn_bar"):
            out[k] = d[k].to_numpy(np.int64)
        for k in ("or_high", "or_low", "width", "u1", "u2", "u3", "d1", "d2", "d3"):
            out[k] = d[k].to_numpy(np.float64)
        out["valid"] = np.isfinite(out["or_high"]) & np.isfinite(out["or_low"])
        return {k: _ro(np.asarray(v)) for k, v in out.items()}
    return ctx.get(MODULE, tf, {"series": "sessions", "version": version}, make)


def candidates(ctx: M.Context, tf: str, version: str = NY) -> Dict[str, np.ndarray]:
    """
    The labels of every session (the market rules' candidates), in time order, read-only, cached: ``bar``, ``side``
    (+1 up, -1 down), ``session`` (index into ``sessions``), ``day``; ``decided`` (the bar closes at or before 16:00
    New York of the session's date), ``room`` (the bar is before the session's flat bar, or that is unknown yet),
    ``ok`` = both (reading 3).
    """
    def make():
        S = sessions(ctx, tf, version)
        b = ctx.bars(tf)
        js = np.arange(len(S["day"]), dtype=np.int64)
        up, dn = S["label_up_bar"], S["label_dn_bar"]
        bar = np.concatenate([up[up >= 0], dn[dn >= 0]]).astype(np.int64)
        side = np.concatenate([np.ones(int((up >= 0).sum()), np.int64), -np.ones(int((dn >= 0).sum()), np.int64)])
        j = np.concatenate([js[up >= 0], js[dn >= 0]]).astype(np.int64)
        o = np.argsort(bar, kind="stable")
        bar, side, j = bar[o], side[o], j[o]
        if len(bar) > 1 and not np.all(np.diff(bar) > 0):
            raise AssertionError("two labels on one bar")
        decided = b.tc[bar] <= S["entry_end_s"][j]
        flat = S["flat_bar"][j]
        room = (flat < 0) | (bar < flat)
        out = {"bar": bar, "side": side, "session": j, "day": S["day"][j], "decided": decided, "room": room,
               "ok": decided & room}
        return {k: _ro(np.asarray(v)) for k, v in out.items()}
    return ctx.get(MODULE, tf, {"series": "candidates", "version": version}, make)


@njit(cache=True)
def _trail_kernel(h, l, c, atr, mult, lo, hi, cap):
    """For each session j and each bar e in [lo[j], hi[j]]: the exit decision bar of a long (``xl``) and of a short
    (``xs``) whose trail starts at bar e (l.258 / 269, 274-286: ``max(nz(trail[1], x), x)`` with x = low - atr * mult,
    exit when close < trail; mirrored), searched up to ``cap[j]`` (the flat bar; -1: the data end) and capped there
    (-1 when nothing is known)."""
    n = c.shape[0]
    xl = np.full(n, -1, np.int64)
    xs = np.full(n, -1, np.int64)
    for j in range(lo.shape[0]):
        end = cap[j] if cap[j] >= 0 else n - 1
        for e in range(lo[j], hi[j] + 1):
            tr = np.nan
            x = -1
            for k in range(e, end + 1):
                v = l[k] - (atr[k] * mult)
                a = tr if tr == tr else v
                if a != a or v != v:
                    tr = np.nan
                else:
                    tr = a if a > v else v
                if c[k] < tr:
                    x = k
                    break
            xl[e] = x if x >= 0 else cap[j]
            tr = np.nan
            x = -1
            for k in range(e, end + 1):
                v = h[k] + (atr[k] * mult)
                a = tr if tr == tr else v
                if a != a or v != v:
                    tr = np.nan
                else:
                    tr = a if a < v else v
                if c[k] > tr:
                    x = k
                    break
            xs[e] = x if x >= 0 else cap[j]
    return xl, xs


def trail_exits(ctx: M.Context, tf: str, version: str = NY) -> Tuple[np.ndarray, np.ndarray]:
    """
    Per bar e of ``ctx.bars(tf)`` (read-only, cached): the exit decision bar of a long (``xl[e]``) and of a short
    (``xs[e]``) whose trail starts at e, for every e from a valid session's first post-session bar to its flat bar:
    the first bar k >= e whose close is beyond the trail (the script's, with the port's ATR(14) and mult 2), else
    the flat bar (-1 while that is unknown, and outside every session's window). On the start bar itself the close
    cannot be beyond its own low - 2 ATR, so a market entry's exit is always a later bar.
    """
    def make():
        b = ctx.bars(tf)
        S = sessions(ctx, tf, version)
        atr = np.asarray(orb_output(ctx, tf, version)["atr"], np.float64)
        n = len(b)
        flat = S["flat_bar"]
        sel = S["valid"] & ((flat < 0) | (flat >= S["post_bar"])) & (S["post_bar"] < n)
        lo = S["post_bar"][sel]
        hi = np.where(flat[sel] >= 0, flat[sel], n - 1).astype(np.int64)
        xl, xs = _trail_kernel(np.ascontiguousarray(b.h, np.float64), np.ascontiguousarray(b.l, np.float64),
                               np.ascontiguousarray(b.c, np.float64), np.ascontiguousarray(atr), float(TRAIL_MULT),
                               np.ascontiguousarray(lo, np.int64), np.ascontiguousarray(hi, np.int64),
                               np.ascontiguousarray(flat[sel], np.int64))
        return _ro(xl), _ro(xs)
    return ctx.get(MODULE, tf, {"series": "trail_exits", "version": version}, make)


def session_adr(ctx: M.Context, tf: str) -> np.ndarray:
    """Session Hunter's ``adr`` per bar of ``ctx.bars(tf)`` (``tradeiq2_ind_session.day_state``: the mean high-low of
    the last up to 10 finished weekday trading days of its clock, na until 5 exist; SH l.191-194, 211), cached."""
    _check_tf(tf)

    def make():
        b = ctx.bars(tf)
        return _ro(SHI.day_state(b.t, b.o, b.h, b.l, b.c, TF_MIN[tf])["adr"].to_numpy(np.float64))
    return ctx.get(MODULE, tf, {"series": "sh_adr"}, make)


def tight_sessions(ctx: M.Context, tf: str, version: str = NY) -> np.ndarray:
    """TIGHT per session (reading 8): valid, Session Hunter's adr at the range's last bar exists, and the width is
    below ``TIGHT_FRAC`` x adr (SH l.325, strict). Read-only, cached."""
    def make():
        S = sessions(ctx, tf, version)
        adr = session_adr(ctx, tf)[S["end_bar"]] if len(S["end_bar"]) else np.zeros(0)
        with np.errstate(invalid="ignore"):
            ok = S["valid"] & np.isfinite(adr) & (S["width"] < TIGHT_FRAC * adr)
        return _ro(ok)
    return ctx.get(MODULE, tf, {"series": "tight", "version": version}, make)


def after_hits(ctx: M.Context, tf: str, version: str = NY) -> Dict[str, np.ndarray]:
    """
    Per session (read-only, cached): ``complete`` (its flat bar is known), ``has_up`` / ``has_dn`` (it is complete and
    has a label of that side decided by 16:00), and ``hit_up`` / ``hit_dn`` (sessions x 3, bool): whether a chart bar
    after the label bar, up to and including the flat bar, reached u1-u3 (high >= u_k) / d1-d3 (low <= d_k) (reading 5).
    """
    def make():
        S = sessions(ctx, tf, version)
        b = ctx.bars(tf)
        nS = len(S["day"])
        flat = S["flat_bar"]
        complete = flat >= 0
        out = {"complete": complete}
        for side, key, levels in ((1, "up", ("u1", "u2", "u3")), (-1, "dn", ("d1", "d2", "d3"))):
            lab = S[f"label_{key}_bar"]
            dec = (lab >= 0) & (b.tc[np.maximum(lab, 0)] <= S["entry_end_s"])
            has = dec & complete
            hit = np.zeros((nS, 3), np.bool_)
            lv = np.stack([S[k] for k in levels], axis=1) if nS else np.zeros((0, 3))
            for j in np.flatnonzero(has):
                L, Fb = int(lab[j]), int(flat[j])
                if L >= Fb:
                    continue
                if side == 1:
                    hit[j] = float(b.h[L + 1:Fb + 1].max()) >= lv[j]
                else:
                    hit[j] = float(b.l[L + 1:Fb + 1].min()) <= lv[j]
            out[f"has_{key}"] = has
            out[f"hit_{key}"] = hit
        return {k: _ro(v) for k, v in out.items()}
    return ctx.get(MODULE, tf, {"series": "after_hits", "version": version}, make)


def o4_choice(has, hit, min_days: int = O4_MIN_DAYS, min_rate: float = O4_MIN_RATE
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    O4's target per session from the sessions BEFORE it (reading 5): ``has`` (sessions,) the session has a breakout of
    the side, ``hit`` (sessions, 3) its T1-T3 were reached after it. Returns (k, n, rate): k in 1..3 = the furthest
    level whose past rate is at least ``min_rate`` when at least ``min_days`` past breakouts exist, else 1; n = the
    past breakouts; rate (sessions, 3) = past hits / n (NaN when n = 0).
    """
    has = np.asarray(has, bool)
    hit = np.asarray(hit, bool) & has[:, None]
    n = (np.cumsum(has) - has).astype(np.int64)
    hits = np.cumsum(hit, axis=0) - hit
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(n[:, None] > 0, hits / np.maximum(n, 1)[:, None], np.nan)
        ok = (n[:, None] >= min_days) & (rate >= min_rate)
    k = np.where(ok.any(axis=1), 3 - np.argmax(ok[:, ::-1], axis=1), 1).astype(np.int64)
    return k, n, rate


def o4_targets(ctx: M.Context, tf: str, version: str = NY) -> Dict[str, np.ndarray]:
    """Per session (read-only, cached): O4's level for a long (``k_up``) and a short (``k_dn``), the past breakouts
    (``n_up``, ``n_dn``) and the past rates (``rate_up``, ``rate_dn``, sessions x 3), from ``after_hits``."""
    def make():
        H = after_hits(ctx, tf, version)
        ku, nu, ru = o4_choice(H["has_up"], H["hit_up"])
        kd, nd, rd = o4_choice(H["has_dn"], H["hit_dn"])
        return {k: _ro(v) for k, v in (("k_up", ku), ("n_up", nu), ("rate_up", ru), ("k_dn", kd), ("n_dn", nd),
                                       ("rate_dn", rd))}
    return ctx.get(MODULE, tf, {"series": "o4", "version": version}, make)


# ───────────────────────────── filters ─────────────────────────────

def entry_allow(ctx: M.Context, tf: str, filt: str, version: str = NY) -> Tuple[np.ndarray, np.ndarray]:
    """(allow_long, allow_short) per bar for a market rule's label at its close (PREREG 5 / 6.5): F0 both; HV / LV the
    port's ``hv`` / its complement for both sides; F2-4H, F2-1D, LO ``ctx.allow``; HV+F2-4H the AND."""
    if filt not in ENTRY_FILTERS:
        raise ValueError(f"{filt}: one of {', '.join(ENTRY_FILTERS)}")
    n = len(ctx.bars(tf))
    if filt == "F0":
        return np.ones(n, bool), np.ones(n, bool)
    if filt in ("HV", "LV"):
        hv = np.asarray(orb_output(ctx, tf, version)["hv"], bool)
        m = hv if filt == "HV" else ~hv
        return m, m
    if filt in ("F2-4H", "F2-1D", LO):
        al, ash = ctx.allow(tf, filt)
        return np.asarray(al, bool), np.asarray(ash, bool)
    hv = np.asarray(orb_output(ctx, tf, version)["hv"], bool)
    al, ash = ctx.allow(tf, "F2-4H")
    return hv & np.asarray(al, bool), hv & np.asarray(ash, bool)


def _o5_filters(filt: str) -> Tuple[Optional[str], bool]:
    """O5: (the filter checked at the placement close or None, whether the fill bar's HV is checked; reading 7)."""
    if filt not in FILTER_SETS + (LO,):
        raise ValueError(f"{filt}: not a filter set of O5 (PREREG 6.5)")
    return {"F0": (None, False), "HV": (None, True), "F2-4H": ("F2-4H", False), "F2-1D": ("F2-1D", False),
            "HV+F2-4H": ("F2-4H", True), LO: (LO, False)}[filt]


# ───────────────────────────── the rules ─────────────────────────────

def o1_trades(ctx: M.Context, tf: str, row: Row) -> Dict[str, np.ndarray]:
    """
    O1's trades (and the labels it could not take), in the script's order (reading 2): the candidates that are ``ok``
    (decided by 16:00, before the flat bar), in a tight session for TIGHT, and allowed by the row's filter at their
    close; each opens a trade only when no trade is open AT ITS BAR (a trade whose trail exits at the close of bar x is
    still open on bar x); the trade's exit is ``trail_exits`` of its label bar and side. Returns ``index`` (into
    ``candidates``), ``bar``, ``side``, ``exit_bar``, ``session``, ``day`` of the trades, ``flat_exit`` (True where the
    exit is the session's flat bar: the trail has not fired before it, or fires on that bar's own close; reading 3)
    and ``busy`` (the candidates refused because a trade was open).
    """
    C = candidates(ctx, tf, row.version)
    keep = np.asarray(C["ok"], bool).copy()
    if row.tight:
        keep &= tight_sessions(ctx, tf, row.version)[C["session"]] if len(keep) else keep
    al, ash = entry_allow(ctx, tf, row.filt, row.version)
    allowed = np.where(C["side"] == 1, al[C["bar"]], ash[C["bar"]]) if len(keep) else keep
    xl, xs = trail_exits(ctx, tf, row.version)
    take, xb, busy = [], [], []
    open_until = -1
    for i in np.flatnonzero(keep & allowed):
        b = int(C["bar"][i])
        if b <= open_until:
            busy.append(int(i))
            continue
        x = int(xl[b] if C["side"][i] == 1 else xs[b])
        if 0 <= x <= b:
            raise AssertionError(f"O1: a trail exit at or before its entry bar {b}")
        take.append(int(i))
        xb.append(x)
        open_until = x if x >= 0 else np.iinfo(np.int64).max
    idx = np.asarray(take, np.int64)
    xb = np.asarray(xb, np.int64)
    flat = sessions(ctx, tf, row.version)["flat_bar"][C["session"][idx]]
    return {"index": idx, "bar": C["bar"][idx], "side": C["side"][idx], "exit_bar": xb,
            "session": C["session"][idx], "day": C["day"][idx], "flat_exit": (xb >= 0) & (xb == flat),
            "busy": np.asarray(busy, np.int64)}


def o1_entries(ctx: M.Context, tf: str, row: Row) -> M.Entries:
    """O1 as market entries for the harness: each trade of ``o1_trades`` at its label bar, no stop, no target, its
    exit decision at ``exit_bar`` (the trail's close or the flat bar), tag = the session's New York date.
    ``close_gap`` where that exit is the session's flat bar (``flat_exit``): booked at the flat bar's last M1 close
    when no M1 bar opens at its close; a trail exit decided at an earlier bar fills at the next M1 open (reading 3)."""
    T = o1_trades(ctx, tf, row)
    return M.entries(T["bar"], T["side"], exit_bar=T["exit_bar"], tag=T["day"], close_gap=T["flat_exit"])


def target_entries(ctx: M.Context, tf: str, row: Row) -> M.Entries:
    """
    O2 / O3 / O4 as market entries: every ``ok`` candidate the row's filter allows at its close; stop level = the far
    side of the range, target level = T_k (k = 1 for O2, 2 for O3, ``o4_targets`` for O4), both absolute (the harness
    measures them from the actual fill and drops an entry beyond either, PREREG 4); exit decision at the flat bar,
    ``close_gap`` on every row (that exit is booked at the flat bar's last M1 close when no M1 bar opens at its close;
    reading 3); tag = the session's New York date. One position at a time is the harness's (a candidate while a trade
    is open is busy).
    """
    if row.rule not in ("O2", "O3", "O4"):
        raise ValueError(f"{row.rule}: target_entries is for O2, O3 and O4")
    C = candidates(ctx, tf, row.version)
    S = sessions(ctx, tf, row.version)
    al, ash = entry_allow(ctx, tf, row.filt, row.version)
    ok = np.asarray(C["ok"], bool)
    allowed = np.where(C["side"] == 1, al[C["bar"]], ash[C["bar"]]) if len(ok) else ok
    if row.tight:
        ok = ok & tight_sessions(ctx, tf, row.version)[C["session"]]
    sel = np.flatnonzero(ok & allowed)
    j, side, bar = C["session"][sel], C["side"][sel], C["bar"][sel]
    if row.rule == "O4":
        T4 = o4_targets(ctx, tf, row.version)
        k = np.where(side == 1, T4["k_up"][j], T4["k_dn"][j])
    else:
        k = np.full(len(sel), TARGET_K[row.rule], np.int64)
    up = np.stack([S["u1"], S["u2"], S["u3"]], axis=1)
    dn = np.stack([S["d1"], S["d2"], S["d3"]], axis=1)
    target = np.where(side == 1, up[j, k - 1], dn[j, k - 1]) if len(sel) else np.zeros(0)
    stop = np.where(side == 1, S["or_low"][j], S["or_high"][j])
    return M.entries(bar, side, stop_level=stop, target_level=target, exit_bar=S["flat_bar"][j], tag=S["day"][j],
                     close_gap=True)


def o5_orders(ctx: M.Context, tf: str, row: Row) -> M.Orders:
    """
    O5's stop orders (reading 6): per valid session of positive width with a bar after the range before its flat bar
    (and tight for TIGHT), placed at the close of the range's last bar: buy stop ``or_high`` with its stop ``or_low``,
    sell stop ``or_low`` with its stop ``or_high``, one cancels the other, until 16:00 New York of the session's date;
    exit decision at the flat bar (``on_fill``'s trail may decide earlier), ``close_gap`` on every order (reading 3:
    the flag is the order's, so the harness applies it to whichever of the flat bar and ``on_fill``'s bar decides the
    exit); tag = the session's date. F2-4H / F2-1D / LO remove the sides they refuse at the placement close
    (``tradeiq2_filters.gate_orders``, which keeps the flag).
    """
    if row.rule != "O5":
        raise ValueError(f"{row.rule}: o5_orders is for O5")
    S = sessions(ctx, tf, row.version)
    flat = S["flat_bar"]
    sel = S["valid"] & (S["width"] > 0) & ((flat < 0) | (flat > S["end_bar"]))
    if row.tight:
        sel = sel & tight_sessions(ctx, tf, row.version)
    j = np.flatnonzero(sel)
    O = M.orders(S["end_bar"][j], S["entry_end_s"][j], buy=S["or_high"][j], sell=S["or_low"][j],
                 buy_stop=S["or_low"][j], sell_stop=S["or_high"][j], exit_bar=flat[j], tag=S["day"][j],
                 close_gap=True)
    gate, _ = _o5_filters(row.filt)
    if gate is not None:
        al, ash = ctx.allow(tf, gate)
        O = F.gate_orders(O, al, ash)
    return O


def o5_on_fill(ctx: M.Context, tf: str, row: Row) -> Callable[[int, int], int]:
    """O5's ``on_fill(fill_bar, side) -> exit_bar``: the trail started at the fill's bar (``trail_exits``; capped at
    the flat bar); for HV / HV+F2-4H the fill's bar itself when that bar is not HV (reading 7)."""
    _, need_hv = _o5_filters(row.filt)
    xl, xs = trail_exits(ctx, tf, row.version)
    hv = np.asarray(orb_output(ctx, tf, row.version)["hv"], bool)

    def on_fill(fill_bar: int, side: int) -> int:
        bf = int(fill_bar)
        if need_hv and not hv[bf]:
            return bf
        return int(xl[bf] if side == 1 else xs[bf])
    return on_fill


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The harness's Exec of a planned row (see the module docstring): EVENTS with market entries (O1-O4) or stop
    orders with ``on_fill`` (O5), labelled with the variant's id."""
    tf, row = _row_of(variant)
    if variant.symbol != ctx.symbol:
        raise ValueError(f"{variant.id}: a row of {variant.symbol}, the context is {ctx.symbol}'s")
    if row.rule == "O1":
        return M.event_exec(tf, entries=o1_entries(ctx, tf, row), label=variant.id)
    if row.rule == "O5":
        return M.event_exec(tf, orders=o5_orders(ctx, tf, row), on_fill=o5_on_fill(ctx, tf, row), label=variant.id)
    return M.event_exec(tf, entries=target_entries(ctx, tf, row), label=variant.id)


def warm(ctx: M.Context, variants_: Sequence[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, every array the given rows read: the port per
    timeframe and version, the sessions, the candidates, the trail exits, O4's targets, TIGHT's adr and the filters."""
    need = set()
    for v in variants_:
        if v.symbol != ctx.symbol:
            continue
        need.add(_row_of(v))
    for tf, row in sorted(need, key=lambda x: (x[0], x[1].version, x[1].rule, x[1].filt, x[1].tight)):
        candidates(ctx, tf, row.version)
        trail_exits(ctx, tf, row.version)
        if row.rule == "O4":
            o4_targets(ctx, tf, row.version)
        if row.tight:
            tight_sessions(ctx, tf, row.version)
        gate = {"F2-4H": "F2-4H", "F2-1D": "F2-1D", LO: LO, "HV+F2-4H": "F2-4H"}.get(row.filt)
        if gate is not None:
            ctx.allow(tf, gate)


# ───────────────────────────── a row in words, and its event geometry ─────────────────────────────

RULE_WORDS = {
    "O1": ("the script's own trade: a market entry at the first labelled breakout of a side (the close crossing the "
           "range from 10:00 on), out at the first close beyond its trail (the highest low - 2 ATR(14) since the "
           "label for a long, the lowest high + 2 ATR(14) for a short) or at the flat time; no other stop"),
    "O2": "a market entry at a labelled breakout; target T1 = the range edge + 1 range width, stop at the far side",
    "O3": "a market entry at a labelled breakout; target T2 = the range edge + 2 range widths, stop at the far side",
    "O4": ("a market entry at a labelled breakout; target the furthest of T1-T3 whose hit rate after past breakouts "
           "of that side is at least 50% (once at least 60 past sessions have a breakout of that side decided by "
           "16:00 New York, else T1), stop at the far side"),
    "O5": ("stop orders at both range edges, one cancels the other, active from the range's end to 16:00; stop at the "
           "far side; out on the trail started at the bar of the fill or at the flat time"),
}
FILTER_WORDS = {
    "F0": "no filter",
    "HV": ("only breakouts whose bar's volume is above its SMA(20) (that bar included; for O5 the bar of the fill, "
           "checked at its close, an LV fill bar ends the trade there)"),
    "LV": "only breakouts whose bar's volume is not above its SMA(20) (the claim-7 control)",
    "F2-4H": "the last closed 4H bar's close on the trade's side of its MA200",
    "F2-1D": "the last closed 1D bar's close on the trade's side of its MA200",
    "HV+F2-4H": "HV and F2-4H together",
    LO: "long only",
}


def describe(variant: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    tf, row = _row_of(variant)
    ver = VERSIONS[row.version]
    vol = "Binance BTCUSDT spot volume" if variant.symbol.startswith("BTC") else "tick volume"
    tight = (" Only sessions whose range is narrower than 50% of Session Hunter's 10-day average daily range "
             "(TIGHT)." if row.tight else "")
    note = f" {variant.info}." if variant.info else ""
    return (f"LuxAlgo's Ultimate Opening Range Breakout on {tf} bars of the bid: {ver.words}; {RULE_WORDS[row.rule]}. "
            f"Filter: {FILTER_WORDS[row.filt]} (volume: {vol}). Entries decided by 16:00 New York, everything flat at "
            f"the last bar close at or before 16:55 New York, one position at a time.{tight}{note}")


def event_table(ctx: M.Context, variant: M.Variant) -> pd.DataFrame:
    """Event geometry of a row (no profit or loss): O1-O4 per candidate (its bar, close time, side, session date,
    decided / room / allowed, taken by O1's order or not, the stop and target levels, the flat bar, ``close_gap``:
    the row's exit is the flat bar, booked before a gap that follows it; reading 3); O5 per order (its placement bar,
    expiry, levels, flat bar, ``close_gap``)."""
    tf, row = _row_of(variant)
    b = ctx.bars(tf)
    S = sessions(ctx, tf, row.version)
    if row.rule == "O5":
        O = o5_orders(ctx, tf, row)
        return pd.DataFrame({"bar": O.bar, "placed": pd.to_datetime(b.tc[O.bar], unit="s", utc=True),
                             "until": pd.to_datetime(O.until, unit="s", utc=True), "buy": O.buy, "sell": O.sell,
                             "buy_stop": O.buy_stop, "sell_stop": O.sell_stop, "exit_bar": O.exit_bar, "tag": O.tag,
                             "close_gap": O.close_gap})
    C = candidates(ctx, tf, row.version)
    al, ash = entry_allow(ctx, tf, row.filt, row.version)
    allowed = np.where(C["side"] == 1, al[C["bar"]], ash[C["bar"]])
    j = C["session"]
    df = pd.DataFrame({"bar": C["bar"], "close": pd.to_datetime(b.tc[C["bar"]], unit="s", utc=True),
                       "side": C["side"], "day": C["day"], "decided": C["decided"], "room": C["room"],
                       "allowed": allowed, "or_high": S["or_high"][j], "or_low": S["or_low"][j],
                       "flat_bar": S["flat_bar"][j]})
    if row.tight:
        df["tight"] = tight_sessions(ctx, tf, row.version)[j]
    if row.rule == "O1":
        T = o1_trades(ctx, tf, row)
        taken = np.zeros(len(df), bool)
        taken[T["index"]] = True
        busy = np.zeros(len(df), bool)
        busy[T["busy"]] = True
        df["taken"], df["busy"] = taken, busy
        ex = np.full(len(df), -1, np.int64)
        ex[T["index"]] = T["exit_bar"]
        df["exit_bar"] = ex
        gap = np.zeros(len(df), bool)
        gap[T["index"]] = T["flat_exit"]
        df["close_gap"] = gap
    else:
        if row.rule == "O4":
            T4 = o4_targets(ctx, tf, row.version)
            k = np.where(C["side"] == 1, T4["k_up"][j], T4["k_dn"][j])
        else:
            k = np.full(len(df), TARGET_K[row.rule], np.int64)
        up = np.stack([S["u1"], S["u2"], S["u3"]], axis=1)
        dn = np.stack([S["d1"], S["d2"], S["d3"]], axis=1)
        df["target_k"] = k
        df["target"] = np.where(C["side"] == 1, up[j, k - 1], dn[j, k - 1]) if len(df) else np.zeros(0)
        df["stop"] = np.where(C["side"] == 1, S["or_low"][j], S["or_high"][j])
        df["close_gap"] = np.ones(len(df), bool)                  # every O2-O4 row's exit is the flat bar
    return df


# ───────────────────────────── claims 6-9 (PREREG 8): event geometry ─────────────────────────────

def breakout_days(ctx: M.Context, tf: str, version: str = NY) -> pd.DataFrame:
    """
    Per session the script counts (no profit or loss), cached: ``day``, ``t0``, ``valid``, ``complete``; the labels
    decided by 16:00 (``up_bar`` / ``dn_bar``, -1 none) and their HV tags (``up_hv`` / ``dn_hv``); the first of them
    (``first_side`` +1 / -1 / 0, ``first_bar``, ``first_hv``); ``c16_side`` the 16:00 close (the close of ``bar16``)
    against the range (+1 above ``or_high``, -1 below ``or_low``, 0 inside, NaN unknown or no range); the dashboard's
    hits (``hit_u1`` .. ``hit_d3``: the port's, reached any time in the span, l.195-214) and the after-breakout hits
    (``after_u1`` .. ``after_d3``: ``after_hits``).
    """
    def make():
        S = sessions(ctx, tf, version)
        H = after_hits(ctx, tf, version)
        out = orb_output(ctx, tf, version)
        d = out["days"]
        b = ctx.bars(tf)
        hv = np.asarray(out["hv"], bool)
        nS = len(S["day"])
        df = pd.DataFrame({"day": S["day"], "t0": S["t0"], "valid": S["valid"], "complete": H["complete"]})
        for key in ("up", "dn"):
            lab = S[f"label_{key}_bar"]
            dec = (lab >= 0) & (b.tc[np.maximum(lab, 0)] <= S["entry_end_s"])
            df[f"{key}_bar"] = np.where(dec, lab, -1)
            df[f"{key}_hv"] = dec & hv[np.maximum(lab, 0)]
        ub, db = df.up_bar.to_numpy(), df.dn_bar.to_numpy()
        big = np.iinfo(np.int64).max
        uu, dd = np.where(ub >= 0, ub, big), np.where(db >= 0, db, big)
        first = np.where((ub < 0) & (db < 0), 0, np.where(uu < dd, 1, -1))
        df["first_side"] = first
        df["first_bar"] = np.where(first == 1, ub, np.where(first == -1, db, -1))
        df["first_hv"] = np.where(first == 1, df.up_hv, np.where(first == -1, df.dn_hv, False))
        k16 = S["bar16"]
        c16 = np.where(k16 >= 0, b.c[np.maximum(k16, 0)], np.nan) if nS else np.zeros(0)
        with np.errstate(invalid="ignore"):
            side16 = np.where(c16 > S["or_high"], 1.0, np.where(c16 < S["or_low"], -1.0, 0.0))
        df["c16_side"] = np.where(np.isfinite(c16) & S["valid"], side16, np.nan)
        for k in ("u1", "u2", "u3", "d1", "d2", "d3"):
            df[f"hit_{k}"] = d[f"hit_{k}"].to_numpy(bool)
        for i in range(3):
            df[f"after_u{i + 1}"] = H["hit_up"][:, i]
            df[f"after_d{i + 1}"] = H["hit_dn"][:, i]
        return df
    return ctx.get(MODULE, tf, {"series": "breakout_days", "version": version}, make)


def _window_rows(ctx: M.Context, tf: str, start, end, version: str = NY) -> pd.DataFrame:
    a_s, z_s = M.s_of(start), M.s_of(end)
    if z_s > int(ctx.mk.end_s):
        raise ValueError(f"{ctx.symbol}: the window ends {M.utc(z_s)}, after the data served ({M.utc(ctx.mk.end_s)})")
    df = breakout_days(ctx, tf, version)
    return df[(df.t0 >= a_s) & (df.t0 < z_s) & df.complete]


def direction_stats(ctx: M.Context, tf: str, start, end, version: str = NY) -> Dict[str, int]:
    """Claim 6 over the complete sessions opening in [start, end): sessions, breakout days (a label decided by 16:00),
    and among them the 16:00 close beyond the first breakout's side (``same``), beyond the other side (``opposite``),
    inside the range (``inside``)."""
    w = _window_rows(ctx, tf, start, end, version)
    bo = w[(w.first_side != 0) & w.c16_side.notna()]
    fs, cs = bo.first_side.to_numpy(np.int64), bo.c16_side.to_numpy(np.float64)
    return {"sessions": int(len(w)), "breakouts": int(len(bo)), "same": int((cs == fs).sum()),
            "opposite": int((cs == -fs).sum()), "inside": int((cs == 0).sum())}


def hit_rate_stats(ctx: M.Context, tf: str, start, end, version: str = NY) -> Dict[str, object]:
    """Claim 8 over the complete sessions opening in [start, end), per level T1-T3 with both sides pooled: the
    dashboard's unconditional hits over 2 x sessions (one up and one down chance a session; the port's flags) and the
    after-breakout hits over the labels decided by 16:00 (``after_hits``), with the two-proportion z statistic."""
    w = _window_rows(ctx, tf, start, end, version)
    n_u = 2 * len(w)
    up, dn = w.up_bar.to_numpy() >= 0, w.dn_bar.to_numpy() >= 0
    n_a = int(up.sum() + dn.sum())
    out: Dict[str, object] = {"sessions": int(len(w)), "n_dashboard": int(n_u), "n_after": n_a}
    for k in (1, 2, 3):
        x_u = int(w[f"hit_u{k}"].sum() + w[f"hit_d{k}"].sum())
        x_a = int(w[f"after_u{k}"].to_numpy()[up].sum() + w[f"after_d{k}"].to_numpy()[dn].sum())
        p_u = x_u / n_u if n_u else np.nan
        p_a = x_a / n_a if n_a else np.nan
        z = np.nan
        if n_u and n_a:
            p = (x_u + x_a) / (n_u + n_a)
            se = math.sqrt(p * (1.0 - p) * (1.0 / n_u + 1.0 / n_a))
            z = (p_a - p_u) / se if se > 0 else np.nan
        out[f"T{k}"] = {"dashboard_hits": x_u, "dashboard_rate": p_u, "after_hits": x_a, "after_rate": p_a, "z": z}
    return out


def clock_stats(ctx: M.Context, tf: str, start, end) -> Dict[str, int]:
    """Claim 9's geometry over the literal UTC-5 clock's complete sessions opening in [start, end): sessions, those
    whose range starts at 10:30 New York (``late``) and at 09:30 (``on_time``), and those whose date is on daylight
    saving time in New York (UTC-4 at the range's start: ``dst``); ``late_not_dst`` / ``dst_not_late`` count
    exceptions."""
    w = _window_rows(ctx, tf, start, end, UTC5)
    t0 = w.t0.to_numpy(np.int64)
    loc = M.ny_local(t0) if len(t0) else np.zeros(0, np.int64)
    minute = (loc % M.DAY) // 60
    dst = (loc - t0) == -4 * 3600
    late = minute == 630
    return {"sessions": int(len(w)), "late": int(late.sum()), "on_time": int((minute == 570).sum()),
            "dst": int(dst.sum()), "late_not_dst": int((late & ~dst).sum()), "dst_not_late": int((dst & ~late).sum())}


def _claim_error(msg: str) -> Exception:
    try:
        from . import tradeiq2 as D
        return D.ClaimError(msg)
    except ImportError:                                  # the driver is not importable: a plain lookup error
        return LookupError(msg)


def _part(part: str, symbol: str, rows: str, dev: str, val: str, dev_ok, val_ok, note: str = "") -> Dict[str, object]:
    return {"part": part, "symbol": symbol, "rows": rows, "dev": dev, "val": val, "dev_ok": dev_ok,
            "val_ok": val_ok, "note": note}


def _pct(k, n) -> str:
    return f"{100.0 * k / n:.1f}%" if n else "-"


def _spans(ev, symbol: str) -> List[Tuple[str, str]]:
    return [M.window_span(w, symbol) for w in ev.windows]


def _most(k: int, n: int) -> bool:
    return n > 0 and 2 * k > n


def claim6(ev) -> List[Dict[str, object]]:
    """PREREG 8 claim 6: "a break of the range often sets the direction for the day", per symbol and timeframe over
    the evidence's two windows (``ev.windows``; geometry of the 09:30 New York version)."""
    out = []
    for s in ev.symbols:
        ctx = ev.context(s)
        for tf in TFS:
            st = [direction_stats(ctx, tf, a, z) for a, z in _spans(ev, s)]
            txt = [f"{x['same']}/{x['breakouts']} breakout days ({_pct(x['same'], x['breakouts'])}); beyond the other "
                   f"side {x['opposite']} ({_pct(x['opposite'], x['breakouts'])}), inside {x['inside']}; "
                   f"{x['sessions']} sessions" for x in st]
            rows = f"{tf}: sessions with a label decided by 16:00 New York; the close of the bar closing at 16:00"
            out.append(_part("the 16:00 close is beyond the range on the first breakout's side on more than half of "
                             "the breakout days", s, rows, txt[0], txt[1], _most(st[0]["same"], st[0]["breakouts"]),
                             _most(st[1]["same"], st[1]["breakouts"])))
            out.append(_part("the 16:00 close is beyond the first breakout's side more often than beyond the other "
                             "side", s, rows, txt[0], txt[1], st[0]["same"] > st[0]["opposite"],
                             st[1]["same"] > st[1]["opposite"]))
    return out


def _need(ev, ids: Sequence[str], what: str) -> None:
    missing = [x for x in ids if x not in ev.dev.index or x not in ev.val.index]
    if missing:
        raise _claim_error(f"{what}: rows not in the results: {', '.join(missing[:4])}")


def claim7(ev) -> List[Dict[str, object]]:
    """PREREG 8 claim 7: "take the breakouts that come with high volume". The test: HV against the LV control, same
    rule (O1-O4 x M5, M15; the driver's results: HV makes more net in most pairs). For information: after HV and LV
    labels, the 16:00 close beyond the label's side and T1 reached after the label (geometry)."""
    out = []
    for s in ev.symbols:
        pairs = [(vid(s, tf, Row(r, "HV")), vid(s, tf, Row(r, LV, eligible=False))) for tf in TFS
                 for r in ("O1", "O2", "O3", "O4")]
        _need(ev, [x for p in pairs for x in p], "ORB HV / LV pairs")
        kd = sum(float(ev.dev.at[a, "net"]) > float(ev.dev.at[b, "net"]) for a, b in pairs)
        kv = sum(float(ev.val.at[a, "net"]) > float(ev.val.at[b, "net"]) for a, b in pairs)
        out.append(_part("HV makes more net than LV in most pairs", s, "ORB O1-O4 x HV against the LV control, same "
                         "rule and timeframe (M5, M15)", f"{kd}/{len(pairs)}", f"{kv}/{len(pairs)}",
                         _most(kd, len(pairs)), _most(kv, len(pairs))))
        ctx = ev.context(s)
        for tf in TFS:
            txt = []
            for a, z in _spans(ev, s):
                w = _window_rows(ctx, tf, a, z)
                parts = []
                for tag, want in (("HV", True), ("LV", False)):
                    n = same = t1 = 0
                    for key, sd in (("up", 1), ("dn", -1)):
                        m = (w[f"{key}_bar"].to_numpy() >= 0) & (w[f"{key}_hv"].to_numpy() == want)
                        n += int(m.sum())
                        same += int((w.c16_side.to_numpy()[m] == sd).sum())
                        t1 += int(w[f"after_{'u' if sd == 1 else 'd'}1"].to_numpy()[m].sum())
                    parts.append(f"{tag} {n} labels: 16:00 close beyond their side {_pct(same, n)}, T1 after "
                                 f"{_pct(t1, n)}")
                txt.append("; ".join(parts))
            out.append(_part("after HV and LV breakouts: the 16:00 close and T1 (information)", s,
                             f"{tf}: labels decided by 16:00 New York", txt[0], txt[1], np.nan, np.nan,
                             "geometry, no verdict"))
    return out


def claim8(ev) -> List[Dict[str, object]]:
    """PREREG 8 claim 8: "the dashboard's hit rates are unconditional, not win rates": per symbol, timeframe and level
    (both sides pooled), the dashboard's rate against the rate after a breakout (O4's statistic); they differ when
    |z| > 1.96 (a two-proportion z-test at 5%). The driver adds O4 against O2 and O3."""
    out = []
    for s in ev.symbols:
        ctx = ev.context(s)
        for tf in TFS:
            st = [hit_rate_stats(ctx, tf, a, z) for a, z in _spans(ev, s)]
            for k in (1, 2, 3):
                cells, oks = [], []
                for x in st:
                    t = x[f"T{k}"]
                    cells.append(f"dashboard {_pct(t['dashboard_hits'], x['n_dashboard'])} of {x['n_dashboard']} "
                                 f"side-days, after a breakout {_pct(t['after_hits'], x['n_after'])} of "
                                 f"{x['n_after']} (z {t['z']:.2f})" if math.isfinite(t["z"]) else
                                 f"dashboard {t['dashboard_hits']}/{x['n_dashboard']}, after {t['after_hits']}/"
                                 f"{x['n_after']}")
                    oks.append(bool(math.isfinite(t["z"]) and abs(t["z"]) > Z_CRIT))
                out.append(_part(f"T{k}: the rate after a breakout differs from the dashboard's unconditional rate", s,
                                 f"{tf}: every session (dashboard, the script's count) against the labels decided by "
                                 "16:00 (reached after the label bar, by 16:55)", cells[0], cells[1], oks[0], oks[1],
                                 "a two-proportion z-test at 5%, both sides pooled"))
    return out


def claim9(ev) -> List[Dict[str, object]]:
    """PREREG 8 claim 9: "the UTC-5 default is an hour late in summer": the literal clock's range at 10:30 New York on
    the daylight-saving sessions (geometry), and O1 x F0 on New York time against the literal clock (the driver's
    results: the New York clock makes more net on both timeframes)."""
    out = []
    for s in ev.symbols:
        ctx = ev.context(s)
        st = [clock_stats(ctx, "M5", a, z) for a, z in _spans(ev, s)]
        txt = [f"{x['late']}/{x['sessions']} sessions start at 10:30 New York ({x['dst']} on daylight saving), "
               f"{x['on_time']} at 09:30" for x in st]
        oks = [x["sessions"] > 0 and x["late"] == x["dst"] and x["late_not_dst"] == 0 and x["dst_not_late"] == 0
               and x["late"] + x["on_time"] == x["sessions"] for x in st]
        out.append(_part("the literal UTC-5 clock's range starts an hour late (10:30 New York) on every "
                         "daylight-saving session and on no other", s, "M5: the sessions of the literal clock",
                         txt[0], txt[1], oks[0], oks[1]))
        pairs = [(vid(s, tf, Row("O1", "F0")), vid(s, tf, Row("O1", "F0", UTC5, eligible=False))) for tf in TFS]
        _need(ev, [x for p in pairs for x in p], "ORB O1 x F0 New York / UTC-5 pairs")
        kd = sum(float(ev.dev.at[a, "net"]) > float(ev.dev.at[b, "net"]) for a, b in pairs)
        kv = sum(float(ev.val.at[a, "net"]) > float(ev.val.at[b, "net"]) for a, b in pairs)
        out.append(_part("O1 on New York time makes more net than on the literal UTC-5 clock on both timeframes", s,
                         "ORB O1 x F0 against its UTC-5 control (M5, M15)", f"{kd}/{len(pairs)}", f"{kv}/{len(pairs)}",
                         kd == len(pairs), kv == len(pairs)))
    return out
