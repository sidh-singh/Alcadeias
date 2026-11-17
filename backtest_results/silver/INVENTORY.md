# Silver (XAGUSDm): what the repo can already run

Step `inventory` of the silver research, 2026-11-17. Nothing is committed. No strategy's performance on silver was read
in this step; see §5 for the one exception and for what the timing runs touched.

Files of this step: `smoke/smoke.py` + `smoke/smoke.log` (one month per engine, plumbing checks), `smoke/timing.py` +
`smoke/timing.log` (wall-clock run time on the 8 years, trade counts only).

## 1. Silver facts that every strategy must respect

| Item | Value | Source |
|---|---|---|
| Contract | 5,000 oz per lot; 0.01 lot = 50 oz, so **$50 per $1.00 move**, $0.05 per point | `multisymbol.register`, `specs.json` |
| Digits / point / min lot | 3 / 0.001 / 0.01 (step 0.01) | same |
| Quote currency | USD, P/L × 1. The bot's `trade_contract_size × mtqty` arithmetic is right | PREREG §3.1, §12 |
| Hours (UTC) | Sunday 22:05 (summer) / 23:05 (winter) to Friday 20:58 / 21:58 | PREREG §3.2 |
| Daily break | Mon–Thu 20:58–22:01 (summer) / 21:58–23:01 (winter) | PREREG §3.2 |
| Data | `data/store/XAGUSDm/`, 109 of 109 months (2017-11 → 2026-11). `sec.npz` + `m1.npz` in every month, **no raw ticks** | store, `data_quality.csv` |
| Data gate | passed for both spans under DEVIATIONS E (the literal silence test fails every symbol, gold included) | `quality/XAGUSDm.json` |
| Quote density | 340k–600k quoted seconds a month in 2018–2024, 770k in 2025, 1.19M in 2026. Gold has about 1.2M every year | `meta.json` |

**The cost hurdle is the biggest difference from gold.** The archive's Standard-account spread:

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| Silver median spread (price) | 0.044 | 0.033 | 0.054 | 0.054 | 0.038 | 0.038 | 0.047 | 0.036 | 0.030 |
| Silver spread, % of price | 0.28 | 0.20 | 0.26 | 0.21 | 0.17 | 0.16 | 0.17 | 0.09 | 0.04 |
| Gold spread, % of price | 0.018 | 0.019 | 0.017 | 0.017 | 0.011 | 0.010 | 0.008 | 0.005 | 0.006 |

- In development (2018-11 → 2022-12), silver's median absolute H1 return was 0.155% and its median absolute D1 return was 0.90%. Both are about twice gold's (0.080% and 0.48%).
- Silver's median M1 spread was 0.213% of price, against gold's 0.016%. **Silver's spread is 1.37 times its median H1 move; gold's is 0.20 times.**
- A round trip costs $1.50–$2.70 per 0.01 lot.
- The spread in price stayed near 0.03–0.05 while the price rose from $16 to $70. So in % of price, the cost falls about 5× from development to hold-out.
- Any result on fast, intraday or small-target rules will therefore look much better in the hold-out than in development. This is a regime change in the cost, not an edge, and it must be named whenever results are compared across splits.

**How the engines handle the break and hours.** All three engines take closures from the data, so no schedule file is needed.
- **Tick engine.** A silence of 30 minutes or more is a session break, and the last quote before it is not fresh, so the server counts as shut. After a break there is a close-only period: 90 s after a daily break and 210 s after a weekend. Both lengths were calibrated on gold; for silver they are an assumption. The smoke month logged 25 `dead_market_skips` and no fill inside the break.
- **M1-bar simulator.** Orders fill at the next M1 bar that exists. Intraday rules need a quote within 3 minutes of the decision.
- **D1 bars.** A UTC day with fewer than 360 M1 bars is merged into the next one, so the Sunday-evening stub joins Monday (checked: no D1 bar ends on a weekend).
- **Trading window.** Every silver run so far used gold's window, Monday 01:00 – Friday 22:00 UTC: `multisymbol.GOLD_WINDOW` for the engine, and the `symbols.json` fallback for `external.in_trading_window`. Silver is already closed for the window's last hour on summer Fridays.

## 2. The engines, with this step's smoke tests (development month, March 2021)

