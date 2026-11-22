"""
The permanent journal of a real-money bot (tracelog.py; spec section 8): journal/<SYMBOL>_<YYYY>.jsonl, never deleted,
one JSON line per
  start   the whole configuration the loop started with;
  order   every order request and its result, with the quote it went out at and the slippage against it;
  trade   every closed trade, once -- also across restarts -- with what the bot knew of it;
  safety, skip   what app.py hands over: the safety's events, an order it held back;
  day     the day that ended, at the first poll of a new UTC day;
  issue   a problem, when it starts, changes and ends, and at most every 15 minutes in between;
and the per-minute samples of logs/<SYMBOL>_<day>_samples.jsonl.
The journal is bounded: a line that repeats is written 3 times, then once a minute with the count; 5 MB a UTC day.
journal() only queues: no line is written while the bot holds mt5_lock.
"""
import builtins
import json
import os
import types
from datetime import datetime, timezone

import pytest

from conftest import DEFAULTS, F, MAGIC, SCALED, START, baskets, market, run_bot
from conftest import differs, found

SYMBOL = 'XAUUSDm'
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
YEAR = DAY[:4]
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
DONE, REFUSED = 10009, 10018


# ───────────────────────────── helpers (test_trace_live.py uses them too) ─────────────────────────────

def journal_of(folder, kind=None):
    """Every line of the permanent journal of a bot folder, in the file's order (of one kind, if given)."""
    jdir = os.path.join(str(folder), 'journal')
    out = []
    for n in sorted(os.listdir(jdir)) if os.path.isdir(jdir) else []:
        with open(os.path.join(jdir, n), encoding='utf-8') as f:
            out += [json.loads(ln) for ln in f]
    return [x for x in out if kind is None or x['kind'] == kind]


def tracer(mods, tmp_path, fake=None, clock=None, **overrides):
    """(modules, bot, its trace) on the small fake terminal, the bot's folder in tmp_path / 'bot_output'."""
    m = mods(fake=fake, clock=clock, **overrides)
    out = tmp_path / 'bot_output'
    assert m.app.OUTPUT_DIR == str(out)                                # (conftest: every bot of a test writes there)
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    bot.state_dir = None
    return m, bot, bot._tracer(SYMBOL)


def again(m, tmp_path):
    """A new process on the same folder: a new bot and a new trace (the launcher started the bot again)."""
    bot = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=tmp_path / 'bot_output')
    bot.state_dir = None
    return bot, bot._tracer(SYMBOL)


def later(m, seconds):
    m.clock.now_ms += int(round(seconds * 1000))
    return m.clock.time()


def ctx_of(m, **over):
    """The locals of one basket poll that read the terminal: flat, a live market, nothing wanted. `over` changes or
    adds names (the hand-overs of the real-money layer: _sizing, _safety, _open_hold, _foreign)."""
    now = m.clock.time()
    tick = types.SimpleNamespace(bid=2000.0, ask=2000.12, time_msc=int((now - 0.4) * 1000), time=int(now))
    ctx = {
        'state': {'basket': None, 'last_close': None}, 'basket': None,
        'account_info': {'balance': 1500.0, 'equity': 1500.0, 'margin': 0.0, 'margin_free': 1500.0,
                         'margin_level': 0.0, 'profit': 0.0},
        'mtqty': 0.01, 'units': 1, 'buy_positions': None, 'sell_positions': None, 'step_up_balance': 1250.0,
        'max_limit': 10, '_tick': tick,
        'market_status': {'status': 'OPEN', 'is_open': True, 'minutes_since_last': 0.0, 'lookback_minutes': 3,
                          'message': ''},
        'server_time': datetime.fromtimestamp(now, tz=timezone.utc), 'in_window': True, 'brake': 0, 'brake_manual': 0,
        'trading_window_cfg': {'enabled': False},
        'analysis_data': {'open_score': 0.0, 'fc_score': 0.0, 'entry_allowed': True}, '_usd_per_price': 1.0,
        'has_candle_data': True, 'candle_is_fresh': True, '_no_data': [], '_short': [], '_fill_pending': False,
        '_frames': {}, '_signals': {}, '_buy_ct': 0, '_sell_ct': 0, 'buy_signal': 'DO_NOTHING',
        'sell_signal': 'DO_NOTHING', 'trend_now': 0, 'vol_now': None, 'iteration_ms': 12.0,
        'sym_cfg': {'step_up_balance': 1250.0, 'unit_max_limit': 10},
    }
    ctx.update(over)
    return ctx


def safety_view(**over):
    """A view as safety.Tracker gives it (the poll local _safety), watching and not blocked."""
    view = {'enabled': True, 'blocked': False, 'hold': False, 'pending': False, 'account_blocked': False,
            'bot_blocked': False, 'blocked_scope': None, 'reasons': [f'Watching account {TAIL}. New trades are allowed.'],
            'since': None, 'period': 'start', 'at': START, 'started_at': START - 3600, 'error': None, 'state': 'on',
            'drop': {'pct': 2.5, 'limit': 20.0, 'peak': 1538.46, 'peak_at': START - 1800, 'balance': 1500.0},
            'day': {'pct': 1.0, 'limit': 12.5, 'day0': 1515.15, 'day0_at': START - 28800, 'day': DAY,
                    'since': 'midnight', 'start_balance': 1515.15, 'start_at': START - 28800, 'cash': 0.0},
            'streak': {'count': 2, 'limit': 5, 'waiting': 0}, 'partner': None,
            'limits': {'drop_pct': 20.0, 'day_pct': 12.5, 'streak_n': 5}, 'account_dir': 'x', 'login_tail': TAIL}
    view.update(over)
    return view


def request(typ, volume=0.01, price=2000.12, position=None, sl=0.0, tp=0.0):
    r = {'action': 1, 'symbol': SYMBOL, 'volume': volume, 'type': typ, 'price': price, 'magic': MAGIC,
         'comment': 'x', 'type_time': 0, 'type_filling': 1}
    if position is None:
        r.update(sl=sl, tp=tp)
    else:
        r.update(position=position, deviation=20)
    return r


def answer(retcode=DONE, price=2000.12, volume=0.01, order=7, deal=8, comment='done'):
    return types.SimpleNamespace(retcode=retcode, price=price, volume=volume, order=order, deal=deal, comment=comment)


def deal(pid, entry, typ, price, profit, t, reason=3, volume=0.01, commission=0.0, swap=0.0, fee=0.0):
    return types.SimpleNamespace(ticket=int(t * 10) % 10 ** 9 + pid + entry, order=0, time=int(t), time_msc=int(t * 1000),
                                 type=typ, entry=entry, magic=MAGIC, position_id=pid, reason=reason, volume=volume,
                                 price=price, commission=commission, swap=swap, profit=profit, fee=fee, symbol=SYMBOL,
                                 comment='')


def _replay(tmp, seconds, restarts=(), hook=None, seed=4, **overrides):
    """A replay of the scaled design with the real writers in tmp / 'bot_output'; every trace is flushed at its end
    (a real job's last lines do that)."""
    out = tmp / 'bot_output'
    fake, clock = market(seconds, seed=seed, restarts=restarts)
    bots = []

    def on_new_bot(bot, n):
        bots.append(bot)
        if hook is not None:
            hook(bot, n)
    run = run_bot(fake, clock, overrides={**SCALED, 'OUTPUT_DIR': str(out), **overrides}, symbol=SYMBOL,
                  state_dir=out / 'state', keep_writers=True, on_new_bot=on_new_bot)
    for bot in bots:
        for tr in list(bot._tracers.values()):
            tr._flush()
    return types.SimpleNamespace(run=run, fake=fake, out=out, bots=bots)


# ───────────────────────────── start ─────────────────────────────

@pytest.mark.slow
def test_the_start_line_holds_the_configuration_the_loop_started_with(tmp_path):
    """Version, branch, design, every constant the CONFIG lines hold (with the value in effect), symbols.json, the
    share, the safety limits, the account (its tail, server, currency, leverage, balance), the terminal's build,
    Python. Never the old accounts' fingerprints, never the account number. One line per start of the loop."""
    r = _replay(tmp_path, 40, restarts=[20.2])
    lines = journal_of(r.out)
    starts = [x for x in lines if x['kind'] == 'start']
    assert len(starts) == 2 and lines[0]['kind'] == 'start'                # the first line of the journal
    s = starts[0]
    assert (s['version'], s['branch'], s['partner_branch']) == (
        DEFAULTS['VERSION'], DEFAULTS['BRANCH'], DEFAULTS['PARTNER_BRANCH'])
    assert (s['design'], s['strategy'], s['symbol'], s['magic'], s['mode']) == (
        SCALED['DESIGN_NAME'], 'basket', SYMBOL, MAGIC, 'live')
    assert s['design_summary'].startswith("design 'scaled_test'") and s['python'].count('.') == 2 and s['schema'] == 1
    c = s['constants']
    names = {n for n in vars(r.run.mods.constants) if n.isupper() and not n.startswith('_')}
    assert set(c) == names - {'OLD_LOGINS_SHA256'}
    assert (c['TARGET_VOL'], c['STOP_VOL'], c['OUTPUT_DIR'], c['MAGIC']) == (2.0, 2.0, str(r.out), MAGIC)   # in effect
    assert c['LOG_KEEP_DAYS'] == DEFAULTS['LOG_KEEP_DAYS'] and c['ACCOUNT_SHARE'] == s['share'] == DEFAULTS['ACCOUNT_SHARE']
    assert s['symbols_json']['symbols'][0]['symbol'] == SYMBOL and s['symbols_json']['mtqty'] == 0.01
    assert s['safety_limits'] == {'default_on': DEFAULTS['SAFETY_DEFAULT_ON'], 'drop_pct': DEFAULTS['SAFETY_DROP_PCT'],
                                  'day_pct': DEFAULTS['SAFETY_DAY_PCT'], 'streak_n': DEFAULTS['SAFETY_STREAK_N']}
    assert s['account'] == {'login_tail': TAIL, 'server': F.ACCOUNT_SERVER, 'currency': 'USD',
                            'leverage': r.fake.leverage, 'balance': 2000.0, 'equity': 2000.0}
    assert s['terminal'] == {'build': r.fake.build, 'ping_ms': round(r.fake.ping_last / 1000.0, 1)}
    assert s['t'] == pytest.approx(START + 0.5, abs=0.01) and s['first_poll_t'] >= s['t']
    assert starts[1]['t'] == pytest.approx(START + 20.2, abs=1.2) and starts[1]['pid'] == s['pid']
    text = json.dumps(starts)
    assert not found(text, str(F.ACCOUNT_LOGIN)) and not found(text, 'OLD_LOGINS')
    assert not any(v in text for v in DEFAULTS['OLD_LOGINS_SHA256'])


