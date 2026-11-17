# More symbols for the bots: silver and the 7 majors. The answer

**Short answer: do not add any of these symbols.** I applied the pre-registered rules (PREREG.md §8) to silver and the majors. They give **N\* = 0**.

**How the rules got there:**
- Of the 42 candidate pairs (7 symbols × 6 designs; GBPUSDm left at the data gate), only 2 qualified on the selection half:
  - USDJPYm with gold Top 2;
  - EURUSDm with BTC Top 2.
- Together, in the confirmation half (2024-05-13 → 2026-11-13, 130.6 weeks) at the volatility-matched lot (b), they **lost $135.67**, which is −$1.04 a week. Their drawdown was $553.05 and their score −0.25.
- The success test needs a profit and a score of at least 1.0. It fails, so the answer is "add none" whatever the rest of the curve shows.
- Adding them to the current six demo bots makes the whole a little worse:

| | Profit a week | Drawdown | Score |
|---|---|---|---|
| The six bots alone | $202.55 | $5,109 | 5.18 |
| The six bots + both qualifiers | $201.51 | $5,131 | 5.13 |

**If you add one anyway:** the best single pair is USDJPYm gold Top 2. In the confirmation half it made **$0.37 a week per $2,000 bot** at lot (b) 0.03 (+$48.41 in total), with a drawdown of $267 (12.5%). That is about 1/90 of what the six bots made together. It also does not pass the success test on its own merit, because its score is only 0.18.

**Your 10 / 15 / 20 options** (silver plus the first 10, 15 or 20 forex pairs) cannot be answered from this run. Only silver and the 7 majors were run, for budget reasons (DEVIATIONS C), and GBPUSDm left at the data gate. That gives at most silver plus 6 forex pairs. The 13 crosses come in a later run.

The closest case available is silver plus the 6 majors, all running gold V3-lite with no selection:
- +$392 over the confirmation half, or **$3.00 a week for 7 bots together** ($0.43 per bot);
- drawdown $2,725 (16.3%), score 0.14.

That is not worth 7 extra terminals.

---

## Where every headline number comes from

In the files below, "line" means the line number in the file, with the header as line 1.

| Number | File | Line / key |
|---|---|---|
| Q = 2 qualifiers, ranks 1 and 2 | `selection.csv` | lines 2 – 3 (`qualified` = True); all 42 ranked |
| N\* = 0, P_Q −$135.67, score −0.2453 | `portfolio_result.json` | `b.success` false, `b.P_Q_profit`, `b.P_Q_score` |
| P_2 conf (b): −$135.67, −$1.04/wk, DD $553.05 (12.83%) | `portfolio_curve.csv` | line 5 |
| P_1 conf (b): +$48.41, $0.37/wk, DD $267.33 (12.49%), score 0.1811 | `portfolio_curve.csv` | line 2 |
| The six bots alone, conf: +$26,446.71, $202.55/wk, DD $5,109.23 (11.93%), score 5.18 | `portfolio_curve.csv` | line 151 |
| The six bots + P_2 (b): $201.51/wk, DD $5,130.79, score 5.128 | `portfolio_curve.csv` | line 155 |
| The six bots + P_1 (b): $202.92/wk, DD $5,157.58, score 5.137 | `portfolio_curve.csv` | line 153 |
| Silver + 6 majors, V3-lite, conf (b): +$392.14, $3.00/wk, DD $2,725.29 | `portfolio_curve.csv` | line 149 |
| USDJPYm gold Top 2, conf (b) +$48.41 (lot 0.03); sel stream +$115.73 | `runs/summary.csv` | lines 331; 335 |
| EURUSDm BTC Top 2, conf (b) −$184.08; sel stream +$108.46 | `runs/summary.csv` | lines 132; 139 |
| Silver Turtle S1 conf (a) / (b) wiped 2026-04-21; stream +$4,940.06 | `runs/summary.csv` | lines 427 – 429 |

**How to recompute everything:**

```
python -m backtesting.research.multiportfolio all
python -m backtesting.research.multiportfolio badtick
```

