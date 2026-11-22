"""
The trace of a real-money bot (tracelog.py; spec sections 9 and 14): what app.py hands over by name and what the
dashboard reads back.

  * the new top-level keys of <SYMBOL>_trace.json -- branch, mode, version, sizing, safety, open_hold, foreign --
    and the account block of a real account; none of account / sizing / safety / foreign is null on a poll that had
    them; a skipped poll keeps the last good poll's;
  * the states the dashboard's banners are drawn from (health.trading_not_allowed, health.disk_low, foreign.*,
    safety.error, safety.partner.*, open_hold.why);
  * an opening order held back (_open_hold): the basket's entry is BLOCKED with that reason, tested before
    OPEN_FAILED; a held ladder add and a held Turtle add are a failing gate of the add; a held Turtle entry is a
    gate of the self-check list and BLOCKED -- and the trace's own self-check stays quiet;
  * the events of the real-money layer, each with a level and a plain sentence;
  * the account number: only its tail leaves the module, whatever it is handed;
  * the wording: no text of tracelog.py speaks of a demo account, a virtual balance or a slot.
"""
import json
import os
import sys
import types
from datetime import datetime, timezone

import pytest

from conftest import DEFAULTS, F, MAGIC, ROOT, SCALED, START, market, run_bot, wording_offenders, string_literals
from conftest import found
import test_journal as TJ
import test_turtle_bot as TB

SYMBOL = 'XAUUSDm'
DAY = datetime.fromtimestamp(START, tz=timezone.utc).strftime('%Y-%m-%d')
TAIL = TJ.TAIL
HOLDS = ('safety', 'safety_checking', 'refused_backoff', 'balance_unknown', 'old_bot')


def trace_of(folder, symbol=SYMBOL):
    with open(os.path.join(str(folder), f'{symbol}_trace.json'), encoding='utf-8') as f:
        return json.load(f)


def log_of(folder, symbol=SYMBOL):
    logs = os.path.join(str(folder), 'logs')
    out = []
    for n in sorted(x for x in os.listdir(logs) if x.endswith('.log')) if os.path.isdir(logs) else []:
        with open(os.path.join(logs, n), encoding='utf-8') as f:
            out += f.read().splitlines()
    return out


def sizing(m, account_balance=1500.0, units=1, source='balance'):
    return m.app.sizing_record(account_balance, round(account_balance * 0.5, 2), 1250.0, units, 0.01, 10, source, START)


def foreign(n=0, age=None, same=False):
    return {'positions': n, 'examples': [{'ticket': '...0042', 'magic': 0, 'comment': '', 'volume': 0.02, 'side': 'BUY',
                                         'sl': 0.0, 'tp': 4000.0, 'price_open': 2000.0}][:n],
            'old_bot_age_s': age, 'old_bot_same_terminal': same}


# ───────────────────────────── the keys of the trace ─────────────────────────────

def test_the_trace_keys_of_the_real_money_layer_after_one_good_poll(mods, tmp_path):
    """One poll that read the terminal, with everything app.py hands over: the trace has branch, mode, version, the
    account block of a real account, and sizing, safety, open_hold and foreign as they were handed -- none of
    account / sizing / safety / foreign is null."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    bot._account_problem()                                              # (the poll guard: the terminal's own facts)
    bot._terminal_problem()
    view = TJ.safety_view()
    hold = {'why': 'safety', 'side': 'BUY', 'kind': 'entry', 'price': 2000.12, 'until': None, 'refusals': 0}
    tr.poll(TJ.ctx_of(m, buy_signal='BUY', _sizing=sizing(m), _safety=view, _open_hold=hold, _foreign=foreign(1),
                      account_info={'balance': 1500.0, 'equity': 1498.4, 'margin': 2.0, 'margin_free': 1496.4,
                                    'margin_level': 74920.0, 'profit': -1.6},
                      buy_positions=None, sell_positions=None))
    s = trace_of(out)
    assert (s['schema'], s['branch'], s['mode'], s['version']) == (1, DEFAULTS['BRANCH'], 'live', DEFAULTS['VERSION'])
    for key in ('account', 'sizing', 'safety', 'foreign', 'open_hold', 'health', 'market', 'decision'):
        assert s[key] is not None, key
    assert s['sizing'] == sizing(m) and s['safety'] == view and s['open_hold'] == hold and s['foreign'] == foreign(1)
    a = s['account']
    assert (a['login_tail'], a['server'], a['currency'], a['leverage'], a['trade_allowed'], a['trade_expert']) == (
        TAIL, F.ACCOUNT_SERVER, 'USD', m.fake.leverage, True, True)
    assert (a['balance'], a['equity'], a['floating_account'], a['floating_own']) == (1500.0, 1498.4, -1.6, 0.0)
    # booked today by both bots: the balance against the one the UTC day began with (the safety keeps it)
    assert a['day_realised'] == round(1500.0 - view['day']['start_balance'], 2) == -15.15
    assert (a['units'], a['lot'], a['share'], a['next_unit_at']) == (1, 0.01, 0.5, 2500.0)
    assert a['unit_rule'] == 'unit = floor(0.5 x account balance / 1250) + 1, at most 10, re-derived only while flat'
    h = s['health']
    assert (h['login_tail'], h['own_login_tail'], h['trade_mode_name'], h['margin_mode_name']) == (TAIL, TAIL, 'real', 'hedging')
    assert h['trading_not_allowed'] == [] and h['disk_low'] is False
    assert (h['terminal_build'], h['ping_ms']) == (m.fake.build, round(m.fake.ping_last / 1000.0, 1))
    text = json.dumps(s)
    assert not found(text, 'virtual') and not found(text, str(F.ACCOUNT_LOGIN))
    for gone in ('login', 'demo_login'):
        assert gone not in h
    # what the trace keeps is a copy: the bot's own dicts can change afterwards
    view['drop']['pct'] = 99.0
    assert tr._last_snapshot['safety']['drop']['pct'] == 2.5


def test_a_name_app_py_does_not_hand_over_reads_null_and_nothing_fails(mods, tmp_path):
    """The poll's locals are read by name: one that is not there (yet) leaves its key null. No line of the log is an
    error for it."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    tr.poll(TJ.ctx_of(m))
    s = trace_of(out)
    assert (s['sizing'], s['safety'], s['open_hold'], s['foreign']) == (None, None, None, None)
    assert s['account']['day_realised'] is None and s['account']['balance'] == 1500.0
    # what is not a dict is not taken (the trace never guesses a shape)
    tr.poll(TJ.ctx_of(m, _sizing='x', _safety=5, _open_hold=[1], _foreign=True))
    s = trace_of(out)
    assert (s['sizing'], s['safety'], s['open_hold'], s['foreign']) == (None, None, None, None)
    # the positions read's own note of what is not the bot's, when the poll made no _foreign of it
    bot.position_helper.last_foreign = {'count': 2, 'examples': [{'magic': 0}]}
    later = TJ.later(m, 2.0)
    tr.poll(TJ.ctx_of(m))
    assert trace_of(out)['foreign'] == {'positions': 2, 'examples': [{'magic': 0}], 'old_bot_age_s': None,
                                        'old_bot_same_terminal': None}
    # ... and the bot's flag of an old bot on this server: its age only while it is alive (the amber banner reads
    # 'not None'; the old bots' files stay in the parent folder long after they were stopped)
    bot._old_bot_alive_flag, bot._old_bot_age_s = False, 86400.0
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m))
    assert trace_of(out)['foreign']['old_bot_age_s'] is None
    bot._old_bot_alive_flag, bot._old_bot_age_s, bot._old_bot_same_terminal = True, 14.5, lambda: True
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m))
    assert trace_of(out)['foreign'] == {'positions': 2, 'examples': [{'magic': 0}], 'old_bot_age_s': 14.5,
                                        'old_bot_same_terminal': True}
    bot.position_helper.last_foreign = None
    bot._old_bot_same_terminal = lambda: 1 / 0                           # (a flag that cannot be read: not known)
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m))
    assert trace_of(out)['foreign'] == {'positions': None, 'examples': None, 'old_bot_age_s': 14.5,
                                        'old_bot_same_terminal': None}
    assert later and not [ln for ln in log_of(out) if '| ERROR |' in ln or '| WARN |' in ln]


