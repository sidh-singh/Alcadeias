# BUILD: the ladder study's engine paths, and the proof that they are right

Built 18 Nov 2026 on `backtest_hedging` (step "build"), against the frozen `PREREG_LADDER.md`. Its sha256 (f64225c0…7267a)
was checked with `shasum -c` before any work: OK. No existing module was edited and nothing was committed. Every run in
this step is an engine check, the live logic, or a reference design. No variant result was read for selection.

## Result

| PREREG §6 check | Result | Files (`identity/`) |
|---|---|---|
| 1. Bit-identity, every new field at its default | **40 of 40 runs equal**: `np.array_equal` on the fills, baskets, counters and scalars arrays. 5 designs × 2 quarters × 2 symbols × 2 seeds, raw ticks. The public `fast.run` gives the same fills. | `identity.csv` |
| 2. Timeframes M4, M6, M12, M20, H3, W1 | **30 of 30**. The bars equal bars rebuilt from the rows by pandas, the warm-up equals the M1 store, and the bars sit on the MT5 grid (W1: Sunday 00:00). The W1 spot check of 3 weeks of OHLC against M1 passes. | `timeframes.csv` |
| 3. Each new path, switched on | **38 paths × 2 symbols, 0 failures**: 66,157 rule checks and 98,939 accounting checks on one F3 quarter (13 Feb - 13 May 2023, raw ticks). **132 of 132** indicator series match a plain-loop reference. The hand traces follow 3 baskets per path, fill by fill. | `features.csv`, `TRACES.md`, `indicators.csv` |
| 4. Anchors | **A1** exact. **A2** all 184 rows per symbol: 176 with today's store and 8 only with the store as it was at round 4 (note 1). **A3, A4, A5** exact. | `anchor_184*.csv`, `anchor_long.csv` |
| 5. Fold prepare (§3.2) | **Sharing is not allowed.** 13 of 24 accounts were equal. The cause is the loop-timing sequence, not the engine: with jitter off, 12 of 12 are bit-identical. **Every R4 account gets its own prepare.** Memory does not bind. | `fold_prepare.csv`, `fold_prepare_cause.csv`, `memory_r4.json` |

Final kernel: `backtesting/research/ladder_kernels.py`, sha256 `2c4f8c7e…ed29f3`. Every check above was run on this file, except two that read only default paths and come from the first build: `fold_prepare.csv` and `memory_r4.json`. Those paths are bit-identical between the builds (check 1).

---

## 1. What was added, and where (new files only)

| Module | What it holds |
|---|---|
| `backtesting/research/ladder_tfs.py` | Registers M4, M6, M12, M20, H3 and W1 in `config.TF_SECONDS` at import. M4-H3 divide a day, so epoch bucketing is MT5's grid. W1 uses an offset of `(t − 3 days) // 7 days`, so weeks open on Sunday 00:00 UTC. Grid helpers. |
| `backtesting/research/ladder_kernels.py` | `run_kernel2`: a **generated copy** of `engine.kernels.run_kernel`. The generator copies the function verbatim and applies 33 asserted, unique patches; it is kept as `identity/make_kernel.py`. The new paths sit behind slots after `CI_N` / `CF_N` (`CI2_*`, `CF2_*`) and new inputs. New reasons, counters and basket columns are appended. Positions carry their own side. |
| `backtesting/research/ladder_engine.py` | `LadderConfig(BacktestConfig)` with the new fields. It overrides `replace`, which would otherwise drop them, and `timeframes`. `prepare` = `fast.prepare` for the epoch-grid timeframes, plus W1 built here. `kernel_inputs` = `fast._kernel_inputs` unchanged, plus the extensions. `run` = `fast.run` with the new kernel (`raw=True` also returns the raw arrays). |
| `backtesting/research/ladder_ind.py` | Closed-bar series from the stored M1 bid bars: trigger series (+1 / −1 / 0) and mask series (bit 0 buys, bit 1 sells). It reuses the `research/external.py` helpers (`wilder`, `wilder_rsi`, `wilder_atr`, `true_range`, `_supertrend`). A value is in force from its bar's **close** time. |
| `backtesting/research/ladder_checks.py` | The checks of §6, the plain-loop references and the trace writer: `python -m backtesting.research.ladder_checks {identity,tfs,ind,features,anchors,long,fold,speed}`. |
| `backtesting/research/ladder_study.py` | **The runner** (§4 below): bases, the frozen level table (seed 20261118), windows, the fork-pool runner, the per-unit run, the score and the stage helpers. |

