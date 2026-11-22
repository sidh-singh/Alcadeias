<!-- branch:start -->
# REAL MONEY · live6_xv3 · XAUUSDm · V3-lite

This branch is one bot. It trades **XAUUSDm** with **real money** on **account 6**. The BTC bot of the same
account is the branch `live6_bs2`. The table holds what belongs to this branch only. Everything below the table
is the same on all 20 real-money branches.

| | This branch |
|---|---|
| Branch | `live6_xv3` |
| Account | account 6: one real Exness MetaTrader 5 account (hedging, in US dollars), shared with the BTC bot `live6_bs2` |
| Strategy | V3-lite on XAUUSDm: the design you tested on `demo_hedging_xauusd6`. Section 1 says what it trades |
| Size | half of the account balance counts for this bot. 1 unit = 0.01 lot. 2 units from an account balance of $3,500, one more unit for every further $3,500, at most 10 units |
| Safety: drop from the high | both bots of the account are blocked at 25% below the highest balance. From $1,500 that is a balance of $1,125.00, a fall of $375.00 |
| Safety: loss in one day | both bots of the account are blocked at 15% lost since 00:00 UTC. On $1,500 that is $225.00 |
| Safety: losing trades in a row | this bot is blocked after 6 losing trades in a row (the BTC bot `live6_bs2` after 5) |
| Start the bot | `start_xauusd.bat live` (the same as `start_job.bat live`) |
| Dashboard | `start_dashboard.bat`, then http://localhost:8106 on the server (port 8106) |
| Bot folder: logs, journal, state | `C:\Alcadeias\live6_xv3` |
| Account folder: safety files, the PIN | `C:\Alcadeias\live6_account` |
| Credentials file | `mt5_credentials.json` in this branch, the block `live`. `live6_bs2` must hold the same values |
| Magic number of its orders | 270611 |
<!-- branch:end -->

**Read sections 2 and 3 before the first start.** The launchers (`.bat` files) of this version have been checked
line by line, but they have never run on a Windows server. Do the first start of each account while you watch.

## 1. What this branch is

- **One branch is one bot:** one symbol, one strategy, one real account. There are 20 of them: 10 accounts, each
  with a gold bot and a BTC bot. The two bots of an account share its MetaTrader 5 and its safety. Each bot has
  its own dashboard.
- **It is the bot you tested on the demo branches, plus what real money needs:** it trades only its own real
  account, it counts half of the balance, it has the safety of section 3, and it writes more for later study.
- **The strategy itself is not changed.** With the safety OFF, or ON as long as it has not held back any trade,
  the bot sends the same orders as the demo bot of the same design. Only the size of its trades follows the real
  account (section 4). It acts differently only when something is wrong: it opens no new trade while it cannot
  read the balance or while an old bot uses its MetaTrader 5, and after 4 minutes of refused orders it tries to
  open less often (section 6).
- **It has no demo mode.** It starts only with the word `live`, and it trades only a real hedging account in US
  dollars. To try something, use the demo branches: they stay as they are.
- **The account number is not shown in full on the page or in a file.** The dashboard, the logs and the files show
  its last 4 digits, for example `...1234`. Only the bot's own window on the server shows the whole number. The
  zip you send with `collect_logs.bat` holds neither the number nor anything that gives it back (section 5).

The five designs. The table at the top says which one this branch runs.

