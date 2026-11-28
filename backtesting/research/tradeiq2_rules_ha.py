"""
Heikin Ashi Candles, Trend Strength & Trend Age Stats (LunqFX) as rules (study 2, PREREG 6.8): the management
overlays M1-M5 and HA-AND on the nine bases, and the entry controls HA-H1 / HA-H2, for the driver (``tradeiq2.py``):
``variants(symbol)``, ``build(variant, ctx)``, ``base_of(variant)``, ``describe(variant)`` and ``warm(ctx, variants)``.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_ha as H
    ctx = M.Context(M.load("XAUUSDm"))         # served to the hold-out start until FINALISTS.md is frozen
    vs = H.variants("XAUUSDm")                 # 78 rows: 54 HA-MANAGED + 24 HA-ENTRY
    ex = H.build(vs[0], ctx)                   # a tradeiq2_market.Exec
    res = M.run_variant(ctx, vs[0], ex)        # Development, Validation and D+V at x1.0 and x1.5
    H.base_of(vs[0])                           # 'XAUUSDm|1H|QQE|R2|F2-4H|S0': the row it is paired with

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen; read with ``DEVIATIONS.md``): sections 4 (execution,
the rules for absolute levels), 5 (how a filter applies: state filters against entry gates), 6.8 (these rows) and 7
(families, eligibility). The candles, phases, streaks and trend-age statistics are the reconciled port
``tradeiq2_ind_ha`` (port A, equal bit for bit to port B on the study's 1H / 4H / 1D bars; ``porting/ha.md``), run on
the base's own bars from the study's data start (gold 2016-01-03, BTC 2018-01-01: ``tradeiq2_market.load``) with the
script's defaults and PREREG 6.8's minimum of 50 finished streaks for a rare age. The bases are study 1's three
finalists of each symbol (``backtest_results/tradeiq_rsi/FINALISTS.md``; their states are built by study 1's own
``tradeiq.lines_of``, ``raw_state``, ``htf_sides``, ``allowed_of`` and ``apply_filter``, their S1 by
``tradeiq_market.s1_stop``) and RIB-LS / RIB-LO x X0 x F0 on 1H, 4H and 1D (``tradeiq2_rules_ribbon.rib_exec``, the
ribbon module's own Exec with the overlays passed through). The execution is ``tradeiq2_market`` (study 1's fills,
stops, marks and scores). Nothing is tuned. Line numbers l. are those of the owner's plain-text copy of the script
(Pine v6, 327 lines; third-party code, cited here, never copied).

The grid (per symbol; XAUUSDm and BTCUSDm only, none on the claim markets)
--------------------------------------------------------------------------
========== =============================================================================== ===== =====================
family     rows                                                                             n     eligible
========== =============================================================================== ===== =====================
HA-MANAGED M1, M2, M3, M4, M5, HA-AND x the 9 bases, Heikin Ashi on the base's timeframe     54    yes
HA-ENTRY   HA-H1, HA-H2 x LS, LO x F0, F2 (1H: F2-4H, 4H: F2-1D, 1D: F1) x 1H, 4H, 1D        24    yes ("control")
========== =============================================================================== ===== =====================

The bases (PREREG 6.8 "Bases"): gold ``XAUUSDm|1H|QQE|R2|F2-4H|S0``, ``XAUUSDm|1H|LaRSI|R2|F1|S0``,
``XAUUSDm|4H|RSI|R2|F1|S0``; BTC ``BTCUSDm|1D|LaRSI|R2|F3|S1``, ``BTCUSDm|1D|VWRSI|R3|F0|S1``,
``BTCUSDm|4H|TSI|R2|F1|S0`` (study 1's frozen finalists, ``STUDY1_FINALISTS``); and on both symbols
``symbol|tf|RIB|LS|X0|F0`` and ``symbol|tf|RIB|LO|X0|F0`` for tf = 1H, 4H, 1D. 9 x 6 = 54 and 2 x 2 x 2 x 3 = 24,
78 rows, every one eligible: section 6.8 marks none "not eligible" or "information only", the entry rules are
controls and PREREG 7 lets controls qualify (its 738 / 720 eligible rows count all 78). Families HA-MANAGED and
HA-ENTRY (PREREG 7; one script for the finalists, "HA").

Ids: ``symbol|tf|HA-MANAGED|overlay|base`` with the base's id after its symbol and timeframe joined by '-' (e.g.
``XAUUSDm|1H|HA-MANAGED|M2|QQE-R2-F2-4H-S0``, ``BTCUSDm|4H|HA-MANAGED|HA-AND|RIB-LO-X0-F0``); ``params['base']`` and
``base_of`` give the base's own id (study 1's ``grid.csv`` id, or this study's RIB row), which the driver pairs the
row with (claims 3 and 4). ``symbol|tf|HA-ENTRY|rule|side|filter`` (e.g. ``XAUUSDm|1H|HA-ENTRY|HA-H1|LS|F2-4H``).
The overlay is one id token and no param value names another overlay, so the driver's token selection of M2 finds
M2's rows and not M5's; the base is one token, so a study-1 base's filter (F2-4H, F1, F3) is no filter token of the
row and ``vs_f0`` does not try to pair it; an HA-ENTRY F2 row pairs with its F0 row by the filter token.

The Heikin Ashi series the rules read (``tradeiq2_ind_ha.heikin_ashi`` of the base's bars; final at each bar's close)
--------------------------------------------------------------------------------------------------------------------
* ``dir``: the candle's colour, ``haC >= haO`` bullish (+1), else bearish (-1): a tie is bullish (l.85), with
  ``haC = (O + H + L + C) / 4`` and ``haO = (haO[1] + haC[1]) / 2`` (l.79-81).
* ``flip``: the colour differs from the previous candle's (l.115); a flip starts a new streak.
* ``ev_ind``: an INDECISION candle right after 2 or more consecutive STRONG candles of the same streak (l.156, the
  script's "INDECISION after a STRONG run"); never on a flip candle (the run is reset at the flip first, l.147). Its
  colour is the streak's.
* ``weak_run``: consecutive WEAK candles of the streak (WEAK: the previous candle's colour and a smaller body, l.94);
  PREREG 6.8's M3 counter, not in the script.
* ``ev_first_strong``: the streak's first STRONG candle (l.158-160; it can be the flip candle).
* ``rare_now``: the bar on which the streak's age first has at least 90% of the finished streaks of its colour shorter
  than it (l.209-212), evaluated at every bar as the script's live alert would at that close (the script computes
  it on the last bar only), and only once 50 streaks of that colour have finished (PREREG 6.8). At most once a
  streak. The script tags every alert with the candle's colour (``side``, l.290-298).

HA-MANAGED: the overlays (PREREG 6.8, "the video's use, not for entries"). Each is its base plus one change
-------------------------------------------------------------------------------------------------------------
A position reacts only to Heikin Ashi events of its own colour (reading 1): a long to bullish candles' events, a short
to bearish ones (M1's flip is against the position by definition).

* M1: exit at the close of a colour flip against the position: a long at a flip to bearish, a short at a flip to
  bullish (``exit_long`` / ``exit_short``: filled at the next M1 open).
* M2: at an ``ev_ind`` candle of the position's colour, the stop moves to the tighter of break-even and that bar's low
  (a long: max(entry fill, low); a short: min(entry fill, high); reading 2), decided at the bar's close and applied
  at the next M1 open (``tighten_long`` / ``tighten_short`` = the bar's low / high, ``tighten_be`` True).
* M3: the same tightening at every WEAK candle of the position's colour that is at least the second WEAK candle in a
  row (``weak_run >= 2``; reading 3).
* M4: exit at the close of the bar on which a streak of the position's colour reaches its rare age (``rare_now``).
* M5: M1 + M2 (the video's "hold on strong, tighten up, get out on the flip").
* HA-AND: the base's entries are taken only when the Heikin Ashi candle of their decision bar has their colour; a
  refused entry is not taken later, and the base's exits are its own (reading 4).
* After a Heikin Ashi exit (M1, M4, or a stop at a tightened level) the base stays flat until its own state changes
  (PREREG 6.8): a study-1 base until its state changes (the harness's state rule: an entry only where the state
  changes), a ribbon base until its next flip (an event rule waits for its next event). The base's own exits stay:
  its state change and S1 stop (study 1), its stop and the opposite ribbon flip (RIB X0).

The base kinds:
* Study 1's finalists are STATE rules (``M.state_exec(tf, state, stop, exit_long=.., tighten_long=.., ...)``: the
  harness turns the state into study 1's entries, an entry where the state changes and at a window's first bar,
  executed one position at a time with the overlays; without overlays it is ``tradeiq_market.run`` itself). S0 bases
  have no stop until M2 / M3 set one; BTC's S1 bases keep study 1's 3 x ATR(14) stop from the fill until a tighter
  level replaces it.
* The ribbon bases are EVENT rules (``tradeiq2_rules_ribbon.rib_exec(ctx, tf, side, 'X0', 'F0', ...)``): a flip opens
  (LS both sides, LO longs), the stop sits riskDist from the fill, the opposite flip exits; the HA exits are OR-ed
  with the flips' exits, the tightenings passed through, HA-AND is ``rib_exec``'s ``gate`` (checked at the flip's
  close, PREREG 5's event-rule gate).

HA-ENTRY: the entry controls (PREREG 6.8, "the video says not to use it for entries"); state rules, no stop
------------------------------------------------------------------------------------------------------------
* HA-H1: long from the first STRONG candle of a bullish streak to the streak's last candle, short from the first
  STRONG candle of a bearish streak; flat between a flip and the new streak's first STRONG candle ("in at the first
  STRONG candle of a streak, out at the flip"). A STRONG flip candle enters at once (LS: the flip reverses).
* HA-H2: the colour stop-and-reverse: long while the candle is bullish, short while it is bearish.
* LO: the short state is flat. Filters F0 and F2 (1H: F2-4H, 4H: F2-1D, 1D: F1, as PREREG 6.3, 6.4 and 6.7 spell
  "F2"), state filters (PREREG 5; ``tradeiq2_filters.as_state_filter``): a state the filter does not allow is flat, so
  the position closes when the filter turns against it and opens where it turns in favour (reading 5). No stop: the
  plan names none ("colour stop-and-reverse": the flip is the stop). Executed as study 1's ``run`` (the window's first
  bar takes the state).

Execution and the rules for absolute levels (PREREG 4; study 1's DEVIATIONS 1-7 and DEVIATIONS 3-5 of this study)
----------------------------------------------------------------------------------------------------------------
* A decision is taken at a bar's close and filled at the open of the first M1 bar at or after it (a buy at the ask,
  a sell at the bid). Stops are checked on every M1 bar, a gap through a stop fills at the open, one extra spread is
  charged on every stop fill (a break-even stop too).
* The overlays act from the bar after the entry's decision bar (DEVIATIONS 4): an event on the decision bar itself is
  not acted on, the trade is not open at that close (reading 6).
* A tightened level is applied at the open of the M1 bar that executes it only if it lies below the bid (a long) /
  above the ask (a short) there; a level price has already crossed is a market exit at that open (booked as a signal
  exit, no extra spread); a level looser than the current stop changes nothing (DEVIATIONS 5). Break-even is the
  entry's actual fill, so M2 / M3 close a losing trade at the next open (reading 7). The x1.5 run recomputes every
  fill, break-even and comparison on its own spreads.
* No entry of these rows carries an absolute stop or target level: the bases' stops are distances from the fill
  (S1, riskDist), so no entry can be dropped for a fill beyond its stop or target (the dropped counts stay 0).

What is known when (no look-ahead)
----------------------------------
Every decision of bar t reads bars 0 .. t of the base's timeframe and, for the base's filter (study 1's F2-4H, F1, F3;
HA-ENTRY's F2), higher-timeframe bars CLOSED at t's close (``htf_at``). The Heikin Ashi candle of bar t uses bars
0 .. t (the recursion), the phase the previous candle, the statistics the streaks finished by t (a streak finishes at
the close of its flip candle); a tightening level is bar t's own low / high, known at its close; HA-AND's verdict on
an episode of the base is taken at the episode's first bar. Every decision fills at the next M1 open. Removing the
bars after t changes no decision up to t (tested on synthetic and on the study's bars).

Readings where the plan leaves a choice (proposed for DEVIATIONS.md; written before any result of these rows)
-----------------------------------------------------------------------------------------------------------
1. Whose events count. M2, M3 and M4 act on events of a streak of the POSITION's colour: a long tightens after
   INDECISION follows bullish STRONG candles and after bullish WEAK candles, and exits when a bullish streak reaches
   its rare age; a short mirrors it. The video's advice is about the move one is in ("strong candles, you hold; a run
   of weak candles or indecision after a strong run, you tighten up"), the script names each alert by the candle's
   colour (l.290-298), and study 3's HA-M4 reads the rare age the same way. The other reading (events of either
   colour) would also tighten a long when a bearish run tires, which is the opposite signal. In Development the
   events split about evenly by colour (bullish / bearish): INDECISION after STRONG gold 1H 500 / 473, 4H 172 / 112,
   1D 20 / 11, BTC 1H 733 / 650, 4H 172 / 138, 1D 30 / 31; rare ages gold 1H 245 / 236, BTC 1H 440 / 431 (counts on
   the bars closing in 2019-2022, as ``porting/ha.md`` 6).
2. "That bar's low" is the signal bar's own (bid) low, for a short its high (spec 4.5: "that bar's real low"). Under
   reading 1 it is also the Heikin Ashi low: an INDECISION candle has wicks on both sides and a WEAK candle a wick
   against its colour, so their HA low (high) is the bar's own (``porting/ha.md`` 9.2, tested on the six series).
3. M3 tightens at every WEAK candle that is at least the second in a row (``weak_run >= 2``), each time to the tighter
   of break-even and its own low (a looser level changes nothing). "A run of weak candles ... you tighten up": the
   last two candles are again two consecutive WEAK candles at the third. The other reading (``weak_run == 2``, once a
   run) differs only where a third WEAK candle follows: 6 gold 1H, 8 BTC 1H and 4 BTC 4H Development bars
   (``porting/ha.md`` 6; counts only).
4. HA-AND ("the base, entered only while the Heikin Ashi colour agrees") gates the base's entries at their decision
   close, for both kinds of base: the colour of that bar's candle must be the entry's side (bullish for a long,
   bearish for a short; a tie is bullish, l.85). It never closes a trade; a refused entry is not taken later, so the
   base stays flat until its own state changes (as after a Heikin Ashi exit). For a ribbon base this is PREREG 5's
   event-rule gate at the flip. For a study-1 base (a state rule) the row's state is the base's state on the episodes
   (runs of one non-zero state) whose first bar had the colour, and flat on the others; the verdict is the
   episode's, so a window that starts inside an episode takes it as the continuous rule holds it. HA-AND's trades
   are therefore a subset of the base's (identical trades). Not taken: the colour as a state filter (it would close
   trades when the colour turns, which is M1's exit with re-entries), and a delayed entry at the first bar of an
   episode where the colour agrees (an entry the base itself never makes). Measured (counts only, the base's entries
   decided on bars closing in Development): HA-AND refuses gold QQE 3 of 347, LaRSI 77 / 377, RSI 54 / 234, BTC
   LaRSI 3 / 26, VWRSI 13 / 54, TSI 20 / 178, and on the ribbon bases at most 2.5% of the flips (gold 1H LS
   13 / 858, 4H 1 / 248; BTC 1H LS 31 / 1,272, 4H 8 / 322; none on 1D): the bases turn on strong closes, whose candle
   mostly has the entry's colour already, so several HA-AND rows are near copies of their bases.
5. HA-H1 and HA-H2 are state rules (the study's map, spec 4.5: "A state rule, so run works as it is"; HA-H2 is the
   colour itself, HA-H1 the colour from the streak's first STRONG candle), so F2 / F1 act on them as state filters
   (PREREG 5). With F0 the event reading (entries at the first STRONG candle / at each flip, the exit at the next
   flip) gives the same trades except at a window's first bar, which a state rule enters when its state is not flat
   (study 1's DEVIATIONS 2). No stop (PREREG 6.8 names none).
6. The overlays act from the bar after the entry's decision bar (DEVIATIONS 4): a flip, an INDECISION, a WEAK pair or
   a rare age on the decision bar itself is not acted on (the trade is not open at that close). So M1 holds a long
   that was entered on a bearish candle until the next flip to bearish, and M4 a long entered on its streak's
   rare-age bar until the next bullish streak's rare age. Measured on the Development entries (counts only): a flip
   against the entry on its own decision bar on at most 7.4% of a base's entries (BTC VWRSI 4 / 54; gold LaRSI
   14 / 377; the ribbon bases at most 1.9%, BTC 4H LO 3 / 161), a rare age of the entry's colour there on at most
   2.7% (gold LaRSI 10 / 377), except BTC's 1D LaRSI (2 / 26).
7. Break-even is the entry's actual fill (the ask paid for a long, the bid for a short; at x1.5 its own fill), the
   level RIB-XBE uses; a stop there is charged one spread as every stop fill. With PREREG 4's rule a break-even above
   the bid (a losing long) is a market exit at the next open: M2 and M3 close a losing trade at the event. On an S0
   base (gold's three finalists, BTC's TSI) the tightening sets the trade's first stop.
8. Study 1's finalists are exactly their rows (indicator, family, filter, stop), computed with study 1's functions on
   the study-2 market. BTC's two markets start together (2018-01-01), so its states are study 1's on every bar.
   Gold's starts in 2016 (study 1's in 2017): its states and S1 are equal on every bar closing in 2019-H1 (tested
   here); over 2019-2024 the unfiltered QQE / LaRSI / RSI states and S1 are equal by the MSD module's test, and the
   MA200 filters are windowed sums of identical closes. BTC's VWRSI R3 finalist reads Exness tick volume, as study
   1's row does: the base is the finalist itself, not study 1's Binance-volume "VWRSI-RV" row (PREREG 6.2's
   MSD-filter rows use RV; 6.8 names the finalists).
9. Heikin Ashi starts at the study's data start on the base's bars (``porting/ha.md`` 8.2), keeps the script's cap of
   5,000 streaks per colour (8.1) and counts the history's first streak (8.3): the port's readings, unchanged.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from . import tradeiq as T1
from . import tradeiq_market as TM
from . import tradeiq2_filters as F
from . import tradeiq2_ind_ha as HA
from . import tradeiq2_market as M
from . import tradeiq2_rules_ribbon as R

__all__ = ["MODULE", "SCRIPT", "FAMILIES", "TFS", "OVERLAYS", "EXIT_OVERLAYS", "ENTRY_RULES", "SIDES", "FILTER_SLOTS",
           "F2_SLOT",
           "STUDY1_FINALISTS", "RIB_BASES", "HA_PARAMS", "S1_PARAMS", "WEAK_RUN", "EXPECTED", "variants", "build",
           "base_of", "describe", "warm", "plan_counts", "bases", "base_token", "ha_of", "overlay_arrays",
           "colour_gate", "and_state", "h1_state", "entry_state", "study1_params", "study1_lines", "study1_state",
           "study1_stop", "managed_exec", "entry_exec"]

MODULE = "tradeiq2_rules_ha"                 # the Context cache's module key
SCRIPT = "HA"
MANAGED, ENTRY = "HA-MANAGED", "HA-ENTRY"
FAMILIES = (MANAGED, ENTRY)                  # PREREG 7's families of this script
TFS = ("1H", "4H", "1D")                     # PREREG 6.8: every base and every entry row is on 1H, 4H or 1D
OVERLAYS = ("M1", "M2", "M3", "M4", "M5", "HA-AND")     # PREREG 6.8, in its order
EXIT_OVERLAYS = ("M1", "M2", "M3", "M4", "M5")
ENTRY_RULES = ("HA-H1", "HA-H2")
SIDES = ("LS", "LO")
FILTER_SLOTS = ("F0", "F2")
F2_SLOT = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}       # PREREG 6.8: "F0 and F2 (1D: F1)"; F2 as 6.3 / 6.4 / 6.7
# PREREG 6.8 "Bases: study 1's three finalists on each symbol (tradeiq_rsi/FINALISTS.md)", in FINALISTS.md's order
STUDY1_FINALISTS: Dict[str, Tuple[str, ...]] = {
    "XAUUSDm": ("XAUUSDm|1H|QQE|R2|F2-4H|S0", "XAUUSDm|1H|LaRSI|R2|F1|S0", "XAUUSDm|4H|RSI|R2|F1|S0"),
    "BTCUSDm": ("BTCUSDm|1D|LaRSI|R2|F3|S1", "BTCUSDm|1D|VWRSI|R3|F0|S1", "BTCUSDm|4H|TSI|R2|F1|S0"),
}
# "RIB-LS x X0 x F0 and RIB-LO x X0 x F0 on 1H, 4H and 1D"
RIB_BASES: Tuple[Tuple[str, str], ...] = tuple((tf, side) for tf in TFS for side in SIDES)
# the port with the script's defaults (l.20-28) and the plan's minimum of 50 finished streaks: the cache key
HA_PARAMS: Dict[str, object] = {"series": "heikin_ashi", "strong_tol": 0.05, "doji_max": 0.25, "ahead_n": 5,
                                "rare_pct": 90, "min_streaks": 50}
S1_PARAMS: Dict[str, object] = {"series": "s1", "mult": 3.0, "n": 14}     # study 1's S1 (tradeiq_market.s1_stop)
WEAK_RUN = 2                                 # M3: "2 consecutive WEAK candles" (reading 3: weak_run >= 2)
# PREREG 6.8: "Size: 9 bases x 6 = 54 rows per symbol"; entry rules "24 rows per symbol"
EXPECTED: Dict[Tuple[str, bool], int] = {(MANAGED, True): 54, (ENTRY, True): 24}

OVERLAY_WORDS = {
    "M1": "M1: exit at the close of a Heikin Ashi colour flip against the position (a long at a flip to bearish, a "
          "short at a flip to bullish)",
    "M2": "M2: at an INDECISION candle right after 2 or more STRONG candles of a streak of the position's colour, the "
          "stop moves to the tighter of break-even (the entry fill) and that bar's low (a short: the lower of the fill "
          "and the bar's high), from the next M1 open; a level the price has already crossed there is a market exit",
    "M3": "M3: the same tightening as M2 at every WEAK candle of the position's colour that is at least the second "
          "WEAK candle in a row",
    "M4": "M4: exit at the close of the bar on which a streak of the position's colour reaches its rare age (at least "
          "90% of the finished streaks of that colour are shorter, from 50 finished streaks on)",
    "M5": "M5 = M1 + M2 (the video's 'hold on strong, tighten up, get out on the flip')",
    "HA-AND": "HA-AND: the base's entries are taken only when the Heikin Ashi candle of their decision bar has their "
              "colour (bullish for a long, bearish for a short); a refused entry is not taken later; the base's "
              "exits are its own",
}
ENTRY_WORDS = {
    ("HA-H1", "LS"): ("long from the first STRONG candle of a bullish Heikin Ashi streak (it can be the flip candle) "
                      "to the streak's end, short from the first STRONG candle of a bearish streak to its end, flat "
                      "in between"),
    ("HA-H1", "LO"): ("long from the first STRONG candle of a bullish Heikin Ashi streak (it can be the flip candle) "
                      "to the streak's end, flat otherwise (long only)"),
    ("HA-H2", "LS"): "long while the Heikin Ashi candle is bullish, short while it is bearish (the colour "
                     "stop-and-reverse)",
    ("HA-H2", "LO"): "long while the Heikin Ashi candle is bullish, flat while it is bearish (long only)",
}
FILTER_WORDS = {"F0": "no filter",
                "F1": "a long only while the close is above its MA200 (same timeframe), a short only below",
                "F2-4H": "a long only while the last closed 4H bar closed above its MA200, a short only below",
                "F2-1D": "a long only while the last closed 1D bar closed above its MA200, a short only below"}


def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _check_tf(tf: str) -> None:
    if tf not in TFS:
        raise ValueError(f"{tf}: the Heikin Ashi rules run on {', '.join(TFS)} (PREREG 6.8)")


# ───────────────────────────── the bases ─────────────────────────────

def bases(symbol: str) -> Tuple[str, ...]:
    """The nine bases of ``symbol`` in PREREG 6.8's order: study 1's three finalists, then RIB-LS / RIB-LO x X0 x F0
    on 1H, 4H and 1D (ids of study 1's ``grid.csv`` and of ``tradeiq2_rules_ribbon.variants``)."""
    if symbol not in STUDY1_FINALISTS:
        raise ValueError(f"{symbol}: PREREG 6.8's bases exist on {' and '.join(STUDY1_FINALISTS)} only")
    return STUDY1_FINALISTS[symbol] + tuple(f"{symbol}|{tf}|RIB|{side}|X0|F0" for tf, side in RIB_BASES)


def base_token(base: str) -> str:
    """The base's id after its symbol and timeframe, joined by '-': one token of an HA-MANAGED id."""
    return "-".join(base.split("|")[2:])


def _is_rib(base: str) -> bool:
    return base.split("|")[2] == "RIB"


def _base_parts(base: str) -> Tuple[str, str]:
    """(symbol, tf) of a base id, checked against the plan's nine bases."""
    sym, tf = base.split("|")[:2]
    if sym not in STUDY1_FINALISTS or base not in bases(sym):
        raise ValueError(f"{base}: not one of PREREG 6.8's bases")
    return sym, tf


# ───────────────────────────── the Heikin Ashi series (cached in the Context) ─────────────────────────────

def ha_of(ctx: M.Context, tf: str) -> Dict[str, np.ndarray]:
    """``tradeiq2_ind_ha.heikin_ashi(o, h, l, c)`` of ``ctx.bars(tf)`` with the script's defaults and the plan's 50
    finished streaks (``HA_PARAMS``): every per-bar key of the port's contract (``streaks`` dropped), read-only,
    cached as (MODULE, symbol, tf, HA_PARAMS). Each value of bar t is final at t's close (the port's docstring)."""
    _check_tf(tf)

    def make():
        b = ctx.bars(tf)
        p = {k: v for k, v in HA_PARAMS.items() if k != "series"}
        out = HA.heikin_ashi(b.o, b.h, b.l, b.c, **p)
        if tuple(out) != HA.KEYS:
            raise AssertionError("the Heikin Ashi port's contract changed")
        res = {k: _ro(v) for k, v in out.items() if k != "streaks"}
        if any(v.shape != (len(b),) for v in res.values()):
            raise AssertionError("a Heikin Ashi series does not have one value per bar")
        return res
    return ctx.get(MODULE, tf, HA_PARAMS, make)


def overlay_arrays(ctx: M.Context, tf: str, overlay: str) -> Dict[str, Optional[np.ndarray]]:
    """
    The per-bar overlay of M1-M5 on ``tf`` for the harness (``exit_long``, ``exit_short``, ``tighten_long``,
    ``tighten_short``, ``tighten_be``; None where the overlay has none), read-only, cached:

    * M1 (and M5): ``exit_long`` = a flip to bearish, ``exit_short`` = a flip to bullish;
    * M4: ``exit_long`` = ``rare_now`` of a bullish streak, ``exit_short`` = of a bearish one;
    * M2 (and M5): at ``ev_ind`` of a bullish candle ``tighten_long`` = the bar's low, of a bearish candle
      ``tighten_short`` = the bar's high, ``tighten_be`` True there (the tighter of that level and the entry fill);
    * M3: the same at ``weak_run >= 2``.
    """
    _check_tf(tf)
    if overlay not in EXIT_OVERLAYS:
        raise ValueError(f"{overlay}: one of {', '.join(EXIT_OVERLAYS)} (HA-AND is an entry gate: colour_gate)")

    def make():
        h = ha_of(ctx, tf)
        b = ctx.bars(tf)
        d = np.asarray(h["dir"])
        out: Dict[str, Optional[np.ndarray]] = {"exit_long": None, "exit_short": None, "tighten_long": None,
                                                "tighten_short": None, "tighten_be": None}
        if overlay in ("M1", "M5"):
            out["exit_long"] = _ro(h["flip"] & (d == -1))
            out["exit_short"] = _ro(h["flip"] & (d == 1))
        if overlay == "M4":
            out["exit_long"] = _ro(h["rare_now"] & (d == 1))
            out["exit_short"] = _ro(h["rare_now"] & (d == -1))
        if overlay in ("M2", "M3", "M5"):
            trig = np.asarray(h["ev_ind"], bool) if overlay != "M3" else np.asarray(h["weak_run"]) >= WEAK_RUN
            tl, ts = trig & (d == 1), trig & (d == -1)
            out["tighten_long"] = _ro(np.where(tl, b.l, np.nan))
            out["tighten_short"] = _ro(np.where(ts, b.h, np.nan))
            out["tighten_be"] = _ro(tl | ts)
        return out
    return ctx.get(MODULE, tf, {"series": "overlay", "overlay": overlay}, make)


def colour_gate(ctx: M.Context, tf: str) -> Tuple[np.ndarray, np.ndarray]:
    """HA-AND's (allow_long, allow_short) per bar: the candle is bullish / bearish (a tie is bullish, l.85)."""
    def make():
        d = np.asarray(ha_of(ctx, tf)["dir"])
        return _ro(d == 1), _ro(d == -1)
    return ctx.get(MODULE, tf, {"series": "colour_gate"}, make)


def and_state(base, colour) -> np.ndarray:
    """
    HA-AND on a state base (reading 4): the base's state (+1 / 0 / -1) on the episodes (maximal runs of one non-zero
    state) whose first bar had the candle of that side (``colour`` = the Heikin Ashi ``dir`` per bar), 0 on the
    others and wherever the base is 0. Causal: bar t reads the base and the colour at its episode's first bar <= t.
    """
    st = np.asarray(base, np.int64)
    col = np.asarray(colour, np.int64)
    if st.shape != col.shape or st.ndim != 1:
        raise ValueError("the base state and the colour must be 1-D series of one length")
    n = len(st)
    if n == 0:
        return np.zeros(0, np.int8)
    prev = np.concatenate(([0], st[:-1]))
    start = (st != 0) & (st != prev)
    ok = start & (col == st)
    last = np.maximum.accumulate(np.where(start, np.arange(n), -1))
    keep = (st != 0) & (last >= 0) & ok[np.maximum(last, 0)]
    return np.where(keep, st, 0).astype(np.int8)


def h1_state(h: Mapping[str, np.ndarray]) -> np.ndarray:
    """HA-H1's state before its filter: the streak's colour from its first STRONG candle (``ev_first_strong``, the
    flip candle included) to its last candle, 0 before it (and on a streak without a STRONG candle). int8."""
    d = np.asarray(h["dir"], np.int64)
    flip = np.asarray(h["flip"], bool)
    evf = np.asarray(h["ev_first_strong"], bool)
    n = len(d)
    if n == 0:
        return np.zeros(0, np.int8)
    idx = np.arange(n)
    start = np.maximum.accumulate(np.where(flip | (idx == 0), idx, 0))       # the streak's first bar
    c = np.cumsum(evf.astype(np.int64))
    before = np.where(start > 0, c[np.maximum(start - 1, 0)], 0)
    seen = (c - before) > 0
    return np.where(seen, d, 0).astype(np.int8)


def entry_state(ctx: M.Context, tf: str, rule: str, side: str, filt: str) -> np.ndarray:
    """HA-H1 / HA-H2's state per bar of ``tf`` (int8, read-only, cached): ``h1_state`` or the colour, LO with the
    short state flat, then the filter as a state filter (``tradeiq2_filters.as_state_filter`` of ``ctx.allow``)."""
    _check_tf(tf)
    if rule not in ENTRY_RULES or side not in SIDES:
        raise ValueError(f"{rule} / {side}: one of {', '.join(ENTRY_RULES)} / {', '.join(SIDES)}")
    if filt not in ("F0", F2_SLOT[tf]):
        raise ValueError(f"{filt}: the {tf} entry rows use F0 or {F2_SLOT[tf]} (PREREG 6.8)")

    def make():
        h = ha_of(ctx, tf)
        raw = h1_state(h) if rule == "HA-H1" else np.asarray(h["dir"], np.int8).copy()
        if side == "LO":
            raw = np.where(raw == 1, 1, 0).astype(np.int8)
        return _ro(F.as_state_filter(raw, *ctx.allow(tf, filt)))
    return ctx.get(MODULE, tf, {"series": "entry", "rule": rule, "side": side, "filter": filt}, make)


# ───────────────────────────── study 1's finalists (state bases) ─────────────────────────────

def study1_params(base: str) -> Dict[str, str]:
    """The cache key of a study-1 base's state (``study1_state``)."""
    return {"series": "study1_state", "base": base}


def study1_lines(ctx: M.Context, tf: str) -> Dict[str, np.ndarray]:
    """Study 1's lines of ``tf`` (``tradeiq.lines_of``: the scripts' defaults; on BTC also the Binance-volume VWRSI)
    on the context's market, read-only, cached."""
    return ctx.get(MODULE, tf, {"series": "study1_lines"},
                   lambda: {k: _ro(v) for k, v in T1.lines_of(ctx.mk, tf).items()})


def study1_state(ctx: M.Context, base: str) -> np.ndarray:
    """The state of study 1's finalist ``base`` per bar of its timeframe (int8, read-only, cached): study 1's
    ``Study.state`` composition, ``apply_filter(raw_state(lines), allowed_of(lines, filter, htf_sides))``."""
    sym, tf = _base_parts(base)
    if _is_rib(base):
        raise ValueError(f"{base}: a ribbon base, not one of study 1's finalists")
    if sym != ctx.symbol:
        raise ValueError(f"{base}: not a base of {ctx.symbol}")
    v = T1.Variant.of(base)

    def make():
        L = study1_lines(ctx, tf)
        raw = T1.raw_state(L, v.indicator, v.family)
        f2 = T1.htf_sides(ctx.bars(v.filt[3:]), ctx.bars(tf)) if v.filt.startswith("F2-") else None
        al, ash = T1.allowed_of(L, v.filt, f2)
        return _ro(T1.apply_filter(raw, al, ash))
    st = ctx.get(MODULE, tf, study1_params(base), make)
    if st.shape != (len(ctx.bars(tf)),):
        raise AssertionError(f"{base}: a state of shape {st.shape}")
    return st


def study1_stop(ctx: M.Context, base: str) -> Optional[np.ndarray]:
    """S1's distance per bar (study 1's ``tradeiq_market.s1_stop``: 3 x Wilder ATR(14) of the signal bars, taken at the
    entry's decision bar and set from the fill) for an S1 finalist; None for an S0 one."""
    _, tf = _base_parts(base)
    if T1.Variant.of(base).stop == "S0":
        return None
    return ctx.get(MODULE, tf, S1_PARAMS, lambda: _ro(TM.s1_stop(ctx.bars(tf))))


# ───────────────────────────── the Execs ─────────────────────────────

def managed_exec(ctx: M.Context, base: str, overlay: str, label: str = "") -> M.Exec:
    """The Exec of ``overlay`` (M1-M5, HA-AND) on ``base`` (one of ``bases(ctx.symbol)``), Heikin Ashi on the base's
    timeframe: a STATE Exec (``M.state_exec``) for study 1's finalists, ``tradeiq2_rules_ribbon.rib_exec`` (EVENTS)
    for the ribbon bases (see the module docstring)."""
    sym, tf = _base_parts(base)
    if sym != ctx.symbol:
        raise ValueError(f"{base}: not a base of {ctx.symbol}")
    if overlay not in OVERLAYS:
        raise ValueError(f"{overlay}: one of {', '.join(OVERLAYS)}")
    if _is_rib(base):
        side = base.split("|")[3]
        if overlay == "HA-AND":
            return R.rib_exec(ctx, tf, side, "X0", "F0", gate=colour_gate(ctx, tf), label=label)
        return R.rib_exec(ctx, tf, side, "X0", "F0", label=label, **overlay_arrays(ctx, tf, overlay))
    stop = study1_stop(ctx, base)
    if overlay == "HA-AND":
        st = ctx.get(MODULE, tf, {"series": "ha_and", "base": base},
                     lambda: _ro(and_state(study1_state(ctx, base), ha_of(ctx, tf)["dir"])))
        return M.state_exec(tf, st, stop, label=label)
    return M.state_exec(tf, study1_state(ctx, base), stop, label=label, **overlay_arrays(ctx, tf, overlay))


def entry_exec(ctx: M.Context, tf: str, rule: str, side: str, filt: str, label: str = "") -> M.Exec:
    """The STATE Exec of an HA-ENTRY row: ``entry_state``, no stop, no overlay (study 1's ``run``)."""
    return M.state_exec(tf, entry_state(ctx, tf, rule, side, filt), None, label=label)


# ───────────────────────────── the grid ─────────────────────────────

def _managed(symbol: str, base: str, overlay: str) -> M.Variant:
    _, tf = base.split("|")[:2]
    rib = _is_rib(base)
    params = {"rule": overlay, "overlay": overlay, "base": base, "base_kind": "event" if rib else "state",
              "base_source": "this study's RIB row" if rib else "study 1's finalist",
              "exit": {"M1": "ha-flip", "M4": "rare-age", "M5": "ha-flip"}.get(overlay, "base"),
              "tighten": {"M2": "indecision-after-strong", "M3": "two-weak", "M5": "indecision-after-strong"}
              .get(overlay, "none"),
              "entry_gate": "ha-colour" if overlay == "HA-AND" else "none", "ha_tf": tf, "events": "own colour"}
    return M.Variant(f"{symbol}|{tf}|{MANAGED}|{overlay}|{base_token(base)}", symbol, tf, SCRIPT, MANAGED, True, "",
                     params)


def _entry(symbol: str, tf: str, rule: str, side: str, slot: str) -> M.Variant:
    filt = "F0" if slot == "F0" else F2_SLOT[tf]
    params = {"rule": rule, "side": side, "filter": filt, "filter_slot": slot, "kind": "state", "stop": "none"}
    return M.Variant(f"{symbol}|{tf}|{ENTRY}|{rule}|{side}|{filt}", symbol, tf, SCRIPT, ENTRY, True, "control",
                     params)


def variants(symbol: str) -> List[M.Variant]:
    """
    EXACTLY PREREG 6.8's rows of ``symbol``: on XAUUSDm and BTCUSDm 54 HA-MANAGED rows (the nine ``bases`` in the
    plan's order, each with M1, M2, M3, M4, M5, HA-AND) and 24 HA-ENTRY rows (1H, 4H, 1D x HA-H1, HA-H2 x LS, LO x
    F0, F2), every one eligible; none on the claim markets (PREREG 8 checks no Heikin Ashi claim there). Raises for a
    symbol that is not the study's.
    """
    if symbol not in M.ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(M.ALL_SYMBOLS)})")
    if symbol not in M.SYMBOLS:
        return []
    out = [_managed(symbol, b, o) for b in bases(symbol) for o in OVERLAYS]
    out += [_entry(symbol, tf, rule, side, slot) for tf in TFS for rule in ENTRY_RULES for side in SIDES
            for slot in FILTER_SLOTS]
    return out


