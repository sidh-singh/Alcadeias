"""
Parameter sweeps.

``run_grid`` evaluates a list of configuration overrides against one prepared data
window using a process pool. Each worker loads the window once and then runs the numba
kernel per configuration (about a second for three months of one-second polls), so a
few thousand configurations take minutes.

Grid builders for the questions this suite was written to answer live here too:
which timeframes should drive OPEN / FORCE-CLOSE / BOOK, for RSI and for MACD.
"""

from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import BacktestConfig, TF_SECONDS
from ..engine.fast import Prepared, prepare, run
from .metrics import score_row

_WORKER: dict = {}


def _init(base: dict, tfs: List[str], mode: str, store_dir: Optional[str]):
    os.environ.setdefault("NUMBA_NUM_THREADS", "1")
    cfg = BacktestConfig.from_dict(base)
    kw = {"store_dir": store_dir} if store_dir else {}
    _WORKER["base"] = cfg
    _WORKER["prep"] = prepare(cfg.symbol, cfg.start, cfg.end, tfs, mode=mode, **kw)


def _one(task: Tuple[int, dict]) -> dict:
    i, ov = task
    base: BacktestConfig = _WORKER["base"]
    prep: Prepared = _WORKER["prep"]
    cfg = base.replace(**ov)
    if len(prep._cache) > 3:      # keep worker memory bounded when indicator params vary
        prep._cache.clear()
    res = run(cfg, prep, light=True)
    row = score_row(res)
    row["_i"] = i
    return row


def grid_timeframes(base: BacktestConfig, grid: Sequence[dict]) -> List[str]:
    """Every timeframe any configuration in the grid reads."""
    tfs = set(base.timeframes())
    for ov in grid:
        tfs |= set(base.replace(**ov).timeframes())
    return sorted(tfs, key=TF_SECONDS.get)


