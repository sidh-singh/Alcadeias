# Strategies from the literature on gold and BTC, alone and with the bot's logic

**The question.** Which published trading strategies give the best equity with the least drawdown on
XAUUSDm and BTCUSDm, on this account? Do they do better when combined with the bot's own logic?

**How it was answered.** Ten strategies with published, codeable rules were taken from two literature
searches. Each was coded once with its published default parameters, plus at most one alternative set
the sources give. None was tuned. All were run on the same M1 bars, spread and $2,000 account (the
bot's unit rule) over three periods: 2023, 2024 – mid-2025 and mid-2025 – Nov 2026. Each was run
standalone, with the risk sizing its source prescribes, and combined with the bot's logic in two ways.
V3-lite, the bot's best design so far, is the reference row.

Status: research only. Nothing in the live bot or the backtest engine was changed.

## The short version

All figures are average net USD per quarter in 2023 / 2024-25 / 2025-26. Each period is one continuous
$2,000 account using the bot's unit rule. Max DD is the worst of the three periods, measured from the
running peak of equity. Nothing was wiped except where a row says so.

1. **On gold, slow trend following made money in all three periods. Most of it came from the 2025-26
   trends.**

   | Strategy | 2023 / 2024-25 / 2025-26 per quarter | Max DD | Trades a quarter |
   |---|---|---|---|
   | Supertrend (ATR 10 × 3) on H4, always in | +$42 / +$84 / +$1,340 | 24% | 9.5 |
   | Supertrend on H4, long only (steadier: 2 of 15 fresh quarters lost) | +$40 / +$187 / +$496 | 24% | 4.7 |
   | 41 / 356 moving-average cross on M5 | +$14 / +$153 / +$534 | 33% | 82 |
   | Asian-range / London breakout | +$11 / +$189 / +$298 | 29% | 49 |
   | Donchian ensemble, published vol-targeted sizing | +$3 / +$197 / +$203 | 23% | 0.9 |

   In 2023 none of them made more than about $50 a quarter. In 2025-26 Supertrend made $3,895 in one
   quarter, and three trades made $4,855 of its $7,336. That is the positive-skew profile the sources
   describe: many small losses and a few very large trends. Gold's run in this data (from about $2,060
   at the start of 2024 to $5,590 at the end of January 2026, then back to $3,880) suits it. The same London rules
   read on the UTC clock lose money (−$8 / −$1 / −$8), so that result depends on the session hours
   chosen.
2. **On BTC nothing makes much.**
   - The best rows were the Turtle System 1 sized at 1% of equity per N (+$140 / +$282 / +$40, DD 21%)
     and the Donchian ensemble with its published sizing (+$118 / +$134 / −$8, DD 14%).
   - The Turtle row could size only 30 of its 59 signals with a 0.01-lot minimum (the rest are taken
     at zero size). Its 2024-25 profit came from two trends, Feb–Mar and Oct–Dec 2024.
   - The 50-day-SMA long / cash rule made +$50 / +$84 / +$10 (DD 14%).
   - The intraday rules lose on BTC: the noise area, the last half hour and the 22:00 UTC hour.
3. **The losers and the controls.**
   - The last half-hour momentum trade loses on both symbols.
   - Connors RSI(2) is flat to negative on gold.
   - The Turtle with bot sizing reaches an 84% drawdown on gold.
   - The Turtle at 1% risk cannot trade gold at all after 2023, because 0.01 lot is already more than
     1% of $2,000 per N.
4. **The bot's votes or the H1 trend as a filter on these strategies' entries (variant a) is not a
   reliable improvement.**
   - On gold the filter raised the three-period total in 10 of 20 strategy / parameter pairs (votes)
     and 10 of 20 (H1 trend). It was better in all three periods in only 3 of 20 for each filter.
   - On BTC: 11 of 18 and 11 of 18 pairs; better in all three periods in 6 and 4 of 18.
   - The H1 trend barely changes the trend followers, which already trade with it.
5. **V3-lite entries kept only in the strategy's own regime (variant b) mostly lower V3-lite's
   drawdown.** At bar level on gold, V3-lite alone made +$22 / +$97 / +$70 with a 39% drawdown. Of the
   five regimes with default parameters, four cut the drawdown and three raised the total:

   | Regime added to V3-lite | Max DD | Three-period total |
   |---|---|---|
   | none (V3-lite alone) | 39% | +$1,043 |
   | TSMOM | 24% | +$1,360 |
   | Donchian ensemble | 25% | +$1,464 |
   | D1 close above / below its 200-day SMA (from RSI(2)) | 25% | +$1,881 |
   | H4 Supertrend, both directions | 34% | +$988 |
   | M5 SMA 41 / 356 | 42% | +$505 |
   | H4 Supertrend, long only (the alternative set) | 14% | +$1,180 |

   2023 stays between −$50 and +$22 a quarter in every variant. On BTC, the TSMOM regime made +$417
   (DD 7%) against V3-lite's +$171 (DD 15%).
6. **The V3-lite reference row understates V3-lite as the bot runs it.**
   - The live bot reads its votes on the still-forming bar. This study reads them on closed bars, as
     the task requires.
   - On the same quarters the tick engine itself, with closed-bar votes, gives about what this
     simulator gives. Gold: +$35 / +$93 / +$77 against +$22 / +$89 / +$94. The two trade lists match
     trade by trade, apart from path details.
   - The tick engine with forming-bar votes reproduces the published V3-lite: +$103 / +$142 / +$385
     with one loop timing, against +$106 / +$152 / +$404 published.
   - So against V3-lite as the bot would run it, Supertrend H4 is ahead only in 2025-26. On fresh
     quarterly accounts, the bot's own format, it made +$39 / +$90 / +$761.
   - The variant (b) filters were measured on closed bars only. Applying them to the live-style V3-lite
     needs an engine change, which was not made.

**What this suggests.**
- **Gold:** the one new rule worth a further test is Supertrend (10, 3) on H4. It is simple, trades
  rarely and is positive in all three periods, and its worst drawdown was 24% (32% on a fresh
  quarterly account). The long-only version has the smoother curve. Its H4 direction, long only, is
  also the best regime filter found for V3-lite (drawdown 39% → 14%).
- **BTC:** no strategy here is clearly worth trading. The slow trend rules are slightly positive with
  drawdowns under 25%.
- **Next:** freeze this shortlist before any further data is run.
  - Run Supertrend H4 (always in and long-only) on raw ticks.
  - Run V3-lite with the H4-Supertrend regime inside the tick engine, with forming-bar votes as live.

