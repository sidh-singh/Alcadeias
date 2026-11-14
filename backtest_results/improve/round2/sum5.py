"""DEV against CONFIRM for the ladder grid (stage3) and the entry-frame grid (stage4). usage: sum5.py SYMBOL stage3|stage4"""
import sys, numpy as np, pandas as pd
SCR = "<working copy>"
sym, tag = sys.argv[1], sys.argv[2]
def load(path):
    d = pd.read_csv(path)
    W = [c.split("@")[1] for c in d.columns if c.startswith("net_profit@")]
    out = pd.DataFrame({"name": d["name"], "group": d["ladder"], "exit": d["exit"]})
    out["mean"] = d[[f"net_profit@{w}" for w in W]].mean(axis=1)
    out["se"] = d[[f"net_profit@{w}" for w in W]].std(axis=1) / np.sqrt(len(W))
    out["pos"] = (d[[f"net_profit@{w}" for w in W]] > 0).sum(axis=1)
    out["worst_q"] = d[[f"net_profit@{w}" for w in W]].min(axis=1)
    out["dip"] = d[[f"acct_dip@{w}" for w in W]].max(axis=1)
    out["wiped"] = sum(d[f"acct_wiped@{w}"].astype(bool).astype(int) for w in W)
    out["n"] = d[[f"baskets@{w}" for w in W]].mean(axis=1)
    return out.set_index("name"), len(W)
dev, nd = load(f"{SCR}/improve/{tag}_{sym}.csv")
con, nc = load(f"{SCR}/improve/{tag}_confirm_{sym}.csv")
m = dev.join(con, lsuffix="_dev", rsuffix="_con", how="inner")
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70); pd.set_option("display.max_rows", 200)
print(f"## {sym} {tag}: one fixed 0.01-lot unit, per-second; mean net per quarter, DEV ({nd} quarters, Aug 2025-Nov 2026) vs CONFIRM ({nc} quarters, Jan 2024-Jun 2025)")
if "LIVE" in con.index:
    L = con.loc["LIVE"]; print(f"LIVE settings on CONFIRM: mean {L['mean']:+.0f}/q, {int(L['pos'])}/{nc} quarters positive, worst quarter {L['worst_q']:+.0f}, account wiped in {int(L['wiped'])} quarters, {L['n']:.0f} baskets/q")
print(f"rank correlation of the {len(m)} settings, DEV vs CONFIRM: {m['mean_dev'].corr(m['mean_con'], method='spearman'):+.2f}")
g = m.groupby("group_dev").agg(dev=("mean_dev", "mean"), confirm=("mean_con", "mean"), con_pos=("pos_con", "mean"), con_worst=("worst_q_con", "min"),
                                con_dip=("dip_con", "max"), con_wiped=("wiped_con", "sum"), n=("n_con", "mean")).round(0)
print("\nby family (averaged over exits):"); print(g.sort_values("confirm", ascending=False).to_string())
e = m.groupby("exit_dev").agg(dev=("mean_dev", "mean"), confirm=("mean_con", "mean"), con_pos=("pos_con", "mean")).round(0)
print("\nby exit (averaged over families):"); print(e.sort_values("confirm", ascending=False).to_string())
m["lcb_dev"] = m["mean_dev"] - m["se_dev"]
top = m.sort_values("lcb_dev", ascending=False).head(15)
print(f"\nthe 15 best on DEV (by mean - 1 s.e.) and what they did on CONFIRM (pos = positive quarters of {nc}):")
print(top[["mean_dev", "lcb_dev", "pos_dev", "mean_con", "pos_con", "worst_q_con", "dip_con", "wiped_con", "n_con"]].round(0).to_string())
both = m[(m["mean_dev"] > 0) & (m["mean_con"] > 0)]
print(f"\npositive on both: {len(both)} of {len(m)}; positive in every quarter of both: {int(((m['pos_dev'] == nd) & (m['pos_con'] == nc)).sum())}")
