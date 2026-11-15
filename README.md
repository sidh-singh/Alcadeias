# DEMO ONLY · demo_hedging_btcusd7 · BTCUSDm · Turtle System 1 + bot votes

This branch runs **Turtle System 1 + bot votes** on the **demo** account (the `demo` block of slot 7's credentials, the same
account every slot uses for demo). It is a copy of `hedging_btcusd7`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

The Turtle on daily UTC bars with the 20-day breakout (skipped after a winning breakout, then the 55-day failsafe) and the 10-day exit, taken only when the bot's M15 votes on closed bars agree; adds and stop as System 2.

Why this one: the final ten's BTC leader on the bot's unit sizing, and the best of the Turtles over 5 years and the last year. It shares many trades with System 2 (branch 6), so the two will often move together.

## Its backtest

Final-ten study (`backtest_hedging`: `backtest_results/final10/FINAL10.md`), Exness ticks, a fresh $2,000 account per
window, the bot's unit rule (0.01 lot, plus 0.01 lot for every $2,500 of balance, at most 0.10 lot). Max DD is the
deepest fall from an equity peak.

| Window | Final equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 8 years | $6,977 | +16.9% a year | 46.0% | 88 |
| 5 years | $6,305 | +25.8% a year | 44.6% | 58 |
| Nov 2018 - Dec 2020 | $2,742 | +37.1% | 10.7% | 21 |
| last year | $3,412 | +70.6% | 26.4% | 11 |

Every year from 2018 to 2026 had been read by earlier studies, so this demo run is the first test on data no study has
seen.

## How to run

```bat
start_btcusd.bat           REM or: start_job.bat   (both default to demo)
start_dashboard.bat
```

## What keeps it apart from the other demo bots

All six demo branches (`demo_hedging_xauusd6/7/8`, `demo_hedging_btcusd6/7/8`) use the same demo account, so each bot
is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26127 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_btcusd7` |
| Dashboard port | 8072 |

The account's own balance, equity and margin are shared by all six bots. Each strategy's own result is the sum of the
deals with its magic number.
