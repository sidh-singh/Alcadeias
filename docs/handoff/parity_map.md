# Verifying a port: the reference replay, `BacktestConfig.live`, the parity check, and what a new branch has to change

> **About this file.** This note was added on 16 Nov 2026, when the map was saved into the repo with `HANDOFF.md`.
> - **What it is.** How the Alcadeias parity harness works: the reference engine that runs a branch's own `app.py` against a simulated MT5 terminal, what `BacktestConfig.live()` reads, what `engine/parity.py` compares and with which tolerances, how long it takes, the port rules that keep parity reachable, and the smallest reliable check for a new branch. It was written for the demo port and is the best template for a parity harness against a simulated Fyers API.
> - **When.** Written on 15 Nov 2026, about 17:44 IST, by an assistant session that worked read-only.
> - **What it describes.** `backtest_hedging` at `9e4c71f` / `0ae5794`, and the live files of `origin/hedging_xauusd6` at `1ed2d6c`.
> - **Out of date.** Most of the gaps this map lists were closed the same evening in commit `c61c998` (15 Nov 2026, 18:51 IST); commit `bed551e` re-stamped the 7 hedging reports.
>   - The simulated terminal now serves magic numbers and comments (refusing comments over 31 characters), position identifiers and times, `history_deals_get`, `symbol_info` with contract size, digits and volume limits, closed-bar reads from any position, `copy_rates_range`, partial closes, and an account shared with other bots. It stores SL/TP but never executes them, and answers pending orders "invalid".
>   - `_apply_config` pushes every lever into every live module for a branch whose `constants.py` defines the demo contract, and refuses levers that neither the bot nor the contract has. For the old live root it still silently accepts levers such as `trend_tf` that the live code lacks (§1.5).
>   - `compare()` compares only the ladder tiers the kernel writes, so `max_adds = 0` and repeated tier timeframes no longer fail.
>   - New live modules are removed after a replay, and every clock reading (`time`, `perf_counter`, `monotonic`, `datetime.now`) is simulated.
>   - `reference.contract_overrides` maps a demo branch's constants for the CLI; `config.py` was left unchanged.
>   - `backtesting/engine/demo_parity.py` is new.
>   - The parity fingerprint in "Facts checked" (`80ad49a1b54e`) was replaced by `7b59f45b82ec` in `bed551e`.
>   - The `reference.py`, `parity.py` and `cli.py` line numbers here match `git show 0ae5794:<file>`, not the current files. `kernels.py`, `fast.py` and `config.py` are unchanged, so their line numbers still hold.
>   - `compare()` has two new options since `c61c998` (`parity.py` L95-105, L136-146, L197-207). `check_entry_allowed` compares the cooldown and loss-pause state (`entry_allowed`) at every poll; `demo_parity` always sets it. `blocked_entries_ok` accepts a poll where the branch's strategy holds back an entry that the kernel holds back at execution, provided the fills still match; it is `demo_parity`'s default and `--strict-gates` refuses it (`demo_parity.py` L346). So §0 item 6 and §3 ("`entry_allowed` is recorded but not compared") describe `0ae5794`.
>   - §6 rule 8's "no broker-side SL/TP" was replaced in the demo port by a backstop further out: every basket fill sends `sl` = the decision quote ∓ 2 × the basket's stop distance, with no `tp` (`1c3f434`), and every Turtle leg gets an `sl` 1 N beyond the trade's stop (`cad41e9`). Parity is unaffected: SimMT5 stores `sl`/`tp` but never executes them, and the bot's own stop always comes first (`HANDOFF.md` §5.9 item 8).
>   - §1.4's "(no break on BTC)" was wrong. The market-closed and close-only rules follow any silence of 30 min or more, on both symbols, and BTC has such silences: about 80 of 30 min to 3 h in 2018 – 2025, e.g. 2-hour weekend pauses in 2018 and 141 min on 5 Feb 2022 (`HANDOFF.md` §3.2).
> - **Scratch files.** The probe scripts, the parity scripts (`parity_final.py`, `parity_recheck.py`, `parity_run2.py`, `parity_queue.sh`, `parity_one.sh`, `parity_rerun_all.sh`), `scratchpad/devclone`, `parity_final/progress.log` and the recordings `parity_final/*.ref.pkl` (14 files: 7 hedging, 7 netting; 109 MB) live in a temporary session folder, `/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/scratchpad/`, which is not part of the repo. They were all still there at about 03:50 IST on 16 Nov 2026 (the first version of this note said they were gone), but a reboot or a clean-up can delete them. The 7 hedging reports are committed as `backtest_results/parity/*.json`.
> - **No credentials.** `mt5_credentials.json` was never opened; the replay never reads it (§1.1).

Scope: read-only study of `backtest_hedging` at `9e4c71f` / `0ae5794`. A concurrent session committed `0ae5794` (balke research) while this was written. That commit touches no engine, config, reference or parity file, so every line number below still holds. Live code comes from `git show origin/hedging_xauusd6:<file>`.

Facts checked before starting:
- **Live code is the same across the n=6/7/8 branches.** `origin/hedging_xauusd6/7/8` and `origin/hedging_btcusd6/7/8` have no diff in `app.py strategy.py indicator.py mt5_helper.py constants.py symbols.json start_job.bat requirements.txt`. Only `mt5_credentials.json` differs (not opened; it has 'demo' and 'live' keys).
- **xau6 and btc6 behave the same.** They differ only in docstrings, the `--symbol` help text, a candidate list in `_get_server_time` (mt5_helper.py:720), `symbols.json` (symbol name and trading window) and the `start_job.bat --symbol`.
- **The root of this checkout is xau6.** The live files at the root of `backtest_hedging` are byte-identical to `origin/hedging_xauusd6`, so `REPO_ROOT` is a valid `live_root` for both symbols.
- **Fingerprints are current.** `experiments.parity_fingerprint()` = `80ad49a1b54e` and `live_fingerprint(REPO)` = `ff2eb10cc257`. They equal the stamps on the 7 committed hedging parity reports (`backtest_results/parity/*.json`).

Probe scripts (all read-only; numba cache redirected to the scratchpad, `python3 -B`) are in a folder
`map_parity_check/` of the session's temporary scratch folder, which is not part of the repo; they were still there at about 03:50 IST on 16 Nov 2026 but can be deleted at any time:
`check_guards.py`, `check_timing.py`, `find_windows.py`, `confirm_windows.py`, `scaled_grid.py`.

---

## 0. The short version

1. **What the reference engine is.** `engine/reference.py::run_reference` imports the branch's own `app.py` from `live_root`, together with `strategy`, `indicator`, `mt5_helper` and `constants`, with `sys.modules["MetaTrader5"]` replaced by a `SimMT5` instance.
   - It patches `app.time`, `mt5_helper.time` and `mt5_helper.datetime` with a simulated clock.
   - It overwrites the *module-level* constant names in `strategy` and `app` from the `BacktestConfig` (`_apply_config`).
   - It then runs the untouched `MT5TradingBot.process_symbol`, recording one trace row per loop pass.
