# Changelog

All notable changes to the Alcadeias trading bot are recorded here, newest first.
Each version lists **exactly what changed per file** and a **Rollback** section so any
version can be reversed cleanly.

Versioning is feature-based (`vMAJOR.MINOR.PATCH`). Each entry names the git
**baseline commit** it was applied on top of, so you can always return to a known state.

**Maintenance policy (every change, no exceptions):** every change — however small — is
recorded here with per-file detail (down to the small stuff), committed together with its
code, and propagated to **all 20 live-money fleet branches** in the same change
(cherry-pick; rebase onto `origin/<branch>` for any branch behind so remote-only
credential/symbol commits are preserved; never force-push). Fleet:
`dev_btcusd1_v2`…`dev_btcusd10_v2` (BTCUSDm) and `dev_xauusd1_v2`…`dev_xauusd10_v2`
(XAUUSDm).

---

## [v2.0.0] — 2026-10-10 — RSI+MACD Slope Strategy (full rewrite of direction + management)

**Baseline:** the live v1.6.0 fleet HEAD per branch (`adcb1cb` btcusd1 / `dca6788` xauusd1).
**Branches:** `rsimacd_dev_btcusd1_v2` (off `dev_btcusd1_v2`) and `rsimacd_dev_xauusd1_v2`
(off `dev_xauusd1_v2`). **EXPERIMENT — NOT propagated to the 20 live fleet branches.**
Must pass the offline backtest before any live money.
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py`, `dashboard.py` (+ this `CHANGELOG.md`).

**Why.** The bot kept taking large losses on spikes/slippage even after the v1.6.0 ADX
regime filter. The owner decided to replace the entire trade-direction + basket-management
logic: remove everything that previously chose direction or averaged down, and rebuild entry
and exit on RSI + MACD **slope** reversals (idea inspired by mean-reversion). The martingale is
removed — one position per signal with real stops — which is what eliminates the deep spike
drawdowns (previously depth-6 H6 capitulations on an averaged-down basket).

### Behaviour — the new strategy
- **Indicators (H1 & H4):** RSI(14) and MACD(12/26/9) histogram. For each, the *latest pivot*
  (local turning point, width `k=2`) within the last `N=20` bars is found — the most recent one
  wins even if smaller than earlier pivots — and a per-bar **slope sign** (pivot → current) is
  taken. 4 slopes total. No OB/OS thresholds anymore (sign only).
- **Entry (flat only):** H4-primary / H1-confirm. H4 both +ve & ≥1 H1 +ve → BUY; H4 both −ve &
  ≥1 H1 −ve → SELL; H4 split → H1-both-aligned decides; any zero/undefined slope → WAIT. Opens a
  **single** position; a 300 s post-close cooldown blocks instant re-entry.
- **Exit (open basket):** (1) profit-protect — profit > `PROFIT_PROTECT_MIN_USD` AND **both** H1
  slopes flipped against → CLOSE; (2) hard stop — H4 both flipped against AND (either H1 against)
  → CLOSE (accept loss); else HOLD. No DCA adds, no H6.

### Change detail per file
- **`constants.py`** — REMOVED the SHA block (`SHA_LENGTH`/`SHA_MA_TYPE`/`SHA_TREND_*`),
  `STRATEGY_LOOKBACK`, `STRATEGY_SHA_THRESHOLD`, the whole Regime Entry Filter block (all
  `REGIME_*`), `RSI_OVERSOLD`/`RSI_OVERBOUGHT`/`RSI_DCA_MAX_POSITIONS`,
  `RSI_MTF_OVERSOLD`/`RSI_MTF_OVERBOUGHT`. ADDED `MACD_FAST`/`SLOW`/`SIGNAL` (12/26/9),
  `SLOPE_TIMEFRAMES` (H1,H4), `PEAK_LOOKBACK` (20), `PIVOT_WIDTH` (2),
  `REENTRY_COOLDOWN_SECONDS` (300), `PROFIT_PROTECT_MIN_USD` (0.0 — tune to costs). KEPT
  `CANDLE_TIMEFRAME`/`CANDLE_COUNT` (price feed), `RSI_LENGTH`/`RSI_MA_TYPE`/`RSI_CANDLE_COUNT`,
  and the RSI timeframe lists (app fetch / dashboard RSI display).
- **`indicator.py`** — REMOVED `calculate_sha_v3`, `calculate_adx`. ADDED `calculate_macd`
  (ta.macd-compatible) and `latest_pivot_slope` (latest-pivot + per-bar slope sign). KEPT
  `calculate_rsi`, `_ma`, `_tv_exp_ma*`.
- **`strategy.py`** — `calculate_signal` fully rewritten. Removed `_analyze`/`_analyze_trend`,
  the SHA entry, the regime param/annotation, the MTF-RSI entry filter, the DCA ladder, the H6
  close, the fixed +$unit target and the Fibo helpers. Added `_slope_sign`, `_slope_direction`
  and the slope entry + exit. New `slopes` / `entry_allowed` params; `analysis_data` now carries
  `slopes` / `slope_direction` / `entry_allowed` / `exit_reason`.
- **`app.py`** — removed SHA fetch/calc, `_compute_regime` + all regime wiring/logging, and the
  `BUY_MORE`/`SELL_MORE` execution handlers. Added H1/H4 MACD + slope computation inside the
  existing RSI fetch loop (no new MT5 call), the re-entry cooldown (`_last_close_time`,
  `entry_allowed`), and `exit_reason` in the close logs.
- **`dashboard.py`** — added `build_slope_panel` (the 4 slopes + decision / cooldown / exit
  reason) and switched the analysis panel from `build_sha_analysis_panel` (now dead) to it.

### Verification
- `python -m py_compile` on all files — OK.
- Unit tests (offline): MACD identity (hist = macd − signal, macd = EMA12 − EMA26); 6 pivot cases
  incl. latest-smaller-wins and monotonic → none; all 25 Step-6 entry cases incl. zeros; full
  exit matrix (profit-protect / hard stop / give-room HOLD / priority / mirror); the cooldown gate
  and the open-position guard.
- **STILL REQUIRED before live:** the ~3-month offline backtest — quantifies `PROFIT_PROTECT_MIN_USD`
  and the strategy's expectancy / drawdown under real spread + commission.

### Rollback
Isolated feature branches off the live v1.6.0 HEADs. To abandon: delete the `rsimacd_dev_*`
branches (the live `dev_*` branches are untouched). To revert a single phase: `git revert <sha>`
— teardown `5a122d1`/`46a817e`/`73bbf63`, rebuild `abca018`/`e715f01`/`67cc93b` (btcusd; mirror
SHAs on xauusd).

---

## [v1.6.0] — 2026-10-01 — Regime Entry Filter (ADX + ATR-spike fresh-entry gate; OFF + shadow by default)

**Baseline commit (state before this change):** `60540a3` — *feat: MTF entry-filter thresholds 30/70 -> 35/65 (CHANGELOG v1.5.0)*.
**Branch:** `dev_btcusd2_v2` (then propagated to all 20 fleet branches).
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py` (+ this `CHANGELOG.md`).
**Behaviour change (when enabled):** adds a **fresh-entry-only** regime gate that can turn a
would-be BUY/SELL into **DO_NOTHING** when the current M15 price regime is hostile to
mean-reversion — a strong trend (**ADX**) or a fast **1–2 candle ATR spike**. It answers the
owner's two failure cases directly: (1) the 2-bar BULL/BEAR spike that lagging SHA enters the
wrong way, and (2) the dull→explosive trend where SHA gives the opposite direction and the
martingale cannot recover. **This is the exact opposite of the rolled-back v1.1.0 HTF
protection**: v1.1.0 *handled* spikes by cutting **open** baskets early (which locked in losses);
this gate only *prevents* a **new** basket from opening and **never touches an open basket** —
once `buy_count>0` or `sell_count>0`, the DCA ladder (M1/M5/M15/H1/H4 adds), RSI adds, `+$unit`
profit close and H6 forced close all run **byte-identical to v1.5.0**.

