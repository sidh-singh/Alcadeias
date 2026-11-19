import pandas as pd, numpy as np, json
V = "/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/port_tmp/ladder_verify"
L = "/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias/backtest_results/ladder"
NAMES = {"G1": "V3L|STOP=ST3|GRAN=T12|SIZING=Z1", "G5": "V3L|GRAN=T12|GATE=GT5|SIZING=Z3",
         "B1": "V3L|CONFIRM=C9|TIERS=T11|DEPTH=D3|SIZE=flat|TRIG-3RD=X-bb|SIZING=Z1", "L0": "L0"}
m = pd.read_csv(f"{V}/runs.csv")
m = m[m.err.isna()].copy()
m["net"] = m.final_equity - 2000.0
m["ret"] = m.net / 20.0
m["wiped"] = m.stopped_out.astype(bool) | (m.min_equity <= 200.0)
m["dname"] = m.design.map(NAMES)
rep = pd.concat([pd.read_csv(f) for f in [f"{L}/runs_XAUUSDm/R4_F{i}.csv" for i in range(1, 5)] +
                 [f"{L}/stress/gap_XAU.csv", f"{L}/stress/gap_BTC.csv", f"{L}/runs_XAUUSDm/cont_1y.csv", f"{L}/stress/cont_1y_BTC.csv",
                  "/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/port_tmp/ladder/btc/R4.csv"]], ignore_index=True)
rep = rep[rep["mode"] == "ticks"].drop_duplicates(["symbol", "design", "start", "end", "seed"])
j = m.merge(rep[["symbol", "design", "start", "end", "seed", "net", "max_dd_pct", "wiped", "baskets", "min_equity"]],
            left_on=["symbol", "dname", "start", "end", "seed"], right_on=["symbol", "design", "start", "end", "seed"],
            how="left", suffixes=("", "_rep"))
out = {"rowmatch": {}}
for (d, s), g in j.groupby(["design", "symbol"]):
    h = g.dropna(subset=["net_rep"])
    dn = (h.net - h.net_rep).abs()
    out["rowmatch"][f"{d} {s}"] = dict(rows=len(g), matched_rows=len(h), net_exact_cent=int((dn < 0.006).sum()),
                                       max_net_diff=round(float(dn.max()), 2) if len(h) else None,
                                       dd_exact=int(((h.max_dd_pct - h.max_dd_pct_rep).abs() < 0.0011).sum()),
                                       wiped_same=int((h.wiped == h.wiped_rep.astype(bool)).sum()),
                                       baskets_same=int((h.baskets == h.baskets_rep).sum()))
def months(y0, m0, n):
    return [f"{y0 + (m0 - 1 + i) // 12:04d}-{(m0 - 1 + i) % 12 + 1:02d}-13" for i in range(n)]
s85 = months(2018, 11, 85)
folds = {f"F{k+1}": months(y, 11, 12) for k, y in enumerate((2018, 2020, 2022, 2024))}
dsg = m.design_x if "design_x" in m else m.design
tab = {}
for (d, s), g in m.groupby(["design", "symbol"]):
    a = g[g.start.isin(s85) & g.seed.isin([1, 2])]
    t = dict(accounts=len(a), wiped=int(a.wiped.sum()), worst_dd=round(a.max_dd_pct.max(), 1), median_dd=round(a.max_dd_pct.median(), 1),
             mean=round(a.ret.mean(), 1), median=round(a.ret.median(), 1), p10=round(a.ret.quantile(0.1), 1), worst=round(a.ret.min(), 1),
             usd_wk_median=round(a.net.median() / 52), usd_wk_p10=round(a.net.quantile(0.1) / 52))
    allf = g[g.start.isin(sum(folds.values(), []))]
    t["fold_accounts"] = len(allf); t["wiped_of_384"] = int(allf.wiped.sum())
    tm = allf.groupby("seed").ret.mean()
    t["timing_mean_range"] = [round(tm.min(), 1), round(tm.max(), 1)]; t["timings_pos"] = int((tm > 0).sum())
    for f, st in folds.items():
        ff = g[g.start.isin(st)]
        t[f] = f"{ff.ret.mean():+.1f} / {int(ff.wiped.sum())} of {len(ff)}; worstDD {ff.max_dd_pct.max():.1f}"
    tab[f"{d} {s}"] = t
out["tables"] = tab
print(json.dumps(out, indent=1))
json.dump(out, open(f"{V}/summary.json", "w"), indent=1)