def test_a_skipped_poll_keeps_the_sizing_the_safety_and_the_foreign_of_the_last_good_poll(mods, tmp_path):
    """A poll that could not read the terminal decides nothing and counts nothing: the safety bar must not go blank
    during an outage. open_hold is this poll's own: nothing was wanted on a poll that decided nothing. Of `foreign`
    the positions are the last good poll's (none were read), the old bot is what the bot's flag says now: app.py looks
    at the old bot's files on every pass, a refused one too (spec 6.2 C)."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    view = TJ.safety_view(blocked=True, account_blocked=True, blocked_scope='account', state='account_blocked')
    hold = {'why': 'safety', 'side': 'SELL', 'kind': 'entry', 'price': 2000.0, 'until': None, 'refusals': 0}
    # (the poll's _foreign is made from the bot's flags: an old bot alive on another MetaTrader 5, 30 s ago)
    bot._old_bot_alive_flag, bot._old_bot_age_s, bot._old_bot_same_terminal = True, 30.0, lambda: False
    tr.poll(TJ.ctx_of(m, sell_signal='SELL', _sizing=sizing(m), _safety=view, _open_hold=hold, _foreign=foreign(1, 30.0)))
    good = trace_of(out)
    for kind, problem in (('positions', 'positions_get(XAUUSDm) returned None'), ('guard', None),
                          ('account_recheck', 'MetaTrader 5 is logged into account ...4321')):
        TJ.later(m, 1.0)
        tr.poll_skipped(kind, problem)
        s = trace_of(out)
        assert s['stale'] is True and s['decision']['action'] == 'SKIPPED'
        assert (s['sizing'], s['safety'], s['foreign'], s['account']) == (
            good['sizing'], good['safety'], good['foreign'], good['account'])
        assert s['sizing'] is not None and s['safety']['blocked'] is True and s['foreign']['positions'] == 1
        assert s['open_hold'] is None and (s['branch'], s['mode'], s['version']) == (
            good['branch'], good['mode'], good['version'])
    # the old bot as the flag says now: alive on this bot's MetaTrader 5 (the refused account's red banner then says
    # to stop it), then gone -- the positions stay the last good poll's
    bot._old_bot_age_s, bot._old_bot_same_terminal = 12.0, lambda: True
    TJ.later(m, 1.0)
    tr.poll_skipped('guard', None)
    assert trace_of(out)['foreign'] == dict(good['foreign'], old_bot_age_s=12.0, old_bot_same_terminal=True)
    bot._old_bot_alive_flag, bot._old_bot_age_s = False, 4000.0
    TJ.later(m, 1.0)
    tr.poll_skipped('guard', None)
    assert trace_of(out)['foreign'] == dict(good['foreign'], old_bot_age_s=None, old_bot_same_terminal=False)
    # ... and a skipped poll before any good one has nothing to keep
    _, tr2 = TJ.again(m, tmp_path)
    tr2.poll_skipped('positions', 'x')
    s = trace_of(out)
    assert (s['sizing'], s['safety'], s['foreign'], s['account']) == (None, None, None, None)


def test_the_states_the_dashboards_banners_are_drawn_from(mods, tmp_path):
    """Banners come from the trace's current state, not from events: a condition that still holds must still show
    after the dashboard was started again. Trading switched off in the terminal or for the account is read on every
    poll from what the terminal last said (app.py keeps it); what it does not report counts as no problem."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    cases = [({}, {}, []),
             ({'trade_allowed': False}, {}, ['algo_trading_off']),
             ({'tradeapi_disabled': True}, {}, ['python_api_disabled']),
             ({}, {'trade_allowed': False}, ['account_trade_disabled']),
             ({}, {'trade_expert': False}, ['account_expert_disabled']),
             ({'trade_allowed': None, 'tradeapi_disabled': None}, {'trade_allowed': None, 'trade_expert': None}, []),
             ({'trade_allowed': False, 'tradeapi_disabled': True}, {'trade_allowed': False, 'trade_expert': False},
              ['algo_trading_off', 'python_api_disabled', 'account_trade_disabled', 'account_expert_disabled'])]
    for term, acct, want in cases:
        bot._terminal = dict({'build': 4738, 'ping_ms': 23.5, 'trade_allowed': True, 'tradeapi_disabled': False,
                              'connected': True}, **term)
        bot._acct = dict({'login_tail': TAIL, 'server': F.ACCOUNT_SERVER, 'currency': 'USD', 'leverage': 2000,
                          'trade_allowed': True, 'trade_expert': True, 'trade_mode': 2, 'margin_mode': 2}, **acct)
        TJ.later(m, 1.0)
        tr.poll(TJ.ctx_of(m))
        assert trace_of(out)['health']['trading_not_allowed'] == want, (term, acct)
        tr.poll_skipped('positions', 'x')                               # read on a skipped poll too
        assert trace_of(out)['health']['trading_not_allowed'] == want
    bot._terminal = bot._acct = None                                    # (before the first poll guard: nothing known)
    tr.poll(TJ.ctx_of(m))
    h = trace_of(out)['health']
    assert h['trading_not_allowed'] == [] and (h['login_tail'], h['trade_mode_name']) == (None, None)
    # the other states are the handed-over dicts themselves, key for key
    view = TJ.safety_view(error='the safety state could not be saved since 14:05 UTC (PermissionError)',
                          partner={'branch': DEFAULTS['PARTNER_BRANCH'], 'account_differs': True, 'limits_differ': True})
    hold = {'why': 'refused_backoff', 'side': 'BUY', 'kind': 'entry', 'price': 1.0, 'until': START + 90, 'refusals': 12}
    tr.poll(TJ.ctx_of(m, buy_signal='BUY', _safety=view, _open_hold=hold, _foreign=foreign(2, 14.0, True)))
    s = trace_of(out)
    assert s['safety']['error'].startswith('the safety state could not be saved')
    assert s['safety']['partner']['account_differs'] is True and s['safety']['partner']['limits_differ'] is True
    assert (s['foreign']['positions'], s['foreign']['old_bot_same_terminal'], s['foreign']['old_bot_age_s']) == (2, True, 14.0)
    assert len(s['foreign']['examples']) == 1 and (s['open_hold']['why'], s['open_hold']['refusals']) == ('refused_backoff', 12)