| Engine | Code | Data | Smoke test | 8-year run time (2018-11-13 → 2026-11-13) |
|---|---|---|---|---|
| **Tick engine**, per-second replay | `engine/fast.py` (`prepare`, `run`), kernel `engine/kernels.py`; silver configs via `multisymbol.basket_cfg` | `sec.npz` only. `mode="ticks"` is impossible on silver (no ticks), so the final ten's raw-tick, eight-loop-timing check of the last year cannot be repeated | PASS: V3-lite 9 baskets, Top 2 12 baskets. P/L = move × lots × 5,000 to the cent; Top 2 cap translated to $14.72; no fill in the break; quotes at most 5 s old | prepare 3.6 s (54.8M rows, peak memory 2.9 GB); then **43 s** a run for V3-lite and Top 2, 62 s for Top 1 + add, 50 s for the Live logic. A sweep of N configs costs about N × 45 s on one core |
| **M1-bar simulator** | `research/external.py` (`load_market`, `bot_signals`, `run_path`, `account` / `_account_kernel`, `run_target`), windows via `final10._bar_account` | `m1.npz` (3.14M bars, 2017-11 → 2026-11) | PASS: k = $50, tick 0.001. Turtle S1 + votes 1 trade, Supertrend H4 3 trades. P/L = move × units × $50 exactly; no entry in the break | load 0.1 s; **the bot's votes 32 s, once per process**; then every strategy builds and runs in 0.0–0.3 s |
| **Balke multi-position account** | `research/balke.py` (`every_signal`, `_multi_kernel`, `multi_account`) on the same M1 market | as above | PASS: ATR Breakout 5 trades, risk-sized and on the unit rule, P/L exact | 0.1 s a run after the votes |
| FX-aware Turtle account (same family) | `multisymbol.turtle_account` / `_turtle_kernel` | M1 | not re-run: gated by G-checks in the multi-symbol study (FX = 1 reproduces `external.account` to the cent) | under 1 s |
| Unit-rule replays | `multisymbol._replay_kernel` / `replay` (per-unit stream → unit-rule and L-scaled accounts); `sizing._bar_replay` | engine or bar trades | not re-run (G2 / G3 of the multi-symbol study) | seconds |

The smoke test is `PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=… python3 backtest_results/silver/smoke/smoke.py` (6 s once compiled); it prints `ALL PASS`.

## 3. The strategies

Columns:
- **Needs on silver**: what must be set or translated before a run means anything.
- **8 y**: wall time on one core, from `timing.log`.
- **Bot today**: whether the live bot can trade it.
  - "yes": the code is on a branch; silver still needs its own branch, `symbols.json` window and MT5 terminal.
  - "config": the bot's existing code, other constants.
  - "new code": anything else.

### 3.1 The bot's basket designs (tick engine)

Settings are in `backtest_results/improve/round4/top3_v4_{XAUUSDm,BTCUSDm}_designs.json` (read with `final10.own_designs`); the silver configs come from `multisymbol.BASKETS` / `basket_cfg`.

