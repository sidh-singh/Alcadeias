"""
Ladder study: the runner the search steps call (PREREG_LADDER.md sections 2-4).

* ``BASES`` / ``LEVELS``  the frozen search space of section 2.2 (bases L0, L5, LB, V3L, ref V3; 19 dimensions,
                          120 alternatives). ``build(symbol, base, {dim: code, ...})`` turns a choice into a
                          ``LadderConfig`` override dict, or None when the level does not apply / equals the base.
* windows                 R1 / R2 quarters, R3 one-year accounts, the R4 fold accounts, the 23-quarter anchor,
                          the continuous accounts (section 3).
* ``run``                 every (design, window, seed) of a rung on fresh $2,000 accounts: one prepare per window,
                          shared by fork workers; rows appended to a CSV (resumable). ``per_unit`` runs the
                          fixed-unit, $1e9 account and keeps the daily P/L (section 5.4).
* ``score``               the rung score (key 1 wiped accounts, key 2 Q = mean(r) / max(max(d), 5), ties mean r).
* stage helpers           ``stage_a``, ``owner_grid``, ``factorial``, ``neighbours`` (RNG seed 20261118).

usage:
  python -m backtesting.research.ladder_study levels                      write levels.json / LEVELS.md
  python -m backtesting.research.ladder_study stageA SYMBOL OUT.json      the stage-A design list (with the skip log)
  python -m backtesting.research.ladder_study run SYMBOL DESIGNS.json RUNG OUT.csv [jobs] [mode] [spread_mult]
        RUNG: R1 | R2 | R3 | anchor | 8y | 5y | 1y | F1..F4 (the fold's 12 accounts) | a window "START:END"
  python -m backtesting.research.ladder_study unit SYMBOL DESIGNS.json START END OUT_DIR [jobs]
"""

from __future__ import annotations

import copy
import json
import math
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import ladder_tfs as LT  # noqa: F401  (registers the new timeframes)
from . import ladder_engine as LE
from . import ladder_ind as LI
from ..config import FIBO, REPO_ROOT, TF_SECONDS
from ..analysis.robustness import live_timing

SEED = 20261118
SYMBOLS = ("XAUUSDm", "BTCUSDm")
OUT = REPO_ROOT / "backtest_results" / "ladder"
ROUND4 = REPO_ROOT / "backtest_results" / "improve" / "round4"
ACCOUNT = 2000.0
WIPE_EQUITY = 200.0            # wiped: stopped out, or equity ever at or below $200 (-90%)
V = dict(vol_tf="H1", vol_len=24)

# ───────────────────────────── windows (section 3) ─────────────────────────────

FOLDS = {"F1": ("2018-11-13", "2020-11-13"), "F2": ("2020-11-13", "2022-11-13"),
         "F3": ("2022-11-13", "2024-11-13"), "F4": ("2024-11-13", "2026-11-13")}


def _add_months(day: str, m: int) -> str:
    return (pd.Timestamp(day) + pd.DateOffset(months=m)).strftime("%Y-%m-%d")


R2_QUARTERS = [(_add_months("2018-11-13", 3 * k), _add_months("2018-11-13", 3 * k + 3)) for k in range(24)]
R1_QUARTERS = [(a, _add_months(a, 3)) for a in ("2018-11-13", "2019-08-13", "2020-05-13", "2021-02-13", "2021-11-13",
                                                "2022-08-13", "2023-05-13", "2024-02-13",
                                                "2020-02-13", "2021-05-13", "2022-05-13")]   # 8 regular + 3 stress
R3_YEARS = [(_add_months("2018-11-13", 3 * k), _add_months("2018-11-13", 3 * k + 12)) for k in range(21)]
CONTINUOUS = {"8y": ("2018-11-13", "2026-11-13"), "5y": ("2021-11-13", "2026-11-13"), "1y": ("2025-11-13", "2026-11-13")}
SCREEN_SPAN = ("2018-11-13", "2024-11-13")     # F1-F3: the per-unit run of R3
SEEDS_SCREEN = (1, 2)
SEEDS_ALL = (1, 2, 3, 4, 5, 6, 7, 8)


def fold_accounts(fold: str) -> List[Tuple[str, str]]:
    """The 12 fresh accounts of a fold: from the 13th of each of its first 12 months, 12 months each."""
    a = FOLDS[fold][0]
    return [(_add_months(a, k), _add_months(a, k + 12)) for k in range(12)]


def anchor_quarters() -> List[Tuple[str, str]]:
    d = pd.read_csv(ROUND4 / "top3_v4_holdout_XAUUSDm.csv")
    e = pd.read_csv(ROUND4 / "top3_v4_dev_XAUUSDm.csv")
    segs = list(dict.fromkeys(list(d["segment"]) + list(e["segment"])))
    return [tuple(s.strip() for s in seg.split("→")) for seg in segs]


def rung_windows(rung: str) -> List[Tuple[str, str]]:
    if rung == "R1":
        return list(R1_QUARTERS)
    if rung == "R2":
        return list(R2_QUARTERS)
    if rung == "R3":
        return list(R3_YEARS)
    if rung == "anchor":
        return anchor_quarters()
    if rung in CONTINUOUS:
        return [CONTINUOUS[rung]]
    if rung in FOLDS:
        return fold_accounts(rung)
    if ":" in rung:
        a, z = rung.split(":")
        return [(a, z)]
    raise ValueError(f"unknown rung {rung!r}")


# ───────────────────────────── bases (section 2.1) ─────────────────────────────

def _round4(name: str) -> dict:
    raw = json.loads((ROUND4 / "top3_v4_XAUUSDm_designs.json").read_text())
    return copy.deepcopy(next(v for k, v in raw.items() if k.split(":")[0].strip() == name))


BASES: Dict[str, dict] = {
    "L0": {},
    "L5": dict(ladder_multipliers=[1.0] * 6, fc_weights={"H4": 1}, agree_weights={"M15": 1}),
    "LB": dict(max_adds=3, ladder_gap_vol=1.0, stop_vol=8.0, max_hold_s=259200.0, trend_tf="H1", trend_mode=1, **V),
    "V3L": _round4("Top 1"),        # gold Top 1, run on both symbols
    "V3": _round4("V3-lite"),       # reference only: not a base for ladder dimensions
}
LADDER_BASES = ("L0", "L5", "LB", "V3L")

