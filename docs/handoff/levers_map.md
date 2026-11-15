# Map: the backtest-only levers of the designs to port (V3-lite, Top 1, Top 2, Top 3 · XAUUSDm / BTCUSDm)

> **About this file.** This note was added on 16 Nov 2026, when the map was saved into the repo with `HANDOFF.md`.
> - **What it is.** The exact semantics of every backtest lever used by the designs that went to the demo accounts: the live default, what the kernel does with it, on which poll, on which bar and price, and how hard it is to port. It also gives the effective parameter sets, basket statistics over 8 years, and expected values for a port's tests. It was written for the demo port.
> - **When.** Written on 15 Nov 2026, about 17:42 IST, by an assistant session that worked read-only.
> - **What it describes.**
>   - The design rows in `backtest_results/improve/round4/top3_v4_{XAUUSDm,BTCUSDm}_designs.json`.
>   - `backtesting/engine/kernels.py` and `fast.py` at `0ae5794`. Both are unchanged since `9e4c71f` and still current at `bed551e` (16 Nov 2026), so the kernel line numbers hold.
>   - The live files of `origin/hedging_xauusd6` at `1ed2d6c` (13 Nov 2026).
> - **Out of date.** §0 says that no parity check exists for these levers and that `reference._apply_config` refuses or ignores them. That was true when written. Commit `c61c998` (15 Nov 2026, 18:51 IST) extended the reference engine. The demo branches' own `app.py` then matched the fast engine poll for poll on 8 windows with these levers (`backtest_results/demo_parity/DEMO_PARITY.md`; `HANDOFF.md` §5.8). For the old live root, `_apply_config` still silently accepts levers such as `trend_tf` that the live code lacks.
> - **Scratch files.** The scripts and outputs named in §0, §4 and §9 (`scratchpad/devclone`, `parity_final/*.json`, `levers_*.py`, `levers_effective.json`, `levers_table.md`, `levers_live/`) live in a temporary session folder, `/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/`, which is not part of the repo. They were all still there at about 03:50 IST on 16 Nov 2026 (the first version of this note said they were gone), but a reboot or a clean-up can delete them. Their results are written out in this map. The 7 hedging parity reports are also committed in the repo as `backtest_results/parity/*.json`.
> - **No credentials.** `mt5_credentials.json` was never opened or copied.

Scope: every key in `backtest_results/improve/round4/top3_v4_{XAUUSDm,BTCUSDm}_designs.json` for the four designs to port. For each key: the live default, what `backtesting/engine/kernels.py` does with it (line numbers of the working copy on `backtest_hedging`), when it is evaluated, on which prices and bars, and how hard it is to reproduce in the live MT5 loop. Live-file line numbers are those printed by `git show origin/hedging_xauusd6:<file> | cat -n`.

Everything here was read-only. The checks I ran are scripts in the scratchpad (listed in section 9). They read the repo and the local tick store, and their output was written only to the scratchpad. `git status` of the repo was unchanged before and after, and no file in the repo got a newer mtime.

During this work another process committed `0ae5794` ("research(balke): …", 17:37), which covers the previously untracked Balke files and `LOGIC_CHANGELOG.md`. That commit does not touch `backtesting/engine`, `config.py`, `robustness.py`, `final10.py`, `experiments.py` or `tests/test_lever_rules.py` (a diff of 0 lines), so every line number below still holds.

---

## 0. Provenance: what the designs are and what they were run against

* **The designs are overrides of `BacktestConfig.live(symbol)`.** `top3_v4.py` builds them as `designs = {**REFS, **picks(sym)}` and runs `robustness.timing_ensemble(E.live_config(sym), ..., overrides=list(designs.values()))`. `final10.py` reads them back through `own_designs()` (L94-97) and runs `E.live_config(symbol, start=a, end=z).replace(**row["overrides"])` (L546-548, L575).
* **`BacktestConfig.live()` reads the working copy's `constants.py` and `symbols.json`** (config.py L388-423). The runs used a scratchpad clone (`scratchpad/devclone`) whose `constants.py` is byte-identical to `origin/hedging_xauusd6:constants.py`.
  * `origin/hedging_btcusd6:constants.py` differs only by the missing newline at EOF.
  * For `BTCUSDm`, `_symbols_json()` falls back to the fleet window Monday 00:00 → Sunday 23:59 (config.py L444-447, L460-462). That window is what `origin/hedging_btcusd6:symbols.json` holds.
  * I built `BacktestConfig.live()` from the files of both deployment branches (copied with `git show`) and compared it with the working copy. The two differ in **nothing**, for either symbol.
* **The devclone's engine differs from the working copy** only by the regime series (`reg_t`/`reg_v`, `K_BLOCK_REGIME`), which is off by default. Results are identical for these designs.
* **Branches 6, 7 and 8 have the same code.** `git diff --stat origin/hedging_{xauusd,btcusd}6 origin/hedging_{…}{7,8}` lists only `mt5_credentials.json`. That file exists and has `demo` / `live` keys; I did not open it. xau6 and btc6 differ only in:
  * comments;
  * the `--symbol` in `start_job.bat`;
  * `symbols.json`: the symbol and the trading window (gold Mon 01:00 – Fri 22:00, BTC Mon 00:00 – Sun 23:59);
  * one fallback symbol name in `mt5_helper._get_server_time` (L720);
  * the EOF newline of `constants.py`.
* **How the designs were scored:**
  * Round 4: raw ticks (`mode="ticks"`) with `live_timing(seed)` (`robustness.py` L44-47): `poll_interval_ms=1000`, `poll_jitter_ms=200`, seeds 1..8, `open_order_delay_ms=100`. Fresh $2,000 per quarter.
  * Final ten, 8y / 5y / new windows: a per-second replay with one fixed timing (no jitter, `open_order_delay_ms=0`).
  * Final ten, 1y window: raw ticks × 8 timings.
* **No parity check exists for any of these levers.** `reference._apply_config` (reference.py L407-442) refuses `force_close_enabled=False`, `max_adds<5`, `stop_loss_usd_per_unit`, `target_usd_per_unit != 1`, non-live ladder tiers and non-Fibonacci multipliers. The 7 hedging parity windows (scratchpad `parity_final/*.json`) all use live logic. The levers are pinned only by `tests/test_lever_rules.py`, which replays them independently, for example `test_trend_filter_opens_on_one_side_of_the_trend_only` L1422, `test_a_losing_basket_is_followed_by_the_longer_cooldown` L1473, `test_macd_turn_ladder_adds_when_the_tier_s_macd_vote_turns_with_the_basket` L1540 and `test_volatility_units_fix_each_basket_s_distances_at_its_open` L1615.
  * Note also: `_apply_config` does **not** refuse `trend_tf`, `loss_cooldown_s`, `vol_tf`, `ladder_trigger` and similar levers. A reference run with only those set would silently ignore them.

---

## 1. One-screen summary

