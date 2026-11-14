# Backtest of the hedging strategy on real Exness ticks

This branch adds a tick-level backtester for the live bot and the results of running it. Nothing in the live files was changed. The strategy tested is exactly what `strategy.py` / `constants.py` on this branch do: open on the H1x1 + M15x1 slope score with full M15 agreement, an RSI ladder of Fibonacci-sized adds, a force-close on an M15 slope reversal, and as profit exit a fixed target (close when basket profit exceeds $1 × unit).

- **Results page:** [`backtest_results/index.html`](backtest_results/index.html) (open in a browser; every chart is interactive)
- **Per-run reports:** linked in the table below — candles with every fill, equity, attribution, second-by-second close-ups
- **Replay studio:** `python -m backtesting studio` — watch the bot trade the history tick by tick
- **How it works, how to run it:** [`backtesting/README.md`](backtesting/README.md)

## Results with the live settings

$2,000 start, 1:2000 account leverage (BTC margined at 1:400), unit auto-stepped from the balance exactly as the bot does it (`floor(balance / 2500) + 1`), real bid/ask quotes. The three-month runs replay every tick at the live loop's cadence (one pass a second, 0.1 s more after an order, 1 s more after a ladder add); the fifteen-month runs use the per-second series (one pass on every whole second).

| Run | Net P/L | Return | Max drawdown | Baskets | Win rate | Needed to break even | Avg win / avg loss | Worst basket | Stopped out | Same run, fixed 0.01-lot unit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| [XAUUSDm · 3 months: 13 Aug → 13 Nov 2026](backtest_results/baseline/XAUUSDm/report.html) | −$793 | -39.6% | $3,380 (95%) | 3,620 | 93.5% | 94.1% | +$2.22 / −$35.15 | −$1,821 | no | +$347 |
| [BTCUSDm · 3 months: 13 Aug → 13 Nov 2026](backtest_results/baseline/BTCUSDm/report.html) | +$316 | +15.8% | $593 (24%) | 2,608 | 81.7% | 79.7% | +$1.24 / −$4.84 | −$125 | no | +$316 |
| [XAUUSDm · 15 months: 13 Aug 2025 → 13 Nov 2026](backtest_results/long/XAUUSDm/report.html) | −$2,000 | -100.0% | $2,082 (100%) | 1,919 | 89.3% | 93.9% | +$1.40 / −$21.56 | −$309 | **yes, on 2025-10-14** (day 62 of 457) | −$2,000 |
| [BTCUSDm · 15 months: 13 Aug 2025 → 13 Nov 2026](backtest_results/long/BTCUSDm/report.html) | −$2,000 | -100.0% | $2,020 (100%) | 5,350 | 85.0% | 88.3% | +$1.30 / −$9.87 | −$379 | **yes, on 2026-02-06** (day 177 of 457) | −$2,000 |

A run that is stopped out ends there: its basket count, win rate and averages describe the days up to the stop-out, not the whole period.

A *basket* is one fresh entry plus its ladder adds, closed together. "Fixed 0.01-lot unit" is the same run with the balance auto-step switched off.

### Quarter by quarter, and how much is timing luck

One run is one path. Whether the bot happens to be inside a basket when a sharp move starts depends on which tick its once-a-second poll lands on, and a few large baskets decide a quarter. The live loop does not poll on a fixed grid either: it sleeps a second and then spends a varying time talking to the terminal. So each of the five quarters was run eight times on raw ticks, on a fresh $2,000, with every pass of the loop taking between 0 and 0.2 s longer, drawn at random (eight different random sequences). All eight are equally plausible for the live bot; the run in the table above is a ninth path, on the fixed one-second grid.

**XAUUSDm**

| Quarter | Median net P/L | Worst timing | Best timing | Runs that lost money | Runs stopped out | Median max drawdown | Worst basket | Baskets (median) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Aug–Nov 2025 (hold-out) | −$2,000 | −$2,000 | −$2,000 | 8 of 8 | 8 of 8 | 100% | −$613 | 1,670 |
| Nov 2025–Feb 2026 (hold-out) | −$1,277 | −$2,000 | +$572 | 7 of 8 | 4 of 8 | 91% | −$1,944 | 3,616 |
| Feb–May 2026 | −$2,000 | −$2,000 | −$2,000 | 8 of 8 | 8 of 8 | 100% | −$1,806 | 1,586 |
| May–Aug 2026 | −$2,000 | −$2,000 | −$694 | 8 of 8 | 6 of 8 | 100% | −$1,680 | 643 |
| Aug–Nov 2026 | −$351 | −$2,000 | +$58.20 | 6 of 8 | 1 of 8 | 59% | −$1,818 | 3,644 |

37 of 40 quarter-runs lost money; 27 ended with the account stopped out.

**BTCUSDm**

| Quarter | Median net P/L | Worst timing | Best timing | Runs that lost money | Runs stopped out | Median max drawdown | Worst basket | Baskets (median) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Aug–Nov 2025 (hold-out) | −$1,369 | −$1,822 | −$1,007 | 8 of 8 | 0 of 8 | 73% | −$412 | 2,798 |
| Nov 2025–Feb 2026 (hold-out) | −$1,407 | −$1,535 | −$1,227 | 8 of 8 | 0 of 8 | 84% | −$811 | 2,809 |
| Feb–May 2026 | −$286 | −$403 | −$250 | 8 of 8 | 0 of 8 | 25% | −$225 | 2,493 |
| May–Aug 2026 | −$190 | −$329 | +$316 | 6 of 8 | 0 of 8 | 23% | −$486 | 2,374 |
| Aug–Nov 2026 | +$282 | +$171 | +$356 | 0 of 8 | 0 of 8 | 26% | −$135 | 2,595 |

30 of 40 quarter-runs lost money; 0 ended with the account stopped out.

## What the backtest says about the strategy

**1. Over the fifteen months tested the live settings lose on both symbols**  
Each quarter was run eight times on raw ticks on a fresh $2,000 with the live unit auto-step, with only the loop's timing drawn at random. Median result per quarter, gold: Aug–Nov 2025 −$2,000; Nov 2025–Feb 2026 −$1,277; Feb–May 2026 −$2,000; May–Aug 2026 −$2,000; Aug–Nov 2026 −$351; 37 of 40 quarter-runs lost money and 27 ended with the account stopped out. BTC: Aug–Nov 2025 −$1,369; Nov 2025–Feb 2026 −$1,407; Feb–May 2026 −$286; May–Aug 2026 −$190; Aug–Nov 2026 +$282; 30 of 40 lost money and 0 were stopped out. Run as one continuous account from 13 Aug 2025, gold was stopped out on 14 Oct 2025, day 62 and BTC was stopped out on 6 Feb 2026, day 177. The three months you asked for (13 Aug–13 Nov 2026) are the best of the five for gold and the best of the five for BTC, so they flatter the strategy.

**2. It wins small and often and loses big and rarely, and the rare losses decide the result**  
Gold, 13 Aug–13 Nov 2026: 93.5% of 3,620 baskets won, and it needs 94.1% to break even, because the average win is +$2.22 and the average loss −$35.15 (one loss cancels 16 wins). The worst basket lost $1,821, as much as 821 average wins; the ten worst gave back 51% of everything the winners made. The quarter ended −$793. BTC, 13 Aug–13 Nov 2026: 81.7% of 2,608 baskets won, and it needs 79.7% to break even, because the average win is +$1.24 and the average loss −$4.84 (one loss cancels 4 wins). The worst basket lost $125, as much as 101 average wins; the ten worst gave back 23% of everything the winners made. The quarter ended +$316. A win rate above 80 or 90% says nothing by itself: what matters is the point or two between the win rate and the break-even rate (gold 0.6 short of it, BTC 2.0 above), and that is decided by a handful of baskets.

**3. One run is one path: the same quarter ends up or down depending on which ticks the loop happens to poll**  
Gold, 13 Aug–13 Nov 2026, same settings, same ticks, eight random loop timings: from −$2,000 to +$58 (median −$351); with no random delay −$793. BTC: from +$171 to +$356 (median +$282); no random delay +$316. The reason is the pay-off above: whether the bot is inside a basket when a sharp move starts depends on the second it entered, and one such basket outweighs a month of wins. Even at one fixed 0.01-lot unit the result of a gold quarter moved by $2,197 at the median, and by up to $3,516, with nothing changed but the loop timing. So no single backtest figure, and no single live month, tells you whether a setting is good; only the spread over many runs and many quarters does.

**4. The ladder is not a ladder: the last three adds usually go in about two seconds apart, at one price**  
Each add is released when the RSI of its timeframe is beyond 35 / 65, which is a level, not a new event. When the M15, H1 and H4 RSI are already there, the third, fourth and fifth add fire on consecutive passes of the loop. On gold 85–100% of those adds came within ten seconds of the previous one (median 2 s), $0.24–0.28 away from it; the median spread at its entries is $0.26 (the quarter's median quote spread was $0.24). So 26 of the 32 units of a full ladder are one clip at one price, not an average-down. Gold baskets that never added made +$4,251 in the quarter; baskets that added lost $5,040; the 40 that reached all six positions account for −$1,839, with an average loss of $567 when they lost. BTC shows the same timing (79–98% within ten seconds): +$1,191 without adds, −$874 with.

**5. The only loss exit watches momentum pivots, not price or money, and nothing stands behind it**  
A losing basket is closed when the M15 RSI / MACD pivot score turns against it. In a steady adverse move that score stays neutral or supportive. The worst gold basket of the quarter was a BUY of 0.64 lots opened on 22 Oct 2026 at 4,037.27: it was held 7.3 hours while price moved $28.45 against its average entry and was closed at −$1,821. 67% of gold's losing baskets were closed within 10% of the worst point they ever showed, 28% had been in profit before, and one basket that ended as a winner had been $1,003 under water on the way. There is no price stop, no time stop and no equity stop, and the stop sent to the broker is not a stop (see the live-code findings).

**6. The entry signal says nothing about where price goes next**  
An entry needs the M15 RSI vote and the M15 MACD vote to agree. Both are measured from the last pivot of their indicator, so both are votes to fade the last extreme: over the fifteen months the MACD vote pointed against its own signal-line trend on 80% of gold's M15 bars (79% for BTC), and 88% of RSI up-votes came after an oversold low. Tested on every closed M15 bar with the live indicator code: after both votes pointed up, gold was higher four bars later 50.8% of the time, against 50.8% for any bar; after both pointed down it was lower 49.9% of the time, against 49.2%. BTC: 51.5% against 50.0%, and 50.8% against 50.0%. That is a coin flip. The wins come from the target being close and the stop being absent, not from the signal knowing direction, which is why the timeframes the signal is read on cannot fix the result.

**7. The spread takes a large share of what the winners make**  
Gold paid $2,945 of spread in the quarter, 39% of the winners' gross profit, on 39 baskets a day; before spread the closed baskets net +$2,157, after it −$788 (−$793 with the basket still open at the end). BTC paid $728 (28% of the winners' gross). A $1 target on 0.01 lot is a $1 move in gold against a median spread at entry of $0.26. The spread was not the same in every quarter (see the hold-out section), and the strategy's result moves with it.

**8. The unit auto-step raises the stake after a good run and the next loss is taken at the larger size**  
The unit is floor(balance / 2,500) + 1, re-derived whenever the account is flat. In the gold quarter: unit 1: 1,607 baskets, +$124 (worst −$295); unit 2: 2,013 baskets, −$912 (worst −$1,821). The account crossed $2,500 on small wins at one unit and gave it back at two. Because the target also scales with the unit while the worst case of a basket has no limit, stepping up multiplies the tail, not the edge.

