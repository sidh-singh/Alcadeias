# Optimiser report: `v3` on XAUUSDm

Entries with the trend of a higher timeframe, stop and target in units of volatility, and an optional bounded ladder: at most two equal-sized adds, released by a price step, an RSI cross-back, a MACD turn or (adding to a winner) a step in profit. max_adds 0 is the same design without a ladder, so the search itself says whether a ladder earns its risk.

|  |  |
|---|---|
| Period | 2025-07-01 → 2026-11-13 in 6 blocks of 3mo |
| Chosen on | 16 months (2025-07 … 2026-10) |
| Held out | nothing: add `--holdout-from` / `--holdout-to` to keep blocks out of the choice |
| Settings | 645 run (500 random, 145 refine) of 1,555,200 raw combinations in the space |
| Objective | `lcb`: mean net per month minus one standard error |
| Not eligible | a setting that wipes the replayed 2,000 USD account in any selection block, or takes it more than 500 USD below its start (105 of 645) |
| Figures | USD for one fixed 0.01-lot unit on the per-second series, per month, unless they say "account" |
| Shown only | 2026-11: less than half a month inside the period, in monthly.csv but in no statistic |
| Build | engine b0c1554d4e48, live rules ff2eb10cc257, space 7a3a86fa558c, written 2026-11-14 19:23 |

## What to believe

**Not proven.** The best setting passes luck, neighbours; is unclear on halves, walk-forward. Treat the result as a lead, not as an edge.

- **On the months it was chosen on.** The best setting made +242.8 USD a month on average over 16 months, standard error 74.1: a lower bound of +168.7. 12 of 16 months were positive; 665 baskets closed, the worst at -153.9.
- **Luck.** It is the best of 540 eligible settings. If none of them had any edge, the one picked the same way would still show about +106.2 a month (below +208.0 in 95% of such searches), and 1% of such searches reach the objective found here. Luck alone rarely does this well.
- **Half and half.** Over 20 ways of splitting the blocks into two halves, the best setting of one half ranked below the median on the other half in 45% of them (0% is ideal, 50% is what noise gives). It averaged +238.9 a month on the half it was chosen on and +103.1 on the other, where it lost money in 20% of the splits.
- **Walk-forward.** Choosing again after every block from the earlier months only, and trading the next block, made +408.6 over 13 months: +31.4 a month, standard error 120.0, 9 of 13 positive. The settings chosen had averaged +219.0 on the months they were chosen on.
- **Neighbours.** 3 of the 21 settings one step away were run: they average an objective of +125.0 against its own +168.7, and 3 of them are positive. It sits on a plateau.

## The top 10 settings

Ranked by the objective on the selection months only. A number in brackets marks a setting that is not eligible.

| # | key | trend_tf | entry_agree_s | target_vol | stop_vol | vol_cap_usd_per_unit | max_adds | ladder_trigger | ladder_gap_vol | trail_gap_vol | trail_start_vol | loss_cooldown_s | reentry_cooldown_s | max_hold_s | neighbours run | their objective |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `s4e71c5ca88a` | H4 | 0 | 5 | 5 | 12 | 2 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 3 of 21 | +125.0 |
| 2 | `s4911a70f807` | H4 | 0 | 5 | 6 | 8 | 2 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 21 of 21 | +82.1 |
| 3 | `s408229883d7` | H1 | 2 | 8 | 8 | 0 | 2 | macd_turn | 2 | 0 | – | 14400 | 1800 | 0 | 19 of 19 | +65.0 |
| 4 | `scc3363a4d6b` | H4 | 0 | 5 | 6 | 12 | 2 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 21 of 21 | +91.3 |
| 5 | `s6a05903cc13` | H4 | 0 | 5 | 6 | 12 | 1 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 3 of 22 | +132.5 |
| 6 | `s34329480876` | H4 | 0 | 6 | 6 | 12 | 2 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 3 of 21 | +113.8 |
| 7 | `s7594656bb1e` | H4 | 0 | 5 | 6 | 0 | 2 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 21 of 21 | +53.4 |
| 8 | `s16a825d5a2d` | H4 | 0 | 5 | 6 | 8 | 1 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 0 | 22 of 22 | +80.8 |
| 9 | `sa4147e81270` | H4 | 0 | 5 | 6 | 8 | 2 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 86400 | 5 of 21 | +125.6 |
| 10 | `sd84d4fb2c47` | H4 | 0 | 5 | 6 | 8 | 1 | profit_step | 1.5 | 0 | – | 14400 | 1800 | 86400 | 3 of 22 | +127.1 |