| Code in the branch name | Design | Tested on | What it trades | 2 units from an account balance of |
|---|---|---|---|---|
| `xv3` | gold V3-lite | `demo_hedging_xauusd6` | Entries on the H1 votes, with the M15 votes agreeing, only in the direction of the H1 trend. One position per trade. A target and a stop of 8 x the H1 volatility unit each, fixed when the trade opens. 12 hours of pause after a losing trade. | $3,500 |
| `xt2` | gold Top 2 | `demo_hedging_xauusd7` | Entries on the H1 votes in the direction of the H1 trend, the M15 votes not against. One position per trade. A target of 8 and a stop of 4 volatility units, the unit capped at $12 per 0.01 lot. 12 hours of pause after a losing trade. | $2,500 |
| `xt1` | gold Top 1 | `demo_hedging_xauusd8` | The same entries. A target of 10 and a stop of 8 volatility units. One addition of 1 unit when the M5 MACD vote turns back with the trade at least one volatility unit against the last fill. 4 hours of pause after a losing trade. | $3,500 |
| `bt2` | BTC Top 2 | `demo_hedging_btcusd8` | The same entries on BTC. One position per trade. A target of 10 and a stop of 8 volatility units. 4 hours of pause after a losing trade. | $2,500 |
| `bs2` | BTC Turtle System 2 + bot votes | `demo_hedging_btcusd6` | The Turtle trend follower on daily UTC bars: a breakout of the 55-day high (buy) or low (sell), taken only when the M15 votes on closed bars agree. 1 more unit every half N, up to 4. One stop for all of them at the tighter of 2N from the last fill and the 20-day opposite channel, never loosened. No target. | $5,000 |

## 2. First start

Do these steps in this order, once for each account. `<branch>` stands for the branch name in the table at the
top; the other branch of the account is named there too.

1. **Clone each branch into its own folder** `C:\AlcadeiasBots\<branch>`:

   ```bat
   git clone -b <branch> --single-branch <address of the repository> C:\AlcadeiasBots\<branch>
   ```

   - Never clone inside `C:\Alcadeias`: that is where the bots write their files.
   - Never put two branches into one folder.
   - Never run `git checkout` of another branch in such a folder. A running launcher would start the other
     branch's files with this branch's settings.
   - Do not change files in these folders on the server. A file changed there stops the next `git pull`.

2. **Stop the old bots of this account.**
   - Stop the old gold bot and the old BTC bot of this account, and switch off whatever starts them (a Jenkins
     job, a Task Scheduler task, the Startup folder).
   - Close their open trades by hand. After the stop nobody manages them, and the old bot's buys have no stop.
   - Check that `C:\Alcadeias\account.json`, `C:\Alcadeias\XAUUSDm.json` and `C:\Alcadeias\BTCUSDm.json` have not
     changed for 2 minutes (the column "Date modified" in Explorer). The old bots rewrite these files all the
     time: a fresh time means an old bot is still running. The new bots look at the same three files.
   - Why: an old bot takes every trade on its symbol for its own. It would close this bot's trades at $1 of
     profit and add to them. The safety cannot stop an old bot.

3. **Start the bot once BEFORE you change the credentials.** In the branch folder run:

   ```bat
   start_job.bat live
   ```

   Do this in both folders of the account. At the very first start on a server the window may first install the
   bot's Python packages; that is normal.

   It must print a line about `mt5_credentials.json` that says the file `still names the old account`. The line
   comes more than once: the bot tries three times, 5 seconds apart. Then the window must say that the branch
   `has stopped and will NOT start again by itself`. That is the right result: it proves Python, the packages and
   the launcher on this server, and nothing was traded.
   If the window says anything else, or says that the bot `starts again in 30 seconds`, close it and send what
   it printed before you go on.

4. **One MetaTrader 5 for each account, installed and logged in by hand.** Do this only after the old bots are
   stopped (step 2): an old bot that still runs trades whatever account its MetaTrader 5 is logged into.
   - Each account needs its own MetaTrader 5 installation. If the server holds a second account, install a
     second MetaTrader 5 for it, in a folder of its own.
   - Note the full path of the `terminal64.exe` of this account's installation, for example
     `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`. It goes into `terminal_path` in step 5.
   - Open that MetaTrader 5. Choose File > Login to Trade Account, enter the account, and tick "Save password".
   - Switch "Algo Trading" on.
   - If a demo bot still uses this MetaTrader 5, it stops trading the moment the real account is logged in. Stop
     it first, or give the demo bots a MetaTrader 5 of their own.
   - The bot never switches a MetaTrader 5 to another account. If it finds another account there, it does not
     trade and tries again every 30 seconds. It never logs in a MetaTrader 5 that an old bot uses, also not after
     that MetaTrader 5 has restarted.

