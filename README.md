# DEMO ONLY · demo_hedging_xauusd6 · XAUUSDm · V3-lite

This branch runs **V3-lite** on the **demo** account (the `demo` block of slot 6's credentials, the same
account every slot uses for demo). It is a copy of `hedging_xauusd6`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

The bot's own RSI/MACD logic, tuned: entries on the H1 votes (with the M15 votes agreeing) only in the direction of the H1 trend; one position per basket (no ladder); a target and a stop of 8 x the H1 volatility unit each, fixed when the basket opens; no M15 force-close; 12 hours of pause after a losing basket.

Why this one: the final ten's most dependable gold design: the most equity of the ten over 8 and 5 years, and the best result on the never-read Nov 2018 - Dec 2020 data.

## Its backtest

Final-ten study (`backtest_hedging`: `backtest_results/final10/FINAL10.md`), Exness ticks, a fresh $2,000 account per
window, the bot's unit rule (0.01 lot, plus 0.01 lot for every $2,500 of balance, at most 0.10 lot). Max DD is the
deepest fall from an equity peak.

| Window | Final equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 8 years | $11,957 | +25.0% a year | 33.0% | 809 |
| 5 years | $10,748 | +40.0% a year | 30.6% | 517 |
| Nov 2018 - Dec 2020 | $2,340 | +17.0% | 8.5% | 201 |
| last year | $3,656 | +82.8% | 45.3% | 99 |

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
| Magic number on every order; it reads and closes only these positions | 26116 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_xauusd6` |
| Dashboard port | 8061 |

The account's own balance, equity and margin are shared by all six bots. Each strategy's own result is the sum of the
deals with its magic number.