**New `LadderConfig` fields.** Each is off at its default; the second column names the PREREG level it serves.

| Field(s) | Serves | Kernel |
|---|---|---|
| `ladder_trigger_x` = `macd_hist`, `macd_cross`, `rsi_macd`, `series` + `trigger_spec` | TRIG-MACD M2-M4, TRIG-3RD | ladder modes 5-8 |
| `tier_os`, `tier_ob` (per-tier RSI levels) | LEVEL LVS, LVL | `tier_lv` |
| `gap_growth`; `gap_vol_tf`, `gap_vol_len`, `gap_vol_mult` | GAP Ggeo, GD1 | `CF2_GAP_GROWTH`, `CI2_GAP_TF` + `VOL2` |
| `stop_pct_balance`; `max_hold_min_adds` | STOP ST4-6; TIME TM4 | `CF2_STOP_PCT`, `CI2_HOLD_MIN_ADDS` |
| `be_after_adds`, `be_spreads`; `target_shrink` | TARGET TG8, TG9 | `CI2_BE_AFTER_ADDS`, `CI2_TARGET_SHRINK` |
| `final_close_tf` | FC FC6 | `CI2_FINAL_TF` |
| `add_trend_tf/_mode`, `add_gate`, `add_block_utc`, `abnormal_day` | GATE GT2-GT7 | add gates, series `SER_ADD`, `SER_ABN_*` |
| `flat_week`; `entry_gate`; `side_rsi_tf/_hi/_lo` | GT8, GT9, CONFIRM C1-C10; SIDE S5 | `CI2_FLAT_*`, series `SER_ENTRY`, `CI2_SIDE_RSI_TF` |
| `reverse`, `reverse_mult` | SIDE S6, S7 | `CI2_REVERSE` |
| `hedge_mode` = `depth` / `counter`, `hedge_stop_mult` | SIDE S8, S9 | `CI2_HEDGE_MODE`, `pos_side` |
| `partial` = `lifo` / `overlap` | PARTIAL P1, P2 | signals 9, 10 |
| `sizing` = `prefund` / `voltarget`, `pf_risk`, `pf_atr_mult`, `vt_k` | SIZING Z1, Z2 | `CI2_SIZING`, series `SER_ATR` |

Everything else in the level table was already in the engine: sizes, depth, tier lists, MACD turn, RSI cross, price step, vol gaps and stops, time stop, targets, force-close sets, trend side, entry sets, D1 in the entry, `fixed_units` and the anti-martingale control.

## 2. How it was proved

**2.1 Bit-identity (§6.1).**
- The designs are Live, V3-lite, gold Top 1 (`macd_turn` add), a `price_step` flat ladder (1 vol unit) and an `rsi_cross` ladder.
- The windows are 13 Aug - 13 Nov 2026 and 13 Feb - 13 May 2021, on both symbols, under loop timings 1 and 2.
- The old side is the existing kernel called exactly as `fast.run(light=True)` calls it; `fast.run` itself is also compared.
- The arrays compared are fills (all 21 columns), baskets (the 19 original columns), counters (the 36 original), the 22 scalars, and the new columns at their neutral values.
- Result: **40 of 40 equal.** This is also why the 22 later anchor quarters and A3-A5 match.

**2.2 Timeframes (§6.2).** Each new timeframe was checked in ticks and in per-second mode on both symbols, Feb - Mar 2023:
- the window bars equal bars rebuilt from the rows by pandas;
- the 600 warm-up bars equal the M1 store aggregated by pandas;
- the window closes equal the M1 store's closes (the closed-bar series are built from them);
- bar opens are on the MT5 grid.

