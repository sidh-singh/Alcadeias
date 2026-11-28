"""
TradeIQ study 2: the rule rows of "Harmonic & Chart Patterns [AI-AlgoCode]", PREREG section 6.7.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_patterns as R
    ctx = M.Context(M.load("XAUUSDm"))           # served to the hold-out start until FINALISTS.md is frozen
    vs = R.variants("XAUUSDm")                   # the 48 eligible rows of PREREG 6.7 + 10 HP-DRAWN information rows
    ex = R.build(vs[0], ctx)                     # an EVENTS Exec (market entries, or stop orders for HP-CS)
    res = M.run_variant(ctx, vs[0], ex)          # Development, Validation and D+V at x1.0 and x1.5
    R.table(vs[0], ctx)                          # the row's candidates: times, sides, levels, flags (no profit)

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen): section 4 (execution and the absolute-level rules),
5 (filters on event rules: entry gates), 6.7 (these rules) and 7 (families, eligibility), read with ``DEVIATIONS.md``.
The patterns are the reconciled port ``tradeiq2_ind_patterns`` (port A; ``porting/patterns.md``, whose section 9
names the rows each rule reads); the filters are ``tradeiq2_filters``; the execution is ``tradeiq2_market``'s
``event_exec``. Line numbers (Lnnn) are those of the owner's copy of the script (third-party code, cited, never copied).

The rows (all EVENT rules; ids ``symbol|tf|family|rule|...``)
-------------------------------------------------------------
| Family | Rule | Event, decided at a bar close | Targets x filters x timeframes | Rows |
|---|---|---|---|---|
| HP-HARMONIC | HP-HF | the first bar of each forming harmonic instance (the forming first hit): a market entry | TP1, TP2, 50/50 x F0, F2, FR (1D: F1 in place of F2) x 1H, 4H, 1D | 27 |
| HP-HARMONIC | HP-HC | the confirmed alert whose first hit is a harmonic (control): a market entry | TP1 x F0 x 1H, 4H, 1D | 3 |
| HP-CHART | HP-CF | the first bar of each forming chart instance, any chart id (reversal and continuation pooled): a market entry | TP1, TP2 x F0, F2, FR x 1H, 4H | 12 |
| HP-CHART | HP-CS | a stop order at the neckline p2 once every condition but the breakout close holds | TP1 x F0, F2 x 1H, 4H | 4 |
| HP-CHART | HP-CC | the confirmed alert whose first hit is a chart pattern (control): a market entry | TP1 x F0 x 1H, 4H | 2 |
| HP-HARMONIC / HP-CHART | HP-DRAWN | information only, never a candidate: the confirmed plan entered at D's bar (look-ahead) | TP1 x F0 x ALL, SHOWN x (1H, 4H, 1D / 1H, 4H) | 6 + 4 |

That is 27 + 3 = 30 HP-HARMONIC and 12 + 4 + 2 = 18 HP-CHART eligible rows per symbol (PREREG 6.7 "Size: 48"),
plus 10 HP-DRAWN rows with ``eligible=False``. Ids: ``XAUUSDm|1H|HP-HARMONIC|HP-HF|50/50|F2-4H``,
``BTCUSDm|4H|HP-CHART|HP-CS|TP1|F2-1D``, ``XAUUSDm|1D|HP-HARMONIC|HP-HF|TP1|F1``,
``XAUUSDm|1H|HP-HARMONIC|HP-DRAWN|SHOWN|TP1|F0``. The filter token of an id is the filter's name in
``tradeiq2_filters`` (``params['filter_slot']`` keeps the PREREG's slot F0 / F2 / FR); swapping it for F0 gives the
row's unfiltered twin.

The script, as the rules read it (``tradeiq2_ind_patterns``' docstring has the full port)
----------------------------------------------------------------------------------------
* Depth 5 (L19), every input at its default (L19-92): the zigzag of L535-572 on the bid high / low / close of the
  signal bars; the 38 predicates of L293-480 with the 144 ratio constants of L146-289; ``detect`` (L525-531) checks
  every id in registry order (bearish harmonics 0-10, bullish harmonics 11-21, chart patterns 22-37) and the FIRST
  hit is the one drawn and alerted.
* Confirmed (L780-795): on a bar where a swing is added, with at least 12 swings, the 11 swings before the new one
  (Q0 = point D, the swing just fixed). Known at that bar's close (``alert.freq_once_per_bar_close``, L825), a median
  of 3 bars after D. The chart predicates read the close of D's bar (``c0`` = pivC[1], L781); the rules' decision
  close is the detection bar's own close (``close``), not ``c0``.
* Forming (L798-813): the script computes it on the last bar only (L802); the study runs it at EVERY bar close on the
  zigzag state after that bar, with that bar's close and at least 11 swings (Q0 = the live D): what a live user sees
  at that close (PREREG 6.7). A forming pattern can change or vanish later; nothing found later is used.
* The plan (``planLevels``, L694-718; inputs L35-41): harmonic AD = |Q3 - Q0|, entry D, SL = D - dir*0.13*AD,
  TP1 = D + dir*0.382*AD, TP2 = D + dir*0.618*AD; chart h = |Q1 - Q2|, entry p2 = Q2 (the neckline),
  SL = p2 - dir*0.5*h, TP1 = p2 + dir*h, TP2 = p2 + dir*1.618*h. The plan horizon is ``planBars`` = 30 (L38):
  the time stop of every row. The rules use these ABSOLUTE levels as the port returns them.
* The overlap gate (L767-792) decides only what is drawn (``drawn``); the alert is never gated (L793-795).

What is known when (no look-ahead, except HP-DRAWN by design)
------------------------------------------------------------
Every forming or confirmed row with ``t_bar`` = T, and ``forming_q`` at T, depends on bars 0..T only (the port's
tests; this module's tests remove the bars after T and compare every candidate decided up to T). Each rule decides
at the close ``tc[T]`` of its decision bar and the harness fills at the open of the first M1 bar at or after it
(``bars.ex[T]``: a buy at the ask, a sell at the bid). HP-CS places its order at ``tc[T]`` (active from
``bars.ex[T]``); its cancel time is the close of the bar where the next swing is added, the moment a live user sees
the key stop being armed, so nothing before that moment depends on it. HP-DRAWN enters at the close of D's bar,
which is earlier than the confirmation that makes the pattern known (``t_conf`` > its decision bar): that look-ahead
is the point of the row (PREREG 8, claim 18) and the reason it is never a candidate.

Execution (PREREG 4, 5; study 1's DEVIATIONS 1-7; study 2's DEVIATIONS 3-9)
--------------------------------------------------------------------------
* Market entries (``M.entries``): ``stop_level`` = the plan's SL and ``target_level`` = TP1 or TP2. The harness turns
  each level L into a distance |fill - L| from the ACTUAL fill, drops an entry whose fill is at or beyond its stop
  or its target (``dropped_stop`` / ``dropped_target``), and the x1.5 run recomputes every fill and distance on its
  own spreads. One extra spread is charged on a stop fill; a target is a limit touched inside an M1 bar; when one
  M1 bar touches both, the stop wins.
* 50/50 (HP-HF): two legs of weight 0.5 with identical entries, one with TP1 and one with TP2 (``M.Leg``,
  PREREG 4's partial exits). The entry is dropped when its fill is at or beyond either target (DEVIATIONS 6); the
  next entry waits until both legs are flat. Live, this needs at least 0.02 lot per unit (noted in the row's info).
* Time stop: ``exit_bar`` = D's bar + 30, the close of the 30th bar after D, never moved.
* HP-CS (``M.orders``): a buy stop (bullish id) or a sell stop (bearish id) at p2, with ``buy_stop`` / ``sell_stop``
  = the plan's SL and ``buy_target`` / ``sell_target`` = TP1 (absolute, from the actual fill); a buy fills at
  max(p2, ask at the open) once the ask reaches p2 inside an M1 bar, a sell at min(p2, bid at the open). Each order
  fills at most once; a newer order replaces an older unfilled one; an order placed while a position is open
  becomes active when it closes, until its cancel time (DEVIATIONS 8).
* One position at a time per row; a candidate that arrives while one is open is skipped ("busy"; PREREG 4: an event
  rule waits for its next event). What is open at a window's end closes at its last M1 close.
* Filters on event rules (PREREG 5): the filter must agree at the decision close of the entry
  (``tradeiq2_filters.gate_entries``; an order: at its placement close, ``gate_orders``). It never closes an open
  trade, which keeps its own exits. F2 = ``F2-4H`` on 1H, ``F2-1D`` on 4H; on 1D HP-HF uses F1; FR = the ribbon trend
  of the higher timeframe (1H: 4H, 4H: 1D, 1D: the 1D ribbon itself).

Readings where PREREG 6.7 is silent (written before any result of these rows exists; for DEVIATIONS.md)
-----------------------------------------------------------------------------------------------------
1. F2's timeframe. 6.7's sizes (27 = 3 targets x 3 filters x 3 timeframes, 12 = 2 x 3 x 2, 4 = 2 x 2) leave one F2
   per timeframe. It is the next higher one, F2-4H on 1H and F2-1D on 4H, as sections 6.3, 6.4, 6.8 and 6.10 spell
   it out, and as 6.7's own "1D: F1 in place of F2" continues it (section 5's table allows both on 1H).
2. The instance and its first bar (porting notes 8.2). HP-HF reads the forming FIRST hit, the pattern the script
   draws and its forming alert names (L808-813); an instance is its key, the id plus the bars of its fixed swings
   Q1..Q(n-1); the entry is at the first bar on which the key is the first hit, once per key (a return while D is
   still live is the same instance). HP-CF reads every chart id, including chart patterns behind a harmonic first
   hit, at the first bar of the key over all hits (``first_bar_of_instance``). All chart hits of one bar read the
   same Q2 and close and every bullish predicate ends with close > Q2, every bearish one with close < Q2, so they
   share the direction and the plan: one entry per bar (its tag is the lowest id). Harmonics do not read the close,
   so an HP-HF first bar is always D's bar (b0 = t_bar).
3. The confirmed controls (porting notes 8.3). The confirmed alert names its first hit: HP-HC reads the detections
   whose first hit is a harmonic, HP-CC those whose first hit is a chart pattern; a chart pattern behind a harmonic
   first hit raises no chart alert. One entry per detection.
4. The skip rule. "Skipped when the close is already beyond TP1" is read as at or beyond (a close on TP1 has touched
   it), at the decision close (the bar's own close; for HP-HC the detection bar's, not ``c0``), on HP-HF and HP-HC
   and on HP-DRAWN's harmonic rows. The plan gives the chart rows (HP-CF, HP-CS, HP-CC) no skip rule, so they have
   none beyond section 4's: an entry whose FILL is at or beyond its target or stop is dropped by the harness. In
   Development it skips 85 of gold 1H's 1,144 HP-HF entry bars and 401 of its 840 HP-HC alerts (BTC 1H: 146 of
   1,546 and 562 of 1,182): the confirmation comes late, as PREREG 6.7 says.
5. "30 bars after D". D is the swing in the row at its decision: the live D for a forming row (``b0`` at the
   decision close; a later move of the live swing does not move the time stop), the live D at the order's placement
   for HP-CS, the fixed D of a confirmed row. The exit decision is the close of bar D + 30. A decision at or after
   that bar is not entered (none in Development); a bar D + 30 beyond the data gives no exit bar (the window's end
   closes the trade, as it would in a longer run of the same window).
6. HP-CS's order (porting notes 8.4). "Every condition except the breakout close" is ``tradeiq2_ind_patterns.armed``:
   the chart predicate without its last conjunct, the only place the close is read (L322-480). It reads Q1..Q8 only,
   which are fixed swings, so a key is armed from the close of the bar where a swing is added until the close of the
   bar where the next one is added (then its swings shift). The order is placed at the close of the bar where the
   key is first armed, at p2 = Q2, and cancelled at the first M1 bar opening at or after the earlier of: the close of
   the bar where the next swing is added (the key is no longer armed), and the close of bar D + 30 (the plan's
   horizon; D = the live swing at the placement). The keys armed at one bar read the same Q1 and Q2, so they share
   p2, h and the levels: one order per bar (tag: the lowest id). If keys of both directions are armed at one bar (none
   in Development on either symbol, none in 12 million random swing sets), the order carries both sides and one
   cancels the other. The order is placed
   even when the close is already beyond p2 (no extra condition in the plan): it then fills at the next M1 open, by
   section 4's "max(level, ask at the open)". That is 85 of gold 1H's 312 armed keys in Development (BTC 1H: 127
   of 421).
7. HP-CS's filter is checked at the placement close (``gate_orders``): the order's decision close is its placement;
   a filter that turns later neither cancels the order nor closes the trade.
8. HP-DRAWN ("the plan as drawn back at D, with look-ahead"; porting notes 8.6). A market entry decided at the close
   of D's bar with the confirmed row's levels, TP1, F0 and the time stop, on the same confirmed first hits as HP-HC
   (harmonic first hits, family HP-HARMONIC) and HP-CC (chart first hits, HP-CHART), so each pair differs only in the
   entry time: the "ALL" rows. The "SHOWN" rows take the subset the overlap gate draws (``drawn``, L785-792), the
   patterns an old chart actually shows (the porting notes' "drawn subset reported beside it"). 3 + 2 timeframes x 2
   sets = 10 rows per symbol, ``eligible=False``, info "information only".
9. Tags: each entry's tag is its pattern id (0-37), carried to the trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping

import numpy as np
import pandas as pd

from . import tradeiq2_filters as F
from . import tradeiq2_ind_patterns as HP
from . import tradeiq2_market as M

__all__ = [
    "SCRIPT", "CACHE", "FAMILIES", "RULES", "HARMONIC_TFS", "CHART_TFS", "TIME_STOP_BARS", "F2_OF", "HF_SLOTS",
    "CF_SLOTS", "CS_SLOTS", "HF_TARGETS", "CF_TARGETS", "DRAWN_SETS", "COUNTS", "INFO_COUNTS", "NEVER", "Spec",
    "variants", "spec_of", "build", "events", "rows_of", "table", "describe", "warm", "filter_name",
]

SCRIPT = "HP"
CACHE = "rules_patterns"                      # this module's key in the Context's cache
FAMILIES = ("HP-HARMONIC", "HP-CHART")         # PREREG 7's families of this script
RULES = ("HP-HF", "HP-HC", "HP-CF", "HP-CS", "HP-CC", "HP-DRAWN")
HARMONIC_TFS = ("1H", "4H", "1D")              # HP-HF, HP-HC: "on 1H, 4H and 1D", "three timeframes"
CHART_TFS = ("1H", "4H")                       # HP-CF, HP-CS, HP-CC: "1H and 4H"
TIME_STOP_BARS = HP.PLAN_BARS                  # 30: "time stop 30 bars after D, the script's plan horizon" (L38)
# the PREREG's F2 slot per timeframe (reading 1); "1D: F1 in place of F2" (HP-HF)
F2_OF = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}
HF_SLOTS = ("F0", "F2", "FR")
CF_SLOTS = ("F0", "F2", "FR")
CS_SLOTS = ("F0", "F2")
HF_TARGETS = ("TP1", "TP2", "50/50")
CF_TARGETS = ("TP1", "TP2")
DRAWN_SETS = ("ALL", "SHOWN")                  # every confirmed first hit / those the overlap gate draws (reading 8)
# PREREG 6.7 "Size: 27 HF + 3 HC + 12 CF + 4 CS + 2 CC = 48 eligible rows per symbol"
COUNTS: Dict[str, int] = {"HP-HARMONIC": 30, "HP-CHART": 18}
INFO_COUNTS: Dict[str, int] = {"HP-HARMONIC": 6, "HP-CHART": 4}      # HP-DRAWN (the plan gives no number)
NEVER = 2 ** 62                               # an order's cancel time when nothing in the data cancels it
_FAMILY_OF = {"HP-HF": "HP-HARMONIC", "HP-HC": "HP-HARMONIC", "HP-CF": "HP-CHART", "HP-CS": "HP-CHART",
              "HP-CC": "HP-CHART"}
_INFO_CONTROL = "control"
_INFO_LEGS = "partial exits: two half legs (TP1 and TP2); live this needs at least 0.02 lot per unit (PREREG 4)"
_INFO_DRAWN = {"ALL": "information only, never a candidate: look-ahead (entered at D's bar, known only at the "
                      "confirmation); every confirmed first hit",
               "SHOWN": "information only, never a candidate: look-ahead (entered at D's bar, known only at the "
                        "confirmation); the first hits the overlap gate draws"}


def filter_name(slot: str, tf: str) -> str:
    """The ``tradeiq2_filters`` name of a PREREG filter slot on timeframe ``tf``: F0 and FR as they are, F2 the next
    higher timeframe's MA200 (F2-4H on 1H, F2-1D on 4H) and F1 on 1D (reading 1)."""
    if slot in ("F0", "FR"):
        return slot
    if slot == "F2":
        return F2_OF[tf]
    raise ValueError(f"{slot}: not a filter slot of PREREG 6.7 (F0, F2, FR)")