# ───────────────────────────── the level table (section 2.2), frozen ─────────────────────────────


def _shape(head: List[float]) -> List[float]:
    return [float(x) for x in head] + [float(head[-1])] * (64 - len(head))


SHAPES = {"flat": _shape([1.0]), "plus1": _shape(list(range(1, 14))), "double": _shape([2.0 ** i for i in range(13)]),
          "fibo": _shape(FIBO)}
LIVE_TIERS = ["M1", "M5", "M15", "H1", "H4"]
TIER_LISTS = {
    "T0": LIVE_TIERS,
    "T1": ["M5", "M15", "H1"], "T2": ["M1", "M5", "M15"], "T3": ["M5", "M15", "H1", "H4", "D1"],
    "T4": ["M15", "H1", "H4", "D1", "W1"], "T5": LIVE_TIERS + ["D1"], "T6": LIVE_TIERS + ["D1", "W1"],
    "T7": ["H1", "H4", "D1"], "T8": ["M5"] * 5, "T9": ["M15"] * 5, "T10": ["H1"] * 5, "T11": ["H4"] * 5,
    "T12": ["M2", "M4", "M6", "M10", "M20"], "T13": ["M10", "M20", "H2", "H3", "H6"], "T14": ["M30", "H2", "H3", "H6", "H8", "H12"],
    "T15": ["M1", "M3", "M5", "M10", "M15", "M30", "H1", "H2", "H4"], "T16": ["M6", "M12", "M20", "H3", "H8"],
}
TRIG3 = {
    "stoch": {"ind": "stoch", "n": 14, "smooth": 3, "lo": 20, "hi": 80},
    "willr": {"ind": "willr", "n": 14, "lo": -80, "hi": -20},
    "cci": {"ind": "cci", "n": 20, "lo": -100, "hi": 100},
    "bb": {"ind": "bb", "n": 20, "k": 2.0, "lo": 0.0, "hi": 1.0},
    "emadist": {"ind": "emadist", "n": 20, "atr": 14, "lo": -2.0, "hi": 2.0},
    "rsi2": {"ind": "rsi", "n": 2, "lo": 10, "hi": 90},
}
FRI_FLAT = [4 * 1440 + 20 * 60, 60]           # Friday 20:00 UTC to Monday 01:00 UTC (minutes of the week)


def _with_vol(ov: dict) -> dict:
    if not ov.get("vol_tf"):
        ov.update(V)
    return ov


def _has_gap(ov: dict) -> bool:
    return float(ov.get("ladder_gap_vol", 0) or 0) > 0 or float(ov.get("ladder_min_gap", 0) or 0) > 0 or bool(ov.get("gap_vol_tf"))


def _trigger_of(ov: dict) -> str:
    return ov.get("ladder_trigger_x") or ov.get("ladder_trigger", "rsi_level")


def _rsi_trigger(ov: dict) -> bool:
    return _trigger_of(ov) in ("rsi_level", "rsi_cross", "rsi_macd")


def _depth(ov: dict) -> int:
    return min(len(ov.get("ladder_tfs", LIVE_TIERS)), int(ov.get("max_adds", 99)))


def _set(**kw) -> Callable[[dict], Optional[dict]]:
    return lambda ov: {**ov, **copy.deepcopy(kw)}


def _tiers(name: str):
    def f(ov):
        return {**ov, "ladder_tfs": list(TIER_LISTS[name])}
    return f


def _depth_level(d: int):
    def f(ov):
        tfs = list(ov.get("ladder_tfs", LIVE_TIERS))
        tfs = tfs + [tfs[-1]] * max(0, d - len(tfs))
        return {**ov, "ladder_tfs": tfs, "max_adds": d}
    return f


def _rsi_levels(os_: float, ob: float):
    def f(ov):
        if not _rsi_trigger(ov):
            return None
        o = {k: v for k, v in ov.items() if k not in ("tier_os", "tier_ob")}
        return {**o, "rsi_oversold": float(os_), "rsi_overbought": float(ob)}
    return f


def _tier_rule(step: float):
    def f(ov):
        if not _rsi_trigger(ov):
            return None
        os_ = [min(max(35.0 + step * q, 0.0), 50.0) for q in range(64)]      # capped at the midline (BUILD.md)
        return {**ov, "rsi_oversold": 35.0, "rsi_overbought": 65.0, "tier_os": os_, "tier_ob": [100.0 - x for x in os_]}
    return f


def _trig_x(kind: str, spec: Optional[dict] = None):
    def f(ov):
        o = {k: v for k, v in ov.items() if k not in ("ladder_trigger_x", "trigger_spec")}
        o["ladder_trigger_x"] = kind
        if spec is not None:
            o["trigger_spec"] = copy.deepcopy(spec)
        return o
    return f


def _trig(kind: str, **kw):
    def f(ov):
        o = {k: v for k, v in ov.items() if k not in ("ladder_trigger_x", "trigger_spec")}
        o.update(ladder_trigger=kind, **kw)
        if kind == "price_step" and not _has_gap(o):
            _with_vol(o)
            o["ladder_gap_vol"] = 1.0
        return o
    return f


def _gap_vol(m: float, growth: float = 1.0):
    def f(ov):
        o = {k: v for k, v in ov.items() if k not in ("gap_vol_tf", "gap_vol_len", "gap_vol_mult")}
        return _with_vol({**o, "ladder_gap_vol": float(m), "gap_growth": float(growth)})
    return f


def _gap_d1(ov):
    return {**ov, "ladder_gap_vol": 0.0, "ladder_min_gap": 0.0, "gap_vol_tf": "D1", "gap_vol_len": 14, "gap_vol_mult": 0.15}


def _stop_vol(m: float):
    def f(ov):
        return _with_vol({**ov, "stop_vol": float(m), "stop_loss_usd_per_unit": None, "stop_pct_balance": 0.0})
    return f