| key | live default (`BacktestConfig.live`) | kernel meaning | evaluated | prices / bars | port difficulty |
|---|---|---|---|---|---|
| `open_weights` | `{H1:1, M15:1}` (constants L91) | open score = Σ w·(rsi_sign+macd_sign), grey-filled | every live poll | forming bar at the current **bid** | easy (constants) |
| `entry_agree_s` | 2 (constants L69) | open only if fc_score (M15, raw signs) ≥ +s for buys / ≤ −s for sells | every flat poll | forming M15 bar, bid | easy, but **0 is not "off"** |
| `force_close_enabled` | True | False: the M15 score force-close never fires; fc_score is still computed for the agreement gate | every basket poll | – | easy |
| `trend_tf` (+`trend_mode`=1) | None | entry only if sign(MACD **signal line** of the last **closed** H1 bar) = trade side; 0 or NaN blocks both sides | at the entry decision; changes once per H1 bar | closed bar (`rates[-2]`), bid closes | easy, **do not reuse live `_sig` (forming bar)** |
| `loss_cooldown_s` | 0 (off) → 300 s after any close | after a basket with net P/L < 0, the next entry waits this long *instead of* 300 s, counted from the close decision | every flat poll | clock time | easy logic; **state is lost on restart** |
| `vol_tf`, `vol_len` | None, 24 | unit = EWMA(α=1/24) of \|Δclose\| of closed H1 bars, read at the last closed bar **when the basket opens**, kept for the basket's life | at open (and a "known" gate before every entry) | closed bars, bid closes | easy to compute; **must persist per basket** |
| `target_vol` / `stop_vol` | 0 / 0 | per-unit USD = mult × unit × contract × mtqty, **fixed at open**; close when basket profit > target×units or ≤ −stop×units | every live poll in a basket | floating P/L: bid for buys, ask for sells | easy; per-basket state |
| `target_usd_per_unit` / `stop_loss_usd_per_unit` | 1.0 / None | None = the USD target / stop is off; the vol versions above replace them at each open | – | – | – |
| `vol_cap_usd_per_unit` | 0 (none) | unit capped at cap ÷ (contract × mtqty) price units; caps target, stop and gap | at open | – | easy; **BTC: USD per unit, not price units** |
| `max_adds` | 99 → 5 live tiers | number of ladder adds = min(len(ladder_tfs), max_adds) | every basket poll | – | 0: delete the ladder; 1: rewrite it |
| `ladder_trigger` | `rsi_level` | `macd_turn`: the tier TF's MACD vote was not with the basket at some poll since the last fill, and is now | every basket poll (adds left) | forming M5 bar, bid | **medium: path-dependent arming state** |
| `ladder_tfs` | M1,M5,M15,H1,H4 | tier timeframe of add n = ladder_tfs[n-1] | – | – | only the first entry ("M5") is ever used |
| `ladder_gap_vol` | 0 | the add also needs price ≥ gap_vol × unit (price units, fixed at open) worse than the last fill | every basket poll | buy: last_fill − **ask**; sell: **bid** − last_fill | easy |
| `ladder_multipliers` | Fibonacci 1,2,3,5,8,13,… | add n size = mult[n] × units × mtqty | at the add | – | easy (live first add is 2 units, design is 1) |
| `entry_rsi_block_tfs` / `entry_rsi_block_mode` / `fc_rsi_tfs` | None / directional / None | RSI-extreme entry block / RSI force-close | – | – | **inert in all 8 designs** |

Design-by-design values are in section 4.

---

## 2. One poll of `run_kernel`: the order of the checks (kernels.py)

`run_kernel` (L594) runs `while T < end_ms:` (L783). One pass:

1. **L785-796.** Advance `ptr` to the latest quote with `t_ms ≤ T`. Nothing is read ahead except the *time* of the next quote.
2. **L800-828. Liveness.** If `T − whole_second(tick_t) > market_lookback_s` (180 s): this is a dead poll. Update the broker close-only window (L806-810) and the data-hole flag (L813-816, backtest-only, BTC), then jump to the next quote. **No exit and no stop check happens on dead polls** (live: `candle_is_fresh` False, app.py L543/L558).
3. **L834-835.** `mkt_closed`: the quote is the last one before a ≥30 min silence and more than 1 s old, so the broker refuses orders.
4. **L837-838.** `b = bid`, `a = bid + (ask − bid)·spread_mult + extra_spread`.
5. **L841-845.** Advance the forming-bar index `K[f]` of every timeframe in use, including `trend_f` and `vol_f`. A new bar becomes "forming" at the **first tick of the new bar**, so bar K−1 has then closed. MT5 behaves the same: `copy_rates_from_pos(...,0,n)` returns the forming bar as row −1 once a tick of it has arrived.
6. **L848-873.** Floating `profit` = Σ_positions `_round2((b − open)·lots·contract)` for buys or `_round2((open − a)·lots·contract)` for sells, then `_round2` again. This is MT5's `pos.profit` summed, like `get_buy_positions` L62/L72. MAE/MFE, equity and drawdown come from it.
7. **L875-883.** Used margin.
8. **L886-896.** `units = floor(balance / step_up) + 1`, capped at 10, **only while flat** (live app.py L503-511).
9. **L899-910.** Trading window on the latest tick's server time sets `brake`, which blocks fresh entries only.
10. **L913-943.** Indicators on the **forming bar** at the current bid: RSI, then the RSI pivot slope and the MACD-histogram pivot slope. The MACD pivot side comes from the forming bar's signal line `sg1` (L938-941).
11. **L946-1001.** Section scores: `open_score` (grey fill), `fc_score` (raw signs) and `agree_score = fc_score` (L1000-1001, because `agree_weights` is None).
12. **L1004-1026.** `entry_dir`, `entry_allowed` (cooldown / loss cooldown), `trend_now` (closed bar), regime.
13. **L1031-1044. Flat.** `signal = BUY/SELL` if `entry_dir ≠ 0 and entry_allowed`.
14. **L1045-1147. In a basket**, the exits in this order: **stop (L1074) → target (L1077) → trailing (L1080) → book (L1084) → force-close (L1087) → max-hold (L1090)**. If none fires, the ladder runs (L1093-1147): tier → trigger and arming → `add_ok` gate → gap / interval.
15. **L1149-1154.** Data-hole close override (backtest-only).
16. **L1181-1185.** Broker stop-out at margin level ≤ `stop_out_level` (0).
17. **L1187-1200.** Fill quote: `T + latency`, with latency 0 in all runs.
18. **L1202-1324. Entry execution.** No order is sent if any of these hold, checked in this order: brake (L1206) → data-hole quarantine (L1209) → allow_long/short (L1212) → regime (L1214) → **trend (L1217)** → spread cap (L1220) → **volatility unknown (L1223)** → daily loss limit (L1226) → **entry RSI block (L1229)** → hours (L1232) → entry confirm (L1235). The order is refused by the broker if the market is closed (L1240) or in close-only mode (L1244). Then the margin check (L1251). On a fill the open happens, and **the basket's distances are fixed** (L1266-1289).
19. **L1326-1376. Add execution.** Refusals: market closed, close-only, margin. Then the add, with `ladder_armed = False` and `last_fill_price` updated. Adds are **not** subject to the window brake, trend, cooldown or vol gate. Live does not brake adds either.
20. **L1378-1485. Close execution and bookkeeping.** `last_lost` (L1461) and `last_close = T` (L1479).
21. **L1517-1521.** `T += poll + extra_wait (+ jitter)`. `extra_wait` is `open_order_delay` after an open and `open_order_delay + add_order_delay` after an add (live: 0.1 s in `buy()`/`sell()` L510, plus `ORDER_COOLDOWN_SECONDS` = 1 s after BUY_MORE, app.py L751). There is no wait after a close (live has none either).

