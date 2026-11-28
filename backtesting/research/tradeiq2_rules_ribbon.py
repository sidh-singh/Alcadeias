"""
Trend Target Ribbon (BOSWaves) as rules, and the video's "2027 chart setup" (study 2, PREREG 6.1 and 6.10): the rule
rows of the ribbon module for the driver (``tradeiq2.py``), ``variants(symbol)`` and ``build(variant, ctx)``.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_ribbon as R
    mk = M.load("XAUUSDm", end="2024-07-01")
    ctx = M.Context(mk)
    vs = R.variants("XAUUSDm")             # 163 rows: 136 RIB + 3 RIB-LIT + 6 ALMA-X + 18 STK
    ex = R.build(vs[0], ctx)               # a tradeiq2_market.Exec
    res = M.run_variant(ctx, vs[0], ex)    # Development, Validation and D+V at x1.0 and x1.5

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen; read with ``DEVIATIONS.md``): sections 4 (execution,
the rules for absolute levels, partial exits), 5 (the filters and how they apply), 6.1 (RIB, ALMA-X, RIB-LIT), 6.10
(STK) and 7 (families, eligibility). The ribbon is the reconciled port ``tradeiq2_ind_ribbon`` (port A, equal bit
for bit to port B on the study's 1H / 4H / 1D bars; ``porting/ribbon.md``), the dashboard the reconciled port
``tradeiq2_ind_msd`` (through ``tradeiq2_filters``' FS), the filters ``tradeiq2_filters`` and the execution
``tradeiq2_market`` (study 1's fills, stops, marks and scores). Nothing is tuned: every input is the script's default.
Line numbers L... are those of the owner's copy of "Trend Target Ribbon [BOSWaves]" (Pine v6, MPL-2.0, L1-776; it is
third-party code, cited here, never copied).

The grid (per symbol; XAUUSDm and BTCUSDm only, none on the claim markets)
--------------------------------------------------------------------------
============ ========== ============================================================== ===== ==========================
family       script     rows                                                            n     eligible
============ ========== ============================================================== ===== ==========================
RIB          RIB        LS, LO x X0, XT2, XP, XBE x the filters of the timeframe:      136   yes
                        1H F0 F1 F2-4H F2-1D FR F3 FS (56), 4H F0 F1 F2-1D FR F3 FS
                        (48), 1D F0 F1 F3 FS (32)
RIB          RIB        RIB-LIT: RIB-LS x X0 x F0 with the literal stop, 1H 4H 1D       3     no ("sensitivity")
ALMA-X       RIB        LS, LO x 1H 4H 1D, X0, F0 (a control)                          6     yes (controls qualify)
STK          STK        STK-RM, STK-RA, STK-RMA x LS, LO x 1H 4H 1D, stop S1            18    yes
============ ========== ============================================================== ===== ==========================

Ids: ``symbol|tf|RIB|side|exit|filter`` (e.g. ``XAUUSDm|1H|RIB|LS|XP|F2-4H``), ``symbol|tf|RIB|RIB-LIT|LS|X0|F0``,
``symbol|tf|ALMA-X|side|X0|F0``, ``symbol|tf|STK|rule|side|S1``. The driver pairs rows by swapping one token (XP ->
X0, F1 -> F0, ...; claim 1 pairs ALMA-X with the RIB row of the same side and timeframe with X0 and F0), and the Heikin
Ashi overlays (PREREG 6.8) take ``symbol|tf|RIB|LS|X0|F0`` and ``symbol|tf|RIB|LO|X0|F0`` as their bases (``rib_exec``
builds a base with the overlays added).

RIB, an event rule (PREREG 6.1): what a row does
------------------------------------------------
* SIGNAL. The ribbon's flip (``tradeiq2_ind_ribbon.ribbon(...)['flip']``): +1 on a ``bullFlip`` bar, -1 on a
  ``bearFlip`` bar (L100-114; the "Bull Trend" / "Bear Trend" alerts, L768-776). A bull setup is ``slopeScore >
  0.08 and close > alma + 0.65 dev`` (L92-98, strict), the bear setup its mirror; the trend is the side of the latest
  setup and never returns to 0; a flip is the first setup of the other side. Flips therefore alternate sides, and a
  stop-out does not reset the trend (L100-110: nothing else writes ``trend``).
* ENTRY. At the flip: a bull flip opens a long, a bear flip a short (LS); LO takes the bull flips only. Decided at the
  flip bar's close (the script's ``entryPrice := close``, L310), filled at the open of the first M1 bar at or after
  that close: a buy at the ask, a sell at the bid (PREREG 4). One trade per flip at most.
* STOP, the "intended" reading registered for every eligible row (PREREG 6.1): ``riskDist = min(max(raw, 0.75 ATR),
  3 ATR)`` with ``raw = close - lowest(low of the 12 bars before the flip bar)`` (L315-328 with the input's tooltip,
  L33-34), a missing raw giving 0.75 ATR: the port's ``risk_long`` / ``risk_short`` at the flip bar. The stop sits
  riskDist from the actual FILL and never moves (PREREG 6.1: "The stop sits riskDist from the fill"); 1R = riskDist.
  The script's ``stopPrice = entryPrice - dir * riskDist`` (L330) is drawn from the flip bar's close; PREREG 4's rule
  for absolute levels makes every level a distance from the fill, so the harness gets the distance itself
  (``stop_dist``; the x1.5 run sets it from its own fill). An entry is therefore never dropped for a fill beyond its
  stop or target (the dropped counts stay 0).
* EXITS. The opposite flip closes the trade at that bar's close (filled at the next M1 open, where the reverse entry
  of LS fills too). After a stop or a target the rule is flat until the next flip. A window starts flat and waits for
  the first flip decided inside it (the harness's event-rule edge, DEVIATIONS 3); what is open at its end closes at
  the last M1 close.
  - X0: the stop or the opposite flip (the script: a flip ends the old position, L215-277; the stop ends it on a bar
    after the entry bar whose low reaches it, L498-501; here every M1 bar from the fill on is checked, PREREG 4, so
    the old trade's stop is also checked inside the flip bar, porting/ribbon.md reading 17).
  - XT2: all out at 2R = fill + 2 riskDist (a limit touched inside an M1 bar; the stop wins a bar that touches both),
    else X0.
  - XP, the video's "take partial profit at the second target and let the rest run with the ribbon": two half-size
    legs with identical entries and the same stop, one with the 2R target, one without (X0). P/L is their sum and the
    drawdown is measured on the summed M1 marks (PREREG 4; live this needs at least 0.02 lot per unit).
  - XBE, the video's "the stop never moves ... so manage it": the stop moves to break-even (the fill) once price has
    gone 1R in favour (the bid high of a long reaches fill + 1R, the ask low of a short fill - 1R, inside an M1 bar
    after its stop and target checks; from the next M1 bar on: ``external``'s ``ber``), else X0.
  The script's four targets (L419-422) only get check marks (L620-631) and close nothing.
* FILTERS (PREREG 5, on an event rule): the filter must agree at the flip bar's close (``tradeiq2_filters.
  gate_entries``); it never closes an open trade, which keeps its own exits. So a flip the filter refuses still ends
  the trade of the other side (that is the trade's X0 exit) and opens nothing. 1H: F0, F1, F2-4H, F2-1D, FR (the
  ribbon trend of the last closed 4H bar), F3 (TSI 5/25 of the signal timeframe), FS (the dashboard's bias, model A,
  LEAN BULL or better for longs); 4H: F0, F1, F2-1D, FR (the last closed 1D bar's ribbon), F3, FS; 1D: F0, F1, F3,
  FS. The video: "take the flips in the direction of the higher time frame".

Controls
--------
* ALMA-X (PREREG 6.1, claim 1 of section 8): trend = sign(close - ALMA) with the same ALMA (L88), the same stop rule
  (the intended riskDist of the bar where the sign changes) and X0; LS and LO. It is the ribbon's trend machine with
  the slope and band conditions removed: setups ``close > alma`` / ``close < alma`` (strict), the trend the side of
  the latest setup, a flip the first setup of the other side.
* RIB-LIT (sensitivity; not eligible): RIB-LS x X0 x F0 with the stop TradingView literally computes (the port's
  ``risk_long_lit`` / ``risk_short_lit``: ``ta.lowest`` inside the flip branch buffers only the lows of earlier
  bull-flip bars, ``[1]`` is its previous execution; porting/ribbon.md readings 8-13).

STK, state rules (PREREG 6.10: "one trend tool, the ribbon; one context tool, the dashboard")
-------------------------------------------------------------------------------------------
* STK-RM: long while the signal timeframe's ribbon trend is +1 AND the dashboard's bias is LEAN BULL or BULLISH (FS);
  short in the mirror case; otherwise flat.
* STK-RA: the ribbon trend AND the higher timeframe's MA200 (1H: F2-4H; 4H: F2-1D; 1D: F1).
* STK-RMA: all three agree.
* LS and LO (LO: a short state is flat). Stop S1: 3 x ATR(14) of the signal timeframe at the decision bar, from the
  fill, fixed (PREREG 6.2; study 1's ``s1_stop``). Executed as study 1's ``run`` (an entry where the state changes,
  also after a stop; the window's first bar takes the state; the position closes where the state changes, so when
  the context turns against it).

What is known when (no look-ahead)
----------------------------------
Every decision of bar t reads bars 0 .. t of its own timeframe and, for FR, F2, FS and STK-RA, higher-timeframe bars
CLOSED at t's close (``tradeiq_market.htf_at``; the dashboard's higher rows model A). The flip and the trend use the
closes, highs and lows up to t (the port: ALMA and deviation of closes t-33 .. t, ATR to t, slope ``alma[t-3]``), the
intended stop the lows (highs) of t-12 .. t-1 and t's close and ATR, the literal stop the lows (highs) of earlier flip
bars, the opposite-flip exit the flip of the later bar where it is taken. Each decision fills at the next M1 open.
Removing the bars after t changes no decision up to t (tested on synthetic and real bars).

Readings where the plan leaves a choice (proposed for DEVIATIONS.md)
--------------------------------------------------------------------
1. A flip the filter refuses still closes the open trade of the other side (its X0 exit) and opens nothing; the
   opposite-flip exits are per-bar exit masks (every bear flip for longs, every bull flip for shorts) whatever the
   filter.
2. ALMA-X at a tie: a bar whose close equals the ALMA exactly is no setup (the trend keeps its side), as the ribbon's
   strict inequalities; before the ALMA exists there is no trend. No such tie exists on the study's 1H / 4H / 1D bars
   of either symbol from the data start to 2024-06-30 (a count), so the reading moves nothing there.
3. ALMA-X's stop: the intended riskDist of the cross bar (computed by the port at every bar).
4. The 2R target and the 1R of XBE are measured from the fill, like the stop (the script draws them from the flip
   bar's close, L621). They are touched as PREREG 4's limits are: a long's by the bid high, a short's by the ask low
   (the script's check marks, L626-629, read the bid chart for both sides).
5. XBE's break-even level is the fill; a break-even stop is charged one spread as every stop fill (PREREG 4).
6. A flip without a positive stop distance (only possible while the ATR is missing or 0, in a warm-up) opens nothing;
   none exists on the study's bars (every ribbon and ALMA-X flip of both symbols from the data start to 2024-06-30
   has one, intended and literal).
7. STK's trend is the ribbon of the signal timeframe itself (not FR's higher-timeframe ribbon), 0 (flat) before its
   first setup; LO STK makes the short states flat.
"""

