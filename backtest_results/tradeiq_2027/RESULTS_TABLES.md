# TradeIQ's 9 indicators for 2027: the tables of RESULTS.md

Written by `python -B -m backtesting.research.tradeiq2 report` on 28 Nov 2026 15:16 UTC. Per 0.01 lot after costs; Development / Validation as PREREG 3. The words of RESULTS.md are written from these.

## Counts

| Symbol | Family | Variants | Eligible | Dev > 0 | Val > 0 | Both | Rule 1 | 1-2 | 1-3 | Qualify | Champion |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | RIB | 139 | 136 | 95 | 105 | 75 | 84 | 72 | 21 | 19 | `1H|RIB|LO|X0|F2-4H` |
| Gold (XAUUSDm) | ALMA-X | 6 | 6 | 2 | 4 | 1 | 2 | 2 | 1 | 1 | `4H|ALMA-X|LO|X0|F0` |
| Gold (XAUUSDm) | MSD-ALONE | 18 | 18 | 14 | 9 | 5 | 14 | 14 | 2 | 1 | `1H|MSD-ALONE|MSD-A2|S0` |
| Gold (XAUUSDm) | MSD-FILTER | 120 | 120 | 90 | 63 | 50 | 79 | 79 | 20 | 12 | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` |
| Gold (XAUUSDm) | BOS | 12 | 12 | 9 | 12 | 9 | 5 | 4 | 0 | 0 | none |
| Gold (XAUUSDm) | WY | 36 | 36 | 12 | 20 | 12 | 12 | 0 | 0 | 0 | none |
| Gold (XAUUSDm) | WY-DERIVED | 18 | 18 | 3 | 8 | 2 | 3 | 2 | 1 | 1 | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` |
| Gold (XAUUSDm) | SP | 36 | 24 | 6 | 10 | 2 | 6 | 5 | 3 | 2 | `4H|SP|W2|POC|LO` |
| Gold (XAUUSDm) | ORB | 82 | 72 | 21 | 65 | 18 | 2 | 2 | 1 | 1 | `M5|ORB|O3|HV+F2-4H` |
| Gold (XAUUSDm) | SH | 118 | 116 | 11 | 59 | 5 | 1 | 1 | 0 | 0 | none |
| Gold (XAUUSDm) | HP-HARMONIC | 36 | 30 | 5 | 11 | 0 | 4 | 1 | 0 | 0 | none |
| Gold (XAUUSDm) | HP-CHART | 22 | 18 | 9 | 12 | 5 | 7 | 3 | 0 | 0 | none |
| Gold (XAUUSDm) | HA-ENTRY | 24 | 24 | 7 | 16 | 6 | 6 | 6 | 1 | 1 | `1D|HA-ENTRY|HA-H2|LO|F0` |
| Gold (XAUUSDm) | HA-MANAGED | 54 | 54 | 41 | 46 | 36 | 35 | 35 | 17 | 16 | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` |
| Gold (XAUUSDm) | COIL | 36 | 36 | 20 | 25 | 13 | 18 | 12 | 11 | 6 | `1H|COIL|COIL-RIB|X-3R|VOL` |
| Gold (XAUUSDm) | STK | 18 | 18 | 11 | 10 | 6 | 10 | 10 | 5 | 5 | `1H|STK|STK-RA|LO|S1` |
| BTC (BTCUSDm) | RIB | 139 | 136 | 79 | 119 | 77 | 63 | 59 | 4 | 3 | `4H|RIB|LS|XBE|F1` |
| BTC (BTCUSDm) | ALMA-X | 6 | 6 | 2 | 2 | 1 | 2 | 2 | 0 | 0 | none |
| BTC (BTCUSDm) | MSD-ALONE | 18 | 18 | 8 | 16 | 8 | 6 | 6 | 0 | 0 | none |
| BTC (BTCUSDm) | MSD-FILTER | 120 | 120 | 67 | 97 | 67 | 61 | 61 | 17 | 17 | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` |
| BTC (BTCUSDm) | BOS | 12 | 12 | 7 | 10 | 7 | 6 | 5 | 3 | 3 | `4H|BOS|BOS-trend|LO|F1|S1` |
| BTC (BTCUSDm) | WY | 39 | 36 | 8 | 4 | 0 | 8 | 0 | 0 | 0 | none |
| BTC (BTCUSDm) | WY-DERIVED | 18 | 18 | 6 | 13 | 6 | 5 | 1 | 0 | 0 | none |
| BTC (BTCUSDm) | SP | 36 | 24 | 11 | 7 | 5 | 10 | 9 | 4 | 2 | `4H|SP|W2|POC|F2-1D` |
| BTC (BTCUSDm) | ORB | 66 | 54 | 2 | 50 | 2 | 1 | 1 | 0 | 0 | none |
| BTC (BTCUSDm) | SH | 118 | 116 | 0 | 72 | 0 | 0 | 0 | 0 | 0 | none |
| BTC (BTCUSDm) | HP-HARMONIC | 36 | 30 | 4 | 8 | 0 | 2 | 1 | 0 | 0 | none |
| BTC (BTCUSDm) | HP-CHART | 22 | 18 | 9 | 9 | 7 | 8 | 3 | 0 | 0 | none |
| BTC (BTCUSDm) | HA-ENTRY | 24 | 24 | 3 | 14 | 3 | 3 | 3 | 0 | 0 | none |
| BTC (BTCUSDm) | HA-MANAGED | 54 | 54 | 30 | 42 | 26 | 30 | 30 | 10 | 10 | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` |
| BTC (BTCUSDm) | COIL | 36 | 36 | 16 | 22 | 10 | 14 | 8 | 3 | 1 | `1D|COIL|COIL-RIB|X-3R|none` |
| BTC (BTCUSDm) | STK | 18 | 18 | 7 | 18 | 7 | 5 | 5 | 0 | 0 | none |
| Nasdaq (USTECm) | SH | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| EURUSD (EURUSDm) | SH | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| GBPUSD (GBPUSDm) | SH | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |

## The champions and the finalists

| Symbol | # | Family | Champion | Finalist | Dev net | Val net | D+V net | D+V DD | D+V P/DD | Exam | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC (BTCUSDm) | 1 | HA-MANAGED | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | yes | +425 | +264 | +689 | 159 | 4.32 | fail |  |
| BTC (BTCUSDm) | 2 | MSD-FILTER | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | yes | +724 | +137 | +857 | 229 | 3.75 | pass |  |
| BTC (BTCUSDm) | 3 | COIL | `1D|COIL|COIL-RIB|X-3R|none` | yes | +592 | +25 | +617 | 183 | 3.37 | pass |  |
| BTC (BTCUSDm) | 4 | BOS | `4H|BOS|BOS-trend|LO|F1|S1` |  | +236 | +370 | +607 | 233 | 2.60 | pass |  |
| BTC (BTCUSDm) | 5 | SP | `4H|SP|W2|POC|F2-1D` |  | +176 | +57 | +233 | 98 | 2.39 | fail |  |
| BTC (BTCUSDm) | 6 | RIB | `4H|RIB|LS|XBE|F1` |  | +357 | +234 | +590 | 284 | 2.07 | pass |  |
| Gold (XAUUSDm) | 1 | RIB | `1H|RIB|LO|X0|F2-4H` | yes | +619 | +261 | +907 | 197 | 4.61 | passes the hold-out only |  |
| Gold (XAUUSDm) | 2 | COIL | `1H|COIL|COIL-RIB|X-3R|VOL` | yes | +367 | +172 | +539 | 131 | 4.11 | passes the hold-out only |  |
| Gold (XAUUSDm) | 3 | STK | `1H|STK|STK-RA|LO|S1` | yes | +504 | +279 | +790 | 207 | 3.81 | passes the hold-out only |  |
| Gold (XAUUSDm) | 4 | HA-MANAGED | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` |  | +346 | +219 | +572 | 152 | 3.76 | passes both |  |
| Gold (XAUUSDm) | 5 | SP | `4H|SP|W2|POC|LO` |  | +220 | +65 | +285 | 103 | 2.76 | passes the hold-out only |  |
| Gold (XAUUSDm) | 6 | MSD-FILTER | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` |  | +388 | +251 | +645 | 281 | 2.30 | passes the hold-out only |  |
| Gold (XAUUSDm) | 7 | HA-ENTRY | `1D|HA-ENTRY|HA-H2|LO|F0` |  | +310 | +166 | +580 | 293 | 1.98 | passes the hold-out only |  |
| Gold (XAUUSDm) | 8 | ALMA-X | `4H|ALMA-X|LO|X0|F0` |  | +266 | +205 | +494 | 275 | 1.80 | passes the hold-out only |  |
| Gold (XAUUSDm) | 9 | WY-DERIVED | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` |  | +145 | +15 | +160 | 117 | 1.37 | fails |  |
| Gold (XAUUSDm) | 10 | ORB | `M5|ORB|O3|HV+F2-4H` |  | +126 | +6.18 | +132 | 101 | 1.30 | fails |  |
| Gold (XAUUSDm) | 11 | MSD-ALONE | `1H|MSD-ALONE|MSD-A2|S0` |  | +456 | +32 | +488 | 521 | 0.94 | passes the hold-out only |  |