@dataclass(frozen=True)
class Spec:
    """One row of the grid, parsed: ``rule`` (RULES), ``tf``, ``family``, ``target`` (TP1, TP2, 50/50), ``slot``
    (the PREREG's filter slot F0 / F2 / FR; ``filt`` is its filter name), ``drawn`` (HP-DRAWN's set: ALL / SHOWN)."""
    symbol: str
    tf: str
    family: str
    rule: str
    target: str = "TP1"
    slot: str = "F0"
    drawn: str = ""

    @property
    def filt(self) -> str:
        return filter_name(self.slot, self.tf)

    @property
    def kind(self) -> str:
        """'harmonic' or 'chart': the patterns the row trades."""
        return "harmonic" if self.family == "HP-HARMONIC" else "chart"

    @property
    def eligible(self) -> bool:
        return self.rule != "HP-DRAWN"

    @property
    def id(self) -> str:
        head = f"{self.symbol}|{self.tf}|{self.family}|{self.rule}"
        if self.rule == "HP-DRAWN":
            return f"{head}|{self.drawn}|{self.target}|{self.filt}"
        return f"{head}|{self.target}|{self.filt}"

    @property
    def source(self) -> str:
        """The candidate table of ``events`` the row reads."""
        if self.rule == "HP-DRAWN":
            return "drawn_" + self.kind
        return {"HP-HF": "hf", "HP-HC": "hc", "HP-CF": "cf", "HP-CS": "cs", "HP-CC": "cc"}[self.rule]

    @property
    def skips_past_tp1(self) -> bool:
        """The skip rule (reading 4): HP-HF, HP-HC and HP-DRAWN's harmonic rows."""
        return self.rule in ("HP-HF", "HP-HC") or (self.rule == "HP-DRAWN" and self.kind == "harmonic")

    @property
    def info(self) -> str:
        if self.rule == "HP-DRAWN":
            return _INFO_DRAWN[self.drawn]
        if self.rule in ("HP-HC", "HP-CC"):
            return _INFO_CONTROL
        if self.target == "50/50":
            return _INFO_LEGS
        return ""

    def params(self) -> Dict[str, object]:
        detection = {"HP-HF": "forming first hit", "HP-HC": "confirmed first hit", "HP-CF": "forming",
                     "HP-CS": "armed", "HP-CC": "confirmed first hit", "HP-DRAWN": "confirmed first hit"}[self.rule]
        entry = {"HP-CS": "stop order at p2", "HP-DRAWN": "market at D's bar (look-ahead)"}.get(self.rule, "market")
        p: Dict[str, object] = {"rule": self.rule, "kind": "events", "patterns": self.kind, "detection": detection,
                                "entry": entry, "target": self.target, "filter": self.filt,
                                "filter_slot": self.slot, "time_stop_bars": TIME_STOP_BARS,
                                "skip": "close at or beyond TP1" if self.skips_past_tp1 else "none",
                                "depth": HP.DEPTH}
        if self.rule == "HP-DRAWN":
            p["drawn_set"] = self.drawn
        return p

    def variant(self) -> M.Variant:
        return M.Variant(self.id, self.symbol, self.tf, SCRIPT, self.family, self.eligible, self.info, self.params())


