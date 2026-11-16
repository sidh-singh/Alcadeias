# DEMO ONLY · demo_hedging_btcusd8 · BTCUSDm · Top 2

This branch runs **Top 2** on the **demo** account of slot 8 (`Exness-MT5Trial14`, login 416608971), which it shares only with
`demo_hedging_xauusd8`. It is a copy of `hedging_btcusd8`
(the same files and launchers) with the strategy changed. **Live mode is disabled:** `mt5_credentials.json` holds only the
`demo` block, and the launchers refuse `live`.

## What it trades

The bot's RSI/MACD logic, tuned: entries on the H1 votes in the direction of the H1 trend (the M15 votes not against); one position per basket; a target of 10 and a stop of 8 H1 volatility units (the unit capped at $12 per 0.01 lot, a cap that has never bound on BTC); no M15 force-close; 4 hours of pause after a losing basket.

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

1. **First, install this slot's own MetaTrader 5.** Install a separate MetaTrader 5 for slot 8, in its own folder
   (for example `C:\MT5\slot8`), and set `terminal_path` in `mt5_credentials.json` to its `terminal64.exe`. The
   gold and BTC bots of slot 8 both use this one. `mt5_credentials.json` still names the live bots' MetaTrader 5
   (`C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`); until you change it, the bot does not start and writes
   `LIVE_TERMINAL_PATH` in the strategy log.
2. **Then log that MetaTrader 5 into the slot's demo account once, by hand.** Open it, log in to login 416608971 on
   `Exness-MT5Trial14` and tick "Save password". From then on the terminal logs into this account by itself when it
   starts, and the bot finds it there: it never has to log in itself (it would only on a terminal that shows no
   account for 15 s).
3. Start the bot and the dashboard:

```bat
start_btcusd.bat           REM or: start_job.bat   (both default to demo)
start_dashboard.bat
```

Both launchers start app.py again 30 s after it exits (a crash, a lost terminal); close the window to stop the bot.

The tests need no terminal and write only into pytest's own tmp folders. Run them from the branch folder with
`python3 -B -m pytest tests_demo -q -p no:cacheprovider` (`-B` keeps Python's bytecode out of the branch; a run
without it fails at its end).

## Safety

- **One MT5 installation per slot, never shared with a live bot.** Install a separate MetaTrader 5 for slot 8 (its
  own folder; its `terminal64.exe` is the `terminal_path` in `mt5_credentials.json`) and let only the slot's two
  demo bots use it (`demo_hedging_xauusd8` and `demo_hedging_btcusd8`, on the slot's one account). Never point a
  demo bot at the terminal of a live bot or of another slot: a login switches the account of every program
  attached to that terminal.
- **The live bots' MetaTrader 5 is refused.** While `terminal_path` names
  `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe` (in any spelling: upper or lower case, `/` or `\`, its
  folder) or is empty, the bot does not start. It stops before it attaches to any terminal and writes one ERROR line
  `LIVE_TERMINAL_PATH` in the strategy log: "install a separate MetaTrader 5 for slot 8 and set terminal_path in
  mt5_credentials.json to its terminal64.exe". While the launcher keeps restarting it, the line comes again every
  15 minutes; nothing else happens.
- **No login over another account.** The bot logs in only on a terminal that shows no account for 15 s. A terminal
  that holds its own account (the login and server of the credentials) it uses as it is. One logged into any other
  account it leaves alone: no login, an ERROR line `TERMINAL_IN_USE` in the strategy log (once for each account it
  finds, then every 15 minutes), and it tries again (at start-up 3 times, then the launcher restarts it; on a
  reconnect every 60 s). A first "no account" answer is not trusted: after an IPC error the bot detaches and tries
  again later; otherwise it reads the account again every second for 15 s. **Guaranteed:** no login on a terminal
  that answers with another account, or that is still starting within those 15 s. **Not covered:** a terminal that
  needs more than 15 s to log into its saved account reads as holding none, and the bot logs in; another program that
  logs in on the same terminal while the bot still reads "no account" (that login is still being authorised when the
  15 s end) is logged over, and the last login wins; and another program can switch the account in the microseconds
  between the bot's account check and its order reaching the terminal. Only separate installations close these gaps.
  On this slot's own MetaTrader 5, logged into the slot's demo account by hand (step 2 of "How to run"), none of them
  can switch another program's account: the slot's two bots use the same account.
- **Demo account only.** The bot refuses to start unless the terminal is logged into a demo, hedging account with
  the login of the credentials, refuses `live` outright, and reads the account again before every poll, right
  after the poll reads its positions, and before every order: if another program logs the terminal into another
  account, nothing is booked or sent and an ERROR line (`ACCOUNT_REFUSED`) appears in the strategy log until the
  demo account is back.
- **A broker-side backstop.** Every fill carries a stop 2 x the basket's stop distance beyond it (here 16 x the
  H1 unit, the unit capped at $12 per 0.01 lot as for the bot's stop; the bot's own stop is at 8), no target. The
  bot's own stop always closes first; the backstop only acts while the bot or the terminal is down, and a position
  it closes is booked as closed outside the bot (its realised loss, then the pause after a loss).
- **A terminal that restarts.** While the terminal does not answer the bot decides nothing; after 5 s it connects
  again (5, 10, 30, then every 60 s while that fails; `RECONNECT_FAILED` in the strategy log once for each reason,
  then every 15 minutes, so a long outage does not push everything else out of it).
- **No decision on data the poll does not have:** a positions read that fails skips the poll; an entry needs every
  vote it reads and 300 closed H1 bars; a fill the terminal has not listed yet is still the open basket for 10 s.

## What keeps it apart from the other demo bots

Each slot has its own demo account, used by its gold bot and its BTC bot (slot 8: `demo_hedging_xauusd8` and
`demo_hedging_btcusd8`), so each bot is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26128 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_btcusd8` |
| Dashboard port | 8073 |

The account's own balance, equity and margin are shared by the slot's two bots. Each strategy's own result is the sum of the
deals with its magic number.