def run_grid(base: BacktestConfig, grid: Sequence[dict], n_jobs: Optional[int] = None,
             mode: str = "sec", labels: Optional[Sequence[dict]] = None,
             store_dir: Optional[str] = None, progress=None) -> pd.DataFrame:
    """
    Run ``base.replace(**ov)`` for every override dict in ``grid``.

    Returns one row per configuration: the override's label columns (``labels[i]``, or the
    override itself) followed by the metrics of ``metrics.score_row``.
    """
    grid = list(grid)
    if not grid:
        return pd.DataFrame()
    tfs = grid_timeframes(base, grid)
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2) - 1)
    n_jobs = min(n_jobs, len(grid))
    tasks = list(enumerate(grid))
    rows: List[dict] = []
    t0 = time.time()
    if n_jobs == 1:
        _init(base.to_dict(), tfs, mode, store_dir)
        for k, t in enumerate(tasks):
            rows.append(_one(t))
            if progress and (k + 1) % 50 == 0:
                progress(k + 1, len(tasks), time.time() - t0)
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(n_jobs, initializer=_init, initargs=(base.to_dict(), tfs, mode, store_dir)) as pool:
            for k, r in enumerate(pool.imap_unordered(_one, tasks, chunksize=max(1, len(tasks) // (n_jobs * 16)))):
                rows.append(r)
                if progress and (k + 1) % 100 == 0:
                    progress(k + 1, len(tasks), time.time() - t0)
    rows.sort(key=lambda r: r["_i"])
    met = pd.DataFrame(rows).drop(columns=["_i"])
    lab = pd.DataFrame([_flatten(l) for l in (labels if labels is not None else grid)])
    return pd.concat([lab.reset_index(drop=True), met.reset_index(drop=True)], axis=1)


def _flatten(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = "+".join(f"{tf}" if _same(w) else f"{tf}{_wfmt(w)}"
                              for tf, w in sorted(v.items(), key=lambda kv: -TF_SECONDS.get(kv[0], 0))) or "-"
        elif isinstance(v, (list, tuple)):
            out[k] = ",".join(str(x) for x in v)
        else:
            out[k] = v
    return out


def _same(w) -> bool:
    return not isinstance(w, (list, tuple)) or (w[0] == w[1] == 1)


def _wfmt(w) -> str:
    if not isinstance(w, (list, tuple)):
        return f"x{w:g}"
    r, m = w
    if r and not m:
        return "[rsi]"
    if m and not r:
        return "[macd]"
    return f"[{r:g},{m:g}]"


# ───────────────────────────── grid builders ─────────────────────────────

def tf_sets(universe: Sequence[str], max_size: int = 2) -> List[Tuple[str, ...]]:
    """All non-empty subsets of ``universe`` up to ``max_size`` timeframes."""
    out: List[Tuple[str, ...]] = []
    for k in range(1, max_size + 1):
        out += list(itertools.combinations(universe, k))
    return out


def grid_joint_timeframes(universe: Sequence[str], variant: str,
                          open_max: int = 2, fc_max: int = 1, book_max: int = 1,
                          strict_entry: Sequence[bool] = (False, True),
                          fc_levels: Sequence[str] = ("half", "full")) -> Tuple[List[dict], List[dict]]:
    """
    OPEN x FORCE-CLOSE (x BOOK on netting) timeframe grid, RSI and MACD on the same
    timeframes (the live structure). Thresholds follow the live convention so every
    cell is a like-for-like alternative to the current settings:

      entry_s        loose  = 2 (one timeframe fully aligned, as live)
                     strict = 2 x number of open timeframes (every one fully aligned)
      entry_agree_s  full agreement of the force-close score (as live)
      force_close_s  half = 1 (one indicator reverses, as live); full = every one reverses
      book_s         1 (as live)
    """
    grid, labels = [], []
    for o in tf_sets(universe, open_max):
        for f in tf_sets(universe, fc_max):
            books = tf_sets(universe, book_max) if variant == "netting" else [()]
            for bk in books:
                for strict in strict_entry:
                    if strict and len(o) == 1:
                        continue          # identical to loose for a single open timeframe
                    for lvl in fc_levels:
                        fc_range = 2.0 * len(f)
                        ov = dict(
                            open_weights={tf: 1 for tf in o},
                            fc_weights={tf: 1 for tf in f},
                            entry_s=2.0 * len(o) if strict else 2.0,
                            entry_agree_s=fc_range,
                            ladder_s=2.0,
                            force_close_s=1.0 if lvl == "half" else fc_range,
                        )
                        lab = dict(open="+".join(o), fc="+".join(f),
                                   entry="strict" if strict else "loose", fc_level=lvl)
                        if variant == "netting":
                            ov.update(book_weights={tf: 1 for tf in bk}, book_s=1.0)
                            lab["book"] = "+".join(bk)
                        grid.append(ov)
                        labels.append(lab)
    return grid, labels


def grid_split_indicator(universe: Sequence[str], variant: str,
                         fc_tfs: Optional[Sequence[str]] = None,
                         book_tfs: Optional[Sequence[str]] = None) -> Tuple[List[dict], List[dict]]:
    """
    RSI and MACD on *different* timeframes for the OPEN score.

    open_score = rsi_sign[TF_rsi] + macd_sign[TF_macd]; opens at |score| = 2 (both agree).
    The force-close (and book) stay on one timeframe each, swept over ``fc_tfs``.
    """
    fc_tfs = list(fc_tfs or universe)
    grid, labels = [], []
    for r_tf in universe:
        for m_tf in universe:
            for f in fc_tfs:
                books = list(book_tfs or universe) if variant == "netting" else [None]
                for bk in books:
                    ow: Dict[str, tuple] = {}
                    if r_tf == m_tf:
                        ow[r_tf] = (1, 1)
                    else:
                        ow[r_tf] = (1, 0)
                        ow[m_tf] = (0, 1)
                    ov = dict(open_weights=ow, fc_weights={f: 1}, entry_s=2.0, entry_agree_s=2.0,
                              ladder_s=2.0, force_close_s=1.0)
                    lab = dict(open_rsi=r_tf, open_macd=m_tf, fc=f)
                    if variant == "netting":
                        ov.update(book_weights={bk: 1}, book_s=1.0)
                        lab["book"] = bk
                    grid.append(ov)
                    labels.append(lab)
    return grid, labels


def grid_split_exit(universe: Sequence[str], variant: str, section: str = "fc") -> Tuple[List[dict], List[dict]]:
    """RSI and MACD on different timeframes for one EXIT section (``fc`` or ``book``), open as live."""
    grid, labels = [], []
    for r_tf in universe:
        for m_tf in universe:
            w: Dict[str, tuple] = {}
            if r_tf == m_tf:
                w[r_tf] = (1, 1)
            else:
                w[r_tf] = (1, 0)
                w[m_tf] = (0, 1)
            if section == "fc":
                ov = dict(fc_weights=w, entry_agree_s=2.0, force_close_s=1.0)
            else:
                ov = dict(book_weights=w, book_s=1.0)
            grid.append(ov)
            labels.append({f"{section}_rsi": r_tf, f"{section}_macd": m_tf})
    return grid, labels


def grid_one_at_a_time(params: Dict[str, Iterable]) -> Tuple[List[dict], List[dict]]:
    """One-at-a-time sensitivity: vary each parameter alone, everything else as the base."""
    grid, labels = [], []
    for name, values in params.items():
        for v in values:
            if isinstance(v, dict) and name.startswith("@"):   # a named bundle of overrides
                grid.append(dict(v["set"]))
                labels.append(dict(param=name[1:], value=v["name"]))
            else:
                grid.append({name: v})
                labels.append(dict(param=name, value=_label(v)))
    return grid, labels


def _label(v) -> str:
    if isinstance(v, dict):
        return _flatten({"x": v})["x"]
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    return str(v)
