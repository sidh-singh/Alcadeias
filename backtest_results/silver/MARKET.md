# Silver (XAGUSDm, Exness) as a market

The silver study, step `market`. Code: `backtesting/research/silver_market.py` (`sec` and `m1` passes). Tables: `backtest_results/silver/market/*.csv`.

**The data rule.** This step must not steer the choice of strategies with hold-out data.
- Every number about returns, trends, volatility, patterns, gold or sizing uses data **from 2017-11-01 to 2024-06-30 only** (warm-up, DEV and VAL). The loader drops every later bar, and an assertion checks this.
- For **2024-07-01 to 2026-11-13** (the hold-out), this report gives only data quality (holes, silences, flagged ticks) and spread levels in dollars. It gives no prices, returns or volatility.
- **Contamination, stated plainly:** the six demo designs' silver results for 2024-05 to 2026-11 were already seen (MULTISYMBOL.md), and silver's 2025-26 rally is public knowledge. While checking the flagged ticks, I printed one October 2025 price to my own console. It is not used anywhere here.

**Conventions.**
- **Prices:** M1 bid bars from `m1.npz`. Spreads come from the per-second bid/ask in `sec.npz`. Each quoted second counts once.
- **Session day:** the New York day shifted by +7 h. The Exness daily break (20:58 – 22:01 UTC in US summer, 21:58 – 23:01 in winter) is at 17:00 New York, so Sunday's open belongs to Monday. Days with fewer than 300 M1 bars (holiday stubs) are dropped from the daily series.
- **M1 returns:** used only inside one session day and when bars are at most 5 minutes apart. Gaps are measured separately (§4).
- **Hours** are UTC, as asked. US summer time shifts every session by one hour, which blurs the hour tables slightly.
- **t-statistics** are heteroskedasticity-robust. Events that overlap in time make them optimistic.
- **DEV** = 2018-11-01 – 2022-12-31, **VAL** = 2023-01-01 – 2024-06-30, **ALL** = 2017-11 – 2024-06.

---

## 0. The short version

1. **Silver is expensive to trade, relative to its moves.** Before 2024-07, the median spread was $0.038 – 0.043, about **21 bps** of price. Gold's was about **1.6 bps**, so silver costs about 13× more.
   - One spread is about **7 – 10% of a daily ATR** on silver, against about **1%** on gold (in 2018-19, when silver was quiet, it was about 16%).
   - On M5 bars one spread is **2.7 ATR(14)**, on M15 1.4, on H1 0.6, on H4 0.3 and on D1 0.1.
   - Anything that trades below H1 must beat a cost larger than the moves it is trying to catch.
2. **Silver is close to a random walk at every horizon from 1 minute to 1 month.**
   - Intraday (5 – 60 min) it mean-reverts slightly: variance ratio 0.91 – 0.95 (z = −2.6 to −3.3). This comes from DEV and fades in VAL.
   - From 2 days to 1 month the variance ratio is 0.99 – 1.08, not significant. Hurst-style exponents are 0.48 – 0.52.
   - Trend following can only earn from the **fat tails**: daily kurtosis is 9 in DEV, and the single worst day was −16% (2020-03-16). There is no steady persistence to earn from.
3. **Silver behaves like gold with about 1.5× gold's beta.**
   - Return correlation with gold rises from 0.69 at 1 minute to about 0.78 – 0.79 at 4 hours to 1 week. Silver's volatility is about 2.0× gold's in percent.
   - Gold leads silver by one minute, but the edge is tiny (corr 0.018) and far below the spread.
   - The gold/silver ratio ranged 64 – 124 and does not mean-revert reliably (Dickey-Fuller t −2.67, half-life 17 – 114 days depending on the period).
4. **One 0.01-lot silver unit carries about 1.2× the daily risk of a 0.01-lot gold unit**, with heavier tails.
   - Mean daily ATR was **$28 (DEV) – $31 (VAL)** per 0.01 lot, against gold's $23 – 26.
   - The worst day was **$217** per 0.01 lot against gold's $116, and the worst 5 days **$271** against $165.
   - On a $2,000 account, one silver unit's worst day was 11% of the balance.
