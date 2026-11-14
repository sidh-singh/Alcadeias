"""
PNG snapshots of the interactive charts (for BACKTEST.md, which GitHub renders as-is).

A figure is written to a throw-away HTML page and photographed by a headless
Chrome, Chromium or Edge found on this machine (macOS, Windows or Linux). Nothing here
is needed to run a backtest; without a browser the functions return ``None`` and the
HTML reports are unaffected.
"""

from __future__ import annotations

import json
import ntpath
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..analysis.holdout import wiped as _wiped
from ..config import BacktestConfig, REPO_ROOT, TF_SECONDS
from ..data import store
from ..engine.fast import Result, run
from . import theme as T
from .report import _RESCALE_JS, _naive, closeup_figure, market_figure

def chrome_candidates(environ=None) -> List[str]:
    """
    Where a Chromium-family browser that can take headless screenshots usually is: full paths
    first (macOS application bundles, the Windows install folders), then the command names
    looked up on PATH (Linux packages, and anything the user put on PATH elsewhere).
    """
    environ = os.environ if environ is None else environ
    out = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    # Windows installs per machine under Program Files (either one, depending on the installer's
    # bitness) or per user under LocalAppData; the folders are read from the environment because
    # they differ between machines and languages. Edge ships with Windows 10 and 11.
    bases = [environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
    for exe in (("Google", "Chrome", "Application", "chrome.exe"),
                ("Microsoft", "Edge", "Application", "msedge.exe"),
                ("Chromium", "Application", "chrome.exe")):
        out += [ntpath.join(b, *exe) for b in bases if b]
    out += ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
            "microsoft-edge", "microsoft-edge-stable", "chrome", "msedge"]
    return out


_CHROME_CANDIDATES = chrome_candidates()


def find_chrome() -> Optional[str]:
    """The first candidate present on this machine, or None (the PNG snapshots are then skipped)."""
    for c in _CHROME_CANDIDATES:
        if os.path.isabs(c):
            if os.path.isfile(c):
                return c
            continue
        w = shutil.which(c)
        if w:
            return w
    return None


def figure_png(fig: go.Figure, path: Path, width: int = 1500, height: Optional[int] = None,
               title: str = "", subtitle: str = "", post_script: Optional[str] = None,
               wait_ms: int = 9000) -> Optional[Path]:
    """Render ``fig`` to ``path`` (PNG). Returns None when no headless browser is available."""
    chrome = find_chrome()
    if chrome is None:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig_h = int(fig.layout.height or 600)
    head = 0
    hdr = ""
    if title:
        head = 62 if subtitle else 40
        hdr = (f'<div style="padding:14px 18px 0"><div style="font-size:16px;font-weight:650;color:{T.INK}">{title}</div>'
               + (f'<div style="font-size:12.5px;color:{T.INK_2};margin-top:2px">{subtitle}</div>' if subtitle else "") + "</div>")
    height = height or (fig_h + head + 16)
    from plotly.offline import get_plotlyjs
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
        body = fig.to_html(full_html=False, include_plotlyjs=False, div_id="fig",
                           config={"displayModeBar": False, "responsive": True}, post_script=post_script)
        (tdp / "page.html").write_text(
            f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:{T.SURFACE};'
            f'font-family:{T.FONT}}}</style><script src="plotly.min.js"></script></head><body>{hdr}{body}</body></html>',
            encoding="utf-8")
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               f"--user-data-dir={tdp / 'profile'}", f"--window-size={width},{height}",
               f"--virtual-time-budget={wait_ms}", "--force-device-scale-factor=2",
               f"--screenshot={path}", (tdp / "page.html").as_uri()]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
    return path if path.exists() else None


# ───────────────────────────── figures for the write-up ─────────────────────────────

def overview_figure(res: Result, m1: Dict[str, np.ndarray], tf: str = "H1") -> go.Figure:
    """Whole period: price with exits, then equity, then exposure."""
    return market_figure(res, m1, tfs=(tf,), default_tf=tf, height=900, initial_days=10_000)


def zoom_figure(res: Result, m1: Dict[str, np.ndarray], center: pd.Timestamp, hours: float = 30.0,
                tf: str = "M15") -> go.Figure:
    fig = market_figure(res, m1, tfs=(tf,), default_tf=tf, height=900, initial_days=1.0)
    a = (center - pd.Timedelta(hours=hours / 2)).tz_localize(None) if center.tzinfo else center - pd.Timedelta(hours=hours / 2)
    z = a + pd.Timedelta(hours=hours)
    fig.update_xaxes(range=[a, z], row=4, col=1)
    return fig


