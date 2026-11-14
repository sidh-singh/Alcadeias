"""
The results landing page: ``backtest_results/index.html``.

It reads whatever the experiment pipeline has written (baseline / long runs, sweeps,
levers, robustness, parity, data quality) and lays it out as one page: what happened
with the live settings, how much to trust the simulation, which timeframes hold up on
windows they were not chosen on, which other knobs matter, and how fragile it all is.

A hand-written ``findings.json`` in the results directory (a list of
``{"title": ..., "detail": ...}``) is rendered at the top when present.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..analysis.holdout import dip as _dip, wiped as _wiped
from ..config import BacktestConfig, REPO_ROOT, TF_SECONDS
from . import theme as T
from .report import _CONFIG, _FIT_JS, _money, _num, _table

WIN_LABEL = {"IS": "Aug 13 → Nov 13, 2026 (asked for)", "OOS1": "May 13 → Aug 13, 2026", "OOS2": "Feb 13 → May 13, 2026",
             "HO2": "Nov 13, 2025 → Feb 13, 2026 (hold-out)", "HO1": "Aug 13 → Nov 13, 2025 (hold-out)"}
WIN_SHORT = {"IS": "Aug–Nov 2026", "OOS1": "May–Aug 2026", "OOS2": "Feb–May 2026",
             "HO2": "Nov 2025–Feb 2026 · hold-out", "HO1": "Aug–Nov 2025 · hold-out"}
WIN_COLOR = {"IS": T.SERIES[0], "OOS1": T.SERIES[1], "OOS2": T.SERIES[2]}
CHRONO = ["HO1", "HO2", "OOS2", "OOS1", "IS"]
LONG_LABEL = "15 months (Aug 2025 → Nov 2026)"


def _fig(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id, config=_CONFIG)


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _windows(df: pd.DataFrame) -> List[str]:
    return [c.split("@")[1] for c in df.columns if c.startswith("net_profit@")]


def _div_scale() -> list:
    """Diverging: loss red -> neutral surface grey -> profit green."""
    return [[0.0, T.DOWN], [0.5, "#27304d"], [1.0, T.UP]]


def _tf_key(label: str) -> tuple:
    parts = label.split("+")
    return (len(parts), tuple(-TF_SECONDS.get(p, 0) for p in parts))


# ───────────────────────────── sections ─────────────────────────────

def section_runs(out: Path, symbols: Sequence[str]) -> str:
    rows, cards = [], []
    for name, label in (("baseline", "3 months (asked for)"), ("long", LONG_LABEL)):
        for sym in symbols:
            j = _read_json(out / name / sym / "summary.json")
            if not j:
                continue
            s = j["summary"]
            fu = _read_json(out / name / sym / "fixed_unit.json") or {}
            rows.append({
                "Run": f'<a href="{name}/{sym}/report.html">{sym} · {label}</a>',
                "Net P/L": _money(s["net_profit"], signed=True),
                "Max drawdown": f'{_money(s["max_drawdown_usd"])} ({_num(s["max_drawdown_pct"], 0)}%)',
                "Baskets": f'{s["baskets"]:,}', "Win %": _num(s.get("win_rate_pct", float("nan")), 1),
                "Needed to break even": _num(s.get("breakeven_win_rate_pct", float("nan")), 1),
                "Avg win": _money(s.get("avg_win", 0), signed=True), "Avg loss": _money(s.get("avg_loss", 0), signed=True),
                "Worst basket": _money(s.get("largest_loss", 0), signed=True),
                "Max lots": _num(s["max_lots"], 2),
                "Fixed unit 1": _money(fu.get("net_profit", float("nan")), signed=True),
                "Stopped out": (f'YES · {pd.Timestamp(int(j["scalars"]["last_poll_ms"]), unit="ms"):%d %b %Y}'
                                if s["stopped_out"] and j.get("scalars", {}).get("last_poll_ms") else
                                ("YES" if s["stopped_out"] else "no")),
            })
    if not rows:
        return ""
    df = pd.DataFrame(rows)
    head = "".join(f'<th class="{"l" if c == "Run" else ""}">{html.escape(c)}</th>' for c in df.columns)
    body = "".join("<tr>" + "".join(
        f'<td class="{"l" if c == "Run" else ""}">{r[c] if c == "Run" else html.escape(str(r[c]))}</td>'
        for c in df.columns) + "</tr>" for _, r in df.iterrows())
    return ('<h2>The live settings on real ticks</h2>'
            '<p class="lede">$2,000 start, 1:2000 account leverage, units auto-stepped from the balance exactly as the bot does. '
            '"Fixed unit 1" is the same run without the auto-step (0.01 lot entry throughout). Click a run for its full report: '
            'candles with every fill, equity, attribution and second-by-second close-ups.</p>'
            f'<div class="card"><div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>'
            + section_equity(out, symbols))


def section_equity(out: Path, symbols: Sequence[str]) -> str:
    present = [(n, s) for n in ("baseline", "long") for s in symbols if (out / n / s / "equity.csv.gz").exists()]
    if not present:
        return ""
    blocks = []
    for name, sym in present:
        e = pd.read_csv(out / name / sym / "equity.csv.gz")
        e["time"] = pd.to_datetime(e["time"], format="ISO8601")
        if e["time"].dt.tz is not None:
            e["time"] = e["time"].dt.tz_convert(None)
        e = e.set_index("time")
        step = "1h" if name == "baseline" else "4h"
        last = e[["balance", "equity"]].resample(step, label="right", closed="right").last().dropna()
        lo = e["equity"].resample(step, label="right", closed="right").min().reindex(last.index)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=last.index, y=last["balance"], mode="lines", name="Balance",
                                 line=dict(color=T.CONTEXT, width=1.4, shape="hv"),
                                 hovertemplate="balance %{y:,.0f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=last.index, y=lo, mode="lines", name="Equity (low of the period)",
                                 line=dict(color=T.EMPHASIS, width=1.8),
                                 hovertemplate="equity low %{y:,.0f}<extra></extra>"))
        fig.add_hline(y=float(e["balance"].iloc[0]), line=dict(color=T.AXIS, width=1))
        fig.update_layout(**T.plotly_layout(height=270, margin=dict(l=56, r=14, t=30, b=30)))
        fig.update_xaxes(**T.axis())
        fig.update_yaxes(**T.axis(title_text="USD", tickformat=",.0f"))
        ttl = f"{sym} · {'3 months' if name == 'baseline' else LONG_LABEL}"
        j = _read_json(out / name / sym / "summary.json") or {}
        note = ""
        s = j.get("summary") or {}
        if s.get("stopped_out"):
            when = pd.Timestamp(s["stopped_out_at"]) if s.get("stopped_out_at") else e.index[-1]
            note = f'<p class="cap">Account stopped out on {when:%d %b %Y}; the run ends there.</p>'
        blocks.append(f'<div class="card"><h3>{ttl}</h3>{note}{_fig(fig, f"eq_{name}_{sym}")}</div>')
    return ('<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px">'
            f'{"".join(blocks)}</div>')


def section_fidelity(out: Path, symbols: Sequence[str]) -> str:
    parts = []
    pdir = out / "parity"
    rows = []
    if pdir.exists():
        for p in sorted(pdir.glob("*.json")):
            j = _read_json(p)
            if not j:
                continue
            rows.append({
                "Window": (f'{j["symbol"]} {j["start"]} → {j.get("end", "")}' if j.get("symbol") and j.get("start") else p.stem),
                "Settings": j.get("scores", "") + (" · other periods and thresholds" if j.get("config_overrides", {}).get("rsi_length") else "")
                            + (f' · start ${j["config_overrides"]["initial_balance"]:,.0f}'
                               if j.get("config_overrides", {}).get("initial_balance") else ""),
                "Live polls": f'{j.get("polls_ref", 0):,}',
                "Mismatches: signals / scores / fills": f'{j.get("signal_mismatches")} / {j.get("score_mismatches")} / {j.get("fill_mismatches")}',
                "Fills (live / fast)": f'{j.get("fills_ref")} / {j.get("fills_fast")}',
                "Orders the broker refused": ", ".join(f'{v} {k.replace("_", " ")}' for k, v in (j.get("refused_ref") or {}).items()
                                                       if v) or "none",
                "Final balance (live / fast)": f'{j.get("balance_ref", 0):,.2f} / {j.get("balance_fast", 0):,.2f}',
                "Result": "identical" if j.get("ok") else "DIFFERS",
            })
    if rows:
        total = sum(int(r["Live polls"].replace(",", "")) for r in rows)
        parts.append(
            '<h2>Can the simulation be trusted?</h2>'
            f'<p class="lede">The reference engine runs the bot\'s own <code>app.py</code> loop, unmodified, against a simulated MT5 '
            f'terminal fed with the same Exness ticks. The fast engine used for everything on this page was compared with it poll '
            f'by poll: {total:,} live polls across {len(rows)} windows, both symbols, default and alternative settings. '
            f'A mismatch would be a poll on which the two disagreed about the signal, a score or a fill. The simulated terminal '
            f'refuses orders as the broker does (after a session\'s last quote, for 90 s after a break, when margin is short), so '
            f'windows with refused orders also check what the live loop does next. The stop-out and the handling of holes in the '
            f'BTC history are not part of this comparison.</p>'
            f'<div class="card"><div class="scroll">{_table(pd.DataFrame(rows), left_cols=["Window", "Settings"])}</div></div>')
    qrows = []
    for sym in symbols:
        q = _read_json(out / "data_quality" / f"{sym}.json")
        if not q:
            continue
        sp, g = q["spread"], q["gaps_over_3min"]
        qrows.append({
            "Symbol": sym, "From": q["first_tick"][:10], "To": q["last_tick"][:10],
            "Ticks": f'{q["ticks_total"]:,}', "Bad / out-of-order rows": f'{q["rows_dropped_invalid"]} / {q["rows_out_of_order"]}',
            "Spread median": _num(sp["median"], 3), "Spread p99": _num(sp["p99"], 3), "Spread max": _num(sp["max"], 3),
            "Silences > 3 min": g["count"], "Holes": len(g.get("holes") or []),
            "Unexplained": len(g["unexplained"]), "Empty days": len(q["days"]["missing"]),
            "Max 1 s move": f'{_num(q["jumps"]["max_1s_move_pct"], 2)}%',
        })
    if qrows:
        import re
        from .markdown import quality_notes
        notes = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", quality_notes(out, symbols)).replace("`", "").replace("  \n", "<br>")
        parts.append('<h3 style="margin-top:18px;font-size:13px">The data</h3><p class="lede" style="margin:0 0 8px;color:var(--ink-2)">'
                     'Exness\'s own published tick history for the exact symbols the bot trades (bid and ask, millisecond stamps).</p>'
                     f'<div class="card"><div class="scroll">{_table(pd.DataFrame(qrows), left_cols=["Symbol"])}</div>'
                     + (f'<p class="cap" style="margin-top:10px">{notes}</p>' if notes else "") + '</div>')
    return "".join(parts)


ACCOUNT = 2000.0
WIPED = " ✕"      # appended to a figure when that run would have wiped out a $2,000 account


def _heat(z: np.ndarray, x: List[str], y: List[str], title_x: str, title_y: str, mark: Optional[tuple] = None,
          height: Optional[int] = None, zmax: Optional[float] = None, ruin: Optional[np.ndarray] = None,
          left: int = 96) -> go.Figure:
    zmax = zmax or float(np.nanmax(np.abs(z))) or 1.0
    def cell(v, wiped):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        t = f"{v / 1000:+.1f}k" if abs(v) >= 1000 else f"{v:+.0f}"
        return t + (WIPED if wiped else "")

    text = [[cell(v, ruin is not None and bool(ruin[i][j])) for j, v in enumerate(row)] for i, row in enumerate(z)]
    fig = go.Figure(go.Heatmap(
        z=z, x=x, y=y, zmin=-zmax, zmax=zmax, colorscale=_div_scale(), xgap=2, ygap=2,
        text=text, texttemplate="%{text}", textfont=dict(color=T.INK, size=10.5),
        hovertemplate=f"{title_y} %{{y}}<br>{title_x} %{{x}}<br><b>%{{z:+,.2f}}</b><extra></extra>",
        colorbar=dict(thickness=10, len=0.8, outlinewidth=0, tickfont=dict(color=T.INK_MUTED, size=10),
                      title=dict(text="USD", font=dict(color=T.INK_MUTED, size=10)))))
    if mark is not None and mark[0] in x and mark[1] in y:
        i, j = x.index(mark[0]), y.index(mark[1])
        fig.add_shape(type="rect", x0=i - 0.5, x1=i + 0.5, y0=j - 0.5, y1=j + 0.5,
                      line=dict(color=T.ACCENT, width=2), fillcolor="rgba(0,0,0,0)")
    fig.update_layout(**T.plotly_layout(height=height or (120 + 26 * len(y)), margin=dict(l=left, r=10, t=14, b=44),
                                        hovermode="closest", showlegend=False))
    fig.update_xaxes(**T.axis(title_text=title_x, showgrid=False, type="category", side="bottom"))
    fig.update_yaxes(**T.axis(title_text=title_y, showgrid=False, type="category", autorange="reversed"))
    return fig


def section_timeframes(out: Path, sym: str, base: BacktestConfig) -> str:
    p = out / "sweeps" / f"{sym}_timeframes.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    wins = _windows(df)
    df["total"] = df[[f"net_profit@{w}" for w in wins]].sum(axis=1)
    df["worst"] = df[[f"net_profit@{w}" for w in wins]].min(axis=1)
    df["n_pos"] = (df[[f"net_profit@{w}" for w in wins]] > 0).sum(axis=1)
    for w in wins:
        df[f"ruin@{w}"] = _wiped(df, w)
    df["n_ruin"] = df[[f"ruin@{w}" for w in wins]].sum(axis=1)
    live_open = "+".join(sorted(base.open_weights, key=TF_SECONDS.get, reverse=True))
    live_fc = "+".join(sorted(base.fc_weights, key=TF_SECONDS.get, reverse=True))
    live_strict = base.entry_s >= 2.0 * len(base.open_weights) and len(base.open_weights) > 1
    live_lvl = "half" if base.force_close_s <= 1.0 else "full"
    # normalise the label order so "M15+H1" and "H1+M15" match
    norm = lambda s: "+".join(sorted(str(s).split("+"), key=TF_SECONDS.get, reverse=True))
    df["open"], df["fc"] = df["open"].map(norm), df["fc"].map(norm)
    blocks = []

    sub = df[(df["entry"] == ("strict" if live_strict else "loose")) & (df["fc_level"] == live_lvl)]
    opens = sorted(sub["open"].unique(), key=_tf_key)
    fcs = sorted(sub["fc"].unique(), key=lambda s: -TF_SECONDS.get(s, 0))
    zmax = float(np.nanpercentile(np.abs(sub[[f"net_profit@{w}" for w in wins]].to_numpy()), 97)) or 1.0
    cards = []
    for w in wins:
        piv = sub.pivot_table(index="open", columns="fc", values=f"net_profit@{w}", aggfunc="first").reindex(index=opens, columns=fcs)
        rn = sub.pivot_table(index="open", columns="fc", values=f"ruin@{w}", aggfunc="first").reindex(index=opens, columns=fcs)
        fig = _heat(piv.to_numpy(), fcs, opens, "FORCE-CLOSE timeframe", "OPEN timeframes", mark=(live_fc, live_open),
                    zmax=zmax, ruin=rn.fillna(False).to_numpy())
        cards.append(f'<div class="card"><h3>{WIN_LABEL.get(w, w)}</h3>'
                     f'<p class="cap">Net P/L of one fixed 0.01-lot unit over the quarter, USD. ✕ = the same baskets on a real '
                     f'$2,000 account with the bot\'s own lot sizing wipe it out in that quarter. Gold frame = the live setting.</p>'
                     f'{_fig(fig, f"tf_{sym}_{w}")}</div>')
    blocks.append('<div class="grid3">' + "".join(cards) + "</div>")
    from .markdown import cell_noise
    noise = cell_noise(out, sym)
    if noise:
        import re
        blocks.append('<p class="lede" style="margin:12px 0 0">' + re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", noise) + "</p>")

    live = df[(df["open"] == live_open) & (df["fc"] == live_fc) & (df["entry"] == ("strict" if live_strict else "loose"))
              & (df["fc_level"] == live_lvl)]
    top = df.sort_values(["n_ruin", "n_pos", "worst"], ascending=[True, False, False]).head(12)
    show = pd.concat([live.assign(_tag="live setting"), top.assign(_tag="")]).drop_duplicates(
        subset=["open", "fc", "entry", "fc_level"])
    t = pd.DataFrame({
        "": show["_tag"], "OPEN": show["open"], "FORCE-CLOSE": show["fc"], "Entry": show["entry"], "FC level": show["fc_level"],
        **{WIN_SHORT.get(w, w): show[f"net_profit@{w}"].map(lambda v: _money(v, signed=True)) for w in wins},
        "Quarters > 0": show["n_pos"].astype(int).astype(str) + f"/{len(wins)}",
        "Wiped $2,000 in": show["n_ruin"].astype(int).astype(str) + f"/{len(wins)}",
        "Worst quarter": show["worst"].map(lambda v: _money(v, signed=True)),
        "Deepest dip": pd.concat([_dip(show, w) for w in wins], axis=1).max(axis=1).map(_money),
        "Baskets / quarter": show[[f"baskets@{w}" for w in wins]].mean(axis=1).map(lambda v: f"{v:,.0f}"),
    })
    n_all3 = int(((df["n_pos"] == len(wins)) & (df["n_ruin"] == 0)).sum())
    n_ruin_any = int((df["n_ruin"] > 0).sum())
    blocks.append(
        f'<div class="card" style="margin-top:14px"><h3>Settings ranked by how they hold up across all three quarters</h3>'
        f'<p class="cap">Net P/L of one fixed 0.01-lot unit per quarter. Sorted by quarters survived, then profitable quarters, then '
        f'the worst quarter. {n_all3} of {len(df)} timeframe combinations made money in all {len(wins)} quarters without wiping a '
        f'real $2,000 account (the same baskets with the bot\'s own lot sizing); {n_ruin_any} wipe it out in at least one quarter. '
        f'"Deepest dip" = furthest that account stood below its start. This ranking is hindsight: the hold-out section below tests '
        f'it.</p>'
        f'<div class="scroll">{_table(t, left_cols=["", "OPEN", "FORCE-CLOSE", "Entry", "FC level"])}</div></div>')

    ag = _read_json(out / "sweeps" / f"{sym}_timeframes_agreement.json") or {}
    if ag and len(wins) >= 2:
        fig = go.Figure()
        a, b = wins[0], wins[1]
        d = df[(df[f"baskets@{a}"] >= 30) & (df[f"baskets@{b}"] >= 30)]
        fig.add_trace(go.Scatter(x=d[f"net_profit@{a}"], y=d[f"net_profit@{b}"], mode="markers",
                                 marker=dict(color=T.CONTEXT, size=6, opacity=0.7, line=dict(color=T.SURFACE, width=0.8)),
                                 text=d["open"] + " / " + d["fc"] + " (" + d["entry"] + ", " + d["fc_level"] + ")",
                                 name="one timeframe combination",
                                 hovertemplate="%{text}<br>" + a + " %{x:+,.0f} → " + b + " %{y:+,.0f}<extra></extra>"))
        if len(live):
            fig.add_trace(go.Scatter(x=live[f"net_profit@{a}"], y=live[f"net_profit@{b}"], mode="markers+text",
                                     marker=dict(color=T.ACCENT, size=12, symbol="diamond", line=dict(color=T.SURFACE, width=1.5)),
                                     text=["live"], textposition="top center", textfont=dict(color=T.INK, size=11),
                                     name="live setting", hovertemplate="live<br>%{x:+,.0f} → %{y:+,.0f}<extra></extra>"))
        fig.update_layout(**T.plotly_layout(height=380, margin=dict(l=64, r=14, t=30, b=46), hovermode="closest"))
        fig.update_xaxes(**T.axis(title_text=f"Net P/L in {WIN_LABEL.get(a, a)}", zeroline=True, zerolinecolor=T.AXIS))
        fig.update_yaxes(**T.axis(title_text=f"Net P/L in {WIN_LABEL.get(b, b)}", zeroline=True, zerolinecolor=T.AXIS))
        k = ag.get(f"{a}->{b}", {})
        cap = ('Each dot is one timeframe combination: what it made in the asked-for window (across) against what it made in the '
               'three months before (up).')
        if "spearman" in k:          # (too few settings with enough baskets in both windows give no statistics)
            cap += (f' Rank correlation {k["spearman"]:+.2f}. The top 10% picked on {WIN_SHORT.get(a, a)} averaged '
                    f'{_money(k.get(f"top_decile_mean_{a}", float("nan")), signed=True)} there and '
                    f'{_money(k.get(f"top_decile_mean_{b}", float("nan")), signed=True)} in {WIN_SHORT.get(b, b)}; the single best one went from '
                    f'{_money(k.get(f"best_{a}", float("nan")), signed=True)} to '
                    f'{_money(k.get(f"best_{a}_then_{b}", float("nan")), signed=True)}.')
        blocks.append(f'<div class="card" style="margin-top:14px"><h3>Does picking the best timeframes on one period work on another?</h3>'
                      f'<p class="cap">{cap}</p>{_fig(fig, f"tf_scatter_{sym}")}</div>')
    return "".join(blocks)


def section_split(out: Path, sym: str, kind: str, base: BacktestConfig) -> str:
    p = out / "sweeps" / f"{sym}_{kind}.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    wins = _windows(df)
    sec = {"split_open": "open", "split_fc": "fc", "split_book": "book"}[kind]
    rc, mc = f"{sec}_rsi", f"{sec}_macd"
    tfs = sorted(set(df[rc]) | set(df[mc]), key=lambda s: -TF_SECONDS.get(s, 0))
    w_live = {"open": base.open_weights, "fc": base.fc_weights, "book": base.book_weights}[sec]
    mark = None
    if len(w_live) == 1:
        tf = next(iter(w_live))
        mark = (tf, tf)
    zmax = float(np.nanpercentile(np.abs(df[[f"net_profit@{w}" for w in wins]].to_numpy()), 97)) or 1.0
    cards = []
    for w in wins + ["sum"]:
        col = df[[f"net_profit@{x}" for x in wins]].sum(axis=1) if w == "sum" else df[f"net_profit@{w}"]
        ru = pd.concat([_wiped(df, x) for x in wins], axis=1).any(axis=1) if w == "sum" else _wiped(df, w)
        piv = df.assign(v=col).pivot_table(index=rc, columns=mc, values="v", aggfunc="mean").reindex(index=tfs, columns=tfs)
        rn = df.assign(v=ru).pivot_table(index=rc, columns=mc, values="v", aggfunc="max").reindex(index=tfs, columns=tfs)
        fig = _heat(piv.to_numpy(), tfs, tfs, "MACD timeframe", "RSI timeframe", mark=mark, height=300,
                    zmax=zmax * (len(wins) if w == "sum" else 1), ruin=rn.fillna(False).to_numpy().astype(bool))
        ttl = "All windows added up" if w == "sum" else WIN_LABEL.get(w, w)
        cards.append(f'<div class="card"><h3>{ttl}</h3>{_fig(fig, f"{kind}_{sym}_{w}")}</div>')
    name = {"open": "OPEN", "fc": "FORCE-CLOSE", "book": "BOOK"}[sec]
    # the grid has no grey-fill in any cell; whether its diagonal is the live rule depends on what the live section does
    live_fill = {"open": base.open_grey_fill, "fc": base.fc_grey_fill, "book": base.book_grey_fill}[sec]
    if live_fill:
        strict = "no grey-fill anywhere in this grid, so the diagonal is a little stricter than the live score"
        frame = "Gold frame = the live timeframe (the live score also fills a grey vote from the other indicator)."
    else:
        strict = "no grey-fill anywhere in this grid; on the diagonal that is the live rule"
        frame = "Gold frame = the live setting."
    return (f'<h3 style="margin:22px 0 4px;font-size:13.5px">{name}: RSI on one timeframe, MACD on another</h3>'
            f'<p class="lede" style="margin:0 0 10px;color:var(--ink-2)">On the diagonal both indicators read the same timeframe. '
            f'Every cell needs both votes to agree ({strict}). Net P/L of one fixed 0.01-lot unit, USD; ✕ = wipes a real '
            f'$2,000 account; everything else as live. {frame if mark else ""}</p>'
            f'<div class="grid2">{"".join(cards)}</div>')


def holdout_figure(out: Path, sym: str, base: BacktestConfig, height: int = 420):
    """(figure, table by group, facts) for the hold-out test, or None when the hold-out sweep is missing."""
    from ..analysis import holdout as H
    r = H.timeframe_carry_over(out, sym)
    m = H.merged_timeframes(out, sym)
    if r is None or m is None:
        return None
    tab, facts = r
    norm = lambda x: "+".join(sorted(str(x).split("+"), key=TF_SECONDS.get, reverse=True))
    m = m.assign(open=m["open"].map(norm), fc=m["fc"].map(norm))
    live_open = norm("+".join(base.open_weights))
    live_fc = norm("+".join(base.fc_weights))
    live_strict = base.entry_s >= 2.0 * len(base.open_weights) and len(base.open_weights) > 1
    live = m[(m["open"] == live_open) & (m["fc"] == live_fc) & (m["entry"] == ("strict" if live_strict else "loose"))
             & (m["fc_level"] == ("half" if base.force_close_s <= 1.0 else "full"))]
    robust = (m["a_pos"] == 3) & (m["a_ruin"] == 0)
    label = m["open"] + " / " + m["fc"] + " (" + m["entry"] + ", " + m["fc_level"] + ")"
    na, nh = len(H.ANALYSED), len(H.HELD_OUT)
    # the frame covers 97% of the settings; the few beyond it are drawn on its edge (hover shows the real figure)
    lim_x = float(np.nanpercentile(np.abs(m["a_total"] / na), 97)) * 1.08 or 1.0
    lim_y = float(np.nanpercentile(np.abs(m["h_total"] / nh), 97)) * 1.08 or 1.0
    hover = "%{text}<br>analysed %{customdata[0]:+,.0f} / quarter → hold-out %{customdata[1]:+,.0f} / quarter<extra></extra>"

    def pts(d):
        x, y = (d["a_total"] / na).to_numpy(float), (d["h_total"] / nh).to_numpy(float)
        return dict(x=np.clip(x, -lim_x, lim_x), y=np.clip(y, -lim_y, lim_y), customdata=np.column_stack([x, y]))

    fig = go.Figure()
    for mask, name, color, sym_, size, op in (
            (~robust, "every other setting", T.CONTEXT, "circle", 6, 0.55),
            (robust, "profitable in all three analysed quarters, account never wiped", T.SERIES[0], "square", 8, 0.95)):
        fig.add_trace(go.Scatter(**pts(m[mask]), mode="markers", name=name, text=label[mask],
                                 marker=dict(color=color, size=size, symbol=sym_, opacity=op, line=dict(color=T.SURFACE, width=0.8)),
                                 hovertemplate=hover))
    if len(live):
        fig.add_trace(go.Scatter(**pts(live), mode="markers+text", name="live setting",
                                 marker=dict(color=T.ACCENT, size=13, symbol="diamond", line=dict(color=T.SURFACE, width=1.5)),
                                 text=["live"], textposition="top center", textfont=dict(color=T.INK, size=11),
                                 hovertemplate=hover.replace("%{text}", "live setting")))
    fig.update_layout(**T.plotly_layout(height=height, margin=dict(l=64, r=14, t=34, b=48), hovermode="closest"))
    fig.update_xaxes(**T.axis(title_text="Net P/L per quarter on the three analysed quarters, USD", zeroline=True,
                              zerolinecolor=T.AXIS, range=[-lim_x * 1.04, lim_x * 1.04]))
    fig.update_yaxes(**T.axis(title_text="Net P/L per quarter on the two hold-out quarters, USD", zeroline=True,
                              zerolinecolor=T.AXIS, range=[-lim_y * 1.04, lim_y * 1.04]))
    return fig, tab, facts


def section_holdout(out: Path, sym: str, base: BacktestConfig) -> str:
    """Do settings chosen on the analysed quarters carry over to two quarters they never saw?"""
    r = holdout_figure(out, sym, base)
    if r is None:
        return ""
    fig, tab, facts = r
    t = pd.DataFrame({
        "On the three analysed quarters": tab["group"],
        "Settings": tab["settings"].astype(int),
        "Hold-out: both quarters up": tab["both_holdout_profitable_pct"].map(lambda v: f"{v:.0f}%"),
        "one or both": tab["one_or_more_pct"].map(lambda v: f"{v:.0f}%"),
        "wiped": tab["wiped_in_holdout_pct"].map(lambda v: f"{v:.0f}%"),
        "mean net / quarter": tab["mean_holdout_net_per_quarter"].map(lambda v: _money(v, signed=True)),
        "median": tab["median_holdout_net_per_quarter"].map(lambda v: _money(v, signed=True)),
    })
    cap = (f'Each dot is one of the {facts["settings"]} timeframe settings (one 0.01-lot unit). Across is what it averaged per quarter on '
           f'the three 2026 quarters everything else on this page was read from; up is what it averaged on two earlier quarters '
           f'(13 Aug 2025 → 13 Feb 2026) that were never used to choose anything. The few settings beyond the frame are drawn '
           f'on its edge. Rank correlation {facts["rank_correlation"]:+.2f}. Of all settings, '
           f'{facts["base_both_profitable_pct"]:.0f}% were profitable in both hold-out quarters and '
           f'{facts["base_wiped_pct"]:.0f}% would have wiped $2,000 in one of them.')
    return (f'<div class="card"><h3>{sym}</h3><p class="cap">{cap}</p><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:18px;align-items:start"><div>{_fig(fig, f"ho_{sym}")}</div>'
            f'<div><p class="cap" style="margin-top:6px">How the settings did on the two hold-out quarters, grouped by how they had '
            f'done on the three analysed ones:</p><div class="scroll">'
            f'{_table(t, left_cols=["On the three analysed quarters"])}</div></div></div></div>')


def _cand_short(tf: str, ladder: str) -> str:
    head = tf.split(":")[0].strip() if ":" in tf else "Live"
    return f"{head} · {ladder}"


def candidates_figure(out: Path, sym: str):
    """(figure, candidate table, [(family letter, description)]) or None when the candidates stage has not run."""
    from ..analysis import holdout as H
    df = H.candidate_table(out, sym)
    if df is None:
        return None
    wins = [w for w in CHRONO if f"net_profit@{w}" in df.columns]
    short = [_cand_short(a, b) for a, b in zip(df["timeframes"], df["ladder"])]
    if all(f"ens_median@{w}" in df.columns for w in wins):
        # the timing ensemble: median of eight loop timings on a fresh $2,000; ✕ = one or more of the eight was stopped out
        z = df[[f"ens_median@{w}" for w in wins]].to_numpy(float)
        ruin = df[[f"ens_stopped@{w}" for w in wins]].to_numpy(float) > 0
    else:
        z = df[[f"net_profit@{w}" for w in wins]].to_numpy(float)
        ruin = np.column_stack([_wiped(df, w).to_numpy(bool) for w in wins])
    zmax = float(np.nanpercentile(np.abs(z), 92)) or 1.0
    fig = _heat(z, [WIN_SHORT[w] for w in wins], short, "Quarter (oldest first)", "", zmax=zmax, ruin=ruin,
                height=110 + 24 * len(df), left=230)
    fams = [(tf.split(":")[0].strip(), tf.split(":", 1)[1].strip()) for tf in dict.fromkeys(df["timeframes"]) if ":" in tf]
    return fig, df, fams


def candidates_mode(df: pd.DataFrame) -> str:
    """'ensemble' when the candidate table carries the eight-timings runs (what the figure then draws), else 'single'."""
    wins = [w for w in CHRONO if f"net_profit@{w}" in df.columns]
    return "ensemble" if wins and all(f"ens_median@{w}" in df.columns for w in wins) else "single"


def section_candidates(out: Path, sym: str) -> str:
    r = candidates_figure(out, sym)
    if r is None:
        return ""
    fig, df, fams = r
    wins = [w for w in CHRONO if f"net_profit@{w}" in df.columns]
    legend = "".join(f"<b>{html.escape(k)}</b> = {html.escape(v)}; " for k, v in fams) + "<b>Live</b> = the deployed timeframes."
    ens = all(f"ens_median@{w}" in df.columns for w in wins)
    if ens:
        n = df["ens_runs"].astype(int).astype(str)
        t = pd.DataFrame({
            "Setting": [_cand_short(a, b) for a, b in zip(df["timeframes"], df["ladder"])],
            **{WIN_SHORT[w].replace(" · hold-out", " (h-o)"): [_money(m, signed=True) + (WIPED if k > 0 else "")
                                                               for m, k in zip(df[f"ens_median@{w}"], df[f"ens_stopped@{w}"])] for w in wins},
            "Runs that lost": df["ens_losing_runs"].astype(int).astype(str) + " of " + n,
            "Stopped out": df["ens_stopped_runs"].astype(int).astype(str) + " of " + n,
            "Median run": df["ens_median"].map(lambda v: _money(v, signed=True)),
            "Worst run": df["ens_worst_run"].map(lambda v: _money(v, signed=True)),
            "Worst basket": df["ens_worst_basket"].map(lambda v: _money(v, signed=True)),
            "Baskets / quarter": df["ens_baskets_per_quarter"].map(lambda v: f"{v:,.0f}"),
        })
        cap = ('Each cell: the median net P/L of eight raw-tick runs of that quarter (eight random loop timings) on a fresh '
               '$2,000 with the unit auto-step, USD. ✕ = one or more of the eight ended in a stop-out. ')
        summ = ("Table view: per-quarter medians, the spread over all 40 quarter-runs, and one per-second run of all fifteen "
                "months on $2,000 (✕ = stopped out); (h-o) = hold-out quarter")
    else:
        t = pd.DataFrame({
            "Setting": df["candidate"],
            **{WIN_SHORT[w]: [_money(n, signed=True) + (WIPED if k else "")
                              for n, k in zip(df[f"net_profit@{w}"], _wiped(df, w))] for w in wins},
            "Quarters > 0": df["quarters_profitable"].astype(int).astype(str) + "/" + df["quarters"].astype(int).astype(str),
            "Hold-out total": df["holdout_total"].map(lambda v: _money(v, signed=True)),
            "Deepest dip": df["deepest_dip"].map(_money),
            "Worst basket": df["worst_basket"].map(lambda v: _money(v, signed=True)),
            "Baskets / quarter": df["baskets_per_quarter"].map(lambda v: f"{v:,.0f}"),
        })
        cap = 'Net P/L of one fixed 0.01-lot unit per quarter, USD. ✕ = the same baskets wipe a real $2,000 account in that quarter. '
        summ = "Table view"
    if "account_net" in df.columns:
        t["15 months in one run"] = [_money(v, signed=True) + (WIPED if bool(k) else "")
                                     for v, k in zip(df["account_net"], df["account_stopped_out"])]
    return (f'<div class="card"><h3>{sym}</h3><p class="cap">{cap}{legend}</p>{_fig(fig, f"cand_{sym}")}'
            f'<details open><summary>{summ}</summary><div class="scroll">{_table(t, left_cols=["Setting"])}</div></details></div>')


def section_signal(out: Path, sym: str, tf: str, horizon: int = 4) -> str:
    from ..analysis.signal import vote_table
    t = vote_table(out, sym, tf, horizon)
    if t is None:
        return ""
    f0, f1 = (lambda v: f"{v:.0f}%"), (lambda v: f"{v:.1f}%")
    d = pd.DataFrame({
        "Period": t["period"], f"{tf} bars": t["bars"].map(lambda v: f"{v:,}"),
        "MACD vote against its own trend": t["macd_against_trend_pct"].map(f0),
        "RSI up-votes after an oversold low": t["rsi_up_from_oversold_low_pct"].map(f0),
        "Both votes up": t["both_up_share_pct"].map(f0),
        f"→ higher {horizon} bars later": t["higher_after_both_up_pct"].map(f1),
        "any bar: higher": t["higher_all_bars_pct"].map(f1),
        "Both votes down": t["both_down_share_pct"].map(f0),
        f"→ lower {horizon} bars later": t["lower_after_both_down_pct"].map(f1),
        "any bar: lower": t["lower_all_bars_pct"].map(f1),
    })
    cap = ""
    a = t[t["period"] == "All fifteen months"]
    if len(a):
        r = a.iloc[0]
        cap = (f'<p class="cap">Over all {int(r["bars"]):,} bars: the MACD vote pointed against its own signal-line trend on '
               f'{r["macd_against_trend_pct"]:.0f}% of them; {r["rsi_up_from_oversold_low_pct"]:.0f}% of RSI up-votes were measured '
               f'from an oversold low. After both votes pointed up, price was higher {horizon} bars later {r["higher_after_both_up_pct"]:.1f}% '
               f'of the time ({r["higher_all_bars_pct"]:.1f}% on any bar); after both pointed down it was lower '
               f'{r["lower_after_both_down_pct"]:.1f}% of the time ({r["lower_all_bars_pct"]:.1f}% on any bar). Neighbouring bars overlap, '
               f'so a point or two either way is noise.</p>')
    return (f'<div class="card"><h3>{sym}</h3>{cap}<div class="scroll">{_table(d, left_cols=["Period"])}</div></div>')


def section_levers(out: Path, sym: str) -> str:
    p = out / "levers" / f"{sym}.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p, dtype={"value": str})
    wins = _windows(df)
    cards = []
    for i, (param, g) in enumerate(df.groupby("param", sort=False)):
        fig = go.Figure()
        for w in wins:
            fig.add_trace(go.Scatter(x=g["value"], y=g[f"net_profit@{w}"], mode="lines+markers", name=WIN_LABEL.get(w, w),
                                     line=dict(color=WIN_COLOR.get(w, T.CONTEXT), width=2),
                                     marker=dict(size=7, line=dict(color=T.SURFACE, width=1.5)),
                                     showlegend=(i == 0),
                                     hovertemplate="%{x}<br>" + WIN_SHORT.get(w, w) + " <b>%{y:+,.0f}</b><extra></extra>"))
        fig.update_layout(**T.plotly_layout(height=240, margin=dict(l=52, r=10, t=26 if i == 0 else 10, b=58),
                                            hovermode="x unified"))
        fig.update_xaxes(**T.axis(type="category", tickangle=-30 if g["value"].str.len().max() > 6 else 0, showgrid=False))
        fig.update_yaxes(**T.axis(title_text="Net P/L, USD", zeroline=True, zerolinecolor=T.AXIS))
        tbl = pd.DataFrame({"Value": g["value"],
                            **{WIN_SHORT.get(w, w): g[f"net_profit@{w}"].map(lambda v: _money(v, signed=True)) for w in wins},
                            "Deepest dip": pd.concat([_dip(g, w) for w in wins], axis=1).max(axis=1).map(_money),
                            "Wiped $2,000 in": (sum(_wiped(g, w).astype(int) for w in wins)).astype(str) + f"/{len(wins)}",
                            "Baskets / quarter": g[[f"baskets@{w}" for w in wins]].mean(axis=1).map(lambda v: f"{v:,.0f}")})
        cards.append(f'<div class="card"><h3>{html.escape(param.replace("_", " "))}</h3>{_fig(fig, f"lev_{sym}_{i}")}'
                     f'<details><summary>Table view</summary><div class="scroll">{_table(tbl, left_cols=["Value"])}</div></details></div>')
    return f'<div class="grid3">{"".join(cards)}</div>'


def section_packages(out: Path, sym: str) -> str:
    p = out / "packages" / f"{sym}.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    wins = _windows(df)
    net = [f"net_profit@{w}" for w in wins]
    df["total"] = df[net].sum(axis=1)
    df["dip"] = pd.concat([_dip(df, w) for w in wins], axis=1).max(axis=1)
    df["n_ruin"] = sum(_wiped(df, w).astype(int) for w in wins)
    df["n_pos"] = (df[net] > 0).sum(axis=1)
    live = df[df["package"] == "live settings"]
    rest = df[df["package"] != "live settings"].sort_values(["n_ruin", "total"], ascending=[True, False])
    d = pd.concat([live, rest])
    # horizontal bars: total over the three windows, sorted as the table
    fig = go.Figure(go.Bar(
        y=d["package"], x=d["total"], orientation="h", width=0.62,
        marker=dict(color=[T.UP if v > 0 else T.DOWN for v in d["total"]], line=dict(width=0)),
        text=[f"{v:+,.0f}" + (WIPED if r > 0 else "") for v, r in zip(d["total"], d["n_ruin"])],
        textposition="outside", textfont=dict(color=T.INK, size=11), cliponaxis=False, constraintext="none",
        hovertemplate="%{y}<br>three windows added up <b>%{x:+,.0f}</b><extra></extra>"))
    span = max(abs(d["total"].max()), abs(d["total"].min()), 1.0)
    fig.update_layout(**T.plotly_layout(height=60 + 24 * len(d), margin=dict(l=10, r=30, t=10, b=36), showlegend=False,
                                        hovermode="closest", bargap=0.3))
    fig.update_xaxes(**T.axis(title_text="Net P/L of one 0.01-lot unit, three quarters added up, USD", zeroline=True,
                              zerolinecolor=T.AXIS, range=[min(d["total"].min(), 0) - span * 0.16, max(d["total"].max(), 0) + span * 0.16]))
    fig.update_yaxes(**T.axis(showgrid=False, autorange="reversed", tickfont=dict(color=T.INK_2, size=11.5)))
    t = pd.DataFrame({
        "What-if": d["package"],
        **{WIN_SHORT.get(w, w): d[f"net_profit@{w}"].map(lambda v: _money(v, signed=True)) for w in wins},
        "Three quarters": d["total"].map(lambda v: _money(v, signed=True)),
        "Quarters > 0": d["n_pos"].astype(int).astype(str) + f"/{len(wins)}",
        "Deepest dip": d["dip"].map(_money),
        "Wiped $2,000 in": d["n_ruin"].astype(int).astype(str) + f"/{len(wins)}",
        "Worst basket": d[[f"largest_loss@{w}" for w in wins]].min(axis=1).map(lambda v: _money(v, signed=True)),
        "Baskets / quarter": d[[f"baskets@{w}" for w in wins]].mean(axis=1).map(lambda v: f"{v:,.0f}"),
    })
    return (f'<div class="card"><h3>{sym}</h3>'
            '<p class="cap">Bars: one fixed 0.01-lot unit, the three 2026 quarters added up. ✕ = the same baskets wipe a real '
            '$2,000 account in at least one quarter. First row = the live settings. Each row is a single path per quarter: read '
            'differences of a few hundred dollars as noise.</p>'
            f'{_fig(fig, f"pkg_{sym}")}'
            f'<details open><summary>Table view</summary><div class="scroll">{_table(t, left_cols=["What-if"])}</div></details></div>')


def section_quarters(out: Path, sym: str) -> str:
    """Every quarter under eight loop timings: dots = single runs, bar = median."""
    from ..analysis.robustness import ensemble_summary
    p = out / "robustness" / sym / "quarters_timing.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    e = ensemble_summary(df)
    lab = {w: WIN_SHORT.get(w, w) for w in e["window"]}
    fig = go.Figure()
    so = df["stopped_out"].astype(bool)
    for mask, name, color, symbol in ((~so, "one run (one random loop timing)", T.CONTEXT, "circle"),
                                      (so, "run ended in a stop-out", T.DOWN, "x")):
        d = df[mask]
        if len(d):
            fig.add_trace(go.Scatter(x=d["window"].map(lab), y=d["net_profit"], mode="markers", name=name,
                                     marker=dict(color=color, size=9, symbol=symbol, opacity=0.9,
                                                 line=dict(color=T.SURFACE, width=1)),
                                     customdata=d["seed"].to_numpy(),
                                     hovertemplate="%{x}<br>loop timing no. %{customdata}<br>"
                                                   "<b>%{y:+,.0f}</b><extra></extra>"))
    fig.add_trace(go.Scatter(x=e["window"].map(lab), y=e["net_median"], mode="markers", name="median of the runs",
                             marker=dict(color=T.EMPHASIS, size=30, symbol="line-ew", line=dict(color=T.EMPHASIS, width=3)),
                             hovertemplate="%{x}<br>median <b>%{y:+,.0f}</b><extra></extra>"))
    fig.update_layout(**T.plotly_layout(height=330, margin=dict(l=60, r=14, t=34, b=40), hovermode="closest"))
    fig.update_xaxes(**T.axis(type="category", showgrid=False, categoryorder="array", categoryarray=[lab[w] for w in e["window"]]))
    fig.update_yaxes(**T.axis(title_text="Net P/L on a fresh $2,000, USD", zeroline=True, zerolinecolor=T.AXIS, tickformat=",.0f"))
    t = pd.DataFrame({
        "Quarter": e["window"].map(lab),
        "Median": e["net_median"].map(lambda v: _money(v, signed=True)),
        "Worst run": e["net_min"].map(lambda v: _money(v, signed=True)),
        "Best run": e["net_max"].map(lambda v: _money(v, signed=True)),
        "Lost money": e["losing_runs"].astype(str) + " of " + e["runs"].astype(str),
        "Stopped out": e["stopped_out_runs"].astype(str) + " of " + e["runs"].astype(str),
        "Median max DD": e["max_dd_pct_median"].map(lambda v: f"{v:.0f}%"),
        "Worst basket": e["worst_basket"].map(lambda v: _money(v, signed=True)),
    })
    tot = int(e["runs"].sum())
    return (f'<div class="card"><h3>{sym}</h3><p class="cap">{int(e["losing_runs"].sum())} of {tot} quarter-runs lost money; '
            f'{int(e["stopped_out_runs"].sum())} ended with the account stopped out.</p><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:18px;align-items:start"><div>{_fig(fig, f"qt_{sym}")}</div>'
            f'<div class="scroll">{_table(t, left_cols=["Quarter"])}</div></div></div>')


def section_robust(out: Path, sym: str) -> str:
    d = out / "robustness" / sym
    if not d.exists():
        return ""
    cards = []

    def card(title, cap, df, left):
        cards.append(f'<div class="card"><h3>{title}</h3><p class="cap">{cap}</p>'
                     f'<div class="scroll">{_table(df, left_cols=left)}</div></div>')

    def fmt(df, keep, money=("net_profit", "max_dd_usd", "largest_loss")):
        t = df[keep].copy()
        for c in keep:
            if c in money:
                t[c] = t[c].map(lambda v: _money(v, signed=(c != "max_dd_usd")))
        for c, nd in (("win_rate_pct", 1), ("profit_factor", 2)):
            if c in t.columns:
                t[c] = t[c].map(lambda v, nd=nd: _num(float(v), nd))        # no closed basket / no losing basket: a dash
        if "start_shift_days" in t.columns:
            t["start_shift_days"] = t["start_shift_days"].astype(int)
        return t.rename(columns={"net_profit": "Net P/L", "max_dd_usd": "Max DD", "baskets": "Baskets",
                                 "win_rate_pct": "Win %", "profit_factor": "PF", "largest_loss": "Worst basket",
                                 "start_shift_days": "Started N days later", "segment": "Period"})

    from ..analysis.robustness import spread_of

    def levels(df, by, label, fmt_level):
        """One row per level of a stress test: median and range over the loop timings it was run under."""
        e = spread_of(df, [by])
        return pd.DataFrame({
            label: e[by].map(fmt_level), "Median net": e["net_median"].map(lambda v: _money(v, signed=True)),
            "Worst": e["net_min"].map(lambda v: _money(v, signed=True)), "Best": e["net_max"].map(lambda v: _money(v, signed=True)),
            "Lost money": e["losing_runs"].astype(str) + " of " + e["runs"].astype(str),
            "Stopped out": e["stopped_out_runs"].astype(str) + " of " + e["runs"].astype(str),
            "Median max DD": e["max_dd_pct_median"].map(lambda v: f"{v:.0f}%"),
        }), (int(e["runs"].iloc[0]) if len(e) else 0)

    p = d / "timing.csv"
    if p.exists():
        t = pd.read_csv(p)
        poll, lat = t[t["test"] == "poll"], t[t["test"] == "latency"]
        if len(poll):
            tb, k = levels(poll, "poll_ms", "Loop period", lambda v: f"{v / 1000:g} s")
            card("A slower loop", f"The asked-for quarter with the loop sleeping longer between passes; each period under {k} "
                 f"random loop timings (raw ticks).", tb, ["Loop period"])
        if len(lat):
            tb, k = levels(lat, "latency_ms", "Latency", lambda v: f"{int(v)} ms")
            card("Order latency", f"Delay between the quote that triggered an order and the quote it filled at; each level under "
                 f"{k} random loop timings.", tb, ["Latency"])
    p = d / "costs.csv"
    if p.exists():
        t = pd.read_csv(p)
        sp, sl = t[t["test"] == "spread"], t[t["test"] == "slippage"]
        if len(sp):
            tb, k = levels(sp, "spread_mult", "Spread", lambda v: f"× {v:g}")
            card("Wider spread", f"The recorded spread scaled up; each level under {k} random loop timings.", tb, ["Spread"])
        if len(sl):
            tb, k = levels(sl, "slippage", "Slippage", lambda v: f"{v:g}")
            card("Slippage", f"Every fill worse by this much, in price units; each level under {k} random loop timings.", tb,
                 ["Slippage"])
    p = d / "start_shift.csv"
    if p.exists():
        t = pd.read_csv(p)
        card("Start date", f"Same settings, same end, started N days later (raw ticks, one path each; starts in a closed market "
             f"repeat the next open and are left out). Net P/L ranged {_money(t['net_profit'].min(), signed=True)} … "
             f"{_money(t['net_profit'].max(), signed=True)}.",
             fmt(t, ["start_shift_days", "net_profit", "max_dd_usd", "baskets", "win_rate_pct", "profit_factor"]), ["Started N days later"])
    p = d / "segments_quarterly.csv"
    if p.exists():
        t = pd.read_csv(p)
        pos = int((t["net_profit"] > 0).sum())
        so = int(t["stopped_out"].astype(bool).sum())
        tq = fmt(t, ["segment", "role", "net_profit", "max_dd_usd", "baskets", "win_rate_pct", "profit_factor", "largest_loss"])
        tq.insert(3, "Stopped out", t["stopped_out"].map(lambda v: "YES" if bool(v) else "no"))
        card("Five quarters, each on a fresh $2,000", f"The live settings with the unit auto-step (per-second replay, one path "
             f"each; the table at the top of the page gives eight paths per quarter). {pos} of {len(t)} quarters ended positive; "
             f"{so} ended in a stop-out.", tq.rename(columns={"Period": "Quarter", "role": "Used for"}), ["Quarter", "Used for"])
    for fn, ttl, cap in (("segments_monthly.csv", "Month by month, each on a fresh $2,000", "Calendar months over all fifteen months."),
                         ("segments_weekly.csv", "Week by week, each on a fresh $2,000", "Seven-day slices of the asked-for window.")):
        p = d / fn
        if p.exists():
            t = pd.read_csv(p)
            whole = t[~t["partial"].astype(bool)] if "partial" in t.columns else t
            pos = int((whole["net_profit"] > 0).sum())
            so = int(whole["stopped_out"].astype(bool).sum())
            tt = fmt(t, ["segment", "net_profit", "max_dd_usd", "baskets", "win_rate_pct", "profit_factor", "largest_loss"])
            if "partial" in t.columns:
                tt["Period"] = [x + (" (part)" if bool(pp) else "") for x, pp in zip(t["segment"], t["partial"])]
            card(ttl, f"{cap} Per-second replay, one path each. {pos} of {len(whole)} whole periods ended positive, {so} in a "
                 f"stop-out.", tt, ["Period"])
    b = _read_json(d / "bootstrap.json")
    if b:
        rows = []
        for k, lab in (("live_units", "The bot's unit rule"), ("fixed_unit_1", "One fixed unit")):
            x = b.get(k) or {}
            if not x:
                continue
            rows.append({"Sizing": lab, "Final balance p5": _money(x["final_p05"]), "p50": _money(x["final_p50"]),
                         "p95": _money(x["final_p95"]), "Ended below the start": f'{x["prob_loss"] * 100:.0f}%',
                         "Lost over 25%": f'{x["prob_loss_over_25pct"] * 100:.0f}%',
                         "Wiped": f'{x["prob_wiped"] * 100:.0f}%',
                         "Deepest dip p50": _money(x["dip_p50"]), "p95 ": _money(x["dip_p95"])})
        if rows:
            n = (b.get("live_units") or b.get("fixed_unit_1") or {}).get("paths", 0)
            card("Which days happened to be in the quarter", f"The baseline run's {b.get('baskets', 0):,} baskets, whole trading "
                 f"days drawn with replacement {n:,} times (some days count twice, others not at all). Every basket is re-sized "
                 f"as the resampled balance evolves, and a path ends when the balance cannot cover a basket's worst floating "
                 f"loss.", pd.DataFrame(rows), ["Sizing"])
    return f'<div class="grid2">{"".join(cards)}</div>' if cards else ""


def section_findings(out: Path) -> str:
    f = _read_json(out / "findings.json")
    if not f:
        return ""
    items = "".join(
        f'<div class="finding"><div class="n">{i + 1}</div><div class="t">{x["title"]}</div>'
        f'<div class="d">{x["detail"]}</div></div>' for i, x in enumerate(f))
    return f'<h2>What the backtest says about the strategy</h2><div class="card">{items}</div>'


def build_index(out: Path, symbols: Sequence[str] = ("XAUUSDm", "BTCUSDm"), live_root: Path = REPO_ROOT) -> Path:
    out = Path(out)
    base = {s: BacktestConfig.live(s, repo_root=live_root) for s in symbols}
    variant = next(iter(base.values())).variant
    from ..experiments import stale_outputs
    stale = stale_outputs(out, live_root)
    banner = ""
    if stale:
        banner = (f'<div class="card" style="border-color:{T.DOWN};margin-bottom:18px"><h3>Some results on this page are stale</h3>'
                  f'<p class="cap">{len(stale)} result file{"s were" if len(stale) != 1 else " was"} written by another build of the '
                  f'engine, for other live settings or from other tick data than this checkout has now, or '
                  f'{"carry" if len(stale) != 1 else "carries"} no build stamp (for example {html.escape(stale[0])}). Run '
                  f'<code>python -m backtesting reproduce</code> to recompute them before reading the numbers'
                  + (" (the fidelity windows are re-checked with <code>python -m backtesting parity</code>)"
                     if any(x.startswith("parity/") for x in stale) else "") + '.</p></div>')
    stack = '<div style="display:grid;gap:14px">'       # full-width cards, one under the other
    agree_tf = max(base[symbols[0]].fc_weights, key=lambda k: TF_SECONDS.get(k, 0))

    # 1. what happened, and how much of it is one path's luck
    body = [section_findings(out), section_runs(out, symbols)]
    qt = [section_quarters(out, sym) for sym in symbols]
    if any(qt):
        body.append('<h2>Quarter by quarter, and how much is timing luck</h2>'
                    '<p class="lede">One run is one path: whether the bot is inside a basket when a sharp move starts depends '
                    'on which tick its once-a-second poll lands on, and a few large baskets decide a quarter. The live loop does '
                    'not poll on a fixed grid: it sleeps a second, then spends a varying time talking to the terminal. Each of '
                    'the five quarters was therefore run eight times on raw ticks, on a fresh $2,000 with the live unit '
                    'auto-step, with every pass of the loop taking 0 to 0.2 s longer, drawn at random. All eight are equally '
                    'plausible for the live bot.</p>'
                    f'{stack}{"".join(x for x in qt if x)}</div>')
    # 2. why: what the signal is
    sg = [section_signal(out, sym, agree_tf) for sym in symbols]
    if any(sg):
        body.append('<h2>What the entry signal is made of</h2>'
                    f'<p class="lede">An entry needs the {agree_tf} RSI vote and the {agree_tf} MACD vote to agree. Both are measured '
                    f'from the last pivot of their indicator, so both are votes to fade the last extreme. The tables test, with the '
                    f'live indicator functions on every closed {agree_tf} bar, whether that agreement says anything about where price '
                    f'goes next. This describes the signal only: no spread, ladder or exits.</p>'
                    f'{stack}{"".join(x for x in sg if x)}</div>')
    # 3. can the numbers be trusted
    body.append(section_fidelity(out, symbols))
    # 4. timeframes: the grid, then the test of choosing from it, then the short list
    for sym in symbols:
        blk = section_timeframes(out, sym, base[sym])
        splits = "".join(section_split(out, sym, k, base[sym]) for k in ("split_open", "split_fc", "split_book"))
        if blk or splits:
            body.append(f'<h2>{sym}: which timeframes for OPEN and FORCE-CLOSE'
                        f'{" and BOOK" if variant == "netting" else ""}?</h2>'
                        '<p class="lede">Every combination of one or two OPEN timeframes with one FORCE-CLOSE timeframe, '
                        'thresholds following the live convention, on three separate quarters. A cell that is green in one '
                        'quarter and red in the next is noise, not an edge.</p>' + blk + splits)
    ho = [section_holdout(out, sym, base[sym]) for sym in symbols]
    if any(ho):
        body.append('<h2>Does choosing timeframes on past data work? The hold-out test</h2>'
                    '<p class="lede">Any setting that looks good above was picked with hindsight on those three quarters. The '
                    'honest test is data it has never seen: the same grid on two earlier quarters. If choosing by past performance '
                    'worked, the highlighted squares would sit clearly above the grey cloud. The hold-out lies before the analysed '
                    'quarters, so this tests whether a choice is stable across periods, not whether it forecasts.</p>'
                    f'{stack}{"".join(x for x in ho if x)}</div>')
    cd = [section_candidates(out, sym) for sym in symbols]
    if any(cd):
        body.append('<h2>Candidate settings on all five quarters</h2>'
                    '<p class="lede">Five hand-picked timeframe families, the same for both symbols, each with the live ladder, '
                    'with no ladder, and with a short spaced ladder. They put H4 into the decision in different ways and were '
                    'chosen by eye from an earlier sweep of the three 2026 quarters: they are not the best of the sweep on either '
                    'symbol, those quarters flatter them, and only the two hold-out columns are independent evidence.</p>'
                    f'{stack}{"".join(x for x in cd if x)}</div>')
    # 5. changes to the rules
    pk = [section_packages(out, sym) for sym in symbols]
    if any(pk):
        body.append('<h2>What-ifs aimed at the flaws</h2>'
                    '<p class="lede">Each row changes the rules in one deliberate way that answers a weakness the baseline exposed '
                    '(the ladder that deploys at one price, the missing price-based exit, the tiny fixed target on a growing '
                    'basket). None of them was tuned on the data; they are hypotheses to take to a demo account, not a promise.</p>'
                    f'<div class="grid2">{"".join(x for x in pk if x)}</div>')
    for sym in symbols:
        lev = section_levers(out, sym)
        if lev:
            body.append(f'<h2>{sym}: every other knob, one at a time</h2>'
                        '<p class="lede">Each chart changes one parameter (or one structural rule) and leaves the rest at the live '
                        'value; one line per quarter, one path each. A parameter is only worth changing if all three lines move the '
                        f'same way by more than the timing noise above.</p><details><summary>Show the {lev.count("<h3>")} '
                        f'parameter charts for {sym}</summary>{lev}</details>')
    # 6. how fragile it all is
    for sym in symbols:
        rb = section_robust(out, sym)
        if rb:
            body.append(f'<h2>{sym}: how fragile is the result?</h2>' + rb)

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alcadeias backtest · {variant}</title>
<style>{T.CSS}</style>
<script src="assets/plotly.min.js"></script>
</head><body><div class="wrap">
<header class="top"><div><div class="brand">Alcadeias · backtest</div>
<h1>{variant.capitalize()} strategy on real Exness ticks</h1>
<div class="sub">XAUUSDm and BTCUSDm · $2,000 start · 1:2000 · the live RSI+MACD slope logic replayed poll by poll</div></div></header>
{banner}{''.join(b for b in body if b)}
<div class="foot">Rebuild everything with <code>python -m backtesting reproduce</code>; explore interactively with
<code>python -m backtesting studio</code>. Method, assumptions and limits: <code>BACKTEST.md</code>. Historical simulation is not a
forecast of live results.</div>
</div>
{_FIT_JS}
</body></html>"""
    path = out / "index.html"
    path.write_text(page, encoding="utf-8")
    return path