from __future__ import annotations

import math
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from . import tradeiq2_filters as F
from . import tradeiq2_ind_ribbon as RB
from . import tradeiq2_market as M

__all__ = ["MODULE", "TFS", "SIDES", "EXITS", "RIB_FILTERS", "STK_RULES", "STK_MA", "variants", "build", "describe",
           "warm", "ribbon_of", "signals", "flip_entries", "flip_exits", "rib_exec", "stk_state", "stk_exec",
           "s1_stop", "side_trend", "stk_filters", "plan_counts", "flip_table"]

MODULE = "tradeiq2_rules_ribbon"            # the Context cache's module key
RIBBON_PARAMS: Dict[str, str] = {"series": "ribbon"}        # the port with the script's defaults (cache key)
TFS = ("1H", "4H", "1D")                    # PREREG 6.1 / 6.10
SIDES = ("LS", "LO")
EXITS = ("X0", "XT2", "XP", "XBE")
# PREREG 6.1 "Filters", in its order
RIB_FILTERS: Dict[str, Tuple[str, ...]] = {"1H": ("F0", "F1", "F2-4H", "F2-1D", "FR", "F3", "FS"),
                                           "4H": ("F0", "F1", "F2-1D", "FR", "F3", "FS"),
                                           "1D": ("F0", "F1", "F3", "FS")}
