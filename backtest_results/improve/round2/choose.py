"""Pick frozen designs from DEV + CONFIRM (11 quarters, fixed 0.01 lot, per-second), by a rule stated in advance:
largest sum over both symbols of (mean per quarter - 1 s.e.), never wiped, deepest dip under $500 on both symbols."""
import numpy as np, pandas as pd
SCR = "<working copy>"
def stats(tag, sym):
    a = pd.read_csv(f"{SCR}/improve/{tag}_{sym}.csv"); b = pd.read_csv(f"{SCR}/improve/{tag}_confirm_{sym}.csv")
    m = a.merge(b.drop(columns=["ladder", "exit"]), on="name", suffixes=("", "_c"))
    W = [c for c in m.columns if c.startswith("net_profit@")]
    net = m[W]
    o = pd.DataFrame({"name": m["name"], "family": m["ladder"], "exit": m["exit"]})
    o["mean"] = net.mean(axis=1); o["se"] = net.std(axis=1) / np.sqrt(len(W)); o["lcb"] = o["mean"] - o["se"]
    o["pos"] = (net > 0).sum(axis=1); o["worst_q"] = net.min(axis=1)
    o["dip"] = m[[c for c in m.columns if c.startswith("acct_dip@")]].max(axis=1)
    o["wiped"] = sum(m[c].astype(bool).astype(int) for c in m.columns if c.startswith("acct_wiped@"))
    o["n/q"] = m[[c for c in m.columns if c.startswith("baskets@")]].mean(axis=1)
    return o.set_index("name"), len(W)
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 70)
for tag, what in (("stage4", "entry frame, no ladder"), ("stage3", "ladder designs (H1 trend, live votes)")):
    g, nq = stats(tag, "XAUUSDm"); b, _ = stats(tag, "BTCUSDm")
    j = g.join(b, lsuffix="_xau", rsuffix="_btc")
    ok = (j["wiped_xau"] == 0) & (j["wiped_btc"] == 0) & (j["dip_xau"] < 500) & (j["dip_btc"] < 500)
    j["score"] = j["lcb_xau"] + j["lcb_btc"]
    cols = ["mean_xau", "lcb_xau", "pos_xau", "worst_q_xau", "dip_xau", "n/q_xau", "mean_btc", "lcb_btc", "pos_btc", "worst_q_btc", "dip_btc", "n/q_btc", "score"]
    print(f"\n## {what}: {nq} quarters per symbol (DEV + CONFIRM); USD per quarter, one fixed 0.01-lot unit; pos = positive quarters of {nq}")
    print(f"eligible (never wiped, dip < $500 on both): {int(ok.sum())} of {len(j)}")
    print(j[ok].sort_values("score", ascending=False).head(10)[cols].round(0).to_string())
    if tag == "stage3":
        lad = j[ok & (j["family_xau"] != "no ladder")]
        print("\nbest WITH a ladder:"); print(lad.sort_values("score", ascending=False).head(6)[cols].round(0).to_string())
        fam = j.groupby("family_xau")[["mean_xau", "lcb_xau", "mean_btc", "lcb_btc", "score"]].mean().round(0)
        print("\nby ladder family (averaged over exits):"); print(fam.sort_values("score", ascending=False).head(12).to_string())