| # | Strategy | Where | Needs on silver | 8 y | Bot today |
|---|---|---|---|---|---|
| 1 | **Live logic**: Fibonacci DCA ladder, no stop, M15 force-close, **$1 per unit target** | `BacktestConfig.live` (+ `constants.py`) | The $1 target is USD and must be translated. On gold it is a $1.00 move; on silver it is a $0.02 move, **under the spread** ($0.03–0.05). The vol-ratio rule of the $12 caps (× 0.0245) gives a 0.0245 move, still under the spread. The "as is" run made 37,822 baskets in 8 years | 50 s | yes (`hedging_*`) |
| 2 | **Slot-5 variant**: flat ladder (`LADDER_FLAT`), force-close on H4 | flat `ladder_multipliers`, H4 force-close weights; the force-close score also gates entries | The same $1 target translation as #1 | ~50 s | yes (`hedging_*5`) |
| 3 | **Gold V3-lite**: H1 votes, both M15 votes agree, H1 trend, 8 / 8 H1-vol units, 12 h pause after a loss | `own_designs("XAUUSDm")["V3-lite"]`; `MS.BASKETS["v3lite"]` | nothing in USD (vol units and time) | 43 s | yes (`demo_hedging_xauusd6`) |
| 4 | **Gold Top 2**: H1 votes and trend, target 8 / stop 4 units, $12 cap, 12 h pause | `["Top 2"]`; `MS.BASKETS["gtop2"]` | cap $12 → 0.2943 price = **$14.72 per 0.01 lot** (`specs.json` caps) | 43 s | yes (`demo_hedging_xauusd7`) |
| 5 | **Gold Top 1**: target 10 / stop 8 units, 1 add on the MACD turn, 4 h pause, no cap | `["Top 1"]`; `MS.BASKETS["gtop1add"]` | nothing in USD | 62 s | yes (`demo_hedging_xauusd8`) |
| 6 | **Gold Top 3**: Top 1 with the $12 cap and a 1 h pause | `["Top 3"]` | cap → 0.2943 price, as #4 | ~60 s | config (Top 1's add + Top 2's cap); no demo branch |
| 7 | **BTC Top 2**: target 10 / stop 8 units, $1,200-price cap, 4 h pause | `own_designs("BTCUSDm")["Top 2"]`; `MS.BASKETS["btop2"]` | cap → 0.6196 price = **$30.98 per 0.01 lot**; window: gold's (BTC's 24/7 window means nothing here) | 43 s | yes (`demo_hedging_btcusd8`) |
| 8 | BTC Top 1 / BTC Top 3 (H1 + M15 votes, 8 / 8, no cap, 4 h pause) | BTC designs JSON | Top 1: check for any cap; Top 3: nothing in USD | ~45 s | config |
| 9 | Owner's rules + H1 trend + 4 h pause (RSI-extreme entry block, RSI force-close) | designs JSON; `entry_rsi_block_tfs`, `fc_rsi_tfs` | nothing in USD | ~50 s | new code: backtester settings (LOGIC_CHANGELOG 2026-11-15); not found in the demo branch constants |
| 10 | V3-lite + regime filters on the engine (the final ten's "supplement") | `fast.run(..., regime=(t, v))`, `final10.run_supplement` | the regime series from §3.2 | 43 s | new code (the regime filter) |
| 11 | The improvement grids: 135 + 56 Live-family designs (trend filter, flat adds, USD targets and stops, cooldowns, spread cap) | `improve.grid_stage1` / `grid_stage1b` | **hard-coded gold / BTC**: `px = 1.0 if XAU else 100.0` and spread cap `0.5 if XAU else 30.0`, so silver would be treated as BTC. Every `target/stop_usd_per_unit` and `ladder_min_gap` needs a silver translation | ~45 s × 191 | config for most rows |

Engine settings in price or USD units, to translate whenever a design uses them:
- `target_usd_per_unit`, `stop_loss_usd_per_unit`, `trail_*_usd_per_unit`, `daily_loss_limit_usd_per_unit`, `vol_cap_usd_per_unit`
- `ladder_min_gap`, `entry_max_spread`, `extra_spread`, `slippage`

The `*_vol` settings and the pauses need no translation.

### 3.2 Published strategies on the M1-bar simulator (`external.py`)

Variants come from `external.evaluate`:
- **standalone**: the bot's unit rule.
- **risk-sized**: the source's own sizing.
- **+ bot votes** / **+ H1 trend**: entries filtered.
- **V3-lite + regime**: the strategy's state used as V3-lite's filter.

`final10._bar_plan` builds any of them by family, params and variant. Every row runs in under 0.3 s once the market and votes are built (32 s). The "zero size" counts below are trades whose risk budget could not buy 0.01 lot at $2,000, from `timing.log`.

| # | Strategy (key) | Function | Needs on silver | Bot today |
|---|---|---|---|---|
| 12 | Time-series momentum 1/3/12 m and 12 m (`tsmom`) | `tsmom(m, alt)` | Nothing in USD. The risk row targets 40% vol notional, and 0.01 lot = 50 oz = $800–3,500 of notional, so sizing is coarse at $2,000 | new code |
| 13 | **Turtle System 1** (20-day, skip-after-winner, 55-day failsafe, 10-day exit) (`turtle` default) | `turtle(m, 1)` | The entry tick is one point = 0.001 (`m.tick`). Risk row (1% per N, brake): **50 of 81 trades took zero size** on 8 y, because 2N on silver is $40–150 per 0.01 lot against a $20 budget | **yes with bot votes** (`demo_hedging_btcusd7`). On silver `turtle.py` needs `TURTLE_TICK` = 0.001 (BTC's 0.01 is wrong) and the Sunday-stub merge of D1 bars. Without votes: probably config, to check. Risk sizing: new code |
| 14 | **Turtle System 2** (55-day entry, 20-day exit) (`turtle` alt) | `turtle(m, 2)` | as #13; risk row 43 of 53 at zero size | **yes with bot votes** (`demo_hedging_btcusd6`), same two changes |
| 15 | Donchian ensemble, 9 lookbacks, long only / long-short (`donchian`) | `donchian_ensemble` | Nothing in USD; risk row is a 25% vol-target notional (coarse) | new code |
| 16 | Long moving average: M5 SMA 41 / 356, 34 / 339; D1 close over SMA 50 (`ma`) | `sma_cross`, `price_over_sma` | Nothing in USD. 1,300+ trades in 8 y, so it is spread-sensitive (§1) | new code |
| 17 | Supertrend H4, ATR 10 × 3, always in / long only (`supertrend`) | `supertrend` | nothing | new code |
| 18 | Asian-range / London breakout, server clock and UTC clock (`london`) | `london_breakout` | Range limits 0.3–1.6% of price and a 0.6% stop cap were set for gold's volatility; silver's is about 2×. Server clock = New York + 7 h, not Exness's UTC. Risk row: 1,127 of 1,541 at zero size | new code |
| 19 | Daily volatility breakout (BTC row of `london`) | `daily_vol_breakout` | 8% stop of price (BTC-calibrated) | new code |
| 20 | Noise-area intraday momentum with VWAP trail (`noise`) | `noise_area(m, "comex" / "broker")` | COMEX session 08:20–13:30 NY is gold's; silver's is 08:25–13:25. Exposure-sized rows: 1,217 of 1,803 (comex) and 5,655 of 6,135 (broker) at zero size | new code |
| 21 | Last half-hour momentum (`lasthalf`) | `last_half_hour` | Gold's COMEX times (13:00–13:30 NY). Intraday, so spread-sensitive | new code |
| 22 | Connors RSI(2) pullback with the 200-day trend (`rsi2`) | `connors_rsi2` | nothing | new code |
| 23 | MAX / MIN 10-day and 22:00–00:00 UTC hold (`maxmin`, BTC-only by source) | `max_min`, `seasonality_22utc` | 22:00 UTC is **inside silver's winter daily break**, so the 22:00 hold fills only in summer. Out of the source's scope | new code |
| 24 | V3-lite at bar level (the calibration row) | `v3lite(m, sig)` | gold's window (applied) | n/a (the engine row #3 is the real one) |

### 3.3 Balke's strategies (`balke.py`, M1 market; multi-position kernel where marked)

His settings files are on IC Trading's server clock, which the code takes as New York + 7 h. Exness runs on UTC.

| # | Strategy | Function | Needs on silver | Bot today |
|---|---|---|---|---|
| 25 | Range Breakout, gold settings (03:05–06:05 range, close 18:55, stop 1% of price, risk 1%) | `range_breakout(m, (3,5), (6,5), (18,55), "percent", 1.0, 1.0)` | The % stop was set for gold's volatility. Risk row: 1,388 of 1,840 at zero size. The times fall after silver's reopen at 01:01 server time | new code |
| 26 | Range Breakout, BTC and US30 settings | `range_breakout(...)` | as #25; BTC's runs every day (silver is closed at weekends) | new code |
| 27 | **ATR Breakout** (H1, ATR 200 × 2.5, close within 25%, TP 2%, SL 0.5%, risk 0.5%), **every signal its own trade** | `atr_breakout`, `multi_account` | % TP and SL as #25. H1 bars next to the daily break are short. Risk row: 719 of 1,174 at zero size. A one-position-at-a-time row also exists | new code (several positions at once) |
| 28 | Go Long (buy 01:05, close 22:55 server time, 100% notional) | `go_long` | An index rule, not meant for metals. Open 4 minutes after silver's reopen | new code |
| 29 | Turnaround Tuesday, SMA 25 / 9 | `turnaround_tuesday` | index rule | new code |
| 30 | Buy and hold (reference) | `buy_hold` | — (it is the benchmark silver's 2025-26 rally makes hard to beat) | — |

### 3.4 Other rule sets in the repo (studies more than strategies)

| # | What | Where | Needs on silver |
|---|---|---|---|
| 31 | 13 position-management mechanisms on identical entries: ATR stops and targets, break-even, trailing, scale-out, hedge lock, Live ladder with no stop / $60 / $200 basket stop, the V2 $20 / $20 exit | `recovery.mechanisms()` (own M1 model) | Contract via `SYMBOLS`, which works once `multisymbol` is imported. The three $-denominated mechanisms need translating. `--symbols` defaults and labels are gold / BTC |
| 32 | Support / resistance as a trading rule against placebo levels | `sr.py`, `sr_trades.py` (own M1 model) | **Hard-coded**: `sr.SYMBOLS` and `sr_trades.UNIT_USD` have no silver entry (round numbers, level shifts, $ per point). **`PERIODS` and `EARLIEST` are 2024–2026, the hold-out**, so it must not run on silver unchanged |
| 33 | Entry-signal screen (direction net of spread) | `edge_screen.main` | **Hard-coded `UNIT` and 2025-07 → 2026-11 quarters, all hold-out**. Do not run as is |
| 34 | Sizing rules | `external.Sizing` (bot unit rule; risk `rf`; exposure; target notional; brake); `sizing.py` (STEP / cap study: engine re-runs + `_bar_replay`, `BarDesigns` hard-coded to BTC); `multisymbol` accounts (per-unit stream, unit rule, L-scaled with `lot_rule`, L = 0.01 for silver) | `sizing.BarDesigns` and `DESIGNS` need a silver version. The unit rule itself is symbol-free |

## 4. What this means for the next steps

- **What the bot can trade on silver today** (with a branch, `symbols.json` and a terminal):
  - the basket designs #1–#8;
  - the Turtle with bot votes (#13–#14), after the two `turtle.py` changes;
  - everything on the bar simulator or in Balke's set is new bot code.
- **Translations needed before a run means anything:**
  - the $1 target of #1 and #2;
  - the caps of #4, #6 and #7, already done in `specs.json`;
  - the hard-coded gold / BTC constants of #11, #31, #32, #33 and `sizing.BarDesigns`.
- **Gold-calibrated settings in % of price or clock time** (#18–#21, #25–#27) are not USD, but they were chosen for gold's volatility and hours. Re-tuning them on silver is a fit and must happen in development only.
- **Risk-based sizing at $2,000 is mostly zero-size on silver.** 0.01 lot = 50 oz, so the 0.01-lot minimum is a large step. Half to three quarters of the risk-sized trades of #13, #14, #18, #25 and #27 could not be taken. Sizing studies must report skipped trades, or use a larger account or a minimum-lot rule stated in advance.
- **The cost regime changes across the splits** (§1). Each split's spread should be reported next to its results.
- **Cost of a full search:**
  - the bar strategies are almost free: 32 s of votes, then under 0.3 s a row;
  - the tick engine costs about 45 s for each design and window on 8 years;
  - a 191-design grid on one window is about 2.4 core-hours.

## 5. Contamination and honesty notes

- **Already seen before this step.** The six demo designs on silver for 2024-05 → 2026-11, and 2021-11 → 2024-05 (multi-symbol study). Silver's 2025-26 rally is public knowledge.
- **The timing runs** (`timing.py`) ran every strategy on the full 2018-11 → 2026-11 window, which includes validation and hold-out. Only wall time, trade counts and zero-size counts were printed: no P/L, equity or drawdown.
  - Future timing or plumbing runs should use the development span only.
- **One development result was seen by accident.** While checking why Go Long (#28) on the unit rule logged 736 trades instead of about 2,050, the check showed that **its unit-rule account was wiped in 2021** (the trade path itself has 2,050 entries, 256–258 a year).
  - This is development data, and Go Long is an index rule.
  - Nothing else about any strategy's results was read.
- **The smoke month** (March 2021) is in development.