2. **What `BacktestConfig.live(symbol, repo_root)` reads.** It executes `<repo_root>/constants.py` under a private module name and reads 20 fixed names, plus `BOOK_*` for netting. The hedging target is **hard-coded to $1 × unit** (config.py:420). It also reads sizing and the trading window from `symbols.json`. **Any new constant is ignored** unless `live()` is extended.
3. **What `engine/parity.py::compare` checks.** At every *fresh* poll, with no tolerance on timing:
   - poll timestamps, the signal, the open / fc / book scores, the ladder RSIs, the signed position count, the floating profit and the unit;
   - then every fill (in/out, side, lots, price, P/L, decision time within 1.5 s), the final balance, and that the live code logged no errors.
4. **Today the reference refuses every design.** V3-lite and Top 1/2/3 are all refused by `_apply_config` (first hit: "the live hedging target is fixed at $1 x unit"). Meanwhile `trend_tf`, `loss_cooldown_s`, `vol_tf/target_vol/stop_vol`, `ladder_trigger`, `entry_rsi_block_tfs`, `fc_rsi_tfs`, `entry_max_spread`, `daily_loss_limit…`, `agree_weights` and `trail_*` are **silently accepted** although the live code has none of them. "Owner's rules + H1 trend + 4 h pause" is accepted outright.
5. **`compare()` has two defects that bite these designs.**
   - It iterates the ladder RSI over all of `cfg.ladder_tfs`, but the kernel writes only `n_ladder_adds` columns: with `max_adds=0` (V3-lite, all BTC Tops) the fast columns are 0 and RSI parity fails.
   - With the gold Top 1/3 `ladder_tfs=["M5","M15","H1","H1","H1"]`, the reference trace gets duplicate column names and `compare()` raises `ValueError` (operands could not be broadcast).
6. **Where a new rule sits decides whether the signals can match.** The kernel's trace signal is written **before** its execution-time entry filters (brake, trend, spread, RSI block, hours, regime …), kernels.py:1156-1172 against 1202-1247. The live trace records `strategy.calculate_signal`'s status.
   - A trend gate placed **inside strategy.py** gives "signal mismatches" although the fills agree.
   - The gate must sit in `app.py` next to the brake check, or the kernel must record the post-filter signal. (Since `c61c998`, `compare(..., blocked_entries_ok=True)` also accepts such a poll if the fills still match; see the note at the top.)
7. **Cost.**
   - Live code: **11.9 ms per live poll** single-process on this machine (20 min of gold took 14.3 s), so **~16-17 min per 24 h of ticks**.
   - With 3 in parallel under `nice`, the stored 24 h windows took 24-35 min.
   - Closed-market passes cost about 1 ms each.
   - The fast engine takes 0.01 s for 20 min after a ~15 s numba compile.
8. **The smallest reliable check is (i) to (iv) below.**
   - (i) `live(new branch)` equals `live(xau6, **design)`, confirmed by identical fast-engine fills (seconds).
   - (ii) Characterization unit tests of the new rules (ms).
   - (iii) One parity replay per symbol on the bundled fixture windows with **scaled-down** design parameters that fire every new rule (validated below; 45-60 min of ticks, 30-45 s each).
   - (iv) One real-parameter window per design on the full store (11-31 min each; windows listed in §7).
   - The real designs take **no trade** in the existing fixture windows (V3-lite gold: 0 fills in 45 min), so the current `tests/test_parity.py` would fail on `min_fills` for a ported branch.
9. **The Turtle rows cannot be checked this way.** "Turtle + bot votes" and "Turtle System 2 + bot votes" exist only in `research/external.py`'s M1-bar simulator. There is no kernel implementation and `SimMT5` has no pending orders or SL/TP, so poll-by-poll parity cannot verify a Turtle port (§8.5).

---

## 1. `engine/reference.py`: how a branch's `app.py` is run

### 1.1 Loading the live modules: `live_code()` (reference.py:367-390)

```python
_LIVE_MODULES = ("MetaTrader5", "constants", "strategy", "indicator", "mt5_helper", "app")   # line 367

@contextmanager
def live_code(live_root: Path, sim: SimMT5):
    root = str(Path(live_root).resolve())
    saved = {n: sys.modules.get(n) for n in _LIVE_MODULES}
    for n in _LIVE_MODULES:
        sys.modules.pop(n, None)
    sys.modules["MetaTrader5"] = sim          # `import MetaTrader5 as mt5` in app.py binds the SimMT5 instance
    sys.path.insert(0, root)
    try:
        import app                             # pulls strategy, indicator, mt5_helper, constants from live_root
        yield types.SimpleNamespace(**{n: sys.modules[n] for n in _LIVE_MODULES if n in sys.modules})
    finally:
        ... remove root from sys.path, pop the six modules, restore the saved ones
```

- **Only six module names are isolated.** A new live module (e.g. `filters.py`) would be imported from `live_root` but **not popped afterwards**. A second `run_reference` in the same process with another `live_root` would silently reuse it. It is also invisible to `_apply_config`. Add any new file to `_LIVE_MODULES` and to `experiments._LIVE_FILES` (experiments.py:95, the live fingerprint).
- **`mt5_credentials.json` is never read.** `load_credentials`, `load_symbols`, `initialize_mt5` and `execute_job` are not called; the bot is assembled by `_new_bot()` (§1.3).

### 1.2 What is patched (reference.py:537-555)

```python
with live_code(live_root, sim) as mods:
    _apply_config(mods, cfg)                       # 538: constants -> module globals (see 1.5)
    app, helper_mod = mods.app, mods.mt5_helper
    class _SimDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(clock.now_ms / 1000.0, tz=tz or timezone.utc)
    helper_mod.datetime = _SimDatetime             # 546: mt5_helper's datetime.now() (get_market_status, ...)
    helper_mod.time = clock                        # 547: sleep(0.1) in buy()/sell()
    app.time = clock                               # 548: loop sleep(1), sleep(ORDER_COOLDOWN_SECONDS), time.time() cooldown
    ...
    app.print = _print                             # 550-555: keeps lines containing "Error:" / "WARNING" as ref.errors
```

- **`SimClock` (reference.py:69-89).** It implements only `time()`, `perf_counter()` and `sleep()`.
  - `sleep()` advances `now_ms` and raises `_End` at `cfg.end`, or `_Restart` at a scheduled restart. Both are `BaseException`, because `process_symbol` swallows every `Exception`.
  - **Time advances only through sleeps.** Work takes no simulated time; the per-pass sleep is 1 s (app.py:834 `time.sleep(max(brake, 1))`).
  - On top of that come 0.1 s inside `buy()`/`sell()` (mt5_helper.py:510/528) and `ORDER_COOLDOWN_SECONDS` = 1 s after every add (app.py:751/791).
- **Not patched**, so it reads the real wall clock or fails:
  - `datetime` in `app.py`, which is a *local* `from datetime import datetime` in `process_symbol` (app.py:448; used only for `last_updated`);
  - any clock in `strategy.py`, `indicator.py` or a new module;
  - `time.monotonic()` and the other `time` functions SimClock lacks: AttributeError, caught by the loop, printed as "Error:", counted in `ref.errors`, and parity fails.

