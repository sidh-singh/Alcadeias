# More symbols: silver and the forex pairs. Pre-registration

- **Written and frozen:** 2026-11-16, 21:23 UTC, on `backtest_hedging` at commit `cfa464e`.
- **Status:** written before any strategy had run on any of the new symbols.
- **Frozen:** the sha256 of this file is recorded in the step report.
  - Any later change is a deviation.
  - The report lists each deviation with its reason and its effect.

**The owner's question.** The bots trade gold and BTC today. Would it help to add silver (XAGUSDm) and the top 10, 15 or 20 forex pairs? Which number is best? This study decides the number.

**What has touched the new symbols so far.** None of it is a result.
- HTTP HEAD requests on the Exness archive: availability and file size of every month, 2017-11 to 2026-11, for 29 symbols.
- One calibration month, May 2024, for EURUSDm and XAGUSDm:
  - downloaded and built into a scratch store, only to time the download and the build and to measure the file sizes;
  - then deleted;
  - no indicator and no strategy was computed on it.

**Fixed inputs, which this study never changes:** the six demo designs' settings, and the final ten's results that the gates reproduce.

| File | sha256 |
|---|---|
| `backtest_results/improve/round4/top3_v4_XAUUSDm_designs.json` | `f232c2acd4f1e1c81815dd961a9c2b3c7ca91859678319dd4c16e30e7367f6da` |
| `backtest_results/improve/round4/top3_v4_BTCUSDm_designs.json` | `684254ccadacabeb3c49c998b2164ee3af8482ddc0db23fdca5c5e89b03a7145` |
| `backtest_results/final10/results.csv` (the reproduction targets, §10.1) | `dec071dc7ec8304796f227e752ff03c339f8f7a0ff9ffc7d95b77283766c80ea` |

---

## 1. The symbols

There are 21 new symbols. All are Exness Standard-account (`m`) symbols. Each was found in the archive for all 109 months from 2017-11 to 2026-11 (HTTP 200).

- **Silver:** XAGUSDm, at the owner's request.
- **The 7 majors**, ordered by spot turnover against the US dollar:

  | Major | Spot turnover ($ billion a day) |
  |---|---|
  | EURUSD | 577 |
  | USDJPY | 477 |
  | GBPUSD | 190 |
  | AUDUSD | 155 |
  | USDCAD | 140 |
  | USDCHF | 123 |
  | NZDUSD | 43 |

- **13 crosses:** the 13 most traded of the 21 crosses among the seven non-USD majors (EUR, JPY, GBP, CHF, AUD, CAD, NZD).

**The source of the turnover figures.** All turnover figures in this file come from the BIS Triennial Survey, OTC FX turnover in April 2025, statistical annex, tables 2 – 5 (spot, "net-net" basis, daily averages).

**How the 21 crosses were ranked.**
- The BIS names 8 of the crosses, with their own spot turnover.
- It does not break out the other 13. Their turnover is estimated by a rule fixed here:
  1. Multiply the two currencies' total spot turnover, in $ billion: EUR 837.5, JPY 573.1, GBP 269.2, AUD 205.1, CHF 174.7, CAD 161.7, NZD 56.5.
  2. Then multiply by **0.0787**. That is the median, over the 8 named crosses, of their turnover divided by the same product.

| Rank | Cross | Spot turnover, $ million a day | Source |
|---|---|---|---|
| 1 | EURGBP | 45,422 | BIS |
| 2 | EURJPY | 38,397 | BIS |
| 3 | EURCHF | 34,322 | BIS |
| 4 | AUDJPY | 18,916 | BIS |
| 5 | GBPJPY | 12,139 | estimate |
| 6 | EURAUD | 11,306 | BIS |
| 7 | CHFJPY | 7,878 | estimate |
| 8 | EURCAD | 7,500 | BIS |
| 9 | GBPAUD | 4,344 | estimate |
| 10 | EURNZD | 3,723 | estimate |
| 11 | GBPCHF | 3,700 | estimate |
| 12 | GBPCAD | 3,426 | estimate |
| 13 | CADJPY | 3,200 | BIS |
| reserve 1 | AUDCHF | 2,819 | estimate |
| reserve 2 | AUDCAD | 2,610 | estimate |
| reserve 3 | NZDJPY | 2,505 | BIS |
| reserve 4 | CADCHF | 2,223 | estimate |
| reserve 5 | GBPNZD | 1,197 | estimate |
| reserve 6 | AUDNZD | 911 | estimate |
| reserve 7 | NZDCHF | 776 | estimate |
| reserve 8 | NZDCAD | 719 | estimate |

**The universe** is silver, the 7 majors and the crosses ranked 1 – 13.
- A reserve comes in, in this order, only when a chosen cross fails the data gate (§3.4).
- NZDCHFm has no history before 2021, so it could replace a cross for the basket designs only.
- This rule replaces the example list in the brief. Compared with the first 13 of that list, it takes EURNZD and GBPCAD in place of AUDNZD and NZDJPY.