def test_a_constant_with_a_secret_in_its_name_is_never_logged_nor_journalled(mods, tmp_path):
    """OLD_LOGINS_SHA256, and any constant whose name holds PIN, PASS or SECRET: in no CONFIG line and not in the
    start line."""
    m, bot, tr = tracer(mods, tmp_path)
    m.constants.DASH_PIN_HINT = '4711-pin'
    m.constants.BROKER_PASSWORD = 'hunter2-pass'
    m.constants.MY_SECRET_KEY = 'shh-secret'
    m.constants.PLAIN_NOTE = 'a-plain-note'
    for name in ('OLD_LOGINS_SHA256', 'DASH_PIN_HINT', 'BROKER_PASSWORD', 'MY_SECRET_KEY', 'x_pin', 'PinCode'):
        assert m.tracelog.hidden_constant(name), name
    for name in ('MAGIC', 'OUTPUT_DIR', 'SAFETY_DROP_PCT', 'BRANCH', 'PLAIN_NOTE'):
        assert not m.tracelog.hidden_constant(name), name
    tr.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    tr.poll(ctx_of(m))
    start = journal_of(tmp_path / 'bot_output', 'start')[0]
    assert start['constants']['PLAIN_NOTE'] == 'a-plain-note'
    written = ''
    for root, _, names in os.walk(tmp_path):
        for n in names:
            with open(os.path.join(root, n), encoding='utf-8', errors='replace') as f:
                written += f.read()
    assert 'a-plain-note' in written
    for secret in ('4711-pin', 'hunter2-pass', 'shh-secret', 'DASH_PIN_HINT', 'BROKER_PASSWORD', 'MY_SECRET_KEY',
                   'OLD_LOGINS_SHA256') + tuple(DEFAULTS['OLD_LOGINS_SHA256']):
        assert not found(written, secret), secret


# ───────────────────────────── order ─────────────────────────────

