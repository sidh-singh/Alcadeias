# TradeIQ's 9 indicators for 2027: the video's claims (PREREG 8)

Written by `python -B -m backtesting.research.tradeiq2 claims` on 28 Nov 2026 15:16 UTC. Each claim is split into the parts it states; each part is counted on the rows it is about, per symbol, in Development and in Validation. **A part holds when it holds in both windows, does not hold when it fails in both, and is mixed otherwise** (study 1's reading, its DEVIATIONS 31). "Most" = more than half; "every" = all; a win = strictly more net profit at x1.0. The claim-check markets (USTECm, EURUSDm, GBPUSDm) are information only.

## The verdicts

| Claim | Part | Symbol | Development | Validation | Verdict | Hold-out (information) | Note |
|---|---|---|---|---|---|---|---|
| 1 | RIB takes fewer trades than ALMA-X in every pair | Gold (XAUUSDm) | 6/6 | 6/6 | **holds** | holds |  |
| 1 | RIB makes more net than ALMA-X in most pairs | Gold (XAUUSDm) | 4/6 | 6/6 | **holds** | does not hold |  |
| 1 | RIB takes fewer trades than ALMA-X in every pair | BTC (BTCUSDm) | 6/6 | 6/6 | **holds** | holds |  |
| 1 | RIB makes more net than ALMA-X in most pairs | BTC (BTCUSDm) | 4/6 | 6/6 | **holds** | holds |  |
| 2 | XP makes more net than X0 in most pairs | Gold (XAUUSDm) | 11/34 | 4/34 | **does not hold** | does not hold |  |
| 2 | XP makes more net than XT2 in most pairs | Gold (XAUUSDm) | 23/34 | 29/34 | **holds** | holds |  |
| 2 | XP makes more net than X0 in most pairs | BTC (BTCUSDm) | 13/34 | 0/34 | **does not hold** | does not hold |  |
| 2 | XP makes more net than XT2 in most pairs | BTC (BTCUSDm) | 21/34 | 32/34 | **holds** | holds |  |
| 3 | XBE makes more net than X0 in most pairs | Gold (XAUUSDm) | 7/34 | 21/34 | **mixed** | does not hold |  |
| 3 | the HA overlays make more net than their RIB X0 base in most pairs | Gold (XAUUSDm) | 12/30 | 5/30 | **does not hold** | does not hold |  |
| 3 | XBE makes more net than X0 in most pairs | BTC (BTCUSDm) | 24/34 | 10/34 | **mixed** | does not hold |  |
| 3 | the HA overlays make more net than their RIB X0 base in most pairs | BTC (BTCUSDm) | 16/30 | 4/30 | **mixed** | does not hold |  |
| 4 | M2 makes more net than its base in most pairs | Gold (XAUUSDm) | 3/9 | 2/9 | **does not hold** | does not hold |  |
| 4 | M2 has a smaller max drawdown than its base in most pairs | Gold (XAUUSDm) | 6/9 | 7/9 | **holds** | holds |  |
| 4 | M3 makes more net than its base in most pairs | Gold (XAUUSDm) | 3/9 | 3/9 | **does not hold** | holds |  |
| 4 | M3 has a smaller max drawdown than its base in most pairs | Gold (XAUUSDm) | 6/9 | 5/9 | **holds** | does not hold |  |
| 4 | M5 makes more net than its base in most pairs | Gold (XAUUSDm) | 1/9 | 0/9 | **does not hold** | does not hold |  |
| 4 | M5 has a smaller max drawdown than its base in most pairs | Gold (XAUUSDm) | 7/9 | 9/9 | **holds** | holds |  |
| 4 | M2 makes more net than its base in most pairs | BTC (BTCUSDm) | 4/9 | 3/9 | **does not hold** | does not hold |  |
| 4 | M2 has a smaller max drawdown than its base in most pairs | BTC (BTCUSDm) | 5/9 | 8/9 | **holds** | holds |  |
| 4 | M3 makes more net than its base in most pairs | BTC (BTCUSDm) | 2/9 | 3/9 | **does not hold** | does not hold |  |
| 4 | M3 has a smaller max drawdown than its base in most pairs | BTC (BTCUSDm) | 3/9 | 4/9 | **does not hold** | does not hold |  |
| 4 | M5 makes more net than its base in most pairs | BTC (BTCUSDm) | 5/9 | 0/9 | **mixed** | does not hold |  |
| 4 | M5 has a smaller max drawdown than its base in most pairs | BTC (BTCUSDm) | 9/9 | 9/9 | **holds** | holds |  |
| 5 | the panel's 'reached age A, then 5+ more' rates, computed before each year, match that year: the binomial 95% interval around them covers the year's share in most cells | Gold (XAUUSDm) | 155/174 cells inside the 95% interval (89%; by year 2019 37/42, 2020 32/43, 2021 45/45, 2022 41/44); ages 1-12, 28,997 streak-ages; mean |year - panel| 3.0 pp (weighted by n), the year above the panel in 84/174 | 66/71 cells inside the 95% interval (93%; by year 2023 36/41, 2024 30/30); ages 1-11, 10,518 streak-ages; mean |year - panel| 2.4 pp (weighted by n), the year above the panel in 36/71 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | Gold (XAUUSDm) | 48/48 cells inside the 95% interval (100%; by year 2019 12/12, 2020 12/12, 2021 12/12, 2022 12/12); ages 1-12, 11,713 streak-ages; mean |year - panel| 1.4 pp (weighted by n), the year above the panel in 24/48 | 17/21 cells inside the 95% interval (81%; by year 2023 7/11, 2024 10/10); ages 1-11, 4,355 streak-ages; mean |year - panel| 2.6 pp (weighted by n), the year above the panel in 11/21 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | Gold (XAUUSDm) | 32/44 cells inside the 95% interval (73%; by year 2019 8/11, 2020 4/10, 2021 11/11, 2022 9/12); ages 1-12, 11,107 streak-ages; mean |year - panel| 3.8 pp (weighted by n), the year above the panel in 20/44 | 20/20 cells inside the 95% interval (100%; by year 2023 11/11, 2024 9/9); ages 1-11, 4,054 streak-ages; mean |year - panel| 1.4 pp (weighted by n), the year above the panel in 9/20 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 4H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | Gold (XAUUSDm) | 26/30 cells inside the 95% interval (87%; by year 2019 7/7, 2020 4/8, 2021 8/8, 2022 7/7); ages 1-8, 2,888 streak-ages; mean |year - panel| 4.3 pp (weighted by n), the year above the panel in 15/30 | 13/13 cells inside the 95% interval (100%; by year 2023 8/8, 2024 5/5); ages 1-8, 1,062 streak-ages; mean |year - panel| 2.5 pp (weighted by n), the year above the panel in 8/13 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 4H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | Gold (XAUUSDm) | 26/28 cells inside the 95% interval (93%; by year 2019 6/7, 2020 5/6, 2021 8/8, 2022 7/7); ages 1-8, 2,681 streak-ages; mean |year - panel| 4.1 pp (weighted by n), the year above the panel in 15/28 | 10/11 cells inside the 95% interval (91%; by year 2023 5/6, 2024 5/5); ages 1-6, 925 streak-ages; mean |year - panel| 4.9 pp (weighted by n), the year above the panel in 2/11 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1D bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | Gold (XAUUSDm) | 14/14 cells inside the 95% interval (100%; by year 2019 3/3, 2020 4/4, 2021 4/4, 2022 3/3); ages 1-4, 352 streak-ages; mean |year - panel| 4.3 pp (weighted by n), the year above the panel in 8/14 | 3/3 cells inside the 95% interval (100%; by year 2023 2/2, 2024 1/1); ages 1-2, 57 streak-ages; mean |year - panel| 4.6 pp (weighted by n), the year above the panel in 3/3 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1D bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | Gold (XAUUSDm) | 9/10 cells inside the 95% interval (90%; by year 2019 1/2, 2020 3/3, 2021 2/2, 2022 3/3); ages 1-3, 256 streak-ages; mean |year - panel| 8.6 pp (weighted by n), the year above the panel in 2/10 | 3/3 cells inside the 95% interval (100%; by year 2023 3/3); ages 1-3, 65 streak-ages; mean |year - panel| 6.4 pp (weighted by n), the year above the panel in 3/3 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | the panel's 'reached age A, then 5+ more' rates, computed before each year, match that year: the binomial 95% interval around them covers the year's share in most cells | BTC (BTCUSDm) | 136/170 cells inside the 95% interval (80%; by year 2019 28/33, 2020 26/42, 2021 39/47, 2022 43/48); ages 1-13, 42,698 streak-ages; mean |year - panel| 3.3 pp (weighted by n), the year above the panel in 94/170 | 75/81 cells inside the 95% interval (93%; by year 2023 45/47, 2024 30/34); ages 1-12, 15,958 streak-ages; mean |year - panel| 2.1 pp (weighted by n), the year above the panel in 32/81 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | BTC (BTCUSDm) | 33/46 cells inside the 95% interval (72%; by year 2019 8/10, 2020 5/12, 2021 9/13, 2022 11/11); ages 1-13, 17,680 streak-ages; mean |year - panel| 3.4 pp (weighted by n), the year above the panel in 30/46 | 20/24 cells inside the 95% interval (83%; by year 2023 12/12, 2024 8/12); ages 1-12, 6,663 streak-ages; mean |year - panel| 2.3 pp (weighted by n), the year above the panel in 14/24 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | BTC (BTCUSDm) | 31/43 cells inside the 95% interval (72%; by year 2019 10/10, 2020 5/10, 2021 7/11, 2022 9/12); ages 1-12, 16,482 streak-ages; mean |year - panel| 2.3 pp (weighted by n), the year above the panel in 22/43 | 17/19 cells inside the 95% interval (89%; by year 2023 8/10, 2024 9/9); ages 1-10, 6,107 streak-ages; mean |year - panel| 1.5 pp (weighted by n), the year above the panel in 5/19 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 4H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | BTC (BTCUSDm) | 28/30 cells inside the 95% interval (93%; by year 2019 5/6, 2020 7/8, 2021 8/8, 2022 8/8); ages 1-8, 4,007 streak-ages; mean |year - panel| 3.9 pp (weighted by n), the year above the panel in 23/30 | 14/14 cells inside the 95% interval (100%; by year 2023 8/8, 2024 6/6); ages 1-8, 1,507 streak-ages; mean |year - panel| 2.2 pp (weighted by n), the year above the panel in 3/14 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 4H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | BTC (BTCUSDm) | 24/29 cells inside the 95% interval (83%; by year 2019 5/7, 2020 6/7, 2021 7/7, 2022 6/8); ages 1-8, 3,833 streak-ages; mean |year - panel| 5.4 pp (weighted by n), the year above the panel in 11/29 | 12/12 cells inside the 95% interval (100%; by year 2023 7/7, 2024 5/5); ages 1-7, 1,379 streak-ages; mean |year - panel| 2.4 pp (weighted by n), the year above the panel in 2/12 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1D bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | BTC (BTCUSDm) | 8/10 cells inside the 95% interval (80%; by year 2020 0/2, 2021 4/4, 2022 4/4); ages 1-4, 325 streak-ages; mean |year - panel| 12.0 pp (weighted by n), the year above the panel in 2/10 | 6/6 cells inside the 95% interval (100%; by year 2023 5/5, 2024 1/1); ages 1-5, 151 streak-ages; mean |year - panel| 6.8 pp (weighted by n), the year above the panel in 6/6 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 5 | 1D bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells | BTC (BTCUSDm) | 12/12 cells inside the 95% interval (100%; by year 2020 3/3, 2021 4/4, 2022 5/5); ages 1-5, 371 streak-ages; mean |year - panel| 9.9 pp (weighted by n), the year above the panel in 6/12 | 6/6 cells inside the 95% interval (100%; by year 2023 5/5, 2024 1/1); ages 1-5, 151 streak-ages; mean |year - panel| 5.7 pp (weighted by n), the year above the panel in 2/6 | **holds** | holds | PREREG 8 claim 5: the panel's 100 g / r (survive, l.176-184; aheadN 5) from every streak finished before the year (keep=None), against the year's streak-ages; a panel with exact rates is covered in at least 95% of cells, its own sampling error lowers that (HA-R12); cells: tradeiq2_rules_ha.claim5_table |
| 6 | the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days | Gold (XAUUSDm) | 566/993 breakout days (57.0%); beyond the other side 144 (14.5%), inside 283; 1031 sessions | 202/372 breakout days (54.3%); beyond the other side 54 (14.5%), inside 116; 385 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the first breakout's side more often than beyond the other side | Gold (XAUUSDm) | 566/993 breakout days (57.0%); beyond the other side 144 (14.5%), inside 283; 1031 sessions | 202/372 breakout days (54.3%); beyond the other side 54 (14.5%), inside 116; 385 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days | Gold (XAUUSDm) | 584/966 breakout days (60.5%); beyond the other side 126 (13.0%), inside 256; 1031 sessions | 226/362 breakout days (62.4%); beyond the other side 30 (8.3%), inside 106; 385 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the first breakout's side more often than beyond the other side | Gold (XAUUSDm) | 584/966 breakout days (60.5%); beyond the other side 126 (13.0%), inside 256; 1031 sessions | 226/362 breakout days (62.4%); beyond the other side 30 (8.3%), inside 106; 385 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days | BTC (BTCUSDm) | 586/1021 breakout days (57.4%); beyond the other side 210 (20.6%), inside 225; 1042 sessions | 225/383 breakout days (58.7%); beyond the other side 71 (18.5%), inside 87; 390 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the first breakout's side more often than beyond the other side | BTC (BTCUSDm) | 586/1021 breakout days (57.4%); beyond the other side 210 (20.6%), inside 225; 1042 sessions | 225/383 breakout days (58.7%); beyond the other side 71 (18.5%), inside 87; 390 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days | BTC (BTCUSDm) | 606/1016 breakout days (59.6%); beyond the other side 190 (18.7%), inside 220; 1042 sessions | 233/379 breakout days (61.5%); beyond the other side 63 (16.6%), inside 83; 390 sessions | **holds** | holds |  |
| 6 | the 16:00 close is beyond the first breakout's side more often than beyond the other side | BTC (BTCUSDm) | 606/1016 breakout days (59.6%); beyond the other side 190 (18.7%), inside 220; 1042 sessions | 233/379 breakout days (61.5%); beyond the other side 63 (16.6%), inside 83; 390 sessions | **holds** | holds |  |
| 7 | HV makes more net than LV in most pairs | Gold (XAUUSDm) | 8/8 | 4/8 | **mixed** | holds |  |
| 7 | after HV and LV breakouts: the 16:00 close and T1 (information) | Gold (XAUUSDm) | HV 746 labels: 16:00 close beyond their side 59.2%, T1 after 53.2%; LV 496 labels: 16:00 close beyond their side 54.0%, T1 after 43.3% | HV 245 labels: 16:00 close beyond their side 55.5%, T1 after 51.4%; LV 217 labels: 16:00 close beyond their side 55.3%, T1 after 35.9% | **information** | information | geometry, no verdict |
| 7 | after HV and LV breakouts: the 16:00 close and T1 (information) | Gold (XAUUSDm) | HV 828 labels: 16:00 close beyond their side 62.7%, T1 after 59.2%; LV 332 labels: 16:00 close beyond their side 57.5%, T1 after 33.1% | HV 295 labels: 16:00 close beyond their side 62.4%, T1 after 55.6%; LV 117 labels: 16:00 close beyond their side 61.5%, T1 after 30.8% | **information** | information | geometry, no verdict |
| 7 | HV makes more net than LV in most pairs | BTC (BTCUSDm) | 1/8 | 5/8 | **mixed** | holds |  |
| 7 | after HV and LV breakouts: the 16:00 close and T1 (information) | BTC (BTCUSDm) | HV 1089 labels: 16:00 close beyond their side 56.6%, T1 after 66.1%; LV 345 labels: 16:00 close beyond their side 52.2%, T1 after 61.7% | HV 397 labels: 16:00 close beyond their side 58.9%, T1 after 69.0%; LV 110 labels: 16:00 close beyond their side 56.4%, T1 after 65.5% | **information** | information | geometry, no verdict |
| 7 | after HV and LV breakouts: the 16:00 close and T1 (information) | BTC (BTCUSDm) | HV 945 labels: 16:00 close beyond their side 62.1%, T1 after 69.5%; LV 401 labels: 16:00 close beyond their side 52.1%, T1 after 60.1% | HV 374 labels: 16:00 close beyond their side 63.9%, T1 after 74.6%; LV 98 labels: 16:00 close beyond their side 58.2%, T1 after 60.2% | **information** | information | geometry, no verdict |
| 8 | T1: the rate after a breakout differs from the dashboard's unconditional rate | Gold (XAUUSDm) | dashboard 29.9% of 2062 side-days, after a breakout 49.3% of 1242 (z 11.15) | dashboard 26.9% of 770 side-days, after a breakout 44.2% of 462 (z 6.23) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T2: the rate after a breakout differs from the dashboard's unconditional rate | Gold (XAUUSDm) | dashboard 12.1% of 2062 side-days, after a breakout 20.1% of 1242 (z 6.22) | dashboard 11.6% of 770 side-days, after a breakout 19.3% of 462 (z 3.72) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T3: the rate after a breakout differs from the dashboard's unconditional rate | Gold (XAUUSDm) | dashboard 5.1% of 2062 side-days, after a breakout 8.5% of 1242 (z 3.86) | dashboard 5.2% of 770 side-days, after a breakout 8.7% of 462 (z 2.39) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T1: the rate after a breakout differs from the dashboard's unconditional rate | Gold (XAUUSDm) | dashboard 29.9% of 2062 side-days, after a breakout 51.7% of 1160 (z 12.25) | dashboard 26.9% of 770 side-days, after a breakout 48.5% of 412 (z 7.47) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T2: the rate after a breakout differs from the dashboard's unconditional rate | Gold (XAUUSDm) | dashboard 12.1% of 2062 side-days, after a breakout 21.2% of 1160 (z 6.86) | dashboard 11.6% of 770 side-days, after a breakout 21.1% of 412 (z 4.40) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T3: the rate after a breakout differs from the dashboard's unconditional rate | Gold (XAUUSDm) | dashboard 5.1% of 2062 side-days, after a breakout 9.1% of 1160 (z 4.39) | dashboard 5.2% of 770 side-days, after a breakout 9.7% of 412 (z 2.94) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T1: the rate after a breakout differs from the dashboard's unconditional rate | BTC (BTCUSDm) | dashboard 51.1% of 2084 side-days, after a breakout 65.1% of 1434 (z 8.24) | dashboard 47.6% of 780 side-days, after a breakout 68.2% of 507 (z 7.30) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T2: the rate after a breakout differs from the dashboard's unconditional rate | BTC (BTCUSDm) | dashboard 32.7% of 2084 side-days, after a breakout 40.3% of 1434 (z 4.61) | dashboard 29.1% of 780 side-days, after a breakout 41.6% of 507 (z 4.63) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T3: the rate after a breakout differs from the dashboard's unconditional rate | BTC (BTCUSDm) | dashboard 21.5% of 2084 side-days, after a breakout 25.9% of 1434 (z 3.03) | dashboard 19.9% of 780 side-days, after a breakout 27.2% of 507 (z 3.07) | **holds** | does not hold | a two-proportion z-test at 5%, both sides pooled |
| 8 | T1: the rate after a breakout differs from the dashboard's unconditional rate | BTC (BTCUSDm) | dashboard 51.1% of 2084 side-days, after a breakout 66.7% of 1346 (z 9.05) | dashboard 47.6% of 780 side-days, after a breakout 71.6% of 472 (z 8.32) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T2: the rate after a breakout differs from the dashboard's unconditional rate | BTC (BTCUSDm) | dashboard 32.7% of 2084 side-days, after a breakout 41.6% of 1346 (z 5.28) | dashboard 29.1% of 780 side-days, after a breakout 43.9% of 472 (z 5.32) | **holds** | holds | a two-proportion z-test at 5%, both sides pooled |
| 8 | T3: the rate after a breakout differs from the dashboard's unconditional rate | BTC (BTCUSDm) | dashboard 21.5% of 2084 side-days, after a breakout 26.6% of 1346 (z 3.41) | dashboard 19.9% of 780 side-days, after a breakout 28.6% of 472 (z 3.55) | **holds** | does not hold | a two-proportion z-test at 5%, both sides pooled |
| 8 | O4 (the hit-rate target) makes more net than O2 in most pairs | Gold (XAUUSDm) | 0/12 | 0/12 | **does not hold** | does not hold |  |
| 8 | O4 (the hit-rate target) makes more net than O3 in most pairs | Gold (XAUUSDm) | 4/12 | 11/12 | **mixed** | does not hold |  |
| 8 | O4 (the hit-rate target) makes more net than O2 in most pairs | BTC (BTCUSDm) | 3/10 | 0/10 | **does not hold** | does not hold |  |
| 8 | O4 (the hit-rate target) makes more net than O3 in most pairs | BTC (BTCUSDm) | 0/10 | 0/10 | **does not hold** | does not hold |  |
| 9 | the literal UTC-5 clock's range starts an hour late (10:30 New York) on every daylight-saving session and on no other | Gold (XAUUSDm) | 676/1031 sessions start at 10:30 New York (676 on daylight saving), 355 at 09:30 | 248/385 sessions start at 10:30 New York (248 on daylight saving), 137 at 09:30 | **holds** | holds |  |
| 9 | O1 on New York time makes more net than on the literal UTC-5 clock on both timeframes | Gold (XAUUSDm) | 2/2 | 1/2 | **mixed** | holds |  |
| 9 | the literal UTC-5 clock's range starts an hour late (10:30 New York) on every daylight-saving session and on no other | BTC (BTCUSDm) | 680/1042 sessions start at 10:30 New York (680 on daylight saving), 362 at 09:30 | 250/390 sessions start at 10:30 New York (250 on daylight saving), 140 at 09:30 | **holds** | holds |  |
| 9 | O1 on New York time makes more net than on the literal UTC-5 clock on both timeframes | BTC (BTCUSDm) | 2/2 | 2/2 | **holds** | holds |  |
| 10 | the claim-check row has a profit factor above 1 (the author: 1.95) | Nasdaq (USTECm) | PF 1.09, 354 trades, 28% win, avg R 0.07 | PF 1.18, 224 trades | **holds** | holds | information only (PREREG 8) |
| 10 | the claim-check row has a profit factor above 1 (the author: 1.95) | Nasdaq (USTECm) | PF 1.10, 242 trades, 32% win, avg R -0.07 | PF 1.56, 153 trades | **holds** | holds | information only (PREREG 8) |
| 10 | the claim-check row has a profit factor above 1 (the author: 1.95) | Nasdaq (USTECm) | PF 1.44, 132 trades, 27% win, avg R 0.55 | PF 1.51, 78 trades | **holds** | holds | information only (PREREG 8) |
| 10 | the claim-check row has a profit factor above 1 (the author: 1.95) | Nasdaq (USTECm) | PF 1.36, 120 trades, 28% win, avg R 0.58 | PF 1.63, 66 trades | **holds** | holds | information only (PREREG 8) |
| 10 | the claim-check row has a profit factor above 1 (the author: 1.95) | EURUSD (EURUSDm) | PF 0.75, 240 trades, 26% win, avg R -0.24 | PF 1.33, 96 trades | **mixed** | holds | information only (PREREG 8) |
| 10 | the claim-check row has a profit factor above 1 (the author: 1.95) | GBPUSD (GBPUSDm) | PF 1.54, 213 trades, 41% win, avg R 0.34 | PF 1.02, 76 trades | **holds** | does not hold | information only (PREREG 8) |
| 10 | nothing held up: at most half of the SH rows make money | Gold (XAUUSDm) | 11/116 | 59/116 | **mixed** | holds |  |
| 10 | holding to 16:00 (E1) makes more net than E2 in most pairs | Gold (XAUUSDm) | 20/30 | 17/30 | **holds** | holds |  |
| 10 | holding to 16:00 (E1) makes more net than E3 in most pairs | Gold (XAUUSDm) | 3/10 | 5/10 | **does not hold** | holds |  |
| 10 | PREREG 6.6's hypothesis: AB is positive (most AB rows net > 0) | Gold (XAUUSDm) | 3/22 | 2/22 | **does not hold** | holds |  |
| 10 | PREREG 6.6's hypothesis: AS is negative (most AS rows net < 0) | Gold (XAUUSDm) | 21/24 | 21/24 | **holds** | holds |  |
| 10 | nothing held up: at most half of the SH rows make money | BTC (BTCUSDm) | 0/116 | 72/116 | **mixed** | holds |  |
| 10 | holding to 16:00 (E1) makes more net than E2 in most pairs | BTC (BTCUSDm) | 8/30 | 26/30 | **mixed** | does not hold |  |
| 10 | holding to 16:00 (E1) makes more net than E3 in most pairs | BTC (BTCUSDm) | 2/10 | 6/10 | **mixed** | holds |  |
| 11 | price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) | Gold (XAUUSDm) | POC touched in 270/317 legs (85.2%), the 50% level in 259/317 (81.7%); only the POC 42, only the 50% level 31; one-sided sign test p = 0.121; 1 left out (began before the window) | POC touched in 91/105 legs (86.7%), the 50% level in 86/105 (81.9%); only the POC 10, only the 50% level 5; one-sided sign test p = 0.151; 1 left out (began before the window) | **does not hold** | does not hold | the levels are the forming leg's POC (f_poc, W1 / W2's level) and 50% level ((f_lo + f_hi) / 2, the placebo's) at each bar, read only on bars where both exist; a leg that began before its window, and the last leg (not finished), are not counted |
| 11 | price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) | Gold (XAUUSDm) | POC touched in 204/317 legs (64.4%), the 50% level in 218/317 (68.8%); only the POC 41, only the 50% level 55; one-sided sign test p = 0.937; 1 left out (began before the window) | POC touched in 62/105 legs (59.0%), the 50% level in 71/105 (67.6%); only the POC 11, only the 50% level 20; one-sided sign test p = 0.965; 1 left out (began before the window) | **information** | information | information, no verdict: the levels are the just-finished leg's POC (legs.poc, W3's level) and 50% level (legs.fifty), fixed from its flip bar's close (the flip bar is not read) |
| 11 | price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) | Gold (XAUUSDm) | POC touched in 72/87 legs (82.8%), the 50% level in 71/87 (81.6%); only the POC 10, only the 50% level 9; one-sided sign test p = 0.500; 1 left out (began before the window) | POC touched in 24/28 legs (85.7%), the 50% level in 20/28 (71.4%); only the POC 7, only the 50% level 3; one-sided sign test p = 0.172; 1 left out (began before the window) | **does not hold** | does not hold | the levels are the forming leg's POC (f_poc, W1 / W2's level) and 50% level ((f_lo + f_hi) / 2, the placebo's) at each bar, read only on bars where both exist; a leg that began before its window, and the last leg (not finished), are not counted |
| 11 | price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) | Gold (XAUUSDm) | POC touched in 50/87 legs (57.5%), the 50% level in 55/87 (63.2%); only the POC 13, only the 50% level 18; one-sided sign test p = 0.859; 1 left out (began before the window) | POC touched in 22/28 legs (78.6%), the 50% level in 19/28 (67.9%); only the POC 5, only the 50% level 2; one-sided sign test p = 0.227; 1 left out (began before the window) | **information** | information | information, no verdict: the levels are the just-finished leg's POC (legs.poc, W3's level) and 50% level (legs.fifty), fixed from its flip bar's close (the flip bar is not read) |
| 11 | price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) | BTC (BTCUSDm) | POC touched in 405/457 legs (88.6%), the 50% level in 352/457 (77.0%); only the POC 86, only the 50% level 33; one-sided sign test p < 0.001; 1 left out (began before the window) | POC touched in 156/184 legs (84.8%), the 50% level in 150/184 (81.5%); only the POC 19, only the 50% level 13; one-sided sign test p = 0.189; 1 left out (began before the window) | **mixed** | holds | the levels are the forming leg's POC (f_poc, W1 / W2's level) and 50% level ((f_lo + f_hi) / 2, the placebo's) at each bar, read only on bars where both exist; a leg that began before its window, and the last leg (not finished), are not counted |
| 11 | price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) | BTC (BTCUSDm) | POC touched in 283/457 legs (61.9%), the 50% level in 288/457 (63.0%); only the POC 70, only the 50% level 75; one-sided sign test p = 0.691; 1 left out (began before the window) | POC touched in 115/184 legs (62.5%), the 50% level in 120/184 (65.2%); only the POC 20, only the 50% level 25; one-sided sign test p = 0.814; 1 left out (began before the window) | **information** | information | information, no verdict: the levels are the just-finished leg's POC (legs.poc, W3's level) and 50% level (legs.fifty), fixed from its flip bar's close (the flip bar is not read) |
| 11 | price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) | BTC (BTCUSDm) | POC touched in 93/107 legs (86.9%), the 50% level in 82/107 (76.6%); only the POC 18, only the 50% level 7; one-sided sign test p = 0.022; 1 left out (began before the window) | POC touched in 34/39 legs (87.2%), the 50% level in 31/39 (79.5%); only the POC 7, only the 50% level 4; one-sided sign test p = 0.274; 1 left out (began before the window) | **mixed** | holds | the levels are the forming leg's POC (f_poc, W1 / W2's level) and 50% level ((f_lo + f_hi) / 2, the placebo's) at each bar, read only on bars where both exist; a leg that began before its window, and the last leg (not finished), are not counted |
| 11 | price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) | BTC (BTCUSDm) | POC touched in 61/107 legs (57.0%), the 50% level in 61/107 (57.0%); only the POC 16, only the 50% level 16; one-sided sign test p = 0.570; 1 left out (began before the window) | POC touched in 26/39 legs (66.7%), the 50% level in 24/39 (61.5%); only the POC 6, only the 50% level 4; one-sided sign test p = 0.377; 1 left out (began before the window) | **information** | information | information, no verdict: the levels are the just-finished leg's POC (legs.poc, W3's level) and 50% level (legs.fifty), fixed from its flip bar's close (the flip bar is not read) |
| 11 | the POC rule makes more net than its 50%-level placebo in most pairs | Gold (XAUUSDm) | 4/12 | 8/12 | **mixed** | does not hold |  |
| 11 | the POC rule makes more net than its 50%-level placebo in most pairs | BTC (BTCUSDm) | 5/12 | 6/12 | **does not hold** | holds |  |
| 12 | after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) | Gold (XAUUSDm) | delta < 0: 5 up legs, median next leg 6.60 ATR; delta > 0: 154, median 8.69 ATR; U 322, one-sided p = 0.729 | delta < 0: 1 up legs, median next leg 3.92 ATR; delta > 0: 52, median 9.70 ATR; U 0, one-sided p = 1.000 | **does not hold** | cannot be tested | the exact one-sided Mann-Whitney U test (ties as midranks); the delta is the script's bin sums (tick volume); a pair whose next leg began before its window is not counted |
| 12 | after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) | Gold (XAUUSDm) | delta < 0: 3 up legs, median next leg 8.31 ATR; delta > 0: 41, median 9.22 ATR; U 66, one-sided p = 0.430 | delta < 0: 0 up legs, median next leg -; delta > 0: 14, median 10.49 ATR; not tested (a group is empty or too small for p < 0.05) | **cannot be tested** | cannot be tested | the exact one-sided Mann-Whitney U test (ties as midranks); the delta is the script's bin sums (tick volume); a pair whose next leg began before its window is not counted |
| 12 | after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) | BTC (BTCUSDm) | delta < 0: 19 up legs, median next leg 8.77 ATR; delta > 0: 209, median 8.77 ATR; U 2089, one-sided p = 0.355; 1 left out (began before the window) | delta < 0: 7 up legs, median next leg 7.34 ATR; delta > 0: 85, median 7.99 ATR; U 234, one-sided p = 0.823; 1 left out (began before the window) | **does not hold** | does not hold | the exact one-sided Mann-Whitney U test (ties as midranks); the delta is the script's bin sums (Binance BTCUSDT volume); a pair whose next leg began before its window is not counted |
| 12 | after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) | BTC (BTCUSDm) | delta < 0: 3 up legs, median next leg 7.89 ATR; delta > 0: 50, median 8.93 ATR; U 47, one-sided p = 0.856; 1 left out (began before the window) | delta < 0: 1 up legs, median next leg 8.38 ATR; delta > 0: 18, median 9.42 ATR; U 7, one-sided p = 0.632; not tested (a group is empty or too small for p < 0.05); 1 left out (began before the window) | **cannot be tested** | does not hold | the exact one-sided Mann-Whitney U test (ties as midranks); the delta is the script's bin sums (Binance BTCUSDT volume); a pair whose next leg began before its window is not counted |
| 13 | MSD-F4 makes more net than study 1's F0 row in most pairs | Gold (XAUUSDm) | 25/60 | 9/60 | **does not hold** | holds |  |
| 13 | MSD-F4 makes more net than study 1's F1 row in most pairs | Gold (XAUUSDm) | 47/60 | 1/60 | **mixed** | holds |  |
| 13 | MSD-F4 makes more net than study 1's F2 row in most pairs | Gold (XAUUSDm) | 52/60 | 0/60 | **mixed** | holds |  |
| 13 | the trades MSD-F4 removes from the F0 base lose money (sum < 0) in most pairs | Gold (XAUUSDm) | 28/60 | 14/60 | **does not hold** | - |  |
| 13 | the trades MSD-F4 removes from the F0 base: their number and net (x1.0) | Gold (XAUUSDm) | 21196 trades, net +727 | 7488 trades, net +8,461 | **information** | - | PREREG 8.13: the trades removed and their net |
| 13 | MSD-F6 makes more net than study 1's F0 row in most pairs | Gold (XAUUSDm) | 19/60 | 32/60 | **mixed** | holds |  |
| 13 | MSD-F6 makes more net than study 1's F1 row in most pairs | Gold (XAUUSDm) | 38/60 | 22/60 | **mixed** | holds |  |
| 13 | MSD-F6 makes more net than study 1's F2 row in most pairs | Gold (XAUUSDm) | 33/60 | 30/60 | **mixed** | does not hold |  |
| 13 | the trades MSD-F6 removes from the F0 base lose money (sum < 0) in most pairs | Gold (XAUUSDm) | 29/60 | 36/60 | **mixed** | - |  |
| 13 | the trades MSD-F6 removes from the F0 base: their number and net (x1.0) | Gold (XAUUSDm) | 3478 trades, net -780 | 1136 trades, net -1,734 | **information** | - | PREREG 8.13: the trades removed and their net |
| 13 | MSD-F4 makes more net than study 1's F0 row in most pairs | BTC (BTCUSDm) | 19/60 | 21/60 | **does not hold** | does not hold |  |
| 13 | MSD-F4 makes more net than study 1's F1 row in most pairs | BTC (BTCUSDm) | 10/60 | 12/60 | **does not hold** | does not hold |  |
| 13 | MSD-F4 makes more net than study 1's F2 row in most pairs | BTC (BTCUSDm) | 10/60 | 0/60 | **does not hold** | does not hold |  |
| 13 | the trades MSD-F4 removes from the F0 base lose money (sum < 0) in most pairs | BTC (BTCUSDm) | 37/60 | 20/60 | **mixed** | - |  |
| 13 | the trades MSD-F4 removes from the F0 base: their number and net (x1.0) | BTC (BTCUSDm) | 29090 trades, net -6,643 | 10024 trades, net +4,080 | **information** | - | PREREG 8.13: the trades removed and their net |
| 13 | MSD-F6 makes more net than study 1's F0 row in most pairs | BTC (BTCUSDm) | 49/60 | 25/60 | **mixed** | does not hold |  |
| 13 | MSD-F6 makes more net than study 1's F1 row in most pairs | BTC (BTCUSDm) | 19/60 | 12/60 | **does not hold** | does not hold |  |
| 13 | MSD-F6 makes more net than study 1's F2 row in most pairs | BTC (BTCUSDm) | 14/60 | 20/60 | **does not hold** | does not hold |  |
| 13 | the trades MSD-F6 removes from the F0 base lose money (sum < 0) in most pairs | BTC (BTCUSDm) | 50/60 | 26/60 | **mixed** | - |  |
| 13 | the trades MSD-F6 removes from the F0 base: their number and net (x1.0) | BTC (BTCUSDm) | 4276 trades, net -3,144 | 1818 trades, net -337 | **information** | - | PREREG 8.13: the trades removed and their net |
| 14 | 1H chart, 4H row: the forming-bar score differs from the closed one at some chart closes inside a 4H bar (it can change: a share above 0) | Gold (XAUUSDm) | 4430/17439 chart closes (25.4%); 2415/6301 4H bars change at least once | 1641/6510 chart closes (25.2%); 894/2350 4H bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) | Gold (XAUUSDm) | 5677/22772 chart closes (24.9%); 614/1032 D bars change at least once | 1855/8502 chart closes (21.8%); 183/385 D bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) | Gold (XAUUSDm) | 6332/23523 chart closes (26.9%); 121/208 W bars change at least once | 2472/8799 chart closes (28.1%); 49/78 W bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) | Gold (XAUUSDm) | label 4497/23591 chart closes (19.1%); MSD-A1's side 3398/23591 (14.4%) | label 1558/8800 chart closes (17.7%); MSD-A1's side 1161/8800 (13.2%) | **information** | information | information, no verdict (the claim is about the rows' scores) |
| 14 | 4H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) | Gold (XAUUSDm) | 1309/5365 chart closes (24.4%); 514/1032 D bars change at least once | 429/2001 chart closes (21.4%); 157/385 D bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 4H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) | Gold (XAUUSDm) | 1663/6168 chart closes (27.0%); 113/208 W bars change at least once | 648/2305 chart closes (28.1%); 49/78 W bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 4H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) | Gold (XAUUSDm) | label 1155/6185 chart closes (18.7%); MSD-A1's side 817/6185 (13.2%) | label 328/2305 chart closes (14.2%); MSD-A1's side 260/2305 (11.3%) | **information** | information | information, no verdict (the claim is about the rows' scores) |
| 14 | 1D chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) | Gold (XAUUSDm) | 222/821 chart closes (27.0%); 89/208 W bars change at least once | 90/307 chart closes (29.3%); 39/78 W bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1D chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) | Gold (XAUUSDm) | label 141/823 chart closes (17.1%); MSD-A1's side 96/823 (11.7%) | label 36/307 chart closes (11.7%); MSD-A1's side 24/307 (7.8%) | **information** | information | information, no verdict (the claim is about the rows' scores) |
| 14 | 1H chart, 4H row: the forming-bar score differs from the closed one at some chart closes inside a 4H bar (it can change: a share above 0) | BTC (BTCUSDm) | 6315/26266 chart closes (24.0%); 3344/8757 4H bars change at least once | 2341/9831 chart closes (23.8%); 1244/3279 4H bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) | BTC (BTCUSDm) | 7815/33562 chart closes (23.3%); 736/1460 D bars change at least once | 2831/12566 chart closes (22.5%); 262/547 D bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) | BTC (BTCUSDm) | 6654/34522 chart closes (19.3%); 109/207 W bars change at least once | 2834/13001 chart closes (21.8%); 44/78 W bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) | BTC (BTCUSDm) | label 6971/34809 chart closes (20.0%); MSD-A1's side 5107/34809 (14.7%) | label 2273/13024 chart closes (17.5%); MSD-A1's side 1646/13024 (12.6%) | **information** | information | information, no verdict (the claim is about the rows' scores) |
| 14 | 4H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) | BTC (BTCUSDm) | 1750/7298 chart closes (24.0%); 624/1460 D bars change at least once | 648/2735 chart closes (23.7%); 219/547 D bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 4H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) | BTC (BTCUSDm) | 1655/8478 chart closes (19.5%); 105/207 W bars change at least once | 698/3195 chart closes (21.8%); 42/78 W bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 4H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) | BTC (BTCUSDm) | label 1753/8549 chart closes (20.5%); MSD-A1's side 1237/8549 (14.5%) | label 528/3200 chart closes (16.5%); MSD-A1's side 354/3200 (11.1%) | **information** | information | information, no verdict (the claim is about the rows' scores) |
| 14 | 1D chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) | BTC (BTCUSDm) | 243/1241 chart closes (19.6%); 85/207 W bars change at least once | 100/468 chart closes (21.4%); 33/78 W bars change at least once | **holds** | holds | forming: model B, the row stepped once on its forming candle, the swing vote at the chart close (the live dashboard); closed: the score the row bar ends with, its row_values with the swing vote at its own close (MSD-P8); the part holds where the share is above 0 ('can change' states a possibility) |
| 14 | 1D chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) | BTC (BTCUSDm) | label 227/1252 chart closes (18.1%); MSD-A1's side 157/1252 (12.5%) | label 63/468 chart closes (13.5%); MSD-A1's side 38/468 (8.1%) | **information** | information | information, no verdict (the claim is about the rows' scores) |
| 15 | events per year: the median WY-STD row's entry signals (candidates) a year | Gold (XAUUSDm) | 0.1 | 0.7 | **information** | information | the plan gives no number for 'rare': reported, no verdict |
| 15 | events per year: the median WY-STD row's entry signals (candidates) a year | BTC (BTCUSDm) | 0.9 | 1.3 | **information** | information | the plan gives no number for 'rare': reported, no verdict |
| 15 | when it shows up it means something: the Standard entries beat 1,000 matched random-entry sets (the pooled test, one-sided p < 0.05 on the mean R) | both | 43 trades, mean R -0.270 against a placebo median of -0.041: p = 0.939 | pooled with Development (one test) | **does not hold** | does not hold | one pooled test over Development + Validation (PREREG 6.3), 1000 placebo sets matched on symbol, timeframe, side, stop distance in ATR and holding time (seed 20261128); in dollars per 0.01 lot: +74.08 against a placebo median of -11.15, p = 0.270; 0 trades without a placebo |
| 16 | the stop is closest at the test: the median S-W stop distance (ATR) at test entries is below the SOS and the LPS entries' | both | test 2.90 (n 18), SOS 4.99 (n 14), LPS 6.94 (n 7) | test 2.86 (n 14), SOS 6.23 (n 6), LPS 8.71 (n 4) | **holds** | holds | distance from the decision close to the S-W stop in ATR(14) of the entry bar; entries the guard skips are left out |
| 16 | the test entries earn more: their average R is above the SOS and the LPS entries' | both | test -0.59 (n 18), SOS 0.46 (n 14), LPS 0.31 (n 7) | test -0.23 (n 14), SOS 0.51 (n 6), LPS 0.04 (n 4) | **does not hold** | holds | R = the trade's P/L after costs over its initial risk; the entry type from the trade's tag |
| 17 | 4H and 1D work better than 1H (a larger share of rows with net > 0) | Gold (XAUUSDm) | 1H 17%, 4H 83%, 1D 0% | 1H 67%, 4H 100%, 1D 0% | **does not hold** | does not hold |  |
| 17 | the entries per timeframe: trades (entry signals) | Gold (XAUUSDm) | 1H 34 (34), 4H 14 (14), 1D 0 (0) | 1H 26 (26), 4H 16 (16), 1D 0 (0) | **information** | information | information |
| 17 | 4H and 1D work better than 1H (a larger share of rows with net > 0) | BTC (BTCUSDm) | 1H 67%, 4H 0%, 1D 0% | 1H 0%, 4H 33%, 1D 0% | **does not hold** | does not hold |  |
| 17 | the entries per timeframe: trades (entry signals) | BTC (BTCUSDm) | 1H 104 (104), 4H 40 (40), 1D 0 (0) | 1H 66 (66), 4H 18 (18), 1D 0 (0) | **information** | information | information |
| 18 | the drawn HP-HARMONIC patterns win more often than HP-HC in most pairs | Gold (XAUUSDm) | 6/6 | 5/6 | **holds** | holds |  |
| 18 | the drawn HP-HARMONIC patterns have a higher profit factor than HP-HC in most pairs | Gold (XAUUSDm) | 6/6 | 6/6 | **holds** | holds |  |
| 18 | the drawn HP-HARMONIC patterns win more often than HP-HF in most pairs | Gold (XAUUSDm) | 54/54 | 48/54 | **holds** | holds |  |
| 18 | the drawn HP-HARMONIC patterns have a higher profit factor than HP-HF in most pairs | Gold (XAUUSDm) | 54/54 | 48/54 | **holds** | holds |  |
| 18 | the drawn HP-CHART patterns win more often than HP-CC in most pairs | Gold (XAUUSDm) | 1/4 | 1/4 | **does not hold** | does not hold |  |
| 18 | the drawn HP-CHART patterns have a higher profit factor than HP-CC in most pairs | Gold (XAUUSDm) | 0/4 | 0/4 | **does not hold** | does not hold |  |
| 18 | the drawn HP-CHART patterns win more often than HP-CF in most pairs | Gold (XAUUSDm) | 5/24 | 12/24 | **does not hold** | does not hold |  |
| 18 | the drawn HP-CHART patterns have a higher profit factor than HP-CF in most pairs | Gold (XAUUSDm) | 12/24 | 15/24 | **mixed** | does not hold |  |
| 18 | the drawn HP-HARMONIC patterns win more often than HP-HC in most pairs | BTC (BTCUSDm) | 6/6 | 6/6 | **holds** | holds |  |
| 18 | the drawn HP-HARMONIC patterns have a higher profit factor than HP-HC in most pairs | BTC (BTCUSDm) | 6/6 | 6/6 | **holds** | holds |  |
| 18 | the drawn HP-HARMONIC patterns win more often than HP-HF in most pairs | BTC (BTCUSDm) | 54/54 | 54/54 | **holds** | holds |  |
| 18 | the drawn HP-HARMONIC patterns have a higher profit factor than HP-HF in most pairs | BTC (BTCUSDm) | 54/54 | 53/54 | **holds** | holds |  |
| 18 | the drawn HP-CHART patterns win more often than HP-CC in most pairs | BTC (BTCUSDm) | 0/4 | 0/4 | **does not hold** | does not hold |  |
| 18 | the drawn HP-CHART patterns have a higher profit factor than HP-CC in most pairs | BTC (BTCUSDm) | 0/4 | 0/4 | **does not hold** | does not hold |  |
| 18 | the drawn HP-CHART patterns win more often than HP-CF in most pairs | BTC (BTCUSDm) | 4/24 | 4/24 | **does not hold** | does not hold |  |
| 18 | the drawn HP-CHART patterns have a higher profit factor than HP-CF in most pairs | BTC (BTCUSDm) | 1/24 | 0/24 | **does not hold** | does not hold |  |
| 19 | HP-CS makes more net than HP-CC in most pairs | Gold (XAUUSDm) | 0/2 | 0/2 | **does not hold** | holds |  |
| 19 | HP-CF makes more net than HP-CC in most pairs | Gold (XAUUSDm) | 1/4 | 1/4 | **does not hold** | holds |  |
| 19 | HP-CS makes more net than HP-CC in most pairs | BTC (BTCUSDm) | 1/2 | 0/2 | **does not hold** | does not hold |  |
| 19 | HP-CF makes more net than HP-CC in most pairs | BTC (BTCUSDm) | 2/4 | 1/4 | **does not hold** | does not hold |  |
| 20 | the script's own results (731 trades, 1 in 4 won, average winner 8.5R) | both |  |  | **cannot be tested** | cannot be tested | the script is private: there is no code to run (PREREG 6.9) |
| 20 | our COIL on 4H: profit factor above 1 in most rows | Gold (XAUUSDm) | 2/12 | 12/12 | **mixed** | holds |  |
| 20 | the BIG grade makes more net than no grade in most pairs | Gold (XAUUSDm) | 1/6 | 4/6 | **mixed** | does not hold |  |
| 20 | the VOL grade makes more net than no grade in most pairs | Gold (XAUUSDm) | 0/6 | 2/6 | **does not hold** | does not hold |  |
| 20 | the ADX grade makes more net than no grade in most pairs | Gold (XAUUSDm) | 0/6 | 4/6 | **mixed** | does not hold |  |
| 20 | the ALL3 grade makes more net than no grade in most pairs | Gold (XAUUSDm) | 1/6 | 2/6 | **does not hold** | does not hold |  |
| 20 | our COIL on 4H: profit factor above 1 in most rows | BTC (BTCUSDm) | 6/12 | 7/12 | **mixed** | does not hold |  |
| 20 | the BIG grade makes more net than no grade in most pairs | BTC (BTCUSDm) | 4/6 | 5/6 | **holds** | does not hold |  |
| 20 | the VOL grade makes more net than no grade in most pairs | BTC (BTCUSDm) | 4/6 | 5/6 | **holds** | does not hold |  |
| 20 | the ADX grade makes more net than no grade in most pairs | BTC (BTCUSDm) | 3/6 | 3/6 | **does not hold** | does not hold |  |
| 20 | the ALL3 grade makes more net than no grade in most pairs | BTC (BTCUSDm) | 4/6 | 3/6 | **mixed** | does not hold |  |

**Claim 1.** Ribbon: the trend only flips when the slope and the close-beyond-the-band agree, so it ignores most of the noise (RIB against ALMA-X, same exits).

- RIB takes fewer trades than ALMA-X in every pair (Gold (XAUUSDm)): **holds**.
- RIB makes more net than ALMA-X in most pairs (Gold (XAUUSDm)): **holds**.
- RIB takes fewer trades than ALMA-X in every pair (BTC (BTCUSDm)): **holds**.
- RIB makes more net than ALMA-X in most pairs (BTC (BTCUSDm)): **holds**.

**Claim 2.** Ribbon: take partial profit at the second target and let the rest run (XP against X0 and XT2).

- XP makes more net than X0 in most pairs (Gold (XAUUSDm)): **does not hold**.
- XP makes more net than XT2 in most pairs (Gold (XAUUSDm)): **holds**.
- XP makes more net than X0 in most pairs (BTC (BTCUSDm)): **does not hold**.
- XP makes more net than XT2 in most pairs (BTC (BTCUSDm)): **holds**.

**Claim 3.** Ribbon: the stop never moves; a trade can hit two targets and come back. Manage it (XBE and the HA overlays against X0).

- XBE makes more net than X0 in most pairs (Gold (XAUUSDm)): **mixed**.
- the HA overlays make more net than their RIB X0 base in most pairs (Gold (XAUUSDm)): **does not hold**.
- XBE makes more net than X0 in most pairs (BTC (BTCUSDm)): **mixed**.
- the HA overlays make more net than their RIB X0 base in most pairs (BTC (BTCUSDm)): **mixed**.

**Claim 4.** Heikin Ashi: strong candles, you hold; a run of weak candles or indecision after a strong run, you tighten up (M2 / M3 / M5 against the base).

- M2 makes more net than its base in most pairs (Gold (XAUUSDm)): **does not hold**.
- M2 has a smaller max drawdown than its base in most pairs (Gold (XAUUSDm)): **holds**.
- M3 makes more net than its base in most pairs (Gold (XAUUSDm)): **does not hold**.
- M3 has a smaller max drawdown than its base in most pairs (Gold (XAUUSDm)): **holds**.
- M5 makes more net than its base in most pairs (Gold (XAUUSDm)): **does not hold**.
- M5 has a smaller max drawdown than its base in most pairs (Gold (XAUUSDm)): **holds**.
- M2 makes more net than its base in most pairs (BTC (BTCUSDm)): **does not hold**.
- M2 has a smaller max drawdown than its base in most pairs (BTC (BTCUSDm)): **holds**.
- M3 makes more net than its base in most pairs (BTC (BTCUSDm)): **does not hold**.
- M3 has a smaller max drawdown than its base in most pairs (BTC (BTCUSDm)): **does not hold**.
- M5 makes more net than its base in most pairs (BTC (BTCUSDm)): **mixed**.
- M5 has a smaller max drawdown than its base in most pairs (BTC (BTCUSDm)): **holds**.

**Claim 5.** Heikin Ashi: the panel's 'reached age A, then 5+ more' percentages are calibrated (computed before each year, against that year).

- the panel's 'reached age A, then 5+ more' rates, computed before each year, match that year: the binomial 95% interval around them covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- 1H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- 1H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- 4H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- 4H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- 1D bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- 1D bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (Gold (XAUUSDm)): **holds**.
- the panel's 'reached age A, then 5+ more' rates, computed before each year, match that year: the binomial 95% interval around them covers the year's share in most cells (BTC (BTCUSDm)): **holds**.
- 1H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (BTC (BTCUSDm)): **holds**.
- 1H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (BTC (BTCUSDm)): **holds**.
- 4H bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (BTC (BTCUSDm)): **holds**.
- 4H bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (BTC (BTCUSDm)): **holds**.
- 1D bullish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (BTC (BTCUSDm)): **holds**.
- 1D bearish streaks: the binomial 95% interval around the panel's rate covers the year's share in most cells (BTC (BTCUSDm)): **holds**.

**Claim 6.** ORB: a break of the range often sets the direction for the day.

- the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days (Gold (XAUUSDm)): **holds**.
- the 16:00 close is beyond the first breakout's side more often than beyond the other side (Gold (XAUUSDm)): **holds**.
- the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days (Gold (XAUUSDm)): **holds**.
- the 16:00 close is beyond the first breakout's side more often than beyond the other side (Gold (XAUUSDm)): **holds**.
- the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days (BTC (BTCUSDm)): **holds**.
- the 16:00 close is beyond the first breakout's side more often than beyond the other side (BTC (BTCUSDm)): **holds**.
- the 16:00 close is beyond the range on the first breakout's side on more than half of the breakout days (BTC (BTCUSDm)): **holds**.
- the 16:00 close is beyond the first breakout's side more often than beyond the other side (BTC (BTCUSDm)): **holds**.

**Claim 7.** ORB: take the breakouts that come with high volume (HV against LV, same rule).

- HV makes more net than LV in most pairs (Gold (XAUUSDm)): **mixed**.
- after HV and LV breakouts: the 16:00 close and T1 (information) (Gold (XAUUSDm)): **information**.
- after HV and LV breakouts: the 16:00 close and T1 (information) (Gold (XAUUSDm)): **information**.
- HV makes more net than LV in most pairs (BTC (BTCUSDm)): **mixed**.
- after HV and LV breakouts: the 16:00 close and T1 (information) (BTC (BTCUSDm)): **information**.
- after HV and LV breakouts: the 16:00 close and T1 (information) (BTC (BTCUSDm)): **information**.

**Claim 8.** ORB: the dashboard's hit rates are unconditional, not win rates (and O4 against O2 and O3).

- T1: the rate after a breakout differs from the dashboard's unconditional rate (Gold (XAUUSDm)): **holds**.
- T2: the rate after a breakout differs from the dashboard's unconditional rate (Gold (XAUUSDm)): **holds**.
- T3: the rate after a breakout differs from the dashboard's unconditional rate (Gold (XAUUSDm)): **holds**.
- T1: the rate after a breakout differs from the dashboard's unconditional rate (Gold (XAUUSDm)): **holds**.
- T2: the rate after a breakout differs from the dashboard's unconditional rate (Gold (XAUUSDm)): **holds**.
- T3: the rate after a breakout differs from the dashboard's unconditional rate (Gold (XAUUSDm)): **holds**.
- T1: the rate after a breakout differs from the dashboard's unconditional rate (BTC (BTCUSDm)): **holds**.
- T2: the rate after a breakout differs from the dashboard's unconditional rate (BTC (BTCUSDm)): **holds**.
- T3: the rate after a breakout differs from the dashboard's unconditional rate (BTC (BTCUSDm)): **holds**.
- T1: the rate after a breakout differs from the dashboard's unconditional rate (BTC (BTCUSDm)): **holds**.
- T2: the rate after a breakout differs from the dashboard's unconditional rate (BTC (BTCUSDm)): **holds**.
- T3: the rate after a breakout differs from the dashboard's unconditional rate (BTC (BTCUSDm)): **holds**.
- O4 (the hit-rate target) makes more net than O2 in most pairs (Gold (XAUUSDm)): **does not hold**.
- O4 (the hit-rate target) makes more net than O3 in most pairs (Gold (XAUUSDm)): **mixed**.
- O4 (the hit-rate target) makes more net than O2 in most pairs (BTC (BTCUSDm)): **does not hold**.
- O4 (the hit-rate target) makes more net than O3 in most pairs (BTC (BTCUSDm)): **does not hold**.

**Claim 9.** ORB: the UTC-5 default is an hour late in summer (the literal clock against New York time, O1).

- the literal UTC-5 clock's range starts an hour late (10:30 New York) on every daylight-saving session and on no other (Gold (XAUUSDm)): **holds**.
- O1 on New York time makes more net than on the literal UTC-5 clock on both timeframes (Gold (XAUUSDm)): **mixed**.
- the literal UTC-5 clock's range starts an hour late (10:30 New York) on every daylight-saving session and on no other (BTC (BTCUSDm)): **holds**.
- O1 on New York time makes more net than on the literal UTC-5 clock on both timeframes (BTC (BTCUSDm)): **holds**.

**Claim 10.** Session Hunter: Nasdaq best with a previous-day sweep and the 1H trend held to the close (PF 1.95 on 290 trades, about 3 in 10 win); a smaller forex edge for the London Judas swing; gold and crypto 'nothing held up'; holding to 16:00 tested best.

- the claim-check row has a profit factor above 1 (the author: 1.95) (Nasdaq (USTECm)): **holds**.
- the claim-check row has a profit factor above 1 (the author: 1.95) (Nasdaq (USTECm)): **holds**.
- the claim-check row has a profit factor above 1 (the author: 1.95) (Nasdaq (USTECm)): **holds**.
- the claim-check row has a profit factor above 1 (the author: 1.95) (Nasdaq (USTECm)): **holds**.
- the claim-check row has a profit factor above 1 (the author: 1.95) (EURUSD (EURUSDm)): **mixed**.
- the claim-check row has a profit factor above 1 (the author: 1.95) (GBPUSD (GBPUSDm)): **holds**.
- nothing held up: at most half of the SH rows make money (Gold (XAUUSDm)): **mixed**.
- holding to 16:00 (E1) makes more net than E2 in most pairs (Gold (XAUUSDm)): **holds**.
- holding to 16:00 (E1) makes more net than E3 in most pairs (Gold (XAUUSDm)): **does not hold**.
- PREREG 6.6's hypothesis: AB is positive (most AB rows net > 0) (Gold (XAUUSDm)): **does not hold**.
- PREREG 6.6's hypothesis: AS is negative (most AS rows net < 0) (Gold (XAUUSDm)): **holds**.
- nothing held up: at most half of the SH rows make money (BTC (BTCUSDm)): **mixed**.
- holding to 16:00 (E1) makes more net than E2 in most pairs (BTC (BTCUSDm)): **mixed**.
- holding to 16:00 (E1) makes more net than E3 in most pairs (BTC (BTCUSDm)): **mixed**.

**Claim 11.** Swing Profile: the point of control of the last leg is a level price often comes back to (POC against the 50% level; W1-W3 against their placebo).

- price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) (Gold (XAUUSDm)): **does not hold**.
- price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) (Gold (XAUUSDm)): **information**.
- price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) (Gold (XAUUSDm)): **does not hold**.
- price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) (Gold (XAUUSDm)): **information**.
- price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) (BTC (BTCUSDm)): **mixed**.
- price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) (BTC (BTCUSDm)): **information**.
- price touches the forming leg's POC more often than its 50% level before the leg ends (more legs, and a one-sided sign test p < 0.05 on the legs that touch only one) (BTC (BTCUSDm)): **mixed**.
- price comes back to the last (just-finished) leg's POC more often than to its 50% level before the next leg ends (information) (BTC (BTCUSDm)): **information**.
- the POC rule makes more net than its 50%-level placebo in most pairs (Gold (XAUUSDm)): **mixed**.
- the POC rule makes more net than its 50%-level placebo in most pairs (BTC (BTCUSDm)): **does not hold**.