def _stop_pct(p: float):
    def f(ov):
        return {**ov, "stop_vol": 0.0, "stop_loss_usd_per_unit": None, "stop_pct_balance": float(p)}
    return f


def _target_usd(x: float):
    def f(ov):
        return {**ov, "target_usd_per_unit": float(x), "target_vol": 0.0}
    return f


def _target_vol(x: float):
    def f(ov):
        return _with_vol({**ov, "target_vol": float(x)})
    return f


def _deep_only(field: str, **kw):
    def f(ov):
        if _depth(ov) < 3:
            return None                             # never acts on a ladder of fewer than 3 adds
        return {**ov, **kw}
    return f


def _fc(weights: Optional[dict]):
    """Force-close on another timeframe (or off); the entry agreement keeps the base's source."""
    def f(ov):
        base_fc = ov.get("fc_weights", {"M15": 1})
        o = dict(ov)
        if "agree_weights" not in o or o["agree_weights"] is None:
            o["agree_weights"] = copy.deepcopy(base_fc)
        if weights is None:
            o["force_close_enabled"] = False
        else:
            o.update(force_close_enabled=True, fc_weights=copy.deepcopy(weights))
        return o
    return f


def _fc_rsi(ov):
    o = dict(ov)
    if o.get("force_close_enabled", True) is False:
        # only the RSI rule: a score force-close the base did not have is not switched on with it
        o.update(force_close_enabled=True, fc_weights={}, agree_weights=copy.deepcopy(ov.get("agree_weights") or ov.get("fc_weights", {"M15": 1})))
    o["fc_rsi_tfs"] = ["H1", "H4"]
    return o


def _entry(**kw):
    def f(ov):
        o = dict(ov)
        if "fc_weights" in kw and ("agree_weights" not in o or o["agree_weights"] is None) and kw.get("entry_agree_s", 1) != 0:
            o["agree_weights"] = {"M15": 1}
        o.update(copy.deepcopy(kw))
        return o
    return f


def _gate_entry(spec: dict):
    def f(ov):
        return {**ov, "entry_gate": list(ov.get("entry_gate") or []) + [copy.deepcopy(spec)]}
    return f


def _gate_add(spec: dict):
    def f(ov):
        return {**ov, "add_gate": list(ov.get("add_gate") or []) + [copy.deepcopy(spec)]}
    return f


def _confirm_d1_trend(ov):
    if ov.get("trend_tf"):
        return _gate_entry({"kind": "macd_trend", "tf": "D1"})(ov)   # keeps the base's own trend filter (BUILD.md)
    return {**ov, "trend_tf": "D1", "trend_mode": 1}


def _counter(ov):
    o = {**ov, "hedge_mode": "counter"}
    if not _has_gap(o):
        _with_vol(o)
        o["ladder_gap_vol"] = 1.0
    return o


def _anti_martingale(ov):
    o = {k: v for k, v in ov.items() if k not in ("ladder_trigger_x", "trigger_spec", "gap_vol_tf", "gap_vol_len", "gap_vol_mult")}
    o = _with_vol(o)
    o.update(ladder_trigger="profit_step", ladder_gap_vol=0.5, max_adds=3, ladder_multipliers=SHAPES["flat"],
             trail_gap_vol=2.0, trail_start_vol=0.0, target_usd_per_unit=None, target_vol=0.0)
    return o


def _sizing_vt(ov, symbol=None):
    return {**ov, "sizing": "voltarget", "vt_k": None}       # vt_k filled in by build() per symbol


