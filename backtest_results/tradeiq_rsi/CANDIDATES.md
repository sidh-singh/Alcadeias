# TradeIQ's RSI replacements: the candidates after Development and Validation

Written by `python -B -m backtesting.research.tradeiq select` on 27 Nov 2026 23:45 UTC from the CSVs of `run` (written 2026-11-27 23:44:50+00:00). **This is not `FINALISTS.md`.** Nothing is frozen, and no result of the hold-out (from 2024-07-01) exists: the guard of `tradeiq_market.py` served the data only up to 2024-06-30 23:59 UTC. The would-be finalists below are what PREREG section 7's rule gives; they become finalists only when `FINALISTS.md` and its sha256 are written.

Per 0.01 lot after Exness costs (spread at every fill, one extra spread on every stop fill). Development 2019-01-01 to 2022-12-31, Validation 2023-01-01 to 2024-06-30, D+V the two together as one continuous run. Profit / DD = net profit / max drawdown. The rules are PREREG section 6 with DEVIATIONS 1-3, 6-7 and 19-26; x1.5 scales the spread of every M1 bar (DEVIATIONS 27). The tables against buy-and-hold, of the filters, of the comparison curves and of the video's claims follow DEVIATIONS 28-31, which were written after the review of this run and before any result of the hold-out.

## What was run

| Symbol | Variants | of them RV | M1 data served | M1 bars | Runs (3 windows x 2 costs) |
|---|---|---|---|---|---|
| Gold (XAUUSDm) | 336 | 0 | 2017-01-03 .. 2024-07-01 00:00 | 2,638,586 | 2016 |
| BTC (BTCUSDm) | 414 | 78 | 2018-01-01 .. 2024-07-01 00:00 | 3,403,835 | 2484 |

Total: 750 variants (DEVIATIONS 22). Code that wrote the CSVs (git blob ids): `tradeiq.py` d0ad7f06a226, `tradeiq_ind.py` 2a6483a415eb, `tradeiq_market.py` dc784854b60c, `external.py` 5f037a44b07e, `silver.py` cbc46c58add0. It is the code in the working tree now.

State checks (`state_checks.csv`): on the bars the windows read, XAUUSDm 42,579 bars, 0 missing values, 0 exact ties with a level; BTCUSDm 62,162 bars, 0 missing values, 0 exact ties with a level.

## Headline

| Symbol | Variants | Dev net > 0 (x1.0) | Val net > 0 (x1.0) | Both > 0 | Rule 1 (dev > 0 at x1.0 and x1.5) | Rules 1-2 | Rules 1-3 | Qualify (rules 1-4) | Would-be finalists |
|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | 336 | 201 | 259 | 162 | 170 | 164 | 55 | 44 | 3 |
| BTC (BTCUSDm) | 414 | 224 | 289 | 202 | 199 | 199 | 65 | 59 | 3 |

Gold (XAUUSDm) by indicator:

| Indicator | Variants | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Median val net | Best dev net | Best val net |
|---|---|---|---|---|---|---|---|---|
| RSI | 54 | 28 | 44 | 8 | +22 | +150 | +379 | +345 |
| LaRSI | 54 | 40 | 45 | 15 | +173 | +180 | +733 | +525 |
| VWRSI | 78 | 42 | 46 | 6 | +22 | +54 | +1,330 | +349 |
| TSI | 60 | 37 | 49 | 7 | +138 | +201 | +543 | +364 |
| QQE | 78 | 48 | 63 | 8 | +81 | +142 | +517 | +435 |
| MA200 | 12 | 6 | 12 | 0 | +21 | +337 | +249 | +417 |

BTC (BTCUSDm) by indicator:

| Indicator | Variants | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Median val net | Best dev net | Best val net |
|---|---|---|---|---|---|---|---|---|
| RSI | 54 | 29 | 44 | 8 | +101 | +117 | +509 | +330 |
| LaRSI | 54 | 33 | 46 | 11 | +84 | +205 | +559 | +404 |
| VWRSI | 78 | 38 | 46 | 8 | -24 | +66 | +680 | +275 |
| VWRSI-RV | 78 | 41 | 38 | 19 | +99 | -10 | +734 | +232 |
| TSI | 60 | 33 | 44 | 7 | +56 | +158 | +576 | +384 |
| QQE | 78 | 40 | 59 | 2 | +9.36 | +135 | +312 | +374 |
| MA200 | 12 | 10 | 12 | 4 | +56 | +323 | +520 | +405 |

Gold (XAUUSDm) by timeframe:

| TF | Variants | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Median val net |
|---|---|---|---|---|---|---|
| 1H | 136 | 76 | 104 | 22 | +68 | +117 |
| 4H | 112 | 78 | 95 | 17 | +143 | +220 |
| 1D | 88 | 47 | 60 | 5 | +23 | +157 |

BTC (BTCUSDm) by timeframe:

| TF | Variants | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Median val net |
|---|---|---|---|---|---|---|
| 1H | 168 | 14 | 82 | 0 | -418 | -16 |
| 4H | 138 | 115 | 108 | 25 | +149 | +152 |
| 1D | 108 | 95 | 99 | 34 | +317 | +246 |

Buy-and-hold of 0.01 lot, for reference:

| Symbol | Window | Net x1.0 | Net x1.5 | Max DD | Profit / DD |
|---|---|---|---|---|---|
| Gold (XAUUSDm) | Development | +542 | +542 | 459 | 1.18 |
| Gold (XAUUSDm) | Validation | +498 | +497 | 264 | 1.88 |
| Gold (XAUUSDm) | D+V | +1,043 | +1,043 | 459 | 2.27 |
| BTC (BTCUSDm) | Development | +128 | +128 | 535 | 0.24 |
| BTC (BTCUSDm) | Validation | +462 | +462 | 171 | 2.69 |
| BTC (BTCUSDm) | D+V | +590 | +590 | 535 | 1.10 |

## Gold (XAUUSDm): the qualifiers

