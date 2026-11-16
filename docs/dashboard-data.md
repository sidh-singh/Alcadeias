# The dashboard's data: what the bot writes (schema 1: the basket strategy and the Turtle)

`tracelog.py` writes these files into the bot's output folder (`OUTPUT_DIR` in `constants.py`, here
`C:\Alcadeias\demo_hedging_btcusd7`). The bot never reads them back; nothing it decides depends on them. This branch
runs the Turtle (`STRATEGY = 'turtle'`, §5); the basket strategy's fields (§1) are those of the basket branches.

| file | what | when |
|---|---|---|
| `<SYMBOL>_trace.json` | the latest decision snapshot | after every poll (a poll takes at least 1 s), so every change of action, position or gate result is in it |
| `<SYMBOL>_bars.json` | bid OHLC bars for the chart | the first poll, then at most every 30 s while a bar moves or a new one starts |
| `<SYMBOL>_trades.json` | this bot's trades from the deal history | the first poll, after every fill and close (and on the poll after), at least every 60 s |
| `logs/<SYMBOL>_<YYYY-MM-DD>.log` | the text log, one line per event | as it happens; one file per UTC day, kept 30 days |
| `logs/<SYMBOL>_events.jsonl` | the same lines as JSON | as it happens; rotated at 10 MB into `_events.1.jsonl` (newest) .. `_events.5.jsonl` |
| `state/<SYMBOL>_exit_reasons.json` | the exit reason the bot recorded per position | at every close |
| `state/<SYMBOL>_turtle_trades.json` | the Turtle's journal per trade: N at the entry, the level, the vote, every leg with its add level, every stop move, the exit | at every entry, add, stop move and exit |