def _specs(symbol: str) -> List[Spec]:
    if symbol not in M.SYMBOLS:
        raise ValueError(f"{symbol}: PREREG 6.7's rows are on {' and '.join(M.SYMBOLS)} only")
    out: List[Spec] = []
    for tf in HARMONIC_TFS:
        for slot in HF_SLOTS:
            for target in HF_TARGETS:
                out.append(Spec(symbol, tf, "HP-HARMONIC", "HP-HF", target, slot))
    for tf in HARMONIC_TFS:
        out.append(Spec(symbol, tf, "HP-HARMONIC", "HP-HC"))
    for tf in CHART_TFS:
        for slot in CF_SLOTS:
            for target in CF_TARGETS:
                out.append(Spec(symbol, tf, "HP-CHART", "HP-CF", target, slot))
    for tf in CHART_TFS:
        for slot in CS_SLOTS:
            out.append(Spec(symbol, tf, "HP-CHART", "HP-CS", "TP1", slot))
    for tf in CHART_TFS:
        out.append(Spec(symbol, tf, "HP-CHART", "HP-CC"))
    for family, tfs in (("HP-HARMONIC", HARMONIC_TFS), ("HP-CHART", CHART_TFS)):
        for tf in tfs:
            for st in DRAWN_SETS:
                out.append(Spec(symbol, tf, family, "HP-DRAWN", "TP1", "F0", st))
    return out


