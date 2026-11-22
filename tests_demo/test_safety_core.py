"""
The rules of the auto-safety (safety.py), without any file: decide(), count_trade(), note_other() and build_view()
are functions of a state and the inputs of one poll, so every rule of the spec (5.5) is tested here on plain
dicts. The file shell (Tracker) is in test_safety_files.py, the buttons (press) in test_safety_press.py.

The limits used here are test values (drop 20, day 10, 3 losing trades), not a branch's own: no value of the
deployment block of constants.py appears in this file. The branch names are made up: 'acct_x9' is a gold bot,
'acct_b9' a BTC bot (the letter after the underscore).

Run:  python3 -B -m pytest tests_demo/test_safety_core.py -q -p no:cacheprovider
"""
import builtins
import copy
import importlib.util
import json
import os
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    # safety.py is loaded by its path under a name of this file's own: the bot's module of the same name, which
    # other tests load and unload, is not touched.
    spec = importlib.util.spec_from_file_location('safety_tested_core', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()


def at(day, hh=0, mm=0, ss=0, month=11):
    return datetime(2026, month, day, hh, mm, tzinfo=timezone.utc).timestamp() + ss


T0 = at(21, 14, 5)              # 21 Nov 14:05 UTC: the time of the spec's examples
GOLD, BTC = 'acct_x9', 'acct_b9'


class Sim:
    """A bot's safety with no folder: the state, what the folder would say (`c`), and decide()."""

    def __init__(self, drop=20.0, day=10.0, streak=3, enabled=True, confirm_s=3.0, cash_wait_s=60.0):
        self.limits = S.Limits(drop, day, streak)
        self.state = S.new_state(GOLD)
        self.c = {'restart_status': 'missing', 'restart_id': None, 'restart_scope': None,
                  'restart_account_id': None, 'enabled': enabled, 'block_id': None, 'block_exists': None}
        self.confirm_s, self.cash_wait_s = confirm_s, cash_wait_s
        self.out, self.events = None, []

    def poll(self, t, balance, cash=None, read_at=None, waiting=0):
        self.state, self.out = S.decide(self.state, self.limits, t, balance, cash, read_at, waiting, self.c,
                                        self.confirm_s, self.cash_wait_s)
        self.events += self.out['events']
        return self.out

    def start(self, t, balance):
        """The first poll with a balance, and the first cash read after it (nothing in the history)."""
        self.poll(t, balance)
        return self.poll(t + 1, balance, [], t + 0.5)

    def settle(self, t, balance, cash=()):
        """The balance is seen changed at t; the read made 3.5 s later confirms it at t + 4."""
        self.poll(t, balance)
        return self.poll(t + 4, balance, list(cash), t + 3.5)

    def pressed(self, new_id, scope='account', account_id=None):
        """What the folder says after a press wrote a new id."""
        if account_id is None:
            account_id = new_id if scope == 'account' else self.c['restart_account_id'] or S.FIRST_ID
        self.c.update(restart_status='ok', restart_id=new_id, restart_scope=scope, restart_account_id=account_id)

    def closed(self, t, key, pl):
        self.state, ev = S.count_trade(self.state, self.limits, t, key, pl, self.c['enabled'])
        self.events += ev
        return ev

    def view(self, t, **facts):
        base = {'enabled': self.c['enabled'], 'login_tail': '...1234', 'branch': GOLD, 'partner_branch': BTC,
                'account_blocked': S.account_blocked(self.state, self.c)}
        if self.out is not None:
            base.update({k: self.out[k] for k in ('hold', 'hold_why', 'hold_since', 'pending', 'waiting')})
            own = self.state.get('account_block')
            if own:
                base['block'] = dict(own, branch=GOLD)
        base.update(facts)
        return S.build_view(self.state, self.limits, t, base)

    def drop_pct(self):
        return S._pct_below(self.state['peak'], self.state['settled_balance'])

    def day_pct(self):
        return S._pct_below(self.state['day0'], self.state['settled_balance'])


def deal(ticket, amount, when):
    return {'ticket': ticket, 'amount': amount, 'time': when}


def names(events):
    return [(e['event'], e.get('scope')) for e in events]


# ───────────────────────────── every rule at, just below and just above its limit ─────────────────────────────

@pytest.mark.parametrize('high, balance, limit, trips', [
    (1500.00, 1200.01, 20.0, False),          # 19.9993 %: just below
    (1500.00, 1200.00, 20.0, True),           # exactly 20 %: at the limit the rule is met
    (1500.00, 1199.99, 20.0, True),           # just above
    (12094.30, 10884.88, 10.0, False),
    (12094.30, 10884.87, 10.0, True),         # exactly 10 %, but floating point says 9.999999999999988
    (12094.30, 10884.86, 10.0, True),
    (1500.00, 1312.50, 12.5, True),
    (1500.00, 1312.51, 12.5, False),
])
def test_the_drop_rule_at_just_below_and_just_above_its_limit(high, balance, limit, trips):
    sim = Sim(drop=limit, day=None, streak=None)
    sim.start(T0, high)
    out = sim.settle(T0 + 10, balance)
    assert out['tripped'] is trips and out['account_blocked'] is trips
    if trips:
        blk = sim.state['account_block']
        assert blk['rules'] == ['DROP'] and blk['period'] == 'start' and blk['at'] == T0 + 14
        assert blk['numbers']['balance'] == balance and blk['numbers']['peak'] == high
        assert blk['numbers']['drop_limit'] == limit
    else:
        assert sim.state['account_block'] is None


@pytest.mark.parametrize('day_start, balance, limit, trips', [
    (1500.00, 1350.01, 10.0, False),
    (1500.00, 1350.00, 10.0, True),
    (1500.00, 1349.99, 10.0, True),
    (12094.30, 10884.88, 10.0, False),
    (12094.30, 10884.87, 10.0, True),         # the 9.999999999999988 case, on the day rule
    (2000.00, 1750.00, 12.5, True),
    (2000.00, 1750.01, 12.5, False),
])
def test_the_day_rule_at_just_below_and_just_above_its_limit(day_start, balance, limit, trips):
    sim = Sim(drop=None, day=limit, streak=None)
    sim.start(T0, day_start)
    out = sim.settle(T0 + 10, balance)
    assert out['tripped'] is trips
    if trips:
        assert sim.state['account_block']['rules'] == ['DAY']
        assert sim.state['account_block']['numbers']['day'] == '2026-11-21'


def test_the_float_case_is_a_real_one():
    """The pair the design review found: an exact 10 % loss that floating point puts just under 10."""
    raw = (12094.30 - 10884.87) / 12094.30 * 100.0
    assert raw < 10.0 and round(raw, 6) == 10.0
    assert Fraction(1209430 - 1088487, 1209430) * 100 == 10          # (exact, in cents)
    assert S._met(raw, 10.0) and not S._met(9.999998, 10.0)


def test_many_balances_exactly_at_a_limit_all_trip_and_one_cent_above_never_does():
    """Balances in whole cents that are exactly `limit` percent below the high, for a range of limits: every one
    must trip, the balance one cent higher must not. A plain `pct >= limit` misses about a third."""
    missed_by_plain_compare = 0
    checked = 0
    for limit in (10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 35.0):
        for high_cents in range(150000, 1500000, 280):         # $1,500.00 to $15,000.00 in steps of $2.80
            exact = Fraction(high_cents) * (100 - Fraction(limit)) / 100
            if exact.denominator != 1:
                continue                                   # (no whole-cent balance is exactly at the limit)
            high, at_limit = high_cents / 100.0, int(exact) / 100.0
            if (high - at_limit) / high * 100.0 < limit:
                missed_by_plain_compare += 1
            state = dict(S.new_state(GOLD), period='start', peak=high, day0=high, settled_balance=at_limit,
                         day='2026-11-21')
            lim = S.Limits(limit, limit, None)
            assert S._account_trip(state, lim, T0)['rules'] == ['DROP', 'DAY'], (limit, high, at_limit)
            state['settled_balance'] = (int(exact) + 1) / 100.0
            assert S._account_trip(state, lim, T0) is None, (limit, high, at_limit)
            checked += 1
    assert checked > 30000 and missed_by_plain_compare > 3000


@pytest.mark.parametrize('losses, blocked', [(2, False), (3, True), (4, True)])
def test_the_losing_trades_rule_at_just_below_and_just_above_its_limit(losses, blocked):
    sim = Sim(streak=3)
    sim.start(T0, 1500.0)
    for i in range(losses):
        sim.closed(T0 + 10 + i, f'trade-{i}', -1.0)
    assert sim.state['streak'] == losses
    assert (sim.state['bot_block'] is not None) is blocked
    if blocked:
        blk = sim.state['bot_block']
        assert blk['rule'] == 'STREAK' and blk['count'] == 3 and blk['limit'] == 3 and blk['at'] == T0 + 12
        assert blk['text'] == 'it lost 3 trades in a row (limit 3)'


def test_a_limit_of_one_losing_trade_says_one_trade():
    sim = Sim(streak=1)
    sim.start(T0, 1500.0)
    sim.closed(T0 + 10, 'trade-0', -1.0)
    assert sim.state['bot_block']['text'] == 'it lost 1 trade in a row (limit 1)'


@pytest.mark.parametrize('off', [None, 0, 0.0])
def test_a_rule_whose_limit_is_none_or_zero_is_off(off):
    sim = Sim(drop=off, day=off, streak=off)
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 10, 300.0)                         # 80 % down in one day
    for i in range(20):
        sim.closed(T0 + 20 + i, f'k{i}', -5.0)
    out = sim.poll(T0 + 60, 300.0, waiting=5)
    assert not out['tripped'] and not out['account_blocked'] and not out['hold']
    assert sim.state['bot_block'] is None and sim.state['streak'] == 20
    assert sim.limits.as_dict() == {'drop_pct': None, 'day_pct': None, 'streak_n': None}


def test_limits_refuse_what_is_not_a_limit():
    assert S.Limits(20, 12.5, 5).as_dict() == {'drop_pct': 20.0, 'day_pct': 12.5, 'streak_n': 5}
    assert S.Limits(streak_n=5.0).streak_n == 5
    for bad in ({'drop_pct': 'twenty'}, {'day_pct': -1}, {'streak_n': 2.5}, {'streak_n': True},
                {'drop_pct': float('nan')}, {'day_pct': float('inf')}, {'streak_n': -3}):
        with pytest.raises(ValueError):
            S.Limits(**bad)
    assert S.Limits(20, 10, 3) == S.Limits(20.0, 10.0, 3) and S.Limits(20, 10, 3) != S.Limits(20, 10, 4)


# ───────────────────────────── the first start and the fresh starts ─────────────────────────────

def test_the_first_start_is_taken_on_the_first_poll_that_has_a_balance():
    sim = Sim()
    out = sim.poll(T0, None)                                 # the terminal has no balance yet
    assert sim.state['period'] == 'start' and sim.state['fresh_pending'] is True
    assert sim.state['peak'] is None and not out['pending'] and not out['hold'] and not out['account_blocked']
    v = sim.view(T0)
    assert v['drop'] == {'pct': 0.0, 'limit': 20.0, 'peak': None, 'peak_at': None, 'balance': None}
    assert v['started_at'] is None and v['blocked'] is False

    out = sim.poll(T0 + 5, 1500.0)
    s = sim.state
    assert s['peak'] == s['day0'] == s['settled_balance'] == s['day_start_balance'] == 1500.0
    assert s['started_at'] == s['peak_at'] == s['day0_at'] == s['settled_at'] == s['day_start_at'] == T0 + 5
    assert s['day'] == '2026-11-21' and s['day_since'] == 'restart' and s['fresh_pending'] is False
    assert s['streak'] == 0 and s['bot_block'] is None and s['account_block'] is None
    assert s['cash_seen'] == {} and s['cash_baseline_done'] is False
    assert names(sim.events) == [('fresh_start', 'first')] and sim.events[0]['balance'] == 1500.0


