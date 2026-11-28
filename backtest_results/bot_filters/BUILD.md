# BUILD: the code of study 3 (entry filters on the bots' designs), and the proof that it runs the designs as published

Built 28 Nov 2026 on `backtest_hedging`, against the frozen `PREREG.md`. Its sha256 (2593648…afb54) was checked against
`PREREG.md.sha256` before any work: OK. No existing file was edited and nothing was committed.

What ran in this step: only the five **base** designs and the **always-allow** (identity) filter, on the Development
windows and the 5-year window (the task's exceptions). No filter variant was run on any data. Nothing was run in T1,
T2 or the forward window. No study-2 indicator was computed on a bar at or after 2024-07-01. The run files are in the
scratch folder, not here: this step writes only this file and the code.

## Result

| Check (task 6 / PREREG) | Result |
|---|---|
| (a) Tick designs, 5-year account: the always-allow filter, composed with the rebuilt H1 trend, reproduces each published account exactly, and its fills equal the no-regime run's fills | **Gold: 3 of 3.** Base and identity filter give V3-lite $10,747.58 / 30.58% / 517, Top 1 $12,433.38 / 31.51% / 783, Top 2 $8,879.85 / 15.30% / 814. Fills are equal row for row (1,034 / 2,415 / 1,629). **BTC Top 2: not run** (memory, section 6). |
| (a') The same in the full Development format (23 quarters + 5y, cut from the one prepare) | **Gold: 24 of 24 accounts equal on each of the 3 designs.** Turtle: 24 of 24. |
| (b) The Turtle's no-op gate reproduces its published 5-year account | **Exact:** $3,546.56, max DD 38.4036%, 41 trades, for the base and the no-op gate. The trades are equal leg for leg on all 24 Development windows. |
| (b') The Turtle exit overlay's machinery | With no flag: the base on 24 of 24 windows. With inert flags at every H4 close (16,163 new decision rows in the 5-year plan): the base on 24 of 24 windows. |
| (c) Causality | A filter value takes effect at the first row at or after its bar's close, never before. This is tested on random rows, on a real per-second week and on the engine. The regime is 0 before the first stamp. On real bars, the allow series up to T do not change when the bars after T are removed (both symbols, two cut times). |
| (d) The guard | Before the freeze, every scored window outside [2021-01-01, 2026-11-13] is refused, base designs included, before any data is read. `freeze` opens it; an edited FINALISTS.md shuts it again. |
| Cutting quarters from one per-second prepare | **Exact.** 3 of 3 V3-lite quarters (H1 2021, C3 2024, IS 2026) equal the same quarter prepared on its own: final equity, max DD to 1e-6 points, trades. |
| Tests | `tests/test_bot_filters.py`: 68 pass and 2 skip (the ribbon and Heikin Ashi ports are not in the repository yet). There are 3 slow tests (`-m slow`): the gold and Turtle identity tests pass (4 min); the BTC one was not run. |

## 1. What was built

`backtesting/research/bot_filters.py` is all new. It imports `external`, `final10`, `tradeiq_ind`, `tradeiq_market`,
`engine.fast` and, lazily, study 2's ports. It edits none of them.

| Part | Functions | What it does |
|---|---|---|
| Designs | `DESIGNS`, `design_cfg`, `published_5y` | The five designs as FINAL10 runs them. Tick designs: `live_config(...).replace(**own_designs(sym)[name])`, prepared with M1/M5/M15/H1/H4, equity sampled hourly (`record_interval_s=3600`). The Turtle: `filtered(turtle(m, 2).plan, m, bot_signals(m).votes_at)` on the M1 market from 2018-01-01. |
| Windows | `DEV_QUARTERS`, `FIVE_Y`, `T1_QUARTERS`, `T1_CONT`, `T2_QUARTERS`, `T2_CONT`, `forward_window`, `COMPARE_SEC`, `COMPARE_1Y` | PREREG 4 exactly. The 23 quarters are round 4's segments; a test reads them back from `improve/round4/top3_v4_{dev,holdout}_*.csv`. |
| Guard | `guard`, `guard_data_end`, `finalists_frozen`, `SealedWindowError` | Any scored window not inside Development raises until `FINALISTS.md` and `FINALISTS.md.sha256` exist and match (study 1's `_guard` pattern, in this study's folder). Data past 2026-11-13 is not even loaded before the freeze. |
| Filters | `single_filters` (59), `FilterBook`, `BarSides`, `Steps`, `bar_steps`, `clock_steps`, `and_steps` | PREREG 3's table on closed H1/H4 bid bars (UTC boundaries) and merged D1 days (`TMarket.tbars`, study 1's bars). The indicators run over the full history from the store's first bar (`tradeiq_ind`: `sma`, `bjorgum_tsi`, `laguerre_rsi`, `qqe_mod`, `vwrsi` with tick volume for gold and Binance volume for BTC). Each value is stamped at the first row at or after its bar's close. RIB / MSD / HA read study 2's ports by lazy import. |
| Regime | `trend_series`, `compose`, `regime_at` | regime(T) = trend_H1(T) where the filter allows that side, else 0, on the union of change times. trend_H1 is rebuilt from the prepare's own signal line and bar start rows (the map's snippet), times the trend mode. |
| Turtle | `turtle_base`, `turtle_gate`, `turtle_filtered`, `TurtleRunner`, `exit_flags`, `ha_flips`, `rare_age`, `turtle_exit_plan`, `inert_flags` | One-sided gates by `plan.copy(alw_l, alw_s, m_l, m_s)`. The HA-M1 / HA-M4 exit overlays on H4 and D1 are built from `PathPlan` rows (section 3). |
| Runner | `run_dev`, `run_sec_stage`, `run_tick_stage`, `run_bar_stage`, `run_confirm`, `run_exam`, `run_compare` | One per-second prepare per symbol (2021-01-01 to 2026-11-13, its own warm-up) and a fork pool (`sizing._pool`'s pattern; the workers share the rows copy-on-write). Per variant: the 23 fresh $2,000 quarters (`light=True`) and the 5-year account (hourly equity, daily marks saved). The confirmation and the exam run raw ticks under `live_timing(1..8)`, one prepare per quarter. Resume-safe: a variant with every window in the CSV is skipped. `run_dev` runs the base and the identity filter first, and stops (`IdentityError`) unless their 24 accounts are equal. |
| Score | `quarter_table`, `yardstick`, `better`, `meets_floor`, `mark_better`, `candidates`, `stage2_pairs`, `finalists`, `score_dev`, `score_confirm`, `choose` | PREREG 5: FINAL10's yardstick (the arithmetic of `final10.evidence`), "better" with the 90% profit floor, three candidates, at most three pairs, the median of eight timings per quarter, two finalists. |
| Freeze, exam | `freeze`, `freeze_choice`, `blob_id`, `window_score`, `exam_pass`, `exam_verdict` | FINALISTS.md (the rules in words, the Development and confirmed scores, the git blob ids of the code) and its sha256. PREREG 6's pass rule per window. |
| Multiple testing | `multiple_testing`, `run_multiple_testing`, `daily_matrix` | Hansen's SPA on the 5-year daily P&L differences against the base (`tradeiq.bootstrap_pvalues`, which reproduces `silver.spa_test` and adds White's Reality Check). The deflated Sharpe (`silver.expected_max_sr`, `silver.dsr`) of the best variant's daily returns. |
| Identity | `identity_ticks`, `identity_turtle`, `check_identity`, `same_path` | The checks of this file. |

Command line, from the repo root (`python -B -m backtesting.research.bot_filters ...`):

| Command | What it runs |
|---|---|
| `identity --symbol S --work DIR` | The tick-design identity checks |
| `identity-turtle --work DIR` | The Turtle's identity checks |
| `dev --design K [--stage singles\|pairs] [--ports] [--workers N]` | The Development format for one design. Without `--ports`, the rows that read study 2's ports (RIB, MSD, HA, the Turtle's exits: 9 per design + 4) are left out; add them once those ports are reconciled (PREREG 3) |
| `score` | The Development yardstick and the candidates |
| `confirm --design K` | The confirmation on raw ticks |
| `select` | The candidates and finalists per design |
| `freeze` | FINALISTS.md and its sha256 |
| `mt` | The multiple-testing statistics |
| `exam --design K --vids ...` | The exam, after the freeze |