## The dashboard as a filter on study 1's rules (MSD-F4 / F6 against study 1's F0, F1, F2)

| Symbol | Kind | Study-1 filter | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) | Verdict |
|---|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | MSD-F4 | F0 | 60 | 25 | 30/60 | 9 | 8/60 | **does not help** |
| Gold (XAUUSDm) | MSD-F4 | F1 | 60 | 47 | 49/60 | 1 | 1/60 | **mixed** |
| Gold (XAUUSDm) | MSD-F4 | F2-4H | 20 | 13 | 14/20 | 0 | 1/20 | **mixed** |
| Gold (XAUUSDm) | MSD-F4 | F2-1D | 40 | 39 | 40/40 | 0 | 2/40 | **mixed** |
| Gold (XAUUSDm) | MSD-F6 | F0 | 60 | 19 | 18/60 | 32 | 30/60 | **mixed** |
| Gold (XAUUSDm) | MSD-F6 | F1 | 60 | 38 | 33/60 | 22 | 14/60 | **mixed** |
| Gold (XAUUSDm) | MSD-F6 | F2-4H | 20 | 5 | 4/20 | 6 | 5/20 | **does not help** |
| Gold (XAUUSDm) | MSD-F6 | F2-1D | 40 | 28 | 24/40 | 24 | 21/40 | **helps** |
| BTC (BTCUSDm) | MSD-F4 | F0 | 60 | 19 | 23/60 | 21 | 26/60 | **does not help** |
| BTC (BTCUSDm) | MSD-F4 | F1 | 60 | 10 | 16/60 | 12 | 12/60 | **does not help** |
| BTC (BTCUSDm) | MSD-F4 | F2-4H | 20 | 0 | 0/20 | 0 | 0/20 | **does not help** |
| BTC (BTCUSDm) | MSD-F4 | F2-1D | 40 | 10 | 8/40 | 0 | 3/40 | **does not help** |
| BTC (BTCUSDm) | MSD-F6 | F0 | 60 | 49 | 44/60 | 25 | 25/60 | **mixed** |
| BTC (BTCUSDm) | MSD-F6 | F1 | 60 | 19 | 21/60 | 12 | 9/60 | **does not help** |
| BTC (BTCUSDm) | MSD-F6 | F2-4H | 20 | 0 | 0/20 | 0 | 0/20 | **does not help** |
| BTC (BTCUSDm) | MSD-F6 | F2-1D | 40 | 14 | 14/40 | 20 | 20/40 | **does not help** |

