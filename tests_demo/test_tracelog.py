"""
The bot side of the dashboard's data contract (tracelog.py, docs/dashboard-data.md), on a real-money branch.

A fake-terminal replay of the scaled design (entries, a one-unit add, stops, a target, the loss pause) with the real
writers: <SYMBOL>_trace.json, _bars.json, _trades.json, logs/<SYMBOL>_<day>.log and <day>_events.jsonl appear with the
right content, next to the files of the old dashboard; the trace changes no decision (the same polls, requests and
fills with it switched off); a disk that fails does not stop the trading; a hook that raises is an ERROR with its
traceback in the log; a heartbeat line every minute. The account is a real one (the fake terminal's: login
F.ACCOUNT_LOGIN): the figures are the account's own, and its number is in no file but as its last four digits.
(The files that grow and what bounds them: test_retention.py; the permanent journal: test_journal.py; the trace's
real-money sections and the orders held back: test_trace_live.py.)
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

from conftest import DEFAULTS, F, MAGIC, SCALED, START, baskets, deals_of, market, run_bot
from conftest import differs, found

SYMBOL = 'XAUUSDm'
SECONDS, SEED = 1200, 4          # 20 minutes: a 2-leg basket stopped out, the 4-min loss pause, a target
DESIGN = dict(SCALED)            # XAU Top 1 shape on fast timeframes (conftest): M1 votes, M5 trend, M1 volatility unit
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
LINE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) UTC \| (DEBUG|INFO|ORDER|FILL|CLOSE|WARN|ERROR) \| '
                  r'([A-Z_]+) \| (.+)$')
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]             # all a file may show of the bot's account number
OTHER_LOGIN = 87654321                               # another account a terminal can hold (its tail: ...4321)
OTHER_TAIL = '...4321'
EVENTS = f'{SYMBOL}_{DAY}_events.jsonl'              # the events day file of the replay's day


def _no_account_number(text):
    """The bot's full account number is in no text the trace wrote (only its tail)."""
    assert not found(text, str(F.ACCOUNT_LOGIN)) and not found(text, str(OTHER_LOGIN))


def _read_log(folder, symbol=SYMBOL):
    path = os.path.join(str(folder), 'logs', f'{symbol}_{DAY}.log')
    with open(path, encoding='utf-8') as f:
        return f.read().splitlines()


def _parsed(lines):
    """[(match or None, line)]: None for the indented traceback lines after an ERROR."""
    return [(LINE.match(ln), ln) for ln in lines]


def _replay(tmp, *, trace=True, keep_writers=True, out=None, hook=None, seconds=SECONDS, seed=SEED, overrides=None):
    """One replay; with the trace on, its trace file is read after every poll, the bars / trades files whenever they
    change, and the time of every poll hook is measured (real time)."""
    fake, clock = market(seconds, seed=seed)
    out = str(out or (tmp / 'out'))
    r = types.SimpleNamespace(fake=fake, out=out, snaps=[], bars_t=[], trades=[], costs=[], bots=[], handed=[])
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
        real = bot._trace

        def spy(symbol, method, *a, **k):
            t0 = time.perf_counter()
            real(symbol, method, *a, **k)
            if method not in ('poll', 'poll_skipped') or not trace:
                return
            if method == 'poll':
                r.costs.append((time.perf_counter() - t0) * 1000.0)
                # which of the real-money hand-overs this poll's locals held (app.py supplies them by name)
                r.handed.append({k for k in ('_sizing', '_safety', '_open_hold', '_foreign')
                                 if isinstance(a[0].get(k), dict)})
            base = bot.trace_dir or out
            try:
                with open(os.path.join(base, f'{symbol}_trace.json'), encoding='utf-8') as f:
                    r.snaps.append(json.load(f))
            except OSError:
                pass
            for name, sink in (('bars', r.bars_t), ('trades', r.trades)):
                p = os.path.join(base, f'{symbol}_{name}.json')
                if changed(p):
                    with open(p, encoding='utf-8') as f:
                        doc = json.load(f)
                    sink.append(doc['t'] if name == 'bars' else doc)
        bot._trace = spy
        if hook is not None:
            hook(bot, n)

    r.run = run_bot(fake, clock, overrides={**DESIGN, 'OUTPUT_DIR': out, **(overrides or {})}, symbol=SYMBOL,
                    state_dir=tmp / 'state', keep_writers=keep_writers, on_new_bot=on_new_bot)
    end_of_job(r.bots)
    return r


def end_of_job(bots):
    """The replay stops mid-poll (StopRun); a real job ends through execute_job, whose last lines make the trace write
    what it still holds -- here, an order sent in the last 0.1 s, its lines made inside mt5_lock."""
    for bot in bots:
        for tr in list((getattr(bot, '_tracers', None) or {}).values()):
            tr._flush()


@pytest.fixture(scope='module')
def traced(tmp_path_factory):
    return _replay(tmp_path_factory.mktemp('traced'))


@pytest.fixture(scope='module')
def untraced(tmp_path_factory):
    """The same replay with the trace switched off and the old writers recording instead of writing."""
    return _replay(tmp_path_factory.mktemp('untraced'), trace=False, keep_writers=False)


def _sl_of(fake):
    """position id -> the broker sl its opening request carried."""
    req = {o['_t_ms']: o for o in fake.orders if 'position' not in o}
    return {d.position_id: req[d.time_msc].get('sl') for d in fake.deals if d.entry == 0 and d.time_msc in req}


# ───────────────────────────── the trace changes nothing ─────────────────────────────

@pytest.mark.slow
def test_the_trace_changes_no_decision(traced, untraced):
    """The same polls, requests and fills with the trace and the real writers as without them."""
    assert not traced.run.errors, traced.run.errors[:3]
    assert not untraced.run.errors, untraced.run.errors[:3]
    assert not differs(traced.run.polls, untraced.run.polls)
    assert not differs(traced.fake.orders, untraced.fake.orders)
    assert not differs(deals_of(traced.fake), deals_of(untraced.fake))
    b = baskets(traced.fake, magic=MAGIC)
    assert len(b) >= 3 and any(len(x['legs']) == 2 for x in b)        # an add was made
    assert any(x['pnl'] < 0 for x in b) and any(x['pnl'] > 0 for x in b)  # stopped out, and a target
    assert not os.listdir(untraced.bots[0].trace_dir)                  # switched off: no file at all


@pytest.mark.slow
def test_the_trace_costs_about_a_millisecond_per_poll(traced):
    c = sorted(traced.costs)
    med, p95, p99 = statistics.median(c), c[int(len(c) * 0.95)], c[int(len(c) * 0.99)]
    print(f'\ntrace hook per poll (real time, fake terminal): median {med:.2f} ms, p95 {p95:.2f} ms, p99 {p99:.2f} ms, '
          f'max {c[-1]:.2f} ms over {len(c)} polls')
    assert med < 5.0 and p95 < 25.0
    tr = traced.bots[-1]._tracers[SYMBOL]
    assert tr.cost_ms is not None and traced.snaps[-1]['health']['trace_ms'] is not None


# ───────────────────────────── 1. <SYMBOL>_trace.json ─────────────────────────────

@pytest.mark.slow
def test_the_trace_file_is_the_poll_decision(traced):
    tl = traced.run.mods.tracelog
    snaps, polls = traced.snaps, traced.run.polls
    assert len(snaps) == len(polls)
    for s, p in zip(snaps, polls):
        assert (s['schema'], s['symbol'], s['magic'], s['strategy'], s['turtle']) == (1, SYMBOL, MAGIC, 'basket', None)
        assert s['branch'] == DEFAULTS['BRANCH'] and s['design'] == DESIGN['DESIGN_NAME'] and not s['stale']
        assert (s['mode'], s['version']) == ('live', DEFAULTS['VERSION'])
        assert s['t'] * 1000 >= p['t'] and s['time_utc'].endswith('Z')
        h = s['health']
        assert h['connected'] and h['account_ok'] and h['market_live'] and h['errors_1h'] == 0
        # a real, hedging account; its number as its tail only (the terminal's, and the one of the credentials)
        assert (h['trade_mode_name'], h['margin_mode_name'], h['login_tail'], h['own_login_tail']) == (
            'real', 'hedging', TAIL, TAIL)
        assert 'login' not in h and 'demo_login' not in h
        assert h['trading_not_allowed'] == [] and h['disk_low'] is False and h['ping_ms'] is not None
        assert h['loop_ms'] is not None and h['last_tick_age_s'] is not None and h['reconnects'] == 0
        a = s['account']
        assert a['units'] == p['units'] and a['lot'] == round(p['units'] * 0.01, 2)
        assert (a['login_tail'], a['server'], a['currency'], a['trade_allowed']) == (TAIL, F.ACCOUNT_SERVER, 'USD', True)
        assert a['balance'] is not None and a['equity'] is not None and a['leverage'] == traced.fake.leverage
        # this bot's open P/L (its magic only), and the whole account's: here the same, the bot trades alone
        assert a['floating_own'] == a['own_open_pl'] == (p['profit'] if p['nb'] + p['ns'] else 0.0)
        assert a['floating_account'] == a['account_profit']
        # how the unit was sized is the poll's own record; the next unit counts with the share of the balance
        assert s['sizing'] == json.loads(json.dumps(p['sizing']))
        assert a['next_unit_at'] == p['sizing']['next_unit_at_account_balance'] and f"{a['share']:g} x account" in a['unit_rule']
        assert not [k for k in a if 'virtual' in k]
        d = s['decision']
        assert d['action'] in tl.ACTIONS and d['headline'] and d['signal'] == {'buy': p['buy'], 'sell': p['sell']}
        assert [g['key'] for g in d['gates']][:4] == ['terminal', 'account', 'positions', 'market_live']
        for g in d['gates']:
            assert {'key', 'name', 'role', 'ok', 'value', 'need', 'note', 'checked'} <= set(g)
            assert g['ok'] in (True, False, None) and g['role'] in ('need', 'exit', 'add', 'info')
        # the action follows the strategy's signal
        sig = {p['buy'], p['sell']} - {'DO_NOTHING'}
        want = {'BUY': ('OPEN_BUY', 'BLOCKED', 'OPEN_FAILED'), 'SELL': ('OPEN_SELL', 'BLOCKED', 'OPEN_FAILED'),
                'CLOSE_BUY': ('CLOSE_BUY',), 'CLOSE_SELL': ('CLOSE_SELL',), 'BUY_MORE': ('ADD_BUY',),
                'SELL_MORE': ('ADD_SELL',)}
        if sig:
            assert d['action'] in want[sig.pop()], (d['action'], p)
        else:
            assert d['action'] in ('WAIT', 'PAUSED', 'HOLD', 'WAIT_FILL'), (d['action'], p)
        # the basket strategy's numbers are the poll's
        b = s['basket']
        assert (b['open_score'], b['fc_score'], b['entry_s'], b['entry_agree_s']) == (
            p['open_score'], p['fc_score'], 2, DESIGN['ENTRY_AGREE_S'])
        assert b['trend']['tf'] == 'M5' and b['trend']['sign'] == p['trend'] and b['vol']['raw'] == p['vol']
        assert b['vol']['bars_used'] == 499 and b['vol']['known'] and b['contract_size'] == 100.0
        for tf, (r, m) in p['votes'].items():
            v = b['votes'][tf]
            assert (v['rsi']['vote'], v['macd']['vote']) == (r or 0, m or 0)
            assert v['rsi']['now'] is not None and len(v['rsi']['series']) == len(v['t']) == 40
        assert b['votes']['M1']['open_contrib'] is not None and b['votes']['M1']['fc_contrib'] == sum(
            x or 0 for x in p['votes']['M1'])
    actions = Counter(s['decision']['action'] for s in snaps)
    for a in ('HOLD', 'PAUSED', 'WAIT', 'BLOCKED'):
        assert actions[a], actions
    assert actions['OPEN_BUY'] + actions['OPEN_SELL'] >= 3 and actions['ADD_BUY'] + actions['ADD_SELL'] == 1
    assert actions['CLOSE_BUY'] + actions['CLOSE_SELL'] == len(baskets(traced.fake, magic=MAGIC))
    # what app.py hands over by name is in the trace on that very poll: never null when the poll had it
    polled = [s for s in snaps if s['decision']['action'] != 'SKIPPED']
    assert len(polled) == len(traced.handed)
    for s, had in zip(polled, traced.handed):
        assert '_sizing' in had and s['account'] is not None
        for name in had:
            assert s[name[1:]] is not None, name
        for name in {'_sizing', '_safety', '_open_hold', '_foreign'} - had:
            assert s[name[1:]] is None, name
    _no_account_number(json.dumps(snaps[-1]))