| Rank | Variant | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | Val P/DD | D+V net | D+V P/DD | Would-be finalist |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|QQE|R2|F2-4H|S0` | +458 | +399 | 348 | 2.82 | 69% | +224 | 1.13 | +688 | 3.48 | **yes** |
| 2 | `1H|LaRSI|R2|F1|S0` | +436 | +374 | 378 | 2.41 | 81% | +228 | 1.14 | +670 | 3.35 | **yes** |
| 3 | `1H|LaRSI|R2|F1|S1` | +427 | +354 | 378 | 2.06 | 75% | +254 | 1.40 | +688 | 3.33 |  |
| 4 | `4H|RSI|R2|F1|S0` | +368 | +330 | 235 | 1.82 | 56% | +270 | 1.26 | +644 | 3.00 | **yes** |
| 5 | `1H|TSI|R2|F2-4H|S0` | +446 | +373 | 386 | 1.93 | 62% | +241 | 1.12 | +694 | 3.00 |  |
| 6 | `4H|RSI|R2|F1|S1` | +361 | +320 | 235 | 1.78 | 56% | +270 | 1.26 | +637 | 2.96 |  |
| 7 | `1H|RSI|R2|F2-4H|S0` | +333 | +202 | 728 | 1.60 | 62% | +233 | 1.19 | +573 | 2.75 |  |
| 8 | `1H|LaRSI|R2|F0|S1` | +581 | +515 | 346 | 1.91 | 81% | +237 | 1.17 | +825 | 2.72 |  |
| 9 | `1H|LaRSI|R2|F0|S0` | +636 | +580 | 346 | 2.02 | 81% | +191 | 0.82 | +833 | 2.64 |  |
| 10 | `1H|LaRSI|R2|F2-1D|S1` | +427 | +373 | 247 | 2.15 | 62% | +121 | 0.59 | +554 | 2.50 |  |
| 11 | `1H|RSI|R2|F2-4H|S1` | +313 | +172 | 728 | 1.41 | 62% | +228 | 1.12 | +548 | 2.46 |  |
| 12 | `4H|VWRSI|R2|F1|S1` | +330 | +293 | 206 | 1.29 | 62% | +289 | 1.71 | +625 | 2.45 |  |
| 13 | `4H|TSI|R2|F0|S0` | +364 | +340 | 168 | 1.37 | 69% | +359 | 1.19 | +730 | 2.41 |  |
| 14 | `4H|TSI|R2|F3|S0` | +364 | +340 | 168 | 1.37 | 69% | +359 | 1.19 | +730 | 2.41 |  |
| 15 | `4H|VWRSI|R2|F1|S0` | +331 | +297 | 206 | 1.25 | 62% | +285 | 1.69 | +622 | 2.34 |  |
| 16 | `4H|TSI|R2|F0|S1` | +347 | +322 | 168 | 1.35 | 69% | +364 | 1.18 | +717 | 2.33 |  |
| 17 | `4H|TSI|R2|F3|S1` | +347 | +322 | 168 | 1.35 | 69% | +364 | 1.18 | +717 | 2.33 |  |
| 18 | `1H|LaRSI|R2|F2-4H|S0` | +409 | +366 | 235 | 1.84 | 75% | +99 | 0.49 | +515 | 2.32 |  |
| 19 | `1H|TSI|R2|F2-4H|S1` | +387 | +309 | 386 | 1.39 | 69% | +253 | 1.17 | +647 | 2.32 |  |
| 20 | `1H|LaRSI|R2|F3|S1` | +367 | +269 | 509 | 1.39 | 62% | +234 | 1.12 | +607 | 2.31 |  |
| 21 | `4H|RSI|R2|F3|S0` | +322 | +283 | 268 | 1.20 | 56% | +345 | 1.14 | +674 | 2.21 |  |
| 22 | `1H|QQE|R2|F0|S0` | +379 | +296 | 553 | 1.33 | 62% | +227 | 0.96 | +613 | 2.16 |  |
| 23 | `1H|LaRSI|R2|F2-4H|S1` | +380 | +325 | 235 | 1.59 | 75% | +122 | 0.63 | +508 | 2.13 |  |
| 24 | `4H|VWRSI|R2|F3|S1` | +350 | +316 | 243 | 1.23 | 69% | +243 | 0.96 | +600 | 2.11 |  |
| 25 | `1H|LaRSI|R2|F3|S0` | +379 | +297 | 509 | 1.31 | 62% | +226 | 1.08 | +611 | 2.11 |  |
| 26 | `4H|RSI|R2|F3|S1` | +304 | +265 | 268 | 1.13 | 56% | +338 | 1.09 | +648 | 2.10 |  |
| 27 | `1H|QQE|R2|F2-4H|S1` | +283 | +218 | 348 | 1.17 | 62% | +212 | 1.05 | +502 | 2.08 |  |
| 28 | `1D|QQE|R2|F3|S0` | +431 | +428 | 23 | 1.37 | 62% | +209 | 0.89 | +653 | 2.08 |  |
| 29 | `4H|RSI|R2|F0|S0` | +379 | +328 | 356 | 1.26 | 50% | +302 | 0.91 | +687 | 2.07 |  |
| 30 | `4H|VWRSI|R2|F3|S0` | +359 | +325 | 243 | 1.20 | 69% | +244 | 0.98 | +610 | 2.04 |  |
| 31 | `1H|VWRSI|R2|F2-4H|S0` | +339 | +228 | 609 | 1.37 | 62% | +157 | 0.79 | +503 | 2.03 |  |
| 32 | `1H|VWRSI|R2|F2-4H|S1` | +329 | +216 | 609 | 1.29 | 62% | +181 | 0.96 | +516 | 2.02 |  |
| 33 | `4H|RSI|R2|F0|S1` | +345 | +294 | 356 | 1.14 | 50% | +313 | 0.93 | +665 | 1.97 |  |
| 34 | `1D|QQE|R2|F3|S1` | +407 | +403 | 23 | 1.26 | 62% | +209 | 0.89 | +629 | 1.95 |  |
| 35 | `4H|QQE|R2|F0|S1` | +353 | +327 | 155 | 1.20 | 62% | +259 | 0.87 | +619 | 1.81 |  |
| 36 | `1H|LaRSI|R2|F2-1D|S0` | +387 | +343 | 247 | 1.73 | 62% | +75 | 0.32 | +469 | 1.74 |  |
| 37 | `1D|QQE|R2|F0|S0` | +404 | +401 | 23 | 1.06 | 62% | +210 | 0.88 | +628 | 1.65 |  |
| 38 | `1D|LaRSI|R2|F3|S0` | +408 | +404 | 18 | 1.23 | 62% | +123 | 0.58 | +544 | 1.65 |  |
| 39 | `1D|LaRSI|R2|F3|S1` | +397 | +393 | 18 | 1.16 | 62% | +123 | 0.58 | +533 | 1.56 |  |
| 40 | `1H|LaRSI|R1|F1|S1` | +329 | +182 | 752 | 1.15 | 62% | +61 | 0.17 | +397 | 1.14 |  |
| 41 | `1H|LaRSI|R1|F2-4H|S0` | +283 | +209 | 448 | 1.09 | 62% | +34 | 0.12 | +323 | 1.11 |  |
| 42 | `4H|TSI|R4|F0|S1` | +418 | +402 | 67 | 1.21 | 50% | +9.27 | 0.04 | +451 | 1.08 |  |
| 43 | `1H|LaRSI|R1|F1|S0` | +343 | +222 | 752 | 1.19 | 62% | +25 | 0.07 | +374 | 0.99 |  |
| 44 | `4H|QQE|R3|F3|S1` | +275 | +210 | 441 | 1.07 | 62% | +22 | 0.05 | +303 | 0.76 |  |

### Gold (XAUUSDm): who WOULD be the finalists

| # | Variant | Indicator | Dev net | Dev x1.5 | Dev DD | Dev trades | Dev win | Dev PF | Dev Sharpe | Val net | Val x1.5 | Val DD | Val trades | D+V net | D+V DD | D+V P/DD | Dev time in mkt | Dev hold (h) | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|QQE|R2|F2-4H|S0` | QQE | +458 | +399 | 163 | 348 | 34% | 1.31 | 0.87 | +224 | +209 | 198 | 137 | +688 | 198 | 3.48 | 30% | 30 | 0.298 |
| 2 | `1H|LaRSI|R2|F1|S0` | LaRSI | +436 | +374 | 180 | 378 | 25% | 1.30 | 0.79 | +228 | +214 | 200 | 132 | +670 | 200 | 3.35 | 41% | 40 | 0.239 |
| 4 | `4H|RSI|R2|F1|S0` | RSI | +368 | +330 | 203 | 235 | 24% | 1.33 | 0.59 | +270 | +261 | 215 | 81 | +644 | 215 | 3.00 | 39% | 59 | 0.138 |

Gold (XAUUSDm): the would-be finalists against buy-and-hold of the same span (x1.0, DEVIATIONS 28). 3 of the 3 never go short. "Exam rule" is PREREG 8's pass rule (net > 0 and P/DD >= 0.5), applied here to these windows for information; "exposure-matched" is the time in the market x buy-and-hold's net.