The module is new (`backtesting/research/multiportfolio.py`). It reads only `runs/`. The base total is the sum of the six (a) confirmation profits in `runs/summary.csv`, lines 436, 446, 456, 66, 79 and 91. They add up to $26,446.71.

---

## 1. Selection half: who qualifies (PREREG §8.3 – 8.4)

**The evidence:**
- Basket designs: 2021-11-13 → 2024-05-13.
- Turtles: 2018-11-13 → 2024-05-13.
- Account: the constant one-unit USD stream. Q5 uses the (b) account.

**How often each test failed** (out of 42):

| Test | Failures |
|---|---|
| Q1 (profit) | 36 |
| Q2 (profit ÷ DD ≥ 1) | 40 |
| Q3 (blocks) | 39 |
| Q4 (trades) | 0 |
| Q5 (lot (b) never wiped, DD ≤ 50%) | 20 |

**The six pairs with a selection-half profit** (`selection.csv` lines 2 – 7):

| Rank | Pair | Weekly Sharpe | Profit (1 unit) | Profit ÷ DD | Positive blocks | Trades | (b) DD | Qualifies |
|---|---|---|---|---|---|---|---|---|
| 1 | USDJPYm gold Top 2 | 0.81 | $115.73 | 1.49 | 7 / 10 quarters | 417 | 9.7% | **yes** |
| 2 | EURUSDm BTC Top 2 | 0.59 | $108.46 | 1.19 | 6 / 10 | 250 | 11.1% | **yes** |
| 3 | USDCHFm gold Top 2 | 0.48 | $72.88 | 0.98 | 6 / 10 | 418 | 9.3% | no (Q2) |
| 4 | USDCHFm BTC Top 2 | 0.33 | $58.26 | 0.57 | 5 / 10 | 264 | 12.9% | no |
| 5 | XAGUSDm Turtle S1 | 0.12 | $517.52 | 0.20 | 5 / 11 half-years | 48 | 73.5% | no |
| 6 | USDJPYm Turtle S2 | 0.07 | $72.86 | 0.17 | 5 / 11 | 31 | 51.9% | no |

The other 36 pairs lost money on the selection half. Every pair on AUDUSDm, NZDUSDm and USDCADm lost.

## 2. Confirmation half: the qualifiers and the curve (§8.5 – 8.6)

**Each qualifier on its own, confirmation half** (`runs/summary.csv`):

| Pair | Account | Lot / unit | Profit | Per week | Max DD | Trades | Win rate | Sharpe | Line |
|---|---|---|---|---|---|---|---|---|---|
| USDJPYm gold Top 2 | (b) | 0.03 | +$48.41 | $0.37 | $307.48 (14.1%) | 419 | 34% | 0.12 | 331 |
| USDJPYm gold Top 2 | (a) | 0.01 | +$16.14 | $0.12 | $102.49 (5.0%) | 419 | 34% | 0.12 | 330 |
| EURUSDm BTC Top 2 | (b) | 0.03 | −$184.08 | −$1.41 | $421.47 (19.7%) | 281 | 42% | −0.41 | 132 |
| EURUSDm BTC Top 2 | (a) | 0.01 | −$61.36 | −$0.47 | $140.49 (6.9%) | 281 | 42% | −0.41 | 130 |

USDJPYm's (a) and (b) accounts are replays of the one-unit run, flagged under DEVIATIONS D.4, because the engine's account there is in yen. The replay error measured on the USD-quoted pairs at these lots is $0.00.

**The portfolios P_N, confirmation half.** The drawdown is that of the summed daily equity. "Worst month" means the worst 13th-to-13th block. The last two columns are correlations of daily P/L: between the members, and with the sum of the six bots (`portfolio_curve.csv`, view `P_N`).