@pytest.mark.slow
def test_the_trace_shows_the_open_basket_with_its_prices(traced):
    """In a basket: legs, P/L, the fixed stop and target in USD (the bot's) and as the prices they mean, the broker
    backstop of every leg, the ladder's next add price."""
    sl_of = _sl_of(traced.fake)
    held = [(s, p) for s, p in zip(traced.snaps, traced.run.polls) if s['decision']['action'] == 'HOLD']
    assert len(held) > 100
    two = 0
    for s, p in held:
        o = s['basket']['open']
        legs = o['legs']
        assert len(legs) == p['nb'] + p['ns'] and o['side'] == ('BUY' if p['nb'] else 'SELL')
        assert o['pnl'] == p['profit'] and (o['stop_usd'], o['target_usd'], o['units']) == (
            p['levels']['stop_usd'], p['levels']['target_usd'], p['levels']['units'])
        lots = sum(x['lots'] for x in legs)
        avg = sum(x['price'] * x['lots'] for x in legs) / lots
        k = lots * 100.0                                    # USD per 1.0 move of the basket (gold)
        buy = o['side'] == 'BUY'
        sl, tg = o['stop_usd_per_unit'] * o['units'], o['target_usd_per_unit'] * o['units']    # (not cent-rounded)
        assert o['stop_price'] == pytest.approx(avg - sl / k if buy else avg + sl / k, abs=6e-4)   # 3 digits
        assert o['target_price'] == pytest.approx(avg + tg / k if buy else avg - tg / k, abs=6e-4)
        assert o['judged_on'] == ('bid' if buy else 'ask')
        assert o['backstop_prices'] == [sl_of[x['id']] for x in legs]
        assert o['to_stop_usd'] == pytest.approx(o['pnl'] + o['stop_usd'], abs=0.011)
        g = {x['key']: x for x in s['decision']['gates']}
        assert g['stop']['ok'] is False and g['target']['ok'] is False and g['force_close']['ok'] is None
        lad = o['ladder']
        if len(legs) == 1:
            assert lad['on'] and lad['tier_tf'] == 'M1' and lad['gap_px'] == pytest.approx(p['levels']['gap_px'])
            nxt = legs[0]['price'] - lad['gap_px'] if buy else legs[0]['price'] + lad['gap_px']
            assert lad['next_add_price'] == pytest.approx(nxt) and lad['armed'] == p['ladder_armed']
        else:
            two += 1
            assert lad['exhausted'] and lad['next_add_price'] is None
    assert two > 0
    # at the close the exit that fired is the bot's exit reason
    for s, p in zip(traced.snaps, traced.run.polls):
        if s['decision']['action'] in ('CLOSE_BUY', 'CLOSE_SELL'):
            g = {x['key']: x for x in s['decision']['gates']}
            fired = {'stop_loss': 'stop', 'target': 'target'}[p['exit_reason']]
            assert g[fired]['ok'] is True and s['decision']['blocked_by'] == fired and s['decision']['reason'] == p['exit_reason']
    # the prices the trace gives are the bot's own exits: at every close by the stop or the target the judged quote is
    # through that price, and on the poll before it was not (not a copy of the trace's formula: the bot's P/L test)
    closes = 0
    for prev, s, p in zip(traced.snaps, traced.snaps[1:], traced.run.polls[1:]):
        if s['decision']['action'] not in ('CLOSE_BUY', 'CLOSE_SELL') or p['exit_reason'] not in ('stop_loss', 'target'):
            continue
        o, o0 = s['basket']['open'], prev['basket']['open']
        if not o0 or o0.get('side') != o.get('side'):
            continue
        buy = o['side'] == 'BUY'
        q, q0 = (s['market']['bid'], prev['market']['bid']) if buy else (s['market']['ask'], prev['market']['ask'])
        level = o['stop_price'] if p['exit_reason'] == 'stop_loss' else o['target_price']
        assert level == o0[{'stop_loss': 'stop_price', 'target': 'target_price'}[p['exit_reason']]]
        down = (p['exit_reason'] == 'stop_loss') == buy          # a buy's stop / a sell's target: the quote falls to it
        tol = 2e-3                                             # (the prices are rounded to the symbol's 3 digits)
        if down:
            assert q <= level + tol and q0 > level - tol, (p['exit_reason'], o['side'], q, q0, level)
        else:
            assert q >= level - tol and q0 < level + tol, (p['exit_reason'], o['side'], q, q0, level)
        closes += 1
    assert closes >= 2


@pytest.mark.slow
def test_the_trace_explains_waits_pauses_blocks_and_new_basket_levels(traced):
    snaps = traced.snaps
    for s in snaps:
        d, b = s['decision'], s['basket']
        g = {x['key']: x for x in d['gates']}
        if d['action'] == 'PAUSED':
            p = b['pause']
            assert p['active'] and g['pause']['ok'] is False and d['blocked_by'] == 'pause'
            assert p['length_s'] == (240.0 if p['last_close']['lost'] else 30.0)
            assert p['until'] == pytest.approx(p['last_close']['t'] + p['length_s'])
            assert 0 < p['left_s'] <= p['length_s'] and 'Paused' in d['headline']
        if d['action'] == 'BLOCKED' and d['reason'] == 'trend':
            side = 1 if d['side'] == 'BUY' else -1
            assert g['trend']['ok'] is False and side * b['trend']['sign'] <= 0 and d['blocked_by'] == 'trend'
            assert all(g[k]['ok'] for k in ('pause', 'open_score', 'agreement', 'window', 'votes_known'))
        if d['action'] == 'WAIT':
            assert d['blocked_by'] in ('open_score', 'agreement')
        if d['action'] in ('WAIT', 'PAUSED', 'BLOCKED'):
            nb = b['new_basket']
            v, u = b['vol']['raw'], nb['units']
            assert nb['stop_usd'] == pytest.approx(round(DESIGN['STOP_VOL'] * v * u, 2))
            assert nb['target_usd'] == pytest.approx(round(DESIGN['TARGET_VOL'] * v * u, 2))
            ask, bid = s['market']['ask'], s['market']['bid']
            assert nb['buy']['stop'] == pytest.approx(ask - DESIGN['STOP_VOL'] * v, abs=1e-3)
            assert nb['sell']['target'] == pytest.approx(bid - DESIGN['TARGET_VOL'] * v, abs=1e-3)
            assert nb['backstop_px'] == pytest.approx(2.0 * DESIGN['STOP_VOL'] * v)
    opened = [s for s in snaps if s['decision']['action'] in ('OPEN_BUY', 'OPEN_SELL')]
    for s in opened:
        o, fill = s['basket']['open'], s['decision']['orders'][0]
        assert fill['kind'] == 'open' and fill['done'] and fill['retcode'] == 10009 and fill['magic'] == MAGIC
        assert o['legs'][0]['price'] == fill['result_price'] and o['backstop_prices'] == [fill['sl']]
        assert 'Opened a' in s['decision']['headline']


@pytest.mark.slow
def test_a_poll_that_could_not_read_the_terminal_is_in_the_trace(tmp_path):
    """The terminal is gone for 30 s: the trace says SKIPPED (stale account / basket kept), the health says why; the
    log has the skip, the reconnect attempts and the account checks of the reconnect."""
    def hook(bot, n):
        bot.position_helper.mt5.down(START + 60, START + 90)
    r = _replay(tmp_path, seconds=240, hook=hook)
    skipped = [s for s in r.snaps if s['decision']['action'] == 'SKIPPED']
    assert len(r.snaps) > len(r.run.polls) and skipped
    assert any(s['basket'] is not None for s in skipped)                         # the last good poll's numbers
    good = [s for s in r.snaps if s['decision']['action'] != 'SKIPPED' and s['t'] < skipped[0]['t']][-1]
    for s in skipped:
        # the sizing (and the safety's view, what else is on the account) are the last good poll's; nothing was
        # held back on a poll that decided nothing
        assert s['sizing'] == good['sizing'] is not None and s['account'] == good['account']
        assert (s['safety'], s['foreign'], s['open_hold']) == (good['safety'], good['foreign'], None)
        assert s['stale'] and not s['health']['connected'] and 'terminal_info()' in s['health']['terminal_problem']
        assert s['decision']['gates'][0]['key'] == 'terminal' and s['decision']['gates'][0]['ok'] is False
        # ... marked as such: the market is not known this poll (its quote is the last one read), no vote was computed
        assert s['health']['market_live'] is None
        assert s['market']['status'] == 'UNKNOWN' and 'the terminal was not read this poll' in s['market']['message']
        assert s['market']['bid'] is not None and (s['basket'] is None or s['basket']['fresh'] is False)
    assert r.snaps[-1]['health']['reconnects'] == 1 and r.snaps[-1]['health']['connected']
    lines = _read_log(r.out)
    text = '\n'.join(lines)
    for needle in ('-> SKIPPED: Poll skipped, nothing decided: terminal_info() returned None', '| WARN | TERMINAL |',
                   '| ERROR | TERMINAL | reconnect failed', '| ERROR | TERMINAL | MT5 initialize failed',
                   '| INFO | TERMINAL | connected to the terminal again',
                   '| INFO | TERMINAL | the terminal answers again'):
        assert needle in text, needle
    # the terminal came back holding this bot's account: no login, and the account checks of the reconnect are in
    # the log, the account as its tail
    assert any('| INFO | ACCOUNT | ' in ln and 'checks passed' in ln and TAIL in ln for ln in lines)
    assert 'login' not in [c[0] for c in r.fake.calls]
    _no_account_number(text)


# ───────────────────────────── 2. <SYMBOL>_bars.json ─────────────────────────────

@pytest.mark.slow
def test_the_bars_file(traced):
    with open(os.path.join(traced.out, f'{SYMBOL}_bars.json'), encoding='utf-8') as f:
        doc = json.load(f)
    assert (doc['schema'], doc['symbol'], doc['price'], doc['digits']) == (1, SYMBOL, 'bid', 3)
    assert doc['counts'] == {'M1': 360, 'M5': 300, 'M15': 300, 'H1': 300, 'D1': 31}      # D1: the fake's 30 days
    assert doc['source'] == {'M1': 'poll', 'M5': 'poll', 'M15': 'poll', 'H1': 'poll', 'D1': 'terminal'}
    for tf, v in doc['tf'].items():
        t = v['t']
        assert t == sorted(set(t)) and all(x % F.TF_SECONDS[tf] == 0 for x in t)
        assert len(v['o']) == len(v['h']) == len(v['l']) == len(v['c']) == len(t)
        for o, h, lo, c in zip(v['o'], v['h'], v['l'], v['c']):
            assert lo <= min(o, c) and max(o, c) <= h
        ref = traced.fake.bars[tf].last(len(t), upto_t=t[-1])             # the terminal's bars at the export
        assert ref['time'].tolist() == t
        assert np.allclose(ref['close'][:-1], v['c'][:-1], atol=6e-4)     # closed bars (rounded to the 3 digits)
    # rewritten at most every 30 s, and kept fresh while the market moves (a poll is 1 s, 2.1 s with an add)
    gaps = np.diff(traced.bars_t)
    assert len(traced.bars_t) >= SECONDS // 33 and gaps.min() >= 30.0 and gaps.max() <= 33.0


# ───────────────────────────── 3. <SYMBOL>_trades.json ─────────────────────────────

