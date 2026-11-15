"""Continuous $2,000 accounts (per-second replay, the bot's unit rule) for the top-3 designs and references; writes an HTML chart.
usage: equity_top3.py OUT.html"""
import json, sys
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone")
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from backtesting import experiments as E
from backtesting.engine import fast
WINDOWS = [("2021 – 2022 (untouched)", "2021-01-01", "2023-01-01"), ("2023 – Nov 2026", "2023-01-01", "2026-11-13")]
PALETTE = ["#e0a400", "#9aa0a6", "#c678dd", "#3d8bfd", "#2ec27e", "#f66151"]
fig = make_subplots(rows=2, cols=2, subplot_titles=[f"{s} · {w[0]}" for s in ("XAUUSDm", "BTCUSDm") for w in WINDOWS], vertical_spacing=0.12, horizontal_spacing=0.06)
summary = []
for r, sym in enumerate(("XAUUSDm", "BTCUSDm"), 1):
    designs = json.load(open(f"{SCR}/improve/top3_v4_{sym}_designs.json"))
    for c, (wname, a, z) in enumerate(WINDOWS, 1):
        base = E.live_config(sym, start=a, end=z)
        tfs = sorted({"M1", "M5", "M15", "H1", "H4"} | set(base.timeframes()), key=lambda t: ["M1", "M5", "M15", "M30", "H1", "H4", "D1"].index(t))
        prep = fast.prepare(sym, a, z, tfs, mode="sec")
        for i, (name, ov) in enumerate(designs.items()):
            res = fast.run(base.replace(**ov), prep)
            e = res.equity.set_index("time")["equity"].resample("8h").last().dropna()
            fig.add_trace(go.Scatter(x=e.index, y=e.values, mode="lines", name=name[:60], legendgroup=f"{sym}{i}", showlegend=(c == 1),
                                     line=dict(color=PALETTE[i % len(PALETTE)], width=1.3)), row=r, col=c)
            s = res.summary()
            summary.append(dict(symbol=sym, window=wname, design=name, net=round(s["net_profit"], 2), max_dd_pct=round(s["max_drawdown_pct"], 1),
                                stopped_out=s["stopped_out"], stopped_at=str(s.get("stopped_out_at") or ""), baskets=s["baskets"]))
            print(summary[-1], flush=True)
fig.update_layout(template="plotly_dark", height=1000, width=1600, title="One continuous $2,000 account per design (per-second replay, the bot's unit rule)",
                  legend=dict(orientation="v", x=1.01, y=1, font=dict(size=10)))
fig.update_yaxes(title_text="equity, USD")
out = sys.argv[1]
fig.write_html(out, include_plotlyjs="../../assets/plotly.min.js")
pd.DataFrame(summary).to_csv(out.replace(".html", ".csv"), index=False)
print("wrote", out)