5. **Put the new account's details into `mt5_credentials.json`, on GitHub, in both branches of the account, and
   nowhere else.** Change only the four values of the block `live`:

   ```json
   "live": {
       "terminal_path": "C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe",
       "login_id": 12345678,
       "login_pass": "the password of the account",
       "server": "Exness-MT5Real8"
   }
   ```

   - The values above are examples. Keep every quote and every comma as it is. Write every backslash of
     `terminal_path` twice.
   - `terminal_path` is the path of the `terminal64.exe` of this account's MetaTrader 5 installation, which you
     noted in step 4.
   - Both branches of the account get the same four values.
   - Then run `git pull` in both folders on the server. If git says that local changes would be overwritten, run
     `git checkout -- mt5_credentials.json` and pull again.
   - The bot refuses to start as long as the file names the old account.
   - Only if a branch must really go on trading its old account: add `"keep_old_account": true` to the block
     `live`, and make sure the old bot of that account is stopped.

6. **Fund the account.** The limits of the safety are percentages. The dollar figures in the table at the top
   are for a start of $1,500. A deposit or a withdrawal is not counted as a profit or a loss.

7. **Open the dashboard's port to your own IP address only, before the dashboards start.** The page has no
   login: anyone who can reach the port sees the account's figures and can try the buttons, and the PIN is sent
   without encryption. In a command window opened with "Run as administrator", for each of the two ports of the
   account:

   ```bat
   netsh advfirewall firewall add rule name="Alcadeias dashboard <port>" dir=in action=allow protocol=TCP localport=<port> remoteip=<your own IP address>
   ```

   - `<port>` is the port in the table at the top of each branch. From your own PC the address of the page is
     then `http://<address of the server>:<port>`.
   - Check that Windows Defender Firewall is On: in the same window, `netsh advfirewall show allprofiles state`
     must show `State ON` for every profile. While the firewall is off, the rule above changes nothing and the
     page is open to everybody. If it is off, ask the server's provider to switch it on: switched on without a
     rule for Remote Desktop, the firewall shuts you out of the server.
   - When a dashboard starts for the first time (step 8), Windows may ask whether python.exe may accept
     connections. Choose **Cancel**. "Allow access" lets everybody in, on every port, whatever the rule above
     says.
   - If another rule already lets Python or this port in from everywhere, the page is still open to everybody:
     remove that rule in "Windows Defender Firewall with Advanced Security", under Inbound Rules. The old
     dashboards may have made one. If the server's provider has a firewall of its own, set the same limit there.
   - On a network you do not trust, press the buttons on the server itself (the address with `localhost`), or
     use `safety.bat` (section 3).

8. **Start the gold bot, then the BTC bot, then the two dashboards.**
   - In the gold branch's folder: `start_job.bat live`. Wait one minute and check that its window shows no
     error. Look at the window, but never click inside it (section 6, "Rules for every day").
   - In the BTC branch's folder: `start_job.bat live`.
   - In each of the two folders: `start_dashboard.bat`. The first start builds the dashboard's own Python
     environment, which takes a minute or two. Then the window prints the address of the page. If Windows asks
     whether python.exe may accept connections, choose Cancel (step 7).
   - Run the four windows of an account as the same Windows user.
   - A window of a bot starts the bot again 30 seconds after it ends. It stops and waits only when something
     needs you, and prints what.

9. **Find the PIN.** The buttons of the safety ask for a PIN. It is in the file `safety_pin.txt` in the account
   folder (the table at the top gives the folder). The file is made when a dashboard of the account starts for
   the first time, and the dashboard's window prints where it is. The two dashboards of an account use the same
   PIN. You may replace it with your own: 4 to 32 letters and digits, no blanks, saved as UTF-8.

10. **Check the page of each bot.** Open the address the dashboard printed, and look for:
    - the badge `LIVE · REAL MONEY` beside the title;
    - a green chip `Real account ...1234 · hedging` with the last 4 digits of your own account;
    - the tile "Account balance" with the money you paid in;
    - the tile "Unit · lot" with a line like `half of $1,500.00 = $750.00 -> 1 unit (0.01 lot)`;
    - at the very top the green bar `SAFETY ON`, with the three meters and the limits of the table at the top;
    - the line of the other bot of the account, saying that it is running;
    - no red banner.

