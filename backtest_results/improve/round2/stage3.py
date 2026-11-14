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
    exits = [(2, 2), (3, 3), (4, 4), (6, 6), (3, 6), (4, 8), (8, 8)]
    ladders = [("no ladder", dict(max_adds=0))]
    for g in (1.0, 2.0):
        for n in (1, 2, 3):
            for mn, mv in (("flat", [1, 1, 1, 1]), ("1,1,2,3", [1, 1, 2, 3])):
                if n == 1 and mn != "flat":
                    continue
                ladders.append((f"price step {g:g}v x{n} {mn}", dict(ladder_trigger="price_step", ladder_gap_vol=g, max_adds=n, ladder_multipliers=mv)))
    for trig, nm in (("rsi_cross", "RSI cross-back"), ("macd_turn", "MACD turn")):
        for g in (0.5, 1.0):
            for n in (1, 2, 3):
                ladders.append((f"{nm} {g:g}v x{n} flat", dict(ladder_trigger=trig, ladder_gap_vol=g, max_adds=n, ladder_multipliers=[1, 1, 1, 1], ladder_tfs=TIERS)))
    ladders.append(("RSI level (live trigger) 1v x2 flat", dict(ladder_trigger="rsi_level", ladder_gap_vol=1.0, max_adds=2, ladder_multipliers=[1, 1, 1, 1], ladder_tfs=TIERS)))
    for g in (1.0, 2.0):
        for n in (1, 2):
            ladders.append((f"add to winners {g:g}v x{n} flat, trail", dict(ladder_trigger="profit_step", ladder_gap_vol=g, max_adds=n, ladder_multipliers=[1, 1, 1, 1],
                                                                             trail_start_vol=g, trail_gap_vol=2.0)))
    grid, labels = [], []
    for ln, lv in ladders:
        for t, s in exits:
            grid.append({**FRAME, **lv, "target_vol": float(t), "stop_vol": float(s)})
            labels.append(dict(name=f"{ln} | T{t}v S{s}v", ladder=ln, exit=f"T{t}v S{s}v"))
    return grid, labels

if __name__ == "__main__":
    sym = sys.argv[1]; jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    base = E.live_config(sym, fixed_units=1, initial_balance=E.SWEEP_BALANCE)
    grid, labels = grid_for(sym)
    t0 = time.time()
    df = robustness.across_windows(base, grid, labels, E.ALL_WINDOWS, n_jobs=jobs,
                                   progress=lambda name, a, b, t: print(f"{sym} {name} {a}/{b} {t:.0f}s", flush=True) if a % 50 == 0 or a == b else None)
    df.to_csv(f"{SCR}/improve/stage3_{sym}.csv", index=False)
    print(f"{sym}: {len(grid)} configurations x {len(E.ALL_WINDOWS)} quarters in {time.time() - t0:.0f}s", flush=True)