| # | Variant | Window | Net | Max DD | P/DD | Exam rule | Time in mkt | Shorts | B&H net | B&H DD | B&H P/DD | Exposure-matched B&H | P/DD above B&H | Net above exp.-matched |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|QQE|R2|F2-4H|S0` | Development | +458 | 163 | 2.82 | yes | 30% | 0 | +542 | 459 | 1.18 | +161 | yes | yes |
| 1 | `1H|QQE|R2|F2-4H|S0` | Validation | +224 | 198 | 1.13 | yes | 32% | 0 | +498 | 264 | 1.88 | +161 | no | yes |
| 1 | `1H|QQE|R2|F2-4H|S0` | D+V | +688 | 198 | 3.48 | yes | 30% | 0 | +1,043 | 459 | 2.27 | +318 | yes | yes |
| 2 | `1H|LaRSI|R2|F1|S0` | Development | +436 | 180 | 2.41 | yes | 41% | 0 | +542 | 459 | 1.18 | +221 | yes | yes |
| 2 | `1H|LaRSI|R2|F1|S0` | Validation | +228 | 200 | 1.14 | yes | 40% | 0 | +498 | 264 | 1.88 | +200 | no | yes |
| 2 | `1H|LaRSI|R2|F1|S0` | D+V | +670 | 200 | 3.35 | yes | 41% | 0 | +1,043 | 459 | 2.27 | +424 | yes | yes |
| 3 | `4H|RSI|R2|F1|S0` | Development | +368 | 203 | 1.82 | yes | 39% | 0 | +542 | 459 | 1.18 | +213 | yes | yes |
| 3 | `4H|RSI|R2|F1|S0` | Validation | +270 | 215 | 1.26 | yes | 41% | 0 | +498 | 264 | 1.88 | +204 | no | yes |
| 3 | `4H|RSI|R2|F1|S0` | D+V | +644 | 215 | 3.00 | yes | 40% | 0 | +1,043 | 459 | 2.27 | +414 | yes | yes |

Gold (XAUUSDm): the best qualifier of each indicator without a slot, against the third would-be finalist `4H|RSI|R2|F1|S0` (rank 4, D+V P/DD 2.9998). "Net needed": the D+V net at which, with its own drawdown, it would have taken the slot.

| Indicator | Best qualifier | Rank | D+V net | D+V DD | D+V P/DD | Gap (P/DD) | Net needed | D+V P/DD x1.5 (it / the third) |
|---|---|---|---|---|---|---|---|---|
| VWRSI | `4H|VWRSI|R2|F1|S1` | 12 | +625 | 256 | 2.4456 | 0.5542 | +142 | 2.25 / 2.74 |
| TSI | `1H|TSI|R2|F2-4H|S0` | 5 | +694 | 231 | 2.9976 | 0.0023 | +0.52 | 2.45 / 2.74 |

The closest is the TSI: +0.52 more D+V net over 5.5 years (0.08% of its D+V net) would have given it the third slot. The order of the slots is a selection rule, not a comparison: it is no evidence that the RSI is better than the TSI. The indicators are compared in the RSI table and in the claims below.

Gold (XAUUSDm): the five best by D+V profit / DD among the variants that fail exactly one rule (for information; they are not candidates):

| Variant | Fails | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V P/DD |
|---|---|---|---|---|---|---|---|---|
| `1D|VWRSI|R4|F0|S1` | q2 | +1,330 | +1,329 | 6 | 5.79 | 69% | +160 | 3.28 |
| `1D|VWRSI|R4|F0|S0` | q2 | +1,255 | +1,255 | 6 | 3.91 | 69% | +118 | 2.92 |
| `4H|QQE|R2|F3|S1` | q3 | +289 | +267 | 162 | 0.98 | 50% | +261 | 1.85 |
| `4H|TSI|R2|F1|S0` | q3 | +174 | +150 | 142 | 0.59 | 56% | +338 | 1.77 |
| `4H|VWRSI|R2|F0|S0` | q3 | +340 | +300 | 282 | 0.85 | 56% | +346 | 1.74 |

## BTC (BTCUSDm): the qualifiers