5. **Hypotheses** (§9):
   - Worth testing: slow trend following on daily and H4 bars, small and volatility-targeted; a US-session breakout restricted to 12 – 16 UTC; gold as a filter.
   - Look hopeless: M1 – M15 scalping, grids and baskets, gap fades, seasonality and ratio reversion as stand-alone bots.

---

## 1. Volatility

### 1.1 By year (`vol_by_year.csv`)

| Period | Days | Mean close | Daily sd | Annualised | Median day range | ATR14 $ | ATR14 % | 99th pct \|day\| | Worst \|day\| | Kurtosis |
|---|---|---|---|---|---|---|---|---|---|---|
| 2018 | 258 | 15.68 | 1.04% | 16% | 1.46% | 0.257 | 1.64% | 3.5% | 4.2% | 1.8 |
| 2019 | 258 | 16.19 | 1.17% | 19% | 1.45% | 0.280 | 1.70% | 3.9% | 4.9% | 2.7 |
| 2020 | 259 | 20.54 | 2.74% | 44% | 2.88% | 0.760 | 3.62% | 7.9% | 16.1% | 7.2 |
| 2021 | 257 | 25.10 | 1.66% | 26% | 2.21% | 0.664 | 2.63% | 5.5% | 8.4% | 4.1 |
| 2022 | 258 | 21.75 | 1.84% | 29% | 2.58% | 0.621 | 2.87% | 4.9% | 8.4% | 1.8 |
| 2023 | 257 | 23.37 | 1.55% | 25% | 2.16% | 0.565 | 2.42% | 4.9% | 6.0% | 2.1 |
| 2024 H1 | 128 | 26.12 | 2.02% | 32% | 2.48% | 0.723 | 2.71% | 5.9% | 7.1% | 1.3 |
| **DEV** | 1074 | 20.64 | 1.91% | 30% | 2.24% | 0.567 | 2.66% | 7.0% | 16.1% | 9.2 |
| **VAL** | 385 | 24.28 | 1.72% | 27% | 2.22% | 0.618 | 2.52% | 5.3% | 7.1% | 1.8 |

- **There are two regimes.** Silver was quiet in 2018-19 (ATR about 1.65%). Since 2020 it has been about 2.4 – 3.6%.
- Dollar volatility rose 2.5× from 2018 to 2024, because both price and percent volatility rose.
- **A fixed lot is therefore a different risk in every year.** The sizing step must scale with ATR, not with a fixed lot ladder.

### 1.2 By hour of day, UTC (`vol_by_hour.csv`; H1 bars)

| UTC | Mean H1 range | Share of daily variance | Spread ÷ H1 range (median) |
|---|---|---|---|
| 00 | 0.34% | 2.1% | 0.79 |
| 01 | 0.57% | 5.6% | 0.44 |
| 02 – 06 | 0.24 – 0.46% | 1.1 – 3.3% each | 0.53 – 1.06 |
| 07 – 11 | 0.40 – 0.49% | 3.0 – 5.5% each | 0.49 – 0.62 |
| **12** | 0.71% | 9.6% | 0.36 |
| **13** | 0.93% | **12.5%** | **0.25** |
| **14** | 0.85% | 10.6% | 0.28 |
| **15** | 0.66% | 7.7% | 0.37 |
| 16 – 19 | 0.38 – 0.49% | 3.0 – 4.1% each | 0.50 – 0.71 |
| 20 – 23 | 0.20 – 0.31% | 0.3 – 2.0% each | 1.0 – 1.3 |

- **12 – 15 UTC carries 40% of the day's variance** (the US data releases and the COMEX open). It is also the only window where the spread is a small part of an hour's range.
- 01 UTC (the Shanghai open) is a smaller second peak.
- Around the daily break (20 – 23 UTC), one spread is larger than a typical hour's whole range.
- The shape is the same in DEV and VAL.

### 1.3 By weekday (`by_weekday.csv`)

Mean daily range is 2.43 – 2.55% on every weekday, so volatility has no weekday effect. Drift by weekday is in §7.

---

## 2. Trend persistence or mean reversion?

### 2.1 Lag-1 autocorrelation of non-overlapping returns (`persistence_ac1.csv`)