## 3. The safety

The safety stops a bot from opening new trades when the account has lost too much. It shows as a bar at the top
of every tab of the dashboard: its state, three meters, the PIN field and the buttons.

**The three rules.** The limits of this account are in the table at the top.

1. **Drop from the high** (the account; it blocks both bots): the balance is that many percent, or more, below
   the highest balance since the safety last started counting.
2. **Loss today** (the account; it blocks both bots): the balance is that many percent, or more, below the
   balance at 00:00 UTC.
3. **Losing trades in a row** (this bot only): this bot closed that many trades in a row with a loss (profit,
   swap, commission and fee together). A winning trade sets the count back to 0.

- **Only closed trades count.** The rules read the booked balance. An open trade counts when it closes.
- **The meters** show how much of each limit is used. A meter turns amber from 70% of its limit and red from 90%.
- **A deposit or a withdrawal is not a profit or a loss.** When the balance falls to a limit, the bot first checks
  in the account's history, for up to 1 minute, that it was a loss and not a withdrawal. The bar then says
  `CHECKING`, and no new trade is opened until it knows. If the history cannot be read within that minute, the
  fall counts as a loss.
- **`CHECKING` also shows for a moment after a trade closes** when that trade could be the last losing trade of
  the limit: the bot waits for its result before it opens anything new.

**What "blocked" means.**

- The bot opens **no new trade** and **adds nothing to an open trade**.
- **Open trades are not closed.** They keep their normal management: their stop, their target, the strategy's own
  close, and the emergency stop at the broker.
- **A block never ends by itself.** It stays until you press Unblock (turning the safety OFF and then ON also ends
  it, and starts the counting again). Look at the dashboards every day. A new block also raises the alert
  banner, with the sound and the browser notification if you ticked them.
- **The Turtle bots after a block:** an add that was held back (by a block, a check or an old bot) is taken later
  only while the price is not more than one add step beyond that add's level. Farther away the trade takes no
  more adds. Its stop and its exit do not change.

**The buttons.**

| Button | PIN | What it does |
|---|---|---|
| **Unblock**, after an account block | yes | Counting starts again from now for both bots: the high becomes the balance of now, today's loss counts from now, both counts of losing trades go to 0. |
| **Unblock**, after a block for losing trades | yes | That bot's count of losing trades goes back to 0. The account's high and today's loss stay as they are. |
| **Turn safety OFF** | yes | No limit blocks anything: both bots trade as the strategy says. The meters go on, for information only. |
| **Turn safety ON** | no | Counting starts from the current balance. |

- After Unblock, or after OFF, a bot whose signal still stands may open a trade within seconds.
- Type the PIN before you press. 5 wrong PINs in a row lock Unblock and OFF for 10 minutes, and longer each time
  it happens again, up to 24 hours. Turn safety ON always works.
- If the bar says `SAFETY CHECK FAILED`, the bot could not check the safety and opens no new trade until it can,
  or until you turn the safety OFF. Open trades are still managed.

**On the server, without the PIN:** `safety.bat` in the branch folder does the same for the account of that
branch. Whoever can use the server can use it.

```bat
safety.bat status
safety.bat unblock
safety.bat on
safety.bat off
```

- `safety.bat unblock` always starts the counting again for the whole account: the high, today's loss and both
  counts of losing trades. That is more than the button does after a block for losing trades.
- `safety.bat unblock` also repairs a damaged file of the safety: `safety_restart.json`, the file that says when
  the counting last started, for example after it was opened and saved again in another program. A button then
  answers that the files of the safety cannot be read, and tells you to run `safety.bat unblock` on the server.
  It writes the file anew and says so; both bots count again from the current balance.
- `safety.bat new-account` is only for an account folder that moves to a new account number. Stop both bots
  first, run it, then start them again.

## 4. Size

