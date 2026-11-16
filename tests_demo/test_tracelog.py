"""
The bot side of the dashboard's data contract (tracelog.py, docs/dashboard-data.md).

A fake-terminal replay of the scaled design (entries, a one-unit add, stops, a target, the loss pause) with the real
writers: <SYMBOL>_trace.json, _bars.json, _trades.json, logs/<SYMBOL>_<day>.log and _events.jsonl appear with the right
content, next to the files of the old dashboard; the trace changes no decision (the same polls, requests and fills
with it switched off); a disk that fails does not stop the trading; a hook that raises is an ERROR with its traceback
in the log; a heartbeat line every minute; the log files stay bounded.
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

SYMBOL = 'XAUUSDm'
SECONDS, SEED = 1200, 4          # 20 minutes: a 2-leg basket stopped out, the 4-min loss pause, a target
DESIGN = dict(SCALED)            # XAU Top 1 shape on fast timeframes (conftest): M1 votes, M5 trend, M1 volatility unit
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
LINE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) UTC \| (DEBUG|INFO|ORDER|FILL|CLOSE|WARN|ERROR) \| '
                  r'([A-Z_]+) \| (.+)$')
CREDS = {'terminal_path': r'C:\fake\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}


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
    r = types.SimpleNamespace(fake=fake, out=out, snaps=[], bars_t=[], trades=[], costs=[], bots=[])
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
    return r


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
    assert traced.run.polls == untraced.run.polls
    assert traced.fake.orders == untraced.fake.orders
    assert deals_of(traced.fake) == deals_of(untraced.fake)
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
        assert s['branch'] == DEFAULTS['DEMO_BRANCH'] and s['design'] == DESIGN['DESIGN_NAME'] and not s['stale']
        assert s['t'] * 1000 >= p['t'] and s['time_utc'].endswith('Z')
        h = s['health']
        assert h['connected'] and h['account_ok'] and h['market_live'] and h['errors_1h'] == 0
        assert (h['trade_mode_name'], h['margin_mode_name'], h['login']) == ('demo', 'hedging', 1)
        assert h['loop_ms'] is not None and h['last_tick_age_s'] is not None and h['reconnects'] == 0
        a = s['account']
        assert a['units'] == p['units'] and a['lot'] == round(p['units'] * 0.01, 2)
        if p['virtual_balance'] is not None:
            assert a['virtual_balance'] == round(p['virtual_balance'], 2)
            assert a['own_closed_pl'] == round(p['virtual_balance'] - 2000.0, 2)
        assert a['own_open_pl'] == (p['profit'] if p['nb'] + p['ns'] else 0.0)
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
        bot.credentials = dict(CREDS)
        bot.position_helper.mt5.down(START + 60, START + 90)
    r = _replay(tmp_path, seconds=240, hook=hook)
    skipped = [s for s in r.snaps if s['decision']['action'] == 'SKIPPED']
    assert len(r.snaps) > len(r.run.polls) and skipped
    assert any(s['basket'] is not None for s in skipped)                         # the last good poll's numbers
    for s in skipped:
        assert s['stale'] and not s['health']['connected'] and 'terminal_info()' in s['health']['terminal_problem']
        assert s['decision']['gates'][0]['key'] == 'terminal' and s['decision']['gates'][0]['ok'] is False
    assert r.snaps[-1]['health']['reconnects'] == 1 and r.snaps[-1]['health']['connected']
    text = '\n'.join(_read_log(r.out))
    for needle in ('-> SKIPPED: Poll skipped, nothing decided: terminal_info() returned None', '| WARN | TERMINAL |',
                   '| ERROR | TERMINAL | reconnect failed', '| ERROR | TERMINAL | MT5 initialize failed',
                   '| INFO | ACCOUNT | logged in: account 1 on Fake-Demo', '| INFO | TERMINAL | connected to the terminal again',
                   '| INFO | TERMINAL | the terminal answers again'):
        assert needle in text, needle


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
    assert (doc['schema'], doc['magic'], doc['virtual'], doc['virtual_start_balance']) == (1, MAGIC, True, 2000.0)
    assert len(closed) == len(b)
    for x, y in zip(closed, b):
        assert x['side'] == ('BUY' if y['side'] == 0 else 'SELL') and len(x['legs']) == len(y['legs'])
        assert x['pnl'] == y['pnl'] and x['status'] == 'closed'
        assert x['open_t'] == pytest.approx(y['t_open']) and x['close_t'] == pytest.approx(y['t_close'])
        lots = sum(leg['vol'] for leg in y['legs'])
        assert x['lots'] == round(lots, 2)
        assert x['open_price'] == pytest.approx(sum(leg['price_in'] * leg['vol'] for leg in y['legs']) / lots, abs=6e-4)
        assert [leg['position_id'] for leg in x['legs']] == [leg['pid'] for leg in y['legs']]
    reasons = [e['details']['reason'] for e in traced.run.events if e['event'] in ('CLOSE_BUY', 'CLOSE_SELL')]
    assert [x['bot_reason'] for x in closed] == reasons
    assert [x['exit_reason'] for x in closed] == [{'stop_loss': 'stop', 'target': 'target'}[r] for r in reasons]
    curve = doc['balance_curve']
    run = 2000.0
    assert curve[0]['v'] == 2000.0 and len(curve) == len(closed) + 1
    for pt, x in zip(curve[1:], closed):
        run = round(run + x['pnl'], 2)
        assert pt['v'] == run == x['balance_after'] and pt['t'] == x['close_t']
    assert doc['summary']['balance_now'] == run and doc['summary']['closed'] == len(closed)
    assert doc['summary']['wins'] + doc['summary']['losses'] == len(closed)
    flat = [s for s in traced.snaps if s['basket']['open'] is None]
    assert flat[-1]['account']['virtual_balance'] == run
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
    own record wins; overlapping legs of one side are one basket; the balance curve adds every deal."""
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
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 1000, now, 3, True)
    got = [(x['id'], len(x['legs']), x['exit_reason'], x['pnl']) for x in doc['closed']]
    assert got == [(1, 1, 'backstop', -10.0), (2, 1, 'closed_outside', 5.0), (3, 2, 'target', 30.0)]
    assert [p['v'] for p in doc['balance_curve']] == [2000.0, 1990.0, 1995.0, 2025.0]
    assert doc['summary']['exit_reasons'] == {'backstop': 1, 'closed_outside': 1, 'target': 1}
    with open(tmp_path / 'state' / f'{SYMBOL}_exit_reasons.json', encoding='utf-8') as f:
        assert json.load(f)['reasons']['3']['reason'] == 'target'