_SPEC_CACHE: Dict[str, Dict[str, Spec]] = {}


def _spec_table(symbol: str) -> Dict[str, Spec]:
    if symbol not in _SPEC_CACHE:
        specs = _specs(symbol)
        table_ = {s.id: s for s in specs}
        if len(table_) != len(specs):
            raise AssertionError("duplicate ids in the HP grid")
        _SPEC_CACHE[symbol] = table_
    return _SPEC_CACHE[symbol]


def variants(symbol: str) -> List[M.Variant]:
    """
    Exactly PREREG 6.7's rows of ``symbol`` (XAUUSDm or BTCUSDm), in the plan's order: HP-HF (1H, 4H, 1D x F0, F2,
    FR x TP1, TP2, 50/50), HP-HC (x 3 timeframes), HP-CF (1H, 4H x F0, F2, FR x TP1, TP2), HP-CS (1H, 4H x F0, F2),
    HP-CC (1H, 4H); then HP-DRAWN (harmonic 1H, 4H, 1D and chart 1H, 4H x ALL, SHOWN), ``eligible=False``. 58 rows:
    30 eligible HP-HARMONIC, 18 eligible HP-CHART, 6 + 4 information rows. Script "HP".
    """
    return [s.variant() for s in _spec_table(symbol).values()]


