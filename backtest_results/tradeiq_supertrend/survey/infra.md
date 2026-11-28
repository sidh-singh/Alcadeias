# Study 4 (TradeIQ video 3, the Supertrend family) and filter round 2: the infrastructure map

Written 2026-11-28 by a read-only survey pass on `backtest_hedging` (HEAD bfe66ba). No backtest was run, no market data
was loaded (the store was listed through its `meta.json` files only), and no repository file was edited. Line
numbers (Lnnn) are those of the working tree now. The scripts in `/Users/sidharthsingh/Desktop/study/trend/` were only
scanned for which Pine features they use. No code from them is reproduced here.

## 0. The answer in brief

1. **Reuse study 2's execution engine as it is, and do not edit it.**
   - The engine is `tradeiq2_market.py` (fills, stops, targets, legs, lanes, break-even, tightening, stop orders,
     `close_gap`, marks, the $2,000 account) and `tradeiq2_filters.py` (F0..FS and the gating helpers).
   - Also reusable: study 1's `tradeiq_market.py`, `tradeiq_ind.py` and `tradeiq.py` helpers; the two-ports + oracle +
     reconciliation-test pattern; compare contract v2; and `study_graphs.py`.
   - Study 2's FINALISTS.md pins the blob ids of all these files, and study 3's pins `bot_filters.py`. Today
     `git hash-object` still matches for `tradeiq2_market.py` (985bdb9), `tradeiq2_filters.py` (6b148d5) and
     `bot_filters.py` (c764f39). Only the study 2 driver `tradeiq2.py` has moved (375e545 against 0d2ca95). That is
     allowed, because it is "recorded, not required" (`tradeiq2.INFO_FILES`, L594).
2. **Do not parametrise `tradeiq2.py`. Write a new driver, `tradeiq3.py`, on top of a thin harness shim,
   `tradeiq3_market.py`, and a filter module, `tradeiq3_filters.py`.** Four reasons:
   - study 2's guard is open now that study 2 is frozen;
   - its public scoring entry points hard-code study 2's five symbols and its "never before" dates;
   - the driver's study constants are module globals read by about a hundred functions;
   - `tradeiq2.port_files()` globs `tradeiq2_ind_*.py`, so a new port with that prefix would change study 2's recorded
     code identity, and its exam and accounts would then refuse to run.
3. **Filter round 2 should be a new module, `bot_filters2.py`, that imports `bot_filters` as a library.**
   - It reuses the designs, the windows, the regime composition, the per-variant task functions, the yardstick and
     the exam rule.
   - It needs its own filter registry, a `FilterBook` subclass, its own stage runners, its own guard and its own
     folder.
   - The reasons: `bot_filters.py` is pinned, its 59-id registry is closed (`filter_of`, `check_vids`, `pair_vid`,
     `FilterBook.sides`), and `run_sec_stage` builds its own `FilterBook`.
4. **The hold-out problem.** The video's author ranked these indicators, and chose their filters, on 11 markets on
   the 4H chart from January 2021 to October 2026, gold and BTC included.
   - So 2021-2026 is in-sample for the video whatever we do. Study 2's hold-out (2024-07 to 2026-11) lies inside that
     span, and 63% of all study 2 rows passed it on gold.
   - The most honest design is a **reverse split**:
     - select on 2021-01-01..2026-11-13;
     - examine on pre-2021 windows: E1 = 2018-11-13..2021-01-01 for both symbols, E2 = gold 2017-01-01..2018-11-13;
     - add, for information, the only spans no study has ever scored (gold 2016-04..2017-01, BTC 2018-04..2018-11-13)
       and the data after 2026-11-13;
     - as a secondary check, use markets the video never tested.
   - Pre-2021 is fresh for these rules and for the video's selection, but it is not unseen by us. Studies 1-3 and
     FINAL10 scored other rules there, and the classic Supertrend H4 (10, 3) has already been scored there as a FINAL10
     hybrid (section 7).

## 1. What was read

| File | Lines | Read for |
|---|---|---|
| `backtesting/research/tradeiq2_market.py` | 2101 | windows, guard, data, bars, types, engine, scores, accounts, `run_variant` |
| `backtesting/research/tradeiq2_filters.py` | 243 | PREREG 5 filters, how they apply |
| `backtesting/research/tradeiq2.py` | 4514 | grid / run / select / freeze / exam / accounts / claims / report, EXTRAS, CLAIMS, identity |
| `backtesting/research/tradeiq2_rules_ribbon.py` | 518 | the rule-module contract (`variants`, `build`, `describe`, `warm`) |
| `backtesting/research/tradeiq2_ind_ribbon.py` | 415 | port A's contract and docstring standard |
| `tests/tradeiq2_oracle_ribbon.py`, `tests/test_tradeiq2_ind_ribbon.py` | 585, ... | port B (a bar-by-bar transcription) and the reconciliation test |
| `backtest_results/tradeiq_2027/PREREG.md`, `porting/ribbon.md`, `EXAM.md`, `DATA.md`, `FINALISTS.md` | | the depth expected; the exam; the base rates; gold 2016; the pinned blobs |
| `backtesting/research/compare_page.py` | 3040 | contract v2, sources, groups, palette, budget, pre-2019 gate |
| `backtesting/research/study_graphs.py` | 2179 | the PNGs from contract files |
| `backtesting/research/bot_filters.py` | 2578 | designs, filters, regime composition, runners, score, exam, compare, export |
| `backtest_results/bot_filters/PREREG.md`, `FINALISTS.md`, `DEVIATIONS.md` | | windows, sealed tests, sequencing rule 13 |
| `external.py` (`supertrend`, `_supertrend`), `final10/results.csv`, `silver/SILVER.md`, `ladder/PREREG_LADDER.md` | | where the classic Supertrend was already run |
| `data/store/*/*/meta.json` | | the symbols and spans in the store (metadata only) |
| transcript and nine scripts (feature scan) | | timeframes, markets, the video's test protocol, Pine features needed |

## 2. Facts that constrain the design

- **F1. Pinned code.**
  - `tradeiq_2027/FINALISTS.md` L162-194 lists the blob ids of:
    - `tradeiq2.py`, `tradeiq2_market.py`, `tradeiq2_filters.py`;
    - `tradeiq_market.py`, `tradeiq_ind.py`, `tradeiq.py`, `external.py`, `balke.py`, `config.py`, `store.py`;
    - all nine `tradeiq2_ind_*` ports, all nine `tradeiq2_rules_*` modules, and `silver.py` and `final10.py`.
  - Study 2's `exam` and `accounts` refuse other result code (`frozen_code_check`, L2370). Result code means
    `RUN_CODE` (L589-592), the ports (glob, L605-607) and the rule module.
  - `bot_filters/FINALISTS.md` pins `bot_filters.py`, `tradeiq_ind.py`, `tradeiq_market.py`, `external.py`,
    `final10.py`, `engine/fast.py`, `engine/kernels.py` and three study-2 ports.
  - A study-4 change to any of these files therefore breaks a frozen study's reproducibility.
