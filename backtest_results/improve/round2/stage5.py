"""The ladder grid (stage 3) and the entry-frame grid (stage 4) again, unchanged, on the CONFIRM quarters (2024-01 .. 2025-06).
usage: stage5.py SYMBOL [jobs]"""
import sys, time
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone"); sys.path.insert(0, f"{SCR}/improve")
from backtesting import experiments as E
from backtesting.analysis import robustness
import stage3, stage4
CONFIRM = {"C1": ("2024-01-01", "2024-04-01"), "C2": ("2024-04-01", "2024-07-01"), "C3": ("2024-07-01", "2024-10-01"),
           "C4": ("2024-10-01", "2025-01-01"), "C5": ("2025-01-01", "2025-04-01"), "C6": ("2025-04-01", "2025-07-01")}
if __name__ == "__main__":
    sym = sys.argv[1]; jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    base = E.live_config(sym, fixed_units=1, initial_balance=E.SWEEP_BALANCE)
    for tag, mod in (("stage3", stage3), ("stage4", stage4)):
        grid, labels = mod.grid_for(sym)
        grid = [dict()] + grid; labels = [dict(name="LIVE", ladder="LIVE", exit="LIVE")] + labels
        t0 = time.time()
        df = robustness.across_windows(base, grid, labels, CONFIRM, n_jobs=jobs)
        df.to_csv(f"{SCR}/improve/{tag}_confirm_{sym}.csv", index=False)
        print(f"{sym} {tag}: {len(grid)} configurations x {len(CONFIRM)} CONFIRM quarters in {time.time() - t0:.0f}s", flush=True)