STK_RULES = ("STK-RM", "STK-RA", "STK-RMA")
STK_MA = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}         # PREREG 6.10: the higher timeframe's MA200
TARGET_R = 2.0                               # XT2, XP: the second target
BE_R = 1.0                                   # XBE: break-even once 1R is touched
PARTIAL = 0.5                                # XP: half out at 2R
S1_MULT = 3.0                                # STK's S1: 3 x ATR(14) from the fill (PREREG 6.2)
S1_PARAMS: Dict[str, object] = {"series": "s1", "mult": S1_MULT}  # its cache key
STOPS = ("intended", "literal")
TRENDS = ("ribbon", "alma-cross")
FAMILIES = ("RIB", "ALMA-X", "STK")          # PREREG 7's families of this module

SIDE_WORDS = {"LS": "a bull flip opens a long, a bear flip a short (the opposite flip exits and reverses)",
              "LO": "a bull flip opens a long, the next bear flip closes it (long only)"}
EXIT_WORDS = {
    "X0": "exit at the stop or at the close of the next (opposite) flip",
    "XT2": "all out at 2R (2 x riskDist from the fill), else at the stop or the next flip",
    "XP": "half out at 2R, the other half at the stop or the next flip (two half-size legs; live this needs at least "
          "0.02 lot per unit)",
    "XBE": "the stop moves to the fill (break-even) once price has gone 1R in favour; else the stop or the next flip",
}
FILTER_WORDS = {
    "F0": "no filter",
    "F1": "longs only while the close is above the MA200 of the same timeframe, shorts only while below",
    "F2-4H": "longs only while the last closed 4H bar is above its MA200, shorts only while below",
    "F2-1D": "longs only while the last closed 1D bar is above its MA200, shorts only while below",
    "FR": "the ribbon trend of the higher timeframe (1H: the last closed 4H bar; 4H: the last closed 1D bar) on the "
          "trade's side",
    "F3": "TSI(5, 25) of the signal timeframe on the trade's side of 0",
    "FS": "the Market Structure Dashboard's bias (model A) at LEAN BULL or BULLISH for longs, LEAN BEAR or BEARISH for "
          "shorts",
}
STK_WORDS = {"STK-RM": "the dashboard's bias", "STK-RA": "the higher timeframe's MA200",
             "STK-RMA": "both the dashboard's bias and the higher timeframe's MA200"}


