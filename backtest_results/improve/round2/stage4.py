"""Stage 3: which ladder (if any) helps inside the trend-filter frame? Distances in H1-volatility units. DEV quarters, fixed unit, per-second.
usage: stage3.py SYMBOL [jobs]"""
import sys, time
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone")
from backtesting import experiments as E
from backtesting.analysis import robustness

FRAME = dict(trend_tf="H1", force_close_enabled=False, loss_cooldown_s=14400.0, vol_tf="H1", vol_len=24,
             target_usd_per_unit=None, stop_loss_usd_per_unit=None)
TIERS = ["M5", "M15", "H1", "H1", "H1"]

def grid_for(sym):
    opens = [("votes H1+M15 (live)", {}), ("votes M15+M5", dict(open_weights={"M15": 1, "M5": 1})), ("votes M15", dict(open_weights={"M15": 1})),
             ("votes H1", dict(open_weights={"H1": 1})), ("votes M5", dict(open_weights={"M5": 1}))]
    grid, labels = [], []
    for tr in ("H1", "H4"):
        for on, ov in opens:
            for ag in (2.0, 0.0):
                for t, s_ in ((4, 4), (6, 6), (8, 8)):
                    for cn, cs in (("1h", 3600.0), ("4h", 14400.0), ("12h", 43200.0)):
                        grid.append({**FRAME, "trend_tf": tr, "max_adds": 0, **ov, "entry_agree_s": ag, "target_vol": float(t), "stop_vol": float(s_), "loss_cooldown_s": cs})
                        labels.append(dict(name=f"trend {tr} | {on} | M15 agree {ag:g} | T{t}v S{s_}v | pause {cn}", ladder=f"trend {tr} | {on} | agree {ag:g}", exit=f"T{t}v S{s_}v pause {cn}"))
    return grid, labels

if __name__ == "__main__":
    sym = sys.argv[1]; jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    base = E.live_config(sym, fixed_units=1, initial_balance=E.SWEEP_BALANCE)
    grid, labels = grid_for(sym)
    t0 = time.time()
    df = robustness.across_windows(base, grid, labels, E.ALL_WINDOWS, n_jobs=jobs,
                                   progress=lambda name, a, b, t: print(f"{sym} {name} {a}/{b} {t:.0f}s", flush=True) if a % 50 == 0 or a == b else None)
    df.to_csv(f"{SCR}/improve/stage4_{sym}.csv", index=False)
    print(f"{sym}: {len(grid)} configurations x {len(E.ALL_WINDOWS)} quarters in {time.time() - t0:.0f}s", flush=True)