def attribution_figure(res: Result) -> go.Figure:
    b = res.baskets
    fig = make_subplots(rows=1, cols=3, horizontal_spacing=0.07,
                        subplot_titles=("Net P/L by exit reason", "Net P/L by ladder depth (positions in the basket)",
                                        "Cumulative realised P/L by exit reason"))
    g = b.groupby("reason")["pnl"].sum().sort_values(ascending=False)
    fig.add_trace(go.Bar(x=[T.REASON_LABEL.get(r, r).split(" (")[0] for r in g.index], y=g.values, width=0.4,
                         marker=dict(color=[T.REASON_COLOR.get(r, T.CONTEXT) for r in g.index]),
                         text=[f"{v:+,.0f}" for v in g.values], textposition="outside", cliponaxis=False,
                         textfont=dict(color=T.INK, size=12), constraintext="none", showlegend=False), row=1, col=1)
    d = b.groupby("n_pos")["pnl"].sum()
    fig.add_trace(go.Bar(x=[str(int(k)) for k in d.index], y=d.values, width=0.5,
                         marker=dict(color=[T.UP if v > 0 else T.DOWN for v in d.values]),
                         text=[f"{v:+,.0f}" for v in d.values], textposition="outside", cliponaxis=False,
                         textfont=dict(color=T.INK, size=12), constraintext="none", showlegend=False), row=1, col=2)
    bs = b.sort_values("close_time")
    for r in [r for r in T.REASON_COLOR if r in set(bs["reason"])]:
        gg = bs[bs["reason"] == r]
        fig.add_trace(go.Scatter(x=_naive(gg["close_time"]), y=gg["pnl"].cumsum(), mode="lines",
                                 name=T.REASON_LABEL.get(r, r).split(" (")[0],
                                 line=dict(color=T.REASON_COLOR[r], width=2, shape="hv")), row=1, col=3)
    fig.add_trace(go.Scatter(x=_naive(bs["close_time"]), y=bs["pnl"].cumsum(), mode="lines", name="All baskets",
                             line=dict(color=T.INK, width=1.4, shape="hv")), row=1, col=3)
    fig.update_layout(**T.plotly_layout(height=380, margin=dict(l=56, r=18, t=46, b=40), hovermode="closest",
                                        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="right", x=1,
                                                    font=dict(color=T.INK_2, size=11.5), bgcolor="rgba(0,0,0,0)")))
    for c in (1, 2, 3):
        fig.update_xaxes(**T.axis(showgrid=(c == 3), type="category" if c < 3 else "date"), row=1, col=c)
        fig.update_yaxes(**T.axis(zeroline=True, zerolinecolor=T.AXIS, tickformat=",.0f"), row=1, col=c)
    for a in fig.layout.annotations:
        a.font = dict(color=T.INK, size=13)
        a.x = a.x - 0.0
    for tr in fig.data[:2]:
        v = np.asarray(tr.y, dtype=float)
        span = max(abs(v.max(initial=0)), abs(v.min(initial=0)), 1e-9)
        ax = "yaxis" if tr is fig.data[0] else "yaxis2"
        fig.layout[ax].range = [min(v.min(initial=0), 0) - span * 0.2, max(v.max(initial=0), 0) + span * 0.2]
    return fig


def equity_figure(equity_csv: Path, title_balance: str = "Balance") -> go.Figure:
    e = pd.read_csv(equity_csv)
    e["time"] = pd.to_datetime(e["time"], format="ISO8601")
    e = e.set_index("time")
    step = "4h"
    last = e[["balance", "equity"]].resample(step, label="right", closed="right").last().dropna()
    lo = e["equity"].resample(step, label="right", closed="right").min().reindex(last.index)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=last.index, y=last["balance"], mode="lines", name=title_balance,
                             line=dict(color=T.CONTEXT, width=1.5, shape="hv")))
    fig.add_trace(go.Scatter(x=last.index, y=lo, mode="lines", name="Equity (low of each 4 h)",
                             line=dict(color=T.EMPHASIS, width=2)))
    fig.add_hline(y=float(e["balance"].iloc[0]), line=dict(color=T.AXIS, width=1))
    fig.update_layout(**T.plotly_layout(height=360, margin=dict(l=60, r=18, t=30, b=34)))
    fig.update_xaxes(**T.axis())
    fig.update_yaxes(**T.axis(title_text="USD", tickformat=",.0f"))
    return fig