## 2. The regime composition, and why it is exact

- **The regime argument.** `fast.run(cfg, prep, regime=(t, v))` refuses a new basket whose side is not the `v` in
  force at the poll (`kernels.py` L1214-1216), right before the trend gate (L1217-1219). Before the first time the
  value is 0. It gates new baskets only: Top 1's add and every exit are untouched, and a refused poll costs no loop
  time.
- **The trend.** The trend gate allows only the side of the sign of the MACD signal line of the last closed H1 bar
  (L1015-1022). The kernel moves its H1 forming-bar index when its tick pointer reaches the first row of the next bar
  (L840-845). `trend_series` stamps bar k's sign at `prep.t_ms[start_row[k+1]]`. The regime lookup `reg_t <= T`
  (L1023-1026) and the pointer `t_ms[ptr] <= T` then switch on the same poll, for every poll, in both modes.
- **The filter's stamp.** A filter bar is stamped at `t_ms[searchsorted(t_ms, close_ms, 'left')]`: the first row at or
  after its close, the instant the kernel (and MT5) sees the bar closed. Bars that close before the first row land on
  it, and the last of them holds. Bars that close after the last row never take effect.
- **Hence the identity.** `compose(trend, ALLOW)` is the trend gate itself: the same fills, and exactly the polls the
  trend gate blocked move to the regime counter. On the 5-year account these are 11,869,073 (V3-lite), 15,597,024
  (Top 1) and 17,625,802 (Top 2). After dropping repeats, the identity regime has 831 entries.
