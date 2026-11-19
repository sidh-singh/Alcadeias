# Ladder study: MAP (what the engine can do, what earlier rounds found, speed, the baseline anchor)

Written 18 Nov 2026 on `backtest_hedging` (step "map"). Nothing has been committed or changed in any existing module. Code references are to this
branch: `backtesting/config.py` (cfg), `backtesting/engine/kernels.py` (K), `backtesting/engine/fast.py` (F).

Effort: **S** = under 1 h, **M** = 1-3 h, **L** = half a day or more. Each estimate includes the bit-identity check described in §1.4.

---

## 1. Coverage: which dimension the fast engine supports today, and what is missing

### 1.1 Ladder dimensions (the owner's points 1-9)

| # | Dimension | Supported today? | Config field(s) | What is missing | Where it would go | Effort |
|---|---|---|---|---|---|---|
| 1-3 | Sizes: flat `1,1,1,…`, +1 `1,2,3,4,5,…`, doubling `1,2,4,8,16,…`, Fibonacci baseline `1,2,3,5,8,13` | **Yes** | `ladder_multipliers` (element 0 is the entry and must be 1; add *n* uses element *n*; the last element repeats up to 64, F:301). Depth = `min(len(ladder_tfs), max_adds)` (cfg `n_ladder_adds`). A deep ladder repeats timeframes, e.g. `ladder_tfs=["M5"]*10` (duplicates are allowed). Lots = `round2(mult × unit × 0.01)` (K:1327). Max 64 positions (K `MAXPOS`). Margin refusals are counted (`K_MARGIN_REJECT`), not fatal. | nothing | - | - |
| 4 | Tier timeframes, longer or shorter lists | **Mostly** | `ladder_tfs` (any length, any timeframe in `TF_SECONDS`: M1 M2 M3 M5 M10 M15 M30 H1 H2 H4 H6 H8 H12 **D1**); `rsi_oversold` / `rsi_overbought` (one level for every tier). `ladder_on_closed_bars` reads closed-bar RSI. | **W1** (see 1.3). Per-tier RSI levels (e.g. 30 on M1, 40 on H4): one level is shared by every tier and also by `entry_rsi_block_tfs` | per-tier level array: copied kernel, ladder block K:1093-1112 | S |
| 5 | Other granularity M4, M6, M12, M20, H3 (M2, M3, M10, M30, H2, H6, H8, H12 already exist) | **Partly** | M2, M3, M10, M30, H2, H6, H8, H12 work now | M4, M6, M12, M20, H3. All divide 86,400 s, so the epoch bucketing of F `_window_bars` (F:103) and `store.resample_bars` matches MT5 bar boundaries. The engine reads the `TF_SECONDS` dict object at run time, so a new module can register them with `config.TF_SECONDS.update(...)` without editing `config.py`. Existing configurations read none of them, so their results cannot change. | new `backtesting/research/ladder_tfs.py` (register, plus a test that the bars match MT5 bar opens) | S |
| 6 | MACD instead of RSI as the trigger, with the combinations above | **Yes (one form)** | `ladder_trigger="macd_turn"`: the tier timeframe's MACD **pivot-slope vote** was against the basket at some poll since the last fill and now points with it (K:1113-1117). It works with any `ladder_tfs`, sizes, gaps and `max_adds`. | MACD **state** triggers, the analogue of `rsi_level`: histogram ≤ 0 for a buy add; MACD under its signal line; the histogram at an extreme in volatility units; a signal-line cross back. The forming bar's `hist` and signal are already computed per poll (K:936-939, `forming_macd`) | new `ladder_mode` codes in the copied kernel, K:1097-1119 | S |
| 7 | A third indicator as the trigger | **No** | - | **Close-only indicators** (Bollinger %B, close z-score against an SMA, distance from an EMA in volatility units, ROC, CMO, a short RSI(2-5)): the forming value needs rolling sums or EMAs of closes per timeframe, built in `prepare` the way `indicator_arrays` does (K:325). **High/low indicators** (Stochastic, Williams %R, CCI, ATR, ADX): the engine keeps **closes only** per timeframe, so it also needs bar high/low arrays in `prepare` and a running high/low of the forming bar in the kernel. **Cheaper route:** compute the indicator on **closed** bars outside the kernel and pass it in as a time series, as `fast.run(regime=…)` already does for entries (F:421-447). Closed-bar indicator code exists in `research/external.py` (`tf_bars` with OHLC, `wilder_atr`, `_supertrend`, `sma`, `roll_max/min`, `wilder_rsi`). Caveat: forming-bar against closed-bar reading changed V3-lite from $11,957 to $2,300 over 8 years (HANDOFF §4.3), so a closed-bar trigger is a different strategy, not an approximation. | closed-bar series: new kernel input `lad_t, lad_v` (+1 buy add allowed, −1 sell, 0 none), checked in K:1093-1119; forming close-only: new arrays in a copied `prepare` + kernel; forming H/L: L | series **M**; close-only forming **M**; H/L forming **L** |
| 8a | Opposite-side (hedge) ladder when the basket is under water | **No** | - | The kernel has one `side` per basket and every position on it (K:717-723, valuation K:846-856, close K:1378 on). It needs a signed side per position, net-profit exits, a rule for when each leg closes and a margin rule for hedged legs. The live `app.py` also freezes when buy and sell positions are both open (HANDOFF §2.5), so a hedge ladder needs live-code changes before a demo. | copied kernel: `pos_side[i]`, exits on net or per leg | **L** |
| 8b | Alternate sides / stop-and-reverse | **No** (approximated by the recovery simulator) | - | an exit that opens the opposite basket at once (skipping the cooldown), optionally at a different size | copied kernel, after the close at K:1378 on | M |
| 8c | Side chosen by a higher-timeframe reversal signal | **Yes for entries** | `trend_tf` (sign of the MACD signal line on the last closed bar of any timeframe, D1 included) with `trend_mode=+1` (with) or `-1` (against, i.e. "reversal"); `regime=` series for any other closed-bar rule; `entry_rsi_block_tfs` | the ladder's adds cannot be gated by a trend or regime | add gate in the copied kernel at K:1056-1063 | S |
| 9 | Price-gap spacing (ATR-like) | **Yes** | `ladder_min_gap` (price), `ladder_gap_vol` (multiples of the volatility unit, needs `vol_tf`, `vol_len`), `ladder_min_interval_s`, `ladder_trigger="price_step"` (distance alone) | **growing gaps** (gap × k^n per tier); a gap per tier | K:1120-1145 | S |
| 9 | Maximum depth | **Yes** | `max_adds` | - | - | - |
| 9 | Basket stop | **Yes, per unit** | `stop_loss_usd_per_unit`, `stop_vol` (+ `vol_cap_usd_per_unit`) | a stop as **% of balance or equity**, and an account-level drawdown stop | K:1072-1074 | S |
| 9 | Time stop | **Yes** | `max_hold_s` | a time stop that applies only when the ladder is deep | K:1088-1090 | S |
| 9 | Smaller target per unit when the ladder is deep | **No** | `target_per_lot` does the **opposite** (target × basket lots / 0.01) | a target schedule by position count (e.g. break-even + x at depth ≥ k), or a target in volatility units that shrinks with depth | K:1073-1080 | S |
| 9 | Partial closes (close the last add on a bounce, LIFO) | **No** | - | the kernel closes whole baskets only; the position arrays exist, so a close of position *i* is possible | copied kernel, close block | M |
| 9 | Pause adds in strong trends (ADX) | **No** | - | ADX needs H/L (see 7). A close-only proxy is an add gate on `trend_tf` (8c). A closed-bar ADX as a series is the cheap route | as 7 / 8c | S-M |
| 9 | News / rollover hours | **Entries only** | `entry_hours_utc`; the broker's close-only minutes after breaks are modelled (`close_only_after_break_s`) | hours that block **adds**; **flat before market closures** (the recovery study found weekend gaps took a $60-budget basket to −$222) | copied kernel: an hour mask for adds; a weekly-calendar close | S |
| 9 | Others already available | **Yes** | `profit_step` (adds to winners), `trail_*` (trailing exit), `daily_loss_limit_usd_per_unit`, `loss_cooldown_s`, `fixed_units` / `step_up_balance` / `unit_max_limit`, `rsi_cross` trigger (`ladder_rsi_exit`), `ladder_s` (add blocked when the open score is against) | - | - | - |

