# DEMO ONLY · demo_hedging_xauusd6 · XAUUSDm · V3-lite

This branch runs **V3-lite** on the **demo** account of slot 6 (`Exness-MT5Trial14`, login 416608968), which it shares only with
`demo_hedging_btcusd6`. It is a copy of `hedging_xauusd6`
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

Both launchers start app.py again 30 s after it exits (a crash, a lost terminal); close the window to stop the bot.

## Safety

- **Demo account only.** The bot refuses to start unless the terminal is logged into a demo, hedging account with
  the login of the credentials, refuses `live` outright, and reads the account again before every poll and every
  order: if another process logs the shared terminal into another account, nothing is sent and an ERROR line
  (`ACCOUNT_REFUSED`) appears in the strategy log until the demo account is back.
- **A broker-side backstop.** Every fill carries a stop 2 x the basket's stop distance beyond it (here 16 x the
  H1 unit; the bot's own stop is at 8), no target. The bot's own stop always closes first; the backstop only acts
  while the bot or the terminal is down.
- **A terminal that restarts.** While the terminal does not answer the bot decides nothing; after 5 s it connects
  again (5, 10, 30, then every 60 s while that fails).
- **No decision on data the poll does not have:** a positions read that fails skips the poll; an entry needs every
  vote it reads and 300 closed H1 bars; a fill the terminal has not listed yet is still the open basket for 10 s.

## What keeps it apart from the other demo bots

Each slot has its own demo account, used by its gold bot and its BTC bot (slot 6: `demo_hedging_xauusd6` and
`demo_hedging_btcusd6`), so each bot is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26116 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_xauusd6` |
| Dashboard port | 8061 |

The account's own balance, equity and margin are shared by the slot's two bots. Each strategy's own result is the sum of the
deals with its magic number.