The entry gates are all ANDed, so their order inside steps 12 and 18 changes only the `polls_entry_blocked_*` counters, never a decision. For a port, the order that matters is the **basket** order: **stop first, then target, then (no force-close) the ladder**.

---

## 3. Lever by lever

### 3.1 `open_weights` (live `{H1:1, M15:1}`; the designs use `{H1:1}`, except BTC Top 3 which keeps `{H1:1, M15:1}`)

* config.py L122 (default), L400 (`live()` reads `OPEN_SCORE_WEIGHTS`). The kernel side is fast.py L267-269 (`w_or`/`w_om`, `need_slope`) and kernels.py L957-965:
  ```python
  if wr != 0.0 or wm != 0.0:
      rr = r
      mm = m
      if grey_open and wr != 0.0 and wm != 0.0:
          if rr == 0 and mm != 0:
              rr = mm
          elif mm == 0 and rr != 0:
              mm = rr
      open_score += wr * rr + wm * mm
  ```
* It is the same rule as live `Strategy._weighted_score(slopes, OPEN_SCORE_WEIGHTS, grey_fill=True)` (strategy.py L77-104, L234), which is parity-verified.
* **`{H1:1}` with `entry_s = 2`:**
  * A buy needs the H1 (RSI sign, MACD sign) to be (+,+), (+,0) or (0,+). The grey fill turns one clear sign into a full vote.
  * The ladder gate `add_ok = open_score > −ladder_s` (L1058/L1062) therefore blocks an add only when H1 is fully against the basket.
* **When:** every live poll, on the forming H1 bar at the current bid. The vote repaints within the hour.
  * This timing is what the gold result rests on. FINAL10.md §7: gold V3-lite made **$11,957 over 8 years with forming-bar votes and $2,300 with closed-bar votes** (`slope_on_closed_bars=True`).
* **Port:** `OPEN_SCORE_WEIGHTS = {'H1': 1}` (constants L91). `SLOPE_TIMEFRAMES` is derived automatically (L100-102).

### 3.2 `entry_agree_s` (live 2; V3-lite 2; all Tops 0)

* kernels.py L1004-1008:
  ```python
  entry_dir = 0
  if open_score >= entry_s and agree_score >= entry_agree_s:
      entry_dir = 1
  elif open_score <= -entry_s and agree_score <= -entry_agree_s:
      entry_dir = -1
  ```
  `agree_score = fc_score` (L1000-1001). `fc_score` is M15 `1·rsi_sign + 1·macd_sign` with **raw** signs (`fc_grey_fill=False`), range −2..+2.
* Live: `Strategy._entry_direction` (strategy.py L119-123) is the same.
* **0 is not "off".** With `entry_agree_s=0`, a buy needs fc_score ∈ {0, +1, +2}, so the M15 score must merely *not oppose* the trade. FINAL10.md §9 describes Top 1 as having "no M15 agreement needed", which is imprecise: M15 at −1 or −2 still blocks a buy.
* **Port:** `ENTRY_AGREE_S = 0`. Keep `FORCE_CLOSE_SCORE_WEIGHTS = {'M15': 1}` and keep computing the M15 slopes **even though the force-close is off**.

### 3.3 `force_close_enabled` (live True; all designs False)

* fast.py L345 sets `CI_FC_ENABLED`. kernels.py L1049 and L1055-1064:
  ```python
  rsi_fc = fc_enabled and fc_rsi_mask != 0
  ...
  fc_hit = fc_enabled and (fc_score <= -force_close_s)      # buy; sell mirror at L1060
  ...
  fc_slope = fc_hit
  fc_hit = fc_hit or rsi_fc
  ```
  With False, neither the M15 slope force-close nor the RSI force-close can fire.
* **Port:** in strategy.py L256/L258, guard `buy_fc`/`sell_fc` with a flag. **Do not drop the `fc_score` computation** (it is used by §3.2).

### 3.4 `trend_tf` = "H1" (+ `trend_mode` = 1, the default) — live None

* config.py L213-217. fast.py L315-316. kernels.py L1016-1022 (read) and L1217-1219 (applied):
  ```python
  trend_now = 0
  if trend_f >= 0 and K[trend_f] >= 1:
      sgt = SG[off[trend_f] + K[trend_f] - 1]
      if sgt > 0.0:
          trend_now = 1
      elif sgt < 0.0:
          trend_now = -1
  ...
  elif trend_f >= 0 and want_side * trend_now * trend_mode <= 0:
      counters[K_BLOCK_TREND] += 1
      ok = False
  ```
* **What is read:** `SG` = the MACD (12, 26, 9) **signal line**, an SMA-seeded TradingView EMA9 of (EMA12 − EMA26) (`indicator_arrays` L368-397, identical to live `Indicator.calculate_macd` L113-140). It is taken at the **last closed** bar `K−1` of H1, on bid closes. It is not the MACD line and not the histogram.
* **When:** at every poll that wants to open. The value changes once per H1 bar, at the first tick of the next bar. `trend_now = 0` (signal exactly 0 or NaN) blocks **both** sides. Adds and exits are not filtered.
* **Port:**
  * Use `macd_df['signal'].iloc[-2]` of the 500-bar H1 fetch that app.py already makes (L582-596).
  * **Do not reuse `_sig` (app.py L606, `iloc[-1]`)**. That is the forming bar's signal line, which the MACD vote uses for its pivot side (kernel L938 `sg1`).
  * config.py's docstring says the trend is "the same line the live MACD vote uses". That is the same line but a different bar.

### 3.5 `loss_cooldown_s` (live 0 = off, so 300 s after any close; V3-lite 43200, XAU Top 1 14400, XAU Top 2 43200, XAU Top 3 3600, BTC Tops 14400)

* config.py L219. fast.py L313-314. kernels.py:
  ```python
  # L1014
  entry_allowed = (T - last_close) >= (loss_cooldown if (last_lost and loss_cooldown > 0) else cooldown)
  # L1461 (basket bookkeeping on every close)
  last_lost = (realised - basket_comm) < 0.0
  # L1479
  last_close = T
  ```
