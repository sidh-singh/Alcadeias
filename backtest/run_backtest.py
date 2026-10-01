"""
Offline backtest runner for the Alcadeias trading bot (BTCUSD).

Runs the SAME strategy/indicator code the live bot runs via start_btcusd.bat, but
with MT5 replaced by historical M1 data (no sign-in) and a simulated broker.

Usage (from repo root):
    python -m backtest.run_backtest                 # last 90 days, units=1, no costs
    python -m backtest.run_backtest --days 90 --balance 10000 --spread-usd 5
    python -m backtest.run_backtest --csv mt5_btcusdm_m1.csv   # broker-exact bars

See backtest/README.md for the full option list and fidelity notes.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime, timezone

import constants as K
from backtest import data as bt_data
from backtest import engine as bt_engine

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _load_symbol_cfg():
    """Pull BTCUSDm live config from symbols.json so defaults match production."""
    path = os.path.join(REPO, "symbols.json")
    cfg = {"mtqty": 0.01, "step_up_balance": 2500, "unit_max_limit": 10}
    try:
        with open(path) as f:
            j = json.load(f)
        cfg["mtqty"] = float(j.get("mtqty", cfg["mtqty"]))
        for s in j.get("symbols", []):
            if str(s.get("symbol", "")).upper().startswith("BTC"):
                cfg["step_up_balance"] = float(s.get("step_up_balance", cfg["step_up_balance"]))
                cfg["unit_max_limit"] = int(s.get("unit_max_limit", cfg["unit_max_limit"]))
                break
    except (OSError, ValueError, KeyError):
        pass
    return cfg


def parse_args():
    cfg = _load_symbol_cfg()
    p = argparse.ArgumentParser(description="Alcadeias BTCUSD offline backtest")
    p.add_argument("--symbol", default="BTCUSDT",
                   help="public data symbol (proxy for broker BTCUSDm); ignored with --csv")
    p.add_argument("--days", type=int, default=90, help="test window length in days")
    p.add_argument("--warmup-days", type=int, default=35,
                   help="extra history before the window for indicator warm-up")
    p.add_argument("--csv", default=None, help="broker-exact M1 CSV (time,open,high,low,close)")
    p.add_argument("--refresh", action="store_true", help="ignore cached data and refetch")
    p.add_argument("--balance", type=float, default=2000.0,
                   help="starting balance (drives the auto unit tier & $-profit target)")
    p.add_argument("--spread-usd", type=float, default=0.0,
                   help="BTC spread in USD paid across each fill (0 = logic-only view)")
    p.add_argument("--commission-per-lot", type=float, default=0.0,
                   help="round-turn commission per 1.0 lot")
    p.add_argument("--contract-size", type=float, default=1.0,
                   help="USD profit per 1.0 price move per 1.0 lot (BTCUSD Exness = 1)")
    p.add_argument("--mtqty", type=float, default=cfg["mtqty"])
    p.add_argument("--step-up-balance", type=float, default=cfg["step_up_balance"])
    p.add_argument("--unit-max-limit", type=int, default=cfg["unit_max_limit"])
    p.add_argument("--sha-intrabar", action="store_true",
                   help="recompute SHA on the forming M15 bar while flat (finer entry timing)")
    # ── parameter-test knobs (all default to exact live behaviour) ──
    p.add_argument("--regime-act", action="store_true",
                   help="arm the v1.6.0 regime filter (ADX+ATR spike) in ACT mode")
    p.add_argument("--max-depth", type=int, default=None,
                   help="cap the DCA ladder at this depth; cut the basket instead of adding deeper")
    p.add_argument("--block-hours", default=None,
                   help="comma-separated UTC hours in which to suppress FRESH entries, e.g. 13,14")
    p.add_argument("--close-mult", type=float, default=1.0,
                   help="profit-target multiplier (1.0 = live: unit N → $N)")
    p.add_argument("--out", default=os.path.join(HERE, "output"))
    return p.parse_args()


def _fmt_dur(minutes: float) -> str:
    h = minutes / 60.0
    if h < 48:
        return f"{h:.1f}h"
    return f"{h / 24.0:.1f}d"


def build_report(res: dict, params: dict) -> str:
    baskets = res["baskets"]
    nb = len(baskets)
    net = [b.net_pnl for b in baskets]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    pf = (gross_win / abs(gross_loss)) if gross_loss < 0 else float("inf")
    start_bal = res["start_balance"]
    end_bal = res["end_balance"]
    net_total = end_bal - start_bal
    depth = {d: 0 for d in range(1, 7)}
    for b in baskets:
        depth[min(6, b.max_count)] = depth.get(min(6, b.max_count), 0) + 1
    p0, p1 = res["period"]
    days = (p1 - p0).total_seconds() / 86400.0
    total_vol = sum(b.total_volume for b in baskets)
    total_spread = sum(b.spread_cost for b in baskets)
    total_comm = sum(b.commission_cost for b in baskets)
    worst_mae = min((b.mae for b in baskets), default=0.0)

    L = []
    A = L.append
    A("=" * 72)
    A("  ALCADEIAS BTCUSD — FULL-LOGIC BACKTEST REPORT")
    A("=" * 72)
    A(f"  Data source      : {params['data_desc']}")
    A(f"  Test window      : {p0:%Y-%m-%d %H:%M} → {p1:%Y-%m-%d %H:%M} UTC  ({days:.1f} days)")
    A(f"  Decision cadence : per M1 bar ({res['test_minutes']:,} minutes)  |  "
      f"SHA entry: {'intrabar M15' if params['sha_intrabar'] else 'closed M15'}")
    A("")
    A("  ── PARAMETERS (as shipped / live) ─────────────────────────────────")
    A(f"  SHA (M15)        : {K.SHA_MA_TYPE}({K.SHA_LENGTH}) signal / "
      f"{K.SHA_TREND_MA_TYPE}({K.SHA_TREND_LENGTH}) trend   lookback={K.STRATEGY_LOOKBACK}")
    A(f"  RSI core         : {K.RSI_MA_TYPE}({K.RSI_LENGTH})  oversold={K.RSI_OVERSOLD} "
      f"overbought={K.RSI_OVERBOUGHT}")
    A(f"  RSI MTF entry    : {K.RSI_MTF_OVERSOLD}/{K.RSI_MTF_OVERBOUGHT} on "
      f"{[t.replace('TIMEFRAME_','') for t in K.RSI_MTF_TIMEFRAMES]}")
    A(f"  DCA ladder TFs   : {[t.replace('TIMEFRAME_','') for t in K.RSI_DCA_LADDER_TIMEFRAMES]}"
      f"  → final close {K.RSI_FINAL_CLOSE_TIMEFRAME.replace('TIMEFRAME_','')}")
    units_used = sorted({b.unit for b in baskets}) if baskets else [params['unit_note']]
    unit_rng = f"{units_used[0]}" if len(units_used) == 1 else f"{units_used[0]}–{units_used[-1]} (auto-stepped)"
    A(f"  Unit / sizing    : balance={start_bal:,.0f} → unit={unit_rng}  "
      f"(step_up={params['step_up_balance']:,.0f}, cap={params['unit_max_limit']}), "
      f"mtqty={params['mtqty']}, contract={params['contract_size']}")
    A(f"  Profit target    : floating > ${params['unit_note']} closes the basket "
      f"(target == unit)")
    A(f"  Costs modelled   : spread=${params['spread_usd']}/BTC  "
      f"commission=${params['commission_per_lot']}/lot")
    # Only print the test-knob line when something deviates from live.
    _tweaks = []
    if params.get("regime_act"):
        _tweaks.append("regime=ACT")
    if params.get("max_depth") is not None:
        _tweaks.append(f"max_depth={params['max_depth']}")
    if params.get("block_hours"):
        _tweaks.append(f"block_utc_hours={params['block_hours']}")
    if params.get("close_mult", 1.0) != 1.0:
        _tweaks.append(f"close_mult={params['close_mult']}")
    if _tweaks:
        A(f"  TEST OVERRIDES   : {'  '.join(_tweaks)}   (deviates from live!)")
    A("")
    A("  ── HEADLINE ───────────────────────────────────────────────────────")
    A(f"  Start balance    : ${start_bal:,.2f}")
    A(f"  End balance      : ${end_bal:,.2f}")
    A(f"  Net P&L          : ${net_total:,.2f}  ({100.0*net_total/start_bal:+.2f}%)")
    A(f"  Max drawdown     : ${res['max_dd']:,.2f}  ({res['max_dd_pct']:.2f}% of peak equity)")
    A(f"  Peak equity      : ${res['peak_equity']:,.2f}")
    A(f"  Worst basket MAE : ${worst_mae:,.2f}  (deepest unrealised loss in any basket)")
    A("")
    A("  ── BASKETS ────────────────────────────────────────────────────────")
    A(f"  Total baskets    : {nb}   (BUY {res['entries']['BUY']} / SELL {res['entries']['SELL']})")
    if nb:
        A(f"  Win / loss       : {len(wins)} / {len(losses)}   "
          f"win-rate {100.0*len(wins)/nb:.1f}%")
        A(f"  Profit factor    : {pf:.2f}   (gross +${gross_win:,.2f} / -${abs(gross_loss):,.2f})")
        A(f"  Avg / median     : ${statistics.mean(net):,.2f} / ${statistics.median(net):,.2f}")
        A(f"  Best / worst     : ${max(net):,.2f} / ${min(net):,.2f}")
        A(f"  Avg hold time    : {_fmt_dur(statistics.mean(b.bars_held for b in baskets))}")
        A(f"  Time in market   : {100.0*res['in_market_min']/max(1,res['test_minutes']):.1f}%")
    A("")
    A("  ── DCA LADDER DEPTH (positions reached in a basket) ───────────────")
    labels = {1: "1  (entry only)", 2: "2  (+M1)", 3: "3  (+M5)", 4: "4  (+M15)",
              5: "5  (+H1)", 6: "6  (+H4 → H6 forced close)"}
    for d in range(1, 7):
        bar = "#" * int(40 * depth[d] / nb) if nb else ""
        A(f"    depth {labels[d]:<28}: {depth[d]:>4}  {bar}")
    A("")
    A("  ── MONTHLY BREAKDOWN (by basket close) ────────────────────────────")
    if nb:
        months = {}
        for b in baskets:
            key = f"{b.close_time:%Y-%m}"
            m = months.setdefault(key, {"n": 0, "net": 0.0, "wins": 0,
                                        "forced": 0, "worst": 0.0})
            m["n"] += 1
            m["net"] += b.net_pnl
            m["wins"] += 1 if b.net_pnl > 0 else 0
            m["forced"] += 1 if b.reason in ("H6_FORCED", "EOD_OPEN") else 0
            m["worst"] = min(m["worst"], b.net_pnl)
        A(f"    {'month':<9}{'baskets':>9}{'win%':>7}{'net P&L':>13}"
          f"{'forced':>8}{'worst':>12}")
        for key in sorted(months):
            m = months[key]
            wr = 100.0 * m["wins"] / m["n"] if m["n"] else 0.0
            net_s = f"${m['net']:,.2f}"
            worst_s = f"${m['worst']:,.2f}"
            A(f"    {key:<9}{m['n']:>9}{wr:>6.0f}%{net_s:>13}"
              f"{m['forced']:>8}{worst_s:>12}")
    A("")
    A("  ── EXITS ──────────────────────────────────────────────────────────")
    cr = res["close_reason"]
    A(f"    +$unit target close : {cr.get('TARGET',0)}")
    A(f"    H6-RSI forced close : {cr.get('H6_FORCED',0)}   (basket hit 6 & capitulated)")
    eod = sum(1 for b in baskets if b.reason == "EOD_OPEN")
    if eod:
        A(f"    open at period end  : {eod}  (marked-to-market)")
    A("")
    A("  ── TRADING VOLUME & COSTS ─────────────────────────────────────────")
    A(f"    Total volume traded : {total_vol:.2f} lots")
    A(f"    Spread paid         : ${total_spread:,.2f}")
    A(f"    Commission paid     : ${total_comm:,.2f}")
    A("=" * 72)
    return "\n".join(L)


def save_outputs(res: dict, params: dict, report: str, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    # baskets CSV
    csv_path = os.path.join(outdir, f"baskets_{stamp}.csv")
    with open(csv_path, "w", newline="") as f:
        f.write("open_time,close_time,side,unit,max_count,total_volume,vwap_entry,exit_price,"
                "gross_pnl,spread_cost,commission_cost,net_pnl,bars_held,mae,reason\n")
        for b in res["baskets"]:
            f.write(f"{b.open_time:%Y-%m-%d %H:%M},{b.close_time:%Y-%m-%d %H:%M},{b.side},"
                    f"{b.unit},{b.max_count},{b.total_volume},{b.vwap_entry},{b.exit_price},"
                    f"{b.gross_pnl},{b.spread_cost},{b.commission_cost},{b.net_pnl},"
                    f"{b.bars_held},{b.mae},{b.reason}\n")
    # summary JSON
    json_path = os.path.join(outdir, f"summary_{stamp}.json")
    summary = {
        "generated_utc": stamp,
        "params": {k: v for k, v in params.items()},
        "start_balance": res["start_balance"],
        "end_balance": res["end_balance"],
        "net_pnl": round(res["end_balance"] - res["start_balance"], 2),
        "max_drawdown": round(res["max_dd"], 2),
        "max_drawdown_pct": round(res["max_dd_pct"], 2),
        "n_baskets": len(res["baskets"]),
        "entries": res["entries"],
        "close_reason": res["close_reason"],
        "add_rung_fires": res["add_rung"],
        "test_minutes": res["test_minutes"],
        "in_market_min": res["in_market_min"],
    }
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    report_path = os.path.join(outdir, f"report_{stamp}.txt")
    with open(report_path, "w") as f:
        f.write(report + "\n")
    return csv_path, json_path, report_path


def main():
    args = parse_args()
    m1 = bt_data.load_m1(symbol=args.symbol, test_days=args.days,
                         warmup_days=args.warmup_days, csv=args.csv, refresh=args.refresh)

    if args.csv:
        data_desc = f"broker CSV {os.path.basename(args.csv)} (BTCUSDm-exact M1)"
    else:
        data_desc = f"{args.symbol} 1m public klines (proxy for broker BTCUSDm)"

    init_unit = max(1, min(int(args.balance // args.step_up_balance) + 1, args.unit_max_limit)) \
        if args.step_up_balance > 0 else 1

    block_hours = None
    if args.block_hours:
        block_hours = {int(h) for h in str(args.block_hours).split(",") if h.strip() != ""}

    print("\nReplaying real strategy.calculate_signal + indicator code over history…")
    res = bt_engine.run_backtest(
        m1, balance=args.balance, spread_usd=args.spread_usd,
        commission_per_lot=args.commission_per_lot, contract_size=args.contract_size,
        mtqty=args.mtqty, step_up_balance=args.step_up_balance,
        unit_max_limit=args.unit_max_limit, sha_intrabar=args.sha_intrabar,
        max_depth=args.max_depth, time_block_hours=block_hours,
        close_mult=args.close_mult, regime_act=args.regime_act,
    )

    params = {
        "data_desc": data_desc,
        "symbol": args.symbol,
        "days": args.days,
        "balance": args.balance,
        "spread_usd": args.spread_usd,
        "commission_per_lot": args.commission_per_lot,
        "contract_size": args.contract_size,
        "mtqty": args.mtqty,
        "step_up_balance": args.step_up_balance,
        "unit_max_limit": args.unit_max_limit,
        "unit_note": init_unit,
        "sha_intrabar": args.sha_intrabar,
        "regime_act": args.regime_act,
        "max_depth": args.max_depth,
        "block_hours": sorted(block_hours) if block_hours else None,
        "close_mult": args.close_mult,
    }
    report = build_report(res, params)
    print("\n" + report)
    csv_path, json_path, report_path = save_outputs(res, params, report, args.out)
    print(f"\nSaved:\n  {os.path.relpath(csv_path, REPO)}\n  "
          f"{os.path.relpath(json_path, REPO)}\n  {os.path.relpath(report_path, REPO)}")


if __name__ == "__main__":
    main()
