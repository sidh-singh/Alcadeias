# DEMO ONLY · demo_hedging_btcusd7 · BTCUSDm · Turtle System 1 + bot votes

This branch runs **Turtle System 1 + bot votes** on the **demo** account of slot 7 (`Exness-MT5Trial7`, login 434526775), which it shares only with
`demo_hedging_xauusd7`. It is a copy of `hedging_btcusd7`
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

Both launchers start app.py again 30 s after it exits (a crash, a lost terminal); close the window to stop the bot.

## Safety

- **One MT5 installation per slot, never shared with a live bot.** Install a separate MetaTrader 5 for slot 7 (its
  own folder; its `terminal64.exe` is the `terminal_path` in `mt5_credentials.json`) and let only the slot's two
  demo bots use it (`demo_hedging_xauusd7` and `demo_hedging_btcusd7`, on the slot's one account). Never point a
  demo bot at the terminal of a live bot or of another slot: a login switches the account of every program
  attached to that terminal. The bot itself logs in only on a terminal that holds no account; a terminal that
  holds its own account (the login and server of the credentials) it uses as it is; one logged into any other
  account it leaves alone: no login, an ERROR line `TERMINAL_IN_USE` in the strategy log (once, then every 15
  minutes), and it tries again (at start-up 3 times, then the launcher restarts it; on a reconnect every 60 s).
  Only separate installations close the last gaps: a switch by another program in the microseconds between the
  bot's account check and its order reaching the terminal, and a terminal that is still logging into its saved
  account when the bot attaches (it reads as holding no account, and the bot logs in).
- **Demo account only.** The bot refuses to start unless the terminal is logged into a demo, hedging account with
  the login of the credentials, refuses `live` outright, and reads the account again before every poll, right
  after the poll reads its positions, and before every order: if another program logs the terminal into another
  account, nothing is synced or sent and an ERROR line (`ACCOUNT_REFUSED`) appears in the strategy log until the
  demo account is back.
- **A broker-side backstop.** Every leg carries a stop 1 N beyond the trade's stop at its fill (the bot's own stop:
  2N from the newest fill, or the exit channel if tighter, never loosened), no target. The bot's own stop always
  closes first; the backstop only acts while the bot or the terminal is down. A leg it closes was closed beyond the
  trade's stop, so when the bot finds it gone it closes the other legs at once, even if the price is back by then
  (the deal history tells it from a leg closed by hand inside the stop, which leaves the trade on).
- **A terminal that restarts.** While the terminal does not answer the bot decides nothing; after 5 s it connects
  again (5, 10, 30, then every 60 s while that fails; `RECONNECT_FAILED` in the strategy log once, then every 15
  minutes, so a long outage does not push everything else out of it).
- **No decision on data the poll does not have:** a positions read that fails skips the poll; an entry needs the M15
  vote of closed bars and 300 closed daily bars; a leg the terminal has not listed yet stays in the trade for 10 s.

## What keeps it apart from the other demo bots

Each slot has its own demo account, used by its gold bot and its BTC bot (slot 7: `demo_hedging_xauusd7` and
`demo_hedging_btcusd7`), so each bot is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26127 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_btcusd7` |
| Dashboard port | 8072 |

The account's own balance, equity and margin are shared by the slot's two bots. Each strategy's own result is the sum of the
deals with its magic number.