| Rank | Variant | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | Val P/DD | D+V net | D+V P/DD | Would-be finalist |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|LaRSI|R2|F3|S1` | +404 | +397 | 26 | 2.36 | 56% | +264 | 1.74 | +668 | 3.70 | **yes** |
| 2 | `1D|LaRSI|R2|F3|S0` | +402 | +397 | 26 | 2.31 | 56% | +264 | 1.74 | +665 | 3.63 |  |
| 3 | `1D|VWRSI|R3|F0|S1` | +473 | +463 | 54 | 2.72 | 62% | +117 | 0.96 | +590 | 3.39 | **yes** |
| 4 | `1D|VWRSI|R3|F0|S0` | +471 | +461 | 54 | 2.70 | 62% | +117 | 0.96 | +587 | 3.37 |  |
| 5 | `1D|LaRSI|R1|F3|S1` | +559 | +547 | 55 | 2.29 | 50% | +229 | 1.22 | +787 | 3.23 |  |
| 6 | `1D|LaRSI|R1|F3|S0` | +557 | +547 | 55 | 2.28 | 50% | +222 | 1.18 | +778 | 3.19 |  |
| 7 | `1D|VWRSI|R3|F3|S1` | +437 | +429 | 45 | 2.46 | 62% | +117 | 0.96 | +553 | 3.12 |  |
| 8 | `1D|VWRSI|R3|F3|S0` | +434 | +426 | 45 | 2.45 | 62% | +117 | 0.96 | +551 | 3.11 |  |
| 9 | `4H|LaRSI|R2|F1|S1` | +294 | +269 | 125 | 1.50 | 56% | +307 | 3.10 | +601 | 3.07 |  |
| 10 | `4H|LaRSI|R2|F1|S0` | +263 | +241 | 125 | 1.27 | 50% | +346 | 3.55 | +610 | 2.94 |  |
| 11 | `4H|TSI|R2|F1|S0` | +294 | +263 | 178 | 1.53 | 62% | +261 | 1.90 | +556 | 2.89 | **yes** |
| 12 | `4H|MA200|R2|F0|S0` | +324 | +301 | 128 | 1.30 | 69% | +376 | 2.88 | +700 | 2.82 |  |
| 13 | `4H|VWRSI|R1|F1|S0` | +488 | +400 | 537 | 2.12 | 62% | +140 | 0.97 | +628 | 2.72 |  |
| 14 | `1D|LaRSI|R1|F0|S1` | +539 | +531 | 40 | 2.08 | 50% | +175 | 0.67 | +711 | 2.70 |  |
| 15 | `4H|TSI|R2|F1|S1` | +287 | +254 | 178 | 1.49 | 62% | +231 | 1.67 | +518 | 2.70 |  |
| 16 | `1D|VWRSI|R3|F1|S0` | +340 | +332 | 44 | 1.92 | 62% | +135 | 0.98 | +474 | 2.68 |  |
| 17 | `1D|VWRSI|R3|F1|S1` | +340 | +332 | 44 | 1.92 | 62% | +135 | 0.98 | +474 | 2.68 |  |
| 18 | `1D|VWRSI-RV|R2|F0|S0` | +430 | +421 | 56 | 1.73 | 50% | +232 | 0.91 | +662 | 2.61 |  |
| 19 | `1D|VWRSI-RV|R2|F3|S0` | +444 | +437 | 44 | 1.98 | 50% | +208 | 0.82 | +652 | 2.57 |  |
| 20 | `1D|LaRSI|R1|F0|S0` | +538 | +531 | 40 | 2.22 | 50% | +138 | 0.52 | +675 | 2.56 |  |
| 21 | `1D|VWRSI-RV|R2|F0|S1` | +427 | +418 | 56 | 1.75 | 50% | +220 | 0.87 | +646 | 2.55 |  |
| 22 | `1D|VWRSI-RV|R3|F3|S1` | +316 | +308 | 46 | 2.15 | 62% | +78 | 0.67 | +393 | 2.54 |  |
| 23 | `1D|LaRSI|R4|F0|S1` | +461 | +456 | 27 | 1.35 | 50% | +404 | 2.98 | +866 | 2.53 |  |
| 24 | `1D|VWRSI-RV|R3|F3|S0` | +317 | +309 | 46 | 2.14 | 62% | +78 | 0.67 | +394 | 2.53 |  |
| 25 | `1D|RSI|R2|F3|S0` | +330 | +322 | 50 | 1.26 | 50% | +330 | 1.83 | +660 | 2.52 |  |
| 26 | `1D|VWRSI-RV|R2|F3|S1` | +441 | +434 | 44 | 2.00 | 50% | +196 | 0.77 | +637 | 2.51 |  |
| 27 | `1D|TSI|R1|F0|S0` | +576 | +564 | 71 | 1.64 | 50% | +306 | 2.25 | +881 | 2.51 |  |
| 28 | `1D|TSI|R1|F3|S0` | +576 | +564 | 71 | 1.64 | 50% | +306 | 2.25 | +881 | 2.51 |  |
| 29 | `1D|RSI|R2|F3|S1` | +327 | +319 | 50 | 1.25 | 50% | +330 | 1.83 | +657 | 2.50 |  |
| 30 | `1D|TSI|R1|F0|S1` | +572 | +561 | 71 | 1.63 | 50% | +305 | 2.25 | +876 | 2.49 |  |
| 31 | `1D|TSI|R1|F3|S1` | +572 | +561 | 71 | 1.63 | 50% | +305 | 2.25 | +876 | 2.49 |  |
| 32 | `4H|MA200|R2|F0|S1` | +301 | +277 | 128 | 1.10 | 69% | +375 | 2.87 | +676 | 2.47 |  |
| 33 | `1D|VWRSI-RV|R3|F0|S0` | +293 | +284 | 53 | 1.95 | 69% | +77 | 0.66 | +369 | 2.46 |  |
| 34 | `1D|VWRSI-RV|R3|F0|S1` | +292 | +283 | 53 | 1.94 | 69% | +77 | 0.66 | +368 | 2.45 |  |
| 35 | `4H|VWRSI-RV|R1|F1|S0` | +517 | +441 | 429 | 1.95 | 62% | +129 | 0.61 | +646 | 2.44 |  |
| 36 | `4H|VWRSI-RV|R1|F1|S1` | +507 | +428 | 429 | 1.94 | 62% | +127 | 0.60 | +635 | 2.43 |  |
| 37 | `4H|VWRSI|R1|F1|S1` | +434 | +336 | 537 | 1.88 | 62% | +124 | 0.82 | +558 | 2.41 |  |
| 38 | `4H|VWRSI-RV|R2|F0|S0` | +321 | +269 | 301 | 1.44 | 56% | +215 | 1.18 | +536 | 2.41 |  |
| 39 | `4H|QQE|R2|F1|S0` | +274 | +244 | 168 | 1.48 | 56% | +166 | 0.91 | +440 | 2.38 |  |
| 40 | `4H|QQE|R2|F1|S1` | +269 | +237 | 168 | 1.44 | 56% | +168 | 0.96 | +436 | 2.34 |  |
| 41 | `1D|LaRSI|R2|F0|S1` | +335 | +331 | 20 | 1.22 | 50% | +300 | 1.69 | +634 | 2.31 |  |
| 42 | `1D|LaRSI|R2|F0|S0` | +332 | +329 | 20 | 1.17 | 50% | +300 | 1.69 | +632 | 2.22 |  |
| 43 | `1D|RSI|R2|F0|S0` | +284 | +274 | 67 | 1.02 | 50% | +322 | 1.51 | +606 | 2.18 |  |
| 44 | `1D|RSI|R2|F0|S1` | +281 | +270 | 67 | 1.01 | 50% | +322 | 1.51 | +603 | 2.17 |  |
| 45 | `4H|VWRSI-RV|R2|F1|S0` | +321 | +282 | 220 | 1.35 | 50% | +181 | 1.16 | +503 | 2.11 |  |
| 46 | `4H|VWRSI-RV|R2|F1|S1` | +310 | +268 | 220 | 1.30 | 50% | +175 | 1.12 | +485 | 2.03 |  |
| 47 | `4H|RSI|R2|F1|S0` | +273 | +225 | 283 | 1.30 | 50% | +153 | 1.04 | +426 | 2.03 |  |
| 48 | `4H|RSI|R4|F0|S1` | +253 | +236 | 80 | 1.03 | 62% | +227 | 1.64 | +480 | 1.95 |  |
| 49 | `4H|TSI|R1|F1|S0` | +330 | +269 | 352 | 1.17 | 50% | +213 | 1.26 | +543 | 1.93 |  |
| 50 | `4H|VWRSI-RV|R2|F3|S1` | +252 | +206 | 267 | 1.05 | 50% | +204 | 1.09 | +457 | 1.91 |  |
| 51 | `4H|RSI|R1|F1|S0` | +331 | +237 | 563 | 1.45 | 50% | +104 | 0.57 | +436 | 1.90 |  |
| 52 | `4H|MA200|R1|F0|S0` | +520 | +473 | 256 | 1.18 | 62% | +290 | 1.66 | +810 | 1.84 |  |
| 53 | `4H|RSI|R2|F1|S1` | +254 | +204 | 283 | 1.21 | 50% | +127 | 0.77 | +381 | 1.81 |  |
| 54 | `4H|MA200|R1|F0|S1` | +503 | +453 | 256 | 1.10 | 62% | +297 | 1.70 | +798 | 1.75 |  |
| 55 | `1D|VWRSI-RV|R1|F0|S0` | +734 | +716 | 112 | 2.46 | 50% | +2.47 | 0.01 | +736 | 1.75 |  |
| 56 | `1D|VWRSI-RV|R3|F1|S0` | +207 | +198 | 43 | 1.02 | 62% | +124 | 1.03 | +330 | 1.64 |  |
| 57 | `1D|VWRSI-RV|R3|F1|S1` | +204 | +196 | 43 | 1.01 | 62% | +124 | 1.03 | +328 | 1.62 |  |
| 58 | `4H|VWRSI-RV|R1|F3|S0` | +328 | +238 | 526 | 1.28 | 69% | +52 | 0.23 | +380 | 1.48 |  |
| 59 | `4H|VWRSI-RV|R1|F3|S1` | +311 | +219 | 526 | 1.22 | 62% | +44 | 0.19 | +355 | 1.39 |  |

### BTC (BTCUSDm): who WOULD be the finalists

| # | Variant | Indicator | Dev net | Dev x1.5 | Dev DD | Dev trades | Dev win | Dev PF | Dev Sharpe | Val net | Val x1.5 | Val DD | Val trades | D+V net | D+V DD | D+V P/DD | Dev time in mkt | Dev hold (h) | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|LaRSI|R2|F3|S1` | LaRSI | +404 | +397 | 171 | 26 | 42% | 3.90 | 0.67 | +264 | +262 | 151 | 10 | +668 | 181 | 3.70 | 46% | 624 | 0.001 |
| 3 | `1D|VWRSI|R3|F0|S1` | VWRSI | +473 | +463 | 174 | 54 | 50% | 2.52 | 0.87 | +117 | +114 | 122 | 22 | +590 | 174 | 3.39 | 40% | 260 | 0.002 |
| 11 | `4H|TSI|R2|F1|S0` | TSI | +294 | +263 | 192 | 178 | 26% | 1.40 | 0.51 | +261 | +251 | 138 | 68 | +556 | 192 | 2.89 | 39% | 76 | 0.000 |

