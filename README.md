# DEMO ONLY · demo_hedging_btcusd6 · BTCUSDm · Turtle System 2 + bot votes

This branch runs **Turtle System 2 + bot votes** on the **demo** account of slot 6 (`Exness-MT5Trial14`, login 416608968), which it shares only with
`demo_hedging_xauusd6`. It is a copy of `hedging_btcusd6`
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

Both launchers start app.py again 30 s after it exits (a crash, a lost terminal); close the window to stop the bot.

## Safety

- **Demo account only.** The bot refuses to start unless the terminal is logged into a demo, hedging account with
  the login of the credentials, refuses `live` outright, and reads the account again before every poll and every
  order: if another process logs the shared terminal into another account, nothing is sent and an ERROR line
  (`ACCOUNT_REFUSED`) appears in the strategy log until the demo account is back.
- **A broker-side backstop.** Every leg carries a stop 1 N beyond the trade's stop at its fill (the bot's own stop:
  2N from the newest fill, or the exit channel if tighter, never loosened), no target. The bot's own stop always
  closes first; the backstop only acts while the bot or the terminal is down, and a leg it closes is handled as one
  closed outside the bot.
- **A terminal that restarts.** While the terminal does not answer the bot decides nothing; after 5 s it connects
  again (5, 10, 30, then every 60 s while that fails).
- **No decision on data the poll does not have:** a positions read that fails skips the poll; an entry needs the M15
  vote of closed bars and 300 closed daily bars; a leg the terminal has not listed yet stays in the trade for 10 s.

## What keeps it apart from the other demo bots

Each slot has its own demo account, used by its gold bot and its BTC bot (slot 6: `demo_hedging_xauusd6` and
`demo_hedging_btcusd6`), so each bot is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26126 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_btcusd6` |
| Dashboard port | 8071 |

The account's own balance, equity and margin are shared by the slot's two bots. Each strategy's own result is the sum of the
deals with its magic number.
