# Silver (XAGUSDm): survey of published strategies

**Step:** `web` of the silver study. **Written:** 2026-11-17. Sources were read on 2026-11-17 by web search and page fetch.
**Purpose:** list every credible published strategy that could trade silver, with rules exact enough to code; rate the evidence; reject what has no rules or no evidence.
**Not done here:** no backtest was run and no data was read. The ratings judge only the rules and the published evidence. Recent silver price moves were not used, because that would leak the hold-out.

**Contamination note.** The hold-out (2024-07-01 .. 2026-11-13) is already partly seen: the six demo designs' silver results for 2024-05 .. 2026-11 are in `multisymbol/MULTISYMBOL.md`, and silver's 2025-26 rally is public knowledge. Several web sources below were written during the hold-out and quote hold-out numbers: the MQL5 London-breakout post (2023-01 .. 2026-09), the GLD overnight post (2026), the World Gold Council session remark and the gold/silver-ratio blogs. Their rules are used here. Their hold-out-period results are not used for any rating.

---

## 0. How to read this

**Credibility scale** (of the evidence that the rule earns money on silver after costs, not of the author):

| Grade | Meaning |
|---|---|
| **A** | Peer-reviewed. Many markets including metals, long samples, replicated. The effect is in the market class that contains silver. |
| **B** | Strong published evidence for the family: peer-reviewed or a full-rules practitioner record. But there is no silver-specific or after-cost evidence, or the effect has decayed. |
| **C** | Complete rules but indirect or weak evidence: one market, another asset class, gross only, or a vendor test. Worth one honest test. |
| **D** | Evidence is weak, contrary or untestable on our horizon. Test it only as a control or a filter, or not at all. |
| **Rejected** | No codeable rules, no evidence, or the data is not in the store (§7). |

**Repo status:** "in repo" names the function that already implements a rule (`backtesting/research/external.py`, `balke.py`). All of them were built for gold or BTC clocks, so each needs silver's session times (§1.2) before it runs.

**Costs to keep in mind:** XAGUSDm's median spread over 2017-11 .. 2026-11 is **$0.038 per oz** (38 points; `multisymbol/runs/data_quality.csv`). That is **$1.90 per 0.01 lot per round trip**: 0.01 lot = 50 oz, and a $1 move = $50 per 0.01 lot. Any rule whose published edge is a few basis points per trade has to clear this.

---

## 1. Silver facts that shape the rules

### 1.1 Behaviour

