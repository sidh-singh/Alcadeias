"""
The Turtle's side of the dashboard's data contract (tracelog.py, docs/dashboard-data.md), STRATEGY = 'turtle', on a
real-money branch (the fake terminal's real, hedging account; its number is written as its last four digits only).

The fake-terminal Turtle cycle of test_turtle_bot.py (the BTC-like market with 200 days of history, a scripted M15
vote: a breakout BUY, three adds every 0.5 N, the one stop, every leg closed at it, the day's orders used) with the
real writers: <SYMBOL>_trace.json carries the turtle block (N, the D1 channels, today's levels and their orders, the
vote of the closed M15 bar and its parts, the open trade with its legs, stop, next add and backstops) and the
decision with its gates in the bot's order; <SYMBOL>_bars.json the chart's bars and the daily levels per D1 bar;
<SYMBOL>_trades.json the Turtle trade with its exit reason, N at the entry, its add levels and stop moves; the text
log the levels, the vote, the entry, the adds, the stop moves, the exit and its result. The trace changes no
decision (the same polls, requests and fills with it switched off), and a trace that fails does not stop the
trading. Also: the vote that blocks a breakout, System 1's filter, a takeover after a restart without the state
file, a gap through the broker's backstops, a skipped poll, no daily levels.
"""
import json
import os
import re
import statistics
import sys
import time
import types
from collections import Counter
from datetime import datetime, timezone

import numpy as np
import pytest

from conftest import DEFAULTS, MAGIC, START, F, run_bot
from conftest import differs, found
import test_turtle_bot as TB

SYMBOL = TB.SYMBOL
LV = TB.LV
T = TB.T
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
LINE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) UTC \| (DEBUG|INFO|ORDER|FILL|CLOSE|WARN|ERROR) \| '
                  r'([A-Z_]+) \| (.+)$')
# the fake terminal has 200 days of history, the bot asks for 1000 D1 bars: its own note about it is the only WARN
D1_NOTE = '200 closed D1 bars from the terminal (asked for 1000)'
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]             # all a file may show of the bot's account number
OTHER_LOGIN = 87654321                               # another account a terminal can hold (its tail: ...4321)
OTHER_TAIL = '...4321'


def _journal(folder):
    """Every line of the permanent journal of a bot folder, in order."""
    jdir = os.path.join(str(folder), 'journal')
    out = []
    for n in sorted(os.listdir(jdir)) if os.path.isdir(jdir) else []:
        with open(os.path.join(jdir, n), encoding='utf-8') as f:
            out += [json.loads(ln) for ln in f]
    return out


def _read_log(folder):
    """Every line of the text log, the UTC day files in order."""
    logs = os.path.join(str(folder), 'logs')
    names = sorted(n for n in os.listdir(logs) if re.match(re.escape(SYMBOL) + r'_\d{4}-\d\d-\d\d\.log$', n))
    assert names and names[0] == f'{SYMBOL}_{DAY}.log', names
    out = []
    for n in names:
        with open(os.path.join(logs, n), encoding='utf-8') as f:
            out += f.read().splitlines()
    return out


def _lines(folder):
    return [m for m in (LINE.match(ln) for ln in _read_log(folder)) if m]


def _replay(tmp, trip=None, vote=lambda t: 1, *, trace=True, keep_writers=True, overrides=None, restarts=(),
            on_bot=None, prepare=None, market=None):
    """The Turtle on the fake terminal; with the trace on, its trace file is read after every poll hook, the bars /
    trades files whenever they change, and the old dashboard JSON (analysis, book) of every poll is kept."""
    fake, clock = market or TB._market(trip or TB._long_trip(), restarts=restarts)
    if prepare is not None:
        prepare(fake)
    out = str(tmp / 'out')
    r = types.SimpleNamespace(fake=fake, out=out, snaps=[], kinds=[], old=[], bars=[], trades=[], costs=[], bots=[])
    v = TB.Vote(fake, vote)
    seen = {}

    def changed(path):
        try:
            m = os.stat(path).st_mtime_ns
        except OSError:
            return False
        if seen.get(path) == m:
            return False
        seen[path] = m
        return True

    def on_new_bot(bot, n):
        r.bots.append(bot)
        bot.trace_enabled = trace
        sys.modules[type(bot).__module__].T.closed_bar_vote = v
        save = bot._save_symbol_data

        def saving(sym, data):
            r.old.append(json.loads(json.dumps({'analysis': data.get('analysis'), 'positions': data.get('positions'),
                                                'book': (data.get('bot') or {}).get('turtle_book')}, default=str)))
            save(sym, data)
        bot._save_symbol_data = saving
        real = bot._trace

        def spy(symbol, method, *a, **k):
            t0 = time.perf_counter()
            real(symbol, method, *a, **k)
            if method not in ('poll', 'poll_skipped') or not trace:
                return
            if method == 'poll':
                r.costs.append((time.perf_counter() - t0) * 1000.0)
            base = bot.trace_dir or out
            try:
                with open(os.path.join(base, f'{symbol}_trace.json'), encoding='utf-8') as f:
                    r.snaps.append(json.load(f))
                    r.kinds.append(method)
            except OSError:
                pass
            for name, sink in (('bars', r.bars), ('trades', r.trades)):
                p = os.path.join(base, f'{symbol}_{name}.json')
                if changed(p):
                    with open(p, encoding='utf-8') as f:
                        sink.append(json.load(f))
        bot._trace = spy
        if on_bot is not None:
            on_bot(bot, n)

    r.run = run_bot(fake, clock, overrides={**TB.TURTLE, 'OUTPUT_DIR': out, **(overrides or {})}, symbol=SYMBOL,
                    state_dir=tmp / 'state', keep_writers=keep_writers, on_new_bot=on_new_bot)
    r.vote = v
    # (the replay stops mid-poll; a real job's last lines make the trace write what it still holds)
    for bot in r.bots:
        for tr in list((getattr(bot, '_tracers', None) or {}).values()):
            tr._flush()
    return r


@pytest.fixture(scope='module')
def traced(tmp_path_factory):
    r = _replay(tmp_path_factory.mktemp('turtle_traced'))
    assert not r.run.errors, r.run.errors[:3]
    return r


@pytest.fixture(scope='module')
def untraced(tmp_path_factory):
    """The same Turtle cycle with the trace switched off and the old writers recording instead of writing."""
    return _replay(tmp_path_factory.mktemp('turtle_untraced'), trace=False, keep_writers=False)


def _polled(r):
    """(trace snapshot, the poll's old JSON) of every poll that read the terminal."""
    snaps = [s for s, k in zip(r.snaps, r.kinds) if k == 'poll']
    assert len(snaps) == len(r.old)
    return list(zip(snaps, r.old))


def _actions(snaps):
    out = []
    for s in snaps:
        a = s['decision']['action']
        if not out or out[-1] != a:
            out.append(a)
    return out


# ───────────────────────────── the trace changes nothing ─────────────────────────────

@pytest.mark.slow
def test_the_trace_changes_no_decision_of_the_turtle(traced, untraced):
    assert not untraced.run.errors, untraced.run.errors[:3]
    assert not differs(traced.run.polls, untraced.run.polls)
    assert not differs(traced.fake.orders, untraced.fake.orders)
    assert [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in traced.fake.deals] == \
           [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in untraced.fake.deals]
    assert len(TB._opens(traced.fake)) == 4 and len(TB._closes(traced.fake)) == 4
    assert not os.listdir(untraced.bots[0].trace_dir)                  # switched off: no file at all


@pytest.mark.slow
def test_the_turtle_trace_costs_about_a_millisecond_per_poll(traced):
    c = sorted(traced.costs)
    med, p95 = statistics.median(c), c[int(len(c) * 0.95)]
    print(f'\nTurtle trace hook per poll (real time, fake terminal): median {med:.2f} ms, p95 {p95:.2f} ms, '
          f'max {c[-1]:.2f} ms over {len(c)} polls')
    assert med < 5.0 and p95 < 25.0


# ───────────────────────────── 1. <SYMBOL>_trace.json: the turtle block ─────────────────────────────