def timeframe_figure(out: Path, sym: str, base: BacktestConfig) -> Optional[go.Figure]:
    """OPEN timeframes x FORCE-CLOSE timeframe, one heatmap per window (live threshold convention)."""
    p = Path(out) / "sweeps" / f"{sym}_timeframes.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    wins = [c.split("@")[1] for c in df.columns if c.startswith("net_profit@")]
    norm = lambda x: "+".join(sorted(str(x).split("+"), key=TF_SECONDS.get, reverse=True))
    df["open"], df["fc"] = df["open"].map(norm), df["fc"].map(norm)
    strict = "strict" if (base.entry_s >= 2.0 * len(base.open_weights) and len(base.open_weights) > 1) else "loose"
    lvl = "half" if base.force_close_s <= 1.0 else "full"
    sub = df[(df["entry"] == strict) & (df["fc_level"] == lvl)]
    opens = sorted(sub["open"].unique(), key=lambda x: (len(x.split("+")), tuple(-TF_SECONDS[t] for t in x.split("+"))))
    fcs = sorted(sub["fc"].unique(), key=lambda x: -TF_SECONDS.get(x, 0))
    zmax = float(np.nanpercentile(np.abs(sub[[f"net_profit@{w}" for w in wins]].to_numpy()), 97)) or 1.0
    labels = {"IS": "13 Aug → 13 Nov 2026 (asked for)", "OOS1": "13 May → 13 Aug 2026", "OOS2": "13 Feb → 13 May 2026"}
    fig = make_subplots(rows=1, cols=len(wins), horizontal_spacing=0.035, shared_yaxes=True,
                        subplot_titles=[labels.get(w, w) for w in wins])
    live_open, live_fc = norm("+".join(base.open_weights)), norm("+".join(base.fc_weights))
    for i, w in enumerate(wins, 1):
        piv = sub.pivot_table(index="open", columns="fc", values=f"net_profit@{w}", aggfunc="first").reindex(index=opens, columns=fcs)
        dip = (sub.assign(_w=_wiped(sub, w).astype(float))
               .pivot_table(index="open", columns="fc", values="_w", aggfunc="first").reindex(index=opens, columns=fcs))
        z = piv.to_numpy()
        text = [[("" if np.isnan(v) else (f"{v / 1000:+.1f}k" if abs(v) >= 1000 else f"{v:+.0f}")
                  + (" ✕" if dip.to_numpy()[r][c] > 0 else ""))
                 for c, v in enumerate(row)] for r, row in enumerate(z)]
        fig.add_trace(go.Heatmap(z=z, x=fcs, y=opens, zmin=-zmax, zmax=zmax, xgap=2, ygap=2,
                                 colorscale=[[0.0, T.DOWN], [0.5, "#27304d"], [1.0, T.UP]], showscale=(i == len(wins)),
                                 text=text, texttemplate="%{text}", textfont=dict(color=T.INK, size=10.5),
                                 colorbar=dict(thickness=10, len=0.85, outlinewidth=0,
                                               tickfont=dict(color=T.INK_MUTED, size=10))), row=1, col=i)
        if live_fc in fcs and live_open in opens:
            a, b = fcs.index(live_fc), opens.index(live_open)
            fig.add_shape(type="rect", x0=a - 0.5, x1=a + 0.5, y0=b - 0.5, y1=b + 0.5,
                          line=dict(color=T.ACCENT, width=2), row=1, col=i)
        fig.update_xaxes(**T.axis(showgrid=False, type="category", title_text="FORCE-CLOSE timeframe"), row=1, col=i)
        fig.update_yaxes(**T.axis(showgrid=False, type="category", autorange="reversed",
                                  title_text="OPEN timeframes" if i == 1 else None), row=1, col=i)
    fig.update_layout(**T.plotly_layout(height=150 + 27 * len(opens), margin=dict(l=96, r=20, t=46, b=48),
                                        hovermode="closest", showlegend=False))
    for a in fig.layout.annotations:
        a.font = dict(color=T.INK, size=13)
    return fig


