# Optimiser report: `v4` on BTCUSDm

Everything that has held up so far, combined: entries with the H1 trend, the bot's votes on H1 or H1 + M15, the owner's RSI-extreme entry block and RSI force-close, stop and target in H1 volatility units with an optional dollar cap, at most one MACD-turn ladder add, and a pause after a losing basket. Searched on Jan 2023 - Nov 2026; 2021-2022 is kept for one final test.

|  |  |
|---|---|
| Period | 2023-01-01 → 2026-11-13 in 16 blocks of 3mo |
| Chosen on | 46 months (2023-01 … 2026-10) |
| Held out | nothing: add `--holdout-from` / `--holdout-to` to keep blocks out of the choice |
| Settings | 490 run (400 random, 90 refine) of 9,216 raw combinations in the space |
| Objective | `lcb`: mean net per month minus one standard error |
| Not eligible | a setting that wipes the replayed 2,000 USD account in any selection block, or takes it more than 600 USD below its start (0 of 490) |
| Figures | USD for one fixed 0.01-lot unit on the per-second series, per month, unless they say "account" |
| Shown only | 2026-11: less than half a month inside the period, in monthly.csv but in no statistic |
| Build | engine c3eac9e556f4, live rules ff2eb10cc257, space 7dac5fb9a287, written 2026-11-15 07:10 |

## What to believe

**Not proven.** The best setting passes luck, halves, neighbours; is unclear on walk-forward. Treat the result as a lead, not as an edge.

- **On the months it was chosen on.** The best setting made +29.6 USD a month on average over 46 months, standard error 10.0: a lower bound of +19.6. 30 of 46 months were positive; 660 baskets closed, the worst at -52.6.
- **Luck.** It is the best of 490 eligible settings. If none of them had any edge, the one picked the same way would still show about +19.3 a month (below +37.7 in 95% of such searches), and 10% of such searches reach the objective found here. Luck alone rarely does this well.
- **Half and half.** Over 12,870 ways of splitting the blocks into two halves, the best setting of one half ranked below the median on the other half in 17% of them (0% is ideal, 50% is what noise gives). It averaged +36.2 a month on the half it was chosen on and +15.1 on the other, where it lost money in 11% of the splits.
- **Walk-forward.** Choosing again after every block from the earlier months only, and trading the next block, made +366.5 over 43 months: +8.5 a month, standard error 10.3, 23 of 43 positive. The settings chosen had averaged +26.8 on the months they were chosen on.
- **Neighbours.** 13 of the 13 settings one step away were run: they average an objective of +10.0 against its own +19.6, and 11 of them are positive. It sits on a plateau.

## The top 10 settings

Ranked by the objective on the selection months only. A number in brackets marks a setting that is not eligible.

| # | key | open_weights | entry_agree_s | target_vol | stop_vol | vol_cap_usd_per_unit | max_adds | loss_cooldown_s | entry_rsi_block_tfs | fc_rsi_tfs | force_close_enabled | neighbours run | their objective |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `sbebda41d64c` | H1 | 0 | 8 | 8 | 20 | 0 | 14400 | none | – | false | 13 of 13 | +10.0 |
| 2 | `s6d84b0465d2` | H1 | 0 | 8 | 8 | 12 | 0 | 14400 | none | – | false | 13 of 13 | +10.0 |
| 3 | `sb6232ea6ed6` | H1 | 0 | 8 | 8 | 0 | 0 | 14400 | none | – | false | 6 of 13 | +15.6 |
| 4 | `s10bdb256b0a` | H1 | 0 | 10 | 8 | 20 | 0 | 14400 | none | – | false | 12 of 12 | +7.5 |
| 5 | `s87fb6be16d5` | H1 | 0 | 10 | 8 | 0 | 0 | 14400 | none | – | false | 12 of 12 | +7.5 |
| 6 | `s09784659eeb` | H1 | 0 | 10 | 8 | 12 | 0 | 14400 | none | – | false | 12 of 12 | +7.5 |
| 7 | `s5ab9c0ebda6` | H1+M15 | 0 | 8 | 8 | 0 | 0 | 14400 | none | – | false | 5 of 13 | +17.0 |
| 8 | `sf4e724d552c` | H1+M15 | 0 | 8 | 8 | 20 | 0 | 14400 | none | – | false | 5 of 13 | +17.0 |
| 9 | `s143dbea0230` | H1+M15 | 0 | 8 | 8 | 12 | 0 | 14400 | none | – | false | 6 of 13 | +13.7 |
| 10 | `s8e0c4c3388d` | H1+M15 | 0 | 8 | 6 | 0 | 0 | 14400 | none | – | false | 13 of 13 | +4.7 |