* **"Lost"** means the basket's **realised** P/L net of commission is below zero. `realised` is Σ `_round2` per position at the close fill (bid for buys, ask for sells; L1388-1400). Commission is 0 on Standard. Swap is not modelled.
  * In these designs every exit is a target (profit > target > 0) or a stop (profit ≤ −stop < 0), so "lost" ⇔ "closed by the stop". The exceptions are the BTC data-hole closes (backtest-only).
* **Timing:**
  * The pause starts at `T` of the poll that *decided* the close, not at the fill.
  * It replaces the 300 s cooldown; it is not added to it.
  * It is wall-clock time, so it runs through weekends and daily breaks.
  * Only the last basket counts.
  * At the start of a run there is no pause (`last_close = -(1<<60)`, L737).
  * Verified on the 8-year trades: the shortest wait after a loss equals the pause exactly (12.00 h, 4.00 h, 1.00 h), and after a win it is 5.0 min.
* **Live today:** `entry_allowed = (time.time() - _last_close_time) >= REENTRY_COOLDOWN_SECONDS` (app.py L646). `_last_close_time = time.time()` is set after `close_by_type` (L755/L795).
  * `_last_close_time` is a **local variable initialised to 0.0** (L477), so a restart ends any pause.
  * The port needs `_last_close_lost` as well, and should persist both or rebuild them from `history_deals_get`.
  * Live also sets `_last_close_time` when the close order fails. The kernel does not move `last_close` on a refused close (L1382-1385).

### 3.6 `vol_tf` = "H1", `vol_len` = 24: the volatility unit (live: off)

* Computed once per timeframe over warm-up plus window bars: fast.py L93 `("VOL", K.vol_array(C, int(cfg.vol_len)))`. `C` holds the **bid closes** (in-window bars `_window_bars` L103-108 return `bid[last]`; warm-up bars come from M1 bid bars, store.py L1-22).
* kernels.py L304-321:
  ```python
  @njit(cache=True)
  def vol_array(C, n):
      out = np.zeros(C.shape[0])
      if C.shape[0] < 2:
          return out
      v = abs(C[1] - C[0])
      out[1] = v
      for k in range(2, C.shape[0]):
          v += (abs(C[k] - C[k - 1]) - v) / n
          out[k] = v
      # not known until n bar-to-bar changes have been averaged (0 = unknown: no basket is opened on it)
      out[:min(int(n), C.shape[0])] = 0.0
      return out
  ```
* **The formula:** `v_k = v_{k−1} + (|C_k − C_{k−1}| − v_{k−1}) / 24`, seeded with the first absolute change. This equals pandas `abs(close.diff()).ewm(alpha=1/24, adjust=False).mean()`.
  * It is **not** an ATR (no high/low).
  * It is **not** a 24-bar simple mean. On the latest gold bar the simple mean is 10.54 against the EWMA's 8.82; on BTC, 167.3 against 189.0.
  * One "bar-to-bar change" spans a weekend or daily break when there is one, as MT5's own bars do.
* **What a decision reads:** `VOL[off[vol_f] + K[vol_f] − 1]`, the value at the **last closed** H1 bar.
  * At the basket's open it is fixed for the basket's life (L1275, see §3.7).
  * Before every entry, a gate blocks the entry while it is still 0 during warm-up (L1223-1225). Live never sees this gate, because 500 bars are always known.
* **Fetch length:** the EWMA restarted on only the last 500 H1 bars matches the full-history value to 3e-10 (gold) and 1e-10 (BTC); 300 bars to 3e-7. With 100 bars it is off by 0.4 % (gold) to 12 % (BTC). Live's `RSI_CANDLE_COUNT = 500` (constants L31) is enough. `adjust=True` over 500 bars also matches to 2e-10.
* **Port:** `v = ewm(|diff(close[:-1])|, alpha=1/24, adjust=False)[-1]` on the H1 500-bar fetch. **Exclude the forming bar** (row −1).

  Typical values from the local store (H1 bars, per year):

  | year | gold price | gold unit median (p90 / max), $ per 0.01 lot | BTC price | BTC unit median (p90 / max), BTC $ | BTC unit, $ per 0.01 lot |
  |---|---|---|---|---|---|
  | 2021 | 1,794 | 2.04 (2.94 / 5.9) | 47,862 | 266 (415 / 917) | 2.66 |
  | 2023 | 1,945 | 2.02 (2.94 / 6.1) | 27,733 | 73 (129 / 253) | 0.73 |
  | 2024 | 2,381 | 2.85 (4.00 / 7.5) | 64,204 | 220 (407 / 765) | 2.20 |
  | 2025 | 3,345 | 4.89 (9.55 / 19.7) | 103,527 | 286 (456 / 971) | 2.87 |
  | 2026 | 4,444 | 9.40 (15.63 / **54.4**) | 74,652 | 196 (319 / 784) | 1.96 |

### 3.7 `target_vol` / `stop_vol` with `target_usd_per_unit = None` / `stop_loss_usd_per_unit = None` (live: target $1 × unit, no stop)

* fast.py L346-347: `CI_TARGET_ON = target_usd_per_unit is not None` and `CI_SL_ON = stop_loss_usd_per_unit is not None`. Both are 0 here. L405-406 copy the multiples.
* At the open, kernels.py L1266-1289:
  ```python
  # this basket's distances: the configured dollars / price, or multiples of the volatility now
  b_target = target
  b_target_on = target_on
  b_sl = sl_usd
  b_sl_on = sl_on
  b_gap = ladder_gap
  b_trail_start = trail_start
  b_trail_gap = trail_gap
  if vol_f >= 0:
      v_now = VOL[off[vol_f] + K[vol_f] - 1]
      if vol_cap > 0.0 and v_now * usd_per_price > vol_cap:
          v_now = vol_cap / usd_per_price
      if target_vol > 0.0:
          b_target = target_vol * v_now * usd_per_price
          b_target_on = True
      if stop_vol > 0.0:
          b_sl = stop_vol * v_now * usd_per_price
          b_sl_on = True
      if gap_vol > 0.0:
          b_gap = gap_vol * v_now
      ...
  ```
  `usd_per_price = contract * mtqty` (L725): gold 100 × 0.01 = **1.0**, BTC 1 × 0.01 = **0.01** USD per 0.01 lot per 1.0 of price.
* On every live poll in a basket, kernels.py L1073-1079:
  ```python
  tgt = b_target * (basket_lot_units if target_per_lot else basket_units)
  if b_sl_on and profit <= -b_sl * basket_units:
      signal = 3 if side > 0 else 4
      reason = R_STOPLOSS
  elif b_target_on and profit > tgt:
      signal = 3 if side > 0 else 4
      reason = R_TARGET
  ```
* **Semantics:**
  * The levels are **USD for the whole basket**: per-unit USD × `basket_units`, the unit at the open (`target_per_lot=False`). They are **fixed at the open** and never updated: not by later bars, not by a change in volatility, not by an add.
  * They are compared with the basket's floating profit as MT5 reports it: bid for buys, ask for sells, each position rounded to cents.
  * The stop is `≤`; the target is strict `>`. The stop is tested first. Both cannot hold at once.
  * The `None` USD settings matter only because, without `vol_tf`, there would be no target at all. With `target_vol > 0`, `b_target_on` is forced True at every open.