@pytest.mark.slow
def test_the_turtle_block_is_the_bots_book(traced):
    tl = traced.run.mods.tracelog
    fills = [d.price for d in TB._deal_ins(traced.fake)]
    sl_of = {o['_t_ms']: o['sl'] for o in TB._opens(traced.fake)}
    pairs = _polled(traced)
    in_trade = 0
    for s, old in pairs:
        assert (s['schema'], s['symbol'], s['magic'], s['strategy'], s['basket']) == (1, SYMBOL, MAGIC, 'turtle', None)
        assert s['branch'] == DEFAULTS['BRANCH'] and s['design'] == TB.TURTLE['DESIGN_NAME'] and not s['stale']
        assert (s['mode'], s['version']) == ('live', DEFAULTS['VERSION'])
        assert s['health']['connected'] and s['health']['market_live'] and s['health']['errors_1h'] == 0
        assert (s['health']['login_tail'], s['health']['own_login_tail'], s['health']['trade_mode_name']) == (
            TAIL, TAIL, 'real')
        # the real account's own figures, and how the unit is (or was, for the open trade) sized
        assert s['account']['balance'] is not None and s['account']['login_tail'] == TAIL
        assert s['sizing'] == json.loads(json.dumps(old['analysis']['sizing'])) is not None
        assert not [k for k in s['account'] if 'virtual' in k]
        tu, a, book = s['turtle'], old['analysis']['turtle'], old['book']
        # the levels of the last closed D1 bar: the bot's (its book) and the test's own computation
        lv = tu['levels']
        for k in ('buy', 'sell', 'n', 'stop_dist', 'add_step', 'trail_long', 'trail_short', 'bar_time', 'from_time'):
            assert lv[k] == book['levels'][k] == pytest.approx(LV[k]), k
        assert (lv['buy'], lv['sell'], lv['n']) == (a['buy_level'], a['sell_level'], a['n'])
        assert tu['d1'] == dict(tu['d1'], bars=200, asked=1000, enough=True, last_bar_t=LV['bar_time'])
        assert tu['n'] == LV['n'] and tu['system'] == 2 and tu['filter'] is None
        ch = tu['channels']
        assert ch['entry']['days'] == 55 and ch['exit']['days'] == 20
        assert ch['entry']['high'] == pytest.approx(LV['buy'] - 0.01) and ch['entry']['low'] == pytest.approx(LV['sell'] + 0.01)
        assert (ch['exit']['long'], ch['exit']['short']) == (LV['trail_long'], LV['trail_short'])
        assert ch['all']['55']['high'] == pytest.approx(ch['entry']['high']) and ch['all']['20']['low'] == LV['trail_long']
        assert ch['all']['55']['high_t'] <= LV['bar_time'] and ch['bar']['t'] == LV['bar_time']
        # the vote of the last closed M15 bar
        vt = tu['vote']
        assert vt['fresh'] and vt['value'] == vt['last'] == a['vote'] == 1 and vt['allows'] == 'BUY'
        assert vt['bar_t'] % 900 == 0 and vt['bar_close_t'] <= s['market']['tick_t'] < vt['bar_close_t'] + 902
        # (read 2 s after each M15 close; the first poll, 1 s after 08:00, reads the bar that closed then and again at
        # 08:00:02)
        assert vt['next_read_t'] in (vt['bar_close_t'] + 2, vt['bar_close_t'] + 902)
        assert vt['next_read_t'] > s['market']['tick_t'] and vt['bars'] >= 100 and vt['tf'] == 'M15'
        assert len(vt['rsi']['series']) == len(vt['macd']['series']) == len(vt['t']) == 40 and vt['t'][-1] == vt['bar_t']
        assert vt['rsi']['vote'] == vt['macd']['vote'] == 1 and vt['macd']['side_rule'] in ('high', 'low', 'none')
        # the day's orders
        o = tu['orders']
        assert o['armed'] == book['armed'] and o['state'] == ('armed' if book['armed'] else 'used')
        assert o['buy']['level'] == LV['buy'] and o['buy']['reached'] == (s['market']['ask'] >= LV['buy'])
        assert o['sell']['reached'] == (s['market']['bid'] <= LV['sell'])
        assert o['buy']['distance'] == pytest.approx(LV['buy'] - s['market']['ask'], abs=1e-3)
        # the open trade
        tr = tu['trade']
        if s['decision']['action'] == 'CLOSE_BUY':          # the book is flat; the trace shows the trade it closed
            assert not book['side'] and tr['closed_now'] and tr['stop'] == pytest.approx(fills[3] - LV['stop_dist'])
            continue
        if not book['side']:
            assert tr is None and tu['new_trade'] is not None
            nt = tu['new_trade']['buy']
            entry = max(LV['buy'], s['market']['ask'])
            assert nt['entry'] == pytest.approx(entry, abs=1e-3) and nt['stop'] == pytest.approx(entry - LV['stop_dist'], abs=1e-3)
            assert nt['backstop'] == pytest.approx(entry - LV['stop_dist'] - LV['n'], abs=2e-3)
            continue
        in_trade += 1
        assert tu['new_trade'] is None
        legs = book['legs']
        assert (tr['side'], tr['legs_count'], tr['units']) == ('BUY', len(legs), 1) == ('BUY', a['legs'], a['units'])
        assert [x['price'] for x in tr['legs']] == [x['price'] for x in legs] == fills[:len(legs)]
        assert tr['stop'] == book['stop'] == a['stop'] and tr['stop_origin'] == a['stop_origin'] == '2N'
        assert tr['stop_2n'] == pytest.approx(max(fills[:len(legs)]) - LV['stop_dist'], abs=1e-3)
        assert tr['n_entry'] == LV['n'] and tr['entry_d1_t'] == LV['bar_time'] and tr['entry_level'] == LV['buy']
        if len(legs) < 4:
            assert tr['next_add'] == pytest.approx(legs[-1]['price'] + LV['add_step'], abs=1e-3) == a['next_add']
        else:
            assert tr['next_add'] is None and tr['full']
        assert tr['backstop_prices'] == list(sl_of.values())[:len(legs)]
        if all(x['listed'] for x in tr['legs']):
            assert tr['pnl'] == old['positions']['buy']['total_profit']
        assert tr['to_stop'] == pytest.approx(s['market']['bid'] - tr['stop'], abs=1e-3)
    assert in_trade > 1000
    assert all(s['decision']['action'] in tl.ACTIONS for s, _ in pairs)


@pytest.mark.slow
def test_the_turtle_decision_and_its_gates(traced):
    snaps = [s for s, _ in _polled(traced)]
    assert _actions(snaps) == ['WAIT', 'OPEN_BUY', 'HOLD', 'ADD_BUY', 'HOLD', 'ADD_BUY', 'HOLD', 'ADD_BUY', 'HOLD',
                               'CLOSE_BUY', 'WAIT']
    head = ['terminal', 'account', 'positions', 'quote', 'd1_levels', 'market_live']
    flat = head + ['armed', 'exit_bar', 'breakout', 'vote_known', 'vote', 'brake']
    trade = head + ['stop', 'fill_listed', 'legs', 'add_bar', 'add_price']
    opened = closed = 0
    for s in snaps:
        d = s['decision']
        g = {x['key']: x for x in d['gates']}
        assert d['headline'] and d['headline'][0].isupper() and d['headline'].endswith('.')
        if d['action'] == 'WAIT':
            assert [x['key'] for x in d['gates']] == flat
            if d['reason'] == 'no breakout':
                assert d['blocked_by'] == 'breakout' and g['breakout']['ok'] is False and not closed
                assert 'waiting for a breakout' in d['headline'] and f"{LV['buy']:,.3f}" in d['headline']
            else:
                assert d['reason'] == 'orders used' and closed and d['blocked_by'] == 'armed'
                assert "today's entry orders were used by the BUY trade" in d['headline']
                assert g['breakout']['checked'] is False                     # (the walk stopped at the used orders)
        elif d['action'] == 'OPEN_BUY':
            opened += 1
            assert [x['key'] for x in d['gates']] == flat and d['blocked_by'] is None
            assert all(g[k]['ok'] for k in flat) and g['breakout']['value'] == 'BUY' and g['vote']['value'] == 1
            assert d['orders'][0]['kind'] == 'open' and d['orders'][0]['done'] and d['orders'][0]['magic'] == MAGIC
            assert d['headline'].startswith('Opened a BUY trade: 0.01 lot at')
        elif d['action'] in ('HOLD', 'ADD_BUY'):
            assert [x['key'] for x in d['gates']] == trade and d['blocked_by'] is None
            assert g['stop']['ok'] is False and g['stop']['role'] == 'exit'
            if d['action'] == 'ADD_BUY':
                assert all(g[k]['ok'] for k in ('legs', 'add_bar', 'add_price')) and d['orders'][0]['kind'] == 'add'
                assert d['headline'].startswith('Added leg ')
            else:
                assert d['headline'].startswith('Holding the BUY trade') and 'it closes only at the stop' in d['headline']
        elif d['action'] == 'CLOSE_BUY':
            closed += 1
            assert d['reason'] == 'stop' and d['blocked_by'] == 'stop' and g['stop']['ok'] is True
            assert [x['kind'] for x in d['orders']] == ['close'] * 4
            assert s['turtle']['trade']['closed_now'] and s['turtle']['trade']['legs_count'] == 4
            assert d['headline'].startswith('Closing the BUY trade at the stop: bid ')
    assert opened == closed == 1


@pytest.mark.slow
def test_a_vote_against_the_breakout_is_the_gate_that_blocks(tmp_path):
    """The price is through the buy level from about 08:07 while the vote is 0; the 08:15 close turns it to +1: the
    trace says BLOCKED (the vote) until then, with the vote's parts and the time of the next read; the log has the vote
    change and the entry right after it."""
    b = LV['buy']
    r = _replay(tmp_path, [(b - 200, b + 50, 600), (b + 50, b + 60, 1200)], vote=lambda t: 1 if t >= START + 900 else 0)
    assert not r.run.errors
    blocked = [s for s, _ in _polled(r) if s['decision']['action'] == 'BLOCKED']
    assert len(blocked) > 100
    for s in blocked:
        d = s['decision']
        g = {x['key']: x for x in d['gates']}
        assert (d['reason'], d['side'], d['blocked_by']) == ('vote', 'BUY', 'vote')
        assert g['breakout']['ok'] and g['vote_known']['ok'] and g['vote']['ok'] is False and g['vote']['value'] == 0
        assert g['brake']['checked'] is False and s['turtle']['vote']['value'] == 0
        assert 'is through the buy level' in d['headline'] and 'no buy until it is +1' in d['headline']
        assert '08:15:02 UTC' in d['headline']
    assert _actions([s for s, _ in _polled(r)])[:3] == ['WAIT', 'BLOCKED', 'OPEN_BUY']
    text = '\n'.join(_read_log(r.out))
    assert '| INFO | VOTE | M15 vote 0 -> +1 on the bar closed at 08:15 UTC' in text
    assert '-> BLOCKED: The ask ' in text and '| INFO | TRADE | BUY trade opened: 0.01 lot at' in text


