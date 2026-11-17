"""Silver inventory: wall-clock run times on the full 8 years (2018-11-13 -> 2026-11-13), per engine and strategy.
Prints timings and trade counts only (no P/L)."""
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from backtesting.research import multisymbol as MS          # noqa: E402
from backtesting.research import external as X              # noqa: E402
from backtesting.research import final10 as F               # noqa: E402
from backtesting.research import balke as B                 # noqa: E402
from backtesting.engine import fast                         # noqa: E402

SYM = "XAGUSDm"
A, Z = F.WINDOWS["8y"]


def log(s):
    print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)


# 1. M1-bar simulator and balke (history from the store's first month, 2017-11)
t0 = time.time()
m = X.load_market(SYM, earliest="2017-11-01", end=F.DATA_END)
log(f"bars: load {len(m):,} M1 bars {time.time() - t0:.1f}s")
t0 = time.time()
sig = X.bot_signals(m)
log(f"bars: the bot's votes {time.time() - t0:.1f}s")
a_ix, z_ix = m.ix(A), m.ix(Z)
t0 = time.time()
v3 = X.v3lite(m, sig)
res, _, _ = F._bar_account(X, m, v3, X.BOT, a_ix, z_ix)
log(f"bars: V3-lite (bar level) plan + 8y account {time.time() - t0:.1f}s, {len(res.trades_pnl)} trades")
for s in X.STRATEGIES:
    for label, (desc, build) in s.for_symbol(SYM).items():
        t0 = time.time()
        try:
            b = build(m)
        except Exception as e:                                       # noqa: BLE001
            log(f"bars: {s.key} {label}: BUILD FAILED {type(e).__name__}: {e}")
            continue
        tb = time.time() - t0
        out = []
        for variant, plan, sz in (("standalone", b.plan, X.BOT), ("risk-sized", b.risk, b.risk_sizing),
                                  ("+ bot votes", X.filtered(b.plan, m, sig.votes_at), X.BOT)):
            if plan is None:
                continue
            t1 = time.time()
            try:
                r, _, _ = F._bar_account(X, m, plan, sz, a_ix, z_ix)
                out.append(f"{variant} {time.time() - t1:.1f}s/{len(r.trades_pnl)}tr/{r.skipped}zero")
            except Exception as e:                                   # noqa: BLE001
                out.append(f"{variant} FAILED {type(e).__name__}: {e}")
        log(f"bars: {s.key:10s} {label:8s} build {tb:5.1f}s | " + " | ".join(out))

for name, build, multi in (("balke ATR Breakout (multi)", lambda: B.atr_breakout(m), True),
                           ("balke Range Breakout, gold settings", lambda: B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0), False),
                           ("balke Go Long", lambda: B.go_long(m), False),
                           ("balke Turnaround Tuesday SMA 25", lambda: B.turnaround_tuesday(m, 25), False)):
    t0 = time.time()
    b = build()
    tb = time.time() - t0
    out = []
    for variant, plan, sz in (("standalone", b.plan, X.BOT), ("risk-sized", b.risk, b.risk_sizing)):
        if plan is None:
            continue
        t1 = time.time()
        try:
            if multi:
                r, _, _ = B.multi_account(m, plan, sz, a_ix, z_ix)
            else:
                r, _, _ = F._bar_account(X, m, plan, sz, a_ix, z_ix)
            out.append(f"{variant} {time.time() - t1:.1f}s/{len(r.trades_pnl)}tr/{r.skipped}zero")
        except Exception as e:                                       # noqa: BLE001
            out.append(f"{variant} FAILED {type(e).__name__}: {e}")
    log(f"{name}: build {tb:.1f}s | " + " | ".join(out))
del m, sig

# 2. tick engine, sec mode, 8 years
t0 = time.time()
prep = fast.prepare(SYM, A, Z, MS.TFS, mode="sec")
log(f"ticks: prepare 8y {prep.n_rows:,} per-second rows {time.time() - t0:.1f}s")
caps = MS.load_specs(SYM)["caps"]
for key in ("v3lite", "gtop2", "gtop1add"):
    cfg = MS.basket_cfg(SYM, key, A, Z, per_unit=True, cap_price=caps.get(key))
    t1 = time.time()
    res = fast.run(cfg, prep, light=True)
    log(f"ticks: {key} 8y {time.time() - t1:.1f}s, {len(res.baskets)} baskets")
cfg = MS.E.live_config(SYM, start=A, end=Z).replace(**MS.GOLD_WINDOW, fixed_units=1, mtqty=0.01, initial_balance=MS.BIG)
t1 = time.time()
res = fast.run(cfg, prep, light=True)
log(f"ticks: Live logic (Fibonacci ladder, $1/unit target, as is) 8y {time.time() - t1:.1f}s, {len(res.baskets)} baskets")
log("done")