| Horizon | ALL | t | DEV | VAL | Gold, ALL (t) |
|---|---|---|---|---|---|
| 1 min | −0.015 | −1.4 | −0.016 | −0.001 | −0.021 (−9.2) |
| 5 min | −0.018 | −3.1 | −0.020 | −0.008 | −0.019 (−4.5) |
| 15 min | −0.015 | −1.8 | −0.020 | +0.009 | −0.008 (−1.4) |
| 1 h | −0.020 | −1.7 | −0.030 | +0.005 | −0.006 (−0.5) |
| 4 h | +0.005 | +0.2 | −0.005 | +0.036 | +0.006 (+0.3) |
| 1 day | +0.018 | +0.5 | +0.044 | −0.016 | +0.016 (+0.6) |
| 1 week | −0.056 | −0.7 | −0.090 | +0.034 | −0.078 (−1.2) |
| 1 month | +0.023 | +0.3 | +0.052 | −0.211 | +0.023 (+0.2) |

### 2.2 Variance ratios (Lo-MacKinlay, robust z; `persistence_vr.csv`)

| Horizon | VR, ALL | z | VR, DEV | VR, VAL (z) |
|---|---|---|---|---|
| 5 min (base 1 min) | 0.953 | −2.6 | 0.948 | 0.988 (−1.8) |
| 15 min | 0.924 | −3.3 | 0.914 | 0.979 (−1.8) |
| 60 min | 0.909 | −2.9 | 0.884 | 1.020 (+0.9) |
| 240 min | 0.958 | −0.9 | 0.924 | 1.095 (+2.4) |
| 2 days (base 1 day) | 1.019 | +0.5 | 1.043 | 0.986 |
| 5 days | 1.079 | +0.9 | 1.118 | 1.031 |
| 10 days | 1.016 | +0.1 | 1.015 | 1.099 |
| 21 days | 0.989 | −0.1 | 1.042 | 0.904 |

### 2.3 Local Hurst exponents (variance scaling between horizons; `persistence_hurst.csv`)

| Range | ALL | DEV | VAL |
|---|---|---|---|
| 1 → 5 min | 0.48 | 0.48 | 0.49 |
| 5 → 15 min | 0.50 | 0.50 | 0.50 |
| 15 → 60 min | 0.50 | 0.49 | 0.52 |
| 60 → 240 min | 0.50 | 0.50 | 0.51 |
| 1 day → 1 week | 0.52 | 0.53 | 0.52 |
| 1 week → 1 month | 0.44 | 0.46 | 0.38 |

**The reading.**
- **Intraday (5 – 60 min):** mild mean reversion, VR about 0.91 – 0.95. It is strongest in DEV and has nearly gone in VAL, where 4 h even leans to continuation (VR 1.095, z +2.4).
- **Daily to weekly:** a faint tendency to continue (VR 1.02 – 1.08, H 0.52), not significant.
- **Weekly to monthly:** a faint reversal (H 0.38 – 0.46), from few observations.
- **Overall, silver is a random walk with fat tails.** It is no more trending than gold.

### 2.4 Hit rates of simple breakouts and fades (`events_breakout_fade.csv`)

**The events:**
- **Donchian:** the close breaks the prior 20-bar high or low (55 bars also on D1).
- **Band:** the close crosses a 2-sd band of the 20-bar mean.
- **Shock:** a bar body larger than 2 × ATR(14).

**The measure:** the forward move after K bars, in the signal's direction, in units of the bar's prior ATR(14). The fade is the opposite trade. Both pay the spread once.