# ───────────────────────────── an opening order held back ─────────────────────────────

@pytest.mark.parametrize('why', HOLDS)
def test_a_held_basket_entry_is_blocked_with_its_reason_not_a_failed_open(mods, tmp_path, why):
    """The strategy wants an entry, every gate of it lets it through, and the last test before the send holds it back
    (the safety, the slower retry after refusals, an unknown balance, an old bot): no order was sent. The trace says
    BLOCKED with that reason -- tested before OPEN_FAILED --, the gate that decided is the held order, the headline
    says why in the owner's words, and the trace's own check of its gates against the signal stays quiet."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    hold = {'why': why, 'side': 'BUY', 'kind': 'entry', 'price': 2000.12, 'until': START + 45.0, 'refusals': 9}
    entry = dict(buy_signal='BUY', analysis_data={'open_score': 2.0, 'fc_score': 2.0, 'entry_allowed': True})
    tr.poll(TJ.ctx_of(m, _open_hold=hold, _safety=TJ.safety_view(), **entry))
    d = trace_of(out)['decision']
    g = {x['key']: x for x in d['gates']}
    assert (d['action'], d['reason'], d['side'], d['blocked_by']) == ('BLOCKED', why, 'BUY', 'open_hold')
    assert d['orders'] == [] and d['signal'] == {'buy': 'BUY', 'sell': 'DO_NOTHING'}
    assert [x['key'] for x in d['gates']][-1] == 'open_hold'            # the last test before the send
    assert (g['open_hold']['ok'], g['open_hold']['role'], g['open_hold']['value'], g['open_hold']['checked']) == (
        False, 'need', why, True)
    assert all(g[k]['ok'] for k in ('pause', 'open_score', 'agreement', 'window', 'votes_known'))
    words = {'safety': 'the safety has blocked new trades', 'safety_checking': 'the safety is checking a change',
             'refused_backoff': 'the broker refused the last orders, so the next one is tried later (9 refusals in a '
                                'row; the next try at 2026-11-17 08:00:45 UTC)',
             'balance_unknown': 'the account balance is not known on this poll',
             'old_bot': 'an old bot is running on this server and uses the same MetaTrader 5'}[why]
    assert words in g['open_hold']['note'] and words in d['headline']
    assert d['headline'].startswith('A BUY signal stands and every check of the strategy lets it through, but no '
                                    'order is sent: ')
    # the same poll without the hold: an entry that was wanted and not sent is a failed open
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m, **entry))
    d = trace_of(out)['decision']
    assert (d['action'], d['reason']) == ('OPEN_FAILED', 'no order') and 'open_hold' not in [x['key'] for x in d['gates']]
    # a hold of another kind of order (an add) does not explain a flat poll
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m, _open_hold=dict(hold, kind='add'), **entry))
    assert trace_of(out)['decision']['action'] == 'OPEN_FAILED'
    lines = log_of(out)
    assert not [ln for ln in lines if '| WARN | TRACE |' in ln or '| ERROR |' in ln]
    assert any(f'-> BLOCKED: A BUY signal stands' in ln and f'reason={why}' in ln for ln in lines)


def test_an_order_the_safety_guard_refused_is_said_so(mods, tmp_path):
    """The last line of defence: buy() / sell() refuse to send while the bot's open guard says no, and the observer is
    told refused='safety'. The order line and the decision say 'the safety guard', not 'the account guard'."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    with bot.mt5_lock:
        tr.order(TJ.request(0), None, 'safety', None, {'bid': 2000.0, 'ask': 2000.12, 't_msc': 1})
    tr.poll(TJ.ctx_of(m, buy_signal='BUY', analysis_data={'open_score': 2.0, 'fc_score': 2.0, 'entry_allowed': True}))
    d = trace_of(out)['decision']
    assert (d['action'], d['reason']) == ('OPEN_FAILED', 'refused by the safety guard')
    assert (d['orders'][0]['refused'], d['orders'][0]['retcode'], d['orders'][0]['done']) == ('safety', None, False)
    assert 'the order was not filled (refused by the safety guard)' in d['headline']
    lines = log_of(out)
    assert any('| ORDER | ORDER | open BUY 0.01 lot at 2,000.12 sl none tp none -> not sent: the safety guard refused it'
               in ln for ln in lines)
    assert not any('account guard' in ln for ln in lines)


def _basket_in_trade(tr, tl, hold=None, signal='DO_NOTHING'):
    """The trace's decision for a BUY basket whose ladder add is due on this poll (armed, the vote turned, the price
    gap reached), without a replay."""
    ov = {'side': 'BUY', 'pnl': -1.0, 'judged_on': 'bid', 'stop_usd': 5.0, 'target_usd': 5.0, 'stop_price': 1995.0,
          'target_price': 2005.0, 'to_stop_usd': 4.0, 'to_target_usd': 6.0, 'legs': [{'id': 1}],
          'ladder': {'on': True, 'tier_tf': 'M1', 'trigger': 'macd_turn', 'vote': 1, 'add_ok': True, 'gap_px': 1.0,
                     'next_add_price': 1999.0, 'price_now': 1998.5, 'last_fill': 2000.0, 'judged_on': 'ask',
                     'tiers': ['M1'], 'count': 1, 'armed': True}}
    bk = {'open': ov, 'fc_score': 0.0, 'force_close_s': 1.0, 'force_close_enabled': False, 'open_score': 1.0,
          'ladder_s': 2.0, 'trend': {'on': False}, 'pause': {'active': False}}
    c = tl._Ctx({'_open_hold': hold, 'market_status': {}})
    G = []
    action, reason, side = tr._decide_basket(c, {'ladder_armed': True}, bk, G, True, True, signal, 'DO_NOTHING', 1, 0,
                                             False, [], START, 3)
    decided = tl._mark_checked(G)
    dec = {'action': action, 'reason': reason, 'side': side, 'blocked_by': decided, 'gates': G, 'orders': [],
           'signal': {'buy': signal, 'sell': 'DO_NOTHING'}}
    dec['headline'] = tr._headline(dec, c, {'basket': bk}, 3, START)
    return dec


