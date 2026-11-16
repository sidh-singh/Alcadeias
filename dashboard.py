"""
Alcadeias dashboard (demo branches): what the bot sees, decides and does, read from the files it writes.

It only reads OUTPUT_DIR (docs/dashboard-data.md lists every field) and never talks to the terminal. One page for
both strategies of the demo branches, told apart by the trace (`strategy`: 'basket' or 'turtle'):

  (every tab) the status bar and, when the open position is close to its target or stop (or a flat Turtle to an
           entry), an amber / red banner; an optional sound and browser notification
  Live     how close it is: meters from the entry to the target and to the stop (amber from 70 %, red from 90 %),
           the handy figures (P/L in $ and price, time in trade, legs, lot, balance, spread, last tick), a flat bot's
           entry conditions; what the bot is doing now: its one-sentence headline, every check in the order the
           bot makes it (passed / blocked / fired, the value against the rule), and the strategy's numbers
           (basket: the votes per timeframe with their pivots and slopes, the scores against their thresholds,
           the trend, the volatility unit, the pause, the levels a new basket would get; Turtle: N, the D1
           channels, today's buy / sell levels and their orders, the M15 vote of closed bars, System 1's filter,
           what a new trade would get); the OHLC chart with every entry, exit and the open trade's levels; the
           open position; the latest events
  Trades   the summary, the virtual balance after every close, every trade with its legs (newest first)
  Log      the events of logs/<SYMBOL>_events.jsonl with level filters and a search, the text log's path to copy
           and send, the raw text of the day's log
  Changes  every WARN / ERROR of the log grouped by kind (count, first / last time, meaning, what to do) and the
           branch's CHANGELOG.md version by version
  History  the old views that still apply (daily trades, the lifetime summary, the old strategy log), the
           settings as constants.py has them, the raw files

Times are UTC, as in the bot's log. Run:  python dashboard.py   (http://<host>:DASHBOARD_PORT)
"""
import functools
import glob
import json
import math
import os
import re
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone

import dash
from dash import dcc, html, no_update
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import constants as _C
from constants import (
    OUTPUT_DIR, DAILY_TRADE_SUBDIR,
    DASHBOARD_REFRESH_INTERVAL, DASHBOARD_HOST, DASHBOARD_PORT,
    HISTORICAL_SUMMARY_FILENAME,
    GRAPH_TEXT_LABEL_THRESHOLD, GRAPH_CUM_LABEL_THRESHOLD,
    STRATEGY_LOG_FILENAME,
    ACTIVE_CONFIG_FILENAME,
    ENTRY_S, ENTRY_AGREE_S, FORCE_CLOSE_S,
    OPEN_SCORE_WEIGHTS, FORCE_CLOSE_SCORE_WEIGHTS,
)

# ───────────────────────────── configuration ─────────────────────────────

JSON_DIR = OUTPUT_DIR                     # every path is built from this at call time (a test may point it elsewhere)
REFRESH_INTERVAL = DASHBOARD_REFRESH_INTERVAL
STATE_SUBDIR = getattr(_C, 'STATE_SUBDIR', 'state')
TIMEFRAMES = ('M1', 'M5', 'M15', 'H1', 'D1')
VIEW_BARS = 160                          # the chart opens on the newest 160 bars (drag or zoom out for the rest)
TF_SECONDS = {'M1': 60, 'M5': 300, 'M15': 900, 'M30': 1800, 'H1': 3600, 'H4': 14400, 'H6': 21600, 'D1': 86400}
LOG_LEVELS = ('ERROR', 'WARN', 'ORDER', 'FILL', 'CLOSE', 'INFO', 'DEBUG')
EVENTS_TAIL_BYTES = 3 * 2 ** 20           # the log tab parses the newest 3 MB of the events file
TEXT_TAIL_BYTES = 512 * 2 ** 10           # ... and shows the newest 512 KB of the day's text log
STALE_WARN_S = 15.0                       # the trace is rewritten after every poll (about 1 s): older is slow ...
STALE_S = 60.0                            # ... and older than this the bot is not running (or cannot write)
TRADES_STALE_S = 180.0                    # trades.json is rewritten at least every 60 s (tracelog TRADES_INTERVAL_S)
HERE = os.path.dirname(os.path.abspath(__file__))

# What a request may name. The page's own values are the symbols of OUTPUT_DIR and the days of their text logs, but a
# client can send any value to a callback (Dash does not check a RadioItems value against its options): a symbol is
# taken only when symbols() lists it, a day only when it reads YYYY-MM-DD and that day's file exists, and every path
# is built from fixed names inside OUTPUT_DIR (_path refuses any other).
_SYMBOL_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}')
_DAY_NAME = re.compile(r'\d{4}-\d{2}-\d{2}')


class OutsideOutputDir(ValueError):
    """A path that would leave OUTPUT_DIR: refused, nothing is read."""


def _now():
    """Wall-clock UTC seconds (a test or a screenshot run may replace this)."""
    return time.time()


def _path(*parts):
    """A file of OUTPUT_DIR: refused (OutsideOutputDir) when the parts would lead out of it (.., an absolute path)."""
    base = os.path.abspath(JSON_DIR)
    p = os.path.abspath(os.path.join(base, *parts))
    try:
        inside = os.path.commonpath([base, p]) == base
    except ValueError:                    # another drive (Windows)
        inside = False
    if not inside:
        raise OutsideOutputDir('a path outside the output folder was refused')
    return p


def is_symbol_name(s):
    """A plain symbol name ('XAUUSDm', 'BTCUSDm'): letters, digits, '.', '_', '-'; no folder, no '..'."""
    return isinstance(s, str) and _SYMBOL_NAME.fullmatch(s) is not None and '..' not in s


def valid_symbol(sym):
    """sym when symbols() lists it, else the first symbol ('' when there is none): what a client sends never
    reaches a path."""
    syms = symbols()
    if isinstance(sym, str) and sym in syms:
        return sym
    return syms[0] if syms else ''


def valid_day(sym, day):
    """day when it reads YYYY-MM-DD and the text log of that day of sym exists, else None."""
    if not isinstance(day, str) or not _DAY_NAME.fullmatch(day):
        return None
    return day if any(d_ == day for d_, _, _ in log_files(sym)) else None


def _rel(path):
    """A file of OUTPUT_DIR by its name there ('logs/XAUUSDm_events.jsonl'): the page shows no folder of this PC."""
    try:
        return os.path.relpath(path, os.path.abspath(JSON_DIR))
    except ValueError:
        return os.path.basename(path)


_TB_FILE = re.compile(r'File "([^"]+)"')


def _scrub(text):
    """A text for the page with file names instead of full paths: 'File "app.py", line 12' in a traceback; the
    output folder, the bot folder and the user's profile folder named, not spelled out. The page has no login: it
    shows no folder of this PC (the copy-path boxes of the log files are the one exception: that is the file to send)."""
    if text is None:
        return ''
    text = _TB_FILE.sub(lambda m: 'File "%s"' % os.path.basename(m.group(1).replace('\\', '/')), str(text))
    folders = [(os.path.abspath(JSON_DIR), 'OUTPUT_DIR'), (HERE, 'the bot folder')]
    home = os.path.expanduser('~')
    if home and home not in ('~', os.sep) and len(home) > 3:
        folders.append((home, '~'))
    for folder, name in sorted(folders, key=lambda z: -len(z[0])):
        text = text.replace(folder + os.sep, name + '/' if name == '~' else '').replace(folder, name)
        if '\\' in folder:                       # the same folder inside a JSON text: C:\\Alcadeias\\...
            esc = folder.replace('\\', '\\\\')
            text = text.replace(esc + '\\\\', name + '/' if name == '~' else '').replace(esc, name)
    return text


def _scrub_obj(v):
    """_scrub over every string of a JSON value (the kv and data of an event)."""
    if isinstance(v, str):
        return _scrub(v)
    if isinstance(v, dict):
        return {k: _scrub_obj(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub_obj(x) for x in v]
    return v


# ───────────────────────────── colours (one accent; green / red only for profit-loss and pass-fail) ─────────────

COL = {
    'page': '#070b17', 'surface': '#0c1324', 'raised': '#111a2e', 'raised2': '#16213a',
    'line': '#1f2a44', 'grid': '#162036',
    'text': '#eef0f5', 'text2': '#aab3c5', 'muted': '#8b95aa', 'faint': '#5d6a85',
    'accent': '#d4a843', 'pos': '#3cc48e', 'neg': '#e05555', 'warn': '#f0c040', 'blue': '#4a8ecc',
    'candle_up': '#26a69a', 'candle_down': '#ef5350',
}
FONT = 'Inter, "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
MONO = '"JetBrains Mono", "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace'


# ───────────────────────────── reading the files ─────────────────────────────

_CACHE = {}


def read_json(path):
    """(data, problem): the parsed file, cached until it changes; (None, 'missing' / 'unreadable ...') else."""
    try:
        st = os.stat(path)
    except OSError:
        return None, 'missing'
    key = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(path)
    if hit is not None and hit[0] == key:
        return hit[1], hit[2]
    try:
        # read, close, then parse: on Windows the bot cannot replace a file while it is open here, so the file is
        # held for the read only (about 1 ms), not for the whole parse (10-40 ms for a full trades.json)
        with open(path, 'rb') as f:
            raw = f.read()
        data, problem = json.loads(raw.decode('utf-8')), None
    except (OSError, ValueError) as e:
        data, problem = None, f'unreadable ({e.__class__.__name__})'
    _CACHE[path] = (key, data, problem)
    return data, problem


def file_sig(*paths):
    """A cheap fingerprint of files (size and modification time): it changes when any of them changes."""
    out = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append(f'{st.st_size}:{st.st_mtime_ns}')
        except OSError:
            out.append('-')
    return '|'.join(out)


def trace_path(sym):
    return _path(f'{sym}_trace.json')


def bars_path(sym):
    return _path(f'{sym}_bars.json')


def trades_path(sym):
    return _path(f'{sym}_trades.json')


def events_path(sym):
    return _path('logs', f'{sym}_events.jsonl')


def text_log_path(sym, day):
    return _path('logs', f'{sym}_{day}.log')


def load(sym):
    """Everything the Live and Trades tabs read for one symbol; a file that is missing or unreadable is None."""
    out = {'symbol': sym}
    for key, path in (('trace', trace_path(sym)), ('bars', bars_path(sym)), ('trades', trades_path(sym)),
                      ('old', _path(f'{sym}.json')), ('account', _path('account.json'))):
        data, problem = read_json(path)
        out[key] = data if isinstance(data, dict) else None
        out[key + '_problem'] = problem if data is None else (None if isinstance(data, dict) else 'not an object')
    return out


def symbols():
    """The symbols with a trace file in OUTPUT_DIR, else those of symbols.json (plain symbol names only)."""
    try:
        found = sorted(n[:-len('_trace.json')] for n in os.listdir(os.path.abspath(JSON_DIR))
                       if n.endswith('_trace.json') and is_symbol_name(n[:-len('_trace.json')]))
    except OSError:
        found = []
    if found:
        return found
    try:
        with open(os.path.join(HERE, 'symbols.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        return [s.get('symbol') for s in cfg.get('symbols', []) if isinstance(s, dict) and is_symbol_name(s.get('symbol'))]
    except (OSError, ValueError, AttributeError):
        return []


# ───────────────────────────── small helpers ─────────────────────────────

def g(d, *keys, default=None):
    """d[k1][k2]... or `default` when any step is missing or None (lists take integer keys)."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        elif isinstance(d, (list, tuple)) and isinstance(k, int) and -len(d) <= k < len(d):
            d = d[k]
        else:
            return default
        if d is None:
            return default
    return d


def num(x):
    """float(x), or None for None / NaN / inf / text / booleans."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def lst(x):
    """x when it is a list, else [] (every field of the files can be null)."""
    return x if isinstance(x, list) else []


def dl(x):
    """The dicts of a list (a malformed or null element is skipped)."""
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def dd(x):
    return x if isinstance(x, dict) else {}


def money(x, signed=False, dp=2):
    v = num(x)
    if v is None:
        return '—'
    body = f'{abs(v):,.{dp}f}'
    if v < 0:
        return f'-${body}'
    return f'+${body}' if signed and v > 0 else f'${body}'


def px(x, digits=2):
    v = num(x)
    return '—' if v is None else f'{v:,.{max(0, int(digits))}f}'


def fnum(x, dp=2, signed=False):
    v = num(x)
    if v is None:
        return '—'
    s = f'{v:,.{dp}f}'
    return ('+' + s) if signed and v > 0 else s


def pct(x, dp=1):
    v = num(x)
    return '—' if v is None else f'{v * 100:.{dp}f}%'


_ISO = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')


def ts(x):
    """Epoch seconds from a number or an ISO text ('2026-11-17T08:00:01.500Z'); None otherwise."""
    v = num(x)
    if v is not None:
        return v
    if isinstance(x, str) and _ISO.match(x):
        try:
            return datetime.fromisoformat(x.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return None


def utc(t):
    return datetime.fromtimestamp(t, tz=timezone.utc)


def when(t, seconds=True):
    """'08:07:37 UTC', with the day in front when it is not today (UTC)."""
    t = ts(t)
    if t is None:
        return '—'
    d = utc(t)
    clock = d.strftime('%H:%M:%S' if seconds else '%H:%M')
    if d.date() != utc(_now()).date():
        return f'{d.strftime("%d %b")} {clock} UTC'
    return f'{clock} UTC'


def stamp(t):
    """'2026-11-17 08:07:37 UTC'."""
    t = ts(t)
    return '—' if t is None else utc(t).strftime('%Y-%m-%d %H:%M:%S UTC')


def dur(s):
    """A length of time in words: '12 s', '4.6 min', '2.3 h', '3.1 d'."""
    v = num(s)
    if v is None:
        return '—'
    v = abs(v)
    if v < 1:
        return '<1 s'
    if v < 90:
        return f'{v:.0f} s'
    if v < 5400:
        return f'{v / 60:.1f} min'
    if v < 172800:
        return f'{v / 3600:.1f} h'
    return f'{v / 86400:.1f} d'


def countdown(s):
    v = num(s)
    if v is None or v <= 0:
        return '0:00'
    v = int(round(v))
    h, rem = divmod(v, 3600)
    m, sec = divmod(rem, 60)
    return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'


def smart(v, digits=None):
    """A gate's value or any loose number as text: adaptive decimals, times as clock times."""
    if v is None:
        return '—'
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, (int, float)):
        f = num(v)
        if f is None:
            return '—'
        if f == int(f) and abs(f) < 1e7:
            return f'{int(f):,}'
        if digits is not None and abs(f) >= 100:          # a price: the symbol's digits
            return f'{f:,.{digits}f}'
        a = abs(f)
        if a >= 100:
            return f'{f:,.2f}'
        if a >= 1:
            return f'{f:,.3f}'.rstrip('0').rstrip('.')
        return f'{f:.4g}'
    if isinstance(v, str):
        if _ISO.match(v):
            return when(v)
        return v
    if isinstance(v, (list, tuple)):
        return ', '.join(smart(x, digits) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, default=str)
    return str(v)


def signed(x):
    """A score or a contribution with its sign: '+2', '-0.5', '0'."""
    v = num(x)
    return '—' if v is None else ('+' if v > 0 else '') + smart(v)


def vote_glyph(v):
    """+1 / -1 / 0 as an arrow and a signed number (never colour alone)."""
    v = num(v)
    if v is None:
        return '?'
    return '▲ +1' if v > 0 else ('▼ -1' if v < 0 else '– 0')


def side_glyph(side):
    s = str(side or '').upper()
    return '▲ BUY' if s == 'BUY' else ('▼ SELL' if s == 'SELL' else (s or '—'))


def pl_class(x):
    v = num(x)
    return 'pos' if v is not None and v > 0 else ('neg' if v is not None and v < 0 else '')


def digits_of(d):
    v = num(g(d, 'trace', 'market', 'digits'))
    if v is None:
        v = num(g(d, 'bars', 'digits'))
    return int(v) if v is not None else 2


# ───────────────────────────── building blocks ─────────────────────────────

def card(title=None, body=None, right=None, sub=None, cls='', cid=None):
    head = None
    if title is not None or right is not None:
        head = html.Div(className='card-head', children=[
            html.Div([html.H2(title, className='card-title') if title else None,
                      html.Div(sub, className='card-sub') if sub else None]),
            html.Div(right, className='card-right') if right is not None else None,
        ])
    kw = {'id': cid} if cid else {}
    return html.Section(className=('card ' + cls).strip(), children=[head, body], **kw)


def badge(text, kind='neutral', title=None):
    kw = {'title': title} if title else {}
    return html.Span(text, className=f'badge badge-{kind}', **kw)


CHIP_ICON = {'pos': '●', 'neg': '■', 'warn': '▲'}


def chip(text, kind='', title=None, icon=None):
    """A rounded label; pass/fail chips carry a shape as well as a colour (● ok, ▲ warning, ■ problem)."""
    kw = {'title': title} if title else {}
    icon = CHIP_ICON.get(kind) if icon is None else icon
    kids = [html.Span(icon, className='chip-ic'), text] if icon else text
    return html.Span(kids, className=('chip ' + (f'chip-{kind}' if kind else '')).strip(), **kw)


def kv(label, value, cls='', title=None):
    kw = {'title': title} if title else {}
    return html.Div(className=('kv ' + cls).strip(), children=[
        html.Span(label, className='kv-k'), html.Span(value, className='kv-v', **kw)])


def tile(label, value, sub=None, cls='', vcls=''):
    return html.Div(className=('tile ' + cls).strip(), children=[
        html.Div(label, className='tile-k'),
        html.Div(value, className=('tile-v ' + vcls).strip()),
        html.Div(sub, className='tile-sub') if sub else None,
    ])


def pl(x, signed=True):
    return html.Span(money(x, signed=signed), className=('mono ' + pl_class(x)).strip())


def empty(text, sub=None):
    return html.Div(className='empty', children=[html.Div(text), html.Div(sub, className='empty-sub') if sub else None])


def table(head, rows, cls='', num_cols=()):
    """A plain table: `head` = column names; `rows` = lists of cells; columns in num_cols are right-aligned."""
    def cell(tag, i, c):
        return tag(c, className='num' if i in num_cols else None)
    return html.Table(className=('tbl ' + cls).strip(), children=[
        html.Thead(html.Tr([cell(html.Th, i, h) for i, h in enumerate(head)])),
        html.Tbody([html.Tr([cell(html.Td, i, c) for i, c in enumerate(r)]) for r in rows]),
    ])


def meter(lo, hi, value, marks=(), bands=(), lo_label=None, hi_label=None, kind='accent'):
    """A horizontal track from lo to hi: shaded `bands` [(a, b, cls)], tick `marks` [(x, label, cls)] with their
    labels above the track, the value's marker on it; the two end labels below. Positions are clamped to the
    track; a label near an end is anchored inside it."""
    lo, hi, v = num(lo), num(hi), num(value)
    if lo is None or hi is None or hi <= lo:
        return html.Div(className='meter meter-empty', children='—')

    def at(x):
        return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100.0))
    kids = []
    for a, b, bcls in bands:
        a, b = num(a), num(b)
        if a is None or b is None:
            continue
        left, right = at(min(a, b)), at(max(a, b))
        kids.append(html.Div(className=f'm-band {bcls}', style={'left': f'{left}%', 'width': f'{right - left}%'}))
    tops = []
    for x, label, mcls in marks:
        x = num(x)
        if x is None:
            continue
        p = at(x)
        kids.append(html.Div(className=f'm-tick {mcls}', style={'left': f'{p}%'}))
        if label:
            shift = '0' if p < 12 else ('-100%' if p > 88 else '-50%')
            tops.append(html.Span(label, className=f'm-tlabel {mcls}',
                                  style={'left': f'{p}%', 'transform': f'translateX({shift})'}))
    if v is not None:
        kids.append(html.Div(className=f'm-dot m-dot-{kind}', style={'left': f'{at(v)}%'}))
    return html.Div(className='meter', children=[
        html.Div(tops, className='m-top'),
        html.Div(kids, className='m-track'),
        html.Div(className='m-bottom', children=[html.Span(lo_label or '', className='m-lo'),
                                                 html.Span(hi_label or '', className='m-hi')]),
    ])


def safe(kind='view'):
    """Wrap a view builder: an exception (a file of an unexpected shape) becomes a card with the traceback, or an
    empty figure with the error, so the rest of the page still shows. Both name files, never their folders."""
    def wrap(fn):
        @functools.wraps(fn)
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as e:  # noqa: BLE001 -- the page must not die on one bad field
                tb = _scrub(traceback.format_exc())
                what = _scrub(f'{e.__class__.__name__}: {e}')
                if kind == 'figure':
                    fig = go.Figure()
                    fig.add_annotation(text=f'This chart could not be drawn: {what}', x=0.5, y=0.5,
                                       xref='paper', yref='paper', showarrow=False, font=dict(color=COL['neg']))
                    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300)
                    fig.update_xaxes(visible=False)
                    fig.update_yaxes(visible=False)
                    return fig
                return card(f'{fn.__name__}: could not be shown',
                            html.Div([html.Div(f'{what} — the rest of the page is not affected; '
                                               f'send this text if it stays.', className='line'),
                                      html.Pre(tb[-4000:], className='pre pre-err')]), cls='card-error')
        return run
    return wrap


# ───────────────────────────── the status bar ─────────────────────────────

def freshness(tr):
    """(kind, text) of the trace's age: live / slow / stale / none."""
    t = ts(g(tr, 't'))
    if t is None:
        return 'neg', 'No trace file: the bot has not written yet'
    age = _now() - t
    if age < -5:
        return 'warn', f'Updated {when(t)} (the clock of this PC is behind)'
    if age < STALE_WARN_S:
        return 'pos', f'Updated {dur(age)} ago'
    if age < STALE_S:
        return 'warn', f'Updated {dur(age)} ago (slow)'
    return 'neg', f'Stale: last update {dur(age)} ago — is the bot running?'


def trace_age(tr):
    """Seconds since the bot wrote the trace (None without one)."""
    t = ts(g(tr, 't'))
    return None if t is None else _now() - t


def is_stale(tr):
    """The bot has not written the trace for STALE_S: everything in it is its last poll, not now."""
    age = trace_age(tr)
    return age is not None and age >= STALE_S


def hm(t):
    """'09:10' (UTC), the day in front when it is not today."""
    return when(t, seconds=False).replace(' UTC', '')


def as_of(d):
    """' (as of 09:10)' when the trace is stale, else ''."""
    tr = dd(d.get('trace')) if isinstance(d, dict) else {}
    return f" (as of {hm(tr.get('t'))})" if is_stale(tr) else ''


_ERR_CACHE = {}


def errors_last_hour(sym, tail=EVENTS_TAIL_BYTES):
    """(count, problem): the ERROR lines of logs/<SYMBOL>_events.jsonl of the last hour, from its newest `tail` bytes.
    Unlike the trace's errors_1h it keeps counting when the trace stops (the bot down, or its loop failing)."""
    path = events_path(sym)
    try:
        st = os.stat(path)
    except OSError:
        return None, 'missing'
    key = (st.st_mtime_ns, st.st_size)
    hit = _ERR_CACHE.get(path)
    if hit is None or hit[0] != key:
        try:
            with open(path, 'rb') as f:
                if st.st_size > tail:
                    f.seek(st.st_size - tail)
                raw = f.read()
        except OSError as e:
            return None, f'unreadable ({e.__class__.__name__})'
        times = []
        for ln in raw.split(b'\n'):
            if b'"ERROR"' not in ln:                # (only those lines are parsed)
                continue
            try:
                ev = json.loads(ln.decode('utf-8', 'replace'))
            except ValueError:
                continue
            if not isinstance(ev, dict) or str(ev.get('level') or '').upper() != 'ERROR':
                continue
            t = ts(ev.get('t'))
            if t is not None:
                times.append(t)
        if len(_ERR_CACHE) > 8:
            _ERR_CACHE.clear()
        hit = _ERR_CACHE[path] = (key, times)
    now = _now()
    return sum(1 for t in hit[1] if now - 3600.0 <= t <= now + 60.0), None