W1 opens on Sundays at 00:00. Its OHLC for the weeks of 10 Mar 2019, 16 May 2021 and 4 Aug 2024 equals a direct cut of the M1 bars. Separately, M1 bars rebuilt from raw ticks equal the stored M1 bars exactly: 180,995 / 264,897 bars in May-Nov 2019 and 87,824 / 128,009 in Feb-May 2023 (gold / BTC).

**2.3 Indicators (§6.3).**
- Indicators checked: SMA, EMA (SMA-seeded), Stochastic(14,3,3), Williams %R(14), CCI(20), Bollinger %B(20,2), ATR(14), the EMA-distance in ATR, RSI(2), RSI(14), ADX(14) with +DI/−DI, Supertrend(10,3), the Donchian(20) side, VR(4,100), the MACD signal and the ATR 100-day 90th-percentile gate.
- Data: H1, H4, D1 and M20 bars of both symbols.
- Each was compared with an independent plain-Python loop written from the indicator's definition. The Supertrend loop was re-written from the Pine source.
- Also checked: the series value in force at 2,000 random times is that of the last bar that **closed** by then; the abnormal-day threshold.
- Result: **132 of 132 match** (tolerance 1e-8; CCI, %B and VR 1e-6).

**2.4 Each new path switched on (§6.3).**
- Each path ran on 13 Feb - 13 May 2023 (F3), live logic otherwise, raw ticks, loop timing 1.
- Every fill was checked against the path's rule, with values recomputed independently: bars by pandas from the M1 store; forming-bar RSI, MACD and volatility by plain loops seeded 3,000 bars back.
- Every basket was also checked for accounting: P/L = the sum of its fills, and balance = start + the closed baskets' P/L.
- Result: **0 failures** in 66,157 rule checks and 98,939 accounting checks.
- `TRACES.md` follows 3 gold baskets per path, fill by fill, with the checked quantity on each fill.

| Path | Rule checks gold / BTC | What the rule check verifies |
|---|---|---|
| sizes flat, +1, doubling | 730 / 1,125; 934 / 1,303; 765 / 908 | each add's lots = round2(mult[n] × unit × 0.01) |
| tiers T12 (M2-M20), T13 (M10-H6), T6 (+D1, W1), per-tier stricter | 593 / 1,286; 495 / 877; 996 / 1,014; 604 / 940 | add n on the n-th timeframe of the list, its forming RSI at the (tier) level |
| macd_hist, macd_cross, rsi_macd | 1,877 / 2,036; 1,423 / 1,967; 492 / 709 | the forming histogram on the wrong side; armed (≤ 0 since the last fill) then back across; RSI level reached since the last fill |
| series triggers: Stochastic, EMA-distance | 518 / 1,410; 530 / 646 | the closed-bar value of the tier timeframe at the threshold |
| gap 1 vol × 1.5^(n−1); gap 0.15 D1 vol | 314 / 421; 466 / 612 | distance from the last fill ≥ the gap (volatility at basket open) |
| stop 20% of balance; time 24 h deep | 1,605 / 1,334; 1,029 / 1,158 | stopped at ≤ −20%, no other basket's MAE below it; time stops only with ≥ 3 adds |
| target b/e after 3 adds; target / positions | 1,293 / 766; 1,322 / 852 | closed above the (shrunk) target |
| H6 final close, ladder full | 58 / 94 | only with 6 positions, H6 forming RSI ≤ 35 (buy) |
| add gates: H1 trend, EMA200 D1, ADX(H1) > 30, abnormal day, 20:30-22:30 | 83 / 182; 419 / 692; 570 / 728; 770 / 1,119; 901 / 1,215 | no add against the gate (139,521; 96,236; 57,251; 22,476; 6,296 polls blocked on gold) |
| Friday flat; ATR(H4) percentile; Supertrend(H4) confirm; D1 RSI side | 1,611 / 1,082; 1,228 / 1,032; 590 / 614; 1,572 / 1,302 | no basket opened or held across the flat window (8 weekend closes on gold); entries only where the gate allows |
| stop-and-reverse × 1, × 2 | 550 / 816; 550 / 794 | opposite basket within 60 s, at unit × mult, never reversed again (273 reversals on gold) |
| hedge-on-depth | 86 / 125 | one hedge per basket, at full depth and under water, of the ladder's net lots; unwound at tier-1 RSI ≥ 65; net target and net stop (37 hedges, 21 unwinds, 18 net stops on gold) |
| counter-ladder | 164 / 227 | adds on the other side, ≥ 1 gap further against the basket, sized by the schedule |
| LIFO; overlap | 666 / 290; 271 / 206 | the newest leg alone at its own +$1 × unit; newest + oldest ≥ one spread on both |
| pre-funded; vol-target (k and 3k); pre-funded on $20,000 | 1,595 / 1,323; 1,595 / 1,323 and 470 / 886; 1,591 / 1,417 | unit at every open = the formula (units 1-10 covered) |