- **High beta to gold, but unstable.** Commentary regressions put silver's beta to gold at about 1.2–1.4. A 1% gold move goes with a 1.2–1.4% silver move ([WisdomTree](https://www.wisdomtree.com/nl/insights/blog/whats-hot-silver-breaks-40oz-and-still-rising); [Investing.com, "Silver Math"](https://www.investing.com/analysis/silver-math-shows-gold-warning-of-a-shortterm-correction-200673762)). A University of Denver JP Morgan Center note finds the beta varied by regime: about 1.0 in 1972–95, about 0.35 from the mid-1990s to the early 2000s, and about 0.8 after that. The gold–silver correlation fell from 95% (2002–11) to 41% (2017 on) ([UC Denver, "The Gold to Silver Ratio", 2020](https://business.ucdenver.edu/jpmorgancenter/sites/default/files/attached-files/the_gold_to_silver_ratio_04032020_uc_denver_0.pdf)). **Any rule that leans on gold must re-estimate the link, not assume it.**
- **Gold drives the long-run link.** Baur & Tran (2014, *Empirical Economics* 47(4)) find gold and silver cointegrated over 1970–2011, with gold driving the relationship. But the link is created by bubbles and crises: in "normal" periods the two are not cointegrated ([IDEAS](https://ideas.repec.org/a/spr/empeco/v47y2014i4p1525-1541.html); [UTS WP 172](https://ideas.repec.org/p/uts/wpaper/172.html)). Ciner (2001, Tokyo futures) found the stable relationship disappeared in the 1990s. Schweikert (2018) found only a nonlinear long-run relationship ([preprint](https://karstenschweikert.github.io/qcoint/qcoint_20171121_preprint.pdf)).
- **Silver is the least predictable of the precious metals.** Urquhart (2017, *European Journal of Finance* 23(14), "How predictable are precious metal returns?") used variance-ratio, BDS and Hurst tests on gold, silver and platinum. Silver is the most efficient of the three. Predictability comes and goes in rolling windows ([Reading](https://centaur.reading.ac.uk/79177); [Southampton](https://eprints.soton.ac.uk/396646)). Escribano & Granger (1995): nonlinear silver models beat the random walk in-sample and lose that edge out of sample. **Set the prior low for any short-horizon pattern on silver.**
- **Violent squeezes and margin crashes.** May 2011: CME raised silver margins by 84% in under two weeks. Silver had its biggest three-day drop since 1983 and fell about 30% in the week of 2 May, after a 57% rise in the four months before ([Bloomberg 2011-05-04](https://www.bloomberg.com/news/articles/2011-05-04/silver-slumps-for-third-day-as-increased-margins-spur-sales-by-investors); [IBTimes](https://www.ibtimes.com/did-silver-bubble-burst-282953); [Motley Fool](https://www.fool.com/how-to-invest/2011/05/11/did-higher-margins-kill-commodities.aspx)). The 1980 Hunt corner is the older example. **Size so that a 30% week is survivable** (§6.1).
- **Information leakage at the London fix (historical).** Caminschi & Heaney (2014, *Journal of Futures Markets* 34(11)) found that gold futures and ETF volume and volatility jumped minutes after the London PM fix started, before the result was published ([IDEAS](https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html)). Caminschi's silver working paper, "Any Silver Linings?" (2000–2013), reports a 10–12 bp downward bias in silver's intraday price around the fix ([NYU Stern PDF](https://www.stern.nyu.edu/sites/default/files/assets/documents/Any%20Silver%20Linings%20-%20WORKING%20PAPER%20-%2020140707%20-%20Merged.pdf); the author asks that it not be quoted without permission, so this is a pointer only). Aspris et al. found the 2014 replacement fix, now the LBMA Silver Price, reduced the leakage ([AUT PDF](https://acfr.aut.ac.nz/__data/assets/pdf_file/0011/29792/A-Aspris-Towards-a-New-Fix-Version-005-Submit.pdf)).
- **Macro releases move metals within minutes.** Elder, Miao & Ramchander studied US macro announcements and gold, silver and copper futures at intraday frequency. Metals react fast and strongly to the 08:30 New York releases, especially nonfarm payrolls and durable goods, and some effects are asymmetric ([working paper](https://mountainscholar.org/bitstreams/21623442-a01d-45a6-879d-d645e781e52a/download); later in *Journal of Banking & Finance*, 2012).
- **Monday and variance seasonality.** Lucey & Tully (2006, *Applied Financial Economics* 16(4), COMEX 1982–2002) found a negative Monday effect in gold and silver, cash and futures, robust in GARCH. Seasonality in mean returns is otherwise weak, while seasonality in variance is strong ([IDEAS](https://ideas.repec.org/a/taf/apfiec/v16y2006i4p319-333.html); [TCD WP](https://www.tcd.ie/triss/assets/PDFs/iiis/iiisdp57.pdf)).

### 1.2 The clock: Exness server time is UTC+0

Times every rule needs, converted from their home markets:

| Event | Local time | UTC, US/UK summer | UTC, winter |
|---|---|---|---|
| Exness XAGUSD daily break (Mon–Thu) | — | 20:58 – 22:01 | 21:58 – 23:01 |
| Week open / close | — | Sun 22:05 / Fri 20:58 | Sun 23:05 / Fri 21:58 |
| London open | 08:00 London | 07:00 | 08:00 |
| LBMA Silver Price auction | 12:00 London | 11:00 | 12:00 |
| US data releases (NFP, CPI) | 08:30 New York | 12:30 | 13:30 |
| COMEX silver day session (old floor hours; settlement 13:25) | 08:25 – 13:25 New York | 12:25 – 17:25 | 13:25 – 18:25 |

The US and UK change clocks on different dates, which makes 2–3 mismatch weeks a year. Rules must use time-zone-aware conversion (`external.local_seconds` / `utc_of_local`), not fixed UTC offsets. The Exness break matches CME Globex's 17:00–18:00 New York pause.

---

## 2. Summary of candidates

27 candidates and 5 sizing rules. "Priority" is this survey's suggestion to the prereg step. It is not a result.

| ID | Strategy | TF | Grade | In repo | Priority |
|---|---|---|---|---|---|
| T1 | Time-series momentum, 12-month (Moskowitz–Ooi–Pedersen 2012) | D1/monthly | **A** | `tsmom` (blend) | high |
| T2 | Blended 1/3/12-month TSMOM, vol-scaled (Hurst–Ooi–Pedersen 2017) | D1/monthly | **A** | `tsmom` | high |
| T3 | Turtle System 1 / 2 with its own drawdown rule (Faith; Dennis 1983) | D1 | **B** | `turtle` | high (sizing) |
| T4 | Clenow core trend model: 50/100 EMA filter, 50-day breakout, 3×ATR trail | D1 | **B** | partly (`price_over_sma`, `turtle`) | high |
| T5 | Dual MA crossover / channel, monthly (Szakmary–Shen–Sharma 2010) | monthly | **A** (class), **B** (silver) | `sma_cross` (intraday only) | medium |
| T6 | 10-month SMA timing, long or flat (Faber 2007; Bartsch et al. on gold) | monthly | **B** | `price_over_sma` | medium |
| T7 | EWMAC forecast blend, vol-targeted (Carver; Lempérière et al. 2014) | D1 | **B** | no | high |
| T8 | Donchian ensemble with a ratcheting midline (Zarattini–Pagani–Barbon 2025) | D1 | **C** | `donchian_ensemble` | low |
| B1 | Opening-range breakout at the COMEX open (Crabel 1990; Holmberg et al. 2013) | M1–M15 | **C** | adapt `range_breakout` | medium |
| B2 | 5-minute ORB (Zarattini & Aziz 2023) | M5 | **C−** | no | low |
| B3 | Open ± k × prior range volatility breakout (Williams; Crabel stretch) | D1/M1 | **C** | `daily_vol_breakout` (ATR variant) | medium |
| B4 | Asian range → London breakout (MQL5 777540) | M1–M15 | **C** | `london_breakout` | medium |
| B5 | Balke Range Breakout / ATR Breakout | M1/H1 | **C** | `range_breakout`, `atr_breakout` | medium |
| B6 | Intraday momentum into the session close (Gao et al. 2018; Baltussen et al. 2021; Xu et al. 2020) | M30 | **B** (effect), **C** (net) | `last_half_hour` | medium |
| B7 | Noise-area intraday momentum (Zarattini–Aziz–Barbon 2024) | M30 | **C** | `noise_area` | medium |
| M1 | Connors RSI(2) with a 200-day filter | D1 | **D** | `connors_rsi2` | control |
| M2 | Bollinger Band fade (20, 2σ) | D1/H1 | **D** | no | control |
| M3 | 10-day max/min rule (Padysak & Vojtko 2022) | D1 | **D** | `max_min` | low |
| M4 | Fade the LBMA-auction drift | M1 | **D** | no | low |
| M5 | Monday effect: avoid or short Mondays (Lucey & Tully 2006) | D1 | **C−** | no | filter |
| G1 | Gold/silver ratio regime switch (80 / 50) | D1/weekly | **D** | no | reject for trading; filter idea |
| G2 | Gold/silver ratio z-score pair trade | D1/H4 | **D** | no | low |
| G3 | Silver catches up to gold (spread error-correction, Adrangi et al. 2000) | M15–H1 | **C** | no | high (silver-specific) |
| G4 | Trade silver only in gold's trend direction (gold-led filter) | H4/D1 | **C** | no (bot votes exist) | medium (filter) |
| S1 | Autumn effect: long September and November (Baur 2013) | monthly | **D** (silver) | no | control |
| S2 | Overnight / Asian-session drift (GLD close-to-open; WGC remark) | H1 | **C−** | `seasonality_22utc`, `go_long` | low |
| S3 | US-release filter: no new risk around 08:30 New York data | M1 | **B** (as a filter) | no | high (filter) |
| R1–R5 | Sizing: vol targeting, Turtle drawdown cut, fixed-fraction ATR, stop theory, worst-week cap | — | **A/B** | partly (`Sizing`, `sizing.py`) | high |

The table has 27 tradable candidates, T1–S3. M3 and M4 are weak extras, run only because they are cheap. The sizing rules R1–R5 are in §6.

---

## 3. Trend following and time-series momentum

### T1 Time-series momentum, 12-month (Moskowitz, Ooi & Pedersen 2012)

- **Rules.** At each month end, compute the instrument's excess return over the past 12 months, r(t−12, t). Hold long if it is positive, short if negative, for one month. Size to a constant risk: position = 40% / σ_t, where σ_t is the ex-ante annualised volatility, an EWMA of squared daily returns with a 60-day centre of mass (the paper's choice). For the bot, replace 40% with a cash risk budget (§6).
- **Source.** T. Moskowitz, Y. H. Ooi, L. H. Pedersen, "Time series momentum", *Journal of Financial Economics* 104(2), 228–250, 2012 ([RePEc](https://econpapers.repec.org/RePEc:eee:jfinec:v:104:y:2012:i:2:p:228-250); [SSRN 2089463](https://papers.ssrn.com/abstract=2089463); [AQR data](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data)).
- **Evidence.** 58 futures and forwards, 24 of them commodities, over 1985–2009. A security's own past 12-month return predicts its next month's return. The effect lasts about a year, then partly reverses. Returns are reported gross. The commodity set is standard and includes COMEX metals, but I could not confirm silver's individual result from the abstract. Replicated widely (T2, Lempérière et al.).
- **Grade A** for the effect in the commodity class. Silver alone is one noisy market: with 12-month signals, the development window (2018-11 .. 2022-12) holds only a handful of independent trend episodes.
- **Silver notes.** Monthly rebalancing means about 12 trades a year, so costs are negligible. Swaps matter, because positions are held for months; MULTISYMBOL §swap applies. In repo: `external.tsmom` uses the 1/3/12 blend (T2). The pure 12-month version is `alt`, or a one-line change.

### T2 Blended 1/3/12-month TSMOM, volatility-scaled (Hurst, Ooi & Pedersen 2017)

- **Rules.** Three signals, the signs of the 1-month, 3-month and 12-month excess returns, equally weighted (each ±1/3). Each instrument is sized to a constant ex-ante volatility, and the portfolio is scaled to 10% a year. Rebalance monthly. The repo uses calendar 30/91/365 days for around-the-clock markets and 21/63/252 trading days otherwise.
- **Source.** B. Hurst, Y. H. Ooi, L. H. Pedersen, "A Century of Evidence on Trend-Following Investing", *Journal of Portfolio Management* 44(1), 15–29, 2017 ([AQR PDF](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing?aqrPDF=1); [Yale copy](https://fairmodel.econ.yale.edu/ec439/hurst.pdf)).
- **Evidence.** 67 markets in four asset classes, 1880/1903 to 2012+. Positive in every decade, reported after simulated costs and 2/20 fees. It does best in prolonged moves and crises.
- **Grade A** for the class. **Silver-specific risk:** a one-market TSMOM is far noisier than the diversified portfolio the paper reports. Its Sharpe ratio is perhaps a third of the portfolio's, by the usual diversification arithmetic.
- **In repo:** `external.tsmom` ("Moskowitz-Ooi-Pedersen / Hurst-Ooi-Pedersen: sign of the 1, 3 and 12-month returns").

### T3 Turtle System 1 and System 2

- **Rules (as published by Curtis Faith).**
  - **Volatility:** N = 20-day Wilder ATR, N_t = (19·N_{t−1} + TR_t)/20.
  - **Unit:** 1% of account equity per 1 N of price move. Lots = 0.01·Equity / (N · $ per $1 per lot); for XAGUSD, $ per $1 per lot is 5,000.
  - **System 1 entry:** break of the 20-day high (long) or low (short). Skip it if the previous S1 breakout would have been a winner, but always take a 55-day breakout (the failsafe). Exit at the 10-day opposite extreme.
  - **System 2 entry:** 55-day breakout. Exit at the 20-day opposite extreme.
  - **Stop:** 2N from entry. With adds, every leg's stop moves to 2N below the latest add.
  - **Pyramid:** add 1 unit every ½N in favour, up to 4 units per market.
  - **Drawdown rule:** each 10% drawdown cuts the notional trading equity used for sizing by 20%.
- **Source.** C. Faith, *The Original Turtle Trading Rules* (free PDF, originalturtles.org, 2003) and *Way of the Turtle* (McGraw-Hill, 2007). Background: M. Covel, *The Complete TurtleTrader* (2007) ([Faith's foreword](https://turtletradersystem.blogspot.com/2009/01/original-turtle-trading-rules-foreword.html); [turtletrader.com](https://www.turtletrader.com/?p=2515)).
- **Evidence.** Famous live record in 1983–88 on diversified futures. The rules are fully public. Later evidence is mixed: Lempérière et al. find short trends have withered while long trends have not (T7), which favours System 2 over System 1.
- **Grade B.** For this study, its **drawdown rule and N-sizing matter more than its entries**. Silver S1's one-unit stream was positive, but the bot's unit-rule account, sized up on gains, was wiped on 2026-04-21 (MULTISYMBOL). The original Turtle sizing never sizes up on unrealised gains and cuts size in drawdowns.
- **Silver notes.** At $2,000, one Turtle unit is 0.01·2000/(N·5000) lots = 0.004/N lots. That falls below the 0.01-lot minimum whenever N > $0.40. **The lot floor forces over-risking on a small account.** The prereg step must decide whether to skip the trade or take 0.01 lot and record the true risk. In repo: `external.turtle(system=1|2)`.

### T4 Clenow core trend model

- **Rules (Following the Trend, ch. on the core strategy).**
  - **Trend filter:** long only if the 50-day EMA is above the 100-day EMA; short only if below.
  - **Entry:** at the close when today's close is the highest close of 50 days (long), or the lowest (short), in the filter's direction.
  - **Exit:** trailing stop 3 × ATR(100) from the highest close since entry (lowest for shorts).
  - **Sizing:** risk factor 0.2% of equity per ATR(100). Lots = 0.002·Equity / (ATR100 · $ per $1 per lot).
- **Source.** A. Clenow, *Following the Trend: Diversified Managed Futures Trading* (Wiley, 2013). Secondary code and rule summaries: [ProRealCode thread](https://www.prorealcode.com/prorealtime-trading-strategies/following-the-trend/?pnum=6); [QuantConnect thread on Clenow sizing](https://www.quantconnect.com/forum/discussion/3136/andreas-f-clenow-momentum/p1).
- **Evidence.** The book's simulation on a diversified futures universe (about 1990–2011) includes COMEX silver. Rules are exact and simple. The forum copies disagree on the stop multiple (3 against 5–7 ATR); the book's 3×ATR(100) is used here. It is not peer-reviewed.
- **Grade B.**
- **Silver notes.** Sizing at 0.2% per ATR means 0.002·2000/(ATR·5000) = 0.0008/ATR lots, which is below 0.01 lot for any realistic silver ATR. **At $2,000, every Clenow trade is at least 0.01 lot and over-risked** (same issue as T3). In repo: partly; needs a new function.

### T5 Dual moving-average crossover and channel rules on monthly data (Szakmary, Shen & Sharma 2010)

- **Rules.** On monthly prices:
  - **Dual MA:** long when the short MA of monthly closes is above the long MA, short when below. Several (short, long) pairs.
  - **Channel:** long when the close exceeds the highest close of the past L months, short below the lowest. Hold until the opposite signal.
- **Source.** A. Szakmary, Q. Shen, S. Sharma, "Trend-following trading strategies in commodity futures: A re-examination", *Journal of Banking & Finance* 34(2), 409–426, 2010 ([IDEAS](https://ideas.repec.org/a/eee/jbfina/v34y2010i2p409-426.html)).
- **Evidence.** 28 commodity futures over 48 years. Every parameterisation of both rules has positive mean excess returns net of costs in at least 22 of the 28 markets.
- **Grade A** for the class. The **exact parameter grid and silver's own row need the paper's tables**, which are behind a paywall and were not read. A secondary site ([qgtm-docs](https://qgtm-docs.pages.dev/research/gold_silver/paper_szakmary_trend_following)) claims "silver 50-day channel, Sharpe ~0.45". The paper uses monthly data, so a 50-*day* channel is inconsistent with it, and the page looks machine-written. **That claim is not used.**
- **Silver notes.** A monthly signal means few trades in our development window. Use it as a slow regime filter or a T1 variant.

### T6 10-month SMA timing, long or flat (Faber); gold timing under a data-snooping test (Bartsch, Baur, Dichtl & Drobetz)

- **Rules.** At each month end, long if the monthly close is above its 10-month SMA, else flat. Faber's original is long-only for asset classes. A short side is optional and untested by the source.
- **Sources.** M. Faber, "A Quantitative Approach to Tactical Asset Allocation", *Journal of Wealth Management*, 2007 (SSRN 962461). Bartsch, Baur, Dichtl & Drobetz, "Investing in the Gold Market: Market Timing or Buy-and-Hold?" (summary at [Quantpedia, 2018-08-06](https://quantpedia.com/an-extensive-test-of-market-timing-strategies-in-the-gold-market/)).
- **Evidence.** Faber: equities, bonds, REITs and the GSCI commodity index, 1973–2005+. The rule reduced drawdowns at similar returns. Bartsch et al. tested more than 4,000 timing rules on gold over 1990–2015: 4,096 monthly seasonal patterns, MA pairs (1–3 against 9/12 months, 1 against 10/24/36/48 months), TSMOM at 1–48 months, and fundamentals. They applied Hansen's SPA test for data snooping. Only "a limited number of technical strategies" beat buy-and-hold significantly, and they did so by being out of gold during prolonged downtrends.
- **Grade B.** Honest multiple-testing evidence on gold, the nearest market to silver. The benefit is drawdown avoidance, not extra return.
- **Silver notes.** It fits a $2,000 account as a long-only regime filter for other rules. In repo: `external.price_over_sma(n, tf)`.

### T7 EWMAC trend forecasts with volatility targeting (Carver; Lempérière et al.)

- **Rules.**
  - **Raw forecast:** (EWMA_fast(P) − EWMA_slow(P)) / σ_P, where σ_P is the daily price volatility (an EWMA of |ΔP|, 25-day span in pysystemtrade).
  - **Variations:** (8, 32), (16, 64), (32, 128), (64, 256) days.
  - **Scaling:** each raw forecast is scaled so its long-run mean |forecast| is 10, then capped at ±20. The variations are averaged.
  - **Position:** (forecast / 10) × (daily cash risk target / instrument daily cash vol). Rebalance only when the position differs from the target by more than 10% ("buffering").
- **Sources.** R. Carver, *Systematic Trading* (Harriman, 2015) and the open-source `pysystemtrade` (GitHub, robcarver17). Y. Lempérière, C. Deremble, P. Seager, M. Potters, J.-P. Bouchaud, "Two centuries of trend following", *Journal of Investment Strategies*, 2014 ([arXiv 1404.3274](https://ar5iv.arxiv.org/html/1404.3274)).
- **Evidence.** Lempérière et al. (CFM) use an EMA-based trend signal with about a 5-month timescale on commodities, currencies, indices and bonds since 1800 (spot) and 1960 (futures). The t-statistic is about 5 since 1960 and about 10 since 1800. There is **no degradation of long trends, but short trends have significantly withered**. Carver's rules are fully public; the book is evidence of practice, not peer-reviewed.
- **Grade B.** This is the most transparent way to run T1/T2-type trend with continuous sizing on one market. Prefer the slower variations: the evidence says short trends decayed.
- **Silver notes.** Continuous sizing rounds to 0.01-lot steps. At $2,000 the position will sit at 0, 0.01 or 0.02 lot most of the time, so check the rounding loss. Not in repo; needs a new function.

### T8 Donchian ensemble with a ratcheting midline stop (Zarattini, Pagani & Barbon 2025)

- **Rules (repo implementation).** Nine Donchian close-breakout models over different lookbacks. Each enters on a close beyond the N-day channel and exits on a ratcheting channel-midline stop. They are averaged and vol-targeted.
- **Source.** The repo's implementation of Zarattini, Pagani & Barbon (2025), written for crypto. The parameters are in `external.LOOKBACKS`.
- **Evidence.** Crypto only. It is a younger relative of T3/T5.
- **Grade C** for silver. In repo: `external.donchian_ensemble`. Run it as a cheap extra trend variant only.

---

## 4. Breakouts and intraday momentum

### B1 Opening-range breakout at the COMEX / New York open

- **Rules.**
  - **Opening range:** the high and low of the first R minutes after 08:25 New York (12:25 UTC in summer, 13:25 in winter). R = 5, 15 or 30.
  - **Orders:** a buy stop at OR high + b and a sell stop at OR low − b, OCO.
  - **Stop:** the opposite side of the OR.
  - **Exit:** at the COMEX settlement time, 13:25 New York, or at the end of the day.
  - **Crabel's variant:** stops at open ± "stretch", where stretch = the 10-day average of min(high − open, open − low).
  - **Optional:** Crabel's trend filter, and his narrow-range filters (NR4/NR7: today's range the narrowest of the last 4 or 7 days).
- **Sources.** T. Crabel, *Day Trading with Short Term Price Patterns and Opening Range Breakout* (Traders Press, 1990). U. Holmberg, C. Lönnbark, C. Lundström, "Assessing the profitability of intraday opening range breakout strategies", *Finance Research Letters* 10(1), 27–33, 2013 ([IDEAS](https://ideas.repec.org/a/eee/finlet/v10y2013i1p27-33.html)). Oxford Capital Strategies' ORB benchmark on 42 futures, 1980–2011, with 1% fixed-fractional sizing and a 6×ATR stop; it reports that a trend filter and longer holds improve ORB ([oxfordstrat](https://oxfordstrat.com/?p=6908)).
- **Evidence.** Holmberg et al.: US crude oil futures, bootstrap test. The ORB was significantly profitable, and Lundström's follow-up finds profitability rises with volatility. Not silver; full text not read.
- **Grade C.** Silver's high intraday volatility fits the "volatility helps ORB" finding, and the COMEX open is a real liquidity event. But Urquhart's efficiency result and spread costs argue against it.
- **Silver notes.** Adapt `balke.range_breakout(start, end, close, stop, …)` to New York clock times.

### B2 5-minute ORB (Zarattini & Aziz 2023)

- **Rules.** If the first 5-minute candle of the session closes up, buy at the open of the second candle; if down, sell. No trade on a doji. Stop at the first candle's opposite extreme. Target 10R, else exit at the session close. Risk 1% per trade, leverage capped at 4×.
- **Source.** C. Zarattini, A. Aziz, "Can Day Trading Really Be Profitable?", SSRN 4416622, 2023 ([PDF copy](https://wealth-lab.com/api/discussion/download/pdf/6590-ORB-Strategy-pdf)). The stock-universe extension is Zarattini, Barbon & Aziz 2024, SSRN 4729284 ([Concretum](https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/)).
- **Evidence.** QQQ, 2016–2023, reported at zero spread. An independent replication on NQ, SPX, Dow, DAX and FTSE CFDs (Jan 2015 – Jun 2026, costs at 6–12% of risk) reproduced the gross +0.13R on NQ, but **net was indistinguishable from zero on all five, and four were negative** ([T.-P. Krueger, MQL5 blog 776235, 2026-09-25](https://www.mql5.com/en/blogs/post/776235)).
- **Grade C−.** The first candle carries a small edge, about the size of the cost. On silver the 5-minute range is small relative to the $0.038 spread, so costs would be a larger share of risk than for the indices. Low priority.

### B3 Open ± k × prior range (Williams volatility breakout)

- **Rules.**
  - **Entry:** buy stop at today's open + k·(yesterday's high − low) and sell stop at open − k·range, OCO. The usual k is 0.25–1.0; Williams-style defaults are about 0.5–0.6.
  - **Stop:** a fraction of the same range.
  - **Exit:** at the session end, or at the first profitable open (Williams' "bail-out").
  - **Optional filters:** day-of-week and trend.
- **Sources.** L. Williams, *Long-Term Secrets to Short-Term Trading* (Wiley, 1999). Rule pages: [WH SelfInvest](https://www.whselfinvest.de/en/trading_strategies_56_volatility_break_out_larry_williams_free.php), [LuxAlgo](https://www.luxalgo.com/library/concept/volatility-breakout/).
- **Evidence.** No peer-reviewed or out-of-sample commodity test of the exact rule was found. Williams' own results are not independently verified.
- **Grade C.** In repo: `external.daily_vol_breakout` (Unger's variant: buy stop at the previous close + ATR(2), 8% stop, out at the day's end). For silver, use Exness's 22:01/23:01 UTC reopen as "the open" and exit before the daily break.

### B4 Asian range → London breakout

- **Rules (exact, from the post).**
  - **Range:** high and low from 03:00 to 08:00 server time. The post's broker clock is New York + 7 h; the repo supports both clocks.
  - **Range filter:** trade only if the range is 0.30–1.60% of price.
  - **Entry:** at 08:00, OCO stop orders a small buffer beyond the range.
  - **Stop:** the other side of the range, capped at 0.6% of price.
  - **Target and exits:** target 2.5R, move to break-even at 1.5R, flat at 21:00. At most one trade a day.
- **Source.** S. Pinjori, "London Breakout on Gold: 3.7 Years of Backtests", MQL5 blog 777540, 2026-10-13 ([link](https://www.mql5.com/en/blogs/post/777540)).
- **Evidence.** Gold, MT5 real ticks, Jan 2023 – Sep 2026, two brokers. Profit factor 1.37–1.38 at 1% risk, drawdown 17–19%, 715 trades. Settings were picked on 2023–25. The post reports what failed: tight in-range stops, no range filter, holding into New York, 5R targets. The author sells the EA. The period is inside our hold-out and the market is gold, so **no silver evidence**.
- **Grade C.**
- **Silver notes.** Silver's typical intraday % range is wider than gold's. The 0.30–1.60% and 0.6% thresholds must be rescaled *on the development data only*. Preferred rescale: multiply by the silver/gold median ratio of the same-window range. In repo: `external.london_breakout(clock=…)`.

### B5 Balke Range Breakout and ATR Breakout (BM Trading)

- **Rules.** As re-built in `balke.py` from the public descriptions:
  - **Range Breakout:** the morning range, then OCO stop orders at its edges, a stop rule, and a close time.
  - **ATR Breakout:** a trade in the direction of an unusually large H1 candle, relative to ATR(200) × 2.5, with a proximity condition and a take-profit percentage.
  - The `ASSUMED` notes in `balke.py` mark the choices that are not public.
- **Source.** René Balke / BM Trading GmbH (MQL5 seller `bmtrading`, YouTube, bmtrading.de). Our report: `backtest_results/balke/BALKE.md`.
- **Evidence.** Our own gold test (BALKE.md): Range Breakout made +11.0% a year at a 24.0% drawdown over 8 years at his sizing, with a daily correlation of 0.10 to V3-lite. An independent real-tick test found that 84% of gold stop entries fill worse than the M1 model assumes. No silver evidence.
- **Grade C.** It is the most promising intraday breakout already in the repo. Silver needs its own range window, near the London open and/or the COMEX open, chosen on development data only.

### B6 Intraday momentum into the close

- **Rules.**
  - **Gao et al. version:** at 30 minutes before the session close, take the sign of the return from the previous session's close (or of the first half hour) to now. Hold in that direction for the last 30 minutes and exit at the close.
  - **Silver session:** COMEX settlement is 13:25 New York, so the signal is at 12:55 and the hold runs 12:55–13:25. The alternative is the Globex close before the Exness daily break.
  - **Filter (Xu et al.):** trade only on days of high volatility or with jumps in the signal window.
- **Sources.**
  - L. Gao, Y. Han, S. Li, G. Zhou, "Market intraday momentum", *Journal of Financial Economics*, 2018 ([PDF](https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf)).
  - G. Baltussen, Z. Da, S. Lammers, M. Martens, "Hedging demand and market intraday momentum", *Journal of Financial Economics* 142(1), 377–403, 2021 ([PDF](https://www3.nd.edu/~zda/intramom.pdf)).
  - Y. Xu, E. Bouri, T. Saeed, Z. Wen, "Intraday return predictability: Evidence from commodity ETFs and their related volatility indices", *Resources Policy* 69, 2020 ([IDEAS](https://ideas.repec.org/a/eee/jrpoli/v69y2020ics030142072030862x.html)).
  - M. Jin, F. Kearney, Y. Li, Y. Yang, "Intraday time-series momentum: Evidence from China", *Journal of Futures Markets* 40(4), 2020 ([IDEAS](https://ideas.repec.org/a/wly/jfutmk/v40y2020i4p632-650.html)).
- **Evidence.** Baltussen et al.: more than 60 futures, commodities included, 1974–2020. The rest-of-day return predicts the last 30 minutes, strongly and significantly. They attribute this to gamma hedging, which exists mainly in equity indices. **Xu et al. study silver directly (SLV, 1-minute):** predictability exists, but the predicting half-hour is market-specific and not always the first one. It is stronger on high-volatility and jump days. Jin et al.: the effect is strongest in metals on high-volume openings, and moves when trading hours change (Chinese night sessions).
- **Grade B** for the existence of the effect, **C** for net profit. The edge per trade is a few basis points, against a silver round trip of 13–19 bp at $20–30 prices. Trade it only on the high-volatility days Xu et al. identify.
- **In repo:** `external.last_half_hour` (gold: COMEX hours, signal 13:00 New York, hold to 13:30). For silver, change the times to 12:55–13:25.

### B7 Noise-area intraday momentum (Zarattini, Aziz & Barbon 2024)

- **Rules.**
  - **Noise width:** σ(t), the 14-day mean of |close(t)/open − 1| at the same time of day t.
  - **Bounds:** upper = max(open, previous close)·(1 + σ(t)); lower = min(open, previous close)·(1 − σ(t)).
  - **Entry:** at each :00/:30, long above the upper bound, short below the lower.
  - **Exit:** trail with the bound or the session VWAP, whichever is tighter; flat at the session end.
  - **Sizing:** volatility-targeted, about 2% daily vol, leverage capped at 4×.
- **Source.** C. Zarattini, A. Aziz, A. Barbon, "Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)", SSRN, 2024.
- **Evidence.** SPY, 2007–2024, with commissions and slippage modelled. Only SPY was tested; there is no commodity evidence.
- **Grade C.** In repo: `external.noise_area(kind="comex"|"utc")`. For silver, use the COMEX day session.

---

## 5. Mean reversion, gold-silver links, seasonality

### M1 Connors RSI(2)

- **Rules.** Long at the close when RSI(2) < 5 (some versions use 10) and the close is above the 200-day SMA. Exit at the close when the close is above the 5-day SMA. The short is the mirror: RSI(2) > 95 and the close below the 200-day SMA, exit below the 5-day SMA. There is no stop in the original.
- **Source.** L. Connors, C. Alvarez, *Short Term Trading Strategies That Work* (TradingMarkets, 2008).
- **Evidence.** It was built on equity indices and stocks. Recent tests show it lagging buy-and-hold badly on the S&P 500 and Nasdaq over 2016–26, and losing on EUR/USD ([backtrex](https://backtrex.com/en/backtests/connors-rsi-2-sp-500); weak sources). Miffre & Rallis (2007, *Journal of Banking & Finance* 31, 1863–1886) tested 56 momentum and contrarian strategies on commodity futures: **contrarian strategies do not work**, momentum does ([EDHEC](https://risk.edhec.edu/publications/momentum-strategies-commodity-futures)). No gold or silver test of RSI(2) was found. Kaminski & Lo (§6) imply that adding a stop to a mean-reversion rule lowers expected return.
- **Grade D.** Keep it as a control. In repo: `external.connors_rsi2`.

### M2 Bollinger Band fade

- **Rules.** Bands = SMA(20) ± 2·SD(20). Long when the close is below the lower band, exit at the middle band. Short is the mirror. An optional filter: no fades against the 200-day trend.
- **Source.** J. Bollinger, *Bollinger on Bollinger Bands* (2001). Test: C. Lento, N. Gradojevic, C. S. Wright, "Investment information content in Bollinger Bands?", *Applied Financial Economics Letters* 3(4), 263–267, 2007 ([IDEAS](https://ideas.repec.org/a/taf/raflxx/v3y2007i4p263-267.html)).
- **Evidence.** Lento et al. tested several band settings on equity indices and FX; the full text was not read. Nothing on metals was found.
- **Grade D.** Commodity evidence favours momentum, not fades (Miffre & Rallis). Keep it as a control only.

### M3 10-day max/min rule (Padysak & Vojtko 2022)

- **Rules.** Long for the next day when today's close is the 10-day highest *or* lowest close.
- **Source.** M. Padysak, R. Vojtko, "Seasonality, Trend-following, and Mean reversion in Bitcoin" (SSRN, 2022).
- **Evidence.** BTC only.
- **Grade D** for silver. In repo: `external.max_min`. Include it only because it is free to run.

### M4 Fade the LBMA-auction drift

- **Rules.** Short silver at the auction start, 12:00 London; exit 15–30 minutes later or at the auction publication.
- **Source.** Caminschi working paper (§1.1); Caminschi & Heaney 2014 for gold; Aspris et al. on the new fix.
- **Evidence.** A 10–12 bp bias around the old silver fix, 2000–2013. **The 2014 reform reduced the leakage.** Our data starts in 2017-11, after the reform, and the bias was smaller than the 13–19 bp round trip.
- **Grade D.** Probably dead and below cost. Test it at most as a cheap event study (mean M1 return around 11:00/12:00 UTC), not as a bot.

### M5 Monday effect

- **Rules.** Flat on Mondays (no longs held from Friday close to Monday close), or short from the Friday close to the Monday close. As a filter: block new long entries on Mondays.
- **Source.** B. Lucey, E. Tully, "Seasonality, risk and return in daily COMEX gold and silver data 1982–2002", *Applied Financial Economics* 16(4), 319–333, 2006 ([IDEAS](https://ideas.repec.org/a/taf/apfiec/v16y2006i4p319-333.html)). Kohli (2012) re-examined gold and silver over 1980–2012 ([PDF](https://businessperspectives.org/images/pdf/applications/publishing/templates/article/assets/4996/IMC_2012_02_Kohli.pdf)).
- **Evidence.** A negative Monday mean in both metals, cash and futures, robust in GARCH. Old sample, small effect, and weekend gap risk applies to the short.
- **Grade C−.** Best used as an entry filter, tested on development data.

### G1 Gold/silver ratio regime switch (80 / 50)

- **Rules.** GSR = XAU/XAG. Hold silver (instead of gold or cash) once the GSR closes above 80, and switch back to gold when it closes below 50. SentimenTrader's version needs a weekly close above 80 to re-enter silver.
- **Sources.** [SentimenTrader GSR update](https://sentimentrader.com/blog/goldsilver-ratio-update); [Schaeffer's 2019](https://www.schaeffersresearch.com/content/analysis/2019/07/24/extreme-gold-silver-ratio-sends-mixed-signals-for-precious-metals); [goldstandard substack](https://goldstandardorg.substack.com/p/the-gold-silver-ratio-your-hidden); [Silver Institute, 2026](https://silverinstitute.org/wp-content/uploads/2026/07/Is-the-Gold-Silver-Ratio-Relevant-Today.pdf) (industry-funded Johansen test, 1970–2026, finds the ratio mean-reverting).
- **Evidence.** Schaeffer's (since 1980): with a high ratio, silver averaged about +10% over the next year, **but more than half of those years were negative**. Below 55, silver averaged −2.5%. The substack test (2000–2025, no costs) had higher return but a deeper drawdown (−50% against −44%), and its Sharpe was slightly *below* holding gold. A full cycle takes years: **only one or two signals fall inside our 2018–2022 development window**, so it is untestable here.
- **Grade D** as a strategy. As a *slow filter* (e.g. long silver only while GSR > its 5-year median), it could be pre-registered, but its evidence is weak.

### G2 Gold/silver ratio z-score pair trade

- **Rules.** z = (ln GSR − SMA_n(ln GSR)) / SD_n, with n = 20–60 days. When z > +2, long silver and short gold, dollar-neutral (beta-neutral optional). When z < −2, the reverse. Exit at |z| < 0.5, with a time stop of 2n.
- **Sources.** [QuantConnect GLD/SLV template](https://www.quantconnect.com/terminal/cache/embedded_backtest_14145b688946fd2d41e76ad5ee46b924.html). [QuantifiedStrategies](https://quantifiedstrategies.substack.com/p/gold-silver-chart-ratio-strategy): an RSI(5) on the ratio, buy above 75, sell below 50, "has not performed well"; the pair variant was "flat". M. Wahab, R. Cohn, M. Lashgari, "The gold-silver spread: Integration, cointegration, predictability, and ex-ante arbitrage", *Journal of Futures Markets* 14(6), 709–756, 1994 ([IDEAS](https://ideas.repec.org/a/wly/jfutmk/v14y1994i6p709-756.html)).
- **Evidence.** Wahab et al. (daily 1982–1992) found cointegration but **no profitable ex-ante trading strategy** on the spread. Ciner and Baur & Tran: the link is unstable and absent in normal periods. Practitioner tests are flat or negative.
- **Grade D.** It also needs two symbols in one EA, which conflicts with the one-strategy-per-bot design unless one EA trades both.

### G3 Silver catches up to gold (spread error-correction)

- **Rules (a codeable form of the paper's finding; no published trading test).**
  - **Spread:** s_t = ln XAG − β·ln XAU on M15 bars, with β re-estimated by rolling OLS over 20 trading days.
  - **Residual:** e_t = s_t − mean_20d(s).
  - **Entry:** when |e_t| > c·SD_20d(e) *and* gold has just made a move (say, gold's 1-hour return beyond ±k gold ATR), trade **silver only**, toward closing the gap. The idea is that silver lags gold, so the trade runs in gold's move direction.
  - **Exit:** at e = 0, or after H bars, with a stop at 2·SD.
  - **Simpler variant ("silver follows gold breakouts"):** when gold closes above its N-bar high and silver has not, buy silver; mirror for shorts.
- **Sources.** B. Adrangi, A. Chatrath, R. David, "Price discovery in strategically-linked markets: the case of the gold-silver spread", *Applied Financial Economics* 10(3), 2000 ([abstract](https://informahealthcare.com/doi/abs/10.1080/096031000331644)): 15-minute gold and silver futures; **silver bears most of the burden of convergence to the gold-silver spread**. Baur & Tran 2014: gold drives the long-run relationship. A non-peer-reviewed daily Granger test finds gold's past moves help predict silver's, not the reverse ([ashnawrites](https://ashnawrites.substack.com/p/gold-explains-silver-until-leverage)).
- **Evidence.** The direction of adjustment is documented. Profitability after costs is not: there is no published backtest. The link is weak in normal periods (§1.1).
- **Grade C.** Silver-specific and testable with our data (gold ticks and silver per-second), and unlike anything the bots run. Pre-register c, k, H and N on a small grid. **Label it our design built on a paper's finding, not a published strategy.**

### G4 Gold-led trend filter for silver

- **Rules.** Allow silver longs only when gold's trend is up and shorts only when it is down. The gold trend can be measured as gold's 50/100-day EMA state, gold's T2 signal, or the bot's H4 votes computed on XAUUSDm. Apply it to any silver entry rule (T3, T4, B1, B4).
- **Sources.** As G3: gold leads, and silver's beta is above 1 in recent regimes. Crabel and Oxford find that trend filters improve ORB (B1).
- **Grade C.** It is a filter, cheap to test, and reduces trades. It must beat the same filter built on silver's own trend, or it adds nothing.

### S1 Autumn effect

- **Rules.** Long silver only in September and November; flat otherwise.
- **Sources.** D. Baur, "The autumn effect of gold", *Research in International Business and Finance* 27(1), 1–11, 2013 ([UTS](https://opus.lib.uts.edu.au/handle/10453/23416)). Potrykus & Augustynowicz 2024 replicated it for gold, and noted that **for silver "this effect is no longer observed for the most recent research sample"** ([PDF](https://reference-global.com/download/article/10.2478/ijme-2024-0011.pdf)). Borowski & Łukasik (2019) found no monthly effects in gold, silver, platinum or copper.
- **Evidence.** Gold only (1980–2010). Silver's evidence is negative. The development window holds only four Septembers and four Novembers.
- **Grade D.** Control only.

### S2 Overnight / Asian-session drift

- **Rules.** Long from the US close (or the Exness reopen, 22:01/23:01 UTC) to the London or New York open; flat during US hours.
- **Sources.** [QuantifiedStrategies, "A Quantitative Look at the Gold Overnight Strategy", 2026-03-11](https://quantifiedstrategies.substack.com/p/a-quantitative-look-at-the-gold-overnight): GLD close-to-open earned about 11.4% a year against 11.8% for buy-and-hold, intraday about flat, average +0.04% a night. A World Gold Council H1 remark, reported second-hand, says gold's rebounds came in Asian hours and pullbacks in US hours ([moneymetals](https://www.moneymetals.com/news/2026/07/12/a-strange-dichotomy-gold-up-on-the-year-in-asian-markets-down-big-in-the-west-005059)); it is recent, so its numbers are not used.
- **Evidence.** Gold only, and the GLD "overnight" includes the whole non-US session. +0.04% a night is less than silver's spread. The overnight hold also pays swap every night.
- **Grade C−.** In repo: `external.seasonality_22utc` (BTC's 22–00 UTC) and `balke.go_long`. Test it at most as a filter: is silver's mean M1 return by UTC hour different from zero on development data?

### S3 US-release filter

- **Rules.** Place no new entries from 5 minutes before to 15 minutes after 08:30 New York on release days. Optionally, flatten intraday positions before the release. The NFP date can be coded as the first Friday of the month, with known exceptions. CPI and other dates need a calendar file, which is not in the store.
- **Source.** Elder, Miao & Ramchander (§1.1).
- **Evidence.** Fast, large and asymmetric metal reactions to US releases, so the risk reduction is documented. There is no evidence of a profit from trading the release.
- **Grade B** as a risk filter for B1/B4/B6/B7 and for the bot. It is not a stand-alone strategy.

---

## 6. Sizing and risk control (rules the account needs to survive)

### 6.1 The arithmetic of 0.01 lot on a $2,000 account

0.01 lot = 50 oz. A move of x% at price P costs 0.5·P·x dollars per 0.01 lot. A 30% week, the size of May 2011, costs 15·P per 0.01 lot: $300 at P = $20, $450 at $30, $600 at $40. **On a $2,000 account, one minimum lot held through such a week loses 15–30%.** Two lots or a sized-up unit can lose half the account. Margin is no constraint (leverage 2000), so only an equity rule protects the account. Any silver bot should therefore:

- cap gross exposure, in oz, from the worst historical week on *development* data, not from the stop distance alone. Stops gap through at weekends and in squeezes;
- never size up on open profit. The MULTISYMBOL silver Turtle wipe came from sizing up on 2025–26 gains;
- treat the 0.01-lot floor as a hard constraint. When a rule's risk-based size rounds below 0.01, the prereg must choose "skip" or "take 0.01 and log the over-risk" (T3, T4, T7).

### R1 Volatility targeting

Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert, "The Impact of Volatility Targeting", *Journal of Portfolio Management*, Fall 2018 ([Duke PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf); [Quantpedia summary](https://quantpedia.com/the-impact-of-volatility-targeting-on-equities-bonds-commodities-and-currencies)). More than 60 assets since 1926. For commodities, vol targeting barely changes the Sharpe ratio, but it **consistently reduces the likelihood of extreme returns and the volatility of volatility**. **Grade A** for the tail benefit. The rule: lots = (cash risk budget per day) / (σ_daily,$ per lot), with σ an EWMA of daily $ moves. It is the default overlay for T1/T2/T7.

### R2 Turtle drawdown rule

Each 10% drawdown from the peak cuts the equity used for sizing by 20% (Faith, T3). **Grade B** (practice, not a study). It is the simplest anti-ruin rule that keeps the strategy unchanged.

### R3 Fixed fraction per ATR

Size so that one ATR move costs a fixed fraction of equity: Turtle 1% per N(20), Clenow 0.2% per ATR(100), and 0.3–1% risk per trade to the stop in B4. **Grade B.** At $2,000 the lot floor binds (§6.1).

### R4 Stops must match the signal

K. Kaminski, A. Lo, "When do stop-loss rules stop losses?", *Journal of Financial Markets* 18, 234–254, 2014 ([MIT PDF](https://dspace.mit.edu/bitstream/handle/1721.1/114876/Lo_When%20Do%20Stop-Loss.pdf)). Under a random walk, stops always lower expected return. Under momentum (positive serial correlation), they can raise it. **Grade A** (theory plus evidence). Use stops on trend and breakout rules (T, B). On mean-reversion rules (M), prefer a time stop and smaller size over a price stop.

### R5 Worst-week exposure cap

This is our rule, derived from §6.1. It has no external source. Maximum oz held = (fraction of equity the owner accepts losing in the worst week) × Equity / (worst development-window weekly % move × P). It is computed at entry and caps every other sizing rule. **Grade:** arithmetic. Its value depends on the worst week chosen, so pre-register that choice. Development data alone includes March 2020.

### 6.2 Multiple testing

This survey hands about 27 rules, each with parameters, to the next step. Bartsch et al. (T6) show how many gold timing rules look good until a data-snooping test (Hansen's SPA) is applied. **The prereg should fix a small grid per rule, count every variant tried, and apply SPA / White's Reality Check, or a deflated-Sharpe haircut, before calling anything a finalist.**

---

## 7. Rejected (and why)

| Item | Source | Why rejected |
|---|---|---|
| "Gold-silver ratio strategy: 1,058% returns" | [RetailVest, dev.to](https://dev.to/retail_vest_1fd4e7c362443/gold-silver-ratio-strategy-how-1058-returns-tell-the-real-story-484c) | Promotional; no method or costs. |
| "Silver above GSR 60 beat gold by 3,852% since 1972" | [Global X](https://www.globalxetfs.com.au/insights/post/when-gold-takes-the-backseat-silver-grabs-the%20-wheel/) | A multi-decade allocation claim with few regime changes; ETF issuer; not a trading rule at our horizon. |
| Gold cTrader range bot, "14-year backtest, PF 1.16, DD 19.3%" | [ctrader.com product](https://ctrader.com/products/3918) | Vendor figures; rules not public. |
| "London killzone raised win rate 65% → 85%" | [Medium/coinmonks](https://medium.com/coinmonks/how-to-backtest-the-goldmine-strategy-for-consistent-gold-profits-bfa20d0925eb) | No method; win rate without payoff is meaningless. |
| "44% of London breakouts are fakeouts" | [RelicusRoad](https://relicusroad-md-website.pages.dev/blog/london-breakout-strategy) | Own untracked statistics; sells software. |
| SLV RSI < 30 with dollar weakness | [Coinrule](https://coinrule.com/slv-smart-automation) | Vendor page; no backtest. |
| Monthly silver seasonality ("February best, June worst", "July best") | [TickerLeague](https://tickerleague.com/commodities/silver/seasonality), [SentimenTrader](https://sentimentrader.com/blog/silver-meets-the-month-of-july), [Kitco/InvestingHaven](https://www.kitco.com/news/article/2024-09-09/silvers-biggest-gains-and-losses-happen-during-same-months-each-year-post) | Sources contradict each other. A Kruskal–Wallis test on monthly averages since 1960 finds no difference between months (p = 0.32; [Bullion Trading](https://bulliontradingllc.com/blog/best-month-to-buy-silver/)). Academic replications find no monthly effect for silver (S1). |
| Trader-survey "best time to trade gold" | [Traders Union](https://tradersunion.com/interesting-articles/gold-trading-time-analysis/) | Self-reported trader outcomes, not price data. |
| "Silver 50-day channel Sharpe 0.45 (Szakmary)" | [qgtm-docs](https://qgtm-docs.pages.dev/research/gold_silver/paper_szakmary_trend_following) | Cannot be matched to the paper (monthly data), and looks machine-written. The paper itself is kept as T5. |
| Mark Fisher ACD method | *The Logical Trader* (Wiley, 2002); [LuxAlgo summary](https://www.luxalgo.com/library/concept/acd-method/) | The A/C offsets are instrument-specific values Fisher published only for his futures. The public rules are incomplete, there is no published silver calibration and no independent evidence. A generic OR version is B1. |
| Sentiment-blog "silver is coiling" and similar setups | [SentimenTrader blog](https://sentimentrader.com/blog/silver-is-coiling) | Discretionary, event-picked studies; often written about hold-out-period prices. |
| COT positioning / hedging-pressure rules (Basu & Miffre 2013) | *Journal of Banking & Finance* | Credible for cross-sectional commodity portfolios, but needs weekly CFTC data that is not in the store, and is not a one-market rule. Could be added later with a COT download. |
| Chinese night-session effects (Ma, Bouri, Xu & Zhou 2025, *Global Finance Journal* 64) | [IDEAS](https://ideas.repec.org/a/eee/glofin/v64y2025ics1044028325000110.html) | Specific to SHFE session design; abstract not retrieved. It shows that intraday patterns move when trading hours change (cf. B6). |

---

## 8. What this suggests for the prereg step (not results)

1. **The best-evidenced families for silver are slow trend (T1, T2, T7, T4) and the sizing overlays (R1–R5).** They are the A/B rows, but on one market their expected Sharpe is modest. Their real job is to survive silver's squeezes, which is a sizing question first (§6.1).
2. **Intraday edges are documented in direction but thin in size** (B1, B2, B6, B7): silver is the least predictable precious metal (Urquhart), and its round trip is about $0.038/oz. Test only the variants with a liquidity-event rationale: the COMEX open, the London open, high-volatility days. Charge real spreads, and treat stop fills as worse than the M1 model (BALKE.md: 84% of gold stop entries filled worse).
3. **The silver-specific idea with a real academic basis is G3** (silver adjusts to gold). It has no published trading test, so it is a genuine hypothesis: pre-register it narrowly.
4. **Controls:** M1, M2, S1 and S2, so that the study shows what failure looks like on the same data.
5. **Clock work first:** every repo function above was written for gold's or BTC's clock. Silver's times are in §1.2 and must be time-zone-aware.