### 1.3 The bot object and the loop (reference.py:560-627)

```python
def _new_bot():                                                   # 560
    bot = app.MT5TradingBot(mode="demo", target_symbol=cfg.symbol)
    bot.symbols_config = {"brake": 1 if cfg.brake else 0, "mtqty": cfg.mtqty,
                          "trading_window": {"enabled": bool(cfg.window_enabled), "start_day": sd, "start_time": st,
                                             "end_day": ed, "end_time": et},
                          "symbols": [{"symbol": cfg.symbol, "is_active": True,
                                       "step_up_balance": cfg.step_up_balance, "unit_max_limit": cfg.unit_max_limit}]}
    bot.symbols = [cfg.symbol]; bot.symbol_configs = {...}; bot.symbol_map = {cfg.symbol: cfg.symbol}
    bot.position_helper = helper_mod.MT5PositionHelper(sim); bot.mt5_initialized = True
    bot._save_symbol_data = _save_symbol_data                     # 575: the trace hook
    bot._save_account_data = bot._save_daily_trades = bot._save_historical_summary = no-op   # 576-578
    bot._log_event = _log_event                                   # 579: events list in memory
```

- **`symbols.json` on disk is not used by the replay.** The window and sizing come from `cfg` (built by `BacktestConfig.live`), not from the file.
- **New persistence must be stubbed.** Any new persistence a port adds (a state file for the loss pause or the frozen volatility, a read of `active_config.json`) would run for real. `OUTPUT_DIR = r'C:\Alcadeias'` on macOS creates a relative `C:\Alcadeias` directory. Stub it in `_new_bot`.
- **The loop and restarts.** The loop is `_new_bot().process_symbol(cfg.symbol)`; on `_Restart` a fresh bot takes over (in-memory state lost, positions kept); on `_End` it stops (reference.py:617-627).
- **The iteration timestamp.** `sim.symbol_select` is wrapped so the *first MT5 call of a pass* (app.py:487 `mt5.symbol_select(...)`) stamps `state["iter_t"]` (reference.py:583-589). A port must keep `symbol_select` as the first call of each pass.

### 1.4 `SimMT5`, the simulated terminal (reference.py:143-364)

- **Data.** Ticks `t_ms`/`bid`/`ask` for `[start, end)` (or the per-second series with `mode="sec"`).
  - Bars of **all 14 timeframes** are grown tick by tick from the bid on UTC buckets, forming bar included (`_Bars.on_tick`, 114-130).
  - They are seeded with the last 600 bars resampled from M1 history. `run_reference` loads M1 from `start - 600 × 86400 s × 1.7` (≈ 2.8 years, bounded by the store; reference.py:503-506).
- **Calls served.** `copy_rates_from_pos` (pos 0 only), `copy_rates_from` (`upto_t`), `symbol_info_tick` (latest tick ≤ clock; `time` in whole seconds), `positions_get` (ticket, type, volume, price_open, symbol, profit rounded to cents per position, time in seconds, swap 0), `account_info` (balance, equity, margin, margin_free, margin_level, profit).
- **Orders (`order_send`, 322-364).** Market deals only.
  - A buy fills at the ask and a sell at the bid; a close (request with `position`) fills at bid/ask and books `_round2` P/L.
  - Refusals: "market closed" when the quote is the last before a gap of 30 min or more and is more than 1 s old; "close-only" for 90 s / 210 s after a break, i.e. any silence of 30 min or more / of a day or more, on both symbols (BTC has such silences too, e.g. about 2-hour weekend pauses in 2018 and 141 min on 5 Feb 2022); "no money" when the free margin cannot carry the order.
  - Every fill is appended to `sim.deals`.
- **Missing (relevant to ports).**
  - `history_deals_get` returns `()` (306-307).
  - `copy_ticks_from` returns `None`.
  - `symbol_info` has only `name, visible, select, trade_mode` (263-266): no `trade_contract_size`, `volume_min`, `point`, `digits`.
  - The request's **`sl`/`tp` are ignored**, and there are no pending orders, `orders_get`, SLTP modification, `comment` or `magic` on positions.

### 1.5 How the constants reach the live code: twice, made equal by `_apply_config` (reference.py:407-462)

1. **For the configuration.** `BacktestConfig.live(repo_root=...)` reads `constants.py` through `load_live_constants` (§2).
2. **For the live code.** The live modules do `from constants import NAME`, which **binds NAME in the importing module** (strategy.py:2-8, app.py:13-27). Patching `constants.NAME` afterwards has no effect on them.
3. **What `_apply_config` does about it.** It overwrites those module globals in `strategy` and `app` with the cfg values. That works only because the live code reads them at call time; `tests/test_live_strategy_characterization.py::test_thresholds_are_read_at_call_time…` pins this.

Pushed (444-462):

| Module | Names set from cfg |
|---|---|
| `strategy` | `ENTRY_S, ENTRY_AGREE_S, LADDER_S, FORCE_CLOSE_S, RSI_OVERSOLD, RSI_OVERBOUGHT, OPEN_SCORE_WEIGHTS, FORCE_CLOSE_SCORE_WEIGHTS` (+ netting `BOOK_S, BOOK_SCORE_WEIGHTS, PROFIT_PROTECT_USD_PER_UNIT`) |
| `app` | `SLOPE_TIMEFRAMES` (= `"TIMEFRAME_"+tf` for the **union of the open/fc(/book) weight keys only**, line 449-455), `RSI_LENGTH, MACD_FAST, MACD_SLOW, MACD_SIGNAL, PEAK_LOOKBACK, PIVOT_WIDTH, RSI_PEAK_OB, RSI_PEAK_OS, REENTRY_COOLDOWN_SECONDS, ORDER_COOLDOWN_SECONDS (= add_order_delay_ms/1000), MARKET_LOOKBACK_MINUTES` |

Guards (410-443), which raise `ValueError` before anything is pushed:
- the variant must match (hedging/netting by `hasattr(strategy, "BOOK_SCORE_WEIGHTS")`);
- hedging `target_usd_per_unit` must be 1.0 (414-415);
- ladder tiers must be exactly M1/M5/M15/H1/H4 and enabled (416-417), and the multipliers must start 1,2,3,5,8,13 (418-419);
- no `slope_on_closed_bars` / `ladder_on_closed_bars` (420-422);
- none of `min_hold_s, fc_confirm_s, entry_confirm_s, ladder_min_gap, ladder_min_interval_s, max_hold_s, target_per_lot, stop_loss_usd_per_unit, entry_hours_utc`, nor `allow_long/short` off, `max_adds < 5`, `fc_grey_fill`, `open_grey_fill` off or `force_close_enabled` off (423-428);
- no extra costs or latency (429-430); `poll_interval_ms == 1000` and no jitter (431-432); `open_order_delay_ms` in {0, 100} (433-434); netting constraints (435-438); `stop_out_level == 0` (439-440); no `fixed_units` (441-442).

