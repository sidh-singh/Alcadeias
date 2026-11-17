# Silver (XAGUSDm, Exness): which strategies work, and at what size. Pre-registration

- **Written and frozen:** 2026-11-17, 06:45 UTC, on `backtest_hedging` at commit `dedecf9` (nothing of this study is committed).
- **Status:** written before any strategy result on silver exists in this study. The exceptions, all already seen elsewhere, are listed in §0.
- **Frozen:** the sha256 of this file is in `PREREG_SILVER.md.sha256`. Any later change is a deviation, listed in `DEVIATIONS_SILVER.md` with its reason and its effect.

**The owner's question.** Which trading strategies can work on silver (XAGUSDm on Exness MT5), tested honestly, and how should they be sized so that a $2,000 bot account survives? One strategy per bot.

**Inputs, frozen as they are now:**

| File | sha256 |
|---|---|
| `backtest_results/silver/MARKET.md` (market profile, data to 2024-06-30 only) | `dd44a359aa7fc59fd277fadb153969f5effb51f31aa0b3a418ea8016510763c3` |
| `backtest_results/silver/WEB_SURVEY.md` (27 published strategies, 5 sizing rules) | `0359872ea937bbbe9b369fc80eca5c788142064e1265776d848eca06446c5d14` |
| `backtest_results/silver/INVENTORY.md` (34 repo entries, engines, smoke tests) | `1d0a4bf433cf92879491f85e4d3ff9366a9d530709769db95d2c29021859d422` |
| `backtest_results/multisymbol/specs.json` (contract, digits, translated caps) | `7c885e1c40264444a29906b92ac3692c74ab12cadfc2fda2adb3b027b4e94ac2` |
| `backtest_results/silver/smoke/smoke.py` (plumbing checks) | `68bb12d9df37eca76abdb22feab4b19e25b4aa2b0000b410ff587359697a674d` |

**Silver facts used throughout** (INVENTORY §1): 5,000 oz per lot, so 0.01 lot = 50 oz and a $1.00 move = **$50 per 0.01 lot** (k = 50). 3 digits, point 0.001, min lot 0.01, step 0.01. USD-quoted (P/L × 1). Daily break Mon–Thu 20:58–22:01 UTC (US summer) / 21:58–23:01 (winter). Week Sun 22:05/23:05 → Fri 20:58/21:58 UTC. Store: `data/store/XAGUSDm/`, 2017-11 → 2026-11, `sec.npz` (per-second bid/ask) + `m1.npz` (M1 bid OHLC, `ask_c`, `spread_mean`), no raw ticks. Gold (XAUUSDm, from 2017-01) and BTC are in the store.

---

## 0. What has already been seen (contamination), and what it means

1. **The six demo designs on silver, unchanged**, 2021-11-13 → 2026-11-13 (MULTISYMBOL.md, `runs/summary.csv`): none qualified. Silver Turtle S1 + votes made +$4,940 on one unit in 2024-05 → 2026-11, and its unit-rule account was wiped on 2026-04-21. In 2021-11-13 → 2024-05-13 the Turtle + votes streams were S1 −$419.40 (23 trades) and S2 −$1,335.00 (17 trades). These affect candidates C03, C04 and C34–C39.
2. **The market profile used DEV and VAL together** (MARKET.md). Every candidate whose idea or setting comes from MARKET.md is marked **[M]** below. For [M] candidates, **validation is not an independent test**: the effect was already seen there. Only the hold-out is clean for them. [M] candidates: C13 (D1 breakout, fixed hold), C26 (M15 fade control), C32 (December, Wednesday), C33 (the 23 UTC hour), the 12–16 UTC window choices in C14/C15/C20/C21.
3. **The inventory step** saw one development result by accident: Go Long's unit-rule account wiped in 2021. Go Long is not a candidate here (an index rule).
4. **Public knowledge:** silver rallied strongly in 2025–26. Any long-biased rule will look good in the hold-out for that reason alone. §8 H4 controls for this with an exposure-matched benchmark.
5. **The cost regime falls in the hold-out.** The dollar spread stayed near $0.03–0.05 while the price rose about 4×, so the spread in % of price falls about 5× from DEV to the hold-out (INVENTORY §1). Fast rules will look better in the hold-out without any real edge. §2.4 and §8 H5 control for this.
6. **Consequence:** the hold-out (2024-07-01 → 2026-11-13) is the only clean test, and only for the frozen finalists, once.

---

## 1. Splits and warm-up

All times UTC; periods are [start, end).

| Period | From | To | Length | Use |
|---|---|---|---|---|
| Warm-up | 2017-11-01 | 2018-11-01 | 12 months | indicators only; no trade before 2018-11-01 |
| **DEVELOPMENT (DEV)** | 2018-11-01 | 2023-01-01 | 4.17 y, 17 quarters (Q4 2018 is two months) | every variant; the shortlist |
| **VALIDATION (VAL)** | 2023-01-01 | 2024-07-01 | 1.50 y, 6 quarters | the shortlist only; finalists; sizing choices (with DEV) |
| **HOLD-OUT (HO)** | 2024-07-01 | 2026-11-13 | 2.37 y, about 123 weeks | the frozen finalists, once |

