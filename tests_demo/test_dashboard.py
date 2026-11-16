"""
The dashboard (dashboard.py) on the files the bot writes (docs/dashboard-data.md).

A basket replay (the scaled design: entries, a one-unit add, stops, a target, the loss pause) and, on a branch with
the Turtle, the Turtle's long trip (a breakout BUY, three adds, the one stop) run with the real writers; their output
folders, taken in an open position and at the end, are what the dashboard reads. Every view of every tab is built
from them without an error card and shows what the bot wrote: the headline, every check in the bot's order, the
votes and scores (basket) or N, the channels, today's levels, the vote of the closed M15 bar (Turtle), the chart's
entries, exits and the open trade's levels on a UTC time axis, the trades, the log with its filters, the old views
and the settings the bot started with. A folder that is empty, files that are cut or hold nulls, a stale trace and a
refused account are shown, never raised. The dashboard only reads files: it never imports the terminal's package,
and no request -- to the callbacks or over HTTP -- reads a file outside its fixed list in OUTPUT_DIR.
"""
import base64
import copy
import json
import math
import os
import re
import shutil
import sys
import threading
import types
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

from conftest import MAGIC, ROOT, SCALED, START, market, run_bot

pytest.importorskip('dash')
plotly = pytest.importorskip('plotly')

BASKET = 'XAUUSDm'
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
ERROR_CARD = ('could not be shown', 'could not be drawn')
HAS_TURTLE = (ROOT / 'turtle.py').exists()


@pytest.fixture(scope='module')
def D():
    """dashboard.py imported from this branch (its constants.py), put back as it was afterwards."""
    names = ('constants', 'dashboard')
    saved = {n: sys.modules.get(n) for n in names}
    sys.path.insert(0, str(ROOT))
    try:
        for n in names:
            sys.modules.pop(n, None)
        import dashboard
        yield dashboard
    finally:
        sys.path.remove(str(ROOT))
        for n in names:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


def _snapshotting(out, when, dst):
    """on_new_bot hook: copy the output folder once, at the first poll whose trace satisfies when(trace)."""
    done = []

    def on_new_bot(bot, n):
        real = bot._trace

        def spy(symbol, method, *a, **k):
            real(symbol, method, *a, **k)
            if method != 'poll' or done:
                return
            try:
                with open(os.path.join(out, f'{symbol}_trace.json'), encoding='utf-8') as f:
                    tr = json.load(f)
            except (OSError, ValueError):
                return
            if when(tr):
                shutil.copytree(out, dst)
                done.append(tr['t'])
        bot._trace = spy
    return on_new_bot, done


@pytest.fixture(scope='module')
def basket(tmp_path_factory):
    """The scaled design's replay (seed 4, 20 minutes): its folder with a basket open (an add armed or made) and
    at the end."""
    tmp = tmp_path_factory.mktemp('dash_basket')
    out, open_dir = str(tmp / 'out'), str(tmp / 'open')
    fake, clock = market(1200, seed=4)
    hook, done = _snapshotting(out, lambda tr: g_open(tr) and len(g_open(tr).get('legs') or []) == 2, open_dir)
    run = run_bot(fake, clock, overrides={**SCALED, 'OUTPUT_DIR': out}, state_dir=os.path.join(out, 'state'),
                  keep_writers=True, on_new_bot=hook)
    assert not run.errors, run.errors[:3]
    assert done, 'no two-leg basket in the replay'
    return types.SimpleNamespace(end=out, open=open_dir)


def g_open(tr):
    return ((tr.get('basket') or {}).get('open')) if isinstance(tr, dict) else None


@pytest.fixture(scope='module')
def turtle(tmp_path_factory):
    """The Turtle's long trip (test_turtle_bot.py): its folder with three legs open and at the end (flat, the trade
    closed at the stop)."""
    if not HAS_TURTLE:
        pytest.skip('no turtle.py on this branch')
    import test_turtle_bot as TB
    tmp = tmp_path_factory.mktemp('dash_turtle')
    out, open_dir = str(tmp / 'out'), str(tmp / 'open')
    fake, clock = TB._market(TB._long_trip())
    snap, done = _snapshotting(out, lambda tr: len(((tr.get('turtle') or {}).get('trade') or {}).get('legs') or []) == 3,
                               open_dir)
    vote = TB.Vote(fake, lambda t: 1)

    def on_new_bot(bot, n):
        sys.modules[type(bot).__module__].T.closed_bar_vote = vote
        snap(bot, n)
    run = run_bot(fake, clock, overrides={**TB.TURTLE, 'OUTPUT_DIR': out}, symbol=TB.SYMBOL,
                  state_dir=os.path.join(out, 'state'), keep_writers=True, on_new_bot=on_new_bot)
    assert not run.errors, run.errors[:3]
    assert done, 'no three-leg trade in the replay'
    return types.SimpleNamespace(end=out, open=open_dir, symbol=TB.SYMBOL)


def _text(obj):
    """Everything a component tree / figure would send to the browser, as one text."""
    return json.dumps(obj, cls=plotly.utils.PlotlyJSONEncoder)


def _point(D, folder, symbol, age=2.0):
    """Point the dashboard at a folder; its clock just after the trace was written."""
    D.JSON_DIR = folder
    D._CACHE.clear()
    D._EVENTS_CACHE.clear()
    try:
        with open(os.path.join(folder, f'{symbol}_trace.json'), encoding='utf-8') as f:
            t = float(json.load(f)['t'])
    except (OSError, ValueError, KeyError, TypeError):
        t = START + 600
    D._now = lambda: t + age
    return D.load(symbol)


def _every_view(D, symbol, d):
    """{name: what the view sends to the browser} of every tab."""
    live = D._live(0, 'live', 'M1', symbol, None)
    out = {'status': D.status_bar(symbol, d), 'now': live[0], 'gates': live[1], 'strategy': live[2], 'chart': live[3],
           'note': live[4], 'position': live[5], 'events': live[6]}
    for tf in D.TIMEFRAMES:
        out[f'chart_{tf}'] = D.price_figure(d, tf)
    out['kpis'], out['equity'], out['trades'], _ = D._trades(0, 'trades', symbol, None)
    files = D._log_files(0, 'log', symbol, None)
    out['log_files'] = files
    out['log'] = D._log(0, 'log', symbol, list(D.LOG_LEVELS), '', [], 200, 'events', files[2], 'live', None)
    out['log_text'] = D._log(0, 'log', symbol, list(D.LOG_LEVELS), '', ['hb', 'cfg'], 200, 'text', files[2], 'live', None)
    out['history'] = D._history(0, 'history', symbol, None, None)
    return out


def _no_error_card(views):
    for name, v in views.items():
        text = _text(v)
        for bad in ERROR_CARD:
            assert bad not in text, (name, text[text.find('Traceback'):][:1500])


# ───────────────────────────── the dashboard only reads files ─────────────────────────────

