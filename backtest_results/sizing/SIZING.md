# How low can the step-up balance go? The six demo designs under more aggressive sizing

*Study of 2026-11-17, not committed. Code: `backtesting/research/sizing.py`. Data in this folder: `results.csv` (design x STEP x cap x window), `rolling.csv` (every 12-month start), `rolling_summary.csv`, `criteria.csv`, `recommendation.csv`, `published_check.csv`.*

## The answer in short

| Design | Today, $2,500: profit/week last year / 8-yr avg, worst DD | (a) lowest STEP never wiped, margin >= 100% at 1:200 | (b) lowest STEP with worst DD <= 50% | (c) lowest STEP with worst DD <= 35% | $750 | $500 |
|---|---|---|---|---|---|---|
| Gold V3-lite | $32 / $24, 45.4% | $500: $218 / $92 a week | $1,750: $83 / $51 a week | none in the grid | too deep: worst DD 76%, 0 wiped | too deep: worst DD 85%, 0 wiped |
| Gold Top 2 | $39 / $16, 19.1% | $500: $208 / $62 a week | $750: $172 / $56 a week | $1,250: $72 / $42 a week | holds, thin margin: worst DD 48%, 0 wiped | too deep: worst DD 69%, 0 wiped |
| Gold Top 1 | $42 / $32, 42.2% | $500: $226 / $102 a week | $1,750: $90 / $62 a week | none in the grid | too deep: worst DD 78%, 0 wiped | too deep: worst DD 98%, 0 wiped |
| BTC Turtle System 2 + bot votes | $20 / $14, 38.4% | $500: $109 / $71 a week | $2,000: $33 / $27 a week | none in the grid | too deep: worst DD 78%, 0 wiped | too deep: worst DD 93%, 0 wiped |
| BTC Turtle System 1 + bot votes | $27 / $12, 52.9% | $750: $81 / $74 a week | none in the grid | none in the grid | too deep: worst DD 96%, 0 wiped | breaks: worst DD 100%, 2 wiped |
| BTC Top 2 | $2 / $5, 17.8% | $500: $6 / $23 a week | $1,000: $6 / $13 a week | $1,750: $5 / $8 a week | too deep: worst DD 52%, 0 wiped | too deep: worst DD 66%, 0 wiped |

Profit a week = net profit of a fresh $2,000 account divided by the weeks of the window (last year: 2025-11-13 to 2026-11-13; 8-yr avg: 2018-11-13 to 2026-11-13). "Worst DD" is the deepest fall of equity (floating losses included) from its running high, in any of the four windows, under any of the eight loop timings of the last year, or in any of the 84 rolling 12-month accounts. Cap of 10 units as the bot runs; without the cap see the design sections.

## The sizing rule, as found

- All six demo branches (`symbols.json`, `constants.py`): step_up_balance $2,500, unit_max_limit 10, mtqty 0.01 lot per unit, VIRTUAL_START_BALANCE $2,000 plus the bot's own closed P/L (from 2026-11-15).
- `app.py` (baskets): `units = int(balance // step_up_balance) + 1`, then `max(1, min(units, unit_max_limit))`, re-derived only while the symbol is flat; an open basket keeps its unit, the ladder add of Top 1 is `multiplier x unit`. `turtle.py` `unit_rule` is the same rule, taken at each Turtle entry; the Turtle's adds use the trade's unit.
- Backtester: `BacktestConfig` step_up_balance 2500, unit_max_limit 10, mtqty 0.01, initial_balance 2000 (the tick engine re-derives the unit only while flat); `external.py` STEP_UP 2500, UNIT_MAX 10, ACCOUNT 2000 (`_account_kernel(..., step_up, unit_max)` sizes each trade and all its legs with one unit).
- The cap binds from a balance of STEP x 9 (STEP $500: $4,500). "No cap" below means the same rule with the limit at 1,000,000 units.

## How it was measured, and the checks