def test_the_first_start_takes_the_id_of_the_restart_file_when_there_is_one():
    sim = Sim()
    sim.pressed('20261120_101500-a1b2c3')
    sim.poll(T0, 1500.0)
    assert sim.state['period'] == '20261120_101500-a1b2c3'
    assert sim.state['account_period'] == '20261120_101500-a1b2c3'
    assert names(sim.events) == [('fresh_start', 'first')]


def _a_bot_in_trouble(sim):
    """High 1700 after a deposit, 5 % below it, 2 losing trades in a row, a further change still being checked."""
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1700.0, [deal(7, 200.0, T0 + 9)])            # a deposit: the high is 1700 now
    sim.settle(T0 + 20, 1615.0)                                      # a loss of 5 %
    sim.closed(T0 + 21, 'a', -40.0)
    sim.closed(T0 + 22, 'b', -45.0)
    sim.poll(T0 + 30, 1460.0)                                        # a further change, not judged yet
    assert sim.state['change_first'] == T0 + 30 and sim.state['streak'] == 2
    assert sim.state['cash_seen'] == {'7': T0 + 9} and sim.state['cash_baseline_done'] is True
    assert sim.state['account_block'] is None and sim.state['peak'] == 1700.0


def test_a_fresh_start_of_the_account_counts_everything_again_from_the_balance_of_now():
    sim = Sim()
    _a_bot_in_trouble(sim)
    day_start = (sim.state['day_start_balance'], sim.state['day_start_at'])
    assert day_start == (1700.0, T0)                                 # (1500 at the start + the 200 paid in)
    sim.closed(T0 + 31, 'c', -1.0)                                   # the third loss: this bot is blocked
    assert sim.state['bot_block'] is not None
    sim.pressed('20261121_141000-aaaaaa')
    out = sim.poll(T0 + 40, 1460.0)
    s = sim.state
    assert s['period'] == '20261121_141000-aaaaaa' and s['account_period'] == s['period']
    assert s['streak'] == 0 and s['bot_block'] is None and s['account_block'] is None
    assert s['peak'] == s['day0'] == s['settled_balance'] == 1460.0
    assert s['started_at'] == s['peak_at'] == s['day0_at'] == s['settled_at'] == T0 + 40
    assert s['day'] == '2026-11-21' and s['day_since'] == 'restart'
    assert s['cash_seen'] == {} and s['cash_baseline_done'] is False and s['cash_read_ok_at'] is None
    assert s['change_first'] is None and s['change_last'] is None            # the unsettled change is forgotten
    assert (s['day_start_balance'], s['day_start_at']) == day_start          # NOT touched by a fresh start
    assert not out['pending'] and not out['hold'] and not out['account_blocked']
    assert names(out['events']) == [('fresh_start', 'account')]
    # the closed trades it has counted are still known: a close reported twice is not counted again
    assert sim.closed(T0 + 41, 'c', -1.0) == [] and s['streak'] == 0


def test_a_fresh_start_of_a_bot_only_sets_a_blocked_bots_count_back():
    sim = Sim()
    _a_bot_in_trouble(sim)
    sim.closed(T0 + 31, 'c', -1.0)
    before = copy.deepcopy(sim.state)
    assert before['bot_block']['rule'] == 'STREAK'
    sim.pressed('20261121_141000-bbbbbb', scope='bot')
    out = sim.poll(T0 + 40, 1460.0)
    s = sim.state
    assert s['period'] == '20261121_141000-bbbbbb' and s['streak'] == 0 and s['bot_block'] is None
    assert s['account_period'] == before['account_period'] == 'start'
    for key in ('peak', 'peak_at', 'day', 'day0', 'day0_at', 'day_since', 'day_start_balance', 'day_start_at',
                'settled_balance', 'settled_at', 'started_at', 'cash_seen', 'cash_baseline_done',
                'change_first', 'change_last', 'counted_trades'):
        assert s[key] == before[key], key
    assert out['pending'] is True                                    # the change is still being checked
    assert names(out['events']) == [('fresh_start', 'bot')]


def test_a_fresh_start_of_a_bot_changes_nothing_in_a_bot_that_is_not_blocked():
    sim = Sim()
    _a_bot_in_trouble(sim)                                           # 2 losses in a row, not blocked
    before = copy.deepcopy(sim.state)
    sim.pressed('20261121_141000-cccccc', scope='bot')
    sim.poll(T0 + 30, 1460.0)
    after = dict(sim.state)
    assert after.pop('period') == '20261121_141000-cccccc'
    before.pop('period')
    assert after == before and after['streak'] == 2                  # its count of losing trades stays


def test_a_fresh_start_that_waits_for_a_balance():
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 10, 1190.0)                                # 20.67 % down: blocked
    assert out['account_blocked']
    sim.pressed('20261121_141000-dddddd')
    out = sim.poll(T0 + 40, None)                                    # the press is seen, the balance is not known
    s = sim.state
    assert s['period'] == '20261121_141000-dddddd' and s['fresh_pending'] is True
    assert s['account_block'] is None and not out['account_blocked']         # the block is of the old id
    assert s['peak'] == 1500.0                                       # (figures of before, until a balance comes)
    v = sim.view(T0 + 40)
    assert v['drop']['pct'] == 0.0 and v['drop']['peak'] is None and v['blocked'] is False
    assert out['events'] == []
    out = sim.poll(T0 + 55, 1185.0)
    assert sim.state['peak'] == sim.state['day0'] == 1185.0 and sim.state['started_at'] == T0 + 55
    assert sim.state['fresh_pending'] is False and names(out['events']) == [('fresh_start', 'account')]


@pytest.mark.parametrize('status', ['missing', None, 'unreadable'])
def test_a_restart_file_that_is_missing_or_cannot_be_read_never_starts_afresh(status):
    sim = Sim()
    sim.pressed('20261121_100000-eeeeee')
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 10, 1190.0)
    assert out['account_blocked'] and sim.state['period'] == '20261121_100000-eeeeee'
    sim.c.update(restart_status=status, restart_id='start' if status == 'missing' else None)
    out = sim.poll(T0 + 30, 1190.0)
    assert sim.state['period'] == '20261121_100000-eeeeee' and out['account_blocked']        # the block stays
    assert sim.state['peak'] == 1500.0


def test_a_bot_that_missed_an_unblock_of_the_account_takes_it_even_when_the_newest_press_is_for_a_bot():
    """The gold bot is stopped while the account is blocked. The owner unblocks the account, later he unblocks the
    BTC bot. When the gold bot starts, the restart file says 'bot': by the id of the last account start in it the
    gold bot sees it has not taken that one, and starts afresh. Otherwise it would block the account again at once
    against the old high."""
    sim = Sim()
    sim.start(T0, 1500.0)
    assert sim.settle(T0 + 10, 1190.0)['account_blocked']
    sim.pressed('20261121_150000-222222', scope='bot', account_id='20261121_143000-111111')
    out = sim.poll(T0 + 7200, 1190.0)
    s = sim.state
    assert s['period'] == '20261121_150000-222222' and s['account_period'] == '20261121_143000-111111'
    assert s['peak'] == s['day0'] == 1190.0 and s['account_block'] is None and not out['account_blocked']
    assert names(out['events']) == [('fresh_start', 'account')]
    # a later unblock of one bot is then only that
    sim.pressed('20261121_160000-333333', scope='bot', account_id='20261121_143000-111111')
    sim.settle(T0 + 7300, 1100.0)
    assert sim.state['period'] == '20261121_160000-333333' and sim.state['peak'] == 1190.0


def test_an_account_limit_met_in_the_same_instant_as_an_unblock_of_one_bot_is_not_lost():
    """press('unblock') found no block file and wrote an id for one bot; in the same instant this bot met the drop
    limit under the old id. The figures did not change, so the rule is judged again under the new id."""
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 10, 1190.0)
    assert out['tripped'] and sim.state['account_block']['period'] == 'start'
    sim.pressed('20261121_140520-444444', scope='bot')               # (account_id stays 'start')
    out = sim.poll(T0 + 16, 1190.0)
    assert sim.state['period'] == '20261121_140520-444444'
    assert out['tripped'] and out['account_blocked']
    assert sim.state['account_block']['period'] == '20261121_140520-444444'
    assert sim.state['account_block']['rules'] == ['DROP', 'DAY'] and sim.state['peak'] == 1500.0


# ───────────────────────────── the settle rule ─────────────────────────────

def test_a_loss_settles_once_the_cash_history_was_read_three_seconds_after_it():
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.poll(T0 + 10, 1450.0)
    assert out['pending'] and not out['settled'] and sim.state['settled_balance'] == 1500.0
    assert (sim.state['change_first'], sim.state['change_last']) == (T0 + 10, T0 + 10)
    out = sim.poll(T0 + 11, 1450.0, [], T0 + 10.2)                   # a read 0.2 s after the change: too early
    assert out['pending'] and not out['settled']
    out = sim.poll(T0 + 13, 1450.0, [], T0 + 12.99)                  # 2.99 s: still too early
    assert out['pending'] and not out['settled']
    out = sim.poll(T0 + 14, 1450.0, [], T0 + 13.0)                   # 3.0 s after the balance last moved
    assert out['settled'] and not out['pending'] and not out['tripped']
    s = sim.state
    assert s['settled_balance'] == 1450.0 and s['settled_at'] == T0 + 14 and s['peak'] == 1500.0
    assert s['change_first'] is None and round(sim.drop_pct(), 4) == 3.3333


def test_a_poll_without_a_read_does_not_settle_and_a_read_without_its_time_is_no_read():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.poll(T0 + 10, 1450.0)
    assert not sim.poll(T0 + 20, 1450.0)['settled']                  # no read since the last poll
    assert not sim.poll(T0 + 21, 1450.0, [], None)['settled']        # deals without the time they were read at
    assert not sim.poll(T0 + 22, 1450.0, None, T0 + 21.5)['settled']    # a read that failed (None)
    assert sim.poll(T0 + 23, 1450.0, [], T0 + 22.5)['settled']


def test_the_wait_starts_again_when_the_balance_moves_again():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.poll(T0 + 10, 1450.0)
    out = sim.poll(T0 + 12, 1430.0, [], T0 + 11.5)                   # a second leg closed: the balance moved again
    assert (sim.state['change_first'], sim.state['change_last']) == (T0 + 10, T0 + 12) and out['pending']
    assert not sim.poll(T0 + 14, 1430.0, [], T0 + 13.5)['settled']   # 3.5 s after the first move, 1.5 after the last
    assert sim.poll(T0 + 16, 1430.0, [], T0 + 15.0)['settled']
    assert sim.state['settled_balance'] == 1430.0


