# Changelog

All notable changes to the Alcadeias trading bot are recorded here, newest first.
Each version lists **exactly what changed per file** and a **Rollback** section so any
version can be reversed cleanly.

Versioning is feature-based (`vMAJOR.MINOR.PATCH`). Each entry names the git
**baseline commit** it was applied on top of, so you can always return to a known state.

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