**Claim 12.** Swing Profile: a leg up with weak buying is a warning (the next leg's size after negative against positive delta).

- after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) (Gold (XAUUSDm)): **does not hold**.
- after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) (Gold (XAUUSDm)): **cannot be tested**.
- after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) (BTC (BTCUSDm)): **does not hold**.
- after an up leg with weak buying (delta < 0) the next leg is larger than after one with delta > 0 (a higher median and a one-sided Mann-Whitney U p < 0.05) (BTC (BTCUSDm)): **cannot be tested**.

**Claim 13.** Dashboard: it filters out a lot of bad trades (MSD-F4 / F6 against the unfiltered and MA200-filtered study-1 rows, pair by pair; the net of the trades they remove).

- MSD-F4 makes more net than study 1's F0 row in most pairs (Gold (XAUUSDm)): **does not hold**.
- MSD-F4 makes more net than study 1's F1 row in most pairs (Gold (XAUUSDm)): **mixed**.
- MSD-F4 makes more net than study 1's F2 row in most pairs (Gold (XAUUSDm)): **mixed**.
- the trades MSD-F4 removes from the F0 base lose money (sum < 0) in most pairs (Gold (XAUUSDm)): **does not hold**.
- the trades MSD-F4 removes from the F0 base: their number and net (x1.0) (Gold (XAUUSDm)): **information**.
- MSD-F6 makes more net than study 1's F0 row in most pairs (Gold (XAUUSDm)): **mixed**.
- MSD-F6 makes more net than study 1's F1 row in most pairs (Gold (XAUUSDm)): **mixed**.
- MSD-F6 makes more net than study 1's F2 row in most pairs (Gold (XAUUSDm)): **mixed**.
- the trades MSD-F6 removes from the F0 base lose money (sum < 0) in most pairs (Gold (XAUUSDm)): **mixed**.
- the trades MSD-F6 removes from the F0 base: their number and net (x1.0) (Gold (XAUUSDm)): **information**.
- MSD-F4 makes more net than study 1's F0 row in most pairs (BTC (BTCUSDm)): **does not hold**.
- MSD-F4 makes more net than study 1's F1 row in most pairs (BTC (BTCUSDm)): **does not hold**.
- MSD-F4 makes more net than study 1's F2 row in most pairs (BTC (BTCUSDm)): **does not hold**.
- the trades MSD-F4 removes from the F0 base lose money (sum < 0) in most pairs (BTC (BTCUSDm)): **mixed**.
- the trades MSD-F4 removes from the F0 base: their number and net (x1.0) (BTC (BTCUSDm)): **information**.
- MSD-F6 makes more net than study 1's F0 row in most pairs (BTC (BTCUSDm)): **mixed**.
- MSD-F6 makes more net than study 1's F1 row in most pairs (BTC (BTCUSDm)): **does not hold**.
- MSD-F6 makes more net than study 1's F2 row in most pairs (BTC (BTCUSDm)): **does not hold**.
- the trades MSD-F6 removes from the F0 base lose money (sum < 0) in most pairs (BTC (BTCUSDm)): **mixed**.
- the trades MSD-F6 removes from the F0 base: their number and net (x1.0) (BTC (BTCUSDm)): **information**.