**Size of the downloads.** Raw zips for the 21 symbols total **15.85 GB**, from the HEAD sizes; 0.46 – 1.07 GB per symbol.

| Months | Zips, all 21 symbols |
|---|---|
| 2017-11 → 2021-04 | 6.42 GB |
| 2021-05 → 2021-10 (warm-up) | 0.51 GB |
| 2021-11 → 2026-11 | 8.92 GB |

The owner asked for "10, 15 or 20". That number is decided in §8, not by this list.

---

## 2. Periods and the split

All times are UTC. Periods are [start, end). The data end, 2026-11-13 00:00, is the final ten's `DATA_END`, so the gold and BTC figures are comparable with it.

| | Basket designs: V3-lite, gold Top 2, gold Top 1 + add, BTC Top 2 | Turtles: System 1 and System 2, each + bot votes |
|---|---|---|
| Indicator history from | 2021-05-01. The engine reads up to about 177 days of M1 before a start | 2017-11-01 |
| **Selection** | **2021-11-13 → 2024-05-13** (130.3 weeks) | **2018-11-13 → 2024-05-13** (286.9 weeks) |
| **Confirmation** | **2024-05-13 → 2026-11-13** (130.6 weeks) | **2024-05-13 → 2026-11-13** |
| Also reported, used by no choice | — | the 8 years 2018-11-13 → 2026-11-13 (the final ten's BTC Turtle window) |

**Each period is a fresh account.**
- Every account starts flat.
- Its indicators are warmed up on the history before its start.
- A unit-rule account starts at $2,000.
- An open position at a period's end is valued at the last price: "final equity", as in the final ten.

**One split date for every pair.**
- The portfolio (§8) adds up accounts of both kinds over the same confirmation half. So the split must be the same instant for every pair.
- Otherwise part of a Turtle's confirmation data would sit inside the portfolio's selection period.
- The Turtles get the longer selection history for two reasons: M1 bars are cheap, and a Turtle trades only about ten times a year.
- This replaces the brief's equal halves of the Turtle's own span (2018-11 – 2022-10 and 2022-11 – 2026-10).

**Why the baskets start in 2021-11.**
- The basket designs need per-second data. V3-lite reads the votes of the bar still forming: with closed-bar votes, gold V3-lite made $2,300 instead of $11,957 over 8 years.
- Five years of per-second data is about 26 GB for the 21 symbols. It fits the disk only one or two symbols at a time (§10.5).
- 2021-11-13 is also the start of the final ten's five-year window.

**The rule.**
- No data dated on or after 2024-05-13 may influence any choice in §§3 – 8.
- Exception 1: the data gate (§3.4) checks the whole span. It reads only whether the data are complete, never any trading result.
- Exception 2: N*, the number the owner's own definition reads off the confirmation half (§8.6). It is reported with its bias.

---

## 3. The symbols' specifications, hours, P/L currency and data gate

### 3.1 Contract specifications

**The source:** the Exness Help Centre, read on 2026-11-16 through its public help-centre API. The Exness website refused automated clients (HTTP 403).

| Help Centre article | Last updated |
|---|---|
| Forex (17854278192284) | 2026-11-13 |
| Commodities (17854173039388) | 2026-11-13 |
| Common trading terms (360014740179) | 2026-10-07 |

**Forex majors and minors:**
- 100,000 units of the base currency per lot;
- 0.01 lot minimum, in steps of 0.01;
- leverage up to 1:2000 (1:Unlimited if eligible);
- market execution on Standard;
- no commission on Standard (commission is charged on Raw Spread and Zero only);
- prices with 5 decimals, or 3 for the JPY-quoted pairs.

**XAGUSD:**
- **5,000 troy ounces per lot (confirmed)**;
- prices with 3 decimals (pip 0.01);
- 0.01 lot minimum;
- leverage 1:Unlimited if eligible; 1:50 – 1:200 during high-margin periods.

**The backtest account.**
- Leverage 1:2000 and stop-out at 0% margin level, as in the final ten.
- No swap in the base case (§9).
- Costs are the archive's own Standard-account bid/ask spread. No other slippage.
- Margin is negligible at these sizes. At 1:2000, ten units of 0.05 lot (above the expected L, §5) need under $40 of margin, against the $22,500 that ten units require. The run step logs the largest margin share as a check.

**Point** = 10^−digits. The Turtle's entry tick is one point (BTC's 0.01 is not used).

**Checking the decimals.** When a symbol's first month is built, its prices must have at most that many decimals, and some prices must use all of them. Otherwise the run stops for that symbol.

