# Map of the live bot loop: `origin/hedging_xauusd6`, and how `origin/hedging_btcusd6` differs

> **About this file.** This note was added on 16 Nov 2026, when the map was saved into the repo with `HANDOFF.md`.
> - **What it is.** A line-by-line map of the live Alcadeias bot loop, version v3.9.2. It covers start-up, one poll, the votes, the scores, the exits, the ladder, sizing, execution, every constant, and where each design lever would land in the live code. It was written for the demo port.
> - **When.** Written on 15 Nov 2026, about 17:35 IST, by an assistant session that worked read-only.
> - **What it describes.**
>   - The live files of `origin/hedging_xauusd6` at `1ed2d6c` and `origin/hedging_btcusd6` at `cef581a`, both of 13 Nov 2026. Neither branch had changed by 16 Nov 2026.
>   - The live files at the root of `backtest_hedging` are byte-identical to `origin/hedging_xauusd6` (checked with `git hash-object` on 16 Nov 2026).
>   - Backtest references (`backtesting/...`) are to `backtest_hedging` at `9e4c71f` / `0ae5794`.
> - **Out of date.**
>   - §2.7 and §5 describe `backtesting/engine/reference.py` before commit `c61c998` (15 Nov 2026, 18:51 IST). That commit extended the simulated terminal (magic numbers, comments, deal history, contract size, closed-bar reads, a shared account). It also lets `_apply_config` drive a demo branch's levers.
>   - The `reference.py` line numbers here match `git show 0ae5794:backtesting/engine/reference.py`, not the current file.
>   - `kernels.py` and `config.py` have not changed since, so their line numbers still hold.
> - **Corrected on 16 Nov 2026.** §0.1 now counts `symbols.json` as 19 lines, by the same rule as `app.py`. §0.2 now says what the CHANGELOG maintenance policy names: the 20 `dev_*_v2` branches, while the v3.9.x entries name the 40 `netting_`/`hedging_` branches.
> - **Scratch files.** This map names none.
> - **No credentials.** `mt5_credentials.json` was never opened. The two Windows user names in §1.1 are folder names taken from the launcher `start_job.bat`; they are not credentials.

All line numbers for live files are from `git show origin/hedging_xauusd6:<file>`. For BTC, `git show origin/hedging_btcusd6:<file>` gives the same numbers, because the only differences are a few literal strings and the trading window in `symbols.json`, which changes behaviour but no line number (see section 0.3).
Backtest cross-references (`backtesting/...`) point to the working tree of `backtest_hedging`.
Nothing in the repository was modified. `mt5_credentials.json` was not opened.

---

## 0. What the live branches are

### 0.1 Heads read

| branch | head | version |
|---|---|---|
| `origin/hedging_xauusd6` | `1ed2d6c` 2026-11-13 "dashboard -- show entry-agreement threshold ... (v3.9.2)" | v3.9.2 |
| `origin/hedging_btcusd6` | `cef581a` 2026-11-13 same subject | v3.9.2 |

Files on each branch:
- `app.py` (1018 lines; the last line, `    main()`, has no trailing newline)
- `strategy.py` (327), `indicator.py` (333), `mt5_helper.py` (756), `constants.py` (147), `symbols.json` (19; like `app.py`, its last line `}` has no trailing newline, so `wc -l` gives 18)
- `start_job.bat` (65), `start_xauusd.bat` / `start_btcusd.bat` (42)
- `dashboard.py` (3123), `requirements.txt`, `CHANGELOG.md`, `docs/*.md`
- `mt5_credentials.json`: exists. Per the task notes it has `demo` and `live` keys; it was not opened.
- `__pycache__/*.cpython-313.pyc` is committed. The launcher runs Python 3.11, which ignores these files.

`requirements.txt`: pandas 2.2.0, MetaTrader5 5.0.4738, multiprocess 0.70.18, dash 2.18.2, plotly 5.24.1.

### 0.2 The "hedging_<symbol><n>" mechanism (slots 6, 7, 8)

- **Slots differ only in credentials.**
  - `git diff --stat origin/hedging_xauusd6 origin/hedging_xauusd7` shows 1 file changed: `mt5_credentials.json`, 2 lines. The same holds for xau 6 vs 8, btc 6 vs 7 and btc 6 vs 8.
  - Xau 6 vs 5 is also credentials-only. Xau 6 vs 9 is credentials-only, 4 lines.
  - So every slot of a symbol runs byte-identical code. A slot is just a different MT5 account, the `demo` and/or `live` entry in its own `mt5_credentials.json`.
- **Commit structure.**
  - The slots share a base commit (`3b0cdad`, v3.8.0).
  - Each slot then has its own credentials commit.
  - The same feature commits (v3.9.0, v3.9.1, v3.9.2) were applied to every slot separately: cherry-picks, so the hashes differ but the subjects match.
  - The `CHANGELOG.md` maintenance policy (lines 10-16) says every change is propagated to "all 20 live-money fleet branches" and names them: `dev_btcusd1_v2` … `dev_btcusd10_v2` and `dev_xauusd1_v2` … `dev_xauusd10_v2`. Only the "Branches:" lines of the v3.9.x entries name the 40 `netting_`/`hedging_` deployment branches. Treat all 60 as live-money branches.
- **Launch.**
  - `start_job.bat [demo|live]` runs `app.py %MODE% --symbol XAUUSDm` (BTC: `--symbol BTCUSDm`).
  - The mode picks `credentials['demo']` or `credentials['live']` (section 1.2).

### 0.3 `hedging_btcusd6` vs `hedging_xauusd6`: the complete diff

`git diff origin/hedging_xauusd6 origin/hedging_btcusd6` touches 6 files and 18 lines:

- **`symbols.json`:**
  - `"symbol": "BTCUSDm"`.
  - `trading_window`: Monday 00:00 to Sunday 23:59. Gold is Monday 01:00 to Friday 22:00.
- **`start_job.bat` line 62:** `--symbol BTCUSDm`.
- **`start_xauusd.bat` is renamed to `start_btcusd.bat`:** the symbol changes in the echo lines and on line 39.
- **`mt5_helper.py`:**
  - Line 720: the server-time fallback list is `['EURUSDm','EURUSD','BTCUSDm','XAUUSDm','XAGUSDm']`. Gold's list has `'XAUUSDm'` twice.
  - Docstring strings change.