**The guards are stale.** `reference.py` was last changed in `c126ac2` (2026-11-14), before the trend filter, loss pause, spread cap (`ddc17e6`), ladder triggers and volatility units (`4a9215f`), owner's rules (`369c75c`) and regime (`9e4c71f`). Probe output (`check_guards.py`):

```
XAUUSDm  V3-lite / Top 1 / Top 2 / Top 3          -> REFUSED: the live hedging target is fixed at $1 x unit (close_threshold=units)
BTCUSDm  V3-lite / Top 1 / Top 2 / Top 3          -> REFUSED: (same)
X/B      Owner's rules + H1 trend + 4 h pause     -> ACCEPTED   (live code has no RSI block, RSI force-close, trend, loss pause)
XAUUSDm  {"trend_tf": "H1"} / {"loss_cooldown_s": 43200} / {"vol_tf": "H1", "target_vol": 8} / {"vol_tf": "H1", "stop_vol": 8}
         / {"entry_max_spread": 0.3} / {"ladder_trigger": "macd_turn"} / {"entry_rsi_block_tfs": [...]} / {"fc_rsi_tfs": [...]}
         / {"daily_loss_limit_usd_per_unit": 5} / {"agree_weights": {"H1": 1}} / {"trail_gap_usd_per_unit": 2}  -> ACCEPTED (silently ignored)
XAUUSDm  {"max_adds": 0} / {"force_close_enabled": false}  -> REFUSED: experimental levers are not part of the live code
```

**A false pass is possible.** On a window where such a lever never binds (no trend flip, no losing basket), `check_parity` would report OK for a rule the live code does not have.

### 1.6 The trace (reference.py:593-608, columns 631-632)

```python
def _save_symbol_data(symbol, data):        # replaces bot._save_symbol_data; called once per pass (app.py:819)
    an = data.get("analysis", {}); sig = data.get("signal", {})
    code = _SIG[sig.get("buy_status", "DO_NOTHING")] or _SIG[sig.get("sell_status", "DO_NOTHING")]
    pos = data.get("positions", {}); nb, ns = pos["buy"]["count"], pos["sell"]["count"]
    pr = buy total_profit if nb else sell total_profit
    rsi = an.get("rsi_mtf", {})
    trace_rows.append((state["iter_t"], code, an["candle_fresh"], an["open_score"], an["fc_score"], an.get("book_score", nan),
                       nb - ns, pr, an["unit_times"], an["entry_allowed"], *[rsi.get("TIMEFRAME_"+tf) for tf in cfg.ladder_tfs]))
cols = ["t_ms", "signal", "fresh", "open_score", "fc_score", "book_score", "n_pos", "profit", "units", "entry_allowed"] \
       + [f"rsi_{tf}" for tf in cfg.ladder_tfs]          # duplicate names if ladder_tfs repeats a timeframe
```

- **The signal is the strategy's wish.** It is `strategy.calculate_signal`'s status (app.py:647-655), recorded **before** app.py's brake check (app.py:725-737: a braked BUY stays "BUY" in the trace).
- **Scores are rounded.** They come from `analysis_data`, rounded to 1 decimal (strategy.py:318-319). That is exact only for integer (or 0.5) weights.

### 1.7 Window set-up (reference.py:499-530)

- **Where the clock starts.** It starts at `start`, or at the first 1 s grid point that can see a tick (as the fast engine does).
- **`after_ms`.** This is the time of the next quote after `end` (`fast._next_quote_ms`), so the window's last quote can count as a session end.
- **Close-only carried in.** A close-only period still running at `start` is inherited from the silences in the warm-up (`fast._silences`).

---

## 2. `BacktestConfig.live(symbol, repo_root=...)` (config.py:388-423)

```python
@classmethod
def live(cls, symbol="XAUUSDm", repo_root=REPO_ROOT, **overrides):
    c = load_live_constants(repo_root)                         # 391
    is_netting = hasattr(c, "BOOK_SCORE_WEIGHTS")              # 392
    kw = dict(symbol=symbol, variant="netting" if is_netting else "hedging",
              rsi_length=c.RSI_LENGTH, macd_fast=c.MACD_FAST, macd_slow=c.MACD_SLOW, macd_signal=c.MACD_SIGNAL,
              peak_lookback=c.PEAK_LOOKBACK, pivot_width=c.PIVOT_WIDTH,
              rsi_peak_ob=float(c.RSI_PEAK_OB), rsi_peak_os=float(c.RSI_PEAK_OS),
              open_weights=dict(c.OPEN_SCORE_WEIGHTS), fc_weights=dict(c.FORCE_CLOSE_SCORE_WEIGHTS),
              entry_s=float(c.ENTRY_S), entry_agree_s=float(c.ENTRY_AGREE_S),
              ladder_s=float(c.LADDER_S), force_close_s=float(c.FORCE_CLOSE_S),
              rsi_oversold=float(c.RSI_OVERSOLD), rsi_overbought=float(c.RSI_OVERBOUGHT),
              ladder_tfs=[t.replace("TIMEFRAME_", "") for t in c.RSI_DCA_LADDER_TIMEFRAMES],
              reentry_cooldown_s=float(c.REENTRY_COOLDOWN_SECONDS),
              add_order_delay_ms=int(c.ORDER_COOLDOWN_SECONDS * 1000),
              market_lookback_s=float(c.MARKET_LOOKBACK_MINUTES * 60))        # 393-409
    if is_netting:
        kw.update(book_enabled=True, book_weights=dict(c.BOOK_SCORE_WEIGHTS), book_s=float(c.BOOK_S),
                  profit_protect_usd_per_unit=float(c.PROFIT_PROTECT_USD_PER_UNIT), target_usd_per_unit=None)  # 410-417
    else:
        # app.py passes close_threshold=units -> the target is $1 of basket profit per unit.
        kw.update(book_enabled=False, target_usd_per_unit=1.0)                 # 418-420  HARD-CODED
    kw.update(_symbols_json(symbol, repo_root))                                # 421
    kw.update(overrides)                                                       # 422 (explicit overrides always win)
    return cls(**kw)                                                           # 423 (__post_init__ validates)
```

- **`load_live_constants(repo_root)` (config.py:478-498).** It resolves `<repo_root>/constants.py` and executes it with `importlib.util.spec_from_file_location` under the private name `_alcadeias_live_constants_<sha1(path)[:10]>`. The result is cached by `(path, st_mtime_ns)`, so several checkouts can be read in one process, whatever `sys.path` holds.
- **`_symbols_json(symbol, repo_root)` (config.py:450-472).** It reads `mtqty`, `brake`, and the symbol entry's `step_up_balance` and `unit_max_limit`, plus `trading_window`, converted to week-minutes with the bot's own arithmetic (`_week_minutes`, 431-438).
  - If the file lacks the symbol, it falls back to the first entry's sizing and `_FLEET_WINDOWS[symbol]` (444-447: gold Mon 01:00-Fri 22:00, BTC Mon 00:00-Sun 23:59).
  - That is how the hedging BTC parity windows ran against this XAU checkout.