**The default split is kept.** Reasons: (a) the warm-up of 12 months is exactly what 12-month TSMOM and the 10–12-month SMAs need; (b) DEV holds the 2018–19 quiet regime and the 2020–22 volatile one, so a rule must work in both; (c) moving dates now, after MARKET.md saw DEV and VAL, would be a choice made with that knowledge. Two refinements, with reasons:

1. **How a split's numbers are made.**
   - **Per-unit streams (bar simulator, Balke kernel):** one continuous run from 2018-11-01, with the data cut at the end of the furthest split allowed at that step (DEV runs: data ends 2023-01-01; VAL runs: 2024-07-01; exam: 2026-11-13). A split's metrics are the slice of the daily marked-to-market stream inside the split, so a trade open across a boundary contributes its floating change to each side. This keeps slow rules from losing their first trade at every split start.
   - **Accounts (sizing, §6):** a fresh account starting flat at $2,000 on the split's first day, taking only trades entered on or after it, which is what deploying would do. An open position at the end is valued at the last price.
   - **Tick engine (basket designs):** one run per split window, starting flat, with the engine's standard indicator warm-up from the history before the start (as in the final ten). The basket designs hold for hours to days, so the boundary effect is small.
2. **The loader enforces the cut.** The new module slices every array at the step's allowed end and asserts that no timestamp at or after it is present. DEV runs cannot read VAL; nothing reads the hold-out until the exam step, and the exam loads only after `FINALISTS.md.sha256` exists.

The slowest indicator, EWMAC (64, 256) in C09, is only about 1 year warm on 2018-11-01. Its EWMA is used as computed; this is declared, not fixed.

---

## 2. Costs

