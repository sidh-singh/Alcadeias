"""
Robustness tests: does a result survive things the bot cannot control?

* ``timing_grid``     loop period, poll phase and order latency (needs raw ticks)
* ``cost_grid``       wider spread, slippage, commission
* ``start_shift``     the same strategy started a few days later (path dependence)
* ``segments``        each sub-period on a fresh balance (is the edge stable in time?)
* ``bootstrap``       resampled sequences of whole trading days (drawdown / loss odds)
* ``across_windows``  one grid over several windows + rank agreement between them
                      (in-sample choice vs out-of-sample outcome)

Every function returns a DataFrame so the numbers can be read, plotted or re-tested.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from .sweep import run_grid


def _ts(x) -> pd.Timestamp:
    return pd.Timestamp(x)


def timing_grid(cfg: BacktestConfig, periods_ms: Sequence[int] = (1000, 1250, 1500, 2000),
                phases_ms: Sequence[int] = (0, 250, 500, 750),
                latencies_ms: Sequence[int] = (0, 150, 300, 600, 1000),
                n_jobs: int = 2, store_dir: Optional[str] = None) -> pd.DataFrame:
    """
    Loop timing the bot does not control. The live loop runs "about once a second" plus
    however long MT5 takes to answer; an order reaches the server some time after the
    quote that triggered it. Runs on raw ticks so sub-second offsets are real.
    """
    start = _ts(cfg.start)
    grid, labels = [], []
    for p in periods_ms:
        for ph in phases_ms:
            if ph >= p:
                continue
            grid.append(dict(poll_interval_ms=int(p), latency_ms=0, open_order_delay_ms=100,
                             start=str(start + pd.Timedelta(milliseconds=int(ph)))))
            labels.append(dict(test="poll", poll_ms=int(p), phase_ms=int(ph), latency_ms=0))
    for lat in latencies_ms:
        grid.append(dict(poll_interval_ms=1000, latency_ms=int(lat), open_order_delay_ms=100))
        labels.append(dict(test="latency", poll_ms=1000, phase_ms=0, latency_ms=int(lat)))
    return run_grid(cfg, grid, n_jobs=n_jobs, mode="ticks", labels=labels, store_dir=store_dir)


def cost_grid(cfg: BacktestConfig, spread_mults: Sequence[float] = (1.0, 1.25, 1.5, 2.0, 3.0),
              slippages: Optional[Sequence[float]] = None, n_jobs: Optional[int] = None,
              store_dir: Optional[str] = None) -> pd.DataFrame:
    """Transaction-cost stress: the recorded spread scaled up, and adverse slippage per fill."""
    if slippages is None:
        # in price units: a few cents on gold, a few dollars on BTC
        slippages = (0.0, 0.02, 0.05, 0.10) if cfg.symbol.startswith("XAU") else (0.0, 1.0, 2.5, 5.0)
    grid, labels = [], []
    for m in spread_mults:
        grid.append(dict(spread_mult=float(m)))
        labels.append(dict(test="spread", spread_mult=float(m), slippage=0.0))
    for s in slippages:
        if s == 0.0:
            continue
        grid.append(dict(slippage=float(s)))
        labels.append(dict(test="slippage", spread_mult=1.0, slippage=float(s)))
    return run_grid(cfg, grid, n_jobs=n_jobs, labels=labels, store_dir=store_dir)


def start_shift(cfg: BacktestConfig, shifts_days: Sequence[float] = (0, 1, 2, 3, 4, 5, 6, 7, 10, 14),
                n_jobs: Optional[int] = None, store_dir: Optional[str] = None) -> pd.DataFrame:
    """Start the same configuration later, same end. A robust edge should not care."""
    start = _ts(cfg.start)
    grid = [dict(start=str(start + pd.Timedelta(days=float(d)))) for d in shifts_days]
    labels = [dict(start_shift_days=float(d)) for d in shifts_days]
    return run_grid(cfg, grid, n_jobs=n_jobs, labels=labels, store_dir=store_dir)


def segments(cfg: BacktestConfig, freq: str = "MS", fixed_days: Optional[int] = None,
             n_jobs: Optional[int] = None, store_dir: Optional[str] = None) -> pd.DataFrame:
    """Every sub-period on a fresh balance. ``fixed_days`` cuts equal slices instead of calendar months."""
    a, z = _ts(cfg.start), _ts(cfg.end)
    if fixed_days:
        edges = list(pd.date_range(a, z, freq=f"{int(fixed_days)}D"))
    else:
        edges = [a] + [d for d in pd.date_range(a, z, freq=freq) if a < d < z]
    if edges[-1] < z:
        edges.append(z)
    grid, labels = [], []
    for s, e in zip(edges[:-1], edges[1:]):
        if (e - s).total_seconds() < 86400:
            continue
        grid.append(dict(start=str(s), end=str(e)))
        labels.append(dict(segment=f"{s:%Y-%m-%d} → {e:%Y-%m-%d}", days=round((e - s).total_seconds() / 86400, 1)))
    return run_grid(cfg, grid, n_jobs=n_jobs, labels=labels, store_dir=store_dir)


def bootstrap(baskets: pd.DataFrame, initial_balance: float, n: int = 5000, seed: int = 7) -> Dict[str, float]:
    """
    Block bootstrap over whole UTC days of realised basket P/L.

    Days are resampled with replacement (keeping each day's baskets together and in
    order, because losses cluster inside a day). Reports the spread of outcomes the same
    trade population could have produced in a different order. Realised P/L only -- the
    floating drawdown inside a basket is *not* in here, so real drawdowns are deeper.
    """
    if len(baskets) == 0:
        return {}
    rng = np.random.default_rng(seed)
    day = baskets["close_time"].dt.floor("D")
    groups = [g["pnl"].to_numpy() for _, g in baskets.sort_values("close_time").groupby(day)]
    k = len(groups)
    finals = np.empty(n)
    dds = np.empty(n)
    ruin = 0
    for i in range(n):
        pick = rng.integers(0, k, size=k)
        seq = np.concatenate([groups[j] for j in pick])
        curve = initial_balance + np.cumsum(seq)
        peak = np.maximum.accumulate(np.concatenate([[initial_balance], curve]))[1:]
        dds[i] = float((peak - curve).max())
        finals[i] = float(curve[-1])
        if curve.min() <= 0:
            ruin += 1
    q = lambda a, p: float(np.quantile(a, p))
    return {
        "days": int(k), "paths": int(n),
        "final_p05": q(finals, 0.05), "final_p25": q(finals, 0.25), "final_p50": q(finals, 0.50),
        "final_p75": q(finals, 0.75), "final_p95": q(finals, 0.95),
        "prob_loss": float((finals < initial_balance).mean()),
        "prob_loss_over_25pct": float((finals < initial_balance * 0.75).mean()),
        "prob_ruin_realised": float(ruin / n),
        "max_dd_p50": q(dds, 0.50), "max_dd_p95": q(dds, 0.95), "max_dd_p99": q(dds, 0.99),
    }


def across_windows(base: BacktestConfig, grid: Sequence[dict], labels: Sequence[dict],
                   windows: Dict[str, Tuple[str, str]], n_jobs: Optional[int] = None,
                   store_dir: Optional[str] = None, progress=None) -> pd.DataFrame:
    """
    Run one grid over several windows and put the results side by side.

    Columns are suffixed with the window name (``net_profit@is``, ``net_profit@oos`` ...).
    Use ``rank_agreement`` on the result to see whether the in-sample ranking carries over.
    """
    out: Optional[pd.DataFrame] = None
    lab_cols = list(pd.DataFrame(list(labels)).columns)
    for name, (s, e) in windows.items():
        cfg = base.replace(start=s, end=e)
        df = run_grid(cfg, grid, n_jobs=n_jobs, labels=labels, store_dir=store_dir,
                      progress=(lambda a, b, t, _n=name: progress(_n, a, b, t)) if progress else None)
        met = [c for c in df.columns if c not in lab_cols]
        df = df.rename(columns={c: f"{c}@{name}" for c in met})
        out = df if out is None else pd.concat([out, df[[f"{c}@{name}" for c in met]]], axis=1)
    return out


def rank_agreement(df: pd.DataFrame, a: str, b: str, metric: str = "net_profit",
                   min_baskets: int = 30) -> Dict[str, float]:
    """
    How well does the ranking on window ``a`` predict window ``b``?

    spearman        rank correlation of the metric across all configurations
    top_decile_*    what the best 10% chosen on ``a`` went on to do on ``b``
    """
    ca, cb = f"{metric}@{a}", f"{metric}@{b}"
    ok = (df[f"baskets@{a}"] >= min_baskets) & (df[f"baskets@{b}"] >= min_baskets)
    d = df[ok]
    if len(d) < 5:
        return {"n": int(len(d))}
    ra, rb = d[ca].rank(), d[cb].rank()
    spearman = float(np.corrcoef(ra, rb)[0, 1])
    top = d.nlargest(max(1, len(d) // 10), ca)
    best = d.loc[d[ca].idxmax()]
    return {
        "n": int(len(d)),
        "spearman": spearman,
        f"median_{a}": float(d[ca].median()), f"median_{b}": float(d[cb].median()),
        f"pct_positive_{a}": float((d[ca] > 0).mean() * 100), f"pct_positive_{b}": float((d[cb] > 0).mean() * 100),
        f"top_decile_mean_{a}": float(top[ca].mean()), f"top_decile_mean_{b}": float(top[cb].mean()),
        f"top_decile_pct_positive_{b}": float((top[cb] > 0).mean() * 100),
        f"best_{a}": float(best[ca]), f"best_{a}_then_{b}": float(best[cb]),
    }
