"""Summary of the owner's rules against the live settings. usage: sum_user.py SYMBOL"""
import sys, numpy as np, pandas as pd
SCR = "<working copy>"
sym = sys.argv[1]
d = pd.read_csv(f"{SCR}/improve/user_rules_{sym}.csv")
order = list(dict.fromkeys(d["design"]))
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 46)
print(f"## {sym}: real $2,000 per quarter, bot's unit rule, raw ticks, 8 loop timings per quarter")
for per in ["DEV", "CONFIRM", "FINAL", "ALL"]:
    x = d if per == "ALL" else d[d["period"] == per]
    if not len(x):
        continue
    rows = []
    for name in order:
        g = x[x["design"] == name]
        rows.append({"design": name, "avg/quarter": g["net_profit"].mean(), "median run": g["net_profit"].median(),
                     "lost": f"{int((g['net_profit'] < 0).sum())}/{len(g)}", "wiped": int(g["stopped_out"].astype(bool).sum()),
                     "maxDD% med": g["max_dd_pct"].median(), "maxDD% worst": g["max_dd_pct"].max(), "worst basket": g["largest_loss"].min(),
                     "win %": g["win_rate_pct"].mean(), "avg win": g["avg_win"].mean(), "avg loss": g["avg_loss"].mean(), "baskets/q": g["baskets"].mean()})
    print(f"\n### {per}" + (" (all 15 quarters)" if per == "ALL" else ""))
    print(pd.DataFrame(rows).round(1).to_string(index=False))
