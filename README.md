# DEMO ONLY · demo_hedging_btcusd8 · BTCUSDm · Top 2

This branch runs **Top 2** on the **demo** account (the `demo` block of slot 8's credentials, the same
account every slot uses for demo). It is a copy of `hedging_btcusd8`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

The bot's RSI/MACD logic, tuned: entries on the H1 votes in the direction of the H1 trend (the M15 votes not against); one position per basket; a target of 10 and a stop of 8 H1 volatility units; no M15 force-close; 4 hours of pause after a losing basket.

Why this one: the lowest drawdown of our BTC designs over 8 years.

## Its backtest

Final-ten study (`backtest_hedging`: `backtest_results/final10/FINAL10.md`), Exness ticks, a fresh $2,000 account per
window, the bot's unit rule (0.01 lot, plus 0.01 lot for every $2,500 of balance, at most 0.10 lot). Max DD is the
deepest fall from an equity peak.

| Window | Final equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 8 years | $4,149 | +9.5% a year | 16.6% | 1,110 |
| 5 years | $3,919 | +14.4% a year | 16.1% | 675 |
| Nov 2018 - Dec 2020 | $2,081 | +4.1% | 2.3% | 322 |
| last year | $2,119 | +5.9% | 13.1% | 138 |

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
| Magic number on every order; it reads and closes only these positions | 26128 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_btcusd8` |
| Dashboard port | 8073 |

The account's own balance, equity and margin are shared by all six bots. Each strategy's own result is the sum of the
deals with its magic number.
