# The safety of a real-money account: its files and their formats

A reference for whoever works on `safety.py` next. The owner's own description is in `README.md`, section 3; the
fields the dashboard draws are in `docs/dashboard-data.md` (`safety` in the trace). `safety.py` is standard library
only: the bot, the trace and the dashboard (which runs in its own Python environment) all import it. It never
imports MetaTrader5, imports `constants` only in its command line, and reads no clock outside its command line:
every time is passed in as `now` (seconds since 1970, UTC). Its one piece of module state is the lock of `press`.

## 1. What it does

Three rules read the **booked balance** of the account (closed trades only):

| Rule | Limit (constants.py) | Blocks |
|---|---|---|
| Drop from the high: the balance is X% or more below its highest balance since counting last started | `SAFETY_DROP_PCT` | both bots of the account |
| Loss today: the balance is Y% or more below the balance at 00:00 UTC | `SAFETY_DAY_PCT` | both bots of the account |
| Losing trades in a row: this bot closed N trades in a row with a net loss (profit, swap, commission and fee together) | `SAFETY_STREAK_N` | this bot |

Blocked = the bot opens nothing new (no entry, no ladder add, no Turtle pyramid). Exits are never touched. A block
never ends by itself. With the switch OFF nothing blocks and nothing is held; the counting goes on. A limit of
`None` or 0 switches its rule off (the tests' default). `Limits` refuses a value that is not a number, a negative
one, or a losing-trades limit that is not a whole number (`ValueError`); `app.py` checks the three `SAFETY_*`
constants the same way at the start (`deployment_problems`), so a mistyped limit stops the bot instead of switching
a rule off.

## 2. Where the files are

- **The account folder**: `safety.account_dir(OUTPUT_DIR, ACCOUNT_FOLDER)`, beside the bot folders:
  `C:\Alcadeias\live<n>_account` on the server. The two bots and the two dashboards of one account meet there.
  Windows path rules whenever `OUTPUT_DIR` has a drive letter or a backslash (on any system), else the system's
  own. Every harness gives a bot an `OUTPUT_DIR` of the form `<a new private folder>/bot_output`, so its account
  folder is a private sibling.
- **The bot folder**: `OUTPUT_DIR/state/safety_state.json`, written only by that bot.
- `Tracker`, `ensure_pin` and `press` make the account folder when it is missing.

## 3. The files of the account folder

| File | Written by | Content |
|---|---|---|
| `safety_switch.json` | `press` | `{"enabled": bool, "at": iso time, "t": seconds, "by": text}`. Missing: `SAFETY_DEFAULT_ON`. |
| `safety_restart.json` | `press` | `{"id": "<yyyymmdd_hhmmss>-<6 hex>", "scope": "account" / "bot", "account_id", "at", "t", "by", "why"}`: the id counting last started with. Missing: the id `start`. Ids are compared for equality only and are never used twice. `account_id` is the id of the last start that reset the account's figures: the new id for scope `account`, the one before for scope `bot`. A bot that was stopped while an account-wide press came, and then a bot-only press overwrote it, still takes the account's reset when it starts. A file that was read but holds no usable id counts as unreadable. |
| `safety_block_<id>.json` | the bot that meets an account limit first | The account block of that id: `{period, rules ('DROP' / 'DAY'), numbers {balance, peak, peak_at, drop_pct, drop_limit, day, day0, day0_at, day_since, day_pct, day_limit}, at, at_utc, branch, login_tail, reasons}` (`reasons`: the sentences the bar shows). **Created exclusively** (`open(path, 'x')`). It blocks by being there (`os.stat` succeeds): an empty or unreadable block file still blocks; a failed write of its content is no error. |
| `safety_status_<branch>.json` | that bot only | Its latest view (the trace's `safety`) plus `branch`, `partner_branch`, `login_sha`, `written_at`, `written_at_utc`, `version`, `bot_block`, `account_block`. Replaced when the view changed and at least every 20 s; its `at` is the time of the bot's last poll. A reader calls a status older than 60 s "not running". The other bot and the dashboards read it. |
| `safety_pin.txt` | `ensure_pin` (the dashboard, when it starts as a program), or the owner | 6 random digits (`secrets`) and a line end, created exclusively when missing; an existing file is never touched. Read as `utf-8-sig` and stripped. A valid PIN is 4 to 32 printable ASCII characters without blanks; anything else means "no valid PIN is set". |
| `safety_audit.jsonl` | `press`, the bots | Append only. A press: `{at, t, by, action, result ('done' / 'refused'), message}`; one that was done also `was` {id, enabled}, and `id` and `scope` when it wrote a new id. A bot: one line per trip, per new start of the counting and per state file it put aside, with `by: "bot <branch>"`, at most 30 lines an hour (the rest is counted and written as one line `{"more": n}` before its first line of a later hour). Refused presses: at most 20 lines an hour; the rest is counted and written as one line `{"refused_more": n, "in_the_hour_from"}` with the first press of a later hour. An empty PIN field writes no line. Never the PIN. |
| `safety_lockout.json` | `press` | `{wrong, locked_until, lock_s, last_wrong_at, refused_hour, refused_lines, refused_more}`: the count of wrong PINs, the end of the lock-out, its length, and the count of refused presses of the hour (for the audit file's limit). |

A JSON file may hold more keys than the table names: readers take what they know. The functions that write them
are the reference: `press` and `Tracker.flush` (with `Tracker._make_block_file`) in `safety.py`.

Three more files are in or beside the account folder; `app.py` owns them (`safety.py` only deletes the first, for
`new-account`):

- `account_claim.json`: `{login_sha, login_tail, server, set_at, set_t, by, account}`, the one account of this
  folder. Made exclusively by the first bot of the account that passes the account checks, never rewritten. A file
  that holds no usable account is put aside as `account_claim.json.not-readable-<yyyymmdd_hhmmss>` and made anew.
- `login_attempt.json`: `{at, at_utc, failed, code, cred_mtime_ns, cred_size, by, files: {branch: [mtime_ns,
  size]}}`, the budget of the bots' own logins, written before each `mt5.login`; deleted by a start that passes the
  account checks. "The credentials file changed since" is judged per branch, from `files` (each branch has its own
  credentials file).
- `<parent of OUTPUT_DIR>/terminal_claims/<sha1 of the terminal path>.json`: `{login_sha, login_tail, account,
  branch, at, at_utc, server, terminal_path}`, which account a MetaTrader 5 belongs to; written whenever a bot
  passes the account checks on that path. A bot logs a MetaTrader 5 in itself only when its claim is missing or
  names its own account.

**Never in a log export:** `safety_pin.txt`, `safety_lockout.json`, `login_attempt.json` (and
`mt5_credentials.json`). `collect_logs.py` leaves them out by name. **Never in any file: the full account number.**
Files that must recognise the account hold `safety.login_sha(login)` (SHA-256 of the number as text); texts show
`safety.mask_login(login)` (`...1234`, `...?` when unknown).

## 4. How the files are written and read

Two bots, two dashboards and a command line use one folder at the same time, on Windows:

- **Writes.** Every file except the block file and the audit file is written whole into a temp file of its own
  (`<name>.<pid>.<8 hex>.tmp`, in the same folder) and then moved over the old one with `os.replace`, tried again
  for about a quarter of a second on `PermissionError` (Windows refuses the move while another program has the old
  file open). The state file, the switch, the restart file and the lock-out record are flushed to the disk before
  the move. A bot that loads removes temp files of this kind (`safety_*.json.<pid>.<8 hex>.tmp`) that are more
  than a day old.
- **Who writes what.** A bot never writes the files `press` writes. `press` never writes a bot's state or a block
  file. So no two writers race for one file, except the exclusive creation of a block file, which one of them
  wins.
- **Reads.** A missing file is an answer: the default. A file that is there but cannot be read or parsed is **not**
  an answer: the reader keeps the last value it knew; a process that knows none yet takes the value of its saved
  state, else the default, and tries again at its next flush. JSON is read as `utf-8-sig` (Notepad's byte-order
  mark is accepted).
- **A new start of the counting happens only on a read that succeeded and found another id.** A file that cannot
  be read never unblocks anything.
- **The block file:** `FileNotFoundError` = no block; any other `OSError` = keep the last known answer.
- **No file work in front of an exit.** `Tracker.poll` works in memory only, plus the exclusive creation of a
  block file in the poll that meets an account limit. Everything else (reading what the owner pressed, the block
  file of the next id, the other bot's status, the state file, the own status file, the audit lines) happens in
  `load` and in `flush`, which the bot calls after its order section. A write that failed is tried again after
  5 s, not on every poll (a block file that is owed: at every flush). None of them raises: a problem becomes
  `view['error']`.

## 5. The id, and what a new start of the counting changes

`safety_restart.json` holds the id the counting last started with and its scope. A bot compares it with the id in
its own state (`period`). Another id:

- scope `account` (Unblock after an account block, Turn ON, `safety.bat unblock`, `safety.bat new-account`), or a
  scope `bot` file whose `account_id` this bot has not taken yet: `period` = the new id, the count of losing
  trades = 0, no bot block, no account block; and on the first poll with a balance the high and the day's
  reference become that balance, the day reference is marked `restart`, the cash operations seen so far are
  forgotten and the first cash read after it is a baseline again. The day's own start balance
  (`day_start_balance`, behind "today +$12.40") is not touched, unless the UTC day is a new one.
- scope `bot` (Unblock after a block for losing trades): `period` = the new id; a bot that is blocked itself sets
  its count to 0 and drops its block. Nothing else changes. (A bot that met an account limit in the same instant
  judges the account rules again under the new id: the figures did not change, so the block is made anew.)

The first start of a bot (a state with no `period`) is a new start of the account kind, taken with its first
balance. An old block file can never block a later start: its id is in its name, and ids are never used twice
(`press` draws again when the new id would be the current one, or a block file of that id exists).

## 6. The state of one bot (`state/safety_state.json`)

`version, login_sha, branch, period, account_period (the account_id this bot last took), started_at, peak,
peak_at, day ('YYYY-MM-DD' UTC), day0, day0_at, day_since ('midnight' / 'restart'), day_start_balance,
day_start_at, day_cash (the cash operations of the day), streak, bot_block (null or {rule: 'STREAK' /
'OTHER_PROGRAM', text, count, limit, at}), account_block (null or {period, rules, numbers, at}), settled_balance,
settled_at, change_first, change_last, seen_balance, cash_seen ({ticket: time}), cash_baseline_done,
cash_read_ok_at, counted_trades (the newest 500 keys), enabled_last, block_exists_last, fresh_pending`.

- Written at a flush when it changed. A state file that exists but cannot be read is tried again (`load` answers
  False; while the safety is ON the bot opens nothing without a usable Tracker). Only a file that was read and is
  not valid JSON, is not a state of this version, or holds another `login_sha`, is renamed aside
  (`safety_state.json.not-readable-<yyyymmdd_hhmmss>` / `.other-account-<yyyymmdd_hhmmss>`) and treated as a first
  start (an audit line and a journal line). Unless it was another account's, a bot block, an account block of the
  current id and the count of losing trades survive that, and a state file that is missing, when the bot's own
  status file still shows them for the same account and the same id.
- A state that says it has started but lacks a number a poll needs starts again with the next balance, keeping
  its count of losing trades and its blocks.

## 7. One poll, in order (`Tracker.poll` -> `decide`)

1. The controls as the last `flush` read them: another id starts the counting again (section 5). A change of the
   switch is an event.
2. No balance: no evaluation; the last meters and the current blocked state are returned. With a balance, a new
   start that waits is taken now.
3. **A balance change settles first.** While the balance differs from `settled_balance` (to the cent) the change
   is unsettled and `needs_cash()` is true: the bot reads the account's balance operations at the end of its poll
   and passes them, with the time of that read, to the next poll. The change settles on the first poll whose cash
   read is at least `confirm_s` (3 s) newer than the last move; a fall also settles after `cash_wait_s` (60 s)
   without such a read (it is then taken as a loss); a rise waits for a read. The 60 s count from when the change
   was first seen, or from when this process began to watch, whichever is later: a bot restarted in the middle of
   a check tries the history first. A read made before the counting started is not the baseline read.
4. **Cash.** The first read after a new start only marks its tickets as seen (they are inside the starting
   balance). Later, every new ticket is applied once, oldest first, by scaling: with `b0` the balance before it
   and `f = (b0 + amount) / b0`, the high and the day's reference are multiplied by `f`, and `day_start_balance`
   and `day_cash` move by the amount. When `b0` or `b0 + amount` is not above 0, the high and the day's reference
   become the balance. An operation dated at or before the last judged balance is inside it already: it is only
   remembered. Deposits and withdrawals so do not move the percentages. Each operation is an event with
   `found_after_s` (how long after the balance moved it was found).
5. A new UTC day: the day's reference and `day_start_balance` become the balance (`day_since` 'midnight'). A change
   first seen on the old day is judged against the old day first.
6. On settling: the high rises to the balance if it is higher; `settled_balance` = the balance.
7. The meters: percent below the high, percent below the day's reference (0 while that reference is not above
   0). A limit is met at the limit itself (`round(pct, 6) >= limit`).
8. Switch OFF: nothing blocks, nothing is held, nothing trips; the tracking goes on.
9. **Account rules**, when a change settles and the account is not blocked under the current id: a met limit is
   put into the state first (`account_block`), then the block file is created (in this poll, and at every later
   `flush` until it exists). The account is blocked when the block file of the current id exists, or this bot's
   own `account_block` is of the current id (whether or not its file could be written).
10. **Bot rule:** the count has reached its limit and there is no bot block yet: a bot block (`STREAK`).
11. **Hold** (`view['hold']`): true while an unsettled change would meet an account limit against the current
    references, or while `pending_results` (closed trades of this bot still waiting for their result) could
    complete the losing-trades limit. The bot opens nothing on `blocked or hold`. A hold ends by itself. A hold
    older than 10 s is an event, and so is its end.
12. `blocked = enabled and (account blocked or bot blocked or error)`.

**The safety check fails** (`view['error']`, `view['state']` 'error'; while the safety is ON `blocked` is true with
the sentence "The safety check failed: no new trades until it works again or the safety is turned OFF.") when:
the state could not be loaded yet; the state file or a block file this bot owes could not be written for 60 s; a
balance change could not be judged for 600 s of polls (no readable cash history, while an account rule is on); or
the safety's own code failed in `poll`, `on_trade_closed`, `note_other_program` or `flush` (at once, until a call
succeeds).

`on_trade_closed(now, trade_key, net_pl)` counts a closed trade once per key: a loss adds 1, anything else sets the
count to 0, a result that is not a number counts as a loss. `note_other_program(now, text)` blocks the bot
(`OTHER_PROGRAM`) when another program trades its symbol in the account: not while the switch is OFF, and not on
top of a bot block it already has. `needs_cash()`: a change is unsettled, or the baseline read of a new start is
owed. `cash_since()`: an hour before the last read that succeeded; before the first one, a day before the counting
started. `take_events()`: what happened since the last call, for the journal: `trip`, `fresh_start`, `switch`,
`cash`, `cash_start`, `trade`, `hold`, `hold_end`, `state_put_aside`, each with `at` and `branch`.

The view (`build_view`, every key always there): `enabled, blocked, hold, pending, account_blocked, bot_blocked,
blocked_scope, reasons, since, period, at, started_at, error, state ('on' / 'checking' / 'account_blocked' /
'bot_blocked' / 'off' / 'error'), drop {pct, limit, peak, peak_at, balance}, day {pct, limit, day0, day0_at, day,
since, start_balance, start_at, cash}, streak {count, limit, waiting}, partner, limits {drop_pct, day_pct,
streak_n}, account_dir, login_tail`. `reasons` holds every sentence of the state (the dashboard prints them);
`partner` is the other bot's status: `{branch, seen_at, blocked, bot_blocked, drop_pct, day_pct, limits_differ,
account_differs, period, stale}` or null. The two account limits and the account must be the same for both bots
(`limits_differ`, `account_differs`: by `login_sha`, else by the tail); the losing-trades limit is each bot's own.

## 8. `press`: the buttons and the command line

`press(account_dir, action, pin, by, now, need_pin=True, expect=None, default_on=True)` returns `(ok, message)` and
never raises. It runs under one lock of the module: the dashboard serves each request in its own thread.
`default_on` is the switch while nobody has pressed it (the branch's `SAFETY_DEFAULT_ON`).

- **Who calls it.** The dashboard's one action callback, always with `need_pin=True` (`dashboard.py` holds neither
  `safety_pin` nor `need_pin=False`: a test reads its source). `safety.py`'s own command line
  (`safety.bat status|unblock|on|off|new-account`), with `need_pin=False` and `by = 'command line'`.
- **What is refused before anything else:** an action that is not one of `unblock`, `off`, `on`, `new-account`;
  `new-account` with `need_pin=True` ("This is done on the server only"); an account folder that cannot be made.
- **The PIN** is asked for `unblock` and `off`. `on` never needs it and is never locked out: the safety can always
  be switched back on. The order: a lock-out refuses without comparing; no valid PIN on the server refuses without
  counting (a missing file and a file that cannot be used have their own answers); an empty PIN refuses without
  counting and without an audit line; else the try is counted **and saved** before the comparison
  (`hmac.compare_digest` on SHA-256 digests), so parallel requests cannot each get a free guess; a lock-out record
  that cannot be read or written refuses. A right PIN sets the count and the lock-out length back. 5 wrong PINs in
  a row lock for 10 minutes, twice as long each further time, up to 24 hours; 24 hours without a wrong PIN since
  the last wrong one or the end of the last lock-out make the next lock-out 10 minutes again.
- **`expect`** is what the page showed (`{'period', 'enabled', 'scope'}`; `None` = not checked, the command line). With `scope` 'bot' an Unblock is refused while the account is blocked, and with `scope` 'account' when no account block is left, so a dialog never lifts a block it did not show. Anything
  else than a dict with both keys equal to the files of now: nothing is written ("The safety changed since this
  page was refreshed. Check the bar and press again."). A page that is a few seconds old must not do the opposite
  of what its button says.
- **A restart file or a switch file that is there but cannot be read:** nothing is written. The one exception: a
  restart file that cannot be read or parsed is written anew by the command line's `unblock` and `on` (a new id
  with scope `account`, which both write anyway; the answer starts "safety_restart.json could not be read, so it
  was written anew."). Every other press refuses and its answer tells the owner to run `safety.bat unblock`.
- **`unblock`:** the block file of the current id exists, or a bot's status file of the current id shows an
  account block (its block file could not be written): a new id with scope `account`. Else a status file of the
  current id shows a bot block: a new id with scope `bot`. Else "Nothing is blocked." (ok, nothing written). From
  the command line it always writes a new id with scope `account`.
- **`off`:** writes the switch, unless it is OFF already ("The safety is already OFF.", ok, nothing written).
  **`on`:** unless it is ON already (ok, nothing written), a new id with scope `account` first, the switch second
  (a crash between the two leaves the safety OFF with a new start, never ON against the old high).
- **`new-account`** (command line only): deletes `account_claim.json` and writes a new id with scope `account`.
- **The audit line's `by`** is fixed text the caller builds: `dashboard <BRANCH> from <remote address>` or
  `command line`. Nothing from the request goes into it but the remote address.

**The command line** (`main`, run by `safety.bat`): `python safety.py status|unblock|on|off|new-account
[--account-dir FOLDER]`. Without `--account-dir` the folder is the branch's own (`constants.OUTPUT_DIR` and
`ACCOUNT_FOLDER` through `account_dir`, and its `SAFETY_DEFAULT_ON`); on a PC that is not Windows, a folder of the
server is refused. `status` prints the switch, the last press, the account block, whether the PIN is usable and
where its file is, a lock-out, and each bot's status (running or not, its sentences, its meters). The others press
without the PIN. Exit code: 0 done, 1 refused, 2 the command was not understood.

`read_controls(account_dir, default_on)` (the dashboard, and a bot without a usable Tracker): `{enabled, period,
scope, block (null or {period, readable, at, branch, rules, numbers, reasons, file_time}), locked_until, pin_set,
readable, pressed_at, pressed_by, pressed_why, switched_at, switched_by}`; a switch file that cannot be read gives
`default_on`. `read_statuses(account_dir)`: `{branch: status}` of every status file that can be read now.

## 9. Where it meets the rest

- `app.py`: one `Tracker` per bot, built and loaded before the poll loop and again after the orders of every poll
  while it is not usable; `poll` before the decision block (memory only), then `note_other_program` when the
  positions read showed the old ladder bot's trades; the one flag every opening order is tested against; the gate
  is the last test before an opening order (basket entry, ladder add, Turtle entry, Turtle pyramid) and never
  touches a close; `mt5_helper.buy()` / `sell()` refuse behind it (`open_guard`). After the order section, each
  step on its own: the cash read (`mt5_helper.get_cash_deals`) while `needs_cash()`, the oldest closed trade of the
  queue (`state/safety_closes.json`) resolved from the deal history (`on_trade_closed`; a closing deal of another
  program's magic: `note_other_program`; after 600 s without a result: the P/L seen at the close, else a loss),
  `flush`, `take_events` into the journal. No usable Tracker, or a `poll` that raises: no opens while the switch is
  ON (`read_controls`; else the last switch this process read; else `SAFETY_DEFAULT_ON`).
- `tracelog.py`: the view goes into the trace (`safety`), the journal (`safety`, `skip`, and the meters of the
  `day` and `trade` lines) and the samples.
- `dashboard.py`: the bar on every tab reads `read_controls`, `read_statuses` and the trace; its buttons call
  `press`; it calls `ensure_pin` once when it starts as a program and prints where the PIN file is.
- Tests: `tests_demo/test_safety_*.py` (the rules without files, the files, `press`, the wording), the bot's side
  in `tests_demo/test_live_*.py` (`test_live_safety_loop.py`, `test_live_refused.py`, `test_live_lock_rule.py`
  among them), the bar in `tests_demo/test_dashboard_safety.py`.