def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _check_tf(tf: str) -> None:
    if tf not in TFS:
        raise ValueError(f"{tf}: the ribbon rules run on {', '.join(TFS)} (PREREG 6.1 / 6.10)")


# ───────────────────────────── the indicators (cached in the Context) ─────────────────────────────

def ribbon_of(ctx: M.Context, tf: str) -> Dict[str, np.ndarray]:
    """``tradeiq2_ind_ribbon.ribbon(o, h, l, c)`` of ``ctx.bars(tf)`` with the script's defaults (the bid OHLC of the
    study's bars), read-only, cached as (MODULE, symbol, tf, RIBBON_PARAMS). Every value of bar t is known at its
    close (the port's docstring)."""
    _check_tf(tf)

    def make():
        b = ctx.bars(tf)
        out = RB.ribbon(b.o, b.h, b.l, b.c)
        if tuple(out) != RB.KEYS or any(len(v) != len(b) for v in out.values()):
            raise AssertionError("the ribbon port's contract changed")
        return {k: _ro(v) for k, v in out.items()}
    return ctx.get(MODULE, tf, RIBBON_PARAMS, make)


def side_trend(up, dn) -> Tuple[np.ndarray, np.ndarray]:
    """
    The ribbon's trend machine (L100-110) on two exclusive setup series: ``trend`` (int8) is the side of the latest
    bar with a setup at or before t (+1 for ``up``, -1 for ``dn``; 0 before the first) and ``flip`` (int8) is +1 / -1
    on a setup bar whose side differs from the trend of the bar before (the ``var`` starts at 0), else 0. This is the
    closed form of ``if trend != 1 and bullSetup: trend := 1 ... else if trend != -1 and bearSetup: trend := -1``,
    equal to it when the setups never hold together (refused here). Causal: bar t reads the setups up to t.
    """
    up, dn = np.asarray(up, bool), np.asarray(dn, bool)
    if up.shape != dn.shape or up.ndim != 1:
        raise ValueError("up and dn must be 1-D series of one length")
    if np.any(up & dn):
        raise ValueError(f"both setups hold at bar {int(np.flatnonzero(up & dn)[0])}")
    n = len(up)
    side = np.where(up, 1, np.where(dn, -1, 0)).astype(np.int8)
    last = np.maximum.accumulate(np.where(side != 0, np.arange(n), -1)) if n else np.zeros(0, np.int64)
    trend = np.where(last >= 0, side[np.maximum(last, 0)], 0).astype(np.int8)
    before = np.zeros(n, np.int8)
    before[1:] = trend[:-1]
    flip = np.where((side != 0) & (side != before), side, 0).astype(np.int8)
    return trend, flip


