"""A2, HOLDOUT quarter 2021-01-01: reproduce round 4 with the store as it was then (history from Jan 2021)."""
import sys, json, numpy as np, pandas as pd
from backtesting.data import store
from backtesting.engine import fast
from backtesting.research import ladder_engine as LE, ladder_checks as LC
from backtesting.config import BacktestConfig
from backtesting.analysis.robustness import live_timing
real_span = store.data_span
rows = []
for sym in ("XAUUSDm", "BTCUSDm"):
    first = store.load_sec(sym, "2021-01-01", "2021-01-08")["t_ms"][0]
    fast.store.data_span = lambda s, d=store.DEFAULT_STORE_DIR, f=first: (pd.Timestamp(int(f), unit="ms"), real_span(s, d)[1])
    a, z = "2021-01-01", "2021-04-01"
    cfg = LE.live_config(sym, start=a, end=z)
    prep = LE.prepare(sym, a, z, cfg.timeframes(), mode="ticks")
    fast.store.data_span = real_span
    tab = LC.anchor_table(sym)
    tab = tab[tab["segment"] == "2021-01-01 → 2021-04-01"].set_index("seed")
    for seed in range(1, 9):
        r_new = LE.run(cfg.replace(**live_timing(seed)), prep, light=True)
        r_old = fast.run(BacktestConfig.live(sym, start=a, end=z).replace(**live_timing(seed)), prep, light=True)
        net_n, net_o = round(r_new.scalars["final_equity"] - 2000, 2), round(r_old.scalars["final_equity"] - 2000, 2)
        csv = tab.loc[seed]
        rows.append(dict(symbol=sym, seed=seed, warm_bars=int(prep.nwarm["H4"]), csv_net=csv["acct_net"], new_net=net_n,
                         old_net=net_o, csv_baskets=int(csv["baskets"]), new_baskets=len(r_new.baskets),
                         match=bool(net_n == round(csv["acct_net"], 2) and len(r_new.baskets) == csv["baskets"] and net_o == net_n)))
d = pd.DataFrame(rows)
print(d.to_string())
d.to_csv("backtest_results/ladder/identity/anchor_184_holdout_q1_store_as_of_round4.csv", index=False)
