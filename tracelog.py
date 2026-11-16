"""
tracelog.py -- what the bot sees, decides and does: the dashboard's data and a detailed text log.
(Demo branches: the basket strategy and the Turtle. Data contract schema 1; docs/dashboard-data.md has every field.)

Every file is in the bot's output folder (OUTPUT_DIR, or MT5TradingBot.trace_dir). JSON is compact, written
atomically (a temp file, then os.replace), times are UTC epoch seconds ("t", "..._t") with an ISO copy
("..._utc"). The files the old dashboard reads (<SYMBOL>.json, account.json, logs/<SYMBOL>_strategy_log.json,
daily_trade/...) are written as before, by app.py.

  <SYMBOL>_trace.json   the latest decision snapshot, after every poll (a poll takes >= 1 s, so every change of
                        action, position or gate result is in it): health, account, market, decision (action,
                        a plain-English headline, the gates in the order the bot checks them, this poll's
                        orders), basket (votes, scores, trend, volatility unit, the levels a new basket would
                        get, the pause, the open basket with its stop / target / backstop prices) or turtle (N,
                        the D1 channels, today's buy / sell levels and their orders, the System 1 filter, the M15
                        vote of closed bars and its parts, what a new trade would get, the open trade with its
                        legs, stop, next add and backstops); the other one null.
  <SYMBOL>_bars.json    bid OHLC for the chart: M1 360, M5 300, M15 300, H1 300, D1 200 bars (the last one is
                        forming), rewritten at most every 30 s and only when a bar moved or a new one started.
                        Basket: M1/M5/M15/H1 come from the bars the poll has already fetched; D1 costs one terminal
                        call. Turtle: all five from the terminal, plus the daily levels per D1 bar (overlay).
  <SYMBOL>_trades.json  this bot's trades from the deal history (its MAGIC, since VIRTUAL_START_DATE): every
                        closed basket / Turtle trade (legs, open / close, lots, P/L, the exit reason the bot
                        recorded; a Turtle trade also its N, entry level and stop history), the open one with its
                        live levels, the virtual-balance curve and a summary. Read after every fill and close (and
                        once more on the next poll), and every 60 s.
  logs/<SYMBOL>_<YYYY-MM-DD>.log   the text log, one file per UTC day, kept 30 days; one line per event:
                        'YYYY-MM-DD HH:MM:SS.mmm UTC | LEVEL | CATEGORY | message | key=value ...'
                        (split(' | ', 4) gives the five fields; the message never holds ' | '); an ERROR from an
                        exception is followed by its traceback, each line indented by 4 spaces. Levels: DEBUG
                        (every decision change), INFO, ORDER, FILL, CLOSE, WARN, ERROR. A HEARTBEAT line every
                        minute with the key numbers: a gap of more than a minute means the bot was not running.
                        Past 50 MB in a day only WARN / ERROR lines are added to that day's file.
  logs/<SYMBOL>_events.jsonl       the same lines as JSON ({t, time, level, cat, msg, kv, data, traceback}),
                        rotated at 10 MB into _events.1.jsonl (newest) .. _events.5.jsonl.
  state/<SYMBOL>_exit_reasons.json the exit reason the bot recorded per position id (feeds trades.json).
  state/<SYMBOL>_turtle_trades.json the Turtle's journal per trade: N at the entry, the level, the vote, every leg
                        with its add level, every stop move and the exit (feeds trades.json).

What this module may do -- the trading must never notice it:
  * it reads what the poll has already computed (app.py hands it the poll's locals at the end of the poll); the
    only terminal calls it makes are the deal history after a fill / close and every 60 s, the bars at most
    every 30 s (basket: D1 only), and the symbol's facts once (symbol_info), each under the bot's mt5_lock;
    the Turtle's RSI / MACD lines for the chart are computed again from the poll's closed M15 bars once per bar;
  * every entry point catches every Exception, logs it (ERROR with the traceback, repeats at most every 10 min)
    and returns; a write that fails is a WARN, the next poll tries again;
  * its own time per poll is measured (health.trace_ms; a millisecond or two).
"""
import enum
import functools
import json
import math
import numbers
import os
import re
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
TRADES_LOOKBACK_S = 90 * 86400   # without VIRTUAL_START_DATE: the history read goes back this far
HEARTBEAT_S = 60.0
LOG_RETENTION_DAYS = 30
LOG_DAY_CAP_BYTES = 50 * 2 ** 20
EVENTS_CAP_BYTES = 10 * 2 ** 20
EVENTS_KEEP = 5
EXIT_REASONS_KEEP = 5000
REPEAT_EVERY_S = 600.0           # the same error / warning is written again at most this often (with a count)
SLOW_POLL_MS = 5000.0            # a poll slower than this is a WARN
LEVELS = ('DEBUG', 'INFO', 'ORDER', 'FILL', 'CLOSE', 'WARN', 'ERROR')

ACTIONS = ('SKIPPED', 'NO_DATA', 'MARKET_CLOSED', 'WAIT', 'PAUSED', 'BLOCKED', 'OPEN_BUY', 'OPEN_SELL', 'OPEN_FAILED',
           'WAIT_FILL', 'HOLD', 'ADD_BUY', 'ADD_SELL', 'ADD_FAILED', 'CLOSE_BUY', 'CLOSE_SELL', 'BOTH_SIDES',
           'UNMANAGED')
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
}
# where the Turtle's one stop is (turtle.stop_origin): {origin: words} ({days} = the exit channel's length)
STOP_ORIGIN_TEXT = {'2N': '2N from the best fill', 'channel': 'the {days}-day {extreme}',
                    'kept': 'kept where it was when a leg was closed outside the bot'}
_BOT_REASON = {'target': 'target', 'stop_loss': 'stop', 'force_close': 'force_close', 'close_retry': 'close_retry',
               'closed_outside': 'closed_outside'}
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


def write_json_atomic(path, obj, retries=3):
    """Write obj as JSON to path: a temp file next to it, then os.replace (a reader sees the old file or the new
    one, never half of one). Returns the bytes written; raises OSError (the caller logs it)."""
    data = dumps(obj)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(data)
        for attempt in range(retries):
            try:
                os.replace(tmp, path)
                return len(data)
            except PermissionError:          # Windows: a reader (the dashboard) has the file open this moment
                if attempt == retries - 1:
                    raise
                time.sleep(0.005)
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