## The ten strategies

Chosen for different families and for evidence that could be coded from bars. Rules as coded (default
parameters; the alternative set in brackets).

| # | Strategy (family) | Rules as coded | Risk-sized row (as the source prescribes) | Sources |
|---|---|---|---|---|
| 1 | **Time-series momentum, TSMOM** (momentum, D1) | Signal S = mean of the signs of the 1-, 3- and 12-month returns (gold 21 / 63 / 252 trading days, BTC 30 / 91 / 365 days). Long if S > 0, short if S < 0, held for a month and reset at each month start; no stop. [12-month sign only, "MOP-12"] | notional = S × equity × 40% / σ; σ = EWMA volatility, 60-day centre of mass, of returns up to the day before; capped at 2× equity; monthly | Moskowitz, Ooi & Pedersen 2012 (JFE); Hurst, Ooi & Pedersen (AQR) |
| 2 | **Turtle breakout** (breakout, D1 + intraday stop orders) | System 1. A buy stop 1 tick above the 20-day high, a sell stop below the 20-day low, filled intraday. A breakout is skipped when the previous breakout would have won (tracked hypothetically, taken or not); only the 55-day breakout is then taken. Stop 2N (N = 20-day Wilder true range). One unit more every ½ N in favour, up to 4, with every stop then 2N from the last fill. Exit at the 10-day low / high. [System 2: 55-day entry, 20-day exit] | unit = 1% of equity per N, rounded down; the notional equity cut 20% for every 10% drawdown from the year's start | The Original Turtle Trading Rules (Faith et al.) |
| 3 | **Donchian ensemble** (trend following, D1) | Nine models, lookbacks 5, 10, 20, 30, 60, 90, 150, 250 and 360 days. Long when the close is the n-day highest close. The stop is the Donchian midline at entry, raised to each day's midline, never lowered; out on a close at or below it. Long only. Bot-sized row: unit lots while at least 5 of the 9 models are long. [long and short, the paper's appendix] | hold the mean over models of min(25% / σ90, 2) × equity in notional; σ90 = 90-day realised volatility; resized on a signal, or when the size is more than 20% off | Zarattini, Pagani & Barbon 2025, "Catching Crypto Trends" |
| 4 | **Long-horizon moving average** (trend following) | Gold: M5 closes, always in, long while SMA(41) > SMA(356), short below. [34 / 339] BTC: daily close above SMA(50) = long, else flat. [BTC alternative: the gold rule] | none prescribed | Urquhart, Batten, Lucey, McGroarty & Peat (gold M5, 2008-2014); Grayscale 2023 summary (BTC) |
| 5 | **Supertrend** (trend following, H4) | ATR(10, Wilder); lines at (H + L) / 2 ± 3 ATR that only move in the trend's favour. Long on a close above the down-line, short on a close below the up-line. Always in, no other stop. [long only] | none prescribed (optional in the source) | KivancOzbilgic's Pine script; HackerNoon test on Exness ticks; BoringEdge; Quantzee |
| 6 | **Asian-range / London breakout** (breakout, gold) | Range = high and low of 03:00-08:00 server time, taken as New York + 7 h (the usual broker clock). Traded only if the range is 0.30-1.60% of price. OCO stop orders at the range ± max(2 spreads, 5% of the range). Stop at the far side, capped at 0.6% of price. Target 2.5 R; stop to break-even after 1.5 R; flat and orders cancelled at 21:00 server. [the same hours read on Exness's UTC clock] **BTC instead** (no sessions): a buy stop at the previous daily close + ATR(2) of daily bars, stop 8%, out at the end of the day (Unger style) | 1% of equity at risk (gold) | MQL5 blog 777540; Backtrex; Kathy Lien; Cryptonomist |
| 7 | **Noise-area intraday momentum** (intraday momentum) | At every :00 and :30 inside the session: bounds = max / min(today's open, yesterday's close) × (1 ± the average absolute move from the open at that time of day over the last 14 sessions). Long above the upper bound, short below the lower. Exit when price falls back below max(upper bound, session VWAP), or rises above min(lower bound, VWAP) for a short. Flat at the session end. Sessions: gold COMEX 08:20-13:30 New York; BTC the UTC day. [gold: broker day 18:00-16:30 New York] | exposure = min(4, 2% / σ14 of daily returns) × equity | Zarattini, Aziz & Barbon 2024, "Beat the Market" |
| 8 | **Last half-hour momentum** (momentum, timed) | Gold: at 13:00 New York, trade the sign of the return since yesterday's 13:30 close; out at 13:30. [the return to 08:50] BTC proxy: the return from yesterday's 16:00 to 15:30 New York, held 15:30-16:00. [the return to 10:00] | none prescribed | Gao, Han, Li & Zhou 2018; Baltussen, Da, Lammers & Martens 2021; Shen, Urquhart & Wang 2022 |
| 9 | **Connors RSI(2)** (mean reversion, D1) | Long when the close is above SMA(200) and RSI(2) < 5; out when the close is above SMA(5) or below SMA(200). Short mirror-image (RSI(2) > 95). No stop. [10 / 90] | none prescribed (a vendor test went all in) | Connors & Alvarez via StockCharts; Backtrex |
| 10 | **Bitcoin MAX / MIN** (other: trend plus dip-buy, D1) | Long for the next day when the close is the highest or the lowest close of the last 10 days; otherwise flat. [hold 22:00-00:00 UTC every day, the same paper's seasonality]. Run on gold too, though it is outside the source's scope | none prescribed | Padysak & Vojtko 2022 (Quantpedia) |
| ref | **V3-lite** (the bot's design, bar level) | On each closed M15 bar, all of these: the H1 votes say BUY (SELL), both M15 votes agree, the H1 trend agrees, and the time is inside the bot's trading window (gold Mon 01:00 – Fri 22:00 UTC, BTC all week). Stop = target = 8 H1 volatility units. 12 h pause after a loss, 5 min after a win | – | IMPROVEMENT.md |

**Left out.**
- **The 5-minute opening-range breakout:** an independent CFD replication found the edge goes to zero
  after retail spreads, and BTC has no opening range.
- **TTM Squeeze:** no credible backtest on gold or BTC; it is described as a filter rather than a
  system.
- **Clenow's EMA 50 / 100 breakout with an ATR trail:** the same family as numbers 2, 3 and 5.
- **MACD + 200 EMA:** negative in the independent tests; its useful part, the trend filter, is
  already the bot's H1 trend.
- **Grid / DCA bots:** the bot's own ladder family, already tested in `recovery_mechanisms.md`.
- **Volatility targeting, ATR sizing and the Chandelier exit:** an overlay, not a strategy. It is
  tested as the risk-sized rows of numbers 1, 2, 3, 6 and 7, including the Turtle drawdown brake.

## How the bot's logic was added

- **(a) The strategy's entries, kept only when the bot agrees.** Two separate rows; the task's "the
  bot's own votes agree … or the H1 trend agrees" is read as two alternatives.
  - **+ bot votes**: both of the bot's M15 votes (the RSI and MACD pivot-slope votes, `votes()` on
    the last closed M15 bar) point in the trade's direction.
  - **+ H1 trend**: the sign of the H1 MACD(12, 26, 9) signal line on the last closed H1 bar is the
    trade's direction.
  - Exits stay the strategy's own.
  - A rule whose entry is a state (TSMOM, the moving-average rules, Supertrend, the Donchian
    ensemble, MAX / MIN) enters at the first decision bar at which the state and the filter agree.
  - A timed or event entry is dropped when the filter disagrees. A stop order stays in place and
    fills on a later touch when the filter agrees.
  - Sizing is the bot's unit rule.
- **(b) V3-lite's entries (the reference row), kept only when the strategy's own trend or regime state
  agrees,** with V3-lite's exits. The regime is read on the strategy's last closed bar:

  | Strategy | Regime used |
  |---|---|
  | TSMOM | the direction it holds |
  | Donchian ensemble | long while any model is long (alternative: the sign of the net count) |
  | Moving-average rule | gold: SMA(41) against SMA(356) on M5; BTC: close above SMA(50), longs only |
  | Supertrend | the H4 trend (alternative: longs only while up) |
  | RSI(2) | close above / below SMA(200) |

  The Turtle, the session breakouts, the noise area, the last half hour and MAX / MIN have no trend or
  regime filter in their rules, so they have no row (b).

## The test

- **Data.**
  - M1 bid bars of the Exness tick store from 2022-12-01 on. December 2022 only warms the indicators
    up; nothing earlier is read.
  - Ask = bid + the bar's mean spread. Per 0.01 lot, gold pays $1 per 1.00 of price and BTC $0.01.
  - No swap is charged; the bot's backtester treats the Standard account as swap-free.
- **Periods** (UTC, [start, end)): 2023-02-01 – 2024-01-01, 2024-01-01 – 2025-07-01 and
  2025-07-01 – 2026-11-13.
  - Each period is its own $2,000 account. It starts flat, with indicators that see all earlier
    history, and whatever is open at the end is closed at the last close.
  - "Per quarter" = net / the period's length in quarters (3.66, 5.99 and 5.48).
  - "Losing quarters" counts the period's calendar quarter blocks in which equity fell.
  - The top-5 tables also give the bot's own format: a fresh $2,000 account in each of the tick
    engine's quarter blocks.
- **Signals and fills.**
  - Signals are read on closed bars of the strategy's timeframe: UTC bars, with gold's short Sunday
    evening merged into Monday.
  - An order is filled at the next M1 open, a buy at the ask and a sell at the bid.
  - Intraday rules decide at fixed clock times and need a quote within three minutes to enter.
- **Stops, targets, adds and stop orders** are checked on every M1 bar.
  - A gap is filled at the open.
  - The unfavourable extreme is taken first, so a bar that reaches both the stop and the target is a
    stop.
  - A stop order filled inside a bar can be stopped in that bar but cannot reach its target there.
- **Sizing.**
  - The bot's rule: unit = floor(balance / 2,500) + 1, at most 10, set when a position opens.
  - Risk-sized rows round down to 0.01 lot. A trade the budget cannot buy is taken at zero size, so
    the strategy's sequence of trades does not change. The CSV counts these as `skipped_trades`.
- **Drawdown and wipe-out.** Max drawdown is measured from the running peak of equity at M1 closes,
  with troughs at the worst price inside each M1 bar. An account is wiped when that worst-price equity
  reaches 0.
- **No tuning.** Every parameter is the published default; one alternative set is used where a source
  gives one. Every variant run is in the tables.
- **2023 data warm-up.** Data from Dec 2022 cannot fill the longest lookbacks in 2023:
  - TSMOM's 12-month sign is missing until about December 2023; the missing horizon counts as 0, the
    paper's own convention for a model that is not formed yet.
  - The 250- and 360-day Donchian models and the 200-day SMA also start late.
- **No look-ahead** (`tests/test_external.py`, 67 tests, about a minute).
  - Every strategy and parameter set, the bot's two filters, V3-lite and V3-lite with a regime make
    the same decisions and trades up to a time T when the history after T is cut off, or replaced by
    a +50% jump or a −40% crash.
  - The cuts include points one to four minutes after the strategy's own entry and exit decisions.
  - Before relying on this, 15 deliberate look-ahead bugs were injected into the builders, V3-lite and
    the filters, each reading one bar or a few minutes too far. The test caught all 15.
  - The simulator has its own tests: spread paid, stop before target, gaps, stop orders, pyramid,
    break-even, pause, sizing, the brake, wipe-out, drawdown, the target book.

**V3-lite at bar level and in the tick engine.** The bar-level simulator was checked against the tick
engine on V3-lite, quarter by quarter.
- With the votes read on closed bars in both, the two make almost the same trades. In Q2 2024 on
  gold, 13 of the engine's 14 baskets are in the bar-level list on the same side: 12 in the same
  minute, 1 six minutes later, all with fills within $0.41.
- The remaining differences:
  - The engine re-enters inside an M15 bar after the 5-minute cooldown; the bar level waits for the
    next close.
  - The engine closes a BTC position at a hole in the archive and then pauses for 6.3 days; the bar
    level ignores the 8 holes of more than 3 h.
  - Tick fills differ from bar fills by cents. A stop $0.30 away was touched in one case and not in
    the other.
- The large difference is the votes. The live bot reads them on the still-forming bar, and that
  reading is worth two to five times more on gold (table "V3-lite three ways" below).

## Results

Rows: each strategy standalone, risk-sized as its source prescribes, and with the bot's logic, (a) and
(b). The V3-lite reference is at bar level.

<!-- tables:begin -->

### XAUUSDm: default parameters

| Strategy | Variant | 2023 / q | 2024-25 / q | 2025-26 / q | Total, 3 periods | Max DD | Trades / q | Losing quarters | Wiped |
|---|---|---|---|---|---|---|---|---|---|
| V3-lite, bar level (reference) | standalone | +$22 | +$97 | +$70 | +$1,043 | 39% | 17.3 | 6 of 16 | no |
| Time-series momentum | standalone | −$100 | +$129 | +$238 | +$1,708 | 40% | 1.0 | 5 of 16 | no |
| Time-series momentum | risk-sized: 40% vol target per instrument, 2x cap, monthly | −$67 | +$149 | +$338 | +$2,501 | 29% | 0.7 | 4 of 16 | no |
| Time-series momentum | + bot votes | −$85 | +$121 | +$290 | +$2,002 | 38% | 1.0 | 6 of 16 | no |
| Time-series momentum | + H1 trend | −$104 | +$126 | +$223 | +$1,591 | 39% | 1.0 | 6 of 16 | no |
| Time-series momentum | V3-lite + regime | −$50 | +$175 | +$90 | +$1,360 | 24% | 10.6 | 6 of 16 | no |
| Turtle Donchian breakout | standalone | −$132 | +$148 | +$205 | +$1,529 | 84% | 2.3 | 9 of 16 | no |
| Turtle Donchian breakout | risk-sized: 1% of equity per N, 20% cut per 10% drawdown | −$4 | $0 | $0 | −$13 | 15% | 0.1 | 1 of 16 | no |
| Turtle Donchian breakout | + bot votes | −$152 | +$219 | +$15 | +$835 | 82% | 2.2 | 10 of 16 | no |
| Turtle Donchian breakout | + H1 trend | −$132 | +$148 | +$205 | +$1,529 | 84% | 2.3 | 9 of 16 | no |
| Donchian ensemble, vol-targeted | standalone | −$27 | +$162 | +$206 | +$1,997 | 29% | 1.7 | 4 of 16 | no |
| Donchian ensemble, vol-targeted | risk-sized: 25% vol target, 2x cap, 20% rebalance threshold | +$3 | +$197 | +$203 | +$2,302 | 23% | 0.9 | 3 of 16 | no |
| Donchian ensemble, vol-targeted | + bot votes | +$8 | +$176 | +$202 | +$2,188 | 30% | 1.3 | 2 of 16 | no |
| Donchian ensemble, vol-targeted | + H1 trend | −$27 | +$168 | +$206 | +$2,033 | 29% | 1.6 | 4 of 16 | no |
| Donchian ensemble, vol-targeted | V3-lite + regime | −$18 | +$177 | +$86 | +$1,464 | 25% | 10.6 | 3 of 16 | no |
| Long-horizon moving-average rule | standalone | +$14 | +$153 | +$534 | +$3,890 | 33% | 82.0 | 3 of 16 | no |
| Long-horizon moving-average rule | + bot votes | +$32 | +$63 | +$953 | +$5,717 | 29% | 59.6 | 3 of 16 | no |
| Long-horizon moving-average rule | + H1 trend | +$6 | +$102 | +$504 | +$3,388 | 38% | 58.5 | 4 of 16 | no |
| Long-horizon moving-average rule | V3-lite + regime | +$22 | +$65 | +$6 | +$505 | 42% | 16.3 | 7 of 16 | no |
| Supertrend | standalone | +$42 | +$84 | +$1,340 | +$7,992 | 24% | 9.5 | 4 of 16 | no |
| Supertrend | + bot votes | +$44 | +$16 | +$569 | +$3,368 | 38% | 9.5 | 5 of 16 | no |
| Supertrend | + H1 trend | +$47 | +$74 | +$1,356 | +$8,040 | 25% | 9.4 | 4 of 16 | no |
| Supertrend | V3-lite + regime | +$4 | +$97 | +$72 | +$988 | 34% | 14.5 | 6 of 16 | no |
| Asian-range / London breakout | standalone | +$11 | +$189 | +$298 | +$2,802 | 29% | 48.7 | 4 of 16 | no |
| Asian-range / London breakout | risk-sized: 1% of equity at risk | −$7 | +$160 | +$10 | +$989 | 12% | 31.1 | 3 of 16 | no |
| Asian-range / London breakout | + bot votes | +$6 | +$22 | +$64 | +$502 | 28% | 43.8 | 7 of 16 | no |
| Asian-range / London breakout | + H1 trend | −$0 | +$62 | +$258 | +$1,787 | 16% | 41.1 | 3 of 16 | no |
| Noise-area intraday momentum with VWAP trail | standalone | +$55 | +$17 | +$4 | +$326 | 25% | 58.2 | 6 of 16 | no |
| Noise-area intraday momentum with VWAP trail | risk-sized: 2% daily vol target, 4x cap | +$166 | +$30 | +$64 | +$1,138 | 9% | 40.5 | 3 of 16 | no |
| Noise-area intraday momentum with VWAP trail | + bot votes | +$30 | +$35 | −$25 | +$184 | 24% | 28.9 | 7 of 16 | no |
| Noise-area intraday momentum with VWAP trail | + H1 trend | +$22 | +$17 | +$14 | +$256 | 22% | 43.2 | 5 of 16 | no |
| Last half-hour intraday momentum | standalone | −$21 | −$5 | −$36 | −$303 | 20% | 64.3 | 12 of 16 | no |
| Last half-hour intraday momentum | + bot votes | −$6 | +$3 | +$11 | +$56 | 6% | 13.0 | 8 of 16 | no |
| Last half-hour intraday momentum | + H1 trend | −$12 | +$1 | −$28 | −$190 | 17% | 49.2 | 12 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | standalone | −$1 | +$21 | −$64 | −$234 | 37% | 1.0 | 4 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + bot votes | +$17 | +$25 | −$54 | −$85 | 38% | 0.6 | 1 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + H1 trend | $0 | −$5 | $0 | −$32 | 5% | 0.1 | 1 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | V3-lite + regime | −$0 | +$177 | +$150 | +$1,881 | 25% | 10.6 | 4 of 16 | no |
| Bitcoin 10-day MAX / MIN composite (outside its source's scope) | standalone | +$0 | +$48 | +$357 | +$2,246 | 46% | 11.6 | 6 of 16 | no |
| Bitcoin 10-day MAX / MIN composite (outside its source's scope) | + bot votes | +$43 | +$64 | −$13 | +$470 | 72% | 5.3 | 4 of 16 | no |
| Bitcoin 10-day MAX / MIN composite (outside its source's scope) | + H1 trend | +$1 | −$3 | +$198 | +$1,070 | 38% | 7.3 | 8 of 16 | no |

### XAUUSDm: alternative parameter sets

| Strategy | Variant | 2023 / q | 2024-25 / q | 2025-26 / q | Total, 3 periods | Max DD | Trades / q | Losing quarters | Wiped |
|---|---|---|---|---|---|---|---|---|---|
| Time-series momentum | standalone | +$6 | +$208 | +$129 | +$1,975 | 49% | 0.3 | 3 of 16 | no |
| Time-series momentum | risk-sized: 40% vol target per instrument, 2x cap, monthly | +$6 | +$208 | +$105 | +$1,846 | 46% | 0.3 | 3 of 16 | no |
| Time-series momentum | + bot votes | +$16 | +$209 | +$195 | +$2,380 | 40% | 0.3 | 2 of 16 | no |
| Time-series momentum | + H1 trend | −$3 | +$211 | +$126 | +$1,940 | 50% | 0.3 | 4 of 16 | no |
| Time-series momentum | V3-lite + regime | +$2 | +$177 | +$63 | +$1,414 | 25% | 8.4 | 2 of 16 | no |
| Turtle Donchian breakout | standalone | −$224 | +$831 | −$109 | +$3,567 | 87% | 1.3 | 8 of 16 | no |
| Turtle Donchian breakout | risk-sized: 1% of equity per N, 20% cut per 10% drawdown | −$31 | $0 | $0 | −$112 | 15% | 0.1 | 1 of 16 | no |
| Turtle Donchian breakout | + bot votes | −$212 | +$828 | −$84 | +$3,725 | 85% | 1.2 | 8 of 16 | no |
| Turtle Donchian breakout | + H1 trend | −$224 | +$831 | −$109 | +$3,567 | 87% | 1.3 | 8 of 16 | no |
| Donchian ensemble, vol-targeted | standalone | −$26 | +$73 | +$147 | +$1,151 | 47% | 3.2 | 7 of 16 | no |
| Donchian ensemble, vol-targeted | risk-sized: 25% vol target, 2x cap, 20% rebalance threshold | −$8 | +$125 | +$122 | +$1,384 | 31% | 2.2 | 6 of 16 | no |
| Donchian ensemble, vol-targeted | + bot votes | −$8 | +$86 | +$28 | +$644 | 38% | 2.3 | 5 of 16 | no |
| Donchian ensemble, vol-targeted | + H1 trend | −$26 | +$104 | +$161 | +$1,412 | 46% | 3.0 | 7 of 16 | no |
| Donchian ensemble, vol-targeted | V3-lite + regime | −$43 | +$176 | +$120 | +$1,556 | 25% | 12.8 | 5 of 16 | no |
| Long-horizon moving-average rule | standalone | +$28 | +$244 | +$416 | +$3,846 | 40% | 90.6 | 2 of 16 | no |
| Long-horizon moving-average rule | + bot votes | +$48 | +$112 | +$568 | +$3,956 | 31% | 65.4 | 4 of 16 | no |
| Long-horizon moving-average rule | + H1 trend | +$15 | +$132 | +$421 | +$3,146 | 41% | 62.7 | 3 of 16 | no |
| Long-horizon moving-average rule | V3-lite + regime | +$22 | +$65 | +$6 | +$504 | 42% | 16.3 | 7 of 16 | no |
| Supertrend | standalone | +$40 | +$187 | +$496 | +$3,982 | 24% | 4.7 | 3 of 16 | no |
| Supertrend | + bot votes | +$42 | +$62 | +$395 | +$2,690 | 25% | 4.6 | 5 of 16 | no |
| Supertrend | + H1 trend | +$35 | +$185 | +$490 | +$3,920 | 24% | 4.7 | 3 of 16 | no |
| Supertrend | V3-lite + regime | +$7 | +$112 | +$88 | +$1,180 | 14% | 8.7 | 4 of 16 | no |
| Asian-range / London breakout | standalone | −$8 | −$1 | −$8 | −$81 | 47% | 52.4 | 8 of 16 | no |
| Asian-range / London breakout | risk-sized: 1% of equity at risk | −$49 | −$37 | +$30 | −$239 | 20% | 32.7 | 7 of 16 | no |
| Asian-range / London breakout | + bot votes | +$29 | −$7 | −$70 | −$316 | 38% | 46.8 | 8 of 16 | no |
| Asian-range / London breakout | + H1 trend | +$3 | −$10 | +$83 | +$406 | 17% | 45.6 | 8 of 16 | no |
| Noise-area intraday momentum with VWAP trail | standalone | −$57 | +$81 | +$90 | +$774 | 35% | 184.6 | 8 of 16 | no |
| Noise-area intraday momentum with VWAP trail | risk-sized: 2% daily vol target, 4x cap | −$136 | +$69 | +$59 | +$241 | 31% | 132.1 | 6 of 16 | no |
| Noise-area intraday momentum with VWAP trail | + bot votes | −$22 | +$64 | +$84 | +$761 | 34% | 88.6 | 8 of 16 | no |
| Noise-area intraday momentum with VWAP trail | + H1 trend | −$28 | +$91 | +$99 | +$982 | 41% | 118.6 | 5 of 16 | no |
| Last half-hour intraday momentum | standalone | −$18 | +$7 | −$40 | −$247 | 19% | 64.3 | 11 of 16 | no |
| Last half-hour intraday momentum | + bot votes | −$3 | +$5 | +$2 | +$30 | 7% | 20.2 | 10 of 16 | no |
| Last half-hour intraday momentum | + H1 trend | −$10 | +$7 | −$30 | −$159 | 16% | 48.1 | 12 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | standalone | −$1 | +$59 | −$65 | −$7 | 44% | 1.8 | 4 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + bot votes | +$2 | +$22 | −$96 | −$386 | 46% | 1.0 | 3 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + H1 trend | $0 | −$5 | +$15 | +$52 | 5% | 0.1 | 1 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | V3-lite + regime | −$0 | +$177 | +$150 | +$1,881 | 25% | 10.6 | 4 of 16 | no |
| Bitcoin 10-day MAX / MIN composite (outside its source's scope) | standalone | +$10 | +$10 | −$12 | +$28 | 13% | 36.8 | 8 of 16 | no |
| Bitcoin 10-day MAX / MIN composite (outside its source's scope) | + bot votes | +$1 | +$8 | +$6 | +$81 | 5% | 9.8 | 7 of 16 | no |
| Bitcoin 10-day MAX / MIN composite (outside its source's scope) | + H1 trend | −$1 | +$6 | +$10 | +$90 | 7% | 19.4 | 8 of 16 | no |

### BTCUSDm: default parameters

| Strategy | Variant | 2023 / q | 2024-25 / q | 2025-26 / q | Total, 3 periods | Max DD | Trades / q | Losing quarters | Wiped |
|---|---|---|---|---|---|---|---|---|---|
| V3-lite, bar level (reference) | standalone | −$0 | +$29 | −$1 | +$171 | 15% | 27.5 | 7 of 16 | no |
| Time-series momentum | standalone | −$4 | +$55 | +$70 | +$697 | 14% | 1.1 | 8 of 16 | no |
| Time-series momentum | risk-sized: 40% vol target per instrument, 2x cap, monthly | −$16 | +$87 | +$75 | +$873 | 33% | 1.1 | 8 of 16 | no |
| Time-series momentum | + bot votes | −$2 | +$58 | +$60 | +$667 | 14% | 1.1 | 9 of 16 | no |
| Time-series momentum | + H1 trend | −$5 | +$66 | +$61 | +$711 | 14% | 1.1 | 9 of 16 | no |
| Time-series momentum | V3-lite + regime | −$8 | +$37 | +$41 | +$417 | 7% | 16.1 | 8 of 16 | no |
| Turtle Donchian breakout | standalone | +$64 | +$27 | +$55 | +$696 | 51% | 3.9 | 8 of 16 | no |
| Turtle Donchian breakout | risk-sized: 1% of equity per N, 20% cut per 10% drawdown | +$140 | +$282 | +$40 | +$2,425 | 21% | 2.0 | 5 of 16 | no |
| Turtle Donchian breakout | + bot votes | +$76 | +$54 | +$98 | +$1,143 | 48% | 3.2 | 8 of 16 | no |
| Turtle Donchian breakout | + H1 trend | +$70 | +$27 | +$60 | +$740 | 50% | 3.8 | 8 of 16 | no |
| Donchian ensemble, vol-targeted | standalone | +$40 | +$66 | −$1 | +$537 | 12% | 2.4 | 8 of 16 | no |
| Donchian ensemble, vol-targeted | risk-sized: 25% vol target, 2x cap, 20% rebalance threshold | +$118 | +$134 | −$8 | +$1,190 | 14% | 2.4 | 8 of 16 | no |
| Donchian ensemble, vol-targeted | + bot votes | +$14 | +$31 | −$3 | +$219 | 12% | 2.0 | 11 of 16 | no |
| Donchian ensemble, vol-targeted | + H1 trend | +$40 | +$66 | −$4 | +$520 | 12% | 2.4 | 8 of 16 | no |
| Donchian ensemble, vol-targeted | V3-lite + regime | +$18 | +$39 | −$10 | +$250 | 9% | 16.9 | 8 of 16 | no |
| Long-horizon moving-average rule | standalone | +$50 | +$84 | +$10 | +$743 | 14% | 2.8 | 8 of 16 | no |
| Long-horizon moving-average rule | + bot votes | +$41 | +$54 | −$23 | +$345 | 15% | 1.8 | 8 of 16 | no |
| Long-horizon moving-average rule | + H1 trend | +$50 | +$83 | +$13 | +$756 | 13% | 2.6 | 8 of 16 | no |
| Long-horizon moving-average rule | V3-lite + regime | +$17 | +$35 | −$7 | +$237 | 9% | 12.1 | 7 of 16 | no |
| Supertrend | standalone | −$3 | +$12 | +$12 | +$124 | 21% | 13.3 | 7 of 16 | no |
| Supertrend | + bot votes | +$7 | +$40 | +$15 | +$350 | 23% | 12.9 | 5 of 16 | no |
| Supertrend | + H1 trend | +$4 | +$22 | +$15 | +$225 | 21% | 13.2 | 7 of 16 | no |
| Supertrend | V3-lite + regime | +$4 | −$0 | −$53 | −$275 | 21% | 22.3 | 9 of 16 | no |
| Asian-range / London breakout | standalone | +$17 | +$31 | +$2 | +$256 | 10% | 15.5 | 6 of 16 | no |
| Asian-range / London breakout | + bot votes | +$7 | +$27 | −$4 | +$164 | 8% | 11.3 | 8 of 16 | no |
| Asian-range / London breakout | + H1 trend | +$10 | +$34 | −$0 | +$241 | 10% | 14.4 | 7 of 16 | no |
| Noise-area intraday momentum with VWAP trail | standalone | −$43 | −$82 | −$11 | −$708 | 29% | 284.4 | 12 of 16 | no |
| Noise-area intraday momentum with VWAP trail | risk-sized: 2% daily vol target, 4x cap | −$165 | −$29 | +$33 | −$592 | 40% | 280.2 | 10 of 16 | no |
| Noise-area intraday momentum with VWAP trail | + bot votes | −$6 | −$62 | +$29 | −$235 | 29% | 137.7 | 9 of 16 | no |
| Noise-area intraday momentum with VWAP trail | + H1 trend | −$15 | −$41 | −$16 | −$389 | 24% | 189.1 | 12 of 16 | no |
| Last half-hour intraday momentum | standalone | +$4 | −$27 | −$20 | −$256 | 11% | 64.8 | 9 of 16 | no |
| Last half-hour intraday momentum | + bot votes | −$0 | −$4 | −$3 | −$44 | 3% | 13.5 | 11 of 16 | no |
| Last half-hour intraday momentum | + H1 trend | +$1 | −$17 | −$15 | −$180 | 8% | 51.0 | 9 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | standalone | +$3 | −$1 | +$40 | +$226 | 8% | 2.0 | 3 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + bot votes | +$2 | +$16 | +$25 | +$239 | 4% | 1.2 | 2 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + H1 trend | $0 | −$1 | $0 | −$7 | 1% | 0.1 | 1 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | V3-lite + regime | +$27 | −$2 | +$6 | +$119 | 15% | 16.1 | 7 of 16 | no |
| Bitcoin 10-day MAX / MIN composite | standalone | +$15 | +$57 | −$3 | +$385 | 14% | 17.1 | 7 of 16 | no |
| Bitcoin 10-day MAX / MIN composite | + bot votes | −$6 | +$22 | +$32 | +$287 | 8% | 8.5 | 7 of 16 | no |
| Bitcoin 10-day MAX / MIN composite | + H1 trend | +$17 | +$23 | +$1 | +$206 | 11% | 9.1 | 6 of 16 | no |

### BTCUSDm: alternative parameter sets

| Strategy | Variant | 2023 / q | 2024-25 / q | 2025-26 / q | Total, 3 periods | Max DD | Trades / q | Losing quarters | Wiped |
|---|---|---|---|---|---|---|---|---|---|
| Time-series momentum | standalone | $0 | +$108 | +$4 | +$671 | 21% | 0.2 | 4 of 16 | no |
| Time-series momentum | risk-sized: 40% vol target per instrument, 2x cap, monthly | $0 | +$409 | −$5 | +$2,421 | 39% | 0.2 | 5 of 16 | no |
| Time-series momentum | + bot votes | $0 | +$108 | +$4 | +$671 | 21% | 0.2 | 4 of 16 | no |
| Time-series momentum | + H1 trend | $0 | +$108 | −$7 | +$613 | 22% | 0.2 | 4 of 16 | no |
| Time-series momentum | V3-lite + regime | $0 | +$48 | +$19 | +$390 | 7% | 12.8 | 5 of 16 | no |
| Turtle Donchian breakout | standalone | +$48 | +$31 | +$43 | +$599 | 44% | 3.0 | 8 of 16 | no |
| Turtle Donchian breakout | risk-sized: 1% of equity per N, 20% cut per 10% drawdown | +$3 | +$203 | +$39 | +$1,442 | 24% | 1.5 | 5 of 16 | no |
| Turtle Donchian breakout | + bot votes | +$62 | +$106 | +$83 | +$1,319 | 33% | 2.4 | 8 of 16 | no |
| Turtle Donchian breakout | + H1 trend | +$52 | +$31 | +$43 | +$613 | 44% | 3.0 | 8 of 16 | no |
| Donchian ensemble, vol-targeted | standalone | +$15 | +$17 | +$12 | +$223 | 13% | 4.8 | 7 of 16 | no |
| Donchian ensemble, vol-targeted | risk-sized: 25% vol target, 2x cap, 20% rebalance threshold | +$43 | +$40 | +$45 | +$640 | 19% | 5.2 | 7 of 16 | no |
| Donchian ensemble, vol-targeted | + bot votes | +$4 | +$3 | +$6 | +$67 | 14% | 3.9 | 10 of 16 | no |
| Donchian ensemble, vol-targeted | + H1 trend | +$15 | +$19 | +$15 | +$251 | 13% | 4.8 | 7 of 16 | no |
| Donchian ensemble, vol-targeted | V3-lite + regime | −$2 | +$17 | −$11 | +$32 | 11% | 18.2 | 8 of 16 | no |
| Long-horizon moving-average rule | standalone | −$14 | −$35 | +$14 | −$187 | 25% | 128.0 | 11 of 16 | no |
| Long-horizon moving-average rule | + bot votes | +$6 | −$50 | +$32 | −$102 | 21% | 94.9 | 9 of 16 | no |
| Long-horizon moving-average rule | + H1 trend | −$6 | −$43 | +$1 | −$273 | 27% | 90.7 | 9 of 16 | no |
| Long-horizon moving-average rule | V3-lite + regime | +$6 | −$25 | −$3 | −$143 | 20% | 25.7 | 9 of 16 | no |
| Supertrend | standalone | +$25 | +$60 | −$27 | +$303 | 18% | 6.6 | 8 of 16 | no |
| Supertrend | + bot votes | +$24 | +$65 | −$20 | +$368 | 21% | 6.4 | 7 of 16 | no |
| Supertrend | + H1 trend | +$25 | +$62 | −$24 | +$332 | 18% | 6.5 | 8 of 16 | no |
| Supertrend | V3-lite + regime | +$19 | +$10 | −$45 | −$120 | 16% | 12.5 | 10 of 16 | no |
| Last half-hour intraday momentum | standalone | −$7 | −$20 | −$12 | −$211 | 7% | 64.8 | 12 of 16 | no |
| Last half-hour intraday momentum | + bot votes | −$4 | −$7 | −$2 | −$68 | 3% | 20.8 | 12 of 16 | no |
| Last half-hour intraday momentum | + H1 trend | −$5 | −$14 | −$10 | −$157 | 6% | 49.9 | 12 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | standalone | +$8 | +$12 | +$23 | +$228 | 7% | 3.5 | 4 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + bot votes | +$13 | +$33 | +$23 | +$372 | 6% | 2.5 | 2 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | + H1 trend | $0 | +$4 | +$4 | +$47 | 3% | 0.3 | 1 of 16 | no |
| Connors RSI(2) pullback with the 200-day trend | V3-lite + regime | +$27 | −$2 | +$6 | +$119 | 15% | 16.1 | 7 of 16 | no |
| Bitcoin 10-day MAX / MIN composite | standalone | −$1 | −$13 | −$20 | −$187 | 10% | 90.5 | 8 of 16 | no |
| Bitcoin 10-day MAX / MIN composite | + bot votes | −$6 | −$6 | −$6 | −$93 | 8% | 30.8 | 11 of 16 | no |
| Bitcoin 10-day MAX / MIN composite | + H1 trend | +$3 | +$2 | −$12 | −$40 | 5% | 47.2 | 9 of 16 | no |

### Top 5 on XAUUSDm (max drawdown under 50% in every period, never wiped)

| # | Strategy | Parameters | Variant | Total, 3 periods | 2023 / q | 2024-25 / q | 2025-26 / q | Max DD | Trades / q | Losing quarters | Fresh $2,000 each quarter: 2023 / 2024-25 / 2025-26 per q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Supertrend | H4, always in | + H1 trend | +$8,040 | +$47 | +$74 | +$1,356 | 25% | 9.4 | 4 of 16 | +$39 / +$86 / +$762 (4 of 15 lost, worst DD 31%) |
| 2 | Supertrend | H4, always in | standalone | +$7,992 | +$42 | +$84 | +$1,340 | 24% | 9.5 | 4 of 16 | +$39 / +$90 / +$761 (4 of 15 lost, worst DD 32%) |
| 3 | Long-horizon moving-average rule | gold M5 SMA 41 / 356, always in | + bot votes | +$5,717 | +$32 | +$63 | +$953 | 29% | 59.6 | 3 of 16 | +$27 / +$87 / +$732 (4 of 15 lost, worst DD 31%) |
| 4 | Supertrend | H4, long only | standalone | +$3,982 | +$40 | +$187 | +$496 | 24% | 4.7 | 3 of 16 | +$36 / +$149 / +$401 (2 of 15 lost, worst DD 25%) |
| 5 | Long-horizon moving-average rule | gold M5 SMA 34 / 339 | + bot votes | +$3,956 | +$48 | +$112 | +$568 | 31% | 65.4 | 4 of 16 | +$42 / +$100 / +$491 (3 of 15 lost, worst DD 33%) |

### Top 5 on BTCUSDm (max drawdown under 50% in every period, never wiped)

| # | Strategy | Parameters | Variant | Total, 3 periods | 2023 / q | 2024-25 / q | 2025-26 / q | Max DD | Trades / q | Losing quarters | Fresh $2,000 each quarter: 2023 / 2024-25 / 2025-26 per q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Turtle Donchian breakout | System 1: 20-day entry with the skip-after-winner filter and 55-day failsafe, 10-day exit | risk-sized (1% of equity per N, 20% cut per 10% drawdown) | +$2,425 | +$140 | +$282 | +$40 | 21% | 2.0 | 5 of 16 | +$95 / +$87 / +$44 (2 of 15 lost, worst DD 17%) |
| 2 | Time-series momentum | 12-month sign only (MOP-12) | risk-sized (40% vol target per instrument, 2x cap, monthly) | +$2,421 | $0 | +$409 | −$5 | 39% | 0.2 | 5 of 16 | $0 / +$360 / −$40 (6 of 15 lost, worst DD 32%) |
| 3 | Turtle Donchian breakout | System 2: 55-day entry, 20-day exit | risk-sized (1% of equity per N, 20% cut per 10% drawdown) | +$1,442 | +$3 | +$203 | +$39 | 24% | 1.5 | 5 of 16 | +$69 / +$107 / +$42 (2 of 15 lost, worst DD 19%) |
| 4 | Turtle Donchian breakout | System 2: 55-day entry, 20-day exit | + bot votes | +$1,319 | +$62 | +$106 | +$83 | 33% | 2.4 | 8 of 16 | +$45 / +$198 / +$180 (6 of 15 lost, worst DD 22%) |
| 5 | Donchian ensemble, vol-targeted | 9 lookbacks 5-360 days, long only | risk-sized (25% vol target, 2x cap, 20% rebalance threshold) | +$1,190 | +$118 | +$134 | −$8 | 14% | 2.4 | 8 of 16 | +$85 / +$120 / −$48 (8 of 15 lost, worst DD 13%) |

### V3-lite three ways (fresh $2,000 per quarter, average per quarter)

| Symbol | Period | Tick engine, published (8 timings) | Tick engine, live votes, 1 timing | Tick engine, closed-bar votes | Bar level (this study) | Trades / q (engine closed-bar, bar level) |
|---|---|---|---|---|---|---|
| XAUUSDm | 2023 | +$106 | +$103 (0 of 4 lost) | +$35 (1 of 4 lost) | +$22 (2 of 4 lost) | 17, 18 |
| XAUUSDm | 2024-25 | +$152 | +$142 (1 of 6 lost) | +$93 (0 of 6 lost) | +$89 (1 of 6 lost) | 17, 17 |
| XAUUSDm | 2025-26 | +$404 | +$385 (1 of 5 lost) | +$77 (1 of 5 lost) | +$94 (1 of 5 lost) | 17, 17 |
| BTCUSDm | 2023 | +$7 | +$9 (2 of 4 lost) | −$4 (2 of 4 lost) | −$2 (2 of 4 lost) | 24, 24 |
| BTCUSDm | 2024-25 | +$48 | +$45 (3 of 6 lost) | +$35 (3 of 6 lost) | +$38 (3 of 6 lost) | 29, 30 |
| BTCUSDm | 2025-26 | +$114 | +$101 (1 of 5 lost) | +$31 (2 of 5 lost) | +$9 (3 of 5 lost) | 24, 27 |

<!-- tables:end -->

## How far to trust this

- **The best of many rows is flattered.** About 80 rows per symbol were run, none of them tuned.
  Rows positive in all three periods on several related rules (Supertrend, two moving-average rules,
  the Donchian ensemble, the London breakout) are more convincing than the single top row.
- **One regime.** In this data gold went from about $1,775 (December 2022) to $5,590 (end of January
  2026) and back to $3,880. With-trend rules profit from that, and none of them made more than about $50 a
  quarter in 2023.
- **A few trades make the result.** Supertrend's 2025-26 total comes mostly from three trends. The
  risk-sized BTC Turtle and the 12-month TSMOM rest on one or two trades each.
- **A $2,000 account is too small for most published risk sizing.** At gold above $4,000, 0.01 lot is
  1 oz, about $4,000 of exposure:
  - the 1%-per-N Turtle can trade nothing on gold;
  - in 2025-26 the 1%-risk London breakout and the vol-targeted noise area skipped 266 of 311 and
    242 of 332 signals.
  These rows are what this account could have done, not what the sources measured.
- **Swap.** No swap is charged, as in the bot's backtester. If the account pays swap on multi-day
  holds, the D1 and H4 rules lose that cost.
- **Bar-level fills.**
  - A stop is filled at its level unless the bar opens beyond it, slightly optimistic against ticks.
  - A bar that reaches both levels is a stop, pessimistic.
  - On V3-lite the bar level and the tick engine agree when the votes are read the same way.
- **Session clocks are assumptions.** The London rules use New York + 7 h as "server time"; the same
  hours on the UTC clock lose. COMEX and US-session times follow New York daylight saving.
- **2023 is partial for long lookbacks** (see the test), and the gold rows of the Bitcoin MAX / MIN
  rule are outside its source's scope.

## Files and how to repeat

- `backtesting/research/external.py`: the simulator, the ten strategies, the combinations, the study
  and the tables.
- `tests/test_external.py`: simulator tests and the no-look-ahead tests.
- `backtest_results/improve/external_strategies.csv`: one row per symbol × strategy × parameters ×
  variant × period, with every figure. These include trades, win rate, average win and loss, profit
  factor, max DD, worst trade, wiped, zero-size trades, quarter blocks and the fresh-quarter figures.
- `external_strategies_blocks.csv`: the same runs cut into quarter blocks.
- `external_v3lite_engine.csv`: V3-lite three ways.

```
export ALCADEIAS_STORE_DIR=<the tick store>           # read from 2022-12-01 on
python -m backtesting.research.external run --cache <scratch dir>        # all strategies and variants (~1 min)
python -m backtesting.research.external engine-check --engine-store <a store holding only 2022-12 on> --cache <scratch dir>
python -m backtesting.research.external tables --update backtest_results/improve/external_strategies.md
python -m pytest tests/test_external.py -q
```

The engine check is given its own copy of the store because the engine reads the span of whatever
store it is pointed at.