def test_the_order_line_and_the_sign_of_its_slippage(mods, tmp_path):
    """The reference is the ask for a BUY order and the bid for a SELL order -- an open, an add and a close alike --
    and above 0 means filled worse than quoted. (An opening request always carries the ASK as its price, also for a
    sell: the slippage is never taken against the request.) slippage_usd = slippage x lots x contract size."""
    m, bot, tr = tracer(mods, tmp_path)
    bot._usd_per_price[SYMBOL] = 1.0                                   # gold: contract size 100 x 0.01 lot
    quote = {'bid': 2000.00, 'ask': 2000.12, 't_msc': int(START * 1000) + 250}
    cases = [  # (request, fill, action, side, order side, slippage)
        (request(0), 2000.15, 'open', 'BUY', 'BUY', 0.03),             # a buy filled 0.03 above the ask: worse
        (request(0), 2000.10, 'open', 'BUY', 'BUY', -0.02),            # ... below it: better
        (request(1), 1999.97, 'open', 'SELL', 'SELL', 0.03),           # a sell filled 0.03 below the bid: worse
        (request(1), 2000.04, 'open', 'SELL', 'SELL', -0.04),
        (request(1, position=501, price=2000.00), 1999.95, 'close', 'BUY', 'SELL', 0.05),   # closing a BUY: a SELL order
        (request(0, position=502, price=2000.12), 2000.18, 'close', 'SELL', 'BUY', 0.06),   # closing a SELL: a BUY order
        (request(0, position=503, price=2000.12), 2000.07, 'close', 'SELL', 'BUY', -0.05),
    ]
    for k, (req, fill, *_) in enumerate(cases):
        tr.order(req, answer(price=fill, order=100 + k, deal=200 + k), False, 3.25, dict(quote))
    tr._state_ref = {'basket': {'side': 'BUY'}}                       # in a BUY basket a buy is an add
    tr.order(request(0), answer(price=2000.14, order=150), False, 1.0, dict(quote))
    tr._flush()
    lines = journal_of(tmp_path / 'bot_output', 'order')
    assert len(lines) == len(cases) + 1
    for x, (req, fill, action, side, order_side, slip) in zip(lines, cases):
        assert (x['action'], x['side'], x['order_side']) == (action, side, order_side)
        assert (x['bid'], x['ask'], x['spread']) == (2000.0, 2000.12, pytest.approx(0.12))
        assert x['quote_t'] == pytest.approx(START + 0.25) and x['price'] == req['price'] and x['volume'] == 0.01
        assert (x['retcode'], x['retcode_text'], x['done'], x['refused'], x['ms']) == (DONE, 'done', True, False, 3.25)
        assert x['fill_price'] == fill and x['slippage'] == pytest.approx(slip, abs=1e-9)
        assert x['slippage_usd'] == pytest.approx(slip * 0.01 * 100.0, abs=1e-6)
        assert x['position'] == req.get('position') and x['magic'] == MAGIC and x['comment'] == 'done'
        assert x['kind'] == 'order' and x['utc'].endswith('Z')
    assert (lines[-1]['action'], lines[-1]['slippage']) == ('add', pytest.approx(0.02))
    # the same figures on the text log's ORDER line and in the trace's orders of the poll
    log = (tmp_path / 'bot_output' / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8').splitlines()
    first = next(ln for ln in log if '| ORDER | ORDER | open BUY 0.01 lot' in ln)
    assert ' bid=2000 ask=2000.12 spread=0.12 slippage=0.03 slippage_usd=0.03' in first
    assert tr._orders[0]['slippage'] == pytest.approx(0.03) and tr._orders[0]['fill_price'] == 2000.15


def test_an_order_without_a_fill_has_no_fill_price_and_no_slippage(mods, tmp_path):
    """A refusal by the broker, a request a guard stopped, no answer at all, an answer without a price: fill_price,
    slippage and slippage_usd are null, never 0. Without a quote the fill price is there and the slippage is not.
    'safety' names the guard that stopped it."""
    m, bot, tr = tracer(mods, tmp_path)
    bot._usd_per_price[SYMBOL] = 1.0
    quote = {'bid': 2000.0, 'ask': 2000.12, 't_msc': 1}
    tr.order(request(0), answer(REFUSED, price=0.0, volume=0.0, order=0, deal=0, comment='market closed'), False, 2.0, quote)
    tr.order(request(0), None, True, None, quote)                     # the account guard
    tr.order(request(1), None, 'safety', None, quote)                 # the safety guard of buy() / sell()
    tr.order(request(1, position=9), None, False, 5.0, quote)         # order_send answered nothing
    tr.order(request(0), answer(price=0.0), False, 1.0, quote)        # done, but the answer has no price
    tr.order(request(0), answer(price=2000.2), False, 1.0)            # no quote handed over
    tr.order(request(0), answer(price=2000.2), False, 1.0, 'not a quote')
    tr._flush()
    a, b, c, d, e, f, g = journal_of(tmp_path / 'bot_output', 'order')
    for x in (a, b, c, d, e):
        assert (x['fill_price'], x['slippage'], x['slippage_usd'], x['fill_volume']) == (None, None, None, None) \
            or (x is e and x['fill_volume'] == 0.01 and x['fill_price'] is None and x['slippage'] is None)
    assert (a['retcode'], a['retcode_text'], a['comment'], a['refused'], a['done']) == (
        REFUSED, 'market closed', 'market closed', False, False)
    assert (b['refused'], b['retcode'], b['retcode_text']) == (True, None, 'refused by the account guard')
    assert (c['refused'], c['retcode'], c['retcode_text']) == ('safety', None, 'refused by the safety guard')
    assert (d['refused'], d['retcode'], d['retcode_text']) == (False, None, 'no answer') and d['last_error'] is not None
    for x in (f, g):
        assert (x['fill_price'], x['bid'], x['ask'], x['spread'], x['slippage'], x['slippage_usd']) == (
            2000.2, None, None, None, None, None)
    log = (tmp_path / 'bot_output' / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8')
    assert '-> not sent: the account guard refused it' in log and '-> not sent: the safety guard refused it' in log
    assert 'open SELL 0.01 lot was not filled: not sent: the safety guard refused it' in log


def test_the_order_observer_reads_no_terminal_and_no_file(mods, tmp_path, monkeypatch):
    """order() runs inside mt5_lock, between order_send and the bot's handling of its answer: it makes its lines in
    memory. The contract size for slippage_usd comes from what the bot already knows."""
    m, bot, tr = tracer(mods, tmp_path)
    calls = []
    for name in ('symbol_info', 'symbol_info_tick', 'account_info', 'positions_get', 'history_deals_get',
                 'terminal_info', 'copy_rates_from_pos'):
        real = getattr(m.fake, name)
        monkeypatch.setattr(m.fake, name, lambda *a, _n=name, _r=real, **k: (calls.append(_n), _r(*a, **k))[1])
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(m.tracelog, 'open', lambda p, *a, **k: (opened.append(str(p)), real_open(p, *a, **k))[1],
                        raising=False)
    quote = {'bid': 2000.0, 'ask': 2000.12, 't_msc': 1}
    with bot.mt5_lock:
        tr.order(request(0), answer(price=2000.15), False, 1.0, quote)
        tr.order(request(0), answer(REFUSED, price=0.0), False, 1.0, quote)
        tr.journal('skip', why='safety', side='BUY', kind='entry', price=2000.12)
    assert calls == [] and opened == []
    assert tr._orders[0]['slippage_usd'] is not None                   # CONTRACT_SIZE_FALLBACK: XAU 100
    assert tr._orders[0]['slippage_usd'] == pytest.approx(0.03 * 0.01 * 100.0)
    tr._facts = {'contract_size': 1.0}                                 # the Turtle's symbol facts come first
    with bot.mt5_lock:
        tr.order(request(0), answer(price=2000.15), False, 1.0, quote)
    assert tr._orders[-1]['slippage_usd'] == pytest.approx(0.03 * 0.01 * 1.0) and calls == []


@pytest.mark.slow
def test_every_order_of_a_replay_is_in_the_journal(tmp_path):
    """Entries, an add, the closes of a two-leg basket: one order line per request, in their order, with the fill of
    the terminal's deal. When the helper hands the quote over, the slippage is the fill against it (the fake fills at
    the quote: 0)."""
    r = _replay(tmp_path, 420)
    lines = journal_of(r.out, 'order')
    assert len(lines) == len(r.fake.orders) >= 4
    deals = {d.order: d for d in r.fake.deals}
    seen = set()
    for x, o in zip(lines, r.fake.orders):
        assert x['t'] * 1000 == pytest.approx(o['_t_ms'], abs=1) and x['volume'] == o['volume'] and x['done']
        assert x['position'] == o.get('position') and x['order_side'] == ('BUY' if o['type'] == 0 else 'SELL')
        assert x['action'] == ('close' if 'position' in o else x['action']) and x['action'] in ('open', 'add', 'close')
        assert x['fill_price'] == deals[x['deal']].price and x['retcode'] == DONE and x['refused'] is False
        if x['bid'] is not None:                                        # the quote of the request, handed over
            assert x['spread'] == pytest.approx(x['ask'] - x['bid']) and x['slippage'] == pytest.approx(0.0, abs=1e-9)
            assert x['slippage_usd'] == pytest.approx(0.0, abs=1e-9)
        else:
            assert x['slippage'] is None and x['slippage_usd'] is None
        seen.add(x['action'])
    assert seen == {'open', 'add', 'close'}


# ───────────────────────────── repeats, the budget ─────────────────────────────

def test_a_line_that_repeats_is_written_three_times_then_once_a_minute_with_the_count(mods, tmp_path):
    """A close the terminal refuses is sent again on every poll, rightly, and each try is an order line: the same
    (kind, action, position, retcode) is written the first 3 times in a row, then once a minute with the count of
    those left out. Three legs are three lines that repeat, each on its own. Nothing is lost: what was left out is
    counted in a line that is written. A fill is never a repeat."""
    m, bot, tr = tracer(mods, tmp_path)
    refused = answer(REFUSED, price=0.0, volume=0.0, order=0, deal=0, comment='trade disabled')
    for i in range(600):                                               # ten minutes of polls, three legs each
        later(m, 1.0)
        for pos in (501, 502, 503):
            tr.order(request(1, position=pos, price=2000.0), refused, False, 1.0)
        tr.poll_skipped('positions', 'x')
    later(m, 90.0)
    tr.poll_skipped('positions', 'x')                                  # the run is over: its last held line goes out
    lines = journal_of(tmp_path / 'bot_output', 'order')
    for pos in (501, 502, 503):
        mine = [x for x in lines if x['position'] == pos]
        assert [x.get('repeats') for x in mine[:3]] == [None, None, None]                 # the first three
        assert 12 <= len(mine) <= 14                                                       # then one a minute
        assert all(57 <= x['repeats'] <= 60 for x in mine[3:-1])
        assert len(mine) + sum(x.get('repeats') or 0 for x in mine) == 600                 # every try is counted
        gaps = [b['t'] - a['t'] for a, b in zip(mine[3:], mine[4:-1])]
        assert all(59.5 <= g <= 61.5 for g in gaps)
    # another answer for the same leg starts a new line: it is written at once
    tr.order(request(1, position=501, price=2000.0), answer(10016, price=0.0, comment='invalid stops'), False, 1.0)
    # ... and so is every fill, however many come in a row
    for k in range(10):
        tr.order(request(0), answer(price=2000.12, order=900 + k), False, 1.0)
    tr._flush()
    lines = journal_of(tmp_path / 'bot_output', 'order')
    assert lines[-11]['retcode'] == 10016 and 'repeats' not in lines[-11]
    assert [x['order'] for x in lines[-10:]] == list(range(900, 910)) and all('repeats' not in x for x in lines[-10:])
    # the text log is not thinned: it has its own caps (test_retention.py)
    log = (tmp_path / 'bot_output' / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8')
    assert log.count('| ORDER | ORDER | close position 501 ') == 601


def test_in_a_row_ends_when_the_line_has_not_come_for_ten_minutes(mods, tmp_path):
    m, bot, tr = tracer(mods, tmp_path)
    refused = answer(REFUSED, price=0.0, comment='market closed')
    for _ in range(5):
        later(m, 1.0)
        tr.order(request(0), refused, False, 1.0)                      # 5 in a row: 3 written, 2 held
    later(m, 700.0)
    for _ in range(5):
        later(m, 1.0)
        tr.order(request(0), refused, False, 1.0)                      # a new row: 3 written again
    later(m, 61.0)
    tr.poll_skipped('positions', 'x')
    lines = journal_of(tmp_path / 'bot_output', 'order')
    assert len(lines) + sum(x.get('repeats') or 0 for x in lines) == 10
    assert [x.get('repeats') for x in lines] == [None, None, None, 1, None, None, None, 1]


def test_the_journals_budget_of_a_day(mods, tmp_path):
    """5 MB a UTC day (here 4,000 bytes): past it lines are left out and counted, with one 'journal_suppressed' line an
    hour. The start and issue lines may fill half of it, so a restart loop cannot push out the orders; a closed trade
    and a day's line go on to twice the budget. A restart keeps counting (the file says how much the day has); a new
    UTC day has a new budget. The file is never deleted."""
    tl = mods().tracelog

    class Clock:
        t = START

        def __call__(self):
            return self.t
    clock = Clock()
    jdir = tmp_path / 'journal'

    def writer():
        return tl.LogWriter(tmp_path / 'logs', SYMBOL, journal_dir=jdir, journal_budget=4000, clock=clock)

    def line(kind, k, t=None):
        t = clock.t if t is None else t
        return (t, kind, tl.dumps({'t': round(t, 3), 'utc': tl._iso(t), 'kind': kind, 'k': k, 'pad': 'x' * 100}))
    w = writer()
    size = len(line('order', 0)[2]) + 1
    for k in range(40):                                                 # 'start' lines: half the budget
        clock.t += 1
        assert w.write([], journal=[line('start', k)])
    path = jdir / f'{SYMBOL}_{YEAR}.jsonl'
    got = [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]
    starts = [x for x in got if x['kind'] == 'start']
    assert len(starts) == 2000 // size and (len(starts) + 1) * size > 2000
    notes = [x for x in got if x['kind'] == 'journal_suppressed']
    assert len(notes) == 1 and notes[0]['lines'] == 1 and notes[0]['budget_bytes'] == 4000 and notes[0]['day'] == DAY
    for k in range(40):                                                 # orders: the whole budget
        clock.t += 1
        assert w.write([], journal=[line('order', k)])
    got = [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]
    orders = [x for x in got if x['kind'] == 'order']
    assert (len(starts) + len(orders)) == 4000 // size
    assert len([x for x in got if x['kind'] == 'journal_suppressed']) == 1    # one an hour, not one per line
    w = writer()                                                        # a restart: the day's count is the file's
    clock.t += 1
    assert w.write([], journal=[line('order', 'after the restart'), line('trade', 'still written'), line('day', 'too')])
    got = [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]
    assert [x['k'] for x in got if x['kind'] in ('trade', 'day')] == ['still written', 'too']
    assert 'after the restart' not in [x.get('k') for x in got]
    clock.t += 3600                                                     # an hour later: the count of what was left out
    assert w.write([], journal=[line('safety', 'left out')])
    notes = [x for x in [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]
             if x['kind'] == 'journal_suppressed']
    assert len(notes) == 3 and notes[-1]['lines'] == 1 and w.journal_left_out == 2
    for k in range(60):                                                 # trades: to twice the budget, then no more
        assert w.write([], journal=[line('trade', k)])
    got = [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]
    kept = sum(len(json.dumps(x, separators=(',', ':'))) + 1 for x in got if x['kind'] != 'journal_suppressed')
    assert 8000 - size < kept <= 8000
    midnight = (int(START) // 86400 + 1) * 86400
    clock.t = midnight + 60                                             # the next UTC day: a new budget
    assert w.write([], journal=[line('order', 'a new day')])
    got = [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]
    assert got[-1]['k'] == 'a new day'
    # the year in the line's own time names the file; the retention of the logs never touches the journal
    assert w.write([rec for rec in []], journal=[line('order', 'last year', t=START - 400 * 86400)])
    assert (jdir / f'{SYMBOL}_{int(YEAR) - 1}.jsonl').exists()
    w.retention(DAY)
    w.size_guard(DAY)
    assert sorted(os.listdir(jdir)) == [f'{SYMBOL}_{int(YEAR) - 1}.jsonl', f'{SYMBOL}_{YEAR}.jsonl']


def test_journal_lines_a_failed_write_could_not_store_are_written_with_the_next_batch(mods, tmp_path):
    """The journal's own backlog (2000 lines): a folder that cannot be written for a while loses no line."""
    tl = mods().tracelog
    jdir = tmp_path / 'journal'
    jdir.write_text('a file where the journal folder should be')
    w = tl.LogWriter(tmp_path / 'logs', SYMBOL, journal_dir=jdir)

    def line(k):
        return (START + k, 'order', tl.dumps({'t': START + k, 'utc': tl._iso(START + k), 'kind': 'order', 'k': k}))
    assert w.write([], journal=[line(1)], samples=[(START, '{"s":1}')]) is False and w.pending('journal') == 1
    assert w.write([], journal=[line(2)]) is False and w.pending('journal') == 2 and w.failures == 2
    jdir.unlink()
    assert w.write([], journal=[line(3)]) is True and w.pending('journal') == 0
    got = [json.loads(ln)['k'] for ln in (jdir / f'{SYMBOL}_{YEAR}.jsonl').read_text().splitlines()]
    assert got == [1, 2, 3]
    assert (tmp_path / 'logs' / f'{SYMBOL}_{DAY}_samples.jsonl').read_text() == '{"s":1}\n'   # (its folder worked)


# ───────────────────────────── trade: once, with what the bot knew ─────────────────────────────

def _polls_of_a_trade(m, tr, pnls, close_pnl, balance_after=1495.8, safety_after=None, pid=7):
    """Drive the trace's trade tracking through one BUY basket without a replay: the entry poll, a poll per floating
    P/L of `pnls`, the poll that closes it (P/L close_pnl at the decision), and the first poll after it. Returns the
    times (entry, close) and the deal-history document of the closed trade."""
    tl = m.tracelog
    sizing = m.app.sizing_record(1500.0, 750.0, 1250.0, 1, 0.01, 10, 'balance', m.clock.time())
    t_in = m.clock.time()

    def snap(view, balance=1500.0, safety=None):
        return {'basket': {'open': view, 'open_score': 2.0, 'fc_score': 1.0, 'trend': {'signal': 0.4},
                           'votes': {'H1': {'rsi': {'vote': 1}, 'macd': {'vote': 1}}}},
                'account': {'balance': balance, 'equity': balance}, 'safety': safety or safety_view(),
                'sizing': sizing, 'turtle': None}

    def view(pnl, **more):
        return dict({'side': 'BUY', 'legs': [{'id': pid}], 'ids': [pid], 'pnl': pnl, 'opened_at': t_in, 'units': 1,
                     'lots': 0.01, 'target_usd': 8.0, 'stop_usd': 4.0, 'target_price': 2008.12, 'stop_price': 1996.12,
                     'vol_unit': 1.0, 'vol_unit_raw': 1.0, 'gap_px': 0.0, 'opened_by': 'bot'}, **more)
    fill = {'done': True, 'kind': 'open', 'side': 'BUY', 'result_price': 2000.15, 'bid': 2000.0, 'ask': 2000.12,
            'spread': 0.12, 'slippage': 0.03, 'slippage_usd': 0.03, 'sl': 1992.12, 'order': pid}
    c = tl._Ctx({})
    tr.polls += 1
    tr._track_trade(c, snap(view(None, listed=False)), {'action': 'OPEN_BUY'}, [fill], m.clock.time())
    for pnl in pnls:
        later(m, 1.0)
        tr.polls += 1
        tr._track_trade(c, snap(view(pnl)), {'action': 'HOLD'}, [], m.clock.time())
    t_out = later(m, 1.0)
    tr.polls += 1
    tr._track_trade(c, snap(view(close_pnl, closed_now=True)), {'action': 'CLOSE_BUY', 'reason': 'stop_loss'}, [], t_out)
    deals = [deal(pid, 0, 0, 2000.15, 0.0, t_in, commission=-0.07),
             deal(pid, 1, 1, 1996.0, close_pnl, t_out, commission=-0.07, swap=-0.01, fee=-0.02)]
    tr._record_exits([pid], 'stop_loss', t_out, close_pnl)
    doc = tr._build_trades(deals, {'basket': {'open': None}}, t_in - 86400, t_out, 3, t_in)
    return t_in, t_out, doc, snap


def test_the_trade_line_joins_the_deal_history_with_what_the_bot_knew(mods, tmp_path):
    """One line when the trade has closed: the history's figures -- profit, swap, commission and fee apart --, the
    facts fixed at the entry (taken on the entry's poll), the highest and lowest floating P/L and when, the P/L at
    the close decision, the account's balance before (at the entry) and after: the balance of the first poll after
    the bot saw the close, with that poll's safety meters. It waits for that poll."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    t_in, t_out, doc, snap = _polls_of_a_trade(m, tr, [0.5, 2.25, 1.0, -3.0, -1.5], -4.15)
    tr._journal_trades(doc, m.clock.time(), t_in)
    tr._flush()
    assert journal_of(out, 'trade') == []                              # the poll after the close has not come yet
    later(m, 1.0)
    tr.polls += 1
    after = safety_view(drop={'pct': 2.8, 'limit': 20.0}, day={'pct': 1.3, 'limit': 12.5},
                        streak={'count': 3, 'limit': 5, 'waiting': 0})
    tr._track_trade(m.tracelog._Ctx({}), {'basket': {'open': None}, 'account': {'balance': 1495.68, 'equity': 1495.68},
                                          'safety': after, 'turtle': None}, {'action': 'PAUSED'}, [], m.clock.time())
    tr._journal_trades(doc, m.clock.time(), t_in)
    tr._journal_trades(doc, m.clock.time(), t_in)                      # (read again: nothing more)
    tr._flush()
    lines = journal_of(out, 'trade')
    assert len(lines) == 1
    x = lines[0]
    assert (x['id'], x['side'], x['legs'], x['leg_ids'], x['lots']) == (7, 'BUY', 1, [7], 0.01)
    assert (x['open_t'], x['close_t'], x['hold_s']) == (pytest.approx(t_in), pytest.approx(t_out), pytest.approx(6.0))
    assert (x['open_price'], x['close_price']) == (2000.15, 1996.0)
    # profit, swap, commission and fee are four figures; together they are the trade's P/L
    assert (x['profit'], x['swap'], x['commission'], x['fee'], x['pnl']) == (-4.15, -0.01, -0.14, -0.02, -4.32)
    assert (x['result'], x['exit_reason'], x['bot_reason'], x['deal_reasons']) == ('loss', 'stop', 'stop_loss', ['expert'])
    assert (x['watched'], x['rebuilt'], x['restarts'], x['closed_by']) == ('full', False, 0, 'bot')
    assert (x['max_pnl'], x['min_pnl'], x['decision_pnl'], x['polls_watched']) == (2.25, -4.15, -4.15, 7)
    assert x['max_pnl_t'] == pytest.approx(t_in + 2.0) and x['min_pnl_t'] == pytest.approx(t_out)
    assert x['watched_from_t'] == pytest.approx(t_in)
    e = x['entry']
    assert (e['rebuilt'], e['side'], e['units'], e['lots'], e['price']) == (False, 'BUY', 1, 0.01, 2000.15)
    assert (e['target_usd'], e['stop_usd'], e['target_price'], e['stop_price'], e['vol_unit']) == (8.0, 4.0, 2008.12, 1996.12, 1.0)
    assert (e['open_score'], e['fc_score'], e['trend_signal'], e['votes']) == (2.0, 1.0, 0.4, {'H1': [1, 1]})
    assert (e['bid'], e['ask'], e['spread'], e['slippage'], e['backstop']) == (2000.0, 2000.12, 0.12, 0.03, 1992.12)
    assert e['sizing']['account_balance'] == 1500.0 and e['sizing']['sizing_balance'] == 750.0
    assert (x['balance_before'], x['balance_after']) == (1500.0, 1495.68)
    assert x['balance_after_t'] == pytest.approx(t_out + 1.0)
    assert x['safety_after'] == {'drop_pct': 2.8, 'day_pct': 1.3, 'streak': 3, 'state': 'on', 'blocked': False}
    assert x['own_total_after'] == -4.32                               # the running total of the bot's own closed P/L
    # the state file says the line is written, and holds no open trade any more
    with open(out / 'state' / f'{SYMBOL}_journal_state.json', encoding='utf-8') as f:
        js = json.load(f)
    assert js['journaled'] == [7] and js['open'] is None and js['closing'] == []
    assert (js['login_tail'], js['branch'], js['symbol'], js['magic']) == (TAIL, DEFAULTS['BRANCH'], SYMBOL, MAGIC)
    assert js['login_sha'] == m.app.safety.login_sha(F.ACCOUNT_LOGIN) and not found(json.dumps(js), str(F.ACCOUNT_LOGIN))


def test_what_the_bot_did_not_see_of_a_trade_is_null_never_zero(mods, tmp_path):
    """A closed trade the bot knows nothing of (it has no record of it: closed while it was not running, or opened
    before its journal existed): the history's figures, and null for everything else, with watched 'none'."""
    m, bot, tr = tracer(mods, tmp_path)
    now = m.clock.time()
    deals = [deal(3, 0, 1, 2000.0, 0.0, now - 900), deal(3, 1, 0, 2001.5, -1.5, now - 600, reason=4)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 86400, now, 3, now - 3600)
    tr._journal_trades(doc, now, now - 3600)
    tr._flush()
    x = journal_of(tmp_path / 'bot_output', 'trade')[0]
    assert (x['id'], x['pnl'], x['exit_reason'], x['watched'], x['deal_reasons']) == (3, -1.5, 'backstop', 'none', ['sl'])
    for key in ('entry', 'max_pnl', 'max_pnl_t', 'min_pnl', 'min_pnl_t', 'polls_watched', 'watched_from_t', 'closed_by',
                'decision_pnl', 'balance_before', 'balance_after', 'balance_after_t', 'safety_after', 'rebuilt',
                'restarts'):
        assert x[key] is None, key
    assert (x['swap'], x['commission'], x['fee']) == (0.0, 0.0, 0.0)   # (the history's own zeros are figures)


def test_only_trades_closed_after_the_live_start_at_most_200_a_read_oldest_first(mods, tmp_path):
    m, bot, tr = tracer(mods, tmp_path)
    now = m.clock.time()
    live = now - 50000
    deals = []
    for k in range(460):                                               # one closed trade every 100 s, oldest first
        t = now - 60000 + 100 * k
        deals += [deal(1000 + k, 0, 0, 2000.0, 0.0, t), deal(1000 + k, 1, 1, 2001.0, 1.0, t + 50)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, live - 86400, now, 3, live)
    assert len(doc['closed']) == 460
    after_live = [x['id'] for x in doc['closed'] if x['close_t'] >= live]
    assert len(after_live) == 360
    counts = []
    for _ in range(4):
        tr._journal_trades(doc, now, live)
        tr._flush()
        counts.append(len(journal_of(tmp_path / 'bot_output', 'trade')))
    assert counts == [200, 360, 360, 360]
    assert [x['id'] for x in journal_of(tmp_path / 'bot_output', 'trade')] == after_live


def test_the_newest_1000_ids_are_remembered_and_older_trades_by_their_time(mods, tmp_path):
    """The state file keeps the newest ids (here 10) and, for those it dropped, the time up to which every trade is
    journaled: a trade from before it is not written a second time, with or without the journal's own tail."""
    m, bot, tr = tracer(mods, tmp_path)
    m.tracelog.JOURNAL_KEEP_IDS = 10
    out = tmp_path / 'bot_output'
    now = m.clock.time()
    deals = []
    for k in range(30):
        t = now - 6000 + 100 * k
        deals += [deal(1000 + k, 0, 0, 2000.0, 0.0, t), deal(1000 + k, 1, 1, 2001.0, 1.0, t + 50)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 86400, now, 3)
    tr._journal_trades(doc, now, None)
    tr._flush()
    assert len(journal_of(out, 'trade')) == 30
    with open(out / 'state' / f'{SYMBOL}_journal_state.json', encoding='utf-8') as f:
        js = json.load(f)
    assert js['journaled'] == list(range(1020, 1030)) and js['journaled_before_t'] == pytest.approx(now - 6000 + 1950)
    os.remove(out / 'journal' / f'{SYMBOL}_{YEAR}.jsonl')              # (not even the journal's tail to read)
    bot2, tr2 = again(m, tmp_path)
    tr2._journal_trades(doc, now, None)
    tr2._flush()
    assert journal_of(out, 'trade') == []


def test_a_process_killed_between_the_trade_line_and_the_state_writes_no_line_twice(mods, tmp_path, monkeypatch):
    """The line goes into the journal first, then the state file says so. Killed in between -- or with a state file
    that is lost, or an old copy of it -- the next process finds the line in the journal's own tail."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    now = m.clock.time()
    deals = [deal(3, 0, 1, 2000.0, 0.0, now - 900), deal(3, 1, 0, 2001.5, -1.5, now - 600),
             deal(4, 0, 0, 2000.0, 0.0, now - 500), deal(4, 1, 1, 2002.0, 2.0, now - 400)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 86400, now, 3)
    real = m.tracelog.write_json_atomic
    order = []

    def killed(path, obj, retries=None, **kw):
        if str(path).endswith('_journal_state.json'):
            order.append('state')
            raise OSError('the process was killed before this write')
        return real(path, obj, retries, **kw)
    monkeypatch.setattr(m.tracelog, 'write_json_atomic', killed)
    real_write = m.tracelog.LogWriter._write_journal
    monkeypatch.setattr(m.tracelog.LogWriter, '_write_journal',
                        lambda self, batch: (order.append('journal'), real_write(self, batch))[1])
    tr._journal_trades(doc, now, None)
    tr._flush()
    assert order[:2] == ['journal', 'state']                           # the journal first
    assert [x['id'] for x in journal_of(out, 'trade')] == [3, 4]
    assert not (out / 'state' / f'{SYMBOL}_journal_state.json').exists()
    monkeypatch.setattr(m.tracelog, 'write_json_atomic', real)
    for _ in range(3):                                                 # the launcher starts it again, and again
        bot2, tr2 = again(m, tmp_path)
        tr2._journal_trades(doc, later(m, 5.0), None)
        tr2._flush()
        assert [x['id'] for x in journal_of(out, 'trade')] == [3, 4]
        assert tr2._js['journaled_before_t'] is None                   # (a journal read to its first line: its ids)
    with open(out / 'state' / f'{SYMBOL}_journal_state.json', encoding='utf-8') as f:
        assert sorted(json.load(f)['journaled']) == [3, 4]


@pytest.mark.slow
def test_restarts_write_no_trade_line_twice_and_keep_the_extremes_saved_before_them(tmp_path):
    """The replay's first basket: its highest floating P/L comes in its second minute, it is stopped out after 5.
    Uninterrupted: one line, watched 'full'. With a restart in the middle of it (after the high) and another right
    after its close: still one line per closed trade; the first one says 'part', 1 restart, and has the high of
    before the restart -- kept in the journal's state file -- and the entry's own facts, not rebuilt ones."""
    ref = _replay(tmp_path / 'ref', 420)
    full = journal_of(ref.out, 'trade')
    closed = baskets(ref.fake, magic=MAGIC)
    assert [x['id'] for x in full] == [b['legs'][0]['pid'] for b in closed][:len(full)] and len(full) >= 1
    first = full[0]
    assert (first['watched'], first['restarts'], first['legs']) == ('full', 0, 2) and first['entry']['rebuilt'] is False
    assert first['max_pnl'] > 0 > first['min_pnl'] == first['decision_pnl']
    assert first['pnl'] == closed[0]['pnl'] and first['balance_after'] == pytest.approx(2000.0 + first['pnl'])
    assert first['balance_before'] == 2000.0 and first['safety_after'] is not None
    mid = (first['max_pnl_t'] + first['close_t']) / 2.0 - START        # after the high, before the close
    r = _replay(tmp_path / 'run', 420, restarts=[mid, first['close_t'] - START + 0.4])
    assert r.run.restarts == 2 and not differs(r.fake.orders, ref.fake.orders)    # (the trading is the same)
    lines = journal_of(r.out, 'trade')
    assert [x['id'] for x in lines] == [x['id'] for x in full]         # one line per closed trade, none twice
    part = lines[0]
    assert (part['watched'], part['restarts'], part['rebuilt']) == ('part', 1, False)
    assert (part['max_pnl'], part['max_pnl_t']) == (first['max_pnl'], first['max_pnl_t'])   # saved before the restart
    assert part['max_pnl_t'] < START + mid and (part['min_pnl'], part['pnl']) == (first['min_pnl'], first['pnl'])
    assert part['entry'] == first['entry']
    assert len(journal_of(r.out, 'start')) == 3


@pytest.mark.slow
def test_a_trade_closed_while_the_bot_was_down_gets_one_line_with_watched_none(tmp_path):
    """The bot is stopped in the middle of a basket; before it is started again the broker closes the position (its
    backstop). The next start books the basket as closed outside the bot; the journal has one line for it: watched
    'none' -- the bot did not see the close, so no extremes and no balance after --, with the facts of its entry from
    the journal's state file. A later restart does not write it again."""
    ref = _replay(tmp_path / 'ref', 200)
    assert ref.fake.positions, 'the replay holds a basket at 200 s'

    def broker_closes(bot, n):
        if n == 1:                                                     # the bot is down: nothing watches
            f = bot.position_helper.mt5
            for p in list(f.positions):
                assert f.close_by_broker(p['ticket'])
    r = _replay(tmp_path / 'run', 420, restarts=[120.3, 300.3], hook=broker_closes)
    assert r.run.restarts == 2
    lines = journal_of(r.out, 'trade')
    first = [x for x in lines if x['open_t'] < START + 120]
    assert len(first) == 1
    x = first[0]
    assert (x['watched'], x['exit_reason'], x['deal_reasons']) == ('none', 'backstop', ['sl'])
    assert x['entry'] is not None and x['entry']['rebuilt'] is False and x['entry']['sizing']['account_balance'] == 2000.0
    for key in ('max_pnl', 'min_pnl', 'decision_pnl', 'balance_after', 'safety_after', 'closed_by'):
        assert x[key] is None, key
    assert x['balance_before'] == 2000.0 and x['pnl'] == pytest.approx(x['profit'])
    assert len({y['id'] for y in lines}) == len(lines)                 # no trade twice, through both restarts


def test_a_trade_taken_over_without_its_record_is_marked_rebuilt(mods, tmp_path):
    """A restart with a basket open and no record of it in the journal's state (the file is gone): the facts are what
    the bot kept of the basket, marked rebuilt, the entry's scores are not known, and the line says 'part'."""
    m, bot, tr = tracer(mods, tmp_path)
    now = m.clock.time()
    sizing = m.app.sizing_record(1500.0, 750.0, 1250.0, 1, 0.01, 10, 'entry', now - 500)
    view = {'side': 'SELL', 'legs': [{'id': 11}], 'ids': [11], 'pnl': 1.2, 'opened_at': now - 500, 'units': 1,
            'lots': 0.01, 'target_usd': 8.0, 'stop_usd': 4.0, 'vol_unit': 1.0, 'opened_by': 'bot'}
    snap = {'basket': {'open': view, 'open_score': -2.0, 'fc_score': -1.0, 'votes': {}}, 'account': {'balance': 1500.0},
            'safety': None, 'sizing': sizing, 'turtle': None}
    c = m.tracelog._Ctx({})
    tr.polls += 1
    tr._track_trade(c, snap, {'action': 'HOLD'}, [], now)
    tr.polls += 1
    tr._track_trade(c, dict(snap, basket=dict(snap['basket'], open=dict(view, pnl=-0.4, closed_now=True))),
                    {'action': 'CLOSE_SELL'}, [], now + 1)
    tr.polls += 1
    tr._track_trade(c, dict(snap, basket={'open': None}), {'action': 'PAUSED'}, [], now + 2)
    deals = [deal(11, 0, 1, 2000.0, 0.0, now - 500), deal(11, 1, 0, 2000.4, -0.4, now + 1)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 86400, now + 2, 3)
    tr._journal_trades(doc, now + 2, None)
    tr._flush()
    x = journal_of(tmp_path / 'bot_output', 'trade')[0]
    assert (x['watched'], x['rebuilt'], x['restarts']) == ('part', True, 0)
    e = x['entry']
    assert (e['rebuilt'], e['side'], e['units'], e['target_usd'], e['stop_usd']) == (True, 'SELL', 1, 8.0, 4.0)
    assert (e['open_score'], e['fc_score'], e['votes'], e['price'], e['slippage']) == (None, None, None, None, None)
    assert e['sizing']['account_balance'] == 1500.0 and x['balance_before'] == 1500.0
    assert (x['max_pnl'], x['min_pnl'], x['balance_after']) == (1.2, -0.4, 1500.0)
    assert x['safety_after'] == {'drop_pct': None, 'day_pct': None, 'streak': None, 'state': None, 'blocked': None}


def test_the_journals_state_of_another_account_is_set_aside(mods, tmp_path):
    """The state file records the account as its tail and its SHA-256. A bot that starts on another account (the
    credentials were changed) does not take the other account's open trade or its journaled ids: the file is set
    aside under a name that says so, and the journal's state starts afresh. A file without the field is accepted."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    path = out / 'state' / f'{SYMBOL}_journal_state.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    other = {'schema': 1, 'symbol': SYMBOL, 'login_sha': m.app.safety.login_sha(87654321), 'login_tail': '...4321',
             'journaled': [1, 2, 3], 'journaled_t': [1.0, 2.0, 3.0], 'open': {'id': 5, 'ids': [5], 'side': 'BUY'},
             'issues': {'FOREIGN_POSITIONS': {'key': '2', 'text': 'x', 'since': 1.0, 'last': 1.0, 'seen': 1.0}}}
    path.write_text(json.dumps(other))
    bot2, tr2 = again(m, tmp_path)
    # (set aside as soon as the trace is made -- by its start-up lines, before the loop: test below)
    assert tr2._js['journaled'] == [] and tr2._js['open'] is None
    tr2.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    assert tr2._js['journaled'] == [] and tr2._js['open'] is None and tr2._js['issues'] == {}
    aside = [n for n in os.listdir(out / 'state') if '.other-account-' in n]
    assert len(aside) == 1 and aside[0].startswith(f'{SYMBOL}_journal_state.json.other-account-2026')
    assert json.loads((out / 'state' / aside[0]).read_text()) == other and not path.exists()
    log = (out / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8')
    assert "| WARN | STATE | the journal's state file was written for another account (...4321)" in log
    assert not found(log, '87654321')
    # a file that names no account is this bot's
    path.write_text(json.dumps({'journaled': [9], 'journaled_t': [9.0]}))
    bot3, tr3 = again(m, tmp_path)
    tr3.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    assert tr3._js['journaled'] == [9] and len([n for n in os.listdir(out / 'state') if '.other-account-' in n]) == 1
    # what cannot be read, or is not a state, counts as none (and never raises)
    for junk in ('', '{"journaled": "x", "open": 5, "closing": 7, "issues": []}', '[1, 2]', '\x00\x01'):
        path.write_text(junk)
        _, tr4 = again(m, tmp_path)
        assert tr4._js['journaled'] == [] and tr4._js['open'] is None and tr4._js['closing'] == []


def test_a_start_that_fails_before_the_loop_never_saves_this_account_over_another_accounts_state(mods, tmp_path):
    """The credentials were changed to a new account and its first starts fail before the trading loop (the launcher
    starts the bot again every 30 s; each start journals its problem). The old account's state is set aside at the
    first of them, before a problem is added to it -- it is never saved again under the new account's mark, so the
    start that reaches the loop does not take the old account's open trade and ids for this account's. A start
    whose credentials could not be loaded knows no account: it sets nothing aside and keeps the file's own mark."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    path = out / 'state' / f'{SYMBOL}_journal_state.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    other_sha = m.app.safety.login_sha(87654321)
    other = {'schema': 1, 'symbol': SYMBOL, 'login_sha': other_sha, 'login_tail': '...4321',
             'journaled': [1, 2, 3], 'journaled_t': [1.0, 2.0, 3.0], 'open': {'id': 5, 'ids': [5], 'side': 'BUY'}}
    path.write_text(json.dumps(other))

    def failed():
        return (later(m, 30.0), 'ERROR', 'START', 'all 3 start attempts failed (TERMINAL_IN_USE: MetaTrader 5 is '
                'logged into another account)', None, None)

    def aside():
        return sorted(n for n in os.listdir(out / 'state') if '.other-account-' in n)
    # no credentials: nothing is known of the account
    b0 = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    b0.state_dir, b0._login, b0._login_tail = None, None, None
    b0._boot_lines.append(failed())
    b0._tracer(SYMBOL)
    js = json.loads(path.read_text())
    assert aside() == [] and (js['login_sha'], js['login_tail'], js['open']) == (other_sha, '...4321', other['open'])
    # the new account's credentials: the old state goes aside before this start's problem is kept
    b1 = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    b1.state_dir = None
    b1._boot_lines.append(failed())
    b1._tracer(SYMBOL)
    assert len(aside()) == 1 and json.loads((out / 'state' / aside()[0]).read_text())['login_sha'] == other_sha
    js = json.loads(path.read_text())
    assert (js['login_sha'], js['login_tail']) == (m.app.safety.login_sha(F.ACCOUNT_LOGIN), TAIL)
    assert (js['journaled'], js['open']) == ([], None) and list(js['issues']) == ['BOOT_START']
    n = len(journal_of(out, 'issue'))
    # the next failed start, and the one that reaches the loop, find this account's state
    b2 = F.make_bot(m, m.fake, SYMBOL, F.Run(), trace_dir=out)
    b2.state_dir = None
    b2._boot_lines.append(failed())
    b2._tracer(SYMBOL)
    bot3, tr3 = again(m, tmp_path)
    tr3.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    assert tr3._js['open'] is None and tr3._js['journaled'] == [] and 'BOOT_START' in tr3._js['issues']
    assert len(aside()) == 1 and len(journal_of(out, 'issue')) == n         # (the same problem: no new line)
    assert not found(''.join(p.read_text(errors='replace') for p in out.rglob('*') if p.is_file()
                                     and '.other-account-' not in p.name), '87654321')


def test_without_a_state_file_no_trade_line_is_written_twice_however_long_the_journal(mods, tmp_path):
    """The state file is gone (or cannot be read) and the journal is longer than the part of it that is read at the
    start: a bot that was running when the oldest line read was written had journaled every trade that closed more
    than a few minutes before it. So a trade whose line is far back in the file is not written again; a trade that
    closed after that line, and that the journal does not have, is."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    now = m.clock.time()
    deals = [deal(3, 0, 1, 2000.0, 0.0, now - 9000), deal(3, 1, 0, 2001.5, -1.5, now - 8000),
             deal(4, 0, 0, 2000.0, 0.0, now - 5000), deal(4, 1, 1, 2002.0, 2.0, now - 4000)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 86400, now, 3)
    tr._journal_trades(doc, now - 3900, None)
    tr._flush()
    assert [x['id'] for x in journal_of(out, 'trade')] == [3, 4]
    jpath = out / 'journal' / f'{SYMBOL}_{YEAR}.jsonl'

    def lines_after(t, n=3300):                        # 3 MB of other lines (orders that repeat for hours)
        one = json.dumps({'t': t, 'utc': DAY + 'T08:00:00.000Z', 'kind': 'order', 'action': 'open', 'pad': 'x' * 900},
                         separators=(',', ':'))
        with open(jpath, 'a', encoding='utf-8') as f:
            f.write((one + '\n') * n)
    lines_after(now - 3500)
    os.remove(out / 'state' / f'{SYMBOL}_journal_state.json')
    # trade 5 closed after those lines (the bot was down then): the journal does not have it
    deals += [deal(5, 0, 0, 2000.0, 0.0, now - 3000), deal(5, 1, 1, 2003.0, 3.0, now - 2000)]
    doc = tr._build_trades(deals, {'basket': {'open': None}}, now - 86400, now, 3)
    bot2, tr2 = again(m, tmp_path)
    tr2._journal_trades(doc, later(m, 5.0), None)
    tr2._flush()
    assert [x['id'] for x in journal_of(out, 'trade')] == [3, 4, 5]           # 5 is new; 3 and 4 not again
    assert tr2._js['journaled_before_t'] == pytest.approx(now - 3500 - m.tracelog.JOURNAL_TAIL_MARGIN_S)
    # lost again, with more lines after trade 5's: none of the three is written again
    lines_after(m.clock.time() + 10.0)
    os.remove(out / 'state' / f'{SYMBOL}_journal_state.json')
    bot3, tr3 = again(m, tmp_path)
    tr3._journal_trades(doc, later(m, 60.0), None)
    tr3._flush()
    assert [x['id'] for x in journal_of(out, 'trade')] == [3, 4, 5]


# ───────────────────────────── safety, skip: what app.py hands over ─────────────────────────────

def test_the_safetys_events_and_a_held_order_are_journal_lines(mods, tmp_path):
    """app.py: self._trace(symbol, 'journal', 'safety', **event) for every item of Tracker.take_events(), and
    'skip' for an order the safety held back. A field called 'kind' keeps its value as 'subkind'. journal() never
    raises, whatever it is given."""
    m, bot, tr = tracer(mods, tmp_path)
    now = m.clock.time()
    bot._trace(SYMBOL, 'journal', 'safety', event='trip', scope='account', rules=['DROP'],
               numbers={'drop_pct': 20.4, 'peak': 1500.0, 'balance': 1194.0}, at=now)
    bot._trace(SYMBOL, 'journal', 'safety', event='cash', ticket=77, amount=-500.0, time=now - 4, counted=True,
               found_after_s=2.4)
    hold = {'why': 'safety', 'side': 'BUY', 'kind': 'entry', 'price': 2000.12, 'until': None, 'refusals': 0}
    bot._trace(SYMBOL, 'journal', 'skip', **hold)
    tr.journal('safety', event='odd', thing=object(), when=datetime(2026, 11, 17, tzinfo=timezone.utc), t=5, utc='x')
    loop = {}
    loop['self'] = loop
    tr.journal('safety', event='loop', value=loop)                     # JSON cannot hold it: the line says so
    tr.journal()                                                       # (not even a kind)
    tr.journal(None)
    tr._flush()
    lines = journal_of(tmp_path / 'bot_output')
    trip, cash, skip, odd, bad, none = lines
    assert (trip['kind'], trip['event'], trip['scope'], trip['rules'], trip['at']) == ('safety', 'trip', 'account', ['DROP'], now)
    assert trip['numbers']['drop_pct'] == 20.4 and trip['t'] == pytest.approx(now) and trip['utc'].startswith(DAY)
    assert (cash['event'], cash['ticket'], cash['amount'], cash['found_after_s']) == ('cash', 77, -500.0, 2.4)
    assert (skip['kind'], skip['subkind'], skip['why'], skip['side'], skip['price']) == ('skip', 'entry', 'safety', 'BUY', 2000.12)
    assert (odd['t_event'], odd['utc_event']) == (5, 'x') and odd['thing'].startswith('<object') and odd['when'].startswith('2026-11-17')
    assert bad['kind'] == 'safety' and 'not_written' in bad and none['kind'] == 'None'
    errors = [ln for ln in (tmp_path / 'bot_output' / 'logs' / f'{SYMBOL}_{DAY}.log').read_text().splitlines()
              if '| ERROR | TRACE | the trace hook journal() failed' in ln]
    assert len(errors) == 1                                            # the call without a kind: logged, not raised


# ───────────────────────────── day ─────────────────────────────

def test_the_day_line_at_the_first_poll_of_a_new_utc_day(mods, tmp_path):
    """For the day that ended: the account's last balance and equity, its high (the safety's), what both bots booked
    that day (deposits and withdrawals are not in it), the cash operations, and complete: false when the bot did
    not watch the whole day (here it started at 08:00). A full day says complete: true. A bot that was down over
    midnight writes the line of the day it last saw at its next start, complete: false."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    midnight = (int(START) // 86400 + 1) * 86400

    def poll(t, balance, tr_=None, day_start=1500.0, cash=0.0, peak=1520.0):
        m.clock.now_ms = int(t * 1000)
        view = safety_view(drop={'pct': 0.0, 'limit': 20.0, 'peak': peak, 'peak_at': START, 'balance': balance},
                           day={'pct': 0.0, 'limit': 12.5, 'day0': day_start, 'day': DAY, 'since': 'midnight',
                                'start_balance': day_start, 'start_at': START, 'cash': cash})
        (tr_ or tr).poll(ctx_of(m, account_info={'balance': balance, 'equity': balance + 1.5, 'profit': 1.5},
                                _safety=view))
    poll(START + 10, 1500.0)
    poll(START + 3600, 1712.0, cash=200.0, day_start=1700.0, peak=1720.0)   # (a deposit of 200: the day's start moves)
    poll(midnight - 30, 1708.25, cash=200.0, day_start=1700.0, peak=1720.0)
    assert journal_of(out, 'day') == []
    poll(midnight + 20, 1708.25, day_start=1708.25, peak=1720.0)
    days = journal_of(out, 'day')
    assert len(days) == 1
    d = days[0]
    assert (d['day'], d['balance'], d['equity'], d['high']) == (DAY, 1708.25, 1709.75, 1720.0)
    assert (d['booked'], d['start_balance'], d['cash']) == (8.25, 1700.0, 200.0)
    assert (d['balance_high'], d['balance_low'], d['polls']) == (1712.0, 1500.0, 3)
    # it started at 08:00: it did not run through the midnight that began the day
    assert (d['complete'], d['ran_through_midnight'], d['watched_from_midnight'], d['watched_whole_day']) == (
        False, True, False, False)
    assert d['first_t'] == START + 10 and d['last_t'] == midnight - 30 and d['t'] == midnight + 20
    for t in range(midnight + 100, midnight + 86400, 100):              # a whole day of polls
        poll(t, 1710.0, day_start=1708.25)
    poll(midnight + 86400 + 15, 1710.0, day_start=1710.0)
    days = journal_of(out, 'day')
    assert len(days) == 2 and (days[1]['complete'], days[1]['booked'], days[1]['longest_gap_s']) == (True, 1.75, 100.0)
    assert days[1]['watched_whole_day'] is True and days[1]['watched_from_midnight'] is True
    # down over the next midnight: the day it last saw, at its next start
    poll(midnight + 86400 + 3600, 1711.0, day_start=1710.0)
    bot2, tr2 = again(m, tmp_path)                                      # (the journal's state has the running day)
    poll(midnight + 2 * 86400 + 8 * 3600, 1711.0, tr_=tr2, day_start=1711.0)
    days = journal_of(out, 'day')
    assert len(days) == 3 and (days[2]['complete'], days[2]['ran_through_midnight']) == (False, False)
    assert days[2]['balance'] == 1711.0 and days[2]['last_t'] == midnight + 86400 + 3600
    # a day it ran through from midnight to midnight, with pauses of 10 minutes in between (restarts, a slow
    # terminal): the day's booked figures are whole -- complete -- and the pauses are said
    d5 = midnight + 3 * 86400
    poll(d5 + 30, 1711.0, tr_=tr2, day_start=1711.0)
    for t in range(d5 + 600, d5 + 86400 - 60, 600):
        poll(t, 1712.0, tr_=tr2, day_start=1711.0)
    poll(d5 + 86400 - 60, 1712.0, tr_=tr2, day_start=1711.0)
    poll(d5 + 86400 + 30, 1712.0, tr_=tr2, day_start=1712.0)
    days = journal_of(out, 'day')
    assert len(days) == 5 and days[3]['complete'] is False              # (day 4: from 08:00 on)
    x = days[4]
    assert x['day'] == datetime.fromtimestamp(d5, tz=timezone.utc).strftime('%Y-%m-%d')
    assert (x['complete'], x['ran_through_midnight'], x['watched_from_midnight'], x['watched_whole_day']) == (
        True, True, True, False)
    assert (x['longest_gap_s'], x['booked'], x['balance']) == (600.0, 1.0, 1712.0)


# ───────────────────────────── issue ─────────────────────────────

def test_a_problem_is_journalled_when_it_starts_changes_and_ends_and_every_15_minutes(mods, tmp_path):
    """The problems a poll shows are states (the dashboard draws its banners from the same keys of the trace): each
    is one line when it starts, one when it becomes another of its kind, one every 15 minutes while it lasts, and
    one when it has ended (it has not shown for a minute of polls that read the terminal)."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'

    def poll(dt, **over):
        later(m, dt)
        tr.poll(ctx_of(m, **over))

    def foreign(n):
        return {'positions': n, 'examples': [{'ticket': '...01', 'magic': 0}], 'old_bot_age_s': None,
                'old_bot_same_terminal': False}
    poll(1)
    assert journal_of(out, 'issue') == []
    for _ in range(30):
        poll(1, _foreign=foreign(2))
    poll(1, _foreign=foreign(3))                                        # another count: it changed
    for _ in range(950):
        poll(1, _foreign=foreign(3))                                    # ... and lasts: again after 15 minutes
    for _ in range(59):
        poll(1, _foreign=foreign(0))                                    # gone for less than a minute: not over yet
    assert [x['state'] for x in journal_of(out, 'issue')] == ['start', 'change', 'still']
    poll(2, _foreign=foreign(0))
    lines = [x for x in journal_of(out, 'issue') if x['code'] == 'FOREIGN_POSITIONS']
    assert [x['state'] for x in lines] == ['start', 'change', 'still', 'end']
    assert '2 trade(s) that are not this bot\'s are open on XAUUSDm' in lines[0]['text'] and '3 trade(s)' in lines[1]['text']
    assert lines[2]['lasted_s'] == pytest.approx(931.0, abs=2.0) and lines[2]['since'] == lines[0]['t']
    assert lines[3]['lasted_s'] == pytest.approx(981.0, abs=2.0) and lines[3]['last_seen'] == pytest.approx(lines[0]['t'] + 981)
    # each state of the trace that is a problem
    safety_err = safety_view(error='the safety state could not be saved since 14:05 UTC (PermissionError)',
                             blocked=True, state='error', partner={'account_differs': True, 'limits_differ': True})
    bot._terminal = dict(bot._terminal or {}, trade_allowed=False, tradeapi_disabled=True)
    bot._acct = dict(bot._acct or {}, trade_allowed=False, trade_expert=False)
    poll(1, _safety=safety_err, _foreign={'positions': 0, 'old_bot_age_s': 12.0, 'old_bot_same_terminal': True},
         _open_hold={'why': 'refused_backoff', 'side': 'BUY', 'kind': 'entry', 'refusals': 9, 'until': m.clock.time() + 20})
    poll(1, _foreign={'positions': 0, 'old_bot_age_s': 12.0, 'old_bot_same_terminal': False})
    started = {x['code']: x for x in journal_of(out, 'issue')[4:] if x['state'] == 'start'}
    assert set(started) == {'SAFETY_ERROR', 'PARTNER_ACCOUNT_DIFFERS', 'PARTNER_LIMITS_DIFFER', 'TRADING_NOT_ALLOWED',
                            'OLD_BOT_SAME_TERMINAL', 'OLD_BOT_RUNNING', 'REFUSED_BACKOFF'}
    assert 'Algo Trading is off in MetaTrader 5' in started['TRADING_NOT_ALLOWED']['text']
    assert 'the bot can neither open nor close' in started['TRADING_NOT_ALLOWED']['text']
    with open(out / f'{SYMBOL}_trace.json', encoding='utf-8') as f:       # the same states, as the dashboard reads them
        snap = json.load(f)
    assert snap['health']['trading_not_allowed'] == ['algo_trading_off', 'python_api_disabled',
                                                     'account_trade_disabled', 'account_expert_disabled']
    assert snap['foreign']['old_bot_age_s'] == 12.0 and snap['safety'] is None


def test_an_order_held_back_now_and_then_is_one_problem_not_one_per_poll(mods, tmp_path):
    """The slower retry after refused opens: the hold shows on the polls between two tries and not on the poll of a
    try. That is one problem that lasts, not a start and an end every 30 seconds."""
    m, bot, tr = tracer(mods, tmp_path)
    hold = {'why': 'refused_backoff', 'side': 'BUY', 'kind': 'entry', 'refusals': 5, 'until': None}
    for i in range(300):
        later(m, 1.0)
        tr.poll(ctx_of(m, buy_signal='BUY', _open_hold=None if i % 30 == 29 else dict(hold)))
    lines = [x for x in journal_of(tmp_path / 'bot_output', 'issue') if x['code'] == 'REFUSED_BACKOFF']
    assert [x['state'] for x in lines] == ['start']
    for _ in range(62):
        later(m, 1.0)
        tr.poll(ctx_of(m))
    lines = [x for x in journal_of(tmp_path / 'bot_output', 'issue') if x['code'] == 'REFUSED_BACKOFF']
    assert [x['state'] for x in lines] == ['start', 'end']


def test_the_problems_of_the_events_and_of_a_start_across_restarts(mods, tmp_path):
    """A problem named by an event of the strategy log lasts until a poll reads the terminal again; one that is a
    moment (another program closed a trade ...) is one line, the same one again at most every 15 minutes. The
    launcher starts a refused bot again every 30 s: the problem is kept in the journal's state file, so it is not
    announced at every start, and its end is said when the bot runs again. What the journal has as its own safety,
    skip and order lines is no issue."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    in_use = {'problem': 'TERMINAL_IN_USE: MetaTrader 5 at C:\\x is logged into another account (...4321 on S).',
              'login_tail': '...4321', 'own_login_tail': TAIL}
    for k in range(40):                                                 # 20 minutes of restarts
        _, t = again(m, tmp_path)
        t.event('TERMINAL_IN_USE', 'ERROR', dict(in_use))
        t.boot([(m.clock.time(), 'ERROR', 'START', 'all 3 start attempts failed (TERMINAL_IN_USE: ...)', None, None)])
        later(m, 30.0)
    lines = journal_of(out, 'issue')
    assert [(x['code'], x['state']) for x in lines] == [
        ('TERMINAL_IN_USE', 'start'), ('BOOT_START', 'start'), ('TERMINAL_IN_USE', 'still'), ('BOOT_START', 'still')]
    assert lines[2]['lasted_s'] == pytest.approx(900.0, abs=31.0)
    _, t = again(m, tmp_path)                                           # another account holds it now: it changed
    t.event('TERMINAL_IN_USE', 'ERROR', dict(in_use, problem=in_use['problem'].replace('...4321', '...9999')))
    assert [(x['code'], x['state']) for x in journal_of(out, 'issue')][4:] == [('TERMINAL_IN_USE', 'change')]
    later(m, 90.0)
    _, t = again(m, tmp_path)                                           # this start works: the loop polls
    t.poll(ctx_of(m))
    ended = [(x['code'], x['state']) for x in journal_of(out, 'issue')][5:]
    assert sorted(ended) == [('BOOT_START', 'end'), ('TERMINAL_IN_USE', 'end')]
    # moments: one line each, the same one again only after 15 minutes
    for _ in range(3):
        t.event('OTHER_PROGRAM', 'ERROR', {'text': 'another program closed this bot\'s trade at 14:05 UTC'})
        t.event('CLOSE_RESULT_UNKNOWN', 'SIGNAL', {'note': 'the result of trade 77 is not in the deal history'})
        t.event('SOMETHING_NEW', 'ERROR', {'note': 'an event this trace has no name for'})
        later(m, 60.0)
    moments = journal_of(out, 'issue')[7:]
    assert sorted((x['code'], x['state']) for x in moments) == [
        ('CLOSE_RESULT_UNKNOWN', 'event'), ('OTHER_PROGRAM', 'event'), ('SOMETHING_NEW', 'event')]
    later(m, 900.0)
    t.event('OTHER_PROGRAM', 'ERROR', {'text': 'another program closed this bot\'s trade at 14:05 UTC'})
    assert len(journal_of(out, 'issue')) == 11
    # the journal's own safety, skip and order lines are not issues as well
    for name in ('SAFETY_SKIP', 'SAFETY_BLOCKED', 'SAFETY_UNBLOCKED', 'BUY_REFUSED', 'SELL_MORE_REFUSED', 'ACCOUNT_OK'):
        t.event(name, 'SIGNAL', {'note': 'x'})
    assert len(journal_of(out, 'issue')) == 11


# ───────────────────────────── the samples ─────────────────────────────

def test_one_line_of_figures_a_minute_also_from_skipped_polls(mods, tmp_path):
    """logs/<SYMBOL>_<day>_samples.jsonl: per minute the last quote, the spread's lowest, average and highest, how many
    polls saw a new tick, the largest and the smallest age of the tick (the smallest is the clocks' offset), the
    account, this bot's and the whole account's open P/L, the positions (own, not its own), the three safety meters,
    the polls and their times, the polls on which an order was held back, the terminal's ping. A minute of skipped
    polls only is a line of nulls."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    m.clock.now_ms = int((START + 60) * 1000)                           # 08:01:00
    bot._terminal = {'build': m.fake.build, 'ping_ms': round(m.fake.ping_last / 1000.0, 1)}   # (app.py's poll guard)
    held = {'why': 'safety', 'side': 'BUY', 'kind': 'entry', 'price': 1.0, 'until': None, 'refusals': 0}
    for k in range(60):                                                 # a minute of good polls, one a second
        now = m.clock.time()
        new_tick = k % 3 != 2                                           # every third poll sees the tick of the one before
        age = 0.25 + (0.5 if k == 9 else 0.0) + (0.0 if new_tick else 1.0)
        spread = 0.10 + (0.30 if k == 20 else 0.0) + (0.02 if k % 2 else 0.0)
        tick = types.SimpleNamespace(bid=2000.0 + k, ask=2000.0 + k + spread, time_msc=int(round((now - age) * 1000)),
                                     time=int(now))
        tr.poll(ctx_of(m, _tick=tick, iteration_ms=10.0 + k, _safety=safety_view(), _open_hold=held if k < 7 else None,
                       _foreign={'positions': 2, 'examples': [], 'old_bot_age_s': None, 'old_bot_same_terminal': False},
                       account_info={'balance': 1500.0 + k, 'equity': 1503.0 + k, 'margin': 2.0, 'margin_free': 1501.0 + k,
                                     'margin_level': 75000.0, 'profit': 3.0},
                       buy_positions={'total_profit': 1.25, 'count': 1}, _buy_ct=0))
        later(m, 1.0)
    for _ in range(60):                                                 # 08:02: the terminal is gone
        tr.poll_skipped('positions', 'positions_get(XAUUSDm) returned None')
        later(m, 1.0)
    tr.poll(ctx_of(m))                                                  # 08:03:00: the minute before is written
    rows = [json.loads(ln) for ln in (out / 'logs' / f'{SYMBOL}_{DAY}_samples.jsonl').read_text().splitlines()]
    assert len(rows) == 2
    a, b = rows
    assert (a['t'], a['utc'], a['polls'], a['skipped']) == (START + 60, f'{DAY}T08:01:00.000Z', 60, 0)
    assert (a['bid'], a['ask']) == (2059.0, pytest.approx(2059.12))     # the minute's last quote
    assert (a['spread_min'], a['spread_max']) == (pytest.approx(0.10), pytest.approx(0.40))
    assert a['spread_avg'] == pytest.approx((60 * 0.10 + 0.30 + 30 * 0.02) / 60)
    assert a['ticks_seen'] == 40 and a['tick_gap_max_s'] == pytest.approx(1.25) and a['clock_offset_s'] == pytest.approx(0.25)
    assert (a['balance'], a['equity'], a['margin'], a['margin_free'], a['margin_level']) == (1559.0, 1562.0, 2.0, 1560.0, 75000.0)
    assert (a['floating_own'], a['floating_account'], a['positions_own'], a['positions_foreign']) == (1.25, 3.0, 0, 2)
    assert (a['drop_pct'], a['day_pct'], a['streak'], a['units']) == (2.5, 1.0, 2, 1)
    assert (a['poll_ms_avg'], a['poll_ms_max']) == (pytest.approx(39.5), 69.0) and a['trace_ms_max'] >= a['trace_ms_avg'] > 0
    assert a['suppressed_polls'] == 7 and a['ping_ms'] == round(m.fake.ping_last / 1000.0, 1)
    assert (b['t'], b['polls'], b['skipped']) == (START + 120, 60, 60)
    for key in ('bid', 'ask', 'spread_min', 'spread_avg', 'spread_max', 'ticks_seen', 'tick_gap_max_s', 'clock_offset_s',
                'balance', 'equity', 'margin', 'margin_free', 'margin_level', 'floating_own', 'floating_account',
                'positions_own', 'positions_foreign', 'drop_pct', 'day_pct', 'streak', 'poll_ms_avg', 'poll_ms_max',
                'suppressed_polls'):
        assert b[key] is None, key
    assert set(a) == set(b)


@pytest.mark.slow
def test_a_replay_has_a_sample_for_every_minute(tmp_path):
    r = _replay(tmp_path, 420)
    rows = [json.loads(ln) for ln in (r.out / 'logs' / f'{SYMBOL}_{DAY}_samples.jsonl').read_text().splitlines()]
    assert [x['t'] for x in rows] == [START + 60 * k for k in range(6)]  # (the running minute is not written yet)
    for x in rows:
        assert 50 <= x['polls'] <= 60 and x['skipped'] == 0 and x['bid'] is not None
        assert x['spread_min'] == x['spread_max'] == pytest.approx(0.12) and x['balance'] is not None
        assert x['ticks_seen'] == x['polls'] and 0 < x['clock_offset_s'] < 1.0 and x['positions_own'] in (0, 1, 2)
    assert [x['positions_own'] for x in rows] == [1, 1, 1, 1, 1, 0]      # (the last poll of each minute)


# ───────────────────────────── no file while the bot holds mt5_lock ─────────────────────────────

def test_no_writer_of_the_journal_the_samples_or_the_state_touches_a_file_inside_mt5_lock(mods, tmp_path, monkeypatch):
    """Inside the lock the bot sends orders and reads the terminal: an order line, a journal line of the safety, a
    problem named by an event (an account refused between two legs of a close), a start-up line of a reconnect are
    all made there -- and none opens, replaces, removes, lists or makes a file. Everything is written by the next
    poll hook outside the lock, in the order it was made."""
    m, bot, tr = tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    tr.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    tr.poll(ctx_of(m))
    touched = []
    tl = m.tracelog

    def spy(name, real):
        def call(path, *a, **k):
            if str(tmp_path) in str(path):
                touched.append((name, bot.mt5_lock.locked(), os.path.basename(str(path))))
            return real(path, *a, **k)
        return call
    monkeypatch.setattr(tl, 'open', spy('open', builtins.open), raising=False)
    for name in ('replace', 'remove', 'makedirs', 'listdir', 'stat'):
        monkeypatch.setattr(tl.os, name, spy(name, getattr(os, name)))
    monkeypatch.setattr(tl.os.path, 'getsize', spy('getsize', os.path.getsize))
    quote = {'bid': 2000.0, 'ask': 2000.12, 't_msc': 1}
    later(m, 61.0)
    with bot.mt5_lock:
        tr.order(request(0), answer(price=2000.15, order=41), False, 1.0, quote)
        tr.order(request(1, position=41, price=2000.0), None, True, None, quote)
        tr.journal('safety', event='trip', scope='bot', rule='STREAK', count=5)
        tr.journal('skip', why='safety', side='BUY', kind='entry')
        tr.event('ACCOUNT_REFUSED', 'ERROR', {'problem': 'MetaTrader 5 is logged into account ...4321 on S'})
        tr.event('OTHER_PROGRAM', 'ERROR', {'text': 'another program closed this bot\'s trade'})
        tr.event('SAFETY_BLOCKED', 'SIGNAL', {'reasons': ['The account fell 20.4% below its high (limit 20%).']})
        tr.boot([(m.clock.time(), 'ERROR', 'TERMINAL', 'MT5 initialize failed: initialize failed: (-10003, x)', None, None)])
        tr.state_note('WARN', 'a note made inside the lock')
        tr.log('INFO', 'TEST', 'a line made inside the lock')
        tr.exception('LOOP', 'not inside an except block')
    assert touched == []
    assert not bot.mt5_lock.locked()
    tr.poll(ctx_of(m))                                                  # the end of the poll: outside the lock
    assert touched and not any(locked for _, locked, _ in touched)
    written = {name for kind, _, name in touched if kind == 'open'}
    assert {f'{SYMBOL}_{DAY}.log', f'{SYMBOL}_{DAY}_events.jsonl', f'{SYMBOL}_{DAY}_samples.jsonl',
            f'{SYMBOL}_{YEAR}.jsonl'} <= written
    kinds = [(x['kind'], x.get('action') or x.get('event') or x.get('code') or x.get('subkind'))
             for x in journal_of(out) if x['t'] > START + 30]
    assert kinds[:6] == [('order', 'open'), ('order', 'close'), ('safety', 'trip'), ('skip', 'entry'),
                         ('issue', 'ACCOUNT_REFUSED'), ('issue', 'OTHER_PROGRAM')]
    assert ('issue', 'BOOT_TERMINAL') in kinds
    log = (out / 'logs' / f'{SYMBOL}_{DAY}.log').read_text(encoding='utf-8')
    for needle in ('| ORDER | ORDER | open BUY 0.01 lot', '-> not sent: the account guard refused it',
                   '| ERROR | ACCOUNT | not trading: MetaTrader 5 is logged into account ...4321 on S',
                   '| WARN | SAFETY | the safety has blocked new trades: The account fell 20.4% below its high',
                   '| WARN | STATE | a note made inside the lock', '| INFO | TEST | a line made inside the lock'):
        assert needle in log, needle