def test_a_held_ladder_add_is_a_failing_gate_of_the_add(mods, tmp_path):
    """The add is due -- its trigger, its gate and its price gap all fire -- and the last test before the send holds
    it back: the strategy's BUY_MORE was taken back to DO_NOTHING. The trace says HOLD (the basket is held, exits go
    on) with one more add gate, not met, and why."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    tl = m.tracelog
    hold = {'why': 'safety', 'side': 'BUY', 'kind': 'add', 'price': 1998.5, 'until': None, 'refusals': 0}
    dec = _basket_in_trade(tr, tl, hold)
    adds = [(x['key'], x['ok'], x['checked']) for x in dec['gates'] if x['role'] == 'add']
    assert adds == [('ladder_trigger', True, True), ('ladder_gate', True, True), ('ladder_gap', True, True),
                    ('open_hold', False, True)]
    assert (dec['action'], dec['side'], dec['blocked_by']) == ('HOLD', 'BUY', None)
    assert dec['headline'].startswith('Holding the BUY basket: P/L -$1.00')
    assert dec['headline'].endswith('; an add is held back: the safety has blocked new trades (the bar at the top of '
                                    'the page says why).')
    # without the hold the same gates read as an add that is due; a hold of an entry is not this basket's
    free = _basket_in_trade(tr, tl, None)
    assert [x['key'] for x in free['gates'] if x['role'] == 'add'] == ['ladder_trigger', 'ladder_gate', 'ladder_gap']
    other = _basket_in_trade(tr, tl, dict(hold, kind='entry'))
    assert 'open_hold' not in [x['key'] for x in other['gates']]


def _turtle_in_trade(tr, tl, T, hold=None, rec=None, bs='DO_NOTHING'):
    """The trace's decision for a Turtle BUY trade of one leg whose next add level is reached on this poll."""
    now = START + 900.0
    tv = {'trade': {'stop': 59000.0, 'stop_text': '2N from the best fill', 'to_stop': 1400.0, 'next_add': 60300.0,
                    'to_next_add': -5.0}}
    st = {'closing': False, 'legs': [{'ticket': 1, 'price': 60000.0, 'time': now - 600}], 'entry_time': now - 600,
          'add_step': 300.0, 'side': 1}
    c = tl._Ctx({'exit_reason': None, 'bid': 60295.0, 'ask': 60305.0, 'pending': False, 'lvl': None, 'now': now,
                 '_open_hold': hold, '_trade_rec': rec})
    G = []
    action, reason, side = tr._turtle_decide_trade(c, tv, G, st, 1, bs, 'DO_NOTHING', [], 3,
                                                   {'max_legs': 4, 'pending_s': 10})
    tl._mark_checked(G)
    return {'action': action, 'reason': reason, 'side': side, 'gates': G}


def test_a_held_turtle_add_is_a_failing_gate_of_the_add_and_the_self_check_stays_quiet(mods, tmp_path):
    """The Turtle's add level is reached and the last test before the send holds the add back (app.py drops the
    level): no signal. With the held order as one more add gate the trace's reading of its gates is 'no add', as the
    bot did. So it is for a trade that takes no more adds because one was missed by more than an add step during a
    block (spec 5.8)."""
    m, bot, tr = TJ.tracer(mods, tmp_path, **TB.TURTLE)
    tl, T = m.tracelog, m.app.T
    hold = {'why': 'safety', 'side': 'BUY', 'kind': 'pyramid', 'price': 60305.0, 'until': None, 'refusals': 0}

    def warned(dec):
        tr._repeats.clear()
        tr._turtle_self_check(dec, 'DO_NOTHING', 'DO_NOTHING')
        tr._flush()
        lines = [ln for ln in log_of(tmp_path / 'bot_output') if "| WARN | TRACE | the trace's reading of the gates" in ln]
        return len(lines)
    dec = _turtle_in_trade(tr, tl, T, hold)
    adds = [(x['key'], x['ok']) for x in dec['gates'] if x['role'] == 'add']
    assert adds == [('legs', True), ('add_bar', True), ('add_price', True), ('open_hold', False)]
    assert dec['action'] == 'HOLD' and warned(dec) == 0
    stopped = _turtle_in_trade(tr, tl, T, None, {'adds_stopped': True})
    assert [(x['key'], x['ok']) for x in stopped['gates'] if x['role'] == 'add'][-1] == ('adds_stopped', False)
    assert stopped['action'] == 'HOLD' and warned(stopped) == 0
    # (the check itself works: the same gates without the held order read 'add', and the bot sent none)
    assert warned(_turtle_in_trade(tr, tl, T, None)) == 1


def _turtle_replay(tmp, on_bot, seconds_of_trip=None):
    out = tmp / 'bot_output'
    fake, clock = TB._market(TB._long_trip())
    vote = TB.Vote(fake, lambda t: 1)
    snaps, bots = [], []

    def on_new_bot(bot, n):
        bots.append(bot)
        sys.modules[type(bot).__module__].T.closed_bar_vote = vote
        real = bot._trace

        def spy(symbol, method, *a, **k):
            real(symbol, method, *a, **k)
            if method == 'poll':
                snaps.append(trace_of(out, symbol))
        bot._trace = spy
        on_bot(bot, fake)
    run = run_bot(fake, clock, overrides={**TB.TURTLE, 'OUTPUT_DIR': str(out)}, symbol=TB.SYMBOL,
                  state_dir=out / 'state', keep_writers=True, on_new_bot=on_new_bot)
    for bot in bots:
        for tr in list(bot._tracers.values()):
            tr._flush()
    return types.SimpleNamespace(run=run, fake=fake, out=out, snaps=snaps)