BTC (BTCUSDm): the would-be finalists against buy-and-hold of the same span (x1.0, DEVIATIONS 28). 2 of the 3 never go short. "Exam rule" is PREREG 8's pass rule (net > 0 and P/DD >= 0.5), applied here to these windows for information; "exposure-matched" is the time in the market x buy-and-hold's net.

| # | Variant | Window | Net | Max DD | P/DD | Exam rule | Time in mkt | Shorts | B&H net | B&H DD | B&H P/DD | Exposure-matched B&H | P/DD above B&H | Net above exp.-matched |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|LaRSI|R2|F3|S1` | Development | +404 | 171 | 2.36 | yes | 46% | 0 | +128 | 535 | 0.24 | +59 | yes | yes |
| 1 | `1D|LaRSI|R2|F3|S1` | Validation | +264 | 151 | 1.74 | yes | 57% | 0 | +462 | 171 | 2.69 | +263 | no | yes |
| 1 | `1D|LaRSI|R2|F3|S1` | D+V | +668 | 181 | 3.70 | yes | 49% | 0 | +590 | 535 | 1.10 | +290 | yes | yes |
| 2 | `1D|VWRSI|R3|F0|S1` | Development | +473 | 174 | 2.72 | yes | 40% | 26 | +128 | 535 | 0.24 | +51 | yes | yes |
| 2 | `1D|VWRSI|R3|F0|S1` | Validation | +117 | 122 | 0.96 | yes | 35% | 9 | +462 | 171 | 2.69 | +162 | no | no |
| 2 | `1D|VWRSI|R3|F0|S1` | D+V | +590 | 174 | 3.39 | yes | 39% | 34 | +590 | 535 | 1.10 | +229 | yes | yes |
| 3 | `4H|TSI|R2|F1|S0` | Development | +294 | 192 | 1.53 | yes | 39% | 0 | +128 | 535 | 0.24 | +49 | yes | yes |
| 3 | `4H|TSI|R2|F1|S0` | Validation | +261 | 138 | 1.90 | yes | 45% | 0 | +462 | 171 | 2.69 | +207 | no | yes |
| 3 | `4H|TSI|R2|F1|S0` | D+V | +556 | 192 | 2.89 | yes | 40% | 0 | +590 | 535 | 1.10 | +238 | yes | yes |

BTC (BTCUSDm): the best qualifier of each indicator without a slot, against the third would-be finalist `4H|TSI|R2|F1|S0` (rank 11, D+V P/DD 2.8930). "Net needed": the D+V net at which, with its own drawdown, it would have taken the slot.

| Indicator | Best qualifier | Rank | D+V net | D+V DD | D+V P/DD | Gap (P/DD) | Net needed | D+V P/DD x1.5 (it / the third) |
|---|---|---|---|---|---|---|---|---|
| RSI | `1D|RSI|R2|F3|S0` | 25 | +660 | 262 | 2.5170 | 0.3760 | +99 | 2.45 / 2.65 |
| QQE | `4H|QQE|R2|F1|S0` | 39 | +440 | 185 | 2.3760 | 0.5170 | +96 | 2.09 / 2.65 |
| MA200 | `4H|MA200|R2|F0|S0` | 12 | +700 | 248 | 2.8204 | 0.0727 | +18 | 2.63 / 2.65 |

The closest is the MA200: +18 more D+V net over 5.5 years (2.58% of its D+V net) would have given it the third slot. The order of the slots is a selection rule, not a comparison: it is no evidence that the TSI is better than the MA200. The indicators are compared in the RSI table and in the claims below.

BTC (BTCUSDm): the five best by D+V profit / DD among the variants that fail exactly one rule (for information; they are not candidates):

| Variant | Fails | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V P/DD |
|---|---|---|---|---|---|---|---|---|
| `1D|TSI|R2|F3|S0` | q3 | +351 | +346 | 35 | 1.43 | 44% | +384 | 3.00 |
| `1D|TSI|R2|F0|S0` | q3 | +351 | +346 | 35 | 1.43 | 44% | +384 | 3.00 |
| `1D|TSI|R2|F3|S1` | q3 | +348 | +342 | 35 | 1.42 | 44% | +384 | 2.99 |
| `1D|TSI|R2|F0|S1` | q3 | +348 | +342 | 35 | 1.42 | 44% | +384 | 2.99 |
| `1D|VWRSI|R2|F0|S0` | q3 | +403 | +393 | 65 | 1.90 | 44% | +275 | 2.83 |

## Multiple testing (Development weekly P/L, x1.0)

| Symbol | Role | Variant | N | Weeks | Sharpe (ann.) | E[max] (as run) | DSR (as run) | E[max] (null var.) | DSR (null var.) | E[max] (within-TF var.) | DSR (within-TF var.) | SPA p | Reality Check p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | best dev Sharpe | `1D|VWRSI|R4|F0|S1` | 336 | 210 | 1.46 | 1.12 | 0.754 | 1.46 | 0.498 | 1.11 | 0.756 | 0.169 | 0.092 |
| Gold (XAUUSDm) | would-be finalist 1 (rank 1) | `1H|QQE|R2|F2-4H|S0` | 336 | 210 | 0.87 | 1.12 | 0.298 | 1.46 | 0.101 | 1.11 | 0.301 | 0.169 | 0.092 |
| Gold (XAUUSDm) | would-be finalist 2 (rank 2) | `1H|LaRSI|R2|F1|S0` | 336 | 210 | 0.79 | 1.12 | 0.239 | 1.46 | 0.075 | 1.11 | 0.242 | 0.169 | 0.092 |
| Gold (XAUUSDm) | would-be finalist 3 (rank 4) | `4H|RSI|R2|F1|S0` | 336 | 210 | 0.59 | 1.12 | 0.138 | 1.46 | 0.035 | 1.11 | 0.140 | 0.169 | 0.092 |
| BTC (BTCUSDm) | best dev Sharpe | `1D|VWRSI|R3|F0|S1` | 414 | 210 | 0.87 | 2.17 | 0.002 | 1.49 | 0.088 | 1.37 | 0.139 | 0.385 | 0.528 |
| BTC (BTCUSDm) | would-be finalist 1 (rank 1) | `1D|LaRSI|R2|F3|S1` | 414 | 210 | 0.67 | 2.17 | 0.001 | 1.49 | 0.044 | 1.37 | 0.073 | 0.385 | 0.528 |
| BTC (BTCUSDm) | would-be finalist 2 (rank 3) | `1D|VWRSI|R3|F0|S1` | 414 | 210 | 0.87 | 2.17 | 0.002 | 1.49 | 0.088 | 1.37 | 0.139 | 0.385 | 0.528 |
| BTC (BTCUSDm) | would-be finalist 3 (rank 11) | `4H|TSI|R2|F1|S0` | 414 | 210 | 0.51 | 2.17 | 0.000 | 1.49 | 0.017 | 1.37 | 0.032 | 0.385 | 0.528 |