def signals(ctx: M.Context, tf: str, trend: str = "ribbon") -> Dict[str, np.ndarray]:
    """
    The trend and the flips a rule trades, per bar of ``tf``, read-only:

    * ``trend='ribbon'``: the ribbon's own ``trend`` and ``flip`` (RIB, RIB-LIT, STK);
    * ``trend='alma-cross'``: ALMA-X's, ``side_trend(close > alma, close < alma)`` with the ribbon's ALMA(34, 0.85, 6)
      of the close (L88; NaN before bar 33 compares False, so no trend before it). Also ``up`` / ``dn``.
    """
    if trend not in TRENDS:
        raise ValueError(f"{trend}: one of {', '.join(TRENDS)}")
    r = ribbon_of(ctx, tf)
    if trend == "ribbon":
        return {"trend": r["trend"], "flip": r["flip"]}

    def make():
        c = ctx.bars(tf).c
        with np.errstate(invalid="ignore"):
            up, dn = c > r["alma"], c < r["alma"]
        tr, fl = side_trend(up, dn)
        return {"trend": _ro(tr), "flip": _ro(fl), "up": _ro(up), "dn": _ro(dn)}
    return ctx.get(MODULE, tf, {"series": "alma-cross"}, make)


def s1_stop(ctx: M.Context, tf: str) -> np.ndarray:
    """STK's S1 per bar: 3 x ATR(14) of the signal timeframe (``ctx.atr``: Pine ``ta.atr``, Wilder RMA seeded with an
    SMA; study 1's ``s1_stop``), a distance taken at the entry's decision bar and set from the fill (PREREG 6.2)."""
    _check_tf(tf)
    return ctx.get(MODULE, tf, S1_PARAMS, lambda: _ro(S1_MULT * np.asarray(ctx.atr(tf), np.float64)))


# ───────────────────────────── RIB, RIB-LIT, ALMA-X: event rules ─────────────────────────────

def flip_entries(ctx: M.Context, tf: str, side: str = "LS", trend: str = "ribbon", stop: str = "intended",
                 target_r: Optional[float] = None, be_r: Optional[float] = None) -> M.Entries:
    """
    The market entries of a flip rule before any filter: one per flip (LS) or per bull flip (LO), decided at the flip
    bar's close, side = the flip's side, ``stop_dist`` = riskDist of that bar (``stop='intended'``: the port's
    ``risk_long`` / ``risk_short``; ``'literal'``: ``risk_long_lit`` / ``risk_short_lit``, the ribbon's flips only),
    optional ``target_r`` (a multiple of riskDist from the fill) and ``be_r``. ``tag`` = the flip's ordinal in the
    whole series (0 = the first flip of the bars), so each trade names its flip. A flip whose distance is not a
    positive number (only while the ATR is missing or 0) opens nothing.
    """
    _check_tf(tf)
    if side not in SIDES:
        raise ValueError(f"{side}: one of {', '.join(SIDES)}")
    if stop not in STOPS:
        raise ValueError(f"{stop}: one of {', '.join(STOPS)}")
    if stop == "literal" and trend != "ribbon":
        raise ValueError("the literal stop exists on the ribbon's own flips only")
    sig = signals(ctx, tf, trend)
    r = ribbon_of(ctx, tf)
    flip = sig["flip"]
    k = np.flatnonzero(flip != 0)
    d = flip[k].astype(np.int64)
    lo, hi = ("risk_long", "risk_short") if stop == "intended" else ("risk_long_lit", "risk_short_lit")
    risk = np.where(d == 1, r[lo][k], r[hi][k]) if len(k) else np.zeros(0)
    with np.errstate(invalid="ignore"):
        keep = np.isfinite(risk) & (risk > 0)
    if side == "LO":
        keep &= d == 1
    tag = np.arange(len(k), dtype=np.int64)
    return M.entries(k[keep], d[keep], stop_dist=risk[keep], target_r=target_r, be_r=be_r, tag=tag[keep])


