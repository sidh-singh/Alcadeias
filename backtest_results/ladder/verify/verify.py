"""Independent verification driver: configs typed from the written design descriptions (PREREG §2, LADDER.md),
engine called directly (ladder_engine.run), own account loop. Not the search/stress scripts."""
import sys, os, csv, time, json, traceback
from multiprocessing import Pool
import numpy as np
from backtesting.research import ladder_engine as LE

T12 = ["M2", "M4", "M6", "M10", "M20"]
# V3L = gold Top 1 of round 4, as written in PREREG §2.1: H1 votes, H1 trend, force-close off, 4 h loss pause,
# target 10 / stop 8 vol units (H1, 24), one flat add on an M5 MACD turn >= 1 vol unit away, entry agreement 0.
V3L = dict(open_weights={"H1": 1}, entry_agree_s=0.0, trend_tf="H1", force_close_enabled=False,
           loss_cooldown_s=14400.0, vol_tf="H1", vol_len=24, vol_cap_usd_per_unit=0.0,
           target_usd_per_unit=None, stop_loss_usd_per_unit=None, target_vol=10.0, stop_vol=8.0,
           max_adds=1, ladder_trigger="macd_turn", ladder_tfs=["M5", "M15", "H1", "H1", "H1"],
           ladder_multipliers=[1.0] * 4, ladder_gap_vol=1.0, entry_rsi_block_tfs=None)

DESIGNS = {
    "L0": {},                                                   # live v3.9.2 = BacktestConfig.live
    # G1: V3L + stop 12 vol units + add on M2 (T12) + pre-funded unit (30% risk, 1.5 x ATR14 D1)
    "G1": {**V3L, "stop_vol": 12.0, "ladder_tfs": T12, "sizing": "prefund", "pf_risk": 0.30, "pf_atr_mult": 1.5},
    # G5: V3L + add on M2 + no adds while ADX(14,H1) > 30 + always 1 unit
    "G5": {**V3L, "ladder_tfs": T12, "add_gate": [{"kind": "adx_above_block", "tf": "H1", "n": 14, "thr": 30.0}],
           "fixed_units": 1},
    # B1: V3L + new baskets only on the Donchian(20,H4) breakout side + H4 tiers x5 + up to 3 flat adds
    #     on closed-bar Bollinger(20,2) %B <= 0 / >= 1 + pre-funded unit
    "B1": {**V3L, "entry_gate": [{"kind": "donchian", "tf": "H4", "n": 20}], "ladder_tfs": ["H4"] * 5,
           "max_adds": 3, "ladder_multipliers": [1.0] * 64, "ladder_trigger_x": "series",
           "trigger_spec": {"ind": "bb", "n": 20, "k": 2.0, "lo": 0.0, "hi": 1.0},
           "sizing": "prefund", "pf_risk": 0.30, "pf_atr_mult": 1.5},
}

def timing(seed):
    return dict(poll_interval_ms=1000, poll_jitter_ms=200, poll_jitter_seed=int(seed), open_order_delay_ms=100)

def make_cfg(design, sym, start, end, seed):
    return LE.LadderConfig.live(sym, **DESIGNS[design], start=start, end=end, initial_balance=2000.0, **timing(seed))

def one(task):
    design, sym, start, end, seed = task
    t0 = time.time()
    try:
        cfg = make_cfg(design, sym, start, end, seed)
        res = LE.run(cfg, mode="ticks", light=True)
        s = res.scalars
        b = res.baskets
        adds = int((b["n_opened"] - 1).clip(lower=0).sum()) if len(b) else 0
        return dict(design=design, symbol=sym, start=start, end=end, seed=seed,
                    final_balance=round(s["final_balance"], 2), final_equity=round(s["final_equity"], 2),
                    min_equity=round(s["min_equity"], 2), max_dd_pct=round(s["max_drawdown_pct"], 3),
                    stopped_out=bool(s["stopped_out"]), baskets=len(b), adds=adds,
                    max_units=int(b["units"].max()) if len(b) else 0, err="", run_s=round(time.time() - t0, 1))
    except Exception:
        return dict(design=design, symbol=sym, start=start, end=end, seed=seed, err=traceback.format_exc()[-400:],
                    run_s=round(time.time() - t0, 1))

def months(y0, m0, n):
    out = []
    for i in range(n):
        y, m = y0 + (m0 - 1 + i) // 12, (m0 - 1 + i) % 12 + 1
        out.append(f"{y:04d}-{m:02d}-13")
    return out

def plus12(d):
    return f"{int(d[:4]) + 1:04d}{d[4:]}"

def tasks(designs_syms, which):
    starts85 = months(2018, 11, 85)                              # 2018-11-13 .. 2025-11-13
    fold = [d for y in (2018, 2020, 2022, 2024) for d in months(y, 11, 12)]
    out = []
    for design, sym in designs_syms:
        if "all" in which:
            out += [(design, sym, s, plus12(s), sd) for s in starts85 for sd in (1, 2)]
        if "fold" in which:
            out += [(design, sym, s, plus12(s), sd) for s in fold for sd in range(3, 9)]
    return out

if __name__ == "__main__":
    out = sys.argv[1]
    ds = [tuple(x.split(":")) for x in sys.argv[2].split(",")]
    which = sys.argv[3].split(",")
    nw = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    todo = tasks(ds, which)
    done = set()
    if os.path.exists(out):
        with open(out) as f:
            for r in csv.DictReader(f):
                if not r.get("err"):
                    done.add((r["design"], r["symbol"], r["start"], r["end"], int(r["seed"])))
    todo = [t for t in todo if t not in done]
    # long runs first
    print(f"{len(todo)} runs", flush=True)
    cols = ["design", "symbol", "start", "end", "seed", "final_balance", "final_equity", "min_equity", "max_dd_pct",
            "stopped_out", "baskets", "adds", "max_units", "err", "run_s"]
    new = not os.path.exists(out)
    t0 = time.time()
    with open(out, "a", newline="") as f, Pool(nw, maxtasksperchild=20) as pool:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        for i, r in enumerate(pool.imap_unordered(one, todo), 1):
            w.writerow(r); f.flush()
            if i % 20 == 0 or r.get("err"):
                print(f"{i}/{len(todo)} {time.time()-t0:.0f}s {r['design']} {r['start']} {r['seed']} {r.get('err','')[:200]}", flush=True)
    print("done", time.time() - t0, flush=True)