| N | Symbols | (b) profit | (b) per week | (b) DD | (b) score | (a) score | Worst month (b) | Corr. between members | Corr. with the six bots | Sel-half (b) score |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | +$48.41 | $0.37 | $267 (12.5%) | **0.18** | 0.18 | −$62 (Apr 2026) | – | 0.02 | 1.65 |
| 2 = Q | 2 | −$135.67 | −$1.04 | $553 (12.8%) | −0.25 | −0.25 | −$140 (Jan 2025) | 0.19 | 0.07 | **1.88** |
| 3 | 3 | −$784.68 | −$6.01 | $1,006 | −0.78 | −0.78 | −$209 | 0.23 | 0.08 | 1.71 |
| 4 | 3 | −$969.80 | −$7.43 | $1,299 | −0.75 | −0.75 | −$256 | 0.31 | 0.11 | 1.48 |
| 5 | 4 | −$2,969.80 | −$22.74 | $15,042 (68.6%) | −0.20 | −0.16 | −$5,007 (Mar 2026) | 0.21 | 0.15 | 0.41 |
| 10 | 4 | −$4,948.95 | −$37.90 | $16,406 | −0.30 | −0.20 | −$5,288 | 0.23 | 0.15 | 0.30 |
| 15 | 6 | −$5,525.60 | −$42.32 | $30,195 | −0.18 | −0.10 | −$7,629 | 0.19 | 0.16 | −0.44 |
| 20 | 6 | −$7,625.27 | −$58.40 | $32,094 | −0.24 | −0.12 | −$7,912 | 0.20 | 0.15 | −0.66 |
| 42 (all) | 7 | −$5,368.38 | −$41.11 | $37,387 | −0.14 | −0.00 | −$10,596 | 0.15 | 0.29 | −0.93 |

**Reading the curve:**
- **N\* (the best confirmation score within 1 … Q) would be 1**, and no other N is within 10% of it. But the success test on P_Q fails, so the registered answer is **N\* = 0**.
- **N_sel = 2:** the best selection-half score. Its confirmation score is −0.25, which is the unbiased figure.
- No N from 1 to 42 reaches a confirmation score of 1.0. Only N = 1 is positive.
- The jump at N = 5 is silver's Turtle System 1. Its one-unit stream made +$4,940 in the confirmation half. But the unit-rule account, sized up on the 2025 – 26 gains, was **wiped on 2026-04-21** (`runs/summary.csv` lines 427 – 428). The pair had already failed Q2, Q3 and Q5 on the selection half, so the rules kept it out correctly.

**One bot per symbol (§8.7.1; view `K_symbols`, lines 128 – 148):**
- K = 1 and 2 are the same as P_1 and P_2.
- From K = 4 on (silver joins), every K loses $2,800 – $5,300 under (b).
- K\* would be 1 among the symbols with a qualifier, but it does not pass the success test.

**Correlation with the six bots.** The two qualifiers hardly move with the six demo bots: their daily P/L correlation with each of the six is between −0.06 and +0.09 (`correlation.csv`). They would diversify, but they bring almost no return.

## 3. Does adding them help the six bots? (§8.7.3, confirmation half)

The six bots are in the (a) account, 0.01 lot per unit (direct engine runs for the baskets); the new pairs are in (b). View `base_plus_P_N` in `portfolio_curve.csv`:

| | Bots | Profit | Per week | Max DD | DD % | Score | Line |
|---|---|---|---|---|---|---|---|
| The six bots | 6 | $26,446.71 | $202.55 | $5,109.23 | 11.93% | **5.18** | 151 |
| + USDJPYm gold Top 2 | 7 | $26,495.13 | $202.92 | $5,157.58 | 11.48% | 5.14 | 153 |
| + both qualifiers (P_Q) | 8 | $26,311.05 | $201.51 | $5,130.79 | 10.99% | 5.13 | 155 |
| + top 5 | 11 | $23,476.92 | $179.80 | $7,790.11 | 16.76% | 3.01 | 161 |

**The rule's answer (P_N\* = nothing added):** the six bots alone are best on score.
- Adding only USDJPYm raises profit by $0.37 a week and the dollar drawdown by $48. That is a worse score, and it costs one more MT5 terminal.
- The DD % falls slightly only because the account is larger ($14k – $16k instead of $12k), not because the risk is smaller.

## 4. Swap (§9)