def packages_figure(out: Path, sym: str) -> Optional[go.Figure]:
    p = Path(out) / "packages" / f"{sym}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    wins = [c.split("@")[1] for c in df.columns if c.startswith("net_profit@")]
    df["total"] = df[[f"net_profit@{w}" for w in wins]].sum(axis=1)
    df["n_ruin"] = sum(_wiped(df, w).astype(int) for w in wins)
    live = df[df["package"] == "live settings"]
    rest = df[df["package"] != "live settings"].sort_values(["n_ruin", "total"], ascending=[True, False])
    d = pd.concat([live, rest])
    fig = go.Figure(go.Bar(
        y=d["package"], x=d["total"], orientation="h", width=0.62,
        marker=dict(color=[T.UP if v > 0 else T.DOWN for v in d["total"]], line=dict(width=0)),
        text=[f"{v:+,.0f}" + (" ✕" * int(r > 0)) for v, r in zip(d["total"], d["n_ruin"])],
        textposition="outside", textfont=dict(color=T.INK, size=11.5), cliponaxis=False, constraintext="none"))
    span = max(abs(d["total"].max()), abs(d["total"].min()), 1.0)
    fig.update_layout(**T.plotly_layout(height=70 + 25 * len(d), margin=dict(l=10, r=40, t=10, b=40), showlegend=False,
                                        hovermode="closest", bargap=0.3))
    fig.update_xaxes(**T.axis(title_text="Net P/L of one 0.01-lot unit, three windows added up, USD", zeroline=True,
                              zerolinecolor=T.AXIS, tickformat=",.0f",
                              range=[min(d["total"].min(), 0) - span * 0.2, max(d["total"].max(), 0) + span * 0.2]))
    fig.update_yaxes(**T.axis(showgrid=False, autorange="reversed", tickfont=dict(color=T.INK_2, size=12)))
    return fig


def _load_result(run_dir: Path, live_root: Path, mode: str) -> Optional[Result]:
    j = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    cfg = BacktestConfig.from_dict(j["config"])
    return run(cfg, mode=mode)


