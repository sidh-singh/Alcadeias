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

Everything takes `--start/--end` (UTC), `--balance`, `--leverage`, and `--set key=value` for
any field of `BacktestConfig`:

```bash
python -m backtesting run --symbol BTCUSDm --start 2026-09-01 --end 2026-10-01 \
    --set 'open_weights={"H4":1,"M15":1}' --set entry_s=4 --set max_adds=2 --set stop_loss_usd_per_unit=20
```

| Command | What it does |
|---|---|
| `data` | Downloads Exness tick archives and builds the local store (`data/`, git-ignored) |
| `quality` | Coverage, gaps, spread and jump statistics of the stored ticks |
| `run` | One backtest → `report.html` + `baskets.csv`, `fills.csv`, `equity.csv.gz`, `summary.json` |
| `parity` | Replays a window through the **real live code** and compares the fast engine with it |
| `sweep` | Timeframe grids (OPEN / FORCE-CLOSE / BOOK; RSI and MACD together or split) |
| `robust` | Loop timing, latency, costs, start date, sub-periods, bootstrap |
| `reproduce` | The whole pipeline behind `backtest_results/` |
| `docs` | Rebuilds `backtest_results/index.html`, the PNG gallery and `BACKTEST.md` from the results |
| `studio` | Interactive results + live-style replay in the browser |

The suite reads the strategy settings from this checkout's own `constants.py` and
`symbols.json` (`BacktestConfig.live()`), and tells the two variants apart by whether
`BOOK_SCORE_WEIGHTS` exists. `--live-root <dir>` points it at another checkout instead.

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
checked are listed in `backtest_results/parity/` and on the results page; a short parity
run on bundled real ticks is part of the test-suite.

## What is simulated, and how

| Aspect | Model |
|---|---|
| Loop | one poll per second; +0.1 s after an order and +1 s after a ladder add, as the live code sleeps |
| Indicators | recomputed on the forming bar at every poll, same seeds and comparisons as `indicator.py` |
| Fill price | market order at the quote of the tick the decision saw: ask for a buy, bid for a sell (`latency_ms` delays the fill quote) |
| Position P/L | (price difference) × lots × contract size, rounded to cents — what `positions_get()` reports |
| Costs | the recorded bid/ask spread; no commission (Standard account); no swap |
| Sizing | `unit = floor(balance / step_up_balance) + 1`, re-derived only while flat; entry `unit × 0.01` lot; ladder ×1,2,3,5,8,13 |
| Margin | lots × contract × open price / leverage (gold follows the account's 1:2000; BTC is held at Exness's former fixed 1:400, the stricter of the two regimes in force during 2026); a rejected order is simply retried next poll, as live |
| Stop-out | all positions closed when equity ≤ 0 (Exness Standard stop-out level 0 %, balance floored at 0 by negative-balance protection); the run ends there |
| Sessions | no decisions while the last tick is older than 3 minutes; fresh entries only inside the trading window; after a session break the broker's close-only mode refuses new orders for 90 s (3.5 min after the weekly open), read off the tick gaps |
| Holes in the history | BTC trades around the clock, so three hours without a tick are missing data, not a closed market (the archive lacks 30 Aug 2025, the evening of 30 Nov 2025 and 30–31 Mar 2026). The open basket is closed at the last quote before the hole (reason `data_hole`; none of the missing hours' P/L is booked) and no basket is opened for 24 h after the history resumes. `data_hole_s=0` switches this off; gold, which has real closures, never uses it |

**Not simulated:** requotes, partial fills and rejections other than margin; terminal or VPS
outages; bot restarts (which reset the live cooldown and unit); manual intervention; swaps;
temporary broker margin increases around news and weekends. Loop timing and order latency
are not knowable exactly, so they are stress-tested instead (`robust`).

## The experiment pipeline

`python -m backtesting reproduce` runs these stages (each is skipped when its output exists,
unless `--force`; `--only <stage ...>` picks some):

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
on: the same settings on the same ticks can end a quarter up or down when the loop phase
moves by a quarter of a second. `robustness/<symbol>/quarters_timing.csv` therefore runs
every quarter under eight loop timings; read single cells of a sweep with that spread in
mind, and trust only patterns that repeat across windows.

Sweeps trade a fixed 0.01-lot unit on a balance too large to be stopped out, so every
setting is measured over the whole window; `max_loss_from_start >= 2000` then marks the
runs in which a real $2,000 account would have been wiped out. Baseline, long, candidate
"account" and robustness runs use the real $2,000 and the live unit auto-step.

## Experimental levers

Every lever is **off by default**, so a default run is the live behaviour. They exist to test
fixes for the weaknesses the backtest exposes:

`max_adds`, `ladder_multipliers`, `ladder_min_gap`, `ladder_min_interval_s`,
`ladder_tfs` — shape and spacing of the DCA ladder · `stop_loss_usd_per_unit`, `max_hold_s` —
price and time stops · `target_usd_per_unit`, `target_per_lot`, `book_enabled`,
`profit_protect_usd_per_unit` — profit exits · `slope_on_closed_bars`,
`ladder_on_closed_bars`, `fc_confirm_s`, `entry_confirm_s`, `min_hold_s` — signal
stability · `allow_long`, `allow_short`, `entry_hours_utc` — filters · separate RSI / MACD
weights per timeframe in `open_weights`, `fc_weights`, `book_weights`
(`{"H4": [1, 0], "M15": [0, 1]}` = RSI on H4, MACD on M15).

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
| `test_levers_and_reports.py` | every experimental lever does what it says and is inert when off; reports and diagnostics build |
| `test_store.py`, `test_config_metrics.py` | tick store and bar building; configuration loading; metrics |
| `test_holdout_analysis.py` | the hold-out and candidate tables, the signal-vote study, the timing ensemble |
| `test_studio.py` | the replay shows exactly the fills of the full run and never draws the future |

`python -m pytest tests -q -m slow` adds the longer parity windows. To run the suite against
another checkout of the live code (for example the other variant), set
`ALCADEIAS_LIVE_ROOT=/path/to/checkout`.