**2.5 Anchors (§6.4)**, the live logic of this branch (v3.9.2) run on the new engine:

| Anchor | Pre-registered | New engine |
|---|---|---|
| A1 gold, 13 Aug - 13 Nov 2026, seed 2 | +$58.20, 3,653 baskets | **+$58.20, 3,653** |
| A1 BTC, same | +$170.57, 2,595 | **+$170.57, 2,595** |
| A2 gold, 184 runs | mean −$1,015, 172 lost, 27 wiped | **184 of 184 rows equal** (note 1) |
| A2 BTC, 184 runs | mean −$1,470, 174 lost, 97 wiped | **184 of 184 rows equal** (note 1) |
| A3 gold, 8 years, per second | wiped 2019-05-21 13:35 after 1,938 baskets | **same** |
| A3 BTC | wiped 2019-06-26 03:57 after 1,997 baskets | **same** |
| A4 gold, per unit, 8 years | −$39,690 over 62,937 baskets | **−$39,689.81, 62,937** |
| A4 BTC | −$62,821 over 56,842 | **−$62,820.81, 56,842** |
| A5 gold V3-lite, 8 years | $11,957.34, max DD 33.0% | **$11,957.34, 33.0%, 809 trades** |
| A5 BTC V3-lite | $2,914.34, max DD 18.33% | **$2,914.34, 18.33%, 1,154 trades** |

**2.6 Fold prepare and memory (§6.5, §3.2).**
- Test: 3 twelve-month accounts in F1 × {L0, V3L} × seeds 1, 2 × both symbols, each run from a fold-wide two-year tick prepare and from a prepare of its own window.
- Result: **13 of 24 equal**. For example, gold V3L from 13 Nov 2019, seed 2: $2,473.27 / 153 baskets shared, against $2,350.44 / 155 own.
- Not the cause: the warm-up. 600 against 900 warm-up bars gives 12 of 12 bit-identical runs (`warmup_sensitivity.csv`). The bars are identical too.
- The cause is the start: a fold-wide prepare lets the account's first poll see the last quote before its start, so that poll is live and takes one jitter draw. In its own prepare the first poll is a dead skip. The whole loop-timing sequence is then shifted by one draw.
- Proof: with jitter off, all 12 shared / own pairs are bit-identical (`fold_prepare_cause.csv`).
- **Rule applied as pre-registered: every R4 account gets its own prepare, in ticks mode.** The runner does this anyway (one prepare per window).
- Memory: the largest one-year account is gold 2025-26 with 97.6 M ticks (≈ 2.3 GB of arrays); the two-year folds hold 39-204 M ticks. A one-year F3 tick prepare shared by 6 fork workers peaked at ≈ 2 GB (system-wide available-memory drop, approximate on macOS). The 8-year per-second runs peak at 7.8 GB (BTC), one process. **Memory does not bind.**

## 3. Speed (one quarter, 13 Feb - 13 May 2023, raw ticks, median of 3; Apple M1)