## The filters against no filter, within a script

| Symbol | Filter | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) | Verdict |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | F1 | 46 | 14 | 10/37 | 16 | 18/37 | **does not help** |
| Gold (XAUUSDm) | F2-4H | 54 | 36 | 31/50 | 35 | 36/54 | **helps** |
| Gold (XAUUSDm) | F2-1D | 58 | 25 | 27/56 | 25 | 27/58 | **does not help** |
| Gold (XAUUSDm) | FR | 29 | 13 | 13/29 | 10 | 13/26 | **does not help** |
| Gold (XAUUSDm) | F3 | 34 | 26 | 27/34 | 16 | 17/34 | **mixed** |
| Gold (XAUUSDm) | FS | 24 | 7 | 13/24 | 0 | 0/24 | **mixed** |
| Gold (XAUUSDm) | FD | 6 | 1 | 0/6 | 1 | 0/6 | **does not help** |
| Gold (XAUUSDm) | LO | 16 | 12 | 12/16 | 10 | 10/16 | **helps** |
| Gold (XAUUSDm) | HV | 10 | 9 | 9/10 | 2 | 2/10 | **mixed** |
| Gold (XAUUSDm) | HV+F2-4H | 10 | 8 | 8/10 | 4 | 6/10 | **mixed** |
| BTC (BTCUSDm) | F1 | 46 | 37 | 37/40 | 16 | 21/40 | **mixed** |
| BTC (BTCUSDm) | F2-4H | 50 | 37 | 36/50 | 34 | 35/50 | **helps** |
| BTC (BTCUSDm) | F2-1D | 58 | 42 | 44/58 | 26 | 27/54 | **mixed** |
| BTC (BTCUSDm) | FR | 29 | 24 | 24/29 | 16 | 14/29 | **mixed** |
| BTC (BTCUSDm) | F3 | 34 | 31 | 31/34 | 14 | 16/34 | **mixed** |
| BTC (BTCUSDm) | FS | 24 | 16 | 16/24 | 6 | 8/24 | **mixed** |
| BTC (BTCUSDm) | FD | 6 | 4 | 4/6 | 4 | 2/5 | **mixed** |
| BTC (BTCUSDm) | LO | 6 | 4 | 3/6 | 5 | 3/6 | **mixed** |
| BTC (BTCUSDm) | HV | 10 | 10 | 10/10 | 0 | 0/10 | **mixed** |
| BTC (BTCUSDm) | HV+F2-4H | 10 | 10 | 10/10 | 4 | 6/10 | **mixed** |