* **As a price:**
  * One leg (`lots = units·mtqty`): profit = (bid − fill)·units·usd_per_price for a buy, so the **target is `bid > fill + target_vol·v`** and the **stop is `bid ≤ fill − stop_vol·v`**. Sells are the mirror on the ask. The fill already paid the spread.
  * Two equal legs (XAU Top 1 / Top 3 after their add): the same USD is spread over twice the lots, so the target is `bid > avg + target_vol·v/2` and the stop is `bid ≤ avg − stop_vol·v/2`. LOGIC_CHANGELOG.md has the worked $20 example.
  * Engine check (§5): XAU Top 3, sell at 4603.89 with an add at 4655.27 and a capped unit of 12. The stop is $96 for the basket and fired at −$96.20.
* **Live today:** `if buy_profit > close_threshold:` (strategy.py L271) with `close_threshold=units` (app.py L650). There is no stop.
  * `_build_request` (mt5_helper.py L471-481) sends broker SL/TP of `ask·(1 ∓ 1)`: SL 0 for buys and 2×ask for sells. In effect there is no broker-side stop.
* **Port:**
  1. At the open, compute and store `tgt_usd_unit` and `sl_usd_unit` (and `gap_px`).
  2. Each poll: `if profit <= -sl*units: close` then `elif profit > tgt*units: close`.
  3. Here `units` must be the **basket's** unit. After a restart, live `units` restarts at 1 (app.py L468) and is not re-derived while positions are open.

### 3.8 `vol_cap_usd_per_unit` (live 0 = none; XAU Top 2 and Top 3 = 12; BTC Top 1 = 20; BTC Top 2 = 12)

* config.py L239, with the validation that it needs `vol_tf` (L298-299). fast.py L413. The kernel applies it at L1276-1277 (above) at the open only. It caps the unit **before** the target, stop, gap and trail are derived from it.
* **The units are USD per 0.01 lot.** The price-unit ceiling is `cap / usd_per_price`:
  * gold: $12 means a $12 gold move per H1 bar;
  * BTC: $12 means a **$1,200 BTC move**, and $20 means $2,000.
* **How often it binds:**
  * **Gold:** never before 2025; on 3.9 % of H1 bars in 2025 and 20.8 % in 2026; 11.0 % over the last 2 years. In Feb 2026 every Top 3 basket opened with a capped unit (raw 13.7–52.4), giving a $120 target and $96 stop per unit.
  * **BTC:** **never**. The largest H1 unit 2018-2026 is $971, i.e. $9.71 per unit, below $12. The BTC caps are inert in all history.
* **Trap:** reading the BTC cap as price units would make BTC targets about 100× too small.

### 3.9 `max_adds` (live 99 → 5 tiers; V3-lite 0; XAU Top 1 and Top 3 1; XAU Top 2 0; all BTC 0)

* config.py L209 and L331-333: `n_ladder_adds = min(len(ladder_tfs), max_adds) if ladder_enabled else 0`. fast.py L287 gives `n_tiers`. Kernel L1094-1096 and L1146-1147:
  ```python
  cnt = n_pos
  if cnt <= n_tiers:
      tf_i = ladder_tf[cnt - 1]
      ...
  else:
      counters[K_LADDER_EXHAUSTED] += 1
  ```
* With 0 there are no adds at all: every basket has one leg (8-year trades: legs {1: N}).
* **Port:**
  * For XAU V3-lite, XAU Top 2 and all four BTC designs, **delete the ladder** (strategy.py L277-288 / L299-310).
  * For XAU Top 1 / Top 3, replace it with one add (§3.10). Over 8 years 672 of 1,240 (Top 1) and 730 of 1,345 (Top 3) gold baskets took it.

### 3.10 The add of XAU Top 1 / Top 3: `ladder_trigger="macd_turn"`, `ladder_tfs[0]="M5"`, `ladder_gap_vol=1`, `ladder_multipliers=[1,1,…]`

These keys also appear, inert, in the other Tops (max_adds 0).

* **Trigger, kernel L1113-1117:**
  ```python
  elif ladder_mode == 2:
      # the tier timeframe's MACD vote was not with the basket since the last fill and now is
      if sgn_m[tf_i] * side <= 0:
          ladder_armed = True
      hit = ladder_armed and sgn_m[tf_i] * side > 0
  ```
  * `sgn_m[M5]` is the M5 **MACD vote**: the latest-pivot slope sign of the MACD histogram on the **forming** M5 bar at the current bid, with the pivot side picked by the forming bar's signal line (L938-941). It is the same value live computes for slope timeframes (app.py L606-611).
  * fast.py L296-297 forces `need_slope[M5] = 1`, so M5's votes are computed but carry no weight in any score.
  * **Port:** add `TIMEFRAME_M5` to the slope list without adding it to any weight dict.
* **Arming state:** `ladder_armed` is cleared at the open (L1265) and after each add (L1348). It is set on *any* poll since then where the vote is against the basket or grey (≤ 0).
  * It is evaluated only on polls that reach the ladder branch, i.e. polls where no exit fired.
  * Once armed it stays armed, so the add fires on the **first later poll** on which all of these hold: vote with the basket, `add_ok`, and gap met.
* **Gate** (L1058/L1062, L1120-1122): `add_ok = open_score > −ladder_s` for a buy (`< +ladder_s` for a sell) with `ladder_s=2`, so H1 must not be fully against the basket.
* **Gap**, kernel L1132-1136 (`b_gap` fixed at the open, L1284-1285):
  ```python
  elif b_gap > 0.0:
      if side > 0:
          gap_ok = (last_fill_price - a) >= b_gap
      else:
          gap_ok = (b - last_fill_price) >= b_gap
  ```
  * A buy adds only when the **ask** is at least one unit below the entry fill (itself an ask); a sell only when the **bid** is at least one unit above.
  * Top 1's unit is uncapped. Top 3's unit is capped at $12, so its gap is at most $12.
  * `ladder_min_interval_s = 0`, so there is no time spacing.
* **Size**, kernel L1327: `lots = _round2(ladder_mult[n_pos] * basket_units * mtqty)` with `ladder_mult[1] = 1.0`, i.e. **the same size as the entry**. fast.py L298 pads the list with its last value.
  * Live `_get_next_fibo_volume` (strategy.py L39-65, called at app.py L739/L779) would make the first add **2 units**.
* **After the add:**
  * The basket's target and stop stay the same USD amount (§3.7).
  * `extra_wait = open_order_delay + add_order_delay` (L1351). Live sleeps 0.1 s in `buy()` plus 1 s at app.py L751.
* **What the add skips:** adds pass no brake, trend, cooldown or vol gate (L1326-1339), as in live.

### 3.11 `entry_rsi_block_tfs` / `entry_rsi_block_mode` / `fc_rsi_tfs`: inert in all eight designs