| Run | Gold (7.7 M rows) | BTC (8.3 M rows) |
|---|---|---|
| existing engine, live | 1.38 s | 1.91 s |
| new engine, live | 1.41 s | 1.94 s |
| new engine with a series trigger / MACD cross / D1 gap / hedge / counter / LIFO / pre-funded / Friday flat / EMA200 add gate / Supertrend confirm | 0.6-1.4 s (shorter where the account is wiped early) | 1.7-2.2 s |

- Preparing a quarter takes 0.7-0.9 s; an 8-year per-second prepare takes 8-17 s.
- The first compile of `run_kernel2` takes about 30 s (cached in `NUMBA_CACHE_DIR`).
- The stage-A smoke (448 designs, one F1 week, per second) took 0.23 s a run.
- **The new paths cost about 2%** (gold 1.41 vs 1.38 s, BTC 1.94 vs 1.91 s). At about 1.6-2.2 s per tick quarter, R1 (≈ 1,500 pairs × 22 accounts per symbol) is about 3 h per symbol on 6 workers.

## 4. The runner: how the search steps call it

```
python -m backtesting.research.ladder_study levels                      # levels.json, LEVELS.md (the frozen table)
python -m backtesting.research.ladder_study stageA SYMBOL OUT.json      # stage-A designs + the skip log
python -m backtesting.research.ladder_study run SYMBOL DESIGNS.json RUNG OUT.csv [jobs] [mode] [spread_mult]
      RUNG = R1 | R2 | R3 | anchor | 8y | 5y | 1y | F1..F4 (12 fold accounts) | START:END
python -m backtesting.research.ladder_study unit SYMBOL DESIGNS.json START END OUT_DIR [jobs]   # R3 per-unit run
```

From Python: `ST.build(symbol, base, {dim: code})`, `ST.stage_a`, `ST.owner_grid(symbol, best_macd, best_3rd)`,
`ST.factorial(symbol, bases, {dim: [3 codes, '=' for the base value]})`, `ST.neighbours(symbol, pairs)`,
`ST.run(symbol, designs, windows, seeds, mode, jobs, out_csv)`, `ST.per_unit(...)` and `ST.score(df)`.

- **Designs** are `{"name", "base", "choice", "overrides"}`, where `overrides` are `LadderConfig` overrides of `BacktestConfig.live`.
  - `canonical()` compares the effective configuration, with the ladder cut to its depth.
  - An alternative equal to its base is not run. One equal to another is run once and listed as an alias.
  - Stage A: **448 designs per symbol** (L0 119, L5 117, LB 114, V3L 97, plus 4 bases and V3). 45 skips, each with its reason. The owner grid gives 132 unique of 168.
- **Windows** follow §2.4 and §3: R1 = 8 + 3 stress quarters; R2 = 24 quarters; R3 = 21 one-year accounts; folds F1-F4 with 12 accounts each; the 23 anchor quarters; and the continuous accounts.
  - Seeds: 1-2 for R1-R3; 1-8 for folds, the anchor and 1y; the fixed timing for per-second runs.
- **One prepare per window** is shared by fork workers (§2.6). Rows are appended to the CSV, so a run can be resumed. A design that raises is recorded with its error, never dropped.
- **Row fields:**
  - net, return %, wiped (stopped out or equity ≤ $200), max DD %;
  - baskets, adds, share of baskets with an add, mean and maximum positions, the depth histogram (`pos_hist`);
  - worst basket ($ and per unit), deepest floating loss, margin refusals;
  - time in the market, baskets a month, reversal / hedge / partial counts;
  - the W1 warm-up flag (`reads_w1`, `w1_warm_bars`: at the F1 start gold has 97 and BTC 45 weekly bars, against 577 and 316 daily bars).
