# Auto-safety limits for the live accounts: what the 8-year backtest gives

*Calibration of 2026-11-21. `python3 -m backtesting.research.live_safety` rebuilds every figure on this page from the trade records of the final-ten study; the tables are in this folder as CSV files.*

The breaker blocks new trades after losses. It has three limits. This page sets them from the backtest by one rule, fixed before any number was read:

> For each limit, take the tightest value that would have blocked at most once in two account-years on average (0.5 blocks per account-year), both in the 24 most recent 12-month accounts and in all 84. This is the "medium" strictness that was asked for.

## The limits the rule gives

| Account type | Gold bot + BTC bot | DROP: block both bots when the balance is this far below its high | DAY: or when one day's loss reaches | STREAK: block one bot after this many losing trades in a row (gold / BTC) | Blocks per account-year with all three on (recent 24 / all 84) |
|---|---|---|---|---|---|
| P1 | Gold Top 2 + BTC Top 2 | 15% | 7.5% | 10 / 8 | 0.29 / 1.13 |
| P2 | Gold V3-lite + BTC Top 2 | 15% | 7.5% | 6 / 8 | 0.67 / 0.71 |
| P3 | Gold Top 1 + BTC Top 2 | 25% | 15% | 9 / 8 | 0.50 / 0.67 |
| P4 | Gold V3-lite + BTC Turtle S2 | 20% | 12.5% | 6 / 5 | 0.83 / 0.65 |
| P5 | Gold Top 2 + BTC Turtle S2 | 20% | 10% | 10 / 5 | 0.25 / 0.89 |
| P6 (information only) | Gold Top 1 + BTC Turtle S2 | 25% | 12.5% | 9 / 5 | 0.42 / 0.74 |

Each limit on its own stays at or below 0.5 blocks per account-year. The last column adds the three together (STREAK counts once per bot), so it can be higher.

One set for every account type, for comparison: DROP **25%**, DAY **15%**, STREAK as in the table (section 7).

### Read this first

1. **The breaker stops the next trade, not the one that is open.** At one unit (0.01 lot) the worst single trade lost $394 for gold V3-lite and $420 for gold Top 1: 26% and 28% of a $1,500 account. The Turtle's worst was $171 (11%), gold Top 2's $61 and BTC Top 2's $54 (about 4%). A DROP or DAY limit smaller than one such trade is reached by a single trade, after the loss is already booked.
2. **On this history the breaker did not make the accounts safer, and it cost some profit.** With the three limits on, the average recent account ended lower than without them in 5 of the 5 account types, by $2 to $392 (section 5). The deepest fall of the worst account became more than one point smaller in 0 account types and more than one point larger in 2 (all 84 accounts; recent 24: 0 and 2). The reason: these bots made money over the period, so the trades that a block skipped had made money on balance. A backtest of profitable bots can only show how often the breaker interrupts a working bot. It cannot show what the breaker saves when a bot stops working, which is what it is for.
3. **A few market days decide the counts.** The 12-month accounts overlap, so one bad day is counted in up to 12 of them. In the recent 24 accounts the chosen DAY limits were reached on this many different days: P1 0, P2 3, P3 2, P4 2, P5 2. One such day more or fewer can move a limit by a grid step.
4. **Accounts started lately were blocked more often than the rule's 0.5.** A typical losing gold trade is now about 4 times larger in dollars than over the 8 years (section 2), and a new $1,500 account meets it at its smallest size. With all three limits on, the 12 most recent of the 84 starts (Dec 2024 – Nov 2025) had this many blocks per account-year: P1 0.25, P2 1.33, P3 1.00, P4 0.92, P5 0.33. Nine later starts (Dec 2025 – Aug 2026, run to the end of the data) had: P1 3.42, P2 5.22, P3 3.06, P4 0.54, P5 0.18 (section 6). The rule averages such accounts with older, quieter ones.
5. **The BTC Turtle's one-unit figures are smaller than in the earlier note.** Its worst losing stretch at one unit is $397 (not $747), its worst trade $171 (not $514) and its net profit of the last 24 months +$1,431 (not +$3,763). The earlier figures left most Turtle trades at the 2 to 4 units of the published account (section 9).

## 1. What was measured