@pytest.mark.slow
def test_a_held_turtle_entry_is_a_gate_of_the_self_check_and_blocked(tmp_path):
    """The Turtle's breakout comes with the vote, and the last test before the send holds the entry back for four
    minutes: no order, the day's orders stay armed. The trace says BLOCKED with the reason and the gate that decided;
    its own check of the gates against the bot's signals stays quiet; when the hold ends the entry goes out."""
    until = START + 700.0

    def on_bot(bot, fake):
        real = bot._open_held

        def held(kind, side, price, *a, **k):
            if kind == 'entry' and fake.clock.time() < until:
                return {'why': 'safety', 'side': side, 'kind': kind, 'price': price, 'until': None, 'refusals': 0}
            return real(kind, side, price, *a, **k)
        bot._open_held = held
    r = _turtle_replay(tmp_path, on_bot)
    opens = TB._opens(r.fake)
    assert opens and until * 1000 <= opens[0]['_t_ms'] <= (until + 2) * 1000             # it went out when the hold ended
    blocked = [s for s in r.snaps if s['decision']['action'] == 'BLOCKED']
    assert len(blocked) > 100
    for s in blocked:
        d = s['decision']
        g = {x['key']: x for x in d['gates']}
        assert (d['reason'], d['side'], d['blocked_by']) == ('safety', 'BUY', 'open_hold')
        assert [x['key'] for x in d['gates']][-7:] == ['armed', 'exit_bar', 'breakout', 'vote_known', 'vote', 'brake',
                                                        'open_hold']
        assert all(g[k]['ok'] for k in ('armed', 'breakout', 'vote_known', 'vote', 'brake')) and g['open_hold']['ok'] is False
        assert s['open_hold']['why'] == 'safety' and s['open_hold']['kind'] == 'entry'
        assert 'is through the buy level' in d['headline'] and d['headline'].endswith(
            'with the vote, but no order is sent: the safety has blocked new trades (the bar at the top of the page '
            'says why).')
        assert s['turtle']['orders']['state'] == 'armed' and s['turtle']['trade'] is None
    first = next(k for k, s in enumerate(r.snaps) if s['decision']['action'] == 'BLOCKED')
    after = [s['decision']['action'] for s in r.snaps[first:]]
    assert after[len(blocked)] == 'OPEN_BUY' and set(after[:len(blocked)]) == {'BLOCKED'}
    lines = log_of(r.out, TB.SYMBOL)
    assert not [ln for ln in lines if '| WARN | TRACE |' in ln or '| ERROR |' in ln]
    assert any('-> BLOCKED: The ask ' in ln and 'reason=safety' in ln for ln in lines)
    # the minutes of the hold are in the samples, and the held order is no problem of its own in the journal
    rows = [json.loads(ln) for ln in open(r.out / 'logs' / f'{TB.SYMBOL}_{DAY}_samples.jsonl', encoding='utf-8')]
    assert sum(x['suppressed_polls'] for x in rows) == len(blocked) and rows[9]['suppressed_polls'] >= 50


@pytest.mark.slow
def test_a_held_basket_entry_in_the_bots_own_loop(tmp_path):
    """The same through the basket loop itself: app.py's last test before the send holds the first entry back for a
    minute. The trace of every such poll is BLOCKED with the reason; nothing is sent; then the entry goes out."""
    out = tmp_path / 'bot_output'
    fake, clock = market(120, seed=4)
    until = START + 60.0
    snaps, bots = [], []

    def on_new_bot(bot, n):
        bots.append(bot)
        real_held, real_trace = bot._open_held, bot._trace

        def held(kind, side, price, *a, **k):
            if kind == 'entry' and fake.clock.time() < until:
                return {'why': 'refused_backoff', 'side': side, 'kind': kind, 'price': price, 'until': until,
                        'refusals': 4}
            return real_held(kind, side, price, *a, **k)

        def spy(symbol, method, *a, **k):
            real_trace(symbol, method, *a, **k)
            if method == 'poll':
                snaps.append(trace_of(out, symbol))
        bot._open_held, bot._trace = held, spy
    run = run_bot(fake, clock, overrides={**SCALED, 'OUTPUT_DIR': str(out)}, symbol=SYMBOL, state_dir=out / 'state',
                  keep_writers=True, on_new_bot=on_new_bot)
    assert not run.errors, run.errors[:3]
    assert len(fake.orders) == 1 and until * 1000 <= fake.orders[0]['_t_ms'] <= (until + 2) * 1000
    before = [s for s in snaps if s['t'] < until]
    held = [s for s in before if s['open_hold']]
    assert len(before) >= 55 and len(held) >= 10
    for s in before:
        d = s['decision']
        assert d['orders'] == [] and not d['action'].startswith('OPEN_')
        if s['open_hold']:                  # an entry every gate of the strategy let through on this poll
            assert (d['action'], d['reason'], d['blocked_by']) == ('BLOCKED', 'refused_backoff', 'open_hold'), d['headline']
            assert s['open_hold']['refusals'] == 4
            assert '4 refusals in a row; the next try at 2026-11-17 08:01:00 UTC' in d['headline']
        else:
            assert d['reason'] != 'refused_backoff'
    assert [s['decision']['action'] for s in snaps if s['t'] >= until][0] in ('OPEN_BUY', 'OPEN_SELL')
    for bot in bots:
        for tr in list(bot._tracers.values()):
            tr._flush()
    assert not [ln for ln in log_of(out) if '| WARN | TRACE |' in ln or '| ERROR |' in ln]
    issue = [x for x in TJ.journal_of(out, 'issue') if x['code'] == 'REFUSED_BACKOFF']
    assert [x['state'] for x in issue][:1] == ['start'] and len(issue) <= 2      # one problem, not one per poll


# ───────────────────────────── the events of the real-money layer ─────────────────────────────

EVENTS = {  # event -> (level, category, what app.py gives it, a part of the line)
    'SAFETY_ERROR': ('ERROR', 'SAFETY', {'problem': 'the safety state could not be loaded (PermissionError)'},
                     'the safety check failed: the safety state could not be loaded (PermissionError). No new trade '
                     'is opened until it works again or the safety is turned OFF; open trades are still managed'),
    'SAFETY_SKIP': ('WARN', 'SAFETY', {'hold': {'why': 'safety', 'side': 'BUY', 'kind': 'entry'}},
                    'no entry order was sent (BUY): the safety has blocked new trades'),
    'SAFETY_BLOCKED': ('WARN', 'SAFETY', {'reasons': ['The account fell 20.4% below its high (limit 20%).']},
                       'the safety has blocked new trades: The account fell 20.4% below its high (limit 20%).'),
    'SAFETY_UNBLOCKED': ('INFO', 'SAFETY', {}, 'the safety block is lifted: new trades are allowed again'),
    'FOREIGN_POSITIONS': ('ERROR', 'ACCOUNT', {'text': "Trades that are not this bot's are open on XAUUSDm in this "
                                                       'account (magic 0).'},
                          "Trades that are not this bot's are open on XAUUSDm in this account (magic 0)."),
    'OLD_BOT_SAME_TERMINAL': ('ERROR', 'ACCOUNT', {'note': 'An old bot is running on this server and uses the same '
                                                           'MetaTrader 5.'}, 'An old bot is running on this server'),
    'OLD_BOT_RUNNING': ('WARN', 'ACCOUNT', {}, 'an old bot is running on this server, on another MetaTrader 5'),
    'OTHER_PROGRAM': ('ERROR', 'ACCOUNT', {'text': "another program closed this bot's trade at 14:05 UTC"},
                      "another program closed this bot's trade at 14:05 UTC"),
    'TRADING_NOT_ALLOWED': ('ERROR', 'TERMINAL', {}, 'the bot can neither open nor close'),
    'TRADING_ALLOWED': ('INFO', 'TERMINAL', {'was': ['algo_trading_off']}, 'MetaTrader 5 lets this bot trade again'),
    'STATE_OTHER_ACCOUNT': ('ERROR', 'STATE', {'note': "This bot's saved trade belongs to account ...1234."},
                            "This bot's saved trade belongs to account ...1234."),
    'LOGIN_REFUSED': ('ERROR', 'ACCOUNT', {'problem': 'The server refused account ...5678 on Fake-Real: check '
                                                      'login_id, login_pass and server.'}, 'The server refused account'),
    'LOGIN_WAIT': ('WARN', 'ACCOUNT', {}, 'MetaTrader 5 is not logged into any account'),
    'CLOSE_RESULT_UNKNOWN': ('WARN', 'CLOSE', {}, 'the result of a closed trade is not in the deal history'),
    'BUY_REFUSED': ('WARN', 'ORDER', {'retcode': 10018, 'comment': 'Market closed', 'refusals': 3},
                    "BUY entry refused by the broker: market closed (10018), the broker says 'Market closed'; 3 "
                    'refusals in a row'),
    'SELL_MORE_REFUSED': ('WARN', 'ORDER', {'note': 'no money (10019)'}, 'SELL add refused by the broker: no money (10019)'),
    'TURTLE_ADDS_STOPPED': ('WARN', 'TRADE', {}, 'this trade takes no more adds'),
    'SERVER_MISMATCH': ('ERROR', 'ACCOUNT', {'problem': 'SERVER_MISMATCH: MetaTrader 5 is logged into account ...5678 '
                                                       'on Other-Real, but mt5_credentials.json says Fake-Real. Correct '
                                                       '"server" in the "live" block and start again.'},
                        'SERVER_MISMATCH: MetaTrader 5 is logged into account ...5678 on Other-Real, but '
                        'mt5_credentials.json says Fake-Real. Correct "server" in the "live" block and start again. The '
                        'bot trades nothing on that server and never logs in over it'),
}


