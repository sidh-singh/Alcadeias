# DEMO ONLY · demo_hedging_xauusd8 · XAUUSDm · Top 1

This branch runs **Top 1** on the **demo** account of slot 8 (`Exness-MT5Trial14`, login 416608971), which it shares only with
`demo_hedging_btcusd8`. It is a copy of `hedging_xauusd8`
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
start_xauusd.bat           REM or: start_job.bat   (both default to demo)
start_dashboard.bat
```

Both launchers start app.py again 30 s after it exits (a crash, a lost terminal); close the window to stop the bot.

The tests need no terminal and write only into pytest's own tmp folders. Run them from the branch folder with
`python3 -B -m pytest tests_demo -q -p no:cacheprovider` (`-B` keeps Python's bytecode out of the branch; a run
without it fails at its end).

## The dashboard

`start_dashboard.bat` (or `python dashboard.py`) serves it on port 8063 of this PC (`DASHBOARD_PORT`;
`http://localhost:8063`; the first start installs dash 2.18.2 and plotly 5.24.1, the versions of `requirements.txt`).
It only reads the files below (it never talks to the terminal), refreshes every 5 s, and shows times in UTC like the
log. One `dashboard.py` serves the basket branches and the Turtle branches: it reads the strategy from the bot's
trace, so here it draws the basket's page.

**The dashboard has no login.** Anyone who can reach port 8063 sees this bot's account figures, its trades and its
logs. Open the port in the server's firewall only to your own IP address, or open the dashboard on the server itself
(`http://localhost:8063`). It shows only the bot's own files in its output folder: a request for any other file
(for example `mt5_credentials.json`) is refused. The page shows no folder of the PC (a traceback shows `app.py`, not
its folder); only the Log tab's copy box has the full path of the day's file.