def flip_exits(ctx: M.Context, tf: str, trend: str = "ribbon") -> Tuple[np.ndarray, np.ndarray]:
    """(exit_long, exit_short) per bar: every bear flip closes a long at its close, every bull flip a short (X0's
    opposite flip; flips alternate, so it is the next flip after the entry's). Read-only."""
    sig = signals(ctx, tf, trend)
    return ctx.get(MODULE, tf, {"series": "exits", "trend": trend},
                   lambda: (_ro(sig["flip"] == -1), _ro(sig["flip"] == 1)))


def _or(base: np.ndarray, extra) -> np.ndarray:
    if extra is None:
        return base
    e = np.asarray(extra, bool)
    if e.shape != base.shape:
        raise ValueError(f"an extra exit mask has shape {e.shape}, the bars {base.shape}")
    return base | e


def rib_exec(ctx: M.Context, tf: str, side: str = "LS", exit: str = "X0", filt: str = "F0", *,
             trend: str = "ribbon", stop: str = "intended", gate: Optional[Tuple[np.ndarray, np.ndarray]] = None,
             exit_long=None, exit_short=None, tighten_long=None, tighten_short=None, tighten_be=None,
             label: str = "") -> M.Exec:
    """
    The EVENTS Exec of one flip rule (RIB, RIB-LIT with ``stop='literal'``, ALMA-X with ``trend='alma-cross'``):
    ``flip_entries`` gated by filter ``filt`` at the flip bar's close (``tradeiq2_filters.gate_entries``; PREREG 5's
    event rule: it never closes an open trade), the opposite-flip exits ``flip_exits`` and the exit variant ``exit``:
    X0 (none added), XT2 (``target_r`` 2), XP (two legs of 0.5: one with ``target_r`` 2, one without), XBE (``be_r``
    1). One position at a time; the reverse entry of LS fills at the same M1 open as the exit.

    For the Heikin Ashi overlays (PREREG 6.8, whose bases are RIB-LS / RIB-LO x X0 x F0): ``gate`` = an extra
    (allow_long, allow_short) pair checked at the entry's decision bar (HA-AND), ``exit_long`` / ``exit_short`` extra
    per-bar exits OR-ed with the flips', and the tightening arrays passed to the harness as they are (PREREG 4: a level
    is applied only below the bid / above the ask at the open that executes it, else that open is a market exit).
    """
    if exit not in EXITS:
        raise ValueError(f"{exit}: one of {', '.join(EXITS)}")
    E = flip_entries(ctx, tf, side, trend, stop, target_r=TARGET_R if exit == "XT2" else None,
                     be_r=BE_R if exit == "XBE" else None)
    E = F.gate_entries(E, *ctx.allow(tf, filt))
    if gate is not None:
        E = F.gate_entries(E, *gate)
    xl, xs = flip_exits(ctx, tf, trend)
    legs = (M.Leg(PARTIAL, target_r=TARGET_R), M.Leg(1.0 - PARTIAL, no_target=True)) if exit == "XP" else None
    return M.event_exec(tf, entries=E, legs=legs, exit_long=_or(xl, exit_long),
                        exit_short=_or(xs, exit_short) if side == "LS" else None, tighten_long=tighten_long,
                        tighten_short=tighten_short if side == "LS" else None, tighten_be=tighten_be, label=label)


# ───────────────────────────── STK: state rules ─────────────────────────────

def stk_filters(tf: str, rule: str) -> Tuple[str, ...]:
    """The filters an STK rule ANDs with the ribbon trend: RM (FS), RA (the higher timeframe's MA200: 1H F2-4H, 4H
    F2-1D, 1D F1), RMA (both)."""
    _check_tf(tf)
    if rule == "STK-RM":
        return ("FS",)
    if rule == "STK-RA":
        return (STK_MA[tf],)
    if rule == "STK-RMA":
        return ("FS", STK_MA[tf])
    raise ValueError(f"{rule}: one of {', '.join(STK_RULES)}")


