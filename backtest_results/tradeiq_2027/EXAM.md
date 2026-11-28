# TradeIQ's 9 indicators for 2027: the exam (PREREG 7)

Computed by `python -B -m backtesting.research.tradeiq2 exam` on 2026-11-28 15:00:43+00:00 (UTC), after `FINALISTS.md` was frozen (sha256 `106542cc04a27b4c34d77154d1e17ea7b1a5455b9f12ded2adee9ae36d4c53b0`). The result code is the code FINALISTS.md records. Per 0.01 lot after Exness costs, one continuous run per champion and window that starts flat at its first bar.

**The rule (PREREG 7): a champion passes an exam when its net profit there is above 0 at x1.0 and its profit / max drawdown is at least 0.5.** Exam 1 is the hold-out (2024-07-01 to the data end); a gold champion also takes exam 2 on the Early window (2017-01-01 to 2018-12-31). x1.5 is information. A champion whose Development or Validation rows change on the data to the data end gets the verdict 'void (look-ahead)'.

## The verdicts

| Symbol | Role | Family | Champion | Exam | Net x1.0 | Net x1.5 | Max DD | Profit / DD | Trades | Profit factor | Positive quarters | Result | B&H net | B&H P/DD | B&H exposure-matched | Verdict | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | finalist | RIB | `1H|RIB|LO|X0|F2-4H` | holdout | +2,264 | +2,250 | 498 | 4.55 | 144 | 2.18 | 7/10 | **PASS** | +1,251 | 0.58 | +411 | passes the hold-out only |  |
| Gold (XAUUSDm) | finalist | RIB | `1H|RIB|LO|X0|F2-4H` | early | +7.32 | -8.32 | 102 | 0.07 | 103 | 1.02 | 5/8 | **FAIL** | +132 | 0.64 | +31 | passes the hold-out only |  |
| Gold (XAUUSDm) | finalist | COIL | `1H|COIL|COIL-RIB|X-3R|VOL` | holdout | +463 | +457 | 551 | 0.84 | 57 | 1.40 | 7/10 | **PASS** | +1,251 | 0.58 | +141 | passes the hold-out only |  |
| Gold (XAUUSDm) | finalist | COIL | `1H|COIL|COIL-RIB|X-3R|VOL` | early | -36 | -71 | 81 | -0.45 | 40 | 0.73 | 2/8 | **FAIL** | +132 | 0.64 | +14 | passes the hold-out only |  |
| Gold (XAUUSDm) | finalist | STK | `1H|STK|STK-RA|LO|S1` | holdout | +2,259 | +2,242 | 709 | 3.19 | 180 | 1.91 | 8/10 | **PASS** | +1,251 | 0.58 | +495 | passes the hold-out only |  |
| Gold (XAUUSDm) | finalist | STK | `1H|STK|STK-RA|LO|S1` | early | +13 | -10 | 93 | 0.14 | 131 | 1.03 | 5/8 | **FAIL** | +132 | 0.64 | +40 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | HA-MANAGED | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | holdout | +853 | +837 | 874 | 0.98 | 144 | 1.39 | 6/10 | **PASS** | +1,251 | 0.58 | +397 | passes both |  |
| Gold (XAUUSDm) | champion | HA-MANAGED | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | early | +75 | +59 | 65 | 1.15 | 98 | 1.29 | 4/8 | **PASS** | +132 | 0.64 | +33 | passes both |  |
| Gold (XAUUSDm) | champion | SP | `4H|SP|W2|POC|LO` | holdout | +272 | +271 | 297 | 0.91 | 18 | 1.55 | 5/10 | **PASS** | +1,251 | 0.58 | +105 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | SP | `4H|SP|W2|POC|LO` | early | -51 | -54 | 101 | -0.51 | 14 | 0.47 | 2/8 | **FAIL** | +132 | 0.64 | +12 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | MSD-FILTER | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | holdout | +1,645 | +1,613 | 731 | 2.25 | 323 | 1.34 | 7/10 | **PASS** | +1,251 | 0.58 | +655 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | MSD-FILTER | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | early | +15 | -27 | 146 | 0.10 | 325 | 1.02 | 5/8 | **FAIL** | +132 | 0.64 | +60 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | HA-ENTRY | `1D|HA-ENTRY|HA-H2|LO|F0` | holdout | +943 | +935 | 1,823 | 0.52 | 73 | 1.47 | 7/10 | **PASS** | +1,251 | 0.58 | +678 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | HA-ENTRY | `1D|HA-ENTRY|HA-H2|LO|F0` | early | +39 | +31 | 193 | 0.20 | 60 | 1.13 | 5/8 | **FAIL** | +132 | 0.64 | +65 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | ALMA-X | `4H|ALMA-X|LO|X0|F0` | holdout | +1,397 | +1,372 | 1,424 | 0.98 | 248 | 1.34 | 8/10 | **PASS** | +1,251 | 0.58 | +692 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | ALMA-X | `4H|ALMA-X|LO|X0|F0` | early | -9.21 | -40 | 134 | -0.07 | 218 | 0.98 | 4/8 | **FAIL** | +132 | 0.64 | +66 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | WY-DERIVED | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | holdout | +49 | +38 | 582 | 0.09 | 125 | 1.02 | 4/10 | **FAIL** | +1,251 | 0.58 | +200 | fails |  |
| Gold (XAUUSDm) | champion | WY-DERIVED | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | early | -42 | -57 | 61 | -0.69 | 46 | 0.74 | 3/8 | **FAIL** | +132 | 0.64 | +9.98 | fails |  |
| Gold (XAUUSDm) | champion | ORB | `M5|ORB|O3|HV+F2-4H` | holdout | -14 | -35 | 262 | -0.05 | 199 | 0.99 | 5/10 | **FAIL** | +1,251 | 0.58 | +63 | fails |  |
| Gold (XAUUSDm) | champion | ORB | `M5|ORB|O3|HV+F2-4H` | early | -87 | -130 | 97 | -0.90 | 246 | 0.76 | 1/8 | **FAIL** | +132 | 0.64 | +9.15 | fails |  |
| Gold (XAUUSDm) | champion | MSD-ALONE | `1H|MSD-ALONE|MSD-A2|S0` | holdout | +2,203 | +2,167 | 1,191 | 1.85 | 333 | 1.85 | 8/10 | **PASS** | +1,251 | 0.58 | +849 | passes the hold-out only |  |
| Gold (XAUUSDm) | champion | MSD-ALONE | `1H|MSD-ALONE|MSD-A2|S0` | early | -72 | -105 | 167 | -0.43 | 257 | 0.81 | 3/8 | **FAIL** | +132 | 0.64 | +20 | passes the hold-out only |  |
| BTC (BTCUSDm) | finalist | HA-MANAGED | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | holdout | +114 | +112 | 397 | 0.29 | 20 | 1.21 | 4/10 | **FAIL** | -23 | -0.03 | -9.35 | fail |  |
| BTC (BTCUSDm) | finalist | MSD-FILTER | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | holdout | +367 | +361 | 358 | 1.03 | 51 | 1.31 | 5/10 | **PASS** | -23 | -0.03 | -20 | pass |  |
| BTC (BTCUSDm) | finalist | COIL | `1D|COIL|COIL-RIB|X-3R|none` | holdout | +166 | +165 | 319 | 0.52 | 11 | 1.44 | 6/10 | **PASS** | -23 | -0.03 | -9.29 | pass |  |
| BTC (BTCUSDm) | champion | BOS | `4H|BOS|BOS-trend|LO|F1|S1` | holdout | +372 | +366 | 231 | 1.61 | 65 | 1.58 | 7/10 | **PASS** | -23 | -0.03 | -8.21 | pass |  |
| BTC (BTCUSDm) | champion | SP | `4H|SP|W2|POC|F2-1D` | holdout | -57 | -59 | 217 | -0.26 | 27 | 0.87 | 4/10 | **FAIL** | -23 | -0.03 | -2.40 | fail |  |
| BTC (BTCUSDm) | champion | RIB | `4H|RIB|LS|XBE|F1` | holdout | +434 | +425 | 243 | 1.78 | 95 | 1.39 | 6/10 | **PASS** | -23 | -0.03 | -11 | pass |  |