* The Tops carry `entry_rsi_block_tfs: null, entry_rsi_block_mode: "any"`, and their labels say `fc_rsi_tfs=nan`. They are used only by the reference row "Owner's rules + H1 trend + 4 h pause", which is not to be ported.
* fast.py L280-286 and L319-321 build bit masks, and `None` gives mask 0.
* **When set, the kernel does this:**
  * Entry block, `_rsi_blocks` L290-301, applied at L1229-1231:
    ```python
    if any_extreme:
        if r >= rsi_ob or r <= rsi_os:
            return True
    elif (want_side > 0 and r >= rsi_ob) or (want_side < 0 and r <= rsi_os):
        return True
    ```
    It reads the forming-bar RSI at the levels 35 / 65 (`rsi_oversold`/`rsi_overbought`), not the 40 / 60 pivot bands.
  * RSI force-close (L1049-1054): fires when **all** listed RSIs are beyond the level against the basket, and only if `force_close_enabled`. It is therefore doubly inert here.
* **Port:** nothing to do.

---

## 4. The effective parameter sets (live defaults + overrides)

Generated from `BacktestConfig.live(sym, repo_root=<copy of the deployment branch's constants.py + symbols.json>).replace(**design)` (scratchpad `levers_effective.json` / `levers_table.md`). "inert" means the key is present but cannot act because there are no adds. `ladder_tfs` and `ladder_multipliers` are shown as the part a design can use.

| key | XAU Live | XAU V3-lite | XAU Top 1 | XAU Top 2 | XAU Top 3 | BTC Live | BTC V3-lite | BTC Top 1 | BTC Top 2 | BTC Top 3 |
|---|---|---|---|---|---|---|---|---|---|---|
| `open_weights` | {H1:1, M15:1} | {H1:1} | {H1:1} | {H1:1} | {H1:1} | {H1:1, M15:1} | {H1:1} | {H1:1} | {H1:1} | {H1:1, M15:1} |
| `fc_weights` | {M15:1} | {M15:1} | {M15:1} | {M15:1} | {M15:1} | {M15:1} | {M15:1} | {M15:1} | {M15:1} | {M15:1} |
| `agree_weights` | None | None | None | None | None | None | None | None | None | None |
| `open_grey_fill` / `fc_grey_fill` | True / False | same | same | same | same | True / False | same | same | same | same |
| `entry_s` | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| `entry_agree_s` | 2 | 2 | **0** | **0** | **0** | 2 | 2 | **0** | **0** | **0** |
| `ladder_s` | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| `force_close_s` | 1 | 1 (off) | 1 (off) | 1 (off) | 1 (off) | 1 | 1 (off) | 1 (off) | 1 (off) | 1 (off) |
| `force_close_enabled` | True | **False** | **False** | **False** | **False** | True | **False** | **False** | **False** | **False** |
| `target_usd_per_unit` | 1 | None | None | None | None | 1 | None | None | None | None |
| `stop_loss_usd_per_unit` | None | None | None | None | None | None | None | None | None | None |
| `vol_tf` / `vol_len` | None / 24 | H1 / 24 | H1 / 24 | H1 / 24 | H1 / 24 | None / 24 | H1 / 24 | H1 / 24 | H1 / 24 | H1 / 24 |
| `target_vol` | 0 | **8** | **10** | **8** | **10** | 0 | **8** | **8** | **10** | **8** |
| `stop_vol` | 0 | **8** | **8** | **4** | **8** | 0 | **8** | **8** | **8** | **8** |
| `vol_cap_usd_per_unit` | 0 | 0 | 0 | **12** | **12** | 0 | 0 | 20 (never binds) | 12 (never binds) | 0 |
| `trend_tf` / `trend_mode` | None / 1 | **H1** / 1 | **H1** / 1 | **H1** / 1 | **H1** / 1 | None / 1 | **H1** / 1 | **H1** / 1 | **H1** / 1 | **H1** / 1 |
| `reentry_cooldown_s` | 300 | 300 | 300 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| `loss_cooldown_s` | 0 | **43200** | **14400** | **43200** | **3600** | 0 | **43200** | **14400** | **14400** | **14400** |
| `max_adds` → `n_ladder_adds` | 99 → 5 | 0 → 0 | **1 → 1** | 0 → 0 | **1 → 1** | 99 → 5 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
| `ladder_trigger` | rsi_level | (inert) | **macd_turn** | (inert) | **macd_turn** | rsi_level | (inert) | (inert) | (inert) | (inert) |
| `ladder_tfs` (used) | M1, M5, M15, H1, H4 | – | **M5** | – | **M5** | M1, M5, M15, H1, H4 | – | – | – | – |
| `ladder_multipliers` (add sizes) | 2, 3, 5, 8, 13 | – | **1** | – | **1** | 2, 3, 5, 8, 13 | – | – | – | – |
| `ladder_gap_vol` | 0 | (inert) | **1** | (inert) | **1** | 0 | (inert) | (inert) | (inert) | (inert) |
| `ladder_min_gap` / `ladder_min_interval_s` | 0 / 0 | – | 0 / 0 | – | 0 / 0 | 0 / 0 | – | – | – | – |
| `rsi_oversold` / `rsi_overbought` | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 | 35 / 65 |
| `entry_rsi_block_tfs` / mode | None / directional | None / directional | None / any | None / any | None / any | None / directional | None / directional | None / any | None / any | None / any |
| `fc_rsi_tfs` | None | None | None | None | None | None | None | None | None | None |
| trading window (min of week) | 60 → 7080 (Mon 01:00 – Fri 22:00) | same | same | same | same | 0 → 10079 (Mon 00:00 – Sun 23:59) | same | same | same | same |
| timeframes read | M1, M5, M15, H1, H4 | M15, H1 | M5, M15, H1 | M15, H1 | M5, M15, H1 | M1, M5, M15, H1, H4 | M15, H1 | M15, H1 | M15, H1 | M15, H1 |

**The same in every design and in live:**
* Account and sizing: `initial_balance` 2000; `leverage` 2000 (BTC capped at 400); `stop_out_level` 0; `mtqty` 0.01; `step_up_balance` 2500; `unit_max_limit` 10; `fixed_units` 0.
* Indicators and pivots: `rsi_length` 14; MACD 12 / 26 / 9; `peak_lookback` 20; `pivot_width` 2; `rsi_peak_ob/os` 60 / 40.
* Variant: `book_enabled` False (hedging); `ladder_enabled` True.
* Bar reading: `slope_on_closed_bars` False and `ladder_on_closed_bars` False (votes on the forming bar).
* All other experimental levers off: `min_hold_s`, `fc_confirm_s`, `entry_confirm_s`, `max_hold_s`, trailing, `target_per_lot`, `entry_hours_utc`, `entry_max_spread`, `daily_loss_limit_usd_per_unit`, `ladder_rsi_exit`; `allow_long/short` True.
* Timing: `poll_interval_ms` 1000; `add_order_delay_ms` 1000; `open_order_delay_ms` 0 (100 in the ensembles); `latency_ms` 0; `poll_jitter_ms` 0 (200 in the ensembles); `market_lookback_s` 180; close-only 90 s / 210 s.
* Costs: `spread_mult` 1, `slippage` 0, `commission` 0.
* Data holes: `data_hole_s` None, i.e. gold off and BTC 3 h, with a 547,200 s (6.3-day) quarantine.

