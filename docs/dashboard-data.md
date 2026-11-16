# The dashboard's data: what the bot writes (schema 1, basket strategy)

`tracelog.py` writes these files into the bot's output folder (`OUTPUT_DIR` in `constants.py`, here
`C:\Alcadeias\demo_hedging_xauusd6`). The bot never reads them back; nothing it decides depends on them.
`tracelog.py` is the same file on all six demo branches. Its Turtle part (the trace's `turtle` block, described in
this file on the Turtle branches) never runs here: this branch runs only `STRATEGY = 'basket'` (`design_problems`
refuses the Turtle), so `turtle` is always null.

| file | what | when |
|---|---|---|
| `<SYMBOL>_trace.json` | the latest decision snapshot | after every poll (a poll takes at least 1 s), so every change of action, position or gate result is in it |
| `<SYMBOL>_bars.json` | bid OHLC bars for the chart | the first poll, then at most every 30 s while a bar moves or a new one starts |
| `<SYMBOL>_trades.json` | this bot's trades from the deal history | the first poll, after every fill and close (and on the poll after), at least every 60 s |
| `logs/<SYMBOL>_<YYYY-MM-DD>.log` | the text log, one line per event | as it happens; one file per UTC day, kept 30 days |
| `logs/<SYMBOL>_events.jsonl` | the same lines as JSON | as it happens; rotated at 10 MB into `_events.1.jsonl` (newest) .. `_events.5.jsonl` |
| `state/<SYMBOL>_exit_reasons.json` | the exit reason the bot recorded per position | at every close |

The old dashboard's files are written as before: `<SYMBOL>.json`, `account.json`, `active_config.json`,
`logs/<SYMBOL>_strategy_log.json`, `daily_trade/<SYMBOL>/*.json`, `state/<SYMBOL>_state.json`.

**Reading them.** JSON files are replaced atomically (a temp file, then a rename): a reader sees the old file or the
new one, never half of one. They are compact (no indentation). A file can be missing (the bot has not run yet, or a
write failed); every field can be `null`. Check `schema` (1). Times are UTC epoch seconds in `t` / `..._t` fields,
with an ISO copy in `..._utc` fields (`2026-11-17T08:00:01.500Z`). Money is USD of the account; prices are bid / ask
as the terminal quotes them, rounded to the symbol's `digits` where the bot computed them.

## 1. `<SYMBOL>_trace.json`

```
schema, branch, design, strategy ('basket'), symbol, mt5_symbol, magic, t, time_utc, poll (count since start),
stale (true: this poll could not read the terminal; account / market / basket are the last good poll's),
stale_since_utc, health, account, market, decision, basket, turtle (null on this strategy)
```
A stale (skipped) poll marks what it kept: `market.status` is 'UNKNOWN' (its `message` says the terminal was not read;
bid / ask are the last ones read), `basket.fresh` is false, `health.market_live` null.

### health
`connected`, `terminal_problem` · `account_ok`, `account_problem`, `login`, `demo_login`, `trade_mode` /
`trade_mode_name` (demo / contest / real), `margin_mode` / `margin_mode_name` (hedging / netting / exchange) ·
`market_live` (a tick or an M1 bar within `MARKET_LOOKBACK_MINUTES`), `market_status`, `minutes_since_activity`,
`last_tick_age_s` · `loop_ms` (the poll's work), `trace_ms` (this module's own time in the last poll),
`poll_gap_s` · `reconnects`, `errors_1h` (ERROR lines in the last hour), `skipped_polls`, `failed_streak`,
`started_utc`, `uptime_s`, `log_write_failures`. A skipped poll adds `positions_problem` when the positions read failed.
The reconnect after a lost terminal: `reconnect_failed_attempts` (failed attempts since the terminal was lost; 0 when
connected), `next_reconnect_t` / `next_reconnect_utc` (the next attempt: 5, 10, 30, then every 60 s), `outage_s` (how
long the terminal has been lost), `connect_problem` (why the last start-up or reconnect failed, e.g.
`TERMINAL_IN_USE: the terminal at ... is logged into another account ...`; null once connected), `terminal_in_use`.

