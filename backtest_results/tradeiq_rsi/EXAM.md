# TradeIQ's RSI replacements: the exam (PREREG 8)

The verdicts were computed by `python -B -m backtesting.research.tradeiq exam` on 2026-11-27 23:47:20+00:00 (UTC), after `FINALISTS.md` was frozen (sha256 `2cdad1fae3836ca82d51cf638934e5baceb568743358ca8df3b91f4fe961ce5e`). The code that computed them is the code FINALISTS.md records (git blob ids in `exam_info.csv`). Per 0.01 lot after Exness costs, over the hold-out: Gold (XAUUSDm) 2024-07-01 to 2026-11-26 (exclusive); BTC (BTCUSDm) 2024-07-01 to 2026-11-27 (exclusive), one continuous run per finalist that starts flat at its first bar.

**The rule (PREREG 8, DEVIATIONS 33): a finalist passes when its hold-out net profit is above 0 at x1.0 costs and its profit / max drawdown is at least 0.5.** x1.5 is reported for information.

## The verdicts

| Symbol | Finalist | Rank | Net x1.0 | Net x1.5 | Max DD | Profit / DD | Trades | Win rate | Profit factor | Positive quarters | Time in market | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | `1H|QQE|R2|F2-4H|S0` | 1 | +1,552 | +1,530 | 626 | 2.48 | 233 | 40% | 1.50 | 7/10 | 37% | **PASS** |
| Gold (XAUUSDm) | `1H|LaRSI|R2|F1|S0` | 2 | +1,967 | +1,945 | 898 | 2.19 | 219 | 31% | 1.75 | 7/10 | 43% | **PASS** |
| Gold (XAUUSDm) | `4H|RSI|R2|F1|S0` | 4 | +1,479 | +1,466 | 1,233 | 1.20 | 144 | 32% | 1.65 | 7/10 | 47% | **PASS** |
| BTC (BTCUSDm) | `1D|LaRSI|R2|F3|S1` | 1 | +114 | +112 | 397 | 0.29 | 20 | 25% | 1.21 | 4/10 | 41% | **FAIL** |
| BTC (BTCUSDm) | `1D|VWRSI|R3|F0|S1` | 3 | -109 | -113 | 377 | -0.29 | 39 | 28% | 0.86 | 4/10 | 37% | **FAIL** |
| BTC (BTCUSDm) | `4H|TSI|R2|F1|S0` | 11 | +252 | +242 | 248 | 1.02 | 103 | 26% | 1.30 | 5/10 | 36% | **PASS** |

Gold (XAUUSDm): 3 of 3 finalists pass.
BTC (BTCUSDm): 1 of 3 finalists pass.

## Against buy-and-hold of the same span (DEVIATIONS 28)

Both markets rose over Development and Validation, and a long-only finalist can pass the rule by holding a rising market. So a pass counts as evidence of an edge over holding the market only if the finalist's hold-out profit / max drawdown is also above buy-and-hold's. "Exposure-matched" = the finalist's time in the market x buy-and-hold's net.

| Symbol | Finalist | Net | Max DD | Profit / DD | Shorts | Time in mkt | B&H net | B&H DD | B&H P/DD | B&H meets the rule | Exposure-matched B&H | P/DD above B&H | Net above exp.-matched | Pass AND P/DD above B&H |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | `1H|QQE|R2|F2-4H|S0` | +1,552 | 626 | 2.48 | 0 | 37% | +1,251 | 2,167 | 0.58 | yes | +468 | yes | yes | **yes** |
| Gold (XAUUSDm) | `1H|LaRSI|R2|F1|S0` | +1,967 | 898 | 2.19 | 0 | 43% | +1,251 | 2,167 | 0.58 | yes | +536 | yes | yes | **yes** |
| Gold (XAUUSDm) | `4H|RSI|R2|F1|S0` | +1,479 | 1,233 | 1.20 | 0 | 47% | +1,251 | 2,167 | 0.58 | yes | +586 | yes | yes | **yes** |
| BTC (BTCUSDm) | `1D|LaRSI|R2|F3|S1` | +114 | 397 | 0.29 | 0 | 41% | -23 | 711 | -0.03 | no | -9.35 | yes | yes | no |
| BTC (BTCUSDm) | `1D|VWRSI|R3|F0|S1` | -109 | 377 | -0.29 | 20 | 37% | -23 | 711 | -0.03 | no | -8.31 | no | no | no |
| BTC (BTCUSDm) | `4H|TSI|R2|F1|S0` | +252 | 248 | 1.02 | 0 | 36% | -23 | 711 | -0.03 | no | -8.21 | yes | yes | **yes** |

