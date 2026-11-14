"""The pre-registered final exam: five frozen designs, raw ticks, eight loop timings per quarter, a real $2,000 with the
bot's unit rule, on DEV, CONFIRM and FINAL (2023). usage: final_exam.py SYMBOL [jobs]"""
import sys, time
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone"); sys.path.insert(0, f"{SCR}/improve")
import pandas as pd
from backtesting import experiments as E
from backtesting.analysis import robustness
import stage3, stage4

def design(mod, sym, name):
    g, l = mod.grid_for(sym)
    return g[[x["name"] for x in l].index(name)]

def designs(sym):
    return {
        "Live": {},
        "V2": dict(trend_tf="H1", max_adds=0, target_usd_per_unit=20.0, stop_loss_usd_per_unit=20.0, force_close_enabled=False, loss_cooldown_s=14400.0),
        "V3": design(stage3, sym, "MACD turn 1v x1 flat | T8v S8v"),
        "V3 without the add": design(stage3, sym, "no ladder | T8v S8v"),
        "V3-lite": design(stage4, sym, "trend H1 | votes H1 | M15 agree 2 | T8v S8v | pause 12h"),
    }

PERIODS = {
    "DEV": dict(sorted(E.ALL_WINDOWS.items(), key=lambda kv: kv[1][0])),
    "CONFIRM": {"C1": ("2024-01-01", "2024-04-01"), "C2": ("2024-04-01", "2024-07-01"), "C3": ("2024-07-01", "2024-10-01"),
                "C4": ("2024-10-01", "2025-01-01"), "C5": ("2025-01-01", "2025-04-01"), "C6": ("2025-04-01", "2025-07-01")},
    "FINAL": {"F1": ("2023-02-01", "2023-05-01"), "F2": ("2023-05-01", "2023-08-01"), "F3": ("2023-08-01", "2023-11-01"),
              "F4": ("2023-11-01", "2024-01-01")},
}

if __name__ == "__main__":
    sym = sys.argv[1]; jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    d = designs(sym)
    for name, ov in d.items():
        print(name, ov, flush=True)
    out = []
    for per, wins in PERIODS.items():
        t0 = time.time()
        df = robustness.timing_ensemble(E.live_config(sym), wins, n_jobs=jobs, overrides=list(d.values()),
                                        override_labels=[dict(design=n) for n in d])
        df["period"] = per
        out.append(df)
        print(f"{sym} {per}: {len(df)} raw-tick quarter-runs in {time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_csv(f"{SCR}/improve/final_exam_{sym}.csv", index=False)
    print("FINAL EXAM DONE", flush=True)
