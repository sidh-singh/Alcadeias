# PREREG_LADDER: pre-registration of the ladder study (XAUUSDm, BTCUSDm)

Written and frozen 18 Nov 2026 on `backtest_hedging`, **before any new run**. Inputs: `MAP.md` (engine coverage, digest, speed,
anchors) and `WEB_LADDER.md` (outside evidence, 17 extra ideas), both in this folder. The sha256 of this file is in
`PREREG_LADDER.md.sha256`. Any later change to a rule below is a **deviation**: it is logged in the final report's
"Deviations" section with its reason and its effect, and it never changes the success test in §5 or the selection rules in §4.

**The question.** Is there a DCA ladder, close to the live v3.9.2 bot but free to change, that survives and makes money on
XAUUSDm and on BTCUSDm at the bot's own sizing, after costs, on data it was not chosen on? We search hard and in good faith.
We report the truth either way, including "every ladder still fails".

**Honest limits, stated in advance.**
- Every year from 2016 to 2026 of both symbols has already been read by earlier studies. No hold-out is untouched.
- More than 1,200 designs were tried before this study (MAP §2.6).
- This study's own selection never sees fold F4 (Nov 2024 to Nov 2026, §3.1) until the last walk-forward test. F4 is therefore clean with respect to **this** study only.
- The final honest test of anything found here is the demo account.

---

## 1. Fixed conventions

- **Symbols:** XAUUSDm and BTCUSDm, judged **separately**. A design may differ by symbol, and cross-asset results are reported as a grade (§5.3).
- **Engine:** the fast numba engine (`backtesting/engine/`), copied into new modules where it must change (§6). Ticks mode with the live loop timing is the reference mode: seeds 1-8, 200 ms jitter, 100 ms open delay (`robustness.live_timing`). Per-second mode is used only where §3 says so, and labelled.
- **Account:** $2,000 virtual start, leverage 1:2000 (BTC capped 1:400 by the instrument), stop-out at 0% margin level.
  - Unit rule: `unit = floor(balance / 2500) + 1`, capped at 10, re-derived only while flat.
  - 300 s pause after any close, unless the design changes it.
- **Costs:** the recorded bid/ask spread of every tick (`spread_mult = 1.0`), swap 0, commission 0 (Exness Standard, as in the engine). The **cost stress** is `spread_mult = 1.5`. `spread_mult = 2.0` is reported for information only.
- **Wiped:** the engine's `stopped_out` flag, **or** equity ever at or below $200 (−90%).
- **Max DD:** `max_drawdown_pct` of the engine, on equity with floating losses included.
- **Vote reading:** RSI and MACD votes and triggers on the forming bar, as live.
  - Third-indicator triggers and second-indicator confirmations are read on the **last closed bar** of their timeframe. The live code can reproduce this exactly from closed MT5 rates.
  - This is labelled in every table, because the closed-against-forming reading changed V3-lite from $11,957 to $2,300 (MAP §1.1 row 7).

---

## 2. The search space

### 2.1 Bases (the frames the ladder variants are tested in)

| Code | Base | Exact settings (overrides of `BacktestConfig.live`, v3.9.2) |
|---|---|---|
| **L0** | Live v3.9.2 (the baseline) | none. Open {H1:1, M15:1}, `entry_s` 2, `entry_agree_s` 2, fc {M15:1}, `force_close_s` 1, target $1/unit, ladder Fibonacci `[1,2,3,5,8,13]` on RSI ≤ 35 / ≥ 65 at tiers `[M1,M5,M15,H1,H4]`, `ladder_s` 2, no gap, no stop |
| **L5** | Slot-5 variant (live on `hedging_*5`, untested on gold/BTC) | `ladder_multipliers=[1]*6`, `fc_weights={"H4":1}`, `agree_weights={"M15":1}` |
| **LB** | Live, bounded the way practitioners bound ladders (WEB §1, §5) | L0 + `max_adds=3`, `ladder_gap_vol=1.0`, `vol_tf="H1"`, `vol_len=24`, `stop_vol=8`, `max_hold_s=259200` (72 h), `trend_tf="H1"`, `trend_mode=+1` |
| **V3L** | V3-lite with its one add (= gold "Top 1" of round 4) on both symbols | the gold Top 1 overrides in `round4/top3_v4_XAUUSDm_designs.json`: H1 votes, H1 trend, force-close off, 4 h loss pause, target 10 / stop 8 vol units, one flat add on an M5 MACD turn ≥ 1 vol unit away |
| ref **V3** | V3-lite, no ladder | the V3-lite overrides from the same file. A reference only; it is not a base for ladder dimensions |