**The rates.** I could not get Exness's current swap rates from the web.
- On 2026-11-17 both https://www.exness.com/forex/ and https://exness.jo/en/forex returned HTTP 403 to automated reading.
- A web search found only third-party copies with undated, inconsistent example figures, which are not usable.
- The Help Centre pages cited in PREREG §9 give the schedule but not the rates.
- So, as PREREG §9 foresaw, `swap_rates.csv` has to come from your MT5 terminal: Market Watch → Specification → Swap long / Swap short.

Until then, `swap.csv` gives, for every pair and the six bots (confirmation half, (a) and (b)):
- the lot-nights, long and short, counted at 21:00 / 22:00 UTC with the triple night;
- the **break-even swap**: the charge in points per lot per night, on both sides, that would cut the profit to zero.

**The figures that matter:**
- **USDJPYm gold Top 2:** break-even **6.1 points per lot per night** (0.001 JPY points; `swap.csv` lines 2 – 3).
  - That is about ¥610, or roughly $4, per lot per night.
  - The USD–JPY interest gap alone is worth roughly $10 per lot per night on the paying side. That is my order-of-magnitude estimate, not an Exness rate.
  - So **on a swap-charging account its small profit would very likely turn into a loss.**
- **EURUSDm BTC Top 2:** it loses before swap (n/a).
- **The six bots:** break-even swaps are far above any realistic charge. For example, gold V3-lite breaks even at 5,649 points per lot per night, which is about $565 per lot per night (`swap.csv` lines 86 – 91). Swap would cost them a few percent at most.

**What changes if the account is not swap-free:** none of the conclusions.
- The answer was already "add none". Swap only makes the forex additions worse.
- The six bots keep their ranking.

Exness lists all of these symbols as swap-free by default (PREREG §9). But it can withdraw that status from accounts that hold large positions overnight. The two qualifiers hold overnight on 51% and 73% of their trades (`runs/trade_stats.csv`, conf rows).

## 5. Caveats

1. **Short test, one regime.**
   - The confirmation half is ~2.5 years (130.6 weeks), the selection half for the baskets also ~2.5.
   - Both fall in one broad regime: high US rates, strong gold and BTC trends, a historic 2025 – 26 silver run.
   - The six designs were tuned on gold and BTC in 2023 – 26, the same years as the confirmation half. Their own confirmation figures ($202.55 a week) are therefore optimistic. The new symbols were not tuned at all.
2. **Many candidates.** Among 42 candidates, 2 qualifiers are about what luck alone would produce. Both failed to hold up in the confirmation half, which is consistent with that.
3. **Costs.**
   - The spreads are the archive's Standard-account quotes.
   - There is no extra slippage and no commission.
   - Only `sec` mode was used, with no random loop timing.
   - There is no swap in the base case (§4 above).
4. **A bad quote in the USDJPYm data.**
   - One M1 bar, 2019-04-15 06:28 UTC, has a bid low of 55.920 between closes of 111.94 (half the price). The data gate's decimals test did not catch it.
   - It moved both USDJPYm Turtles' selection-half results. System 1 was stopped out on it: −$500 at one unit, and its (b) account was later wiped, in 2020-11.
   - I re-ran both Turtles in memory with that bar repaired (`usdjpy_badtick.csv`, a sensitivity check that replaces no registered result):
     - System 1 selection stream: +$386.72, profit ÷ DD 0.89, so it still fails Q2;
     - System 2: +$64.14, ratio 0.14, still fails.
   - The confirmation figures are unchanged. **The selection and every conclusion stand.**
   - A scan of all kept M1 stores (≥ 3% jump against the previous close for forex, ≥ 6% for metals) found no other bar like it. Silver's March 2020 and January 2021 jumps, and USDCHF's 2023-12-25 spike, look like real thin-market prints.
5. **USDJPYm's dollar accounts are replays** (DEVIATIONS D.4). The one-unit stream used for selection is exact.
6. **Deploying a non-USD-quoted symbol** (USDJPY, USDCAD, USDCHF, every cross) would need the live bot's P/L conversion fixed first (PREREG §12).
7. **Scope.** Silver plus 6 majors were judged here, not 21 symbols. The 13 crosses could still add qualifiers in the later run. On this evidence, the base rate of forex pairs that survive the confirmation half is low.
