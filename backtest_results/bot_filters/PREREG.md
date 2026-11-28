# Entry filters on the bots' designs (MA200 on 1H/4H/1D and the rest): pre-registration

Written 28 Nov 2026 on `backtest_hedging`, before any filter below was run on these designs. The sha256 of this file
is in `PREREG.md.sha256`. Every later change of a rule is a deviation, logged in `DEVIATIONS.md` with its reason and
written before the result it could affect exists.

## 1. The question

The owner asked (28 Nov 2026): test the 200 moving average on the 1-hour, 4-hour and daily charts ("every other
possibility", the daily too) and other filters on the designs the bots run, to "improve the score even further".

The five designs (the final-ten study, `backtest_results/final10/FINAL10.md`):

| Design | Symbol | Engine | FINAL10 score (5 periods up) |
|---|---|---|---|
| V3-lite | XAUUSDm | tick engine | 3.09 (5 of 5) |
| Top 1 | XAUUSDm | tick engine | 3.92 (3 of 5, not eligible) |
| Top 2 | XAUUSDm | tick engine | 6.20 (3 of 5, not eligible) |
| Top 2 | BTCUSDm | tick engine | 4.49 (4 of 5) |
| Turtle S2 + bot votes | BTCUSDm | M1-bar model | 4.65 (5 of 5, warm evidence) |

1. Does any entry filter raise a design's score without costing more than 10% of its profit?
2. Does it hold on data no design or filter was chosen on?
3. Which filter, if any, should be proposed for the live bots? Live changes are the owner's decision and are not part
   of this study.

## 2. How the designs are run (no engine change)

**Tick designs:**
- They run on the tick engine exactly as FINAL10 runs them: `E.live_config(symbol, start, end)` with
  `F.own_designs(symbol)[name]`, prepared with `["M1","M5","M15","H1","H4"]`.
- Nothing under `backtesting/engine/`, `config.py` or the live files is edited, so no committed result goes stale.
- The filter enters through the existing backtest-only argument `fast.run(cfg, prep, regime=(times_ms, values))`. It
  gates new baskets only: Top 1's add and every exit are untouched, and a blocked poll leaves the pause and agreement
  state alone.
- All four designs gate on the H1 trend (the sign of the MACD signal line of the last closed H1 bar). The regime is
  therefore composed as:

      regime(T) = trend_H1(T) if the filter allows that side at T, else 0

  An always-allow filter must reproduce each design fill for fill. This identity check runs before any variant.

**The Turtle:**
- It runs on `external.py`'s M1-bar model as FINAL10 runs it: `X.filtered(X.turtle(m, 2).plan, m, sig.votes_at)`.
- Its filters are one-sided gates on the plan: `plan.copy(alw_l=..., alw_s=..., m_l=..., m_s=...)`. Only first fills
  are gated; pyramid adds are not. The no-op gate must reproduce $7,814.72 over 8 years.

**Accounts:** $2,000, nothing withdrawn, the unit rule (floor(balance / 2,500) + 1, at most 10), Exness bid/ask on
every fill, no swap, stop-out at equity 0. These are the settings of every published number. The live branches' 50%
account share and their per-symbol steps are not used.

## 3. The filters

Each filter says, at every moment, whether a long is allowed and whether a short is allowed.

**Bars and timing:**
- Values come from CLOSED bars only:
  - H1 and H4: the bid bars on UTC boundaries;
  - D1: UTC days, with a day of fewer than 360 M1 bars merged into the next (`external.day_bars`, as study 1 and
    FINAL10's 200-day filter).
- A bar's value takes effect at the first tick at or after its close.
- Indicators are computed over the full history from the symbol's data start, with Pine semantics.

| Id | Definition | Timeframes | Count |
|---|---|---|---|
| SIDE(n) | long iff close > SMA(n); short iff close < SMA(n); n = 50, 100, 200 | H1, H4, D1 | 9 |
| SLOPE(n) | long iff SMA(n) > SMA(n) 5 bars earlier; short iff below | H1, H4, D1 | 9 |
| TREND(n) | SIDE(n) and SLOPE(n) together | H1, H4, D1 | 9 |
| CROSS | long iff SMA(50) > SMA(200); short iff below | H1, H4, D1 | 3 |
| LGATE200 | longs only while close > SMA(200); shorts always allowed | H1, H4, D1 | 3 |
| SGATE200 | shorts only while close < SMA(200); longs always allowed | H1, H4, D1 | 3 |
| TSI | long iff the TSI(5, 25) of study 1 is above 0; short iff below | H1, H4, D1 | 3 |
| LARSI | long iff the Laguerre RSI (alpha 0.2) is above 50; short iff below | H1, H4, D1 | 3 |
| QQE | longs blocked on a RED QQE MOD bar, shorts blocked on a BLUE one; GRAY allows both | H1, H4, D1 | 3 |
| VWRSI | long iff the volume-weighted RSI(14) is above 50; short iff below; BTC on Binance volume | H1, H4, D1 | 3 |
| RIB | long iff the Trend Target Ribbon's trend is up; short iff down (the TradeIQ 2027 study's port) | H1, H4, D1 | 3 |
| MSD | long iff the Market Structure Dashboard's bias is LEAN BULL or BULLISH; short iff LEAN BEAR or BEARISH; chart = that timeframe, closed higher-timeframe rows | H1, H4, D1 | 3 |
| HA | long iff the last closed Heikin Ashi candle is bullish; short iff bearish | H1, H4, D1 | 3 |
| SESS-KZ | entries only 02:00-05:00 or 07:00-11:00 New York time (Session Hunter's kill zones) | none | 1 |
| SESS-LN | entries only 02:00-11:00 New York time | none | 1 |

- That is 59 single filters per design.
- The indicator ports are study 1's verified `tradeiq_ind.py` and the TradeIQ 2027 study's reconciled ports. The RIB,
  MSD and HA rows run once those ports have passed their reconciliation.

**Stage 2 (pre-registered here):** for each design, the AND of every pair among its three best single filters by
Development score. A pair is formed only from filters that beat the base's score; if fewer than two do, there are no
pairs. That is at most 3 pairs per design.

**Turtle exits** (information and candidates; the Turtle is the only design whose exits can be changed without the
engine):
- HA-M1: exit at a Heikin Ashi colour flip against the position, on H4 and on D1.
- HA-M4: exit when the Heikin Ashi streak reaches its rare age (the 90th percentile, computed causally), on H4 and on D1.
- If these need an edit of `external.py`, they are dropped and that is logged.

**Size:** 59 × 5 = 295 single variants, up to 15 pairs, and 4 Turtle exit variants. Every variant counts in the
multiple-testing report.

## 4. Windows

**Development:** FINAL10's 23 evidence quarters, each a fresh $2,000 account:

| Period | Quarters |
|---|---|
| 2021 | H1-H4: 2021-01-01, 04-01, 07-01, 10-01 to 2022-01-01 |
| 2022 | H5-H8: 2022-01-01 to 2023-01-01 by quarters |
| 2023 | F1 2023-02-01 to 05-01; F2 to 08-01; F3 to 11-01; F4 2023-11-01 to 2024-01-01 |
| 2024-25 | C1-C6: 2024-01-01 to 2025-07-01 by quarters |
| 2025-26 | HO1 2025-08-13 to 11-13; HO2 to 2026-02-13; OOS2 to 05-13; OOS1 to 08-13; IS 2026-08-13 to 11-13 |

- Plus one continuous 5-year account, 2021-11-13 to 2026-11-13. It is used for the multiple-testing statistics and
  for information.
- Tick designs run per second, with one loop timing (FINAL10's 8y/5y mode). Windows are cut from one prepare of
  2021-01-01 to 2026-11-13 per symbol, which is exact in per-second mode.
- These quarters are in-sample for the designs, which were tuned on 2023-2026, but no filter has been chosen on them.

**Sealed test windows.** They are computed only after `FINALISTS.md` and its sha256 exist; a guard in the code
refuses them before that.
- **T1, 2018-11-13 to 2021-01-01, both symbols:** a stub quarter 2018-11-13 to 2019-01-01, then the eight calendar
  quarters of 2019-2020, each a fresh $2,000 account; plus one continuous account over the window (FINAL10's "new"
  window).
- **T2, 2017-01-03 to 2018-11-13, gold only:** the quarters of 2017 and of 2018 to 2018-10-01, plus a stub 2018-10-01
  to 2018-11-13; plus one continuous account.
  - No study has ever scored this window.
  - It needs gold's 2016 ticks, which are downloaded first, for the warm-up of the H1 designs (600 H1 bars) and of
    the D1 SMA(200).
  - If the download fails, T2 starts at the first day on which every finalist's filter is warmed up, and that is
    logged.
- BTC has no unread history: its archive starts in 2018-01, and the D1 SMA(200) exists only from late July 2018.

**Not clean on T1.** These design-filter pairs were run on T1 before; their T1 verdict is reported as "not a clean test":
- gold V3-lite × SIDE(200) D1 (FINAL10's 200-day filter, same definition);
- gold Top 1 × SIDE(200) D1 and SIDE(50) H4 (the ladder study's EMA200-D1 and EMA50-H4 gates on 2018-11 to 2024-11:
  same idea, EMA instead of SMA);
- Turtle × SIDE(200) D1 and Turtle × LGATE200 D1 (printed by a planning probe on 28 Nov 2026, never used);
- on BTC, study 1 showed MA200 filters helping indicator rules in 2019-2022. That is a soft leak at the level of the
  idea, not of these pairs.

**Forward (information only):** 2026-11-13 to the data end. It has not been read by any design choice.

## 5. The score and "better"

**The score** is FINAL10's selection yardstick (`final10.evidence`):
- Each period's value is the mean net profit per quarter of its fresh $2,000 accounts.
- score = (mean of the five period values) / max(worst quarter's max drawdown %, 1).
- FINAL10's eligibility needs at least 4 of 5 periods up, no account wiped, a worst-quarter drawdown of at most 50%,
  and a mean above 0. It is reported for every variant.

The base designs are recomputed in exactly the same format, on today's store, before any variant runs.

**A variant is "better" than its base** in Development when all of these hold:
1. its score is higher than the base's;
2. it has no fewer periods up than the base;
3. its mean profit per quarter is at least 90% of the base's. This is the profit floor: the owner has turned down
   lower drawdown at a large cost in profit (FINAL10 §10);
4. no account is wiped, and its worst-quarter drawdown is at most 50%.

**Candidates and finalists:**
- Candidates: per design, the three "better" variants (single, pair or Turtle exit) with the highest Development
  scores.
- Confirmation, tick designs only: the candidates and the base are rerun on the 23 quarters on raw ticks under eight
  loop timings, using the median per quarter (FINAL10's round-4 format; `live_timing(seed)`, seeds 1-8). A candidate
  must still be "better" in that format. The Turtle's model has no loop timing, so it needs no confirmation.
- Finalists: per design, up to the two confirmed candidates with the highest confirmed score.
- `FINALISTS.md` (rule rows and code blob ids) and its sha256 are then written, before T1 or T2 is computed for
  anything.
- A design with no "better" variant has no finalist. Its answer is "no filter improved it".

## 6. The exam

On each sealed window, a finalist is compared with its base design over the same window.
- The format is the median of eight raw-tick timings per quarter for the tick designs, and the M1-bar model for the
  Turtle. The per-second figures are shown beside them.
- A finalist **passes a window** when:
  1. its score over the window's quarters is at least the base's; and
  2. its mean profit per quarter is at least 90% of the base's, or at least the base's when the base's mean is 0 or
     below.
- Gold finalists must pass T1 and T2; BTC finalists must pass T1.
- The verdict also reports the continuous accounts (final equity, max drawdown, CAGR / drawdown) and the forward
  period.

**Accounts for the comparison page:**
- For every finalist and its base, after the exam: 8 years (2018-11-13 to 2026-11-13), 5 years and the new window per
  second; the last year on raw ticks with eight timings (median and range).
- These are labelled as mixing in-sample and test data.
- Daily equity curves are kept for the owner's comparison page (`backtest_results/compare/`).

## 7. Multiple testing

- **SPA:** Hansen's SPA p-value for "some variant beats the base", over all of a design's variants, on the daily
  profit-and-loss differences of their 5-year accounts.
- **Deflated Sharpe:** for the best variant, the deflated Sharpe ratio of its 5-year daily returns, given the number of
  variants.

## 8. Deliverables

- `RESULTS.md`: the answer per design in plain English, with the exam verdicts and what would and would not go live.
- CSVs: every variant's per-quarter results; the confirmation runs; the exam; the accounts; daily equity.
- PNG graphs and a section of the comparison page.
- **Code:**
  - `backtesting/research/bot_filters.py`: the filters, the regime composition, the guard, the runs;
  - `tests/test_bot_filters.py`: the identity checks, causality (a filter value never precedes its bar's close) and
    the guard.
- Committed and pushed to `backtest_hedging` at each checkpoint (the owner's standing rule of 28 Nov 2026).