### Selection

| # | mean / month | ± SE | lower bound | worst block | months up | baskets / month | worst basket | account |
|---|---|---|---|---|---|---|---|---|
| 1 | +242.8 | 74.1 | +168.7 | +57.0 | 12 of 16 | 40.8 | -153.9 | dip 237 |
| 2 | +242.0 | 78.3 | +163.7 | +76.8 | 12 of 16 | 44.1 | -88.2 | dip 334 |
| 3 | +220.1 | 60.4 | +159.8 | -155.9 | 13 of 16 | 14.9 | -396.6 | dip 243 |
| 4 | +237.3 | 78.1 | +159.2 | +88.0 | 12 of 16 | 38.4 | -134.8 | dip 353 |
| 5 | +239.6 | 81.2 | +158.5 | +129.6 | 10 of 16 | 37.7 | -134.0 | dip 298 |
| 6 | +234.8 | 76.4 | +158.4 | +121.4 | 12 of 16 | 36.5 | -132.7 | dip 322 |
| 7 | +225.3 | 77.7 | +147.5 | +88.0 | 12 of 16 | 34.8 | -289.1 | dip 353 |
| 8 | +221.5 | 76.6 | +144.9 | +180.0 | 10 of 16 | 43.4 | -88.2 | dip 386 |
| 9 | +213.8 | 70.8 | +143.0 | -15.8 | 11 of 16 | 45.1 | -88.2 | dip 273 |
| 10 | +203.6 | 66.5 | +137.2 | +60.1 | 12 of 16 | 44.6 | -88.2 | dip 316 |
| live (reference) | -352.1 | 143.2 | -495.3 | -2,041.0 | 5 of 16 | 1,195.0 | -1,687.1 | wiped in 3 |
| V2 (reference) | +74.7 | 29.5 | +45.2 | -117.2 | 11 of 16 | 37.4 | -32.0 | dip 166 |
| V2 in volatility units (6 / 6) (reference) | +145.0 | 54.8 | +90.2 | -197.5 | 12 of 16 | 16.4 | -314.9 | dip 298 |

"account" is the replay of the same baskets on 2,000 USD with the bot's unit rule, a fresh account in every block: the deepest it stood below its start, or in how many blocks it was wiped. References are named in the space file (overrides on the live settings) and are never candidates.

### Block by block

| # | 2025-07-01 → | 2025-10-01 → | 2026-01-01 → | 2026-04-01 → | 2026-07-01 → | 2026-10-01 → |
|---|---|---|---|---|---|---|
| 1 | +439 | +1,054 | +1,417 | +291 | +627 | -3 |
| 2 | +496 | +861 | +1,331 | +678 | +428 | -136 |
| 3 | +439 | +684 | +1,334 | +807 | +413 | +66 |
| 4 | +498 | +663 | +1,727 | +495 | +325 | -90 |
| 5 | +402 | +929 | +1,809 | +380 | +130 | +5 |
| 6 | +589 | +980 | +1,370 | +422 | +274 | -2 |
| 7 | +498 | +734 | +1,524 | +440 | +321 | -90 |
| 8 | +402 | +753 | +1,284 | +638 | +287 | -37 |
| 9 | +496 | +898 | +1,100 | +445 | +498 | -189 |
| 10 | +402 | +771 | +1,060 | +516 | +448 | -115 |
| live (reference) | -863 | -1,235 | -919 | -2,041 | -802 | -163 |
| V2 (reference) | +154 | +366 | +428 | -31 | +394 | +75 |
| V2 in volatility units (6 / 6) (reference) | +207 | +657 | +1,000 | +761 | -107 | +89 |

Net of each block, named by the day it starts. A result that comes from one block is one event, not an edge.

## Is the best result more than luck?

|  | mean / month | objective |
|---|---|---|
| the best setting | +242.8 | +168.7 |
| the best of 540 settings without any edge, on average | +106.2 | +55.2 |
| … 95% of the time below | +208.0 |  |
| … if the 540 settings were unrelated to each other | +156.5 |  |

Searches without any edge that reach the objective found here: **1%**. The settings are alike: they spread their best results like about 28 unrelated ones. (2,000 resamples of the months, every setting with its own average taken away.)

## Does choosing on one half work on the other?

Chosen among the 500 settings of the sample. The 145 settings added by refinement are left out here: what to refine was decided by looking at every selection month.