**What each design is, in plain terms.** The per-0.01-lot amounts use the 2025 / 2026 median H1 unit: gold 4.89 / 9.40, BTC 286 / 196 BTC-$.

| design | entry | stop / target per 0.01 lot (2025 → 2026 median unit) | adds | pause after a loss |
|---|---|---|---|---|
| XAU V3-lite | H1 votes ≥ 2, M15 raw score = ±2 (both signs on side), H1 trend | 8u / 8u: $39 / $39 → $75 / $75; **uncapped**: $408 at the Feb 2026 unit of 51 | none | 12 h |
| XAU Top 1 | H1 votes ≥ 2, M15 not against, H1 trend | 8u / 10u: $39 / $49 → $75 / $94; uncapped | 1 × 1 unit on an M5 MACD turn, ≥ 1u adverse | 4 h |
| XAU Top 2 | as Top 1 | 4u / 8u with u ≤ $12: $20 / $39 → $38 / $75; at most $48 / $96 | none | 12 h |
| XAU Top 3 | as Top 1 | 8u / 10u with u ≤ $12: $39 / $49 → $75 / $94; at most $96 / $120 | 1 × 1 unit on an M5 MACD turn, ≥ min(u, 12) adverse | 1 h |
| BTC V3-lite | as XAU V3-lite | 8u / 8u: $22.9 / $22.9 → $15.7 / $15.7 | none | 12 h |
| BTC Top 1 | H1 votes ≥ 2, M15 not against, H1 trend | 8u / 8u (the cap of $20 never binds) | none | 4 h |
| BTC Top 2 | as BTC Top 1 | 8u / 10u: $22.9 / $28.7 → $15.7 / $19.6 (the cap of $12 never binds) | none | 4 h |
| BTC Top 3 | H1 + M15 votes ≥ 2 (the live opening rule), M15 not against, H1 trend | 8u / 8u | none | 4 h |

**Baskets in the 8-year run** (final10 `trades_*_ticks.csv.gz`, window 8y, per-second replay):

| design | baskets | target / stop / data-hole | 2-leg baskets | hold h: median / p90 / max | win rate |
|---|---|---|---|---|---|
| XAU V3-lite | 809 | 454 / 355 / 0 | 0 | 24.8 / 121.6 / 503 | 0.56 |
| XAU Top 1 | 1240 | 599 / 641 / 0 | 672 | 22.3 / 93.3 / 238 | 0.48 |
| XAU Top 2 | 1316 | 479 / 837 / 0 | 0 | 11.9 / 63.9 / 265 | 0.36 |
| XAU Top 3 | 1345 | 639 / 706 / 0 | 730 | 22.5 / 93.4 / 238 | 0.48 |
| BTC V3-lite | 1154 | 603 / 545 / **6** | 0 | 20.8 / 82.0 / 739 | 0.53 |
| BTC Top 1 | 1372 | 715 / 651 / **6** | 0 | 20.8 / 88.0 / 599 | 0.52 |
| BTC Top 2 | 1110 | 535 / 569 / **6** | 0 | 24.2 / 116.2 / 599 | 0.48 |
| BTC Top 3 | 1552 | 822 / 723 / **7** | 0 | 20.7 / 89.7 / 711 | 0.53 |

No basket ever closed for any reason other than target, stop or data hole, as expected with force-close and the ladder RSI off.

---

## 5. Worked example from the engine (expected values for a port's parity test)

`levers_worked_example.py` runs the fast engine (per-second rows, February 2026) and recomputes each basket's unit independently. It asserts that every target close is above the implied level, every stop close is at or below it, and every add is at least one gap from the entry. All assertions passed.

XAUUSDm Top 3:

| open (UTC) | side | entry | unit at open | capped | target $ | stop $ | gap | legs | add at | add distance | reason | P/L seen $ | hold h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-02-02 01:10:20 | SELL | 4627.721 | 50.967 | yes | 120.00 | 96.00 | 12.000 | 1 | – | – | stop_loss | −97.64 | 0.4 |
| 2026-02-02 04:05:14 | SELL | 4603.890 | 49.726 | yes | 120.00 | 96.00 | 12.000 | 2 | 4655.265 | 51.375 | stop_loss | −96.20 | 0.2 |
| 2026-02-05 03:15:01 | BUY | 4845.564 | 30.175 | yes | 120.00 | 96.00 | 12.000 | 2 | 4833.560 | 12.004 | target | 122.05 | 13.6 |
| 2026-02-17 00:52:16 | SELL | 4957.284 | 9.931 | no | 99.31 | 79.45 | 9.931 | 2 | 4967.269 | 9.985 | target | 99.44 | 4.4 |

* XAUUSDm V3-lite, same month: 2026-02-02 01:10:23 SELL 4623.376, unit 50.967 **uncapped**, stop $407.74, P/L seen −$408.79. This is one stop worth 20 % of a $2,000 account.
* BTCUSDm Top 2: 2026-02-06 19:39:35 SELL 70270.95, unit 725.7, target $72.57, stop $58.06 (the cap would start at a unit of 1,200).
* Shortest pause after a loss: XAU Top 3 1.45 h (pause 1 h), V3-lite 26.4 h (pause 12 h), BTC Top 2 4.00 h (pause 4 h). After a win: 5.0 min in all three.

---

## 6. Where each lever lands in the live code (hedging_*6 files)

| lever | live touch point |
|---|---|
| `open_weights` | constants.py L91 `OPEN_SCORE_WEIGHTS` (`SLOPE_TIMEFRAMES` follows, L100-102) |
| `entry_agree_s` | constants.py L69 `ENTRY_AGREE_S` (used by strategy.py L119-123) |
| `force_close_enabled` | strategy.py L256-259 (`buy_fc`/`sell_fc`) → a flag; keep L235 `fc_score` |
| `trend_tf` | app.py L594-596 already computes `calculate_macd` for H1; pass `signal.iloc[-2]` into `calculate_signal` and gate the flat branch L261-266 |
| `loss_cooldown_s` | app.py L477 / L646 / L755 / L795 (plus a lost flag); persist across restarts |
| `vol_tf` / `vol_len` / `*_vol` / cap | app.py L580-640 (H1 fetch) → compute the unit; at a fill (L725-733 / L765-773) store the per-basket distances; strategy.py L271 / L293 become stop then target |
| `max_adds` / `ladder_*` | strategy.py L277-288 / L299-310 (5 RSI tiers) → none, or 1 macd_turn tier on M5 with gap and gate; app.py L739 / L779 `_get_next_fibo_volume` → `units*mtqty`; add M5 to the slope TFs (app.py L593 checks `SLOPE_TIMEFRAMES`) |
| unit of an open basket | app.py L468 `units = 1` and L503-511 (re-derived only while flat) → after a restart, recover it from the positions' volume |