| Symbol | Quote currency | P/L to USD (§3.5) | Contract | Digits | One point at 0.01 lot |
|---|---|---|---|---|---|
| EURUSDm | USD | × 1 | 100,000 | 5 | $0.01 |
| XAGUSDm | USD | × 1 | 5,000 oz | 3 | $0.05 |
| USDJPYm | JPY | ÷ USDJPY | 100,000 | 3 | ¥1 |
| GBPUSDm | USD | × 1 | 100,000 | 5 | $0.01 |
| AUDUSDm | USD | × 1 | 100,000 | 5 | $0.01 |
| USDCADm | CAD | ÷ USDCAD | 100,000 | 5 | C$0.01 |
| USDCHFm | CHF | ÷ USDCHF | 100,000 | 5 | CHF 0.01 |
| NZDUSDm | USD | × 1 | 100,000 | 5 | $0.01 |
| EURGBPm | GBP | × GBPUSD | 100,000 | 5 | £0.01 |
| EURJPYm | JPY | ÷ USDJPY | 100,000 | 3 | ¥1 |
| EURCHFm | CHF | ÷ USDCHF | 100,000 | 5 | CHF 0.01 |
| AUDJPYm | JPY | ÷ USDJPY | 100,000 | 3 | ¥1 |
| GBPJPYm | JPY | ÷ USDJPY | 100,000 | 3 | ¥1 |
| EURAUDm | AUD | × AUDUSD | 100,000 | 5 | A$0.01 |
| CHFJPYm | JPY | ÷ USDJPY | 100,000 | 3 | ¥1 |
| EURCADm | CAD | ÷ USDCAD | 100,000 | 5 | C$0.01 |
| GBPAUDm | AUD | × AUDUSD | 100,000 | 5 | A$0.01 |
| EURNZDm | NZD | × NZDUSD | 100,000 | 5 | NZ$0.01 |
| GBPCHFm | CHF | ÷ USDCHF | 100,000 | 5 | CHF 0.01 |
| GBPCADm | CAD | ÷ USDCAD | 100,000 | 5 | C$0.01 |
| CADJPYm | JPY | ÷ USDJPY | 100,000 | 3 | ¥1 |

Reserves follow the same pattern:
- AUDCHF, CADCHF and NZDCHF: CHF-quoted.
- AUDCAD and NZDCAD: CAD-quoted.
- NZDJPY: JPY-quoted.
- GBPNZD and AUDNZD: NZD-quoted.

### 3.2 Trading hours

**The source:** the Exness Help Centre articles "Instrument trading hours" (4405235684498) and "Trading Hours Update: End of US DST, 01 Nov 2026" (31342732737180). Exness servers run on UTC+0.

| Instrument | Opens | Closes | Daily break |
|---|---|---|---|
| Forex | Sunday 21:05 in US summer time, 22:05 in winter | Friday 20:59 in summer, 21:59 in winter | none, Monday – Thursday. The rollover at 21:00 / 22:00 widens spreads, and trading may pause for a few minutes |
| XAGUSD | Sunday 22:05 in summer, 23:05 in winter | Friday 20:58 in summer, 21:58 in winter | Monday – Thursday, 20:58 – 22:01 in summer and 21:58 – 23:01 in winter |

**Holidays:** as the data show.

**The engine needs no schedule.**
- As on gold, it reads closures from the data: an order sent after 30 minutes or more without a quote is refused until quotes return.
- The trading window does the rest (§4).

### 3.3 Data holes

**`data_hole_s = 0` for all 21**, the same setting as gold.
- These markets have real closures: weekends, holidays and silver's daily break.
- So a silence is left alone and never treated as missing history.
- BTC's three-hour rule would close every position and pause entries every weekend.

### 3.4 The data gate

The gate is applied before any design runs on a symbol, and it reads only the data.

**How it is run.**
- `backtesting/data/quality.py` (`quality_report`) runs on two spans:
  - the Turtle span, 2017-11-01 → 2024-05-13;
  - the basket span, 2021-05-01 → 2026-11-13.
- It needs `sec.npz`, so it runs on each span before that span's `sec.npz` files are deleted. If disk is short, it can run one year at a time.

**A symbol fails a span when any of these holds:**
- a month is missing;
- a silence of 8 hours or more starts between Monday 00:00 and Friday 18:00 UTC, unless it covers 25 December, 1 January or Good Friday. This catches holes that `quality.py` would class as a "holiday / long close";
- a full week (Monday – Friday) has fewer than 25% of the symbol's median weekly count of seconds with a quote, other than the weeks of 25 December and 1 January. This catches thin, broken feeds;
- the decimals contradict §3.1.

`quality_report` is saved for every span as the record, whether the symbol passes or fails.

**What happens to a symbol that fails:**
- A chosen cross that fails the basket span is replaced by the next reserve that passes.
- A symbol that fails only the Turtle span keeps its basket designs. Its Turtles are dropped, with no replacement.
- A major or silver that fails is reported and leaves the candidate pool.
  - A major's M1 bars are still used for currency conversion.
  - Where a bar is missing, the conversion uses the last bar before it. The rate is then stale for at most the gap.

### 3.5 Profit currency

Profit is made in the quote currency and converted to USD when each trade closes. Floating P/L in the drawdown is converted at each minute.

**The rate.**
- The rate is the conversion pair's M1 bid close for the minute that contains the time.
- If that minute has no bar, it is the last bar before it.
- For USDJPY, USDCHF and USDCAD the pair is the symbol itself.
- The bid-versus-mid difference is one spread, at most about 0.01%, and is ignored.