- **The trades.** Every closed trade of each bot's own 8-year backtest, 13 Nov 2018 – 13 Nov 2026, brought to one unit (0.01 lot). A gold Top 1 trade can hold two legs of one unit, a Turtle trade up to four.
- **The account.** $1,500, shared by one gold bot and one BTC bot. Each bot trades `floor(half the balance / STEP) + 1` units, at most 10, from the balance booked when the trade opens. STEP is $1,250 for gold Top 2 and BTC Top 2, $1,750 for gold V3-lite and Top 1, $2,500 for the Turtle, so a bot trades 1 unit until the account reaches $2,500, $3,500 or $5,000.
- **The accounts.** A new account on the 1st of every month from Dec 2018 to Nov 2025, each run for 12 months: 84 accounts. "Recent 24" are the starts from Dec 2023 to Nov 2025. One more account runs for the whole 8 years.
- **The three limits.** All are checked on the booked balance (closed trades only), after every closed trade:
  - DROP: the balance is X% below its highest value since the start or the last unblock. Blocks both bots.
  - DAY: the balance is Y% below the balance at 00:00 UTC (after an unblock that day: below the balance at the unblock). Blocks both bots.
  - STREAK: N closed trades of one bot in a row lost money. Blocks that bot.
- **A block** stops new trades only. A trade that is open keeps its own stop and target and is booked when it closes. The unblock is taken to come 24 hours after the block and starts the counts afresh; 4, 72 and 168 hours were run as well.
- **An account-year** is one account for one year. A rate of 0.5 is one block in two years of one account, or about 5 blocks a year across 10 accounts, per limit.

## 2. The five bots at one unit (0.01 lot)

| Bot | STEP | Trades | Winning trades | Net profit | Worst losing stretch | Worst single trade | Longest run of losing trades |
|---|---|---|---|---|---|---|---|
| Gold V3-lite | $1,750 | 809 / 198 | 56% / 61% | +$4,054 / +$2,849 | −$394 / −$394 | −$394 / −$394 | 9 / 5 |
| Gold Top 1 | $1,750 | 1,240 / 301 | 48% / 54% | +$4,852 / +$4,044 | −$660 / −$476 | −$420 / −$420 | 10 / 6 |
| Gold Top 2 | $1,250 | 1,316 / 325 | 36% / 43% | +$2,959 / +$2,725 | −$335 / −$262 | −$61 / −$61 | 14 / 7 |
| BTC Top 2 | $1,250 | 1,110 / 275 | 48% / 50% | +$1,324 / +$853 | −$370 / −$279 | −$54 / −$52 | 8 / 8 |
| BTC Turtle S2 | $2,500 | 60 / 16 | 38% / 50% | +$3,755 / +$1,431 | −$397 / −$397 | −$171 / −$171 | 9 / 4 |

*Each cell: the 8 years / the last 24 months (trades closed from 13 Nov 2024). Worst losing stretch = the largest fall of the running total from a high, on closed trades.*

What one losing trade costs now, at one unit, against a $1,500 account (trades closed in the last 12 months, from 13 Nov 2025):

| Bot | Trades in the 12 months | Typical losing trade (the middle one) | 1 losing trade in 10 lost more than | Worst trade | Typical losing trade over the 8 years |
|---|---|---|---|---|---|
| Gold V3-lite | 101 | $73 (4.8%) | $123 (8.2%) | $394 (26.2%) | $19 |
| Gold Top 1 | 158 | $73 (4.9%) | $124 (8.2%) | $420 (28.0%) | $19 |
| Gold Top 2 | 158 | $36 (2.4%) | $48 (3.2%) | $61 (4.1%) | $10 |
| BTC Top 2 | 139 | $18 (1.2%) | $27 (1.8%) | $52 (3.4%) | $12 |
| BTC Turtle S2 | 7 | $98 (6.5%) | $108 (7.2%) | $110 (7.4%) | $34 |

*The Turtle's 12 months hold too few trades to call anything typical.*

## 3. Two bots on one $1,500 account, no breaker