### 2.2 Dimensions and levels

The levels of each dimension are listed below. The base's own value is never re-run. A level that does not apply to a base is skipped (for example, RSI thresholds when the trigger is a MACD turn), and every skip is logged. For sells, every rule is mirrored. "Vol unit" is the engine's volatility unit (`vol_tf` H1, `vol_len` 24, unless stated).

| Dim | Owner point | Levels (alternatives to the base) | n | New code? |
|---|---|---|---|---|
| **SIZE** | 1-3 | flat `1,1,1,…`; +1 `1,2,3,4,5,…`; doubling `1,2,4,8,16,…`; Fibonacci `1,2,3,5,8,13,…` (live). The last element repeats when the ladder is deeper | 3 | no |
| **DEPTH** | 4, 9 | `max_adds` 1, 2, 3, 5, 8, 12. A tier list shorter than the depth repeats its last timeframe | 5 | no |
| **TIERS** | 4 | T1 `[M5,M15,H1]`; T2 `[M1,M5,M15]`; T3 `[M5,M15,H1,H4,D1]`; T4 `[M15,H1,H4,D1,W1]`; T5 live + D1; T6 live + D1 + W1; T7 `[H1,H4,D1]`; T8-T11 one timeframe repeated ×5: M5, M15, H1, H4 | 11 | W1 (M) |
| **GRAN** | 5 | T12 `[M2,M4,M6,M10,M20]`; T13 `[M10,M20,H2,H3,H6]`; T14 `[M30,H2,H3,H6,H8,H12]`; T15 `[M1,M3,M5,M10,M15,M30,H1,H2,H4]`; T16 `[M6,M12,M20,H3,H8]` | 5 | M4, M6, M12, M20, H3 (S) |
| **LEVEL** | 4 | RSI 20/80, 25/75, 30/70, 40/60, 45/55; per-tier stricter when deeper (35, 32, 29, 26, 23, …); per-tier looser when deeper (35, 38, 41, 44, 47, …) | 7 | per-tier (S) |
| **TRIG-MACD** | 6 | `macd_turn` (exists); MACD histogram on the wrong side (≤ 0 for a buy add), forming bar; signal-line cross back in the basket's favour, forming bar; RSI level **and** MACD turn ("wait for the turn") | 4 | 3 new (S) |
| **TRIG-3RD** | 7 | closed bar of the tier timeframe: Stochastic(14,3,3) %K ≤ 20; Williams %R(14) ≤ −80; CCI(20) ≤ −100; Bollinger(20,2) %B ≤ 0; distance (close − EMA20)/ATR14 ≤ −2; RSI(2) ≤ 10 (Connors). Plus `rsi_cross` and `price_step` (1 vol unit), which exist | 8 | series input (M) |
| **GAP** | 9 | `ladder_gap_vol` 0.5, 1, 2; geometric gap 1 × 1.5^(n−1) and 1 × 2^(n−1); 0.15 D1 vol units (`vol_tf` D1, `vol_len` 14) for the gap only; `ladder_min_interval_s` 300 | 7 | geometric (S) |
| **STOP** | 9 | `stop_vol` 4, 8, 12; basket stop at 10%, 20%, 30% of the balance at basket open | 6 | % stop (S) |
| **TIME** | 9 | `max_hold_s` 24 h, 72 h, 168 h; 24 h only once depth ≥ 3 | 4 | deep-only (S) |
| **TARGET** | exits | $0.5, $2, $5, $10 per unit; `target_vol` 2, 4, 8; break-even + one spread once depth ≥ 3; target_0 / depth | 9 | shrink (S) |
| **FC** | exits | force-close {H1:1}, {H4:1}, {D1:1}, off; owner's RSI force-close (`fc_rsi_tfs=["H1","H4"]`); H6 RSI final close only when the ladder is full (the live intent) | 6 | full-only (S) |
| **GATE** | 9 | `ladder_s` off; adds only with the H1 trend (MACD signal sign); adds only with the H4 trend; adds only on the EMA200(D1) side; no adds while ADX(14, H1) > 30; abnormal-day pause (\|today's return so far\| > 2 × the 20-day mean \|D1 return\|); no adds 20:30-22:30 UTC; flat at Friday 20:00 UTC, no new basket until Monday 01:00 (gold; BTC the same clock); no new basket while ATR(H4) is above its 100-day 90th percentile | 9 | gates (S); ADX, ATR-pct as series (S-M) |
| **SIDE** | 8 | (8c) entry side with / against the H4 trend; with / against the D1 trend; D1 RSI reversal (D1 RSI ≥ 70: sells only, ≤ 30: buys only). (8b) stop-and-reverse at the stop or force-close, same size; the same at entry size × 2. (8a) hedge-on-depth: at full depth, one opposite position of the net size, unwound on the opposite tier-1 RSI extreme, pair closed at net ≥ target or at a net stop of 2 × the frozen loss; counter-ladder: once under water by the gap, adds go on the **opposite** side with the size schedule, and the basket closes on net profit ≥ target | 9 | 8b (M); 8a (L) |
| **ENTRY** | entries | {H4,M5} with v3.9.2 force-close and agreement; the exact pre-v3.9.0 set ({H4,M5}, fc {M15:4,H1:3,H4:2,D1:1}, `force_close_s` 12, `entry_agree_s` 0); {H1,M15,D1} with `entry_s` 2 and 4; {H4,M5,D1} with `entry_s` 2 and 4; {H1} alone; {H4,H1,M15} `entry_s` 4; RSI-only votes {H1,M15}; `entry_agree_s` 0. When the force-close changes, `agree_weights={"M15":1}` keeps the live agreement | 10 | no |
| **CONFIRM** | RSI + 2nd | gates **new baskets**, closed bars: EMA200(D1) side; EMA50(H4) side; Supertrend(10,3) H4 side; ADX(14,H4) < 25 to allow; ADX ≥ 25 → only the +DI/−DI side; Stochastic(14,3,3) H1 %K ≤ 30 for buys / ≥ 70 for sells; CCI(20) H1 ≤ −100 / ≥ 100; Bollinger %B(20,2) H1 ≤ 0.2 / ≥ 0.8; Donchian(20) H4 breakout side; variance ratio VR(4) < 1 on 100 H1 bars to allow; D1 MACD-signal trend (`trend_tf="D1"`) | 11 | regime series (S each) |
| **SIZING** | 9 | pre-funded unit: the largest unit whose full ladder, from the entry price to the last tier plus a further 1.5 × ATR(D1), loses ≤ 30% of the balance (floor at 1, cap 10); volatility-targeted unit `clamp(round(k · balance / (ATR_D1 · contract)), 1, 10)` with k set so that median unit = live median; `fixed_units=1` | 3 | pre-funded, vol (S) |
| **PARTIAL** | 9 | LIFO: close the newest add alone when it reaches its own +$1 × unit; overlap close (newest leg's profit ≥ oldest leg's loss + one spread: close both) | 2 | (M) |
| **CONTROL** | 9 | anti-martingale: adds to winners (`profit_step` 0.5 vol units, at most 3) with a 2 vol-unit trailing exit | 1 | no |

That is **120 alternatives** per base, before skips.

**Not in the search, and why:**
- Range-reset grids (WEB idea 14) are a different strategy, not the bot's ladder.
- VWAP has no rigorous evidence (WEB §6, grade D).
- News calendars: there is no event data in the store.

### 2.3 The staged funnel

The unit of counting is a **(design, symbol) pair**. Every pair that reaches rung R1 counts towards the multiple-testing burden (§5.4), whatever happens to it later.

| Stage | What | Size per symbol (≈) |
|---|---|---|
| **A** | one dimension at a time around each base (L0, L5, LB, V3L); plus the 4 bases and ref V3 | ≈ 470 |
| **O** | the owner's grid, forced, whatever stage A says: SIZE (4) × tier lists {T0 live, T1, T3, T5, T6, T12, T13} (7) × trigger {RSI level, the best TRIG-MACD level from A, the best TRIG-3RD level from A} (3) on bases L0 and LB | 168 |
| **B** | factorial. **Dimension importance** = the best R2 score gain over the base among the dimension's levels, averaged over the bases where it applies. Choose the 4 most important dimensions other than SIZE, the best 3 levels of each by R2 score (the base value may be one of them), all 4 SIZE levels, on the 2 bases with the best single-change R2 score: 4 × 3⁴ × 2 | 648 |
| **C** | local search: the 10 best pairs by R2 score after B and O; 30 neighbours each (1-3 dimensions changed: an adjacent level for ordered dimensions, a random level otherwise; RNG seed 20261118; duplicates dropped and not replaced) | ≤ 300 |
| **D** | the owner's per-dimension answers: the best level of every dimension around L0 and LB re-run on F4 with the R3 protocol, plus L5 on the full anchor and the 8-year account (§3.3). These answer questions; they cannot enter the pool | ≈ 40 |

- **Budget:** at most **3,500 pairs at R1** in total (expected ≈ 3,200) and at most **40 hours of machine time** for every rung together (expected ≈ 25 h, from MAP §3).
- **If the budget runs short,** stage C is cut first, then R2 drops to 1 seed. Any cut is logged.
- **Inputs not built.** If a new code path cannot be built and proved bit-identical (§6) within its effort class plus 100%, its levels are marked "not run" and the report says so.
  - **Fallback for the hedge paths (8a):** the bot's own entries, exported from the fast engine, are run through the M1-bar recovery simulator (`research/recovery.py`), labelled as such.

### 2.4 Rungs (successive halving)

Fresh $2,000 accounts, bot sizing, ticks mode, unless stated. **Screening rungs R1-R3 use folds F1-F3 only.**

| Rung | Runs per pair | Promotion |
|---|---|---|
| **R1** | 11 quarters × seeds 1, 2 = 22 quarter accounts. The quarters are every third quarter of F1-F3 (starting 2018-11-13, 2019-08-13, 2020-05-13, 2021-02-13, 2021-11-13, 2022-08-13, 2023-05-13, 2024-02-13), plus three stress quarters chosen by market events before any run: 2020-02-13 (Covid crash), 2021-05-13 (BTC May 2021 crash), 2022-05-13 (June 2022 crash) | the top third by score per symbol and stage, plus any pair with 0 wipes and mean return > 0, capped at half the stage |
| **R2** | all 24 quarters of F1-F3 × seeds 1, 2 = 48 quarter accounts | stages A, O and B decide from R2; at most 120 pairs per symbol go to R3 (the best by score, taken across stages) |
| **R3** | 21 one-year accounts started every quarter of F1-F3 (2018-11-13 … 2023-11-13) × seeds 1, 2; plus one per-unit run over F1-F3 (`fixed_units=1`, balance $1e9, per-second, seed-free) for the tail per unit (worst basket, deepest floating loss, daily P&L for §5.4) | the 15 best per symbol by R3 score form the **pool** |
| **R4** | the full protocol (§3.2) on every fold F1-F4, for the pool plus the references L0, L5, LB, V3L and V3; cost stress and continuous accounts (§3.3) | walk-forward picks (§4.2) |

**Score** (used at R1-R3, and for the R4 training folds), over a set of accounts with net return *r* (%), max DD *d* (%) and wiped flag *w*:
- key 1 is the number of wiped accounts (fewer is better);
- key 2 is `Q = mean(r) / max(max(d), 5)`;
- ties are broken by mean *r*.

Pairs that hit margin refusals are kept (the refusals are counted and reported).

---

## 3. Evaluation

### 3.1 Folds (two years each, aligned with the 8-year window)

| Fold | From | To | Role in selection |
|---|---|---|---|
| F1 | 2018-11-13 | 2020-11-13 | screening, training |
| F2 | 2020-11-13 | 2022-11-13 | screening, training, test of WF1 (contaminated by screening) |
| F3 | 2022-11-13 | 2024-11-13 | screening, training, test of WF2 (contaminated by screening) |
| F4 | 2024-11-13 | 2026-11-13 | **test of WF3 only; never read by R1-R3 or stages A-C** |

**Warm-up:** history before 2018-11-13 comes from Jan 2017 (gold) and Jan 2018 (BTC). D1 has ≥ 200 bars and W1 has 45-95 bars at the F1 start. RSI(14) and MACD(26) are converged to within about 4% of their starting weight. W1 results in F1 are flagged.

### 3.2 The fold protocol (R4)

In each fold, **12 fresh $2,000 accounts** start on the 13th of each of the fold's first 12 months. Each runs 12 months. Each is run under the **8 loop timings**, giving **96 accounts per fold** in ticks mode.

- **Memory:** if a two-year tick prepare cannot be shared by ≥ 3 fork workers under 14 GB peak, the 12-month accounts run in per-second mode with seed 1. The 8-timing check then moves to the fold's 8 quarters × 8 seeds in ticks mode. The mode used is reported.
- **Shared prepare:** an account may share a fold-wide prepare only if the build step shows the final equity within 1% (and identical basket counts) against a prepare of its own window. Otherwise each account gets its own prepare.

**Metrics per design, symbol and fold** (all reported):
- accounts wiped;
- worst and median max DD;
- mean, median and worst 12-month return;
- share of positive account-quarters;
- median per-account `r / max(d, 5)`;
- worst basket loss (per unit and in dollars);
- deepest floating loss;
- ladder depth reached (the distribution of positions per basket);
- share of baskets with at least one add;
- time in the market;
- baskets per month;
- margin refusals;
- per-timing mean return.

### 3.3 Additional runs for the pool and references

- **Cost stress:** `spread_mult = 1.5` on the test folds for the walk-forward picks and the 5 best pool members per symbol. `spread_mult = 2.0` for information.
- **Continuous accounts:**
  - 8 years (2018-11-13 → 2026-11-13) and 5 years (2021-11-13 →), per-second, fixed timing;
  - last year (2025-11-13 →), ticks, 8 timings, as in `final10`.
- **No-ladder twin:** the same design with `max_adds=0`, on the same protocol (needed for §5.2 S8).
- **Old anchor view:** the MAP §4.1 grid of 184 quarters for the picks, L5 and the references, so that results connect to earlier rounds.

---

## 4. Selection

### 4.1 Pool
The 15 best pairs per symbol by R3 score, plus the references. References may be picked by the walk-forward rule like any other member.

### 4.2 Walk-forward (expanding window)
| Split | Choose on | Test on | Clean? |
|---|---|---|---|
| WF1 | F1 | F2 | no (F2 helped build the pool) |
| WF2 | F1 + F2 | F3 | no (F3 helped build the pool) |
| WF3 | F1 + F2 + F3 | **F4** | **yes, for this study** |

**Choice rule on the training folds, per symbol:**
- key 1 is the fewest wiped accounts summed over the training folds;
- key 2 is the **minimum** over the training folds of the fold's Q (§2.4), computed on its 96 accounts.

A pick is fixed before its test fold is read; the script writes the pick to disk first and then runs the test. **Cross-asset:** the WF3 gold pick is also run on BTC F4, and vice versa.

---

## 5. Success: "a ladder that works"

### 5.1 The pass test, per symbol, applied to the pick of every split on its own test fold (WF1 on F2, WF2 on F3, WF3 on F4)

| # | Criterion | Strict pass | "Comfortable" |
|---|---|---|---|
| S1 | Survival | 0 wiped accounts of 96, at spread × 1.0 **and** × 1.5 | same |
| S2 | Drawdown | worst max DD of the 96 accounts ≤ 50% | ≤ 35% |
| S3 | Profit | mean **and** median 12-month return > 0; mean > 0 at spread × 1.5 | mean ≥ +10% a year |
| S4 | Consistency | ≥ 60% of account-quarters positive | ≥ 70% |
| S5 | Profit per drawdown | median per-account `r / max(d, 5)` ≥ 0.5 (≥ 0.25 at spread × 1.5) | ≥ 1.0 |
| S6 | Loop timing | ≥ 7 of the 8 timings with mean return > 0 (and S1 for all 8) | 8 of 8 |
| S7 | Continuous accounts | 8-year and 5-year accounts not wiped, max DD ≤ 50%; last year: 0 of 8 timings wiped | max DD ≤ 35% |
| S8 | It is a ladder | ≥ 10% of baskets add at least once in the test fold, **and** the mean test return beats the design's no-ladder twin | same |
| S9 | Multiple-testing haircut | §5.4: DSR ≥ 0.95 for the WF3 pick | same |

### 5.2 Verdicts, per symbol
- **WORKS** if the WF1, WF2 and WF3 picks each pass S1-S8 on their test folds and the WF3 pick passes S9. It is **WORKS (comfortable)** if the WF3 pick also meets every "comfortable" column.
- **SURVIVES, DOES NOT EARN** if S1, S2 and S7 pass in every split, but S3, S4, S5 or S9 fail.
- **EARNS, DOES NOT SURVIVE** if S3 passes but S1 or S2 fails in some split.
- **WORKS, BUT THE LADDER ADDS NOTHING** if S1-S7 and S9 pass but S8 fails. The finding is then about the frame, not the ladder.
- **FAILS** in every other case.

**Not a pass, reported apart:** a design that passes on F4 alone (today's spreads: BTC spread was 0.215% of price in 2018 and 0.017% in 2026) is reported as "conditional on today's costs". It is not a pass.

### 5.3 Cross-asset grade
For a WORKS pick, the grade is:
- **A** if the same design also passes S1 and S2 on the other symbol's F4;
- **B** if it does not. The report then carries a warning that the result is symbol-specific.

### 5.4 Multiple-testing haircut (Deflated Sharpe Ratio, Bailey & López de Prado 2014)
- **SR̂:** the WF3 pick's daily Sharpe ratio of per-unit P&L (`fixed_units=1`, balance $1e9, per-second) on F4, with T = the number of trading days in F4, and its skew and kurtosis.
- **Trial dispersion:** Var[SR] across the R3 per-unit F1-F3 runs of the same symbol.
- **N:** the number of that symbol's pairs that reached R1 in this study.
- **Formula:**
  - SR₀ = √Var[SR] · ((1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)));
  - DSR = Φ((SR̂ − SR₀)·√(T−1) / √(1 − skew·SR̂ + (kurt−1)/4·SR̂²)).
- **Pass:** DSR ≥ 0.95.
- **Also reported:** DSR with N + 1,200 (counting the earlier studies), and the ratio of the pick's F4 result to its F1-F3 score (selection inflation).

### 5.5 If nothing passes, the report will still give (pre-committed)
1. The verdict per symbol, from §5.2, in the first lines.
2. The best failing design per symbol (the WF3 pick): every criterion it failed and by how much, and its full settings.
3. The near-miss lists: "survives, does not earn" and "earns, does not survive", with the 5 best of each by score.
4. The owner's nine points and the entry and exit questions answered one by one from stages A and D. For each: the effect of every level on wipes, DD and profit around L0 and LB; whether the best level held up on F4.
   - **Sizes**, and **tier timeframes** (longer, shorter, D1/W1);
   - **granularity** (M2-M20, H2-H12);
   - **MACD** as the trigger, and **third indicators**;
   - **side switching**, and the **brainstorm** levers;
   - **{H4,M5} against {H1,M15}**, with and without D1;
   - **RSI plus a second indicator**;
   - **the slot-5 variant on gold and BTC**.
5. The view conditional on today's costs (§5.2), labelled as not a pass.
6. The pair count (N per stage and rung), the machine time used and every deviation.
7. The recommendation. No design that failed may be recommended for live money. A WORKS design goes to the demo account first, and only after an independent rebuild has matched it (§7, step 10).

---

## 6. Build, bit-identity and anchors (before any variant runs)

**New modules only.** No existing module is edited.
- `backtesting/research/ladder_tfs.py` registers M4, M6, M12, M20 and H3 in `config.TF_SECONDS` at import, plus W1 with its Sunday offset in copied functions.
- `backtesting/research/ladder_kernels.py` is a copy of `run_kernel` with new paths behind new `ci`/`cf` slots after `CI_N`/`CF_N`.
- `backtesting/research/ladder_engine.py` holds copies of `prepare`, `_kernel_inputs` and `run`, and `LadderConfig(BacktestConfig)`, which overrides `replace` and `from_dict` so that new fields survive.
- `backtesting/research/ladder_ind.py` builds the closed-bar indicator series, reusing the `research/external.py` helpers.
- `backtesting/research/ladder_study.py` is the runner. It holds the frozen level table of §2.2 and the RNG seed.
- Numba runs in the inner loop. Long jobs run as background scripts with logs.

**Checks that must pass first** (results under `backtest_results/ladder/identity/`):
1. **Bit-identity.** With every new field at its default, the new engine equals the existing one: `np.array_equal` on the fills, baskets and scalars arrays.
   - Designs: Live, V3-lite, gold Top 1, a `price_step` flat ladder and an `rsi_cross` ladder.
   - Windows: the quarters 2026-08-13→11-13 and 2021-02-13→05-13 × both symbols × seeds 1, 2, in ticks mode.
2. **Timeframes.** The bars of M4, M6, M12, M20 and H3 resampled by the engine equal the bars built from the stored M1 data at the same bucket boundaries. W1 bars open on Sunday 00:00 server time, and a spot check of 3 weeks against the M1 data passes.
3. **Each new code path**, switched on, is checked on one hand-traced quarter. The trace is a short note with 3 baskets followed fill by fill.
4. **Anchors, reproduced exactly** (to the cent and the basket count) with the new engine:
   - **A1** Live, 2026-08-13→11-13, seed 2: gold **+$58.20, 3,653 baskets**; BTC **+$170.57, 2,595 baskets**.
   - **A2** Live on the 184-run anchor, row by row against `round4/top3_v4_{holdout,dev}_*.csv`: gold mean **−$1,015, 172 lost, 27 wiped**; BTC **−$1,470, 174 lost, 97 wiped**.
   - **A3** Live, 8 years per-second: gold **wiped 2019-05-21 13:35 after 1,938 baskets**; BTC **wiped 2019-06-26 03:57 after 1,997 baskets**.
   - **A4** Live per unit, 8 years (`fixed_units=1`, $1e9): gold **−$39,690 over 62,937 baskets**; BTC **−$62,821 over 56,842**.
   - **A5** V3-lite, 8 years per-second: gold **$11,957.34, max DD 33.0%**; BTC **$2,914.34, max DD 18.33%** (`final10/runs_*_ticks.csv`).
5. **The fold-prepare check of §3.2.**

If any check fails, it is fixed before anything else runs. No variant result is used from an engine that has not passed checks 1-5.

---

## 7. Order of work

1. Freeze this file, with its sha256. (This step.)
2. Build the new modules and pass §6 checks 1-5. The hedge paths (8a) can be built in parallel with stage A, and run when ready.
3. **New reference measurements**, recorded before any variant: L0, L5, LB, V3L and V3 on R1-R3 and on the full R4 protocol; L5 also on the 184-run anchor and the 8-year account (the slot-5 answer).
4. Stage A (R1 → R2), then stage O (R1 → R2).
5. Compute the dimension importance and write down stage B's dimensions, levels and bases (to `stageB_plan.json`, before stage B runs). Then run stage B (R1 → R2).
6. Stage C (R1 → R2).
7. R3 on the at most 120 best pairs per symbol. Form the pool.
8. R4: the fold protocol on F1-F3 for the pool. Write the WF1 and WF2 picks, then read F2 and F3 as tests. Write the WF3 pick, then run F4. Then the cost stress, the continuous accounts, the no-ladder twins and the cross-asset runs.
9. Stage D (the per-dimension F4 checks) and the haircut (§5.4).
10. **Independent re-check:** a separate agent rebuilds each pick that passes (or the best failing pick per symbol) from its written rules alone, and must match its F4 result within 1%.
11. Write the report, `backtest_results/ladder/LADDER.md`, compactly. The verdict goes first. Outputs go to `backtest_results/ladder/` only, and nothing is committed.

**Expected answer, written in advance so that it can be checked.** Earlier rounds, the recovery-mechanism law (every extra unit must earn its spread back) and the outside evidence all predict the same outcome: no open-ended ladder passes. If any ladder passes, it will most likely look like a short, gap-spaced, trend-gated, stopped mean-reversion add inside a V3-lite-like frame, most likely on gold. This prediction does not change any rule above.