**9. No choice of timeframes makes it pay: settings that look good on one period do not hold on another**  
432 combinations of OPEN and FORCE-CLOSE timeframes were run on five quarters (one fixed 0.01-lot unit; "wiped" replays the baskets on a real $2,000 account with the bot's lot sizing). Gold: 12 of 432 settings were profitable in all three analysed quarters without wiping a $2,000 account. On the two hold-out quarters 0% of those were profitable in both and 75% wiped the account in one (mean −$1,164 a quarter), against 6% and 75% (mean −$1,245) for all settings; rank correlation between the two periods +0.30. BTC: 25 of 432 settings were profitable in all three analysed quarters without wiping a $2,000 account. On the two hold-out quarters 0% of those were profitable in both and 80% wiped the account in one (mean −$1,423 a quarter), against 0% and 71% (mean −$1,706) for all settings; rank correlation between the two periods +0.37. No gold setting was profitable in all five quarters without wiping the account. No BTC setting was profitable in all five quarters without wiping the account. Averaged over all five quarters every timeframe loses. As an OPEN timeframe slower loses less: strictly in order on BTC, on gold with M30 out of line. As FORCE-CLOSE, gold's H4 and H1 lose least but M30 loses more than M15 and M5; on BTC there is no clear order. Mean net per quarter, gold: FORCE-CLOSE on H4 −$271, H1 −$429, M30 −$1,723, M15 −$1,132, M5 −$1,416, M1 −$2,159; OPEN containing H4 −$664, H1 −$888, M15 −$910, M30 −$1,280, M5 −$1,450, M1 −$1,738. BTC: FORCE-CLOSE on H4 −$606, H1 −$1,185, M30 −$696, M15 −$617, M5 −$1,030, M1 −$1,655; OPEN containing H4 −$723, H1 −$794, M30 −$869, M15 −$927, M5 −$1,053, M1 −$1,298. The live setting (OPEN H1+M15, FORCE-CLOSE M15) on gold: Aug–Nov 2025 −$2,461, Nov 2025–Feb 2026 +$854, Feb–May 2026 −$2,299, May–Aug 2026 −$2,356, Aug–Nov 2026 +$296. Keep in mind that each cell is a single path whose result moves by about $2,200 a quarter on gold (up to $3,500) and a few hundred dollars on BTC with the loop timing alone.

**10. Removing the ladder cuts the worst loss many times over; nothing tested makes the live timeframes reliably profitable**  
Each what-if changes one rule, or one small package of rules, and leaves the rest live (one fixed unit, three 2026 quarters, single paths). Gold: live settings: −$4,359 over three quarters, worst basket −$1,687, account wiped; no ladder: −$2,321 over three quarters, worst basket −$217; ladder: adds >= $3 apart: −$2,701 over three quarters, worst basket −$1,243, account wiped; stop: $20 per unit: −$5,107 over three quarters, worst basket −$166, account wiped; no ladder + stop $10: −$2,807 over three quarters, worst basket −$58; cooldown 30 min: −$2,928 over three quarters, worst basket −$1,687, account wiped; signals on closed bars: −$6,829 over three quarters, worst basket −$2,545, account wiped. BTC: live settings: −$340 over three quarters, worst basket −$484; no ladder: −$248 over three quarters, worst basket −$26; ladder: adds >= $300 apart: −$147 over three quarters, worst basket −$84; stop: $20 per unit: −$2,074 over three quarters, worst basket −$45; no ladder + stop $10: −$296 over three quarters, worst basket −$13; cooldown 30 min: −$966 over three quarters, worst basket −$484; signals on closed bars: −$904 over three quarters, worst basket −$377. A stop alone turns a rare large loss into frequent medium ones; the ladder is what makes the large loss large. These are directions to test on a demo account, not settings to deploy. Spacing the ladder cut the worst loss many times over on BTC but only by about a quarter on gold.

**11. What does hold up on data it was never fitted to: a with-trend design with a real stop and no ladder (gold)**  
Designs were chosen on 13 Aug 2025 – 13 Nov 2026 and Jan 2024 – Jun 2025, frozen, and then run once on Feb – Dec 2023 (three quarters and one two-month block), which had played no part in any choice (every tick, eight loop timings per quarter, a real $2,000 account with the bot's unit rule). V3-lite, entries only with the H1 trend (H1 MACD signal line), H1 votes with M15 agreement, stop and target 8 H1-volatility units on the whole basket, no ladder, a 12 h pause after a losing basket, made +$106 per block on gold in 2023 with no losing run of 32, and +$152 a quarter with none of 48 losing in 2024 – mid 2025; the live settings lost $666 and $675 a quarter there. On BTC no design made money reliably: V3-lite +$7 a quarter in 2023, the live settings lost $1,194. About 1,200 designs were tried, so the 2023 figure is the honest one; the edge is small (gold about +$4 a basket). See IMPROVEMENT.md.

**12. Support and resistance, and the other ways to recover a losing position, do not add an edge**  
Two independent studies of H1, H4 and D1 levels (swing highs and lows, the previous day's and week's high and low, round numbers): price turned at the levels no more often than at placebo prices, and no bounce rule made money after the spread in either period. A few gold breakout and retest rules with the trend were slightly positive in both, but they were found after the fact and did no better than placebo levels in 2025-26. Forty-two position-management mechanisms on the same 32,553 entries (averaging down with a budget, averaging up, break-even and trailing stops, scale-out, hedge lock, zone recovery, stop-and-reverse, martingale): none raised the expectancy; they only change how the result is distributed. A ladder with equal lots, at most two adds and a hard $60 budget, flat over every market closure, never lost more than $60 (held over closures, up to −$222 on gold), and earned no more than not adding. A hedge lock unlocked on the next signal pays exactly what closing and re-entering pays; a lock that is simply closed later costs one spread more than a stop. Reports: backtest_results/improve/.

## XAUUSDm: the three months in pictures

Measured on the baseline run (numbers in [`diagnostics.json`](backtest_results/baseline/XAUUSDm/diagnostics.json)):

- **Pay-off.** 93.5% of 3,620 baskets won; break-even needs 94.1%. Average win +$2.22, average loss −$35.15 (one loss = 16 wins). The worst basket (−$1,821) cancelled 821 average wins; the ten worst gave back 51% of everything the winners made.
- **Ladder.** 1,145 adds in 649 baskets. Share of each tier's adds that came within 10 s of the previous fill: M1 12% (median 453 s, $4.82 away); M5 43% (median 44 s, $1.26 away); M15 85% (median 2 s, $0.28 away); H1 97% (median 2 s, $0.24 away); H4 100% (median 2 s, $0.24 away). Baskets with no add: +$4,251; baskets with at least one add: −$5,040.
- **Full ladders.** 40 baskets reached all 6 positions: 90% won +$11.88 on average, the rest lost −$567 on average (worst −$1,821); net −$1,839.
- **Exits.** 67% of losing baskets were closed within 10% of the largest loss they ever showed. Losers were held a median 11 min, the longest 7.3 h. Winners were at worst −$1,003 under water before recovering.
- **Spread.** $2,945 paid, 39% of the winners' gross profit. Before spread the run nets +$2,157; after it −$788.

![Three months at a glance: price with every exit, account, exposure, scores.](backtest_results/img/XAUUSDm_overview.png)

*Three months at a glance: price with every exit, account, exposure, scores.*

![Thirty hours up close: every entry, ladder add and exit at its fill price.](backtest_results/img/XAUUSDm_zoom.png)

*Thirty hours up close: every entry, ladder add and exit at its fill price.*

![Where the money came from and where it went.](backtest_results/img/XAUUSDm_attribution.png)

*Where the money came from and where it went.*

![The worst basket, second by second.](backtest_results/img/XAUUSDm_worst_basket.png)

*The worst basket, second by second.*

![The same settings over the whole history.](backtest_results/img/XAUUSDm_long_equity.png)

*The same settings over the whole history.*

## BTCUSDm: the three months in pictures

Measured on the baseline run (numbers in [`diagnostics.json`](backtest_results/baseline/BTCUSDm/diagnostics.json)):

- **Pay-off.** 81.7% of 2,608 baskets won; break-even needs 79.7%. Average win +$1.24, average loss −$4.84 (one loss = 4 wins). The worst basket (−$125) cancelled 101 average wins; the ten worst gave back 23% of everything the winners made.
- **Ladder.** 1,570 adds in 823 baskets. Share of each tier's adds that came within 10 s of the previous fill: M1 5% (median 1045 s, $1.26 away); M5 37% (median 179 s, $0.55 away); M15 79% (median 2 s, $0.10 away); H1 93% (median 2 s, $0.08 away); H4 98% (median 2 s, $0.08 away). Baskets with no add: +$1,191; baskets with at least one add: −$874.
- **Full ladders.** 81 baskets reached all 6 positions: 93% won +$3.72 on average, the rest lost −$68.79 on average (worst −$125); net −$134.
- **Exits.** 65% of losing baskets were closed within 10% of the largest loss they ever showed. Losers were held a median 17 min, the longest 4.6 h. Winners were at worst −$540 under water before recovering.
- **Spread.** $728 paid, 28% of the winners' gross profit. Before spread the run nets +$1,045; after it +$317.

![Three months at a glance: price with every exit, account, exposure, scores.](backtest_results/img/BTCUSDm_overview.png)

*Three months at a glance: price with every exit, account, exposure, scores.*

![Thirty hours up close: every entry, ladder add and exit at its fill price.](backtest_results/img/BTCUSDm_zoom.png)

*Thirty hours up close: every entry, ladder add and exit at its fill price.*

![Where the money came from and where it went.](backtest_results/img/BTCUSDm_attribution.png)

*Where the money came from and where it went.*

![The worst basket, second by second.](backtest_results/img/BTCUSDm_worst_basket.png)

*The worst basket, second by second.*

![The same settings over the whole history.](backtest_results/img/BTCUSDm_long_equity.png)

*The same settings over the whole history.*

## What the entry signal is made of

An entry needs the M15 RSI vote and the M15 MACD vote to point the same way. Measured with the live `indicator.py` functions on every closed M15 bar (no spread, no ladder, no exits — this describes the signal, not the trading). The MACD vote compares the histogram with its last pivot on the side the signal line selects, so in an up-trend it reads "down" unless momentum makes a new high; the RSI vote is measured from the last pivot beyond 60 / 40. Both are therefore votes to fade the last extreme. The bold columns are the test of whether that predicts anything: after both votes agreed, how often was price further that way four bars later, against how often that happens on any bar. Neighbouring bars overlap (each looks four bars ahead), so a difference of a point or two between a bold figure and its neighbour is within noise. A bar that closed unchanged counts as neither higher nor lower in the bold columns; in the (any bar) lower column it counts as lower.

### XAUUSDm

| Period | M15 bars | MACD vote against its own trend | RSI up-votes that follow an oversold low | Both votes up (share of bars) | … price higher 4 bars later | (any bar) | Both votes down (share of bars) | … price lower 4 bars later | (any bar)  |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Aug–Nov 2025 | 6,057 | 80% | 83% | 30% | **52.8%** | 54.1% | 43% | **44.8%** | 45.9% |
| Nov 2025–Feb 2026 | 5,838 | 79% | 84% | 33% | **53.1%** | 54.2% | 39% | **45.6%** | 45.8% |
| Feb–May 2026 | 5,697 | 80% | 91% | 37% | **52.0%** | 50.0% | 35% | **52.4%** | 50.0% |
| May–Aug 2026 | 6,030 | 80% | 91% | 38% | **48.2%** | 47.9% | 34% | **53.8%** | 52.1% |
| Aug–Nov 2026 | 6,058 | 79% | 92% | 38% | **48.8%** | 48.0% | 33% | **54.9%** | 52.0% |
| All fifteen months | 29,680 | 80% | 88% | 35% | **50.8%** | 50.8% | 37% | **49.9%** | 49.2% |

### BTCUSDm

| Period | M15 bars | MACD vote against its own trend | RSI up-votes that follow an oversold low | Both votes up (share of bars) | … price higher 4 bars later | (any bar) | Both votes down (share of bars) | … price lower 4 bars later | (any bar)  |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Aug–Nov 2025 | 8,736 | 79% | 90% | 36% | **53.2%** | 50.2% | 35% | **50.7%** | 49.8% |
| Nov 2025–Feb 2026 | 8,807 | 79% | 92% | 36% | **52.5%** | 50.1% | 34% | **51.0%** | 49.9% |
| Feb–May 2026 | 8,352 | 78% | 89% | 36% | **50.7%** | 50.3% | 36% | **50.1%** | 49.7% |
| May–Aug 2026 | 8,832 | 79% | 92% | 35% | **50.3%** | 49.2% | 36% | **51.3%** | 50.8% |
| Aug–Nov 2026 | 8,832 | 79% | 90% | 35% | **50.7%** | 50.3% | 36% | **51.0%** | 49.7% |
| All fifteen months | 43,559 | 79% | 91% | 36% | **51.5%** | 50.0% | 36% | **50.8%** | 50.0% |

## Which timeframes for OPEN, FORCE-CLOSE — RSI and MACD

Each setting was run on three separate three-month windows: the one asked for (13 Aug → 13 Nov) and the two before it. To compare settings fairly they all trade a fixed 0.01-lot unit on a balance that cannot be stopped out; the column "wiped $2,000" then says whether the real account would have survived. A timeframe choice is only worth anything if it holds up on windows it was not picked on.

### XAUUSDm

![XAUUSDm: OPEN x FORCE-CLOSE timeframes on three windows](backtest_results/img/XAUUSDm_timeframes.png)

| Window | Combinations profitable | Median net | Best | Worst | Would have wiped $2,000 |
|---|---:|---:|---:|---:|---:|
| Aug–Nov 2026 | 41% | −$404 | +$2,812 | −$7,534 | 29% |
| May–Aug 2026 | 19% | −$1,740 | +$3,714 | −$11,124 | 65% |
| Feb–May 2026 | 37% | −$891 | +$5,717 | −$8,433 | 69% |

432 combinations of OPEN timeframes × FORCE-CLOSE timeframe × threshold convention. **12** made money in all 3 quarters without wiping a real $2,000 account; 368 wipe it out in at least one quarter. ("Wiped" replays each setting's baskets on a $2,000 account with the bot's own lot sizing: the unit steps up above $2,500, so later losses are larger than at the fixed unit shown in the net columns.)

**How much of one cell is luck.** The live setting itself, at the same fixed 0.01-lot unit, run eight times per quarter on raw ticks with nothing changed but the loop timing: Aug–Nov 2025 −$2,742 to −$1,466; Nov 2025–Feb 2026 −$2,081 to +$1,039; Feb–May 2026 −$3,944 to −$1,746; May–Aug 2026 −$4,210 to −$694; Aug–Nov 2026 −$676 to +$427. The spread inside one quarter was $2,197 at the median and $3,516 at most. Differences of that size between two settings in the tables below are not evidence; only patterns that repeat across quarters are.

Does choosing on one window work on another?

| Chosen on → tested on | Rank correlation | Top 10% there | Same settings here | Best single setting there → here |
|---|---:|---:|---:|---:|
| Aug–Nov 2026 → May–Aug 2026 | +0.04 | +$1,806 | −$3,368 | +$2,812 → −$1,959 |
| Aug–Nov 2026 → Feb–May 2026 | +0.36 | +$1,806 | +$456 | +$2,812 → +$2,187 |
| May–Aug 2026 → Aug–Nov 2026 | +0.04 | +$1,494 | −$4.65 | +$3,714 → −$1,942 |
| May–Aug 2026 → Feb–May 2026 | +0.31 | +$1,494 | +$1,112 | +$3,714 → +$4,074 |
| Feb–May 2026 → Aug–Nov 2026 | +0.36 | +$2,692 | +$204 | +$5,717 → −$522 |
| Feb–May 2026 → May–Aug 2026 | +0.31 | +$2,692 | −$1,048 | +$5,717 → +$2,969 |

The live setting and the ten that held up best on these three quarters (sorted by quarters survived, quarters profitable, worst quarter). Net P/L of one fixed 0.01-lot unit; ✕ = the same baskets wipe a real $2,000 account in that quarter (the bot's own lot sizing applied). This ranking is hindsight; the hold-out section tests it.

|  | OPEN | FORCE-CLOSE | Entry needs | FC fires on | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Deepest dip of the $2,000 account | Baskets / quarter |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **live** | H1+M15 | M15 | one TF fully aligned | one indicator reversing | +$296 | −$2,356 ✕ | −$2,299 ✕ | $2,000 | 3,720 |
|  | H4+M5 | H1 | one TF fully aligned | one indicator reversing | +$598 | +$504 | +$1,702 | $1,229 | 1,903 |
|  | H4+M15 | M15 | every TF fully aligned | both reversing | +$385 | +$423 | +$571 | $838 | 2,047 |
|  | H4 | M15 | one TF fully aligned | both reversing | +$353 | +$396 | +$397 | $838 | 2,039 |
|  | H4+M15 | M30 | one TF fully aligned | both reversing | +$595 | +$1,401 | +$328 | $1,896 | 2,185 |
|  | H1+M1 | M15 | every TF fully aligned | both reversing | +$765 | +$1,015 | +$296 | $539 | 1,706 |
|  | H1+M1 | M15 | every TF fully aligned | one indicator reversing | +$503 | +$432 | +$223 | $946 | 1,707 |
|  | H4+M5 | H1 | one TF fully aligned | both reversing | +$948 | +$216 | +$1,716 | $1,570 | 1,902 |
|  | H4+M1 | M15 | every TF fully aligned | both reversing | +$192 | +$400 | +$630 | $592 | 1,180 |
|  | H4+M15 | M15 | every TF fully aligned | one indicator reversing | +$290 | +$206 | +$183 | $498 | 2,050 |
|  | H4+M1 | M15 | every TF fully aligned | one indicator reversing | +$102 | +$162 | +$343 | $678 | 1,180 |

Averaged over every combination that contains the timeframe:

| Timeframe | in OPEN: mean net / window | in OPEN: wiped $2,000 | as FORCE-CLOSE: mean net / window | as FORCE-CLOSE: wiped $2,000 |
|---|---:|---:|---:|---:|
| H4 | −$385 | 37% | +$157 | 73% |
| H1 | −$986 | 50% | −$315 | 57% |
| M30 | −$1,305 | 56% | −$1,522 | 53% |
| M15 | −$823 | 50% | −$1,170 | 40% |
| M5 | −$1,445 | 59% | −$1,514 | 44% |
| M1 | −$1,708 | 70% | −$2,541 | 60% |

**OPEN: RSI slope on one timeframe, MACD slope on another.** Three quarters added up, one fixed 0.01-lot unit; in brackets the number of quarters that were profitable; ✕ = wipes a real $2,000 account in one of them. On the diagonal both indicators read the same timeframe. Every cell needs both votes to agree: grey-fill (a grey vote borrowing the other's sign) only exists when both sit on one timeframe, so it is off throughout this grid to keep the cells comparable.

| RSI ↓ / MACD → | H4 | H1 | M30 | M15 | M5 | M1 |
|---|---:|---:|---:|---:|---:|---:|
| **H4** | +$356 (2/3) | +$478 (2/3) | −$502 (1/3) | +$352 (2/3) | −$596 (1/3) | −$654 (2/3) |
| **H1** | +$470 (2/3) | −$778 ✕ (1/3) | +$297 ✕ (2/3) | −$1,801 ✕ (2/3) | −$2,718 ✕ (1/3) | +$316 ✕ (2/3) |
| **M30** | −$129 (2/3) | −$1,988 (0/3) | −$4,265 ✕ (0/3) | −$4,256 ✕ (1/3) | −$5,915 ✕ (1/3) | −$4,253 ✕ (1/3) |
| **M15** | +$53.34 (2/3) | −$1,948 (0/3) | −$3,864 ✕ (0/3) | −$6,873 ✕ (0/3) | −$6,954 ✕ (1/3) | −$6,443 ✕ (0/3) |
| **M5** | −$2,375 ✕ (0/3) | −$1,978 (1/3) | −$3,167 ✕ (1/3) | −$5,614 ✕ (1/3) | −$10,334 ✕ (0/3) | −$7,781 ✕ (0/3) |
| **M1** | −$2,600 (0/3) | −$3,019 ✕ (1/3) | −$6,043 ✕ (0/3) | −$10,478 ✕ (0/3) | −$7,880 ✕ (0/3) | −$7,160 ✕ (0/3) |

**FORCE-CLOSE: RSI slope on one timeframe, MACD slope on another.** Three quarters added up, one fixed 0.01-lot unit; in brackets the number of quarters that were profitable; ✕ = wipes a real $2,000 account in one of them. On the diagonal both indicators read the same timeframe. Every cell needs both votes to agree: grey-fill (a grey vote borrowing the other's sign) only exists when both sit on one timeframe, so it is off throughout this grid to keep the cells comparable.

| RSI ↓ / MACD → | H4 | H1 | M30 | M15 | M5 | M1 |
|---|---:|---:|---:|---:|---:|---:|
| **H4** | +$4,079 ✕ (2/3) | +$2,335 ✕ (2/3) | +$2,601 ✕ (2/3) | +$722 ✕ (2/3) | +$1,529 (3/3) | −$632 ✕ (1/3) |
| **H1** | +$757 ✕ (2/3) | +$2,834 ✕ (2/3) | −$4,977 ✕ (1/3) | −$424 ✕ (1/3) | −$852 ✕ (1/3) | +$1,447 ✕ (2/3) |
| **M30** | −$1,546 ✕ (1/3) | +$2,053 ✕ (2/3) | −$5,605 ✕ (1/3) | −$1,338 ✕ (1/3) | −$2,338 (0/3) | −$1,199 ✕ (2/3) |
| **M15** | −$1,836 ✕ (1/3) | +$503 ✕ (2/3) | −$1,678 ✕ (2/3) | −$4,359 ✕ (1/3) | −$4,416 ✕ (0/3) | −$4,878 ✕ (0/3) |
| **M5** | −$1,262 ✕ (2/3) | +$696 ✕ (1/3) | −$4,335 ✕ (1/3) | −$4,181 ✕ (1/3) | −$4,964 ✕ (0/3) | −$4,220 ✕ (0/3) |
| **M1** | +$4.12 ✕ (2/3) | −$1,577 ✕ (1/3) | −$2,904 ✕ (2/3) | −$4,346 ✕ (1/3) | −$5,054 ✕ (0/3) | −$5,466 ✕ (0/3) |

### BTCUSDm

![BTCUSDm: OPEN x FORCE-CLOSE timeframes on three windows](backtest_results/img/BTCUSDm_timeframes.png)

| Window | Combinations profitable | Median net | Best | Worst | Would have wiped $2,000 |
|---|---:|---:|---:|---:|---:|
| Aug–Nov 2026 | 23% | −$372 | +$1,120 | −$3,618 | 15% |
| May–Aug 2026 | 42% | −$94.06 | +$1,473 | −$3,862 | 2% |
| Feb–May 2026 | 24% | −$567 | +$796 | −$3,834 | 6% |

432 combinations of OPEN timeframes × FORCE-CLOSE timeframe × threshold convention. **25** made money in all 3 quarters without wiping a real $2,000 account; 82 wipe it out in at least one quarter. ("Wiped" replays each setting's baskets on a $2,000 account with the bot's own lot sizing: the unit steps up above $2,500, so later losses are larger than at the fixed unit shown in the net columns.)

**How much of one cell is luck.** The live setting itself, at the same fixed 0.01-lot unit, run eight times per quarter on raw ticks with nothing changed but the loop timing: Aug–Nov 2025 −$1,822 to −$1,007; Nov 2025–Feb 2026 −$1,535 to −$1,227; Feb–May 2026 −$403 to −$250; May–Aug 2026 −$329 to +$379; Aug–Nov 2026 +$171 to +$356. The spread inside one quarter was $309 at the median and $815 at most. Differences of that size between two settings in the tables below are not evidence; only patterns that repeat across quarters are.

Does choosing on one window work on another?

| Chosen on → tested on | Rank correlation | Top 10% there | Same settings here | Best single setting there → here |
|---|---:|---:|---:|---:|
| Aug–Nov 2026 → May–Aug 2026 | +0.00 | +$566 | −$17.89 | +$1,120 → +$455 |
| Aug–Nov 2026 → Feb–May 2026 | +0.34 | +$566 | −$110 | +$1,120 → −$16.02 |
| May–Aug 2026 → Aug–Nov 2026 | +0.00 | +$966 | −$1,534 | +$1,473 → −$3,100 |
| May–Aug 2026 → Feb–May 2026 | +0.47 | +$966 | −$509 | +$1,473 → −$1,413 |
| Feb–May 2026 → Aug–Nov 2026 | +0.34 | +$610 | −$582 | +$796 → +$56.45 |
| Feb–May 2026 → May–Aug 2026 | +0.47 | +$610 | +$369 | +$796 → +$878 |

The live setting and the ten that held up best on these three quarters (sorted by quarters survived, quarters profitable, worst quarter). Net P/L of one fixed 0.01-lot unit; ✕ = the same baskets wipe a real $2,000 account in that quarter (the bot's own lot sizing applied). This ranking is hindsight; the hold-out section tests it.

|  | OPEN | FORCE-CLOSE | Entry needs | FC fires on | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Deepest dip of the $2,000 account | Baskets / quarter |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **live** | H1+M15 | M15 | one TF fully aligned | one indicator reversing | +$185 | −$159 | −$366 | $418 | 2,492 |
|  | H1+M30 | H4 | every TF fully aligned | both reversing | +$684 | +$736 | +$735 | $703 | 828 |
|  | H1+M30 | H4 | every TF fully aligned | one indicator reversing | +$526 | +$533 | +$735 | $804 | 829 |
|  | M30+M5 | H4 | every TF fully aligned | both reversing | +$869 | +$366 | +$490 | $911 | 769 |
|  | H4+H1 | H1 | every TF fully aligned | one indicator reversing | +$353 | +$531 | +$551 | $270 | 1,252 |
|  | H4 | H1 | one TF fully aligned | one indicator reversing | +$338 | +$536 | +$557 | $268 | 1,239 |
|  | H1 | H4 | one TF fully aligned | both reversing | +$245 | +$503 | +$786 | $823 | 1,194 |
|  | H4+M30 | H1 | every TF fully aligned | one indicator reversing | +$240 | +$488 | +$343 | $232 | 847 |
|  | H4+M30 | H1 | every TF fully aligned | both reversing | +$239 | +$605 | +$384 | $231 | 844 |
|  | H1+M30 | H4 | one TF fully aligned | both reversing | +$196 | +$817 | +$795 | $996 | 1,184 |
|  | M30+M5 | H4 | every TF fully aligned | one indicator reversing | +$869 | +$175 | +$381 | $911 | 769 |

Averaged over every combination that contains the timeframe:

| Timeframe | in OPEN: mean net / window | in OPEN: wiped $2,000 | as FORCE-CLOSE: mean net / window | as FORCE-CLOSE: wiped $2,000 |
|---|---:|---:|---:|---:|
| H4 | −$303 | 4% | +$97.01 | 4% |
| H1 | −$342 | 8% | −$441 | 18% |
| M30 | −$359 | 5% | −$355 | 6% |
| M15 | −$439 | 5% | −$181 | 0% |
| M5 | −$545 | 10% | −$715 | 5% |
| M1 | −$737 | 13% | −$1,229 | 14% |

**OPEN: RSI slope on one timeframe, MACD slope on another.** Three quarters added up, one fixed 0.01-lot unit; in brackets the number of quarters that were profitable; ✕ = wipes a real $2,000 account in one of them. On the diagonal both indicators read the same timeframe. Every cell needs both votes to agree: grey-fill (a grey vote borrowing the other's sign) only exists when both sit on one timeframe, so it is off throughout this grid to keep the cells comparable.

| RSI ↓ / MACD → | H4 | H1 | M30 | M15 | M5 | M1 |
|---|---:|---:|---:|---:|---:|---:|
| **H4** | −$178 (1/3) | +$134 (1/3) | +$460 (2/3) | −$429 (1/3) | −$1,192 (0/3) | −$490 (1/3) |
| **H1** | +$289 (3/3) | −$296 (1/3) | +$805 (3/3) | +$268 (2/3) | −$714 (1/3) | +$511 (3/3) |
| **M30** | +$543 (3/3) | +$44.75 (2/3) | +$541 (3/3) | −$3.04 (1/3) | −$464 (1/3) | +$429 (2/3) |
| **M15** | +$145 (2/3) | −$212 (1/3) | +$155 (2/3) | −$778 (1/3) | −$1,335 (0/3) | −$773 (0/3) |
| **M5** | +$256 (2/3) | −$573 (1/3) | +$234 (2/3) | −$662 (1/3) | −$1,824 (1/3) | −$744 (1/3) |
| **M1** | −$349 (0/3) | −$480 (1/3) | −$92.93 (2/3) | −$677 (1/3) | −$490 (1/3) | −$1,130 (1/3) |

**FORCE-CLOSE: RSI slope on one timeframe, MACD slope on another.** Three quarters added up, one fixed 0.01-lot unit; in brackets the number of quarters that were profitable; ✕ = wipes a real $2,000 account in one of them. On the diagonal both indicators read the same timeframe. Every cell needs both votes to agree: grey-fill (a grey vote borrowing the other's sign) only exists when both sit on one timeframe, so it is off throughout this grid to keep the cells comparable.

| RSI ↓ / MACD → | H4 | H1 | M30 | M15 | M5 | M1 |
|---|---:|---:|---:|---:|---:|---:|
| **H4** | +$771 (2/3) | −$1,325 ✕ (1/3) | +$453 (2/3) | −$134 (1/3) | −$724 (1/3) | −$811 (1/3) |
| **H1** | +$1,158 (2/3) | −$1,942 ✕ (1/3) | −$1,067 (0/3) | −$1,155 (0/3) | −$2,082 (0/3) | −$1,102 (1/3) |
| **M30** | −$544 (1/3) | −$2,164 ✕ (1/3) | −$417 (0/3) | −$66.06 (2/3) | −$849 (0/3) | −$341 (1/3) |
| **M15** | −$116 (2/3) | −$2,004 ✕ (1/3) | −$752 (1/3) | −$340 (1/3) | −$1,381 (0/3) | −$1,456 (0/3) |
| **M5** | +$220 (2/3) | −$2,508 ✕ (1/3) | −$783 (0/3) | −$541 (1/3) | −$1,532 (0/3) | −$1,809 (0/3) |
| **M1** | −$261 (2/3) | −$3,768 ✕ (1/3) | +$158 (2/3) | −$366 (1/3) | −$2,336 (0/3) | −$2,626 (0/3) |

## Does choosing timeframes on past data work? The hold-out test

Everything above was read off three quarters of 2026. A setting that looks good there was chosen with hindsight, so the same 432 settings were run on two earlier quarters (13 Aug 2025 → 13 Feb 2026) that were never used to choose anything. If picking by past performance worked, the settings that did best on the analysed quarters would do clearly better on the hold-out than the rest. The hold-out lies before the analysed quarters, so this tests whether a choice is stable across periods, not whether it forecasts; and one round trip did not cost the same in every quarter:

XAUUSDm: median spread Aug–Nov 2025 0.16 ($0.16 per 0.01 lot), Nov 2025–Feb 2026 0.16 ($0.16 per 0.01 lot), Feb–May 2026 0.28 ($0.28 per 0.01 lot), May–Aug 2026 0.26 ($0.26 per 0.01 lot), Aug–Nov 2026 0.24 ($0.24 per 0.01 lot).  
BTCUSDm: median spread Aug–Nov 2025 18.00 ($0.18 per 0.01 lot), Nov 2025–Feb 2026 18.00 ($0.18 per 0.01 lot), Feb–May 2026 14.00 ($0.14 per 0.01 lot), May–Aug 2026 10.00 ($0.10 per 0.01 lot), Aug–Nov 2026 10.00 ($0.10 per 0.01 lot).

### XAUUSDm

![XAUUSDm: analysed quarters against hold-out quarters](backtest_results/img/XAUUSDm_holdout.png)

| On the three analysed quarters the setting was | Settings | Profitable in both hold-out quarters | In at least one | Wiped $2,000 in the hold-out | Mean hold-out net per quarter | Median |
|---|---:|---:|---:|---:|---:|---:|
| 3 of 3 profitable, account never wiped | 12 | 0% | 25% | 75% | −$1,164 | −$974 |
| 3 of 3 profitable, but the account wiped in at least one | 17 | 18% | 76% | 82% | −$492 | −$644 |
| 2 of 3 profitable | 105 | 11% | 69% | 88% | −$1,024 | −$752 |
| 1 of 3 profitable | 120 | 5% | 57% | 88% | −$1,216 | −$1,018 |
| 0 of 3 profitable | 178 | 2% | 19% | 57% | −$1,471 | −$1,290 |

Across all 432 settings: 6% were profitable in both hold-out quarters, 75% would have wiped $2,000 in one of them, mean −$1,245 per quarter. Rank correlation between the three-quarter total and the hold-out total: +0.30.

The eight settings one would have picked from the analysed quarters (quarters survived, quarters profitable, worst quarter), and what they then did on the hold-out (one fixed 0.01-lot unit; ✕ = wipes a real $2,000 account in that quarter):

| OPEN | FORCE-CLOSE | Entry / FC | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Nov 2025–Feb 2026 (hold-out) | Aug–Nov 2025 (hold-out) |
|---|---:|---:|---:|---:|---:|---:|---:|
| H4+M5 | H1 | loose / half | +$598 | +$504 | +$1,702 | +$1,441 | −$252 |
| H4+M15 | M15 | strict / full | +$385 | +$423 | +$571 | −$10.92 | −$1,627 ✕ |
| H4 | M15 | loose / full | +$353 | +$396 | +$397 | −$252 | −$1,608 ✕ |
| H4+M15 | M30 | loose / full | +$595 | +$1,401 | +$328 | −$5,062 ✕ | −$3,076 ✕ |
| H1+M1 | M15 | strict / full | +$765 | +$1,015 | +$296 | −$49.04 | −$1,077 |
| H1+M1 | M15 | strict / half | +$503 | +$432 | +$223 | −$220 | −$1,703 |
| H4+M5 | H1 | loose / full | +$948 | +$216 | +$1,716 | −$1,578 ✕ | +$130 |
| H4+M1 | M15 | strict / full | +$192 | +$400 | +$630 | −$2,526 ✕ | −$755 |

### BTCUSDm

![BTCUSDm: analysed quarters against hold-out quarters](backtest_results/img/BTCUSDm_holdout.png)

| On the three analysed quarters the setting was | Settings | Profitable in both hold-out quarters | In at least one | Wiped $2,000 in the hold-out | Mean hold-out net per quarter | Median |
|---|---:|---:|---:|---:|---:|---:|
| 3 of 3 profitable, account never wiped | 25 | 0% | 8% | 80% | −$1,423 | −$1,716 |
| 2 of 3 profitable | 79 | 0% | 27% | 82% | −$1,569 | −$1,605 |
| 1 of 3 profitable | 153 | 1% | 21% | 69% | −$1,689 | −$1,487 |
| 0 of 3 profitable | 175 | 0% | 10% | 66% | −$1,823 | −$1,667 |

Across all 432 settings: 0% were profitable in both hold-out quarters, 71% would have wiped $2,000 in one of them, mean −$1,706 per quarter. Rank correlation between the three-quarter total and the hold-out total: +0.37.

The eight settings one would have picked from the analysed quarters (quarters survived, quarters profitable, worst quarter), and what they then did on the hold-out (one fixed 0.01-lot unit; ✕ = wipes a real $2,000 account in that quarter):

| OPEN | FORCE-CLOSE | Entry / FC | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Nov 2025–Feb 2026 (hold-out) | Aug–Nov 2025 (hold-out) |
|---|---:|---:|---:|---:|---:|---:|---:|
| H1+M30 | H4 | strict / full | +$684 | +$736 | +$735 | −$520 | −$1,484 ✕ |
| H1+M30 | H4 | strict / half | +$526 | +$533 | +$735 | −$520 | −$3,821 ✕ |
| M30+M5 | H4 | strict / full | +$869 | +$366 | +$490 | −$531 | −$730 ✕ |
| H4+H1 | H1 | strict / half | +$353 | +$531 | +$551 | −$136 | −$3,296 ✕ |
| H4 | H1 | loose / half | +$338 | +$536 | +$557 | −$261 | −$3,379 ✕ |
| H1 | H4 | loose / full | +$245 | +$503 | +$786 | −$2,403 ✕ | −$1,157 ✕ |
| H4+M30 | H1 | strict / half | +$240 | +$488 | +$343 | −$374 | −$3,657 ✕ |
| H4+M30 | H1 | strict / full | +$239 | +$605 | +$384 | −$250 | −$3,634 ✕ |

## Candidate settings

Five hand-picked timeframe families, the same for both symbols, each with the live ladder, without a ladder, and with a short spaced ladder. Four of them (A to D) put H4 into the decision in different ways; E keeps the live H1 + M15 timeframes and requires both to be fully aligned. A and C enter on the same rule (H4 and M15 both fully aligned) and differ only in when a ladder add is blocked, so their no-ladder rows are identical. They were chosen by eye from an earlier sweep of the three 2026 quarters: they are not the best of the sweep on either symbol, those quarters flatter them, and the two hold-out columns are the only independent evidence.

### XAUUSDm

Because one run is one path, every setting was run eight times per quarter on raw ticks (eight random loop timings, as above), each on a fresh $2,000 with the unit auto-step: 40 quarter-runs per setting. Cells show the median of the eight; ✕ = one or more of the eight ended in a stop-out.

![XAUUSDm: candidate settings on five quarters](backtest_results/img/XAUUSDm_candidates.png)

| Setting | Aug–Nov 2025 (hold-out) | Nov 2025–Feb 2026 (hold-out) | Feb–May 2026 | May–Aug 2026 | Aug–Nov 2026 | Quarter-runs that lost | Stopped out | Median quarter-run | Mean | Worst quarter-run | Worst basket | Baskets / quarter | One run of all 15 months on $2,000 | That run stopped out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **live timeframes · live ladder** | −$2,000 ✕ | −$1,277 ✕ | −$2,000 ✕ | −$2,000 ✕ | −$351 ✕ | 37 of 40 | 27 of 40 | −$2,000 | −$1,480 | −$2,000 | −$1,944 | 2,427 | −$2,000 | **yes** |
| live timeframes · no ladder | −$389 | −$858 | −$669 | −$1,173 | −$432 | 40 of 40 | 0 of 40 | −$610 | −$701 | −$1,357 | −$217 | 2,499 | −$2,000 | **yes** |
| live timeframes · 2 adds, >= $3 apart | −$590 | −$298 | −$549 | −$2,000 ✕ | −$263 | 37 of 40 | 5 of 40 | −$499 | −$678 | −$2,000 | −$875 | 3,470 | −$2,000 | **yes** |
| A: H4 must agree - open H4+M15 (both aligned), close on M15 · live ladder | −$2,000 ✕ | −$340 | +$404 ✕ | −$1,711 ✕ | +$364 | 27 of 40 | 9 of 40 | −$396 | −$601 | −$2,000 | −$2,138 | 1,946 | −$2,000 | **yes** |
| A: H4 must agree - open H4+M15 (both aligned), close on M15 · no ladder | −$413 | −$0.60 | −$258 | −$338 | +$80.36 | 30 of 40 | 0 of 40 | −$202 | −$185 | −$494 | −$156 | 1,507 | −$712 | no |
| A: H4 must agree - open H4+M15 (both aligned), close on M15 · 2 adds, >= $3 apart | −$518 | −$120 | −$236 | −$712 | +$357 | 28 of 40 | 0 of 40 | −$357 | −$244 | −$886 | −$800 | 1,975 | −$761 | no |
| B: H4 gate - open M5+M15, H4 must agree, close when H4 turns · live ladder | −$2,000 ✕ | −$2,000 ✕ | −$2,000 ✕ | −$2,000 ✕ | +$436 | 29 of 40 | 29 of 40 | −$2,000 | −$926 | −$2,000 | −$6,018 | 1,291 | −$2,000 | **yes** |
| B: H4 gate - open M5+M15, H4 must agree, close when H4 turns · no ladder | −$645 | +$70.23 | −$314 | +$61.05 | +$159 | 18 of 40 | 0 of 40 | +$14.84 | −$137 | −$733 | −$682 | 823 | −$372 | no |
| B: H4 gate - open M5+M15, H4 must agree, close when H4 turns · 2 adds, >= $3 apart | −$67.53 | −$980 ✕ | −$2,000 ✕ | −$698 ✕ | +$416 | 27 of 40 | 13 of 40 | −$584 | −$653 | −$2,000 | −$2,387 | 1,337 | −$2,000 | **yes** |
| C: open on H4 alone, close on M15 · live ladder | −$2,000 ✕ | −$255 | −$35.16 ✕ | −$1,493 ✕ | +$381 | 30 of 40 | 12 of 40 | −$736 | −$807 | −$2,000 | −$2,133 | 1,889 | −$2,000 | **yes** |
| C: open on H4 alone, close on M15 · no ladder | −$413 | −$0.60 | −$258 | −$338 | +$80.36 | 30 of 40 | 0 of 40 | −$202 | −$185 | −$494 | −$156 | 1,507 | −$712 | no |
| C: open on H4 alone, close on M15 · 2 adds, >= $3 apart | −$426 | +$110 | −$234 | −$683 | +$257 | 26 of 40 | 0 of 40 | −$260 | −$198 | −$844 | −$916 | 1,976 | −$819 | no |
| D: slow - open H1+H4 (both aligned), close on H1 · live ladder | −$2,000 ✕ | +$1,856 | −$2,000 ✕ | −$668 | +$0.69 | 28 of 40 | 16 of 40 | −$668 | −$559 | −$2,000 | −$2,237 | 1,516 | −$2,000 | **yes** |
| D: slow - open H1+H4 (both aligned), close on H1 · no ladder | −$496 | −$382 | −$79.60 | +$38.60 | +$165 | 25 of 40 | 0 of 40 | −$100 | −$154 | −$568 | −$257 | 1,178 | −$1,151 | no |
| D: slow - open H1+H4 (both aligned), close on H1 · 2 adds, >= $3 apart | −$2,000 ✕ | +$581 | −$879 ✕ | +$496 | +$389 | 19 of 40 | 11 of 40 | +$11.50 | −$332 | −$2,000 | −$1,777 | 1,881 | −$2,000 | **yes** |
| E: live timeframes, H1 must fully agree · live ladder | −$1,210 ✕ | +$32.40 | +$371 | −$2,000 ✕ | +$49.48 | 27 of 40 | 9 of 40 | −$302 | −$498 | −$2,000 | −$1,830 | 2,321 | −$2,000 | **yes** |
| E: live timeframes, H1 must fully agree · no ladder | −$135 | −$795 | −$385 | −$1,007 | −$273 | 40 of 40 | 0 of 40 | −$389 | −$514 | −$1,134 | −$217 | 2,007 | −$1,999 | no |
| E: live timeframes, H1 must fully agree · 2 adds, >= $3 apart | −$430 | −$692 | +$177 | −$2,000 ✕ | −$198 | 31 of 40 | 6 of 40 | −$480 | −$629 | −$2,000 | −$916 | 2,488 | −$2,000 | **yes** |
| live timeframes · no ladder, 1 h cooldown | −$173 | −$151 | −$103 | −$192 | +$59.40 | 32 of 40 | 0 of 40 | −$151 | −$116 | −$319 | −$90.04 | 705 | −$574 | no |
| live timeframes · closed-bar signals, no ladder | −$394 | −$717 | −$258 | −$887 | −$258 | 39 of 40 | 0 of 40 | −$420 | −$507 | −$1,065 | −$222 | 1,977 | −$2,000 | **yes** |

### BTCUSDm

Because one run is one path, every setting was run eight times per quarter on raw ticks (eight random loop timings, as above), each on a fresh $2,000 with the unit auto-step: 40 quarter-runs per setting. Cells show the median of the eight; ✕ = one or more of the eight ended in a stop-out.

![BTCUSDm: candidate settings on five quarters](backtest_results/img/BTCUSDm_candidates.png)

| Setting | Aug–Nov 2025 (hold-out) | Nov 2025–Feb 2026 (hold-out) | Feb–May 2026 | May–Aug 2026 | Aug–Nov 2026 | Quarter-runs that lost | Stopped out | Median quarter-run | Mean | Worst quarter-run | Worst basket | Baskets / quarter | One run of all 15 months on $2,000 | That run stopped out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **live timeframes · live ladder** | −$1,369 | −$1,407 | −$286 | −$190 | +$282 | 30 of 40 | 0 of 40 | −$312 | −$585 | −$1,822 | −$811 | 2,615 | −$2,000 | **yes** |
| live timeframes · no ladder | −$272 | −$377 | −$208 | −$8.35 | −$54.45 | 39 of 40 | 0 of 40 | −$208 | −$184 | −$414 | −$49.96 | 1,787 | −$921 | no |
| live timeframes · 2 adds, >= $300 apart | −$704 | −$828 | −$272 | −$221 | +$148 | 32 of 40 | 0 of 40 | −$276 | −$380 | −$908 | −$186 | 2,197 | −$1,844 | no |
| A: H4 must agree - open H4+M15 (both aligned), close on M15 · live ladder | −$682 | −$239 | −$137 | −$564 | +$83.19 | 32 of 40 | 0 of 40 | −$239 | −$308 | −$744 | −$487 | 1,486 | −$1,545 | no |
| A: H4 must agree - open H4+M15 (both aligned), close on M15 · no ladder | −$174 | −$148 | −$82.27 | −$22.98 | −$4.20 | 37 of 40 | 0 of 40 | −$82.27 | −$88.23 | −$177 | −$42.51 | 1,089 | −$469 | no |
| A: H4 must agree - open H4+M15 (both aligned), close on M15 · 2 adds, >= $300 apart | −$297 | −$456 | −$147 | −$197 | −$89.48 | 40 of 40 | 0 of 40 | −$197 | −$235 | −$519 | −$130 | 1,278 | −$1,024 | no |
| B: H4 gate - open M5+M15, H4 must agree, close when H4 turns · live ladder | −$2,000 ✕ | −$2,000 ✕ | −$54.80 | +$823 | +$437 | 24 of 40 | 16 of 40 | −$54.80 | −$556 | −$2,000 | −$1,746 | 1,067 | −$2,000 | **yes** |
| B: H4 gate - open M5+M15, H4 must agree, close when H4 turns · no ladder | −$233 | −$171 | +$127 | −$104 | +$93.83 | 23 of 40 | 0 of 40 | −$104 | −$57.63 | −$279 | −$118 | 475 | −$305 | no |
| B: H4 gate - open M5+M15, H4 must agree, close when H4 turns · 2 adds, >= $300 apart | −$802 | −$600 | +$244 | +$221 | −$90.52 | 24 of 40 | 0 of 40 | −$90.52 | −$209 | −$1,026 | −$650 | 898 | −$1,321 | no |
| C: open on H4 alone, close on M15 · live ladder | −$717 | −$273 | −$204 | −$148 | −$51.82 | 38 of 40 | 0 of 40 | −$203 | −$282 | −$780 | −$411 | 1,478 | −$1,348 | no |
| C: open on H4 alone, close on M15 · no ladder | −$174 | −$148 | −$82.27 | −$22.98 | −$4.20 | 37 of 40 | 0 of 40 | −$82.27 | −$88.23 | −$177 | −$42.51 | 1,089 | −$469 | no |
| C: open on H4 alone, close on M15 · 2 adds, >= $300 apart | −$227 | −$423 | −$62.88 | −$219 | −$74.59 | 40 of 40 | 0 of 40 | −$185 | −$199 | −$456 | −$130 | 1,273 | −$926 | no |
| D: slow - open H1+H4 (both aligned), close on H1 · live ladder | −$2,000 ✕ | −$156 | +$659 | +$601 | +$196 | 16 of 40 | 8 of 40 | +$196 | −$139 | −$2,000 | −$946 | 1,189 | −$2,000 | **yes** |
| D: slow - open H1+H4 (both aligned), close on H1 · no ladder | −$156 | −$246 | +$35.47 | +$4.88 | +$25.15 | 18 of 40 | 0 of 40 | +$4.88 | −$66.56 | −$270 | −$62.15 | 651 | −$367 | no |
| D: slow - open H1+H4 (both aligned), close on H1 · 2 adds, >= $300 apart | −$500 | −$213 | +$139 | +$192 | +$21.41 | 17 of 40 | 0 of 40 | +$21.41 | −$77.22 | −$641 | −$308 | 1,029 | −$245 | no |
| E: live timeframes, H1 must fully agree · live ladder | −$809 | −$1,366 | −$3.09 | +$302 | −$101 | 28 of 40 | 0 of 40 | −$101 | −$396 | −$1,761 | −$807 | 2,033 | −$2,000 | **yes** |
| E: live timeframes, H1 must fully agree · no ladder | −$247 | −$360 | −$187 | −$15.07 | −$54.95 | 39 of 40 | 0 of 40 | −$187 | −$171 | −$384 | −$47.79 | 1,455 | −$827 | no |
| E: live timeframes, H1 must fully agree · 2 adds, >= $300 apart | −$480 | −$839 | −$225 | −$139 | +$14.52 | 33 of 40 | 0 of 40 | −$225 | −$335 | −$937 | −$187 | 1,755 | −$1,640 | no |
| live timeframes · no ladder, 1 h cooldown | −$267 | −$116 | −$128 | −$118 | +$70.27 | 32 of 40 | 0 of 40 | −$120 | −$112 | −$307 | −$38.26 | 778 | −$471 | no |
| live timeframes · closed-bar signals, no ladder | −$45.14 | −$186 | −$188 | +$48.38 | −$16.65 | 32 of 40 | 0 of 40 | −$45.14 | −$76.13 | −$207 | −$47.16 | 1,297 | −$442 | no |

## What-ifs aimed at the flaws

Each row changes the rules in one deliberate way that answers a weakness found above. None was tuned on the data. One fixed 0.01-lot unit per quarter. "Wiped $2,000 in" counts the quarters in which the same baskets wipe a real $2,000 account (the bot's own lot sizing applied); sorted by that count, then by the three-quarter total.

### XAUUSDm

![XAUUSDm: what-ifs](backtest_results/img/XAUUSDm_whatifs.png)

| What-if | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters | Profitable quarters | Deepest dip of the $2,000 account | Wiped $2,000 in | Worst basket |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **live settings** | +$296 | −$2,356 | −$2,299 | −$4,359 | 1/3 | $2,000 | 2/3 | −$1,687 |
| no ladder, slope book instead of target | +$29.03 | −$888 | −$26.87 | −$886 | 1/3 | $931 | 0/3 | −$212 |
| no ladder, target $3, stop $10 | −$151 | −$852 | −$455 | −$1,459 | 0/3 | $872 | 0/3 | −$56.66 |
| closed bars + no ladder | −$167 | −$881 | −$492 | −$1,540 | 0/3 | $954 | 0/3 | −$127 |
| no ladder, target $2 | −$291 | −$1,104 | −$451 | −$1,847 | 0/3 | $1,163 | 0/3 | −$217 |
| no ladder, target $5, stop $10 | −$144 | −$1,237 | −$678 | −$2,059 | 0/3 | $1,271 | 0/3 | −$55.86 |
| no ladder | −$364 | −$1,152 | −$805 | −$2,321 | 0/3 | $1,199 | 0/3 | −$217 |
| closed bars + no ladder + stop $10 | −$327 | −$1,065 | −$950 | −$2,343 | 0/3 | $1,074 | 0/3 | −$57.50 |
| flat lots, >= $3 apart + stop $20 | −$249 | −$1,101 | −$1,069 | −$2,419 | 0/3 | $1,154 | 0/3 | −$36.57 |
| adds >= $5 apart + stop $80 | −$331 | −$1,484 | −$722 | −$2,537 | 0/3 | $1,697 | 0/3 | −$181 |
| no ladder + stop $20 | −$291 | −$1,227 | −$1,128 | −$2,645 | 0/3 | $1,259 | 0/3 | −$65.60 |
| no ladder + stop $10 | −$512 | −$1,091 | −$1,204 | −$2,807 | 0/3 | $1,232 | 0/3 | −$57.50 |
| 2 adds >= $3 apart + stop $20 | −$228 | −$1,539 | −$1,088 | −$2,855 | 0/3 | $1,579 | 0/3 | −$165 |
| target per lot + adds >= $3 apart + stop $40 | −$89.57 | −$1,319 | −$1,540 | −$2,949 | 0/3 | $1,564 | 0/3 | −$181 |
| adds >= $3 apart + stop $40 | −$385 | −$1,326 | −$1,280 | −$2,990 | 0/3 | $1,391 | 0/3 | −$181 |
| ladder: 1 add only | −$482 | −$1,840 | −$1,210 | −$3,532 | 0/3 | $1,905 | 0/3 | −$594 |
| no ladder + stop $5 | −$759 | −$1,292 | −$1,753 | −$3,804 | 0/3 | $1,771 | 0/3 | −$54.39 |
| stop: $10 per unit | −$1,543 | −$1,963 | −$1,947 | −$5,452 | 0/3 | $1,977 | 0/3 | −$34.62 |
| force-close needs 60 s confirmation | +$677 | −$2,635 | +$51.87 | −$1,906 | 2/3 | $2,000 | 1/3 | −$1,732 |
| ladder: adds >= $3 apart | +$897 | −$3,082 | −$516 | −$2,701 | 1/3 | $2,000 | 1/3 | −$1,243 |
| cooldown 30 min | −$445 | −$2,317 | −$166 | −$2,928 | 0/3 | $2,000 | 1/3 | −$1,687 |
| ladder: adds >= $5 apart | +$708 | −$3,062 | −$649 | −$3,003 | 1/3 | $2,000 | 1/3 | −$1,056 |
| time stop: 1 h | −$280 | −$1,926 | −$1,267 | −$3,474 | 0/3 | $2,000 | 1/3 | −$570 |
| ladder: flat lots, adds >= $3 apart | −$22.74 | −$2,023 | −$1,474 | −$3,520 | 0/3 | $2,000 | 1/3 | −$414 |
| target per lot + adds >= $3 apart | +$275 | −$3,437 | −$387 | −$3,548 | 1/3 | $2,000 | 1/3 | −$1,243 |
| ladder: 2 adds only | −$195 | −$2,422 | −$1,136 | −$3,753 | 0/3 | $2,000 | 1/3 | −$456 |
| ladder: adds >= 15 min apart | +$306 | −$3,227 | −$1,458 | −$4,378 | 1/3 | $2,000 | 1/3 | −$934 |
| ladder: flat lots 1,1,1,1,1,1 | −$112 | −$2,920 | −$1,460 | −$4,491 | 0/3 | $2,000 | 1/3 | −$430 |
| stop: $20 per unit | −$1,254 | −$2,056 | −$1,797 | −$5,107 | 0/3 | $2,000 | 1/3 | −$166 |
| signals on closed bars | +$427 | −$6,187 | −$1,069 | −$6,829 | 1/3 | $2,000 | 1/3 | −$2,545 |
| target: $1 per 0.01 lot held | +$590 | −$2,182 | −$1,299 | −$2,891 | 1/3 | $2,000 | 2/3 | −$1,687 |
| time stop: 4 h | +$194 | −$2,055 | −$2,600 | −$4,461 | 1/3 | $2,000 | 2/3 | −$1,432 |
| ladder: adds >= $3 apart and >= 5 min apart | +$516 | −$4,436 | −$1,971 | −$5,891 | 1/3 | $2,000 | 2/3 | −$1,702 |
| stop: $80 per unit | −$951 | −$2,906 | −$2,376 | −$6,233 | 0/3 | $2,000 | 2/3 | −$181 |
| stop: $40 per unit | −$1,490 | −$2,725 | −$2,031 | −$6,246 | 0/3 | $2,000 | 2/3 | −$181 |

### BTCUSDm

![BTCUSDm: what-ifs](backtest_results/img/BTCUSDm_whatifs.png)

| What-if | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters | Profitable quarters | Deepest dip of the $2,000 account | Wiped $2,000 in | Worst basket |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **live settings** | +$185 | −$159 | −$366 | −$340 | 1/3 | $418 | 0/3 | −$484 |
| target per lot + adds >= $300 apart | +$166 | −$165 | +$114 | +$115 | 2/3 | $301 | 0/3 | −$175 |
| no ladder, target $5, stop $10 | +$75.67 | +$39.28 | −$115 | −$0.45 | 2/3 | $118 | 0/3 | −$11.42 |
| no ladder, target $3, stop $10 | +$114 | +$25.73 | −$148 | −$8.85 | 2/3 | $151 | 0/3 | −$12.69 |
| target: $1 per 0.01 lot held | +$414 | −$454 | +$23.15 | −$16.99 | 2/3 | $837 | 0/3 | −$579 |
| no ladder, slope book instead of target | +$43.87 | −$1.25 | −$104 | −$61.85 | 1/3 | $111 | 0/3 | −$21.07 |
| no ladder, target $2 | +$71.95 | +$18.21 | −$161 | −$70.87 | 2/3 | $164 | 0/3 | −$26.19 |
| ladder: adds >= $500 apart | +$129 | −$163 | −$99.47 | −$133 | 1/3 | $232 | 0/3 | −$126 |
| target per lot + adds >= $300 apart + stop $40 | +$141 | −$170 | −$105 | −$134 | 1/3 | $269 | 0/3 | −$50.85 |
| closed bars + no ladder + stop $10 | −$38.27 | +$41.14 | −$139 | −$136 | 1/3 | $151 | 0/3 | −$12.69 |
| ladder: adds >= $300 apart | +$95.72 | −$161 | −$81.76 | −$147 | 1/3 | $196 | 0/3 | −$84.46 |
| ladder: adds >= $300 apart and >= 5 min apart | +$133 | −$141 | −$158 | −$166 | 1/3 | $218 | 0/3 | −$84.46 |
| time stop: 4 h | +$52.87 | +$143 | −$374 | −$178 | 2/3 | $426 | 0/3 | −$224 |
| closed bars + no ladder | −$44.89 | +$43.78 | −$182 | −$184 | 1/3 | $193 | 0/3 | −$27.58 |
| adds >= $500 apart + stop $80 | +$47.94 | −$117 | −$127 | −$196 | 1/3 | $186 | 0/3 | −$85.74 |
| flat lots, >= $300 apart + stop $20 | −$32.53 | −$82.46 | −$125 | −$240 | 0/3 | $158 | 0/3 | −$24.20 |
| no ladder + stop $20 | −$53.30 | −$6.15 | −$185 | −$244 | 0/3 | $187 | 0/3 | −$20.53 |
| no ladder | −$51.44 | −$6.27 | −$191 | −$248 | 0/3 | $193 | 0/3 | −$26.10 |
| no ladder + stop $10 | −$42.72 | −$41.46 | −$212 | −$296 | 0/3 | $214 | 0/3 | −$13.11 |
| ladder: flat lots, adds >= $300 apart | +$14.14 | −$153 | −$168 | −$307 | 1/3 | $223 | 0/3 | −$110 |
| no ladder + stop $5 | −$101 | −$32.27 | −$216 | −$349 | 0/3 | $218 | 0/3 | −$6.98 |
| adds >= $300 apart + stop $40 | +$99.18 | −$208 | −$276 | −$385 | 1/3 | $290 | 0/3 | −$49.05 |
| ladder: flat lots 1,1,1,1,1,1 | +$61.96 | −$258 | −$248 | −$443 | 1/3 | $346 | 0/3 | −$124 |
| 2 adds >= $300 apart + stop $20 | −$16.33 | −$147 | −$323 | −$487 | 0/3 | $325 | 0/3 | −$26.97 |
| time stop: 1 h | −$101 | −$22.03 | −$473 | −$596 | 0/3 | $484 | 0/3 | −$306 |
| ladder: 1 add only | −$116 | −$213 | −$327 | −$656 | 0/3 | $328 | 0/3 | −$74.26 |
| ladder: adds >= 15 min apart | +$31.54 | −$618 | −$129 | −$715 | 1/3 | $667 | 0/3 | −$155 |
| force-close needs 60 s confirmation | +$138 | −$53.19 | −$904 | −$819 | 1/3 | $971 | 0/3 | −$436 |
| stop: $80 per unit | −$134 | −$133 | −$617 | −$884 | 0/3 | $669 | 0/3 | −$95.23 |
| ladder: 2 adds only | −$18.45 | −$410 | −$473 | −$901 | 0/3 | $507 | 0/3 | −$136 |
| signals on closed bars | +$101 | −$240 | −$765 | −$904 | 1/3 | $819 | 0/3 | −$377 |
| cooldown 30 min | −$134 | −$369 | −$463 | −$966 | 0/3 | $528 | 0/3 | −$484 |
| stop: $40 per unit | −$392 | −$414 | −$695 | −$1,501 | 0/3 | $716 | 0/3 | −$79.92 |
| stop: $20 per unit | −$353 | −$783 | −$938 | −$2,074 | 0/3 | $940 | 0/3 | −$45.05 |
| stop: $10 per unit | −$517 | −$739 | −$1,160 | −$2,415 | 0/3 | $1,162 | 0/3 | −$28.94 |

## Every other parameter, one at a time

One parameter changed, everything else at the live value. Net P/L of one fixed 0.01-lot unit per quarter; ✕ = the same baskets wipe a real $2,000 account in that quarter (the bot's own lot sizing applied). Charts of the same numbers are on the results page.

<details><summary><b>XAUUSDm</b> — all parameter tables</summary>

| entry s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 2 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 4 | +$54.29 | −$1,727 ✕ | +$624 | −$1,049 |

| entry agree s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | −$119 | −$3,083 ✕ | −$3,422 ✕ | −$6,624 |
| 1 | +$358 | −$2,992 ✕ | −$2,737 ✕ | −$5,371 |
| 2 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |

| force close s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 1 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 2 | +$1,000 | −$5,154 ✕ | −$1,921 ✕ | −$6,074 |

| ladder s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 2 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 4 | +$428 | −$2,591 ✕ | −$916 | −$3,078 |

| rsi oversold | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 20 | +$404 | −$1,462 ✕ | −$2,493 ✕ | −$3,551 |
| 25 | +$782 | −$1,441 ✕ | −$2,859 ✕ | −$3,517 |
| 30 | +$606 | −$1,759 ✕ | −$2,013 ✕ | −$3,167 |
| 35 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 40 | +$433 | −$5,395 ✕ | −$4,594 ✕ | −$9,556 |

| rsi overbought | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 60 | +$1,544 | −$1,724 ✕ | +$87.44 ✕ | −$92.46 |
| 65 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 70 | +$80.05 | −$2,891 ✕ | −$797 ✕ | −$3,608 |
| 75 | +$45.47 | −$2,084 ✕ | −$801 ✕ | −$2,839 |
| 80 | −$222 | −$2,121 ✕ | −$480 ✕ | −$2,824 |

| rsi length | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 7 | +$511 | −$1,733 ✕ | −$2,493 ✕ | −$3,716 |
| 9 | −$2,250 ✕ | −$1,857 ✕ | −$1,590 ✕ | −$5,697 |
| 14 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 21 | +$1,351 | −$2,445 ✕ | −$1,404 | −$2,499 |
| 28 | +$677 | −$1,970 ✕ | −$597 | −$1,891 |

| peak lookback | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 8 | +$49.71 | −$1,006 | +$171 | −$786 |
| 12 | +$243 | −$1,294 ✕ | +$722 | −$329 |
| 20 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 30 | +$60.39 | −$2,685 ✕ | −$3,717 ✕ | −$6,342 |
| 50 | +$609 | −$2,913 ✕ | −$2,514 ✕ | −$4,818 |

| pivot width | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 1 | −$171 | −$2,402 ✕ | −$8,304 ✕ | −$10,878 |
| 2 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 3 | −$202 | −$1,833 ✕ | +$898 | −$1,137 |
| 4 | +$440 | −$2,868 ✕ | −$1,961 ✕ | −$4,389 |

| rsi peak ob | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 55 | −$375 | −$2,682 ✕ | −$2,748 ✕ | −$5,804 |
| 60 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 65 | +$780 | −$3,973 ✕ | −$2,104 ✕ | −$5,297 |
| 70 | +$569 | −$2,459 ✕ | −$822 | −$2,712 |

| rsi peak os | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 30 | +$343 | −$2,039 ✕ | −$1,777 ✕ | −$3,472 |
| 35 | +$594 | −$2,451 ✕ | −$2,550 ✕ | −$4,407 |
| 40 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 45 | −$207 | −$2,463 ✕ | −$4,299 ✕ | −$6,969 |

| reentry cooldown s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | −$581 | −$5,695 ✕ | −$3,520 ✕ | −$9,796 |
| 60 | −$530 | −$4,232 ✕ | −$2,867 ✕ | −$7,630 |
| 300 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 900 | −$250 | −$2,952 ✕ | −$1,075 | −$4,277 |
| 1800 | −$445 | −$2,317 ✕ | −$166 | −$2,928 |
| 3600 | −$282 | +$355 | −$178 | −$105 |

| max adds | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | −$364 | −$1,152 | −$805 | −$2,321 |
| 1 | −$482 | −$1,840 | −$1,210 | −$3,532 |
| 2 | −$195 | −$2,422 ✕ | −$1,136 | −$3,753 |
| 3 | −$176 | −$2,517 ✕ | −$1,676 | −$4,368 |
| 4 | +$356 | −$3,308 ✕ | −$2,028 ✕ | −$4,980 |
| 5 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |

| macd | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 5,13,4 | +$337 | −$4,744 ✕ | −$1,295 ✕ | −$5,701 |
| 8,17,9 | −$360 | −$2,152 ✕ | +$443 | −$2,070 |
| 12,26,9 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 19,39,9 | −$672 | −$3,346 ✕ | −$907 ✕ | −$4,924 |
| 24,52,18 | −$269 | −$3,448 ✕ | +$2,457 | −$1,260 |

| rsi bands | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 20/80 | −$114 | −$1,158 | −$667 | −$1,939 |
| 25/75 | +$532 | −$1,100 | −$1,353 | −$1,921 |
| 30/70 | +$390 | −$2,284 ✕ | −$525 | −$2,418 |
| 35/65 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 40/60 | +$1,729 | −$4,724 ✕ | −$2,222 ✕ | −$5,217 |

| ladder shape | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| fibonacci 1,2,3,5,8,13 (live) | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| flat 1,1,1,1,1,1 | −$112 | −$2,920 ✕ | −$1,460 | −$4,491 |
| linear 1,2,3,4,5,6 | −$180 | −$2,453 ✕ | −$1,812 | −$4,445 |
| double 1,2,4,8,16,32 | +$770 | −$775 ✕ | −$5,869 ✕ | −$5,874 |

| ladder timeframes | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| M1,M5,M15,H1,H4 (live) | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| M5,M15,H1,H4,H4 | −$1,069 | −$2,092 ✕ | −$207 | −$3,367 |
| M15,H1,H4,H4,H4 | +$40.02 | −$5,763 ✕ | −$8,558 ✕ | −$14,281 |
| H4,H1,M15,M5,M1 | +$16.39 | −$2,827 ✕ | −$7,775 ✕ | −$10,586 |
| all five on M1 | −$6,307 ✕ | −$5,042 ✕ | −$3,047 ✕ | −$14,396 |
| all five on M5 | −$728 | −$7,967 ✕ | −$3,022 ✕ | −$11,717 |
| all five on M15 | −$1,134 ✕ | −$10,446 ✕ | −$7,568 ✕ | −$19,148 |
| all five on H1 | −$5,549 ✕ | −$9,441 ✕ | −$15,850 ✕ | −$30,840 |

| ladder min gap | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| $0 in price | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| $1 in price | +$1,059 | −$870 | −$937 | −$748 |
| $2 in price | +$672 | −$2,471 ✕ | −$2,041 ✕ | −$3,840 |
| $3 in price | +$897 | −$3,082 ✕ | −$516 | −$2,701 |
| $5 in price | +$708 | −$3,062 ✕ | −$649 | −$3,003 |
| $8 in price | +$269 | −$2,024 ✕ | −$1,980 ✕ | −$3,736 |

| signals on | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| forming bar (live) | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| closed bars: slopes | −$415 | −$2,726 ✕ | +$381 | −$2,760 |
| closed bars: slopes + ladder RSI | +$427 | −$6,187 ✕ | −$1,069 | −$6,829 |

| ladder min interval | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 min | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 1 min | +$374 | −$2,260 ✕ | +$780 | −$1,106 |
| 5 min | +$528 | −$4,215 ✕ | −$3,183 ✕ | −$6,870 |
| 15 min | +$306 | −$3,227 ✕ | −$1,458 | −$4,378 |
| 30 min | +$328 | −$1,696 | −$1,920 ✕ | −$3,288 |
| 60 min | +$75.96 | −$2,027 ✕ | −$1,071 | −$3,022 |

| max hold | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| none (live) | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 0.25 h | −$1,717 | −$1,512 | −$1,115 | −$4,343 |
| 0.5 h | −$1,112 | −$1,516 | −$1,714 | −$4,342 |
| 1 h | −$280 | −$1,926 ✕ | −$1,267 | −$3,474 |
| 2 h | −$145 | −$2,495 ✕ | −$2,250 ✕ | −$4,891 |
| 4 h | +$194 | −$2,055 ✕ | −$2,600 ✕ | −$4,461 |
| 8 h | +$265 | −$2,356 ✕ | −$2,497 ✕ | −$4,587 |

| fc confirm s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 10 | +$343 | −$2,359 ✕ | −$2,357 ✕ | −$4,373 |
| 30 | +$648 | −$2,258 ✕ | −$434 | −$2,044 |
| 60 | +$677 | −$2,635 ✕ | +$51.87 | −$1,906 |
| 120 | +$729 | −$2,601 ✕ | −$464 ✕ | −$2,337 |
| 300 | +$930 | −$2,092 ✕ | +$314 | −$847 |

| entry confirm s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 10 | +$272 | −$2,598 ✕ | −$1,765 | −$4,091 |
| 30 | +$235 | −$2,029 ✕ | −$2,604 ✕ | −$4,398 |
| 60 | +$297 | −$2,052 ✕ | −$676 | −$2,430 |
| 120 | −$26.08 | −$653 | −$24.46 | −$703 |
| 300 | −$149 | −$1,050 ✕ | −$1,780 | −$2,979 |

| min hold s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 30 | +$321 | −$2,359 ✕ | −$2,302 ✕ | −$4,340 |
| 60 | +$296 | −$2,390 ✕ | −$2,271 ✕ | −$4,365 |
| 300 | +$231 | −$2,085 ✕ | −$2,259 ✕ | −$4,113 |
| 900 | +$621 | −$1,901 ✕ | −$2,432 ✕ | −$3,713 |

| stop loss | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| none (live) | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| $3 per unit | −$1,830 | −$2,071 ✕ | −$1,821 | −$5,723 |
| $5 per unit | −$1,637 | −$1,916 | −$2,281 ✕ | −$5,834 |
| $10 per unit | −$1,543 | −$1,963 | −$1,947 | −$5,452 |
| $20 per unit | −$1,254 | −$2,056 ✕ | −$1,797 | −$5,107 |
| $40 per unit | −$1,490 | −$2,725 ✕ | −$2,031 ✕ | −$6,246 |
| $80 per unit | −$951 | −$2,906 ✕ | −$2,376 ✕ | −$6,233 |

| side | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| both (live) | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| long only | −$419 | −$1,557 | −$301 ✕ | −$2,278 |
| short only | +$762 | −$844 | −$2,118 ✕ | −$2,200 |

| exit mix | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| force-close off | +$4,247 ✕ | −$6,744 ✕ | +$5,423 ✕ | +$2,926 |
| slope book only (netting exit) | +$1,939 ✕ | −$9,880 ✕ | −$3,168 ✕ | −$11,109 |

| target usd per unit | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0.5 | −$195 | −$4,270 ✕ | −$3,415 ✕ | −$7,879 |
| 1.0 | +$296 | −$2,356 ✕ | −$2,299 ✕ | −$4,359 |
| 1.5 | −$1,075 | −$2,752 ✕ | −$3,854 ✕ | −$7,680 |
| 2.0 | −$734 | −$3,303 ✕ | −$2,740 ✕ | −$6,777 |
| 3.0 | +$20.26 | −$3,388 ✕ | −$1,867 ✕ | −$5,235 |
| 5.0 | +$1,441 | −$3,135 ✕ | −$1,802 ✕ | −$3,496 |
| 10.0 | +$1,324 | −$2,802 ✕ | −$2,313 ✕ | −$3,791 |

</details>

<details><summary><b>BTCUSDm</b> — all parameter tables</summary>

| entry s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 2 | +$185 | −$159 | −$366 | −$340 |
| 4 | −$189 | +$334 | −$43.13 | +$103 |

| entry agree s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | −$112 | +$23.08 | −$689 | −$777 |
| 1 | −$12.33 | +$256 | −$561 | −$318 |
| 2 | +$185 | −$159 | −$366 | −$340 |

| force close s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 1 | +$185 | −$159 | −$366 | −$340 |
| 2 | −$13.68 | −$261 | −$55.85 | −$330 |

| ladder s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 2 | +$185 | −$159 | −$366 | −$340 |
| 4 | +$325 | +$5.72 | −$206 | +$124 |

| rsi oversold | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 20 | +$131 | −$64.41 | −$86.46 | −$20.34 |
| 25 | +$93.05 | −$104 | −$67.94 | −$78.39 |
| 30 | +$152 | −$377 | +$4.38 | −$221 |
| 35 | +$185 | −$159 | −$366 | −$340 |
| 40 | −$222 | −$1,371 | −$540 | −$2,132 |

| rsi overbought | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 60 | −$14.49 | −$508 | −$1,308 | −$1,831 |
| 65 | +$185 | −$159 | −$366 | −$340 |
| 70 | +$35.22 | −$155 | −$431 | −$551 |
| 75 | +$32.83 | −$122 | −$339 | −$428 |
| 80 | −$40.67 | −$146 | −$358 | −$545 |

| rsi length | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 7 | −$1,744 ✕ | −$1,590 | −$2,123 ✕ | −$5,457 |
| 9 | −$267 | −$1,680 | −$1,047 | −$2,995 |
| 14 | +$185 | −$159 | −$366 | −$340 |
| 21 | +$237 | +$94.55 | −$89.21 | +$242 |
| 28 | +$81.90 | −$47.06 | +$60.11 | +$94.95 |

| peak lookback | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 8 | −$1,377 | −$1.19 | +$54.85 | −$1,323 |
| 12 | −$27.55 | +$277 | −$10.27 | +$239 |
| 20 | +$185 | −$159 | −$366 | −$340 |
| 30 | −$117 | +$438 | −$558 | −$238 |
| 50 | −$109 | +$393 | −$680 | −$396 |

| pivot width | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 1 | +$64.02 | −$650 | −$432 | −$1,018 |
| 2 | +$185 | −$159 | −$366 | −$340 |
| 3 | −$625 | +$336 | −$211 | −$501 |
| 4 | −$780 | +$36.58 | −$489 | −$1,233 |

| rsi peak ob | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 55 | +$187 | −$221 | −$512 | −$546 |
| 60 | +$185 | −$159 | −$366 | −$340 |
| 65 | +$245 | +$152 | −$126 | +$270 |
| 70 | +$85.11 | +$90.41 | −$235 | −$59.17 |

| rsi peak os | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 30 | +$365 | −$106 | +$43.33 | +$301 |
| 35 | +$307 | −$139 | −$243 | −$74.89 |
| 40 | +$185 | −$159 | −$366 | −$340 |
| 45 | −$41.15 | −$176 | −$320 | −$538 |

| reentry cooldown s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$369 | −$914 | −$868 | −$1,412 |
| 60 | +$251 | −$565 | −$422 | −$736 |
| 300 | +$185 | −$159 | −$366 | −$340 |
| 900 | +$104 | −$316 | −$318 | −$530 |
| 1800 | −$134 | −$369 | −$463 | −$966 |
| 3600 | +$69.04 | −$102 | −$38.32 | −$71.21 |

| max adds | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | −$51.44 | −$6.27 | −$191 | −$248 |
| 1 | −$116 | −$213 | −$327 | −$656 |
| 2 | −$18.45 | −$410 | −$473 | −$901 |
| 3 | +$50.81 | −$275 | −$511 | −$735 |
| 4 | +$32.06 | −$355 | −$297 | −$620 |
| 5 | +$185 | −$159 | −$366 | −$340 |

| macd | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 5,13,4 | −$163 | −$399 | −$607 | −$1,170 |
| 8,17,9 | −$199 | +$409 | −$611 | −$402 |
| 12,26,9 | +$185 | −$159 | −$366 | −$340 |
| 19,39,9 | −$710 | +$48.81 | −$795 | −$1,456 |
| 24,52,18 | −$792 | +$92.89 | −$1,026 | −$1,726 |

| rsi bands | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 20/80 | −$100 | −$51.15 | −$78.04 | −$230 |
| 25/75 | −$59.61 | −$65.90 | −$40.63 | −$166 |
| 30/70 | +$1.56 | −$373 | −$60.65 | −$432 |
| 35/65 | +$185 | −$159 | −$366 | −$340 |
| 40/60 | −$402 | −$1,725 | −$1,488 | −$3,614 |

| ladder shape | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| fibonacci 1,2,3,5,8,13 (live) | +$185 | −$159 | −$366 | −$340 |
| flat 1,1,1,1,1,1 | +$61.96 | −$258 | −$248 | −$443 |
| linear 1,2,3,4,5,6 | +$7.09 | −$213 | −$139 | −$345 |
| double 1,2,4,8,16,32 | +$248 | +$389 | −$816 | −$178 |

| ladder timeframes | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| M1,M5,M15,H1,H4 (live) | +$185 | −$159 | −$366 | −$340 |
| M5,M15,H1,H4,H4 | −$82.19 | −$211 | −$520 | −$813 |
| M15,H1,H4,H4,H4 | −$125 | −$11.03 | −$181 | −$318 |
| H4,H1,M15,M5,M1 | −$31.33 | −$488 | −$461 | −$980 |
| all five on M1 | −$2,133 ✕ | −$2,163 ✕ | −$3,930 ✕ | −$8,226 |
| all five on M5 | −$284 | −$693 | −$903 | −$1,880 |
| all five on M15 | −$1,077 | −$1,093 | −$2,437 ✕ | −$4,608 |
| all five on H1 | −$1,146 | −$3,375 ✕ | −$3,160 ✕ | −$7,680 |

| ladder min gap | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| $0 in price | +$185 | −$159 | −$366 | −$340 |
| $100 in price | +$126 | −$6.96 | −$52.94 | +$65.83 |
| $200 in price | +$85.82 | −$132 | −$62.92 | −$109 |
| $300 in price | +$95.72 | −$161 | −$81.76 | −$147 |
| $500 in price | +$129 | −$163 | −$99.47 | −$133 |
| $800 in price | −$48.81 | −$53.89 | −$49.62 | −$152 |

| signals on | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| forming bar (live) | +$185 | −$159 | −$366 | −$340 |
| closed bars: slopes | −$71.91 | +$131 | −$654 | −$595 |
| closed bars: slopes + ladder RSI | +$101 | −$240 | −$765 | −$904 |

| ladder min interval | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 min | +$185 | −$159 | −$366 | −$340 |
| 1 min | +$47.53 | −$671 | −$141 | −$765 |
| 5 min | −$512 | −$1,070 | −$262 | −$1,844 |
| 15 min | +$31.54 | −$618 | −$129 | −$715 |
| 30 min | −$127 | −$265 | −$156 | −$549 |
| 60 min | −$21.21 | −$124 | −$330 | −$476 |

| max hold | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| none (live) | +$185 | −$159 | −$366 | −$340 |
| 0.25 h | −$333 | −$575 | −$855 | −$1,763 |
| 0.5 h | −$37.42 | −$232 | −$689 | −$958 |
| 1 h | −$101 | −$22.03 | −$473 | −$596 |
| 2 h | −$115 | +$22.78 | −$557 | −$649 |
| 4 h | +$52.87 | +$143 | −$374 | −$178 |
| 8 h | +$185 | −$159 | −$366 | −$340 |

| fc confirm s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$185 | −$159 | −$366 | −$340 |
| 10 | +$108 | −$192 | −$454 | −$538 |
| 30 | +$62.36 | −$21.73 | −$701 | −$661 |
| 60 | +$138 | −$53.19 | −$904 | −$819 |
| 120 | +$215 | +$109 | −$958 | −$634 |
| 300 | +$29.24 | +$100 | −$1,148 | −$1,018 |

| entry confirm s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$185 | −$159 | −$366 | −$340 |
| 10 | +$98.00 | +$228 | −$166 | +$161 |
| 30 | +$278 | −$324 | −$174 | −$220 |
| 60 | +$185 | +$153 | −$84.20 | +$253 |
| 120 | +$241 | +$201 | −$39.33 | +$402 |
| 300 | +$197 | +$298 | −$3.51 | +$492 |

| min hold s | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0 | +$185 | −$159 | −$366 | −$340 |
| 30 | +$188 | −$150 | −$369 | −$330 |
| 60 | +$178 | −$142 | −$353 | −$317 |
| 300 | +$281 | −$123 | −$329 | −$170 |
| 900 | +$306 | −$57.43 | −$554 | −$305 |

| stop loss | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| none (live) | +$185 | −$159 | −$366 | −$340 |
| $3 per unit | −$698 | −$801 | −$1,021 | −$2,520 |
| $5 per unit | −$649 | −$869 | −$1,161 | −$2,679 |
| $10 per unit | −$517 | −$739 | −$1,160 | −$2,415 |
| $20 per unit | −$353 | −$783 | −$938 | −$2,074 |
| $40 per unit | −$392 | −$414 | −$695 | −$1,501 |
| $80 per unit | −$134 | −$133 | −$617 | −$884 |

| side | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| both (live) | +$185 | −$159 | −$366 | −$340 |
| long only | −$23.04 | −$197 | −$256 | −$476 |
| short only | +$192 | +$28.10 | −$125 | +$94.95 |

| exit mix | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| force-close off | −$2,026 ✕ | −$2,600 ✕ | −$1,617 ✕ | −$6,243 |
| slope book only (netting exit) | −$131 | −$863 | −$155 | −$1,149 |

| target usd per unit | Aug–Nov 2026 | May–Aug 2026 | Feb–May 2026 | Three quarters |
|---|---:|---:|---:|---:|
| 0.5 | +$3.93 | +$54.53 | −$594 | −$535 |
| 1.0 | +$185 | −$159 | −$366 | −$340 |
| 1.5 | +$200 | −$250 | −$191 | −$241 |
| 2.0 | +$322 | −$200 | −$172 | −$49.40 |
| 3.0 | +$574 | −$141 | −$317 | +$116 |
| 5.0 | +$399 | −$349 | −$119 | −$68.90 |
| 10.0 | +$539 | −$320 | −$78.57 | +$140 |

</details>

## How fragile is the live result?

The live settings again, real $2,000 account and auto-step, varying only things the bot does not control.

### XAUUSDm

- **A slower loop** (median and range of 4 loop timings each): every 1 s: −$69.78 (−$2,000 … +$58.20); every 1.25 s: −$78.23 (−$148 … +$51.08); every 1.5 s: −$405 (−$509 … −$200); every 2 s: −$58.07 (−$280 … +$89.51).
- **Order latency**, the delay between the quote that triggered an order and the quote it fills at (median and range of 4 loop timings each): 0 ms: −$69.78 (−$2,000 … +$58.20); 150 ms: +$46.37 (−$69.24 … +$150); 300 ms: −$313 (−$541 … +$23.77); 600 ms: −$533 (−$753 … −$265); 1000 ms: −$1,415 (−$2,000 … −$663).
- **Spread scaled** (median and range of 4 loop timings each): ×1: −$69.78 (−$2,000 … +$58.20); ×1.25: −$471 (−$524 … −$323); ×1.5: −$1,320 (−$2,000 … −$559); ×2: −$2,000 (−$2,000 … −$2,000); ×3: −$2,000 (−$2,000 … −$2,000).
- **Adverse slippage on every fill**, in price units (median and range of 4 loop timings each): 0.02: −$454 (−$482 … −$123); 0.05: −$484 (−$2,000 … −$416); 0.1: −$2,000 (−$2,000 … −$974).
- **Start date** (same settings and end date, started up to 14 days later; 8 distinct runs, one path each): net P/L from −$836 to −$202; 0 of 8 positive; 0 stopped out.
- **Five consecutive quarters, a fresh $2,000 each**: 2025-08-13 → 2025-11-13 −$2,000 (stopped out); 2025-11-13 → 2026-02-13 +$292; 2026-02-13 → 2026-05-13 −$2,000 (stopped out); 2026-05-13 → 2026-08-13 −$2,000 (stopped out); 2026-08-13 → 2026-11-13 −$239.
- **Each calendar month on a fresh $2,000** (14 whole periods, per-second replay, one path each): 4 positive, 4 stopped out; best +$185, worst −$2,000, median −$361.
- **Each week of the three-month window on a fresh $2,000** (13 whole periods, per-second replay, one path each): 9 positive, 0 stopped out; best +$284, worst −$358, median +$60.91.
- **Which days happened to be in the quarter** (the baseline run's 3,620 baskets; whole days drawn with replacement 5,000 times, so some days count twice and others not at all; every basket re-sized by the bot's own unit rule; a path ends when the balance cannot cover a basket's worst floating loss): final balance 5th–95th percentile $0.00–$3,906, median $1,526; ended below the start in 65% of the draws, lost more than a quarter in 49%, wiped in 29%.

| Month (fresh $2,000 each) | Net P/L | Max drawdown | Baskets | Win rate | Worst basket | Stopped out |
|---|---:|---:|---:|---:|---:|---:|
| 2025-08-13 → 2025-09-01 (part) | −$262 | $656 | 422 | 83.7% | −$191 | no |
| 2025-09-01 → 2025-10-01 | −$544 | $675 | 966 | 91.5% | −$303 | no |
| 2025-10-01 → 2025-11-01 | −$2,000 | $2,101 | 842 | 90.7% | −$765 | **yes** |
| 2025-11-01 → 2025-12-01 | +$28.75 | $850 | 1213 | 95.1% | −$775 | no |
| 2025-12-01 → 2026-01-01 | −$39.61 | $1,049 | 1151 | 94.1% | −$605 | no |
| 2026-01-01 → 2026-02-01 | −$794 | $2,066 | 1377 | 94.5% | −$1,584 | no |
| 2026-02-01 → 2026-03-01 | −$1,046 | $2,107 | 1429 | 96.6% | −$1,793 | no |
| 2026-03-01 → 2026-04-01 | −$2,000 | $2,687 | 792 | 96.0% | −$2,687 | **yes** |
| 2026-04-01 → 2026-05-01 | −$177 | $916 | 1230 | 93.3% | −$554 | no |
| 2026-05-01 → 2026-06-01 | −$2,000 | $2,049 | 972 | 91.5% | −$570 | **yes** |
| 2026-06-01 → 2026-07-01 | −$76.12 | $891 | 1279 | 94.2% | −$298 | no |
| 2026-07-01 → 2026-08-01 | +$130 | $860 | 1295 | 94.0% | −$521 | no |
| 2026-08-01 → 2026-09-01 | −$2,000 | $2,077 | 233 | 91.4% | −$1,687 | **yes** |
| 2026-09-01 → 2026-10-01 | +$99.93 | $439 | 1295 | 94.0% | −$213 | no |
| 2026-10-01 → 2026-11-01 | +$185 | $427 | 1196 | 93.0% | −$117 | no |
| 2026-11-01 → 2026-11-13 (part) | −$400 | $797 | 479 | 95.4% | −$293 | no |

### BTCUSDm

- **A slower loop** (median and range of 4 loop timings each): every 1 s: +$197 (+$171 … +$356); every 1.25 s: +$156 (+$81.61 … +$226); every 1.5 s: +$200 (+$143 … +$217); every 2 s: +$144 (+$115 … +$323).
- **Order latency**, the delay between the quote that triggered an order and the quote it fills at (median and range of 4 loop timings each): 0 ms: +$197 (+$171 … +$356); 150 ms: +$224 (+$202 … +$305); 300 ms: +$226 (+$188 … +$275); 600 ms: +$89.02 (+$26.51 … +$220); 1000 ms: +$195 (+$131 … +$261).
- **Spread scaled** (median and range of 4 loop timings each): ×1: +$197 (+$171 … +$356); ×1.25: +$112 (−$8.30 … +$159); ×1.5: −$78.41 (−$99.37 … −$7.29); ×2: −$347 (−$448 … −$318); ×3: −$739 (−$796 … −$706).
- **Adverse slippage on every fill**, in price units (median and range of 4 loop timings each): 1: +$126 (−$19.93 … +$145); 2.5: −$201 (−$382 … −$59.16); 5: −$590 (−$741 … −$493).
- **Start date** (same settings and end date, started up to 14 days later; 10 distinct runs, one path each): net P/L from +$301 to +$371; 10 of 10 positive; 0 stopped out.
- **Five consecutive quarters, a fresh $2,000 each**: 2025-08-13 → 2025-11-13 −$1,564; 2025-11-13 → 2026-02-13 −$713; 2026-02-13 → 2026-05-13 −$366; 2026-05-13 → 2026-08-13 −$159; 2026-08-13 → 2026-11-13 +$185.
- **Each calendar month on a fresh $2,000** (14 whole periods, per-second replay, one path each): 4 positive, 0 stopped out; best +$211, worst −$596, median −$155.
- **Each week of the three-month window on a fresh $2,000** (13 whole periods, per-second replay, one path each): 10 positive, 0 stopped out; best +$88.43, worst −$176, median +$29.62.
- **Which days happened to be in the quarter** (the baseline run's 2,608 baskets; whole days drawn with replacement 5,000 times, so some days count twice and others not at all; every basket re-sized by the bot's own unit rule; a path ends when the balance cannot cover a basket's worst floating loss): final balance 5th–95th percentile $1,866–$2,951, median $2,311; ended below the start in 12% of the draws, lost more than a quarter in 0%, wiped in 0%.

| Month (fresh $2,000 each) | Net P/L | Max drawdown | Baskets | Win rate | Worst basket | Stopped out |
|---|---:|---:|---:|---:|---:|---:|
| 2025-08-13 → 2025-09-01 (part) | −$153 | $335 | 528 | 88.5% | −$206 | no |
| 2025-09-01 → 2025-10-01 | −$418 | $532 | 667 | 80.2% | −$379 | no |
| 2025-10-01 → 2025-11-01 | −$533 | $719 | 1167 | 86.9% | −$355 | no |
| 2025-11-01 → 2025-12-01 | −$475 | $757 | 1097 | 86.7% | −$260 | no |
| 2025-12-01 → 2026-01-01 | +$93.14 | $149 | 740 | 82.7% | −$54.52 | no |
| 2026-01-01 → 2026-02-01 | −$159 | $537 | 906 | 82.8% | −$160 | no |
| 2026-02-01 → 2026-03-01 | −$596 | $952 | 986 | 89.2% | −$795 | no |
| 2026-03-01 → 2026-04-01 | −$252 | $486 | 1005 | 83.7% | −$224 | no |
| 2026-04-01 → 2026-05-01 | −$44.47 | $302 | 742 | 79.8% | −$158 | no |
| 2026-05-01 → 2026-06-01 | +$79.54 | $292 | 797 | 78.4% | −$71.65 | no |
| 2026-06-01 → 2026-07-01 | −$166 | $514 | 881 | 84.5% | −$484 | no |
| 2026-07-01 → 2026-08-01 | −$151 | $250 | 747 | 77.8% | −$94.32 | no |
| 2026-08-01 → 2026-09-01 | −$58.61 | $310 | 744 | 80.7% | −$119 | no |
| 2026-09-01 → 2026-10-01 | +$211 | $149 | 864 | 82.5% | −$52.68 | no |
| 2026-10-01 → 2026-11-01 | +$30.14 | $596 | 901 | 81.2% | −$99.62 | no |
| 2026-11-01 → 2026-11-13 (part) | −$14.57 | $84.36 | 343 | 76.1% | −$42.97 | no |

## Recommendations

1. **Do not run the live settings on real money as they are.** They lost in every period tested: gold −$666 a quarter in 2023, −$675 in 2024 – mid 2025 and −$1,480 in Aug 2025 – Nov 2026 on a $2,000 account; BTC −$1,194, −$1,995 and −$585, with the account wiped in 46 of 48 BTC runs of 2024-25.
2. **Put a hard stop behind every basket, at the broker.** The stop the bot sends today is not a stop (`RISK_REWARD_RATIO = [1, 1]` gives SL = 0.0 on a buy and SL = twice the price on a sell, see the live-code findings). Every design that held up has a stop on the whole basket.
3. **Trade with the higher-timeframe trend.** Entries only when the H1 MACD signal line agrees was the single largest improvement on gold; an H4 trend did not hold up outside 2025-26.
4. **Replace the Fibonacci ladder.** It is what empties the account: 26 of 32 units go in within seconds at one price, with no stop. If a ladder is kept, use equal lots, at most one or two adds, each at least one volatility unit away and released by an event (a MACD turn or an RSI cross-back, not an RSI level), all inside the basket stop. On gold one such add earned more than no add in every period tested; on BTC less in two of three.
5. **Candidate for a demo account: V3-lite on gold** (`IMPROVEMENT.md`): H1 trend filter, H1 votes with M15 agreement, stop and target 8 H1-volatility units, no ladder, 12 h pause after a loss. Expect about 25 baskets a quarter held about a day each, 60–64% won, and an edge of a few dollars a basket per 0.01 lot. Positions are held over weekends, so a Monday gap can pass the stop.
6. **BTC:** no tested design makes money reliably. Pause it, or run V3-lite only as a capital-preserving setup on demo.
7. **Keep the unit at 1 until a quarter of demo results exist.** The balance auto-step raises the stake after good runs and takes the next loss at the larger size.
8. **Fix the operational defects in the live code** listed under "Live-code findings": a failed position read is taken for "no positions", orders and closes are not checked or retried, a dead terminal connection is swallowed.
9. **Before any change goes live:** write it into `strategy.py` / `app.py` on a new branch, check with `python -m backtesting parity` that the backtester and the new live code make the same decisions, run it on a demo account, and compare the demo's deal history with the backtest of the same weeks.

## Why the simulation can be trusted — and where it cannot

**It makes the same decisions as the live code.** The reference engine runs this branch's own `app.py` loop, unmodified, against a simulated MT5 terminal fed with the same ticks. 373,614 polls of the real `app.py` loop across 7 windows, compared with the fast engine poll by poll:

| Window (UTC) | Settings | Live polls | Signal / score / fill mismatches | Fills | Orders the broker refused | Final balance live = fast | Result |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDm 2026-09-22 00:00 → 2026-09-22 12:00 | open[H4x1 + M5x1] fc[D1x1 + H4x2 + H1x3 + M15x4] + other overrides | 43,159 | 0 / 0 / 0 | 131 | none | 2,040.35 = 2,040.35 | identical |
| BTCUSDm 2026-10-10 00:00 → 2026-10-11 00:00 | open[H1x1 + M15x1] fc[M15x1] | 86,359 | 0 / 0 / 0 | 45 | none | 2,001.62 = 2,001.62 | identical |
| BTCUSDm 2026-09-15 00:00 → 2026-09-16 00:00 | open[H1x1 + M15x1] fc[M15x1] | 86,375 | 0 / 0 / 0 | 108 | none | 1,992.88 = 1,992.88 | identical |
| BTCUSDm 2026-08-20 00:00 → 2026-08-20 12:00 | open[H1x1 + M15x1] fc[M15x1] + other overrides | 43,159 | 0 / 0 / 0 | 128 | none | 5,237.01 = 5,237.01 | identical |
| XAUUSDm 2026-02-02 00:50 → 2026-02-02 01:40 | open[H1x1 + M15x1] fc[M15x1] + other overrides | 2,998 | 0 / 0 / 0 | 16 | none | 1,000,018.59 = 1,000,018.59 | identical |
| XAUUSDm 2026-10-14 00:00 → 2026-10-15 00:00 | open[H1x1 + M15x1] fc[M15x1] | 82,800 | 0 / 0 / 0 | 154 | 1 market closed, 34 close only | 2,013.79 = 2,013.79 | identical |
| XAUUSDm 2026-10-16 18:00 → 2026-10-19 03:00 | open[H1x1 + M15x1] fc[M15x1] | 28,764 | 0 / 0 / 0 | 25 | none | 2,018.19 = 2,018.19 | identical |

The simulated terminal applies the same broker-side rules as the fast engine (an order sent after a session's last quote is refused, new orders are refused for 90 s after a session break and 3.5 min after the weekly open, and an order the free margin cannot carry is refused), so the windows in which the broker refused orders also check what the live loop does next. Not covered by this comparison: the stop-out (the simulated terminal has none; unit tests only), the handling of holes in the BTC history (the live code never meets one), and the 90 s / 3.5 min durations themselves, which are read off Exness's published behaviour, not measured.

**The data is the broker's own.** Exness's published tick history for `XAUUSDm` and `BTCUSDm`:

| Symbol | Span | Ticks | Dropped / out-of-order rows | Spread median / p99 / max | Silences > 3 min | Days without ticks |
|---|---:|---:|---:|---:|---:|---:|
| XAUUSDm | 2025-08-13 → 2026-11-12 | 121,848,115 | 0 / 0 | 0.24 / 0.36 / 4.00 | 335 (250 daily break, 64 weekend, 10 short pause, 7 early close before the daily break (holiday), 3 holiday / long close, 1 other) | 2025-11-30, 2026-04-03 |
| BTCUSDm | 2025-08-13 → 2026-11-12 | 70,060,891 | 0 / 0 | 14.00 / 21.60 / 413.89 | 72 (69 short pause (maintenance), 3 hole in the archive) | 2025-08-30, 2026-03-30, 2026-03-31 |

XAUUSDm: days without ticks other than Saturdays: 2025-11-30 (Sunday), 2026-04-03 (Friday). A Sunday without ticks is a late weekly open; a weekday is a market holiday (it shows up as a long close in the list of silences). 1 silence fits no session pattern (`data_quality/XAUUSDm.json` lists them).  
**BTCUSDm has 3 holes in the archive** — the market traded, the history is missing: 2025-08-29 23:59 → 2025-08-31 00:00 UTC (24.0 h, price +0.4% across it); 2025-11-30 18:29 → 2025-12-01 00:00 UTC (5.5 h, price -1.1% across it); 2026-03-29 23:59 → 2026-04-01 00:00 UTC (48.0 h, price +3.4% across it). The backtest does not pretend to know what happened inside them: a basket open at the last quote before a hole is closed there, and no basket is opened for 6.3 days after the history resumes, whatever the settings (38 H4 bars: the time the slowest indicator needs to leave the hole behind; see `data_hole_s` in the README).

**What it cannot know.** Real order latency and slippage, requotes, terminal or VPS outages, bot restarts, how long each pass of the live loop really takes, and whether the live MT5 server's ticks match the archive tick for tick. The timing and cost tests above show how sensitive the result is to order latency, slippage and the duration of a pass; they do not bound them. Leverage is taken as 1:2000 on gold and 1:400 on BTC and swaps as zero (Exness accounts are swap-free by default); neither was read from a real account. A backtest is a description of the past, not a forecast.

## Live-code findings (outside the strategy rules)

Found while reading the live code for the backtester; each was checked by a second reviewer against the code. Nothing here was changed on this branch.

- **No stop exists at the broker: every loss exit lives in the Python loop** (mt5_helper.py:471-481, constants.py:121) — With RISK_REWARD_RATIO = [1, 1] every BUY is sent with SL = price − price×1 = 0.0 (which MT5 reads as "no stop") and TP = 2× price; every SELL with SL = 2× price and TP = 0.0. The only thing that ever closes a losing basket is the M15 force-close, and it only runs while the Python process is alive, connected and sees the market as live. The CHANGELOG records this as a deliberate choice; it is listed first because every other item below is made worse by it. At unit 1 a full 0.32-lot basket loses the whole $2,000 on a $62.50 move in gold or a $6,250 move in BTC.
- **A dead MT5 connection is swallowed silently** (app.py:238, 479-844) — The bot connects once at start-up. If the terminal or its IPC link dies while Python keeps running, every helper call returns "no data": positions read as flat, the market reads as closed, no signal is computed and no close can be sent. The loop prints one console line per pass, keeps writing a fresh dashboard file showing 0 positions, and never reconnects, exits or raises an alert.
- **A failed position read is treated as "no positions"** (mt5_helper.py:52-53, 101-102; app.py:503-511) — get_buy_positions / get_sell_positions return None both when there are no positions and when the read failed, and the loop maps None to a count of 0. One failed read while a basket is open makes the bot believe it is flat: it re-derives the unit and, if the entry conditions hold, opens a second basket on top of the first. Demonstrated on this branch's real app.py by tests/test_live_fault_injection.py::test_failed_position_read_is_treated_as_flat.
- **Open and add orders are never checked** (mt5_helper.py:508-511, 526-529; app.py:729-750, 769-790) — buy() / sell() return the order result unread and the bot logs BUY_EXECUTED / SELL_EXECUTED unconditionally. A rejected order (market closed, no money, requote) leaves the signal true, so it is re-sent every loop with no back-off and no alert, and each attempt is logged as executed. Demonstrated by test_rejected_open_is_logged_as_executed_and_resent_every_loop: twelve seconds of refusals produce an "executed" line on every pass and no position.
- **A basket close is several independent orders, never retried** (mt5_helper.py:531-621; app.py:752-762, 792-802) — close_by_type sends one market order per leg in the order MT5 lists them. A leg that fails or fills partially is counted and left; the caller ignores the failure count, starts the re-entry cooldown and logs the close as done. The leftover leg stays open until a close condition happens to fire again.
- **Ladder tier comes from the ticket count, lot size from the summed volume** (strategy.py:39-65; strategy.py:279-288, 301-310; app.py:739, 779) — The two stay in step only while the open positions are exactly the bot's own ladder. After a partial close, a manual trade or a second process on the same symbol, the next add continues up the Fibonacci series from whatever volume is left: a lone 0.13 leg is followed by 0.13, 0.21, 0.34, 0.55 and 0.89 lots. There is no maximum-lot cap.
- **No magic number and no instance lock** (mt5_helper.py:483-493, 591-601; strategy.py:261 / 268 / 290) — Orders carry no magic number or comment, so every position on the symbol counts as the bot's: a manual trade or a second copy of the bot is added into the basket profit, used to size the next add, and closed by the bot. If positions exist on both sides at once the strategy has no branch for it and does nothing at all, with no log line, until someone intervenes.
- **A restart forgets the unit and the cooldown** (app.py:468, 477, 505-511) — The unit and the time of the last close exist only in process memory. After a restart with a basket open the unit is 1 until the symbol is flat: on an account above $2,500 the remaining adds are mis-sized (0.44× to 1.27× of the intended ladder) and the profit target drops from $N to $1. The 300 s re-entry cooldown is also forgotten: test_restart_forgets_the_reentry_cooldown shows an immediate re-entry where the running process would still be waiting. Changing any constant requires exactly such a restart.
- **Brake and trading window only block the first order of a basket** (app.py:516-517, 726, 766) — Ladder adds are sent under the manual brake, outside the trading window and at the weekend reopen, and nothing flattens a basket before the weekend. The backtest reproduces this as written; the worst gold baskets in the results were carried across a session break.
- **The liveness gate compares the VPS clock with broker time, and the bars that drive decisions are not checked at all** (mt5_helper.py:420-431; app.py:558, 580-584) — All actions, exits included, run only when the newest tick is less than three minutes old measured against the VPS wall clock. A VPS clock running more than three minutes fast, or a server whose time is not UTC, makes the bot treat an open market as closed and stop evaluating exits. Separately, the RSI / MACD inputs come from a single unverified copy_rates_from_pos call with no bar-age check, so stale bars would hold the force-close silent while ticks keep the gate open.
- **Decisions are taken on the still-forming bar, about once a second** (indicator.py:188-198; app.py:580-611, 834; strategy.py:279-288, 301-310) — The current value, the newest pivot's right-hand neighbour and the MACD side selector all include the forming bar, so a pivot can appear and vanish inside one bar and a close or entry fires on the first poll that sees it. This is how the live bot works and the backtest replays it poll by poll; it is listed because any closed-bar backtest (TradingView, MT5 strategy tester on bar closes) will not reproduce the live trades.
- **If any account is in MT5 netting mode, the ladder would run away** (strategy.py:279-288, 301-310; mt5_helper.py:50-71) — The ladder tier is the number of position tickets. On an MT5 netting-mode account there is always exactly one ticket, so tier 1 (M1 RSI ≤ 35 / ≥ 65) would re-fire about every two seconds with growing Fibonacci lots: 2.31 lots after nine adds. Nothing in the repo says any account is in that mode ("netting" here names the strategy variant, and the code documents six separate positions), but the code never checks account_info().margin_mode. Worth confirming for all forty accounts.
- **The +$1 target is a snapshot taken before the close orders** (strategy.py:271, 293; mt5_helper.py:561-603) — The target test reads the floating profit polled at the start of the pass; the legs are then closed one by one at market. What is realised is that snapshot plus or minus volume × price drift during the close (about $0.32 for every cent gold moves, on a full ladder), and the log records the snapshot, not the fills. The threshold also does not grow with the basket: a full ladder needs only $0.03 per ounce beyond break-even to trigger.

## Reproduce

```bash
pip install -r requirements-backtest.txt
python -m backtesting data --from 2025-07 --to 2026-11   # ~2 GB download
python -m backtesting reproduce                         # every table except the round-2 research (findings on the
                                                        # 2023 test, recommendations: IMPROVEMENT.md, backtest_results/improve/)
python -m backtesting docs                              # this file
python -m pytest tests -q                               # test-suite
```