1. **Published figures reproduced.** At STEP $2,500 with the cap of 10, all 24 published accounts (six designs x four windows): final equity to the cent 24/24, maximum drawdown to 0.1 point 24/24, trade counts 24/24 (`published_check.csv`).
2. **Turtles (M1-bar simulator): the per-unit replay is exact.** The Turtle trade path does not depend on the account at all; the account kernel only sizes it. `_bar_replay` mirrors the kernel operation for operation and adds lowest equity, margin and lots. It equals the kernel itself bit for bit (every trade's P/L, final balance, drawdown, daily marks) at every STEP and cap, in all four windows and all 84 rolling starts (2,816 accounts), including STEP $1,000 and $500 for System 2 over 8 years and the last year.
3. **The tick-engine designs: the per-unit premise fails, so the engine itself was re-run at every STEP.** The engine, like MT5, rounds each position's floating profit to the cent and compares the basket's profit with `unit x target` and `-unit x stop`. Rounding does not scale with the unit, so the first poll that crosses a target or a stop can move by a second or more when the unit changes, and the exit price and every later trade with it. A per-unit replay of the STEP-$2,500 run (same trades, exact cent rounding, only the unit changed) against the engine re-run at the new STEP:
| Design | Window | STEP | Cap | Engine re-run | Per-unit replay | Replay - engine | First basket that differs | Every basket before it equal to the cent |
|---|---|---|---|---|---|---|---|---|
| Gold V3-lite | 8 years | $1,000 | 10 | $34,575.02 | $34,574.48 | -$0.54 | 7 of 809 | yes |
| Gold V3-lite | 8 years | $1,000 | none | $67,794.83 | $67,794.29 | -$0.54 | 7 of 809 | yes |
| Gold V3-lite | 8 years | $500 | 10 | $40,365.99 | $40,363.75 | -$2.24 | 7 of 809 | yes |
| Gold V3-lite | 8 years | $500 | none | $311,262.38 | $309,596.91 | -$1,665.47 | 7 of 809 | yes |
| Gold V3-lite | last year, timing 5 | $1,000 | 10 | $7,678.38 | $7,678.38 | $0.00 | - of 99 | yes |
| Gold V3-lite | last year, timing 5 | $1,000 | none | $7,678.38 | $7,678.38 | $0.00 | - of 99 | yes |
| Gold V3-lite | last year, timing 5 | $500 | 10 | $13,295.30 | $13,295.30 | $0.00 | - of 99 | yes |
| Gold V3-lite | last year, timing 5 | $500 | none | $4,467.26 | $4,467.26 | $0.00 | - of 99 | yes |

   Example (Gold V3-lite, 8y, STEP $1,000): engine `2018-12-17 17:24:26+00:00 -> 2018-12-18 11:05:53+00:00 target 11.23`, replay `2018-12-17 17:24:26+00:00 -> 2018-12-18 11:05:55+00:00 11.23`. Every figure of the four tick-engine designs in this study is therefore the engine's own run at that STEP (per second for 8 years, 5 years, Nov 2018 - Dec 2020 and every rolling start; every tick under the eight loop timings for the last year), not a replay.
4. **Rolling starts.** A fresh $2,000 account on the 1st of every month from 2018-12 to 2025-11 (84 starts), each run for 12 months; "last 24 months" = the 24 starts from 2023-12, whose years end between Dec 2024 and Nov 2026. The tick designs run per second, cut out of one 8-year preparation (checked: the 5-year and Nov 2018 - Dec 2020 windows cut the same way give the published accounts to the cent, and a rolling start cut out equals the same start prepared on its own).
5. **Breaking** is judged on equity with floating P/L at the engine's own resolution (every poll of the tick engine; the worst price of every M1 bar for the Turtles): wiped = equity reached 0 (the engine's stop-out), margin level = equity / margin with margin = lots x contract (gold 100 oz, BTC 1 BTC) x fill price / leverage, at 1:100 and 1:200, and drawdown >= 50%. The uncapped account is run only where the capped one reached 10 units; otherwise the two are the same account.

## Design by design

### Gold V3-lite (`demo_hedging_xauusd6`)