@pytest.mark.slow
def test_the_trades_file(traced):
    with open(os.path.join(traced.out, f'{SYMBOL}_trades.json'), encoding='utf-8') as f:
        doc = json.load(f)
    b = baskets(traced.fake, magic=MAGIC)
    closed = doc['closed']
    assert (doc['schema'], doc['magic']) == (1, MAGIC)
    # real numbers only: no balance of the bot's own is made up, and the read starts a day before its live start
    assert not [k for k in doc if 'virtual' in k] and not found(json.dumps(doc['summary']), 'virtual')
    live = doc['live_start_t']
    # app.py's state/live_start.json (the first poll of the replay): the read starts a day before it, and every
    # trade of the view is one since it
    assert live is not None and START <= live <= START + 5 and doc['since_t'] == live - 86400.0
    assert all(x['open_t'] >= live for x in closed)
    assert doc['live_start_utc'] == datetime.fromtimestamp(live, tz=timezone.utc).isoformat(
        timespec='milliseconds').replace('+00:00', 'Z')
    assert len(closed) == len(b)
    for x, y in zip(closed, b):
        assert x['side'] == ('BUY' if y['side'] == 0 else 'SELL') and len(x['legs']) == len(y['legs'])
        assert x['pnl'] == y['pnl'] and x['status'] == 'closed'
        assert x['open_t'] == pytest.approx(y['t_open']) and x['close_t'] == pytest.approx(y['t_close'])
        lots = sum(leg['vol'] for leg in y['legs'])
        assert x['lots'] == round(lots, 2)
        assert x['open_price'] == pytest.approx(sum(leg['price_in'] * leg['vol'] for leg in y['legs']) / lots, abs=6e-4)
        assert [leg['position_id'] for leg in x['legs']] == [leg['pid'] for leg in y['legs']]
        # profit, swap, commission and fee apart; together they are the trade's P/L in dollars
        assert x['pnl'] == pytest.approx(x['profit'] + x['swap'] + x['commission'] + x['fee'])
        assert all({'profit', 'swap', 'commission', 'fee', 'net'} <= set(leg) for leg in x['legs'])
    reasons = [e['details']['reason'] for e in traced.run.events if e['event'] in ('CLOSE_BUY', 'CLOSE_SELL')]
    assert [x['bot_reason'] for x in closed] == reasons
    assert [x['exit_reason'] for x in closed] == [{'stop_loss': 'stop', 'target': 'target'}[r] for r in reasons]
    # the running total of the bot's own closed P/L, from 0, after every closed trade; its deepest fall in dollars
    curve = doc['balance_curve']
    run, top, fall = 0.0, 0.0, 0.0
    assert curve[0]['v'] == 0.0 and curve[0]['id'] is None and len(curve) == len(closed) + 1
    assert curve[0]['t'] == (live if live is not None else doc['since_t'])
    for pt, x in zip(curve[1:], closed):
        run = round(run + x['pnl'], 2)
        assert pt['v'] == run == x['balance_after'] and pt['t'] == x['close_t']
        top = max(top, run)
        fall = max(fall, top - run)
    sm = doc['summary']
    assert sm['balance_now'] == run == sm['net'] and sm['closed'] == len(closed)
    assert sm['wins'] + sm['losses'] == len(closed)
    assert sm['deepest_fall'] == pytest.approx(fall, abs=0.005) and fall > 0 and sm['deepest_fall_to_t'] is not None
    # the trace's account block has the same total (from the last read of the deal history), and the real balance
    flat = [s for s in traced.snaps if s['basket']['open'] is None]
    assert flat[-1]['account']['own_closed_pl'] == run
    assert flat[-1]['account']['balance'] == pytest.approx(traced.fake.balance)
    # refreshed at every fill and close (and the poll after), at least every 60 s
    t_docs = [d['t'] for d in traced.trades]
    assert max(np.diff(t_docs)) <= 62.5
    # read at the end of the poll of every fill and close: 0.1 s after the order, 1.1 s after an add (its 1 s
    # cooldown); an order in the run's last seconds never reaches its poll's end (the replay's clock stops first)
    fills = sorted({o['_t_ms'] / 1000.0 for o in traced.fake.orders if o['_t_ms'] < (START + SECONDS - 2) * 1000})
    assert fills
    for t in fills:
        assert any(0.0 <= td - t <= 1.2 for td in t_docs), t
    # an open basket is listed with its live levels
    open_docs = [d for d in traced.trades if d['open']]
    assert open_docs and all(d['open'][0]['live'] and d['open'][0]['stop_price'] for d in open_docs)


def test_exit_reasons_of_baskets_closed_outside_the_bot(mods, tmp_path):
    """A leg closed by the broker's stop is 'backstop', one closed from the terminal 'closed outside the bot'; the bot's
    own record wins; overlapping legs of one side are one basket; the running total of the bot's closed P/L adds
    every deal, from 0 (no balance of its own is made up), and its deepest fall is in dollars."""
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    bot = F.make_bot(m, fake, SYMBOL, F.Run(), trace_dir=tmp_path)
    tr = bot._tracer(SYMBOL)
    now = clock.time()

    def deal(pid, entry, typ, vol, price, profit, t, reason, magic=MAGIC):
        return types.SimpleNamespace(ticket=len(deals) + 1, order=0, time=int(t), time_msc=int(t * 1000), type=typ,
                                     entry=entry, magic=magic, position_id=pid, reason=reason, volume=vol, price=price,
                                     commission=0.0, swap=0.0, profit=profit, fee=0.0, symbol=SYMBOL, comment='')
    deals = []
    for d in [(1, 0, 0, 0.01, 2000.0, 0.0, now - 900, 3), (1, 1, 1, 0.01, 1990.0, -10.0, now - 800, 4),    # sl
              (2, 0, 1, 0.01, 2000.0, 0.0, now - 700, 3), (2, 1, 0, 0.01, 1995.0, 5.0, now - 600, 0),       # manual
              (3, 0, 0, 0.01, 2000.0, 0.0, now - 500, 3), (4, 0, 0, 0.01, 1990.0, 0.0, now - 450, 3),       # 2 legs
              (3, 1, 1, 0.01, 2010.0, 10.0, now - 400, 3), (4, 1, 1, 0.01, 2010.0, 20.0, now - 400, 3)]:
        deals.append(deal(*d))
    tr._record_exits([3, 4], 'target', now - 400)
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 1000, now, 3)
    got = [(x['id'], len(x['legs']), x['exit_reason'], x['pnl']) for x in doc['closed']]
    assert got == [(1, 1, 'backstop', -10.0), (2, 1, 'closed_outside', 5.0), (3, 2, 'target', 30.0)]
    assert [p['v'] for p in doc['balance_curve']] == [0.0, -10.0, -5.0, 25.0]
    assert doc['summary']['exit_reasons'] == {'backstop': 1, 'closed_outside': 1, 'target': 1}
    assert (doc['summary']['net'], doc['summary']['balance_now'], doc['summary']['deepest_fall']) == (25.0, 25.0, 10.0)
    assert doc['summary']['deepest_fall_to_t'] == pytest.approx(now - 800)
    assert (doc['live_start_t'], doc['since_t']) == (None, now - 1000) and not found(json.dumps(doc), 'virtual')
    # with the bot's live start known, the curve begins there, and a commission and a fee are two figures
    deals[1].commission, deals[1].fee = -0.25, -0.1
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 1000, now, 3, now - 950)
    first = doc['closed'][0]
    assert (first['profit'], first['commission'], first['fee'], first['pnl']) == (-10.0, -0.25, -0.1, -10.35)
    assert (doc['balance_curve'][0]['t'], doc['live_start_t']) == (now - 950, now - 950)
    with open(tmp_path / 'state' / f'{SYMBOL}_exit_reasons.json', encoding='utf-8') as f:
        assert json.load(f)['reasons']['3']['reason'] == 'target'


def test_a_basket_the_backstop_closed_while_the_bot_was_down(tmp_path):
    """The bot starts with a state file holding a BUY basket whose position the broker's stop closed meanwhile: the
    first poll books it as closed outside the bot; the log says so (CLOSE, then the pause from the deal history) and
    trades.json gives the exit reason 'backstop'."""
    fake, clock = market(30)
    pid = fake.add_position(0, 0.01, 1999.0, START - 600, magic=MAGIC, comment='its own')
    fake.positions.clear()
    fake.add_deal(pid, 1, 1, 0.01, 1990.0, -9.0, START - 100, magic=MAGIC)
    fake.deals[-1].reason = fake.DEAL_REASON_SL
    basket = {'target_usd_per_unit': 1, 'stop_usd_per_unit': None, 'gap_px': 0.0, 'vol_unit_raw': None, 'vol_unit': None,
              'side': 'BUY', 'units': 1, 'ids': [pid], 'first_time': START - 600, 'opened_at': START - 600,
              'opened_by': 'bot', 'ladder_armed': False, 'close_pending': False, 'levels_pending': False,
              'vol_source': None, 'last_profit': -8.5}
    (tmp_path / 'state').mkdir()
    with open(tmp_path / 'state' / f'{SYMBOL}_state.json', 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'symbol': SYMBOL, 'magic': MAGIC, 'design': 'live', 'saved_at': START - 200,
                   'basket': basket, 'last_close': None}, f)
    run = run_bot(fake, clock, symbol=SYMBOL, state_dir=tmp_path / 'state', trace_dir=tmp_path / 'out')
    assert not run.errors
    text = '\n'.join(_read_log(tmp_path / 'out'))
    assert '| INFO | STATE | state restored: BUY basket (opened by bot, 1 position(s)' in text
    assert ('| CLOSE | CLOSE | the BUY basket was closed outside the bot (the broker\'s backstop, the terminal, or while '
            'the bot was down): realised -$9.00, its last closing deal at 2026-11-17 07:58:20 UTC (deal history)') in text
    assert '| INFO | PAUSE | entry pause started: 5.0 min after a close (loss -$9.00), until 2026-11-17 08:03:20 UTC' in text
    with open(tmp_path / 'out' / f'{SYMBOL}_trades.json', encoding='utf-8') as f:
        doc = json.load(f)
    assert [(x['id'], x['exit_reason'], x['pnl']) for x in doc['closed']] == [(pid, 'backstop', -9.0)]


# ───────────────────────────── 4. the text log and the events file ─────────────────────────────

