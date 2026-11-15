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
from .reference import ReferenceResult, ladder_rsi_columns, run_reference

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
    # orders the simulated broker refused while the live code ran, by reason: shows whether a window
    # exercised the broker-side rules (market closed, close-only after a reopen, margin) at all
    refused_ref: dict = field(default_factory=dict)
    # polls where the kernel wanted an entry that its execution-time filters (window, trend, ...) then held
    # back, and the live strategy already returned "do nothing" (accepted only with blocked_entries_ok)
    signal_blocked_entry: int = 0
    # polls where the cooldown state (entry_allowed) differs (counted only with check_entry_allowed)
    entry_allowed_mismatches: int = 0
    # the earliest difference of any kind, in time order (None: none)
    first_divergence_ms: Optional[int] = None
    first_divergence: str = ""

    def __str__(self) -> str:
        head = "PARITY OK" if self.ok else "PARITY FAILED"
        lines = [
            f"{head}: {self.polls_ref:,} live polls (fast {self.polls_fast:,}), "
            f"signal mismatches {self.signal_mismatches}, score mismatches {self.score_mismatches}, "
            f"max |RSI diff| {self.rsi_max_abs_diff:.2e}",
            f"  fills ref {self.fills_ref} / fast {self.fills_fast}, mismatched {self.fill_mismatches}; "
            f"balance ref {self.balance_ref:.2f} / fast {self.balance_fast:.2f}",
            f"  signals seen by the live code: {self.signals_ref}",
            f"  orders the broker refused in the live run: {self.refused_ref or 'none'}",
        ]
        if self.signal_blocked_entry:
            lines.append(f"  entries held back by an execution-time filter (strategy said 'do nothing', the kernel "
                         f"wanted in and did not send): {self.signal_blocked_entry} polls")
        if self.first_divergence:
            lines.append(f"  first divergence: {self.first_divergence}")
        lines += [f"  ! {d}" for d in self.first_differences[:12]]
        lines += [f"  live-code error: {e}" for e in self.ref_errors[:5]]
        return "\n".join(lines)


def fast_config_for_parity(cfg: BacktestConfig) -> BacktestConfig:
    """
    The fast-engine configuration that corresponds to a reference run of ``cfg``: the 0.1 s the
    live helper sleeps after an order, and no data-hole handling (that is hygiene for the
    backtest's own data; the live code never meets a hole, it just sees a silent market).
    The broker-side rules (market closed, close-only after a reopen, margin) stay as in ``cfg``:
    the simulated terminal applies the same ones.
    """
    return cfg.replace(open_order_delay_ms=LIVE_OPEN_ORDER_DELAY_MS, data_hole_s=0.0)


