"""Silver inventory: one plumbing smoke test per engine on XAGUSDm, one development month (March 2021).

Prints counts, timings and arithmetic checks only (no P/L, no equity): the point is that each engine loads silver,
uses its 5,000 oz contract and 3 digits, trades around the daily break and produces internally consistent trades.

    cd <repo> && PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=... python3 backtest_results/silver/smoke/smoke.py
"""
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from backtesting.research import multisymbol as MS          # noqa: E402  (registers XAGUSDm in the engine's table)
from backtesting.research import external as X              # noqa: E402
from backtesting.research import final10 as F               # noqa: E402
from backtesting.research import balke as B                 # noqa: E402
from backtesting.engine import fast                         # noqa: E402
from backtesting.config import SYMBOLS                      # noqa: E402

SYM = "XAGUSDm"
A, Z = "2021-03-01", "2021-04-01"
HIST = "2020-01-01"                       # D1 history for the bar strategies' indicators (55-day Turtle, ATR 200 on H1)
DAY = 86400
ok_all = True


def check(name, cond, info=""):
    global ok_all
    ok_all &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(': ' + info) if info else ''}", flush=True)


def secs(col):
    """Epoch seconds of a datetime column (tz-aware or naive UTC)."""
    import pandas as pd
    t = pd.to_datetime(col, utc=True)
    return (t.astype("int64") // 10**9).to_numpy() if hasattr(t, "astype") else np.asarray(t.view("int64") // 10**9)


def in_break(ts_s):
    """True when a UTC time lies inside silver's daily break (Mon-Thu 20:58-22:01 summer / 21:58-23:01 winter).
    Both windows are tested (no DST table): a time inside either one counts."""
    ts_s = np.asarray(ts_s, np.int64)
    mod = (ts_s % DAY) // 60
    dow = (ts_s // DAY + 3) % 7
    return (dow <= 3) & (((mod >= 20 * 60 + 59) & (mod < 22 * 60)) | ((mod >= 21 * 60 + 59) & (mod < 23 * 60)))


spec = SYMBOLS[SYM]
print(f"spec: contract {spec.contract_size}, digits {spec.digits}, quote {spec.quote}, data_hole_s {spec.data_hole_s}")
check("engine table holds silver at 5,000 oz / 3 digits", spec.contract_size == 5000.0 and spec.digits == 3)

# ── 1. tick engine (per-second replay), gold V3-lite and gold Top 2 with the translated cap ──
print("\n1. tick engine, sec mode:", A, "->", Z)
t0 = time.time()
prep = fast.prepare(SYM, A, Z, MS.TFS, mode="sec")
print(f"  prepare: {prep.n_rows:,} per-second rows, warm bars {prep.nwarm}, {time.time() - t0:.1f}s")
caps = MS.load_specs(SYM)["caps"]
for key in ("v3lite", "gtop2"):
    cfg = MS.basket_cfg(SYM, key, A, Z, per_unit=True, cap_price=caps.get(key))
    t1 = time.time()
    res = fast.run(cfg, prep)
    rt = time.time() - t1
    b, f = res.baskets, res.fills
    print(f"  {key}: window {cfg.window_start_min}-{cfg.window_end_min} min, cap ${cfg.vol_cap_usd_per_unit:.2f}/unit, "
          f"{len(b)} baskets, {len(f)} fills, {rt:.1f}s")
    if key == "gtop2":
        check("Top 2 cap translated to 0.2943 price = $14.72 per 0.01 lot",
              abs(cfg.vol_cap_usd_per_unit - caps["gtop2"] * 5000 * 0.01) < 1e-9)
    check(f"{key}: trades happened", len(b) > 0)
    one = b[b["n_pos"] == 1]
    if len(one):
        sgn = np.where(one["side"] == "BUY", 1.0, -1.0)
        calc = sgn * (one["close_price"] - one["first_price"]) * one["lots"] * spec.contract_size
        err = float(np.abs(calc - one["pnl"] - one.get("commission", 0.0)).max())
        check(f"{key}: P/L = price move x lots x 5,000 on single-position baskets", err < 0.02, f"max diff ${err:.4f}")
    print(f"    fill actions: {f['action'].value_counts().to_dict()}")
    ft = secs(f["fill_time"])
    j = np.searchsorted(prep.t_ms, ft * 1000, side="right") - 1
    gap = (ft * 1000 - prep.t_ms[np.maximum(j, 0)]) / 1000.0
    check(f"{key}: no order inside the daily break, every fill had a quote within 3 min",
          (not in_break(ft).any()) and (gap.max() <= 180 if len(gap) else True),
          f"{int(in_break(ft).sum())} in break, max quote age {gap.max() if len(gap) else 0:.0f}s")
    rs = b["reason"].value_counts().to_dict()
    print(f"    exit reasons: {rs}; session counters "
          f"{ {k: v for k, v in res.counters.items() if any(w in k for w in ('close_only', 'closed', 'hole', 'dead'))} }")

# ── 2. M1-bar simulator (external.py): Turtle System 1 + bot votes, Supertrend H4 standalone ──
print("\n2. M1-bar simulator:", HIST, "history,", A, "->", Z)
t0 = time.time()
m = X.load_market(SYM, earliest=HIST, end=Z)
sig = X.bot_signals(m)
print(f"  market + bot votes: {len(m):,} M1 bars, k = ${m.k:.0f} per 1.00 of price per 0.01 lot, tick {m.tick}, "
      f"around the clock {m.around_the_clock}, {time.time() - t0:.1f}s")
check("bar simulator: k = 50 USD per 1.00 per 0.01 lot, tick 0.001", m.k == 50.0 and abs(m.tick - 0.001) < 1e-12)
d1 = m.bars("D1")
wd = ((d1.tc - 1) // DAY + 3) % 7                # the UTC day a D1 bar closes on (its open can be Sunday evening)
check("D1 bars: none ends on a Sunday or Saturday (Sunday-evening stub merged into Monday)", not (wd >= 5).any(),
      f"{len(d1)} D1 bars, weekdays {sorted(set(wd.tolist()))}")
a_ix, z_ix = m.ix(A), m.ix(Z)
for name, plan, sizing in (
        ("Turtle S1 + bot votes", X.filtered(X.turtle(m, 1).plan, m, sig.votes_at), X.BOT),
        ("Supertrend H4", X.supertrend(m).plan, X.BOT)):
    t1 = time.time()
    res, daily, tr = F._bar_account(X, m, plan, sizing, a_ix, z_ix)
    print(f"  {name}: {len(res.trades_pnl)} trades ({res.skipped} at zero size), {time.time() - t1:.1f}s")
    if len(tr):
        single = tr[tr["legs"] == 1]
        if len(single):
            sgn = np.where(single["side"] == "BUY", 1.0, -1.0)
            calc = sgn * (single["exit"] - single["entry"]) * single["lots"] / 0.01 * m.k
            err = float(np.abs(calc - single["pnl"]).max())
            check(f"{name}: P/L = price move x units x $50", err < 1e-6, f"max diff ${err:.6f}")
        et = secs(tr["open_time"])
        check(f"{name}: no entry inside the daily break", not in_break(et).any())

# ── 3. Balke's multi-position account: ATR Breakout (his gold settings), every signal its own trade ──
print("\n3. balke multi-position account:", A, "->", Z)
t1 = time.time()
bt = B.atr_breakout(m)
for label, (plan, sizing) in (("risk-sized 0.5%", (bt.risk, bt.risk_sizing)), ("bot unit rule", (bt.plan, X.BOT))):
    res, daily, tr = B.multi_account(m, plan, sizing, a_ix, z_ix)
    print(f"  ATR Breakout, {label}: {len(res.trades_pnl)} trades ({res.skipped} at zero size), "
          f"{(tr['open_time'] < tr['close_time'].shift()).sum() if len(tr) else 0} entered while another was open, "
          f"{time.time() - t1:.1f}s")
    if len(tr):
        sgn = np.where(tr["side"] == "BUY", 1.0, -1.0)
        calc = sgn * (tr["exit"] - tr["entry"]) * tr["lots"] / 0.01 * m.k
        err = float(np.abs(calc - tr["pnl"]).max())
        check(f"ATR Breakout {label}: P/L = price move x units x $50", err < 1e-6, f"max diff ${err:.6f}")
check("balke multi-account produced trades", True)

print("\nALL PASS" if ok_all else "\nSOME CHECKS FAILED")
