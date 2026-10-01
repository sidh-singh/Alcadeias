# Alcadeias BTCUSD — Offline Full-Logic Backtest

This package replays the **exact** live trading logic against historical 1-minute
data, with **no MT5 sign-in** and no live orders. It exists to answer one
question: *how do the parameters and the strategy actually behave over the last
few months?*

> ⚠️ **Testing tool only.** This lives on the `backtest_btcusd` branch and must
> **never** be cherry-picked into the 20 live fleet branches. It does not modify
> `app.py`, `strategy.py`, `indicator.py`, `constants.py`, or `symbols.json`.

---

## What makes it faithful

The backtest **imports and calls the real code** — it does not re-implement the
strategy:

| Live component | In the backtest |
|---|---|
| `strategy.Strategy.calculate_signal(...)` | called **unchanged**, same argument order as `app.py` |
| `indicator.Indicator.calculate_sha_v3 / calculate_rsi / _ma` | called **unchanged** |
| `constants.py` (RSI 35/65, SHA TEMA10/DEMA20 on M15, ladder TFs, lookback…) | imported **as-is** |
| `symbols.json` (`mtqty`, `step_up_balance`, `unit_max_limit`) | read for defaults |
| MT5 data feed (`get_rates`) | replaced by historical M1 bars, causally resampled |
| MT5 orders / positions (`buy`/`sell`/`close_by_type`/`get_*_positions`) | replaced by a simulated broker that reproduces `pos.profit` and the Fibo lot ladder |

Only the two things the user asked to skip — **sign-in and live execution** — are
stubbed. Everything that decides *what* to trade is the production code.

### Faithful details worth knowing

- **Decision cadence = per M1 bar.** The live bot loops every ~second and reacts
  intrabar; we evaluate every minute so the tiny `+$unit` profit target and the
  RSI DCA / H6 exits fire at minute resolution (not just on bar closes).
- **MT5 "forming bar" RSI.** Live, `get_rates(tf, 500)` returns the *in-progress*
  higher-timeframe bar as the last row, whose close is the current price — so
  e.g. the H6 RSI updates every second from the live price, not only every 6h.
  We reproduce this exactly with a one-step Wilder-RMA extension from the last
  completed bar to the current price. At startup this is asserted equal to
  calling the real `calculate_rsi` on `[completed closes … + current price]`.
- **SHA entry signal (M15).** Recomputed with the real `calculate_sha_v3` on the
  live `CANDLE_COUNT` (300)-bar rolling window each time an M15 bar closes. SHA is
  used **only** in the flat/entry branch — an open basket's adds and exits never
  depend on it — so evaluating entries on *closed* M15 (≤15 min later than live's
  intrabar SHA) does not affect basket management. Pass `--sha-intrabar` to
  rebuild the forming M15 bar every minute while flat for finer entry timing.
- **Broker P&L = mt5_helper semantics.** `profit = (price − entry)·volume·
  contract_size` for BUY (mirrored for SELL); aggregates rounded to 2 dp. Entry
  fills at ask / exits at bid for BUY (mirrored for SELL), so the spread is paid
  on both sides. Unit auto-steps from balance **only while flat** (an open basket
  keeps the unit it opened on), exactly like `app.py`.
- **Single basket at a time.** As live: a new entry requires `buy_count==0 and
  sell_count==0`, so long and short are never held together.

### Where it is an approximation (read before trusting the P&L)

1. **Data proxy.** With no broker CSV it uses **Binance BTCUSDT 1m** (public, no
   sign-in) as a stand-in for the broker's `BTCUSDm`. Great for studying logic and
   parameters; for broker-exact fills export M1 bars from MT5 and pass `--csv`.