def test_a_clock_that_is_set_back_or_a_read_stamped_in_the_future_does_not_settle_early():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.poll(T0 + 100, 1450.0)
    out = sim.poll(T0 + 40, 1450.0, [], T0 + 39.5)                   # the server's clock went back a minute
    assert (sim.state['change_first'], sim.state['change_last']) == (T0 + 40, T0 + 40) and not out['settled']
    assert not sim.poll(T0 + 42, 1450.0, [], T0 + 41.5)['settled']
    assert sim.poll(T0 + 44, 1450.0, [], T0 + 43.5)['settled']
    # a read stamped later than the poll that gets it counts as made at that poll
    sim.poll(T0 + 200, 1400.0)
    out = sim.poll(T0 + 201, 1400.0, [], T0 + 900)
    assert not out['settled'] and sim.state['cash_read_ok_at'] == T0 + 201
    assert sim.poll(T0 + 204, 1400.0, [], T0 + 900)['settled']


def test_a_fall_with_failing_reads_settles_after_a_minute_as_a_loss():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.poll(T0 + 10, 1100.0)                                        # (in truth a withdrawal of 400)
    out = sim.poll(T0 + 69.9, 1100.0)                                # every read failed: 59.9 s
    assert out['pending'] and out['hold'] and not out['settled'] and not out['account_blocked']
    out = sim.poll(T0 + 70, 1100.0)                                  # 60 s: taken as a loss
    assert out['settled'] and out['tripped'] and sim.state['account_block']['rules'] == ['DROP', 'DAY']
    assert sim.state['peak'] == 1500.0 and sim.state['settled_balance'] == 1100.0
    # its history line arrives after that: it is inside a balance already judged, so it is only remembered
    out = sim.settle(T0 + 300, 1090.0, [deal(31, -400.0, T0 + 9.5)])
    assert sim.state['peak'] == 1500.0 and sim.state['cash_seen'] == {'31': T0 + 9.5}
    assert [e['counted'] for e in out['events'] if e['event'] == 'cash'] == [False]


def test_the_minute_counts_only_while_the_bot_was_looking():
    """The bot dies two seconds after the balance fell (a withdrawal) and starts again ten minutes later. The fall
    is older than a minute, but this process has not yet tried the history once: it must not be taken as a loss
    by the first poll."""
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.poll(T0 + 10, 1000.0)
    sim.poll(T0 + 12, 1000.0)                                        # ...and the process ends here
    sim.c['watching_since'] = T0 + 600                               # the new process
    out = sim.poll(T0 + 601, 1000.0)
    assert out['pending'] and out['hold'] and not out['settled'] and not out['account_blocked']
    out = sim.poll(T0 + 602, 1000.0, [deal(77, -500.0, T0 + 9.5)], T0 + 601.5)
    assert out['settled'] and not out['tripped'] and sim.state['peak'] == 1000.0     # a withdrawal, as the history says
    # and when the history cannot be read after the restart either: a loss, a minute after the restart
    other = Sim()
    other.start(T0, 1500.0)
    other.poll(T0 + 10, 1000.0)
    other.c['watching_since'] = T0 + 600
    assert not other.poll(T0 + 659.9, 1000.0)['settled']
    assert other.poll(T0 + 660, 1000.0)['tripped']


def test_a_rise_waits_for_a_read_however_long_it_takes():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1400.0)
    sim.poll(T0 + 20, 1900.0)                                        # a deposit, or a profit: only the history tells
    for dt in (60, 600, 6000):
        out = sim.poll(T0 + 20 + dt, 1900.0)
        assert out['pending'] and not out['settled'] and not out['hold']
        assert sim.state['peak'] == 1500.0 and sim.state['settled_balance'] == 1400.0    # the high is not raised
    out = sim.poll(T0 + 7000, 1900.0, [deal(41, 500.0, T0 + 19)], T0 + 6999)
    assert out['settled'] and round(sim.state['peak'], 6) == round(1500.0 * 1900 / 1400, 6)
    assert round(sim.drop_pct(), 6) == round(100.0 / 1500 * 100, 6)  # still 6.67 % down, as before the deposit


def test_a_withdrawal_whose_history_line_arrives_two_seconds_late_is_not_a_loss():
    sim = Sim()
    sim.start(T0, 1500.0)
    t = T0 + 100
    out = sim.poll(t, 1000.0)                                        # 500 withdrawn: 33 % "down"
    assert out['hold'] and out['hold_why'] == 'limit' and out['hold_since'] == t
    assert sim.poll(t + 1, 1000.0, [], t + 0.1)['hold']              # the history does not have it yet
    assert sim.poll(t + 2, 1000.0, [], t + 1.1)['hold']
    late = [deal(51, -500.0, t - 0.4)]
    out = sim.poll(t + 3, 1000.0, late, t + 2.1)                     # there it is, but 2.1 s is not 3 s
    assert out['hold'] and not out['settled'] and sim.state['peak'] == 1500.0
    out = sim.poll(t + 4, 1000.0, late, t + 3.1)
    assert out['settled'] and not out['tripped'] and not out['hold'] and not out['account_blocked']
    s = sim.state
    assert s['peak'] == s['day0'] == 1000.0 and s['day_start_balance'] == 1000.0 and s['day_cash'] == -500.0
    assert sim.drop_pct() == 0.0 and sim.day_pct() == 0.0
    cash = [e for e in out['events'] if e['event'] == 'cash']
    assert cash == [{'event': 'cash', 'ticket': '51', 'amount': -500.0, 'time': t - 0.4, 'counted': True,
                     'found_after_s': 3.1, 'at': t + 4}]


def test_a_deposit_is_not_counted_twice():
    sim = Sim()
    sim.start(T0, 1500.0)
    t = T0 + 100
    sim.poll(t, 2000.0)
    assert sim.state['peak'] == 1500.0
    for dt in (1, 2, 3, 20):                                         # the history read fails for 20 s
        out = sim.poll(t + dt, 2000.0)
        assert out['pending'] and sim.state['peak'] == 1500.0        # the high is not lifted meanwhile
    dep = [deal(61, 500.0, t - 0.3)]
    out = sim.poll(t + 25, 2000.0, dep, t + 24.5)
    assert out['settled'] and sim.state['peak'] == sim.state['day0'] == 2000.0       # not 2500
    assert not out['account_blocked'] and sim.drop_pct() == 0.0
    # the same line in every later read changes nothing
    out = sim.settle(t + 60, 1990.0, dep)
    assert sim.state['peak'] == 2000.0 and [e for e in out['events'] if e['event'] == 'cash'] == []


def test_a_deposit_found_only_after_its_balance_was_judged_is_not_added_on_top():
    """The history was more than 3 s behind: the rise was judged as a profit (the high went up to the balance).
    When the deposit's line shows up later it must not scale the high again: 1500 -> 2000 would become 2667,
    a 25 % 'drop' out of nothing."""
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 100, 2000.0)                               # the read 3.5 s later still has no line
    assert out['settled'] and sim.state['peak'] == 2000.0
    out = sim.settle(T0 + 500, 1990.0, [deal(71, 500.0, T0 + 99.7)])
    assert sim.state['peak'] == 2000.0 and not out['account_blocked']
    assert [e['counted'] for e in out['events'] if e['event'] == 'cash'] == [False]


def test_the_hold_while_an_unsettled_balance_would_meet_a_limit():
    sim = Sim(drop=20.0, day=10.0)
    sim.start(T0, 1500.0)
    out = sim.poll(T0 + 10, 1351.0)                                  # 9.93 %: no limit would be met
    assert out['pending'] and not out['hold']
    out = sim.poll(T0 + 11, 1350.0)                                  # exactly 10 % of the day: held
    assert out['pending'] and out['hold'] and out['hold_why'] == 'limit' and out['hold_since'] == T0 + 10
    assert not out['account_blocked'] and sim.state['account_block'] is None
    v = sim.view(T0 + 11)
    assert v['hold'] is True and v['blocked'] is False and v['pending'] is True and v['state'] == 'checking'
    assert v['since'] == T0 + 10
    assert v['drop']['pct'] == 0.0 and v['drop']['balance'] == 1500.0       # the meters keep the judged balance
    out = sim.poll(T0 + 15, 1350.0, [], T0 + 14.5)                   # it was a loss: the hold becomes the block
    assert out['tripped'] and out['account_blocked'] and not out['hold'] and not out['pending']


def test_the_hold_ends_by_itself_when_the_balance_comes_back():
    sim = Sim()
    sim.start(T0, 1500.0)
    assert sim.poll(T0 + 10, 1000.0)['hold']
    out = sim.poll(T0 + 11, 1500.0)                                  # (a transfer out and back)
    assert not out['hold'] and not out['pending'] and sim.state['change_first'] is None
    assert sim.state['settled_balance'] == 1500.0 and sim.state['settled_at'] == T0


def test_a_day_loss_first_seen_at_23_59_58_is_judged_against_the_old_day():
    sim = Sim(drop=None, day=10.0)
    sim.start(at(21, 9), 1500.0)
    out = sim.poll(at(21, 23, 59, 58), 1340.0)                       # 10.67 % of the day
    assert out['hold'] and sim.state['day'] == '2026-11-21'
    out = sim.poll(at(22, 0, 0, 0), 1340.0, [], at(21, 23, 59, 59))  # the new day; the read is 1 s old
    assert out['hold'] and out['pending'] and sim.state['day'] == '2026-11-21'       # the old day is not closed yet
    out = sim.poll(at(22, 0, 0, 2), 1340.0, [], at(22, 0, 0, 1))
    assert out['settled'] and out['tripped']
    blk = sim.state['account_block']
    assert blk['rules'] == ['DAY'] and blk['numbers']['day'] == '2026-11-21' and blk['numbers']['day0'] == 1500.0
    assert round(blk['numbers']['day_pct'], 2) == 10.67
    # and then the new day starts from the balance of now
    s = sim.state
    assert s['day'] == '2026-11-22' and s['day0'] == s['day_start_balance'] == 1340.0
    assert s['day0_at'] == s['day_start_at'] == at(22, 0, 0, 2) and s['day_since'] == 'midnight'


# ───────────────────────────── deposits and withdrawals ─────────────────────────────

def test_a_deposit_dated_before_the_first_start_changes_nothing():
    """The account was funded an hour before the bot's first start: that money is the starting balance. A bot that
    added it to the high would be 50 % 'down' and blocked at its first poll."""
    sim = Sim()
    sim.poll(T0, 1500.0)
    funded = [deal(1, 1500.0, T0 - 3600), deal(2, -20.0, T0 - 1800), deal(3, 20.0, T0 - 60)]
    out = sim.poll(T0 + 1, 1500.0, funded, T0 + 0.5)
    s = sim.state
    assert s['cash_baseline_done'] is True and s['cash_seen'] == {'1': T0 - 3600, '2': T0 - 1800, '3': T0 - 60}
    assert s['peak'] == s['day0'] == s['day_start_balance'] == 1500.0 and s['day_cash'] == 0.0
    assert not out['account_blocked'] and not out['hold'] and not out['pending']
    assert [e['event'] for e in out['events']] == ['cash_start']
    out = sim.settle(T0 + 100, 1490.0, funded)                       # they stay unseen-proof ever after
    assert sim.state['peak'] == 1500.0 and [e for e in out['events'] if e['event'] == 'cash'] == []