### Selection

| # | mean / month | ± SE | lower bound | worst block | months up | baskets / month | worst basket | account |
|---|---|---|---|---|---|---|---|---|
| 1 | +29.6 | 10.0 | +19.6 | -53.0 | 30 of 46 | 14.2 | -52.6 | dip 133 |
| 2 | +29.6 | 10.0 | +19.6 | -53.0 | 30 of 46 | 14.2 | -52.6 | dip 133 |
| 3 | +29.6 | 10.0 | +19.6 | -53.0 | 30 of 46 | 14.2 | -52.6 | dip 133 |
| 4 | +30.3 | 11.1 | +19.1 | -93.0 | 30 of 46 | 11.6 | -51.5 | dip 145 |
| 5 | +30.3 | 11.1 | +19.1 | -93.0 | 30 of 46 | 11.6 | -51.5 | dip 145 |
| 6 | +30.3 | 11.1 | +19.1 | -93.0 | 30 of 46 | 11.6 | -51.5 | dip 145 |
| 7 | +30.3 | 12.5 | +17.9 | -65.4 | 27 of 46 | 16.2 | -75.0 | dip 119 |
| 8 | +30.3 | 12.5 | +17.9 | -65.4 | 27 of 46 | 16.2 | -75.0 | dip 119 |
| 9 | +30.3 | 12.5 | +17.9 | -65.4 | 27 of 46 | 16.2 | -75.0 | dip 119 |
| 10 | +29.4 | 12.2 | +17.2 | -101.7 | 29 of 46 | 19.6 | -56.0 | dip 163 |
| live (reference) | -546.5 | 71.4 | -618.0 | -3,401.2 | 4 of 46 | 747.5 | -1,158.5 | wiped in 7 |
| V3-lite (reference) | +15.7 | 12.1 | +3.5 | -120.5 | 25 of 46 | 12.0 | -50.6 | dip 140 |
| Owner's rules + H1 trend + 4 h pause (reference) | -37.9 | 9.6 | -47.5 | -394.7 | 16 of 46 | 75.8 | -172.2 | dip 438 |

"account" is the replay of the same baskets on 2,000 USD with the bot's unit rule, a fresh account in every block: the deepest it stood below its start, or in how many blocks it was wiped. References are named in the space file (overrides on the live settings) and are never candidates.

### Block by block