*With the cap of 10 units (0.10 lot), as the bot runs:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $32 | $24 | $26 | 45.3% (45.4%) | 33.0% | 37.7% | **45.4%** | 79% of $2,000 | 3,926% / 1,963% | 0 | holds, thin margin |
| $2,000 | $70 | $37 | $35 | 42.0% (42.0%) | 35.8% | 44.0% | **44.0%** | 85% of $2,000 | 4,146% / 2,073% | 0 | holds, thin margin |
| $1,750 | $83 | $51 | $40 | 42.3% (42.4%) | 38.9% | 48.3% | **48.3%** | 80% of $2,000 | 3,838% / 1,919% | 0 | holds, thin margin |
| $1,500 | $75 | $58 | $44 | 54.8% (54.9%) | 41.6% | 48.9% | **54.9%** | 74% of $2,000 | 3,096% / 1,548% | 0 | too deep |
| $1,250 | $82 | $71 | $50 | 57.8% (57.9%) | 33.8% | 57.1% | **57.9%** | 74% of $2,000 | 2,550% / 1,275% | 0 | too deep |
| $1,000 | $110 | $78 | $68 | 63.3% (63.4%) | 29.9% | 64.7% | **64.7%** | 72% of $2,000 | 2,065% / 1,033% | 0 | too deep |
| $750 | $196 | $87 | $94 | 75.8% (75.9%) | 32.3% | 76.3% | **76.3%** | 65% of $2,000 | 1,277% / 638% | 0 | too deep |
| $500 | $218 | $92 | $149 | 85.1% (85.2%) | 40.4% | 68.7% | **85.2%** | 52% of $2,000 | 946% / 473% | 0 | too deep |

*Without the cap:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $32 | $24 | $26 | 45.3% (45.4%) | 33.0% | 37.7% | **45.4%** | 79% of $2,000 | 3,926% / 1,963% | 0 | holds, thin margin |
| $2,000 | $70 | $37 | $35 | 42.0% (42.0%) | 35.8% | 44.0% | **44.0%** | 85% of $2,000 | 4,146% / 2,073% | 0 | holds, thin margin |
| $1,750 | $83 | $50 | $40 | 42.3% (42.4%) | 38.9% | 48.3% | **48.3%** | 80% of $2,000 | 3,838% / 1,919% | 0 | holds, thin margin |
| $1,500 | $75 | $63 | $44 | 54.8% (54.9%) | 43.2% | 48.9% | **54.9%** | 74% of $2,000 | 3,096% / 1,548% | 0 | too deep |
| $1,250 | $82 | $96 | $50 | 57.8% (57.9%) | 50.5% | 57.1% | **57.9%** | 74% of $2,000 | 2,550% / 1,275% | 0 | too deep |
| $1,000 | $110 | $158 | $68 | 63.3% (63.4%) | 59.7% | 64.7% | **64.7%** | 72% of $2,000 | 2,065% / 1,033% | 0 | too deep |
| $750 | $168 | $337 | $93 | 75.8% (75.9%) | 72.0% | 76.3% | **76.3%** | 65% of $2,000 | 1,277% / 638% | 0 | too deep |
| $500 | $59 | $741 | $148 | 93.0% (93.2%) | 90.6% | 92.4% | **93.2%** | 26% of $2,000 | 338% / 169% | 0 | too deep |

Lowest safe STEP, cap 10: (a) $500, (b) $1,750, (c) none in the grid. Without the cap: (a) $500, (b) $1,750, (c) none in the grid.

### Gold Top 2 (`demo_hedging_xauusd7`)