DSR (deflated Sharpe ratio, Bailey and Lopez de Prado): the probability that the variant's true Sharpe ratio exceeds E[max], the expected best Sharpe ratio of N trials without skill, given its weekly Sharpe, skew and kurtosis over the weeks. E[max] needs the variance of the trials' Sharpe ratios: "as run" (DEVIATIONS 26) the spread of the N variants' Sharpe ratios; "null var." the trials' Sharpe variance under no skill, 1 / (weeks - 1); "within-TF var." (added after the run, on review) the spread around each timeframe's mean, pooled. The share of the spread that lies between the timeframes' means is 1% on Gold (XAUUSDm), 60% on BTC (BTCUSDm) (on BTC the costs make most 1H rows lose, which widens the spread and raises the as-run E[max]). SPA / Reality Check: the p-value of "no variant of the symbol beats staying flat", over all N variants at once (DEVIATIONS 26).

Over the rows above: DSR 0.000-0.754 as run, 0.017-0.498 with the null variance and 0.032-0.756 with the within-timeframe variance; SPA p 0.169 / 0.385 and Reality Check p 0.092 / 0.528 (Gold (XAUUSDm) / BTC (BTCUSDm)). By none of these figures can a Development Sharpe ratio be told apart from the best of N trials without skill (a DSR of 0.95 and a p-value of 0.05 are common bars in the literature). The plan sets no threshold for them: under PREREG 7 they are information, and the would-be finalists go to the exam as the rule selects them.

## Against the plain RSI (PREREG 7, question 1)

Each oscillator's variant against the RSI variant with the same family (R1, R2, R4), filter, stop, timeframe and symbol. Wins = strictly better (DEVIATIONS 25).

| Symbol | Indicator | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) | Dev fewer trades | Dev median trades / RSI's |
|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | LaRSI | 54 | 36 | 36 / 54 | 26 | 29 / 54 | 48 | 0.42 |
| Gold (XAUUSDm) | VWRSI | 54 | 38 | 34 / 54 | 30 | 30 / 54 | 54 | 0.84 |
| Gold (XAUUSDm) | TSI | 54 | 40 | 41 / 54 | 51 | 49 / 54 | 48 | 0.60 |
| Gold (XAUUSDm) | QQE | 48 | 31 | 30 / 48 | 17 | 24 / 48 | 48 | 0.51 |
| BTC (BTCUSDm) | LaRSI | 54 | 37 | 42 / 54 | 31 | 35 / 54 | 48 | 0.42 |
| BTC (BTCUSDm) | VWRSI | 54 | 29 | 29 / 54 | 16 | 20 / 54 | 50 | 0.96 |
| BTC (BTCUSDm) | TSI | 54 | 40 | 42 / 54 | 47 | 45 / 54 | 48 | 0.57 |
| BTC (BTCUSDm) | QQE | 48 | 22 | 22 / 48 | 46 | 44 / 48 | 48 | 0.49 |
| BTC (BTCUSDm) | VWRSI-RV | 54 | 44 | 46 / 54 | 15 | 13 / 54 | 54 | 0.70 |

By timeframe:

| Symbol | Indicator | TF | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | LaRSI | 1H | 22 | 22 | 22 | 7 | 11 |
| Gold (XAUUSDm) | VWRSI | 1H | 22 | 20 | 18 | 2 | 2 |
| Gold (XAUUSDm) | TSI | 1H | 22 | 21 | 20 | 21 | 19 |
| Gold (XAUUSDm) | QQE | 1H | 20 | 17 | 17 | 13 | 14 |
| Gold (XAUUSDm) | LaRSI | 4H | 18 | 2 | 2 | 16 | 16 |
| Gold (XAUUSDm) | VWRSI | 4H | 18 | 6 | 6 | 14 | 14 |
| Gold (XAUUSDm) | TSI | 4H | 18 | 5 | 7 | 16 | 16 |
| Gold (XAUUSDm) | QQE | 4H | 16 | 2 | 1 | 2 | 4 |
| Gold (XAUUSDm) | LaRSI | 1D | 14 | 12 | 12 | 3 | 2 |
| Gold (XAUUSDm) | VWRSI | 1D | 14 | 12 | 10 | 14 | 14 |
| Gold (XAUUSDm) | TSI | 1D | 14 | 14 | 14 | 14 | 14 |
| Gold (XAUUSDm) | QQE | 1D | 12 | 12 | 12 | 2 | 6 |
| BTC (BTCUSDm) | LaRSI | 1H | 22 | 20 | 20 | 12 | 7 |
| BTC (BTCUSDm) | VWRSI | 1H | 22 | 0 | 0 | 1 | 5 |
| BTC (BTCUSDm) | TSI | 1H | 22 | 20 | 20 | 19 | 18 |
| BTC (BTCUSDm) | QQE | 1H | 20 | 20 | 20 | 20 | 19 |
| BTC (BTCUSDm) | VWRSI-RV | 1H | 22 | 20 | 21 | 1 | 1 |
| BTC (BTCUSDm) | LaRSI | 4H | 18 | 3 | 8 | 17 | 17 |
| BTC (BTCUSDm) | VWRSI | 4H | 18 | 16 | 16 | 14 | 14 |
| BTC (BTCUSDm) | TSI | 4H | 18 | 8 | 10 | 16 | 15 |
| BTC (BTCUSDm) | QQE | 4H | 16 | 2 | 2 | 14 | 13 |
| BTC (BTCUSDm) | VWRSI-RV | 4H | 18 | 12 | 13 | 14 | 12 |
| BTC (BTCUSDm) | LaRSI | 1D | 14 | 14 | 14 | 2 | 11 |
| BTC (BTCUSDm) | VWRSI | 1D | 14 | 13 | 13 | 1 | 1 |
| BTC (BTCUSDm) | TSI | 1D | 14 | 12 | 12 | 12 | 12 |
| BTC (BTCUSDm) | QQE | 1D | 12 | 0 | 0 | 12 | 12 |
| BTC (BTCUSDm) | VWRSI-RV | 1D | 14 | 12 | 12 | 0 | 0 |

## PREREG 8's pass rule on Development and Validation (DEVIATIONS 28)

How many rows would pass the exam's rule (net > 0 at x1.0 and profit / max drawdown >= 0.5) on the windows already run. The rule is the exam's and stays; this table shows how often it is met by rows that only hold longs (the R2 rows; 5 of the 6 would-be finalists never go short) and by buy-and-hold.

| Symbol | Window | R2 rows (long only) | Other rows | Qualifiers | Buy-and-hold |
|---|---|---|---|---|---|
| Gold (XAUUSDm) | Development | 67/126 (53%) | 42/210 (20%) | 44/44 (100%) | yes |
| Gold (XAUUSDm) | Validation | 116/126 (92%) | 61/210 (29%) | 37/44 (84%) | yes |
| Gold (XAUUSDm) | D+V | 105/126 (83%) | 47/210 (22%) | 44/44 (100%) | yes |
| BTC (BTCUSDm) | Development | 66/150 (44%) | 87/264 (33%) | 59/59 (100%) | no |
| BTC (BTCUSDm) | Validation | 132/150 (88%) | 99/264 (38%) | 56/59 (95%) | yes |
| BTC (BTCUSDm) | D+V | 100/150 (67%) | 100/264 (38%) | 59/59 (100%) | yes |

## Question 2: the filters against no filter (DEVIATIONS 30)

Each filtered R1 / R2 / R3 variant against the same variant with F0 (the TSI's F3 rows, equal to its F0 rows, are left out). Wins = strictly better. F1 = MA200 on the signal timeframe, F2-4H / F2-1D = MA200 on the 4H / 1D chart (the owner's idea), F3 = TSI > 0. "Helps": more than half of the pairs won on net and on P/DD in both windows; "does not help": at most half on both in both; otherwise "mixed".