def stk_state(ctx: M.Context, tf: str, rule: str, side: str = "LS") -> np.ndarray:
    """STK's target state per bar (int8, +1 / 0 / -1): the ribbon's trend of ``tf`` where every filter of
    ``stk_filters`` allows that side at the bar's close (``tradeiq2_filters.as_state_filter``), else 0; LO also makes
    the short states 0. Read-only, cached."""
    if side not in SIDES:
        raise ValueError(f"{side}: one of {', '.join(SIDES)}")
    names = stk_filters(tf, rule) + (("LO",) if side == "LO" else ())

    def make():
        al, ash = F.combine(*[ctx.allow(tf, f) for f in names])
        return _ro(F.as_state_filter(signals(ctx, tf, "ribbon")["trend"], al, ash))
    return ctx.get(MODULE, tf, {"series": "stk", "rule": rule, "side": side}, make)


def stk_exec(ctx: M.Context, tf: str, rule: str, side: str = "LS", label: str = "") -> M.Exec:
    """The STATE Exec of an STK row: ``stk_state`` with the S1 stop (``s1_stop``), study 1's ``run``."""
    return M.state_exec(tf, stk_state(ctx, tf, rule, side), s1_stop(ctx, tf), label=label)


# ───────────────────────────── the grid ─────────────────────────────

def _v(symbol: str, tf: str, family: str, rest: str, script: str, eligible: bool = True, info: str = "",
       **params) -> M.Variant:
    return M.Variant(f"{symbol}|{tf}|{family}|{rest}", symbol, tf, script, family, eligible, info, params)


def variants(symbol: str) -> List[M.Variant]:
    """
    EXACTLY the rows of PREREG 6.1 and 6.10 for ``symbol`` (the module docstring's table): 163 on XAUUSDm and on
    BTCUSDm, in the order RIB (timeframe, side, exit, filter), RIB-LIT, ALMA-X, STK; none on the claim markets
    (PREREG 8 checks only Session Hunter there). ``params``: rule, side, exit, filter, stop, trend (STK: rule, side,
    stop, context). Raises for a symbol that is not the study's.
    """
    if symbol not in M.ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(M.ALL_SYMBOLS)})")
    if symbol not in M.SYMBOLS:
        return []
    out: List[M.Variant] = []
    for tf in TFS:
        for side in SIDES:
            for ex in EXITS:
                for f in RIB_FILTERS[tf]:
                    out.append(_v(symbol, tf, "RIB", f"{side}|{ex}|{f}", "RIB", rule=f"RIB-{side}", side=side,
                                  exit=ex, filter=f, stop="intended", trend="ribbon"))
    for tf in TFS:
        out.append(_v(symbol, tf, "RIB", "RIB-LIT|LS|X0|F0", "RIB", False, "sensitivity; not eligible",
                      rule="RIB-LIT", side="LS", exit="X0", filter="F0", stop="literal", trend="ribbon"))
    for tf in TFS:
        for side in SIDES:
            out.append(_v(symbol, tf, "ALMA-X", f"{side}|X0|F0", "RIB", True, "control", rule="ALMA-X", side=side,
                          exit="X0", filter="F0", stop="intended", trend="alma-cross"))
    for tf in TFS:
        for rule in STK_RULES:
            for side in SIDES:
                out.append(_v(symbol, tf, "STK", f"{rule}|{side}|S1", "STK", rule=rule, side=side, stop="S1",
                              context=list(stk_filters(tf, rule))))
    return out


_CANON: Dict[str, Dict[str, M.Variant]] = {}


def _canonical(symbol: str) -> Dict[str, M.Variant]:
    if symbol not in _CANON:
        _CANON[symbol] = {v.id: v for v in variants(symbol)}
    return _CANON[symbol]