**Why the decisions do not change.**
- Targets, stops, add gaps and the cap are distances in price: multiples of the volatility unit, in the same currency.
- So the decisions are the same in any currency.

**What uses USD.**
- the unit rule;
- the USD-denominated settings (§4);
- all reporting.

---

## 4. The six designs on a new symbol

**The settings are the demo branches' design blocks, unchanged.** In the backtester they are the round-4 overrides:

| Design | Overrides |
|---|---|
| **V3-lite** (gold, `demo_hedging_xauusd6`) | H1 votes; both M15 votes agree (`entry_agree_s` 2); H1 trend; target 8 and stop 8 volatility units; 12 h pause after a loss; no adds |
| **Gold Top 2** (`xauusd7`) | H1 votes and H1 trend; target 8 and stop 4 units; unit capped at $12 per 0.01 lot; 12 h pause; no adds |
| **Gold Top 1 + add** (`xauusd8`) | H1 votes and H1 trend; target 10 and stop 8 units; 4 h pause; one add on an M5 MACD turn at least 1 unit from the entry |
| **BTC Top 2** (`btcusd8`) | H1 votes and H1 trend; target 10 and stop 8 units; unit capped at $12 per 0.01 lot; 4 h pause; no adds |
| **BTC Turtle System 2 + bot votes** (`btcusd6`) | 55-day breakout, exit at the 20-day extreme; 2N stop; add every ½N up to 4 legs; entries only when both closed-bar M15 votes agree |
| **BTC Turtle System 1 + bot votes** (`btcusd7`) | 20-day breakout, skipped after a winning breakout, with the 55-day failsafe; exit at the 10-day extreme; otherwise as System 2 |

Every setting not listed stays at the live hedging value, as in the final ten. None of the four basket designs uses the M15 force-close or the Fibonacci ladder. The volatility unit is the EWMA, weight 1/24, of the absolute H1 close-to-close moves.

**Basket designs.**
- They run on the tick engine (`backtesting/engine/fast.py`) in `sec` mode: every second's last quote, one fixed loop timing. This is how the final ten ran its five- and eight-year windows.
- The configuration is the live hedging configuration (`experiments.live_config`) with:
  - the symbol's spec registered at runtime by the new module;
  - the design's overrides;
  - the gold trading window, Monday 01:00 – Friday 22:00 UTC, for all four basket designs on every new symbol.
- **About the window:**
  - It skips the thin Sunday-evening open.
  - It ends after the forex Friday close, so it never binds there.
  - BTC Top 2's 24/7 window would mean nothing on forex.
- The window gates entries only, as on gold.

**Turtles.**
- They run on the M1-bar simulator, with its code unchanged:
  - `external.turtle(m, system)`;
  - the bot-vote filter, `external.filtered(plan, m, sig.votes_at)`;
  - `external.run_path`.
- They are sized with the bot's unit rule, as the final ten's "Turtle + bot votes" and "Turtle [alt] + bot votes".
- The Market is `balke.SpecMarket` with the specs of §3.1.
- **D1 bars** are UTC days. A day with fewer than 360 M1 bars is merged into the next one (`external.day_bars`). So the forex and silver Sunday-evening stub joins Monday.
- There is no trading window, as in the final ten.

**The only USD settings that need translating** are the two $12 caps. Nothing else in the six designs is in dollars: the targets, stops and add gap are in volatility units, and the pauses are in time. The caps are translated by this fixed rule:

1. Let `u` be the H1 volatility unit as the engine defines it: the EWMA of |Δ close| on H1 bid bars built from M1 bars (UTC hours), with α = 1/24 and `adjust=False`. The series starts at the first H1 bar on or after 2021-05-01.
2. `med(S)` is the median of `u` over the H1 bars that close in the selection half [2021-11-13, 2024-05-13). It is computed the same way for XAUUSDm and BTCUSDm from their existing stores.
3. Each cap is set at a price distance, so it stays the same multiple of the symbol's typical unit as it is on the design's own market:

   | Design | Cap on symbol S, in S's price units | The reference |
   |---|---|---|
   | Gold Top 2 | 12.0 × med(S) / med(XAUUSDm) | $12 per 0.01 lot = a $12.00 move in gold |
   | BTC Top 2 | 1,200 × med(S) / med(BTCUSDm) | $12 per 0.01 lot = a $1,200 move in BTC |

4. In each run the engine's `vol_cap_usd_per_unit` = cap in price units × contract × the run's lot per unit. It is stated in the run's account currency: the quote currency in the per-unit runs (§6).

These values, the §5 values and the §3.4 result are written for each symbol to `specs.json`, with a timestamp, before any design runs on that symbol.

---

## 5. Lot per unit

The bot's unit rule is kept: units = floor(balance ÷ 2,500) + 1, at most 10. Each account is reported at two lot sizes:

