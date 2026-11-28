# TradeIQ's RSI replacements: the finalists (frozen)

Written by `python -B -m backtesting.research.tradeiq freeze` on 27 Nov 2026 23:47 UTC. Until this file and its sha256 (`FINALISTS.md.sha256`) existed, the guard of `tradeiq_market.py` served no data from 2024-07-01 00:00 UTC on, so no result of the hold-out existed when the finalists below were chosen. The file is written once: `freeze` refuses to write it again, and the guard closes the hold-out again if its sha256 stops matching.

The rule (PREREG 7, DEVIATIONS 23-24): a variant qualifies when (1) its Development net profit is above 0 at x1.0 and at x1.5 costs, (2) it has at least 30 Development trades (1H, 4H) or 15 (1D), (3) its Development profit / max drawdown is at least 1.0 with at least 50% of the quarters positive, and (4) its Validation net profit is above 0 at x1.0. The finalists of a symbol are its three qualifiers with the highest profit / max drawdown over Development + Validation together (one continuous run, 2019-01-01 to 2024-06-30, x1.0), at most one per indicator (RSI, LaRSI, VWRSI with its Binance-volume rows, TSI, QQE, MA200 alone); ties by Development's profit / max drawdown, then by the id. The finalists were recomputed from `results_dev_val.csv` by this command and are those of `qualification.csv` and `CANDIDATES.md`.

## The finalists

The exam (`python -B -m backtesting.research.tradeiq exam`) reads its variants from this block, one id per line (symbol | timeframe | indicator | family | filter | stop):

```text
XAUUSDm|1H|QQE|R2|F2-4H|S0
XAUUSDm|1H|LaRSI|R2|F1|S0
XAUUSDm|4H|RSI|R2|F1|S0
BTCUSDm|1D|LaRSI|R2|F3|S1
BTCUSDm|1D|VWRSI|R3|F0|S1
BTCUSDm|4H|TSI|R2|F1|S0
```

### Gold (XAUUSDm): 3 finalists (44 qualifiers)

| # | Rank | Variant | Indicator | TF | Family | Filter | Stop |
|---|---|---|---|---|---|---|---|
| 1 | 1 | `XAUUSDm|1H|QQE|R2|F2-4H|S0` | QQE | 1H | R2 | F2-4H | S0 |
| 2 | 2 | `XAUUSDm|1H|LaRSI|R2|F1|S0` | LaRSI | 1H | R2 | F1 | S0 |
| 3 | 4 | `XAUUSDm|4H|RSI|R2|F1|S0` | RSI | 4H | R2 | F1 | S0 |

The rule rows:

1. `XAUUSDm|1H|QQE|R2|F2-4H|S0`: 1-hour bars of the bid (UTC); QQE MOD (RSI 6, smoothing 5, factors 3.0 / 1.61, threshold 3, Bollinger 50 x 0.35): long after a BLUE bar, held through GRAY bars, flat after a RED bar (long only); BLUE = secondary RSI - 50 > 3 and primary RSI - 50 above the upper band, RED the mirror, GRAY neither; filter: a long only while the last CLOSED 4-hour bar closed above its 200-bar SMA, a short only below it; stop: no stop: exits by the rule only. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).
2. `XAUUSDm|1H|LaRSI|R2|F1|S0`: 1-hour bars of the bid (UTC); long while the 100 x Laguerre RSI (alpha 0.2) of the close is above 50, flat while below (long only); filter: a long only while the bar closed above its 200-bar SMA, a short only below it; stop: no stop: exits by the rule only. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).
3. `XAUUSDm|4H|RSI|R2|F1|S0`: 4-hour bars of the bid (UTC); long while the RSI(14) of the close is above 50, flat while below (long only); filter: a long only while the bar closed above its 200-bar SMA, a short only below it; stop: no stop: exits by the rule only. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).

Development, 2019-01-01 to 2022-12-31 (per 0.01 lot after costs):

| # | Variant | Net x1.0 | Net x1.5 | Trades | Max DD | Profit / DD | Positive quarters | Win rate | Profit factor | Weekly Sharpe (ann.) | Time in market |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|QQE|R2|F2-4H|S0` | +458 | +399 | 348 | 163 | 2.82 | 11/16 | 34% | 1.31 | 0.87 | 30% |
| 2 | `1H|LaRSI|R2|F1|S0` | +436 | +374 | 378 | 180 | 2.41 | 13/16 | 25% | 1.30 | 0.79 | 41% |
| 3 | `4H|RSI|R2|F1|S0` | +368 | +330 | 235 | 203 | 1.82 | 9/16 | 24% | 1.33 | 0.59 | 39% |

Validation, 2023-01-01 to 2024-06-30, and Development + Validation as one run:

| # | Variant | Val net x1.0 | Val net x1.5 | Val trades | Val max DD | Val profit / DD | Val positive quarters | D+V net | D+V max DD | D+V profit / DD (the ranking) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|QQE|R2|F2-4H|S0` | +224 | +209 | 137 | 198 | 1.13 | 5/6 | +688 | 198 | 3.4840 |
| 2 | `1H|LaRSI|R2|F1|S0` | +228 | +214 | 132 | 200 | 1.14 | 4/6 | +670 | 200 | 3.3488 |
| 3 | `4H|RSI|R2|F1|S0` | +270 | +261 | 81 | 215 | 1.26 | 4/6 | +644 | 215 | 2.9998 |

### BTC (BTCUSDm): 3 finalists (59 qualifiers)

| # | Rank | Variant | Indicator | TF | Family | Filter | Stop |
|---|---|---|---|---|---|---|---|
| 1 | 1 | `BTCUSDm|1D|LaRSI|R2|F3|S1` | LaRSI | 1D | R2 | F3 | S1 |
| 2 | 3 | `BTCUSDm|1D|VWRSI|R3|F0|S1` | VWRSI | 1D | R3 | F0 | S1 |
| 3 | 11 | `BTCUSDm|4H|TSI|R2|F1|S0` | TSI | 4H | R2 | F1 | S0 |