def build_gallery(out: Path, symbols: Sequence[str] = ("XAUUSDm", "BTCUSDm"), live_root: Path = REPO_ROOT,
                  log=print) -> List[Path]:
    """Write backtest_results/img/*.png from the committed baseline / long runs."""
    out = Path(out)
    img = out / "img"
    made: List[Path] = []
    if find_chrome() is None:
        log("no Chrome, Chromium or Edge found on this machine - skipping the PNG snapshots "
            "(the HTML pages do not need them)")
        return made
    for sym in symbols:
        d = out / "baseline" / sym
        if not (d / "summary.json").exists():
            continue
        j = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        cfg = BacktestConfig.from_dict(j["config"])
        res = run(cfg, mode=j.get("engine", {}).get("mode", "sec"))
        m1 = store.load_m1(cfg.symbol, cfg.start, cfg.end)
        s = res.summary()
        sub = (f"{cfg.start} → {cfg.end} UTC · net {s['net_profit']:+,.2f} USD on ${cfg.initial_balance:,.0f} · "
               f"max drawdown {s['max_drawdown_pct']:.0f}% · {s['baskets']:,} baskets · win rate {s.get('win_rate_pct', 0):.1f}%")
        js = (_RESCALE_JS.replace("__START__", pd.Timestamp(int(m1["t"][0]), unit="s").strftime("%Y-%m-%d %H:%M:%S"))
              .replace("__END__", pd.Timestamp(int(m1["t"][-1]) + 60, unit="s").strftime("%Y-%m-%d %H:%M:%S")))
        p = figure_png(overview_figure(res, m1), img / f"{sym}_overview.png",
                       title=f"{sym} · {cfg.variant} · live settings, three months", subtitle=sub, post_script=js)
        made += [p] if p else []
        # a busy day and a half, close enough to read every fill
        b = res.baskets
        if len(b):
            day = b.assign(d=b["open_time"].dt.floor("D")).groupby("d").size()
            center = day.sort_values().index[int(len(day) * 0.8)] + pd.Timedelta(hours=12)
            p = figure_png(zoom_figure(res, m1, center), img / f"{sym}_zoom.png",
                           title=f"{sym} · 30 hours up close",
                           subtitle="▲ ▼ entries · hollow triangles = ladder adds · ● target exit · ✕ force-close · "
                                    "exit colour = basket won / lost", post_script=js)
            made += [p] if p else []
            p = figure_png(attribution_figure(res), img / f"{sym}_attribution.png",
                           title=f"{sym} · where the money came from and went", subtitle=sub)
            made += [p] if p else []
            worst = int(b.loc[b["pnl"].idxmin(), "basket"])
            cf = closeup_figure(res, worst)
            if cf is not None:
                r = b[b["basket"] == worst].iloc[0]
                cf.update_layout(height=560)
                p = figure_png(cf, img / f"{sym}_worst_basket.png", width=1300,
                               title=f"{sym} · the worst basket, second by second",
                               subtitle=(f"{r['side']} · {int(r['n_pos'])} positions · {r['lots']:.2f} lot · opened "
                                         f"{r['open_time']:%d %b %H:%M:%S} UTC · held {r['duration_s'] / 3600:.1f} h · "
                                         f"closed by {r['reason'].replace('_', ' ')} at {r['pnl']:+,.2f} USD"))
                made += [p] if p else []
        le = out / "long" / sym / "equity.csv.gz"
        if le.exists():
            lj = json.loads((out / "long" / sym / "summary.json").read_text(encoding="utf-8"))["summary"]
            p = figure_png(equity_figure(le), img / f"{sym}_long_equity.png", width=1300,
                           title=f"{sym} · live settings from {lj['start']} to {lj['end']}",
                           subtitle=(f"net {lj['net_profit']:+,.2f} USD on ${lj['initial_balance']:,.0f} · max drawdown "
                                     f"{lj['max_drawdown_pct']:.0f}%" + (" · account stopped out" if lj["stopped_out"] else "")))
            made += [p] if p else []
    for sym in symbols:
        base = BacktestConfig.live(sym, repo_root=live_root)
        tf = timeframe_figure(out, sym, base)
        if tf is not None:
            p = figure_png(tf, img / f"{sym}_timeframes.png", width=1700,
                           title=f"{sym} · OPEN timeframes × FORCE-CLOSE timeframe on three separate quarters",
                           subtitle="Net P/L of one fixed 0.01-lot unit, USD · ✕ = the same baskets wipe a real $2,000 account "
                                    "(the bot's own lot sizing) · gold frame = the live setting")
            made += [p] if p else []
        pk = packages_figure(out, sym)
        if pk is not None:
            p = figure_png(pk, img / f"{sym}_whatifs.png", width=1300,
                           title=f"{sym} · what-ifs aimed at the flaws",
                           subtitle="One fixed 0.01-lot unit, three quarters added up · ✕ = the same baskets wipe a real $2,000 "
                                    "account in at least one quarter · first row = live settings")
            made += [p] if p else []
    from .index import candidates_figure, candidates_mode, holdout_figure
    for sym in symbols:
        base = BacktestConfig.live(sym, repo_root=live_root)
        r = holdout_figure(out, sym, base, height=520)
        if r is not None:
            fig, _, facts = r
            p = figure_png(fig, img / f"{sym}_holdout.png", width=1100,
                           title=f"{sym} · do timeframes chosen on past data hold up on data they never saw?",
                           subtitle=(f"One dot per timeframe setting ({facts['settings']}), one 0.01-lot unit · across: average per "
                                     f"quarter on the three analysed quarters · up: on the two hold-out quarters · rank "
                                     f"correlation {facts['rank_correlation']:+.2f}"))
            made += [p] if p else []
        r = candidates_figure(out, sym)
        if r is not None:
            fig, cdf, fams = r
            what = ("Median net P/L of eight raw-tick runs per quarter on a fresh $2,000 (unit auto-step), USD · ✕ = one or more of "
                    "the eight stopped out" if candidates_mode(cdf) == "ensemble" else
                    "Net P/L of one fixed 0.01-lot unit per quarter, USD · ✕ = the same baskets wipe a real $2,000 account")
            p = figure_png(fig, img / f"{sym}_candidates.png", width=1300,
                           title=f"{sym} · candidate settings on five quarters",
                           subtitle=what + " · " + " · ".join(f"{k} = {v}" for k, v in fams)[:300])
            made += [p] if p else []
    for p in made:
        log(f"  {p.relative_to(out)}")
    return made
