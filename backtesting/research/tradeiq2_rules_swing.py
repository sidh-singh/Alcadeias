"""
Swing Profile (BigBeluga) as rules (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.4): the rule rows of
the swing module for the driver (``tradeiq2.py``), ``variants(symbol)`` and ``build(variant, ctx)``.

    from backtesting.research import tradeiq2_market as M, tradeiq2_rules_swing as RS
    ctx = M.Context(M.load("XAUUSDm"))                 # to the hold-out start
    vs = RS.variants("XAUUSDm")                         # 36 rows: 24 eligible + 12 placebo rows (not eligible)
    ex = RS.build(vs[0], ctx)                           # an EVENTS Exec of tradeiq2_market
    res = M.run_variant(ctx, vs[0], ex)                 # Development, Validation and D+V at x1.0 and x1.5

The plan is PREREG.md (frozen; read with ``DEVIATIONS.md``): sections 4 (execution, the rules for absolute levels), 5
(the filters and how they apply), 6.4 (SP-W1 to SP-W3, the filters F0 / FD / F2 / LO, the 50% placebo) and 7
(families, eligibility). The indicator is the reconciled port ``tradeiq2_ind_swing`` (port A, equal bit for bit to
port B on the study's 1H / 4H bars of both symbols; ``backtest_results/tradeiq_2027/porting/swing.md``), run with the
script's defaults on the bid bars of ``tradeiq2_market.load`` from the symbol's data start (gold 2016-01-03, BTC
2018-01-01), gold on its tick volume and BTC on Binance BTCUSDT spot volume (PREREG 2; ``Context.volume``). The filters
are ``tradeiq2_filters`` and the execution ``tradeiq2_market`` (study 1's fills, stops, marks and scores). Nothing is
tuned: every input is the script's default. Line numbers l. are those of the owner's plain-text copy of "Swing Profile
[BigBeluga]" (Pine v6, CC BY-NC-SA 4.0, l.1-424); it is third-party code, cited here, never copied.

The grid (per symbol; XAUUSDm and BTCUSDm only, none on the claim markets)
--------------------------------------------------------------------------
Ids: ``symbol|tf|SP|rule|level|filter``, e.g. ``XAUUSDm|1H|SP|W2|POC|FD`` and its placebo ``XAUUSDm|1H|SP|W2|L50|F0``.

======== ========================================================================= ===== ===========================
family   rows                                                                      n     eligible
======== ========================================================================= ===== ===========================
SP       W1, W2, W3 x level POC x filters F0, FD, F2, LO x 1H, 4H                   24    yes
SP       the placebo: W1, W2, W3 x level L50 (the leg's 50% level) x F0, F2 x 1H, 4H 12    no ("control; not eligible")
======== ========================================================================= ===== ===========================

That is PREREG 6.4's "3 x 4 x 2 = 24 eligible rows, plus 12 placebo rows, per symbol"; section 7 puts them in the
family SP (the placebo rows are scored, never selected). F2 is F2-4H on 1H and F2-1D on 4H (6.4 "Filters"). The driver
pairs a placebo row with its POC row by the tokens W1-W3 and F0 / F2-4H / F2-1D (claim 11; ``tradeiq2._claim11``), so
the params of a row never carry another of those tokens.

What the indicator gives each bar (the port's contract, ``tradeiq2_ind_swing``; known at the bar's close)
-------------------------------------------------------------------------------------------------------
* ``is_down_move`` (l.69-72): true from a bar that is a new 50-bar high, false from one that is a new 50-bar low (the
  low wins on a bar that is both); ``flip`` (l.90) where it changes. A flip to false (a new low) finishes the UP leg,
  a flip to true the DOWN leg.
* The stored swing high and low (l.75-82: bar and price), each confirmed one bar late. The FORMING leg is the leg
  between them: ``f_dir`` +1 (up: the swing high is the newer point), -1 (down), 0 (a point missing, or both the same
  outside bar); ``f_lo`` / ``f_hi``; its volume profile recomputed at every bar with that bar's ATR(200) (l.106-154,
  the forming copy l.214-258): ``f_poc`` (the drawn level of the bin with the most volume; ties go to the bin nearest
  the bar's close), ``f_delta_pct`` ((buy - sell) / total of the bins, l.183-187).
* The FINISHED legs (``legs``): one row per flip, known from its flip bar's close on (its POC and delta are drawn
  back over the leg by the script, which is look-ahead before the flip bar): ``dir`` (+1 the up leg, -1 the down leg:
  the flip's side), ``poc`` (ties to the bin nearest the flip bar's close, then fixed), ``fifty`` = (lo + hi) / 2,
  ``delta_pct``.

The rules (event rules; "at most one trade per swing anchor; shorts mirror longs", PREREG 6.4)
--------------------------------------------------------------------------------------------
A TOUCH AND HOLD of a level P on bar t: long ``low[t] <= P < close[t]``, short ``high[t] >= P > close[t]`` (6.4: "a
bar with low <= POC and close > POC"). Every decision is taken at the close of bar t and filled at the open of the
first M1 bar at or after that close (a buy at the ask, a sell at the bid; PREREG 4). ATR = Pine ``ta.atr(14)`` of the
signal timeframe at the decision bar (``Context.atr``; PREREG 5), not the script's ATR(200).

* SP-W1, the video's use. While the forming leg is up (``f_dir == +1``), a touch and hold of its POC ``f_poc[t]``
  gives a long; while it is down (``f_dir == -1``) a touch and hold from below gives a short. Stop at the leg's swing
  low (the stored low's price at bar t), target the leg's swing high (the stored high's price at bar t); shorts: stop
  at the swing high, target the swing low. Exit at the close of a flip against the trade (a long: a flip to a new
  50-bar low, ``flip & ~is_down_move``; a short: a flip to a new high), filled at the next M1 open; or the stop or
  the target. ANCHOR: the swing point the forming leg starts from, the stored swing low for a long (``ls_bar``), the
  stored swing high for a short (``hs_bar``); it stays the same while the leg extends to newer highs (lows), and an
  anchor never returns once a newer swing point replaces it.
* SP-W2: as W1, with the stop at POC - 1.5 ATR (a short: POC + 1.5 ATR) and the target at 2R, R = |fill - stop|.
* SP-W3: after a flip, a touch and hold of the just-finished leg's POC in the new direction: after a flip to a new
  high (the down leg finished) a long, after a flip to a new low (the up leg finished) a short. The level is
  ``legs.poc`` of the latest flip before bar t, on the bars after its flip bar up to the next flip bar (reading R4).
  Stop POC -/+ 1.5 ATR, target 2R; no other exit. ANCHOR: the finished leg (its flip bar).
* PLACEBO (control; not eligible): W1-W3 with the POC replaced by the same leg's 50% level, (f_lo + f_hi) / 2 for the
  forming leg (W1, W2) and ``legs.fifty`` for the finished leg (W3); everything else as the POC row (anchors, W1's
  swing stop and target, the 50% level -/+ 1.5 ATR and 2R for W2 / W3, the exits); filters F0 and F2.

FILTERS (PREREG 5 on an event rule: the filter must agree at the decision close of the entry; it never closes an
open trade, which keeps its own exits):
* F0: none. LO: long only (``tradeiq2_filters`` 'LO'). F2: F2-4H on 1H, F2-1D on 4H (the last closed higher bar's
  close against its MA200; ``tradeiq2_filters``).
* FD, the video's "a leg up with weak buying is a warning": the leg's delta on the trade's side, delta > 0 for a long,
  delta < 0 for a short (0 or NaN allows neither). The leg is the one whose POC the rule trades: the forming leg at the
  decision bar (``f_delta_pct[t]``) for W1 / W2, the just-finished leg (``legs.delta_pct``) for W3.

ONE TRADE PER ANCHOR: of the touch-and-hold bars of an anchor whose levels exist and that the row's filter allows,
the FIRST is the anchor's one candidate (reading R1). The harness then executes one position at a time (a candidate
decided while a trade is open is skipped, "busy") and applies PREREG 4's rules for absolute levels: every stop and
target level L is a distance |fill - L| from the actual fill, an entry whose fill is at or beyond its stop or target
is dropped, and the x1.5 run recomputes each from its own fill. The stop and target never move. ``tag`` of every
entry = its anchor's bar (W1 / W2: the swing point's bar; W3: the finished leg's flip bar), so each trade names its
anchor.

What is known when (no look-ahead)
----------------------------------
Every decision of bar t reads the port's values at t (the flag and the window t-49 .. t, the swing points confirmed by
t's close, the forming leg's bars between them, the ATR(200) and the close of t; a finished leg only from its flip bar
on), the ATR(14) to t, and for F2 the last 4H / 1D bar CLOSED at t's close (``tradeiq_market.htf_at``). The first
candidate of an anchor is the first of its bars up to t. The flip exits are flips of later bars. Removing the bars
after t changes no decision up to t (tested on synthetic and real bars).

Readings where the plan leaves a choice (proposed for DEVIATIONS.md)
--------------------------------------------------------------------
Counts are of the Development decision bars (a bar closing after 2019-01-01 00:00 UTC whose fill comes before
2023-01-01), from the module's ``event_counts`` on the study's bars; counts and geometry only, no profit or loss.

R1. "At most one trade per swing anchor" is one CANDIDATE per anchor: the first touch and hold of the anchor whose
    levels exist and that the row's filter allows. When it is busy (another trade is open) or dropped by PREREG 4 (its
    fill at or beyond its stop or target), the anchor gets no trade; a later touch of the same anchor is not tried.
    Why: the harness executes one fixed list of candidates for every window and for both costs, so a list in which a
    later touch depended on whether an earlier one filled would differ between x1.0 and x1.5 and between windows; and
    the first pullback to the level is the event the video describes ("when a pullback reaches it"). An anchor whose
    first touch comes before a window's start has no candidate in that window (the window starts flat; PREREG 3). It
    affects every row. With F0 in Development: W1 / W2 have 227 / 61 candidates on gold 1H / 4H (from 1,083 / 284
    touch-and-hold bars) and 326 / 73 on BTC (1,846 / 400); W3 has 161 / 42 on gold (725 / 198 bars) and 214 / 47 on
    BTC (1,032 / 210).
R2. The filter comes before the one-per-anchor rule: a touch the filter refuses (F2, LO, FD) is no entry, so it does
    not use up the anchor, and a later touch of the same anchor that the filter allows can be its candidate. A
    filtered row's candidates are therefore not always a subset of the F0 row's.
R3. W1 / W2's "while the forming leg is up" is the forming leg's geometry ``f_dir`` (porting/swing.md, reading 1; the
    specification's "its confirmed high is newer than its confirmed low"): no trigger while both stored swing points
    are one outside bar (``f_dir == 0``; 46 gold 1H and 115 BTC 1H bars). On a flip bar and until the new extreme is
    confirmed, the stored pair is still the leg the flip just finished, so W1 / W2 can trigger there with the script's
    flag already against the trade. The "flip against" of such a trade is the next one after its decision bar
    (per-bar exits act from the bar after the decision; ``tradeiq2_market``), so it ends at its stop, its target or
    that later flip. W1 / W2 x F0 candidates in such a window (``event_counts`` ``n_flag_against``): gold 9 / 2 (1H /
    4H), BTC 8 / 2; the placebo's W1 / W2 x F0: gold 28 / 4, BTC 41 / 4. A rule that required the flag to agree would
    drop them.
R4. W3's window is the bars AFTER the flip bar up to the next flip bar (excluded), one candidate per finished leg.
    "After a flip": the flip and the finished leg's POC are known only at the flip bar's close (PREREG 6.4 "used only
    from its flip bar on"), so the flip bar's own low or high reached the level before either was known; read from
    the flip bar on, the first touch would be the flip bar itself (a bar through the POC, not a return to it) for 58 /
    22 of the F0 legs on gold 1H / 4H and 113 / 19 on BTC (``n_w3_flip_bar_alt``). The touch is W1's bar shape in the
    new direction. The specification's extra condition ("if the close is already past the finished leg's POC in the
    new direction", map 3.5) is not in the PREREG and is not applied: 56 / 12 (gold) and 61 / 14 (BTC) of the W3 x F0
    candidates are on legs whose flip bar's close had not passed the POC (``n_not_past_at_flip``), where the first
    touch is a close through the POC rather than a pullback to it.
R5. W3's exits are the stop and the 2R target only: W3 is not "as W1" and the PREREG names no other exit. A W3 trade
    can therefore still be open at the next flip, and the next leg's first touch is then busy (R1).
R6. FD's leg is the one whose level the rule trades: the forming leg at the decision bar for W1 / W2, the just-finished
    leg for W3 (so a W3 short after an up leg needs that up leg's delta below 0, "a leg up with weak buying", which is
    also how claim 12 reads the warning: it is about the next leg). The delta is the script's bin sums (porting/swing.md
    reading 3); a delta of exactly 0 or NaN allows neither side. Consequence: a finished leg's delta has its own
    direction's sign in 93-97 % of the Development legs (against it: gold 14 of 318 1H and 6 of 88 4H legs, BTC 34 of
    458 and 3 of 108), so W3 x FD keeps only 4 / 1 Development candidates on gold 1H / 4H and 16 / 1 on BTC (of 161 /
    42 and 214 / 47): those rows fall short of the 30-trade minimum. W1 / W2 x FD keep 219 / 58 (gold) and 308 /
    73 (BTC) of the F0 rows' 227 / 61 and 326 / 73.
R7. W1's stop and target are the stored swing prices of the decision bar (an up leg's swing low and swing high), fixed
    for the trade's life although the forming leg may later extend; a touch whose target does not lie beyond its stop
    (a stored pair whose prices run against its order) is no entry (never in Development). W2 / W3's stop is the level
    -/+ 1.5 ATR(14) of the decision bar (PREREG 5's ATR, not the script's ATR(200)); 1R = |fill - stop|
    (``tradeiq2_market``).
R8. The placebo's level is the same leg's 50% level computed as the port's ``fifty``, (lo + hi) / 2, for the forming
    leg too. The placebo reads the same profile (its swing points and flips do not depend on the volume).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import tradeiq2_filters as F
from . import tradeiq2_ind_swing as SP
from . import tradeiq2_market as M

__all__ = ["MODULE", "SCRIPT", "FAMILY", "TFS", "RULES", "LEVELS", "FILTER_SLOTS", "PLACEBO_SLOTS", "F2_OF",
           "VOLUME", "STOP_ATR", "TARGET_R", "EXPECTED", "variants", "build", "describe", "warm", "spec_of",
           "profile", "use_profile", "triggers", "trigger_table", "first_per_anchor", "active_leg", "flip_exits",
           "exits_of", "fd_allow", "allow_of", "rule_entries", "event_counts", "plan_counts"]

MODULE = "tradeiq2_rules_swing"          # the Context cache's module key
SCRIPT = "SP"
FAMILY = "SP"                            # PREREG 7: "SP | Swing Profile"
TFS = ("1H", "4H")                       # PREREG 6.4: "Swing Profile (SP), 1H / 4H"
RULES = ("W1", "W2", "W3")
LEVELS = ("POC", "L50")                  # the level a rule touches: the POC, or the placebo's 50% level
FILTER_SLOTS = ("F0", "FD", "F2", "LO")  # PREREG 6.4 "Filters", in its order
PLACEBO_SLOTS = ("F0", "F2")             # PREREG 6.4 "Placebo ... F0 and F2"
F2_OF = {"1H": "F2-4H", "4H": "F2-1D"}   # PREREG 6.4: "1H rows use F2-4H, 4H rows F2-1D"
VOLUME = {M.GOLD: "tick", M.BTC: "binance"}     # PREREG 2: gold tick volume, BTC Binance BTCUSDT spot volume
STOP_ATR = 1.5                           # W2 / W3: the stop 1.5 ATR(14) beyond the level
TARGET_R = 2.0                           # W2 / W3: the target at 2R
PLACEBO_INFO = "placebo (control): the leg's 50% level in place of the POC; not eligible"
PROFILE_KEY = "profile"

# PREREG 6.4 "Size: 3 x 4 x 2 = 24 eligible rows, plus 12 placebo rows, per symbol": (family, eligible) -> rows
EXPECTED = {M.GOLD: {(FAMILY, True): 24, (FAMILY, False): 12}, M.BTC: {(FAMILY, True): 24, (FAMILY, False): 12}}


@dataclass(frozen=True)
class Rule:
    """One rule of PREREG 6.4: the leg whose level it touches, its stop, its target and whether a flip against the
    trade closes it."""
    name: str
    leg: str            # "forming" (W1, W2) or "finished" (W3)
    stop: str           # "swing": the leg's first swing point (W1); "level": the level -/+ 1.5 ATR(14)
    target: str         # "swing": the leg's last swing point (W1); "2R"
    flip_exit: bool     # exit at the close of a flip against the trade


RULE: Dict[str, Rule] = {
    "W1": Rule("W1", "forming", "swing", "swing", True),
    "W2": Rule("W2", "forming", "level", "2R", True),
    "W3": Rule("W3", "finished", "level", "2R", False),
}


def _ro(a) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _check_tf(tf: str) -> None:
    if tf not in TFS:
        raise ValueError(f"{tf}: the Swing Profile rules run on {', '.join(TFS)} (PREREG 6.4)")


def _check(rule: str, level: str) -> Rule:
    if rule not in RULE:
        raise ValueError(f"{rule}: one of {', '.join(RULES)}")
    if level not in LEVELS:
        raise ValueError(f"{level}: one of {', '.join(LEVELS)}")
    return RULE[rule]


# ───────────────────────────── the grid (PREREG 6.4 and 7) ─────────────────────────────

def _variant(symbol: str, tf: str, rule: str, level: str, slot: str) -> M.Variant:
    filt = F2_OF[tf] if slot == "F2" else slot
    r = RULE[rule]
    placebo = level == "L50"
    params = {"rule": rule, "level": level, "filter": filt, "side": "LO" if filt == "LO" else "LS", "leg": r.leg,
              "stop": "swing" if r.stop == "swing" else f"level-{STOP_ATR:g}ATR",
              "target": "swing" if r.target == "swing" else f"{TARGET_R:g}R", "flip_exit": bool(r.flip_exit),
              "volume": VOLUME[symbol]}
    vid = f"{symbol}|{tf}|{FAMILY}|{rule}|{level}|{filt}"
    return M.Variant(vid, symbol, tf, SCRIPT, FAMILY, not placebo, PLACEBO_INFO if placebo else "", params)


def variants(symbol: str) -> List[M.Variant]:
    """
    EXACTLY PREREG 6.4's rows of ``symbol``: on XAUUSDm and BTCUSDm 24 eligible rows (W1, W2, W3 x POC x F0, FD, F2, LO
    x 1H, 4H) and 12 placebo rows (W1, W2, W3 x L50 x F0, F2 x 1H, 4H; eligible=False), in that order (timeframe,
    rule, filter); none on the claim markets (PREREG 8 checks only Session Hunter there). Raises for a symbol that is
    not the study's.
    """
    if symbol not in M.ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(M.ALL_SYMBOLS)})")
    if symbol not in M.SYMBOLS:
        return []
    out = [_variant(symbol, tf, rule, "POC", slot) for tf in TFS for rule in RULES for slot in FILTER_SLOTS]
    out += [_variant(symbol, tf, rule, "L50", slot) for tf in TFS for rule in RULES for slot in PLACEBO_SLOTS]
    return out


_CANON: Dict[str, Dict[str, M.Variant]] = {}


def _canonical(symbol: str) -> Dict[str, M.Variant]:
    if symbol not in _CANON:
        _CANON[symbol] = {v.id: v for v in variants(symbol)}
    return _CANON[symbol]


@dataclass(frozen=True)
class Spec:
    """What a row is: its rule, level and filter (the concrete name: F0, FD, F2-4H, F2-1D or LO)."""
    rule: Rule
    level: str
    filter: str
    placebo: bool


def spec_of(variant: M.Variant) -> Spec:
    """The rule row of a variant of ``variants`` (looked up by its id; its timeframe and family must match)."""
    v = _canonical(variant.symbol).get(variant.id) if variant.symbol in M.ALL_SYMBOLS else None
    if v is None or (v.tf, v.family) != (variant.tf, variant.family):
        raise ValueError(f"{variant.id}: not a row of PREREG 6.4 (tradeiq2_rules_swing.variants)")
    p = dict(v.params)
    return Spec(RULE[p["rule"]], p["level"], p["filter"], p["level"] == "L50")


def plan_counts(symbol: str) -> Dict[Tuple[str, bool], int]:
    """The rows ``variants(symbol)`` gives per (family, eligible), for the grid check."""
    out: Dict[Tuple[str, bool], int] = {}
    for v in variants(symbol):
        out[(v.family, bool(v.eligible))] = out.get((v.family, bool(v.eligible)), 0) + 1
    return out


# ───────────────────────────── the indicator (cached in the Context) ─────────────────────────────

def _volume_source(ctx: M.Context) -> str:
    return VOLUME.get(ctx.symbol, "tick")


def _pack(out: Mapping[str, object], n: int) -> Dict[str, object]:
    """The port's output (``SP.KEYS``) as read-only arrays, with the finished legs' columns as arrays ``leg_*``."""
    if tuple(out) != SP.KEYS:
        raise ValueError(f"a swing profile has exactly the port's keys {SP.KEYS}")
    for k in SP.KEYS[:-1]:
        if np.shape(out[k]) != (n,):
            raise ValueError(f"{k}: one value per bar ({n}) is expected, got shape {np.shape(out[k])}")
    legs = out["legs"]
    if list(legs.columns) != list(SP.LEG_COLUMNS):
        raise ValueError(f"legs: the columns {SP.LEG_COLUMNS} are expected")
    fb = legs["flip_bar"].to_numpy(np.int64)
    if len(fb) and (np.any(np.diff(fb) <= 0) or fb[0] < 0 or fb[-1] >= n):
        raise ValueError("legs: one row per flip bar, in order, inside the bars")
    p: Dict[str, object] = {k: _ro(np.array(out[k])) for k in SP.KEYS[:-1]}
    p["legs"] = legs
    p["leg_flip_bar"] = _ro(fb.copy())
    p["leg_dir"] = _ro(legs["dir"].to_numpy(np.int64).copy())
    for k in ("poc", "fifty", "delta_pct", "lo", "hi"):
        p[f"leg_{k}"] = _ro(legs[k].to_numpy(np.float64).copy())
    return p


def profile(ctx: M.Context, tf: str) -> Dict[str, object]:
    """
    ``tradeiq2_ind_swing.swing_profile`` of ``ctx.bars(tf)`` with the script's defaults (swing length 50, ATR(200),
    bins of 0.5 ATR) on the bid OHLC and PREREG 2's volume (``Context.volume``: gold tick volume, BTC Binance BTCUSDT
    spot volume, an hour without a kline 0), from the first bar the market holds; read-only, cached as (MODULE,
    symbol, tf, {'series': 'profile', 'volume': source}). Keys: the port's ``KEYS`` and the legs' columns as arrays
    ``leg_flip_bar``, ``leg_dir``, ``leg_poc``, ``leg_fifty``, ``leg_delta_pct``, ``leg_lo``, ``leg_hi``.
    """
    _check_tf(tf)
    src = _volume_source(ctx)

    def make():
        b = ctx.bars(tf)
        v = np.asarray(ctx.volume(tf), np.float64)
        return _pack(SP.swing_profile(b.o, b.h, b.l, b.c, v), len(b))
    return ctx.get(MODULE, tf, {"series": PROFILE_KEY, "volume": src}, make)


def use_profile(ctx: M.Context, tf: str, out: Mapping[str, object]) -> None:
    """Put ``out`` (a dict with exactly the port's ``KEYS``, one value per bar of ``ctx.bars(tf)``) in the Context's
    cache as the profile of ``tf`` (hand-made tests and diagnostics only). Refuses when one is already there."""
    _check_tf(tf)
    mine = _pack(out, len(ctx.bars(tf)))
    if ctx.get(MODULE, tf, {"series": PROFILE_KEY, "volume": _volume_source(ctx)}, lambda: mine) is not mine:
        raise ValueError(f"the {tf} profile of this Context is already computed (use a fresh Context)")


def active_leg(leg_flip_bar, n: int) -> np.ndarray:
    """Per bar t of ``n``: the row of the latest finished leg whose flip bar is at or before t (the "just-finished
    leg" of W3, known from its flip bar's close on); -1 before the first flip."""
    fb = np.asarray(leg_flip_bar, np.int64)
    return (np.searchsorted(fb, np.arange(n, dtype=np.int64), side="right") - 1).astype(np.int64)


def flip_exits(prof: Mapping[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    """(exit_long, exit_short) per bar: a flip to a new 50-bar low (``flip & ~is_down_move``, it finishes the up leg)
    is against a long; a flip to a new high (``flip & is_down_move``) against a short (W1, W2)."""
    fl = np.asarray(prof["flip"], bool)
    dn = np.asarray(prof["is_down_move"], bool)
    return fl & ~dn, fl & dn


# ───────────────────────────── the touch-and-hold bars ─────────────────────────────

def _level_series(prof: Mapping[str, np.ndarray], r: Rule, level: str, n: int, flip_bar: bool = False):
    """Per bar: the level a rule touches, the side it trades (+1 / -1 / 0), the anchor, the leg's delta and the row of
    the finished leg (W3; -1 for W1 / W2). W3's window is the bars AFTER the flip bar up to the next flip bar
    (reading R4); ``flip_bar=True`` also gives each flip bar its own just-finished leg (counts only)."""
    if r.leg == "forming":
        if level == "POC":
            P = np.asarray(prof["f_poc"], np.float64)
        else:
            P = (np.asarray(prof["f_lo"], np.float64) + np.asarray(prof["f_hi"], np.float64)) / 2.0
        d = np.asarray(prof["f_dir"]).astype(np.int64)
        anchor = np.where(d == 1, np.asarray(prof["ls_bar"], np.int64),
                          np.where(d == -1, np.asarray(prof["hs_bar"], np.int64), -1))
        delta = np.asarray(prof["f_delta_pct"], np.float64)
        return P, d, anchor, delta, np.full(n, -1, np.int64)
    fb = np.asarray(prof["leg_flip_bar"], np.int64)
    if len(fb) == 0:
        z = np.full(n, np.nan)
        return z, np.zeros(n, np.int64), np.full(n, -1, np.int64), z.copy(), np.full(n, -1, np.int64)
    k = active_leg(fb, n)
    kk = np.maximum(k, 0)
    has = (k >= 0) & (flip_bar | (fb[kk] < np.arange(n)))
    k = np.where(has, k, -1).astype(np.int64)
    lv = np.asarray(prof["leg_poc"] if level == "POC" else prof["leg_fifty"], np.float64)
    P = np.where(has, lv[kk], np.nan)
    d = np.where(has, -np.asarray(prof["leg_dir"], np.int64)[kk], 0).astype(np.int64)
    anchor = np.where(has, np.asarray(prof["leg_flip_bar"], np.int64)[kk], -1).astype(np.int64)
    delta = np.where(has, np.asarray(prof["leg_delta_pct"], np.float64)[kk], np.nan)
    return P, d, anchor, delta, k


def triggers(prof: Mapping[str, np.ndarray], h, l, c, atr, rule: str, level: str = "POC",
             flip_bar: bool = False) -> Dict[str, np.ndarray]:
    """
    Every touch-and-hold bar of ``rule`` on ``level`` (POC, or the placebo's L50) with its geometry, before the
    filter and the one-per-anchor rule, from a profile (``profile``'s keys) and the bars' high, low, close and
    ATR(14). Keys: ``bar``, ``side`` (+1 long / -1 short), ``anchor`` (W1 / W2: the bar of the stored swing low of an
    up leg / swing high of a down leg; W3: the finished leg's flip bar), ``leg`` (W3: the row of the finished leg;
    -1), ``level`` (the level touched), ``stop`` (W1: the leg's first swing point; W2 / W3: the level -/+ 1.5 ATR),
    ``target`` (W1: the leg's last swing point; NaN for the 2R rules), ``delta`` (the leg's delta, FD), ``atr`` and
    ``valid`` (the stop, W1's target and W2 / W3's ATR exist; W1's target lies beyond its stop). W3's bars are those
    after a flip bar up to the next flip bar (reading R4); ``flip_bar=True`` adds the flip bars themselves (counts
    only, never a rule). Plain arrays, so it can be checked on hand-made profiles.
    """
    r = _check(rule, level)
    h, l, c = (np.asarray(x, np.float64) for x in (h, l, c))
    atr = np.asarray(atr, np.float64)
    n = len(c)
    if not (len(h) == len(l) == len(atr) == n):
        raise ValueError("h, l, c and atr: one value per bar")
    P, d, anchor, delta, k = _level_series(prof, r, level, n, flip_bar)
    with np.errstate(invalid="ignore"):
        up = (d == 1) & (l <= P) & (c > P)
        dn = (d == -1) & (h >= P) & (c < P)
    bar = np.flatnonzero(up | dn).astype(np.int64)
    side = np.where(up[bar], 1, -1).astype(np.int64)
    lvl = P[bar]
    a = atr[bar]
    if r.stop == "swing":
        lp, hp = np.asarray(prof["ls_price"], np.float64)[bar], np.asarray(prof["hs_price"], np.float64)[bar]
        stop = np.where(side == 1, lp, hp)
        target = np.where(side == 1, hp, lp)
        with np.errstate(invalid="ignore"):
            valid = np.isfinite(stop) & np.isfinite(target) & (side * (target - stop) > 0)
    else:
        with np.errstate(invalid="ignore"):
            stop = lvl - side * STOP_ATR * a
            valid = np.isfinite(stop) & np.isfinite(a) & (a > 0)
        target = np.full(len(bar), np.nan)
    valid &= anchor[bar] >= 0
    return {"bar": bar, "side": side, "anchor": anchor[bar].astype(np.int64), "leg": k[bar].astype(np.int64),
            "level": lvl.astype(np.float64), "stop": np.asarray(stop, np.float64),
            "target": np.asarray(target, np.float64), "delta": delta[bar].astype(np.float64),
            "atr": a.astype(np.float64), "valid": np.asarray(valid, bool)}


def trigger_table(ctx: M.Context, tf: str, rule: str, level: str = "POC") -> Dict[str, np.ndarray]:
    """``triggers`` on ``ctx.bars(tf)`` with ``profile(ctx, tf)`` and ``ctx.atr(tf)`` (Pine ``ta.atr(14)``),
    read-only, cached."""
    _check_tf(tf)
    _check(rule, level)

    def make():
        b = ctx.bars(tf)
        t = triggers(profile(ctx, tf), b.h, b.l, b.c, ctx.atr(tf), rule, level)
        return {k: _ro(v) for k, v in t.items()}
    return ctx.get(MODULE, tf, {"series": "triggers", "rule": rule, "level": level, "volume": _volume_source(ctx)},
                   make)


def first_per_anchor(side, anchor) -> np.ndarray:
    """The positions (ascending) of the first row of each (side, anchor) in the given order: one candidate per swing
    anchor (reading R1). The rows are in time order."""
    side, anchor = np.asarray(side, np.int64), np.asarray(anchor, np.int64)
    if side.shape != anchor.shape:
        raise ValueError("side and anchor: one value per row")
    if len(side) == 0:
        return np.zeros(0, np.int64)
    _, first = np.unique(np.stack([side, anchor], axis=1), axis=0, return_index=True)
    return np.sort(first).astype(np.int64)


# ───────────────────────────── filters and exits ─────────────────────────────

def fd_allow(ctx: M.Context, tf: str, rule: str) -> Tuple[np.ndarray, np.ndarray]:
    """FD per bar (reading R6): (delta > 0, delta < 0) of the leg whose level the rule trades, the forming leg's
    ``f_delta_pct`` for W1 / W2 and the just-finished leg's ``delta_pct`` for W3; NaN allows neither. Read-only,
    cached."""
    r = _check(rule, "POC")

    def make():
        prof = profile(ctx, tf)
        n = len(ctx.bars(tf))
        delta = _level_series(prof, r, "POC", n)[3]
        with np.errstate(invalid="ignore"):
            return _ro(delta > 0.0), _ro(delta < 0.0)
    return ctx.get(MODULE, tf, {"series": "FD", "leg": r.leg, "volume": _volume_source(ctx)}, make)


def allow_of(ctx: M.Context, tf: str, rule: str, filt: str) -> Tuple[np.ndarray, np.ndarray]:
    """(allow_long, allow_short) per bar of a row's filter: FD from ``fd_allow``; F0, LO, F2-4H and F2-1D from
    ``Context.allow`` (``tradeiq2_filters``)."""
    allowed = ("F0", "FD", "LO", F2_OF[tf])
    if filt not in allowed:
        raise ValueError(f"{filt}: the filters of {tf} Swing Profile rows are {', '.join(allowed)} (PREREG 6.4)")
    if filt == "FD":
        return fd_allow(ctx, tf, rule)
    return ctx.allow(tf, filt)


def exits_of(ctx: M.Context, tf: str, rule: str) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """The per-bar exits of a rule: W1 and W2 exit at the close of a flip against the trade (``flip_exits``,
    read-only, cached); W3 has none (reading R5)."""
    r = _check(rule, "POC")
    if not r.flip_exit:
        return None, None

    def make():
        xl, xs = flip_exits(profile(ctx, tf))
        return _ro(xl), _ro(xs)
    return ctx.get(MODULE, tf, {"series": "flip_exits", "volume": _volume_source(ctx)}, make)


def rule_entries(ctx: M.Context, tf: str, rule: str, level: str = "POC", filt: str = "F0") -> M.Entries:
    """
    The market entries of one row: the valid touch-and-hold bars of ``rule`` on ``level`` (``trigger_table``) as
    entries (W1: ``stop_level`` and ``target_level``, the swing prices; W2 / W3: ``stop_level`` = level -/+ 1.5 ATR
    and ``target_r`` 2; ``tag`` = the anchor), gated by the filter at the decision close
    (``tradeiq2_filters.gate_entries`` on ``allow_of``), then the first of each anchor (``first_per_anchor``).
    """
    r = _check(rule, level)
    t = trigger_table(ctx, tf, rule, level)
    ok = np.flatnonzero(t["valid"])
    E = M.entries(t["bar"][ok], t["side"][ok], stop_level=t["stop"][ok],
                  target_level=t["target"][ok] if r.target == "swing" else None,
                  target_r=TARGET_R if r.target == "2R" else None, tag=t["anchor"][ok])
    E = F.gate_entries(E, *allow_of(ctx, tf, rule, filt))
    return E.take(first_per_anchor(E.side, E.tag))


def build(variant: M.Variant, ctx: M.Context) -> M.Exec:
    """The EVENTS Exec of one row of ``variants`` (looked up by its id): ``rule_entries`` with the row's level and
    filter, W1 / W2's flip exits (a long-only row has no short exits), one position at a time; label = the id."""
    s = spec_of(variant)
    if variant.symbol != ctx.symbol:
        raise ValueError(f"{variant.id}: not a variant of {ctx.symbol}")
    tf = variant.tf
    E = rule_entries(ctx, tf, s.rule.name, s.level, s.filter)
    xl, xs = exits_of(ctx, tf, s.rule.name)
    return M.event_exec(tf, entries=E, exit_long=xl, exit_short=None if s.filter == "LO" else xs, label=variant.id)


def warm(ctx: M.Context, variants_: Sequence[M.Variant]) -> None:
    """Compute in the parent, before the driver forks its workers, every array the given rows read: the profile, the
    ATR(14), the touch-and-hold tables, the filters (F2's higher bars, FD) and the flip exits."""
    for v in variants_:
        if v.symbol != ctx.symbol:
            continue
        s = spec_of(v)
        trigger_table(ctx, v.tf, s.rule.name, s.level)
        allow_of(ctx, v.tf, s.rule.name, s.filter)
        exits_of(ctx, v.tf, s.rule.name)


# ───────────────────────────── words and counts ─────────────────────────────

_TF_WORDS = {"1H": "1-hour", "4H": "4-hour"}
_RULE_WORDS = {
    "W1": ("while the forming leg is up (its stored swing high newer than its swing low), a bar whose low is at or "
           "below the leg's {lvl} and whose close is above it gives a long (shorts mirror it in a down leg); stop at "
           "the leg's swing low, target its swing high (shorts: the swing high, the swing low), the levels of the "
           "decision bar; exit at the close of a flip against the trade (a new 50-bar low for a long, a new high for "
           "a short), else the stop or the target"),
    "W2": ("as W1 (a touch and hold of the forming leg's {lvl}), with the stop at the {lvl} - 1.5 ATR(14) (shorts +) "
           "and the target at 2R; exit at the close of a flip against the trade, else the stop or the target"),
    "W3": ("after a flip, a touch and hold of the just-finished leg's {lvl} in the new direction (a long after a down "
           "leg, a short after an up leg) on the bars after the flip bar up to the next flip; stop at the {lvl} -/+ "
           "1.5 ATR(14), target 2R, no other exit"),
}
_LEVEL_WORDS = {"POC": "point of control (POC)", "L50": "50% level"}
_FILTER_WORDS = {
    "F0": "no filter",
    "FD": ("the leg's buy/sell delta on the trade's side (above 0 for a long, below 0 for a short; W1 / W2: the "
           "forming leg at the decision bar, W3: the just-finished leg)"),
    "F2-4H": "longs only while the last closed 4H bar is above its MA200, shorts only while below",
    "F2-1D": "longs only while the last closed 1D bar is above its MA200, shorts only while below",
    "LO": "long only",
}


def describe(variant: M.Variant) -> str:
    """The rule row in words (the driver's FINALISTS.md)."""
    s = spec_of(variant)
    vol = {"tick": "tick volume", "binance": "Binance BTCUSDT volume"}[VOLUME[variant.symbol]]
    lvl = _LEVEL_WORDS[s.level]
    anchor = ("one trade per finished leg" if s.rule.leg == "finished" else
              "one trade per swing anchor (the leg's swing low for longs, its swing high for shorts)")
    text = (f"Swing Profile [BigBeluga] (swing length 50, bins of 0.5 ATR(200)) on {_TF_WORDS[variant.tf]} bars of the "
            f"bid ({vol}), {s.rule.name}: {_RULE_WORDS[s.rule.name].format(lvl=lvl)}; the first such bar of each "
            f"anchor that the filter allows, {anchor}; filled at the next M1 open, stop and target as distances from "
            f"the fill; filter: {_FILTER_WORDS[s.filter]}, checked at the entry's close; one position at a time")
    if s.placebo:
        text += "; placebo row (the 50% level in place of the POC), not eligible"
    return text


def _span(ctx: M.Context, window) -> Tuple[int, int]:
    """(start in s, the M1 index of the end) of a window: a name of ``tradeiq2_market.WINDOWS`` or a (start, end)
    pair (tests)."""
    a, z = M.window_span(window, ctx.symbol) if isinstance(window, str) else (str(window[0]), str(window[1]))
    return M.s_of(a), int(np.searchsorted(ctx.mk.t, M.s_of(z), side="left"))


def _candidates(t: Mapping[str, np.ndarray], al: np.ndarray, ash: np.ndarray) -> np.ndarray:
    """A mask over a trigger table: its valid bars the filter allows, the first of each anchor (as ``rule_entries``)."""
    ok = t["valid"] & np.where(t["side"] == 1, al[t["bar"]], ash[t["bar"]])
    idx = np.flatnonzero(ok)[first_per_anchor(t["side"][ok], t["anchor"][ok])]
    cand = np.zeros(len(t["bar"]), bool)
    cand[idx] = True
    return cand


def event_counts(ctx: M.Context, window="dev") -> pd.DataFrame:
    """
    Per row of ``variants(ctx.symbol)``: the touch-and-hold bars decided in ``window`` (a bar closing after its start
    and filled before its end; long / short), the anchors they belong to, those the filter allows, the candidates
    (the first allowed bar of each anchor, over the whole series, inside the window; long / short), the candidates
    with the script's flag already against the trade (reading R3) and on a flip bar, (W3) those on a leg whose flip
    bar's close had not passed the level yet (reading R4) and the candidates W3 would have on the flip bar itself if
    its window began there (``n_w3_flip_bar_alt``, reading R4), and the median stop distance from the decision close
    in ATR(14). Counts and geometry only (no profit or loss).
    """
    a_s, iz = _span(ctx, window)
    rows = []
    for v in variants(ctx.symbol):
        s = spec_of(v)
        tf = v.tf
        b = ctx.bars(tf)
        prof = profile(ctx, tf)
        t = trigger_table(ctx, tf, s.rule.name, s.level)
        inw = (b.tc[t["bar"]] > a_s) & (b.ex[t["bar"]] < iz)
        al, ash = allow_of(ctx, tf, s.rule.name, s.filter)
        ok = t["valid"] & np.where(t["side"] == 1, al[t["bar"]], ash[t["bar"]])
        cw = _candidates(t, al, ash) & inw
        bars = t["bar"][cw]
        side = t["side"][cw]
        dn = np.asarray(prof["is_down_move"], bool)[bars]
        against = ((side == 1) & ~dn) | ((side == -1) & dn)
        on_flip = np.asarray(prof["flip"], bool)[bars]
        not_past = np.zeros(len(bars), bool)
        alt_flip = 0
        if s.rule.leg == "finished":
            if len(bars):
                fb = t["anchor"][cw]
                not_past = side * (b.c[fb] - t["level"][cw]) <= 0
            u = triggers(prof, b.h, b.l, b.c, ctx.atr(tf), s.rule.name, s.level, flip_bar=True)
            uw = _candidates(u, al, ash) & (b.tc[u["bar"]] > a_s) & (b.ex[u["bar"]] < iz)
            alt_flip = int((uw & (u["bar"] == u["anchor"])).sum())
        with np.errstate(invalid="ignore", divide="ignore"):
            dist = side * (b.c[bars] - t["stop"][cw]) / t["atr"][cw] if len(bars) else np.zeros(0)
        tw = t["valid"] & inw
        rows.append({"symbol": ctx.symbol, "tf": tf, "vid": v.id, "rule": s.rule.name, "level": s.level,
                     "filter": s.filter, "window": window if isinstance(window, str) else f"{window[0]}..{window[1]}",
                     "touch_bars": int(tw.sum()), "touch_long": int((tw & (t["side"] == 1)).sum()),
                     "touch_short": int((tw & (t["side"] == -1)).sum()),
                     "anchors": int(len(np.unique(np.stack([t["side"][tw], t["anchor"][tw]], 1), axis=0)))
                     if tw.any() else 0,
                     "allowed_bars": int((ok & inw).sum()), "candidates": int(cw.sum()),
                     "cand_long": int((side == 1).sum()), "cand_short": int((side == -1).sum()),
                     "n_flag_against": int(against.sum()), "n_on_flip_bar": int(on_flip.sum()),
                     "n_not_past_at_flip": int(not_past.sum()), "n_w3_flip_bar_alt": alt_flip,
                     "median_stop_atr": float(np.median(dist)) if len(dist) else np.nan})
    return pd.DataFrame(rows)