@safe()
def status_bar(sym, d):
    tr = dd(d.get('trace'))
    h, acc, mk = dd(tr.get('health')), dd(tr.get('account')), dd(tr.get('market'))
    strategy = tr.get('strategy') or getattr(_C, 'STRATEGY', None)
    design = tr.get('design') or getattr(_C, 'DESIGN_NAME', None)
    branch = tr.get('branch') or getattr(_C, 'DEMO_BRANCH', None)
    magic = tr.get('magic') if tr.get('magic') is not None else getattr(_C, 'MAGIC', None)
    if strategy == 'turtle':
        what = f"Turtle System {g(tr, 'turtle', 'system') or getattr(_C, 'TURTLE_SYSTEM', '?')} + bot votes"
    else:
        what = 'Basket: the bot\'s RSI / MACD votes'
    fk, ftext = freshness(tr)
    chips = [chip(ftext, fk, title=f"trace written {stamp(tr.get('t'))}, poll {smart(tr.get('poll'))}")]
    stale = is_stale(tr)
    asof = as_of(d)

    def state_chip(text, kind, title=None, icon=None):
        """A chip of the bot's state: neutral, with the time of the trace, once the trace is stale (it is the last
        poll's state, not now's)."""
        if stale:
            return chip(text + asof, '', title=(title + ' · ' if title else '') + 'the last poll the bot wrote')
        return chip(text, kind, title=title, icon=icon)
    if tr:
        demo = h.get('account_ok') and str(h.get('trade_mode_name') or '').lower() == 'demo'
        if demo:
            chips.append(state_chip(f"Demo account {smart(h.get('login'))} · {h.get('margin_mode_name') or '?'}", 'pos',
                                    icon='✓', title='the bot trades only on the demo, hedging account of its credentials'))
        else:
            chips.append(state_chip(f"Account refused: {h.get('account_problem') or h.get('trade_mode_name') or 'unknown'}",
                                    'neg', icon='✗', title='the bot sends nothing until the demo account is back'))
        if h.get('connected'):
            chips.append(state_chip('Terminal connected' + (f" · {h.get('reconnects')} reconnects"
                                                            if h.get('reconnects') else ''), 'pos'))
        else:
            chips.append(state_chip(f"Terminal: {h.get('terminal_problem') or 'not connected'}", 'neg'))
        tick_t = ts(mk.get('tick_t'))
        tick_age = (_now() - tick_t) if tick_t is not None else None
        if tick_age is None or tick_age < -5:          # (the clock of this PC behind the bot's: the bot's own age)
            tick_age = num(h.get('last_tick_age_s'))
        if stale:
            chips.append(chip(f"Market: last tick {dur(tick_age)} ago" + asof, '',
                              title=f"the market was {'open' if h.get('market_live') else 'not live'} at the last poll"))
        elif h.get('market_live') is None or str(mk.get('status') or '').upper() == 'UNKNOWN':
            chips.append(chip('Market: unknown (terminal not read)', '',
                              title=f"the last quote read: {when(tick_t)}" if tick_t else None))
        elif h.get('market_live'):
            chips.append(chip(f"Market open · last tick {dur(tick_age)} ago", 'pos'))
        else:
            chips.append(chip(f"Market closed ({mk.get('status') or 'no tick'})", 'warn', title=mk.get('message') or ''))
        # errors of the last hour: the events file keeps counting when the trace stops (the bot down, its loop failing)
        logged, problem = errors_last_hour(sym)
        errs = int(logged or 0) if stale else max(int(num(h.get('errors_1h')) or 0), int(logged or 0))
        src = (('the log' if stale else 'the trace and the log') if problem is None else
               f'the trace (the events file is {problem})')
        if errs:
            chips.append(chip(f'{errs} error(s) in the last hour', 'neg', title=f'from {src}; see the Log tab, level ERROR'))
        elif stale:
            chips.append(chip('Errors in the last hour: not known' if problem is not None else
                              'No error logged in the last hour', '',
                              title=f'the events file is {problem}' if problem is not None else
                              'from the log; the bot has not written its trace since' + asof))
        else:
            chips.append(chip('No errors in the last hour', 'pos', title=f'from {src}'))
        if tr.get('stale'):
            chips.append(state_chip(f"Last poll could not read the terminal (since {when(tr.get('stale_since_utc'))})",
                                    'warn'))
    ident = html.Div(className='ident', children=[
        html.Div(className='ident-top', children=[
            html.Span(sym or '—', className='sym'),
            html.Span(what, className='what'),
        ]),
        html.Div(className='ident-sub', children=[
            html.Span(['design ', html.B(design or '—')]),
            html.Span(['branch ', html.B(branch or '—')]),
            html.Span(['magic ', html.B(smart(magic))]),
            html.Span(['strategy ', html.B(strategy or '—')]),
        ]),
    ])
    vb, vstart = acc.get('virtual_balance'), acc.get('virtual_start_balance')
    money_row = html.Div(className='money', children=[
        tile('Virtual balance', money(vb), f"start {money(vstart, dp=0)} · {acc.get('virtual_start_date') or '—'}"
             if acc.get('virtual') else 'the account balance (no virtual balance)'),
        tile('Unit · lot', f"{smart(acc.get('units'))} · {fnum(acc.get('lot'), 2)} lot",
             f"next unit at {money(acc.get('next_unit_at'), dp=0)}" if acc.get('next_unit_at') else acc.get('unit_rule')),
        tile('Open P/L (this bot)', pl(acc.get('own_open_pl')), 'floating, its magic only' + asof),
        tile('Closed P/L (this bot)', pl(acc.get('own_closed_pl')), 'since the virtual start'),
        tile('This bot\'s equity', money(acc.get('own_equity')), 'virtual balance + open P/L' + asof),
        tile('Demo account (shared)', f"{money(acc.get('balance'), dp=0)} / {money(acc.get('equity'), dp=0)}",
             'balance / equity, the slot\'s 2 bots' + asof),
        tile('Bot running', ('not writing' if stale else f"{dur(h.get('uptime_s'))}") if h.get('uptime_s') is not None
             else '—',
             (f"no trace since {when(tr.get('t'))}; it had run {dur(h.get('uptime_s'))} then" if stale else
              f"poll {smart(tr.get('poll'))} · loop {fnum(h.get('loop_ms'), 1)} ms · trace {fnum(h.get('trace_ms'), 1)} ms"
              + (f" · {smart(h.get('skipped_polls'))} skipped" if h.get('skipped_polls') else '')),
             vcls='neg' if stale else ''),
    ])
    if not tr:
        money_row = html.Div('The balance, the unit and the P/L appear here once the bot writes its trace.',
                             className='line muted')
    return [html.Div(className='status-top', children=[ident, html.Div(chips, className='chips')]), money_row]


# ───────────────────────────── what the bot is doing now ─────────────────────────────

ACTION_KIND = {
    'WAIT': 'neutral', 'MARKET_CLOSED': 'neutral', 'PAUSED': 'warn', 'BLOCKED': 'warn', 'NO_DATA': 'warn',
    'SKIPPED': 'neg', 'OPEN_FAILED': 'neg', 'ADD_FAILED': 'neg', 'BOTH_SIDES': 'warn', 'UNMANAGED': 'warn',
    'OPEN_BUY': 'accent', 'OPEN_SELL': 'accent', 'WAIT_FILL': 'accent', 'HOLD': 'accent', 'ADD_BUY': 'accent',
    'ADD_SELL': 'accent', 'CLOSE_BUY': 'accent', 'CLOSE_SELL': 'accent', 'TRACE_ERROR': 'neg',
}
ACTION_WORDS = {
    'WAIT': 'waiting for an entry', 'PAUSED': 'paused after a close', 'BLOCKED': 'an entry is blocked',
    'SKIPPED': 'this poll decided nothing', 'NO_DATA': 'not enough data', 'MARKET_CLOSED': 'the market is closed',
    'OPEN_BUY': 'opened a buy', 'OPEN_SELL': 'opened a sell', 'OPEN_FAILED': 'an entry was not filled',
    'WAIT_FILL': 'waiting for the terminal to list the fill', 'HOLD': 'holding the position',
    'ADD_BUY': 'added to the buy', 'ADD_SELL': 'added to the sell', 'ADD_FAILED': 'an add was not filled',
    'CLOSE_BUY': 'closing the buy', 'CLOSE_SELL': 'closing the sell', 'BOTH_SIDES': 'a buy and a sell are open',
    'UNMANAGED': 'positions it cannot take over', 'TRACE_ERROR': 'the trace failed on this poll (see the Log tab)',
}
_OTHER_SIDE = {'BUY': 'SELL', 'SELL': 'BUY'}


def close_sides(o):
    """(the side of the position, the side of the order) of a close: a SELL position is closed with a BUY order. A
    trace before v3.9.2-demo.5's fix had only the order's side, in `side`."""
    if 'order_side' in o:
        return o.get('side') or '?', o.get('order_side') or '?'
    order = str(o.get('side') or '').upper()
    return _OTHER_SIDE.get(order, '?'), order or '?'


def order_line(o, digits):
    ok = o.get('done')
    kind = 'pos' if ok else 'neg'
    if str(o.get('kind') or '').lower() == 'close':
        pos_side, order_side = close_sides(o)
        what = (f"CLOSE {pos_side} position {o.get('position') or '?'} ({order_side} order, "
                f"{fnum(o.get('volume'), 2)} lot)")
    else:
        what = f"{(o.get('kind') or '').upper()} {o.get('side') or ''} {fnum(o.get('volume'), 2)} lot"
        if o.get('position'):
            what += f" (position {o.get('position')})"
    res = o.get('retcode_text') or ('refused by the bot' if o.get('refused') else '—')
    return html.Div(className='order', children=[
        badge('✓ done' if ok else '✗ ' + str(res), kind),
        html.Span(what, className='order-what'),
        html.Span(f"requested {px(o.get('price'), digits)} · sl {px(o.get('sl'), digits) if num(o.get('sl')) else 'none'}"
                  f" · filled {px(o.get('result_price'), digits)} · retcode {o.get('retcode') if o.get('retcode') is not None else '—'}"
                  + (f" · {o.get('result_comment')}" if o.get('result_comment') else '')
                  + (f" · {fnum(o.get('ms'), 0)} ms" if num(o.get('ms')) else ''), className='order-det mono'),
    ])


@safe()
def now_header(d):
    tr = dd(d.get('trace'))
    dec = dd(tr.get('decision'))
    act = dec.get('action') or '—'
    digits = digits_of(d)
    chips = []
    if dec.get('reason'):
        chips.append(chip(f"reason: {dec['reason']}"))
    if dec.get('side'):
        chips.append(chip(f"side: {side_glyph(dec['side'])}"))
    if dec.get('blocked_by'):
        gate = next((x for x in dl(dec.get('gates')) if x.get('key') == dec['blocked_by']), None)
        chips.append(chip(f"decided by: {(gate or {}).get('name') or dec['blocked_by']}", 'accent'))
    sig = dd(dec.get('signal'))
    if sig:
        chips.append(chip(f"signals: buy {sig.get('buy') or '—'} · sell {sig.get('sell') or '—'}",
                          title='the strategy\'s own signals (the old dashboard\'s BUY / SELL / DO_NOTHING)'))
    orders = dl(dec.get('orders'))
    stale = is_stale(tr)
    head = html.Div(className='now-head', children=[
        html.Div(className='now-title', children=[
            html.Span('What the bot was doing at its last poll' if stale else 'What the bot is doing now',
                      className='eyebrow'),
            badge(act, 'neutral' if stale else ACTION_KIND.get(act, 'neutral')),
            html.Span(ACTION_WORDS.get(act, '') + as_of(d), className='now-words'),
        ]),
        html.Span(f"decided {when(tr.get('t'))} · poll {smart(tr.get('poll'))}", className='now-meta'),
    ])
    # the bot has stopped writing (it is down, the PC slept, or its loop fails before the trace): said first
    gone = html.Div(className='banner banner-neg', children=(
        f"The bot has not written since {when(tr.get('t'))} ({dur(trace_age(tr))} ago): is it running? Everything "
        f"below is its last poll, not now; the Log tab shows what it wrote since.")) if stale else None
    banner = None
    if tr.get('stale'):
        banner = html.Div(className='banner banner-warn', children=(
            f"This poll could not read the terminal (since {when(tr.get('stale_since_utc'))}): the account, market "
            f"and position numbers below are those of the last good poll."))
    return html.Div([
        head,
        gone,
        html.P(dec.get('headline') or 'No decision yet.', className='headline' + (' headline-old' if stale else '')),
        html.Div(chips, className='chips chips-left') if chips else None,
        banner,
        html.Div(className='orders', children=[html.Div("This poll's orders", className='mini-title')]
                 + [order_line(o, digits) for o in orders]) if orders else None,
    ])


GATE_SECTION = {
    'need': ('Conditions', 'the first one not met decides what the bot does'),
    'exit': ('Exits', 'any one that fires closes the position'),
    'add': ('Adds', 'every condition must hold for an add'),
    'info': ('For information', 'shown, not checked'),
}


def gate_icon(role, ok):
    if ok is None:
        return ('–', 'gi-na', 'does not apply')
    if role == 'exit':
        return ('⚡', 'gi-fire', 'fires') if ok else ('○', 'gi-idle', 'not hit')
    if role == 'add':
        return ('✓', 'gi-pass', 'met') if ok else ('○', 'gi-idle', 'not met yet')
    if role == 'info':
        return ('i', 'gi-na', 'information')
    return ('✓', 'gi-pass', 'passed') if ok else ('✗', 'gi-fail', 'not met: blocks')


def gate_row(gt, decides, digits):
    role = gt.get('role') or 'need'
    glyph, gcls, word = gate_icon(role, gt.get('ok'))
    checked = gt.get('checked', True) is not False
    tags = []
    if decides:
        tags.append(html.Span('decides', className='gtag gtag-accent'))
    if not checked:
        tags.append(html.Span('not reached this poll', className='gtag'))
    return html.Div(className='gate' + (' gate-decides' if decides else '') + ('' if checked else ' gate-idle'),
                    title=f'{word} — {gt.get("key")}', children=[
        html.Span(glyph, className=f'gi {gcls}'),
        html.Div(className='gate-main', children=[
            html.Div(className='gate-top', children=[
                html.Span(gt.get('name') or gt.get('key') or '?', className='gate-name'),
                *tags,
                html.Span(smart(gt.get('value'), digits), className='gate-val mono'),
            ]),
            html.Div(gt.get('need'), className='gate-need') if gt.get('need') else None,
            html.Div(gt.get('note'), className='gate-note') if gt.get('note') else None,
        ]),
    ])


@safe()
def gates_view(d):
    tr = dd(d.get('trace'))
    dec = dd(tr.get('decision'))
    gates = dl(dec.get('gates'))
    digits = digits_of(d)
    if not gates:
        return card('Checks', empty('No checks in the trace yet.'))
    rows, last = [], None
    for gt in gates:
        role = gt.get('role') or 'need'
        if role != last:
            title, sub = GATE_SECTION.get(role, (role, ''))
            rows.append(html.Div(className='gsec', children=[html.Span(title), html.Span(sub, className='gsec-sub')]))
            last = role
        rows.append(gate_row(gt, gt.get('key') == dec.get('blocked_by'), digits))
    legend = html.Div(className='glegend', children=[
        html.Span([html.B('✓', className='gi-pass'), ' passed / met']),
        html.Span([html.B('✗', className='gi-fail'), ' blocks']),
        html.Span([html.B('⚡', className='gi-fire'), ' fires']),
        html.Span([html.B('○', className='gi-idle'), ' not yet']),
        html.Span([html.B('–', className='gi-na'), ' does not apply']),
        html.Span([html.B('▌', className='gi-fire'), ' decided this poll']),
    ])
    this = f"its last poll{as_of(d)}" if is_stale(tr) else 'this poll'
    return card('The bot\'s checks', html.Div(rows, className='gates'),
                sub=html.Div([html.Div(f'{len(gates)} checks {this}, in the order the bot makes them'), legend]))


# ── the basket strategy ──

TF_ORDER = ('D1', 'H6', 'H4', 'H1', 'M30', 'M15', 'M5', 'M1')


def _spark(series, pivot_ago=None, pivot=None, bands=(), zero=False, height=86, extra=None):
    """A small line chart of an indicator's last values: the latest pivot (accent dot), the slope from it to the
    current value (accent dashes), the current value (white dot), reference lines (RSI bands / MACD zero)."""
    ys = [num(v) for v in lst(series)]
    if not any(v is not None for v in ys):
        return html.Div('no series', className='spark-empty')
    n = len(ys)
    xs = list(range(n))
    fig = go.Figure()
    for b in (bands if isinstance(bands, (list, tuple)) else ()):
        if num(b) is not None:
            fig.add_hline(y=float(b), line_color=COL['line'], line_width=1)
    if zero:
        fig.add_hline(y=0, line_color=COL['line'], line_width=1)
    if lst(extra):
        fig.add_trace(go.Scatter(x=xs, y=[num(v) for v in lst(extra)], mode='lines', hoverinfo='skip',
                                 line=dict(color=COL['faint'], width=1)))
    fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', hoverinfo='skip', line=dict(color=COL['text2'], width=1.6)))
    last = ys[-1]
    ago = num(pivot_ago)
    if ago is not None and num(pivot) is not None and 0 <= n - 1 - int(ago) < n and last is not None:
        xi = n - 1 - int(ago)
        fig.add_trace(go.Scatter(x=[xi, n - 1], y=[float(pivot), last], mode='lines', hoverinfo='skip',
                                 line=dict(color=COL['accent'], width=1.6, dash='dash')))
        fig.add_trace(go.Scatter(x=[xi], y=[float(pivot)], mode='markers', hoverinfo='skip',
                                 marker=dict(size=8, color=COL['accent'], line=dict(color=COL['surface'], width=2))))
    if last is not None:
        fig.add_trace(go.Scatter(x=[n - 1], y=[last], mode='markers', hoverinfo='skip',
                                 marker=dict(size=7, color=COL['text'], line=dict(color=COL['surface'], width=2))))
    fig.update_layout(height=height, margin=dict(l=34, r=6, t=4, b=4), showlegend=False,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(family=FONT, size=9, color=COL['muted']))
    fig.update_xaxes(visible=False, range=[-0.5, n - 0.5])
    fig.update_yaxes(showgrid=False, zeroline=False, nticks=3, tickfont=dict(size=9, color=COL['muted']))
    return dcc.Graph(figure=fig, config={'displayModeBar': False, 'staticPlot': True}, className='spark',
                     style={'height': f'{height}px'})


def _part_text(p, kind):
    """One indicator's vote in words: 'pivot high 64.62, 11 bars ago, slope +0.687/bar'."""
    if not isinstance(p, dict):
        return '—'
    if p.get('pivot') is None:
        return 'no qualifying pivot in the window'
    return (f"pivot {p.get('pivot_side') or '?'} {smart(p.get('pivot'))}, {smart(p.get('bars_ago'))} bars ago, "
            f"slope {fnum(p.get('slope'), 4 if kind == 'rsi' else 6, signed=True)}/bar")


def score_block(label, score, thr, rng, weights, wants_text, sub=None):
    """A score against its thresholds: the track from -range to +range, the no-side band between -thr and +thr."""
    s, t, r = num(score), num(thr), num(rng)
    r = r if r and r > 0 else max(1.0, abs(s or 0), abs(t or 0))
    marks = []
    if t is not None:
        if t > 0:
            marks = [(-t, f'SELL ≤ -{smart(t)}', 'mk-sell'), (t, f'BUY ≥ +{smart(t)}', 'mk-buy')]
        else:
            marks = [(0, 'any side ≥ 0 / ≤ 0', 'mk-zero')]
    return html.Div(className='score', children=[
        html.Div(className='score-head', children=[
            html.Span(label, className='score-label'),
            html.Span(weights, className='score-w'),
            html.Span(signed(s), className='score-v'),
        ]),
        meter(-r, r, s, marks=marks, bands=[(-t, t, 'band-none')] if t else [],
              lo_label=f'-{smart(r)}', hi_label=f'+{smart(r)}'),
        html.Div(wants_text, className='score-sub'),
        html.Div(sub, className='score-sub muted') if sub else None,
    ])


def _weights_text(w):
    return ' + '.join(f'{smart(v)}×{k}' for k, v in dd(w).items()) or '—'


def basket_panel(d):
    tr = dd(d.get('trace'))
    bk = dd(tr.get('basket'))
    digits = digits_of(d)
    if not bk:
        return card('The basket strategy', empty('No basket data in the trace.'))
    ow, aw = g(bk, 'weights', 'open') or OPEN_SCORE_WEIGHTS, g(bk, 'weights', 'agreement') or FORCE_CLOSE_SCORE_WEIGHTS
    entry_s = bk.get('entry_s') if bk.get('entry_s') is not None else ENTRY_S
    agree_s = bk.get('entry_agree_s') if bk.get('entry_agree_s') is not None else ENTRY_AGREE_S
    os_, fc = num(bk.get('open_score')), num(bk.get('fc_score'))
    if os_ is None:
        wants = 'no score this poll'
    elif num(entry_s) is not None and os_ >= num(entry_s):
        wants = f'wants a BUY (≥ +{smart(entry_s)})'
    elif num(entry_s) is not None and os_ <= -num(entry_s):
        wants = f'wants a SELL (≤ -{smart(entry_s)})'
    else:
        wants = f'no side: between -{smart(entry_s)} and +{smart(entry_s)}'
    ag = num(agree_s) or 0
    if fc is None:
        agree = 'no score this poll'
    elif ag > 0:
        agree = (f'lets a BUY in (≥ +{smart(ag)})' if fc >= ag else f'lets a SELL in (≤ -{smart(ag)})' if fc <= -ag
                 else f'lets neither side in (between -{smart(ag)} and +{smart(ag)})')
    else:
        agree = 'not against a BUY or a SELL' if fc == 0 else ('lets only a BUY in' if fc > 0 else 'lets only a SELL in')
    fc_on = bk.get('force_close_enabled')
    fc_sub = (f"force-close ON: a basket closes when this score is {smart(bk.get('force_close_s') or FORCE_CLOSE_S)} or "
              f"more against it" if fc_on else 'force-close is off in this design: these votes only gate entries')
    scores = html.Div(className='scores', children=[
        score_block('Open score', os_, entry_s, bk.get('open_range'), _weights_text(ow), wants),
        score_block('Agreement score', fc, agree_s, bk.get('fc_range'), _weights_text(aw), agree, fc_sub),
    ])
    votes = dd(bk.get('votes'))
    order = [tf for tf in TF_ORDER if tf in votes] + [tf for tf in votes if tf not in TF_ORDER]
    rows, sparks = [], []
    for tf in order:
        v = dd(votes.get(tf))
        r, m = dd(v.get('rsi')), dd(v.get('macd'))
        roles = ' · '.join(str(x) for x in lst(v.get('roles'))) or '—'
        contrib = []
        if v.get('open_weight') is not None:
            contrib.append(f"open {signed(v.get('open_contrib'))}"
                           + (f" (grey {v['grey_filled']} filled)" if v.get('grey_filled') else ''))
        if v.get('fc_weight') is not None:
            contrib.append(f"agreement {signed(v.get('fc_contrib'))}")
        rows.append([html.Div([html.B(tf), html.Div(roles, className='tf-roles')]), vote_glyph(r.get('vote')),
                     smart(r.get('now')), _part_text(r, 'rsi'), vote_glyph(m.get('vote')), smart(m.get('now')),
                     _part_text(m, 'macd'), ' · '.join(contrib) or '—'])
        sparks.append(html.Div(className='spark-pair', children=[
            html.Div([html.Div(f'{tf} RSI {smart(r.get("now"))} · vote {vote_glyph(r.get("vote"))}', className='spark-t'),
                      _spark(r.get('series'), r.get('bars_ago'), r.get('pivot'), bands=r.get('bands') or ())]),
            html.Div([html.Div(f'{tf} MACD hist {smart(m.get("now"))} · vote {vote_glyph(m.get("vote"))} · pivots: '
                               f'{m.get("side_rule") or "?"}s', className='spark-t'),
                      _spark(m.get('series'), m.get('bars_ago'), m.get('pivot'), zero=True)]),
        ]))
    votes_box = html.Div([
        html.Div(className='mini-title', children=['Votes per timeframe ',
                                                   html.Span('(the forming bar; +1 / -1 when the slope from the latest '
                                                             'pivot points that way)', className='muted')]),
        table(['TF · role', 'RSI', 'RSI now', 'RSI pivot → slope', 'MACD', 'hist now', 'MACD pivot → slope',
               'adds to the scores'], rows, cls='tbl-votes') if rows else empty('No votes this poll.'),
        html.Div(sparks, className='sparks') if sparks else None,
        html.Div(className='spark-legend', children=[
            html.Span([html.I(className='lk lk-line'), 'indicator']),
            html.Span([html.I(className='lk lk-dot-accent'), 'latest pivot']),
            html.Span([html.I(className='lk lk-dash-accent'), 'slope pivot → now']),
            html.Span([html.I(className='lk lk-dot-white'), 'now (forming bar)']),
        ]) if sparks else None,
    ])
    tiles = html.Div(className='tiles3', children=[_trend_tile(bk), _vol_tile(bk, digits), _pause_tile(bk)])
    # fresh = the poll computed the votes; a skipped poll (stale) or a trace the bot no longer writes keeps old ones
    if is_stale(tr):
        votes_when = f"votes of its last poll{as_of(d)}"
    elif bk.get('fresh') and not tr.get('stale'):
        votes_when = 'votes fresh this poll'
    else:
        votes_when = 'votes kept from the last poll'
    return card('The basket strategy, ' + ('its last poll' if is_stale(tr) else 'this poll'),
                html.Div([scores, votes_box, tiles, _new_basket(bk, digits), _rsi_row(bk)]),
                sub=f"design levers as the bot runs them · {votes_when}")


def _trend_tile(bk):
    t = dd(bk.get('trend'))
    if not t.get('on'):
        return tile('Trend gate', 'off', 'TREND_TF = None: no trend filter in this design')
    word = {'up': '▲ up: buys only', 'down': '▼ down: sells only'}.get(t.get('text'), '– flat: neither side')
    return tile(f"{t.get('tf') or '?'} trend", word,
                f"MACD signal {smart(t.get('signal'))} on the closed bar of {when(t.get('bar_utc') or t.get('bar_t'), seconds=False)}"
                + (f" · {t.get('rule')}" if t.get('rule') else ''), cls='tile-wide')


def _vol_tile(bk, digits):
    v = dd(bk.get('vol'))
    if not v.get('on'):
        return tile('Volatility unit', 'off', 'VOL_TF = None: target / stop in $ per unit')
    cap = (f" · cap {money(v.get('cap_usd_per_unit'))}/unit" + (' (binds)' if v.get('cap_binds') else '')) \
        if num(v.get('cap_usd_per_unit')) else ' · no cap'
    known = v.get('known')
    return tile(f"{v.get('tf') or '?'} volatility unit",
                smart(v.get('capped') if v.get('capped') is not None else v.get('raw'), None) if known else 'not known yet',
                f"raw {smart(v.get('raw'))}{cap} · {smart(v.get('bars_used'))} closed bars (needs {smart(v.get('min_bars'))})"
                f" · = {money(v.get('usd_per_unit'))} per unit", cls='tile-wide')


def _pause_tile(bk):
    p = dd(bk.get('pause'))
    lc = dd(p.get('last_close'))
    last = (f"last close {when(lc.get('utc') or lc.get('t'))}: {lc.get('side') or ''} {lc.get('reason') or ''} "
            f"{money(lc.get('pnl'), signed=True)}") if lc else 'no close yet'
    if p.get('active'):
        return tile('Entry pause', countdown(p.get('left_s')) + ' left',
                    f"until {when(p.get('until_utc') or p.get('until'))} ({p.get('why') or ''}, {dur(p.get('length_s'))}) · {last}",
                    cls='tile-wide tile-warn')
    return tile('Entry pause', 'none', f"{dur(p.get('pause_s'))} after a close, {dur(p.get('loss_pause_s'))} after a loss · {last}",
                cls='tile-wide')