def test_the_dashboard_only_reads_files(D):
    src = (ROOT / 'dashboard.py').read_text(encoding='utf-8')
    assert 'MetaTrader5' not in src and 'mt5_helper' not in src and 'order_send' not in src
    assert 'MetaTrader5' not in getattr(D, '__dict__', {})
    # the old imports from constants by name, as before
    head = src[src.index('from constants import ('):src.index(')', src.index('from constants import ('))]
    for name in ('OUTPUT_DIR', 'DAILY_TRADE_SUBDIR', 'DASHBOARD_REFRESH_INTERVAL', 'DASHBOARD_HOST', 'DASHBOARD_PORT',
                 'HISTORICAL_SUMMARY_FILENAME', 'GRAPH_TEXT_LABEL_THRESHOLD', 'GRAPH_CUM_LABEL_THRESHOLD',
                 'STRATEGY_LOG_FILENAME', 'ACTIVE_CONFIG_FILENAME', 'ENTRY_S', 'ENTRY_AGREE_S', 'FORCE_CLOSE_S',
                 'OPEN_SCORE_WEIGHTS', 'FORCE_CLOSE_SCORE_WEIGHTS'):
        assert name in head, name
        assert getattr(D, name) == getattr(sys.modules['constants'], name)
    assert D.REFRESH_INTERVAL == D.DASHBOARD_REFRESH_INTERVAL
    # the page: four tabs, the refresh at DASHBOARD_REFRESH_INTERVAL, no MT5 call anywhere
    layout = _text(D.serve_layout())
    for tab in ('"Live"', '"Trades"', '"Log"', '"History & settings"'):
        assert tab in layout
    assert f'"interval": {D.DASHBOARD_REFRESH_INTERVAL}' in layout
    # the Log tab's search applies when Enter is pressed (one request, not one per key): its box says so
    assert 'search the message, category and values, then press Enter' in layout


def test_the_dashboard_launcher_installs_the_pinned_dash_and_prints_no_wrong_address():
    """start_dashboard.bat installs the versions requirements.txt pins (an unpinned install could bring Dash 3 or
    plotly 6) and prints no address of its own: dashboard.py prints the real one (DASHBOARD_PORT)."""
    bat = (ROOT / 'start_dashboard.bat').read_text(encoding='utf-8')
    pins = dict(ln.strip().split('==', 1) for ln in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
                if '==' in ln)
    assert f"dash=={pins['dash']}" in bat and f"plotly=={pins['plotly']}" in bat, bat
    assert not re.search(r'pip install dash plotly\s*$', bat, flags=re.M) and 'localhost:8050' not in bat
    src = (ROOT / 'dashboard.py').read_text(encoding='utf-8')
    assert 'http://localhost:{DASHBOARD_PORT}' in src


# ───────────────────────────── the basket strategy ─────────────────────────────

def test_every_tab_draws_a_basket_bot(D, basket):
    for folder in (basket.open, basket.end):
        d = _point(D, folder, BASKET)
        views = _every_view(D, BASKET, d)
        _no_error_card(views)
        tr = d['trace']
        dec = tr['decision']
        assert tr['strategy'] == 'basket'
        assert dec['headline'] in _text(views['now'])
        gates = _text(views['gates'])
        for gt in dec['gates']:
            assert json.dumps(gt['name'])[1:-1] in gates, gt['name']
        status = _text(views['status'])
        for bit in (tr['branch'], f"{MAGIC:,}", 'Demo account', 'Updated 2 s ago', 'Virtual balance'):
            assert bit in status, bit
        strategy = _text(views['strategy'])
        for bit in ('Open score', 'Agreement score', 'Votes per timeframe', 'M1', 'M5 trend', 'M1 volatility unit',
                    'Entry pause', 'A basket opened now would get',
                    'force-close is off in this design: these votes only gate entries'):
            assert bit in strategy, bit