| Account type | Accounts | End balance: lowest / middle / highest | Deepest fall from a high: middle / worst account | Worst single day: middle / worst account | Accounts ending below $1,000 / $750 |
|---|---|---|---|---|---|
| P1 | recent 24 | $2,307 / $3,970 / $5,623 | 12.3% / 15.9% | 4.3% / 7.4% | 0 / 0 |
|  | all 84 | $1,149 / $1,606 / $5,623 | 12.1% / 30.7% | 2.9% / 7.4% | 0 / 0 |
|  | 8-year account | $10,995 | 28.8% | 5.4% | - |
| P2 | recent 24 | $2,278 / $3,218 / $5,943 | 13.1% / 24.0% | 4.4% / 22.0% | 0 / 0 |
|  | all 84 | $1,366 / $1,802 / $5,943 | 12.5% / 24.0% | 3.5% / 22.0% | 0 / 0 |
|  | 8-year account | $13,751 | 17.0% | 12.1% | - |
| P3 | recent 24 | $2,455 / $3,724 / $8,626 | 16.8% / 24.4% | 6.1% / 21.9% | 0 / 0 |
|  | all 84 | $935 / $1,862 / $8,626 | 18.5% / 45.1% | 3.9% / 21.9% | 3 / 0 |
|  | 8-year account | $16,215 | 30.5% | 14.4% | - |
| P4 | recent 24 | $2,004 / $2,855 / $5,540 | 15.3% / 29.4% | 11.8% / 17.6% | 0 / 0 |
|  | all 84 | $1,317 / $1,805 / $5,540 | 11.5% / 29.6% | 4.4% / 17.6% | 0 / 0 |
|  | 8-year account | $20,328 | 15.3% | 12.6% | - |
| P5 | recent 24 | $2,050 / $3,132 / $5,603 | 15.3% / 20.8% | 7.8% / 10.9% | 0 / 0 |
|  | all 84 | $1,121 / $1,641 / $5,603 | 15.0% / 31.0% | 4.5% / 10.9% | 0 / 0 |
|  | 8-year account | $18,669 | 22.4% | 6.0% | - |
| P6 (information only) | recent 24 | $2,198 / $3,121 / $7,615 | 22.3% / 24.2% | 10.0% / 23.3% | 0 / 0 |
|  | all 84 | $743 / $1,998 / $7,615 | 19.7% / 57.1% | 4.6% / 23.3% | 6 / 1 |
|  | 8-year account | $21,781 | 27.4% | 12.8% | - |

*Deepest fall = the largest fall of the booked balance below its highest value so far, in per cent of that high. Worst single day = the largest loss booked within one UTC day, in per cent of the balance at 00:00. These are what the DROP and DAY limits look at. The 8-year account is one account: one figure per cell.*

## 4. Each limit on its own

Blocks per account-year with only that limit on (unblock after 24 hours). The chosen value is in bold: the tightest one at or below 0.5 in both rows.

**DROP: block both bots when the balance is this far below its high**

| Account type | Accounts | 15% | 20% | 25% | 30% | 35% | 40% | 45% | 50% |
|---|---|---|---|---|---|---|---|---|---|
| P1 | recent 24 | **0.17** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | **0.37** | 0.12 | 0.08 | 0.04 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | recent 24 | **0.33** | 0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | **0.21** | 0.06 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P3 | recent 24 | 1.92 | 0.75 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 1.26 | 0.70 | **0.18** | 0.12 | 0.07 | 0.02 | 0.01 | 0.00 |
| P4 | recent 24 | 0.58 | **0.38** | 0.21 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 0.40 | **0.24** | 0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P5 | recent 24 | 0.62 | **0.08** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 0.60 | **0.25** | 0.10 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |
| P6 (information only) | recent 24 | 2.25 | 0.92 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 1.61 | 0.77 | **0.33** | 0.23 | 0.12 | 0.11 | 0.10 | 0.08 |

**DAY: block both bots when one day's loss reaches**

| Account type | Accounts | 5% | 7.5% | 10% | 12.5% | 15% | 20% | 25% | 30% |
|---|---|---|---|---|---|---|---|---|---|
| P1 | recent 24 | 0.75 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 0.36 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | recent 24 | 1.25 | **0.46** | 0.38 | 0.12 | 0.12 | 0.08 | 0.00 | 0.00 |
|  | all 84 | 0.50 | **0.13** | 0.11 | 0.04 | 0.04 | 0.02 | 0.00 | 0.00 |
| P3 | recent 24 | 4.04 | 1.29 | 1.12 | 0.92 | **0.38** | 0.04 | 0.00 | 0.00 |
|  | all 84 | 1.30 | 0.37 | 0.32 | 0.26 | **0.11** | 0.01 | 0.00 | 0.00 |
| P4 | recent 24 | 4.38 | 1.71 | 0.58 | **0.46** | 0.17 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 1.68 | 0.76 | 0.18 | **0.13** | 0.05 | 0.00 | 0.00 | 0.00 |
| P5 | recent 24 | 1.88 | 0.62 | **0.17** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 0.96 | 0.51 | **0.14** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P6 (information only) | recent 24 | 4.96 | 1.46 | 0.67 | **0.42** | 0.29 | 0.29 | 0.00 | 0.00 |
|  | all 84 | 1.92 | 0.82 | 0.29 | **0.12** | 0.08 | 0.08 | 0.00 | 0.00 |

**STREAK: block one bot after this many losing trades in a row**

