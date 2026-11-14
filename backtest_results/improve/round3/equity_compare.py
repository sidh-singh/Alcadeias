"""One continuous $2,000 account per design (per-second replay, the bot's unit rule) on two long windows, both symbols;
writes an interactive HTML with the equity curves. usage: equity_compare.py OUT.html"""
import sys, json
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone"); sys.path.insert(0, f"{SCR}/improve")
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from backtesting import experiments as E
from backtesting.engine import fast
from user_rules import RSI_FC

ANY = dict(entry_rsi_block_tfs=["H1", "H4"], entry_rsi_block_mode="any")
DESIGNS = {"Your live logic": {}, "Your rules (literal), M15 force-close": {**ANY, **RSI_FC}}
WINDOWS = [("Jan 2024 – Jun 2025", "2024-01-01", "2025-07-01"), ("Aug 2025 – Nov 2026", "2025-08-13", "2026-11-13")]
COLORS = {"Your live logic": "#e0a400", "Your rules (literal), M15 force-close": "#3d8bfd"}
fig = make_subplots(rows=2, cols=2, subplot_titles=[f"{s} · {w[0]}" for s in ("XAUUSDm", "BTCUSDm") for w in WINDOWS],
                    vertical_spacing=0.12, horizontal_spacing=0.06)
summary = []
for r, sym in enumerate(("XAUUSDm", "BTCUSDm"), 1):
    for c, (wname, a, z) in enumerate(WINDOWS, 1):
        base = E.live_config(sym, start=a, end=z)
        tfs = sorted(set(base.timeframes()) | {"H1", "H4"}, key=lambda t: ["M1", "M5", "M15", "M30", "H1", "H4", "D1"].index(t))
        prep = fast.prepare(sym, a, z, tfs, mode="sec")
        for name, ov in DESIGNS.items():
            res = fast.run(base.replace(**ov), prep, light=False)
            e = res.equity.set_index("time")["equity"].resample("4h").last().dropna()
            fig.add_trace(go.Scatter(x=e.index, y=e.values, mode="lines", name=name, legendgroup=name, showlegend=(r == 1 and c == 1),
                                     line=dict(color=COLORS[name], width=1.4)), row=r, col=c)
            s = res.summary()
            summary.append(dict(symbol=sym, window=wname, design=name, net=round(s["net_profit"], 2), stopped_out=s["stopped_out"],
                                stopped_at=str(s.get("stopped_out_at") or ""), max_dd_pct=round(s["max_drawdown_pct"], 1), baskets=s["baskets"]))
            print(summary[-1], flush=True)
fig.update_layout(template="plotly_dark", height=900, width=1500, title="One continuous $2,000 account, the bot's unit rule (per-second replay)",
                  legend=dict(orientation="h", y=1.06))
fig.update_yaxes(title_text="equity, USD")
out = sys.argv[1]
fig.write_html(out, include_plotlyjs="../../assets/plotly.min.js")
pd.DataFrame(summary).to_csv(out.replace(".html", ".csv"), index=False)
print("wrote", out)