|  |  |
|---|---|
| Splits of the blocks into two halves | 20 |
| Best of one half below the median of the other (probability of overfitting) | **45%** |
| Its typical rank on the other half (0% worst, 100% best) | 85% |
| Its mean / month on the half it was chosen on | +238.9 |
| Its mean / month on the other half | +103.1 |
| Splits in which it lost money on the other half | 20% |
| Splits in which the replayed account was wiped on the other half | 0% |

With 6 blocks there are only 20 splits, so this percentage moves in coarse steps; shorter blocks (`--block 1mo`) give more.

## Walk-forward: choosing with past data only

Chosen among the 500 settings of the sample. The 145 settings added by refinement are left out here: what to refine was decided by looking at every selection month.

| chosen on everything before | setting chosen | its objective then | its mean / month then | block traded | net by month | together | account |
|---|---|---|---|---|---|---|---|
| 2025-10-01 | #169 `sfb204ba22fa` | +142.5 | +149.9 | 2025-10-01 → 2026-01-01 | -47 +70 +152 | +175 |  |
| 2026-01-01 | #(628) `s18157901f14` | +103.2 | +154.8 | 2026-01-01 → 2026-04-01 | +400 -1,259 +28 | -831 |  |
| 2026-04-01 | #3 `s408229883d7` | +190.4 | +273.1 | 2026-04-01 → 2026-07-01 | +200 +282 +326 | +807 |  |
| 2026-07-01 | #3 `s408229883d7` | +210.5 | +272.1 | 2026-07-01 → 2026-10-01 | +47 +472 -106 | +413 |  |
| 2026-10-01 | #3 `s408229883d7` | +186.5 | +245.2 | 2026-10-01 → 2026-11-13 | -156 | -156 |  |

| over the 13 months traded | mean / month | ± SE | total |
|---|---|---|---|
| re-chosen after every block (out of sample) | +31.4 | 120.0 | +408.6 |
| the final best setting on the same months (hindsight: they helped choose it) | +265.1 |  |  |
| the average setting of the sample on the same months | +65.1 |  |  |
| live (reference) on the same months | -367.0 |  |  |
| V2 (reference) on the same months | +80.0 |  |  |
| V2 in volatility units (6 / 6) (reference) on the same months | +162.5 |  |  |

## Stability

### Average by parameter value

| parameter | value | settings | average objective | average mean / month | with a positive mean | eligible |
|---|---|---|---|---|---|---|
| trend_tf | H1 | 250 | +21.9 | +68.9 | 98% | 91% |
| trend_tf | H4 | 250 | +10.6 | +58.9 | 94% | 82% |
| entry_agree_s | 0 | 250 | +17.9 | +67.3 | 95% | 86% |
| entry_agree_s | 2 | 250 | +14.6 | +60.6 | 96% | 86% |
| target_vol | 3 | 100 | +11.3 | +59.6 | 96% | 84% |
| target_vol | 4 | 100 | +19.6 | +67.0 | 97% | 87% |
| target_vol | 5 | 100 | +19.9 | +65.8 | 97% | 88% |
| target_vol | 6 | 100 | +11.5 | +59.3 | 95% | 87% |
| target_vol | 8 | 100 | +19.0 | +68.0 | 94% | 86% |
| stop_vol | 3 | 100 | +9.5 | +52.1 | 97% | 91% |
| stop_vol | 4 | 100 | +16.8 | +61.2 | 96% | 96% |
| stop_vol | 5 | 100 | +18.6 | +66.2 | 96% | 87% |
| stop_vol | 6 | 100 | +13.1 | +64.0 | 94% | 82% |
| stop_vol | 8 | 100 | +23.2 | +76.1 | 96% | 76% |
| vol_cap_usd_per_unit | 0 | 167 | +7.8 | +57.3 | 93% | 73% |
| vol_cap_usd_per_unit | 8 | 166 | +13.9 | +57.7 | 96% | 92% |
| vol_cap_usd_per_unit | 12 | 167 | +27.1 | +76.7 | 98% | 94% |
| max_adds | 0 | 166 | +28.8 | +74.8 | 99% | 93% |
| max_adds | 1 | 167 | +7.4 | +56.3 | 96% | 82% |
| max_adds | 2 | 167 | +12.6 | +60.7 | 93% | 84% |
| ladder_trigger | price_step | 83 | +0.3 | +50.5 | 90% | 71% |
| ladder_trigger | rsi_cross | 84 | +10.8 | +56.7 | 96% | 89% |
| ladder_trigger | macd_turn | 84 | +11.5 | +59.0 | 96% | 86% |
| ladder_trigger | profit_step | 83 | +17.4 | +67.8 | 94% | 87% |
| ladder_gap_vol | 1 | 83 | +1.2 | +49.8 | 89% | 78% |
| ladder_gap_vol | 1.5 | 83 | +7.4 | +57.2 | 95% | 83% |
| ladder_gap_vol | 2 | 84 | +16.2 | +66.8 | 96% | 87% |
| ladder_gap_vol | 3 | 84 | +15.1 | +60.1 | 96% | 85% |
| trail_gap_vol | 0 | 166 | +25.5 | +81.9 | 99% | 78% |
| trail_gap_vol | 2 | 167 | +10.1 | +52.3 | 93% | 93% |
| trail_gap_vol | 3 | 167 | +13.2 | +57.6 | 95% | 88% |
| trail_start_vol | 1 | 167 | +4.9 | +45.9 | 93% | 93% |
| trail_start_vol | 2 | 167 | +18.4 | +64.0 | 95% | 89% |
| loss_cooldown_s | 3600 | 166 | +18.5 | +67.9 | 99% | 83% |
| loss_cooldown_s | 14400 | 167 | +22.1 | +71.0 | 98% | 87% |
| loss_cooldown_s | 43200 | 167 | +8.2 | +52.9 | 91% | 89% |
| reentry_cooldown_s | 300 | 250 | +15.9 | +65.6 | 96% | 83% |
| reentry_cooldown_s | 1800 | 250 | +16.6 | +62.2 | 95% | 90% |
| max_hold_s | 0 | 167 | +22.7 | +72.4 | 96% | 86% |
| max_hold_s | 43200 | 167 | +9.9 | +54.7 | 95% | 87% |
| max_hold_s | 86400 | 166 | +16.1 | +64.7 | 96% | 86% |