- **Status bar** (on every tab): the symbol, the design, the branch and its magic number; whether the bot's data is
  fresh, the demo-account check, the terminal, the market, errors in the last hour; the virtual balance, the unit and
  lot, this bot's open and closed P/L and its equity, the shared demo account, how long the bot has run. When the bot
  has not written for a minute, the first chip is red, the others are grey with the time of its last poll ('as of
  09:10'), and a red banner says the page shows that poll, not now.
- **Live**: *what the bot is doing now*: the action and the bot's own one-sentence reason, every check in the order
  the bot makes it (✓ passed, ✗ blocks, ⚡ fires, ○ not yet; the one that decided is marked) with its value against
  the rule, and the strategy's numbers: the open and agreement scores against their thresholds, every timeframe's
  RSI and MACD vote with its pivot and slope (and a small chart of each), the trend, the volatility unit, the pause
  countdown after a loss, what a new basket would get (entry, target, stop, backstop). Then the **price chart**
  (M1 / M5 / M15 / H1 / D1, bid): every entry (▲ buy, ▼ sell, one per leg), every exit (✕, green won, red lost) with
  its reason and P/L and a dotted line from its entries, the open basket's legs and its levels as labelled lines
  (target, stop, average price, the broker backstops, the next add when the design has a ladder, the bid and the
  ask); hover any mark for its details. The candles are bid prices: a level the bot compares with the ask (a sell
  basket's stop and target, a buy basket's next add) says '(ask)'. Then the **open position** (the basket's P/L
  between its stop and its target, its levels and legs; when flat, the last trade) and the **latest events**.
- **How close is it** (at the top of Live, under the bot's sentence): for an open position, a meter from the entry to
  the target and one to the stop loss (the Turtle has no target: its stop and its next add). Each meter says how far
  it has gone (percent), and the distance in price and in $. It turns **amber from 70 %** and **red from 90 %**. Below
  it: the P/L in $ and in price, the time in the trade, the legs and the lot, the virtual balance, the spread and the
  last tick. For a flat bot: which entry conditions pass and which one is missing; on a Turtle branch also how far the
  price is from today's BUY and SELL level (the meter fills over the last 2 N).
- **The alert banner** (on every tab, under the tabs): amber or red when a meter passes 70 % or 90 %, with the words
  of that meter. Tick **sound** or **browser notification** in the tab bar to hear a beep or get a notification
  when it starts or gets worse (the browser remembers the choice; it asks once for the notification). A stale bot
  gives no alert: its numbers are old.
- **Trades**: the summary (trades, win rate, net P/L, largest loss, max drawdown of the virtual balance, profit
  factor), the virtual balance after every close, and every trade, newest first (click one for its legs, its profit,
  swap and commission, and the exit reason the bot recorded).
- **Log**: the events with level filters (ERROR, WARN, ORDER, FILL, CLOSE, INFO, DEBUG), a search (type, then press
  Enter), live or paused; the raw text of any day; the path of today's text log to copy and a button that downloads a
  day's file.
  **When something looks wrong, send that day's file.**
- **Changes & issues**: every WARN and ERROR line of the bot, grouped by kind (for example `TERMINAL_IN_USE`,
  `ACCOUNT_REFUSED`, `RECONNECT_FAILED`), with how many, the first and the last time, what it means and what to do.
  Below it, this branch's `CHANGELOG.md`, version by version (the newest open).
- **History & settings**: the old views (daily trades, the lifetime summary, the old strategy log), the settings the
  bot started with (a value `constants.py` has changed since is marked: the bot takes it at its next start), and the
  raw files.

## What it writes for the dashboard, and its log

Next to the files the old dashboard reads, the bot writes into its output folder (every field:
`docs/dashboard-data.md`; `tracelog.py`, which writes them, is the same file on all six demo branches):

- `XAUUSDm_trace.json`: after every poll, what the bot sees and decides: one sentence on what it does now and why,
  every check in the order it makes them (passed, blocked, fired), the votes, the trend, the volatility unit, the
  pause, and the open basket with its stop, target and backstop as prices;
- `XAUUSDm_bars.json`: the bars for the chart (M1, M5, M15, H1, D1), `XAUUSDm_trades.json`: every basket with its
  open, close, P/L and exit reason, and the virtual-balance curve;
- `logs\XAUUSDm_<YYYY-MM-DD>.log`: the detailed text log (UTC days, kept 30 days): the start-up and every constant,
  every decision change, order, fill, close, pause, reconnect and error with its traceback, and a heartbeat line
  every minute; also every safety refusal of the section below (a terminal that holds another account, the account
  refused, every failed reconnect attempt, a basket leg closed outside the bot). When something looks wrong, this
  file (and `logs\XAUUSDm_events.jsonl`) is the one to send.

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
  H1 unit; the bot's own stop is at 8), no target. The bot's own stop always closes first; the backstop only acts
  while the bot or the terminal is down, and a position it closes is booked as closed outside the bot (its
  realised loss, then the pause after a loss). If it closes only the entry (the entry's backstop lies nearer than
  the add's), the bot closes the add on the first poll that finds the entry gone and books the whole basket as
  closed outside the bot.
- **A terminal that restarts.** While the terminal does not answer the bot decides nothing; after 5 s it connects
  again (5, 10, 30, then every 60 s while that fails; `RECONNECT_FAILED` in the strategy log once for each reason,
  then every 15 minutes, so a long outage does not push everything else out of it).
- **No decision on data the poll does not have:** a positions read that fails skips the poll; an entry needs every
  vote it reads and 300 closed H1 bars, the add its M5 vote; a fill the terminal has not listed yet is still the
  open basket for 10 s.

## What keeps it apart from the other demo bots

Each slot has its own demo account, used by its gold bot and its BTC bot (slot 8: `demo_hedging_xauusd8` and
`demo_hedging_btcusd8`), so each bot is fenced off:

| | This bot |
|---|---|
| Magic number on every order; it reads and closes only these positions | 26118 |
| Sizing | from a virtual $2,000 plus its own closed profit and loss (deals with its magic number), as in the backtest |
| Output folder (JSON, logs, daily trades) | `C:\Alcadeias\demo_hedging_xauusd8` |
| Dashboard port | 8063 |

The account's own balance, equity and margin are shared by the slot's two bots. Each strategy's own result is the sum of the
deals with its magic number.