| TF | Family | K | n | Hit (continue) | Forward (ATR) | t | DEV | VAL | Spread (ATR) | Net, continue | Net, fade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M5 | Donchian 20 | 5 | 36,185 | 45.7% | −0.078 | −6.5 | −0.073 | −0.060 | **2.69** | −2.76 | −2.61 |
| M5 | Band | 5 | 26,935 | 45.9% | −0.074 | −4.9 | −0.053 | −0.068 | 2.82 | −2.89 | −2.75 |
| M15 | Donchian 20 | 5 | 11,533 | 45.9% | −0.091 | −4.1 | −0.088 | −0.081 | **1.43** | −1.52 | −1.34 |
| M15 | Shock | 20 | 4,050 | 48.3% | +0.053 | +0.6 | +0.030 | +0.169 | 1.61 | −1.56 | −1.67 |
| H1 | Donchian 20 | 20 | 2,668 | 48.6% | +0.142 | +1.8 | +0.241 | −0.056 | **0.60** | −0.46 | −0.75 |
| H1 | Shock | 5 | 1,160 | 50.1% | +0.114 | +1.4 | +0.074 | +0.221 | 0.68 | −0.56 | −0.79 |
| H4 | Donchian 20 | 5 | 755 | 50.2% | +0.080 | +1.2 | +0.190 | −0.156 | **0.28** | −0.20 | −0.36 |
| H4 | Band | 1 | 588 | 51.1% | +0.076 | +1.9 | +0.059 | +0.154 | 0.30 | −0.22 | −0.38 |
| D1 | Donchian 20 | 1 | 130 | 55.0% | +0.128 | +1.8 | +0.180 | +0.144 | **0.10** | **+0.03** | −0.23 |
| D1 | Donchian 55 | 20 | 67 | 50.7% | +0.768 | +1.1 | +1.271 | −0.799 | 0.10 | +0.66 | −0.87 |
| D1 | Band | 1 | 99 | 55.1% | +0.134 | +1.5 | +0.206 | +0.250 | 0.11 | +0.03 | −0.24 |

(The full grid is in the CSV: 48 rows, K = 1, 5, 20.)

- **M5 and M15:** breakouts reverse slightly (hit rate 45 – 47%, t up to −6.5). So a fade has the right sign, but it earns 0.03 – 0.15 ATR against a spread of 1.4 – 2.8 ATR. Both directions lose heavily.
- **H1 and H4:** breakouts continue slightly (+0.06 – 0.14 ATR), but the sign flips between DEV and VAL and stays below the spread.
- **D1:** the only timeframe where the gross edge reaches the cost.
  - The 20-day breakout's next day earns +0.13 ATR, positive in both DEV and VAL, against a 0.10 ATR spread.
  - The 55-day breakout's 20-day gain is large but comes from DEV only and reverses in VAL (n = 67).
  - Hit rates stay near 50%. Any daily trend edge lives in the size of the winners, not in how often they win.

---

## 3. Spikes and big moves within minutes (`spikes_by_year.csv`, `spikes_top_m5.csv`)

**How often a bar's range is at least 3× its own prior ATR(14):** 10 – 15 per 1,000 M1 bars, 12 – 16 per 1,000 M5 bars and 15 – 26 per 1,000 M15 bars, in every year.

**Moves measured against the daily ATR:**

| Year | M15 bars with range ≥ 0.5 daily ATR | M15 ≥ 1 daily ATR | M5 ≥ 1 daily ATR |
|---|---|---|---|
| 2018 | 54 | 3 | 1 |
| 2019 | 63 | 3 | 1 |
| 2020 | 119 | 21 | 14 |
| 2021 | 77 | 4 | 3 |
| 2022 | 52 | 2 | 0 |
| 2023 | 61 | 0 | 0 |
| 2024 H1 | 45 | 1 | 0 |

**The largest 5-minute ranges:**

| Time (UTC) | Range | Daily ATRs | Per 0.01 lot |
|---|---|---|---|
| 2020-03-16 12:55 | $1.69 | 2.3 | $84 |
| 2021-08-08 22:50 – 22:55 (the Sunday-open flash crash) | $0.83 + $1.13 | 1.6 + 2.2 | $42 + $57 |
| 2020-12-21 10:05 | $1.30 | 1.7 | $65 |
| 2020-07-28 03:00 – 07:35 | three bars over 1.1 daily ATRs | | |

**What this means for the bots:** a design that holds an open basket without a stop must survive moves of 1 – 2 daily ATRs within 5 minutes. They happened several times a year in 2020-21 and roughly once a year otherwise.

---

## 4. Gaps (`gaps_summary.csv`, `gaps_events.csv`)