def _first_reads(amount, failing, later_loss=0.0, dated=-0.5):
    """A fresh start at T0 on $1,500, polled once a second; the owner's deposit or withdrawal lands 3 s after it (its
    history line dated `dated` s from the poll that sees it); the first reads of the cash history fail for 6 s when
    `failing`; `later_loss` is lost at 14 s. Each read is made at the end of a poll and handed to the next."""
    sim = Sim(drop=20.0, day=12.5, streak=None)
    t, bal, history, read = T0, 1500.0, [], (None, None)
    for i in range(20):
        if i == 3 and amount:
            bal += amount
            history.append(deal(5001, amount, t + dated))
        if i == 14 and later_loss:
            bal -= later_loss
        sim.poll(t, bal, *read)
        read = (None, None) if (failing and i < 6) else (list(history), t + 0.2)
        t += 1
    return sim


@pytest.mark.parametrize('amount, later_loss', [(-400.0, 0.0), (1500.0, 600.0), (300.0, 0.0)])
def test_an_operation_made_after_a_fresh_start_while_its_first_reads_fail_is_scaled_as_if_they_had_worked(
        amount, later_loss):
    """The first read that works after a fresh start takes what it returns up to the start (2 s later at most) as
    inside the starting balance. The reads fail for the first seconds, and the owner withdraws (or pays in) 3 s after
    the start: that operation is scaled when its change settles, exactly as with reads that work -- no false 26.7 %
    block for a $400 withdrawal, and after a deposit the day counts from the money that is there."""
    good, late = _first_reads(amount, False, later_loss), _first_reads(amount, True, later_loss)
    keys = ('peak', 'day0', 'day_start_balance', 'settled_balance', 'account_block', 'day_cash')
    assert {k: late.state[k] for k in keys} == {k: good.state[k] for k in keys}
    assert '5001' in late.state['cash_seen']
    if amount == -400.0:
        assert late.state['account_block'] is None and late.drop_pct() == 0.0 and late.state['peak'] == 1100.0
    if amount == 1500.0:
        assert late.state['day0'] == 3000.0 and round(late.day_pct(), 6) == 20.0          # (not 0 % against 1500)
    start = [e for e in late.events if e['event'] == 'cash_start']
    assert len(start) == 1 and (start[0]['tickets'], start[0]['later']) == (0, 1)


def test_an_operation_dated_up_to_two_seconds_after_the_start_is_inside_its_starting_balance():
    """The history's clock and the bot's differ a little: an operation the balance of the fresh start already holds
    can be dated just after it. Up to 2 s after the start it is taken as inside it (not scaled); a later one is not."""
    for dated, inside in ((1.9, True), (2.0, True), (2.6, False)):
        sim = Sim(drop=20.0, day=12.5, streak=None)
        sim.poll(T0, 3000.0)                                         # the $1,500 paid in is in this balance
        out = sim.poll(T0 + 3, 3000.0, [deal(7, 1500.0, T0 + dated)], T0 + 2.8)
        assert ('7' in sim.state['cash_seen']) is inside, dated
        assert sim.state['peak'] == sim.state['day0'] == 3000.0 and not out['pending']
        start = [e for e in out['events'] if e['event'] == 'cash_start'][0]
        assert (start['tickets'], start['later']) == ((1, 0) if inside else (0, 1))


def test_a_read_made_before_the_start_is_not_the_first_read_of_that_start():
    sim = Sim()
    out = sim.poll(T0, 1500.0, [deal(1, 1500.0, T0 - 50)], T0 - 0.5)         # read at the end of the poll before
    assert sim.state['cash_baseline_done'] is False and sim.state['cash_seen'] == {}
    assert sim.state['cash_read_ok_at'] is None                      # (the start forgets the reads of before)
    sim.poll(T0 + 1, 1500.0, [deal(1, 1500.0, T0 - 50)], T0 + 0.5)
    assert sim.state['cash_baseline_done'] is True and sim.state['cash_read_ok_at'] == T0 + 0.5


def test_a_withdrawal_during_a_drawdown_does_not_move_the_percentages():
    """High 1500, balance 1300 (13.33 % down, limit 20): withdrawing 500 must leave it 13.33 % down. Shifting the
    high by the dollars (1000) would read 20 % and block the account with no new loss."""
    sim = Sim(drop=20.0, day=15.0)
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1300.0)
    assert round(sim.drop_pct(), 4) == 13.3333 and round(sim.day_pct(), 4) == 13.3333
    out = sim.settle(T0 + 100, 800.0, [deal(81, -500.0, T0 + 99.5)])
    assert not out['account_blocked'] and not out['tripped']
    assert round(sim.drop_pct(), 4) == 13.3333 and round(sim.day_pct(), 4) == 13.3333
    assert round(sim.state['peak'], 4) == round(1500.0 * 800 / 1300, 4)
    assert sim.state['day_start_balance'] == 1000.0 and sim.state['day_cash'] == -500.0
    assert sim.state['peak_at'] == T0                                # the high is still the high of that moment


def test_a_deposit_during_a_drawdown_does_not_move_the_percentages_either():
    sim = Sim(drop=20.0, day=None)
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1250.0)                                      # 16.67 % down
    out = sim.settle(T0 + 100, 2500.0, [deal(82, 1250.0, T0 + 99.5)])
    assert round(sim.drop_pct(), 4) == 16.6667 and sim.state['peak'] == 3000.0 and not out['tripped']
    assert not sim.settle(T0 + 200, 2401.0)['tripped']               # 19.97 % down on the money now at risk
    out = sim.settle(T0 + 300, 2400.0)                               # 20 %: a further loss of $100, not of $300
    assert out['tripped'] and sim.state['account_block']['rules'] == ['DROP']


def test_cash_and_a_trade_result_in_one_change_are_told_apart():
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 100, 1900.0, [deal(83, 500.0, T0 + 99.5)])         # +500 paid in, -100 lost
    assert sim.state['peak'] == 2000.0 and round(sim.drop_pct(), 4) == 5.0
    assert sim.state['day_start_balance'] == 2000.0 and not out['account_blocked']


def test_several_cash_lines_of_one_read_are_applied_in_time_order_each_once():
    sim = Sim(drop=20.0, day=None)
    sim.start(T0, 1000.0)
    sim.settle(T0 + 10, 900.0)                                       # 10 % down
    lines = [deal(92, -450.0, T0 + 99.8), deal(91, 900.0, T0 + 99.2)]        # given newest first
    out = sim.settle(T0 + 100, 1350.0, lines)                        # 900 + 900 - 450
    assert round(sim.drop_pct(), 4) == 10.0 and round(sim.state['peak'], 4) == 1500.0
    assert [e['ticket'] for e in out['events'] if e['event'] == 'cash'] == ['91', '92']
    assert sim.state['day_cash'] == 450.0 and sim.state['day_start_balance'] == 1450.0
    # the other order would give another high only if a line emptied the account on the way: -450 first is fine
    # too, but 900 must come before a withdrawal larger than the balance
    other = Sim(drop=20.0, day=None)
    other.start(T0, 1000.0)
    other.settle(T0 + 10, 900.0)
    out = other.settle(T0 + 100, 600.0, [deal(94, -1200.0, T0 + 99.8), deal(93, 900.0, T0 + 99.2)])
    assert round(other.drop_pct(), 4) == 10.0 and round(other.state['peak'], 4) == round(1000.0 * 600 / 900, 4)


def test_an_unfunded_account_raises_nothing_and_counts_from_its_first_money():
    sim = Sim()
    out = sim.start(T0, 0.0)                                         # started before the money arrived
    assert sim.state['peak'] == 0.0 and not out['account_blocked'] and not out['hold']
    v = sim.view(T0 + 1)
    assert v['drop']['pct'] == 0.0 and v['day']['pct'] == 0.0 and v['blocked'] is False
    out = sim.settle(T0 + 100, 1500.0, [deal(5, 1500.0, T0 + 99.5)])
    s = sim.state
    assert s['peak'] == s['day0'] == 1500.0 and s['day_start_balance'] == 1500.0
    assert s['peak_at'] == T0 + 104 and not out['account_blocked']
    assert sim.settle(T0 + 200, 1200.0)['tripped']                   # and from there the rules count


def test_a_balance_below_zero_is_not_scaled_from():
    """After a stop-out through a gap the balance can be below zero. Money paid in then cannot scale anything (the
    factor would be negative): counting starts from the balance of now."""
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 100, -50.0)                                # more than everything lost: blocked, of course
    assert out['tripped'] and round(sim.drop_pct(), 2) == 103.33
    sim.pressed('20261121_142000-777777')
    sim.poll(T0 + 200, -50.0)
    sim.poll(T0 + 201, -50.0, [], T0 + 200.5)
    assert sim.state['peak'] == -50.0 and sim.drop_pct() == 0.0 and not sim.out['account_blocked']
    out = sim.settle(T0 + 300, 1500.0, [deal(12, 1550.0, T0 + 299.5)])
    s = sim.state
    assert s['peak'] == s['day0'] == 1500.0 and s['peak_at'] == s['day0_at'] == T0 + 304
    assert not out['account_blocked'] and sim.drop_pct() == 0.0 and sim.day_pct() == 0.0


def test_a_profit_never_shows_as_a_negative_loss():
    sim = Sim()
    sim.start(at(21, 9), 1500.0)
    sim.settle(at(21, 10), 1400.0)
    sim.poll(at(22, 0, 0, 1), 1400.0)                                # the new day starts at 1400
    sim.settle(at(22, 9), 1460.0)                                    # +60 today, still under the high of 1500
    v = sim.view(at(22, 9, 0, 5))
    assert v['day']['pct'] == 0.0 and v['day']['day0'] == 1400.0     # not -4.3
    assert round(v['drop']['pct'], 4) == 2.6667
    sim.settle(at(22, 10), 1600.0)                                   # a new high
    v = sim.view(at(22, 10, 0, 5))
    assert v['drop']['pct'] == 0.0 and v['drop']['peak'] == 1600.0 and v['drop']['peak_at'] == at(22, 10, 0, 4)
    assert v['day']['pct'] == 0.0


def test_an_account_that_is_emptied_raises_nothing():
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.settle(T0 + 100, 0.0, [deal(6, -1500.0, T0 + 99.5)])
    assert sim.state['peak'] == sim.state['day0'] == 0.0 and not out['account_blocked'] and not out['tripped']
    assert sim.drop_pct() == 0.0 and sim.day_pct() == 0.0


def test_what_is_not_a_cash_line_is_left_out():
    sim = Sim()
    sim.start(T0, 1500.0)
    junk = [None, 'x', {'ticket': 1}, {'ticket': 2, 'amount': 'ten', 'time': T0 + 99},
            {'ticket': 3, 'amount': float('nan'), 'time': T0 + 99}, deal(4, 0.0, T0 + 99.5),
            {'amount': 100.0, 'time': T0 + 99.5}, deal(8, 50.0, None)]
    out = sim.settle(T0 + 100, 1600.0, junk)
    assert out['settled'] and sim.state['peak'] == 1600.0            # the 100 without a ticket was applied once
    assert round(sim.state['day_start_balance'], 2) == 1600.0
    cash = {e['ticket']: e['counted'] for e in out['events'] if e['event'] == 'cash'}
    assert cash == {'4': True, f'{T0 + 99.5}:100.0': True, '8': False}       # no time: only remembered


