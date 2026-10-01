"""
Parameter sweep for the Alcadeias BTCUSD backtest.

Runs the REAL strategy/indicator over the same 90-day history under several
parameter variations and tabulates them side by side, so you can see which
changes would have survived the period. Data is loaded ONCE and reused.

TESTING TOOL ONLY — lives on backtest_btcusd, never propagated to the 20 live
branches. It does not modify strategy.py / indicator.py / constants.py; RSI
threshold variants are applied by temporarily overriding the names the strategy
module already imported (restored after each run).

    python -X utf8 -u -m backtest.sweep                 # 90 days, no costs
    python -X utf8 -u -m backtest.sweep --days 90 --spread-usd 5
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import os
import statistics
from datetime import datetime, timezone

import strategy as strat_mod
from backtest import data as bt_data
from backtest import engine as bt_engine
from backtest.run_backtest import _load_symbol_cfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


# ── scenarios ────────────────────────────────────────────────────────────────
# Each dict: a name + any run_backtest knobs, plus optional rsi_core / rsi_mtf
# (temporarily patched into the strategy module). Everything omitted = live value.
SCENARIOS = [
    dict(name="baseline"),                                    # exactly live
    dict(name="rsi 30/70", rsi_core=(30, 70), rsi_mtf=(30, 70)),
    dict(name="rsi 25/75", rsi_core=(25, 75), rsi_mtf=(25, 75)),
    dict(name="rsi 40/60", rsi_core=(40, 60), rsi_mtf=(40, 60)),
    dict(name="regime ON", regime_act=True),                  # v1.6.0 ADX+spike gate
    dict(name="cut@depth5", max_depth=5),
    dict(name="cut@depth4", max_depth=4),
    dict(name="cut@depth3", max_depth=3),
    dict(name="block 13-14z", time_block_hours={13, 14}),     # worst-loss UTC window
    dict(name="target x2", close_mult=2.0),
    dict(name="regime+cut4", regime_act=True, max_depth=4),
    dict(name="regime+cut4+blk", regime_act=True, max_depth=4, time_block_hours={13, 14}),
]


@contextlib.contextmanager
def patched_rsi(core=None, mtf=None):
    """Temporarily override the RSI thresholds the strategy module resolves.

    strategy.py does `from constants import RSI_OVERSOLD, ...`, binding them as
    strategy-module globals, so calculate_signal reads strategy.RSI_OVERSOLD etc.
    We set those names for the duration of one run and restore them after.
    """
    saved = {}

    def _set(name, val):
        saved[name] = getattr(strat_mod, name)
        setattr(strat_mod, name, val)

    try:
        if core is not None:
            _set("RSI_OVERSOLD", core[0])
            _set("RSI_OVERBOUGHT", core[1])
        if mtf is not None:
            _set("RSI_MTF_OVERSOLD", mtf[0])
            _set("RSI_MTF_OVERBOUGHT", mtf[1])
        yield
    finally:
        for k, v in saved.items():
            setattr(strat_mod, k, v)


def summarize(name, res):
    baskets = res["baskets"]
    nb = len(baskets)
    net = [b.net_pnl for b in baskets]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    gw, gl = sum(wins), sum(losses)
    pf = (gw / abs(gl)) if gl < 0 else float("inf")
    cr = res["close_reason"]
    return {
        "scenario": name,
        "net": round(res["end_balance"] - res["start_balance"], 2),
        "net_pct": round(100.0 * (res["end_balance"] - res["start_balance"]) / res["start_balance"], 2),
        "max_dd_pct": round(res["max_dd_pct"], 2),
        "max_dd": round(res["max_dd"], 2),
        "baskets": nb,
        "win_pct": round(100.0 * len(wins) / nb, 1) if nb else 0.0,
        "pf": round(pf, 2) if pf != float("inf") else 999.99,
        "depth6": sum(1 for b in baskets if b.max_count >= 6),
        "forced": cr.get("H6_FORCED", 0),
        "early_cut": cr.get("EARLY_CUT", 0),
        "worst_basket": round(min(net), 2) if nb else 0.0,
        "worst_mae": round(min((b.mae for b in baskets), default=0.0), 2),
        "in_market_pct": round(100.0 * res["in_market_min"] / max(1, res["test_minutes"]), 1),
    }


def main():
    cfg = _load_symbol_cfg()
    p = argparse.ArgumentParser(description="Alcadeias BTCUSD parameter sweep")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--warmup-days", type=int, default=35)
    p.add_argument("--csv", default=None)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--balance", type=float, default=2000.0)
    p.add_argument("--spread-usd", type=float, default=0.0)
    p.add_argument("--commission-per-lot", type=float, default=0.0)
    p.add_argument("--contract-size", type=float, default=1.0)
    p.add_argument("--out", default=os.path.join(HERE, "output"))
    args = p.parse_args()

    m1 = bt_data.load_m1(symbol=args.symbol, test_days=args.days,
                         warmup_days=args.warmup_days, csv=args.csv, refresh=args.refresh)

    base_kwargs = dict(
        balance=args.balance, spread_usd=args.spread_usd,
        commission_per_lot=args.commission_per_lot, contract_size=args.contract_size,
        mtqty=cfg["mtqty"], step_up_balance=cfg["step_up_balance"],
        unit_max_limit=cfg["unit_max_limit"], progress=False,
    )

    rows = []
    for sc in SCENARIOS:
        name = sc["name"]
        kw = dict(base_kwargs)
        for k in ("max_depth", "time_block_hours", "close_mult", "regime_act"):
            if k in sc:
                kw[k] = sc[k]
        print(f"\n=== {name} ===", flush=True)
        with patched_rsi(core=sc.get("rsi_core"), mtf=sc.get("rsi_mtf")):
            res = bt_engine.run_backtest(m1, **kw)
        row = summarize(name, res)
        rows.append(row)
        print(f"    net ${row['net']:+,.2f} ({row['net_pct']:+.1f}%)  "
              f"maxDD {row['max_dd_pct']:.1f}%  baskets {row['baskets']}  "
              f"PF {row['pf']}  depth6 {row['depth6']}  worst ${row['worst_basket']:,.2f}",
              flush=True)

    # ── comparison table ──
    p0, p1 = res["period"]
    hdr = (f"{'scenario':<17}{'net$':>10}{'net%':>8}{'maxDD%':>8}{'baskets':>8}"
           f"{'win%':>7}{'PF':>7}{'d6':>5}{'forced':>7}{'cut':>6}{'worstBkt':>11}{'inMkt%':>8}")
    print("\n" + "=" * len(hdr))
    print(f"  SWEEP — BTCUSD {args.days}d  ({p0:%Y-%m-%d} → {p1:%Y-%m-%d})  "
          f"balance ${args.balance:,.0f}  spread ${args.spread_usd}  comm ${args.commission_per_lot}")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['scenario']:<17}{r['net']:>10,.2f}{r['net_pct']:>8.1f}{r['max_dd_pct']:>8.1f}"
              f"{r['baskets']:>8}{r['win_pct']:>7.1f}{r['pf']:>7.2f}{r['depth6']:>5}"
              f"{r['forced']:>7}{r['early_cut']:>6}{r['worst_basket']:>11,.2f}{r['in_market_pct']:>8.1f}")
    print("=" * len(hdr))

    # ── save ──
    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(args.out, f"sweep_{stamp}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved: {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