| Bot | Accounts | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold V3-lite | recent 24 | 1.08 | 0.88 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 1.94 | 1.21 | **0.14** | 0.13 | 0.13 | 0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Gold Top 1 | recent 24 | 4.12 | 0.58 | 0.46 | 0.00 | 0.00 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 5.77 | 2.63 | 1.40 | 0.98 | 0.69 | **0.15** | 0.13 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Gold Top 2 | recent 24 | 8.33 | 5.58 | 2.67 | 1.12 | 0.08 | 0.00 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 11.85 | 7.94 | 4.75 | 2.95 | 1.67 | 0.87 | **0.46** | 0.33 | 0.26 | 0.14 | 0.13 | 0.00 | 0.00 |
| BTC Top 2 | recent 24 | 3.33 | 0.83 | 0.58 | 0.12 | **0.12** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 4.88 | 1.99 | 1.10 | 0.82 | **0.30** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| BTC Turtle S2 | recent 24 | 0.58 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
|  | all 84 | 0.45 | **0.14** | 0.11 | 0.11 | 0.11 | 0.08 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

How firm each choice is, and what the limit did on its own:

| Account type | Limit | Chosen | Blocks per account-year | One step tighter | One step wider | Different days it was reached | Largest value seen with no breaker, all 84 accounts | Average change of the end balance | If the last 12 starts had to meet the rule too | and the 9 late starts as well |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | DROP | **15%** | 0.17 / 0.37 | not tried | 20%: 0.00 / 0.12 | 2 / 15 | 30.7% | −$17 / −$5 | 15% | 20% |
| P2 | DROP | **15%** | 0.33 / 0.21 | not tried | 20%: 0.12 / 0.06 | 4 / 8 | 24.0% | −$22 / −$5 | 20% | 30% |
| P3 | DROP | **25%** | 0.00 / 0.18 | 20%: 0.75 / 0.70 | 30%: 0.00 / 0.12 | 0 / 9 | 45.1% | $0 / −$1 | 25% | 30% |
| P4 | DROP | **20%** | 0.38 / 0.24 | 15%: 0.58 / 0.40 | 25%: 0.21 / 0.12 | 5 / 7 | 29.6% | −$3 / −$3 | 20% | 20% |
| P5 | DROP | **20%** | 0.08 / 0.25 | 15%: 0.62 / 0.60 | 25%: 0.00 / 0.10 | 1 / 12 | 31.0% | −$3 / −$1 | 20% | 20% |
| P6 (information only) | DROP | **25%** | 0.00 / 0.33 | 20%: 0.92 / 0.77 | 30%: 0.00 / 0.23 | 0 / 15 | 57.1% | $0 / +$1 | 25% | 25% |
| P1 | DAY | **7.5%** | 0.00 / 0.00 | 5%: 0.75 / 0.36 | 10%: 0.00 / 0.00 | 0 / 0 | 7.4% | $0 / $0 | 7.5% | 7.5% |
| P2 | DAY | **7.5%** | 0.46 / 0.13 | 5%: 1.25 / 0.50 | 10%: 0.38 / 0.11 | 3 / 3 | 22.0% | −$82 / −$23 | 12.5% | 20% |
| P3 | DAY | **15%** | 0.38 / 0.11 | 12.5%: 0.92 / 0.26 | 20%: 0.04 / 0.01 | 2 / 2 | 21.9% | −$388 / −$111 | 20% | 20% |
| P4 | DAY | **12.5%** | 0.46 / 0.13 | 10%: 0.58 / 0.18 | 15%: 0.17 / 0.05 | 2 / 2 | 17.6% | −$3 / −$1 | 15% | 20% |
| P5 | DAY | **10%** | 0.17 / 0.14 | 7.5%: 0.62 / 0.51 | 12.5%: 0.00 / 0.00 | 2 / 3 | 10.9% | $0 / $0 | 10% | 10% |
| P6 (information only) | DAY | **12.5%** | 0.42 / 0.12 | 10%: 0.67 / 0.29 | 15%: 0.29 / 0.08 | 2 / 2 | 23.3% | −$259 / −$74 | 25% | 25% |

*Pairs of figures: recent 24 / all 84 accounts. "One step tighter" fails the rule; "not tried" = the chosen value is the tightest in the grid. The last two columns are not part of the rule. They show what the same rule would give if the 12 most recent of the 84 starts (Dec 2024 – Nov 2025), and then also the 9 late starts of section 6, had to stay at or below 0.5 as well.*