**Ships OFF and safe.** `REGIME_FILTER_ENABLED = False` → **byte-identical to v1.5.0** (the gate
computes nothing and `strategy.py` receives an inert `{}`). Turning it on defaults to **shadow
mode** (`REGIME_FILTER_SHADOW = True`): it computes the verdict and **logs** every fresh entry it
*would* have blocked, but still trades identically — so the block rate can be measured on live
data before it is ever allowed to suppress a trade. No new MT5 fetches (ATR is an intermediate of
ADX on the M15 `source_df` already pulled for SHA) and fully **stateless** (recomputed each loop;
no latch to get stuck, unlike v1.1.0's `spike_latched`).

### Why
Per the owner (planning phase → approved): SHA is a lagging trend pair (TEMA10/DEMA20 on M15) and
RSI is a range tool, so neither can veto an entry taken *into* a fresh trend/spike. A **regime**
dimension is the missing filter. ADX (inverted: high ADX = trend = **don't** open a mean-reversion
basket) plus a stateless ATR-spike guard catches both the slow trend and the fast 2-bar move. Built
entry-only and OFF-by-default precisely because the previous market-protection attempt (v1.1.0) lost
money by acting on open baskets — the owner asked to *prevent* bad entries, not *handle* them, and to
"be prepared to rollback if this also fails."

### Change detail per file
- **`constants.py`** — new `Regime Entry Filter (FRESH-ENTRY gate ONLY)` block (L76–118), placed
  after `RSI_FINAL_CLOSE_TIMEFRAME` and before `Risk Management`. Master switches
  `REGIME_FILTER_ENABLED = False`, `REGIME_FILTER_SHADOW = True`. ADX gate: `REGIME_ADX_ENABLED`,
  `REGIME_ADX_PERIOD = 14`, `REGIME_ADX_MAX = 25.0`, `REGIME_ADX_USE_DI = False`. ATR-spike guard:
  `REGIME_ATR_ENABLED`, `REGIME_SPIKE_K1 = 2.2`, `REGIME_SPIKE_K2 = 3.2`, `REGIME_SPIKE_WINDOW = 2`,
  `REGIME_SPIKE_USE_DIR = False`. RSI-slope phase-2 (off): `REGIME_RSI_SLOPE_ENABLED = False`,
  `REGIME_RSI_SLOPE_TIMEFRAMES = [M1, M5]`, `REGIME_RSI_SLOPE_BARS = 3`, `REGIME_RSI_SLOPE_MIN = 8.0`.
  A comment documents the optional per-symbol `"regime"` override in `symbols.json`
  (`adx_max`/`spike_k1`/`spike_k2`/`spike_window`). No existing key changed.
- **`indicator.py`** — new `calculate_adx(self, high, low, close, length=14)` (L169), inserted
  between `calculate_rsi` and `_ma`. Wilder / TradingView `ta.adx`-compatible: TR, RMA-smoothed ATR,
  `+DI`/`−DI` from directional movement, `DX`, and RMA-smoothed `ADX`; returns a DataFrame
  `{TR, ATR, plus_DI, minus_DI, ADX}` (ATR falls out for free, so the spike guard needs no extra
  math). Divide-by-zero guarded via `replace(0, np.nan)` on ATR and the DI sum. Pure addition — no
  existing indicator touched. Verified on synthetic data: ADX∈0–100, low in range / ~99 in trend,
  `+DI>−DI` on an uptrend, NaN-safe warmup.
- **`strategy.py`** — `calculate_signal(...)` gains a trailing `regime=None` param (L168) + docstring
  note (L184–185: entry-only, ignored once a basket is open). In the **flat** branch only
  (`buy_count == 0 and sell_count == 0`), the SHA decision is split into `sha_wants_buy`/`sha_wants_sell`
  (L277–278) and gated by `_block_buy`/`_block_sell` read from the regime dict (L274–276), so a blocked
  side falls through to DO_NOTHING (L283–285). Every open-basket branch (DCA ladder, RSI adds, profit
  close, H6 close) is **unchanged**. Adds a `regime_out` telemetry block (L326–334:
  `would_fire_buy/sell`, `blocked_buy/sell`, `shadow_would_block_buy/sell`) surfaced as
  `analysis_data['regime']` (L350); the early-return path carries `'regime': regime or {}` (L241).
  `regime=None` ⇒ `{}` ⇒ nothing blocks (full backward compatibility).
- **`app.py`** — imports the 15 `REGIME_*` constants (L25–30). New `_compute_regime(...)` (L444–565):
  returns an inert dict when `REGIME_FILTER_ENABLED` is False; else calls `calculate_adx` on the M15
  `source_df` (**fail-open** — any exception returns no-block, L476), applies the ADX gate
  (`adx >= adx_max`, symmetric or `+DI/−DI` directional), the stateless ATR-spike guard (scans the last
  `spike_window` bars, 1-bar `TR ≥ K1·priorATR` and 2-bar sum `≥ K2·priorATR`, optional direction from
  the last candle body), and the optional RSI-slope check; emits `would_block_*` (measurement) and
  `block_*` (= active **and** would-block) separately. Per-symbol overrides read once
  (L600–604) with constant fallbacks. The MTF-RSI loop optionally captures an RSI slope for the phase-2
  check (L750–755). `_compute_regime` is called just before `calculate_signal` and passed in
  (L764–778). Shadow verdicts ride along in the `BUY_EXECUTED`/`SELL_EXECUTED` log detail
  (L857–862 / L902–907); when actually blocking, a `REGIME_BLOCK_BUY`/`REGIME_BLOCK_SELL` event is
  logged **throttled to once per M15 bar** (`_last_regime_log_bar`, L605 / L945–960).

### Behaviour matrix
| `REGIME_FILTER_ENABLED` | `REGIME_FILTER_SHADOW` | Effect |
|---|---|---|
| `False` (default) | — | **Byte-identical to v1.5.0.** Gate computes nothing; `strategy.py` gets `{}`. |
| `True` | `True` (default when on) | Trades identically, but **logs** every fresh entry it *would* block. Measurement / A-B. |
| `True` | `False` | **Actively blocks** hostile-regime fresh entries (symmetric unless `*_USE_DIR`). |

### Verification
- `python -m py_compile constants.py indicator.py strategy.py app.py` → OK.
- `calculate_adx` unit-checked on synthetic calm→trend→spike data: ADX range 0–100, ~29 in range vs
  ~99 in trend, `+DI≫−DI` on the uptrend, and an injected 1-bar candle trips `TR/priorATR = 5.0 ≥ K1`.
- Entry-only guarantee: the regime dict is consulted **only** inside the `buy_count == 0 and
  sell_count == 0` branch; no open-basket branch reads it.

### Rollback
- **Instant, no code change:** leave/confirm `REGIME_FILTER_ENABLED = False` in `constants.py` — the
  filter is completely inert (this is the shipped default).
- **De-risk while keeping it on:** set `REGIME_FILTER_SHADOW = True` (log-only, never blocks).
- **Full removal:** revert the four files to `60540a3` (`git checkout 60540a3 -- constants.py
  indicator.py strategy.py app.py`), or if committed as `<v1.6.0-sha>`: `git revert <v1.6.0-sha>`.
  Removal is clean because every change is additive and OFF-gated — nothing in the v1.5.0 path was
  modified.

---

## [v1.5.0] — 2026-09-29 — MTF entry-filter thresholds 30/70 → 35/65 (match core RSI)

**Baseline commit (state before this change):** `93ddd21` — *feat: core RSI thresholds 30/70 -> 35/65 (CHANGELOG v1.4.0)*.
**Branch:** `dev_btcusd2_v2` (then propagated to all 20 fleet branches).
**Files touched:** `constants.py` (+ this `CHANGELOG.md`).
**Behaviour change:** the multi-timeframe **entry filter** thresholds are tightened
inward from 30/70 to 35/65 — `RSI_MTF_OVERSOLD 30 → 35`, `RSI_MTF_OVERBOUGHT 70 → 65` —
so both RSI threshold pairs now use the same 35/65 band. This filter gates **fresh
entries** only (`strategy.py` ~L253–254): a new BUY is blocked when ANY of M1/M5/M15/M30
RSI ≤ 35, a new SELL when ANY ≥ 65. Widening the block band from 30/70 to 35/65 makes
the entry filter **stricter** — fresh baskets open less often, only when all four MTF
RSIs sit in the calmer 35–65 middle. The core DCA-ladder / H6-close thresholds
(`RSI_OVERSOLD`/`RSI_OVERBOUGHT`) remain 35/65 from v1.4.0 — unchanged here.

### Why
Per the owner: apply the same 35/65 range to the MTF entry filter so it matches the
core RSI thresholds (one consistent band across entry + ladder).

### Change detail per file
- **`constants.py`** — L56 `RSI_MTF_OVERSOLD = 30` → `35`; L57 `RSI_MTF_OVERBOUGHT = 70`
  → `65` (comments and alignment unchanged). Core `RSI_OVERSOLD`/`RSI_OVERBOUGHT` stay
  at 35/65 (v1.4.0); `RSI_MTF_TIMEFRAMES` (M1/M5/M15/M30) unchanged.
- No logic files changed: `strategy.py` reads these constants by name
  (`any(v <= RSI_MTF_OVERSOLD ...)`, `any(v >= RSI_MTF_OVERBOUGHT ...)`), so the new
  values take effect with no code edits.

### Rollback
Restore the two values in `constants.py` (`RSI_MTF_OVERSOLD = 30`,
`RSI_MTF_OVERBOUGHT = 70`), or if committed as `<v1.5.0-sha>`: `git revert <v1.5.0-sha>`.

---

## [v1.4.0] — 2026-09-29 — Core RSI thresholds 30/70 → 35/65

**Baseline commit (state before this change):** `9e311b7` — *revert: roll back HTF spike/drawdown protection (CHANGELOG v1.3.0)*.
**Branch:** `dev_btcusd2_v2` (then propagated to all 20 fleet branches).
**Files touched:** `constants.py` (+ this `CHANGELOG.md`).
**Behaviour change:** the **core** RSI oversold/overbought thresholds are tightened
inward from 30/70 to 35/65 — `RSI_OVERSOLD 30 → 35`, `RSI_OVERBOUGHT 70 → 65`. These
gate the DCA ladder adds (`BUY_MORE`/`SELL_MORE` at M1/M5/M15/H1/H4, `strategy.py`
~L277–304) and the H6 RSI forced-close, so a basket adds the next rung — and
force-closes when maxed — at a less-extreme RSI (sooner / more readily). The
multi-timeframe **entry filter** is deliberately left at 30/70 (`RSI_MTF_OVERSOLD`,
`RSI_MTF_OVERBOUGHT`), so fresh-entry gating is unchanged.

### Why
Per the owner: make the mean-reversion ladder react on shallower RSI extremes.
Entry-filter behaviour intentionally unchanged (confirmed scope: "Core RSI only").

### Change detail per file
- **`constants.py`** — L50 `RSI_OVERSOLD = 30` → `35`; L51 `RSI_OVERBOUGHT = 70` → `65`
  (comments and alignment unchanged). `RSI_MTF_OVERSOLD` (30) and `RSI_MTF_OVERBOUGHT`
  (70) left untouched.
- No logic files changed: `strategy.py` references these constants by name
  (`rsi_* <= RSI_OVERSOLD`, `rsi_* >= RSI_OVERBOUGHT`), so the new values take effect
  with no code edits.

### Rollback
Restore the two values in `constants.py` (`RSI_OVERSOLD = 30`, `RSI_OVERBOUGHT = 70`),
or if committed as `<v1.4.0-sha>`: `git revert <v1.4.0-sha>`.

---

## [v1.3.0] — 2026-09-29 — Rollback HTF Spike / Drawdown Protection (revert v1.1.0)

**Baseline commit (state before this change):** `32dc79a` — *feat: HTF spike/drawdown protection + remove gap_range & SHA convergence entry filters* (this commit bundled v1.1.0 + v1.2.0 together).
**Branch:** `dev_btcusd2_v2`
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py` (+ this `CHANGELOG.md`)
**Status:** working tree (uncommitted).
**Behaviour change:** the entire v1.1.0 Higher-Timeframe Spike / Drawdown Protection
module is **removed**. The DCA/martingale basket is back to pure RSI mean-reversion:
the ladder runs all tiers — fresh entry, then M1/M5/M15/H1/**H4** adds — with the
**H6** RSI forced-close as the only capitulation exit. There is again **no tail-risk
stop** (no catastrophe stop, no spike medium stop, no ladder cap, no ATR spike
detector). This is exactly the pre-v1.1.0 (`d0bc0ec` / v1.0.0) loss-side behaviour.
The v1.2.0 entry-filter change (gap_range + SHA convergence removed) and the
balance-stepped auto unit sizing (`step_up_balance`) are **kept, untouched**.

### Why
Per the owner, in live trading the spike/slippage protection cut baskets early at
the H1/H4 tiers and locked in losses the mean-reversion ladder would otherwise have
recovered — it caused net loss. Reverting restores the profitable "mean-reverse till
H4, H6 forced close" logic. The auto lot-increment must stay, so this is a surgical
removal of v1.1.0 only, **not** a full reset to `d0bc0ec`.

### Verification
- `git diff d0bc0ec` for the four code files shows **no** HTF/spike content — the
  spike-protection surface is byte-identical to the pre-v1.1.0 baseline `d0bc0ec`.
- The BUY/SELL DCA `if/elif` ladder is **byte-identical to `d0bc0ec`** (full H4 add,
  H6 forced close).
- The v1.2.0 gap_range/convergence removal is still present (diff vs `d0bc0ec` still
  shows those deletions).
- Auto unit stepping (`step_up_balance`) is still present in `app.py`.
- All four files parse (`ast.parse`); grep finds none of `HTF_`, `_detect_htf_spike`,
  `spike_latched`, `spike_src_df`, `ladder_capped`, `calculate_atr`, `htf_spike`, or
  `acct_balance` remaining.

### Change detail per file (all REMOVALS of the v1.1.0 additions)
- **`constants.py`** — removed the whole `Higher-Timeframe Spike / Drawdown
  Protection` block (all 10 `HTF_*` keys). `RISK_REWARD_RATIO` is now immediately
  followed by the `File System / Output` section.
- **`indicator.py`** — removed the `calculate_atr(self, high, low, close, length=14)`
  method. `calculate_rsi` is now immediately followed by `_ma`.
- **`strategy.py`** — removed the 6 `HTF_*` imports; removed the `balance`/`spike`
  params (and their docstring lines) from `calculate_signal`; restored both the BUY
  and SELL `if/elif` ladders to their pre-v1.1.0 form (dropped the `catastrophe_hit` /
  `spike_medium_hit` / `ladder_capped` computation and the `and not ladder_capped` H4
  guard); removed the `htf_spike` and `htf_protection_enabled` keys from
  `analysis_data`.
- **`app.py`** — removed the 5 `HTF_*` imports; removed the `_detect_htf_spike`
  method; removed the `spike_latched` declaration and its flat-check reset (the
  adjacent `step_up_balance` auto-increment block was left in place); removed the
  `spike_src_df` init + in-loop capture; removed the spike detect/latch block; removed
  the `acct_balance` local and the `balance=`/`spike=` args on the
  `calculate_signal(...)` call; removed the two `'htf_spike'` log keys.

### Rollback (re-enable HTF protection)
This reversal is a pure removal of the v1.1.0 additions, applied on top of `32dc79a`.

**If this rollback is NOT yet committed** (current state) — discard it to get HTF back:
```bash
git checkout -- constants.py indicator.py strategy.py app.py
```
This restores the four files to `32dc79a` (HTF present). To then keep HTF present but
OFF, set `HTF_PROTECTION_ENABLED = False` in `constants.py`.

**If this rollback WAS committed** (say as `<v1.3.0-sha>`):
```bash
git revert <v1.3.0-sha>                                    # inverse commit, or:
git checkout 32dc79a -- constants.py indicator.py strategy.py app.py
```

---

## [v1.2.0] — 2026-09-20 — Remove gap_range + SHA convergence entry filters

**Baseline:** applied on top of v1.1.0 (working tree; still on commit `d0bc0ec`).
**Files touched:** `symbols.json`, `constants.py`, `indicator.py`, `strategy.py`, `app.py`, `dashboard.py`.
**Behaviour change:** the fresh-entry condition is **loosened**. Before, a new
basket opened only when SHA signal+trend agreed **AND** the gap% was inside
`gap_range` **AND** the SHA gap was `DIVERGING` **AND** no MTF RSI was extreme.
Now it opens when SHA signal+trend agree **AND** no MTF RSI is extreme. Two of
the four entry gates were removed, so entries fire more often. The DCA ladder,
exits, and HTF protection (v1.1.0) are unchanged.

### Why
Per the owner, the `gap_range` band and the SHA converging/diverging detection
"weren't much use" as entry filters. Removing them also drops two indicator calls
per loop (`calculate_sha_gap`, `calculate_sha_convergence`), trimming a little
compute.

### Verification requested (point 3 — no code change)
Confirmed: **RSI overbought/oversold never OPENS a fresh position on any
timeframe.** Fresh entries live only in the `buy_count == 0 and sell_count == 0`
branch, which is SHA-driven and gated by `rsi_mtf_blocked`. RSI extremes only
(a) *block* a fresh entry (via `rsi_mtf_blocked` on M1/M5/M15/M30), or (b) trigger
`BUY_MORE`/`SELL_MORE` on an already-open basket (count ≥ 1). No RSI path creates
a new basket. (Left as-is by request.)

### Change detail per file (all REMOVALS)
- **`symbols.json`** — removed the `"gap_range": [0.0002, 0.0200]` key from the
  `BTCUSDm` entry (and the trailing comma on the line above it).
- **`constants.py`** — removed `DEFAULT_GAP_RANGE` (and its `# ─── SHA Gap ───`
  header) and the whole `# ─── SHA Convergence ───` block
  (`SHA_CONVERGENCE_LOOKBACK`, `SHA_CLOSE_THRESHOLD`, `SHA_CONVERGENCE_THRESHOLD`).
