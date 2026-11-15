# Optimiser report: `v4` on XAUUSDm

Everything that has held up so far, combined: entries with the H1 trend, the bot's votes on H1 or H1 + M15, the owner's RSI-extreme entry block and RSI force-close, stop and target in H1 volatility units with an optional dollar cap, at most one MACD-turn ladder add, and a pause after a losing basket. Searched on Jan 2023 - Nov 2026; 2021-2022 is kept for one final test.

|  |  |
|---|---|
| Period | 2023-01-01 → 2026-11-13 in 16 blocks of 3mo |
| Chosen on | 46 months (2023-01 … 2026-10) |
| Held out | nothing: add `--holdout-from` / `--holdout-to` to keep blocks out of the choice |
| Settings | 476 run (400 random, 76 refine) of 9,216 raw combinations in the space |
| Objective | `lcb`: mean net per month minus one standard error |
| Not eligible | a setting that wipes the replayed 2,000 USD account in any selection block, or takes it more than 600 USD below its start (43 of 476) |
| Figures | USD for one fixed 0.01-lot unit on the per-second series, per month, unless they say "account" |
| Shown only | 2026-11: less than half a month inside the period, in monthly.csv but in no statistic |
| Build | engine c3eac9e556f4, live rules ff2eb10cc257, space 7dac5fb9a287, written 2026-11-15 05:54 |

## What to believe

**Not proven.** The best setting passes luck, neighbours; is unclear on halves, walk-forward. Treat the result as a lead, not as an edge.

- **On the months it was chosen on.** The best setting made +101.2 USD a month on average over 46 months, standard error 36.4: a lower bound of +64.8. 29 of 46 months were positive; 604 baskets closed, the worst at -420.2.
- **Luck.** It is the best of 433 eligible settings. If none of them had any edge, the one picked the same way would still show about +41.5 a month (below +85.5 in 95% of such searches), and 1% of such searches reach the objective found here. Luck alone rarely does this well.
- **Half and half.** Over 12,870 ways of splitting the blocks into two halves, the best setting of one half ranked below the median on the other half in 35% of them (0% is ideal, 50% is what noise gives). It averaged +89.0 a month on the half it was chosen on and +33.0 on the other, where it lost money in 13% of the splits.
- **Walk-forward.** Choosing again after every block from the earlier months only, and trading the next block, made +606.2 over 43 months: +14.1 a month, standard error 27.9, 28 of 43 positive. The settings chosen had averaged +47.9 on the months they were chosen on.
- **Neighbours.** 5 of the 12 settings one step away were run: they average an objective of +44.7 against its own +64.8, and 5 of them are positive. It sits on a plateau.

## The top 10 settings

Ranked by the objective on the selection months only. A number in brackets marks a setting that is not eligible.

| # | key | open_weights | entry_agree_s | target_vol | stop_vol | vol_cap_usd_per_unit | max_adds | loss_cooldown_s | entry_rsi_block_tfs | fc_rsi_tfs | force_close_enabled | neighbours run | their objective |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `sea3e1314f21` | H1 | 0 | 10 | 8 | 0 | 1 | 14400 | none | – | false | 5 of 12 | +44.7 |
| 2 | `s172e72d3a77` | H1 | 0 | 10 | 8 | 12 | 1 | 14400 | none | – | false | 12 of 12 | +35.8 |
| 3 | `s3ef901c9387` | H1 | 0 | 8 | 4 | 12 | 0 | 43200 | none | – | false | 11 of 11 | +31.2 |
| 4 | `s3416da609ac` | H1 | 0 | 10 | 4 | 12 | 0 | 43200 | none | – | false | 10 of 10 | +28.3 |
| 5 | `sff12e2d213a` | H1 | 0 | 8 | 6 | 12 | 0 | 43200 | none | – | false | 12 of 12 | +33.0 |
| 6 | `sae21cb3406d` | H1 | 0 | 10 | 8 | 12 | 1 | 3600 | none | – | false | 4 of 11 | +42.1 |
| 7 | `s1ea97c69953` | H1 | 0 | 10 | 8 | 12 | 1 | 43200 | none | – | false | 2 of 11 | +49.7 |
| 8 | `s94975dcba80` | H1+M15 | 2 | 8 | 8 | 0 | 1 | 14400 | none | – | false | 13 of 13 | +28.9 |
| 9 | `s086e52ccbc0` | H1 | 0 | 10 | 10 | 12 | 1 | 14400 | none | – | false | 4 of 11 | +32.8 |
| 10 | `saf2ffb47de2` | H1 | 2 | 8 | 8 | 12 | 1 | 14400 | none | – | false | 13 of 13 | +32.8 |