def compare(cfg: BacktestConfig, ref: ReferenceResult, fast: Result,
            rsi_tol: float = 1e-6, score_tol: float = 1e-9, money_tol: float = 0.0051,
            blocked_entries_ok: bool = False, check_entry_allowed: bool = False) -> ParityReport:
    """
    ``blocked_entries_ok``  accept a poll where the live strategy returned "do nothing" while the kernel
                            wanted an entry but sent no order: the kernel writes its signal before its
                            execution-time filters (window brake, trend, volatility not known, ...), so a
                            branch that applies such a filter inside its strategy instead of next to the brake
                            in app.py differs there in the signal alone. The fills still have to match.
    ``check_entry_allowed`` also compare the cooldown state (re-entry and loss pause) at every poll.
    """
    diffs: List[str] = []
    # (time ms, rank, what) of the first difference of each kind; at one time the cadence is named first, then
    # the signal, the scores, the RSI, the position, the cooldown, the fills and the poll count
    firsts: List[tuple] = []
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
        if not len(bad_t):
            longer = rt["t_ms"].to_numpy(np.int64) if n_ref > n_fast else ft[:, K.T_T].astype(np.int64)
            firsts.append((int(longer[n]), 7, f"poll count: the {'live' if n_ref > n_fast else 'fast'} engine polls "
                                           f"on at {ts(longer[n])} after the other has stopped"))
    if len(bad_t):
        i = int(bad_t[0])
        diffs.append(f"cadence diverges at poll {i}: live {ts(t_ref[i])} vs fast {ts(t_fast[i])}")
        firsts.append((int(min(t_ref[i], t_fast[i])), 0, f"cadence: poll {i} at live {ts(t_ref[i])} / fast {ts(t_fast[i])}"))
        n = i   # everything after a cadence break is incomparable

    sig_ref = rt["signal"].to_numpy(np.int64)[:n]
    sig_fast = ft[:n, K.T_SIGNAL].astype(np.int64)
    bad = sig_ref != sig_fast
    blocked = 0
    if blocked_entries_ok and bad.any():
        f = fast.fills
        opened = set()
        if len(f):
            ot = f.loc[f["action"].to_numpy() == "open", "time"]
            opened = set((ot.dt.as_unit("ns").astype("int64") // 1_000_000).tolist())
        held = (bad & (sig_ref == 0) & ((sig_fast == 1) | (sig_fast == 2))
                & ~np.isin(t_fast[:n], np.fromiter(opened, np.int64, len(opened))))
        blocked = int(held.sum())
        bad &= ~held
    bad_sig = np.flatnonzero(bad)
    for i in bad_sig[:5]:
        diffs.append(f"signal at {ts(t_ref[i])}: live {int(sig_ref[i])} vs fast {int(sig_fast[i])} "
                     f"(open {rt['open_score'][i]} / {ft[i, K.T_OPEN_SCORE]}, fc {rt['fc_score'][i]} / "
                     f"{ft[i, K.T_FC_SCORE]}, n_pos {rt['n_pos'][i]} / {ft[i, K.T_NPOS]:.0f}, "
                     f"profit {rt['profit'][i]} / {ft[i, K.T_PROFIT]})")
    if len(bad_sig):
        i = int(bad_sig[0])
        firsts.append((int(t_ref[i]), 1, f"signal at {ts(t_ref[i])}: live {int(sig_ref[i])} vs fast {int(sig_fast[i])}"))

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
        if len(bad):
            firsts.append((int(t_ref[bad[0]]), 2, f"{col} at {ts(t_ref[bad[0]])}: live {a[bad[0]]} vs fast {b[bad[0]]}"))

    # the kernel records the RSI of the tiers it can use only (n_ladder_adds of them, at most T_N - T_RSI0)
    rsi_max = 0.0
    rsi_cols = ladder_rsi_columns(cfg.ladder_tfs)
    for q in range(min(cfg.n_ladder_adds, K.T_N - K.T_RSI0)):
        tf = cfg.ladder_tfs[q]
        a = rt[rsi_cols[q]].to_numpy(float)[:n]
        b = ft[:n, K.T_RSI0 + q]
        if n and not np.all(np.isnan(a)):
            dd = np.abs(a - b)
            d = float(np.nanmax(dd))
            rsi_max = max(rsi_max, d)
            if d > rsi_tol:
                i = int(np.nanargmax(dd))
                diffs.append(f"RSI {tf} at {ts(t_ref[i])}: live {a[i]:.9f} vs fast {b[i]:.9f}")
                j = int(np.flatnonzero(dd > rsi_tol)[0])
                firsts.append((int(t_ref[j]), 3, f"RSI {tf} at {ts(t_ref[j])}: live {a[j]:.9f} vs fast {b[j]:.9f}"))

    for col, kcol, tol in (("n_pos", K.T_NPOS, 0.0), ("profit", K.T_PROFIT, money_tol), ("units", K.T_UNITS, 0.0)):
        a = rt[col].to_numpy(float)[:n]
        b = ft[:n, kcol]
        bad = np.flatnonzero(np.abs(a - b) > tol)
        if len(bad):
            i = int(bad[0])
            diffs.append(f"{col} at {ts(t_ref[i])}: live {a[i]} vs fast {b[i]} ({len(bad)} polls)")
            firsts.append((int(t_ref[i]), 4, f"{col} at {ts(t_ref[i])}: live {a[i]} vs fast {b[i]}"))
            score_bad += len(bad)

    ea_bad = 0
    if check_entry_allowed:
        a = rt["entry_allowed"].to_numpy(bool)[:n]
        b = ft[:n, K.T_ENTRY_ALLOWED] > 0.5
        bad = np.flatnonzero(a != b)
        ea_bad = int(len(bad))
        if ea_bad:
            i = int(bad[0])
            diffs.append(f"entry_allowed (cooldown / loss pause) at {ts(t_ref[i])}: live {bool(a[i])} vs fast "
                         f"{bool(b[i])} ({ea_bad} polls)")
            firsts.append((int(t_ref[i]), 5, f"entry_allowed at {ts(t_ref[i])}: live {bool(a[i])} vs fast {bool(b[i])}"))

    # fills
    d, f = ref.deals, fast.fills
    fill_bad = 0
    if len(d) != len(f):
        diffs.append(f"fill count differs: live {len(d)} vs fast {len(f)}")
        fill_bad += abs(len(d) - len(f))
    m = min(len(d), len(f))
    f_t = (f["time"].dt.as_unit("ns").astype("int64") // 1_000_000).to_numpy() if len(f) else np.zeros(0, np.int64)
    if len(d) != len(f):
        extra_t = int(d["t_ms"].iloc[m]) if len(d) > m else int(f_t[m])
        firsts.append((extra_t, 6, f"fill {m} at {ts(extra_t)} exists in the {'live' if len(d) > m else 'fast'} "
                                f"run only"))
    if m:
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
        same &= np.abs(d["t_ms"].to_numpy(np.int64)[:m] - f_t[:m]) <= 1500
        bad = np.flatnonzero(~same)
        fill_bad += len(bad)
        for i in bad[:5]:
            diffs.append(f"fill {i}: live {ts(d['t_ms'][i])} {d['entry'][i]} type {d['type'][i]} "
                         f"{d['volume'][i]} @ {d['price'][i]} p/l {d['profit'][i]} vs fast "
                         f"{f['time'][i]} {f['action'][i]} {f['side'][i]} {f['lots'][i]} @ {f['price'][i]} "
                         f"p/l {f['profit'][i]}")
        if len(bad):
            i = int(bad[0])
            firsts.append((int(min(d["t_ms"].iloc[i], f_t[i])), 6, f"fill {i}: live {ts(d['t_ms'].iloc[i])} "
                           f"{d['entry'].iloc[i]} {d['volume'].iloc[i]} @ {d['price'].iloc[i]} vs fast "
                           f"{ts(f_t[i])} {f['action'].iloc[i]} {f['lots'].iloc[i]} @ {f['price'].iloc[i]}"))

    bal_ok = abs(ref.final_balance - fast.scalars["final_balance"]) <= max(money_tol, 0.0051 * max(len(d), 1))
    if not bal_ok:
        diffs.append(f"final balance: live {ref.final_balance:.2f} vs fast {fast.scalars['final_balance']:.2f}")

    names = {0: "none", 1: "BUY", 2: "SELL", 3: "CLOSE_BUY", 4: "CLOSE_SELL", 5: "BUY_MORE", 6: "SELL_MORE"}
    vals, cnts = np.unique(rt["signal"].to_numpy(np.int64), return_counts=True)
    ok = (not diffs) and (len(bad_sig) == 0) and score_bad == 0 and fill_bad == 0 and not ref.errors
    first_ms, _, first = min(firsts) if firsts else (None, 0, "")
    return ParityReport(
        ok=ok, polls_ref=n_ref, polls_fast=n_fast, signal_mismatches=int(len(bad_sig)),
        score_mismatches=int(score_bad), rsi_max_abs_diff=rsi_max,
        fills_ref=int(len(d)), fills_fast=int(len(f)), fill_mismatches=int(fill_bad),
        balance_ref=float(ref.final_balance), balance_fast=float(fast.scalars["final_balance"]),
        signals_ref={names[int(v)]: int(c) for v, c in zip(vals, cnts)},
        first_differences=diffs, ref_errors=list(ref.errors),
        refused_ref={k: int(v) for k, v in (getattr(ref, "refused", None) or {}).items() if v},
        signal_blocked_entry=blocked, entry_allowed_mismatches=ea_bad,
        first_divergence_ms=first_ms, first_divergence=first)


def check_parity(cfg: BacktestConfig, live_root: Path = REPO_ROOT, mode: str = "ticks",
                 store_dir: Path = store.DEFAULT_STORE_DIR, progress=None) -> ParityReport:
    """Run both engines over [cfg.start, cfg.end) and compare them."""
    ref = run_reference(cfg, live_root=live_root, mode=mode, store_dir=store_dir, progress=progress)
    fcfg = fast_config_for_parity(cfg)
    prep = prepare(fcfg.symbol, fcfg.start, fcfg.end, fcfg.timeframes(), mode=mode, store_dir=store_dir)
    # (in 'sec' mode both engines are fed the same per-second rows, so the 0.1 s order sleep is applied
    #  to that series on purpose: no warning about off-grid timing)
    fast = run(fcfg, prep, trace=True, warn_off_grid=False)
    return compare(cfg, ref, fast)