In words:

- Gold (XAUUSDm) `1H|QQE|R2|F2-4H|S0` passes: net +1,552 (x1.5: +1,530), max drawdown $626, profit / DD 2.48; and its profit / DD is above buy-and-hold's (0.58): evidence of an edge over holding the market.
- Gold (XAUUSDm) `1H|LaRSI|R2|F1|S0` passes: net +1,967 (x1.5: +1,945), max drawdown $898, profit / DD 2.19; and its profit / DD is above buy-and-hold's (0.58): evidence of an edge over holding the market.
- Gold (XAUUSDm) `4H|RSI|R2|F1|S0` passes: net +1,479 (x1.5: +1,466), max drawdown $1,233, profit / DD 1.20; and its profit / DD is above buy-and-hold's (0.58): evidence of an edge over holding the market.
- BTC (BTCUSDm) `1D|LaRSI|R2|F3|S1` fails: net +114 (x1.5: +112), max drawdown $397, profit / DD 0.29; Buy-and-hold of the same span: net -23, profit / DD -0.03.
- BTC (BTCUSDm) `1D|VWRSI|R3|F0|S1` fails: net -109 (x1.5: -113), max drawdown $377, profit / DD -0.29; Buy-and-hold of the same span: net -23, profit / DD -0.03.
- BTC (BTCUSDm) `4H|TSI|R2|F1|S0` passes: net +252 (x1.5: +242), max drawdown $248, profit / DD 1.02; and its profit / DD is above buy-and-hold's (-0.03): evidence of an edge over holding the market.

## For information: every variant over the hold-out (DEVIATIONS 28, 30, 34)

Computed after the verdicts above by `python -B -m backtesting.research.tradeiq holdout` (`results_holdout.csv`; `results_full.csv` holds every variant over 2019-01-01 to the data end). None of it changes a verdict.

Checks (`holdout_checks.csv`):

| Check | Result |
|---|---|
| dev, val and devval rerun on the data to the data end equal results_dev_val.csv byte for byte | True |
| the finalists' rows of results_holdout.csv equal exam.csv | True |
| the code is the code FINALISTS.md records | True |
| lines without a value on the bars the windows read, 2019 to the data end | 0 |
| exact ties with a level on those bars (a tie is the flat state, DEVIATIONS 19) | 0 |

PREREG 8's rule (net > 0 at x1.0 and profit / DD >= 0.5) over the hold-out and over the full span, by kind of row (R2 = long only, MA200 alone's included):

| Symbol | Window | R2 rows (long only) | Other rows | Qualifiers | All rows | Buy-and-hold |
|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | Hold-out | 124/126 (98%) | 178/210 (85%) | 42/44 (95%) | 302/336 (90%) | yes |
| Gold (XAUUSDm) | Full span | 126/126 (100%) | 178/210 (85%) | 43/44 (98%) | 304/336 (90%) | yes |
| BTC (BTCUSDm) | Hold-out | 32/150 (21%) | 91/264 (34%) | 41/59 (69%) | 123/414 (30%) | no |
| BTC (BTCUSDm) | Full span | 88/150 (59%) | 104/264 (39%) | 55/59 (93%) | 192/414 (46%) | yes |

