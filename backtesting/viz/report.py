"""
Static HTML report for one backtest run.

``build_report(result, out_dir)`` writes a self-contained page (``report.html``) plus the
raw tables behind every chart (``baskets.csv``, ``fills.csv``, ``equity.csv.gz``,
``summary.json``):

* headline tiles,
* the market: candles with every entry / ladder add / exit marked at its fill price,
  and under it -- on the same time axis -- equity, exposure and the section scores,
* where the money came from and went: by exit reason, ladder depth, side, hour, weekday,
* the shape of the risk: worst baskets, adverse excursion, holding time,
* a close-up gallery that replays individual baskets second by second.

Charts follow ``viz/theme.py``; every chart has its numbers in a table next to it.
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

from ..config import BacktestConfig, TF_SECONDS
from ..data import store
from ..engine.fast import Result, prepare, run
from . import theme as T

PLOTLY_JS = "plotly.min.js"
_CONFIG = {"displaylogo": False, "scrollZoom": True, "responsive": True,
           "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}


# ───────────────────────────── helpers ─────────────────────────────

def _money(x: float, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    s = f"{abs(x):,.2f}"
    if signed:
        return ("+" if x > 0 else "-" if x < 0 else "") + "$" + s
    return ("-" if x < 0 else "") + "$" + s


def _num(x, nd: int = 2) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    return f"{x:,.{nd}f}"


def _dur(s: float) -> str:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return "-"
    s = float(s)
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.1f}m"
    if s < 172800:
        return f"{s / 3600:.1f}h"
    return f"{s / 86400:.1f}d"


def _sign_cls(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""


def _fig_html(fig: go.Figure, div_id: str, post_script: Optional[str] = None) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id,
                       config=_CONFIG, post_script=post_script)


def _table(df: pd.DataFrame, left_cols: Sequence[str] = ()) -> str:
    head = "".join(f'<th class="{"l" if c in left_cols else ""}">{html.escape(str(c))}</th>' for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        tds = "".join(f'<td class="{"l" if c in left_cols else ""}">{html.escape(str(r[c]))}</td>' for c in df.columns)
        rows.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def weekend_breaks(bar_t_s: np.ndarray, min_gap_s: int = 6 * 3600) -> List[dict]:
    """Plotly rangebreaks that hide long no-trade gaps (the gold weekend)."""
    if len(bar_t_s) < 2:
        return []
    gaps = np.flatnonzero(np.diff(bar_t_s) > min_gap_s)
    out = []
    for i in gaps:
        a, b = int(bar_t_s[i]) + 60, int(bar_t_s[i + 1])
        out.append(dict(values=[pd.Timestamp(a, unit="s").strftime("%Y-%m-%d %H:%M:%S")],
                        dvalue=(b - a) * 1000))
    return out


# rescale the y axes to what is visible after every pan / zoom (plotly does not do this itself)
_RESCALE_JS = """
(function(){
  var gd = document.getElementById('{plot_id}');
  if(!gd) return;
  var busy = false, level = -1;
  // plotly treats date strings as wall-clock time; parse them the same way (as UTC) everywhere
  function p(s){ if(typeof s !== 'string') return +s; return Date.parse(s.slice(0, 19).replace(' ', 'T') + 'Z'); }
  function vis(tr){ return tr.visible === undefined || tr.visible === true; }
  function rescale(){
    if(busy) return;
    var xr = (gd._fullLayout && gd._fullLayout.xaxis ? gd._fullLayout.xaxis.range : gd.layout.xaxis.range); if(!xr) return;
    var x0 = p(xr[0]), x1 = p(xr[1]);
    var ext = {};
    gd.data.forEach(function(tr){
      if(!vis(tr) || !tr.x) return;
      var ya = tr.yaxis || 'y';
      var lo = tr.type === 'candlestick' ? tr.low : tr.y, hi = tr.type === 'candlestick' ? tr.high : tr.y;
      if(!lo) return;
      var e = ext[ya] || [Infinity, -Infinity];
      for(var i = 0; i < tr.x.length; i++){
        if(tr.x[i] === null) continue;
        var t = p(tr.x[i]);
        if(t < x0 || t > x1) continue;
        var a = lo[i], b = hi[i];
        if(a === null || b === null || isNaN(a) || isNaN(b)) continue;
        if(a < e[0]) e[0] = a; if(b > e[1]) e[1] = b;
      }
      ext[ya] = e;
    });
    var upd = {};
    Object.keys(ext).forEach(function(ya){
      var e = ext[ya]; if(!isFinite(e[0]) || !isFinite(e[1])) return;
      var pad = (e[1] - e[0]) * 0.07 || Math.abs(e[1]) * 0.001 || 1;
      var name = ya === 'y' ? 'yaxis' : 'yaxis' + ya.slice(1);
      upd[name + '.range'] = [e[0] - pad, e[1] + pad];
    });
    // trade marks shrink as the view widens so they never bury the candles
    var days = (x1 - x0) / 86400000;
    var lv = days > 21 ? 0 : days > 6 ? 1 : days > 1.5 ? 2 : 3;
    var sizes = [4, 6, 8, 11], idx = [];
    gd.data.forEach(function(tr, i){ if(tr.meta === 'trade') idx.push(i); });
    busy = true;
    var chain = Plotly.relayout(gd, upd);
    if(lv !== level && idx.length){
      level = lv;
      chain = chain.then(function(){ return Plotly.restyle(gd, {'marker.size': sizes[lv]}, idx); });
    }
    chain.then(function(){ busy = false; });
  }
  gd.on('plotly_relayout', function(ev){
    if(!ev) return;
    if(Object.keys(ev).some(function(k){ return k.indexOf('xaxis') === 0; })) rescale();
  });
  window.alcSetTF = function(i, n, btn){
    var v = []; for(var k = 0; k < n; k++) v.push(k === i);
    var ids = []; for(var k = 0; k < n; k++) ids.push(k);
    Plotly.restyle(gd, {visible: v}, ids).then(rescale);
    btn.parentNode.querySelectorAll('button').forEach(function(b){ b.classList.remove('on'); });
    btn.classList.add('on');
  };
  window.alcSetSpan = function(days, btn){
    var a = p(gd.dataset.start), z = p(gd.dataset.end);
    var from = days ? Math.max(a, z - days * 86400000) : a;
    var iso = function(t){ return new Date(t).toISOString().slice(0, 19).replace('T', ' '); };
    Plotly.relayout(gd, {'xaxis.range': [iso(from), iso(z)]});
    btn.parentNode.querySelectorAll('button').forEach(function(b){ b.classList.remove('on'); });
    btn.classList.add('on');
  };
  gd.dataset.start = '__START__'; gd.dataset.end = '__END__';
  rescale();
})();
"""


# ───────────────────────────── the market figure ─────────────────────────────

def _naive(x):
    """UTC wall-clock datetimes without tz info (plotly drops offsets; keep one convention)."""
    if isinstance(x, pd.Series):
        return x.dt.tz_convert(None) if x.dt.tz is not None else x
    if isinstance(x, pd.DatetimeIndex):
        return x.tz_convert(None) if x.tz is not None else x
    if isinstance(x, pd.Timestamp):
        return x.tz_convert(None) if x.tzinfo is not None else x
    return x


def _trade_traces(res: Result) -> List[go.Scatter]:
    """Entry / add / exit marks. Shape carries the meaning; the HTML key above the chart names them."""
    f, b = res.fills, res.baskets
    traces: List[go.Scatter] = []
    ring = dict(color=T.SURFACE, width=1.2)

    # connectors: entry -> exit, coloured by outcome (two traces, None-separated)
    for won, color in ((True, T.UP), (False, T.DOWN)):
        g = b[b["pnl"] > 0] if won else b[b["pnl"] <= 0]
        if len(g) == 0:
            continue
        xs, ys = [], []
        for ot, ct, p0, p1 in zip(_naive(g["open_time"]), _naive(g["close_time"]), g["first_price"], g["close_price"]):
            xs += [ot, ct, None]
            ys += [p0, p1, None]
        traces.append(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=1),
                                 opacity=0.4, hoverinfo="skip", showlegend=False))

    opens = f[f["action"] == "open"]
    adds = f[f["action"] == "add"]
    for side, sym, color in (("BUY", "triangle-up", T.UP), ("SELL", "triangle-down", T.DOWN)):
        g = opens[opens["side"] == side]
        if len(g):
            cd = np.stack([g["lots"], g["open_score"], g["fc_score"], g["basket"], g["units"]], axis=1)
            traces.append(go.Scatter(
                x=_naive(g["time"]), y=g["price"], mode="markers", name=f"Open {side}", meta="trade", showlegend=False,
                marker=dict(symbol=sym, size=10, color=color, line=ring), customdata=cd,
                hovertemplate=(f"<b>OPEN {side}</b> %{{customdata[0]:.2f}} lot @ %{{y:,.2f}}"
                               "<br>basket #%{customdata[3]:.0f} · unit %{customdata[4]:.0f}"
                               "<br>open score %{customdata[1]:+.0f} · fc score %{customdata[2]:+.0f}<extra></extra>")))
        g = adds[adds["side"] == side]
        if len(g):
            cd = np.stack([g["lots"], g["n_pos"], g["basket"], g["basket_profit"]], axis=1)
            traces.append(go.Scatter(
                x=_naive(g["time"]), y=g["price"], mode="markers", name=f"Ladder add {side}", meta="trade", showlegend=False,
                marker=dict(symbol=sym + "-open", size=8, color=color, line=dict(color=color, width=1.6)),
                customdata=cd, text=g["tier"],
                hovertemplate=(f"<b>ADD {side}</b> %{{customdata[0]:.2f}} lot @ %{{y:,.2f}}"
                               "<br>position %{customdata[1]:.0f} · tier %{text} RSI"
                               "<br>basket #%{customdata[2]:.0f} floating %{customdata[3]:+,.2f}<extra></extra>")))

    for reason in [r for r in T.REASON_SYMBOL if r in set(b["reason"])]:
        for won, color in ((True, T.UP), (False, T.DOWN)):
            g = b[(b["reason"] == reason) & ((b["pnl"] > 0) if won else (b["pnl"] <= 0))]
            if len(g) == 0:
                continue
            cd = np.stack([g["pnl"], g["n_pos"], g["lots"], g["duration_s"], g["basket"], g["mae"]], axis=1)
            sym = T.REASON_SYMBOL[reason]
            traces.append(go.Scatter(
                x=_naive(g["close_time"]), y=g["close_price"], mode="markers", meta="trade", showlegend=False,
                name=f"Exit: {reason.replace('_', ' ')} ({'won' if won else 'lost'})",
                marker=dict(symbol=sym, size=9, color=color,
                            line=dict(color=color, width=2) if sym == "x" else ring),
                customdata=cd, text=g["side"],
                hovertemplate=(f"<b>CLOSE</b> ({reason.replace('_', ' ')}) @ %{{y:,.2f}}"
                               "<br>basket #%{customdata[4]:.0f} %{text} · %{customdata[1]:.0f} pos · %{customdata[2]:.2f} lot"
                               "<br>P/L <b>%{customdata[0]:+,.2f}</b> · worst floating %{customdata[5]:+,.2f}"
                               "<br>held %{customdata[3]:,.0f}s<extra></extra>")))
    return traces


def market_figure(res: Result, m1: Dict[str, np.ndarray], tfs: Sequence[str] = ("M15", "H1", "H4"),
                  default_tf: str = "M15", height: int = 1000, initial_days: float = 7.0) -> go.Figure:
    """Candles + every fill, and below them equity, exposure and the section scores on one time axis."""
    cfg = res.cfg
    has_book = cfg.book_enabled
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.02,
                        row_heights=[0.52, 0.20, 0.11, 0.17])

    for tf in tfs:
        bars = store.resample_bars(m1, TF_SECONDS[tf])
        x = pd.to_datetime(bars["t"], unit="s")
        fig.add_trace(go.Candlestick(
            x=x, open=bars["o"], high=bars["h"], low=bars["l"], close=bars["c"], name=f"{cfg.symbol} {tf}",
            increasing=dict(line=dict(color=T.UP, width=1), fillcolor=T.UP),
            decreasing=dict(line=dict(color=T.DOWN, width=1), fillcolor=T.DOWN),
            visible=(tf == default_tf), showlegend=False), row=1, col=1)
    for tr in _trade_traces(res):
        fig.add_trace(tr, row=1, col=1)

    eq = res.equity
    if len(eq):
        e = eq.assign(time=_naive(eq["time"])).set_index("time")
        step = "15min"
        last = e[["balance", "equity", "lots", "open_score", "fc_score", "book_score"]].resample(step, label="right", closed="right").last().dropna(how="all")
        lo = e["equity"].resample(step, label="right", closed="right").min().reindex(last.index)
        hi = e["equity"].resample(step, label="right", closed="right").max().reindex(last.index)
        x = last.index
        # simplify=False: with a zero-width line plotly would otherwise decimate the band to a rough hull
        fig.add_trace(go.Scatter(x=x, y=hi, mode="lines", line=dict(width=0, simplify=False), hoverinfo="skip",
                                 showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=lo, mode="lines", line=dict(width=0, simplify=False), fill="tonexty",
                                 fillcolor="rgba(57,135,229,0.22)", hoverinfo="skip", showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=last["balance"], mode="lines", name="Balance",
                                 line=dict(color=T.CONTEXT, width=1.5, shape="hv"),
                                 hovertemplate="balance %{y:,.2f}<extra></extra>"), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=last["equity"], mode="lines", name="Equity (band = range inside each 15 min)",
                                 line=dict(color=T.EMPHASIS, width=2),
                                 hovertemplate="equity %{y:,.2f}<extra></extra>"), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=last["lots"], mode="lines", name="Open lots",
                                 line=dict(color=T.INK_MUTED, width=1.2, shape="hv"), fill="tozeroy",
                                 fillcolor="rgba(138,143,163,0.14)", showlegend=False,
                                 hovertemplate="open lots %{y:+.2f}<extra></extra>"), row=3, col=1)
        for col in ["open_score", "fc_score"] + (["book_score"] if has_book else []):
            fig.add_trace(go.Scatter(x=x, y=last[col], mode="lines", name=T.SCORE_LABEL[col],
                                     line=dict(color=T.SCORE_COLOR[col], width=1.4, shape="hv"),
                                     hovertemplate=T.SCORE_LABEL[col] + " %{y:+.0f}<extra></extra>"),
                          row=4, col=1)

    breaks = weekend_breaks(m1["t"]) if len(m1.get("t", [])) else []
    fig.update_layout(**T.plotly_layout(
        height=height, margin=dict(l=64, r=18, t=34, b=28), hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.005, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=T.INK_2, size=11.5), traceorder="normal")))
    end = pd.Timestamp(int(m1["t"][-1]) + 60, unit="s")
    start = max(pd.Timestamp(int(m1["t"][0]), unit="s"), end - pd.Timedelta(days=initial_days))
    for r in range(1, 5):
        fig.update_xaxes(**T.axis(rangebreaks=breaks, rangeslider=dict(visible=False),
                                  showticklabels=(r == 4)), row=r, col=1)
    fig.update_xaxes(range=[start, end], row=4, col=1)
    fig.update_yaxes(**T.axis(title_text="Price (bid)", tickformat=",.0f" if cfg.symbol.startswith("BTC") else ",.1f"), row=1, col=1)
    fig.update_yaxes(**T.axis(title_text="Account, USD", tickformat=",.0f"), row=2, col=1)
    fig.update_yaxes(**T.axis(title_text="Lots (+long / -short)", tickformat="+.2f", zeroline=True, zerolinecolor=T.AXIS), row=3, col=1)
    fig.update_yaxes(**T.axis(title_text="Score", zeroline=True, zerolinecolor=T.AXIS, dtick=1), row=4, col=1)
    return fig


def market_controls(tfs: Sequence[str], default_tf: str = "M15", default_span: str = "1W") -> str:
    """One filter row above the chart: candle timeframe and visible span."""
    tf_btns = "".join(
        f'<button class="{"on" if tf == default_tf else ""}" onclick="alcSetTF({i},{len(tfs)},this)">{tf}</button>'
        for i, tf in enumerate(tfs))
    spans = [("1D", 1), ("3D", 3), ("1W", 7), ("1M", 30), ("All", 0)]
    sp_btns = "".join(
        f'<button class="{"on" if lab == default_span else ""}" onclick="alcSetSpan({d},this)">{lab}</button>'
        for lab, d in spans)
    return (f'<div class="controls"><span class="lab">Candles</span><span class="seg">{tf_btns}</span>'
            f'<span class="lab">Show</span><span class="seg">{sp_btns}</span></div>')


# ───────────────────────────── attribution ─────────────────────────────

def _bar(labels, values, colors, title_y: str = "Net P/L, USD", text=None, height: int = 280,
         hover: Optional[str] = None) -> go.Figure:
    vals = np.asarray(values, dtype=float)
    fig = go.Figure(go.Bar(
        x=list(labels), y=vals, marker=dict(color=colors, line=dict(width=0)), width=0.55,
        text=[(_money(v, signed=True) if text is None else t) for v, t in zip(vals, text or [None] * len(vals))],
        textposition="outside", textfont=dict(color=T.INK, size=11), cliponaxis=False, constraintext="none",
        hovertemplate=hover or "%{x}<br><b>%{y:+,.2f}</b><extra></extra>"))
    span = max(abs(vals.max(initial=0)), abs(vals.min(initial=0)), 1e-9)
    fig.update_layout(**T.plotly_layout(height=height, margin=dict(l=56, r=14, t=22, b=40),
                                        showlegend=False, hovermode="closest", bargap=0.35))
    fig.update_xaxes(**T.axis(showgrid=False, type="category"))
    fig.update_yaxes(**T.axis(title_text=title_y, zeroline=True, zerolinecolor=T.AXIS,
                              range=[min(vals.min(initial=0), 0) - span * 0.18, max(vals.max(initial=0), 0) + span * 0.18]))
    return fig


def _pol(values) -> List[str]:
    return [T.UP if v > 0 else T.DOWN if v < 0 else T.NEUTRAL for v in values]


def attribution_blocks(res: Result) -> List[str]:
    b = res.baskets
    out: List[str] = []
    if len(b) == 0:
        return out

    def block(title: str, cap: str, fig: go.Figure, table: pd.DataFrame, div_id: str, left=("",)) -> str:
        return (f'<div class="card"><h3>{html.escape(title)}</h3><p class="cap">{cap}</p>'
                f'{_fig_html(fig, div_id)}'
                f'<details><summary>Table view</summary><div class="scroll">{_table(table, left_cols=[table.columns[0]])}</div></details></div>')

    def agg(key, order=None, label=None):
        g = b.groupby(key).agg(baskets=("pnl", "size"), net=("pnl", "sum"),
                               win_rate=("pnl", lambda s: (s > 0).mean() * 100),
                               avg=("pnl", "mean"), worst=("pnl", "min")).reset_index()
        if order is not None:
            g = g.set_index(key).reindex(order).dropna(how="all").reset_index()
        if label:
            g[key] = g[key].map(label)
        return g

    def fmt(g, first):
        t = g.copy()
        t.columns = [first, "Baskets", "Net P/L", "Win %", "Avg P/L", "Worst"]
        t["Baskets"] = t["Baskets"].astype(int)
        for c in ("Net P/L", "Avg P/L", "Worst"):
            t[c] = t[c].map(lambda v: _money(v, signed=True))
        t["Win %"] = t["Win %"].map(lambda v: _num(v, 1))
        return t

    # exit reason (identity colours)
    g = agg("reason")
    g = g.sort_values("net", ascending=False)
    fig = _bar([T.REASON_LABEL.get(r, r).split(" (")[0] for r in g["reason"]], g["net"],
               [T.REASON_COLOR.get(r, T.CONTEXT) for r in g["reason"]])
    t = fmt(g.assign(reason=g["reason"].map(lambda r: T.REASON_LABEL.get(r, r))), "Exit reason")
    out.append(block("Net P/L by exit reason", "What each exit rule earned or cost in total.", fig, t, "attr_reason"))

    # ladder depth (polarity)
    g = agg("n_pos")
    fig = _bar([f"{int(k)} pos" for k in g["n_pos"]], g["net"], _pol(g["net"]))
    t = fmt(g.assign(n_pos=g["n_pos"].map(lambda k: f"{int(k)} position{'s' if k > 1 else ''}")), "Basket depth")
    out.append(block("Net P/L by ladder depth", "1 position = no DCA add; 6 = the full Fibonacci ladder (32 units).", fig, t, "attr_depth"))

    # side
    g = agg("side", order=["BUY", "SELL"])
    fig = _bar(["Long (BUY)" if s == "BUY" else "Short (SELL)" for s in g["side"]], g["net"], _pol(g["net"]))
    out.append(block("Net P/L by side", "Long baskets against short baskets.", fig, fmt(g, "Side"), "attr_side"))

    # hour of entry (UTC)
    bb = b.assign(hour=b["open_time"].dt.hour, weekday=b["open_time"].dt.dayofweek)
    g = bb.groupby("hour").agg(baskets=("pnl", "size"), net=("pnl", "sum"),
                               win_rate=("pnl", lambda s: (s > 0).mean() * 100), avg=("pnl", "mean"),
                               worst=("pnl", "min")).reindex(range(24)).fillna(0).reset_index()
    fig = _bar([f"{h:02d}" for h in g["hour"]], g["net"], _pol(g["net"]), text=[""] * 24)
    fig.update_xaxes(title_text="Hour of entry, UTC")
    out.append(block("Net P/L by hour of entry", "UTC hour in which the basket was opened.", fig,
                     fmt(g.assign(hour=g["hour"].map(lambda h: f"{int(h):02d}:00")), "Hour (UTC)"), "attr_hour"))

    # weekday
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    g = bb.groupby("weekday").agg(baskets=("pnl", "size"), net=("pnl", "sum"),
                                  win_rate=("pnl", lambda s: (s > 0).mean() * 100), avg=("pnl", "mean"),
                                  worst=("pnl", "min")).reset_index()
    fig = _bar([names[int(d)] for d in g["weekday"]], g["net"], _pol(g["net"]))
    out.append(block("Net P/L by weekday of entry", "Day (UTC) on which the basket was opened.", fig,
                     fmt(g.assign(weekday=g["weekday"].map(lambda d: names[int(d)])), "Weekday"), "attr_wd"))

    # holding time
    edges = [0, 10, 60, 300, 900, 3600, 4 * 3600, 1e12]
    labels = ["<10s", "10-60s", "1-5m", "5-15m", "15-60m", "1-4h", ">4h"]
    bb["bucket"] = pd.cut(bb["duration_s"], edges, labels=labels, right=False)
    g = bb.groupby("bucket", observed=False).agg(baskets=("pnl", "size"), net=("pnl", "sum"),
                                                 win_rate=("pnl", lambda s: (s > 0).mean() * 100 if len(s) else 0),
                                                 avg=("pnl", "mean"), worst=("pnl", "min")).fillna(0).reset_index()
    fig = _bar(labels, g["net"], _pol(g["net"]))
    fig.update_xaxes(title_text="Time from first entry to close")
    out.append(block("Net P/L by holding time", "How long the basket was open.", fig, fmt(g, "Held for"), "attr_dur"))
    return out


# ───────────────────────────── risk shape ─────────────────────────────

def risk_blocks(res: Result) -> List[str]:
    b = res.baskets
    out: List[str] = []
    if len(b) == 0:
        return out

    # cumulative P/L by exit reason
    fig = go.Figure()
    bs = b.sort_values("close_time")
    reasons = [r for r in T.REASON_COLOR if r in set(bs["reason"])]
    for r in reasons:
        g = bs[bs["reason"] == r]
        fig.add_trace(go.Scatter(x=_naive(g["close_time"]), y=g["pnl"].cumsum(), mode="lines",
                                 name=T.REASON_LABEL.get(r, r).split(" (")[0],
                                 line=dict(color=T.REASON_COLOR[r], width=2, shape="hv"),
                                 hovertemplate="%{y:+,.2f}<extra>" + r.replace("_", " ") + "</extra>"))
    fig.add_trace(go.Scatter(x=_naive(bs["close_time"]), y=bs["pnl"].cumsum(), mode="lines", name="All baskets",
                             line=dict(color=T.INK, width=1.3, shape="hv"),
                             hovertemplate="%{y:+,.2f}<extra>all</extra>"))
    fig.update_layout(**T.plotly_layout(height=330, margin=dict(l=60, r=14, t=30, b=34)))
    fig.update_xaxes(**T.axis())
    fig.update_yaxes(**T.axis(title_text="Cumulative realised P/L, USD", zeroline=True, zerolinecolor=T.AXIS))
    out.append('<div class="card"><h3>Cumulative realised P/L by exit reason</h3>'
               '<p class="cap">Each line adds up only the baskets closed by that rule; the pale line is all of them.</p>'
               f'{_fig_html(fig, "risk_cum")}</div>')

    # the worst baskets against everything else
    pnl = np.sort(b["pnl"].to_numpy())
    k = min(25, len(pnl))
    worst = b.nsmallest(k, "pnl").sort_values("pnl")
    fig = go.Figure(go.Bar(
        x=[f"#{int(i)}" for i in worst["basket"]], y=worst["pnl"], marker=dict(color=T.DOWN, line=dict(width=0)),
        width=0.6, customdata=np.stack([worst["n_pos"], worst["lots"], worst["duration_s"]], axis=1),
        text=[r.replace("_", " ") for r in worst["reason"]],
        hovertemplate="basket %{x}<br><b>%{y:+,.2f}</b> · %{customdata[0]:.0f} pos · %{customdata[1]:.2f} lot"
                      "<br>held %{customdata[2]:,.0f}s · %{text}<extra></extra>", textposition="none"))
    fig.update_layout(**T.plotly_layout(height=330, margin=dict(l=60, r=14, t=22, b=44), showlegend=False,
                                        hovermode="closest", bargap=0.3))
    fig.update_xaxes(**T.axis(showgrid=False, type="category", tickangle=-60, tickfont=dict(size=9, color=T.INK_MUTED)))
    fig.update_yaxes(**T.axis(title_text="Basket P/L, USD", zeroline=True, zerolinecolor=T.AXIS))
    gross_win = float(pnl[pnl > 0].sum())
    worst_sum = float(worst["pnl"].clip(upper=0).sum())
    share = (-worst_sum / gross_win * 100) if gross_win > 0 else float("nan")
    out.append('<div class="card"><h3>The 25 worst baskets</h3>'
               f'<p class="cap">Together they lost {_money(worst_sum)} &mdash; '
               f'{_num(share, 0)}% of everything the winning baskets made ({_money(gross_win)}).</p>'
               f'{_fig_html(fig, "risk_worst")}</div>')

    # adverse excursion vs outcome (<= 3 identity colours on a scatter)
    fig = go.Figure()
    top = [r for r in b["reason"].value_counts().index[:3]]
    for r in top:
        g = b[b["reason"] == r]
        fig.add_trace(go.Scatter(
            x=g["mae"], y=g["pnl"], mode="markers", name=T.REASON_LABEL.get(r, r).split(" (")[0],
            marker=dict(color=T.REASON_COLOR.get(r, T.CONTEXT), size=7, opacity=0.75,
                        symbol=T.REASON_SYMBOL.get(r, "circle"), line=dict(color=T.SURFACE, width=1)),
            customdata=np.stack([g["basket"], g["n_pos"]], axis=1),
            hovertemplate="basket #%{customdata[0]:.0f} · %{customdata[1]:.0f} pos<br>worst floating %{x:+,.2f}"
                          "<br>closed <b>%{y:+,.2f}</b><extra></extra>"))
    fig.update_layout(**T.plotly_layout(height=330, margin=dict(l=60, r=14, t=30, b=44), hovermode="closest"))
    fig.update_xaxes(**T.axis(title_text="Worst floating P/L while open (MAE), USD", zeroline=True, zerolinecolor=T.AXIS))
    fig.update_yaxes(**T.axis(title_text="Closed P/L, USD", zeroline=True, zerolinecolor=T.AXIS))
    out.append('<div class="card"><h3>How far under water before the close</h3>'
               '<p class="cap">One mark per basket: its worst floating loss against where it finally closed.</p>'
               f'{_fig_html(fig, "risk_mae")}</div>')
    return out


# ───────────────────────────── basket close-ups ─────────────────────────────

def _observe_scores(cfg: BacktestConfig, start_ms: int, end_ms: int, store_dir) -> pd.DataFrame:
    """Per-second section scores over a short window (scores do not depend on positions)."""
    start_ms -= start_ms % 1000          # the per-second series is read on whole seconds
    end_ms += -end_ms % 1000
    c = cfg.replace(start=str(store.ms_to_dt(start_ms).tz_localize(None)),
                    end=str(store.ms_to_dt(end_ms).tz_localize(None)),
                    allow_long=False, allow_short=False, record_interval_s=1, window_enabled=False,
                    # pure observation on whole seconds: no order is ever sent, so no order timing applies
                    poll_interval_ms=1000, poll_jitter_ms=0, open_order_delay_ms=0, latency_ms=0)
    prep = prepare(c.symbol, c.start, c.end, c.timeframes(), mode="sec", store_dir=store_dir)
    return run(c, prep).equity


def closeup_figure(res: Result, basket_id: int, store_dir=store.DEFAULT_STORE_DIR, max_points: int = 2400) -> Optional[go.Figure]:
    cfg = res.cfg
    b = res.baskets[res.baskets["basket"] == basket_id]
    if len(b) == 0:
        return None
    b = b.iloc[0]
    f = res.fills[res.fills["basket"] == basket_id]
    t0, t1 = int(b["open_time"].value // 1_000_000), int(b["close_time"].value // 1_000_000)
    pad = int(min(max((t1 - t0) * 0.35, 180_000), 3_600_000))
    a_ms, z_ms = t0 - pad, t1 + pad
    sec = store.load_sec(cfg.symbol, a_ms, z_ms, store_dir)
    if not sec:
        return None
    px = pd.DataFrame({"t": pd.to_datetime(sec["t_ms"], unit="ms"), "bid": sec["bid"], "ask": sec["ask"]})
    stride = max(1, len(px) // max_points)
    if stride > 1:
        grp = px.groupby(np.arange(len(px)) // stride)
        px = pd.DataFrame({"t": grp["t"].last(), "bid": grp["bid"].last(), "ask": grp["ask"].last()})
    has_book = cfg.book_enabled
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])
    fig.add_trace(go.Scatter(x=px["t"], y=px["bid"], mode="lines", name="Bid",
                             line=dict(color=T.INK_2, width=1.3),
                             hovertemplate="bid %{y:,.2f}<extra></extra>"), row=1, col=1)
    side = b["side"]
    color = T.UP if side == "BUY" else T.DOWN
    sym = "triangle-up" if side == "BUY" else "triangle-down"
    ring = dict(color=T.SURFACE, width=1.5)
    o = f[f["action"] == "open"]
    fig.add_trace(go.Scatter(x=_naive(o["time"]), y=o["price"], mode="markers", name=f"Open {side}",
                             marker=dict(symbol=sym, size=12, color=color, line=ring),
                             hovertemplate="OPEN %{y:,.2f}<extra></extra>"), row=1, col=1)
    ad = f[f["action"] == "add"]
    if len(ad):
        fig.add_trace(go.Scatter(x=_naive(ad["time"]), y=ad["price"], mode="markers", name="Ladder add",
                                 marker=dict(symbol=sym + "-open", size=10, color=color, line=dict(color=color, width=1.8)),
                                 text=[f"{l:.2f}" for l in ad["lots"]],
                                 hovertemplate="ADD %{text} lot @ %{y:,.2f}<extra></extra>"), row=1, col=1)
    won = b["pnl"] > 0
    rs = T.REASON_SYMBOL.get(b["reason"], "circle")
    fig.add_trace(go.Scatter(x=[_naive(b["close_time"])], y=[b["close_price"]], mode="markers",
                             name=f"Close ({b['reason'].replace('_', ' ')})",
                             marker=dict(symbol=rs, size=12, color=T.UP if won else T.DOWN,
                                         line=dict(color=T.UP if won else T.DOWN, width=2.2) if rs == "x" else ring),
                             hovertemplate="CLOSE %{y:,.2f}<extra></extra>"), row=1, col=1)
    fig.add_shape(type="line", x0=_naive(b["open_time"]), x1=_naive(b["close_time"]), y0=b["avg_price"], y1=b["avg_price"],
                  line=dict(color=T.ACCENT, width=1), row=1, col=1)
    fig.add_annotation(x=_naive(b["close_time"]), y=b["avg_price"], text="avg entry", showarrow=False, xanchor="left",
                       xshift=6, font=dict(color=T.INK_MUTED, size=10), row=1, col=1)
    try:
        sc = _observe_scores(cfg, a_ms, z_ms, store_dir)
        if len(sc):
            st = max(1, len(sc) // max_points)
            sc = sc.iloc[::st]
            for col in ["open_score", "fc_score"] + (["book_score"] if has_book else []):
                fig.add_trace(go.Scatter(x=_naive(sc["time"]), y=sc[col], mode="lines", name=T.SCORE_LABEL[col],
                                         line=dict(color=T.SCORE_COLOR[col], width=1.4, shape="hv"),
                                         hovertemplate=T.SCORE_LABEL[col] + " %{y:+.0f}<extra></extra>"), row=2, col=1)
    except Exception:
        pass
    fig.update_layout(**T.plotly_layout(height=420, margin=dict(l=58, r=14, t=30, b=30), hovermode="x unified",
                                        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11, color=T.INK_2),
                                                    bgcolor="rgba(0,0,0,0)")))
    fig.update_xaxes(**T.axis(showticklabels=False), row=1, col=1)
    fig.update_xaxes(**T.axis(), row=2, col=1)
    fig.update_yaxes(**T.axis(title_text="Price"), row=1, col=1)
    fig.update_yaxes(**T.axis(title_text="Score", zeroline=True, zerolinecolor=T.AXIS, dtick=1), row=2, col=1)
    return fig


def closeup_blocks(res: Result, n_worst: int = 4, n_ladder: int = 2, n_typical: int = 2,
                   store_dir=store.DEFAULT_STORE_DIR) -> List[str]:
    b = res.baskets
    if len(b) == 0:
        return []
    picks: List[tuple] = []
    for _, r in b.nsmallest(n_worst, "pnl").iterrows():
        picks.append((int(r["basket"]), "One of the worst"))
    deep = b[(b["pnl"] > 0) & (b["n_pos"] >= 3)].nlargest(n_ladder, "n_pos")
    for _, r in deep.iterrows():
        picks.append((int(r["basket"]), "A ladder that worked"))
    typical = b[(b["pnl"] > 0) & (b["n_pos"] == 1)]
    if len(typical):
        med = typical["duration_s"].median()
        t2 = typical.iloc[(typical["duration_s"] - med).abs().argsort()[:n_typical]]
        for _, r in t2.iterrows():
            picks.append((int(r["basket"]), "A typical winner"))
    seen, out = set(), []
    for bid, why in picks:
        if bid in seen:
            continue
        seen.add(bid)
        fig = closeup_figure(res, bid, store_dir=store_dir)
        if fig is None:
            continue
        r = b[b["basket"] == bid].iloc[0]
        cap = (f"{why}: {r['side']} basket #{bid}, {int(r['n_pos'])} position{'s' if r['n_pos'] > 1 else ''}, "
               f"{r['lots']:.2f} lot, opened {r['open_time']:%d %b %H:%M:%S} UTC, held {_dur(r['duration_s'])}, "
               f"closed by {r['reason'].replace('_', ' ')} at <b>{_money(r['pnl'], signed=True)}</b> "
               f"(worst floating {_money(r['mae'], signed=True)}).")
        out.append(f'<div class="card"><p class="cap">{cap}</p>{_fig_html(fig, f"closeup_{bid}")}</div>')
    return out


# ───────────────────────────── tables ─────────────────────────────

def monthly_table(res: Result) -> pd.DataFrame:
    b = res.baskets
    if len(b) == 0:
        return pd.DataFrame()
    key = b["close_time"].dt.tz_convert(None).dt.to_period("M").astype(str)
    g = b.groupby(key).agg(baskets=("pnl", "size"), net=("pnl", "sum"),
                           win=("pnl", lambda s: (s > 0).mean() * 100),
                           avg_win=("pnl", lambda s: s[s > 0].mean() if (s > 0).any() else 0.0),
                           avg_loss=("pnl", lambda s: s[s < 0].mean() if (s < 0).any() else 0.0),
                           worst=("pnl", "min"), adds=("n_pos", lambda s: int((s - 1).sum()))).reset_index()
    g.columns = ["Month", "Baskets", "Net P/L", "Win %", "Avg win", "Avg loss", "Worst basket", "Ladder adds"]
    for c in ("Net P/L", "Avg win", "Avg loss", "Worst basket"):
        g[c] = g[c].map(lambda v: _money(v, signed=True))
    g["Win %"] = g["Win %"].map(lambda v: _num(v, 1))
    return g


def worst_table(res: Result, n: int = 15) -> pd.DataFrame:
    b = res.baskets
    if len(b) == 0:
        return pd.DataFrame()
    w = b.nsmallest(n, "pnl")
    return pd.DataFrame({
        "Basket": w["basket"].map(lambda i: f"#{int(i)}"),
        "Opened (UTC)": w["open_time"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "Side": w["side"], "Positions": w["n_pos"].astype(int), "Lots": w["lots"].map(lambda v: f"{v:.2f}"),
        "Held": w["duration_s"].map(_dur), "Exit": w["reason"].str.replace("_", " "),
        "Worst floating": w["mae"].map(lambda v: _money(v, signed=True)),
        "P/L": w["pnl"].map(lambda v: _money(v, signed=True)),
    })


def config_block(cfg: BacktestConfig) -> str:
    rows = [
        ("Symbol", cfg.symbol), ("Variant", cfg.variant),
        ("Window (UTC)", f"{cfg.start} → {cfg.end}"),
        ("Start balance / leverage", f"${cfg.initial_balance:,.0f} / 1:{cfg.effective_leverage:g}"),
        ("OPEN timeframes", cfg.describe_scores().split("] ")[0].replace("open[", "")),
        ("FORCE-CLOSE timeframes", cfg.describe_scores().split("fc[")[1].split("]")[0]),
    ]
    if cfg.book_enabled:
        rows.append(("BOOK timeframes", cfg.describe_scores().split("book[")[1].split("]")[0]))
    rows += [
        ("ENTRY_S / ENTRY_AGREE_S", f"{cfg.entry_s:g} / {cfg.entry_agree_s:g}"),
        ("FORCE_CLOSE_S / LADDER_S", f"{cfg.force_close_s:g} / {cfg.ladder_s:g}"),
        ("Profit exit", (f"book: profit > ${cfg.profit_protect_usd_per_unit:g} x unit and book score ≤ -{cfg.book_s:g}"
                         if cfg.book_enabled else f"target: profit > ${cfg.target_usd_per_unit:g} x unit")),
        ("RSI / MACD", f"RSI {cfg.rsi_length} · MACD {cfg.macd_fast},{cfg.macd_slow},{cfg.macd_signal}"),
        ("Pivot lookback / width / bands", f"{cfg.peak_lookback} / {cfg.pivot_width} / {cfg.rsi_peak_os:g}-{cfg.rsi_peak_ob:g}"),
        ("Ladder", f"{'+'.join(cfg.ladder_tfs[:cfg.n_ladder_adds]) or 'off'} at RSI {cfg.rsi_oversold:g}/{cfg.rsi_overbought:g}, "
                   f"lots x{','.join(f'{m:g}' for m in cfg.ladder_multipliers[:cfg.n_ladder_adds + 1])}"),
        ("Unit", (f"fixed {cfg.fixed_units}" if cfg.fixed_units else
                  f"floor(balance / {cfg.step_up_balance:,.0f}) + 1, max {cfg.unit_max_limit}") + f" · {cfg.mtqty:g} lot per unit"),
        ("Re-entry cooldown", f"{cfg.reentry_cooldown_s:g}s"),
        ("Poll / latency", f"{cfg.poll_interval_ms} ms / {cfg.latency_ms} ms"),
        ("Costs", f"recorded spread x{cfg.spread_mult:g}" + (f" + {cfg.extra_spread:g}" if cfg.extra_spread else "")
                  + (f", slippage {cfg.slippage:g}" if cfg.slippage else "") + f", commission ${cfg.commission_per_lot:g}/lot"),
    ]
    return '<div class="cfg">' + "".join(
        f"<div><span>{html.escape(k)}</span><span>{html.escape(str(v))}</span></div>" for k, v in rows) + "</div>"


# ───────────────────────────── the page ─────────────────────────────

def _tiles(s: dict, res: Result) -> str:
    net = s["net_profit"]
    t = []

    def tile(label, value, note="", cls=""):
        t.append(f'<div class="tile"><div class="label">{label}</div>'
                 f'<div class="value {cls}">{value}</div><div class="note">{note}</div></div>')

    tile("Max drawdown", _money(s["max_drawdown_usd"]), f'{_num(s["max_drawdown_pct"], 1)}% of the equity peak')
    tile("Win rate", f'{_num(s.get("win_rate_pct", float("nan")), 1)}%',
         f'needs {_num(s.get("breakeven_win_rate_pct", float("nan")), 1)}% to break even' if "breakeven_win_rate_pct" in s else "")
    tile("Profit factor", _num(s.get("profit_factor", float("nan")), 2), "gross profit / gross loss")
    tile("Baskets", f'{s["baskets"]:,}', f'{_num(s["baskets_per_day"], 1)} per day · {s["ladder_adds"]:,} ladder adds')
    tile("Average win", _money(s.get("avg_win", 0.0), signed=True), "per winning basket")
    tile("Average loss", _money(s.get("avg_loss", 0.0), signed=True),
         f'{_num(abs(s.get("avg_loss", 0.0)) / s["avg_win"], 1)}x the average win' if s.get("avg_win") else "")
    tile("Worst basket", _money(s.get("largest_loss", 0.0), signed=True),
         f'worst floating {_money(s["max_floating_loss"], signed=True)}')
    tile("Largest exposure", f'{_num(s["max_lots"], 2)} lot', f'{s["max_positions"]} positions · margin {_money(s["max_margin_used"])}')
    tile("Median hold", _dur(s.get("median_duration_s", float("nan"))),
         f'{_num(s.get("pct_baskets_under_60s", float("nan")), 0)}% closed inside 60s')
    if "daily_sharpe" in s:
        tile("Daily Sharpe (annualised)", _num(s["daily_sharpe"], 2), f'{_num(s.get("pct_days_positive", float("nan")), 0)}% of days positive')
    hero = (f'<div class="card big"><div class="label">Net result on ${s["initial_balance"]:,.0f}</div>'
            f'<div class="value {_sign_cls(net)}">{_money(net, signed=True)}</div>'
            f'<div class="note">{_num(s["return_pct"], 2)}% over {_num(s.get("ran_days", s["days"]), 0)} days · final equity '
            f'{_money(s["final_equity"])}'
            + (f' · <b>account stopped out on {str(s.get("stopped_out_at") or "")[:10]}</b>, day '
               f'{_num(s.get("ran_days", 0), 0)} of {_num(s["days"], 0)}; the run ends there' if s["stopped_out"] else '')
            + (f' · {_money(s["open_profit_at_end"], signed=True)} still open' if abs(s["open_profit_at_end"]) > 0.005 else '')
            + '</div></div>')
    return f'<div class="hero">{hero}<div class="tiles">{"".join(t)}</div></div>'


def _legend_key() -> str:
    def sw(color, shape="■"):
        return f'<span><span style="color:{color}">{shape}</span> '
    return ('<div class="key">'
            f'{sw(T.UP, "▲")}open long</span>{sw(T.DOWN, "▼")}open short</span>'
            f'{sw(T.INK_2, "△")}hollow triangle = ladder add</span>'
            f'{sw(T.INK_2, "●")}exit by target</span>{sw(T.INK_2, "◆")}exit by profit-book</span>'
            f'{sw(T.INK_2, "✕")}exit by force-close</span>{sw(T.INK_2, "★")}broker stop-out</span>'
            f'{sw(T.UP, "■")}exit colour = basket won</span>{sw(T.DOWN, "■")}basket lost</span>'
            '</div>')


# plots are created while the page is still being parsed, so the grid has not settled: refit them
_FIT_JS = """<script>
(function(){
  function fit(){ document.querySelectorAll('.plotly-graph-div').forEach(function(d){ try{ Plotly.Plots.resize(d); }catch(e){} }); }
  window.addEventListener('load', fit);
  if(window.ResizeObserver){
    var ro = new ResizeObserver(function(es){ es.forEach(function(e){
      var d = e.target.querySelector('.plotly-graph-div'); if(d){ try{ Plotly.Plots.resize(d); }catch(x){} } }); });
    document.querySelectorAll('.card').forEach(function(c){ ro.observe(c); });
  }
})();
</script>
"""


def build_report(res: Result, out_dir: Path, title: Optional[str] = None, subtitle: Optional[str] = None,
                 notes_html: str = "", closeups: bool = True, plotly_src: str = "../assets/" + PLOTLY_JS,
                 store_dir: Path = store.DEFAULT_STORE_DIR, tfs: Sequence[str] = ("M15", "H1", "H4")) -> Path:
    """Write report.html + the data tables into ``out_dir`` and return the HTML path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = res.cfg
    s = res.summary()

    # raw tables
    # one timestamp format everywhere (UTC), so the CSVs load cleanly in pandas / Excel
    fmt = "%Y-%m-%d %H:%M:%S.%f"
    res.baskets.to_csv(out_dir / "baskets.csv", index=False, date_format=fmt)
    res.fills.to_csv(out_dir / "fills.csv", index=False, date_format=fmt)
    if len(res.equity):
        # each row is the state at the END of its five minutes (stamped with that end time)
        eq5 = (res.equity.set_index("time").resample("5min", label="right", closed="right").last()
               .dropna(how="all").reset_index())
        eq5.to_csv(out_dir / "equity.csv.gz", index=False, compression="gzip", date_format=fmt)
    (out_dir / "summary.json").write_text(json.dumps(
        {"summary": s, "counters": res.counters, "scalars": res.scalars, "config": cfg.to_dict(),
         "engine": {"mode": res.mode, "runtime_s": round(res.runtime_s, 3), "warm_bars": res.warm_bars}},
        indent=2, default=str), encoding="utf-8")
    from ..analysis import diagnostics
    (out_dir / "diagnostics.json").write_text(json.dumps(diagnostics.diagnose(res), indent=2, default=str), encoding="utf-8")
    found = diagnostics.findings(res)
    diag_html = ""
    if found:
        items = "".join(f'<div class="finding"><div class="n">{i + 1}</div><div class="t">{html.escape(x["title"])}</div>'
                        f'<div class="d">{html.escape(x["detail"])}</div></div>' for i, x in enumerate(found))
        diag_html = ('<h2>What this run shows about the strategy</h2><p class="lede">Measured on this run\'s own baskets and '
                     'fills; the numbers are in <a href="diagnostics.json">diagnostics.json</a>.</p>'
                     f'<div class="card">{items}</div>')

    m1 = store.load_m1(cfg.symbol, cfg.start, cfg.end, store_dir)
    if m1:
        js = (_RESCALE_JS
              .replace("__START__", pd.Timestamp(int(m1["t"][0]), unit="s").strftime("%Y-%m-%d %H:%M:%S"))
              .replace("__END__", pd.Timestamp(int(m1["t"][-1]) + 60, unit="s").strftime("%Y-%m-%d %H:%M:%S")))
        market = market_controls(tfs) + '<div class="card flush">' + _fig_html(
            market_figure(res, m1, tfs=tfs), "market", post_script=js) + "</div>"
    else:
        market = ""
    attr = attribution_blocks(res)
    risk = risk_blocks(res)
    close = closeup_blocks(res, store_dir=store_dir) if closeups else []
    mt, wt = monthly_table(res), worst_table(res)

    title = title or f"{cfg.symbol} · {cfg.variant} · backtest"
    subtitle = subtitle or (f"{cfg.start} → {cfg.end} UTC · {cfg.describe_scores()} · "
                            f"Exness tick history, {res.mode}-level replay, {int(res.scalars.get('rows', 0)):,} rows")
    ct = res.counters
    flat = max(ct["polls_flat"], 1)
    funnel = (f'While flat the bot polled {ct["polls_flat"]:,} times: the open score wanted a trade but the force-close '
              f'score vetoed it on {ct["polls_entry_blocked_chop"] / flat * 100:.1f}% of those polls, the re-entry cooldown '
              f'blocked a ready signal on {ct["polls_entry_blocked_cooldown"] / flat * 100:.1f}%, and the trading window on '
              f'{ct["polls_entry_blocked_window"] / flat * 100:.1f}%. A ladder tier hit its RSI level but was held back by the '
              f'open-score gate on {ct["polls_ladder_blocked_gate"]:,} polls; {ct["polls_ladder_exhausted"]:,} polls were spent '
              f'holding a full ladder.')

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{T.CSS}</style>
<script src="{html.escape(plotly_src)}"></script>
</head><body><div class="wrap">
<header class="top"><div><div class="brand">Alcadeias · backtest</div><h1>{html.escape(title)}</h1>
<div class="sub">{html.escape(subtitle)}</div></div></header>
{_tiles(s, res)}
{notes_html}
{diag_html}
<h2>Market, trades and account</h2>
<p class="lede">Every fill is drawn at the price it filled at. Drag to pan, scroll to zoom, use the buttons for the candle
timeframe and the visible span; the lower panels share the time axis.</p>
{_legend_key()}
{market}
<h2>Where the money came from, and where it went</h2>
<p class="lede">{funnel}</p>
<div class="grid2">{''.join(attr)}</div>
<h2>The shape of the risk</h2>
<div class="grid2">{''.join(risk)}</div>
{('<h2>Close-ups: single baskets, second by second</h2><p class="lede">The bid, the fills and the section scores the bot was reading while each of these baskets was open. The gold line is the lot-weighted average entry.</p><div class="grid2">' + ''.join(close) + '</div>') if close else ''}
<h2>Month by month</h2>
<div class="card"><div class="scroll">{_table(mt, left_cols=["Month"]) if len(mt) else ''}</div></div>
<h2>Worst baskets</h2>
<div class="card"><div class="scroll">{_table(wt, left_cols=["Basket", "Opened (UTC)", "Side", "Exit"]) if len(wt) else ''}</div></div>
<h2>Configuration</h2>
<div class="card">{config_block(cfg)}</div>
<div class="foot">Raw tables next to this file: <a href="baskets.csv">baskets.csv</a> · <a href="fills.csv">fills.csv</a> ·
<a href="equity.csv.gz">equity.csv.gz</a> (5-minute samples) · <a href="summary.json">summary.json</a>. A basket is one fresh entry plus its ladder
adds, closed together. Times are UTC (Exness server time). Past results on historical ticks are not a forecast.</div>
</div>
{_FIT_JS}</body></html>"""
    path = out_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path


def ensure_plotly_js(assets_dir: Path) -> Path:
    """Copy the plotly bundle shipped with the installed package next to the reports (offline viewing)."""
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    dst = assets_dir / PLOTLY_JS
    if not dst.exists():
        from plotly.offline import get_plotlyjs
        dst.write_text(get_plotlyjs(), encoding="utf-8")
    return dst