@pytest.mark.slow
def test_the_text_log(traced):
    lines = _read_log(traced.out)
    parsed = _parsed(lines)
    assert all(m for m, _ in parsed), [ln for m, ln in parsed if not m][:3]       # a clean run: no traceback
    ms = [m for m, _ in parsed]
    levels = Counter(m.group(2) for m in ms)
    assert levels['ERROR'] == 0 and levels['WARN'] == 0, [m.group(0) for m in ms if m.group(2) in ('WARN', 'ERROR')][:3]
    text = '\n'.join(lines)
    # start-up: branch, design, every effective constant, symbols.json, the state found
    assert f"branch={DEFAULTS['BRANCH']}" in text and f"design={DESIGN['DESIGN_NAME']}" in text
    assert f"version={DEFAULTS['VERSION']}" in text and ' mode=live ' in text
    names = {n for n in vars(traced.run.mods.constants) if n.isupper() and not n.startswith('_')}
    config = {m.group(4).split(' = ')[0] for m in ms if m.group(3) == 'CONFIG' and ' = ' in m.group(4)}
    # ... but never the old accounts' fingerprints (nor a name that holds PIN, PASS or SECRET): in no line at all
    hidden = {'OLD_LOGINS_SHA256'}
    assert hidden <= names and names - hidden <= config, names - hidden - config
    assert not hidden & config and not found(text, 'OLD_LOGINS')
    assert not any(v in text for v in DEFAULTS['OLD_LOGINS_SHA256'])
    _no_account_number(text)
    assert '| INFO | CONFIG | TARGET_VOL = 2' in text and '| INFO | CONFIG | symbols.json: brake 0' in text
    assert '| INFO | STATE | no state file of this bot' in text
    # every order request with its result; a FILL for every open / add; a CLOSE per basket with reason and P/L
    orders = [m for m in ms if m.group(2) == 'ORDER']
    assert len(orders) == len(traced.fake.orders)
    assert all('retcode=10009' in m.group(4) and f'magic={MAGIC}' in m.group(4) for m in orders)
    assert len([m for m in ms if m.group(2) == 'FILL']) == len([o for o in traced.fake.orders if 'position' not in o])
    closes = [m for m in ms if m.group(2) == 'CLOSE']
    assert len(closes) == len(baskets(traced.fake, magic=MAGIC))
    assert all('reason=' in m.group(4) and 'decision_pnl=' in m.group(4) and 'realised_pnl=' in m.group(4) for m in closes)
    assert any('basket closed (stop)' in m.group(4) for m in closes) and any('basket closed (target)' in m.group(4) for m in closes)
    for needle in ('| INFO | PAUSE | entry pause started: 4.0 min after a losing basket', '| INFO | PAUSE | entry pause over',
                   '| INFO | BASKET | SELL basket opened' if 'SELL basket opened' in text else '| INFO | BASKET | BUY basket opened',
                   '| INFO | BASKET | added 0.01 lot', '| DEBUG | STATE | state saved', '-> BLOCKED: A ',
                   '| INFO | CONFIG | contract size 100.0'):
        assert needle in text, needle
    decisions = [m for m in ms if m.group(3) == 'DECISION']
    assert len(decisions) >= 20 and all(m.group(2) == 'DEBUG' and 'gates=' in m.group(4) for m in decisions)
    # a heartbeat every minute: no gap of more than a minute (and a poll) between two lines
    times = [datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S.%f') for m in ms]
    assert max((b - a).total_seconds() for a, b in zip(times, times[1:])) <= 62.5
    beats = [t for t, m in zip(times, ms) if m.group(3) == 'HEARTBEAT']
    assert len(beats) >= SECONDS // 62 and all(60.0 <= (b - a).total_seconds() <= 62.5 for a, b in zip(beats, beats[1:]))
    # the events file of the day: the same lines, as JSON
    with open(os.path.join(traced.out, 'logs', EVENTS), encoding='utf-8') as f:
        events = [json.loads(ln) for ln in f]
    assert len(events) == len(ms)
    for e, m in zip(events, ms):
        assert (e['level'], e['cat']) == (m.group(2), m.group(3)) and m.group(4).startswith(e['msg'])
        assert e['time'] == m.group(1) + ' UTC'
    assert all(isinstance(e['data']['gates'], list) for e in events if e['cat'] == 'DECISION')


@pytest.mark.slow
def test_a_close_order_names_the_side_of_its_position(traced):
    """close_by_type closes a SELL position with a BUY order: the ORDER line and the trace's orders give the side of the
    position (side) and of the order (order_side), as the dashboard shows them."""
    lines = [ln for ln in _read_log(traced.out) if '| ORDER | ORDER | close position' in ln]
    reqs = [o for o in traced.fake.orders if 'position' in o]
    assert reqs and len(lines) == len(reqs)
    by_pos = {int(re.search(r' position=(\d+)', ln).group(1)): ln for ln in lines}
    for o in reqs:
        pos_side, order_side = ('SELL', 'BUY') if o['type'] == 0 else ('BUY', 'SELL')
        ln = by_pos[o['position']]
        assert f"close position {o['position']} ({pos_side} {o['volume']} lot, with a {order_side} order)" in ln, ln
        assert f'| kind=close side={pos_side} order_side={order_side} ' in ln, ln
    sent = [x for s in traced.snaps for x in s['decision']['orders'] if x['kind'] == 'close']
    assert sent and all(x['side'] != x['order_side'] for x in sent)
    closing = [s for s in traced.snaps if any(x['kind'] == 'close' for x in s['decision']['orders'])]
    assert all(x['side'] == s['decision']['action'].split('_')[1] for s in closing for x in s['decision']['orders']
               if x['kind'] == 'close')


def test_an_add_on_the_first_poll_after_a_start_is_an_add(mods, tmp_path):
    """A restart with a basket open: its ladder add on the very first poll -- before the trace has seen a poll -- is an
    'add' in its ORDER / FILL lines (the basket loop's own state says the side it holds), an order of the other side
    or one sent flat an 'open'."""
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    bot = F.make_bot(m, fake, SYMBOL, F.Run(), trace_dir=tmp_path)
    state = {'basket': {'side': 'BUY', 'units': 1, 'ids': [7], 'opened_by': 'bot'}, 'last_close': None}
    tr = bot._tracer(SYMBOL)
    tr.loop_start({'state': state, 'sym_cfg': {}, '_rebuild_pause': False})     # the state file restored
    done = types.SimpleNamespace(retcode=10009, price=2000.5, volume=0.01, order=8, deal=9, comment='done')

    def send(typ):
        tr.order({'action': 1, 'symbol': SYMBOL, 'type': typ, 'volume': 0.01, 'price': 2000.5, 'magic': MAGIC}, done,
                 False, 2.0)
    send(0)                    # the ladder's add of the BUY basket
    send(1)                    # a SELL would be a new basket
    state['basket'] = None
    send(0)                    # flat: an entry
    tr._flush()
    lines = _read_log(tmp_path)
    assert not any('| ERROR |' in ln for ln in lines)
    orders = [ln.split(' | ')[3] for ln in lines if '| ORDER | ORDER |' in ln]
    fills = [ln for ln in lines if '| FILL | FILL |' in ln]
    assert [o.split(' ', 2)[:2] for o in orders] == [['add', 'BUY'], ['open', 'SELL'], ['open', 'BUY']], orders
    assert [('kind=add' in f, 'kind=open' in f) for f in fills] == [(True, False), (False, True), (False, True)]


def test_no_file_is_written_while_the_bot_holds_mt5_lock(mods, tmp_path):
    """The review's slow disk (250 ms a write: an antivirus scan, a saturated VPS disk). Closing a 4-leg basket inside
    mt5_lock takes no longer with the trace than without it (a few ms): the ORDER lines, and an event logged inside the
    lock, wait in memory and are written by the next write outside it (the end of the poll), every one, in order."""
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    bot = F.make_bot(m, fake, SYMBOL, F.Run(), trace_dir=tmp_path)
    bot._install_order_guard()                                           # the guard and the trace's order observer
    writes = []
    real_write = m.tracelog.LogWriter.write

    def slow_write(self, recs, **more):
        writes.append(bot.mt5_lock.locked())
        time.sleep(0.25)
        return real_write(self, recs, **more)
    m.tracelog.LogWriter.write = slow_write

    def close_four():
        for k in range(4):
            fake.add_position(0, 0.01, 2000.0 + k, clock.time() - 60, magic=MAGIC, comment='its own')
        t0 = time.perf_counter()
        with bot.mt5_lock:                                               # as process_symbol closes a basket
            res = bot.position_helper.close_by_type(SYMBOL, 0)
            bot._trace(SYMBOL, 'event', 'LEG_CLOSED_OUTSIDE', 'WARN', {'side': 'BUY', 'legs_gone': [1], 'legs_left': [2]})
        took = time.perf_counter() - t0
        assert res['closed_count'] == 4, res
        return took
    bot.trace_enabled = False
    without = min(close_four() for _ in range(3))
    bot.trace_enabled = True
    bot._tracer(SYMBOL)
    writes.clear()
    with_trace = [close_four() for _ in range(3)]
    print(f'\n4 close requests inside mt5_lock, a disk of 250 ms a write: without the trace {without * 1000:.1f} ms, with '
          f'it {min(with_trace) * 1000:.1f} ms (worst of 3: {max(with_trace) * 1000:.1f} ms)')
    assert not any(writes), 'a write while the lock was held'
    assert min(with_trace) <= without + 0.03, (with_trace, without)         # the same time: a few ms
    assert max(with_trace) < 0.5, with_trace                                # (before the fix: 4 writes, >= 1 s)
    bot._trace(SYMBOL, 'log', 'INFO', 'TEST', 'the end of the poll')     # the next write outside the lock
    assert writes == [False]
    lines = _read_log(tmp_path)
    closes = [ln for ln in lines if '| ORDER | ORDER | close position' in ln]
    assert len(closes) == 12 and all('kind=close side=BUY order_side=SELL' in ln for ln in closes)
    assert sum('| WARN | BASKET | leg(s) [1] of the BUY basket closed outside the bot' in ln for ln in lines) == 3
    assert lines[-1].endswith('| INFO | TEST | the end of the poll')


@pytest.mark.slow
def test_a_step_of_the_poll_hook_that_fails_leaves_the_others_running(tmp_path):
    """Two steps of the poll hook fail on every poll (the bars: an unexpected rates frame; the trades: a deal field it
    does not expect): each is an ERROR line (at most every 10 min); the trace file, the heartbeat and the bookkeeping go
    on; the deal history is read once a minute, not on every poll."""
    reads = []

    def hook(bot, n):
        TL = sys.modules['tracelog'].TraceLog

        def bad_bars(self, *a, **k):
            raise ValueError('boom: an unexpected rates frame')

        def bad_build(self, *a, **k):
            raise KeyError('a deal field the trace does not expect')
        real_trades, real_deals = TL._trades, bot.position_helper.get_bot_deals
        inside = []

        def trades(self, *a, **k):
            inside.append(1)
            try:
                return real_trades(self, *a, **k)
            finally:
                inside.pop()

        def deals(*a, **k):
            if inside:
                reads.append(bot.position_helper.mt5.clock.time())
            return real_deals(*a, **k)
        TL._bars, TL._build_trades, TL._trades = bad_bars, bad_build, trades
        bot.position_helper.get_bot_deals = deals
    seconds = 300
    r = _replay(tmp_path, seconds=seconds, hook=hook)
    assert not r.run.errors
    lines = _read_log(r.out)
    errs = [ln for ln in lines if '| ERROR | TRACE |' in ln]
    assert len([e for e in errs if 'failed in its step _bars: ValueError' in e]) == 1
    assert len([e for e in errs if 'failed in its step _trades: KeyError' in e]) == 1
    assert sum('| INFO | HEARTBEAT |' in ln for ln in lines) >= seconds // 62
    polled = [s for s in r.snaps if s['decision']['action'] != 'SKIPPED']
    assert len(polled) >= len(r.run.polls) - 1 and polled[-1]['t'] > START + seconds - 5
    assert polled[-1]['health']['poll_gap_s'] is not None and polled[-1]['health']['poll_gap_s'] < 5
    assert 2 <= len(reads) <= seconds // 60 + 2, reads
    assert all(b - a >= 59.0 for a, b in zip(reads, reads[1:])), reads
    assert not os.path.exists(os.path.join(r.out, f'{SYMBOL}_bars.json'))


@pytest.mark.slow
def test_the_old_dashboard_files_are_still_written(traced):
    for rel in (f'{SYMBOL}.json', 'account.json', f'logs/{SYMBOL}_strategy_log.json',
                f'daily_trade/{SYMBOL}/historical_summary.json', f"daily_trade/{SYMBOL}/17_nov_2026.json"):
        with open(os.path.join(traced.out, rel), encoding='utf-8') as f:
            assert json.load(f), rel
    with open(os.path.join(traced.out, f'{SYMBOL}.json'), encoding='utf-8') as f:
        assert json.load(f)['analysis']['design'] == DESIGN['DESIGN_NAME']


def test_a_heartbeat_every_minute_while_nothing_changes(mods, tmp_path):
    """The quotes stop after 40 s: after 3 minutes the market is not live and nothing is decided; the log still
    gets a HEARTBEAT line every minute, so a gap means the bot was not running."""
    m1, t, b, a = F.random_walk_market(START, 40, seed=3, warm_days=30)
    clock = F.FakeClock(START + 0.5, START + 600)
    fake = F.FakeMT5(SYMBOL, t, b, a, clock, warm_m1=m1, contract_size=100.0)
    run = run_bot(fake, clock, symbol=SYMBOL, state_dir=tmp_path / 'state', trace_dir=tmp_path)
    assert not run.errors
    ms = [m for m, _ in _parsed(_read_log(tmp_path)) if m]
    times = [datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S.%f') for m in ms]
    assert max((y - x).total_seconds() for x, y in zip(times, times[1:])) <= 61.0
    beats = [(t_, m) for t_, m in zip(times, ms) if m.group(3) == 'HEARTBEAT']
    assert len(beats) in (9, 10) and all(m.group(2) == 'INFO' for _, m in beats)
    assert all(abs((y[0] - x[0]).total_seconds() - 60.0) < 1.01 for x, y in zip(beats, beats[1:]))
    assert sum('MARKET_CLOSED: Market closed' in m.group(4) for _, m in beats) >= 5
    assert any(m.group(3) == 'MARKET' and 'market not live' in m.group(4) for m in ms)
    with open(tmp_path / f'{SYMBOL}_trace.json', encoding='utf-8') as f:
        s = json.load(f)
    assert s['decision']['action'] == 'MARKET_CLOSED' and s['health']['market_live'] is False
    assert s['decision']['gates'][3]['ok'] is False and s['decision']['blocked_by'] == 'market_live'


# ───────────────────────────── failures ─────────────────────────────

def _no_space(*a, **k):
    raise OSError(28, 'No space left on device')


@pytest.mark.slow
def test_a_failing_disk_does_not_stop_the_trading(tmp_path, untraced):
    """Every file of the output folder fails (it is under a file, as if the disk were gone) and so does every JSON the
    trace writes: the bot trades exactly as before; the text log (here in a folder that works) says what failed.
    (The safety's account folder, which lies beside the output folder, is kept on a disk that works: a safety that
    cannot write its files blocks new trades while it is ON, by design -- spec 5.5, test_live_safety_loop.py. What
    is tested here is that the trace's and the old dashboard's failing files change nothing.)"""
    blocker = tmp_path / 'blocker'
    blocker.write_text('a file where the output folder should be')
    trace_dir = tmp_path / 'trace'
    account = tmp_path / str(DEFAULTS['ACCOUNT_FOLDER'])

    def hook(bot, n):
        bot.trace_dir = str(trace_dir)
        sys.modules['tracelog'].write_json_atomic = _no_space
        sys.modules['app']._account_folder = lambda: str(account)
    r = _replay(tmp_path, out=blocker / 'out', hook=hook)
    assert not differs(r.run.polls, untraced.run.polls) and not differs(deals_of(r.fake), deals_of(untraced.fake))
    assert not differs(r.fake.orders, untraced.fake.orders)
    assert r.run.errors and all('could not write' in e for e in r.run.errors)    # the console says so (once a minute)
    files = {e.split('could not write ', 1)[1].split(':', 1)[0] for e in r.run.errors}
    assert len(r.run.errors) <= len(files) * (SECONDS // 60 + 1)
    assert not os.path.exists(trace_dir / f'{SYMBOL}_trace.json')
    lines = _read_log(trace_dir)
    warn = [m.group(4) for m, _ in _parsed(lines) if m and m.group(2) == 'WARN' and m.group(3) == 'WRITE']
    for what in (f'{SYMBOL}.json', 'account.json', 'the strategy log'):          # the old dashboard's files
        assert any(w.startswith(f'could not write {what}:') for w in warn), what
    for what in ('the trace', 'the bars', 'the trades', 'the exit reasons', "the journal's state"):   # the trace's own JSON
        assert any(w.startswith(f'could not write {what}:') and 'No space left' in w for w in warn), what
    assert '| WARN | SAVE | the daily-trade / history-summary files could not be saved' in '\n'.join(lines)
    kinds = {w.split(':', 1)[0] for w in warn}
    assert len(warn) <= len(kinds) * (SECONDS // 300 + 1)                         # once per 5 min and file
    # the journal and the samples are appended by the log's own writer (their folder works here): they go on, and
    # every closed trade has its line though the journal's state could not be saved
    with open(trace_dir / 'journal' / f'{SYMBOL}_{DAY[:4]}.jsonl', encoding='utf-8') as f:
        journal = [json.loads(ln) for ln in f]
    assert len([x for x in journal if x['kind'] == 'order']) == len(r.fake.orders)
    assert sorted(x['id'] for x in journal if x['kind'] == 'trade') == sorted(
        b_['legs'][0]['pid'] for b_ in baskets(r.fake, magic=MAGIC))
    assert os.path.getsize(trace_dir / 'logs' / f'{SYMBOL}_{DAY}_samples.jsonl') > 0


@pytest.mark.slow
def test_a_hook_that_raises_is_an_error_with_its_traceback(tmp_path, untraced):
    """A bug in the trace (here a step of every poll hook raises): an ERROR with the full traceback, the repeats counted
    and written again at most every 10 minutes; the trading goes on exactly as before, and so do the hook's other
    steps: the trace file (its decision TRACE_ERROR, says why), the bars, the trades and the heartbeat."""
    def hook(bot, n):
        def boom(self, *a, **k):
            raise ValueError('boom: a bug in the trace')
        sys.modules['tracelog'].TraceLog._basket_section = boom
    r = _replay(tmp_path, hook=hook)
    assert not r.run.errors and not differs(deals_of(r.fake), deals_of(untraced.fake)) and not differs(r.run.polls, untraced.run.polls)
    lines = _read_log(r.out)
    errs = [i for i, (m, _) in enumerate(_parsed(lines)) if m and m.group(2) == 'ERROR']
    assert 1 <= len(errs) <= SECONDS // 600 + 1
    first = lines[errs[0]]
    assert ("| ERROR | TRACE | the trace hook poll() failed in its step _basket_section: ValueError: boom: a bug in the "
            "trace; ignored, its other steps and the trading go on") in first
    tb = []
    for ln in lines[errs[0] + 1:]:
        if not ln.startswith('    '):
            break
        tb.append(ln[4:])
    assert tb[0] == 'Traceback (most recent call last):' and tb[-1] == 'ValueError: boom: a bug in the trace'
    assert any('in boom' in ln for ln in tb) and any('in _step' in ln for ln in tb)
    if len(errs) > 1:
        assert 'more times since it was last written' in lines[errs[1]]
    # the order lines come from another hook, which still works
    assert sum('| ORDER | ORDER |' in ln for ln in lines) == len(r.fake.orders)
    # the hook's other steps go on: the trace says what failed, the heartbeat comes every minute, bars and trades
    polled = [s for s in r.snaps if s['decision']['action'] != 'SKIPPED']
    assert polled and all(s['decision']['action'] == 'TRACE_ERROR' and s['basket'] is None for s in polled)
    assert 'its step _basket_section failed' in polled[-1]['decision']['headline'] and polled[-1]['account']['units']
    assert sum('| INFO | HEARTBEAT | TRACE_ERROR:' in ln for ln in lines) >= SECONDS // 62
    assert r.bars_t and r.trades and r.trades[-1]['closed']


def test_an_exception_in_the_loop_is_an_error_with_its_traceback(tmp_path):
    """The poll itself raises (a bug in the strategy): the loop logs an ERROR with the traceback and goes on."""
    state = {'n': 0}

    def hook(bot, n):
        real = bot.strategy.calculate_signal

        def flaky(*a, **k):
            state['n'] += 1
            if state['n'] == 30:
                raise ZeroDivisionError('a bug in the strategy')
            return real(*a, **k)
        bot.strategy.calculate_signal = flaky
    r = _replay(tmp_path, seconds=120, hook=hook)
    lines = _read_log(r.out)
    i = next(k for k, ln in enumerate(lines) if '| ERROR | LOOP |' in ln)
    assert "the poll failed: ZeroDivisionError: a bug in the strategy; the loop goes on in 1 s" in lines[i]
    assert lines[i + 1] == '    Traceback (most recent call last):' and 'in flaky' in '\n'.join(lines[i + 1:i + 30])
    t_err = datetime.strptime(lines[i][:23], '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc).timestamp()
    assert any(p['t'] / 1000.0 > t_err + 10 for p in r.run.polls)              # it went on
    assert r.snaps[-1]['health']['errors_1h'] == 1


# ───────────────────────────── start-up lines ─────────────────────────────

def test_the_account_checks_of_the_start_are_in_the_log(mods, tmp_path):
    """The lines of a start come before any trace exists; the first trace writes them, in their order. A terminal
    that holds this bot's account -- the real, hedging account of its credentials: no login, the checks passed, the
    account as its tail. A terminal that holds a demo account under the same number: refused, and the log says what
    MetaTrader 5 reports. Never the full account number, never the password."""
    fake, clock = market(600)
    m = mods(fake=fake, clock=clock)
    bot = F.make_bot(m, fake, SYMBOL, F.Run(), trace_dir=tmp_path / 'bot_output')
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5()                                      # the terminal holds this bot's account
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_DEMO
    assert not bot.initialize_mt5()                                  # the same number, but not a real account
    assert 'login' not in [c[0] for c in fake.calls]                 # never a login over an account
    bot._tracer(SYMBOL)                       # the first trace writes what was logged before it existed
    lines = _read_log(tmp_path / 'bot_output')
    text = '\n'.join(lines)
    ok = [k for k, ln in enumerate(lines) if '| INFO | ACCOUNT | ' in ln and 'checks passed' in ln]
    assert len(ok) == 1 and TAIL in lines[ok[0]] and F.ACCOUNT_SERVER in lines[ok[0]]
    assert f' login_tail={TAIL} ' in lines[ok[0]] + ' ' and ' trade_mode=2 ' in lines[ok[0]] and ' balance=' in lines[ok[0]]
    refused = [k for k, ln in enumerate(lines) if '| ERROR | ACCOUNT | refused, not trading: ' in ln]
    assert len(refused) == 1 and ok[0] < refused[0]
    assert 'is not a real account' in lines[refused[0]] and TAIL in lines[refused[0]]
    assert ' trade_mode=0 ' in lines[refused[0]] + ' '
    assert sum('| INFO | TERMINAL | MT5 initialized' in ln for ln in lines) == 2
    assert '| INFO | TERMINAL | symbols: XAUUSDm -> XAUUSDm' in text
    _no_account_number(text)
    assert not found(text, 'not-a-password')
    # a start that failed is a problem for the journal too, once (with the account as its tail)
    with open(tmp_path / 'bot_output' / 'journal' / f'{SYMBOL}_{DAY[:4]}.jsonl', encoding='utf-8') as f:
        issues = [json.loads(ln) for ln in f]
    assert issues and all((x['kind'], x['state']) == ('issue', 'start') for x in issues)
    boot = [x for x in issues if x['code'] == 'BOOT_ACCOUNT']
    assert len(boot) == 1 and 'is not a real account' in boot[0]['text'] and TAIL in boot[0]['text']
    _no_account_number(json.dumps(issues))


def test_a_job_that_ends_before_the_loop_leaves_its_log(mods, tmp_path):
    """A design every branch refuses (a stop and a ladder without an add gap): the job ends before it connects -- the
    credentials file is never opened -- and its log says why."""
    out = tmp_path / 'bot_output'
    m = mods(VOL_TF='H1', TARGET_USD_PER_UNIT=None, TARGET_VOL=10.0, STOP_VOL=8.0, MAX_ADDS=1,
             LADDER_TRIGGER='macd_turn', OUTPUT_DIR=str(out))
    opened = []
    real_open = open

    def spying_open(path, *a, **k):
        opened.append(os.path.basename(str(path)))
        assert opened[-1] != 'mt5_credentials.json', 'the credentials file may not be opened by the job here'
        return real_open(path, *a, **k)
    m.app.open = spying_open
    bot = m.app.MT5TradingBot(mode='live', target_symbol=SYMBOL)
    assert bot.execute_job() is False
    assert 'mt5_credentials.json' not in opened and m.fake.calls == []
    logs = os.listdir(out / 'logs')
    assert len([n for n in logs if n.endswith('.log')]) == 1
    with open(out / 'logs' / next(n for n in logs if n.endswith('.log')), encoding='utf-8') as f:
        text = f.read()
    refused = [ln for ln in text.splitlines() if '| ERROR | START | ' in ln and 'LADDER_GAP_VOL > 0' in ln]
    assert len(refused) == 1 and 'a design with a stop and a ladder needs' in refused[0]


# ───────────────────────────── bounded files ─────────────────────────────

def _rec(t, level='INFO', msg='hello', kv=None, tb=None):
    return (t, level, 'TEST', msg, kv, None, tb)


def test_a_log_that_cannot_be_written_keeps_its_lines_and_never_raises(mods, tmp_path):
    tl = mods().tracelog
    target = tmp_path / 'logs'
    target.write_text('a file where the log folder should be')
    w = tl.LogWriter(target, SYMBOL)
    assert w.write([_rec(START, msg='first')]) is False and w.failures >= 1
    target.unlink()
    assert w.write([_rec(START + 1, msg='second')]) is True
    lines = (target / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    assert [ln.split(' | ')[3] for ln in lines] == ['first', 'second']
    events = [json.loads(ln) for ln in (target / EVENTS).read_text(encoding='utf-8').splitlines()]
    assert [e['msg'] for e in events] == ['first', 'second']             # the events file kept its lines too


def test_the_line_format(mods):
    tl = mods().tracelog
    line = tl.format_line(START + 0.25, 'ERROR', 'LOOP', 'a | b\nc', {'x': 1.5, 'note': 'two words', 'ok': True,
                                                                     'none': None, 'ids': [1, 2]},
                          tb='Traceback (most recent call last):\n  File "x.py", line 1\nValueError: v\n')
    head, *tb = line.rstrip('\n').split('\n')
    assert head == (f'{DAY} 08:00:00.250 UTC | ERROR | LOOP | a ; b / c | x=1.5 note="two words" ok=true none=null '
                    'ids=[1,2]')
    assert head.split(' | ', 4)[3] == 'a ; b / c'
    assert tb == ['    Traceback (most recent call last):', '      File "x.py", line 1', '    ValueError: v']
    assert tl.dumps({'a': float('nan'), 'b': [1.0, float('inf')]}) == '{"a":null,"b":[1.0,null]}'


# ───────────────────── the paths of v3.9.2-demo.4 (the re-review's fixes) in the trace and the log ─────────────────────

def test_a_terminal_that_holds_another_account_is_in_the_log(mods, tmp_path):
    """TERMINAL_IN_USE: MetaTrader 5 is logged into another account than this bot's, and every start attempt leaves it
    alone. The text log has the problem once as an ERROR (the strategy log's event: when it starts or changes, then at
    most every 15 min) with who holds the terminal -- both accounts as their tails -- and no double prefix; the
    journal has it once as a problem that started."""
    out = tmp_path / 'bot_output'
    fake, clock = market(600)
    m = mods(fake=fake, clock=clock, OUTPUT_DIR=str(out))
    fake.account_login = OTHER_LOGIN                                  # (another real account on the same server)
    bot = m.app.MT5TradingBot(mode='live', target_symbol=SYMBOL)
    bot.credentials, bot.symbols = F.account_credentials(), [SYMBOL]
    for _ in range(3):
        assert bot.initialize_mt5() is False
    assert 'login' not in [c[0] for c in fake.calls]
    lines = _read_log(out)
    err = [ln for ln in lines if '| ERROR | ACCOUNT | TERMINAL_IN_USE: ' in ln]
    assert len(err) == 1 and not any('TERMINAL_IN_USE: TERMINAL_IN_USE' in ln for ln in lines)
    assert f'is logged into another account ({OTHER_TAIL} on {F.ACCOUNT_SERVER})' in err[0]
    assert f"not this bot's {TAIL}" in err[0]
    assert 'No login: MetaTrader 5 and its account are left as they are' in err[0]
    assert f' login_tail={OTHER_TAIL} ' in err[0] and f' own_login_tail={TAIL} ' in err[0] + ' '
    assert ' event=TERMINAL_IN_USE' in err[0]
    assert not any('| ACCOUNT | logged in:' in ln for ln in lines)
    _no_account_number('\n'.join(lines))
    with open(out / 'journal' / f'{SYMBOL}_{DAY[:4]}.jsonl', encoding='utf-8') as f:
        journal = [json.loads(ln) for ln in f]
    use = [x for x in journal if x['kind'] == 'issue' and x['code'] == 'TERMINAL_IN_USE']
    assert [x['state'] for x in use] == ['start'] and OTHER_TAIL in use[0]['text']
    _no_account_number(json.dumps(journal))


@pytest.mark.slow
def test_every_failed_reconnect_attempt_is_in_the_log_and_the_trace(tmp_path):
    """The terminal is gone for 4 minutes. The strategy log has RECONNECT_FAILED once (one reason: the throttle of
    v3.9.2-demo.4); the text log has its ERROR line and a WARN line for every other failed attempt, and the trace's
    health the failed attempts, the next one, the outage so far and why the last one failed; TERMINAL_RECONNECTED says
    how long it took."""
    def hook(bot, n):
        bot.position_helper.mt5.down(START + 60, START + 300)
    r = _replay(tmp_path, seconds=420, hook=hook)
    failed = [e for e in r.run.events if e['event'] == 'RECONNECT_FAILED']
    back = [e['details'] for e in r.run.events if e['event'] == 'TERMINAL_RECONNECTED']
    assert len(failed) == 1 and len(back) == 1 and back[0]['failed_attempts'] >= 5
    lines = _read_log(r.out)
    err = [ln for ln in lines if '| ERROR | TERMINAL | reconnect failed: initialize failed' in ln]
    warn = [ln for ln in lines if '| WARN | TERMINAL | reconnect attempt ' in ln]
    assert len(err) == 1 and 'next attempt in 5 s (the strategy log has this once' in err[0]
    assert len(warn) == back[0]['failed_attempts'] - 1                                   # every other attempt
    assert all('failed (initialize failed' in ln and 'without the terminal so far' in ln for ln in warn)
    up = [ln for ln in lines if '| INFO | TERMINAL | connected to the terminal again' in ln]
    assert len(up) == 1 and f"(attempt {back[0]['attempt']}, after " in up[0] and 'failed attempt(s))' in up[0]
    skipped = [s for s in r.snaps if s['decision']['action'] == 'SKIPPED' and s['health']['reconnect_failed_attempts']]
    assert skipped
    h = skipped[-1]['health']
    assert h['connect_problem'].startswith('initialize failed') and h['next_reconnect_utc'] and h['outage_s'] > 60
    assert h['terminal_in_use'] is False
    assert f"The last of {h['reconnect_failed_attempts']} failed reconnect attempt(s): initialize failed" in \
        skipped[-1]['decision']['headline']
    assert r.snaps[-1]['health']['reconnect_failed_attempts'] == 0 and r.snaps[-1]['health']['outage_s'] is None


@pytest.mark.slow
def test_an_account_switch_just_before_the_positions_read_is_in_the_trace(tmp_path):
    """Another program logs MetaTrader 5 into another account after the poll's first check, just before its positions
    read: the account read again right after the positions refuses that poll. The trace says SKIPPED with the gate
    that refused and why (the other account as its tail); the log has ACCOUNT_REFUSED, then ACCOUNT_OK when this
    bot's account is back; the journal has the problem's start and its end; the bot trades on."""
    def hook(bot, n):
        f = bot.position_helper.mt5

        def to_other(f_):
            f_.account_login = OTHER_LOGIN

        def back(f_):
            f_.account_login = F.ACCOUNT_LOGIN
        f.on_call('positions_get', START + 60, to_other)
        f.at(START + 70, back)
    r = _replay(tmp_path, seconds=240, hook=hook)
    assert [e['event'] for e in r.run.events if e['event'] in ('ACCOUNT_REFUSED', 'ACCOUNT_OK')] == \
        ['ACCOUNT_REFUSED', 'ACCOUNT_OK']
    re_ = [s for s in r.snaps if s['decision']['reason'] == 'account_recheck']
    assert len(re_) == 1
    dec = re_[0]['decision']
    g = {x['key']: x for x in dec['gates']}
    assert dec['action'] == 'SKIPPED' and dec['blocked_by'] == 'account_recheck' and re_[0]['stale']
    assert g['account']['ok'] is True and g['positions']['ok'] is True and g['account_recheck']['ok'] is False
    assert g['account']['name'] == "This bot's account" and TAIL in g['account']['need']
    assert OTHER_TAIL in g['account_recheck']['value'] and TAIL in g['account_recheck']['value']
    assert "the account read again right after the positions is not this bot's (" in dec['headline']
    assert f"until MetaTrader 5 holds this bot's account {TAIL} again." in dec['headline']
    assert re_[0]['health']['account_ok'] is False and re_[0]['health']['login_tail'] == OTHER_TAIL
    assert re_[0]['health']['own_login_tail'] == TAIL
    lines = _read_log(r.out)
    assert any('| ERROR | ACCOUNT | not trading: ' in ln and OTHER_TAIL in ln for ln in lines)
    assert any(f"| INFO | ACCOUNT | MetaTrader 5 holds this bot's account {TAIL} again: trading" in ln for ln in lines)
    assert any('-> SKIPPED: Poll skipped, nothing decided: the account read again right after the positions' in ln
               for ln in lines)
    later = [s for s in r.snaps if s['t'] > START + 75]
    assert later and later[-1]['decision']['action'] != 'SKIPPED' and later[-1]['health']['account_ok']
    _no_account_number('\n'.join(lines) + json.dumps(r.snaps[-1]) + json.dumps(re_[0]))
    with open(os.path.join(r.out, 'journal', f'{SYMBOL}_{DAY[:4]}.jsonl'), encoding='utf-8') as f:
        issues = [json.loads(ln) for ln in f if '"kind":"issue"' in ln]
    refused = [x for x in issues if x['code'] == 'ACCOUNT_REFUSED']
    assert [x['state'] for x in refused] == ['start', 'end']
    assert 5.0 <= refused[1]['lasted_s'] <= 15.0 and OTHER_TAIL in refused[0]['text']


def test_a_basket_a_backstop_closed_only_partly_is_booked_whole_in_the_trace(tmp_path):
    """The broker's backstop closed the entry of a two-leg BUY basket while the bot was down (the add is left): the
    first poll closes the add at once and books the whole basket as closed outside the bot (v3.9.2-demo.4). The trace
    shows the gate and the headline, the log the leg gone, the close of the rest and the booking, and trades.json
    one trade of both legs with the exit reason leg_closed_outside."""
    ids = {}

    def hook(bot, n):
        if n:
            return
        f = bot.position_helper.mt5
        e = f.add_position(0, 0.01, 2000.5, START - 300, magic=MAGIC, comment='its own')
        a = f.add_position(0, 0.01, 1999.5, START - 200, magic=MAGIC, comment='its own')
        f.positions[:] = [p for p in f.positions if p['ticket'] != e]        # its backstop, 100 s before the start
        f.add_deal(e, 1, 1, 0.01, 1995.0, -5.5, START - 100, magic=MAGIC)
        f.deals[-1].reason = f.DEAL_REASON_SL
        ids.update(e=e, a=a)
        basket = {'target_usd_per_unit': 50.0, 'stop_usd_per_unit': 50.0, 'gap_px': 1.0, 'vol_unit_raw': 1.0,
                  'vol_unit': 1.0, 'side': 'BUY', 'units': 1, 'ids': [e, a], 'first_time': START - 300,
                  'opened_at': START - 300, 'opened_by': 'bot', 'ladder_armed': False, 'close_pending': False,
                  'levels_pending': False, 'vol_source': 'bars', 'last_profit': 0.0}
        path = bot._state_path(SYMBOL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'version': 1, 'symbol': SYMBOL, 'magic': MAGIC, 'design': 'scaled_test', 'saved_at': START - 100,
                       'basket': basket, 'last_close': None}, fh)
    r = _replay(tmp_path, seconds=40, hook=hook)
    assert not r.run.errors, r.run.errors[:3]
    e, a = ids['e'], ids['a']
    closes = [o for o in r.fake.orders if 'position' in o]
    assert [o['position'] for o in closes] == [a] and closes[0]['_t_ms'] <= (START + 3) * 1000
    snap = next(s for s in r.snaps if s['decision']['action'] == 'CLOSE_BUY')
    dec = snap['decision']
    g = {x['key']: x for x in dec['gates']}
    assert dec['reason'] == 'leg_closed_outside' and dec['blocked_by'] == 'legs_outside'
    assert g['legs_outside']['ok'] is True and g['legs_outside']['value'] == [e] and 'close_retry' not in g
    assert dec['headline'].startswith(f'Closing the rest of the BUY basket: leg(s) [{e}] were closed outside the bot')
    assert snap['basket']['open']['outside_ids'] == [e]
    lines = _read_log(r.out)
    text = '\n'.join(lines)
    assert (f"| WARN | BASKET | leg(s) [{e}] of the BUY basket closed outside the bot (the broker's backstop, a "
            'stop-out or by hand): the other 1 leg(s) are closed at once and the whole basket is booked as closed '
            'outside the bot') in text
    assert f'| CLOSE | CLOSE | the rest of the BUY basket closed after leg(s) [{e}] were closed outside the bot: 1 ' \
           'position(s)' in text
    realised = round(sum(d.profit for d in r.fake.deals if d.position_id in (e, a)), 2)
    book = [ln for ln in lines if '| CLOSE | CLOSE | the BUY basket is booked as closed outside the bot' in ln]
    assert len(book) == 1 and f'leg(s) [{e}] were closed outside it' in book[0] and 'the bot closed the other 1' in book[0]
    assert ('realised ' + ('-' if realised < 0 else '+') + f'${abs(realised):,.2f} on every leg (deal history)') in book[0]
    assert '| INFO | PAUSE | entry pause started:' in text
    assert not any('| WARN | TRACE |' in ln for ln in lines)                            # the gates read as the bot did
    doc = r.trades[-1]
    t = next(x for x in doc['closed'] if {l['position_id'] for l in x['legs']} == {e, a})
    assert t['exit_reason'] == 'leg_closed_outside' and t['pnl'] == realised
    assert t['exit_reason_text'] == 'a leg closed outside the bot, the rest closed by the bot'


# ───────────────────────────── the final review's fixes ─────────────────────────────

# A made-up credentials file (nothing of a real one): the block the bot reads is "live". Its numbers and passwords
# must reach no log.
FAKE_CREDS = {'live': {'terminal_path': 'C:\\MT5\\own\\terminal64.exe', 'login_id': 4444111122,
                       'login_pass': 'FAKE-live-pässword-4444', 'server': 'Fake-Real'},
              'demo': {'login_id': 9999333344, 'login_pass': 'FAKE-old-pässword-9999', 'server': 'Fake-Old'}}


def _all_logged(folder):
    out = ''
    for root, _, names in os.walk(folder):
        for n in names:
            with open(os.path.join(root, n), 'rb') as f:
                out += f.read().decode('utf-8', 'replace')
    return out


@pytest.mark.parametrize('encoding', ['cp1252', 'utf-16'])
def test_a_credentials_file_that_is_not_utf8_leaves_no_byte_of_it_in_the_logs(mods, tmp_path, encoding):
    """Notepad's ANSI (cp1252) or PowerShell's UTF-16: the bot says the file is not UTF-8 text and logs none of its bytes
    (the repr of a decode error holds the whole file, passwords included); the day file is named as symbols.json
    spells the symbol (the job was started with --symbol in capitals)."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    code = tmp_path / 'code'
    code.mkdir()
    (code / 'mt5_credentials.json').write_bytes(json.dumps(FAKE_CREDS, ensure_ascii=False, indent=1).encode(encoding))
    (code / 'symbols.json').write_text(json.dumps({'symbols': [{'symbol': SYMBOL, 'is_active': True}]}), encoding='utf-8')
    m.app.__file__ = str(code / 'app.py')                    # (the bot reads its files next to app.py)
    bot = m.app.MT5TradingBot(mode='live', target_symbol=SYMBOL.upper())
    bot.trace_dir = str(out)
    assert bot.load_credentials() is False and not bot.credentials
    bot._boot_flush()
    logs = os.listdir(out / 'logs')
    assert any(n.startswith(f'{SYMBOL}_') and n.endswith('.log') for n in logs), logs        # 'XAUUSDm_', not 'XAUUSDM_'
    text = _all_logged(out)
    assert '| ERROR | START | ' in text and 'not UTF-8' in text
    for secret in ('FAKE', 'p\\xe4ss', 'pässword', '4444111122', '9999333344', '4444', 'F\\x00A', 'Fake-Old'):
        assert not found(text, secret), secret


def test_a_job_that_fails_logs_the_error_type_and_message_never_its_repr(mods, tmp_path):
    """An exception that reaches execute_job: its type and str() in the log (the repr of a decode error is every byte it
    decoded)."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    bot = m.app.MT5TradingBot(mode='live', target_symbol=SYMBOL)
    bot.trace_dir = str(out)
    secret = b'{"live": {"login_pass": "FAKE-secret-\xe4"}}'
    at = secret.index(b'\xe4')

    def boom():
        raise UnicodeDecodeError('utf-8', secret, at, at + 1, 'invalid continuation byte')
    bot._init_cycle = boom
    assert bot.execute_job() is False
    text = _all_logged(out)
    assert ("the job failed: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe4 in position "
            f'{at}: invalid continuation byte') in text
    assert not found(text, 'FAKE-secret')
    assert m.app._err_text(ValueError('x')) == 'ValueError: x' and m.tracelog.err_text('plain text') == 'plain text'


def test_a_refused_replace_is_tried_again_for_a_quarter_of_a_second(mods, tmp_path, monkeypatch):
    """Windows refuses os.replace onto a file a reader (the dashboard) has open: the trace's JSON writer -- the trace,
    the bars, the trades, the journal's state -- tries again (about 0.24 s in all) before it gives up, and leaves no
    temp file behind."""
    tl = mods().tracelog
    calls = []
    real = os.replace

    def refusing(n):
        def rep(a, b):
            calls.append(time.perf_counter())
            if len(calls) <= n:
                raise PermissionError(13, 'Access is denied')
            return real(a, b)
        return rep
    monkeypatch.setattr(tl.os, 'replace', refusing(4))
    tl.write_json_atomic(str(tmp_path / 'a.json'), {'x': 1})
    assert len(calls) == 5 and json.loads((tmp_path / 'a.json').read_text(encoding='utf-8')) == {'x': 1}
    calls.clear()
    monkeypatch.setattr(tl.os, 'replace', refusing(99))
    with pytest.raises(PermissionError):
        tl.write_json_atomic(str(tmp_path / 'b.json'), {'x': 2})
    assert len(calls) == len(tl.REPLACE_WAITS_S) + 1 and 0.2 <= calls[-1] - calls[0] <= 1.0
    assert not [n for n in os.listdir(tmp_path) if n.endswith('.tmp')]


def test_the_accounts_figures_after_a_restart_in_a_trade_are_real_ones(mods, tmp_path):
    """A restart in the middle of a trade: the bot keeps the unit the trade opened with and the record of how it was
    sized. The trace's account block is the real account's -- its balance, this bot's open P/L, the whole account's,
    what both bots booked today -- and this bot's closed P/L comes from the deal history (null until its first read,
    never a made-up balance). The next unit counts with the bot's share of the balance."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    tr = bot._tracer(SYMBOL)
    tl = m.tracelog
    sizing = m.app.sizing_record(3000.0, 1500.0, 1250.0, 2, 0.01, 10, 'entry', START)
    c = tl._Ctx({'account_info': {'balance': 3003.0, 'equity': 3004.5, 'profit': 4.0, 'margin': 2.0, 'margin_free': 3002.5,
                                  'margin_level': 150225.0},
                 'mtqty': 0.01, 'units': 2, 'buy_positions': {'total_profit': 1.5}, 'sell_positions': None,
                 'step_up_balance': 1250.0, 'max_limit': 10, '_sizing': sizing,
                 '_safety': {'day': {'start_balance': 2990.0}}})
    snap = {'account': tr._account(c)}
    tr._handed_over(c, snap)
    acct = snap['account']
    assert not [k for k in acct if 'virtual' in k] and 'own_equity' not in acct
    assert (acct['balance'], acct['equity'], acct['floating_account'], acct['floating_own']) == (3003.0, 3004.5, 4.0, 1.5)
    assert acct['own_closed_pl'] is None and acct['day_realised'] == 13.0
    assert (acct['units'], acct['lot'], acct['share']) == (2, 0.02, 0.5)
    # two units from $2,500 of account balance (0.5 x 2,500 = one step), the third from $5,000
    assert acct['next_unit_at'] == 5000.0 == sizing['next_unit_at_account_balance']
    assert acct['unit_rule'] == 'unit = floor(0.5 x account balance / 1250) + 1, at most 10, re-derived only while flat'
    assert snap['sizing'] == sizing and snap['sizing'] is not sizing
    tr._own_closed = -3.75                                   # the deal history was read: this bot's closed trades
    assert tr._account(c)['own_closed_pl'] == -3.75
    # at the cap there is no next unit; without a balance of the day no figure for today
    c2 = tl._Ctx(dict(c.d, units=10, _safety=None))
    snap2 = {'account': tr._account(c2)}
    tr._handed_over(c2, snap2)
    assert snap2['account']['next_unit_at'] is None and snap2['account']['day_realised'] is None
    assert snap2['safety'] is None


# ───────────────────── the paths of v3.9.2-demo.5 (the third fix round) in the trace and the log ─────────────────────

class _Wall:
    """app.time for the launcher's restarts: the wall clock, as the strategy log's times are (its entries carry
    datetime.now(); the limit across restarts compares them with time.time()), and a sleep() that only moves it on."""

    def __init__(self):
        self.offset = 0.0

    def time(self):
        return time.time() + self.offset

    def perf_counter(self):
        return time.perf_counter() + self.offset

    def sleep(self, seconds):
        self.offset += float(seconds)


def _start(m, wall, attempt=None):
    """One start of the job by the launcher (a new process) on the fake terminal, then the launcher's 30 s.
    attempt(k) runs at the start of the job's start attempt k (1 to 3). The bot gets the credentials of the fake's
    default account (F.CREDS), whatever account the terminal holds."""
    bot = m.app.MT5TradingBot(mode='live', target_symbol=SYMBOL)
    bot.load_credentials = lambda: setattr(bot, 'credentials', F.account_credentials()) or True
    k = [0]

    def load_symbols():                       # (never the real files)
        k[0] += 1
        if attempt is not None:
            attempt(k[0])
        bot.symbols = [SYMBOL]
        return True
    bot.load_symbols = load_symbols
    ok = bot.execute_job()
    wall.sleep(30)
    return ok


def _day_logs(folder):
    """Every line of the text log's day files, in order (on the wall clock: any day)."""
    logs = os.path.join(str(folder), 'logs')
    out = []
    for n in sorted(x for x in os.listdir(logs) if re.match(re.escape(SYMBOL) + r'_\d{4}-\d\d-\d\d\.log$', x)):
        with open(os.path.join(logs, n), encoding='utf-8') as f:
            out += f.read().splitlines()
    return out


def _journal_of(folder):
    """Every line of the permanent journal in a bot folder, in order."""
    jdir = os.path.join(str(folder), 'journal')
    out = []
    for n in sorted(os.listdir(jdir)) if os.path.isdir(jdir) else []:
        with open(os.path.join(jdir, n), encoding='utf-8') as f:
            out += [json.loads(ln) for ln in f]
    return out


def test_a_start_refused_on_another_account_is_in_the_log_once_per_the_limit(mods, tmp_path, monkeypatch):
    """A problem that lasts across the launcher's restarts: MetaTrader 5 holds another account (TERMINAL_IN_USE), the
    job is refused and the terminal left alone. The text log has the refusal as one ERROR line that names the problem
    once and says what to do, the three start attempts and the job's end with the problem in it -- once per the
    strategy log's limit: the launcher's restarts every 30 s in the next 15 minutes add no line, the first one after
    them writes the block again. The journal has the problem once when it starts and once more after 15 minutes
    ('still'), not once per restart."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    wall = _Wall()
    monkeypatch.setattr(m.app, 'time', wall)
    m.fake.account_login = OTHER_LOGIN
    assert _start(m, wall) is False
    lines = _day_logs(out)
    text = '\n'.join(lines)
    err = [ln for ln in lines if '| ERROR | ACCOUNT | TERMINAL_IN_USE: ' in ln]
    assert len(err) == 1 and not found(text, 'TERMINAL_IN_USE: TERMINAL_IN_USE')
    assert f'is logged into another account ({OTHER_TAIL} on' in err[0] and f"not this bot's {TAIL}" in err[0]
    assert 'The bot never switches the account itself' in err[0]                     # what to do, and what it will not
    assert 'No login: MetaTrader 5 and its account are left as they are' in err[0]
    assert sum('| WARN | START | start attempt ' in ln and 'TERMINAL_IN_USE' in ln for ln in lines) == 3
    assert sum('| ERROR | START | ' in ln and 'TERMINAL_IN_USE: ' in ln for ln in lines) == 1      # the job's end
    n = len(lines)
    for _ in range(10):                      # the launcher's restarts within the 15 minutes: nothing more is written
        assert _start(m, wall) is False
    assert len(_day_logs(out)) == n
    use = [x for x in _journal_of(out) if x['kind'] == 'issue' and x['code'] == 'TERMINAL_IN_USE']
    assert [x['state'] for x in use] == ['start']
    wall.sleep(900)
    assert _start(m, wall) is False          # the first start after them: the whole block again
    lines = _day_logs(out)
    assert len(lines) == 2 * n and sum('| ERROR | ACCOUNT | TERMINAL_IN_USE: ' in ln for ln in lines) == 2
    with open(out / 'logs' / f'{SYMBOL}_strategy_log.json', encoding='utf-8') as f:
        assert [e['event'] for e in json.load(f)] == ['TERMINAL_IN_USE'] * 2
    use = [x for x in _journal_of(out) if x['kind'] == 'issue' and x['code'] == 'TERMINAL_IN_USE']
    assert [x['state'] for x in use] == ['start', 'still'] and use[1]['lasted_s'] >= 900
    assert 'login' not in [c[0] for c in m.fake.calls] and not found('\n'.join(lines), 'not-a-password')
    _no_account_number('\n'.join(lines) + json.dumps(_journal_of(out)))


def test_the_wait_for_the_terminals_account_and_an_unknown_account_are_in_the_log(mods, tmp_path):
    """The login rule in the log: a terminal still logging into its saved account (read again every second, then this
    bot's own account: no login), and an IPC error (the account is not known: no login, detached). The account is
    written as its tail; the password never."""
    out = tmp_path / 'bot_output'
    fake, clock = market(900)
    m = mods(fake=fake, clock=clock, OUTPUT_DIR=str(out))
    grace = m.app._ACCOUNT_GRACE_S
    bot = F.make_bot(m, fake, SYMBOL, F.Run(), trace_dir=out)
    bot.mt5_initialized, bot.position_helper = False, None
    fake.login_delay_s = 4.0                                     # (it logs into its saved account 4 s after starting)
    assert bot.initialize_mt5()
    fake.login_delay_s = 0.0
    fake.account_answers = ['ipc_timeout']
    assert not bot.initialize_mt5()
    bot._tracer(SYMBOL)                       # the first trace writes what was logged before it existed
    lines = _read_log(out)
    text = '\n'.join(lines)
    wait = [ln for ln in lines if '| INFO | ACCOUNT | the terminal shows no account yet (account_info() answered None' in ln]
    assert len(wait) == 1 and f'for up to {grace:g} s before any login' in wait[0]
    held = [ln for ln in lines if '| INFO | ACCOUNT | no login: ' in ln and TAIL in ln]
    assert len(held) == 1 and F.ACCOUNT_SERVER in held[0]
    assert ('| WARN | ACCOUNT | no login: account not known: account_info() answered None (last_error' in text
            and 'the bot detached and tries again later' in text)
    assert 'login' not in [c[0] for c in fake.calls]
    assert not found(text, 'not-a-password')
    _no_account_number(text)


def test_an_entry_and_an_add_are_legs_from_their_fill_in_the_log(traced):
    """_record_fill: the entry's and the add's position id comes from the order's answer. The BASKET line of the fill
    says so (recorded=<id>), and the next poll, which lists it, has a DEBUG line."""
    lines = _read_log(traced.out)
    opened = [ln for ln in lines if '| INFO | BASKET | ' in ln and ' basket opened: ' in ln]
    added = [ln for ln in lines if '| INFO | BASKET | added ' in ln]
    assert opened and added
    for ln in opened + added:
        pid = re.search(r' recorded=(\d+)', ln)
        assert pid and f"position {pid.group(1)} is a leg of the basket from its fill (its id from the order's answer; " \
                       'the terminal lists it within 10 s)' in ln, ln
        listed = [x for x in lines if f'| DEBUG | BASKET | position(s) [{pid.group(1)}] of the ' in x
                  and 'basket listed by the terminal' in x]
        assert listed, ln


def _close_poll(tr, tl, state, cr, ov, now, reason='stop_loss'):
    """The trace's view of one poll that closed a BUY basket (its log lines and headline), without a replay."""
    c = tl._Ctx({'state': state, 'close_response': cr, 'analysis_data': {}, 'has_candle_data': True,
                 'candle_is_fresh': True})
    snap = {'basket': {'open': ov, 'pause': {'active': False}, 'trend': {}, 'vol': {}, 'force_close_enabled': False},
            'account': {}}
    dec = {'action': 'CLOSE_BUY', 'reason': reason, 'side': 'BUY', 'gates': []}
    tr._transitions(c, snap, dec, [], now, 2)
    head = tr._headline(dec, c, snap, 2, now)
    tr._flush()
    return head


def test_a_basket_close_that_closed_nothing_or_waits_for_an_unlisted_add_is_said_so(mods, tmp_path):
    """A close that closed nothing (close_by_type found none of this bot's positions) books nothing and is decided again
    next poll; a close that closed every listed leg while an add recorded from its order is not listed yet keeps the
    basket (app.py _after_close): the log and the headline say so, not 'basket closed'."""
    m = mods(OUTPUT_DIR=str(tmp_path / 'bot_output'))
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=tmp_path)
    tr = bot._tracer(SYMBOL)
    now = m.clock.time()
    ov = {'side': 'BUY', 'legs': [{'id': 100001}], 'pnl': -5.0, 'stop_usd': 5.0, 'judged_on': 'bid'}
    b = {'side': 'BUY', 'ids': [100001], 'units': 1, 'opened_by': 'bot', 'first_time': now - 60, 'close_pending': False}
    head = _close_poll(tr, m.tracelog, {'basket': dict(b), 'last_close': None},
                       {'closed_count': 0, 'failed_count': 0, 'message': 'No positions to close'}, ov, now)
    assert 'The close closed nothing' in head and 'decided again next poll' in head
    b2 = dict(b, ids=[100001, 100002], close_pending=True, unlisted=[{'id': 100002, 'time': now - 2}])
    head2 = _close_poll(tr, m.tracelog, {'basket': b2, 'last_close': None},
                        {'closed_count': 1, 'failed_count': 0, 'closed_tickets': [100001]}, ov, now + 1)
    assert 'The close is incomplete: leg(s) [100002] filled less than 10 s ago are not listed by the terminal yet' in head2
    lines = _read_log(tmp_path)
    nothing = [ln for ln in lines if '| WARN | CLOSE | the close of the BUY basket closed nothing' in ln]
    assert len(nothing) == 1 and 'nothing is booked, and the close is decided again next poll' in nothing[0]
    waits = [ln for ln in lines if '| WARN | CLOSE | the close of the BUY basket is incomplete: 1 closed; leg(s) [100002]' in ln]
    assert len(waits) == 1 and 'the basket stays open, nothing is booked yet, and the rest is closed next poll' in waits[0]
    assert not any('| CLOSE | CLOSE | BUY basket closed' in ln for ln in lines)
    assert not any('is incomplete: 0 closed, 0 failed' in ln for ln in lines)
    assert tr._pending_reason == 'stop_loss'                 # (the retry's close keeps the reason of the first one)


def _gone_entry_polls(m, tmp_path, guarded=False, fail=None):
    """The trace's transitions on the polls of round 3's fix E case, without a replay: an entry recorded from its order
    (never listed), then gone -- app.py books it as closed outside the bot, realised -$5.50 from the deal history --,
    five polls of the pause after the loss, then five with a SELL basket. guarded: through the poll hook's guarded step
    (_transitions_step), else the bare step; fail(tr) may break the trace first. Returns, for each poll, whether its
    transitions step failed, and the text log."""
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=tmp_path)
    tr = bot._tracer(SYMBOL)
    tl = m.tracelog
    if fail is not None:
        fail(tr)
    now = m.clock.time()
    pause = {'active': True, 'length_s': 240, 'left_s': 240, 'why': 'after a losing basket', 'until': now + 280,
             'until_utc': None}
    snap = {'basket': {'open': {}, 'pause': pause, 'trend': {}, 'vol': {}, 'force_close_enabled': False}, 'account': {}}

    def poll(state, t):
        c = tl._Ctx({'state': state, 'close_response': None, 'analysis_data': {}, 'has_candle_data': True,
                     'candle_is_fresh': True})
        dec = {'action': 'HOLD', 'reason': None, 'side': None, 'gates': []}
        if guarded:
            r = tr._transitions_step(tr._transitions, tr._keep_basket, c, snap, dec, [], t, 2)
        else:
            r = tr._step('poll', '_transitions', tr._transitions, c, snap, dec, [], t, 2)
        tr._flush()
        return r is tl._FAILED
    entry = {'side': 'BUY', 'ids': [100001], 'units': 1, 'opened_by': 'bot', 'opened_at': now, 'first_time': None,
             'unlisted': [{'id': 100001, 'time': now}], 'close_pending': False}
    failed = [poll({'basket': entry, 'last_close': None}, now)]
    lc = {'time': now + 40, 'pnl': -5.5, 'lost': True, 'resolved': True, 'source': 'history', 'reason': 'closed_outside',
          'side': 'BUY', 'ids': [100001], 'open_time': now, 'attempts': 1, 'time_from_history': True}
    failed += [poll({'basket': None, 'last_close': dict(lc)}, now + 41 + k) for k in range(5)]
    sell = {'side': 'SELL', 'ids': [100002], 'units': 1, 'opened_by': 'bot', 'opened_at': now + 300,
            'first_time': now + 300, 'close_pending': False}
    failed += [poll({'basket': dict(sell), 'last_close': dict(lc)}, now + 301 + k) for k in range(5)]
    return failed, _day_logs(tmp_path)


def test_an_entry_gone_before_the_terminal_listed_it_is_one_close_line(mods, tmp_path):
    """Round 3's fix E case: an entry whose id came from its order and that its backstop closed while the bot or the
    terminal was down, before any positions read listed it. app.py books it as closed outside the bot. The log has one
    CLOSE line that says so with the realised P/L, then the pause after the loss, and the polls after it are quiet.
    (Before: that line raised UnboundLocalError on this poll and on every poll after it until the bot's next close --
    an ERROR line, errors_1h counting each poll, no CLOSE and no PAUSE line, and a SELL basket after it 'replaced the
    BUY one' on every poll.)"""
    m = mods(OUTPUT_DIR=str(tmp_path / 'bot_output'))
    failed, lines = _gone_entry_polls(m, tmp_path)
    assert failed == [False] * 11
    assert not [ln for ln in lines if '| ERROR | TRACE |' in ln]
    gone = [ln for ln in lines if '| CLOSE | CLOSE | ' in ln]
    assert len(gone) == 1, gone
    assert ('| CLOSE | CLOSE | the BUY entry [100001] is gone before the terminal listed it (its broker backstop while '
            'the bot or the terminal was down?): booked as closed outside the bot, with the pause after a loss if it '
            'lost: realised -$5.50, its closing deal at ') in gone[0]
    assert sum('| INFO | PAUSE | entry pause started: 4.0 min after a losing basket (loss -$5.50)' in ln
               for ln in lines) == 1
    assert not [ln for ln in lines if 'replaced the BUY one' in ln]


def test_a_transitions_line_that_fails_is_not_tried_again_every_poll(mods, tmp_path):
    """A bug in one line of the trace's transitions (here the booking of the exits raises): an ERROR line with its
    traceback on that poll. The poll hook's step then keeps that poll's basket and last close for the next poll, so
    the line is not tried again and nothing fails again. (Before: the same error on every poll until the bot's next
    close -- hours in the pause after a loss.)"""
    def broken(tr):
        def raising(*a, **k):
            raise ValueError('boom: a bug in a transitions line')
        tr._record_exits = raising
    m = mods(OUTPUT_DIR=str(tmp_path / 'bot_output'))
    failed, lines = _gone_entry_polls(m, tmp_path, guarded=True, fail=broken)
    assert failed == [False, True] + [False] * 9
    errs = [ln for ln in lines if '| ERROR | TRACE |' in ln]
    assert len(errs) == 1 and 'failed in its step _transitions: ValueError: boom: a bug in a transitions line' in errs[0]
    assert not [ln for ln in lines if 'replaced the BUY one' in ln]

def test_a_held_back_start_is_written_when_an_attempt_fails_another_way(mods, tmp_path, monkeypatch):
    """The 15-minute limit holds back the text log of a start only when all its 3 attempts were refused on a problem it
    held back. TERMINAL_IN_USE: the first start writes its block, the launcher's restarts after it add no line. A start
    whose second attempt fails another way is written whole: MetaTrader 5 cannot be attached to; it shows no account
    at all (the bot may then log in itself, and the server refuses it); or mt5.initialize() raises. (Before: nothing
    of these starts was written -- the check read only the problem of the last attempt, or of an attempt before the
    one that raised.)"""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    wall = _Wall()
    monkeypatch.setattr(m.app, 'time', wall)
    fake = m.fake
    fake.account_login = OTHER_LOGIN                     # the terminal holds another account
    assert _start(m, wall) is False
    lines = _day_logs(out)
    assert sum('| ERROR | ACCOUNT | TERMINAL_IN_USE: ' in ln for ln in lines) == 1
    n = len(lines)
    for _ in range(3):
        assert _start(m, wall) is False                  # held back: no line
    assert len(_day_logs(out)) == n
    attempts = ['start attempt 1/3 failed (', 'start attempt 2/3 failed (', 'start attempt 3/3 failed (']
    real_init, real_login = fake.initialize, fake.login

    def not_there(k):                                    # attempt 2: MetaTrader 5 cannot be attached to
        fake.initialize = (lambda *a, **kw: False) if k == 2 else real_init
    assert _start(m, wall, not_there) is False
    fake.initialize = real_init
    lines = _day_logs(out)[n:]
    assert sum('| ERROR | TERMINAL | MT5 initialize failed' in ln for ln in lines) == 1
    assert [ln.split(' | ')[-1][:26] for ln in lines if '| WARN | START | start attempt ' in ln] == attempts
    assert sum('| ERROR | START | ' in ln and 'TERMINAL_IN_USE: ' in ln for ln in lines) == 1      # the job's end
    n += len(lines)

    def no_account(k):
        if k == 2:                                       # no account at all for the whole wait; a login is refused
            fake.logged_in, fake.account_login = False, 0
            fake.login = lambda **kw: (fake.calls.append(('login', kw.get('login'))), False)[1]
        else:
            fake.logged_in, fake.account_login, fake.login = True, OTHER_LOGIN, real_login
    assert _start(m, wall, no_account) is False
    fake.logged_in, fake.account_login, fake.login = True, OTHER_LOGIN, real_login
    lines = _day_logs(out)[n:]
    assert [ln.split(' | ')[-1][:26] for ln in lines if '| WARN | START | start attempt ' in ln] == attempts
    second = next(ln for ln in lines if '| WARN | START | start attempt 2/3 failed (' in ln)
    assert 'TERMINAL_IN_USE' not in second               # it failed another way, and the log says how
    assert any(('| WARN | ACCOUNT | ' in ln or '| ERROR | ACCOUNT | ' in ln) and 'TERMINAL_IN_USE' not in ln
               for ln in lines)
    assert [c[0] for c in fake.calls].count('login') <= 1
    n += len(lines)

    def raises(k):
        fake.initialize = real_init
        if k == 2:
            def boom(*a, **kw):
                raise RuntimeError('the terminal raised')
            fake.initialize = boom
    assert _start(m, wall, raises) is False
    fake.initialize = real_init
    lines = _day_logs(out)[n:]
    assert sum('| ERROR | START | the job failed: RuntimeError: the terminal raised' in ln for ln in lines) == 1
    assert sum('| WARN | START | start attempt 1/3 failed (TERMINAL_IN_USE: ' in ln for ln in lines) == 1
    text = '\n'.join(_day_logs(out))
    assert not found(text, 'not-a-password')
    _no_account_number(text)