- **Not read from the code.**
  - Ignored constants: `RSI_MA_TYPE` (RMA assumed), `RSI_CANDLE_COUNT` (500; the engine warms on 600), `RSI_MTF_TIMEFRAMES`, `RSI_FINAL_CLOSE_TIMEFRAME`, `CANDLE_*`, `FIBO_SEQUENCE_LENGTH` (the `FIBO` default list equals `fib[2:]`), `STRATEGY_HEDGE`, `PROFIT_PROTECT_MIN_USD`, `RISK_REWARD_RATIO`.
  - Fixed in the backtester, not derived: the 0.1 s order sleep (`parity.LIVE_OPEN_ORDER_DELAY_MS = 100`, cli.py:62) and the 1 s pass (`poll_interval_ms` default).
- **Every newer field stays at its "off" default.** Today a branch's `TREND_TF`, `LOSS_COOLDOWN_…`, `TARGET_VOL`, `MAX_ADDS` and the like would be ignored. For this checkout `live("XAUUSDm")` gives:
  - `open {'H1':(1,1),'M15':(1,1)}`, `fc {'M15':(1,1)}`, entry/agree/ladder/fc thresholds `2/2/2/1`, `target_usd_per_unit 1.0`;
  - `ladder_tfs M1..H4`, `ladder_multipliers FIBO`, `max_adds 99`;
  - `trend_tf None`, `vol_tf None`, `target_vol 0`, `stop_vol 0`, `loss_cooldown_s 0`, `reentry 300 s`, `add_order_delay_ms 1000`, `market_lookback_s 180`;
  - window `60 → 7080` min, `mtqty 0.01`, `step_up 2500`, `unit_max 10`.

---

## 3. `engine/parity.py`: what must match

`fast_config_for_parity(cfg)` (71-79) = `cfg.replace(open_order_delay_ms=100, data_hole_s=0.0)`: the live helper's 0.1 s sleep, and no BTC data-hole handling (the live code never meets a hole). Broker rules stay as configured; SimMT5 applies the same ones.

`check_parity(cfg, live_root, mode="ticks", store_dir, progress)` (188-197): `run_reference(cfg, live_root, …)`, then `fast.prepare(fcfg.symbol, start, end, fcfg.timeframes(), mode)` and `fast.run(fcfg, prep, trace=True, warn_off_grid=False)`, then `compare(cfg, ref, fast)`. **It has no `regime` argument** (`fast.run(..., regime=...)` exists for the V3-lite hybrids).

`compare(cfg, ref, fast, rsi_tol=1e-6, score_tol=1e-9, money_tol=0.0051)` (82-185):

| What | How (parity.py lines) | Tolerance |
|---|---|---|
| polls | `rt = ref.trace[ref.trace["fresh"]]` (live passes where `market_status.is_open`) vs every kernel trace row (the kernel traces live polls only); count must be equal (96-97) | exact |
| cadence | `t_ref != t_fast` → "cadence diverges at poll i", and **everything after is ignored** (93-101) | exact ms |
| signal | `rt.signal` vs `ft[:, T_SIGNAL]` at every poll (103-110) | exact |
| scores | open / fc / book; a column that is all NaN is skipped (book on hedging) (112-121) | 1e-9 |
| ladder RSI | `for q, tf in enumerate(cfg.ladder_tfs): rt[f"rsi_{tf}"] vs ft[:, T_RSI0+q]` (123-132) | 1e-6 |
| n_pos (signed), floating profit, unit | (134-141) | 0 / $0.0051 / 0 |
| fills | count; then deal i vs fill i: out/in, type/side, volume, price (1e-9), P/L ≤ $0.0051, decision time ≤ 1500 ms (143-169) | as stated |
| final balance | `abs ≤ max(0.0051, 0.0051 × n_deals)` (171-173) | |
| live-code errors | `ok` requires `not ref.errors` (177) | none allowed |

- **`entry_allowed` is recorded but not compared**, and nor are `T_ENTRY_ALLOWED` and `T_BRAKE` of the kernel trace. (At `0ae5794`. Since `c61c998`, `compare(..., check_entry_allowed=True)` compares `entry_allowed` with `T_ENTRY_ALLOWED`, and `demo_parity` always sets it; `T_BRAKE` is still not compared.)
- **Kernel trace semantics** (kernels.py:1156-1172; columns 266-279, `T_N = 18`, at most 6 ladder RSIs):
  - The row is written after the exits, the cooldown (incl. `loss_cooldown_s`, 1014) and the ladder decision.
  - It is written **before** the execution-time entry filters at 1202-1247: brake → data-hole quarantine → allow_long/short → **regime** → **trend** → spread cap → volatility unknown → daily loss → RSI block → hours → confirm → market closed / close-only.
  - The trace therefore says BUY while the order is blocked, exactly like a braked live BUY.
- **The kernel writes only `n_ladder_adds` RSI columns.** The loop is `for q in range(n_tiers)` (1169-1171); the rest stay 0. Probe: V3-lite on the gold fixture shows all 5 columns zero, `n_ladder_adds=0`.

---

## 4. How the scripts and tests run it

- **`parity_final.py`** (scratchpad):
  - `names` lists `parity_final/*.ref.pkl`.
  - `recheck <code_root> [--write]` loads each pickle (trace, deals, events, balances, overrides, symbol, live_root). It rebuilds `cfg = BacktestConfig.live(symbol, repo_root=root, **overrides)`. Here `root` is `<code_root>` for hedging windows and the recorded `netting_live` snapshot for netting (`live_root_of`, 24-27). It runs only the fast engine (`fast_config_for_parity` + `prepare(..., mode="ticks")` on the full store) and `compare()`s it with the **stored** live result, taking seconds per window. `--write` restamps the JSONs with `parity_fingerprint()` / `live_fingerprint(root)`.
  - `run <code_root> <name> <out_dir>` replays the live loop again (`run_reference`) and rewrites the pickle and JSON (20-35 min for 24 h).