| Bot | Chosen N | Blocks per account-year (recent 24 / all 84) | One fewer (fails the rule) | Longest run of losing trades: 8 years / last 24 months | Times N in a row happened in the 8 years, at one unit | If the last 12 and the 9 late starts had to meet the rule too |
|---|---|---|---|---|---|---|
| Gold V3-lite | **6** | 0.00 / 0.14 | 5: 0.88 / 1.21 | 9 / 5 | 1 | 6 |
| Gold Top 1 | **9** | 0.00 / 0.15 | 8: 0.00 / 0.69 | 10 / 6 | 2 | 9 |
| Gold Top 2 | **10** | 0.00 / 0.46 | 9: 0.00 / 0.87 | 14 / 7 | 4 | 10 |
| BTC Top 2 | **8** | 0.12 / 0.30 | 7: 0.12 / 0.82 | 8 / 8 | 3 | 9 |
| BTC Turtle S2 | **5** | 0.00 / 0.14 | 4: 0.58 / 0.45 | 9 / 4 | 1 | 5 |

## 5. The three chosen limits together

Each account type with its own DROP and DAY limits and its two bots' STREAK limits, unblock after 24 hours.

| Account type | Accounts | Blocks per account-year: DROP / DAY / STREAK gold / STREAK BTC | All | Accounts with a block | Trades skipped per account-year | End balance against no breaker: average / worst account / best account | Deepest fall, worst account: with / without | Lowest end balance: with / without |
|---|---|---|---|---|---|---|---|---|
| P1 | recent 24 | 0.17 / 0.00 / 0.00 / 0.12 | **0.29** | 29% | 0.29 | −$23 / −$120 / $0 | 18.5% / 15.9% | $2,307 / $2,307 |
|  | all 84 | 0.37 / 0.00 / 0.46 / 0.30 | **1.13** | 68% | 0.80 | −$7 / −$120 / +$23 | 32.1% / 30.7% | $1,093 / $1,149 |
|  | 8-year account | 0.38 / 0.00 / 0.50 / 0.38 | **1.25** | 100% | 0.62 | −$51 / −$51 / −$51 | 28.8% / 28.8% | $10,943 / $10,995 |
| P2 | recent 24 | 0.33 / 0.46 / 0.00 / 0.00 | **0.67** | 42% | 0.71 | −$114 / −$546 / +$22 | 23.3% / 24.0% | $2,278 / $2,278 |
|  | all 84 | 0.21 / 0.13 / 0.14 / 0.26 | **0.71** | 45% | 0.58 | −$33 / −$546 / +$22 | 23.3% / 24.0% | $1,386 / $1,366 |
|  | 8-year account | 0.25 / 0.12 / 0.12 / 0.38 | **0.88** | 100% | 1.12 | −$1,230 / −$1,230 / −$1,230 | 17.5% / 17.0% | $12,522 / $13,751 |
| P3 | recent 24 | 0.00 / 0.38 / 0.00 / 0.12 | **0.50** | 38% | 0.83 | −$392 / −$1,854 / $0 | 36.8% / 24.4% | $2,455 / $2,455 |
|  | all 84 | 0.18 / 0.11 / 0.10 / 0.30 | **0.67** | 37% | 0.81 | −$113 / −$1,854 / +$45 | 46.7% / 45.1% | $910 / $935 |
|  | 8-year account | 0.12 / 0.00 / 0.12 / 0.38 | **0.62** | 100% | 0.50 | −$109 / −$109 / −$109 | 29.8% / 30.5% | $16,106 / $16,215 |
| P4 | recent 24 | 0.38 / 0.46 / 0.00 / 0.00 | **0.83** | 83% | 0.21 | −$6 / −$33 / $0 | 29.4% / 29.4% | $1,997 / $2,004 |
|  | all 84 | 0.24 / 0.13 / 0.14 / 0.14 | **0.65** | 56% | 0.19 | −$3 / −$33 / +$16 | 30.5% / 29.6% | $1,303 / $1,317 |
|  | 8-year account | 0.00 / 0.12 / 0.12 / 0.12 | **0.38** | 100% | 0.00 | $0 / $0 / $0 | 15.3% / 15.3% | $20,328 / $20,328 |
| P5 | recent 24 | 0.08 / 0.17 / 0.00 / 0.00 | **0.25** | 25% | 0.12 | −$2 / −$56 / +$10 | 21.7% / 20.8% | $2,050 / $2,050 |
|  | all 84 | 0.17 / 0.14 / 0.46 / 0.14 | **0.89** | 55% | 0.35 | $0 / −$56 / +$13 | 31.0% / 31.0% | $1,121 / $1,121 |
|  | 8-year account | 0.12 / 0.00 / 0.50 / 0.12 | **0.75** | 100% | 0.25 | +$36 / +$36 / +$36 | 22.1% / 22.4% | $18,705 / $18,669 |
| P6 (information only) | recent 24 | 0.00 / 0.42 / 0.00 / 0.00 | **0.42** | 38% | 0.42 | −$259 / −$2,066 / $0 | 36.3% / 24.2% | $2,198 / $2,198 |
|  | all 84 | 0.33 / 0.12 / 0.14 / 0.14 | **0.74** | 44% | 0.44 | −$70 / −$2,066 / +$63 | 54.8% / 57.1% | $764 / $743 |
|  | 8-year account | 0.12 / 0.12 / 0.12 / 0.12 | **0.50** | 100% | 0.25 | −$2,766 / −$2,766 / −$2,766 | 27.5% / 27.4% | $19,016 / $21,781 |

