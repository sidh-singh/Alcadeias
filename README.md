# DEMO ONLY · demo_hedging_xauusd8 · XAUUSDm · Top 1

This branch runs **Top 1** on the **demo** account (the `demo` block of slot 8's credentials, the same
account every slot uses for demo). It is a copy of `hedging_xauusd8`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

Entries on the H1 votes in the direction of the H1 trend (the M15 votes not against); a target of 10 and a stop of 8 H1 volatility units; one add of 1 unit when the M5 MACD vote turns back with the basket at least one volatility unit against the last fill; no M15 force-close; 4 hours of pause after a losing basket.

Why this one: the most 8-year growth of all our gold designs.

## Its backtest

Final-ten study (`backtest_hedging`: `backtest_results/final10/FINAL10.md`), Exness ticks, a fresh $2,000 account per
window, the bot's unit rule (0.01 lot, plus 0.01 lot for every $2,500 of balance, at most 0.10 lot). Max DD is the
deepest fall from an equity peak.

| Window | Final equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 8 years | $15,168 | +28.8% a year | 32.5% | 1,240 |
| 5 years | $12,433 | +44.1% a year | 31.5% | 783 |
| Nov 2018 - Dec 2020 | $2,226 | +11.3% | 21.7% | 325 |
| last year | $4,165 | +108.3% | 41.9% | 158 |

Every year from 2018 to 2026 had been read by earlier studies, so this demo run is the first test on data no study has
seen.

## How to run

```bat
start_xauusd.bat           REM or: start_job.bat   (both default to demo)
start_dashboard.bat
```

## What keeps it apart from the other demo bots

All six demo branches (`demo_hedging_xauusd6/7/8`, `demo_hedging_btcusd6/7/8`) use the same demo account, so each bot
is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26118 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_xauusd8` |
| Dashboard port | 8063 |

The account's own balance, equity and margin are shared by all six bots. Each strategy's own result is the sum of the
deals with its magic number.
