# DEMO ONLY · demo_hedging_xauusd7 · XAUUSDm · Top 2

This branch runs **Top 2** on the **demo** account of slot 7 (`Exness-MT5Trial7`, login 434526775), which it shares only with
`demo_hedging_btcusd7`. It is a copy of `hedging_xauusd7`
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

Both launchers start app.py again 30 s after it exits (a crash, a lost terminal); close the window to stop the bot.

## Safety

- **Demo account only.** The bot refuses to start unless the terminal is logged into a demo, hedging account with
  the login of the credentials, refuses `live` outright, and reads the account again before every poll and every
  order: if another process logs the shared terminal into another account, nothing is sent and an ERROR line
  (`ACCOUNT_REFUSED`) appears in the strategy log until the demo account is back.
- **A broker-side backstop.** Every fill carries a stop 2 x the basket's stop distance beyond it (here 8 x the
  capped H1 unit; the bot's own stop is at 4), no target. The bot's own stop always closes first; the backstop only
  acts while the bot or the terminal is down.
- **A terminal that restarts.** While the terminal does not answer the bot decides nothing; after 5 s it connects
  again (5, 10, 30, then every 60 s while that fails).
- **No decision on data the poll does not have:** a positions read that fails skips the poll; an entry needs every
  vote it reads and 300 closed H1 bars; a fill the terminal has not listed yet is still the open basket for 10 s.

## What keeps it apart from the other demo bots

Each slot has its own demo account, used by its gold bot and its BTC bot (slot 7: `demo_hedging_xauusd7` and
`demo_hedging_btcusd7`), so each bot is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26117 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_xauusd7` |
| Dashboard port | 8062 |

The account's own balance, equity and margin are shared by the slot's two bots. Each strategy's own result is the sum of the
deals with its magic number.