### Selection

| # | mean / month | ± SE | lower bound | worst block | months up | baskets / month | worst basket | account |
|---|---|---|---|---|---|---|---|---|
| 1 | +101.2 | 36.4 | +64.8 | -175.8 | 29 of 46 | 13.0 | -420.2 | dip 453 |
| 2 | +78.6 | 23.5 | +55.1 | -175.8 | 29 of 46 | 13.2 | -113.8 | dip 453 |
| 3 | +71.4 | 19.0 | +52.4 | -94.2 | 30 of 46 | 13.6 | -61.3 | dip 211 |
| 4 | +68.7 | 17.2 | +51.6 | -79.4 | 28 of 46 | 12.0 | -55.2 | dip 267 |
| 5 | +70.0 | 19.6 | +50.3 | -113.9 | 30 of 46 | 12.2 | -81.8 | dip 239 |
| 6 | +71.9 | 21.8 | +50.1 | -207.0 | 33 of 46 | 14.0 | -113.8 | dip 274 |
| 7 | +70.9 | 22.4 | +48.6 | -177.9 | 27 of 46 | 11.6 | -113.8 | dip 508 |
| 8 | +78.9 | 32.3 | +46.6 | -75.2 | 30 of 46 | 18.1 | -392.7 | dip 207 |
| 9 | +73.2 | 26.9 | +46.4 | -184.1 | 27 of 46 | 12.3 | -132.9 | dip 461 |
| 10 | +67.0 | 21.0 | +46.0 | -157.4 | 33 of 46 | 11.7 | -102.3 | dip 310 |
| live (reference) | -289.0 | 65.4 | -354.4 | -2,041.6 | 12 of 46 | 839.6 | -1,687.1 | wiped in 4 |
| V3-lite (reference) | +82.0 | 19.2 | +62.8 | -9.1 | 34 of 46 | 8.6 | -393.7 | dip 398 |
| Owner's rules + H1 trend + 4 h pause (reference) | -3.2 | 13.3 | -16.4 | -346.2 | 27 of 46 | 74.7 | -277.3 | dip 451 |

"account" is the replay of the same baskets on 2,000 USD with the bot's unit rule, a fresh account in every block: the deepest it stood below its start, or in how many blocks it was wiped. References are named in the space file (overrides on the live settings) and are never candidates.

### Block by block