*"All" counts a closed trade that reaches two limits at once as one block.*

How long the block lasts (hours until the unblock), recent 24 / all 84 accounts:

| Account type |  | 4 hours | 24 hours | 72 hours | 168 hours |
|---|---|---|---|---|---|
| P1 | blocks per account-year | 0.29 / 1.13 | 0.29 / 1.13 | 0.29 / 1.13 | 0.29 / 1.07 |
|  | average change of the end balance | $0 / $0 | −$23 / −$7 | −$34 / −$9 | −$48 / −$7 |
| P2 | blocks per account-year | 0.67 / 0.71 | 0.67 / 0.71 | 0.62 / 0.71 | 0.62 / 0.70 |
|  | average change of the end balance | −$80 / −$23 | −$114 / −$33 | −$242 / −$69 | −$316 / −$84 |
| P3 | blocks per account-year | 0.50 / 0.65 | 0.50 / 0.67 | 0.46 / 0.65 | 0.46 / 0.62 |
|  | average change of the end balance | $0 / $0 | −$392 / −$113 | −$286 / −$84 | −$312 / −$93 |
| P4 | blocks per account-year | 0.83 / 0.65 | 0.83 / 0.65 | 0.83 / 0.65 | 0.88 / 0.65 |
|  | average change of the end balance | $0 / $0 | −$6 / −$3 | −$161 / −$46 | −$293 / −$84 |
| P5 | blocks per account-year | 0.25 / 0.89 | 0.25 / 0.89 | 0.25 / 0.92 | 0.29 / 0.86 |
|  | average change of the end balance | $0 / $0 | −$2 / $0 | +$1 / +$1 | −$86 / −$19 |
| P6 (information only) | blocks per account-year | 0.42 / 0.77 | 0.42 / 0.74 | 0.42 / 0.79 | 0.38 / 0.67 |
|  | average change of the end balance | $0 / $0 | −$259 / −$70 | −$183 / −$55 | −$161 / −$48 |

*A block of 4 hours skips few trades, in most account types none. After a losing trade the bot that lost waits by itself before its next trade (4 hours for gold Top 1 and BTC Top 2, 12 hours for gold V3-lite and gold Top 2), and a trade that opens at the very moment a block ends is taken. What a 4-hour block can skip is a trade of the other bot.*

When the accounts were started (all three limits on, 24 hours): blocks per account-year by the year of the account's start.

| Account type | 2019 (12 starts) | 2020 (12 starts) | 2021 (12 starts) | 2022 (12 starts) | 2023 (12 starts) | 2024 (12 starts) | 2025 (11 starts) |
|---|---|---|---|---|---|---|---|
| P1 | 1.17 | 1.00 | 2.00 | 2.08 | 0.92 | 0.33 | 0.27 |
| P2 | 0.00 | 0.58 | 1.17 | 1.92 | 0.00 | 0.00 | 1.45 |
| P3 | 0.08 | 0.00 | 1.58 | 1.92 | 0.00 | 0.00 | 1.09 |
| P4 | 0.00 | 0.00 | 1.50 | 1.00 | 0.50 | 0.67 | 1.00 |
| P5 | 1.17 | 0.25 | 1.75 | 1.25 | 1.17 | 0.25 | 0.27 |
| P6 (information only) | 0.08 | 0.00 | 2.00 | 1.50 | 0.67 | 0.00 | 0.91 |

*Every block of the six 8-year accounts, with its date, limit and balance, is in `trips_8y.csv`.*

## 6. Accounts started in the last year of the data

Outside the rule, for information. The latest of the 84 accounts starts on 1 Nov 2025. Here a new $1,500 account also starts on the 1st of every month from Dec 2025 to Aug 2026 and runs to the end of the data (13 Nov 2026): 9 accounts of 3 to 11 months, 5.6 account-years in all. They are the nearest thing in the backtest to an account opened now: one unit, on $1,500, at this year's trade sizes. They share most of their months, so one bad week is counted in several of them.