def spec_of(variant: M.Variant) -> Spec:
    """The registered row behind ``variant`` (its id is the identity; a grid row rebuilt from grid.csv works too)."""
    s = _spec_table(variant.symbol).get(variant.id)
    if s is None:
        raise ValueError(f"{variant.id}: not a row of PREREG 6.7 (tradeiq2_rules_patterns.variants)")
    if variant.tf != s.tf or variant.family != s.family or variant.script != SCRIPT:
        raise ValueError(f"{variant.id}: tf / family / script {variant.tf} / {variant.family} / {variant.script} "
                         f"differ from the registered row's {s.tf} / {s.family} / {SCRIPT}")
    return s


# ───────────────────────────── the events (cached in the Context) ─────────────────────────────

_ORDER_KEYS = ("bar", "until", "buy", "sell", "buy_stop", "sell_stop", "buy_target", "sell_target", "d_bar", "pid",
               "n_keys", "sides", "close", "next_add")


def _ro(a) -> np.ndarray:
    a = np.ascontiguousarray(a)
    a.setflags(write=False)
    return a


def _table_of(df: pd.DataFrame, decision: str, c: np.ndarray) -> Dict[str, np.ndarray]:
    """Rows of the port's confirmed / forming tables as candidate arrays: the decision bar (``t_bar``, or D's bar
    ``b0`` for HP-DRAWN), the side (the pattern's ``dir``), the decision close, the plan levels, D's bar, the id, the
    detection bar (``t_conf``) and the overlap gate's ``drawn`` (confirmed rows; True elsewhere)."""
    bar = df[decision].to_numpy(np.int64)
    out = {"bar": bar, "side": df["dir"].to_numpy(np.int64), "close": c[bar].astype(np.float64)}
    for k in ("entry", "sl", "tp1", "tp2", "unit"):
        out[k] = df[k].to_numpy(np.float64)
    out["d_bar"] = df["b0"].to_numpy(np.int64)
    out["pid"] = df["id"].to_numpy(np.int64)
    out["t_conf"] = df["t_bar"].to_numpy(np.int64)
    out["drawn"] = df["drawn"].to_numpy(bool) if "drawn" in df.columns else np.ones(len(df), bool)
    out["n_ids"] = np.ones(len(df), np.int64)
    if len(df) and decision == "t_bar" and not np.array_equal(df["close"].to_numpy(np.float64), out["close"]):
        raise AssertionError("the port's decision close is not the bar's close")
    return out


def _chart_per_bar(g: pd.DataFrame, c: np.ndarray) -> Dict[str, np.ndarray]:
    """HP-CF: the chart rows that are the first bar of their instance, one candidate per bar (reading 2). Every chart
    row of a bar reads that bar's Q2 and close, so they share the direction and the plan (checked); the candidate
    takes the bar's first row (the lowest id) and counts the instances in ``n_ids``."""
    tab = _table_of(g, "t_bar", c)
    if not len(g):
        return tab
    bar = tab["bar"]
    start = np.flatnonzero(np.r_[True, bar[1:] != bar[:-1]])
    seg = np.repeat(np.arange(len(start)), np.diff(np.r_[start, len(bar)]))
    for k in ("side", "sl", "tp1", "tp2", "entry", "unit", "d_bar"):
        v = tab[k]
        if not np.array_equal(v, v[start][seg], equal_nan=v.dtype.kind == "f"):
            raise AssertionError(f"two chart instances of one bar differ in {k}")
    out = {k: v[start] for k, v in tab.items()}
    out["n_ids"] = np.diff(np.r_[start, len(bar)]).astype(np.int64)
    return out