| # | 2023-01-01 → | 2023-04-01 → | 2023-07-01 → | 2023-10-01 → | 2024-01-01 → | 2024-04-01 → | 2024-07-01 → | 2024-10-01 → | 2025-01-01 → | 2025-04-01 → | 2025-07-01 → | 2025-10-01 → | 2026-01-01 → | 2026-04-01 → | 2026-07-01 → | 2026-10-01 → |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | -41 | -70 | +18 | +30 | -31 | +262 | +26 | +260 | +64 | +246 | +467 | +906 | +2,240 | -29 | +483 | -318 |
| 2 | -41 | -70 | +18 | +30 | -31 | +262 | +26 | +260 | +64 | +244 | +467 | +600 | +1,171 | +307 | +483 | -318 |
| 3 | +51 | -16 | -94 | +143 | +8 | +138 | +93 | +150 | +128 | +422 | +175 | +363 | +1,069 | +119 | +575 | -204 |
| 4 | +65 | +4 | -79 | +57 | +52 | +167 | +2 | +177 | +127 | +391 | +275 | +383 | +739 | +98 | +767 | -260 |
| 5 | +52 | -114 | +55 | +261 | +109 | +136 | +146 | -15 | +85 | +332 | +93 | +308 | +914 | +652 | +191 | -232 |
| 6 | -2 | -207 | +19 | +98 | +3 | +219 | +10 | +201 | +79 | +215 | +402 | +836 | +886 | +197 | +443 | -131 |
| 7 | -53 | -136 | +30 | +88 | +7 | +168 | +87 | +265 | +6 | +168 | +420 | +212 | +1,289 | +336 | +555 | -501 |
| 8 | -75 | +36 | +2 | +167 | +52 | -75 | +210 | +356 | +55 | +487 | +412 | +672 | +702 | +615 | +39 | +265 |
| 9 | -15 | -184 | -67 | +296 | +145 | +344 | +44 | +251 | -71 | +97 | +284 | +741 | +1,122 | +236 | +294 | -85 |
| 10 | +92 | -8 | +49 | +110 | -142 | +25 | +65 | +313 | +140 | +250 | +92 | +492 | +582 | +643 | +537 | -310 |
| live (reference) | -2,042 | +118 | -1,051 | -786 | -917 | -974 | -520 | -657 | -775 | -53 | -863 | -1,235 | -919 | -2,041 | -802 | -163 |
| V3-lite (reference) | +83 | +41 | +30 | +231 | +97 | +63 | -9 | +236 | +72 | +404 | +3 | +562 | +1,034 | +681 | +227 | -157 |
| Owner's rules + H1 trend + 4 h pause (reference) | -263 | +1 | -100 | +49 | +32 | -119 | -27 | -161 | +129 | +65 | +185 | +207 | +327 | -346 | -18 | -27 |

Net of each block, named by the day it starts. A result that comes from one block is one event, not an edge.

## Is the best result more than luck?

|  | mean / month | objective |
|---|---|---|
| the best setting | +101.2 | +64.8 |
| the best of 433 settings without any edge, on average | +41.5 | +19.7 |
| … 95% of the time below | +85.5 |  |
| … if the 433 settings were unrelated to each other | +49.8 |  |

Searches without any edge that reach the objective found here: **1%**. The settings are alike: they spread their best results like about 36 unrelated ones. (2,000 resamples of the months, every setting with its own average taken away.)

## Does choosing on one half work on the other?

Chosen among the 400 settings of the sample. The 76 settings added by refinement are left out here: what to refine was decided by looking at every selection month.

|  |  |
|---|---|
| Splits of the blocks into two halves | 12,870 |
| Best of one half below the median of the other (probability of overfitting) | **35%** |
| Its typical rank on the other half (0% worst, 100% best) | 77% |
| Its mean / month on the half it was chosen on | +89.0 |
| Its mean / month on the other half | +33.0 |
| Splits in which it lost money on the other half | 13% |
| Splits in which the replayed account was wiped on the other half | 0% |

## Walk-forward: choosing with past data only

Chosen among the 400 settings of the sample. The 76 settings added by refinement are left out here: what to refine was decided by looking at every selection month.