**Claim 14.** Dashboard: its higher-timeframe rows use the forming candle and can change.

- 1H chart, 4H row: the forming-bar score differs from the closed one at some chart closes inside a 4H bar (it can change: a share above 0) (Gold (XAUUSDm)): **holds**.
- 1H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) (Gold (XAUUSDm)): **holds**.
- 1H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) (Gold (XAUUSDm)): **holds**.
- 1H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) (Gold (XAUUSDm)): **information**.
- 4H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) (Gold (XAUUSDm)): **holds**.
- 4H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) (Gold (XAUUSDm)): **holds**.
- 4H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) (Gold (XAUUSDm)): **information**.
- 1D chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) (Gold (XAUUSDm)): **holds**.
- 1D chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) (Gold (XAUUSDm)): **information**.
- 1H chart, 4H row: the forming-bar score differs from the closed one at some chart closes inside a 4H bar (it can change: a share above 0) (BTC (BTCUSDm)): **holds**.
- 1H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) (BTC (BTCUSDm)): **holds**.
- 1H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) (BTC (BTCUSDm)): **holds**.
- 1H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) (BTC (BTCUSDm)): **information**.
- 4H chart, D row: the forming-bar score differs from the closed one at some chart closes inside a D bar (it can change: a share above 0) (BTC (BTCUSDm)): **holds**.
- 4H chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) (BTC (BTCUSDm)): **holds**.
- 4H chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) (BTC (BTCUSDm)): **information**.
- 1D chart, W row: the forming-bar score differs from the closed one at some chart closes inside a W bar (it can change: a share above 0) (BTC (BTCUSDm)): **holds**.
- 1D chart: the label the live dashboard shows (forming rows, model B) differs from the label the chart's history shows for that bar (closed rows, model A) (information) (BTC (BTCUSDm)): **information**.