def _new_basket(bk, digits):
    nb = dd(bk.get('new_basket'))
    if not nb:
        return None
    rows = []
    for side in ('buy', 'sell'):
        s = dd(nb.get(side))
        rows.append([side_glyph(side), px(s.get('entry'), digits), px(s.get('target'), digits), px(s.get('stop'), digits),
                     px(s.get('backstop'), digits), s.get('judged_on') or '—'])
    parts = [f"{smart(nb.get('units'))} unit = {fnum(nb.get('lots'), 2)} lot"]
    if nb.get('target_usd') is not None:
        parts.append(f"target {money(nb.get('target_usd'), signed=True)} ({smart(nb.get('target_px'))} price)")
    else:
        parts.append('no target')
    if nb.get('stop_usd') is not None:
        parts.append(f"stop -{money(nb.get('stop_usd'))} ({smart(nb.get('stop_px'))} price)")
    else:
        parts.append('no stop')
    if nb.get('gap_px') is not None:
        parts.append(f"add gap {smart(nb.get('gap_px'))}")
    if nb.get('backstop_px') is not None:
        parts.append(f"broker backstop {smart(nb.get('backstop_px'))} beyond the entry")
    return html.Div([
        html.Div(className='mini-title', children=['A basket opened now would get ',
                                                   html.Span('(fixed at the open for its life)', className='muted')]),
        html.Div(' · '.join(parts), className='line'),
        table(['side', 'entry', 'target', 'stop', 'backstop', 'P/L judged on'], rows, num_cols=(1, 2, 3, 4)),
    ])


def _rsi_row(bk):
    r = dd(bk.get('rsi'))
    if not r:
        return None
    order = [tf for tf in TF_ORDER[::-1] if tf in r] + [tf for tf in r if tf not in TF_ORDER]
    return html.Div(className='rsi-row', children=[html.Span('RSI by timeframe', className='mini-title')]
                    + [chip(f'{tf} {smart(r.get(tf))}') for tf in order])


# ── the Turtle ──

def turtle_panel(d):
    tr = dd(d.get('trace'))
    tt = dd(tr.get('turtle'))
    digits = digits_of(d)
    if not tt:
        return card('The Turtle', empty('No Turtle data in the trace.'))
    lv = dd(tt.get('levels'))
    orders = dd(tt.get('orders'))
    n = num(tt.get('n')) or num(lv.get('n'))
    parts = [_orders_box(tt, lv, orders, n, digits),
             html.Div(className='tiles4', children=[
                 tile('N (20-day ATR)', smart(n, 2) if n else '—',
                      f"{fnum(lv.get('n_pct'), 2)}% of the price · from the D1 bar of {(lv.get('bar_utc') or '')[:10] or '—'}"),
                 tile('Stop distance 2N', smart(lv.get('stop_dist'), 2), 'a new trade\'s stop from its fill'),
                 tile('Add step 0.5N', smart(lv.get('add_step'), 2), f"up to {smart(g(tt, 'params', 'max_legs'))} legs"),
                 _exit_tile(tt, lv, digits),
             ]),
             _vote_box(tt),
             _channels_box(tt, digits),
             _filter_box(tt, digits),
             _new_trade_box(tt, digits)]
    return card('The Turtle, ' + (f'its last poll{as_of(d)}' if is_stale(tr) else 'this poll'), html.Div(parts),
                sub=tt.get('rules') or f"System {tt.get('system')}")


def _exit_tile(tt, lv, digits):
    days = smart(g(tt, 'channels', 'exit', 'days'))
    if str(g(tt, 'trade', 'side') or '').upper() == 'SELL':
        return tile(f'Exit channel ({days}-day high)', px(lv.get('trail_short'), digits),
                    f"a short's stop moves down to it · the low {px(lv.get('trail_long'), digits)} is a long's")
    return tile(f'Exit channel ({days}-day low)', px(lv.get('trail_long'), digits),
                f"a long's stop moves up to it · the high {px(lv.get('trail_short'), digits)} is a short's")


def _orders_box(tt, lv, orders, n, digits):
    state = orders.get('state') or ('armed' if orders.get('armed') else 'none')
    b, s = dd(orders.get('buy')), dd(orders.get('sell'))
    if state == 'armed':
        st = badge('ARMED', 'accent')
        txt = f"until the next D1 close {when(orders.get('until_utc') or orders.get('until_t'))}"
    elif state == 'used':
        st = badge('USED', 'neutral')
        txt = (f"by the {orders.get('used_by') or ''} trade of {when(orders.get('used_utc') or orders.get('used_t'))}; "
               f"new orders at the next D1 close {when(orders.get('until_utc') or orders.get('until_t'))}")
    else:
        st = badge('NONE', 'warn')
        txt = 'no daily levels: no orders'
    lo, hi = num(s.get('level')), num(b.get('level'))
    bid_now, ask_now = num(s.get('price_now')), num(b.get('price_now'))

    def gap(o, quote, name):
        dist, dn = num(o.get('distance')), num(o.get('distance_n'))
        if dist is None:
            return f'{name} {px(quote, digits)}'
        how = 'away' if dist > 0 else 'beyond it'
        return f"{name} {px(quote, digits)}: {smart(abs(dist), digits)} {how} ({fnum(abs(dn) if dn is not None else None, 2)} N)"
    gauge = None
    if lo is not None and hi is not None and hi > lo:
        mid = None
        if bid_now is not None and ask_now is not None:
            mid = (bid_now + ask_now) / 2.0
        span = hi - lo
        gauge = meter(lo - span * 0.04, hi + span * 0.04, mid, marks=[(lo, 'SELL level', 'mk-sell'), (hi, 'BUY level', 'mk-buy')],
                      lo_label=f"sell at ≤ {px(lo, digits)} · " + gap(s, bid_now, 'bid'),
                      hi_label=f"buy at ≥ {px(hi, digits)} · " + gap(b, ask_now, 'ask'))
    extra = []
    in_trade = isinstance(tt.get('trade'), dict) and bool(tt.get('trade'))
    for side, o in (('buy', b), ('sell', s)):
        if not o.get('reached'):
            continue
        if state == 'armed' and not in_trade:      # an entry trigger: it waits for the vote
            extra.append(chip(f"{side.upper()} level reached ({o.get('judged_on')} {px(o.get('price_now'), digits)}); "
                              f"needs the M15 vote {vote_glyph(o.get('vote_needed'))}", 'accent'))
        else:                                      # not a trigger now: say why
            why = 'a trade is open' if in_trade else ("today's orders are used" if state == 'used' else 'no orders')
            extra.append(chip(f"{side.upper()} level passed ({o.get('judged_on')} {px(o.get('price_now'), digits)}): "
                              f"no entry, {why}"))
    if orders.get('in_exit_bar'):
        extra.append(chip('in the M1 bar of the last exit: no entry this minute', 'warn'))
    if orders.get('last_exit_utc'):
        extra.append(chip(f"last exit {when(orders.get('last_exit_utc'))}"))
    return html.Div(className='box', children=[
        html.Div(className='box-head', children=[html.Span("Today's entry orders", className='mini-title'), st,
                                                  html.Span(txt, className='muted')]),
        gauge,
        html.Div(className='line muted', children=(
            f"BUY level = the {g(tt, 'channels', 'entry', 'days') or '?'}-day high {px(g(tt, 'channels', 'entry', 'high'), digits)} + "
            f"{smart(g(tt, 'params', 'tick'))} ({b.get('channel') or '—'}), SELL level = the low {px(g(tt, 'channels', 'entry', 'low'), digits)} "
            f"- {smart(g(tt, 'params', 'tick'))}; one entry per D1 bar")),
        html.Div(extra, className='chips chips-left') if extra else None,
    ])


def _vote_box(tt):
    v = dd(tt.get('vote'))
    if not v:
        return None
    r, m = dd(v.get('rsi')), dd(v.get('macd'))
    val = v.get('value')
    allows = v.get('allows')
    head = html.Div(className='box-head', children=[
        html.Span(f"{v.get('tf') or 'M15'} vote of the last closed bar", className='mini-title'),
        badge(vote_glyph(val) if val is not None else 'unknown', 'accent' if val in (1, -1) else 'neutral'),
        html.Span((f"allows a {allows}" if allows else 'allows neither side') +
                  f" · bar {when(v.get('bar_utc') or v.get('bar_t'), seconds=False)}–{when(v.get('bar_close_utc') or v.get('bar_close_t'), seconds=False)}"
                  f" · next read {when(v.get('next_read_utc') or v.get('next_read_t'))}"
                  f" · {smart(v.get('bars'))} closed bars", className='muted'),
    ])
    rows = [
        ['RSI', vote_glyph(r.get('vote')), smart(r.get('now')), _part_text(r, 'rsi'),
         f"highs count ≥ {smart(r.get('ob'))}, lows ≤ {smart(r.get('os'))}"],
        ['MACD hist', vote_glyph(m.get('vote')), smart(m.get('now')), _part_text(m, 'macd'),
         f"line {smart(m.get('line'))}, signal {smart(m.get('signal'))}: {m.get('side_rule') or '?'} pivots count"],
    ]
    sparks = html.Div(className='spark-pair', children=[
        html.Div([html.Div(f"RSI {smart(r.get('now'))}", className='spark-t'),
                  _spark(r.get('series'), r.get('bars_ago'), r.get('pivot'), bands=[r.get('os'), r.get('ob')])]),
        html.Div([html.Div(f"MACD histogram {smart(m.get('now'))} (grey: the signal line)", className='spark-t'),
                  _spark(m.get('series'), m.get('bars_ago'), m.get('pivot'), zero=True, extra=m.get('signal_series'))]),
    ])
    return html.Div(className='box', children=[
        head,
        table(['part', 'vote', 'now', 'latest pivot → slope', 'rule'], rows),
        sparks,
        html.Div(v.get('rule'), className='line muted') if v.get('rule') else None,
    ])


def _channels_box(tt, digits):
    ch = dd(tt.get('channels'))
    allc = dd(ch.get('all'))
    rows = []
    for days in ('10', '20', '55'):
        c = dd(allc.get(days) or allc.get(int(days)))
        if not c:
            continue
        rows.append([f'{days}-day', px(c.get('high'), digits), (c.get('high_utc') or '')[:10] or '—',
                     px(c.get('low'), digits), (c.get('low_utc') or '')[:10] or '—'])
    bar = dd(ch.get('bar'))
    d1 = dd(tt.get('d1'))
    d1_line = (f"{smart(d1.get('bars'))} closed D1 bars used (asked {smart(d1.get('asked'))}, needs {smart(d1.get('min_bars'))})"
               f" · last D1 bar {(d1.get('last_bar_utc') or '')[:10] or '—'} · next D1 close {when(d1.get('next_close_utc') or d1.get('next_close_t'))}"
               + (f" (in {dur((ts(d1.get('next_close_t') or d1.get('next_close_utc')) or 0) - _now())})"
                  if ts(d1.get('next_close_t') or d1.get('next_close_utc')) else ''))
    kids = [html.Div(className='box-head', children=[html.Span('The D1 channels', className='mini-title'),
                                                    html.Span(d1_line, className='muted')])]
    if d1.get('stale'):
        kids.append(html.Div('The D1 bar that closed at 00:00 UTC is not there yet: the bot goes on with the levels and '
                             'the stop of the bar before and asks again every poll.', className='banner banner-warn'))
    if rows:
        kids.append(table(['channel', 'high', 'made on', 'low', 'made on'], rows, num_cols=(1, 3)))
    if bar:
        kids.append(html.Div(className='line', children=(
            f"Last closed D1 bar {(bar.get('utc') or '')[:10]}: O {px(bar.get('o'), digits)} · H {px(bar.get('h'), digits)} · "
            f"L {px(bar.get('l'), digits)} · C {px(bar.get('c'), digits)} · true range {smart(bar.get('true_range'), 2)}")))
    for key in ('entry', 'exit'):
        rule = g(ch, key, 'rule')
        if rule:
            kids.append(html.Div(rule, className='line muted'))
    return html.Div(kids, className='box')


def _filter_box(tt, digits):
    f = tt.get('filter')
    if not isinstance(f, dict):
        return None
    hyp = dd(f.get('hypothetical'))
    rows = [[side_glyph(x.get('side')), (x.get('entry_utc') or '')[:10], px(x.get('entry'), digits),
             (x.get('exit_utc') or '')[:10], px(x.get('exit'), digits), 'win' if x.get('win') else 'loss']
            for x in dl(hyp.get('trades'))]
    return html.Div(className='box', children=[
        html.Div(className='box-head', children=[
            html.Span("System 1's filter", className='mini-title'),
            badge('20-day breakouts' if f.get('use20') else '55-day failsafe', 'accent' if f.get('use20') else 'neutral'),
            html.Span(f"levels from the {f.get('levels_from') or '?'} channel · the filter's own trade: "
                      f"{hyp.get('state') or 'flat'} · last one {'won' if hyp.get('last_win') else 'lost or none'}",
                      className='muted')]),
        table(['side', 'entry day', 'entry', 'exit day', 'exit', 'result'], rows, num_cols=(2, 4)) if rows else None,
        html.Div(f.get('rule'), className='line muted') if f.get('rule') else None,
    ])


def _new_trade_box(tt, digits):
    nt = tt.get('new_trade')
    if not isinstance(nt, dict):
        return None
    rows = []
    for side in ('buy', 'sell'):
        s = dd(nt.get(side))
        rows.append([side_glyph(side), f"{px(s.get('entry'), digits)} ({s.get('at') or '?'})",
                     f"{px(s.get('stop'), digits)} ({s.get('stop_origin') or '?'})", px(s.get('next_add'), digits),
                     px(s.get('backstop'), digits), pl(s.get('pnl_at_stop'))])
    return html.Div(className='box', children=[
        html.Div(className='box-head', children=[
            html.Span('A trade opened now would get', className='mini-title'),
            html.Span(f"{smart(nt.get('units'))} unit = {fnum(nt.get('lots'), 2)} lot a leg · N {smart(nt.get('n'), 2)} frozen · "
                      f"stop 2N {smart(nt.get('stop_dist'), 2)} · add every {smart(nt.get('add_step'), 2)} · "
                      f"{smart(nt.get('max_legs'))} legs at most · balance {money(nt.get('balance'))}", className='muted')]),
        table(['side', 'entry', 'stop', 'first add', 'broker backstop', 'P/L at the stop (1 leg)'], rows,
              num_cols=(1, 2, 3, 4, 5)),
    ])


@safe()
def strategy_panel(d):
    tr = dd(d.get('trace'))
    if tr.get('strategy') == 'turtle' or (tr.get('turtle') and not tr.get('basket')):
        return turtle_panel(d)
    return basket_panel(d)


# ───────────────────────────── the open position ─────────────────────────────

def legs_table(legs, digits, turtle=False):
    rows = []
    for i, lg in enumerate(dl(legs)):
        rows.append([smart(lg.get('n') or i + 1), smart(lg.get('ticket') or lg.get('id')), when(lg.get('open_utc') or lg.get('open_t')),
                     px(lg.get('price'), digits), fnum(lg.get('lots'), 2), pl(lg.get('profit')), money(lg.get('swap')),
                     px(lg.get('backstop'), digits) if num(lg.get('backstop')) else 'none',
                     '✓' if lg.get('listed', True) else 'not listed yet'])
    return table(['leg', 'ticket', 'opened', 'price', 'lots', 'P/L', 'swap', 'broker sl (backstop)', 'listed'], rows,
                 num_cols=(3, 4, 5, 6, 7))


@safe()
def position_view(d):
    tr = dd(d.get('trace'))
    digits = digits_of(d)
    if (tr.get('strategy') or getattr(_C, 'STRATEGY', 'basket')) == 'turtle' or tr.get('turtle'):
        return _turtle_position(d, dd(tr.get('turtle')), digits)
    return _basket_position(d, g(tr, 'basket', 'open'), digits)


def trades_note(d, what='the closed trades below'):
    """None, or what is wrong with <SYMBOL>_trades.json: missing / unreadable (the closed trades are not known), or
    old (the bot has not read the deal history for a while: `what` is as of then)."""
    name = f"{d.get('symbol') or '<SYMBOL>'}_trades.json"
    if d.get('trades') is None:
        return (f"{name} is {d.get('trades_problem') or 'missing'}: the closed trades are not known here (the bot writes "
                f"it at its first deal-history read after a start, then at least every minute)")
    t = ts(g(d, 'trades', 't'))
    age = None if t is None else _now() - t
    if age is not None and age > TRADES_STALE_S:
        return (f"{name} was last written {when(t)} ({dur(age)} ago): {what} are as of then (the bot reads the deal "
                f"history every minute; it is not running, or the terminal gives no history)")
    return None


def _last_closed_line(d, digits):
    closed = dl(g(d, 'trades', 'closed'))
    if d.get('trades') is None:
        return f"The last closed trade is not known: {trades_note(d)}."
    if not closed:
        return 'No closed trade yet.'
    c = closed[-1]
    return (f"Last trade: {side_glyph(c.get('side'))} {smart(len(lst(c.get('legs'))))} leg(s), {fnum(c.get('lots'), 2)} lot, "
            f"opened {when(c.get('open_utc') or c.get('open_t'))} at {px(c.get('open_price'), digits)}, closed "
            f"{when(c.get('close_utc') or c.get('close_t'))} at {px(c.get('close_price'), digits)} "
            f"({c.get('exit_reason_text') or c.get('exit_reason') or '?'}): {money(c.get('pnl'), signed=True)}, "
            f"{dur(_now() - (ts(c.get('close_t') or c.get('close_utc')) or _now()))} ago.")


def _basket_position(d, op, digits):
    if not isinstance(op, dict):
        return card('Open position', html.Div([html.Div('Flat: no basket open' + (as_of(d) or '.'), className='flat'),
                                               html.Div(_last_closed_line(d, digits), className='line muted')]))
    side = op.get('side')
    pnl = num(op.get('pnl'))
    stop_usd, tgt_usd = num(op.get('stop_usd')), num(op.get('target_usd'))
    lo = -stop_usd if stop_usd else min(-1.0, (pnl or 0) * 1.5)
    hi = tgt_usd if tgt_usd else max(1.0, (pnl or 0) * 1.5)
    gauge = meter(lo * 1.08, hi * 1.08, pnl, marks=[(lo, 'STOP' if stop_usd else '', 'mk-sell'), (0, '0', 'mk-zero'),
                                                     (hi, 'TARGET' if tgt_usd else '', 'mk-buy')],
                  bands=[(lo * 1.08, lo, 'band-neg'), (hi, hi * 1.08, 'band-pos')],
                  lo_label=(f"stop -{money(stop_usd)} at {op.get('judged_on') or ''} {px(op.get('stop_price'), digits)} · "
                            f"{money(op.get('to_stop_usd'))} away") if stop_usd else 'no stop',
                  hi_label=(f"target +{money(tgt_usd)} at {op.get('judged_on') or ''} {px(op.get('target_price'), digits)} · "
                            f"{money(op.get('to_target_usd'))} to go") if tgt_usd else 'no target',
                  kind='pos' if (pnl or 0) > 0 else 'neg' if (pnl or 0) < 0 else 'accent')
    ld = dd(op.get('ladder'))
    if ld.get('on') is False or not ld:
        ladder = ld.get('note') or 'no ladder in this design'
    elif ld.get('exhausted'):
        ladder = f"all adds made ({smart(ld.get('count'))} legs)"
    else:
        ladder = (f"next add: leg {smart((num(ld.get('count')) or 0) + 1)} on a {ld.get('tier_tf') or '?'} {ld.get('trigger') or ''}"
                  f" ({'armed' if ld.get('armed') else 'not armed yet'}), {ld.get('judged_on') or ''} at "
                  f"{px(ld.get('next_add_price'), digits)} or better (now {px(ld.get('price_now'), digits)}), "
                  f"{fnum(ld.get('next_add_lots'), 2)} lot")
    flags = []
    for key, text, kind in (('levels_pending', 'levels pending', 'warn'), ('close_pending', 'close pending', 'warn'),
                            ('closing', 'closing this poll', 'accent'), ('known_to_bot', None, None)):
        if key == 'known_to_bot':
            if op.get('known_to_bot') is False:
                flags.append(chip('taken over from the terminal (no state file)', 'warn'))
        elif op.get(key):
            flags.append(chip(text, kind))
    info = html.Div(className='kvs', children=[
        kv('Average price', px(op.get('avg_price'), digits)),
        kv(f"Price now ({op.get('judged_on') or '?'})", px(op.get('price_now'), digits)),
        kv('Stop', f"{px(op.get('stop_price'), digits)} (-{money(stop_usd)})" if stop_usd else 'none'),
        kv('Target', f"{px(op.get('target_price'), digits)} (+{money(tgt_usd)})" if tgt_usd else 'none'),
        kv('Broker backstops', ', '.join(px(x, digits) for x in lst(op.get('backstop_prices'))) or 'none'),
        kv('Volatility unit', f"{smart(op.get('vol_unit'))} ({op.get('vol_source') or '?'})"),
        kv('Add gap', smart(op.get('gap_px'))),
        kv('Opened', f"{when(op.get('opened_utc') or op.get('opened_at'))} by {op.get('opened_by') or '?'} · {dur(op.get('age_s'))} ago"),
    ])
    body = html.Div([
        html.Div(className='pos-head', children=[
            badge(side_glyph(side), 'accent'),
            html.Span(f"{smart(len(dl(op.get('legs'))))} leg(s) · {fnum(op.get('lots'), 2)} lot · unit {smart(op.get('units'))}",
                      className='pos-what'),
            html.Span(money(pnl, signed=True), className=f'pos-pl {pl_class(pnl)}'),
            *flags,
        ]),
        gauge,
        html.Div(ladder, className='line'),
        info,
        legs_table(op.get('legs'), digits),
    ])
    return card('Open basket' + as_of(d), body, sub='its stop, target and add gap were fixed when it opened'
                + (' · the bot has not written since: the P/L and the legs are those of its last poll' if as_of(d) else ''))


def _turtle_position(d, tt, digits):
    trd = tt.get('trade')
    if not isinstance(trd, dict):
        return card('Open position', html.Div([html.Div('Flat: no Turtle trade open' + (as_of(d) or '.'), className='flat'),
                                               html.Div(_last_closed_line(d, digits), className='line muted')]))
    if trd.get('both_sides'):
        return card('Open position', html.Div('A buy and a sell of this bot are open: it holds still (BOTH_SIDES).',
                                               className='banner banner-warn'))
    side = trd.get('side')
    pnl = num(trd.get('pnl'))
    stop, nxt, now_px = num(trd.get('stop')), num(trd.get('next_add')), num(trd.get('price_now'))
    long_ = str(side).upper() == 'BUY'
    gauge = None
    if stop is not None and now_px is not None:
        far = nxt if nxt is not None else (now_px + (now_px - stop) * 0.3)
        lo, hi = (stop, far) if long_ else (far, stop)
        span = (hi - lo) or 1.0
        marks = [(stop, 'STOP', 'mk-sell')]
        if nxt is not None:
            marks.append((nxt, 'NEXT ADD', 'mk-accent'))
        for lg in dl(trd.get('legs')):
            if num(lg.get('price')) is not None:
                marks.append((lg['price'], '', 'mk-leg'))
        stop_txt = (f"stop {px(stop, digits)} ({trd.get('stop_text') or trd.get('stop_origin') or ''}) · "
                    f"{smart(trd.get('to_stop'), digits)} away · P/L there {money(trd.get('pnl_at_stop'), signed=True)}")
        add_txt = (f"next add {px(nxt, digits)} at {trd.get('next_add_judged_on') or 'ask'} · "
                   f"{smart(trd.get('to_next_add'), digits)} to go") if nxt is not None else 'the trade is full: no more adds'
        gauge = meter(lo - span * 0.04, hi + span * 0.04, now_px, marks=marks,
                      lo_label=stop_txt if long_ else add_txt, hi_label=add_txt if long_ else stop_txt,
                      kind='pos' if (pnl or 0) > 0 else 'neg' if (pnl or 0) < 0 else 'accent')
    info = html.Div(className='kvs', children=[
        kv('Entry level', px(trd.get('entry_level'), digits), title=f"the levels of the D1 bar of {(trd.get('entry_d1_utc') or '')[:10]}"),
        kv('Average price', px(trd.get('avg_price'), digits)),
        kv(f"Price now ({trd.get('judged_on') or '?'})", px(now_px, digits)),
        kv('N at the entry', smart(trd.get('n_entry'), 2)),
        kv('Stop', f"{px(stop, digits)} · {trd.get('stop_origin') or '?'}"),
        kv('2N from the best fill', px(trd.get('stop_2n'), digits)),
        kv('Exit channel', f"{px(trd.get('stop_channel'), digits)} (now {px(trd.get('exit_channel_now'), digits)})"),
        kv('Broker backstops', ', '.join(px(x, digits) for x in lst(trd.get('backstop_prices'))) or 'none'),
        kv('Adds left', smart(trd.get('adds_left'))),
        kv('Entered', f"{when(trd.get('entry_utc') or trd.get('entry_t'))} · {dur(trd.get('age_s'))} ago"),
    ])
    stops = dl(g(trd, 'journal', 'stops'))
    stop_rows = [[when(s.get('utc') or s.get('t')), px(s.get('stop'), digits), s.get('origin') or '—', s.get('why') or '—']
                 for s in stops]
    flags = []
    if trd.get('known_to_bot') is False:
        flags.append(chip('positions it could not take over', 'warn'))
    if trd.get('pending_fill'):
        flags.append(chip('a leg is not listed yet', 'warn'))
    if trd.get('closing'):
        flags.append(chip('closing this poll', 'accent'))
    if g(trd, 'journal', 'rebuilt'):
        flags.append(chip('rebuilt from the terminal after a start without the state file', 'warn'))
    body = html.Div([
        html.Div(className='pos-head', children=[
            badge(side_glyph(side), 'accent'),
            html.Span(f"{smart(trd.get('legs_count'))}/{smart(trd.get('max_legs'))} legs · {fnum(trd.get('lots'), 2)} lot · "
                      f"unit {smart(trd.get('units'))}", className='pos-what'),
            html.Span(money(pnl, signed=True), className=f'pos-pl {pl_class(pnl)}'),
            *flags,
        ]),
        gauge,
        info,
        legs_table(trd.get('legs'), digits, turtle=True),
        html.Div([html.Div('Every stop move', className='mini-title'),
                  table(['time', 'stop', 'from', 'why'], stop_rows, num_cols=(1,))]) if stop_rows else None,
    ])
    return card('Open Turtle trade' + as_of(d), body, sub='one stop for every leg, never loosened; no target'
                + (' · the bot has not written since: the P/L and the legs are those of its last poll' if as_of(d) else ''))


# ───────────────────────────── how close is it (the open position's exits, a flat bot's entry) ─────────────────