### 1.2 Entry and exit ideas

| Idea | Supported today? | How / what is missing | Effort |
|---|---|---|---|
| OPEN_SCORE {H4, M5} (what the owner believes is live; it was live before v3.9.0) | **Yes** | `open_weights={"H4":1,"M5":1}`. The pre-v3.9.0 bot also had force-close `fc_weights={"M15":4,"H1":3,"H4":2,"D1":1}`, `force_close_s=12` and, before v3.9.1, `entry_agree_s=0` (HANDOFF §2.1). The agreement gate is the force-close section unless `agree_weights` is set, so give `agree_weights={"M15":1}` to keep the live M15 agreement while the force-close changes. | - |
| {H1, M15} (live) | **Yes** | default of `BacktestConfig.live` (reads this branch's `constants.py`, which is v3.9.2) | - |
| Either set with **D1** added | **Yes** | `open_weights={"H4":1,"M5":1,"D1":1}` etc. With three timeframes the score runs −6…+6 in steps of 2, so `entry_s` must be chosen again: 2 = net one timeframe, 4 = two, 6 = all three. A weight can be a `(rsi, macd)` tuple. D1 warm-up: 600 bars × 1.7 calendar factor is asked for, and history starts Jan 2017 (gold) / Jan 2018 (BTC), so D1 is short of 600 bars before about 2019-2020; RSI(14) / MACD(26) converge in about 100-150 bars, so windows from 2019 on are fine. | - |
| RSI base + second indicator as **closed-bar** confirmation (Supertrend, EMA trend, ADX, Stochastic, CCI, Bollinger) | **Yes, via `fast.run(regime=(t_ms, v))`** | one series, values +1 / −1 / 0, gates **new baskets only**; the indicators are computed with `research/external.py` helpers. Two filters at once: combine them into one series. The MACD-signal trend filter is built in (`trend_tf`). | S per indicator |
| Second indicator on the **forming** bar | **No** | as dimension 7 | M-L |
| RSI-only votes (drop MACD) | **Yes** | `open_weights={"H1":(1,0),…}` | - |
| RSI **level / cross** as the entry (not the pivot-slope vote) | **No** | an entry mode reading `rsi_now` (already computed per poll) | S |
| Target per unit | **Yes** | `target_usd_per_unit`, `target_vol`, `target_per_lot` | - |
| Force-close timeframe M15 / H1 / H4 / D1 / off | **Yes** | `fc_weights`, `force_close_s`, `force_close_enabled=False`, `fc_grey_fill`, `min_hold_s`, `fc_confirm_s` | - |
| Final close on the H6 RSI extreme once the ladder is full (dead in v3.9.2: fetched, read by nothing) | **Partly** | `fc_rsi_tfs=["H6"]` closes a buy when H6 RSI ≤ `rsi_oversold` **at any depth** (and every listed timeframe must agree). Missing: the condition "only when the ladder is full", and the opposite reading (close at the extreme in the basket's favour) | S |
| Take profit on RSI back to 50 / to the other level | **No** | exit reading `rsi_now` | S |
| Stop, trailing, time, book, daily limit | **Yes** | see 1.1 | - |

### 1.3 W1 bars

W1 is the only timeframe that does not fit the epoch bucketing. MT5's weekly bar opens on Sunday 00:00 server time, and epoch day 0 (1 Jan 1970) was a Thursday. W1 needs a 3-day offset in the bar id: `(t − 3·86400) // 604800`, in `_window_bars`, in `resample_bars` and in `prepare`'s `bar_t`. That means a copied `prepare` in the new module. Warm-up is also short: by Nov 2018 there are only about 95 weekly bars of gold and about 45 of BTC, against 600 asked for, so W1 RSI is unconverged before about 2020 (BTC 2021). **Effort M.** For gold the closed weekend hides the Sunday-against-Monday question. For BTC it matters.

### 1.4 How to add the missing pieces without touching existing modules

- New files: `backtesting/research/ladder_kernels.py` (a copy of `run_kernel` with new `ladder_mode` codes, per-tier levels, add gates, depth-dependent targets, partial / reverse / hedge paths behind new `ci`/`cf` slots appended after `CI_N`/`CF_N`) and `backtesting/research/ladder_engine.py` (copies of `prepare`, `_kernel_inputs` and `run`, plus a `LadderConfig(BacktestConfig)` with the new fields).
  - Caveat: `BacktestConfig.replace()` calls `BacktestConfig.from_dict` by name, so a subclass must override `replace`/`from_dict`, or the new fields are silently dropped.
- **Bit-identity proof** before any result: with every new field at its default, run Live, V3-lite, gold Top 1 (`macd_turn` add), a `price_step` flat ladder and a `rsi_cross` ladder through both engines, on 2 quarters × 2 symbols × 2 seeds in ticks mode. Require `np.array_equal` on the fills, baskets and scalars arrays.
  - Any new path must also be off in the live parity sense: `tests/test_parity.py` still compares only the original engine.
- The new timeframes (M4, M6, M12, M20, H3) need no kernel change, only registration (§1.1 row 5).
- Parallel runs: `analysis/sweep.run_grid` uses a **spawn** pool where every worker prepares its own data. `research/sizing.py:254` uses **fork**, so the workers share one prepared array set copy-on-write. Use fork for 8-year runs (memory, §3).

---

## 2. Digest: what earlier rounds found (build on it, do not repeat it blindly)

Sources: IM = `IMPROVEMENT.md`; LC = `LOGIC_CHANGELOG.md`; HO = `HANDOFF.md`; REC = `backtest_results/improve/recovery_mechanisms.md`; R4 = `backtest_results/improve/round4/`; BT = `BACKTEST.md`; SIL = `backtest_results/silver/SILVER.md`.

### 2.1 The live ladder itself
- **It is one clip, not an average-down** (HO §2.6, gold Aug-Nov 2026): the share of adds within 10 s of the previous fill is M1 12%, M5 43%, M15 85%, H1 97%, H4 100%, at a median distance of $0.24-0.28 against a $0.24 spread. **26 of 32 units go in at one price.** BTC: 79-98% of the last three tiers within 10 s.
- In that quarter, gold baskets that never added made +$4,251 and baskets that added lost $5,040. The 40 six-position baskets netted −$1,839. BTC: +$1,191 without adds, −$874 with. This is partly selection: a basket adds only when the price goes against it (HO §2.13).
- The add gate is weaker than the entry gate: adds are allowed in 45 of the 54 no-force-close sign states (HO §2.6).
- **How it dies:** the $1 target needs a 75.5-97.7% win rate, and it fell short in 22 of 23 quarters on each symbol. There is a bleed (many medium force-close losses) and a tail (full-ladder baskets of −$1,237 to −$1,944; gold on 2 Feb 2026 lost the whole account in 3 min 6 s). The unit step-up doubles the stake right after small wins (HO §2.12-2.13).

### 2.2 Changing one part
| Change (live logic otherwise) | Result | Source |
|---|---|---|
| No ladder | gold −$701 a quarter, 40/40 lost, worst basket −$217, none wiped; BTC −$184, 39/40 lost | HO §2.14 |
| A stop alone, ladder kept ($20 per unit, 3 quarters, 1 unit) | gold −$5,107 against −$4,359 live, still wiped: "the stop turns a rare large loss into frequent medium ones" | HO §2.14 (BT §10) |
| Live ladder + $60 / $200 basket stop (fixed entries) | negative in 23 of 24 cells (−$0.12 to −$2.55 per entry) | REC |
| Live ladder, no stop (fixed entries) | 99.8-100% won; in every cell one basket was ≥ $1,358 under water; 7 of 12 cells emptied $2,000 with one basket; deepest −$68,514 | REC |
| 432 OPEN × FORCE-CLOSE timeframe combinations, 5 quarters | none profitable in all five without a wipe; the 12 best gold settings: none profitable in both hold-out quarters, 75% wiped in one | HO §2.14 (BT §9) |
| Owner's rules (no entry while H1/H4 RSI is beyond 35/65, RSI force-close), ladder and $1 kept | 15 quarters 2023-26: gold −$175, BTC −$712, 0 wipes; **+ at most 3 adds: gold −$148, BTC −$620**; + H1 trend + 4 h loss pause: gold +$9, BTC −$125, but over 8 years gold was destroyed ($1 left) and BTC wiped 31 Oct 2021 | LC round 3; HO §2.14 |
| $1 → $10 target, $20 stop, force-close off (191 designs, 1 unit) | gold −$280 → −$55, BTC −$74 → +$83 a quarter | IM R1 |
| M15 force-close on / off (400 round-4 settings) | gold off +$30.1 a month against on −$1.8; BTC +$7.7 against −$5.8 | HO §4.3 |

### 2.3 Bounded ladders, triggers, spacing, depth (round 2, DEV, 1 unit, inside "H1 trend, force-close off, 4 h loss pause", averaged over 7 stop/target sizes of 2-8 volatility units; LC round 2)
| Ladder | Gold / quarter | BTC / quarter |
|---|---|---|
| no ladder | **+$265** | **+$81** |
| 1 add, price step 1 unit | +$219 | +$61 |
| 1 add, MACD turn, ≥ 1 unit apart | +$216 | +$58 |
| 1-3 adds, RSI cross-back | +$175 … +$196 | +$58 … +$78 |
| 1-3 adds, price step 2 units (flat or 1,1,2,3) | +$172 … +$188 | +$82 … +$90 |
| 2 adds, RSI level (live trigger), ≥ 1 unit apart | +$150 | +$68 |
| 2-3 adds, price step 1 unit | +$84 … +$99 | +$27 … +$45 |
| adding to winners + trailing exit | +$76 … +$258 | +$11 … +$13 |

- **Lessons:** one well-spaced add costs little; several close adds cost a lot; the live RSI-level trigger is the weakest; RSI cross-back beat RSI level on both symbols, and the MACD turn beat it on gold only. **No trigger beat no ladder on average** (IM; HO §4.3). The BTC price step of 2 units (+$82 to +$90) is the only row at or above its no-ladder figure, in one period.
- **V3 (one equal add on an M5 MACD turn, ≥ 1 vol unit away) against its no-add twin**, per quarter: gold +$321, +$102, +$53 more (DEV, CONFIRM, FINAL 2023); BTC +$9, −$27, −$21. It makes the worst basket larger (IM). This is the **only ladder that has ever beaten no ladder on held-out data** (gold). Gold Top 1 / Top 3 carry it, and gold Top 1 made $0 in 2021-22 (R4).
- **Budget ladder** (equal lots, ≤ 2 adds, hard $60 budget, flat over every closure): none of 31,952 baskets lost more than $60, but it earned $0.06 per entry **less** than not adding. More adds 0.2-0.3 ATR apart: expectancy −21.9% to −24.5% of R at worst (REC).
- **The general law (REC):** across 42 mechanisms the change in expectancy follows the extra spread paid, with a slope close to −1. **Every extra unit a ladder opens must earn its spread back.** No mechanism raised the expectancy; they only change the shape (a higher win rate bought with a larger rare loss).

### 2.4 Side switching (already measured on fixed entries, M1-bar simulator `research/recovery.py`)
- **Hedge lock** at −1 ATR, unlocked on the next signal: **identical** to closing and re-entering (largest difference 10⁻¹² USD) while holding two positions. A lock closed 4 h later costs one spread more than a stop (REC).
- **Zone recovery** (alternating, growing opposite legs 1/3/6/12): 5.5-6.9 units per entry, negative in 19-22 of 24 cells, on BTC in all twelve; worst gold basket −$1,502 (REC).
- **Stop and reverse** once, same size: expectancy −12.8% to +1.2% of R; double size: −18.4% to +3.8%, one account emptied (REC).
- **Martingale / anti-martingale** on the next basket: each emptied the account in 6 of 12 cells (REC).
- **Not yet tested:** a side-switching ladder *inside the bot's own engine*, i.e. on its own entries, forming-bar votes, $1-per-unit target and unit rule. This is new, but the identity result above predicts that a lock adds nothing beyond its spread.

### 2.5 Entry timeframes and filters
- No entry signal predicts direction. After both M15 votes up, gold was higher 4 bars later 50.8% of the time, the same as any bar. Twenty classic signals, support / resistance and divergence: none reliable. Fading against the H4 trend lost $1.44 per 0.01 lot over 4 h (IM R1; HO §2.3, §4.4).
- **H1 trend filter** (MACD signal sign, last closed H1 bar) is the largest single lever on gold: −$423 → +$6 a quarter over 191 designs. H4 trend failed outside 2025-26 (IM; HO §4.3).
- Votes: round 4, gold H1 + M15 +$16.5 a month against H1 alone +$11.8; BTC H1 +$5.0 against H1 + M15 −$3.1. M15 agreement: gold 0 +$16.7 against 2 +$11.6 (HO §4.3). **{H4, M5} and D1 in the entry score were not tested in any study since the 432-combination grid.** D1 voting is new.
- Closed-bar votes destroy the edge (V3-lite 8 years $11,957 → $2,300). Keep forming bars (HO §4.3).

### 2.6 Other context
- **Costs:** spread × 1.5 took the gold quarter from −$70 to −$1,320; 0.1 slippage per fill gave −$2,000 (HO §2.12.1). BTC spread was 0.215% of price in 2018, 0.139% in 2021, 0.052% in 2024 and 0.017% in 2026, so a $1 target per 0.01 lot was mostly spread on BTC before 2024 (HO §2.13).
- **Silver:** the slot-5 variant (flat ladder, H4 force-close) made +$811 / +$1,692 per 0.01 lot before costs ($10 / $20 target) and −$11,280 / −$8,906 after, 2018-22 (SIL). **The slot-5 variant has never been run on gold or BTC.**
- **Multiple testing:** more than 1,200 designs plus several hundred variants have been tried. The 2023 hold-out gave about a quarter of the DEV figure, and walk-forward gave +$14.1 a month against +$109.2 in-sample (HO §4.10). Every year 2016-2026 has been read, so **no hold-out is left**. The new study should pre-register its families and its selection rule, report the number of trials, and treat the demo account as the only real test.
- **Protocol that caught the traps:** fresh $2,000 per quarter × 8 loop timings **and** one continuous account (8 years, 5 years). The owner's rules had 0 wipes on fresh quarters but were destroyed over 8 years (LC round 3).

---

## 3. Speed (measured today, one process, Apple M1, 16 GB, numba 0.66; script `…/scratchpad/port_tmp/ladder/scripts/speed.py`, log `speed.log`)

The live logic (v3.9.2 defaults). One-off numba compile of `run_kernel` took 12 s.

| Run | Gold rows | Gold prepare | **Gold run** | BTC rows | BTC prepare | **BTC run** |
|---|---|---|---|---|---|---|
| One quarter (13 Aug - 13 Nov 2026), raw ticks, one loop timing | 19.7 M | 1.4 s | **1.5 s** | 11.4 M | 0.7 s | **2.0 s** |
| Same quarter, per-second rows | 5.0 M | 0.2 s | 1.6 s | 7.2 M | 0.3 s | 2.2 s |
| 8 years (13 Nov 2018 - 13 Nov 2026), per-second, live (stops at the wipe) | 124.8 M | 7 s | 3.4 s (wiped 21 May 2019) | 227.7 M | 15.5 s | 5.8 s (wiped 26 Jun 2019) |
| 8 years, the same decisions run to the end (`fixed_units=1`, balance $1e9) | - | - | **49 s** | - | - | **71 s** |
| Peak memory of the 8-year process | 5.6 GB | | | 7.5 GB | | |

**Throughput on this machine** (an estimate, not measured in parallel: 4 performance + 4 efficiency cores, so about 6 performance-core equivalents):
- **Quarter runs (ticks):** about 1.6-2.1 s each including result building, with one prepare per quarter shared by all designs. That is about **10,000-13,000 quarter-runs an hour**. One design on the full anchor (23 quarters × 8 timings = 184 runs) takes about 5-6 min on one core, or about 1 min on six. **A 1,000-design screen on the anchor takes about 15-20 hours**, so screen on fewer quarters or seeds first.
  - Memory per quarter worker is under 1 GB.
- **8-year runs (per-second, run to the end):** memory, not CPU, is the limit. With a fork pool sharing one prepared set (copy-on-write), 6 workers give about **400 gold / 300 BTC runs an hour**. With spawn (`run_grid`), only 2 workers fit in 16 GB: about 145 gold / 100 BTC an hour. Ladders that wipe stop early and cost seconds.
- Deeper ladders add fills but little time; the poll loop dominates.

---

## 4. Baseline anchors and how to reproduce them

### 4.1 Fresh $2,000 per quarter, 8 loop timings (primary anchor)
- **File:** `backtest_results/improve/round4/top3_v4_{holdout,dev}_{XAUUSDm,BTCUSDm}.csv`, rows `design == "Live"`, column `acct_net` (also `acct_wiped`, `largest_loss`, `baskets`).
- **Quarters (23):**
  - HOLDOUT 2021-01-01 … 2023-01-01, 8 calendar quarters;
  - FINAL 2023-02-01→05-01, 05-01→08-01, 08-01→11-01, 11-01→2024-01-01;
  - CONFIRM 2024-01-01 … 2025-07-01, 6 quarters;
  - DEV 2025-08-13→11-13, →2026-02-13, →05-13, →08-13, →11-13.
  - Jul - 12 Aug 2025 is not covered.
- **Totals (re-counted today):**

| Period | Gold: mean / quarter, lost, wiped, worst basket | BTC: the same |
|---|---|---|
| HOLDOUT 2021-22 (64 runs) | −$1,154, 64, 0, −$436 | −$1,767, 64, 48, −$627 |
| FINAL 2023 (32) | −$666, 24, 0, −$570 | −$1,194, 32, 3, −$402 |
| CONFIRM 2024 - Jun 2025 (48) | −$675, 47, 0, −$653 | −$1,995, 48, 46, −$1,157 |
| DEV Aug 2025 - Nov 2026 (40) | −$1,480, 37, 27, −$1,944 | −$585, 30, 0, −$811 |
| **All 184** | **−$1,015; 172 lost; 27 wiped** | **−$1,470; 174 lost; 97 wiped** |

- **Reproduce:** `robustness.timing_ensemble(E.live_config(sym), {name: (a, z)}, n_jobs=…)`. It uses seeds 1-8, 200 ms jitter, a 100 ms open delay and ticks mode (`analysis/robustness.py:40-87`; runner `round4/top3_v4.py`).
  - Pass a design as `overrides=[{…}]`.
- **Checked today, bit-identical:**
  - gold 2026-08-13→11-13 seed 2 = **+$58.20, 3,653 baskets**;
  - BTC seed 2 = **+$170.57, 2,595 baskets**;
  - both equal to the CSV rows.
  - Per-second mode is not the anchor: the same gold quarter gave −$239 on the fixed 1 s grid.

### 4.2 One continuous account (catches the slow death)
- **8 years from 13 Nov 2018**, per-second rows, fixed timing (`final10.WINDOWS["8y"]`, `fast.run(E.live_config(sym, start, end), prep)`):
  - gold **wiped 2019-05-21 13:35 after 1,938 baskets**;
  - BTC **wiped 2019-06-26 03:57 after 1,997 baskets**;
  - both reproduced today, matching `final10` / HO §2.12.2.
- **5 years from 13 Nov 2021:** gold wiped 15 Mar 2022, BTC 21 Dec 2021.
- **Last year from 13 Nov 2025**, 8 raw-tick timings: gold 8/8 wiped, BTC 5/8 (`final10/timings_1y_*.csv`).
- Other windows: HO §2.12.2.

### 4.3 A per-unit anchor without wipe truncation (new, measured today)
Run the live decisions to the end with `fixed_units=1, initial_balance=1e9`. Over 8 years this gives:
- gold **−$39,690 over 62,937 baskets** (−$0.63 a basket, per 0.01 lot);
- BTC **−$62,821 over 56,842** (−$1.11).

This lets ladder variants be compared over all 8 years in dollars per unit (expectancy, worst basket, deepest floating loss) before they are judged on a real $2,000 account, where most die in 2019.

### 4.4 What the new study should run first
1. **Bit-identity** of any new module (§1.4).
2. **The slot-5 variant on gold and BTC** (`ladder_multipliers=[1]*6`, `fc_weights={"H4":1}`, `agree_weights={"M15":1}`, everything else live), on the 184-run anchor and the 8-year account. It is live on `hedging_*5` and untested there.
3. **The size families** (flat, +1, doubling, Fibonacci) × trigger (RSI level, RSI cross, MACD turn, price step) × spacing (none, 0.5, 1, 2 vol units) × stop (none, vol-unit stop) inside the live frame and inside V3-lite's frame. Screen on a few quarters × 2 seeds, then run the survivors on the full anchor and the continuous accounts.