## Our combinations against the scripts alone (PREREG 1 question 3, 6.11)

| Symbol | Combination | Pairs | Dev wins (net) | Dev wins (P/DD) | Val wins (net) | Val wins (P/DD) | Verdict |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | STK against RIB alone (same side and timeframe, X0, F0) | 18 | 5 | 7/18 | 3 | 7/18 | **does not help** |
| Gold (XAUUSDm) | WY-CL / WY-SP against WY-STD x X-S (same filter and timeframe) | 18 | 3 | 3/9 | 7 | 5/12 | **does not help** |
| Gold (XAUUSDm) | ORB-CX (the COMEX-open range) against the New York range | 8 | 0 | 1/8 | 5 | 5/8 | **mixed** |
| Gold (XAUUSDm) | TIGHT against the same ORB rule without it | 4 | 3 | 3/4 | 0 | 0/4 | **mixed** |
| BTC (BTCUSDm) | STK against RIB alone (same side and timeframe, X0, F0) | 18 | 12 | 10/18 | 5 | 8/18 | **mixed** |
| BTC (BTCUSDm) | WY-CL / WY-SP against WY-STD x X-S (same filter and timeframe) | 18 | 5 | 6/12 | 12 | 6/9 | **mixed** |
| BTC (BTCUSDm) | TIGHT against the same ORB rule without it | 4 | 4 | 4/4 | 0 | 1/4 | **mixed** |

The filters of 6.11 (RIB x F2 / FR / FS / F3, SP x FD / F2, SH x F2 / F3, ORB x HV / F2, HP x F2 / FR) are the table above; `combos_unmatched.csv` lists the combination rows without a counterpart.

## Each family's best row against study 1's best of the same symbol and timeframe

