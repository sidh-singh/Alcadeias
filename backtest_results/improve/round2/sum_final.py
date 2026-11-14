"""Summary of the final exam. usage: sum_final.py SYMBOL"""
import sys, numpy as np, pandas as pd
SCR = "<working copy>"
sym = sys.argv[1]
d = pd.read_csv(f"{SCR}/improve/final_exam_{sym}.csv")
dd = "max_drawdown_pct" if "max_drawdown_pct" in d.columns else "max_dd_pct"
order = ["Live", "V2", "V3", "V3 without the add", "V3-lite"]
pd.set_option("display.width", 250)
print(f"## {sym}: real $2,000 per quarter, bot's unit rule, raw ticks, 8 loop timings per quarter")
for per in ("DEV", "CONFIRM", "FINAL"):
    x = d[d["period"] == per]
    rows = []
    for name in order:
        g = x[x["design"] == name]
        if not len(g):
            continue
        med = g.groupby("window")["net_profit"].median()
        rows.append({"design": name, "quarters": len(med), "avg per quarter": g["net_profit"].mean(),
                     "median quarter": med.median(), "quarters up (median run)": f"{int((med > 0).sum())}/{len(med)}",
                     "runs lost": f"{int((g['net_profit'] < 0).sum())}/{len(g)}", "stopped out": int(g["stopped_out"].astype(bool).sum()),
                     "max DD med %": g[dd].median(), "max DD worst %": g[dd].max(), "worst basket": g["largest_loss"].min(),
                     "baskets/q": g["baskets"].mean()})
    print(f"\n### {per}")
    print(pd.DataFrame(rows).round(0).to_string(index=False))
    a = x[x["design"] == "V3"].set_index(["window", "seed"])["net_profit"]
    b = x[x["design"] == "V3 without the add"].set_index(["window", "seed"])["net_profit"]
    if len(a) and len(b):
        diff = (a - b).groupby(level=0).mean()
        print(f"the add itself (V3 minus its twin), per quarter: mean {diff.mean():+.0f} ± {diff.std() / np.sqrt(len(diff)):.0f}, better in {(diff > 0).sum()}/{len(diff)} quarters")
