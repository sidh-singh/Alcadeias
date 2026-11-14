"""
Robustness tests: does a result survive things the bot cannot control?

* ``timing_ensemble`` every window under several loop timings (how much of a result is timing luck?)
* ``timing_grid``     a slower loop and order latency, each level under several loop timings
* ``cost_grid``       wider spread and slippage, each level under several loop timings
* ``start_shift``     the same strategy started a few days later (path dependence)
* ``segments``        each sub-period on a fresh balance (is the result stable in time?)
* ``bootstrap``       whole trading days resampled with replacement, re-sized by the bot's unit rule
* ``across_windows``  one grid over several windows + rank agreement between them
                      (in-sample choice vs out-of-sample outcome)

Every function returns a DataFrame so the numbers can be read, plotted or re-tested.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..config import BacktestConfig
from .sweep import run_grid


def _ts(x) -> pd.Timestamp:
    return pd.Timestamp(x)


# ───────────────────────────── loop timing ─────────────────────────────
# One run is one path. The live loop sleeps one second and then spends a varying time talking to
# the terminal, so its polls do not sit on a fixed grid; which tick a poll lands on decides whether
# the bot is inside a basket when a sharp move starts, and a few large baskets decide a quarter.
# A "timing" below is therefore the live cadence (1 s sleep, 0.1 s after an order) with every pass
# taking 0..ENSEMBLE_JITTER_MS longer, drawn from a reproducible sequence. Different seeds can never
# fall back onto the same poll grid (fixed phase offsets can: the grid shifts by 0.1 s per order,
# so runs that started 0.5 s apart end up identical).
ENSEMBLE_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
ENSEMBLE_JITTER_MS = 200


def live_timing(seed: int, jitter_ms: int = ENSEMBLE_JITTER_MS, poll_ms: int = 1000) -> dict:
    """Overrides for one plausible loop timing (see the note above)."""
    return dict(poll_interval_ms=int(poll_ms), poll_jitter_ms=int(jitter_ms), poll_jitter_seed=int(seed),
                open_order_delay_ms=100)


def timing_grid(cfg: BacktestConfig, periods_ms: Sequence[int] = (1000, 1250, 1500, 2000),
                latencies_ms: Sequence[int] = (0, 150, 300, 600, 1000), seeds: Sequence[int] = (1, 2, 3, 4),
                jitter_ms: int = ENSEMBLE_JITTER_MS, n_jobs: int = 2, store_dir: Optional[str] = None) -> pd.DataFrame:
    """
    A slower loop, and a delay between the quote that triggered an order and the quote it fills at.
    Every level is run under several loop timings, so a level is read by its median and range.
    Raw ticks. Rows: test ('poll' / 'latency') x level x seed.
    """
    grid, labels = [], []
    for p in periods_ms:
        for sd in seeds:
            grid.append({**live_timing(sd, jitter_ms, p), "latency_ms": 0})
            labels.append(dict(test="poll", poll_ms=int(p), latency_ms=0, seed=int(sd)))
    for lat in latencies_ms:
        for sd in seeds:
            grid.append({**live_timing(sd, jitter_ms), "latency_ms": int(lat)})
            labels.append(dict(test="latency", poll_ms=1000, latency_ms=int(lat), seed=int(sd)))
    return run_grid(cfg, grid, n_jobs=n_jobs, mode="ticks", labels=labels, store_dir=store_dir)


def timing_ensemble(cfg: BacktestConfig, windows: Dict[str, Tuple[str, str]],
                    seeds: Sequence[int] = ENSEMBLE_SEEDS, jitter_ms: int = ENSEMBLE_JITTER_MS,
                    n_jobs: int = 2, store_dir: Optional[str] = None,
                    overrides: Sequence[dict] = ({},), override_labels: Sequence[dict] = ({},)) -> pd.DataFrame:
    """
    ``cfg`` on every window under each loop timing, raw ticks, a fresh balance each time.
    Rows: (setting x) window x seed; ``overrides`` runs several settings through the same
    timings (``override_labels`` names them).
    """
    out = []
    for name, (a, z) in windows.items():
        grid, labels = [], []
        for ov, lab in zip(overrides, override_labels):
            for sd in seeds:
                grid.append({**ov, **live_timing(sd, jitter_ms)})
                labels.append({**lab, "window": name, "segment": f"{a} → {z}", "seed": int(sd)})
        out.append(run_grid(cfg.replace(start=a, end=z), grid, n_jobs=n_jobs, mode="ticks", labels=labels, store_dir=store_dir))
    return pd.concat(out, ignore_index=True)


def spread_of(df: pd.DataFrame, by: Sequence[str]) -> pd.DataFrame:
    """Median, range and loss / stop-out counts of the runs sharing the ``by`` columns (order kept)."""
    rows = []
    by = list(by)
    for key, g in df.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key)), "runs": int(len(g)),
                     "net_median": float(g["net_profit"].median()), "net_min": float(g["net_profit"].min()),
                     "net_max": float(g["net_profit"].max()), "losing_runs": int((g["net_profit"] < 0).sum()),
                     "stopped_out_runs": int(g["stopped_out"].astype(bool).sum()),
                     "max_dd_pct_median": float(g["max_dd_pct"].median()),
                     "worst_basket": float(g["largest_loss"].min()),
                     "baskets_median": float(g["baskets"].median())})
    return pd.DataFrame(rows)


def ensemble_summary(df: pd.DataFrame, by: Sequence[str] = ()) -> pd.DataFrame:
    """Per (``by`` ...,) window of a ``timing_ensemble``: median, range, how many timings lost money or were stopped out."""
    return spread_of(df, list(by) + ["window", "segment"])


def cost_grid(cfg: BacktestConfig, spread_mults: Sequence[float] = (1.0, 1.25, 1.5, 2.0, 3.0),
              slippages: Optional[Sequence[float]] = None, seeds: Sequence[int] = (1, 2, 3, 4),
              jitter_ms: int = ENSEMBLE_JITTER_MS, n_jobs: int = 2, store_dir: Optional[str] = None) -> pd.DataFrame:
    """
    Transaction-cost stress: the recorded spread scaled up, and adverse slippage on every fill.
    Every level is run under several loop timings (raw ticks), because one path per level would
    show timing luck, not the cost. Rows: test ('spread' / 'slippage') x level x seed.
    """
    if slippages is None:
        # in price units: a few cents on gold, a few dollars on BTC
        slippages = (0.02, 0.05, 0.10) if cfg.symbol.startswith("XAU") else (1.0, 2.5, 5.0)
    grid, labels = [], []
    for m in spread_mults:
        for sd in seeds:
            grid.append({**live_timing(sd, jitter_ms), "spread_mult": float(m)})
            labels.append(dict(test="spread", spread_mult=float(m), slippage=0.0, seed=int(sd)))
    for sl in slippages:
        if sl == 0.0:
            continue
        for sd in seeds:
            grid.append({**live_timing(sd, jitter_ms), "slippage": float(sl)})
            labels.append(dict(test="slippage", spread_mult=1.0, slippage=float(sl), seed=int(sd)))
    return run_grid(cfg, grid, n_jobs=n_jobs, mode="ticks", labels=labels, store_dir=store_dir)


def start_shift(cfg: BacktestConfig, shifts_days: Sequence[float] = (0, 1, 2, 3, 4, 5, 6, 7, 10, 14),
                n_jobs: int = 2, store_dir: Optional[str] = None) -> pd.DataFrame:
    """
    The same configuration started N days later, same end, on raw ticks at the cadence of the
    baseline run (so a shift of 0 is that run). Starts that fall in a closed market give the
    same run as the next open; those repeats are dropped.
    """
    start = _ts(cfg.start)
    grid = [dict(start=str(start + pd.Timedelta(days=float(d))), open_order_delay_ms=100) for d in shifts_days]
    labels = [dict(start_shift_days=float(d)) for d in shifts_days]
    df = run_grid(cfg, grid, n_jobs=n_jobs, mode="ticks", labels=labels, store_dir=store_dir)
    return df.drop_duplicates(subset=["net_profit", "baskets", "max_dd_usd", "largest_loss"]).reset_index(drop=True)


def segments(cfg: BacktestConfig, freq: str = "MS", fixed_days: Optional[int] = None,
             n_jobs: Optional[int] = None, store_dir: Optional[str] = None) -> pd.DataFrame:
    """
    Every sub-period on a fresh balance (per-second replay). ``fixed_days`` cuts equal slices
    instead of calendar months. ``partial`` marks a slice clearly shorter than the nominal one
    (the ends of the window); leave those out when counting winning periods.
    """
    a, z = _ts(cfg.start), _ts(cfg.end)
    if fixed_days:
        edges = list(pd.date_range(a, z, freq=f"{int(fixed_days)}D"))
    else:
        edges = [a] + [d for d in pd.date_range(a, z, freq=freq) if a < d < z]
    if edges[-1] < z:
        edges.append(z)
    grid, labels = [], []
    for s, e in zip(edges[:-1], edges[1:]):
        days = (e - s).total_seconds() / 86400
        if days < 1:
            continue
        nominal = float(fixed_days) if fixed_days else float(s.days_in_month)
        grid.append(dict(start=str(s), end=str(e)))
        labels.append(dict(segment=f"{s:%Y-%m-%d} → {e:%Y-%m-%d}", days=round(days, 1), partial=bool(days < 0.9 * nominal)))
    return run_grid(cfg, grid, n_jobs=n_jobs, labels=labels, store_dir=store_dir)


@njit(cache=True)
def _boot_paths(pnl_u, mae_u, day_start, day_len, picks, account, step_up, unit_max):
    """Final balance, deepest dip below the start and a wiped flag for every resampled path."""
    n, k = picks.shape
    finals = np.empty(n)
    dips = np.empty(n)
    wiped = np.zeros(n, np.uint8)
    for i in range(n):
        bal = account
        low = account
        dead = False
        for j in range(k):
            d = picks[i, j]
            for q in range(day_start[d], day_start[d] + day_len[d]):
                u = 1.0
                if step_up > 0.0:
                    u = float(int(bal // step_up) + 1)
                    if u > unit_max:
                        u = unit_max
                    if u < 1.0:
                        u = 1.0
                worst = bal + u * mae_u[q]
                if worst < low:
                    low = worst
                if worst <= 0.0:
                    dead = True
                    break
                bal += u * pnl_u[q]
                if bal < low:
                    low = bal
                if bal <= 0.0:
                    dead = True
                    break
            if dead:
                break
        if dead:
            bal = 0.0
            low = 0.0
            wiped[i] = 1
        finals[i] = bal
        dips[i] = account - low
    return finals, dips, wiped


def bootstrap(baskets: pd.DataFrame, account: float, step_up: float = 0.0, unit_max: int = 1,
              n: int = 5000, seed: int = 7) -> Dict[str, float]:
    """
    Whole UTC days of baskets drawn WITH replacement (each day's baskets kept together and in
    order, because losses cluster inside a day): in a resampled quarter some days occur twice
    and others not at all. That is not "the same trades in another order" (which could never
    change the final balance); it asks how much the quarter's result depends on which days
    happened to be in it.

    Every basket is re-sized by the bot's own rule as the resampled balance evolves
    (``floor(balance / step_up) + 1`` units, capped at ``unit_max``; ``step_up`` = 0 keeps one
    unit), using its result and its worst floating loss per unit, and a path ends when the
    balance can no longer cover a basket's worst floating loss.
    """
    if len(baskets) == 0:
        return {}
    b = baskets.sort_values("close_time")
    units = np.maximum(b["units"].to_numpy(float), 1.0)
    pnl_u = np.ascontiguousarray(b["pnl"].to_numpy(float) / units)
    mae_u = np.ascontiguousarray(np.minimum(b["mae"].to_numpy(float), 0.0) / units)
    day = b["close_time"].dt.floor("D").to_numpy()
    cut = np.flatnonzero(np.concatenate([[True], day[1:] != day[:-1]]))
    day_start = cut.astype(np.int64)
    day_len = np.diff(np.concatenate([cut, [len(b)]])).astype(np.int64)
    k = len(day_start)
    picks = np.random.default_rng(seed).integers(0, k, size=(n, k)).astype(np.int64)
    finals, dips, wiped = _boot_paths(pnl_u, mae_u, day_start, day_len, picks, float(account), float(step_up), float(unit_max))
    q = lambda a, p: float(np.quantile(a, p))
    return {
        "days": int(k), "paths": int(n),
        "final_p05": q(finals, 0.05), "final_p25": q(finals, 0.25), "final_p50": q(finals, 0.50),
        "final_p75": q(finals, 0.75), "final_p95": q(finals, 0.95),
        "prob_loss": float((finals < account).mean()),
        "prob_loss_over_25pct": float((finals < account * 0.75).mean()),
        "prob_wiped": float(wiped.mean()),
        "dip_p50": q(dips, 0.50), "dip_p95": q(dips, 0.95),
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