2. **Spread/commission default to 0** (a clean logic view). Real costs matter a
   lot here because the target is only `$unit` — pass `--spread-usd` and
   `--commission-per-lot` to see the real net. (BTCUSD spread on a standard
   account can easily exceed a 0.01-lot's `$1` target.)
3. **Timeframe boundaries are UTC-aligned.** The broker server timezone would
   shift M30/H4/H6 bucket edges slightly; a minor effect on RSI timing.
4. **Fills at the M1 close** (no intrabar high/low touch, no slippage), and
   floating P&L is marked at the close (mid). With `--spread-usd 0` this is exact.
5. Starts **flat at the window open** (no warmup positions carried in).

---

## Running it

From the repo root:

```bash
# Last 90 days, unit=1 ($2,000 balance), logic-only (no costs)
python -m backtest.run_backtest

# 90 days with a realistic BTC spread and a bigger balance (higher unit tier)
python -m backtest.run_backtest --days 90 --balance 10000 --spread-usd 5

# Broker-exact: replay MT5-exported M1 bars instead of the public proxy
python -m backtest.run_backtest --csv path\to\BTCUSDm_M1.csv
```

Or double-click / run `run_backtest_btcusd.bat` (mirrors `start_btcusd.bat`).

### Key options

| Flag | Default | Meaning |
|---|---|---|
| `--days` | 90 | length of the scored window |
| `--warmup-days` | 35 | extra history before the window so indicators converge |
| `--balance` | 2000 | starting balance → drives the auto unit tier & `$unit` target |
| `--spread-usd` | 0.0 | BTC spread (USD) paid across each fill |
| `--commission-per-lot` | 0.0 | round-turn commission per 1.0 lot |
| `--contract-size` | 1.0 | USD P&L per 1.0 price-move per 1.0 lot (BTCUSD Exness = 1) |
| `--csv` | — | broker-exact M1 CSV (`time,open,high,low,close[,volume]`) |
| `--sha-intrabar` | off | recompute SHA on the forming M15 bar while flat |
| `--refresh` | off | ignore the cached data file and refetch |

**Parameter-test knobs** (all default to *exact live behaviour*; use them to answer
"what if"). The first two change what the **real** strategy sees; the last two are
engine-side test overlays:

| Flag | Default | Meaning |
|---|---|---|
| `--regime-act` | off | arm the shipped v1.6.0 regime filter (ADX≥25 + ATR spike) in ACT mode — the verdict is computed from the real `calculate_adx` and passed into the real `calculate_signal` |
| `--close-mult` | 1.0 | multiply the profit target the strategy receives (2.0 = close at `$2×unit`) |
| `--max-depth` | — | cap the DCA ladder at this depth; cut the basket (reason `EARLY_CUT`) instead of adding deeper. Test overlay, **not** a live feature |
| `--block-hours` | — | comma-separated UTC hours to suppress FRESH entries, e.g. `13,14`. Test overlay |

Data is cached under `backtest/data/`; reports, a per-basket CSV and a JSON
summary are written to `backtest/output/`.

---

## Parameter sweep

To compare many parameter variations over the **same** window in one pass:

```bash
python -m backtest.sweep --days 90 --balance 2000
```

It loads the data once and runs a table of scenarios (baseline, RSI 30/70 · 25/75 ·
40/60, regime ON, `cut@depth 3/4/5`, a UTC-hour entry block, `target ×2`, and a few
combinations), printing net %, max drawdown %, profit factor, how many baskets hit
depth 6, forced closes, and the worst single basket for each. Results are saved to
`backtest/output/sweep_*.csv`. Edit the `SCENARIOS` list in `backtest/sweep.py` to
add your own. RSI-threshold variants are applied by temporarily overriding the names
`strategy.py` imported (restored after each run) — `constants.py` is never written.

Once the sweep points at a promising config, re-run that single scenario through
`run_backtest` (with the knobs above) to get its full report — monthly breakdown,
ladder-depth histogram and the per-basket CSV.

## Reading the report

- **Net P&L / drawdown / peak equity** — the headline. Watch drawdown, not just
  net: this is a martingale, so it wins small and often but can dig deep.
- **DCA ladder depth** — how often a basket needed 1…6 positions. Depth 6 means
  the ladder was exhausted and the **H6-RSI forced close** is the only exit left.
- **Exits** — `+$unit target` vs `H6-RSI forced close`. Forced closes are where
  losses concentrate (the basket capitulated at the bottom rung).
- **Worst basket MAE** — the deepest unrealised loss any single basket sat
  through; a direct read on tail risk.
- **baskets_*.csv** — every basket with entry/exit, depth, volume, P&L, hold time
  and close reason, for your own analysis.