*With the cap of 10 units (0.10 lot), as the bot runs:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $39 | $16 | $29 | 17.3% (19.0%) | 17.1% | 19.1% | **19.1%** | 87% of $2,000 | 4,466% / 2,233% | 0 | holds |
| $2,000 | $47 | $21 | $37 | 21.5% (22.9%) | 22.1% | 22.4% | **22.9%** | 83% of $2,000 | 4,013% / 2,006% | 0 | holds |
| $1,750 | $42 | $22 | $48 | 23.3% (24.1%) | 32.7% | 25.1% | **32.7%** | 73% of $2,000 | 3,650% / 1,825% | 0 | holds |
| $1,500 | $60 | $34 | $47 | 23.6% (26.0%) | 32.8% | 23.9% | **32.8%** | 73% of $2,000 | 3,551% / 1,776% | 0 | holds |
| $1,250 | $72 | $42 | $60 | 30.6% (31.9%) | 32.7% | 29.8% | **32.7%** | 73% of $2,000 | 3,109% / 1,555% | 0 | holds |
| $1,000 | $100 | $49 | $82 | 31.8% (35.1%) | 40.3% | 32.0% | **40.3%** | 66% of $2,000 | 2,646% / 1,323% | 0 | holds, thin margin |
| $750 | $172 | $56 | $130 | 39.2% (40.2%) | 47.8% | 40.2% | **47.8%** | 59% of $2,000 | 2,163% / 1,081% | 0 | holds, thin margin |
| $500 | $208 | $62 | $177 | 52.2% (53.3%) | 69.1% | 52.2% | **69.1%** | 37% of $2,000 | 1,451% / 726% | 0 | too deep |

*Without the cap:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $39 | $16 | $29 | 17.3% (19.0%) | 17.1% | 19.1% | **19.1%** | 87% of $2,000 | 4,466% / 2,233% | 0 | holds |
| $2,000 | $47 | $21 | $37 | 21.5% (22.9%) | 22.1% | 22.4% | **22.9%** | 83% of $2,000 | 4,013% / 2,006% | 0 | holds |
| $1,750 | $42 | $22 | $48 | 23.3% (24.1%) | 32.7% | 25.1% | **32.7%** | 73% of $2,000 | 3,650% / 1,825% | 0 | holds |
| $1,500 | $60 | $32 | $47 | 23.6% (26.0%) | 32.8% | 23.9% | **32.8%** | 73% of $2,000 | 3,551% / 1,776% | 0 | holds |
| $1,250 | $72 | $43 | $60 | 30.6% (31.9%) | 32.7% | 29.8% | **32.7%** | 73% of $2,000 | 3,109% / 1,555% | 0 | holds |
| $1,000 | $100 | $66 | $82 | 31.8% (35.1%) | 40.3% | 32.0% | **40.3%** | 66% of $2,000 | 2,646% / 1,323% | 0 | holds, thin margin |
| $750 | $146 | $120 | $122 | 39.3% (42.7%) | 47.8% | 40.2% | **47.8%** | 59% of $2,000 | 2,163% / 1,081% | 0 | holds, thin margin |
| $500 | $212 | $318 | $213 | 52.2% (56.8%) | 69.1% | 52.2% | **69.1%** | 37% of $2,000 | 1,451% / 726% | 0 | too deep |

Lowest safe STEP, cap 10: (a) $500, (b) $750, (c) $1,250. Without the cap: (a) $500, (b) $750, (c) $1,250.

### Gold Top 1 (`demo_hedging_xauusd8`)

*With the cap of 10 units (0.10 lot), as the bot runs:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $42 | $32 | $45 | 41.9% (42.2%) | 32.5% | 38.9% | **42.2%** | 69% of $2,000 | 1,877% / 938% | 0 | holds, thin margin |
| $2,000 | $77 | $54 | $52 | 45.6% (46.2%) | 38.9% | 46.3% | **46.3%** | 68% of $2,000 | 2,052% / 1,026% | 0 | holds, thin margin |
| $1,750 | $90 | $62 | $67 | 43.6% (43.9%) | 39.0% | 44.1% | **45.0%** | 58% of $2,000 | 1,857% / 929% | 0 | holds, thin margin |
| $1,500 | $98 | $72 | $76 | 48.7% (49.3%) | 44.8% | 51.2% | **51.2%** | 56% of $2,000 | 1,574% / 787% | 0 | too deep |
| $1,250 | $129 | $83 | $86 | 55.0% (57.7%) | 49.6% | 55.1% | **57.7%** | 48% of $2,000 | 1,275% / 637% | 0 | too deep |
| $1,000 | $192 | $90 | $119 | 62.5% (67.1%) | 60.4% | 66.5% | **67.1%** | 40% of $2,000 | 934% / 467% | 0 | too deep |
| $750 | $240 | $99 | $189 | 77.2% (77.9%) | 68.4% | 75.8% | **77.9%** | 31% of $2,000 | 649% / 324% | 0 | too deep |
| $500 | $226 | $102 | $223 | 89.7% (97.7%) | 80.5% | 74.6% | **97.7%** | 7% of $2,000 | 137% / 69% | 0 | too deep |