- **`indicator.py`** — removed the methods `calculate_sha_gap` and
  `calculate_sha_convergence`. (`calculate_atr` from v1.1.0 now sits between
  `calculate_rsi` and `_ma`.)
- **`strategy.py`** — removed `DEFAULT_GAP_RANGE` + the 3 `SHA_CONVERGENCE_*`
  imports; removed `gap_pct_series`, `gap_range`, `convergence` params from
  `calculate_signal` (and their docstring lines); removed the `current_gap_pct`
  block, the `gap_range` default, and the convergence-state block; removed the
  `gap_in_range` / `below_gap` / `entry_conv_ok` / `exit_conv_ok` locals; dropped
  `and gap_in_range and entry_conv_ok` from both entry conditions; removed
  `current_gap_pct` / `gap_range` / `convergence` from both `analysis_data` dicts.
  Also fixed a stale comment on the MTF-RSI entry filter: it now correctly states
  that the filter uses `RSI_MTF_TIMEFRAMES` (M1/M5/M15/M30) and that the DCA-ladder
  (H1/H4) and final forced-close (H6, not H1) timeframes are excluded. Comment-only,
  no behaviour change.
- **`app.py`** — removed `DEFAULT_GAP_RANGE` + the 3 `SHA_CONVERGENCE_*` imports;
  removed the `symbol_gap_range = ...` lookup; removed the `gap_pct_series` +
  `convergence` computation block; removed `gap_pct_series`, `gap_range=`,
  `convergence=` from the `calculate_signal(...)` call.
