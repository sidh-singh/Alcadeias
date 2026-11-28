"""
"Wyckoff [theUltimator5]" (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.3): the rule rows, their
Execs, the pooled placebo test of 6.3 and the claim-16 extra.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_wyckoff as RW
    ctx = M.Context(M.load("XAUUSDm"))                    # to the hold-out start
    vs = RW.variants("XAUUSDm")                            # 54 rows (BTCUSDm: 57, with the 3 tick-volume controls)
    ex = RW.build(vs[0], ctx)                              # an EVENTS Exec of tradeiq2_market
    res = M.run_variant(ctx, vs[0], ex)
    pt = RW.pooled_test_run({"XAUUSDm": ctx_gold, "BTCUSDm": ctx_btc})   # later: Development + Validation

The engine is the reconciled port ``tradeiq2_ind_wyckoff`` (``W.wyckoff``; ``porting/wyckoff.md``), run on the
signal bars from the symbol's data start (gold 2016-01-03, BTC 2018-01-01: ``tradeiq2_market.load``), every input
at the script's default, gold on tick volume, BTC on Binance BTCUSDT volume (PREREG 2), the control on Exness tick
volume. Line numbers ``(Lnnnn)`` are those of the owner's copy of the Pine source (third-party, not in the
repository); ``porting/wyckoff.md`` holds the readings of the engine itself.

The rows (per symbol; ids ``symbol|tf|family|rule|stop|exit|filter``, the control ``...|F0|VOL-TICK``)
------------------------------------------------------------------------------------------------------
| family | rule | entry (decided at the bar's close) | stop | exits | filters | rows |
|---|---|---|---|---|---|---|
| WY | WY-STD | the Standard entry alert, both sides | S-W | X-S, X-S3 | F0, F2 | 3 TF x 2 x 2 = 12 |
| WY | WY-STD-L | the Standard entry alert, longs only | S-W | X-S, X-S3 | F0, F2 | 12 |
| WY | WY-AGG | the Aggressive entry alert, both sides | S-W | X-S, X-S3 | F0, F2 | 12 |
| WY-DERIVED | WY-CL | the bar that confirms a climax (SC long, BC short) | S-CL | X-2R50 | F0, F2 | 6 |
| WY-DERIVED | WY-SP | the recovery bar of a spring / UTAD (confirmed or provisional) | S-SP | X-S, X-S3 | F0, F2 | 12 |
| WY, not eligible (BTCUSDm only) | WY-STD on Exness tick volume | as WY-STD | S-W | X-S | F0 | 3 |

That is 36 + 18 = 54 eligible rows per symbol plus 3 control rows on BTC (PREREG 6.3 "Size"; section 7's 738 / 720
eligible variants use the same 54). The timeframes are 1H, 4H and 1D; F2 is F2-4H on 1H, F2-1D on 4H and F1 on 1D
(PREREG 6.3 "Filters"). Families: WY (the script's entries) and WY-DERIVED (PREREG 7).

* ENTRIES. ``entry_std`` / ``entry_agg``: the script's alert ``chartLongEntryNow`` / ``chartShortEntryNow``
  (L2236-2238), +1 / -1 on the bar whose close sets the campaign's entry slot (L1729-1747), per setting from one pass;
  the labels, phases and schematics drawn back in time are never read. ``climax``: +1 / -1 on the absorption bar
  that confirms a selling / buying climax (L1278-1290; ``climax_px`` is the climax bar's low / high). ``exc``: +1 /
  -1 on the recovery bar of a spring / UTAD, confirmed (``f_excFromPend``) or provisional (Phase B not yet mature,
  L1574-1586; ``exc_px`` is its extreme then); the bar that later adopts a provisional spring on a breakout
  (L1654-1660) is not a recovery bar (porting/wyckoff.md, reading 15). Every decision is taken at the close of the bar
  the event is reported on, from bars up to that close (the engine has no look-ahead), and fills at the open of the
  next M1 bar (``tradeiq2_market``; PREREG 4).
* STOPS, fixed for the trade's life, as absolute levels (PREREG 4: the distance |fill - level| from the actual fill;
  an entry whose fill is at or beyond its stop is dropped by the harness), ATR = Pine ``ta.atr(14)`` of the signal
  bars at the decision bar (``Context.atr``; PREREG 5):
  - S-W: the hard level ``hard_lo`` / ``hard_hi`` (the script's ``f_hardLevel``, L723-729: the spring / UTAD extreme
    when the campaign holds that outcome from an excursion, otherwise the lower of the climax low and the range low /
    the higher of the climax high and the range high) minus / plus 0.15 ATR. SKIP GUARD: an entry is skipped when its
    stop is less than 0.25 ATR beyond the decision close (close - stop < 0.25 ATR for a long, stop - close for a
    short), before the fill is known.
  - S-CL: the climax extreme ``climax_px`` minus / plus 0.15 ATR.
  - S-SP: the excursion's extreme ``exc_px`` as known at the recovery bar minus / plus 0.15 ATR (reading D3 below).
* EXITS (per entry: ``Entries.exit_bar`` = the bar at whose close the exit is decided, filled at the next M1 open):
  - X-S, structure: the close of the first bar j > i on which the entry's campaign no longer holds the trade's outcome
    in Phases C-E: not (``in_cde[j]`` and ``campaign[j] == campaign[i]`` and ``outcome[j] == side``), i.e. a reset
    (the script's invalidation, no absorption, stale, departure, the end of Phase E, L1181-1234), a re-seed, a
    demotion (L1210-1218, which ends the hold even when the same bar re-enters Phase C) or an outcome change. While it
    still holds at the last bar there is no exit decision (the stop or the window's end closes the trade).
  - X-S3: X-S plus a target at 3R, R = the initial risk |fill - stop| from the actual fill.
  - X-2R50 (WY-CL): a 2R target, else the close of the 50th bar after the entry bar (a time stop).
  - WY-SP's X-S follows reading D2 below (a provisional spring holds no outcome yet).
* FILTERS (event rule, PREREG 5): checked at the decision close of the entry (``tradeiq2_filters.gate_entries`` on
  ``Context.allow``); a filter never closes an open trade, which keeps its own exits.
* ONE POSITION per row (the harness): an entry decided while a trade is open is skipped ("busy"); after a stop or a
  target the rule waits for its next event. The script itself allows one entry per campaign and setting (its entry
  slot, kept through a demotion), so WY-STD / WY-STD-L / WY-AGG see at most one entry per campaign.
* ``tag`` of every entry: 10 x (campaign id + 1) + kind (``KINDS``: 1 test, 2 terminal test, 3 LPS / LPSY, 4 SOS / SOW
  (Aggressive), 5 climax, 6 confirmed spring / UTAD, 7 provisional one), so the trades carry the entry type (claim
  16) and the campaign (the seed bar's index, ``s.startBar``).

Deviations (readings of PREREG 6.3 where it is silent or ambiguous; proposed for DEVIATIONS.md)
------------------------------------------------------------------------------------------------
D1. WY-DERIVED's 18 rows. 6.3 gives "36 + 18 = 54 eligible rows per symbol" (and section 7's 738 / 720 eligible
    variants), while the text of WY-CL ("exit at a 2R target or after 50 bars") and WY-SP ("exit at a 3R target or
    X-S") with "F0 and F2, on three timeframes" counts 12 if both "or"s join one exit. The reading that gives 18 and
    stays closest to the script: WY-SP, the spring entry the video recommends ("wait for the spring and the test"),
    takes the two exits of the script's own rows, X-S and X-S3 (= X-S plus a 3R target), 2 x 2 x 3 = 12 rows; WY-CL,
    entered in Phase A where the campaign holds no outcome and X-S does not apply, has one exit, the 2R target with
    the 50-bar time stop as its cap (whichever comes first), 2 x 3 = 6 rows.
D2. WY-SP's X-S after a provisional excursion (porting/wyckoff.md, reading 3). At a provisional recovery the
    campaign is still in Phase B without an outcome, so a literal X-S would close every such trade one bar after its
    entry (most WY-SP entries are provisional: gold 1H 50 of 64, BTC 1H 106 of 122 in Development). Reading: X-S is
    ARMED from the first bar (the entry bar included) on which the entry's campaign holds the trade's side in Phases
    C-E; from then on it is X-S as above. Before that the trade exits at the close of the first bar on which the
    entry's campaign is gone (a reset or a re-seed: another id or none) or holds the opposite outcome. A confirmed
    spring holds its outcome at its recovery bar, so its X-S is the plain one (on the real bars to 2024-06-30 every
    confirmed recovery but one: BTC 1H on Binance volume, 2023-11-22 00:00, where a demotion on the same bar ends the
    hold, porting/wyckoff.md reading 5; that trade is armed from the next bar). Measured (counts only, data start to
    2024-06-30): of the provisional recoveries, gold 1H 20 of 100 and BTC 1H 40 of 158 are armed later; the rest end
    on a reset, a re-seed or the opposite outcome.
D3. WY-SP's stop "beyond the extreme": ``exc_px`` (the extreme known at the recovery bar; the script's later
    extension of an untested spring moves its hard level, never this stop) minus / plus 0.15 ATR, the distance S-W and
    WY-CL use (porting/wyckoff.md, reading 4).
D4. The skip guard is S-W's (6.3 lists it with S-W). WY-CL and WY-SP do not use it: their stops are 0.15 ATR beyond an
    extreme the close has already left (absorption needs a close at least 0.35 climax-ATR above the climax low, L1282;
    a recovery a close back inside the range after a dip of at least 0.15 ATR, L1570-1572), so it could skip almost
    none of them. Measured on the real bars to 2024-06-30 (geometry only): it would skip none; the smallest stop
    distances are 0.38 ATR (WY-CL) and 0.39 ATR (WY-SP), both BTC 1H.
D5. X-S is decided per entry from the engine's state (``in_cde``, ``campaign``, ``outcome``), port A's form of the
    contract (equal to port B's ``in_cde`` alone at every entry of the real bars, test_tradeiq2_ind_wyckoff). An
    X-S that would come after the last bar served is no exit decision (the trade then ends at its stop or at the
    window's last M1 close, PREREG 3); WY-CL's time stop likewise when bar i + 50 is not served.
D6. The control's stop and exit are WY-STD's S-W and X-S; only the volume differs (PREREG 6.3 "Control").
D7. The pooled test (PREREG 6.3 "Few trades"; ``pooled_test_run``): the real trades of WY-STD x S-W x X-S x F0 on
    1H / 4H / 1D of both symbols over one window (Development + Validation as one continuous run per series, x1.0);
    1,000 placebo sets, each with one random entry per real trade: the same symbol, timeframe and side, a decision bar
    drawn uniformly from the window's bars (seeded), a stop at the real trade's initial risk in ATR of its decision bar
    times the placebo bar's ATR from the placebo's own fill, and a time exit after the real trade's holding time in
    signal bars (from the entry bar to the bar of its last exposed M1 bar, at least 1), the stop active throughout.
    Each placebo trade is executed by the same harness (non-overlapping trades share an Exec, so none is skipped). The
    statistic is the mean R (primary; R pools across the symbols) and the total in dollars per 0.01 lot (reported
    with it); p = (1 + #{placebo sets >= the real}) / (1 + 1,000), one-sided; "holds" at p < 0.05.

What is known when: every input of an entry (the engine's state, the ATR, the filter) is that of the decision bar's
close; the X-S and time-stop exits are decisions at later closes from the state then. Truncating the bars after bar T
leaves every entry decided up to T and every exit decided up to T unchanged (tests).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import tradeiq2_filters as F
from . import tradeiq2_ind_wyckoff as W
from . import tradeiq2_market as M

__all__ = ["variants", "build", "warm", "describe", "engine", "plan", "rule_entries", "xs_exit", "sp_exit",
           "candidate_events", "event_counts", "pooled_test_run", "pooled_test", "claim16", "RULES", "TFS"]

SCRIPT = "WY"
FAMILY, DERIVED = "WY", "WY-DERIVED"
FAMILIES = (FAMILY, DERIVED)
TFS = ("1H", "4H", "1D")
FILTER_SLOTS = ("F0", "F2")
F2_SLOT = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}       # PREREG 6.3: "F2 (1H: F2-4H; 4H: F2-1D; 1D: F1)"
VOLUME = {M.GOLD: "tick", M.BTC: "binance"}                 # PREREG 2 / 6.3: gold tick volume, BTC Binance volume
CONTROL_VOLUME = "tick"                                     # PREREG 6.3 "Control": BTC on Exness tick volume
CONTROL_TOKEN = "VOL-TICK"
CONTROL_INFO = "control: BTC on Exness tick volume (PREREG 6.3); not eligible"

STOP_ATR = 0.15          # S-W, S-CL and (D3) S-SP: the stop 0.15 ATR beyond its level
SKIP_ATR = 0.25          # S-W's skip guard: the stop at least 0.25 ATR beyond the decision close
XS3_R = 3.0              # X-S3: X-S plus a 3R target
CL_R, CL_BARS = 2.0, 50  # WY-CL: a 2R target, else the close of the 50th bar


@dataclass(frozen=True)
class Rule:
    """One rule of PREREG 6.3: its family, the engine output it enters on, long only or both sides, its stop and its
    exits (in the grid's order)."""
    name: str
    family: str
    entry: str               # "std" / "agg" (the entry alert), "climax", "exc"
    long_only: bool
    stop: str                # "S-W", "S-CL", "S-SP"
    exits: Tuple[str, ...]


RULES: Dict[str, Rule] = {r.name: r for r in (
    Rule("WY-STD", FAMILY, "std", False, "S-W", ("X-S", "X-S3")),
    Rule("WY-STD-L", FAMILY, "std", True, "S-W", ("X-S", "X-S3")),
    Rule("WY-AGG", FAMILY, "agg", False, "S-W", ("X-S", "X-S3")),
    Rule("WY-CL", DERIVED, "climax", False, "S-CL", ("X-2R50",)),
    Rule("WY-SP", DERIVED, "exc", False, "S-SP", ("X-S", "X-S3")),
)}
# exit -> (target in R, time stop in bars); X-S / X-S3 also carry the structure exit
EXITS: Dict[str, Tuple[Optional[float], Optional[int]]] = {"X-S": (None, None), "X-S3": (XS3_R, None),
                                                           "X-2R50": (CL_R, CL_BARS)}

# the entry types carried in the trades' tag (10 x (campaign + 1) + kind)
K_TEST, K_CTEST, K_LPS, K_SOS, K_CLIMAX, K_SPRING, K_PROV = 1, 2, 3, 4, 5, 6, 7
KINDS = {K_TEST: "test", K_CTEST: "terminal test", K_LPS: "LPS", K_SOS: "SOS", K_CLIMAX: "climax",
         K_SPRING: "spring (confirmed)", K_PROV: "spring (provisional)"}
ENGINE_KEY = "wyckoff"   # the Context cache's module name for the engine's outputs

# PREREG 6.3's rows per symbol: (family, eligible) -> rows
EXPECTED = {M.GOLD: {(FAMILY, True): 36, (DERIVED, True): 18},
            M.BTC: {(FAMILY, True): 36, (DERIVED, True): 18, (FAMILY, False): 3}}


def tag_of(campaign, kind):
    """The entries' tag: 10 x (campaign id + 1) + kind (campaign -1 = none gives the kind alone)."""
    return 10 * (np.asarray(campaign, np.int64) + 1) + np.asarray(kind, np.int64)


def kind_of_tag(tag):
    return np.asarray(tag, np.int64) % 10


def campaign_of_tag(tag):
    return np.asarray(tag, np.int64) // 10 - 1


# ───────────────────────────── the grid (PREREG 6.3 and 7) ─────────────────────────────

def _variant(symbol: str, tf: str, rule: Rule, exit_: str, slot: str, control: bool = False) -> M.Variant:
    filt = "F0" if slot == "F0" else F2_SLOT[tf]
    vid = "|".join([symbol, tf, rule.family, rule.name, rule.stop, exit_, filt] + ([CONTROL_TOKEN] if control else []))
    target_r, time_bars = EXITS[exit_]
    params = {"rule": rule.name, "entry": rule.entry, "side": "LO" if rule.long_only else "LS", "stop": rule.stop,
              "exit": exit_, "filter": filt, "filter_slot": slot,
              "volume": CONTROL_VOLUME if control else VOLUME[symbol]}
    if target_r is not None:
        params["target_r"] = target_r
    if time_bars is not None:
        params["time_bars"] = time_bars
    return M.Variant(vid, symbol, tf, SCRIPT, rule.family, not control, CONTROL_INFO if control else "", params)


def variants(symbol: str) -> List[M.Variant]:
    """PREREG 6.3's rows of ``symbol``: 54 eligible on XAUUSDm and BTCUSDm (36 WY, 18 WY-DERIVED) and, on BTCUSDm, the
    3 control rows (WY, not eligible). None on the claim markets (PREREG 8 checks no Wyckoff claim there)."""
    if symbol not in M.SYMBOLS:
        return []
    out = [_variant(symbol, tf, r, x, slot) for tf in TFS for r in RULES.values() for x in r.exits
           for slot in FILTER_SLOTS]
    if symbol == M.BTC:
        out += [_variant(symbol, tf, RULES["WY-STD"], "X-S", "F0", control=True) for tf in TFS]
    return out


@dataclass(frozen=True)
class Spec:
    """What a row's id says: its rule, exit, filter and volume source."""
    rule: Rule
    exit: str
    filter: str
    volume: str
    control: bool


def spec_of(v: M.Variant) -> Spec:
    """The rule row of a variant, read from its id (``symbol|tf|family|rule|stop|exit|filter[|VOL-TICK]``) and checked
    against its family, timeframe and params."""
    t = v.id.split("|")
    if len(t) not in (7, 8) or t[0] != v.symbol or t[1] != v.tf or t[3] not in RULES:
        raise ValueError(f"{v.id}: not a Wyckoff row of this module")
    rule = RULES[t[3]]
    control = len(t) == 8
    if (t[2] != rule.family or t[4] != rule.stop or t[5] not in rule.exits or v.family != rule.family
            or v.tf not in TFS or (control and (t[7] != CONTROL_TOKEN or v.symbol != M.BTC or rule.name != "WY-STD"))):
        raise ValueError(f"{v.id}: an inconsistent Wyckoff row")
    if t[6] not in ("F0", F2_SLOT[v.tf]):
        raise ValueError(f"{v.id}: filter {t[6]} is not one of {v.tf}'s (F0, {F2_SLOT[v.tf]})")
    vol = CONTROL_VOLUME if control else VOLUME[v.symbol]
    p = dict(v.params)
    if p and (p.get("rule") != rule.name or p.get("exit") != t[5] or p.get("filter") != t[6]
              or p.get("volume", vol) != vol):
        raise ValueError(f"{v.id}: its params {p} do not match its id")
    return Spec(rule, t[5], t[6], vol, control)


# ───────────────────────────── the engine ─────────────────────────────

def _volume_key(ctx: M.Context, volume: Optional[str]) -> str:
    src = VOLUME.get(ctx.symbol, "tick") if volume is None else volume
    if src not in ("tick", "binance"):
        raise ValueError(f"volume source {src!r} (tick or binance)")
    return src


def engine(ctx: M.Context, tf: str, volume: Optional[str] = None) -> Dict[str, np.ndarray]:
    """``tradeiq2_ind_wyckoff.wyckoff`` on ``ctx.bars(tf)`` (from the data start the market holds) with the volume
    ``volume`` ('tick' or 'binance'; None: PREREG 2's, gold tick and BTC Binance), the symbol's ``syminfo.mintick``
    (``W.MINTICK``) and the chart's seconds; cached in the Context; read-only arrays (``W.CONTRACT_KEYS``)."""
    src = _volume_key(ctx, volume)

    def make():
        b = ctx.bars(tf)
        v = np.asarray(ctx.volume(tf, src), np.float64)
        out = W.wyckoff(b.o, b.h, b.l, b.c, v, b.t, mintick=W.MINTICK[ctx.symbol],
                        tf_seconds=float(M.TF_SECONDS[tf]))
        for a in out.values():
            a.setflags(write=False)
        return out
    return ctx.get(ENGINE_KEY, tf, {"volume": src}, make)


def use_engine_output(ctx: M.Context, tf: str, out: Mapping[str, np.ndarray], volume: Optional[str] = None) -> None:
    """Put ``out`` (arrays of ``W.CONTRACT_KEYS``, one value per bar of ``ctx.bars(tf)``) in the Context's cache as the
    engine's output (hand-made tests and diagnostics only)."""
    n = len(ctx.bars(tf))
    if set(out) != set(W.CONTRACT_KEYS) or any(len(np.asarray(out[k])) != n for k in W.CONTRACT_KEYS):
        raise ValueError(f"an engine output has exactly W.CONTRACT_KEYS, one value per {tf} bar ({n})")
    mine = {k: np.asarray(out[k]) for k in W.CONTRACT_KEYS}
    if ctx.get(ENGINE_KEY, tf, {"volume": _volume_key(ctx, volume)}, lambda: mine) is not mine:
        raise ValueError(f"the engine's {tf} output of this Context is already computed (use a fresh Context)")


# ───────────────────────────── entries, stops and exits ─────────────────────────────

def _script_kinds(out: Mapping[str, np.ndarray], idx: np.ndarray, mode: str) -> np.ndarray:
    """The entry type of the entry alert at bars ``idx`` (the script's ``entryKind``, L1747): Standard: the LPS
    fallback when an LPS / LPSY bit is on the bar (``standardLpsFallback``, L1742, comes first in L1747), else the
    test (or terminal test); Aggressive (its triggers L1739-1740 have no LPS): the test (or terminal test) when a test
    bit is on the bar, else the SOS / SOW fallback."""
    test, ctest = np.asarray(out["ev_test"])[idx], np.asarray(out["ev_ctest"])[idx]
    k = np.where(test, K_TEST, np.where(ctest, K_CTEST, K_SOS))
    if mode == "std":
        lps = np.asarray(out["ev_lps"])[idx] | np.asarray(out["ev_lpsy"])[idx]
        k = np.where(lps, K_LPS, k)
    return k.astype(np.int64)


def candidate_events(out: Mapping[str, np.ndarray], close, atr, rule: str) -> Dict[str, np.ndarray]:
    """Every event ``rule`` would enter on, before its guard and filter, with its geometry: ``bar`` (the decision bar),
    ``side``, ``kind``, ``campaign`` (the engine's id at the bar), ``level`` (S-W: the hard level; S-CL: the climax
    extreme; S-SP: the excursion's extreme), ``stop`` (the level -/+ 0.15 ATR), ``dist_atr`` (side x (close - stop) /
    ATR at the bar), ``valid`` (a finite stop and ATR > 0) and ``guard`` (S-W: the stop at least 0.25 ATR beyond the
    close; True for the other stops). Counts and geometry only (no profit or loss)."""
    r = RULES[rule]
    close, atr = np.asarray(close, np.float64), np.asarray(atr, np.float64)
    if r.entry in ("std", "agg"):
        e = np.asarray(out[f"entry_{r.entry}"])
        idx = np.flatnonzero(e != 0)
        side = e[idx].astype(np.int64)
        if r.long_only:
            idx, side = idx[side == 1], side[side == 1]
        level = np.where(side == 1, np.asarray(out["hard_lo"])[idx], np.asarray(out["hard_hi"])[idx])
        kind = _script_kinds(out, idx, r.entry)
    elif r.entry == "climax":
        e = np.asarray(out["climax"])
        idx = np.flatnonzero(e != 0)
        side = e[idx].astype(np.int64)
        level = np.asarray(out["climax_px"], np.float64)[idx]
        kind = np.full(len(idx), K_CLIMAX, np.int64)
    else:
        e = np.asarray(out["exc"])
        idx = np.flatnonzero(e != 0)
        side = e[idx].astype(np.int64)
        level = np.asarray(out["exc_px"], np.float64)[idx]
        confirmed = np.asarray(out["ev_spring"])[idx] | np.asarray(out["ev_utad"])[idx]
        kind = np.where(confirmed, K_SPRING, K_PROV).astype(np.int64)
    a = atr[idx]
    with np.errstate(invalid="ignore"):
        stop = level - side * STOP_ATR * a
        valid = np.isfinite(stop) & np.isfinite(a) & (a > 0)
        dist = np.where(valid, side * (close[idx] - stop) / np.where(valid, a, 1.0), np.nan)
        guard = (dist >= SKIP_ATR) if r.stop == "S-W" else np.ones(len(idx), bool)
    return {"bar": idx.astype(np.int64), "side": side, "kind": kind,
            "campaign": np.asarray(out["campaign"])[idx].astype(np.int64), "level": level.astype(np.float64),
            "stop": stop.astype(np.float64), "dist_atr": dist.astype(np.float64), "valid": valid,
            "guard": valid & guard}


def _campaign_change(campaign) -> np.ndarray:
    """The bars whose campaign id differs from the previous bar's (sorted)."""
    c = np.asarray(campaign)
    return np.flatnonzero(c[1:] != c[:-1]) + 1


def _segment_end(chg: np.ndarray, i: int, n: int) -> int:
    """The first bar j > i whose campaign id differs from bar i's (n when none)."""
    k = int(np.searchsorted(chg, i + 1, side="left"))
    return int(chg[k]) if k < len(chg) else n


def xs_exit(out: Mapping[str, np.ndarray], i: int, side: int, chg: Optional[np.ndarray] = None) -> int:
    """PREREG 6.3's X-S of a trade on ``side`` entered at the close of bar ``i``: the first bar j > i at whose close
    not (``in_cde[j]`` and ``campaign[j] == campaign[i]`` and ``outcome[j] == side``); -1 when the hold lasts to the
    last bar."""
    cde, camp, outc = out["in_cde"], out["campaign"], out["outcome"]
    n = len(cde)
    chg = _campaign_change(camp) if chg is None else chg
    if int(camp[i]) < 0:
        return i + 1 if i + 1 < n else -1
    e = _segment_end(chg, i, n)                              # campaign[j] == campaign[i] on i .. e-1
    bad = np.flatnonzero(~(np.asarray(cde[i + 1:e]) & (np.asarray(outc[i + 1:e]) == side)))
    if len(bad):
        return i + 1 + int(bad[0])
    return e if e < n else -1


def sp_exit(out: Mapping[str, np.ndarray], i: int, side: int, chg: Optional[np.ndarray] = None) -> int:
    """WY-SP's X-S (deviation D2) of a trade on ``side`` entered at the recovery bar ``i``: armed from the first bar
    k >= i on which the campaign of bar i holds ``side`` in Phases C-E, X-S from there (``xs_exit`` of bar k); until
    then, the close of the first bar j > i on which that campaign is gone (another id, or none) or holds the opposite
    outcome. -1: no exit decision up to the last bar."""
    cde, camp, outc = out["in_cde"], out["campaign"], out["outcome"]
    n = len(cde)
    chg = _campaign_change(camp) if chg is None else chg
    if int(camp[i]) < 0:
        return i + 1 if i + 1 < n else -1
    e = _segment_end(chg, i, n)
    hold = np.asarray(cde[i:e]) & (np.asarray(outc[i:e]) == side)         # [0] is bar i
    arm = np.flatnonzero(hold)
    opp = np.flatnonzero(np.asarray(outc[i + 1:e]) == -side)
    a = i + int(arm[0]) if len(arm) else None
    o = i + 1 + int(opp[0]) if len(opp) else None
    if a is not None and (o is None or a < o):
        after = np.flatnonzero(~hold[a - i + 1:])
        if len(after):
            return a + 1 + int(after[0])
        return e if e < n else -1
    if o is not None:
        return o
    return e if e < n else -1


def plan(out: Mapping[str, np.ndarray], close, atr, rule: str, exit_: str) -> Dict[str, np.ndarray]:
    """The entries of ``rule`` with exit ``exit_`` (before the filter): the events of ``candidate_events`` with a valid
    stop that pass the guard, each with ``stop_level``, ``target_r`` (NaN: none), ``exit_bar`` (X-S, WY-SP's X-S or the
    time stop; -1 none) and ``tag``. Plain arrays, so it can be checked on hand-made engine outputs."""
    r = RULES[rule]
    if exit_ not in r.exits:
        raise ValueError(f"{rule} has the exits {r.exits}, not {exit_}")
    ev = candidate_events(out, close, atr, rule)
    keep = ev["guard"]
    bar, side = ev["bar"][keep], ev["side"][keep]
    n = len(np.asarray(close))
    target_r, time_bars = EXITS[exit_]
    if time_bars is not None:
        xb = np.where(bar + time_bars < n, bar + time_bars, -1).astype(np.int64)
    else:
        chg = _campaign_change(out["campaign"])
        fn = sp_exit if r.entry == "exc" else xs_exit
        xb = np.asarray([fn(out, int(i), int(d), chg) for i, d in zip(bar, side)], np.int64)
    return {"bar": bar, "side": side, "stop_level": ev["stop"][keep],
            "target_r": np.full(len(bar), np.nan if target_r is None else float(target_r)), "exit_bar": xb,
            "tag": tag_of(ev["campaign"][keep], ev["kind"][keep]), "kind": ev["kind"][keep]}


def rule_entries(ctx: M.Context, tf: str, rule: str, exit_: str, volume: Optional[str] = None) -> M.Entries:
    """The market entries of ``rule`` x ``exit_`` on ``tf`` (no filter), from the engine with ``volume``."""
    p = plan(engine(ctx, tf, volume), ctx.bars(tf).c, ctx.atr(tf), rule, exit_)
    tr = p["target_r"]
    return M.entries(p["bar"], p["side"], stop_level=p["stop_level"],
                     target_r=None if not np.isfinite(tr).any() else tr, exit_bar=p["exit_bar"], tag=p["tag"])


def build(v: M.Variant, ctx: M.Context) -> M.Exec:
    """The EVENTS Exec of a row of ``variants``: its entries (``rule_entries``) gated by its filter at the decision
    close (``tradeiq2_filters.gate_entries`` on ``ctx.allow``)."""
    if v.symbol != ctx.symbol:
        raise ValueError(f"{v.id}: not a variant of {ctx.symbol}")
    s = spec_of(v)
    E = rule_entries(ctx, v.tf, s.rule.name, s.exit, s.volume)
    al, ash = ctx.allow(v.tf, s.filter)
    return M.event_exec(v.tf, entries=F.gate_entries(E, al, ash), label=v.id)


def warm(ctx: M.Context, vs: Sequence[M.Variant]) -> None:
    """The engine's outputs, the ATR and the filter masks every row of ``vs`` reads, computed once (the driver calls
    this in its parent process, so the workers share them)."""
    for v in vs:
        if v.symbol != ctx.symbol:
            continue
        s = spec_of(v)
        engine(ctx, v.tf, s.volume)
        ctx.atr(v.tf)
        ctx.allow(v.tf, s.filter)


_TF_WORDS = {"1H": "1-hour", "4H": "4-hour", "1D": "daily"}
_ENTRY_WORDS = {"WY-STD": "the script's Standard entry alert (long and short)",
                "WY-STD-L": "the script's Standard entry alert, longs only",
                "WY-AGG": "the script's Aggressive entry alert (long and short)",
                "WY-CL": "the bar that confirms a selling climax (long) or a buying climax (short)",
                "WY-SP": "the recovery bar of a confirmed or provisional spring (long) or UTAD (short)"}
_STOP_WORDS = {"S-W": "stop S-W at the script's hard level (the spring / UTAD extreme, else the climax or range "
                      "edge) -/+ 0.15 ATR(14), fixed; skipped when the stop is less than 0.25 ATR beyond the close",
               "S-CL": "stop at the climax extreme -/+ 0.15 ATR(14), fixed",
               "S-SP": "stop at the excursion's extreme -/+ 0.15 ATR(14), fixed"}
_EXIT_WORDS = {"X-S": "exit X-S at the close of the first bar on which the campaign no longer holds the trade's "
                      "outcome in Phases C-E",
               "X-S3": "exit X-S, or a 3R target first",
               "X-2R50": "exit at a 2R target or at the close of the 50th bar"}


def describe(v: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    s = spec_of(v)
    ex = _EXIT_WORDS[s.exit]
    if s.rule.entry == "exc" and s.exit in ("X-S", "X-S3"):
        ex += " (armed once the campaign holds it; before that a reset, re-seed or the opposite outcome ends it)"
    vol = {"tick": "tick volume", "binance": "Binance BTCUSDT volume"}[s.volume]
    filt = "no filter" if s.filter == "F0" else f"filter {s.filter} at the entry's close"
    return (f"Wyckoff [theUltimator5] on {_TF_WORDS[v.tf]} bars of the bid ({vol}): enter on "
            f"{_ENTRY_WORDS[s.rule.name]} at the next M1 open; {_STOP_WORDS[s.rule.stop]}; {ex}; {filt}; one "
            f"position at a time" + ("; control row, not eligible" if s.control else ""))


def event_counts(ctx: M.Context, window="dev") -> pd.DataFrame:
    """Per timeframe and rule (and the control): the events in ``window`` (decided at a bar closing after its start
    and filled before its end), those with a valid stop, those the guard keeps, the long / short split and the median
    stop distance in ATR. Counts and geometry only, no profit or loss."""
    _, _, a_s, iz = _span(ctx, window)
    rows = []
    for tf in TFS:
        b = ctx.bars(tf)
        inw = (b.tc > a_s) & (b.ex < iz)
        sources = [(VOLUME[ctx.symbol], False)] + ([(CONTROL_VOLUME, True)] if ctx.symbol == M.BTC else [])
        for src, control in sources:
            out = engine(ctx, tf, src)
            for name in (("WY-STD",) if control else tuple(RULES)):
                ev = candidate_events(out, b.c, ctx.atr(tf), name)
                w = inw[ev["bar"]]
                g = ev["guard"] & w
                rows.append({"symbol": ctx.symbol, "tf": tf, "rule": name, "volume": src, "window": window,
                             "events": int(w.sum()), "valid": int((ev["valid"] & w).sum()), "kept": int(g.sum()),
                             "long": int((g & (ev["side"] == 1)).sum()), "short": int((g & (ev["side"] == -1)).sum()),
                             "median_stop_atr": float(np.median(ev["dist_atr"][g])) if g.any() else np.nan})
    return pd.DataFrame(rows)


# ───────────────────────────── the pooled test and its placebo (PREREG 6.3 "Few trades") ─────────────────────────────

POOLED = ("WY-STD", "S-W", "X-S", "F0")
N_PLACEBO = 1000
PLACEBO_SEED = 20261128
P_LEVEL = 0.05
_AT_OPEN = ("signal", "gap stop", "gap target")             # exits filled at an M1 open (the bar before is the last)
_SYM_INDEX = {s: q for q, s in enumerate(M.ALL_SYMBOLS)}
_TF_INDEX = {tf: q for q, tf in enumerate(M.TFS)}


def pooled_variants(symbol: str) -> List[M.Variant]:
    """The rows of the pooled test on ``symbol``: WY-STD x S-W x X-S x F0 on 1H, 4H and 1D (the eligible ones)."""
    return [v for v in variants(symbol) if v.eligible and v.id.split("|")[3:7] == list(POOLED)]


def hold_bars(bars, bar, exit_ix, reason) -> np.ndarray:
    """A trade's holding time in signal bars: from its decision bar to the bar of its last exposed M1 bar (the one
    before an exit at an M1 open, the exit's own bar otherwise), at least 1. An X-S exit at the close of bar j gives
    j - bar."""
    bar = np.asarray(bar, np.int64)
    x = np.asarray(exit_ix, np.int64)
    last = np.where(np.isin(np.asarray(reason, object), _AT_OPEN), x - 1, x)
    q = np.searchsorted(np.asarray(bars.i1), last, side="left")
    return np.maximum(q - bar, 1).astype(np.int64)


def _span(ctx: M.Context, window) -> Tuple[str, str, int, int]:
    """(start, end, start in s, the M1 index of the end) of a window: a name of ``tradeiq2_market.WINDOWS`` or a
    (start, end) pair (tests)."""
    a, z = M.window_span(window, ctx.symbol) if isinstance(window, str) else (str(window[0]), str(window[1]))
    return a, z, M.s_of(a), int(np.searchsorted(ctx.mk.t, M.s_of(z), side="left"))


def pooled_trades(ctx: M.Context, window="devval", cost: float = 1.0) -> pd.DataFrame:
    """The real trades of the pooled test on one symbol: WY-STD x S-W x X-S x F0 on 1H, 4H and 1D over ``window`` (one
    continuous run per timeframe), with what the placebo is matched on: side, ``stop_atr`` (the initial risk from the
    fill over the ATR of the decision bar) and ``hold`` (``hold_bars``)."""
    a, z, _, _ = _span(ctx, window)
    out = []
    for v in pooled_variants(ctx.symbol):
        r = M.run_exec(ctx.mk, build(v, ctx), a, z, cost)
        tr = r.trades
        b = ctx.bars(v.tf)
        bar = tr["bar"].to_numpy(np.int64)
        atr = np.asarray(ctx.atr(v.tf), np.float64)[bar]
        out.append(pd.DataFrame({
            "symbol": ctx.symbol, "tf": v.tf, "vid": v.id, "bar": bar, "side": tr["side"].to_numpy(np.int64),
            "risk": tr["risk"].to_numpy(np.float64), "atr": atr, "stop_atr": tr["risk"].to_numpy(np.float64) / atr,
            "hold": hold_bars(b, bar, tr["exit_ix"].to_numpy(np.int64), tr["reason"].to_numpy(object)),
            "kind": kind_of_tag(tr["tag"].to_numpy(np.int64)), "reason": tr["reason"].to_numpy(object),
            "pnl": tr["pnl"].to_numpy(np.float64), "r": tr["r"].to_numpy(np.float64)}))
    cols = ["symbol", "tf", "vid", "bar", "side", "risk", "atr", "stop_atr", "hold", "kind", "reason", "pnl", "r"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def _lanes(j_fill: np.ndarray, x_end: np.ndarray) -> List[np.ndarray]:
    """Partition trades (fill at M1 bar j, at the latest out at the open of M1 bar x) into lanes of trades that do not
    overlap: in a lane each fill comes after the previous trade's latest exit (greedy, by fill)."""
    order = np.argsort(j_fill, kind="stable")
    heap: List[Tuple[int, int]] = []
    lanes: List[List[int]] = []
    for t in order:
        t = int(t)
        if heap and heap[0][0] < int(j_fill[t]):
            _, q = heapq.heappop(heap)
        else:
            q = len(lanes)
            lanes.append([])
        lanes[q].append(t)
        heapq.heappush(heap, (int(x_end[t]), q))
    return [np.asarray(x, np.int64) for x in lanes]


def placebo_trades(ctx: M.Context, real: pd.DataFrame, n_sets: int = N_PLACEBO, seed: int = PLACEBO_SEED,
                   window="devval", cost: float = 1.0) -> pd.DataFrame:
    """``n_sets`` placebo sets for the real trades of ``ctx.symbol`` in ``real`` (``pooled_trades``): per set and real
    trade one random entry on the same timeframe and side, at a decision bar drawn uniformly from the window's bars
    (its close after the window's start, its time exit filled before the window's end), with a stop at the real
    trade's ``stop_atr`` times the placebo bar's ATR from its own fill and a time exit at the close of the bar
    ``hold`` bars later. Every placebo trade is executed by the harness (``run_exec``); trades that do not overlap
    share one Exec. Returns one row per placebo trade: set, the real trade's row in ``real`` (``trade``), symbol, tf,
    bar, side, stop_atr, hold, entry_ix / exit_ix (M1), reason, pnl, r. A real trade whose holding time does not fit
    in the window gets no placebo (``trade`` then never appears). The draws depend only on the seed, the symbol, the
    timeframe and the real trades of that series, not on the order the series are run in."""
    a, z, a_s, iz = _span(ctx, window)
    rows = []
    mine = real[real.symbol == ctx.symbol]
    for tf in TFS:
        g = mine[mine.tf == tf]
        if not len(g):
            continue
        b = ctx.bars(tf)
        atr = np.asarray(ctx.atr(tf), np.float64)
        ok = np.isfinite(atr) & (atr > 0)
        nb = int(np.searchsorted(b.ex, iz, side="left"))     # bars whose fill is inside the window: 0 .. nb-1
        lo = int(np.searchsorted(b.tc, a_s, side="right"))   # the first bar closing after the window's start
        while lo < nb and not ok[lo]:
            lo += 1
        rng = np.random.default_rng([int(seed), _SYM_INDEX.get(ctx.symbol, 99), _TF_INDEX[tf]])
        sets, trade, bars_, side, sd, hold = [], [], [], [], [], []
        for q, row in zip(g.index, g.itertuples(index=False)):
            h = int(row.hold)
            hi = nb - 1 - h
            if hi < lo or not (math.isfinite(row.stop_atr) and row.stop_atr > 0):
                continue
            bb = rng.integers(lo, hi + 1, size=n_sets)
            if not ok[bb].all():
                raise AssertionError(f"{ctx.symbol} {tf}: a placebo bar without an ATR inside the window")
            sets.append(np.arange(n_sets))
            trade.append(np.full(n_sets, q))
            bars_.append(bb)
            side.append(np.full(n_sets, int(row.side)))
            sd.append(float(row.stop_atr) * atr[bb])
            hold.append(np.full(n_sets, h))
        if not bars_:
            continue
        cat = lambda xs, dt: np.concatenate(xs).astype(dt)
        S, Q, B, D, SD, H = (cat(sets, np.int64), cat(trade, np.int64), cat(bars_, np.int64), cat(side, np.int64),
                             cat(sd, np.float64), cat(hold, np.int64))
        idx = np.arange(len(B), dtype=np.int64)
        got = np.full(len(B), -1, np.int64)
        eix, xix = np.full(len(B), -1, np.int64), np.full(len(B), -1, np.int64)
        pnl, rr = np.full(len(B), np.nan), np.full(len(B), np.nan)
        why = np.empty(len(B), object)
        for lane in _lanes(b.ex[B], b.ex[B + H]):
            E = M.entries(B[lane], D[lane], stop_dist=SD[lane], exit_bar=B[lane] + H[lane], tag=idx[lane])
            run = M.run_exec(ctx.mk, M.event_exec(tf, entries=E), a, z, cost)
            if run.counts["taken"] != len(lane) or len(run.trades) != len(lane):
                raise AssertionError(f"{ctx.symbol} {tf}: a placebo lane skipped or dropped a trade {run.counts}")
            t = run.trades["tag"].to_numpy(np.int64)
            got[t] = 1
            eix[t] = run.trades["entry_ix"].to_numpy(np.int64)
            xix[t] = run.trades["exit_ix"].to_numpy(np.int64)
            pnl[t] = run.trades["pnl"].to_numpy(np.float64)
            rr[t] = run.trades["r"].to_numpy(np.float64)
            why[t] = run.trades["reason"].to_numpy(object)
        if (got < 0).any():
            raise AssertionError(f"{ctx.symbol} {tf}: a placebo trade was not executed")
        rows.append(pd.DataFrame({"set": S, "trade": Q, "symbol": ctx.symbol, "tf": tf, "bar": B, "side": D,
                                  "stop_atr": SD / atr[B], "hold": H, "entry_ix": eix, "exit_ix": xix, "reason": why,
                                  "pnl": pnl, "r": rr}))
    cols = ["set", "trade", "symbol", "tf", "bar", "side", "stop_atr", "hold", "entry_ix", "exit_ix", "reason", "pnl",
            "r"]
    return pd.concat(rows, ignore_index=True)[cols] if rows else pd.DataFrame(columns=cols)


def pooled_stats(real: pd.DataFrame, placebo: pd.DataFrame, n_sets: int = N_PLACEBO) -> Tuple[Dict[str, object],
                                                                                              pd.DataFrame]:
    """The statistics of the pooled test: over the real trades that have a placebo, their number, mean R, total R and
    total dollars per 0.01 lot; per placebo set the same; the one-sided p-values p = (1 + #{sets >= real}) / (1 +
    n_sets) of the mean R (primary) and of the dollars. Returns (summary, per-set table)."""
    matched = sorted(set(placebo["trade"].astype(np.int64))) if len(placebo) else []
    rm = real.loc[matched] if matched else real.iloc[:0]

    def stat(r, pnl):
        # one arithmetic for the real trades and every set (np.sum in the order of the real trades), so a placebo
        # set equal to the real trades gives the same bits and counts as ">=" (the conservative tie rule)
        return (len(r), float(np.sum(r)) / len(r) if len(r) else np.nan, float(np.sum(r)), float(np.sum(pnl)))
    rows = [(k, *stat(np.zeros(0), np.zeros(0))) for k in range(n_sets)]
    if len(placebo):
        p = placebo.sort_values(["set", "trade"], kind="stable")
        sets = p["set"].to_numpy(np.int64)
        r_, pnl_ = p["r"].to_numpy(np.float64), p["pnl"].to_numpy(np.float64)
        cut = np.flatnonzero(np.diff(sets)) + 1
        for g_r, g_p, g_s in zip(np.split(r_, cut), np.split(pnl_, cut), np.split(sets, cut)):
            rows[int(g_s[0])] = (int(g_s[0]), *stat(g_r, g_p))
    per = pd.DataFrame(rows, columns=["set", "n", "mean_r", "total_r", "total_usd"]).set_index("set")
    n = int(len(rm))
    s = {"n_real": int(len(real)), "n_matched": n, "n_unmatched": int(len(real) - n), "n_sets": int(n_sets)}
    if n == 0:
        s.update({"mean_r": np.nan, "total_r": np.nan, "total_usd": np.nan, "p_r": np.nan, "p_usd": np.nan,
                  "placebo_mean_r_median": np.nan, "placebo_mean_r_p95": np.nan, "placebo_usd_median": np.nan,
                  "placebo_usd_p95": np.nan})
        return s, per.reset_index()
    _, mr, tr_, tu = stat(rm["r"].to_numpy(np.float64), rm["pnl"].to_numpy(np.float64))
    s.update({"mean_r": mr, "total_r": tr_, "total_usd": tu,
              "p_r": (1.0 + float((per["mean_r"].to_numpy() >= mr).sum())) / (n_sets + 1.0),
              "p_usd": (1.0 + float((per["total_usd"].to_numpy() >= tu).sum())) / (n_sets + 1.0),
              "placebo_mean_r_median": float(per["mean_r"].median()),
              "placebo_mean_r_p95": float(per["mean_r"].quantile(0.95)),
              "placebo_usd_median": float(per["total_usd"].median()),
              "placebo_usd_p95": float(per["total_usd"].quantile(0.95))})
    return s, per.reset_index()


@dataclass
class PooledTest:
    """``pooled_test_run``'s result: ``summary`` (pooled_stats plus the window, cost and seed), ``real`` (the real
    trades), ``placebo`` (every placebo trade), ``sets`` (per placebo set), ``by_series`` (per symbol and timeframe:
    the real trades' number, mean R and dollars, and the placebo trades' mean R and dollars per set)."""
    summary: Dict[str, object]
    real: pd.DataFrame
    placebo: pd.DataFrame
    sets: pd.DataFrame
    by_series: pd.DataFrame


def pooled_test_run(contexts: Mapping[str, M.Context], window="devval", n_sets: int = N_PLACEBO,
                    seed: int = PLACEBO_SEED, cost: float = 1.0) -> PooledTest:
    """PREREG 6.3's primary pooled test (deviation D7): WY-STD x S-W x X-S x F0 over the symbols of ``contexts`` (gold
    and BTC) and 1H / 4H / 1D in ``window`` (Development + Validation: 'devval'; a (start, end) pair in tests), against
    ``n_sets`` matched placebo sets. Computes profit and loss: run it only in the study's run of the claims."""
    real, plac = [], []
    for s in sorted(contexts, key=lambda x: _SYM_INDEX.get(x, 99)):
        ctx = contexts[s]
        r = pooled_trades(ctx, window, cost)
        r.index = r.index + sum(len(x) for x in real)
        real.append(r)
    real_all = pd.concat(real) if real else pd.DataFrame()
    for s in sorted(contexts, key=lambda x: _SYM_INDEX.get(x, 99)):
        plac.append(placebo_trades(contexts[s], real_all, n_sets, seed, window, cost))
    plac_all = pd.concat(plac, ignore_index=True) if plac else pd.DataFrame()
    summary, sets = pooled_stats(real_all, plac_all, n_sets)
    summary.update({"window": window if isinstance(window, str) else f"{window[0]} .. {window[1]}",
                    "cost": float(cost), "seed": int(seed),
                    "statistic": "mean R (primary), total dollars per 0.01 lot"})
    rows = []
    for (s, tf), g in real_all.groupby(["symbol", "tf"], sort=False) if len(real_all) else []:
        p = plac_all[(plac_all.symbol == s) & (plac_all.tf == tf)] if len(plac_all) else plac_all
        ps = p.groupby("set").agg(mean_r=("r", "mean"), usd=("pnl", "sum")) if len(p) else None
        rows.append({"symbol": s, "tf": tf, "trades": int(len(g)), "mean_r": float(g["r"].mean()),
                     "usd": float(g["pnl"].sum()), "placebo_trades_per_set": int(len(p) // max(n_sets, 1)),
                     "placebo_mean_r_median": float(ps["mean_r"].median()) if ps is not None else np.nan,
                     "placebo_usd_median": float(ps["usd"].median()) if ps is not None else np.nan})
    return PooledTest(summary, real_all, plac_all, sets, pd.DataFrame(rows))


def _windows_of(ev) -> Tuple[str, ...]:
    w = tuple(getattr(ev, "windows", ("dev", "val")))
    return w


def pooled_test(ev, n_sets: int = N_PLACEBO, seed: int = PLACEBO_SEED) -> List[Dict[str, object]]:
    """The driver's claim-15 extra (``tradeiq2.EXTRAS['claim15']``): the pooled test as one row of the claims table.
    With the Development / Validation evidence the test runs once over Development + Validation (PREREG 6.3); with the
    hold-out evidence (after the freeze) over the hold-out. The verdict is the primary p-value's: "holds" at
    p < 0.05."""
    w = _windows_of(ev)
    window = "devval" if set(w) <= {"dev", "val", "devval"} else w[0]
    syms = [s for s in M.SYMBOLS if s in set(getattr(ev, "symbols", M.SYMBOLS))]
    res = pooled_test_run({s: ev.context(s) for s in syms}, window=window, n_sets=n_sets, seed=seed)
    s = res.summary
    part = ("when it shows up it means something: the Standard entries beat 1,000 matched random-entry sets "
            "(the pooled test, one-sided p < 0.05 on the mean R)")
    rows = ("WY-STD x S-W x X-S x F0, " + " and ".join(syms) + ", 1H / 4H / 1D, " + M.WINDOW_NAMES.get(window, window)
            + ", x1.0")
    if s["n_matched"] == 0:
        return [{"part": part, "symbol": "both", "rows": rows, "dev": "no trades", "val": "", "dev_ok": np.nan,
                 "val_ok": np.nan, "verdict": "cannot be tested", "note": "no Standard entry was traded"}]
    ok = bool(s["p_r"] < P_LEVEL)
    txt = (f"{s['n_matched']} trades, mean R {s['mean_r']:+.3f} against a placebo median of "
           f"{s['placebo_mean_r_median']:+.3f}: p = {s['p_r']:.3f}")
    note = (f"one pooled test over {M.WINDOW_NAMES.get(window, window)} (PREREG 6.3), {s['n_sets']} placebo sets "
            f"matched on symbol, timeframe, side, stop distance in ATR and holding time (seed {s['seed']}); in "
            f"dollars per 0.01 lot: {s['total_usd']:+.2f} against a placebo median of {s['placebo_usd_median']:+.2f}, "
            f"p = {s['p_usd']:.3f}; {s['n_unmatched']} trades without a placebo")
    return [{"part": part, "symbol": "both", "rows": rows, "dev": txt,
             "val": "pooled with Development (one test)" if window == "devval" else "",
             "dev_ok": ok, "val_ok": ok, "verdict": "holds" if ok else "does not hold", "note": note}]


# ───────────────────────────── claim 16 (PREREG 8): the risk at the spring and the test ─────────────────────────────

def entry_geometry(ctx: M.Context, window: str) -> pd.DataFrame:
    """The script's entries in ``window`` (Standard: test, terminal test and LPS entries; Aggressive: its SOS / SOW
    entries, the ones Standard does not take), per symbol and timeframe, with their S-W stop distance from the
    decision close in ATR and whether the guard keeps them. Geometry only."""
    _, _, a_s, iz = _span(ctx, window)
    rows = []
    for tf in TFS:
        b = ctx.bars(tf)
        out = engine(ctx, tf, VOLUME[ctx.symbol])
        for rule, kinds in (("WY-STD", (K_TEST, K_CTEST, K_LPS)), ("WY-AGG", (K_SOS,))):
            ev = candidate_events(out, b.c, ctx.atr(tf), rule)
            w = (b.tc[ev["bar"]] > a_s) & (b.ex[ev["bar"]] < iz) & np.isin(ev["kind"], kinds) & ev["valid"]
            for k in np.flatnonzero(w):
                rows.append({"symbol": ctx.symbol, "tf": tf, "window": window, "bar": int(ev["bar"][k]),
                             "rule": rule, "kind": int(ev["kind"][k]), "side": int(ev["side"][k]),
                             "stop_atr": float(ev["dist_atr"][k]), "guard": bool(ev["guard"][k])})
    return pd.DataFrame(rows, columns=["symbol", "tf", "window", "bar", "rule", "kind", "side", "stop_atr", "guard"])


_GROUPS = {"test": (K_TEST, K_CTEST), "SOS": (K_SOS,), "LPS": (K_LPS,)}


def _group_of(kind: np.ndarray) -> np.ndarray:
    k = np.asarray(kind, np.int64)
    return np.where(np.isin(k, _GROUPS["test"]), "test", np.where(k == K_SOS, "SOS", np.where(k == K_LPS, "LPS", "")))


def claim16(ev) -> List[Dict[str, object]]:
    """The driver's claim-16 extra: "the risk is smallest at the spring and the test" (PREREG 8). Two parts, pooled
    over both symbols and the three timeframes, per window: (1) the median S-W stop distance in ATR at the test entries
    (Standard test and terminal-test entries) is below that at the Aggressive SOS entries and at the LPS entries; (2)
    the test entries' trades have a higher average R than the SOS and LPS entries' (WY-STD x S-W x X-S x F0 for test
    and LPS entries, WY-AGG x S-W x X-S x F0 for SOS entries, x1.0)."""
    w0, w1 = _windows_of(ev)
    syms = [s for s in M.SYMBOLS if s in set(getattr(ev, "symbols", M.SYMBOLS))]
    geo = {w: pd.concat([entry_geometry(ev.context(s), w) for s in syms], ignore_index=True) for w in {w0, w1}}

    def med(w):
        g = geo[w][geo[w].guard]
        grp = _group_of(g["kind"].to_numpy())
        return {k: (float(np.median(g["stop_atr"][grp == k])) if (grp == k).any() else np.nan, int((grp == k).sum()))
                for k in _GROUPS}

    def txt(d):
        return ", ".join(f"{k} {v:.2f} (n {n})" if math.isfinite(v) else f"{k} - (n 0)" for k, (v, n) in d.items())

    def smallest(d):
        t, s_, l_ = d["test"][0], d["SOS"][0], d["LPS"][0]
        return bool(math.isfinite(t) and math.isfinite(s_) and math.isfinite(l_) and t < min(s_, l_))

    m0, m1 = med(w0), med(w1)
    out = [{"part": "the stop is closest at the test: the median S-W stop distance (ATR) at test entries is below "
                    "the SOS and the LPS entries'", "symbol": "both",
            "rows": "the Standard and Aggressive entry alerts, gold and BTC, 1H / 4H / 1D (geometry, no P/L)",
            "dev": txt(m0), "val": txt(m1), "dev_ok": smallest(m0), "val_ok": smallest(m1),
            "note": "distance from the decision close to the S-W stop in ATR(14) of the entry bar; entries the guard "
                    "skips are left out"}]
    ids = {f"{s}|{tf}|{FAMILY}|{rule}|S-W|X-S|F0": kinds for s in syms for tf in TFS
           for rule, kinds in (("WY-STD", (K_TEST, K_CTEST, K_LPS)), ("WY-AGG", (K_SOS,)))}

    def avg_r(w):
        tr = ev.trades(w)
        tr = tr[tr.vid.isin(list(ids)) & (np.asarray(tr["cost"], np.float64) == 1.0)]
        keep = np.asarray([int(k) in ids[v] for v, k in zip(tr.vid, kind_of_tag(tr["tag"].to_numpy(np.int64)))],
                          bool) if len(tr) else np.zeros(0, bool)
        tr = tr[keep]
        grp = _group_of(kind_of_tag(tr["tag"].to_numpy(np.int64))) if len(tr) else np.zeros(0, object)
        r = tr["r"].to_numpy(np.float64) if len(tr) else np.zeros(0)
        return {k: (float(np.nanmean(r[grp == k])) if (grp == k).any() else np.nan, int((grp == k).sum()))
                for k in _GROUPS}

    def most(d):
        t, s_, l_ = d["test"][0], d["SOS"][0], d["LPS"][0]
        return bool(math.isfinite(t) and math.isfinite(s_) and math.isfinite(l_) and t > max(s_, l_))

    r0, r1 = avg_r(w0), avg_r(w1)
    out.append({"part": "the test entries earn more: their average R is above the SOS and the LPS entries'",
                "symbol": "both", "rows": "WY-STD (test, LPS) and WY-AGG (SOS) x S-W x X-S x F0, gold and BTC, "
                                         "1H / 4H / 1D, x1.0",
                "dev": txt(r0), "val": txt(r1), "dev_ok": most(r0), "val_ok": most(r1),
                "note": "R = the trade's P/L after costs over its initial risk; the entry type from the trade's tag"})
    return out
