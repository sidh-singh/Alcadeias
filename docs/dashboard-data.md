# The dashboard's data: what the bot writes (schema 1: the basket strategy and the Turtle)

`tracelog.py` writes these files into the bot's output folder (`OUTPUT_DIR` in `constants.py`: `C:\Alcadeias\<branch>`
on the server). Nothing the bot decides depends on them. This file is the same on all 20 real-money branches: a
branch trades the basket strategy (§1) or the Turtle (`STRATEGY = 'turtle'`, §5).

**Since v3.9.2-live.1 (the real-money layer)** the account is a real one and the figures are the account's own:
every `virtual_*` field is gone, the trace has the new sections `sizing`, `safety`, `open_hold` and `foreign` (§1),
and the account number appears as its last 4 digits only (`...1234`) in every file. The safety's own files are in
`docs/live-safety.md`.

| file | what | when |
|---|---|---|
| `<SYMBOL>_trace.json` | the latest decision snapshot | after every poll (a poll takes at least 1 s), so every change of action, position or gate result is in it |
| `<SYMBOL>_bars.json` | bid OHLC bars for the chart | the first poll, then at most every 30 s while a bar moves or a new one starts |
| `<SYMBOL>_trades.json` | this bot's trades from the deal history | the first poll, after every fill and close (and on the poll after), at least every 60 s |
| `logs/<SYMBOL>_<YYYY-MM-DD>.log` | the text log, one line per event | as it happens; one file per UTC day; kept: today and the `LOG_KEEP_DAYS` (7) UTC days before it |
| `logs/<SYMBOL>_<YYYY-MM-DD>_events.jsonl` | the same lines as JSON | as it happens; one file per UTC day, kept like the text log (it replaces the size-rotated `_events.jsonl`) |
| `logs/<SYMBOL>_<YYYY-MM-DD>_samples.jsonl` | one line of figures a minute (§4, the samples) | every minute, also from skipped polls (with nulls); kept like the text log |
| `journal/<SYMBOL>_<YYYY>.jsonl` | the permanent journal: one JSON line per `start`, `order`, `trade`, `safety`, `skip`, `day` and `issue` (§4, the journal) | as it happens (written with the batch after it); never deleted |
| `state/<SYMBOL>_journal_state.json` | which closed trades the journal already holds, the open trade's entry context and extremes, the trades that ended and wait for the history, the problems that last, the running day's figures; with the account (`login_sha`, `login_tail`) and `branch` | at the open, at the close, when an extreme changed (at most every 30 s), when a problem starts, changes or ends, and every 5 minutes for the running day |
| `state/<SYMBOL>_exit_reasons.json` | the exit reason the bot recorded per position | at every close |
| `state/<SYMBOL>_turtle_trades.json` | the Turtle's journal per trade: N at the entry, the level, the vote, every leg with its add level, every stop move, the exit | at every entry, add, stop move and exit |

`app.py` writes the rest of the bot folder. The old dashboard's files are written as before: `<SYMBOL>.json` (its
section `demo` is called `bot` since v3.9.2-live.1: `branch`, `magic`, `design`, and `basket`, `last_close` on the
basket / `turtle_book` on the Turtle), `account.json` (the basket loop; the Turtle's loop has never written it -- its
numbers are in `<SYMBOL>.json` and in the trace's `account`), `active_config.json`,
`logs/<SYMBOL>_strategy_log.json` (the events, newest first, at most 200), `daily_trade/<SYMBOL>/<dd>_<mon>_<yyyy>.json`
(one per server day; the newest 400 are kept) and `daily_trade/<SYMBOL>/historical_summary.json` (since a day before
the live start; 10 years while that is not known). Its state files, each of them stamped with the account it was
written on (`login_sha`: SHA-256 of the account number; `login_tail`: `...1234`) and `branch`:

| file | what | when |
|---|---|---|
| `state/<SYMBOL>_state.json` | the basket loop: `{version, symbol, magic, design, branch, login_sha, login_tail, saved_at, basket, last_close}` (the open basket keeps its `sizing`) | at every change of the basket |
| `state/<SYMBOL>_turtle.json` | the Turtle's book: `{version, symbol, magic, design, system, branch, login_sha, login_tail, saved_at, book}` (the book is `turtle.py`'s) | at every change of the book |
| `state/<SYMBOL>_turtle_side.json` | the Turtle's record beside its book: `{version, symbol, magic, branch, login_sha, login_tail, saved_at, trade}`, `trade` = null or `{entry_time, ticket, side, units, sizing, missed_add ({level, step, at}: a pyramid a block held back), adds_stopped (true: the trade takes no more adds)}` | at the entry, when a pyramid is held back or stopped, and at the exit (`trade` null) |
| `state/safety_state.json` | the safety's own state of this bot (`docs/live-safety.md`, §6) | by `safety.Tracker.flush`, after the orders of a poll, when it changed |
| `state/safety_closes.json` | closed trades waiting for their result (the losing-trades rule): `{version, symbol, magic, branch, login_sha, login_tail, saved_at, turtle, queue}`, `turtle` = null or `{entry_time, ids (every position id the running Turtle trade ever had), decision_pnl}`, `queue` = `[{trade_key (the smallest position id), ids, opened_at, closed_at, decision_pnl, kind ('basket' / 'turtle'), reason}]` | after the orders of a poll, when it changed |
| `state/live_start.json` | when this bot first traded this account: `{time (the earliest of the first poll that passed the account guard, its oldest open position and its first deal in the history), time_utc, account_balance, branch, login_sha, login_tail, symbol, magic, written_at, history_read}` | at the end of the first poll that passed the account guard; again only while the history could not be read (`history_read` false, every 60 s; the time can only move back) |
| `state/<SYMBOL>.lock` | empty: the one-process lock, held open by the running bot | at the start |

A state file written on another account (another `login_sha`) is never used: it is renamed
`<name>.other-account-<yyyymmdd_hhmmss>` (UTC) and the bot starts without it, as without a file (the event
`STATE_OTHER_ACCOUNT`). `safety_state.json` and the account claim that cannot be read as such go to
`<name>.not-readable-<yyyymmdd_hhmmss>`. Files set aside are never deleted by the bot (nor by the sweep of old temp
files).

Beside the bot folder: the account folder `C:\Alcadeias\live<n>_account` (the safety's files, the account claim, the
login budget: `docs/live-safety.md`, §3) and `C:\Alcadeias\terminal_claims\<sha1 of the terminal path>.json` (which
account a MetaTrader 5 belongs to).

**Reading them.** The files of `tracelog.py` and the state files are replaced atomically (a temp file, then a
rename): a reader sees the old file or the new one, never half of one. (`<SYMBOL>.json`, `account.json`,
`active_config.json`, the strategy log and the daily files are written in place, as before.) The files of
`tracelog.py` are compact (no indentation). A file can be missing (the bot has not run yet, or a write failed);
every field can be `null`. Check `schema` (1). Times are UTC epoch seconds in `t` / `..._t` fields,
with an ISO copy in `..._utc` fields (`2026-11-17T08:00:01.500Z`). Money is USD of the account; prices are bid / ask
as the terminal quotes them, rounded to the symbol's `digits` where the bot computed them.

## 1. `<SYMBOL>_trace.json`