def _armed_orders(out: Mapping[str, object], tc: np.ndarray, c: np.ndarray) -> Dict[str, np.ndarray]:
    """HP-CS's orders (reading 6): every chart key (id, bars of Q1..Q(n-1)) at the first bar where ``HP.armed`` holds
    on ``forming_q`` (pivP.size() >= 11), grouped by that bar; one order per bar, at p2 = Q2, with the plan's SL and
    TP1 per side; cancelled at the earlier of the close of the next bar that adds a swing and the close of bar
    D + 30 (D = the live swing at the placement)."""
    fq, fqb = out["forming_q"], out["forming_qbar"]
    added = np.asarray(out["added"], bool)
    n = len(tc)
    rows = np.flatnonzero(np.asarray(out["n_piv"]) >= HP.N_Q)
    first: Dict[tuple, int] = {}
    for pid in range(22, HP.N_IDS):
        if not len(rows):
            break
        a = np.asarray(HP.armed(pid, fq[rows]), bool)
        m = int(HP.PTS[pid])
        for t in rows[a]:
            key = (pid,) + tuple(int(x) for x in fqb[t, 1:m])
            if key not in first:
                first[key] = int(t)
    by_bar: Dict[int, List[int]] = {}
    for key, t in first.items():
        by_bar.setdefault(t, []).append(int(key[0]))
    adds = np.flatnonzero(added)
    cols: Dict[str, list] = {k: [] for k in _ORDER_KEYS}
    for t in sorted(by_bar):
        if not added[t]:
            raise AssertionError(f"a chart key first armed on bar {t}, where no swing was added")
        pids = sorted(set(by_bar[t]))
        lv = {}
        for d in (1, -1):
            mine = [p for p in pids if int(HP.DIR[p]) == d]
            if mine:
                lv[d] = HP.plan_levels(mine[0], fq[t])          # (unit, entry, sl, tp1, tp2)
        ok = {d: v for d, v in lv.items() if v[0] > 0 and all(np.isfinite(v[1:]))}
        if not ok:
            continue                                            # a zero-height pattern has no levels (R10)
        d_bar = int(fqb[t, 0])
        k = int(np.searchsorted(adds, t, side="right"))
        nxt = int(adds[k]) if k < len(adds) else -1
        until = min(int(tc[nxt]) if nxt >= 0 else NEVER, int(tc[d_bar + TIME_STOP_BARS])
                    if d_bar + TIME_STOP_BARS < n else NEVER)
        cols["bar"].append(t)
        cols["until"].append(until)
        for d, side in ((1, "buy"), (-1, "sell")):
            v = ok.get(d)
            cols[side].append(v[1] if v else np.nan)
            cols[side + "_stop"].append(v[2] if v else np.nan)
            cols[side + "_target"].append(v[3] if v else np.nan)
        cols["d_bar"].append(d_bar)
        cols["pid"].append(min(p for p in pids if int(HP.DIR[p]) in ok))
        cols["n_keys"].append(len(pids))
        cols["sides"].append(sum(ok))                           # +1 buy, -1 sell, 0 both
        cols["close"].append(float(c[t]))
        cols["next_add"].append(nxt)
    ints = ("bar", "until", "d_bar", "pid", "n_keys", "sides", "next_add")
    return {k: np.asarray(v, np.int64 if k in ints else np.float64) for k, v in cols.items()}


def events(ctx: M.Context, tf: str) -> Dict[str, Dict[str, np.ndarray]]:
    """
    Every candidate table of one timeframe, from ONE run of ``tradeiq2_ind_patterns.patterns`` on ``ctx.bars(tf)``
    (bid high / low / close, depth 5), read-only and cached (the port's DataFrames are not kept):

    * ``hf``: forming first-hit harmonics (ids 0-21), the first bar of each key (``instance_key``) as first hit;
    * ``hc`` / ``cc``: confirmed detections whose first hit is a harmonic / a chart pattern, at the detection bar;
    * ``drawn_harmonic`` / ``drawn_chart``: the same detections decided at D's bar (``bar`` = ``b0``), with their
      detection bar in ``t_conf`` and the overlap gate's verdict in ``drawn``;
    * ``cf``: forming chart rows (ids 22-37) at ``first_bar_of_instance``, one per bar (``n_ids`` instances);
    * ``cs``: HP-CS's orders, one per bar where chart keys are first armed.

    Row tables carry ``bar`` (the decision bar), ``side``, ``close`` (the decision close), the plan's ``entry``,
    ``sl``, ``tp1``, ``tp2``, ``unit`` (AD or h), ``d_bar`` (D's bar: the time stop's origin), ``pid``, ``t_conf``,
    ``drawn``, ``n_ids``. ``cs`` carries ``bar``, ``until`` (UTC s), ``buy`` / ``sell`` (p2 or NaN), their stops and
    targets, ``d_bar``, ``pid``, ``n_keys``, ``sides``, ``close``, ``next_add`` (the bar of the next swing, -1 none).
    Nothing is filtered here: the skip rule, the time stop and the filters are applied per row (``rows_of``).
    """
    if tf not in HARMONIC_TFS:
        raise ValueError(f"{tf}: the pattern rules are on {', '.join(HARMONIC_TFS)} (PREREG 6.7)")

    def make():
        b = ctx.bars(tf)
        c = np.asarray(b.c, np.float64)
        out = HP.patterns(b.h, b.l, b.c)
        fm, cf = out["forming"], out["confirmed"]
        ev: Dict[str, Dict[str, np.ndarray]] = {}
        f = fm[fm["first_hit"].to_numpy(bool) & (fm["id"].to_numpy() <= 21)]
        f = f[~f["instance_key"].duplicated(keep="first").to_numpy(bool)]
        ev["hf"] = _table_of(f, "t_bar", c)
        first = cf[cf["first_hit"].to_numpy(bool)]
        harm = first[first["id"].to_numpy() <= 21]
        chart = first[first["id"].to_numpy() >= 22]
        ev["hc"] = _table_of(harm, "t_bar", c)
        ev["cc"] = _table_of(chart, "t_bar", c)
        ev["drawn_harmonic"] = _table_of(harm, "b0", c)
        ev["drawn_chart"] = _table_of(chart, "b0", c)
        g = fm[(fm["id"].to_numpy() >= 22) & fm["first_bar_of_instance"].to_numpy(bool)]
        ev["cf"] = _chart_per_bar(g, c)
        ev["cs"] = _armed_orders(out, np.asarray(b.tc, np.int64), c)
        return {k: {kk: _ro(vv) for kk, vv in v.items()} for k, v in ev.items()}
    return ctx.get(CACHE, tf, {"what": "events", "depth": HP.DEPTH}, make)


