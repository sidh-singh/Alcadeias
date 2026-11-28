"""
Session Hunter [TradeIQ] as rules (study 2, PREREG 6.6 and claim 10 of section 8): the rule rows of the session
module for the driver (``tradeiq2.py``), ``variants(symbol)`` and ``build(variant, ctx)``.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_session as R
    mk = M.load("XAUUSDm", end="2024-07-01")
    ctx = M.Context(mk)
    vs = R.variants("XAUUSDm")             # 118 rows: 116 eligible + 2 Monday-variant rows (information only)
    ex = R.build(vs[0], ctx)               # a tradeiq2_market.Exec (EVENTS; LANES for the presets)
    res = M.run_variant(ctx, vs[0], ex)    # Development, Validation and D+V at x1.0 and x1.5

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen; read with ``DEVIATIONS.md``): sections 4 (execution,
the rules for absolute levels, Session Hunter's lanes), 5 (filters, and how they apply), 6.6 (the rows), 7 (families,
eligibility) and claim 10 of section 8 (the claim-check rows). The signals are the reconciled port
``tradeiq2_ind_session`` (port A, equal bit for bit to port B on the study's M5 / M15 bars of both symbols and on the
claim markets; ``backtest_results/tradeiq_2027/porting/session.md``), the filters ``tradeiq2_filters`` and the
execution ``tradeiq2_market`` (study 1's fills, stops, marks and scores). Nothing is tuned: every input is the
script's default (L50-82) unless the plan says otherwise. Line numbers L... are those of the owner's plain-text copy of
"Session Hunter [TradeIQ]" (Pine v6, MPL-2.0, 535 lines; third-party code, cited here, never copied).

The grid
--------
XAUUSDm and BTCUSDm, each (PREREG 6.6 "Grids"; 116 + 2 rows):

=============================================================================== ===== ===============================
rows                                                                             n     eligible
=============================================================================== ===== ===============================
core: AS, LS, PD, AB, OR x K1, K2, K3 x E1, E2 x M5, M15                         60    yes
K0 x E1: the five setups x M5, M15                                               10    yes
K2 x E3: the five setups x M5, M15                                               10    yes
presets as lane portfolios, x M5, M15: Custom (AS + LS, K2, E1), Forex (AS, K3,   6    yes
E1), Nasdaq (LS + PD, K2, E1)
K2 x E1 with the 1H EMA200 replaced by F2-4H, F2-1D or F3: five setups x M5, M15  30    yes
the Monday variant (Monday gets Friday's levels): PD x K2 x E1 x M5, M15           2    no ("information only")
=============================================================================== ===== ===============================

The claim-check rows (PREREG 8 claim 10; information only, eligible=False): USTECm the Nasdaq preset and PD + HTF on
M5 and M15 (4 rows), EURUSDm and GBPUSDm the Forex preset on M15 (1 row each).

Ids (``|``-separated tokens; the driver pairs rows by swapping one token, e.g. E1 -> E2 / E3):
``symbol|tf|SH|setup|K|E`` (core, K0 x E1, K2 x E3; ``USTECm|tf|SH|PD|HTF|E1`` for PD + HTF),
``symbol|tf|SH|setup|K2|E1|F`` with F in F2-4H, F2-1D, F3 (the trend replaced),
``symbol|tf|SH|PRESET-CUSTOM|K2|E1``, ``...|PRESET-FOREX|K3|E1``, ``...|PRESET-NASDAQ|K2|E1``,
``symbol|tf|SH|PD|K2|E1|MON-FRI`` (the Monday variant). Family and script: SH.

What a row does (an EVENT rule, one lane per setup)
---------------------------------------------------
* SIGNAL. ``tradeiq2_ind_session.session_hunter`` on the chart bars (``ctx.bars('M5' | 'M15')``, the bid OHLC, New York
  clock with daylight saving, the day key = the New York date of time + 4h, L127-140). Five setups, each with its own
  state, at most one signal per setup and trading day (the ``done`` flag, L331-358): AS fades a sweep of the Asia range
  (20:00-24:00) in 02:00-05:00; LS fades a sweep of the London range (02:00-05:00) in 07:00-11:00; PD fades a sweep of
  the previous weekday's high / low in 02:00-11:00, never on Mondays (the quirk: Monday's ``pWk`` is false, L199,
  L362); AB follows a close outside the Asia range in 02:00-05:00; OR follows a close outside 09:30-10:00 in
  10:00-12:00. A fade signals at the first close back inside after a sweep that passes the confirmations; a bar that
  fails them does not end the setup (L342-346). A breakout signals at the first close outside that passes them, and
  only if it is within 4 ATR of the range's middle (L353-357).
* CONFIRMATIONS (``f_conf``, L312-328): K0 none, K1 FVG, K2 FVG + HTF (the script's default, L57-59), K3 FVG + MSS (its
  Forex preset, L105-107); the claim row "PD + HTF" is HTF alone. HTF = the chart close on the trade's side of the 1H
  EMA200 of the last 1H bar CLOSED AT OR BEFORE THE CHART BAR'S OPEN (L145, ``request.security(.., ema[1],
  lookahead_on)``; PREREG 6.6; the port's ``htf_ema_dir`` on the market's own 1H bars from its data start).
* TREND REPLACED (the 30 rows "K2 x E1 with the 1H EMA200 replaced by F2-4H, F2-1D or F3"): the HTF confirmation
  reads the filter's side instead, ``allow_long - allow_short`` of ``tradeiq2_filters.allow`` at the signal bar's
  close: F2-4H / F2-1D the last CLOSED 4H / 1D bar's close against its MA200, F3 the TSI(5, 25) of the last closed 1H
  bar (PREREG 5). It sits where the EMA sat, inside ``f_conf``: like the EMA, a bar it refuses does not end a fade
  setup, and a breakout waits for a close it allows (reading 5).
* ENTRY. At the market: decided at the signal bar's close, filled at the open of the first M1 bar at or after it (a
  buy at the ask, a sell at the bid; PREREG 4). That M1 bar opens the chart's entry bar (the next chart bar), whose
  bid open is the script's entry ``e`` (L431). The script's own cancels at entry are applied (L427-439, "as coded"): no
  trade when the entry bar opens 16:00-20:00 New York or starts a new trading day, when its bid open is at or beyond
  the stop, and for E3 when the target is less than 1R from that open (reading 4). PREREG 4's rules on the actual
  fill apply on top (the harness drops an entry whose fill is at or beyond its stop or its target).
* STOP. The port's absolute level: the sweep's extreme for a fade (the highest high / lowest low beyond the range
  since the window opened), the range's middle for a breakout, moved to 0.5 ATR(14) from the SIGNAL close when it is
  nearer (L399-402). The harness sets it as a distance |fill - level| from the actual fill (PREREG 4), so it is at
  the level itself; every stop fill is charged one extra spread.
* EXITS (the script's order, L452-461: a new trading day, the 16:00 bar, the stop, the target; the time exits apply
  to every mode):
  - E1, "Hold to 16:00 NY" (L80, the default): the stop, or the time exit, priced where the script prices it
    (reading 1): the open of the first chart bar from 16:00 New York (after an early close that reopens before 20:00,
    the reopen's open), or, when a new trading day comes first, the last close before it (the harness's
    ``close_gap``);
  - E2, "At TP2": also a target 2R from the fill (2 x |fill - stop|; reading 2);
  - E3, "Opposite liquidity": also a target at the port's ``tgt_ref`` (L403): the opposite side of the swept range for
    a fade, the broken side plus one range width for a breakout (reading 3), as an absolute level (|fill - level|
    from the fill); the trade is cancelled when it is less than 1R away (L437, reading 4).
  A target is a limit touched inside an M1 bar; a bar touching the stop and the target exits at the stop (PREREG 4).
* LANES. A setup row is one lane (one position at a time; the next signal is the next day's, so "busy" never
  happens). A preset row is ``tradeiq2_market.lanes_exec`` of its setups' lanes, summed, with the multi-position
  account (PREREG 4): Custom AS + LS (L50-51, the inputs' defaults), Nasdaq LS + PD (L100-104), Forex AS (one lane).
* MONDAY VARIANT (information only): PD x K2 x E1 with the port's ``monday_friday_levels=True`` (Monday trades the
  levels of the last finished weekday, Friday's; porting/session.md, reading 2 of its section 8).

What is known when (no look-ahead)
----------------------------------
A signal of bar i reads the chart bars 0 .. i (the session levels are final before their windows open: Asia at
00:00, London at 05:00, the opening range at 10:00, yesterday's levels from 20:00), the 1H EMA of 1H bars closed by
bar i's OPEN (up to an hour old) or, in the trend rows, the 4H / 1D / 1H bars closed by bar i's CLOSE. The cancels
read the entry bar's open time and bid open, which are those of the fill's own M1 bar. The time exit reads the clock:
the decision is booked at the close of the bar before the exit bar and filled at that bar's first M1 open, the moment
its open time is known. A new-day exit is priced as the script prices it (L454-455), at the close of the last bar
before the gap that always precedes it here: a price known at that close, while the fact that no bar of that trading
day would open from 16:00 to 20:00 is known only at the reopen. The booking takes it as known, as the script's own
price does: from the published hours for the early closes; a hole in the data (BTC's of 2-3 Mar 2021) could not be
known then. Nothing else reads it (the stop and a target act up to that close, and the
next entry of the lane is the next trading day's, after the reopen). Stops and targets are levels fixed at the fill.
Removing the bars after bar T changes no entry decided before T, and no exit decision before T (tested; nor whether
it is a new-day exit).

Readings where the plan leaves a choice (deviation paragraphs, for DEVIATIONS.md)
--------------------------------------------------------------------------------
1. THE TIME EXIT, PRICED WHERE THE SCRIPT PRICES IT. The script exits at the open of the first bar from 16:00
   (L456-457) or, on a new trading day, at the previous bar's close (L454-455), whichever comes first after the entry
   bar (a new day first when both hold, the Sunday reopen). Here both are an exit decision at the close of the bar
   before that bar (``exit_bar``, ``time_exits``), and each is priced as the script prices it:
   - the 16:00 exit fills at the next M1 open, the open of the script's first bar from 16:00: normally the 16:00
     bar's; after an early close that reopens before 20:00 on the same trading day (gold's US holidays, closed from
     about 13:00 to 18:00 New York) the reopen's, the trade held over the break as the script holds it;
   - the new-day exit is booked at the previous bar's close. A new trading day comes first only when no bar of the
     entry's trading day opens from 16:00 to 20:00 (an entry bar opens before 16:00: one from 16:00 is cancelled): an
     early close into a weekend or a closed day (the Friday after Thanksgiving, 3 July 2020, 24 and 31 December), a
     hole in the data. The reopen then usually opens at 18:00 of a later day, both a new day and from 16:00, and the
     new day is checked first (L454 before L456): 22 of the 30 flagged Development K2 x E1 trades. So a gap always
     precedes it, and the row's ``close_gap`` (``time_exit_new_day``; the harness's reading 15) books it
     at the close of that bar's last M1 bar (the bid for a long, the ask for a short, no extra spread), not at the
     first M1 bar after the gap.
   A stop or a target touched before then exits as usual; on days without a gap nothing differs. Every exit mode has
   it (E2, E3 too), as in the script. Not taken: ``close_gap`` on every time exit, which would also book the US
   holidays at the last close before the break, where the script holds to the reopen's open.
2. E2'S 2R FROM THE FILL. The 2R target is 2 x the trade's own initial risk |fill - stop| from its fill (the harness's
   ``target_r``; R as DEVIATIONS 9), as the ribbon's and Wyckoff's R targets. The script draws TP2 from the chart's
   bid open (L436: ``open + d * 2 * risk``): the same level for a short (a sell fills at the bid), three spreads
   further for a long.
3. E3 FOR BREAKOUTS. A breakout has no swept range: E3's target is the script's ``tgtRef`` there, the broken side
   plus one range width (L403), "as coded".
4. THE CANCELS ARE THE SCRIPT'S, ON ITS BID OPEN. The port's ``cancelled`` (closeT, new day, risk <= 0, the open at or
   beyond the stop) and E3's "less than 1R away" (``exit_reason_liq == 'cancel_lt_1R'``) are measured as the script
   measures them, from the entry bar's bid open with risk = |open - stop| (L431-439; porting/session.md, reading 3 of
   its section 8). For a long whose bid open is at or below the stop while the ask is above it, the script cancels and
   PREREG 4's rule alone would not. PREREG 4's rules on the actual fill apply on top.
5. THE TREND ROWS REPLACE THE CONFIRMATION, THEY DO NOT GATE THE ENTRY. "With the 1H EMA200 replaced by F2-4H, F2-1D
   or F3" is read literally: the filter's side takes the HTF confirmation's place in ``f_conf`` (L319), evaluated at
   the signal bar's close (PREREG 5's higher-timeframe values: the last CLOSED 4H / 1D / 1H bar). The other reading,
   PREREG 5's event gate after the fact (FVG alone in ``f_conf``, the filter checked at the signal's close), would
   lose the day whenever it refused, because the script's setup is done at its first signal; here, as with the EMA, a
   refused bar does not end the setup and a later bar of the same window may still signal (tested).
6. THE MONDAY VARIANT is PD x K2 x E1 on M5 and M15 (two rows per symbol): the script's default confirmations and exit
   on the only setup the quirk touches (no planned row uses YC). Eligible False, information only.
7. THE CLAIM ROWS. "PD + HTF" (claim 10: "a previous-day sweep with the 1H trend held to the close") is the PD setup
   with the HTF confirmation alone (no FVG), E1. The plan names no E2 / E3 rows on the claim markets, so there are
   none; "E1 against E2 and E3" is read on gold's and BTC's grid. USTECm's EMA has the 1H bars from its data start
   (2020-06-01), 484 of them before its Development start.
8. THE FOREX PRESET has one setup, so its one lane gives the trades of the core row AS x K3 x E1 exactly (identical
   scores; the plan numbers both, and both are kept).
9. NO VOLUME is read: the relative-volume confirmation (RV) is in no planned row.

Inputs never change: the script's defaults (min stop 0.5 ATR, TP2 = 2R, ATR(14), FVG over the last four three-bar
groups, MSS over the five bars before, EMA length 200 on the 60-minute chart).
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import tradeiq2_ind_session as SH
from . import tradeiq2_market as M

__all__ = ["MODULE", "SCRIPT", "FAMILY", "TFS", "TF_MIN", "SETUPS", "CONF_SETS", "EXITS", "TREND_EMA", "TREND_FILTERS",
           "PRESETS", "PRESET_TOKEN", "TARGET_R", "MONDAY_TOKEN", "CLAIM_ROWS", "variants", "build", "describe", "warm",
           "plan_counts", "trend_dir", "signal_table", "time_exits", "time_exit_new_day", "lane_mask", "lane_entries",
           "lane_exec", "event_table"]

MODULE = "tradeiq2_rules_session"           # the Context cache's module key
SCRIPT = "SH"
FAMILY = "SH"                               # PREREG 7's family of every row of this module
TFS = ("M5", "M15")                         # PREREG 6.6
TF_MIN = {"M5": 5, "M15": 15}
SETUPS = SH.SETUPS                          # ('AS', 'LS', 'PD', 'AB', 'OR'): the script's order (L360-364)
# the confirmation sets of PREREG 6.6 (and claim 10's "PD + HTF")
CONF_SETS: Dict[str, Tuple[str, ...]] = {"K0": (), "K1": ("FVG",), "K2": ("FVG", "HTF"), "K3": ("FVG", "MSS"),
                                         "HTF": ("HTF",)}
EXITS = ("E1", "E2", "E3")                  # hold to 16:00 / the 2R target / the opposite liquidity
TREND_EMA = "EMA200-1H"                     # the script's own 1H trend (L145)
TREND_FILTERS = ("F2-4H", "F2-1D", "F3")    # PREREG 6.6: the 30 rows with the 1H EMA200 replaced
TRENDS = (TREND_EMA,) + TREND_FILTERS
TARGET_R = float(SH.TP2_R)                  # E2: tp2 = 2.0 R (L78)
# the script's presets (L93-112): setups in the script's order, the confirmation set; all hold to 16:00 (E1)
PRESETS: Dict[str, Tuple[Tuple[str, ...], str]] = {"Custom": (("AS", "LS"), "K2"), "Forex": (("AS",), "K3"),
                                                   "Nasdaq": (("LS", "PD"), "K2")}
PRESET_TOKEN = {"Custom": "PRESET-CUSTOM", "Forex": "PRESET-FOREX", "Nasdaq": "PRESET-NASDAQ"}
MONDAY_TOKEN = "MON-FRI"                    # the Monday variant: Monday gets Friday's levels
# PREREG 8 claim 10 (information only): (tf, preset or setup, confirmation set)
CLAIM_ROWS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "USTECm": (("M5", "Nasdaq", "K2"), ("M15", "Nasdaq", "K2"), ("M5", "PD", "HTF"), ("M15", "PD", "HTF")),
    "EURUSDm": (("M15", "Forex", "K3"),),
    "GBPUSDm": (("M15", "Forex", "K3"),),
}
INFO_MONDAY = "information only (PREREG 6.6: the variant that gives Monday Friday's levels)"
INFO_CLAIM = "information only (PREREG 8 claim 10: a claim-check market)"

SETUP_WORDS = {
    "AS": "AS, the Asia sweep: a sweep of the Asia range (20:00-24:00 New York) faded in 02:00-05:00",
    "LS": "LS, the London sweep: a sweep of the London range (02:00-05:00) faded in 07:00-11:00",
    "PD": "PD, the previous-day sweep: a sweep of the previous weekday's high or low faded in 02:00-11:00",
    "AB": "AB, the Asia breakout: a close outside the Asia range followed in 02:00-05:00",
    "OR": "OR, the opening-range breakout: a close outside 09:30-10:00 followed in 10:00-12:00",
}
CONF_WORDS = {
    "K0": "no confirmation (K0)",
    "K1": "a fair value gap in the trade's direction in the last four three-bar groups (K1: FVG)",
    "K2": "a fair value gap and the close on the trade's side of the 1H EMA200 (K2: FVG + HTF, the script's default)",
    "K3": "a fair value gap and the close beyond the five bars before (K3: FVG + MSS, the Forex preset)",
    "HTF": "the close on the trade's side of the 1H EMA200 alone (claim 10's PD + HTF)",
}
TREND_WORDS = {
    TREND_EMA: "the 1H EMA200 of the last 1H bar closed at the chart bar's open (the script's)",
    "F2-4H": "the last closed 4H bar's side of its MA200 (F2-4H, in place of the 1H EMA200)",
    "F2-1D": "the last closed 1D bar's side of its MA200 (F2-1D, in place of the 1H EMA200)",
    "F3": "the TSI(5, 25) of the last closed 1H bar on the trade's side of 0 (F3, in place of the 1H EMA200)",
}
TIME_WORDS = ("the open of the first bar from 16:00 New York (after an early close that reopens before 20:00, the "
              "reopen's), or the last close before a new trading day when that comes first (an early close into a "
              "weekend or a closed day)")
EXIT_WORDS = {
    "E1": f"the stop, else the time exit: {TIME_WORDS}",
    "E2": f"a target 2R from the fill (2 x |fill - stop|), the stop, else the time exit: {TIME_WORDS}",
    "E3": ("a target at the opposite liquidity (a fade: the far side of the swept range; a breakout: the broken side "
           "plus one range width), cancelled when less than 1R from the entry open; the stop; else the time exit: "
           f"{TIME_WORDS}"),
}


def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _check_tf(tf: str) -> None:
    if tf not in TFS:
        raise ValueError(f"{tf}: Session Hunter's rules run on {', '.join(TFS)} (PREREG 6.6)")


def _check_conf(conf: str, trend: Optional[str]) -> Optional[str]:
    if conf not in CONF_SETS:
        raise ValueError(f"{conf}: one of {', '.join(CONF_SETS)}")
    if "HTF" in CONF_SETS[conf]:
        trend = TREND_EMA if trend is None else trend
        if trend not in TRENDS:
            raise ValueError(f"{trend}: the HTF confirmation reads one of {', '.join(TRENDS)}")
        return trend
    if trend not in (None, "none"):
        raise ValueError(f"{conf} has no HTF confirmation, so no trend ({trend}) is read")
    return None


# ───────────────────────────── the indicator arrays (cached in the Context) ─────────────────────────────

def _clock(ctx: M.Context, tf: str) -> Mapping[str, np.ndarray]:
    """The script's New York clock of the chart bars (``tradeiq2_ind_session.clock``: minute, day key, weekday, new
    day, the sessions, closeT; L127-140), read-only, cached."""
    _check_tf(tf)
    return ctx.get(MODULE, tf, {"series": "clock"},
                   lambda: {k: _ro(v) for k, v in SH.clock(ctx.bars(tf).t, TF_MIN[tf]).items()})


def trend_dir(ctx: M.Context, tf: str, trend: str = TREND_EMA) -> np.ndarray:
    """
    The direction the HTF confirmation compares with (L319), per chart bar of ``tf`` (int8, +1 / -1 / 0), read-only,
    cached: ``trend=TREND_EMA`` the script's own, ``tradeiq2_ind_session.htf_ema_dir`` = sign(chart close - the 1H
    EMA200 of the last 1H bar closed at or before the chart bar's OPEN), on ``ctx.bars('1H')`` (study 1's 1H bars from
    the market's data start; porting reading R7); ``'F2-4H'`` / ``'F2-1D'`` / ``'F3'`` ``allow_long - allow_short`` of
    ``tradeiq2_filters.allow`` (the last CLOSED 4H / 1D bar's MA200 side, the last closed 1H bar's TSI, each at the
    chart bar's close). 0 (no side) fails both sides, as a missing EMA does in the script.
    """
    _check_tf(tf)
    if trend not in TRENDS:
        raise ValueError(f"{trend}: one of {', '.join(TRENDS)}")

    def make():
        b = ctx.bars(tf)
        if trend == TREND_EMA:
            d = SH.htf_ema_dir(b.t, b.c, ctx.bars("1H"))
        else:
            al, ash = ctx.allow(tf, trend)
            d = np.asarray(al, np.int8) - np.asarray(ash, np.int8)
        d = np.asarray(d, np.int8)
        if d.shape != (len(b),):
            raise AssertionError(f"the {trend} direction has shape {d.shape}, the bars {len(b)}")
        return _ro(d)
    return ctx.get(MODULE, tf, {"series": "trend", "trend": trend}, make)


def signal_table(ctx: M.Context, tf: str, conf: str = "K2", trend: Optional[str] = None,
                 monday: bool = False) -> Mapping[str, np.ndarray]:
    """
    Every signal of the five setups on ``ctx.bars(tf)`` for one confirmation set (``CONF_SETS``), its trend (the HTF
    sets only; default the script's EMA) and the Monday variant (``monday``): the port's table as read-only arrays
    (cached). Each setup is its own lane in the port (switching one off changes nothing in the others), so one run
    serves every setup. Keys: ``setup`` (index into SETUPS), ``bar``, ``dir``, ``stop``, ``tgt_ref``, ``r_hi``,
    ``r_lo``, ``entry_bar``, ``cancel`` (the port's ``cancelled``: '' when none), ``e3_cancel`` (E3's own cancel, the
    target less than 1R from the entry bar's bid open: ``exit_reason_liq == 'cancel_lt_1R'``), ``day_key`` (the
    script's trading day of the signal bar). The port's own exit columns (cost 0, the chart's bid) are not kept: every
    scored number comes from the harness.
    """
    _check_tf(tf)
    trend = _check_conf(conf, trend)

    def make():
        b = ctx.bars(tf)
        hd = trend_dir(ctx, tf, trend) if trend is not None else None
        df = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, None, TF_MIN[tf], hd, setups=SETUPS, conf=CONF_SETS[conf],
                               monday_friday_levels=bool(monday))
        code = {s: i for i, s in enumerate(SETUPS)}
        bar = df["bar"].to_numpy(np.int64)
        dk = _clock(ctx, tf)["day_key"]
        out = {"setup": np.asarray([code[s] for s in df["setup"]], np.int8),
               "bar": bar, "dir": df["dir"].to_numpy(np.int64), "stop": df["stop"].to_numpy(np.float64),
               "tgt_ref": df["tgt_ref"].to_numpy(np.float64), "r_hi": df["r_hi"].to_numpy(np.float64),
               "r_lo": df["r_lo"].to_numpy(np.float64), "entry_bar": df["entry_bar"].to_numpy(np.int64),
               "cancel": np.asarray(["" if x is None else str(x) for x in df["cancelled"]], dtype=object),
               "e3_cancel": (df["exit_reason_liq"] == "cancel_lt_1R").to_numpy(bool),
               "day_key": dk[bar] if len(bar) else np.zeros(0, np.int64)}
        return {k: _ro(v) for k, v in out.items()}
    return ctx.get(MODULE, tf, {"series": "signals", "conf": conf, "trend": trend or "none",
                                "monday": bool(monday)}, make)


def time_exits(ctx: M.Context, tf: str) -> np.ndarray:
    """
    Per entry bar e (0 .. len(bars); read-only, cached): the bar whose close books the script's time exit (reading
    1), i.e. j - 1 for the first chart bar j > e that opens in 16:00-20:00 New York (``closeT``, L140, L456) or starts a
    new trading day (``newDay``, L133, L454); -1 when no such bar is in the data. The script checks both only after
    the entry bar (``bar_index > T.x0``), and its cancel at entry rules them out on the entry bar itself, so the exit
    decision is never earlier than the entry bar (and always later than the signal bar). Where it is priced (the next
    M1 open, or the decision bar's last M1 close for a new-day exit): ``time_exit_new_day``.
    """
    _check_tf(tf)

    def make():
        n = len(ctx.bars(tf))
        ck = _clock(ctx, tf)
        idx = np.flatnonzero(ck["new_day"] | ck["close_t"])
        e = np.arange(n + 1, dtype=np.int64)
        if len(idx) == 0:
            return _ro(np.full(n + 1, -1, np.int64))
        pos = np.searchsorted(idx, e + 1, side="left")
        j = np.where(pos < len(idx), idx[np.minimum(pos, len(idx) - 1)], n)
        return _ro(np.where(j < n, j - 1, -1).astype(np.int64))
    return ctx.get(MODULE, tf, {"series": "time_exit"}, make)


def time_exit_new_day(ctx: M.Context, tf: str) -> np.ndarray:
    """
    Per entry bar e (0 .. len(bars), aligned with ``time_exits``; read-only, cached): True when the script prices that
    time exit at the previous bar's close, i.e. the bar after the decision bar starts a new trading day (``newDay``,
    L454-455; checked before ``closeT``, so also on a Sunday reopen that opens in 16:00-20:00). That is the row's
    ``close_gap`` (reading 1): across the gap before that bar the exit is booked at the decision bar's last M1 close.
    False when that bar opens in 16:00-20:00 of the same trading day (``closeT``, L456-457: priced at its open, the
    next M1 open after the decision, after an early close too) and when there is no time exit (-1). Known at that
    bar's open, like the exit decision itself.
    """
    _check_tf(tf)

    def make():
        xb = time_exits(ctx, tf)
        nd = _clock(ctx, tf)["new_day"]
        out = np.zeros(len(xb), np.bool_)
        has = xb >= 0
        out[has] = nd[xb[has] + 1]          # the bar the script exits on: xb + 1 < len(bars) whenever xb >= 0
        return _ro(out)
    return ctx.get(MODULE, tf, {"series": "time_exit_new_day"}, make)


# ───────────────────────────── one lane: the entries of one setup ─────────────────────────────

def lane_mask(sig: Mapping[str, np.ndarray], setup: str, exit: str) -> Tuple[np.ndarray, Dict[str, int]]:
    """The signal rows a lane takes to the harness: those of ``setup`` that the script does not cancel at entry
    (``cancel`` empty), and for E3 also not cancelled by its "less than 1R away" (reading 4). Returns the mask and the
    counts (signals, cancelled at entry, E3 cancels, kept)."""
    if setup not in SETUPS:
        raise ValueError(f"{setup}: one of {', '.join(SETUPS)}")
    if exit not in EXITS:
        raise ValueError(f"{exit}: one of {', '.join(EXITS)}")
    sel = sig["setup"] == SETUPS.index(setup)
    canc = sel & (sig["cancel"] != "")
    keep = sel & ~canc
    e3 = keep & sig["e3_cancel"] if exit == "E3" else np.zeros(len(sel), bool)
    keep &= ~e3
    return keep, {"signals": int(sel.sum()), "cancelled": int(canc.sum()), "e3_cancelled": int(e3.sum()),
                  "kept": int(keep.sum())}


def lane_entries(ctx: M.Context, tf: str, setup: str, conf: str, exit: str, trend: Optional[str] = None,
                 monday: bool = False) -> M.Entries:
    """
    The market entries of one setup (one lane): per kept signal (``lane_mask``), decided at the signal bar's close,
    side = the signal's, ``stop_level`` = the port's stop (an absolute level; the harness measures it from the fill),
    ``exit_bar`` = the time exit (``time_exits`` of the entry bar), ``close_gap`` = whether it is a new-day exit
    (``time_exit_new_day``: booked at the last M1 close before the gap that precedes it; reading 1), E2 ``target_r`` =
    2, E3 ``target_level`` = the port's ``tgt_ref``; ``tag`` = the setup's index in SETUPS. At most one entry per
    trading day (asserted).
    """
    sig = signal_table(ctx, tf, conf, trend, monday)
    keep, _ = lane_mask(sig, setup, exit)
    k = np.flatnonzero(keep)
    dk = sig["day_key"][k]
    if len(np.unique(dk)) != len(dk):
        raise AssertionError(f"{setup} on {tf}: two signals on one trading day (the script's done flag)")
    n = len(ctx.bars(tf))
    eb = np.minimum(sig["entry_bar"][k], n)
    xb = time_exits(ctx, tf)[eb]
    kw = {}
    if exit == "E2":
        kw["target_r"] = TARGET_R
    elif exit == "E3":
        kw["target_level"] = sig["tgt_ref"][k]
    return M.entries(sig["bar"][k], sig["dir"][k], stop_level=sig["stop"][k], exit_bar=xb,
                     tag=SETUPS.index(setup), close_gap=time_exit_new_day(ctx, tf)[eb], **kw)


def lane_exec(ctx: M.Context, tf: str, setup: str, conf: str, exit: str, trend: Optional[str] = None,
              monday: bool = False, label: str = "") -> M.Exec:
    """The EVENTS Exec of one setup's lane (``lane_entries``): one position at a time, no other overlay."""
    return M.event_exec(tf, entries=lane_entries(ctx, tf, setup, conf, exit, trend, monday), label=label)


# ───────────────────────────── the grid ─────────────────────────────

def _v(symbol: str, tf: str, rest: str, eligible: bool = True, info: str = "", **params) -> M.Variant:
    return M.Variant(f"{symbol}|{tf}|{SCRIPT}|{rest}", symbol, tf, SCRIPT, FAMILY, eligible, info, params)


def _params(block: str, setups: Sequence[str], conf: str, exit: str, trend: Optional[str] = None, preset: str = "",
            monday: bool = False) -> Dict[str, object]:
    """A row's settings. Lists are joined with '+' (a preset's setups 'AS+LS'), so a preset carries no single setup's
    name among its tokens (the driver reads id and params tokens: 'AS' rows are the AS rows)."""
    p: Dict[str, object] = {"block": block, "setups": "+".join(setups), "preset": preset, "conf": conf,
                            "confirmations": "+".join(CONF_SETS[conf]) or "none",
                            "trend": (trend or TREND_EMA) if "HTF" in CONF_SETS[conf] else "none", "exit": exit,
                            "monday": "friday" if monday else "quirk", "lanes": len(setups)}
    if trend in TREND_FILTERS:
        p["filter"] = trend
    return p


def _preset_row(symbol: str, tf: str, name: str, eligible: bool = True, info: str = "") -> M.Variant:
    setups, conf = PRESETS[name]
    return _v(symbol, tf, f"{PRESET_TOKEN[name]}|{conf}|E1", eligible, info,
              **_params("preset" if eligible else "claim 10", setups, conf, "E1", preset=name))


def variants(symbol: str) -> List[M.Variant]:
    """
    EXACTLY the rows of PREREG 6.6 (gold, BTC) and of claim 10 (the claim markets) for ``symbol`` (the module
    docstring's grid): 118 on XAUUSDm and on BTCUSDm (116 eligible, 2 Monday-variant rows, information only), 4 on
    USTECm, 1 on EURUSDm and 1 on GBPUSDm (information only). Order: core (timeframe, setup, K1-K3, E1-E2), K0 x E1,
    K2 x E3, the presets, the trend rows, the Monday variant. Raises for a symbol that is not the study's.
    """
    if symbol not in M.ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(M.ALL_SYMBOLS)})")
    if symbol in CLAIM_ROWS:
        out = []
        for tf, what, conf in CLAIM_ROWS[symbol]:
            if what in PRESETS:
                out.append(_preset_row(symbol, tf, what, False, INFO_CLAIM))
            else:
                out.append(_v(symbol, tf, f"{what}|{conf}|E1", False, INFO_CLAIM,
                              **_params("claim 10", (what,), conf, "E1")))
        return out
    out: List[M.Variant] = []
    for tf in TFS:
        for s in SETUPS:
            for k in ("K1", "K2", "K3"):
                for e in ("E1", "E2"):
                    out.append(_v(symbol, tf, f"{s}|{k}|{e}", **_params("core", (s,), k, e)))
    for tf in TFS:
        for s in SETUPS:
            out.append(_v(symbol, tf, f"{s}|K0|E1", **_params("K0 x E1", (s,), "K0", "E1")))
    for tf in TFS:
        for s in SETUPS:
            out.append(_v(symbol, tf, f"{s}|K2|E3", **_params("K2 x E3", (s,), "K2", "E3")))
    for tf in TFS:
        for name in PRESETS:
            out.append(_preset_row(symbol, tf, name))
    for tf in TFS:
        for s in SETUPS:
            for f in TREND_FILTERS:
                out.append(_v(symbol, tf, f"{s}|K2|E1|{f}", **_params("trend", (s,), "K2", "E1", trend=f)))
    for tf in TFS:
        out.append(_v(symbol, tf, f"PD|K2|E1|{MONDAY_TOKEN}", False, INFO_MONDAY,
                      **_params("Monday variant", ("PD",), "K2", "E1", monday=True)))
    return out


_CANON: Dict[str, Dict[str, M.Variant]] = {}


def _canonical(symbol: str) -> Dict[str, M.Variant]:
    if symbol not in _CANON:
        _CANON[symbol] = {v.id: v for v in variants(symbol)}
    return _CANON[symbol]


def _row(variant: M.Variant) -> M.Variant:
    v = _canonical(variant.symbol).get(variant.id) if variant.symbol in M.ALL_SYMBOLS else None
    if v is None or (v.tf, v.family) != (variant.tf, variant.family):
        raise ValueError(f"{variant.id}: not a row of PREREG 6.6 / claim 10 (tradeiq2_rules_session.variants)")
    return v


def _settings(v: M.Variant) -> Tuple[Tuple[str, ...], str, str, Optional[str], bool, str]:
    p = dict(v.params)
    trend = None if p["trend"] == "none" else str(p["trend"])
    return (tuple(str(p["setups"]).split("+")), str(p["conf"]), str(p["exit"]), trend, p["monday"] == "friday",
            str(p["preset"]))


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """
    The ``tradeiq2_market.Exec`` of one row of ``variants`` (looked up by its id; the settings are the canonical
    row's): a setup row is the EVENTS Exec of its lane (``lane_exec``), a preset row the LANES Exec of its setups'
    lanes (``tradeiq2_market.lanes_exec``, summed; PREREG 4). The Exec's label is the id (a lane's: id#setup).
    """
    v = _row(variant)
    if v.symbol != ctx.symbol:
        raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
    setups, conf, exit, trend, monday, preset = _settings(v)
    if not preset:
        return lane_exec(ctx, v.tf, setups[0], conf, exit, trend, monday, label=v.id)
    return M.lanes_exec([lane_exec(ctx, v.tf, s, conf, exit, trend, monday, label=f"{v.id}#{s}") for s in setups],
                        label=v.id)


def describe(variant: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    v = _row(variant)
    setups, conf, exit, trend, monday, preset = _settings(v)
    bars = f"{v.tf} bars of the bid (UTC boundaries, New York clock with daylight saving)"
    what = "; ".join(SETUP_WORDS[s] for s in setups)
    head = (f"Session Hunter's {preset} preset, one lane per setup, summed ({what})" if preset else
            f"Session Hunter's {what}")
    conf_w = CONF_WORDS[conf]
    if trend in TREND_FILTERS:
        conf_w = f"a fair value gap and {TREND_WORDS[trend]}"
    mon = (" Monday trades Friday's levels (the information-only variant of the script's Monday quirk)." if monday
           else "")
    note = f" {v.info}." if v.info else ""
    return (f"{head}, on {bars}, at most one trade a day per setup. Confirmations: {conf_w}. Entry at the open of the "
            "next M1 bar (cancelled as the script cancels: the next bar from 16:00 or a new day, its bid open at or "
            "beyond the stop); stop at the sweep's extreme (a fade) or the range's middle (a breakout), at least "
            f"0.5 ATR(14) from the signal close; exit: {EXIT_WORDS[exit]}.{mon}{note}")


def warm(ctx: M.Context, variants_: Sequence[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, every array the given rows read: the trend
    directions (the 1H EMA, the F2 / F3 filters), the signal tables, the time exits and their new-day flags."""
    for v in variants_:
        v = _row(v)
        if v.symbol != ctx.symbol:
            continue
        setups, conf, exit, trend, monday, preset = _settings(v)
        signal_table(ctx, v.tf, conf, trend, monday)
        time_exits(ctx, v.tf)
        time_exit_new_day(ctx, v.tf)


def plan_counts(symbol: str) -> Dict[Tuple[str, bool], int]:
    """The rows ``variants(symbol)`` gives per (family, eligible), for the grid check."""
    out: Dict[Tuple[str, bool], int] = {}
    for v in variants(symbol):
        out[(v.family, bool(v.eligible))] = out.get((v.family, bool(v.eligible)), 0) + 1
    return out


def event_table(ctx: M.Context, variant: M.Variant) -> pd.DataFrame:
    """Event geometry of a row for reports and checks (no profit or loss): per signal of its setups, the lane, the
    setup, the signal bar and its close time, the side, the stop and target reference, the stop distance from the
    signal close in the port's ATR(14) (at least 0.5: the minimum stop), the script's cancel at entry ('' none;
    'cancel_lt_1R' for E3's), whether the lane takes it to the harness, the time exit's decision bar (-1: none in
    the data), its kind ('closeT': the first bar from 16:00, at its open; 'new_day': the previous close; '' none) and
    the ``close_gap`` flag the lane hands the harness (True on the new-day exits; reading 1)."""
    v = _row(variant)
    if v.symbol != ctx.symbol:
        raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
    setups, conf, exit, trend, monday, preset = _settings(v)
    b = ctx.bars(v.tf)
    sig = signal_table(ctx, v.tf, conf, trend, monday)
    tx = time_exits(ctx, v.tf)
    nd = time_exit_new_day(ctx, v.tf)
    # the port's own ATR(14) (the one its minimum-stop rule reads, L143 and L401)
    atr = ctx.get(MODULE, v.tf, {"series": "atr14"}, lambda: _ro(SH.shared_series(b.h, b.l, b.c)["atr"]))
    parts = []
    for q, s in enumerate(setups):
        keep, _ = lane_mask(sig, s, exit)
        sel = np.flatnonzero(sig["setup"] == SETUPS.index(s))
        bar = sig["bar"][sel]
        cancel = np.where(sig["cancel"][sel] != "", sig["cancel"][sel],
                          np.where((exit == "E3") & sig["e3_cancel"][sel], "cancel_lt_1R", ""))
        eb = np.minimum(sig["entry_bar"][sel], len(b))
        with np.errstate(invalid="ignore", divide="ignore"):
            parts.append(pd.DataFrame({
                "vid": v.id, "lane": q, "setup": s, "bar": bar, "t_signal": pd.to_datetime(b.tc[bar], unit="s",
                                                                                         utc=True),
                "side": sig["dir"][sel], "stop": sig["stop"][sel], "tgt_ref": sig["tgt_ref"][sel],
                "stop_atr": np.abs(b.c[bar] - sig["stop"][sel]) / atr[bar], "cancel": cancel,
                "taken": keep[sel], "exit_bar": tx[eb],
                "time_exit": np.where(tx[eb] < 0, "", np.where(nd[eb], "new_day", "closeT")).astype(object),
                "close_gap": nd[eb]}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