**Claim 15.** Wyckoff: it is strict and rare ('when it shows up, it means something'): events per year, and the pooled test with its placebo.

- events per year: the median WY-STD row's entry signals (candidates) a year (Gold (XAUUSDm)): **information**.
- events per year: the median WY-STD row's entry signals (candidates) a year (BTC (BTCUSDm)): **information**.
- when it shows up it means something: the Standard entries beat 1,000 matched random-entry sets (the pooled test, one-sided p < 0.05 on the mean R) (both): **does not hold**.

**Claim 16.** Wyckoff: the risk is smallest at the spring and the test.

- the stop is closest at the test: the median S-W stop distance (ATR) at test entries is below the SOS and the LPS entries' (both): **holds**.
- the test entries earn more: their average R is above the SOS and the LPS entries' (both): **does not hold**.

**Claim 17.** Wyckoff: 'on the 4-hour or the daily' (entries and results by timeframe).

- 4H and 1D work better than 1H (a larger share of rows with net > 0) (Gold (XAUUSDm)): **does not hold**.
- the entries per timeframe: trades (entry signals) (Gold (XAUUSDm)): **information**.
- 4H and 1D work better than 1H (a larger share of rows with net > 0) (BTC (BTCUSDm)): **does not hold**.
- the entries per timeframe: trades (entry signals) (BTC (BTCUSDm)): **information**.