```
schema, branch (`BRANCH`), mode ('live'), version (`VERSION`), design, strategy ('basket' | 'turtle'), symbol,
mt5_symbol, magic, t, time_utc, poll (count since start), stale (true: this poll could not read the terminal;
account / market / basket / turtle are the last good poll's), stale_since_utc, health, account, sizing, safety,
open_hold, foreign, market, decision, basket (null on the Turtle), turtle (null on the basket)
```
A stale (skipped) poll marks what it kept: `market.status` is 'UNKNOWN' (its `message` says the terminal was not read;
bid / ask are the last ones read), `basket.fresh` is false, `health.market_live` null. `account`, `sizing` and
`safety` are then copies of the last good poll's, `open_hold` is null, and `foreign` keeps the last good poll's
positions with the old bot as the bot's flag says now (it is looked at on every pass of the loop, a refused one
too).

### health
`connected`, `terminal_problem` · `account_ok`, `account_problem`, `login_tail` (the account the terminal holds, as
`...1234`), `own_login_tail` (the account of the bot's credentials; before v3.9.2-live.1 these two were the full
numbers `login` and `demo_login`), `trade_mode` / `trade_mode_name` (demo / contest / real: the terminal's own
words; the bot accepts only real), `margin_mode` / `margin_mode_name` (hedging / netting / exchange) ·
`trading_not_allowed` (`[]`, or what stands in the way of every order: `algo_trading_off`, `python_api_disabled`,
`account_trade_disabled`, `account_expert_disabled`; a fact the terminal does not report counts as no problem),
`disk_low` (less than 2 GB free: DEBUG / INFO lines and the samples are dropped), `terminal_build`, `ping_ms` ·
`market_live` (a tick or an M1 bar within `MARKET_LOOKBACK_MINUTES`), `market_status`, `minutes_since_activity`,
`last_tick_age_s` · `loop_ms` (the poll's work), `trace_ms` (this module's own time in the last poll),
`poll_gap_s` · `reconnects`, `errors_1h` (ERROR lines in the last hour), `skipped_polls`, `failed_streak`,
`started_utc`, `uptime_s`, `log_write_failures`. A skipped poll adds `positions_problem` when the positions read failed.
The reconnect after a lost terminal: `reconnect_failed_attempts` (failed attempts since the terminal was lost; 0 when
connected), `next_reconnect_t` / `next_reconnect_utc` (the next attempt: 5, 10, 30, then every 60 s), `outage_s` (how
long the terminal has been lost), `connect_problem` (why the last start-up or reconnect failed, e.g.
`TERMINAL_IN_USE: the terminal at ... is logged into another account ...`; null once connected), `terminal_in_use`.

### account
The real account, which the two bots of an account share. `login_tail` (`...1234`), `server`, `currency`,
`leverage`, `trade_allowed`, `trade_expert` · `balance`, `equity`, `margin`, `margin_free`, `margin_level`,
`account_profit` · `floating_account` (the open P/L of the whole account), `floating_own` (this bot's own open P/L,
its magic number only; `own_open_pl` is the same figure), `own_closed_pl` (this bot's closed P/L since its live
start, from the last read of the deal history: `summary.net` of `<SYMBOL>_trades.json`; null before the first
read), `day_realised` (booked today by both bots: the balance minus `safety.day.start_balance`; deposits and
withdrawals are not in it) · `units`, `lot` (units x mtqty), `mtqty`, `share` (`ACCOUNT_SHARE`), `step_up_balance`,
`unit_max_limit`, `next_unit_at` (the account balance from which a new trade gets one more unit: units x step /
share; null at the cap) and `unit_rule` (text: `unit = floor(<share> x account balance / <step>) + 1, at most <n>,
re-derived only while flat`).
Gone since v3.9.2-live.1: every `virtual_*` field (`virtual`, `virtual_balance`, `virtual_balance_source`,
`virtual_start_balance`, `virtual_start_date`) and what was counted from the virtual balance.

### sizing
How the unit of a new trade is counted (the poll local `_sizing` of `app.py`): `share` (`ACCOUNT_SHARE`, 0.5: two
bots trade one account), `account_balance`, `sizing_balance` (share x account balance, to the cent), `step`
(`step_up_balance`), `units` (1 + the whole steps in the sizing balance, at most `unit_max`), `lot`, `unit_max`,
`next_unit_at_account_balance` ((units x step) / share; null at the cap), `source` ('balance': derived on this poll,
flat; 'entry': fixed at the entry of the open trade; 'positions': an open trade taken over from the terminal without
its record, the balances not known; 'unknown': flat and the balance is not known), `t` (when the balance was read).
An open trade keeps the unit it opened with; without a balance (`sizing_balance` null or <= 0) no new trade is
opened on that poll (an add keeps the unit of its trade).

### safety
The view of the bot's safety (`safety.Tracker.view()`, the poll local `_safety`; the rules and the files:
`docs/live-safety.md`): `enabled`, `blocked`, `hold`, `pending`, `account_blocked`, `bot_blocked`, `blocked_scope`
('account' / 'bot' / null), `state` ('on' / 'checking' / 'account_blocked' / 'bot_blocked' / 'off' / 'error'),
`reasons` (every sentence of the state, as the bar shows them), `since`, `period` (the id counting last started
with), `at`, `started_at`, `error` · `drop` {`pct`, `limit`, `peak`, `peak_at`, `balance`} · `day` {`pct`, `limit`,
`day0`, `day0_at`, `day`, `since` ('midnight' / 'restart'), `start_balance`, `start_at`, `cash`} · `streak` {`count`,
`limit`, `waiting`} · `partner` (the other bot of the account, from its status file, or null) {`branch`, `seen_at`,
`blocked`, `bot_blocked`, `drop_pct`, `day_pct`, `limits_differ`, `account_differs`, `period`, `stale`} · `limits`
{`drop_pct`, `day_pct`, `streak_n`} · `account_dir`, `login_tail`. The bot opens nothing new while `blocked` or `hold`
is true. Without a usable Tracker (not loaded yet, or it failed) the bot makes this view itself: `blocked` = the
switch as the account folder says it, `state` 'error' (or 'off'), `error` '<type>: <message>', the meters of the
last view.