- **Each bot counts half of the account balance**, because two bots trade one account.
- **1 unit is 0.01 lot.** A bot trades 1 unit until half of the balance reaches its step, then 2 units, and one
  more unit for each further step, at most 10. The table at the top gives the account balance where the second
  unit starts; the table in section 1 gives it for all five designs.
- **The size is set when a trade opens** and stays for that trade. A deposit that takes the balance over a step
  raises the size of the next trade, not of the open one.
- **Without a balance there is no new trade:** if the bot cannot read the balance, or the account holds no money,
  it opens no new trade until it can.
- **Compared with the demo run:** with $1,500 every bot starts at 1 unit. On their demo accounts the two Top 2
  bots (gold and BTC) traded 2 units, so here their profits and losses in dollars are about half of what you saw
  there.

## 5. Logs and what is kept

Each bot writes into its own folder (the bot folder of the table at the top). The two bots of an account share
the account folder.

| Where | What | Kept |
|---|---|---|
| bot folder, `logs\` | The detailed log, one file for each UTC day: every decision, order, fill, close, warning and error. Beside it the same lines as JSON, and one line of figures a minute (prices, spread, balance, the safety meters). | today and the 7 days before it |
| bot folder, `journal\` | The journal, one file a year: every start, every order with its fill and its slippage, every closed trade, every block and button press the bot saw, every problem when it starts and ends, one line for every day. It stays small. | for good |
| bot folder, `state\` | What the bot must remember when it is started again: the open trade, the counts of the safety, the closed trades the journal already has, when it first traded this account. | for good |
| bot folder, `daily_trade\` | The day files of the History tab. | the newest 400 days |
| account folder | The files of the safety, and which account the folder belongs to. `safety_audit.jsonl` lists every button press, every block and every new start of the counting. | for good |
| `C:\Alcadeias\terminal_claims` | Which account each MetaTrader 5 of the server belongs to: a bot never logs a MetaTrader 5 of another account in. | for good |

- The bot deletes old log days itself, and it keeps its logs under about 500 MB.
- If the disk has less than 2 GB free, the bot stops writing its detailed lines (DEBUG and INFO) and the figures
  of every minute, and the dashboard shows the red banner `DISK_LOW`. The lines of every order, fill and close,
  every warning and every error, and the journal are still written.

**To send the logs: `collect_logs.bat`.** Run it in the branch folder (a double-click is enough). The bot may keep
running.

- It writes one zip file into `C:\Alcadeias\exports` and prints the full path of the file.
- The zip holds the logs, the journal, the state, the day files, the `.json` files at the top of the bot folder
  and the files of the account folder.
- It never holds `mt5_credentials.json` or the PIN.
- Some files on the server hold a fingerprint of the account number, by which the bot knows its account. In the
  zip each fingerprint is replaced by a random token, so the zip holds neither the account number nor anything
  that gives it back.
- It keeps the newest 5 zip files of the branch and deletes its older ones.
- It refuses to write when that would leave less than 2 GB free on the disk.
- Run it in both branches of the account and send both zip files.

## 6. Warnings and what to do

**In the window of the bot**

`... has stopped and will NOT start again by itself.` Only you can fix the cause. The lines above that one say
which it is:

- The credentials file still names the old account: step 5 of section 2.
- The credentials file is missing, has a typing mistake (the line names the place), is not saved as UTF-8, lacks
  a value of its block `live`, or its `terminal_path` is not a file on this server.
- MetaTrader 5 holds the bot's account, but the file names another server: correct `server` in the block `live`.
- The account is not a real account, not a hedging account, or not kept in US dollars.
- The account folder already belongs to another account number, or the account is already traded from another
  account folder on this server. The two branches of an account must hold the same credentials. Only when an
  account really moves to a new number: `safety.bat new-account` (section 3).
- The same bot already runs in another window.
- `symbols.json` or the settings of the branch are damaged: the line says what is wrong.

Fix what the lines say, then run `start_job.bat live` again.

| What it says | What it means | What to do |
|---|---|---|
| `This is the real-money branch ... It has no demo mode.` | The word `live` was missing, or another word was typed. Nothing was started. | Run `start_job.bat live`. |
| `app.py ended with code ... - it starts again in 30 seconds.` | The bot ended for a reason that can pass by itself, and the window starts it again. The lines above say why. The common reasons are in the next rows. | Read the lines above. Close the window only if you want the bot to stop. |
| `MetaTrader 5 at ... is logged into another account` | The bot found another account in its MetaTrader 5. It never switches the account itself. | First make sure the old bot of this account is stopped. Then log that MetaTrader 5 into this bot's account by hand (File > Login to Trade Account, "Save password"). If that MetaTrader 5 belongs to another account, install a second one and put its path into `terminal_path` of both branches. |
| `MetaTrader 5 at ... is not logged into any account` | The line says why the bot does not log in itself: there is no password in the file, its own last login was refused and it waits before it tries again, or this MetaTrader 5 belongs to another account. | Log it in by hand, as above. The bot finds the account by itself, within about a minute. |
| `The server refused account ...` | The login, the password or the server name in the credentials file is wrong. The bot waits before it tries the password again: 15 minutes, then 30 minutes, 1 hour, 2 hours, 6 hours. | Correct `mt5_credentials.json` on GitHub in both branches and pull. Or log MetaTrader 5 in by hand: the bot then starts by itself. |
| `An old bot is running on this server and uses the same MetaTrader 5.` | The bot does not start beside an old bot on its MetaTrader 5: the old bot would add to and close this bot's trades. While the old bot runs, the bot never logs that MetaTrader 5 in, also not after MetaTrader 5 has restarted. | Stop the old bot (step 2 of section 2). This bot then starts by itself. Do not log that MetaTrader 5 in by hand before the old bot is stopped. |
| `MetaTrader 5 was switched to account ...` | An old bot runs on this server with the same MetaTrader 5, and that MetaTrader 5 is now logged into another account. The bot sends nothing, not even a close, until its own account is back. | Stop the old bot, then log MetaTrader 5 back into this bot's account. |
| `QuickEdit could not be switched off in this window` | Each bot and each dashboard switches off, when it starts, what lets a click inside its window freeze it. Here that did not work. | Never click inside this window. If its title starts with `Select`, the bot is frozen: press Esc. |
| `Python 3.11 was not found on this server.` | The launcher found no Python. It says where it looked. | Install Python 3.11, or set `ALCADEIAS_PYTHON` (see the rules below). |
| `The Python packages of the bot could not be installed or loaded.` | The launcher could not install the packages of `requirements.txt`. Nothing was started. | Check that the server reaches the internet, then start the launcher again. |

**On the dashboard**

The tab "Changes & issues" lists every warning and error of the log, grouped by kind, each with what it means and
what to do. The bar at the top and the banners below it show what holds now:

| What it shows | What it means | What to do |
|---|---|---|
| Red bar `ACCOUNT BLOCKED` or `THIS BOT BLOCKED` | A safety limit was reached. The bar says which one, when, and with which numbers. | Section 3. Decide, then press Unblock. |
| Red bar `THIS BOT BLOCKED`, with the words `another program is trading ...` | Another program closed this bot's trade, or holds trades of the old bot's kind on this symbol. | Find and stop that program (the old bot of this account?), then press Unblock. |
| Amber bar `CHECKING` | The balance fell to a limit and the bot checks that it was not a withdrawal (up to 1 minute), or it waits for the result of a trade that could be the last losing one. No new trade meanwhile. | Nothing: it ends by itself. |
| Amber bar `SAFETY OFF` | The safety was turned OFF. No limit stops new trades; the meters are for information only. | Turn the safety ON when you want the limits again (no PIN needed). |
| Red bar `SAFETY CHECK FAILED` | The bot cannot read or write the safety's files, or it cannot read the account's history to judge a change of the balance. It opens no new trade. | Check the disk and the account folder: the bar says what failed. If you must trade meanwhile, turn the safety OFF. |
| Grey line `The bot is not running` | The bot has not written for more than a minute: it is stopped, it is frozen by a click in its window, or its window waits for you. A button you press now is applied when the bot starts. | Look at the bot's window, but never click inside it. If its title starts with `Select`, the bot is frozen: press Esc. Start it again if it was closed. |
| The line of the other bot: `not seen ...`, or `BLOCKED since ...` | The other bot of the account has not written for more than a minute, or the safety blocks it. | Look at its window and at its dashboard. |
| Red box `The bot is not running: its start was refused` | The bot's last start failed and it has not started since. The box shows what the bot wrote, what it means and what to do. | Do what the box says. |
| Red chip `This trace is another bot's (...)` | The bot folder holds the files of another branch or magic number, so the page does not show this bot. | Check that the bot and this dashboard run from this branch's own folder (step 1 of section 2). If it stays, send the logs. |
| Red banner: `... the bot can neither open nor close` | MetaTrader 5 or the broker does not let the bot trade: Algo Trading is off, trading from Python is switched off, or the account may not trade. The banner says which. | Do what the banner says at once (for Algo Trading: switch it on in MetaTrader 5). Until then no stop and no target of the bot works, only the emergency stop at the broker. |
| Red banner: `Trades that are not this bot's are open on ...` | Somebody else has trades on this symbol in this account: an old bot, or a trade by hand. This bot does not manage them. | Close them yourself. If an old bot still runs on this account, stop it. |
| Red banner: `An old bot is running on this server and uses the same MetaTrader 5.` | While it runs, this bot opens nothing new. It still manages its open trades. Turning the safety OFF does not change this. If MetaTrader 5 restarts meanwhile, the bot does not log it in. | Stop the old bot. |
| Amber banner: `An old bot is running on this server`, with another MetaTrader 5 | An old bot runs here with another MetaTrader 5. | Make sure it does not trade this account. |
| Red banner: `MetaTrader 5 was switched to account ...` | The bot's MetaTrader 5 is logged into another account, for example by an old bot on this server. The bot sends nothing, not even a close, until its own account is back. | If an old bot runs on this server, stop it first. Then log MetaTrader 5 back into this bot's account. |
| Red banner: `The two bots of account ... are logged into different accounts` | The credentials files of the two branches differ. | Put the same four values into both branches on GitHub, pull both, start both again. |
| Red banner: `The two bots of account ... have different safety limits.` | The two branches of the account do not agree on the account's limits. One of the two folders is probably not up to date. | Close the four windows of the account, run `git pull` in both folders, start again. If it stays, send the logs. |
| Red banner: `This page and the bot use different account folders.` | The dashboard was not started from the folder of the bot it shows: a button pressed here does not reach the bot. | Close it and run `start_dashboard.bat` in the same branch folder as the bot. |
| Red banner: `This bot's saved trade belongs to account ...` | The bot folder held a saved open trade of another account. The bot put that file aside and started fresh. It shows for 24 hours. (A file of another account without an open trade is only a line under "Changes & issues".) | If positions of that trade are still open in the other account, close them by hand. |
| Red banner `DISK_LOW` | Less than 2 GB is free on the disk. The bot stops writing its detailed lines and the figures of every minute. Orders, fills, closes, warnings, errors and the journal are still written. | Delete old files, for example old zip files in `C:\Alcadeias\exports`. |
| Amber banner: `The broker refuses this bot's new orders since ...` | The broker has refused this bot's orders to open for 4 minutes or more. The bot now tries only every 30 seconds, after 15 minutes every minute. Orders that close a trade are always sent at once. | Nothing while the market is closed. If the market is open, send the logs. |
| Amber banner: `A trade of this bot was closed by something else.` | In the last 24 hours a trade ended without the bot: by the emergency stop at the broker, by a stop-out, or by hand. | Read which one it was. Nothing to do if you know why. |
| Amber banner `CLOSE_RESULT_UNKNOWN` | The deal history did not show the result of a closed trade for 10 minutes. For its count of losing trades the bot took the P/L it saw at the close, or a loss when it saw none. | Nothing if the Trades tab shows the trade. If it repeats, send the logs. |
| Log lines `BUY_REFUSED`, `SELL_REFUSED` (for an add: `BUY_MORE_REFUSED`, `SELL_MORE_REFUSED`) | An order to open or to add was not filled. Mostly the broker refused it; the bot tries again, after 4 minutes of refusals only every 30 seconds, after 15 minutes every minute. An order MetaTrader 5 did not answer at all is logged under the same name, with a note that no answer came; it does not slow the next tries. Orders that close a trade are always sent at once. | Nothing while the market is closed. If the market is open, send the logs. |