def _utc_dt(ts):
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


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
    """The text log (one file per UTC day, kept `retention_days`) and the events file (JSON lines, rotated by size).
    A batch is appended with one open / write / close per file, so nothing stays open (a reader, a deletion or a
    full disk never meets a handle of the bot). Never raises: lines a failed write could not store are kept (the
    newest 2000) and written with the next batch."""

    def __init__(self, log_dir, symbol, retention_days=LOG_RETENTION_DAYS, day_cap=LOG_DAY_CAP_BYTES,
                 events_cap=EVENTS_CAP_BYTES, events_keep=EVENTS_KEEP):
        self.dir = str(log_dir)
        self.symbol = str(symbol)
        self.retention_days = int(retention_days)
        self.day_cap = int(day_cap)
        self.events_cap = int(events_cap)
        self.events_keep = max(1, int(events_keep))
        self._lock = threading.Lock()
        self._day = None
        self._day_bytes = 0
        self._capped = False
        self._events_bytes = None
        self._text_backlog = deque(maxlen=2000)
        self._events_backlog = deque(maxlen=2000)
        self._note_t = None
        self.failures = 0
        self.last_error = None
        self._name = re.compile(r'^' + re.escape(self.symbol) + r'_(\d{4}-\d{2}-\d{2})\.log$')

    def day_path(self, day):
        return os.path.join(self.dir, f'{self.symbol}_{day}.log')

    @property
    def events_path(self):
        return os.path.join(self.dir, f'{self.symbol}_events.jsonl')

    def write(self, records):
        """records: (t, level, cat, msg, kv, data, tb) tuples. True when every line was stored."""
        records = list(records)
        with self._lock:
            ok = True
            batch = list(self._text_backlog) + records
            self._text_backlog.clear()
            try:
                if batch:
                    os.makedirs(self.dir, exist_ok=True)
                    self._write_text(batch)
            except Exception as e:
                self._text_backlog.extend(batch)
                ok = self._failed(e)
            batch = list(self._events_backlog) + records
            self._events_backlog.clear()
            try:
                if batch:
                    os.makedirs(self.dir, exist_ok=True)
                    self._write_events(batch)
            except Exception as e:
                self._events_backlog.extend(batch)
                ok = self._failed(e)
            return ok

    def _failed(self, e):
        self.failures += 1
        self.last_error = repr(e)
        now = time.time()
        if self._note_t is None or now - self._note_t >= 60.0:
            self._note_t = now
            try:
                print(f'[{self.symbol}] tracelog: cannot write the log in {self.dir}: {e!r} (trading goes on)')
            except Exception:
                pass
        return False

    def _open_day(self, day):
        if day == self._day:
            return
        self._day = day
        try:
            self._day_bytes = os.path.getsize(self.day_path(day))
        except OSError:
            self._day_bytes = 0
        self._capped = self._day_bytes >= self.day_cap
        self.retention(day)

    def retention(self, today):
        """Delete this symbol's day files `retention_days` or more days older than `today` ('YYYY-MM-DD')."""
        try:
            t_today = datetime.strptime(today, '%Y-%m-%d').date()
            names = os.listdir(self.dir)
        except (OSError, ValueError):
            return
        for name in names:
            m = self._name.match(name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), '%Y-%m-%d').date()
            except ValueError:
                continue
            if (t_today - d).days >= self.retention_days:
                try:
                    os.remove(os.path.join(self.dir, name))
                except OSError:
                    pass

    def _write_text(self, batch):
        by_day = {}
        for rec in batch:
            by_day.setdefault(_day(rec[0]), []).append(rec)
        for day in sorted(by_day):
            self._open_day(day)
            parts = []
            for t, level, cat, msg, kv, data, tb in by_day[day]:
                if self._capped and level not in ('WARN', 'ERROR'):
                    continue
                parts.append(format_line(t, level, cat, msg, kv, tb))
            if not parts:
                continue
            last_t = by_day[day][-1][0]
            text = ''.join(parts)
            size = len(text.encode('utf-8'))
            if not self._capped and self._day_bytes + size >= self.day_cap:
                self._capped = True
                text += format_line(last_t, 'WARN', 'LOG', f'this text log passed {self.day_cap / 2 ** 20:g} MB today: '
                                    f'until 00:00 UTC it takes only WARN and ERROR lines (the events file '
                                    f'{os.path.basename(self.events_path)} keeps every line)')
                size = len(text.encode('utf-8'))
            with open(self.day_path(day), 'a', encoding='utf-8') as f:
                f.write(text)
            self._day_bytes += size

    def _write_events(self, batch):
        text = ''.join(dumps(_event_dict(r)) + '\n' for r in batch)
        size = len(text.encode('utf-8'))
        path = self.events_path
        if self._events_bytes is None:
            try:
                self._events_bytes = os.path.getsize(path)
            except OSError:
                self._events_bytes = 0
        if self._events_bytes and self._events_bytes + size > self.events_cap:
            self._rotate_events()
        with open(path, 'a', encoding='utf-8') as f:
            f.write(text)
        self._events_bytes += size

    def _rotate_events(self):
        base = self.events_path[:-len('.jsonl')]
        for k in range(self.events_keep - 1, 0, -1):
            src = f'{base}.{k}.jsonl'
            if os.path.exists(src):
                os.replace(src, f'{base}.{k + 1}.jsonl')
        if os.path.exists(self.events_path):
            os.replace(self.events_path, f'{base}.1.jsonl')
        self._events_bytes = 0


# ───────────────────────────── the trace ─────────────────────────────