*Without the cap:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $42 | $32 | $45 | 41.9% (42.2%) | 32.5% | 38.9% | **42.2%** | 69% of $2,000 | 1,877% / 938% | 0 | holds, thin margin |
| $2,000 | $77 | $49 | $52 | 45.6% (46.2%) | 38.9% | 46.3% | **46.3%** | 68% of $2,000 | 2,052% / 1,026% | 0 | holds, thin margin |
| $1,750 | $90 | $60 | $67 | 43.6% (43.9%) | 39.0% | 44.1% | **45.0%** | 58% of $2,000 | 1,857% / 929% | 0 | holds, thin margin |
| $1,500 | $98 | $73 | $76 | 48.7% (49.3%) | 44.8% | 51.2% | **51.2%** | 56% of $2,000 | 1,574% / 787% | 0 | too deep |
| $1,250 | $127 | $104 | $86 | 55.0% (57.7%) | 50.2% | 55.1% | **57.7%** | 48% of $2,000 | 1,275% / 637% | 0 | too deep |
| $1,000 | $132 | $143 | $119 | 62.5% (67.1%) | 60.4% | 66.5% | **67.1%** | 40% of $2,000 | 934% / 467% | 0 | too deep |
| $750 | $125 | $242 | $163 | 77.2% (77.9%) | 73.7% | 76.4% | **77.9%** | 31% of $2,000 | 649% / 324% | 0 | too deep |
| $500 | -$14 | $116 | $192 | 97.3% (100.0%) | 94.1% | 95.7% | **100.0%** | -0% of $2,000 | -0% / -0% | 3 | breaks |

Lowest safe STEP, cap 10: (a) $500, (b) $1,750, (c) none in the grid. Without the cap: (a) $750, (b) $1,750, (c) none in the grid.

### BTC Turtle System 2 + bot votes (`demo_hedging_btcusd6`)

*With the cap of 10 units (0.10 lot), as the bot runs:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $20 | $14 | $8 | 22.4% | 32.5% | 38.3% | **38.4%** | 65% of $2,000 | 5,712% / 2,856% | 0 | holds, thin margin |
| $2,000 | $33 | $27 | $10 | 36.3% | 36.3% | 46.5% | **46.5%** | 59% of $2,000 | 4,545% / 2,272% | 0 | holds, thin margin |
| $1,750 | $32 | $26 | $9 | 36.3% | 39.5% | 52.4% | **52.4%** | 50% of $2,000 | 4,451% / 2,225% | 0 | too deep |
| $1,500 | $37 | $32 | $12 | 36.3% | 42.1% | 57.1% | **57.1%** | 49% of $2,000 | 3,988% / 1,994% | 0 | too deep |
| $1,250 | $38 | $35 | $19 | 36.3% | 47.3% | 61.6% | **61.6%** | 42% of $2,000 | 3,157% / 1,578% | 0 | too deep |
| $1,000 | $53 | $53 | $16 | 45.8% | 53.2% | 72.8% | **72.8%** | 33% of $2,000 | 2,424% / 1,212% | 0 | too deep |
| $750 | $64 | $62 | $14 | 45.8% | 53.0% | 78.4% | **78.4%** | 22% of $2,000 | 1,883% / 942% | 0 | too deep |
| $500 | $109 | $71 | $19 | 57.8% | 42.6% | 93.0% | **93.0%** | 7% of $2,000 | 848% / 424% | 0 | too deep |