- Gold (XAUUSDm): 11 champions; passes the hold-out only: 8, fails: 2, passes both: 1.
- BTC (BTCUSDm): 6 champions; pass: 4, fail: 2.

A pass counts as evidence of an edge over holding the market only if the champion's profit / max drawdown is also above buy-and-hold's over the same span (study 1's DEVIATIONS 28; `edge_over_bh` in `exam.csv`); the exposure-matched buy-and-hold is the champion's time in the market x buy-and-hold's net (`net_above_exposure_matched`).

## The base rate (PREREG 7, information)

The same exam computed for every variant after the verdicts: the share of each set that passes ('all rows' = every variant of the symbol, the share PREREG 7 asks for).

| Symbol | Window | Rows | Pass | Share |
|---|---|---|---|---|
| Gold (XAUUSDm) | holdout | all rows | 488/775 | 63% |
| Gold (XAUUSDm) | holdout | all eligible rows | 477/738 | 65% |
| Gold (XAUUSDm) | holdout | qualifiers | 60/65 | 92% |
| Gold (XAUUSDm) | holdout | champions | 9/11 | 82% |
| Gold (XAUUSDm) | holdout | finalists | 3/3 | 100% |
| Gold (XAUUSDm) | holdout | not-eligible and information rows | 11/37 | 30% |
| Gold (XAUUSDm) | holdout | buy-and-hold | 1/1 | 100% |
| Gold (XAUUSDm) | early | all rows | 103/775 | 13% |
| Gold (XAUUSDm) | early | all eligible rows | 91/738 | 12% |
| Gold (XAUUSDm) | early | qualifiers | 13/65 | 20% |
| Gold (XAUUSDm) | early | champions | 1/11 | 9% |
| Gold (XAUUSDm) | early | finalists | 0/3 | 0% |
| Gold (XAUUSDm) | early | not-eligible and information rows | 12/37 | 32% |
| Gold (XAUUSDm) | early | buy-and-hold | 1/1 | 100% |
| Gold (XAUUSDm) | both | all rows | 59/775 | 8% |
| Gold (XAUUSDm) | both | all eligible rows | 53/738 | 7% |
| Gold (XAUUSDm) | both | qualifiers | 12/65 | 18% |
| Gold (XAUUSDm) | both | champions | 1/11 | 9% |
| Gold (XAUUSDm) | both | finalists | 0/3 | 0% |
| Gold (XAUUSDm) | both | not-eligible and information rows | 6/37 | 16% |
| BTC (BTCUSDm) | holdout | all rows | 170/762 | 22% |
| BTC (BTCUSDm) | holdout | all eligible rows | 158/720 | 22% |
| BTC (BTCUSDm) | holdout | qualifiers | 10/36 | 28% |
| BTC (BTCUSDm) | holdout | champions | 4/6 | 67% |
| BTC (BTCUSDm) | holdout | finalists | 2/3 | 67% |
| BTC (BTCUSDm) | holdout | not-eligible and information rows | 12/42 | 29% |
| BTC (BTCUSDm) | holdout | buy-and-hold | 0/1 | 0% |
| Nasdaq (USTECm) | holdout | claim-check rows (information) | 4/4 | 100% |
| Nasdaq (USTECm) | holdout | buy-and-hold | 1/1 | 100% |
| EURUSD (EURUSDm) | holdout | claim-check rows (information) | 1/1 | 100% |
| EURUSD (EURUSDm) | holdout | buy-and-hold | 0/1 | 0% |
| GBPUSD (GBPUSDm) | holdout | claim-check rows (information) | 0/1 | 0% |
| GBPUSD (GBPUSDm) | holdout | buy-and-hold | 0/1 | 0% |

## Multiple testing (Development weekly P/L; PREREG 7)

| Universe | Symbol | Role | Variant | N | DSR | SPA p | Reality Check p |
|---|---|---|---|---|---|---|---|
| all variants run | Gold (XAUUSDm) | best dev Sharpe | `1H|HP-HARMONIC|HP-DRAWN|ALL|TP1|F0` | 775 | 1.000 | 0.000 | 0.000 |
| all variants run | Gold (XAUUSDm) | would-be finalist 1 (rank 1) | `1H|RIB|LO|X0|F2-4H` | 775 | 0.029 | 0.000 | 0.000 |
| all variants run | Gold (XAUUSDm) | would-be finalist 2 (rank 2) | `1H|COIL|COIL-RIB|X-3R|VOL` | 775 | 0.004 | 0.000 | 0.000 |
| all variants run | Gold (XAUUSDm) | would-be finalist 3 (rank 4) | `1H|STK|STK-RA|LO|S1` | 775 | 0.008 | 0.000 | 0.000 |
| all variants run | BTC (BTCUSDm) | best dev Sharpe | `1H|HP-HARMONIC|HP-DRAWN|ALL|TP1|F0` | 762 | 1.000 | 0.028 | 0.001 |
| all variants run | BTC (BTCUSDm) | would-be finalist 1 (rank 1) | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | 762 | 0.000 | 0.028 | 0.001 |
| all variants run | BTC (BTCUSDm) | would-be finalist 2 (rank 2) | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | 762 | 0.000 | 0.028 | 0.001 |
| all variants run | BTC (BTCUSDm) | would-be finalist 3 (rank 4) | `1D|COIL|COIL-RIB|X-3R|none` | 762 | 0.000 | 0.028 | 0.001 |
| eligible variants | Gold (XAUUSDm) | best dev Sharpe | `1H|RIB|LO|X0|F2-4H` | 738 | 0.172 | 0.396 | 0.489 |
| eligible variants | Gold (XAUUSDm) | would-be finalist 1 (rank 1) | `1H|RIB|LO|X0|F2-4H` | 738 | 0.172 | 0.396 | 0.489 |
| eligible variants | Gold (XAUUSDm) | would-be finalist 2 (rank 2) | `1H|COIL|COIL-RIB|X-3R|VOL` | 738 | 0.045 | 0.396 | 0.489 |
| eligible variants | Gold (XAUUSDm) | would-be finalist 3 (rank 4) | `1H|STK|STK-RA|LO|S1` | 738 | 0.066 | 0.396 | 0.489 |
| eligible variants | BTC (BTCUSDm) | best dev Sharpe | `1D|COIL|COIL-RIB|X-3R|ADX` | 720 | 0.001 | 0.638 | 0.389 |
| eligible variants | BTC (BTCUSDm) | would-be finalist 1 (rank 1) | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | 720 | 0.000 | 0.638 | 0.389 |
| eligible variants | BTC (BTCUSDm) | would-be finalist 2 (rank 2) | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | 720 | 0.001 | 0.638 | 0.389 |
| eligible variants | BTC (BTCUSDm) | would-be finalist 3 (rank 4) | `1D|COIL|COIL-RIB|X-3R|none` | 720 | 0.001 | 0.638 | 0.389 |

## Checks

| Check | Variant | Result | Differs |
|---|---|---|---|
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1H|RIB|LO|X0|F2-4H` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1H|COIL|COIL-RIB|X-3R|VOL` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1H|STK|STK-RA|LO|S1` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|4H|HA-MANAGED|M2|RSI-R2-F1-S0` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|4H|SP|W2|POC|LO` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1D|HA-ENTRY|HA-H2|LO|F0` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|4H|ALMA-X|LO|X0|F0` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|M5|ORB|O3|HV+F2-4H` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `XAUUSDm|1H|MSD-ALONE|MSD-A2|S0` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `BTCUSDm|1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `BTCUSDm|1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `BTCUSDm|1D|COIL|COIL-RIB|X-3R|none` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `BTCUSDm|4H|BOS|BOS-trend|LO|F1|S1` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `BTCUSDm|4H|SP|W2|POC|F2-1D` | True |  |
| D, V and D+V again on the data to the data end equal results_dev_val.csv's text | `BTCUSDm|4H|RIB|LS|XBE|F1` | True |  |
| the champions' rows of results_holdout.csv / results_early.csv equal exam.csv |  | True |  |
| every variant's D, V and D+V again on the data to the data end equal results_dev_val.csv's text (1523 variants; 20 that look ahead by design left out) |  | True |  |

## Files

`exam.csv` (the champions' exam rows at x1.0 and `_x15`, the result, buy-and-hold, the verdict), `exam_full.csv` (their full span), `exam_trades.csv.gz`, `exam_buy_and_hold.csv`, `exam_info.csv`, `exam_checks.csv`, `results_holdout.csv`, `results_early.csv`, `results_recheck_dev_val.csv`, `trades_holdout.csv.gz`, `trades_early.csv.gz`, `base_rate.csv`, `multiple_testing.csv`.