- **(a) The bot's 0.01 lot per unit.** This is what the bot, as configured, would trade.
- **(b) A volatility-matched lot per unit.** One unit's typical daily USD move equals gold's at 0.01 lot.
  - **The daily move:** D1 bars from `external.day_bars` on the M1 bid bars. Take each bar's |close − previous close| in price, × contract × 0.01, converted to USD at that day's close.
  - G is gold's median daily move over the D1 bars closing in the selection half. Gold's daily move per 0.01 lot is simply |Δ close| in dollars.
  - M(S) is the same median for symbol S.
  - **L(S) = max(0.01, 0.01 × G ÷ M(S), rounded half up to the 0.01-lot step).** For example, 0.034 becomes 0.03 and 0.035 becomes 0.04.
  - L(S) applies to all six designs on S. The base (gold and BTC, §8.7) keeps its demo 0.01.

- **Which one leads the report.** (b) is the headline for the choice of N (§8). The reason: at 0.01 lot a forex unit moves several times fewer dollars than a gold unit, so the forex accounts would hardly matter in dollars. Dollar figures are always reported under both (a) and (b).
- **The choice of pairs barely depends on the lot.** The ranking and Q1 – Q4 use the constant-size stream (§6). Only the risk check Q5 (§8.3) uses (b).

---

## 6. How the accounts are computed

### 6.1 Basket designs: one engine run per design and period, then a replay in USD

**The engine run** for each symbol × design × period:
- `fixed_units = 1`;
- lot 0.01 (`mtqty = 0.01`);
- initial balance 1e9, so margin and stop-out never act;
- the account currency is the quote currency.

It gives each basket's open and close times, side, P/L, positions, lots and MAE (the worst floating P/L seen while it was open, at any second). It also gives the minute equity samples.

**The replay** runs the baskets in order, one at a time. The bot holds one basket per symbol, and the run step checks that no two overlap.
- Each basket's P/L at one unit, in USD = P/L × FX at its close.
- The floating P/L at each minute sample is the sample's equity − balance, × FX at that minute.
- Three accounts are replayed from these:
  1. **The constant-size stream:** always one unit, from $2,000.
  2. **(a):** units u = min(floor(B ÷ 2,500) + 1, 10), set at each basket's open from the closed USD balance B. The P/L and the floating P/L are × u.
  3. **(b):** as (a), × u × L(S) ÷ 0.01.
- An account is **wiped** at its first mark with equity ≤ 0. Its balance becomes 0 and it trades no more.
- **The maximum drawdown** is the largest fall from a previous peak, in USD and in % of that peak. It is the larger of two measures:
  - over the minute equity marks, where the peaks also include the balance after each close;
  - for each basket k, the trough B_k + u_k × MAE_k × FX at its close, against the peak as it stood when the basket opened.
- **Daily equity:** the last mark of each UTC day. A closed market carries its last mark forward.

**Why this is exact.** The unit rule changes only the size of a basket, never a decision. So the replay reproduces a direct run's closed balances, up to the engine's rounding of each position's P/L to the cent.

