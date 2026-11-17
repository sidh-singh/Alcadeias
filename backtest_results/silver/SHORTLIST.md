# Silver study: the DEV shortlist (PREREG_SILVER.md §5.1)

- Written 2026-11-17 07:18 UTC, before any VAL run.
- Variants: 144 (N = 144); not run: 0.
- DEV 2018-11-01 → 2023-01-01, per-unit streams (0.01 lot), costs × 1.0 and × 1.5 (§2).
- Multiple testing over the 144 run variants: E[max weekly Sharpe] of 144 trials, annualised: 7.91 with the cross-variant variance, 1.30 under a pure-noise null of 219 weeks. Hansen SPA (best variant C32[which=dec]): p = 0.288.
- Variants failing each rule: D1 27, D2 118, D3 120, D4 141, D5 125, D6 46.

**The shortlist is empty.** By §5.2 there are no finalists and the hold-out is not run.


**The six closest variants that did not pass** (by DEV annualised profit/DD, for information; rules D1 trades, D2 profit at ×1.0 and ×1.5, D3 positive quarters ≥ 50%, D4 profit/DD ≥ 1.0, D5 neighbours or halves positive, D6 max DD < $2,000, D7 gold filter beats silver's):

| Variant | Flags | DEV profit ×1.0 | ×1.5 | Max DD | Profit/DD | Pos. quarters | Trades (need) | Failed | D5 detail | DSR (prereg) | DSR vs noise null |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C32[which=dec] | C,M | +388 | +375 | 121 | 3.20 | 100% | 4 (12) | D1 | halves +276 / +112 | 0.00 | 0.44 |
| C01[L=6,lo=True] |  | +474 | +465 | 408 | 1.16 | 77% | 5 (12) | D1 | neighbours +255 | 0.00 | 0.04 |
| C12[period=10,mult=4.0] |  | +597 | +485 | 546 | 1.09 | 59% | 105 (12) | D5 | neighbours +242 -239 | 0.00 | 0.04 |
| C30[trend=True] |  | +160 | +130 | 176 | 0.91 | 44% | 19 (12) | D3 D4 D5 | halves +232 / -72 | 0.00 | 0.02 |
| C08[n=10] |  | +325 | +312 | 408 | 0.80 | 62% | 5 (12) | D1 D4 | neighbours +316 +252 | 0.00 | 0.02 |
| C06[s=1,l=10,lo=True] |  | +325 | +312 | 408 | 0.80 | 62% | 5 (12) | D1 D4 | neighbours +252 | 0.00 | 0.02 |

The full table (every variant, every rule) is `dev/shortlist_table.csv`; the per-split metrics are `dev_results.csv`.