**Rules for every day**

- **Never click inside a bot's window.** If its title starts with `Select`, the bot is frozen: press Esc. A
  frozen bot sends nothing, not even a close: only the emergency stop at the broker acts. The same holds for
  the window of a dashboard.
- **Never start a bot twice.** A second window of the same bot stops by itself. Two folders with the same branch
  must not exist on one server.
- **Closing the window does not close trades.** It stops the bot. Its open trades stay open with only their
  emergency stop at the broker, until the bot runs again.
- **Never sign out of the server.** Signing out ends every bot, every dashboard and MetaTrader 5. When you are
  done, close the Remote Desktop window instead: that only disconnects, and everything goes on running.
- **After the server has restarted, start the four windows of every account again** (section 2, step 8). Until
  then the open trades have only their emergency stop at the broker.
- **Windows Update must not restart the server by itself.** Set it to notify only: in a command window opened
  with "Run as administrator", run `sconfig`, choose 5 (Windows Update settings), then D (download only). At the
  least, set its active hours (Settings > Update & Security > Windows Update > Change active hours); outside
  them Windows may still restart. Install the updates yourself at a time you choose, then start the windows
  again.
- **Before `git pull`: close the bot's window and the dashboard's window** of that branch. Pull, then start them
  again.
- **Under Jenkins or Task Scheduler** set the variable `ALCADEIAS_NO_PAUSE=1`. Without it a launcher that has
  stopped waits for a key that nobody presses.
