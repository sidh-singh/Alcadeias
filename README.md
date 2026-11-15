# DEMO ONLY · demo_hedging_btcusd6 · BTCUSDm · Turtle System 2 + bot votes

This branch runs **Turtle System 2 + bot votes** on the **demo** account (the `demo` block of slot 6's credentials, the same
account every slot uses for demo). It is a copy of `hedging_btcusd6`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

The Turtle trend follower on daily UTC bars: a breakout of the 55-day high (buy) or low (sell), taken only when the bot's M15 votes on closed bars agree; 1 more unit every half N (N = 20-day average true range) up to 4 units; one stop for all units at the tighter of 2N from the last fill and the 20-day opposite channel, never loosened.

Why this one: the best BTC result on the bot's unit sizing over 8 years, and the best on the never-read Nov 2018 - Dec 2020 data.

## Its backtest

Final-ten study (`backtest_hedging`: `backtest_results/final10/FINAL10.md`), Exness ticks, a fresh $2,000 account per
window, the bot's unit rule (0.01 lot, plus 0.01 lot for every $2,500 of balance, at most 0.10 lot). Max DD is the
deepest fall from an equity peak.

| Window | Final equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 8 years | $7,815 | +18.6% a year | 32.5% | 60 |
| 5 years | $3,547 | +12.1% a year | 38.4% | 41 |
| Nov 2018 - Dec 2020 | $2,858 | +42.9% | 9.4% | 14 |
| last year | $3,039 | +52.0% | 22.4% | 7 |

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
| Magic number on every order; it reads and closes only these positions | 26126 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_btcusd6` |
| Dashboard port | 8071 |

The account's own balance, equity and margin are shared by all six bots. Each strategy's own result is the sum of the
deals with its magic number.
