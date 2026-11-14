"""The owner's modification of the live hedging logic, and its parts, on raw ticks: eight loop timings per quarter, a real
$2,000 with the bot's unit rule, on DEV, CONFIRM and 2023. usage: user_rules.py SYMBOL [jobs]"""
import sys, time
SCR = "<working copy>"
sys.path.insert(0, f"{SCR}/devclone"); sys.path.insert(0, f"{SCR}/improve")
import pandas as pd
from backtesting import experiments as E
from backtesting.analysis import robustness
from final_exam import PERIODS

BLOCK = dict(entry_rsi_block_tfs=["H1", "H4"], entry_rsi_block_mode="directional")
RSI_FC = dict(fc_rsi_tfs=["H1", "H4"])
FC_H1 = dict(fc_weights={"H1": 1}, agree_weights={"M15": 1})          # force-close reads H1; the entry still needs M15 to agree

DESIGNS_FIRST = {
    "Live": {},
    "Yours, M15 force-close": {**BLOCK, **RSI_FC},
    "Yours, H1 force-close": {**BLOCK, **RSI_FC, **FC_H1},
    "Entry block only": dict(BLOCK),
    "RSI force-close only": dict(RSI_FC),
    "Yours (M15), entry block on either extreme": {**RSI_FC, "entry_rsi_block_tfs": ["H1", "H4"], "entry_rsi_block_mode": "any"},
    "Yours (M15) + at most 3 adds": {**BLOCK, **RSI_FC, "max_adds": 3},
    "Yours (M15) + basket stop $40 per unit": {**BLOCK, **RSI_FC, "stop_loss_usd_per_unit": 40.0},
}

ANY = dict(entry_rsi_block_tfs=["H1", "H4"], entry_rsi_block_mode="any")
DESIGNS = {
    "Literal rules, H1 force-close": {**ANY, **RSI_FC, **FC_H1},
    "Literal entry block only": dict(ANY),
    "Literal rules (M15) + at most 3 adds": {**ANY, **RSI_FC, "max_adds": 3},
}

if __name__ == "__main__":
    sym = sys.argv[1]; jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    out = []
    for per, wins in PERIODS.items():
        t0 = time.time()
        df = robustness.timing_ensemble(E.live_config(sym), wins, n_jobs=jobs, overrides=list(DESIGNS.values()),
                                        override_labels=[dict(design=n) for n in DESIGNS])
        df["period"] = per
        out.append(df)
        print(f"{sym} {per}: {len(df)} raw-tick quarter-runs in {time.time() - t0:.0f}s", flush=True)
        pd.concat(out, ignore_index=True).to_csv(f"{SCR}/improve/user_rules2_{sym}.csv", index=False)
    print("USER RULES2 DONE", flush=True)
