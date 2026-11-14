"""
BACKTEST.md generator.

The write-up at the repository root is assembled from the committed result files so the
numbers in it cannot drift from the data: ``python -m backtesting docs`` re-creates it.
Interpretation that cannot be computed -- the list of flaws, the recommendations and the
live-code audit -- is read from three hand-written files in the results directory:
``findings.json``, ``recommendations.md`` and ``audit.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from ..config import BacktestConfig, REPO_ROOT, TF_SECONDS

ACCOUNT = 2000.0
WIN_LABEL = {"IS": "Aug–Nov 2026", "OOS1": "May–Aug 2026", "OOS2": "Feb–May 2026",
             "HO2": "Nov 2025–Feb 2026", "HO1": "Aug–Nov 2025"}


def _j(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _usd(x, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    s = f"{abs(x):,.0f}" if abs(x) >= 100 else f"{abs(x):,.2f}"
    sign = ("+" if x > 0 else "−" if x < 0 else "") if signed else ("−" if x < 0 else "")
    return f"{sign}${s}"


def _table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join("---" if i == 0 else "---:" for i in range(len(cols))) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def _windows(df: pd.DataFrame) -> List[str]:
    return [c.split("@")[1] for c in df.columns if c.startswith("net_profit@")]


def _cell(net: float, dip: float) -> str:
    return _usd(net) + (" ✕" if dip >= ACCOUNT else "")


# ───────────────────────────── sections ─────────────────────────────

def sec_runs(out: Path, symbols: Sequence[str]) -> str:
    rows = []
    for name, label in (("baseline", "3 months: 13 Aug → 13 Nov 2026"), ("long", "15 months: 13 Aug 2025 → 13 Nov 2026")):
        for sym in symbols:
            j = _j(out / name / sym / "summary.json")
            if not j:
                continue
            s = j["summary"]
            fu = _j(out / name / sym / "fixed_unit.json") or {}
            rows.append({
                "Run": f"[{sym} · {label}](backtest_results/{name}/{sym}/report.html)",
                "Net P/L": _usd(s["net_profit"]),
                "Return": f"{s['return_pct']:+.1f}%",
                "Max drawdown": f"{_usd(s['max_drawdown_usd'], False)} ({s['max_drawdown_pct']:.0f}%)",
                "Baskets": f"{s['baskets']:,}",
                "Win rate": f"{s.get('win_rate_pct', float('nan')):.1f}%",
                "Needed to break even": f"{s.get('breakeven_win_rate_pct', float('nan')):.1f}%",
                "Avg win / avg loss": f"{_usd(s.get('avg_win', 0))} / {_usd(s.get('avg_loss', 0))}",
                "Worst basket": _usd(s.get("largest_loss", 0)),
                "Stopped out": "**yes**" if s["stopped_out"] else "no",
                "Same run, fixed 0.01-lot unit": _usd(fu.get("net_profit", float("nan"))),
            })
    return _table(pd.DataFrame(rows)) if rows else ""


def sec_images(out: Path, sym: str) -> str:
    img = out / "img"
    parts = []
    for name, cap in ((f"{sym}_overview.png", "Three months at a glance: price with every exit, account, exposure, scores."),
                      (f"{sym}_zoom.png", "Thirty hours up close: every entry, ladder add and exit at its fill price."),
                      (f"{sym}_attribution.png", "Where the money came from and where it went."),
                      (f"{sym}_worst_basket.png", "The worst basket, second by second."),
                      (f"{sym}_long_equity.png", "The same settings over the whole history.")):
        if (img / name).exists():
            parts.append(f"![{cap}](backtest_results/img/{name})\n\n*{cap}*")
    return "\n\n".join(parts)


def sec_diagnostics(out: Path, sym: str) -> str:
    d = _j(out / "baseline" / sym / "diagnostics.json")
    if not d or not d.get("payoff"):
        return ""
    p, l, x, c = d["payoff"], d["ladder"], d["exits"], d["costs"]
    lines = [
        f"- **Pay-off.** {p['win_rate_pct']:.1f}% of {p['baskets']:,} baskets won; break-even needs "
        f"{p.get('breakeven_win_rate_pct', float('nan')):.1f}%. Average win {_usd(p['avg_win'])}, average loss "
        f"{_usd(p['avg_loss'])} (one loss = {p.get('wins_to_repay_avg_loss', float('nan')):.0f} wins). The worst basket "
        f"({_usd(p['worst_basket'])}) cancelled {p['worst_basket_in_avg_wins']:.0f} average wins; the ten worst gave back "
        f"{p.get('worst_10_pct_of_gross_win', float('nan')):.0f}% of everything the winners made.",
    ]
    if l.get("adds"):
        tiers = "; ".join(f"{t['tier']} {t['pct_within_10s']:.0f}% (median {t['median_seconds']:.0f} s, "
                          f"{_usd(t['median_gap_usd_per_unit'], False)} away)" for t in l.get("by_tier", []))
        lines.append(f"- **Ladder.** {l['adds']:,} adds in {l['baskets_with_adds']:,} baskets. Share of each tier's adds that "
                     f"came within 10 s of the previous fill: {tiers}. Baskets with no add: {_usd(l['net_without_adds'])}; "
                     f"baskets with at least one add: {_usd(l['net_with_adds'])}.")
        if "full_ladder" in l:
            fl = l["full_ladder"]
            lines.append(f"- **Full ladders.** {fl['baskets']} baskets reached all {fl['positions']} positions: "
                         f"{fl['win_rate_pct']:.0f}% won {_usd(fl['avg_win'])} on average, the rest lost {_usd(fl['avg_loss'])} "
                         f"on average (worst {_usd(fl['worst'])}); net {_usd(fl['net'])}.")
    if x.get("losers"):
        lines.append(f"- **Exits.** {x['pct_losers_closed_at_worst']:.0f}% of losing baskets were closed within 10% of the largest "
                     f"loss they ever showed. Losers were held a median {x['loser_median_hold_s'] / 60:.0f} min, the longest "
                     f"{x['loser_max_hold_s'] / 3600:.1f} h. Winners were at worst {_usd(x.get('winner_worst_mae', 0))} under "
                     f"water before recovering.")
    if c:
        lines.append(f"- **Spread.** {_usd(c['spread_paid'], False)} paid, {c['spread_pct_of_gross_win']:.0f}% of the winners' gross "
                     f"profit. Before spread the run nets {_usd(c['net_before_spread'])}; after it {_usd(c['net'])}.")
    return "\n".join(lines)


def _norm(s: str) -> str:
    return "+".join(sorted(str(s).split("+"), key=TF_SECONDS.get, reverse=True))


def cell_noise(out: Path, sym: str) -> str:
    """How far one sweep cell moves with nothing changed but the loop timing (the live setting, fixed unit)."""
    from ..analysis.robustness import ensemble_summary
    p = out / "robustness" / sym / "quarters_timing_fixed_unit.csv"
    if not p.exists():
        return ""
    e = ensemble_summary(pd.read_csv(p))
    spread = e["net_max"] - e["net_min"]
    parts = "; ".join(f"{WIN_LABEL.get(w, w)} {_usd(a)} to {_usd(b)}" for w, a, b in zip(e["window"], e["net_min"], e["net_max"]))
    return (f"**How much of one cell is luck.** The live setting itself, at the same fixed 0.01-lot unit, run eight times per "
            f"quarter on raw ticks with nothing changed but the loop timing: {parts}. The spread inside one quarter was "
            f"{_usd(float(spread.median()), False)} at the median and {_usd(float(spread.max()), False)} at most. Differences of "
            f"that size between two settings in the tables below are not evidence; only patterns that repeat across quarters are.")


def sec_timeframes(out: Path, sym: str, base: BacktestConfig) -> str:
    p = out / "sweeps" / f"{sym}_timeframes.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    wins = _windows(df)
    net = [f"net_profit@{w}" for w in wins]
    df["open"], df["fc"] = df["open"].map(_norm), df["fc"].map(_norm)
    df["total"] = df[net].sum(axis=1)
    df["worst"] = df[net].min(axis=1)
    df["n_pos"] = (df[net] > 0).sum(axis=1)
    df["n_ruin"] = (df[[f"max_loss_from_start@{w}" for w in wins]] >= ACCOUNT).sum(axis=1)
    live_open, live_fc = _norm("+".join(base.open_weights)), _norm("+".join(base.fc_weights))
    strict = "strict" if (base.entry_s >= 2.0 * len(base.open_weights) and len(base.open_weights) > 1) else "loose"
    lvl = "half" if base.force_close_s <= 1.0 else "full"
    live = df[(df["open"] == live_open) & (df["fc"] == live_fc) & (df["entry"] == strict) & (df["fc_level"] == lvl)]
    out_lines = []
    stats = []
    for w in wins:
        stats.append({"Window": WIN_LABEL.get(w, w),
                      "Combinations profitable": f"{(df[f'net_profit@{w}'] > 0).mean() * 100:.0f}%",
                      "Median net": _usd(df[f"net_profit@{w}"].median()),
                      "Best": _usd(df[f"net_profit@{w}"].max()),
                      "Worst": _usd(df[f"net_profit@{w}"].min()),
                      "Would have wiped $2,000": f"{(df[f'max_loss_from_start@{w}'] >= ACCOUNT).mean() * 100:.0f}%"})
    out_lines.append(_table(pd.DataFrame(stats)))
    ok = int(((df["n_pos"] == len(wins)) & (df["n_ruin"] == 0)).sum())
    out_lines.append(f"\n{len(df)} combinations of OPEN timeframes × FORCE-CLOSE timeframe × threshold convention. "
                     f"**{ok}** made money in all {len(wins)} windows without ever standing $2,000 below the start; "
                     f"{int((df['n_ruin'] > 0).sum())} would have wiped out a $2,000 account in at least one window.")
    noise = cell_noise(out, sym)
    if noise:
        out_lines.append("\n" + noise)
    ag = _j(out / "sweeps" / f"{sym}_timeframes_agreement.json") or {}
    if ag:
        rows = []
        for k, v in ag.items():
            a, b = k.split("->")
            if "spearman" not in v:
                continue
            rows.append({"Chosen on → tested on": f"{WIN_LABEL.get(a, a)} → {WIN_LABEL.get(b, b)}",
                         "Rank correlation": f"{v['spearman']:+.2f}",
                         "Top 10% there": _usd(v.get(f"top_decile_mean_{a}", float("nan"))),
                         "Same settings here": _usd(v.get(f"top_decile_mean_{b}", float("nan"))),
                         "Best single setting there → here": f"{_usd(v.get(f'best_{a}', float('nan')))} → "
                                                             f"{_usd(v.get(f'best_{a}_then_{b}', float('nan')))}"})
        if rows:
            out_lines.append("\nDoes choosing on one window work on another?\n\n" + _table(pd.DataFrame(rows)))
    top = df.sort_values(["n_ruin", "n_pos", "worst"], ascending=[True, False, False]).head(10)
    show = pd.concat([live.assign(_tag="**live**"), top.assign(_tag="")]).drop_duplicates(
        subset=["open", "fc", "entry", "fc_level"])
    t = pd.DataFrame({
        "": show["_tag"], "OPEN": show["open"], "FORCE-CLOSE": show["fc"],
        "Entry needs": show["entry"].map({"loose": "one TF fully aligned", "strict": "every TF fully aligned"}),
        "FC fires on": show["fc_level"].map({"half": "one indicator reversing", "full": "both reversing"}),
        **{WIN_LABEL.get(w, w): [_cell(n, d) for n, d in zip(show[f"net_profit@{w}"], show[f"max_loss_from_start@{w}"])]
           for w in wins},
        "Deepest dip": show[[f"max_loss_from_start@{w}" for w in wins]].max(axis=1).map(lambda v: _usd(v, False)),
        "Baskets / window": show[[f"baskets@{w}" for w in wins]].mean(axis=1).map(lambda v: f"{v:,.0f}"),
    })
    out_lines.append("\nThe live setting and the ten that held up best (sorted by windows survived, windows profitable, worst "
                     "window). Net P/L of one 0.01-lot unit; ✕ = the loss exceeded $2,000 at some point.\n\n" + _table(t))
    # main effects
    rows = []
    for tf in sorted({x for s in df["open"] for x in s.split("+")}, key=TF_SECONDS.get, reverse=True):
        m = df[df["open"].map(lambda s: tf in s.split("+"))]
        rows.append({"Timeframe": tf, "in OPEN: mean net / window": _usd(m[net].mean().mean()),
                     "in OPEN: wiped $2,000": f"{(m[[f'max_loss_from_start@{w}' for w in wins]] >= ACCOUNT).mean().mean() * 100:.0f}%",
                     "as FORCE-CLOSE: mean net / window": _usd(df[df["fc"] == tf][net].mean().mean()),
                     "as FORCE-CLOSE: wiped $2,000": f"{(df[df['fc'] == tf][[f'max_loss_from_start@{w}' for w in wins]] >= ACCOUNT).mean().mean() * 100:.0f}%"})
    out_lines.append("\nAveraged over every combination that contains the timeframe:\n\n" + _table(pd.DataFrame(rows)))
    return "\n".join(out_lines)


def sec_split(out: Path, sym: str, kind: str) -> str:
    p = out / "sweeps" / f"{sym}_{kind}.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    wins = _windows(df)
    sec = {"split_open": "open", "split_fc": "fc", "split_book": "book"}[kind]
    rc, mc = f"{sec}_rsi", f"{sec}_macd"
    tfs = sorted(set(df[rc]) | set(df[mc]), key=lambda s: -TF_SECONDS.get(s, 0))
    df["total"] = df[[f"net_profit@{w}" for w in wins]].sum(axis=1)
    df["dip"] = df[[f"max_loss_from_start@{w}" for w in wins]].max(axis=1)
    df["n_pos"] = (df[[f"net_profit@{w}" for w in wins]] > 0).sum(axis=1)
    piv = df.pivot_table(index=rc, columns=mc, values="total", aggfunc="mean").reindex(index=tfs, columns=tfs)
    dip = df.pivot_table(index=rc, columns=mc, values="dip", aggfunc="max").reindex(index=tfs, columns=tfs)
    npos = df.pivot_table(index=rc, columns=mc, values="n_pos", aggfunc="max").reindex(index=tfs, columns=tfs)
    rows = []
    for r in tfs:
        row = {"RSI ↓ / MACD →": f"**{r}**"}
        for m in tfs:
            v = piv.loc[r, m]
            row[m] = "–" if pd.isna(v) else f"{_cell(v, dip.loc[r, m])} ({int(npos.loc[r, m])}/{len(wins)})"
        rows.append(row)
    name = {"open": "OPEN", "fc": "FORCE-CLOSE", "book": "BOOK"}[sec]
    return (f"**{name}: RSI slope on one timeframe, MACD slope on another.** Three windows added up, one 0.01-lot unit; "
            f"in brackets the number of windows that were profitable; ✕ = the loss exceeded $2,000 at some point. The "
            f"diagonal is both indicators on the same timeframe.\n\n" + _table(pd.DataFrame(rows)))


def _signal_frame(out: Path, sym: str, tf: str, horizon: int = 4) -> Optional[pd.DataFrame]:
    from ..analysis.signal import vote_table
    t = vote_table(out, sym, tf, horizon)
    if t is None:
        return None
    f = lambda v: f"{v:.0f}%"
    return pd.DataFrame({
        "Period": t["period"], f"{tf} bars": t["bars"].map(lambda v: f"{v:,}"),
        "MACD vote against its own trend": t["macd_against_trend_pct"].map(f),
        "RSI up-votes that follow an oversold low": t["rsi_up_from_oversold_low_pct"].map(f),
        "Both votes up (share of bars)": t["both_up_share_pct"].map(f),
        f"… price higher {horizon} bars later": t["higher_after_both_up_pct"].map(lambda v: f"**{v:.1f}%**"),
        "(any bar)": t["higher_all_bars_pct"].map(lambda v: f"{v:.1f}%"),
        "Both votes down (share of bars)": t["both_down_share_pct"].map(f),
        f"… price lower {horizon} bars later": t["lower_after_both_down_pct"].map(lambda v: f"**{v:.1f}%**"),
        "(any bar) ": t["lower_all_bars_pct"].map(lambda v: f"{v:.1f}%"),
    })


def sec_signal(out: Path, sym: str, tf: str) -> str:
    t = _signal_frame(out, sym, tf)
    return _table(t) if t is not None else ""


def sec_holdout(out: Path, sym: str) -> str:
    from ..analysis import holdout as H
    r = H.timeframe_carry_over(out, sym)
    if r is None:
        return ""
    tab, facts = r
    t = pd.DataFrame({
        "On the three analysed quarters the setting was": tab["group"],
        "Settings": tab["settings"],
        "Profitable in both hold-out quarters": tab["both_holdout_profitable_pct"].map(lambda v: f"{v:.0f}%"),
        "In at least one": tab["one_or_more_pct"].map(lambda v: f"{v:.0f}%"),
        "Wiped $2,000 in the hold-out": tab["wiped_in_holdout_pct"].map(lambda v: f"{v:.0f}%"),
        "Mean hold-out net per quarter": tab["mean_holdout_net_per_quarter"].map(_usd),
        "Median": tab["median_holdout_net_per_quarter"].map(_usd),
    })
    lines = [_table(t),
             f"\nAcross all {facts['settings']} settings: {facts['base_both_profitable_pct']:.0f}% were profitable in both hold-out "
             f"quarters, {facts['base_wiped_pct']:.0f}% would have wiped $2,000 in one of them, mean {_usd(facts['base_mean_net_per_quarter'])} "
             f"per quarter. Rank correlation between the three-quarter total and the hold-out total: {facts['rank_correlation']:+.2f}."]
    best = H.best_survivors(out, sym, 8)
    if best is not None and len(best):
        b = pd.DataFrame({
            "OPEN": best["open"].map(_norm), "FORCE-CLOSE": best["fc"].map(_norm),
            "Entry / FC": best["entry"] + " / " + best["fc_level"],
            **{WIN_LABEL[w]: [_cell(n, d) for n, d in zip(best[f"net_profit@{w}"], best[f"max_loss_from_start@{w}"])]
               for w in H.ANALYSED},
            **{WIN_LABEL[w] + " (hold-out)": [_cell(n, d) for n, d in zip(best[f"net_profit@{w}"], best[f"max_loss_from_start@{w}"])]
               for w in H.HELD_OUT},
        })
        lines.append("\nThe eight settings one would have picked from the analysed quarters (windows survived, windows profitable, "
                     "worst window), and what they then did on the hold-out:\n\n" + _table(b))
    return "\n".join(lines)


def sec_candidates(out: Path, sym: str) -> str:
    from ..analysis import holdout as H
    df = H.candidate_table(out, sym)
    if df is None:
        return ""
    wins = [w for w in H.ANALYSED + H.HELD_OUT if f"net_profit@{w}" in df.columns]
    name = df["candidate"].map(lambda x: f"**{x}**" if x == "live timeframes · live ladder" else x)
    if all(f"ens_median@{w}" in df.columns for w in wins):
        chrono = [w for w in ("HO1", "HO2", "OOS2", "OOS1", "IS") if w in wins]
        n = df["ens_runs"].astype(int).astype(str)
        t = pd.DataFrame({
            "Setting": name,
            **{WIN_LABEL[w] + (" (hold-out)" if w in H.HELD_OUT else ""):
               [_usd(m) + (" ✕" if k > 0 else "") for m, k in zip(df[f"ens_median@{w}"], df[f"ens_stopped@{w}"])] for w in chrono},
            "Quarter-runs that lost": df["ens_losing_runs"].astype(int).astype(str) + " of " + n,
            "Stopped out": df["ens_stopped_runs"].astype(int).astype(str) + " of " + n,
            "Median quarter-run": df["ens_median"].map(_usd), "Mean": df["ens_mean"].map(_usd),
            "Worst quarter-run": df["ens_worst_run"].map(_usd), "Worst basket": df["ens_worst_basket"].map(_usd),
            "Baskets / quarter": df["ens_baskets_per_quarter"].map(lambda v: f"{v:,.0f}"),
        })
        if "account_net" in df.columns:
            t["One run of all 15 months on $2,000"] = df["account_net"].map(_usd)
            t["stopped out"] = df["account_stopped_out"].map(lambda v: "**yes**" if bool(v) else "no")
        return _table(t)
    t = pd.DataFrame({
        "Setting": df["candidate"].map(lambda x: f"**{x}**" if x == "live timeframes · live ladder" else x),
        **{WIN_LABEL[w] + (" (hold-out)" if w in H.HELD_OUT else ""):
           [_cell(n, d) for n, d in zip(df[f"net_profit@{w}"], df[f"max_loss_from_start@{w}"])] for w in wins},
        "Quarters profitable": df["quarters_profitable"].astype(int).astype(str) + "/" + df["quarters"].astype(int).astype(str),
        "Deepest dip": df["deepest_dip"].map(lambda v: _usd(v, False)),
        "Worst basket": df["worst_basket"].map(_usd),
        "Baskets / quarter": df["baskets_per_quarter"].map(lambda v: f"{v:,.0f}"),
    })
    if "account_net" in df.columns:
        t["$2,000 account, 15 months: net"] = df["account_net"].map(_usd)
        t["max drawdown"] = df["account_max_dd_pct"].map(lambda v: f"{v:.0f}%")
        t["stopped out"] = df["account_stopped_out"].map(lambda v: "**yes**" if bool(v) else "no")
    return _table(t)


def sec_packages(out: Path, sym: str) -> str:
    p = out / "packages" / f"{sym}.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    wins = _windows(df)
    net = [f"net_profit@{w}" for w in wins]
    df["total"] = df[net].sum(axis=1)
    df["dip"] = df[[f"max_loss_from_start@{w}" for w in wins]].max(axis=1)
    df["n_ruin"] = (df[[f"max_loss_from_start@{w}" for w in wins]] >= ACCOUNT).sum(axis=1)
    df["n_pos"] = (df[net] > 0).sum(axis=1)
    live = df[df["package"] == "live settings"]
    rest = df[df["package"] != "live settings"].sort_values(["n_ruin", "total"], ascending=[True, False])
    d = pd.concat([live, rest])
    t = pd.DataFrame({
        "What-if": d["package"].map(lambda s: f"**{s}**" if s == "live settings" else s),
        **{WIN_LABEL.get(w, w): d[f"net_profit@{w}"].map(_usd) for w in wins},
        "Three windows": d["total"].map(_usd),
        "Profitable windows": d["n_pos"].astype(int).astype(str) + f"/{len(wins)}",
        "Deepest dip": d["dip"].map(lambda v: _usd(v, False)),
        "Wiped $2,000 in": d["n_ruin"].astype(int).astype(str) + f"/{len(wins)}",
        "Worst basket": d[[f"largest_loss@{w}" for w in wins]].min(axis=1).map(_usd),
    })
    return _table(t)


def sec_levers(out: Path, sym: str, top: int = 40) -> str:
    p = out / "levers" / f"{sym}.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p, dtype={"value": str})
    wins = _windows(df)
    blocks = []
    for param, g in df.groupby("param", sort=False):
        t = pd.DataFrame({
            param.replace("_", " "): g["value"],
            **{WIN_LABEL.get(w, w): [_cell(n, d) for n, d in zip(g[f"net_profit@{w}"], g[f"max_loss_from_start@{w}"])]
               for w in wins},
            "Three windows": g[[f"net_profit@{w}" for w in wins]].sum(axis=1).map(_usd),
        })
        blocks.append(_table(t))
    return "\n\n".join(blocks)


def sec_quarters(out: Path, sym: str) -> str:
    """Every quarter under eight loop timings: the honest per-quarter figure for the live settings."""
    from ..analysis.robustness import ensemble_summary
    p = out / "robustness" / sym / "quarters_timing.csv"
    if not p.exists():
        return ""
    e = ensemble_summary(pd.read_csv(p))
    t = pd.DataFrame({
        "Quarter": e["window"].map(lambda w: WIN_LABEL.get(w, w) + (" (hold-out)" if w in ("HO1", "HO2") else "")),
        "Median net P/L": e["net_median"].map(_usd),
        "Worst timing": e["net_min"].map(_usd), "Best timing": e["net_max"].map(_usd),
        "Timings that lost money": e["losing_runs"].astype(str) + " of " + e["runs"].astype(str),
        "Timings stopped out": e["stopped_out_runs"].astype(str) + " of " + e["runs"].astype(str),
        "Median max drawdown": e["max_dd_pct_median"].map(lambda v: f"{v:.0f}%"),
        "Worst basket": e["worst_basket"].map(_usd),
        "Baskets (median)": e["baskets_median"].map(lambda v: f"{v:,.0f}"),
    })
    tot = len(e) * int(e["runs"].iloc[0]) if len(e) else 0
    return (_table(t) + f"\n\n{int(e['losing_runs'].sum())} of {tot} quarter-runs lost money; "
            f"{int(e['stopped_out_runs'].sum())} ended with the account stopped out.")


def sec_robust(out: Path, sym: str) -> str:
    d = out / "robustness" / sym
    if not d.exists():
        return ""
    lines = []
    p = d / "timing.csv"
    if p.exists():
        t = pd.read_csv(p)
        poll, lat = t[t["test"] == "poll"], t[t["test"] == "latency"]
        if len(poll):
            lines.append(f"- **Loop timing** ({len(poll)} raw-tick replays, loop every 1.0–2.0 s at different phases): net P/L from "
                         f"{_usd(poll['net_profit'].min())} to {_usd(poll['net_profit'].max())}, median "
                         f"{_usd(poll['net_profit'].median())}; {int((poll['net_profit'] > 0).sum())} of {len(poll)} positive; "
                         f"max drawdown {poll['max_dd_pct'].min():.0f}%–{poll['max_dd_pct'].max():.0f}%.")
        if len(lat):
            lines.append("- **Order latency**: " + "; ".join(
                f"{int(r['latency_ms'])} ms {_usd(r['net_profit'])}" for _, r in lat.iterrows()) + ".")
    p = d / "costs.csv"
    if p.exists():
        t = pd.read_csv(p)
        sp, sl = t[t["test"] == "spread"], t[t["test"] == "slippage"]
        if len(sp):
            lines.append("- **Spread scaled**: " + "; ".join(
                f"×{r['spread_mult']:g} {_usd(r['net_profit'])}" for _, r in sp.iterrows()) + ".")
        if len(sl):
            lines.append("- **Adverse slippage per fill** (price units): " + "; ".join(
                f"{r['slippage']:g} {_usd(r['net_profit'])}" for _, r in sl.iterrows()) + ".")
    p = d / "start_shift.csv"
    if p.exists():
        t = pd.read_csv(p)
        lines.append(f"- **Start date** (same settings and end date, started 0–14 days later, {len(t)} runs): net P/L from "
                     f"{_usd(t['net_profit'].min())} to {_usd(t['net_profit'].max())}; "
                     f"{int((t['net_profit'] > 0).sum())} of {len(t)} positive; "
                     f"{int(t['stopped_out'].sum())} stopped out.")
    p = d / "segments_quarterly.csv"
    if p.exists():
        t = pd.read_csv(p)
        lines.append("- **Five consecutive quarters, a fresh $2,000 each**: " + "; ".join(
            f"{r['segment']} {_usd(r['net_profit'])}" + (" (stopped out)" if bool(r["stopped_out"]) else "")
            for _, r in t.iterrows()) + ".")
    for fn, label in (("segments_monthly.csv", "Each calendar month on a fresh $2,000"),
                      ("segments_weekly.csv", "Each week of the three-month window on a fresh $2,000")):
        p = d / fn
        if p.exists():
            t = pd.read_csv(p)
            lines.append(f"- **{label}** ({len(t)} periods): {int((t['net_profit'] > 0).sum())} positive, "
                         f"{int(t['stopped_out'].sum())} stopped out; best {_usd(t['net_profit'].max())}, worst "
                         f"{_usd(t['net_profit'].min())}, median {_usd(t['net_profit'].median())}.")
    b = _j(d / "bootstrap.json")
    if b and b.get("live_units"):
        x = b["live_units"]
        lines.append(f"- **Same trades in a different order** (5,000 resamplings of whole days, realised P/L only): final balance "
                     f"5th–95th percentile {_usd(x['final_p05'], False)}–{_usd(x['final_p95'], False)}, median "
                     f"{_usd(x['final_p50'], False)}; probability of ending below the start {x['prob_loss'] * 100:.0f}%, of losing "
                     f"more than a quarter {x['prob_loss_over_25pct'] * 100:.0f}%.")
    out_s = "\n".join(lines)
    p = d / "segments_monthly.csv"
    if p.exists():
        t = pd.read_csv(p)
        tt = pd.DataFrame({"Month (fresh $2,000 each)": t["segment"], "Net P/L": t["net_profit"].map(_usd),
                           "Max drawdown": t["max_dd_usd"].map(lambda v: _usd(v, False)),
                           "Baskets": t["baskets"].astype(int), "Win rate": t["win_rate_pct"].map(lambda v: f"{v:.1f}%"),
                           "Worst basket": t["largest_loss"].map(_usd),
                           "Stopped out": t["stopped_out"].map(lambda v: "**yes**" if v else "no")})
        out_s += "\n\n" + _table(tt)
    return out_s


def sec_parity(out: Path) -> str:
    rows = []
    for p in sorted((out / "parity").glob("*.json")) if (out / "parity").exists() else []:
        j = _j(p)
        if not j:
            continue
        rows.append({"Window (UTC)": f"{j.get('symbol')} {j.get('start')} → {j.get('end')}",
                     "Settings": j.get("scores", "") + (" + other overrides" if j.get("config_overrides") else ""),
                     "Live polls": f"{j.get('polls_ref', 0):,}",
                     "Signal / score / fill mismatches": f"{j.get('signal_mismatches')} / {j.get('score_mismatches')} / {j.get('fill_mismatches')}",
                     "Fills": j.get("fills_ref"),
                     "Final balance live = fast": f"{j.get('balance_ref', 0):,.2f} = {j.get('balance_fast', 0):,.2f}",
                     "Result": "identical" if j.get("ok") else "**differs**"})
    if not rows:
        return ""
    total = sum(int(r["Live polls"].replace(",", "")) for r in rows)
    return (f"{total:,} polls of the real `app.py` loop across {len(rows)} windows, compared with the fast engine poll by "
            f"poll:\n\n" + _table(pd.DataFrame(rows)))


def sec_quality(out: Path, symbols: Sequence[str]) -> str:
    rows = []
    for sym in symbols:
        q = _j(out / "data_quality" / f"{sym}.json")
        if not q:
            continue
        sp, g = q["spread"], q["gaps_over_3min"]
        rows.append({"Symbol": sym, "Span": f"{q['first_tick'][:10]} → {q['last_tick'][:10]}", "Ticks": f"{q['ticks_total']:,}",
                     "Dropped / out-of-order rows": f"{q['rows_dropped_invalid']} / {q['rows_out_of_order']}",
                     "Spread median / p99 / max": f"{sp['median']:.2f} / {sp['p99']:.2f} / {sp['max']:.2f}",
                     "Silences > 3 min": f"{g['count']} ({', '.join(f'{v} {k}' for k, v in g['by_kind'].items())})",
                     "Days without ticks": ", ".join(q["days"]["missing"]) or "none"})
    if not rows:
        return ""
    notes = quality_notes(out, symbols)
    return _table(pd.DataFrame(rows)) + ("\n\n" + notes if notes else "")


def quality_notes(out: Path, symbols: Sequence[str]) -> str:
    """Plain sentences about what is missing from the history and how the engine deals with it."""
    parts = []
    for sym in symbols:
        q = _j(out / "data_quality" / f"{sym}.json")
        if not q:
            continue
        holes = q["gaps_over_3min"].get("holes") or []
        if holes:
            lst = "; ".join(f"{h['from'][:16].replace('T', ' ')} → {h['to'][:16].replace('T', ' ')} UTC "
                            f"({h['minutes'] / 60:.1f} h, price {h['price_jump_pct']:+.1f}% across it)" for h in holes)
            parts.append(f"**{sym} has {len(holes)} hole{'s' if len(holes) != 1 else ''} in the archive** — the market traded, the "
                         f"history is missing: {lst}. The backtest does not pretend to know what happened inside them: a basket "
                         f"open at the last quote before a hole is closed there, and no basket is opened for 24 hours after the "
                         f"history resumes (see `data_hole_s` in the README).")
        elif q["days"]["missing"]:
            days = ", ".join(f"{d} ({pd.Timestamp(d).day_name()})" for d in q["days"]["missing"])
            other = q["gaps_over_3min"]["by_kind"].get("other", 0)
            parts.append(f"{sym}: days without ticks other than Saturdays: {days}. A Sunday without ticks is a late weekly open; "
                         f"a weekday is a market holiday (it shows up as a long close in the list of silences). "
                         f"{other} silence{'s' if other != 1 else ''} fit{'' if other != 1 else 's'} no session pattern "
                         f"(`data_quality/{sym}.json` lists them).")
    return "  \n".join(parts)


def build_backtest_md(out: Path, symbols: Sequence[str] = ("XAUUSDm", "BTCUSDm"), live_root: Path = REPO_ROOT,
                      target: Optional[Path] = None) -> Path:
    out = Path(out)
    base = {s: BacktestConfig.live(s, repo_root=live_root) for s in symbols}
    variant = next(iter(base.values())).variant
    netting = variant == "netting"
    exit_rule = ("a slope \"book\" (close when in profit by more than $1 × unit and the M15 score reverses)" if netting
                 else "a fixed target (close when basket profit exceeds $1 × unit)")
    findings = _j(out / "findings.json") or []
    audit = _j(out / "audit.json") or []
    reco_p = out / "recommendations.md"
    reco = reco_p.read_text(encoding="utf-8").strip() if reco_p.exists() else ""

    L: List[str] = []
    A = L.append
    A(f"# Backtest of the {variant} strategy on real Exness ticks\n")
    A(f"This branch adds a tick-level backtester for the live bot and the results of running it. Nothing in the live files "
      f"was changed. The strategy tested is exactly what `strategy.py` / `constants.py` on this branch do: open on the "
      f"{base[symbols[0]].describe_scores().split(' fc[')[0].replace('open[', '').rstrip(']')} slope score with full M15 "
      f"agreement, an RSI ladder of Fibonacci-sized adds, a force-close on an M15 slope reversal, and as profit exit {exit_rule}.\n")
    A("- **Results page:** [`backtest_results/index.html`](backtest_results/index.html) (open in a browser; every chart is interactive)")
    A("- **Per-run reports:** linked in the table below — candles with every fill, equity, attribution, second-by-second close-ups")
    A("- **Replay studio:** `python -m backtesting studio` — watch the bot trade the history tick by tick")
    A("- **How it works, how to run it:** [`backtesting/README.md`](backtesting/README.md)\n")

    A("## Results with the live settings\n")
    A("$2,000 start, 1:2000 leverage, unit auto-stepped from the balance exactly as the bot does it "
      "(`floor(balance / 2500) + 1`), real bid/ask ticks, the live loop cadence.\n")
    A(sec_runs(out, symbols) + "\n")
    A("A *basket* is one fresh entry plus its ladder adds, closed together. \"Fixed 0.01-lot unit\" is the same run with the "
      "balance auto-step switched off.\n")

    qt = [(sym, sec_quarters(out, sym)) for sym in symbols]
    if any(t for _, t in qt):
        A("### Quarter by quarter, and how much is timing luck\n")
        A("One run is one path. Whether the bot happens to be inside a basket when a sharp move starts depends on which tick "
          "its once-a-second poll lands on, and a few large baskets decide a quarter. So each of the five quarters was run "
          "eight times on raw ticks, on a fresh $2,000, with the loop period (1.0 s or 1.25 s) and its phase (0 / 0.25 / 0.5 / "
          "0.75 s) varied — all equally plausible for the live bot. The run in the table above is the first of the eight for "
          "its quarter.\n")
        for sym, t in qt:
            if t:
                A(f"**{sym}**\n")
                A(t + "\n")

    if findings:
        A("## What the backtest says about the strategy\n")
        for i, f in enumerate(findings, 1):
            A(f"**{i}. {f['title']}**  \n{f['detail']}\n")

    for sym in symbols:
        imgs = sec_images(out, sym)
        diag = sec_diagnostics(out, sym)
        if imgs or diag:
            A(f"## {sym}: the three months in pictures\n")
            if diag:
                A("Measured on the baseline run (numbers in "
                  f"[`diagnostics.json`](backtest_results/baseline/{sym}/diagnostics.json)):\n")
                A(diag + "\n")
            if imgs:
                A(imgs + "\n")

    agree_tf = max(base[symbols[0]].fc_weights, key=lambda k: TF_SECONDS.get(k, 0))
    sg = [(sym, sec_signal(out, sym, agree_tf)) for sym in symbols]
    if any(t for _, t in sg):
        A("## What the entry signal is made of\n")
        A(f"An entry needs the {agree_tf} RSI vote and the {agree_tf} MACD vote to point the same way. Measured with the live "
          f"`indicator.py` functions on every closed {agree_tf} bar (no spread, no ladder, no exits — this describes the signal, "
          f"not the trading). The MACD vote compares the histogram with its last pivot on the side the signal line selects, so "
          f"in an up-trend it reads \"down\" unless momentum makes a new high; the RSI vote is measured from the last pivot "
          f"beyond 60 / 40. Both are therefore votes to fade the last extreme. The bold columns are the test of whether that "
          f"predicts anything: after both votes agreed, how often was price further that way four bars later, against how "
          f"often that happens on any bar.\n")
        for sym, t in sg:
            if t:
                A(f"### {sym}\n")
                A(t + "\n")

    A("## Which timeframes for OPEN, FORCE-CLOSE" + (", BOOK" if netting else "") + " — RSI and MACD\n")
    A("Each setting was run on three separate three-month windows: the one asked for (13 Aug → 13 Nov) and the two before "
      "it. To compare settings fairly they all trade a fixed 0.01-lot unit on a balance that cannot be stopped out; the "
      "column \"wiped $2,000\" then says whether the real account would have survived. A timeframe choice is only worth "
      "anything if it holds up on windows it was not picked on.\n")
    for sym in symbols:
        t = sec_timeframes(out, sym, base[sym])
        if t:
            A(f"### {sym}\n")
            if (out / "img" / f"{sym}_timeframes.png").exists():
                A(f"![{sym}: OPEN x FORCE-CLOSE timeframes on three windows](backtest_results/img/{sym}_timeframes.png)\n")
            A(t + "\n")
            for kind in ("split_open", "split_fc") + (("split_book",) if netting else ()):
                s = sec_split(out, sym, kind)
                if s:
                    A(s + "\n")

    ho = [(sym, sec_holdout(out, sym)) for sym in symbols]
    if any(t for _, t in ho):
        A("## Does choosing timeframes on past data work? The hold-out test\n")
        A("Everything above was read off three quarters of 2026. A setting that looks good there was chosen with hindsight, so "
          "the same 432 settings were run on two earlier quarters (13 Aug 2025 → 13 Feb 2026) that were never used to choose "
          "anything. If picking by past performance worked, the settings that did best on the analysed quarters would do "
          "clearly better on the hold-out than the rest.\n")
        for sym, t in ho:
            if t:
                A(f"### {sym}\n")
                if (out / "img" / f"{sym}_holdout.png").exists():
                    A(f"![{sym}: analysed quarters against hold-out quarters](backtest_results/img/{sym}_holdout.png)\n")
                A(t + "\n")

    cd = [(sym, sec_candidates(out, sym)) for sym in symbols]
    if any(t for _, t in cd):
        A("## Candidate settings\n")
        A("The timeframe families that held up best in the sweeps, each with the live ladder, without a ladder, and with a "
          "short spaced ladder. Because one run is one path, every setting was run eight times per quarter on raw ticks (loop "
          "period 1.0 / 1.25 s × four phases), each on a fresh $2,000 with the unit auto-step: 40 quarter-runs per setting. "
          "Cells show the median of the eight; ✕ = one or more of the eight ended in a stop-out. The families were chosen after "
          "looking at the three 2026 quarters, so the two hold-out columns are the only independent evidence.\n")
        for sym, t in cd:
            if t:
                A(f"### {sym}\n")
                if (out / "img" / f"{sym}_candidates.png").exists():
                    A(f"![{sym}: candidate settings on five quarters](backtest_results/img/{sym}_candidates.png)\n")
                A(t + "\n")

    pk = [(sym, sec_packages(out, sym)) for sym in symbols]
    if any(t for _, t in pk):
        A("## What-ifs aimed at the flaws\n")
        A("Each row changes the rules in one deliberate way that answers a weakness found above. None was tuned on the data. "
          "One 0.01-lot unit; ✕ / \"wiped\" as before; sorted by windows survived, then by the three-window total.\n")
        for sym, t in pk:
            if t:
                A(f"### {sym}\n")
                if (out / "img" / f"{sym}_whatifs.png").exists():
                    A(f"![{sym}: what-ifs](backtest_results/img/{sym}_whatifs.png)\n")
                A(t + "\n")

    lv = [(sym, sec_levers(out, sym)) for sym in symbols]
    if any(t for _, t in lv):
        A("## Every other parameter, one at a time\n")
        A("One parameter changed, everything else at the live value. Net P/L of one 0.01-lot unit per window; ✕ = the loss "
          "exceeded $2,000 at some point in that window. Charts of the same numbers are on the results page.\n")
        for sym, t in lv:
            if t:
                A(f"<details><summary><b>{sym}</b> — all parameter tables</summary>\n\n{t}\n\n</details>\n")

    rb = [(sym, sec_robust(out, sym)) for sym in symbols]
    if any(t for _, t in rb):
        A("## How fragile is the live result?\n")
        A("The live settings again, real $2,000 account and auto-step, varying only things the bot does not control.\n")
        for sym, t in rb:
            if t:
                A(f"### {sym}\n")
                A(t + "\n")

    if reco:
        A("## Recommendations\n")
        A(reco + "\n")

    par, qual = sec_parity(out), sec_quality(out, symbols)
    if par or qual:
        A("## Why the simulation can be trusted — and where it cannot\n")
        if par:
            A("**It makes the same decisions as the live code.** The reference engine runs this branch's own `app.py` loop, "
              "unmodified, against a simulated MT5 terminal fed with the same ticks. " + par + "\n")
        if qual:
            A("**The data is the broker's own.** Exness's published tick history for `XAUUSDm` and `BTCUSDm`:\n\n" + qual + "\n")
        A("**What it cannot know.** Real order latency and slippage, requotes and rejections, terminal or VPS outages, bot "
          "restarts, and whether the live MT5 server's ticks match the archive tick for tick. The timing and cost stress "
          "tests above bound the first two. Swaps are taken as zero (Exness accounts are swap-free by default). A "
          "backtest is a description of the past, not a forecast.\n")

    if audit:
        A("## Live-code findings (outside the strategy rules)\n")
        A("Found while reading the live code for the backtester; each was checked by a second reviewer against the code. "
          "Nothing here was changed on this branch.\n")
        for a in audit:
            A(f"- **{a['title']}** ({a.get('where', '')}) — {a['detail']}")
        A("")

    A("## Reproduce\n")
    A("```bash\npip install -r requirements-backtest.txt\npython -m backtesting data --from 2025-07 --to 2026-11   # ~2 GB download\n"
      "python -m backtesting reproduce                         # every number on this page\npython -m backtesting docs"
      "                              # this file\npython -m pytest tests -q                               # test-suite\n```\n")

    target = Path(target) if target else Path(live_root) / "BACKTEST.md"
    target.write_text("\n".join(L), encoding="utf-8")
    return target