A gap is the first bid after a pause of 30 minutes or more, minus the last bid before it. It is measured in the daily ATR(14) of the day before.

| Kind | n | Median \|gap\| | Median (ATR) | 99th pct (ATR) | Largest | Share > 1 ATR | Refilled within 4 h | Median / largest per 0.01 lot |
|---|---|---|---|---|---|---|---|---|
| Sunday open | 329 | $0.030 | 0.06 | 0.66 | 1.64 ATR ($1.47, 2021-01-29 → Feb 1, +5.5%) | 0.3% | 72% | $1.5 / $73.5 |
| Daily break | 1,320 | $0.010 | 0.02 | 0.14 | 0.27 ATR | 0% | 92% | $0.5 / $11.9 |
| Holiday closures | 73 | $0.024 | 0.05 | 0.61 | 0.86 ATR | 0% | 68% | $1.2 / $24.1 |
| Other silences of 30+ min | 19 | $0.023 | 0.05 | 0.23 | 0.24 ATR | 0% | 79% | |

- The median gap is about the size of one spread or smaller, so there is nothing to fade.
- Weekend gaps are a tail risk, not an opportunity. A few per year exceed 0.25 ATR, and a large one is an unhedged loss for any position held over the weekend.

---

## 5. Spreads

### 5.1 By period (from `sec.npz`; `spread_by_bucket.csv`)

| Period | Median | Mean | p90 | p99 |
|---|---|---|---|---|
| 2018 | $0.043 | $0.041 | $0.045 | $0.050 |
| 2019 | $0.034 | $0.035 | $0.039 | $0.044 |
| 2020 | $0.054 | $0.050 | $0.067 | $0.067 |
| 2021 | $0.054 | $0.059 | $0.067 | $0.067 |
| 2022 | $0.038 | $0.039 | $0.047 | $0.054 |
| 2023 | $0.038 | $0.040 | $0.047 | $0.047 |
| 2024 H1 | $0.047 | $0.044 | $0.047 | $0.047 |
| **Pre-cut, pooled** | **$0.043** | $0.045 | $0.067 | $0.067 |
| 2024 H2 *(hold-out)* | $0.042 | $0.043 | $0.047 | $0.047 |
| 2025 *(hold-out)* | $0.037 | $0.038 | $0.042 | $0.090 |
| 2026 to Nov 13 *(hold-out)* | $0.030 | $0.032 | $0.042 | $0.050 |
| **Hold-out, pooled** | **$0.030** | $0.036 | $0.044 | $0.060 |

**Compared with gold, before the cut:** the median M1 spread was gold $0.22 (1.6 bps) and silver $0.038 (20.9 bps). Per daily ATR, that is about 1% for gold and 7% for silver.

### 5.2 By UTC hour (`spread_by_hour.csv`)

- **Before the cut:** the median is flat at $0.042 – 0.045 all day, rising to $0.047 at 22 – 23 UTC (after the break).
- **Hold-out:** the median is $0.030 at most hours. It is $0.033 – 0.035 at 12 – 15 UTC and $0.040 at 21 UTC (the edge of the break). The mean is highest at 22 UTC ($0.042).
- The spread barely changes by hour. What changes is the volatility (§1.2), so **cost relative to movement is lowest at 12 – 16 UTC.**

---

## 6. Silver and gold (`gold_corr.csv`, `gold_leadlag_1m.csv`, `gold_predictive.csv`, `ratio_*.csv`)

### 6.1 Return correlation by horizon

| Horizon | ALL | DEV | VAL | Lowest year | Highest year | Beta (silver % per gold %) |
|---|---|---|---|---|---|---|
| 1 min | 0.69 | 0.67 | 0.73 | 0.61 (2020) | 0.74 | 1.40 |
| 5 min | 0.73 | 0.72 | 0.76 | 0.68 | 0.77 | 1.49 |
| 15 min | 0.75 | 0.74 | 0.76 | 0.71 | 0.79 | 1.53 |
| 1 h | 0.77 | 0.77 | 0.78 | 0.75 | 0.80 | 1.56 |
| 4 h | 0.79 | 0.79 | 0.78 | 0.77 | 0.81 | 1.55 |
| 1 day | 0.78 | 0.78 | 0.77 | 0.75 | 0.83 | 1.58 |
| 1 week | 0.79 | 0.81 | 0.75 | 0.68 (2024 H1) | 0.84 | 1.66 |
| 1 month | 0.72 | 0.71 | 0.73 | 0.63 | 0.86 | 1.48 |