- **On the fixture store:** the same holds for the trend timeframes M1, M5 and H1 and for the contrarian trend mode.
  One-sided steps equal the engine's own `allow_long` / `allow_short` switches. With random allow-steps, every basket
  opened in a direction that both the trend and the steps allowed.

## 3. The Turtle's exit overlays (HA-M1, HA-M4 on H4 and D1): built without editing `external.py`

- **D1 flags** fall on the plan's own decision rows (the D1 closes) and are OR-ed into their `xl` / `xs`. The kernel
  exits at the next M1 open, and that same row then arms the next day's stop orders, so a re-entry needs a new 55-day
  extreme.
- **H4 flags** (other than at 00:00 UTC) become new decision rows that copy every field of the day's decision.
  - Re-arming at a new row would change the Turtle in two cases, so those rows carry NaN order levels:
    - after a fill earlier in the same day (the kernel's "one fill cancels both until the next decision",
      `external.py` L757-758);
    - after an exit by that row or by an earlier new row of the day.
  - Rows also carry NaN levels when the day's decision lies before the window (the kernel skips such rows, L564).
  - Which rows these are depends on the path, so the plan is rebuilt until it is a fixed point. Each pass fixes the
    earliest event, and the path before it no longer changes.
- **Proof:**
  - with no flags, the overlay is the base on 24/24 windows;
  - with inert flags at every H4 close, it is the base trade for trade on 24/24 windows (the 5-year plan holds 16,163
    new rows). Inert flags never meet a position against them, so every new row only re-arms or cancels;
  - two hand-made cases show the cancelling is needed: without it, the Turtle re-enters the same day.
- **The Heikin Ashi colour** comes from study 2's port (`tradeiq2_ind_ha.heikin_ashi(o, h, l, c)['dir']`), which is not
  in the repository yet. The four exit variants cannot run until it is. HA-M4's rare age is the port's own causal
  series if it has one (`rare_now` / `rare`), else `rare_age` here.

## 4. Readings where the plan is silent (to be logged in DEVIATIONS.md before any variant result exists)

1. **Profit floor when the base's mean is 0 or below** (PREREG 5 (3)): the floor is the base's own value, the exam's
   rule (PREREG 6). Every comparison with the floor allows 1e-9 of the base for rounding: 0.9 × 100 is
   90.00000000000001 in floating point.
2. **Warm-up of a filter:** a comparison with na is false (Pine).
   - SIDE, SLOPE, TREND, CROSS, TSI, LARSI, VWRSI, RIB, MSD and HA allow neither side until their lines exist.
   - LGATE200 / SGATE200 keep their "always" side.
   - QQE is GRAY (both sides allowed) before its Bollinger band exists.
   - All are warm long before 2021, and before T1 / T2.
3. **History of the filters:** from the store's first M1 bar: gold 2016-01-03, BTC 2018-01-01. Gold's 2016 months
   appeared in the store during this step: PREREG 4 and study 2 asked for that download. Each results row records the
   history start (`history_from`). T2 therefore has its warm-up and can start on 2017-01-03 as planned.
4. **Sessions:** the poll's New York hour. The steps sit exactly on UTC hour boundaries, because New York's offset is a
   whole number of hours. A session is [start, end). On the M1-bar model, the open of the fill's M1 bar is used.
5. **MSD:** the port's `rows_for(mk)` (its end-aware weekly row: a week that can still grow closes at its ISO end) and
   `structure_dashboard(rows, chart_tf)['label']` (int8, -2 to +2). LEAN BULL / BULLISH = label > 0; LEAN BEAR /
   BEARISH = label < 0.
6. **HA-M1** exits at a colour FLIP against the position (bullish to bearish for a long), not on every bar of the
   opposite colour.
