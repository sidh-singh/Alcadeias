"""
The experiment pipeline behind the committed results.

    python -m backtesting reproduce                      # everything, for this branch's variant
    python -m backtesting reproduce --only baseline sweeps

Stages (each writes plain CSV / JSON under ``backtest_results/`` and is skipped when its
output already exists, unless ``--force``):

  quality     data-quality report per symbol
  baseline    the live configuration, raw-tick replay with the live loop cadence, HTML report
  long        the same configuration over the longest history available
  sweeps      which timeframes should drive OPEN / FORCE-CLOSE / BOOK -- RSI and MACD together
              and separately -- on three disjoint three-month windows
  levers      one-at-a-time sensitivity of every other parameter + structural what-ifs
  improve     hypothesis-driven what-if packages aimed at the flaws the baseline exposed
  holdout     the whole timeframe grid again on the two hold-out quarters
  candidates  a short list of settings (timeframes x risk fixes) on all five quarters, and on
              a real $2,000 account over the whole fifteen months
  robust      loop timing, order latency, costs, start date, sub-periods, bootstrap

Windows. ``IS`` is the three months the owner asked for. ``OOS1`` and ``OOS2`` are the two
three-month blocks before it. A setting is only interesting if it holds up on windows it
was not chosen on. ``HO2`` and ``HO1`` are two still earlier quarters kept as a hold-out:
nothing is ever selected on them, they are only used to test what was selected.

Sweeps run with a fixed unit of 1 (0.01 lot entry, no balance auto-step) on a balance too
large to be stopped out. The auto-step doubles every lot once the balance passes $2,500,
which makes results path-dependent and would bury the effect of the parameter being
studied; and a stop-out would hide everything after it. Each row therefore reports the
P/L of one 0.01-lot unit over the whole window plus ``max_loss_from_start`` -- if that
reaches $2,000 the owner's account would have been wiped out in that window. Baseline /
long runs use the live auto-step and the real $2,000 exactly as deployed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .analysis import robustness, sweep
from .analysis.metrics import score_row
from .config import BacktestConfig, FIBO, REPO_ROOT
from .engine.fast import run

WINDOWS: Dict[str, Tuple[str, str]] = {
    "IS": ("2026-08-13", "2026-11-13"),
    "OOS1": ("2026-05-13", "2026-08-13"),
    "OOS2": ("2026-02-13", "2026-05-13"),
}
# Hold-out: two earlier quarters that play NO part in choosing anything. Every setting that
# looks good on the three windows above was picked with hindsight on them; these two say
# whether such a pick carries over to data it has never seen.
HOLDOUT: Dict[str, Tuple[str, str]] = {
    "HO2": ("2025-11-13", "2026-02-13"),
    "HO1": ("2025-08-13", "2025-11-13"),
}
ALL_WINDOWS: Dict[str, Tuple[str, str]] = {**WINDOWS, **HOLDOUT}
LONG_WINDOW = ("2025-08-13", "2026-11-13")          # all five quarters in one run
SYMBOLS = ("XAUUSDm", "BTCUSDm")
# Sweeps, levers and packages run a fixed 0.01-lot unit on a balance too large to be stopped
# out, so every configuration is measured over the *whole* window (a stop-out would hide
# whatever came after it). Whether the owner's $2,000 account would have survived is then
# read off the deepest dip below the starting balance: ``max_loss_from_start >= ACCOUNT``.
SWEEP_BALANCE = 1_000_000.0
ACCOUNT = 2000.0
UNIVERSE = ["M1", "M5", "M15", "M30", "H1", "H4"]


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def live_config(symbol: str, live_root: Path = REPO_ROOT, **kw) -> BacktestConfig:
    return BacktestConfig.live(symbol, repo_root=live_root, **kw)


def _progress(tag: str):
    return lambda name, a, b, t: _log(f"    {tag} {name}: {a}/{b} ({t:.0f}s)")


# ───────────────────────────── stages ─────────────────────────────

def stage_quality(out: Path, symbols: Sequence[str], force: bool = False) -> None:
    from .data import quality
    d = out / "data_quality"
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        p = d / f"{sym}.json"
        if p.exists() and not force:
            continue
        q = quality.quality_report(sym, LONG_WINDOW[0], LONG_WINDOW[1])
        p.write_text(json.dumps(q, indent=2, default=str))
        _log("quality\n" + quality.format_quality(q))


def stage_baseline(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                   window: Tuple[str, str] = WINDOWS["IS"], name: str = "baseline", mode: str = "ticks",
                   closeups: bool = True) -> None:
    from .viz.report import build_report, ensure_plotly_js
    ensure_plotly_js(out / "assets")
    for sym in symbols:
        d = out / name / sym
        if (d / "summary.json").exists() and not force:
            continue
        cfg = live_config(sym, live_root, start=window[0], end=window[1])
        if mode == "ticks":
            cfg = cfg.replace(open_order_delay_ms=100)   # the 0.1 s sleep inside the live buy()/sell()
        t0 = time.time()
        res = run(cfg, mode=mode)
        s = res.summary()
        _log(f"{name} {cfg.variant} {sym} [{mode}] net {s['net_profit']:+.2f}  maxDD {s['max_drawdown_usd']:.2f} "
             f"({s['max_drawdown_pct']:.1f}%)  baskets {s['baskets']}  win {s.get('win_rate_pct')}%  "
             f"PF {s.get('profit_factor')}  ({time.time() - t0:.0f}s)")
        build_report(res, d, closeups=closeups, plotly_src="../../assets/plotly.min.js",
                     tfs=("M15", "H1", "H4") if name == "baseline" else ("H1", "H4"))
        # the same configuration without the balance auto-step, for a like-for-like per-unit read
        r1 = run(cfg.replace(fixed_units=1), mode="sec", light=True)
        (d / "fixed_unit.json").write_text(json.dumps(score_row(r1), indent=2))


def joint_grid(variant: str) -> Tuple[List[dict], List[dict]]:
    # the BOOK timeframe is swept separately (split-book); here it stays at the live setting
    return sweep.grid_joint_timeframes(UNIVERSE, "hedging")


def stage_sweeps(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                 n_jobs: Optional[int] = None, windows: Dict[str, Tuple[str, str]] = WINDOWS) -> None:
    d = out / "sweeps"
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        base = live_config(sym, live_root, fixed_units=1, initial_balance=SWEEP_BALANCE)
        variant = base.variant
        plans: Dict[str, Tuple[List[dict], List[dict]]] = {
            "timeframes": joint_grid(variant),
            "split_open": sweep.grid_split_indicator(UNIVERSE, "hedging", fc_tfs=list(base.fc_weights)),
            "split_fc": sweep.grid_split_exit(UNIVERSE, variant, "fc"),
        }
        if variant == "netting":
            plans["split_book"] = sweep.grid_split_exit(UNIVERSE, variant, "book")
            plans["book_joint"] = _book_joint_grid()
        for kind, (grid, labels) in plans.items():
            p = d / f"{sym}_{kind}.csv"
            if p.exists() and not force:
                continue
            _log(f"sweep {variant} {sym} {kind}: {len(grid)} configurations x {len(windows)} windows")
            t0 = time.time()
            df = robustness.across_windows(base, grid, labels, windows, n_jobs=n_jobs,
                                           progress=_progress(f"{sym} {kind}"))
            df.to_csv(p, index=False)
            agree = {f"{a}->{b}": robustness.rank_agreement(df, a, b)
                     for a in windows for b in windows if a != b}
            (d / f"{sym}_{kind}_agreement.json").write_text(json.dumps(agree, indent=2))
            _log(f"  done in {time.time() - t0:.0f}s -> {p.name}")


def _book_joint_grid() -> Tuple[List[dict], List[dict]]:
    """Netting: BOOK timeframe x FORCE-CLOSE timeframe (the two exits interact), open as live."""
    grid, labels = [], []
    for bk in UNIVERSE:
        for fc in UNIVERSE:
            for lvl in ("half", "full"):
                grid.append(dict(book_weights={bk: 1}, book_s=1.0, fc_weights={fc: 1}, entry_agree_s=2.0,
                                 force_close_s=1.0 if lvl == "half" else 2.0))
                labels.append(dict(book=bk, fc=fc, fc_level=lvl))
    return grid, labels


def lever_grid(base: BacktestConfig) -> Tuple[List[dict], List[dict]]:
    """Every other knob, one at a time, plus structural what-ifs (all relative to the live settings)."""
    xau = base.symbol.startswith("XAU")
    gap_unit = 1.0 if xau else 100.0          # $1 of gold / $100 of BTC = $1 P/L on 0.01 lot
    params: Dict[str, list] = {
        "entry_s": [1, 2, 3, 4],
        "entry_agree_s": [0, 1, 2],
        "force_close_s": [1, 2],
        "ladder_s": [1, 2, 3, 4, 99],
        "rsi_oversold": [20, 25, 30, 35, 40],
        "rsi_overbought": [60, 65, 70, 75, 80],
        "rsi_length": [7, 9, 14, 21, 28],
        "peak_lookback": [8, 12, 20, 30, 50],
        "pivot_width": [1, 2, 3, 4],
        "rsi_peak_ob": [55, 60, 65, 70],
        "rsi_peak_os": [30, 35, 40, 45],
        "reentry_cooldown_s": [0, 60, 300, 900, 1800, 3600],
        "max_adds": [0, 1, 2, 3, 4, 5],
        "@macd": [{"name": f"{f},{s},{g}", "set": dict(macd_fast=f, macd_slow=s, macd_signal=g)}
                  for f, s, g in ((5, 13, 4), (8, 17, 9), (12, 26, 9), (19, 39, 9), (24, 52, 18))],
        "@rsi_bands": [{"name": f"{lo}/{hi}", "set": dict(rsi_oversold=lo, rsi_overbought=hi)}
                       for lo, hi in ((20, 80), (25, 75), (30, 70), (35, 65), (40, 60))],
        "@ladder_shape": [
            {"name": "fibonacci 1,2,3,5,8,13 (live)", "set": dict(ladder_multipliers=list(FIBO))},
            {"name": "flat 1,1,1,1,1,1", "set": dict(ladder_multipliers=[1] * 12)},
            {"name": "linear 1,2,3,4,5,6", "set": dict(ladder_multipliers=list(range(1, 13)))},
            {"name": "double 1,2,4,8,16,32", "set": dict(ladder_multipliers=[2 ** i for i in range(12)])},
        ],
        # which timeframe's RSI releases each add (live: 1st add M1, 2nd M5, 3rd M15, 4th H1, 5th H4); depth kept at five
        "@ladder_timeframes": [
            {"name": "M1,M5,M15,H1,H4 (live)", "set": dict()},
            {"name": "M5,M15,H1,H4,H4", "set": dict(ladder_tfs=["M5", "M15", "H1", "H4", "H4"])},
            {"name": "M15,H1,H4,H4,H4", "set": dict(ladder_tfs=["M15", "H1", "H4", "H4", "H4"])},
            {"name": "H4,H1,M15,M5,M1", "set": dict(ladder_tfs=["H4", "H1", "M15", "M5", "M1"])},
            {"name": "all five on M1", "set": dict(ladder_tfs=["M1"] * 5)},
            {"name": "all five on M5", "set": dict(ladder_tfs=["M5"] * 5)},
            {"name": "all five on M15", "set": dict(ladder_tfs=["M15"] * 5)},
            {"name": "all five on H1", "set": dict(ladder_tfs=["H1"] * 5)},
        ],
        "@ladder_min_gap": [{"name": f"${g:g} per 0.01 lot", "set": dict(ladder_min_gap=g * gap_unit)}
                            for g in (0, 1, 2, 3, 5, 8)],
        "@signals_on": [
            {"name": "forming bar (live)", "set": dict()},
            {"name": "closed bars: slopes", "set": dict(slope_on_closed_bars=True)},
            {"name": "closed bars: slopes + ladder RSI", "set": dict(slope_on_closed_bars=True, ladder_on_closed_bars=True)},
        ],
        "@ladder_min_interval": [{"name": f"{m} min", "set": dict(ladder_min_interval_s=m * 60.0)}
                                 for m in (0, 1, 5, 15, 30, 60)],
        "@max_hold": [{"name": "none (live)", "set": dict(max_hold_s=0.0)}] + [
            {"name": f"{h:g} h", "set": dict(max_hold_s=h * 3600.0)} for h in (0.25, 0.5, 1, 2, 4, 8)],
        "fc_confirm_s": [0, 10, 30, 60, 120, 300],
        "entry_confirm_s": [0, 10, 30, 60, 120, 300],
        "min_hold_s": [0, 30, 60, 300, 900],
        "@stop_loss": [{"name": "none (live)", "set": dict(stop_loss_usd_per_unit=None)}] + [
            {"name": f"${x} per unit", "set": dict(stop_loss_usd_per_unit=float(x))} for x in (3, 5, 10, 20, 40, 80)],
        "@side": [
            {"name": "both (live)", "set": dict()},
            {"name": "long only", "set": dict(allow_short=False)},
            {"name": "short only", "set": dict(allow_long=False)},
        ],
        "@exit_mix": [
            {"name": "force-close off", "set": dict(force_close_enabled=False)},
        ],
    }
    if base.book_enabled:
        params["book_s"] = [1, 2]
        params["profit_protect_usd_per_unit"] = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
        params["@exit_mix"] += [
            {"name": "book + $1 target", "set": dict(target_usd_per_unit=1.0)},
            {"name": "book + $3 target", "set": dict(target_usd_per_unit=3.0)},
            {"name": "book + $10 target", "set": dict(target_usd_per_unit=10.0)},
            {"name": "target $1 only (hedging exit)", "set": dict(target_usd_per_unit=1.0, book_enabled=False)},
        ]
    else:
        params["target_usd_per_unit"] = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
        params["@exit_mix"] += [
            {"name": "target + slope book (netting exit too)", "set": dict(book_enabled=True)},
            {"name": "slope book only (netting exit)", "set": dict(book_enabled=True, target_usd_per_unit=None)},
        ]
    return sweep.grid_one_at_a_time(params)


def stage_levers(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                 n_jobs: Optional[int] = None, windows: Dict[str, Tuple[str, str]] = WINDOWS) -> None:
    d = out / "levers"
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        p = d / f"{sym}.csv"
        if p.exists() and not force:
            continue
        base = live_config(sym, live_root, fixed_units=1, initial_balance=SWEEP_BALANCE)
        grid, labels = lever_grid(base)
        _log(f"levers {base.variant} {sym}: {len(grid)} configurations x {len(windows)} windows")
        df = robustness.across_windows(base, grid, labels, windows, n_jobs=n_jobs, progress=_progress(f"{sym} levers"))
        df.to_csv(p, index=False)


def stage_robust(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                 n_jobs: Optional[int] = None, window: Tuple[str, str] = WINDOWS["IS"]) -> None:
    for sym in symbols:
        d = out / "robustness" / sym
        d.mkdir(parents=True, exist_ok=True)
        cfg = live_config(sym, live_root, start=window[0], end=window[1])
        todo = {
            "costs.csv": lambda: robustness.cost_grid(cfg, n_jobs=n_jobs),
            "start_shift.csv": lambda: robustness.start_shift(cfg, n_jobs=n_jobs),
            "segments_monthly.csv": lambda: robustness.segments(
                live_config(sym, live_root, start=LONG_WINDOW[0], end=LONG_WINDOW[1]), n_jobs=n_jobs),
            "segments_weekly.csv": lambda: robustness.segments(cfg, fixed_days=7, n_jobs=n_jobs),
            "segments_quarterly.csv": lambda: _quarters(live_config(sym, live_root), n_jobs),
            "timing.csv": lambda: robustness.timing_grid(cfg, n_jobs=2),
        }
        for name, fn in todo.items():
            p = d / name
            if p.exists() and not force:
                continue
            t0 = time.time()
            df = fn()
            df.to_csv(p, index=False)
            _log(f"robust {cfg.variant} {sym} {name} ({time.time() - t0:.0f}s)")
        p = d / "bootstrap.json"
        if not p.exists() or force:
            res = run(cfg, light=True)
            r1 = run(cfg.replace(fixed_units=1), light=True)
            p.write_text(json.dumps({"live_units": robustness.bootstrap(res.baskets, cfg.initial_balance),
                                     "fixed_unit_1": robustness.bootstrap(r1.baskets, cfg.initial_balance)}, indent=2))
            _log(f"robust {cfg.variant} {sym} bootstrap")


def package_grid(base: BacktestConfig) -> Tuple[List[dict], List[dict]]:
    """
    Hypothesis-driven what-if packages. Each one answers a flaw the baseline exposed
    (the ladder that deploys at one price, the missing price-based exit, the fixed tiny
    target on a growing basket); none of them was tuned on the data.
    """
    xau = base.symbol.startswith("XAU")
    px = 1.0 if xau else 100.0     # price move worth $1 on a 0.01 lot
    hedging = not base.book_enabled
    P: List[Tuple[str, dict]] = [
        ("live settings", {}),
        ("no ladder", dict(max_adds=0)),
        ("ladder: 1 add only", dict(max_adds=1)),
        ("ladder: 2 adds only", dict(max_adds=2)),
        ("ladder: adds >= $3 apart", dict(ladder_min_gap=3 * px)),
        ("ladder: adds >= $5 apart", dict(ladder_min_gap=5 * px)),
        ("ladder: adds >= 15 min apart", dict(ladder_min_interval_s=900.0)),
        ("ladder: adds >= $3 and >= 5 min apart", dict(ladder_min_gap=3 * px, ladder_min_interval_s=300.0)),
        ("ladder: flat lots 1,1,1,1,1,1", dict(ladder_multipliers=[1] * 12)),
        ("ladder: flat lots, adds >= $3 apart", dict(ladder_multipliers=[1] * 12, ladder_min_gap=3 * px)),
        ("stop: $10 per unit", dict(stop_loss_usd_per_unit=10.0)),
        ("stop: $20 per unit", dict(stop_loss_usd_per_unit=20.0)),
        ("stop: $40 per unit", dict(stop_loss_usd_per_unit=40.0)),
        ("stop: $80 per unit", dict(stop_loss_usd_per_unit=80.0)),
        ("time stop: 1 h", dict(max_hold_s=3600.0)),
        ("time stop: 4 h", dict(max_hold_s=4 * 3600.0)),
        ("no ladder + stop $5", dict(max_adds=0, stop_loss_usd_per_unit=5.0)),
        ("no ladder + stop $10", dict(max_adds=0, stop_loss_usd_per_unit=10.0)),
        ("no ladder + stop $20", dict(max_adds=0, stop_loss_usd_per_unit=20.0)),
        ("2 adds >= $3 apart + stop $20", dict(max_adds=2, ladder_min_gap=3 * px, stop_loss_usd_per_unit=20.0)),
        ("adds >= $3 apart + stop $40", dict(ladder_min_gap=3 * px, stop_loss_usd_per_unit=40.0)),
        ("adds >= $5 apart + stop $80", dict(ladder_min_gap=5 * px, stop_loss_usd_per_unit=80.0)),
        ("flat lots, >= $3 apart + stop $20", dict(ladder_multipliers=[1] * 12, ladder_min_gap=3 * px,
                                                   stop_loss_usd_per_unit=20.0)),
        ("signals on closed bars", dict(slope_on_closed_bars=True, ladder_on_closed_bars=True)),
        ("closed bars + no ladder", dict(slope_on_closed_bars=True, ladder_on_closed_bars=True, max_adds=0)),
        ("closed bars + no ladder + stop $10", dict(slope_on_closed_bars=True, ladder_on_closed_bars=True,
                                                    max_adds=0, stop_loss_usd_per_unit=10.0)),
        ("force-close needs 60 s confirmation", dict(fc_confirm_s=60.0)),
        ("cooldown 30 min", dict(reentry_cooldown_s=1800.0)),
    ]
    if hedging:
        P += [
            ("target: $1 per 0.01 lot held", dict(target_per_lot=True)),
            ("target per lot + adds >= $3 apart", dict(target_per_lot=True, ladder_min_gap=3 * px)),
            ("target per lot + adds >= $3 apart + stop $40", dict(target_per_lot=True, ladder_min_gap=3 * px,
                                                                  stop_loss_usd_per_unit=40.0)),
            ("no ladder, target $2", dict(max_adds=0, target_usd_per_unit=2.0)),
            ("no ladder, target $3, stop $10", dict(max_adds=0, target_usd_per_unit=3.0, stop_loss_usd_per_unit=10.0)),
            ("no ladder, target $5, stop $10", dict(max_adds=0, target_usd_per_unit=5.0, stop_loss_usd_per_unit=10.0)),
            ("no ladder, slope book instead of target", dict(max_adds=0, target_usd_per_unit=None, book_enabled=True)),
        ]
    else:
        P += [
            ("no ladder + $3 target on top of the book", dict(max_adds=0, target_usd_per_unit=3.0)),
            ("no ladder + protect $3", dict(max_adds=0, profit_protect_usd_per_unit=3.0)),
            ("no ladder + stop $10 + protect $3", dict(max_adds=0, stop_loss_usd_per_unit=10.0,
                                                       profit_protect_usd_per_unit=3.0)),
            ("no ladder, $1 target instead of the book", dict(max_adds=0, target_usd_per_unit=1.0, book_enabled=False)),
        ]
    return [ov for _, ov in P], [dict(package=name) for name, _ in P]


def stage_improve(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                  n_jobs: Optional[int] = None, windows: Dict[str, Tuple[str, str]] = WINDOWS) -> None:
    d = out / "packages"
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        p = d / f"{sym}.csv"
        if p.exists() and not force:
            continue
        base = live_config(sym, live_root, fixed_units=1, initial_balance=SWEEP_BALANCE)
        grid, labels = package_grid(base)
        _log(f"packages {base.variant} {sym}: {len(grid)} configurations x {len(windows)} windows")
        df = robustness.across_windows(base, grid, labels, windows, n_jobs=n_jobs, progress=_progress(f"{sym} packages"))
        df.to_csv(p, index=False)


def _quarters(cfg: BacktestConfig, n_jobs: Optional[int]) -> pd.DataFrame:
    """The live configuration on each of the five quarters, a fresh $2,000 every time."""
    order = sorted(ALL_WINDOWS.items(), key=lambda kv: kv[1][0])
    base = cfg.replace(start=LONG_WINDOW[0], end=LONG_WINDOW[1])
    grid = [dict(start=a, end=z) for _, (a, z) in order]
    labels = [dict(window=k, segment=f"{a} → {z}", role="hold-out" if k in HOLDOUT else "analysed") for k, (a, z) in order]
    return sweep.run_grid(base, grid, n_jobs=n_jobs, labels=labels)


def stage_holdout(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                  n_jobs: Optional[int] = None) -> None:
    """The timeframe grid on the two hold-out quarters (same grid, same fixed unit, never used to choose)."""
    d = out / "sweeps"
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        p = d / f"{sym}_timeframes_holdout.csv"
        if p.exists() and not force:
            continue
        base = live_config(sym, live_root, fixed_units=1, initial_balance=SWEEP_BALANCE)
        grid, labels = joint_grid(base.variant)
        _log(f"holdout {base.variant} {sym}: {len(grid)} configurations x {len(HOLDOUT)} windows")
        df = robustness.across_windows(base, grid, labels, HOLDOUT, n_jobs=n_jobs, progress=_progress(f"{sym} holdout"))
        df.to_csv(p, index=False)


def candidate_grid(base: BacktestConfig) -> Tuple[List[dict], List[dict]]:
    """
    A short list of settings to take to a demo account: the timeframe families that held up
    best in the sweeps, each with and without the fixes for the ladder.

    They were chosen AFTER looking at the three analysed windows, so those windows flatter
    them. The two hold-out quarters are the honest test.
    """
    xau = base.symbol.startswith("XAU")
    px = 1.0 if xau else 100.0
    netting = base.book_enabled
    tf_sets: List[Tuple[str, dict]] = [
        ("live timeframes", {}),
        ("A: H4 must agree - open H4+M15 (both aligned), close on M15",
         dict(open_weights={"H4": 1, "M15": 1}, entry_s=4.0, fc_weights={"M15": 1}, entry_agree_s=2.0, force_close_s=1.0)),
        ("B: H4 gate - open M5+M15, H4 must agree, close when H4 turns",
         dict(open_weights={"M15": 1, "M5": 1}, entry_s=2.0, fc_weights={"H4": 1}, entry_agree_s=2.0, force_close_s=2.0)),
        ("C: open on H4 alone, close on M15",
         dict(open_weights={"H4": 1}, entry_s=2.0, fc_weights={"M15": 1}, entry_agree_s=2.0,
              force_close_s=2.0 if netting else 1.0)),
        ("D: slow - open H1+H4 (both aligned), close on H1",
         dict(open_weights={"H4": 1, "H1": 1}, entry_s=4.0, fc_weights={"H1": 1}, entry_agree_s=2.0, force_close_s=1.0)),
        ("E: live timeframes, H1 must fully agree",
         dict(entry_s=4.0)),
    ]
    risk: List[Tuple[str, dict]] = [
        ("live ladder", {}),
        ("no ladder", dict(max_adds=0)),
        ("2 adds, >= $3 apart", dict(max_adds=2, ladder_min_gap=3 * px)),
    ]
    grid, labels = [], []
    for tname, tov in tf_sets:
        for rname, rov in risk:
            grid.append({**tov, **rov})
            labels.append(dict(candidate=f"{tname} · {rname}", timeframes=tname, ladder=rname))
    extras: List[Tuple[str, dict]] = [
        ("live timeframes · no ladder, 1 h cooldown", dict(max_adds=0, reentry_cooldown_s=3600.0)),
        ("live timeframes · closed-bar signals, no ladder", dict(slope_on_closed_bars=True, ladder_on_closed_bars=True, max_adds=0)),
    ]
    for name, ov in extras:
        grid.append(ov)
        labels.append(dict(candidate=name, timeframes=name.split(" · ")[0], ladder=name.split(" · ")[1]))
    return grid, labels


def stage_candidates(out: Path, symbols: Sequence[str], live_root: Path, force: bool = False,
                     n_jobs: Optional[int] = None) -> None:
    d = out / "candidates"
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        p = d / f"{sym}.csv"
        if not p.exists() or force:
            base = live_config(sym, live_root, fixed_units=1, initial_balance=SWEEP_BALANCE)
            grid, labels = candidate_grid(base)
            _log(f"candidates {base.variant} {sym}: {len(grid)} configurations x {len(ALL_WINDOWS)} windows")
            df = robustness.across_windows(base, grid, labels, ALL_WINDOWS, n_jobs=n_jobs,
                                           progress=_progress(f"{sym} candidates"))
            df.to_csv(p, index=False)
        p = d / f"{sym}_account.csv"
        if not p.exists() or force:
            # the same settings on the real account: $2,000, unit auto-step, all fifteen months in one go
            acct = live_config(sym, live_root, start=LONG_WINDOW[0], end=LONG_WINDOW[1])
            grid, labels = candidate_grid(acct)
            df = sweep.run_grid(acct, grid, n_jobs=n_jobs, labels=labels)
            df.to_csv(p, index=False)
            _log(f"candidates {acct.variant} {sym}: real-account runs over {LONG_WINDOW[0]} → {LONG_WINDOW[1]}")


STAGES = ("quality", "baseline", "long", "sweeps", "levers", "improve", "holdout", "candidates", "robust")


def reproduce(out: Path, symbols: Sequence[str] = SYMBOLS, live_root: Path = REPO_ROOT,
              only: Optional[Sequence[str]] = None, force: bool = False, n_jobs: Optional[int] = None) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stages = [s for s in STAGES if not only or s in only]
    t0 = time.time()
    for st in stages:
        _log(f"== stage {st}")
        if st == "quality":
            stage_quality(out, symbols, force)
        elif st == "baseline":
            stage_baseline(out, symbols, live_root, force)
        elif st == "long":
            stage_baseline(out, symbols, live_root, force, window=LONG_WINDOW, name="long", mode="sec", closeups=False)
        elif st == "sweeps":
            stage_sweeps(out, symbols, live_root, force, n_jobs)
        elif st == "levers":
            stage_levers(out, symbols, live_root, force, n_jobs)
        elif st == "improve":
            stage_improve(out, symbols, live_root, force, n_jobs)
        elif st == "holdout":
            stage_holdout(out, symbols, live_root, force, n_jobs)
        elif st == "candidates":
            stage_candidates(out, symbols, live_root, force, n_jobs)
        elif st == "robust":
            stage_robust(out, symbols, live_root, force, n_jobs)
    _log(f"all stages done in {(time.time() - t0) / 60:.1f} min -> {out}")