In percent, silver's volatility is about **2.0× gold's** at every horizon.

### 6.2 Lead-lag of 1-minute returns

- **Gold leads by 1 minute:** corr(silver now, gold a minute earlier) = **0.018** (t = 7.6). This holds identically in DEV and VAL.
- **Silver does not lead gold:** 0.003 (t = 1.2).
- **Beyond one minute** every lag from 2 to 60 minutes is below 0.006. At 5, 15, 30 and 60 minutes, gold's last return does not predict silver's next (|corr| ≤ 0.02, with the sign changing between DEV and VAL).
- **Not tradeable:** a 0.018 correlation on 1-minute returns (sd about 3 bps) is worth a small fraction of a basis point against a 21 bps spread. Part of it is also unsynchronised quoting.

### 6.3 The gold/silver ratio

| Period | Mean | Min | Max |
|---|---|---|---|
| 2018 | 81.1 | 76.1 | 86.3 |
| 2019 | 86.2 | 79.3 | 93.3 |
| 2020 | 89.1 | 69.7 | **124.1** (March) |
| 2021 | 72.0 | **64.2** | 80.9 |
| 2022 | 83.3 | 75.2 | 95.4 |
| 2023 | 83.3 | 76.7 | 91.3 |
| 2024 H1 | 85.0 | 73.2 | 91.7 |

- **AR(1) on the daily log ratio:** Dickey-Fuller t = −2.67 (ALL, 1,717 days; the 5% critical value is about −2.86), so a random walk cannot be rejected.
  - Half-life: 86 days (ALL), 114 (DEV) and 17 (VAL). It is not stable.
- **Fading a 60-day z-score beyond ±2** (64 events): the ratio reverted 59% of the time over 5 days (+0.12%) but only 55% over 20 days, with a mean of −0.35% (it kept going).
- **No usable mean reversion.** A ratio trade would also need two legs, two symbols and two bots.

---

## 7. Seasonality (`season_month.csv`, `by_weekday.csv`, `vol_by_hour.csv`)

**Calendar months** (2017-12 – 2024-06; only 6 – 7 years per month):
- December: +5.2% (6 of 7 up, t = 2.1).
- October: +2.8% (5 of 6, t = 1.8).
- September: −6.2% (t = −1.8).
- February: −3.2% (1 of 7 up, t = −1.3).
- **With 12 months tested, about 0.6 results with |t| > 2 are expected by chance. None is credible.**

**Weekdays:**
- Wednesday: +18 bps (55% up, t = 2.1), positive in both DEV (+20) and VAL (+26).
- The other days: −10 to +5 bps, t below 1.
- With 5 tests, Wednesday is borderline. Its 18 bps is about one spread (21 bps), so it has no value as a bot by itself.

**Hours (drift within the hour):**
- 23 UTC: +2.3 bps per hour (t = 3.7). This is the only hour that survives a 24-test correction.
- 10 UTC: −1.3 bps (t = −1.8).
- Both are about a tenth of a spread. At most they could time entries; they are not a strategy.

---

## 8. The size of one 0.01-lot unit (`unit_size.csv`)

One 0.01 lot of XAGUSD is 50 oz, so a $1 move is **$50**. One 0.01 lot of XAUUSD is 1 oz, so a $1 move is **$1**.