def test_the_open_basket_and_its_levels_on_the_chart(D, basket):
    d = _point(D, basket.open, BASKET)
    op = d['trace']['basket']['open']
    digits = D.digits_of(d)
    pos = _text(D.position_view(d))
    assert 'Open basket' in pos and D.px(op['stop_price'], digits) in pos and D.px(op['target_price'], digits) in pos
    for lg in op['legs']:
        assert D.px(lg['price'], digits) in pos
    fig = D.price_figure(d, 'M1')
    tags = [a.text.split(' · ')[0] for a in fig.layout.annotations]          # (the distance to go after ' · ')
    on = ' (ask)' if op['judged_on'] == 'ask' else ''                    # a sell's stop / target are judged on the ask
    for name, price in ((f'TARGET{on}', op['target_price']), (f'STOP{on}', op['stop_price']),
                        ('BID', d['trace']['market']['bid']), ('ASK', d['trace']['market']['ask'])):
        assert any(t.endswith(f'{name} {D.px(price, digits)}') for t in tags), (name, tags)
    assert any('BACKSTOP' in t for t in tags)
    names = {tr.name for tr in fig.data}
    assert {'open legs', 'M1 bars (bid)'} <= names
    # the time axis is UTC wall-clock time (a number would be shown in the browser's own time zone)
    bars = d['bars']['tf']['M1']
    candles = next(tr for tr in fig.data if tr.type == 'candlestick')
    assert candles.x[0] == datetime.fromtimestamp(bars['t'][0], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S.000')
    # the price tags never overlap: at least 17 px apart
    y0, y1 = fig.layout.yaxis.range
    per_px = (y1 - y0) / (600 - 72)
    ys = sorted(a.y for a in fig.layout.annotations)
    assert all(b - a >= 17 * per_px for a, b in zip(ys, ys[1:]))


def test_the_closed_baskets_on_the_chart_and_in_the_trades_tab(D, basket):
    d = _point(D, basket.end, BASKET)
    closed = d['trades']['closed']
    assert len(closed) >= 2
    fig = D.price_figure(d, 'M1')
    entries = sum(len(tr.x) for tr in fig.data if tr.name in ('buy entries', 'sell entries'))
    exits = sum(len(tr.x) for tr in fig.data if tr.name in ('exits (won)', 'exits (lost)'))
    assert entries == sum(len(c['legs']) for c in closed) and exits == len(closed)
    hover = _text(fig)
    for c in closed:
        assert (c.get('exit_reason_text') or c['exit_reason']) in hover
    kpis, equity, trades, _ = D._trades(0, 'trades', BASKET, None)
    text = _text(trades)
    assert f"{len(closed)} closed trade(s)" in text
    for c in closed:
        assert D.money(c['pnl'], signed=True) in text and D.money(c['balance_after']) in text
    s = d['trades']['summary']
    k = _text(kpis)
    assert D.money(s['net'], signed=True) in k and D.money(s['worst'], signed=True) in k
    assert len(next(tr for tr in equity.data if tr.name == 'virtual balance').y) == len(d['trades']['balance_curve'])


def test_the_log_tab_filters_and_finds(D, basket):
    _point(D, basket.end, BASKET)
    files, opts, day = D._log_files(0, 'log', BASKET, None)
    assert day == DAY and opts[0]['value'] == DAY
    assert json.dumps(os.path.join('logs', f'{BASKET}_{DAY}.log'))[1:-1] in _text(files)
    count, rows, _ = D._log(0, 'log', BASKET, ['ORDER'], '', [], 2000, 'events', day, 'live', None)
    levels = re.findall(r'"lvl lvl-(\w+)"', _text(rows))
    assert levels and set(levels) == {'order'}
    count, rows, _ = D._log(0, 'log', BASKET, list(D.LOG_LEVELS), 'stop', [], 2000, 'events', day, 'live', None)
    assert 'stop' in _text(rows).lower() and 'HEARTBEAT' not in _text(rows)
    count, rows, _ = D._log(0, 'log', BASKET, list(D.LOG_LEVELS), '', ['hb'], 2000, 'events', day, 'live', None)
    assert 'HEARTBEAT' in _text(rows)
    count, rows, _ = D._log(0, 'log', BASKET, ['CLOSE'], '', [], 200, 'text', day, 'live', None)
    lines = [ln for ln in rows.children.split('\n') if ln]
    assert lines and all(' | CLOSE | ' in ln for ln in lines)
    sent = D._download(1, day, BASKET)
    assert sent['filename'] == f'{BASKET}_{DAY}.log'


def test_the_settings_are_those_the_bot_started_with(D, basket):
    d = _point(D, basket.end, BASKET)
    text = _text(D.settings_view(BASKET, d))
    assert 'as the bot logged them when it started' in text
    assert 'scaled_test' in text                                # the replay's design, not constants.py's
    assert 'constants.py now' in text                           # ... which constants.py does not have


# ───────────────────────────── the Turtle ─────────────────────────────

def test_every_tab_draws_a_turtle_bot(D, turtle):
    for folder in (turtle.open, turtle.end):
        d = _point(D, folder, turtle.symbol)
        views = _every_view(D, turtle.symbol, d)
        _no_error_card(views)
        tr = d['trace']
        assert tr['strategy'] == 'turtle'
        assert tr['decision']['headline'] in _text(views['now'])
        strategy = _text(views['strategy'])
        for bit in ("Today's entry orders", 'N (20-day ATR)', 'Stop distance 2N', 'Add step 0.5N',
                    'M15 vote of the last closed bar', 'The D1 channels', '55-day', '20-day', '10-day'):
            assert bit in strategy, bit
        assert D.px(tr['turtle']['levels']['buy'], D.digits_of(d)) in strategy


def test_the_open_turtle_trade_its_stop_moves_and_levels(D, turtle):
    d = _point(D, turtle.open, turtle.symbol)
    trd = d['trace']['turtle']['trade']
    digits = D.digits_of(d)
    pos = _text(D.position_view(d))
    for bit in ('Open Turtle trade', '3/4 legs', 'Every stop move', D.px(trd['stop'], digits),
                D.px(trd['next_add'], digits)):
        assert bit in pos, bit
    fig = D.price_figure(d, 'M1')                               # M1: every stop move in a bar of its own
    tags = ' / '.join(a.text for a in fig.layout.annotations)
    for name in ('STOP', 'NEXT ADD', 'BUY LEVEL', 'BACKSTOP'):
        assert name in tags, (name, tags)
    stop = next(tr for tr in fig.data if tr.name == 'stop (as it moved)')
    assert list(stop.y)[-1] == pytest.approx(trd['stop'])
    # a step per stop move of the journal, ending at the stop in force (the journal notes a move on the poll after
    # the fill that made it)
    assert set(stop.y) == {s['stop'] for s in trd['journal']['stops']} | {trd['stop']}


def test_the_closed_turtle_trade_with_its_journal(D, turtle):
    d = _point(D, turtle.end, turtle.symbol)
    closed = d['trades']['closed']
    assert len(closed) == 1 and closed[0]['exit_reason'] == 'turtle_stop'
    text = _text(D.trades_list(d))
    for bit in ('turtle stop', 'Legs and their add levels', 'Stop moves', 'N at the entry'):
        assert bit in text, bit
    d1 = D.price_figure(d, 'D1')
    assert {'buy level', 'sell level'} <= {tr.name for tr in d1.data}     # the channels as steps on D1
    # on D1 the stop's moves of one day are one bar: the stop is a plain line there, no steps
    d_open = _point(D, turtle.open, turtle.symbol)
    assert 'stop (as it moved)' not in {tr.name for tr in D.price_figure(d_open, 'D1').data}


# ───────────────────────────── files that are missing, cut or odd; the bot's state ─────────────────────────────

def test_an_empty_folder_and_broken_files_are_shown_not_raised(D, tmp_path, basket):
    empty_dir = str(tmp_path / 'empty')
    os.makedirs(empty_dir)
    d = _point(D, empty_dir, BASKET)
    views = _every_view(D, BASKET, d)
    _no_error_card(views)
    assert 'No trace from the bot yet' in _text(views['now'])
    assert 'No trace file' in _text(views['status'])
    # files cut in the middle of a write, or not JSON at all
    cut = str(tmp_path / 'cut')
    shutil.copytree(basket.open, cut)
    for name in (f'{BASKET}_trace.json', f'{BASKET}_bars.json', f'{BASKET}_trades.json'):
        p = os.path.join(cut, name)
        with open(p, encoding='utf-8') as f:
            raw = f.read()
        with open(p, 'w', encoding='utf-8') as f:
            f.write(raw[:len(raw) // 2])
    with open(os.path.join(cut, 'logs', f'{BASKET}_events.jsonl'), 'a', encoding='utf-8') as f:
        f.write('{"t": 1, "level": "INFO", "msg": "cut in the mid')
    _no_error_card(_every_view(D, BASKET, _point(D, cut, BASKET)))


def _nulls(o):
    """The same structure with every leaf None (a list keeps one None element)."""
    if isinstance(o, dict):
        return {k: _nulls(v) for k, v in o.items()}
    if isinstance(o, list):
        return [None] if o else []
    return None


def test_every_field_may_be_null(D, tmp_path, basket):
    for kind in ('leaves', 'sections'):
        folder = str(tmp_path / kind)
        shutil.copytree(basket.open, folder)
        for name in (f'{BASKET}_trace.json', f'{BASKET}_trades.json', f'{BASKET}_bars.json'):
            p = os.path.join(folder, name)
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            if kind == 'leaves':
                data = _nulls(data)
            else:
                data = {k: (None if isinstance(v, (dict, list)) else v) for k, v in data.items()}
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        _no_error_card(_every_view(D, BASKET, _point(D, folder, BASKET)))


def test_a_skipped_poll_a_refused_account_and_errors_are_shown(D, tmp_path, basket):
    """A poll that could not read the terminal (the trace is fresh: the bot writes it): the refused account, the lost
    terminal and the errors in red, the market unknown (not 'closed'), the votes kept from the last poll. Five
    minutes later the same trace is stale: only its age is red, the other chips are neutral with the time of the trace,
    and the errors are counted from the log (it has none here), not from the trace."""
    folder = str(tmp_path / 'state')
    shutil.copytree(basket.end, folder)
    p = os.path.join(folder, f'{BASKET}_trace.json')
    with open(p, encoding='utf-8') as f:
        tr = json.load(f)
    tr['health'].update(account_ok=False, account_problem='the terminal is logged into account 7, not the demo login 1',
                        errors_1h=3, connected=False, terminal_problem='terminal_info() is None', market_live=None)
    tr['stale'], tr['stale_since_utc'] = True, tr['time_utc']
    tr['market'].update(status='UNKNOWN')        # (what a skipped poll writes: the last market, marked unknown)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(tr, f)
    d = _point(D, folder, BASKET, age=2.0)
    status = _text(D.status_bar(BASKET, d))
    for bit in ('Updated 2 s ago', 'Account refused: the terminal is logged into account 7', '3 error(s) in the last hour',
                'Terminal: terminal_info() is None', 'Last poll could not read the terminal',
                'Market: unknown (terminal not read)'):
        assert bit in status, bit
    assert 'Market closed' not in status
    assert 'the account, market and position numbers below are those of the last good poll' in _text(D.now_header(d))
    assert 'votes kept from the last poll' in _text(D.strategy_panel(d))
    d = _point(D, folder, BASKET, age=300.0)
    status = _text(D.status_bar(BASKET, d))
    hhmm = datetime.fromtimestamp(tr['t'], tz=timezone.utc).strftime('%H:%M')
    assert 'Stale: last update 5.0 min ago' in status and status.count('"chip chip-neg"') == 1
    assert f'Account refused: the terminal is logged into account 7, not the demo login 1 (as of {hhmm})' in status
    assert 'No error logged in the last hour' in status and '3 error(s)' not in status
    assert D.freshness({'t': START})[0] == 'neg'


def test_a_trace_the_bot_stopped_writing_shows_its_last_poll_not_now(D, tmp_path, basket):
    """The bot stopped writing two hours ago (killed, the PC asleep, or its loop failing before the trace hook): the
    age chip is red; no chip is green -- the account, terminal and market chips are neutral with the time of the trace,
    the market chip counts the last tick's age now; the errors come from the log, which kept getting ERROR lines; a
    banner says the page is the last poll; the strategy, the checks, the position and the uptime say so too."""
    folder = str(tmp_path / 'stopped')
    shutil.copytree(basket.open, folder)
    with open(os.path.join(folder, f'{BASKET}_trace.json'), encoding='utf-8') as f:
        tr = json.load(f)
    now = tr['t'] + 7200.0
    with open(os.path.join(folder, 'logs', f'{BASKET}_events.jsonl'), 'a', encoding='utf-8') as f:
        for k in (20, 10):              # the loop failing after its last trace: ERROR lines in the last hour
            f.write(json.dumps({'t': now - 60 * k, 'level': 'ERROR', 'cat': 'LOOP', 'msg': 'the poll failed: boom'}) + '\n')
    d = _point(D, folder, BASKET, age=7200.0)
    status = _text(D.status_bar(BASKET, d))
    hhmm = datetime.fromtimestamp(tr['t'], tz=timezone.utc).strftime('%H:%M')
    assert 'Stale: last update 2.0 h ago' in status
    assert '"chip chip-pos"' not in status                                  # nothing the trace holds is now's
    assert json.dumps(f"Demo account {tr['health']['login']:,} · hedging (as of {hhmm})")[1:-1] in status
    assert f'Terminal connected (as of {hhmm})' in status
    assert f'Market: last tick 2.0 h ago (as of {hhmm})' in status
    assert '2 error(s) in the last hour' in status                         # from the log, not the frozen trace
    assert 'not writing' in status and f'no trace since {hhmm}' in status
    now_ = _text(D.now_header(d))
    assert 'The bot has not written since' in now_ and 'Everything below is its last poll, not now' in now_
    assert 'What the bot was doing at its last poll' in now_
    assert f'votes of its last poll (as of {hhmm})' in _text(D.strategy_panel(d))
    assert f'checks its last poll (as of {hhmm})' in _text(D.gates_view(d))
    assert f'Open basket (as of {hhmm})' in _text(D.position_view(d))
    # a PC whose clock is behind the bot's: no negative age shown as hours ago; the bot's own tick age
    d = _point(D, folder, BASKET, age=-7200.0)
    status = _text(D.status_bar(BASKET, d))
    assert 'the clock of this PC is behind' in status and 'last tick 2.0 h ago' not in status
    assert f"last tick {D.dur(tr['health']['last_tick_age_s'])} ago" in status


def test_a_missing_or_old_trades_file_is_said(D, tmp_path, basket):
    """trades.json missing (before the first deal-history read, or a write that failed): the Trades tab, the equity
    chart, the position card and the chart note say so -- never 'No trade yet'. An old one (the history not read for 3
    hours) is shown with its time and a warning."""
    folder = str(tmp_path / 'no_trades')
    shutil.copytree(basket.end, folder)
    os.remove(os.path.join(folder, f'{BASKET}_trades.json'))
    d = _point(D, folder, BASKET)
    kpis, equity, trades, _ = D._trades(0, 'trades', BASKET, None)
    text = _text([kpis, equity, trades])
    assert f'{BASKET}_trades.json is missing' in text and 'the closed trades are not known' in text
    assert 'No trade yet' not in text and 'No closed trade yet' not in text and 'No balance curve' in text
    assert 'Closed trades' not in _text(kpis)                     # no summary of zeros: they would read as no trade
    flat = copy.deepcopy(d)
    flat['trace']['basket']['open'] = None
    assert 'The last closed trade is not known' in _text(D.position_view(flat))
    assert 'No past entries or exits' in _text(D.chart_note(d, 'M1'))
    with open(os.path.join(basket.end, f'{BASKET}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    doc['t'] = d['trace']['t'] - 3 * 3600
    with open(os.path.join(folder, f'{BASKET}_trades.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f)
    _point(D, folder, BASKET)
    text = _text(D._trades(0, 'trades', BASKET, None)[:3])
    assert f'{BASKET}_trades.json was last written' in text and '(3.0 h ago)' in text
    assert 'the closed trades below are as of then' in text and f"{len(doc['closed'])} closed trade(s)" in text


def test_a_close_is_shown_with_the_side_of_its_position(D):
    """A SELL position is closed with a BUY order: the order list names the position's side (and the order's)."""
    o = {'kind': 'close', 'side': 'SELL', 'order_side': 'BUY', 'volume': 0.01, 'position': 100001, 'done': True,
         'retcode': 10009, 'retcode_text': 'done', 'price': 1781.644, 'result_price': 1781.644}
    assert 'CLOSE SELL position 100001 (BUY order, 0.01 lot)' in _text(D.order_line(o, 3))
    assert 'retcode 10009' in _text(D.order_line(o, 3))           # a code, not an amount (no thousands comma)
    old = {k: v for k, v in o.items() if k != 'order_side'}
    old['side'] = 'BUY'                          # a trace written before the fix: only the order's own side
    assert 'CLOSE SELL position 100001 (BUY order, 0.01 lot)' in _text(D.order_line(old, 3))
    add = dict(o, kind='add', side='BUY', order_side='BUY', position=None, volume=0.02)
    assert 'ADD BUY 0.02 lot' in _text(D.order_line(add, 3))


def _tag_names(fig):
    """{tag name: the annotation} of a price chart: 'STOP (ask)', 'BID', 'BUY LEVEL' ... (no arrow, no price)."""
    out = {}
    for a in fig.layout.annotations:
        head = a.text.split('<br>')[0].split(' · ')[0].lstrip('▲▼ ')
        out[re.sub(r' -?[\d,]+(\.\d+)?$', '', head)] = a
    return out


def test_levels_judged_on_the_ask_say_so_and_the_ask_is_drawn(D, basket):
    """The candles are bid prices. A sell basket's stop, target and broker stops are hit by the ask, a buy basket's next
    add is bought at the ask: their tags say '(ask)', and the ASK line is drawn next to the BID line."""
    d = _point(D, basket.open, BASKET)
    digits = D.digits_of(d)
    mk = d['trace']['market']
    for side, judged, add_on in (('SELL', 'ask', 'bid'), ('BUY', 'bid', 'ask')):
        dd = copy.deepcopy(d)
        op = dd['trace']['basket']['open']
        op.update(side=side, judged_on=judged)
        op['ladder'] = dict(op.get('ladder') or {}, on=True, exhausted=False, judged_on=add_on, tier_tf='M1',
                            next_add_price=round(mk['bid'] + (1.0 if side == 'SELL' else -1.0), digits))
        tags = _tag_names(D.price_figure(dd, 'M1'))
        want = {'TARGET', 'STOP', 'BACKSTOP'} if side == 'BUY' else {'TARGET (ask)', 'STOP (ask)', 'BACKSTOP (ask)'}
        want |= {'NEXT ADD (ask)' if side == 'BUY' else 'NEXT ADD', 'AVG', 'BID', 'ASK'}
        assert want <= set(tags), (side, sorted(tags))
        assert tags['ASK'].text.endswith(D.px(mk['ask'], digits)) and tags['BID'].text.endswith(D.px(mk['bid'], digits))
        assert 'judged on the ask' in (tags.get('STOP (ask)') or tags['STOP']).hovertext or side == 'BUY'
    assert 'ASK line' in _text(D.chart_note(d, 'M1')) and "'(ask)'" in _text(D.chart_note(d, 'M1'))


def _turtle_d(orders_state, trade_side=None):
    """A Turtle trace and its bars, made by hand (any branch): an hour of M1 and 30 D1 bars, today's levels, the
    day's orders in `orders_state`, a trade of `trade_side` or none."""
    m1_t = [START - 3600 + 60 * i for i in range(60)]
    m1_c = [60000.0 + 30.0 * math.sin(i / 6.0) for i in range(60)]
    d1_t = [START - 86400 * (30 - i) for i in range(30)]
    d1_c = [59000.0 + 40.0 * i for i in range(30)]

    def cols(t, c):
        return {'t': t, 'o': c, 'h': [x + 40 for x in c], 'l': [x - 40 for x in c], 'c': c}
    midnight = (int(START) // 86400 + 1) * 86400
    bars = {'digits': 2, 'tf': {'M1': cols(m1_t, m1_c), 'D1': cols(d1_t, d1_c)},
            'overlay': {'turtle': {'from_t': [t + 86400 for t in d1_t], 'buy': [x + 300 for x in d1_c],
                                   'sell': [x - 300 for x in d1_c], 'exit_long': [x - 150 for x in d1_c],
                                   'exit_short': [x + 150 for x in d1_c]}}}
    lv = {'ok': True, 'buy': 60110.0, 'sell': 59890.0, 'from_time': midnight - 86400, 'trail_long': 59950.0,
          'trail_short': 60050.0, 'n': 400.0}
    orders = {'state': orders_state, 'armed': orders_state == 'armed', 'until_t': midnight,
              'used_by': 'BUY' if orders_state == 'used' else None,
              'buy': {'level': lv['buy'], 'judged_on': 'ask', 'price_now': m1_c[-1] + 15.0, 'distance': -10.0,
                      'reached': True, 'vote_needed': 1},
              'sell': {'level': lv['sell'], 'judged_on': 'bid', 'price_now': m1_c[-1], 'distance': 100.0,
                       'reached': False, 'vote_needed': -1}}
    trade = None
    if trade_side:
        buy = trade_side == 'BUY'
        fill = 60112.0 if buy else 59888.0
        trade = {'side': trade_side, 'legs': [{'n': 1, 'ticket': 7, 'open_t': START - 1200, 'price': fill, 'lots': 0.01}],
                 'legs_count': 1, 'max_legs': 4, 'entry_t': START - 1200, 'avg_price': fill, 'pnl': 1.0,
                 'stop': fill - 800 if buy else fill + 800, 'next_add': fill + 200 if buy else fill - 200,
                 'judged_on': 'bid' if buy else 'ask', 'next_add_judged_on': 'ask' if buy else 'bid',
                 'backstop_prices': [fill - 1200 if buy else fill + 1200], 'price_now': m1_c[-1]}
    tr = {'strategy': 'turtle', 't': START + 1.0,
          'market': {'bid': m1_c[-1], 'ask': m1_c[-1] + 15.0, 'spread': 15.0, 'tick_t': START + 0.5, 'digits': 2},
          'turtle': {'levels': lv, 'orders': orders, 'trade': trade,
                     'channels': {'entry': {'days': 55}, 'exit': {'days': 20}}}}
    return {'symbol': 'BTCUSDm', 'trace': tr, 'bars': bars, 'trades': {'closed': []}}


def test_the_turtles_levels_are_entry_triggers_only_while_its_orders_are_armed(D):
    """Today's BUY / SELL LEVEL is an entry trigger only while the day's orders are armed and no trade is open. Used, or
    with a trade open, they are drawn muted, their tag saying why (on M1 and on D1). A short's stop and broker stop are
    hit by the ask, a long's next add is bought at the ask: their tags say '(ask)'."""
    D._now = lambda: START + 2.0
    tags = _tag_names(D.price_figure(_turtle_d('armed'), 'M1'))
    assert {'BUY LEVEL (ask)', 'SELL LEVEL', 'BID', 'ASK'} <= set(tags), sorted(tags)
    assert tags['BUY LEVEL (ask)'].bordercolor == D.COL['blue'] and '<br>' not in tags['BUY LEVEL (ask)'].text
    assert 'an entry when the ask reaches it' in tags['BUY LEVEL (ask)'].hovertext
    for state, side, note in (('used', None, 'used, new orders at 00:00'), ('armed', 'BUY', 'no entry while in a trade'),
                              ('used', 'SELL', 'no entry while in a trade')):
        for tf in ('M1', 'D1'):
            tags = _tag_names(D.price_figure(_turtle_d(state, side), tf))
            for name in ('BUY LEVEL (ask)', 'SELL LEVEL'):
                a = tags[name]
                assert a.bordercolor == D.COL['faint'] and a.text.endswith(f'>{note}</span>'), (state, side, tf, a.text)
                assert 'not an entry now' in a.hovertext, a.hovertext
    tags = _tag_names(D.price_figure(_turtle_d('used', 'SELL'), 'M1'))
    assert {'STOP (ask)', 'BACKSTOP (ask)', 'NEXT ADD', 'AVG'} <= set(tags), sorted(tags)
    tags = _tag_names(D.price_figure(_turtle_d('used', 'BUY'), 'M1'))
    assert {'STOP', 'BACKSTOP', 'NEXT ADD (ask)'} <= set(tags), sorted(tags)
    # the right margin holds the widest tag
    fig = D.price_figure(_turtle_d('used', 'BUY'), 'M1')
    assert fig.layout.margin.r >= 168
    # the orders panel: a level reached waits for the vote only while it is a trigger
    assert 'BUY level reached (ask' in _text(D.turtle_panel(_turtle_d('armed'))) and 'needs the M15 vote' in \
        _text(D.turtle_panel(_turtle_d('armed')))
    for state, side, why in (('used', None, "no entry, today's orders are used"), ('armed', 'BUY', 'no entry, a trade is open')):
        panel = _text(D.turtle_panel(_turtle_d(state, side)))
        assert json.dumps(why)[1:-1] in panel and 'needs the M15 vote' not in panel, (state, side)


# ───────────────────────────── no request reads a file outside OUTPUT_DIR ─────────────────────────────

SECRET = 'FAKE-SECRET-not-a-password'


def _secret_tree(tmp_path, basket):
    """OUTPUT_DIR = <tmp>/up2/up1/out (a copy of the basket replay's folder) and files holding a fake secret one and two
    folders above it: mt5_credentials.json (for the JSON views), journal_<day>.log and journal_events.jsonl (for the
    log views and the download)."""
    up2 = tmp_path / 'up2'
    up1 = up2 / 'up1'
    out = up1 / 'out'
    shutil.copytree(basket.end, out)
    for folder, tag in ((up1, 'one-up'), (up2, 'two-up')):
        (folder / 'mt5_credentials.json').write_text(json.dumps(
            {'demo': {'login_id': 1, 'login_pass': f'{SECRET}-{tag}-json', 'server': 'Fake-Demo'}}), encoding='utf-8')
        (folder / f'journal_{DAY}.log').write_text(f'{DAY} 08:00:00.000 UTC | INFO | X | {SECRET}-{tag}-log\n',
                                                  encoding='utf-8')
        (folder / 'journal_events.jsonl').write_text(json.dumps(
            {'t': START + 60, 'level': 'ERROR', 'cat': 'X', 'msg': f'{SECRET}-{tag}-events'}) + '\n', encoding='utf-8')
    return str(out), up1, up2


def _climbing_values(up1, up2):
    """Symbol and day values that would climb out of OUTPUT_DIR (or its logs folder): ../ and Windows backslashes,
    absolute paths, a symbol with a folder, empty strings and None."""
    syms = []
    for name in ('mt5_credentials', 'journal'):
        syms += [f'../{name}', f'../../{name}', f'../../../{name}', f'..\\{name}', f'..\\..\\{name}',
                 f'..\\..\\..\\{name}', str(up1 / name), str(up2 / name), 'C:' + str(up1 / name).replace('/', '\\')]
    syms += ['', None, '.', '..', '/', f'{BASKET}/../../mt5_credentials', f'{BASKET}\\..\\..\\mt5_credentials', 7, ['x']]
    days = [f'../../{DAY}', '../../../journal', '..\\..\\journal', str(up1 / 'journal'), '', None, f'{DAY}\n',
            f'{DAY}/../../../journal', '2026-13-45', 20261117]
    return syms, days


def _decoded(dl):
    """The bytes a download answer would send (dcc.send_file: base64), as text."""
    if isinstance(dl, dict) and dl.get('content'):
        return base64.b64decode(dl['content']).decode('utf-8', 'replace') if dl.get('base64') else str(dl['content'])
    return ''


def test_no_callback_reads_a_file_outside_the_output_folder(D, tmp_path, basket):
    """Dash does not check a value against its options: any client can send any symbol or day. The callbacks take a
    symbol only from symbols() and a day only when it reads YYYY-MM-DD and its file exists, so no view, raw view or
    download shows a file above OUTPUT_DIR -- here a fake credentials file and fake logs one and two folders up."""
    out, up1, up2 = _secret_tree(tmp_path, basket)
    _point(D, out, BASKET)
    syms, days = _climbing_values(up1, up2)
    for sym, day in [(s, DAY) for s in syms] + [(BASKET, x) for x in days] + [(s, x) for s in syms[:3] for x in days[:2]]:
        views = [D._status(0, sym), D._live(0, 'live', 'M1', sym, None), D._trades(0, 'trades', sym, None),
                 D._log_files(0, 'log', sym, day), D._history(0, 'history', sym, day, None),
                 D._log(0, 'log', sym, list(D.LOG_LEVELS), '', ['hb', 'cfg'], 2000, 'events', day, 'live', None),
                 D._log(0, 'log', sym, list(D.LOG_LEVELS), '', ['hb', 'cfg'], 2000, 'text', day, 'live', None)]
        dl = D._download(1, day, sym)
        text = _text(views + [dl if isinstance(dl, dict) else None]) + _decoded(dl)
        assert SECRET not in text, (sym, day, text[text.find(SECRET) - 200:text.find(SECRET) + 60])
        assert str(up1) not in text.replace(os.path.join(out, ''), ''), (sym, day)     # no folder above it is named
    # the bot's own files are still there: the symbol of OUTPUT_DIR, its day, its download
    raw = _text(D._history(0, 'history', BASKET, None, None))
    assert f'{BASKET}_trace.json' in raw and 'old status' in raw
    assert D._download(1, DAY, BASKET)['filename'] == f'{BASKET}_{DAY}.log'
    assert D.valid_symbol('../mt5_credentials') == BASKET and D.valid_day(BASKET, f'{DAY}\n') is None
    with pytest.raises(D.OutsideOutputDir):
        D._path('..', 'mt5_credentials.json')


def _serve(D):
    from werkzeug.serving import make_server
    srv = make_server('127.0.0.1', 0, D.server, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _post(port, body):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/_dash-update-component', data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def test_no_http_request_reads_a_file_outside_the_output_folder(D, tmp_path, basket):
    """The same as a client on the network would send it: POSTs to a running server's /_dash-update-component for
    every callback, with symbol and day values that climb out of OUTPUT_DIR. Every answer is 200 / 204 and none holds
    the fake secret (the download's base64 content decoded)."""
    out, up1, up2 = _secret_tree(tmp_path, basket)
    _point(D, out, BASKET)
    syms, days = _climbing_values(up1, up2)
    tab_of = {'live-now': 'live', 'trades-kpis': 'trades', 'log-files': 'log', 'log-count': 'log', 'hist-day': 'history',
              'issues-view': 'changes', 'changelog-view': 'changes'}
    fixed = {('tick', 'n_intervals'): 1, ('tf', 'value'): 'M1', ('log-levels', 'value'): list(D.LOG_LEVELS),
             ('log-search', 'value'): '', ('log-hb', 'value'): ['hb', 'cfg'], ('log-limit', 'value'): 2000,
             ('log-follow', 'value'): 'live', ('log-dl-btn', 'n_clicks'): 1, ('url', 'search'): '?tab=history'}
    srv = _serve(D)
    try:
        answers = []
        values = ([(s, DAY) for s in syms[:4] + syms[6:9] + syms[13:22]] + [(BASKET, x) for x in days]
                  + [(syms[1], days[1]), (syms[10], days[3])])
        for sym, day in values:
            for key, cb in D.app.callback_map.items():
                if 'callback' not in cb:              # (the alert's sound / notification runs in the browser only)
                    continue
                outs = [dict(zip(('id', 'property'), o.rsplit('.', 1))) for o in key.strip('.').split('...')]
                for view in (('events', 'text') if outs[0]['id'] == 'log-count' else ('events',)):
                    def value(i):
                        k = (i['id'], i['property'])
                        if k == ('symbol', 'value'):
                            return sym
                        if k in (('log-day', 'value'), ('hist-day', 'value')):
                            return day
                        if k == ('tabs', 'value'):
                            return tab_of.get(outs[0]['id'], 'live')
                        if k == ('log-view', 'value'):
                            return view
                        return fixed.get(k)
                    ins = [dict(i, value=value(i)) for i in cb['inputs']]
                    body = {'output': key, 'outputs': outs if key.startswith('..') else outs[0], 'inputs': ins,
                            'state': [dict(i, value=value(i)) for i in cb.get('state', [])],
                            'changedPropIds': [f"{ins[0]['id']}.{ins[0]['property']}"]}
                    status, text = _post(srv.server_port, body)
                    answers.append(status)
                    assert status in (200, 204), (sym, day, key, status, text[-1500:])
                    dl = (json.loads(text).get('response') or {}).get('log-dl', {}).get('data') if status == 200 else None
                    seen = text + _decoded(dl)
                    assert SECRET not in seen, (sym, day, key, seen[seen.find(SECRET) - 200:seen.find(SECRET) + 60])
        assert answers.count(200) > len(values) * 5          # the callbacks answered (not only 204: no update)
        # and the page itself: the bot's own download still works over HTTP
        ok = {'output': 'log-dl.data', 'outputs': {'id': 'log-dl', 'property': 'data'},
              'inputs': [{'id': 'log-dl-btn', 'property': 'n_clicks', 'value': 1}],
              'state': [{'id': 'log-day', 'property': 'value', 'value': DAY},
                        {'id': 'symbol', 'property': 'value', 'value': BASKET}], 'changedPropIds': ['log-dl-btn.n_clicks']}
        status, text = _post(srv.server_port, ok)
        assert status == 200 and _decoded(json.loads(text)['response']['log-dl']['data']).startswith(DAY)
    finally:
        srv.shutdown()


def test_the_force_close_gauge_follows_the_design(D, basket):
    d = _point(D, basket.end, BASKET)
    off = _text(D.strategy_panel(d))
    assert 'force-close is off in this design' in off and 'force-close ON' not in off
    on = copy.deepcopy(d)
    on['trace']['basket']['force_close_enabled'] = True
    text = _text(D.strategy_panel(on))
    assert 'force-close ON: a basket closes when this score is 1 or more against it' in text


# ───────────────────────────── how close is it; changes & issues (the owner's requests of 16 Nov 2026) ───────────

def _with_open(d, **upd):
    dd = copy.deepcopy(d)
    dd['trace']['basket']['open'].update(upd)
    return dd


def test_how_close_the_open_basket_is_to_its_target_and_stop(D, basket):
    """The meters of the open basket: percent of the way to the target (P/L / target) and to the stop (-P/L / stop),
    the distance in price and in $; amber from 70 %, red from 90 %; the banner on every tab (the status callback) says
    which one, and nothing when the position is far from both or the trace is stale."""
    d = _point(D, basket.open, BASKET)
    op = d['trace']['basket']['open']
    tgt, stop = op['target_usd'], op['stop_usd']
    digits = D.digits_of(d)
    view, alert = D.proximity(_with_open(d, pnl=0.0, to_target_usd=tgt, to_stop_usd=stop))
    text = _text(view)
    assert alert['level'] is None and 'To the target' in text and 'To the stop loss' in text and 'NOT CLOSE' in text
    for bit in ('P/L in price', 'Time in trade', 'Legs · lot', 'Virtual balance', 'Spread', 'Last tick'):
        assert json.dumps(bit)[1:-1] in text, bit
    near_t = _with_open(d, pnl=round(tgt * 0.95, 2), to_target_usd=round(tgt * 0.05, 2))
    view, alert = D.proximity(near_t)
    assert alert['level'] == 'red' and 'target' in alert['text'] and '95% of the way to its target' in alert['text']
    assert 'prog prog-red prog-exit' in _text(view) and 'VERY CLOSE' in _text(view)
    assert D.px(op['target_price'], digits) in _text(view)
    near_s = _with_open(d, pnl=round(-stop * 0.75, 2), to_stop_usd=round(stop * 0.25, 2))
    view, alert = D.proximity(near_s)
    assert alert['level'] == 'amber' and '75% of the way to its stop loss' in alert['text']
    assert 'prog prog-amber prog-exit' in _text(view)
    banner = _text(D.alert_banner(alert))
    assert 'Getting close: ' in banner and 'alertbar-amber' in banner
    assert D.alert_banner({'level': None}) is None
    # the status callback (every tab): the bar, the banner, the alert for the sound / notification
    status, bar, al = D._status(0, BASKET)
    assert al == D.alert_of(D.load(BASKET))
    # stale: no alert (the numbers are those of the last poll)
    D._now = lambda: d['trace']['t'] + 7200
    assert D.proximity(near_t)[1]['level'] is None and '(as of ' in _text(D.proximity_view(near_t))


def test_how_close_the_turtle_trade_is_to_its_stop_and_next_add(D, turtle):
    d = _point(D, turtle.open, turtle.symbol)
    trd = d['trace']['turtle']['trade']
    view, alert = D.proximity(d)
    text = _text(view)
    pct_ = (1 - trd['to_stop'] / trd['stop_dist']) * 100
    assert 'To the stop loss' in text and f'{pct_:.0f}% of the way' in text
    assert 'To the next add (+1 leg)' in text and 'No target: the Turtle exits only at its stop' in text
    assert (alert['level'] is None) == (pct_ < D.ALERT_AMBER)
    near = copy.deepcopy(d)
    near['trace']['turtle']['trade']['to_stop'] = trd['stop_dist'] * 0.08
    assert D.proximity(near)[1]['level'] == 'red'


def test_how_close_a_flat_turtle_is_to_an_entry(D):
    D._now = lambda: START + 2.0
    view, alert = D.proximity(_turtle_d('armed'))
    text = _text(view)
    assert 'To a BUY entry' in text and 'To a SELL entry' in text and 'reached' in text
    assert alert['level'] == 'red' and 'BUY entry' in alert['text']           # the buy level is reached
    view, alert = D.proximity(_turtle_d('used'))
    assert alert['level'] is None and "today's orders are used" in _text(view)


@pytest.fixture(scope='module')
def turtle_short(tmp_path_factory):
    """The Turtle's short trip (test_turtle_bot.py, the vote -1) with the real writers: its folder with two legs open."""
    if not HAS_TURTLE:
        pytest.skip('no turtle.py on this branch')
    import test_turtle_bot as TB
    tmp = tmp_path_factory.mktemp('dash_turtle_short')
    out, open_dir = str(tmp / 'out'), str(tmp / 'open')
    fake, clock = TB._market(TB._short_trip())
    snap, done = _snapshotting(out, lambda tr: len(((tr.get('turtle') or {}).get('trade') or {}).get('legs') or []) == 2,
                               open_dir)
    vote = TB.Vote(fake, lambda t: -1)

    def on_new_bot(bot, n):
        sys.modules[type(bot).__module__].T.closed_bar_vote = vote
        snap(bot, n)
    run = run_bot(fake, clock, overrides={**TB.TURTLE, 'OUTPUT_DIR': out}, symbol=TB.SYMBOL,
                  state_dir=os.path.join(out, 'state'), keep_writers=True, on_new_bot=on_new_bot)
    assert not run.errors, run.errors[:3]
    assert done, 'no two-leg short in the replay'
    return types.SimpleNamespace(end=out, open=open_dir, symbol=TB.SYMBOL)


def test_a_short_turtle_trades_hovers_and_meters_say_the_short_side(D, turtle_short):
    """A real short (the bot's own trace): its next add is at the bid <= the last fill - 0.5N, its stop at the ask;
    the hovers say so (the long's words were shown before), and the meters read the short's distances."""
    d = _point(D, turtle_short.open, turtle_short.symbol)
    trd = d['trace']['turtle']['trade']
    assert trd['side'] == 'SELL' and trd['next_add_judged_on'] == 'bid' and trd['judged_on'] == 'ask'
    last_fill = trd['legs'][-1]['price']
    assert trd['next_add'] == pytest.approx(last_fill - trd['add_step'], abs=2e-3)
    tags = _tag_names(D.price_figure(d, 'M1'))
    assert {'STOP (ask)', 'NEXT ADD', 'AVG'} <= set(tags), sorted(tags)
    hover = tags['NEXT ADD'].hovertext
    assert hover == 'next leg when the bid ≤ this (the last fill - 0.5N)', hover
    assert '+ 0.5N' not in _text(D.price_figure(d, 'M1'))
    text = _text(D.proximity(d)[0])
    assert json.dumps('bid ≤ ' + D.px(trd['next_add'], D.digits_of(d)))[1:-1] in text and 'To the stop loss' in text


def _events_file(folder, symbol, events):
    os.makedirs(os.path.join(folder, 'logs'), exist_ok=True)
    with open(os.path.join(folder, 'logs', f'{symbol}_events.jsonl'), 'a', encoding='utf-8') as f:
        for e in events:
            f.write(json.dumps(e) + '\n')


def test_the_changes_and_issues_tab(D, tmp_path, basket):
    """Every WARN / ERROR of the events file grouped by kind (count, first and last time, what it means and what to do);
    the branch's CHANGELOG.md rendered version by version, the newest open."""
    folder = str(tmp_path / 'issues')
    shutil.copytree(basket.end, folder)
    t = json.load(open(os.path.join(folder, f'{BASKET}_trace.json'), encoding='utf-8'))['t']
    evs = []
    for k in range(3):
        evs.append({'t': t - 3000 + 60 * k, 'level': 'ERROR', 'cat': 'ACCOUNT',
                    'msg': 'TERMINAL_IN_USE: the terminal C:\\MT5\\slot6\\terminal64.exe holds account 9 on X-Live; no login'})
    evs.append({'t': t - 2000, 'level': 'ERROR', 'cat': 'ACCOUNT', 'msg': 'not trading: the terminal holds account 9'})
    for k in range(4):
        evs.append({'t': t - 1000 + 5 * k, 'level': 'ERROR', 'cat': 'TERMINAL', 'msg': f'reconnect failed: attempt {k + 1}'})
    evs.append({'t': t - 500, 'level': 'WARN', 'cat': 'WRITE', 'msg': 'could not write the trades: PermissionError: [Errno 13]'})
    evs.append({'t': t - 400, 'level': 'WARN', 'cat': 'DATA', 'msg': 'something new 12 times'})
    evs.append({'t': t - 300, 'level': 'WARN', 'cat': 'DATA', 'msg': 'something new 13 times'})
    _events_file(folder, BASKET, evs)
    _point(D, folder, BASKET)
    rows, _, problem = D.issues(BASKET)
    by = {r['code']: r for r in rows}
    assert problem is None
    assert by['TERMINAL_IN_USE']['count'] == 3 and by['TERMINAL_IN_USE']['level'] == 'ERROR'
    assert by['TERMINAL_IN_USE']['first'] == t - 3000 and by['TERMINAL_IN_USE']['last'] == t - 2880
    assert by['ACCOUNT_REFUSED']['count'] == 1 and by['RECONNECT_FAILED']['count'] == 4
    assert by['WRITE_FAILED']['level'] == 'WARN' and by['DATA: something new # times']['count'] == 2
    assert [r['level'] for r in rows][:3] == ['ERROR'] * 3
    issues, _ = D._changes(0, 'changes', BASKET, None)
    changes, sig = D._changelog(0, 'changes', None)
    text = _text(issues)
    for bit in ('TERMINAL_IN_USE', 'ACCOUNT_REFUSED', 'RECONNECT_FAILED', 'What it means: ', 'What to do: ',
                f"{sum(r['count'] for r in rows if r['level'] == 'ERROR')} error line(s)",
                f"{sum(r['count'] for r in rows if r['level'] == 'WARN')} warning line(s)", 'in the last hour'):
        assert bit in text, bit
    entries = D.changelog_entries()
    head = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').split('\n## [', 2)[1].split(']')[0]
    assert entries[0][0] == head and entries[0][3]
    assert any(e[1] == '2026-11-16' for e in entries)                       # a dated entry: its date, not '2026'
    text = _text(changes)
    assert head in text and '"open": true' in text and 'versions in this branch' in text
    assert D._changes(0, 'live', BASKET, None) == [D.no_update] * 2
    # the CHANGELOG is drawn once (the pane stays in the page) and again only when the file changes
    assert D._changelog(0, 'changes', sig) == [D.no_update] * 2 and D._changelog(0, 'live', None) == [D.no_update] * 2


def test_the_page_shows_no_folder_of_this_pc(D, tmp_path, basket):
    """The page has no login: event lines, their values and tracebacks, the raw text and the footer name no folder of
    the PC (the bot folder of a traceback becomes a file name, the profile folder '~'); the copy-path boxes are the one
    exception."""
    folder = str(tmp_path / 'paths')
    shutil.copytree(basket.end, folder)
    home = os.path.expanduser('~')
    bot = os.path.join(str(D.HERE), 'app.py')
    tb = f'Traceback (most recent call last):\n  File "{bot}", line 2341, in execute_job\nValueError: x'
    t = json.load(open(os.path.join(folder, f'{BASKET}_trace.json'), encoding='utf-8'))['t']
    _events_file(folder, BASKET, [{'t': t - 5, 'level': 'ERROR', 'cat': 'START', 'msg': f'the job failed in {D.HERE}',
                                   'kv': {'path': os.path.join(home, 'x', 'state.json')}, 'traceback': tb}])
    with open(os.path.join(folder, 'logs', f'{BASKET}_{DAY}.log'), 'a', encoding='utf-8') as f:
        f.write(f'{DAY} 09:00:00.000 UTC | ERROR | START | the job failed\n    File "{bot}", line 1\n')
    _point(D, folder, BASKET)
    ev = _text(D._log(0, 'log', BASKET, list(D.LOG_LEVELS), '', [], 200, 'events', DAY, 'live', None))
    raw = _text(D._log(0, 'log', BASKET, list(D.LOG_LEVELS), '', [], 2000, 'text', DAY, 'live', None))
    for text in (ev, raw, _text(D.latest_events(BASKET)), _text(D.issues_view(BASKET))):
        body = text.replace(json.dumps(os.path.abspath(D.text_log_path(BASKET, DAY)))[1:-1], '')
        assert str(D.HERE) not in body and json.dumps(str(D.HERE))[1:-1] not in body
        assert json.dumps(home)[1:-1] + json.dumps(os.sep)[1:-1] not in body.replace(json.dumps(folder)[1:-1], '')
    assert 'File \\"app.py\\", line 2341' in ev and 'the bot folder' in ev and '~/x/state.json'.replace('/', os.sep) in ev.replace('\\\\', '\\')
    layout = _text(D.serve_layout())
    assert json.dumps(os.path.abspath(folder))[1:-1] not in layout and "reads the bot's output folder" in layout
    # the settings (OUTPUT_DIR as the bot logged it: the replay's own folder) and the raw files name no folder either
    _point(D, basket.end, BASKET)
    views = _text([D.settings_view(BASKET, D.load(BASKET)), D.raw_view(BASKET)])
    assert 'OUTPUT_DIR' in views
    assert json.dumps(os.path.abspath(basket.end))[1:-1] not in views and json.dumps(str(D.HERE))[1:-1] not in views


def test_a_day_file_named_in_another_case_is_listed_and_downloaded(D, tmp_path, basket):
    """A start that failed before symbols.json was read named its day XAUUSDM_<day>.log (Windows keeps that case for the
    day): the Log tab lists it and the download sends it."""
    folder = str(tmp_path / 'case')
    shutil.copytree(basket.end, folder)
    logs = os.path.join(folder, 'logs')
    for n in os.listdir(logs):
        if n.endswith('.log'):
            os.remove(os.path.join(logs, n))
    with open(os.path.join(logs, f'{BASKET.upper()}_{DAY}.log'), 'w', encoding='utf-8') as f:
        f.write(f'{DAY} 08:00:00.000 UTC | ERROR | START | mt5_credentials.json is not UTF-8 text\n')
    _point(D, folder, BASKET)
    assert [x[0] for x in D.log_files(BASKET)] == [DAY] and D.valid_day(BASKET, DAY) == DAY
    got = D._download(1, DAY, BASKET)
    assert _decoded(got).startswith(f'{DAY} 08:00:00.000 UTC | ERROR | START')


def test_the_dashboard_holds_a_file_only_to_read_it(D, tmp_path, basket, monkeypatch):
    """On Windows the bot cannot replace a file the dashboard has open: read_json closes the file before it parses."""
    _point(D, basket.end, BASKET)
    open_files = []
    real_open = open

    class Tracked:
        def __init__(self, f):
            self.f = f
            open_files.append(self)
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.closed = True
            self.f.close()

        def read(self, *a):
            return self.f.read(*a)
    monkeypatch.setattr('builtins.open', lambda *a, **k: Tracked(real_open(*a, **k)))
    real_loads = json.loads
    seen = []

    def loads(*a, **k):
        seen.append(all(x.closed for x in open_files))
        return real_loads(*a, **k)
    monkeypatch.setattr(D.json, 'loads', loads)
    D._CACHE.clear()
    data, problem = D.read_json(D.trades_path(BASKET))
    monkeypatch.undo()
    assert problem is None and data and seen == [True]


def test_odd_paths_get_a_plain_404(D):
    client = D.server.test_client()
    for path in ('/_dash-component-suites/dash/../../../constants.py', '/_dash-component-suites/dash/%2e%2e/x.js',
                 '/assets/..%5cmt5_credentials.json', '/assets/%2E%2E/%2E%2E/mt5_credentials.json'):
        r = client.get(path)
        assert r.status_code == 404, (path, r.status_code)
    assert client.get('/').status_code == 200