def rows_of(s: Spec, ctx: M.Context) -> Dict[str, np.ndarray]:
    """
    The candidates of row ``s`` before its filter: ``events``' table with the row's own rules applied.

    * HP-DRAWN SHOWN: only the first hits the overlap gate draws.
    * Levels: rows without finite levels (a zero-size pattern, L704 / L713) are dropped (none on our bars).
    * The skip rule (HP-HF, HP-HC, HP-DRAWN harmonic): the decision close at or beyond TP1 is dropped (reading 4).
    * The time stop: ``exit_bar`` = ``d_bar`` + 30; a decision at or after it is dropped; beyond the bars, -1.

    Adds ``exit_bar`` and keeps every column of the table. HP-CS's orders get ``exit_bar`` the same way.
    """
    if s.tf not in (HARMONIC_TFS if s.kind == "harmonic" else CHART_TFS):
        raise ValueError(f"{s.id}: {s.rule} is not run on {s.tf}")
    tab = events(ctx, s.tf)[s.source]
    n = len(ctx.bars(s.tf))
    keep = np.ones(len(tab["bar"]), bool)
    if s.rule == "HP-DRAWN" and s.drawn == "SHOWN":
        keep &= tab["drawn"]
    if s.rule == "HP-CS":
        keep &= np.isfinite(tab["buy"]) | np.isfinite(tab["sell"])
    else:
        keep &= np.isfinite(tab["sl"]) & np.isfinite(tab["tp1"]) & np.isfinite(tab["tp2"])
        if s.skips_past_tp1:
            with np.errstate(invalid="ignore"):
                keep &= ~(tab["side"] * (tab["close"] - tab["tp1"]) >= 0.0)
    xb = tab["d_bar"] + TIME_STOP_BARS
    keep &= xb > tab["bar"]
    out = {k: v[keep] for k, v in tab.items()}
    xb = xb[keep]
    out["exit_bar"] = np.where(xb < n, xb, -1).astype(np.int64)
    return out