ALERT_AMBER = 70.0                        # a meter this far of the way (percent) turns amber ...
ALERT_RED = 90.0                          # ... and this far red; the banner (and the optional sound) follow
NEAR_ENTRY_N = 2.0                        # a flat Turtle's entry meter fills over the last 2 N before its level


def closeness(pct_):
    """'red' (>= ALERT_RED %), 'amber' (>= ALERT_AMBER %) or 'ok'."""
    v = num(pct_)
    if v is None:
        return 'ok'
    return 'red' if v >= ALERT_RED else 'amber' if v >= ALERT_AMBER else 'ok'


def _clamp_pct(v):
    v = num(v)
    return None if v is None else max(0.0, min(100.0, v))


def prog(label, pct_, detail, kind='exit', sub=None):
    """One progress meter: `label`, the percent of the way, a bar that turns amber / red (kind 'exit' or 'entry'; an
    'info' meter stays neutral), the distance in words under it."""
    p = _clamp_pct(pct_)
    level = 'info' if kind == 'info' else closeness(p)
    return html.Div(className=f'prog prog-{level} prog-{kind}', children=[
        html.Div(className='prog-head', children=[
            html.Span(label, className='prog-label'),
            html.Span('—' if p is None else f'{p:.0f}% of the way', className='prog-pct'),
        ]),
        html.Div(className='prog-track', children=[
            html.Div(className='prog-fill', style={'width': f'{p or 0:.1f}%'}),
            html.Div(className='prog-mark', style={'left': f'{ALERT_AMBER:g}%'}),
            html.Div(className='prog-mark', style={'left': f'{ALERT_RED:g}%'}),
        ]),
        html.Div(detail, className='prog-detail'),
        html.Div(sub, className='prog-sub') if sub else None,
    ])


def _extra_tiles(d, side, pnl, avg, now_px, legs, lots, age_s, digits):
    """The handy figures of an open position: P/L in $ and in price, time in trade, legs and lot, the virtual balance,
    the spread, the last tick."""
    tr = dd(d.get('trace'))
    acct, mk = dd(tr.get('account')), dd(tr.get('market'))
    sgn = 1.0 if str(side).upper() == 'BUY' else -1.0
    pts = (now_px - avg) * sgn if (num(now_px) is not None and num(avg) is not None) else None
    tick_t = ts(mk.get('tick_t') or mk.get('tick_utc'))
    vb_src = acct.get('virtual_balance_source')
    return html.Div(className='xtiles', children=[
        tile('P/L', money(pnl, signed=True), 'floating, this bot only', vcls=pl_class(pnl)),
        tile('P/L in price', (f"{'+' if (pts or 0) > 0 else ''}{px(pts, digits)}" if pts is not None else '—'),
             f"from the average {px(avg, digits)}", vcls=pl_class(pts)),
        tile('Time in trade', dur(age_s) if num(age_s) is not None else '—', 'since the first leg'),
        tile('Legs · lot', f"{smart(legs)} · {fnum(lots, 2)}", 'open legs · lots in all'),
        tile('Virtual balance', money(acct.get('virtual_balance')),
             'from the deal history (the bot re-reads it when flat)' if vb_src == 'deal history' else
             f"start {money(acct.get('virtual_start_balance'))}"),
        tile('Spread', smart(mk.get('spread'), digits), f"bid {px(mk.get('bid'), digits)} · ask {px(mk.get('ask'), digits)}"),
        tile('Last tick', when(tick_t), (f"{dur(_now() - tick_t)} ago" if tick_t is not None else 'no tick yet')),
    ])


def _gate_summary(dec, flat_words):
    """A flat bot: which entry conditions pass, which one is missing (the bot's own checks, in its order)."""
    gates = [gt for gt in dl(dec.get('gates')) if gt.get('role') in (None, 'need')]
    if not gates:
        return None
    ok = [gt for gt in gates if gt.get('ok') is True]
    first_bad = next((gt for gt in gates if gt.get('ok') is False), None)
    chips = [chip(('✓ ' if gt.get('ok') is True else '✗ ' if gt.get('ok') is False else '○ ') + str(gt.get('name') or gt.get('key')),
                  'pos' if gt.get('ok') is True else 'neg' if gt.get('ok') is False else '', icon='')
             for gt in gates]
    if first_bad is not None:
        need = first_bad.get('need')
        val = first_bad.get('value')
        wait = html.Div(className='wait', children=[
            html.Span('Waiting for: ', className='muted'), html.B(str(first_bad.get('name') or first_bad.get('key'))),
            html.Span(f" — now {smart(val) if not isinstance(val, str) else val}" if val is not None else ''),
            html.Span(f"; needs {need}" if need else ''),
            html.Span(f" ({first_bad.get('note')})" if first_bad.get('note') else '', className='muted'),
        ])
    else:
        wait = html.Div(f'Every entry condition passes: {flat_words}', className='wait')
    return html.Div([
        html.Div(f"{len(ok)} of {len(gates)} entry conditions met", className='mini-title'),
        html.Div(chips, className='chips chips-left gchips'),
        wait,
    ])


def proximity(d):
    """(view, alert): how close the open position is to its exits (target, stop, next add), or a flat bot to an entry;
    alert = {'level': 'red' / 'amber' / None, 'text', 'key'} for the banner and the optional sound / notification."""
    tr = dd(d.get('trace'))
    digits = digits_of(d)
    stale = is_stale(tr)
    alert = {'level': None, 'text': None, 'key': None}
    rows, extra, head = [], None, None
    bk = g(tr, 'basket', 'open')
    tt = dd(tr.get('turtle'))
    trd = tt.get('trade') if isinstance(tt.get('trade'), dict) else None
    worst = []                                     # (pct, what, text) of the alarm meters

    if isinstance(bk, dict) and bk.get('side'):
        side, pnl = bk.get('side'), num(bk.get('pnl'))
        jo = bk.get('judged_on') or 'bid'
        now_px = num(bk.get('price_now'))
        tgt_usd, stop_usd = num(bk.get('target_usd')), num(bk.get('stop_usd'))
        if tgt_usd:
            p = (pnl or 0.0) / tgt_usd * 100.0
            dist = abs((num(bk.get('target_price')) or 0) - (now_px or 0)) if num(bk.get('target_price')) is not None else None
            rows.append(prog('To the target', p,
                             f"target +{money(tgt_usd)} at {jo} {px(bk.get('target_price'), digits)} · "
                             f"{px(dist, digits)} in price · {money(bk.get('to_target_usd'))} to go"))
            worst.append((_clamp_pct(p), 'target', f"{side} basket {(_clamp_pct(p) or 0):.0f}% of the way to its target "
                                                   f"({money(bk.get('to_target_usd'))} to go)"))
        else:
            rows.append(html.Div('No target in this design: the basket closes at its stop (or another exit).',
                                 className='line muted'))
        if stop_usd:
            p = -(pnl or 0.0) / stop_usd * 100.0
            dist = abs((num(bk.get('stop_price')) or 0) - (now_px or 0)) if num(bk.get('stop_price')) is not None else None
            rows.append(prog('To the stop loss', p,
                             f"stop -{money(stop_usd)} at {jo} {px(bk.get('stop_price'), digits)} · "
                             f"{px(dist, digits)} in price · {money(bk.get('to_stop_usd'))} away"))
            worst.append((_clamp_pct(p), 'stop', f"{side} basket {(_clamp_pct(p) or 0):.0f}% of the way to its stop loss "
                                                 f"({money(bk.get('to_stop_usd'))} away)"))
        else:
            rows.append(html.Div('No stop in this design: the broker backstop is the only floor.', className='line muted'))
        ld = dd(bk.get('ladder'))
        last, nxt, lp = num(ld.get('last_fill')), num(ld.get('next_add_price')), num(ld.get('price_now'))
        if ld.get('on') and not ld.get('exhausted') and None not in (last, nxt, lp) and nxt != last:
            p = (lp - last) / (nxt - last) * 100.0
            gap_words = (f"{px(abs(nxt - lp), digits)} away" if p < 100 else
                         f"reached ({px(abs(nxt - lp), digits)} beyond it)")
            rows.append(prog('To the next add (price gap)', p,
                             f"{ld.get('judged_on') or 'ask'} {px(nxt, digits)} or better, {gap_words} · then a "
                             f"{ld.get('tier_tf') or '?'} {ld.get('trigger') or ''} "
                             f"({'armed' if ld.get('armed') else 'not armed yet'})", kind='info'))
        bs = [num(x) for x in lst(bk.get('backstop_prices')) if num(x) is not None]
        if bs and now_px is not None:
            near = min(bs, key=lambda b_: abs(b_ - now_px))
            rows.append(html.Div(f"Broker backstop {px(near, digits)} is {px(abs(near - now_px), digits)} away (it acts "
                                 "only while the bot is down).", className='line muted small'))
        extra = _extra_tiles(d, side, pnl, bk.get('avg_price'), now_px, len(dl(bk.get('legs'))), bk.get('lots'),
                             bk.get('age_s'), digits)
        head = f"Open {side} basket"
    elif trd and trd.get('side') and not trd.get('both_sides'):
        side, pnl = trd.get('side'), num(trd.get('pnl'))
        jo = trd.get('judged_on') or 'bid'
        now_px = num(trd.get('price_now'))
        sd, to_stop = num(trd.get('stop_dist')), num(trd.get('to_stop'))
        if sd and to_stop is not None:
            p = (1.0 - to_stop / sd) * 100.0
            gap = (pnl - num(trd.get('pnl_at_stop'))) if (pnl is not None and num(trd.get('pnl_at_stop')) is not None) else None
            rows.append(prog('To the stop loss', p,
                             f"stop {px(trd.get('stop'), digits)} at {jo} ({trd.get('stop_text') or trd.get('stop_origin') or ''}) · "
                             f"{px(to_stop, digits)} in price · {money(gap)} of P/L away · P/L there "
                             f"{money(trd.get('pnl_at_stop'), signed=True)}",
                             sub=f"the meter fills over the 2N stop distance ({px(sd, digits)}) from the stop"))
            worst.append((_clamp_pct(p), 'stop', f"{side} trade {(_clamp_pct(p) or 0):.0f}% of the way to its stop "
                                                 f"({px(to_stop, digits)} away)"))
        step, to_add = num(trd.get('add_step')), num(trd.get('to_next_add'))
        if num(trd.get('next_add')) is not None and step and to_add is not None:
            p = (1.0 - to_add / step) * 100.0
            rows.append(prog('To the next add (+1 leg)', p,
                             f"{trd.get('next_add_judged_on') or 'ask'} {'≥' if str(side).upper() == 'BUY' else '≤'} "
                             f"{px(trd.get('next_add'), digits)} · {px(to_add, digits)} to go · "
                             f"{smart(trd.get('adds_left'))} add(s) left", kind='info'))
        elif trd.get('full'):
            rows.append(html.Div('The trade is full: no more adds.', className='line muted'))
        rows.append(html.Div('No target: the Turtle exits only at its stop (2N from the best fill, or the exit channel '
                             'when that is tighter).', className='line muted small'))
        extra = _extra_tiles(d, side, pnl, trd.get('avg_price'), now_px, trd.get('legs_count'), trd.get('lots'),
                             trd.get('age_s'), digits)
        head = f"Open {side} Turtle trade"
    else:
        dec = dd(tr.get('decision'))
        o = dd(tt.get('orders'))
        if tt and o:
            n = num(tt.get('n')) or num(g(tt, 'levels', 'n'))
            armed = o.get('state') == 'armed' or o.get('armed') is True
            vote = g(tt, 'vote', 'last')
            for key, name, sign in (('buy', 'BUY', 1), ('sell', 'SELL', -1)):
                od = dd(o.get(key))
                lvl, dist = num(od.get('level')), num(od.get('distance'))
                if lvl is None:
                    continue
                if od.get('reached'):
                    p = 100.0
                elif dist is not None and n:
                    p = (1.0 - max(dist, 0.0) / (NEAR_ENTRY_N * n)) * 100.0
                else:
                    p = None
                vote_ok = vote is not None and num(vote) == od.get('vote_needed')
                detail = (f"{od.get('judged_on') or ('ask' if sign > 0 else 'bid')} {px(od.get('price_now'), digits)} → "
                          f"level {px(lvl, digits)} ({od.get('channel') or ''}) · "
                          + ('reached' if od.get('reached') else f"{px(dist, digits)} away ({fnum(od.get('distance_n'), 2)} N)")
                          + f" · needs the M15 vote {'+1' if sign > 0 else '-1'} (now {smart(vote) if vote is not None else '?'}"
                          + (', ok)' if vote_ok else ')'))
                rows.append(prog(f"To a {name} entry", p if armed else None, detail,
                                 kind='entry' if armed else 'info',
                                 sub=None if armed else (f"not an entry now: today's orders are {o.get('state') or 'not armed'}"
                                                         + (f" (used by the {o.get('used_by')} trade)" if o.get('used_by') else ''))))
                if armed:
                    worst.append((_clamp_pct(p), 'entry', f"flat: {(_clamp_pct(p) or 0):.0f}% of the way to a {name} entry "
                                                          f"({'level reached' if od.get('reached') else px(dist, digits) + ' away'})"))
        gs = _gate_summary(dec, 'the bot enters on this poll')
        if gs is not None:
            rows.append(gs)
        head = 'Flat: how close an entry is'
        if not rows:
            rows.append(html.Div('Flat: no entry condition in the trace yet.', className='line muted'))
    if worst and not stale:
        top = max(worst, key=lambda z: z[0] or 0)
        lvl = closeness(top[0])
        if lvl != 'ok':
            alert = {'level': lvl, 'text': top[2], 'key': f"{top[1]}:{lvl}:{tr.get('symbol') or d.get('symbol')}"}
    body = html.Div([
        html.Div(className='prox-head', children=[
            html.Span(head or '', className='prox-what'),
            badge({'red': 'VERY CLOSE', 'amber': 'GETTING CLOSE'}.get(alert['level'], 'NOT CLOSE'),
                  {'red': 'neg', 'amber': 'warn'}.get(alert['level'], 'neutral')) if worst and not stale else None,
            html.Span(f"amber from {ALERT_AMBER:g}% of the way, red from {ALERT_RED:g}%", className='muted small')
            if worst else None,
        ]),
        html.Div(rows, className='progs'),
        extra,
    ])
    return body, alert


@safe()
def proximity_view(d):
    if not d.get('trace'):
        return None
    view, _ = proximity(d)
    return html.Div([html.Div(className='prox-title', children=[
        html.Span('How close is it' + as_of(d), className='eyebrow'),
        html.Span(' · the open position against its target and stop loss, or a flat bot against its entry',
                  className='muted small')]), view], className='prox')


def alert_of(d):
    try:
        return proximity(d)[1] if d.get('trace') else {'level': None, 'text': None, 'key': None}
    except Exception:
        return {'level': None, 'text': None, 'key': None}


def alert_banner(alert):
    if not alert or not alert.get('level'):
        return None
    return html.Div(className=f"alertbar alertbar-{alert['level']}", children=[
        html.Span('●' if alert['level'] == 'red' else '▲', className='alert-ic'),
        html.B('Very close: ' if alert['level'] == 'red' else 'Getting close: '),
        html.Span(alert.get('text') or ''),
        html.Span(' · the Live tab has the details', className='muted'),
    ])


# ───────────────────────────── the chart ─────────────────────────────

def _bars(d, tf):
    """The bars of one timeframe as lists (t, o, h, l, c), the forming bar moved with the trace's bid."""
    b = dd(g(d, 'bars', 'tf', tf))
    cols = [lst(b.get(k)) for k in ('t', 'o', 'h', 'l', 'c')]
    n = min(len(c) for c in cols) if all(isinstance(c, list) for c in cols) else 0
    t, o, h, l, c = [], [], [], [], []
    for i in range(n):
        vals = [num(cols[j][i]) for j in range(5)]
        if any(v is None for v in vals):
            continue
        t.append(vals[0]); o.append(vals[1]); h.append(vals[2]); l.append(vals[3]); c.append(vals[4])
    bid = num(g(d, 'trace', 'market', 'bid'))
    tick_t = ts(g(d, 'trace', 'market', 'tick_t')) or ts(g(d, 'trace', 't'))
    tf_s = TF_SECONDS.get(tf, 60)
    if t and bid is not None and tick_t is not None and t[-1] <= tick_t < t[-1] + tf_s:
        c[-1] = bid
        h[-1] = max(h[-1], bid)
        l[-1] = min(l[-1], bid)
    return t, o, h, l, c


def _ms(t):
    """A time for a plotly date axis: the UTC wall-clock time as text. (Numbers would be shown in the browser's own
    time zone; the bot and its log work in UTC.)"""
    if t is None:
        return None
    return utc(float(t)).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def _result_col(pnl):
    v = num(pnl)
    return COL['pos'] if v is not None and v > 0 else (COL['neg'] if v is not None and v < 0 else COL['muted'])


