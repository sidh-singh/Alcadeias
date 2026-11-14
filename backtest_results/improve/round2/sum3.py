"""Compact view of the ladder exploration. usage: sum3.py SYMBOL [tag]"""
import sys, numpy as np, pandas as pd
SCR = "<working copy>"
sym = sys.argv[1]; tag = sys.argv[2] if len(sys.argv) > 2 else "stage3"
d = pd.read_csv(f"{SCR}/improve/{tag}_{sym}.csv")
W = [w for w in ["HO1", "HO2", "OOS2", "OOS1", "IS"] if f"net_profit@{w}" in d.columns]
for w in W: d[w] = d[f"net_profit@{w}"]
d["mean/q"] = d[W].mean(axis=1); d["min q"] = d[W].min(axis=1); d["pos"] = (d[W] > 0).sum(axis=1)
d["wiped"] = sum(d[f"acct_wiped@{w}"].astype(bool).astype(int) for w in W)
d["dip"] = d[[f"acct_dip@{w}" for w in W]].max(axis=1); d["worst"] = d[[f"largest_loss@{w}" for w in W]].min(axis=1)
d["n/q"] = d[[f"baskets@{w}" for w in W]].mean(axis=1)
d["se"] = d[W].std(axis=1) / np.sqrt(len(W)); d["lcb"] = d["mean/q"] - d["se"]
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60); pd.set_option("display.max_rows", 200)
print(f"## {sym} {tag}: one fixed 0.01-lot unit, per-second, {len(W)} quarters; USD per quarter")
g = d.groupby("ladder").agg(mean_q=("mean/q", "mean"), best_q=("mean/q", "max"), lcb=("lcb", "mean"), min_q=("min q", "mean"), dip=("dip", "mean"), worst=("worst", "min"), n=("n/q", "mean"), wiped=("wiped", "sum")).round(0)
print("by ladder (averaged over the exit sizes):"); print(g.sort_values("mean_q", ascending=False).to_string())
e = d.groupby("exit").agg(mean_q=("mean/q", "mean"), lcb=("lcb", "mean"), dip=("dip", "mean"), n=("n/q", "mean")).round(0)
print("by exit (averaged over the ladders):"); print(e.sort_values("mean_q", ascending=False).to_string())
print("top 12 by mean - 1 s.e.:"); print(d.sort_values("lcb", ascending=False).head(12)[["name"] + W + ["mean/q", "lcb", "pos", "dip", "worst", "n/q"]].round(0).to_string(index=False))