Hold-out net at x1.0, every variant and the qualifiers (a variant chosen by its hold-out result would be chosen on the exam's data, so none is named here; every row is in `results_holdout.csv`):

| Symbol | Variants | Net > 0 | Median net | Qualifiers | Qualifiers net > 0 | Qualifiers median net | Highest net |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | 336 | 313 | +1,609 | 44 | 43 | +1,799 | +3,183 |
| BTC (BTCUSDm) | 414 | 229 | +58 | 59 | 47 | +243 | +666 |

Question 1 in the hold-out: each oscillator's variant against the RSI variant of the same row (DEVIATIONS 25; wins = strictly better):

| Symbol | Indicator | Pairs | Hold-out wins (net) | Hold-out wins (P/DD) | Full-span wins (net) | Full-span wins (P/DD) | Hold-out median trades / RSI's |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | LaRSI | 54 | 38 | 44 / 54 | 38 | 43 / 54 | 0.33 |
| Gold (XAUUSDm) | VWRSI | 54 | 47 | 49 / 54 | 52 | 53 / 54 | 0.78 |
| Gold (XAUUSDm) | TSI | 54 | 47 | 48 / 54 | 49 | 51 / 54 | 0.49 |
| Gold (XAUUSDm) | QQE | 48 | 22 | 30 / 48 | 21 | 36 / 48 | 0.51 |
| BTC (BTCUSDm) | LaRSI | 54 | 25 | 29 / 54 | 44 | 41 / 54 | 0.44 |
| BTC (BTCUSDm) | VWRSI | 54 | 18 | 19 / 54 | 20 | 18 / 54 | 0.87 |
| BTC (BTCUSDm) | TSI | 54 | 23 | 26 / 54 | 47 | 38 / 54 | 0.61 |
| BTC (BTCUSDm) | QQE | 48 | 19 | 19 / 48 | 30 | 34 / 48 | 0.50 |
| BTC (BTCUSDm) | VWRSI-RV | 54 | 28 | 27 / 54 | 40 | 33 / 54 | 0.71 |

Question 2 in the hold-out: each filtered variant against the same variant without a filter (DEVIATIONS 30; F1 / F2-4H / F2-1D = the MA200 filters, F3 = TSI > 0):

| Symbol | Filter | Pairs | Hold-out wins (net) | Hold-out wins (P/DD) | Full-span wins (net) | Full-span wins (P/DD) |
|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | F1 | 72 | 43 | 48 / 72 | 33 | 41 / 72 |
| Gold (XAUUSDm) | F2-4H | 24 | 13 | 15 / 24 | 15 | 17 / 24 |
| Gold (XAUUSDm) | F2-1D | 48 | 42 | 46 / 48 | 26 | 41 / 48 |
| Gold (XAUUSDm) | F3 | 60 | 40 | 38 / 60 | 48 | 44 / 60 |
| BTC (BTCUSDm) | F1 | 90 | 55 | 54 / 90 | 63 | 71 / 90 |
| BTC (BTCUSDm) | F2-4H | 30 | 29 | 29 / 30 | 30 | 30 / 30 |
| BTC (BTCUSDm) | F2-1D | 60 | 42 | 44 / 60 | 50 | 53 / 60 |
| BTC (BTCUSDm) | F3 | 78 | 48 | 48 / 78 | 58 | 58 / 78 |

## Files

`exam.csv` (the finalists' hold-out scores at x1.0 and `_x15` at x1.5, the verdict, buy-and-hold), `exam_trades.csv` (their hold-out trades at both costs), `exam_buy_and_hold.csv`, `exam_info.csv` (the data served, the code's blob ids, FINALISTS.md's sha256), `results_holdout.csv`, `results_full.csv`, `trades_holdout.csv.gz`, `buy_and_hold_exam.csv`, `state_checks_full.csv`, `holdout_checks.csv`, `vs_rsi_holdout_summary.csv`, `vs_f0_holdout_summary.csv`, `exam_rule_rates_holdout.csv`.