@safe('figure')
def price_figure(d, tf):
    """Candles (bid) with this bot's entries (▲ buy / ▼ sell), exits (✕, green win / red loss), a dotted line
    from every entry to its exit, and the open trade's levels as labelled lines (Turtle: also today's levels)."""
    tf = tf if tf in TF_SECONDS else 'M15'
    tf_s = TF_SECONDS[tf]
    digits = digits_of(d)
    t, o, h, l, c = _bars(d, tf)
    fig = go.Figure()
    base_layout = dict(
        height=600, margin=dict(l=70, r=168, t=36, b=36), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family=FONT, size=11, color=COL['text2']), hovermode='closest', dragmode='pan',
        hoverlabel=dict(bgcolor=COL['raised'], bordercolor=COL['line'], font=dict(family=FONT, size=12, color=COL['text'])),
        legend=dict(orientation='h', x=0, y=1.0, xanchor='left', yanchor='bottom', font=dict(size=11, color=COL['text2']),
                    bgcolor='rgba(0,0,0,0)', itemclick='toggle', itemdoubleclick='toggleothers'),
        uirevision=f"{d.get('symbol')}-{tf}",
    )
    if not t:
        fig.update_layout(**dict(base_layout, height=260))
        fig.add_annotation(text=f'No {tf} bars yet ({d.get("bars_problem") or "the bars file has none"}).',
                           x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False, font=dict(size=14, color=COL['muted']))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig
    x = [_ms(v) for v in t]
    fig.add_trace(go.Candlestick(
        x=x, open=o, high=h, low=l, close=c, name=f'{tf} bars (bid)',
        increasing=dict(line=dict(color=COL['candle_up'], width=1), fillcolor=COL['candle_up']),
        decreasing=dict(line=dict(color=COL['candle_down'], width=1), fillcolor=COL['candle_down']),
        whiskerwidth=0, hoverlabel=dict(bgcolor=COL['raised']),
    ))
    t0, t_end = t[0], t[-1] + tf_s
    now_x = _ms(t[-1])

    def snap(v):
        v = ts(v)
        return None if v is None else _ms(math.floor(v / tf_s) * tf_s)

    def visible(v):
        v = ts(v)
        return v is not None and t0 <= v < t_end

    # the first view: the newest VIEW_BARS bars (and the whole open position); pan or zoom out for the rest
    tr0 = dd(d.get('trace'))
    pos_t = ts(g(tr0, 'basket', 'open', 'first_t') or g(tr0, 'basket', 'open', 'opened_at')
               or g(tr0, 'turtle', 'trade', 'entry_t'))
    vi = max(0, len(t) - VIEW_BARS)
    if pos_t is not None:
        while vi > 0 and t[vi] > pos_t - 10 * tf_s:
            vi -= 1
    y_lo, y_hi = min(l[vi:]), max(h[vi:])
    keep = []          # prices that must stay in view
    trades = dl(g(d, 'trades', 'closed'))
    tr = dd(d.get('trace'))
    # ── closed trades: entries, exits, the lines between ──
    ent = {'BUY': ([], [], []), 'SELL': ([], [], [])}
    ex = {'win': ([], [], []), 'loss': ([], [], [])}
    lines = {'win': ([], []), 'loss': ([], [])}
    for k, tr_ in enumerate(trades):
        legs = dl(tr_.get('legs'))
        pnl = num(tr_.get('pnl'))
        res = 'win' if (pnl or 0) > 0 else 'loss'
        reason = tr_.get('exit_reason_text') or tr_.get('exit_reason') or '?'
        close_t, close_px = ts(tr_.get('close_t') or tr_.get('close_utc')), num(tr_.get('close_price'))
        side = str(tr_.get('side') or '').upper()
        for i, lg in enumerate(legs):
            ot, op_ = ts(lg.get('open_t')), num(lg.get('open_price'))
            if ot is None or op_ is None:
                continue
            lt, lp = ts(lg.get('close_t')) or close_t, num(lg.get('close_price')) or close_px
            if visible(ot):
                bucket = ent.get(side) or ent['BUY']
                bucket[0].append(snap(ot)); bucket[1].append(op_)
                bucket[2].append(f"<b>{side_glyph(side)} · leg {i + 1} of {len(legs)}{' (add)' if i else ''}</b><br>"
                                 f"{stamp(ot)}<br>{px(op_, digits)} · {fnum(lg.get('lots'), 2)} lot<br>"
                                 f"trade {tr_.get('id')}: {reason}, {money(pnl, signed=True)} · leg {money(lg.get('net'), signed=True)}")
            if lt is not None and lp is not None and (visible(ot) or visible(lt)):
                lines[res][0].extend([snap(max(ot, t0)), snap(min(lt, t_end - 1)), None])
                lines[res][1].extend([op_, lp, None])
        if close_t is not None and close_px is not None and visible(close_t):
            ex[res][0].append(snap(close_t)); ex[res][1].append(close_px)
            ex[res][2].append(f"<b>✕ EXIT · {reason}</b><br>{stamp(close_t)} · {px(close_px, digits)}<br>"
                              f"{len(legs)} leg(s) · {fnum(tr_.get('lots'), 2)} lot · held {dur(tr_.get('hold_s'))}<br>"
                              f"P/L <b>{money(pnl, signed=True)}</b> · balance after {money(tr_.get('balance_after'))}")
    for res, (lx, ly) in lines.items():
        if lx:
            fig.add_trace(go.Scatter(x=lx, y=ly, mode='lines', name='trade (won)' if res == 'win' else 'trade (lost)',
                                     line=dict(color=COL['pos'] if res == 'win' else COL['neg'], width=1.5, dash='dot'),
                                     hoverinfo='skip', legendgroup=res, showlegend=False))
    # ── the open position ──
    open_legs, open_side, open_pnl, levels = [], None, None, []
    bk_open = g(tr, 'basket', 'open')
    trd = g(tr, 'turtle', 'trade')
    price_now = None
    # `on`: the price the bot compares a level with. The candles are bid prices; a level judged on the ask (a sell's
    # stop and target, a buy's add, a buy level, a sell position's broker sl) is crossed when the ask reaches it, about
    # a spread above the bid: its tag says '(ask)' and the ASK line is drawn next to the BID line
    if isinstance(bk_open, dict):
        open_legs, open_side, open_pnl = dl(bk_open.get('legs')), bk_open.get('side'), bk_open.get('pnl')
        price_now = num(bk_open.get('price_now'))
        jo = bk_open.get('judged_on') or ''
        t_from = ts(bk_open.get('first_t') or bk_open.get('opened_at'))
        sl_on = 'ask' if str(open_side or '').upper() == 'SELL' else 'bid'      # the broker sl of a sell: on the ask
        levels += [
            dict(y=bk_open.get('target_price'), name='TARGET', col=COL['pos'], dash='solid', t_from=t_from, key=True,
                 on=jo, hover=f"target +{money(bk_open.get('target_usd'))} (P/L > target, judged on the {jo}) · "
                              f"{money(bk_open.get('to_target_usd'))} to go"),
            dict(y=bk_open.get('stop_price'), name='STOP', col=COL['neg'], dash='solid', t_from=t_from, key=True, on=jo,
                 hover=f"stop -{money(bk_open.get('stop_usd'))} (judged on the {jo}) · {money(bk_open.get('to_stop_usd'))} away"),
            dict(y=bk_open.get('avg_price'), name='AVG', col=COL['muted'], dash='dashdot', t_from=t_from, key=True,
                 hover='the basket\'s lot-weighted average price'),
        ]
        for i, b_ in enumerate(lst(bk_open.get('backstop_prices'))):
            levels.append(dict(y=b_, name='BACKSTOP' if i == 0 else '', col=COL['neg'], dash='dot', t_from=t_from, key=False,
                               width=1, on=sl_on,
                               hover=f"broker backstop (the sl of leg {i + 1}, hit by the {sl_on}): only acts while the "
                                     f"bot is down"))
        ld = dd(bk_open.get('ladder'))
        if ld.get('on') and not ld.get('exhausted') and num(ld.get('next_add_price')) is not None:
            levels.append(dict(y=ld.get('next_add_price'), name='NEXT ADD', col=COL['accent'], dash='dash', t_from=t_from,
                               key=True, on=ld.get('judged_on'),
                               hover=f"next add: {ld.get('tier_tf')} {ld.get('trigger')} "
                                     f"({'armed' if ld.get('armed') else 'not armed'}), {ld.get('judged_on')} at this price or better"))
    elif isinstance(trd, dict) and not trd.get('both_sides'):
        open_legs, open_side, open_pnl = dl(trd.get('legs')), trd.get('side'), trd.get('pnl')
        price_now = num(trd.get('price_now'))
        t_from = ts(trd.get('entry_t') or trd.get('entry_utc'))
        stop_on = trd.get('judged_on') or ('ask' if str(open_side or '').upper() == 'SELL' else 'bid')
        # the stop as it moved: a step line from the entry to now
        stops = [s for s in dl(g(trd, 'journal', 'stops')) if ts(s.get('t') or s.get('utc')) and num(s.get('stop'))]
        if len({snap(max(ts(s.get('t') or s.get('utc')), t0)) for s in stops}) < 2:
            stops = []                  # every move inside one bar of this timeframe: the stop as a plain line
        if stops and t_from is not None:
            sx, sy = [], []
            for s in stops:
                st_t = max(ts(s.get('t') or s.get('utc')), t0)
                sx.append(snap(st_t)); sy.append(num(s.get('stop')))
            sx.append(_ms(t_end)); sy.append(num(trd.get('stop')) or sy[-1])
            fig.add_trace(go.Scatter(x=sx, y=sy, mode='lines', line=dict(color=COL['neg'], width=2, shape='hv'),
                                     name='stop (as it moved)',
                                     hovertemplate='stop %{y:,.' + str(digits) + 'f}' + (' (judged on the ask)' if stop_on == 'ask'
                                                                                         else '') + '<extra></extra>'))
        levels.append(dict(y=trd.get('stop'), name='STOP', col=COL['neg'], dash='solid', t_from=None if stops else t_from,
                           key=True, line=not stops, on=stop_on,
                           hover=f"the one stop of every leg, judged on the {stop_on}: {trd.get('stop_text') or trd.get('stop_origin')} · "
                                 f"{smart(trd.get('to_stop'), digits)} away · P/L there {money(trd.get('pnl_at_stop'), signed=True)}"))
        if num(trd.get('next_add')) is not None:
            levels.append(dict(y=trd.get('next_add'), name='NEXT ADD', col=COL['accent'], dash='dash', t_from=t_from, key=True,
                               on=trd.get('next_add_judged_on') or 'ask',
                               hover=(f"next leg when the {trd.get('next_add_judged_on') or 'ask'} ≥ this (the last fill + 0.5N)"
                                      if str(open_side or '').upper() == 'BUY' else
                                      f"next leg when the {trd.get('next_add_judged_on') or 'bid'} ≤ this (the last fill - 0.5N)")))
        for i, b_ in enumerate(lst(trd.get('backstop_prices'))):
            levels.append(dict(y=b_, name='BACKSTOP' if i == 0 else '', col=COL['neg'], dash='dot', t_from=t_from, key=False,
                               width=1, on=stop_on,
                               hover=f"broker backstop of leg {i + 1} (1 N beyond the stop at its fill, hit by the {stop_on})"))
        levels.append(dict(y=trd.get('avg_price'), name='AVG', col=COL['muted'], dash='dashdot', t_from=t_from, key=True,
                           hover='the trade\'s average price'))
    # ── the Turtle's levels: entry triggers only while today's orders are armed and no trade is open ──
    lv = g(tr, 'turtle', 'levels')
    ov = g(d, 'bars', 'overlay', 'turtle')
    t_orders = dd(g(tr, 'turtle', 'orders'))
    in_trade = bool(open_side) or (isinstance(trd, dict) and bool(trd))
    o_state = t_orders.get('state') or ('armed' if t_orders.get('armed') else None)
    new_t = ts(t_orders.get('until_t') or t_orders.get('until_utc'))
    new_at = utc(new_t).strftime('%H:%M') if new_t is not None else '?'       # the next D1 close: always 00:00 UTC
    if in_trade:                       # (note in the tag, words in the hover)
        not_now = ('no entry while in a trade', 'no entry while a trade is open (an entry needs a flat book)')
    elif o_state == 'used':
        by = f" by the {t_orders.get('used_by')} trade" if t_orders.get('used_by') else ''
        not_now = (f'used, new orders at {new_at}',
                   f"today's orders were used{by}: no entry until new orders at the next D1 close, {new_at} UTC")
    elif o_state == 'armed':
        not_now = None
    else:
        not_now = ('no orders', 'no daily levels: no orders')
    if tf == 'D1' and isinstance(ov, dict) and ov.get('from_t'):
        steps = {'buy': ('BUY LEVEL', 'dash', 'ask'), 'sell': ('SELL LEVEL', 'dash', 'bid'),
                 'exit_long': ('EXIT (long)', 'dot', None), 'exit_short': ('EXIT (short)', 'dot', None)}
        ft = lst(ov.get('from_t'))
        for key, (name, dash_, on) in steps.items():
            ys = lst(ov.get(key))
            pts = [(ts(a), num(b_)) for a, b_ in zip(ft, ys)]
            pts = [(a, b_) for a, b_ in pts if a is not None and b_ is not None and a >= t0 - 86400]
            if not pts:
                continue
            fig.add_trace(go.Scatter(x=[_ms(a) for a, _ in pts] + [_ms(t_end)], y=[b_ for _, b_ in pts] + [pts[-1][1]],
                                     mode='lines', line=dict(color=COL['blue'], width=1.4 if dash_ == 'dash' else 1,
                                                             dash=dash_, shape='hv'),
                                     name=name.lower(),
                                     hovertemplate=name.lower() + ' %{y:,.' + str(digits) + 'f}<extra></extra>'))
            muted = key in ('buy', 'sell') and not_now is not None
            levels.append(dict(y=pts[-1][1], name=name.split(' (')[0] if 'EXIT' not in name else name,
                               col=COL['faint'] if muted else COL['blue'], dash=dash_, key=False, line=False, on=on,
                               note=not_now[0] if muted else None,
                               hover=(f'{name.lower()} of today: not an entry now: {not_now[1]}' if muted else name.lower())))
    elif isinstance(lv, dict) and lv.get('ok') is not False:
        day_from = ts(lv.get('from_time') or lv.get('from_utc'))
        long_ = str(open_side or '').upper() == 'BUY'
        short_ = str(open_side or '').upper() == 'SELL'
        days = g(tr, 'turtle', 'channels', 'entry', 'days') or '?'
        xdays = g(tr, 'turtle', 'channels', 'exit', 'days') or '?'
        for key, name, on, what_, rule in (
                ('buy', 'BUY LEVEL', 'ask', f"today's buy level (the {days}-day high + tick)",
                 'an entry when the ask reaches it with the M15 vote +1'),
                ('sell', 'SELL LEVEL', 'bid', f"today's sell level (the {days}-day low - tick)",
                 'an entry when the bid reaches it with the M15 vote -1')):
            if not_now is None:            # the orders are armed and the book is flat: an entry trigger
                levels.append(dict(y=lv.get(key), name=name, col=COL['blue'], dash='dash', t_from=day_from, key=True,
                                   width=1.4, on=on, hover=f'{what_}: {rule}'))
            else:                          # used, or a trade is open: drawn muted, not a trigger now
                levels.append(dict(y=lv.get(key), name=name, col=COL['faint'], dash='dot', t_from=day_from, key=False,
                                   width=1, on=on, note=not_now[0], hover=f'{what_}: not an entry now: {not_now[1]}'))
        if long_:
            levels.append(dict(y=lv.get('trail_long'), name='EXIT CHANNEL', col=COL['blue'], dash='dot', t_from=day_from,
                               key=False, width=1,
                               hover=f"the {xdays}-day low: the long's stop is raised to it at a D1 close when it is tighter"))
        if short_:
            levels.append(dict(y=lv.get('trail_short'), name='EXIT CHANNEL', col=COL['blue'], dash='dot', t_from=day_from,
                               key=False, width=1,
                               hover=f"the {xdays}-day high: the short's stop is lowered to it at a D1 close when it is tighter"))
    # ── the open position highlighted: the room to the target (green) and to the stop (red), from its entry to now ──
    zone_from = None
    if isinstance(bk_open, dict):
        zone_from, z_avg = ts(bk_open.get('first_t') or bk_open.get('opened_at')), num(bk_open.get('avg_price'))
        zones = [(bk_open.get('target_price'), 'rgba(38,166,154,0.10)'), (bk_open.get('stop_price'), 'rgba(239,83,80,0.10)')]
    elif isinstance(trd, dict) and not trd.get('both_sides'):
        zone_from, z_avg = ts(trd.get('entry_t') or trd.get('entry_utc')), num(trd.get('avg_price'))
        zones = [(trd.get('stop'), 'rgba(239,83,80,0.10)')]
    if zone_from is not None and z_avg is not None:
        for y_, colr in zones:
            y_ = num(y_)
            if y_ is None:
                continue
            fig.add_shape(type='rect', xref='x', yref='y', x0=snap(max(zone_from, t0)), x1=_ms(t_end), y0=min(z_avg, y_),
                          y1=max(z_avg, y_), fillcolor=colr, line=dict(width=0), layer='below')
    # ── the open legs ──
    if open_legs:
        ox, oy, ot_ = [], [], []
        lx, ly = [], []
        side = str(open_side or '').upper()
        for i, lg in enumerate(open_legs):
            t_in, p_in = ts(lg.get('open_t') or lg.get('open_utc')), num(lg.get('price'))
            if t_in is None or p_in is None:
                continue
            if visible(t_in):
                ox.append(snap(t_in)); oy.append(p_in)
                ot_.append(f"<b>{side_glyph(side)} · open leg {i + 1} of {len(open_legs)}{' (add)' if i else ''}</b><br>"
                           f"{stamp(t_in)}<br>{px(p_in, digits)} · {fnum(lg.get('lots'), 2)} lot · P/L {money(lg.get('profit'), signed=True)}")
            if price_now is not None:
                lx.extend([snap(max(t_in, t0)), now_x, None]); ly.extend([p_in, price_now, None])
        if lx:
            fig.add_trace(go.Scatter(x=lx, y=ly, mode='lines', line=dict(color=_result_col(open_pnl), width=1.5, dash='dash'),
                                     hoverinfo='skip', name='open trade', showlegend=False))
        if ox:
            fig.add_trace(go.Scatter(x=ox, y=oy, mode='markers', name='open legs', text=ot_,
                                     hovertemplate='%{text}<extra></extra>',
                                     marker=dict(symbol='triangle-up' if side == 'BUY' else 'triangle-down', size=14,
                                                 color=COL['accent'], line=dict(color=COL['text'], width=1.5))))
            keep += oy
    for side, (xs, ys, txt) in ent.items():
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='markers', name=f'{side.lower()} entries', text=txt,
                                     hovertemplate='%{text}<extra></extra>',
                                     marker=dict(symbol='triangle-up' if side == 'BUY' else 'triangle-down', size=12,
                                                 color=COL['accent'], line=dict(color=COL['surface'], width=1.5))))
    for res, (xs, ys, txt) in ex.items():
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='markers', name='exits (won)' if res == 'win' else 'exits (lost)',
                                     text=txt, hovertemplate='%{text}<extra></extra>', legendgroup=res,
                                     marker=dict(symbol='x', size=12, color=COL['pos'] if res == 'win' else COL['neg'],
                                                 line=dict(color=COL['surface'], width=1.5))))
    # ── the price now: the bid (the candles) and the ask (what the '(ask)' levels are compared with) ──
    bid, ask = num(g(tr, 'market', 'bid')), num(g(tr, 'market', 'ask'))
    recent = t[max(0, len(t) - 1 - max(6, len(t) // 10))]
    spread = smart(g(tr, 'market', 'spread'))
    if bid is not None:
        levels.append(dict(y=bid, name='BID', col=COL['text2'], dash='dot', t_from=recent, key=True, width=1, line=True,
                           hover=f"the bid now (the candles are bid prices) · ask {px(ask, digits)} · spread {spread}"))
    if ask is not None:
        levels.append(dict(y=ask, name='ASK', col=COL['muted'], dash='dash', t_from=recent, key=True, width=1, line=True,
                           hover=f"the ask now, a spread ({spread}) above the bid: the levels tagged (ask) are crossed "
                                 f"when this line reaches them, not the candles"))
    # ── y range: the candles and the levels that matter; the others get a tag at the edge ──
    reach = (y_hi - y_lo) * 0.6          # a level this far beyond the candles still widens the range; farther: a tag
    for lvl in levels:
        y = num(lvl.get('y'))
        if lvl.get('key') and y is not None and y_lo - reach <= y <= y_hi + reach:
            keep.append(y)
    lo_v, hi_v = min([y_lo] + keep), max([y_hi] + keep)
    pad = (hi_v - lo_v) * 0.06 or max(abs(hi_v) * 0.001, 1.0)
    lo_v, hi_v = lo_v - pad, hi_v + pad
    tags = []
    for lvl in levels:
        y = num(lvl.get('y'))
        if y is None:
            continue
        inside = lo_v <= y <= hi_v
        label = (lvl['name'] or 'level') + (' (ask)' if lvl.get('on') == 'ask' else '')
        if lvl.get('line', True) and inside:
            x_from = snap(max(lvl['t_from'], t0)) if lvl.get('t_from') else _ms(t0)
            fig.add_trace(go.Scatter(x=[x_from, _ms(t_end)], y=[y, y], mode='lines', showlegend=False,
                                     line=dict(color=lvl['col'], width=lvl.get('width', 1.6), dash=lvl['dash']),
                                     hovertemplate=f"<b>{label} {px(y, digits)}</b><br>{lvl.get('hover', '')}<extra></extra>"))
        if lvl.get('name'):
            tags.append((y if inside else (hi_v if y > hi_v else lo_v), lvl, inside, y))
    # price tags at the right edge (over the price axis), spread so that none covers another: an upward pass,
    # then a downward one from the top edge, so every tag stays as close to its line as the others allow (a tag with
    # a note under its price takes two lines)
    plot_h = 600 - 36 - 36
    per_px = (hi_v - lo_v) / plot_h
    tags.sort(key=lambda z: z[0])
    ys = [z[0] for z in tags]
    half = [(15.0 if z[1].get('note') else 9.0) * per_px for z in tags]       # half a tag's height
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + half[i - 1] + half[i])
    if ys and ys[-1] > hi_v - half[-1]:
        ys[-1] = hi_v - half[-1]
        for i in range(len(ys) - 2, -1, -1):
            ys[i] = min(ys[i], ys[i + 1] - half[i + 1] - half[i])
    widest = 0
    for y_draw, (y_at, lvl, inside, y_true) in zip(ys, tags):
        arrow = '' if inside else ('▲ ' if y_true > hi_v else '▼ ')
        head = f"{arrow}{lvl['name']}{' (ask)' if lvl.get('on') == 'ask' else ''} {px(y_true, digits)}"
        ref = ask if lvl.get('on') == 'ask' else bid
        if lvl['name'] not in ('BID', 'ASK') and ref is not None and not lvl.get('note'):
            # how far the level is from the price it is compared with: the distance to go
            gap_ = y_true - ref
            head += f" · {'+' if gap_ > 0 else '-' if gap_ < 0 else ''}{px(abs(gap_), digits)}"
        text = head + (f"<br><span style='font-size:9.5px;color:{COL['muted']}'>{lvl['note']}</span>"
                       if lvl.get('note') else '')
        widest = max(widest, len(head) * 6.4, len(lvl.get('note') or '') * 5.8)
        fig.add_annotation(x=1.0, xref='paper', xanchor='left', y=y_draw, yref='y', showarrow=False,
                           text=text, align='left',
                           font=dict(family=MONO, size=10.5, color=COL['muted'] if lvl.get('note') else COL['text']),
                           bgcolor=COL['raised'], bordercolor=lvl['col'], borderwidth=1, borderpad=3,
                           hovertext=lvl.get('hover'), xshift=4)
    # the right margin holds the widest tag
    base_layout['margin'] = dict(base_layout['margin'], r=int(min(320, max(168, widest + 18))))
    # gaps in the bars (a weekend, gold's daily break on D1) are left out of the time axis
    gap_s = 1.5 * tf_s if tf_s >= 86400 else max(3 * tf_s, 3 * 3600)
    breaks = []
    for i in range(1, len(t)):
        if t[i] - t[i - 1] > gap_s:
            breaks.append(dict(bounds=[_ms(t[i - 1] + tf_s), _ms(t[i])]))
    fig.update_layout(**base_layout)
    fig.update_xaxes(type='date', range=[_ms(t[vi] - tf_s), _ms(t_end + (t_end - t[vi]) * 0.03)], showgrid=True,
                     gridcolor=COL['grid'], linecolor=COL['line'], tickfont=dict(color=COL['muted']),
                     showspikes=True, spikemode='across', spikesnap='cursor', spikethickness=1, spikecolor=COL['faint'],
                     spikedash='solid', rangeslider=dict(visible=False),
                     rangebreaks=[dict(bounds=b['bounds']) for b in breaks[-20:]] or None)
    step = (hi_v - lo_v) / 7.0
    tick_dp = max(0, min(digits, -int(math.floor(math.log10(step))) if step > 0 else digits))
    fig.update_yaxes(side='left', range=[lo_v, hi_v], showgrid=True, gridcolor=COL['grid'], zeroline=False,
                     tickformat=f',.{tick_dp}f', tickfont=dict(family=MONO, color=COL['muted'], size=10),
                     showspikes=True, spikemode='across', spikesnap='cursor', spikethickness=1, spikecolor=COL['faint'],
                     spikedash='solid')
    return fig


@safe()
def chart_note(d, tf):
    t, _, _, _, _ = _bars(d, tf)
    src = g(d, 'bars', 'source', tf)
    if not t:
        return 'No bars for this timeframe yet.'
    note = trades_note(d, what="the past entries and exits on the chart")
    return (f"{len(t)} {tf} bars (bid), {stamp(t[0])} → {stamp(t[-1])} (the last one is forming"
            f"{', moved with the bid of the trace' if g(d, 'trace', 'market', 'bid') is not None else ''}); bars file "
            f"written {when(g(d, 'bars', 't'))}{f', from the {src}' if src else ''}. A tag '(ask)' marks a level the bot "
            f"compares with the ask (the ASK line), not with the bid of the candles. "
            + (f"No past entries or exits: {note}. " if d.get('trades') is None else
               (f"{note[0].upper()}{note[1:]}. " if note else ''))
            + "Drag to pan, scroll to zoom, double-click to reset; click a legend item to hide it.")


# ───────────────────────────── the latest events (Live) and the log tab ─────────────────────────────

_EVENTS_CACHE = {}


def read_events(sym, tail=EVENTS_TAIL_BYTES):
    """(events, cut, problem): the events of logs/<SYMBOL>_events.jsonl in its last `tail` bytes, oldest first;
    cut = the file is longer. Cached until the file changes."""
    path = events_path(sym)
    try:
        st = os.stat(path)
    except OSError:
        return [], False, 'missing'
    key = (st.st_mtime_ns, st.st_size)
    hit = _EVENTS_CACHE.get((path, tail))
    if hit is not None and hit[0] == key:
        return hit[1], hit[2], None
    cut = st.st_size > tail
    try:
        with open(path, 'rb') as f:
            if cut:
                f.seek(st.st_size - tail)
            raw = f.read()
    except OSError as e:
        return [], False, f'unreadable ({e.__class__.__name__})'
    lines = raw.split(b'\n')
    if cut and lines:
        lines = lines[1:]               # the first line is cut in the middle
    out = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            ev = json.loads(ln.decode('utf-8', 'replace'))
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    for k in list(_EVENTS_CACHE):           # a copy: callbacks run in several threads
        if k[0] != path:
            _EVENTS_CACHE.pop(k, None)
    _EVENTS_CACHE[(path, tail)] = (key, out, cut)
    return out, cut, None


def _ev_text(ev):
    kv_ = dd(ev.get('kv'))
    return ' '.join([str(ev.get('cat') or ''), str(ev.get('msg') or ''),
                     ' '.join(f'{k}={v}' for k, v in kv_.items()) if isinstance(kv_, dict) else str(kv_)]).lower()


def event_row(ev, compact=False):
    lvl = str(ev.get('level') or 'INFO').upper()
    t = ts(ev.get('t')) or ts(ev.get('time'))
    clock = utc(t).strftime('%H:%M:%S.%f')[:-3] if t is not None else (ev.get('time') or '—')
    summary = html.Summary(className='ev-sum', children=[
        html.Span(clock, className='ev-t mono'),
        html.Span(lvl, className=f'lvl lvl-{lvl.lower()}'),
        html.Span(ev.get('cat') or '', className='ev-cat'),
        html.Span(_scrub(ev.get('msg') or ''), className='ev-msg'),
    ])
    if compact:
        return html.Div(className='ev ev-compact', children=summary.children)
    body = []
    kv_ = ev.get('kv')
    if isinstance(kv_, dict) and kv_:
        body.append(html.Div(className='ev-kv', children=[
            html.Div([html.Span(k, className='kv-k'),
                      html.Span(_scrub(v if isinstance(v, str) else json.dumps(_scrub_obj(v), default=str)),
                                className='kv-v mono')], className='kv')
            for k, v in kv_.items()]))
    if ev.get('data') is not None:
        body.append(html.Pre(json.dumps(_scrub_obj(ev.get('data')), indent=1, default=str)[:20000], className='pre'))
    if ev.get('traceback'):
        tb = ev['traceback']
        body.append(html.Pre(_scrub(tb if isinstance(tb, str) else '\n'.join(map(str, tb))), className='pre pre-err'))
    body.append(html.Div(_scrub(f"{ev.get('time') or stamp(t)} | {lvl} | {ev.get('cat')} | {ev.get('msg')}"),
                         className='ev-raw mono'))
    return html.Details(className=f'ev ev-{lvl.lower()}', children=[summary, html.Div(body, className='ev-body')])


_GATES_ONLY = re.compile(r'^[A-Z_]+ \(gates changed')


@safe()
def latest_events(sym, n=12):
    evs, _, problem = read_events(sym, tail=256 * 1024)
    keep = [e for e in evs if str(e.get('cat')) not in ('HEARTBEAT', 'CONFIG')
            and (str(e.get('level')).upper() != 'DEBUG'
                 or (str(e.get('cat')) == 'DECISION' and not _GATES_ONLY.match(str(e.get('msg') or ''))))]
    rows = [event_row(e, compact=True) for e in reversed(keep[-n:])]
    today = utc(_now()).strftime('%Y-%m-%d')
    path = os.path.abspath(text_log_path(sym, today))
    right = html.Div(className='pathbox', children=[
        html.Span("Today's text log:", className='muted'),
        html.Code(path, id='live-log-path', className='path'),
        dcc.Clipboard(target_id='live-log-path', className='copy', title='copy the path'),
    ])
    return card('Latest events', html.Div(rows, className='evlist evlist-compact') if rows else empty(
        'No events yet.' if problem is None else f'The events file is {problem}: {_rel(events_path(sym))}'),
        right=right, sub='orders, fills, closes, warnings, errors and every change of action; the Log tab has every line')


def log_files(sym):
    """[(day, path, size)] of the text logs of this symbol (logs/<SYMBOL>_<YYYY-MM-DD>.log), newest first."""
    if not is_symbol_name(sym):
        return []
    folder = _path('logs')
    name = re.compile(re.escape(sym) + r'_(\d{4}-\d{2}-\d{2})\.log', re.IGNORECASE)   # XAUUSDM_<day>.log too
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for n in names:
        m = name.fullmatch(n)
        if not m:
            continue
        p = os.path.join(folder, n)
        try:
            out.append((m.group(1), p, os.path.getsize(p)))
        except OSError:
            continue
    return sorted(out, reverse=True)


def _size(b):
    b = num(b) or 0
    return f'{b / 2 ** 20:.1f} MB' if b >= 2 ** 20 else f'{b / 1024:.0f} KB'


def text_tail(path, nbytes=TEXT_TAIL_BYTES):
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            if size > nbytes:
                f.seek(size - nbytes)
            raw = f.read().decode('utf-8', 'replace')
    except OSError as e:
        return None, f'{e.__class__.__name__}'
    lines = raw.split('\n')
    if size > nbytes:
        lines = lines[1:]
    return lines, None


# ───────────────────────────── trades ─────────────────────────────

def drawdown(curve):
    """(max drawdown in $, in % of the peak, peak time, trough time) of a balance curve [{t, v}]."""
    peak, peak_t, best = None, None, (0.0, 0.0, None, None)
    for p in dl(curve):
        v, t = num(p.get('v')), ts(p.get('t'))
        if v is None:
            continue
        if peak is None or v > peak:
            peak, peak_t = v, t
        fall = peak - v
        if fall > best[0]:
            best = (fall, fall / peak if peak else 0.0, peak_t, t)
    return best


@safe()
def trades_kpis(d):
    trd = dd(d.get('trades'))
    s = dd(trd.get('summary'))
    curve = dl(trd.get('balance_curve'))
    mdd, mdd_p, _, mdd_t = drawdown(curve)
    start = num(trd.get('virtual_start_balance')) or num(g(curve, 0, 'v'))
    now_bal = num(s.get('balance_now')) or num(g(curve, -1, 'v'))
    gw, gl = num(s.get('gross_win')) or 0.0, num(s.get('gross_loss')) or 0.0
    pf = (gw / abs(gl)) if gl else None
    ret = ((now_bal - start) / start) if (start and now_bal is not None) else None
    reasons = dd(s.get('exit_reasons'))
    note = trades_note(d)
    if d.get('trades') is None:             # no number at all: a 0 would read as "no trade yet"
        return html.Div(note[0].upper() + note[1:] + '.', className='banner banner-neg')
    written = ts(trd.get('t'))
    return html.Div([
        html.Div(note[0].upper() + note[1:] + '.', className='banner banner-warn') if note else None,
        html.Div(f"{d.get('symbol') or ''}_trades.json written {when(written)} ({dur(_now() - written)} ago)",
                 className='line muted') if written is not None and not note else None,
        html.Div(className='kpis', children=[
            tile('Closed trades', smart(s.get('closed') or 0), f"{smart(s.get('wins') or 0)} won · {smart(s.get('losses') or 0)} lost"),
            tile('Win rate', pct(s.get('win_rate'), 0) if s.get('closed') else '—', 'trades with a profit'),
            tile('Net P/L', pl(s.get('net')), f"won {money(gw)} · lost {money(gl)}"),
            tile('Largest loss', pl(s.get('worst')) if num(s.get('worst')) is not None and num(s.get('worst')) < 0 else '—',
                 f"best {money(s.get('best'), signed=True)}"),
            tile('Max drawdown', html.Span(f'-{money(mdd)}' if mdd else '$0.00', className='neg' if mdd else ''),
                 f"{pct(mdd_p)} of the peak" + (f" · deepest {when(mdd_t)}" if mdd_t else '')),
            tile('Virtual balance', money(now_bal), f"start {money(start)} · {pct(ret, 2) if ret is not None else '—'}"),
            tile('Profit factor', fnum(pf, 2) if pf is not None else '—', 'money won / money lost'),
            tile('Average hold', dur(s.get('avg_hold_s')), f"{smart(s.get('deals'))} deals in the history"),
        ]),
        html.Div(className='chips chips-left', children=[html.Span('Exits:', className='muted')]
                 + [chip(f'{k.replace("_", " ")} × {v}') for k, v in sorted(reasons.items(), key=lambda kv_: -kv_[1])])
        if reasons else None,
    ])


@safe('figure')
def equity_figure(d):
    trd = dd(d.get('trades'))
    curve = [p for p in dl(trd.get('balance_curve')) if ts(p.get('t')) is not None and num(p.get('v')) is not None]
    fig = go.Figure()
    layout = dict(height=300, margin=dict(l=10, r=70, t=10, b=30), paper_bgcolor='rgba(0,0,0,0)',
                  plot_bgcolor='rgba(0,0,0,0)', font=dict(family=FONT, size=11, color=COL['text2']), showlegend=False,
                  hovermode='x unified', hoverlabel=dict(bgcolor=COL['raised'], bordercolor=COL['line'],
                                                         font=dict(family=FONT, color=COL['text'])))
    if not curve:
        fig.update_layout(**layout)
        missing = d.get('trades') is None
        fig.add_annotation(text=(f"No balance curve: {d.get('symbol') or '<SYMBOL>'}_trades.json is "
                                 f"{d.get('trades_problem') or 'missing'}." if missing else 'No closed trade yet.'),
                           x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
                           font=dict(size=13, color=COL['warn'] if missing else COL['muted']))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig
    tx = [ts(p['t']) for p in curve]
    ys = [num(p['v']) for p in curve]
    start = ys[0]
    # the start value holds until the first trade: draw it from that trade's open, not from the start date's midnight
    first_open = ts(g(dl(trd.get('closed')), 0, 'open_t'))
    if len(tx) > 1 and first_open is not None and tx[0] < first_open < tx[1]:
        tx[0] = first_open
    xs = [_ms(v) for v in tx]
    peak, peaks = None, []
    for v in ys:
        peak = v if peak is None else max(peak, v)
        peaks.append(peak)
    fig.add_trace(go.Scatter(x=xs, y=peaks, mode='lines', line=dict(width=0, shape='hv'), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(width=0, shape='hv'), fill='tonexty',
                             fillcolor='rgba(224,85,85,0.12)', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color=COL['accent'], width=2, shape='hv'),
                             name='virtual balance', hovertemplate='%{y:$,.2f}<extra>balance</extra>'))
    hover = [f"{p.get('id') or 'start'} · {money(p.get('pnl'), signed=True) if p.get('pnl') is not None else 'start'}"
             for p in curve]
    fig.add_trace(go.Scatter(x=xs[1:], y=ys[1:], mode='markers', text=hover[1:],
                             marker=dict(size=8, color=[_result_col(p.get('pnl')) for p in curve[1:]],
                                         line=dict(color=COL['surface'], width=2)),
                             hovertemplate='%{text}<extra>trade</extra>'))
    eq = num(g(d, 'trace', 'account', 'own_equity'))
    t_now = ts(g(d, 'trace', 't'))
    if eq is not None and t_now is not None and t_now > ts(curve[-1]['t']):
        fig.add_trace(go.Scatter(x=[xs[-1], _ms(t_now)], y=[ys[-1], eq], mode='lines+markers',
                                 line=dict(color=COL['accent'], width=1.5, dash='dot'),
                                 marker=dict(size=[0, 8], color=COL['accent'], line=dict(color=COL['surface'], width=2)),
                                 hovertemplate='%{y:$,.2f}<extra>now, with the open P/L</extra>'))
    fig.add_hline(y=start, line_color=COL['line'], line_width=1)
    fig.update_layout(**layout)
    fig.update_xaxes(type='date', showgrid=False, linecolor=COL['line'], tickfont=dict(color=COL['muted']))
    fig.update_yaxes(side='right', showgrid=True, gridcolor=COL['grid'], zeroline=False, tickprefix='$',
                     tickformat=',.0f', tickfont=dict(color=COL['muted']))
    return fig


def _journal_view(j, digits):
    if not isinstance(j, dict):
        return None
    lines = [f"N at the entry {smart(j.get('n_entry'), 2)} · stop distance {smart(j.get('stop_dist'), 2)} · add step "
             f"{smart(j.get('add_step'), 2)} · entry level {px(j.get('entry_level'), digits)} (D1 bar {(j.get('entry_d1_utc') or '')[:10]})"
             f" · M15 vote {vote_glyph(j.get('vote'))} · unit {smart(j.get('units'))} from {money(j.get('balance'))}"
             + (' · rebuilt from the terminal' if j.get('rebuilt') else '')]
    legs = [[smart(x.get('id')), when(x.get('t')), px(x.get('price'), digits), px(x.get('level'), digits),
             px(x.get('backstop'), digits)] for x in dl(j.get('legs'))]
    stops = [[when(s.get('utc') or s.get('t')), px(s.get('stop'), digits), s.get('origin') or '—', s.get('why') or '—']
             for s in dl(j.get('stops'))]
    ex = dd(j.get('exit'))
    return html.Div([
        html.Div(lines, className='line muted'),
        html.Div(className='two', children=[
            html.Div([html.Div('Legs and their add levels', className='mini-title'),
                      table(['position', 'time', 'fill', 'add level', 'backstop'], legs, num_cols=(2, 3, 4))]) if legs else None,
            html.Div([html.Div('Stop moves', className='mini-title'),
                      table(['time', 'stop', 'from', 'why'], stops, num_cols=(1,))]) if stops else None,
        ]),
        html.Div(f"Exit {when(ex.get('t'))}: {ex.get('reason') or '?'} at {px(ex.get('price'), digits)} (stop {px(ex.get('stop'), digits)}, "
                 f"{ex.get('origin') or '?'}), P/L at the decision {money(ex.get('decision_pnl'), signed=True)}",
                 className='line muted') if ex else None,
    ])


TRADE_HEAD = ['#', 'opened', 'side', 'legs', 'lots', 'entry', 'closed', 'exit price', 'held', 'P/L', 'exit', 'balance after']


def trade_row(i, tr_, digits, live=False):
    legs = dl(tr_.get('legs'))
    pnl = tr_.get('pnl')
    reason = 'open' if live else (tr_.get('exit_reason_text') or tr_.get('exit_reason') or '?')
    cells = [smart(i), when(tr_.get('open_utc') or tr_.get('open_t') or tr_.get('first_utc') or tr_.get('entry_utc')),
             side_glyph(tr_.get('side')), smart(len(legs)), fnum(tr_.get('lots'), 2),
             px(tr_.get('open_price') or tr_.get('avg_price'), digits),
             '—' if live else when(tr_.get('close_utc') or tr_.get('close_t')),
             px(tr_.get('price_now'), digits) if live else px(tr_.get('close_price'), digits),
             dur(tr_.get('age_s')) if live else dur(tr_.get('hold_s')), pl(pnl),
             badge(reason, 'accent') if live else reason, '—' if live else money(tr_.get('balance_after'))]
    leg_rows = [[smart(lg.get('position_id') or lg.get('ticket') or lg.get('id')), side_glyph(lg.get('side') or tr_.get('side')),
                 fnum(lg.get('lots'), 2), when(lg.get('open_t') or lg.get('open_utc')), px(lg.get('open_price') or lg.get('price'), digits),
                 when(lg.get('close_t')) if lg.get('close_t') else '—', px(lg.get('close_price'), digits),
                 pl(lg.get('net') if lg.get('net') is not None else lg.get('profit')),
                 ', '.join(str(x) for x in lst(lg.get('deal_reasons'))) or '—']
                for lg in legs]
    body = [table(['position', 'side', 'lots', 'opened', 'open price', 'closed', 'close price', 'net P/L', 'deal reasons'],
                  leg_rows, num_cols=(2, 4, 6, 7))]
    extra = []
    if not live:
        extra.append(f"profit {money(tr_.get('profit'))} · swap {money(tr_.get('swap'))} · commission {money(tr_.get('commission'))}"
                     f" · the bot recorded: {tr_.get('bot_reason') or '—'}"
                     + (f" · stop {px(tr_.get('exit_stop'), digits)} ({tr_.get('exit_detail')})" if tr_.get('exit_stop') else ''))
    body.append(html.Div(extra, className='line muted') if extra else None)
    body.append(_journal_view(tr_.get('turtle') or tr_.get('journal'), digits))
    return html.Details(className='trow' + (' trow-live' if live else ''), children=[
        html.Summary(className='trow-sum', children=[html.Span(c, className='tc' + (' num' if j in (4, 5, 7, 9, 11) else ''))
                                                     for j, c in enumerate(cells)]),
        html.Div(body, className='trow-body'),
    ])


@safe()
def trades_list(d, limit=200):
    trd = dd(d.get('trades'))
    digits = digits_of(d)
    closed = dl(trd.get('closed'))
    live = []
    tr = dd(d.get('trace'))
    op = g(tr, 'basket', 'open') or g(tr, 'turtle', 'trade')
    if isinstance(op, dict) and not op.get('both_sides'):
        live = [dict(op, legs=dl(op.get('legs')))]
    else:
        live = [x for x in trd.get('open') or [] if isinstance(x, dict)]
    rows = [trade_row('open', x, digits, live=True) for x in live]
    n = len(closed)
    for k, tr_ in enumerate(reversed(closed[-limit:])):
        rows.append(trade_row(n - k, tr_, digits))
    head = html.Div(className='trow-head', children=[html.Span(h, className='tc' + (' num' if j in (4, 5, 7, 9, 11) else ''))
                                                    for j, h in enumerate(TRADE_HEAD)])
    written = ts(trd.get('t'))
    missing = d.get('trades') is None
    if missing:                             # (the summary above says why)
        sub = (f"{'the open trade, from the trace; ' if rows else ''}the closed trades are not known: "
               f"{d.get('symbol') or '<SYMBOL>'}_trades.json is {d.get('trades_problem') or 'missing'}")
    else:
        sub = (f"{n} closed trade(s) since {(trd.get('since_utc') or '')[:10] or '—'} (this bot's magic {smart(trd.get('magic'))}); "
               f"click a row for its legs" + ('' if n <= limit else f'; the newest {limit} shown')
               + (f" · trades.json written {when(written)}" if written is not None else ''))
    if rows:
        body = html.Div([head] + rows, className='trows')
    elif missing:
        body = empty(f"{d.get('symbol') or '<SYMBOL>'}_trades.json is {d.get('trades_problem') or 'missing'}",
                     'the closed trades are not known here; the bot writes the file at its first deal-history read after '
                     'a start, then at least every minute')
    else:
        body = empty('No trade yet.', trades_note(d))
    return card('Every trade, newest first', body, sub=sub)


# ───────────────────────────── history (the old views) ─────────────────────────────

def daily_dir(sym):
    return _path(DAILY_TRADE_SUBDIR, sym)


def daily_files(sym):
    """{server_date 'YYYY-MM-DD': path} of the old daily-trade files."""
    out = {}
    if not is_symbol_name(sym):
        return out
    for p in glob.glob(os.path.join(glob.escape(daily_dir(sym)), '*.json')):
        if os.path.basename(p) == HISTORICAL_SUMMARY_FILENAME:
            continue
        data, _ = read_json(p)
        day = g(data, 'server_date')
        if isinstance(day, str):
            out[day] = p
    return out


def daily_figure(deals):
    deals = sorted([x for x in deals or [] if isinstance(x, dict)], key=lambda x: str(x.get('time') or ''))
    fig = make_subplots(rows=2, cols=1, row_heights=[0.45, 0.55], vertical_spacing=0.16,
                        subplot_titles=['P/L of every closing deal', 'Cumulative P/L'])
    labels, pnl, cum, hover = [], [], [], []
    run = 0.0
    for i, x in enumerate(deals, 1):
        t = ts(x.get('time'))
        label = utc(t).strftime('%H:%M:%S') if t is not None else f'#{i}'
        if label in labels:                     # two deals of one close: one bar each
            label = f'{label} ({sum(1 for v in labels if v.split(" (")[0] == label) + 1})'
        labels.append(label)
        v = num(x.get('net_profit')) if num(x.get('net_profit')) is not None else (num(x.get('profit')) or 0.0)
        pnl.append(v)
        run += v
        cum.append(round(run, 2))
        hover.append(f"{x.get('type') or ''} {x.get('volume') or ''} lot at {x.get('price')}<br>net {money(v, signed=True)} "
                     f"(profit {money(x.get('profit'))}, commission {money(x.get('commission'))}, swap {money(x.get('swap'))})"
                     f"<br>cumulative {money(run, signed=True)}")
    show_text = len(deals) <= GRAPH_TEXT_LABEL_THRESHOLD
    width = min(0.6, 24.0 / (1400.0 / max(1, len(deals))))        # bars about 24 px wide at most
    fig.add_trace(go.Bar(x=labels, y=pnl, width=width, marker=dict(color=[_result_col(v) for v in pnl], line=dict(width=0)),
                         text=[money(v, signed=True) for v in pnl] if show_text else None, textposition='outside',
                         cliponaxis=False, textfont=dict(size=10, color=COL['text2']), hovertext=hover, hoverinfo='text',
                         showlegend=False),
                  row=1, col=1)
    lo_b, hi_b = min(pnl + [0.0]), max(pnl + [0.0])
    pad_b = (hi_b - lo_b) * 0.3 or 1.0
    fig.update_yaxes(range=[lo_b - pad_b, hi_b + pad_b], row=1, col=1)
    fig.add_trace(go.Scatter(x=labels, y=cum, mode='lines+markers' if len(deals) <= GRAPH_CUM_LABEL_THRESHOLD else 'lines',
                             line=dict(color=COL['accent'], width=2), marker=dict(size=7, color=COL['accent'],
                                                                                 line=dict(color=COL['surface'], width=2)),
                             hovertext=hover, hoverinfo='text', showlegend=False), row=2, col=1)
    fig.add_hline(y=0, line_color=COL['line'], line_width=1, row=2, col=1)
    fig.update_layout(height=440, margin=dict(l=50, r=20, t=30, b=30), paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', font=dict(family=FONT, size=11, color=COL['text2']), bargap=0.35)
    fig.update_xaxes(showgrid=False, tickfont=dict(size=9, color=COL['muted']), type='category')
    fig.update_yaxes(showgrid=True, gridcolor=COL['grid'], zeroline=False, tickprefix='$', tickfont=dict(color=COL['muted']))
    for ann in fig.layout.annotations:
        ann.font = dict(size=11, color=COL['muted'], family=FONT)
    return fig


@safe()
def history_daily(sym, day):
    files = daily_files(sym)
    path = files.get(day)
    data, _ = read_json(path) if path else (None, None)
    hist, _ = read_json(os.path.join(daily_dir(sym), HISTORICAL_SUMMARY_FILENAME))
    deals = lst(g(data, 'deals'))
    tiles_ = html.Div(className='kpis', children=[
        tile(f'P/L on {day}', pl(g(data, 'total_profit')) if data else '—', f"{smart(g(data, 'deal_count') or 0)} closing deals"),
        tile('Average per deal', pl(g(data, 'avg_profit')) if data else '—', f"{fnum(g(data, 'total_volume'), 2)} lot in all"),
        tile('Lifetime P/L', pl(g(hist, 'total_profit')) if hist else '—',
             f"{smart(g(hist, 'total_deals') or 0)} deals · {g(hist, 'period') or 'last 10 years'}"),
        tile('Lifetime average', pl(g(hist, 'avg_profit')) if hist else '—', f"updated {when(g(hist, 'last_updated'))}"),
    ])
    chart = dcc.Graph(figure=daily_figure(deals), config={'displayModeBar': False}) if deals else empty(
        f'No closing deal of this bot on {day}.')
    return html.Div([tiles_, chart])


@safe()
def history_strategy_log(sym):
    data, problem = read_json(_path('logs', f'{sym}_{STRATEGY_LOG_FILENAME}'))
    if not isinstance(data, list) or not data:
        return empty('No old strategy log.' if problem in (None, 'missing') else f'The old strategy log is {problem}.')
    rows = []
    for e in data[:200]:
        det = dd(e.get('details'))
        bits = [f'{k} {smart(v)}' for k, v in det.items() if k not in ('response', 'mt5_symbol')
                and not isinstance(v, (dict, list))][:8]
        rows.append([when(e.get('time')), e.get('event') or '—', e.get('tag') or '—', _scrub(' · '.join(bits))])
    return table(['time (server)', 'event', 'tag', 'details'], rows, cls='tbl-log')


_CONFIG_CACHE = {}
_CONST_LINE = re.compile(r'^([A-Z][A-Z0-9_]*) = (.*)$')
DESIGN_KEYS = ('DESIGN_NAME', 'STRATEGY', 'OPEN_SCORE_WEIGHTS', 'FORCE_CLOSE_SCORE_WEIGHTS', 'ENTRY_S', 'ENTRY_AGREE_S',
               'LADDER_S', 'FORCE_CLOSE_ENABLED', 'FORCE_CLOSE_S', 'TREND_TF', 'VOL_TF', 'VOL_LEN', 'TARGET_USD_PER_UNIT',
               'STRATEGY_HEDGE', 'STOP_LOSS_USD_PER_UNIT', 'TARGET_VOL', 'STOP_VOL', 'BACKSTOP_FACTOR',
               'VOL_CAP_USD_PER_UNIT', 'LOSS_COOLDOWN_S', 'REENTRY_COOLDOWN_SECONDS', 'MAX_ADDS', 'LADDER_TRIGGER',
               'LADDER_TFS', 'LADDER_GAP_VOL', 'LADDER_MULTIPLIERS', 'RSI_OVERSOLD', 'RSI_OVERBOUGHT')
DEPLOY_KEYS = ('DEMO_BRANCH', 'MAGIC', 'ORDER_COMMENT', 'VIRTUAL_START_BALANCE', 'VIRTUAL_START_DATE', 'OUTPUT_DIR',
               'DASHBOARD_PORT', 'MARKET_LOOKBACK_MINUTES')


def bot_config(sym, d):
    """(when, {NAME: text}, notes) from the CONFIG lines the bot wrote when it started (the text log of its start
    day); (None, {}, []) when they cannot be found. Read once per start of the bot."""
    started = ts(g(d, 'trace', 'health', 'started_utc'))
    if started is None:
        return None, {}, []
    path = text_log_path(sym, utc(started).strftime('%Y-%m-%d'))
    key = (path, started)
    if key in _CONFIG_CACHE:
        return _CONFIG_CACHE[key]
    blocks, cur = [], None
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for ln in f:
                if ' | START | ' in ln and 'trading loop started' in ln:
                    cur = {'t': ts(ln[:23].replace(' ', 'T') + 'Z'), 'consts': {}, 'notes': []}
                    blocks.append(cur)
                elif cur is not None and ' | CONFIG | ' in ln:
                    msg = ln.split(' | ', 4)[3] if ln.count(' | ') >= 3 else ''
                    m = _CONST_LINE.match(msg.strip())
                    if m:
                        cur['consts'][m.group(1)] = m.group(2)
                    elif msg.strip():
                        cur['notes'].append(msg.strip())
    except OSError:
        return None, {}, []
    blocks = [b for b in blocks if b['t'] is not None and b['t'] <= started + 120 and b['consts']]
    out = (blocks[-1]['t'], blocks[-1]['consts'], blocks[-1]['notes']) if blocks else (None, {}, [])
    if len(_CONFIG_CACHE) > 8:
        _CONFIG_CACHE.clear()
    _CONFIG_CACHE[key] = out
    return out


def _as_value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-12
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    return a == b


@safe()
def settings_view(sym='', d=None):
    """The settings the bot started with (its CONFIG lines), grouped: the design and its levers, this deployment,
    everything else; a value constants.py has changed since is marked. Without those lines: constants.py as the
    dashboard read it at its start. 'design' marks what the branch's design block sets."""
    d = d or {}
    design_names = set()
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'constants.py'), encoding='utf-8') as f:
            tail = f.read().split('# ─── Design of this branch', 1)
        if len(tail) == 2:
            design_names = set(re.findall(r'^([A-Z][A-Z0-9_]*)\s*=', tail[1], flags=re.M))
    except OSError:
        pass
    when_, consts, notes = bot_config(sym, d)
    here = {n: getattr(_C, n) for n in vars(_C) if n.isupper()}
    from_bot = bool(consts)
    values = {k: _as_value(v) for k, v in consts.items()} if from_bot else here
    strategy = values.get('STRATEGY') or g(d, 'trace', 'strategy')
    turtle_keys = tuple(k for k in values if k.startswith('TURTLE_'))
    design = [k for k in (DESIGN_KEYS[:2] + (turtle_keys if strategy == 'turtle' else DESIGN_KEYS[2:])) if k in values]
    deploy = [k for k in DEPLOY_KEYS if k in values]
    rest = [k for k in values if k not in design and k not in deploy]

    def row(name):
        v = values.get(name)
        text = consts[name] if from_bot else (json.dumps(v, default=str) if isinstance(v, (dict, list, tuple)) else repr(v))
        tags = []
        if name in design_names:
            tags.append(badge('design', 'accent', title="set in this branch's design block of constants.py"))
        if from_bot and name in here and not _same(_as_value(consts[name]), here[name]):
            tags.append(badge(f'constants.py now: {here[name]!r}'[:60], 'warn',
                              title='constants.py has another value now: the bot uses it after its next start'))
        return html.Div(className='set-row', children=[html.Code(name, className='set-k'),
                                                       html.Span(_scrub(text[:300]), className='set-v mono'),
                                                       html.Span(tags, className='set-tags')])

    head = (f"as the bot logged them when it started, {stamp(when_)}" if from_bot else
            "constants.py as the dashboard read it at its start (the bot's start-up lines were not found)")
    return html.Div([
        html.Div(head, className='line muted'),
        html.Div("The design and its levers" + (" (the Turtle)" if strategy == 'turtle' else ''), className='mini-title set-h'),
        html.Div([row(k) for k in design], className='set-grid'),
        html.Div('This deployment', className='mini-title set-h'),
        html.Div([row(k) for k in deploy], className='set-grid'),
        html.Details(className='raw', children=[
            html.Summary([html.B(f'Every other setting ({len(rest)})'),
                          html.Span('  indicator lengths, timeframes, files, the old live levers', className='muted')]),
            html.Div([row(k) for k in rest], className='set-grid'),
        ]),
        html.Details(className='raw', children=[
            html.Summary([html.B(f'The start-up notes ({len(notes)})'),
                          html.Span('  the design in words, symbols.json, the symbol\'s facts', className='muted')]),
            html.Div([html.Div(n_, className='line mono small') for n_ in notes]),
        ]) if notes else None,
    ])


