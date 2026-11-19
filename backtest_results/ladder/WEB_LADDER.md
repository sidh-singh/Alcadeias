# WEB_LADDER: what practitioners and research say about DCA, grid and martingale ladders

Survey date: 2026-11-18. Written for the ladder search on XAUUSDm and BTCUSDm. Each claim carries a
credibility grade:

- **A**: peer-reviewed, or a mathematical result you can check yourself.
- **B**: a working paper, or a test whose method and costs are published.
- **C**: practitioner rules with code or settings but no independent check.
- **D**: vendor marketing or forum anecdote. Kept only to reject it, or as a design idea with no evidence.

Lines marked *(derived)* are my own arithmetic on the repo's contract specs (`backtesting/config.py`), not
claims from a source.

---

## 1. Bottom line

1. **No source shows a leveraged, unstopped averaging-down ladder that survives a long sample after
   costs.** Taranto & Khan (A/B) prove that a grid without a stop is ruined almost surely once a trend
   lasts long enough. Chen et al. (B) show a plain grid has an expected value of about zero, and fees make
   it negative. Martingale sizing is a plain gambler's-ruin problem (A).
2. **Where "DCA works", the conditions differ from the live bot:**
   - the account is spot and unleveraged, or the full ladder is paid for up front;
   - it trades long only, in an asset with positive drift (BTC in 2016-2024, gold in 2019-2026);
   - the ladder has a fixed number of steps spaced by price, not by time or oscillator;
   - or a stop or reset ends the cycle.

   The one ladder in this survey with published, positive results is Chen et al.'s Dynamic Grid. It is a
   spot BTC/ETH grid that resets when price leaves its range, keeps the coins, and never takes leverage.
   It still drew down about 50% in ETH's 80% fall.
3. **What decides whether a ladder survives, in order of weight in the sources:**
   - total exposure at full depth, measured against the account (this is the whole martingale problem);
   - a hard end to the cycle, by equity stop, time stop or weekend flat;
   - step spacing that grows with volatility;
   - a trend or regime gate;
   - the multiplier shape. It matters, but less than the four points above.
4. **Indicator evidence on crypto, net of costs:** mean-reversion oscillators (RSI, Stochastic, Bollinger
   reversion, Connors RSI-2) come out **net-negative**, and trend rules (ADX, Bollinger breakout, MACD
   momentum, Donchian/moving average) come out slightly positive. A ladder is a mean-reversion bet. Pairing
   RSI with a second oscillator adds little because the oscillators are highly correlated. A trend or
   regime filter is the pairing with the best support.
5. **Most credible pro-ladder market fact:** BTC hourly returns show significant *negative*
   autocorrelation at 1, 2 and 4 hours, and larger moves reverse more (De Nicola 2021, B). Two other
   papers find intraday *momentum*, especially on days with abnormal moves (Caporale & Plastun 2020;
   Shen, Urquhart & Wang 2022). A BTC ladder therefore has a plausible edge at H1-H4 on ordinary days and
   should be switched off on abnormal-move days. I found no rigorous intraday study for gold. The repo's
   earlier finding (gold leads silver by about a minute, intraday moves close to random) is the best
   evidence available for gold.

---

## 2. Sources and what each one is worth