- **`per_unit`** runs `fixed_units=1` on $1e9, per second and seed-free, for §5.4.
  - It keeps the daily P/L **marked to market**: the change of equity, floating included, from one trading day's end to the next. The days sum exactly to the run's net.
  - A trading day is a UTC day with at least 6 h of M1 bars. Gold's Sunday-evening hour and other short sessions roll into the next trading day, so T counts full sessions (gold 23 and BTC 31 in March 2019).
  - It also keeps the daily Sharpe, skew and kurtosis.
  - Sizing levels are ignored (the unit is fixed). A stop at x% of the balance becomes the per-unit stop it equals at $2,000 (x% × $2,000), since on $1e9 it would never act.
- **`score`** follows §2.4: key 1 wiped accounts, key 2 Q = mean r / max(max d, 5), ties broken by mean r.
- **Checked on the final kernel:** every stage-A design of both symbols runs without error on one F1 week (`designs/smoke_*.csv` in the scratch folder).

## 5. Conventions taken where the pre-registration leaves room (they hold for the whole study)

1. **Depth means the number of adds.** TG8 and TM4 ("depth ≥ 3") start at 3 adds. They are skipped on V3L, which can never make 3 adds.
2. **LEVEL.**
   - One level applies to every tier, and the final close and the hedge unwind use it too.
   - The per-tier rules are 35 − 3q and 35 + 3q (mirrored for sells), capped at the midline 50. The cap only matters beyond 5 tiers.
   - LEVEL is skipped for non-RSI triggers.
3. **The new MACD triggers read the tier timeframe's forming bar.**
   - `macd_hist`: histogram ≤ 0 (buy) / ≥ 0 (sell).
   - `macd_cross`: armed by a histogram ≤ 0 since the last fill, released when it is back above 0.
   - `rsi_macd`: the RSI level was reached at some poll since the last fill, **and** the MACD vote was against the basket at some poll since then and now points with it. The order is not enforced. The vote itself is the existing, parity-tested `slope_sign`.
4. **Third-indicator triggers read the tier timeframe's last closed bar.**
   - Slow %K(14,3,3) ≤ 20 / ≥ 80; %R(14) ≤ −80 / ≥ −20; CCI(20) ≤ −100 / ≥ 100.
   - %B(20, 2, population σ) ≤ 0 / ≥ 1; (C − EMA20) / ATR14 ≤ −2 / ≥ 2; RSI(2) ≤ 10 / ≥ 90.
   - EMAs are SMA-seeded; RSI and ATR use Wilder's smoothing.
   - A bar's value is in force from its close. An unknown value never triggers and always blocks.
5. **Gaps.**
   - Add n needs gap × k^(n−1) from the last fill.
   - GD1 replaces the gap with 0.15 × the D1 volatility unit (EW mean |ΔC| over 14 bars), measured at basket open; no basket opens until it is known.
   - Levels that need a volatility unit add H1 / 24 bars to bases that have none.
6. **Stops and targets.**
   - ST4-6: % of the balance at basket open, replacing the base's own stop.
   - TG8: once 3 adds are made, the target is one spread on the basket's lots.
   - TG9: target × unit / positions, never below one spread on the lots.
7. **FC levels move only the exit.** The entry agreement keeps the base's source (`agree_weights` = the base's force-close set).
   - FC5 on a base whose force-close is off adds only the RSI rule.
   - FC6 is the original final close from the v1 `strategy.py`: with the ladder full, close a buy when H6 forming RSI ≤ 35 (a sell when ≥ 65).
8. **Gates.**
   - GT2 / GT3: the sign of the MACD signal on the last closed bar (the same line as `trend_tf`).
   - GT6 blocks only adds **against** today's move, when |price / last D1 close − 1| > 2 × the mean |D1 return| of the last 20 closed D1 bars.
   - GT7 uses tick time in UTC.
   - GT8 applies to both symbols. It closes at the first poll from Friday 20:00 (if the market has already shut, at the next open) and opens nothing before Monday 01:00.
   - GT9: a rolling 100-calendar-day 90% quantile, the current bar included.