- **`app.py`:** docstring/help strings only (lines 446 and 1005).
- **`constants.py`:** the trailing newline at end of file is missing on BTC. Every value is identical.

**Strategy logic, constants, sizing and timing are identical on both symbols.**

What differs comes from the instrument (see `backtesting/config.py` 62-70):
- **Gold:** 0.01 lot = 1 oz, so $1 of basket P/L = a $1 move.
- **BTC:** 0.01 lot = 0.01 BTC, so $1 of basket P/L = a $100 move.
- **Trading window:**
  - Gold: no fresh entries from Friday 22:00 to Monday 01:00 UTC.
  - BTC: braked only Sunday 23:59-24:00.

---

## 1. Start-up

### 1.1 How it is launched

- **`start_job.bat`** (generic):
  - `set "MODE=%~1"`, defaulting to `demo` (lines 14-15).
  - Python path by mode (lines 18-22): live uses `C:\Users\Administrator\...\Python311`, demo uses `C:\Users\admin\...\Python311`. So demo and live are expected on machines with different Windows users.
  - Live mode waits 5 s behind a warning (40-46).
  - Installs requirements once, guarded by `deps_installed.flag` (49-58).
  - Runs `"%PYTHON_EXE%" -X utf8 -u app.py %MODE% --symbol XAUUSDm` (62).
  - There is **no restart loop** in the bat. When `app.py` exits, the script ends.
- **`start_xauusd.bat`:** the same, but with the Administrator path for both modes (11-15). It runs line 39.
- **`app.py main()`** (988-1018):

```python
parser.add_argument('mode', nargs='?', default='demo', choices=['demo', 'live'], ...)   # 1002
parser.add_argument('--symbol', '-s', type=str, default=None, ...)                       # 1004
bot = MT5TradingBot(mode=args.mode, target_symbol=args.symbol)                           # 1010
success = bot.execute_job()                                                              # 1011
sys.exit(0 if success else 1)                                                            # 1014
```

`MT5TradingBot.__init__` (33-55) sets:
- `self.mode`
- `self.target_symbol`, upper-cased
- `self.thread_lock` (file I/O) and `self.mt5_lock` (MT5 API)
- `self.indicator = Indicator()`, `self.strategy = Strategy()`
- `self._stop_event`

### 1.2 Init sequence: `execute_job()` (950-985) and `_init_cycle()` (909-948)

`_init_cycle` is tried up to 3 times, with `time.sleep(5)` between attempts (958-965). Each attempt:

1. **Writes the mode.** `OUTPUT_DIR\active_config.json` (`C:\Alcadeias\active_config.json`) gets `{'mode': self.mode}` (914-927). The dashboard reads it; the bot itself never reads it back.
2. **`load_credentials()`** (157-175):
   - Opens `Path(__file__).parent / 'mt5_credentials.json'`.
   - Requires `self.mode in credentials`, then sets `self.credentials = credentials[self.mode]`.
   - The keys used later are `terminal_path`, `login_id`, `login_pass` and `server` (238, 246-250).
3. **`load_symbols()`** (177-229):
   - Reads `symbols.json` and keeps entries with `is_active` true (197).
   - With `--symbol`, filters to the case-insensitive match (207-216). An unknown symbol fails.
   - Builds `self.symbols` and `self.symbol_configs[name] = entry`.
4. **`initialize_mt5()`** (231-297):
   - `mt5.initialize(path=self.credentials['terminal_path'])`, then `mt5.login(login=..., password=..., server=...)`.
   - Prints the account, then creates `MT5PositionHelper(mt5)` (278).
   - `_build_symbol_map()` (146-155) resolves broker aliases with a scored `symbols_get` search (102-144).
   - Subscribes the traded symbol plus an EURUSD heartbeat via `mt5.symbol_select` (282-295).

Then `run_multithreaded_processing()` (846-900) runs:
- **One symbol** (always the case with `--symbol`): `self.process_symbol(symbol)` on the main thread (856-868).
- **Several symbols:** a thread pool, the legacy path.

`process_symbol` never returns unless `_stop_event` is set (837-838, 843-844). Nothing in `app.py` sets that event except KeyboardInterrupt or an exception in `execute_job`.

### 1.3 Trading window

- `trading_window_cfg = self.symbols_config.get('trading_window', {})` (453).
- `_is_in_trading_window(now_dt, window_cfg)` (78-100) converts both ends to minutes since Monday 00:00 with `_day_time_to_week_minutes` (68-76):
  - `enabled` false or missing: always in the window.
  - `start == end`: 24/7.
  - `start < end`: `start <= now < end`.
  - Otherwise the window wraps.
- Evaluated each poll on **broker server time**, i.e. the latest tick time of the traded symbol (`_get_server_time`, mt5_helper 707-741; Exness = UTC+0):

```python
in_window = self._is_in_trading_window(server_time, trading_window_cfg)   # 516
brake = 1 if brake_manual or not in_window else 0                          # 517
```

- `brake` only blocks **fresh** BUY/SELL (726, 766).
- Ladder adds and closes run regardless of the window. Open baskets are held over the gold weekend.

### 1.4 Main loop and timing

`process_symbol(symbol)` (440-844) works in two parts.

Once before the loop (450-477):

```python
sym_cfg = self.symbol_configs.get(symbol, {})                 # 451
brake_manual = self.symbols_config.get('brake', 0)            # 452
trading_window_cfg = self.symbols_config.get('trading_window', {})   # 453
step_up_balance = sym_cfg.get('step_up_balance', 0)           # 466
max_limit = sym_cfg.get('unit_max_limit', 1)                  # 467
units = 1                                                     # 468
mtqty = self.symbols_config.get('mtqty', 0.01)                # 469
trade_symbol = self.symbol_map.get(symbol, symbol)            # 470
_last_daily_save = 0.0; _last_hist_save = 0.0                 # 473-474
_DAILY_SAVE_INTERVAL = 60; _HIST_SAVE_INTERVAL = 300          # 475-476
_last_close_time = 0.0          # for the post-close re-entry cooldown   477
```

These locals, plus `units`, are the **only state carried between polls**. `Strategy` is stateless: its only attribute is `self.hedge`, which nothing uses.

Then `while True:` (479), and every iteration does:

| step | lines | sleep / timing |
|---|---|---|
| MT5 reads, lock window 1: `symbol_select`, `get_rates(M15, 300)`, `get_market_status(M1, lookback 3 min)` | 485-491 | `get_rates`/`get_market_status` retry an empty fetch up to 3 times with `time.sleep(0.2)` (mt5_helper 287, 408) |
| `time.sleep(0)`, a yield | 492 | 0 |
| lock window 2: `get_buy_positions`, `get_sell_positions`, `get_account_info`, `_get_server_time` | 493-497 | |
| unit auto-step | 503-511 | |
| brake | 516-517 | |
| `_save_account_data` (writes `C:\Alcadeias\account.json`) | 520-521 | |
| freshness check | 527-556 | |
| indicators (7 rate fetches of 500 bars) and `calculate_signal` | 558-660 | Python RSI/MACD/pivots on 7 TFs |
| execution | 722-802 | `buy()`/`sell()` sleep 0.1 s (mt5_helper 510, 528); after an **add**, `time.sleep(ORDER_COOLDOWN_SECONDS)` = 1 s more (751, 791); no extra sleep after a fresh open or a close |
| `_save_symbol_data` (`C:\Alcadeias\<symbol>.json`), daily trades every 60 s, history every 300 s | 819-832 | |
| `time.sleep(max(brake, 1))` | 834 | **always 1 s**, since brake is 0 or 1 |
| any Exception | 840-844 | `print(f"[{symbol}] Error: {e}")`, `time.sleep(1)`, continue. A bug in new code silently stops trading while the loop keeps running |

The poll period is therefore 1 s plus the variable work time, plus 0.1 s or 1.1 s when an order is sent. The loop is **not** on a fixed 1 s grid.

The backtest kernel uses a fixed `poll_interval_ms=1000` and `poll_jitter_ms=0` (config.py 153-161). The research reports "8 timings" to show how results vary with loop phase.

---

## 2. The decision flow, per poll, in order

### 2.1 Market data and freshness (527-556)

- **`source_df`** is 300 M15 bars (`CANDLE_TIMEFRAME`, `CANDLE_COUNT`), fetched through the non-simple `get_rates` path (mt5_helper 279-370):
  - warms the feed;
  - compares `copy_rates_from_pos` with `copy_rates_from(now_tick)`;
  - the synthetic tick bar and the tick rebuild apply only to M1.

  The strategy does **not** use it. It only sets `has_candle_data` (527) and metadata.
- **`candle_is_fresh = bool(market_status.get('is_open'))`** (543), where `get_market_status` (mt5_helper 372-452) computes:
  - `activity_ref = max(last M1 bar time, last tick time)`;
  - `is_open = (datetime.now(UTC) - activity_ref) <= 3 min`.

  This uses the **local VPS clock** against the broker tick time.
- If the data is not fresh, `calculate_signal` is **not called**. Nothing is decided: no target, no force-close, no ladder (558, 659-660).

### 2.2 Units and lots (503-511, 728, 739, 768, 779)

```python
if _buy_ct == 0 and _sell_ct == 0 and account_info:          # 505
    balance = account_info.get('balance', 0)
    if step_up_balance and step_up_balance > 0:
        units = int(balance // step_up_balance) + 1           # 508
    else:
        units = 1
    units = max(1, min(units, max_limit))                      # 511
```

- **The unit is re-derived only while flat.** With `step_up_balance=2500` and `unit_max_limit=10`: balance under $2,500 gives 1 unit, $2,500-4,999 gives 2, and so on up to 10.
- **Entry lot:** `units * mtqty` (728, 768), i.e. 0.01 x units.
- **Ladder add lot:** `self.strategy._get_next_fibo_volume(total_volume, units)` (739, 779), defined in strategy.py 39-65.
  - It walks the Fibonacci list `[1,2,3,5,8,13,...]` (`FIBO_SEQUENCE_LENGTH=25`, the first two dropped) and returns the next element times `units / 100`.
  - The `/100` **hard-codes mtqty = 0.01**.
  - Positions: units=1 gives 0.01, 0.02, 0.03, 0.05, 0.08, 0.13 (6 positions, 0.32 lots). Units=3 gives 0.03 ... 0.39 (0.96 lots).
- `_get_fibo_qty` (32-37) is dead code.

### 2.3 Votes: what is computed, on which bars (564-641; indicator.py)

**Timeframes fetched** (573-579): the ordered union of these lists, which comes out as **[M1, M5, M15, M30, H1, H4, H6]**:
- `RSI_MTF_TIMEFRAMES` (M1, M5, M15, M30)
- `RSI_DCA_LADDER_TIMEFRAMES` (M1, M5, M15, H1, H4)
- `SLOPE_TIMEFRAMES` (H1, M15)
- `[RSI_FINAL_CLOSE_TIMEFRAME]` (H6)

Each one is fetched with:

```python
tf_df = self.position_helper.get_rates(trade_symbol, getattr(mt5, tf_name), RSI_CANDLE_COUNT, simple=True)  # 582-584
```

- The `simple=True` path (mt5_helper 271-277) is `copy_rates_from_pos(symbol, tf, 0, 500)`. **Position 0 is the still-forming bar, so the last row is the forming bar.**
- **Every RSI, MACD and pivot value the strategy reads is a forming-bar (intrabar) value.** The last close is the current Bid.

**RSI** (586-589):
- `Indicator.calculate_rsi(close, 14, 'RMA')` (indicator.py 86-111) uses a Wilder RMA, SMA-seeded via `_tv_exp_ma` (13-53).
- `rsi.fillna(100.0)`, so the warm-up NaNs become 100.
- `rsi_mtf[tf] = rsi_s.iloc[-1]`, the forming bar. A failed fetch gives 50.0 (639-640).
- M30 and H6 are fetched but **no decision reads them** (dashboard only).
- `current_rsi` = M1 RSI (641), used for display.

**Slope votes**: only for `tf_name in SLOPE_TIMEFRAMES`, i.e. **H1 and M15** (593-638):
- **MACD:** `calculate_macd(close, 12, 26, 9)` (indicator.py 113-140) uses SMA-seeded EMAs; hist = macd - signal.
- **RSI vote:** `latest_pivot_slope(rsi_s, lookback=20, width=2, ob_level=60, os_level=40)` (599-602).
- **MACD vote:** `latest_pivot_slope(hist, lookback=20, width=2, side=...)`. The side comes from the **forming bar's signal line**:

```python
_sig = float(macd_df['signal'].iloc[-1]) if len(macd_df) > 0 else 0.0      # 606
_macd_side = 'high' if _sig > 0 else ('low' if _sig < 0 else None)          # 607
```

