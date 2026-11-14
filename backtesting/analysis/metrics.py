"""
Performance metrics.

The unit of analysis is the **basket** (one fresh entry plus any ladder adds, closed
together) because that is the unit the strategy opens and closes. Figures quoted in
dollars are for the configured account ($2,000 by default).
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
import pandas as pd


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b not in (0, 0.0) and not (isinstance(b, float) and math.isnan(b)) else float("nan")


def daily_returns(equity: pd.DataFrame, initial_balance: float) -> pd.Series:
    """Day-over-day equity returns from the per-minute equity series (UTC days)."""
    if equity is None or len(equity) == 0:
        return pd.Series(dtype=float)
    s = equity.set_index("time")["equity"].resample("1D").last().dropna()
    prev = s.shift(1)
    prev.iloc[0] = initial_balance
    return (s / prev - 1.0).replace([np.inf, -np.inf], np.nan).dropna()


ACCOUNT = 2000.0     # the owner's account: what "wiped" is measured against when a run uses another balance


def replay_account(baskets: pd.DataFrame, account: float, step_up: float, unit_max: int,
                   open_profit: float = 0.0, open_units: int = 1, open_mae: float = 0.0) -> Dict[str, float]:
    """
    The same sequence of baskets on a real account of ``account`` dollars with the bot's own sizing.

    Sweeps run one fixed 0.01-lot unit on a balance too large to be stopped out, so that every
    setting is measured over the whole window. The live account does not trade like that: it
    re-derives its unit from the balance whenever it is flat (``floor(balance / step_up) + 1``),
    so after a good run every later basket, and every later loss, is two or more times as large.
    This replays the baskets in order with that rule: each basket's result and its worst floating
    loss are scaled by (unit the balance implies) / (unit it was run at), and the account is
    wiped when balance plus a basket's worst floating loss reaches zero (stop-out level 0 %).

    A basket still open when the window ends counts like the others: with its worst floating
    loss so far (``open_mae``) and its floating result at the end (``open_profit``), both at the
    unit it was run at (``open_units``).

    It is the same path re-sized, not a second simulation: the small differences a different lot
    size makes to the decisions themselves (cent rounding at the thresholds) are not in it.
    """
    bal = float(account)
    low = bal
    wiped = False
    top_unit = 1

    def unit_now() -> int:
        if step_up <= 0:
            return 1
        return int(max(1, min(int(bal // step_up) + 1, int(unit_max))))

    if len(baskets):
        b = baskets.sort_values("close_time")
        for pnl, mae, u0 in zip(b["pnl"].to_numpy(float), b["mae"].to_numpy(float), b["units"].to_numpy(float)):
            u = unit_now()
            k = u / max(u0, 1.0)
            top_unit = max(top_unit, u)
            worst = bal + k * min(mae, 0.0)
            low = min(low, worst)
            if worst <= 0.0:
                wiped = True
                bal = 0.0
                break
            bal += k * pnl
            low = min(low, bal)
            if bal <= 0.0:
                wiped = True
                bal = 0.0
                break
    final = bal
    if not wiped and (open_profit != 0.0 or open_mae != 0.0):
        u = unit_now()
        top_unit = max(top_unit, u)
        k = u / max(float(open_units), 1.0)
        worst = bal + k * min(open_mae, open_profit, 0.0)
        low = min(low, worst)
        final = bal + k * open_profit
        if worst <= 0.0 or final <= 0.0:
            wiped, final = True, 0.0
    return {"acct_net": round(final - account, 2), "acct_wiped": bool(wiped),
            "acct_dip": round(min(max(account - low, 0.0), account), 2), "acct_max_units": int(top_unit)}


def summarize(res) -> Dict[str, float]:
    """One flat dict of headline numbers for a Result."""
    cfg, b, sc, ct = res.cfg, res.baskets, res.scalars, res.counters
    init = float(cfg.initial_balance)
    final_eq = sc["final_equity"]
    days = max((pd.Timestamp(cfg.end) - pd.Timestamp(cfg.start)).total_seconds() / 86400.0, 1e-9)
    # a run that is stopped out ends there: rates per day are over the days it actually traded
    start_ms = pd.Timestamp(cfg.start).value // 1_000_000
    ran_days = days
    last = sc.get("last_poll_ms")
    if last is not None and last == last and last > start_ms:
        ran_days = min(days, max((float(last) - start_ms) / 86_400_000.0, 1e-9))
    n = int(len(b))
    out: Dict[str, float] = {
        "symbol": cfg.symbol, "variant": cfg.variant, "start": cfg.start, "end": cfg.end,
        "days": round(days, 2),
        "ran_days": round(ran_days, 2),
        "stopped_out_at": (pd.Timestamp(int(last), unit="ms").strftime("%Y-%m-%d %H:%M")
                           if bool(sc["stopped_out"]) and last is not None and last == last else None),
        "initial_balance": init,
        "final_balance": round(sc["final_balance"], 2),
        "final_equity": round(final_eq, 2),
        "net_profit": round(final_eq - init, 2),
        "return_pct": round((final_eq - init) / init * 100.0, 4),
        "open_profit_at_end": round(sc["open_profit_at_end"], 2),
        "max_drawdown_usd": round(sc["max_drawdown_usd"], 2),
        "max_drawdown_pct": round(sc["max_drawdown_pct"], 3),
        "min_equity": round(sc["min_equity"], 2),
        "max_floating_loss": round(sc["max_floating_loss"], 2),
        "max_lots": round(sc["max_lots"], 2),
        "max_positions": int(sc["max_positions"]),
        "max_margin_used": round(sc["max_margin_used"], 2),
        "min_margin_level_pct": (round(sc["min_margin_level_pct"], 1)
                                 if math.isfinite(sc["min_margin_level_pct"]) else None),
        "stopped_out": bool(sc["stopped_out"]),
        "baskets": n,
        "baskets_per_day": round(n / ran_days, 2),
        "ladder_adds": int(ct["ladder_adds"]),
    }
    if n == 0:
        out.update(win_rate_pct=float("nan"), profit_factor=float("nan"), expectancy=float("nan"))
        return out

    pnl = b["pnl"].to_numpy()
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
    out.update(
        win_rate_pct=round(len(wins) / n * 100.0, 2),
        profit_factor=round(_safe_div(gross_win, gross_loss), 3),
        expectancy=round(float(pnl.mean()), 4),
        gross_profit=round(gross_win, 2),
        gross_loss=round(-gross_loss, 2),
        avg_win=round(float(wins.mean()), 3) if len(wins) else 0.0,
        avg_loss=round(float(losses.mean()), 3) if len(losses) else 0.0,
        payoff_ratio=round(_safe_div(float(wins.mean()) if len(wins) else 0.0,
                                     float(-losses.mean()) if len(losses) else float("nan")), 3),
        largest_win=round(float(pnl.max()), 2),
        largest_loss=round(float(pnl.min()), 2),
        median_duration_s=round(float(b["duration_s"].median()), 1),
        mean_duration_s=round(float(b["duration_s"].mean()), 1),
        pct_baskets_under_60s=round(float((b["duration_s"] < 60).mean() * 100.0), 2),
        long_baskets=int((b["side"] == "BUY").sum()),
        short_baskets=int((b["side"] == "SELL").sum()),
        long_pnl=round(float(b.loc[b["side"] == "BUY", "pnl"].sum()), 2),
        short_pnl=round(float(b.loc[b["side"] == "SELL", "pnl"].sum()), 2),
        worst_mae=round(float(b["mae"].min()), 2),
        return_over_max_dd=round(_safe_div(final_eq - init, sc["max_drawdown_usd"]), 3),
    )
    # breakeven win rate implied by the realised average win / loss
    if len(wins) and len(losses):
        out["breakeven_win_rate_pct"] = round(float(-losses.mean() / (wins.mean() - losses.mean()) * 100.0), 2)
    # consecutive losers
    streak = best = 0
    for x in pnl:
        streak = streak + 1 if x < 0 else 0
        best = max(best, streak)
    out["max_consecutive_losses"] = int(best)
    # exit-reason attribution
    for reason, g in b.groupby("reason"):
        key = reason or "none"
        out[f"n_{key}"] = int(len(g))
        out[f"pnl_{key}"] = round(float(g["pnl"].sum()), 2)
    # ladder depth attribution
    for depth, g in b.groupby("n_pos"):
        out[f"n_depth{int(depth)}"] = int(len(g))
        out[f"pnl_depth{int(depth)}"] = round(float(g["pnl"].sum()), 2)

    dr = daily_returns(res.equity, init)
    if len(dr) >= 5 and dr.std() > 0:
        out["daily_sharpe"] = round(float(dr.mean() / dr.std() * math.sqrt(365.0 if cfg.symbol.startswith("BTC") else 252.0)), 3)
        downside = dr[dr < 0]
        if len(downside) >= 2 and downside.std() > 0:
            out["daily_sortino"] = round(float(dr.mean() / downside.std() * math.sqrt(365.0 if cfg.symbol.startswith("BTC") else 252.0)), 3)
        out["best_day_pct"] = round(float(dr.max() * 100.0), 3)
        out["worst_day_pct"] = round(float(dr.min() * 100.0), 3)
        out["pct_days_positive"] = round(float((dr > 0).mean() * 100.0), 2)
    return out


def score_row(res, account: float = ACCOUNT) -> Dict[str, float]:
    """
    Compact metrics for sweeps (no equity series needed).

    ``acct_*`` say what the same baskets would have done to a real ``account`` with the bot's own
    lot sizing (see ``replay_account``). For a run that already is such an account they simply
    repeat the run's own figures.
    """
    cfg, b, sc, ct = res.cfg, res.baskets, res.scalars, res.counters
    init = float(cfg.initial_balance)
    n = int(len(b))
    pnl = b["pnl"].to_numpy() if n else np.zeros(0)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    net = sc["final_equity"] - init
    if cfg.fixed_units > 0 or abs(init - account) > 1e-9:
        acct = replay_account(b, account, cfg.step_up_balance, cfg.unit_max_limit,
                              open_profit=sc["open_profit_at_end"], open_mae=sc.get("open_mae_at_end", 0.0),
                              open_units=max(int(sc.get("open_units_at_end", 0) or 0), 1))
    else:
        acct = {"acct_net": round(net, 2), "acct_wiped": bool(sc["stopped_out"]),
                "acct_dip": round(min(max(init - sc["min_equity"], 0.0), init), 2),
                "acct_max_units": int(b["units"].max()) if n else 1}
    return {
        **acct,
        "net_profit": round(net, 2),
        "return_pct": round(net / init * 100.0, 3),
        "max_dd_usd": round(sc["max_drawdown_usd"], 2),
        "max_dd_pct": round(sc["max_drawdown_pct"], 3),
        "ret_over_dd": round(_safe_div(net, sc["max_drawdown_usd"]), 3),
        "baskets": n,
        "win_rate_pct": round(len(wins) / n * 100.0, 2) if n else float("nan"),
        "profit_factor": round(_safe_div(float(wins.sum()), float(-losses.sum())), 3) if n else float("nan"),
        "expectancy": round(float(pnl.mean()), 4) if n else float("nan"),
        "avg_win": round(float(wins.mean()), 3) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 3) if len(losses) else 0.0,
        "largest_loss": round(float(pnl.min()), 2) if n else 0.0,
        "ladder_adds": int(ct["ladder_adds"]),
        "max_lots": round(sc["max_lots"], 2),
        "max_positions": int(sc["max_positions"]),
        "min_equity": round(sc["min_equity"], 2),
        # deepest the account ever stood below its starting balance (floating included)
        "max_loss_from_start": round(max(init - sc["min_equity"], 0.0), 2),
        "stopped_out": bool(sc["stopped_out"]),
        "pct_under_60s": round(float((b["duration_s"] < 60).mean() * 100.0), 2) if n else float("nan"),
        "median_duration_s": round(float(b["duration_s"].median()), 1) if n else float("nan"),
    }