### 2.1 Spread at every fill
- **Tick engine:** the per-second bid/ask, as recorded. Buys fill at the ask, sells at the bid.
- **Bar simulator and Balke kernel:** the M1 bar's `spread_mean` at the fill bar, added to the bid for buys (the repo's kernels already do this).
- **Floor:** the spread used is max(recorded, 0.5 × that month's median spread). February 2023 has 831 seconds with a zero or inverted spread; no fill may book a cost below half the month's normal.

### 2.2 Slippage: one extra spread
One extra spread (that fill's spread, floored as in 2.1) is charged, × k × lots, on:
- every **stop exit**: any exit triggered by a price level against the position (stop loss, trailing stop, gap stop, ATR or N stop, basket stop, Top 2's cap, channel exits that trigger intrabar);
- every **stop-order entry** (buy-stop or sell-stop breakouts: C14–C19, C28). This is a refinement of the brief, for the reason in BALKE.md: 84% of gold stop entries filled worse than the M1 model;
- **every fill in the first 5 minutes after a session reopen** (the daily break or the weekend), whatever the order type.

Market-order exits at a time, a target or a signal on a close pay the spread only.

### 2.3 Cost stress
"Costs × 1.5" means the spread and the extra slippage are both multiplied by 1.5 at every fill. In the bar simulator this is a re-run with `sp × 1.5` (so stop triggers on the ask move too). In the tick engine the ask is widened to bid + 1.5 × (ask − bid), bid unchanged, in a copy of the arrays.

### 2.4 Constant-percent spread (reported, and a gate for fast rules in §8)
The spread is replaced by **0.21% of the mid price** (the pre-cut pooled median, MARKET §0) at every fill. It removes the cost regime change of §0.5. Reported for every finalist in every split.

### 2.5 Swap
- **Base case: none.** XAGUSD is swap-free by default on Exness (MULTISYMBOL PREREG §9). The status can be withdrawn from accounts that hold large positions overnight regularly; slow trend rules are the risk.
- **Sensitivity (assumed, stated):** charged at the Exness swap time (21:00 UTC summer, 22:00 winter), Monday–Friday, triple on Wednesday. Assumed rates, as a cost on both sides: **long 8% a year, short 3% a year of the notional, /360 per night.** Per 0.01 lot per night: long $0.0111 × P, short $0.0042 × P, where P is the silver price in dollars (at P = $25: $0.28 and $0.10; per 1.00 lot: $27.8 and $10.4).
- **Break-even swap:** the uniform charge per 0.01 lot per night, on both sides, that cuts the profit to zero. Reported with the nights held, long and short.
- If the owner reads the real rates from MT5 (Specification → Swap long / Swap short, in points) into `backtest_results/silver/swap_rates.csv`, the finalists are re-reported with them.

---

## 3. Metrics

All on the **per-unit stream**: one unit = 0.01 lot = 50 oz. A rule that holds several units (pyramids, ladders, EWMAC ±2) holds that many 0.01 lots. Every number is after costs (§2) unless labelled gross. For every variant and split:

| Metric | Definition |
|---|---|
| Profit | net $, costs × 1.0; also at × 1.5, at the constant-% spread, and gross |
| Profit per week | profit / (calendar days / 7) |
| Max DD | peak-to-trough of the equity curve **with floating losses**: tick engine per second; bar models at each M1 bar's worst mark (bid low for longs, ask high for shorts) |
| Profit / DD | profit / max DD; also annualised: (profit per year) / max DD |
| Weekly Sharpe | mean / sd of weekly $ P/L (UTC weeks ending Friday's close) × √52 |
| Positive-quarter share | quarters with P/L > 0 / quarters with any exposure |
| Trades, avg holding time | closed trades (baskets count once); mean hours from first fill to last exit; time in market % |
| Also | long and short P/L; win rate; worst day, worst 5 days, worst week ($); costs paid / gross profit; median spread of the split; profit without the best trade |

**Multiple-testing haircut, reported next to every raw Sharpe and profit/DD:**
- **N = 144**, the total variants of §4 (counted in §4.3). It is reported with every result.
- **Deflated Sharpe ratio** (Bailey & López de Prado 2014): the probability that the true weekly Sharpe is above zero, given N = 144 trials, the cross-variant variance of the DEV Sharpe ratios of all 144 variants, the number of weeks, and the variant's weekly skew and kurtosis. In VAL it uses N = the shortlist size; in the hold-out, N = the number of finalists, and also N = 144.
- **Hansen's SPA test** (studentised, stationary bootstrap, mean block 8 weeks, 5,000 resamples, seed 20261117) over all 144 DEV weekly P/L series against being flat: the p-value of the best variant. Repeated on the shortlist in VAL.
- **E[max Sharpe] under the null** for N = 144 and the DEV length, so that every DEV Sharpe can be read against what the best of 144 random rules would show.

---

## 4. Candidates

### 4.1 Conventions for all candidates
- Long-short unless stated. One position per candidate at a time unless stated (C19 is multi-position, as Balke's).
- Time rules use time-zone-aware conversion (`external.local_seconds` / `utc_of_local`). New York (NY) times: COMEX day session 08:25–13:25 NY; **"before the break" = 16:45 NY** (15 minutes before the Exness break at 17:00 NY).
- No new entry inside the break, in the 5 minutes before it, or in the first 5 minutes after a reopen. Intraday rules are flat at their exit time or 16:45 NY, whichever is first, and never hold over a weekend.
- D1 bars: the session day (the NY day shifted +7 h), with the Sunday stub merged into Monday (`external.day_bars`). Signals on a D1 close are filled at the next M1 bar's open after the reopen.
- Monthly signals: on the last D1 close of the month, filled at the next reopen.
- ATR(n): Wilder ATR on the stated timeframe. N (Turtle) = 20-day Wilder ATR.
- **Code:** new module(s) only, `backtesting/research/silver.py` (and `silver_exam.py` for the exam). They import and call the existing functions; no existing module is edited. Where a repo function hard-codes gold or BTC values (times, % thresholds, `TURTLE_TICK`), the new module passes or re-implements the silver value. The tick 0.001 is used for all entry offsets.
- **Grid neighbours:** on each numeric axis, the next value up and down in the declared grid. Categorical axes (long-only vs long-short, filter on/off) are not neighbour axes. "Split-half" means DEV 2018-11-01 → 2021-01-01 and 2021-01-01 → 2023-01-01.
- Flags: **[M]** = idea or setting from MARKET.md (VAL already seen); **[C]** = control, expected to fail; **[S]** = already seen on silver in 2021-11 → 2024-05 (§0.1); **[Bot]** = the live bot can trade it today (with a branch, `symbols.json` window and an MT5 terminal).
- Grades are the survey's (WEB_SURVEY §2).

### 4.2 The 40 candidates

**Trend following, D1 / monthly / H4 (family TREND)**

| ID | Strategy (grade) | Exact rules | Grid (variants) | Neighbours | Engine |
|---|---|---|---|---|---|
| C01 | 12-month-type TSMOM (A) | Month end: sign of the return over the last L months; hold that sign one month; long-only: long if positive, else flat | L ∈ {6, 9, 12} × {LS, LO} (**6**) | L | bar sim, `tsmom`-style, new |
| C02 | Blended 1/3/12 TSMOM (A) | Month end: s = sign(r1m) + sign(r3m) + sign(r12m) (21/63/252 trading days). "majority": position = sign(s); "unanimous": ±1 only if \|s\| = 3, else flat | {majority, unanimous} × {LS, LO} (**4**) | none; split-half | bar sim, `external.tsmom` |
| C03 | Turtle System 1 (B) [S for votes] [Bot for votes] | 20-day high/low breakout by one tick (stop order), skip after a winning S1 breakout, 55-day failsafe; exit 10-day opposite extreme; stop k·N from the last fill; pyramid +1 unit per ½N to P units | (P=1, 2N), (P=4, 2N), (P=1, 1N), (P=1, 2N, + bot votes), (P=4, 2N, + bot votes) (**5**) | P (within votes on/off); stop k at P=1 no votes | bar sim, `external.turtle(1)` with tick 0.001 |
| C04 | Turtle System 2 (B) [S for votes] [Bot for votes] | 55-day breakout, no skip rule; exit 20-day opposite extreme; stop and pyramid as C03 | as C03 (**5**) | as C03 | bar sim, `external.turtle(2)` |
| C05 | Clenow core trend (B) | Long only if EMA50 > EMA100 (D1), short only if below; enter at the close when it is the highest (lowest) close of B days; exit on a trailing stop m × ATR(100) from the best close since entry (checked on closes) | B ∈ {50, 100} × m ∈ {3, 5} (**4**) | B, m | bar sim, new |
| C06 | Szakmary dual MA, monthly (A/B) | Month end: long if SMA(s) of monthly closes > SMA(l), short (LS) or flat (LO) if below | (s, l) ∈ {(1,10), (1,12), (3,12)} × {LS, LO} (**6**) | the three pairs in that order | bar sim, new |
| C07 | Szakmary channel, monthly (A/B) | Month end: long if the close > highest close of the prior L months, short if < lowest; else keep the position | L ∈ {6, 9, 12} (**3**) | L | bar sim, new |
| C08 | Faber SMA timing (B) | Month end: long if the monthly close > SMA(n) of monthly closes, else flat | n ∈ {8, 10, 12} (**3**) | n | bar sim, new |
| C09 | EWMAC forecast (B) | f = (EWMA_fast − EWMA_slow) / σ, σ = EWMA(span 25) of \|ΔP\| (D1); scaled so the mean \|f\| on DEV-warm-up data (2017-11 → 2018-11) is 10, capped ±20; the blend averages the three scaled forecasts; position = clip(round(f / 10), −2, +2) units; rebalance at the D1 close only when the target differs from the position | (16,64), (32,128), (64,256), blend of the three (**4**) | the three speeds in order | bar sim, new |
| C10 | Donchian ensemble (C) | repo `external.donchian_ensemble` (9 lookbacks, midline stop); per-unit stream = position rounded to whole units, at most 1 | {LO, LS} (**2**) | none; split-half | bar sim |
| C11 | D1 close vs SMA | At the D1 close: long if close > SMA(n), short if below (repo `price_over_sma`, LS) | n ∈ {50, 100, 200} (**3**) | n | bar sim |
| C12 | Supertrend H4 | repo `supertrend` on H4, always in the market | period ∈ {10, 20} × mult ∈ {3, 4} (**4**) | period, mult | bar sim |
| C13 | D1 breakout, fixed hold [M] | At the D1 close, if the close > the prior N-day high (< low): enter long (short) at the next open; exit after H session days at the close; no overlapping trades | N ∈ {20, 55} × H ∈ {1, 5, 20} (**6**) | N, H | bar sim, new |

**Breakouts and intraday momentum (family INTRADAY)**

| ID | Strategy (grade) | Exact rules | Grid | Neighbours | Engine |
|---|---|---|---|---|---|
| C14 | COMEX opening-range breakout (C) [M window] | Range = high/low of the first R min after 08:25 NY; OCO buy stop at range high + 1 tick, sell stop at range low − 1 tick, valid until 12:00 NY; stop = the opposite side; exit at X | R ∈ {15, 30} × X ∈ {13:25 NY, 16:45 NY} (**4**) | R; X (2 values) | bar sim, `balke.range_breakout`-style, new times |
| C15 | 5-min ORB, Zarattini–Aziz (C−) | First M5 bar from 08:25 NY: up close → buy at the next bar's open, down → sell; doji (\|close − open\| < 1 tick) → no trade; stop at the first bar's other extreme; target 10R; else exit at X | X ∈ {13:25, 16:45 NY} (**2**) | X | bar sim, new |
| C16 | Williams volatility breakout (C) | After the reopen, OCO stops at open ± k × (prior session's high − low); stop = 0.5 × k × range from entry; exit 16:45 NY | k ∈ {0.5, 0.75, 1.0} (**3**) | k | bar sim, new |
| C17 | Asian range → London breakout (C) | repo `london_breakout` with silver thresholds: the range filter and the stop cap are gold's × ρ, where ρ = silver/gold median of the same-window range in % of price, computed on DEV only; clock as named; target T × R, break-even at 1.5R, flat at 21:00 server/16:45 NY whichever first | clock ∈ {server, utc} × T ∈ {1.5, 2.5} (**4**) | T | bar sim |
| C18 | Balke Range Breakout, silver windows (C) | Range window W, then OCO stops at its edges until 12:00 NY; stop s% of price; close 16:45 NY; one trade a day | W ∈ {07:00–09:00 London, 08:25–09:30 NY} × s ∈ {1.0, 2.0}% (**4**) | s | Balke kernel, `range_breakout` |
| C19 | Balke ATR Breakout (C) | H1 candle with range > a × ATR(200, H1), close in the outer 25% of the candle → trade in its direction at the next bar; TP/SL in % of price; every signal its own position | a ∈ {2.0, 2.5, 3.0} × (TP, SL) ∈ {(2%, 0.5%) gold's, (4%, 1%) × 2 for silver's vol} (**6**) | a | Balke `multi_account` |
| C20 | Close momentum (B effect, C net) [M window] | At 12:55 NY, sign of the return from the reference R to 12:55; hold that side to 13:25 NY; "high-vol only": only if the 08:25–09:25 NY range > its 20-day median | R ∈ {prior 17:00 NY close, 08:25 NY open} × {all days, high-vol only} (**4**) | none; split-half | bar sim, `last_half_hour` with silver times |
| C21 | Noise-area momentum (C) [M window] | repo `noise_area` on the COMEX session 08:25–13:25 NY, σ over 14 days, bounds × b; checks at :00/:30; exit by trail T or at 13:25 | b ∈ {1.0, 1.5} × T ∈ {VWAP or bound (tighter), bound only} (**4**) | b | bar sim |

**Mean reversion (family MR; all controls)**

| ID | Strategy (grade) | Exact rules | Grid | Neighbours | Engine |
|---|---|---|---|---|---|
| C22 | Connors RSI(2) [C] (D) | Long at the D1 close if RSI(2) < lo and close > SMA200; exit at a close > SMA5; short mirrored (LS) | lo/hi ∈ {5/95, 10/90} × {LO, LS} (**4**) | lo/hi | bar sim, `connors_rsi2` |
| C23 | Bollinger fade, D1 [C] (D) | Close < SMA20 − z·SD20 → long, exit at the close crossing SMA20; short mirrored; 200-day filter: no fade against SMA200 | z ∈ {2.0, 2.5} × filter {off, on} (**4**) | z | bar sim, new |
| C24 | 10-day max/min [C] (D) | Long for the next session when the close is the highest or lowest close of n days | n ∈ {10, 20} (**2**) | n | bar sim, `max_min` |
| C25 | LBMA-auction fade [C] (D) | Short at 12:00 London, exit after D minutes | D ∈ {15, 30} (**2**) | D | bar sim, new |
| C26 | M15 Donchian-20 fade [C] [M] | M15 close beyond the prior 20-bar high (low) → sell (buy) at the next bar; exit after 5 bars; 07:00–16:45 NY only | (**1**) | none; split-half | bar sim, new |

**Gold-led and ratio signals (family GOLD)**

| ID | Strategy (grade) | Exact rules | Grid | Neighbours | Engine |
|---|---|---|---|---|---|
| C27 | Silver catches up to gold, error correction (C; our design on Adrangi et al. 2000) | M15: s = ln XAG − β ln XAU, β by rolling OLS of M15 log returns over 20 sessions; e = s − mean20(s), z = e / sd20(e). Entry when \|z\| > c **and** gold's last-H1 return is beyond ±1 gold ATR(14, H1) in the direction that closes the gap: trade silver only, toward e = 0; exit at z crossing 0, after H M15 bars, or stop at \|z\| ≥ c + 2 (checked on M15 closes); no entries 16:45 NY → reopen + 5 min | c ∈ {1.5, 2.0} × H ∈ {4, 16} (**4**) | c, H | bar sim, new, gold M1 aligned to silver bars by timestamp |
| C28 | Silver follows a gold breakout (C) | H1: gold closes above its prior N-bar high and silver's close is not above its own → buy silver at the next bar; mirror for shorts; exit after E H1 bars or at a stop of 2 × ATR(14, H1) | N ∈ {20, 50} × E ∈ {8, 24} (**4**) | N, E | bar sim, new |
| C29 | Gold-led trend filter (C) | Base rules at fixed settings: C03 (P=1, 2N, no votes), C05 (B=50, m=3), C14 (R=30, 13:25). Filter: longs only when gold's D1 EMA50 > EMA100, shorts only when below; the comparison filter uses **silver's own** EMA50/100 | 3 bases × {gold filter, silver filter} (**6**) | none; split-half; the gold filter must also beat the silver filter on DEV profit/DD to be shortlisted | bar sim |
| C30 | Gold/silver ratio regime (D) | Long silver while GSR (D1 close) > its rolling 250-session median, else flat; "+ trend": also require silver's close > SMA200 | {plain, + trend} (**2**) | none; split-half | bar sim, new |
| C31 | Ratio z-score, silver leg only (D) | z = (ln GSR − SMA_n) / SD_n (D1). z > 2 → long silver, z < −2 → short silver; exit at \|z\| < 0.5 or after 2n sessions; one leg because one strategy per bot | n ∈ {20, 60} (**2**) | n | bar sim, new |

**Seasonality and calendar (family SEASON; all controls)**

| ID | Strategy | Exact rules | Grid | Neighbours | Engine |
|---|---|---|---|---|---|
| C32 | Calendar controls [C] [M for December, Wednesday] | (a) long Sep and Nov (Baur), from the first to the last session of the month; (b) short Friday close → Monday close (Lucey & Tully); (c) long Wednesday session open → close before the break; (d) long December | (**4**) | none; split-half | bar sim, new |
| C33 | Overnight drift [C] [M for 23 UTC] | (a) long from reopen + 5 min to 07:00 London, Mon–Thu sessions; (b) long 23:00 → 23:59 UTC each weekday session that is open then | (**2**) | none; split-half | bar sim, new |

**Filters (family INTRADAY)**

| ID | Strategy (grade) | Exact rules | Grid | Neighbours | Engine |
|---|---|---|---|---|---|
| C34 | US-release filter (B as a filter) | Bases at fixed settings: C14 (R=30, 13:25), C20 (prior close, all days), C21 (b=1.0, VWAP). On NFP days no new entry from 08:25 to 08:45 NY. NFP day = the first Friday of the month (no exceptions; CPI and other dates are not in the store) | 3 bases (**3**) | none; split-half | bar sim |

**The bot's basket designs, re-tuned only inside the grid (family BOT; tick engine, per second)**

All use gold's trading window as before (Mon 01:00 – Fri 22:00 UTC) and the engine's per-second bid/ask. Settings not named are the designs' own (`final10.own_designs`, `multisymbol.BASKETS`).

| ID | Design [flags] | Grid (variants) | Neighbours |
|---|---|---|---|
| C35 | Live logic: Fibonacci ladder, no stop, M15 force-close [S] [Bot] | `target_usd_per_unit` ∈ {$5, $10, $20} (a $0.10 / $0.20 / $0.40 move; the $1 translation is under the spread, INVENTORY #1); `ladder_min_gap` × 0.0245 of gold's (the vol ratio of the $12 caps) (**3**) | target |
| C36 | Slot-5 variant: flat ladder, H4 force-close (also gating entries) [Bot] | as C35 (**3**) | target |
| C37 | Gold V3-lite [S] [Bot] | (`target_vol`, `stop_vol`) ∈ {(6,6), (8,8), (10,10)} (**3**) | the pairs in order |
| C38 | Gold Top 2 [S] [Bot] | (8/4, cap $14.72 per 0.01 lot = the translation), (8/4, cap $30), (10/5, cap $14.72) (**3**) | cap at 8/4; 8/4 ↔ 10/5 at $14.72 |
| C39 | Gold Top 1 + add [S] [Bot] | (target, stop) ∈ {(8,8), (10,8), (12,10)} (**3**) | in order |
| C40 | BTC Top 2 [S] [Bot] | (10/8, cap $30.98 = translation), (8/8, $30.98), (10/8, no cap) (**3**) | (8/8) ↔ (10/8) at $30.98; cap |

**Reference, not a candidate and not counted:** buy-and-hold one 0.01 lot (`balke.buy_hold`) in every split; the exposure-matched benchmark of §8 H4 is built from it.

### 4.3 The count: the multiple-testing burden

| Family | Candidates | Variants |
|---|---|---|
| TREND (C01–C13) | 13 | 6+4+5+5+4+6+3+3+4+2+3+4+6 = **55** |
| INTRADAY (C14–C21, C34) | 9 | 4+2+3+4+4+6+4+4+3 = **34** |
| MR (C22–C26) | 5 | 4+4+2+2+1 = **13** |
| GOLD (C27–C31) | 5 | 4+4+6+2+2 = **18** |
| SEASON (C32–C33) | 2 | 4+2 = **6** |
| BOT (C35–C40) | 6 | 3×6 = **18** |
| **Total** | **40** | **144** |

**N = 144 is reported with every result.** The cost stresses (× 1.5, constant %), the swap sensitivity and the sizing rules of §6 are not extra trials: they are applied to every variant (or every finalist) the same way and never used to pick between variants of one candidate, except where §5 and §6 say so. The STEP and risk-% grids of §6 are sizing choices, counted separately (§5.5).

### 4.4 Rules for running
- If a variant cannot be built as written (a missing field, an impossible time), it is recorded as "not run" with the reason; it still counts in N. No replacement variant is invented.
- Every variant runs on DEV at costs × 1.0 and × 1.5. No variant runs on VAL before `SHORTLIST.md` and its sha256 exist.

---

## 5. Selection

### 5.1 DEV → shortlist (`SHORTLIST.md`, written with its sha256 before any VAL run)
A variant is shortlisted when **all** hold on DEV:

| Rule | Requirement |
|---|---|
| D1 trades | closed trades ≥ 12 if the mean holding time > 5 days; ≥ 40 if 1–5 days; ≥ 150 if < 1 day (baskets count once) |
| D2 profit | > 0 at costs × 1.0 **and** > 0 at costs × 1.5 |
| D3 quarters | positive-quarter share ≥ 50% (at least half; "most" would reject most trend rules, whose median quarter is near zero by their skew) |
| D4 profit / DD | ≥ 1.0 over DEV (about 0.24 a year, 4.17 years) |
| D5 robustness | every grid neighbour (§4.2) has DEV profit > 0 at costs × 1.0; where the candidate has no neighbour axis, both split halves are > 0 |
| D6 survival | the per-unit stream's DEV max DD < $2,000 (the fixed 0.01-lot $2,000 account is not wiped) |
| D7 (C29 only) | the gold-filtered variant beats the same base with silver's own filter on DEV profit/DD |

Reported for every variant, not gates: profit without the best trade, profit without 2020-03-01 → 2020-04-30, the DSR, SPA p-value, E[max Sharpe].

### 5.2 VAL → finalists (`FINALISTS.md` + `FINALISTS.md.sha256`, before the exam)
A shortlisted variant is **eligible** when on VAL: profit > 0 at costs × 1.0 and × 1.5; trades ≥ 3 (mean hold > 5 days), ≥ 10 (1–5 days), ≥ 40 (< 1 day); VAL max DD ≤ 1.5 × its DEV max DD.

**Score** = min(annualised profit/DD in DEV, annualised profit/DD in VAL). Ties: the higher DEV+VAL weekly Sharpe.

**Finalists:** in score order, at most **one variant per candidate**, at most **two per family**, at most **six** in all. [M] candidates are allowed but labelled "VAL not independent". A control [C] is allowed if it passes; the report then discusses it as a likely false positive. The next three eligible variants excluded by the caps are listed.

**If the shortlist is empty:** there are no finalists. The report says so, lists the six closest variants by DEV score (for information), and **the hold-out is not run**: it stays clean for a future pre-registered idea. Spending it on a near miss needs the owner's explicit decision and is a deviation.

**If the shortlist is non-empty but no variant is eligible:** the same as above.

### 5.3 What is frozen in `FINALISTS.md`
For each finalist: candidate, variant, every parameter, the module file and function, the new module's sha256, the cost model (§2), the sizing parameters of §6 chosen on DEV+VAL (the STEP of (ii), the account of (iii), the risk % and caps of (iv)), the DEV and VAL metrics, and the DSR and SPA figures. Then its sha256 goes into `FINALISTS.md.sha256`. The exam module refuses to run if the hash does not match.

### 5.4 The exam
One run per finalist, 2018-11-01 → 2026-11-13, per-unit stream and every sizing of §6, costs × 1.0, × 1.5, constant %, and the swap sensitivity. The hold-out slice is reported. Nothing is re-tuned afterwards; any later idea is a new study.

### 5.5 Sizing choices are trials too
The STEP grid of §6 (ii) has 11 values and (iv) has 3 risk levels: they are chosen on DEV+VAL by the rules in §6, frozen, and the hold-out reports only the frozen choice (plus the others, labelled as not chosen).

---

## 6. Sizing (0.01 lot = 50 oz)

For each finalist, on DEV+VAL (to choose) and then the hold-out (to report):

**(i) Fixed 0.01 lot per unit on $2,000.** Profit, max DD in $ and % of the running peak, lowest equity, wiped or not.

**(ii) The bot's unit rule.** units = max(1, min(⌊balance / STEP⌋ + 1, 10)), taken at each new entry (baskets: re-derived while flat; bar rules: at each trade's entry, adds use the trade's unit), exactly as `app.py` / `turtle.py` / `external._account_kernel`. STEP grid: $5,000, $4,000, $3,000, $2,500 (today), $2,000, $1,750, $1,500, $1,250, $1,000, $750, $500. **Chosen STEP = the lowest STEP whose worst DD ≤ 35% and which is never wiped**, over: the continuous DEV+VAL account from $2,000 on 2018-11-01, and every 12-month account starting on the first of each month from 2018-11 to 2023-07, each from $2,000. Basket designs are re-run in the engine at each STEP (the per-unit replay is not exact for them, SIZING.md). If no STEP qualifies: "none in grid".

**(iii) The smallest account at a fixed 0.01 lot with worst DD ≤ 35%.** = max over the same DEV+VAL accounts of the dollar max DD (with floating) at fixed size / 0.35, rounded up to $100. Also reported: whether $2,000 is enough.

**(iv) Volatility-scaled.** lots = ⌊(r × E_s) / (D × 5,000) / 0.01⌋ × 0.01, where D is the trade's stop distance in price if the rule has one, else 2 × ATR(20, D1) at entry. **Skip the trade if lots = 0.** E_s is the sizing equity under the Turtle drawdown rule: equity × 0.8^⌊DD% / 10⌋ (DD from the running peak). **Cap (R5):** the oz held never exceed 0.25 × equity / (W × P), where W = the worst 5-session % move of silver in DEV+VAL (measured from the data when the module first runs, then frozen) and P the price at entry. r ∈ {0.5%, 1%, 2%}; **1% is the headline**, the other two reported. Rules holding several units (pyramids, EWMAC) size each unit this way. Basket designs: units = ⌊r_b × equity / (the design's worst basket loss per unit, with floating, in DEV+VAL)⌋ with r_b = 3%, skip if 0. Reported: trades taken, skipped and the share skipped; the true risk of each taken trade.

**The 2026-04-21-type event, for every finalist and every sizing.** "A sharp reversal after a strong run-up, hitting an account that has sized up on recent gains."
- **Before the exam (DEV+VAL):** the worst 10-session loss as % of the equity at its start, with its dates and the lots held; and a **stress**: W (above) applied adversely to the account's largest oz held, at that moment's price, as % of that moment's equity. Flag any value > 35%.
- **At the exam (hold-out):** the account's path from 2026-04-07 to 2026-05-05 (equity at the start, minimum, end, peak lots), and the hold-out's own worst 10-session loss as % of the equity at its start.

---

## 7. Portfolio

**The six demo bots** (one unit each, 0.01 lot per unit): gold V3-lite (`demo_hedging_xauusd6`), gold Top 2 (`xauusd7`), gold Top 1 + add (`xauusd8`), BTC Top 2 (`btcusd8`), BTC Turtle S1 + votes (`btcusd7`), BTC Turtle S2 + votes (`btcusd6`). Their per-unit daily P/L is built for 2018-11-01 → 2026-11-13 with the same split slices (baskets: the tick engine per second, per split window; Turtles: the bar simulator), using their frozen settings (`own_designs`, MULTISYMBOL PREREG's inputs).

For each finalist:
- **Correlation** of daily and of weekly per-unit P/L with each of the six bots and with their sum, per split.
- **The effect of adding it:** the sum of the six per-unit streams with and without the finalist, per split: profit, profit per week, max DD with floating (the summed daily marks; intraday floating is not summed across bots, stated), profit/DD, weekly Sharpe. And the same with accounts: each bot on its own $2,000 account at its demo STEP $2,500, the finalist at its frozen sizing (ii), summed.
- **"The best silver bot"** = the finalist that passes §8 with the highest hold-out score (min of annualised profit/DD in VAL and HO); if none passes, the highest-scoring finalist, labelled as failing. The verdict on adding it uses the hold-out only and the multi-symbol study's score (profit per week / max DD of the combined account).

---

## 8. Success: what "works on silver" means

A finalist **passes the exam** when **all** hold on the hold-out, 2024-07-01 → 2026-11-13:

| Rule | Requirement |
|---|---|
| H1 | per-unit profit > 0 at costs × 1.0 **and** > 0 at costs × 1.5 |
| H2 | per-unit profit / DD ≥ 1.0 over the 2.37 years (about 0.42 a year) |
| H3 | survives at a size: under at least one of its frozen sizings (ii), (iii) or (iv, 1%), the hold-out account is never wiped and its worst DD ≤ 35%; for (iv), at least 70% of signals were taken |
| H4 | beats the exposure-matched benchmark: profit − ē × (buy-and-hold profit of one 0.01 lot) > 0, where ē is the time-weighted mean signed position in units over the hold-out. This removes the credit a rule gets for simply being long in the 2025–26 rally |
| H5 | if its mean holding time < 24 h: hold-out profit > 0 also with the constant 0.21%-of-price spread (§2.4) |

**Two labels on a pass:**
- **"Works and fits today's $2,000 bot"** if H3 holds with (i) on $2,000, (ii) at its frozen STEP from $2,000, or (iv) from $2,000.
- **"Works, but needs an account of $X"** if H3 holds only through (iii), with X its frozen smallest account.

**And the strength of the evidence, always stated:** the hold-out DSR with N = number of finalists and with N = 144, and the one-sided p-value of the hold-out weekly mean. A pass with p < 0.05 / (number of finalists) is called **"strong"**; any other pass is called **"passes, weak evidence"** (2.4 years of one market). An [M] finalist's pass is reported as resting on the hold-out alone.

**If nothing passes**, the report says: *"No strategy we tested works on silver after costs at a survivable size. We recommend not running a silver bot; its slot is better used on gold or BTC."* It then gives each finalist's failing rules, the best near misses, and what the costs alone took (gross minus net). Nothing is re-tuned on the hold-out. A new idea needs a new pre-registration, and its clean test must be data after 2026-11-13 (forward or demo trading), because this hold-out is spent.

---

## 9. Run order, gates and budget

1. **Gates, before any candidate runs:**
   - G1: `smoke/smoke.py` prints `ALL PASS`.
   - G2: the new module reproduces, to the cent, the already-seen silver Turtle + votes streams of 2021-11-13 → 2024-05-13 (MULTISYMBOL `runs/summary.csv` lines 432 and 420: S1 −$419.40, max DD $1,394.55, 23 trades; S2 −$1,335.00, max DD $1,381.08, 17 trades). They lie inside DEV+VAL, so the gate reads no hold-out data.
   - G3: on one DEV month per engine, P/L = price move × lots × 5,000 to the cent after removing the §2.2 slippage, and the slippage equals the declared count × spread × k.
   - G4: the loader assertion of §1 fires when a DEV run is given a bar dated 2023-01-01.
   - A failed gate stops the step; the fix is a deviation.
2. **DEV:** all 144 variants at costs × 1.0 and × 1.5 (126 bar/Balke variants: the votes once, about 32 s, then under 1 s each; 18 engine variants × 2 costs × about 25 s on 4.2 years ≈ 15 core-minutes). Then DSR, SPA, `SHORTLIST.md` + sha256.
3. **VAL:** the shortlist only. Then the sizing choices of §6 on DEV+VAL, the pre-exam event stress, `FINALISTS.md` + sha256.
4. **Exam:** §5.4, §6 hold-out, §7, §8. Report `SILVER.md`.
- Long jobs run in the background with logs in `backtest_results/silver/logs/`. Python with `PYTHONDONTWRITEBYTECODE=1`, `NUMBA_CACHE_DIR` and `TMPDIR` under the session scratchpad.
- **Outputs** (nothing committed): `backtest_results/silver/dev/` (`runs.csv` one row per variant × cost, daily streams), `SHORTLIST.md`, `val/`, `FINALISTS.md`, `exam/`, `portfolio/`, `SILVER.md`, `DEVIATIONS_SILVER.md`.

## 10. Limits stated in advance
- **No raw ticks:** the per-second replay is the finest model. Stop fills in a fast market can be worse than one extra spread; the 2020-03-16 and 2021-08-08 moves (1–2 daily ATRs in 5 minutes) are where it matters.
- **One market, short periods:** VAL is 6 quarters and the hold-out 9.5. A slow trend rule makes a handful of trades in each. A pass is weak evidence unless §8 calls it strong.
- **The M1 bar model** fills stop orders at the level (plus the extra spread) and ignores queueing; trailing exits are evaluated on M1 marks.
- **The bar model's spread** is the M1 bar's mean, not the spread at the fill second.
- **Swap** rates are assumed (§2.5) until the owner supplies them.
- **Deploying** anything other than C35–C40 and the Turtle + votes variants (C03/C04 with votes) needs new bot code, a branch, a `symbols.json` silver window and its own MT5 terminal. The Turtle on silver also needs `TURTLE_TICK` = 0.001 and the Sunday-stub merge in `turtle.py` (INVENTORY §3.2 #13).
