"""Summary of the top-3 validation. usage: sum_top3.py SYMBOL"""
import sys, pandas as pd
SCR = "<working copy>"
sym = sys.argv[1]
d = pd.concat([pd.read_csv(f"{SCR}/improve/top3_v4_{w}_{sym}.csv") for w in ("dev", "holdout")], ignore_index=True)
order = list(dict.fromkeys(d["design"]))
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 60)
rows = []
for name in order:
    g = d[d["design"] == name]
    r = {"design": name[:58]}
    for per in ("FINAL", "CONFIRM", "DEV", "HOLDOUT"):
        x = g[g["period"] == per]
        r[{"FINAL": "2023", "CONFIRM": "2024-25", "DEV": "2025-26", "HOLDOUT": "2021-22 (untouched)"}[per]] = round(x["net_profit"].mean())
    s = g[g["period"] != "HOLDOUT"]; h = g[g["period"] == "HOLDOUT"]
    r.update({"lost 23-26": f"{int((s['net_profit'] < 0).sum())}/{len(s)}", "lost 21-22": f"{int((h['net_profit'] < 0).sum())}/{len(h)}",
              "wiped": int(g["stopped_out"].astype(bool).sum()), "DD med %": round(g["max_dd_pct"].median()), "DD worst %": round(g["max_dd_pct"].max()),
              "worst basket": round(g["largest_loss"].min()), "baskets/q": round(g["baskets"].mean())})
    rows.append(r)
print(f"## {sym}: average per quarter on a fresh $2,000, the bot's unit rule, raw ticks, 8 loop timings per quarter")
print(pd.DataFrame(rows).to_string(index=False))