def _entries_of(s: Spec, rows: Mapping[str, np.ndarray], keep: np.ndarray) -> M.Entries:
    r = {k: v[keep] for k, v in rows.items()}
    target = {"TP1": r["tp1"], "TP2": r["tp2"], "50/50": None}[s.target]
    return M.entries(r["bar"], r["side"], stop_level=r["sl"], target_level=target, exit_bar=r["exit_bar"],
                     tag=r["pid"])


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The harness's Exec of one row (see the module docstring): market entries (``M.entries``) with the plan's
    absolute SL and TP1 / TP2 (50/50: two half legs), the time stop as ``exit_bar``, gated by the row's filter at the
    decision close; HP-CS: stop orders (``M.orders``) gated at the placement close."""
    s = spec_of(variant)
    if variant.symbol != ctx.symbol:
        raise ValueError(f"{variant.id}: not a variant of {ctx.symbol}")
    rows = rows_of(s, ctx)
    al, ash = F.allow(ctx, s.tf, s.filt)
    if s.rule == "HP-CS":
        O = M.orders(rows["bar"], rows["until"], buy=rows["buy"], sell=rows["sell"], buy_stop=rows["buy_stop"],
                     sell_stop=rows["sell_stop"], buy_target=rows["buy_target"], sell_target=rows["sell_target"],
                     exit_bar=rows["exit_bar"], tag=rows["pid"])
        return M.event_exec(s.tf, orders=F.gate_orders(O, al, ash), label=variant.id)
    # the gate first, on the rows' positions, then the kept rows (so the legs' arrays line up with the entries)
    idx = M.entries(rows["bar"], rows["side"], tag=np.arange(len(rows["bar"]), dtype=np.int64))
    kept = np.zeros(len(rows["bar"]), bool)
    kept[F.gate_entries(idx, al, ash).tag] = True
    E = _entries_of(s, rows, kept)
    if s.target == "50/50":
        legs = (M.Leg(0.5, target_level=rows["tp1"][kept]), M.Leg(0.5, target_level=rows["tp2"][kept]))
        return M.event_exec(s.tf, entries=E, legs=legs, label=variant.id)
    return M.event_exec(s.tf, entries=E, label=variant.id)


# ───────────────────────────── the candidates in words and numbers (no profit) ─────────────────────────────

def table(variant: M.Variant, ctx: M.Context) -> pd.DataFrame:
    """The row's candidates as a DataFrame (event geometry and counts only, never a profit): the decision close's UTC
    time, the fill bar's open time, side, pattern id and name, the plan's levels (an order: its level, stop and
    target per side and its cancel time), D's bar time, the time stop's bar time, the detection bar's time, and
    ``allowed`` (the row's filter at the decision close)."""
    s = spec_of(variant)
    rows = rows_of(s, ctx)
    b = ctx.bars(s.tf)
    al, ash = F.allow(ctx, s.tf, s.filt)
    bar = rows["bar"]
    m1t = ctx.mk.t

    def times(s_, ok):
        return pd.Series(pd.to_datetime(np.where(ok, s_, 0), unit="s", utc=True)).where(ok)

    fill_ix = b.ex[bar]
    df = pd.DataFrame({"decision_bar": bar, "decision_close": times(b.tc[bar], np.ones(len(bar), bool)),
                       "fill_open": times(m1t[np.minimum(fill_ix, len(m1t) - 1)], fill_ix < len(m1t)),
                       "pattern_id": rows["pid"], "pattern": [HP.NAMES[int(p)] for p in rows["pid"]],
                       "d_close": times(b.tc[rows["d_bar"]], np.ones(len(bar), bool)),
                       "time_stop_close": times(b.tc[np.maximum(rows["exit_bar"], 0)], rows["exit_bar"] >= 0)})
    if s.rule == "HP-CS":
        for k in ("buy", "buy_stop", "buy_target", "sell", "sell_stop", "sell_target", "close", "n_keys"):
            df[k] = rows[k]
        df["cancel"] = times(rows["until"], rows["until"] < NEVER)
        df["allowed_buy"] = al[bar] & np.isfinite(rows["buy"])
        df["allowed_sell"] = ash[bar] & np.isfinite(rows["sell"])
        df["allowed"] = df.allowed_buy | df.allowed_sell
    else:
        for k in ("side", "close", "entry", "sl", "tp1", "tp2", "unit", "n_ids"):
            df[k] = rows[k]
        df["detected_close"] = times(b.tc[rows["t_conf"]], np.ones(len(bar), bool))
        df["drawn"] = rows["drawn"]
        df["allowed"] = np.where(rows["side"] == 1, al[bar], ash[bar])
    return df


_TF_WORDS = {"1H": "1-hour", "4H": "4-hour", "1D": "daily"}
_FILTER_WORDS = {"F0": "no filter (F0)",
                 "F1": "F1: a long only while the close is above its MA200 (same timeframe), a short only below",
                 "F2-4H": "F2-4H: a long only while the last closed 4H bar's close is above its MA200, a short only "
                          "below",
                 "F2-1D": "F2-1D: a long only while the last closed 1D bar's close is above its MA200, a short only "
                          "below",
                 "FR": "FR: a long only while the Trend Target Ribbon's trend of the higher timeframe is up (1H rows: "
                       "the last closed 4H bar's, 4H: the last closed 1D bar's, 1D: the 1D ribbon), a short only while "
                       "it is down"}


def describe(variant: M.Variant) -> str:
    """The row in words (for FINALISTS.md)."""
    s = spec_of(variant)
    head = (f"{_TF_WORDS[s.tf]} bars of the bid (UTC); AI-AlgoCode's Harmonic & Chart Patterns, zigzag depth 5, all "
            "38 patterns, the script's ratio windows and first-hit order")
    if s.rule == "HP-HF":
        ev = ("HP-HF: at the first bar close where a harmonic pattern is forming on the live zigzag (the script's "
              "forming first hit), once per pattern instance, a market entry in its direction; stop D - dir x 0.13 x "
              "AD; skipped when the close is already at or beyond TP1")
    elif s.rule == "HP-HC":
        ev = ("HP-HC (control): at the close of the bar whose new swing confirms a pattern whose first hit is a "
              "harmonic (the script's alert), a market entry in its direction; stop D - dir x 0.13 x AD; skipped when "
              "the close is already at or beyond TP1")
    elif s.rule == "HP-CF":
        ev = ("HP-CF: at the first bar close where a chart pattern (any of the 16, reversal or continuation) is "
              "forming with the close beyond its neckline p2, once per instance, a market entry in its direction; "
              "stop p2 - dir x 0.5 x h")
    elif s.rule == "HP-CS":
        ev = ("HP-CS: once every condition of a chart pattern but the breakout close holds (at the close of the bar "
              "that adds the latest swing), a stop order at the neckline p2 in its direction, valid until the next "
              "swing is added or 30 bars after D; stop p2 - dir x 0.5 x h")
    elif s.rule == "HP-CC":
        ev = ("HP-CC (control): at the close of the bar whose new swing confirms a pattern whose first hit is a chart "
              "pattern (the script's alert), a market entry in its direction; stop p2 - dir x 0.5 x h")
    else:
        which = "every confirmed first hit" if s.drawn == "ALL" else "the confirmed first hits the script draws"
        stop = ("stop D - dir x 0.13 x AD; skipped when that close is already at or beyond TP1" if s.kind == "harmonic"
                else "stop p2 - dir x 0.5 x h")
        ev = (f"HP-DRAWN (information only, look-ahead): {which} ({s.kind}), entered at the close of point D's bar "
              f"although it is only known when the next swing forms, with the script's levels; {stop}")
    unit = "AD" if s.kind == "harmonic" else "h"
    base = "D" if s.kind == "harmonic" else "p2"
    k1, k2 = (HP.TP1_K, HP.TP2_K) if s.kind == "harmonic" else (HP.CTP1_K, HP.CTP2_K)
    tgt = {"TP1": f"target TP1 = {base} + dir x {k1:g} x {unit}", "TP2": f"target TP2 = {base} + dir x {k2:g} x {unit}",
           "50/50": f"half at TP1 = {base} + dir x {k1:g} x {unit}, half at TP2 = {base} + dir x {k2:g} x {unit}"
                    " (two legs; live at least 0.02 lot per unit)"}[s.target]
    when = "at the order's placement close" if s.rule == "HP-CS" else "at the decision close"
    return (f"{head}. {ev}; {tgt}; time stop at the close of the 30th bar after D; {_FILTER_WORDS[s.filt]}, checked "
            f"{when}. An event rule: one position at a time, a candidate during an open trade is "
            "skipped; the absolute stop and target become distances from the actual fill, and an entry whose fill is "
            "at or beyond either is dropped. Decided at the close of a signal bar, filled at the open of the next M1 "
            "bar (a buy at the ask, a sell at the bid)" + (" or, for the stop order, at max(p2, ask) / min(p2, bid)"
                                                          if s.rule == "HP-CS" else ""))


def warm(ctx: M.Context, variants_: Iterable[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, what the rows read: the patterns' candidate tables
    of each timeframe and the filters (the workers then share them copy-on-write)."""
    for v in variants_:
        s = spec_of(v)
        events(ctx, s.tf)
        F.allow(ctx, s.tf, s.filt)
