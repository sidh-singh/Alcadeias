# DEMO ONLY · demo_hedging_xauusd7 · XAUUSDm · Top 2

This branch runs **Top 2** on the **demo** account (the `demo` block of slot 7's credentials, the same
account every slot uses for demo). It is a copy of `hedging_xauusd7`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

The same entries as Top 1 (H1 votes, H1 trend, the M15 votes not against); one position per basket; a target of 8 and a stop of 4 H1 volatility units, the unit capped at $12 per 0.01 lot; no M15 force-close; 12 hours of pause after a losing basket.

Why this one: the best growth per unit of drawdown over 8 years (1.16) and the lowest drawdown of our gold designs; it lost 4.5% on the never-read Nov 2018 - Dec 2020 data.

## Its backtest

Final-ten study (`backtest_hedging`: `backtest_results/final10/FINAL10.md`), Exness ticks, a fresh $2,000 account per
window, the bot's unit rule (0.01 lot, plus 0.01 lot for every $2,500 of balance, at most 0.10 lot). Max DD is the
deepest fall from an equity peak.

| Window | Final equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 8 years | $8,545 | +19.9% a year | 17.1% | 1,316 |
| 5 years | $8,880 | +34.7% a year | 15.3% | 814 |
| Nov 2018 - Dec 2020 | $1,910 | -4.5% | 10.7% | 358 |
| last year | $4,018 | +100.9% | 17.3% | 157 |

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
| Magic number on every order; it reads and closes only these positions | 26117 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_xauusd7` |
| Dashboard port | 8062 |

The account's own balance, equity and margin are shared by all six bots. Each strategy's own result is the sum of the
deals with its magic number.