| # | 2023-01-01 → | 2023-04-01 → | 2023-07-01 → | 2023-10-01 → | 2024-01-01 → | 2024-04-01 → | 2024-07-01 → | 2024-10-01 → | 2025-01-01 → | 2025-04-01 → | 2025-07-01 → | 2025-10-01 → | 2026-01-01 → | 2026-04-01 → | 2026-07-01 → | 2026-10-01 → |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | +111 | -53 | -26 | +62 | +172 | +9 | -13 | +146 | +121 | -26 | +104 | +419 | +122 | +158 | +19 | +98 |
| 2 | +111 | -53 | -26 | +62 | +172 | +9 | -13 | +146 | +121 | -26 | +104 | +419 | +122 | +158 | +19 | +98 |
| 3 | +111 | -53 | -26 | +62 | +172 | +9 | -13 | +146 | +121 | -26 | +104 | +419 | +122 | +158 | +19 | +98 |
| 4 | +86 | -65 | -18 | +42 | +237 | -63 | +58 | +358 | +324 | -38 | +28 | +350 | +114 | +121 | -93 | -71 |
| 5 | +86 | -65 | -18 | +42 | +237 | -63 | +58 | +358 | +324 | -38 | +28 | +350 | +114 | +121 | -93 | -71 |
| 6 | +86 | -65 | -18 | +42 | +237 | -63 | +58 | +358 | +324 | -38 | +28 | +350 | +114 | +121 | -93 | -71 |
| 7 | +112 | -33 | -34 | +17 | +46 | +25 | -14 | +425 | +186 | -65 | -3 | +392 | +124 | +145 | +22 | +35 |
| 8 | +112 | -33 | -34 | +17 | +46 | +25 | -14 | +425 | +186 | -65 | -3 | +392 | +124 | +145 | +22 | +35 |
| 9 | +112 | -33 | -34 | +17 | +46 | +25 | -14 | +425 | +186 | -65 | -3 | +392 | +124 | +145 | +22 | +35 |
| 10 | +53 | -14 | -50 | -26 | -13 | -102 | +47 | +391 | +271 | +118 | -28 | +408 | +306 | -31 | +11 | -25 |
| live (reference) | -1,649 | -1,755 | -713 | -1,219 | -2,396 | -2,217 | -2,881 | -2,508 | -3,401 | -2,315 | -2,054 | -915 | -1,005 | -140 | -2 | +16 |
| V3-lite (reference) | +61 | -47 | -35 | +21 | +182 | -59 | -8 | +240 | +38 | -121 | -11 | +467 | -67 | +101 | -99 | +71 |
| Owner's rules + H1 trend + 4 h pause (reference) | -46 | -202 | -133 | -110 | -244 | -395 | -306 | -91 | -40 | -64 | -22 | +85 | +10 | -81 | -115 | +29 |

Net of each block, named by the day it starts. A result that comes from one block is one event, not an edge.

## Is the best result more than luck?

|  | mean / month | objective |
|---|---|---|
| the best setting | +29.6 | +19.6 |
| the best of 490 settings without any edge, on average | +19.3 | +9.0 |
| … 95% of the time below | +37.7 |  |
| … if the 490 settings were unrelated to each other | +26.7 |  |

Searches without any edge that reach the objective found here: **10%**. The settings are alike: they spread their best results like about 23 unrelated ones. (2,000 resamples of the months, every setting with its own average taken away.)

## Does choosing on one half work on the other?

Chosen among the 400 settings of the sample. The 90 settings added by refinement are left out here: what to refine was decided by looking at every selection month.

|  |  |
|---|---|
| Splits of the blocks into two halves | 12,870 |
| Best of one half below the median of the other (probability of overfitting) | **17%** |
| Its typical rank on the other half (0% worst, 100% best) | 84% |
| Its mean / month on the half it was chosen on | +36.2 |
| Its mean / month on the other half | +15.1 |
| Splits in which it lost money on the other half | 11% |
| Splits in which the replayed account was wiped on the other half | 0% |

## Walk-forward: choosing with past data only

Chosen among the 400 settings of the sample. The 90 settings added by refinement are left out here: what to refine was decided by looking at every selection month.