def test_every_event_of_the_real_money_layer_has_a_level_and_a_plain_sentence(mods, tmp_path):
    """app.py emits them through _log_event; the trace gives each a level, a category and a sentence -- app.py's own
    when it has one, else this module's. Each line carries event=<NAME> (the dashboard keys its advice on it). The
    rule that kept a demo bot off the real-money terminal is gone with its event."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    tl = m.tracelog
    assert 'LIVE_TERMINAL_PATH' not in tl.TraceLog._EVENTS and not found(json.dumps(
        [t for _, t in string_literals(ROOT / 'tracelog.py')]), 'LIVE_TERMINAL_PATH')
    named = ('SAFETY_ERROR', 'SAFETY_SKIP', 'SAFETY_BLOCKED', 'SAFETY_UNBLOCKED', 'FOREIGN_POSITIONS',
             'OLD_BOT_SAME_TERMINAL', 'OLD_BOT_RUNNING', 'OTHER_PROGRAM', 'TRADING_NOT_ALLOWED', 'STATE_OTHER_ACCOUNT',
             'LOGIN_REFUSED', 'LOGIN_WAIT', 'CLOSE_RESULT_UNKNOWN', 'BUY_REFUSED', 'SELL_REFUSED', 'BUY_MORE_REFUSED',
             'SELL_MORE_REFUSED', 'TURTLE_ADDS_STOPPED', 'SERVER_MISMATCH')
    refused = ('BUY_REFUSED', 'SELL_REFUSED', 'BUY_MORE_REFUSED', 'SELL_MORE_REFUSED')     # (_refused_words)
    for name in named + ('TRADING_ALLOWED',):        # (app.py's own: trading switched on again)
        assert tl.TraceLog._EVENTS.get(name) is not None, name
        words = tl.TraceLog._EVENT_WORDS.get(name)
        assert name in refused or words, name            # a sentence of its own, never the bare default line
        assert words is None or '{note}' not in words or name in tl.TraceLog._EVENT_DEFAULT_NOTE, name
    assert set(EVENTS) <= set(named) | {'TRADING_ALLOWED'}
    for name, (level, cat, details, part) in EVENTS.items():
        tr.event(name, 'SIGNAL', dict(details, response='never logged'))
    lines = log_of(tmp_path / 'bot_output')
    assert len(lines) == len(EVENTS)
    for ln, (name, (level, cat, details, part)) in zip(lines, EVENTS.items()):
        assert f' | {level} | {cat} | ' in ln and part in ln, (name, ln)
        assert f'event={name}' in ln.split(' | ', 4)[4] and 'never logged' not in ln
        text = ln.split(' | ', 4)[3]
        assert not any(w in text.casefold() for w in ('demo', 'virtual', 'slot', 'epoch', 'latch', 'rebase'))
    # an event this module has no name for: its name and app.py's note; an ERROR when its tag says so
    tr.event('BRAND_NEW', 'ERROR', {'note': 'something else'})
    tr.event('BRAND_NEW_TOO', 'SIGNAL', {})
    last = log_of(tmp_path / 'bot_output')[-2:]
    assert '| ERROR | EVENT | BRAND_NEW: something else | ' in last[0] and '| INFO | EVENT | BRAND_NEW_TOO | ' in last[1]


def test_the_account_is_back_and_the_terminal_in_use_lines_name_tails(mods, tmp_path):
    m, bot, tr = TJ.tracer(mods, tmp_path)
    tr.event('ACCOUNT_REFUSED', 'ERROR', {'problem': f"MetaTrader 5 is logged into account ...4321 on S, not this "
                                                     f"bot's account {TAIL} on {F.ACCOUNT_SERVER}",
                                          'own_login_tail': TAIL})
    tr.event('ACCOUNT_OK', 'SIGNAL', {'login_tail': TAIL, 'was': 'x'})
    tr.event('TERMINAL_IN_USE', 'ERROR', {'problem': 'TERMINAL_IN_USE: MetaTrader 5 at C:\\x is logged into another '
                                                     f"account (...4321 on S), not this bot's {TAIL}. It tries again "
                                                     'every 30 seconds.', 'login_tail': '...4321'})
    a, b, c = log_of(tmp_path / 'bot_output')
    assert f"| ERROR | ACCOUNT | not trading: MetaTrader 5 is logged into account ...4321 on S, not this bot's account {TAIL}" in a
    assert f"| INFO | ACCOUNT | MetaTrader 5 holds this bot's account {TAIL} again: trading | " in b
    assert ('It tries again every 30 seconds. No login: MetaTrader 5 and its account are left as they are (this line '
            'comes once for each account it holds, then at most every 15 min) | ') in c
    assert 'TERMINAL_IN_USE: TERMINAL_IN_USE' not in c


def _emitted_events(path):
    """Every event name app.py hands to _log_event / _log_limited or leaves for the events after the orders
    (_events_due): the literal names, and the f-strings of the opening orders' answers spelled out."""
    import ast
    names = set()
    for n in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', None)
        arg = None
        if fname == '_log_event' and len(n.args) > 1:
            arg = n.args[1]
        elif fname == '_log_limited' and n.args:
            arg = n.args[0]
        elif fname == 'append' and isinstance(f, ast.Attribute) and '_events_due' in ast.unparse(f.value) and n.args \
                and isinstance(n.args[0], ast.Tuple):
            arg = n.args[0].elts[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            names.add(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            tail = ''.join(v.value for v in arg.values if isinstance(v, ast.Constant))
            names.update(f'{side}{tail}' for side in ('BUY', 'SELL', 'BUY_MORE', 'SELL_MORE'))
        elif isinstance(arg, ast.IfExp):
            names.update(x.value for x in (arg.body, arg.orelse) if isinstance(x, ast.Constant))
    return names


def test_every_event_app_py_emits_has_a_level_of_its_own(mods, tmp_path):
    """No event of app.py falls to the trace's default line ('NAME: its note' at INFO / ERROR EVENT): each has its
    level and category, and a problem among them its own sentence. SERVER_MISMATCH was the one that did."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    tl = m.tracelog
    names = _emitted_events(ROOT / 'app.py')
    assert {'SERVER_MISMATCH', 'TERMINAL_IN_USE', 'LOGIN_WAIT', 'BUY_REFUSED', 'SELL_MORE_EXECUTED',
            'CLOSE_RESULT_UNKNOWN', 'TURTLE_ADDS_STOPPED', 'CLOSE_SELL'} <= names       # (the scan sees them all)
    missing = sorted(n for n in names if n not in tl.TraceLog._EVENTS and n != 'TURTLE_NOTE')
    assert not missing, missing
    problems = sorted(n for n in names if (tl.TraceLog._EVENTS.get(n) or ('', ''))[0] in ('WARN', 'ERROR'))
    unworded = [n for n in problems if n not in tl.TraceLog._EVENT_WORDS and not n.endswith('_REFUSED')
                and n not in ('ACCOUNT_REFUSED', 'TERMINAL_ERROR', 'RECONNECT_FAILED', 'LEG_CLOSED_OUTSIDE')]
    assert not unworded, unworded
    # the line of SERVER_MISMATCH as app.py makes it (initialize_mt5: _log_limited, tag ERROR, the problem named)
    tr.event('SERVER_MISMATCH', 'ERROR', {
        'problem': 'SERVER_MISMATCH: MetaTrader 5 is logged into account ...5678 on Other-Real, but mt5_credentials.json '
                   'says Fake-Real. Correct "server" in the "live" block and start again.',
        'login_tail': '...5678', 'server': 'Other-Real', 'own_login_tail': TAIL, 'own_server': F.ACCOUNT_SERVER})
    tr.event('SERVER_MISMATCH', 'ERROR', {})
    a, b = log_of(tmp_path / 'bot_output')
    assert '| ERROR | ACCOUNT | SERVER_MISMATCH: MetaTrader 5 is logged into account ...5678 on Other-Real' in a
    assert 'SERVER_MISMATCH: SERVER_MISMATCH' not in a and 'start again. The bot trades nothing on that server' in a
    assert ("| ERROR | ACCOUNT | MetaTrader 5 holds this bot's account number on another server than "
            'mt5_credentials.json names: correct "server" in the "live" block and start again. The bot trades') in b


def test_an_opening_order_without_an_answer_is_not_called_refused_by_the_broker(mods, tmp_path):
    """order_send gave no answer at all (None: a guard stopped the order before it went out, or the terminal did not
    answer): app.py logs <NAME>_REFUSED with no retcode and its note; the line says what happened -- not filled, and
    not refused by the broker. A refusal with a retcode is the broker's, as before."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    note = 'MetaTrader 5 gave no answer: the order was not sent (a guard stopped it) or the terminal did not answer'
    tr.event('BUY_REFUSED', 'ORDER', {'retcode': None, 'comment': None, 'refusals': 1, 'broker_refusals': 0,
                                      'no_answer': True, 'note': note})
    tr.event('SELL_MORE_REFUSED', 'ORDER', {'retcode': None, 'comment': None, 'refusals': 4, 'summary': True})
    tr.event('SELL_REFUSED', 'ORDER', {'retcode': 10018, 'comment': 'Market closed', 'refusals': 2})
    a, b, c = log_of(tmp_path / 'bot_output')
    assert f'| WARN | ORDER | BUY entry not filled, and not refused by the broker either: {note} | ' in a
    assert 'SELL add not filled, and not refused by the broker either: MetaTrader 5 gave no answer' in b
    assert '4 opening orders in a row were not filled' in b
    assert 'refused by the broker:' not in a.replace('not refused by the broker either:', '')
    assert 'refused by the broker:' not in b.replace('not refused by the broker either:', '')
    assert "| WARN | ORDER | SELL entry refused by the broker: market closed (10018), the broker says 'Market closed'; " \
           '2 refusals in a row | ' in c


# ───────────────────────────── the account number ─────────────────────────────

def test_only_the_tail_of_the_account_number_leaves_the_trace(mods, tmp_path):
    """Whatever the bot hands over -- a problem's text, an event's details, an example of a foreign position, a field
    of a journal line, a traceback -- the full number of the bot's own account is written as its tail: in the text
    log, the events file, the trace, the journal, the samples and the journal's state."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    n = F.ACCOUNT_LOGIN
    tr.loop_start({'state': {'basket': None, 'last_close': None}, 'sym_cfg': {}, '_rebuild_pause': True})
    tr.event('ACCOUNT_REFUSED', 'ERROR', {'problem': f'the terminal is logged into account {n}, not {n}0', 'login': n,
                                          'request': {'login': n, 'note': f'acct={n}'}})
    tr.event('OTHER_PROGRAM', 'ERROR', {'text': f'another program on account {n} closed a trade'})
    tr.log('INFO', 'TEST', f'account {n} again', kv={'login': n, 'logins': [n, 5], 'order': n + 1})
    tr.state_note('WARN', f'{n}: a state note')
    tr.boot([(m.clock.time(), 'ERROR', 'ACCOUNT', f'login failed for {n}', {'login': n}, f'Traceback\n  login={n}\n')])
    tr.journal('safety', event='trip', by=f'bot of {n}', login=n, nested={'a': [{'login': n}]})
    with bot.mt5_lock:
        tr.order(dict(TJ.request(0), comment=f'c{n}'), TJ.answer(comment=f'done {n}'), False, 1.0)
    bad = {'positions': 1, 'examples': [{'ticket': n, 'comment': f'old bot {n}'}], 'old_bot_age_s': None,
           'old_bot_same_terminal': False}
    view = TJ.safety_view(reasons=[f'Watching account {n}.'], login_tail=TAIL)
    hold = {'why': 'safety', 'side': 'BUY', 'kind': 'entry', 'price': 1.0, 'note': f'{n}'}
    tr.poll(TJ.ctx_of(m, buy_signal='BUY', _foreign=bad, _safety=view, _open_hold=hold,
                      _sizing=dict(sizing(m), note=f'account {n}')))
    TJ.later(m, 61.0)
    tr.poll(TJ.ctx_of(m))
    written = ''
    for root, _, names in os.walk(tmp_path):
        for name in names:
            with open(os.path.join(root, name), encoding='utf-8', errors='replace') as f:
                written += f.read()
    assert not found(written.replace(str(n) + '0', '').replace(str(n + 1), ''), str(n))
    assert written.count(TAIL) >= 8 and f'{n}0' in written and str(n + 1) in written    # (other numbers are left alone)
    s = trace_of(out)
    assert s['health']['own_login_tail'] == TAIL
    journal = TJ.journal_of(out)
    trip = next(x for x in journal if x['kind'] == 'safety')
    assert (trip['login'], trip['by'], trip['nested']) == (TAIL, f'bot of {TAIL}', {'a': [{'login': TAIL}]})
    # a bot whose account number is no longer than its tail cannot be told apart: nothing is rewritten for it
    bot._login = 1234
    assert tr._mask('order 1234 at 1234') == 'order 1234 at 1234'
    assert m.tracelog._login_tail(12345678) == '...5678' == m.app.safety.mask_login(12345678)
    assert m.tracelog._login_sha(12345678) == m.app.safety.login_sha(12345678)
    assert (m.tracelog._login_tail(None), m.tracelog._login_sha(None), m.tracelog._login_sha('x')) == ('...?', None, None)


def test_the_files_of_the_trace_hold_the_tail_even_of_a_text_that_names_the_full_number(mods, tmp_path):
    """The trace file copies some of the bot's own texts as they are (why the account was refused, why the last
    start or reconnect failed, a poll's problem) and the state files hold what the polls showed. Should one of them
    ever name the full number, the file still holds only its tail -- every level deep -- while the trace of a bot
    whose texts are clean is written as it is."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    n = F.ACCOUNT_LOGIN
    tr.poll(TJ.ctx_of(m))
    clean = (out / f'{SYMBOL}_trace.json').read_text(encoding='utf-8')
    assert not found(clean, str(n)) and TAIL in clean
    bot._account_bad = f'MetaTrader 5 is logged into account {n} on S'
    bot._init_problem = f'TERMINAL_IN_USE: the terminal holds {n}'
    deep = {'a': {'b': {'c': {'d': {'e': {'f': [f'account {n}', n]}}}}}}
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m, _safety=TJ.safety_view(partner=deep)))
    s = trace_of(out)
    assert s['health']['account_problem'] == f'MetaTrader 5 is logged into account {TAIL} on S'
    assert s['health']['connect_problem'] == f'TERMINAL_IN_USE: the terminal holds {TAIL}'
    assert s['safety']['partner']['a']['b']['c']['d']['e']['f'] == [f'account {TAIL}', TAIL]
    TJ.later(m, 1.0)
    tr.poll_skipped('account', f'MetaTrader 5 is logged into account {n}, not this one')
    s = trace_of(out)
    assert s['health']['account_problem'] == f'MetaTrader 5 is logged into account {TAIL}, not this one'
    assert s['decision']['headline'].startswith(f'Poll skipped, nothing decided: MetaTrader 5 is logged into '
                                                f'account {TAIL}, not this one.')
    assert s['safety']['partner']['a']['b']['c']['d']['e']['f'] == [f'account {TAIL}', TAIL]
    # the same deep inside a journal line, a log line's values and its data (the events file)
    tr.journal('safety', event='deep', deep=deep)
    tr.log('INFO', 'TEST', 'a deep value', kv={'deep': deep})
    tr._flush()
    written = ''.join(p.read_text(encoding='utf-8', errors='replace') for p in out.rglob('*') if p.is_file())
    assert not found(written, str(n))
    line = next(x for x in TJ.journal_of(out, 'safety') if x['event'] == 'deep')
    assert line['deep']['a']['b']['c']['d']['e']['f'] == [f'account {TAIL}', TAIL]
    # a value that holds itself (twice at every level) is not walked again: the copy ends at once
    loop = {'n': n}
    loop['a'], loop['b'] = loop, [loop, loop]
    copy = m.tracelog._masked(loop, n, TAIL, max_depth=64)
    assert copy['n'] == TAIL and copy['a'] is loop and copy['b'][1] is loop
    # (the bot's own texts are left as they are: the copy is the trace's)
    assert bot._account_bad.endswith(f'{n} on S')