_CANON: Dict[str, Dict[str, M.Variant]] = {}


def _canonical(symbol: str) -> Dict[str, M.Variant]:
    if symbol not in _CANON:
        vs = variants(symbol)
        table = {v.id: v for v in vs}
        if len(table) != len(vs):
            raise AssertionError("duplicate ids in the Heikin Ashi grid")
        _CANON[symbol] = table
    return _CANON[symbol]


def _row(variant: M.Variant) -> M.Variant:
    v = _canonical(variant.symbol).get(variant.id) if variant.symbol in M.SYMBOLS else None
    if v is None or (v.tf, v.family, v.script) != (variant.tf, variant.family, variant.script):
        raise ValueError(f"{variant.id}: not a row of PREREG 6.8 (tradeiq2_rules_ha.variants)")
    return v


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The ``tradeiq2_market.Exec`` of one row of ``variants`` (looked up by its id; the settings are the canonical
    row's): ``managed_exec`` for HA-MANAGED, ``entry_exec`` for HA-ENTRY. The Exec's label is the id."""
    v = _row(variant)
    if v.symbol != ctx.symbol:
        raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
    p = dict(v.params)
    if v.family == ENTRY:
        return entry_exec(ctx, v.tf, p["rule"], p["side"], p["filter"], label=v.id)
    return managed_exec(ctx, p["base"], p["overlay"], label=v.id)


def base_of(variant: M.Variant) -> Optional[str]:
    """The id of the row an HA-MANAGED row is paired with (PREREG 6.8: "each is paired with its base rule over the same
    windows"): study 1's finalist (its ``grid.csv`` / ``results_dev_val.csv`` id) or this study's RIB row; None for an
    HA-ENTRY row (it has no base)."""
    v = _row(variant)
    return str(v.params["base"]) if v.family == MANAGED else None


_RIB_ROWS: Dict[str, Dict[str, M.Variant]] = {}


def _rib_row(base: str) -> M.Variant:
    sym = base.split("|")[0]
    if sym not in _RIB_ROWS:
        _RIB_ROWS[sym] = {v.id: v for v in R.variants(sym)}
    return _RIB_ROWS[sym][base]


def describe(variant: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    v = _row(variant)
    p = dict(v.params)
    if v.family == ENTRY:
        how = ENTRY_WORDS[(p["rule"], p["side"])]
        return (f"Heikin Ashi entry control {p['rule']} (LunqFX's candles and phases with the script's defaults) on "
                f"{v.tf} bars of the bid (UTC), a state rule: {how}; filter: {FILTER_WORDS[p['filter']]} (a state "
                "filter: the position closes when it turns against it); no stop. Decided at the bar's close, filled "
                "at the open of the next M1 bar (a buy at the ask, a sell at the bid)")
    base = p["base"]
    btxt = R.describe(_rib_row(base)) if _is_rib(base) else T1.rule_text(base)
    return (f"Heikin Ashi management {OVERLAY_WORDS[p['overlay']]}; Heikin Ashi (LunqFX, the script's defaults) on the "
            f"base's {v.tf} bars; a long reacts to bullish candles' events, a short to bearish ones; after a Heikin "
            f"Ashi exit or a stop the base stays flat until its own state changes. The base ({base}): {btxt}")


def warm(ctx: M.Context, variants_: Sequence[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, every array the given rows read: the Heikin Ashi
    series, the overlays and the colour gate, study 1's lines, states and S1, the ribbon bases' flips and filters, and
    the entry rows' states (with their filters)."""
    for v in variants_:
        v = _row(v)
        p = dict(v.params)
        if v.symbol != ctx.symbol:
            raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
        ha_of(ctx, v.tf)
        if v.family == ENTRY:
            entry_state(ctx, v.tf, p["rule"], p["side"], p["filter"])
            continue
        base, ov = p["base"], p["overlay"]
        if ov == "HA-AND":
            colour_gate(ctx, v.tf)
        else:
            overlay_arrays(ctx, v.tf, ov)
        if _is_rib(base):
            R.warm(ctx, [_rib_row(base)])
        else:
            study1_state(ctx, base)
            study1_stop(ctx, base)


def plan_counts(symbol: str) -> Dict[Tuple[str, bool], int]:
    """The rows ``variants(symbol)`` gives per (family, eligible), for the grid check."""
    out: Dict[Tuple[str, bool], int] = {}
    for v in variants(symbol):
        out[(v.family, bool(v.eligible))] = out.get((v.family, bool(v.eligible)), 0) + 1
    return out