def test_the_list_of_seen_cash_lines_stays_short():
    seen = {str(i): T0 - 400000.0 + i for i in range(300)}
    seen.update({f'new{i}': T0 - 100.0 + i for i in range(5)})
    kept = S._pruned_cash(seen, T0)
    assert sorted(kept) == sorted(f'new{i}' for i in range(5))       # older than any later read can return
    assert S._pruned_cash({str(i): T0 for i in range(150)}, T0).keys() == {str(i) for i in range(150)}
    assert len(S._pruned_cash({str(i): T0 + i for i in range(5000)}, None)) == 2000


# ───────────────────────────── the new UTC day ─────────────────────────────

def test_the_new_utc_day_starts_from_the_balance_of_its_first_poll():
    sim = Sim()
    sim.start(at(21, 9), 1500.0)
    sim.settle(at(21, 10), 1400.0)
    assert sim.state['day_since'] == 'restart' and round(sim.day_pct(), 4) == 6.6667
    out = sim.poll(at(21, 23, 59, 59), 1400.0)
    assert sim.state['day'] == '2026-11-21'
    out = sim.poll(at(22, 0, 0, 1), 1400.0)
    s = sim.state
    assert s['day'] == '2026-11-22' and s['day_since'] == 'midnight'
    assert s['day0'] == s['day_start_balance'] == 1400.0 and s['day0_at'] == s['day_start_at'] == at(22, 0, 0, 1)
    assert s['day_cash'] == 0.0 and s['peak'] == 1500.0 and sim.day_pct() == 0.0
    assert round(sim.drop_pct(), 4) == 6.6667 and not out['settled']
    # yesterday's 6.67 % and today's 9 % are not one day's loss
    out = sim.settle(at(22, 8), 1274.0)
    assert not out['tripped'] and round(sim.day_pct(), 4) == 9.0
    assert sim.settle(at(22, 9), 1260.0)['tripped']                  # 10 % of today
    assert sim.state['account_block']['rules'] == ['DAY']


def test_a_change_first_seen_by_the_first_poll_of_a_new_day_is_not_a_loss_of_the_day_before():
    """The bot was stopped at 20:00 and starts at 08:00 two days later: the account is 12 % lower (the other bot's
    trades). Nobody knows on which day that was lost, so it is no 'loss today' of 12 %: the day starts from the
    balance found. The drop from the high still counts all of it."""
    sim = Sim(drop=20.0, day=10.0)
    sim.start(at(20, 9), 1500.0)
    sim.poll(at(20, 20), 1500.0)
    out = sim.poll(at(22, 8), 1320.0)                                # 12 % lower, first seen today
    assert out['pending'] and not out['hold']                        # the day rule does not count it, the drop is 12 %
    assert sim.state['day'] == '2026-11-20'                          # (the day changes when the balance is judged)
    out = sim.poll(at(22, 8, 0, 4), 1320.0, [], at(22, 8, 0, 3))
    s = sim.state
    assert out['settled'] and not out['tripped'] and not out['account_blocked']
    assert s['day'] == '2026-11-22' and s['day0'] == s['day_start_balance'] == 1320.0
    assert s['day_since'] == 'midnight' and s['day0_at'] == at(22, 8, 0, 4)
    assert round(sim.drop_pct(), 4) == 12.0 and sim.day_pct() == 0.0


def test_a_deposit_seen_by_the_first_poll_of_a_new_day_does_not_scale_the_new_day_twice():
    sim = Sim()
    sim.start(at(21, 9), 1500.0)
    sim.poll(at(21, 23, 59, 59), 1500.0)
    out = sim.poll(at(22, 0, 0, 1), 2000.0)                          # paid in around midnight
    assert out['pending'] and sim.state['day'] == '2026-11-21'
    out = sim.poll(at(22, 0, 0, 5), 2000.0, [deal(9, 500.0, at(22, 0, 0, 0))], at(22, 0, 0, 4))
    s = sim.state
    assert out['settled'] and s['day'] == '2026-11-22'
    assert s['peak'] == 2000.0 and s['day0'] == s['day_start_balance'] == 2000.0     # not 2666.67
    assert s['day_cash'] == 0.0 and sim.day_pct() == 0.0 and not out['account_blocked']


def test_the_days_own_start_is_not_changed_by_a_fresh_start_but_by_cash():
    sim = Sim()
    sim.start(at(21, 9), 1500.0)
    sim.poll(at(22, 0, 0, 1), 1500.0)                                # 00:00: the day starts at 1500
    sim.settle(at(22, 10), 1400.0)
    sim.pressed('20261122_110000-ffffff')
    sim.poll(at(22, 11), 1400.0)                                     # an unblock at 11:00
    s = sim.state
    assert s['day0'] == 1400.0 and s['day_since'] == 'restart' and s['day0_at'] == at(22, 11)
    assert (s['day_start_balance'], s['day_start_at']) == (1500.0, at(22, 0, 0, 1))      # "today -100" stays true
    sim.poll(at(22, 11, 0, 1), 1400.0, [], at(22, 11, 0, 0.5))
    sim.settle(at(22, 12), 1700.0, [deal(11, 300.0, at(22, 11, 59))])
    assert sim.state['day_start_balance'] == 1800.0 and sim.state['day_cash'] == 300.0
    v = sim.view(at(22, 12, 0, 4))
    assert v['day']['start_balance'] == 1800.0 and v['day']['cash'] == 300.0
    assert v['day']['start_at'] == at(22, 0, 0, 1) and v['day']['since'] == 'restart'
    assert v['drop']['balance'] - v['day']['start_balance'] == -100.0        # booked today: -100, cash left out


def test_a_fresh_start_on_a_new_day_also_starts_the_days_own_figures():
    sim = Sim()
    sim.start(at(21, 9), 1500.0)
    sim.pressed('20261122_080000-abcdef')
    sim.poll(at(22, 8), 1450.0)                                      # first poll of the new day is a fresh start
    s = sim.state
    assert s['day'] == '2026-11-22' and s['day_since'] == 'restart'
    assert (s['day_start_balance'], s['day_start_at']) == (1450.0, at(22, 8))


# ───────────────────────────── losing trades in a row ─────────────────────────────

def test_the_count_of_losing_trades_and_what_sets_it_back():
    sim = Sim(streak=5)
    sim.start(T0, 1500.0)
    sim.closed(T0 + 1, 'a', -0.01)
    sim.closed(T0 + 2, 'b', -30.0)
    assert sim.state['streak'] == 2
    sim.closed(T0 + 3, 'c', 0.0)                                     # break-even is not a loss
    assert sim.state['streak'] == 0
    sim.closed(T0 + 4, 'd', -1.0)
    sim.closed(T0 + 5, 'e', 12.5)                                    # a winner
    assert sim.state['streak'] == 0 and sim.state['bot_block'] is None
    assert sim.state['counted_trades'] == ['a', 'b', 'c', 'd', 'e']


def test_a_closed_trade_is_counted_once_whatever_is_reported_again():
    sim = Sim(streak=3)
    sim.start(T0, 1500.0)
    assert [e['event'] for e in sim.closed(T0 + 1, 4711, -5.0)] == ['trade']
    assert sim.closed(T0 + 2, 4711, -5.0) == [] and sim.closed(T0 + 3, '4711', -9.0) == []
    assert sim.state['streak'] == 1
    sim.closed(T0 + 4, 4712, -5.0)
    sim.closed(T0 + 5, 4713, +5.0)
    assert sim.closed(T0 + 6, 4711, -5.0) == [] and sim.state['streak'] == 0         # still known after a winner


def test_a_result_that_is_not_a_number_counts_as_a_loss():
    sim = Sim(streak=3)
    sim.start(T0, 1500.0)
    sim.closed(T0 + 1, 'a', None)
    sim.closed(T0 + 2, 'b', float('nan'))
    assert sim.state['streak'] == 2                                  # an unknown result must not set the count back
    sim.closed(T0 + 3, 'c', 'oops')
    assert sim.state['bot_block']['rule'] == 'STREAK'


def test_the_newest_500_counted_trades_are_remembered():
    sim = Sim(streak=None)
    sim.start(T0, 1500.0)
    for i in range(620):
        sim.closed(T0 + i, i, 1.0)
    kept = sim.state['counted_trades']
    assert len(kept) == 500 and kept[0] == '120' and kept[-1] == '619'
    assert sim.closed(T0 + 700, 619, -1.0) == [] and sim.closed(T0 + 701, 121, -1.0) == []


def test_the_block_of_losing_trades_is_set_once_and_the_count_goes_on():
    sim = Sim(streak=3)
    sim.start(T0, 1500.0)
    for i, key in enumerate('abc'):
        ev = sim.closed(T0 + i, key, -1.0)
    assert [e['event'] for e in ev] == ['trade', 'trip'] and ev[1]['scope'] == 'bot' and ev[1]['count'] == 3
    blk = dict(sim.state['bot_block'])
    assert [e['event'] for e in sim.closed(T0 + 9, 'd', -1.0)] == ['trade']          # an open trade closing later
    assert sim.state['bot_block'] == blk and sim.state['streak'] == 4
    sim.closed(T0 + 10, 'e', +50.0)                                  # a winner does not unblock: only the owner does
    assert sim.state['bot_block'] == blk and sim.state['streak'] == 0
    out = sim.poll(T0 + 11, 1500.0)
    assert sim.state['bot_block'] == blk and sim.view(T0 + 11)['blocked'] is True


def test_the_hold_while_a_closed_trade_without_a_result_could_be_the_nth_loss():
    sim = Sim(streak=3)
    sim.start(T0, 1500.0)
    sim.closed(T0 + 1, 'a', -1.0)
    assert not sim.poll(T0 + 2, 1500.0, waiting=1)['hold']           # 1 + 1 < 3
    sim.closed(T0 + 3, 'b', -1.0)
    out = sim.poll(T0 + 4, 1500.0, waiting=1)                        # 2 + 1 = 3: it could be the third loss
    assert out['hold'] and out['hold_why'] == 'results' and out['waiting'] == 1 and not out['pending']
    v = sim.view(T0 + 4, hold_since=T0 + 4)
    assert v['hold'] and not v['blocked'] and v['streak'] == {'count': 2, 'limit': 3, 'waiting': 1}
    assert v['reasons'] == ['The gold bot waits for the result of its last closed trade. If it is a loss, it has '
                            'lost 3 trades in a row (limit 3). No new trade until the result is known.']
    assert not sim.poll(T0 + 5, 1500.0, waiting=0)['hold']           # the result came: a winner, or nothing owed
    sim.closed(T0 + 6, 'c', +1.0)
    assert not sim.poll(T0 + 7, 1500.0, waiting=2)['hold']           # 0 + 2 < 3
    assert sim.poll(T0 + 8, 1500.0, waiting=3)['hold']
    sim2 = Sim(streak=None)
    sim2.start(T0, 1500.0)
    assert not sim2.poll(T0 + 1, 1500.0, waiting=50)['hold']         # the rule is off


# ───────────────────────────── the switch ─────────────────────────────