- **To have the windows started for you** (if you want): one Task Scheduler task for each bot and one for each
  dashboard, four for an account. In Task Scheduler choose "Create Task..." and set:
  1. General: "Run only when user is logged on", as the Windows user who runs the four windows of the account.
  2. Triggers: New, "At log on", "Specific user": that same user.
  3. Actions: New, "Start a program". Program/script: `cmd.exe`. Add arguments:
     `/c set ALCADEIAS_NO_PAUSE=1&& start_job.bat live` (for a dashboard:
     `/c set ALCADEIAS_NO_PAUSE=1&& start_dashboard.bat`). Start in: the branch folder, `C:\AlcadeiasBots\<branch>`.
  4. Settings: untick "Stop the task if it runs longer than". With its default of 3 days, the task would end the
     window after 3 days, and with it the bot and its restart loop.

  The tasks start the windows when you log on, not when the server starts: after a restart, log on by Remote
  Desktop, then close the Remote Desktop window (do not sign out). Start such a window by hand only while it is
  closed, for example after a `git pull`.
- **If Python 3.11 is not where the launchers look**, set the variable `ALCADEIAS_PYTHON` to the full path of
  `python.exe`, without quotes. A launcher that finds no Python says where it looked.
- **Times** on the page and in the logs are UTC.

## 7. How to run the tests

The tests need no MetaTrader 5 and no account. They write only into their own temporary folders. Run them on a
PC, or in a Python of their own: not in the Python the bots of a server use. That Python needs `pytest`, `pandas`,
`numpy`, `dash` and `plotly`. It does not need `MetaTrader5`: the tests use a stand-in for it.

From the branch folder:

```bat
python -B -m pytest tests_demo -q -p no:cacheprovider
```

- `-B` keeps Python's cache files out of the branch. A run without it fails at its end.
- The whole run takes about 40 minutes. For the quick part only, add `-m "not slow"`: it takes about 10 minutes.
- Some tests compare this bot, order by order, with the demo branches. They need those branches in the clone. In
  a clone made with `--single-branch` (step 1 of section 2) most of them are skipped; a skip is not a failure.
- `tests_demo\test_launchers.py` checks the `.bat` files as text. It cannot run them: only a Windows server can.
