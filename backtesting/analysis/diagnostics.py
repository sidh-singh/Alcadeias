"""
Flaw diagnostics: plain measurements of *how* a run made and lost its money.

Each function looks at one mechanism of the strategy and returns numbers that can be
checked against the trade tables:

* ``payoff``   the win-rate / pay-off balance and how concentrated the losses are
* ``ladder``   whether the DCA ladder actually averages (time and price between adds)
* ``exits``    what the force-close does for a losing basket, and how far winners dipped
* ``costs``    spread paid against what the baskets earned gross

``diagnose(result)`` bundles them; ``findings(result)`` turns them into sentences for
the report.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..config import TF_SECONDS


def _unit_px(res) -> float:
    """Price move worth $1 of P/L on one unit (mtqty lots)."""
    return 1.0 / (res.cfg.mtqty * res.cfg.spec.contract_size)


def payoff(res) -> Dict[str, float]:
    b = res.baskets
    if len(b) == 0:
        return {}
    pnl = b["pnl"].to_numpy()
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_win = float(wins.sum())
    srt = np.sort(pnl)
    out = {
        "baskets": int(len(b)),
        "win_rate_pct": float(len(wins) / len(b) * 100),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "median_win": float(np.median(wins)) if len(wins) else 0.0,
        "gross_win": gross_win,
        "gross_loss": float(losses.sum()),
        "worst_basket": float(pnl.min()),
        "worst_basket_in_avg_wins": float(-pnl.min() / wins.mean()) if len(wins) else float("nan"),
    }
    if len(wins) and len(losses):
        out["breakeven_win_rate_pct"] = float(-losses.mean() / (wins.mean() - losses.mean()) * 100)
    for k in (1, 5, 10, 25):
        if len(srt) >= k:
            worst = float(srt[:k].clip(max=0).sum())
            out[f"worst_{k}_sum"] = worst
            out[f"worst_{k}_pct_of_gross_win"] = float(-worst / gross_win * 100) if gross_win > 0 else float("nan")
    # how many winners does one average loser cancel
    if len(wins) and len(losses):
        out["wins_to_repay_avg_loss"] = float(-losses.mean() / wins.mean())
    return out


def ladder(res) -> Dict[str, object]:
    f, b = res.fills, res.baskets
    e = f[f["action"].isin(["open", "add"])].sort_values(["basket", "time"]).copy()
    if len(e) == 0:
        return {}
    upx = _unit_px(res)
    e["dt"] = e.groupby("basket")["time"].diff().dt.total_seconds()
    e["dpx"] = e.groupby("basket")["price"].diff().abs() / upx      # in $ of P/L per unit
    a = e[e["action"] == "add"]
    out: Dict[str, object] = {"adds": int(len(a)), "baskets_with_adds": int(a["basket"].nunique()),
                              "baskets": int(len(b))}
    if len(a) == 0:
        return out
    out.update(
        median_seconds_since_previous_fill=float(a["dt"].median()),
        pct_adds_within_3s=float((a["dt"] <= 3).mean() * 100),
        pct_adds_within_10s=float((a["dt"] <= 10).mean() * 100),
        pct_adds_within_60s=float((a["dt"] <= 60).mean() * 100),
        median_price_gap_usd_per_unit=float(a["dpx"].median()),
        pct_adds_closer_than_1usd=float((a["dpx"] < 1.0).mean() * 100),
    )
    tiers = []
    for tier, g in a.groupby("tier"):
        tiers.append({"tier": tier, "adds": int(len(g)), "median_seconds": float(g["dt"].median()),
                      "pct_within_10s": float((g["dt"] <= 10).mean() * 100),
                      "median_gap_usd_per_unit": float(g["dpx"].median())})
    out["by_tier"] = sorted(tiers, key=lambda t: TF_SECONDS.get(t["tier"], 0))
    depth = []
    for n_pos, g in b.groupby("n_pos"):
        depth.append({"positions": int(n_pos), "baskets": int(len(g)), "net": float(g["pnl"].sum()),
                      "win_rate_pct": float((g["pnl"] > 0).mean() * 100),
                      "avg_win": float(g.loc[g["pnl"] > 0, "pnl"].mean()) if (g["pnl"] > 0).any() else 0.0,
                      "avg_loss": float(g.loc[g["pnl"] < 0, "pnl"].mean()) if (g["pnl"] < 0).any() else 0.0,
                      "worst": float(g["pnl"].min())})
    out["by_depth"] = depth
    out["net_without_adds"] = float(b.loc[b["n_pos"] == 1, "pnl"].sum())
    out["net_with_adds"] = float(b.loc[b["n_pos"] > 1, "pnl"].sum())
    n_max = int(b["n_pos"].max())
    full = b[b["n_pos"] == n_max]
    if n_max > 1 and len(full):
        span, rng = [], []
        for bid in full["basket"]:
            g = e[e["basket"] == bid]
            span.append((g["time"].max() - g["time"].min()).total_seconds())
            rng.append((g["price"].max() - g["price"].min()) / upx)
        out["full_ladder"] = {
            "positions": n_max, "baskets": int(len(full)), "net": float(full["pnl"].sum()),
            "win_rate_pct": float((full["pnl"] > 0).mean() * 100),
            "avg_win": float(full.loc[full["pnl"] > 0, "pnl"].mean()) if (full["pnl"] > 0).any() else 0.0,
            "avg_loss": float(full.loc[full["pnl"] < 0, "pnl"].mean()) if (full["pnl"] < 0).any() else 0.0,
            "worst": float(full["pnl"].min()),
            "median_seconds_entry_to_full": float(np.median(span)),
            "pct_full_within_60s": float((np.asarray(span) <= 60).mean() * 100),
            "median_price_range_usd_per_unit": float(np.median(rng)),
        }
    return out


def exits(res) -> Dict[str, object]:
    b = res.baskets
    if len(b) == 0:
        return {}
    los, win = b[b["pnl"] < 0], b[b["pnl"] > 0]
    out: Dict[str, object] = {}
    by = []
    for reason, g in b.groupby("reason"):
        by.append({"reason": reason or "open at end", "baskets": int(len(g)), "net": float(g["pnl"].sum()),
                   "win_rate_pct": float((g["pnl"] > 0).mean() * 100), "avg": float(g["pnl"].mean()),
                   "worst": float(g["pnl"].min()), "median_hold_s": float(g["duration_s"].median())})
    out["by_reason"] = by
    if len(los):
        out.update(
            losers=int(len(los)),
            loser_median_hold_s=float(los["duration_s"].median()),
            loser_p90_hold_s=float(los["duration_s"].quantile(0.9)),
            loser_max_hold_s=float(los["duration_s"].max()),
            # a loser closed within 10% of its worst floating loss = the exit fired at the bottom
            pct_losers_closed_at_worst=float((los["pnl"] <= los["mae"] * 0.9).mean() * 100),
            pct_losers_that_were_in_profit=float((los["mfe"] >= 0.5 * los["units"]).mean() * 100),
            loser_median_mae=float(los["mae"].median()),
        )
    if len(win):
        out.update(
            winner_median_mae=float(win["mae"].median()),
            winner_p95_mae=float(win["mae"].quantile(0.05)),
            winner_worst_mae=float(win["mae"].min()),
            pct_winners_held_under_60s=float((win["duration_s"] < 60).mean() * 100),
        )
    return out


def costs(res) -> Dict[str, float]:
    f, b = res.fills, res.baskets
    if len(f) == 0:
        return {}
    opens = f[f["action"].isin(["open", "add"])]
    c = res.cfg.spec.contract_size
    spread_paid = float(((opens["ask"] - opens["bid"]) * opens["lots"] * c).sum())
    gross_win = float(b.loc[b["pnl"] > 0, "pnl"].sum()) if len(b) else 0.0
    net = float(b["pnl"].sum()) if len(b) else 0.0
    first = f[f["action"] == "open"]
    return {
        "spread_paid": spread_paid,
        "net": net,
        "net_before_spread": net + spread_paid,
        "spread_pct_of_gross_win": spread_paid / gross_win * 100 if gross_win > 0 else float("nan"),
        "median_entry_spread_usd_per_unit": float(((first["ask"] - first["bid"]) / _unit_px(res)).median()) if len(first) else float("nan"),
    }


def diagnose(res) -> Dict[str, object]:
    return {"payoff": payoff(res), "ladder": ladder(res), "exits": exits(res), "costs": costs(res)}


def _usd(x: float) -> str:
    return ("-" if x < 0 else "") + f"${abs(x):,.2f}"


def findings(res) -> List[Dict[str, str]]:
    """Sentences for the report. Only states what the numbers of *this* run show."""
    d = diagnose(res)
    p, l, x, c = d["payoff"], d["ladder"], d["exits"], d["costs"]
    out: List[Dict[str, str]] = []
    if not p:
        return out
    if "breakeven_win_rate_pct" in p:
        gap = p["win_rate_pct"] - p["breakeven_win_rate_pct"]
        out.append({
            "title": f"{p['win_rate_pct']:.1f}% of baskets win, and it needs {p['breakeven_win_rate_pct']:.1f}% to break even",
            "detail": (f"The average winner is {_usd(p['avg_win'])}, the average loser {_usd(p['avg_loss'])}: one average loss "
                       f"cancels {p['wins_to_repay_avg_loss']:.0f} wins. The worst basket ({_usd(p['worst_basket'])}) cancels "
                       f"{p['worst_basket_in_avg_wins']:.0f}. "
                       + (f"The 10 worst baskets gave back {p['worst_10_pct_of_gross_win']:.0f}% of everything the winners made. "
                          if "worst_10_pct_of_gross_win" in p else "")
                       + ("The margin over break-even is " + f"{gap:+.1f} points." if abs(gap) < 50 else ""))})
    if l.get("adds"):
        late = [t for t in l.get("by_tier", []) if TF_SECONDS.get(t["tier"], 0) >= 900]
        if late:
            worst_t = max(late, key=lambda t: t["pct_within_10s"])
            out.append({
                "title": "The ladder's big tiers fire together, at one price",
                "detail": (f"{l['pct_adds_within_3s']:.0f}% of all ladder adds came within 3 seconds of the previous fill. "
                           "By tier: "
                           + "; ".join(f"{t['tier']} fired within 10 s of the add before it {t['pct_within_10s']:.0f}% of the "
                                       f"time (median {t['median_seconds']:.0f} s later, {_usd(t['median_gap_usd_per_unit'])} "
                                       f"per unit away)" for t in late)
                           + ". Those tiers carry most of the basket's size, so the 'averaging' is one large clip, not a ladder.")})
        if "full_ladder" in l:
            fl = l["full_ladder"]
            out.append({
                "title": f"Full ladders: {fl['win_rate_pct']:.0f}% win {_usd(fl['avg_win'])}, the rest lose {_usd(fl['avg_loss'])}",
                "detail": (f"{fl['baskets']} baskets reached all {fl['positions']} positions; together they made "
                           f"{_usd(fl['net'])} (worst {_usd(fl['worst'])}). Baskets with no add made "
                           f"{_usd(l['net_without_adds'])} in total; baskets with at least one add made {_usd(l['net_with_adds'])}.")})
    if x.get("losers"):
        out.append({
            "title": "The slope exit closes losers near their worst price",
            "detail": (f"{x['pct_losers_closed_at_worst']:.0f}% of losing baskets were closed within 10% of the largest loss they "
                       f"ever showed. Losers were held a median {x['loser_median_hold_s'] / 60:.0f} minutes (one in ten longer than "
                       f"{x['loser_p90_hold_s'] / 3600:.1f} h, the longest {x['loser_max_hold_s'] / 3600:.1f} h); "
                       f"{x['pct_losers_that_were_in_profit']:.0f}% of them had been in profit first. Winners were at worst "
                       f"{_usd(x.get('winner_worst_mae', 0.0))} under water before coming back.")})
    if c:
        out.append({
            "title": f"Spread paid: {_usd(c['spread_paid'])}",
            "detail": (f"That is {c['spread_pct_of_gross_win']:.0f}% of the gross profit of the winning baskets; before spread the "
                       f"run would have netted {_usd(c['net_before_spread'])} instead of {_usd(c['net'])}. Median spread at entry: "
                       f"{_usd(c['median_entry_spread_usd_per_unit'])} per unit.")})
    return out