# the raw files the History tab shows: a fixed list of the bot's own files ({sym} = a symbol of symbols())
RAW_FILES = (('trace', '{sym}_trace.json'), ('trades', '{sym}_trades.json'), ('old status', '{sym}.json'),
             ('account', 'account.json'), ('basket state', STATE_SUBDIR + '/{sym}_state.json'),
             ('Turtle book', STATE_SUBDIR + '/{sym}_turtle.json'),
             ('Turtle journal', STATE_SUBDIR + '/{sym}_turtle_trades.json'),
             ('exit reasons', STATE_SUBDIR + '/{sym}_exit_reasons.json'))


@safe()
def raw_view(sym):
    if not is_symbol_name(sym):
        return empty('No files yet.')
    kids = []
    for label, name in RAW_FILES:
        rel = name.format(sym=sym)
        data, problem = read_json(_path(*rel.split('/')))
        if data is None and problem == 'missing':
            continue
        text = json.dumps(data, indent=1, default=str) if data is not None else problem
        kids.append(html.Details(className='raw', children=[
            html.Summary([html.B(label), html.Span(f'  {rel} · {_size(len(text))}', className='muted')]),
            html.Pre(_scrub(text[:300000]), className='pre'),
        ]))
    bars, _ = read_json(bars_path(sym))
    if isinstance(bars, dict):
        meta = {k: v for k, v in bars.items() if k not in ('tf', 'overlay')}
        meta['bars'] = {tf: len(g(bars, 'tf', tf, 't') or []) for tf in (dd(bars.get('tf')))}
        kids.append(html.Details(className='raw', children=[
            html.Summary([html.B('bars (without the columns)'), html.Span(f'  {sym}_bars.json', className='muted')]),
            html.Pre(json.dumps(meta, indent=1, default=str), className='pre')]))
    return html.Div(kids) if kids else empty('No files yet.')


# ───────────────────────────── the page ─────────────────────────────

# ───────────────────────────── changes & issues ─────────────────────────────

# The bot's WARN / ERROR lines grouped by what they are about: (code, what the message holds, what it means, what to do)
ISSUE_KINDS = (
    ('TERMINAL_IN_USE', re.compile(r'TERMINAL_IN_USE'),
     'The slot\'s terminal holds another account: the bot does not log in over it and does not trade.',
     'Open that MT5 terminal and log it into the demo account of mt5_credentials.json (or give each slot its own '
     'terminal). The bot tries again by itself.'),
    ('LIVE_TERMINAL_PATH', re.compile(r'LIVE_TERMINAL_PATH'),
     'The terminal path in the credentials is the one of a live bot: the demo bot refuses it.',
     'Give this demo slot its own MT5 terminal folder in mt5_credentials.json.'),
    ('ACCOUNT_REFUSED', re.compile(r'^not trading: |ACCOUNT_REFUSED|refused, not trading'),
     'The terminal holds an account the bot refuses (not the demo account, not hedging, another login): no trading.',
     'Log the terminal into the demo account of mt5_credentials.json. Trading starts again by itself.'),
    ('RECONNECT_FAILED', re.compile(r'^reconnect failed|^reconnect attempt \d+ failed|RECONNECT_FAILED'),
     'The bot lost the terminal and could not connect again yet. It keeps trying (the log has every attempt).',
     'Check that the MT5 terminal is open and logged in. If it stays red for more than a few minutes, restart the '
     'terminal, then the bot.'),
    ('MT5_INIT_FAILED', re.compile(r'initiali[sz]e failed'),
     'The bot could not connect to the MT5 terminal (initialize). While the terminal is gone this comes with '
     'RECONNECT_FAILED.',
     'Check that the slot\'s MT5 terminal is installed, open and logged in, and that terminal_path in '
     'mt5_credentials.json points at it.'),
    ('TERMINAL_ERROR', re.compile(r'^poll skipped'),
     'A poll could not read the terminal; nothing was decided in that poll.',
     'A few are normal (a short stall). Many in a row: check the terminal and the internet connection.'),
    ('POLL_FAILED', re.compile(r'^the poll failed'),
     'A poll raised an error; the loop goes on one second later.',
     'Send the day\'s text log: the line has the full traceback.'),
    ('TRACE_FAILED', re.compile(r'^the trace hook'),
     'A part of the dashboard\'s data could not be written this poll. Trading is not affected.',
     'Send the day\'s text log if it repeats.'),
    ('WRITE_FAILED', re.compile(r'^could not write|could not write the state file'),
     'A file could not be written (a full disk, or Windows refused it for a moment). Trading goes on.',
     'Check the free disk space. A single line is harmless: the bot writes the file again.'),
    ('CLOSE_INCOMPLETE', re.compile(r'is incomplete'),
     'A close left legs open (the terminal refused one); the bot closes the rest on the next poll.',
     'Nothing, unless it repeats for minutes: then check the terminal (off quotes, market closed).'),
    ('CLOSED_OUTSIDE', re.compile(r'closed outside the bot'),
     'Positions of this bot were closed outside it: the broker backstop, a stop-out, by hand, or while it was down.',
     'Nothing to do if you closed them. Else look at the Trades tab for the result.'),
    ('D1_LATE', re.compile(r'is not there yet'),
     'The terminal gave the new daily bar late; the bot keeps the levels of the day before until it comes.',
     'Nothing: it asks again every poll. Many minutes late: check the terminal\'s connection.'),
    ('ORDER_REFUSED', re.compile(r'retcode|\b(order|close)\b.*\brefused'),
     'The terminal refused an order or a close.',
     'Look at the retcode in the line (10018 market closed, 10019 no money, 10021 no quotes). Send the day\'s log if '
     'it repeats.'),
)
_NUM_RUN = re.compile(r'(?<![A-Za-z])\d[\d,.:]*')