The rule rows:

1. `BTCUSDm|1D|LaRSI|R2|F3|S1`: daily bars of the bid (UTC); long while the 100 x Laguerre RSI (alpha 0.2) of the close is above 50, flat while below (long only); filter: a long only while the TSI (5 / 25) of the bar is above 0, a short only below it; stop: a stop 3 x ATR(14) of the signal timeframe from the entry fill, never moved (one extra spread on a stop fill); after a stop, flat until the state changes. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).
2. `BTCUSDm|1D|VWRSI|R3|F0|S1`: daily bars of the bid (UTC); flat while the consolidation score (length 10) of the volume-weighted RSI (AlgoAlpha, 14) on the bar's tick volume is above 0; otherwise long while the line is above 50, short while below; filter: no filter; stop: a stop 3 x ATR(14) of the signal timeframe from the entry fill, never moved (one extra spread on a stop fill); after a stop, flat until the state changes. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).
3. `BTCUSDm|4H|TSI|R2|F1|S0`: 4-hour bars of the bid (UTC); long while the Bjorgum TSI x 100 (speed Fast: 5 / 25) is above 0, flat while below (long only); filter: a long only while the bar closed above its 200-bar SMA, a short only below it; stop: no stop: exits by the rule only. Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).

Development, 2019-01-01 to 2022-12-31 (per 0.01 lot after costs):

| # | Variant | Net x1.0 | Net x1.5 | Trades | Max DD | Profit / DD | Positive quarters | Win rate | Profit factor | Weekly Sharpe (ann.) | Time in market |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|LaRSI|R2|F3|S1` | +404 | +397 | 26 | 171 | 2.36 | 9/16 | 42% | 3.90 | 0.67 | 46% |
| 2 | `1D|VWRSI|R3|F0|S1` | +473 | +463 | 54 | 174 | 2.72 | 10/16 | 50% | 2.52 | 0.87 | 40% |
| 3 | `4H|TSI|R2|F1|S0` | +294 | +263 | 178 | 192 | 1.53 | 10/16 | 26% | 1.40 | 0.51 | 39% |

Validation, 2023-01-01 to 2024-06-30, and Development + Validation as one run:

| # | Variant | Val net x1.0 | Val net x1.5 | Val trades | Val max DD | Val profit / DD | Val positive quarters | D+V net | D+V max DD | D+V profit / DD (the ranking) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|LaRSI|R2|F3|S1` | +264 | +262 | 10 | 151 | 1.74 | 3/6 | +668 | 181 | 3.6970 |
| 2 | `1D|VWRSI|R3|F0|S1` | +117 | +114 | 22 | 122 | 0.96 | 5/6 | +590 | 174 | 3.3864 |
| 3 | `4H|TSI|R2|F1|S0` | +261 | +251 | 68 | 138 | 1.90 | 4/6 | +556 | 192 | 2.8930 |

## The exam (PREREG 8)

Each finalist is run over the hold-out, Gold (XAUUSDm) 2024-07-01 00:00 to 2026-11-26 00:00 UTC (exclusive); BTC (BTCUSDm) 2024-07-01 00:00 to 2026-11-27 00:00 UTC (exclusive) (the data end, `DATA.md`), as one continuous run that starts flat at its first bar (DEVIATIONS 2, 7), at x1.0 and x1.5 costs. **It passes when its hold-out net profit is above 0 at x1.0 and its profit / max drawdown is at least 0.5** (DEVIATIONS 33). The result is reported next to buy-and-hold of 0.01 lot over the same span (DEVIATIONS 28).

## The selection's inputs and the code

The sha256 of the files the finalists were read from:

| File | sha256 |
|---|---|
| `results_dev_val.csv` | `1e4b2dcd70d12ab995205d15ca6273287d270618122873a17c5c643602d70ba3` |
| `qualification.csv` | `f68966c0bd8c70bb78f33e04edeee7d3ac026d111130c7360e4c784606973f6a` |
| `run_info.csv` | `f98e08e444ebf031b4cf64bbf62c5de0401ca5bc33c8870cb9c22a9e9f0e077b` |
| `CANDIDATES.md` | `fd686f5bb3c7ef46a27e7b2f015e6d7a0a6b53917e934c663abb35ba9a75d187` |

The code (git blob ids, `git hash-object`). `run_info.csv` records the code that wrote `results_dev_val.csv` (written 2026-11-27 23:44:50+00:00): it is the code below, and it is the code that computes the hold-out.

```text
blob tradeiq.py d0ad7f06a2268eb14d99d78965edc789a3aba125
blob tradeiq_ind.py 2a6483a415eb50b9b5e067fe899f4922e085ce9f
blob tradeiq_market.py dc784854b60c0bcb4b01b189b8a7cd5516267b04
blob external.py 5f037a44b07e954cd0a857e677914eec42205c90
blob silver.py cbc46c58add01afb7eea6dc3737cba3649b87d1b
```

| File | Blob id now | Equal to run_info.csv |
|---|---|---|
| tradeiq.py | `d0ad7f06a2268eb14d99d78965edc789a3aba125` | yes |
| tradeiq_ind.py | `2a6483a415eb50b9b5e067fe899f4922e085ce9f` | yes |
| tradeiq_market.py | `dc784854b60c0bcb4b01b189b8a7cd5516267b04` | yes |
| external.py | `5f037a44b07e954cd0a857e677914eec42205c90` | yes |
| silver.py | `cbc46c58add01afb7eea6dc3737cba3649b87d1b` | yes |
