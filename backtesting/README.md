# The backtesting suite

A tick-level backtester for the live RSI+MACD slope bot in this repo. It replays real
Exness ticks through the same decisions `app.py` makes once a second, against a simulated
MT5 account. Results and conclusions for this branch are in [`../BACKTEST.md`](../BACKTEST.md);
this file explains how the suite works and how to use it.

The live files (`app.py`, `strategy.py`, `indicator.py`, `mt5_helper.py`, `constants.py`,
`dashboard.py`, `symbols.json`) are **not modified** by anything here.

## Quick start

```bash
pip install -r requirements-backtest.txt

python -m backtesting data --from 2025-07 --to 2026-11   # download + build the tick store (~2 GB download)
python -m backtesting run --symbol XAUUSDm               # live settings, last 3 months -> HTML report
python -m backtesting studio                             # watch the bot trade history, tick by tick
python -m pytest tests -q                                # test-suite (no download needed)
```

The commands that run the strategy on one symbol — `run`, `parity`, `sweep`, `robust` — take
`--symbol`, `--start/--end` (UTC), `--balance`, `--leverage`, `--set key=value` for any field
of `BacktestConfig`, and `--live-root <dir>`:

```bash
python -m backtesting run --symbol BTCUSDm --start 2026-09-01 --end 2026-10-01 \
    --set 'open_weights={"H4":1,"M15":1}' --set entry_s=4 --set max_adds=2 --set stop_loss_usd_per_unit=20
```

The other commands take only what they use; `python -m backtesting <command> --help` lists it.

| Command | What it does | Options besides its own switches |
|---|---|---|
| `data` | Downloads Exness tick archives and builds the local store (`data/`, git-ignored) | `--symbols`, `--from/--to` (months) |
| `quality` | Coverage, gaps, spread and jump statistics of the stored ticks | `--symbol`, `--start/--end` |
| `run` | One backtest → `report.html` + `baskets.csv`, `fills.csv`, `equity.csv.gz`, `summary.json` | `--symbol`, `--start/--end`, `--balance`, `--leverage`, `--set`, `--live-root` |
| `parity` | Replays a window through the **real live code** and compares the fast engine with it | as `run` |
| `sweep` | Timeframe grids (OPEN / FORCE-CLOSE / BOOK; RSI and MACD together or split) | as `run` |
| `robust` | Loop timing, latency, costs, start date, sub-periods, bootstrap | as `run` |
| `reproduce` | The whole pipeline behind `backtest_results/` | `--symbols`, `--live-root`; its windows and balances are fixed |
| `docs` | Rebuilds `backtest_results/index.html`, the PNG gallery and `BACKTEST.md` from the results | `--symbols`, `--live-root` |
| `studio` | Interactive results + live-style replay in the browser | `--host`, `--port`; always this checkout |

The suite reads the strategy settings from this checkout's own `constants.py` and
`symbols.json` (`BacktestConfig.live()`), and tells the two variants apart by whether
`BOOK_SCORE_WEIGHTS` exists. `--live-root <dir>` (on `run`, `parity`, `sweep`, `robust`,
`reproduce` and `docs`) points it at another checkout instead, for example a worktree of
another deployment branch: the settings come from that directory's `constants.py` and
`symbols.json`, and `parity` runs that directory's `app.py`. The `studio` has no such option
and always shows this checkout's settings.

The PNG snapshots of `docs` need a Chrome, Chromium or Edge on the machine (found in the usual
places on macOS, Windows and Linux, or on `PATH`); without one that step is skipped with one
log line and everything else is built. The suite is verified on pandas 2 and plotly 5, and
`requirements-backtest.txt` holds both below their next major version.

### Raw ticks or the per-second series

`run` replays one of two series, chosen with `--mode`:

| `--mode` | Data | Loop timing |
|---|---|---|
| `sec` (default) | the per-second series (`sec.npz`, see Data) | one poll on every whole second, +1 s after a ladder add. The 0.1 s the live `buy()` / `sell()` sleep after sending an entry or a ladder add is **not** modelled: this series cannot represent it, because a poll a tenth of a second off the whole second would need a quote the series does not hold. The sweeps use this mode |
| `ticks` | every tick | the same, plus that 0.1 s (`open_order_delay_ms=100`, set by `run --mode ticks` unless you pass `--set open_order_delay_ms=...`), so the polls leave the whole seconds as the live loop's do. This is the timing of the pipeline's baseline runs |

