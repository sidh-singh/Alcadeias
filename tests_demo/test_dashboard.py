"""
The dashboard (dashboard.py) on the files the bot writes (docs/dashboard-data.md).

A basket replay (the scaled design: entries, a one-unit add, stops, a target, the loss pause) and, on a branch with
the Turtle, the Turtle's long trip (a breakout BUY, three adds, the one stop) run with the real writers; their output
folders, taken in an open position and at the end, are what the dashboard reads. Every view of every tab is built
from them without an error card and shows what the bot wrote: the headline, every check in the bot's order, the
votes and scores (basket) or N, the channels, today's levels, the vote of the closed M15 bar (Turtle), the chart's
entries, exits and the open trade's levels on a UTC time axis, the trades, the log with its filters, the old views
and the settings the bot started with. A folder that is empty, files that are cut or hold nulls, a stale trace and a
refused account are shown, never raised. The dashboard only reads files: it never imports the terminal's package.
"""
import copy
import json
import os
import re
import shutil
import sys
import types
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
    tags = [a.text for a in fig.layout.annotations]
    for name, price in (('TARGET', op['target_price']), ('STOP', op['stop_price']), ('BID', d['trace']['market']['bid'])):
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


def test_a_stale_trace_a_refused_account_and_errors_are_shown(D, tmp_path, basket):
    folder = str(tmp_path / 'state')
    shutil.copytree(basket.end, folder)
    p = os.path.join(folder, f'{BASKET}_trace.json')
    with open(p, encoding='utf-8') as f:
        tr = json.load(f)
    tr['health'].update(account_ok=False, account_problem='the terminal is logged into account 7, not the demo login 1',
                        errors_1h=3, connected=False, terminal_problem='terminal_info() is None')
    tr['stale'], tr['stale_since_utc'] = True, tr['time_utc']
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(tr, f)
    d = _point(D, folder, BASKET, age=300.0)
    status = _text(D.status_bar(BASKET, d))
    for bit in ('Stale: last update 5.0 min ago', 'Account refused: the terminal is logged into account 7',
                '3 error(s) in the last hour', 'Terminal: terminal_info() is None',
                'Last poll could not read the terminal'):
        assert bit in status, bit
    assert 'the account, market and position numbers below are those of the last good poll' in _text(D.now_header(d))
    assert D.freshness({'t': START})[0] == 'neg'


def test_the_force_close_gauge_follows_the_design(D, basket):
    d = _point(D, basket.end, BASKET)
    off = _text(D.strategy_panel(d))
    assert 'force-close is off in this design' in off and 'force-close ON' not in off
    on = copy.deepcopy(d)
    on['trace']['basket']['force_close_enabled'] = True
    text = _text(D.strategy_panel(on))
    assert 'force-close ON: a basket closes when this score is 1 or more against it' in text