| Symbol | Family | Best row | Champion | D+V P/DD | Study 1's best | Its D+V P/DD | Better (D+V P/DD) |
|---|---|---|---|---|---|---|---|
| Gold (XAUUSDm) | RIB | `1H|RIB|LO|X0|F2-4H` | yes | 4.61 | `1H|QQE|R2|F2-4H|S0` | 3.48 | yes |
| Gold (XAUUSDm) | ALMA-X | `4H|ALMA-X|LO|X0|F0` | yes | 1.80 | `4H|RSI|R2|F1|S0` | 3.00 | no |
| Gold (XAUUSDm) | MSD-ALONE | `1H|MSD-ALONE|MSD-A2|S0` | yes | 0.94 | `1H|QQE|R2|F2-4H|S0` | 3.48 | no |
| Gold (XAUUSDm) | MSD-FILTER | `1H|MSD-FILTER|MSD-F6|QQE|R2|S0` | yes | 2.30 | `1H|QQE|R2|F2-4H|S0` | 3.48 | no |
| Gold (XAUUSDm) | BOS | `1D|BOS|BOS-trend|LO|F0|S1` |  | 2.16 | `1D|QQE|R2|F3|S0` | 2.08 | yes |
| Gold (XAUUSDm) | WY | `4H|WY|WY-AGG|S-W|X-S3|F0` |  | 2.27 | `4H|RSI|R2|F1|S0` | 3.00 | no |
| Gold (XAUUSDm) | WY-DERIVED | `1H|WY-DERIVED|WY-CL|S-CL|X-2R50|F0` | yes | 1.37 | `1H|QQE|R2|F2-4H|S0` | 3.48 | no |
| Gold (XAUUSDm) | SP | `4H|SP|W2|POC|LO` | yes | 2.76 | `4H|RSI|R2|F1|S0` | 3.00 | no |
| Gold (XAUUSDm) | ORB | `M5|ORB|O3|HV+F2-4H` | yes | 1.30 | none | - | - |
| Gold (XAUUSDm) | SH | `M15|SH|OR|K2|E1|F2-4H` |  | 1.47 | none | - | - |
| Gold (XAUUSDm) | HP-HARMONIC | `1D|HP-HARMONIC|HP-HF|50/50|FR` |  | 0.49 | `1D|QQE|R2|F3|S0` | 2.08 | no |
| Gold (XAUUSDm) | HP-CHART | `4H|HP-CHART|HP-CF|TP2|F0` |  | 3.03 | `4H|RSI|R2|F1|S0` | 3.00 | yes |
| Gold (XAUUSDm) | HA-ENTRY | `1D|HA-ENTRY|HA-H2|LO|F0` | yes | 1.98 | `1D|QQE|R2|F3|S0` | 2.08 | no |
| Gold (XAUUSDm) | HA-MANAGED | `4H|HA-MANAGED|M2|RSI-R2-F1-S0` | yes | 3.76 | `4H|RSI|R2|F1|S0` | 3.00 | yes |
| Gold (XAUUSDm) | COIL | `1H|COIL|COIL-RIB|X-3R|VOL` | yes | 4.11 | `1H|QQE|R2|F2-4H|S0` | 3.48 | yes |
| Gold (XAUUSDm) | STK | `1H|STK|STK-RA|LO|S1` | yes | 3.81 | `1H|QQE|R2|F2-4H|S0` | 3.48 | yes |
| BTC (BTCUSDm) | RIB | `4H|RIB|LS|XBE|F1` | yes | 2.07 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | ALMA-X | `1D|ALMA-X|LO|X0|F0` |  | 0.63 | `1D|LaRSI|R2|F3|S1` | 3.70 | no |
| BTC (BTCUSDm) | MSD-ALONE | `4H|MSD-ALONE|MSD-A2|S1` |  | 1.69 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | MSD-FILTER | `1D|MSD-FILTER|MSD-F6|LaRSI|R1|S1` | yes | 3.75 | `1D|LaRSI|R2|F3|S1` | 3.70 | yes |
| BTC (BTCUSDm) | BOS | `4H|BOS|BOS-trend|LO|F1|S1` | yes | 2.60 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | WY | `1H|WY|WY-AGG|S-W|X-S|F0` |  | 1.09 | `1H|QQE|R2|F2-4H|S0` | 1.23 | no |
| BTC (BTCUSDm) | WY-DERIVED | `4H|WY-DERIVED|WY-SP|S-SP|X-S|F0` |  | 2.79 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | SP | `4H|SP|W2|POC|F2-1D` | yes | 2.39 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | ORB | `M15|ORB|O1|HV+F2-4H` |  | 4.14 | none | - | - |
| BTC (BTCUSDm) | SH | `M15|SH|AB|K2|E1|F2-1D` |  | 0.31 | none | - | - |
| BTC (BTCUSDm) | HP-HARMONIC | `4H|HP-HARMONIC|HP-HF|TP1|FR` |  | 0.43 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | HP-CHART | `4H|HP-CHART|HP-CF|TP1|FR` |  | 2.60 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |
| BTC (BTCUSDm) | HA-ENTRY | `1D|HA-ENTRY|HA-H1|LO|F1` |  | 2.33 | `1D|LaRSI|R2|F3|S1` | 3.70 | no |
| BTC (BTCUSDm) | HA-MANAGED | `1D|HA-MANAGED|HA-AND|LaRSI-R2-F3-S1` | yes | 4.32 | `1D|LaRSI|R2|F3|S1` | 3.70 | yes |
| BTC (BTCUSDm) | COIL | `1D|COIL|COIL-RIB|X-3R|none` | yes | 3.37 | `1D|LaRSI|R2|F3|S1` | 3.70 | no |
| BTC (BTCUSDm) | STK | `4H|STK|STK-RA|LO|S1` |  | 1.56 | `4H|LaRSI|R2|F1|S1` | 3.07 | no |