*Without the cap:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $20 | $14 | $8 | 22.4% | 32.5% | 38.3% | **38.4%** | 65% of $2,000 | 5,712% / 2,856% | 0 | holds, thin margin |
| $2,000 | $33 | $27 | $10 | 36.3% | 36.3% | 46.5% | **46.5%** | 59% of $2,000 | 4,545% / 2,272% | 0 | holds, thin margin |
| $1,750 | $32 | $26 | $9 | 36.3% | 39.5% | 52.4% | **52.4%** | 50% of $2,000 | 4,451% / 2,225% | 0 | too deep |
| $1,500 | $37 | $31 | $12 | 36.3% | 42.1% | 57.1% | **57.1%** | 49% of $2,000 | 3,988% / 1,994% | 0 | too deep |
| $1,250 | $38 | $34 | $19 | 36.3% | 47.8% | 61.6% | **61.6%** | 42% of $2,000 | 3,157% / 1,578% | 0 | too deep |
| $1,000 | $53 | $50 | $16 | 45.8% | 53.7% | 72.8% | **72.8%** | 33% of $2,000 | 2,424% / 1,212% | 0 | too deep |
| $750 | $64 | $74 | $14 | 45.8% | 62.7% | 78.4% | **78.4%** | 22% of $2,000 | 1,883% / 942% | 0 | too deep |
| $500 | $102 | $101 | $16 | 57.8% | 77.6% | 93.0% | **93.0%** | 7% of $2,000 | 848% / 424% | 0 | too deep |

Lowest safe STEP, cap 10: (a) $500, (b) $2,000, (c) none in the grid. Without the cap: (a) $500, (b) $2,000, (c) none in the grid.

### BTC Turtle System 1 + bot votes (`demo_hedging_btcusd7`)

*With the cap of 10 units (0.10 lot), as the bot runs:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $27 | $12 | $6 | 26.4% | 46.0% | 52.9% | **52.9%** | 49% of $2,000 | 5,006% / 2,503% | 0 | too deep |
| $2,000 | $30 | $25 | $4 | 40.3% | 48.2% | 60.2% | **60.2%** | 43% of $2,000 | 3,652% / 1,826% | 0 | too deep |
| $1,750 | $40 | $29 | $2 | 42.7% | 51.5% | 66.4% | **66.4%** | 34% of $2,000 | 3,652% / 1,826% | 0 | too deep |
| $1,500 | $49 | $32 | $2 | 42.7% | 57.2% | 72.6% | **72.6%** | 31% of $2,000 | 2,827% / 1,413% | 0 | too deep |
| $1,250 | $49 | $54 | $5 | 42.7% | 50.8% | 73.0% | **73.0%** | 28% of $2,000 | 2,303% / 1,152% | 0 | too deep |
| $1,000 | $55 | $67 | $5 | 51.9% | 56.4% | 88.1% | **88.1%** | 12% of $2,000 | 1,551% / 775% | 0 | too deep |
| $750 | $81 | $74 | $2 | 56.8% | 64.9% | 96.4% | **96.4%** | 4% of $2,000 | 643% / 322% | 0 | too deep |
| $500 | $131 | $84 | -$14 | 68.8% | 61.7% | 100.0% | **100.0%** | -1% of $2,000 | -64% / -32% | 2 | breaks |