The old dashboard's files are written as before: `<SYMBOL>.json`, `account.json` (the basket loop; the Turtle's loop
has never written it -- its numbers are in `<SYMBOL>.json` and in the trace's `account`), `active_config.json`,
`logs/<SYMBOL>_strategy_log.json`, `daily_trade/<SYMBOL>/*.json`, `state/<SYMBOL>_state.json` (basket) /
`state/<SYMBOL>_turtle.json` (the Turtle's book).

**Reading them.** JSON files are replaced atomically (a temp file, then a rename): a reader sees the old file or the
new one, never half of one. They are compact (no indentation). A file can be missing (the bot has not run yet, or a
write failed); every field can be `null`. Check `schema` (1). Times are UTC epoch seconds in `t` / `..._t` fields,
with an ISO copy in `..._utc` fields (`2026-11-17T08:00:01.500Z`). Money is USD of the account; prices are bid / ask
as the terminal quotes them, rounded to the symbol's `digits` where the bot computed them.

## 1. `<SYMBOL>_trace.json`

```
schema, branch, design, strategy ('basket' | 'turtle'), symbol, mt5_symbol, magic, t, time_utc, poll (count since
start), stale (true: this poll could not read the terminal; account / market / basket / turtle are the last good
poll's), stale_since_utc, health, account, market, decision, basket (null on the Turtle), turtle (null on the basket)
```

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
`virtual` (units from the virtual balance), `virtual_balance`, `virtual_start_balance`, `virtual_start_date`,
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

**orders**: `{t, kind (open / add / close), side, symbol, volume, price, sl, tp, position, magic, comment, refused,
retcode, retcode_text, done, result_price, result_volume, order, deal, result_comment, last_error, ms}`.

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
  `closed_now` (this poll closes it), `listed` / `opened_now` (just opened).

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

| level | lines |
|---|---|
| DEBUG | DECISION (every change of the action or of a checked gate, with all the gates), STATE (state saved), BASKET (a position listed, the ladder armed), SIGNAL |
| INFO | START, CONFIG (every effective constant, symbols.json, the contract size), STATE, ACCOUNT (logged in, or no login when the terminal already holds this bot's account; the checks passed), TERMINAL (connected again, after how long and how many failed attempts), BASKET (opened, added), PAUSE (start, end), MARKET, WINDOW, DATA, HEARTBEAT (every minute) |
| ORDER | every order request and its result (retcode, comment, price, sl, tp) |
| FILL | an entry or add filled |
| CLOSE | a basket closed, with the reason and the P/L (also one closed outside the bot; after a leg closed outside the bot, the close of the rest and the booking of the whole basket) |
| WARN | an order not filled, a terminal read error, missing bars, a file that could not be written, a slow poll, BASKET: legs of the basket closed outside the bot, TERMINAL: every failed reconnect attempt that the strategy log leaves out (it has RECONNECT_FAILED only when the problem starts or changes, then every 15 min) |
| ERROR | an exception (with its traceback), the account refused (also by the account read again right after the positions), TERMINAL_IN_USE (the terminal holds another account: no login, the terminal is left as it is; once, then every 15 min), a reconnect that failed (as in the strategy log) |

A HEARTBEAT line comes every minute: a gap of more than a minute means the bot was not running. The same
exception at the same place is written again at most every 10 minutes, with the count of the repeats. Past 50 MB
in a day the day's file takes only WARN and ERROR lines (the events file keeps every line).

`logs/<SYMBOL>_events.jsonl`: one JSON object per line: `{t, time, level, cat, msg, kv, data, traceback}`;
`data` holds the full gate list of a DECISION line, the state of a STATE line.

## 5. The Turtle (`STRATEGY = 'turtle'`; this branch)

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
| `BLOCKED` | a level is reached (`side`) but `reason` 'vote' (the M15 vote is not +1 for a buy / -1 for a sell), 'vote unknown' (no vote of the last closed M15 bar), 'brake' |
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
| flat | `armed` (today's orders not used), `exit_bar`, `breakout` (value: the side reached), `vote_known`, `vote`, `brake` |
| in a trade | (`stop_passed`: a leg closed outside the bot at or beyond the stop, value its tickets; or `close_retry`), `stop` (exit: the bid of a long at or below it, the ask of a short at or above it), `fill_listed`, then the add gates `legs`, `add_bar` (not the entry's M1 bar), `add_price` (the ask of a long at or above the last fill + 0.5 N) |

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
| CLOSE | CLOSE | the trade closed at the stop (where it came from, the price, the legs, the P/L at the decision), or ended after a leg closed outside the bot beyond the stop (`reason=stop_passed_outside`), or closed outside the bot; WARN: an incomplete close |
| INFO | RESULT | the realised P/L of a closed trade from the deal history, its exit, the virtual balance after it (also, at a start, for a trade the journal knows that closed while the bot was down; never twice) |
| INFO / WARN | TURTLE | the bot's own notes (too few D1 / M15 bars, a refused order, the brake), at most every 5 min each |
| INFO / WARN | DATA / MARKET / ACCOUNT | daily levels missing / back, the D1 bar of the day late (WARN) / there, the market live / not, the unit changing |
| DEBUG | STATE | the Turtle book saved (the book in the events file's `data`) |

## 6. Who reads them: `dashboard.py`

The dashboard reads these files and nothing else (no terminal call), every `DASHBOARD_REFRESH_INTERVAL`, and draws one
page for both strategies (it takes `strategy` from the trace; without a trace, `STRATEGY` of `constants.py`).

| tab | reads |
|---|---|
| status bar | `<SYMBOL>_trace.json`: `t` (its age: fresh under 15 s, slow under 60 s, stale after), `health`, `account`, `market`, `stale` |
| Live | the trace's `decision` (headline, gates in order, `blocked_by`, this poll's `orders`) and `basket` / `turtle`; `<SYMBOL>_bars.json` (the forming bar moved with `market.bid`; `overlay.turtle` on D1); `<SYMBOL>_trades.json` `closed` for the chart's entries and exits; the newest 256 KB of `logs/<SYMBOL>_events.jsonl` |
| Trades | `<SYMBOL>_trades.json` (`summary`, `balance_curve`, `closed`, each trade's `turtle` journal) and the trace's open position |
| Log | the newest 3 MB of `logs/<SYMBOL>_events.jsonl`, the newest 512 KB of a day's `logs/<SYMBOL>_<day>.log` (download: the whole file) |
| History & settings | `daily_trade/<SYMBOL>/*.json`, `historical_summary.json`, `logs/<SYMBOL>_strategy_log.json`, the CONFIG lines of the bot's start (the text log of `health.started_utc`'s day; `constants.py` when they are not there), the raw files |

A file that is missing, cut in the middle or of an unexpected shape shows as such (an empty state, or a card with the
error and its traceback); the rest of the page is unaffected. The charts take times as UTC wall-clock text (a number
would be shown in the browser's own time zone).