def _guarded(fn):
    """A trace entry point: whatever it raises is logged (ERROR + traceback) and swallowed; the lines it made are
    written at its end."""
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
            try:
                self._flush()
            except Exception:
                pass
    return call


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
    result, refused, ms) from MT5PositionHelper._send, event(...) from _log_event, state_saved(state),
    exception(cat, msg) from an except block, write_failed(what, path, error), log(level, cat, msg, kv)."""

    def __init__(self, bot, symbol, out_dir, app_module):
        self.bot = bot
        self.app = app_module
        self.symbol = str(symbol)
        self.mt5_symbol = (getattr(bot, 'symbol_map', None) or {}).get(symbol, symbol)
        self.out_dir = str(out_dir)
        self.log_dir = os.path.join(self.out_dir, 'logs')
        self.paths = {
            'trace': os.path.join(self.out_dir, f'{self.symbol}_trace.json'),
            'bars': os.path.join(self.out_dir, f'{self.symbol}_bars.json'),
            'trades': os.path.join(self.out_dir, f'{self.symbol}_trades.json'),
            'exits': os.path.join(self.out_dir, 'state', f'{self.symbol}_exit_reasons.json'),
        }
        strategy_mod = sys.modules.get(getattr(getattr(app_module, 'Strategy', None), '__module__', ''), None)
        helper_mod = sys.modules.get(getattr(getattr(app_module, 'MT5PositionHelper', None), '__module__', ''), None)
        self._mods = [m for m in (app_module, strategy_mod, helper_mod, sys.modules.get('constants')) if m is not None]
        self.writer = LogWriter(self.log_dir, self.symbol)
        self._lock = threading.Lock()          # the pending lines (log() may come from another thread)
        self._pending = []
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
        self._trades_dirty = True
        self._trades_again = False
        self._trades_retry_t = None
        self._prev = {}
        self._digits = None
        self._digits_t = None
        self._pending_reason = None
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
        self._closed_known = None              # the Turtle's closed trades already in trades.json (a RESULT line each)

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

    def _rec(self, level, cat, msg, kv=None, data=None, tb=None, t=None):
        t = self._now() if t is None else float(t)
        with self._lock:
            self._pending.append((t, level if level in LEVELS else 'INFO', cat, msg, kv, data, tb))
        if level == 'ERROR':
            self._errors.append(t)

    def _flush(self):
        with self._lock:
            recs, self._pending = self._pending, []
        if recs:
            self.writer.write(recs)

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

    def _hook_failed(self, name, e):
        tb = traceback.format_exc()
        write, n = self._repeat(('hook', name, type(e).__name__, _tb_where(tb)))
        if write:
            more = f' (it failed {n} more times since it was last written)' if n else ''
            self._rec('ERROR', 'TRACE', f'the trace hook {name}() failed: {e!r}; ignored, trading goes on{more}', tb=tb)
        else:
            self._errors.append(self._now())

    def _errors_1h(self, now):
        return sum(1 for t in self._errors if now - t <= 3600.0)

    # ── entry points ──
    @_guarded
    def log(self, level, cat, msg, kv=None, tb=None):
        self._rec(level, cat, msg, kv=kv, tb=tb)

    @_guarded
    def boot(self, records):
        """Lines the bot logged before this trace existed (job start, the account checks): (t, level, cat, msg, kv, tb)."""
        for t, level, cat, msg, kv, tb in records or ():
            self._rec(level, cat, msg, kv=kv, tb=tb, t=t)

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
            self._rec('WARN', 'WRITE', f'could not write {what}: {err!r}; trading goes on{more}', kv={'path': path})

    @_guarded
    def state_saved(self, state):
        b = (state or {}).get('basket')
        lc = (state or {}).get('last_close')
        self._rec('DEBUG', 'STATE', f'state saved: {self._basket_words(b)}; last close: {self._close_words(lc)}',
                  data={'basket': b, 'last_close': lc})

    @_guarded
    def state_note(self, level, msg):
        self._rec(level, 'STATE', msg)

    @_guarded
    def order(self, request, result, refused=False, ms=None):
        """Every order request of the bot (MT5PositionHelper._send) and its result; called inside the bot's mt5_lock."""
        r = request or {}
        typ = _i(r.get('type'))
        side = 'BUY' if typ == 0 else 'SELL' if typ == 1 else str(typ)
        is_close = 'position' in r
        if is_close:
            kind = 'close'
            what = f"close position {r.get('position')} ({'SELL' if typ == 0 else 'BUY'} {r.get('volume')} lot)"
        else:
            book = self._book_ref if isinstance(self._book_ref, dict) else None
            if book is not None:                 # the Turtle: its book (changed in place) says entry or add
                kind = 'add' if book.get('side') == (1 if side == 'BUY' else -1) else 'open'
            else:
                prev = self._prev.get('positions') or {}
                kind = 'add' if prev.get(side) else 'open'
            what = f"{kind} {side} {r.get('volume')} lot"
        retcode = _i(getattr(result, 'retcode', None))
        done = retcode in _DONE
        err = None
        if result is None and not refused:
            try:
                err = self.app.mt5.last_error()
            except Exception as e:
                err = repr(e)
        o = {
            't': self._now(), 'kind': kind, 'side': side, 'symbol': r.get('symbol'), 'volume': _f(r.get('volume')),
            'price': _f(r.get('price')), 'sl': _f(r.get('sl')), 'tp': _f(r.get('tp')), 'position': r.get('position'),
            'magic': r.get('magic'), 'comment': r.get('comment'), 'refused': bool(refused), 'retcode': retcode,
            'retcode_text': RETCODES.get(retcode) if retcode is not None else ('refused by the account guard'
                                                                               if refused else 'no answer'),
            'done': done, 'result_price': _f(getattr(result, 'price', None)),
            'result_volume': _f(getattr(result, 'volume', None)), 'order': _i(getattr(result, 'order', None)),
            'deal': _i(getattr(result, 'deal', None)), 'result_comment': getattr(result, 'comment', None),
            'last_error': err, 'ms': _f(ms, 2),
        }
        self._orders.append(o)
        d = self._digits                       # (known after the first poll; no terminal call in here: inside mt5_lock)
        price = f" at {_px(o['price'], d)}" if o['price'] is not None else ''
        stops = '' if is_close else f" sl {_px(o['sl'], d) if o['sl'] else 'none'} tp {_px(o['tp'], d) if o['tp'] else 'none'}"
        res = ('not sent: the account guard refused it' if refused else
               f"{o['retcode_text']} ({retcode})" if retcode is not None else f'no answer ({err})')
        kv = {k: o[k] for k in ('kind', 'side', 'symbol', 'volume', 'price', 'sl', 'tp', 'position', 'magic',
                                'comment', 'retcode', 'retcode_text', 'result_price', 'result_volume', 'order',
                                'deal', 'result_comment', 'last_error', 'ms') if o[k] is not None}
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

    _EVENTS = {  # the strategy log's events -> (level, category); None = covered by the ORDER / FILL / BASKET / CLOSE lines
        'BUY_EXECUTED': None, 'SELL_EXECUTED': None, 'BUY_MORE_EXECUTED': None, 'SELL_MORE_EXECUTED': None,
        'CLOSE_BUY': None, 'CLOSE_SELL': None,
        'BUY_SIGNAL': ('DEBUG', 'SIGNAL'), 'SELL_SIGNAL': ('DEBUG', 'SIGNAL'),
        'ACCOUNT_REFUSED': ('ERROR', 'ACCOUNT'), 'ACCOUNT_OK': ('INFO', 'ACCOUNT'),
        'TERMINAL_ERROR': ('WARN', 'TERMINAL'), 'TERMINAL_OK': ('INFO', 'TERMINAL'),
        'TERMINAL_RECONNECTED': ('INFO', 'TERMINAL'), 'RECONNECT_FAILED': ('ERROR', 'TERMINAL'),
        # the Turtle's: covered by the trace's LEVELS / TRADE / STOP / CLOSE lines (they diff the book every poll)
        'TURTLE_LEVELS': None, 'TURTLE_REBUILT': None, 'TURTLE_CLOSED_OUTSIDE': None, 'TURTLE_LEG_CLOSED_OUTSIDE': None,
    }

    @_guarded
    def event(self, event, tag, details=None, server_time=None):
        """An event of the strategy log (MT5TradingBot._log_event), as a log line."""
        if event == 'TERMINAL_RECONNECTED':
            self.reconnects += 1
        if event == 'TURTLE_NOTE':           # the Turtle's notes (at most every 5 min each): missing bars, refusals ...
            d = {k: v for k, v in (details or {}).items() if k != 'response'}
            note = str(d.pop('note', '') or 'note')
            self._rec('INFO' if note.lower().startswith('brake') else 'WARN', 'TURTLE', note, kv=d or None)
            return
        m = self._EVENTS.get(event, ('ERROR', 'EVENT') if tag == 'ERROR' else ('INFO', 'EVENT'))
        if m is None:
            return
        level, cat = m
        d = {k: v for k, v in (details or {}).items() if k != 'response'}
        note = d.get('note') or d.get('problem') or d.get('why')
        if cat == 'SIGNAL':                 # the brake note repeats every poll: once, then again after 10 min
            key = (event, note)
            write = self._repeat(('signal', key))[0]
            if key == self._last_signal_note and not write:
                return
            self._last_signal_note = key
        msg = {'ACCOUNT_REFUSED': 'not trading: {note}', 'ACCOUNT_OK': 'the terminal holds the demo account again: trading',
               'TERMINAL_ERROR': 'poll skipped, nothing decided: {note}',
               'TERMINAL_OK': 'the terminal answers again',
               'TERMINAL_RECONNECTED': 'connected to the terminal again',
               'RECONNECT_FAILED': 'reconnect failed: {note}'}.get(event, f'{event}: {{note}}' if note else event)
        self._rec(level, cat, msg.format(note=note), kv=d or None)

    @_guarded
    def loop_start(self, ctx):
        """The start of the trading loop: who, what design, every effective constant, symbols.json, the state found."""
        c = _Ctx(ctx)
        if self._is_turtle():
            return self._turtle_loop_start(c)
        bot = self.bot
        self._rec('INFO', 'START', f'trading loop started for {self.symbol} ({self.mt5_symbol} at the terminal)', kv={
            'branch': self._cfg('DEMO_BRANCH'), 'design': self._cfg('DESIGN_NAME'), 'strategy': self._cfg('STRATEGY'),
            'magic': self._cfg('MAGIC'), 'mode': getattr(bot, 'mode', None), 'pid': os.getpid(),
            'python': sys.version.split()[0], 'out_dir': self.out_dir, 'schema': SCHEMA})
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
        self._rec('INFO', 'START', 'files: ' + ', '.join(os.path.basename(p) for p in self.paths.values())
                  + f', logs/{self.symbol}_<day>.log, logs/{self.symbol}_events.jsonl', kv={'out_dir': self.out_dir})

    @_guarded
    def poll_skipped(self, kind, problem=None):
        """A poll that decided nothing: the terminal or the account was not right ('guard'), or the positions read
        failed ('positions')."""
        t0 = time.perf_counter()
        now = self._now()
        bot = self.bot
        self.polls += 1
        self.skipped += 1
        if kind == 'guard':
            why = getattr(bot, '_guard_why', None) or (None, None)
            kind, problem = why[0] or 'terminal', why[1] or problem
        if not problem:
            problem = getattr(bot, '_read_bad', None) if kind != 'account' else getattr(bot, '_account_bad', None)
        problem = problem or 'unknown'
        streak = _i(getattr(bot, '_failed_polls', 0)) or 0
        gates = [
            _gate('terminal', 'Terminal connected', kind != 'terminal', problem if kind == 'terminal' else 'answers',
                  'terminal_info() answers, connected to the trade server'),
            _gate('account', 'Demo account', None if kind == 'terminal' else kind != 'account',
                  problem if kind == 'account' else getattr(bot, '_account_login', None),
                  'the demo, hedging account of the credentials'),
            _gate('positions', 'Positions read', None if kind != 'positions' else False,
                  problem if kind == 'positions' else None, "positions_get() answers (this bot's magic only)"),
        ]
        decided = _mark_checked(gates)
        if kind == 'terminal':
            after = _i(self._cfg('_RECONNECT_AFTER')) or 5
            at = _f(getattr(bot, '_reconnect_at', None))
            nxt = f'next reconnect attempt at {_hm(at)}' if at else f'the bot reconnects after {after} such polls in a row'
            head = f'Poll skipped, nothing decided: {problem}. {streak} poll(s) in a row; {nxt}.'
        elif kind == 'account':
            head = (f'Poll skipped, nothing decided: {problem}. No order is sent until the terminal holds the demo '
                    f"account {getattr(bot, '_account_login', None)} again.")
        else:
            head = (f'Poll skipped, nothing decided: {problem}. The positions are not known, so the '
                    + ('trade is neither managed nor booked this poll (its stop is checked again on the next good one).'
                       if self._is_turtle() else 'basket is neither managed nor booked this poll.'))
        dec = {'action': 'SKIPPED', 'reason': kind, 'side': None, 'headline': head, 'gates': gates,
               'blocked_by': decided, 'signal': None, 'orders': self._take_orders()}
        health = self._health(None, now, skip=(kind, problem))
        prev = self._last_snapshot or {}
        snap = self._base(now)
        snap.update(stale=True, stale_since_utc=_iso(self._last_poll_t), health=health,
                    account=prev.get('account'), market=prev.get('market'), decision=dec,
                    basket=prev.get('basket'), turtle=prev.get('turtle'))
        self._decision_line(dec, now)
        self._write_trace(snap, dec, now, force=True)
        self._heartbeat(dec, snap, now)
        self._flush()
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
        if self._is_turtle():
            return self._poll_turtle(c)
        now = self._now()
        self.polls += 1
        orders = self._take_orders()
        digits = self._get_digits()
        snap = self._base(now)
        snap['health'] = self._health(c, now)
        snap['account'] = self._account(c)
        snap['market'] = self._market(c, now, digits)
        snap['basket'] = self._basket_section(c, now, digits, orders)
        snap['turtle'] = None
        dec = self._decide(c, snap, orders, now, digits)
        snap['decision'] = dec
        self._transitions(c, snap, dec, orders, now, digits)
        self._decision_line(dec, now)
        self._last_snapshot = snap
        self._write_trace(snap, dec, now)
        self._bars(c, now, digits)
        self._trades(c, snap, now, digits)
        self._heartbeat(dec, snap, now)
        self._prev['positions'] = {'BUY': _i(c._buy_ct) or 0, 'SELL': _i(c._sell_ct) or 0}
        self._last_poll_t = now
        self._flush()

    def _take_orders(self):
        orders, self._orders = self._orders, []
        return orders

    def _base(self, now):
        return {'schema': SCHEMA, 'branch': self._cfg('DEMO_BRANCH'), 'design': self._cfg('DESIGN_NAME'),
                'strategy': self._cfg('STRATEGY', 'basket'), 'symbol': self.symbol, 'mt5_symbol': self.mt5_symbol,
                'magic': self._cfg('MAGIC'), 't': round(now, 3), 'time_utc': _iso(now), 'poll': self.polls,
                'stale': False}

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
        acct = getattr(bot, '_last_account', None) or (None, None, None)
        mt5 = getattr(self.app, 'mt5', None)
        tm = {getattr(mt5, 'ACCOUNT_TRADE_MODE_DEMO', 0): 'demo', getattr(mt5, 'ACCOUNT_TRADE_MODE_CONTEST', 1): 'contest',
              getattr(mt5, 'ACCOUNT_TRADE_MODE_REAL', 2): 'real'}
        mm = {getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_NETTING', 0): 'netting',
              getattr(mt5, 'ACCOUNT_MARGIN_MODE_EXCHANGE', 1): 'exchange',
              getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING', 2): 'hedging'}
        h = {
            'connected': True, 'terminal_problem': None,
            'account_ok': getattr(bot, '_account_bad', None) is None,
            'account_problem': getattr(bot, '_account_bad', None),
            'login': acct[0], 'demo_login': getattr(bot, '_account_login', None),
            'trade_mode': acct[1], 'trade_mode_name': tm.get(acct[1]),
            'margin_mode': acct[2], 'margin_mode_name': mm.get(acct[2]),
            'market_live': None, 'market_status': None, 'minutes_since_activity': None, 'last_tick_age_s': None,
            'loop_ms': None, 'trace_ms': self.cost_ms,
            'reconnects': max(self.reconnects, _i(getattr(bot, '_reconnects_done', 0)) or 0),
            'errors_1h': self._errors_1h(now), 'skipped_polls': self.skipped,
            'failed_streak': _i(getattr(bot, '_failed_polls', 0)),
            'poll_gap_s': _f(now - self._last_poll_t, 2) if self._last_poll_t is not None else None,
            'started_utc': _iso(self.started_at), 'uptime_s': round(now - self.started_at, 1),
            'log_write_failures': self.writer.failures,
        }
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
        ai = c.account_info or {}
        mtqty = _f(c.mtqty) or 0.01
        units = _i(c.units) or 1
        virtual = bool(self._call('virtual_balance_enabled'))
        vb = _f(c._virtual_balance)
        if vb is None:
            vb = _f(getattr(self.bot, '_virtual_balance_last', None))
        vstart = _f(self._cfg('VIRTUAL_START_BALANCE'))
        open_pl = sum((_f((p or {}).get('total_profit')) or 0.0) for p in (c.buy_positions, c.sell_positions))
        step, top = _f(c.step_up_balance), _i(c.max_limit)
        return {
            'virtual': virtual, 'virtual_balance': _f(vb, 2) if virtual else None,
            'virtual_start_balance': vstart if virtual else None,
            'virtual_start_date': self._cfg('VIRTUAL_START_DATE') if virtual else None,
            'units': units, 'lot': round(units * mtqty, 2), 'mtqty': mtqty,
            'own_closed_pl': _f(vb - vstart, 2) if (virtual and vb is not None and vstart is not None) else None,
            'own_open_pl': round(open_pl, 2),
            'own_equity': _f(vb + open_pl, 2) if (virtual and vb is not None) else None,
            'balance': _f(ai.get('balance')), 'equity': _f(ai.get('equity')), 'margin': _f(ai.get('margin')),
            'margin_free': _f(ai.get('margin_free')), 'margin_level': _f(ai.get('margin_level')),
            'account_profit': _f(ai.get('profit')),
            'step_up_balance': step, 'unit_max_limit': top,
            'next_unit_at': (units * step) if (step and step > 0 and top and units < top) else None,
            'unit_rule': (f'unit = floor(balance / {step:g}) + 1, at most {top}, re-derived only while flat'
                          if step else 'unit 1'),
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
            'known_to_bot': bool(b),
        }

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
    def _decide(self, c, snap, orders, now, digits):
        a = c.analysis_data or {}
        bk = snap['basket']
        bs, ss = _sig_name(c.buy_signal), _sig_name(c.sell_signal)
        nb, ns = _i(c._buy_ct) or 0, _i(c._sell_ct) or 0
        login = (getattr(self.bot, '_last_account', None) or (None,))[0]
        G = [_gate('terminal', 'Terminal connected', True, 'answers', 'terminal_info() answers, connected to the trade server'),
             _gate('account', 'Demo account', True, login, 'the demo, hedging account of the credentials'),
             _gate('positions', 'Positions read', True, f'{nb} buy, {ns} sell', "positions_get() answers (this bot's magic only)")]
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
        if ov.get('close_pending'):
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
            if g.get('close_retry'):
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
            if cr and int(cr.get('failed_count') or 0):
                res = (f" The close is incomplete: {cr.get('closed_count')} closed, {cr.get('failed_count')} failed "
                       f"({'; '.join(cr.get('errors') or [])}); the rest is closed next poll.")
            if reason == 'target':
                return f"Closing the {side} basket at the target: P/L {_usd(pnl)} > target {_usd(ov.get('target_usd'))}." + res
            if reason == 'stop_loss':
                return f"Closing the {side} basket at the stop: P/L {_usd(pnl)} <= stop {_usd(-(ov.get('stop_usd') or 0))}." + res
            if reason == 'force_close':
                return (f"Closing the {side} basket: the agreement score {_sc(bk['fc_score'])} turned against it "
                        f"(force-close at {_sc(-bk['force_close_s'] if side == 'BUY' else bk['force_close_s'])})." + res)
            if reason == 'close_retry':
                return f'Closing the rest of the {side} basket (an earlier close left positions open).' + res
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
                         if vol.get('on') else ''),
                      kv={'side': dec['side'], 'price': fill.get('result_price'), 'lots': fill.get('result_volume'),
                          'units': ov.get('units'), 'target_usd': ov.get('target_usd'), 'stop_usd': ov.get('stop_usd'),
                          'target_price': ov.get('target_price'), 'stop_price': ov.get('stop_price'),
                          'backstop': fill.get('sl'), 'vol_unit': ov.get('vol_unit'), 'trend_signal': bk['trend'].get('signal'),
                          'open_score': bk['open_score'], 'fc_score': bk['fc_score']})
            self._trades_dirty = True
        elif act in ('ADD_BUY', 'ADD_SELL'):
            fill = next((o for o in orders if o['done'] and o['kind'] in ('add', 'open')), {})
            keep = [w for w, v in (('stop ' + _usd(-(ov.get('stop_usd') or 0)), ov.get('stop_usd')),
                                   ('target ' + _usd(ov.get('target_usd')), ov.get('target_usd'))) if v is not None]
            self._rec('INFO', 'BASKET', f"added {fill.get('result_volume') or fill.get('volume')} lot to the {dec['side']} basket "
                      f"at {_px(fill.get('result_price') or fill.get('price'), digits)} ({len(ov.get('legs') or []) + 1} "
                      'positions now)' + (f"; the basket's {' and '.join(keep)} "
                                          f"{'stay as they are' if len(keep) > 1 else 'stays as it is'} (in USD)" if keep else ''),
                      kv={'side': dec['side'], 'price': fill.get('result_price'), 'lots': fill.get('result_volume'),
                          'positions_before': len(ov.get('legs') or []), 'sl': fill.get('sl'),
                          'trigger': (ov.get('ladder') or {}).get('trigger'), 'tier': (ov.get('ladder') or {}).get('tier_tf')})
            self._trades_dirty = True
        elif act in ('CLOSE_BUY', 'CLOSE_SELL'):
            cr = c.close_response or {}
            closed, failed = int(cr.get('closed_count') or 0), int(cr.get('failed_count') or 0)
            reason = dec['reason']
            if reason == 'close_retry':
                reason = self._pending_reason or reason
            lc = st.get('last_close') or {}
            ids = [l['id'] for l in ov.get('legs') or [] if l.get('id') is not None]
            if closed:                       # the reason is the one of the close that closed (the rest follows it)
                self._record_exits(ids, reason, now, ov.get('pnl'))
            if closed and not failed:
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
            if new_ids:
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
            self._record_exits(ids, 'closed_outside', now, lc.get('pnl'))
            final = lc.get('resolved') and lc.get('source') == 'history'
            self._rec('CLOSE', 'CLOSE', f"the {lc.get('side')} basket was closed outside the bot (the broker's backstop, "
                      'the terminal, or while the bot was down): '
                      + (f"realised {_usd(lc.get('pnl'))}, its last closing deal at {_hm(lc.get('time'))} (deal history)"
                         if final else f"P/L last seen {_usd(lc.get('pnl'))}; the realised P/L and the closing time follow "
                                       'from the deal history'),
                      kv={'reason': 'closed_outside', 'ids': ids, 'pnl': lc.get('pnl'), 'final': bool(final),
                          'closed_utc': _iso(lc.get('time'))})
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
            self._rec('INFO', 'ACCOUNT', f"unit {prev.get('units')} -> {units}"
                      + (f" (virtual balance {_usd(acct.get('virtual_balance'), signed=False)})" if acct.get('virtual') else ''))
        upp = _f(c._usd_per_price)
        if upp != prev.get('usd_pp'):
            self._rec('INFO', 'CONFIG', f"contract size {bk.get('contract_size')}: {_usd(upp, signed=False)} per unit "
                      f"({acct.get('mtqty')} lot) for a 1.0 price move", kv={'usd_per_price': upp, 'digits': digits})
        if first:
            p = bk['pause']
            self._rec('INFO', 'STATE', f"first poll: {self._basket_words(b)}; last close: {self._close_words(lc)}"
                      + (f"; entry pause {_dur(p['left_s'])} left" if p['active'] else '')
                      + (f"; virtual balance {_usd(acct.get('virtual_balance'), signed=False)}, unit {units}"
                         if acct.get('virtual') else f'; unit {units}'),
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
              'units': ac.get('units'), 'virtual_balance': ac.get('virtual_balance'), 'open_pl': ac.get('own_open_pl'),
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
            write_json_atomic(self.paths['trace'], snap)
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
    def _trades(self, c, snap, now, digits):
        due = (self._trades_dirty or self._trades_again or self._trades_t is None
               or now - self._trades_t >= TRADES_INTERVAL_S)
        if not due or (self._trades_retry_t is not None and now < self._trades_retry_t):
            return
        virtual = bool(self._call('virtual_balance_enabled'))
        since = None
        if self._cfg('VIRTUAL_START_DATE') is not None:
            try:
                since = _f(self._call('_virtual_start_ts'))
            except Exception:
                since = None
        if since is None:
            since = now - TRADES_LOOKBACK_S
        with self.bot.mt5_lock:
            deals = self.bot.position_helper.get_bot_deals(_utc_dt(since), _utc_dt(now + 86400))
        if deals is None:
            self._trades_retry_t = now + TRADES_RETRY_S
            write, n = self._repeat(('history',), every=300.0)
            if write:
                self._rec('WARN', 'TRADES', 'the terminal gave no deal history: trades.json keeps its last content')
            return
        self._trades_retry_t = None
        doc = self._build_trades(list(deals), snap, since, now, digits, virtual)
        if self._is_turtle():
            self._turtle_results(doc)
        try:
            write_json_atomic(self.paths['trades'], doc)
        except Exception as e:
            self.write_failed('the trades', self.paths['trades'], e)
            self._trades_retry_t = now + 30.0               # no history read every poll while the disk fails
            return
        self._trades_again = self._trades_dirty
        self._trades_dirty = False
        self._trades_t = now

    def _build_trades(self, deals, snap, since, now, digits, virtual):
        sym = self.mt5_symbol
        vstart = (_f(self._cfg('VIRTUAL_START_BALANCE')) or 0.0) if virtual else 0.0
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
                'commission': round(sum(float(getattr(d, 'commission', 0) or 0) + float(getattr(d, 'fee', 0) or 0)
                                        for d in ds), 2),
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
                     'swap': round(sum(l['swap'] for l in ls), 2), 'commission': round(sum(l['commission'] for l in ls), 2)}
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
        curve = [{'t': since, 'utc': _iso(since), 'v': round(vstart, 2), 'id': None}]
        curve += [{'t': x['close_t'], 'utc': x['close_utc'], 'v': x['balance_after'], 'id': x['id'], 'pnl': x['pnl']}
                  for x in closed]
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
            'since_t': since, 'since_utc': _iso(since), 'virtual': virtual,
            'virtual_start_balance': vstart if virtual else None,
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
            write_json_atomic(self.paths['exits'], {'schema': SCHEMA, 'symbol': self.symbol, 'magic': self._cfg('MAGIC'),
                                                    'reasons': self._exits})
        except Exception as e:
            self.write_failed('the exit reasons', self.paths['exits'], e)

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
                      'branch': self._cfg('DEMO_BRANCH'), 'design': self._cfg('DESIGN_NAME'), 'strategy': 'turtle',
                      'system': p['system'], 'magic': self._cfg('MAGIC'), 'mode': getattr(bot, 'mode', None),
                      'pid': os.getpid(), 'python': sys.version.split()[0], 'out_dir': self.out_dir, 'schema': SCHEMA})
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
        self._rec('INFO', 'START', 'files: ' + ', '.join(names) + f', state/{os.path.basename(self.paths["exits"])}, '
                  f'state/{os.path.basename(self.journal_path)}, logs/{self.symbol}_<day>.log, logs/{self.symbol}_events.jsonl',
                  kv={'out_dir': self.out_dir})
        self._prev['turtle'] = self._book_sum(st)
        self._book_ref = c.st if isinstance(c.st, dict) else None
        self._journal_load()

    @_guarded
    def turtle_state_saved(self, st):
        """MT5TradingBot._save_turtle_state wrote the book."""
        self._rec('DEBUG', 'STATE', f'Turtle book saved: {self._book_words(st)}', data={'book': st})

    # ── one poll ──
    def _poll_turtle(self, c):
        now = self._now()
        self.polls += 1
        if isinstance(c.st, dict):
            self._book_ref = c.st
        orders = self._take_orders()
        facts = self._symbol_facts() or {}
        digits = facts.get('digits')
        if digits is None:
            digits = _i((getattr(self.bot, '_digits', None) or {}).get(self.mt5_symbol))
        snap = self._base(now)
        snap['health'] = self._health(c, now, live=bool(c.live), tick=c.tick)
        snap['account'] = self._account(c)
        snap['market'] = self._turtle_market(c, digits)
        snap['basket'] = None
        snap['turtle'] = self._turtle_section(c, now, digits, orders, facts)
        dec = self._turtle_decide(c, snap, orders, digits)
        snap['decision'] = dec
        self._turtle_transitions(c, snap, dec, orders, now, digits)
        self._decision_line(dec, now)
        self._last_snapshot = snap
        self._write_trace(snap, dec, now)
        tick = c.tick
        sig = None if tick is None else (getattr(tick, 'time_msc', None) or getattr(tick, 'time', None),
                                         _f(getattr(tick, 'bid', None)))
        self._bars(c, now, digits, sig=sig, overlay=lambda: self._turtle_overlay(c, digits))
        self._trades(c, snap, now, digits)
        self._heartbeat(dec, snap, now)
        self._prev['positions'] = {'BUY': self._count(c.buy_positions), 'SELL': self._count(c.sell_positions)}
        self._last_poll_t = now
        self._flush()

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
            'units_rule': 'the unit is fixed at the first fill (the virtual balance then); every leg = unit x mtqty lot',
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
        out = {'units': units, 'lots': lots, 'n': n, 'stop_dist': sd_, 'add_step': step, 'max_legs': p['max_legs'],
               'balance': _f(c._virtual_balance, 2)}
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
        login = (getattr(self.bot, '_last_account', None) or (None,))[0]
        G = [_gate('terminal', 'Terminal connected', True, 'answers', 'terminal_info() answers, connected to the trade server'),
             _gate('account', 'Demo account', True, login, 'the demo, hedging account of the credentials'),
             _gate('positions', 'Positions read', True, f'{nb} buy, {ns} sell', "positions_get() answers (this bot's magic only)")]
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
        if retry or (st.get('closing') and not closing_now):
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
            return f'CLOSE_{side}', ('close_retry' if retry else 'stop'), side
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
        return 'WAIT', None, None

    def _turtle_self_check(self, dec, bs, ss):
        """The gates are this module's reading of the decision; the bot's signals are the decision. A difference is a
        WARN (a bug of the trace, not of the trading), at most every 10 min."""
        if dec['action'] in ('SKIPPED', 'NO_DATA', 'MARKET_CLOSED', 'BOTH_SIDES', 'UNMANAGED'):
            return
        g = {x['key']: x for x in dec['gates']}
        if 'armed' in g:
            reads = all(g[k]['ok'] for k in ('armed', 'exit_bar', 'breakout', 'vote_known', 'vote', 'brake'))
            signal = bs == 'BUY' or ss == 'SELL'
        else:
            if 'close_retry' in g:
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
                left = _dur((_f(o.get('until_t')) or 0) - (_f(c.now) or 0)) if o.get('until_t') else 'n/a'
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
            if reason == 'close_retry':
                return f'Closing the rest of the {side} trade (an earlier close left legs open).' + res
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
                   'balance': _f(c._virtual_balance, 2), 'rebuilt': False,
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
                      + (f" (virtual balance {_usd(c._virtual_balance, signed=False)})" if acct.get('virtual') else '')
                      + f"; N {_num(tr.get('n_entry'))} frozen for the trade: stop {_px(tr.get('stop'), d)} "
                      f"({tr.get('stop_text')}), next add at {'ask >=' if side == 'BUY' else 'bid <='} "
                      f"{_px(tr.get('next_add'), d)}, up to {p['max_legs']} legs; broker backstop {_px(fill.get('sl'), d)}",
                      kv={'side': side, 'price': fill.get('result_price'), 'level': lvl, 'lots': fill.get('result_volume'),
                          'units': tr.get('units'), 'n_entry': tr.get('n_entry'), 'stop': tr.get('stop'),
                          'stop_origin': tr.get('stop_origin'), 'next_add': tr.get('next_add'), 'backstop': fill.get('sl'),
                          'vote': vt.get('last'), 'vote_bar': vt.get('bar_utc'), 'd1_bar': _iso(tr.get('entry_d1_t')),
                          'use20': (tv['levels'] or {}).get('use20'), 'balance': _f(c._virtual_balance, 2)})
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
            if closed:
                self._record_exits(ids, 'turtle_stop', now, tr.get('pnl'), extra=extra)
            if closed and not failed:
                rec = self._journal_rec(ids)
                if rec is not None:
                    rec['exit'] = {'t': now, 'reason': 'turtle_stop', 'stop': stop, 'origin': origin,
                                   'price': tr.get('price_now'), 'decision_pnl': tr.get('pnl')}
                    jdirty = True
                head = (f"the last {closed} leg(s) of the {side} trade closed (the close at the stop "
                        f"{_px(stop, d)} had left them open)" if dec['reason'] == 'close_retry' else
                        f"{side} trade closed at the stop ({self._origin_words(origin, side)}): {tr.get('judged_on')} "
                        f"{_px(tr.get('price_now'), d)} {'<=' if side == 'BUY' else '>='} {_px(stop, d)}; {closed} leg(s)")
                self._rec('CLOSE', 'CLOSE', f"{head}, P/L {_usd(tr.get('pnl'))} at the decision, held "
                          f"{_dur(tr.get('age_s'))}; the realised P/L follows from the deal history",
                          kv={'side': side, 'reason': 'turtle_stop', 'stop': stop, 'stop_origin': origin,
                              'price': tr.get('price_now'), 'decision_pnl': tr.get('pnl'), 'legs': closed,
                              'tickets': cr.get('closed_tickets'), 'n_entry': tr.get('n_entry'), 'held_s': tr.get('age_s'),
                              'retry': dec['reason'] == 'close_retry'})
            else:
                self._rec('WARN', 'CLOSE', f"the close of the {side} trade is incomplete: {closed} closed, {failed} failed "
                          f"({'; '.join(cr.get('errors') or []) or cr.get('message')}); the rest is closed next poll, "
                          'whatever the price', kv={'closed': closed, 'failed': failed, 'stop': stop})
            self._trades_dirty = True
        # the book after this poll, compared with the last one
        same = bool(pb['side'] and cb['side'] == pb['side'] and cb['entry_time'] == pb['entry_time'])
        if pb['side'] and not cb['side'] and act not in ('CLOSE_BUY', 'CLOSE_SELL'):
            ids = [x[0] for x in pb['legs'] if x[0] is not None]
            self._record_exits(ids, 'closed_outside', now, last_tr.get('pnl'), extra={'side': side_w[pb['side']]})
            rec = self._journal_rec(ids)
            if rec is not None and rec.get('exit') is None:
                rec['exit'] = {'t': now, 'reason': 'closed_outside', 'stop': pb.get('stop'), 'origin': pb.get('origin'),
                               'price': None, 'decision_pnl': last_tr.get('pnl')}
                jdirty = True
            self._rec('CLOSE', 'CLOSE', f"the {side_w[pb['side']]} trade was closed outside the bot (the broker's backstop, "
                      f"the terminal, or while the bot was down): its {len(ids)} leg(s) are gone; P/L last seen "
                      f"{_usd(last_tr.get('pnl'))}; the realised P/L and the closing deals follow from the deal history",
                      kv={'reason': 'closed_outside', 'ids': ids, 'pnl_last_seen': last_tr.get('pnl'),
                          'stop': pb.get('stop'), 'backstops': last_tr.get('backstop_prices')})
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
                self._rec('WARN', 'TRADE', f"leg(s) {gone} of the {side_w[cb['side']]} trade closed outside the bot (the "
                          f"broker's backstop, or by hand): {len(cb['legs'])} leg(s) left; the stop stays at "
                          f"{_px(cb['stop'], d)} ({self._origin_words(cb['origin'], side_w[cb['side']])})",
                          kv={'gone': gone, 'legs': len(cb['legs']), 'stop': cb['stop'], 'stop_origin': cb['origin']})
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
            self._rec('INFO', 'ACCOUNT', f"unit {prev.get('units')} -> {units}"
                      + (f" (virtual balance {_usd(acct.get('virtual_balance'), signed=False)})" if acct.get('virtual') else ''))
        if first:
            self._rec('INFO', 'STATE', f"first poll: {self._book_words(st)}; {vt['tf']} vote "
                      f"{_sc(vt.get('last')) if vt.get('fresh') else 'unknown'}"
                      + (f"; virtual balance {_usd(acct.get('virtual_balance'), signed=False)}, unit {units}"
                         if acct.get('virtual') else f'; unit {units}'), data={'book': self._book_copy(st)})
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
        from the deals, its exit, the virtual balance after it. At the first read after a start, for the trades the
        journal knows and has no result of yet (closed while the bot was down: the broker's backstops ...); the result
        is kept in the journal, so no start repeats it."""
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
                      f"{_usd(x.get('commission'))}) on {len(x.get('legs') or [])} leg(s), {x.get('lots')} lot, held "
                      f"{_dur(x.get('hold_s'))}; exit: {x.get('exit_reason_text')}"
                      + (f"; virtual balance now {_usd(x.get('balance_after'), signed=False)}" if doc.get('virtual') else ''),
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
            write_json_atomic(self.journal_path, {'schema': SCHEMA, 'symbol': self.symbol, 'magic': self._cfg('MAGIC'),
                                                  'trades': J})
        except Exception as e:
            self.write_failed('the Turtle journal', self.journal_path, e)

    # ── words ──
    def _constants(self):
        """(name, effective value) of every constant: the value the module reading it holds."""
        cm = sys.modules.get('constants')
        names = [n for n in vars(cm) if n.isupper() and not n.startswith('_')] if cm is not None else []
        return [(n, self._cfg(n)) for n in names]

    def _basket_words(self, b):
        if not b:
            return 'no basket'
        tgt, sl, u = _f(b.get('target_usd_per_unit')), _f(b.get('stop_usd_per_unit')), _i(b.get('units')) or 1
        return (f"{b.get('side')} basket (opened by {b.get('opened_by')}, {len(b.get('ids') or [])} position(s), unit {u}, "
                f"target {_usd(tgt * u) if tgt is not None else 'none'}, stop {_usd(-sl * u) if sl is not None else 'none'}, "
                f"volatility unit {_num(b.get('vol_unit'), 3) if b.get('vol_unit') is not None else 'n/a'}"
                + (', levels pending' if b.get('levels_pending') else '') + (', close pending' if b.get('close_pending') else '')
                + (', ladder armed' if b.get('ladder_armed') else '') + ')')

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
            'close_pending': b.get('close_pending'), 'armed': b.get('ladder_armed')}


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