def test_off_blocks_nothing_and_trips_nothing_while_tracking_goes_on():
    sim = Sim(enabled=False)
    sim.start(T0, 1500.0)
    out = sim.poll(T0 + 10, 1000.0)                                  # a third of the account gone
    assert not out['hold'] and out['pending'] and out['enabled'] is False
    out = sim.poll(T0 + 14, 1000.0, [], T0 + 13.5)
    assert out['settled'] and not out['tripped'] and not out['account_blocked']
    assert sim.state['account_block'] is None and sim.state['settled_balance'] == 1000.0
    for i in range(6):
        sim.closed(T0 + 20 + i, f't{i}', -1.0)
    assert sim.state['streak'] == 6 and sim.state['bot_block'] is None       # counted, not blocked
    assert not sim.poll(T0 + 30, 1000.0, waiting=9)['hold']
    sim.settle(T0 + 40, 1800.0)
    assert sim.state['peak'] == 1800.0                               # the high is still tracked
    v = sim.view(T0 + 45)
    assert v['enabled'] is False and v['blocked'] is False and v['state'] == 'off' and v['blocked_scope'] is None
    assert round(v['drop']['pct'], 2) == 0.0 and v['streak']['count'] == 6
    assert v['reasons'] == ['No limit is applied: both bots of account ...1234 trade exactly as the strategy says. '
                            'The meters are for information only.']


def test_off_lifts_every_block_and_on_again_starts_fresh():
    sim = Sim()
    sim.start(T0, 1500.0)
    assert sim.settle(T0 + 10, 1190.0)['account_blocked']
    for i in range(3):
        sim.closed(T0 + 20 + i, f't{i}', -1.0)
    assert sim.view(T0 + 25)['blocked'] is True
    sim.c['enabled'] = False                                         # OFF pressed
    out = sim.poll(T0 + 30, 1190.0)
    v = sim.view(T0 + 30)
    assert v['blocked'] is False and v['hold'] is False and v['enabled'] is False
    assert v['account_blocked'] is True and v['bot_blocked'] is True         # they exist, but stop nothing
    assert [(e['event'], e.get('enabled')) for e in out['events']] == [('switch', False)]
    sim.settle(T0 + 40, 900.0)                                       # falls further while OFF: nothing new trips
    # ON is pressed: press writes a new id first, then the switch
    sim.pressed('20261121_150000-0a0a0a')
    sim.c['enabled'] = True
    out = sim.poll(T0 + 100, 900.0)
    v = sim.view(T0 + 100)
    assert v['enabled'] is True and v['blocked'] is False and v['account_blocked'] is False
    assert sim.state['peak'] == sim.state['day0'] == 900.0 and sim.state['streak'] == 0
    assert sim.state['bot_block'] is None and sim.state['account_block'] is None
    assert sorted(names(out['events'])) == [('fresh_start', 'account'), ('switch', None)]


def test_a_switch_set_back_on_without_a_new_id_blocks_what_is_blocked():
    """(The switch file removed by hand.) No fresh start was asked for: the blocks of before apply again."""
    sim = Sim()
    sim.start(T0, 1500.0)
    assert sim.settle(T0 + 10, 1190.0)['account_blocked']
    sim.c['enabled'] = False
    sim.poll(T0 + 20, 1190.0)
    sim.c['enabled'] = True
    out = sim.poll(T0 + 30, 1190.0)
    assert out['account_blocked'] and sim.view(T0 + 30)['blocked'] is True


# ───────────────────────────── another program in this bot's market (6.3) ─────────────────────────────

def test_note_other_program_blocks_this_bot_until_it_is_unblocked():
    sim = Sim()
    sim.start(T0, 1500.0)
    text = 'another program holds 2 trades of its own on XAUUSDm'
    sim.state, ev = S.note_other(sim.state, T0 + 5, text, True)
    blk = sim.state['bot_block']
    assert blk == {'rule': 'OTHER_PROGRAM', 'text': text, 'count': None, 'limit': None, 'at': T0 + 5}
    assert [(e['event'], e['scope'], e['rule']) for e in ev] == [('trip', 'bot', 'OTHER_PROGRAM')]
    again, ev = S.note_other(sim.state, T0 + 6, 'another program closed this bot\'s trade at 14:05 UTC', True)
    assert again['bot_block'] == blk and ev == []                    # the first block stays, said once
    sim.poll(T0 + 7, 1500.0)
    v = sim.view(T0 + 7)
    assert v['blocked'] and v['bot_blocked'] and v['blocked_scope'] == 'bot' and v['since'] == T0 + 5
    assert v['reasons'] == [
        'The gold bot opens no new trade since 21 Nov 14:05: another program is trading gold in this account '
        '(another program holds 2 trades of its own on XAUUSDm). If the old ladder bot still runs on this account, '
        'stop it, then press Unblock.']
    sim.pressed('20261121_142000-121212', scope='bot')               # Unblock
    sim.poll(T0 + 20, 1500.0)
    assert sim.state['bot_block'] is None and sim.view(T0 + 20)['blocked'] is False


def test_note_other_program_is_not_applied_while_the_safety_is_off_nor_over_a_block_of_losing_trades():
    sim = Sim(enabled=False)
    sim.start(T0, 1500.0)
    state, ev = S.note_other(sim.state, T0 + 5, 'another program holds 1 trade of its own on XAUUSDm', False)
    assert state['bot_block'] is None and ev == []
    sim2 = Sim(streak=1)
    sim2.start(T0, 1500.0)
    sim2.closed(T0 + 1, 'a', -1.0)
    state, ev = S.note_other(sim2.state, T0 + 5, 'x', True)
    assert state['bot_block']['rule'] == 'STREAK' and ev == []


# ───────────────────────────── a poll without a balance ─────────────────────────────

def test_without_a_balance_nothing_is_judged_and_the_blocked_state_stays():
    sim = Sim()
    sim.start(T0, 1500.0)
    assert sim.poll(T0 + 10, 1400.0)['pending']
    before = copy.deepcopy(sim.state)
    out = sim.poll(T0 + 500, None, [], T0 + 499)                     # the terminal answers nothing for 8 minutes
    after = dict(sim.state)
    assert after == before and out['pending'] and not out['settled']
    assert not out['hold']                                           # 6.7 %: no limit would be met
    assert sim.settle(T0 + 600, 1190.0)['account_blocked']
    out = sim.poll(T0 + 700, None)
    assert out['account_blocked'] and sim.view(T0 + 700)['blocked'] is True
    for junk in ('1500', float('nan'), float('inf'), True, [1500.0]):
        assert not sim.poll(T0 + 800, junk)['settled']               # not a balance: the same as none
    assert sim.state['settled_balance'] == 1190.0


def test_a_hold_is_kept_while_the_balance_is_not_known():
    sim = Sim()
    sim.start(T0, 1500.0)
    assert sim.poll(T0 + 10, 1100.0)['hold']
    out = sim.poll(T0 + 11, None)
    assert out['hold'] and out['pending']                            # the change seen last would still meet a limit


# ───────────────────────────── the block of the account, as the rules see it ─────────────────────────────

def test_a_block_file_blocks_a_bot_that_met_no_limit_itself_and_only_for_its_own_id():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.c.update(block_id='20261101_000000-999999', block_exists=True)       # the block file of another id
    assert not sim.poll(T0 + 9, 1500.0)['account_blocked']           # ...says nothing about this one
    sim.c.update(block_id='start', block_exists=True)                # the other bot made the file of this id
    out = sim.poll(T0 + 10, 1500.0)
    assert out['account_blocked'] and sim.state['account_block'] is None
    assert sim.state['block_exists_last'] is True
    assert sim.view(T0 + 10)['blocked_scope'] == 'account'
    sim.c.update(block_id='start', block_exists=False)               # the file is gone (FileNotFoundError)
    assert not sim.poll(T0 + 12, 1500.0)['account_blocked'] and sim.state['block_exists_last'] is False


def test_a_block_this_bot_holds_for_another_id_does_not_block():
    """(A state file edited by hand, or written by a version that kept old blocks.)"""
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1190.0)
    old = dict(sim.state['account_block'])
    state = dict(sim.state, period='20261121_150000-898989')
    assert state['account_block']['period'] == 'start'
    assert S.account_blocked(state, {}) is False
    assert S.account_blocked(dict(state, account_block=dict(old, period=state['period'])), {}) is True
    assert S.account_blocked(dict(state, account_block=None, block_exists_last=True), {}) is True
    assert S.account_blocked(dict(state, account_block=None, block_exists_last=True),
                             {'block_id': state['period'], 'block_exists': False}) is False


def test_when_the_folder_cannot_be_asked_the_last_known_answer_stays():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.c.update(block_id='start', block_exists=True)
    assert sim.poll(T0 + 10, 1500.0)['account_blocked']
    sim.c.update(block_id='start', block_exists=None)                # os.stat failed with something else than "not there"
    assert sim.poll(T0 + 11, 1500.0)['account_blocked']
    sim.c.update(block_id=None, block_exists=None)                   # (a new process: nothing read yet)
    assert sim.poll(T0 + 12, 1500.0)['account_blocked']              # the answer is part of the state


def test_while_the_account_is_blocked_nothing_new_trips_and_the_block_keeps_its_first_numbers():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1190.0)
    first = copy.deepcopy(sim.state['account_block'])
    out = sim.settle(T0 + 100, 900.0)                                # an open trade closes far lower
    assert not out['tripped'] and out['account_blocked'] and sim.state['account_block'] == first
    assert sim.state['settled_balance'] == 900.0                     # (the balance is still followed)


def test_a_trip_sets_the_block_in_the_state_of_that_very_poll():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.poll(T0 + 10, 1190.0)
    assert sim.state['account_block'] is None
    out = sim.poll(T0 + 14, 1190.0, [], T0 + 13.5)
    assert out['tripped'] and sim.state['account_block']['at'] == T0 + 14
    trip = [e for e in out['events'] if e['event'] == 'trip']
    assert len(trip) == 1 and trip[0]['scope'] == 'account' and trip[0]['rules'] == ['DROP', 'DAY']
    assert trip[0]['numbers']['balance'] == 1190.0 and trip[0]['id'] == 'start'
    assert not sim.poll(T0 + 15, 1190.0)['tripped']                  # once


# ───────────────────────────── the rules touch no file and change nothing they are given ─────────────────────────────

def test_the_rules_open_no_file_and_do_not_change_their_inputs(monkeypatch):
    def no_files(*a, **k):
        raise AssertionError(f'the rules must not touch a file: {a!r}')
    sim = Sim()
    for name in ('open',):
        monkeypatch.setattr(builtins, name, no_files)
    for name in ('stat', 'replace', 'remove', 'makedirs', 'listdir', 'rename', 'mkdir'):
        monkeypatch.setattr(os, name, no_files)
    steps = [(T0, 1500.0, None, None), (T0 + 1, 1500.0, [deal(1, 1500.0, T0 - 9)], T0 + 0.5),
             (T0 + 10, 1100.0, None, None), (T0 + 14, 1100.0, [deal(2, -100.0, T0 + 9.5)], T0 + 13.5),
             (T0 + 20, None, None, None), (at(22, 0, 0, 5), 1100.0, [], at(22, 0, 0, 4))]
    for t, bal, cash, read_at in steps:
        frozen = json.dumps(sim.state, sort_keys=True)
        controls = json.dumps(sim.c, sort_keys=True)
        given = copy.deepcopy(cash)
        state_in = sim.state
        sim.poll(t, bal, cash, read_at, waiting=1)
        assert json.dumps(state_in, sort_keys=True) == frozen and state_in is not sim.state
        assert json.dumps(sim.c, sort_keys=True) == controls and cash == given
        S.build_view(sim.state, sim.limits, t, {'enabled': True, 'account_blocked': sim.out['account_blocked']})
    frozen = json.dumps(sim.state, sort_keys=True)
    new, _ = S.count_trade(sim.state, sim.limits, T0 + 30, 'k', -1.0)
    new2, _ = S.note_other(sim.state, T0 + 31, 'another program', True)
    assert json.dumps(sim.state, sort_keys=True) == frozen and new is not sim.state and new2 is not sim.state
    assert sim.out['tripped'] is False and sim.state['account_block'] is not None    # (it did trip on the way)
    monkeypatch.undo()