| Symbol | Filter | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) | Verdict |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | F1 | 72 | 15 | 18 / 72 | 46 | 55 / 72 | **mixed** |
| Gold (XAUUSDm) | F2-4H | 24 | 12 | 12 / 24 | 19 | 20 / 24 | **mixed** |
| Gold (XAUUSDm) | F2-1D | 48 | 7 | 8 / 48 | 25 | 27 / 48 | **mixed** |
| Gold (XAUUSDm) | F3 | 60 | 36 | 36 / 60 | 36 | 36 / 60 | **helps** |
| BTC (BTCUSDm) | F1 | 90 | 63 | 60 / 90 | 66 | 68 / 90 | **helps** |
| BTC (BTCUSDm) | F2-4H | 30 | 30 | 30 / 30 | 29 | 30 / 30 | **helps** |
| BTC (BTCUSDm) | F2-1D | 60 | 45 | 46 / 60 | 38 | 38 / 60 | **helps** |
| BTC (BTCUSDm) | F3 | 78 | 55 | 55 / 78 | 59 | 59 / 78 | **helps** |

By timeframe:

| Symbol | Filter | TF | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) | Verdict |
|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | F1 | 1H | 24 | 10 | 10 | 23 | 24 | mixed |
| Gold (XAUUSDm) | F2-4H | 1H | 24 | 12 | 12 | 19 | 20 | mixed |
| Gold (XAUUSDm) | F2-1D | 1H | 24 | 7 | 8 | 12 | 13 | mixed |
| Gold (XAUUSDm) | F3 | 1H | 20 | 12 | 12 | 16 | 16 | helps |
| Gold (XAUUSDm) | F1 | 4H | 24 | 3 | 6 | 7 | 15 | mixed |
| Gold (XAUUSDm) | F2-1D | 4H | 24 | 0 | 0 | 13 | 14 | mixed |
| Gold (XAUUSDm) | F3 | 4H | 20 | 10 | 10 | 13 | 11 | mixed |
| Gold (XAUUSDm) | F1 | 1D | 24 | 2 | 2 | 16 | 16 | mixed |
| Gold (XAUUSDm) | F3 | 1D | 20 | 14 | 14 | 7 | 9 | mixed |
| BTC (BTCUSDm) | F1 | 1H | 30 | 30 | 28 | 30 | 30 | helps |
| BTC (BTCUSDm) | F2-4H | 1H | 30 | 30 | 30 | 29 | 30 | helps |
| BTC (BTCUSDm) | F2-1D | 1H | 30 | 28 | 28 | 20 | 20 | helps |
| BTC (BTCUSDm) | F3 | 1H | 26 | 20 | 17 | 23 | 20 | helps |
| BTC (BTCUSDm) | F1 | 4H | 30 | 30 | 28 | 18 | 20 | helps |
| BTC (BTCUSDm) | F2-1D | 4H | 30 | 17 | 18 | 18 | 18 | helps |
| BTC (BTCUSDm) | F3 | 4H | 26 | 15 | 16 | 20 | 21 | helps |
| BTC (BTCUSDm) | F1 | 1D | 30 | 3 | 4 | 18 | 18 | mixed |
| BTC (BTCUSDm) | F3 | 1D | 26 | 20 | 22 | 16 | 18 | helps |

## PREREG 8's account curves: the rows (DEVIATIONS 29)

Chosen from Development and Validation only, before any hold-out result exists. The curves themselves (2019-01-01 to the data end, and the hold-out alone) are drawn after the exam.

| Symbol | Roles | Variant | Qualifies | Rank | D+V net | D+V DD | D+V P/DD |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | finalist 1; best QQE | `1H|QQE|R2|F2-4H|S0` | yes | 1 | +688 | 198 | 3.48 |
| Gold (XAUUSDm) | finalist 2; best LaRSI | `1H|LaRSI|R2|F1|S0` | yes | 2 | +670 | 200 | 3.35 |
| Gold (XAUUSDm) | finalist 3; best RSI; RSI baseline of finalist 3 | `4H|RSI|R2|F1|S0` | yes | 4 | +644 | 215 | 3.00 |
| Gold (XAUUSDm) | best VWRSI | `4H|VWRSI|R2|F1|S1` | yes | 12 | +625 | 256 | 2.45 |
| Gold (XAUUSDm) | best TSI | `1H|TSI|R2|F2-4H|S0` | yes | 5 | +694 | 231 | 3.00 |
| Gold (XAUUSDm) | best MA200 | `1H|MA200|R2|F0|S0` | no | - | +585 | 395 | 1.48 |
| Gold (XAUUSDm) | RSI baseline of finalist 1 | `1H|RSI|R2|F2-4H|S0` | yes | 7 | +573 | 209 | 2.75 |
| Gold (XAUUSDm) | RSI baseline of finalist 2 | `1H|RSI|R2|F1|S0` | no | - | +403 | 271 | 1.49 |
| BTC (BTCUSDm) | finalist 1; best LaRSI | `1D|LaRSI|R2|F3|S1` | yes | 1 | +668 | 181 | 3.70 |
| BTC (BTCUSDm) | finalist 2; best VWRSI | `1D|VWRSI|R3|F0|S1` | yes | 3 | +590 | 174 | 3.39 |
| BTC (BTCUSDm) | finalist 3; best TSI | `4H|TSI|R2|F1|S0` | yes | 11 | +556 | 192 | 2.89 |
| BTC (BTCUSDm) | best RSI | `1D|RSI|R2|F3|S0` | yes | 25 | +660 | 262 | 2.52 |
| BTC (BTCUSDm) | best QQE | `4H|QQE|R2|F1|S0` | yes | 39 | +440 | 185 | 2.38 |
| BTC (BTCUSDm) | best MA200 | `4H|MA200|R2|F0|S0` | yes | 12 | +700 | 248 | 2.82 |
| BTC (BTCUSDm) | RSI baseline of finalist 1 | `1D|RSI|R2|F3|S1` | yes | 29 | +657 | 262 | 2.50 |
| BTC (BTCUSDm) | RSI baseline of finalist 2 | `1D|RSI|R1|F0|S1` | no | - | +620 | 418 | 1.48 |
| BTC (BTCUSDm) | RSI baseline of finalist 3 | `4H|RSI|R2|F1|S0` | yes | 47 | +426 | 210 | 2.03 |

## PREREG 9: the evidence for the video's claims (DEVIATIONS 31)

Each part of a claim on the rows it is about, per symbol, in Development and in Validation separately; it holds when it holds in both windows, does not hold when it fails in both, and is mixed otherwise. These are the counts the verdicts of `RESULTS.md` will rest on; the hold-out is added after the exam, for information.