# ───────────────────────────── 2. <SYMBOL>_bars.json ─────────────────────────────

@pytest.mark.slow
def test_the_bars_file_with_the_daily_levels(traced):
    with open(os.path.join(traced.out, f'{SYMBOL}_bars.json'), encoding='utf-8') as f:
        doc = json.load(f)
    assert doc['counts'] == {'M1': 360, 'M5': 300, 'M15': 300, 'H1': 300, 'D1': 200}
    assert set(doc['source'].values()) == {'terminal'}                  # the Turtle's poll fetches none of them
    for tf, v in doc['tf'].items():
        ref = traced.fake.bars[tf].last(len(v['t']), upto_t=v['t'][-1])
        assert ref['time'].tolist() == v['t'] and np.allclose(ref['close'][:-1], v['c'][:-1], atol=6e-4)
    ov = doc['overlay']['turtle']
    assert len(ov['d1_t']) == len(ov['buy']) == len(ov['sell']) == len(ov['exit_long']) == len(ov['n']) == 200
    assert ov['d1_t'][-1] == LV['bar_time'] and ov['from_t'][-1] == LV['from_time']
    assert (ov['buy'][-1], ov['sell'][-1]) == (round(LV['buy'], 3), round(LV['sell'], 3))
    assert (ov['exit_long'][-1], ov['exit_short'][-1]) == (round(LV['trail_long'], 3), round(LV['trail_short'], 3))
    assert ov['buy'][0] is None or ov['buy'][0] > 0                    # (the first rows: N not known yet)
    gaps = np.diff([d['t'] for d in traced.bars])
    assert len(traced.bars) >= 3000 // 33 and gaps.min() >= 30.0 and gaps.max() <= 33.0


# ───────────────────────────── 3. <SYMBOL>_trades.json ─────────────────────────────