- **F2. Both guards are open.**
  - `tradeiq2_market.frozen()` (L195-203) is True, and `_guard` (L206-215) then passes everything.
  - `bot_filters.finalists_frozen()` (L327-335) is True, and `guard` (L338-351) then passes everything.
  - A new study that imports either gets no hold-out protection from it.
- **F3. Study 2's rules that apply even after its freeze.**
  - `_score_guard` (L218-233) raises for:
    - any symbol outside `SCORE_FROM` (only study 2's five);
    - any gold window starting before 2017-01-01;
    - any BTC window before 2019-01-01.
  - It runs inside `run_exec` (through `_window`, L1691), `metrics` (L1890), `scores`, `account_curve` (L1939),
    `unit_curve` and `buy_and_hold`.
  - `load` (L352-376) refuses symbols outside `DATA_START` (L135; `data_start` raises at L241-242). It also refuses any
    end past study 2's `DATA_END` (gold 2026-11-26, BTC 2026-11-27; L363-364).
  - `window_span` (L176-185) knows only study 2's windows and symbols. `Context.run` (L1078) uses it, and so do
    `run_variant` (L2024) and the driver's `span` (L2270).
  - `TMarket2.__init__` (L258-287) accepts only `config.SYMBOLS` (gold, BTC) and `CLAIM_CONTRACTS` (USTECm, EURUSDm,
    GBPUSDm).
  - Study 1's own guard (`tradeiq_market._guard`, L136) only checks ends against its own, now open, hold-out. So
    `_score_guard` is the only blocker below it.
- **F4. Name collisions.**
  - `tradeiq2.port_files()` = every `backtesting/research/tradeiq2_ind_*.py`.
  - `CodeSnapshot.changed()` (L687-696) reports a file that appears in that glob as "added". From then on, study 2's
    `exam` and `accounts` stop with `CodeChangedError`.
  - The rule prefix is `tradeiq2_rules_` (L114). `_require_api` (L427-433) refuses keys outside `MODULE_KEYS`.
  - So **every study-4 file must use the prefix `tradeiq3_`**.
- **F5. The video's own sample and protocol** (transcript, chapters 3-5 and 15).
  - Markets: 11 (BTC, ETH, SOL, BNB, XRP, EURUSD, GBPUSD, USDJPY, gold, the S&P 500 and the NASDAQ).
  - Chart and span: the 4H chart, January 2021 to October 2026.
  - Protocol: default settings, signals only, entry at the next open, a stop 2 ATR away = 1R, no target, exit on the
    opposite signal.
  - Five checks:
    1. at least 200 trades;
    2. profitable in the older half and in the newer half;
    3. profitable on most markets;
    4. profitable without its five best trades;
    5. profitable after the costs are doubled.
  - It ranks by profit per trade in R, and also reports R per year per market.
  - Filters it recommends: the 200 EMA side for several scripts, ADX above 20 for two, and the daily 50 EMA for PMax.
  - AlphaTrend and Hull Suite are not named anywhere in the transcript (grep). Whether they are eligible scripts or
    controls is a PREREG decision.
- **F6. The classic Supertrend has already been scored.**
  - `external.supertrend` (L1417) wraps `_supertrend` (L1385), KivancOzbilgic's logic.
  - FINAL10 scored "V3-lite + H4 Supertrend filter" (gold, rank 10) and "Supertrend + bot votes" (BTC) on 8y, 5y,
    new (2018-11-13..2021-01-01) and 1y (`final10/results.csv`, 12 rows).
  - The ladder study used Supertrend(10, 3) H4 as a basket gate.
  - The silver study ran Supertrend H4 (10, 3.0) and (10, 4.0) on XAGUSDm over 2018-11..2026-11 (`silver/SILVER.md`
    L18, L81).
  - So the direction of the classic Supertrend is "not a clean test" anywhere from 2018-11-13 on, on gold, BTC and
    silver (compare study 3's `T1_NOT_CLEAN`, L2077).
  - The video's standalone protocol has never been run on any of them.
- **F7. The store** (directory metadata only).

| Symbol | Months | First | Last tick |
|---|---|---|---|
| XAUUSDm | 131 | 2016-01 | 2026-11-25 23:59:59 |
| BTCUSDm | 107 | 2018-01 | 2026-11-26 23:59:59 |
| XAGUSDm, EURUSDm, GBPUSDm, USDJPYm, AUDUSDm, NZDUSDm, USDCADm, USDCHFm | 109 | 2017-11 | 2026-11-15 |
| USTECm, US30m | 78 | 2020-06 | 2026-11-13 21:54 |

  - The store has no ETH, SOL, BNB, XRP or US500.
  - Gold's Exness archive starts in 2016-01 (memory note), so nothing earlier exists.
  - Gold 2016 has three archive holes (`tradeiq_2027/DATA.md` L77-83): 22-27 Jan, 25 Mar - 1 Apr, and 27-29 Jun.
  - The silver store has no raw ticks, only per-second data and M1 bars (`silver/PREREG_SILVER.md` L19). That is
    enough for the M1-bar harness.
- **F8. Contract sizes outside gold and BTC.**
  - `multisymbol.py` L102-105: silver 5,000 oz with 3 digits; FX 100,000 with 5 digits (3 for JPY), in the quote
    currency.
  - `balke.INDEX_SPECS` L79: USTECm and US30m, 1.0 with 2 digits.
  - JPY-, CAD- and CHF-quoted pairs need a USD conversion for $ accounts. In R-multiples they need none, which is study
    2's approach for its claim markets.
- **F9. Volume.**
  - BTC uses Binance BTCUSDT volume (`Context.volume`, L1038-1045): study 1's 1h klines on 1H and above, the 5m klines
    on M5/M15. Gold uses tick volume.
  - The klines on disk end at `tradeiq_market.BINANCE_LAST_DAY` = 2026-11-26, and the loaders handle BTCUSDT only.
  - Volume-reading scripts: AlphaTrend (MFI unless its no-volume switch is set), RMI Trend Sniper (MFI), Volume
    SuperTrend AI (volume-weighted average with a kNN step), and Precision Sniper (volume checks among its
    confirmations).
- **F10. Higher timeframes.**
  - Precision Sniper's optional HTF read (off by default) and its prior-day high/low both use `[1]` with
    `lookahead_on`. That is the value of the last HTF bar closed at or before the chart bar's open: the harness's
    `htf_at_open` (L385-389), not `htf_at` (L379-382). Hull Suite's HTF option is off by default.
- **F11. Pine features the nine scripts use** (keyword scan).
  - Pivots: Pivot Point SuperTrend, AlgoAlpha Smart Money Breakout and Precision Sniper. Their confirmation is delayed
    by the right-hand length.
  - `request.security`, sessions with a time zone, VWAP, `ta.dmi`/ADX, arrays and user types (its own trade
    object): Precision Sniper (1,022 lines, v6).
  - Loops over past data (kNN): Volume SuperTrend AI.
  - Pine versions: v4 for Pivot Point SuperTrend, Profit Maximizer, Supertrend and Hull Suite (declared as
    `study`); v5 and v6 for the others.
  - None calls `strategy.*`. "Profit Maximizer Strategy" is an indicator.

## 3. Reuse as is (import, never edit)

### 3.1 The harness engine (`tradeiq2_market.py`)

| Component | Lines | Use in study 4 |
|---|---|---|
| `Variant` | L657-678 | grid rows (`symbol\|tf\|...` ids; params) |
| `Entries` / `entries` | L714-780 | market entries: stop level or distance, targets (level / dist / R), break-even, own `exit_bar`, `risk`, `tag`, `close_gap` |
| `Orders` / `orders` | L783-864 | stop-entry orders (breakout scripts), OCO, `until`, `on_fill` |
| `Leg`, `ONE_LEG` | L867-891 | partial exits (equal weights in the account, see 4.5) |
| `Exec`, `state_exec`, `event_exec`, `lanes_exec` | L894-992 | state and event rules, per-bar exit masks, per-bar stop tightening (`tighten_long/short`, `tighten_be`) |
| `Context` (`bars`, `get`, `volume`, `volume_missing`, `atr`, `ny`) | L1009-1071 | the per-symbol cache. Not `allow` (study 2's filters only) and not `run` (study 2's windows) |
| `_Sim`, `_run_single`, `_combine_legs`, `_marks`, `_sum_marks`, `COUNT_KEYS` | L1137-1832 | the engine. Frozen, so its private API is stable |
| `Run2` (with `slim`), `r_stats` | L1102-1131, L1874 | runs, and R per trade (`r` = P/L / (k × risk), costs included: the video's R) |
| `htf_at`, `htf_at_open`, `atr14` | L379-395 | last closed HTF bar, at the chart close or at the chart open; Pine `ta.atr` |
| New York clock | L400-434 | sessions (other time zones: `external.local_seconds(t, tz)`) |
| `TMarket2.tbars` ('M5', 'M15', '1W'; '1H'/'4H'/'1D' are study 1's bars) | L289-342 | the bars |
| Binance BTC volume (5m and 1h) and its check | L437-652 | BTC volume rows |

The video's protocol maps one-to-one onto these types:
- the decision is taken at the bar's close and filled at the next M1 open, a buy at the ask, a sell at the bid;
- `stop_dist` = 2 × ATR, measured from the fill;
- the opposite-signal exit masks reverse at the same M1 open, as study 2's RIB X0 does (`tradeiq2_rules_ribbon.rib_exec`,
  L322-349);
- x1.5 and x2 cost copies come from `mk.costed(c)`.

The scripts' own exits fit as well:
- Trailing lines that do not depend on the entry fit `tighten_long/short` arrays: the Supertrend line, the PMax line,
  the AlphaTrend line, Pivot Point SuperTrend's trailing line and the VST bands. Each level is applied at the next M1
  open when it is below the bid, otherwise that open becomes a market exit (`_rows_after`, L1321-1345).
- Close-based trails fit an entry's own `exit_bar` or `on_fill`, as study 2's COIL X-TR and ORB O5 did.

### 3.2 Filters (`tradeiq2_filters.py`)

- The filters: `allow(ctx, tf, name)` (L155-176) for F0, F1 (SMA200 on the same timeframe), F2-4H / F2-1D, F3
  (TSI 5/25), LO, FR (the ribbon of the higher timeframe) and FS (the dashboard's bias).
- How they apply: `as_state_filter`, `gate_entries`, `gate_orders`, `fill_masks` and `combine` (L179-232).

### 3.3 Studies 1 and 2 as building blocks

- `tradeiq_ind.py`, verified Pine ports: `sma`, `ema` (seed choice), `rma`, `wma`, `hma`, `stdev`, `rsi`, `tsi`,
  `true_range`, `atr`, `crossover` / `crossunder` / `cross`, `change`, `hist`, `math_sum`, `laguerre_rsi`, `vwrsi`,
  `qqe_mod`, `ma200`.
- `tradeiq.py` (study 1's driver): `bootstrap_pvalues` (L671), `multiple_testing` (L730), `exam_rule` (L780),
  `verdict` (L632), `_most`, `as_two_windows` (L1836), `blob_id` (L462), `read_frozen` (L1582), `Study` (L294) and
  `bh_run` (L1999).
- Study 2's reconciled ports used as components:
  - `tradeiq2_ind_coil.adx` (L385): Pine `ta.dmi(14, 14)`. Its `_dmi` also returns +DI and -DI. This serves the
    video's ADX > 20 filter.
  - `tradeiq2_ind_wyckoff.pivots` (L1473): `ta.pivothigh/low(x, L, L)`, equal left and right lengths only, strict
    ties.
  - `tradeiq2_ind_ribbon.lowest` / `highest`.
  - The ribbon, the dashboard and Heikin Ashi as partners in our own combinations: FR and FS through
    `tradeiq2_filters`, and the Heikin Ashi overlays M1-M5 through `tradeiq2_rules_ha`.
- A third-opinion Supertrend: `external._supertrend`, already used by FINAL10, the silver study and the ladder study.
  It can play the role of the unreviewed scratch port of `porting/ribbon.md` section 5: a cross-check, never the
  production port.

### 3.4 Driver helpers in `tradeiq2.py` that read no study-2 global

These can be imported:
- files: `_atomic`, `write_csv`, `write_text`, `_bool`, `read_grid`, `read_results`, `_CsvStream`;
- code and data identity: `blobs_of`, `env_versions`, `binance_identity`, `data_identity`, `market_info`;
- resumable parts: `part_path`, `write_part`, `part_ok`, `part_seconds`, `read_part`, `_drop_part`, `_clean_tmp`,
  `_stamp`;
- the fork pool: `_Work`, `_task`, `_worker`, `_fork_pool`, `_pool`, `_rss_mb`, `exec_shape`, `_build`;
- selection and exam pieces: `_order`, `_as_str_frame`, `exam_rule`, `_with_bh`;
- the page's account pieces: `_round`, `_sharpe`, `day_marks`, `_at`, `_iso_day`;
- the grid check, given a table: `Count` and `counts_of(table=...)`, `count_report`;
- claims: `Evidence` (L3470) as a base class (override `span`, `context`, `trades` and the study-1 readers).

**Not reusable as is**, because they read study-2 globals:

| Function | What ties it to study 2 |
|---|---|
| `checked_grid`, `collect`, `_variant_problems`, `grid_frame` | `MODULE_KEYS`, `MODULE_FAMILIES`, `GROUP`, `TFS`, `CLAIM_SYMBOLS` |
| `run_job` | loops over `ALL_SYMBOLS` × `MODULE_KEYS` at L1092-1095; with a custom loader it records no Binance identity (L1103) |
| `score_job`, `_score` | `M.run_variant`, so study 2's windows |
| `CodeSnapshot` | `run_code` = study 2's `RUN_CODE` + `tradeiq2_ind_*` |
| `qualification`, `champions_*`, `family_best`, `multiple_testing` | `FAMILIES`, `GROUP`, `SYMBOLS`, `M.MIN_TRADES` |
| `select`, `freeze`, `exam`, `accounts` | `M.STUDY_DIR`, `M.frozen`, `M.window_span`, `M.load` |
| `account_rows` | `M.account_curve` and `M.scores`, which run `_score_guard` |
| `CLAIMS`, `claims_table` | a module-global registry |
| `report` and its tables | study-2 tokens (`VS_F0_FILTERS`, `COMBO_NAMES`, ...) |

### 3.5 The comparison page and the graphs

- `compare_page.py`: contract v2 (`SERIES_COLS` + `SERIES_OPT`, `METRICS_COLS` + `METRICS_OPT`, `CURVE_COLS`,
  L105-117); `write_source` (L263); `validate` (L1383), which accepts any source id; `curve_stats` and the `eod_*`
  helpers; and `build(data=subset, out=<study>/index.html)` for a study page.
- `study_graphs.py`: as it is (`--source SID`). It reads only contract files, never imports a study module
  (L59-62), and names unknown sources through `CP.SOURCES` (L482-487).

### 3.6 `bot_filters.py` as a library

**Pure or duck-typed parts:**
- designs and windows: `DESIGNS` (L212-218), `design_cfg` (L222), `published_5y`, `Window`, `DEV_QUARTERS`, `FIVE_Y`,
  `DEV_WINDOWS`, the T1 and T2 definitions (L279-286), `forward_window` (L301);
- steps and clocks: `BarSides`, `Steps`, `ALLOW`, `bar_steps`, `clock_steps`, `and_steps`, `ny_hour`;
- the regime: `trend_series` (L731), `compose` (L757), `regime_at`;
- the Turtle:
  - `turtle_base`, `turtle_gate` (L789);
  - `turtle_filtered` (L799-802), which takes any book with `masks()`;
  - `turtle_exit_plan` (L867), which works from per-bar exit flags, so a Supertrend-flip exit for the Turtle needs no
    edit of `external.py`;
- variant ids: `Variant` (kind and fids come from the string alone);
- results files: `_append`, `read_rows`, `read_daily`, `read_tick_daily`, `_done`, `check_identity`;
- the score: `quarter_table`, `yardstick` (L1499), `profit_floor`, `meets_floor`, `better` (L1538), `mark_better`,
  `_rank`, `candidates` (L1561), `finalists` (L1576), `window_score` (L1586), `exam_pass` (L1593), `exam_verdict`,
  `multiple_testing` (L1708);
- the comparison: `compare_curve`, `compare_accounts`.

**The task functions.** `_sec_task` (L1124-1142) and `_tick_task` (L1145-1163) read only `bot_filters._G` (`prep`,
`trend`, `steps`). A new runner that fills `B._G` itself can therefore call them through `B._map` (L1166).

**`FilterBook` (L586-726) as a base class.** Its `line()` and `sides()` cover the 59 round-1 filters, including RIB,
MSD and HA through study 2's ports.

## 4. What must be generalised or added

### 4.1 `backtesting/research/tradeiq3_market.py`: the study-4 harness shim (about 400 lines, new)

It re-exports study 2's types and engine, and replaces only the study-specific edges.

**Tables:**
- `SYMBOLS` (gold, BTC); `TRANSFER_SYMBOLS` and `CLAIM_SYMBOLS` (section 7);
- `CONTRACTS` for the new markets (F8);
- `DATA_START` (gold 2016-01-01, BTC 2018-01-01, the others their first month);
- `DATA_END` / `LAST_TICK` per symbol, which a store refresh may move forward;
- `SCORE_FROM`, the hard floor per symbol (gold 2016-04-01, after the March 2016 hole; BTC 2018-04-01; the others
  their first month + 3);
- `WINDOWS` (section 7.4), `MIN_TRADES`, `COSTS = (1.0, 1.5, 2.0)` (x2 is the video's fifth check), `STUDY_DIR`.

**The guard.**
- `frozen()` reads `backtest_results/<study4>/FINALISTS.md` and its sha256.
- `_score_guard3`: before the freeze nothing is scored outside [DEV_START, DEV_END]. That is study 3's rule (`guard`,
  L338-351) applied to study 4's span. Never anything before `SCORE_FROM`.
- `_load_guard3`: before the freeze nothing past DEV_END (2026-11-13) is loaded, so the forward data stay unread.
  Indicators may read every bar from the data start (warm-up).

**The market and the loader.**
- `TMarket3(M.TMarket2)` for the new symbols. `TMarket2.__init__` raises for them, so build the same attributes from
  `CONTRACTS`. `Context` and `run_exec` check `isinstance(mk, TMarket2)`, and a subclass passes.
- `load3(symbol, end)` on `store.load_m1`, with study 4's tables.

**Guarded scoring entry points** that call study 2's unguarded internals:
- `run_exec3`: `_score_guard3`, then `tradeiq_market._window_ix`, then `M._run_single`, and the lanes code of
  `M.run_exec` (L1849-1869);
- `metrics3`: `tradeiq_market.metrics` + `M.r_stats` + the counts;
- `scores3`: `M.scores`'s columns plus:
  - `r_per_year`;
  - `net_ex5` and `r_ex5` (without the five best trades);
  - `streak_r` (the R lost in the longest losing streak);
  - the share of losers closed within 2 days;
- `account_curve3`: `tradeiq_market.account_curve`, or `balke._multi_kernel` for legs and lanes, as in L1939-1966;
- `unit_curve3` and `buy_and_hold3`;
- `run_variant3`: the logic of `M.run_variant` (L2009-2059) with study 4's `window_span3` and costs.

**`Context3(M.Context)`.**
- `allow` goes to `tradeiq3_filters.allow`.
- `run` uses study 4's windows.
- `volume` handles other crypto pairs: Binance ETH, SOL, BNB and XRP USDT klines, or "volume rows cannot be tested
  there".
- It is also the place for Binance klines past 2026-11-26 (the forward window). `fetch_binance_5m` and study 1's fetch
  take a `last_day`, but `load_binance_5m` and `binance_volume` default to 2026-11-26.

### 4.2 `backtesting/research/tradeiq3_filters.py` (new)

- `allow(ctx, tf, name)` hands study 2's names (F0, F1, F2-4H, F2-1D, F3, LO, FR, FS) to `tradeiq2_filters.allow`,
  cached under its own key.
- It adds the video's filters and ours:

| Id | Definition |
|---|---|
| E200 | EMA(200) side, same timeframe. The video says EMA; study 2's F1 is an SMA |
| E200-4H / E200-1D | the same on the last closed higher bar |
| ADX20 | `tradeiq2_ind_coil.adx` ≥ 20 (or > 20, a reading) |
| D50 | the side of the daily EMA(50) of the last closed 1D bar (PMax's advice) |
| STH | the higher timeframe's Supertrend direction |
| VOL | volume above its SMA, if registered |

- The gating helpers are re-exported unchanged.

### 4.3 Pine built-ins that no verified port has yet

| Built-in | Needed by | Note |
|---|---|---|
| `ta.mfi` | AlphaTrend, RMI | |
| `ta.vwma` | Volume SuperTrend AI | |
| `ta.vwap` | Precision Sniper | anchored to a session or day; TradingView's anchor for an Exness symbol against our UTC days is a reading |
| `ta.macd` | Precision Sniper | |
| `ta.pivothigh/low(left, right)` | the pivot scripts | the Wyckoff helper covers equal lengths only |
| `ta.barssince`, `ta.valuewhen` | | |
| session membership `time(tf, spec, tz)` | Precision Sniper | |
| a deterministic kNN step | Volume SuperTrend AI | |

Put them in `tradeiq3_ind_common.py`. Port A imports them. Port B writes its own from TradingView's reference code, as
study 2's port B did for `ta.alma`, `ta.stdev` and `ta.atr`.

### 4.4 `backtesting/research/tradeiq3.py`: the driver (new; adapted from `tradeiq2.py`)

Everything study 2 hard-codes changes:

| Area | What changes |
|---|---|
| Identity and naming | `SID`, `STUDY_NAME`, `REAL_STUDY_DIR`, `RULES_PREFIX = "backtesting.research.tradeiq3_rules_"` |
| Symbols and costs | `SYMBOLS`, `CLAIM_SYMBOLS`, `TRANSFER_SYMBOLS`, `NAME`, `COSTS` |
| Modules and families | `MODULE_KEYS` (proposed: `supertrend`, `alphatrend`, `pivotst`, `rmi`, `sniper`, `pmax`, `smb`, `vstai`, `hull`, and `combo` for our own combinations), `SECTION`, `FAMILIES`, `MODULE_FAMILIES`, `GROUP`, `CLAIM_MODULES`, `LOOKAHEAD_TOKENS` |
| The plan's numbers | `COUNT_TABLE`, `PLAN_ELIGIBLE` |
| Extras and readings | `EXTRAS` (the claim extras per module), `READINGS` |
| Code identity | `RUN_CODE`: the shim, `tradeiq3_filters.py`, `tradeiq2_market.py`, `tradeiq2_filters.py`, every study-2 port it reads, study 1's files, `external.py`, `balke.py`, `config.py`, `store.py`. `port_files()`: the glob `tradeiq3_ind_*.py` plus the study-2 ports used |
| Runs | `run_job`: study 4's symbols and modules, Binance identity also with the shim loader |
| Selection | `qualification`: study 2's four rules, plus the video's five checks as qualification rules or as columns (a PREREG choice) |
| Windows and exam | `span` / `exam_windows` / `verdict_of`: study 4's windows and verdict words |
| Accounts and page | `ACCOUNT_PLAN` and `SAMPLE_OF` (in, out or mixed by study 4's split; section 7.4) |
| References | buy-and-hold, study 1's finalists, **study 2's finalists and champions**, **study 3's finalists**, and the bots' designs on 5y / 8y / new / 1y (FINAL10's and the compare data, not study 1's `curves_summary`, which covers only study 1's full and hold-out spans) |
| Claims | its own `CLAIMS` registry and `claims_table`; `Evidence3` |
| Report | its own tables: each script against the Supertrend baseline, filter against F0, the video's checks, our combinations against the scripts alone, against study 2's champions and against the bots |
| Text | every markdown title |

The rule-module contract stays study 2's:
- `variants(symbol) -> [Variant]` and `build(variant, ctx) -> Exec`;
- optional `describe`, `warm`, `claim_variants` and claim extras.

A shared `tradeiq3_rules_common.signal_exec(ctx, tf, signal, side, exit, filt)` would give all nine scripts the video's
protocol in a few lines each.

### 4.5 Harness features that do not exist (needed only by some rows)

| Feature | State in the harness | Needed by | Option |
|---|---|---|---|
| An intrabar stop that trails the trade's own extreme | Per-bar tightening arrays are shared by every entry of an Exec; close-based trails exist | The scripts' own trade plans: Precision Sniper's stop, three targets and trail; SMB's three targets. The video ignores these targets in its own test | A `_Sim` subclass in the shim whose `_rows_after` asks a per-entry callback for its rows |
| Unequal partial-exit weights in the $2,000 account | `account_curve` refuses (L1946-1948; `balke._multi_kernel` takes one weight). Per-0.01-lot scores work | Unequal partials | Equal sub-legs (50/25/25 = four legs of 0.25). Live, every leg needs 0.01 lot per unit: study 2's 0.02-lot note becomes 0.04 |
| Cross-symbol portfolios | Lanes are single-symbol | "R per year on 11 markets" as one account | `multiportfolio.py`, or report it as aggregated R rows (simpler) |
| The video's five-check columns | Not computed | Every row | Add to `scores3` |
| Missing markets for the video's own replication | ETHUSDm, SOLUSDm, BNBUSDm, XRPUSDm and US500m are not in the store | The replication | Check the Exness archive's symbol list before the PREREG. Otherwise replicate on 7 of the 11 (gold, BTC, EURUSD, GBPUSD, USDJPY, USTEC; US30 is no S&P stand-in) |

### 4.6 `compare_page.py`

It is not pinned, but the finishing studies are editing it: `tests/test_compare_page.py` is modified in the working
tree. Wait for their commit first.

- Register the sources: `SOURCES`, `EXPECTED_SOURCES`, `GROUPS`, `GROUP_SHORT`, `_group_of` (L133-150, L1499-1526).
- Add `WINDOW_META` entries for the new windows, `BH_EXTRA` buy-and-hold over them, and the "pending" texts.
- The pre-2019 gate (`SEALED_BEFORE`, L67; `STUDY2_EXAM`, L101) is keyed to study 2. Study 4's sealed windows need
  their own gate before any study-4 row is exported.
- **Palette.** There are 7 slots (L1505). Six groups have curves today: the bots, FINAL10, study 1, study 2, study 3
  and Balke. Study 4 makes seven. A separate round-2 group would be the eighth and fall to the ink colour of
  buy-and-hold (`group_slots`, L1512-1520). Either put round 2 in the `bot_filters` group, or add an 8th colour that
  passes the dataviz validator, and update the slot tests.
- **Budget.** `BUDGET_MB = 11.6` (L1509). Study 2's 5y curve file alone is 14.8 MB (gzip). `build` thins
  non-featured curves (7 to 56 days) and drops them as a last resort; past that it raises. Export the all-variant
  curves to the study's own page and give the main page the focus rows (champions, finalists, each family's best row).

### 4.7 `backtesting/research/bot_filters2.py`: filter round 2 (new)

**Its own:**
- `STUDY_DIR` (proposed `backtest_results/bot_filters_trend/`), `SID`, `finalists_frozen`, `guard` and windows
  (section 7.5);
- `CODE_FILES` (bot_filters2 + bot_filters + engine + the `tradeiq3_ind_*` ports it reads).

**The registry.**
- `single_filters2()` and `filter_of2`.
- New families, each on H1, H4 and D1: ST (10, 3), ATR (AlphaTrend), PPST, RMI, PMAX, HULL, VST, PS (Precision
  Sniper's trend or regime state), SMB (structure state).
- The video's context filters: E200, ADX20, D-E50.
- A pair name of its own, because `pair_vid` (L1003-1006) orders by round 1's `SINGLE_IDS`.

**`FilterBook2(B.FilterBook)`.** `line()` and `sides()` handle the new families and hand the old ones to `super()`.
This keeps round-1 winners usable as stacked bases, for example gold Top 2 + SLOPE100-D1.

**The stage runners**, sec / tick / bar, are new code: `B.run_sec_stage` calls `B.check_vids` and builds a
`B.FilterBook` itself (L1205, L1221). Each is about 40 lines and reuses:
- `B.design_cfg`, `fast.prepare`, `B.trend_series`, `B._warm_kernel`;
- `B._G` + `B._sec_task` / `B._tick_task` + `B._map`;
- `B._append`, `B.read_rows`, `B._done`, `B.check_identity`.

**`TurtleRunner2(B.TurtleRunner)`** builds a `FilterBook2`.

**Scoring, selection and the exam:** `B.yardstick`, `B.mark_better`, `B.candidates`, `B.finalists`,
`B.window_score`, `B.exam_pass` and `B.exam_verdict`, unchanged.

**Multiple testing:** `B.multiple_testing` over the union of round 1's and round 2's 5-year daily files. Round 1's
`daily5y_<key>.csv` exist in `backtest_results/bot_filters/`. Only `compare_page` and `study_graphs` are barred from
opening that folder's dev and daily files; this module is not.

**Compare and export:** its own `read_finalists`, `compare_gate` (requires round 2's freeze and exam, plus study 4's
freeze whenever round 2's exam windows overlap study 4's sealed span) and `export_compare` with its own SID.

**The engine's limits stay:**
- The regime gate can only block a new basket. It cannot express "both sides", and it cannot change a tick design's
  exits.
- Only the Turtle's exits can change, through `turtle_exit_plan`.
- Prior hybrid tests must be disclosed as "not clean". FINAL10's "V3-lite + H4 Supertrend filter" is essentially the
  filter ST-H4 on V3-lite, and FINAL10's "Supertrend + bot votes" is a related Supertrend H4 + bot-votes combination
  on BTC.

## 5. Recommended layout for study 4

| Path | What |
|---|---|
| `backtest_results/tradeiq_supertrend/` | PREREG.md (+ .sha256), DATA.md, DEVIATIONS.md, `porting/<key>.md` × 9, STUDY.md, CANDIDATES.md, FINALISTS.md (+ .sha256), EXAM.md, CLAIMS.md, RESULTS.md, index.html, img/, CSVs; SID `tradeiq_supertrend` |
| `backtesting/research/tradeiq3_market.py` | the shim (4.1) |
| `backtesting/research/tradeiq3_filters.py` | the filters (4.2) |
| `backtesting/research/tradeiq3_ind_common.py` | the missing Pine built-ins (4.3) |
| `backtesting/research/tradeiq3_ind_<key>.py` × 9 | port A, for keys `supertrend`, `alphatrend`, `pivotst`, `rmi`, `sniper`, `pmax`, `smb`, `vstai`, `hull` |
| `tests/tradeiq3_oracle_<key>.py` × 9 | port B, a bar-by-bar plain-Python transcription with one object per Pine call site (as `tradeiq2_oracle_ribbon.py`) |
| `tests/test_tradeiq3_ind_<key>.py` (+ `_a`, `_b`) | the bit-for-bit reconciliation on real 1H / 4H / 1D bars, synthetic random inputs inside each script's input ranges, short series, and a check that removing later bars changes no earlier value; plus each port's own trap tests |
| `backtesting/research/tradeiq3_rules_<key>.py` (+ `tradeiq3_rules_common.py`, `tradeiq3_rules_combo.py`) | `variants` / `build` / `describe` / `warm` / claim extras |
| `backtesting/research/tradeiq3.py` | the driver (4.4). Commands as study 2: grid, run, select, freeze, exam, accounts, claims, report |
| `tests/test_tradeiq3.py`, `tests/tradeiq3_stub_rules.py`, `tests/test_tradeiq3_market.py`, `tests/test_tradeiq3_filters.py`, `tests/test_tradeiq3_rules_<key>.py` | driver, shim, filter and rule tests. The stub pattern is `tests/tradeiq2_stub_rules.py`'s: synthetic markets, an oracle row that must win, a look-ahead row the checks must leave out |

**The order of work:**
1. Write the PREREG with the split (7.4) and freeze it.
2. Write DATA.md: counts and spans only, including gold 2016's holes and BTC 2018's quality.
3. Build the ports and reconcile them. Real-bar reconciliation may read every bar (indicator values), but the event
   counts printed in `porting/*.md` come from Development bars only.
4. Write the rules.
5. Review them, and log every reading in DEVIATIONS.md before `run`.
6. `grid`, `run`, `select`.
7. Run an independent re-derivation of the champions (study 2's REDERIVATION.md), then `freeze`.
8. `exam` (with the base rate and the look-ahead recheck), then `accounts`, `claims`, `report`.
9. Update the compare page, build the study page and the PNGs, then commit and push.

**Compute is cheap and porting is not.** Study 2's run of 1,543 variants took about two minutes (memory note,
2026-11-28 20:20 IST). Its cost was the ports and their reconciliation. Run one symbol at a time with at most 2
workers.

## 6. Recommended layout for filter round 2

| Path | What |
|---|---|
| `backtest_results/bot_filters_trend/` | PREREG.md (+ .sha256), BUILD.md, DEVIATIONS.md, FINALISTS.md (+ .sha256), RESULTS.md, CSVs; SID `bot_filters_trend`, shown in the `bot_filters` colour group |
| `backtesting/research/bot_filters2.py` | 4.7 |
| `tests/test_bot_filters2.py` | the identity check (the ALLOW filter reproduces each design on all 24 Development accounts, stacked bases included), the registry, `FilterBook2` delegation, the guard |

**Bases:**
- the five designs as published;
- optionally gold Top 2 + SLOPE100-D1 and + MSD-D1. Study 3's exam found that these alone pass T1 and T2 (memory
  note).

**Development** is study 3's: the 23 FINAL10 quarters + the 5-year account, 2021-01-01..2026-11-13. The confirmation
is the same: raw ticks, 8 timings.

**Memory** (`bot_filters` docstring, L16-18): a gold per-second prepare of 2021-2026 is about 2.7 GB, BTC's about
twice that. Run one design at a time, and BTC alone.

**Sequencing,** as study 3's DEVIATIONS 13 did:
- rows that read `tradeiq3_ind_*` run only after those ports are reconciled;
- round 2's exam runs only after study 4's freeze, whenever round 2's exam windows lie in study 4's sealed span. That
  is the case for T0 and T1 below.

## 7. The hold-out problem

### 7.1 What has already been examined

| Span | Gold | BTC | By whom |
|---|---|---|---|
| 2016 | warm-up only (studies 2 and 3) | (no data) | never scored in any report found; the ladder PREREG says "every year from 2016 to 2026 ... read by earlier studies" (a blanket statement) |
| 2017-01 .. 2018-11-12 | study 2's Early exam (2017-2018: all 775 rows, base rate 13%); study 3's T2 (gold) | 2018-01..2018-11-12: warm-up only | studies 2 and 3 |
| 2018-11-13 .. 2020-12 | study 1 and 2 Development (2019-2022); study 3's T1; FINAL10's "new" and 8y windows (the Supertrend H4 hybrids included); the ladder study; silver (XAG) Dev | the same (BTC scored from 2018-11-13 by FINAL10 and study 3's T1 stub) | studies 1-3, FINAL10, ladder |
| 2021 .. 2024-06 | studies 1 and 2 Dev / Val; study 3's Dev; FINAL10's evidence quarters; **the video's selection** | the same | everyone |
| 2024-07 .. data end | studies 1 and 2 hold-out (study 2: every row; base rate gold 63%, BTC 22%); study 3's Dev; **the video's selection to 2026-10** | the same | everyone |
| 2026-11-13 .. data end (gold 11-25, BTC 11-26) | study 3's forward (information); inside study 2's hold-out | the same | studies 2 and 3 |

### 7.2 What is still sealed or never scored

These numbers assume the video's "about once a week" for a 4H Supertrend. 1D rules trade about a sixth as often, and
the other scripts trade less than the Supertrend.

| Span | Length | Clean for | Expected 4H trades | Caveats |
|---|---|---|---|---|
| Gold 2016-04-01 .. 2017-01-01 | 0.75 y | every rule and the bots' designs: never scored | about 35-40 | warm-up from 2016-01-03 is enough for 1H/4H (4H EMA200 ≈ 33 days), not for a D1 EMA200 (about October 2016), so D1 rows and D1-MA filters cannot be scored; three archive holes |
| BTC 2018-04-01 .. 2018-11-13 | 0.62 y | the same | about 30 | the 2018 crash regime ($6k-10k); 2018 archive quality unchecked; the D1 SMA200 exists only from late July 2018 (study 3 PREREG) |
| Forward 2026-11-13 .. (refresh) | 2 weeks now | the video's selection (ended 2026-10); seen by studies 2 and 3 for other rules | 2-3 | grows only with time; `M.load` caps at 2026-11-26/27 and the klines end 2026-11-26 |
| Transfer markets the video never used: XAGUSDm, AUDUSDm, NZDUSDm, USDCADm, USDCHFm (2017-11+), US30m (2020-06+) | up to 9 y | all nine scripts were never run there, except the classic Supertrend on silver | many | not the owner's markets; they were used for the bots' designs (multisymbol, silver, Balke); CAD- and CHF-quoted pairs in R only |
| Every span before 2021, for these rules | 4 y gold, 2.1 y BTC | no Supertrend-family rule in the video protocol; outside the video's selection | about 100 per 2 years | not unseen by us: other rules were scored there and the market path is known (gold flat then rallying; BTC 2019 rebound, 2020 crash and rally). The classic Supertrend's direction was scored there as a FINAL10 hybrid |

### 7.3 The honest options

| Option | Selection on | Exam on | For | Against |
|---|---|---|---|---|
| **A. Reverse split** (recommended) | 2021-01-01..2026-11-13, split into the video's older / newer half (D 2021-01..2024-01, V 2024-01..2026-11-13) | E1 = 2018-11-13..2021-01-01 (both symbols; = FINAL10's "new" = study 3's T1); E2 = gold 2017-01-01..2018-11-13 (= study 3's T2; study 2's Early runs to 2019-01-01) | tests the video's ranking out of its own sample; BTC gets a real exam; aligned with study 3's span (one guard logic for both studies); the page's "new" window becomes this study's out-of-sample window | numbers sit on different windows from studies 1-2's Dev / Val / hold-out (but the page compares on its common windows anyway); pre-2021 is a second look at known data; E2 is known to be hard for trend rules (13% of study 2's gold rows passed its Early window), so a pre-registered relative criterion is needed to keep the regime from deciding (7.4) |
| B. Study 2's split | Dev 2019-2022, Val 2023-2024H1 | hold-out 2024-07..end; Early gold 2017-2018 | windows comparable with studies 1-2 | the hold-out lies inside the video's selection sample and its base rate for gold was 63% (near uninformative); BTC has no exam outside the video's sample; Dev 2021-2022 is also the video's sample |
| C. Forward only | any | data after the video's end, re-scored at a pre-registered date (for example the first refresh after 2027-02-13 and again after 2027-05-13) | the only fully clean test | months away; the current two weeks are not evidence |
| D. Never-scored slivers | any | E0 = gold 2016-04..2017-01, BTC 2018-04..2018-11-13 | truly unscored, for the rules and the bots | 30-40 trades per row on 4H; 1H/4H only; holes; low power |
| E. Transfer markets | gold and BTC | the frozen champions unchanged on the five store markets the video never tested (US30 from 2020-06), in R, at x1.0 and x2 | out of the video's cross-section | answers "does it generalise", not "does it work on gold / BTC"; silver is not clean for the classic Supertrend |
| F. Statistical controls (no sealed data needed) | | placebo entries matched on side, frequency, stop in ATR and holding time (the pattern of study 2's Wyckoff pooled test); deflated Sharpe and SPA with N = every row of the study | an honest haircut on any window | not a hold-out |

### 7.4 Recommendation for study 4

**Primary: option A.**

The windows:

| Window | Span | Role |
|---|---|---|
| `d` | 2021-01-01..2024-01-01 | selection |
| `v` | 2024-01-01..2026-11-13 | selection |
| `dv` | `d` + `v` | the ranking (one continuous run) |
| `e1` | 2018-11-13..2021-01-01 | exam 1, gold and BTC |
| `e2` | gold 2017-01-01..2018-11-13 | exam 2 |
| `e0` | gold 2016-04-01..2017-01-01; BTC 2018-04-01..2018-11-13 | exam 3, 1H/4H rows only, information-weighted |
| `fwd` | 2026-11-13..data end | information; a second, pre-registered re-score later (option C) |
| `full` | from the first exam start to the data end | accounts |

The guard:
- Before the freeze, nothing outside [2021-01-01, 2026-11-13] is scored, and nothing past 2026-11-13 is loaded.
- Indicators may read every bar from the data start.
- Never score before `SCORE_FROM`.
- With these two rules every pre-2021 stub is sealed as well, for example BTC 2018-11-13..2019-01-01.

The exam rule should be relative as well as absolute:
- a champion passes a window when its net at x1.0 is above 0 and its P/DD ≥ 0.5 (study 2's rule), **and** its R per
  trade is at least the Supertrend baseline's under the video's protocol on the same window and symbol;
- report buy-and-hold, the exposure-matched buy-and-hold and every row's base rate beside it, as study 2 did.

The relative criterion stops a trending window from passing everything (study 2's gold hold-out) and a ranging one
from failing everything (its Early window).

The PREREG must say why the split was chosen: it is the video's sample, not our knowledge of how trend rules did
before 2021.

Disclose in the PREREG:
- F6 (the classic Supertrend's earlier runs);
- that studies 1-3 scored other rules in E1 and E2;
- that this survey listed the store and read study 2's exam base rates.

**Secondary:**
- Option E as a pre-registered "generalises" verdict (information-weighted).
- The video's replication on its own markets and window: gold, BTC, EURUSDm, GBPUSDm, USDJPYm and USTECm, plus the
  alts and US500 if the archive has them. This is information on Development data. It is the claims section, and the
  port's sanity check against the video's reported trade counts and R per trade.

**Multiple testing:** SPA and the deflated Sharpe over every row of study 4. In RESULTS.md, state the cumulative
count: this is the fourth study of its kind on the same two markets. Studies 1-3 ran about 2,600 rows between them
(about 730-750, 1,543 and up to 314), on top of FINAL10's designs and the ladder study's 2,661.

**Power:** about 100 trades per exam window. With R per trade spread of order 1.5-2 for trend systems, an exam
separates gross failures from plausible edges, not 0.1R from 0.3R. Say so.

### 7.5 Recommendation for filter round 2

1. Development stays study 3's.
2. **Exam T0 (primary, never scored)**, information-weighted because it is small:
   - gold tick designs on 2016-04-01..2017-01-01 (the prepare's 600 H1 bars of warm-up fit from 2016-01-03);
   - BTC designs on 2018-04-01..2018-11-13 (600 H1 bars from 2018-01-01 by late January);
   - the Turtle on its M1-bar model, market from 2018-01-01.
   - Only filters with a short warm-up can be examined there: the Supertrend family on H1/H4, D1 Supertrend (10, 3).
     Not D1 SMA/EMA200.
3. **T1 / T2 again (secondary), labelled "second use".** These windows are fresh for the new filters. But the bases'
   T1 / T2 results, and round 1's winners' (daily SLOPE100 and MSD on gold Top 2), are known. That is a leak at the
   level of ideas, so pre-register the filters from the video and the scripts only, never by analogy with round 1's
   winners.
4. **Pass rule:** a finalist is proposed only if it passes T0 and T1 (gold also T2) under `B.exam_pass`.
5. **Forward and demo:** the forward window is information. The demo account comes before anything goes live.
6. **Multiple testing:** count rounds 1 and 2 together in the SPA and the deflated Sharpe.

## 8. Gaps and open questions

1. **The guard.** No study-4 or round-2 guard exists, and both inherited guards are open (F2). The shim (4.1) and
   `bot_filters2.guard` must exist before any P/L.
2. **The scoring entry points.** Study 2's refuse new symbols, gold before 2017 and BTC before 2019 (F3), so study 4
   needs `run_exec3`, `metrics3`, `scores3`, `account_curve3`, `unit_curve3`, `buy_and_hold3` and `run_variant3`.
   The driver's `account_rows` must use them.
3. **The loader.** `M.load` caps at 2026-11-26/27 and the Binance klines at 2026-11-26. Forward exams need a loader of
   study 4's own and fresh klines.
4. **Name collisions.** Use the `tradeiq3_` prefix only (F4). A `tradeiq2_ind_*` file would break study 2's exam and
   accounts code checks.
5. **Pine built-ins** without a verified port: `ta.mfi`, `ta.vwma`, `ta.vwap`, `ta.macd`, asymmetric pivots,
   `ta.barssince` / `ta.valuewhen`, session membership with a time zone, and the kNN step (4.3).
6. **Entry-dependent intrabar trails** and **unequal partial weights in the account** are not supported (4.5). They
   are needed only for the scripts' own trade plans. Decide in the PREREG whether those rows exist, and as what: for
   example sensitivity rows, never eligible.
7. **Missing markets.** The video's 11 markets are 7 in the store. ETH, SOL, BNB, XRP and US500 would need to be
   downloaded, if the Exness archive has them, together with Binance volume for the alts' volume-based rows. Contract
   specs are needed for every new symbol (F8).
8. **The video's five checks** (and R per year) are not harness scores. Add them to `scores3`, and decide whether they
   gate qualification.
9. **AlphaTrend and Hull Suite** are not in the transcript (F5). Their status (scripts or controls) and their filters
   must be set in the PREREG without a video claim to lean on.
10. **Readings each port must register:**
    - the TradingView daily session against our UTC days (Precision Sniper's prior day and VWAP anchor);
    - `htf_at_open` against `htf_at` for its HTF option;
    - pivot confirmation bars;
    - gold's tick volume as volume, and BTC's Binance volume;
    - v4 against v5/v6 built-in defaults (for example `atr()` against `sma(tr)` in the v4 Supertrend's switch).
11. **The compare page.**
    - Source registration.
    - The palette's 7 slots (put round 2 in the `bot_filters` group, or add a validated colour).
    - The 11.6 MB budget (all-variant curves on the study page only).
    - A study-4 gate for exporting pre-2021 windows.
    - The slot tests need updating.
    - Wait until the finishing studies commit `tests/test_compare_page.py`.
12. **Disclosures for the PREREGs:**
    - F6, the classic Supertrend's runs (FINAL10's hybrids on gold and BTC, the ladder gate, silver standalone);
    - FINAL10's "V3-lite + H4 Supertrend filter" and "Supertrend + bot votes" for round 2, as "not clean" pairs;
    - this survey's reading of study 2's exam base rates;
    - the ladder PREREG's blanket claim that all years 2016-2026 were "read".
13. **Data checks before the PREREG (counts and spans only):**
    - gold 2016 quality (DATA.md lists three holes);
    - BTC 2018 quality (unchecked);
    - whether gold's 2016 and BTC's early-2018 tick months support the per-second and raw-tick prepares of the tick
      engine (study 3 used gold 2016 only as warm-up).
14. **Sequencing with the finishing studies.** Study 3's compare and export work is still uncommitted in the working
    tree (the untracked `bot_filters/compare_*.csv` and `daily_compare_*.csv`). Start study 4's code only after it is
    committed, so that no blob a running command stamps changes under it. Study 2's `CodeSnapshot` stops a run whose
    files change while it runs.
