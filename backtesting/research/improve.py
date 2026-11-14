"""
The improvement search for the hedging variant (see IMPROVEMENT.md at the top of the repository).

    python -m backtesting.research.improve stage1   XAUUSDm [jobs]   # 135 designs x 5 quarters, one fixed 0.01-lot unit, per-second replay
    python -m backtesting.research.improve stage1b  XAUUSDm [jobs]   # 56 designs: exit sizes around the trend-filter family
    python -m backtesting.research.improve validate XAUUSDm [jobs]   # the short list on raw ticks: 8 loop timings x 5 quarters, real $2,000
    python -m backtesting.research.improve report   XAUUSDm          # print the tables from the files written above

Everything is written to ``backtest_results/improve/``. Designs are chosen on the three analysed
quarters only; the two hold-out quarters and the raw-tick runs under random loop timings are the test.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

from .. import experiments as E
from ..analysis import robustness
from ..config import REPO_ROOT

OUT = REPO_ROOT / "backtest_results" / "improve"


def grid_stage1(sym):
    px = 1.0 if sym.startswith("XAU") else 100.0
    trends = [("no trend filter", {}), ("with H4 trend", dict(trend_tf="H4")), ("with H1 trend", dict(trend_tf="H1"))]
    ladders = [("no ladder", dict(max_adds=0)),
               ("2 flat adds, 5 apart", dict(max_adds=2, ladder_multipliers=[1, 1, 1], ladder_min_gap=5 * px))]
    exits = [("T1", dict(target_usd_per_unit=1.0)), ("T3", dict(target_usd_per_unit=3.0)), ("T5", dict(target_usd_per_unit=5.0))]
    for t, s in ((3, 10), (5, 10), (10, 10), (10, 20)):
        exits.append((f"T{t} S{s}", dict(target_usd_per_unit=float(t), stop_loss_usd_per_unit=float(s))))
        exits.append((f"T{t} S{s} noFC", dict(target_usd_per_unit=float(t), stop_loss_usd_per_unit=float(s), force_close_enabled=False)))
    cools = [("", {}), (" +1h after loss", dict(loss_cooldown_s=3600.0))]
    grid, labels = [dict(), dict(trend_tf="H4"), dict(trend_tf="H1")], [dict(name="LIVE"), dict(name="LIVE + with H4 trend"), dict(name="LIVE + with H1 trend")]
    for tn, tv in trends:
        for ln, lv in ladders:
            for en, ev in exits:
                for cn, cv in cools:
                    grid.append({**tv, **lv, **ev, **cv}); labels.append(dict(name=f"{tn} | {ln} | {en}{cn}"))
    return grid, labels


def grid_stage1b(sym):
    px = 1.0 if sym.startswith("XAU") else 100.0
    cap = 0.5 if sym.startswith("XAU") else 30.0            # about twice the usual spread: only spikes are refused
    grid, labels = [], []
    for tn, tv in (("with H1 trend", dict(trend_tf="H1")), ("with H4 trend", dict(trend_tf="H4"))):
        for t, s in ((5, 10), (10, 10), (10, 20), (15, 15), (20, 20), (20, 40), (30, 30)):
            for cn, cs in (("1h", 3600.0), ("4h", 14400.0)):
                for sn, sv in (("", {}), (" spread cap", dict(entry_max_spread=cap))):
                    grid.append({**tv, "max_adds": 0, "target_usd_per_unit": float(t), "stop_loss_usd_per_unit": float(s),
                                 "force_close_enabled": False, "loss_cooldown_s": cs, **sv})
                    labels.append(dict(name=f"{tn} | no ladder | T{t} S{s} noFC +{cn} after loss{sn}"))
    return grid, labels


# the designs taken to the raw-tick validation: the live settings, the single change that matters most on gold,
# and the leading designs of the two grids (the same list for both symbols)
VALIDATE_1 = ["LIVE", "LIVE + with H4 trend",
              "with H1 trend | no ladder | T10 S20 noFC +1h after loss", "with H4 trend | no ladder | T10 S20 noFC +1h after loss",
              "with H1 trend | no ladder | T5 S10 noFC +1h after loss", "no trend filter | no ladder | T10 S10 noFC",
              "no trend filter | 2 flat adds, 5 apart | T10 S10 noFC", "with H4 trend | no ladder | T10 S20 noFC"]
VALIDATE_1B = ["with H1 trend | no ladder | T20 S20 noFC +4h after loss", "with H1 trend | no ladder | T20 S40 noFC +4h after loss",
               "with H4 trend | no ladder | T20 S20 noFC +4h after loss", "with H1 trend | no ladder | T10 S20 noFC +4h after loss"]


def design(sym: str, name: str) -> dict:
    """The configuration overrides of a design, by its name in the grids."""
    for fn in (grid_stage1, grid_stage1b):
        grid, labels = fn(sym)
        for g, l in zip(grid, labels):
            if l["name"] == name:
                return g
    raise KeyError(name)


def run_stage(sym: str, tag: str, jobs: int = 4) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    grid, labels = (grid_stage1 if tag == "stage1" else grid_stage1b)(sym)
    base = E.live_config(sym, fixed_units=1, initial_balance=E.SWEEP_BALANCE)
    t0 = time.time()
    df = robustness.across_windows(base, grid, labels, E.ALL_WINDOWS, n_jobs=jobs)
    df.to_csv(OUT / f"{tag}_{sym}.csv", index=False)
    print(f"{sym}: {len(grid)} designs x {len(E.ALL_WINDOWS)} quarters in {time.time() - t0:.0f}s")


def validate(sym: str, jobs: int = 4) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    names = VALIDATE_1 + VALIDATE_1B
    t0 = time.time()
    df = robustness.timing_ensemble(E.live_config(sym), dict(sorted(E.ALL_WINDOWS.items(), key=lambda kv: kv[1][0])), n_jobs=jobs,
                                    overrides=[design(sym, n) for n in names], override_labels=[dict(name=n) for n in names])
    df.to_csv(OUT / f"validate_{sym}.csv", index=False)
    print(f"{sym}: {len(df)} raw-tick quarter-runs in {time.time() - t0:.0f}s")


def report_grid(sym: str, tag: str = "stage1", top: int = 12) -> None:
    d = pd.read_csv(OUT / f"{tag}_{sym}.csv")
    A, H, ALL = ["OOS2", "OOS1", "IS"], ["HO1", "HO2"], ["HO1", "HO2", "OOS2", "OOS1", "IS"]
    for w in ALL: d[w] = d[f"net_profit@{w}"]
    d["tot3"] = d[A].sum(axis=1); d["ho2"] = d[H].sum(axis=1); d["tot5"] = d[ALL].sum(axis=1); d["min5"] = d[ALL].min(axis=1)
    d["wiped3"] = sum(d[f"acct_wiped@{w}"].astype(bool).astype(int) for w in A); d["wiped5"] = sum(d[f"acct_wiped@{w}"].astype(bool).astype(int) for w in ALL)
    d["dip"] = d[[f"acct_dip@{w}" for w in ALL]].max(axis=1); d["worst"] = d[[f"largest_loss@{w}" for w in ALL]].min(axis=1)
    d["n/q"] = d[[f"baskets@{w}" for w in ALL]].mean(axis=1); d["pos5"] = (d[ALL] > 0).sum(axis=1)
    cols = ["name"] + ALL + ["tot3", "ho2", "tot5", "pos5", "wiped5", "dip", "worst", "n/q"]
    pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 62)
    show = lambda t: print(t[cols].round(0).to_string(index=False))
    print(f"## {sym}: net P/L per quarter of one fixed 0.01-lot unit (per-second replay); dip = deepest the replayed $2,000 account stood below its start; worst = worst basket")
    show(d[d["name"].str.startswith("LIVE")])
    sel = d[(d["wiped3"] == 0) & ~d["name"].str.startswith("LIVE")].sort_values("tot3", ascending=False)
    print(f"\nchosen on the three analysed quarters only (tot3), {len(sel)} of {len(d)} never wiped there: top {top}"); show(sel.head(top))
    print("\nbest by all five quarters (for reference, hindsight):"); show(d.sort_values("tot5", ascending=False).head(6))
    print(f"\nrank correlation, analysed total vs hold-out total over all {len(d)} rows: {d['tot3'].corr(d['ho2'], method='spearman'):+.2f}")
    g = d[~d["name"].str.startswith("LIVE")].copy()
    p = g["name"].str.split(" \\| ", expand=True); g["trend"], g["ladder"] = p[0], p[1]
    g["cool"] = np.where(p[2].str.contains("after loss"), "1h after loss", "live cooldown"); g["exit"] = p[2].str.replace(" +1h after loss", "", regex=False)
    for f in ("trend", "ladder", "cool", "exit"):
        m = g.groupby(f).agg(mean_per_q=("tot5", lambda x: x.mean() / 5), ho_per_q=("ho2", lambda x: x.mean() / 2), wiped5=("wiped5", "mean"), dip=("dip", "mean"), nq=("n/q", "mean")).round(1)
        print(f"\naverage over all rows by {f}:"); print(m.sort_values("mean_per_q", ascending=False).to_string())


def report_validation(sym: str) -> None:
    d = pd.read_csv(OUT / f"validate_{sym}.csv")
    W = ["HO1", "HO2", "OOS2", "OOS1", "IS"]
    dd = "max_drawdown_pct" if "max_drawdown_pct" in d.columns else "max_dd_pct"
    rows = []
    for name, g in d.groupby("name", sort=False):
        med = g.groupby("window")["net_profit"].median()
        r = {"design": name, **{w: med.get(w, np.nan) for w in W}, "sum of medians": med.reindex(W).sum(), "mean run": g["net_profit"].mean(),
             "worst run": g["net_profit"].min(), "lost": f"{int((g['net_profit'] < 0).sum())}/{len(g)}", "stopped": int(g["stopped_out"].astype(bool).sum()),
             "maxDD% med": g[dd].median(), "maxDD% worst": g[dd].max(), "worst basket": g["largest_loss"].min(), "baskets/q": g["baskets"].mean()}
        rows.append(r)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 280); pd.set_option("display.max_colwidth", 58)
    print(f"## {sym}: real $2,000, live unit rule, raw ticks, 8 random loop timings x 5 quarters (median net P/L per quarter, USD)")
    print(t.round(0).to_string(index=False))


if __name__ == "__main__":
    cmd, sym = sys.argv[1], sys.argv[2]
    jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    if cmd in ("stage1", "stage1b"):
        run_stage(sym, cmd, jobs)
    elif cmd == "validate":
        validate(sym, jobs)
    elif cmd == "report":
        for tag in ("stage1", "stage1b"):
            if (OUT / f"{tag}_{sym}.csv").exists():
                report_grid(sym, tag)
        if (OUT / f"validate_{sym}.csv").exists():
            report_validation(sym)
    else:
        raise SystemExit(__doc__)