| Claim | Part | Symbol | Development | Validation | Verdict | Note |
|---|---|---|---|---|---|---|
| 1 | half of 8 alternatives could not beat the RSI | both |  |  | **cannot be tested** | the other four alternatives of the video are not in the grid |
| 1 | QQE beats the RSI in most of its pairs | Gold (XAUUSDm) | 31/48 | 17/48 | **mixed** |  |
| 1 | QQE beats the RSI in most of its pairs | BTC (BTCUSDm) | 22/48 | 46/48 | **mixed** |  |
| 1 | TSI beats the RSI in most of its pairs | Gold (XAUUSDm) | 40/54 | 51/54 | **holds** |  |
| 1 | TSI beats the RSI in most of its pairs | BTC (BTCUSDm) | 40/54 | 47/54 | **holds** |  |
| 1 | VWRSI beats the RSI in most of its pairs | Gold (XAUUSDm) | 38/54 | 30/54 | **holds** |  |
| 1 | VWRSI beats the RSI in most of its pairs | BTC (BTCUSDm) | 29/54 | 16/54 | **mixed** |  |
| 1 | LaRSI beats the RSI in most of its pairs | Gold (XAUUSDm) | 36/54 | 26/54 | **mixed** |  |
| 1 | LaRSI beats the RSI in most of its pairs | BTC (BTCUSDm) | 37/54 | 31/54 | **holds** |  |
| 1 | VWRSI-RV beats the RSI in most of its pairs | BTC (BTCUSDm) | 44/54 | 15/54 | **mixed** |  |
| 2 | QQE takes fewer trades than the RSI in every pair | Gold (XAUUSDm) | 48/48 | 48/48 | **holds** |  |
| 2 | QQE takes fewer trades than the RSI in every pair | BTC (BTCUSDm) | 48/48 | 48/48 | **holds** |  |
| 2 | QQE beats the RSI in most pairs | Gold (XAUUSDm) | 31/48 | 17/48 | **mixed** |  |
| 2 | QQE beats the RSI in most pairs | BTC (BTCUSDm) | 22/48 | 46/48 | **mixed** |  |
| 2 | QQE has a shorter longest losing streak in most pairs | Gold (XAUUSDm) | 34/48 | 40/48 | **holds** |  |
| 2 | QQE has a shorter longest losing streak in most pairs | BTC (BTCUSDm) | 42/48 | 48/48 | **holds** |  |
| 3 | the zero line works: TSI R1 / R2 with F0 make money in most rows | Gold (XAUUSDm) | 8/12 | 10/12 | **holds** |  |
| 3 | the zero line works: TSI R1 / R2 with F0 make money in most rows | BTC (BTCUSDm) | 8/12 | 10/12 | **holds** |  |
| 3 | the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs | Gold (XAUUSDm) | 2/6 | 3/6 | **does not hold** | signal-line rows with net > 0: 4/6 (dev), 4/6 (val) |
| 3 | the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs | BTC (BTCUSDm) | 6/6 | 5/6 | **holds** | signal-line rows with net > 0: 1/6 (dev), 0/6 (val) |
| 3 | TSI takes about half the RSI's trades (median ratio in [0.375, 0.625]) | Gold (XAUUSDm) | 0.60 | 0.58 | **holds** |  |
| 3 | TSI takes about half the RSI's trades (median ratio in [0.375, 0.625]) | BTC (BTCUSDm) | 0.57 | 0.52 | **holds** |  |
| 4 | VWRSI's 20 / 80 reversals are no better than the RSI's (it wins at most half) | Gold (XAUUSDm) | 6/6 | 4/6 | **does not hold** |  |
| 4 | VWRSI's 20 / 80 reversals are no better than the RSI's (it wins at most half) | BTC (BTCUSDm) | 1/6 | 2/6 | **holds** |  |
| 4 | the VWRSI's trend rule on crypto; it needs real volume | Gold (XAUUSDm) |  |  | **cannot be tested** | not a crypto market: the gold CFD has tick volume only |
| 4 | VWRSI's trend rule beats the RSI on every crypto timeframe (most pairs on each) | BTC (BTCUSDm) | 1H 0/20, 4H 16/16, 1D 12/12 | 1H 0/20, 4H 14/16, 1D 0/12 | **does not hold** |  |
| 4 | VWRSI-RV's trend rule beats the RSI on every crypto timeframe (most pairs on each) | BTC (BTCUSDm) | 1H 20/20, 4H 12/16, 1D 12/12 | 1H 0/20, 4H 14/16, 1D 0/12 | **mixed** |  |
| 4 | VWRSI-RV's 20 / 80 reversals are no better than the RSI's (it wins at most half) | BTC (BTCUSDm) | 0/6 | 1/6 | **holds** |  |
| 4 | the VWRSI needs real volume: on Binance volume it beats tick volume in most rows | BTC (BTCUSDm) | 60/78 | 11/78 | **mixed** |  |
| 5 | LaRSI beats the RSI in most pairs on every timeframe | Gold (XAUUSDm) | 1H 22/22, 4H 2/18, 1D 12/14 | 1H 7/22, 4H 16/18, 1D 3/14 | **does not hold** |  |
| 5 | LaRSI beats the RSI in most pairs on every timeframe | BTC (BTCUSDm) | 1H 20/22, 4H 3/18, 1D 14/14 | 1H 12/22, 4H 17/18, 1D 2/14 | **does not hold** |  |
| 5 | LaRSI takes far fewer trades than the RSI (median ratio <= 0.5) | Gold (XAUUSDm) | 0.42 | 0.41 | **holds** |  |
| 5 | LaRSI takes far fewer trades than the RSI (median ratio <= 0.5) | BTC (BTCUSDm) | 0.42 | 0.34 | **holds** |  |
| 5 | on 1H LaRSI on its own mostly did not make money (net > 0 in at most half) | Gold (XAUUSDm) | 6/6 | 4/6 | **does not hold** |  |
| 5 | on 1H LaRSI on its own mostly did not make money (net > 0 in at most half) | BTC (BTCUSDm) | 0/6 | 2/6 | **holds** |  |
| 5 | 4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H) | Gold (XAUUSDm) | 1H 100%, 4H 44%, 1D 71% | 1H 82%, 4H 94%, 1D 71% | **does not hold** |  |
| 5 | 4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H) | BTC (BTCUSDm) | 1H 18%, 4H 83%, 1D 100% | 1H 64%, 4H 100%, 1D 100% | **holds** |  |
| 5 | pair LaRSI with a trend filter: TSI > 0 (F3) beats no filter in most pairs | Gold (XAUUSDm) | 4/12 | 3/12 | **does not hold** |  |
| 5 | pair LaRSI with a trend filter: TSI > 0 (F3) beats no filter in most pairs | BTC (BTCUSDm) | 10/12 | 5/12 | **mixed** |  |
| 5 | pair LaRSI with a trend filter: MA200 (F1, F2) beats no filter in most pairs | Gold (XAUUSDm) | 1/24 | 13/24 | **mixed** |  |
| 5 | pair LaRSI with a trend filter: MA200 (F1, F2) beats no filter in most pairs | BTC (BTCUSDm) | 18/24 | 15/24 | **holds** |  |
| 6 | the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0) | Gold (XAUUSDm) | 1H 60%, 4H 69%, 1D 56% | 1H 75%, 4H 81%, 1D 69% | **does not hold** |  |
| 6 | the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0) | BTC (BTCUSDm) | 1H 8%, 4H 81%, 1D 88% | 1H 44%, 4H 76%, 1D 91% | **holds** |  |
| 6 | on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row) | Gold (XAUUSDm) | 1H +733, 4H +543, 1D +1,330 | 1H +353, 4H +419, 1D +525 | **mixed** |  |
| 6 | on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row) | BTC (BTCUSDm) | 1H +142, 4H +517, 1D +734 | 1H +188, 4H +365, 1D +404 | **holds** |  |

## Files

`grid.csv`, `results_dev_val.csv` (one row per variant and window; `_x15` = x1.5 costs), `trades_dev_val.csv.gz`, `quarters_dev_val.csv`, `weekly_dev_val.csv.gz`, `buy_and_hold.csv`, `state_checks.csv`, `run_info.csv`, `qualification.csv`, `vs_rsi.csv`, `vs_rsi_summary.csv`, `multiple_testing.csv`, `vs_buy_and_hold.csv`, `exam_rule_rates.csv`, `runners_up.csv`, `curves.csv`, `vs_f0.csv`, `vs_f0_summary.csv`, `claims.csv`.