| Period | Silver ATR14 per 0.01 lot | Gold ATR14 per 0.01 lot | Silver ÷ gold | Silver 99th pct day | Gold 99th pct day | Silver worst day | Gold worst day | Silver worst 5 days | Gold worst 5 days |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | $12.8 | $12.2 | 1.05 | $28 | $22 | $31 | $30 | $49 | $39 |
| 2019 | $14.0 | $15.5 | 0.90 | $34 | $30 | $46 | $34 | $82 | $89 |
| 2020 | $38.0 | $30.2 | 1.26 | $98 | $73 | **$217** | $116 | **$271** | $165 |
| 2021 | $33.2 | $23.9 | 1.39 | $72 | $41 | $117 | $64 | $184 | $125 |
| 2022 | $31.0 | $25.6 | 1.21 | $52 | $52 | $84 | $58 | $134 | $132 |
| 2023 | $28.3 | $23.9 | 1.18 | $56 | $47 | $63 | $69 | $123 | $121 |
| 2024 H1 | $36.2 | $30.5 | 1.19 | $89 | $62 | $107 | $82 | $179 | $119 |
| **DEV** | **$28.4** | $23.3 | 1.22 | $84 | $52 | $217 | $116 | $271 | $165 |
| **VAL** | **$30.9** | $26.1 | 1.19 | $67 | $53 | $107 | $82 | $179 | $121 |

- **Before the cut, a silver unit carried about 1.2× a gold unit's typical daily risk.** Its tails were 1.3 – 1.9× gold's.
- **On a $2,000 account**, one 0.01 lot of silver moved about 1.4 – 1.5% of the balance on a typical day (one ATR), and 11% on the worst day (2020-03-16).
- **The unit's risk is not fixed.** It scales as 50 oz × price × ATR%:
  - ATR% was 1.6 – 1.7% in 2018-19 and 2.4 – 3.6% from 2020 to 2024 H1.
  - At the 2020 – 24 typical ATR of about 2.6%, one 0.01 lot carries about **1.3 × (the silver price in $)** dollars of daily ATR.
  - The hold-out prices are not used here. The sizing step should plug in the price at the time of trading, which today's live quote gives.
- **Margin is not the constraint:** at 1:2000, one 0.01 lot of silver needs well under $1 of margin. Risk, not margin, limits the size.

---

## 9. Data quality, every period (`quality_by_bucket.csv`, `quality_events.csv`)

| Period | Quoted seconds per active day | Weekday silences 5 – 30 min | 30 min – 2 h | Holiday closures | Daily break, median (max) min | Flagged ticks¹ | Seconds with spread > 10× the month median | Seconds with ask ≤ bid |
|---|---|---|---|---|---|---|---|---|
| 2018 | 14,750 | 23 | 0 | 11 | 62 (79) | 0 | 0 | 0 |
| 2019 | 13,630 | 112 | 1 | 10 | 62 (76) | 0 | 0 | 0 |
| 2020 | 21,010 | 5 | 1 | 11 | 62 (64) | 6 (2020-03-16/18, crash) | 0 | 0 |
| 2021 | 16,810 | 102 | 1 | 11 | 63 (66) | 0 | 0 | 0 |
| 2022 | 13,160 | 110 | 4 | 9 | 64 (66) | 0 | 31 | 0 |
| 2023 | 15,370 | 94 | 1 | 9 | 64 (68) | 0 | 0 | **831** (Feb 2023) |
| 2024 H1 | 20,080 | 30 | **10** | 9 | 64 (74) | 0 | 0 | 0 |
| 2024 H2 *(hold-out)* | 25,760 | 9 | 0 | 6 | 63 (65) | 0 | 0 | 0 |
| 2025 *(hold-out)* | 29,750 | 6 | 1 (2025-01-03, 63 min) | 12 | 63 (66) | 18 | **27,446** (Oct 2025) | 0 |
| 2026 *(hold-out, to Nov 13)* | 48,260 | 4 | 0 | 8 | 64 (93) | 6 (2026-01-30) | 59 | 0 |

¹ A flagged tick is a one-second bid jump of more than 0.5% that the next quote undoes to within 0.15%.

**What the table shows:**
- **No months are missing** (109 of 109).
- **No weekday holes of 8 hours or more**, as the multi-symbol gate found.
- **Quote density rises steadily.** In 2026 there are three times as many quoted seconds per day as in 2018.