@pytest.mark.slow
def test_the_trades_file_has_the_turtle_trade(traced):
    with open(os.path.join(traced.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    fake = traced.fake
    ins = TB._deal_ins(fake)
    outs = [d for d in fake.deals if d.entry == 1]
    assert len(doc['closed']) == 1 and not doc['open']
    x = doc['closed'][0]
    assert (x['side'], len(x['legs']), x['status'], x['result']) == ('BUY', 4, 'closed', 'loss')
    assert x['pnl'] == round(sum(d.profit for d in outs), 2)
    assert x['open_t'] == pytest.approx(ins[0].time_msc / 1000.0) and x['close_t'] == pytest.approx(outs[-1].time_msc / 1000.0)
    assert (x['exit_reason'], x['exit_detail'], x['bot_reason']) == ('turtle_stop', '2N', 'turtle_stop')
    assert x['exit_reason_text'] == 'turtle stop (2N from the best fill)'
    assert x['exit_stop'] == pytest.approx(max(d.price for d in ins) - LV['stop_dist'])
    j = x['turtle']
    assert (j['n_entry'], j['entry_level'], j['entry_d1_t'], j['units'], j['vote'], j['rebuilt']) == (
        LV['n'], LV['buy'], LV['bar_time'], 1, 1, False)
    assert [leg['price'] for leg in j['legs']] == [d.price for d in ins]
    assert [leg['level'] for leg in j['legs'][1:]] == pytest.approx([d.price + LV['add_step'] for d in ins[:-1]])
    stops = [s['stop'] for s in j['stops']]
    assert len(stops) == 4 and stops == sorted(stops) and [s['why'] for s in j['stops']][0] == 'entry'
    assert j['exit']['reason'] == 'turtle_stop' and j['exit']['stop'] == stops[-1]
    # real numbers only: the running total of the bot's own closed P/L, from 0; its deepest fall in dollars
    assert [p['v'] for p in doc['balance_curve']] == [0.0, x['pnl']] and x['balance_after'] == x['pnl']
    sm = doc['summary']
    assert sm['exit_reasons'] == {'turtle_stop': 1} and sm['balance_now'] == sm['net'] == x['pnl']
    assert sm['deepest_fall'] == -x['pnl'] > 0 and not found(json.dumps(sm), 'virtual') and not found(doc, 'virtual')
    # the journal's record of the entry has what the unit was counted from (the account's balance, the bot's share)
    assert (j['balance'], j['account_balance']) == (1000.0, 2000.0)
    # while the trade was open it was listed with its live levels
    live = [d['open'][0] for d in traced.trades if d['open']]
    assert live and all(t['live'] and t['side'] == 'BUY' and t['stop'] and t['n_entry'] == LV['n'] for t in live)


# ───────────────────────────── 4. the text log ─────────────────────────────

@pytest.mark.slow
def test_the_text_log_tells_the_turtles_story(traced):
    ms = _lines(traced.out)
    assert len(ms) == len(_read_log(traced.out))                         # a clean run: no traceback lines
    levels = Counter(m.group(2) for m in ms)
    assert levels['ERROR'] == 0
    assert [m.group(4) for m in ms if m.group(2) == 'WARN'] == [D1_NOTE + ': N can differ from the backtest by a little']
    text = '\n'.join(_read_log(traced.out))
    fake = traced.fake
    fills = [d.price for d in TB._deal_ins(fake)]
    # the start: branch, design, the Turtle's rules, every constant, symbols.json, the book found, the symbol facts
    assert f"| INFO | START | trading loop started for {SYMBOL} ({SYMBOL} at the terminal): the Turtle, System 2" in text
    assert f"branch={DEFAULTS['BRANCH']}" in text and 'design=btc_turtle_s2' in text
    assert f"version={DEFAULTS['VERSION']}" in text and ' mode=live ' in text
    names = {n for n in vars(traced.run.mods.constants) if n.isupper() and not n.startswith('_')}
    config = {m.group(4).split(' = ')[0] for m in ms if m.group(3) == 'CONFIG' and ' = ' in m.group(4)}
    hidden = {'OLD_LOGINS_SHA256'}                       # never in a log line (nor a name with PIN, PASS, SECRET)
    assert hidden <= names and names - hidden <= config and not hidden & config, names - hidden - config
    assert not found(text, 'OLD_LOGINS') and not found(text, str(F.ACCOUNT_LOGIN))
    for needle in ('| INFO | CONFIG | the Turtle as it runs: entries on the 55-day breakout',
                   '| INFO | CONFIG | rules: Turtle System 2 + bot votes',
                   '| INFO | STATE | no Turtle state file of this bot', '| INFO | CONFIG | symbol BTCUSDm: digits 3',
                   '| INFO | CONFIG | symbols.json: brake 0'):
        assert needle in text, needle
    # the levels of the day, with the numbers the bot trades on
    lv = [m.group(4) for m in ms if m.group(3) == 'LEVELS']
    assert len(lv) == 1 and lv[0].startswith('levels in force: levels for 2026-11-17 (the D1 bar of 2026-11-16')
    assert f"BUY at ask >= {LV['buy']:,.3f}" in lv[0] and f"SELL at bid <= {LV['sell']:,.3f}" in lv[0]
    assert f"N {LV['n']:,.2f}" in lv[0] and f"the 20-day low {LV['trail_long']:,.3f}" in lv[0]
    # the vote, the entry, the adds, the stop moves, the exit, its result
    assert '| INFO | VOTE | M15 vote +1 on the bar closed at 08:00 UTC' in text
    assert sum(1 for m in ms if m.group(3) == 'VOTE' and m.group(2) == 'DEBUG') >= 2     # every new M15 bar
    trade = [m.group(4) for m in ms if m.group(3) == 'TRADE' and m.group(2) == 'INFO']
    assert len(trade) == 4 and trade[0].startswith(f"BUY trade opened: 0.01 lot at {fills[0]:,.3f} (the buy level "
                                                   f"{LV['buy']:,.3f} = the 55-day high")
    assert 'stop ' in trade[0] and 'next add at ask >=' in trade[0] and 'broker backstop' in trade[0]
    assert 'unit 1 (0.5 x the account balance $2,000.00 = $1,000.00)' in trade[0]
    for k in (1, 2, 3):
        assert trade[k].startswith(f"leg {k + 1}/4 added to the BUY trade: 0.01 lot at {fills[k]:,.3f} (the add level ")
    stops = [m.group(4) for m in ms if m.group(3) == 'STOP']
    assert len(stops) == 3 and all(s.startswith('stop raised ') and "below the new leg's fill" in s for s in stops)
    assert f"-> {fills[3] - LV['stop_dist']:,.3f}" in stops[-1]
    close = [m for m in ms if m.group(2) == 'CLOSE']
    assert len(close) == 1 and close[0].group(4).startswith('BUY trade closed at the stop (2N from the best fill): bid ')
    assert 'reason=turtle_stop' in close[0].group(4) and 'stop_origin=2N' in close[0].group(4)
    pnl = round(sum(d.profit for d in fake.deals if d.entry == 1), 2)
    result = [m.group(4) for m in ms if m.group(3) == 'RESULT']
    assert len(result) == 1 and f'realised -${-pnl:,.2f}' in result[0] and 'exit: turtle stop (2N from the best fill)' in result[0]
    assert f"this bot's closed trades since its live start now total -${-pnl:,.2f}" in result[0]
    # every order with its result, a FILL per entry / add
    orders = [m for m in ms if m.group(2) == 'ORDER']
    assert len(orders) == len(fake.orders) and all('retcode=10009' in m.group(4) for m in orders)
    kinds = [re.search(r'kind=(\w+)', m.group(4)).group(1) for m in orders]
    assert kinds == ['open', 'add', 'add', 'add', 'close', 'close', 'close', 'close']
    # a close names the side of the trade's leg (BUY) and its own order (SELL)
    assert all('(BUY 0.01 lot, with a SELL order)' in m.group(4) and '| kind=close side=BUY order_side=SELL ' in m.group(4)
               for m in orders if 'kind=close' in m.group(4))
    assert len([m for m in ms if m.group(2) == 'FILL']) == 4
    # a DEBUG line at every change of the decision, a heartbeat every minute
    decisions = [m.group(4) for m in ms if m.group(3) == 'DECISION']
    assert decisions[0].startswith('start -> WAIT: Flat, orders armed, waiting for a breakout')
    assert any(d.startswith('HOLD -> CLOSE_BUY: Closing the BUY trade at the stop') for d in decisions)
    assert any(d.startswith('CLOSE_BUY -> WAIT: Flat: today\'s entry orders were used') for d in decisions)
    times = [datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S.%f') for m in ms]
    assert max((b - a).total_seconds() for a, b in zip(times, times[1:])) <= 62.5
    beats = [m.group(4) for m in ms if m.group(3) == 'HEARTBEAT']
    assert len(beats) >= 3000 // 62 and all('buy_level=' in b and 'orders=' in b for b in beats)
    assert any('trade=BUY' in b and 'stop=' in b for b in beats)
    # the events file of the day: the same lines as JSON
    with open(os.path.join(traced.out, 'logs', f'{SYMBOL}_{DAY}_events.jsonl'), encoding='utf-8') as f:
        events = [json.loads(ln) for ln in f]
    assert len(events) == len(ms)
    assert all((e['level'], e['cat']) == (m.group(2), m.group(3)) for e, m in zip(events, ms))
    assert any(e['cat'] == 'STATE' and e['msg'].startswith('Turtle book saved') and e['data']['book'] for e in events)


@pytest.mark.slow
def test_the_old_dashboard_files_are_still_written(traced):
    """(the Turtle's loop writes <SYMBOL>.json, its account block included, and the strategy log; it has never written
    account.json, which only the basket loop writes)"""
    for rel in (f'{SYMBOL}.json', f'logs/{SYMBOL}_strategy_log.json', f'daily_trade/{SYMBOL}/historical_summary.json'):
        with open(os.path.join(traced.out, rel), encoding='utf-8') as f:
            assert json.load(f), rel
    with open(os.path.join(traced.out, f'{SYMBOL}.json'), encoding='utf-8') as f:
        assert json.load(f)['analysis']['turtle']['system'] == 2


# ───────────────────────────── a D1 close inside the trade ─────────────────────────────

def _night_market(early_exit=False):
    """23:40 UTC, 200 days of history whose last 30 days rise 20 a day (so the 20-day low rises by 20 at every D1
    close), +-300 within each day; a 5N stop, so the 20-day low is the tighter stop. The ask goes through the buy
    level at about 23:45, holds above it past midnight (the D1 bar of the day closes: new levels, the stop raised to
    the new 20-day low), then falls through the stop at about 00:20. early_exit: it falls through the stop at about
    23:55 instead and stays below it (flat past midnight, today's orders used)."""
    s0 = START + 15 * 3600 + 40 * 60
    n = 200 * 96
    t = (int(s0) - 900 * np.arange(n, 0, -1)).astype(np.int64)
    rel = t // 86400 - int(s0) // 86400
    p = np.round(60000.0 + 20.0 * np.maximum(rel, -30) + 300.0 * np.sin(2 * np.pi * (t % 86400) / 86400.0), 2)
    warm = {'t': t, 'o': p, 'h': p + 5, 'l': p - 5, 'c': p, 'n': np.ones(n, np.int64)}
    d1 = F.resample(warm, 86400)
    closed = d1['t'] + 86400 <= s0
    rows = T.daily_rows(d1['o'][closed], d1['h'][closed], d1['l'][closed], d1['c'][closed], system=2, stop_n=5.0)
    lv = T.row_levels(rows, d1['t'][closed], int(closed.sum()) - 1)
    b = lv['buy']
    if early_exit:
        bid = np.round(np.concatenate([np.linspace(b - 100, b + 100, 600), np.linspace(b + 100, lv['trail_long'] - 200, 300),
                                       np.full(1800, lv['trail_long'] - 200)]), 2)
    else:
        bid = np.round(np.concatenate([np.linspace(b - 100, b + 100, 600), np.full(1200, b + 100),
                                       np.linspace(b + 100, lv['trail_long'] - 200, 1200)]), 2)
    k = len(bid)
    t_ms = (int(s0) * 1000 + 1000 + 1000 * np.arange(k)).astype(np.int64)
    clock = F.FakeClock(s0 + 1.5, s0 + k)
    fake = F.FakeMT5(SYMBOL, t_ms, bid, bid + TB.SPREAD, clock, warm_m1=warm, contract_size=1.0, balance=2000.0)
    return (fake, clock), lv


@pytest.mark.slow
def test_a_d1_close_inside_the_trade_raises_the_stop_to_the_channel(tmp_path):
    market, lv = _night_market()
    r = _replay(tmp_path, market=market, overrides={'TURTLE_STOP_N': 5.0})
    assert not r.run.errors and len(TB._opens(r.fake)) == 1 and len(TB._closes(r.fake)) == 1
    # the levels the D1 bar of 2026-11-17 sets, from the terminal's bars as they are after its close
    d1 = r.fake.bars['D1']
    k = int(np.searchsorted(d1.t[:d1.n], lv['bar_time'] + 86400)) + 1
    rows = T.daily_rows(d1.o[:k][-1000:], d1.h[:k][-1000:], d1.l[:k][-1000:], d1.c[:k][-1000:], system=2, stop_n=5.0)
    new = T.row_levels(rows, d1.t[:k][-1000:], len(d1.t[:k][-1000:]) - 1)
    assert new['bar_time'] == lv['bar_time'] + 86400 and new['trail_long'] == pytest.approx(lv['trail_long'] + 20.0)
    snaps = [s for s, _ in _polled(r)]
    held = [s for s in snaps if s['turtle']['trade'] and not s['turtle']['trade'].get('closed_now')]
    before = [s for s in held if s['turtle']['levels']['bar_time'] == lv['bar_time']]
    after = [s for s in held if s['turtle']['levels']['bar_time'] == new['bar_time']]
    assert before and after
    for s in before:
        tr = s['turtle']['trade']
        assert (tr['stop'], tr['stop_origin'], tr['stop_channel']) == (lv['trail_long'], 'channel', lv['trail_long'])
        assert tr['stop_text'] == 'the 20-day low' and tr['stop_2n'] < tr['stop']
        assert s['turtle']['orders']['state'] == 'used'
    for s in after:
        tr = s['turtle']['trade']
        assert tr['stop'] == pytest.approx(new['trail_long']) and tr['stop_origin'] == 'channel'
        assert s['turtle']['orders']['state'] == 'armed' and s['turtle']['levels']['buy'] == pytest.approx(new['buy'])
    ms = _lines(r.out)
    lines = [m.group(4) for m in ms if m.group(3) == 'LEVELS']
    assert len(lines) == 2 and lines[1].startswith('levels for 2026-11-18 (the D1 bar of 2026-11-17; ')
    assert f"in the BUY trade: its stop is {new['trail_long']:,.3f}" in lines[1]
    stops = [m.group(4) for m in ms if m.group(3) == 'STOP']
    assert stops == [s for s in stops if s.startswith(f"stop raised {lv['trail_long']:,.3f} -> {new['trail_long']:,.3f} "
                                                      '(the 20-day low of the D1 bar of 2026-11-17: the exit channel)')]
    assert len(stops) == 1
    close = [m.group(4) for m in ms if m.group(2) == 'CLOSE']
    assert len(close) == 1 and close[0].startswith('BUY trade closed at the stop (the 20-day low): bid ')
    with open(os.path.join(r.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        x = json.load(f)['closed'][0]
    assert (x['exit_reason'], x['exit_detail'], x['exit_reason_text']) == ('turtle_stop', 'channel',
                                                                          'turtle stop (the 20-day low)')
    assert [s['stop'] for s in x['turtle']['stops']] == pytest.approx([lv['trail_long'], new['trail_long']])


@pytest.mark.slow
def test_a_refused_close_is_logged_until_every_leg_is_out(tmp_path):
    """The terminal refuses the close of one leg for 20 s: a WARN for the incomplete close, CLOSE_BUY 'close_retry'
    polls with the gate that fired, one CLOSE line when the last leg is out, every leg's exit reason recorded."""
    ref = _replay(tmp_path / 'ref', trace=False, keep_writers=False)
    t_exit = TB._closes(ref.fake)[0]['_t_ms'] / 1000.0

    def refusing(fake):
        orig = fake.positions_get

        def positions_get(symbol=None, **k):
            now = fake.clock.time()
            fake.fail_close_tickets = ({fake.positions[0]['ticket']} if t_exit - 5 <= now < t_exit + 20
                                       and fake.positions else set())
            return orig(symbol=symbol, **k)
        fake.positions_get = positions_get
    r = _replay(tmp_path / 'run', prepare=refusing)
    snaps = [s for s, _ in _polled(r)]
    closing = [s for s in snaps if s['decision']['action'] == 'CLOSE_BUY']
    assert closing[0]['decision']['reason'] == 'stop' and len(closing) > 2
    for s in closing[1:]:
        g = {x['key']: x for x in s['decision']['gates']}
        assert s['decision']['reason'] == 'close_retry' and s['decision']['blocked_by'] == 'close_retry'
        assert g['close_retry']['ok'] is True and s['decision']['headline'].startswith('Closing the rest of the BUY trade')
    ms = _lines(r.out)
    warn = [m.group(4) for m in ms if m.group(2) == 'WARN' and m.group(3) == 'CLOSE']
    assert warn and warn[0].startswith('the close of the BUY trade is incomplete: 3 closed, 1 failed')
    close = [m.group(4) for m in ms if m.group(2) == 'CLOSE']
    assert len(close) == 1 and close[0].startswith('the last 1 leg(s) of the BUY trade closed (the close at the stop ')
    with open(os.path.join(r.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    assert [(x['exit_reason'], len(x['legs'])) for x in doc['closed']] == [('turtle_stop', 4)]


@pytest.mark.slow
def test_a_late_d1_bar_is_said_and_the_old_levels_stay(tmp_path):
    """The terminal gives no D1 bars from 00:00 to 00:06 UTC: the bot keeps the levels of the day before (and its stop)
    until the new bar comes; the trace says the levels are stale, the log says so once and again when the bar is
    there, and the stop is raised to the new 20-day low only then."""
    market, lv = _night_market()
    fake = market[0]
    midnight = lv['from_time'] + 86400
    fake.fail_rates('D1', midnight, midnight + 360)
    r = _replay(tmp_path, market=market, overrides={'TURTLE_STOP_N': 5.0})
    snaps = [s for s, _ in _polled(r)]
    stale = [s for s in snaps if s['turtle']['d1']['stale']]
    assert stale and all(s['turtle']['levels']['bar_time'] == lv['bar_time'] for s in stale)
    assert midnight + 60 < min(s['market']['tick_t'] for s in stale) and max(s['market']['tick_t'] for s in stale) < midnight + 365
    assert all('not there yet' in next(g for g in s['decision']['gates'] if g['key'] == 'd1_levels')['note'] for s in stale)
    ms = _lines(r.out)
    data = [(m.group(2), m.group(4)) for m in ms if m.group(3) == 'DATA']
    assert data[0][0] == 'WARN' and data[0][1].startswith('the D1 bar that closed at 2026-11-18 00:00:00 UTC is not there yet')
    assert data[1][0] == 'INFO' and data[1][1].startswith('the new D1 bar is there')
    stop = [m for m in ms if m.group(3) == 'STOP']
    assert len(stop) == 1 and stop[0].group(1) >= '2026-11-18 00:06'
    # the bot's own note says what it does: it goes on with the levels and the stop of the day before (not 'not trading')
    notes = [m.group(4) for m in ms if m.group(3) == 'TURTLE' and 'closed D1 bars from the terminal, at least' in m.group(4)]
    assert notes and all(n.endswith('needed: the bot goes on with the levels and the stop of the D1 bar before and asks '
                                    'again every poll') for n in notes), notes
    assert not any('not trading' in m.group(4) for m in ms)


def test_a_trade_closed_while_the_bot_was_down_gets_its_result_once(mods, tmp_path):
    """The journal knows a trade the deal history shows closed (the backstops closed it while the bot was down): the
    first trades.json of the next start gives its RESULT line; a trade the journal does not know gets none; another
    start does not repeat it."""
    m = mods(**TB.TURTLE)
    now = m.clock.time()

    def deal(pid, entry, typ, price, profit, t, reason):
        return types.SimpleNamespace(ticket=pid * 10 + entry, order=0, time=int(t), time_msc=int(t * 1000), type=typ,
                                     entry=entry, magic=MAGIC, position_id=pid, reason=reason, volume=0.01, price=price,
                                     commission=0.0, swap=0.0, profit=profit, fee=0.0, symbol=SYMBOL, comment='')
    deals = [deal(7, 0, 0, 60000.0, 0.0, now - 9000, 3), deal(8, 0, 0, 60300.0, 0.0, now - 8000, 3),
             deal(7, 1, 1, 59000.0, -10.0, now - 600, 4), deal(8, 1, 1, 59000.0, -13.0, now - 600, 4),
             deal(3, 0, 1, 61000.0, 0.0, now - 90000, 3), deal(3, 1, 0, 61500.0, -5.0, now - 86000, 4)]
    results = []
    for k in range(2):
        bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=tmp_path)
        tr = bot._tracer(SYMBOL)
        if k == 0:
            tr._journal_load()['7'] = {'side': 'BUY', 'n_entry': 600.0, 'entry_level': 60000.0, 'opened_t': now - 9000,
                                       'legs': [{'id': 7}, {'id': 8}], 'stops': [], 'exit': None}
            tr._journal_save()
        doc = tr._build_trades(deals, {'turtle': {'trade': None}}, now - 100000, now, 3)
        tr._turtle_results(doc)
        tr._flush()
        results.append([x for x in _read_log(tmp_path) if '| INFO | RESULT |' in x])
        assert [(x['id'], x['exit_reason']) for x in doc['closed']] == [(3, 'backstop'), (7, 'backstop')]
    assert len(results[0]) == 1 and results[1] == results[0]
    assert 'the BUY trade of' in results[0][0] and 'realised -$23.00' in results[0][0] and 'exit: backstop' in results[0][0]
    with open(tmp_path / 'state' / f'{SYMBOL}_turtle_trades.json', encoding='utf-8') as f:
        assert json.load(f)['trades']['7']['result']['pnl'] == -23.0


# ───────────────────────────── the other paths ─────────────────────────────

@pytest.mark.slow
def test_system_1_shows_its_filter(tmp_path):
    """System 1: use20 and the hypothetical trade of its filter (the same loop as turtle.s1_use20), in the trace and in
    the levels line."""
    lv1 = TB._levels(system=1)
    r = _replay(tmp_path, TB._long_trip()[:1], overrides={'TURTLE_SYSTEM': 1})
    assert not r.run.errors
    for s, old in _polled(r):
        f = s['turtle']['filter']
        assert f['use20'] == old['book']['levels']['use20'] == lv1['use20']
        assert f['hypothetical']['use20'] == f['use20'] and f['levels_from'] in ('20-day', '55-day failsafe')
        assert s['turtle']['channels']['entry']['days'] == (20 if f['use20'] else 55)
        assert s['turtle']['channels']['exit']['days'] == 10 and s['turtle']['levels']['buy'] == lv1['buy']
    text = '\n'.join(_read_log(r.out))
    assert '; System 1 filter: the ' in text and 'exit channel: the 10-day low' in text


def test_the_filters_hypothetical_trade_is_turtle_s1_use20(mods):
    """tracelog's replica of the System 1 filter gives turtle.s1_use20's use20 on every prefix of a random D1 series."""
    tl = mods(**TB.TURTLE).tracelog
    rng = np.random.default_rng(5)
    n = 400
    c = 60000 + np.cumsum(rng.normal(0, 900, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 600, n)
    lo = np.minimum(o, c) - rng.uniform(0, 600, n)
    t = (np.arange(n) * 86400 + 1700000000 // 86400 * 86400).astype(np.int64)
    rows = T.daily_rows(o, h, lo, c, system=1)
    use20 = rows['use20']
    assert use20.any() and not use20.all()
    for b in range(60, n, 7):
        got = tl._s1_hypothetical(o[:b + 1], h[:b + 1], lo[:b + 1], rows['n'][:b + 1], t[:b + 1], 0.01, T)
        assert got['use20'] == bool(use20[b]), b
        assert got['state'] in ('flat', 'BUY', 'SELL') and (got['state'] == 'flat') == (got['entry'] is None)


@pytest.mark.slow
def test_a_restart_without_the_state_file_logs_the_takeover(tmp_path):
    """A restart after the second add, the Turtle's state file removed: the log says the trade was taken over from
    the terminal, the trace shows the same N, stop and next add, the journal keeps the entry level from before."""
    ref = _replay(tmp_path / 'ref', trace=False, keep_writers=False)
    at = TB._opens(ref.fake)[2]['_t_ms'] / 1000.0 + 30.5 - START

    def drop(bot, n):
        if n > 0:
            os.remove(bot._turtle_state_path(SYMBOL))
    r = _replay(tmp_path / 'run', restarts=[at], on_bot=drop)
    assert r.run.restarts == 1 and not r.run.errors, r.run.errors[:3]
    assert not differs(r.fake.orders, ref.fake.orders)                             # (the trade goes on as it would have)
    text = '\n'.join(_read_log(r.out))
    assert '| INFO | STATE | no Turtle state file of this bot' in text
    m = re.search(r'\| WARN \| TRADE \| BUY trade of 3 leg\(s\) taken over from the terminal \(no Turtle state for it\): '
                  r'unit 1, N at the entry ([\d,.]+) \(the D1 bar of 2026-11-16\), stop ([\d,.]+) \(2N from the best fill\)',
                  text)
    assert m and float(m.group(1).replace(',', '')) == pytest.approx(LV['n'], abs=0.006)
    after = [s for s, k in zip(r.snaps, r.kinds) if k == 'poll' and s['t'] > START + at]
    tr = after[0]['turtle']['trade']
    fills = [d.price for d in TB._deal_ins(r.fake)][:3]
    assert tr['legs_count'] == 3 and tr['n_entry'] == pytest.approx(LV['n'])
    assert tr['stop'] == pytest.approx(max(fills) - LV['stop_dist']) and tr['entry_level'] == LV['buy']
    # the figures after the restart are real ones for the rest of the trade: the account's balance, this bot's
    # open P/L, and the record of how the trade's unit was sized at its entry (app.py keeps it beside the book)
    in_trade = [x for x in after if x['turtle']['trade'] and x['decision']['action'] not in ('CLOSE_BUY', 'CLOSE_SELL')]
    before = [x for x, k in zip(r.snaps, r.kinds) if k == 'poll' and x['t'] <= START + at and x['turtle']['trade']]
    assert in_trade and before
    for x in in_trade:
        assert x['account']['balance'] == before[-1]['account']['balance'] == 2000.0
        assert x['account']['floating_own'] == x['turtle']['trade']['pnl'] or x['turtle']['trade']['pnl'] is None
        assert not [k for k in x['account'] if 'virtual' in k]
        assert (x['sizing']['source'], x['sizing']['units']) == ('entry', 1)
        assert x['sizing']['account_balance'] == before[-1]['sizing']['account_balance'] == 2000.0
    # the journal's trade line says the trade was watched in part (a restart in the middle): the watch began at the
    # entry, before the restart, and the entry's own facts are those of the entry poll (kept in the journal's state
    # file across the restart, not rebuilt)
    line = [x for x in _journal(r.out) if x['kind'] == 'trade']
    assert len(line) == 1 and (line[0]['watched'], line[0]['restarts'], line[0]['rebuilt']) == ('part', 1, False)
    assert line[0]['entry']['entry_level'] == LV['buy'] and line[0]['entry']['n'] == pytest.approx(LV['n'])
    assert line[0]['entry']['rebuilt'] is False and line[0]['entry']['vote'] == 1
    assert line[0]['max_pnl'] > 0 > line[0]['min_pnl']
    assert line[0]['watched_from_t'] < START + at < line[0]['max_pnl_t'] < line[0]['min_pnl_t']


@pytest.mark.slow
def test_a_gap_through_the_backstops_is_a_close_outside_the_bot(tmp_path):
    """The price gaps 5 N down while the trade holds its four legs: the broker's backstops close them; the log says the
    trade was closed outside the bot (CLOSE) and gives the realised result; trades.json says 'backstop'."""
    def gap(fake):
        i = int((fake.t_ms >= (START + 1600) * 1000).argmax())
        fake.bid[i:] -= 5 * LV['n']
        fake.ask[i:] -= 5 * LV['n']
    r = _replay(tmp_path, prepare=gap)
    assert not TB._closes(r.fake) and len(TB._opens(r.fake)) == 4
    ms = _lines(r.out)
    close = [m.group(4) for m in ms if m.group(2) == 'CLOSE']
    assert len(close) == 1 and close[0].startswith("the BUY trade was closed outside the bot (the broker's backstop")
    result = [m.group(4) for m in ms if m.group(3) == 'RESULT']
    assert len(result) == 1 and 'exit: backstop (broker stop)' in result[0]
    with open(os.path.join(r.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    assert [(x['exit_reason'], len(x['legs'])) for x in doc['closed']] == [('backstop', 4)]
    assert doc['closed'][0]['turtle']['exit']['reason'] == 'closed_outside'
    snaps = [s for s, _ in _polled(r)]
    assert _actions(snaps)[-1] == 'WAIT' and snaps[-1]['decision']['reason'] == 'orders used'


@pytest.mark.slow
def test_a_skipped_poll_keeps_the_last_turtle_block(tmp_path):
    fake_ref = _replay(tmp_path / 'ref', trace=False, keep_writers=False).fake
    a = TB._opens(fake_ref)[1]['_t_ms'] / 1000.0 + 20.0

    def failing(fake):
        fake.fail_positions(a, a + 15)
    r = _replay(tmp_path / 'run', prepare=failing)
    assert not differs(r.fake.orders, fake_ref.orders)
    skipped = [s for s, k in zip(r.snaps, r.kinds) if k == 'poll_skipped']
    assert 10 <= len(skipped) <= 16
    for s in skipped:
        assert s['stale'] and s['decision']['action'] == 'SKIPPED' and s['decision']['reason'] == 'positions'
        assert s['turtle']['trade']['side'] == 'BUY' and s['turtle']['trade']['legs_count'] == 2
        assert 'the trade is neither managed nor booked this poll' in s['decision']['headline']


def test_no_daily_levels_no_trading_and_the_trace_says_why(tmp_path):
    """Fewer closed D1 bars than TURTLE_MIN_D1_BARS: NO_DATA, the gate that blocks, the headline, a WARN line."""
    r = _replay(tmp_path, [(60000.0, 60100.0, 90)], overrides={'TURTLE_MIN_D1_BARS': 300, 'TURTLE_D1_BARS': 400})
    assert not TB._opens(r.fake)
    snaps = [s for s, _ in _polled(r)]
    assert snaps and all(s['decision']['action'] == 'NO_DATA' and s['decision']['reason'] == 'd1 bars' for s in snaps)
    s = snaps[-1]
    assert s['decision']['blocked_by'] == 'd1_levels' and s['turtle']['levels'] is None and s['turtle']['trade'] is None
    assert s['decision']['headline'].startswith('No daily levels yet: the terminal gave 200 closed D1 bars, at least 300')
    text = '\n'.join(_read_log(r.out))
    assert '| WARN | DATA | no daily levels: the terminal gave 200 closed D1 bars, 300 needed' in text
    # (no levels of a day before: the bot's own note says it does not trade)
    assert '| WARN | TURTLE | 200 closed D1 bars from the terminal, at least 300 needed: not trading' in text


@pytest.mark.slow
def test_a_turtle_trace_that_fails_changes_nothing(tmp_path, untraced):
    """A bug in the Turtle's part of the trace (every poll hook raises): an ERROR with its traceback, at most every 10
    min; the trading is exactly the same; the order lines (another hook) still come."""
    def boom(bot, n):
        def raising(self, *a, **k):
            raise ValueError('boom: a bug in the Turtle trace')
        sys.modules['tracelog'].TraceLog._turtle_section = raising
    r = _replay(tmp_path, on_bot=boom)
    assert not differs(r.run.polls, untraced.run.polls) and not differs(r.fake.orders, untraced.fake.orders)
    lines = _read_log(r.out)
    errs = [ln for ln in lines if '| ERROR | TRACE |' in ln]
    assert 1 <= len(errs) <= 3000 // 600 + 1
    assert ("the trace hook poll() failed in its step _turtle_section: ValueError: boom: a bug in the Turtle trace; "
            "ignored, its other steps and the trading go on") in errs[0]
    i = lines.index(errs[0])
    assert lines[i + 1] == '    Traceback (most recent call last):' and 'in _step' in '\n'.join(lines[i:i + 40])
    assert sum('| ORDER | ORDER |' in ln for ln in lines) == len(r.fake.orders)
    # its other steps go on: the trace says what failed, the heartbeat every minute, the bars and the trades
    polled = [s for s, k in zip(r.snaps, r.kinds) if k == 'poll']
    assert polled and all(s['decision']['action'] == 'TRACE_ERROR' and s['turtle'] is None for s in polled)
    assert sum('| INFO | HEARTBEAT | TRACE_ERROR:' in ln for ln in lines) >= 3000 // 62
    assert r.bars and r.trades and r.trades[-1]['closed']


@pytest.mark.slow
def test_a_turtle_transitions_line_that_fails_is_not_tried_again_every_poll(tmp_path, untraced):
    """A bug in one line of the Turtle's transitions (here the day's levels line, written on the first poll and when a
    D1 bar closes, raises): one ERROR line with its traceback. The poll hook's step keeps that poll's book for the next
    poll, so the line is not tried again on every poll after it (before: the first poll's lines were tried, and failed,
    on every poll); the trading is exactly the same."""
    calls = []

    def broken(bot, n):
        def raising(self, *a, **k):
            calls.append(1)
            raise ValueError('boom: a bug in a Turtle transitions line')
        sys.modules['tracelog'].TraceLog._log_levels = raising
    r = _replay(tmp_path, on_bot=broken)
    assert not differs(r.run.polls, untraced.run.polls) and not differs(r.fake.orders, untraced.fake.orders)
    assert len(calls) == 1, len(calls)                 # (the replay's 50 minutes are inside one UTC day)
    lines = _read_log(r.out)
    errs = [ln for ln in lines if '| ERROR | TRACE |' in ln]
    assert len(errs) == 1, errs[:3]
    assert ('the trace hook poll() failed in its step _turtle_transitions: ValueError: boom: a bug in a Turtle '
            'transitions line; ignored, its other steps and the trading go on') in errs[0]
    assert sum('| FILL | FILL |' in ln for ln in lines) >= 4 and r.trades[-1]['closed']


# ───────────────────── the paths of v3.9.2-demo.4 (the re-review's fixes) on the Turtle ─────────────────────

@pytest.mark.slow
def test_a_leg_closed_beyond_the_stop_while_the_terminal_is_down_is_in_the_trace(traced, tmp_path):
    """The terminal is gone for 8 s; one tick spikes through the fourth leg's backstop and the price comes back above
    the trade's stop (test_turtle_safety.py). Connected again, the bot closes the other three at once:
    stop_passed_outside (v3.9.2-demo.4). The trace has the gate that decided and the headline; the log the leg
    closed beyond the stop, then the end of the trade; trades.json and the journal the exit reason."""
    sl = [o['sl'] for o in TB._opens(traced.fake)]
    assert len(sl) == 4 and sl == sorted(sl)
    a = START + 1590.0

    def prepare(fake):
        i = int((fake.t_ms >= (a + 4.0) * 1000).argmax())
        spike = (sl[3] + sl[2]) / 2.0
        fake.bid[i], fake.ask[i] = spike, spike + (fake.ask[i] - fake.bid[i])
        fake.down(a, a + 8.0)

    r = _replay(tmp_path, prepare=prepare)
    fourth = [d for d in r.fake.deals if d.entry == 0][3].position_id
    closes = TB._closes(r.fake)
    assert len(closes) == 3 and fourth not in {c['position'] for c in closes} and not r.fake.positions
    leg = next(e['details'] for e in r.run.events if e['event'] == 'TURTLE_LEG_CLOSED_OUTSIDE')
    assert leg['tickets'] == [fourth] and leg['beyond_stop'] is True
    snap = next(s for s in r.snaps if s['decision']['action'] == 'CLOSE_BUY')
    dec = snap['decision']
    g = {x['key']: x for x in dec['gates']}
    assert dec['reason'] == 'stop_passed_outside' and dec['blocked_by'] == 'stop_passed' and 'close_retry' not in g
    assert g['stop_passed']['ok'] is True and g['stop_passed']['value'] == [fourth] and g['stop']['ok'] is False
    assert dec['headline'].startswith(f'Closing the rest of the BUY trade: leg(s) [{fourth}] were closed outside the bot '
                                      'at or beyond its stop')
    lines = _read_log(r.out)
    text = '\n'.join(lines)
    warn = [ln for ln in lines if f'| WARN | TRADE | leg(s) [{fourth}] of the BUY trade closed outside the bot' in ln]
    assert len(warn) == 1 and 'at or beyond its stop' in warn[0] and 'beyond_stop=true' in warn[0]
    assert ('(their broker backstop, the deal history shows): the stop was passed while the bot did not look, so the '
            'other 3 leg(s) are closed at once') in warn[0]
    orders = [k for k, ln in enumerate(lines) if '| ORDER | ORDER | close position' in ln]
    assert len(orders) == 3 and lines.index(warn[0]) < orders[0]          # the reason first, then the closes
    close = [m.group(4) for m in _lines(r.out) if m.group(2) == 'CLOSE']
    assert len(close) == 1 and close[0].startswith(f'the BUY trade ended: leg(s) [{fourth}] were closed outside the bot '
                                                   'at or beyond its stop')
    assert 'so the other 3 leg(s) closed now at the bid' in close[0] and 'reason=stop_passed_outside' in close[0]
    assert not found(text, '| WARN | TRACE |')                                     # the gates read as the bot did
    with open(os.path.join(r.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    t = doc['closed'][-1]
    assert t['exit_reason'] == 'stop_passed_outside' and len(t['legs']) == 4
    assert t['exit_reason_text'] == 'the stop passed outside the bot (a leg closed beyond it), the rest closed by the bot'
    assert t['turtle']['exit']['reason'] == 'stop_passed_outside' and t['turtle']['exit']['legs_outside'] == [fourth]
    result = [m.group(4) for m in _lines(r.out) if m.group(3) == 'RESULT']
    assert result and 'exit: the stop passed outside the bot' in result[-1]


@pytest.mark.slow
def test_a_leg_closed_by_hand_inside_the_stop_keeps_the_trade_in_the_log(traced, tmp_path):
    """One leg closed from the terminal by hand, inside the stop: the deal history shows it (beyond_stop false), the
    trade goes on with its stop kept (and adds again: the price is past the next add level), and the log says so."""
    at = TB._opens(traced.fake)[2]['_t_ms'] / 1000.0 + 60.0              # after the second add (test_turtle_bot.py)
    done = []

    def prepare(fake):
        done.extend([TB._close_by_hand(fake, at, newest_only=True)])
    r = _replay(tmp_path, prepare=prepare)
    assert done[0] and not r.run.errors, r.run.errors[:3]
    leg = next(e['details'] for e in r.run.events if e['event'] == 'TURTLE_LEG_CLOSED_OUTSIDE')
    assert leg['beyond_stop'] is False and leg['legs'] == 2
    lines = _read_log(r.out)
    warn = [ln for ln in lines if f"| WARN | TRADE | leg(s) {leg['tickets']} of the BUY trade closed outside the bot" in ln]
    assert len(warn) == 1 and 'inside its stop' in warn[0] and 'by hand, the deal history shows' in warn[0]
    assert 'the trade goes on with 2 leg(s)' in warn[0] and 'beyond_stop=false' in warn[0]
    with open(os.path.join(r.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    assert doc['closed'][-1]['exit_reason'] == 'turtle_stop'               # the trade ended at its own stop


@pytest.mark.slow
def test_an_account_switch_just_before_the_turtles_positions_read_is_in_the_trace(tmp_path):
    """Another program (an old bot) logs the terminal into another account after the Turtle's account check, just
    before its positions read (that account shows none of this bot's legs): the account read again right after the
    positions refuses the poll. The trace says SKIPPED with the gate and keeps the trade; the log has ACCOUNT_REFUSED
    and ACCOUNT_OK; no leg is taken as closed outside the bot."""
    stash = {}

    def prepare(fake):
        def to_other(f):
            stash['positions'], f.positions = f.positions, []
            f.account_login = OTHER_LOGIN

        def back(f):
            f.positions = stash['positions']
            f.account_login = F.ACCOUNT_LOGIN
        fake.on_call('positions_get', START + 845.0, to_other)             # after the first add, before the second
        fake.at(START + 905.0, back)
    r = _replay(tmp_path, prepare=prepare)
    events = [e['event'] for e in r.run.events]
    assert not {'TURTLE_CLOSED_OUTSIDE', 'TURTLE_LEG_CLOSED_OUTSIDE', 'TURTLE_REBUILT'} & set(events)
    assert events.count('ACCOUNT_REFUSED') == 1 and events.count('ACCOUNT_OK') == 1
    re_ = [s for s, k in zip(r.snaps, r.kinds) if k == 'poll_skipped' and s['decision']['reason'] == 'account_recheck']
    assert len(re_) == 1
    dec = re_[0]['decision']
    g = {x['key']: x for x in dec['gates']}
    assert dec['blocked_by'] == 'account_recheck' and g['account_recheck']['ok'] is False and g['positions']['ok'] is True
    assert "the account read again right after the positions is not this bot's (" in dec['headline']
    assert OTHER_TAIL in dec['headline'] and f"this bot's account {TAIL} again" in dec['headline']
    assert re_[0]['stale'] and re_[0]['turtle']['trade']['legs_count'] == 2          # the last good poll's trade
    lines = _read_log(r.out)
    text = '\n'.join(lines)
    assert any('| ERROR | ACCOUNT | not trading: ' in ln and OTHER_TAIL in ln for ln in lines)
    assert f"| INFO | ACCOUNT | MetaTrader 5 holds this bot's account {TAIL} again: trading" in text
    assert not found(text, str(F.ACCOUNT_LOGIN)) and not found(text, str(OTHER_LOGIN))
    # the trade went on through it: the journal's line says it was watched from its entry to its close
    line = [x for x in _journal(r.out) if x['kind'] == 'trade']
    assert len(line) == 1 and line[0]['watched'] == 'full' and line[0]['legs'] == 4
    assert len(TB._opens(r.fake)) == 4 and len(TB._closes(r.fake)) == 4             # the trade as without the switch


# ───────────────────────────── the final review's fixes ─────────────────────────────

@pytest.mark.slow
def test_a_stop_passed_close_with_a_refused_leg_keeps_its_reason_to_the_end(traced, tmp_path):
    """The leg-beyond-the-stop case above, and the terminal refuses the close of one of the other legs once (off
    quotes): the retry on the next poll is the end of the same exit, 'the stop passed outside the bot', in the CLOSE
    line, the journal and trades.json (it said 'turtle_stop' at a price far above the stop)."""
    sl = [o['sl'] for o in TB._opens(traced.fake)]
    a = START + 1590.0

    def prepare(fake):
        i = int((fake.t_ms >= (a + 4.0) * 1000).argmax())
        spike = (sl[3] + sl[2]) / 2.0
        fake.bid[i], fake.ask[i] = spike, spike + (fake.ask[i] - fake.bid[i])
        fake.down(a, a + 8.0)
        orig = fake.positions_get

        def positions_get(symbol=None, **k):
            now = fake.clock.time()
            # the first close after the reconnect (three legs left) is refused for one of them; the retry is not
            fake.fail_close_tickets = ({fake.positions[0]['ticket']} if now >= a and len(fake.positions) == 3 else set())
            return orig(symbol=symbol, **k)
        fake.positions_get = positions_get

    r = _replay(tmp_path, prepare=prepare)
    assert not r.fake.positions
    reasons = [s['decision']['reason'] for s in r.snaps if s['decision']['action'] == 'CLOSE_BUY']
    assert reasons[0] == 'stop_passed_outside' and 'close_retry' in reasons, reasons
    ms = _lines(r.out)
    warn = [m.group(4) for m in ms if m.group(2) == 'WARN' and m.group(3) == 'CLOSE']
    assert warn and 'is incomplete: 2 closed, 1 failed' in warn[0]
    close = [m.group(4) for m in ms if m.group(2) == 'CLOSE']
    assert len(close) == 1 and close[0].startswith('the last 1 leg(s) of the BUY trade closed (the close that followed '
                                                   'the stop ')
    assert 'reason=stop_passed_outside' in close[0] and 'reason=turtle_stop' not in close[0]
    with open(os.path.join(r.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        t = json.load(f)['closed'][-1]
    assert t['exit_reason'] == 'stop_passed_outside' and t['turtle']['exit']['reason'] == 'stop_passed_outside'
    result = [m.group(4) for m in ms if m.group(3) == 'RESULT']
    assert result and 'exit: the stop passed outside the bot' in result[-1]


@pytest.mark.slow
def test_a_late_d1_bar_while_flat_with_the_orders_used_is_not_counted_as_still_to_come(tmp_path):
    """The night market, but the trade stops out before midnight: flat, today's orders used. After 00:00 the terminal
    gives the new D1 bar 6 minutes late: the headline says the bar that closed at 00:00 is not there yet (it counted the
    past close as 'in 2.0 min', 'in 3.0 min' ...), and the gate note too; before midnight it counts down."""
    (fake2, clock), lv = _night_market(early_exit=True)
    midnight = lv['from_time'] + 86400
    fake2.fail_rates('D1', midnight, midnight + 360)
    r = _replay(tmp_path, market=(fake2, clock), overrides={'TURTLE_STOP_N': 5.0})
    snaps = [s for s, _ in _polled(r)]
    assert TB._closes(fake2) and TB._closes(fake2)[-1]['_t_ms'] / 1000.0 < midnight
    used = [s for s in snaps if s['decision']['action'] == 'WAIT' and s['decision']['reason'] == 'orders used']
    late = [s for s in used if s['market']['tick_t'] >= midnight]
    early = [s for s in used if s['market']['tick_t'] < midnight]
    assert early and all('(in ' in s['decision']['headline'] for s in early)
    assert late and any(s['turtle']['d1']['stale'] for s in late)
    for s in late:
        h = s['decision']['headline']
        assert '00:00:00 UTC is not there yet' in h and '(in ' not in h and 'UTC UTC' not in h, h
        note = next(g for g in s['decision']['gates'] if g['key'] == 'armed')['note']
        assert 'is not there yet' in note and 'arms new ones' not in note, note


@pytest.mark.slow
def test_a_short_turtle_trade_is_the_bots_book(tmp_path):
    """The short trip (test_turtle_bot.py, the vote -1) with the trace: the trade block is the bot's book and the
    terminal on every poll -- the stop judged on the ask, the next add on the bid at the last fill - 0.5N, the stop at
    the lowest fill + 2N, the P/L at the stop."""
    r = _replay(tmp_path, trip=TB._short_trip(), vote=lambda t: -1)
    assert not r.run.errors, r.run.errors[:3]
    fills = [d.price for d in TB._deal_ins(r.fake)]
    assert len(fills) >= 2
    in_trade = 0
    for s, old in _polled(r):
        book, tr = old['book'], s['turtle']['trade']
        if not book['side'] or s['decision']['action'] == 'CLOSE_SELL':
            continue
        in_trade += 1
        legs = book['legs']
        assert tr['side'] == 'SELL' and tr['legs_count'] == len(legs) and tr['judged_on'] == 'ask'
        assert tr['stop'] == book['stop'] and tr['stop_2n'] == pytest.approx(min(fills[:len(legs)]) + LV['stop_dist'], abs=1e-3)
        assert tr['to_stop'] == pytest.approx(tr['stop'] - s['market']['ask'], abs=1e-3)
        if len(legs) < 4:
            assert tr['next_add_judged_on'] == 'bid'
            assert tr['next_add'] == pytest.approx(legs[-1]['price'] - LV['add_step'], abs=1e-3)
            assert tr['to_next_add'] == pytest.approx(s['market']['bid'] - tr['next_add'], abs=1e-3)
        assert tr['pnl_at_stop'] == pytest.approx(sum((x['price'] - tr['stop']) * x['lots'] for x in tr['legs']), abs=0.02)
    assert in_trade > 500
    close = [m.group(4) for m in _lines(r.out) if m.group(2) == 'CLOSE']
    assert close and close[0].startswith('SELL trade closed at the stop')


# ───────────────────── the paths of v3.9.2-demo.5 (the third fix round) on the Turtle ─────────────────────

def _inside_the_close(switched, inside):
    """on_bot hook: `inside(fake)` runs at the first close_by_type call, before that close reads the positions."""
    def on_bot(bot, n):
        close = bot.position_helper.close_by_type
        fake = bot.position_helper.mt5

        def close_by_type(symbol, pos_type):
            if not switched:
                switched.append(fake.clock.time())
                inside(fake)
            return close(symbol, pos_type)
        bot.position_helper.close_by_type = close_by_type
    return on_bot


@pytest.mark.slow
def test_a_close_that_closed_nothing_is_said_and_decided_again(tmp_path):
    """Fix C of the third round: another program logs the terminal into another account just before the stop's close
    reads the positions, so it closes nothing. The log says 'closed nothing ... decided again next poll' (not
    'incomplete: 0 closed, 0 failed'), the headline too, and the trace keeps the trade; when this bot's account is
    back, one CLOSE line ends the trade with its four legs, and trades.json gives the stop as its exit."""
    switched, stash = [], {}

    def to_other(f):
        stash['positions'], f.positions = f.positions, []
        f.account_login = OTHER_LOGIN
        f.at(f.clock.time() + 60, back)

    def back(f):
        f.positions = stash['positions']
        f.account_login = F.ACCOUNT_LOGIN
    r = _replay(tmp_path, on_bot=_inside_the_close(switched, to_other))
    assert switched and r.run.errors and all('not trading: ' in e and OTHER_TAIL in e for e in r.run.errors), \
        r.run.errors[:3]
    lines = _lines(r.out)
    warn = [m.group(4) for m in lines if m.group(2) == 'WARN' and m.group(3) == 'CLOSE']
    nothing = [w for w in warn if w.startswith('the close of the BUY trade closed nothing')]
    assert len(nothing) == 1 and 'the trade stays booked, and the close is decided again next poll' in nothing[0]
    assert not any('is incomplete: 0 closed, 0 failed' in w for w in warn)
    first = next(s for s in r.snaps if s['decision']['action'] == 'CLOSE_BUY')
    assert 'The close closed nothing' in first['decision']['headline'] and first['turtle']['trade']
    closes = [m.group(4) for m in lines if m.group(2) == 'CLOSE' and m.group(3) == 'CLOSE']
    assert len(closes) == 1 and closes[0].startswith('the BUY trade closed: its 4 leg(s), on the next try (the close '
                                                     'at the stop ')
    assert 'had closed nothing)' in closes[0] and 'reason=turtle_stop' in closes[0]
    trade = r.trades[-1]['closed'][-1]
    assert trade['exit_reason'] == 'turtle_stop'


@pytest.mark.slow
def test_legs_gone_before_a_close_that_closed_nothing_end_the_trade_next_poll(tmp_path):
    """The broker closes every leg between the poll's positions read and the stop's close, which closes nothing; the
    next poll finds the legs gone and ends the trade (app.py: not as closed outside the bot, its close was decided).
    The log says both: the close that closed nothing, then the end of the trade and why."""
    switched = []

    def broker_closes_all(f):
        for p in list(f.positions):
            f.close_by_broker(p['ticket'])
    r = _replay(tmp_path, on_bot=_inside_the_close(switched, broker_closes_all))
    assert switched and not r.run.errors, r.run.errors[:3]
    lines = _lines(r.out)
    assert sum(m.group(2) == 'WARN' and m.group(4).startswith('the close of the BUY trade closed nothing')
               for m in lines) == 1
    ended = [m.group(4) for m in lines if m.group(2) == 'CLOSE' and 'had closed nothing, so they were closed outside '
             'the bot first' in m.group(4)]
    assert len(ended) == 1 and ended[0].startswith('the BUY trade ended: its 4 leg(s) are gone')
    assert 'the bot ends the trade (not booked as closed outside it)' in ended[0] and 'after_close_of=turtle_stop' in ended[0]
    assert 'TURTLE_CLOSED_OUTSIDE' not in {e['event'] for e in r.run.events}