7. **HA-M4** exits a long when a bullish streak's `rareNow` fires: the script's l.209-212, pctBelow(age) reaches 90
   while pctBelow(age - 1) was below it. It is computed from the streaks finished before the bar, and needs at least 50
   finished streaks of that colour (study 2's PREREG 6.8).
8. **After an H4 Heikin Ashi exit,** the Turtle's orders stay cancelled until its next D1 decision ("the base stays flat
   until its own state changes"). After a D1 exit, the decision row arms the next day's orders at once.
9. **Stage 2:** "filters that beat the base's score" means a Development score strictly above the base's, not
   "better". Ties in any ranking go to the higher mean profit per quarter, then to the id.
10. **SPA:** a mean block of eight weeks in days (study 1's eight weeks), 5,000 resamples, seed 20261128, over the
    design's singles, pairs and exits (not the base, not the identity filter).
11. **Deflated Sharpe:** reported for the variant with the best 5-year daily Sharpe (the textbook case) and for the
    variant with the best Development score.
12. **Exam window score:** the mean net per quarter over the window's quarters / max(worst quarter DD, 1).
13. **The Turtle's identity** is checked on 5 years, not on PREREG 2's 8 years ($7,814.72): the 8-year window reads T1,
    which is sealed until the freeze.

## 5. Run time and memory (this Mac, shared with other agents)

| Item | Gold | BTC |
|---|---|---|
| Per-second prepare 2021-01-01 .. 2026-11-13 | 95,606,523 rows in 5.7 s. Process RSS 2.7 GB while running; max RSS 4.07 GB, peak footprint 4.76 GB (with the indicator arrays and two runs' buffers) | not run (memory) |
| 5-year account, one run | V3-lite 27.7 s, Top 1 42.7 s, Top 2 31.6 s. With the identity filter: 27.8, 43.3 and 29.9 s | FINAL10's probe: 42.6 s |
| One variant in the Development format (23 quarters + 5y), 2 workers | **V3-lite 69 s, Top 1 98 s, Top 2 66 s** (base and identity filter equal to the second) | estimate from the probe: about 100 s |
| All 51 available bar filters (data to 2024-07-01) | 0.9 s | 0.8 s |
| Stamping 53 filters on 50 M rows; composing 53 regimes | 1.1 s; 0.17 s | 1.6 s; 0.19 s |
| Turtle: market and bot votes; one variant (24 accounts) | | 54 s once (1 s once cached); 0.1-0.4 s per variant. The exit overlay with 16k rows: 1.4 s for 72 window plans |

- A variant costs its kernel runs: the filter, its stamping and the composition together take well under a second.
- **Expected stage times with 4 workers on gold** (59 singles each):
  - V3-lite about 17 min, Top 1 about 24 min, Top 2 about 16 min;
  - add 1-2 minutes per design for the prepare, the warm-up and up to 3 pairs.
- **BTC Top 2 with 3 workers:** about 33 min (estimate).
- **The Turtle:** under a minute for all 63 variants, after the bot's votes.
- **Confirmation:** FINAL10's map estimates 4-5 min per design (23 raw-tick prepares, 8 timings × (base + 3
  candidates)).
- **Memory:** the parent holds the prepare; each worker adds about 0.3-0.5 GB of its own. Run gold with 4 workers and
  BTC alone.

## 6. Not done in this step, and why

- **BTC Top 2 tick identity:** the per-second BTC prepare of 2021-2026 needs about 6-8 GB.
  - vm_stat showed 7.52 GB free + inactive after the gold run, and 8.06 GB at a second check. Both are below the 9 GB
    the task requires, so the check was skipped.
  - Run it alone: `python -B -m backtesting.research.bot_filters identity --symbol BTCUSDm --work DIR`, or the slow test
    `test_the_identity_filter_reproduces_the_published_five_year_accounts[BTCUSDm]`.
  - `run_dev` itself refuses to run any BTC variant unless the identity filter equals the base on all 24 accounts.
- **RIB, HA and the four Turtle exit variants** wait for `tradeiq2_ind_ribbon` / `tradeiq2_ind_ha` and their
  reconciliation (PREREG 3). MSD's port is in the working tree and feeds its filter. It has been tested on hand-made
  bars only.
- **Sequencing note, for the orchestrator.** Study 3's Development window runs to 2026-11-13. Its RIB / MSD / HA rows
  therefore compute and score study 2's indicators on study 2's hold-out (from 2024-07-01). To keep study 2's hold-out
  clean, run those 9 rows per design only after study 2's FINALISTS.md is frozen, or log the overlap as a deviation.
- Nothing was run in T1, T2 or the forward window. No FINALISTS.md exists.