| # | Source | Type | Grade | What it gives us |
|---|---|---|---|---|
| S1 | Taranto & Khan, "Gambler's ruin problem and bi-directional grid constrained trading and investment strategies", *Risk Governance & Control* 10(3), 2020, and a companion paper in *Investment Management & Financial Innovations* 2020/3 ([USQ record](https://research.usq.edu.au/item/q5x02/gambler-s-ruin-problem-and-bi-directional-grid-constrained-trading-and-investment-strategies), [PDF](https://research.usq.edu.au/download/349e694dc633476c44d53edfe21d883ce283789fb6eab4a0b900f1d05f6b8f17/1074119/IMFI_2020_03_Taranto.pdf)) | peer-reviewed theory | A/B | A grid can win over short horizons but is ruined almost surely as a trend continues. Flat-lot grid loss grows as n(n+1)/2 per adverse level; martingale loss as 2^n. Drift and volatility dominate the outcome. |
| S2 | MQL5 article 21833, "Building a research-grounded grid EA ... what Taranto proved" ([link](https://www.mql5.com/en/articles/21833)) | practitioner with code | C | Turns S1 into EA rules: D1-ATR spacing (×0.12, roughly 10-15% of the average daily range), a 72 h cycle cap, an equity kill switch from cycle-start equity, a CUSUM trend gate before a cycle starts, Friday flat close. The author's XAUUSD depth sweep (6 weeks of 2026, M1 real ticks) gave PF 0.71 to 5.36, depending on depth, with no pattern. A single kill-switch event erased the depth-5 run. Too short to trust; it does show how fragile the results are to depth. |
| S3 | Chen, Chen & Jang, "Dynamic Grid Trading Strategy: From Zero Expectation to Market Outperformance", arXiv 2506.11921, 2025 ([html](https://arxiv.org/html/2506.11921)) | working paper, code public | B | A plain grid's EV is 0 under a symmetric walk. With fees, a grid of n levels needs more than n²/8 − n/4 round trips to come out positive. DGT resets the grid when price leaves the range. Data: BTC/ETH spot, 1-minute, 2021-01 to 2024-07, 0.08% fee. IRR "up to 60-70%". ETH drawdown about 50% while ETH fell 80%. Spot only. |
| S4 | Hudson & Urquhart, "Technical trading and cryptocurrencies", *Annals of OR* 2021 ([Springer](https://link.springer.com/article/10.1007/s10479-019-03357-1)) | peer-reviewed | A | 14,919 rules in 5 families; significant predictability on daily crypto after bootstrap and data-snooping corrections. Break-even costs above typical crypto costs. The rules are mostly trend-type. |
| S5 | Deprez & Frömmel, "Are simple technical trading rules profitable in bitcoin markets?", *Int. Rev. Econ. & Fin.* 2024 ([IDEAS](https://ideas.repec.org/a/eee/reveco/v93y2024ipbp858-874.html)) | peer-reviewed | A | 75,360 rules under stricter tests; some still beat buy-and-hold out of sample, mainly on risk-adjusted terms. |
| S6 | De Nicola, "On the intraday behavior of Bitcoin", *Ledger* 6, 2021 ([LMU](https://epub.ub.uni-muenchen.de/97651/)) | peer-reviewed | B | Significant **negative** first-order autocorrelation of BTC returns at 1 h, 2 h and 4 h (mean reversion). Larger moves reverse more strongly. Costs not reported in the abstract. |
| S7 | Caporale & Plastun, "Momentum effects in the cryptocurrency market after one-day abnormal returns", *FMPM* 34, 2020 ([Springer](https://link.springer.com/doi/10.1007/s11408-020-00357-1)) | peer-reviewed | A | Hourly BTC/ETH/LTC data, 2015-2019. Momentum on abnormal-move days and the day after, except a contrarian effect after BTC's positive abnormal days. |
| S8 | Shen, Urquhart & Wang, "Bitcoin intraday time-series momentum", *Financial Review* 57(2), 2022 ([Reading](https://centaur.reading.ac.uk/100181)) | peer-reviewed | A | Intraday momentum in BTC driven by liquidity provision; the first half-hour predicts the last. Strongest in downturns. |
| S9 | Kaminski & Lo, "When do stop-loss rules stop losses?", *J. Financial Markets* 2014 ([MIT PDF](https://dspace.mit.edu/bitstream/handle/1721.1/114876/Lo_When%20Do%20Stop-Loss.pdf)) | peer-reviewed | A | Under a random walk a stop only lowers expected return. With momentum or regime switching, a stop adds value. Our worst losses come from trends, which is the momentum case, so a basket stop should help most exactly there. |
| S10 | Harvey et al., "The impact of volatility targeting", *JPM* 2018 ([Duke PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf)) | peer-reviewed | A | Over 60+ assets, scaling exposure by inverse volatility consistently cuts extreme returns and maximum drawdowns. Sharpe gains only in risk assets. Supports sizing the unit by volatility rather than by balance alone. |
| S11 | Urquhart et al., high-frequency MA rules on gold and silver, 2015 ([PDF](https://c.mql5.com/forextsd/forum/174/does_technical_analysis_beat_the_market__evidence_from_high_frequency_trading_in_gold_and_silver.pdf); [CXO summary](https://www.cxoadvisory.com/technical-trading/high-frequency-technical-trading-of-gold-and-silver/)) | peer-reviewed | B | 5-minute gold: in-sample-best SMA rules stay profitable out of sample *before costs*; silver's do not. "Possible but not easy." |
| S12 | "We graded 13 famous trading strategies on 6 years of data" ([dev.to](https://dev.to/tessen/we-graded-13-famous-trading-strategies-on-6-years-of-data-all-13-failed-26o4)) | practitioner, method described, costs modelled | C | Out of sample, net of fees and slippage, 10+ crypto pairs. Per trade: ADX trend +10.7 bp, Bollinger breakout +3.8, MACD momentum +3.5, Connors RSI-2 −3.7, Bollinger reversion −9.7, Stochastic reversion −13.5, RSI reversion −19.8, dip buyer −28.3. |
| S13 | Connors RSI(2) rules and recent replications ([MQL5 17636](https://www.mql5.com/en/articles/17636); [Backtrex S&P](https://backtrex.com/en/backtests/connors-rsi-2-sp-500)) | practitioner | C | Buy when RSI(2) < 5 and close > SMA200; exit when close > SMA5. 71% win rate but 1.7% CAGR against 13.5% buy-and-hold over 2016-2026, with a worse average loss than average win. The textbook "win often, lose big" shape. |
| S14 | 3Commas / Gainium DCA "safety order" mechanics ([3Commas blog](https://3commas.io/blog/dca-bots-creating-a-dca-bot-using-a-built-in-technical-analysis-indicator); [Gainium calculator](https://gainium.io/tools/dca-calculator)) | vendor docs | C (mechanics) / D (performance) | The standard crypto DCA design: first deviation about 1.5-2%; *step scale* multiplies each next gap (geometric spacing); *volume scale* multiplies each next size; a fixed number of orders with capital reserved for all of them; take-profit measured from the average price. The mechanics are useful. No performance evidence. |
| S15 | Turtle rules (Faith/Covel summaries; [MQL5 23448](https://www.mql5.com/en/articles/23448)) | practitioner, rules public | C | The opposite of averaging down. Add a unit every 0.5 N (ATR20) *in favour*, at most 4-5 units, with a 2 N stop that moves up with each add. The repo's earlier finding that "only Turtle earns on BTC" fits this. |
| S16 | Grid "overlap" or exposure reduction: close the oldest loser with the newest winners ([forexsb forum](https://forexsb.com/forum/post/83100); [SmartChoise manual](https://smartchoise.gitbook.io/smartchoise-manual/options/exposure-reduction)) | practitioner / vendor | C/D | Close the first (worst) leg, fully or in part, once the newest legs' profit covers it. One user reports lower drawdown; the vendor says outright that there is no guarantee. |
| S17 | Zone recovery / "no-loss" hedge ([TradingHeroes review](https://www.tradingheroes.com/?p=1023354); [babypips thread](https://forums.babypips.com/t/zone-recovery-strategy/703488)) | practitioner | C/D | Opposite-side trades, each larger than the last, at fixed zone edges. This is a martingale in disguise: it loses in a whipsaw, where a pure grid loses in a trend. |
| S18 | Gold rollover and spread windows ([MQL5 gold sessions](https://www.mql5.com/en/blogs/post/773690); [IC Markets rollover](https://www.icmarkets.com/blog/wp-json/wp/v2/posts/5983)) | practitioner/broker | C | Spreads widen about ±30 minutes around 17:00 New York (the CME 60-minute clearing break). Advice: block new grid orders in that window. |
| S19 | Martingale-EA blow-up talk on Myfxbook/MQL5 ([Myfxbook](https://myfxbook.com/community/new-traders/fallacy-martingalegrid-systems/3130769,1); [MQL5 forum 512226](https://www.mql5.com/en/forum/512226)) | forum | D | "90% blow up" has no source. The useful part is the warning signs: short account life, a smooth equity curve, lot size rising with drawdown. |
| R1 | Yodacom "grid walk-forward, 13 years of crypto" ([page](https://yodacom-site.pages.dev/research/grid-trading-walk-forward-2026)) | company page | **rejected** | Withdrawn in Oct 2026; the numbers were removed while the simulator is rebuilt. |
| R2 | DCAUT / Altrady "DCA bot survives crashes" posts ([Altrady](https://www.altrady.com/blog/crypto-trading-strategies/bitcoin-flash-crash-may-2026-analysis)) | vendor | **rejected** | Sells the product; no rules, no out-of-sample test. |
| R3 | MQL5 Market grid EAs (ProTrade Smart Grid, Falcon Grid, Apex Grid Guardian ...) | vendor | **rejected as evidence** | Their *input lists* are a useful catalogue of controls (ATR spacing, maximum levels, equity stop, daily loss lock). Their performance claims are marketing. |
| R4 | "Never-lose / 100% win-rate" hedging and martingale signals | vendor | **rejected** | A high win rate with increasing lot size is the signature of S19. |

Off-topic note: "DCA" in investing (fixed monthly buys) is a different thing. Vanguard's 2012 study
*Dollar-cost averaging just means taking risk later* found that lump-sum investing beat DCA about two-thirds
of the time. I quote it from memory and did not re-fetch it (grade B). It also has nothing to do with
leveraged averaging down.

---

## 3. How the ladder families are built, and their exposure *(derived where marked)*

Notation: sizes are in units of 0.01 lot × `unit`. Gold: 0.01 lot = 1 oz, so 1 unit of size loses $1 per $1
of gold move. BTC: 0.01 lot = 0.01 BTC, so 1 unit of size loses $1 per $100 of BTC move.

| Shape (sizes) | Total size after k fills | Loss after an adverse move of n equal steps g (all levels filled) | Notes |
|---|---|---|---|
| Flat (1,1,1,...) | k | g·n(n+1)/2 (S1: triangular) | the shape Taranto calls "engineerable" |
| +1 (1,2,3,4,...) | k(k+1)/2 | g·Σ i(n−i+1) ≈ g·n³/6 | cubic growth |
| Fibonacci (1,2,3,5,8,13), live | 32 after 6 fills | about φ^n | the live ladder |
| Doubling (1,2,4,8,16,...) | 2^k − 1 | about g·2^(n+1) | classic martingale |

*(derived)* **The live ladder at full depth.** Six fills of 1+2+3+5+8+13 = 32 size units, at unit 1:

- **Gold:** about $32 per $1 move. A $60 adverse day costs about $1,900, which is the whole $2,000 start.
- **BTC:** about $32 per $100 move. A $5,000 adverse day costs about $1,600.

With unit 10 (balance ≥ $22,500) both figures are ten times larger. **The live ladder also has no price
spacing.** The tier condition is "RSI of TF n ≤ 35". In a fast fall M1, M5, M15, H1 and H4 RSI can all be
oversold within the same hour, so all six fills can land within a small price range. The basket then
carries full size with almost no averaging benefit, and the only exits left are the force-close and the H6
final close. That is close to doubling-down, all at once.

**What the "working" practitioner ladders have that the live one lacks (S2, S3, S14):**

1. A fixed number of orders, with capital reserved for every one of them before the first order is placed.
2. Steps set by *price distance* (a percentage or a multiple of ATR), often widening (step scale > 1).
3. A take-profit measured from the *average price*, not a fixed dollar amount per unit.
4. A hard end to the cycle: equity kill switch, maximum hours, Friday flat, or a range reset (S3).
5. A gate that stops a new cycle from starting in a confirmed trend (CUSUM, ADX, moving-average slope).

---

## 4. When ladders work and why they blow up

**They work when the price path is mean-reverting at the step scale, and the account can carry the
worst excursion of the test period.**

- S1: equity variance grows with time in the cycle, roughly as exp(4v²σ²t/g²). Long cycles are the
  dangerous ones, which is the case for a time stop.
- S6: BTC at 1-4 h is the strongest published case of reversion at a horizon a ladder can trade.
- S3: on BTC/ETH spot, reversion inside a range paid the fees at a 0.08% cost. A grid needs more than
  n²/8 round trips to beat fees, so wide spacing and few levels are better than many narrow ones.

**They blow up through:**

- **Trends.** S1 proves ruin under persistent drift. S7 and S8 show that crypto trends are strongest on
  abnormal-move days, exactly when an RSI ladder fills deepest.
- **Leverage and stop-out.** The Exness Standard account stops out at 0% margin level (repo config), so
  the account dies when equity reaches zero.
- **Gaps and illiquid windows.** The daily rollover break (S18) and weekend closes for gold; liquidation
  cascades for BTC.
  - For BTC, Oct 2025 is reported as a ~9% fall with ~$19B liquidated. That figure is from vendor
    reporting (grade D, magnitude only). Mar 2020 (about −40% in a day) is common knowledge and I did not
    re-fetch it.
  - I found no sourced study of gold weekend gaps. The repo's own tick store is the better source for
    that.
- **Costs.** S3's n²/8 bound; S12, where every crypto mean-reversion rule is gross-positive or near zero
  but net-negative; and the repo's silver study, where everything that made money before costs lost after
  them.
- **Path dependence in sizing.** Re-deriving the unit from the balance after wins raises the size just
  before the drawdown that kills the account. This is the sizing study's finding, and S10's
  volatility-targeting argument points the same way.

---

## 5. Risk controls: evidence and exact codeable rules

Each rule is written to drop straight into the engine. The levers already in `BacktestConfig` are named;
**NEW** marks code that does not exist yet.

| Control | Evidence | Exact rule | Engine lever |
|---|---|---|---|
| **Maximum depth** | S1 (loss grows with depth, collapse near a threshold), S2 (depth sweep fragile) | at most K adds, K ∈ {2, 3, 4}; at full depth only closes are allowed | `max_adds` |
| **Price spacing by ATR** | S1/S2: 10-15% of the average daily range (D1 ATR × 0.12) was optimal for forex. S14: geometric step | add i is allowed only if price is ≥ gap_i below the last fill (buy), with gap_i = m · ATR(TF, 14) · s^(i−1). Grid: m ∈ {0.5, 1, 2} on H1 ATR, or 0.12 on D1 ATR; s ∈ {1, 1.5, 2} | `ladder_gap_vol` + `vol_tf` (s = 1); **NEW** step scale s |
| **Pre-funded sizing (the key fix)** | S14 (capital reserved for all orders); S1 | choose `unit` so that the loss with the ladder full, at its last fill price minus a further X · ATR_D1 (X = 1.5), is ≤ R × balance (R = 30%). That is `unit = floor(R·balance / worst_loss_per_unit)`. With this rule the ladder shape sets the *unit*, not the risk | **NEW** (`fixed_units` gives a crude stand-in) |
| **Basket equity stop** | S9 (stops add value under momentum and regime switching); S2 kill switch | close everything when the basket's floating loss ≥ L. L = c × ATR_H4 × total open size, c ∈ {2, 3, 4}; or a fixed share of cycle-start equity (10-25%) | `stop_vol` / `stop_loss_usd_per_unit`; **NEW** %-of-equity |
| **Time stop** | S1 (variance grows with time); S2 (72 h cap) | close the basket after T hours, T ∈ {24, 72, 168} | `max_hold_s` |
| **Friday flat / no weekend hold** (gold) | S2; gaps | close all at Fri 20:00 UTC; no new cycle until Mon 01:00 | `window_end_min` (blocks entries only); **NEW** forced flat |
| **Rollover block** (gold) | S18 | no entry or add from 20:30 to 22:30 UTC (17:00 NY ±30 min, plus the CME hour) | `entry_hours_utc` (entries only); **NEW** for adds |
| **Trend / regime gate before a cycle starts** | S1/S2 (CUSUM gate); S12 (ADX trend works, so ADX high means do not fade) | start a buy cycle only if ADX(14, H4) < 20-25, *or* price is above EMA200(D1) (Connors-style "buy dips in an uptrend"); start no counter-trend cycle | `trend_tf` / `trend_mode`; **NEW** ADX |
| **Pause adds in a strong trend** | S7 (momentum on abnormal days), S8 | block adds while \|today's return\| > 2 × the mean absolute D1 return over 20 days, or while ADX(H1) > 30 and rising | **NEW** |
| **Target from the average price** | S14 | close when bid ≥ average entry + τ · ATR_H1 (τ ∈ {0.3, 0.5, 1}) instead of +$1 × unit | `target_vol`; `target_per_lot` |
| **Smaller target when deep** | design (S14 sets the take-profit from the average price) | target_k = target_0 / k at depth k, or the break-even price plus spread | **NEW** |
| **Partial close / overlap** | S16 (weak) | when the newest leg's profit ≥ the oldest leg's loss + $δ, close both; repeat | **NEW** |
| **Daily loss lock** | R3 input lists (no evidence) | no new cycle for the rest of the UTC day after the day's realised loss ≥ D | `daily_loss_limit_usd_per_unit` |
| **Volatility-targeted unit** | S10 (A) | unit = clamp(round(k · balance / (ATR_D1 · contract)), 1, 10) | `vol_cap_usd_per_unit` (partial); **NEW** |
| **Range-reset grid** | S3 (B, spot) | define a range [P0 − N·g, P0 + N·g]. If price leaves it upward, close all and recentre. If it leaves downward: *spot* keeps the coins; *leveraged* must take the stop, since we cannot hold without margin | **NEW** |

How much evidence the shape choice has: S1 is the only rigorous comparison, flat against doubling. Flat
ladders lose more slowly (triangular against exponential) but are not safe. I found nothing that ranks +1
against Fibonacci; both lie between flat and doubling. Expect shape to matter only once depth and stop are
fixed.

---

## 6. Indicators to pair with RSI on gold and BTC

| Pairing | Role | Evidence | Codeable rule | Verdict |
|---|---|---|---|---|
| RSI + long trend filter (EMA/SMA200 on D1, or EMA50 on H4) | entry and ladder side | S13 (Connors), S4/S5 (trend rules work on crypto) | buy ladders only when close > EMA200(D1); sell ladders only when below | **best supported**; test first |
| RSI + ADX | regime gate | S12 (+10.7 bp ADX trend, the best of 13); practitioner rule ADX < 20 → grid, > 25 → trend (C) | open a counter-trend cycle only if ADX(14, H1 or H4) < 20; block adds if ADX > 30 | **test** |
| RSI + Supertrend (ATR 10, ×3) or Donchian(20) | trend side or no-trade | repo's silver near-miss (H4 Supertrend); Turtle (S15); no outside test of Supertrend+RSI | ladder only in the Supertrend direction (buy dips while Supertrend is up on H4) | test as a side filter |
| RSI + Bollinger %B or z-score / distance from MA in ATR | ladder *trigger* and spacing | S12: Bollinger reversion −9.7 bp net; S6 (bigger BTC moves revert more) | add when (close − EMA20)/ATR14 ≤ −k, k ∈ {1.5, 2, 2.5, 3}, on the tier TF | **best trigger candidate**, because it scales with price distance |
| RSI + Stochastic(14, 3, 3) / Williams %R / CCI(20) | second oscillator | S12: Stochastic reversion −13.5 bp. These are near-collinear with RSI(14) (all measure the close's position in a recent range) | %K < 20 together with RSI < 35 | low value; test only as a trigger alternative (owner's point 7) |
| RSI + MACD histogram turn | trigger | S12: MACD *momentum* +3.5 bp (trend use, not reversion) | add only once the MACD histogram on the tier TF has turned up (the fall is slowing) | test: "wait for the turn" cuts the knife-catch |
| RSI + VWAP (session/daily, BTC) | intraday anchor | none rigorous found (D) | add only below VWAP − k·σ_VWAP | low priority |
| RSI + abnormal-day filter | ladder pause | S7 (A) | block counter-trend adds on days with \|return\| > 2× the 20-day mean \|return\| | **test** (cheap) |
| RSI + volatility regime (ATR percentile) | sizing / pause | S10 (A) | unit × min(1, ATR_med / ATR_now); no new cycle if ATR(H4) is above its 90th percentile over 100 days | **test** |

On the entry timeframes ({H4, M5} against {H1, M15}, with D1 added): no source speaks to multi-timeframe
RSI/MACD slope votes. The only relevant outside evidence is that daily-level trend information carries
the most out-of-sample value on crypto (S4, S5). So "add D1" is best tested as a **trend side filter**,
not as one more equal vote.

---

## 7. Claims rejected

- "Grids and martingales never lose if you have enough capital": S1 proves ruin almost surely under
  persistent drift, and the capital needed grows without bound.
- "Zone recovery / hedging is no-loss" (S17): a hedged position at equal size has zero net exposure, so the
  basket only recovers through *larger* opposite legs. That is a martingale on whipsaws.
- Win rate as proof (S13, S19): a 70-95% win rate with losses larger than wins is exactly the failure shape.
- Vendor equity curves (R1-R4): no rules, no costs, no out-of-sample test, or withdrawn.
- "DCA beats the market" (investing sense): it is a different strategy, and even there lump sum usually wins.

---

## 8. Ladder ideas worth testing beyond the owner's nine points

Ordered by how strongly the evidence supports them and how cheaply they can be built. Every one must be
judged net of the repo's recorded spreads, on the existing one-account long windows and fresh-$2,000
quarters.

1. **Pre-funded unit (risk budget for the full ladder).** Unit chosen so that full depth plus 1.5 ATR_D1
   of further adverse move costs ≤ 30% of the balance (S14, S1). This is the one change that addresses
   *why* the account is wiped, rather than how often.
2. **ATR price spacing with a geometric step (3Commas-style)** on top of the RSI tier condition: add i
   needs RSI ≤ 35 *and* a fall of ≥ m·ATR·s^(i−1) since the last fill. Use m ∈ {0.5, 1, 2} on H1 ATR
   and s ∈ {1, 1.5, 2} (S2, S14). `ladder_gap_vol` already covers s = 1.
3. **Average-price take-profit:** close at average entry + τ·ATR_H1, replacing +$1/unit (S14).
   `target_vol`, `target_per_lot`.
4. **Hard cycle end:** equity stop at c·ATR_H4 × total size (c ∈ {2, 3, 4}) **plus** a time stop
   T ∈ {24, 72} h (S1, S2, S9).
5. **Trend-side ladder (Connors framing):** only buy ladders above EMA200(D1) and only sell ladders below
   it. Optionally also require ADX(H4) < 25 at cycle start (S4, S12, S13).
6. **Abnormal-day pause:** no adds against today's move when \|D1 return so far\| > 2× its 20-day mean
   (S7). BTC first.
7. **Distance-from-mean trigger:** (close − EMA20)/ATR14 ≤ −k on the tier TF, as the ladder trigger,
   replacing RSI ≤ 35. It is the trigger that links fills to price distance (S6: bigger moves revert more).
8. **"Wait for the turn" adds:** an add needs the RSI condition *and* a MACD histogram (or RSI) uptick on
   the tier TF, so the bot buys after the fall slows rather than during it.
9. **Anti-martingale (Turtle) ladder as a control:** add every 0.5·ATR *in favour*, at most 4 units, with
   a 2·ATR trailing stop (S15). It is the opposite bet, and it tests whether the edge is trend, not
   reversion. The repo found Turtle the only BTC earner.
10. **BTC H1-H4 reversion ladder:** entry on a z-score ≤ −2 at H1, adds at H2/H4 z-score tiers, exit at
    the H1 mean (EMA20), time stop 24 h. This is aimed directly at the S6 effect.
11. **Volatility-targeted unit:** unit ∝ balance / ATR_D1, cap 10; no new cycle when ATR(H4) is above its
    90th percentile over 100 days (S10).
12. **Overlap close:** when the newest leg's profit ≥ the oldest leg's loss + spread, close both and shrink
    the basket from both ends (S16, weak). Cheap to add to the engine.
13. **Friday-flat plus rollover block for gold:** flat by Fri 20:00 UTC; no adds 20:30-22:30 UTC (S2, S18).
14. **Range-reset grid with a stop (leveraged DGT):** a flat ladder of N levels at spacing g = 0.12·ATR_D1
    around P0. Upper break: take profit and recentre. Lower break: stop and recentre (S3 adapted, since
    leverage forbids holding).
15. **Hedge-on-depth, at most the same size (not zone recovery):** at depth K, open one opposite position
    equal to the net size, freezing the loss, and unwind it on the opposite RSI extreme. It must be judged
    against simply stopping (S9). The likely result is that it equals a stop plus spread and swap.
16. **Shrinking target when deep:** target_k = max(spread·size, target_0/k), so deep baskets leave at about
    break-even instead of holding out for +$1/unit.
17. **Regime test before each cycle:** start a cycle only if the rolling 100-bar H1 return autocorrelation
    is < 0, or the variance ratio VR(4) < 1 (mean-reverting regime). S1/S2 use CUSUM for the same purpose.

**What to expect, honestly:** none of the sources gives a reason to think that a deeper or differently
shaped ladder alone turns the live logic profitable. The ideas with the best support (1, 4, 5, 6, 10) work
by **capping or avoiding the trend case**. On these two symbols, a surviving ladder will probably look like
"a short, ATR-spaced, trend-aligned, stopped mean-reversion trade", not like the live open-ended ladder.