9. **Side switching.**
   - S5 uses the forming D1 RSI(14), as the bot reads RSI.
   - S6 / S7 follow a stop-loss or force-close (score or RSI), once per original basket, sent on the next poll and valid for 60 s. They skip the entry rules but not the brake / window, the weekly flat or the data-hole quarantine. Units = round(unit × mult), not capped.
   - **S8 (hedge-on-depth):**
     - one opposite position of the ladder's net lots, once per basket;
     - it opens when the ladder is full and under water, outside the unwind zone;
     - it is unwound when the tier-1 forming RSI reaches the opposite extreme (≥ 65 for a buy basket);
     - from the first hedge on, the basket's stops, target and **net** stop (≤ 2 × the P/L frozen by the hedge) read its whole P/L, realised hedge leg included.
   - **S9 (counter-ladder):**
     - the adds go on the opposite side, released by distance alone: one gap further against the original side since the last fill (bid for a buy basket, ask for a sell);
     - the gap is the base's own, or 1 H1 vol unit if it has none; the size schedule applies;
     - the open-score gate is read for the add's own side; every exit reads the net P/L.
   - Margin with opposite positions = the larger side's margin.
10. **CONFIRM masks are AND-ed.** C11 is `trend_tf = D1` on bases without a trend filter (L0, L5), where it equals S3 and is deduplicated. On LB and V3L it is a D1 MACD-signal gate AND-ed with their H1 trend.
11. **Sizing.**
    - Z1 (pre-funded): the largest unit, from 1 to 10, whose full ladder, filled one gap apart (all at one price if there is no gap) and then a further 1.5 × ATR(D1) plus one spread, loses ≤ 30% of the balance. The unit is set at each open.
    - Z2 (vol-target): unit = clamp(round(k × balance / (ATR(D1) × contract)), 1, 10). k is chosen so that the median unit over F1-F3 at $2,000 is the live rule's 1: gold **1.039**, BTC **0.490**.
12. **Partial closes** apply only outside hedge modes.
    - After a LIFO close, the next add is measured from the newest remaining position.
    - An overlap of the last two positions is a full close (reason `overlap`).
    - The remaining basket's target reads its floating P/L, as the live bot sees its positions.
13. **CONTROL**: `profit_step` 0.5 vol units, at most 3 flat adds, a 2-vol-unit trailing exit from the entry (also a stop at −2), and the fixed target off. With the $1 target on, no add could ever be reached.

## 6. Notes for the report (deviations and caveats)

1. **A2, quarter 1 Jan - 1 Apr 2021 (the first HOLDOUT quarter).**
   - The round-4 CSV rows for this quarter were computed when the store began in January 2021 (the 2017-2020 ticks were downloaded later, in `9e4c71f`), so the indicators had **no warm-up**.
   - With that store state emulated, the new engine and the existing engine both reproduce all 16 rows to the cent and the basket.
   - With today's store, those 8 runs per symbol differ: gold mean −$1,016.87 over 184 (172 lost, 27 wiped); BTC −$1,469.77 (174 lost, **96** wiped).
   - **The "old anchor view" of §3.3 should use today's figures**, with this note.
2. **A smoke run inside F4.** Before the build checks, one smoke run printed variant results for 13 Aug - 13 Sep 2026, inside F4. Nothing from it is used. Every later variant run in this step is in F1-F3.
3. **Two hedge-path corrections, found by the trace review before any study run.**
   - First, the target ignored the realised loss of an unwound hedge leg. It booked the loss and closed on a small floating profit (−$44.53 in total).
   - Second, a re-hedge rule I had added churned hedges every second.
   - The path now follows the pre-registered wording literally: one hedge, net target, net stop. Every check of §6 was re-run on the corrected kernel.
   - A runner bug was also fixed before any use: the per-unit run raised for designs that set their own unit rule (SIZING levels).
4. **Stage A has 448 designs per symbol**, against ≈ 470 expected, because equal configurations are not re-run. All of them count towards N if they reach R1.
5. **The fold check's own memory sampler could not read the workers' private memory** (macOS permissions). Memory was measured system-wide instead (§2.6).
6. **A fold-wide prepare is never used** (§2.6). Twelve-month accounts in ticks mode each get their own prepare, which costs 2-9 s.