| chosen on everything before | setting chosen | its objective then | its mean / month then | block traded | net by month | together | account |
|---|---|---|---|---|---|---|---|
| 2023-04-01 | #94 `se8a853b82b3` | +47.7 | +56.4 | 2023-04-01 → 2023-07-01 | -22 +39 +53 | +70 |  |
| 2023-07-01 | #94 `se8a853b82b3` | +26.6 | +39.8 | 2023-07-01 → 2023-10-01 | +7 +11 +1 | +18 |  |
| 2023-10-01 | #94 `se8a853b82b3` | +18.3 | +28.5 | 2023-10-01 → 2024-01-01 | +17 +62 +54 | +133 |  |
| 2024-01-01 | #94 `se8a853b82b3` | +24.1 | +32.5 | 2024-01-01 → 2024-04-01 | +72 +52 +64 | +188 |  |
| 2024-04-01 | #94 `se8a853b82b3` | +31.0 | +38.5 | 2024-04-01 → 2024-07-01 | +151 -0 -36 | +115 |  |
| 2024-07-01 | #150 `s20d41f6ef6a` | +31.5 | +41.9 | 2024-07-01 → 2024-10-01 | +44 -166 -4 | -125 |  |
| 2024-10-01 | #150 `s20d41f6ef6a` | +16.6 | +30.0 | 2024-10-01 → 2025-01-01 | +9 +23 -70 | -38 |  |
| 2025-01-01 | #(449) `se3c0e72f316` | +18.0 | +31.7 | 2025-01-01 → 2025-04-01 | +49 -12 +13 | +50 |  |
| 2025-04-01 | #(459) `s2204a6e450d` | +19.1 | +35.1 | 2025-04-01 → 2025-07-01 | +13 -181 +70 | -98 |  |
| 2025-07-01 | #(454) `s1a733118266` | +24.6 | +40.1 | 2025-07-01 → 2025-10-01 | +88 -73 +281 | +296 |  |
| 2025-10-01 | #(454) `s1a733118266` | +29.1 | +45.4 | 2025-10-01 → 2026-01-01 | +382 -148 +114 | +348 |  |
| 2026-01-01 | #(447) `sd823f36806c` | +33.3 | +54.0 | 2026-01-01 → 2026-04-01 | +40 -466 +249 | -177 |  |
| 2026-04-01 | #88 `s2127f767ad9` | +53.6 | +85.6 | 2026-04-01 → 2026-07-01 | +332 -106 +37 | +264 |  |
| 2026-07-01 | #88 `s2127f767ad9` | +55.1 | +85.8 | 2026-07-01 → 2026-10-01 | -570 +457 -287 | -400 |  |
| 2026-10-01 | #3 `s3ef901c9387` | +54.6 | +73.8 | 2026-10-01 → 2026-11-13 | -38 | -38 |  |

| over the 43 months traded | mean / month | ± SE | total |
|---|---|---|---|
| re-chosen after every block (out of sample) | +14.1 | 27.9 | +606.2 |
| the final best setting on the same months (hindsight: they helped choose it) | +109.2 |  |  |
| the average setting of the sample on the same months | +15.4 |  |  |
| live (reference) on the same months | -261.6 |  |  |
| V3-lite (reference) on the same months | +85.8 |  |  |
| Owner's rules + H1 trend + 4 h pause (reference) on the same months | +2.7 |  |  |

## Stability

### Average by parameter value