The two agree until the first order and can part afterwards, because from then on they poll
at different instants. Neither includes the time the live loop spends on its MT5 calls; the
`robust` tests vary that instead (see "One run is one path" below).

## Data

Exness publishes every tick of every symbol, account-type suffix included, at
`ticks.ex2archive.com` — so the backtest runs on the broker's own bid/ask stream for
`XAUUSDm` and `BTCUSDm`, with the spreads, session breaks and gaps the live accounts saw.
Timestamps are UTC, which is also Exness MT5 server time, so bars bucket on plain UTC
boundaries exactly as the terminal builds them (from Bid).

`python -m backtesting quality` lists what the feed contains: coverage, every silence over
three minutes by kind (daily break, weekend, holiday, maintenance pause, hole in the
archive), spread by hour and the largest one-second moves. The large moves in this history
are real events (the crypto liquidation of 10 October 2025, gold on US data releases), not
bad ticks.

`python -m backtesting data` keeps three resolutions per month under `data/store/`:

| File | Content | Used for |
|---|---|---|
| `ticks.npz` | every tick | high-fidelity runs, parity with the live code, timing tests |
| `sec.npz` | the last tick of each second, plus any tick stamped exactly on a whole second | sweeps — a 1 s poll on whole seconds sees exactly these quotes |
| `m1.npz` | M1 bid bars | indicator warm-up before a window, chart candles |

## Two engines, one configuration

```
BacktestConfig ──┬── engine/reference.py   the real app.py loop on a simulated MT5 terminal   (truth, slow)
                 └── engine/fast.py        numba re-implementation of the same loop           (seconds per run)
                              ▲
                     engine/parity.py checks them against each other, poll by poll
```

**Reference engine.** `run_reference` imports this branch's own `app.py` and swaps the
`MetaTrader5` module for `SimMT5`, an in-memory terminal that serves bars (forming bar
included), ticks, positions and fills from real ticks; the clock is simulated, so the loop's
own `time.sleep` calls are what advance time. `MT5TradingBot.process_symbol` then runs
untouched. Whatever it decides is, by construction, what the live bot would decide on that
tick stream.

**Fast engine.** `engine/kernels.py` does the same thing in numba: at every poll it takes
the latest tick, updates the *forming* bar of each timeframe with that price (the live bot
reads RSI, MACD and pivot slopes on the still-forming bar), derives the slope signs and
section scores, applies the rules of `strategy.py`, and keeps the account. Three months of
one-second polls take one to three seconds, which is what makes sweeps possible.

**Parity.** `python -m backtesting parity` replays a window through both and requires
identical poll timestamps, signals, scores, fills and final balance. The windows already
checked are listed in `backtest_results/parity/` and on the results page; parity runs on
bundled real ticks, including one across a session break and two in which the broker
refuses orders for margin, are part of the test-suite.

What the comparison covers: the strategy rules, the loop cadence, fills, and what the live
loop does when the broker refuses an order, because the simulated terminal applies the same
broker-side rules as the fast engine (see the table below). What it does not cover: the
stop-out (the simulated terminal has none; unit tests only), the handling of holes in the BTC
history (the live code never meets one), a loop that does not take exactly one second per
pass, and the 90 s / 3.5 min close-only durations themselves, which are read off Exness's
published behaviour and not measured.

## What is simulated, and how