## Buy-and-hold of 0.01 lot

| Symbol | Window | Cost | Net | Max DD | P/DD |
|---|---|---|---|---|---|
| Gold (XAUUSDm) | dev | 1.0 | +542 | 459 | 1.18 |
| Gold (XAUUSDm) | dev | 1.5 | +542 | 459 | 1.18 |
| Gold (XAUUSDm) | val | 1.0 | +498 | 264 | 1.88 |
| Gold (XAUUSDm) | val | 1.5 | +497 | 264 | 1.88 |
| Gold (XAUUSDm) | devval | 1.0 | +1,043 | 459 | 2.27 |
| Gold (XAUUSDm) | devval | 1.5 | +1,043 | 459 | 2.27 |
| BTC (BTCUSDm) | dev | 1.0 | +128 | 535 | 0.24 |
| BTC (BTCUSDm) | dev | 1.5 | +128 | 535 | 0.24 |
| BTC (BTCUSDm) | val | 1.0 | +462 | 171 | 2.69 |
| BTC (BTCUSDm) | val | 1.5 | +462 | 171 | 2.69 |
| BTC (BTCUSDm) | devval | 1.0 | +590 | 535 | 1.10 |
| BTC (BTCUSDm) | devval | 1.5 | +590 | 535 | 1.10 |
| Nasdaq (USTECm) | dev | 1.0 | +7.92 | 63 | 0.13 |
| Nasdaq (USTECm) | dev | 1.5 | +7.90 | 63 | 0.12 |
| Nasdaq (USTECm) | val | 1.0 | +88 | 19 | 4.67 |
| Nasdaq (USTECm) | val | 1.5 | +88 | 19 | 4.67 |
| Nasdaq (USTECm) | devval | 1.0 | +96 | 63 | 1.51 |
| Nasdaq (USTECm) | devval | 1.5 | +96 | 63 | 1.51 |
| EURUSD (EURUSDm) | dev | 1.0 | -76 | 281 | -0.27 |
| EURUSD (EURUSDm) | dev | 1.5 | -76 | 281 | -0.27 |
| EURUSD (EURUSDm) | val | 1.0 | +1.73 | 83 | 0.02 |
| EURUSD (EURUSDm) | val | 1.5 | +0.23 | 83 | 0.00 |
| EURUSD (EURUSDm) | devval | 1.0 | -73 | 281 | -0.26 |
| EURUSD (EURUSDm) | devval | 1.5 | -73 | 281 | -0.26 |
| GBPUSD (GBPUSDm) | dev | 1.0 | -66 | 389 | -0.17 |
| GBPUSD (GBPUSDm) | dev | 1.5 | -66 | 389 | -0.17 |
| GBPUSD (GBPUSDm) | val | 1.0 | +54 | 110 | 0.49 |
| GBPUSD (GBPUSDm) | val | 1.5 | +53 | 110 | 0.48 |
| GBPUSD (GBPUSDm) | devval | 1.0 | -11 | 389 | -0.03 |
| GBPUSD (GBPUSDm) | devval | 1.5 | -11 | 389 | -0.03 |