**Claim 18.** Patterns: they are only confirmed when the next swing forms; on an old chart every pattern looks like it caught the exact turn (HP-DRAWN against HP-HC and HP-HF).

- the drawn HP-HARMONIC patterns win more often than HP-HC in most pairs (Gold (XAUUSDm)): **holds**.
- the drawn HP-HARMONIC patterns have a higher profit factor than HP-HC in most pairs (Gold (XAUUSDm)): **holds**.
- the drawn HP-HARMONIC patterns win more often than HP-HF in most pairs (Gold (XAUUSDm)): **holds**.
- the drawn HP-HARMONIC patterns have a higher profit factor than HP-HF in most pairs (Gold (XAUUSDm)): **holds**.
- the drawn HP-CHART patterns win more often than HP-CC in most pairs (Gold (XAUUSDm)): **does not hold**.
- the drawn HP-CHART patterns have a higher profit factor than HP-CC in most pairs (Gold (XAUUSDm)): **does not hold**.
- the drawn HP-CHART patterns win more often than HP-CF in most pairs (Gold (XAUUSDm)): **does not hold**.
- the drawn HP-CHART patterns have a higher profit factor than HP-CF in most pairs (Gold (XAUUSDm)): **mixed**.
- the drawn HP-HARMONIC patterns win more often than HP-HC in most pairs (BTC (BTCUSDm)): **holds**.
- the drawn HP-HARMONIC patterns have a higher profit factor than HP-HC in most pairs (BTC (BTCUSDm)): **holds**.
- the drawn HP-HARMONIC patterns win more often than HP-HF in most pairs (BTC (BTCUSDm)): **holds**.
- the drawn HP-HARMONIC patterns have a higher profit factor than HP-HF in most pairs (BTC (BTCUSDm)): **holds**.
- the drawn HP-CHART patterns win more often than HP-CC in most pairs (BTC (BTCUSDm)): **does not hold**.
- the drawn HP-CHART patterns have a higher profit factor than HP-CC in most pairs (BTC (BTCUSDm)): **does not hold**.
- the drawn HP-CHART patterns win more often than HP-CF in most pairs (BTC (BTCUSDm)): **does not hold**.
- the drawn HP-CHART patterns have a higher profit factor than HP-CF in most pairs (BTC (BTCUSDm)): **does not hold**.