**The checks** in §10 prove this on gold, EURUSDm and XAGUSDm:
- the same baskets;
- final equity within the rounding bound, $0.01 × Σ over positions of (the position's lots ÷ 0.01);
- drawdown within 1 percentage point of the engine's own per-second drawdown.

**If a drawdown check fails:**
- The replay drawdown is reported everywhere as a range.
- The low end is the method above.
- The high end measures each basket's MAE trough against the peak as it stood at the basket's close.
- The high end is then used for every choice.

### 6.2 Turtles

- `run_path` gives the path at one unit.
- A new account function copies `external._account_kernel`'s bot mode:
  - units set at each trade's entry from the closed balance, the same for all its legs;
  - peaks at minute closes and troughs at each minute's worst price.
- The only differences:
  - k = contract × lot per unit;
  - the P/L is × FX at the exit minute;
  - each minute's mark is × FX at that minute.
- **The check:** with FX = 1 it must reproduce `external.account` to the cent, on BTC and on EURUSDm and XAGUSDm (§10).

---

## 7. What is reported

For each symbol × design × period, under the constant-size stream, (a) and (b):

| Measure | Definition |
|---|---|
| Profit | final equity − $2,000; the final equity includes an open position at the last price |
| Profit per week | profit ÷ the period's length in weeks |
| Maximum drawdown with floating losses | §6, in USD and in % |
| Profit per unit of drawdown | profit ÷ maximum drawdown in USD, with the drawdown floored at $1 |
| Trades | closed trades |
| Win rate | share of closed trades with P/L > 0 |
| Positive months | share of monthly blocks (13th to 13th; 30 per basket period) whose equity rose |
| Positive quarters / half-years | the same, for §8 |
| Wiped | the date, if wiped |
| Largest lot | the biggest position size reached |

For each symbol × design, over all its trades:
- the average and median holding time, in hours;
- **nights held** (§9): per trade, the total, and the share of trades held over at least one night;
- longs and shorts shown separately.

---

## 8. The selection rule

All of §8.1 – 8.5 uses the selection period only.

### 8.1 Candidates

There are **126 pairs**: 21 symbols × 6 designs. A symbol that fails the gate drops out, and reserves step in for crosses only (§3.4). So "126" below means the number of candidates, which is fewer if a major or silver drops out. The base, the six demo pairs on gold and BTC, is not a candidate.

### 8.2 The evidence

| | Basket designs | Turtles |
|---|---|---|
| Period | 2021-11-13 → 2024-05-13 | 2018-11-13 → 2024-05-13 |
| Account | the constant-size USD stream (§6) | the same |

The constant-size stream makes the choice independent of the lot. Q5 below also uses the (b) unit-rule account over the same period.

### 8.3 A pair qualifies when all five hold

| Test | Basket designs | Turtles |
|---|---|---|
| **Q1** | profit > 0 | the same |
| **Q2** | profit ÷ maximum drawdown ≥ 1.0 | the same |
| **Q3** | positive in at least 6 of the 10 quarterly blocks (13 Nov, 13 Feb, 13 May, 13 Aug) | positive in at least 6 of the 11 half-year blocks (from 2018-11-13). A Turtle trades a few times a quarter, so its quarters are mostly noise |
| **Q4** | at least 60 closed trades | at least 25 |
| **Q5** | the (b) account was never wiped, and its maximum drawdown ≤ 50% (the final ten's limit) | the same |

### 8.4 The ranking

- All 126 pairs are ranked by the **annualised Sharpe ratio of weekly P/L** of the evidence stream.
  - The weekly P/L is the change in equity between Saturday 00:00 UTC marks.
  - The annualising factor is √52.18.
- The qualifiers come first, in that order. The other pairs follow, in the same order.
- Ties are broken by Q2's ratio, then by the order of §1 (symbol) and of §4 (design).
- **Why the Sharpe ratio:**
  - It uses every week, not one worst episode.
  - It does not depend on the lot size or on the length of the period.
- **A caveat:** the basket pairs' 130 weeks give noisier estimates than the Turtles' 287. So extreme values, high and low, will come mostly from basket pairs.

### 8.5 The portfolios

- P_N is the top N of the ranking, for N = 1 … 126.
- Each member is a fresh $2,000 unit-rule account.
- The portfolio's equity is the sum of the members' daily equity.
- **The score is profit ÷ maximum drawdown of the summed daily equity, in USD.** Both the profit and the drawdown are also reported, with the drawdown in % of the peak.
- The scores are computed for:
  - the confirmation half, under (b) (the headline) and under (a);
  - the basket selection half, 2021-11-13 → 2024-05-13, under (b), with every member fresh on it, Turtles included.

### 8.6 The best number

1. **The success test comes first.**
   - Q is the number of qualifiers.
   - Under (b) in the confirmation half, P_Q (all the qualifiers together) must make a **profit > 0** with a **score ≥ 1.0**.
   - If Q = 0, or if the test fails, the answer is: **add none of these symbols with these designs (N* = 0)**, whatever the curve shows elsewhere. The curve is still reported.
2. **Otherwise, N\* is the N in 1 … Q with the best confirmation score under (b).** This is the owner's definition of "best number". It is reported with:
   - the whole curve for N = 1 … 126, with the qualified part marked;
   - **the plain alternatives N = 5, 10, 15, 20**;
   - every N whose score is within 10% of the best;
   - N_sel, the N in 1 … Q with the best selection-half score, and N_sel's confirmation score.
3. **Why N_sel is reported.**
   - N* is read off the confirmation half itself, so its own confirmation score is biased upward.
   - N_sel's confirmation score is the unbiased figure.
   - The two are given side by side.
4. **The same is done under (a)**, for information.

### 8.7 The owner's question, in symbols

1. **One bot per symbol.**
   - Each symbol's best pair is its highest-ranked pair.
   - The symbols are ordered by that rank.
   - Their portfolios are K = 1 … 21 symbols, scored as in §8.5.
   - K = 5, 10, 15, 20 are marked.
   - K* is the best K among the symbols with at least one qualified pair.
2. **The additions the owner named, with no selection at all.**
   - Silver plus the first F forex symbols in §1's order (majors first, then crosses by turnover), for F = 10, 15 and 20.
   - Each runs gold V3-lite, the final ten's most dependable design.
3. **The base plus N.**
   - The base is the six demo bots: gold V3-lite, Top 2 and Top 1 + add; BTC Turtle System 2 + votes, Turtle System 1 + votes and Top 2.
   - Each runs at 0.01 lot per unit, fresh on each half, on its own existing data.
   - Report base + P_N for N = 0 … Q, in the confirmation half, with (b) for the new pairs.
   - Report whether base + P_N* beats the base alone on score and on profit per week.

**For every portfolio, the report gives:** profit, profit per week, maximum drawdown (USD and %), score, the number of distinct symbols, and the members.

---

## 9. Swap

The base case has no swap, as in the final ten.

**The Exness rules.** Source: the Exness Help Centre, "About swap" (360014709151, updated 2026-11-14).
- Swap is charged at 21:00 UTC in US summer time and 22:00 UTC in winter, Monday – Friday.
- It is tripled on Wednesday, and on Thursday for USDCAD. It is not charged on Saturday or Sunday.
- **Swap = rate in points × nights × lots × contract × point**, in the quote currency.

**Swap-free status.** Source: "Swap-free status" (4402341895570) and "… (Islamic countries)" (18055079599132).
- All accounts are swap-free by default for a listed set of instruments. The list includes:
  - all 7 majors;
  - every cross here, including the reserves;
  - XAUUSD, XAGUSD and all cryptocurrencies.
- Exness's algorithm can withdraw the status from accounts that "regularly hold large amounts of open orders overnight". Clients from the listed Islamic countries are swap-free unconditionally, and India is not on that list.
- So: no swap is expected while the status holds. The sensitivity shows what happens if it is withdrawn. Bots that hold overnight, above all the Turtles, are the risk to that status.

**The sensitivity:**
1. **Nights:** for every trade, count the swap times t with open < t ≤ close, weighted as above. Count longs and shorts separately, × lots.
2. **Break-even swap**, which needs no rates.
   - Computed for every pair, and for P_N* and the base + P_N*, in the confirmation half under (a) and (b).
   - It is the swap cost, in points per lot per night, charged on both sides, that would cut the profit to zero.
   - "n/a" if the profit is ≤ 0 before swap.
3. **Exness's current rates.**
   - The Exness website refused automated reading on 2026-11-16. The Help Centre has the schedule but not the rates. So the rates must come from the owner's MT5 terminal: Market Watch → right-click the symbol → Specification → "Swap long" and "Swap short", in points.
   - They go into `backtest_results/multisymbol/swap_rates.csv`, with columns symbol, swap_long_points, swap_short_points, date.
   - When that file exists, every pair and portfolio is re-reported with swap: rate × nights × lots × point value, in USD at each trade's close. The swap is applied at the close; its effect on later unit sizes is ignored, a second-order effect.
   - Until then, the report gives the nights and the break-even rates only.

---

## 10. The run step

### 10.1 The gates, before any new symbol is touched

**G1. Reproduce the final ten's five-year window**, 2021-11-13 → 2026-11-13, to the cent, from `results.csv`:

| Design | Final equity | How it is run |
|---|---|---|
| Gold V3-lite | $10,747.58 | tick engine, `sec` mode |
| Gold Top 2 | $8,879.85 | tick engine, `sec` mode |
| Gold Top 1 | $12,433.38 | tick engine, `sec` mode |
| BTC Top 2 | $3,918.63 | tick engine, `sec` mode |
| BTC "Turtle + bot votes" (System 1) | $6,304.88 | M1 simulator, BTC history from 2018-01-01 |
| BTC "Turtle [alt] + bot votes" (System 2) | $3,546.56 | M1 simulator, BTC history from 2018-01-01 |

**G2. Prove the replay on the same window.**
- The four basket designs on their own symbols: the `fixed_units = 1` run plus the replay (a) must reproduce the direct run (§6.1 tolerances).
- The new Turtle account function with FX = 1 must reproduce `external.account` to the cent, for both BTC Turtles.

### 10.2 The base

The six demo pairs run on the two halves, on their existing data. This is the base of §8.7.

### 10.3 The symbols, in this order

**Majors first, because the crosses need the majors' M1 bars for conversion.** EURUSDm and XAGUSDm go first: they are USD-quoted and are the check symbols.

| Order | Symbols |
|---|---|
| 1 – 2 | EURUSDm, XAGUSDm |
| 3 – 8 | USDJPYm, GBPUSDm, AUDUSDm, USDCADm, USDCHFm, NZDUSDm |
| 9 – 21 | EURGBPm, EURJPYm, EURCHFm, AUDJPYm, GBPJPYm, EURAUDm, CHFJPYm, EURCADm, GBPAUDm, EURNZDm, GBPCHFm, GBPCADm, CADJPYm |
| after them | any reserves that are needed |

**For each symbol:**
1. Check free disk (§10.5).
2. Download the 109 monthly zips, 2017-11 → 2026-11, over 4 parallel connections.
3. Build each month with `keep_ticks=False`. Delete each zip once its `meta.json` is written.
4. Run the data gate (§3.4).
5. Delete the `sec.npz` files of the months before 2021-11.
6. Write the symbol's entry in `specs.json`: spec, conversion, med(S), the caps, G, M(S) and L(S).
7. Run the basket designs: 4 designs × 2 halves, one engine run each.
8. Replay each run: the constant-size stream, (a) and (b).
9. Run the Turtles: System 1 and System 2, each on its selection period, its confirmation half, the basket selection half and the 8 years. Each as the constant-size stream, (a) and (b).
10. Save the results.
11. Delete the `sec.npz` files of 2021-11 → 2026-11. The exception: EURUSDm and XAGUSDm keep their full stores until the check step is done.

**G3, after XAGUSDm and before any other symbol.** For EURUSDm and XAGUSDm, all 4 basket designs × 2 halves:
- direct runs under (a) and under (b), with `mtqty = L` and the cap scaled as in §4;
- they must match the replay within §6.1's tolerances;
- the (b) run must have exactly the per-unit run's baskets, which proves that the lot changes no decision;
- the Turtle account with FX = 1 must equal `external.account`.

If G3 fails, stop and report.

### 10.4 The budget

**The calibration month** (EURUSDm and XAGUSDm, May 2024):
- download 7 – 9 s for 5 MB, about 0.6 – 0.7 MB/s on one connection;
- build 2.5 s;
- `sec.npz` 14 – 16 MB (2.8 – 3.1 × the zip), and `m1.npz` 2.3 MB.

**Per symbol:**
- **Target:** about 30 minutes of wall time:
  - download 4 – 8 minutes, at 4 connections, for 0.5 – 1.1 GB;
  - build about 5 minutes;
  - gate and specs 2 minutes;
  - 8 engine runs and the replays 10 – 15 minutes;
  - Turtles about 3 minutes.
- **Hard limit:** 90 minutes. Past it, stop and report. Never skip a symbol silently.
- The next symbol's download may overlap the current symbol's runs.

**Workers:** 2 engine workers while the other job (the step-up study) is running, and up to 5 after it ends.

**The whole run:** gates and base about 1 hour, plus about 7 – 10 hours for the 21 symbols.

### 10.5 Disk

**The limits:**
- Before every download batch, run `df`. Stop if free space minus the batch would fall below **15 GB**.
- Never hold more than about **15 GB** of new market data at once.

**What is kept:**

| Data | Size | What happens to it |
|---|---|---|
| Raw zips | ≤ 1.1 GB per symbol | deleted month by month, so never more than a symbol's worth at once |
| `sec.npz`, 2021-11 → 2026-11 | about 0.6 – 2.0 GB per symbol | held only while the symbol runs |
| `m1.npz` | about 0.25 GB per symbol, 5.3 GB for all 21 | kept: needed for the conversions, the portfolio, the Turtle and the charts |
| EURUSDm and XAGUSDm `sec.npz` | about 2.7 GB together | kept until the check step |

**The peak:** about 5.3 + 2.7 + 2 × 2.0 ≈ **12 GB**, with two symbols in flight. That is under the limit.

### 10.6 The outputs

Everything goes in `backtest_results/multisymbol/`. Nothing is committed.

| File | What it holds |
|---|---|
| `PREREG.md` | this file |
| `specs.json` | §§3 – 5 per symbol, written before that symbol's first design run |
| `quality/<SYM>.json` | the data-gate reports |
| `runs.csv` | every account × measure of §7 |
| `trades_<SYM>.csv.gz` | the trades |
| `daily_<SYM>.csv.gz` | the daily equity of every account |
| `selection.csv` | Q1 – Q5, the Sharpe ratio, the rank and whether the pair qualified |
| `portfolio_curve.csv` | every view of §8.5 – 8.7 |
| `swap.csv` | the swap figures of §9 |
| `checks/` | G1 – G3 |
| `logs/` | the run logs |
| `MULTISYMBOL.md` | the report |

---

## 11. Deviations

- Nothing in §§1 – 9 changes once the first design has run on a new symbol.
- A bug found later is fixed, and everything it touches is rerun. The report lists each fix and its effect.
- A rule that turns out to be impossible to apply is replaced by the nearest rule that can be applied. The report gives the replacement, why, and whether it could have been influenced by results.

## 12. Limits and what deploying would need

1. **Non-USD-quoted symbols need a code change in the live bot before deployment.** This affects 16 of the 21: USDJPY, USDCAD, USDCHF and the 13 crosses. The bot turns price moves into dollars as `trade_contract_size × mtqty` (`app.py`), which is right only when the quote currency is USD.
   - On a JPY, CHF, CAD, GBP, AUD or NZD-quoted symbol, the targets, stops and cap would be off by the exchange rate.
   - A fix would use the terminal's tick value instead.
   - The backtest models the intended price-distance rule.
   - Its `CONTRACT_SIZE_FALLBACK` (`constants.py`) knows only XAU and BTC. It is used only when the terminal reports no contract size.
2. **`turtle.py` needs two changes for forex and silver.**
   - Its `TURTLE_TICK = 0.01` is BTC's; it must be one point.
   - It reads the terminal's UTC D1 bars, where the Sunday-evening stub is a bar of its own. The backtest merges it into Monday, and the live bot would need the same merge.
3. **Every new symbol needs its own setup:** a trading window in its branch's `symbols.json` and its own MT5 terminal (one per slot).
4. **Only `sec` mode is used.** There is no raw-tick re-run with random loop timings: no ticks are stored, to save disk.
5. **The designs were tuned on gold and BTC in 2023 – 2026**, the same calendar years as the confirmation half. No setting is tuned on any new symbol. The only symbol-specific values are the specs, L(S) and the translated caps, all from the formulas above.
6. **There are 126 candidates, so false positives are expected.** The confirmation half is the test, and N* is optimistic (§8.6).
7. **There is no swap in the base case** (§9). The spreads are the archive's Standard-account quotes, with no slippage beyond them.