def test_the_state_is_plain_json():
    sim = Sim()
    _a_bot_in_trouble(sim)
    sim.closed(T0 + 50, 'c', -1.0)
    sim.settle(T0 + 60, 1100.0)
    again = json.loads(json.dumps(sim.state, allow_nan=False))
    assert again == sim.state
    assert S.state_from_file(again) == sim.state                     # what a restart reads back is the same state
    assert sorted(sim.state) == sorted(S.new_state())                # no field the spec's list does not start with


# ───────────────────────────── the view: every key, every state, the owner's sentences ─────────────────────────────

VIEW_KEYS = {'enabled', 'blocked', 'hold', 'pending', 'account_blocked', 'bot_blocked', 'blocked_scope', 'reasons',
             'since', 'period', 'at', 'started_at', 'error', 'drop', 'day', 'streak', 'partner', 'limits',
             'account_dir', 'login_tail'}
DROP_KEYS = {'pct', 'limit', 'peak', 'peak_at', 'balance'}
DAY_KEYS = {'pct', 'limit', 'day0', 'day0_at', 'day', 'since', 'start_balance', 'start_at', 'cash'}
STREAK_KEYS = {'count', 'limit', 'waiting'}


def _has_every_key(v):
    assert VIEW_KEYS <= set(v), VIEW_KEYS - set(v)
    assert set(v['drop']) == DROP_KEYS and set(v['day']) == DAY_KEYS and set(v['streak']) == STREAK_KEYS
    assert set(v['limits']) == {'drop_pct', 'day_pct', 'streak_n'}
    assert isinstance(v['reasons'], list) and v['reasons'] and all(isinstance(r, str) and r for r in v['reasons'])
    assert isinstance(v['drop']['pct'], float) and isinstance(v['day']['pct'], float)
    for flag in ('enabled', 'blocked', 'hold', 'pending', 'account_blocked', 'bot_blocked'):
        assert isinstance(v[flag], bool), flag
    assert v['blocked_scope'] in ('account', 'bot', None)
    json.dumps(v, allow_nan=False)                                   # it goes into the trace and the status file


def test_every_key_of_the_view_is_always_there():
    _has_every_key(S.build_view(None, S.Limits(), T0))               # nothing known at all
    _has_every_key(S.build_view(S.new_state(), S.Limits(20, 10, 3), T0, {}))
    sim = Sim()
    _has_every_key(sim.view(T0))
    sim.poll(T0, None)
    _has_every_key(sim.view(T0))
    sim.start(T0, 1500.0)
    _has_every_key(sim.view(T0 + 1))
    sim.poll(T0 + 10, 1100.0)
    _has_every_key(sim.view(T0 + 10))
    sim.poll(T0 + 14, 1100.0, [], T0 + 13.5)
    _has_every_key(sim.view(T0 + 14))
    for i in range(3):
        sim.closed(T0 + 20 + i, i, -1.0)
    _has_every_key(sim.view(T0 + 30))
    _has_every_key(sim.view(T0 + 30, error='the safety state could not be saved', error_since=T0 + 20))
    _has_every_key(sim.view(T0 + 30, enabled=False))
    _has_every_key(sim.view(T0 + 30, partner=S.partner_view({'at': T0}, BTC, sim.limits, None, '...1234', T0 + 30)))


def test_the_view_of_a_bot_that_watches():
    sim = Sim(drop=20.0, day=15.0, streak=3)
    sim.start(T0, 1612.40)
    sim.settle(T0 + 60, 1412.40)
    sim.closed(T0 + 61, 'a', -200.0)
    v = sim.view(T0 + 70, account_dir='X:/acct')
    assert v['reasons'] == ['Watching account ...1234. New trades are allowed.']
    assert (v['enabled'], v['blocked'], v['hold'], v['pending'], v['state']) == (True, False, False, False, 'on')
    assert v['blocked_scope'] is None and v['since'] is None and v['error'] is None
    assert v['period'] == 'start' and v['at'] == T0 + 70 and v['started_at'] == T0
    assert v['drop'] == {'pct': pytest.approx(12.4038, abs=1e-4), 'limit': 20.0, 'peak': 1612.40, 'peak_at': T0,
                         'balance': 1412.40}
    assert v['day'] == {'pct': pytest.approx(12.4038, abs=1e-4), 'limit': 15.0, 'day0': 1612.40, 'day0_at': T0,
                        'day': '2026-11-21', 'since': 'restart', 'start_balance': 1612.40, 'start_at': T0,
                        'cash': 0.0}
    assert v['streak'] == {'count': 1, 'limit': 3, 'waiting': 0}
    assert v['limits'] == {'drop_pct': 20.0, 'day_pct': 15.0, 'streak_n': 3}
    assert v['account_dir'] == 'X:/acct' and v['login_tail'] == '...1234' and v['partner'] is None


def test_the_sentence_while_a_limit_is_being_checked():
    sim = Sim()
    sim.start(T0 - 3600, 1500.0)
    sim.poll(T0 + 20, 1100.0)
    v = sim.view(T0 + 21)
    assert v['state'] == 'checking' and v['hold'] and not v['blocked'] and v['since'] == T0 + 20
    assert v['reasons'] == ['A limit was reached at 14:05. Checking that it is a loss and not a withdrawal '
                            '(up to 1 minute). No new trade until then.']


def test_the_sentences_of_a_blocked_account_are_the_spec_s():
    """Section 10: 'The account fell 20.4% below its high (limit 20%): balance $1,194.00, high $1,500.00 on
    12 Nov.' and the day sentence, with the numbers of the block."""
    sim = Sim(drop=20.0, day=None)
    sim.start(at(12, 9, 30), 1500.0)                                 # the high is of 12 Nov
    sim.poll(at(21, 14, 4, 56), 1194.0)
    sim.poll(at(21, 14, 5, 0), 1194.0, [], at(21, 14, 4, 59.5))
    v = sim.view(at(21, 14, 5, 1))
    assert v['blocked'] and v['account_blocked'] and v['blocked_scope'] == 'account' and v['state'] == 'account_blocked'
    assert v['since'] == at(21, 14, 5, 0)
    assert v['reasons'] == [
        'Both bots open no new trade and add nothing to open trades since 21 Nov 14:05. Open trades keep their stop '
        'and target. Press Unblock to trade again.',
        'The account fell 20.4% below its high (limit 20%): balance $1,194.00, high $1,500.00 on 12 Nov.',
        'The gold bot (acct_x9) saw it.']

    day = Sim(drop=None, day=10.0)
    day.start(at(20, 9), 1500.0)
    day.poll(at(21, 0, 0, 1), 1500.0)                                # 00:00 of 21 Nov: the day starts at 1500
    day.poll(at(21, 14, 4, 56), 1347.10)
    day.poll(at(21, 14, 5, 0), 1347.10, [], at(21, 14, 4, 59.5))
    assert day.view(at(21, 14, 5, 1))['reasons'][1:] == [
        'The account lost 10.2% on 21 Nov, UTC day (limit 10%): balance $1,347.10, $1,500.00 at the start of that '
        'day.', 'The gold bot (acct_x9) saw it.']
    assert S.block_sentences(['DAY'], dict(day.state['account_block']['numbers'], day_since='restart',
                                           day0_at=at(21, 9, 7))) == [
        'The account lost 10.2% on 21 Nov, UTC day (limit 10%): balance $1,347.10, $1,500.00 when counting started '
        'that day at 09:07.']
    late = dict(day.state['account_block']['numbers'], day0_at=at(21, 8, 30))        # the bot started at 08:30
    assert S.block_sentences(['DAY'], late) == [
        'The account lost 10.2% on 21 Nov, UTC day (limit 10%): balance $1,347.10, $1,500.00 at 08:30, the first '
        'balance this bot saw that day.']
    assert S.block_sentences(['DAY'], dict(late, day0_at=at(21, 0, 4, 59)))[0].endswith('at the start of that day.')
    assert S.block_sentences(['DAY'], dict(late, day='?'))[0].endswith('$1,500.00 at the start of that day.')
    assert S.block_sentences(['DROP', 'DAY'], sim.state['account_block']['numbers'])[0].startswith('The account fell')
    assert S.block_sentences([], {}) == [] and S.block_sentences(['DROP'], None)[0].startswith('The account fell')


def test_a_block_whose_details_cannot_be_read_still_says_that_it_blocks():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.c.update(block_id='start', block_exists=True)
    sim.poll(T0 + 10, 1500.0)
    v = sim.view(T0 + 10, block=None, block_since=T0 + 3)            # an empty block file: only its time is known
    assert v['blocked'] and v['since'] == T0 + 3
    assert v['reasons'] == [
        'Both bots open no new trade and add nothing to open trades since 21 Nov 14:05. Open trades keep their stop '
        'and target. Press Unblock to trade again.', 'The details of this block cannot be read.']
    v = sim.view(T0 + 10, block={'at': None, 'reasons': ['The account fell 21.0% below its high (limit 20%): '
                                                         'balance $1,185.00, high $1,500.00 on 21 Nov.',
                                                         'The BTC bot (acct_b9) saw it.', 7, '']})
    assert v['reasons'][1:] == ['The account fell 21.0% below its high (limit 20%): balance $1,185.00, high '
                                '$1,500.00 on 21 Nov.', 'The BTC bot (acct_b9) saw it.']
    assert v['reasons'][0].startswith('Both bots open no new trade and add nothing to open trades. ')    # no time known


def test_the_sentence_of_a_bot_blocked_for_losing_trades_names_the_other_bot():
    sim = Sim(streak=10)
    sim.start(T0 - 5000, 1500.0)
    for i in range(10):
        sim.closed(T0 - 100 + i * 10 + 10, i, -3.0)                  # the tenth at 14:05:00
    sim.poll(T0 + 1, 1500.0)
    fresh = S.partner_view({'at': T0, 'period': 'start', 'bot_blocked': False, 'blocked': False}, BTC, sim.limits,
                           None, '...1234', T0 + 1)
    v = sim.view(T0 + 1, partner=fresh)
    assert v['blocked'] and v['bot_blocked'] and not v['account_blocked'] and v['blocked_scope'] == 'bot'
    assert v['state'] == 'bot_blocked' and v['since'] == T0
    assert v['reasons'] == ['The gold bot opens no new trade since 21 Nov 14:05: it lost 10 trades in a row '
                            '(limit 10). Its open trade keeps its stop and target. The BTC bot is not blocked.']
    both = dict(fresh, bot_blocked=True)
    assert sim.view(T0 + 1, partner=both)['reasons'][0].endswith('target. The BTC bot is blocked as well.')
    for unknown in (None, dict(fresh, stale=True), dict(fresh, period='20261101_000000-000000')):
        assert sim.view(T0 + 1, partner=unknown)['reasons'][0].endswith('Its open trade keeps its stop and target.')
    # the BTC bot's own sentence
    v = S.build_view(sim.state, sim.limits, T0 + 1, {'branch': BTC, 'partner_branch': GOLD, 'partner': fresh})
    assert v['reasons'][0].startswith('The BTC bot opens no new trade since 21 Nov 14:05: it lost 10 trades')
    assert v['reasons'][0].endswith('The gold bot is not blocked.')