| parameter | value | settings | average objective | average mean / month | with a positive mean | eligible |
|---|---|---|---|---|---|---|
| open_weights | H1 | 200 | -0.7 | +11.8 | 57% | 88% |
| open_weights | H1+M15 | 200 | -0.2 | +16.5 | 72% | 94% |
| entry_agree_s | 0 | 200 | +1.4 | +16.7 | 70% | 92% |
| entry_agree_s | 2 | 200 | -2.3 | +11.6 | 60% | 90% |
| target_vol | 4 | 100 | -2.7 | +10.0 | 70% | 95% |
| target_vol | 6 | 100 | -4.4 | +8.9 | 56% | 91% |
| target_vol | 8 | 100 | +2.7 | +18.8 | 66% | 94% |
| target_vol | 10 | 100 | +2.6 | +19.0 | 67% | 84% |
| stop_vol | 4 | 100 | -1.6 | +11.6 | 62% | 97% |
| stop_vol | 6 | 100 | -1.7 | +12.1 | 58% | 95% |
| stop_vol | 8 | 100 | +1.7 | +17.1 | 68% | 92% |
| stop_vol | 10 | 100 | -0.2 | +15.8 | 71% | 80% |
| vol_cap_usd_per_unit | 0 | 133 | -2.0 | +13.0 | 63% | 83% |
| vol_cap_usd_per_unit | 12 | 133 | +2.6 | +17.7 | 72% | 98% |
| vol_cap_usd_per_unit | 20 | 134 | -1.9 | +11.7 | 59% | 92% |
| max_adds | 0 | 200 | -0.1 | +13.5 | 66% | 90% |
| max_adds | 1 | 200 | -0.8 | +14.7 | 64% | 92% |
| loss_cooldown_s | 3600 | 133 | -1.1 | +13.5 | 64% | 86% |
| loss_cooldown_s | 14400 | 134 | +1.2 | +16.7 | 67% | 90% |
| loss_cooldown_s | 43200 | 133 | -1.4 | +12.1 | 63% | 97% |
| entry_rsi_block_tfs | none | 200 | +4.7 | +21.7 | 76% | 87% |
| entry_rsi_block_tfs | H1+H4 | 200 | -5.5 | +6.5 | 53% | 95% |
| fc_rsi_tfs | none | 100 | -10.7 | -1.3 | 34% | 100% |
| fc_rsi_tfs | H1+H4 | 100 | -11.5 | -2.3 | 32% | 100% |
| force_close_enabled | false | 200 | +10.2 | +30.1 | 96% | 82% |
| force_close_enabled | true | 200 | -11.1 | -1.8 | 33% | 100% |

Over the settings of the grid or random sample that contain the value (refinement crowds around the best and is left out; so is a setting in which a condition switched the parameter off). A value that is good on average over everything it was combined with is worth more than one good row.

## Reproduce

The best setting on the real account over the selection period (one run, the unit stepping with the balance):

```
python -m backtesting run --symbol XAUUSDm --start 2023-01-01 --end 2026-11-13 --set entry_agree_s=0.0 --set 'entry_rsi_block_mode="any"' --set entry_rsi_block_tfs=null --set force_close_enabled=false --set ladder_gap_vol=1.0 --set 'ladder_multipliers=[1.0, 1.0, 1.0, 1.0]' --set 'ladder_tfs=["M5", "M15", "H1", "H1", "H1"]' --set 'ladder_trigger="macd_turn"' --set loss_cooldown_s=14400.0 --set max_adds=1 --set 'open_weights={"H1": 1}' --set stop_loss_usd_per_unit=null --set stop_vol=8.0 --set target_usd_per_unit=null --set target_vol=10.0 --set 'trend_tf="H1"' --set vol_cap_usd_per_unit=0.0 --set vol_len=24 --set 'vol_tf="H1"'
```

Its last selection block exactly as measured here (stored net -318.35):

```
python -m backtesting run --symbol XAUUSDm --start '2026-10-01 00:00:00' --end '2026-11-13 00:00:00' --balance 1000000 --set fixed_units=1 --set entry_agree_s=0.0 --set 'entry_rsi_block_mode="any"' --set entry_rsi_block_tfs=null --set force_close_enabled=false --set ladder_gap_vol=1.0 --set 'ladder_multipliers=[1.0, 1.0, 1.0, 1.0]' --set 'ladder_tfs=["M5", "M15", "H1", "H1", "H1"]' --set 'ladder_trigger="macd_turn"' --set loss_cooldown_s=14400.0 --set max_adds=1 --set 'open_weights={"H1": 1}' --set stop_loss_usd_per_unit=null --set stop_vol=8.0 --set target_usd_per_unit=null --set target_vol=10.0 --set 'trend_tf="H1"' --set vol_cap_usd_per_unit=0.0 --set vol_len=24 --set 'vol_tf="H1"'
```

Files next to this report: `trials.csv` (every setting), `monthly.csv` (settings x months), `best.json`, `evaluations.jsonl` (raw results; the same command continues an interrupted run). How to read all of this: `backtesting/OPTIMISER.md`.

