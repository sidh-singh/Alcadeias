"""Top 3 of the v4 search per symbol (diverse), with references, on raw ticks: eight loop timings per quarter, a real $2,000
with the bot's unit rule. usage: top3_v4.py SYMBOL {pick|dev|holdout} [jobs]
  pick     print the picks
  dev      2023 - 2026 (the periods the search saw)
  holdout  2021 - 2022 (untouched; run once)"""
import ast, json, sys, time
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone"); sys.path.insert(0, f"{SCR}/improve")
import pandas as pd
from backtesting import experiments as E
from backtesting.analysis import robustness
from final_exam import PERIODS

REFS = {
    "Live": {},
    "V3-lite": {"trend_tf": "H1", "force_close_enabled": False, "loss_cooldown_s": 43200.0, "vol_tf": "H1", "vol_len": 24,
                "target_usd_per_unit": None, "stop_loss_usd_per_unit": None, "max_adds": 0, "open_weights": {"H1": 1},
                "entry_agree_s": 2.0, "target_vol": 8.0, "stop_vol": 8.0},
    "Owner's rules + H1 trend + 4 h pause": {"entry_rsi_block_tfs": ["H1", "H4"], "entry_rsi_block_mode": "any",
                                             "fc_rsi_tfs": ["H1", "H4"], "trend_tf": "H1", "loss_cooldown_s": 14400.0},
}
HOLDOUT = {f"H{i + 1}": (a, z) for i, (a, z) in enumerate(
    [("2021-01-01", "2021-04-01"), ("2021-04-01", "2021-07-01"), ("2021-07-01", "2021-10-01"), ("2021-10-01", "2022-01-01"),
     ("2022-01-01", "2022-04-01"), ("2022-04-01", "2022-07-01"), ("2022-07-01", "2022-10-01"), ("2022-10-01", "2023-01-01")])}

def picks(sym, n=3):
    t = pd.read_csv(f"{SCR}/opt/v4_{sym}/trials.csv")
    t = t[(t["origin"] != "reference") & (t["eligible"].astype(str) == "True")].sort_values("objective", ascending=False)
    params = [c for c in ("open_weights", "entry_agree_s", "target_vol", "stop_vol", "vol_cap_usd_per_unit", "max_adds", "loss_cooldown_s",
                          "entry_rsi_block_tfs", "fc_rsi_tfs", "force_close_enabled") if c in t.columns]
    chosen = []
    for _, r in t.iterrows():
        if all(sum(str(r[p]) != str(c[p]) for p in params) >= 2 for c in chosen):
            chosen.append(r)
        if len(chosen) == n:
            break
    out = {}
    for i, r in enumerate(chosen, 1):
        label = f"Top {i}: " + ", ".join(f"{p}={r[p]}" for p in params)
        try:
            out[label] = json.loads(r["overrides"])
        except ValueError:
            out[label] = ast.literal_eval(r["overrides"])
        print(sym, label, f"| objective {r['objective']:.1f}/month, mean {r['mean']:.1f}, worst block {r['worst_block']:.1f}, max dip {r['max_dip']:.0f}")
    return out

if __name__ == "__main__":
    sym, what = sys.argv[1], sys.argv[2]; jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    designs = {**REFS, **picks(sym)}
    if what == "pick":
        sys.exit(0)
    json.dump({k: v for k, v in designs.items()}, open(f"{SCR}/improve/top3_v4_{sym}_designs.json", "w"), indent=1, default=str)
    periods = PERIODS if what == "dev" else {"HOLDOUT": HOLDOUT}
    out = []
    for per, wins in periods.items():
        t0 = time.time()
        df = robustness.timing_ensemble(E.live_config(sym), wins, n_jobs=jobs, overrides=list(designs.values()),
                                        override_labels=[dict(design=k) for k in designs])
        df["period"] = per
        out.append(df)
        print(f"{sym} {per}: {len(df)} raw-tick quarter-runs in {time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_csv(f"{SCR}/improve/top3_v4_{what}_{sym}.csv", index=False)
    print("TOP3 DONE", flush=True)
