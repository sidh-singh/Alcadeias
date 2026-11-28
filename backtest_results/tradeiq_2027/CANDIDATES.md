# TradeIQ's 9 indicators for 2027: the candidates after Development and Validation

Written by `python -B -m backtesting.research.tradeiq2 select` on 28 Nov 2026 14:37 UTC from the CSVs of `run` (written 2026-11-28 14:37:19+00:00). **This is not `FINALISTS.md`.** Nothing is frozen, and no result of the hold-out (from 2024-07-01) or of gold's Early window (2017-2018) exists: the guard of `tradeiq2_market.py` served the data only up to 2024-06-30 23:59 UTC. The would-be champions and finalists below are what PREREG section 7's rule gives; they become champions and finalists only when `FINALISTS.md` and its sha256 are written (`freeze`). The same text, as it would be frozen, is `FINALISTS.draft.md`.

Per 0.01 lot after Exness costs (the spread at every fill, one extra spread on every stop fill). Development 2019-01-01 to 2022-12-31, Validation 2023-01-01 to 2024-06-30, D+V the two together as one continuous run (the claim markets' Development starts as PREREG 3 says). Profit / DD = net profit / max drawdown on equity marked at M1 extremes.

## What was run

| Symbol | Variants | Eligible | Not eligible / information | M1 data served | M1 bars | Runs (3 windows x 2 costs) |
|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | 775 | 738 | 37 | 2016-01-03 .. 2024-07-01 00:00 | 2,978,668 | 4650 |
| BTC (BTCUSDm) | 762 | 720 | 42 | 2018-01-01 .. 2024-07-01 00:00 | 3,403,835 | 4572 |
| Nasdaq (USTECm) | 4 | 0 | 4 | 2020-06-01 .. 2024-07-01 00:00 | 1,370,640 | 24 |
| EURUSD (EURUSDm) | 1 | 0 | 1 | 2017-11-01 .. 2024-07-01 00:00 | 2,435,066 | 6 |
| GBPUSD (GBPUSDm) | 1 | 0 | 1 | 2017-11-01 .. 2024-07-01 00:00 | 2,450,322 | 6 |

Code that wrote the CSVs (git blob ids, `run_info.csv`): `tradeiq2.py` 0d2ca9519506, `tradeiq2_market.py` 985bdb991d80, `tradeiq2_filters.py` 6b148d5bc069, `tradeiq_market.py` dc784854b60c, `tradeiq_ind.py` 2a6483a415eb, `tradeiq.py` d0ad7f06a226, `external.py` 5f037a44b07e, `balke.py` c7e86b6febce, `config.py` 5585bf412626, `store.py` 3dda14c5133e, `tradeiq2_ind_coil.py` 2d734f1864c5, `tradeiq2_ind_ha.py` e9d1844fdbfd, `tradeiq2_ind_msd.py` 6dc2ce35e979, `tradeiq2_ind_orb.py` bd506a18fb26, `tradeiq2_ind_patterns.py` a49132d15c8a, `tradeiq2_ind_ribbon.py` 100379b349c9, `tradeiq2_ind_session.py` 34a52bfbdf25, `tradeiq2_ind_swing.py` 8c80fa218caf, `tradeiq2_ind_wyckoff.py` 78c9b467ab17, `tradeiq2_rules_ribbon.py` c51009eac671, `tradeiq2_rules_msd.py` f5b9f1ace19c, `tradeiq2_rules_wyckoff.py` a3c8540110a7, `tradeiq2_rules_swing.py` 7f715e2a4e90, `tradeiq2_rules_orb.py` f0d0be92db9a, `tradeiq2_rules_session.py` 863d1c978503, `tradeiq2_rules_patterns.py` af576e8fa6ff, `tradeiq2_rules_ha.py` 8863ff0c752e, `tradeiq2_rules_coil.py` d0733293c4bc, `silver.py` cbc46c58add0, `final10.py` 5e675ee0774e.

## Headline

| Symbol | Variants | Eligible | Dev net > 0 | Val net > 0 | Both > 0 | Rule 1 | Rules 1-2 | Rules 1-3 | Qualify (1-4) | Champions | Would-be finalists |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | 775 | 738 | 356 | 475 | 245 | 288 | 248 | 83 | 65 | 11 | 3 |
| BTC (BTCUSDm) | 762 | 720 | 259 | 503 | 226 | 224 | 194 | 41 | 36 | 6 | 3 |

Rules 1-3 and the net counts are over the eligible rows. Rule 1: Development net > 0 at x1.0 and x1.5; 2: the minimum of Development trades (PREREG 5); 3: Development P/DD >= 1.0 with at least 50% of the quarters positive; 4: Validation net > 0 at x1.0.

### Gold (XAUUSDm) by family

| Family | Script group | Variants | Eligible | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Would-be champion | Its D+V P/DD |
|---|---|---|---|---|---|---|---|---|---|
| RIB | RIB | 139 | 136 | 95 | 105 | 19 | +79 | `1H|RIB|LO|X0|F2-4H` | 4.61 |
| ALMA-X | RIB | 6 | 6 | 2 | 4 | 1 | -55 | `4H|ALMA-X|LO|X0|F0` | 1.80 |
| MSD-ALONE | MSD | 18 | 18 | 14 | 9 | 1 | +216 | `1H|MSD-ALONE|MSD-A2|S0` | 0.94 |
| MSD-FILTER | MSD | 120 | 120 | 90 | 63 | 12 | +116 | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | 2.30 |
| BOS | MSD | 12 | 12 | 9 | 12 | 0 | +19 | none | - |
| WY | WY | 36 | 36 | 12 | 20 | 0 | +0.00 | none | - |
| WY-DERIVED | WY | 18 | 18 | 3 | 8 | 1 | -11 | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | 1.37 |
| SP | SP | 36 | 24 | 6 | 10 | 2 | -57 | `4H|SP|W2|POC|LO` | 2.76 |
| ORB | ORB | 82 | 72 | 21 | 65 | 1 | -26 | `M5|ORB|O3|HV+F2-4H` | 1.30 |
| SH | SH | 118 | 116 | 11 | 59 | 0 | -151 | none | - |
| HP-HARMONIC | HP | 36 | 30 | 5 | 11 | 0 | -152 | none | - |
| HP-CHART | HP | 22 | 18 | 9 | 12 | 0 | -22 | none | - |
| HA-ENTRY | HA | 24 | 24 | 7 | 16 | 1 | -103 | `1D|HA-ENTRY|HA-H2|LO|F0` | 1.98 |
| HA-MANAGED | HA | 54 | 54 | 41 | 46 | 16 | +150 | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | 3.76 |
| COIL | COIL | 36 | 36 | 20 | 25 | 6 | +17 | `1H|COIL|COIL-RIB|X-3R|VOL` | 4.11 |
| STK | STK | 18 | 18 | 11 | 10 | 5 | +47 | `1H|STK|STK-RA|LO|S1` | 3.81 |

Gold (XAUUSDm) by timeframe (eligible rows):

| TF | Variants | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Median val net |
|---|---|---|---|---|---|---|
| M5 | 94 | 16 | 60 | 1 | -119 | +28 |
| M15 | 94 | 16 | 64 | 0 | -98 | +47 |
| 1H | 207 | 121 | 151 | 50 | +62 | +63 |
| 4H | 193 | 119 | 116 | 10 | +43 | +20 |
| 1D | 150 | 84 | 84 | 4 | +38 | +59 |

### BTC (BTCUSDm) by family

| Family | Script group | Variants | Eligible | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Would-be champion | Its D+V P/DD |
|---|---|---|---|---|---|---|---|---|---|
| RIB | RIB | 139 | 136 | 79 | 119 | 3 | +43 | `4H|RIB|LS|XBE|F1` | 2.07 |
| ALMA-X | RIB | 6 | 6 | 2 | 2 | 0 | -237 | none | - |
| MSD-ALONE | MSD | 18 | 18 | 8 | 16 | 0 | -35 | none | - |
| MSD-FILTER | MSD | 120 | 120 | 67 | 97 | 17 | +59 | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | 3.75 |
| BOS | MSD | 12 | 12 | 7 | 10 | 3 | +105 | `4H|BOS|BOS-trend|LO|F1|S1` | 2.60 |
| WY | WY | 39 | 36 | 8 | 4 | 0 | +0.00 | none | - |
| WY-DERIVED | WY | 18 | 18 | 6 | 13 | 0 | -0.84 | none | - |
| SP | SP | 36 | 24 | 11 | 7 | 2 | -11 | `4H|SP|W2|POC|F2-1D` | 2.39 |
| ORB | ORB | 66 | 54 | 2 | 50 | 0 | -258 | none | - |
| SH | SH | 118 | 116 | 0 | 72 | 0 | -199 | none | - |
| HP-HARMONIC | HP | 36 | 30 | 4 | 8 | 0 | -159 | none | - |
| HP-CHART | HP | 22 | 18 | 9 | 9 | 0 | -4.76 | none | - |
| HA-ENTRY | HA | 24 | 24 | 3 | 14 | 0 | -236 | none | - |
| HA-MANAGED | HA | 54 | 54 | 30 | 42 | 10 | +50 | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | 4.32 |
| COIL | COIL | 36 | 36 | 16 | 22 | 1 | -12 | `1D|COIL|COIL-RIB|X-3R|none` | 3.37 |
| STK | STK | 18 | 18 | 7 | 18 | 0 | -22 | none | - |

BTC (BTCUSDm) by timeframe (eligible rows):

| TF | Variants | Dev net > 0 | Val net > 0 | Qualify | Median dev net | Median val net |
|---|---|---|---|---|---|---|
| M5 | 85 | 0 | 57 | 0 | -246 | +28 |
| M15 | 85 | 2 | 65 | 0 | -176 | +37 |
| 1H | 195 | 38 | 109 | 1 | -179 | +13 |
| 4H | 193 | 112 | 144 | 9 | +31 | +84 |
| 1D | 162 | 107 | 128 | 26 | +107 | +156 |

## Buy-and-hold of 0.01 lot, for reference

| Symbol | Window | Net x1.0 | Net x1.5 | Max DD | Profit / DD |
|---|---|---|---|---|---|
| Gold (XAUUSDm) | Development | +542 | +542 | 459 | 1.18 |
| Gold (XAUUSDm) | Validation | +498 | +497 | 264 | 1.88 |
| Gold (XAUUSDm) | D+V | +1,043 | +1,043 | 459 | 2.27 |
| BTC (BTCUSDm) | Development | +128 | +128 | 535 | 0.24 |
| BTC (BTCUSDm) | Validation | +462 | +462 | 171 | 2.69 |
| BTC (BTCUSDm) | D+V | +590 | +590 | 535 | 1.10 |
| Nasdaq (USTECm) | Development | +7.92 | +7.90 | 63 | 0.13 |
| Nasdaq (USTECm) | Validation | +88 | +88 | 19 | 4.67 |
| Nasdaq (USTECm) | D+V | +96 | +96 | 63 | 1.51 |
| EURUSD (EURUSDm) | Development | -76 | -76 | 281 | -0.27 |
| EURUSD (EURUSDm) | Validation | +1.73 | +0.23 | 83 | 0.02 |
| EURUSD (EURUSDm) | D+V | -73 | -73 | 281 | -0.26 |
| GBPUSD (GBPUSDm) | Development | -66 | -66 | 389 | -0.17 |
| GBPUSD (GBPUSDm) | Validation | +54 | +53 | 110 | 0.49 |
| GBPUSD (GBPUSDm) | D+V | -11 | -11 | 389 | -0.03 |

## Gold (XAUUSDm): the would-be champions and finalists

| # | Rank | Family | Group | Champion | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V net | D+V DD | D+V P/DD | Would-be finalist | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | RIB | RIB | `1H|RIB|LO|X0|F2-4H` | +619 | +580 | 207 | 3.49 | 75% | +261 | +907 | 197 | 4.6106 | **finalist** |  |
| 2 | 2 | COIL | COIL | `1H|COIL|COIL-RIB|X-3R|VOL` | +367 | +352 | 94 | 3.89 | 69% | +172 | +539 | 131 | 4.1123 | **finalist** |  |
| 3 | 4 | STK | STK | `1H|STK|STK-RA|LO|S1` | +504 | +450 | 278 | 2.43 | 62% | +279 | +790 | 207 | 3.8092 | **finalist** |  |
| 4 | 5 | HA-MANAGED | HA | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | +346 | +305 | 235 | 2.28 | 75% | +219 | +572 | 152 | 3.7611 |  |  |
| 5 | 12 | SP | SP | `4H|SP|W2|POC|LO` | +220 | +175 | 31 | 2.13 | 69% | +65 | +285 | 103 | 2.7561 |  |  |
| 6 | 24 | MSD-FILTER | MSD | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | +388 | +301 | 592 | 1.38 | 62% | +251 | +645 | 281 | 2.2985 |  |  |
| 7 | 36 | HA-ENTRY | HA | `1D|HA-ENTRY|HA-H2|LO|F0` | +310 | +291 | 130 | 1.06 | 56% | +166 | +580 | 293 | 1.9777 |  |  |
| 8 | 44 | ALMA-X | RIB | `4H|ALMA-X|LO|X0|F0` | +266 | +195 | 458 | 1.05 | 56% | +205 | +494 | 275 | 1.8006 |  |  |
| 9 | 52 | WY-DERIVED | WY | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | +145 | +103 | 157 | 1.24 | 56% | +15 | +160 | 117 | 1.3682 |  |  |
| 10 | 55 | ORB | ORB | `M5|ORB|O3|HV+F2-4H` | +126 | +37 | 362 | 1.24 | 56% | +6.18 | +132 | 101 | 1.3035 |  |  |
| 11 | 64 | MSD-ALONE | MSD | `1H|MSD-ALONE|MSD-A2|S0` | +456 | +378 | 541 | 1.75 | 75% | +32 | +488 | 521 | 0.9364 |  |  |

Families with no qualifier: BOS, WY, SH, HP-HARMONIC, HP-CHART.

Gold (XAUUSDm): the qualifiers, 65 in all (the first 30 by rank; every row is in `qualification.csv`):

| Rank | Variant | Family | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V P/DD | Champion |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1H|RIB|LO|X0|F2-4H` | RIB | +619 | +580 | 207 | 3.49 | 75% | +261 | 4.61 | yes |
| 2 | `1H|COIL|COIL-RIB|X-3R|VOL` | COIL | +367 | +352 | 94 | 3.89 | 69% | +172 | 4.11 | yes |
| 3 | `1H|RIB|LO|XBE|F2-4H` | RIB | +578 | +535 | 207 | 3.24 | 75% | +150 | 3.90 |  |
| 4 | `1H|STK|STK-RA|LO|S1` | STK | +504 | +450 | 278 | 2.43 | 62% | +279 | 3.81 | yes |
| 5 | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | HA-MANAGED | +346 | +305 | 235 | 2.28 | 75% | +219 | 3.76 | yes |
| 6 | `1H|HA-MANAGED|HA-AND|QQE-R2-F2-4H-S0` | HA-MANAGED | +476 | +417 | 345 | 2.93 | 69% | +226 | 3.59 |  |
| 7 | `1H|RIB|LO|XP|F2-4H` | RIB | +440 | +405 | 207 | 3.38 | 75% | +176 | 3.44 |  |
| 8 | `1H|HA-MANAGED|M3|LaRSI-R2-F1-S0` | HA-MANAGED | +421 | +355 | 378 | 2.08 | 69% | +210 | 3.15 |  |
| 9 | `1H|HA-MANAGED|M3|QQE-R2-F2-4H-S0` | HA-MANAGED | +410 | +348 | 348 | 2.06 | 69% | +198 | 3.08 |  |
| 10 | `1H|COIL|COIL-RIB|X-3R|ADX` | COIL | +589 | +554 | 155 | 3.59 | 69% | +91 | 3.02 |  |
| 11 | `4H|HA-MANAGED|M3|RSI-R2-F1-S0` | HA-MANAGED | +316 | +276 | 235 | 1.75 | 50% | +305 | 2.83 |  |
| 12 | `4H|SP|W2|POC|LO` | SP | +220 | +175 | 31 | 2.13 | 69% | +65 | 2.76 | yes |
| 13 | `1H|COIL|COIL-RIB|X-3R|ALL3` | COIL | +261 | +253 | 48 | 2.01 | 50% | +142 | 2.69 |  |
| 14 | `1H|STK|STK-RM|LO|S1` | STK | +460 | +386 | 424 | 2.50 | 62% | +185 | 2.67 |  |
| 15 | `1H|RIB|LO|X0|F3` | RIB | +458 | +392 | 377 | 1.61 | 75% | +270 | 2.64 |  |
| 16 | `1H|HA-MANAGED|M4|QQE-R2-F2-4H-S0` | HA-MANAGED | +266 | +207 | 348 | 1.85 | 56% | +271 | 2.63 |  |
| 17 | `1H|STK|STK-RMA|LO|S1` | STK | +392 | +333 | 290 | 2.84 | 56% | +150 | 2.56 |  |
| 18 | `1H|RIB|LS|X0|F3` | RIB | +568 | +390 | 752 | 2.16 | 69% | +196 | 2.54 |  |
| 19 | `1H|COIL|COIL-RIB|X-TR|ADX` | COIL | +668 | +639 | 153 | 3.58 | 56% | +33 | 2.53 |  |
| 20 | `4H|HA-MANAGED|M4|RSI-R2-F1-S0` | HA-MANAGED | +323 | +284 | 235 | 1.86 | 56% | +104 | 2.48 |  |
| 21 | `1H|HA-MANAGED|M3|RIB-LS-X0-F0` | HA-MANAGED | +622 | +388 | 858 | 1.95 | 56% | +138 | 2.45 |  |
| 22 | `1H|RIB|LS|X0|F0` | RIB | +613 | +417 | 858 | 1.86 | 62% | +206 | 2.39 |  |
| 23 | `1H|HA-MANAGED|HA-AND|RIB-LS-X0-F0` | HA-MANAGED | +596 | +402 | 845 | 1.66 | 62% | +212 | 2.32 |  |
| 24 | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | MSD-FILTER | +388 | +301 | 592 | 1.38 | 62% | +251 | 2.30 | yes |
| 25 | `1H|HA-MANAGED|M2|QQE-R2-F2-4H-S0` | HA-MANAGED | +226 | +154 | 348 | 1.34 | 50% | +252 | 2.22 |  |
| 26 | `1H|RIB|LS|X0|FS` | RIB | +398 | +356 | 222 | 2.72 | 75% | +48 | 2.16 |  |
| 27 | `1H|MSD-FILTER|MSD-F6|LaRSI|R2|S0` | MSD-FILTER | +558 | +495 | 400 | 1.58 | 75% | +200 | 2.16 |  |
| 28 | `1H|RIB|LO|X0|FS` | RIB | +292 | +260 | 144 | 1.60 | 50% | +119 | 2.16 |  |
| 29 | `4H|MSD-FILTER|MSD-F6|TSI|R2|S0` | MSD-FILTER | +304 | +274 | 214 | 1.01 | 62% | +337 | 2.14 |  |
| 30 | `1H|HA-MANAGED|HA-AND|RIB-LO-X0-F0` | HA-MANAGED | +477 | +403 | 422 | 1.32 | 62% | +260 | 2.12 |  |

Gold (XAUUSDm): the five best by D+V P/DD among the eligible rows that fail exactly one rule (for information; they are not candidates):

| Variant | Fails | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V P/DD |
|---|---|---|---|---|---|---|---|---|
| `1D|RIB|LO|XT2|F3` | q3 | +335 | +333 | 15 | 2.36 | 44% | +285 | 4.81 |
| `1D|RIB|LO|XT2|F0` | q3 | +261 | +259 | 17 | 1.72 | 44% | +285 | 4.00 |
| `4H|HA-MANAGED|HA-AND|RSI-R2-F1-S0` | q3 | +364 | +334 | 181 | 1.85 | 44% | +267 | 3.05 |
| `4H|HP-CHART|HP-CF|TP2|F0` | q3 | +226 | +219 | 42 | 2.27 | 44% | +76 | 3.03 |
| `1D|RIB|LO|XP|F3` | q3 | +293 | +291 | 15 | 1.35 | 44% | +306 | 3.00 |

Gold (XAUUSDm): 47 Wyckoff rows have fewer than 15 Development trades: their verdict is "insufficient events" (PREREG 6.3).

## BTC (BTCUSDm): the would-be champions and finalists

| # | Rank | Family | Group | Champion | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V net | D+V DD | D+V P/DD | Would-be finalist | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | HA-MANAGED | HA | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | +425 | +419 | 23 | 2.78 | 56% | +264 | +689 | 159 | 4.3244 | **finalist** |  |
| 2 | 2 | MSD-FILTER | MSD | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | +724 | +708 | 72 | 3.43 | 62% | +137 | +857 | 229 | 3.7508 | **finalist** |  |
| 3 | 4 | COIL | COIL | `1D|COIL|COIL-RIB|X-3R|none` | +592 | +589 | 18 | 3.23 | 75% | +25 | +617 | 183 | 3.3679 | **finalist** |  |
| 4 | 17 | BOS | MSD | `4H|BOS|BOS-trend|LO|F1|S1` | +236 | +213 | 118 | 1.01 | 50% | +370 | +607 | 233 | 2.5993 |  |  |
| 5 | 21 | SP | SP | `4H|SP|W2|POC|F2-1D` | +176 | +99 | 38 | 1.83 | 56% | +57 | +233 | 98 | 2.3923 |  |  |
| 6 | 30 | RIB | RIB | `4H|RIB|LS|XBE|F1` | +357 | +320 | 172 | 1.38 | 56% | +234 | +590 | 284 | 2.0748 |  |  |

Families with no qualifier: ALMA-X, MSD-ALONE, WY, WY-DERIVED, ORB, SH, HP-HARMONIC, HP-CHART, HA-ENTRY, STK.

BTC (BTCUSDm): the qualifiers, 36 in all (the first 30 by rank; every row is in `qualification.csv`):

| Rank | Variant | Family | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V P/DD | Champion |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | HA-MANAGED | +425 | +419 | 23 | 2.78 | 56% | +264 | 4.32 | yes |
| 2 | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | MSD-FILTER | +724 | +708 | 72 | 3.43 | 62% | +137 | 3.75 | yes |
| 3 | `1D|HA-MANAGED|M3|LaRSI-R2-F3-S1` | HA-MANAGED | +349 | +342 | 26 | 2.04 | 50% | +311 | 3.65 |  |
| 4 | `1D|COIL|COIL-RIB|X-3R|none` | COIL | +592 | +589 | 18 | 3.23 | 75% | +25 | 3.37 | yes |
| 5 | `1D|HA-MANAGED|M2|VWRSI-R3-F0-S1` | HA-MANAGED | +513 | +503 | 54 | 2.95 | 56% | +71 | 3.35 |  |
| 6 | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S0` | MSD-FILTER | +671 | +656 | 72 | 3.18 | 62% | +107 | 3.20 |  |
| 7 | `1D|HA-MANAGED|M3|VWRSI-R3-F0-S1` | HA-MANAGED | +449 | +439 | 54 | 2.58 | 62% | +108 | 3.19 |  |
| 8 | `1D|HA-MANAGED|M4|VWRSI-R3-F0-S1` | HA-MANAGED | +380 | +370 | 54 | 2.18 | 62% | +151 | 3.04 |  |
| 9 | `1D|HA-MANAGED|M5|RIB-LS-X0-F0` | HA-MANAGED | +252 | +242 | 49 | 1.70 | 56% | +175 | 2.89 |  |
| 10 | `4H|HA-MANAGED|HA-AND|TSI-R2-F1-S0` | HA-MANAGED | +335 | +308 | 158 | 1.82 | 62% | +196 | 2.88 |  |
| 11 | `1D|MSD-FILTER|MSD-F6|VWRSI-RV|R1|S0` | MSD-FILTER | +755 | +732 | 126 | 3.37 | 62% | +68 | 2.77 |  |
| 12 | `1D|MSD-FILTER|MSD-F6|TSI|R2|S1` | MSD-FILTER | +342 | +337 | 38 | 1.40 | 50% | +333 | 2.76 |  |
| 13 | `1D|MSD-FILTER|MSD-F6|TSI|R2|S0` | MSD-FILTER | +342 | +336 | 38 | 1.40 | 50% | +333 | 2.76 |  |
| 14 | `1D|MSD-FILTER|MSD-F6|VWRSI-RV|R1|S1` | MSD-FILTER | +757 | +734 | 126 | 3.38 | 62% | +55 | 2.74 |  |
| 15 | `4H|HA-MANAGED|M3|TSI-R2-F1-S0` | HA-MANAGED | +317 | +285 | 178 | 1.54 | 62% | +239 | 2.71 |  |
| 16 | `1D|MSD-FILTER|MSD-F4|LaRSI|R2|S1` | MSD-FILTER | +327 | +321 | 46 | 1.58 | 50% | +234 | 2.63 |  |
| 17 | `4H|BOS|BOS-trend|LO|F1|S1` | BOS | +236 | +213 | 118 | 1.01 | 50% | +370 | 2.60 | yes |
| 18 | `1D|MSD-FILTER|MSD-F4|LaRSI|R2|S0` | MSD-FILTER | +324 | +317 | 46 | 1.45 | 50% | +234 | 2.50 |  |
| 19 | `4H|MSD-FILTER|MSD-F6|VWRSI-RV|R2|S0` | MSD-FILTER | +330 | +277 | 313 | 1.48 | 56% | +212 | 2.44 |  |
| 20 | `1D|MSD-FILTER|MSD-F6|VWRSI-RV|R2|S0` | MSD-FILTER | +427 | +418 | 60 | 1.71 | 56% | +182 | 2.40 |  |
| 21 | `4H|SP|W2|POC|F2-1D` | SP | +176 | +99 | 38 | 1.83 | 56% | +57 | 2.39 | yes |
| 22 | `1D|MSD-FILTER|MSD-F6|VWRSI-RV|R2|S1` | MSD-FILTER | +428 | +419 | 60 | 1.77 | 56% | +169 | 2.35 |  |
| 23 | `1D|BOS|BOS-trend|LO|F0|S1` | BOS | +331 | +327 | 15 | 1.12 | 62% | +364 | 2.35 |  |
| 24 | `1D|MSD-FILTER|MSD-F6|RSI|R2|S1` | MSD-FILTER | +309 | +299 | 67 | 1.23 | 50% | +272 | 2.32 |  |
| 25 | `1D|MSD-FILTER|MSD-F6|RSI|R2|S0` | MSD-FILTER | +309 | +298 | 67 | 1.23 | 50% | +272 | 2.32 |  |
| 26 | `1D|BOS|BOS-trend|LS|F0|S1` | BOS | +536 | +529 | 31 | 1.50 | 69% | +290 | 2.30 |  |
| 27 | `1D|MSD-FILTER|MSD-F6|LaRSI|R2|S1` | MSD-FILTER | +335 | +331 | 27 | 1.22 | 50% | +283 | 2.26 |  |
| 28 | `1D|HA-MANAGED|HA-AND|VWRSI-R3-F0-S1` | HA-MANAGED | +328 | +321 | 41 | 2.11 | 69% | +13 | 2.19 |  |
| 29 | `1D|MSD-FILTER|MSD-F6|LaRSI|R2|S0` | MSD-FILTER | +331 | +326 | 27 | 1.17 | 50% | +283 | 2.18 |  |
| 30 | `4H|RIB|LS|XBE|F1` | RIB | +357 | +320 | 172 | 1.38 | 56% | +234 | 2.07 | yes |

BTC (BTCUSDm): the five best by D+V P/DD among the eligible rows that fail exactly one rule (for information; they are not candidates):

| Variant | Fails | Dev net | Dev x1.5 | Dev trades | Dev P/DD | Dev +Q | Val net | D+V P/DD |
|---|---|---|---|---|---|---|---|---|
| `1D|COIL|COIL-RIB|X-3R|ADX` | q2 | +660 | +659 | 12 | 4.31 | 56% | +42 | 4.59 |
| `1D|HA-MANAGED|M5|RIB-LO-X0-F0` | q3 | +315 | +309 | 24 | 2.81 | 31% | +161 | 4.25 |
| `M15|ORB|O1|HV+F2-4H` | q3 | +128 | +37 | 478 | 1.87 | 44% | +155 | 4.14 |
| `1D|MSD-FILTER|MSD-F6|TSI|R1|S1` | q3 | +663 | +646 | 96 | 2.65 | 44% | +210 | 3.48 |
| `1D|MSD-FILTER|MSD-F6|TSI|R1|S0` | q3 | +655 | +638 | 96 | 2.61 | 44% | +208 | 3.44 |

BTC (BTCUSDm): 46 Wyckoff rows have fewer than 15 Development trades: their verdict is "insufficient events" (PREREG 6.3).

## Multiple testing (Development weekly P/L, x1.0; PREREG 7)

| Universe | Symbol | Role | Variant | N | N (all rows) | N (eligible) | Weeks | Sharpe (ann.) | E[max] (as run) | DSR | DSR (null var.) | DSR (within-TF var.) | SPA p | Reality Check p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all variants run | Gold (XAUUSDm) | best dev Sharpe | `1H|HP-HARMONIC|HP-DRAWN|ALL|TP1|F0` | 775 | 775 | 738 | 210 | 6.67 | 2.03 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| all variants run | Gold (XAUUSDm) | would-be finalist 1 (rank 1) | `1H|RIB|LO|X0|F2-4H` | 775 | 775 | 738 | 210 | 1.17 | 2.03 | 0.029 | 0.179 | 0.054 | 0.000 | 0.000 |
| all variants run | Gold (XAUUSDm) | would-be finalist 2 (rank 2) | `1H|COIL|COIL-RIB|X-3R|VOL` | 775 | 775 | 738 | 210 | 0.86 | 2.03 | 0.004 | 0.047 | 0.009 | 0.000 | 0.000 |
| all variants run | Gold (XAUUSDm) | would-be finalist 3 (rank 4) | `1H|STK|STK-RA|LO|S1` | 775 | 775 | 738 | 210 | 0.89 | 2.03 | 0.008 | 0.069 | 0.016 | 0.000 | 0.000 |
| all variants run | BTC (BTCUSDm) | best dev Sharpe | `1H|HP-HARMONIC|HP-DRAWN|ALL|TP1|F0` | 762 | 762 | 720 | 210 | 4.50 | 2.57 | 1.000 | 1.000 | 1.000 | 0.028 | 0.001 |
| all variants run | BTC (BTCUSDm) | would-be finalist 1 (rank 1) | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | 762 | 762 | 720 | 210 | 0.74 | 2.57 | 0.000 | 0.037 | 0.006 | 0.028 | 0.001 |
| all variants run | BTC (BTCUSDm) | would-be finalist 2 (rank 2) | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | 762 | 762 | 720 | 210 | 0.89 | 2.57 | 0.000 | 0.075 | 0.015 | 0.028 | 0.001 |
| all variants run | BTC (BTCUSDm) | would-be finalist 3 (rank 4) | `1D|COIL|COIL-RIB|X-3R|none` | 762 | 762 | 720 | 210 | 0.90 | 2.57 | 0.000 | 0.070 | 0.013 | 0.028 | 0.001 |
| eligible variants | Gold (XAUUSDm) | best dev Sharpe | `1H|RIB|LO|X0|F2-4H` | 738 | 775 | 738 | 210 | 1.17 | 1.60 | 0.172 | 0.183 | 0.264 | 0.396 | 0.489 |
| eligible variants | Gold (XAUUSDm) | would-be finalist 1 (rank 1) | `1H|RIB|LO|X0|F2-4H` | 738 | 775 | 738 | 210 | 1.17 | 1.60 | 0.172 | 0.183 | 0.264 | 0.396 | 0.489 |
| eligible variants | Gold (XAUUSDm) | would-be finalist 2 (rank 2) | `1H|COIL|COIL-RIB|X-3R|VOL` | 738 | 775 | 738 | 210 | 0.86 | 1.60 | 0.045 | 0.049 | 0.085 | 0.396 | 0.489 |
| eligible variants | Gold (XAUUSDm) | would-be finalist 3 (rank 4) | `1H|STK|STK-RA|LO|S1` | 738 | 775 | 738 | 210 | 0.89 | 1.60 | 0.066 | 0.071 | 0.115 | 0.396 | 0.489 |
| eligible variants | BTC (BTCUSDm) | best dev Sharpe | `1D|COIL|COIL-RIB|X-3R|ADX` | 720 | 762 | 720 | 210 | 1.03 | 2.40 | 0.001 | 0.115 | 0.073 | 0.638 | 0.389 |
| eligible variants | BTC (BTCUSDm) | would-be finalist 1 (rank 1) | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | 720 | 762 | 720 | 210 | 0.74 | 2.40 | 0.000 | 0.038 | 0.022 | 0.638 | 0.389 |
| eligible variants | BTC (BTCUSDm) | would-be finalist 2 (rank 2) | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | 720 | 762 | 720 | 210 | 0.89 | 2.40 | 0.001 | 0.077 | 0.048 | 0.638 | 0.389 |
| eligible variants | BTC (BTCUSDm) | would-be finalist 3 (rank 4) | `1D|COIL|COIL-RIB|X-3R|none` | 720 | 762 | 720 | 210 | 0.90 | 2.40 | 0.001 | 0.072 | 0.044 | 0.638 | 0.389 |

As study 1 (its DEVIATIONS 26): the deflated Sharpe ratio for N trials with the trials' Sharpe variance as run, with the null variance and with the within-timeframe variance; SPA and the Reality Check over all N variants of the universe at once. 'All variants run' is PREREG 7's (N = every variant run on the symbol); 'eligible variants' leaves out the not-eligible and information rows (HP-DRAWN looks ahead), for information. PREREG 7 sets no threshold: information.

## The claim-check rows (PREREG 8, information only)

| Variant | Dev net | Dev trades | Dev PF | Dev avg R | Val net | Val PF |
|---|---|---|---|---|---|---|
| `USTECm|M5|SH|PRESET-NASDAQ|K2|E1` | +12 | 354 | 1.09 | 0.07 | +12 | 1.18 |
| `USTECm|M15|SH|PRESET-NASDAQ|K2|E1` | +11 | 242 | 1.10 | -0.07 | +24 | 1.56 |
| `USTECm|M5|SH|PD|HTF|E1` | +20 | 132 | 1.44 | 0.55 | +10 | 1.51 |
| `USTECm|M15|SH|PD|HTF|E1` | +16 | 120 | 1.36 | 0.58 | +9.51 | 1.63 |
| `EURUSDm|M15|SH|PRESET-FOREX|K3|E1` | -77 | 240 | 0.75 | -0.24 | +35 | 1.33 |
| `GBPUSDm|M15|SH|PRESET-FOREX|K3|E1` | +184 | 213 | 1.54 | 0.34 | +2.78 | 1.02 |

## Files

`grid.csv`, `results_dev_val.csv` (one row per variant and window; `_x15` = x1.5 costs), `trades_dev_val.csv.gz`, `quarters_dev_val.csv`, `weekly_dev_val.csv.gz`, `buy_and_hold.csv`, `run_info.csv`, `qualification.csv`, `champions.csv`, `multiple_testing.csv`, `FINALISTS.draft.md`.