Over the settings of the grid or random sample that contain the value (refinement crowds around the best and is left out; so is a setting in which a condition switched the parameter off). A value that is good on average over everything it was combined with is worth more than one good row.

## Reproduce

The best setting on the real account over the selection period (one run, the unit stepping with the balance):

```
python -m backtesting run --symbol XAUUSDm --start 2025-07-01 --end 2026-11-13 --set entry_agree_s=0.0 --set force_close_enabled=false --set ladder_gap_vol=1.5 --set 'ladder_multipliers=[1.0, 1.0, 1.0, 1.0]' --set 'ladder_tfs=["M5", "M15", "H1", "H1", "H1"]' --set 'ladder_trigger="profit_step"' --set loss_cooldown_s=14400.0 --set max_adds=2 --set max_hold_s=0.0 --set reentry_cooldown_s=1800.0 --set stop_loss_usd_per_unit=null --set stop_vol=5.0 --set target_usd_per_unit=null --set target_vol=5.0 --set trail_gap_vol=0.0 --set 'trend_tf="H4"' --set vol_cap_usd_per_unit=12.0 --set vol_len=24 --set 'vol_tf="H1"'
```

Its last selection block exactly as measured here (stored net -2.65):

```
python -m backtesting run --symbol XAUUSDm --start '2026-10-01 00:00:00' --end '2026-11-13 00:00:00' --balance 1000000 --set fixed_units=1 --set entry_agree_s=0.0 --set force_close_enabled=false --set ladder_gap_vol=1.5 --set 'ladder_multipliers=[1.0, 1.0, 1.0, 1.0]' --set 'ladder_tfs=["M5", "M15", "H1", "H1", "H1"]' --set 'ladder_trigger="profit_step"' --set loss_cooldown_s=14400.0 --set max_adds=2 --set max_hold_s=0.0 --set reentry_cooldown_s=1800.0 --set stop_loss_usd_per_unit=null --set stop_vol=5.0 --set target_usd_per_unit=null --set target_vol=5.0 --set trail_gap_vol=0.0 --set 'trend_tf="H4"' --set vol_cap_usd_per_unit=12.0 --set vol_len=24 --set 'vol_tf="H1"'
```

Files next to this report: `trials.csv` (every setting), `monthly.csv` (settings x months), `best.json`, `evaluations.jsonl` (raw results; the same command continues an interrupted run). How to read all of this: `backtesting/OPTIMISER.md`.