| Account type | Deepest fall with no breaker, the 9 late starts: middle / worst | The same, recent 24 accounts | Own limits, blocks per account-year: DROP / DAY / STREAK gold / STREAK BTC | All | Different days | Common set (25% / 15%): all blocks per account-year | Different days |
|---|---|---|---|---|---|---|---|
| P1 | 16.7% / 23.6% | 12.3% / 15.9% | 1.98 / 0.00 / 0.00 / 1.44 | **3.42** | 6 | **1.44** | 1 |
| P2 | 22.5% / 27.1% | 13.1% / 24.0% | 3.42 / 2.34 / 0.00 / 0.18 | **5.22** | 11 | **2.34** | 3 |
| P3 | 28.5% / 30.8% | 16.8% / 24.4% | 1.08 / 0.54 / 0.00 / 1.44 | **3.06** | 4 | **3.06** | 4 |
| P4 | 16.5% / 26.2% | 15.3% / 29.4% | 0.18 / 0.54 / 0.00 / 0.00 | **0.54** | 1 | **0.54** | 1 |
| P5 | 16.2% / 20.4% | 15.3% / 20.8% | 0.18 / 0.00 / 0.00 / 0.00 | **0.18** | 1 | **0.00** | 0 |
| P6 (information only) | 23.4% / 25.8% | 22.3% / 24.2% | 0.18 / 0.90 / 0.00 / 0.00 | **1.08** | 4 | **0.72** | 3 |

## 7. One set of limits for every account type

The tightest DROP and DAY values that meet the rule in every one of P1 – P5: **DROP 25%, DAY 15%**, with the STREAK limits of section 4. All three on, unblock after 24 hours:

| Account type | Its own DROP / DAY | Blocks per account-year, own limits | Blocks per account-year, common set | Average change of the end balance, own limits | Average change of the end balance, common set | Deepest fall with the common set, worst of all 84: with / without |
|---|---|---|---|---|---|---|
| P1 | 15% / 7.5% | 0.29 / 1.13 | 0.12 / 0.83 | −$23 / −$7 | −$6 / −$3 | 31.9% / 30.7% |
| P2 | 15% / 7.5% | 0.67 / 0.71 | 0.25 / 0.48 | −$114 / −$33 | −$12 / −$5 | 24.0% / 24.0% |
| P3 | 25% / 15% | 0.50 / 0.67 | 0.50 / 0.67 | −$392 / −$113 | −$392 / −$113 | 46.7% / 45.1% |
| P4 | 20% / 12.5% | 0.83 / 0.65 | 0.38 / 0.45 | −$6 / −$3 | +$2 / $0 | 30.5% / 29.6% |
| P5 | 20% / 10% | 0.25 / 0.89 | 0.00 / 0.70 | −$2 / $0 | $0 / +$1 | 31.0% / 31.0% |
| P6 (information only) | 25% / 12.5% | 0.42 / 0.74 | 0.29 / 0.70 | −$259 / −$70 | −$139 / −$36 | 54.8% / 57.1% |

*Pairs of figures: recent 24 / all 84 accounts.*

## 8. What these numbers cannot tell you

- **Closed trades only.** The breaker, and this replay, see the booked balance. A trade that is deep in loss but still open does not move it. The account's equity, open losses included, can fall further than the figures here.
- **A replay, not a new backtest.** A trade at 2 units is taken to make twice its one-unit profit: exact for the Turtle; for the other four bots the engine itself can differ by cents, and now and then by a trade, when the unit changes (the sizing study measured it). A skipped trade is taken to change no later trade: after an unblock the bot waits for the next recorded trade. A real bot may instead enter late into the move it was kept out of, which matters most for the Turtle, whose trades last weeks.
- **The 12-month accounts are cut out of one 8-year run.** A bot really started on the 1st of a month has no open trade and no pause carried over; here it takes up the 8-year run's next trade.
- **The bots were chosen on this data.** All five were selected on 2021 – 2026. Only Nov 2018 – Dec 2020 was new to them. Losing runs in real trading can be longer than any in the backtest.
- **84 accounts are not 84 independent years.** They are cut from 8 years, and neighbours share 11 of their 12 months.
- **Today's trade sizes are barely tested from a small balance.** Most of the 84 accounts met the small gold trades of 2019 – 2024, and the recent ones had grown before the trades became large. An account that starts at $1,500 now meets them at one unit from the first day. Section 6 is the only evidence on that, and it is less than one year of market.
- **The unblock is taken to come on time.** A real unblock can come sooner or much later than 24 hours. Longer blocks skipped more trades and mostly cost more (section 5).
- **No swap, commission or slippage beyond the spread,** as in the backtests themselves.
- **Limits tighter than the grid were not tried.** Where the chosen value is the tightest of the grid, a tighter one might also have met the rule.

## 9. How the numbers were checked