def issue_kind(ev):
    """(code, meaning, what to do) of a WARN / ERROR event; unknown ones are grouped by category and message shape."""
    msg = str(ev.get('msg') or '')
    for code, rx, meaning, todo in ISSUE_KINDS:
        if rx.search(msg):
            return code, meaning, todo
    shape = _NUM_RUN.sub('#', msg)[:70]
    return f"{ev.get('cat') or 'OTHER'}: {shape}", None, None


def issues(sym, now=None):
    """[{code, level, count, count_24h, first, last, msg, meaning, todo}] of the WARN / ERROR lines of the events file
    (its newest EVENTS_TAIL_BYTES), the newest problem first; (list, cut, problem)."""
    evs, cut, problem = read_events(sym)
    now = _now() if now is None else now
    groups = {}
    for e in evs:
        lvl = str(e.get('level') or '').upper()
        if lvl not in ('WARN', 'ERROR'):
            continue
        code, meaning, todo = issue_kind(e)
        t = ts(e.get('t')) or ts(e.get('time'))
        gr = groups.get(code)
        if gr is None:
            gr = groups[code] = {'code': code, 'level': lvl, 'count': 0, 'count_24h': 0, 'first': t, 'last': t,
                                 'msg': None, 'meaning': meaning, 'todo': todo, 'cat': e.get('cat')}
        gr['count'] += 1
        if lvl == 'ERROR':
            gr['level'] = 'ERROR'
        if t is not None:
            if now - t <= 86400:
                gr['count_24h'] += 1
            gr['first'] = t if gr['first'] is None else min(gr['first'], t)
            gr['last'] = t if gr['last'] is None else max(gr['last'], t)
        gr['msg'] = e.get('msg')
    out = sorted(groups.values(), key=lambda x: (x['level'] != 'ERROR', -(x['last'] or 0)))
    return out, cut, problem


@safe()
def issues_view(sym):
    rows, cut, problem = issues(sym)
    if problem:
        return empty(f'The events file is {problem}: {_rel(events_path(sym))}',
                     'the bot writes it from its start; no file, no issue list')
    if not rows:
        return html.Div([html.Div('No warning and no error in the log.', className='flat pos'),
                         html.Div('Every WARN and ERROR line of the bot would be listed here, grouped by kind.',
                                  className='line muted')])
    now = _now()
    n_err = sum(r['count'] for r in rows if r['level'] == 'ERROR')
    n_warn = sum(r['count'] for r in rows if r['level'] == 'WARN')
    recent = sum(r['count_24h'] for r in rows)
    head = html.Div(className='chips chips-left', children=[
        chip(f'{n_err} error line(s)', 'neg' if n_err else 'pos'),
        chip(f'{n_warn} warning line(s)', 'warn' if n_warn else 'pos'),
        chip(f'{recent} in the last 24 h', 'warn' if recent else 'pos'),
        html.Span(f"from {'the newest ' + _size(EVENTS_TAIL_BYTES) + ' of ' if cut else ''}"
                  f"{os.path.basename(events_path(sym))}", className='muted small'),
    ])
    items = []
    for k, r in enumerate(rows):
        active = r['last'] is not None and now - r['last'] <= 3600
        items.append(html.Details(open=k == 0, className=f"issue issue-{r['level'].lower()}", children=[
            html.Summary(className='issue-sum', children=[
                html.Span(r['level'], className=f"lvl lvl-{r['level'].lower()}"),
                html.Span(r['code'], className='issue-code mono'),
                html.Span(f"{r['count']}×", className='issue-n mono'),
                html.Span(f"first {when(r['first'])} · last {when(r['last'])} ({dur(now - r['last']) + ' ago' if r['last'] else '—'})",
                          className='issue-when'),
                badge('in the last hour', 'neg' if r['level'] == 'ERROR' else 'warn') if active else None,
            ]),
            html.Div(className='issue-body', children=[
                html.Div([html.B('What it means: '), r['meaning']], className='line') if r.get('meaning') else None,
                html.Div([html.B('What to do: '), r['todo']], className='line') if r.get('todo') else None,
                html.Div([html.Span('The last line: ', className='muted'), html.Code(_scrub(r.get('msg') or ''), className='mono')],
                         className='line'),
                html.Div(f"{r['count_24h']} in the last 24 h · category {r.get('cat') or '—'} · the Log tab has every line "
                         f"(search for a word of it)", className='line muted small'),
            ]),
        ]))
    return html.Div([head, html.Div(items, className='issues')])


_CHANGELOG_CACHE = {}
_CL_HEAD = re.compile(r'^## \[(?P<ver>[^\]]+)\]\s+[—–]\s+(?P<date>.+?)\s+[—–]\s+(?P<title>.*)$')


def changelog_entries():
    """[(version, date, title, markdown body)] of the branch's CHANGELOG.md, newest first; cached until it changes."""
    path = os.path.join(HERE, 'CHANGELOG.md')
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    hit = _CHANGELOG_CACHE.get(path)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8', 'replace')
    except OSError:
        return None
    out = []
    parts = re.split(r'\n(?=## \[)', text)
    for part in parts[1:]:
        first, _, body = part.partition('\n')
        m = _CL_HEAD.match(first.strip())
        if m:
            out.append((m.group('ver'), m.group('date').strip(), m.group('title').strip(), body.strip('\n -')))
        else:
            out.append((first.lstrip('# ').strip(), '', '', body.strip('\n -')))
    _CHANGELOG_CACHE.clear()
    _CHANGELOG_CACHE[path] = (key, out)
    return out


@safe()
def changelog_view(limit=40):
    entries = changelog_entries()
    if entries is None:
        return empty('No CHANGELOG.md next to dashboard.py.')
    items = []
    for i, (ver, date, title, body) in enumerate(entries[:limit]):
        demo = 'demo' in ver
        items.append(html.Details(open=i == 0, className='cl', children=[
            html.Summary(className='cl-sum', children=[
                html.Span(ver, className=f"cl-ver mono {'cl-demo' if demo else ''}"),
                html.Span(date, className='cl-date'),
                html.Span(title, className='cl-title'),
            ]),
            dcc.Markdown(body, className='md', link_target='_blank'),
        ]))
    more = len(entries) - limit
    return html.Div([
        html.Div(f"{len(entries)} versions in this branch's CHANGELOG.md, newest first; click one to open it"
                 + (f" (the {more} oldest are in the file)" if more > 0 else '') + '.', className='count'),
        html.Div(items, className='cls'),
    ])


CSS = """
:root{--page:#070b17;--surface:#0c1324;--raised:#111a2e;--raised2:#16213a;--line:#1f2a44;--grid:#162036;
--text:#eef0f5;--text2:#aab3c5;--muted:#8b95aa;--faint:#5d6a85;--accent:#d4a843;--accent-soft:rgba(212,168,67,.13);
--accent-line:rgba(212,168,67,.5);--pos:#3cc48e;--pos-soft:rgba(60,196,142,.13);--neg:#e05555;--neg-soft:rgba(224,85,85,.13);
--warn:#f0c040;--warn-soft:rgba(240,192,64,.12);--blue:#4a8ecc;
--sans:Inter,"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
--mono:"JetBrains Mono","Cascadia Mono","SF Mono",Menlo,Consolas,monospace}
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;background:var(--page);color:var(--text);font:13px/1.45 var(--sans);-webkit-font-smoothing:antialiased}
b{font-weight:600}
code,.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:.94em}
.muted{color:var(--muted)}
.pos{color:var(--pos)}.neg{color:var(--neg)}
::selection{background:rgba(212,168,67,.3)}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#263252;border-radius:8px}
::-webkit-scrollbar-track{background:transparent}
._dash-loading,._dash-loading-callback{display:none!important}
/* top bar */
.topbar{background:linear-gradient(180deg,#0a1122,#080d1b);border-bottom:1px solid var(--line);padding:14px 28px 12px}
.top-row{display:flex;gap:18px;align-items:flex-start}
.brand{display:flex;align-items:center;gap:10px;min-width:150px;padding-top:2px}
.brand img{width:38px;height:38px;object-fit:contain}
.brand-name{font-weight:800;letter-spacing:.22em;font-size:13px;color:var(--accent)}
.brand-sub{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-top:1px}
.status{flex:1;min-width:0}
.status-top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}
.ident-top{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.sym{font-size:22px;font-weight:700;letter-spacing:.02em}
.what{font-size:13px;color:var(--text2)}
.ident-sub{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:2px}
.ident-sub b{color:var(--text2);font-family:var(--mono);font-weight:500}
.chips{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;align-items:center}
.chips-left{justify-content:flex-start;margin:8px 0 0}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);
background:var(--raised);color:var(--text2);font-size:12px;white-space:nowrap}
.chip-ic{font-size:10px;line-height:1}
.chip-pos{border-color:rgba(60,196,142,.4);color:var(--text)}.chip-pos .chip-ic{color:var(--pos)}
.chip-neg{border-color:rgba(224,85,85,.55);background:var(--neg-soft);color:var(--text)}.chip-neg .chip-ic{color:var(--neg)}
.chip-warn{border-color:rgba(240,192,64,.5);background:var(--warn-soft);color:var(--text)}.chip-warn .chip-ic{color:var(--warn)}
.chip-accent{border-color:var(--accent-line);background:var(--accent-soft);color:var(--text)}
.money{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;margin-top:12px}
/* tabs */
.tabbar{display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid var(--line);
background:#080d1b;position:sticky;top:0;z-index:20}
.tabbar-right{display:flex;gap:12px;align-items:center;color:var(--muted);font-size:12px}
/* page */
.page{max-width:1640px;margin:0 auto;padding:18px 28px 40px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px}
.card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:12px}
.card-title{margin:0;font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--text2)}
.card-sub{font-size:12px;color:var(--muted);margin-top:3px}
.card-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.grid-2{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:16px;align-items:start}
.grid-2>.card{margin-bottom:0}
@media (max-width:1180px){.grid-2{grid-template-columns:1fr}.money{grid-template-columns:repeat(3,1fr)}}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--text2)}
.now{border-color:#2a3656;background:linear-gradient(180deg,#0e1730,#0c1324 60%)}
.now-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.now-title{display:flex;align-items:center;gap:10px}
.now-words{color:var(--muted)}
.now-meta{color:var(--muted);font-size:12px;font-family:var(--mono)}
.headline{font-size:21px;line-height:1.4;font-weight:600;margin:10px 0 2px;max-width:1250px;color:var(--text)}
.now-grid{margin-top:14px}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;
letter-spacing:.04em;border:1px solid var(--line);background:var(--raised);color:var(--text2);white-space:nowrap}
.badge-accent{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent)}
.badge-pos{background:var(--pos-soft);border-color:rgba(60,196,142,.45);color:var(--pos)}
.badge-neg{background:var(--neg-soft);border-color:rgba(224,85,85,.5);color:var(--neg)}
.badge-warn{background:var(--warn-soft);border-color:rgba(240,192,64,.45);color:var(--warn)}
.banner{border-radius:8px;padding:8px 12px;margin-top:10px;font-size:12.5px}
.banner-warn{background:var(--warn-soft);border:1px solid rgba(240,192,64,.4)}
.banner-neg{background:var(--neg-soft);border:1px solid rgba(224,85,85,.5);color:var(--text);font-weight:600}
.headline-old{color:var(--text2)}
.orders{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.order{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:4px 0}
.order-what{font-weight:600}.order-det{color:var(--muted)}
.mini-title{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);margin:0 0 6px}
.line{margin:6px 0;color:var(--text2)}
.line.muted{color:var(--muted);font-size:12px}
.flat{font-size:15px;font-weight:600}
/* tiles */
.tile{background:var(--raised);border:1px solid var(--line);border-radius:10px;padding:9px 12px;min-width:0}
.tile-k{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile-v{font-size:16px;font-weight:600;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile-sub{font-size:11.5px;color:var(--muted);margin-top:2px;line-height:1.35}
.tile-warn{border-color:rgba(240,192,64,.45)}
.tiles3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0}
.tiles4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}
.kpis{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:8px}
.kpis .tile-v{font-size:20px}
@media (max-width:1180px){.kpis{grid-template-columns:repeat(4,1fr)}.tiles4{grid-template-columns:repeat(2,1fr)}}
/* key-values */
.kvs{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:4px 28px;margin:12px 0}
.kv{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid var(--grid);min-width:0}
.kv-k{color:var(--muted);white-space:nowrap}
.kv-v{color:var(--text);text-align:right;overflow-wrap:anywhere;font-family:var(--mono);font-size:12px}
/* gates */
.gates{display:flex;flex-direction:column}
.gsec{display:flex;gap:8px;align-items:baseline;margin:12px 0 4px;font-size:11px;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;color:var(--text2)}
.gsec:first-child{margin-top:0}
.gsec-sub{font-weight:400;letter-spacing:0;text-transform:none;color:var(--muted)}
.gate{display:grid;grid-template-columns:24px minmax(0,1fr);gap:8px;padding:7px 8px;border-top:1px solid var(--grid);
border-left:2px solid transparent}
.gate-decides{background:var(--accent-soft);border-left-color:var(--accent);border-radius:0 6px 6px 0}
.gate-idle{opacity:.5}
.gi{font-weight:700;text-align:center;font-size:14px;line-height:20px}
.gi-pass{color:var(--pos)}.gi-fail{color:var(--neg)}.gi-fire{color:var(--accent)}.gi-idle{color:var(--muted)}
.gi-na{color:var(--faint)}
.gate-top{display:flex;align-items:baseline;gap:8px;min-width:0}
.gate-name{font-weight:600}
.gate-val{margin-left:auto;color:var(--text);text-align:right;padding-left:8px;white-space:nowrap}
.gtag{font-size:10.5px;padding:0 6px;border-radius:4px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.gtag-accent{border-color:var(--accent-line);color:var(--accent)}
.gate-need{color:var(--text2);font-size:12px;margin-top:1px}
.gate-note{color:var(--muted);font-size:12px}
.glegend{display:flex;gap:10px;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
.glegend b{font-size:13px}
/* scores / meters */
.scores{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.score{background:var(--raised);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.score-head{display:flex;align-items:baseline;gap:8px}
.score-label{font-weight:600}
.score-w{color:var(--muted);font-family:var(--mono);font-size:12px}
.score-v{margin-left:auto;font-size:20px;font-weight:700}
.score-sub{font-size:12px;color:var(--text2);margin-top:2px}
.meter{position:relative;margin:4px 0 2px}
.m-top{position:relative;height:16px}
.m-tlabel{position:absolute;transform:translateX(-50%);font-size:10.5px;font-weight:600;white-space:nowrap;color:var(--text2)}
.m-track{position:relative;height:10px;border-radius:5px;background:#0a1020;border:1px solid var(--line)}
.m-band{position:absolute;top:0;bottom:0}
.band-none{background:rgba(139,149,170,.16)}
.band-neg{background:var(--neg-soft)}.band-pos{background:var(--pos-soft)}
.m-tick{position:absolute;top:-4px;bottom:-4px;width:2px;transform:translateX(-1px);background:var(--muted)}
.mk-buy,.mk-sell,.mk-zero{background:var(--text2)}
.mk-accent{background:var(--accent)}
.mk-leg{background:var(--faint);top:0;bottom:0}
.m-tlabel.mk-buy,.m-tlabel.mk-sell,.m-tlabel.mk-zero,.m-tlabel.mk-accent,.m-tlabel.mk-leg{background:none}
.m-tlabel.mk-accent{color:var(--accent)}
.m-dot{position:absolute;top:50%;width:14px;height:14px;border-radius:50%;transform:translate(-50%,-50%);
border:3px solid var(--surface);box-shadow:0 0 0 1px var(--text2)}
.m-dot-accent{background:var(--accent)}.m-dot-pos{background:var(--pos)}.m-dot-neg{background:var(--neg)}
.m-bottom{display:flex;justify-content:space-between;gap:16px;margin-top:5px;font-size:11.5px;color:var(--muted)}
.m-hi{text-align:right}
.meter-empty{color:var(--muted)}
/* tables */
.tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin:4px 0 8px}
.tbl th{font-size:11px;font-weight:600;color:var(--muted);text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);
white-space:nowrap}
.tbl td{padding:6px 8px;border-bottom:1px solid var(--grid);color:var(--text);vertical-align:top}
.tbl .num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl tr:hover td{background:rgba(255,255,255,.015)}
.tbl-votes td:nth-child(2),.tbl-votes td:nth-child(5){white-space:nowrap;font-weight:600}
.tbl-votes td:nth-child(4),.tbl-votes td:nth-child(7){color:var(--text2);font-size:12px}
.tf-roles{font-size:11px;color:var(--muted);white-space:nowrap}
.tbl-settings td{padding:4px 8px}.tbl-settings code{color:var(--text)}
.tbl-log td:first-child{white-space:nowrap;font-family:var(--mono)}
/* sparks */
.sparks{display:flex;flex-direction:column;gap:6px;margin-top:6px}
.spark-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.spark-t{font-size:11.5px;color:var(--text2);margin:2px 0 0 4px}
.spark-empty{color:var(--faint);font-size:12px;padding:10px}
.spark-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--muted);margin-top:4px}
.lk{display:inline-block;vertical-align:middle;margin-right:5px}
.lk-line{width:16px;height:2px;background:var(--text2)}
.lk-dot-accent{width:8px;height:8px;border-radius:50%;background:var(--accent)}
.lk-dash-accent{width:16px;height:0;border-top:2px dashed var(--accent)}
.lk-dot-white{width:7px;height:7px;border-radius:50%;background:var(--text)}
.rsi-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:10px}
.rsi-row .mini-title{margin:0 6px 0 0}
.box{background:var(--raised);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:10px 0}
.box-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.box-head .mini-title{margin:0}
.box .tbl td{border-bottom-color:#1a2440}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
/* the open position */
.pos-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.pos-what{color:var(--text2)}
.pos-pl{margin-left:auto;font-size:24px;font-weight:700}
/* chart */
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--raised)}
.seg label{padding:5px 12px;cursor:pointer;color:var(--text2);font-weight:600;font-size:12px;border-right:1px solid var(--line);
margin:0;display:inline-flex;align-items:center;user-select:none}
.seg label:last-child{border-right:0}
.seg input{position:absolute;opacity:0;width:0;height:0;pointer-events:none}
.seg label:has(input:checked){background:var(--accent-soft);color:var(--accent)}
.chart-note{font-size:12px;color:var(--muted);margin-top:4px}
/* events */
.evlist{display:flex;flex-direction:column}
.ev{border-top:1px solid var(--grid)}
.ev-sum{display:grid;grid-template-columns:96px 62px 104px minmax(0,1fr);gap:10px;padding:6px 6px;cursor:pointer;
list-style:none;align-items:baseline}
.ev-sum::-webkit-details-marker{display:none}
.ev-compact{display:grid;grid-template-columns:96px 62px 104px minmax(0,1fr);gap:10px;padding:5px 6px;align-items:baseline}
.ev[open]>.ev-sum{background:rgba(255,255,255,.02)}
.ev-t{color:var(--muted);font-size:12px}
.ev-cat{color:var(--text2);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ev-msg{color:var(--text);overflow-wrap:anywhere}
.ev-body{padding:4px 8px 10px 112px}
.ev-kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:2px 18px}
.ev-raw{color:var(--faint);font-size:11px;margin-top:6px;overflow-wrap:anywhere}
.lvl{font-size:10.5px;font-weight:700;letter-spacing:.04em;text-align:center;padding:1px 0;border-radius:4px;border:1px solid var(--line);
color:var(--text2)}
.lvl-error{color:var(--neg);border-color:rgba(224,85,85,.55);background:var(--neg-soft)}
.lvl-warn{color:var(--warn);border-color:rgba(240,192,64,.45);background:var(--warn-soft)}
.lvl-order,.lvl-fill,.lvl-close{color:var(--accent);border-color:var(--accent-line);background:var(--accent-soft)}
.lvl-debug{color:var(--muted);border-color:var(--grid)}
.ev-error .ev-msg{color:#f3b0b0}
.pre{background:#080d1b;border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-family:var(--mono);font-size:11.5px;
color:var(--text2);white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;margin:6px 0}
.pre-err{color:#f3b0b0;border-color:rgba(224,85,85,.4)}
.pre-log{max-height:900px;font-size:11px;line-height:1.5}
.dayrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px}
.pathbox{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px}
.path{background:#080d1b;border:1px solid var(--line);border-radius:6px;padding:3px 8px;color:var(--text);font-size:12px}
.copy{cursor:pointer;color:var(--accent);font-size:14px;display:inline-flex}
.logbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.chk{display:inline-flex;gap:4px;flex-wrap:wrap}
.chk label{display:inline-flex!important;align-items:center;gap:6px;padding:3px 11px;border:1px solid var(--line);
border-radius:999px;font-size:12px;font-weight:600;color:var(--muted);cursor:pointer;margin:0;user-select:none;
background:transparent}
.chk input{position:absolute;opacity:0;width:0;height:0;pointer-events:none}
.chk label::before{content:'○';font-size:10px}
.chk label:has(input:checked){color:var(--text);border-color:#34426a;background:var(--raised)}
.chk label:has(input:checked)::before{content:'✓';color:var(--accent)}
.search input,.search{background:#080d1b;border:1px solid var(--line);border-radius:8px;color:var(--text);padding:6px 10px;
font:13px var(--sans);min-width:400px;outline:none}
.search:focus{border-color:var(--accent-line)}
.btn{background:var(--accent-soft);border:1px solid var(--accent-line);color:var(--accent);border-radius:8px;padding:5px 12px;
font:600 12px var(--sans);cursor:pointer}
.btn:hover{background:rgba(212,168,67,.22)}
.filesgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:8px}
.count{color:var(--muted);font-size:12px;margin:2px 0 8px}
.daysep{padding:8px 6px 4px;color:var(--accent);font-size:11px;font-weight:700;letter-spacing:.08em}
/* trades */
.trows{display:flex;flex-direction:column}
.trow-head,.trow-sum{display:grid;grid-template-columns:48px 150px 76px 40px 52px 110px 150px 110px 76px 96px minmax(150px,1fr) 104px;
gap:18px;align-items:baseline;padding:7px 10px}
.trow-head{font-size:11px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line)}
.trow{border-bottom:1px solid var(--grid)}
.trow-sum{cursor:pointer;list-style:none}
.trow-sum::-webkit-details-marker{display:none}
.trow[open]>.trow-sum,.trow-sum:hover{background:rgba(255,255,255,.02)}
.trow-live>.trow-sum{background:var(--accent-soft)}
.tc{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tc.num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.trow-body{padding:4px 10px 12px 52px}
details.raw{border-top:1px solid var(--grid);padding:6px 0}
details.raw>summary{cursor:pointer;list-style:none}
details.raw>summary::-webkit-details-marker{display:none}
.empty{padding:22px;text-align:center;color:var(--muted)}
.empty-sub{font-size:12px;margin-top:4px}
.footer{color:var(--faint);font-size:11.5px;text-align:center;padding:10px 0 26px}
.set-h{margin-top:14px}
.set-grid{display:grid;grid-template-columns:1fr 1fr;column-gap:28px}
.set-row{display:grid;grid-template-columns:minmax(200px,auto) minmax(0,1fr) auto;gap:12px;align-items:baseline;
padding:5px 2px;border-bottom:1px solid var(--grid)}
.set-k{color:var(--text2);font-size:12px}
.set-v{color:var(--text);overflow-wrap:anywhere}
.set-tags{display:flex;gap:4px}
.small{font-size:12px}
/* how close is it */
.prox{margin-top:16px;border-top:1px solid var(--line);padding-top:14px}
.prox-title{margin-bottom:8px}
.prox-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.prox-what{font-size:15px;font-weight:600}
.progs{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:10px 18px}
.prog{background:var(--raised);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.prog-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.prog-label{font-weight:600}
.prog-pct{font-family:var(--mono);font-size:13px;font-weight:700;color:var(--text2)}
.prog-track{position:relative;height:12px;border-radius:6px;background:#0a1020;border:1px solid var(--line);margin:7px 0 6px;
overflow:hidden}
.prog-fill{position:absolute;left:0;top:0;bottom:0;border-radius:6px 0 0 6px;background:var(--blue);transition:width .4s}
.prog-mark{position:absolute;top:0;bottom:0;width:1px;background:rgba(238,240,245,.28)}
.prog-detail{font-size:12px;color:var(--text2)}
.prog-sub{font-size:11.5px;color:var(--muted);margin-top:2px}
.prog-ok .prog-fill{background:#3a6fa8}
.prog-amber{border-color:rgba(240,192,64,.55);background:linear-gradient(180deg,rgba(240,192,64,.08),var(--raised))}
.prog-amber .prog-fill{background:var(--warn)}.prog-amber .prog-pct{color:var(--warn)}
.prog-red{border-color:rgba(224,85,85,.7);background:linear-gradient(180deg,rgba(224,85,85,.12),var(--raised));
box-shadow:0 0 0 1px rgba(224,85,85,.25)}
.prog-red .prog-fill{background:var(--neg)}.prog-red .prog-pct{color:var(--neg)}
.prog-info .prog-fill{background:var(--accent);opacity:.75}
.xtiles{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;margin-top:12px}
@media (max-width:1180px){.xtiles{grid-template-columns:repeat(3,1fr)}.progs{grid-template-columns:1fr}}
.gchips .chip{font-size:11.5px}
.wait{margin-top:8px;color:var(--text2)}
/* the banner on every tab */
.alert-wrap{max-width:1640px;margin:0 auto;padding:0 28px}
.alertbar{margin-top:14px;border-radius:10px;padding:10px 14px;font-size:13.5px;display:flex;gap:8px;align-items:baseline;
flex-wrap:wrap}
.alertbar-amber{background:var(--warn-soft);border:1px solid rgba(240,192,64,.6)}
.alertbar-red{background:rgba(224,85,85,.18);border:1px solid rgba(224,85,85,.8);animation:pulse 1.6s ease-in-out infinite}
.alert-ic{font-size:12px}.alertbar-amber .alert-ic{color:var(--warn)}.alertbar-red .alert-ic{color:var(--neg)}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(224,85,85,.0)}50%{box-shadow:0 0 0 4px rgba(224,85,85,.25)}}
/* changes & issues */
.issues{display:flex;flex-direction:column;margin-top:10px}
.issue{border-top:1px solid var(--grid)}
.issue-sum{display:grid;grid-template-columns:62px minmax(220px,420px) 60px minmax(0,1fr) auto;gap:12px;padding:8px 6px;
cursor:pointer;list-style:none;align-items:baseline}
.issue-sum::-webkit-details-marker{display:none}
.issue[open]>.issue-sum,.issue-sum:hover{background:rgba(255,255,255,.02)}
.issue-code{font-weight:700;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.issue-n{color:var(--text2);text-align:right}
.issue-when{color:var(--muted);font-size:12px}
.issue-body{padding:2px 8px 10px 80px}
.issue-body code{white-space:pre-wrap;overflow-wrap:anywhere}
.cls{display:flex;flex-direction:column}
.cl{border-top:1px solid var(--grid)}
.cl-sum{display:grid;grid-template-columns:170px 100px minmax(0,1fr);gap:12px;padding:8px 6px;cursor:pointer;list-style:none;
align-items:baseline}
.cl-sum::-webkit-details-marker{display:none}
.cl[open]>.cl-sum,.cl-sum:hover{background:rgba(255,255,255,.02)}
.cl-ver{font-weight:700;color:var(--text2)}.cl-demo{color:var(--accent)}
.cl-date{color:var(--muted);font-size:12px}
.cl-title{color:var(--text)}
.md{padding:2px 10px 14px 18px;color:var(--text2);font-size:13px;line-height:1.55;max-width:1200px}
.md h3{font-size:13px;color:var(--text);margin:14px 0 6px;letter-spacing:.02em}
.md h4{font-size:12.5px;color:var(--text);margin:10px 0 4px}
.md code{background:#080d1b;border:1px solid var(--line);border-radius:4px;padding:0 4px;color:var(--text)}
.md pre{background:#080d1b;border:1px solid var(--line);border-radius:8px;padding:8px 10px;overflow:auto}
.md pre code{border:0;padding:0}
.md ul{padding-left:20px;margin:4px 0}
.md li{margin:2px 0}
.md table{border-collapse:collapse;margin:8px 0}.md th,.md td{border:1px solid var(--line);padding:4px 8px}
.md strong{color:var(--text)}
.md a{color:var(--accent)}
"""