def _row(variant: M.Variant) -> M.Variant:
    v = _canonical(variant.symbol).get(variant.id) if variant.symbol in M.ALL_SYMBOLS else None
    if v is None or (v.tf, v.family) != (variant.tf, variant.family):
        raise ValueError(f"{variant.id}: not a row of PREREG 6.1 / 6.10 (tradeiq2_rules_ribbon.variants)")
    return v


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The ``tradeiq2_market.Exec`` of one row of ``variants`` (looked up by its id; the settings are the canonical
    row's): ``rib_exec`` for RIB, RIB-LIT and ALMA-X, ``stk_exec`` for STK. The Exec's label is the id."""
    v = _row(variant)
    if v.symbol != ctx.symbol:
        raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
    p = dict(v.params)
    if v.family == "STK":
        return stk_exec(ctx, v.tf, p["rule"], p["side"], label=v.id)
    return rib_exec(ctx, v.tf, p["side"], p["exit"], p["filter"], trend=p["trend"], stop=p["stop"], label=v.id)


def describe(variant: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    v = _row(variant)
    p = dict(v.params)
    bars = f"{v.tf} bars of the bid (UTC)"
    if v.family == "STK":
        ctx_words = STK_WORDS[p["rule"]]
        verb = "agree" if p["rule"] == "STK-RMA" else "agrees"
        how = "short in the mirror case, otherwise flat" if p["side"] == "LS" else "otherwise flat (long only)"
        return (f"The video's 2027 chart setup {p['rule']} on {bars}, a state rule: long while the ribbon's trend is "
                f"up and {ctx_words} ({' + '.join(p['context'])}) {verb}, {how}. Stop S1: 3 x ATR(14) from the fill, "
                "fixed. An entry where the state changes (also after a stop), at the open of the next M1 bar; the "
                "position closes where the state changes")
    if v.family == "ALMA-X":
        sig = ("The close crossing the ribbon's ALMA(34, 0.85, 6) (the control of the ribbon's flips: no slope or "
               "band condition)")
    else:
        sig = "The Trend Target Ribbon's flip (slope > 0.08 ATR over 3 bars and the close beyond ALMA -/+ 0.65 dev)"
    stop = ("the literal TradingView stop (a long's: the lowest low of up to 12 earlier bull-flip bars, a short's "
            "mirrored, clamped to 0.75-3 ATR; RIB-LIT, a sensitivity row)" if p["stop"] == "literal" else
            "riskDist = min(max(close - the lowest low of the 12 bars before, 0.75 ATR), 3 ATR) (a short's mirrored)")
    rule = (f"{SIDE_WORDS[p['side']]}; filled at the open of the next M1 bar; stop {stop}, set from the fill and "
            f"never moved; {EXIT_WORDS[p['exit']]}; filter: {FILTER_WORDS[p['filter']]}, checked at the flip's close "
            "(it never closes an open trade)")
    if v.family == "ALMA-X":
        rule = rule.replace("bull flip", "cross up").replace("bear flip", "cross down").replace(" flip", " cross")
    return f"{sig} on {bars}: {rule}"


def warm(ctx: M.Context, variants_: Sequence[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, every array the given rows read: the ribbon, the
    ALMA cross, the exits, the filters (FR's higher ribbon, FS's dashboard), the S1 stop and the STK states."""
    for v in variants_:
        v = _row(v)
        p = dict(v.params)
        if v.family == "STK":
            stk_state(ctx, v.tf, p["rule"], p["side"])
            s1_stop(ctx, v.tf)
        else:
            flip_exits(ctx, v.tf, p["trend"])
            ctx.allow(v.tf, p["filter"])


def plan_counts(symbol: str) -> Dict[Tuple[str, bool], int]:
    """The rows ``variants(symbol)`` gives per (family, eligible), for the grid check."""
    out: Dict[Tuple[str, bool], int] = {}
    for v in variants(symbol):
        out[(v.family, bool(v.eligible))] = out.get((v.family, bool(v.eligible)), 0) + 1
    return out


def flip_table(ctx: M.Context, tf: str, trend: str = "ribbon") -> Mapping[str, np.ndarray]:
    """Event geometry for reports and checks (no profit or loss): per flip, its bar, close time, side, the intended
    and the literal stop distance in price and in ATR. Read-only arrays."""
    sig = signals(ctx, tf, trend)
    r = ribbon_of(ctx, tf)
    b = ctx.bars(tf)
    k = np.flatnonzero(sig["flip"] != 0)
    d = sig["flip"][k].astype(np.int64)
    risk = np.where(d == 1, r["risk_long"][k], r["risk_short"][k]) if len(k) else np.zeros(0)
    lit = (np.where(d == 1, r["risk_long_lit"][k], r["risk_short_lit"][k]) if (len(k) and trend == "ribbon")
           else np.full(len(k), math.nan))
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"bar": _ro(k), "tc": _ro(b.tc[k]), "side": _ro(d), "risk": _ro(risk), "risk_lit": _ro(lit),
                "risk_atr": _ro(risk / r["atr"][k]), "risk_lit_atr": _ro(lit / r["atr"][k])}