*Without the cap:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $27 | $12 | $6 | 26.4% | 46.0% | 52.9% | **52.9%** | 49% of $2,000 | 5,006% / 2,503% | 0 | too deep |
| $2,000 | $30 | $25 | $4 | 40.3% | 48.2% | 60.2% | **60.2%** | 43% of $2,000 | 3,652% / 1,826% | 0 | too deep |
| $1,750 | $40 | $29 | $2 | 42.7% | 51.5% | 66.4% | **66.4%** | 34% of $2,000 | 3,652% / 1,826% | 0 | too deep |
| $1,500 | $49 | $32 | $2 | 42.7% | 57.2% | 72.6% | **72.6%** | 31% of $2,000 | 2,827% / 1,413% | 0 | too deep |
| $1,250 | $49 | $41 | $5 | 42.7% | 63.0% | 73.0% | **73.0%** | 28% of $2,000 | 2,303% / 1,152% | 0 | too deep |
| $1,000 | $55 | $52 | $5 | 51.9% | 70.5% | 88.1% | **88.1%** | 12% of $2,000 | 1,551% / 775% | 0 | too deep |
| $750 | $81 | $72 | $2 | 56.8% | 82.3% | 96.4% | **96.4%** | 4% of $2,000 | 643% / 322% | 0 | too deep |
| $500 | $119 | $73 | -$14 | 68.8% | 95.4% | 100.0% | **100.0%** | -1% of $2,000 | -64% / -32% | 2 | breaks |

Lowest safe STEP, cap 10: (a) $750, (b) none in the grid, (c) none in the grid. Without the cap: (a) $750, (b) none in the grid, (c) none in the grid.

### BTC Top 2 (`demo_hedging_btcusd8`)

*With the cap of 10 units (0.10 lot), as the bot runs:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $2 | $5 | $9 | 13.1% (14.1%) | 16.6% | 17.8% | **17.8%** | 85% of $2,000 | 20,045% / 10,023% | 0 | holds |
| $2,000 | $5 | $6 | $20 | 22.6% (23.9%) | 28.9% | 21.6% | **28.9%** | 83% of $2,000 | 15,516% / 7,758% | 0 | holds |
| $1,750 | $5 | $8 | $22 | 22.6% (25.0%) | 29.2% | 24.9% | **33.3%** | 75% of $2,000 | 14,036% / 7,018% | 0 | holds |
| $1,500 | $5 | $8 | $19 | 22.6% (25.0%) | 29.2% | 25.5% | **35.1%** | 67% of $2,000 | 15,026% / 7,513% | 0 | holds, thin margin |
| $1,250 | $3 | $10 | $27 | 26.8% (28.6%) | 32.1% | 25.5% | **32.9%** | 69% of $2,000 | 13,145% / 6,572% | 0 | holds |
| $1,000 | $6 | $13 | $33 | 32.2% (34.4%) | 40.4% | 29.4% | **43.4%** | 68% of $2,000 | 10,481% / 5,240% | 0 | holds, thin margin |
| $750 | $5 | $20 | $47 | 38.6% (41.2%) | 49.8% | 36.3% | **51.7%** | 56% of $2,000 | 8,837% / 4,419% | 0 | too deep |
| $500 | $6 | $23 | $71 | 51.2% (54.2%) | 65.8% | 49.0% | **65.8%** | 37% of $2,000 | 5,787% / 2,894% | 0 | too deep |

*Without the cap:*

| STEP | Profit/week last year | Profit/week 8-yr avg | Profit/week, median 12 months (last 24 starts) | DD last year (worst timing) | DD 8 yr | Worst DD, 12-month starts in the last 24 months | Worst DD anywhere | Lowest equity | Margin level min 1:200 / 1:100 | Wiped accounts | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2,500 | $2 | $5 | $9 | 13.1% (14.1%) | 16.6% | 17.8% | **17.8%** | 85% of $2,000 | 20,045% / 10,023% | 0 | holds |
| $2,000 | $5 | $6 | $20 | 22.6% (23.9%) | 28.9% | 21.6% | **28.9%** | 83% of $2,000 | 15,516% / 7,758% | 0 | holds |
| $1,750 | $5 | $8 | $22 | 22.6% (25.0%) | 29.2% | 24.9% | **33.3%** | 75% of $2,000 | 14,036% / 7,018% | 0 | holds |
| $1,500 | $5 | $8 | $19 | 22.6% (25.0%) | 29.2% | 25.5% | **35.1%** | 67% of $2,000 | 15,026% / 7,513% | 0 | holds, thin margin |
| $1,250 | $3 | $10 | $27 | 26.8% (28.6%) | 32.1% | 25.5% | **32.9%** | 69% of $2,000 | 13,145% / 6,572% | 0 | holds |
| $1,000 | $6 | $13 | $33 | 32.2% (34.4%) | 40.4% | 29.4% | **43.4%** | 68% of $2,000 | 10,481% / 5,240% | 0 | holds, thin margin |
| $750 | $5 | $19 | $47 | 38.6% (41.2%) | 49.8% | 36.3% | **51.7%** | 56% of $2,000 | 8,837% / 4,419% | 0 | too deep |
| $500 | $6 | $26 | $66 | 51.2% (54.2%) | 65.8% | 49.0% | **65.8%** | 37% of $2,000 | 5,787% / 2,894% | 0 | too deep |