# ───────────────────────────── the wording ─────────────────────────────

def test_no_text_of_tracelog_py_speaks_of_a_demo_account_a_virtual_balance_or_a_slot():
    """Every string of tracelog.py outside its docstrings (the fixed parts of f-strings one by one): none holds
    'demo', 'virtual' or 'slot', letter case ignored -- but for the name of the MT5 constant and the terminal's own
    word for an account kind, 'demo' (the trace reports what kind of account MetaTrader 5 holds)."""
    assert wording_offenders(ROOT / 'tracelog.py') == []
    # (the check itself sees a text of that kind)
    probe = ROOT / 'tests_demo' / 'conftest.py'
    assert wording_offenders(probe, words=('tests_demo',), allowed=())


def test_no_text_of_tracelog_py_holds_a_word_the_owner_must_not_read():
    """Rule 8: no 'epoch', 'latch', 'rebase' in a text; 'period' only as the name of the safety view's key."""
    bad = []
    for line, text in string_literals(ROOT / 'tracelog.py'):
        low = text.casefold()
        if any(w in low for w in ('epoch', 'latch', 'rebase')) or ('period' in low and text != 'period'):
            bad.append(f'{line}: {text!r}')
    assert bad == []


def test_the_owner_s_texts_of_a_real_account(mods, tmp_path):
    """What a refused account, a held order and the sizing read like on the page: 'this bot's account ...5678', the
    real balance, the share -- never a balance of the bot's own."""
    m, bot, tr = TJ.tracer(mods, tmp_path)
    out = tmp_path / 'bot_output'
    bot._account_problem()
    tr.poll(TJ.ctx_of(m, _sizing=sizing(m)))
    tr.poll_skipped('account_recheck', f"MetaTrader 5 is logged into account ...4321 on S, not this bot's account {TAIL}")
    s = trace_of(out)
    g = {x['key']: x for x in s['decision']['gates']}
    assert g['account']['name'] == "This bot's account" and g['account']['need'] == f'the real, hedging account {TAIL}'
    assert g['account_recheck']['name'] == "This bot's account, read again after the positions"
    assert g['account_recheck']['need'] == 'the same account right after the positions read'
    assert s['decision']['headline'].endswith(f"until MetaTrader 5 holds this bot's account {TAIL} again.")
    tr.poll_skipped('guard')
    TJ.later(m, 1.0)
    tr.poll(TJ.ctx_of(m, _sizing=sizing(m, 2600.0, 2), units=2))
    lines = log_of(out)
    assert any('| INFO | STATE | first poll: no basket; last close: none; unit 1 (0.5 x the account balance $1,500.00 = '
               '$750.00)' in ln for ln in lines)
    assert any('| INFO | ACCOUNT | unit 1 -> 2 (0.5 x the account balance $2,600.00 = $1,300.00)' in ln for ln in lines)
    beat = next(ln for ln in lines if '| INFO | HEARTBEAT |' in ln)
    assert ' units=1 balance=1500 equity=1500 open_pl=0 ' in beat
    text = '\n'.join(lines).casefold()
    assert not found(text, 'virtual') and not found(text, 'demo')