**The one-unit profit of every trade.** Each bot's 8-year trades were replayed on the study's own account ($2,000, STEP $2,500, whole balance) by the same code that runs the accounts above. The unit came out equal to the recorded one on 4,535 of 4,535 trades, and the closing balance equals the recorded one to the cent:

| Bot | Trades | Published final equity | Rebuilt closing balance | Trades with a different unit | Why the two differ |
|---|---|---|---|---|---|
| Gold V3-lite | 809 | $11,957.34 | $11,957.34 | 0 | no trade open at the end |
| Gold Top 1 | 1,240 | $15,167.68 | $15,246.13 | 0 | a trade of 7 units still open at the end: −$78.45 |
| Gold Top 2 | 1,316 | $8,544.75 | $8,589.58 | 0 | a trade of 4 units still open at the end: −$44.83 |
| BTC Top 2 | 1,110 | $4,148.66 | $4,128.13 | 0 | a trade of 2 units still open at the end: +$20.53 |
| BTC Turtle S2 | 60 | $7,814.72 | $7,814.72 | 0 | no trade open at the end |

The published figure is equity: it includes a trade still open on 13 Nov 2026, which a list of closed trades cannot hold. A run of the bot's own engine over 20 Oct – 13 Nov 2026 at one unit (made once, on 2026-11-21) ended with these trades open: −$11.21 for gold Top 1 and for gold Top 2, +$10.26 for BTC Top 2, none for gold V3-lite. Times the units in the table, those are the differences, to the engine's rounding of a cent or two.

**The first formula was wrong for gold Top 1.** The plan for this calibration took the one-unit profit as profit ÷ (lots ÷ 0.01). The two engines write `lots` differently: the bot's own engine writes the total of all legs, the Turtle's simulator the size of one leg. 672 of Top 1's 1,240 trades have two legs, and the formula halves them: the rebuilt account then ends at $29,584.46 instead of $15,246.13, with a wrong unit on 754 trades. This page uses lots ÷ 0.01 ÷ legs for the four bots of the bot's own engine and lots ÷ 0.01 for the Turtle.

**The earlier one-unit figures.**

| Bot | Earlier: worst stretch 8 years / 24 months / worst trade / net profit / trades (last 24 months) | Here |  |
|---|---|---|---|
| Gold V3-lite | −$394 / −$394 / −$394 / +$2,849 / 198 | −$394 / −$394 / −$394 / +$2,849 / 198 | the same |
| Gold Top 1 | −$660 / −$476 / −$420 / +$4,044 / 301 | −$660 / −$476 / −$420 / +$4,044 / 301 | the same |
| Gold Top 2 | −$335 / −$262 / −$61 / +$2,725 / 325 | −$335 / −$262 / −$61 / +$2,725 / 325 | the same |
| BTC Top 2 | −$370 / −$279 / −$52 / +$853 / 275 | −$370 / −$279 / −$52 / +$853 / 275 | the same |
| BTC Turtle S2 | −$747 / −$696 / −$514 / +$3,763 / 16 | −$397 / −$397 / −$171 / +$1,431 / 16 | the earlier figures divided the Turtle's profit by lots ÷ 0.01 ÷ legs, which left most of its trades at 2 to 4 units |

| Two bots, one unit each, last 24 months: worst losing stretch | Earlier | Here |  |
|---|---|---|---|
| Gold V3-lite + BTC Top 2 | −$461 | −$509 | the earlier figure is on each day's summed profit (−$461); trade by trade, as the breaker sees it, the stretch is deeper |
| Gold V3-lite + BTC Turtle S2 | −$666 | −$394 | the Turtle's division, as above |
| Gold Top 2 + BTC Top 2 | −$360 | −$360 | the same |
| Gold Top 2 + BTC Turtle S2 | −$673 | −$342 | the Turtle's division, as above |
| Gold Top 1 + BTC Top 2 | −$599 | −$599 | the same |
| Gold Top 1 + BTC Turtle S2 | −$912 | −$581 | the Turtle's division, as above |

**The replay itself.** `python3 -m backtesting.research.live_safety check` runs it on seven hand-worked accounts, one for each convention: the sizing steps, a trade that opens on the instant of a block or of an unblock, the day's reference after an unblock, a trade open across a block, two limits reached at once. A second replay, written separately, gave the same result on every one of 9,588 account-and-setting combinations (run once, on 2026-11-21; it is not part of the module).

**One reading that could be made two ways.** After a STREAK block, the unblock restarts that bot's count only; the account's high and the day's reference stay. Restarting those as well would change 9 of 84 accounts at most in any account type, and no limit: the limits are chosen from the runs with one limit on.