**Claim 19.** Patterns: trade the chart patterns on the breakout, where the entry is real (HP-CS and HP-CF against HP-CC).

- HP-CS makes more net than HP-CC in most pairs (Gold (XAUUSDm)): **does not hold**.
- HP-CF makes more net than HP-CC in most pairs (Gold (XAUUSDm)): **does not hold**.
- HP-CS makes more net than HP-CC in most pairs (BTC (BTCUSDm)): **does not hold**.
- HP-CF makes more net than HP-CC in most pairs (BTC (BTCUSDm)): **does not hold**.

**Claim 20.** Coil Breakout AI: 731 trades on eight coins on 4H since 2021, one in four won, almost three times what it lost, average winner 8.5R; big candle, volume surge and trend strength helped.

- the script's own results (731 trades, 1 in 4 won, average winner 8.5R) (both): **cannot be tested**.
- our COIL on 4H: profit factor above 1 in most rows (Gold (XAUUSDm)): **mixed**.
- the BIG grade makes more net than no grade in most pairs (Gold (XAUUSDm)): **mixed**.
- the VOL grade makes more net than no grade in most pairs (Gold (XAUUSDm)): **does not hold**.
- the ADX grade makes more net than no grade in most pairs (Gold (XAUUSDm)): **mixed**.
- the ALL3 grade makes more net than no grade in most pairs (Gold (XAUUSDm)): **does not hold**.
- our COIL on 4H: profit factor above 1 in most rows (BTC (BTCUSDm)): **mixed**.
- the BIG grade makes more net than no grade in most pairs (BTC (BTCUSDm)): **holds**.
- the VOL grade makes more net than no grade in most pairs (BTC (BTCUSDm)): **holds**.
- the ADX grade makes more net than no grade in most pairs (BTC (BTCUSDm)): **does not hold**.
- the ALL3 grade makes more net than no grade in most pairs (BTC (BTCUSDm)): **mixed**.

## Files

`claims.csv` (Development and Validation), `claims_holdout.csv` (the hold-out, once it exists), `results_dev_val.csv`, `results_holdout.csv`.