- **`parity_recheck.py`** does the same recheck with `root = d["live_root"]` taken from the pickle (the repo, or `scratchpad/devclone`, whose six live files are identical to the repo's).
- **How the windows were produced.** `parity_run2.py` (run against `scratchpad/devclone`'s backtesting) and `parity_queue.sh` (3 at a time) produced the 7 hedging and 6 netting windows. `parity_one.sh` / `parity_rerun_all.sh` re-ran them on the final build.
- **What the windows cover.** The 7 hedging windows hold 373,614 live polls, all identical:
  - xau 24 h 2026-10-14, the weekend 10-16 → 10-19, the crash 2026-02-02 00:50-01:40;
  - btc 24 h 10-10 and 09-15, units3 12 h 08-20, altparams 12 h 09-22.
- **A recheck is a regression test of the engine, not of a new branch.** The stored traces are outputs of the *old* app.py. Rechecking with a new branch's root would compare the new design against old live behaviour and must fail. Run it with the xau6 root after any engine, compare or kernel edit.
- **Tests.**
  - `tests/conftest.py` puts `ALCADEIAS_LIVE_ROOT` (default: this repo) first on `sys.path`. `live_cfg(symbol, **ov)` = `BacktestConfig.live(symbol, repo_root=LIVE_ROOT, start/end=fixture window)`. The fixture store `tests/fixtures/store` holds XAU 2026-11-11 15:00-15:45 and BTC 2026-11-09 06:00-07:00, each with 12 days of M1 warm-up (built by `tests/make_fixtures.py`).
  - `tests/test_parity.py`: two 20-min windows; other settings on BTC (M5+M15 open, M5/M1 fc, shorter indicators); unit 3 ($5,200); per-second mode; and `-m slow` full fixture windows. `_assert_ok` requires `fills >= min_fills` (1, or 6 for the full windows).
  - `tests/test_account_and_broker_rules.py` adds parity across a gold session break and under margin refusals.
  - `tests/test_live_fault_injection.py` uses `run_reference(hook=…, restart_at=…)` and documents that a restart forgets the cooldown.
  - `tests/test_live_strategy_characterization.py` pins the live `strategy.py`, including `test_configured_thresholds_snapshot` (176-192, the constants themselves).
- **CLI.** `python -m backtesting parity --symbol X --start … --end … --live-root DIR [--set k=v] [--mode ticks] --out f.json` runs `check_parity` and stamps the JSON (cli.py:159-175, 337-342). `_live_root` only checks that `DIR/constants.py` exists (cli.py:79-87).

---

## 5. Time cost

| What | Time | Source |
|---|---|---|
| live loop, 20 min of gold (1,199 polls), one process | 14.3 s = **11.9 ms per poll**, so ≈ 16.5 min per 24 h of gold (82,800 polls) and ≈ 17 min for BTC (86,400) | `check_timing.py` (and `PARITY OK: 1,199 polls, 4 fills, balance 1997.38/1997.38`) |
| stored 24 h windows, 3 in parallel under `nice` | gold 1,449.6 s; BTC 1,933 s / 2,060 s; BTC 12 h 913 / 1,278 s; gold 57 h weekend 686.6 s (205,196 passes, only 28,764 live: a closed-market pass ≈ 1 ms, a live one ≈ 17 ms under that load); 50-min crash window 44.7 s | `parity_final/*.json`, `progress.log` |
| fast engine, same windows | ~15 s numba compile once, then 0.01 s per 20 min of ticks; three months per-second 1-3 s | probes / README |

---

## 6. Port rules that keep parity reachable

These rules apply to a V3-lite / Top 1-3 port. All the levers exist in the kernel already: trend 1015-1022/1217-1219, loss pause 1014/1461, volatility unit at the open 1274-1289, stop and target 1073-1079, `vol_cap` 1276-1277, `macd_turn` + `ladder_gap_vol` 1113-1117/1132-1136, `max_adds` → `n_tiers` (fast.py:287), `force_close_enabled` 1056/1060.

1. **Parameters are module globals read at call time.** Make them constants imported by name, never captured in default arguments, `__init__` or closures, or `_apply_config` cannot drive them.
2. **The trend is the sign of the trend timeframe's MACD signal line on the last *closed* bar.** That is `macd_df['signal'].iloc[-2]` of the H1 fetch (kernel `SG[off+K-1]`), *not* `iloc[-1]` (the forming bar, used for the MACD vote side at app.py:606). A signal of 0 or NaN blocks both sides (`want_side*trend*mode <= 0`).
3. **Put entry-only gates where the kernel puts them.** That covers trend, spread cap, RSI block, hours, regime and "volatility not known".
   - **Option A (recommended, no kernel change):** in app.py's order branch next to the brake: `if has_candle_data and candle_is_fresh and buy_signal == Signal.BUY: if not brake and <gates ok>:` (app.py:725-737 / 765-777), leaving `buy_signal` as the strategy's wish.
   - The loss pause belongs in `entry_allowed` (app.py:646), **before** `calculate_signal`, as in the kernel.
   - Exits (volatility target and stop) and adds belong in `strategy.calculate_signal`, because the kernel decides them before the trace row.
4. **The volatility unit.** It is `vol_array` (kernels.py:304-321): `v = |C1-C0|; v += (|Ck-Ck-1| - v)/vol_len`, taking the value of the last **closed** `vol_tf` bar (iloc[-2] of the closes).
   - It is measured **on the poll that sends the entry** and frozen for the basket's life. Optionally cap it: `v*contract*mtqty ≤ vol_cap_usd_per_unit`.
   - Basket target = `target_vol × v × contract × mtqty × unit` USD, closed when `profit > target` (**strict**). Stop = `stop_vol × …`, closed when `profit <= -stop` (**inclusive**). **The stop is checked before the target.**
   - `contract × mtqty` is 1.0 for XAU (contract 100) and 0.01 for BTC (contract 1). SimMT5's `symbol_info` has no `trade_contract_size`, so hard-code it in constants or extend SimMT5.
   - The live window holds 500 bars where the kernel uses 600+, so the seed difference is about (23/24)^475 ≈ 1e-9 relative. That is negligible, but in theory it can flip a threshold exactly at the boundary.
5. **The loss pause.** The basket counts as lost when its realised P/L is `< 0` (strict). In the replay the close fills on the same tick, so the floating `total_profit` at the close decision is equivalent. The pause counts from the close decision (`_last_close_time`, app.py:755/795).
6. **`entry_agree_s = 0` still means the agreement score must not oppose.** BUY needs `fc_score(M15) >= 0` and SELL `<= 0` (kernel 1005-1008). Keep `FORCE_CLOSE_SCORE_WEIGHTS={'M15':1}` as the agreement section even with `force_close_enabled=False`.
7. **The gold Top 1/3 add.** It is one add (`max_adds=1`) on tier 1 = M5, with `ladder_trigger='macd_turn'`.
   - It is *armed* once the M5 MACD vote is not with the basket on any poll that reaches the ladder branch since the last fill. It fires on the first such poll where the vote is with the basket.
   - It also needs `open_score > -LADDER_S` and a price at least `ladder_gap_vol × v_open` worse than the last fill (`last_fill - ask` for a buy).
   - Size = `1 × unit × 0.01` (multipliers `[1,1,1,1]`), **not** the Fibonacci `_get_next_fibo_volume` (that would give 2×).
   - M5 must be in the slope fetch. `_apply_config` must then put it into `a.SLOPE_TIMEFRAMES` (§8.2).
8. **No new sleeps, no `datetime.now()` or `time.monotonic()` in decision code, and no broker-side SL/TP that could act before the bot's own exits.** The cadence and the 1 s-poll stop model are what the kernel reproduces.
   - The demo port later added a broker-side backstop further out, which keeps parity: every basket fill sends `sl` = the decision quote ∓ 2 × the basket's stop distance, with no `tp` (`1c3f434`); every Turtle leg gets an `sl` 1 N beyond the trade's stop (`cad41e9`). SimMT5 stores `sl`/`tp` but never executes them, and in normal operation the bot's own stop always closes first.

---

## 7. The smallest reliable check (validated with the fast engine)

1. **The configuration maps (seconds).**
   - `BacktestConfig.live(sym, repo_root=<new branch dir>)` must equal `BacktestConfig.live(sym, repo_root=<xau6 dir>, **design_overrides)` on every field that is in effect.
   - Inert fields (ladder settings when `n_ladder_adds == 0`, `entry_rsi_block_mode` when there is no block TF) may differ.
   - Simplest proof: the fast engine gives **identical fills** for both configs over three months per-second (1-3 s).
   - Export the branch without credentials: `git archive <branch> app.py strategy.py indicator.py mt5_helper.py constants.py symbols.json | tar -x -C <dir>`. (On the Turtle branches add `turtle.py`, which their `app.py` loads at import, and `tests_demo/` for their tests; `HANDOFF.md` §0.2.)
2. **Characterization unit tests** of the new `strategy.py` rules with hand-made slopes and positions, like the existing characterization file (ms).
3. **Parity on the fixture store with scaled-down design parameters** (`scaled_grid.py`). The real designs open nothing in the fixture windows. `ALCADEIAS_LIVE_ROOT=<dir>`, `check_parity(live_cfg(sym, **ov), …)`, about 30-45 s per window:
   - **XAU 2026-11-11 15:00-15:45:** `open_weights={"M1":1}, fc_weights={"M1":1}, entry_agree_s=0.0, trend_tf="M5", force_close_enabled=False, max_adds=0, target_usd_per_unit=None, stop_loss_usd_per_unit=None, vol_tf="M1", vol_len=10, target_vol=2.0, stop_vol=2.0, loss_cooldown_s=240.0, reentry_cooldown_s=30.0`. Result: 3 baskets (2 target, 1 stop), trend blocked on 1,509 polls, cooldown on 297.
   - **BTC 2026-11-09 06:00-07:00:** the same, plus `max_adds=1, ladder_tfs=["M1","M5","M15","H1","H4"], ladder_multipliers=[1,1,1,1], ladder_trigger="macd_turn", ladder_gap_vol=1.0`. Result: 9 baskets (5 target, 4 stop), 2 adds, trend blocked on 1,275 polls, cooldown on 1,041.
   - Use `initial_balance` for the unit, not `fixed_units` (refused).
4. **One real-parameter window per design** on the full store (`confirm_windows.py`: started flat, raw ticks, parity cadence; minutes at 12 ms per live poll):

   | Design | Window (UTC) | What it holds | Replay |
   |---|---|---|---|
   | XAU V3-lite | 2026-10-28 17:00 → 10-30 14:00 | stop, then the 12 h pause, then target; trend blocked 12,290 polls | ~31 min |
   | XAU Top 1 / Top 3 | 2026-11-02 22:00 → 11-03 14:00 | target with the M5 MACD-turn add, then stop | ~11 min |
   | XAU Top 2 | 2026-10-21 06:00 → 10-22 14:00 | stop, then the 12 h pause, then target | ~22 min |
   | BTC V3-lite | 2026-10-01 14:00 → 10-02 18:00 | target, stop (no trend block) | ~20 min |
   | BTC Top 1 | 2026-10-08 12:00 → 10-09 06:00 | target, stop, trend blocked 2,190 | ~13 min |
   | BTC Top 2 | 2026-09-03 14:00 → 09-04 13:00 | target, stop | ~17 min |
   | BTC Top 3 | (choose another window: started flat at 10-08 13:00 its second basket is still open at 10-09 06:00) | | |

5. **Keep the old windows green.** `parity_final.py recheck <xau6 root>` must stay "ALL IDENTICAL" (seconds) after any engine or compare edit.

---

## 8. What has to change for a branch with new behaviour

Example: an H1 trend filter and volatility-based targets, controlled by new constants.

### 8.1 What the designs need

| Design | Overrides of `live()` |
|---|---|
| V3-lite (both) | `open_weights {'H1':1}`, `entry_agree_s 2` (M15 fc section as agreement), `force_close_enabled False`, `max_adds 0`, `trend_tf H1`, `vol_tf H1`, `vol_len 24`, `target_usd_per_unit None`, `stop_loss_usd_per_unit None`, `target_vol 8`, `stop_vol 8`, `loss_cooldown_s 43200` |
| XAU Top 1 | open H1, `entry_agree_s 0`, target/stop 10/8 vol, no cap, `max_adds 1` (`macd_turn` on tier M5, `ladder_gap_vol 1`, multipliers `[1,1,1,1]`, `ladder_tfs [M5,M15,H1,H1,H1]`), pause 4 h, trend H1, no force-close |
| XAU Top 2 | open H1, agree 0, target/stop 8/4, cap $12, `max_adds 0`, pause 12 h |
| XAU Top 3 | as Top 1 with cap $12, pause 1 h |
| BTC Top 1 / 2 / 3 | open H1 (Top 3: H1+M15), agree 0, target/stop 8/8 cap $20 / 10/8 cap $12 / 8/8 no cap, `max_adds 0`, pause 4 h |
| Owner's rules | `entry_rsi_block_tfs [H1,H4]` ("any"), `fc_rsi_tfs [H1,H4]`, trend H1, pause 4 h, live ladder |

### 8.2 (a) `BacktestConfig.live(repo_root=<branch>)` must produce the design (config.py)

- **config.py:393-422.** After the `kw = dict(...)` block, read the new constants with `getattr(c, NAME, <off value>)`. Old branches then produce exactly what they produce today. Replace the hard-coded hedging target at line 420:

```python
# config.py, inside live(), after line 409 (and replacing line 420's hard-coded target)
def _tf(x):  return None if x is None else str(x).replace("TIMEFRAME_", "")
g = lambda name, default: getattr(c, name, default)
kw.update(
    force_close_enabled=bool(g("FORCE_CLOSE_ENABLED", True)),
    max_adds=int(g("MAX_ADDS", 99)),
    ladder_multipliers=list(g("LADDER_MULTIPLIERS", FIBO)),
    ladder_trigger=g("LADDER_TRIGGER", "rsi_level"), ladder_gap_vol=float(g("LADDER_GAP_VOL", 0.0)),
    trend_tf=_tf(g("TREND_TF", None)), trend_mode=int(g("TREND_MODE", 1)),
    loss_cooldown_s=float(g("LOSS_COOLDOWN_SECONDS", 0.0)),
    vol_tf=_tf(g("VOL_TF", None)), vol_len=int(g("VOL_LEN", 24)),
    vol_cap_usd_per_unit=float(g("VOL_CAP_USD_PER_UNIT", 0.0)),
    target_vol=float(g("TARGET_VOL", 0.0)), stop_vol=float(g("STOP_VOL", 0.0)),
    stop_loss_usd_per_unit=g("STOP_LOSS_USD_PER_UNIT", None),
)
...
else:
    kw.update(book_enabled=False, target_usd_per_unit=g("TARGET_USD_PER_UNIT", 1.0))   # was: 1.0
```

- **Simpler alternative.** Name the constants exactly as the fields, upper-cased (`TREND_TF`, `LOSS_COOLDOWN_S`, `TARGET_VOL` …), and loop over one tuple of field names. The same tuple then drives `_apply_config` (§8.3), so the two sides cannot drift.
- **Keep the agreement section.** `FORCE_CLOSE_SCORE_WEIGHTS` must stay as the agreement section, or else add `AGREE_SCORE_WEIGHTS` → `agree_weights`. The kernel then reads the agreement from it (`CI_AGREE_SEP`).
- **`__post_init__` (config.py:270-310) catches inconsistent constants**, e.g. a `TARGET_VOL` without `VOL_TF`. Keep timeframe constants in short keys (`'H1'`).
- **Check:** §7 step 1. The fast engine on `live(new)` must reproduce the published runs (e.g. `final10/runs_*_ticks.csv`) on the same window and timing.

### 8.3 (b) A reference replay of the new app.py must be comparable with the fast engine

1. **`reference._apply_config` (reference.py:407-462).**
   - **Guards (410-443).** Replace the blanket refusals that the branch now implements with *capability checks* on the live modules. Example: allow `target_usd_per_unit=None` / `max_adds<5` / `force_close_enabled=False` / `ladder_multipliers≠FIBO` / non-standard `ladder_tfs` only if `hasattr(mods.strategy or mods.app, "TARGET_VOL" / "MAX_ADDS" / "FORCE_CLOSE_ENABLED" / …)`.
   - **Add refusals.** Refuse every non-default lever the live code lacks: `trend_tf`, `loss_cooldown_s`, `vol_tf`/`*_vol`/`vol_cap`, `ladder_trigger≠'rsi_level'`, `ladder_rsi_exit`, `trail_*`, `entry_rsi_block_tfs`, `fc_rsi_tfs`, `entry_max_spread`, `daily_loss_limit_usd_per_unit`, `agree_weights`. Today these pass silently (§1.5).
   - **Pushes (444-462).** Set each new value in every module that did `from constants import NAME` (`mods.strategy`, `mods.app`, `mods.mt5_helper`), and in `mods.constants` for code that reads `constants.NAME`.
   - **Extend the slope list (449-455).** It must contain whatever the branch fetches slopes for: `cfg.trend_tf`, `cfg.vol_tf`, and the tier timeframes when `ladder_trigger == "macd_turn"`, mirroring the new `constants.SLOPE_TIMEFRAMES` derivation. Today it is clobbered to open ∪ fc (∪ book).
2. **`reference.run_reference`.**
   - Add any new live module to `_LIVE_MODULES` (367) and `experiments._LIVE_FILES` (experiments.py:95).
   - Patch its clock as well (546-548): `mods.<module>.time = clock`, and `datetime` if used.
   - Stub new persistence in `_new_bot` (575-579).
   - If the port reads them, implement in `SimMT5`: `history_deals_get` (306-307, from `self.deals`: entry 0/1, profit, time, …), the `symbol_info` fields (263-266: `trade_contract_size`, `volume_min/step`, `digits`, `point`), and `comment` on `order_send`/`positions_get` (322-364 / 310-320).
3. **The reference trace (593-608, 631-632).**
   - Name the ladder columns by position (`rsi_{q}_{tf}`) and only for `cfg.ladder_tfs[:cfg.n_ladder_adds]`: duplicates crash `compare()` today.
   - Optionally record new `analysis_data` fields so differences are found fast: trend sign, volatility unit, frozen target/stop USD, loss-pause flag.
4. **`parity.compare` (82-185).**
   - Change the RSI loop at line 124 to `for q, tf in enumerate(cfg.ladder_tfs[:cfg.n_ladder_adds])`, with positional columns.
   - Add `entry_allowed` against `T_ENTRY_ALLOWED`; it pins the loss pause.
   - If any entry gate is ported into `strategy.py` (option B), the signal comparison at lines 103-110 must use the kernel's post-filter signal (next item).
5. **Kernel, only for option B.** Write a block-reason column after the execution checks (kernels.py:1202-1247 into the row written at 1156-1172), raise `T_N` (279), and make the `T_RSI0` bound at 1170 a constant of its own. In `compare()`, treat a fast BUY/SELL with a strategy-level block as 0.
   - This changes `engine_fingerprint`, so every stamped result is flagged stale (the numbers themselves are unchanged).
   - Option A (§6.3) needs no kernel change.
6. **`fast_config_for_parity` (71-79) stays as it is**, unless the port changes its sleeps. `check_parity` (188-197) needs a `regime=` pass-through only for a V3-lite + regime hybrid.
7. **Tests.**
   - `tests/conftest.py` `FIXTURE_WINDOWS` and `tests/make_fixtures.py`: add windows in which the design trades, or use the scaled overrides of §7.
   - `tests/test_parity.py::_assert_ok(min_fills)` fails on today's fixtures for V3-lite (0 fills).
   - `test_configured_thresholds_snapshot` and the hedging target/ladder characterization tests describe the old rules and must be rewritten for the branch.

### 8.4 The verification recipe

1. Export the branch's six live files to a directory.
2. Run §7 step 1: config mapping plus identical fast fills.
3. Run `ALCADEIAS_LIVE_ROOT=<dir> python3 -m pytest tests/test_parity.py tests/test_live_strategy_characterization.py -p no:cacheprovider` with the updated tests.
4. Run `python -m backtesting parity --live-root <dir> --symbol … --start … --end … --out …` on the §7 windows, once per design.
5. Run `parity_final.py recheck <xau6 root>`.
6. Demo forward test. The parity is a code-equality proof, not a performance proof.

### 8.5 Bar-level strategies (Turtle + bot votes, Turtle System 2 + bot votes, London breakout …)

**How the backtest ran them.** In `research/external.py`:
- `turtle(m, system)` (1282-1301): D1 Donchian stop-entry orders at the 20/55-day high/low ± tick, 2N stop, pyramid every ½N up to 4 units, exit at the 10-day (S1) or 20-day (S2) low/high, and the S1 skip-after-winner filter `_turtle_s1_use20` (1218-1279).
- "+ bot votes" = `filtered(plan, m, sig.votes_at)`: M15 RSI and MACD votes both agreeing on **closed** M15 bars (`bot_signals`, 334-356).
- Simulation on M1 bars: fills at the next M1 open, stop entries inside the bar, stop before target.
- D1 bars are UTC days with days under 360 M1 bars merged (`day_bars`).

**Why parity cannot check a port.** There is no kernel and no SimMT5 support for pending orders or SL modification. A port needs either broker stop orders, which SimMT5 would have to model, or 1 s polling of the breakout levels in the bot; the latter fills differently from the simulator.

**What verification would look like.** A trade-list comparison of a SimMT5 replay against `external.run_path` trades within explicit tolerances (same day and side, entry within spread plus slippage, same exit rule), not poll-by-poll equality.