| Aspect | Model |
|---|---|
| Loop | one pass per second; 0.1 s more after every entry or add the bot sends and 1 s more after an add, filled or refused, as the live code sleeps. Raw-tick runs (`--mode ticks`: the baseline, the timing and cost tables, the candidate ensemble) model this exactly. Per-second runs (sweeps, the fifteen-month run, monthly and weekly segments) keep every pass on a whole second, i.e. without the 0.1 s; the engine warns if a per-second run is given a timing it cannot carry. `poll_jitter_ms` makes every pass take a random 0..N ms longer (reproducible by `poll_jitter_seed`): the live loop's own work time varies, so its polls do not sit on a fixed grid |
| Indicators | recomputed on the forming bar at every poll, same seeds and comparisons as `indicator.py`. The engine warms them up on up to 600 bars per timeframe where the live bot fetches 500; with the live lengths the two agree to nine decimals, and at the longest RSI length the lever table tries (28) they differ by about one millionth of an RSI point |
| Fill price | market order at the quote of the tick the decision saw: ask for a buy, bid for a sell (`latency_ms` delays the fill quote) |
| Position P/L | (price difference) × lots × contract size, rounded to cents — what `positions_get()` reports |
| Costs | the recorded bid/ask spread; no commission (Standard account); no swap |
| Sizing | `unit = floor(balance / step_up_balance) + 1`, re-derived only while flat; entry `unit × 0.01` lot; ladder ×1,2,3,5,8,13 |
| Margin | lots × contract × open price / leverage (gold follows the account's 1:2000; BTC is held at Exness's former fixed 1:400, the stricter of the two regimes in force during 2026); an order the free margin cannot carry is refused and retried on the next pass, after the same sleeps as a filled one |
| Stop-out | all positions closed when equity ≤ 0 (Exness Standard stop-out level 0 %, balance floored at 0 by negative-balance protection); the run ends there |
| Sessions | no decisions while the last tick is older than 3 minutes (the bot's own liveness rule); fresh entries only inside the trading window. A session ends with its last quote before a silence of 30 minutes or more: an order sent more than a second after that quote is refused ("market closed") even though the bot still counts the market as live, so nothing is opened or closed on a stale quote. After the break the broker's close-only mode refuses new orders for 90 s (3.5 min after a break of a day or more) while closes go through. A run that starts just after a break inherits what is left of that period, and a window that ends inside a closure treats its last quote as the end of the session (the time of the next quote in the history is looked up; never its price). With `latency_ms` the broker judges the order when it arrives |
| Holes in the history | BTC trades around the clock, so three hours without a tick are missing data, not a closed market (the archive lacks 30 Aug 2025, the evening of 30 Nov 2025 and 30–31 Mar 2026). The open basket is closed at the last quote before the hole (reason `data_hole`; none of the missing hours' P/L is booked) and no basket is opened for 6.3 days after the history resumes: 38 H4 bars, the time the slowest indicator of the live settings needs to leave the hole behind. The length is the same for every configuration on purpose, so that all rows of a sweep or a what-if table sit out the same days (`data_hole_quarantine_s` changes it). This removes most, not all, of the distortion: the bars still straddle the hole. `data_hole_s=0` switches it off; gold, which has real closures, never uses it |

**Not simulated:** requotes and partial fills; refusals other than the three above; terminal
or VPS outages; bot restarts (which reset the live cooldown and unit); manual intervention;
swaps; temporary broker margin increases around news and weekends. How long a pass of the
live loop really takes, and how long an order takes to reach the server, are not known, so
the pipeline measures how sensitive the result is to them instead (`robust`). A run starts at
the first pass that can see a quote of its own window.

## The experiment pipeline

`python -m backtesting reproduce` runs these stages (each is skipped when its output is
there and was written by this build for these live settings, unless `--force`;
`--only <stage ...>` picks some):

| Stage | Output | What it answers |
|---|---|---|
| `quality` | `data_quality/` | is the tick history complete and sane? |
| `baseline` | `baseline/<symbol>/` | the live settings on the three months asked for, raw ticks, $2,000 |
| `long` | `long/<symbol>/` | the same over all fifteen months in one run |
| `signal` | `signal/` | what the RSI / MACD slope votes are made of, and what price did after they agreed (closed bars, live `indicator.py`) |
| `sweeps` | `sweeps/` | which timeframes for OPEN / FORCE-CLOSE / BOOK, RSI and MACD together and split |
| `levers` | `levers/` | every other parameter, one at a time |
| `improve` | `packages/` | what-ifs aimed at the weaknesses the baseline shows |
| `holdout` | `sweeps/*_holdout.csv` | the timeframe grid again on two quarters never used to choose anything |
| `candidates` | `candidates/` | a short list of settings on all five quarters and on the real account |
| `robust` | `robustness/<symbol>/` | loop timing, latency, costs, start date, sub-periods, bootstrap; every quarter under eight loop timings |

Five three-month windows are used. `IS` (13 Aug → 13 Nov 2026) is the period asked for;
`OOS1` and `OOS2` are the two quarters before it; settings are compared on these three.
`HO2` and `HO1` (13 Aug 2025 → 13 Feb 2026) are a hold-out: nothing is selected on them,
they only test what was selected.

**One run is one path.** The result of a quarter rests on a handful of large baskets, and
whether the bot is inside one when a sharp move starts depends on which tick its poll lands
on: the same settings on the same ticks can end a quarter up or down when the loop timing
moves by a fraction of a second. A "loop timing" in the pipeline is the live cadence with
every pass taking a random 0 to 0.2 s longer; `robustness/<symbol>/quarters_timing.csv`
runs every quarter under eight of them, the cost and latency tables run every level under
four, and `candidates/<symbol>_timing.csv` runs every candidate setting under eight per
quarter. (Fixed phase offsets would not do: the poll grid moves by 0.1 s with every order,
so runs started half a second apart fall onto the same grid and become one path.) Read
single cells of a sweep with that spread in mind, and trust only patterns that repeat
across quarters.

**One fixed unit, and the real account.** Sweeps trade a fixed 0.01-lot unit on a balance
too large to be stopped out, so every setting is measured over the whole window. The live
account does not trade like that: it steps its unit up with the balance, so after a good run
every later loss is larger. Each sweep row therefore also carries `acct_net`, `acct_wiped`
and `acct_dip`: the same baskets replayed in order on a $2,000 account with the bot's unit
rule (`metrics.replay_account`); that is what "wiped" and ✕ mean in the tables. A basket
still open when the window ends counts with its worst floating loss. The baseline, the
fifteen-month run, the timing ensembles (`robustness/<symbol>/quarters_timing.csv`,
`candidates/<symbol>_timing.csv`), the fifteen-month candidate runs
(`candidates/<symbol>_account.csv`) and the cost, latency, start-date and segment tables use
the real $2,000 and the live unit auto-step directly; `candidates/<symbol>.csv` and
`robustness/<symbol>/quarters_timing_fixed_unit.csv` are fixed-unit runs with the replay,
like the sweeps.

**Which build wrote what.** Every pipeline output is stamped in
`backtest_results/manifest.json` with three fingerprints: of the code that decides its numbers
(engine, analysis and report modules), of the live rules (`constants.py`, `symbols.json`,
`strategy.py`, `indicator.py`, `app.py`, `mt5_helper.py`) and of the tick history it read. A
stage is skipped only when its output carries the current three; change a constant, the engine
or the data and `reproduce` recomputes what depends on it. The fingerprints are taken when
`reproduce` starts, and it stops rather than stamp a result if those files change while it
runs (worker processes import whatever is on disk), so do not edit them during a run. `docs`
warns when a page would show a file that is stale or carries no stamp, and a parity report
(`backtest_results/parity/*.json`, stamped by `python -m backtesting parity --out`) counts as
stale once either engine or the live rules have changed since it was made. A checkout without
the tick history can still build the pages; it then cannot judge the data fingerprint and does
not try to.

The tick store lives in `data/store/`; set `ALCADEIAS_STORE_DIR` to keep it elsewhere.

## Experimental levers

Every lever is **off by default**, so a default run is the live behaviour. They exist to test
fixes for the weaknesses the backtest exposes:

`max_adds`, `ladder_multipliers`, `ladder_min_gap`, `ladder_min_interval_s`,
`ladder_tfs` — shape and spacing of the DCA ladder · `stop_loss_usd_per_unit`, `max_hold_s` —
price and time stops · `target_usd_per_unit`, `target_per_lot`, `book_enabled`,
`profit_protect_usd_per_unit` — profit exits · `slope_on_closed_bars`,
`ladder_on_closed_bars`, `fc_confirm_s`, `entry_confirm_s`, `min_hold_s` — signal
stability · `allow_long`, `allow_short`, `entry_hours_utc` — filters · `trend_tf`, `trend_mode` —
entries only with (+1) or against (-1) the trend of one timeframe, read as the sign of the MACD
signal line of its last closed bar · `entry_max_spread` — no entry on a quote wider than this ·
`loss_cooldown_s` — a longer pause after a losing basket · separate RSI / MACD
weights per timeframe in `open_weights`, `fc_weights`, `book_weights`
(`{"H4": [1, 0], "M15": [0, 1]}` = RSI on H4, MACD on M15).

The improvement search built on these levers (which designs were tried, how they were chosen and
what they did on five quarters) is in [`IMPROVEMENT.md`](../IMPROVEMENT.md); its code is
`backtesting/research/` (`python -m backtesting.research.improve report XAUUSDm`).

## Layout

```
backtesting/
  config.py            BacktestConfig, symbol specs, BacktestConfig.live()
  data/                exness.py (download) · store.py (tick store) · quality.py
  engine/              kernels.py · fast.py · reference.py · parity.py
  analysis/            metrics.py · diagnostics.py · signal.py · sweep.py · robustness.py · holdout.py
  viz/                 report.py · index.py · markdown.py · studio.py · replay.py · snapshot.py · theme.py
  experiments.py       the pipeline behind backtest_results/
  cli.py               python -m backtesting ...
tests/                 test-suite + a miniature store of real ticks (tests/fixtures)
backtest_results/      committed outputs: index.html, reports, sweeps, candidates, robustness, parity
```

## Tests

`python -m pytest tests -q` needs no download: `tests/fixtures/store` holds an hour of real
BTC ticks and 45 minutes of real gold ticks with their warm-up history.

| File | What it pins down |
|---|---|
| `test_indicators.py` | the numba kernels against `indicator.py`: RSI, MACD, the forming-bar update, and a randomised comparison of the pivot-slope logic |
| `test_live_strategy_characterization.py` | the rules of the live `strategy.py` as they are today, so an accidental edit is caught |
| `test_parity.py` | the fast engine against the real `app.py` loop on the bundled ticks: every poll, signal, score, fill and the final balance |
| `test_engine_invariants.py` | the account adds up; baskets close what they opened; cooldown, window and sizing rules; determinism; no look-ahead; per-second series = raw ticks |
| `test_live_fault_injection.py` | three weaknesses of the live loop, demonstrated on the real code: a failed position read, a restart, a rejected order |
| `test_levers_and_reports.py` | the ladder shape and spacing levers, the price and time stops, the per-lot target and the broker close-only window do what they say; reports, diagnostics and sweep grids build |
| `test_lever_rules.py` | the rules no live code stands behind, on the engine's own fills and poll trace: an independent replay of the decision rules with several levers on at once; one property per remaining lever and setting (confirmation times, hold, direction and hour filters, thresholds, cooldown, split weights and grey-fill, exit order, book and profit bar, ladder levels and timeframes); closed-bar signals and other indicator settings against `indicator.py`; a BUY / SELL mirror run; every lever inert at its off value |
| `test_store.py`, `test_config_metrics.py` | tick store and bar building; configuration loading; metrics |
| `test_holdout_analysis.py` | the hold-out and candidate tables, the signal-vote study, the timing ensemble |
| `test_studio.py` | the replay shows exactly the fills of the full run and never draws the future |
| `test_cli_and_portability.py` | which command takes which option and that `--live-root` is used; the 0.1 s order sleep of `run --mode ticks`; nanosecond result times; browser discovery; non-ASCII text under a non-UTF-8 default encoding |

`pytest.ini` leaves the tests marked `slow` (the full-window parity replays, about a minute
each) out of the default run. `python -m pytest tests -q -m slow` runs **only** those;
`python -m pytest tests -q -m "slow or not slow"` runs everything. To run the suite against
another checkout of the live code (for example the other variant), set
`ALCADEIAS_LIVE_ROOT=/path/to/checkout`.
