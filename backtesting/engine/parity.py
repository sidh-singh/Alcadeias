"""
Parity check: the fast engine against the live code.

``check_parity`` replays the same window through ``run_reference`` (this branch's real
``app.py`` loop on a simulated terminal) and through the numba kernel, then compares

  * the poll timestamps (the loop cadence, including the post-order sleeps),
  * the signal the strategy returned at every poll,
  * the section scores and the ladder RSI values at every poll,
  * every fill (time, side, lots, price, realised profit),
  * the final balance.

A window passes only if all of them match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from ..config import BacktestConfig, REPO_ROOT
from ..data import store
from . import kernels as K
from .fast import Result, prepare, run
from .reference import ReferenceResult, run_reference

# the live helper sleeps 0.1 s inside buy()/sell(); the fast engine must keep the same cadence
LIVE_OPEN_ORDER_DELAY_MS = 100


@dataclass
class ParityReport:
    ok: bool
    polls_ref: int
    polls_fast: int
    signal_mismatches: int
    score_mismatches: int
    rsi_max_abs_diff: float
    fills_ref: int
    fills_fast: int
    fill_mismatches: int
    balance_ref: float
    balance_fast: float
    signals_ref: dict = field(default_factory=dict)
    first_differences: List[str] = field(default_factory=list)
    ref_errors: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        head = "PARITY OK" if self.ok else "PARITY FAILED"
        lines = [
            f"{head}: {self.polls_ref:,} live polls (fast {self.polls_fast:,}), "
            f"signal mismatches {self.signal_mismatches}, score mismatches {self.score_mismatches}, "
            f"max |RSI diff| {self.rsi_max_abs_diff:.2e}",
            f"  fills ref {self.fills_ref} / fast {self.fills_fast}, mismatched {self.fill_mismatches}; "
            f"balance ref {self.balance_ref:.2f} / fast {self.balance_fast:.2f}",
            f"  signals seen by the live code: {self.signals_ref}",
        ]
        lines += [f"  ! {d}" for d in self.first_differences[:12]]
        lines += [f"  live-code error: {e}" for e in self.ref_errors[:5]]
        return "\n".join(lines)


def fast_config_for_parity(cfg: BacktestConfig) -> BacktestConfig:
    # SimMT5 accepts every order, so the broker's close-only windows are switched off here
    return cfg.replace(open_order_delay_ms=LIVE_OPEN_ORDER_DELAY_MS,
                       close_only_after_break_s=0.0, close_only_after_weekend_s=0.0)


def compare(cfg: BacktestConfig, ref: ReferenceResult, fast: Result,
            rsi_tol: float = 1e-6, score_tol: float = 1e-9, money_tol: float = 0.0051) -> ParityReport:
    diffs: List[str] = []
    rt = ref.trace[ref.trace["fresh"]].reset_index(drop=True)
    ft = fast.trace
    n_ref, n_fast = len(rt), len(ft)
    n = min(n_ref, n_fast)

    def ts(ms):
        return pd.Timestamp(int(ms), unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    t_ref = rt["t_ms"].to_numpy(np.int64)[:n]
    t_fast = ft[:n, K.T_T].astype(np.int64)
    bad_t = np.flatnonzero(t_ref != t_fast)
    if n_ref != n_fast:
        diffs.append(f"poll count differs: live {n_ref} vs fast {n_fast}")
    if len(bad_t):
        i = int(bad_t[0])
        diffs.append(f"cadence diverges at poll {i}: live {ts(t_ref[i])} vs fast {ts(t_fast[i])}")
        n = i   # everything after a cadence break is incomparable

    sig_ref = rt["signal"].to_numpy(np.int64)[:n]
    sig_fast = ft[:n, K.T_SIGNAL].astype(np.int64)
    bad_sig = np.flatnonzero(sig_ref != sig_fast)
    for i in bad_sig[:5]:
        diffs.append(f"signal at {ts(t_ref[i])}: live {int(sig_ref[i])} vs fast {int(sig_fast[i])} "
                     f"(open {rt['open_score'][i]} / {ft[i, K.T_OPEN_SCORE]}, fc {rt['fc_score'][i]} / "
                     f"{ft[i, K.T_FC_SCORE]}, n_pos {rt['n_pos'][i]} / {ft[i, K.T_NPOS]:.0f}, "
                     f"profit {rt['profit'][i]} / {ft[i, K.T_PROFIT]})")

    score_bad = 0
    for col, kcol in (("open_score", K.T_OPEN_SCORE), ("fc_score", K.T_FC_SCORE), ("book_score", K.T_BOOK_SCORE)):
        a = rt[col].to_numpy(float)[:n]
        if np.all(np.isnan(a)):
            continue   # this variant has no such score
        b = ft[:n, kcol]
        bad = np.flatnonzero(~(np.abs(a - b) <= score_tol))
        score_bad += len(bad)
        for i in bad[:3]:
            diffs.append(f"{col} at {ts(t_ref[i])}: live {a[i]} vs fast {b[i]}")

    rsi_max = 0.0
    for q, tf in enumerate(cfg.ladder_tfs):
        a = rt[f"rsi_{tf}"].to_numpy(float)[:n]
        b = ft[:n, K.T_RSI0 + q]
        if n:
            d = float(np.nanmax(np.abs(a - b)))
            rsi_max = max(rsi_max, d)
            if d > rsi_tol:
                i = int(np.nanargmax(np.abs(a - b)))
                diffs.append(f"RSI {tf} at {ts(t_ref[i])}: live {a[i]:.9f} vs fast {b[i]:.9f}")

    for col, kcol, tol in (("n_pos", K.T_NPOS, 0.0), ("profit", K.T_PROFIT, money_tol), ("units", K.T_UNITS, 0.0)):
        a = rt[col].to_numpy(float)[:n]
        b = ft[:n, kcol]
        bad = np.flatnonzero(np.abs(a - b) > tol)
        if len(bad):
            i = int(bad[0])
            diffs.append(f"{col} at {ts(t_ref[i])}: live {a[i]} vs fast {b[i]} ({len(bad)} polls)")
            score_bad += len(bad)

    # fills
    d, f = ref.deals, fast.fills
    fill_bad = 0
    if len(d) != len(f):
        diffs.append(f"fill count differs: live {len(d)} vs fast {len(f)}")
        fill_bad += abs(len(d) - len(f))
    m = min(len(d), len(f))
    if m:
        f_t = (f["time"].astype("int64") // 1_000_000).to_numpy()[:m]
        f_side = np.where(f["side"].to_numpy()[:m] == "BUY", 0, 1)
        f_out = (f["action"].to_numpy()[:m] == "close")
        d_out = (d["entry"].to_numpy()[:m] == "out")
        # an 'out' deal closes a position of d.type; an 'in' deal opens d.type
        same = ((d_out == f_out)
                & (d["type"].to_numpy(np.int64)[:m] == f_side)
                & (np.abs(d["volume"].to_numpy(float)[:m] - f["lots"].to_numpy()[:m]) < 1e-9)
                & (np.abs(d["price"].to_numpy(float)[:m] - f["price"].to_numpy()[:m]) < 1e-9)
                & (np.abs(d["profit"].to_numpy(float)[:m] - f["profit"].to_numpy()[:m]) <= money_tol))
        # the live loop sleeps between the decision and later sends, so compare decision times loosely
        same &= np.abs(d["t_ms"].to_numpy(np.int64)[:m] - f_t) <= 1500
        bad = np.flatnonzero(~same)
        fill_bad += len(bad)
        for i in bad[:5]:
            diffs.append(f"fill {i}: live {ts(d['t_ms'][i])} {d['entry'][i]} type {d['type'][i]} "
                         f"{d['volume'][i]} @ {d['price'][i]} p/l {d['profit'][i]} vs fast "
                         f"{f['time'][i]} {f['action'][i]} {f['side'][i]} {f['lots'][i]} @ {f['price'][i]} "
                         f"p/l {f['profit'][i]}")

    bal_ok = abs(ref.final_balance - fast.scalars["final_balance"]) <= max(money_tol, 0.0051 * max(len(d), 1))
    if not bal_ok:
        diffs.append(f"final balance: live {ref.final_balance:.2f} vs fast {fast.scalars['final_balance']:.2f}")

    names = {0: "none", 1: "BUY", 2: "SELL", 3: "CLOSE_BUY", 4: "CLOSE_SELL", 5: "BUY_MORE", 6: "SELL_MORE"}
    vals, cnts = np.unique(rt["signal"].to_numpy(np.int64), return_counts=True)
    ok = (not diffs) and (len(bad_sig) == 0) and score_bad == 0 and fill_bad == 0 and not ref.errors
    return ParityReport(
        ok=ok, polls_ref=n_ref, polls_fast=n_fast, signal_mismatches=int(len(bad_sig)),
        score_mismatches=int(score_bad), rsi_max_abs_diff=rsi_max,
        fills_ref=int(len(d)), fills_fast=int(len(f)), fill_mismatches=int(fill_bad),
        balance_ref=float(ref.final_balance), balance_fast=float(fast.scalars["final_balance"]),
        signals_ref={names[int(v)]: int(c) for v, c in zip(vals, cnts)},
        first_differences=diffs, ref_errors=list(ref.errors))


def check_parity(cfg: BacktestConfig, live_root: Path = REPO_ROOT, mode: str = "ticks",
                 store_dir: Path = store.DEFAULT_STORE_DIR, progress=None) -> ParityReport:
    """Run both engines over [cfg.start, cfg.end) and compare them."""
    ref = run_reference(cfg, live_root=live_root, mode=mode, store_dir=store_dir, progress=progress)
    fcfg = fast_config_for_parity(cfg)
    prep = prepare(fcfg.symbol, fcfg.start, fcfg.end, fcfg.timeframes(), mode=mode, store_dir=store_dir)
    fast = run(fcfg, prep, trace=True)
    return compare(cfg, ref, fast)