Lowest safe STEP, cap 10: (a) $500, (b) $1,000, (c) $1,750. Without the cap: (a) $500, (b) $1,000, (c) $1,750.

## The six together

Six $2,000 accounts summed minute by minute (one account per bot, as on the demo):

| Levels | Window | Start | Final | Profit/week | Combined max DD |
|---|---|---|---|---|---|
| today: STEP $2,500, cap 10 | 8 years | $12,000 | $54,611 | $102 | 16.9% |
| (c) levels, cap 10 ($2,500 where no lower STEP passes) | 8 years | $12,000 | $66,567 | $131 | 15.9% |
| (c) levels, cap none ($2,500 where no lower STEP passes) | 8 years | $12,000 | $67,048 | $132 | 15.9% |
| (b) levels, cap 10 ($2,500 where no lower STEP passes) | 8 years | $12,000 | $104,048 | $221 | 17.2% |
| (b) levels, cap none ($2,500 where no lower STEP passes) | 8 years | $12,000 | $129,759 | $282 | 23.3% |
| today: STEP $2,500, cap 10 | 5 years | $12,000 | $45,831 | $130 | 14.9% |
| (c) levels, cap 10 ($2,500 where no lower STEP passes) | 5 years | $12,000 | $59,113 | $181 | 14.6% |
| (c) levels, cap none ($2,500 where no lower STEP passes) | 5 years | $12,000 | $61,162 | $188 | 15.2% |
| (b) levels, cap 10 ($2,500 where no lower STEP passes) | 5 years | $12,000 | $83,787 | $275 | 16.9% |
| (b) levels, cap none ($2,500 where no lower STEP passes) | 5 years | $12,000 | $131,125 | $457 | 26.7% |
| today: STEP $2,500, cap 10 | Nov 2018 - Dec 2020 | $12,000 | $14,157 | $19 | 6.1% |
| (c) levels, cap 10 ($2,500 where no lower STEP passes) | Nov 2018 - Dec 2020 | $12,000 | $14,152 | $19 | 7.5% |
| (c) levels, cap none ($2,500 where no lower STEP passes) | Nov 2018 - Dec 2020 | $12,000 | $14,152 | $19 | 7.5% |
| (b) levels, cap 10 ($2,500 where no lower STEP passes) | Nov 2018 - Dec 2020 | $12,000 | $15,691 | $33 | 11.5% |
| (b) levels, cap none ($2,500 where no lower STEP passes) | Nov 2018 - Dec 2020 | $12,000 | $15,691 | $33 | 11.5% |
| today: STEP $2,500, cap 10 | last year | $12,000 | $20,447 | $162 | 16.0% |
| (c) levels, cap 10 ($2,500 where no lower STEP passes) | last year | $12,000 | $22,291 | $197 | 16.6% |
| (c) levels, cap none ($2,500 where no lower STEP passes) | last year | $12,000 | $22,291 | $197 | 16.6% |
| (b) levels, cap 10 ($2,500 where no lower STEP passes) | last year | $12,000 | $33,708 | $416 | 18.5% |
| (b) levels, cap none ($2,500 where no lower STEP passes) | last year | $12,000 | $32,320 | $390 | 22.1% |