### open_hold
null, or why this poll did not send an opening order it would have sent: `why` ('old_bot': an old bot shares the
terminal; 'safety': blocked (a limit, a block of this bot, a failing check); 'safety_checking': the safety holds
(a balance change that would meet a limit is being checked, or a result that could be the last losing trade is
awaited); 'balance_unknown': an entry while the balance is not known or not above 0; 'refused_backoff': the slower
retry after refused opens), `side`, `kind` ('entry' / 'add' / 'pyramid'), `price` (the quote it would have gone out
at), `until` (epoch seconds of the next try for 'refused_backoff', else null), `refusals` (refused opens in a row),
`since` (for 'refused_backoff': when the broker's first refusal of the streak came; null for every other `why`).
The reasons are tested in that order. Closes are never held.

### foreign
What is on the bot's symbol in this account and is not the bot's, from the poll's own positions read:
`positions` (how many; null when no positions read has told it yet), `examples` (the first three: `ticket`
('...1234'), `magic`, `comment`, `volume`, `side`, `sl`, `tp`, `price_open`), `old_bot_age_s` (the age in seconds of the newest of the old bots' files `account.json`,
`XAUUSDm.json`, `BTCUSDm.json` in the parent folder of `OUTPUT_DIR` while an old bot is alive, i.e. that file
changed less than 120 s ago; null whenever no old bot is alive), `old_bot_same_terminal` (an old bot is alive and
this bot's `terminal_path` is the old bots' MetaTrader 5: no opens while it lasts).

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
| `BLOCKED` | the strategy wants an entry (`side`) but a gate after it refuses (`reason` window / votes unknown / trend / volatility unknown / contract size unknown), or, since v3.9.2-live.1, the order was held (`reason` = `open_hold.why`: safety / safety_checking / refused_backoff / balance_unknown / old_bot; tested before `OPEN_FAILED`) |
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
- An opening order held back before the send (`open_hold`) is the gate `open_hold` ('New orders allowed', `value`
  the `why`, `note` the reason in words): a held entry has role `need` and the action `BLOCKED` (basket and
  Turtle); a held add (the basket's ladder add, the Turtle's pyramid) has role `add`. A Turtle trade that takes no
  more adds (a pyramid held back during a block, and the price then more than one add step beyond its level) has
  the failing add gate `adds_stopped` ('Adds still taken').

| path | gate keys |
|---|---|
| every poll | `terminal`, `account`, `positions`, (`market_data`), `market_live`; a poll skipped by the account read again after the positions: `terminal`, `account`, `positions`, `account_recheck` |
| flat | `pause`, `open_score`, `agreement`, `window`, `votes_known`, `trend`, `volatility`, (`contract_size`), (`open_hold`) |
| basket | (`fill_listed`), (`legs_outside`: legs closed outside the bot, value their ids, or `close_retry`), `stop`, `target`, `force_close`, then `ladder` (no adds) or `ladder_trigger`, `ladder_gate`, (`ladder_gap`), (`open_hold`) |
| both sides open | `one_side` |

**orders**: `{t, kind (open / add / close), side, order_side, symbol, volume, price, sl, tp, position, magic, comment,
refused, retcode, retcode_text, done, result_price, result_volume, order, deal, result_comment, last_error, ms, bid,
ask, spread, fill_price, slippage, slippage_usd}` (the quote is the tick the helper read to build the request; the
slippage as in the journal's order line, §4).
`refused` is true for a request the account guard stopped and `'safety'` for one the safety guard of `buy()` /
`sell()` stopped (worded "not sent: the safety guard refused it"); neither reached the terminal.
`side` is the side of the trade: for a close, the side of the position it closes; `order_side` is the order's own
type (a SELL position is closed with a BUY order). `kind` comes from the loop's own state (the basket loop's `state`,
the Turtle's book): an order on the side of the open basket or trade is an `add`, also on the first poll after a start.

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
{schema, symbol, mt5_symbol, magic, design, t, time_utc, since_t, since_utc, live_start_t, live_start_utc,
 closed: [...], open: [...], balance_curve: [{t, utc, v, id, pnl}], summary: {...}}
```
Real numbers only (v3.9.2-live.1): this bot's closed trades since its live start (`state/live_start.json`:
`live_start_t`, null while it is not written; the read, `since_t`, starts a day before it, or 90 days back while
there is no live start), their P/L in dollars, and no synthetic balance. The `virtual` and `virtual_start_balance`
keys are gone.
- A trade is a basket: the positions of one side that were open together. `closed` (oldest first, the newest
  2000): `{id (its first position), side, legs, lots, open_t, open_utc, open_price (lot-weighted), close_t,
  close_utc, close_price, hold_s, pnl (profit + swap + commission + fee), profit, swap, commission, fee,
  exit_reason, exit_reason_text, bot_reason, balance_after (the running total of this bot's closed P/L after it),
  result (win / loss / flat), status}`; a leg: `{position_id, side, lots, open_t, open_price, close_t, close_price,
  closed, profit, swap, commission, fee, net, deal_reasons, magic}`.
- `exit_reason`: `target`, `stop`, `force_close`, `close_retry` (as the bot recorded it), `backstop` (the broker's
  stop: the position's sl), `broker_target`, `stop_out`, `closed_outside` (from the terminal, or while the bot was
  down), `leg_closed_outside` (a leg closed outside the bot -- its backstop, a stop-out or by hand -- and the bot closed
  the rest; the legs' `deal_reasons` say how), `unknown` (closed by the bot before it recorded reasons).
- `open`: the open basket with its live levels (the trace's `basket.open`, `live: true`), or the open baskets of the
  deal history.
- `balance_curve`: the running total of this bot's own closed P/L, from 0 at the live start, after every closed
  trade (it sizes nothing: the units come from the account balance, `sizing`). `summary`: `closed`, `wins`,
  `losses`, `win_rate`, `net` (this bot's closed P/L: the trace's `account.own_closed_pl`), `gross_win`,
  `gross_loss`, `best`, `worst`, `avg_hold_s`, `exit_reasons`, `balance_now` (the running total of every deal read),
  `deals`, and the deepest fall of the running total in dollars: `deepest_fall`, from `deepest_fall_from_t` /
  `_utc` (its high) to `deepest_fall_to_t` / `_utc` (its low; both null without a fall).

## 4. The text log and the events file

```
2026-11-17 08:05:23.700 UTC | CLOSE | CLOSE | SELL basket closed (stop): 2 position(s), P/L -$2.31 at the decision, realised -$2.31 | side=SELL reason=stop_loss decision_pnl=-2.31 realised_pnl=-2.31 lost=true positions=2 ...
```
`line.split(' | ', 4)` gives time, level, category, message, `key=value` pairs (text values with spaces are
quoted, lists and dicts are JSON). The message never holds ` | `. An ERROR from an exception is followed by its
traceback, every line indented by 4 spaces.

**When lines are written.** No file is written while the bot holds `mt5_lock` (it sends orders and reads the terminal
inside it). The ORDER and FILL lines (made inside `MT5PositionHelper._send`) and any line made inside the lock (an
event, a state save, a start-up line of a reconnect) wait in memory and are written at the end of the poll, by a
skipped poll, the exception hook or the job's last lines; each keeps its own time and its place. If the process is
killed in between (a fraction of a second after an order), those lines are lost; the order itself is in the deal
history (`<SYMBOL>_trades.json`). A close's ORDER line: `close position 100001 (SELL 0.01 lot, with a BUY order) at
1,781.644 -> done (10009) | kind=close side=SELL order_side=BUY ...`.

**A step that fails.** The poll hook runs each step on its own (the sections, the decision, the trace file, the bars,
the trades, the heartbeat, the bookkeeping): one that raises is an ERROR TRACE line ('the trace hook poll() failed in
its step _bars: ...', again at most every 10 min with the count) and the others go on. The deal history is read again
at most every 5 s after a failed read and every 60 s after a failed build.

| level | lines |
|---|---|
| DEBUG | DECISION (every change of the action or of a checked gate, with all the gates), STATE (state saved), BASKET (a position listed -- also a leg recorded from its order, listed now, or listed under another id -- the ladder armed), SIGNAL |
| INFO | START, CONFIG (every effective constant, symbols.json, the contract size; never `OLD_LOGINS_SHA256` or a name that holds `PIN`, `PASS` or `SECRET`), STATE, ACCOUNT (the terminal shows no account yet: read again every second for up to 60 s; logged in, or no login when the terminal already holds this bot's account; the checks passed), TERMINAL (connected again, after how long and how many failed attempts), BASKET (opened, added; `recorded=<id>`: the position id taken from the order's answer), PAUSE (start, end), MARKET, WINDOW, DATA, HEARTBEAT (every minute) |
| ORDER | every order request and its result (retcode, comment, price, sl, tp) |
| FILL | an entry or add filled |
| CLOSE | a basket closed, with the reason and the P/L (also one closed outside the bot; an entry gone before the terminal listed it; after a leg closed outside the bot, the close of the rest and the booking of the whole basket) |
| WARN | an order not filled, a terminal read error, missing bars, a file that could not be written, a slow poll, BASKET: legs of the basket closed outside the bot, CLOSE: a close that is incomplete (a leg refused, or an add not listed yet: the basket stays open) or that closed nothing (decided again next poll), ACCOUNT: no login because the account is not known (an IPC error), the bot logging in itself after 60 s of no account (only with a password in the file, on a terminal no other account has claimed, and inside the login budget), TERMINAL: every failed reconnect attempt that the strategy log leaves out (it has RECONNECT_FAILED once for each reason, then at most every 15 min for that reason) |
| ERROR | an exception (with its traceback), the account refused (also by the account read again right after the positions), TERMINAL_IN_USE (the terminal holds another account: no login, the terminal is left as it is; once for each account, then every 15 min), START: a start only the owner can put right (the mode, a refused design or deployment block, `symbols.json`, the credentials file, the old account, another server, an account that is not real / hedging / USD, the account claim; the line of the job's end has `needs_owner` and exit code 78) and all 3 start attempts failed (with the problem), a reconnect that failed (as in the strategy log, with `not_logged_since`), TRACE: a step of the trace that failed (the trading goes on) |

The events of the real-money layer (`app.py` `_log_event`; each also in `logs/<SYMBOL>_strategy_log.json`, with
its details as `kv`):

| level | category | events |
|---|---|---|
| ERROR | SAFETY | `SAFETY_ERROR` (the safety check failed: no opens while ON) |
| WARN / INFO | SAFETY | `SAFETY_BLOCKED` (once per new block, with the reasons and the meters), `SAFETY_SKIP` (an opening order held back: once per kind and side, again after 15 minutes; `hold` = the `open_hold`), `SAFETY_UNBLOCKED` (INFO) |
| ERROR | ACCOUNT | `FOREIGN_POSITIONS`, `OLD_BOT_SAME_TERMINAL` (at the start: no attach; while running: no opens; at the start and on a reconnect: no own login on that MetaTrader 5), `OTHER_PROGRAM`, `LOGIN_REFUSED`, `TERMINAL_IN_USE`, `SERVER_MISMATCH` (this bot's account number on another server), `ACCOUNT_REFUSED` |
| WARN / INFO | ACCOUNT | `OLD_BOT_RUNNING` (an old bot with another MetaTrader 5), `LOGIN_WAIT` (no account in the terminal and no own login allowed now: `why` no_password / terminal_claimed / login_budget / claim_unreadable / budget_unreadable / budget_unwritable), `ACCOUNT_OK` (INFO) |
| ERROR / INFO | TERMINAL | `TRADING_NOT_ALLOWED` (with `reasons`), `TRADING_ALLOWED` (INFO, when it is over) |
| ERROR | STATE | `STATE_OTHER_ACCOUNT` (a state file of another account set aside; `held_open_trade`, `file`, `set_aside_as`, `problem`) |
| WARN | ORDER | `BUY_REFUSED`, `SELL_REFUSED`, `BUY_MORE_REFUSED`, `SELL_MORE_REFUSED` (an opening order not filled: the retcode and the broker's comment, `refusals`, `broker_refusals`, `refusing_since`; the first 3 of a streak one by one, then one line per 30 s with `summary` and `not_logged_since`; an order MetaTrader 5 did not answer has `no_answer: true`, a `note` and no retcode, its line says that the broker refused nothing, and it does not count for the slower retry). `BUY_EXECUTED` and its siblings are logged only for an order that was done |
| WARN | CLOSE | `CLOSE_RESULT_UNKNOWN` (a closed trade's result not in the history after 10 minutes) |
| WARN | TRADE | `TURTLE_ADDS_STOPPED` |
| ERROR / INFO | DISK | `DISK_LOW` (less than 2 GB free), `DISK_OK` (the trace's own lines: once when it starts and once when it ends) |

The five start refusals `TERMINAL_IN_USE`, `SERVER_MISMATCH`, `LOGIN_WAIT`, `LOGIN_REFUSED` and
`OLD_BOT_SAME_TERMINAL` are logged the first time, then at most every 15 minutes for the same problem, also across
the launcher's restarts.

A HEARTBEAT line comes every minute: a gap of more than a minute means the bot was not running. The same
exception at the same place is written again at most every 10 minutes, with the count of the repeats. Past 50 MB
in a day the text log and the events file take only WARN and ERROR lines, and each stops at 100 MB a day except
for one "N lines dropped" line a minute. All the day files of the bot together stay under 500 MB (`LOG_MAX_BYTES`;
older days go first, today's never). With less than 2 GB free on the disk (asked once a minute) DEBUG and INFO
lines and the samples are dropped (`DISK_LOW`); ORDER, FILL, CLOSE, WARN and ERROR lines and the journal are still
written. Old day files go by the date in their name (never by their age on the disk), at the start, at every new
UTC day and once an hour; only this symbol's three day patterns are ever deleted. Temp files a killed process left
of the bot's own files (`<file>.tmp`, `<file>.<digits>.tmp`, `<file>.<digits>.<hex>.tmp`, in the bot folder and in
`state/`) go when they are a day old.

`logs/<SYMBOL>_<YYYY-MM-DD>_events.jsonl`: one JSON object per line: `{t, time, level, cat, msg, kv, data,
traceback}`; `data` holds the full gate list of a DECISION line, the state of a STATE line. A text line or an events
line that would hold the full account number is written with its last 4 digits instead.

**The samples** (`logs/<SYMBOL>_<YYYY-MM-DD>_samples.jsonl`), one line per UTC minute, also for a minute of skipped
polls (then mostly nulls): `{t, utc, polls, skipped, bid, ask, spread_min, spread_avg, spread_max, ticks_seen (polls
whose tick differs from the poll before), tick_gap_max_s (the largest local time minus tick time), clock_offset_s
(the smallest of the minute, on a live market), balance, equity, margin, margin_free, margin_level, floating_own,
floating_account, positions_own, positions_foreign, drop_pct, day_pct, streak, units, poll_ms_avg, poll_ms_max,
trace_ms_avg, trace_ms_max, suppressed_polls (polls with an `open_hold`), ping_ms}`. The figures are the last of the
minute. A stop loses the minute that was not finished.

**The journal** (`journal/<SYMBOL>_<YYYY>.jsonl`, never deleted): one JSON line `{t, utc, kind, ...}` per
- `start` (once per start of the loop, with the first poll that read the terminal, or a minute after the start
  when none did): `version`, `branch`,
  `partner_branch`, `design`, `design_summary`, `strategy`, `symbol`, `mt5_symbol`, `magic`, `mode`, `pid`,
  `python`, `schema`, `out_dir`, `constants` (every effective constant of the CONFIG lines; never
  `OLD_LOGINS_SHA256` or a name with `PIN`, `PASS` or `SECRET`), `symbols_json`, `share`, `safety_limits`
  {`default_on`, `drop_pct`, `day_pct`, `streak_n`}, `account` {`login_tail`, `server`, `currency`, `leverage`,
  `balance`, `equity`}, `terminal` {`build`, `ping_ms`}, `first_poll_t`;
- `order` (every request and its answer): `action` (open / add / close), `side`, `order_side`, `symbol`, `volume`,
  `price`, `bid`, `ask`, `spread`, `quote_t` (the quote the helper read to build the request), `sl`, `tp`,
  `position`, `magic`, `refused` (true: the account guard; 'safety': the safety guard of `buy()` / `sell()`),
  `retcode`, `retcode_text`, `comment`, `done`, `order`, `deal`, `fill_price`, `fill_volume`, `slippage` (fill - ask
  for a BUY order, bid - fill for a SELL order: above 0 = worse than quoted), `slippage_usd`, `last_error`, `ms`;
  without a fill or with a retcode that is not done the fill and slippage fields are null;
- `trade` (once per closed trade that closed after the live start, also across restarts; at most 200 per read of
  the history): `id`, `side`, `legs`, `leg_ids`, `lots`, `open_t` / `_utc`, `open_price`, `close_t` / `_utc`,
  `close_price`, `hold_s`, `pnl`, `profit`, `swap`, `commission`, `fee`, `result`, `exit_reason`,
  `exit_reason_text`, `bot_reason`, `deal_reasons`, `watched` ('full': seen from its entry to its close; 'part'; 'none':
  the close was not seen), `rebuilt`, `restarts`, `entry` (the facts fixed at the entry: side, units, target, stop,
  the volatility unit or N, the scores and votes, `sizing`), `max_pnl` / `_t`, `min_pnl` / `_t` (this bot's
  extremes of floating P/L while open), `polls_watched`, `watched_from_t`, `closed_by`, `decision_pnl`,
  `balance_before`, `balance_after` / `_t` (the account balance at the first poll after the bot saw the close),
  `safety_after` {`drop_pct`, `day_pct`, `streak`, `state`, `blocked`}, `own_total_after`; the Turtle also
  `exit_detail`, `exit_stop`. A field the bot does not know is null, never 0;
- `safety` (every item of `Tracker.take_events()`: `event` trip / fresh_start / switch / cash / cash_start / trade /
  hold / hold_end / state_put_aside, with its numbers and `branch`);
- `skip` (an opening order the safety, an old bot or the slower retry held back: the `open_hold` fields,
  `safety_state`, `safety_reasons`; once per kind and side, again after 15 minutes);
- `day` (at the first poll of a new UTC day, for the day that ended): `day`, `balance`, `equity`, `high`,
  `balance_high`, `balance_low`, `booked` (both bots, deposits and withdrawals left out), `start_balance`, `cash`,
  `own_closed_total`, `drop_pct`, `day_pct`, `streak`, `units`, `complete` (the bot ran through both midnights of
  the day), `ran_through_midnight`, `watched_from_midnight`, `watched_whole_day`, `first_t`, `last_t`, `polls`,
  `longest_gap_s`;
- `issue`: `code`, `state` ('start' / 'change' / 'still' every 15 minutes / 'end' / 'event' for a moment), `text`,
  `since`, `lasted_s`. The codes the trace reads every poll: `TERMINAL_ERROR`, `ACCOUNT_REFUSED`,
  `TRADING_NOT_ALLOWED`, `DISK_LOW`, `FOREIGN_POSITIONS`, `OLD_BOT_SAME_TERMINAL`, `OLD_BOT_RUNNING`,
  `SAFETY_ERROR`, `PARTNER_ACCOUNT_DIFFERS`, `PARTNER_LIMITS_DIFFER`, `REFUSED_BACKOFF` (a problem ends after 60 s
  without it); every other WARN / ERROR event by its own name.

A field called `kind`, `t` or `utc` in what `app.py` hands over is written as `subkind`, `t_event`, `utc_event`. The
same line (kind, action, position or side, answer) is written the first 3 times in a row, then once a minute with
`repeats: n` (a filled order is never a repeat). A UTC day's lines stop at 5 MB of the journal for `order`, `safety`
and `skip` lines, 2.5 MB for `start` and `issue` lines and 10 MB for `trade` and `day` lines; then one
`journal_suppressed` line an hour. A line that would hold the full account number is written with its tail.

**The third fix round (v3.9.2-demo.5) in the log, as it stands since v3.9.2-live.1.**
- `LIVE_TERMINAL_PATH` no longer exists: that rule kept a demo bot off the real-money bots' MetaTrader 5, and on a
  real-money branch that MetaTrader 5 is the bot's own.
- A start refused on `TERMINAL_IN_USE` comes at most every 15 minutes, as in the strategy log: a launcher restart
  (every 30 s) that the limit holds back writes no line at all (`_boot_flush`). This needs all 3 attempts of the
  start held back: a start whose other attempt failed another way (a login by the bot that failed, an exception)
  is written whole.
- The login rule: 'the terminal shows no account yet (account_info() answered None, last_error ...): the bot reads it
  again every second' for up to 60 s before any login (INFO ACCOUNT); 'no login: account not known: ... ; the bot
  detached and tries again later' (WARN ACCOUNT: an IPC error); the bot's own login, when it is allowed (WARN
  ACCOUNT 'the terminal showed no account for 60 s: the bot logs in itself ...'); `LOGIN_WAIT` when it is not
  allowed (no password, the MetaTrader 5 claimed by another account, the login budget) and `LOGIN_REFUSED` when the
  server refused it (both events, at most every 15 minutes per problem). The account is written as `...1234`; no
  password is ever written.
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

## 5. The Turtle (`STRATEGY = 'turtle'`; the branches whose code ends in `s2`)

Its loop (`MT5TradingBot._process_turtle`, the rules in `turtle.py`) hands the trace the same things the basket's
does; `health`, `account`, `decision` keep their meaning. `market` has no trading window (`window` says so, `brake` =
the manual brake). Prices the bot compares (`levels`, `stop`, `n`) are exact; the others are rounded to `digits`.

### decision (the Turtle)

| action | meaning |
|---|---|
| `SKIPPED` | as above (the trade is neither managed nor booked; its stop is checked on the next good poll) |
| `NO_DATA` | no quote (`reason` 'quote') or fewer closed D1 bars than `TURTLE_MIN_D1_BARS` (`reason` 'd1 bars'): not trading |
| `MARKET_CLOSED` | no tick for 3 min: nothing decided (an open trade is held, its stop is not checked) |
| `WAIT` | flat: `reason` 'no breakout' (the orders are armed, no level reached), 'orders used' (an entry filled since the last D1 close: none until the next one), 'exit bar' (the M1 bar of the last exit) |
| `BLOCKED` | a level is reached (`side`) but `reason` 'vote' (the M15 vote is not +1 for a buy / -1 for a sell), 'vote unknown' (no vote of the last closed M15 bar), 'brake', or (since v3.9.2-live.1) the entry was held before the send (`reason` = `open_hold.why`) |
| `OPEN_BUY` / `OPEN_SELL` / `OPEN_FAILED` | an entry was sent: filled / not filled (`reason` the retcode text) |
| `WAIT_FILL` | a leg filled, the terminal does not list it yet (up to 10 s; no add) |
| `HOLD` | in a trade: the stop not hit, no add due |
| `ADD_BUY` / `ADD_SELL` / `ADD_FAILED` | a pyramid add was sent |
| `CLOSE_BUY` / `CLOSE_SELL` | every leg closed at the stop (`reason` 'stop', 'close_retry': the legs an incomplete close left, or 'stop_passed_outside': a leg was closed outside the bot at or beyond the stop -- its broker backstop -- so the others are closed at once, whatever the price) |
| `BOTH_SIDES` | a buy and a sell of this bot are open: it holds still |
| `UNMANAGED` | positions of this bot it could not take over (they predate the D1 history): left alone |

| path | gate keys, in the bot's order |
|---|---|
| every poll | `terminal`, `account`, `positions`, `quote`, `d1_levels`, (`one_side`), (`trade_known`), `market_live` |
| flat | `armed` (today's orders not used), `exit_bar`, `breakout` (value: the side reached), `vote_known`, `vote`, `brake`, (`open_hold`) |
| in a trade | (`stop_passed`: a leg closed outside the bot at or beyond the stop, value its tickets; or `close_retry`), `stop` (exit: the bid of a long at or below it, the ask of a short at or above it), `fill_listed`, then the add gates `legs`, `add_bar` (not the entry's M1 bar), `add_price` (the ask of a long at or above the last fill + 0.5 N), (`open_hold`), (`adds_stopped`) |

### turtle
- `system` (1 / 2), `rules` (text), `params` {`system, n_len, stop_n, add_n, max_legs, tick, backstop_n, vote_tf,
  vote_bars, min_vote_bars, d1_bars, min_d1_bars, entry_days, failsafe_days, exit_days, pending_s, settle_s`}.
- `d1` {`bars` (closed D1 bars used), `asked`, `min_bars`, `enough`, `got_last_read`, `last_bar_t` / `_utc`,
  `next_close_t` / `_utc` (the next 00:00 UTC: new levels), `stale` (a minute after 00:00 UTC the terminal has not
  given the D1 bar that closed: the bot goes on with the levels and the stop of the bar before and asks again every
  poll)}; `n` (N of the last closed D1 bar).
- `levels` (what the last closed D1 bar sets, the bot's own numbers): `bar_time` (that bar) / `bar_utc`, `from_time` /
  `from_utc` (00:00 after it) .. `until_t` / `until_utc`, `system`, `n`, `n_pct` (N as % of the bid), `buy`, `sell`
  (the stop-entry levels), `stop_dist` (2N), `add_step` (0.5N), `trail_long` / `trail_short` (the exit channels),
  `use20` (System 1), `ok`. null without daily levels.
- `channels`: `entry` {`days` (55 System 2; System 1 20, or 55 on a failsafe day), `high`, `low`, `rule`}, `exit`
  {`days` (20 / 10), `long` (the low a long's stop is raised to), `short`, `rule`}, `all` {`10` / `20` / `55`: `high`,
  `high_t` / `_utc` (the day of the extreme), `low`, `low_t` / `_utc`}, `bar` {the last closed D1 bar: `t`, `o h l c`,
  `true_range`}.
- `filter` (System 1, else null): `use20`, `levels_from` ('20-day' / '55-day failsafe'), `hypothetical` {the filter's
  own one-unit System 1 on the D1 bars: `state` (flat / BUY / SELL), `entry`, `stop`, `exit_level_next`, `since_t` /
  `_utc`, `last_win`, `use20`, `trades` (its last five: side, entry / exit day and price, win)}, `rule`.
- `vote`: `tf` (M15), `value` (+1 / -1 / 0 of the last CLOSED bar, null when not known), `last`, `fresh`, `allows`
  (BUY / SELL / null), `bar_t` / `_utc` (that bar's open), `bar_close_t` / `_utc`, `next_read_t` / `_utc` (2 s after
  the next M15 close), `bars` (closed M15 bars used), `asked`, `min_bars`; `rsi` {`vote`, `pivot`, `pivot_side`,
  `bars_ago`, `slope`, `now`, `ob`, `os`, `series`} and `macd` {`vote`, `pivot`, `pivot_side`, `bars_ago`, `slope`,
  `now` (the histogram), `line`, `signal`, `side_rule` (the signal line picks high / low pivots), `series`,
  `signal_series`}: the series are the last 40 closed bars, times in `t`, closes in `close`; `rule`.
- `orders` (the day's stop-entry orders): `state` ('armed' / 'used' / 'none'), `armed`, `from_t` .. `until_t` (with
  `_utc`), `buy` / `sell` {`level`, `judged_on` (ask / bid), `price_now`, `distance` (to the level; <= 0 = reached),
  `distance_n` (in N), `reached`, `vote_needed`, `channel`}, `used_t` / `used_utc` / `used_by` (the entry that used
  them), `last_exit_t` / `_utc`, `in_exit_bar`, `rule`.
- `new_trade` (flat only): what an entry now would get, N frozen: `units`, `lots` (per leg), `n`, `stop_dist`,
  `add_step`, `max_legs`, `balance`, and `buy` / `sell` {`entry` (the level, or the quote beyond it), `at`, `stop`,
  `stop_origin`, `next_add`, `backstop`, `pnl_at_stop` (the first leg's P/L at the stop), `judged_on`}.
- `trade`: null when flat; else `side`, `units`, `lots_per_leg`, `lots`, `legs` [{`n`, `ticket`, `id`, `open_t` /
  `_utc`, `price`, `lots`, `profit`, `swap`, `backstop` (the leg's broker sl), `tp`, `magic`, `comment`, `listed`}],
  `legs_count`, `max_legs`, `full`, `n_entry`, `stop_dist`, `add_step`, `entry_t` / `_utc`, `age_s`, `entry_d1_t` /
  `_utc` (the D1 bar whose orders filled), `entry_level`, `avg_price`, `best_fill`, `pnl` (floating), `judged_on`,
  `price_now`, `stop` (the one stop of all legs), `stop_origin` ('2N' / 'channel' / 'kept') and `stop_text`,
  `stop_2n` (2N from the best fill), `stop_channel` (the tightest exit channel since the entry), `stop_floor` (kept
  after a leg closed outside), `exit_channel_now`, `to_stop`, `pnl_at_stop`, `next_add` (null when full),
  `next_add_judged_on`, `add_price_now`, `to_next_add`, `adds_left`, `backstop_prices`, `closing`, `closed_now` (this
  poll closed it), `pending_fill`, `known_to_bot`, `journal` (below). `{both_sides: true, ...}` when both sides are
  open; `known_to_bot: false` for positions it could not take over.
- `pending_fill`, `hold`, `closing`, `units_rule`, `book` (a copy of the bot's book, `turtle.py` state).

### the Turtle in `<SYMBOL>_bars.json` and `<SYMBOL>_trades.json`
- bars: all five timeframes from the terminal (`source` 'terminal'), plus `overlay.turtle` {`d1_t` (the D1 bar),
  `from_t` (the day its levels apply), `buy`, `sell`, `exit_long`, `exit_short`, `n`, (`use20`)}: the last 200 D1 bars'
  levels, to draw the channels as steps.
- trades: a trade = the legs of one side open together. A closed Turtle trade's `exit_reason` is `turtle_stop` (the
  bot's stop; `exit_detail` '2N' / 'channel' / 'kept', `exit_stop` the stop price, `exit_reason_text` e.g. 'turtle
  stop (2N from the best fill)'), `stop_passed_outside` (a leg closed outside the bot at or beyond the stop, the bot
  closed the rest), `backstop` (the broker closed it at a leg's sl), `closed_outside`, `stop_out`. Every
  trade has `turtle` (the journal): `side`, `units`, `lots`, `n_entry`, `stop_dist`, `add_step`, `entry_level`,
  `entry_d1_t` / `_utc`, `use20`, `vote`, `vote_bar_t`, `opened_t` / `_utc`, `balance`, `rebuilt` (taken over after a
  start without the state file), `legs` [{`id`, `t`, `price`, `level` (the add level it was taken at), `backstop`}],
  `stops` [{`t`, `utc`, `stop`, `origin`, `why`}: the entry's, every tightening], `exit` {`t`, `reason`, `stop`,
  `origin`, `price`, `decision_pnl`, (`legs_outside`)}. The open trade is the trace's `turtle.trade` (`live: true`).

### the Turtle's log lines
| level | category | lines |
|---|---|---|
| INFO | LEVELS | the levels of every new D1 bar (and the ones in force at the start): buy / sell and the channels they come from, N, 2N, 0.5N, the exit channels, System 1's filter, the orders' state; the orders marked used from the deal history |
| INFO / DEBUG | VOTE | a change of the M15 vote (INFO, with its RSI / MACD pivots and slopes), every new closed M15 bar (DEBUG); WARN: no vote |
| INFO | TRADE | an entry (fill, level, vote, unit, N, stop, next add, backstop), every add (fill, add level, next add) |
| WARN | TRADE | a trade taken over from the terminal (no state file), legs closed outside the bot (with `beyond_stop` from the deal history: at or beyond the stop, so the other legs are closed at once; or inside it, by hand, and the trade goes on), a trade replaced, both sides open |
| INFO | STOP | every stop move and why (2N from a new leg, the exit channel of a new D1 bar, kept after a leg closed outside); WARN if it ever loosened |
| CLOSE | CLOSE | the trade closed at the stop (where it came from, the price, the legs, the P/L at the decision), or ended after a leg closed outside the bot beyond the stop (`reason=stop_passed_outside`), or closed outside the bot; WARN: an incomplete close, or (since v3.9.2-demo.5) a close that closed nothing: the trade stays booked and the close is decided again next poll -- the next close says 'on the next try (the close at the stop ... of HH:MM had closed nothing)', or, when the legs are gone by then, 'the trade ended: ... had closed nothing, so they were closed outside the bot first' (`after_close_of=<exit>`) |
| INFO | RESULT | the realised P/L of a closed trade from the deal history and its exit (also, at a start, for a trade the journal knows that closed while the bot was down; never twice) |
| INFO / WARN | TURTLE | the bot's own notes (too few D1 / M15 bars, positions that predate the D1 history, the brake, an entry held before the send: 'Turtle entry held: ...'), at most every 5 min each; too few D1 bars after midnight, with the levels of the day before in force: 'the bot goes on with the levels and the stop of the D1 bar before and asks again every poll' (at a start, without levels: 'not trading'). A refused entry or add is no note since v3.9.2-live.1: it is a `BUY_REFUSED` / `SELL_REFUSED` / `BUY_MORE_REFUSED` / `SELL_MORE_REFUSED` line (WARN ORDER, §4) |
| INFO / WARN | DATA / MARKET / ACCOUNT | daily levels missing / back, the D1 bar of the day late (WARN) / there, the market live / not, the unit changing |
| DEBUG | STATE | the Turtle book saved (the book in the events file's `data`) |

## 6. Who reads them: `dashboard.py`

The dashboard reads these files and nothing else (no terminal call), every `DASHBOARD_REFRESH_INTERVAL`, and draws one
page for both strategies (it takes `strategy` from the trace; without a trace, `STRATEGY` of `constants.py`).
Since v3.9.2-live.1 it also reads the safety's files in the account folder for the bar at the top of every tab. It
writes nothing but a press of Unblock / OFF / ON, through `safety.press` (`docs/live-safety.md`; the switch, the
restart id, the audit line, the wrong-PIN count), and, once when it is started as a program, the PIN file when there
is none (`safety.ensure_pin`; its window then prints where the file is). It never opens `mt5_credentials.json`, and
no page holds the full account number: the chip and every text show `...1234`, and the raw views leave out every
key whose name holds `login` (the `..._tail` keys stay).

| tab | reads |
|---|---|
| status bar | `<SYMBOL>_trace.json`: `t` (its age: fresh under 15 s, slow under 60 s, stale after), `branch` and `magic` (the line under the symbol shows this branch's own `BRANCH` and `MAGIC` from `constants.py`; a trace of another branch or magic gets the red chip 'This trace is another bot's (...)'), `health`, `account`, `sizing` (the line under 'Unit · lot'), `safety.day.start_balance` (with `account.day_realised`: 'today +$12.40'), `market` (`tick_t`: the last tick's age now), `stale`; `<SYMBOL>_trades.json` `summary.net` ('Closed P/L (this bot)') and `state/live_start.json` `time` (its 'since'; else trades.json `live_start_t` / `since_t`); the ERROR lines of the last hour from the newest 3 MB of the events day files (the two with the newest dates: `logs/<SYMBOL>_<day>_events.jsonl`); from the same files a refused start (below) |
| Live | the trace's `decision` (headline, gates in order, `blocked_by`, this poll's `orders`) and `basket` / `turtle`; `<SYMBOL>_bars.json` (the forming bar moved with `market.bid`; `overlay.turtle` on D1); `<SYMBOL>_trades.json` `closed` for the chart's entries and exits; the newest 256 KB of the events day files |
| Trades | `<SYMBOL>_trades.json` (`t`, `summary`, `balance_curve`, `closed`, each trade's `turtle` journal) and the trace's open position |
| Log | the newest 3 MB of the events day files, the newest 512 KB of a day's `logs/<SYMBOL>_<day>.log` (download: the whole file); it says what is kept: today and the last `LOG_KEEP_DAYS` days |
| Changes & issues | the WARN and ERROR lines of the newest 3 MB of the events day files, grouped by kind (below), errors first; the branch's `CHANGELOG.md`, version by version |
| History & settings | `daily_trade/<SYMBOL>/*.json`, `daily_trade/<SYMBOL>/historical_summary.json`, `logs/<SYMBOL>_strategy_log.json`; the settings the bot started with: the newest `start` line of `journal/<SYMBOL>_<YYYY>.jsonl` (this year's file, else last year's) not later than 2 minutes after the running bot's start, else the CONFIG lines of the text log of its start day (kept for `LOG_KEEP_DAYS` days only), else `constants.py` as the dashboard read it at its start (a value `constants.py` has changed since is marked); the raw files (a fixed list: the trace, trades, `<SYMBOL>.json`, `account.json`, `state/<SYMBOL>_state.json`, the Turtle's book, `state/<SYMBOL>_turtle_side.json`, the Turtle's journal, the exit reasons, `state/safety_state.json`, `state/safety_closes.json`, `state/live_start.json`, the bars' header; no file of the account folder). Never shown: `OLD_LOGINS_SHA256` and any setting whose name holds `PIN`, `PASS` or `SECRET` |
| the safety bar (every tab) | the trace's `safety` (else this bot's status file, whichever is newer), and in the account folder the switch, the restart id, the block file of the current id, the wrong-PIN record, whether the PIN file holds a usable PIN, and the two bots' status files (`safety.read_controls`, `safety.read_statuses`) |

**The banners** (every tab, under the bar, most urgent first) come from the state the trace holds now, not from
events, so a condition that still holds still shows after the dashboard is started again:

| source | banner |
|---|---|
| this bot's status `account_dir` is not the folder the dashboard reads (while the bot runs) | red: 'This page and the bot use different account folders.' |
| `health.trading_not_allowed` | red, one per reason: '... the bot can neither open nor close.' |
| `health.account_ok` false and `health.login_tail` another account than `own_login_tail` | red: 'MetaTrader 5 was switched to account ...9876.' (with the bot's open trades, and 'Stop the old bot, then log ...' when `foreign.old_bot_same_terminal`) |
| `foreign.old_bot_same_terminal` (else) | red: 'An old bot is running on this server and uses the same MetaTrader 5.' |
| `foreign.positions` > 0 | red: "Trades that are not this bot's are open on ..." (with the examples) |
| `safety.partner.account_differs` | red: 'The two bots of account <n> are logged into different accounts ...' |
| `safety.partner.limits_differ` | red: 'The two bots of account <n> have different safety limits.' |
| `health.disk_low` | red: 'DISK_LOW: less than 2 GB is free on the disk of the server.' |
| `foreign.old_bot_age_s` below 120 (another MetaTrader 5) | amber: 'An old bot is running on this server (...), with another MetaTrader 5.' |
| `open_hold.why` 'refused_backoff' | amber: "The broker refuses this bot's new orders since HH:MM (N refusals). ..." (`open_hold.since`, `refusals`, `until`) |
| `<SYMBOL>_trades.json` `closed`: an exit reason closed_outside / stop_out / backstop / broker_target / leg_closed_outside / stop_passed_outside in the last 24 hours | amber: 'A trade of this bot was closed by something else.' |
| the issues list, for 24 hours: `STATE_OTHER_ACCOUNT` (only a line whose `kv.held_open_trade` is not false; the bot's own sentence), `OTHER_PROGRAM`, `CLOSE_RESULT_UNKNOWN` | red / amber / amber: '<CODE> (HH:MM). ...' |

`safety.error` is the bar's red `SAFETY CHECK FAILED`; a new block (or a failing check) also goes into the alert store
(the banner, the sound and the browser notification the owner ticked), and a block of the other bot as an amber
alert.

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

**A refused start** (since v3.9.2-demo.5): when the newest ERROR START line of the events files (all 3 start attempts
failed, a refused design or credentials file, a start only the owner can put right, the job failed) is newer than
the trace and than the last 'trading loop started' line, the bot is not running. The status bar (every tab) has a
red chip 'Not started: <kind> (HH:MM)' ('Stopped: ...' when the job ended) and a red box 'The bot is not running:
its start was refused': what the bot wrote, what it means and what to do (the README's section 6 has the same list
for the owner). Whether the window has stopped for good comes from the line itself: its `kv.exit_code` (78: it
does NOT start again by itself), else its `kv.needs_owner`, else the kind; for `TERMINAL_IN_USE`, `LOGIN_WAIT` and
`OLD_BOT_SAME_TERMINAL` the box says that the launcher tries again every 30 s and that the log has the line again
at most every 15 minutes.

**The issue kinds** (Changes & issues; `ISSUE_KINDS` in `dashboard.py` is the list, each with what it means and what
to do, the particular ones before the general ones). The line's own name counts first: its `kv.needs_owner` (a start
only the owner can put right: `OLD_ACCOUNT`, `SERVER_MISMATCH`, `ACCOUNT_KIND`, `ACCOUNT_CLAIM`, `CREDENTIALS_...` and
`TERMINAL_PATH_...` as `CREDENTIALS_FILE`, `SYMBOLS_...` as `SYMBOLS_FILE`, `WRONG_MODE`, `DESIGN_REFUSED`); then the
first kind whose pattern matches the event's name (`event` / `kv.event`) with the message, or the message alone. The
real-money layer's kinds: `OLD_ACCOUNT`, `SERVER_MISMATCH`, `ACCOUNT_CLAIM`, `WRONG_MODE`, `DESIGN_REFUSED`,
`LOGIN_REFUSED`, `LOGIN_WAIT`, `ACCOUNT_KIND`, `SYMBOLS_FILE`, `CREDENTIALS_FILE`, `TRADING_NOT_ALLOWED`,
`STATE_OTHER_ACCOUNT`, `OLD_BOT_SAME_TERMINAL`, `OLD_BOT_RUNNING`, `FOREIGN_POSITIONS`, `OTHER_PROGRAM`,
`SAFETY_ERROR`, `SAFETY_BLOCKED`, `SAFETY_SKIP`, `CLOSE_RESULT_UNKNOWN`, `TURTLE_ADDS_STOPPED`, `BUY_REFUSED`,
`SELL_REFUSED`, `BUY_MORE_REFUSED`, `SELL_MORE_REFUSED`, `DISK_LOW`; and those of before: `TERMINAL_IN_USE`,
`ACCOUNT_NOT_KNOWN` (no login: the account was not known), `BOT_LOGIN` (the bot logged in itself), `ACCOUNT_REFUSED`,
`RECONNECT_FAILED`, `MT5_INIT_FAILED`, `START_FAILED` (a start attempt or the job failed), `TERMINAL_ERROR`,
`POLL_FAILED`, `TRACE_FAILED`, `WRITE_FAILED`, `CLOSE_NOTHING` (a close that closed nothing), `CLOSE_INCOMPLETE`,
`CLOSED_OUTSIDE`, `D1_LATE`, `ORDER_REFUSED`; any other by its category and the shape of its message.
`LIVE_TERMINAL_PATH` is gone. The advice of `LOGIN_WAIT` follows the line's `kv.why` (no_password,
terminal_claimed, login_budget, claim_unreadable, budget_unreadable, budget_unwritable), that of
`TRADING_NOT_ALLOWED` its `kv.reasons`; a group shows the advice of its newest line. The advice names the README's
sections: section 2 "First start" (step 2 the old bots, step 4 MetaTrader 5 installed and logged in by hand, step 5
the credentials, step 7 the firewall, step 9 the PIN), section 3 the safety, section 5 the logs, section 6 the
warnings.

**An open basket's leg not listed yet**: the position card has the chip 'N leg(s) not listed yet', a line with each
leg (its kind, lots, price, how long ago it filled) and that the P/L, stop and target use the listed legs until the
terminal lists it; the legs table has its row, 'not listed yet'.

**trades.json missing or old**: missing or unreadable, the Trades tab, its chart, the position card and the
chart note say so (the closed trades are not known; never 'No trade yet'); older than 3 minutes (it is rewritten at
least every minute), the Trades tab shows when it was written and warns that its trades are as of then.

**The chart**: the candles are bid. A level the bot compares with the ask (a sell basket's stop / target / broker
stops, a buy basket's next add, the Turtle's buy level, a short's stop / broker stops, a long's next add) is tagged
'(ask)', and an ASK line is drawn next to the BID line. The Turtle's BUY / SELL LEVEL are entry triggers (blue,
dashed) only while `turtle.orders.state` is 'armed' and no trade is open; else they are drawn faint and dotted with
'used, new orders at 00:00' or 'no entry while in a trade' under the price (the orders panel then says 'BUY level
passed ...: no entry, ...' instead of 'needs the M15 vote'). A close in 'This poll's orders' reads 'CLOSE SELL
position 100001 (BUY order, 0.01 lot)'.