**Things the backtests must handle:**
- **April 2024 (VAL):** about ten daily breaks ran long or shifted, for example 22:02 → 23:59 UTC (1.95 h) on 04-08, 04-16, 04-18 and 04-30, and 23:00 → 23:59 on 04-10, 04-11 and 04-15. The engine refuses orders after 30 minutes without a quote, so a bot cannot trade then.
- **February 2023:** 831 seconds with a zero or inverted spread. A cost model must not book negative costs there.
- **October 2025 (hold-out): a spread stress episode.**
  - 27,446 seconds had spreads above 10× the month median. The widest was $1.50.
  - At the Sunday open of 2025-10-12 (22:13 – 22:18 UTC), quotes flickered between two levels about 1.3% apart with $0.25 – 0.40 spreads. Most of 2025's 18 flagged ticks are there.
  - The exam step's cost model will meet this in the hold-out. No setting should be tuned to it.
- **Fast markets:** the 2020-03-16 and 2026-01-30 flags happened on fast-market days and are probably real quotes, not bad data.

---

## 10. What the evidence suggests (hypotheses, not results)

These follow from the pre-cut data only. Each one has to be tested against costs in DEV, confirmed in VAL, and taken to the hold-out once.

**Families that might work:**

1. **Slow trend following, daily (and perhaps H4).** Examples: Donchian/Turtle breakouts, time-series momentum, moving-average trend.
   - **For:** D1 is the only timeframe where the spread (0.1 ATR) is small against the moves. The 20-day breakout's next day was positive in both DEV and VAL. Fat tails (kurtosis up to 9, days of 8 – 16%) reward strategies that let winners run.
   - **Against:** persistence is statistically absent (VR about 1, H about 0.5). Hit rates are about 50%, so the payoff must come from a few large trends, with long flat or losing stretches between them. This matches the earlier Turtle result on silver: its one-unit stream made money, but the account was sized up and then wiped.
   - **To test:** an exit that limits each trade's loss (an ATR stop or channel exit), and volatility-targeted size.
2. **US-session (12 – 16 UTC) intraday breakout on M15 – H1**, of the Balke Range Breakout or ATR Breakout kind.
   - **For:** this window carries 40% of the variance at the lowest cost per unit of movement (spread about 0.25 – 0.37 of an H1 range).
   - **Against:** H1 breakouts' gross edge (+0.06 – 0.14 ATR) is below the average H1 spread, and it changed sign between DEV and VAL.
   - **The case is weak:** test it once, with a tight trading window.
3. **Gold as a filter, not a signal.** Correlation is about 0.78 at 4 h – 1 week and silver's beta is about 1.5. A silver trend trade taken only when gold's trend agrees might cut false breakouts. There is no direct evidence yet. The 1-minute gold lead is real but worth nothing after costs.
4. **Sizing as the strategy's half.**
   - A silver unit's daily risk moved 2.5× between 2018 and 2024, and the worst day was 11% of $2,000 per 0.01 lot.
   - Any silver bot needs size set from the current ATR in dollars, a per-trade risk cap and an account-level stop, not a fixed lot ladder.
   - Every candidate should be judged by its result after sizing, with a ruin check.

**Families that look hopeless:**

1. **Scalping, grids, DCA baskets and fades on M1 – M15** (including the bot's basket designs).
   - The statistical mean reversion exists (VR 0.91 – 0.95), but it is worth 0.03 – 0.15 ATR against a spread of 1.4 – 2.8 ATR.
   - Designs without a stop also face 1 – 2 daily-ATR moves within 5 minutes several times a year.
   - This is consistent with the multi-symbol study, where none of the basket designs qualified on silver.
2. **Fading gaps at the Sunday open or the daily break.** The median gap is at or below one spread.
3. **Calendar and weekday seasonality as a bot.** The samples are small and multiple testing explains the few |t| about 2 results. The best effects (Wednesday +18 bps, 23 UTC +2 bps) are no larger than a spread.
4. **Gold/silver ratio reversion.** Unit-root behaviour, an unstable half-life, 55% reversion over 20 days with a negative mean, and two symbols needed.

**Cautions for the next steps:**
- Silver's 2020 behaviour (the crash, the squeeze, the flash crashes) dominates the DEV tails. VAL is calmer.
- A rule tuned on 2020 may learn the outliers, not the market.
- Spreads in dollars have drifted over time. A backtest must use the archive's own per-second spreads, not a constant.