### account
`virtual` (units from the virtual balance), `virtual_balance`, `virtual_balance_source` ('bot': the bot's own figure; 'deal history': after a restart in a trade the bot has none until it is flat again, so the trace gives the balance of its last deal-history read; null without a balance), `virtual_start_balance`, `virtual_start_date`,
`units`, `lot` (units x mtqty), `mtqty`, `own_closed_pl` (virtual balance - start), `own_open_pl` (this bot's
floating P/L), `own_equity` · the shared account: `balance`, `equity`, `margin`, `margin_free`, `margin_level`,
`account_profit` · `step_up_balance`, `unit_max_limit`, `next_unit_at` (the virtual balance of the next unit),
`unit_rule` (text).

### market
`bid`, `ask`, `spread`, `tick_t` / `tick_utc`, `digits`, `server_time_utc`, `status`, `minutes_since_activity`,
`lookback_minutes`, `message`, `in_window`, `brake` (1 = no new entries), `brake_manual`, `window` (text).

### decision
`action`, `reason`, `side`, `headline` (one plain sentence: what the bot does now and why), `signal` (`buy`,
`sell`: the strategy's signals), `gates` (below), `blocked_by` (the gate that decided: the need gate that blocked,
or the exit that fired), `orders` (this poll's order requests and results).

| action | meaning |
|---|---|
| `SKIPPED` | the terminal, the account or the positions read was not right: nothing decided (`reason` terminal / account / positions / account_recheck: the account read again right after the positions is not this bot's, so the positions may be another account's) |
| `NO_DATA` / `MARKET_CLOSED` | no M15 bars / no tick for 3 min: nothing decided (an open basket is held, its stop is not checked) |
| `WAIT` | flat, no entry signal (`reason` 'open score' or 'agreement') |
| `PAUSED` | flat, the pause after the last close runs (`reason` 'after a close' / 'after a losing basket') |
| `BLOCKED` | the strategy wants an entry (`side`) but a gate after it refuses (`reason` window / votes unknown / trend / volatility unknown / contract size unknown) |
| `OPEN_BUY` / `OPEN_SELL` / `OPEN_FAILED` | an entry was sent: filled / not filled (`reason` the retcode text) |
| `WAIT_FILL` | the entry filled, the terminal does not list the position yet (up to 10 s; no new entry) |
| `HOLD` | in a basket, no exit, no add |
| `ADD_BUY` / `ADD_SELL` / `ADD_FAILED` | a ladder add was sent |
| `CLOSE_BUY` / `CLOSE_SELL` | the basket is closed (`reason` stop_loss / target / force_close / close_retry / leg_closed_outside: a leg was closed outside the bot, so the rest is closed at once and the whole basket is booked as closed outside the bot) |
| `BOTH_SIDES` | a buy and a sell of this bot are open: the strategy holds still |
| `TRACE_ERROR` | the trace could not work out this poll's decision: a step of `tracelog.py` failed (`reason` the step; the ERROR TRACE line of the log has its traceback). The trading is not affected; `gates` is empty |

**Gates**, in the order the bot checks them: `{key, name, role, ok, value, need, note, checked}`.
- `role` `need`: `ok` true = met; the first one not met blocks. `exit` / `add`: `ok` true = it fires (a fired stop
  closes the basket; every add gate must be true for an add). `info`: shown, not checked (`ok` null).
- `ok` null = does not apply (e.g. no side is wanted, the lever is off in this design).
- `checked` false = the bot did not get that far this poll (an earlier gate decided); its value is still current.
- `value` is the number (or word) tested, `need` the rule with its threshold, `note` the explanation.

| path | gate keys |
|---|---|
| every poll | `terminal`, `account`, `positions`, (`market_data`), `market_live`; a poll skipped by the account read again after the positions: `terminal`, `account`, `positions`, `account_recheck` |
| flat | `pause`, `open_score`, `agreement`, `window`, `votes_known`, `trend`, `volatility`, (`contract_size`) |
| basket | (`fill_listed`), (`legs_outside`: legs closed outside the bot, value their ids, or `close_retry`), `stop`, `target`, `force_close`, then `ladder` (no adds) or `ladder_trigger`, `ladder_gate`, (`ladder_gap`) |
| both sides open | `one_side` |

**orders**: `{t, kind (open / add / close), side, order_side, symbol, volume, price, sl, tp, position, magic, comment,
refused, retcode, retcode_text, done, result_price, result_volume, order, deal, result_comment, last_error, ms}`.
`side` is the side of the trade: for a close, the side of the position it closes; `order_side` is the order's own
type (a SELL position is closed with a BUY order). `kind` comes from the basket loop's own `state`: an order on the
side of the open basket is an `add`, also on the first poll after a start.

### basket (the basket strategy)
- `fresh` (the poll computed votes), `weights` (`open`, `agreement`: `{TF: weight}`).
- `votes` `{TF: ...}` for every timeframe with votes: `roles` (open / agreement / ladder), `rsi` and `macd`, each
  `{vote (+1 / -1 / 0), now, pivot, pivot_side, bars_ago, slope, series (the last 40 values)}` (rsi also `bands`
  [40, 60]; macd also `signal_forming` and `side_rule`: the forming bar's signal line picks the pivot side),
  `open_weight`, `open_contrib` (with grey fill), `grey_filled` ('rsi' / 'macd' / null), `fc_weight`,
  `fc_contrib`, `t` (the bar times of `series`).
- `open_score`, `entry_s`, `open_range`, `open_wants` · `fc_score` (the agreement score), `entry_agree_s`,
  `fc_range`, `force_close_enabled`, `force_close_s` · `ladder_s`, `buy_add_ok`, `sell_add_ok` ·
  `entry_direction`, `entry_chop_block`, `entry_allowed`, `exit_reason`.
- `trend` `{on, tf, signal (the MACD signal line of the last closed bar), sign, text (up / down / flat), allows
  (BUY / SELL / null), bar_t, bar_utc, rule}`.
- `vol` `{on, tf, len, raw, capped, cap_usd_per_unit, cap_binds, bars_used, min_bars, known, short_history,
  usd_per_unit, rule}`.
- `usd_per_price` (USD per unit for a 1.0 move), `contract_size`.
- `new_basket`: what a basket opened now would get, fixed at its open: `units`, `lots`, `target_usd`, `stop_usd`
  (and per unit), `target_px` / `stop_px` (price distances), `gap_px`, `backstop_px`, `vol_unit`, and `buy` /
  `sell` `{entry, target, stop, backstop, judged_on}` (a buy is judged on the bid, a sell on the ask).
- `pause` `{active, left_s, until, until_utc, length_s, why, pause_s, loss_pause_s, last_close {t, utc, pnl, lost,
  reason, side, resolved, source, ids}}`.
- `rsi` `{TF: value}` (every fetched timeframe), `no_data`, `short_history`, `fill_pending`, `ladder_tiers`,
  `ladder_trigger`.
- `open`: null when flat, else the basket: `side`, `units`, `lots`, `legs` [`{ticket, id, open_t, open_utc,
  price, lots, profit, swap, backstop, tp, magic, comment, listed}`], `avg_price`, `pnl`, `judged_on`,
  `price_now`, `stop_usd` / `target_usd` (and per unit), `stop_price` / `target_price` (where the basket's P/L
  reaches them), `to_stop_usd`, `to_target_usd`, `backstop_prices`, `vol_unit`, `vol_unit_raw`, `vol_source`,
  `gap_px`, `ladder` `{on, tiers, trigger, count, armed, gap_px, exhausted, tier_tf, vote, rsi, rsi_level, add_ok,
  last_fill, next_add_price, judged_on, price_now, next_add_lots}` (or `{on: false, note}`), `opened_at` /
  `opened_utc`, `opened_by` (bot / rebuild), `first_t` / `first_utc`, `age_s`, `levels_pending`, `close_pending`,
  `ids`, `outside_ids` (its legs closed outside the bot: the rest is closed at once), `known_to_bot`, `closing` /
  `closed_now` (this poll closes it), `listed` / `opened_now` (just opened), `unlisted` [`{id, fill_t, fill_utc,
  age_s, wait_s, price, lots, kind}`] (since v3.9.2-demo.5: the legs whose position id the bot took from the order's
  answer and the terminal has not listed yet, kept `wait_s` = 10 s; `legs`, `pnl`, `stop_price` and `target_price` are
  those of the listed legs, as the bot's own test reads them).

## 2. `<SYMBOL>_bars.json`

```
{schema, symbol, mt5_symbol, t, time_utc, price: 'bid', digits, last_is_forming: true,
 counts: {M1: 360, M5: 300, M15: 300, H1: 300, D1: <= 200}, source: {TF: 'poll' | 'terminal'},
 tf: {M1: {t: [...], o: [...], h: [...], l: [...], c: [...], v: [...]}, M5: ..., M15: ..., H1: ..., D1: ...}}
```
Columns, oldest first; `t` is the bar's open time (UTC seconds); the last bar is still forming. Between two
rewrites the chart can move the last bar with the trace's `market.bid`.

## 3. `<SYMBOL>_trades.json`

```
{schema, symbol, mt5_symbol, magic, design, t, time_utc, since_t, since_utc, virtual, virtual_start_balance,
 closed: [...], open: [...], balance_curve: [{t, utc, v, id, pnl}], summary: {...}}
```
- A trade is a basket: the positions of one side that were open together. `closed` (oldest first, the newest
  2000): `{id (its first position), side, legs, lots, open_t, open_utc, open_price (lot-weighted), close_t,
  close_utc, close_price, hold_s, pnl (profit + swap + commission + fee), profit, swap, commission, exit_reason,
  exit_reason_text, bot_reason, balance_after, result (win / loss / flat), status}`; a leg: `{position_id, side,
  lots, open_t, open_price, close_t, close_price, closed, profit, swap, commission, net, deal_reasons, magic}`.
- `exit_reason`: `target`, `stop`, `force_close`, `close_retry` (as the bot recorded it), `backstop` (the broker's
  stop: the position's sl), `broker_target`, `stop_out`, `closed_outside` (from the terminal, or while the bot was
  down), `leg_closed_outside` (a leg closed outside the bot -- its backstop, a stop-out or by hand -- and the bot closed
  the rest; the legs' `deal_reasons` say how), `unknown` (closed by the bot before it recorded reasons).
- `open`: the open basket with its live levels (the trace's `basket.open`, `live: true`), or the open baskets of the
  deal history.
- `balance_curve`: the virtual balance at the start and after every closed basket (the last value = the virtual
  balance the units are sized from). `summary`: `closed`, `wins`, `losses`, `win_rate`, `net`, `gross_win`,
  `gross_loss`, `best`, `worst`, `avg_hold_s`, `exit_reasons`, `balance_now`, `deals`.

## 4. The text log and the events file

```
2026-11-17 08:05:23.700 UTC | CLOSE | CLOSE | SELL basket closed (stop): 2 position(s), P/L -$2.31 at the decision, realised -$2.31 | side=SELL reason=stop_loss decision_pnl=-2.31 realised_pnl=-2.31 lost=true positions=2 ...
```
`line.split(' | ', 4)` gives time, level, category, message, `key=value` pairs (text values with spaces are
quoted, lists and dicts are JSON). The message never holds ` | `. An ERROR from an exception is followed by its
traceback, every line indented by 4 spaces.

**When lines are written.** No file is written while the bot holds `mt5_lock` (it sends orders and reads the terminal
inside it). The ORDER and FILL lines (made inside `MT5PositionHelper._send`) and any line made inside the lock (an
event such as LEG_CLOSED_OUTSIDE, a state save, a start-up line of a reconnect) wait in memory and are written at the
end of the poll, by a skipped poll, the exception hook or the job's last lines; each keeps its own time and its place.
If the process is killed in between (a fraction of a second after an order), those lines are lost; the order itself is
in the deal history (`<SYMBOL>_trades.json`). A close's ORDER line: `close position 100001 (SELL 0.01 lot, with a BUY
order) at 1,781.644 -> done (10009) | kind=close side=SELL order_side=BUY ...`.

**A step that fails.** The poll hook runs each step on its own (the sections, the decision, the trace file, the bars,
the trades, the heartbeat, the bookkeeping): one that raises is an ERROR TRACE line ('the trace hook poll() failed in
its step _bars: ...', again at most every 10 min with the count) and the others go on. The deal history is read again
at most every 5 s after a failed read and every 60 s after a failed build.

| level | lines |
|---|---|
| DEBUG | DECISION (every change of the action or of a checked gate, with all the gates), STATE (state saved), BASKET (a position listed -- also a leg recorded from its order, listed now, or listed under another id -- the ladder armed), SIGNAL |
| INFO | START, CONFIG (every effective constant, symbols.json, the contract size), STATE, ACCOUNT (the terminal shows no account yet: read again every second for up to 15 s; logged in, or no login when the terminal already holds this bot's account; the checks passed), TERMINAL (connected again, after how long and how many failed attempts), BASKET (opened, added; `recorded=<id>`: the position id taken from the order's answer), PAUSE (start, end), MARKET, WINDOW, DATA, HEARTBEAT (every minute) |
| ORDER | every order request and its result (retcode, comment, price, sl, tp) |
| FILL | an entry or add filled |
| CLOSE | a basket closed, with the reason and the P/L (also one closed outside the bot; an entry gone before the terminal listed it; after a leg closed outside the bot, the close of the rest and the booking of the whole basket) |
| WARN | an order not filled, a terminal read error, missing bars, a file that could not be written, a slow poll, BASKET: legs of the basket closed outside the bot, CLOSE: a close that is incomplete (a leg refused, or an add not listed yet: the basket stays open) or that closed nothing (decided again next poll), ACCOUNT: no login because the account is not known (an IPC error), the bot logging in itself after 15 s of no account, TERMINAL: every failed reconnect attempt that the strategy log leaves out (it has RECONNECT_FAILED once for each reason, then at most every 15 min for that reason) |
| ERROR | an exception (with its traceback), the account refused (also by the account read again right after the positions), TERMINAL_IN_USE (the terminal holds another account: no login, the terminal is left as it is; once for each account, then every 15 min), START: LIVE_TERMINAL_PATH (refused before any terminal call) and all 3 start attempts failed (with the problem), a reconnect that failed (as in the strategy log, with `not_logged_since`), TRACE: a step of the trace that failed (the trading goes on) |

A HEARTBEAT line comes every minute: a gap of more than a minute means the bot was not running. The same
exception at the same place is written again at most every 10 minutes, with the count of the repeats. Past 50 MB
in a day the day's file takes only WARN and ERROR lines (the events file keeps every line).

`logs/<SYMBOL>_events.jsonl`: one JSON object per line: `{t, time, level, cat, msg, kv, data, traceback}`;
`data` holds the full gate list of a DECISION line, the state of a STATE line.

**The third fix round (v3.9.2-demo.5) in the log.**
- `LIVE_TERMINAL_PATH` (terminal_path names the live bots' MetaTrader 5, or is empty): one ERROR START line
  'LIVE_TERMINAL_PATH: terminal_path ... is the MetaTrader 5 of the live bots (...): install a separate MetaTrader 5
  for slot N and set terminal_path in mt5_credentials.json to its terminal64.exe. The bot attached to no terminal and
  does not trade ...', then the three start attempts and 'all 3 start attempts failed (LIVE_TERMINAL_PATH: ...)'. It
  comes at most every 15 minutes, as in the strategy log: a launcher restart (every 30 s) that the limit holds back
  writes no line at all (`_boot_flush`). The same holds for a start refused on `TERMINAL_IN_USE`. This needs
  all 3 attempts of the start held back: a start whose other attempt failed another way (a login by the bot
  that failed, an exception) is written whole.
- The login rule: 'the terminal shows no account yet (account_info() answered None, last_error ...): the bot reads it
  again every second for up to 15 s before any login' (INFO ACCOUNT); 'no login: account not known: ... ; the bot
  detached and tries again later' (WARN ACCOUNT: an IPC error); 'the terminal showed no account for 15 s: the bot logs
  in itself (login N on SERVER). Log this MetaTrader 5 into the slot's demo account once by hand ...' (WARN ACCOUNT).
  No password is ever written.
- The limits per problem: RECONNECT_FAILED once for each reason, then at most every 15 min for it (its ERROR line
  ends with '; N more failed attempt(s) with this reason since its last RECONNECT_FAILED'); every other attempt is a
  WARN TERMINAL line. TERMINAL_IN_USE once for each account the terminal holds.
- A fill is a leg of the basket from the order's answer (`_record_fill`): the BASKET line of the entry or the add has
  'position N is a leg of the basket from its fill (its id from the order's answer; ...)' and `recorded=N`; the poll
  that lists it a DEBUG line; an entry gone before it was ever listed is a CLOSE line 'the BUY entry [N] is gone
  before the terminal listed it ...'; a close that could not reach an add not listed yet is a WARN CLOSE 'is
  incomplete: ... not listed by the terminal yet ...: the basket stays open' (the headline says it too).
- A close that closed nothing (close_by_type found none of this bot's positions: another account just then, or the
  positions already gone): WARN CLOSE '... closed nothing ...; nothing is booked, and the close is decided again next
  poll'. (On the Turtle branches: 'the trade stays booked, and the close is decided again next poll'; the next close
  says 'on the next try', or, when the legs are gone, 'the trade ended: ... the bot's close of HH:MM had closed
  nothing'.)

## 5. Who reads them: `dashboard.py`

The dashboard reads these files and nothing else (no terminal call), every `DASHBOARD_REFRESH_INTERVAL`. The same
`dashboard.py` runs on the Turtle demo branches: it takes `strategy` from the trace (without a trace, `STRATEGY` of
`constants.py`) and draws that strategy's page; on this branch the trace has the `basket` block, never `turtle`.

| tab | reads |
|---|---|
| status bar | `<SYMBOL>_trace.json`: `t` (its age: fresh under 15 s, slow under 60 s, stale after), `health`, `account`, `market` (`tick_t`: the last tick's age now), `stale`; the ERROR lines of the last hour from the newest 3 MB of `logs/<SYMBOL>_events.jsonl`; from the same file a refused start (below) |
| Live | the trace's `decision` (headline, gates in order, `blocked_by`, this poll's `orders`) and `basket`; `<SYMBOL>_bars.json` (the forming bar moved with `market.bid`); `<SYMBOL>_trades.json` `closed` for the chart's entries and exits; the newest 256 KB of `logs/<SYMBOL>_events.jsonl` |
| Trades | `<SYMBOL>_trades.json` (`t`, `summary`, `balance_curve`, `closed`) and the trace's open basket (`basket.open`) |
| Log | the newest 3 MB of `logs/<SYMBOL>_events.jsonl`, the newest 512 KB of a day's `logs/<SYMBOL>_<day>.log` (download: the whole file) |
| Changes & issues | the WARN and ERROR lines of the newest 3 MB of `logs/<SYMBOL>_events.jsonl`, grouped by kind (below), errors first; the branch's `CHANGELOG.md`, version by version |
| History & settings | `daily_trade/<SYMBOL>/*.json`, `historical_summary.json`, `logs/<SYMBOL>_strategy_log.json`, the CONFIG lines of the bot's start (the text log of `health.started_utc`'s day; `constants.py` when they are not there), the raw files (a fixed list: the trace, trades, `<SYMBOL>.json`, `account.json`, the state files, the exit reasons, the bars' header) |

A file that is missing, cut in the middle or of an unexpected shape shows as such (an empty state, or a card with the
error and its traceback, files named, not their folders); the rest of the page is unaffected. The charts take times as
UTC wall-clock text (a number would be shown in the browser's own time zone).

**What a request may name.** The page has no login and listens on `DASHBOARD_HOST` (`0.0.0.0`): anyone who can reach
its port can send any value to a callback. A symbol is taken only when the dashboard lists it (the `*_trace.json`
files of `OUTPUT_DIR`, else `symbols.json`; plain names: letters, digits, `.`, `_`, `-`), a day only when it reads
`YYYY-MM-DD` and `logs/<SYMBOL>_<day>.log` exists; another symbol falls back to the first one, another day to today's
file (the download then sends nothing). Every path is a fixed name inside `OUTPUT_DIR`; one that would leave it (`..`,
an absolute path, another drive) is refused.

**A stale trace** (older than 60 s: the bot is down, the PC slept, or the loop fails before its trace hook): the age
chip is red and every other chip is neutral with 'as of HH:MM' (the trace's time); the market chip counts the last
tick's age now; the errors of the last hour come from the events file (it keeps getting the loop's ERROR lines); a
red banner above the headline says the page is the bot's last poll; the strategy, the checks, the position and the
uptime say 'as of' / 'not writing'. A skipped poll (fresh, `stale` true): 'Market: unknown (terminal not read)',
'votes kept from the last poll'.

**A refused start** (since v3.9.2-demo.5): when the newest ERROR START line of the events file (LIVE_TERMINAL_PATH, all
3 start attempts failed, a refused design or credentials file, the job failed) is newer than the trace and than the
last 'trading loop started' line, the bot is not running. The status bar (every tab) has a red chip 'Not started:
<kind> (HH:MM)' and a red box: what the bot wrote, what it means and what to do (LIVE_TERMINAL_PATH: install a
separate MetaTrader 5 for the slot, set terminal_path to its terminal64.exe, log it into the slot's demo account once
by hand with 'Save password': README, How to run, steps 1 and 2).

**The issue kinds** (Changes & issues; the first that matches the line's message): `TERMINAL_IN_USE`,
`LIVE_TERMINAL_PATH`, `ACCOUNT_NOT_KNOWN` (no login: the account was not known), `BOT_LOGIN` (the bot logged in
itself), `ACCOUNT_REFUSED`, `RECONNECT_FAILED`, `MT5_INIT_FAILED`, `START_FAILED` (a start attempt or the job failed),
`TERMINAL_ERROR`, `POLL_FAILED`, `TRACE_FAILED`, `WRITE_FAILED`, `CLOSE_NOTHING` (a close that closed nothing),
`CLOSE_INCOMPLETE`, `CLOSED_OUTSIDE`, `D1_LATE`, `ORDER_REFUSED`; any other by its category and the shape of its
message. Each has what it means and what to do.

**An open basket's leg not listed yet**: the position card has the chip 'N leg(s) not listed yet', a line with each
leg (its kind, lots, price, how long ago it filled) and that the P/L, stop and target use the listed legs until the
terminal lists it; the legs table has its row, 'not listed yet'.

**trades.json missing or old**: missing or unreadable, the Trades tab, the balance chart, the position card and the
chart note say so (the closed trades are not known; never 'No trade yet'); older than 3 minutes (it is rewritten at
least every minute), the Trades tab shows when it was written and warns that its trades are as of then.

**The chart**: the candles are bid. A level the bot compares with the ask (a sell basket's stop / target / broker
stops, a buy basket's next add) is tagged '(ask)', and an ASK line is drawn next to the BID line. A close in 'This
poll's orders' reads 'CLOSE SELL position 100001 (BUY order, 0.01 lot)'. (On the Turtle branches also: the Turtle's
levels, and its BUY / SELL LEVEL drawn faint while its orders are used or a trade is open.)