def test_a_check_of_the_account_is_also_said_under_a_block_of_this_bot():
    sim = Sim(streak=3)
    sim.start(T0 - 600, 1500.0)
    for i in range(3):
        sim.closed(T0 - 300 + i, i, -1.0)
    sim.poll(T0 + 20, 1100.0)                                        # blocked for losing trades, and a limit is checked
    v = sim.view(T0 + 21)
    assert v['state'] == 'bot_blocked' and v['blocked'] and v['hold'] and v['since'] == T0 - 298
    assert len(v['reasons']) == 2 and v['reasons'][0].startswith('The gold bot opens no new trade since 21 Nov 14:00')
    assert v['reasons'][1] == ('A limit was reached at 14:05. Checking that it is a loss and not a withdrawal '
                               '(up to 1 minute). No new trade until then.')


def test_both_blocks_at_once_are_both_said_the_account_first():
    sim = Sim()
    sim.start(T0, 1500.0)
    sim.settle(T0 + 10, 1190.0)
    for i in range(3):
        sim.closed(T0 + 20 + i, i, -1.0)
    sim.poll(T0 + 30, 1190.0)
    v = sim.view(T0 + 30)
    assert v['blocked_scope'] == 'account' and v['state'] == 'account_blocked' and v['since'] == T0 + 14
    assert len(v['reasons']) == 5 and v['reasons'][0].startswith('Both bots open no new trade')
    assert v['reasons'][4].startswith('The gold bot opens no new trade since 21 Nov 14:05: it lost 3 trades in a row')
    assert 'is not blocked' not in v['reasons'][4]                   # (both are: the account is)


def test_the_error_view_blocks_while_on_and_not_while_off():
    sim = Sim()
    sim.start(T0, 1500.0)
    why = 'the safety state could not be saved since 14:05 UTC (PermissionError: denied)'
    v = sim.view(T0 + 90, error=why, error_since=T0)
    assert v['error'] == why and v['blocked'] is True and v['state'] == 'error' and v['since'] == T0
    assert v['account_blocked'] is False and v['bot_blocked'] is False and v['blocked_scope'] is None
    assert v['reasons'] == ['The safety check failed: no new trades until it works again or the safety is turned OFF.']
    v = sim.view(T0 + 90, error=why, error_since=T0, enabled=False)
    assert v['error'] == why and v['blocked'] is False and v['state'] == 'off'
    assert v['reasons'][0].startswith('No limit is applied')
    sim.settle(T0 + 100, 1190.0)                                     # an error on top of a real block: both are said
    v = sim.view(T0 + 110, error=why, error_since=T0)
    assert v['state'] == 'error' and v['blocked_scope'] == 'account' and len(v['reasons']) == 5
    assert v['reasons'][0].startswith('The safety check failed') and v['reasons'][1].startswith('Both bots')


def test_the_view_shows_no_hold_and_no_block_while_off_whatever_was_true_a_moment_ago():
    """Between two polls the owner turns the safety OFF: the view made then (after a closed trade, say) must not
    carry the hold of the poll before."""
    sim = Sim()
    sim.start(T0, 1500.0)
    out = sim.poll(T0 + 10, 1100.0)
    assert out['hold']
    stale = {'hold': True, 'hold_why': 'limit', 'hold_since': T0 + 10, 'pending': True, 'account_blocked': True}
    v = S.build_view(sim.state, sim.limits, T0 + 11, dict(stale, enabled=False, login_tail='...1234'))
    assert v['hold'] is False and v['blocked'] is False and v['state'] == 'off' and v['pending'] is True
    v = S.build_view(sim.state, sim.limits, T0 + 11, dict(stale, enabled=True, login_tail='...1234'))
    assert v['hold'] is True and v['blocked'] is True


def test_the_partner_part_of_the_view():
    mine = S.Limits(20.0, 10.0, 3)
    sha_a, sha_b = S.login_sha(12345678), S.login_sha(87654321)
    status = {'at': T0 - 5, 'period': 'start', 'blocked': True, 'bot_blocked': True, 'login_tail': '...5678',
              'login_sha': sha_a, 'limits': {'drop_pct': 20.0, 'day_pct': 10.0, 'streak_n': 9},
              'drop': {'pct': 4.25}, 'day': {'pct': 1.5}}
    p = S.partner_view(status, BTC, mine, sha_a, '...5678', T0)
    assert p == {'branch': BTC, 'seen_at': T0 - 5, 'blocked': True, 'bot_blocked': True, 'drop_pct': 4.25,
                 'day_pct': 1.5, 'limits_differ': False, 'account_differs': False, 'period': 'start',
                 'stale': False}                                    # its own losing-trades limit may differ
    assert S.partner_view(dict(status, limits={'drop_pct': 25.0, 'day_pct': 10.0}), BTC, mine, sha_a, '...5678',
                          T0)['limits_differ'] is True
    assert S.partner_view(dict(status, limits={'drop_pct': 20.0, 'day_pct': None}), BTC, mine, sha_a, '...5678',
                          T0)['limits_differ'] is True
    assert S.partner_view(dict(status, limits='?'), BTC, mine, sha_a, '...5678', T0)['limits_differ'] is False
    assert S.partner_view(status, BTC, mine, sha_b, '...4321', T0)['account_differs'] is True
    same_tail_other_account = S.partner_view(dict(status, login_sha=S.login_sha(99995678)), BTC, mine, sha_a,
                                             '...5678', T0)
    assert same_tail_other_account['account_differs'] is True        # the last 4 digits alone would not tell
    no_sha = dict(status, login_sha=None)
    assert S.partner_view(no_sha, BTC, mine, None, '...4321', T0)['account_differs'] is True
    assert S.partner_view(no_sha, BTC, mine, None, '...5678', T0)['account_differs'] is False
    assert S.partner_view(no_sha, BTC, mine, None, '...?', T0)['account_differs'] is False      # not known: no alarm
    assert S.partner_view(status, BTC, mine, sha_a, '...5678', T0 + 55)['stale'] is False
    old = S.partner_view(status, BTC, mine, sha_a, '...5678', T0 + 56)
    assert old['stale'] is True and old['seen_at'] == T0 - 5 and old['blocked'] is True          # last seen 61 s ago
    assert S.partner_view({'period': 7}, BTC, mine, sha_a, '...5678', T0) == {
        'branch': BTC, 'seen_at': None, 'blocked': False, 'bot_blocked': False, 'drop_pct': None, 'day_pct': None,
        'limits_differ': False, 'account_differs': False, 'period': None, 'stale': True}
    assert S.partner_view(None, BTC, mine, sha_a, '...5678', T0) is None                         # no status file


# ───────────────────────────── dates, money and names as the owner reads them ─────────────────────────────

def test_dates_money_and_names():
    assert S._stamp(T0) == '21 Nov 14:05' and S._day_text(at(5, 9, 7)) == '5 Nov'
    assert S._stamp(at(5, 9, 7)) == '5 Nov 09:07' and S._clock(T0 + 610, seconds=True) == '14:15:10'
    assert S._stamp(at(1, 0, 0, month=1)) == '1 Jan 00:00' and S._stamp(at(31, 23, 59, 59, month=12)) == '31 Dec 23:59'
    assert S._day_key(at(21, 23, 59, 59)) == '2026-11-21' and S._day_key(at(22)) == '2026-11-22'
    assert S._name_stamp(T0 + 10) == '20261121_140510' and S._iso(T0) == '2026-11-21T14:05:00Z'
    assert S._day_key_text('2026-11-21') == '21 Nov' and S._day_key_text('2026-01-03') == '3 Jan'
    assert S._day_key_text(None) == 'that day' and S._day_key_text('2026-13-01') == 'that day'
    assert S._money(1194) == '$1,194.00' and S._money(1347.1) == '$1,347.10' and S._money(-3.1) == '-$3.10'
    assert S._money(1234567.891) == '$1,234,567.89' and S._money(-0.001) == '$0.00' and S._money(0) == '$0.00'
    assert S._pct(20.44) == '20.4%' and S._pct(10.19) == '10.2%' and S._pct(0) == '0.0%'
    assert S._plain(20.0) == '20' and S._plain(12.5) == '12.5' and S._plain(9) == '9'
    assert S._length(600) == '10 minutes' and S._length(60) == '1 minute' and S._length(86400) == '24 hours'
    assert S._length(9600) == '2 hours 40 minutes' and S._length(3600) == '1 hour' and S._length(45) == '45 seconds'
    assert S._ago(3) == '3 seconds' and S._ago(1) == '1 second' and S._ago(300) == '5 minutes'
    assert S._ago(7200) == '2 hours' and S._ago(400000) == '4 days'
    # the branch names are live<n>_<x or b><design>: the letter after the underscore says which bot it is
    assert S._bot('live77_xq9') == 'the gold bot' and S._bot('live100_bq9') == 'the BTC bot'
    assert S._bot('live0_Bzz') == 'the BTC bot' and S._bot('live5_X') == 'the gold bot'
    assert S._bot('live77_qx9') == 'this bot' and S._bot('xgold') == 'this bot' and S._bot('a_b_x') == 'the BTC bot'
    assert S._bot('main') == 'this bot' and S._bot(None) == 'this bot' and S._bot('zzz', other=True) == 'the other bot'
    assert S._market('acct_x9') == 'gold' and S._market('acct_b9') == 'BTC' and S._market('acct_q') is None
    # a time nobody can name does not crash a sentence
    for junk in (None, 'soon', float('nan'), 1e300, True):
        assert S._stamp(junk) == 'an unknown time' and S._clock(junk) == 'an unknown time'
        assert S._iso(junk) is None and S._day_key(junk) is None
    assert S._money(None) == 'an unknown amount' and S._pct(None) == 'an unknown share'
    assert S._name_stamp(None) == '19700101_000000'


def test_the_shared_helpers_are_unchanged():
    """Spec 2.4: the three helpers every part of the bot uses keep their behaviour exactly."""
    assert S.account_dir(r'C:\Alcadeias\some_branch', 'some_account') == r'C:\Alcadeias\some_account'
    assert S.account_dir('C:\\Alcadeias\\some_branch\\', 'some_account') == r'C:\Alcadeias\some_account'
    assert S.account_dir(r'D:\x\y\bot', 'acct') == r'D:\x\y\acct' and S.account_dir(r'x\bot', 'acct') == r'x\acct'
    private = os.path.join(os.sep, 'tmp', 'pytest-1', 'test_a0')
    assert S.account_dir(os.path.join(private, 'bot_output'), 'acct') == os.path.join(private, 'acct')
    assert S.account_dir(os.path.join(private, 'bot_output') + os.sep, 'acct') == os.path.join(private, 'acct')
    assert S.mask_login(12345678) == '...5678' and S.mask_login('00123456') == '...3456'
    assert S.mask_login(12) == '...12' and S.mask_login(0) == '...0'
    for unknown in (None, '', 'abc', '12a4', -5, True, 3.0, [1234]):
        assert S.mask_login(unknown) == '...?' and S.login_sha(unknown) is None
    assert S.login_sha(0) == '5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9'
    assert S.login_sha(' 12345678 ') == S.login_sha(12345678) == S.login_sha('12345678')
    assert S.login_sha('0012') == S.login_sha(12) and len(S.login_sha(12345678)) == 64