- **`latest_pivot_slope`** (indicator.py 142-224):
  - Scans i from `n-1-width` (= n-3, so a pivot's right neighbours include the forming bar) back to `max(width, n-lookback)`.
  - The first bar strictly above its 2 left and 2 right neighbours is a high; strictly below is a low.
  - An RSI high counts only if >= 60, an RSI low only if <= 40.
  - The `side` argument restricts MACD to highs only or lows only.
  - `slope = (current - pivot) / bars_ago`, where `current = vals[-1]` (the forming bar), and `sign = +1/-1/0`. No pivot gives sign 0, the "grey" vote.
- **Storage:** `slopes[tf_key] = {'rsi': {...,'sign'}, 'macd': {...,'sign'}}` with `tf_key` 'H1' or 'M15' (612-615).
- The H1 `macd_df` and `tf_df` are **loop-locals** and are not kept after the loop. Only `slopes`, `rsi_mtf` and the graph series survive.

### 2.4 Scores and thresholds (strategy.py 226-259)

```python
open_score = self._weighted_score(slopes, OPEN_SCORE_WEIGHTS, grey_fill=True)   # 234  {'H1':1,'M15':1} -> range +-4
fc_score = self._weighted_score(slopes, FORCE_CLOSE_SCORE_WEIGHTS)              # 235  {'M15':1} raw  -> range +-2
entry_direction = self._entry_direction(open_score, fc_score)                   # 241
open_wants = 'BUY' if open_score >= ENTRY_S else ('SELL' if open_score <= -ENTRY_S else None)   # 243
entry_chop_block = bool(open_wants and entry_direction is None)                 # 244
buy_add_ok = open_score > -LADDER_S                                             # 249
sell_add_ok = open_score < LADDER_S                                             # 250
buy_fc = fc_score <= -FORCE_CLOSE_S                                             # 256
sell_fc = fc_score >= FORCE_CLOSE_S                                             # 258
```

- **`_weighted_score`** (76-104) is `sum(w * (rsi_sign + macd_sign))`.
  - Grey-fill (OPEN only): if exactly one of a TF's two signs is 0, it borrows the other sign, so the TF counts plus or minus 2w.
- **`_entry_direction`** (106-123):
  - BUY if `open_score >= ENTRY_S(2) and fc_score >= ENTRY_AGREE_S(2)`; SELL mirrors it; otherwise None.
  - **The M15 force-close score doubles as the entry agreement gate.**
- `_slope_direction` (125-161) is computed (226) but is display-only. It needs H4, which is no longer fetched for slopes, so it reads "WAIT".

### 2.5 Branches (strategy.py 261-310), checked in this order

**Flat** (261-266). The only entry gate in strategy.py is the cooldown:

```python
if entry_allowed and entry_direction == 'BUY':   buy_status = Signal.BUY
elif entry_allowed and entry_direction == 'SELL': sell_status = Signal.SELL
```

**Open BUY only** (268-288); SELL mirrors it at 290-310:

```python
if buy_profit > close_threshold:          # 271  target (USD)            exit_reason 'target'
    buy_status = Signal.CLOSE_BUY
elif buy_fc:                              # 274  M15 force-close           exit_reason 'force_close'
    buy_status = Signal.CLOSE_BUY
elif buy_add_ok:                          # 277  ladder gate (open_score > -2)
    if rsi_1m <= RSI_OVERSOLD and buy_count == 1:   buy_status = Signal.BUY_MORE   # 279
    elif rsi_5m  <= RSI_OVERSOLD and buy_count == 2: ...                           # 281
    elif rsi_15m <= RSI_OVERSOLD and buy_count == 3: ...                           # 283
    elif rsi_1h  <= RSI_OVERSOLD and buy_count == 4: ...                           # 285
    elif rsi_4h  <= RSI_OVERSOLD and buy_count == 5: ...                           # 287
```

**Both sides open** (`buy_count>0 and sell_count>0`): no branch matches, so DO_NOTHING on both. A manual or foreign position on the other side freezes management of the basket.

**Target:**
- `close_threshold=units` (app.py 650), so **$1 per unit for the whole basket**, however many positions it holds.
- `buy_profit` = `round(sum(pos.profit), 2)` over the side's positions (mt5_helper 62, 72): MT5 floating profit, **excluding swap and commission**.
- The comparison is strict `>`.

**Stop:** **none in the loop.** Broker SL/TP come from `RISK_REWARD_RATIO=[1,1]` (mt5_helper 471-481):
- BUY: `sl = ask - ask*1 = 0` (no SL), `tp = 2*ask`.
- SELL: `sl = 2*ask`, `tp = 0` (no TP).

Neither is reachable in practice.

**Force-close:** M15 only, raw signs. A BUY closes at `fc_score <= -1`, a SELL at `>= +1`. It is checked after the target and before the ladder.

**Profit-book:** none on the hedging variant. The netting branches have `BOOK_SCORE_WEIGHTS`/`BOOK_S`. `PROFIT_PROTECT_MIN_USD = 0.0` (constants 117) is defined but nothing reads it.

**Ladder:**
- **Tiers** are hard-coded per position count: count 1 uses M1, 2 uses M5, 3 uses M15, 4 uses H1, 5 uses H4.
  - Changing `RSI_DCA_LADDER_TIMEFRAMES` changes only which TFs are fetched, not the tiers.
- **Trigger:** the forming-bar RSI of the tier TF is `<= 35` (BUY) or `>= 65` (SELL). This is a level, a *state*.
- **Gate:** `open_score > -2` (BUY) or `< +2` (SELL).
- **Spacing:** no price gap and no time gap, apart from the 1.1 s of sleeps after an add. Several tiers can fire on consecutive polls.
- **Max adds:** 5, so at most 6 positions. Sizes as in section 2.2.

**Time stop:** none. `RSI_FINAL_CLOSE_TIMEFRAME='TIMEFRAME_H6'` is fetched (app 577) but not used; the constants comment at 43-53 is stale.

**Pause after a basket** (app.py 646, 755, 795):

```python
entry_allowed = (time.time() - _last_close_time) >= REENTRY_COOLDOWN_SECONDS   # 646 (300 s)
_last_close_time = time.time()   # start the re-entry cooldown                 # 755 (CLOSE_BUY), 795 (CLOSE_SELL)
```

- The same 300 s applies whatever the reason or the result of the close.
- It is set after `close_by_type` returns, **even if the close failed**.
- It is **reset by a restart** (`_last_close_time = 0.0`, line 477).

### 2.6 Execution (app.py 722-802; mt5_helper.py)

| signal | condition | call | then |
|---|---|---|---|
| BUY | `has_candle_data and candle_is_fresh` and `not brake` (725-726) | `buy(trade_symbol, units * mtqty)` (728) | `_log_event('BUY_EXECUTED','ENTRY')`. If braked, `BUY_SIGNAL` "Brake active". The retcode is **not checked**: a refused order is just retried next poll |
| BUY_MORE | (738) | `buy(trade_symbol, vol)`, vol from `_get_next_fibo_volume` (739-741) | log `BUY_MORE_EXECUTED`; `time.sleep(ORDER_COOLDOWN_SECONDS)` (751) |
| CLOSE_BUY | (752) | `close_by_type(trade_symbol, 0)` (754) | `_last_close_time = time.time()` (755); log `CLOSE_BUY` with `total_profit` (the decision-time floating P/L) and `reason=exit_reason` |
| SELL / SELL_MORE / CLOSE_SELL | 765-802 | mirror, `close_by_type(..., 1)` | |

`_build_request` (mt5_helper 454-493), used by `buy()` (495-511) and `sell()` (513-529):

```python
ask = self.mt5.symbol_info_tick(symbol).ask
... "action": TRADE_ACTION_DEAL, "symbol": symbol, "volume": qty, "type": order_type,
    "price": ask,                       # ask for BOTH buy and sell
    "type_time": ORDER_TIME_GTC, "type_filling": ORDER_FILLING_IOC, "sl": computed_sl, "tp": computed_tp
```

- No `deviation`, **no `magic`**, **no `comment`**.
- `time.sleep(0.1)` after `order_send` (510, 528).

`close_by_type(symbol, pos_type)` (531-621):
- Reads `positions_get(symbol=symbol)` and filters by `type`.
- For each position, sends an opposite deal with `"position": pos.ticket`, `"price": bid` (closing a buy) or `ask` (closing a sell), `"deviation": 20`, IOC, GTC (591-601).
- Counts DONE and failed results. It does not return the realised profit.

**Position reads:** `get_buy_positions` / `get_sell_positions` (31-127) call `positions_get(symbol=symbol)`.
- They take **every position on the symbol**, with no magic or comment filter. Manual trades, or another bot on the same account and symbol, become part of "the basket".
- They return only `count`, `total_profit`, `total_volume`, `first_profit`/`first_volume` and `last_profit`/`last_volume`.
- `price_open` and `time` are not exposed. They exist on the MT5 position objects (`first_pos`/`last_pos`, 66-67).

### 2.7 Restart handling

There is **no persistence**. A restart (the process killed and relaunched by the operator or a scheduler; the bat does not loop) does the following:
- **Units:** reloads from `symbols.json` with `units = 1` (468) and `_last_close_time = 0.0` (477).
- **Open basket:** if a basket is open at restart, **`units` stays 1 until the basket is flat** (re-derivation is flat-only, 505). That makes the target $1 instead of $N, and the ladder lots are computed with `times=1`. Example: a 0.03 entry at units=3 would get a 0.03 add instead of 0.06.
- **Cooldown:** lost, so a fresh entry is allowed on the first poll after a restart.
- **Basket ownership:** whatever is open on the symbol is adopted as the basket. Nothing distinguishes this bot's positions from others.

The reference engine can simulate restarts (`run_reference(..., restart_at=...)`, reference.py 495-497, 617-625): a fresh `MT5TradingBot` with the terminal's positions kept.

### 2.8 Per-poll outputs

- **`analysis_data` keys** (strategy.py 312-325, app.py 656-684): `rsi_value`, `rsi_mtf`, `slopes`, `slope_direction`, `entry_direction`, `open_score`, `fc_score`, `buy_add_ok`, `sell_add_ok`, `entry_allowed`, `entry_chop_block`, `exit_reason`, `rsi_graphs`, `macd_graphs`, `candle_fresh`, `source_candle_count`, `rates_source`, `synthetic_bar`, `tick_rebuilt`, `last_source_candle_time`, `candle_age_min`, `unit_times`, `step_up_balance`, `unit_max_limit`, `iteration_ms`.
- **Written to** `C:\Alcadeias\<symbol>.json` every poll (819).
- **Events** go to `C:\Alcadeias\logs\<symbol>_strategy_log.json`, newest first, capped at 200 (396-438).
- **Daily deals** are written to the **hard-coded** `C:\Alcadeias\daily_trade\<symbol>\dd_mon_yyyy.json` (327; it does not use `OUTPUT_DIR`).
- **History summary** goes to `OUTPUT_DIR\daily_trade\<symbol>\historical_summary.json`.

Several bots on one machine therefore overwrite each other's files, including `account.json` and `active_config.json`.

---

## 3. Every constant and `symbols.json` key

### 3.1 `constants.py` (identical on xau6 and btc6)

Reader line numbers count only code lines. Docstring mentions are excluded.

| constant | line | value | read by | role |
|---|---|---|---|---|
| `CANDLE_TIMEFRAME` | 13 | `'TIMEFRAME_M15'` | app 488 | M15 "source" feed; freshness metadata only |
| `CANDLE_COUNT` | 14 | 300 | app 488 | bars in that feed |
| `ALLOW_SYNTHETIC_TICK_BAR` | 15 | True | mt5_helper 320 | synthetic tick bar, **M1 only** (the source feed is M15, so it never applies) |
| `MARKET_STATUS_TIMEFRAME` | 18 | `'TIMEFRAME_M1'` | app 490 | liveness probe |
| `MARKET_LOOKBACK_MINUTES` | 19 | 3 | app 490 | live if a tick or M1 bar arrived within 3 min (local clock) |
| `STRATEGY_HEDGE` | 22 | 1 | strategy 25 (`self.hedge`) | **unused** |
| `FIBO_SEQUENCE_LENGTH` | 23 | 25 | strategy 33, 55 | Fibonacci list length (first 2 dropped) |
| `RSI_LENGTH` | 26 | 14 | app 587 | RSI period |
| `RSI_MA_TYPE` | 27 | `'RMA'` | app 587 | Wilder smoothing |
| `RSI_CANDLE_COUNT` | 31 | 500 | app 583 | bars per indicator fetch (all 7 TFs) |
| `RSI_OVERSOLD` | 32 | 35 | strategy 279-287 | BUY ladder level |
| `RSI_OVERBOUGHT` | 33 | 65 | strategy 301-309 | SELL ladder level |
| `RSI_MTF_TIMEFRAMES` | 36 | M1, M5, M15, M30 | app 574 | fetch list (M30 display only) |
| `RSI_DCA_LADDER_TIMEFRAMES` | 45-47 | M1, M5, M15, H1, H4 | app 575 | fetch list only; the tiers are hard-coded in strategy |
| `RSI_FINAL_CLOSE_TIMEFRAME` | 53 | `'TIMEFRAME_H6'` | app 577 | fetched, **never used in a decision** |
| `MACD_FAST` / `MACD_SLOW` / `MACD_SIGNAL` | 56-58 | 12 / 26 / 9 | app 595 | MACD |
| `ENTRY_S` | 67 | 2 | strategy 119, 121, 243; dashboard 902-911 | \|open_score\| to open |
| `ENTRY_AGREE_S` | 69 | 2 | strategy 119, 121; dashboard 1235 | fc_score must agree by this to open (M15 both votes) |
| `LADDER_S` | 75 | 2 | strategy 249-250 | ladder gate on open_score |
| `FORCE_CLOSE_S` | 77 | 1 | strategy 256, 258; dashboard 1234 | force-close threshold |
| `OPEN_SCORE_WEIGHTS` | 91 | `{'H1': 1, 'M15': 1}` | strategy 234; constants 101; dashboard 899, 957, 1231 | open and ladder-gate section |
| `FORCE_CLOSE_SCORE_WEIGHTS` | 92 | `{'M15': 1}` | strategy 235; constants 101; dashboard 1233-1234 | force-close **and entry-agreement** section |
| `SLOPE_TIMEFRAMES` | 100-102 | derived: `['TIMEFRAME_H1','TIMEFRAME_M15']` | app 576, 593 | TFs that get RSI and MACD pivot slopes (the **union of the OPEN and FC dicts only**) |
| `PEAK_LOOKBACK` | 103 | 20 | app 600, 609 | pivot scan window |
| `PIVOT_WIDTH` | 104 | 2 | app 600, 609 | bars each side of a pivot |
| `RSI_PEAK_OB` / `RSI_PEAK_OS` | 108 / 109 | 60 / 40 | app 601, 625 | RSI pivot bands |
| `RSI_GRAPH_BARS` | 112 | 40 | app 619, 631 | dashboard series length |
| `REENTRY_COOLDOWN_SECONDS` | 113 | 300 | app 646 | pause after any close |
| `PROFIT_PROTECT_MIN_USD` | 117 | 0.0 | **nobody** | leftover |
| `RISK_REWARD_RATIO` | 121 | [1, 1] | mt5_helper 24, 471-481 | broker SL/TP (effectively none) |
| `OUTPUT_DIR` | 124 | `r'C:\Alcadeias'` | app 302, 313, 369, 421, 915; dashboard 27 | JSON output root |
| `DAILY_TRADE_SUBDIR` | 125 | `'daily_trade'` | app 369; dashboard 28 | |
| `HISTORICAL_SUMMARY_DAYS` | 126 | 3650 | app 376 | |
| `HISTORICAL_SUMMARY_FILENAME` | 127 | `'historical_summary.json'` | app 371; dashboard 1566, 1603, 1635 | |
| `DASHBOARD_REFRESH_INTERVAL` / `HOST` / `PORT` | 130-132 | 5000 / '0.0.0.0' / 8050 | dashboard 29, 3123 | |
| `DASHBOARD_MAX_HEIGHT_JSON` | 133 | 300 | nobody | |
| `GRAPH_TEXT_LABEL_THRESHOLD` / `GRAPH_CUM_LABEL_THRESHOLD` | 136-137 | 60 / 60 | dashboard 1736-1737 | |
| `ORDER_COOLDOWN_SECONDS` | 140 | 1 | app 751, 791 | sleep after a ladder add |
| `STRATEGY_LOG_FILENAME` | 143 | `'strategy_log.json'` | app 423; dashboard 1950 | |
| `STRATEGY_LOG_MAX_ENTRIES` | 144 | 200 | app 435 | |
| `ACTIVE_CONFIG_FILENAME` | 147 | `'active_config.json'` | app 915; dashboard 126, 131 | the bot writes `mode` here |

`dashboard.py` imports `ENTRY_S`, `ENTRY_AGREE_S`, `FORCE_CLOSE_S`, `OPEN_SCORE_WEIGHTS` and `FORCE_CLOSE_SCORE_WEIGHTS` from constants (dashboard 15-24). **Removing or renaming any of them breaks the dashboard import.**

### 3.2 `symbols.json`

| key | xau6 | btc6 | read by |
|---|---|---|---|
| `brake` | 0 | 0 | app 452 → 517; also 834 (`sleep(max(brake,1))`) |
| `mtqty` | 0.01 | 0.01 | app 469 → 728, 768 (entry lots). The ladder ignores it (strategy hard-codes /100) |
| `trading_window.enabled/start_day/start_time/end_day/end_time` | true, Monday 01:00 → Friday 22:00 | true, Monday 00:00 → Sunday 23:59 | app 453 → 516 (`_is_in_trading_window` 78-100) |
| `symbols[0].symbol` | XAUUSDm | BTCUSDm | app 194, matched against `--symbol` (209) |
| `symbols[0].is_active` | true | true | app 197 |
| `symbols[0].step_up_balance` | 2500 | 2500 | app 466 → 508 |
| `symbols[0].unit_max_limit` | 10 | 10 | app 467 → 511 |

The dashboard also reads `symbols.json` itself (dashboard 135-137).

---

## 4. Where each listed change would land (current behaviour at each spot)

Backtest semantics are cited from `backtesting/engine/kernels.py` (the design overrides in `top3_v4_*_designs.json` feed these). No change is designed here.

### 4a. Entry filter by the H1 trend (`trend_tf='H1'`, `trend_mode=+1`)

**Backtest semantics:**
- The trend is the sign of the H1 MACD **signal line of the last CLOSED bar**: `SG[off + K - 1]` (kernels 1015-1022).
- It blocks a fresh entry when `want_side * trend_now <= 0`, so a zero or unknown trend also blocks (kernels 1217-1219).
- It is applied at the order stage, after brake and quarantine.

**Data in the live loop today:**
- H1 rates: `tf_df` at app.py 582-584 (500 bars, last row forming).
- H1 MACD: `macd_df` at 594-596, computed only because 'H1' is in `SLOPE_TIMEFRAMES`.
- The only signal-line read is the **forming** bar, `macd_df['signal'].iloc[-1]` (606), used to pick the MACD pivot side.
- The last closed bar would be `iloc[-2]`. It is not read or kept anywhere, and `macd_df` is overwritten by the next TF in the loop.

**Passing to the strategy:** the `calculate_signal(...)` call (app 647-655) has no trend argument. The signature is strategy.py 163-167.

**Decision point:** the flat branch, strategy.py 261-266 (`if entry_allowed and entry_direction == 'BUY'`), or `_entry_direction` 106-123. An app-side alternative is the execution guards at app.py 725-726 / 765-766, next to `if not brake:`.

**Current behaviour:** no trend gate. Fresh entries are gated only by `entry_direction` (open + agreement), the cooldown and the brake.

### 4b. Volatility-based target and stop (`vol_tf='H1'`, `vol_len=24`, `target_vol`, `stop_vol`; `target_usd_per_unit=None`)

**Backtest semantics:**
- **Vol unit:** `vol_array` (kernels 305-321) is an EWMA, weight 1/24, of |ΔClose| of **closed** H1 bars. The kernel takes the value at the last closed bar (`VOL[off+K-1]`).
- **Snapshot at open:** it is snapshotted **when the basket opens** and kept for the basket's life (kernels 1274-1289):
  - `b_target = target_vol * v * usd_per_price`
  - `b_sl = stop_vol * v * usd_per_price`
  - `usd_per_price = contract_size * mtqty` (kernels 725): 1.0 for XAU, 0.01 for BTC.
- **No vol yet:** no entry while the vol is unknown (kernels 1223-1225).
- **Per poll:**
  - Stop first: `profit <= -b_sl * basket_units`.
  - Then target: `profit > b_target * basket_units` (kernels 1072-1079).
  - Then force-close (if enabled) and the ladder.

**Live target today:** strategy.py 271 (BUY) / 293 (SELL), `buy_profit > close_threshold`. `close_threshold=units` is passed at app.py 650 ($1 x unit), and the target is the first check in each open branch.

**Live stop today:** none.
- No branch before 271/293.
- Broker SL/TP from `_build_request` (mt5_helper 471-481) are effectively off.
- `buy()`/`sell()` accept `sl`/`tp` parameters (495, 513), but app.py never passes them (728, 741, 768, 781).

**Missing inputs at that spot:**
1. **No volatility function.** There is no ATR or vol function in `indicator.py`. H1 closes exist only transiently in the loop (582-589).
2. **No per-basket state.** Only `units` is basket-sticky (499-511), and there is nowhere to hold a value measured at the open. The open happens at app.py 725-733 / 765-773.
3. **No contract size.** It appears nowhere in the live code. `mt5.symbol_info` is called only in `_resolve_symbol_alias` (104) and `_ensure_symbol_ready` (mt5_helper 166).
4. **No restart survival.** Section 2.7 applies; the MT5 position `time` / `price_open` are not exposed by `get_*_positions`.

The basket profit used for the comparison is `buy_positions['total_profit']` (strategy 207/210 ← mt5_helper 62/72).

### 4c. Cap on the volatility distance in $ per unit (`vol_cap_usd_per_unit`, 12 or 20)

**Backtest semantics:** it caps the **volatility unit itself**, at the basket-open snapshot (kernels 1276-1277):

```python
if vol_cap > 0.0 and v_now * usd_per_price > vol_cap:
    v_now = vol_cap / usd_per_price
```

The target and stop are then multiples of the capped unit. For example, gold Top 2 has a 4-unit stop and an 8-unit target, with 1 unit at most $12 per 0.01 lot.

**Live location:** the same spot as 4b, i.e. wherever the open-time snapshot would be taken (app.py 725-733 / 765-773). It needs the $/price conversion that the live code lacks (4b item 3).

**Current behaviour:** nothing. There is no distance concept, only the fixed $1 x unit target.

### 4d. Longer pause after a losing basket (`loss_cooldown_s`: 3600, 14400 or 43200)

**Backtest semantics:**

```python
entry_allowed = (T - last_close) >= (loss_cooldown if (last_lost and loss_cooldown > 0) else cooldown)   # kernels 1014
last_lost = (realised - basket_comm) < 0.0       # kernels 1461, realised at the close fill price
last_close = T                                   # kernels 1479, the decision poll
```

**Live location:**
- Check: app.py 646 (`entry_allowed = (time.time() - _last_close_time) >= REENTRY_COOLDOWN_SECONDS`).
- Start: app.py 755 / 795 (`_last_close_time = time.time()`).
- State lives in process-locals (477).

**What the live code knows at the close:**
- `buy_positions['total_profit']`, the decision-time floating P/L (logged at 759/799).
- `analysis_data['exit_reason']`.
- `close_response` (counts and tickets only). The realised P/L is not returned by `close_by_type` (mt5_helper 531-621).
- `get_deal_history`/`get_today_deals` (mt5_helper 623-705) read realised deals, but only in the throttled 60 s save (app 822-832).

**Current behaviour:** 300 s after every close, win or lose. It is lost on restart.

### 4e. Switching the M15 force-close off (`force_close_enabled=False`)

**Live location:**
- strategy.py 256-259 (`buy_fc` / `sell_fc` from `fc_score`), consumed at 274 (`elif buy_fc:`) and 296 (`elif sell_fc:`).
- Threshold `FORCE_CLOSE_S` (constants 77); section `FORCE_CLOSE_SCORE_WEIGHTS` (constants 92).

**Current behaviour:** a BUY basket closes the first poll the M15 raw score is at or below -1, i.e. one M15 vote turns against it, read on the forming bar. This check comes after the target and before the ladder.

**Coupling that must be kept in mind:** the **same `fc_score` is the entry agreement gate.**
- strategy 241 → 119/121.
- Kernel: `agree_score = fc_score` when no separate agree section (kernels 1000-1001), whatever `force_close_enabled` says (kernels 1056/1060 only gate the close).
- The designs still rely on it:
  - V3-lite: `entry_agree_s=2`, both M15 votes must agree.
  - Top 1/2/3: `entry_agree_s=0`, M15 must not oppose.
- `SLOPE_TIMEFRAMES` (constants 100-102) is derived only from the OPEN and FORCE_CLOSE dicts. Emptying `FORCE_CLOSE_SCORE_WEIGHTS` with H1-only open weights would stop the M15 slopes being computed, giving `fc_score == 0` on every poll.
- The dashboard FORCE-CLOSE meter (dashboard 1233-1235) also reads these constants.

### 4f. Entry votes from H1 only (`open_weights={'H1': 1}`)

**Live location:** constants.py 91 `OPEN_SCORE_WEIGHTS`, read at strategy.py 234 (with `grey_fill=True`). It is also the ladder-add gate (249-250) and feeds `SLOPE_TIMEFRAMES` (100-102) and the dashboard gauge (dashboard 899, 957, 1231).

**Current behaviour:**
- H1 + M15, range ±4.
- `ENTRY_S=2` is met by one fully aligned TF, or by both half-aligned.
- With H1 only, the range becomes ±2, so `ENTRY_S=2` needs both H1 votes, or one vote with the other grey (grey-fill).
- `LADDER_S=2` then blocks a BUY add only when H1 is fully adverse.
- Kernel: grey-fill applies when both weights are non-zero (kernels 960-965), matching scalar weights.

### 4g. Ladder add on a MACD turn, at given TFs, with a minimum gap in vol units

Design values: `ladder_trigger='macd_turn'`, `ladder_tfs=['M5','M15','H1','H1','H1']`, `max_adds=1`, `ladder_multipliers=[1,1,1,1]`, `ladder_gap_vol=1.0`. XAU Top 1 and Top 3 use it; the other designs have `max_adds=0`.

**Backtest semantics:**
- **Tier:** tier `cnt-1` (count 1 → M5).
- **Arming:** armed once the tier TF's MACD vote is not in the basket's favour at any poll since the last fill; it fires when the vote is in favour (kernels 1113-1117).
- **Gates:** also needs `add_ok` (open-score gate, kernels 1058/1062) and the price gap: BUY `(last_fill_price - ask) >= gap`, SELL `(bid - last_fill_price) >= gap` (kernels 1132-1136). The gap is `ladder_gap_vol * v`, snapshotted at the open (kernels 1284-1285).
- **Size:** lot = `ladder_mult[n_pos] * basket_units * mtqty` = 1 unit (kernels 1327).
- **Reset:** the arm resets at the open (1265) and at each add (1348).

**Live ladder location:**
- Decision: strategy.py 277-288 (BUY) / 299-310 (SELL), RSI-level tiers hard-coded by count; gate 249-250.
- Lot: app.py 739 / 779 (`_get_next_fibo_volume`, Fibonacci: the first add is 2 units) and strategy.py 39-65.
- Post-add sleep: app.py 751 / 791.

**Missing at that spot:**
1. **MACD votes for the tier TFs.** They exist only for `SLOPE_TIMEFRAMES` (app 593). M5 is fetched (it is in `rsi_tf_list`) but gets **no MACD or slope** computation, and M5 is not in `slopes`.
2. **Cross-poll arm state.** `Strategy` is stateless, and `process_symbol` has no slot for it.
3. **Last fill price.** Not exposed: `get_*_positions` returns no `price_open`, even though `last_pos` (mt5_helper 67) carries it.
4. **Vol unit and size.** The vol unit snapshot (4b) is missing too. The add size is hard-wired to Fibonacci with `/100`, and the max-adds limit is implicit (5 tiers, `count == 1..5`).

---

## 5. Constraints from the backtest harness that a port runs into

These matter if the port is to be replayed through `engine/reference.py` for parity, as the existing hedging pipeline was.

- **`_apply_config` patches module globals** (reference.py 407-462):
  - `strategy.ENTRY_S/ENTRY_AGREE_S/LADDER_S/FORCE_CLOSE_S/RSI_*`, the weight dicts, `app.SLOPE_TIMEFRAMES` (re-derived from open+fc(+book) weights only, line 455), `app.RSI_LENGTH/MACD_*/PEAK_*/RSI_PEAK_*/REENTRY_COOLDOWN_SECONDS/ORDER_COOLDOWN_SECONDS/MARKET_LOOKBACK_MINUTES`.
  - It **raises** for hedging when `target_usd_per_unit != 1.0` (414), when the ladder is not M1..H4 Fibonacci (416-419), when `max_adds < 5` or `not force_close_enabled` (423-428), and for other levers.
  - So **none of the six target designs can run through the reference engine today**. It also does not look at `trend_tf`, `loss_cooldown_s`, `vol_*` or `ladder_trigger`.
  - A new constant would not be patched by it, and an M5 slope TF for the ladder would be dropped by line 455.
- **The `SimMT5` API surface is narrow:**
  - `symbol_info()` returns only `name, visible, select, trade_mode` (263-266). There is **no `trade_contract_size`**.
  - `positions_get()` returns `ticket, type, volume, price_open, symbol, profit, time (s), swap` (310-320). There is **no `magic`/`comment`**.
  - `history_deals_get()` returns `()` (306-307).
  - `copy_rates_from_pos` supports only `start_pos=0` (292-293).
  - `copy_ticks_from` returns None.
  - **Effect:** port code that touches anything else raises inside `process_symbol`, gets swallowed by `except Exception` (app 840-844), and the reference run silently never trades.
- **Bars in the simulator** are built from Bid ticks with the forming bar included, the same as live `copy_rates_from_pos(..., 0, n)`. A new bar appears only with its first tick, in both MT5 and the kernel, so "last closed = `iloc[-2]`" is consistent.

---

## 6. Facts relevant to the Turtle rows (bar-level, `research/external.py`)

- **"+ bot votes":** the entry is taken only when **both M15 votes agree on CLOSED M15 bars** (`BotSignals.m15_agree`, external.py 314-352, via `analysis.signal.votes`). The live `fc_score == ±2` (`ENTRY_AGREE_S=2`) is the same idea read on the **forming** bar.
- **The rest:**
  - D1 Donchian 20/55 entries; 10/20-day exits.
  - 2N ATR stop; adds every ½N up to 4 units.
  - Sized by the bot's unit rule.
- **Live loop gaps:** none of this machinery exists in the live loop.
  - D1 is not fetched. The fetch list is M1, M5, M15, M30, H1, H4, H6. With 500 bars, a D1 fetch would cover a 55-day window.
  - No stop or breakout orders: the live code sends only market deals.
  - No ATR.