| chosen on everything before | setting chosen | its objective then | its mean / month then | block traded | net by month | together | account |
|---|---|---|---|---|---|---|---|
| 2023-04-01 | #92 `s00a012fdec8` | +28.2 | +45.9 | 2023-04-01 → 2023-07-01 | -34 -20 +17 | -37 |  |
| 2023-07-01 | #256 `s6f260aba46a` | +6.6 | +19.4 | 2023-07-01 → 2023-10-01 | -22 -12 -18 | -52 |  |
| 2023-10-01 | #294 `s1a5ec4d32ea` | -2.6 | +6.4 | 2023-10-01 → 2024-01-01 | +67 -49 -38 | -20 |  |
| 2024-01-01 | #280 `s4e864196c8e` | -0.0 | +8.4 | 2024-01-01 → 2024-04-01 | -18 +116 -179 | -81 |  |
| 2024-04-01 | #51 `s9f0e0dfd6f3` | +10.8 | +24.1 | 2024-04-01 → 2024-07-01 | +29 -70 -17 | -58 |  |
| 2024-07-01 | #26 `s711f54c4c32` | +5.3 | +20.0 | 2024-07-01 → 2024-10-01 | -39 +2 +30 | -7 |  |
| 2024-10-01 | #51 `s9f0e0dfd6f3` | +8.8 | +19.6 | 2024-10-01 → 2025-01-01 | +24 +56 +48 | +129 |  |
| 2025-01-01 | #51 `s9f0e0dfd6f3` | +12.9 | +22.5 | 2025-01-01 → 2025-04-01 | +65 +52 -57 | +60 |  |
| 2025-04-01 | #4 `s10bdb256b0a` | +20.8 | +35.5 | 2025-04-01 → 2025-07-01 | +10 -1 -47 | -38 |  |
| 2025-07-01 | #4 `s10bdb256b0a` | +17.1 | +30.7 | 2025-07-01 → 2025-10-01 | +14 -17 +31 | +28 |  |
| 2025-10-01 | #4 `s10bdb256b0a` | +16.3 | +28.8 | 2025-10-01 → 2026-01-01 | +101 +268 -19 | +350 |  |
| 2026-01-01 | #4 `s10bdb256b0a` | +22.7 | +36.1 | 2026-01-01 → 2026-04-01 | +14 +83 +17 | +114 |  |
| 2026-04-01 | #4 `s10bdb256b0a` | +23.8 | +36.2 | 2026-04-01 → 2026-07-01 | +37 +49 +35 | +121 |  |
| 2026-07-01 | #4 `s10bdb256b0a` | +25.0 | +36.5 | 2026-07-01 → 2026-10-01 | -105 +33 -22 | -93 |  |
| 2026-10-01 | #4 `s10bdb256b0a` | +20.8 | +32.0 | 2026-10-01 → 2026-11-13 | -49 | -49 |  |

| over the 43 months traded | mean / month | ± SE | total |
|---|---|---|---|
| re-chosen after every block (out of sample) | +8.5 | 10.3 | +366.5 |
| the final best setting on the same months (hindsight: they helped choose it) | +29.0 |  |  |
| the average setting of the sample on the same months | +1.1 |  |  |
| live (reference) on the same months | -546.3 |  |  |
| V3-lite (reference) on the same months | +15.3 |  |  |
| Owner's rules + H1 trend + 4 h pause (reference) on the same months | -39.4 |  |  |

## Stability

### Average by parameter value