def test_a_basket_the_backstop_closed_while_the_bot_was_down(tmp_path):
    """The bot starts with a state file holding a BUY basket whose position the broker's stop closed meanwhile: the
    first poll books it as closed outside the bot; the log says so (CLOSE, then the pause from the deal history) and
    trades.json gives the exit reason 'backstop'."""
    fake, clock = market(30)
    pid = fake.add_position(0, 0.01, 1999.0, START - 600, magic=MAGIC, comment='demo')
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
    assert f"branch={DEFAULTS['DEMO_BRANCH']}" in text and f"design={DESIGN['DESIGN_NAME']}" in text
    names = {n for n in vars(traced.run.mods.constants) if n.isupper() and not n.startswith('_')}
    config = {m.group(4).split(' = ')[0] for m in ms if m.group(3) == 'CONFIG' and ' = ' in m.group(4)}
    assert names <= config, names - config
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
    # the events file: the same lines, as JSON
    with open(os.path.join(traced.out, 'logs', f'{SYMBOL}_events.jsonl'), encoding='utf-8') as f:
        events = [json.loads(ln) for ln in f]
    assert len(events) == len(ms)
    for e, m in zip(events, ms):
        assert (e['level'], e['cat']) == (m.group(2), m.group(3)) and m.group(4).startswith(e['msg'])
        assert e['time'] == m.group(1) + ' UTC'
    assert all(isinstance(e['data']['gates'], list) for e in events if e['cat'] == 'DECISION')


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
    trace writes: the bot trades exactly as before; the text log (here in a folder that works) says what failed."""
    blocker = tmp_path / 'blocker'
    blocker.write_text('a file where the output folder should be')
    trace_dir = tmp_path / 'trace'

    def hook(bot, n):
        bot.trace_dir = str(trace_dir)
        sys.modules['tracelog'].write_json_atomic = _no_space
    r = _replay(tmp_path, out=blocker / 'out', hook=hook)
    assert r.run.polls == untraced.run.polls and deals_of(r.fake) == deals_of(untraced.fake)
    assert r.fake.orders == untraced.fake.orders
    assert r.run.errors and all('could not write' in e for e in r.run.errors)    # the console says so (once a minute)
    assert len(r.run.errors) <= 3 * (SECONDS // 60 + 1)
    assert not os.path.exists(trace_dir / f'{SYMBOL}_trace.json')
    lines = _read_log(trace_dir)
    warn = [m.group(4) for m, _ in _parsed(lines) if m and m.group(2) == 'WARN' and m.group(3) == 'WRITE']
    for what in (f'{SYMBOL}.json', 'account.json', 'the strategy log'):          # the old dashboard's files
        assert any(w.startswith(f'could not write {what}:') for w in warn), what
    for what in ('the trace', 'the bars', 'the trades', 'the exit reasons'):      # the trace's own JSON
        assert any(w.startswith(f'could not write {what}:') and 'No space left' in w for w in warn), what
    assert '| WARN | SAVE | the daily-trade / history-summary files could not be saved' in '\n'.join(lines)
    assert len(warn) <= 7 * (SECONDS // 300 + 1)                                  # once per 5 min and file


@pytest.mark.slow
def test_a_hook_that_raises_is_an_error_with_its_traceback(tmp_path, untraced):
    """A bug in the trace (here every poll hook raises): an ERROR with the full traceback, the repeats counted and
    written again at most every 10 minutes; the trading goes on exactly as before."""
    def hook(bot, n):
        def boom(self, *a, **k):
            raise ValueError('boom: a bug in the trace')
        sys.modules['tracelog'].TraceLog._basket_section = boom
    r = _replay(tmp_path, hook=hook)
    assert not r.run.errors and deals_of(r.fake) == deals_of(untraced.fake) and r.run.polls == untraced.run.polls
    lines = _read_log(r.out)
    errs = [i for i, (m, _) in enumerate(_parsed(lines)) if m and m.group(2) == 'ERROR']
    assert 1 <= len(errs) <= SECONDS // 600 + 1
    first = lines[errs[0]]
    assert "| ERROR | TRACE | the trace hook poll() failed: ValueError('boom: a bug in the trace')" in first
    tb = []
    for ln in lines[errs[0] + 1:]:
        if not ln.startswith('    '):
            break
        tb.append(ln[4:])
    assert tb[0] == 'Traceback (most recent call last):' and tb[-1] == 'ValueError: boom: a bug in the trace'
    assert any('in boom' in ln for ln in tb) and any('in _poll' in ln for ln in tb)
    if len(errs) > 1:
        assert 'more times since it was last written' in lines[errs[1]]
    # the order lines come from another hook, which still works
    assert sum('| ORDER | ORDER |' in ln for ln in lines) == len(r.fake.orders)


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
    assert "the poll failed: ZeroDivisionError('a bug in the strategy'); the loop goes on in 1 s" in lines[i]
    assert lines[i + 1] == '    Traceback (most recent call last):' and 'in flaky' in '\n'.join(lines[i + 1:i + 30])
    t_err = datetime.strptime(lines[i][:23], '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc).timestamp()
    assert any(p['t'] / 1000.0 > t_err + 10 for p in r.run.polls)              # it went on
    assert r.snaps[-1]['health']['errors_1h'] == 1


# ───────────────────────────── start-up lines ─────────────────────────────

def test_the_account_checks_of_the_start_are_in_the_log(mods, tmp_path):
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    bot = F.make_bot(m, fake, SYMBOL, F.Run(), trace_dir=tmp_path)
    bot.credentials = dict(CREDS)
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5()
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_REAL
    assert not bot.initialize_mt5()
    bot._tracer(SYMBOL)                       # the first trace writes what was logged before it existed
    text = '\n'.join(_read_log(tmp_path))
    assert ('| INFO | ACCOUNT | logged in: account 1 on Fake-Demo; checks passed (a demo account, a hedging account, '
            'the login of the credentials) | login=1 server=Fake-Demo trade_mode=0 margin_mode=2') in text
    assert '| ERROR | ACCOUNT | refused, not trading: account 1 is not a demo account (trade_mode 2, demo is 0)' in text
    assert '| INFO | TERMINAL | MT5 initialized' in text and '| INFO | TERMINAL | symbols: XAUUSDm -> XAUUSDm' in text


def test_a_job_that_ends_before_the_loop_leaves_its_log(mods, tmp_path):
    """(a design this branch refuses -- the job ends before it connects, so the credentials file is never read)"""
    m = mods(STRATEGY='turtle', TURTLE_SYSTEM=3, OUTPUT_DIR=str(tmp_path))
    m.app.open = lambda *a, **k: (_ for _ in ()).throw(AssertionError('no file may be opened by the job here'))
    bot = m.app.MT5TradingBot(mode='demo', target_symbol=SYMBOL)
    assert bot.execute_job() is False
    logs = os.listdir(tmp_path / 'logs')
    assert len([n for n in logs if n.endswith('.log')]) == 1
    with open(tmp_path / 'logs' / next(n for n in logs if n.endswith('.log')), encoding='utf-8') as f:
        text = f.read()
    assert "| ERROR | START | the design in constants.py is refused: TURTLE_SYSTEM must be 1 or 2, not 3" in text


# ───────────────────────────── bounded files ─────────────────────────────

def _rec(t, level='INFO', msg='hello', kv=None, tb=None):
    return (t, level, 'TEST', msg, kv, None, tb)


def test_day_files_and_their_retention(mods, tmp_path):
    tl = mods().tracelog
    w = tl.LogWriter(tmp_path, SYMBOL)

    def day(days_back):
        return f'{datetime.fromtimestamp(START - days_back * 86400, tz=timezone.utc):%Y-%m-%d}'

    def days_left():
        return sorted(n[len(SYMBOL) + 1:-4] for n in os.listdir(tmp_path) if n.startswith(SYMBOL + '_2'))
    for d in (1, 5, 29, 30, 31, 60):
        (tmp_path / f'{SYMBOL}_{day(d)}.log').write_text('x\n')
    (tmp_path / f'OTHER_{day(60)}.log').write_text('x\n')
    midnight = (int(START) // 86400 + 1) * 86400
    assert w.write([_rec(START), _rec(midnight - 0.001)])
    assert days_left() == sorted(day(d) for d in (0, 1, 5, 29))       # 30 days kept, the 30th day back is gone
    assert w.write([_rec(midnight + 0.5)])                             # a new UTC day: a new file, retention again
    assert days_left() == sorted([day(0), day(1), day(5), day(-1)])
    assert f'OTHER_{day(60)}.log' in os.listdir(tmp_path)              # another symbol's files are not touched
    today = (tmp_path / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    assert today[-1].startswith(f'{DAY} 23:59:59.999 UTC | INFO | TEST | hello')
    assert (tmp_path / f'{SYMBOL}_{day(-1)}.log').read_text(encoding='utf-8').startswith(f'{day(-1)} 00:00:00.500 UTC')


def test_the_events_file_is_rotated_and_the_day_file_capped(mods, tmp_path):
    tl = mods().tracelog
    w = tl.LogWriter(tmp_path, SYMBOL, events_cap=4000, events_keep=3, day_cap=6000)
    for i in range(400):
        w.write([_rec(START + i, level='ERROR' if i % 50 == 0 else 'INFO', msg=f'line {i}', kv={'i': i})])
    names = sorted(os.listdir(tmp_path))
    assert [n for n in names if 'events' in n] == [f'{SYMBOL}_events.{k}.jsonl' for k in (1, 2, 3)] + [f'{SYMBOL}_events.jsonl']
    for n in names:
        if 'events' in n:
            assert os.path.getsize(tmp_path / n) <= 4000 + 200
    last = [json.loads(ln) for ln in (tmp_path / f'{SYMBOL}_events.jsonl').read_text().splitlines()]
    assert last[-1]['msg'] == 'line 399' and last[-1]['kv'] == {'i': 399}
    text = (tmp_path / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    note = [k for k, ln in enumerate(text) if '| WARN | LOG | this text log passed' in ln]
    assert len(note) == 1
    assert all('| ERROR |' in ln or '| WARN |' in ln for ln in text[note[0] + 1:])      # past the cap: errors only
    assert sum('| ERROR |' in ln for ln in text[note[0] + 1:]) >= 5


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
