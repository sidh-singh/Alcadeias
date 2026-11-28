"""
TradeIQ study 2: the rule rows of the Market Structure Dashboard (Flux Charts), PREREG section 6.2.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_msd as R
    ctx = M.Context(M.load("XAUUSDm"))           # served to the hold-out start until FINALISTS.md is frozen
    vs = R.variants("XAUUSDm")                   # the 150 rows of PREREG 6.2 for one symbol
    ex = R.build(vs[0], ctx)                     # a STATE Exec: study 1's tradeiq_market.run, exactly
    res = M.run_variant(ctx, vs[0], ex)          # Development, Validation and D+V at x1.0 and x1.5
    R.study1_ids(vs[18])                         # the first MSD-F4 row: its study-1 rows F0, F1, F2-4H, F2-1D
    rows = R.claim14(ev)                         # PREREG 8 claim 14 on a tradeiq2.Evidence (the driver's extra)

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen): section 4 (execution), 5 (filters: how a filter
applies to a state rule), 6.2 (these rules) and 7 (families, eligibility), read with ``DEVIATIONS.md``. The
dashboard is the reconciled port ``tradeiq2_ind_msd`` (port A; ``porting/msd.md``); the filters are
``tradeiq2_filters``; the base rules of MSD-F4 / MSD-F6 are study 1's own functions (``tradeiq.lines_of``,
``tradeiq.raw_state``, ``tradeiq_market.s1_stop``), imported, never edited. The execution is ``tradeiq2_market``'s
``state_exec`` without overlays, which is study 1's ``tradeiq_market.run`` itself.

The rows (all STATE rules, all eligible; ids ``symbol|tf|family|rule|...``)
--------------------------------------------------------------------------
The state of each chart bar is decided at its close:

* MSD-ALONE (18 rows: 3 rules x S0, S1 x 1H, 4H, 1D):
  - MSD-A1: +1 at LEAN BULL or BULLISH (label >= +1), -1 at LEAN BEAR or BEARISH (label <= -1), 0 at NEUTRAL;
  - MSD-A2: MSD-A1 with the short state flat (long only);
  - MSD-A3: +1 at BULLISH (+2), -1 at BEARISH (-2), else 0.
* MSD-FILTER (120 rows): study 1's R1 / R2 state of RSI, LaRSI, VWRSI (BTC: VWRSI-RV), TSI or QQE (5 x 2 x S0, S1
  x 3 timeframes = 60 bases), under
  - MSD-F4: FS as a state filter (60 rows);
  - MSD-F6: the video's veto (60 rows): a long is flat while the 4H, D and W rows all score below 0 (1D chart: D
    and W), a short while they all score above 0.
* BOS (12 rows): BOS-trend, the side of the chart row's latest break of structure; LS or LO, F0 or F1, S1 only
  (2 x 2 x 3 timeframes).

That is 18 + 120 + 12 = 150 rows per symbol (PREREG 6.2, "Size"). Ids:
``XAUUSDm|1H|MSD-ALONE|MSD-A1|S0``, ``BTCUSDm|4H|MSD-FILTER|MSD-F6|VWRSI-RV|R2|S1``,
``XAUUSDm|1D|BOS|BOS-trend|LO|F1|S1``. The MSD-FILTER ids carry study 1's indicator, family and stop tokens, so
``study1_ids`` gives the study-1 rows each is paired with: F0, F1, F2-4H, F2-1D on 1H; F0, F1, F2-1D on 4H; F0, F1 on
1D (study 1's ``grid.csv`` ids, e.g. ``BTCUSDm|4H|VWRSI-RV|R2|F2-1D|S1``). Their published results are reused, not
rerun (PREREG 6.2).

The dashboard, as the rules read it (Pine line numbers of the owner's copy; ``tradeiq2_ind_msd``'s docstring)
--------------------------------------------------------------------------------------------------------------
* The bias label (L1343-1344): ``biasPct = biasPoints / maxScore * 100`` against 50 / 20 / -50 / -20, strict, in
  the port's integer form: +2 BULLISH, +1 LEAN BULL, 0 NEUTRAL, -1 LEAN BEAR, -2 BEARISH (``out['label']``).
* The rows at or above the chart (L692): 1H chart 1H, 4H, D, W; 4H chart 4H, D, W; 1D chart D, W; weights 2, 2, 3,
  4 (L76-88). Built from ``ctx.bars('1H' | '4H' | '1D' | '1W')`` (the harness's 1W bars = ``weekly_bars``,
  DEVIATIONS 1), the same rows ``tradeiq2_filters``' FS reads.
* Model A (PREREG 6.2): a higher row takes the values of its last CLOSED bar, the one whose close time is at or
  before the chart bar's close (``htf_at``). The live script reads the forming bar (it repaints); model A is what
  TradingView shows on historical bars.
* A row's score (MSD-F6) is ``calcBiasForTf`` (L710-721) without its weight: ``dirScore(structBias) +
  dirScore(obDir) + dirScore(fvgDir) + swingDir`` (the EMA factor is off by default, L121), in [-4, 4]: the port's
  ``s_<row>``. Its swing vote uses the CHART close against the row's swing high and low (``swingBiasDir``,
  L705-708, called at L1330, outside ``request.security``), so it is the score the dashboard on that chart shows. A
  row with no closed bar yet scores 0 (``dirScore(na)``, L703).
* The break of structure (BOS-trend): ``trackPivotBreaks`` of the chart row (L537-565; the chart-level call of L633):
  a close above the last unbroken 5/5 pivot high with the previous close at or below it is bullish (+1), the mirror
  bearish (-1), each pivot breaks once (``out['bos']``). BOS-trend's state is ``out['bos_trend']``, the side of the
  latest break, 0 before the first one (in the warm-up only; it is never 0 from 2019 on, ``porting/msd.md`` 6).

What is known when (no look-ahead)
----------------------------------
Every state of chart bar j is known at its close ``tc[j]``: the chart row's bar j, each higher row's last bar closed
by then (model A), study 1's lines and filters of bar j, the ATR of bar j. The harness fills the decision at the
open of the first M1 bar at or after ``tc[j]`` (``bars.ex[j]``; a buy at the ask, a sell at the bid). Pivots are
known 5 row bars after their bar, an order block at the close of its break bar, a fair value gap one bar after its
third candle; a forming week (a data end inside a week) is never read as closed (DEVIATIONS 1). The tests check that
every state up to a time T is unchanged when the data after T is removed.

Execution (PREREG 4, 5; study 1's DEVIATIONS 1-7)
-------------------------------------------------
* Every row is a STATE rule run by ``M.state_exec(tf, state, stop)`` with no overlay, i.e. ``tradeiq_market.run``:
  an entry only where the state changes (and at a window's first bar, which takes the state), the exit at the close
  where it changes again, a flip at the same M1 open, whatever is open at the window's end closed at its last M1
  close; after a stop the rule stays flat until its state changes (study 1's DEVIATIONS 1).
* S0: no stop. S1: study 1's ``tradeiq_market.s1_stop``, 3 x ATR(14) (Pine ``ta.atr``, Wilder RMA seeded with an
  SMA) of the signal bars, taken at the entry's decision bar and set from the actual fill, never moved; checked on
  every M1 bar, one extra spread on a stop fill; the x1.5 run sets it from its own fill. No absolute stop or target
  level and no target, break-even or partial exit exists in these rows, so section 4's absolute-level rules have
  nothing to act on here.
* Filters on state rules (PREREG 5): a state the filter does not allow becomes flat (``tradeiq2_filters
  .as_state_filter``, study 1's ``apply_filter``), so the position closes when the filter turns against it and opens
  where it turns in favour while the base is on that side. FS = ``tradeiq2_filters.allow(ctx, tf, 'FS')`` (long at
  label >= +1, short at <= -1); F1 = the same module's F1 (the close against the MA200 of the same timeframe);
  MSD-F6's veto is computed here from the dashboard's row scores.

Readings where PREREG 6.2 leaves a choice (written before any result of these rows exists)
-----------------------------------------------------------------------------------------
1. MSD-F6, "all score below 0": every row of the veto has ``s_row < 0`` (strict; a row at 0 does not veto, so
   neither does a row that has no closed bar yet). The rows are 4H, D and W on the 1H and the 4H chart, D and W on
   the 1D chart, read from the dashboard of the signal chart; the 1H row of a 1H chart takes no part in the veto. The
   video: "If the 4hour, the daily, and the weekly all say bearish, I don't take a long" (chapter 8). The script
   shows no bias per row, so "says bearish" is the row's score below 0, as the PREREG writes it.
2. MSD-A3 trades both sides, as MSD-A1 does ("as A1, at BULLISH or BEARISH only").
3. The base states of MSD-F4 / MSD-F6 are computed with study 1's ``lines_of`` / ``raw_state`` on the study-2 market.
   Gold's market starts in 2016 here (study 1's in 2017). What the test compares (``tests/test_tradeiq2_rules_msd.py``,
   real data, both symbols, 1H, 4H and 1D), against study 1's ``Study`` on study 1's own market: the bars (open and
   close times, OHLC, tick volume) on study 1's whole span; and on every bar closing after 2019-01-01 00:00 up to the
   hold-out start, every array ``lines_of`` returns (14 on gold, 17 on BTC) and S1's distance, bit for bit (the same
   dtype, floats by their 64-bit patterns), each MSD-FILTER row's base state against study 1's F0 row of that base,
   and the row's state against study 1's ``apply_filter`` of it. So these are study 1's states on every bar from 2019
   (Development, Validation and the hold-out); gold's Early window (exam 2) differs until 2017-03-29 (reading 6).
   BTC's VWRSI is study 1's "VWRSI-RV" (Binance BTCUSDT spot volume, PREREG 6.2), gold's VWRSI the tick-volume one.
4. BOS-trend's F1 is a state filter (it is a state rule): long only while the close is above the MA200 of the same
   timeframe, short only while below; BOS-trend runs with S1 only (PREREG 6.2).
5. All 150 rows are eligible: section 6.2 marks none "not eligible" or "information only", and section 7's totals
   (738 gold, 720 BTC eligible) count all of them.
6. The data start (information: measured, not asserted by a test). Gold's base states on the study-2 market (from
   2016) and on study 1's market (from 2017) differ only inside study 1's own warm-up: on at most 57 bars of a series,
   all closing on or before 2017-03-29. S1's distance is missing on study 1's first 13 bars of each series (its ATR's
   warm-up) and after them differs in its last bits only, until 2018-09-14 (1D). The lines differ in their last bits
   until 2018-12-25 (the 1D VWRSI; on 1H until 2017-01-31, on 4H until 2017-05-03). This touches gold's Early window
   (exam 2) only, where study 1 has no result to pair with. BTC's two markets start together (2018-01-01) and differ
   nowhere. The dashboard's own dependence on the data start (BTC's D and W rows until 2019-06-30, gold's until
   2018-05-19) is the port's: ``porting/msd.md``, sections 6 and 8 (entries 3 and 4).

Claim 14 (PREREG 8): "its higher-timeframe rows use the forming candle and can change"
---------------------------------------------------------------------------------------
``claim14(ev)`` is the driver's extra (``tradeiq2.EXTRAS['claim14']``). PREREG's test is "the share of chart closes
inside a higher-timeframe bar where the forming-bar score differs from the closed one". It is read as follows
(``porting/msd.md`` section 8, entry 8; DEVIATIONS MSD-P8 and MSD-C14), per symbol, chart and higher row (1H chart: 4H,
D, W; 4H chart: D, W; 1D chart: W), in each of the evidence's two windows:

* The forming-bar score at a chart close is model B's ``s_<row>`` (``dashboard(ctx, tf, "B")``). The row's state after
  its last closed bar is stepped once on the forming candle: the open of its first chart bar, the high and the low so
  far and the chart close. The swing vote uses the chart close. This is what the live dashboard shows.
* The closed one is the score the row bar ends with (``closed_score``): its own committed values (``row_values``) with
  the swing vote at its own close. Where a chart bar closes with the row bar, this is model A's ``s_<row>`` on that
  chart bar. Gold's week, its Friday day bar and its Friday 20:00 4H bar close at Saturday 00:00 UTC, when no chart
  bar closes, so there only the row's own values can supply it.
* The chart closes counted are those strictly inside a row bar (``forming_bar``): the row bar opened at or before the
  chart bar's open and closes after the chart bar's close. The chart bar must lie inside the window, and the row bar
  must be complete and also lie inside the window (``ev.in_window`` of both; the first follows from the second), so
  the closed score, the outcome, is inside the window too. A chart close at the row bar's own close is left out:
  there the live score is the closed one by construction. "Inside" is read by the clock. Gold's last 1H bar before
  the weekend (closing at 21:00 or 22:00 UTC) is inside its 4H, D and W bars, but no data come after it, so its
  forming candle is already the whole bar. It is counted, and it agrees by construction. So does every counted close
  after which no data come in its higher bar: before a weekend, a holiday or early close, or a data hole (in
  Development 234 / 213 / 208 gold 1H closes for the 4H / D / W rows, 11 / 8 gold 4H closes for D / W, and on BTC
  6 / 5 / 0 and 1 / 0).
* The verdict, fixed before any count existed: "can change" states a possibility, so a row's part holds in a window
  when the share is above 0 (at least one counted close differs). It fails when the share is 0 or nothing is counted.
  A cut above 0 (5%, 10%) would be ours, not the claim's. The share and the number of row bars that change at least
  once are reported, so the size is visible. The claim's first half, that the rows use the forming candle, is the
  script's code (``request.security`` on realtime bars); history cannot show it, and model B is built on it.
* For information, per chart (no verdict): the label the live dashboard shows (model B) against the label the chart's
  history shows for the same bar (model A), and MSD-A1's long / flat / short side under each. These are counted over
  the chart closes in the window that lie strictly inside a bar of at least one higher row (elsewhere the two models
  are equal by construction).
* A check before counting: at the last chart bar inside each row bar of the windows, the forming score must equal the
  closed score (the chart bars tile the row bar, so the forming candle is the whole bar there). Otherwise
  ``claim14`` raises ``AssertionError``.

The closed score of a row bar is known only at that bar's close. It is a measurement and no state reads it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

import numpy as np

from . import tradeiq as T1
from . import tradeiq_market as TM
from . import tradeiq2_filters as F
from . import tradeiq2_ind_msd as MS
from . import tradeiq2_market as M

__all__ = [
    "SCRIPT", "FAMILIES", "TFS", "STOPS", "ALONE_RULES", "FILTER_RULES", "BOS_RULE", "RULES", "BASE_INDICATORS",
    "BASE_FAMILIES", "BOS_SIDES", "BOS_FILTERS", "ROWS", "VETO_ROWS", "STUDY1_FILTERS", "COUNTS", "Spec",
    "variants", "build", "spec_of", "state_of", "study1_ids", "describe", "warm", "dashboard", "alone_state",
    "veto_allow", "bos_state", "base_indicator", "base_state", "study1_lines", "s1_stop", "filter_allow",
    "HIGHER_ROWS", "closed_score", "forming_bar", "forming_counts", "claim14",
]

SCRIPT = "MSD"
CACHE = "rules_msd"                                  # this module's key in the Context's cache
FAMILIES = ("MSD-ALONE", "MSD-FILTER", "BOS")       # PREREG 7's families of this script
TFS = ("1H", "4H", "1D")                            # PREREG 6.2: "on 1H, 4H and 1D"
STOPS = ("S0", "S1")
ALONE_RULES = ("MSD-A1", "MSD-A2", "MSD-A3")
FILTER_RULES = ("MSD-F4", "MSD-F6")
BOS_RULE = "BOS-trend"
RULES = ALONE_RULES + FILTER_RULES + (BOS_RULE,)
BASE_INDICATORS = ("RSI", "LaRSI", "VWRSI", "TSI", "QQE")    # study 1's five oscillators (BTC's VWRSI: VWRSI-RV)
BASE_FAMILIES = ("R1", "R2")                                 # study 1's R1 (both sides), R2 (long only)
BOS_SIDES = ("LS", "LO")
BOS_FILTERS = ("F0", "F1")
BOS_STOPS = ("S1",)
ROWS: Mapping[str, Tuple[str, ...]] = F.MSD_ROWS     # the dashboard's rows per chart (L692), as FS reads them
VETO_ROWS: Dict[str, Tuple[str, ...]] = {"1H": ("4H", "1D", "1W"), "4H": ("4H", "1D", "1W"), "1D": ("1D", "1W")}
# PREREG 6.2: "Paired with study 1's F0, F1 and F2 rows of the same base" (study 1's F2 of each timeframe)
STUDY1_FILTERS: Dict[str, Tuple[str, ...]] = {"1H": ("F0", "F1", "F2-4H", "F2-1D"), "4H": ("F0", "F1", "F2-1D"),
                                              "1D": ("F0", "F1")}
# PREREG 6.2 "Size: 18 alone + 60 MSD-F4 + 60 MSD-F6 + 12 BOS-trend = 150 rows per symbol"
COUNTS: Dict[str, int] = {"MSD-ALONE": 18, "MSD-FILTER": 120, "BOS": 12}
_ALONE_LEVEL = {"MSD-A1": 1, "MSD-A2": 1, "MSD-A3": 2}      # |label| needed: LEAN (1) or the full label (2)
_ALONE_SIDES = {"MSD-A1": "LS", "MSD-A2": "LO", "MSD-A3": "LS"}
_FILTER_OF = {"MSD-F4": "FS", "MSD-F6": "MSD-F6"}


@dataclass(frozen=True)
class Spec:
    """One row of the grid, parsed: ``rule`` (MSD-A1 .. BOS-trend), ``tf``, ``family``; ``indicator`` and
    ``base_family`` (study 1's) for MSD-FILTER rows; ``sides`` (LS / LO); ``filt`` (F0, F1, FS, MSD-F6); ``stop``."""
    symbol: str
    tf: str
    family: str
    rule: str
    stop: str
    sides: str = "LS"
    filt: str = "F0"
    indicator: str = ""
    base_family: str = ""

    @property
    def id(self) -> str:
        head = f"{self.symbol}|{self.tf}|{self.family}|{self.rule}"
        if self.family == "MSD-ALONE":
            return f"{head}|{self.stop}"
        if self.family == "MSD-FILTER":
            return f"{head}|{self.indicator}|{self.base_family}|{self.stop}"
        return f"{head}|{self.sides}|{self.filt}|{self.stop}"

    @property
    def state_key(self) -> Dict[str, str]:
        """What decides the state (the stop does not): the cache key of ``state_of``."""
        return {"rule": self.rule, "sides": self.sides, "filt": self.filt, "indicator": self.indicator,
                "base_family": self.base_family}

    def params(self) -> Dict[str, object]:
        p: Dict[str, object] = {"rule": self.rule, "kind": "state", "filter": self.filt, "stop": self.stop,
                                "model": "A"}
        if self.family == "MSD-ALONE":
            p.update(sides=self.sides, min_label=_ALONE_LEVEL[self.rule])
        elif self.family == "MSD-FILTER":
            p.update(indicator=self.indicator, base_family=self.base_family, sides=self.sides)
        else:
            p.update(sides=self.sides)
        return p

    def variant(self) -> M.Variant:
        return M.Variant(self.id, self.symbol, self.tf, SCRIPT, self.family, True, "", self.params())


def base_indicator(symbol: str, indicator: str) -> str:
    """Study 1's indicator name of a base rule: BTC's VWRSI is the Binance-volume "VWRSI-RV" (PREREG 6.2)."""
    if indicator not in BASE_INDICATORS:
        raise ValueError(f"{indicator}: not one of the base oscillators ({', '.join(BASE_INDICATORS)})")
    return T1.RV if (indicator == "VWRSI" and T1.has_rv(symbol)) else indicator


def _specs(symbol: str) -> List[Spec]:
    if symbol not in M.SYMBOLS:
        raise ValueError(f"{symbol}: PREREG 6.2's rows are on {' and '.join(M.SYMBOLS)} only")
    out: List[Spec] = []
    for rule in ALONE_RULES:
        for tf in TFS:
            for stop in STOPS:
                out.append(Spec(symbol, tf, "MSD-ALONE", rule, stop, sides=_ALONE_SIDES[rule]))
    for rule in FILTER_RULES:
        for tf in TFS:
            for ind in BASE_INDICATORS:
                for fam in BASE_FAMILIES:
                    for stop in STOPS:
                        out.append(Spec(symbol, tf, "MSD-FILTER", rule, stop, sides="LS" if fam == "R1" else "LO",
                                        filt=_FILTER_OF[rule], indicator=base_indicator(symbol, ind),
                                        base_family=fam))
    for tf in TFS:
        for sides in BOS_SIDES:
            for filt in BOS_FILTERS:
                for stop in BOS_STOPS:
                    out.append(Spec(symbol, tf, "BOS", BOS_RULE, stop, sides=sides, filt=filt))
    return out


_SPEC_CACHE: Dict[str, Dict[str, Spec]] = {}


def _spec_table(symbol: str) -> Dict[str, Spec]:
    if symbol not in _SPEC_CACHE:
        specs = _specs(symbol)
        table = {s.id: s for s in specs}
        if len(table) != len(specs):
            raise AssertionError("duplicate ids in the MSD grid")
        _SPEC_CACHE[symbol] = table
    return _SPEC_CACHE[symbol]


def variants(symbol: str) -> List[M.Variant]:
    """
    Exactly PREREG 6.2's rows of ``symbol`` (XAUUSDm or BTCUSDm), in the plan's order: MSD-A1, A2, A3 (x 1H, 4H, 1D x
    S0, S1); MSD-F4 then MSD-F6 (x 1H, 4H, 1D x RSI, LaRSI, VWRSI / VWRSI-RV, TSI, QQE x R1, R2 x S0, S1); BOS-trend
    (x 1H, 4H, 1D x LS, LO x F0, F1, S1). 150 rows, every one eligible, script "MSD", families MSD-ALONE (18),
    MSD-FILTER (120) and BOS (12).
    """
    return [s.variant() for s in _spec_table(symbol).values()]


def spec_of(variant: M.Variant) -> Spec:
    """The registered row behind ``variant`` (its id is the identity; a grid row rebuilt from grid.csv works too)."""
    table = _spec_table(variant.symbol)
    s = table.get(variant.id)
    if s is None:
        raise ValueError(f"{variant.id}: not a row of PREREG 6.2 (tradeiq2_rules_msd.variants)")
    if variant.tf != s.tf or variant.family != s.family or variant.script != SCRIPT:
        raise ValueError(f"{variant.id}: tf / family / script {variant.tf} / {variant.family} / {variant.script} "
                         f"differ from the registered row's {s.tf} / {s.family} / {SCRIPT}")
    return s


# ───────────────────────────── the pieces (cached in the Context) ─────────────────────────────

def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def dashboard(ctx: M.Context, tf: str, model: str = "A") -> Dict[str, np.ndarray]:
    """The dashboard on chart ``tf`` for every bar of ``ctx.bars(tf)``: ``tradeiq2_ind_msd.structure_dashboard`` on
    the rows ``ROWS[tf]`` taken from ``ctx.bars`` (label, score, the rows' scores ``s_<r>`` and votes, ``bos``,
    ``bos_trend``). Read-only arrays, cached. ``model`` "A" (each higher row from its last closed bar) is what every
    row of the grid reads; "B" (each higher row on its forming bar: the live dashboard) is for claim 14 only."""
    if tf not in TFS:
        raise ValueError(f"{tf}: the dashboard's rules are on {', '.join(TFS)} charts (PREREG 6.2)")
    if model not in ("A", "B"):
        raise ValueError(f"model {model!r}: 'A' (the rows) or 'B' (claim 14)")

    def make():
        out = MS.structure_dashboard({r: ctx.bars(r) for r in ROWS[tf]}, tf, model=model)
        n = len(ctx.bars(tf))
        res = {}
        for k, v in out.items():
            a = np.asarray(v)
            if a.shape != (n,):
                raise AssertionError(f"dashboard {k}: shape {a.shape}, the {tf} bars {n}")
            res[k] = _ro(a)
        return res
    return ctx.get(CACHE, tf, {"what": "dashboard", "model": model}, make)


def alone_state(label, rule: str) -> np.ndarray:
    """MSD-A1 / A2 / A3 from the bias label (-2 .. +2): A1 +1 at label >= 1, -1 at <= -1, else 0; A2 the same long
    only; A3 +1 at +2 (BULLISH), -1 at -2 (BEARISH), else 0. int8."""
    if rule not in ALONE_RULES:
        raise ValueError(f"{rule}: not one of {', '.join(ALONE_RULES)}")
    lab = np.asarray(label, np.int64)
    k = _ALONE_LEVEL[rule]
    st = np.where(lab >= k, 1, np.where(lab <= -k, -1, 0))
    if _ALONE_SIDES[rule] == "LO":
        st = np.maximum(st, 0)
    return st.astype(np.int8)


def veto_allow(dash: Mapping[str, np.ndarray], tf: str) -> Tuple[np.ndarray, np.ndarray]:
    """MSD-F6's (allow_long, allow_short) per chart bar: a long is not allowed while every row of ``VETO_ROWS[tf]``
    scores below 0 (``s_<row> < 0``), a short while every one scores above 0 (reading 1 of the module docstring)."""
    if tf not in VETO_ROWS:
        raise ValueError(f"{tf}: MSD-F6 is defined on {', '.join(VETO_ROWS)} charts")
    s = np.stack([np.asarray(dash[f"s_{r}"], np.int64) for r in VETO_ROWS[tf]])
    return ~np.all(s < 0, axis=0), ~np.all(s > 0, axis=0)


def bos_state(bos_trend, sides: str) -> np.ndarray:
    """BOS-trend from the chart row's ``bos_trend`` (+1 after a bullish break, -1 after a bearish one, 0 before the
    first): LS as it is, LO with the short state flat. int8."""
    bt = np.asarray(bos_trend, np.int64)
    if not np.all(np.isin(bt, (-1, 0, 1))):
        raise ValueError("bos_trend must be -1, 0 or +1")
    if sides == "LS":
        return bt.astype(np.int8)
    if sides == "LO":
        return np.maximum(bt, 0).astype(np.int8)
    raise ValueError(f"sides {sides!r}: LS or LO")


def study1_lines(ctx: M.Context, tf: str) -> Dict[str, np.ndarray]:
    """Study 1's lines of ``tf`` (``tradeiq.lines_of``: RSI, LaRSI, VWRSI, TSI, QQE, MA200 with the scripts' defaults,
    and on BTC the VWRSI on Binance volume) on the context's market, read-only, cached."""
    def make():
        return {k: _ro(v) for k, v in T1.lines_of(ctx.mk, tf).items()}
    return ctx.get(CACHE, tf, {"what": "study1_lines"}, make)


def base_state(ctx: M.Context, tf: str, indicator: str, family: str) -> np.ndarray:
    """Study 1's unfiltered state of ``indicator`` (study 1's name: RSI, LaRSI, VWRSI, VWRSI-RV, TSI, QQE) and
    ``family`` (R1, R2) on ``tf``: ``tradeiq.raw_state`` of ``study1_lines`` (= study 1's F0 row's state). Cached."""
    if family not in BASE_FAMILIES:
        raise ValueError(f"{family}: the base rules are {', '.join(BASE_FAMILIES)}")
    if indicator == T1.RV and not T1.has_rv(ctx.symbol):
        raise ValueError(f"{T1.RV} exists on BTC only")
    return ctx.get(CACHE, tf, {"what": "base", "indicator": indicator, "family": family},
                   lambda: _ro(T1.raw_state(study1_lines(ctx, tf), indicator, family)))


def s1_stop(ctx: M.Context, tf: str) -> np.ndarray:
    """S1's distance per bar: study 1's ``tradeiq_market.s1_stop`` (3 x Wilder ATR(14) of ``tf``), cached."""
    return ctx.get(CACHE, tf, {"what": "s1"}, lambda: _ro(TM.s1_stop(ctx.bars(tf))))


def filter_allow(ctx: M.Context, tf: str, filt: str) -> Tuple[np.ndarray, np.ndarray]:
    """(allow_long, allow_short) of a filter these rows use: F0, F1 and FS from ``tradeiq2_filters``, MSD-F6's veto
    from the dashboard (``veto_allow``)."""
    if filt in ("F0", "F1", "FS"):
        return F.allow(ctx, tf, filt)
    if filt == "MSD-F6":
        def make():
            al, ash = veto_allow(dashboard(ctx, tf), tf)
            return _ro(al), _ro(ash)
        return ctx.get(CACHE, tf, {"what": "veto"}, make)
    raise ValueError(f"{filt}: not a filter of PREREG 6.2's rows")


def _make_state(s: Spec, ctx: M.Context) -> np.ndarray:
    if s.family == "MSD-ALONE":
        return alone_state(dashboard(ctx, s.tf)["label"], s.rule)
    if s.family == "MSD-FILTER":
        return F.as_state_filter(base_state(ctx, s.tf, s.indicator, s.base_family), *filter_allow(ctx, s.tf, s.filt))
    st = bos_state(dashboard(ctx, s.tf)["bos_trend"], s.sides)
    if s.filt == "F0":
        return st
    return F.as_state_filter(st, *filter_allow(ctx, s.tf, s.filt))


def state_of(variant: M.Variant, ctx: M.Context) -> np.ndarray:
    """The row's state per bar of ``ctx.bars(variant.tf)`` (+1 / 0 / -1, int8, read-only, cached; the stop does not
    change it)."""
    s = spec_of(variant)
    if variant.symbol != ctx.symbol:
        raise ValueError(f"{variant.id}: not a variant of {ctx.symbol}")
    st = ctx.get(CACHE, s.tf, {"what": "state", **s.state_key}, lambda: _ro(_make_state(s, ctx)))
    if st.shape != (len(ctx.bars(s.tf)),):
        raise AssertionError(f"{variant.id}: state of shape {st.shape}")
    return st


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The harness's Exec of one row: ``M.state_exec(tf, state, stop)`` with S1's distance per bar or no stop, no
    overlay (study 1's ``run``; see the module docstring)."""
    s = spec_of(variant)
    st = state_of(variant, ctx)
    stop = s1_stop(ctx, s.tf) if s.stop == "S1" else None
    return M.state_exec(s.tf, st, stop=stop, label=variant.id)


def study1_ids(variant: M.Variant) -> Dict[str, str]:
    """{study-1 filter: study-1 id} of the rows an MSD-F4 / MSD-F6 row is paired with (PREREG 6.2: study 1's F0, F1
    and F2 rows of the same base: indicator, family, stop and timeframe); {} for the other rows."""
    s = spec_of(variant)
    if s.family != "MSD-FILTER":
        return {}
    return {f: T1.Variant(s.symbol, s.tf, s.indicator, s.base_family, f, s.stop).vid for f in STUDY1_FILTERS[s.tf]}


# ───────────────────────────── words and warming ─────────────────────────────

_TF_WORDS = {"1H": "1-hour", "4H": "4-hour", "1D": "daily"}
_ROW_WORDS = {"1H": "1H", "4H": "4H", "1D": "D", "1W": "W"}
_LINE_WORDS = {"RSI": "RSI(14) of the close (middle 50)", "LaRSI": "100 x Laguerre RSI (alpha 0.2) (middle 50)",
               "VWRSI": "AlgoAlpha's volume-weighted RSI on tick volume (middle 50)",
               T1.RV: "AlgoAlpha's volume-weighted RSI on Binance BTCUSDT spot volume (middle 50)",
               "TSI": "Bjorgum TSI Fast (5, 25) (middle 0)",
               "QQE": "QQE MOD's colour (BLUE long, RED short, GRAY keeps the side)"}


def _and(words) -> str:
    words = list(words)
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def describe(variant: M.Variant) -> str:
    """The row in words (for FINALISTS.md)."""
    s = spec_of(variant)
    rows = ", ".join(_ROW_WORDS[r] for r in ROWS[s.tf])
    if s.family == "BOS":
        head = (f"{_TF_WORDS[s.tf]} bars of the bid (UTC); the Market Structure Dashboard's structure engine on the "
                f"{s.tf} row (breaks of structure of its 5 / 5 pivots)")
    else:
        head = (f"{_TF_WORDS[s.tf]} bars of the bid (UTC); the Market Structure Dashboard's bias on the {s.tf} chart "
                f"(rows {rows}; each higher row from its last closed bar, model A)")
    if s.family == "MSD-ALONE":
        lvl = "LEAN BULL or BULLISH" if _ALONE_LEVEL[s.rule] == 1 else "BULLISH"
        lvs = "LEAN BEAR or BEARISH" if _ALONE_LEVEL[s.rule] == 1 else "BEARISH"
        rule = (f"{s.rule}: long while the label is {lvl}" +
                (f", short while it is {lvs}" if s.sides == "LS" else ", flat otherwise (long only)") +
                ("" if s.sides == "LO" else ", flat otherwise"))
    elif s.family == "MSD-FILTER":
        fam = "both sides (R1)" if s.base_family == "R1" else "long only (R2)"
        base = f"study 1's {s.indicator} {s.base_family} state: {_LINE_WORDS[s.indicator]}, {fam}"
        if s.rule == "MSD-F4":
            rule = (f"{s.rule}: {base}; a long allowed only while the label is LEAN BULL or BULLISH, a short only "
                    "while it is LEAN BEAR or BEARISH (FS as a state filter)")
        else:
            vr = _and(_ROW_WORDS[r] for r in VETO_ROWS[s.tf])
            rule = (f"{s.rule}: {base}; a long is flat while the {vr} rows all score below 0, a short while they "
                    "all score above 0 (the video's veto, a state filter)")
    else:
        f1 = ""
        if s.filt == "F1":
            f1 = ("; filter F1: a long only while the close is above its MA200 (same timeframe)" +
                  (", a short only while it is below" if s.sides == "LS" else ""))
        rule = (f"{s.rule}: long after a bullish break of structure of the {s.tf} row, " +
                ("short after a bearish one" if s.sides == "LS" else "flat after a bearish one (long only)") + f1)
    stop = ("a fixed stop 3 x ATR(14) of the signal timeframe from the entry fill (study 1's S1), after which the "
            "rule stays flat until its state changes" if s.stop == "S1" else "no stop (S0)")
    return (f"{head}. {rule}. A state rule: in at the close where the state turns, out where it changes; {stop}. "
            "Decided at the close of a signal bar, filled at the open of the first M1 bar at or after that close (a "
            "buy at the ask, a sell at the bid)")


def warm(ctx: M.Context, variants_: Iterable[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, what the rows read: the dashboards, study 1's
    lines, the filters, the S1 distances and every row's state (the workers then share them copy-on-write)."""
    for v in variants_:
        state_of(v, ctx)
        if spec_of(v).stop == "S1":
            s1_stop(ctx, v.tf)


# ───────────────────────────── claim 14 (PREREG 8): the forming candle ─────────────────────────────

# the rows above each chart: claim 14's higher-timeframe rows (the chart's own row is never forming at its close)
HIGHER_ROWS: Dict[str, Tuple[str, ...]] = {tf: tuple(ROWS[tf][1:]) for tf in TFS}
_EV_WINDOWS = ("dev", "val")                    # the evidence's two windows as it labels them (tradeiq2.Evidence)


def closed_score(ctx: M.Context, row: str) -> np.ndarray:
    """
    Claim 14's "closed one", per bar of ``ctx.bars(row)``: the score that bar ends with. These are its own committed
    values (``tradeiq2_ind_msd.row_values``: the structure, order-block and gap votes and the swing high and low after
    the bar) with the swing vote at its own close: struct + ob + fvg + swing, in [-4, 4] (int64, read-only, cached).
    Where a chart bar closes with the row bar, this equals model A's ``s_<row>`` on that chart bar. Gold's week, its
    Friday day bar and its Friday 20:00 4H bar close when no chart bar closes (Saturday 00:00 UTC).
    """
    if row not in MS.ROWS:
        raise ValueError(f"{row}: the dashboard's rows are {', '.join(MS.ROWS)}")
    tick = MS.MINTICK.get(ctx.symbol)
    if tick is None:
        raise ValueError(f"{ctx.symbol}: the dashboard's tick (syminfo.mintick) is known on {', '.join(MS.MINTICK)}")

    def make():
        b = ctx.bars(row)
        v = MS.row_values(b)
        swing = MS.swing_factor(b.c, v["swing_h"], v["swing_l"], tick)
        return _ro(v["struct"].astype(np.int64) + v["ob"] + v["fvg"] + swing)
    return ctx.get(CACHE, row, {"what": "closed_score"}, make)


def _times(bars) -> Tuple[np.ndarray, np.ndarray]:
    return np.asarray(bars.t, np.int64), np.asarray(bars.tc, np.int64)


def forming_bar(chart, row) -> np.ndarray:
    """
    Per chart bar, the row bar it lies strictly inside, else -1 (int64). That is the last row bar opening at or before
    the chart bar's open, if it closes after the chart bar's close, so it is still forming at the chart close. A chart
    bar that closes with a row bar, or lies in none (before the first, in a hole between two, after the last), gets
    -1. Times only (``t``, ``tc``): inside by the clock.
    """
    ct, ctc = _times(chart)
    rt, rtc = _times(row)
    if len(rt) == 0:
        return np.full(len(ct), -1, np.int64)
    k = np.searchsorted(rt, ct, side="right") - 1
    inside = (k >= 0) & (ctc < rtc[np.maximum(k, 0)])
    return np.where(inside, k, -1).astype(np.int64)


def _last_inside(chart, row) -> Tuple[np.ndarray, np.ndarray]:
    """(row bars, their last chart bar): every row bar with a chart bar inside it (opening at or after the row bar's
    open, closing at or before its close), with the last such chart bar."""
    ct, ctc = _times(chart)
    rt, rtc = _times(row)
    if len(rt) == 0 or len(ct) == 0:
        z = np.zeros(0, np.int64)
        return z, z
    k = np.searchsorted(rt, ct, side="right") - 1
    j = np.flatnonzero((k >= 0) & (ctc <= rtc[np.maximum(k, 0)]))
    kj = k[j]
    last = np.append(kj[1:] != kj[:-1], True) if len(j) else np.zeros(0, bool)
    return kj[last], j[last]


def forming_counts(s_forming, s_closed, k, chart_ok, row_ok) -> Dict[str, int]:
    """
    Claim 14's count over one window, from per-bar arrays. Chart bar j is counted when it lies strictly inside row bar
    ``k[j] >= 0`` (``forming_bar``), ``chart_ok[j]`` and ``row_ok[k[j]]``. It differs where ``s_forming[j] !=
    s_closed[k[j]]``. Returns ``closes`` (counted), ``differ``, ``bars`` (row bars with a counted close) and
    ``bars_differ`` (those with at least one counted close that differs).
    """
    sf, sc, k = (np.asarray(x, np.int64) for x in (s_forming, s_closed, k))
    chart_ok, row_ok = np.asarray(chart_ok, bool), np.asarray(row_ok, bool)
    if not (sf.shape == k.shape == chart_ok.shape) or sc.shape != row_ok.shape:
        raise ValueError("s_forming, k and chart_ok are per chart bar; s_closed and row_ok per row bar")
    j = np.flatnonzero((k >= 0) & chart_ok)
    j = j[row_ok[k[j]]]
    kj = k[j]
    diff = sf[j] != sc[kj]
    return {"closes": int(len(j)), "differ": int(diff.sum()), "bars": int(len(np.unique(kj))),
            "bars_differ": int(len(np.unique(kj[diff])))}


def _part(part: str, symbol: str, rows: str, dev: str, val: str, dev_ok, val_ok, note: str = "") -> Dict[str, object]:
    """One row of the driver's claims table (the fields of ``tradeiq2._row``)."""
    return {"part": part, "symbol": symbol, "rows": rows, "dev": dev, "val": val, "dev_ok": dev_ok,
            "val_ok": val_ok, "note": note}


def _pct(k: int, n: int) -> str:
    return f"{100.0 * k / n:.1f}%" if n else "-"


def _can_change(st: Mapping[str, int]) -> bool:
    """Claim 14's verdict line in one window (fixed before any count existed): a counted chart close differs."""
    return bool(st["closes"] > 0 and st["differ"] > 0)


_C14_NOTE = ("forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the "
             "live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own "
             "close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility)")


def claim14(ev) -> List[Dict[str, object]]:
    """
    The driver's claim-14 extra (PREREG 8): "its higher-timeframe rows use the forming candle and can change", tested
    by "the share of chart closes inside a higher-timeframe bar where the forming-bar score differs from the closed
    one". The parts are per symbol of ``ev.symbols``, chart and higher row (``HIGHER_ROWS``), in the evidence's two
    windows ('dev' and 'val'). A close is counted through ``ev.in_window`` of the chart bar and of the row bar, and
    the row bar must be complete. Each part carries a verdict: it holds where the share is above 0. Each chart also
    gets one information part: the label the live dashboard shows against the label the chart's history shows. The
    readings are in the module docstring.
    """
    out: List[Dict[str, object]] = []
    for s in ev.symbols:
        ctx = ev.context(s)
        for tf in TFS:
            chart = ctx.bars(tf)
            live = dashboard(ctx, tf, "B")
            inside_any = np.zeros(len(chart), bool)
            for r in HIGHER_ROWS[tf]:
                row = ctx.bars(r)
                rw = _ROW_WORDS[r]
                k = forming_bar(chart, row)
                inside_any |= k >= 0
                sf = np.asarray(live[f"s_{r}"], np.int64)
                sc = closed_score(ctx, r)
                row_ok = {w: np.asarray(ev.in_window(s, r, w), bool) & np.asarray(row.complete, bool)
                          for w in _EV_WINDOWS}
                kl, jl = _last_inside(chart, row)
                keep = row_ok["dev"][kl] | row_ok["val"][kl]
                if not np.array_equal(sf[jl[keep]], sc[kl[keep]]):
                    raise AssertionError(f"claim 14, {s} {tf} chart, {r} row: at the last chart bar inside a row bar "
                                         "the forming score must be the score the bar closes with (the chart bars "
                                         "tile the row bar)")
                st = {w: forming_counts(sf, sc, k, ev.in_window(s, tf, w), row_ok[w]) for w in _EV_WINDOWS}
                txt = {w: f"{x['differ']}/{x['closes']} chart closes ({_pct(x['differ'], x['closes'])}); "
                          f"{x['bars_differ']}/{x['bars']} {rw} bars change at least once" for w, x in st.items()}
                out.append(_part(
                    f"{tf} chart, {rw} row: the forming-bar score differs from the closed one at some chart closes "
                    f"inside a {rw} bar (it can change: a share above 0)", s,
                    f"{tf} chart closes strictly inside a complete {rw} bar of the window; the live {rw} score against "
                    "the score that bar closes with", txt["dev"], txt["val"], _can_change(st["dev"]),
                    _can_change(st["val"]), _C14_NOTE))
            hist = dashboard(ctx, tf)
            la, lb = np.asarray(hist["label"]), np.asarray(live["label"])
            sa, sb = alone_state(la, "MSD-A1"), alone_state(lb, "MSD-A1")
            txt = {}
            for w in _EV_WINDOWS:
                m = np.asarray(ev.in_window(s, tf, w), bool) & inside_any
                n, kd, ks = int(m.sum()), int(np.sum(la[m] != lb[m])), int(np.sum(sa[m] != sb[m]))
                txt[w] = f"label {kd}/{n} chart closes ({_pct(kd, n)}); MSD-A1's side {ks}/{n} ({_pct(ks, n)})"
            out.append(_part(
                f"{tf} chart: the label the live dashboard shows (forming rows, model B) differs from the label the "
                "chart's history shows for that bar (closed rows, model A) (information)", s,
                f"{tf} chart closes in the window strictly inside a bar of a higher row "
                f"({', '.join(_ROW_WORDS[r] for r in HIGHER_ROWS[tf])})", txt["dev"], txt["val"], np.nan, np.nan,
                "information, no verdict (the claim is about the rows' scores)"))
    return out