---

## 7. Hard to reproduce in a live MT5 loop (ranked)

1. **Per-basket state has to survive restarts.** The kernel keeps these in memory for the life of the run:
   * the unit at the open and the distances derived from it: target, stop, gap (L1266-1289);
   * `basket_units`;
   * `last_fill_price`;
   * `ladder_armed`;
   * the loss pause: `last_close` and `last_lost`.

   The live loop keeps `units` (app.py L468, starting at 1 and not re-derived while positions are open) and `_last_close_time` (L477, starting at 0) as locals, so a process restart (supervisor, `start_job.bat`, a crash, a Windows reboot) resets them. After a restart mid-basket:
   * the stop and target would scale with unit 1;
   * the distances would be gone;
   * a 12 h pause would end at once.

   Most of it can be rebuilt from MT5:
   * the unit = `round(first position volume / mtqty)`;
   * the unit at the open = the EWMA at the H1 bar before the first position's `time`, deterministic from `copy_rates_range`;
   * the pause from `history_deals_get` (the last closing deals' time and net P/L).

   `ladder_armed` is a path of per-poll votes and cannot be rebuilt exactly. Persist it, or accept a different add timing after a restart.
2. **The stops and targets exist only inside the bot.** They are checked on live polls only (no check on dead polls or while the process is down). There is no broker SL/TP: `_build_request` (mt5_helper.py L471-481) sets SL 0 for buys and 2×ask for sells. Holds last a median of about 20 h and up to 30 days (BTC V3-lite 739 h).

   A broker-side SL/TP at the same price would mirror the one-leg designs closely:
   * buy SL = fill − stop_vol·v, triggered on the bid;
   * sell SL = fill + stop_vol·v, triggered on the ask.

   It would trigger on the tick rather than the next 1 s poll, so fills differ slightly. For two-leg baskets both legs' SL/TP must move to avg ∓ mult·v/2 after the add. Without it, an outage in a crash has no protection, a case the backtest never shows.
3. **The gold edge rests on forming-bar votes.** V3-lite gold made $11,957 against $2,300 when the votes were read on closed bars (FINAL10 §7). The 8-year figures are single per-second replays with one timing.
   * The last-year ensemble shows how much timing moves a result: Top 3 ranged $3,708 – $4,674 over the 8 timings.
   * A demo feed (quotes, bar closes, the live loop's real iteration time over about 10 rate fetches per poll) that differs from the archive or the 1.0–1.2 s cadence changes which intrabar votes are seen.
   * The live code already reads the forming bar (parity-verified), so keep that, but expect more divergence than the 0.1 s parity windows suggest.
4. **The definition of the unit is easy to get wrong.**
   * It is the EWMA (α = 1/24, `adjust=False`) of \|Δclose\| of **closed** H1 **bid** bars, not ATR and not a 24-bar SMA (~20 % different).
   * Exclude the forming bar.
   * Fetch at least about 300 bars; 500 is exact. 100 bars give errors up to 12 % on BTC.
   * Read it once at the open and never refresh it.
5. **`vol_cap_usd_per_unit` is USD per 0.01 lot.** For BTC, 12 means $1,200 of BTC price, which never binds. Reading it as price units would shrink BTC targets about 100×. Also check `symbol_info().trade_contract_size` on the demo server (gold 100, BTC 1): every conversion assumes $1 per 0.01 lot per $1 of gold and $0.01 per $1 of BTC.
6. **The trend uses the closed bar.** Use `signal.iloc[-2]`, not the forming-bar `_sig` the MACD vote uses (app.py L606). A signal of exactly 0 or NaN blocks both sides.
7. **The `macd_turn` add is path-dependent.** Arming happens on any poll since the last fill where the forming-bar M5 vote is against the basket or grey, and stays set. The add fires on the first later poll with the vote with the basket, `open_score > −2` (buy) and the ask ≥ 1 unit below the entry (sell: bid ≥ 1 unit above).
   * A slower or irregular live cadence can miss or catch brief vote flips.
   * Needs the M5 slope computed every poll (not in `SLOPE_TIMEFRAMES` today).
   * The add is 1 unit, where live Fibonacci gives 2.
   * The basket's USD stop and target stay fixed after the add, which halves their distance from the average price.
8. **`entry_agree_s = 0` still filters.** A buy needs the raw M15 score ≥ 0. Keep the M15 slopes and `FORCE_CLOSE_SCORE_WEIGHTS` after disabling the force-close. FINAL10 §9's "no M15 agreement needed" is imprecise.
9. **How the loss pause is timed.** It counts from the close **decision**, uses wall-clock time (through weekends), replaces the 300 s pause rather than adding to it, and "lost" means net P/L < 0. Live also starts the pause when the close order fails; the kernel does not.
10. **Backtest-only artefacts with no live counterpart:**
    * BTC data-hole closes: 6–7 baskets per design over 8 years, closed at the last quote before a ≥3 h archive gap, then 6.3 days without entries.
    * The "volatility unknown" warm-up gate.
    * Fills at the decision quote (latency 0, no slippage). Live stop fills in fast markets (gold 2 Feb 2026) will be worse.
11. **Account assumptions.**
    * Swap-free: multi-day holds. If the demo account charges swaps, `pos.profit` ignores them, but the account result does not.
    * The results assume a fresh $2,000. A demo account with a larger balance starts at a higher unit (floor(balance/2,500) + 1, at most 10) and scales every stop.

---

## 8. Other backtest-only inputs these designs do NOT use

* `fast.run(..., regime=(times, values))` (kernels.py L1023-1026, L1214-1216) drives the "V3-lite + 200-day trend / 12-month momentum filter, as the bot runs it" supplement rows. It is not a `BacktestConfig` key and appears in none of the eight designs.
* The Turtle rows are bar-level (`research/external.py`) and are outside this map.

---

## 9. Scratchpad files behind this map

These files are in a temporary session folder that is not part of the repo (see the note at the top). They were still there at about 03:50 IST on 16 Nov 2026 but can be deleted at any time. The list is kept to show how each number above was produced.

* `levers_effective.py` → `levers_effective.json`: the full effective configs and their differences from live.
* `levers_table.py` → `levers_table.md`: the table in section 4.
* `levers_vol_stats.py`: H1 unit statistics, the cap-binding share, and the fetch-length and `adjust` sensitivity.
* `levers_trade_stats.py`: basket statistics of the final10 8-year runs.
* `levers_worked_example.py`: the engine check in section 5. It ran with `PYTHONDONTWRITEBYTECODE=1` and `NUMBA_CACHE_DIR=scratchpad/numba_cache`; the repo was untouched.
* `levers_live/{xau6,btc6}/`: `constants.py` and `symbols.json` from `git show`. No credentials were copied.