- **`dashboard.py`** — removed the `_build_gap_row` function, its call in the SHA
  panel (and the `row_divider` above it), and the `gap_pct` / `gap_range_val` /
  `convergence` extraction lines.

### Rollback
All v1.1.0 + v1.2.0 changes are still **uncommitted**, and the removed gap/
convergence code is byte-identical to what exists at baseline `d0bc0ec`.

**Restore just the gap_range + convergence code (keep v1.1.0 HTF protection):**
this is a manual re-add — the exact original blocks are recoverable from git:
```bash
git show d0bc0ec:symbols.json     # copy back the gap_range key
git show d0bc0ec:constants.py     # copy back DEFAULT_GAP_RANGE + SHA_CONVERGENCE_*
git show d0bc0ec:indicator.py     # copy back calculate_sha_gap + calculate_sha_convergence
git show d0bc0ec:strategy.py      # copy back the params/blocks/entry gates listed above
git show d0bc0ec:app.py           # copy back the imports/lookup/calc/call args
git show d0bc0ec:dashboard.py     # copy back _build_gap_row + its call + extractions
```
Then re-apply the v1.1.0 additions to any file you overwrite (see the v1.1.0
entry's markers), since `d0bc0ec` predates v1.1.0.

**Revert everything to before v1.1.0 AND v1.2.0 (clean slate):**
```bash
git checkout d0bc0ec -- symbols.json constants.py indicator.py strategy.py app.py dashboard.py
```

**Cleaner granular rollback going forward:** commit v1.1.0 and v1.2.0 as separate
commits/tags; then each can be reversed independently with `git revert <sha>`.

---

## [v1.1.0] — 2026-09-20 — Higher-Timeframe Spike / Drawdown Protection

**Baseline commit (state before this change):** `d0bc0ec` — *chore: remove dead config keys (fibo_power, trading_window.timezone)*
**Branch:** `dev_btcusd2_v2`
**Files touched:** `constants.py`, `indicator.py`, `strategy.py`, `app.py` (+ this `CHANGELOG.md`)
**Behaviour change:** additive and OFF-safe. When `HTF_PROTECTION_ENABLED = False`
the bot behaves byte-for-byte like `d0bc0ec`. When `True`, it adds tail-risk
protection at the H1/H4/H6 tiers only; the low tiers (M1/M5/M15) and normal
(non-spike) deep reversions are unchanged.

### Why
The DCA/martingale basket had no real stop loss (the broker `sl`/`tp` are a no-op
because `RISK_REWARD_RATIO = [1, 1]`). The only loss-side exit was the H6
capitulation, so a rare adverse **spike/slippage** at the 1H/4H tiers produced huge
drawdowns (observed ≈ **$1000 on a ≈$1200 balance = 83%**). This adds a surgical,
low-compute defense for exactly that case.

### What was added — 4 layered mechanisms (strict priority chain, never conflict)
Priority order evaluated in `strategy.calculate_signal` (BUY and SELL branches):

```
catastrophe stop  >  profit close  >  spike medium stop  >  ladder cap  >  normal ladder
```

1. **Spike detector** — ATR on the H1 candles *already fetched* for RSI (no extra
   fetch). Adverse move over last N H1 bars ≥ `K × H1-ATR`. Latched per basket.
2. **Ladder cap on spike** — blocks the big H4 add (#6, 0.13 lot); allows up to the
   H1 add (#5, 0.08 lot). "Reduce to 1H, go no further."
3. **Spike medium stop** — flatten when spiking AND count ≥ H1 tier AND loss ≥
   `HTF_MEDIUM_LOSS_PCT × balance`.
4. **Catastrophe stop (always on)** — flatten when loss ≥ `HTF_CATASTROPHE_LOSS_PCT × balance`.

### Change detail per file

#### `constants.py`
- **Added** one block immediately after `RISK_REWARD_RATIO = [1, 1]`, header
  `# ─── Higher-Timeframe Spike / Drawdown Protection ───`, defining these 10 keys
  (all prefixed `HTF_`):
  `HTF_PROTECTION_ENABLED` (True), `HTF_CATASTROPHE_LOSS_PCT` (0.45),
  `HTF_MEDIUM_LOSS_PCT` (0.20), `HTF_PROTECT_MIN_COUNT` (4),
  `HTF_LADDER_CAP_ON_SPIKE` (True), `HTF_LADDER_CAP_MAX_COUNT` (5),
  `HTF_SPIKE_TIMEFRAME` ('TIMEFRAME_H1'), `HTF_SPIKE_ATR_PERIOD` (14),
  `HTF_SPIKE_LOOKBACK_BARS` (3), `HTF_SPIKE_ATR_MULT` (1.8).
- Nothing else changed.

#### `indicator.py`
- **Added** one method `calculate_atr(self, high, low, close, length=14)` immediately
  before `calculate_sha_convergence`. Pure/vectorized, reuses the existing `_ma(..., 'RMA')`.
- Nothing else changed.

#### `strategy.py`
- **Import block:** added 6 names to `from constants import (...)`:
  `HTF_PROTECTION_ENABLED, HTF_CATASTROPHE_LOSS_PCT, HTF_MEDIUM_LOSS_PCT,
  HTF_PROTECT_MIN_COUNT, HTF_LADDER_CAP_ON_SPIKE, HTF_LADDER_CAP_MAX_COUNT`.
- **`calculate_signal` signature:** added two trailing kwargs `balance=None, spike=False`
  (backward compatible — defaults reproduce old behaviour).
- **Docstring:** added `balance:` and `spike:` argument descriptions.
- **BUY branch** (`elif buy_count > 0 and sell_count == 0:`): added the
  `catastrophe_hit` / `spike_medium_hit` / `ladder_capped` computation and reordered
  the `if/elif` chain; the H4 add now has `and not ladder_capped`.
- **SELL branch** (`elif buy_count == 0 and sell_count > 0:`): mirror of the BUY change.
- **`analysis_data` (main dict):** added keys `'htf_spike'` and `'htf_protection_enabled'`.

#### `app.py`
- **Import block:** added 5 names to `from constants import (...)`:
  `HTF_PROTECTION_ENABLED, HTF_SPIKE_TIMEFRAME, HTF_SPIKE_ATR_PERIOD,
  HTF_SPIKE_LOOKBACK_BARS, HTF_SPIKE_ATR_MULT`.
- **Added** method `_detect_htf_spike(self, ohlc_df, is_buy_basket)` immediately before
  `def process_symbol`.
- **`process_symbol`:**
  - added `spike_latched = False` just before `while True:`.
  - added `spike_latched = False` reset inside the flat check
    (`if _buy_ct == 0 and _sell_ct == 0:`).
  - added `spike_src_df = None` before the RSI `for tf_name` loop; inside the loop,
    `if tf_name == HTF_SPIKE_TIMEFRAME: spike_src_df = tf_df`.
  - added the spike detect + latch block after `current_rsi = ...`.
  - added `acct_balance = ...` and passed `balance=acct_balance, spike=spike_latched`
    into `self.strategy.calculate_signal(...)`.
  - added `'htf_spike': spike_latched` to the `CLOSE_BUY` and `CLOSE_SELL` log details.

### Configuration reference (all in `constants.py`)
| Key | Default | Meaning |
|---|---|---|
| `HTF_PROTECTION_ENABLED` | `True` | Master switch. `False` = pre-v1.1.0 behaviour. |
| `HTF_CATASTROPHE_LOSS_PCT` | `0.45` | Always-on hard stop, fraction of balance. |
| `HTF_MEDIUM_LOSS_PCT` | `0.20` | Spike stop, fraction of balance. |
| `HTF_PROTECT_MIN_COUNT` | `4` | Arm medium stop only at count ≥ this (4 = H1 tier). |
| `HTF_LADDER_CAP_ON_SPIKE` | `True` | Block DCA adds beyond the cap during a spike. |
| `HTF_LADDER_CAP_MAX_COUNT` | `5` | Block adds when count ≥ this during a spike. |
| `HTF_SPIKE_TIMEFRAME` | `'TIMEFRAME_H1'` | Timeframe used for ATR/spike detection. |
| `HTF_SPIKE_ATR_PERIOD` | `14` | ATR period. |
| `HTF_SPIKE_LOOKBACK_BARS` | `3` | Bars over which the adverse move is measured. |
| `HTF_SPIKE_ATR_MULT` | `1.8` | Adverse move ≥ this × ATR → spike. |

### How to find every line this version added
All additions carry unique markers — grep for them to see the full footprint:
```
HTF_            _detect_htf_spike     spike_latched     spike_src_df
htf_spike       acct_balance          calculate_atr     ladder_capped
```

### Rollback

**Quick disable (no code removal):** set `HTF_PROTECTION_ENABLED = False` in
`constants.py`. The bot immediately reverts to pre-v1.1.0 behaviour.

**Full rollback — if these changes are NOT yet committed** (current state):
```bash
git checkout -- app.py strategy.py indicator.py constants.py
rm -f CHANGELOG.md            # optional: this file was added by v1.1.0
```
This restores the four files exactly to baseline `d0bc0ec`.

**Full rollback — if v1.1.0 WAS committed** (say as commit `<v1.1.0-sha>`):
```bash
git revert <v1.1.0-sha>       # creates an inverse commit, or:
git checkout d0bc0ec -- app.py strategy.py indicator.py constants.py
```

**Manual rollback (no git)** — reverse the "Change detail per file" list above:
delete the `HTF_*` block in `constants.py`; delete `calculate_atr` in `indicator.py`;
in `strategy.py` remove the 6 HTF imports, remove `balance`/`spike` from the
signature, and restore the BUY/SELL `if/elif` ladders to their original form
(remove the `catastrophe_hit`/`spike_medium_hit`/`ladder_capped` lines and the
`and not ladder_capped` guard) and drop the two `analysis_data` keys; in `app.py`
remove the 5 HTF imports, the `_detect_htf_spike` method, and every line matching the
markers above.

---

## [v1.0.0] — baseline (commit `d0bc0ec`)
Pre-existing behaviour before this changelog was introduced: RSI multi-timeframe
mean-reversion DCA basket (Fibo lot ladder gated by M1/M5/M15/H1/H4 RSI, H6 forced
close, `+$unit` basket profit target, balance-stepped unit sizing). No tail-risk stop.