INDEX = """<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
<link rel="icon" type="image/png" href="/assets/alcadeias.png">
{%css%}
<style>""" + CSS + """</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

TAB_STYLE = {'background': 'transparent', 'border': 'none', 'borderBottom': '2px solid transparent', 'padding': '12px 18px',
             'color': COL['muted'], 'fontWeight': '600', 'fontSize': '13px', 'fontFamily': FONT, 'width': 'auto',
             'flex': '0 0 auto'}
TAB_SELECTED = dict(TAB_STYLE, color=COL['text'], borderBottom=f"2px solid {COL['accent']}")
TABS = (('live', 'Live'), ('trades', 'Trades'), ('log', 'Log'), ('changes', 'Changes & issues'),
        ('history', 'History & settings'))

app = dash.Dash(__name__, title=f"{getattr(_C, 'DEMO_BRANCH', None) or 'demo bot'} · Alcadeias", update_title=None,
                suppress_callback_exceptions=True)
app.index_string = INDEX
server = app.server


@server.before_request
def _refuse_odd_paths():
    """A request path with '..' or a backslash (a probe for files outside the package folders) gets a plain 404:
    Dash's /_dash-component-suites/ route answered such paths with a 500 and a stack trace in the console."""
    from flask import request
    path = request.path or ''
    if '..' in path or '\\' in path or '%2e%2e' in path.lower() or '%5c' in path.lower():
        return 'not found', 404
    return None


def _pane_live():
    return html.Div(id='pane-live', children=[
        html.Section(className='card now', children=[
            html.Div(id='live-now'),
            html.Div(id='live-close'),
        ]),
        html.Section(className='card', children=[
            html.Div(className='card-head', children=[
                html.Div([html.H2('Price chart', className='card-title'),
                          html.Div('this bot\'s entries ▲ ▼, exits ✕ (green: won, red: lost) and the open trade\'s levels; '
                                   'hover for the details', className='card-sub')]),
                dcc.RadioItems(id='tf', options=[{'label': t, 'value': t} for t in TIMEFRAMES], value='M15',
                               className='seg', persistence=True, persistence_type='local', inline=True),
            ]),
            dcc.Graph(id='chart', config={'displaylogo': False, 'scrollZoom': True,
                                          'modeBarButtonsToRemove': ['lasso2d', 'select2d', 'autoScale2d']}),
            html.Div(id='chart-note', className='chart-note'),
        ]),
        html.Section(className='card', children=[
            html.Div(className='grid-2', children=[html.Div(id='live-gates'), html.Div(id='live-strategy')]),
        ]),
        html.Div(id='live-position'),
        html.Div(id='live-events'),
    ])


def _pane_trades():
    return html.Div(id='pane-trades', style={'display': 'none'}, children=[
        card('Summary', html.Div(id='trades-kpis'), sub='this bot\'s closed trades from the deal history (its magic number)'),
        card('Virtual balance', dcc.Graph(id='equity', config={'displayModeBar': False}, style={'height': '300px'}),
             sub='after every close (a dot per trade: green won, red lost; shaded: below the running peak); dotted: now, '
                 'with the open P/L'),
        html.Div(id='trades-list'),
    ])


def _pane_log():
    return html.Div(id='pane-log', style={'display': 'none'}, children=[
        card('Log files', html.Div([
            html.Div(id='log-files'),
            html.Div(className='dayrow', children=[
                html.Span('Days:', className='muted'),
                dcc.RadioItems(id='log-day', options=[], value=None, className='seg', inline=True),
                html.Button('Download the selected day', id='log-dl-btn', className='btn'),
                dcc.Download(id='log-dl'),
            ]),
        ]), sub='one text file per UTC day (kept 30 days) and the same lines as JSON; when something looks wrong, '
                'send the day\'s text file'),
        html.Section(className='card', children=[
            html.Div(className='logbar', children=[
                dcc.Checklist(id='log-levels', options=[{'label': lv_, 'value': lv_} for lv_ in LOG_LEVELS],
                              value=list(LOG_LEVELS), className='chk', inline=True, persistence=True,
                              persistence_type='local'),
                dcc.Input(id='log-search', type='text',
                          placeholder='search the message, category and values, then press Enter',
                          debounce=True, className='search'),
                dcc.Checklist(id='log-hb', options=[{'label': 'show heartbeats', 'value': 'hb'},
                                                    {'label': 'show start-up settings', 'value': 'cfg'}],
                              value=[], className='chk', inline=True, persistence=True, persistence_type='local'),
                dcc.RadioItems(id='log-limit', options=[{'label': str(n), 'value': n} for n in (200, 500, 2000)],
                               value=200, className='seg', inline=True, persistence=True, persistence_type='local'),
                dcc.RadioItems(id='log-view', options=[{'label': 'events', 'value': 'events'},
                                                       {'label': 'raw text', 'value': 'text'}],
                               value='events', className='seg', inline=True),
                dcc.RadioItems(id='log-follow', options=[{'label': '● live', 'value': 'live'},
                                                         {'label': 'Ⅱ paused', 'value': 'paused'}],
                               value='live', className='seg', inline=True),
            ]),
            html.Div(id='log-count', className='count'),
            html.Div(id='log-list'),
        ]),
    ])


def _pane_changes():
    return html.Div(id='pane-changes', style={'display': 'none'}, children=[
        card('Issues from the log', html.Div(id='issues-view'),
             sub='every WARN and ERROR line the bot wrote, grouped by kind: how many, the first and the last time, what '
                 'it means and what to do (click a row)'),
        card('Changes (CHANGELOG.md)', html.Div(id='changelog-view'),
             sub='what changed in this branch, version by version: the new features, the fixes and how to undo each one'),
    ])


def _pane_history():
    return html.Div(id='pane-history', style={'display': 'none'}, children=[
        card('Daily trades', html.Div([
            dcc.RadioItems(id='hist-day', options=[], value=None, className='seg', inline=True),
            html.Div(id='hist-daily', style={'marginTop': '12px'}),
        ]), sub='this bot\'s closing deals per server day (the old dashboard\'s view: daily_trade/<SYMBOL>/)'),
        card('Old strategy log', html.Div(id='hist-slog'), sub='logs/<SYMBOL>_strategy_log.json, newest first (the '
                                                               'detailed log is on the Log tab)'),
        card('Settings', html.Div(id='hist-settings'), sub='what the bot runs with; "design" marks what the branch\'s '
                                                           'design block sets'),
        card('Raw files', html.Div(id='hist-raw'), sub='what the bot wrote, as it is (click to open)'),
    ])


def serve_layout():
    syms = symbols()
    first = syms[0] if syms else ''
    return html.Div([
        dcc.Location(id='url', refresh=False),
        dcc.Interval(id='tick', interval=REFRESH_INTERVAL, n_intervals=0),
        dcc.Store(id='sig-live'), dcc.Store(id='sig-trades'), dcc.Store(id='sig-log'), dcc.Store(id='sig-hist'),
        dcc.Store(id='sig-changes'), dcc.Store(id='alert-store'), dcc.Store(id='alert-done'), dcc.Store(id='alert-perm'),
        html.Header(className='topbar', children=[html.Div(className='top-row', children=[
            html.Div(className='brand', children=[
                html.Img(src=app.get_asset_url('alcadeias.png'), alt=''),
                html.Div([html.Div('ALCADEIAS', className='brand-name'), html.Div('demo bot', className='brand-sub')]),
            ]),
            html.Div(id='status', className='status'),
        ])]),
        html.Nav(className='tabbar', children=[
            dcc.Tabs(id='tabs', value='live', children=[dcc.Tab(label=lbl, value=val, style=TAB_STYLE,
                                                               selected_style=TAB_SELECTED) for val, lbl in TABS],
                     style={'borderBottom': 'none', 'background': 'transparent'}, parent_style={'flex': '1'}),
            html.Div(className='tabbar-right', children=[
                dcc.RadioItems(id='symbol', options=[{'label': s, 'value': s} for s in syms], value=first,
                               className='seg', inline=True, style={} if len(syms) > 1 else {'display': 'none'}),
                dcc.Checklist(id='alert-opts', options=[{'label': 'sound', 'value': 'sound'},
                                                        {'label': 'browser notification', 'value': 'notify'}],
                              value=[], className='chk', inline=True, persistence=True, persistence_type='local'),
                html.Span(f'refreshes every {REFRESH_INTERVAL / 1000:g} s · times in UTC'),
            ]),
        ]),
        html.Div(id='alert-bar', className='alert-wrap'),
        html.Main(className='page', children=[_pane_live(), _pane_trades(), _pane_log(), _pane_changes(),
                                              _pane_history()]),
        html.Div('Alcadeias · reads the bot\'s output folder (OUTPUT_DIR) · never sends anything to the terminal',
                 className='footer'),
    ])


app.layout = serve_layout


# ───────────────────────────── callbacks ─────────────────────────────

def _query(search):
    out = {}
    for part in (search or '').lstrip('?').split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            out[k] = v
    return out


@app.callback(Output('tabs', 'value'), Output('tf', 'value'), Input('url', 'search'))
def _from_url(search):
    """?tab=trades&tf=M1 opens a tab / a timeframe (a bookmark, a screenshot)."""
    q = _query(search)
    tab = q.get('tab') if q.get('tab') in dict(TABS) else no_update
    tf = q.get('tf') if q.get('tf') in TIMEFRAMES else no_update
    return tab, tf


@app.callback([Output(f'pane-{k}', 'style') for k, _ in TABS], Input('tabs', 'value'))
def _show_tab(tab):
    return [{} if k == tab else {'display': 'none'} for k, _ in TABS]


def _triggered():
    try:
        return [t['prop_id'] for t in dash.callback_context.triggered]
    except Exception:
        return []


# Every callback takes the symbol (and the day) only through valid_symbol / valid_day: a request can send any value,
# and none may name a file outside the fixed names of OUTPUT_DIR.

@app.callback(Output('status', 'children'), Output('alert-bar', 'children'), Output('alert-store', 'data'),
              Input('tick', 'n_intervals'), Input('symbol', 'value'))
def _status(_n, sym):
    """The status bar and, on every tab, the banner when the open position (or a flat Turtle's entry) is close."""
    sym = valid_symbol(sym)
    d = load(sym)
    alert = alert_of(d)
    return status_bar(sym, d), alert_banner(alert), alert


# The optional sound and browser notification: in the browser only, when the alert gets worse (amber -> red, or a new
# position's alert); ticked in the tab bar, remembered by the browser.
app.clientside_callback(
    """
    function(alert, opts, done) {
        if (!alert || !alert.level || !alert.key) { return null; }
        if (done === alert.key) { return window.dash_clientside.no_update; }
        opts = opts || [];
        var red = alert.level === 'red';
        if (opts.indexOf('sound') >= 0) {
            try {
                var Ctx = window.AudioContext || window.webkitAudioContext;
                var ctx = new Ctx();
                [0, 0.25, red ? 0.5 : -1].forEach(function (at) {
                    if (at < 0) { return; }
                    var o = ctx.createOscillator(), g = ctx.createGain();
                    o.type = 'sine'; o.frequency.value = red ? 880 : 660;
                    g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
                    g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + at + 0.02);
                    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.18);
                    o.connect(g); g.connect(ctx.destination);
                    o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.2);
                });
            } catch (e) {}
        }
        if (opts.indexOf('notify') >= 0 && window.Notification && Notification.permission === 'granted') {
            try { new Notification((red ? 'Very close: ' : 'Getting close: ') + document.title, {body: alert.text}); }
            catch (e) {}
        }
        return alert.key;
    }
    """,
    Output('alert-done', 'data'), Input('alert-store', 'data'), State('alert-opts', 'value'), State('alert-done', 'data'))

app.clientside_callback(
    """
    function(opts) {
        if (opts && opts.indexOf('notify') >= 0 && window.Notification && Notification.permission === 'default') {
            try { Notification.requestPermission(); } catch (e) {}
        }
        return (window.Notification && Notification.permission) || 'none';
    }
    """,
    Output('alert-perm', 'data'), Input('alert-opts', 'value'))


@app.callback(
    Output('live-now', 'children'), Output('live-gates', 'children'), Output('live-strategy', 'children'),
    Output('chart', 'figure'), Output('chart-note', 'children'), Output('live-position', 'children'),
    Output('live-events', 'children'), Output('sig-live', 'data'), Output('live-close', 'children'),
    Input('tick', 'n_intervals'), Input('tabs', 'value'), Input('tf', 'value'), Input('symbol', 'value'),
    State('sig-live', 'data'))
def _live(_n, tab, tf, sym, prev):
    if tab != 'live':
        return [no_update] * 9
    sym = valid_symbol(sym)
    tf = tf if tf in TIMEFRAMES else 'M15'
    sig = '|'.join([sym, str(tf), file_sig(trace_path(sym), bars_path(sym), trades_path(sym), events_path(sym)),
                    str(int(_now() // 60))])
    if sig == prev and any(p.startswith('tick.') for p in _triggered()):
        return [no_update] * 9
    d = load(sym)
    if not d.get('trace'):
        msg = html.Div([
            html.Div(className='now-head', children=[html.Div(className='now-title', children=[
                html.Span('What the bot is doing now', className='eyebrow'), badge('NO DATA', 'warn')])]),
            html.P('No trace from the bot yet.', className='headline'),
            html.Div(f"{os.path.basename(trace_path(sym))} is {d.get('trace_problem')} in the bot's output folder. The "
                     f"bot writes it after every poll: start the bot (start_btcusd.bat / start_job.bat) and this page "
                     f"fills in.", className='line muted'),
        ])
        return (msg, None, None, price_figure(d, tf), chart_note(d, tf), position_view(d), latest_events(sym), sig, None)
    return (now_header(d), gates_view(d), strategy_panel(d), price_figure(d, tf), chart_note(d, tf), position_view(d),
            latest_events(sym), sig, proximity_view(d))


@app.callback(Output('trades-kpis', 'children'), Output('equity', 'figure'), Output('trades-list', 'children'),
              Output('sig-trades', 'data'),
              Input('tick', 'n_intervals'), Input('tabs', 'value'), Input('symbol', 'value'), State('sig-trades', 'data'))
def _trades(_n, tab, sym, prev):
    if tab != 'trades':
        return [no_update] * 4
    sym = valid_symbol(sym)
    # trades.json changes after every fill and close (and every minute); the open row's P/L follows every 30 s, so
    # a row opened to read its legs stays open
    sig = '|'.join([sym, file_sig(trades_path(sym)), str(int(_now() // 30))])
    if sig == prev and any(p.startswith('tick.') for p in _triggered()):
        return [no_update] * 4
    d = load(sym)
    return trades_kpis(d), equity_figure(d), trades_list(d), sig


@app.callback(Output('log-files', 'children'), Output('log-day', 'options'), Output('log-day', 'value'),
              Input('tick', 'n_intervals'), Input('tabs', 'value'), Input('symbol', 'value'), State('log-day', 'value'))
def _log_files(_n, tab, sym, day):
    if tab != 'log':
        return [no_update] * 3
    sym = valid_symbol(sym)
    today = utc(_now()).strftime('%Y-%m-%d')
    today_path = os.path.abspath(text_log_path(sym, today))      # (the path to copy: the file to send)
    files = log_files(sym)
    rows = [html.Div(className='pathbox', children=[
        html.Span("Today's text log (UTC day):", className='muted'),
        html.Code(today_path, id='log-path-today', className='path'),
        dcc.Clipboard(target_id='log-path-today', className='copy', title='copy the path'),
        html.Span(_size(os.path.getsize(today_path)) if os.path.exists(today_path) else 'not written yet today',
                  className='muted'),
    ]), html.Div(className='pathbox', style={'marginTop': '6px'}, children=[
        html.Span('The same lines as JSON:', className='muted'),
        html.Code(os.path.abspath(events_path(sym)), id='log-path-events', className='path'),
        dcc.Clipboard(target_id='log-path-events', className='copy', title='copy the path'),
        html.Span('(rotated at 10 MB into _events.1.jsonl … _events.5.jsonl)', className='muted'),
    ])]
    opts = [{'label': f'{d_} · {_size(size)}', 'value': d_} for d_, _, size in files[:30]]
    if day not in [o['value'] for o in opts]:
        day = opts[0]['value'] if opts else None
    return rows, opts, day


@app.callback(Output('log-count', 'children'), Output('log-list', 'children'), Output('sig-log', 'data'),
              Input('tick', 'n_intervals'), Input('tabs', 'value'), Input('symbol', 'value'), Input('log-levels', 'value'),
              Input('log-search', 'value'), Input('log-hb', 'value'), Input('log-limit', 'value'), Input('log-view', 'value'),
              Input('log-day', 'value'), Input('log-follow', 'value'), State('sig-log', 'data'))
def _log(_n, tab, sym, levels, search, hb, limit, view, day, follow, prev):
    """The events (or the raw text) filtered; 'paused' keeps the list as it is while new lines come in (an open
    line stays open), a filter still applies at once."""
    if tab != 'log':
        return [no_update] * 3
    if follow == 'paused' and prev and any(p.startswith('tick.') for p in _triggered()):
        return [no_update] * 3
    sym = valid_symbol(sym)
    day = valid_day(sym, day)
    today = utc(_now()).strftime('%Y-%m-%d')
    text_path = text_log_path(sym, day or today)
    levels = [x for x in levels if isinstance(x, str)] if isinstance(levels, list) else []
    hb = [x for x in hb if isinstance(x, str)] if isinstance(hb, list) else []
    search = search if isinstance(search, str) else ''
    limit = limit if limit in (200, 500, 2000) else 200
    view = 'text' if view == 'text' else 'events'
    sig = '|'.join([sym, file_sig(events_path(sym), text_path), json.dumps([levels, search, hb, limit, view, day])])
    if sig == prev and any(p.startswith('tick.') for p in _triggered()):
        return [no_update] * 3
    levels = set(levels)
    q = search.strip().lower()
    hb = set(hb)
    if view == 'text':
        lines, problem = text_tail(text_path)
        if lines is None:
            return f'The text log {_rel(text_path)} is not readable ({problem}).', None, sig
        keep = [ln for ln in lines if ln.strip() and (not q or q in ln.lower())
                and (len(ln.split(' | ', 2)) < 2 or ln.split(' | ', 2)[1].strip() in levels or ln.startswith('    '))
                and ('hb' in hb or ' | HEARTBEAT | ' not in ln) and ('cfg' in hb or ' | CONFIG | ' not in ln)]
        shown = [_scrub(ln) for ln in keep[-int(limit or 200):]]
        return (f'The last {len(shown)} of {len(keep)} matching lines of {os.path.basename(text_path)} (its newest '
                f'{_size(TEXT_TAIL_BYTES)} at most), oldest first as in the file; the level and heartbeat filters and '
                f'the search apply.'), html.Pre('\n'.join(shown), className='pre pre-log'), sig
    evs, cut, problem = read_events(sym)
    if problem:
        return f'The events file is {problem}: {_rel(events_path(sym))}', None, sig
    counts = Counter(str(e.get('level') or '').upper() for e in evs)
    keep = []
    for e in reversed(evs):
        lvl = str(e.get('level') or '').upper()
        cat = str(e.get('cat') or '')
        if lvl not in levels or (cat == 'HEARTBEAT' and 'hb' not in hb) or (cat == 'CONFIG' and 'cfg' not in hb):
            continue
        if q and q not in _ev_text(e):
            continue
        keep.append(e)
    shown = keep[:int(limit or 200)]
    items, last_day = [], None
    for e in shown:
        t = ts(e.get('t'))
        dday = utc(t).strftime('%A %d %B %Y') if t is not None else None
        if dday != last_day:
            items.append(html.Div(dday or '—', className='daysep'))
            last_day = dday
        items.append(event_row(e))
    count = (f"{len(shown)} of {len(keep)} matching events, newest first, from "
             f"{'the newest ' + _size(EVENTS_TAIL_BYTES) + ' of ' if cut else ''}{os.path.basename(events_path(sym))}: " +
             ' · '.join(f'{lv_} {counts.get(lv_, 0)}' for lv_ in LOG_LEVELS) + '. Click a line for its values.')
    return count, html.Div(items, className='evlist') if items else empty('Nothing matches.'), sig


@app.callback(Output('log-dl', 'data'), Input('log-dl-btn', 'n_clicks'), State('log-day', 'value'),
              State('symbol', 'value'), prevent_initial_call=True)
def _download(_clicks, day, sym):
    """The text log of the selected day: one of the files log_files() lists (logs/<SYMBOL>_<YYYY-MM-DD>.log), else
    nothing."""
    sym = valid_symbol(sym)
    day = valid_day(sym, day)
    path = next((p for d_, p, _ in log_files(sym) if d_ == day), None) if day else None
    if path is None:
        return no_update
    return dcc.send_file(path)


@app.callback(Output('issues-view', 'children'), Output('changelog-view', 'children'), Output('sig-changes', 'data'),
              Input('tick', 'n_intervals'), Input('tabs', 'value'), Input('symbol', 'value'), State('sig-changes', 'data'))
def _changes(_n, tab, sym, prev):
    if tab != 'changes':
        return [no_update] * 3
    sym = valid_symbol(sym)
    sig = '|'.join([sym, file_sig(events_path(sym), os.path.join(HERE, 'CHANGELOG.md')), str(int(_now() // 60))])
    if sig == prev and any(p.startswith('tick.') for p in _triggered()):
        return [no_update] * 3
    return issues_view(sym), changelog_view(), sig


@app.callback(Output('hist-day', 'options'), Output('hist-day', 'value'), Output('hist-daily', 'children'),
              Output('hist-slog', 'children'), Output('hist-settings', 'children'), Output('hist-raw', 'children'),
              Output('sig-hist', 'data'),
              Input('tick', 'n_intervals'), Input('tabs', 'value'), Input('symbol', 'value'), Input('hist-day', 'value'),
              State('sig-hist', 'data'))
def _history(_n, tab, sym, day, prev):
    if tab != 'history':
        return [no_update] * 7
    sym = valid_symbol(sym)
    files = daily_files(sym)
    days = sorted(files, reverse=True)[:14]
    if day not in days:
        day = days[0] if days else None
    sig = '|'.join([sym, str(day), file_sig(*(files[k] for k in days[:1]), _path('logs', f'{sym}_{STRATEGY_LOG_FILENAME}')),
                    str(int(_now() // 60))])
    if sig == prev and any(p.startswith('tick.') for p in _triggered()):
        return [no_update] * 7
    opts = [{'label': k, 'value': k} for k in days]
    daily = history_daily(sym, day) if day else empty('No daily-trade file yet.')
    return opts, day, daily, history_strategy_log(sym), settings_view(sym, load(sym)), raw_view(sym), sig


if __name__ == '__main__':
    print(f"Alcadeias dashboard of {getattr(_C, 'DEMO_BRANCH', None) or 'this bot'}: http://localhost:{DASHBOARD_PORT} "
          f"(reads {os.path.abspath(JSON_DIR)})", flush=True)
    app.run(debug=False, host=DASHBOARD_HOST, port=DASHBOARD_PORT)
