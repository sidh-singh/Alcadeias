"""
tracelog.py -- what the bot sees, decides and does: the dashboard's data, a detailed text log and the permanent
journal. (Real-money branches: the basket strategy and the Turtle. Data contract schema 1; docs/dashboard-data.md
has every field.)

Every file is in the bot's output folder (OUTPUT_DIR, or MT5TradingBot.trace_dir). JSON is compact, written
atomically (a temp file, then os.replace), times are UTC epoch seconds ("t", "..._t") with an ISO copy
("..._utc"). The files the old dashboard reads (<SYMBOL>.json, account.json, logs/<SYMBOL>_strategy_log.json,
daily_trade/...) are written as before, by app.py. The account is a real one: its number leaves this module only
as its last four digits ('...1234').

  <SYMBOL>_trace.json   the latest decision snapshot, after every poll (a poll takes >= 1 s, so every change of
                        action, position or gate result is in it): branch, mode, version, health, account,
                        sizing, safety, open_hold, foreign, market, decision (action, a plain-English headline,
                        the gates in the order the bot checks them, this poll's orders), basket (votes, scores,
                        trend, volatility unit, the levels a new basket would get, the pause, the open basket
                        with its stop / target / backstop prices) or turtle (N, the D1 channels, today's buy /
                        sell levels and their orders, the System 1 filter, the M15 vote of closed bars and its
                        parts, what a new trade would get, the open trade with its legs, stop, next add and
                        backstops); the other one null.
  <SYMBOL>_bars.json    bid OHLC for the chart: M1 360, M5 300, M15 300, H1 300, D1 200 bars (the last one is
                        forming), rewritten at most every 30 s and only when a bar moved or a new one started.
                        Basket: M1/M5/M15/H1 come from the bars the poll has already fetched; D1 costs one terminal
                        call. Turtle: all five from the terminal, plus the daily levels per D1 bar (overlay).
  <SYMBOL>_trades.json  this bot's trades from the deal history (its MAGIC, since its live start:
                        state/live_start.json, written by app.py; the read begins a day before it): every closed
                        basket / Turtle trade (legs, open / close, lots, P/L in dollars, the exit reason the bot
                        recorded; a Turtle trade also its N, entry level and stop history), the open one with its
                        live levels, the running total of its own closed P/L (from 0), its deepest fall and a
                        summary. Real numbers only. Read after every fill and close (and once more on the next
                        poll), and every 60 s.
  logs/<SYMBOL>_<YYYY-MM-DD>.log   the text log, one file per UTC day; one line per event:
                        'YYYY-MM-DD HH:MM:SS.mmm UTC | LEVEL | CATEGORY | message | key=value ...'
                        (split(' | ', 4) gives the five fields; the message never holds ' | '); an ERROR from an
                        exception is followed by its traceback, each line indented by 4 spaces. Levels: DEBUG
                        (every decision change), INFO, ORDER, FILL, CLOSE, WARN, ERROR. A HEARTBEAT line every
                        minute with the key numbers: a gap of more than a minute means the bot was not running.
  logs/<SYMBOL>_<YYYY-MM-DD>_events.jsonl    the same lines as JSON ({t, time, level, cat, msg, kv, data,
                        traceback}), one file per UTC day.
  logs/<SYMBOL>_<YYYY-MM-DD>_samples.jsonl   one line of figures a minute (the quote and its spread, the ticks,
                        the account, the positions, the safety meters, the poll times), also from skipped polls.
                        These three are the day files: today and the LOG_KEEP_DAYS (7) UTC days before it are
                        kept, by the date in the name. Past 50 MB in a day the text log and the events file take
                        only WARN / ERROR lines, past 100 MB one 'N lines dropped' line a minute; all day files of
                        the bot together stay under 500 MB (older days go first); with less than 2 GB free on the
                        disk DEBUG / INFO lines and the samples are dropped.
  journal/<SYMBOL>_<YYYY>.jsonl    the permanent journal, never deleted: one JSON line per start (the whole
                        configuration), order (request, quote, result, slippage), closed trade (once, also
                        across restarts), safety event, order the safety held back, UTC day and problem (when it
                        starts, changes and ends). Bounded: a line that repeats is written 3 times, then once a
                        minute with the count; 5 MB a UTC day.
  state/<SYMBOL>_journal_state.json   which closed trades the journal already holds, the open trade's entry
                        facts and its highest / lowest floating P/L, the problems that last, the running day.
  state/<SYMBOL>_exit_reasons.json the exit reason the bot recorded per position id (feeds trades.json).
  state/<SYMBOL>_turtle_trades.json the Turtle's journal per trade: N at the entry, the level, the vote, every leg
                        with its add level, every stop move and the exit (feeds trades.json).

What this module may do -- the trading must never notice it:
  * it reads what the poll has already computed (app.py hands it the poll's locals at the end of the poll, by
    name: a name that is not there reads as None and its field stays empty); the only terminal calls it makes are
    the deal history after a fill / close and every 60 s, the bars at most every 30 s (basket: D1 only), and the
    symbol's facts once (symbol_info), each under the bot's mt5_lock; the Turtle's RSI / MACD lines for the chart
    are computed again from the poll's closed M15 bars once per bar;
  * no file is read or written while the bot holds mt5_lock: order(), journal() and an event logged in there only
    queue their lines, which the next write outside the lock stores (one batch: text log, events, journal,
    samples);
  * every entry point catches every Exception, logs it (ERROR with the traceback, repeats at most every 10 min)
    and returns; a write that fails is a WARN, the next poll tries again;
  * its own time per poll is measured (health.trace_ms; a millisecond or two).
"""
import enum
import functools
import hashlib
import json
import math
import numbers
import os
import re
import shutil
import sys
import threading
import time
import traceback
from bisect import bisect_right
from collections import deque
from datetime import datetime, timezone

import numpy as np

SCHEMA = 1

TRACE_MIN_INTERVAL_S = 1.0       # the trace is rewritten at most this often, unless the decision changed
BARS_MIN_INTERVAL_S = 30.0       # the bars file at most this often
BARS_SPEC = (('M1', 360), ('M5', 300), ('M15', 300), ('H1', 300), ('D1', 200))
TRADES_INTERVAL_S = 60.0         # the deal history is read at least this often (and after every fill / close)
TRADES_RETRY_S = 5.0             # ... and not more often than this while the terminal gives no history
TRADES_MAX_CLOSED = 2000         # the newest closed baskets kept in trades.json
TRADES_LOOKBACK_S = 90 * 86400   # while state/live_start.json is not there: the history read goes back this far
LIVE_START_MARGIN_S = 86400.0    # the trades read begins this long before the bot's live start
HEARTBEAT_S = 60.0
# ── the day files of logs/ (the text log, the events, the samples) ──
LOG_KEEP_DAYS = 7                    # today and this many UTC days before it are kept (constants.py LOG_KEEP_DAYS)
LOG_DAY_CAP_BYTES = 50 * 2 ** 20     # past this in a UTC day the text log / the events file take only WARN / ERROR lines
LOG_DAY_STOP_BYTES = 100 * 2 ** 20   # ... and past this nothing but one 'N lines dropped' line a minute
LOG_MAX_BYTES = 500 * 2 ** 20        # every day file of this bot together, today's counted: older days go first
DISK_LOW_BYTES = 2 * 2 ** 30         # less free space than this: DEBUG / INFO lines and the samples are dropped
DISK_CHECK_S = 60.0                  # the free space is asked for at most this often
TIDY_EVERY_S = 3600.0                # old day files, old temp files and old daily files go at the start, at every new
                                     # UTC day and this often
TEMP_SWEEP_AGE_S = 86400.0           # a temp file of one of the bot's own files, left by a killed process, goes after this
DAILY_TRADE_KEEP = 400               # daily_trade/<SYMBOL>/: the newest day files kept (the History tab reads them)
SAMPLE_S = 60.0                      # one line of figures per this long in logs/<SYMBOL>_<day>_samples.jsonl
# ── the permanent journal ──
JOURNAL_DAY_BYTES = 5 * 2 ** 20      # the budget of a UTC day; past it one 'journal_suppressed' line an hour
JOURNAL_SHARE = {'start': 0.5, 'issue': 0.5, 'trade': 2.0, 'day': 2.0}   # the part of the budget a kind may fill
                                     # (others: 1): a restart loop cannot push out the orders, and a closed trade or
                                     # a day's line -- real money, one line each -- is the last thing to be left out
JOURNAL_NOTE_S = 3600.0
JOURNAL_REPEAT_FIRST = 3             # the same line is written this many times in a row ...
JOURNAL_REPEAT_S = 60.0              # ... then once per this long, with the count of those left out
JOURNAL_RUN_GAP_S = 600.0            # 'in a row' ends when the line has not come for this long
JOURNAL_KEEP_IDS = 1000              # the newest closed trades the journal's state remembers by id
JOURNAL_TRADES_PER_READ = 200        # at most this many trade lines per read of the deal history
JOURNAL_SAVE_S = 30.0                # the open trade's extremes are saved at most this often
JOURNAL_DAY_SAVE_S = 300.0           # ... and the running day's figures alone this often
JOURNAL_AFTER_WAIT_S = 120.0         # a closed trade's line waits this long for the first poll after its close
# without a state file: a trade that closed this long before the oldest journal line read has its line already
JOURNAL_TAIL_MARGIN_S = 2 * JOURNAL_AFTER_WAIT_S + TRADES_INTERVAL_S
ISSUE_REPEAT_S = 900.0               # a problem that lasts is written again at most this often
ISSUE_END_AFTER_S = 60.0             # ... and counts as over when it has not shown for this long
EXIT_REASONS_KEEP = 5000
REPEAT_EVERY_S = 600.0           # the same error / warning is written again at most this often (with a count)
SLOW_POLL_MS = 5000.0            # a poll slower than this is a WARN
LEVELS = ('DEBUG', 'INFO', 'ORDER', 'FILL', 'CLOSE', 'WARN', 'ERROR')
# Never logged, never journalled (the CONFIG lines, the journal's start line): the old accounts' fingerprints, and
# any constant whose name holds one of these words.
HIDDEN_CONSTANTS = ('OLD_LOGINS_SHA256',)
HIDDEN_NAME_PARTS = ('PIN', 'PASS', 'SECRET')

ACTIONS = ('SKIPPED', 'NO_DATA', 'MARKET_CLOSED', 'WAIT', 'PAUSED', 'BLOCKED', 'OPEN_BUY', 'OPEN_SELL', 'OPEN_FAILED',
           'WAIT_FILL', 'HOLD', 'ADD_BUY', 'ADD_SELL', 'ADD_FAILED', 'CLOSE_BUY', 'CLOSE_SELL', 'BOTH_SIDES',
           'UNMANAGED', 'TRACE_ERROR')
TURTLE_JOURNAL_KEEP = 500        # the newest Turtle trades kept in state/<SYMBOL>_turtle_trades.json
VOTE_SERIES_N = 40               # the Turtle's M15 RSI / MACD lines in the trace: the last 40 closed bars

RETCODES = {
    10004: 'requote', 10006: 'rejected', 10007: 'canceled', 10008: 'placed', 10009: 'done', 10010: 'done partially',
    10011: 'error', 10012: 'timeout', 10013: 'invalid request', 10014: 'invalid volume', 10015: 'invalid price',
    10016: 'invalid stops', 10017: 'trade disabled', 10018: 'market closed', 10019: 'no money',
    10020: 'price changed', 10021: 'off quotes', 10022: 'invalid expiration', 10023: 'order state changed',
    10024: 'too many requests', 10025: 'no changes', 10026: 'autotrading disabled by the server',
    10027: 'autotrading disabled in the terminal', 10028: 'locked', 10029: 'frozen', 10030: 'invalid filling mode',
    10031: 'no connection', 10032: 'only real accounts', 10033: 'pending orders limit', 10034: 'volume limit',
    10035: 'invalid order', 10036: 'position already closed', 10038: 'invalid close volume',
    10039: 'close order exists', 10040: 'positions limit', 10041: 'cancel rejected', 10042: 'long only',
    10043: 'short only', 10044: 'close only', 10045: 'FIFO close only',
}
DEAL_REASONS = {0: 'client', 1: 'mobile', 2: 'web', 3: 'expert', 4: 'sl', 5: 'tp', 6: 'stop_out', 7: 'rollover',
                8: 'vmargin', 9: 'split'}
EXIT_TEXT = {
    'target': 'target', 'stop': 'stop', 'force_close': 'force-close', 'backstop': 'backstop (broker stop)',
    'broker_target': 'broker target', 'stop_out': 'stop-out', 'closed_outside': 'closed outside the bot',
    'close_retry': 'close (retry)', 'unknown': 'closed by the bot (reason not recorded)',
    'turtle_stop': 'turtle stop',
    'leg_closed_outside': 'a leg closed outside the bot, the rest closed by the bot',
    'stop_passed_outside': 'the stop passed outside the bot (a leg closed beyond it), the rest closed by the bot',
}
# where the Turtle's one stop is (turtle.stop_origin): {origin: words} ({days} = the exit channel's length)
STOP_ORIGIN_TEXT = {'2N': '2N from the best fill', 'channel': 'the {days}-day {extreme}',
                    'kept': 'kept where it was when a leg was closed outside the bot'}
_BOT_REASON = {'target': 'target', 'stop_loss': 'stop', 'force_close': 'force_close', 'close_retry': 'close_retry',
               'closed_outside': 'closed_outside', 'leg_closed_outside': 'leg_closed_outside'}
_TF = 'TIMEFRAME_'
_DONE = (10009, 10010)


# ───────────────────────────── small helpers ─────────────────────────────

def _f(x, nd=None):
    """x as a finite float (rounded to nd decimals), else None."""
    if x is None or isinstance(x, (str, bytes)):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd) if nd is not None else v


def _i(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _sign(x):
    return x if x in (-1, 0, 1) else 0


def _epoch(x):
    """A time (epoch seconds, datetime, pandas Timestamp, numpy datetime64) as epoch seconds, else None."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, numbers.Real):
        return _f(x)
    if isinstance(x, np.datetime64):
        return _f(x.astype('datetime64[ms]').astype(np.int64) / 1000.0)
    if isinstance(x, datetime):
        try:
            return (x if x.tzinfo is not None else x.replace(tzinfo=timezone.utc)).timestamp()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _iso(ts):
    """Epoch seconds -> '2026-11-17T08:00:01.500Z' (None stays None)."""
    t = _f(ts)
    if t is None:
        return None
    try:
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return dt.strftime('%Y-%m-%dT%H:%M:%S.') + f'{dt.microsecond // 1000:03d}Z'


def _stamp(t):
    """Epoch seconds -> '2026-11-17 08:00:01.500 UTC' (the time of a log line)."""
    dt = datetime.fromtimestamp(float(t), tz=timezone.utc)
    return dt.strftime('%Y-%m-%d %H:%M:%S.') + f'{dt.microsecond // 1000:03d} UTC'


def _hm(t):
    t = _f(t)
    return 'n/a' if t is None else datetime.fromtimestamp(t, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def _day(t):
    return datetime.fromtimestamp(float(t), tz=timezone.utc).strftime('%Y-%m-%d')


def _date(t):
    """'2026-11-17' (a D1 bar's day), 'n/a' for None."""
    t = _f(t)
    return 'n/a' if t is None else _day(t)


def _clock(t):
    """'09:15 UTC' (an M15 bar's time of day), 'n/a' for None."""
    t = _f(t)
    return 'n/a' if t is None else datetime.fromtimestamp(t, tz=timezone.utc).strftime('%H:%M UTC')


def _usd(x, signed=True):
    v = _f(x)
    if v is None:
        return 'n/a'
    body = f'${abs(v):,.2f}'
    if signed:
        return ('-' if v < 0 else '+') + body
    return ('-' if v < 0 else '') + body


def _px(x, digits=None):
    v = _f(x)
    if v is None:
        return 'n/a'
    return f'{v:,.{2 if digits is None else max(0, int(digits))}f}'


def _num(x, nd=2):
    v = _f(x)
    return 'n/a' if v is None else f'{v:,.{nd}f}'


def _sc(x):
    """A score: '+2', '-1', '0'."""
    v = _f(x)
    if v is None:
        return 'n/a'
    return f'{v:+g}' if v else '0'


def _dur(s):
    v = _f(s)
    if v is None:
        return 'n/a'
    v = abs(v)
    if v < 90:
        return f'{v:.0f} s'
    if v < 5400:
        return f'{v / 60:.1f} min'
    if v < 172800:
        return f'{v / 3600:.1f} h'
    return f'{v / 86400:.1f} days'


def _tf_key(tf):
    if tf is None:
        return None
    s = str(tf).strip().upper()
    return s[len(_TF):] if s.startswith(_TF) else s


def _sig_name(sig):
    if sig is None:
        return None
    return getattr(sig, 'name', None) or str(sig)


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, enum.Enum):
        return o.name
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, (set, frozenset, tuple, deque)):
        return list(o)
    return str(o)


def _clean(o):
    """o with every non-finite float replaced by None (JSON has no NaN / Infinity)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.floating):
        v = float(o)
        return v if math.isfinite(v) else None
    return o


def dumps(obj):
    """Compact JSON; a NaN / Infinity anywhere becomes null."""
    try:
        return json.dumps(obj, separators=(',', ':'), default=_json_default, allow_nan=False, ensure_ascii=False)
    except ValueError:
        return json.dumps(_clean(obj), separators=(',', ':'), default=_json_default, allow_nan=False,
                          ensure_ascii=False)


def err_text(e):
    """An exception for the log: its type and its message ('UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe4
    in position 60: invalid continuation byte'). Never repr(e): the repr of a decode error holds every byte it was
    decoding (a whole credentials file)."""
    if not isinstance(e, BaseException):
        return str(e)
    try:
        return f'{type(e).__name__}: {e}'
    except Exception:
        return type(e).__name__


REPLACE_WAITS_S = (0.005, 0.01, 0.02, 0.04, 0.06, 0.1)     # about 0.24 s in all


def replace_retry(src, dst, waits=REPLACE_WAITS_S):
    """os.replace(src, dst), tried again while Windows refuses it (PermissionError: a reader such as the dashboard has
    dst open this moment): up to len(waits) more times, about 0.24 s in all. Raises the last error."""
    for wait in tuple(waits) + (None,):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)


def write_json_atomic(path, obj, retries=None, text=None):
    """Write obj as JSON to path: a temp file next to it, then os.replace (a reader sees the old file or the new
    one, never half of one), tried again for about 0.24 s while Windows refuses it. text: obj already as JSON (the
    caller made it). Returns the bytes written; raises OSError (the caller logs it)."""
    data = dumps(obj) if text is None else text
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(data)
        replace_retry(tmp, path, REPLACE_WAITS_S if retries is None else REPLACE_WAITS_S[:max(0, retries - 1)])
        return len(data)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return len(data)


_PLAIN = re.compile(r'^[^\s"\'|]+$')


def kv_text(v):
    """A key=value value: numbers and plain words as they are, other text quoted, lists / dicts as JSON."""
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, numbers.Integral):
        return str(int(v))
    if isinstance(v, numbers.Real):
        f = float(v)
        return f'{f:.10g}' if math.isfinite(f) else 'null'
    if isinstance(v, str):
        return v if (v and _PLAIN.match(v)) else json.dumps(v, ensure_ascii=False)
    try:
        return dumps(v)
    except (TypeError, ValueError):
        return json.dumps(str(v), ensure_ascii=False)


def _clean_msg(s):
    return str(s).replace('\r', ' ').replace('\n', ' / ').replace(' | ', ' ; ')


def format_line(t, level, cat, msg, kv=None, tb=None):
    """One text-log line (and the indented traceback lines after it)."""
    line = f'{_stamp(t)} | {level} | {cat} | {_clean_msg(msg)}'
    if kv:
        line += ' | ' + ' '.join(f'{k}={kv_text(v)}' for k, v in kv.items())
    out = line + '\n'
    if tb:
        out += ''.join('    ' + ln + '\n' for ln in str(tb).rstrip('\n').splitlines())
    return out


def _event_dict(rec):
    t, level, cat, msg, kv, data, tb = rec
    d = {'t': round(float(t), 3), 'time': _stamp(t), 'level': level, 'cat': cat, 'msg': _clean_msg(msg)}
    if kv:
        d['kv'] = kv
    if data:
        d['data'] = data
    if tb:
        d['traceback'] = tb
    return d


def _text_line(rec):
    """One line of the text log (and its traceback lines) from a record (t, level, cat, msg, kv, data, tb)."""
    return format_line(rec[0], rec[1], rec[2], rec[3], rec[4], rec[6])


def _event_line(rec):
    """One line of the events file. A record whose values cannot be written as JSON keeps its time, level and
    message: one bad value must not hold back every line behind it."""
    try:
        return dumps(_event_dict(rec)) + '\n'
    except Exception as e:
        t, level, cat, msg = rec[0], rec[1], rec[2], rec[3]
        return dumps({'t': round(float(t), 3), 'time': _stamp(t), 'level': level, 'cat': cat, 'msg': _clean_msg(msg),
                      'kv': {'values_not_written': err_text(e)}}) + '\n'


def _utc_dt(ts):
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def hidden_constant(name):
    """True for a constant that is never logged and never journalled: the old accounts' fingerprints
    (OLD_LOGINS_SHA256), and any name that holds PIN, PASS or SECRET."""
    n = str(name).upper()
    return n in HIDDEN_CONSTANTS or any(part in n for part in HIDDEN_NAME_PARTS)


# ── the account number: its last four digits only ──

def _login_tail(login):
    """'...1234', the only form of an account number this module writes (safety.mask_login's rule)."""
    n = _i(login)
    return '...?' if n is None or n < 0 else '...' + str(n)[-4:]


def _login_sha(login):
    """What a state file stores to recognise the account without holding its number (safety.login_sha's rule):
    SHA-256 of the number as text; None without a number."""
    n = _i(login)
    if n is None or n < 0:
        return None
    return hashlib.sha256(str(n).encode('ascii')).hexdigest()


def _masked(obj, login, tail, depth=0, max_depth=4, _path=None):
    """A copy of obj (its dicts and lists, `max_depth` levels deep) with the account number `login` (a whole number
    of five or more digits) replaced by `tail` wherever it stands on its own: in a text, as a number. What the bot
    hands over already carries tails; this is the last net before a file. login None: the copy alone. A dict or
    list that holds itself is not walked again where it comes again (left as it is: JSON cannot hold it, and the
    writer says so), so no walk can run away."""
    if obj is None or isinstance(obj, bool):
        return obj
    if login is not None:
        if isinstance(obj, numbers.Integral):
            return tail if int(obj) == login else obj
        if isinstance(obj, str):
            digits = str(login)
            if digits not in obj:
                return obj
            return re.sub(r'(?<!\d)' + digits + r'(?!\d)', tail, obj)
    if depth < max_depth and isinstance(obj, (dict, list, tuple)):
        path = set() if _path is None else _path
        if id(obj) in path:
            return obj
        path.add(id(obj))
        try:
            if isinstance(obj, dict):
                return {k: _masked(v, login, tail, depth + 1, max_depth, path) for k, v in obj.items()}
            return [_masked(v, login, tail, depth + 1, max_depth, path) for v in obj]
        finally:
            path.discard(id(obj))
    return obj


def _problem_key(text):
    """A problem's text without the terminal's last_error, which can differ from one poll to the next (as app.py's
    _why_key): whether a problem that lasts is still the same one."""
    if not text:
        return None
    s = str(text)
    for sep in (' (last_error ', ': ('):
        i = s.find(sep)
        if i >= 0:
            s = s[:i]
    return s[:200]


_DAILY_NAME = re.compile(r'^(\d{2})_([a-z]{3})_(\d{4})\.json$', re.IGNORECASE)
_MONTHS = {m: k + 1 for k, m in enumerate(('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct',
                                           'nov', 'dec'))}
_TMP_MIDDLE = re.compile(r'^(?:\.\d+(?:\.[0-9a-fA-F]+)?)?$')       # '', '.<digits>' or '.<digits>.<hex>'
_LINE_T = re.compile(rb'^\{"t":(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?),')    # the time a journal line begins with


def _daily_date(name):
    """The day of a daily_trade file name ('17_nov_2026.json' -> (2026, 11, 17)); None for any other name."""
    m = _DAILY_NAME.match(name)
    if not m:
        return None
    month = _MONTHS.get(m.group(2).lower())
    day = int(m.group(1))
    if month is None or not 1 <= day <= 31:
        return None
    return int(m.group(3)), month, day


def temp_file_of(name, own_names):
    """True when `name` is a temp file of one of the files `own_names`: '<file>.tmp', '<file>.<digits>.tmp' or
    '<file>.<digits>.<hex>.tmp' (the forms this bot's writers use). Nothing else is ever swept."""
    if not name.endswith('.tmp'):
        return False
    body = name[:-4]
    for base in own_names:
        if body.startswith(base) and _TMP_MIDDLE.match(body[len(base):]):
            return True
    return False


# ── terminal objects (the same rules as app.py) ──

def _pos_time(p):
    msc = getattr(p, 'time_msc', None)
    return msc / 1000.0 if msc else _f(getattr(p, 'time', None))


def _pos_id(p):
    ident = getattr(p, 'identifier', None)
    return int(ident) if ident else _i(getattr(p, 'ticket', None))


def _deal_t(d):
    msc = getattr(d, 'time_msc', None)
    return msc / 1000.0 if msc else float(getattr(d, 'time', 0) or 0)


def _deal_net(d):
    return sum(float(getattr(d, k, 0.0) or 0.0) for k in ('profit', 'swap', 'commission', 'fee'))


def _deal_entry(d):
    """'in' (DEAL_ENTRY_IN 0), 'out' (DEAL_ENTRY_OUT 1 / OUT_BY 3), 'inout' (2) or None."""
    e = getattr(d, 'entry', None)
    if e in (0, 'in'):
        return 'in'
    if e in (1, 3, 'out'):
        return 'out'
    if e == 2:
        return 'inout'
    return None


def _frame_times(frame, n):
    """The bar times (epoch seconds) of the last n rows of a rates DataFrame."""
    try:
        return frame['time'].values[-n:].astype('datetime64[s]').astype(np.int64).tolist()
    except Exception:
        return None


# ───────────────────────────── the log files ─────────────────────────────

class LogWriter:
    """The files that grow: the three day files of logs/ -- the text log, the events (the same lines as JSON) and
    the samples (one line of figures a minute) -- and the permanent journal (journal/<SYMBOL>_<YYYY>.jsonl).
    A batch is appended with one open / write / close per file, so nothing stays open (a reader, a deletion or a
    full disk never meets a handle of the bot). Never raises: lines a failed write could not store are kept (the
    newest 2000 of each file) and written with the next batch.

    What bounds them:
      * the day files: today and `keep_days` UTC days before it are kept. A file is deleted only when its name is
        one of this symbol's three day patterns, by the date in its name (never by its age on the disk), oldest
        first: at the first write, at every new UTC day and once an hour. Nothing else in the folder is touched
        (the strategy log, another symbol's files);
      * past `day_cap` bytes in a UTC day the text log and the events file take only WARN and ERROR lines; past
        `day_stop` nothing but one 'N lines dropped' line a minute;
      * all day files together stay under `max_bytes`, today's counted: one pass, oldest first, never today's; a
        file that cannot be deleted is skipped;
      * with less than `disk_low_bytes` free on the disk (asked once a minute) DEBUG and INFO lines and the
        samples are dropped (disk_low: the trace says so);
      * the journal is never deleted. A UTC day's lines stop at `journal_budget` bytes (a kind's part of it:
        JOURNAL_SHARE), then one 'journal_suppressed' line an hour; a restart keeps counting (the file's tail).
    """

    def __init__(self, log_dir, symbol, keep_days=LOG_KEEP_DAYS, day_cap=LOG_DAY_CAP_BYTES,
                 day_stop=LOG_DAY_STOP_BYTES, max_bytes=LOG_MAX_BYTES, journal_dir=None,
                 journal_budget=JOURNAL_DAY_BYTES, disk_low_bytes=DISK_LOW_BYTES, clock=None, login=None):
        self.dir = str(log_dir)
        self.symbol = str(symbol)
        # login: a function giving the bot's full account number (None while not known): a line of the text log
        # or the events file that holds it anyway -- in a value deep inside a line's data -- is written with its tail
        self._login = login if callable(login) else None
        try:
            days = int(keep_days)
        except (TypeError, ValueError):
            days = LOG_KEEP_DAYS
        self.keep_days = max(1, days)              # (0 would delete today's file at every start)
        self.day_cap = int(day_cap)
        self.day_stop = max(self.day_cap, int(day_stop))
        self.max_bytes = int(max_bytes)
        self.journal_dir = (str(journal_dir) if journal_dir is not None
                            else os.path.join(os.path.dirname(os.path.abspath(self.dir)), 'journal'))
        self.journal_budget = int(journal_budget)
        self.disk_low_bytes = int(disk_low_bytes)
        self._clock = clock if callable(clock) else time.time
        self._lock = threading.Lock()
        self._days = {}                            # 'text' / 'events' -> that file's count for its day
        self._journal_days = {}                    # UTC day -> the journal's count for it
        self._today = None                         # the newest UTC day written
        self._tidy_due = False
        self._tidy_t = None
        self._disk_t = None
        self.disk_low = False
        self.disk_free = None
        self._backlog = {name: deque(maxlen=2000) for name in ('text', 'events', 'journal', 'samples')}
        self._note_t = None
        self.failures = 0
        self.last_error = None
        self.journal_left_out = 0                  # journal lines the day's budget left out, since the start
        # IGNORECASE: on Windows (NTFS keeps the case of whoever made the file first) a day begun by a start that
        # failed before symbols.json was read can be named XAUUSDM_<day>.log; it is still this bot's file
        self._name = re.compile(r'^' + re.escape(self.symbol) + r'_(\d{4}-\d{2}-\d{2})(\.log|_events\.jsonl|'
                                r'_samples\.jsonl)$', re.IGNORECASE)

    # ── the names ──
    def day_path(self, day):
        return os.path.join(self.dir, f'{self.symbol}_{day}.log')

    def events_path(self, day):
        return os.path.join(self.dir, f'{self.symbol}_{day}_events.jsonl')

    def samples_path(self, day):
        return os.path.join(self.dir, f'{self.symbol}_{day}_samples.jsonl')

    def journal_path(self, year):
        return os.path.join(self.journal_dir, f'{self.symbol}_{year}.jsonl')

    def pending(self, name='journal'):
        """Lines of a file a failed write is still holding (written with the next batch)."""
        return len(self._backlog[name])

    # ── one batch ──
    def write(self, records, journal=(), samples=()):
        """records: (t, level, cat, msg, kv, data, tb) tuples, for the text log and the events file; journal:
        (t, kind, the line as JSON text); samples: (t, the line as JSON text). True when every line was stored."""
        records = list(records)
        with self._lock:
            ok = True
            now = self._clock()
            self._check_disk(now)
            for name, fresh, store in (('text', records, self._write_text), ('events', records, self._write_events),
                                       ('journal', list(journal), self._write_journal),
                                       ('samples', list(samples), self._write_samples)):
                backlog = self._backlog[name]
                batch = list(backlog) + fresh
                backlog.clear()
                if not batch:
                    continue
                try:
                    store(batch)
                except Exception as e:
                    backlog.extend(batch)
                    ok = self._failed(e)
            try:
                self._tidy(now)
            except Exception:
                pass                               # (old files that could not be looked at: the next hour tries again)
            return ok

    def _failed(self, e):
        self.failures += 1
        self.last_error = err_text(e)
        now = self._clock()
        if self._note_t is None or not 0.0 <= now - self._note_t < 60.0:
            self._note_t = now
            try:
                print(f'[{self.symbol}] tracelog: cannot write the log in {self.dir}: {err_text(e)} (trading goes on)')
            except Exception:
                pass
        return False

    def _check_disk(self, now):
        """The free space of the disk the logs are on, asked for at most once a minute; while it cannot be asked
        the last answer stands."""
        if self._disk_t is not None and 0.0 <= now - self._disk_t < DISK_CHECK_S:
            return
        self._disk_t = now
        folder = os.path.abspath(self.dir)
        for _ in range(64):                        # (the log folder may not be there yet: the nearest one that is)
            if os.path.isdir(folder):
                break
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
        try:
            free = int(shutil.disk_usage(folder).free)
        except Exception:
            return
        self.disk_free = free
        self.disk_low = free < self.disk_low_bytes

    # ── old files ──
    def _note_day(self, day):
        if self._today is None or day > self._today:
            self._today = day
            self._tidy_due = True                  # the first write of this process, and every new UTC day

    def _tidy(self, now):
        if self._today is None:
            return
        if not (self._tidy_due or self._tidy_t is None or not 0.0 <= now - self._tidy_t < TIDY_EVERY_S):
            return
        self._tidy_due, self._tidy_t = False, now
        self.retention(self._today)
        self.size_guard(self._today)

    def day_files(self):
        """[(date, name)] of this symbol's day files in the log folder, oldest first. Only names of the three day
        patterns: the strategy log, another symbol's files and anything else are not in it."""
        try:
            names = os.listdir(self.dir)
        except OSError:
            return []
        out = []
        for name in names:
            m = self._name.match(name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), '%Y-%m-%d').date()
            except ValueError:
                continue
            out.append((d, name))
        out.sort()
        return out

    def retention(self, today):
        """Delete this symbol's day files of more than `keep_days` days before `today` ('YYYY-MM-DD'), oldest
        first, by the date in the name."""
        try:
            t_today = datetime.strptime(today, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return
        for d, name in self.day_files():
            if (t_today - d).days > self.keep_days:
                try:
                    os.remove(os.path.join(self.dir, name))
                except OSError:
                    pass

    def size_guard(self, today):
        """Keep this symbol's day files under max_bytes in all (today's counted): one pass, oldest first, never
        today's; a file that cannot be deleted is skipped."""
        try:
            t_today = datetime.strptime(today, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return
        files = []
        total = 0
        for d, name in self.day_files():
            path = os.path.join(self.dir, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            files.append((d, path, size))
            total += size
        for d, path, size in files:
            if total <= self.max_bytes:
                break
            if d >= t_today:
                continue
            try:
                os.remove(path)
            except OSError:
                continue
            total -= size

    # ── the text log and the events file ──
    def _day_state(self, kind, day):
        st = self._days.get(kind)
        if st is None or st['day'] != day:
            path = self.day_path(day) if kind == 'text' else self.events_path(day)
            try:
                size = os.path.getsize(path)       # (a restart keeps counting)
            except OSError:
                size = 0
            st = self._days[kind] = {'day': day, 'path': path, 'bytes': size, 'capped': size >= self.day_cap,
                                     'dropped': 0, 'drop_t': None}
        return st

    def _write_capped(self, kind, batch, render):
        by_day = {}
        for rec in batch:
            by_day.setdefault(_day(rec[0]), []).append(rec)
        now = self._clock()
        os.makedirs(self.dir, exist_ok=True)
        for day in sorted(by_day):
            self._note_day(day)
            st = self._day_state(kind, day)
            parts, size = [], 0
            for rec in by_day[day]:
                level = rec[1]
                if self.disk_low and level in ('DEBUG', 'INFO'):
                    continue                       # the disk is nearly full: only what matters is kept
                if st['bytes'] + size >= self.day_stop:
                    st['dropped'] += 1
                    continue
                if st['capped'] and level not in ('WARN', 'ERROR'):
                    continue
                text = render(rec)
                parts.append(text)
                size += len(text.encode('utf-8'))
            last_t = by_day[day][-1][0]
            mb = 2 ** 20
            if parts and not st['capped'] and st['bytes'] + size >= self.day_cap:
                st['capped'] = True
                text = render((last_t, 'WARN', 'LOG', f'this file passed {self.day_cap / mb:g} MB today: until 00:00 '
                               f'UTC it takes only WARN and ERROR lines, and past {self.day_stop / mb:g} MB one line '
                               'a minute that counts what was dropped', {'file': os.path.basename(st['path'])},
                               None, None))
                parts.append(text)
                size += len(text.encode('utf-8'))
            if st['dropped'] and (st['drop_t'] is None or not 0.0 <= now - st['drop_t'] < 60.0):
                text = render((last_t, 'WARN', 'LOG', f"{st['dropped']} lines dropped: this file is past "
                               f'{self.day_stop / mb:g} MB today (it takes lines again at 00:00 UTC)',
                               {'file': os.path.basename(st['path']), 'dropped': st['dropped']}, None, None))
                parts.append(text)
                size += len(text.encode('utf-8'))
                st['dropped'], st['drop_t'] = 0, now
            if not parts:
                continue
            with open(st['path'], 'a', encoding='utf-8') as f:
                f.write(''.join(parts))
            st['bytes'] += size

    def _write_text(self, batch):
        self._write_capped('text', batch, self._net(_text_line))

    def _write_events(self, batch):
        self._write_capped('events', batch, self._net(_event_line))

    def _net(self, render):
        """render, with the last net of the account number: the line is looked at as text, and made again from a
        masked copy of its record (every level deep) only when the full number is in it."""
        def out(rec):
            text = render(rec)
            try:
                login = self._login() if self._login is not None else None
            except Exception:
                login = None
            if login is None or str(login) not in text:
                return text
            tail = _login_tail(login)
            return render(tuple(_masked(x, login, tail, max_depth=64) for x in rec))
        return out

    # ── the samples ──
    def _write_samples(self, batch):
        if self.disk_low:
            return                                 # (dropped: the disk is nearly full)
        by_day = {}
        for t, text in batch:
            by_day.setdefault(_day(t), []).append(text + '\n')
        os.makedirs(self.dir, exist_ok=True)
        for day in sorted(by_day):
            self._note_day(day)
            with open(self.samples_path(day), 'a', encoding='utf-8') as f:
                f.write(''.join(by_day[day]))

    # ── the journal ──
    def _journal_state(self, day):
        st = self._journal_days.get(day)
        if st is None:
            if len(self._journal_days) >= 3:       # (yesterday's and today's: a late line can carry yesterday's time)
                self._journal_days.pop(min(self._journal_days))
            st = self._journal_days[day] = {'bytes': self._journal_bytes(day), 'left_out': 0, 'note_t': None}
        return st

    def _journal_bytes(self, day):
        """The bytes the journal already holds for UTC day `day`: read once per day from the tail of the year's
        file (a line begins {"t":...,"utc":"<day>T..."), so a restart keeps counting towards the budget. A tail
        that is that day's from its first byte means the budget is spent."""
        path = self.journal_path(day[:4])
        limit = int(self.journal_budget * max([1.0] + list(JOURNAL_SHARE.values()))) + 65536
        try:
            size = os.path.getsize(path)
            with open(path, 'rb') as f:
                if size > limit:
                    f.seek(size - limit)
                data = f.read()
        except OSError:
            return 0
        mark = ('"utc":"' + day).encode('ascii')
        return sum(len(line) + 1 for line in data.split(b'\n')
                   if mark in line[:96] and b'"kind":"journal_suppressed"' not in line[:140])

    def _write_journal(self, batch):
        """One append per UTC day of the batch (its year's file). A group that could not be written stays for the
        next batch; the others are stored."""
        by_day = {}
        for item in batch:
            by_day.setdefault(_day(item[0]), []).append(item)
        failed, error = [], None
        for day in sorted(by_day):
            try:
                self._write_journal_day(day, by_day[day])
            except Exception as e:
                failed.extend(by_day[day])
                error = e
        if error is not None:
            batch[:] = failed                      # (the caller keeps what is left for the next batch)
            raise error

    def _write_journal_day(self, day, group):
        st = self._journal_state(day)
        now = self._clock()
        parts, size, left = [], 0, 0
        for t, kind, text in group:
            n = len(text.encode('utf-8')) + 1
            if st['bytes'] + size + n > self.journal_budget * JOURNAL_SHARE.get(kind, 1.0):
                left += 1
                continue
            parts.append(text + '\n')
            size += n
        note = (left or st['left_out']) and (st['note_t'] is None or not 0.0 <= now - st['note_t'] < JOURNAL_NOTE_S)
        if note:
            t = group[-1][0]
            parts.append(dumps({'t': round(float(t), 3), 'utc': _iso(t), 'kind': 'journal_suppressed',
                                'lines': st['left_out'] + left, 'day': day, 'budget_bytes': self.journal_budget,
                                'bytes': st['bytes'] + size}) + '\n')
        if parts:
            os.makedirs(self.journal_dir, exist_ok=True)
            with open(self.journal_path(day[:4]), 'a', encoding='utf-8') as f:
                f.write(''.join(parts))
        st['bytes'] += size
        self.journal_left_out += left
        if note:
            st['left_out'], st['note_t'] = 0, now
        else:
            st['left_out'] += left


# ───────────────────────────── the trace ─────────────────────────────

def _guarded(fn=None, *, flush=True):
    """A trace entry point: whatever it raises is logged (ERROR + traceback) and swallowed. The lines it made are
    written at its end, unless the bot holds its mt5_lock at that moment (_flush waits then: an order, a close or a
    sync inside the lock never waits for the disk) or flush is False (order(), which runs inside
    MT5PositionHelper._send): those lines wait for the next write outside the lock -- the end of the poll,
    poll_skipped, an exception, the job's start-up lines."""
    def wrap(fn):
        name = fn.__name__

        @functools.wraps(fn)
        def call(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except Exception as e:
                try:
                    self._hook_failed(name, e)
                except Exception:
                    pass
                return None
            finally:
                if flush:
                    try:
                        self._flush()
                    except Exception:
                        pass
        return call
    return wrap(fn) if fn is not None else wrap


_FAILED = object()      # what _step returns when the step raised


class _Ctx:
    """The poll's locals, read by name (a missing one reads None)."""
    __slots__ = ('d',)

    def __init__(self, d):
        self.d = d if isinstance(d, dict) else {}

    def __getattr__(self, name):
        return self.d.get(name)


def _gate(key, name, ok, value=None, need=None, note=None, role='need'):
    return {'key': key, 'name': name, 'role': role, 'ok': ok, 'value': value, 'need': need, 'note': note,
            'checked': None}


def _mark_checked(gates):
    """checked = the bot got as far as this gate this poll: 'need' gates stop the walk at the first one not met,
    'exit' gates at the first one that fires, 'add' gates (all needed for an add) at the first one not met.
    Returns the key of the gate that decided: the need gate that blocked, or the exit that fired (else None)."""
    going, decided = True, None
    for g in gates:
        g['checked'] = going
        if not going:
            continue
        if g['role'] == 'need' and g['ok'] is False:
            going, decided = False, g['key']
        elif g['role'] == 'exit' and g['ok'] is True:
            going, decided = False, g['key']
        elif g['role'] == 'add' and g['ok'] is False:
            going = False
    return decided


def _mark(role, ok):
    """How a gate reads in the text log: need gates ok / NO, exit and add gates FIRE / no, '-' = not applicable."""
    if ok is None:
        return '-'
    if role in ('exit', 'add'):
        return 'FIRE' if ok else 'no'
    return 'ok' if ok else 'NO'


def _gates_text(gates):
    """'market_live=ok pause=ok open_score=NO(+1) ...' (checked gates; '-' = not applicable)."""
    out = []
    for g in gates:
        if not g.get('checked'):
            continue
        mark = _mark(g['role'], g.get('ok'))
        v = g.get('value')
        if isinstance(v, bool) or v is None or isinstance(v, (list, dict)):
            out.append(f"{g['key']}={mark}")
        elif isinstance(v, numbers.Real):
            out.append(f"{g['key']}={mark}({v:.6g})")
        else:
            s = str(v)
            out.append(f"{g['key']}={mark}({s if len(s) <= 24 else s[:21] + '...'})")
    return ' '.join(out)


class TraceLog:
    """The trace of one symbol's trading loop. app.py makes one per symbol (MT5TradingBot._tracer) and calls:
    boot(), loop_start(locals), poll(locals) at the end of every poll, poll_skipped(kind, problem), order(request,
    result, refused, ms, quote) from MT5PositionHelper._send, event(...) from _log_event, journal(kind, **fields)
    for the safety's events and the orders it held back, state_saved(state), exception(cat, msg) from an except
    block, write_failed(what, path, error), reconnect_failed(...) from _try_reconnect, log(level, cat, msg, kv).
    No file is read or written while the bot holds mt5_lock (order() and journal() only queue; the others wait
    when the lock is held): the lines made there are written at the end of the poll, by poll_skipped or the
    exception hook."""

    def __init__(self, bot, symbol, out_dir, app_module):
        self.bot = bot
        self.app = app_module
        self.symbol = str(symbol)
        self.mt5_symbol = (getattr(bot, 'symbol_map', None) or {}).get(symbol, symbol)
        self.out_dir = str(out_dir)
        self.log_dir = os.path.join(self.out_dir, 'logs')
        self.journal_dir = os.path.join(self.out_dir, 'journal')
        self.paths = {
            'trace': os.path.join(self.out_dir, f'{self.symbol}_trace.json'),
            'bars': os.path.join(self.out_dir, f'{self.symbol}_bars.json'),
            'trades': os.path.join(self.out_dir, f'{self.symbol}_trades.json'),
            'exits': os.path.join(self.out_dir, 'state', f'{self.symbol}_exit_reasons.json'),
            'jstate': os.path.join(self.out_dir, 'state', f'{self.symbol}_journal_state.json'),
        }
        strategy_mod = sys.modules.get(getattr(getattr(app_module, 'Strategy', None), '__module__', ''), None)
        helper_mod = sys.modules.get(getattr(getattr(app_module, 'MT5PositionHelper', None), '__module__', ''), None)
        self._mods = [m for m in (app_module, strategy_mod, helper_mod, sys.modules.get('constants')) if m is not None]
        self.writer = LogWriter(self.log_dir, self.symbol, keep_days=self._cfg('LOG_KEEP_DAYS', LOG_KEEP_DAYS),
                                journal_dir=self.journal_dir, clock=self._now, login=self._own_login)
        self._lock = threading.Lock()          # the pending lines (log() may come from another thread)
        self._pending = []
        self._jq = []                          # journal lines waiting for the next write: (t, kind, JSON text)
        self._sq = []                          # sample lines waiting for it: (t, JSON text)
        self._errors = deque(maxlen=20000)     # times of ERROR lines (health.errors_1h)
        self._repeats = {}
        self._orders = []                      # this poll's order requests and results (decision.orders)
        self.polls = 0
        self.skipped = 0
        self.reconnects = 0
        self.started_at = self._now()
        self.cost_ms = None                    # this module's own time in the last poll hook (real time)
        self.costs = deque(maxlen=5000)
        self._last_key = None
        self._last_action = None
        self._last_gates = None
        self._last_trace_t = None
        self._last_trace_key = None
        self._last_snapshot = None
        self._last_poll_t = None
        self._hb_t = None
        self._bars_t = None
        self._bars_sig = None
        self._trades_t = None
        self._own_closed = None          # this bot's closed P/L since its live start, from the last deal-history read
        # the journal (the permanent record) and its state file
        self._jruns = {}                 # a journal line that repeats: its key -> how often, when it was last written
        self._js = self._jstate_load()   # journaled trades, the open trade's facts and extremes, lasting problems, the day
        self._js_dirty = None            # None, 'soon' (within JOURNAL_SAVE_S), 'day' (the day's figures only) or 'now'
        self._js_saved_t = None
        self._js_tail_read = False       # the journal's own tail read for trade ids (once, at the first trades read)
        self._js_first = True            # the first poll that read the terminal: is the trade the file holds still open?
        self._start_line = None          # the journal's start line, waiting for the first poll's account figures
        self._smp = None                 # the running minute of the samples
        self._smp_tick = None            # the tick time the last poll saw (ticks_seen)
        self._tidy_t = None              # old temp files and old daily files: when they were last looked for
        self._tidy_day = None
        self._disk_low_said = False
        self._trades_dirty = True
        self._trades_again = False
        self._trades_retry_t = None
        self._prev = {}
        self._digits = None
        self._digits_t = None
        self._pending_reason = None
        self._turtle_pending_key = None  # a Turtle close that left legs open: its exit, for the retry's close
        self._turtle_nothing = None      # a Turtle close that closed nothing (v3.9.2-demo.5): its time and exit, till it ends
        self._fills = {}                 # the bot's fills by order ticket (a basket leg the terminal has not listed yet)
        self._exits = self._load_exits()
        self._last_signal_note = None
        # the Turtle (STRATEGY = 'turtle')
        self.journal_path = os.path.join(self.out_dir, 'state', f'{self.symbol}_turtle_trades.json')
        self._journal = None                   # loaded on the Turtle's first use
        self._facts = None                     # symbol_info facts (digits, contract size, ...), read once
        self._facts_t = None
        self._ch_key = self._ch = None         # the D1 channels, computed once per new D1 bar
        self._vs_key = self._vs = None         # the M15 RSI / MACD lines, computed once per new M15 bar
        self._book_ref = None                  # the Turtle's book (the bot's own dict, read only): entry or add?
        self._state_ref = None                 # the basket loop's state (the bot's own dict, read only): entry or add?
        self._closed_known = None              # the Turtle's closed trades already in trades.json (a RESULT line each)
        self._legs_outside = {}                # the Turtle's legs closed outside the bot: ticket -> TURTLE_LEG_CLOSED_OUTSIDE
        self._outside_logged = set()           # ... of those, the ones the log has a line for

    # ── plumbing ──
    def _now(self):
        try:
            return float(self.app.time.time())
        except Exception:
            return time.time()

    def _cfg(self, name, default=None):
        for m in self._mods:
            if hasattr(m, name):
                return getattr(m, name)
        return default

    def _call(self, name, *args, **kwargs):
        fn = getattr(self.app, name, None)
        return fn(*args, **kwargs) if callable(fn) else None

    def _own_login(self):
        """The bot's own account number when it can be told from its tail (five digits or more), else None. Read
        only to keep it out of every file (_mask) and to recognise the account's state file (_login_sha)."""
        login = getattr(self.bot, '_login', None)
        if isinstance(login, bool) or not isinstance(login, int) or login < 10000:
            return None
        return login

    def _mask(self, obj):
        """obj as it may be written: the bot's full account number, wherever it stands, as its tail (dicts and
        lists come back as copies)."""
        login = self._own_login()
        return obj if login is None else _masked(obj, login, _login_tail(login))

    def _copy(self, obj):
        """A copy of what app.py handed over (its own dicts change from poll to poll), masked as _mask does."""
        login = self._own_login()
        return _masked(obj, login, _login_tail(login) if login is not None else None)

    def _write_json(self, path, obj):
        """write_json_atomic for the files of this module (the trace, the trades, the state files), with the last
        net of the account number: should the bot's full number be anywhere in obj -- a problem text app.py wrote,
        a value -- the file holds its tail. It is looked for in the JSON text, so the masked copy (every level
        deep) is made only when the number is there; the common case costs one search of the text."""
        text = dumps(obj)
        login = self._own_login()
        if login is not None and str(login) in text:
            text = dumps(_masked(obj, login, _login_tail(login), max_depth=64))
        return write_json_atomic(path, None, text=text)

    def _own_tail(self):
        """'...1234' of the account of the bot's credentials (None before they are loaded)."""
        tail = getattr(self.bot, '_login_tail', None)
        return str(tail) if tail else None

    def _rec(self, level, cat, msg, kv=None, data=None, tb=None, t=None):
        t = self._now() if t is None else float(t)
        if self._own_login() is not None:      # (the last net: no line carries the full account number)
            msg, kv, tb = self._mask(msg), self._mask(kv), self._mask(tb)
        with self._lock:
            self._pending.append((t, level if level in LEVELS else 'INFO', cat, msg, kv, data, tb))
        if level == 'ERROR':
            self._errors.append(t)

    def _in_lock(self):
        """True while the bot's mt5_lock is held (one symbol per process: by this thread, sending or reading)."""
        lk = getattr(self.bot, 'mt5_lock', None)
        try:
            return bool(lk is not None and lk.locked())
        except Exception:
            return False

    def _flush(self):
        """Write the pending lines -- the text log and the events, the journal, the samples: one batch -- never
        while the bot holds mt5_lock: then they wait for the next flush, so no order, close or terminal read waits
        for the disk."""
        if self._in_lock():
            return
        # the journal's start line is made at the end of the loop's first poll (it holds that poll's balance): what
        # that poll queues before it -- its own orders -- waits those few moments, so the start line comes first
        start = self._start_line
        wait = start is not None and 0.0 <= self._now() - start['at'] < 90.0
        with self._lock:
            recs, self._pending = self._pending, []
            jrecs = []
            if not wait:
                jrecs, self._jq = self._jq, []
            srecs, self._sq = self._sq, []
        if recs or jrecs or srecs:
            self.writer.write(recs, journal=jrecs, samples=srecs)
        if self._js_dirty == 'now':
            # a trade line or a problem's line has just gone out: the state that says so follows it at once, also
            # outside a poll (a start that fails and ends writes its lines through here)
            self._jstate_save(self._now())

    def _repeat(self, key, every=REPEAT_EVERY_S):
        """(write now?, repeats since it was last written): a line keyed `key` at most once per `every` s."""
        now = self._now()
        last = self._repeats.get(key)
        if last is not None and now - last[0] < every:
            self._repeats[key] = (last[0], last[1] + 1)
            return False, last[1] + 1
        if len(self._repeats) > 500:
            self._repeats.clear()
        self._repeats[key] = (now, 0)
        return True, (last[1] if last else 0)

    def _hook_failed(self, name, e, step=None):
        tb = traceback.format_exc()
        write, n = self._repeat(('hook', name, step, type(e).__name__, _tb_where(tb)))
        if write:
            more = f' (it failed {n} more times since it was last written)' if n else ''
            at = f' in its step {step}' if step else ''
            goes_on = 'its other steps and the trading go on' if step else 'trading goes on'
            self._rec('ERROR', 'TRACE', f'the trace hook {name}() failed{at}: {err_text(e)}; ignored, {goes_on}{more}', tb=tb)
        else:
            self._errors.append(self._now())

    def _step(self, name, step, fn, *args, **kwargs):
        """One step of a poll hook: what it raises is an ERROR line (with its traceback, repeats at most every 10 min)
        and _FAILED is returned, so the steps after it (the trace file, the bars, the trades, the heartbeat, the
        bookkeeping) still run."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            try:
                self._hook_failed(name, e, step)
            except Exception:
                pass
            return _FAILED

    def _transitions_step(self, fn, keep, c, snap, dec, orders, now, digits):
        """The transitions step of a poll (_transitions, _turtle_transitions), as _step. When it raises, keep(c) still
        records this poll's book for the next poll to compare with: the line that failed is not tried again -- and
        does not fail again -- on every poll after it (until the book changed again: hours in a pause after a loss)."""
        step = getattr(fn, '__name__', 'transitions')
        r = self._step('poll', step, fn, c, snap, dec, orders, now, digits)
        if r is _FAILED:
            self._step('poll', step, keep, c)
        return r

    def _keep_basket(self, c):
        st = c.state or {}
        self._prev.update(polled=True, basket=_basket_sum(st.get('basket')), lc=_close_sum(st.get('last_close')))

    def _keep_turtle(self, c):
        self._prev.update(polled=True, turtle=self._book_sum(c.st if isinstance(c.st, dict) else {}))

    def _failed_decision(self, orders, step):
        """The decision of a poll whose trace could not work it out (a step before it raised): said as such."""
        return {'action': 'TRACE_ERROR', 'reason': step, 'side': None,
                'headline': (f'The trace could not work out what the bot decided this poll: its step {step} failed (the '
                             'ERROR line of the log has the traceback). The trading is not affected.'),
                'gates': [], 'blocked_by': None, 'signal': None, 'orders': orders}

    def _errors_1h(self, now):
        return sum(1 for t in self._errors if now - t <= 3600.0)

    # ── entry points ──
    @_guarded
    def log(self, level, cat, msg, kv=None, tb=None):
        self._rec(level, cat, msg, kv=kv, tb=tb)

    @_guarded
    def boot(self, records):
        """Lines the bot logged before this trace existed (job start, the account checks): (t, level, cat, msg, kv, tb)."""
        # (the credentials are loaded by now, if they could be: a journal state of another account is set aside
        # before a problem of this start is added to it)
        self._step('boot', '_jstate_account', self._jstate_account)
        for t, level, cat, msg, kv, tb in records or ():
            self._rec(level, cat, msg, kv=kv, tb=tb, t=t)
            if level == 'ERROR':             # a start (or a reconnect) that failed: a problem that lasts until a poll
                self._issue_on('BOOT_' + str(cat), _problem_key(msg), self._mask(str(msg)), float(t))   # reads the terminal

    @_guarded
    def exception(self, cat, msg, level='ERROR'):
        """From inside an except block: an ERROR (or `level`) line with the traceback; the same exception at the same
        place is written again at most every 10 min, with the count of the repeats (errors_1h counts every one)."""
        e = sys.exc_info()[1]
        tb = traceback.format_exc() if e is not None else None
        write, n = self._repeat(('exc', cat, type(e).__name__ if e else None, _tb_where(tb)))
        if write:
            self._rec(level, cat, msg + (f' (it happened {n} more times since it was last written)' if n else ''), tb=tb)
        elif level == 'ERROR':
            self._errors.append(self._now())

    @_guarded
    def write_failed(self, what, path, err):
        write, n = self._repeat(('write', what), every=300.0)
        if write:
            more = f' ({n} more failures since the last line)' if n else ''
            self._rec('WARN', 'WRITE', f'could not write {what}: {err_text(err)}; trading goes on{more}', kv={'path': path})

    @_guarded
    def reconnect_failed(self, attempt, why, next_in_s=None, outage_s=None, logged=False):
        """MT5TradingBot._try_reconnect: a reconnect attempt failed. The strategy log has RECONNECT_FAILED once for each
        reason, then at most every 15 min for that reason (logged: this attempt's event was written, and event() made
        its ERROR line); every other attempt is a WARN line here, so the text log has each one."""
        if logged:
            return
        self._rec('WARN', 'TERMINAL', f'reconnect attempt {attempt} failed ({why}); next one in {_num(next_in_s, 0)} s, '
                  f'{_dur(outage_s)} without the terminal so far (the strategy log has RECONNECT_FAILED once for each '
                  'reason, then at most every 15 min for that reason)',
                  kv={'attempt': attempt, 'why': why, 'next_in_s': next_in_s, 'outage_s': outage_s})

    @_guarded
    def state_saved(self, state):
        b = (state or {}).get('basket')
        lc = (state or {}).get('last_close')
        self._rec('DEBUG', 'STATE', f'state saved: {self._basket_words(b)}; last close: {self._close_words(lc)}',
                  data={'basket': b, 'last_close': lc})

    @_guarded
    def state_note(self, level, msg):
        self._rec(level, 'STATE', msg)

    @_guarded(flush=False)
    def order(self, request, result, refused=False, ms=None, quote=None):
        """Every order request of the bot (MT5PositionHelper._send) and its result. It runs inside the bot's mt5_lock,
        before order_send's result reaches the bot, so it only makes the record and its lines: they are written at the
        end of the poll (or by poll_skipped / the exception hook), never in here. A close is told by the side of the
        position it closes (side; the order itself is the other side: order_side).
        refused: True = the account guard stopped the request, 'safety' = the safety guard of buy() / sell() did;
        neither reached the terminal. quote: {'bid', 'ask', 't_msc'}, the tick the helper read when it built the
        request (None: not handed over). From it the journal's order line gets the spread and the slippage: the fill
        against the ask for a BUY order, against the bid for a SELL order -- an open, an add and a close alike --
        above 0 = filled worse than quoted. Without a fill price, or with a retcode that is not done, they are
        null."""
        r = request or {}
        typ = _i(r.get('type'))
        order_side = 'BUY' if typ == 0 else 'SELL' if typ == 1 else str(typ)
        is_close = 'position' in r
        if is_close:
            kind = 'close'
            side = 'SELL' if typ == 0 else 'BUY' if typ == 1 else str(typ)      # a BUY order closes a SELL position
            what = f"close position {r.get('position')} ({side} {r.get('volume')} lot, with a {order_side} order)"
        else:
            side = order_side
            kind = self._entry_kind(side)
            what = f"{kind} {side} {r.get('volume')} lot"
        by_safety = bool(refused) and str(refused).strip().lower() == 'safety'
        guard = 'safety guard' if by_safety else 'account guard'
        retcode = _i(getattr(result, 'retcode', None))
        done = retcode in _DONE
        err = None
        if result is None and not refused:
            try:
                err = self.app.mt5.last_error()
            except Exception as e:
                err = repr(e)
        q = quote if isinstance(quote, dict) else {}
        bid, ask = _f(q.get('bid')), _f(q.get('ask'))
        fill = _f(getattr(result, 'price', None))
        fill = fill if (done and fill) else None                  # (an answer without a price says 0)
        slip = None
        if fill is not None:
            if order_side == 'BUY' and ask is not None:
                slip = fill - ask
            elif order_side == 'SELL' and bid is not None:
                slip = bid - fill
        vol = _f(getattr(result, 'volume', None)) or _f(r.get('volume'))
        cs = self._contract_size() if slip is not None else None
        o = {
            't': self._now(), 'kind': kind, 'side': side, 'order_side': order_side, 'symbol': r.get('symbol'),
            'volume': _f(r.get('volume')),
            'price': _f(r.get('price')), 'sl': _f(r.get('sl')), 'tp': _f(r.get('tp')), 'position': r.get('position'),
            'magic': r.get('magic'), 'comment': r.get('comment'),
            'refused': ('safety' if by_safety else True) if refused else False, 'retcode': retcode,
            'retcode_text': RETCODES.get(retcode) if retcode is not None else (f'refused by the {guard}'
                                                                               if refused else 'no answer'),
            'done': done, 'result_price': _f(getattr(result, 'price', None)),
            'result_volume': _f(getattr(result, 'volume', None)), 'order': _i(getattr(result, 'order', None)),
            'deal': _i(getattr(result, 'deal', None)), 'result_comment': getattr(result, 'comment', None),
            'last_error': err, 'ms': _f(ms, 2),
            'bid': bid, 'ask': ask, 'spread': _f(ask - bid, 8) if (bid is not None and ask is not None) else None,
            'fill_price': fill, 'slippage': _f(slip, 8),
            'slippage_usd': _f(slip * vol * cs, 4) if (slip is not None and vol and cs) else None,
        }
        o = self._mask(o)
        self._orders.append(o)
        if done and not is_close and o['order']:
            # (v3.9.2-demo.5) the basket takes the leg's position id from this answer at once (app.py _record_fill):
            # kept here so the trace can show a leg the terminal has not listed yet (its price and lots)
            self._fills[o['order']] = o
            if len(self._fills) > 50:
                self._fills = dict(list(self._fills.items())[-20:])
        d = self._digits                       # (known after the first poll; no terminal call in here: inside mt5_lock)
        price = f" at {_px(o['price'], d)}" if o['price'] is not None else ''
        stops = '' if is_close else f" sl {_px(o['sl'], d) if o['sl'] else 'none'} tp {_px(o['tp'], d) if o['tp'] else 'none'}"
        res = (f'not sent: the {guard} refused it' if refused else
               f"{o['retcode_text']} ({retcode})" if retcode is not None else f'no answer ({err})')
        kv = {k: o[k] for k in ('kind', 'side', 'order_side', 'symbol', 'volume', 'price', 'sl', 'tp', 'position',
                                'magic', 'comment', 'retcode', 'retcode_text', 'result_price', 'result_volume', 'order',
                                'deal', 'result_comment', 'last_error', 'ms', 'bid', 'ask', 'spread', 'slippage',
                                'slippage_usd')
              if o[k] is not None and (k != 'order_side' or is_close)}
        self._rec('ORDER', 'ORDER', f'{what}{price}{stops} -> {res}', kv=kv)
        if done and not is_close:
            self._rec('FILL', 'FILL', f"{side} {o['result_volume'] or o['volume']} lot filled at "
                      f"{_px(o['result_price'] or o['price'], d)}"
                      + (f" (order {o['order']}, deal {o['deal']})" if o['order'] else '')
                      + (f", broker sl {_px(o['sl'], d)}" if o['sl'] else '')
                      + (f", broker tp {_px(o['tp'], d)}" if o['tp'] else ''),
                      kv={'kind': kind, 'side': side, 'price': o['result_price'], 'volume': o['result_volume'],
                          'order': o['order'], 'deal': o['deal'], 'sl': o['sl']})
        elif not done:
            self._rec('WARN', 'ORDER', f'{what} was not filled: {res}', kv={'retcode': retcode, 'last_error': err})
        if done:
            self._trades_dirty = True
        # the permanent record of the request and its answer (queued; written with the next batch outside the lock)
        t_msc = _f(q.get('t_msc'))
        self._jline('order', {
            'action': kind, 'side': side, 'order_side': order_side, 'symbol': o['symbol'], 'volume': o['volume'],
            'price': o['price'], 'bid': bid, 'ask': ask, 'spread': o['spread'],
            'quote_t': round(t_msc / 1000.0, 3) if t_msc else None, 'sl': o['sl'], 'tp': o['tp'],
            'position': o['position'], 'magic': o['magic'], 'refused': o['refused'], 'retcode': retcode,
            'retcode_text': o['retcode_text'], 'comment': o['result_comment'], 'done': done, 'order': o['order'],
            'deal': o['deal'], 'fill_price': fill, 'fill_volume': o['result_volume'] if done else None,
            'slippage': o['slippage'], 'slippage_usd': o['slippage_usd'], 'last_error': err, 'ms': o['ms']}, t=o['t'])

    def _contract_size(self):
        """The symbol's contract size from what the bot already knows (no terminal call: order() runs inside
        mt5_lock): the Turtle's symbol facts, else the basket loop's USD per price move / mtqty, else
        CONTRACT_SIZE_FALLBACK by the symbol's prefix. None when not known."""
        facts = self._facts if isinstance(self._facts, dict) else {}
        size = _f(facts.get('contract_size'))
        if size:
            return size
        upp = _f((getattr(self.bot, '_usd_per_price', None) or {}).get(self.mt5_symbol))
        mtqty = _f((getattr(self.bot, 'symbols_config', None) or {}).get('mtqty'))
        if upp and mtqty:
            return round(upp / mtqty, 6)
        for prefix, value in (self._cfg('CONTRACT_SIZE_FALLBACK') or {}).items():
            if str(self.mt5_symbol).upper().startswith(str(prefix).upper()):
                return _f(value)
        return None

    # ── the permanent journal: journal/<SYMBOL>_<YYYY>.jsonl ──
    @_guarded(flush=False)
    def journal(self, kind, /, **fields):
        """One line of the permanent journal: app.py's safety events (kind 'safety', every item of
        Tracker.take_events()) and the orders the safety held back ('skip'); this module writes 'start', 'order',
        'trade', 'day' and 'issue' itself. It never raises and it only queues -- it may be called while the bot
        holds mt5_lock: the line is written by LogWriter with the next batch, outside the lock. `kind` is
        positional only, so a field may be called 'kind' too (it is written as 'subkind')."""
        self._jline(str(kind), fields)

    _JOURNAL_OWN_KEYS = {'kind': 'subkind', 't': 't_event', 'utc': 'utc_event'}
    _JOURNAL_FACTS = ('start', 'trade', 'day', 'issue')     # one line each, never a repeat of another

    def _jline(self, kind, fields, t=None, first=False):
        """Queue a journal line {t, utc, kind, ...fields}; memory only. A line that repeats (_jline_repeat) is
        counted instead: True when the line was queued. first: in front of the lines that wait (the start line,
        made at the end of the first poll, before that poll's own orders)."""
        now = self._now() if t is None else float(t)
        line = {'t': round(now, 3), 'utc': _iso(now), 'kind': kind}
        for k, v in (fields or {}).items():
            line[self._JOURNAL_OWN_KEYS.get(k, k)] = v
        line = self._mask(line)
        with self._lock:
            if kind not in self._JOURNAL_FACTS and line.get('done') is not True:
                left = self._jline_repeat(kind, line, now)
                if left is None:
                    return False
                if left:
                    line['repeats'] = left
            self._jline_queue(now, kind, line, first)
        return True

    def _jline_queue(self, t, kind, line, first=False):
        try:
            text = dumps(line)
            login = self._own_login()
            if login is not None and str(login) in text:       # (deeper than _mask looks: the last net)
                text = dumps(_masked(line, login, _login_tail(login), max_depth=64))
        except Exception as e:                 # (a value JSON cannot hold: the line keeps its time and kind)
            text = dumps({'t': line.get('t'), 'utc': line.get('utc'), 'kind': kind,
                          'not_written': err_text(e)})
        self._jq.insert(0 if first else len(self._jq), (t, kind, text))
        if len(self._jq) > 5000:               # (a bound while nothing can be written)
            del self._jq[:-5000]

    @staticmethod
    def _jline_key(kind, line):
        """What makes two journal lines 'the same': the kind, the action (an order's open / add / close, an event's
        name, a hold's reason), the position or the side, and the answer."""
        what = line.get('action') or line.get('event') or line.get('code') or line.get('why')
        who = next((line[k] for k in ('position', 'ticket', 'key', 'id', 'side') if line.get(k) is not None), None)
        res = line.get('retcode')
        if res is None:
            res = line.get('refused') or None
        return tuple(x if isinstance(x, (str, int, float, bool, type(None))) else str(x)
                     for x in (kind, what, who, res))

    def _jline_repeat(self, kind, line, now):
        """The repeat rule: the same line (_jline_key) is written the first JOURNAL_REPEAT_FIRST times in a row,
        then once per JOURNAL_REPEAT_S with the count of those left out. Returns that count for a line to write
        (0: none), None for one that is left out and counted (the newest is kept: _jline_runs writes it when no
        other of its kind follows within the minute). 'In a row' ends after JOURNAL_RUN_GAP_S without the line.
        A filled order is never a repeat (the caller does not ask)."""
        key = self._jline_key(kind, line)
        run = self._jruns.get(key)
        if run is None or not 0.0 <= now - run['seen'] <= JOURNAL_RUN_GAP_S:
            if run is not None:
                self._jline_held_out(run)      # (the row before: what it still held is written, not forgotten)
            if len(self._jruns) >= 300:
                for k in sorted(self._jruns, key=lambda k: self._jruns[k]['seen'])[:100]:
                    self._jline_held_out(self._jruns.pop(k))
            run = self._jruns[key] = {'n': 0, 'written': now, 'held': 0, 'seen': now, 'last': None}
        run['seen'] = now
        run['n'] += 1
        if run['n'] <= JOURNAL_REPEAT_FIRST or not 0.0 <= now - run['written'] < JOURNAL_REPEAT_S:
            left, run['held'], run['written'], run['last'] = run['held'], 0, now, None
            return left
        run['held'] += 1
        run['last'] = (now, kind, line)
        return None

    def _jline_held_out(self, run):
        """Queue the newest line a row of repeats still holds, with the count of the others it left out (the caller
        has self._lock)."""
        if run['held'] and run['last'] is not None:
            t, kind, line = run['last']
            if run['held'] > 1:
                line = dict(line, repeats=run['held'] - 1)
            self._jline_queue(t, kind, line)
        run['held'], run['last'] = 0, None

    def _jline_runs(self, now):
        """A run of repeats that has ended: its newest line, left out so far, is written once the minute is over,
        with the count of the others -- so every line that was left out is counted in one that is written."""
        with self._lock:
            for run in self._jruns.values():
                if run['held'] and not 0.0 <= now - run['written'] < JOURNAL_REPEAT_S:
                    self._jline_held_out(run)
                    run['written'] = now

    def _entry_kind(self, side):
        """'add' or 'open' for an order that is not a close, from the bot's own dicts (changed in place, read only):
        the Turtle's book, or the basket loop's state -- an order on the side of the trade or basket it holds is an
        add (also on the first poll after a start, before the trace has seen a poll); without them (a trace made
        outside the loop) the positions of the last poll."""
        book = self._book_ref if isinstance(self._book_ref, dict) else None
        if book is not None:
            return 'add' if book.get('side') == (1 if side == 'BUY' else -1) else 'open'
        st = self._state_ref if isinstance(self._state_ref, dict) else None
        if st is not None:
            b = st.get('basket')
            return 'add' if isinstance(b, dict) and b.get('side') == side else 'open'
        prev = self._prev.get('positions') or {}
        return 'add' if prev.get(side) else 'open'

    _EVENTS = {  # the strategy log's events -> (level, category); None = covered by the ORDER / FILL / BASKET / CLOSE lines
        'BUY_EXECUTED': None, 'SELL_EXECUTED': None, 'BUY_MORE_EXECUTED': None, 'SELL_MORE_EXECUTED': None,
        'CLOSE_BUY': None, 'CLOSE_SELL': None,
        'BUY_SIGNAL': ('DEBUG', 'SIGNAL'), 'SELL_SIGNAL': ('DEBUG', 'SIGNAL'),
        'ACCOUNT_REFUSED': ('ERROR', 'ACCOUNT'), 'ACCOUNT_OK': ('INFO', 'ACCOUNT'),
        'TERMINAL_ERROR': ('WARN', 'TERMINAL'), 'TERMINAL_OK': ('INFO', 'TERMINAL'),
        'TERMINAL_RECONNECTED': ('INFO', 'TERMINAL'), 'RECONNECT_FAILED': ('ERROR', 'TERMINAL'),
        'TERMINAL_IN_USE': ('ERROR', 'ACCOUNT'), 'SERVER_MISMATCH': ('ERROR', 'ACCOUNT'),
        'LEG_CLOSED_OUTSIDE': ('WARN', 'BASKET'),
        # the real-money layer: the safety, other activity on the account, the login, refused orders
        'SAFETY_ERROR': ('ERROR', 'SAFETY'), 'SAFETY_SKIP': ('WARN', 'SAFETY'), 'SAFETY_BLOCKED': ('WARN', 'SAFETY'),
        'SAFETY_UNBLOCKED': ('INFO', 'SAFETY'),
        'FOREIGN_POSITIONS': ('ERROR', 'ACCOUNT'), 'OLD_BOT_SAME_TERMINAL': ('ERROR', 'ACCOUNT'),
        'OLD_BOT_RUNNING': ('WARN', 'ACCOUNT'), 'OTHER_PROGRAM': ('ERROR', 'ACCOUNT'),
        'TRADING_NOT_ALLOWED': ('ERROR', 'TERMINAL'), 'TRADING_ALLOWED': ('INFO', 'TERMINAL'),
        'STATE_OTHER_ACCOUNT': ('ERROR', 'STATE'),
        'LOGIN_REFUSED': ('ERROR', 'ACCOUNT'), 'LOGIN_WAIT': ('WARN', 'ACCOUNT'),
        'CLOSE_RESULT_UNKNOWN': ('WARN', 'CLOSE'),
        'BUY_REFUSED': ('WARN', 'ORDER'), 'SELL_REFUSED': ('WARN', 'ORDER'),
        'BUY_MORE_REFUSED': ('WARN', 'ORDER'), 'SELL_MORE_REFUSED': ('WARN', 'ORDER'),
        'TURTLE_ADDS_STOPPED': ('WARN', 'TRADE'),
        # the Turtle's: covered by the trace's LEVELS / TRADE / STOP / CLOSE lines (they diff the book every poll)
        'TURTLE_LEVELS': None, 'TURTLE_REBUILT': None, 'TURTLE_CLOSED_OUTSIDE': None, 'TURTLE_LEG_CLOSED_OUTSIDE': None,
    }
    # What each event of the real-money layer says in the log when app.py gives no sentence of its own (its note /
    # problem / text). {note} = app.py's sentence.
    _EVENT_WORDS = {
        'ACCOUNT_REFUSED': 'not trading: {note}',
        'ACCOUNT_OK': "MetaTrader 5 holds this bot's account again: trading",
        'TERMINAL_ERROR': 'poll skipped, nothing decided: {note}',
        'TERMINAL_OK': 'the terminal answers again',
        'TERMINAL_RECONNECTED': 'connected to the terminal again',
        'RECONNECT_FAILED': 'reconnect failed: {note}',
        # (the problem names TERMINAL_IN_USE itself; the strategy log has each problem once, then at most every
        # 15 min: _log_limited)
        'TERMINAL_IN_USE': ('{note} No login: MetaTrader 5 and its account are left as they are (this line comes '
                            'once for each account it holds, then at most every 15 min)'),
        # (the problem names SERVER_MISMATCH itself, as TERMINAL_IN_USE's does)
        'SERVER_MISMATCH': ('{note} The bot trades nothing on that server and never logs in over it (this line comes '
                            'once for each server MetaTrader 5 shows, then at most every 15 min)'),
        'SAFETY_ERROR': ('the safety check failed: {note}. No new trade is opened until it works again or the safety '
                         'is turned OFF; open trades are still managed'),
        'SAFETY_SKIP': 'an order was not sent: {note}',
        'SAFETY_BLOCKED': 'the safety has blocked new trades: {note}',
        'SAFETY_UNBLOCKED': 'the safety block is lifted: new trades are allowed again',
        'FOREIGN_POSITIONS': '{note}',
        'OLD_BOT_SAME_TERMINAL': '{note}',
        'OLD_BOT_RUNNING': '{note}',
        'OTHER_PROGRAM': '{note}',
        'TRADING_NOT_ALLOWED': '{note}',
        'TRADING_ALLOWED': '{note}',
        'STATE_OTHER_ACCOUNT': '{note}',
        'LOGIN_REFUSED': '{note}',
        'LOGIN_WAIT': '{note}',
        'CLOSE_RESULT_UNKNOWN': '{note}',
        'TURTLE_ADDS_STOPPED': '{note}',
    }
    _EVENT_DEFAULT_NOTE = {
        'SAFETY_ERROR': 'it could not read or save its files',
        'SAFETY_SKIP': 'the safety held it back',
        'SAFETY_BLOCKED': 'a limit was reached',
        'FOREIGN_POSITIONS': ("trades that are not this bot's are open on this symbol in this account. Nothing manages "
                              'them here: close them yourself'),
        'OLD_BOT_SAME_TERMINAL': ('an old bot is running on this server and uses the same MetaTrader 5: it would add '
                                  "to and close this bot's trades. Stop it"),
        'OLD_BOT_RUNNING': 'an old bot is running on this server, on another MetaTrader 5',
        'OTHER_PROGRAM': "another program is trading this bot's symbol in this account",
        'TRADING_NOT_ALLOWED': ('trading is switched off in MetaTrader 5 or for this account: the bot can neither '
                                'open nor close'),
        'TRADING_ALLOWED': 'MetaTrader 5 lets this bot trade again',
        'STATE_OTHER_ACCOUNT': "this bot's saved trade belongs to another account: the file is set aside",
        'LOGIN_REFUSED': 'the server refused the login of this account: check login_id, login_pass and server',
        'LOGIN_WAIT': 'MetaTrader 5 is not logged into any account, and the bot may not log in itself right now',
        'SERVER_MISMATCH': ("MetaTrader 5 holds this bot's account number on another server than mt5_credentials.json "
                            'names: correct "server" in the "live" block and start again'),
        'CLOSE_RESULT_UNKNOWN': ('the result of a closed trade is not in the deal history: what the bot saw at the '
                                 'close counts'),
        'TURTLE_ADDS_STOPPED': ('the price ran more than one add step past an add the safety held back: this trade '
                                'takes no more adds'),
    }
    # The problems the journal's issue lines follow from the events (the others it reads from every poll: _issues):
    # one line each time (a moment), or a problem that lasts until the next poll that reads the terminal.
    _ISSUE_MOMENTS = ('STATE_OTHER_ACCOUNT', 'OTHER_PROGRAM', 'CLOSE_RESULT_UNKNOWN', 'LEG_CLOSED_OUTSIDE',
                      'TURTLE_ADDS_STOPPED')
    _ISSUE_NEVER = ('SAFETY_SKIP', 'SAFETY_BLOCKED', 'BUY_REFUSED', 'SELL_REFUSED', 'BUY_MORE_REFUSED',
                    'SELL_MORE_REFUSED')       # (the journal has these as its safety, skip and order lines)

    @staticmethod
    def _event_note(d):
        """app.py's own sentence of an event: its note, problem, why, text or message; its reasons joined."""
        for k in ('note', 'problem', 'why', 'text', 'message', 'reason'):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        rs = d.get('reasons')
        if isinstance(rs, (list, tuple)) and rs:
            return ' '.join(str(x) for x in rs if x)
        return None

    @_guarded
    def event(self, event, tag, details=None, server_time=None):
        """An event of the strategy log (MT5TradingBot._log_event), as a log line; a problem also as a line of the
        journal (issue)."""
        if event == 'TERMINAL_RECONNECTED':
            self.reconnects += 1
        if event == 'TURTLE_NOTE':           # the Turtle's notes (at most every 5 min each): missing bars, refusals ...
            d = {k: v for k, v in (details or {}).items() if k != 'response'}
            note = str(d.pop('note', '') or 'note')
            self._rec('INFO' if note.lower().startswith('brake') else 'WARN', 'TURTLE', note, kv=d or None)
            return
        if event == 'TURTLE_LEG_CLOSED_OUTSIDE':
            # its WARN TRADE line now, before the orders that close the other legs: closed at or beyond the stop
            # (beyond_stop, from the deal history: the other legs are closed at once) or inside it (by hand); kept for
            # the end of this poll's decision, CLOSE line, exit reasons and journal
            d = dict(details or {}, t=self._now())
            gone = [_i(k) for k in (d.get('tickets') or []) if _i(k) is not None]
            for k in gone:
                self._legs_outside[k] = d
            if len(self._legs_outside) > 200:
                self._legs_outside = dict(list(self._legs_outside.items())[-100:])
            book = self._book_ref if isinstance(self._book_ref, dict) else {}
            side = {1: 'BUY', -1: 'SELL'}.get(_i(book.get('side')))
            if gone and side:
                self._log_outside(gone, side, None, self._digits)
            return
        m = self._EVENTS.get(event, ('ERROR', 'EVENT') if tag == 'ERROR' else ('INFO', 'EVENT'))
        if m is None:
            return
        level, cat = m
        d = {k: v for k, v in (details or {}).items() if k != 'response'}
        note = self._event_note(d)
        if cat == 'SIGNAL':                 # the brake note repeats every poll: once, then again after 10 min
            key = (event, note)
            write = self._repeat(('signal', key))[0]
            if key == self._last_signal_note and not write:
                return
            self._last_signal_note = key
        if event in ('BUY_REFUSED', 'SELL_REFUSED', 'BUY_MORE_REFUSED', 'SELL_MORE_REFUSED'):
            msg = self._refused_words(event, note, d)
        elif event == 'SAFETY_SKIP' and isinstance(d.get('hold'), dict) and not note:
            h = d['hold']
            msg = (f"no {h.get('kind') or 'new'} order was sent"
                   + (f" ({h.get('side')})" if h.get('side') else '') + f': {self._hold_words(h)}')
        else:
            said = note if note is not None else self._EVENT_DEFAULT_NOTE.get(event)
            words = self._EVENT_WORDS.get(event)
            if words is None:                # an event this module has no sentence for: its name and app.py's note
                msg = f'{event}: {said}' if said else event
            elif words == '{note}':
                msg = said or event
            elif event == 'TERMINAL_IN_USE':  # (app.py's note is whole sentences: it ends with a full stop)
                msg = words.format(note=(said or 'MetaTrader 5 is logged into another account').rstrip('.') + '.')
            elif event == 'SERVER_MISMATCH':  # (the same: whole sentences)
                said = (said or '').rstrip('.')
                msg = words.format(note=said[:1].upper() + said[1:] + '.')
            elif event == 'SAFETY_ERROR':
                msg = words.format(note=(said or 'no reason given').rstrip('.'))
            elif event == 'ACCOUNT_OK':
                tail = d.get('login_tail') or self._own_tail()
                msg = (f"MetaTrader 5 holds this bot's account {tail} again: trading" if tail else words)
            else:
                msg = words.format(note=said if said is not None else 'no reason given')
        if event == 'TERMINAL_RECONNECTED' and d.get('outage_s') is not None:
            msg += (f" (attempt {d.get('attempt')}, after {_dur(d.get('outage_s'))} without the terminal and "
                    f"{d.get('failed_attempts')} failed attempt(s))")
        elif event == 'RECONNECT_FAILED':
            more = _i(d.get('not_logged_since')) or 0
            msg += (f"; next attempt in {_num(d.get('next_in_s'), 0)} s (the strategy log has this once for each reason, "
                    'then at most every 15 min for that reason; every attempt is a line here)'
                    + (f'; {more} more failed attempt(s) with this reason since its last RECONNECT_FAILED' if more else ''))
        elif event == 'LEG_CLOSED_OUTSIDE':
            msg = (f"leg(s) {d.get('legs_gone')} of the {d.get('side')} basket closed outside the bot (the broker's backstop, "
                   f"a stop-out or by hand): the other {len(d.get('legs_left') or [])} leg(s) are closed at once and the "
                   'whole basket is booked as closed outside the bot')
        self._rec(level, cat, msg, kv=dict(d, event=event))
        if level in ('WARN', 'ERROR') and event not in self._ISSUE_NEVER:
            self._issue_from_event(event, note or msg, msg, d)

    def _refused_words(self, event, note, d):
        """An opening order that was not filled (app.py: the first three of a streak one by one, then a summary
        every 30 s). Refused by the broker: its retcode and its comment. No answer at all (order_send gave None:
        a guard stopped the order before it went out, or the terminal did not answer -- app.py marks it no_answer,
        with a retcode of None): the broker refused nothing, and the line says what happened."""
        side = 'BUY' if event.startswith('BUY') else 'SELL'
        kind = 'add' if '_MORE_' in event else 'entry'
        code = _i(d.get('retcode'))
        n = _i(d.get('refusals') if d.get('refusals') is not None else d.get('count'))
        if d.get('no_answer') is True or ('retcode' in d and code is None and not d.get('comment')):
            what = (note or 'MetaTrader 5 gave no answer: the order was not sent (a guard stopped it) or the terminal '
                    'did not answer').rstrip('.')
            return (f'{side} {kind} not filled, and not refused by the broker either: {what}'
                    + (f'; {n} opening orders in a row were not filled' if n and n > 1 else ''))
        if note:
            return f'{side} {kind} refused by the broker: {note}'
        why = RETCODES.get(code, 'no answer' if code is None else 'refused')
        return (f'{side} {kind} refused by the broker: {why}' + (f' ({code})' if code is not None else '')
                + (f", the broker says '{d.get('comment')}'" if d.get('comment') else '')
                + (f'; {n} refusals in a row' if n and n > 1 else ''))

    @_guarded
    def loop_start(self, ctx):
        """The start of the trading loop: who, what design, every effective constant, symbols.json, the state found."""
        c = _Ctx(ctx)
        # the loop's own dict, changed in place (read only): an order of the first poll is an open or an add by it
        if self._is_turtle():
            if isinstance(c.st, dict):
                self._book_ref = c.st                 # the Turtle's book
        elif isinstance(c.state, dict):
            self._state_ref = c.state                 # the basket loop's state
        # (a trace made before the login -- by a TERMINAL_IN_USE event -- had no symbol map yet)
        self.mt5_symbol = (getattr(self.bot, 'symbol_map', None) or {}).get(self.symbol, self.mt5_symbol)
        self._step('loop_start', '_jstate_account', self._jstate_account)
        self._step('loop_start', '_start_facts', self._start_facts, c)
        if self._is_turtle():
            return self._turtle_loop_start(c)
        bot = self.bot
        self._rec('INFO', 'START', f'trading loop started for {self.symbol} ({self.mt5_symbol} at the terminal)', kv={
            'branch': self._cfg('BRANCH'), 'design': self._cfg('DESIGN_NAME'), 'strategy': self._cfg('STRATEGY'),
            'magic': self._cfg('MAGIC'), 'mode': getattr(bot, 'mode', None), 'version': self._cfg('VERSION'),
            'pid': os.getpid(), 'python': sys.version.split()[0], 'out_dir': self.out_dir, 'schema': SCHEMA})
        summary = self._call('design_summary')
        if summary:
            self._rec('INFO', 'CONFIG', 'design: ' + str(summary))
        for name, value in self._constants():
            self._rec('INFO', 'CONFIG', f'{name} = {kv_text(value)}')
        cfg = getattr(bot, 'symbols_config', None) or {}
        sc = c.sym_cfg or {}
        self._rec('INFO', 'CONFIG', f"symbols.json: brake {cfg.get('brake', 0)}, mtqty {cfg.get('mtqty')}, trading window "
                  f"{self._window_text(cfg.get('trading_window'))}, step_up_balance {sc.get('step_up_balance')}, "
                  f"unit_max_limit {sc.get('unit_max_limit')}", kv={'symbols_json': cfg})
        st = c.state or {}
        self._prev.update(basket=_basket_sum(st.get('basket')), lc=_close_sum(st.get('last_close')))
        try:
            path = bot._state_path(self.symbol)
        except Exception:
            path = None
        if c._rebuild_pause:
            self._rec('INFO', 'STATE', 'no state file of this bot: an open basket is rebuilt from the terminal (unit from '
                      'its oldest position, volatility unit from the bars at its open), the pause from the deal history',
                      kv={'path': path})
        else:
            self._rec('INFO', 'STATE', f"state restored: {self._basket_words(st.get('basket'))}; last close: "
                      f"{self._close_words(st.get('last_close'))}", kv={'path': path},
                      data={'basket': st.get('basket'), 'last_close': st.get('last_close')})
        self._rec('INFO', 'START', 'files: ' + ', '.join(os.path.basename(p) for p in (
            self.paths['trace'], self.paths['bars'], self.paths['trades'])) + ', ' + self._files_words(),
            kv={'out_dir': self.out_dir})

    def _files_words(self):
        """The growing files of this bot, as the START line names them."""
        s = self.symbol
        return (f'state/{os.path.basename(self.paths["exits"])}, state/{os.path.basename(self.paths["jstate"])}, '
                f'logs/{s}_<day>.log, logs/{s}_<day>_events.jsonl, logs/{s}_<day>_samples.jsonl (today and '
                f'{self.writer.keep_days} days before it are kept), journal/{s}_<year>.jsonl (kept for good)')

    def _start_facts(self, c):
        """What the journal's start line holds of the configuration: collected when the loop starts, written with
        the first poll's account figures (_start_out)."""
        bot = self.bot
        g = self._cfg
        self._start_line = {
            'at': self._now(),
            'line': {
                'version': g('VERSION'), 'branch': g('BRANCH'), 'partner_branch': g('PARTNER_BRANCH'),
                'design': g('DESIGN_NAME'),
                'design_summary': self._call('design_summary'), 'strategy': g('STRATEGY', 'basket'),
                'symbol': self.symbol, 'mt5_symbol': self.mt5_symbol, 'magic': g('MAGIC'),
                'mode': getattr(bot, 'mode', None), 'pid': os.getpid(), 'python': sys.version.split()[0],
                'schema': SCHEMA, 'out_dir': self.out_dir,
                'constants': {name: value for name, value in self._constants()},
                'symbols_json': getattr(bot, 'symbols_config', None), 'share': g('ACCOUNT_SHARE'),
                'safety_limits': {'default_on': g('SAFETY_DEFAULT_ON'), 'drop_pct': g('SAFETY_DROP_PCT'),
                                  'day_pct': g('SAFETY_DAY_PCT'), 'streak_n': g('SAFETY_STREAK_N')},
            }}

    def _start_out(self, snap, now, good):
        """The journal's start line, once per start of the loop: with the first poll that read the terminal (the
        account's balance, the terminal's build), or a minute after the start when none did."""
        pending = self._start_line
        if pending is None or (not good and 0.0 <= now - pending['at'] < 60.0):
            return
        self._start_line = None
        acct = getattr(self.bot, '_acct', None) or {}
        term = getattr(self.bot, '_terminal', None) or {}
        ac = (snap.get('account') or {}) if good else {}
        self._jline('start', dict(pending['line'], account={
            'login_tail': acct.get('login_tail') or self._own_tail(), 'server': acct.get('server'),
            'currency': acct.get('currency'), 'leverage': acct.get('leverage'),
            'balance': ac.get('balance'), 'equity': ac.get('equity')},
            terminal={'build': term.get('build'), 'ping_ms': term.get('ping_ms')},
            first_poll_t=round(now, 3) if good else None), t=pending['at'], first=True)

    @_guarded
    def poll_skipped(self, kind, problem=None):
        """A poll that decided nothing: the terminal or the account was not right ('guard'), the positions read
        failed ('positions'), or the account read again right after the positions is not this bot's
        ('account_recheck': the positions may be another account's)."""
        t0 = time.perf_counter()
        now = self._now()
        bot = self.bot
        self.polls += 1
        self.skipped += 1
        reason = kind
        if kind == 'guard':
            why = getattr(bot, '_guard_why', None) or (None, None)
            kind, problem = why[0] or 'terminal', why[1] or problem
            reason = kind
        recheck = kind == 'account_recheck'
        if recheck:
            kind = 'account'
        if not problem:
            problem = getattr(bot, '_read_bad', None) if kind != 'account' else getattr(bot, '_account_bad', None)
        problem = problem or 'unknown'
        streak = _i(getattr(bot, '_failed_polls', 0)) or 0
        own = self._own_tail() or 'of its credentials'
        held = (getattr(bot, '_acct', None) or {}).get('login_tail')
        gates = [
            _gate('terminal', 'Terminal connected', kind != 'terminal', problem if kind == 'terminal' else 'answers',
                  'terminal_info() answers, connected to the trade server'),
            _gate('account', "This bot's account", None if kind == 'terminal' else (recheck or kind != 'account'),
                  problem if (kind == 'account' and not recheck) else held,
                  f"the real, hedging account {own}"),
            _gate('positions', 'Positions read', True if recheck else (None if kind != 'positions' else False),
                  'read, not used' if recheck else (problem if kind == 'positions' else None),
                  "positions_get() answers (this bot's magic only)"),
        ]
        if recheck:
            gates.append(_gate('account_recheck', "This bot's account, read again after the positions", False, problem,
                               'the same account right after the positions read',
                               "a switch since the poll's first check: the positions just read may be another account's"))
        decided = _mark_checked(gates)
        if kind == 'terminal':
            after = _i(self._cfg('_RECONNECT_AFTER')) or 5
            at = _f(getattr(bot, '_reconnect_at', None))
            nxt = f'next reconnect attempt at {_hm(at)}' if at else f'the bot reconnects after {after} such polls in a row'
            head = f'Poll skipped, nothing decided: {problem}. {streak} poll(s) in a row; {nxt}.'
            last = getattr(bot, '_init_problem', None)
            fails = _i(getattr(bot, '_reconnects_failed', 0)) or 0
            if fails and last:
                head += f' The last of {fails} failed reconnect attempt(s): {last}.'
        elif recheck:
            head = (f"Poll skipped, nothing decided: the account read again right after the positions is not this bot's "
                    f"({problem}). The positions just read may be another account's, so nothing is booked or sent until "
                    f"MetaTrader 5 holds this bot's account {own} again.")
        elif kind == 'account':
            head = (f"Poll skipped, nothing decided: {problem}. No order is sent until MetaTrader 5 holds this bot's "
                    f"account {own} again.")
        else:
            head = (f'Poll skipped, nothing decided: {problem}. The positions are not known, so the '
                    + ('trade is neither managed nor booked this poll (its stop is checked again on the next good one).'
                       if self._is_turtle() else 'basket is neither managed nor booked this poll.'))
        dec = {'action': 'SKIPPED', 'reason': reason, 'side': None, 'headline': head, 'gates': gates,
               'blocked_by': decided, 'signal': None, 'orders': self._take_orders()}
        health = self._health(None, now, skip=(kind, problem))
        prev = self._last_snapshot or {}
        snap = self._base(now)
        # the last good poll's blocks, marked as such: the market is not known this poll (the quote is the last one
        # read) and the votes were not computed this poll; the sizing, the safety's view and what else is on the
        # account are the last good poll's too (nothing was read or counted on this one)
        market, basket = prev.get('market'), prev.get('basket')
        if isinstance(market, dict):
            market = dict(market, status='UNKNOWN', message="the terminal was not read this poll: the quote is the last "
                                                            "good poll's")
        if isinstance(basket, dict):
            basket = dict(basket, fresh=False)
        snap.update(stale=True, stale_since_utc=_iso(self._last_poll_t), health=health,
                    account=prev.get('account'), sizing=prev.get('sizing'), safety=prev.get('safety'),
                    open_hold=None, foreign=self._foreign_skipped(prev.get('foreign')), market=market, decision=dec,
                    basket=basket, turtle=prev.get('turtle'))
        S = functools.partial(self._step, 'poll_skipped')
        S('_decision_line', self._decision_line, dec, now)
        S('_write_trace', self._write_trace, snap, dec, now, force=True)
        S('_after_poll', self._after_poll, snap, now, False)
        S('_heartbeat', self._heartbeat, dec, snap, now)
        self._flush()
        S('_jstate_save', self._jstate_save, now)
        self.cost_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        self.costs.append(self.cost_ms)

    @_guarded
    def poll(self, ctx):
        """The end of a poll that read the terminal: its locals (see app.py process_symbol)."""
        t0 = time.perf_counter()
        try:
            self._poll(_Ctx(ctx))
        finally:
            ms = (time.perf_counter() - t0) * 1000.0
            self.cost_ms = round(ms, 3)
            self.costs.append(ms)

    # ── one poll ──
    def _poll(self, c):
        """Every step on its own (_step): one that raises is an ERROR line and the others still run -- the trace file,
        the bars, the trades, the heartbeat and the bookkeeping. A step the decision needs that fails gives the
        decision TRACE_ERROR."""
        if self._is_turtle():
            return self._poll_turtle(c)
        now = self._now()
        self.polls += 1
        if isinstance(c.state, dict):
            self._state_ref = c.state
        orders = self._take_orders()
        S = functools.partial(self._step, 'poll')
        digits = S('_get_digits', self._get_digits)
        digits = None if digits is _FAILED else digits
        snap = self._base(now)
        for key, fn, args in (('health', self._health, (c, now)), ('account', self._account, (c,)),
                              ('market', self._market, (c, now, digits))):
            v = S('_' + key, fn, *args)
            snap[key] = None if v is _FAILED else v
        S('_handed_over', self._handed_over, c, snap)
        bk = S('_basket_section', self._basket_section, c, now, digits, orders)
        snap['basket'] = None if bk is _FAILED else bk
        snap['turtle'] = None
        dec = _FAILED if bk is _FAILED else S('_decide', self._decide, c, snap, orders, now, digits)
        failed = dec is _FAILED
        if failed:
            dec = self._failed_decision(orders, '_basket_section' if bk is _FAILED else '_decide')
        snap['decision'] = dec
        if not failed:
            self._transitions_step(self._transitions, self._keep_basket, c, snap, dec, orders, now, digits)
        S('_decision_line', self._decision_line, dec, now)
        self._last_snapshot = snap
        S('_write_trace', self._write_trace, snap, dec, now)
        S('_track_trade', self._track_trade, c, snap, dec, orders, now)
        S('_after_poll', self._after_poll, snap, now, True)
        S('_bars', self._bars, c, now, digits)
        S('_trades', self._trades, c, snap, now, digits)
        S('_heartbeat', self._heartbeat, dec, snap, now)
        self._prev['positions'] = {'BUY': _i(c._buy_ct) or 0, 'SELL': _i(c._sell_ct) or 0}
        self._last_poll_t = now
        self._flush()
        S('_jstate_save', self._jstate_save, now)

    def _after_poll(self, snap, now, good):
        """What every poll -- one that read the terminal (good) or a skipped one -- adds to the files that grow: the
        journal's start line and its lines about problems and the day that ended, the minute's sample; and, at the
        start, at a new UTC day and once an hour, the old temp files and old daily files that go. Each on its own:
        one that fails leaves the others."""
        S = functools.partial(self._step, 'poll' if good else 'poll_skipped')
        S('_start_out', self._start_out, snap, now, good)
        S('_issues', self._issues, snap, now, good)
        if good:
            S('_day_line', self._day_line, snap, now)
        S('_sample', self._sample, snap, now, good)
        S('_jline_runs', self._jline_runs, now)
        S('_tidy', self._tidy, now)

    def _take_orders(self):
        orders, self._orders = self._orders, []
        return orders

    def _foreign_skipped(self, last):
        """The `foreign` block of a skipped poll: the positions that are not this bot's as the last good poll read
        them (none were read on this one), and the old bot as the bot's flag says NOW -- app.py looks at the old
        bot's files on every pass of its loop, a refused one too (spec 6.2 C: while the account is refused because
        an old bot on this MetaTrader 5 switched it, the banner must say to stop that old bot). Its age only while
        it is alive. Never raises."""
        out = dict(last) if isinstance(last, dict) else None
        try:
            alive = getattr(self.bot, '_old_bot_alive_flag', False) is True
            same = False
            if alive:
                try:
                    same = bool(self.bot._old_bot_same_terminal())
                except Exception:
                    same = False
            if out is None and not alive:
                return None
            out = out if out is not None else {'positions': None, 'examples': None}
            out.update(old_bot_age_s=_f(getattr(self.bot, '_old_bot_age_s', None)) if alive else None,
                       old_bot_same_terminal=same)
            return self._copy(out)
        except Exception:
            return last

    def _base(self, now):
        return {'schema': SCHEMA, 'branch': self._cfg('BRANCH'), 'mode': getattr(self.bot, 'mode', None),
                'version': self._cfg('VERSION'), 'design': self._cfg('DESIGN_NAME'),
                'strategy': self._cfg('STRATEGY', 'basket'), 'symbol': self.symbol, 'mt5_symbol': self.mt5_symbol,
                'magic': self._cfg('MAGIC'), 't': round(now, 3), 'time_utc': _iso(now), 'poll': self.polls,
                'stale': False, 'sizing': None, 'safety': None, 'open_hold': None, 'foreign': None}

    def _handed_over(self, c, snap):
        """What app.py hands over ready-made, as it is (a copy; a full account number, should one ever be in it,
        as its tail): how the unit was sized (_sizing), the safety's view (_safety), an opening order this poll held
        back (_open_hold) and what else is on the symbol in this account (_foreign). A name app.py does not have
        (yet) reads None and the key stays null."""
        for key, name in (('sizing', '_sizing'), ('safety', '_safety'), ('open_hold', '_open_hold'),
                          ('foreign', '_foreign')):
            v = getattr(c, name)
            snap[key] = self._copy(v) if isinstance(v, dict) else None
        if snap['foreign'] is None:
            # (the poll made no _foreign: the positions read's own note of what is not this bot's, and the bot's
            # flag of an old bot on this server -- its age only while it is alive: the banner reads 'not None')
            lf = getattr(getattr(self.bot, 'position_helper', None), 'last_foreign', None)
            lf = lf if isinstance(lf, dict) else None
            alive = getattr(self.bot, '_old_bot_alive_flag', False) is True
            same = None
            if alive:
                try:
                    same = bool(self.bot._old_bot_same_terminal())
                except Exception:
                    same = None
            if lf is not None or alive:
                snap['foreign'] = self._copy({
                    'positions': _i(lf.get('count')) if lf is not None else None,
                    'examples': lf.get('examples') if lf is not None else None,
                    'old_bot_age_s': _f(getattr(self.bot, '_old_bot_age_s', None)) if alive else None,
                    'old_bot_same_terminal': same})
        ac = snap.get('account')
        sf = snap.get('safety')
        if isinstance(ac, dict) and isinstance(sf, dict):
            # booked today by both bots of the account: the balance against the one the UTC day began with (the
            # safety keeps it: changed by deposits and withdrawals, not by an unblock)
            start = _f((sf.get('day') or {}).get('start_balance'))
            bal = _f(ac.get('balance'))
            ac['day_realised'] = round(bal - start, 2) if (bal is not None and start is not None) else None

    def _get_digits(self):
        """The symbol's price digits: from the bot's cache, else symbol_info() once (retried every 60 s if unknown)."""
        if self._digits is not None:
            return self._digits
        cache = getattr(self.bot, '_digits', None) or {}
        if self.mt5_symbol in cache:
            self._digits = _i(cache[self.mt5_symbol])
            return self._digits
        now = self._now()
        if self._digits_t is not None and now - self._digits_t < 60.0:
            return None
        self._digits_t = now
        with self.bot.mt5_lock:
            info = self.app.mt5.symbol_info(self.mt5_symbol)
        self._digits = _i(getattr(info, 'digits', None)) if info is not None else None
        return self._digits

    def _health(self, c, now, skip=None, live=None, tick=None):
        """live / tick: the Turtle's (its loop has no candle flags); None = the basket poll's."""
        bot = self.bot
        # what the terminal said last about its account and about itself (app.py keeps both; tails only)
        acct = getattr(bot, '_acct', None) or {}
        term = getattr(bot, '_terminal', None) or {}
        mt5 = getattr(self.app, 'mt5', None)
        tm = {getattr(mt5, 'ACCOUNT_TRADE_MODE_DEMO', 0): 'demo', getattr(mt5, 'ACCOUNT_TRADE_MODE_CONTEST', 1): 'contest',
              getattr(mt5, 'ACCOUNT_TRADE_MODE_REAL', 2): 'real'}
        mm = {getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_NETTING', 0): 'netting',
              getattr(mt5, 'ACCOUNT_MARGIN_MODE_EXCHANGE', 1): 'exchange',
              getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING', 2): 'hedging'}
        # trading switched off somewhere (a state, read every poll: the dashboard's banner is drawn from it). What the
        # terminal does not report counts as no problem.
        off = [name for name, bad in (('algo_trading_off', term.get('trade_allowed') is False),
                                      ('python_api_disabled', term.get('tradeapi_disabled') is True),
                                      ('account_trade_disabled', acct.get('trade_allowed') is False),
                                      ('account_expert_disabled', acct.get('trade_expert') is False)) if bad]
        h = {
            'connected': True, 'terminal_problem': None,
            'account_ok': getattr(bot, '_account_bad', None) is None,
            'account_problem': getattr(bot, '_account_bad', None),
            'login_tail': acct.get('login_tail'), 'own_login_tail': self._own_tail(),
            'trade_mode': acct.get('trade_mode'), 'trade_mode_name': tm.get(acct.get('trade_mode')),
            'margin_mode': acct.get('margin_mode'), 'margin_mode_name': mm.get(acct.get('margin_mode')),
            'trading_not_allowed': off, 'disk_low': bool(self.writer.disk_low),
            'terminal_build': term.get('build'), 'ping_ms': _f(term.get('ping_ms')),
            'market_live': None, 'market_status': None, 'minutes_since_activity': None, 'last_tick_age_s': None,
            'loop_ms': None, 'trace_ms': self.cost_ms,
            'reconnects': max(self.reconnects, _i(getattr(bot, '_reconnects_done', 0)) or 0),
            'errors_1h': self._errors_1h(now), 'skipped_polls': self.skipped,
            'failed_streak': _i(getattr(bot, '_failed_polls', 0)),
            'poll_gap_s': _f(now - self._last_poll_t, 2) if self._last_poll_t is not None else None,
            'started_utc': _iso(self.started_at), 'uptime_s': round(now - self.started_at, 1),
            'log_write_failures': self.writer.failures,
        }
        # the bot's reconnect after a lost terminal (app.py _poll_failed / _try_reconnect), read only: the failed attempts
        # since the connection was lost, the next one, the outage so far, why the last start-up / reconnect failed
        lost_at = _f(getattr(bot, '_ipc_lost_at', None))
        nxt = _f(getattr(bot, '_reconnect_at', None))
        why = getattr(bot, '_init_problem', None)
        h.update(reconnect_failed_attempts=_i(getattr(bot, '_reconnects_failed', 0)) or 0,
                 next_reconnect_t=nxt, next_reconnect_utc=_iso(nxt),
                 outage_s=_f(now - lost_at, 1) if lost_at is not None else None,
                 connect_problem=str(why) if why else None,
                 terminal_in_use=bool(why) and str(why).startswith('TERMINAL_IN_USE'))
        if skip is not None:
            kind, problem = skip
            if kind == 'terminal':
                h.update(connected=False, terminal_problem=problem)
            elif kind == 'account':
                h.update(account_ok=False, account_problem=problem)
            else:
                h['positions_problem'] = problem
            return h
        ms = c.market_status or {}
        tick = c._tick if tick is None else tick
        tick_t = (getattr(tick, 'time_msc', 0) or 0) / 1000.0 or _f(getattr(tick, 'time', None)) if tick is not None else None
        live = bool(c.has_candle_data and c.candle_is_fresh) if live is None else bool(live)
        h.update(market_live=live, market_status=ms.get('status'),
                 minutes_since_activity=_f(ms.get('minutes_since_last'), 2),
                 last_tick_age_s=_f(now - tick_t, 2) if tick_t else None, loop_ms=_f(c.iteration_ms, 1))
        return h

    def _account(self, c):
        """The real account the two bots of an account share, and this bot's part in it. Real numbers only."""
        ai = c.account_info or {}
        acct = getattr(self.bot, '_acct', None) or {}
        sz = c._sizing if isinstance(c._sizing, dict) else {}
        mtqty = _f(c.mtqty) or 0.01
        units = _i(c.units) or 1
        open_pl = sum((_f((p or {}).get('total_profit')) or 0.0) for p in (c.buy_positions, c.sell_positions))
        step, top = _f(c.step_up_balance), _i(c.max_limit)
        share = _f(sz.get('share')) if sz.get('share') is not None else _f(self._cfg('ACCOUNT_SHARE'))
        # the ACCOUNT balance from which a new trade gets one more unit: units x step / share (None at the cap)
        nxt = None
        if step and step > 0 and top and units < top and share and share > 0:
            nxt = round(units * step / share, 2)
        return {
            'login_tail': acct.get('login_tail'), 'server': acct.get('server'), 'currency': acct.get('currency'),
            'leverage': acct.get('leverage'), 'trade_allowed': acct.get('trade_allowed'),
            'trade_expert': acct.get('trade_expert'),
            'balance': _f(ai.get('balance')), 'equity': _f(ai.get('equity')), 'margin': _f(ai.get('margin')),
            'margin_free': _f(ai.get('margin_free')), 'margin_level': _f(ai.get('margin_level')),
            'account_profit': _f(ai.get('profit')),
            'floating_account': _f(ai.get('profit')), 'floating_own': round(open_pl, 2),
            'own_open_pl': round(open_pl, 2),
            # this bot's closed trades since its live start, from the last read of the deal history (trades.json)
            'own_closed_pl': self._own_closed,
            'day_realised': None,                # (set from the safety's view: _handed_over)
            'units': units, 'lot': round(units * mtqty, 2), 'mtqty': mtqty, 'share': share,
            'step_up_balance': step, 'unit_max_limit': top,
            'next_unit_at': nxt,
            'unit_rule': (f'unit = floor({share:g} x account balance / {step:g}) + 1, at most {top}, re-derived only '
                          f'while flat' if (step and share) else 'unit 1'),
        }

    def _market(self, c, now, digits):
        tick = c._tick
        bid = _f(getattr(tick, 'bid', None)) if tick is not None else None
        ask = _f(getattr(tick, 'ask', None)) if tick is not None else None
        tick_t = None
        if tick is not None:
            tick_t = (getattr(tick, 'time_msc', 0) or 0) / 1000.0 or _f(getattr(tick, 'time', None))
        ms = c.market_status or {}
        st = c.server_time
        return {'bid': bid, 'ask': ask, 'spread': _f(ask - bid, 6) if bid is not None and ask is not None else None,
                'tick_t': tick_t, 'tick_utc': _iso(tick_t), 'digits': digits,
                'server_time_utc': _iso(_epoch(st)), 'status': ms.get('status'),
                'minutes_since_activity': _f(ms.get('minutes_since_last'), 2),
                'lookback_minutes': ms.get('lookback_minutes'), 'message': ms.get('message'),
                'in_window': c.in_window, 'brake': c.brake, 'brake_manual': c.brake_manual,
                'window': self._window_text(c.trading_window_cfg)}

    def _window_text(self, w):
        if not w or not w.get('enabled', False):
            return 'off (always open)'
        return (f"{w.get('start_day', 'Monday')} {w.get('start_time', '00:00')} - {w.get('end_day', 'Saturday')} "
                f"{w.get('end_time', '00:00')} server time")

    def _levels(self, vol_unit, usd_pp):
        try:
            return self._call('basket_levels', vol_unit, usd_pp) or {}
        except Exception:
            return {}

    def _ladder_tiers(self):
        try:
            return list(self.app.Strategy.ladder_tiers())
        except Exception:
            return []

    # ── the basket strategy's section ──
    def _basket_section(self, c, now, digits, orders):
        a = c.analysis_data or {}
        st = c.state or {}
        usd_pp = _f(c._usd_per_price)
        mtqty = _f(c.mtqty) or 0.01
        units = _i(c.units) or 1
        ow = dict(self._cfg('OPEN_SCORE_WEIGHTS') or {})
        fw = dict(self._cfg('FORCE_CLOSE_SCORE_WEIGHTS') or {})
        fc_on = bool(self._cfg('FORCE_CLOSE_ENABLED', True))
        es, eas = _f(self._cfg('ENTRY_S')), _f(self._cfg('ENTRY_AGREE_S'))
        open_score, fc = _f(a.get('open_score')), _f(a.get('fc_score'))
        wants = None
        if open_score is not None and es is not None:
            wants = 'BUY' if open_score >= es else 'SELL' if open_score <= -es else None
        bid = _f(getattr(c._tick, 'bid', None)) if c._tick is not None else None
        ask = _f(getattr(c._tick, 'ask', None)) if c._tick is not None else None
        return {
            'fresh': bool(c.has_candle_data and c.candle_is_fresh),
            'weights': {'open': ow, 'agreement': fw},
            'votes': self._votes(c, a, ow, fw, fc_on),
            'open_score': open_score, 'entry_s': es, 'open_range': 2 * sum(abs(float(w)) for w in ow.values()),
            'open_wants': wants,
            'fc_score': fc, 'entry_agree_s': eas, 'fc_range': 2 * sum(abs(float(w)) for w in fw.values()),
            'force_close_enabled': fc_on, 'force_close_s': _f(self._cfg('FORCE_CLOSE_S')),
            'ladder_s': _f(self._cfg('LADDER_S')), 'buy_add_ok': a.get('buy_add_ok'), 'sell_add_ok': a.get('sell_add_ok'),
            'entry_direction': a.get('entry_direction'), 'entry_chop_block': a.get('entry_chop_block'),
            'entry_allowed': a.get('entry_allowed'), 'exit_reason': a.get('exit_reason'),
            'trend': self._trend(c, a),
            'vol': self._vol(c, a, usd_pp),
            'usd_per_price': usd_pp, 'contract_size': _f(usd_pp / mtqty, 6) if usd_pp and mtqty else None,
            'new_basket': self._new_levels(a, usd_pp, units, mtqty, digits, bid, ask),
            'pause': self._pause(st, a, now),
            'rsi': {_tf_key(k): _f(v, 2) for k, v in (a.get('rsi_mtf') or {}).items()},
            'no_data': list(c._no_data or []), 'short_history': list(c._short or []),
            'fill_pending': bool(c._fill_pending),
            'open': self._open_view(c, a, now, digits, usd_pp, mtqty, orders),
            'ladder_tiers': self._ladder_tiers(), 'ladder_trigger': self._cfg('LADDER_TRIGGER'),
        }

    def _votes(self, c, a, ow, fw, fc_on):
        slopes = a.get('slopes') or {}
        rg, mg = a.get('rsi_graphs') or {}, a.get('macd_graphs') or {}
        rsi_mtf = a.get('rsi_mtf') or {}
        frames, sigs = c._frames or {}, c._signals or {}
        tiers = self._ladder_tiers() if self._cfg('LADDER_TRIGGER') == 'macd_turn' else []
        out = {}
        for tf in dict.fromkeys([*ow, *fw, *slopes]):
            s = slopes.get(tf)
            if s is None:
                continue
            ri, mi = s.get('rsi') or {}, s.get('macd') or {}
            r, m = _sign(ri.get('sign')), _sign(mi.get('sign'))
            rr, mm, filled = r, m, None
            if r == 0 and m != 0:
                rr, filled = m, 'rsi'
            elif m == 0 and r != 0:
                mm, filled = r, 'macd'
            w_o, w_f = _f(ow.get(tf)), _f(fw.get(tf))
            roles = []
            if w_o:
                roles.append('open')
            if w_f:
                roles.append('agreement + force-close' if fc_on else 'agreement')
            if tf in tiers:
                roles.append('ladder')
            gr, gm = rg.get(tf) or {}, mg.get(tf) or {}
            n = len(gr.get('series') or [])
            fr = frames.get(_TF + tf)
            sig = _f(sigs.get(_TF + tf))
            out[tf] = {
                'roles': roles,
                'rsi': {'vote': r, 'now': _f(gr.get('current'), 2) if gr else _f(rsi_mtf.get(_TF + tf), 2),
                        'pivot': _f(ri.get('value'), 2), 'pivot_side': ri.get('side'), 'bars_ago': _i(ri.get('bars_ago')),
                        'slope': _f(ri.get('slope'), 4), 'bands': gr.get('bands'), 'series': gr.get('series')},
                'macd': {'vote': m, 'now': _f(gm.get('current'), 6), 'pivot': _f(mi.get('value'), 6),
                         'pivot_side': mi.get('side'), 'bars_ago': _i(mi.get('bars_ago')), 'slope': _f(mi.get('slope'), 6),
                         'signal_forming': sig,
                         'side_rule': (None if sig is None else 'high' if sig > 0 else 'low' if sig < 0 else 'none'),
                         'series': gm.get('series')},
                'open_weight': w_o, 'open_contrib': (w_o * (rr + mm)) if w_o else None,
                'grey_filled': filled if w_o else None,
                'fc_weight': w_f, 'fc_contrib': (w_f * (r + m)) if w_f else None,
                't': _frame_times(fr, n) if (fr is not None and n) else None,
            }
        return out

    def _trend(self, c, a):
        tf = self._cfg('TREND_TF')
        if tf is None:
            return {'on': False, 'tf': None, 'text': 'off'}
        k = _tf_key(tf)
        fr = (c._frames or {}).get(_TF + k)
        bar_t = None
        if fr is not None and len(fr) >= 2:
            bar_t = _epoch(fr['time'].iloc[-2])
        sig, sign = _f(a.get('trend_signal')), a.get('trend')
        text = 'up' if sign == 1 else 'down' if sign == -1 else ('flat' if sig is not None else 'unknown')
        return {'on': True, 'tf': k, 'signal': sig, 'sign': sign, 'text': text,
                'allows': 'BUY' if sign == 1 else 'SELL' if sign == -1 else None,
                'bar_t': bar_t, 'bar_utc': _iso(bar_t),
                'rule': (f"the MACD({self._cfg('MACD_FAST')},{self._cfg('MACD_SLOW')},{self._cfg('MACD_SIGNAL')}) signal "
                         f'line of the last closed {k} bar: > 0 lets only buys in, < 0 only sells, 0 neither')}

    def _vol(self, c, a, usd_pp):
        tf = self._cfg('VOL_TF')
        if tf is None:
            return {'on': False, 'tf': None}
        k = _tf_key(tf)
        raw = _f(a.get('vol_unit_now'))
        lv = self._levels(raw, usd_pp) if raw else {}
        capped = _f(lv.get('vol_unit'))
        cap = _f(self._cfg('VOL_CAP_USD_PER_UNIT')) or 0.0
        fr = (c._frames or {}).get(_TF + k)
        short = k in (c._short or [])
        n = self._cfg('VOL_LEN')
        return {'on': True, 'tf': k, 'len': n, 'raw': raw, 'capped': capped, 'cap_usd_per_unit': cap,
                'cap_binds': bool(cap > 0 and raw and usd_pp and raw * usd_pp > cap),
                'bars_used': (len(fr) - 1) if fr is not None else None, 'min_bars': self._cfg('_MIN_CLOSED_BARS'),
                'known': bool(raw and raw > 0 and not short), 'short_history': short,
                'usd_per_unit': _f(capped * usd_pp, 4) if capped and usd_pp else None,
                'rule': (f'EWMA(1/{n}) of |change of close| of the closed {k} bars (the forming bar left out), '
                         'fixed for a basket when it opens')}

    def _new_levels(self, a, usd_pp, units, mtqty, digits, bid, ask):
        """The distances a basket opened now would get (fixed at its open), and the prices they mean."""
        lv = self._levels(_f(a.get('vol_unit_now')), usd_pp)
        tgt_u, sl_u = _f(lv.get('target_usd_per_unit')), _f(lv.get('stop_usd_per_unit'))
        tgt_px = tgt_u / usd_pp if (tgt_u is not None and usd_pp) else None
        sl_px = sl_u / usd_pp if (sl_u is not None and usd_pp) else None
        bs_px = None
        if self._call('design_has_stop'):
            bs_px = _f(self._call('backstop_distance', sl_u, usd_pp))
        d = 6 if digits is None else digits

        def at(entry, k):
            if entry is None:
                return None
            return {'entry': entry,
                    'target': round(entry + k * tgt_px, d) if tgt_px is not None else None,
                    'stop': round(entry - k * sl_px, d) if sl_px is not None else None,
                    'backstop': round(entry - k * bs_px, d) if bs_px is not None else None,
                    'judged_on': 'bid' if k > 0 else 'ask'}
        return {'units': units, 'lots': round(units * mtqty, 2),
                'target_usd_per_unit': tgt_u, 'stop_usd_per_unit': sl_u,
                'target_usd': _f(tgt_u * units, 2) if tgt_u is not None else None,
                'stop_usd': _f(sl_u * units, 2) if sl_u is not None else None,
                'target_px': tgt_px, 'stop_px': sl_px, 'gap_px': _f(lv.get('gap_px')), 'backstop_px': bs_px,
                'vol_unit': _f(lv.get('vol_unit')), 'buy': at(ask, 1), 'sell': at(bid, -1)}

    def _pause(self, st, a, now):
        lc = st.get('last_close') or {}
        t = _f(lc.get('time'))
        lost = bool(lc.get('lost'))
        loss_cd = _f(self._cfg('LOSS_COOLDOWN_S')) or 0.0
        base = _f(self._cfg('REENTRY_COOLDOWN_SECONDS')) or 0.0
        length = loss_cd if (lost and loss_cd > 0) else base
        until = t + length if t else None
        left = max(0.0, until - now) if until else 0.0
        why = None
        if t:
            why = 'after a losing basket' if (lost and loss_cd > 0) else 'after a close'
        last = None
        if lc:
            last = {'t': t, 'utc': _iso(t), 'pnl': _f(lc.get('pnl')), 'lost': lc.get('lost'), 'reason': lc.get('reason'),
                    'side': lc.get('side'), 'resolved': lc.get('resolved'), 'source': lc.get('source'),
                    'ids': lc.get('ids')}
        return {'active': left > 0, 'left_s': round(left, 1), 'until': until, 'until_utc': _iso(until),
                'length_s': length, 'why': why, 'pause_s': base, 'loss_pause_s': loss_cd, 'last_close': last}

    def _open_view(self, c, a, now, digits, usd_pp, mtqty, orders):
        """The basket this poll held (or opened): legs, P/L, its fixed stop / target in USD and as prices, the backstops,
        the ladder. None when flat."""
        st = c.state or {}
        post, pre = st.get('basket'), c.basket
        nb, ns = _i(c._buy_ct) or 0, _i(c._sell_ct) or 0
        if nb and ns:
            return {'both_sides': True, 'buy_count': nb, 'sell_count': ns}
        if nb or ns:
            side = 'BUY' if nb else 'SELL'
            pos = (c.buy_positions if nb else c.sell_positions) or {}
            plist = sorted(pos.get('positions') or [], key=lambda p: (_pos_time(p) or 0.0, _i(getattr(p, 'ticket', 0)) or 0))
            b = pre if (pre and pre.get('side') == side) else (post if (post and post.get('side') == side) else None)
            legs = [self._leg(p, digits) for p in plist]
            v = self._basket_view(b, legs, side, _f(pos.get('total_profit')), c, a, now, digits, usd_pp, mtqty)
            sig = _sig_name(c.buy_signal if side == 'BUY' else c.sell_signal)
            v['closing'] = sig == f'CLOSE_{side}'
            v['closed_now'] = v['closing'] and (post is None or post.get('side') != side)
            return v
        if post is not None:                 # opened this poll, or filled and not listed by the terminal yet
            side = post.get('side')
            legs = []
            for o in orders:
                if o['done'] and o['kind'] in ('open', 'add') and o['side'] == side:
                    legs.append({'ticket': o['order'], 'id': o['order'], 'open_t': o['t'], 'open_utc': _iso(o['t']),
                                 'price': o['result_price'] or o['price'], 'lots': o['result_volume'] or o['volume'],
                                 'profit': None, 'swap': None, 'backstop': o['sl'] or None, 'tp': o['tp'] or None,
                                 'listed': False})
            v = self._basket_view(post, legs, side, None, c, a, now, digits, usd_pp, mtqty)
            v['listed'] = False
            v['opened_now'] = bool(legs)
            v['closing'] = False
            v['closed_now'] = False
            return v
        return None

    def _leg(self, p, digits):
        t = _pos_time(p)
        return {'ticket': _i(getattr(p, 'ticket', None)), 'id': _pos_id(p), 'open_t': t, 'open_utc': _iso(t),
                'price': _f(getattr(p, 'price_open', None)), 'lots': _f(getattr(p, 'volume', None)),
                'profit': _f(getattr(p, 'profit', None)), 'swap': _f(getattr(p, 'swap', None)),
                'backstop': _f(getattr(p, 'sl', None)) or None, 'tp': _f(getattr(p, 'tp', None)) or None,
                'magic': getattr(p, 'magic', None), 'comment': getattr(p, 'comment', None), 'listed': True}

    def _basket_view(self, b, legs, side, pnl, c, a, now, digits, usd_pp, mtqty):
        b = b or {}
        units = _i(b.get('units')) or _i(c.units) or 1
        tgt_u, sl_u = _f(b.get('target_usd_per_unit')), _f(b.get('stop_usd_per_unit'))
        tgt = tgt_u * units if tgt_u is not None else None
        sl = sl_u * units if sl_u is not None else None
        lots = sum(l['lots'] or 0.0 for l in legs)
        avg = (sum((l['price'] or 0.0) * (l['lots'] or 0.0) for l in legs) / lots) if lots else None
        k = (lots / mtqty) * usd_pp if (lots and mtqty and usd_pp) else None      # USD per 1.0 move of the basket
        tick = c._tick
        bid = _f(getattr(tick, 'bid', None)) if tick is not None else None
        ask = _f(getattr(tick, 'ask', None)) if tick is not None else None
        buy = side == 'BUY'
        d = 6 if digits is None else digits
        stop_px = target_px = None
        if avg is not None and k:
            if sl is not None:
                stop_px = round(avg - sl / k if buy else avg + sl / k, d)
            if tgt is not None:
                target_px = round(avg + tgt / k if buy else avg - tgt / k, d)
        first_t = _f(b.get('first_time')) or (legs[0]['open_t'] if legs else None)
        opened = _f(b.get('opened_at'))
        return {
            'side': side, 'units': units, 'lots': round(lots, 2), 'legs': legs,
            'avg_price': _f(avg, d) if avg is not None else None, 'pnl': pnl,
            'judged_on': 'bid' if buy else 'ask', 'price_now': bid if buy else ask,
            'stop_usd': _f(sl, 2) if sl is not None else None, 'target_usd': _f(tgt, 2) if tgt is not None else None,
            'stop_usd_per_unit': sl_u, 'target_usd_per_unit': tgt_u,
            'stop_price': stop_px, 'target_price': target_px,
            'to_stop_usd': _f(pnl + sl, 2) if (pnl is not None and sl is not None) else None,
            'to_target_usd': _f(tgt - pnl, 2) if (pnl is not None and tgt is not None) else None,
            'backstop_prices': [l['backstop'] for l in legs if l.get('backstop')],
            'vol_unit': _f(b.get('vol_unit')), 'vol_unit_raw': _f(b.get('vol_unit_raw')), 'vol_source': b.get('vol_source'),
            'gap_px': _f(b.get('gap_px')), 'ladder': self._ladder_view(b, legs, side, a, units, mtqty, bid, ask),
            'opened_at': opened, 'opened_utc': _iso(opened), 'opened_by': b.get('opened_by'),
            'first_t': first_t, 'first_utc': _iso(first_t),
            'age_s': _f(now - first_t, 1) if first_t else (_f(now - opened, 1) if opened else None),
            'levels_pending': b.get('levels_pending'), 'close_pending': b.get('close_pending'), 'ids': b.get('ids'),
            'outside_ids': b.get('outside_ids'),
            'unlisted': self._unlisted_view(b, legs, now, d),
            'known_to_bot': bool(b),
        }

    def _unlisted_view(self, b, legs, now, digits):
        """(v3.9.2-demo.5) The basket's legs recorded from their order's answer that the terminal has not listed yet
        (app.py _record_fill: a leg of the basket from its fill, kept _PENDING_FILL_S). The P/L, stop and target above
        are those of the listed legs, as the bot's own test reads them."""
        listed = {l.get('id') for l in legs if l.get('listed')}
        wait = _f(self._cfg('_PENDING_FILL_S')) or 10.0
        out = []
        for u in (b or {}).get('unlisted') or []:
            pid, t = _i((u or {}).get('id')), _f((u or {}).get('time'))
            if pid is None or pid in listed:
                continue
            o = self._fills.get(pid) or {}
            out.append({'id': pid, 'fill_t': t, 'fill_utc': _iso(t), 'age_s': _f(now - t, 1) if t is not None else None,
                        'wait_s': wait, 'price': _f(o.get('result_price') or o.get('price'), digits),
                        'lots': _f(o.get('result_volume') or o.get('volume')), 'kind': o.get('kind')})
        return out

    def _ladder_view(self, b, legs, side, a, units, mtqty, bid, ask):
        tiers = self._ladder_tiers()
        trigger = self._cfg('LADDER_TRIGGER')
        count = len(legs)
        if not tiers:
            return {'on': False, 'note': f"no adds in this design (MAX_ADDS {self._cfg('MAX_ADDS')})"}
        out = {'on': True, 'tiers': tiers, 'trigger': trigger, 'count': count, 'armed': bool(b.get('ladder_armed')),
               'gap_px': _f(b.get('gap_px')) or 0.0}
        if count < 1 or count > len(tiers):
            out.update(exhausted=count > len(tiers), tier_tf=None, next_add_price=None)
            return out
        tf = tiers[count - 1]
        s = (a.get('slopes') or {}).get(tf) or {}
        vote = _sign(((s.get('macd') or {}).get('sign')))
        rsi = _f((a.get('rsi_mtf') or {}).get(_TF + tf))
        buy = side == 'BUY'
        last_fill = legs[-1]['price'] if legs else None
        gap = out['gap_px']
        nxt = None
        if gap > 0 and last_fill is not None:
            nxt = round(last_fill - gap if buy else last_fill + gap, 6 if self._digits is None else self._digits)
        try:
            lots = self.bot.strategy.next_add_volume(sum(l['lots'] or 0 for l in legs), count, units, mtqty)
        except Exception:
            lots = None
        out.update(exhausted=False, tier_tf=tf, vote=vote, rsi=rsi,
                   rsi_level=self._cfg('RSI_OVERSOLD') if buy else self._cfg('RSI_OVERBOUGHT'),
                   add_ok=a.get('buy_add_ok') if buy else a.get('sell_add_ok'), last_fill=last_fill,
                   next_add_price=nxt, judged_on='ask' if buy else 'bid', price_now=ask if buy else bid,
                   next_add_lots=_f(lots))
        return out

    # ── the decision: action, headline, gates ──
    def _first_gates(self, nb, ns):
        """The three gates every poll that read the terminal has passed: the terminal, this bot's account, the
        positions."""
        held = (getattr(self.bot, '_acct', None) or {}).get('login_tail')
        own = self._own_tail() or 'of its credentials'
        return [_gate('terminal', 'Terminal connected', True, 'answers', 'terminal_info() answers, connected to the trade server'),
                _gate('account', "This bot's account", True, held, f'the real, hedging account {own}'),
                _gate('positions', 'Positions read', True, f'{nb} buy, {ns} sell', "positions_get() answers (this bot's magic only)")]

    # An opening order the bot wanted on this poll and did not send (app.py _open_held, the poll local _open_hold:
    # the last test before the send): why, in the owner's words.
    _HOLD_WORDS = {
        'safety': 'the safety has blocked new trades (the bar at the top of the page says why)',
        'safety_checking': ('the safety is checking a change of the account balance that would reach a limit (up to '
                            '1 minute)'),
        'refused_backoff': 'the broker refused the last orders, so the next one is tried later',
        'balance_unknown': ('the account balance is not known on this poll, or is not above 0, so the size of a new '
                            'trade cannot be worked out'),
        'old_bot': 'an old bot is running on this server and uses the same MetaTrader 5',
    }

    @staticmethod
    def _hold(c, kinds=None):
        """The poll's _open_hold when it holds back an order of one of `kinds` ('entry', 'add', 'pyramid'; None =
        any), else None."""
        h = c._open_hold
        if not isinstance(h, dict) or not h.get('why'):
            return None
        if kinds is not None and h.get('kind') is not None and h.get('kind') not in kinds:
            return None
        return h

    def _hold_words(self, hold):
        """One plain sentence part for why an opening order was held back."""
        why = (hold or {}).get('why')
        text = self._HOLD_WORDS.get(why, str(why))
        if why == 'refused_backoff':
            bits = []
            n = _i(hold.get('refusals'))
            if n:
                bits.append(f'{n} refusals in a row')
            until = _f(hold.get('until'))
            if until:
                bits.append(f'the next try at {_hm(until)}')
            if bits:
                text += ' (' + '; '.join(bits) + ')'
        return text

    def _hold_gate(self, hold, role='need'):
        """The gate of an order held back: the last test before the send, not met."""
        return _gate('open_hold', 'New orders allowed', False, hold.get('why'),
                     'nothing holds new orders back: the safety, the broker, the account balance, an old bot',
                     self._hold_words(hold), role=role)

    def _decide(self, c, snap, orders, now, digits):
        a = c.analysis_data or {}
        bk = snap['basket']
        bs, ss = _sig_name(c.buy_signal), _sig_name(c.sell_signal)
        nb, ns = _i(c._buy_ct) or 0, _i(c._sell_ct) or 0
        G = self._first_gates(nb, ns)
        has = bool(c.has_candle_data)
        fresh = has and bool(c.candle_is_fresh)
        if not has:
            G.append(_gate('market_data', 'Market data', False, 'no M15 bars', 'the terminal returns the M15 bars',
                           'nothing is decided without bars'))
        ms = c.market_status or {}
        lb = self._cfg('MARKET_LOOKBACK_MINUTES')
        G.append(_gate('market_live', 'Market live', fresh, _f(ms.get('minutes_since_last'), 2),
                       f'a tick or an M1 bar within {lb} min',
                       None if fresh else 'nothing is decided while the market is closed: no entry, no stop, no target'))
        fill_pending = bool(c._fill_pending)
        if nb and ns:
            G.append(_gate('one_side', 'One side open', False, f'{nb} buy and {ns} sell', 'a basket holds one side',
                           'the strategy holds still and manages neither side (close one by hand)'))
            action, reason, side = ('BOTH_SIDES' if fresh else ('NO_DATA' if not has else 'MARKET_CLOSED')), None, None
        elif nb or ns or fill_pending:
            action, reason, side = self._decide_basket(c, a, bk, G, fresh, has, bs, ss, nb, ns, fill_pending, orders, now,
                                                        digits)
        else:
            action, reason, side = self._decide_flat(c, a, bk, G, fresh, has, bs, ss, orders)
        decided = _mark_checked(G)
        dec = {'action': action, 'reason': reason, 'side': side, 'blocked_by': decided,
               'signal': {'buy': bs, 'sell': ss}, 'gates': G, 'orders': orders}
        dec['headline'] = self._headline(dec, c, snap, digits, now)
        self._self_check(dec, bs, ss, fresh, nb, ns, fill_pending)
        return dec

    def _decide_flat(self, c, a, bk, G, fresh, has, bs, ss, orders):
        pause = bk['pause']
        p_ok = (not pause['active']) if a.get('entry_allowed') is None else bool(a.get('entry_allowed'))
        last = pause.get('last_close') or {}
        since = _f(self._now() - last['t'], 1) if last.get('t') else None
        G.append(_gate('pause', 'Entry pause over', p_ok, since,
                       f"{_dur(pause['length_s'])} after the last close" + (' (a loss)' if last.get('lost') else ''),
                       (f"{_dur(pause['left_s'])} left, until {pause['until_utc']}" if not p_ok else
                        ('no close yet' if not last else f"last close {_dur(since)} ago ({last.get('reason')})"))))
        s, es = bk['open_score'], bk['entry_s']
        wants = bk['open_wants']
        tfs = ', '.join(bk['weights']['open'])
        G.append(_gate('open_score', f'Open score ({tfs})', wants is not None, s,
                       f'>= {_sc(es)} to buy, <= {_sc(-es if es is not None else None)} to sell',
                       f'wants a {wants}' if wants else 'no side wanted'))
        f, eas = bk['fc_score'], bk['entry_agree_s']
        ftfs = ', '.join(bk['weights']['agreement'])
        if wants == 'BUY':
            ag, need = (f is not None and eas is not None and f >= eas), f'>= {_sc(eas)} for a buy'
        elif wants == 'SELL':
            ag, need = (f is not None and eas is not None and f <= -eas), f'<= {_sc(-eas if eas is not None else None)} for a sell'
        else:
            ag, need = None, f'>= {_sc(eas)} for a buy, <= {_sc(-eas if eas is not None else None)} for a sell'
        G.append(_gate('agreement', f'Agreement score ({ftfs})', ag, f, need,
                       'the M15 votes must not stand against the entry' if eas == 0 else None))
        brake = bool(c.brake)
        G.append(_gate('window', 'Trading window', not brake,
                       ('manual brake (symbols.json brake 1)' if c.brake_manual else 'outside') if brake else 'inside',
                       self._window_text(c.trading_window_cfg)))
        try:
            entry_tfs = list(self.app.entry_timeframes())
        except Exception:
            entry_tfs = []
        missing = sorted({_tf_key(t) for t in (c._no_data or [])} & set(entry_tfs))
        G.append(_gate('votes_known', 'Votes known', not missing, missing or 'all',
                       'bars this poll for ' + ', '.join(entry_tfs), 'a missing timeframe would read as a 0 vote' if missing else None))
        tr = bk['trend']
        k = 1 if wants == 'BUY' else -1 if wants == 'SELL' else 0
        if tr.get('on'):
            ok = (k * (tr.get('sign') or 0) > 0) if k else None
            G.append(_gate('trend', f"{tr['tf']} trend", ok, tr.get('signal'),
                           f"MACD signal line of the last closed {tr['tf']} bar > 0 to buy, < 0 to sell",
                           f"{tr['text']}: " + ({'BUY': 'buys only', 'SELL': 'sells only'}.get(tr.get('allows')) or 'no entry')))
        else:
            G.append(_gate('trend', 'Trend filter', None, None, None, 'off in this design', role='info'))
        vol = bk['vol']
        if vol.get('on'):
            G.append(_gate('volatility', f"{vol['tf']} volatility unit", bool(vol.get('known')), vol.get('raw'),
                           f"> 0 on at least {vol.get('min_bars')} closed {vol['tf']} bars",
                           (f"{vol.get('bars_used')} closed bars" + (', capped' if vol.get('cap_binds') else ''))
                           if vol.get('bars_used') is not None else 'no bars this poll'))
            need_cs = any((_f(self._cfg(n)) or 0) > 0 for n in ('TARGET_VOL', 'STOP_VOL', 'VOL_CAP_USD_PER_UNIT'))
            if need_cs:
                G.append(_gate('contract_size', 'Contract size known', bool(bk.get('usd_per_price')), bk.get('contract_size'),
                               'symbol_info().trade_contract_size or CONTRACT_SIZE_FALLBACK'))
        else:
            G.append(_gate('volatility', 'Volatility unit', None, None, None, 'off in this design', role='info'))
        hold = self._hold(c, ('entry',))
        if hold is not None:                 # the last test before the send held the entry back (app.py _open_held)
            G.append(self._hold_gate(hold))
        if not fresh:
            return ('NO_DATA' if not has else 'MARKET_CLOSED'), None, None
        if bs == 'BUY' or ss == 'SELL':
            side = 'BUY' if bs == 'BUY' else 'SELL'
            if c.brake:
                return 'BLOCKED', 'window', side
            try:
                why = self._call('entry_block_reason', 1 if side == 'BUY' else -1, c.trend_now, c.vol_now,
                                 c._usd_per_price, no_data=c._no_data or [], short_history=c._short or [])
            except Exception:
                why = None
            if why:
                return 'BLOCKED', why, side
            if hold is not None:             # no order was sent: not a failed open
                return 'BLOCKED', hold.get('why'), side
            sent = [o for o in orders if o['kind'] == 'open' and o['side'] == side]
            if any(o['done'] for o in sent):
                return f'OPEN_{side}', None, side
            return 'OPEN_FAILED', (sent[-1]['retcode_text'] if sent else 'no order'), side
        if not p_ok:
            return 'PAUSED', pause.get('why'), None
        return 'WAIT', ('open score' if wants is None else 'agreement'), None

    def _decide_basket(self, c, a, bk, G, fresh, has, bs, ss, nb, ns, fill_pending, orders, now, digits=None):
        ov = bk.get('open') or {}
        side = ov.get('side') or ('BUY' if nb else 'SELL')
        buy = side == 'BUY'
        pnl = ov.get('pnl')
        judged = ov.get('judged_on')
        if fill_pending and not (nb or ns):
            opened = _f(ov.get('opened_at'))
            age = _f(now - opened, 1) if opened else None
            G.append(_gate('fill_listed', 'Fill listed', False, age,
                           f"the terminal lists the position (waits {_f(self._cfg('_PENDING_FILL_S'))} s)",
                           'no new entry meanwhile; the basket keeps its unit'))
            return 'WAIT_FILL', None, side
        if ov.get('close_pending') and ov.get('outside_ids'):
            G.append(_gate('legs_outside', 'Legs closed outside the bot', True, ov.get('outside_ids'),
                           'a leg gone without a close of this bot (the broker\'s backstop, a stop-out or by hand)',
                           'the other legs are closed at once; the whole basket is booked as closed outside the bot',
                           role='exit'))
        elif ov.get('close_pending'):
            G.append(_gate('close_retry', 'Earlier close finished', True, None,
                           'the positions an incomplete close left are closed first', role='exit'))
        sl, tg = ov.get('stop_usd'), ov.get('target_usd')
        # the exact thresholds the strategy compared the P/L with this poll (the USD shown is rounded to cents)
        sl_x = _f(a.get('stop_threshold')) if a.get('stop_threshold') is not None else sl
        tg_x = _f(a.get('close_threshold')) if a.get('close_threshold') is not None else tg
        if sl is None:
            G.append(_gate('stop', 'Stop', None, pnl, None, 'no stop in this design', role='exit'))
        else:
            G.append(_gate('stop', 'Stop', (pnl is not None and pnl <= -sl_x), pnl,
                           f"P/L <= {_usd(-sl)} ({judged} {'<=' if buy else '>='} {_px(ov.get('stop_price'), digits)})",
                           f"{_usd(ov.get('to_stop_usd'), signed=False)} above the stop" if ov.get('to_stop_usd') is not None else None,
                           role='exit'))
        if tg is None:
            G.append(_gate('target', 'Target', None, pnl, None, 'no target in this design', role='exit'))
        else:
            G.append(_gate('target', 'Target', (pnl is not None and pnl > tg_x), pnl,
                           f"P/L > {_usd(tg)} ({judged} {'>' if buy else '<'} {_px(ov.get('target_price'), digits)})",
                           f"{_usd(ov.get('to_target_usd'), signed=False)} to go" if ov.get('to_target_usd') is not None else None,
                           role='exit'))
        f, fcs = bk['fc_score'], bk['force_close_s']
        if not bk['force_close_enabled']:
            G.append(_gate('force_close', 'Force-close', None, f, None, 'off in this design (the M15 votes only gate entries)',
                           role='exit'))
        else:
            hit = (f is not None and fcs is not None and (f <= -fcs if buy else f >= fcs))
            G.append(_gate('force_close', 'Force-close', hit, f,
                           f"{'<=' if buy else '>='} {_sc(-fcs if buy else fcs)} (agreement score against the basket)", None,
                           role='exit'))
        ld = ov.get('ladder') or {}
        if not ld.get('on'):
            G.append(_gate('ladder', 'Ladder add', None, None, None, ld.get('note'), role='add'))
        elif ld.get('exhausted') or not ld.get('tier_tf'):
            G.append(_gate('ladder', 'Ladder add', None, ld.get('count'), None,
                           f"all {len(ld.get('tiers') or [])} adds made" if ld.get('exhausted') else 'no tier', role='add'))
        else:
            tf = ld['tier_tf']
            if ld.get('trigger') == 'macd_turn':
                hit = bool(a.get('ladder_armed')) and (ld.get('vote') or 0) * (1 if buy else -1) > 0
                G.append(_gate('ladder_trigger', f'{tf} MACD turn', hit, ld.get('vote'),
                               f"armed (the vote was against the basket since the last fill), then a vote {'+1' if buy else '-1'}",
                               'armed' if a.get('ladder_armed') else 'not armed yet', role='add'))
            else:
                r, lvl = ld.get('rsi'), ld.get('rsi_level')
                hit = r is not None and lvl is not None and (r <= lvl if buy else r >= lvl)
                G.append(_gate('ladder_trigger', f'{tf} RSI', hit, r, f"{'<=' if buy else '>='} {lvl}", None, role='add'))
            G.append(_gate('ladder_gate', 'Open score not against', bool(ld.get('add_ok')), bk['open_score'],
                           f"{'>' if buy else '<'} {_sc(-bk['ladder_s'] if buy else bk['ladder_s'])}", None, role='add'))
            if ld.get('gap_px'):
                nxt, now_px, last = ld.get('next_add_price'), ld.get('price_now'), ld.get('last_fill')
                # the strategy's own test: buy last fill - ask >= gap, sell bid - last fill >= gap
                ok = (last is not None and now_px is not None
                      and ((last - now_px) >= ld['gap_px'] if buy else (now_px - last) >= ld['gap_px']))
                G.append(_gate('ladder_gap', 'Price gap', ok, now_px,
                               f"{ld.get('judged_on')} {'<=' if buy else '>='} {_px(nxt, digits)} ({_num(ld['gap_px'], 3)} from the last fill)",
                               None, role='add'))
        hold = self._hold(c, ('add', 'pyramid'))
        if hold is not None:                 # an add every gate above lets through, held back before the send
            G.append(self._hold_gate(hold, role='add'))
        if not fresh:
            return ('NO_DATA' if not has else 'MARKET_CLOSED'), None, side
        sig = bs if buy else ss
        if sig == f'CLOSE_{side}':
            return f'CLOSE_{side}', a.get('exit_reason'), side
        if sig == f'{side}_MORE':
            done = any(o['done'] for o in orders if o['kind'] in ('add', 'open') and o['side'] == side)
            return (f'ADD_{side}' if done else 'ADD_FAILED'), None, side
        return 'HOLD', None, side

    def _self_check(self, dec, bs, ss, fresh, nb, ns, fill_pending):
        """The gates are this module's reading of the decision; the strategy's signal is the decision. A difference is
        a WARN (a bug of the trace, not of the trading) -- at most every 10 min."""
        if not fresh or (nb and ns):
            return
        g = {x['key']: x for x in dec['gates']}
        if not (nb or ns or fill_pending):
            reads = all(g[k]['ok'] for k in ('pause', 'open_score', 'agreement') if k in g)
            signal = bs == 'BUY' or ss == 'SELL'
        else:
            fired = [x['key'] for x in dec['gates'] if x['role'] == 'exit' and x['ok'] is True]
            reads = bool(fired)
            signal = bs in ('CLOSE_BUY',) or ss in ('CLOSE_SELL',)
            if g.get('close_retry') or g.get('legs_outside'):
                return
        if reads != signal:
            write, n = self._repeat(('selfcheck', dec['action']))
            if write:
                self._rec('WARN', 'TRACE', f"the trace's reading of the gates ({'act' if reads else 'hold'}) differs from the "
                          f"strategy's signal (buy {bs}, sell {ss}); the signal is what the bot did",
                          data={'gates': dec['gates']})

    def _headline(self, dec, c, snap, digits, now):
        act, reason, side = dec['action'], dec['reason'], dec['side']
        bk = snap['basket']
        g = {x['key']: x for x in dec['gates']}
        ms = c.market_status or {}
        ov = bk.get('open') or {}
        lb = self._cfg('MARKET_LOOKBACK_MINUTES')
        if act == 'NO_DATA':
            return 'No market data: the terminal returned no M15 bars this poll, so nothing is decided.'
        if act == 'MARKET_CLOSED':
            mins = ms.get('minutes_since_last')
            if ov.get('side'):
                return (f"Market closed (no tick for {_num(mins, 1)} min): holding the {ov['side']} basket at P/L "
                        f"{_usd(ov.get('pnl'))}; the stop and the target are checked again when it trades.")
            return (f'Market closed: no tick for {_num(mins, 1)} min (live needs one within {lb} min); nothing is '
                    'decided until it trades again.')
        if act == 'BOTH_SIDES':
            return ('Both a BUY and a SELL of this bot are open: the strategy holds still and manages neither side '
                    '(close one of them by hand).')
        tr = bk['trend']
        trend_note = ''
        if tr.get('on') and tr.get('allows'):
            trend_note = f" The {tr['tf']} trend is {tr['text']}: {'buys' if tr['allows'] == 'BUY' else 'sells'} only."
        if act == 'WAIT':
            s, es = bk['open_score'], bk['entry_s']
            if reason == 'agreement':
                w = bk['open_wants']
                return (f"Waiting: the open score wants a {w} ({_sc(s)}) but the agreement score is {_sc(bk['fc_score'])}; "
                        f"a {w.lower()} needs {g['agreement']['need'].split(' for ')[0]}." + trend_note)
            return (f"Waiting for an entry: the open score is {_sc(s)}; a buy needs {_sc(es)} or more, a sell "
                    f"{_sc(-es if es is not None else None)} or less." + trend_note)
        if act == 'PAUSED':
            p = bk['pause']
            last = p.get('last_close') or {}
            res = f" The last basket {'lost' if last.get('lost') else 'made'} {_usd(last.get('pnl'))}." if last else ''
            return (f"Paused {p.get('why') or ''}: no entry until {_hm(p.get('until'))} ({_dur(p.get('left_s'))} left)."
                    + res)
        if act == 'BLOCKED':
            if reason == 'window':
                return (f'A {side} signal is blocked: outside the trading window ({self._window_text(c.trading_window_cfg)}); '
                        'no new entries until it opens.')
            if reason == 'trend':
                return (f"A {side} signal is blocked: the {tr.get('tf')} trend is {tr.get('text')} (MACD signal "
                        f"{_num(tr.get('signal'), 4)} on the last closed bar); entries go only with the trend.")
            if reason == 'volatility unknown':
                v = bk['vol']
                return (f"A {side} signal is blocked: the {v.get('tf')} volatility unit is not known yet "
                        f"({v.get('bars_used')} closed bars, needs {v.get('min_bars')}).")
            if reason == 'votes unknown':
                return (f"A {side} signal is blocked: the terminal returned no bars for "
                        f"{', '.join(g['votes_known']['value'] or [])} this poll, so their votes are not known.")
            if 'open_hold' in g:
                return (f"A {side} signal stands and every check of the strategy lets it through, but no order is "
                        f"sent: {g['open_hold']['note']}.")
            return f'A {side} signal is blocked: {reason}.'
        if act in ('OPEN_BUY', 'OPEN_SELL'):
            fill = next((o for o in dec['orders'] if o['done'] and o['kind'] == 'open'), {})
            ends = self._ends_words(ov, side, digits)
            return (f"Opened a {side} basket: {fill.get('result_volume') or fill.get('volume')} lot at "
                    f"{_px(fill.get('result_price') or fill.get('price'), digits)}; "
                    + (('it closes at ' + ' or '.join(ends)) if ends else 'no stop and no target')
                    + (f"; {self._sl_word()} {_px(fill.get('sl'), digits)}" if fill.get('sl') else '') + '.')
        if act == 'OPEN_FAILED':
            return (f'Tried to open a {side} basket: the order was not filled ({reason}); it is tried again on the next '
                    'poll if the signal holds.')
        if act == 'WAIT_FILL':
            return (f"The {side} order filled; waiting for the terminal to list the position "
                    f"({_num(g['fill_listed']['value'], 0)} s so far); no new entry meanwhile.")
        if act in ('CLOSE_BUY', 'CLOSE_SELL'):
            pnl = ov.get('pnl')
            cr = c.close_response or {}
            res = ''
            n_closed, n_failed = int(cr.get('closed_count') or 0), int(cr.get('failed_count') or 0)
            waiting = self._close_waits_for(c.state, side, n_closed, n_failed)
            if cr and n_failed:
                res = (f" The close is incomplete: {cr.get('closed_count')} closed, {cr.get('failed_count')} failed "
                       f"({'; '.join(cr.get('errors') or [])}); the rest is closed next poll.")
            elif cr and not n_closed:
                res = (" The close closed nothing (none of this bot's positions were there to close): nothing is booked, "
                       'and the close is decided again next poll.')
            elif waiting:
                res = (f" The close is incomplete: leg(s) {waiting} filled less than "
                       f"{_num(self._cfg('_PENDING_FILL_S'), 0)} s ago are not listed by the terminal yet: the basket "
                       'stays open and the rest is closed next poll.')
            if reason == 'target':
                return f"Closing the {side} basket at the target: P/L {_usd(pnl)} > target {_usd(ov.get('target_usd'))}." + res
            if reason == 'stop_loss':
                return f"Closing the {side} basket at the stop: P/L {_usd(pnl)} <= stop {_usd(-(ov.get('stop_usd') or 0))}." + res
            if reason == 'force_close':
                return (f"Closing the {side} basket: the agreement score {_sc(bk['fc_score'])} turned against it "
                        f"(force-close at {_sc(-bk['force_close_s'] if side == 'BUY' else bk['force_close_s'])})." + res)
            if reason == 'close_retry':
                return f'Closing the rest of the {side} basket (an earlier close left positions open).' + res
            if reason == 'leg_closed_outside':
                return (f"Closing the rest of the {side} basket: leg(s) {ov.get('outside_ids')} were closed outside the "
                        "bot (the broker's backstop, a stop-out or by hand), so the whole basket is booked as closed "
                        f"outside the bot; P/L {_usd(pnl)} on the legs left." + res)
            return f'Closing the {side} basket ({reason}): P/L {_usd(pnl)}.' + res
        if act in ('ADD_BUY', 'ADD_SELL', 'ADD_FAILED'):
            ld = ov.get('ladder') or {}
            o = next((x for x in dec['orders'] if x['kind'] in ('add', 'open')), {})
            what = 'Added' if act != 'ADD_FAILED' else 'Tried to add'
            return (f"{what} {o.get('volume')} lot to the {side} basket ({self._ladder_words(ld, side, fired=True)})"
                    + (f": {ld.get('judged_on')} {_px(ld.get('price_now'), digits)} vs the next-add price "
                       f"{_px(ld.get('next_add_price'), digits)}" if ld.get('next_add_price') else '')
                    + (f" -> {o.get('retcode_text')}" if act == 'ADD_FAILED' else '') + '.')
        if act == 'HOLD':
            parts = [f"Holding the {side} basket: P/L {_usd(ov.get('pnl'))}"]
            ends = self._ends_words(ov, side, digits)
            if bk['force_close_enabled']:
                ends.append('a force-close')
            if ends:
                parts.append('; it closes at ' + ' or '.join(ends))
            ld = ov.get('ladder') or {}
            if ld.get('on') and ld.get('tier_tf'):
                parts.append(f"; next add {self._ladder_words(ld, side)}"
                             + (f" at {ld.get('judged_on')} {_px(ld.get('next_add_price'), digits)} or better"
                                if ld.get('next_add_price') else ''))
            if 'open_hold' in g:
                parts.append(f"; an add is held back: {g['open_hold']['note']}")
            return ''.join(parts) + '.'
        return act

    @staticmethod
    def _ladder_words(ld, side, fired=False):
        """'on an M5 MACD turn (armed)' / 'when the M1 RSI is >= 65 (now 61.2)' -- what the next add waits for."""
        tf = ld.get('tier_tf')
        if ld.get('trigger') == 'macd_turn':
            if fired:
                return f'the {tf} MACD vote turned with the basket'
            return f"on a {tf} MACD turn ({'armed' if ld.get('armed') else 'not armed yet'})"
        op = '<=' if side == 'BUY' else '>='
        now = f", now {_num(ld.get('rsi'), 1)}" if ld.get('rsi') is not None else ''
        if fired:
            return f"the {tf} RSI {_num(ld.get('rsi'), 1)} {op} {ld.get('rsi_level')}"
        return f"when the {tf} RSI is {op} {ld.get('rsi_level')}{now}"

    def _sl_word(self):
        """A design with a stop sends a broker-side backstop as the request sl; the live levers send the live (unreachable)
        auto sl."""
        try:
            return 'broker backstop' if (self._is_turtle() or self._call('design_has_stop')) else 'broker sl'
        except Exception:
            return 'broker sl'

    @staticmethod
    def _ends_words(ov, side, digits):
        """['the stop -$75.20 (bid <= 2,045.25)', 'the target +$75.20 (bid > 2,195.65)'] of a basket view."""
        buy = side == 'BUY'
        ends = []
        if ov.get('stop_usd') is not None:
            ends.append(f"the stop {_usd(-ov['stop_usd'])} ({ov.get('judged_on')} {'<=' if buy else '>='} "
                        f"{_px(ov.get('stop_price'), digits)})")
        if ov.get('target_usd') is not None:
            ends.append(f"the target {_usd(ov['target_usd'])} ({ov.get('judged_on')} {'>' if buy else '<'} "
                        f"{_px(ov.get('target_price'), digits)})")
        return ends

    # ── what changed since the last poll: log lines ──
    def _transitions(self, c, snap, dec, orders, now, digits):
        a = c.analysis_data or {}
        bk = snap['basket']
        st = c.state or {}
        prev = self._prev
        first = not prev.get('polled')         # (the basket / last close compare with the state loaded at the start)
        acct = snap['account']
        # the bot's own trading this poll
        ov = bk.get('open') or {}
        act = dec['action']
        if act in ('OPEN_BUY', 'OPEN_SELL'):
            fill = next((o for o in orders if o['done'] and o['kind'] == 'open'), {})
            vol = bk['vol']
            self._rec('INFO', 'BASKET',
                      f"{dec['side']} basket opened: {fill.get('result_volume') or fill.get('volume')} lot at "
                      f"{_px(fill.get('result_price') or fill.get('price'), digits)}, unit {ov.get('units')}, target "
                      f"{_usd(ov.get('target_usd'))} ({ov.get('judged_on')} {'>' if dec['side'] == 'BUY' else '<'} "
                      f"{_px(ov.get('target_price'), digits)}), stop "
                      + (f"{_usd(-ov['stop_usd'])} ({ov.get('judged_on')} {'<=' if dec['side'] == 'BUY' else '>='} "
                         f"{_px(ov.get('stop_price'), digits)})" if ov.get('stop_usd') is not None else 'none')
                      + (f", {self._sl_word()} {_px(fill.get('sl'), digits)}" if fill.get('sl') else '')
                      + (f", volatility unit {_num(ov.get('vol_unit'), 3)} ({vol.get('tf')}, raw {_num(vol.get('raw'), 3)})"
                         if vol.get('on') else '') + self._recorded_words(st, fill),
                      kv={'side': dec['side'], 'price': fill.get('result_price'), 'lots': fill.get('result_volume'),
                          'units': ov.get('units'), 'target_usd': ov.get('target_usd'), 'stop_usd': ov.get('stop_usd'),
                          'target_price': ov.get('target_price'), 'stop_price': ov.get('stop_price'),
                          'backstop': fill.get('sl'), 'vol_unit': ov.get('vol_unit'), 'trend_signal': bk['trend'].get('signal'),
                          'open_score': bk['open_score'], 'fc_score': bk['fc_score'],
                          **self._recorded_kv(st, fill)})
            self._trades_dirty = True
        elif act in ('ADD_BUY', 'ADD_SELL'):
            fill = next((o for o in orders if o['done'] and o['kind'] in ('add', 'open')), {})
            keep = [w for w, v in (('stop ' + _usd(-(ov.get('stop_usd') or 0)), ov.get('stop_usd')),
                                   ('target ' + _usd(ov.get('target_usd')), ov.get('target_usd'))) if v is not None]
            self._rec('INFO', 'BASKET', f"added {fill.get('result_volume') or fill.get('volume')} lot to the {dec['side']} basket "
                      f"at {_px(fill.get('result_price') or fill.get('price'), digits)} ({len(ov.get('legs') or []) + 1} "
                      'positions now)' + (f"; the basket's {' and '.join(keep)} "
                                          f"{'stay as they are' if len(keep) > 1 else 'stays as it is'} (in USD)" if keep else '')
                      + self._recorded_words(st, fill),
                      kv={'side': dec['side'], 'price': fill.get('result_price'), 'lots': fill.get('result_volume'),
                          'positions_before': len(ov.get('legs') or []), 'sl': fill.get('sl'),
                          'trigger': (ov.get('ladder') or {}).get('trigger'), 'tier': (ov.get('ladder') or {}).get('tier_tf'),
                          **self._recorded_kv(st, fill)})
            self._trades_dirty = True
        elif act in ('CLOSE_BUY', 'CLOSE_SELL'):
            cr = c.close_response or {}
            closed, failed = int(cr.get('closed_count') or 0), int(cr.get('failed_count') or 0)
            reason = dec['reason']
            if reason == 'close_retry':
                reason = self._pending_reason or reason
            lc = st.get('last_close') or {}
            ids = [l['id'] for l in ov.get('legs') or [] if l.get('id') is not None]
            waiting = self._close_waits_for(st, dec['side'], closed, failed)
            if closed:                       # the reason is the one of the close that closed (the rest follows it)
                self._record_exits(ids, reason, now, ov.get('pnl'))
            if waiting:
                # (v3.9.2-demo.5) the close closed every leg the terminal listed, but a leg recorded from its order is
                # not listed yet (app.py _after_close): the basket stays open and its close is finished next poll
                self._pending_reason = reason
                self._rec('WARN', 'CLOSE', f"the close of the {dec['side']} basket is incomplete: {closed} closed; leg(s) "
                          f"{waiting} filled less than {_num(self._cfg('_PENDING_FILL_S'), 0)} s ago are not listed by "
                          'the terminal yet, so the close did not reach them: the basket stays open, nothing is booked '
                          'yet, and the rest is closed next poll',
                          kv={'reason': reason, 'closed': closed, 'failed': failed, 'not_listed': waiting,
                              'tickets': cr.get('closed_tickets')})
            elif not closed and not failed:
                self._rec('WARN', 'CLOSE', f"the close of the {dec['side']} basket closed nothing: the close's own "
                          "positions read found none of this bot's positions (another account just now, or the "
                          'positions are already gone); nothing is booked, and the close is decided again next poll',
                          kv={'reason': reason, 'closed': 0, 'failed': 0, 'message': cr.get('message')})
            elif closed and not failed and reason == 'leg_closed_outside':
                self._pending_reason = None
                self._rec('CLOSE', 'CLOSE', f"the rest of the {dec['side']} basket closed after leg(s) "
                          f"{ov.get('outside_ids')} were closed outside the bot: {closed} position(s), P/L "
                          f"{_usd(ov.get('pnl'))} at the decision; the whole basket is booked as closed outside the bot",
                          kv={'side': dec['side'], 'reason': reason, 'decision_pnl': ov.get('pnl'),
                              'outside_ids': ov.get('outside_ids'), 'positions': closed,
                              'tickets': cr.get('closed_tickets'), 'held_s': ov.get('age_s')})
            elif closed and not failed:
                self._pending_reason = None
                realised = lc.get('pnl') if lc.get('resolved') and lc.get('source') == 'history' else None
                self._rec('CLOSE', 'CLOSE', f"{dec['side']} basket closed ({EXIT_TEXT.get(_BOT_REASON.get(reason, ''), reason)}): "
                          f"{closed} position(s), P/L {_usd(ov.get('pnl'))} at the decision"
                          + (f", realised {_usd(realised)}" if realised is not None else ', realised P/L follows from the deal history'),
                          kv={'side': dec['side'], 'reason': reason, 'decision_pnl': ov.get('pnl'), 'realised_pnl': realised,
                              'lost': lc.get('lost'), 'positions': closed, 'tickets': cr.get('closed_tickets'),
                              'stop_usd': ov.get('stop_usd'), 'target_usd': ov.get('target_usd'),
                              'held_s': ov.get('age_s')})
            else:
                if closed:
                    self._pending_reason = reason
                self._rec('WARN', 'CLOSE', f"the close of the {dec['side']} basket is incomplete: {closed} closed, {failed} "
                          f"failed ({'; '.join(cr.get('errors') or []) or cr.get('message')}); "
                          + ('the rest is closed next poll' if closed else 'it is decided again next poll'),
                          kv={'reason': reason, 'closed': closed, 'failed': failed})
            self._trades_dirty = True
        # the basket and the last close, as the state has them after this poll
        b = st.get('basket')
        lc = st.get('last_close')
        bsum, lsum = _basket_sum(b), _close_sum(lc)
        pb, pl = prev.get('basket'), prev.get('lc')
        new_close = bool(lsum and (pl is None or lsum['time'] != pl['time']))
        if pb is None and bsum is not None and bsum['opened_by'] == 'rebuild':
            self._rec('WARN', 'BASKET', f"{self._basket_words(b)}: taken over from the terminal (no state for it); the "
                      'ladder starts disarmed', data={'basket': b})
        elif pb is not None and bsum is None and not new_close:
            self._rec('WARN', 'BASKET', f"the {pb['side']} fill of {_hm(pb.get('opened_at'))} never showed up as a "
                      f"position in {_f(self._cfg('_PENDING_FILL_S'))} s; the basket is dropped")
        elif pb is not None and bsum is not None and pb['side'] == bsum['side']:
            new_ids = [i for i in bsum['ids'] if i not in pb['ids']]
            # (v3.9.2-demo.5) legs recorded from their order (app.py _record_fill): listed now, or listed under another id
            was_waiting = [i for i in (pb.get('unlisted') or []) if i not in (bsum.get('unlisted') or [])]
            listed_now = [i for i in was_waiting if i in bsum['ids']]
            swapped = [i for i in was_waiting if i not in bsum['ids']]
            if listed_now:
                self._rec('DEBUG', 'BASKET', f"position(s) {listed_now} of the {bsum['side']} basket listed by the terminal "
                          '(a leg since its fill: its id came from the order)')
            if swapped and new_ids:
                self._rec('DEBUG', 'BASKET', f"the fill(s) of order(s) {swapped} listed as position(s) {new_ids} in the "
                          f"{bsum['side']} basket ({len(bsum['ids'])} now)")
            elif new_ids:
                self._rec('DEBUG', 'BASKET', f"position(s) {new_ids} listed in the {bsum['side']} basket ({len(bsum['ids'])} now)")
            if pb.get('levels_pending') and not bsum.get('levels_pending'):
                self._rec('INFO', 'BASKET', f"the taken-over {bsum['side']} basket's levels are set from the volatility unit "
                          f"measured now: {self._basket_words(b)}")
            if pb.get('armed') != bsum.get('armed'):
                self._rec('DEBUG', 'BASKET', f"ladder {'armed' if bsum.get('armed') else 'disarmed'}")
        elif pb is not None and bsum is not None:
            self._rec('WARN', 'BASKET', f"the {bsum['side']} basket replaced the {pb['side']} one: {self._basket_words(b)}")
        if new_close and lsum.get('reason') == 'closed_outside':
            ids = list(lc.get('ids') or [])
            outside = list(lc.get('outside_ids') or [])
            self._record_exits(ids, 'closed_outside', now, lc.get('pnl'))
            final = lc.get('resolved') and lc.get('source') == 'history'
            if outside:                      # some legs closed outside the bot, the rest by the bot (_sync_basket)
                head = (f"the {lc.get('side')} basket is booked as closed outside the bot: leg(s) {outside} were closed "
                        f"outside it (the broker's backstop, a stop-out or by hand), the bot closed the other "
                        f"{max(0, len(ids) - len(outside))}: ")
                tail = (f"realised {_usd(lc.get('pnl'))} on every leg (deal history)" if final else
                        f"{_usd(lc.get('pnl'))} so far (until the deal history shows every leg, the basket counts as a "
                        'loss: the pause after a loss)')
            elif pb is not None and not pb.get('listed') and pb.get('side') == lc.get('side'):
                # (v3.9.2-demo.5) an entry recorded from its order that the terminal never listed (app.py _sync_basket)
                head = (f"the {lc.get('side')} entry {ids} is gone before the terminal listed it (its broker backstop "
                        'while the bot or the terminal was down?): booked as closed outside the bot, with the pause '
                        'after a loss if it lost: ')
                tail = (f"realised {_usd(lc.get('pnl'))}, its closing deal at {_hm(lc.get('time'))} (deal history)"
                        if final else 'the bot never saw its P/L: the realised P/L and the closing time follow from the '
                                      'deal history')
            else:
                head = (f"the {lc.get('side')} basket was closed outside the bot (the broker's backstop, the terminal, "
                        'or while the bot was down): ')
                tail = (f"realised {_usd(lc.get('pnl'))}, its last closing deal at {_hm(lc.get('time'))} (deal history)"
                        if final else f"P/L last seen {_usd(lc.get('pnl'))}; the realised P/L and the closing time follow "
                                      'from the deal history')
            kv = {'reason': 'closed_outside', 'ids': ids, 'pnl': lc.get('pnl'), 'final': bool(final),
                  'closed_utc': _iso(lc.get('time'))}
            if outside:
                kv['outside_ids'] = outside
            self._rec('CLOSE', 'CLOSE', head + tail, kv=kv)
            self._trades_dirty = True
        if new_close:
            p = bk['pause']
            head = ('entry pause started' if lsum.get('source') != 'history_rebuild' else
                    f"no state file: the last close ({_hm(lc.get('time'))}) comes from the deal history, so the entry "
                    'pause')
            self._rec('INFO', 'PAUSE', f"{head}: {_dur(p['length_s'])} {p.get('why')} "
                      f"({'loss' if lc.get('lost') else 'result'} {_usd(lc.get('pnl'))}"
                      f"{', not final yet' if not lc.get('resolved') else ''}), until {_hm(p.get('until'))}",
                      kv={'length_s': p['length_s'], 'until_utc': p.get('until_utc'), 'lost': lc.get('lost'),
                          'pnl': lc.get('pnl'), 'resolved': lc.get('resolved'), 'source': lsum.get('source')})
        elif lsum and pl and lsum['resolved'] and not pl['resolved']:
            p = bk['pause']
            src = lsum.get('source')
            self._rec('INFO', 'CLOSE', f"the last basket's result is final: {_usd(lc.get('pnl'))} "
                      + ('(from the deal history)' if src == 'history' else '(the history had no closing deals: the P/L '
                         'seen at the close stands)')
                      + (f"; the pause is {_dur(p['length_s'])} {p.get('why')}, until {_hm(p.get('until'))}"
                         if pl.get('lost') != lsum.get('lost') else ''),
                      kv={'pnl': lc.get('pnl'), 'lost': lc.get('lost'), 'source': src})
            self._trades_dirty = True
        pause_active = bk['pause']['active']
        if prev.get('pause_active') and not pause_active:
            self._rec('INFO', 'PAUSE', 'entry pause over: entries are allowed again')
        # the market, the window, the data, the unit, the contract size
        live = bool(c.has_candle_data and c.candle_is_fresh)
        if not first and prev.get('live') != live:
            ms = c.market_status or {}
            if live:
                self._rec('INFO', 'MARKET', 'market live again')
            else:
                self._rec('INFO', 'MARKET', f"market not live: no tick or M1 bar for {_num(ms.get('minutes_since_last'), 1)} "
                          'min; nothing is decided until it trades', kv={'status': ms.get('status'), 'message': ms.get('message')})
        if not c.has_candle_data and (first or prev.get('has_data', True)):
            self._rec('WARN', 'DATA', 'the terminal returned no M15 bars: nothing is decided')
        brake = bool(c.brake)
        if not first and prev.get('brake') != brake:
            self._rec('INFO', 'WINDOW', ('outside the trading window' if not c.brake_manual else 'manual brake on')
                      + f' ({self._window_text(c.trading_window_cfg)}): no new entries; an open basket is still managed'
                      if brake else 'inside the trading window: entries allowed')
        nd = sorted(set(c._no_data or []))
        if nd != (prev.get('no_data') or []):
            if nd:
                self._rec('WARN', 'DATA', f"the terminal returned no bars for {', '.join(nd)} this poll (their votes are "
                          'unknown: no entry on them; exits go on)')
            elif not first:
                self._rec('INFO', 'DATA', 'every timeframe has bars again')
        sh = sorted(set(c._short or []))
        if sh != (prev.get('short') or []):
            if sh:
                self._rec('WARN', 'DATA', f"fewer than {self._cfg('_MIN_CLOSED_BARS')} closed bars of {', '.join(sh)}: "
                          'the trend / volatility unit are not settled, no entry')
            elif not first:
                self._rec('INFO', 'DATA', 'the trend and volatility timeframes have a full history again')
        units = acct.get('units')
        if not first and prev.get('units') != units:
            self._rec('INFO', 'ACCOUNT', f"unit {prev.get('units')} -> {units}" + self._sizing_words(snap))
        upp = _f(c._usd_per_price)
        if upp != prev.get('usd_pp'):
            self._rec('INFO', 'CONFIG', f"contract size {bk.get('contract_size')}: {_usd(upp, signed=False)} per unit "
                      f"({acct.get('mtqty')} lot) for a 1.0 price move", kv={'usd_per_price': upp, 'digits': digits})
        if first:
            p = bk['pause']
            self._rec('INFO', 'STATE', f"first poll: {self._basket_words(b)}; last close: {self._close_words(lc)}"
                      + (f"; entry pause {_dur(p['left_s'])} left" if p['active'] else '')
                      + f'; unit {units}' + self._sizing_words(snap),
                      data={'basket': b, 'last_close': lc})
        ms_loop = _f(c.iteration_ms)
        if ms_loop is not None and ms_loop > SLOW_POLL_MS:
            write, n = self._repeat(('slow',), every=300.0)
            if write:
                self._rec('WARN', 'LOOP', f'slow poll: {ms_loop / 1000.0:.1f} s of work (the terminal answered slowly?)',
                          kv={'loop_ms': ms_loop, 'more_since': n})
        prev.update(polled=True, basket=bsum, lc=lsum, pause_active=pause_active, live=live, has_data=bool(c.has_candle_data),
                    brake=brake, no_data=nd, short=sh, units=units, usd_pp=upp)

    def _decision_line(self, dec, now):
        """A DEBUG line whenever the decision changes: the action, or the result of a gate the bot checked."""
        gates = {g['key']: (g['role'], g['ok']) for g in dec['gates'] if g.get('checked')}
        key = (dec['action'], dec.get('reason'), dec.get('side'), tuple(gates.items()))
        if key == self._last_key:
            return
        prev, before = self._last_action, self._last_gates or {}
        self._last_key, self._last_action, self._last_gates = key, dec['action'], gates
        if prev == dec['action'] and before:
            changed = [f'{k} {_mark(*before[k]) if k in before else "unchecked"}->{_mark(*v)}'
                       for k, v in gates.items() if before.get(k) != v]
            changed += [f'{k} {_mark(*v)}->unchecked' for k, v in before.items() if k not in gates]
            msg = f"{dec['action']} (gates changed: {', '.join(changed)}): {dec['headline']}"
        else:
            msg = f"{prev or 'start'} -> {dec['action']}: {dec['headline']}"
        self._rec('DEBUG', 'DECISION', msg,
                  kv={'reason': dec.get('reason'), 'side': dec.get('side'), 'gates': _gates_text(dec['gates'])},
                  data={'gates': dec['gates'], 'signal': dec.get('signal'), 'blocked_by': dec.get('blocked_by')})

    def _heartbeat(self, dec, snap, now):
        if self._hb_t is not None and now - self._hb_t < HEARTBEAT_S:
            return
        self._hb_t = now
        h, ac, m, bk = snap.get('health') or {}, snap.get('account') or {}, snap.get('market') or {}, snap.get('basket') or {}
        ov = bk.get('open') or {}
        kv = {'poll': self.polls, 'bid': m.get('bid'), 'ask': m.get('ask'), 'spread': m.get('spread'),
              'open_score': bk.get('open_score'), 'agree_score': bk.get('fc_score'),
              'trend': (bk.get('trend') or {}).get('sign'), 'vol': (bk.get('vol') or {}).get('raw'),
              'units': ac.get('units'), 'balance': ac.get('balance'), 'equity': ac.get('equity'),
              'open_pl': ac.get('own_open_pl'),
              'basket': ov.get('side'), 'pnl': ov.get('pnl'), 'pause_left_s': (bk.get('pause') or {}).get('left_s'),
              'loop_ms': h.get('loop_ms'), 'trace_ms': h.get('trace_ms'), 'tick_age_s': h.get('last_tick_age_s'),
              'errors_1h': h.get('errors_1h'), 'skipped': h.get('skipped_polls'), 'stale': snap.get('stale')}
        tu = snap.get('turtle')
        if tu:                                 # the Turtle's key numbers instead of the basket's
            lv, vt, tr = tu.get('levels') or {}, tu.get('vote') or {}, tu.get('trade') or {}
            for k in ('open_score', 'agree_score', 'trend', 'vol', 'basket', 'pause_left_s'):
                kv.pop(k, None)
            kv.update(buy_level=lv.get('buy'), sell_level=lv.get('sell'), n=lv.get('n'),
                      orders=(tu.get('orders') or {}).get('state'), vote=vt.get('value'), vote_bar=vt.get('bar_utc'),
                      trade=tr.get('side'), legs=tr.get('legs_count'), stop=tr.get('stop'), next_add=tr.get('next_add'),
                      pnl=tr.get('pnl'))
        self._rec('INFO', 'HEARTBEAT', f"{dec['action']}: {dec['headline']}", kv={k: v for k, v in kv.items() if v is not None})

    def _write_trace(self, snap, dec, now, force=False):
        held = (snap.get('basket') or {}).get('open') or (snap.get('turtle') or {}).get('trade') or {}
        key = (dec['action'], dec.get('reason'), tuple((g['key'], g['ok']) for g in dec['gates']),
               tuple(l.get('ticket') for l in held.get('legs') or []))
        if (not force and self._last_trace_t is not None and now - self._last_trace_t < TRACE_MIN_INTERVAL_S
                and key == self._last_trace_key):
            return
        try:
            self._write_json(self.paths['trace'], snap)
        except Exception as e:
            self.write_failed('the trace', self.paths['trace'], e)
            return
        self._last_trace_t, self._last_trace_key = now, key

    # ── the chart's bars ──
    def _bars(self, c, now, digits, sig=None, overlay=None):
        """sig: what says the market moved since the last write (basket: the poll's M1 bar; the Turtle, which fetches
        no M1 bars: the last tick); overlay: a function giving the file's 'overlay' (the Turtle's daily levels)."""
        frames = c._frames or {}
        m1 = frames.get(_TF + 'M1')
        if sig is None and m1 is not None and len(m1):
            sig = (_epoch(m1['time'].iloc[-1]), _f(m1['close'].iloc[-1]), _f(m1['high'].iloc[-1]), _f(m1['low'].iloc[-1]))
        if self._bars_t is not None and (now - self._bars_t < BARS_MIN_INTERVAL_S or sig is None or sig == self._bars_sig):
            return
        tfs, sources = {}, {}
        for tf, n in BARS_SPEC:
            fr = frames.get(_TF + tf)
            if fr is not None and len(fr):
                tfs[tf] = self._bars_from_frame(fr, n, digits)
                sources[tf] = 'poll'
            else:
                tfs[tf] = self._bars_from_terminal(tf, n, digits)
                sources[tf] = 'terminal'
        doc = {'schema': SCHEMA, 'symbol': self.symbol, 'mt5_symbol': self.mt5_symbol, 't': round(now, 3),
               'time_utc': _iso(now), 'price': 'bid', 'digits': digits, 'last_is_forming': True,
               'counts': {tf: len((v or {}).get('t') or []) for tf, v in tfs.items()}, 'source': sources, 'tf': tfs}
        if overlay is not None:
            doc['overlay'] = overlay()
        self._bars_t = now                     # (a failed write is tried again in 30 s, not every poll)
        try:
            write_json_atomic(self.paths['bars'], doc)
        except Exception as e:
            self.write_failed('the bars', self.paths['bars'], e)
            return
        self._bars_sig = sig

    @staticmethod
    def _round_list(arr, digits):
        a = np.asarray(arr, dtype=float)
        return (np.round(a, digits) if digits is not None else a).tolist()

    def _bars_from_frame(self, fr, n, digits):
        tail = fr.iloc[-n:]
        return {'t': tail['time'].values.astype('datetime64[s]').astype(np.int64).tolist(),
                'o': self._round_list(tail['open'].to_numpy(), digits), 'h': self._round_list(tail['high'].to_numpy(), digits),
                'l': self._round_list(tail['low'].to_numpy(), digits), 'c': self._round_list(tail['close'].to_numpy(), digits),
                'v': tail['tick_volume'].to_numpy().astype(np.int64).tolist() if 'tick_volume' in tail else None}

    def _bars_from_terminal(self, tf, n, digits):
        code = getattr(self.app.mt5, _TF + tf, None)
        if code is None:
            return None
        with self.bot.mt5_lock:
            rates = self.app.mt5.copy_rates_from_pos(self.mt5_symbol, code, 0, n)
        if rates is None or len(rates) == 0:
            return None
        names = rates.dtype.names or ()
        return {'t': np.asarray(rates['time'], dtype=np.int64).tolist(),
                'o': self._round_list(rates['open'], digits), 'h': self._round_list(rates['high'], digits),
                'l': self._round_list(rates['low'], digits), 'c': self._round_list(rates['close'], digits),
                'v': np.asarray(rates['tick_volume'], dtype=np.int64).tolist() if 'tick_volume' in names else None}

    # ── the trades ──
    def _state_dir(self):
        """The folder of the bot's own state files (app.py: state_dir, or OUTPUT_DIR/state)."""
        try:
            return os.path.dirname(self.bot._state_path(self.symbol))
        except Exception:
            return os.path.join(self.out_dir, 'state')

    def _live_start(self):
        """When this bot started trading real money on this account: app.py's record (state/live_start.json, made at
        the first poll that passed the account guard: the earliest of that moment, the bot's oldest open position and
        its first deal in the account's history -- so it can still move back while the history could not be read).
        The bot's own copy of it when it has one, else the file; None while there is none, or it is another
        account's."""
        data = getattr(self.bot, '_live_start', None)
        if not isinstance(data, dict):
            try:
                with open(os.path.join(self._state_dir(), 'live_start.json'), 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                return None
            if not isinstance(data, dict):
                return None
        t = _f(data.get('time'))
        mine = _login_sha(getattr(self.bot, '_login', None))
        if t is None or t <= 0 or (data.get('login_sha') and mine and data.get('login_sha') != mine):
            return None
        return t

    def _trades(self, c, snap, now, digits):
        due = (self._trades_dirty or self._trades_again or self._trades_t is None
               or now - self._trades_t >= TRADES_INTERVAL_S)
        if not due or (self._trades_retry_t is not None and now < self._trades_retry_t):
            return
        # a reporting read: from a day before the bot's live start (the reads the bot decides on keep their own
        # windows, in app.py). Without the file yet: the last TRADES_LOOKBACK_S (only this bot's magic is read)
        live_t = self._live_start()
        since = max(0.0, live_t - LIVE_START_MARGIN_S if live_t is not None else now - TRADES_LOOKBACK_S)
        # set before the read and cleared only after a good write: a read, a build or a write that fails is not
        # tried again on every poll (the full deal history is read under mt5_lock)
        self._trades_retry_t = now + TRADES_RETRY_S
        with self.bot.mt5_lock:
            deals = self.bot.position_helper.get_bot_deals(_utc_dt(since), _utc_dt(now + 86400))
        if deals is None:
            write, n = self._repeat(('history',), every=300.0)
            if write:
                self._rec('WARN', 'TRADES', 'the terminal gave no deal history: trades.json keeps its last content')
            return
        self._trades_retry_t = now + TRADES_INTERVAL_S          # a build that raises: the next read in a minute
        doc = self._build_trades(list(deals), snap, since, now, digits, live_t)
        self._own_closed = _f(((doc.get('summary') or {}).get('net')), 2)
        if self._is_turtle():
            self._turtle_results(doc)
        # the journal's line for every trade the history shows closed (once each; on its own: a failure here must
        # not keep trades.json from being written)
        self._step('poll', '_journal_trades', self._journal_trades, doc, now, live_t)
        try:
            self._write_json(self.paths['trades'], doc)
        except Exception as e:
            self.write_failed('the trades', self.paths['trades'], e)
            self._trades_retry_t = now + 30.0               # no history read every poll while the disk fails
            return
        self._trades_retry_t = None
        self._trades_again = self._trades_dirty
        self._trades_dirty = False
        self._trades_t = now

    def _build_trades(self, deals, snap, since, now, digits, live_t=None):
        """trades.json from this bot's deals since `since`: real numbers only. Every closed trade with its P/L in
        dollars (profit, swap, commission and fee apart), the running total of the bot's own closed P/L from 0
        (balance_after of a trade, balance_curve, summary.balance_now) and its deepest fall in dollars. No balance
        of the bot's own is made up: the account's balance is in the trace."""
        sym = self.mt5_symbol
        vstart = 0.0                           # the running total of the bot's own closed P/L starts at 0
        rows = [d for d in deals if getattr(d, 'symbol', sym) in (sym, None, '') and _deal_t(d) >= since]
        rows.sort(key=lambda d: (_deal_t(d), _i(getattr(d, 'ticket', 0)) or 0))
        by_pos = {}
        for d in rows:
            pid = _i(getattr(d, 'position_id', 0)) or 0
            if pid:
                by_pos.setdefault(pid, []).append(d)
        legs = []
        for pid, ds in by_pos.items():
            ins = [d for d in ds if _deal_entry(d) == 'in']
            outs = [d for d in ds if _deal_entry(d) == 'out']
            if not ins and not outs:
                continue
            vin = sum(float(getattr(d, 'volume', 0) or 0) for d in ins)
            vout = sum(float(getattr(d, 'volume', 0) or 0) for d in outs)
            if ins:
                side = 'BUY' if _i(getattr(ins[0], 'type', None)) == 0 else 'SELL'
            else:
                side = 'SELL' if _i(getattr(outs[0], 'type', None)) == 0 else 'BUY'

            def wavg(ds_):
                v = sum(float(getattr(d, 'volume', 0) or 0) for d in ds_)
                return (sum(float(getattr(d, 'price', 0) or 0) * float(getattr(d, 'volume', 0) or 0) for d in ds_) / v
                        if v else None)
            closed = bool(outs) and (not ins or vout >= vin - 1e-9)
            legs.append({
                'position_id': pid, 'side': side, 'lots': _f(vin or vout, 2),
                'open_t': _deal_t(ins[0]) if ins else None, 'open_price': _f(wavg(ins), digits) if ins else None,
                'close_t': _deal_t(outs[-1]) if outs else None, 'close_price': _f(wavg(outs), digits) if outs else None,
                'closed': closed,
                'profit': round(sum(float(getattr(d, 'profit', 0) or 0) for d in ds), 2),
                'swap': round(sum(float(getattr(d, 'swap', 0) or 0) for d in ds), 2),
                'commission': round(sum(float(getattr(d, 'commission', 0) or 0) for d in ds), 2),
                'fee': round(sum(float(getattr(d, 'fee', 0) or 0) for d in ds), 2),
                'net': round(sum(_deal_net(d) for d in ds), 2),
                'deal_reasons': [DEAL_REASONS.get(_i(getattr(d, 'reason', None)), getattr(d, 'reason', None)) for d in outs],
                'magic': getattr(ins[0], 'magic', None) if ins else None,
            })
        legs.sort(key=lambda l: ((l['open_t'] if l['open_t'] is not None else (l['close_t'] or 0.0)), l['position_id']))
        groups, cur = [], None
        for leg in legs:
            t_in = leg['open_t'] if leg['open_t'] is not None else (leg['close_t'] or 0.0)
            if cur is not None and leg['side'] == cur['side'] and (cur['close_t'] is None or t_in <= cur['close_t'] + 1.0):
                cur['legs'].append(leg)
                cur['close_t'] = None if (cur['close_t'] is None or not leg['closed']) else max(cur['close_t'], leg['close_t'])
            else:
                cur = {'side': leg['side'], 'legs': [leg], 'close_t': leg['close_t'] if leg['closed'] else None}
                groups.append(cur)
        times = [_deal_t(d) for d in rows]
        cum, run = [], vstart
        for d in rows:
            run += _deal_net(d)
            cum.append(run)
        closed, open_ = [], []
        turtle = self._is_turtle()
        for g in groups:
            ls = g['legs']
            lots = sum(l['lots'] or 0.0 for l in ls)
            opened = [l for l in ls if l['open_price'] is not None]
            olots = sum(l['lots'] or 0.0 for l in opened)
            t_open = min((l['open_t'] for l in ls if l['open_t'] is not None), default=None)
            trade = {'id': ls[0]['position_id'], 'side': g['side'], 'legs': ls, 'lots': round(lots, 2),
                     'open_t': t_open, 'open_utc': _iso(t_open),
                     'open_price': _f(sum(l['open_price'] * (l['lots'] or 0) for l in opened) / olots, digits)
                     if olots else None,
                     'pnl': round(sum(l['net'] for l in ls), 2), 'profit': round(sum(l['profit'] for l in ls), 2),
                     'swap': round(sum(l['swap'] for l in ls), 2), 'commission': round(sum(l['commission'] for l in ls), 2),
                     'fee': round(sum(l['fee'] for l in ls), 2)}
            if turtle:
                trade['turtle'] = self._journal_view([l['position_id'] for l in ls])
            if g['close_t'] is None:
                trade['status'] = 'open'
                open_.append(trade)
                continue
            t_close = g['close_t']
            clots = sum(l['lots'] or 0.0 for l in ls if l['close_price'] is not None)
            reason, bot_reason, rec = self._exit_of(ls)
            k = bisect_right(times, t_close + 1e-6)
            text = EXIT_TEXT.get(reason, reason)
            if reason == 'turtle_stop' and (rec or {}).get('origin'):
                text = f"{text} ({self._origin_words(rec['origin'], g['side'])})"
            trade.update(status='closed', close_t=t_close, close_utc=_iso(t_close),
                         close_price=_f(sum(l['close_price'] * (l['lots'] or 0) for l in ls if l['close_price'] is not None)
                                        / clots, digits) if clots else None,
                         hold_s=_f(t_close - t_open, 1) if t_open is not None else None,
                         exit_reason=reason, exit_reason_text=text, bot_reason=bot_reason,
                         balance_after=round(cum[k - 1], 2) if k else round(vstart, 2), result=(
                             'win' if trade['pnl'] > 0 else 'loss' if trade['pnl'] < 0 else 'flat'))
            if turtle:
                trade.update(exit_detail=(rec or {}).get('origin'), exit_stop=(rec or {}).get('stop'))
            closed.append(trade)
        closed.sort(key=lambda x: x['close_t'])
        t0 = live_t if live_t is not None else since
        curve = [{'t': t0, 'utc': _iso(t0), 'v': round(vstart, 2), 'id': None}]
        curve += [{'t': x['close_t'], 'utc': x['close_utc'], 'v': x['balance_after'], 'id': x['id'], 'pnl': x['pnl']}
                  for x in closed]
        # the deepest fall of that running total, in dollars: from its highest point so far (0 at the start) down
        # to the lowest point after it
        top, top_t, fall, fall_from_t, fall_to_t = vstart, t0, 0.0, None, None
        for pt in curve[1:]:
            if pt['v'] > top:
                top, top_t = pt['v'], pt['t']
            elif top - pt['v'] > fall:
                fall, fall_from_t, fall_to_t = top - pt['v'], top_t, pt['t']
        wins = [x['pnl'] for x in closed if x['pnl'] > 0]
        losses = [x['pnl'] for x in closed if x['pnl'] < 0]
        net = round(sum(x['pnl'] for x in closed), 2)
        live = (snap.get('turtle') or {}).get('trade') if turtle else (snap.get('basket') or {}).get('open')
        if live and live.get('side') and not live.get('both_sides'):
            live = dict(live, status='open', live=True)
            open_list = [live]
        else:
            open_list = open_
        reasons = {}
        for x in closed:
            reasons[x['exit_reason']] = reasons.get(x['exit_reason'], 0) + 1
        return {
            'schema': SCHEMA, 'symbol': self.symbol, 'mt5_symbol': sym, 'magic': self._cfg('MAGIC'),
            'design': self._cfg('DESIGN_NAME'), 't': round(now, 3), 'time_utc': _iso(now),
            'since_t': since, 'since_utc': _iso(since),
            # the bot's live start (null while app.py has not written state/live_start.json: the read then goes
            # back TRADES_LOOKBACK_S)
            'live_start_t': live_t, 'live_start_utc': _iso(live_t),
            'closed': closed[-TRADES_MAX_CLOSED:], 'open': open_list,
            'balance_curve': curve[-(TRADES_MAX_CLOSED + 1):],
            'summary': {
                'closed': len(closed), 'wins': len(wins), 'losses': len(losses),
                'win_rate': round(len(wins) / len(closed), 4) if closed else None, 'net': net,
                'gross_win': round(sum(wins), 2), 'gross_loss': round(sum(losses), 2),
                'best': max((x['pnl'] for x in closed), default=None), 'worst': min((x['pnl'] for x in closed), default=None),
                'avg_hold_s': round(sum(x['hold_s'] or 0 for x in closed) / len(closed), 1) if closed else None,
                'exit_reasons': reasons, 'balance_now': round(cum[-1], 2) if cum else round(vstart, 2),
                'deals': len(rows),
                'deepest_fall': round(fall, 2), 'deepest_fall_from_t': fall_from_t,
                'deepest_fall_from_utc': _iso(fall_from_t), 'deepest_fall_to_t': fall_to_t,
                'deepest_fall_to_utc': _iso(fall_to_t),
            },
        }

    def _exit_of(self, legs):
        """(exit reason key, the reason the bot recorded, its record): the bot's record for the legs that closed last
        (a Turtle leg closed outside the bot earlier does not name the trade's exit), refined by the closing deals'
        reasons for a trade closed outside the bot (the broker's stop = the backstop ...)."""
        bot, rec = None, None
        last = sorted(legs, key=lambda l: -(l['close_t'] or 0.0))
        for l in last:
            r = self._exits.get(str(l['position_id']))
            if r:
                bot, rec = r.get('reason'), r
                break
        if bot is not None and bot != 'closed_outside':
            return _BOT_REASON.get(bot, bot), bot, rec
        top = last[0]['close_t'] if last else None
        why = [r for l in last if l['close_t'] == top for r in l['deal_reasons']] or \
              [r for l in legs for r in l['deal_reasons']]
        if 'sl' in why:
            return 'backstop', bot, rec
        if 'tp' in why:
            return 'broker_target', bot, rec
        if 'stop_out' in why:
            return 'stop_out', bot, rec
        if bot == 'closed_outside' or any(r in ('client', 'mobile', 'web') for r in why):
            return 'closed_outside', bot, rec
        return 'unknown', bot, rec

    def _load_exits(self):
        try:
            with open(self.paths['exits'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get('reasons'), dict):
                return dict(data['reasons'])
        except (OSError, ValueError):
            pass
        return {}

    def _record_exits(self, ids, reason, t, pnl=None, extra=None):
        changed = False
        for i in ids or ():
            k = str(i)
            if k not in self._exits:
                self._exits[k] = dict(extra or {}, reason=reason, t=round(float(t), 3), pnl=_f(pnl))
                changed = True
        if not changed:
            return
        if len(self._exits) > EXIT_REASONS_KEEP:
            keep = sorted(self._exits.items(), key=lambda kv: kv[1].get('t') or 0)[-EXIT_REASONS_KEEP:]
            self._exits = dict(keep)
        try:
            self._write_json(self.paths['exits'], {'schema': SCHEMA, 'symbol': self.symbol, 'magic': self._cfg('MAGIC'),
                                                   'reasons': self._exits})
        except Exception as e:
            self.write_failed('the exit reasons', self.paths['exits'], e)

    # ═════════════ the journal's state: journaled trades, the open trade, lasting problems, the running day ═════════════
    # state/<SYMBOL>_journal_state.json, written atomically by this module only, never while the bot holds mt5_lock:
    #   journaled, journaled_t   the newest JOURNAL_KEEP_IDS closed trades the journal has a line for (id, close time)
    #   journaled_before_t       trades closed at or before this time count as journaled too (ids dropped from the list)
    #   open                     the trade the bot holds: its ids, the facts fixed at its entry, its highest / lowest
    #                            floating P/L, how it was watched (from its entry? restarts?)
    #   closing                  trades that have ended and wait for the deal history to show them closed
    #   issues, moments          the problems that last (since when, when last written), the last line of the others
    #   day                      the running UTC day's figures (the day line is written when the next day begins)
    # and, as every state file of a real-money bot, the account as its tail and its SHA-256, and the branch.

    @staticmethod
    def _jstate_new():
        return {'journaled': [], 'journaled_t': [], 'journaled_before_t': None, 'open': None, 'closing': [],
                'issues': {}, 'moments': {}, 'day': None}

    def _jstate_load(self):
        """The journal's state as this process finds it; a fresh one without a readable file. Never raises (it runs
        when the trace is made)."""
        self._js_sha = self._js_tail = None    # the account the file was written for
        self._js_file = False                  # a readable file was there (else the journal's own tail names its trades)
        self._js_nosave = False
        self._js_saving = False
        self._js_seen = {}                     # trade id -> the poll (of this process) that saw its close
        self._js_wait_t = None
        js = self._jstate_new()
        try:
            with open(self.paths['jstate'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return js
            self._js_file = True
            self._js_sha, self._js_tail = data.get('login_sha'), data.get('login_tail')
            ids = [_i(x) for x in data.get('journaled') or []]
            times = [_f(x) for x in data.get('journaled_t') or []]
            times += [None] * (len(ids) - len(times))
            pairs = [(i, t) for i, t in zip(ids, times) if i is not None]
            js['journaled'], js['journaled_t'] = [p[0] for p in pairs], [p[1] for p in pairs]
            js['journaled_before_t'] = _f(data.get('journaled_before_t'))
            js['open'] = data['open'] if isinstance(data.get('open'), dict) else None
            js['closing'] = [x for x in data.get('closing') or [] if isinstance(x, dict)][-20:]
            js['issues'] = {str(k): v for k, v in (data.get('issues') or {}).items() if isinstance(v, dict)}
            js['moments'] = {str(k): v for k, v in (data.get('moments') or {}).items() if _f(v) is not None}
            js['day'] = data['day'] if isinstance(data.get('day'), dict) else None
        except Exception:
            return self._jstate_new()
        return js

    def _jstate_account(self):
        """As soon as the credentials are known -- the start-up lines (boot), the loop's start, and before every save
        of the state, so that a start that fails before the loop never saves this account's mark over another
        account's state: a state written for another account is not this bot's -- its open trade, its journaled
        ids and its problems are that account's. The file is set aside (<name>.other-account-<yyyymmdd_hhmmss>)
        and the journal's state starts afresh; if it cannot be moved it is left as it is and nothing is saved over
        it in this process. Once done (or without the credentials yet) it does nothing; never inside mt5_lock."""
        mine = _login_sha(getattr(self.bot, '_login', None))
        if not self._js_sha or not mine or self._js_sha == mine or self._in_lock():
            return
        path = self.paths['jstate']
        stamp = datetime.fromtimestamp(self._now(), tz=timezone.utc).strftime('%Y%m%d_%H%M%S')
        aside = f'{path}.other-account-{stamp}'
        try:
            replace_retry(path, aside)
            moved = True
        except OSError:
            moved = False
            self._js_nosave = True
        self._rec('WARN', 'STATE', f"the journal's state file was written for another account ({self._js_tail or '...?'}), "
                  f"not this bot's {self._own_tail()}: " + (f'it is set aside as {os.path.basename(aside)}' if moved else
                                                           'it could not be moved, so it is left as it is and not used')
                  + '; the journal starts afresh for this account', kv={'path': path})
        self._js = self._jstate_new()
        self._js_sha = self._js_tail = None
        self._js_file = False

    def _js_mark(self, level):
        """The state changed: 'now' (saved at the end of this poll: a trade opened or ended, a line written once),
        'soon' (an extreme moved: within JOURNAL_SAVE_S) or 'day' (the day's figures: within JOURNAL_DAY_SAVE_S)."""
        order = (None, 'day', 'soon', 'now')
        if order.index(level) > order.index(self._js_dirty):
            self._js_dirty = level

    def _jstate_save(self, now):
        """Write the journal's state when it is due. After the poll's own flush: a trade line is in the journal
        before the state says so (a process killed in between finds the line in the journal's tail at its next
        start, not a second time). Never while the bot holds mt5_lock."""
        level = self._js_dirty
        if level is None or self._js_nosave or self._js_saving or self._in_lock():
            return
        self._jstate_account()                 # (a state of another account is set aside first, never saved over)
        if self._js_nosave:
            return
        wait = {'now': 0.0, 'soon': JOURNAL_SAVE_S, 'day': JOURNAL_DAY_SAVE_S}[level]
        if wait and self._js_saved_t is not None and 0.0 <= now - self._js_saved_t < wait:
            return
        if level == 'now' and self.writer.pending('journal'):
            # the journal itself could not be written just now: its lines wait in memory, and so does the state
            # that would call them written (for 5 minutes at most: the open trade's extremes must not wait for good)
            if self._js_wait_t is None:
                self._js_wait_t = now
            if 0.0 <= now - self._js_wait_t < 300.0:
                return
        self._js_wait_t = None
        # the account the file is for: this bot's, once its credentials are known; until then the one the file
        # already named (the tail always goes with its own fingerprint)
        sha = _login_sha(getattr(self.bot, '_login', None))
        data = {'schema': SCHEMA, 'symbol': self.symbol, 'magic': self._cfg('MAGIC'), 'branch': self._cfg('BRANCH'),
                'login_sha': sha or self._js_sha, 'login_tail': (self._own_tail() if sha else None) or self._js_tail,
                'saved_at': round(now, 3)}
        data.update(self._js)
        self._js_saved_t = now                 # (a write that fails is tried again after the wait, not every poll)
        self._js_saving = True
        try:
            self._write_json(self.paths['jstate'], data)
            self._js_dirty = None
        except Exception as e:
            if level == 'now':
                self._js_dirty = 'soon'
            self.write_failed("the journal's state", self.paths['jstate'], e)
        finally:
            self._js_saving = False

    def _journaled_from_tail(self):
        """The trade lines at the end of the journal itself, read once, at the first read of the deal history: their
        ids count as journaled also when the state file does not say so (a process killed between the two writes,
        or a state file that is gone). The newest 256 KB with a state file, 2 MB without one -- and then, when the
        journal is longer than that, the trades that closed well before its oldest line read count as journaled
        too (journaled_before_t)."""
        js = self._js
        need = 262144 if self._js_file else 2 * 2 ** 20
        year = int(_day(self._now())[:4])
        found, oldest, whole = [], None, True  # whole: every line of the journal was read
        for y in (year, year - 1):
            path = self.writer.journal_path(y)
            if need <= 0:
                whole = whole and not os.path.exists(path)
                break
            try:
                size = os.path.getsize(path)
                with open(path, 'rb') as f:
                    if size > need:
                        f.seek(size - need)
                    data = f.read()
            except OSError:
                continue
            lines = data.split(b'\n')
            if size > len(data):
                whole = False
                lines = lines[1:]              # (the first one is cut)
            for line in lines:
                m = _LINE_T.match(line)
                if m:
                    t = float(m.group(1))
                    oldest = t if oldest is None else min(oldest, t)
                if b'"kind":"trade"' not in line[:160]:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                tid = _i(rec.get('id')) if isinstance(rec, dict) else None
                if tid is not None:
                    found.append((tid, _f(rec.get('close_t'))))
            need -= len(data)
        known = set(js['journaled'])
        new = [(i, t) for i, t in found if i not in known]
        if new:
            js['journaled'] += [i for i, _ in new]
            js['journaled_t'] += [t for _, t in new]
            self._js_mark('now')
        if not self._js_file and not whole and oldest is not None:
            # no state file to say which trades are in, and lines older than the part read: a bot that was running
            # when the oldest line read was written had written the line of every trade that closed more than a
            # few minutes before it (at its first read of the deal history after the close), so such a trade is
            # either before the part read or in it -- never to be written again
            floor = oldest - JOURNAL_TAIL_MARGIN_S
            before = _f(js.get('journaled_before_t'))
            if before is None or floor > before:
                js['journaled_before_t'] = round(floor, 3)
                self._js_mark('now')

    # ── the open trade: the facts of its entry, its highest and lowest floating P/L ──
    def _trade_now(self, snap):
        """What this poll shows of the trade the bot holds: None when it is flat, False when that cannot be told
        (both sides open, positions it does not manage, a section of the trace that failed), else {'key', 'ids',
        'side', 'pnl', 'closed_now', 'view'} -- also on the poll that closes it (closed_now), with the P/L at the
        close decision."""
        if self._is_turtle():
            sec = snap.get('turtle')
            if not isinstance(sec, dict):
                return False
            v = sec.get('trade')
            if v is None:
                return None
            if v.get('both_sides') or not v.get('known_to_bot') or not v.get('side'):
                return False
            key = ['T', v.get('side'), v.get('entry_t')]
            ids = [x.get('id') for x in v.get('legs') or []]
        else:
            sec = snap.get('basket')
            if not isinstance(sec, dict):
                return False
            v = sec.get('open')
            if v is None:
                return None
            if v.get('both_sides') or not v.get('side'):
                return False
            key = ['B', v.get('side'), v.get('opened_at')]
            ids = [x.get('id') for x in v.get('legs') or []] + list(v.get('ids') or [])
        ids = list(dict.fromkeys(i for i in (_i(x) for x in ids) if i is not None))
        return {'key': key if key[2] is not None else None, 'ids': ids, 'side': v.get('side'), 'pnl': _f(v.get('pnl')),
                'closed_now': bool(v.get('closed_now')), 'view': v}

    @staticmethod
    def _same_trade(jo, v):
        if jo.get('key') is not None and v.get('key') is not None and list(jo['key']) == list(v['key']):
            return True
        return bool(set(jo.get('ids') or []) & set(v.get('ids') or []))

    def _track_trade(self, c, snap, dec, orders, now):
        """Every poll that read the terminal, in memory: the trade the bot holds -- the facts of its entry (taken on
        the poll of the entry; after a restart or a takeover from what the bot kept of it, marked rebuilt), its
        highest and lowest floating P/L -- and the trades that have just ended (the balance of the first poll after
        the close). The state file is saved at the open, at the close, and when an extreme changed but at most every
        JOURNAL_SAVE_S (_jstate_save, at the end of the poll)."""
        js = self._js
        first, self._js_first = self._js_first, False
        acct, sf = snap.get('account') or {}, snap.get('safety') or {}
        for ctx in js['closing']:
            seen = self._js_seen.get(ctx.get('id'))
            if seen is not None and seen < self.polls and ctx.get('after') is None:
                # the first poll after the one that saw the close: the account's balance now holds the result (and
                # whatever the other bot of the account booked meanwhile), and these are that poll's safety meters
                ctx['after'] = {'t': round(now, 3), 'balance': acct.get('balance'), 'equity': acct.get('equity'),
                                'drop_pct': _f((sf.get('drop') or {}).get('pct')),
                                'day_pct': _f((sf.get('day') or {}).get('pct')),
                                'streak': _i((sf.get('streak') or {}).get('count')), 'state': sf.get('state'),
                                'blocked': sf.get('blocked')}
                self._js_mark('now')
                self._trades_dirty = True      # (the deal history is read on this poll: the trade's line can go out)
        v = self._trade_now(snap)
        if v is False:
            return
        jo = js['open']
        if first and jo is not None:
            if v is not None and self._same_trade(jo, v):
                jo['restarts'] = (_i(jo.get('restarts')) or 0) + 1      # a restart in the middle of the trade
            else:
                # the trade the file holds is gone: it ended while the bot was not running (its close was not seen)
                js['closing'].append(dict(jo, seen_close=False))
                js['open'] = jo = None
                self._trades_dirty = True
            self._js_mark('now')
        if v is None:
            if jo is not None:                 # gone since the last poll: closed outside the bot
                self._trade_ended(jo, None, dec, now)
            return
        if jo is not None and not self._same_trade(jo, v):
            self._trade_ended(jo, None, dec, now)   # another trade in its place, with no flat poll between
            jo = None
        if jo is None:
            jo = js['open'] = self._trade_new(c, snap, dec, orders, v, now)
            self._js_mark('now')
        if v['ids'] and v['ids'] != jo.get('ids'):
            jo['ids'] = list(dict.fromkeys(list(jo.get('ids') or []) + v['ids']))
            if jo.get('id') is None:
                jo['id'] = jo['ids'][0]
            self._js_mark('soon')
        jo['polls'] = (_i(jo.get('polls')) or 0) + 1
        jo['last_t'] = round(now, 3)
        pnl = v['pnl']
        if pnl is not None:
            jo['last_pnl'] = pnl
            if jo.get('max_pnl') is None or pnl > jo['max_pnl']:
                jo['max_pnl'], jo['max_t'] = pnl, round(now, 3)
                self._js_mark('soon')
            if jo.get('min_pnl') is None or pnl < jo['min_pnl']:
                jo['min_pnl'], jo['min_t'] = pnl, round(now, 3)
                self._js_mark('soon')
        if v['closed_now']:
            self._trade_ended(jo, v, dec, now)

    def _trade_new(self, c, snap, dec, orders, v, now):
        entry_now = dec.get('action') in ('OPEN_BUY', 'OPEN_SELL')
        view = v['view']
        opened = _f(view.get('entry_t') if self._is_turtle() else (view.get('first_t') or view.get('opened_at')))
        return {'id': v['ids'][0] if v['ids'] else None, 'ids': list(v['ids']), 'key': v['key'], 'side': v['side'],
                'opened_t': opened, 'from_entry': entry_now, 'rebuilt': not entry_now, 'restarts': 0,
                'entry': self._entry_facts(c, snap, orders, view, entry_now),
                'max_pnl': None, 'max_t': None, 'min_pnl': None, 'min_t': None, 'last_pnl': None, 'polls': 0,
                'first_t': round(now, 3), 'last_t': round(now, 3)}

    def _entry_facts(self, c, snap, orders, view, entry_now):
        """What was fixed when the trade opened: side, units, target and stop, the volatility unit or N, the scores
        and votes, how the unit was sized, the entry's quote and slippage. entry_now False: a trade the trace did
        not see open (a restart without its record, a takeover from the terminal): what the bot kept of it, marked
        rebuilt; what it does not have is null."""
        fill = next((o for o in orders if o['done'] and o['kind'] == 'open'), {}) if entry_now else {}
        facts = {'rebuilt': not entry_now, 'side': view.get('side'), 'units': view.get('units'),
                 'price': fill.get('result_price'), 'bid': fill.get('bid'), 'ask': fill.get('ask'),
                 'spread': fill.get('spread'), 'slippage': fill.get('slippage'),
                 'slippage_usd': fill.get('slippage_usd'), 'backstop': fill.get('sl') or None,
                 'sizing': snap.get('sizing')}
        if self._is_turtle():
            tv = snap.get('turtle') or {}
            vt = tv.get('vote') or {}
            facts.update(lots=view.get('lots_per_leg'), n=view.get('n_entry'), stop=view.get('stop'),
                         stop_origin=view.get('stop_origin'), stop_dist=view.get('stop_dist'),
                         add_step=view.get('add_step'), entry_level=view.get('entry_level'),
                         entry_d1_t=view.get('entry_d1_t'), max_legs=view.get('max_legs'),
                         vote=vt.get('last') if entry_now else None,
                         votes={'rsi': (vt.get('rsi') or {}).get('vote'), 'macd': (vt.get('macd') or {}).get('vote')}
                         if entry_now else None,
                         use20=((tv.get('levels') or {}).get('use20')) if entry_now else None)
        else:
            bk = snap.get('basket') or {}
            facts.update(lots=view.get('lots'), target_usd=view.get('target_usd'), stop_usd=view.get('stop_usd'),
                         target_price=view.get('target_price'), stop_price=view.get('stop_price'),
                         vol_unit=view.get('vol_unit'), vol_unit_raw=view.get('vol_unit_raw'),
                         gap_px=view.get('gap_px'), opened_by=view.get('opened_by'),
                         open_score=bk.get('open_score') if entry_now else None,
                         fc_score=bk.get('fc_score') if entry_now else None,
                         trend_signal=(bk.get('trend') or {}).get('signal') if entry_now else None,
                         votes={tf: [(x.get('rsi') or {}).get('vote'), (x.get('macd') or {}).get('vote')]
                                for tf, x in (bk.get('votes') or {}).items()} if entry_now else None)
        return facts

    def _trade_ended(self, jo, v, dec, now):
        """The bot saw this trade end on this poll: it closed it (v: the poll's view, with the P/L at the decision),
        or its positions are gone (v None: closed outside the bot). Its line is written when the deal history shows
        it closed and the next poll has given the balance after it."""
        js = self._js
        jo.update(seen_close=True, closed_seen_t=round(now, 3),
                  closed_by='bot' if v is not None else 'outside',
                  decision_pnl=v['pnl'] if v is not None else None)
        if jo.get('id') is not None:
            self._js_seen[jo['id']] = self.polls
            if len(self._js_seen) > 100:
                self._js_seen = dict(list(self._js_seen.items())[-50:])
        js['closing'].append(jo)
        del js['closing'][:-20]
        if js['open'] is jo:
            js['open'] = None
        self._js_mark('now')
        self._trades_dirty = True

    def _journal_trades(self, doc, now, live_t):
        """At every read of the deal history: one journal line for every closed trade the journal does not hold yet
        that closed after the bot's live start, oldest first, at most JOURNAL_TRADES_PER_READ per read. Once per
        trade, also across restarts (the state file's ids, and the journal's own tail)."""
        js = self._js
        if not self._js_tail_read:
            self._js_tail_read = True
            self._journaled_from_tail()
        known = set(js['journaled'])
        before = _f(js.get('journaled_before_t'))
        held = set((js['open'] or {}).get('ids') or [])
        wrote = 0
        for x in doc.get('closed') or []:
            tid, ct = _i(x.get('id')), _f(x.get('close_t'))
            if tid is None or ct is None or tid in known or (before is not None and ct <= before):
                continue
            if x.get('open_t') is None or (live_t is not None and ct < live_t):
                continue                       # not a whole trade of the read, or one from before the live start
            ids = {_i(leg.get('position_id')) for leg in x.get('legs') or []} | {tid}
            if ids & held:
                continue                       # the bot still holds it: its line comes once a poll has seen it end
            ctx = next((k for k in js['closing'] if ids & (set(k.get('ids') or []) | {k.get('id')})), None)
            if (ctx is not None and ctx.get('seen_close') and ctx.get('after') is None
                    and ctx.get('id') in self._js_seen
                    and 0.0 <= now - (_f(ctx.get('closed_seen_t')) or 0.0) < JOURNAL_AFTER_WAIT_S):
                continue                       # the poll after its close has not come yet (the balance after it)
            self._jline('trade', self._trade_line(x, ctx), t=now)
            js['journaled'].append(tid)
            js['journaled_t'].append(ct)
            known.add(tid)
            if ctx is not None:
                js['closing'] = [k for k in js['closing'] if k is not ctx]
            wrote += 1
            if wrote >= JOURNAL_TRADES_PER_READ:
                break
        if wrote:
            extra = len(js['journaled']) - JOURNAL_KEEP_IDS
            if extra > 0:
                gone = [t for t in js['journaled_t'][:extra] if t is not None]
                if gone:
                    js['journaled_before_t'] = max([max(gone)] + ([before] if before is not None else []))
                del js['journaled'][:extra]
                del js['journaled_t'][:extra]
            self._js_mark('now')

    def _trade_line(self, x, ctx):
        """The journal's line of one closed trade: the deal history's figures (profit, swap, commission and fee
        apart) joined with what the bot knew. watched: 'full' -- the bot saw it from its entry to its close without
        a restart; 'part' -- it saw the close, but not all of the trade (a restart in between, or a trade it took
        over); 'none' -- it did not see the close (it was not running, or the trade is not known to it): then the
        extremes and the balance after are not known. What is not known is null, never 0."""
        legs = x.get('legs') or []
        seen = bool(ctx and ctx.get('seen_close'))
        if not seen:
            watched = 'none'
        elif ctx.get('from_entry') and not ctx.get('restarts') and not ctx.get('rebuilt'):
            watched = 'full'
        else:
            watched = 'part'
        ctx = ctx or {}
        entry = ctx.get('entry') if isinstance(ctx.get('entry'), dict) else None
        own = ctx if seen else {}
        after = own.get('after') if isinstance(own.get('after'), dict) else {}
        reasons = sorted({str(r) for leg in legs for r in (leg.get('deal_reasons') or []) if r is not None})
        line = {
            'id': x.get('id'), 'side': x.get('side'), 'legs': len(legs),
            'leg_ids': [leg.get('position_id') for leg in legs], 'lots': x.get('lots'),
            'open_t': x.get('open_t'), 'open_utc': x.get('open_utc'), 'open_price': x.get('open_price'),
            'close_t': x.get('close_t'), 'close_utc': x.get('close_utc'), 'close_price': x.get('close_price'),
            'hold_s': x.get('hold_s'), 'pnl': x.get('pnl'), 'profit': x.get('profit'), 'swap': x.get('swap'),
            'commission': x.get('commission'), 'fee': x.get('fee'), 'result': x.get('result'),
            'exit_reason': x.get('exit_reason'), 'exit_reason_text': x.get('exit_reason_text'),
            'bot_reason': x.get('bot_reason'), 'deal_reasons': reasons,
            'watched': watched, 'rebuilt': ctx.get('rebuilt') if ctx else None,
            'restarts': ctx.get('restarts') if ctx else None, 'entry': entry,
            'max_pnl': own.get('max_pnl'), 'max_pnl_t': own.get('max_t'), 'min_pnl': own.get('min_pnl'),
            'min_pnl_t': own.get('min_t'), 'polls_watched': own.get('polls'), 'watched_from_t': own.get('first_t'),
            'closed_by': own.get('closed_by'), 'decision_pnl': own.get('decision_pnl'),
            'balance_before': ((entry or {}).get('sizing') or {}).get('account_balance'),
            # the ACCOUNT's balance at the first poll after the bot saw the close (it holds the other bot's bookings
            # of that moment too), and that poll's safety meters
            'balance_after': after.get('balance'), 'balance_after_t': after.get('t'),
            'safety_after': ({k: after.get(k) for k in ('drop_pct', 'day_pct', 'streak', 'state', 'blocked')}
                             if after else None),
            # the running total of this bot's own closed trades after this one (trades.json balance_after)
            'own_total_after': x.get('balance_after'),
        }
        if self._is_turtle():
            line.update(exit_detail=x.get('exit_detail'), exit_stop=x.get('exit_stop'))
        return line

    # ── the problems: when one starts, changes and ends, and at most every 15 minutes in between ──
    # (codes the poll itself reads from its snapshot every time: _issues; the others come from the events)
    _ISSUE_STATES = ('TERMINAL_ERROR', 'ACCOUNT_REFUSED', 'TRADING_NOT_ALLOWED', 'DISK_LOW', 'FOREIGN_POSITIONS',
                     'OLD_BOT_SAME_TERMINAL', 'OLD_BOT_RUNNING', 'SAFETY_ERROR', 'PARTNER_ACCOUNT_DIFFERS',
                     'PARTNER_LIMITS_DIFFER', 'REFUSED_BACKOFF')

    def _issue_on(self, code, key, text, now, extra=None):
        """A problem that lasts is there on this poll (or an event just named it): a journal line when it starts
        ('start'), when it is another one of its kind ('change': `key` differs) and every ISSUE_REPEAT_S while it
        lasts ('still'). key None: named by an event; the poll's own reading gives the key later, without a line.
        Kept in the journal's state, so a restart neither announces it again nor forgets to say that it ended."""
        iss = self._js['issues']
        key, text = self._mask(key), self._mask(text)      # (they are kept in the state file: tails only)
        key = None if key is None else str(key)[:200]
        cur = iss.get(code)
        t = round(now, 3)
        if cur is None:
            iss[code] = {'key': key, 'text': text, 'since': t, 'last': t, 'seen': t}
            self._jline('issue', dict(extra or {}, code=code, state='start', text=text), t=now)
            self._js_mark('now')
            return
        cur['seen'] = t
        if key is not None and cur.get('key') is None:
            cur['key'] = key
        elif key is not None and key != cur.get('key'):
            cur.update(key=key, text=text, last=t)
            self._jline('issue', dict(extra or {}, code=code, state='change', text=text, since=cur.get('since')), t=now)
            self._js_mark('now')
        elif not 0.0 <= now - (_f(cur.get('last')) or 0.0) < ISSUE_REPEAT_S:
            cur['last'] = t
            since = _f(cur.get('since'))
            self._jline('issue', dict(extra or {}, code=code, state='still', text=cur.get('text'), since=since,
                                        lasted_s=round(now - since, 1) if since is not None else None), t=now)
            self._js_mark('now')

    def _issue_moment(self, code, key, text, now, extra=None):
        """A problem that is a moment, not a state (a state file of another account, another program's close, a
        close whose result is not known ...): one journal line, the same one again at most every ISSUE_REPEAT_S."""
        moments = self._js['moments']
        k = f'{code}|{self._mask(key)}'[:240]
        last = _f(moments.get(k))
        if last is not None and 0.0 <= now - last < ISSUE_REPEAT_S:
            return
        moments[k] = round(now, 3)
        if len(moments) > 50:
            for old in sorted(moments, key=lambda m: _f(moments[m]) or 0.0)[:len(moments) - 50]:
                del moments[old]
        self._jline('issue', dict(extra or {}, code=code, state='event', text=text), t=now)
        self._js_mark('now')

    def _issue_from_event(self, event, note, msg, d):
        """A WARN / ERROR event of the strategy log as a problem of the journal."""
        now = self._now()
        if event in self._ISSUE_MOMENTS or event not in self._EVENTS:
            self._issue_moment(event, _problem_key(note), msg, now)
        else:
            self._issue_on(event, None if event in self._ISSUE_STATES else _problem_key(note), msg, now)

    def _issues(self, snap, now, good):
        """Every poll: the problems this poll's snapshot shows (they are states: the dashboard draws its banners
        from the same keys), each as a problem that lasts; and, on a poll that read the terminal, the end of every
        problem that has not shown for ISSUE_END_AFTER_S."""
        h = snap.get('health') or {}
        f = snap.get('foreign') or {}
        s = snap.get('safety') or {}
        p = s.get('partner') if isinstance(s.get('partner'), dict) else {}
        hold = snap.get('open_hold') or {}
        cur = {}
        if h.get('connected') is False:
            cur['TERMINAL_ERROR'] = (_problem_key(h.get('terminal_problem')), f"the terminal cannot be read: "
                                     f"{h.get('terminal_problem')}")
        elif h.get('positions_problem'):
            cur['TERMINAL_ERROR'] = (_problem_key(h.get('positions_problem')), f"the positions cannot be read: "
                                     f"{h.get('positions_problem')}")
        if h.get('account_ok') is False:
            cur['ACCOUNT_REFUSED'] = (_problem_key(h.get('account_problem')), f"not trading: {h.get('account_problem')}")
        off = h.get('trading_not_allowed') or []
        if off:
            cur['TRADING_NOT_ALLOWED'] = (','.join(off), 'trading is switched off (' + ', '.join(
                self._TRADING_OFF_WORDS.get(x, x) for x in off) + '): the bot can neither open nor close')
        if h.get('disk_low'):
            cur['DISK_LOW'] = ('1', self._disk_low_words())
        n = _i(f.get('positions')) or 0
        if n > 0:
            cur['FOREIGN_POSITIONS'] = (str(n), f"{n} trade(s) that are not this bot's are open on {self.mt5_symbol} "
                                        'in this account: nothing manages them here')
        if f.get('old_bot_same_terminal'):
            cur['OLD_BOT_SAME_TERMINAL'] = ('1', 'an old bot is running on this server and uses the same MetaTrader 5: '
                                            'this bot opens nothing new until it is stopped')
        elif f.get('old_bot_age_s') is not None:
            cur['OLD_BOT_RUNNING'] = ('1', 'an old bot is running on this server, on another MetaTrader 5')
        if s.get('error'):
            cur['SAFETY_ERROR'] = (_problem_key(s.get('error')), f"the safety check failed: {s.get('error')}")
        if p.get('account_differs'):
            cur['PARTNER_ACCOUNT_DIFFERS'] = ('1', 'the two bots of this account are logged into different accounts')
        if p.get('limits_differ'):
            cur['PARTNER_LIMITS_DIFFER'] = ('1', 'the two bots of this account have different safety limits')
        if hold.get('why') == 'refused_backoff':
            cur['REFUSED_BACKOFF'] = ('1', "the broker refuses this bot's new orders: they are tried again more slowly")
        for code, (key, text) in cur.items():
            self._issue_on(code, key, text, now)
        low = bool(h.get('disk_low'))
        if low != self._disk_low_said:         # (in the text log too, once when it starts and once when it ends)
            self._disk_low_said = low
            if low:
                self._rec('ERROR', 'DISK', self._disk_low_words(), kv={
                    'event': 'DISK_LOW', 'free_mb': round((self.writer.disk_free or 0) / 2 ** 20, 1)})
            else:
                self._rec('INFO', 'DISK', 'there is room on the disk again: every line is logged again',
                          kv={'event': 'DISK_OK'})
        if not good:
            return                             # (a skipped poll read nothing: what it does not show is not over)
        iss = self._js['issues']
        for code in [k for k, v in iss.items() if not 0.0 <= now - (_f(v.get('seen')) or 0.0) < ISSUE_END_AFTER_S]:
            gone = iss.pop(code)
            since, seen = _f(gone.get('since')), _f(gone.get('seen'))
            self._jline('issue', {'code': code, 'state': 'end', 'text': gone.get('text'), 'since': since,
                                    'last_seen': seen,
                                    'lasted_s': round(seen - since, 1) if (since is not None and seen is not None)
                                    else None}, t=now)
            self._js_mark('now')

    _TRADING_OFF_WORDS = {'algo_trading_off': 'Algo Trading is off in MetaTrader 5',
                          'python_api_disabled': 'MetaTrader 5 has the Python API disabled',
                          'account_trade_disabled': 'the account may not trade',
                          'account_expert_disabled': 'the broker does not let programs trade this account'}

    def _disk_low_words(self):
        return (f'less than {DISK_LOW_BYTES / 2 ** 30:g} GB is free on the disk of {self.out_dir}: until there is room '
                'again the log keeps only orders, fills, closes, warnings and errors, and the per-minute samples '
                'stop. Free some space: collect_logs.bat makes a zip of the logs, old zips can go')

    # ── the day that ended ──
    def _day_line(self, snap, now):
        """Every poll that read the terminal keeps the running UTC day's figures; at the first one of a new day the
        journal gets the line of the day that ended: balance, equity, the account's high (the safety's), the day's
        booked P/L (both bots; deposits and withdrawals are not in it), the cash operations, and complete: false
        when the bot did not run through midnight -- the one that began the day (else the day's start is the
        balance of its first poll) or the one that ended it (else the last figures are of an earlier moment).
        A pause in between does not change the day's booked figures: it is in longest_gap_s and
        watched_whole_day."""
        ac, sf = snap.get('account') or {}, snap.get('safety') or {}
        today = _day(now)
        rec = self._js.get('day')
        if isinstance(rec, dict) and rec.get('day') and rec.get('day') != today:
            midnight = math.floor(now / 86400.0) * 86400.0
            last, first_t = _f(rec.get('last_t')), _f(rec.get('first_t'))
            day0 = None
            try:
                day0 = datetime.strptime(str(rec['day']), '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                pass
            # through the midnight that ended the day (its last poll and this one within 2 minutes of it), and the one
            # that began it (its first poll within 2 minutes after it)
            through = (last is not None and 0.0 <= midnight - last <= 120.0 and now - midnight <= 120.0
                       and day0 is not None and midnight - day0 == 86400.0)
            began = first_t is not None and day0 is not None and 0.0 <= first_t - day0 <= 120.0
            whole = through and began and (_f(rec.get('longest_gap_s')) or 0.0) <= 120.0
            self._jline('day', {
                'day': rec.get('day'), 'balance': rec.get('balance'), 'equity': rec.get('equity'),
                'high': rec.get('high'), 'balance_high': rec.get('balance_high'), 'balance_low': rec.get('balance_low'),
                'booked': rec.get('booked'), 'start_balance': rec.get('start_balance'), 'cash': rec.get('cash'),
                'own_closed_total': rec.get('own_closed_total'), 'drop_pct': rec.get('drop_pct'),
                'day_pct': rec.get('day_pct'), 'streak': rec.get('streak'), 'units': rec.get('units'),
                'complete': bool(through and began), 'ran_through_midnight': bool(through),
                'watched_from_midnight': bool(began), 'watched_whole_day': bool(whole), 'first_t': first_t,
                'last_t': last, 'polls': rec.get('polls'), 'longest_gap_s': rec.get('longest_gap_s')}, t=now)
            rec = None
            self._js_mark('now')
        if not isinstance(rec, dict) or not rec.get('day'):
            rec = self._js['day'] = {'day': today, 'first_t': round(now, 3), 'last_t': None, 'polls': 0,
                                     'longest_gap_s': 0.0, 'balance_high': None, 'balance_low': None}
        last = _f(rec.get('last_t'))
        if last is not None and now - last > (_f(rec.get('longest_gap_s')) or 0.0):
            rec['longest_gap_s'] = round(now - last, 1)
        bal = _f(ac.get('balance'))
        if bal is not None:
            if rec.get('balance_high') is None or bal > rec['balance_high']:
                rec['balance_high'] = bal
            if rec.get('balance_low') is None or bal < rec['balance_low']:
                rec['balance_low'] = bal
        day = sf.get('day') or {}
        rec.update(last_t=round(now, 3), polls=(_i(rec.get('polls')) or 0) + 1, balance=bal,
                   equity=_f(ac.get('equity')), high=_f((sf.get('drop') or {}).get('peak')),
                   booked=ac.get('day_realised'), start_balance=_f(day.get('start_balance')),
                   cash=_f(day.get('cash')), own_closed_total=self._own_closed,
                   drop_pct=_f((sf.get('drop') or {}).get('pct')), day_pct=_f(day.get('pct')),
                   streak=_i((sf.get('streak') or {}).get('count')), units=ac.get('units'))
        self._js_mark('day')

    # ── the samples: one line of figures a minute ──
    def _sample(self, snap, now, good):
        """This poll's figures into the running minute; when a new minute begins the one before is queued for
        logs/<SYMBOL>_<day>_samples.jsonl. A skipped poll counts as a poll and adds nothing else: a minute of
        skipped polls only is a line of nulls."""
        bucket = int(now // SAMPLE_S)
        a = self._smp
        if a is not None and a['bucket'] != bucket:
            self._sample_out(a)
            a = None
        if a is None:
            a = self._smp = {'bucket': bucket, 'polls': 0, 'skipped': 0, 'spread_n': 0, 'spread_sum': 0.0,
                             'spread_min': None, 'spread_max': None, 'ticks': 0, 'gap_max': None, 'offset': None,
                             'ms_n': 0, 'ms_sum': 0.0, 'ms_max': None, 'trace_n': 0, 'trace_sum': 0.0,
                             'trace_max': None, 'held': 0, 'last': {}}
        a['polls'] += 1
        h = snap.get('health') or {}
        if not good:
            a['skipped'] += 1
            a['last']['ping_ms'] = h.get('ping_ms')
            return
        m, ac, sf, f = (snap.get(k) or {} for k in ('market', 'account', 'safety', 'foreign'))
        bid, ask, tick_t = _f(m.get('bid')), _f(m.get('ask')), _f(m.get('tick_t'))
        if bid is not None and ask is not None:
            sp = ask - bid
            a['spread_n'] += 1
            a['spread_sum'] += sp
            a['spread_min'] = sp if a['spread_min'] is None else min(a['spread_min'], sp)
            a['spread_max'] = sp if a['spread_max'] is None else max(a['spread_max'], sp)
        if tick_t is not None:
            if tick_t != self._smp_tick:
                a['ticks'] += 1                # a poll whose tick is not the one of the poll before
                self._smp_tick = tick_t
            gap = now - tick_t
            a['gap_max'] = gap if a['gap_max'] is None else max(a['gap_max'], gap)
            if h.get('market_live'):           # the smallest of the minute: the clocks' offset (no tick is that fresh
                a['offset'] = gap if a['offset'] is None else min(a['offset'], gap)   # on a closed market)
        for name, key in (('ms', 'loop_ms'), ('trace', 'trace_ms')):
            x = _f(h.get(key))
            if x is not None:
                a[name + '_n'] += 1
                a[name + '_sum'] += x
                a[name + '_max'] = x if a[name + '_max'] is None else max(a[name + '_max'], x)
        if snap.get('open_hold'):
            a['held'] += 1
        own = 0
        tv = (snap.get('turtle') or {}).get('trade') if snap.get('turtle') else (snap.get('basket') or {}).get('open')
        if isinstance(tv, dict):
            own = ((_i(tv.get('buy_count')) or 0) + (_i(tv.get('sell_count')) or 0) if tv.get('both_sides')
                   else len(tv.get('legs') or []))
        a['last'] = {'bid': bid, 'ask': ask, 'balance': ac.get('balance'), 'equity': ac.get('equity'),
                     'margin': ac.get('margin'), 'margin_free': ac.get('margin_free'),
                     'margin_level': ac.get('margin_level'), 'floating_own': ac.get('floating_own'),
                     'floating_account': ac.get('floating_account'), 'positions_own': own,
                     'positions_foreign': _i(f.get('positions')), 'drop_pct': _f((sf.get('drop') or {}).get('pct')),
                     'day_pct': _f((sf.get('day') or {}).get('pct')),
                     'streak': _i((sf.get('streak') or {}).get('count')), 'units': ac.get('units'),
                     'ping_ms': h.get('ping_ms')}

    def _sample_out(self, a):
        t = a['bucket'] * SAMPLE_S
        last = a['last']
        line = {
            't': t, 'utc': _iso(t), 'polls': a['polls'], 'skipped': a['skipped'],
            'bid': last.get('bid'), 'ask': last.get('ask'),
            'spread_min': _f(a['spread_min'], 8), 'spread_max': _f(a['spread_max'], 8),
            'spread_avg': _f(a['spread_sum'] / a['spread_n'], 8) if a['spread_n'] else None,
            'ticks_seen': a['ticks'] if a['polls'] > a['skipped'] else None,
            'tick_gap_max_s': _f(a['gap_max'], 3), 'clock_offset_s': _f(a['offset'], 3),
            'balance': last.get('balance'), 'equity': last.get('equity'), 'margin': last.get('margin'),
            'margin_free': last.get('margin_free'), 'margin_level': last.get('margin_level'),
            'floating_own': last.get('floating_own'), 'floating_account': last.get('floating_account'),
            'positions_own': last.get('positions_own'), 'positions_foreign': last.get('positions_foreign'),
            'drop_pct': last.get('drop_pct'), 'day_pct': last.get('day_pct'), 'streak': last.get('streak'),
            'units': last.get('units'),
            'poll_ms_avg': _f(a['ms_sum'] / a['ms_n'], 1) if a['ms_n'] else None, 'poll_ms_max': _f(a['ms_max'], 1),
            'trace_ms_avg': _f(a['trace_sum'] / a['trace_n'], 2) if a['trace_n'] else None,
            'trace_ms_max': _f(a['trace_max'], 2),
            'suppressed_polls': a['held'] if a['polls'] > a['skipped'] else None, 'ping_ms': last.get('ping_ms'),
        }
        try:
            text = dumps(self._mask(line))
        except Exception:
            return
        with self._lock:
            self._sq.append((t, text))
            if len(self._sq) > 2000:
                del self._sq[:-2000]

    # ── old files that go: temp files of a killed process, daily files beyond the newest 400 ──
    def _tidy(self, now):
        """At the start, at every new UTC day and once an hour (the day files of logs/: LogWriter, on the same
        rhythm). Outside mt5_lock (the poll hooks call it)."""
        day = _day(now)
        if self._tidy_t is not None and day == self._tidy_day and 0.0 <= now - self._tidy_t < TIDY_EVERY_S:
            return
        self._tidy_t, self._tidy_day = now, day
        self._temp_sweep()
        self._daily_files()

    def _own_files(self):
        """{folder: the names of the files this bot writes there}: the bot's output folder itself and its state
        folder. Only temp files of these names are ever swept; no folder below them is looked into (dash_env,
        journal, daily_trade, logs)."""
        s, g = self.symbol, self._cfg
        top = {f'{s}_trace.json', f'{s}_bars.json', f'{s}_trades.json', f'{s}.json', 'account.json',
               str(g('ACTIVE_CONFIG_FILENAME', 'active_config.json'))}
        state = {f'{s}_state.json', f'{s}_turtle.json', f'{s}_turtle_side.json', 'safety_state.json',
                 'safety_closes.json', 'live_start.json', f'{s}_journal_state.json', f'{s}_exit_reasons.json',
                 f'{s}_turtle_trades.json'}
        for getter in ('_state_path', '_turtle_state_path', '_turtle_side_path'):
            try:
                state.add(os.path.basename(getattr(self.bot, getter)(s)))
            except Exception:
                pass
        out = {}
        tops = [self.out_dir] + ([str(g('OUTPUT_DIR'))] if g('OUTPUT_DIR') else [])
        for folder in tops:
            out.setdefault(os.path.abspath(folder), set()).update(top)
        for folder in [os.path.join(t, str(g('STATE_SUBDIR', 'state'))) for t in tops] + [self._state_dir()]:
            out.setdefault(os.path.abspath(folder), set()).update(state)
        return out

    def _temp_sweep(self):
        """Delete temp files a killed process left of the bot's own files ('<file>.tmp', '<file>.<digits>.tmp',
        '<file>.<digits>.<hex>.tmp') that are older than a day. Never anything else: not a state file, not a file
        set aside ('....not-readable-<time>', '....other-account-<time>'), not a file of another name."""
        now = time.time()                      # (a file's age is on the wall clock)
        for folder, names in self._own_files().items():
            try:
                listing = os.listdir(folder)
            except OSError:
                continue
            for name in listing:
                if not temp_file_of(name, names):
                    continue
                path = os.path.join(folder, name)
                try:
                    if os.path.isfile(path) and not os.path.islink(path) \
                            and now - os.stat(path).st_mtime > TEMP_SWEEP_AGE_S:
                        os.remove(path)
                except OSError:
                    continue

    def _daily_files(self):
        """daily_trade/<SYMBOL>/: app.py writes one file per server day (<dd>_<mon>_<yyyy>.json) and never deletes
        one; the newest DAILY_TRADE_KEEP by the date in the name are kept (the History tab reads them). The summary
        file and any other name are not touched."""
        sub = str(self._cfg('DAILY_TRADE_SUBDIR', 'daily_trade'))
        tops = dict.fromkeys(os.path.abspath(t) for t in [self.out_dir, str(self._cfg('OUTPUT_DIR') or self.out_dir)])
        for top in tops:
            folder = os.path.join(top, sub, self.symbol)
            try:
                dated = sorted((d, n) for n in os.listdir(folder) for d in [_daily_date(n)] if d is not None)
            except OSError:
                continue
            for _, name in dated[:max(0, len(dated) - DAILY_TRADE_KEEP)]:
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass

    def _sizing_words(self, snap):
        """' (0.5 x the account balance $1,512.40 = $756.20)': what the unit was counted from; '' when not known."""
        sz = snap.get('sizing') or {}
        ab, sb, share = _f(sz.get('account_balance')), _f(sz.get('sizing_balance')), _f(sz.get('share'))
        if ab is None or sb is None:
            return ''
        if share:
            return f' ({share:g} x the account balance {_usd(ab, signed=False)} = {_usd(sb, signed=False)})'
        return f' (counted from {_usd(sb, signed=False)})'

    # ═════════════════════ the Turtle (STRATEGY = 'turtle'; its loop: MT5TradingBot._process_turtle) ═════════════════════
    # The poll hands over its locals as the basket's does; the book `st` (turtle.py's state) is read, never changed: the
    # rules module's pure functions (add_level, stop_origin, bar_of) and copies only. What changed since the last poll
    # (levels, vote, entry, adds, stop moves, exits, rebuilds) is found by comparing the book with the one of the poll
    # before (_book_sum).

    def _is_turtle(self):
        return self._cfg('STRATEGY') == 'turtle'

    def _T(self):
        """turtle.py as app.py loaded it (the rules)."""
        return getattr(self.app, 'T', None)

    @staticmethod
    def _count(p):
        return _i((p or {}).get('count')) or 0

    def _turtle_params(self):
        g = self._cfg
        system = _i(g('TURTLE_SYSTEM'))
        return {'system': system, 'n_len': g('TURTLE_N_LEN'), 'stop_n': _f(g('TURTLE_STOP_N')),
                'add_n': _f(g('TURTLE_ADD_N')), 'max_legs': _i(g('TURTLE_MAX_LEGS')) or 4, 'tick': _f(g('TURTLE_TICK')) or 0.0,
                'backstop_n': _f(g('TURTLE_BACKSTOP_N')), 'vote_tf': _tf_key(g('TURTLE_VOTE_TF')),
                'vote_bars': g('TURTLE_VOTE_BARS'), 'min_vote_bars': g('_TURTLE_MIN_VOTE_BARS'),
                'd1_bars': g('TURTLE_D1_BARS'), 'min_d1_bars': g('TURTLE_MIN_D1_BARS'),
                'entry_days': 55 if system == 2 else 20, 'failsafe_days': 55 if system == 1 else None,
                'exit_days': 20 if system == 2 else 10, 'pending_s': g('_TURTLE_PENDING_S'),
                'settle_s': _f(g('_TURTLE_SETTLE_S')) or 0.0}

    def _symbol_facts(self):
        """symbol_info() once (again every 60 s while it fails): digits, contract size, volumes, the stops / freeze
        levels and the swaps, logged once (INFO CONFIG). {} while unknown."""
        if self._facts is not None:
            return self._facts
        now = self._now()
        if self._facts_t is not None and now - self._facts_t < 60.0:
            return {}
        self._facts_t = now
        with self.bot.mt5_lock:
            info = self.app.mt5.symbol_info(self.mt5_symbol)
        if info is None:
            return {}

        def g(name):
            return getattr(info, name, None)
        f = {'digits': _i(g('digits')), 'point': _f(g('point')), 'contract_size': _f(g('trade_contract_size')),
             'volume_min': _f(g('volume_min')), 'volume_step': _f(g('volume_step')), 'volume_max': _f(g('volume_max')),
             'stops_level': _i(g('trade_stops_level')), 'freeze_level': _i(g('trade_freeze_level')),
             'swap_long': _f(g('swap_long')), 'swap_short': _f(g('swap_short')), 'swap_mode': _i(g('swap_mode')),
             'trade_mode': _i(g('trade_mode')), 'filling_mode': _i(g('filling_mode')),
             'currency_profit': g('currency_profit')}
        self._facts = f
        if self._digits is None and f['digits'] is not None:
            self._digits = f['digits']

        def w(x, unit=''):
            return 'n/a' if x is None else f'{x:g}{unit}' if isinstance(x, float) else f'{x}{unit}'
        self._rec('INFO', 'CONFIG', f"symbol {self.mt5_symbol}: digits {w(f['digits'])}, contract size "
                  f"{w(f['contract_size'])}, volume {w(f['volume_min'])} .. {w(f['volume_max'])} step {w(f['volume_step'])}, "
                  f"stops level {w(f['stops_level'], ' points')}, freeze level {w(f['freeze_level'], ' points')}, swap long "
                  f"{w(f['swap_long'])} / short {w(f['swap_short'])} (mode {w(f['swap_mode'])})",
                  kv={k: v for k, v in f.items() if v is not None})
        return f

    # ── the loop's start ──
    def _turtle_loop_start(self, c):
        bot, T = self.bot, self._T()
        p = self._turtle_params()
        self._rec('INFO', 'START', f"trading loop started for {self.symbol} ({self.mt5_symbol} at the terminal): the Turtle, "
                  f"System {p['system']}", kv={
                      'branch': self._cfg('BRANCH'), 'design': self._cfg('DESIGN_NAME'), 'strategy': 'turtle',
                      'system': p['system'], 'magic': self._cfg('MAGIC'), 'mode': getattr(bot, 'mode', None),
                      'version': self._cfg('VERSION'), 'pid': os.getpid(), 'python': sys.version.split()[0],
                      'out_dir': self.out_dir, 'schema': SCHEMA})
        summary = self._call('design_summary')
        if summary:
            self._rec('INFO', 'CONFIG', 'design: ' + str(summary))
        if T is not None:
            self._rec('INFO', 'CONFIG', 'rules: ' + T.describe(p['system']))
        for name, value in self._constants():
            self._rec('INFO', 'CONFIG', f'{name} = {kv_text(value)}')
        entry = (f"{p['entry_days']}-day" if p['system'] == 2 else
                 f"20-day (the 55-day failsafe after a winning 20-day breakout)")
        self._rec('INFO', 'CONFIG', f"the Turtle as it runs: entries on the {entry} breakout + / - {p['tick']:g} of the "
                  f"closed UTC D1 bars, exit channel {p['exit_days']}-day, N = Wilder's RMA({p['n_len']}) of the D1 true "
                  f"range, one stop for all legs {p['stop_n']:g}N from the best fill (or the exit channel if tighter, never "
                  f"loosened), an add every {p['add_n']:g}N (N frozen at the entry) up to {p['max_legs']} legs, a broker "
                  f"backstop {p['backstop_n']:g}N beyond the stop on every leg, entries only with the {p['vote_tf']} vote of "
                  f"closed bars ({p['vote_bars']} read, at least {p['min_vote_bars']}), {p['d1_bars']} closed D1 bars read "
                  f"(at least {p['min_d1_bars']}); no target, no trading window (the manual brake stops new entries)", kv=p)
        cfg = getattr(bot, 'symbols_config', None) or {}
        sc = c.sym_cfg or {}
        self._rec('INFO', 'CONFIG', f"symbols.json: brake {cfg.get('brake', 0)}, mtqty {cfg.get('mtqty')}, step_up_balance "
                  f"{sc.get('step_up_balance')}, unit_max_limit {sc.get('unit_max_limit')} (the Turtle has no trading window)",
                  kv={'symbols_json': cfg})
        st = c.st if isinstance(c.st, dict) else {}
        try:
            path = bot._turtle_state_path(self.symbol)
        except Exception:
            path = None
        if c._history_done:
            self._rec('INFO', 'STATE', 'Turtle book restored: ' + self._book_words(st), kv={'path': path},
                      data={'book': st})
        else:
            self._rec('INFO', 'STATE', "no Turtle state file of this bot: an open trade is rebuilt from the terminal (the "
                      "legs from its positions, N at the entry and the stop from the D1 bars), the day's used orders and "
                      'the last exit from the deal history', kv={'path': path})
        names = [os.path.basename(x) for x in (self.paths['trace'], self.paths['bars'], self.paths['trades'])]
        self._rec('INFO', 'START', 'files: ' + ', '.join(names) + f', state/{os.path.basename(self.journal_path)}, '
                  + self._files_words(), kv={'out_dir': self.out_dir})
        self._prev['turtle'] = self._book_sum(st)
        self._book_ref = c.st if isinstance(c.st, dict) else None
        self._journal_load()

    @_guarded
    def turtle_state_saved(self, st):
        """MT5TradingBot._save_turtle_state wrote the book."""
        self._rec('DEBUG', 'STATE', f'Turtle book saved: {self._book_words(st)}', data={'book': st})

    # ── one poll ──
    def _poll_turtle(self, c):
        """As _poll: every step on its own, so one that raises leaves the others running."""
        now = self._now()
        self.polls += 1
        if isinstance(c.st, dict):
            self._book_ref = c.st
        orders = self._take_orders()
        S = functools.partial(self._step, 'poll')
        facts = S('_symbol_facts', self._symbol_facts)
        facts = facts if isinstance(facts, dict) else {}
        digits = facts.get('digits')
        if digits is None:
            digits = _i((getattr(self.bot, '_digits', None) or {}).get(self.mt5_symbol))
        snap = self._base(now)
        for key, fn, args, kw in (('health', self._health, (c, now), {'live': bool(c.live), 'tick': c.tick}),
                                  ('account', self._account, (c,), {}),
                                  ('market', self._turtle_market, (c, digits), {})):
            v = S(fn.__name__, fn, *args, **kw)
            snap[key] = None if v is _FAILED else v
        S('_handed_over', self._handed_over, c, snap)
        snap['basket'] = None
        tv = S('_turtle_section', self._turtle_section, c, now, digits, orders, facts)
        snap['turtle'] = None if tv is _FAILED else tv
        dec = _FAILED if tv is _FAILED else S('_turtle_decide', self._turtle_decide, c, snap, orders, digits)
        failed = dec is _FAILED
        if failed:
            dec = self._failed_decision(orders, '_turtle_section' if tv is _FAILED else '_turtle_decide')
        snap['decision'] = dec
        if not failed:
            self._transitions_step(self._turtle_transitions, self._keep_turtle, c, snap, dec, orders, now, digits)
        S('_decision_line', self._decision_line, dec, now)
        self._last_snapshot = snap
        S('_write_trace', self._write_trace, snap, dec, now)
        S('_track_trade', self._track_trade, c, snap, dec, orders, now)
        S('_after_poll', self._after_poll, snap, now, True)
        tick = c.tick
        sig = None if tick is None else (getattr(tick, 'time_msc', None) or getattr(tick, 'time', None),
                                         _f(getattr(tick, 'bid', None)))
        S('_bars', self._bars, c, now, digits, sig=sig, overlay=lambda: self._turtle_overlay(c, digits))
        S('_trades', self._trades, c, snap, now, digits)
        S('_heartbeat', self._heartbeat, dec, snap, now)
        self._prev['positions'] = {'BUY': self._count(c.buy_positions), 'SELL': self._count(c.sell_positions)}
        self._last_poll_t = now
        self._flush()
        S('_jstate_save', self._jstate_save, now)

    def _turtle_market(self, c, digits):
        bid, ask = _f(c.bid), _f(c.ask)
        ms = c.market_status or {}
        tick_t = _f(c.now)
        return {'bid': bid, 'ask': ask, 'spread': _f(ask - bid, 6) if bid is not None and ask is not None else None,
                'tick_t': tick_t, 'tick_utc': _iso(tick_t), 'digits': digits,
                'server_time_utc': _iso(_epoch(c.server_time)), 'status': ms.get('status'),
                'minutes_since_activity': _f(ms.get('minutes_since_last'), 2),
                'lookback_minutes': ms.get('lookback_minutes'), 'message': ms.get('message'),
                'in_window': None, 'brake': bool(c.brake_manual), 'brake_manual': c.brake_manual,
                'window': 'none: the Turtle trades around the clock (the manual brake stops new entries)'}

    # ── the turtle block of the trace ──
    def _turtle_section(self, c, now, digits, orders, facts):
        T = self._T()
        p = self._turtle_params()
        st = c.st if isinstance(c.st, dict) else {}
        lv = st.get('levels') or {}
        dd = 6 if digits is None else digits
        bid, ask, tnow = _f(c.bid), _f(c.ask), _f(c.now)
        rows_t = c.rows_t
        n_d1 = len(rows_t) if rows_t is not None else 0
        n = _f(lv.get('n'))
        tick = p['tick']
        use20 = lv.get('use20')
        entry_days = p['entry_days'] if p['system'] == 2 else (20 if use20 else 55)
        levels = None
        if lv:
            from_t = _f(lv.get('from_time'))
            levels = {k: lv.get(k) for k in ('bar_time', 'from_time', 'system', 'n', 'buy', 'sell', 'stop_dist', 'add_step',
                                              'trail_long', 'trail_short', 'use20', 'ok')}
            levels.update(bar_utc=_iso(lv.get('bar_time')), from_utc=_iso(from_t),
                          until_t=from_t + 86400.0 if from_t is not None else None,
                          until_utc=_iso(from_t + 86400.0) if from_t is not None else None,
                          n_pct=_f(100.0 * n / bid, 3) if (n and bid) else None)
        ch = self._turtle_channels(c, p)
        high_e = _f(lv.get('buy') - tick, dd) if _f(lv.get('buy')) is not None else None
        low_e = _f(lv.get('sell') + tick, dd) if _f(lv.get('sell')) is not None else None
        channels = {
            'bar_t': lv.get('bar_time'), 'bar_utc': _iso(lv.get('bar_time')),
            'entry': {'days': entry_days, 'high': high_e, 'low': low_e,
                      'rule': f'buy level = the {entry_days}-day high + {tick:g}, sell level = the {entry_days}-day low - '
                              f'{tick:g} (the closed D1 bars, the last one included)'},
            'exit': {'days': p['exit_days'], 'long': _f(lv.get('trail_long')), 'short': _f(lv.get('trail_short')),
                     'rule': f"a long's stop is raised to the {p['exit_days']}-day low, a short's lowered to the "
                             f"{p['exit_days']}-day high, at every D1 close (never loosened)"},
            'all': (ch or {}).get('all'), 'bar': (ch or {}).get('bar'),
        }
        filt = None
        if p['system'] == 1:
            filt = {'use20': use20, 'levels_from': None if use20 is None else ('20-day' if use20 else '55-day failsafe'),
                    'hypothetical': (ch or {}).get('s1'),
                    'rule': "a hypothetical one-unit System 1 on the D1 bars (every 20-day breakout while it is flat, a 2N "
                            "stop, the previous day's 10-day exit, no adds, no votes): use20 is true only while it is flat "
                            "and its last trade did not make money; otherwise only the 55-day failsafe levels are traded"}
        d1 = {'bars': n_d1, 'asked': p['d1_bars'], 'min_bars': p['min_d1_bars'], 'enough': c.rows is not None,
              'got_last_read': _i(c.got), 'last_bar_t': int(rows_t[-1]) if n_d1 else None,
              'last_bar_utc': _iso(int(rows_t[-1])) if n_d1 else None,
              'next_close_t': (math.floor(tnow / 86400.0) + 1) * 86400.0 if tnow is not None else None}
        d1['next_close_utc'] = _iso(d1['next_close_t'])
        # stale: a minute after 00:00 UTC the terminal has not given the D1 bar that closed; the bot goes on with the
        # levels (and the stop) of the bar before, and asks again every poll
        until = (levels or {}).get('until_t')
        d1['stale'] = bool(until is not None and tnow is not None and tnow > until + 60.0)
        vote = self._turtle_vote(c, p)
        armed = bool(st.get('armed'))
        used_t, used_by = self._prev.get('used_t'), self._prev.get('used_by')
        if used_t is None and not armed and st.get('side') and st.get('entry_row') == st.get('row'):
            used_t, used_by = _f(st.get('entry_time')), {1: 'BUY', -1: 'SELL'}.get(st.get('side'))
        lx = _f(st.get('last_exit_time'))
        in_exit_bar = bool(T is not None and lx is not None and tnow is not None and T.bar_of(tnow) <= T.bar_of(lx))
        buy, sell = _f(lv.get('buy')), _f(lv.get('sell'))
        o = {
            'state': 'none' if not lv else ('armed' if armed else 'used'), 'armed': armed,
            'from_t': (levels or {}).get('from_time'), 'from_utc': (levels or {}).get('from_utc'),
            'until_t': (levels or {}).get('until_t'), 'until_utc': (levels or {}).get('until_utc'),
            'buy': None if buy is None else {
                'level': buy, 'judged_on': 'ask', 'price_now': ask, 'vote_needed': 1,
                'distance': _f(buy - ask, dd) if ask is not None else None,
                'distance_n': _f((buy - ask) / n, 3) if (ask is not None and n) else None,
                'reached': ask is not None and ask >= buy, 'channel': f'{entry_days}-day high + {tick:g}'},
            'sell': None if sell is None else {
                'level': sell, 'judged_on': 'bid', 'price_now': bid, 'vote_needed': -1,
                'distance': _f(bid - sell, dd) if bid is not None else None,
                'distance_n': _f((bid - sell) / n, 3) if (bid is not None and n) else None,
                'reached': bid is not None and bid <= sell, 'channel': f'{entry_days}-day low - {tick:g}'},
            'used_t': used_t, 'used_utc': _iso(used_t), 'used_by': used_by,
            'last_exit_t': lx, 'last_exit_utc': _iso(lx), 'in_exit_bar': in_exit_bar,
            'rule': 'one entry per D1 bar: a fill uses both orders until the next D1 close (00:00 UTC) arms new ones; an '
                    'exit later that day does not re-arm them; no entry in the M1 bar of an exit',
        }
        return {
            'system': p['system'], 'rules': T.describe(p['system']) if T is not None else None, 'params': p,
            'd1': d1, 'n': n, 'levels': levels, 'channels': channels, 'filter': filt, 'vote': vote, 'orders': o,
            'new_trade': None if st.get('side') else self._turtle_new_trade(c, lv, p, dd, facts),
            'trade': self._turtle_trade(c, st, digits, orders, facts, p),
            'pending_fill': bool(c.pending), 'hold': bool(c.hold), 'closing': bool(st.get('closing')),
            'units_rule': ("the unit is fixed at the first fill (from this bot's share of the account balance then); "
                           'every leg = unit x mtqty lot'),
            'book': self._book_copy(st),
        }

    @staticmethod
    def _book_copy(st):
        """A copy of the book (the trace keeps snapshots; the bot changes its book in place)."""
        if not isinstance(st, dict):
            return None
        out = dict(st)
        out['legs'] = [dict(x) for x in st.get('legs') or []]
        out['levels'] = dict(st['levels']) if isinstance(st.get('levels'), dict) else st.get('levels')
        return out

    def _turtle_channels(self, c, p):
        """The 10 / 20 / 55-day channels of the last closed D1 bar with the day of each extreme, that bar, and (System
        1) the hypothetical trade of its filter: from the D1 bars the bot read, once per new D1 bar."""
        rows_t, d1 = c.rows_t, c.d1
        if rows_t is None or not len(rows_t):
            return None
        key = (len(rows_t), int(rows_t[-1]))
        if key == self._ch_key:
            return self._ch
        out = None
        if isinstance(d1, dict) and d1.get('t') is not None and len(d1['t']) == len(rows_t) \
                and int(d1['t'][-1]) == int(rows_t[-1]):
            t = np.asarray(d1['t'], np.int64)
            o, h, l, cl = (np.asarray(d1[k], float) for k in ('o', 'h', 'l', 'c'))
            allc = {}
            for k in (10, 20, 55):
                if len(h) >= k:
                    ih, il = int(np.argmax(h[-k:])), int(np.argmin(l[-k:]))
                    allc[str(k)] = {'high': float(h[-k:][ih]), 'high_t': int(t[-k + ih]), 'high_utc': _iso(int(t[-k + ih])),
                                    'low': float(l[-k:][il]), 'low_t': int(t[-k + il]), 'low_utc': _iso(int(t[-k + il]))}
            tr = float(h[-1] - l[-1]) if len(h) < 2 else float(max(h[-1] - l[-1], abs(h[-1] - cl[-2]), abs(l[-1] - cl[-2])))
            out = {'all': allc, 'bar': {'t': int(t[-1]), 'utc': _iso(int(t[-1])), 'o': float(o[-1]), 'h': float(h[-1]),
                                        'l': float(l[-1]), 'c': float(cl[-1]), 'true_range': tr}}
            if p['system'] == 1 and c.rows is not None:
                try:
                    out['s1'] = _s1_hypothetical(o, h, l, np.asarray(c.rows['n'], float), t, p['tick'], self._T())
                except Exception:
                    out['s1'] = None
        self._ch_key, self._ch = key, out
        return out

    def _turtle_vote(self, c, p):
        vi = c.vote_info if isinstance(c.vote_info, dict) else {}
        r, m = vi.get('rsi') or {}, vi.get('macd') or {}
        fresh = bool(c.vote_fresh)
        last = _sign(_i(c.vote))
        vbar = _f(c.vote_bar)
        vote_s = _f(c.vote_s) or 900.0
        vq = _i(c.vote_q)
        s = self._vote_series(c) or {}
        b15 = c.b15
        sig = s.get('signal_now')
        tf = p['vote_tf']
        g = self._cfg
        return {
            'tf': tf, 'value': last if fresh else None, 'last': last, 'fresh': fresh,
            'allows': ('BUY' if last == 1 else 'SELL' if last == -1 else None) if fresh else None,
            'bar_t': vbar, 'bar_utc': _iso(vbar), 'bar_close_t': vbar + vote_s if vbar is not None else None,
            'bar_close_utc': _iso(vbar + vote_s) if vbar is not None else None,
            'next_read_t': (vq + 1) * vote_s + p['settle_s'] if vq is not None else None,
            'next_read_utc': _iso((vq + 1) * vote_s + p['settle_s']) if vq is not None else None,
            'bars': len(b15['c']) if isinstance(b15, dict) and b15.get('c') is not None else None,
            'asked': p['vote_bars'], 'min_bars': p['min_vote_bars'],
            'rsi': {'vote': _sign(_i(r.get('sign'))), 'pivot': _f(r.get('value'), 2), 'pivot_side': r.get('side'),
                    'bars_ago': _i(r.get('bars_ago')), 'slope': _f(r.get('slope'), 4), 'now': s.get('rsi_now'),
                    'ob': g('RSI_PEAK_OB'), 'os': g('RSI_PEAK_OS'), 'series': s.get('rsi')},
            'macd': {'vote': _sign(_i(m.get('sign'))), 'pivot': _f(m.get('value'), 6), 'pivot_side': m.get('side'),
                     'bars_ago': _i(m.get('bars_ago')), 'slope': _f(m.get('slope'), 6), 'now': s.get('hist_now'),
                     'line': s.get('macd_now'), 'signal': sig,
                     'side_rule': None if sig is None else ('high' if sig > 0 else 'low' if sig < 0 else 'none'),
                     'series': s.get('hist'), 'signal_series': s.get('signal')},
            't': s.get('t'), 'close': s.get('close'),
            'rule': (f"the RSI({g('RSI_LENGTH')}) and the MACD({g('MACD_FAST')},{g('MACD_SLOW')},{g('MACD_SIGNAL')}) "
                     f"histogram pivot-slope votes of the last CLOSED {tf} bar (a pivot: {g('PIVOT_WIDTH')} bars each side, "
                     f"within {g('PEAK_LOOKBACK')} bars; RSI highs >= {g('RSI_PEAK_OB')}, lows <= {g('RSI_PEAK_OS')}; the "
                     f"MACD pivot side from its signal line): +1 when both are +1, -1 when both are -1, else 0; read "
                     f"{p['settle_s']:g} s after every {tf} close"),
        }

    def _vote_series(self, c):
        """The last VOTE_SERIES_N closed M15 bars' close, RSI, MACD line, signal line and histogram (the chart under the
        price): computed again from the poll's closed bars with the bot's indicator, once per new M15 bar."""
        b15, key = c.b15, _f(c.vote_bar)
        if key is not None and key == self._vs_key:
            return self._vs
        out = None
        if (key is not None and isinstance(b15, dict) and b15.get('c') is not None and len(b15['c']) >= 30
                and int(b15['t'][-1]) == int(key)):
            import pandas as pd
            ind = getattr(self.bot, 'indicator', None)
            g = self._cfg
            s = pd.Series(np.asarray(b15['c'], float))
            rsi = ind.calculate_rsi(s, length=g('RSI_LENGTH'), ma_type=g('RSI_MA_TYPE'))
            macd = ind.calculate_macd(s, fast=g('MACD_FAST'), slow=g('MACD_SLOW'), signal=g('MACD_SIGNAL'))
            k = VOTE_SERIES_N

            def tail(x, nd):
                return [None if not math.isfinite(v) else round(float(v), nd) for v in np.asarray(x, float)[-k:]]
            out = {'t': np.asarray(b15['t'], np.int64)[-k:].tolist(), 'close': tail(s, 6), 'rsi': tail(rsi, 2),
                   'macd': tail(macd['macd'], 6), 'signal': tail(macd['signal'], 6), 'hist': tail(macd['hist'], 6),
                   'rsi_now': _f(rsi.iloc[-1], 2), 'macd_now': _f(macd['macd'].iloc[-1], 6),
                   'signal_now': _f(macd['signal'].iloc[-1], 6), 'hist_now': _f(macd['hist'].iloc[-1], 6)}
        self._vs_key, self._vs = key, out
        return out

    def _turtle_new_trade(self, c, lv, p, dd, facts):
        """What a trade entered now would get (N frozen, the stop, the next add, the backstop) on each side: entered at
        the level, or at the quote when the price is already beyond it (the bot enters at the market)."""
        n, sd_, step = _f(lv.get('n')), _f(lv.get('stop_dist')), _f(lv.get('add_step'))
        if not (lv and lv.get('ok') and n and sd_ and step):
            return None
        units = _i(c.units) or 1
        mtqty = _f(c.mtqty) or 0.01
        lots = round(units * mtqty, 2)
        contract = facts.get('contract_size')
        bsn = p['backstop_n'] or 0.0
        sz = c._sizing if isinstance(c._sizing, dict) else {}
        out = {'units': units, 'lots': lots, 'n': n, 'stop_dist': sd_, 'add_step': step, 'max_legs': p['max_legs'],
               'balance': _f(sz.get('sizing_balance'), 2), 'account_balance': _f(sz.get('account_balance'), 2)}
        for key, k in (('buy', 1), ('sell', -1)):
            level = _f(lv.get('buy' if k == 1 else 'sell'))
            q = _f(c.ask if k == 1 else c.bid)
            if level is None:
                out[key] = None
                continue
            entry = level if q is None else (max(level, q) if k == 1 else min(level, q))
            stop, origin = entry - k * sd_, '2N'
            tr = _f(lv.get('trail_long' if k == 1 else 'trail_short'))
            if tr is not None and ((k == 1 and tr > stop) or (k == -1 and tr < stop)):
                stop, origin = tr, 'channel'
            out[key] = {'entry': round(entry, dd), 'at': 'level' if entry == level else ('ask' if k == 1 else 'bid'),
                        'stop': round(stop, dd), 'stop_origin': origin, 'next_add': round(entry + k * step, dd),
                        'backstop': round(stop - k * bsn * n, dd),
                        'pnl_at_stop': _f(k * (stop - entry) * lots * contract, 2) if contract else None,
                        'judged_on': 'bid' if k == 1 else 'ask'}
        return out

    def _turtle_leg(self, p_, k, digits):
        leg = self._leg(p_, digits)
        leg['n'] = k
        return leg

    def _turtle_trade(self, c, st, digits, orders, facts, p):
        """The trade this poll held (or closed, or just opened): legs, P/L, the one stop and where it comes from, the next
        add, the backstops. None when flat."""
        nb, ns = self._count(c.buy_positions), self._count(c.sell_positions)
        if nb and ns:
            return {'both_sides': True, 'buy_count': nb, 'sell_count': ns}
        bs, ss = _sig_name(c.buy_signal), _sig_name(c.sell_signal)
        closing_now = bs == 'CLOSE_BUY' or ss == 'CLOSE_SELL'
        bk = st if st.get('side') else ((self._prev.get('turtle') or {}) if closing_now else st)
        side = _i(bk.get('side')) or 0
        if not side and not (nb or ns):
            return None
        pos = (c.buy_positions if (side == 1 or (not side and nb)) else c.sell_positions) or {}
        plist = sorted(pos.get('positions') or [], key=lambda x: (_pos_time(x) or 0.0, _i(getattr(x, 'ticket', 0)) or 0))
        if not side:                         # positions the book could not take over (UNMANAGED)
            legs = [self._turtle_leg(x, k + 1, digits) for k, x in enumerate(plist)]
            return {'side': 'BUY' if nb else 'SELL', 'known_to_bot': False, 'legs': legs, 'legs_count': len(legs),
                    'pnl': _f(pos.get('total_profit')), 'stop': None, 'next_add': None,
                    'note': 'positions of this bot the book could not take over (they predate the D1 history): not managed'}
        dd = 6 if digits is None else digits
        buy = side == 1
        by_id = {_pos_id(x): x for x in plist}
        sent = {o['order']: o for o in orders if o['done'] and o['kind'] in ('open', 'add') and o['order']}
        units = _i(bk.get('units')) or 1
        mtqty = _f(c.mtqty) or 0.01
        raw = bk.get('legs') or []
        legs = []
        for k, leg in enumerate(raw):
            tid, price, t = (leg if isinstance(leg, tuple) else (leg.get('ticket'), leg.get('price'), leg.get('time')))
            x = by_id.get(_i(tid))
            if x is not None:
                one = self._turtle_leg(x, k + 1, digits)
            else:                            # filled by the bot, not listed by the terminal yet
                o = sent.get(_i(tid)) or {}
                one = {'n': k + 1, 'ticket': _i(tid), 'id': _i(tid), 'open_t': _f(t), 'open_utc': _iso(t),
                       'price': _f(price), 'lots': o.get('result_volume') or round(units * mtqty, 2), 'profit': None,
                       'swap': None, 'backstop': o.get('sl') or None, 'tp': None, 'listed': False}
            legs.append(one)
        fills = [x['price'] for x in legs if x['price'] is not None]
        sdist, step = _f(bk.get('stop_dist')), _f(bk.get('add_step'))
        if closing_now and not st.get('side'):
            stop, origin = _f(c.stop), c.origin
        else:
            stop, origin = _f(bk.get('stop')), self._origin_of(bk)
        best = (max(fills) if buy else min(fills)) if fills else None
        px = _f(c.bid if buy else c.ask)
        q = _f(c.ask if buy else c.bid)
        contract = facts.get('contract_size')
        lots = round(sum(x['lots'] or 0.0 for x in legs), 2)
        full = len(legs) >= p['max_legs']
        nxt = None if (full or not fills or step is None) else round(legs[-1]['price'] + (step if buy else -step), dd)
        lv = st.get('levels') or {}
        et = _f(bk.get('entry_time'))
        jr = self._journal_view([x['id'] for x in legs])
        entry_level = (jr or {}).get('entry_level')
        if entry_level is None and lv and bk.get('entry_row') is not None and lv.get('bar_time') == bk.get('entry_row'):
            entry_level = _f(lv.get('buy' if buy else 'sell'))        # the levels in force are the entry bar's
        return {
            'side': 'BUY' if buy else 'SELL', 'units': units, 'lots_per_leg': round(units * mtqty, 2), 'lots': lots,
            'legs': legs, 'legs_count': len(legs), 'max_legs': p['max_legs'], 'full': full,
            'n_entry': _f(bk.get('n_entry')), 'stop_dist': sdist, 'add_step': step,
            'entry_t': et, 'entry_utc': _iso(et), 'age_s': _f(self._now() - et, 1) if et else None,
            'entry_d1_t': bk.get('entry_row'), 'entry_d1_utc': _iso(bk.get('entry_row')),
            'entry_level': entry_level,
            'avg_price': _f(sum((x['price'] or 0) * (x['lots'] or 0) for x in legs) / lots, dd) if lots else None,
            'best_fill': best, 'pnl': _f(pos.get('total_profit')),
            'judged_on': 'bid' if buy else 'ask', 'price_now': px,
            'stop': stop, 'stop_origin': origin, 'stop_text': self._origin_words(origin, 'BUY' if buy else 'SELL'),
            'stop_2n': _f(best - sdist if buy else best + sdist, dd) if (best is not None and sdist) else None,
            'stop_channel': _f(bk.get('trail_best')), 'stop_floor': _f(bk.get('stop_floor')),
            'exit_channel_now': _f(lv.get('trail_long' if buy else 'trail_short')),
            'to_stop': _f((px - stop) if buy else (stop - px), dd) if (px is not None and stop is not None) else None,
            'pnl_at_stop': _f(sum((x['lots'] or 0) * contract * ((stop - x['price']) if buy else (x['price'] - stop))
                                  for x in legs if x['price'] is not None), 2) if (contract and stop is not None) else None,
            'next_add': nxt, 'next_add_judged_on': 'ask' if buy else 'bid', 'add_price_now': q,
            'to_next_add': _f((nxt - q) if buy else (q - nxt), dd) if (nxt is not None and q is not None) else None,
            'adds_left': max(0, p['max_legs'] - len(legs)),
            'backstop_prices': [x['backstop'] for x in legs if x.get('backstop')],
            'closing': closing_now or bool(bk.get('closing')),
            'closed_now': closing_now and not st.get('side'),
            'pending_fill': bool(c.pending), 'known_to_bot': True,
            'journal': jr,
        }

    def _outside_of(self, tr, st):
        """The legs of this trade app.py found closed outside the bot (its TURTLE_LEG_CLOSED_OUTSIDE events since the
        trade's entry), oldest first; [] when the trace saw none."""
        et = _f((tr or {}).get('entry_t'))
        if et is None and isinstance(st, dict):
            et = _f(st.get('entry_time'))
        return sorted(k for k, ev in self._legs_outside.items()
                      if k is not None and (et is None or (_f(ev.get('t')) or 0.0) >= et))

    @staticmethod
    def _legs_words(gone):
        return f'leg(s) {gone} were' if gone else 'a leg was'

    def _log_outside(self, gone, side, pb, d, cb=None):
        """The WARN TRADE line of legs app.py found closed outside the bot (once per leg): at or beyond the trade's stop
        (beyond_stop true: the deal history shows it; null: it does not show them yet) -- the stop was passed, the other
        legs are closed at once -- or inside it (false: by hand), and the trade goes on."""
        new = [g for g in gone if g not in self._outside_logged]
        if not new:
            return
        self._outside_logged |= set(new)
        evs = [self._legs_outside.get(_i(g)) or {} for g in new]
        flags = [ev.get('beyond_stop') for ev in evs]
        beyond = True if any(f is True for f in flags) else (None if any(f is None for f in flags) else False)
        stop = next((_f(ev.get('stop')) for ev in evs if _f(ev.get('stop')) is not None), None)
        stop = _f((pb or {}).get('stop')) if stop is None else stop
        left = next((_i(ev.get('legs')) for ev in evs if ev.get('legs') is not None), None)   # (right after it)
        if left is None and cb is not None:
            left = len(cb.get('legs') or [])
        if beyond is False:
            msg = (f"leg(s) {new} of the {side} trade closed outside the bot inside its stop {_px(stop, d)} (by hand, the "
                   f"deal history shows): the trade goes on with {left} leg(s); the stop stays at {_px(stop, d)}")
        else:
            msg = (f"leg(s) {new} of the {side} trade closed outside the bot at or beyond its stop {_px(stop, d)} "
                   + ("(their broker backstop, the deal history shows)" if beyond else
                      "(the deal history does not show them yet, so they count as closed beyond it)")
                   + f": the stop was passed while the bot did not look, so the other {left} leg(s) are closed at once")
        self._rec('WARN', 'TRADE', msg, kv={'gone': new, 'beyond_stop': beyond, 'stop': stop, 'legs_left': left})

    def _origin_of(self, bk):
        if isinstance(bk.get('origin'), str) or 'origin' in bk:
            return bk.get('origin')
        try:
            return self._T().stop_origin(bk)
        except Exception:
            return None

    def _origin_words(self, origin, side):
        p = self._turtle_params()
        w = STOP_ORIGIN_TEXT.get(origin)
        if w is None:
            return str(origin) if origin else 'n/a'
        return w.format(days=p['exit_days'], extreme='low' if side == 'BUY' else 'high')

    # ── the decision: action, headline, gates ──
    def _turtle_decide(self, c, snap, orders, digits):
        T = self._T()
        tv = snap['turtle']
        st = c.st if isinstance(c.st, dict) else {}
        p = tv['params']
        bs, ss = _sig_name(c.buy_signal), _sig_name(c.sell_signal)
        nb, ns = self._count(c.buy_positions), self._count(c.sell_positions)
        d = digits
        G = self._first_gates(nb, ns)
        bid, ask = _f(c.bid), _f(c.ask)
        quote = bid is not None and ask is not None and c.now is not None
        G.append(_gate('quote', 'Quote', quote, f'{_px(bid, d)} / {_px(ask, d)}' if quote else 'none',
                       'symbol_info_tick() answers (bid / ask; the time of the last tick is the decision time)',
                       None if quote else 'no tick: nothing is decided'))
        rows_ok = c.rows is not None
        lvd = tv['levels'] or {}
        if not rows_ok:
            note = 'N and the channels are not settled: not trading'
        elif tv['d1'].get('stale'):
            note = (f"the levels of the D1 bar of {_date(lvd.get('bar_time'))} are still in force: the D1 bar that closed "
                    f"at {_hm(lvd.get('until_t'))} is not there yet (asked again every poll)")
        else:
            note = f"levels of the D1 bar of {_date(lvd.get('bar_time'))}"
        G.append(_gate('d1_levels', 'Daily levels', rows_ok, tv['d1']['bars'] if rows_ok else tv['d1']['got_last_read'],
                       f">= {p['min_d1_bars']} closed D1 bars (asked for {p['d1_bars']})", note))
        both = bool(nb and ns)
        if both:
            G.append(_gate('one_side', 'One side open', False, f'{nb} buy and {ns} sell', 'the Turtle holds one side',
                           'it holds still and manages neither side (close one of them by hand)'))
        unmanaged = bool(c.hold) and rows_ok and quote and not both
        if unmanaged:
            G.append(_gate('trade_known', 'Trade known', False, f'{nb or ns} position(s)',
                           "the positions are the book's, or rebuilt from them and the D1 bars",
                           'the positions predate the D1 history the terminal gives: they are left alone'))
        live = bool(c.live)
        ms = c.market_status or {}
        G.append(_gate('market_live', 'Market live', live, _f(ms.get('minutes_since_last'), 2),
                       f"a tick or an M1 bar within {self._cfg('MARKET_LOOKBACK_MINUTES')} min",
                       None if live else 'nothing is decided while the market is closed: no entry, no add, no stop'))
        if bs in ('CLOSE_BUY', 'BUY_MORE'):
            pre_side = 1
        elif ss in ('CLOSE_SELL', 'SELL_MORE'):
            pre_side = -1
        elif bs == 'BUY' or ss == 'SELL':
            pre_side = 0
        else:
            pre_side = _i(st.get('side')) or 0
        if pre_side:
            action, reason, side = self._turtle_decide_trade(c, tv, G, st, pre_side, bs, ss, orders, d, p)
        else:
            action, reason, side = self._turtle_decide_flat(c, tv, G, st, bs, ss, orders, d, p)
        if not quote:
            action, reason = 'NO_DATA', 'quote'
        elif not rows_ok:
            action, reason = 'NO_DATA', 'd1 bars'
        elif both:
            action, reason, side = 'BOTH_SIDES', None, None
        elif unmanaged:
            action, reason = 'UNMANAGED', 'positions predate the D1 history'
        elif not live:
            action, reason = 'MARKET_CLOSED', None
        decided = _mark_checked(G)
        dec = {'action': action, 'reason': reason, 'side': side, 'blocked_by': decided,
               'signal': {'buy': bs, 'sell': ss}, 'gates': G, 'orders': orders}
        dec['headline'] = self._turtle_headline(dec, c, snap, d)
        self._turtle_self_check(dec, bs, ss)
        return dec

    def _turtle_decide_trade(self, c, tv, G, st, pre_side, bs, ss, orders, d, p):
        T = self._T()
        buy = pre_side == 1
        side = 'BUY' if buy else 'SELL'
        tr = tv.get('trade') or {}
        closing_now = bs == 'CLOSE_BUY' or ss == 'CLOSE_SELL'
        retry = closing_now and c.exit_reason == 'close_retry'
        # a leg closed outside the bot at or beyond the stop (app.py _turtle_sync, from the deal history): the other legs
        # are closed at once (this poll's close, exit reason stop_passed_outside; or the next live poll's)
        passed = (c.exit_reason == 'stop_passed_outside' if closing_now else
                  bool(st.get('closing')) and bool(getattr(self.bot, '_turtle_stop_passed', False)))
        if passed:
            gone = self._outside_of(tr, st)
            G.append(_gate('stop_passed', 'Stop passed outside the bot', True, gone or None,
                           'a leg closed outside the bot at or beyond the stop (its broker backstop; the deal history)',
                           'the stop was passed while the bot did not look: the other legs are closed at once, whatever '
                           'the price', role='exit'))
        elif retry or (st.get('closing') and not closing_now):
            G.append(_gate('close_retry', 'Earlier close finished', True, None,
                           'the legs an incomplete close left are closed first, whatever the price', role='exit'))
        stop = tr.get('stop')
        px = _f(c.bid if buy else c.ask)
        fired = ((closing_now and c.exit_reason == 'stop') or
                 (not closing_now and px is not None and stop is not None and (px <= stop if buy else px >= stop)))
        G.append(_gate('stop', 'Stop', fired, px,
                       f"{'bid' if buy else 'ask'} {'<=' if buy else '>='} {_px(stop, d)} ({tr.get('stop_text')})",
                       f"{_px(tr.get('to_stop'), d)} {'above' if buy else 'below'} the stop"
                       if tr.get('to_stop') is not None else None, role='exit'))
        if closing_now:
            return f'CLOSE_{side}', ('close_retry' if retry else 'stop_passed_outside' if passed else 'stop'), side
        pending = bool(c.pending)
        G.append(_gate('fill_listed', 'Fill listed', not pending, None if not pending else 'not yet',
                       f"the terminal lists every leg (a new one waits up to {_num(p['pending_s'], 0)} s)",
                       'no add meanwhile' if pending else None))
        adding = bs == 'BUY_MORE' or ss == 'SELL_MORE'
        add_done = adding and any(o['done'] for o in orders if o['kind'] in ('add', 'open') and o['side'] == side)
        n_legs = len(st.get('legs') or []) - (1 if add_done else 0)
        room = n_legs < p['max_legs']
        G.append(_gate('legs', 'Legs', room, f"{n_legs}/{p['max_legs']}", f"fewer than {p['max_legs']}",
                       None if room else 'the trade is full: no more adds', role='add'))
        et, tnow = _f(st.get('entry_time')), _f(c.now)
        bar_ok = bool(T is not None and et is not None and tnow is not None and T.bar_of(tnow) > T.bar_of(et))
        G.append(_gate('add_bar', 'Not the entry minute', bar_ok, _iso(et), 'no add in the M1 bar of the entry', role='add'))
        if adding:
            lvl = _f(c.lvl)
        else:
            lvl = tr.get('next_add')
        q = _f(c.ask if buy else c.bid)
        hit = lvl is not None and q is not None and (q >= lvl if buy else q <= lvl)
        G.append(_gate('add_price', 'Add level', hit if room else None, q,
                       (f"{'ask' if buy else 'bid'} {'>=' if buy else '<='} {_px(lvl, d)} (the last fill "
                        f"{'+' if buy else '-'} 0.5N {_num(st.get('add_step'))})") if lvl is not None else None,
                       (f"{_px(tr.get('to_next_add'), d)} to go" if (tr.get('to_next_add') or 0) > 0 else None),
                       role='add'))
        hold = self._hold(c, ('pyramid', 'add'))
        if hold is not None:                 # an add every gate above lets through, held back before the send
            G.append(self._hold_gate(hold, role='add'))
        rec = c._trade_rec if isinstance(c._trade_rec, dict) else {}
        if rec.get('adds_stopped') and not adding:
            # the price ran more than one add step past an add the safety held back: no more adds for this trade
            G.append(_gate('adds_stopped', 'Adds still taken', False, True,
                           'no add was missed by more than one add step (0.5 N) while the safety held it back',
                           'this trade takes no more adds: a late one far past its level would move the stop of the '
                           'whole trade', role='add'))
        if pending:
            return 'WAIT_FILL', None, side
        if adding:
            return (f'ADD_{side}' if add_done else 'ADD_FAILED'), None, side
        return 'HOLD', None, side

    def _turtle_decide_flat(self, c, tv, G, st, bs, ss, orders, d, p):
        T = self._T()
        entering = bs == 'BUY' or ss == 'SELL'
        side = 'BUY' if bs == 'BUY' else ('SELL' if ss == 'SELL' else None)
        o, vt = tv['orders'], tv['vote']
        armed = True if entering else bool(st.get('armed'))
        lvd = tv['levels'] or {}
        if armed:
            note = f"the orders of the D1 bar of {_date(lvd.get('bar_time'))}"
        else:
            by = (f" by the {o['used_by']} trade of {_hm(o['used_t'])}" if o.get('used_t') else
                  ' (an entry filled since that D1 bar closed)')
            u_t, n_t = _f(o.get('until_t')), _f(c.now)
            if u_t is not None and n_t is not None and u_t <= n_t:
                note = (f"used{by}; the D1 bar that closed at {_hm(u_t)} is not there yet: new orders as soon as the "
                        'terminal gives it')
            else:
                note = f"used{by}; the next D1 close ({_hm(o.get('until_t'))}) arms new ones"
        G.append(_gate('armed', "Today's orders", armed, 'armed' if armed else 'used',
                       'the entry orders of the last D1 bar not used yet (one entry per D1 bar)', note))
        tnow, lx = _f(c.now), _f(st.get('last_exit_time'))
        in_exit_bar = bool(not entering and T is not None and lx is not None and tnow is not None
                           and T.bar_of(tnow) <= T.bar_of(lx))
        G.append(_gate('exit_bar', 'Not the exit minute', not in_exit_bar, _iso(lx), 'no entry in the M1 bar of the last exit'))
        ob, os_ = o.get('buy') or {}, o.get('sell') or {}
        if entering:
            hb, hs = side == 'BUY', side == 'SELL'
        else:
            hb, hs = bool(ob.get('reached')), bool(os_.get('reached'))
        reached = side if entering else ('BUY' if hb else 'SELL' if hs else None)
        far = []
        if ob:
            far.append(f"ask {_px(ob.get('price_now'), d)} is {_px(abs(ob.get('distance') or 0), d)} "
                       f"{'below' if (ob.get('distance') or 0) > 0 else 'beyond'} the buy level")
        if os_:
            far.append(f"bid {_px(os_.get('price_now'), d)} is {_px(abs(os_.get('distance') or 0), d)} "
                       f"{'above' if (os_.get('distance') or 0) > 0 else 'beyond'} the sell level")
        G.append(_gate('breakout', 'Breakout', bool(hb or hs), reached,
                       f"ask >= {_px(ob.get('level'), d)} (buy) or bid <= {_px(os_.get('level'), d)} (sell)",
                       '; '.join(far) or None))
        fresh = bool(vt.get('fresh'))
        G.append(_gate('vote_known', f"{vt['tf']} vote known", fresh, vt.get('bar_utc'),
                       f"the vote of the last closed {vt['tf']} bar",
                       None if fresh else f"no vote of the last closed {vt['tf']} bar (the terminal gave "
                                          f"{vt.get('bars')} closed bars, {vt.get('min_bars')} needed)"))
        v = vt.get('last') if fresh else 0
        if hb or hs:
            ok = (hb and v == 1) or (hs and v == -1)
            need = '+1 for the buy' if (hb and not hs) else ('-1 for the sell' if hs and not hb else '+1 / -1')
        else:
            ok, need = None, '+1 for a buy, -1 for a sell'
        G.append(_gate('vote', f"{vt['tf']} vote", ok, v, need,
                       f"RSI {_sc(vt['rsi']['vote'])}, MACD {_sc(vt['macd']['vote'])} on the bar closed at "
                       f"{_clock(vt.get('bar_close_t'))}"))
        brake = bool(c.brake_manual)
        G.append(_gate('brake', 'Manual brake off', not brake, int(c.brake_manual or 0), 'symbols.json brake 0',
                       'no new entries while the brake is on' if brake else None))
        hold = None if entering else self._hold(c, ('entry',))
        if hold is not None:                 # the last test before the send held the entry back (app.py _open_held)
            G.append(self._hold_gate(hold))
        if entering:
            sent = [x for x in orders if x['kind'] == 'open' and x['side'] == side]
            if any(x['done'] for x in sent):
                return f'OPEN_{side}', None, side
            return 'OPEN_FAILED', (sent[-1]['retcode_text'] if sent else 'no order'), side
        if not armed:
            return 'WAIT', 'orders used', None
        if in_exit_bar:
            return 'WAIT', 'exit bar', None
        if not (hb or hs):
            return 'WAIT', 'no breakout', None
        if not fresh:
            return 'BLOCKED', 'vote unknown', reached
        if not ok:
            return 'BLOCKED', 'vote', reached
        if brake:
            return 'BLOCKED', 'brake', reached
        if hold is not None:
            return 'BLOCKED', hold.get('why'), reached or hold.get('side')
        return 'WAIT', None, None

    def _turtle_self_check(self, dec, bs, ss):
        """The gates are this module's reading of the decision; the bot's signals are the decision. A difference is a
        WARN (a bug of the trace, not of the trading), at most every 10 min."""
        if dec['action'] in ('SKIPPED', 'NO_DATA', 'MARKET_CLOSED', 'BOTH_SIDES', 'UNMANAGED'):
            return
        g = {x['key']: x for x in dec['gates']}
        if 'armed' in g:
            reads = all(g[k]['ok'] for k in ('armed', 'exit_bar', 'breakout', 'vote_known', 'vote', 'brake',
                                             'open_hold') if k in g)
            signal = bs == 'BUY' or ss == 'SELL'
        else:
            if 'close_retry' in g or 'stop_passed' in g:
                return
            close = g['stop']['ok'] is True
            add = (not close and bool(g.get('fill_listed', {}).get('ok'))
                   and all(x['ok'] for x in dec['gates'] if x['role'] == 'add'))
            reads, signal = (close, add), (bs == 'CLOSE_BUY' or ss == 'CLOSE_SELL', bs == 'BUY_MORE' or ss == 'SELL_MORE')
        if reads != signal:
            write, n = self._repeat(('selfcheck', dec['action']))
            if write:
                self._rec('WARN', 'TRACE', f"the trace's reading of the gates differs from the bot's signals (buy {bs}, "
                          f"sell {ss}); the signals are what the bot did", data={'gates': dec['gates']})

    def _turtle_headline(self, dec, c, snap, d):
        act, reason, side = dec['action'], dec['reason'], dec['side']
        tv = snap['turtle']
        p, o, vt, lv = tv['params'], tv['orders'], tv['vote'], tv['levels'] or {}
        tr = tv.get('trade') or {}
        ms = c.market_status or {}
        tf = vt['tf']
        e_days = tv['channels']['entry']['days']
        if act == 'NO_DATA':
            if reason == 'quote':
                return f'No quote: the terminal gave no tick for {self.mt5_symbol} this poll, so nothing is decided.'
            return (f"No daily levels yet: the terminal gave {tv['d1']['got_last_read'] or 0} closed D1 bars, at least "
                    f"{p['min_d1_bars']} are needed for N and the channels; not trading.")
        if act == 'MARKET_CLOSED':
            mins = _num(ms.get('minutes_since_last'), 1)
            if tr.get('side'):
                if bool(getattr(self.bot, '_turtle_stop_passed', False)) and tr.get('closing'):
                    return (f"Market not live (no tick for {mins} min): a leg of the {tr['side']} trade was closed outside "
                            f"the bot beyond its stop {_px(tr.get('stop'), d)}; the other {tr.get('legs_count')} leg(s) "
                            'are closed as soon as it trades.')
                return (f"Market not live (no tick for {mins} min): holding the {tr['side']} trade ({tr.get('legs_count')} "
                        f"legs, P/L {_usd(tr.get('pnl'))}); its stop {_px(tr.get('stop'), d)} is checked again when it "
                        'trades.')
            return (f"Market not live: no tick for {mins} min (live needs one within "
                    f"{self._cfg('MARKET_LOOKBACK_MINUTES')} min); nothing is decided until it trades again.")
        if act == 'BOTH_SIDES':
            return ('Both a BUY and a SELL of this bot are open: the Turtle holds still and manages neither side (close '
                    'one of them by hand).')
        if act == 'UNMANAGED':
            return ("This bot's open positions predate the D1 history the terminal gives: their N and stop cannot be "
                    'rebuilt, so the bot leaves them alone (close them by hand or give the terminal more D1 history).')
        vote_now = (f"the {tf} vote is {_sc(vt.get('last'))}" if vt.get('fresh') else
                    f'the {tf} vote of the last closed bar is not known')
        if act == 'WAIT':
            if reason == 'orders used':
                by = f" by the {o['used_by']} trade of {_hm(o['used_t'])}" if o.get('used_t') else ''
                until_t, now_t = _f(o.get('until_t')), _f(c.now)
                if until_t is not None and now_t is not None and until_t <= now_t:
                    # the D1 close has passed but the terminal has not given the new D1 bar yet (the bot asks every poll)
                    return (f"Flat: today's entry orders were used{by}; the D1 bar that closed at {_hm(until_t)} "
                            f"is not there yet ({_dur(now_t - until_t)} late): new orders as soon as the terminal "
                            'gives it (asked every poll).')
                left = _dur(until_t - now_t) if (until_t is not None and now_t is not None) else 'n/a'
                return (f"Flat: today's entry orders were used{by}; no new entry until the next D1 bar closes at "
                        f"{_hm(o.get('until_t'))} (in {left}) and sets new levels.")
            if reason == 'exit bar':
                return (f"Flat: the trade was closed at {_hm(o.get('last_exit_t'))}; no entry in the same M1 bar (the "
                        f"orders are {o['state']}).")
            ob, os_ = o.get('buy') or {}, o.get('sell') or {}
            return (f"Flat, orders armed, waiting for a breakout: a BUY when the ask reaches {_px(ob.get('level'), d)} "
                    f"(the {e_days}-day high + {p['tick']:g}; ask {_px(ob.get('price_now'), d)}, "
                    f"{_px(ob.get('distance'), d)} away) or a SELL when the bid reaches {_px(os_.get('level'), d)} "
                    f"(bid {_px(os_.get('price_now'), d)}, {_px(os_.get('distance'), d)} away), each only with the "
                    f"{tf} vote of closed bars ({vote_now}).")
        if act == 'BLOCKED':
            k = (o.get('buy') if side == 'BUY' else o.get('sell')) or {}
            what = f"The {k.get('judged_on')} {_px(k.get('price_now'), d)} is through the {side.lower()} level {_px(k.get('level'), d)}"
            if reason == 'vote':
                return (f"{what}, but the {tf} vote of the bar closed at {_clock(vt.get('bar_close_t'))} is "
                        f"{_sc(vt.get('last'))} (RSI {_sc(vt['rsi']['vote'])}, MACD {_sc(vt['macd']['vote'])}): no "
                        f"{side.lower()} until it is {'+1' if side == 'BUY' else '-1'}; the next vote is read at "
                        f"{_hm(vt.get('next_read_t'))}.")
            if reason == 'vote unknown':
                return (f"{what}, but the vote of the last closed {tf} bar is not known (the terminal gave "
                        f"{vt.get('bars')} closed bars, {vt.get('min_bars')} needed): no entry until it is.")
            if reason == 'brake':
                return f'{what} with the vote, but the manual brake is on (symbols.json brake 1): no new entries.'
            hg = next((x for x in dec['gates'] if x['key'] == 'open_hold'), None)
            if hg is not None:
                return f"{what} with the vote, but no order is sent: {hg['note']}."
            return f'{what}: blocked ({reason}).'
        if act in ('OPEN_BUY', 'OPEN_SELL'):
            fill = next((x for x in dec['orders'] if x['done'] and x['kind'] == 'open'), {})
            k = (o.get('buy') if side == 'BUY' else o.get('sell')) or {}
            jr = tr.get('journal') or {}
            return (f"Opened a {side} trade: {fill.get('result_volume') or fill.get('volume')} lot at "
                    f"{_px(fill.get('result_price') or fill.get('price'), d)} (the {side.lower()} level "
                    f"{_px(jr.get('entry_level') or k.get('level'), d)}, {tf} vote {_sc(vt.get('last'))}); N "
                    f"{_num(tr.get('n_entry'))} frozen: stop {_px(tr.get('stop'), d)} ({tr.get('stop_text')}), next add "
                    f"at {_px(tr.get('next_add'), d)}, {p['max_legs']} legs at most; broker backstop "
                    f"{_px(fill.get('sl'), d)}.")
        if act == 'OPEN_FAILED':
            return (f'Tried to open a {side} trade: the order was not filled ({reason}); it is tried again on the next '
                    'poll while the breakout and the vote hold.')
        if act == 'WAIT_FILL':
            return (f"The {side} leg filled; waiting for the terminal to list it (up to {_num(p['pending_s'], 0)} s); no "
                    'add meanwhile.')
        if act in ('CLOSE_BUY', 'CLOSE_SELL'):
            cr = c.close_response or {}
            res = ''
            if cr and int(cr.get('failed_count') or 0):
                res = (f" The close is incomplete: {cr.get('closed_count')} closed, {cr.get('failed_count')} failed "
                       f"({'; '.join(cr.get('errors') or [])}); the rest is closed next poll.")
            elif cr and not int(cr.get('closed_count') or 0):
                res = (" The close closed nothing (none of the trade's legs were there to close): the trade stays booked, "
                       'and the close is decided again next poll.')
            if reason == 'close_retry':
                return f'Closing the rest of the {side} trade (an earlier close left legs open).' + res
            if reason == 'stop_passed_outside':
                return (f"Closing the rest of the {side} trade: {self._legs_words(self._outside_of(tr, c.st))} closed "
                        f"outside the bot at or beyond its stop {_px(tr.get('stop'), d)} (the broker's backstop) while the "
                        "bot did not look; the stop has been passed, so the other legs close now, whatever the price; P/L "
                        f"{_usd(tr.get('pnl'))} at the decision." + res)
            return (f"Closing the {side} trade at the stop: {tr.get('judged_on')} {_px(tr.get('price_now'), d)} "
                    f"{'<=' if side == 'BUY' else '>='} the stop {_px(tr.get('stop'), d)} ({tr.get('stop_text')}); "
                    f"{tr.get('legs_count')} legs, P/L {_usd(tr.get('pnl'))} at the decision." + res)
        if act in ('ADD_BUY', 'ADD_SELL', 'ADD_FAILED'):
            x = next((y for y in dec['orders'] if y['kind'] in ('add', 'open')), {})
            lvl = _f(c.lvl)
            if act == 'ADD_FAILED':
                return (f"Tried to add a leg to the {side} trade at the add level {_px(lvl, d)}: "
                        f"{x.get('retcode_text') or 'no order'}; tried again on the next poll.")
            return (f"Added leg {tr.get('legs_count')}/{p['max_legs']} to the {side} trade: "
                    f"{x.get('result_volume') or x.get('volume')} lot at {_px(x.get('result_price') or x.get('price'), d)} "
                    f"(the add level {_px(lvl, d)} = the last fill {'+' if side == 'BUY' else '-'} 0.5N); the stop is now "
                    f"{_px(tr.get('stop'), d)} ({tr.get('stop_text')}); "
                    + (f"next add at {_px(tr.get('next_add'), d)}." if tr.get('next_add') is not None else
                       'the trade is full.'))
        if act == 'HOLD':
            buy = side == 'BUY'
            parts = [f"Holding the {side} trade, {tr.get('legs_count')}/{p['max_legs']} legs, P/L {_usd(tr.get('pnl'))}: "
                     f"the stop is {_px(tr.get('stop'), d)} ({tr.get('stop_text')}; the {tr.get('judged_on')} "
                     f"{_px(tr.get('price_now'), d)} is {_px(tr.get('to_stop'), d)} away)"]
            if tr.get('next_add') is not None:
                parts.append(f"; the next add at {'ask >=' if buy else 'bid <='} {_px(tr.get('next_add'), d)} "
                             f"({tr.get('next_add_judged_on')} now {_px(tr.get('add_price_now'), d)})")
            else:
                parts.append('; the trade is full (no more adds)')
            held = {x['key']: x for x in dec['gates'] if x['key'] in ('open_hold', 'adds_stopped')}
            if 'open_hold' in held:
                parts.append(f"; an add is held back: {held['open_hold']['note']}")
            elif 'adds_stopped' in held:
                parts.append('; it takes no more adds (one was missed by more than an add step while the safety held '
                             'it back)')
            parts.append('; no target: it closes only at the stop.')
            return ''.join(parts)
        return act

    # ── what changed since the last poll: log lines ──
    def _book_sum(self, st):
        """What the log compares of the Turtle's book from one poll to the next (and the trade view of a poll that
        closed it reads)."""
        st = st if isinstance(st, dict) else {}
        lv = st.get('levels') or {}
        origin = None
        if st.get('side') and self._T() is not None:
            try:
                origin = self._T().stop_origin(st)
            except Exception:
                origin = None
        return {'side': _i(st.get('side')) or 0, 'units': _i(st.get('units')),
                'legs': [(_i(x.get('ticket')), _f(x.get('price')), _f(x.get('time'))) for x in st.get('legs') or []],
                'n_entry': _f(st.get('n_entry')), 'stop_dist': _f(st.get('stop_dist')), 'add_step': _f(st.get('add_step')),
                'trail_best': _f(st.get('trail_best')), 'stop_floor': _f(st.get('stop_floor')), 'stop': _f(st.get('stop')),
                'origin': origin, 'row': _i(st.get('row')), 'armed': bool(st.get('armed')),
                'closing': bool(st.get('closing')), 'last_exit_time': _f(st.get('last_exit_time')),
                'entry_time': _f(st.get('entry_time')), 'entry_row': _i(st.get('entry_row')),
                'levels': {k: lv.get(k) for k in ('bar_time', 'from_time', 'buy', 'sell', 'n', 'use20', 'trail_long',
                                                  'trail_short', 'stop_dist', 'add_step', 'ok')} if lv else None}

    def _book_words(self, st):
        if not isinstance(st, dict) or not st:
            return 'no book'
        d = self._digits
        lv = st.get('levels') or {}
        lev = (f"levels of the D1 bar of {_date(lv.get('bar_time'))}: buy {_px(lv.get('buy'), d)}, sell "
               f"{_px(lv.get('sell'), d)}, N {_num(lv.get('n'))}, orders {'armed' if st.get('armed') else 'used'}"
               if lv else 'no levels yet')
        side = st.get('side')
        if not side:
            return (f'flat; {lev}' + (f"; last exit {_hm(st.get('last_exit_time'))}" if st.get('last_exit_time') else ''))
        s = self._book_sum(st)
        return (f"{'BUY' if side == 1 else 'SELL'} trade of {len(st.get('legs') or [])} leg(s), unit {st.get('units')}, "
                f"N at entry {_num(st.get('n_entry'))}, stop {_px(st.get('stop'), d)} "
                f"({self._origin_words(s['origin'], 'BUY' if side == 1 else 'SELL')}), entered {_hm(st.get('entry_time'))}"
                + (', closing' if st.get('closing') else '') + f'; {lev}')

    def _vote_words(self, vt):
        def part(name, x, nd):
            if not x.get('pivot_side'):
                return f"{name} {_sc(x.get('vote'))} (no pivot)"
            return (f"{name} {_sc(x.get('vote'))} (pivot {x.get('pivot_side')} {_num(x.get('pivot'), nd)} "
                    f"{x.get('bars_ago')} bars ago, slope {_num(x.get('slope'), nd)})")
        m = vt['macd']
        side = f", signal line {_num(m.get('signal'), 4)}: {m.get('side_rule')}s count" if m.get('side_rule') else ''
        return part('RSI', vt['rsi'], 2) + ', ' + part('MACD', m, 4) + side

    def _turtle_transitions(self, c, snap, dec, orders, now, digits):
        tv = snap['turtle']
        st = c.st if isinstance(c.st, dict) else {}
        prev = self._prev
        first = not prev.get('polled')
        pb = prev.get('turtle') or self._book_sum({})
        cb = self._book_sum(st)
        p, d = tv['params'], digits
        acct = snap['account']
        act = dec['action']
        tr = tv.get('trade') or {}
        last = self._last_snapshot or {}
        last_tr = (last.get('turtle') or {}).get('trade') or {}
        side_w = {1: 'BUY', -1: 'SELL'}
        J = self._journal_load()
        jdirty = False
        # the levels of the day (a D1 bar closed, or the first poll)
        if cb['row'] is not None and (first or cb['row'] != pb.get('row')):
            self._log_levels(c, tv, cb, pb, first, d)
            if cb['armed']:
                prev['used_t'] = prev['used_by'] = None
        elif pb.get('armed') and not cb['armed'] and act not in ('OPEN_BUY', 'OPEN_SELL') and not cb['side']:
            self._rec('INFO', 'LEVELS', "today's entry orders are marked used: the deal history shows an entry since the "
                      f"D1 bar of {_date(cb['row'])} closed; no entry until the next D1 close")
        # the M15 vote
        vt = tv['vote']
        pv = prev.get('vote')
        if vt.get('bar_t') is not None and (pv is None or pv[0] != vt['bar_t']):
            kv = {'bar_utc': vt.get('bar_utc'), 'vote': vt.get('last'), 'rsi': vt['rsi']['vote'], 'macd': vt['macd']['vote'],
                  'rsi_now': vt['rsi'].get('now'), 'rsi_pivot': vt['rsi'].get('pivot'), 'rsi_slope': vt['rsi'].get('slope'),
                  'hist_now': vt['macd'].get('now'), 'macd_pivot': vt['macd'].get('pivot'),
                  'macd_slope': vt['macd'].get('slope'), 'signal': vt['macd'].get('signal'), 'bars': vt.get('bars')}
            allows = {1: 'a BUY breakout may enter', -1: 'a SELL breakout may enter'}.get(vt.get('last'), 'no entry on either side')
            if pv is None or pv[1] != vt.get('last'):
                head = (f"{vt['tf']} vote {_sc(pv[1])} -> {_sc(vt.get('last'))}" if pv is not None else
                        f"{vt['tf']} vote {_sc(vt.get('last'))}")
                self._rec('INFO', 'VOTE', f"{head} on the bar closed at {_clock(vt.get('bar_close_t'))}: "
                          f"{self._vote_words(vt)}; {allows}", kv=kv)
            else:
                self._rec('DEBUG', 'VOTE', f"{vt['tf']} vote of the bar closed at {_clock(vt.get('bar_close_t'))}: "
                          f"{_sc(vt.get('last'))} ({self._vote_words(vt)})", kv=kv)
        if pv is not None and pv[2] and not vt.get('fresh'):
            self._rec('WARN', 'VOTE', f"no {vt['tf']} vote for the bar that closed last (the terminal gave {vt.get('bars')} "
                      f"closed bars, {vt.get('min_bars')} needed): no entry until there is one")
        elif pv is not None and not pv[2] and vt.get('fresh'):
            self._rec('INFO', 'VOTE', f"the {vt['tf']} vote is known again")
        # the bot's own trading this poll
        if act in ('OPEN_BUY', 'OPEN_SELL'):
            fill = next((x for x in orders if x['done'] and x['kind'] == 'open'), {})
            side = dec['side']
            k = (tv['orders'].get('buy') if side == 'BUY' else tv['orders'].get('sell')) or {}
            lvl = _f(k.get('level'))
            ext = tv['channels']['entry'].get('high' if side == 'BUY' else 'low')
            rec = {'side': side, 'units': tr.get('units'), 'lots': tr.get('lots_per_leg'), 'n_entry': tr.get('n_entry'),
                   'stop_dist': tr.get('stop_dist'), 'add_step': tr.get('add_step'), 'entry_level': lvl,
                   'entry_d1_t': tr.get('entry_d1_t'), 'use20': (tv['levels'] or {}).get('use20'),
                   'vote': vt.get('last'), 'vote_bar_t': vt.get('bar_t'), 'opened_t': tr.get('entry_t'),
                   'balance': _f((snap.get('sizing') or {}).get('sizing_balance'), 2),
                   'account_balance': _f((snap.get('sizing') or {}).get('account_balance'), 2), 'rebuilt': False,
                   'legs': [{'id': x['id'], 't': x['open_t'], 'price': x['price'], 'level': lvl, 'backstop': x['backstop']}
                            for x in tr.get('legs') or []],
                   'stops': [{'t': now, 'stop': tr.get('stop'), 'origin': tr.get('stop_origin'), 'why': 'entry'}],
                   'exit': None}
            if tr.get('legs'):
                J[str(tr['legs'][0]['id'])] = rec
                jdirty = True
            prev['used_t'], prev['used_by'] = tr.get('entry_t'), side
            self._rec('INFO', 'TRADE', f"{side} trade opened: {fill.get('result_volume') or fill.get('volume')} lot at "
                      f"{_px(fill.get('result_price') or fill.get('price'), d)} (the {side.lower()} level {_px(lvl, d)} = the "
                      f"{tv['channels']['entry']['days']}-day {'high' if side == 'BUY' else 'low'} {_px(ext, d)} "
                      f"{'+' if side == 'BUY' else '-'} {p['tick']:g}, reached by the {k.get('judged_on')}; {vt['tf']} vote "
                      f"{_sc(vt.get('last'))} on the bar closed at {_clock(vt.get('bar_close_t'))}), unit {tr.get('units')}"
                      + self._sizing_words(snap)
                      + f"; N {_num(tr.get('n_entry'))} frozen for the trade: stop {_px(tr.get('stop'), d)} "
                      f"({tr.get('stop_text')}), next add at {'ask >=' if side == 'BUY' else 'bid <='} "
                      f"{_px(tr.get('next_add'), d)}, up to {p['max_legs']} legs; broker backstop {_px(fill.get('sl'), d)}",
                      kv={'side': side, 'price': fill.get('result_price'), 'level': lvl, 'lots': fill.get('result_volume'),
                          'units': tr.get('units'), 'n_entry': tr.get('n_entry'), 'stop': tr.get('stop'),
                          'stop_origin': tr.get('stop_origin'), 'next_add': tr.get('next_add'), 'backstop': fill.get('sl'),
                          'vote': vt.get('last'), 'vote_bar': vt.get('bar_utc'), 'd1_bar': _iso(tr.get('entry_d1_t')),
                          'use20': (tv['levels'] or {}).get('use20'),
                          'balance': _f((snap.get('sizing') or {}).get('sizing_balance'), 2),
                          'account_balance': _f((snap.get('sizing') or {}).get('account_balance'), 2)})
            self._trades_dirty = True
        elif act in ('ADD_BUY', 'ADD_SELL'):
            fill = next((x for x in orders if x['done'] and x['kind'] in ('add', 'open')), {})
            side = dec['side']
            lvl = _f(c.lvl)
            legs = tr.get('legs') or []
            prev_fill = legs[-2]['price'] if len(legs) >= 2 else None
            rec = J.get(str(legs[0]['id'])) if legs else None
            if rec is not None and legs:
                rec.setdefault('legs', []).append({'id': legs[-1]['id'], 't': legs[-1]['open_t'], 'price': legs[-1]['price'],
                                                   'level': lvl, 'backstop': fill.get('sl')})
                jdirty = True
            self._rec('INFO', 'TRADE', f"leg {len(legs)}/{p['max_legs']} added to the {side} trade: "
                      f"{fill.get('result_volume') or fill.get('volume')} lot at "
                      f"{_px(fill.get('result_price') or fill.get('price'), d)} (the add level {_px(lvl, d)} = the last fill "
                      f"{_px(prev_fill, d)} {'+' if side == 'BUY' else '-'} 0.5N {_num(tr.get('add_step'))}, reached by the "
                      f"{tr.get('next_add_judged_on')}); "
                      + (f"next add at {_px(tr.get('next_add'), d)}" if tr.get('next_add') is not None else
                         'the trade is full: no more adds') + f"; broker backstop {_px(fill.get('sl'), d)}",
                      kv={'side': side, 'leg': len(legs), 'price': fill.get('result_price'), 'level': lvl,
                          'last_fill': prev_fill, 'lots': fill.get('result_volume'), 'next_add': tr.get('next_add'),
                          'backstop': fill.get('sl'), 'stop': tr.get('stop')})
            self._trades_dirty = True
        elif act in ('CLOSE_BUY', 'CLOSE_SELL'):
            cr = c.close_response or {}
            closed, failed = int(cr.get('closed_count') or 0), int(cr.get('failed_count') or 0)
            side = dec['side']
            stop, origin = _f(c.stop), c.origin
            ids = [x['id'] for x in tr.get('legs') or [] if x.get('id') is not None]
            extra = {'origin': origin, 'stop': stop, 'side': side}
            # a leg closed outside the bot beyond the stop (app.py _turtle_sync): the bot closes the others now
            passed = dec['reason'] == 'stop_passed_outside'
            retry = dec['reason'] == 'close_retry'
            gone = self._outside_of(tr, st) if passed else []
            key = 'stop_passed_outside' if passed else 'turtle_stop'
            if retry and self._turtle_pending_key:
                key = self._turtle_pending_key       # the retry finishes the close that left legs open: its exit
            if gone:
                self._log_outside(gone, side, pb, d)
                self._record_exits(gone, 'closed_outside', now, None, extra={'side': side})
            if closed:
                self._record_exits([i for i in ids if i not in gone], key, now, tr.get('pnl'), extra=extra)
            if closed and not failed:
                rec = self._journal_rec(ids)
                if rec is not None:
                    rec['exit'] = {'t': now, 'reason': key, 'stop': stop, 'origin': origin,
                                   'price': tr.get('price_now'), 'decision_pnl': tr.get('pnl')}
                    if gone:
                        rec['exit']['legs_outside'] = gone
                    jdirty = True
                self._turtle_pending_key = None
                if retry and key == 'stop_passed_outside':
                    head = (f"the last {closed} leg(s) of the {side} trade closed (the close that followed the stop "
                            f"{_px(stop, d)} passed outside the bot had left them open) at the {tr.get('judged_on')} "
                            f"{_px(tr.get('price_now'), d)}, whatever the price")
                elif retry and self._turtle_nothing:
                    head = (f"the {side} trade closed: its {closed} leg(s), on the next try (the close at the stop "
                            f"{_px(stop, d)} of {_hm(self._turtle_nothing.get('t'))} had closed nothing)")
                elif retry:
                    head = (f"the last {closed} leg(s) of the {side} trade closed (the close at the stop "
                            f"{_px(stop, d)} had left them open)")
                elif passed:
                    head = (f"the {side} trade ended: {self._legs_words(gone)} closed outside the bot at or beyond its "
                            f"stop {_px(stop, d)} ({self._origin_words(origin, side)}) while the bot did not look, so the "
                            f"other {closed} leg(s) closed now at the {tr.get('judged_on')} {_px(tr.get('price_now'), d)}, "
                            'whatever the price')
                else:
                    head = (f"{side} trade closed at the stop ({self._origin_words(origin, side)}): {tr.get('judged_on')} "
                            f"{_px(tr.get('price_now'), d)} {'<=' if side == 'BUY' else '>='} {_px(stop, d)}; "
                            f"{closed} leg(s)")
                self._rec('CLOSE', 'CLOSE', f"{head}, P/L {_usd(tr.get('pnl'))} at the decision, held "
                          f"{_dur(tr.get('age_s'))}; the realised P/L follows from the deal history",
                          kv={'side': side, 'reason': key, 'stop': stop, 'stop_origin': origin,
                              'price': tr.get('price_now'), 'decision_pnl': tr.get('pnl'), 'legs': closed,
                              'tickets': cr.get('closed_tickets'), 'n_entry': tr.get('n_entry'), 'held_s': tr.get('age_s'),
                              'retry': retry, **({'legs_outside': gone} if gone else {})})
                self._turtle_nothing = None
            elif not closed and not failed:
                # (v3.9.2-demo.5) app.py keeps the book and sets 'closing': the close is decided again next poll, and if
                # the legs are gone by then the trade ends there (not as closed outside the bot)
                self._turtle_pending_key = key
                self._turtle_nothing = {'t': now, 'key': key}
                self._rec('WARN', 'CLOSE', f"the close of the {side} trade closed nothing: the close's own positions read "
                          "found none of this bot's legs (another account just now, or the legs are already gone); the "
                          'trade stays booked, and the close is decided again next poll',
                          kv={'closed': 0, 'failed': 0, 'stop': stop, 'reason': key, 'legs': len(ids),
                              'message': cr.get('message')})
            else:
                self._turtle_pending_key = key           # the next poll's close (close_retry) ends the trade this way
                self._rec('WARN', 'CLOSE', f"the close of the {side} trade is incomplete: {closed} closed, {failed} failed "
                          f"({'; '.join(cr.get('errors') or []) or cr.get('message')}); the rest is closed next poll, "
                          'whatever the price', kv={'closed': closed, 'failed': failed, 'stop': stop})
            self._trades_dirty = True
        # the book after this poll, compared with the last one
        same = bool(pb['side'] and cb['side'] == pb['side'] and cb['entry_time'] == pb['entry_time'])
        nothing = self._turtle_nothing               # (a close of this trade that closed nothing: v3.9.2-demo.5)
        if not cb['side']:
            self._turtle_pending_key = None          # flat: no close is left to finish
            self._turtle_nothing = None
        if pb['side'] and not cb['side'] and act not in ('CLOSE_BUY', 'CLOSE_SELL'):
            ids = [x[0] for x in pb['legs'] if x[0] is not None]
            self._record_exits(ids, 'closed_outside', now, last_tr.get('pnl'), extra={'side': side_w[pb['side']]})
            rec = self._journal_rec(ids)
            if rec is not None and rec.get('exit') is None:
                rec['exit'] = {'t': now, 'reason': 'closed_outside', 'stop': pb.get('stop'), 'origin': pb.get('origin'),
                               'price': None, 'decision_pnl': last_tr.get('pnl')}
                jdirty = True
            if nothing:
                head = (f"the {side_w[pb['side']]} trade ended: its {len(ids)} leg(s) are gone, and the bot's close of "
                        f"{_hm(nothing.get('t'))} had closed nothing, so they were closed outside the bot first (their "
                        "broker backstop, or by hand); the bot ends the trade (not booked as closed outside it)")
            else:
                head = (f"the {side_w[pb['side']]} trade was closed outside the bot (the broker's backstop, the terminal, "
                        f"or while the bot was down): its {len(ids)} leg(s) are gone")
            self._rec('CLOSE', 'CLOSE', f"{head}; P/L last seen {_usd(last_tr.get('pnl'))}; the realised P/L and the "
                      'closing deals follow from the deal history',
                      kv={'reason': 'closed_outside', 'ids': ids, 'pnl_last_seen': last_tr.get('pnl'),
                          'stop': pb.get('stop'), 'backstops': last_tr.get('backstop_prices'),
                          **({'after_close_of': nothing.get('key')} if nothing else {})})
            self._trades_dirty = True
        elif pb['side'] and cb['side'] and cb['side'] != pb['side']:
            self._rec('WARN', 'TRADE', f"the {side_w[pb['side']]} trade was replaced outside the bot by a "
                      f"{side_w[cb['side']]} one, taken over: {self._book_words(st)}")
        if not pb['side'] and cb['side'] and act not in ('OPEN_BUY', 'OPEN_SELL'):
            ids = [x[0] for x in cb['legs']]
            if ids and self._journal_rec(ids) is None:
                J[str(ids[0])] = {'side': side_w[cb['side']], 'units': cb['units'], 'n_entry': cb['n_entry'],
                                  'stop_dist': cb['stop_dist'], 'add_step': cb['add_step'], 'entry_level': None,
                                  'entry_d1_t': cb['entry_row'], 'opened_t': cb['entry_time'], 'rebuilt': True,
                                  'legs': [{'id': x[0], 't': x[2], 'price': x[1], 'level': None} for x in cb['legs']],
                                  'stops': [{'t': now, 'stop': cb['stop'], 'origin': cb['origin'], 'why': 'rebuilt'}],
                                  'exit': None}
                jdirty = True
            self._rec('WARN', 'TRADE', f"{side_w[cb['side']]} trade of {len(cb['legs'])} leg(s) taken over from the terminal "
                      f"(no Turtle state for it): unit {cb['units']}, N at the entry {_num(cb['n_entry'])} (the D1 bar of "
                      f"{_date(cb['entry_row'])}), stop {_px(cb['stop'], d)} ({self._origin_words(cb['origin'], side_w[cb['side']])}), "
                      f"next add at {_px(tr.get('next_add'), d)}; today's orders are {'armed' if cb['armed'] else 'used'}",
                      kv={'side': side_w[cb['side']], 'legs': len(cb['legs']), 'units': cb['units'], 'n_entry': cb['n_entry'],
                          'stop': cb['stop'], 'stop_origin': cb['origin'], 'entry_d1': _iso(cb['entry_row'])},
                      data={'book': self._book_copy(st)})
            self._trades_dirty = True
        if same:
            now_ids = {x[0] for x in cb['legs']}
            gone = [x[0] for x in pb['legs'] if x[0] is not None and x[0] not in now_ids]
            if gone and act not in ('CLOSE_BUY', 'CLOSE_SELL'):
                self._record_exits(gone, 'closed_outside', now, None, extra={'side': side_w[cb['side']]})
                if gone[0] in self._legs_outside:     # (app.py's TURTLE_LEG_CLOSED_OUTSIDE: where they closed)
                    self._log_outside(gone, side_w[cb['side']], pb, d, cb=cb)
                else:
                    self._rec('WARN', 'TRADE', f"leg(s) {gone} of the {side_w[cb['side']]} trade closed outside the bot "
                              f"(the broker's backstop, or by hand): {len(cb['legs'])} leg(s) left; the stop stays at "
                              f"{_px(cb['stop'], d)} ({self._origin_words(cb['origin'], side_w[cb['side']])})",
                              kv={'gone': gone, 'legs': len(cb['legs']), 'stop': cb['stop'], 'stop_origin': cb['origin']})
                    self._outside_logged |= set(gone)
                self._trades_dirty = True
            if pb.get('stop') is not None and cb['stop'] is not None and abs(cb['stop'] - pb['stop']) > 1e-9:
                jdirty |= self._log_stop_move(c, tv, pb, cb, act, d)
        if prev.get('pending') and not tv['pending_fill'] and cb['side']:
            self._rec('DEBUG', 'TRADE', f"the terminal lists every leg of the {side_w[cb['side']]} trade now "
                      f"({len(cb['legs'])})")
        # the market, the data, the unit
        live = bool(c.live)
        if not first and prev.get('live') != live:
            ms = c.market_status or {}
            if live:
                self._rec('INFO', 'MARKET', 'market live again')
            else:
                self._rec('INFO', 'MARKET', f"market not live: no tick or M1 bar for {_num(ms.get('minutes_since_last'), 1)} "
                          'min; nothing is decided until it trades', kv={'status': ms.get('status'), 'message': ms.get('message')})
        d1_ok = c.rows is not None
        if (first and not d1_ok) or (not first and prev.get('d1_ok') != d1_ok):
            if d1_ok:
                self._rec('INFO', 'DATA', f"daily levels available: {tv['d1']['bars']} closed D1 bars")
            else:
                self._rec('WARN', 'DATA', f"no daily levels: the terminal gave {tv['d1']['got_last_read'] or 0} closed D1 "
                          f"bars, {p['min_d1_bars']} needed: not trading")
        d1_stale = bool(tv['d1'].get('stale'))
        lvd = tv['levels'] or {}
        if d1_stale and not prev.get('d1_stale'):
            self._rec('WARN', 'DATA', f"the D1 bar that closed at {_hm(lvd.get('until_t'))} is not there yet: the bot goes on "
                      f"with the levels of the D1 bar of {_date(lvd.get('bar_time'))} (and its stop), and asks the terminal "
                      f"again every poll (it gave {tv['d1']['got_last_read'] or 0} closed D1 bars last time)",
                      kv={'levels_of': _iso(lvd.get('bar_time')), 'got': tv['d1']['got_last_read']})
        elif prev.get('d1_stale') and not d1_stale:
            self._rec('INFO', 'DATA', f"the new D1 bar is there: the levels of the D1 bar of {_date(lvd.get('bar_time'))}")
        both = act == 'BOTH_SIDES'
        if both and not prev.get('both'):
            self._rec('WARN', 'TRADE', 'a BUY and a SELL of this bot are open: the Turtle holds still and manages neither')
        units = acct.get('units')
        if not first and prev.get('units') != units:
            self._rec('INFO', 'ACCOUNT', f"unit {prev.get('units')} -> {units}" + self._sizing_words(snap))
        if first:
            self._rec('INFO', 'STATE', f"first poll: {self._book_words(st)}; {vt['tf']} vote "
                      f"{_sc(vt.get('last')) if vt.get('fresh') else 'unknown'}"
                      + f'; unit {units}' + self._sizing_words(snap), data={'book': self._book_copy(st)})
        ms_loop = _f(c.iteration_ms)
        if ms_loop is not None and ms_loop > SLOW_POLL_MS:
            write, n = self._repeat(('slow',), every=300.0)
            if write:
                self._rec('WARN', 'LOOP', f'slow poll: {ms_loop / 1000.0:.1f} s of work (the terminal answered slowly?)',
                          kv={'loop_ms': ms_loop, 'more_since': n})
        if jdirty:
            self._journal_save()
        prev.update(polled=True, turtle=cb, vote=(vt.get('bar_t'), vt.get('last'), bool(vt.get('fresh'))), live=live,
                    d1_ok=d1_ok, d1_stale=d1_stale, both=both, units=units, pending=tv['pending_fill'])

    def _log_levels(self, c, tv, cb, pb, first, d):
        lv, ch, p = tv['levels'] or {}, tv['channels'], tv['params']
        e, x = ch['entry'], ch['exit']
        days = ((cb['row'] - pb['row']) / 86400.0) if pb.get('row') else None
        msg = (f"levels for {_date(lv.get('from_time'))} (the D1 bar of {_date(lv.get('bar_time'))}; "
               f"{tv['d1']['bars']} closed D1 bars): BUY at ask >= {_px(lv.get('buy'), d)} (the {e['days']}-day high "
               f"{_px(e.get('high'), d)} + {p['tick']:g}), SELL at bid <= {_px(lv.get('sell'), d)} (the {e['days']}-day low "
               f"{_px(e.get('low'), d)} - {p['tick']:g}); N {_num(lv.get('n'))}"
               + (f" ({lv.get('n_pct'):.2f}% of the price)" if lv.get('n_pct') else '')
               + f": a new trade's stop 2N = {_num(lv.get('stop_dist'))}, an add every 0.5N = {_num(lv.get('add_step'))}; "
               f"exit channel: the {x['days']}-day low {_px(x.get('long'), d)} (a long), the {x['days']}-day high "
               f"{_px(x.get('short'), d)} (a short)")
        if p['system'] == 1:
            hy = (tv.get('filter') or {}).get('hypothetical') or {}
            if lv.get('use20'):
                why = 'the 20-day breakout (its hypothetical trade is flat and the last one did not make money)'
            elif hy.get('state') in ('BUY', 'SELL'):
                why = (f"the 55-day failsafe: the hypothetical 20-day {hy['state']} of {_date(hy.get('since_t'))} is still "
                       f"open (its exit at {_px(hy.get('exit_level_next'), d)})")
            else:
                why = 'the 55-day failsafe: the last hypothetical 20-day breakout made money'
            msg += '; System 1 filter: ' + why
        if cb['side']:
            msg += f"; in the {'BUY' if cb['side'] == 1 else 'SELL'} trade: its stop is {_px(cb['stop'], d)}"
        else:
            msg += f"; orders {'armed' if cb['armed'] else 'used'} until {_hm(lv.get('until_t'))}"
            if not cb['armed'] and _f(c.last_entry) is not None:
                msg += f" (the deal history shows an entry at {_hm(c.last_entry)})"
        if first:
            msg = 'levels in force: ' + msg
        if days and days > 1.0:
            msg += f' ({days:g} D1 bars closed since the last poll: the bot was not running at their closes)'
        self._rec('INFO', 'LEVELS', msg, kv={
            'd1_bar': _iso(lv.get('bar_time')), 'from_utc': lv.get('from_utc'), 'until_utc': lv.get('until_utc'),
            'buy': lv.get('buy'), 'sell': lv.get('sell'), 'n': lv.get('n'), 'stop_dist': lv.get('stop_dist'),
            'add_step': lv.get('add_step'), 'exit_long': lv.get('trail_long'), 'exit_short': lv.get('trail_short'),
            'entry_high': e.get('high'), 'entry_low': e.get('low'), 'use20': lv.get('use20'), 'armed': cb['armed'],
            'bars': tv['d1']['bars'], 'channels': ch.get('all')})

    def _log_stop_move(self, c, tv, pb, cb, act, d):
        """A stop move of the open trade: INFO when it tightens (it only ever does), WARN otherwise. True when the
        journal changed."""
        buy = cb['side'] == 1
        old, new = pb['stop'], cb['stop']
        why = []
        if cb['row'] != pb.get('row') and cb['origin'] == 'channel':
            why.append(f"the {tv['params']['exit_days']}-day {'low' if buy else 'high'} of the D1 bar of "
                       f"{_date(cb['row'])}: the exit channel")
        if act in ('ADD_BUY', 'ADD_SELL') and cb['origin'] == '2N':
            why.append(f"2N {_num(cb['stop_dist'])} {'below' if buy else 'above'} the new leg's fill "
                       f"{_px(cb['legs'][-1][1] if cb['legs'] else None, d)}")
        if cb['origin'] == 'kept':
            why.append('kept where it was: a leg was closed outside the bot')
        if not why:
            why.append(self._origin_words(cb['origin'], 'BUY' if buy else 'SELL'))
        tr = tv.get('trade') or {}
        better = new > old if buy else new < old
        msg = (f"stop {'raised' if buy else 'lowered'} {_px(old, d)} -> {_px(new, d)} ({'; '.join(why)}); the "
               f"{tr.get('judged_on')} {_px(tr.get('price_now'), d)} is {_px(tr.get('to_stop'), d)} away"
               if better else f"the stop moved AGAINST the trade {_px(old, d)} -> {_px(new, d)} ({'; '.join(why)})")
        self._rec('INFO' if better else 'WARN', 'STOP', msg, kv={'side': 'BUY' if buy else 'SELL', 'from': old, 'to': new,
                                                                  'origin': cb['origin'], 'legs': len(cb['legs'])})
        rec = self._journal_rec([x[0] for x in cb['legs']])
        if rec is None:
            return False
        rec.setdefault('stops', []).append({'t': self._now(), 'stop': new, 'origin': cb['origin'], 'why': '; '.join(why)})
        return True

    def _turtle_results(self, doc):
        """An INFO RESULT line for every Turtle trade the deal history shows closed since the last read: its realised P/L
        from the deals, its exit, the total of this bot's closed trades after it. At the first read after a start, for
        the trades the journal knows and has no result of yet (closed while the bot was down: the broker's backstops
        ...); the result is kept in the journal, so no start repeats it."""
        closed = doc.get('closed') or []
        ids = {x['id'] for x in closed}
        first = self._closed_known is None
        known = self._closed_known or set()
        dirty = False
        for x in closed:
            if x['id'] in known:
                continue
            rec = self._journal_rec([leg.get('position_id') for leg in x.get('legs') or []])
            if (rec is not None and rec.get('result')) or (first and rec is None):
                continue
            if rec is not None:
                rec['result'] = {'pnl': x['pnl'], 'close_t': x.get('close_t'), 'exit_reason': x.get('exit_reason'),
                                 'balance_after': x.get('balance_after')}
                dirty = True
            tu = x.get('turtle') or {}
            self._rec('INFO', 'RESULT', f"the {x['side']} trade of {_hm(x.get('open_t'))} closed at {_hm(x.get('close_t'))}: "
                      f"realised {_usd(x['pnl'])} (profit {_usd(x.get('profit'))}, swap {_usd(x.get('swap'))}, commission "
                      f"{_usd(x.get('commission'))}" + (f", fee {_usd(x.get('fee'))}" if x.get('fee') else '')
                      + f") on {len(x.get('legs') or [])} leg(s), {x.get('lots')} lot, held "
                      f"{_dur(x.get('hold_s'))}; exit: {x.get('exit_reason_text')}; this bot's closed trades since its "
                      f"live start now total {_usd(x.get('balance_after'))}",
                      kv={'id': x['id'], 'side': x['side'], 'pnl': x['pnl'], 'legs': len(x.get('legs') or []),
                          'open_price': x.get('open_price'), 'close_price': x.get('close_price'),
                          'exit_reason': x.get('exit_reason'), 'exit_detail': x.get('exit_detail'),
                          'n_entry': tu.get('n_entry'), 'balance_after': x.get('balance_after')})
        self._closed_known = known | ids
        if dirty:
            self._journal_save()

    # ── the chart's overlay: the daily levels per D1 bar ──
    def _turtle_overlay(self, c, digits):
        rows, rows_t = c.rows, c.rows_t
        if rows is None or rows_t is None or not len(rows_t):
            return None
        k = dict(BARS_SPEC).get('D1', 200)
        dd = 6 if digits is None else digits
        t = np.asarray(rows_t, np.int64)[-k:]

        def col(name, nd):
            a = rows.get(name)
            if a is None:
                return None
            return [None if not math.isfinite(v) else round(float(v), nd) for v in np.asarray(a, float)[-k:]]
        out = {'d1_t': t.tolist(), 'from_t': (t + 86400).tolist(), 'buy': col('buy', dd), 'sell': col('sell', dd),
               'exit_long': col('trail_long', dd), 'exit_short': col('trail_short', dd), 'n': col('n', 2),
               'note': 'row k: the levels the D1 bar d1_t[k] sets for the day from from_t[k] (00:00 UTC): the buy / sell '
                       'stop-entry levels, the exit channels (a long / a short), N'}
        if rows.get('use20') is not None:
            out['use20'] = [bool(x) for x in np.asarray(rows['use20'])[-k:]]
        return {'turtle': out}

    # ── the journal: per Turtle trade, N at the entry, the level, every leg, every stop move, the exit ──
    def _journal_load(self):
        if self._journal is None:
            data = None
            try:
                with open(self.journal_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = None
            trades = (data or {}).get('trades') if isinstance(data, dict) else None
            self._journal = dict(trades) if isinstance(trades, dict) else {}
        return self._journal

    def _journal_rec(self, ids):
        J = self._journal_load()
        for i in ids or ():
            r = J.get(str(i))
            if r is not None:
                return r
        want = {_i(i) for i in ids or ()} - {None}
        if not want:
            return None
        for r in J.values():
            if want & {_i(x.get('id')) for x in r.get('legs') or []}:
                return r
        return None

    def _journal_view(self, ids):
        r = self._journal_rec(ids)
        if r is None:
            return None
        v = dict(r)
        v['entry_d1_utc'] = _iso(r.get('entry_d1_t'))
        v['opened_utc'] = _iso(r.get('opened_t'))
        v['stops'] = [dict(s, utc=_iso(s.get('t'))) for s in r.get('stops') or []]
        return v

    def _journal_save(self):
        J = self._journal_load()
        if len(J) > TURTLE_JOURNAL_KEEP:
            keep = sorted(J.items(), key=lambda kv: (kv[1].get('opened_t') or 0))[-TURTLE_JOURNAL_KEEP:]
            self._journal = J = dict(keep)
        try:
            self._write_json(self.journal_path, {'schema': SCHEMA, 'symbol': self.symbol, 'magic': self._cfg('MAGIC'),
                                                 'trades': J})
        except Exception as e:
            self.write_failed('the Turtle journal', self.journal_path, e)

    # ── words ──
    def _constants(self):
        """(name, effective value) of every constant: the value the module reading it holds. Never the old
        accounts' fingerprints, nor a constant whose name holds PIN, PASS or SECRET (hidden_constant): they are in
        no log line and not in the journal's start line."""
        cm = sys.modules.get('constants')
        names = [n for n in vars(cm) if n.isupper() and not n.startswith('_')] if cm is not None else []
        return [(n, self._cfg(n)) for n in names if not hidden_constant(n)]

    def _recorded_id(self, st, fill):
        """(v3.9.2-demo.5) The position id app.py _record_fill took from this fill's order answer, while the terminal has
        not listed it yet; None otherwise."""
        pid = _i((fill or {}).get('order'))
        return pid if pid is not None and pid in _unlisted_ids((st or {}).get('basket')) else None

    def _recorded_kv(self, st, fill):
        pid = self._recorded_id(st, fill)
        return {'recorded': pid} if pid is not None else {}

    def _recorded_words(self, st, fill):
        pid = self._recorded_id(st, fill)
        if pid is None:
            return ''
        return (f"; position {pid} is a leg of the basket from its fill (its id from the order's answer; the terminal "
                f"lists it within {_num(self._cfg('_PENDING_FILL_S'), 0)} s)")

    def _close_waits_for(self, st, side, closed, failed):
        """(v3.9.2-demo.5) The legs a close that closed every listed leg could not reach: recorded from their order,
        not listed yet (app.py _after_close keeps the basket, close_pending). [] when the close booked the basket."""
        b = (st or {}).get('basket')
        if not closed or failed or not isinstance(b, dict) or b.get('side') != side or not b.get('close_pending'):
            return []
        return _unlisted_ids(b)

    def _basket_words(self, b):
        if not b:
            return 'no basket'
        tgt, sl, u = _f(b.get('target_usd_per_unit')), _f(b.get('stop_usd_per_unit')), _i(b.get('units')) or 1
        return (f"{b.get('side')} basket (opened by {b.get('opened_by')}, {len(b.get('ids') or [])} position(s), unit {u}, "
                f"target {_usd(tgt * u) if tgt is not None else 'none'}, stop {_usd(-sl * u) if sl is not None else 'none'}, "
                f"volatility unit {_num(b.get('vol_unit'), 3) if b.get('vol_unit') is not None else 'n/a'}"
                + (', levels pending' if b.get('levels_pending') else '') + (', close pending' if b.get('close_pending') else '')
                + (', ladder armed' if b.get('ladder_armed') else '')
                + (f", {_unlisted_ids(b)} not listed by the terminal yet" if _unlisted_ids(b) else '') + ')')

    def _close_words(self, lc):
        if not lc:
            return 'none'
        return (f"{lc.get('side')} at {_hm(lc.get('time'))}, {lc.get('reason')}, P/L {_usd(lc.get('pnl'))}"
                f"{' (a loss)' if lc.get('lost') else ''}{'' if lc.get('resolved') else ' (not final yet)'}")


def _basket_sum(b):
    """What the log compares of a basket from one poll to the next."""
    if not b:
        return None
    return {'side': b.get('side'), 'ids': list(b.get('ids') or []), 'opened_by': b.get('opened_by'),
            'opened_at': b.get('opened_at'), 'levels_pending': b.get('levels_pending'),
            'close_pending': b.get('close_pending'), 'armed': b.get('ladder_armed'),
            'unlisted': _unlisted_ids(b), 'listed': b.get('first_time') is not None}


def _unlisted_ids(b):
    """(v3.9.2-demo.5) The ids of a basket's legs recorded from their order that the terminal has not listed yet."""
    out = []
    for u in (b or {}).get('unlisted') or []:
        pid = _i((u or {}).get('id')) if isinstance(u, dict) else None
        if pid is not None:
            out.append(pid)
    return sorted(out)


def _close_sum(lc):
    """What the log compares of the last close from one poll to the next."""
    if not lc:
        return None
    return {'time': lc.get('time'), 'resolved': lc.get('resolved'), 'lost': lc.get('lost'), 'pnl': lc.get('pnl'),
            'reason': lc.get('reason'), 'source': lc.get('source')}


def _s1_hypothetical(O, H, L, N, t, tick, T):
    """The Turtle System 1 filter's hypothetical trade (turtle.s1_use20, step for step: the same loop on the same closed
    D1 bars, with what it did kept): its state at the last bar (flat / BUY / SELL, entry, stop, since), whether its last
    trade won, use20, and its last five trades. Display only: the bot's use20 is turtle.s1_use20's."""
    O, H, L, N = (np.asarray(x, float) for x in (O, H, L, N))
    hi20, lo20 = T.roll_max(H, 20), T.roll_min(L, 20)
    hi10, lo10 = T.roll_max(H, 10), T.roll_min(L, 10)
    nb = len(O)
    hyp, entry, stop, last_win = 0, 0.0, 0.0, False
    cur, trades = None, []

    def done(b, px, win):
        nonlocal cur
        cur.update(exit_t=int(t[b]), exit_utc=_iso(int(t[b])), exit=float(px), win=bool(win))
        trades.append(cur)
        cur = None
    for b in range(nb):
        if b >= 1:
            if hyp == 0 and hi20[b - 1] == hi20[b - 1] and N[b - 1] == N[b - 1]:
                up_l, dn_l = hi20[b - 1] + tick, lo20[b - 1] - tick
                up, dn = H[b] >= up_l, L[b] <= dn_l
                if up and dn:
                    if up_l - O[b] <= O[b] - dn_l:
                        dn = False
                    else:
                        up = False
                if up:
                    hyp, entry = 1, max(up_l, O[b])
                    stop = entry - 2.0 * N[b - 1]
                    cur = {'side': 'BUY', 'entry_t': int(t[b]), 'entry_utc': _iso(int(t[b])), 'entry': float(entry),
                           'stop': float(stop)}
                    if L[b] <= stop:
                        hyp, last_win = 0, False
                        done(b, stop, False)
                elif dn:
                    hyp, entry = -1, min(dn_l, O[b])
                    stop = entry + 2.0 * N[b - 1]
                    cur = {'side': 'SELL', 'entry_t': int(t[b]), 'entry_utc': _iso(int(t[b])), 'entry': float(entry),
                           'stop': float(stop)}
                    if H[b] >= stop:
                        hyp, last_win = 0, False
                        done(b, stop, False)
            elif hyp == 1:
                ex = stop
                if lo10[b - 1] == lo10[b - 1] and lo10[b - 1] > ex:
                    ex = lo10[b - 1]
                if O[b] <= ex:
                    last_win, hyp = O[b] > entry, 0
                    done(b, O[b], last_win)
                elif L[b] <= ex:
                    last_win, hyp = ex > entry, 0
                    done(b, ex, last_win)
            elif hyp == -1:
                ex = stop
                if hi10[b - 1] == hi10[b - 1] and hi10[b - 1] < ex:
                    ex = hi10[b - 1]
                if O[b] >= ex:
                    last_win, hyp = O[b] < entry, 0
                    done(b, O[b], last_win)
                elif H[b] >= ex:
                    last_win, hyp = ex < entry, 0
                    done(b, ex, last_win)
    exit_now = None
    if hyp == 1:
        exit_now = max(stop, float(lo10[-1])) if lo10[-1] == lo10[-1] else stop
    elif hyp == -1:
        exit_now = min(stop, float(hi10[-1])) if hi10[-1] == hi10[-1] else stop
    return {'state': {1: 'BUY', -1: 'SELL'}.get(hyp, 'flat'), 'entry': float(entry) if hyp else None,
            'stop': float(stop) if hyp else None, 'exit_level_next': exit_now,
            'since_t': cur['entry_t'] if cur else None, 'since_utc': cur['entry_utc'] if cur else None,
            'last_win': bool(last_win), 'use20': bool(hyp == 0 and not last_win), 'trades': trades[-5:]}


def _tb_where(tb):
    """The last 'File ..., line N' of a traceback (what identifies a repeating error)."""
    if not tb:
        return None
    lines = [ln.strip() for ln in str(tb).splitlines() if ln.strip().startswith('File ')]
    return lines[-1] if lines else None