| parameter | value | settings | average objective | average mean / month | with a positive mean | eligible |
|---|---|---|---|---|---|---|
| open_weights | H1 | 200 | -1.9 | +5.0 | 74% | 100% |
| open_weights | H1+M15 | 200 | -10.9 | -3.1 | 32% | 100% |
| entry_agree_s | 0 | 200 | -7.8 | -0.2 | 50% | 100% |
| entry_agree_s | 2 | 200 | -5.0 | +2.1 | 56% | 100% |
| target_vol | 4 | 100 | -7.7 | -1.6 | 46% | 100% |
| target_vol | 6 | 100 | -8.3 | -1.7 | 48% | 100% |
| target_vol | 8 | 100 | -6.2 | +2.0 | 54% | 100% |
| target_vol | 10 | 100 | -3.5 | +5.1 | 64% | 100% |
| stop_vol | 4 | 100 | -6.9 | -0.4 | 52% | 100% |
| stop_vol | 6 | 100 | -4.8 | +2.2 | 63% | 100% |
| stop_vol | 8 | 100 | -7.8 | -0.0 | 43% | 100% |
| stop_vol | 10 | 100 | -6.2 | +2.0 | 54% | 100% |
| vol_cap_usd_per_unit | 0 | 133 | -4.7 | +3.0 | 63% | 100% |
| vol_cap_usd_per_unit | 12 | 133 | -8.2 | -0.9 | 42% | 100% |
| vol_cap_usd_per_unit | 20 | 134 | -6.3 | +0.7 | 54% | 100% |
| max_adds | 0 | 200 | -4.8 | +2.2 | 58% | 100% |
| max_adds | 1 | 200 | -8.0 | -0.4 | 48% | 100% |
| loss_cooldown_s | 3600 | 133 | -7.1 | +0.3 | 49% | 100% |
| loss_cooldown_s | 14400 | 134 | -6.5 | +1.1 | 51% | 100% |
| loss_cooldown_s | 43200 | 133 | -5.6 | +1.4 | 59% | 100% |
| entry_rsi_block_tfs | none | 200 | -9.2 | -1.1 | 44% | 100% |
| entry_rsi_block_tfs | H1+H4 | 200 | -3.6 | +3.0 | 62% | 100% |
| fc_rsi_tfs | none | 100 | -10.1 | -6.0 | 22% | 100% |
| fc_rsi_tfs | H1+H4 | 100 | -9.6 | -5.7 | 24% | 100% |
| force_close_enabled | false | 200 | -3.0 | +7.7 | 83% | 100% |
| force_close_enabled | true | 200 | -9.8 | -5.8 | 23% | 100% |

Over the settings of the grid or random sample that contain the value (refinement crowds around the best and is left out; so is a setting in which a condition switched the parameter off). A value that is good on average over everything it was combined with is worth more than one good row.

## Reproduce

The best setting on the real account over the selection period (one run, the unit stepping with the balance):

```
python -m backtesting run --symbol BTCUSDm --start 2023-01-01 --end 2026-11-13 --set entry_agree_s=0.0 --set 'entry_rsi_block_mode="any"' --set entry_rsi_block_tfs=null --set force_close_enabled=false --set ladder_gap_vol=1.0 --set 'ladder_multipliers=[1.0, 1.0, 1.0, 1.0]' --set 'ladder_tfs=["M5", "M15", "H1", "H1", "H1"]' --set 'ladder_trigger="macd_turn"' --set loss_cooldown_s=14400.0 --set max_adds=0 --set 'open_weights={"H1": 1}' --set stop_loss_usd_per_unit=null --set stop_vol=8.0 --set target_usd_per_unit=null --set target_vol=8.0 --set 'trend_tf="H1"' --set vol_cap_usd_per_unit=20.0 --set vol_len=24 --set 'vol_tf="H1"'
```

Its last selection block exactly as measured here (stored net +98.42):

```
python -m backtesting run --symbol BTCUSDm --start '2026-10-01 00:00:00' --end '2026-11-13 00:00:00' --balance 1000000 --set fixed_units=1 --set entry_agree_s=0.0 --set 'entry_rsi_block_mode="any"' --set entry_rsi_block_tfs=null --set force_close_enabled=false --set ladder_gap_vol=1.0 --set 'ladder_multipliers=[1.0, 1.0, 1.0, 1.0]' --set 'ladder_tfs=["M5", "M15", "H1", "H1", "H1"]' --set 'ladder_trigger="macd_turn"' --set loss_cooldown_s=14400.0 --set max_adds=0 --set 'open_weights={"H1": 1}' --set stop_loss_usd_per_unit=null --set stop_vol=8.0 --set target_usd_per_unit=null --set target_vol=8.0 --set 'trend_tf="H1"' --set vol_cap_usd_per_unit=20.0 --set vol_len=24 --set 'vol_tf="H1"'
```

Files next to this report: `trials.csv` (every setting), `monthly.csv` (settings x months), `best.json`, `evaluations.jsonl` (raw results; the same command continues an interrupted run). How to read all of this: `backtesting/OPTIMISER.md`.