# (dimension, code, what, transform). Application order of dimensions in a combination = the order below.
LEVELS: List[Tuple[str, str, str, Callable]] = [
    ("ENTRY", "E1", "{H4,M5}, v3.9.2 force-close and agreement", _entry(open_weights={"H4": 1, "M5": 1})),
    ("ENTRY", "E2", "pre-v3.9.0: {H4,M5}, fc {M15:4,H1:3,H4:2,D1:1}, force_close_s 12, entry_agree_s 0",
     _entry(open_weights={"H4": 1, "M5": 1}, fc_weights={"M15": 4, "H1": 3, "H4": 2, "D1": 1}, force_close_s=12.0, entry_agree_s=0.0)),
    ("ENTRY", "E3", "{H1,M15,D1}, entry_s 2", _entry(open_weights={"H1": 1, "M15": 1, "D1": 1}, entry_s=2.0)),
    ("ENTRY", "E4", "{H1,M15,D1}, entry_s 4", _entry(open_weights={"H1": 1, "M15": 1, "D1": 1}, entry_s=4.0)),
    ("ENTRY", "E5", "{H4,M5,D1}, entry_s 2", _entry(open_weights={"H4": 1, "M5": 1, "D1": 1}, entry_s=2.0)),
    ("ENTRY", "E6", "{H4,M5,D1}, entry_s 4", _entry(open_weights={"H4": 1, "M5": 1, "D1": 1}, entry_s=4.0)),
    ("ENTRY", "E7", "{H1} alone", _entry(open_weights={"H1": 1}, entry_s=2.0)),
    ("ENTRY", "E8", "{H4,H1,M15}, entry_s 4", _entry(open_weights={"H4": 1, "H1": 1, "M15": 1}, entry_s=4.0)),
    ("ENTRY", "E9", "RSI-only votes {H1,M15}", _entry(open_weights={"H1": [1, 0], "M15": [1, 0]})),
    ("ENTRY", "E10", "entry_agree_s 0", _entry(entry_agree_s=0.0)),
    ("CONFIRM", "C1", "EMA200(D1) side", _gate_entry({"kind": "ema_side", "tf": "D1", "n": 200})),
    ("CONFIRM", "C2", "EMA50(H4) side", _gate_entry({"kind": "ema_side", "tf": "H4", "n": 50})),
    ("CONFIRM", "C3", "Supertrend(10,3) H4 side", _gate_entry({"kind": "supertrend", "tf": "H4", "n": 10, "mult": 3.0})),
    ("CONFIRM", "C4", "ADX(14,H4) < 25", _gate_entry({"kind": "adx_below", "tf": "H4", "n": 14, "thr": 25.0})),
    ("CONFIRM", "C5", "ADX(14,H4) >= 25: +DI/-DI side only", _gate_entry({"kind": "adx_di", "tf": "H4", "n": 14, "thr": 25.0})),
    ("CONFIRM", "C6", "Stochastic(14,3,3) H1 <= 30 buys / >= 70 sells",
     _gate_entry({"kind": "zone", "tf": "H1", "ind": {"ind": "stoch", "n": 14, "smooth": 3, "lo": 30, "hi": 70}})),
    ("CONFIRM", "C7", "CCI(20) H1 <= -100 buys / >= 100 sells",
     _gate_entry({"kind": "zone", "tf": "H1", "ind": {"ind": "cci", "n": 20, "lo": -100, "hi": 100}})),
    ("CONFIRM", "C8", "Bollinger %B(20,2) H1 <= 0.2 buys / >= 0.8 sells",
     _gate_entry({"kind": "zone", "tf": "H1", "ind": {"ind": "bb", "n": 20, "k": 2.0, "lo": 0.2, "hi": 0.8}})),
    ("CONFIRM", "C9", "Donchian(20) H4 breakout side", _gate_entry({"kind": "donchian", "tf": "H4", "n": 20})),
    ("CONFIRM", "C10", "variance ratio VR(4) < 1 on 100 H1 bars", _gate_entry({"kind": "vr_below", "tf": "H1", "q": 4, "n": 100, "thr": 1.0})),
    ("CONFIRM", "C11", "D1 MACD-signal trend", _confirm_d1_trend),
    ("SIDE", "S1", "entries with the H4 trend", _set(trend_tf="H4", trend_mode=1)),
    ("SIDE", "S2", "entries against the H4 trend", _set(trend_tf="H4", trend_mode=-1)),
    ("SIDE", "S3", "entries with the D1 trend", _set(trend_tf="D1", trend_mode=1)),
    ("SIDE", "S4", "entries against the D1 trend", _set(trend_tf="D1", trend_mode=-1)),
    ("SIDE", "S5", "D1 RSI reversal (>= 70 sells only, <= 30 buys only)", _set(side_rsi_tf="D1", side_rsi_hi=70.0, side_rsi_lo=30.0)),
    ("SIDE", "S6", "stop-and-reverse at the stop / force-close, same size", _set(reverse=True, reverse_mult=1.0)),
    ("SIDE", "S7", "stop-and-reverse, entry size x 2", _set(reverse=True, reverse_mult=2.0)),
    ("SIDE", "S8", "hedge-on-depth", _set(hedge_mode="depth", hedge_stop_mult=2.0)),
    ("SIDE", "S9", "counter-ladder", _counter),
    ("FC", "FC1", "force-close {H1:1}", _fc({"H1": 1})),
    ("FC", "FC2", "force-close {H4:1}", _fc({"H4": 1})),
    ("FC", "FC3", "force-close {D1:1}", _fc({"D1": 1})),
    ("FC", "FC4", "force-close off", _fc(None)),
    ("FC", "FC5", "owner's RSI force-close (H1 and H4)", _fc_rsi),
    ("FC", "FC6", "H6 RSI final close when the ladder is full", _set(final_close_tf="H6")),
    ("TARGET", "TG1", "$0.5 per unit", _target_usd(0.5)),
    ("TARGET", "TG2", "$2 per unit", _target_usd(2.0)),
    ("TARGET", "TG3", "$5 per unit", _target_usd(5.0)),
    ("TARGET", "TG4", "$10 per unit", _target_usd(10.0)),
    ("TARGET", "TG5", "target 2 vol units", _target_vol(2.0)),
    ("TARGET", "TG6", "target 4 vol units", _target_vol(4.0)),
    ("TARGET", "TG7", "target 8 vol units", _target_vol(8.0)),
    ("TARGET", "TG8", "break-even + one spread once depth >= 3", _deep_only("be", be_after_adds=3, be_spreads=1.0)),
    ("TARGET", "TG9", "target_0 / positions (never below one spread)", _set(target_shrink=True)),
    ("STOP", "ST1", "stop 4 vol units", _stop_vol(4.0)),
    ("STOP", "ST2", "stop 8 vol units", _stop_vol(8.0)),
    ("STOP", "ST3", "stop 12 vol units", _stop_vol(12.0)),
    ("STOP", "ST4", "basket stop 10% of the balance", _stop_pct(10.0)),
    ("STOP", "ST5", "basket stop 20% of the balance", _stop_pct(20.0)),
    ("STOP", "ST6", "basket stop 30% of the balance", _stop_pct(30.0)),
    ("TIME", "TM1", "time stop 24 h", _set(max_hold_s=86400.0, max_hold_min_adds=0)),
    ("TIME", "TM2", "time stop 72 h", _set(max_hold_s=259200.0, max_hold_min_adds=0)),
    ("TIME", "TM3", "time stop 168 h", _set(max_hold_s=604800.0, max_hold_min_adds=0)),
    ("TIME", "TM4", "time stop 24 h once depth >= 3", _deep_only("time", max_hold_s=86400.0, max_hold_min_adds=3)),
    *[("TIERS", t, f"tiers {t} {TIER_LISTS[t]}", _tiers(t)) for t in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11")],
    *[("GRAN", t, f"tiers {t} {TIER_LISTS[t]}", _tiers(t)) for t in ("T12", "T13", "T14", "T15", "T16")],
    *[("DEPTH", f"D{d}", f"max_adds {d}", _depth_level(d)) for d in (1, 2, 3, 5, 8, 12)],
    *[("SIZE", s, f"size {s}", _set(ladder_multipliers=SHAPES[s])) for s in ("flat", "plus1", "double", "fibo")],
    ("LEVEL", "LV20", "RSI 20/80", _rsi_levels(20, 80)), ("LEVEL", "LV25", "RSI 25/75", _rsi_levels(25, 75)),
    ("LEVEL", "LV30", "RSI 30/70", _rsi_levels(30, 70)), ("LEVEL", "LV40", "RSI 40/60", _rsi_levels(40, 60)),
    ("LEVEL", "LV45", "RSI 45/55", _rsi_levels(45, 55)),
    ("LEVEL", "LVS", "per tier stricter when deeper (35, 32, 29, ...)", _tier_rule(-3.0)),
    ("LEVEL", "LVL", "per tier looser when deeper (35, 38, 41, ...)", _tier_rule(3.0)),
    ("TRIG-MACD", "M1", "MACD turn (macd_turn)", _trig("macd_turn")),
    ("TRIG-MACD", "M2", "MACD histogram on the wrong side, forming bar", _trig_x("macd_hist")),
    ("TRIG-MACD", "M3", "MACD signal-line cross back, forming bar", _trig_x("macd_cross")),
    ("TRIG-MACD", "M4", "RSI level and MACD turn (wait for the turn)", _trig_x("rsi_macd")),
    *[("TRIG-3RD", f"X-{k}", f"closed-bar {k} {v}", _trig_x("series", v)) for k, v in TRIG3.items()],
    ("TRIG-3RD", "X-rsicross", "RSI cross-back (rsi_cross)", _trig("rsi_cross")),
    ("TRIG-3RD", "X-pricestep", "price step 1 vol unit (price_step)", _trig("price_step")),
    ("GAP", "G0.5", "gap 0.5 vol units", _gap_vol(0.5)), ("GAP", "G1", "gap 1 vol unit", _gap_vol(1.0)),
    ("GAP", "G2", "gap 2 vol units", _gap_vol(2.0)),
    ("GAP", "Ggeo1.5", "gap 1 vol unit x 1.5^(n-1)", _gap_vol(1.0, 1.5)), ("GAP", "Ggeo2", "gap 1 vol unit x 2^(n-1)", _gap_vol(1.0, 2.0)),
    ("GAP", "GD1", "gap 0.15 D1 vol units (vol_len 14)", _gap_d1),
    ("GAP", "Gint300", "300 s between fills", _set(ladder_min_interval_s=300.0)),
    ("GATE", "GT1", "ladder_s off", _set(ladder_s=1e9)),
    ("GATE", "GT2", "adds only with the H1 trend", _set(add_trend_tf="H1", add_trend_mode=1)),
    ("GATE", "GT3", "adds only with the H4 trend", _set(add_trend_tf="H4", add_trend_mode=1)),
    ("GATE", "GT4", "adds only on the EMA200(D1) side", _gate_add({"kind": "ema_side", "tf": "D1", "n": 200})),
    ("GATE", "GT5", "no adds while ADX(14,H1) > 30", _gate_add({"kind": "adx_above_block", "tf": "H1", "n": 14, "thr": 30.0})),
    ("GATE", "GT6", "abnormal-day pause for adds", _set(abnormal_day={"mult": 2.0, "days": 20})),
    ("GATE", "GT7", "no adds 20:30-22:30 UTC", _set(add_block_utc=[1230, 1350])),
    ("GATE", "GT8", "flat Friday 20:00 UTC, no new basket until Monday 01:00", _set(flat_week=FRI_FLAT)),
    ("GATE", "GT9", "no new basket while ATR(H4) > its 100-day 90th percentile",
     _gate_entry({"kind": "atr_pct_block", "tf": "H4", "n": 14, "days": 100, "q": 0.9})),
    ("SIZING", "Z1", "pre-funded unit (30% of the balance, 1.5 ATR(D1))", _set(sizing="prefund", pf_risk=0.30, pf_atr_mult=1.5)),
    ("SIZING", "Z2", "volatility-targeted unit", _sizing_vt),
    ("SIZING", "Z3", "fixed_units 1", _set(fixed_units=1)),
    ("PARTIAL", "P1", "LIFO: close the newest add at its own target", _set(partial="lifo")),
    ("PARTIAL", "P2", "overlap close (newest pays for oldest)", _set(partial="overlap")),
    ("CONTROL", "AM", "anti-martingale: adds to winners 0.5 vol units, <= 3, 2 vol-unit trailing exit", _anti_martingale),
]
DIMENSIONS = list(dict.fromkeys(d for d, *_ in LEVELS))
LEVEL_BY_KEY = {(d, c): (w, f) for d, c, w, f in LEVELS}
assert len(LEVELS) == len(LEVEL_BY_KEY)


def vt_k(symbol: str, live_median_unit: float = 1.0) -> float:
    """k of the volatility-targeted unit: the median unit over F1-F3 at $2,000 equals the live rule's median (1)."""
    b = LI.bars(symbol, "D1")
    at = LI.X.wilder_atr(b["h"], b["l"], b["c"], 14)
    a, z = (pd.Timestamp(x).timestamp() for x in SCREEN_SPAN)
    sel = (b["t"] >= a) & (b["t"] < z)
    contract = LE.live_config(symbol).spec.contract_size
    return float(live_median_unit * np.nanmedian(at[sel]) * contract / ACCOUNT)


def canonical(symbol: str, ov: dict) -> str:
    """What a design does (effective ladder only), to drop alternatives that equal their base."""
    cfg = LE.live_config(symbol).replace(**ov)
    d = cfg.to_dict()
    n = cfg.n_ladder_adds
    d["ladder_tfs"] = list(cfg.ladder_tfs[:n])
    m = list(cfg.ladder_multipliers) + [cfg.ladder_multipliers[-1]] * 64
    d["ladder_multipliers"] = [float(x) for x in m[:n + 1]]
    d["max_adds"] = n
    for k in ("start", "end"):
        d.pop(k, None)
    return json.dumps(d, sort_keys=True, default=str)


def build(symbol: str, base: str, choice: Dict[str, str]) -> Tuple[Optional[dict], str]:
    """Overrides of the live config for ``base`` + one level per dimension in ``choice``; (None, why) when it cannot run."""
    ov = copy.deepcopy(BASES[base])
    for dim in DIMENSIONS:
        if dim not in choice:
            continue
        what, fn = LEVEL_BY_KEY[(dim, choice[dim])]
        nxt = fn(ov)
        if nxt is None:
            return None, f"{dim}={choice[dim]} does not apply to {base}"
        ov = nxt
    if ov.get("sizing") == "voltarget" and not ov.get("vt_k"):
        ov["vt_k"] = vt_k(symbol)
    try:
        LE.live_config(symbol).replace(**ov)
    except (ValueError, TypeError) as e:
        return None, f"invalid: {e}"
    return ov, ""


def design_name(base: str, choice: Dict[str, str]) -> str:
    return "|".join([base] + [f"{d}={choice[d]}" for d in DIMENSIONS if d in choice])


def stage_a(symbol: str) -> Tuple[List[dict], List[dict]]:
    """The bases, ref V3, and one dimension at a time around each ladder base. Returns (designs, skip log)."""
    designs, skips, seen = [], [], {}
    for b in LADDER_BASES + ("V3",):
        designs.append({"name": b, "base": b, "choice": {}, "overrides": copy.deepcopy(BASES[b])})
        seen[canonical(symbol, BASES[b])] = b
    for b in LADDER_BASES:
        for dim, code, what, _ in LEVELS:
            ov, why = build(symbol, b, {dim: code})
            name = design_name(b, {dim: code})
            if ov is None:
                skips.append({"name": name, "why": why})
                continue
            key = canonical(symbol, ov)
            if key in seen:
                same = seen[key]
                skips.append({"name": name, "why": "equals the base" if same == b else f"same as {same}"})
                continue
            seen[key] = name
            designs.append({"name": name, "base": b, "choice": {dim: code}, "overrides": ov})
    return designs, skips


def dedupe(symbol: str, designs: Sequence[dict]) -> List[dict]:
    """One design per distinct behaviour; the other labels that build the same configuration are kept as aliases."""
    out, seen = [], {}
    for d in designs:
        key = canonical(symbol, d["overrides"])
        if key in seen:
            seen[key].setdefault("aliases", []).append(d["name"])
            continue
        seen[key] = d
        out.append(d)
    return out


def owner_grid(symbol: str, best_macd: str, best_3rd: str, bases: Sequence[str] = ("L0", "LB")) -> List[dict]:
    """Stage O: SIZE x tier lists {T0,T1,T3,T5,T6,T12,T13} x trigger {RSI level, best TRIG-MACD, best TRIG-3RD}."""
    out = []
    for b in bases:
        for size in ("flat", "plus1", "double", "fibo"):
            for t in ("T0", "T1", "T3", "T5", "T6", "T12", "T13"):
                for trig in ("rsi", best_macd, best_3rd):
                    choice = {"SIZE": size}
                    if t != "T0":
                        choice["TIERS" if t in ("T1", "T3", "T5", "T6") else "GRAN"] = t
                    if trig != "rsi":
                        choice["TRIG-MACD" if trig.startswith("M") else "TRIG-3RD"] = trig
                    ov, why = build(symbol, b, choice)
                    if ov is not None:
                        out.append({"name": design_name(b, choice), "base": b, "choice": choice, "overrides": ov})
    return dedupe(symbol, out)


def factorial(symbol: str, bases: Sequence[str], dims: Dict[str, List[str]]) -> List[dict]:
    """Stage B: all 4 sizes x the 3 chosen levels of each chosen dimension, on the chosen bases ('=' = the base's value)."""
    import itertools
    out = []
    keys = list(dims)
    for b in bases:
        for size in ("flat", "plus1", "double", "fibo"):
            for combo in itertools.product(*[dims[k] for k in keys]):
                choice = {"SIZE": size, **{k: c for k, c in zip(keys, combo) if c != "="}}
                ov, why = build(symbol, b, choice)
                if ov is not None:
                    out.append({"name": design_name(b, choice), "base": b, "choice": choice, "overrides": ov})
    return dedupe(symbol, out)


def neighbours(symbol: str, pairs: Sequence[dict], n: int = 30, seed: int = SEED) -> List[dict]:
    """Stage C: n neighbours of each design (1-3 dimensions changed; adjacent level for ordered dimensions)."""
    rng = np.random.default_rng(seed)
    codes = {d: [c for dd, c, *_ in LEVELS if dd == d] for d in DIMENSIONS}
    ordered = {"DEPTH", "LEVEL", "GAP", "STOP", "TIME", "TARGET", "SIZE"}
    seen, out = {p["name"] for p in pairs}, []
    for p in pairs:
        for _ in range(n):
            choice = dict(p["choice"])
            for dim in rng.choice(DIMENSIONS, size=int(rng.integers(1, 4)), replace=False):
                lv = codes[dim]
                cur = choice.get(dim)
                if dim in ordered and cur in lv:
                    j = lv.index(cur) + int(rng.choice([-1, 1]))
                    choice[dim] = lv[min(max(j, 0), len(lv) - 1)]
                else:
                    choice[dim] = lv[int(rng.integers(len(lv)))]
            name = design_name(p["base"], choice)
            if name in seen:
                continue                            # duplicates dropped, not replaced
            seen.add(name)
            ov, why = build(symbol, p["base"], choice)
            if ov is not None:
                out.append({"name": name, "base": p["base"], "choice": choice, "overrides": ov})
    return out


# ───────────────────────────── running ─────────────────────────────

_W: dict = {}


def metrics(res, a: str, z: str) -> dict:
    """One account's figures (section 3.2)."""
    sc, b, ct = res.scalars, res.baskets, res.counters
    init = float(res.cfg.initial_balance)
    net = sc["final_equity"] - init
    n = len(b)
    span_d = (pd.Timestamp(z) - pd.Timestamp(a)).total_seconds() / 86400.0
    dur = b["duration_s"].to_numpy() if n else np.zeros(0)
    npos = b["n_opened"].to_numpy() if n and "n_opened" in b else (b["n_pos"].to_numpy() if n else np.zeros(0))
    return {
        "net": round(net, 2), "ret_pct": round(net / init * 100.0, 3),
        "wiped": bool(sc["stopped_out"] or sc["min_equity"] <= WIPE_EQUITY * init / ACCOUNT),
        "stopped_out": bool(sc["stopped_out"]), "max_dd_pct": round(sc["max_drawdown_pct"], 3),
        "min_equity": round(sc["min_equity"], 2), "baskets": n, "adds": int(ct["ladder_adds"]),
        "share_add": round(float((npos > 1).mean()), 4) if n else 0.0,
        "mean_pos": round(float(npos.mean()), 3) if n else 0.0, "max_pos": int(sc["max_positions"]),
        "pos_hist": json.dumps(np.bincount(np.minimum(npos.astype(int), 16), minlength=17)[1:].tolist()) if n else "[]",
        "worst_basket": round(float(b["pnl"].min()), 2) if n else 0.0,
        "worst_basket_per_unit": round(float((b["pnl"] / b["units"].clip(lower=1)).min()), 2) if n else 0.0,
        "deepest_float": round(sc["max_floating_loss"], 2), "margin_rejects": int(ct["margin_rejects"]),
        "time_in_market": round(float(dur.sum()) / 86400.0 / span_d, 4) if span_d > 0 else 0.0,
        "baskets_per_month": round(n / (span_d / 30.4375), 2) if span_d > 0 else 0.0,
        "reverse_opens": int(ct.get("reverse_opens", 0)), "hedge_opens": int(ct.get("hedge_opens", 0)),
        "partial_closes": int(ct.get("partial_closes", 0)),
        "open_at_end": int(sc["open_positions_at_end"]), "max_units": int(b["units"].max()) if n else 0,
    }


def _work(task):
    i, seed = task
    d = _W["designs"][i]
    a, z = _W["window"]
    t0 = time.time()
    ov = {**d["overrides"]}
    if seed:
        ov.update(live_timing(seed))
    cfg = LE.live_config(_W["symbol"], start=a, end=z).replace(**ov)
    if len(_W["prep"]._cache) > 6:
        _W["prep"]._cache.clear()
    try:
        res = LE.run(cfg, _W["prep"], light=True, warn_off_grid=False)
        row = metrics(res, a, z)
        err = ""
    except Exception as e:                          # a design that cannot run is reported, never silently dropped
        row, err = {}, repr(e)
    # W1 has few warm-up bars before 2020 (gold ~95, BTC ~45 at the F1 start): such rows are flagged (section 3.1)
    w1 = "W1" in cfg.timeframes()
    return {"symbol": _W["symbol"], "design": d["name"], "start": a, "end": z, "seed": seed, "mode": _W["mode"],
            **row, "reads_w1": w1, "w1_warm_bars": int(_W["prep"].nwarm.get("W1", -1)) if w1 else -1,
            "error": err, "run_s": round(time.time() - t0, 2)}


def _warm_series(symbol: str, designs: Sequence[dict], a: str, z: str) -> None:
    """Build every closed-bar series the designs read in the parent, so fork workers share them."""
    for d in designs:
        cfg = LE.live_config(symbol, start=a, end=z).replace(**d["overrides"])
        LE._series(cfg, cfg.n_ladder_adds, 0, 1 << 62)


def run(symbol: str, designs: Sequence[dict], windows: Sequence[Tuple[str, str]], seeds: Sequence[int] = SEEDS_SCREEN,
        mode: str = "ticks", jobs: int = 6, out_csv: Optional[Path] = None, log=print) -> pd.DataFrame:
    """Every design x window x seed on a fresh $2,000 account (bot sizing). Resumable through ``out_csv``."""
    done = set()
    if out_csv is not None and Path(out_csv).exists():
        prev = pd.read_csv(out_csv)
        done = set(zip(prev["design"], prev["start"], prev["end"], prev["seed"]))
    designs = list(designs)
    tfs = set()
    for d in designs:
        tfs |= set(LE.live_config(symbol).replace(**d["overrides"]).timeframes())
    tfs = sorted(tfs, key=TF_SECONDS.get)
    rows = []
    for (a, z) in windows:
        tasks = [(i, s) for i, d in enumerate(designs) for s in seeds if (d["name"], a, z, s) not in done]
        if not tasks:
            continue
        t0 = time.time()
        _warm_series(symbol, designs, a, z)
        _W.update(symbol=symbol, designs=designs, window=(a, z), mode=mode,
                  prep=LE.prepare(symbol, a, z, tfs, mode=mode))
        log(f"{symbol} {a} → {z}: {mode} prepared in {time.time() - t0:.0f}s, {len(tasks)} runs")
        if jobs > 1:
            with mp.get_context("fork").Pool(jobs) as pool:
                part = pool.map(_work, tasks, chunksize=max(1, len(tasks) // (jobs * 8)))
        else:
            part = [_work(t) for t in tasks]
        _W.clear()
        rows += part
        if out_csv is not None:
            pd.DataFrame(part).to_csv(out_csv, mode="a", header=not Path(out_csv).exists(), index=False)
        log(f"  done in {time.time() - t0:.0f}s")
    return pd.DataFrame(rows)


def _work_unit(i):
    d = _W["designs"][i]
    a, z = _W["window"]
    t0 = time.time()
    ov = {**d["overrides"], "fixed_units": 1, "initial_balance": 1e9, "sizing": "live"}
    if float(ov.get("stop_pct_balance", 0) or 0) > 0:
        # a stop at x% of the balance means x% of $2,000 at unit 1; on $1e9 it would never act (BUILD.md)
        ov["stop_loss_usd_per_unit"] = float(ov.pop("stop_pct_balance")) / 100.0 * ACCOUNT
    cfg = LE.live_config(_W["symbol"], start=a, end=z).replace(**ov, record_interval_s=900)
    res = LE.run(cfg, _W["prep"], light=False)
    b = res.baskets
    # trading days: UTC days with at least 6 h of M1 bars (gold: no weekends; its Sunday-evening hour and other short
    # sessions belong to the next trading day, so T counts full sessions only)
    m1t = LI.m1_history(_W["symbol"])["t"]
    a_s, z_s = int(pd.Timestamp(a).timestamp()), int(pd.Timestamp(z).timestamp())
    dd, cnt = np.unique(m1t[(m1t >= a_s) & (m1t < z_s)] // 86400, return_counts=True)
    tdays = dd[cnt >= 360]
    # daily P/L marked to market: the change of equity (floating included) from one trading day's end to the next
    eq = res.equity
    lv = eq.groupby(eq["time"].dt.floor("D"))["equity"].last() if len(eq) else pd.Series(dtype=float)
    lv_days = lv.index.asi8 // 10**9 // 86400 if len(lv) else np.zeros(0, np.int64)
    k = np.searchsorted(lv_days, tdays, side="right") - 1
    level = np.where(k >= 0, lv.to_numpy()[np.maximum(k, 0)] if len(lv) else 1e9, 1e9).astype(np.float64)
    if len(level):
        level[-1] = res.scalars["final_equity"]
    daily = pd.Series(np.diff(np.concatenate([[1e9], level])), index=pd.to_datetime(tdays * 86400, unit="s", utc=True))
    sr = float(daily.mean() / daily.std(ddof=1)) if daily.std(ddof=1) > 0 else 0.0
    return {"symbol": _W["symbol"], "design": d["name"], "start": a, "end": z, "net_per_unit": round(res.scalars["final_equity"] - 1e9, 2),
            "baskets": len(b), "worst_basket": round(float(b["pnl"].min()), 2) if len(b) else 0.0,
            "deepest_float": round(res.scalars["max_floating_loss"], 2), "daily_sr": sr,
            "skew": float(daily.skew()), "kurt": float(daily.kurt() + 3.0), "days": len(daily),
            "daily": daily.round(2).tolist(), "run_s": round(time.time() - t0, 1)}


def per_unit(symbol: str, designs: Sequence[dict], start: str = SCREEN_SPAN[0], end: str = SCREEN_SPAN[1],
             jobs: int = 4, out_dir: Optional[Path] = None, log=print) -> pd.DataFrame:
    """The R3 per-unit run: fixed_units=1 on $1e9, per second, seed-free; daily P/L kept for the haircut (section 5.4)."""
    designs = list(designs)
    tfs = set()
    for d in designs:
        tfs |= set(LE.live_config(symbol).replace(**d["overrides"]).timeframes())
    t0 = time.time()
    _warm_series(symbol, designs, start, end)
    _W.update(symbol=symbol, designs=designs, window=(start, end), mode="sec",
              prep=LE.prepare(symbol, start, end, sorted(tfs, key=TF_SECONDS.get), mode="sec"))
    log(f"{symbol} per-unit {start} → {end}: prepared in {time.time() - t0:.0f}s, {len(designs)} designs")
    with mp.get_context("fork").Pool(jobs) as pool:
        rows = pool.map(_work_unit, range(len(designs)))
    _W.clear()
    d = pd.DataFrame(rows)
    if out_dir is not None:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        d.drop(columns=["daily"]).to_csv(Path(out_dir) / f"unit_{symbol}.csv", index=False)
        np.savez_compressed(Path(out_dir) / f"unit_daily_{symbol}.npz", names=np.array(d["design"]),
                            daily=np.array([np.asarray(x) for x in d["daily"]], dtype=object), allow_pickle=True)
    return d


def score(df: pd.DataFrame, by: str = "design") -> pd.DataFrame:
    """The rung score per design: wiped accounts (fewer better), then Q = mean(r) / max(max(d), 5), then mean r."""
    g = df.groupby(by)
    s = pd.DataFrame({"accounts": g.size(), "wiped": g["wiped"].sum(), "mean_r": g["ret_pct"].mean(),
                      "median_r": g["ret_pct"].median(), "max_dd": g["max_dd_pct"].max(),
                      "errors": g["error"].apply(lambda e: int((e.fillna("") != "").sum())) if "error" in df else 0})
    s["Q"] = s["mean_r"] / s["max_dd"].clip(lower=5.0)
    return s.sort_values(["wiped", "Q", "mean_r"], ascending=[True, False, False])


# ───────────────────────────── CLI ─────────────────────────────

def write_levels(out: Path = OUT) -> None:
    rows = [{"dimension": d, "code": c, "what": w} for d, c, w, _ in LEVELS]
    (out / "levels.json").write_text(json.dumps({"seed": SEED, "bases": BASES, "levels": rows,
                                                 "tier_lists": TIER_LISTS, "trig3": TRIG3}, indent=1, default=str))
    md = ["# The frozen level table (PREREG_LADDER.md section 2.2), as the runner implements it", "",
          "| Dimension | Code | Level |", "|---|---|---|"] + [f"| {r['dimension']} | {r['code']} | {r['what']} |" for r in rows]
    (out / "LEVELS.md").write_text("\n".join(md) + "\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0]
    if cmd == "levels":
        write_levels()
        print(len(LEVELS), "levels written")
    elif cmd == "stageA":
        sym, out = argv[1], Path(argv[2])
        des, skips = stage_a(sym)
        out.write_text(json.dumps({"designs": des, "skips": skips}, indent=1, default=str))
        print(sym, len(des), "designs,", len(skips), "skipped")
    elif cmd == "run":
        sym, path, rung, out = argv[1], Path(argv[2]), argv[3], Path(argv[4])
        jobs = int(argv[5]) if len(argv) > 5 else 6
        mode = argv[6] if len(argv) > 6 else "ticks"
        des = json.loads(path.read_text())
        des = des["designs"] if isinstance(des, dict) else des
        if len(argv) > 7:                       # cost stress: every design at spread_mult x
            sm = float(argv[7])
            des = [{**d, "name": f"{d['name']}@spread{sm:g}", "overrides": {**d["overrides"], "spread_mult": sm}} for d in des]
        seeds = SEEDS_ALL if rung in FOLDS or rung == "anchor" or rung == "1y" else (SEEDS_SCREEN if rung in ("R1", "R2", "R3") else (0,))
        if mode == "sec":
            seeds = (0,)
        run(sym, des, rung_windows(rung), seeds=seeds, mode=mode, jobs=jobs, out_csv=out)
    elif cmd == "unit":
        sym, path, a, z, out = argv[1], Path(argv[2]), argv[3], argv[4], Path(argv[5])
        jobs = int(argv[6]) if len(argv) > 6 else 4
        des = json.loads(path.read_text())
        des = des["designs"] if isinstance(des, dict) else des
        per_unit(sym, des, a, z, jobs=jobs, out_dir=out)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
