"""
The buttons of the auto-safety and its command line (safety.press, safety.main): what each action changes from
each state, the PIN and its lock, what a page that is not fresh may do, the audit file, and safety.bat's commands.
Every file is in the test's tmp_path; no command is started as a process (main() is called as a function).

The rules are in test_safety_core.py, the files of a bot in test_safety_files.py. Limits and branch names are
test values ('acct_x9' a gold bot, 'acct_b9' a BTC bot).

Run:  python3 -B -m pytest tests_demo/test_safety_press.py -q -p no:cacheprovider
"""
import builtins
import importlib.util
import json
import os
import sys
import threading
import time
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import differs, found

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location('safety_tested_press', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()

T0 = datetime(2026, 11, 21, 14, 7, 10, tzinfo=timezone.utc).timestamp()      # 21 Nov 14:07:10 UTC
GOLD, BTC = 'acct_x9', 'acct_b9'
PIN = '482913'
WEB = 'dashboard acct_x9 from 10.0.0.9'
HOUR = 3600.0


@pytest.fixture
def acct(tmp_path):
    """An account folder with a PIN, as after the dashboard's first start."""
    d = tmp_path / 'acct'
    d.mkdir()
    (d / 'safety_pin.txt').write_text(PIN + '\n', encoding='ascii')
    return d


def press(acct, action, pin=PIN, now=T0, by=WEB, **kw):
    return S.press(str(acct), action, pin, by, now, **kw)


def snap(folder):
    return {p.name: p.read_bytes() for p in sorted(Path(folder).iterdir())}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def restart_id(acct):
    f = Path(acct) / 'safety_restart.json'
    return read(f)['id'] if f.exists() else 'start'


def audit(acct):
    f = Path(acct) / 'safety_audit.jsonl'
    return [json.loads(line) for line in f.read_text(encoding='utf-8').splitlines()] if f.exists() else []


def lockout(acct):
    return read(Path(acct) / 'safety_lockout.json')


def bot(acct, branch=GOLD, partner=BTC, streak=3):
    return S.Tracker(str(acct), str(Path(acct).parent / branch / 'state' / 'safety_state.json'), branch, partner,
                     S.Limits(20.0, 10.0, streak), login=12345678)


def tick(tr, now, balance, cash=None, read_at=None):
    view = tr.poll(now, balance, cash, read_at)
    tr.flush(now)
    return view


def running(acct, now=T0 - 600, balance=1500.0):
    """Both bots of the account, started and counting."""
    gold, btc = bot(acct), bot(acct, BTC, GOLD)
    for tr in (gold, btc):
        assert tr.load(now)
        tick(tr, now, balance)
        tick(tr, now + 1, balance, [], now + 0.5)
    return gold, btc


def lose(trackers, now, balance):
    for tr in trackers:
        tick(tr, now, balance)
    return [tick(tr, now + 4, balance, [], now + 3.5) for tr in trackers]


def see(trackers, now, balance):
    """Two polls: the first reads what was pressed, the second counts under it."""
    for tr in trackers:
        tick(tr, now, balance)
    return [tick(tr, now + 1, balance, [], now + 0.5) for tr in trackers]


# ───────────────────────────── every action from every state ─────────────────────────────

def test_nothing_blocked_and_on_what_each_button_does(acct):
    before = snap(acct)
    assert press(acct, 'on', pin=None) == (True, 'The safety is already ON.')
    assert not differs(snap(acct), before)                                      # nothing written, not even an audit line
    assert press(acct, 'unblock') == (True, 'Nothing is blocked.')
    after = snap(acct)                                               # the PIN was checked: its count, nothing else
    assert sorted(set(after) - set(before)) == ['safety_lockout.json'] and lockout(acct)['wrong'] == 0
    assert press(acct, 'off') == (True, 'Safety is OFF since 14:07:10 UTC.')
    assert read(acct / 'safety_switch.json') == {'enabled': False, 'at': '2026-11-21T14:07:10Z', 't': T0, 'by': WEB}
    assert not (acct / 'safety_restart.json').exists()               # OFF starts nothing afresh
    assert S.read_controls(str(acct))['enabled'] is False
    lines = audit(acct)
    assert len(lines) == 1 and lines[0]['action'] == 'off' and lines[0]['result'] == 'done'
    assert lines[0]['by'] == WEB and lines[0]['was'] == {'id': 'start', 'enabled': True}
    assert lines[0]['at'] == '2026-11-21T14:07:10Z' and lines[0]['message'] == 'Safety is OFF since 14:07:10 UTC.'


def test_off_what_each_button_does(acct):
    press(acct, 'off')
    before = snap(acct)
    assert press(acct, 'off', now=T0 + 5) == (True, 'The safety is already OFF.')
    assert press(acct, 'unblock', now=T0 + 6) == (True, 'Nothing is blocked.')
    assert not differs(snap(acct), before)                                      # no file changed, no audit line
    ok, msg = press(acct, 'on', pin=None, now=T0 + 60)               # ON needs no PIN
    assert (ok, msg) == (True, 'Safety is ON since 14:08:10 UTC. Counting starts from the current balance.')
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'account' and r['why'] == 'on' and r['by'] == WEB and r['t'] == T0 + 60
    assert r['id'].startswith('20261121_140810-') and len(r['id']) == 22 and r['account_id'] == r['id']
    assert read(acct / 'safety_switch.json')['enabled'] is True
    c = S.read_controls(str(acct))
    assert c['enabled'] is True and c['period'] == r['id'] and c['scope'] == 'account'
    assert c['pressed_at'] == T0 + 60 and c['pressed_why'] == 'on' and c['switched_at'] == T0 + 60
    assert [(a['action'], a['result']) for a in audit(acct)] == [('off', 'done'), ('on', 'done')]
    assert audit(acct)[1]['id'] == r['id'] and audit(acct)[1]['scope'] == 'account'


def test_an_account_block_is_lifted_for_both_bots_by_one_unblock(acct):
    gold, btc = running(acct)
    for i in range(3):
        btc.on_trade_closed(T0 - 500 + i, i, -5.0)                   # the BTC bot is blocked by itself as well
    views = lose((gold, btc), T0 - 400, 1190.0)                      # 20.7 % down: the account is blocked
    assert all(v['blocked'] and v['account_blocked'] for v in views)
    assert (acct / 'safety_block_start.json').exists()
    assert press(acct, 'unblock') == (True, 'Unblocked at 14:07:10 UTC. Counting again from the current balance.')
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'account' and r['why'] == 'unblock of the account' and r['account_id'] == r['id']
    for v in see((gold, btc), T0 + 5, 1190.0):
        assert v['blocked'] is False and v['period'] == r['id'] and v['drop']['peak'] == 1190.0
        assert v['streak']['count'] == 0 and v['bot_blocked'] is False       # all three rules count again
    assert press(acct, 'unblock', now=T0 + 20) == (True, 'Nothing is blocked.')
    assert restart_id(acct) == r['id']


def test_a_block_of_one_bot_is_lifted_without_touching_the_account(acct):
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1400.0)                              # 6.7 % down: nothing blocked
    for i in range(3):
        gold.on_trade_closed(T0 - 300 + i, i, -5.0)
    btc.on_trade_closed(T0 - 300, 'x', -5.0)
    see((gold, btc), T0 - 200, 1400.0)
    assert gold.view()['bot_blocked'] and not btc.view()['blocked']
    ok, msg = press(acct, 'unblock')
    assert ok and msg == ("Unblocked at 14:07:10 UTC: losing trades in a row start again from 0. The account's high "
                          "and today's start are unchanged.")
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'bot' and r['why'] == 'unblock of one bot' and r['account_id'] == 'start'
    g, b = see((gold, btc), T0 + 5, 1400.0)
    assert g['blocked'] is False and g['streak']['count'] == 0 and g['period'] == r['id']
    assert b['streak']['count'] == 1 and b['period'] == r['id']      # the other bot's count is its own
    for v in (g, b):
        assert v['drop']['peak'] == 1500.0 and round(v['drop']['pct'], 2) == 6.67 and v['day']['day0'] == 1500.0
    pressed = [a for a in audit(acct) if a.get('action') == 'unblock']
    assert len(pressed) == 1 and pressed[0]['scope'] == 'bot' and pressed[0]['id'] == r['id']
    seen = [a for a in audit(acct) if a.get('event') == 'fresh_start' and a['id'] == r['id']]
    assert sorted((a['by'], a['scope']) for a in seen) == [('bot acct_b9', 'bot'), ('bot acct_x9', 'bot')]


def test_a_stopped_bots_old_status_does_not_keep_unblock_alive(acct):
    """The gold bot is stopped while blocked. After the Unblock its status file still says 'blocked', under the old
    id: a further press must not start the running bot afresh again and again."""
    gold, btc = running(acct)
    for i in range(3):
        gold.on_trade_closed(T0 - 300 + i, i, -5.0)
    see((gold, btc), T0 - 200, 1500.0)                               # ...and the gold bot stops here
    assert press(acct, 'unblock')[1].startswith('Unblocked at 14:07:10 UTC: losing trades in a row')
    first = restart_id(acct)
    see((btc,), T0 + 5, 1500.0)
    assert read(acct / 'safety_status_acct_x9.json')['bot_blocked'] is True          # the stopped bot's old status
    before = snap(acct)
    assert press(acct, 'unblock', now=T0 + 30) == (True, 'Nothing is blocked.')
    assert not differs(snap(acct), before) and restart_id(acct) == first
    again = bot(acct)                                                # the gold bot starts: the press is applied now
    assert again.load(T0 + 60)
    v = see((again,), T0 + 60, 1500.0)[0]
    assert v['blocked'] is False and v['streak']['count'] == 0 and v['drop']['peak'] == 1500.0


def test_a_bot_that_was_stopped_through_two_unblocks_does_not_block_the_account_again(acct):
    """The gold bot is stopped while the account is blocked. The owner unblocks the account; later the BTC bot
    loses three in a row and he unblocks that. The newest press is 'one bot', but the gold bot has not taken the
    unblock of the account before it: started again it must take that one, not judge the balance against the old
    high and block both bots a second time."""
    gold, btc = running(acct)
    lose((gold, btc), T0 - 500, 1190.0)                              # 20.7 % down: blocked; the gold bot stops here
    assert press(acct, 'unblock', now=T0 - 400)[1].startswith('Unblocked at 14:00:30 UTC. Counting again')
    account_id = restart_id(acct)
    see((btc,), T0 - 390, 1190.0)
    for i in range(3):
        btc.on_trade_closed(T0 - 300 + i, f'b{i}', -2.0)
    see((btc,), T0 - 290, 1184.0)
    assert btc.view()['bot_blocked'] and not btc.view()['account_blocked']
    assert press(acct, 'unblock', now=T0 - 200)[1].startswith('Unblocked at 14:03:50 UTC: losing trades in a row')
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'bot' and r['account_id'] == account_id and r['id'] != account_id
    again = bot(acct)                                                # the gold bot starts: its state is of the old id
    assert again.load(T0 - 100) is True and again.view()['account_blocked'] is True
    v = see((again,), T0 - 99, 1184.0)[0]
    assert v['blocked'] is False and v['period'] == r['id']
    assert v['drop']['peak'] == 1184.0 and v['drop']['pct'] == 0.0   # counting from the balance of now
    v = lose((again, btc), T0 - 50, 1150.0)[0]                       # 2.9 % down from there: nothing is blocked
    assert v['blocked'] is False and not [n for n in snap(acct) if n.startswith(f"safety_block_{r['id']}")]


def test_an_account_block_whose_file_could_not_be_written_can_still_be_unblocked(acct, monkeypatch):
    gold, btc = running(acct)
    real = builtins.open

    def no_block_file(path, mode='r', *a, **k):
        if 'safety_block_' in str(path) and 'x' in mode:
            raise PermissionError(13, 'Permission denied')
        return real(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', no_block_file, raising=False)
    v = lose((gold,), T0 - 400, 1190.0)[0]
    assert v['account_blocked'] and not (acct / 'safety_block_start.json').exists()
    assert read(acct / 'safety_status_acct_x9.json')['account_blocked'] is True
    assert press(acct, 'unblock') == (True, 'Unblocked at 14:07:10 UTC. Counting again from the current balance.')
    assert read(acct / 'safety_restart.json')['scope'] == 'account'
    assert see((gold,), T0 + 5, 1190.0)[0]['blocked'] is False


def test_unblock_refuses_when_it_cannot_tell_whether_the_account_is_blocked(acct, monkeypatch):
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1190.0)
    real = os.stat

    def stat(path, *a, **k):
        if 'safety_block_' in str(path):
            raise PermissionError(13, 'Permission denied')
        return real(path, *a, **k)
    monkeypatch.setattr(os, 'stat', stat)
    assert press(acct, 'unblock') == (False, 'The safety files cannot be read right now. Nothing was changed; try '
                                             'again.')
    assert not (acct / 'safety_restart.json').exists()
    monkeypatch.setattr(os, 'stat', real)
    assert press(acct, 'unblock', now=T0 + 1)[0] is True


def test_off_lets_a_blocked_account_trade_and_on_starts_it_fresh(acct):
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1190.0)
    assert press(acct, 'off') == (True, 'Safety is OFF since 14:07:10 UTC.')
    for v in see((gold, btc), T0 + 5, 1190.0):
        assert v['enabled'] is False and v['blocked'] is False and v['account_blocked'] is True
    assert press(acct, 'unblock', now=T0 + 10)[0] is True            # (the block exists: Unblock still lifts it)
    lose((gold, btc), T0 + 20, 900.0)
    ok, msg = press(acct, 'on', pin='', now=T0 + 60)
    assert ok and msg.startswith('Safety is ON since 14:08:10 UTC.')
    for v in see((gold, btc), T0 + 65, 900.0):
        assert v['enabled'] and v['blocked'] is False and v['drop']['peak'] == 900.0 and v['drop']['pct'] == 0.0


def _folder_in(state, acct):
    """An account folder in one of the states the bar can show, made by real bots and real presses."""
    gold, btc = running(acct)
    if state in ('account blocked', 'off and account blocked', 'both blocks'):
        if state == 'both blocks':
            for i in range(3):
                btc.on_trade_closed(T0 - 500 + i, i, -5.0)
        lose((gold, btc), T0 - 400, 1190.0)
    elif state == 'bot blocked':
        for i in range(3):
            gold.on_trade_closed(T0 - 500 + i, i, -5.0)
        see((gold, btc), T0 - 400, 1500.0)
    elif state == 'other program':
        btc.note_other_program(T0 - 500, 'another program holds 2 trades of its own on BTCUSDm')
        see((gold, btc), T0 - 400, 1500.0)
    if state in ('off', 'off and account blocked'):
        assert press(acct, 'off', now=T0 - 300)[0] is True
        see((gold, btc), T0 - 200, 1190.0 if 'blocked' in state else 1500.0)
    return gold, btc


UNBLOCKED_ACCOUNT = 'Unblocked at 14:07:10 UTC. Counting again from the current balance.'
UNBLOCKED_BOT = ("Unblocked at 14:07:10 UTC: losing trades in a row start again from 0. The account's high and today's "
                 "start are unchanged.")
EVERY_ACTION_FROM_EVERY_STATE = [
    # state                      action     answer                              new id (scope)   switch after
    ('on',                       'unblock', 'Nothing is blocked.',              None,            True),
    ('on',                       'off',     'Safety is OFF since 14:07:10 UTC.', None,           False),
    ('on',                       'on',      'The safety is already ON.',        None,            True),
    ('off',                      'unblock', 'Nothing is blocked.',              None,            False),
    ('off',                      'off',     'The safety is already OFF.',       None,            False),
    ('off',                      'on',      'Safety is ON since 14:07:10 UTC. Counting starts from the current balance.',
     'account', True),
    ('account blocked',          'unblock', UNBLOCKED_ACCOUNT,                  'account',       True),
    ('account blocked',          'off',     'Safety is OFF since 14:07:10 UTC.', None,           False),
    ('account blocked',          'on',      'The safety is already ON.',        None,            True),
    ('bot blocked',              'unblock', UNBLOCKED_BOT,                      'bot',           True),
    ('bot blocked',              'off',     'Safety is OFF since 14:07:10 UTC.', None,           False),
    ('bot blocked',              'on',      'The safety is already ON.',        None,            True),
    ('other program',            'unblock', UNBLOCKED_BOT,                      'bot',           True),
    ('both blocks',              'unblock', UNBLOCKED_ACCOUNT,                  'account',       True),
    ('off and account blocked',  'unblock', UNBLOCKED_ACCOUNT,                  'account',       False),
    ('off and account blocked',  'off',     'The safety is already OFF.',       None,            False),
    ('off and account blocked',  'on',      'Safety is ON since 14:07:10 UTC. Counting starts from the current balance.',
     'account', True),
]


@pytest.mark.parametrize('state, action, answer, new_scope, switch_after', EVERY_ACTION_FROM_EVERY_STATE)
def test_every_action_from_every_state(acct, state, action, answer, new_scope, switch_after):
    gold, btc = _folder_in(state, acct)
    before = S.read_controls(str(acct))
    files = snap(acct)
    assert press(acct, action) == (True, answer)
    after = S.read_controls(str(acct))
    assert after['enabled'] is switch_after
    if new_scope is None:
        assert after['period'] == before['period']                  # no new id: nothing starts counting again
    else:
        assert after['period'] != before['period'] and after['scope'] == new_scope and after['block'] is None
    changed = sorted(n for n, b in snap(acct).items() if files.get(n) != b and n != 'safety_lockout.json')
    expected = set()
    if new_scope is not None:
        expected |= {'safety_restart.json', 'safety_audit.jsonl'}
    if after['enabled'] is not before['enabled']:
        expected |= {'safety_switch.json', 'safety_audit.jsonl'}
    assert changed == sorted(expected)                               # and nothing else was written
    # what the bots make of it, two polls later
    balance = 1190.0 if 'account blocked' in state or state == 'both blocks' else 1500.0
    for v in see((gold, btc), T0 + 5, balance):
        assert v['enabled'] is switch_after and v['period'] == after['period']
        if action == 'unblock' and new_scope or not switch_after or (action == 'on' and new_scope):
            assert v['blocked'] is False
        elif state in ('account blocked', 'both blocks'):
            assert v['blocked'] is True and v['account_blocked'] is True
    if state == 'bot blocked' and action == 'on':
        assert gold.view()['blocked'] is True and gold.view()['bot_blocked'] is True     # ON is no Unblock
        assert btc.view()['blocked'] is False
    if new_scope == 'account':
        assert gold.view()['drop']['peak'] == balance and btc.view()['streak']['count'] == 0
    if new_scope == 'bot':
        assert gold.view()['drop']['peak'] == 1500.0 and gold.view()['started_at'] == T0 - 600


def test_an_unknown_action_changes_nothing(acct):
    before = snap(acct)
    for action in ('toggle', 'ON', '', None, 'unblock ', 5):
        ok, msg = press(acct, action)
        assert ok is False and msg.startswith('Unknown action')
    assert press(acct, 'new-account') == (False, 'This is done on the server only: run "safety.bat new-account" there.')
    assert not differs(snap(acct), before)


def test_press_creates_the_account_folder_and_never_raises(tmp_path, monkeypatch):
    d = tmp_path / 'not' / 'there' / 'acct'
    assert S.press(str(d), 'off', None, 'command line', T0, need_pin=False)[0] is True
    assert d.is_dir() and read(d / 'safety_switch.json')['enabled'] is False
    (tmp_path / 'file').write_text('x')
    ok, msg = S.press(str(tmp_path / 'file' / 'acct'), 'on', None, WEB, T0)
    assert ok is False and 'cannot be used' in msg and 'Nothing was changed' in msg
    def broken(*a, **k):
        raise RuntimeError('a fault nobody expected')
    monkeypatch.setattr(S, '_read_restart', broken)
    ok, msg = S.press(str(d), 'on', None, WEB, T0)
    assert ok is False and msg == 'The safety could not be changed (RuntimeError: a fault nobody expected). Try again.'


def test_press_writes_only_its_own_files(acct):
    gold, btc = running(acct)
    for i in range(3):
        gold.on_trade_closed(T0 - 300 + i, i, -5.0)
    lose((gold, btc), T0 - 200, 1190.0)
    (acct / 'account_claim.json').write_text('{"login_tail": "...5678"}')
    bots_files = {n: b for n, b in snap(acct).items() if n.startswith(('safety_status_', 'safety_block_'))}
    state_files = {p: p.read_bytes() for p in acct.parent.glob('acct_*/state/*')}
    assert len(bots_files) == 3 and len(state_files) == 2
    press(acct, 'unblock', pin='000000')
    press(acct, 'unblock')
    press(acct, 'off', now=T0 + 1)
    press(acct, 'on', now=T0 + 2)
    after = snap(acct)
    for n, b in bots_files.items():
        assert after[n] == b, n                                      # never a bot's status or a block file
    assert not differs({p: p.read_bytes() for p in acct.parent.glob('acct_*/state/*')}, state_files)
    assert after['account_claim.json'] == b'{"login_tail": "...5678"}' and after['safety_pin.txt'] == (PIN + '\n').encode()
    assert sorted(set(after) - set(bots_files)) == ['account_claim.json', 'safety_audit.jsonl', 'safety_lockout.json',
                                                    'safety_pin.txt', 'safety_restart.json', 'safety_switch.json']


# ───────────────────────────── what the page showed: expect ─────────────────────────────

def test_a_page_that_is_not_fresh_changes_nothing(acct):
    changed = 'The safety changed since this page was refreshed. Check the bar and press again.'
    press(acct, 'off', now=T0 - 100)                                 # switched OFF from the other dashboard
    before = {n: b for n, b in snap(acct).items() if n != 'safety_audit.jsonl'}
    stale = {'period': 'start', 'enabled': True}                     # this page still shows ON
    assert press(acct, 'off', expect=stale) == (False, changed)
    assert press(acct, 'on', expect=stale) == (False, changed)       # "ON" on an old page must not act either
    assert press(acct, 'unblock', expect=stale) == (False, changed)
    for odd in ({}, {'period': 'start'}, {'enabled': False}, {'period': 'start', 'enabled': 0},
                {'period': None, 'enabled': False}, 'start', 7, ['start', False]):
        assert press(acct, 'on', expect=odd) == (False, changed), odd
    assert not differs({n: b for n, b in snap(acct).items() if n not in ('safety_audit.jsonl', 'safety_lockout.json')},
                       {n: b for n, b in before.items() if n != 'safety_lockout.json'})
    assert S.read_controls(str(acct))['enabled'] is False
    fresh = {'period': 'start', 'enabled': False}
    assert press(acct, 'on', expect=fresh)[0] is True
    assert press(acct, 'on', expect=fresh) == (False, changed)       # the same request sent twice: once
    refused = [a for a in audit(acct) if a['result'] == 'refused']
    assert len(refused) == 12 and all(a['message'] == changed for a in refused)


def test_the_same_press_twice_changes_the_state_once(acct):
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1190.0)
    seen = {'period': 'start', 'enabled': True}                      # what the bar showed
    assert press(acct, 'unblock', expect=seen)[0] is True
    first = restart_id(acct)
    ok, msg = press(acct, 'unblock', expect=seen, now=T0 + 0.2)      # the browser sent it again
    assert ok is False and msg.startswith('The safety changed since this page was refreshed')
    assert restart_id(acct) == first
    # without an expectation (the command line) the second OFF is simply "already"
    assert S.press(str(acct), 'off', None, 'command line', T0 + 1, need_pin=False)[0] is True
    before = snap(acct)
    assert S.press(str(acct), 'off', None, 'command line', T0 + 2, need_pin=False) == (True, 'The safety is already OFF.')
    assert not differs(snap(acct), before)


CHANGED = 'The safety changed since this page was refreshed. Check the bar and press again.'


def _unchanged(acct, before):
    """Nothing but the audit line and the PIN's count was written."""
    skip = ('safety_audit.jsonl', 'safety_lockout.json')
    return not differs({n: b for n, b in snap(acct).items() if n not in skip},
                       {n: b for n, b in before.items() if n not in skip})


@pytest.mark.parametrize('how', ['block file', 'status only'])
def test_an_unblock_offered_for_one_bot_does_not_lift_a_block_of_the_account_that_came_after(acct, monkeypatch, how):
    """The page showed THIS BOT BLOCKED and its question said "the account's high and today's loss stay". Before the
    press arrives the account is blocked under the same counting (by its block file, or -- the file could not be
    made -- by a bot's status): the press is refused as a stale page's and changes nothing. Offered for the account
    (the page as it is now), it lifts the account block."""
    gold, btc = running(acct)
    for i in range(3):
        gold.on_trade_closed(T0 - 300 + i, i, -5.0)
    see((gold, btc), T0 - 200, 1500.0)
    assert gold.view()['bot_blocked'] and not gold.view()['account_blocked']
    page = {'period': 'start', 'enabled': True, 'scope': 'bot'}          # what the bar offered then
    if how == 'status only':
        real = builtins.open

        def no_block_file(path, mode='r', *a, **k):
            if 'safety_block_' in str(path) and 'x' in mode:
                raise PermissionError(13, 'Permission denied')
            return real(path, mode, *a, **k)
        monkeypatch.setattr(S, 'open', no_block_file, raising=False)
    lose((gold, btc), T0 - 100, 1190.0)                              # 20.7 % down: the account is blocked
    assert (acct / 'safety_block_start.json').exists() is (how == 'block file')
    assert read(acct / 'safety_status_acct_x9.json')['account_blocked'] is True
    before = snap(acct)
    assert press(acct, 'unblock', expect=page) == (False, CHANGED)
    assert _unchanged(acct, before) and not (acct / 'safety_restart.json').exists()
    assert see((gold,), T0 - 50, 1190.0)[0]['account_blocked'] is True
    ok, msg = press(acct, 'unblock', expect=dict(page, scope='account'))
    assert ok and msg == 'Unblocked at 14:07:10 UTC. Counting again from the current balance.'
    assert read(acct / 'safety_restart.json')['scope'] == 'account'


def test_an_unblock_offered_for_the_account_is_refused_once_no_account_block_is_left(acct):
    """The page showed ACCOUNT BLOCKED and asked about the whole account. By the press nothing blocks the account
    under this counting any more (here: only one bot's own block is left): refused, nothing written -- never a
    different unblock than the one confirmed, and never "Nothing is blocked" for a page that showed a block."""
    (acct / 'safety_status_acct_x9.json').write_text(json.dumps(
        {'branch': GOLD, 'period': 'start', 'bot_blocked': True, 'account_blocked': False}), encoding='utf-8')
    page = {'period': 'start', 'enabled': True, 'scope': 'account'}
    before = snap(acct)
    assert press(acct, 'unblock', expect=page) == (False, CHANGED)
    assert _unchanged(acct, before)
    (acct / 'safety_status_acct_x9.json').unlink()                   # nothing blocked at all
    assert press(acct, 'unblock', expect=page) == (False, CHANGED)
    assert not (acct / 'safety_restart.json').exists()


def test_without_a_scope_or_with_the_one_the_files_show_unblock_is_as_before(acct):
    """The command line sends no expectation, a page of before this rule sends no scope, and the bar's 'scope' None
    offers no Unblock: what the files show decides, as before."""
    for i, scope in enumerate(('not sent', None, 'bot')):           # ('bot': offered for that bot, as the files say)
        current = restart_id(acct)
        (acct / 'safety_status_acct_x9.json').write_text(json.dumps(
            {'branch': GOLD, 'period': current, 'bot_blocked': True}), encoding='utf-8')
        expect = {'period': current, 'enabled': True}
        if scope != 'not sent':
            expect['scope'] = scope
        ok, msg = press(acct, 'unblock', now=T0 + i, expect=expect)
        assert ok and msg == (f"Unblocked at 14:07:1{i} UTC: losing trades in a row start again from 0. The account's "
                              "high and today's start are unchanged."), scope
        assert read(acct / 'safety_restart.json')['scope'] == 'bot' and restart_id(acct) != current
    # the scope is Unblock's alone: OFF goes by the switch
    assert press(acct, 'off', now=T0 + 5, expect={'period': restart_id(acct), 'enabled': True, 'scope': 'account'}) \
        == (True, 'Safety is OFF since 14:07:15 UTC.')


def test_on_while_on_does_not_unblock(acct):
    """'on' needs no PIN: if it started afresh while already ON, anybody who reaches the port could lift a block."""
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1190.0)
    before = snap(acct)
    for i in range(30):
        assert press(acct, 'on', pin=None, now=T0 + i) == (True, 'The safety is already ON.')
    assert not differs(snap(acct), before) and not (acct / 'safety_restart.json').exists()
    assert see((gold,), T0 + 40, 1190.0)[0]['blocked'] is True


# ───────────────────────────── a restart file that cannot be read ─────────────────────────────

DAMAGED = [b'', b'{"id": "2026', b'{"id": "a/b"}', b'[]', b'\xff\xfe\x00\x00',
           '{"id": "20261121_140500-a1b2c3", "scope": "account"}'.encode('utf-16')]     # (saved as UTF-16 in Notepad)
RESTART_UNREADABLE = ('The safety files cannot be read right now. Nothing was changed; try again. If this answer '
                      'stays, run "safety.bat unblock" on the server: it writes safety_restart.json anew, and both '
                      'bots count again from the current balance.')


@pytest.mark.parametrize('content', DAMAGED)
@pytest.mark.parametrize('action', ['unblock', 'off', 'on'])
def test_an_unreadable_restart_file_writes_nothing_from_the_page_and_its_answer_says_the_way_out(acct, content,
                                                                                               action):
    (acct / 'safety_restart.json').write_bytes(content)
    (acct / 'safety_block_start.json').write_text('{}')
    before = snap(acct)
    assert press(acct, action) == (False, RESTART_UNREADABLE)
    if action == 'off':                                              # the command line's OFF does not need that file
        assert S.press(str(acct), action, None, 'command line', T0, need_pin=False) == (False, RESTART_UNREADABLE)
    after = snap(acct)
    assert not differs({n: b for n, b in after.items() if n not in ('safety_audit.jsonl', 'safety_lockout.json')}, before)
    assert [a['result'] for a in audit(acct)] == ['refused'] * (2 if action == 'off' else 1)


@pytest.mark.parametrize('content', DAMAGED)
def test_safety_bat_unblock_writes_a_damaged_restart_file_anew_and_says_so(acct, content):
    """The bots keep counting under the id they had while the file cannot be read, so a block stays and the page
    can lift nothing. "safety.bat unblock" on the server writes the file anew: a new id, scope account -- a fresh start
    of the whole account, as every unblock from the command line is -- and both bots take it."""
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1190.0)                              # 20.7 % down: the account is blocked
    (acct / 'safety_restart.json').write_bytes(content)
    assert see((gold, btc), T0 - 300, 1190.0)[0]['blocked'] is True  # (the bots keep the id they had: blocked)
    assert press(acct, 'unblock')[1] == RESTART_UNREADABLE           # the page: nothing, and the way out
    ok, msg = S.press(str(acct), 'unblock', None, 'command line', T0, need_pin=False)
    assert ok and msg == ('safety_restart.json could not be read, so it was written anew. Unblocked at 14:07:10 UTC. '
                          'Counting again from the current balance.')
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'account' and r['account_id'] == r['id'] and r['id'] != 'start' and r['by'] == 'command line'
    for v in see((gold, btc), T0 + 5, 1190.0):
        assert v['blocked'] is False and v['period'] == r['id'] and v['drop']['peak'] == 1190.0
    done = [a for a in audit(acct) if a.get('result') == 'done']
    assert done[-1]['repaired'] == 'safety_restart.json' and done[-1]['was'] == {'id': None, 'enabled': True}


@pytest.mark.parametrize('switch', ['on', 'off'])
def test_safety_bat_on_writes_a_damaged_restart_file_anew_too(acct, switch):
    if switch == 'off':
        press(acct, 'off', now=T0 - 60)
    (acct / 'safety_restart.json').write_bytes(b'{"id": "2026')
    ok, msg = S.press(str(acct), 'on', None, 'command line', T0, need_pin=False)
    if switch == 'on':
        assert ok and msg == ('safety_restart.json could not be read, so it was written anew. The safety is ON; '
                              'counting starts again from the current balance.')
    else:
        assert ok and msg == ('safety_restart.json could not be read, so it was written anew. Safety is ON since '
                              '14:07:10 UTC. Counting starts from the current balance.')
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'account' and r['id'] != 'start' and S.read_controls(str(acct))['enabled'] is True
    # the file is whole again: the next press is an ordinary one
    assert S.press(str(acct), 'on', None, 'command line', T0 + 1, need_pin=False) == (True, 'The safety is already ON.')
    assert main_says(acct, 'unblock', T0 + 2)[0] == 0


def main_says(acct, command, now):
    """safety.bat <command>, as the command line runs it: (exit code, what it printed)."""
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = S.main([command, '--account-dir', str(acct)], now=now)
    return code, out.getvalue()


def test_safety_bat_unblock_through_main_repairs_and_exits_0(acct):
    (acct / 'safety_restart.json').write_bytes('{"id": "x"}'.encode('utf-16'))
    code, said = main_says(acct, 'unblock', T0)
    assert code == 0 and said.startswith('safety_restart.json could not be read, so it was written anew. Unblocked at')
    code, said = main_says(acct, 'off', T0 + 1)
    assert code == 0 and said.startswith('Safety is OFF since')


def test_a_restart_or_switch_file_held_by_another_program_writes_nothing(acct, monkeypatch):
    press(acct, 'off', now=T0 - 50)
    press(acct, 'on', pin=None, now=T0 - 40)
    before = snap(acct)
    real = builtins.open
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)
    for held in ('safety_restart.json', 'safety_switch.json'):
        tries = []

        def fake(path, mode='r', *a, _held=held, **k):
            if str(path).endswith(_held) and 'r' in mode:
                tries.append(mode)
                raise PermissionError(13, 'Permission denied')
            return real(path, mode, *a, **k)
        monkeypatch.setattr(S, 'open', fake, raising=False)
        for action in ('unblock', 'off', 'on'):
            assert press(acct, action)[1] == ('The safety files cannot be read right now. Nothing was changed; try '
                                              'again.' if held == 'safety_switch.json' else RESTART_UNREADABLE)
        assert len(tries) == 12                                      # each press tried 4 times before giving up
        monkeypatch.delattr(S, 'open')
    after = snap(acct)
    for n in ('safety_restart.json', 'safety_switch.json', 'safety_pin.txt'):
        assert after[n] == before[n]


def test_a_file_that_cannot_be_written_is_said_and_leaves_the_old_one_whole(acct, monkeypatch):
    press(acct, 'off', now=T0 - 50)
    before = snap(acct)

    def refuse(src, dst, *a, **k):
        raise PermissionError(13, 'Permission denied')
    monkeypatch.setattr(S, '_replace_retry', refuse)
    ok, msg = S.press(str(acct), 'on', None, 'command line', T0, need_pin=False)
    assert ok is False and msg.startswith('The safety files cannot be written right now. Nothing was changed; try again.')
    assert 'PermissionError' in msg
    ok, msg = S.press(str(acct), 'unblock', None, 'command line', T0, need_pin=False)
    assert ok is False and msg.startswith('The safety files cannot be written right now.')
    ok, msg = press(acct, 'unblock')                                 # with the PIN: its try cannot even be counted
    assert (ok, msg) == (False, 'The safety files cannot be written right now. Nothing was changed; try again.')
    after = snap(acct)
    assert not differs({n: b for n, b in after.items() if n != 'safety_audit.jsonl'},
                       {n: b for n, b in before.items() if n != 'safety_audit.jsonl'})
    assert not [n for n in after if n.endswith('.tmp')]


def test_on_writes_the_new_id_first_so_a_failure_between_the_two_files_leaves_the_safety_off(acct, monkeypatch):
    press(acct, 'off', now=T0 - 50)
    real = S._replace_retry
    order = []

    def replace(src, dst, *a, **k):
        order.append(os.path.basename(dst))
        if dst.endswith('safety_switch.json'):
            raise PermissionError(13, 'Permission denied')           # the crash point: after the id, before the switch
        return real(src, dst, *a, **k)
    monkeypatch.setattr(S, '_replace_retry', replace)
    ok, msg = press(acct, 'on', pin=None)
    assert order[:2] == ['safety_restart.json', 'safety_switch.json']
    assert ok is False and msg.startswith('The safety is still OFF: its switch file cannot be written right now')
    c = S.read_controls(str(acct))
    assert c['enabled'] is False and c['period'] != 'start'          # OFF with a fresh start, never ON on the old high
    monkeypatch.setattr(S, '_replace_retry', real)
    assert press(acct, 'on', pin=None, now=T0 + 5)[0] is True and S.read_controls(str(acct))['enabled'] is True


# ───────────────────────────── the PIN ─────────────────────────────

def test_a_right_pin_and_a_wrong_pin(acct):
    assert press(acct, 'off', pin='000000') == (False, 'Wrong PIN. 4 more tries, then the buttons lock for 10 minutes.')
    assert not (acct / 'safety_switch.json').exists()
    assert lockout(acct)['wrong'] == 1 and lockout(acct)['last_wrong_at'] == T0
    assert press(acct, 'unblock', pin='482914', now=T0 + 1)[1] == \
        'Wrong PIN. 3 more tries, then the buttons lock for 10 minutes.'
    assert press(acct, 'off', pin='48291', now=T0 + 2)[1].startswith('Wrong PIN. 2 more tries')
    assert press(acct, 'off', pin='4829133', now=T0 + 3)[1] == \
        'Wrong PIN. 1 more try, then the buttons lock for 10 minutes.'
    assert press(acct, 'off', pin=f'  {PIN}\n', now=T0 + 4) == (True, 'Safety is OFF since 14:07:14 UTC.')
    assert lockout(acct)['wrong'] == 0                               # a right PIN: the count starts again
    assert press(acct, 'unblock', pin='1', now=T0 + 5)[1].startswith('Wrong PIN. 4 more tries')
    lines = audit(acct)
    assert [a['result'] for a in lines] == ['refused'] * 4 + ['done', 'refused']
    text = (acct / 'safety_audit.jsonl').read_text() + (acct / 'safety_lockout.json').read_text()
    for typed in ('000000', '482914', '4829133', PIN):
        assert not found(text, typed)                                     # never a PIN, right or wrong, in a file


def test_five_wrong_pins_lock_the_buttons_for_ten_minutes_and_a_locked_press_is_not_compared(acct, monkeypatch):
    for i in range(4):
        press(acct, 'off', pin='x' * 6, now=T0 + i)
    ok, msg = press(acct, 'off', pin='y' * 6, now=T0 + 4)
    assert (ok, msg) == (False, 'Wrong PIN. Too many wrong PINs: the buttons are locked until 14:17 UTC. On the '
                                'server, "safety.bat unblock" (or on, off) works without the PIN.')
    rec = lockout(acct)
    assert rec['locked_until'] == T0 + 4 + 600 and rec['wrong'] == 0 and rec['lock_s'] == 1200.0
    assert S.read_controls(str(acct))['locked_until'] == T0 + 604
    compared = []
    real = S.hmac.compare_digest
    monkeypatch.setattr(S.hmac, 'compare_digest', lambda a, b: (compared.append(1), real(a, b))[1])
    locked = (False, 'Too many wrong PINs: the buttons are locked until 14:17 UTC. On the server, "safety.bat '
                     'unblock" (or on, off) works without the PIN.')
    assert press(acct, 'off', pin=PIN, now=T0 + 10) == locked        # even the right PIN: nothing is compared
    assert press(acct, 'unblock', pin=PIN, now=T0 + 603.9) == locked
    assert compared == [] and not (acct / 'safety_switch.json').exists()
    assert lockout(acct)['wrong'] == 0                               # ...and nothing is counted while locked
    assert press(acct, 'off', pin=PIN, now=T0 + 604) == (True, 'Safety is OFF since 14:17:14 UTC.')
    assert compared == [1]
    assert lockout(acct)['lock_s'] == 600.0 and lockout(acct)['locked_until'] == 0.0


def test_each_further_lock_is_twice_as_long_up_to_24_hours(acct):
    now = T0
    lengths = []
    for round_ in range(10):
        for i in range(5):
            ok, msg = press(acct, 'off', pin='nope', now=now + i)
        rec = lockout(acct)
        lengths.append(rec['locked_until'] - (now + 4))
        assert 'locked until' in msg
        if round_ == 1:
            assert press(acct, 'off', pin='nope', now=now + 3)[1].startswith('Too many wrong PINs')
        now = rec['locked_until'] + 1                                # try again as soon as the lock ends
        if round_ < 9:
            warn = press(acct, 'off', pin='nope', now=now)[1]        # the warning names the length of the next lock
            now += 1
            for i in range(4):
                msg = press(acct, 'off', pin='nope', now=now + i)[1]
            rec = lockout(acct)
            lengths.append(rec['locked_until'] - (now + 3))
            now = rec['locked_until'] + 1
            assert warn.endswith(f'then the buttons lock for {S._length(lengths[-1])}.')
    assert lengths[:9] == [600.0, 1200.0, 2400.0, 4800.0, 9600.0, 19200.0, 38400.0, 76800.0, 86400.0]
    assert set(lengths[9:]) == {86400.0}                             # never longer than a day
    assert 'until 2' in msg or 'Nov' in msg or 'Dec' in msg          # a lock that ends on another day says the day


def test_a_lock_that_ends_on_another_day_names_the_day(acct):
    (acct / 'safety_lockout.json').write_text(json.dumps({'wrong': 4, 'lock_s': 86400.0, 'last_wrong_at': T0 - 5}))
    ok, msg = press(acct, 'off', pin='nope')
    assert msg == ('Wrong PIN. Too many wrong PINs: the buttons are locked until 22 Nov 14:07 UTC. On the server, '
                   '"safety.bat unblock" (or on, off) works without the PIN.')
    assert press(acct, 'off', pin=PIN, now=T0 + 60)[1].startswith('Too many wrong PINs: the buttons are locked until '
                                                                  '22 Nov 14:07 UTC.')


def test_a_right_pin_and_24_quiet_hours_set_the_lock_length_back(acct):
    for i in range(5):
        press(acct, 'off', pin='nope', now=T0 + i)
    assert lockout(acct)['lock_s'] == 1200.0                         # the next lock would be 20 minutes
    later = T0 + 700
    assert press(acct, 'off', pin='nope', now=later)[1] == 'Wrong PIN. 4 more tries, then the buttons lock for 20 minutes.'
    # 24 hours without a wrong PIN: the length is 10 minutes again (the tries in a row are still counted)
    ok, msg = press(acct, 'off', pin='nope', now=later + 86400)
    assert msg == 'Wrong PIN. 3 more tries, then the buttons lock for 10 minutes.'
    assert lockout(acct)['lock_s'] == 600.0 and lockout(acct)['wrong'] == 2
    for i in range(3):
        press(acct, 'off', pin='nope', now=later + 86401 + i)
    assert lockout(acct)['lock_s'] == 1200.0
    after_lock = lockout(acct)['locked_until'] + 1
    assert press(acct, 'off', pin=PIN, now=after_lock)[0] is True    # a right PIN: count and length back to the start
    assert lockout(acct)['lock_s'] == 600.0 and lockout(acct)['wrong'] == 0


def test_on_needs_no_pin_and_ignores_the_lock(acct):
    press(acct, 'off')
    for i in range(5):
        press(acct, 'unblock', pin='nope', now=T0 + 1 + i)
    assert press(acct, 'off', now=T0 + 10)[1].startswith('Too many wrong PINs')
    before = lockout(acct)
    for pin in (None, '', 'whatever', 123):
        press(acct, 'off', pin=PIN, now=T0 + 700 + len(str(pin)))    # (OFF again once the lock is over)
        ok, msg = press(acct, 'on', pin=pin, now=T0 + 20 if pin is None else T0 + 800)
        assert ok is True, pin
    # while locked: ON works, and it neither counts nor clears anything
    press(acct, 'off', pin=PIN, now=T0 + 900)
    for i in range(5):
        press(acct, 'unblock', pin='nope', now=T0 + 901 + i)
    locked = lockout(acct)
    assert locked['locked_until'] > T0 + 1000
    assert press(acct, 'on', pin=None, now=T0 + 1000) == (
        True, 'Safety is ON since 14:23:50 UTC. Counting starts from the current balance.')
    after = lockout(acct)
    assert after['locked_until'] == locked['locked_until'] and after['wrong'] == locked['wrong']
    assert before['locked_until'] > 0


def test_an_empty_pin_is_not_a_try(acct):
    before = snap(acct)
    msg = f'Type the PIN first. It is in the file safety_pin.txt in {acct} on the server.'
    for nothing in ('', '   ', None, 0, b'482913', ['482913']):
        assert press(acct, 'off', pin=nothing) == (False, msg)
        assert press(acct, 'unblock', pin=nothing) == (False, msg)
    assert not differs(snap(acct), before)                                      # not counted, not audited


@pytest.mark.parametrize('raw', [b'\xef\xbb\xbf482913', b'\xef\xbb\xbf482913\r\n', b'482913\r\n', b'  482913  \n\n',
                                 b'\t482913'])
def test_a_pin_file_with_a_byte_order_mark_or_line_ends_is_the_same_pin(acct, raw):
    (acct / 'safety_pin.txt').write_bytes(raw)                       # Notepad's "UTF-8 with BOM", Windows line ends
    assert S.read_controls(str(acct))['pin_set'] is True
    assert press(acct, 'off') == (True, 'Safety is OFF since 14:07:10 UTC.')
    assert press(acct, 'unblock', pin='482913x', now=T0 + 1)[1].startswith('Wrong PIN')


@pytest.mark.parametrize('raw', [b'', b'\n', b'123', b'12 34 56', b'1234\n5678', '482913'.encode('utf-16'),
                                 '482913'.encode('utf-16-le'), 'geheim\u00e4'.encode('utf-8'), b'\xff\xfe\xfd',
                                 b'x' * 33, b'pin\x00pin'])
def test_a_pin_file_that_holds_no_usable_pin_refuses_without_counting(acct, raw):
    (acct / 'safety_pin.txt').write_bytes(raw)
    assert S.read_controls(str(acct))['pin_set'] is False
    msg = (f'The PIN file cannot be used: open safety_pin.txt in {acct} in Notepad, keep only letters and digits, '
           'save as UTF-8.')
    typed = raw.decode('utf-8', 'ignore').strip() or 'anything'
    for i in range(7):                                               # more than 5: this never locks
        assert press(acct, 'off', pin=typed, now=T0 + i) == (False, msg)
    assert not (acct / 'safety_switch.json').exists()
    rec = lockout(acct)
    assert rec['wrong'] == 0 and rec['locked_until'] == 0.0
    assert press(acct, 'on', pin=None)[1] == 'The safety is already ON.'     # ON needs none
    assert S.press(str(acct), 'off', None, 'command line', T0 + 9, need_pin=False)[0] is True


def test_valid_pins_are_4_to_32_printable_characters_without_spaces():
    for good in ('1234', '482913', 'a' * 32, 'Gold-2026!', '~!@#$%^&*()_+'):
        assert S._valid_pin(good), good
    for bad in ('', '123', 'a' * 33, '12 34', 'tab\tpin', 'line\npin', 'geheim\u00e4', None, 1234, b'1234'):
        assert not S._valid_pin(bad), bad


def test_without_a_pin_file_the_buttons_say_how_to_get_one(tmp_path):
    d = tmp_path / 'acct'
    ok, msg = S.press(str(d), 'off', '123456', WEB, T0)
    assert ok is False and msg == (f'There is no PIN yet: start the dashboard once on the server (it makes '
                                   f'safety_pin.txt in {d}), or make that file in Notepad with 4 to 32 letters and '
                                   'digits.')
    assert not (d / 'safety_switch.json').exists() and lockout(d)['wrong'] == 0
    S.ensure_pin(str(d))
    made = (d / 'safety_pin.txt').read_text().strip()
    assert S.press(str(d), 'off', made, WEB, T0 + 1) == (True, 'Safety is OFF since 14:07:11 UTC.')


def test_a_lockout_file_that_is_damaged_is_an_empty_record_and_one_that_is_held_refuses(acct, monkeypatch):
    (acct / 'safety_lockout.json').write_bytes(b'{"wrong": 4, "locked_un')
    assert press(acct, 'off', pin='nope')[1] == 'Wrong PIN. 4 more tries, then the buttons lock for 10 minutes.'
    (acct / 'safety_lockout.json').write_text('{"wrong": "many", "locked_until": "soon", "lock_s": -5}')
    assert press(acct, 'off', pin='nope', now=T0 + 1)[1].startswith('Wrong PIN. 4 more tries, then the buttons lock '
                                                                    'for 10 minutes')
    real = builtins.open
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)

    def held(path, mode='r', *a, **k):
        if str(path).endswith('safety_lockout.json') and 'r' in mode:
            raise PermissionError(13, 'Permission denied')
        return real(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', held, raising=False)
    # the count cannot be read: no comparison, not even of the right PIN
    assert press(acct, 'off', pin=PIN, now=T0 + 2) == (
        False, 'The safety files cannot be read right now. Nothing was changed; try again.')
    assert not (acct / 'safety_switch.json').exists()


def test_parallel_wrong_pins_from_threads_are_each_counted(acct, monkeypatch):
    """The dashboard answers each request in its own thread. Without the lock in press() ten requests sent in the
    same instant would all read 'no wrong PIN yet' and each get a free guess."""
    real = S._write_lockout

    def slow_write(folder, record, **kw):
        time.sleep(0.002)                                            # widen the window a race would need
        return real(folder, record, **kw)
    monkeypatch.setattr(S, '_write_lockout', slow_write)
    gate = threading.Barrier(4)
    answers = []

    def guess(i):
        gate.wait()
        answers.append(press(acct, 'off', pin=f'{i:06d}', now=T0 + i * 0.001)[1])
    threads = [threading.Thread(target=guess, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert lockout(acct)['wrong'] == 4
    assert sorted(a.split('.')[1].strip() for a in answers) == ['1 more try, then the buttons lock for 10 minutes',
                                                               '2 more tries, then the buttons lock for 10 minutes',
                                                               '3 more tries, then the buttons lock for 10 minutes',
                                                               '4 more tries, then the buttons lock for 10 minutes']
    # twelve more at once, one of them with the right PIN but after the fifth wrong one: at most one more guess
    gate = threading.Barrier(12)
    del answers[:]
    threads = [threading.Thread(target=guess, args=(100 + i,)) for i in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len([a for a in answers if a.startswith('Wrong PIN')]) == 1       # the fifth: it locks
    assert len([a for a in answers if a.startswith('Too many wrong PINs')]) == 11
    assert not (acct / 'safety_switch.json').exists()


# ───────────────────────────── the audit file ─────────────────────────────

def test_accepted_presses_are_always_in_the_audit_file(acct):
    for i in range(40):                                              # 40 real changes within one hour
        assert press(acct, 'off' if i % 2 == 0 else 'on', now=T0 + i)[0] is True
    lines = audit(acct)
    assert len(lines) == 40 and all(a['result'] == 'done' for a in lines)
    assert [a['action'] for a in lines[:4]] == ['off', 'on', 'off', 'on']
    assert all(a['by'] == WEB and 't' in a and 'message' in a and 'was' in a for a in lines)
    assert all('id' in a and a['scope'] == 'account' for a in lines if a['action'] == 'on')


def test_refused_presses_are_capped_at_20_lines_an_hour_then_counted(acct):
    hour0 = (T0 // HOUR) * HOUR + HOUR                               # the start of the next full hour: 15:00
    changed = {'period': 'another', 'enabled': True}
    for i in range(75):
        assert press(acct, 'on', pin=None, now=hour0 + i, expect=changed)[0] is False
    assert len(audit(acct)) == 20 and all(a['result'] == 'refused' for a in audit(acct))
    rec = lockout(acct)
    assert rec['refused_lines'] == 20 and rec['refused_more'] == 55
    size = (acct / 'safety_audit.jsonl').stat().st_size
    for i in range(300):                                             # a flood: the file does not grow
        press(acct, 'on', pin=None, now=hour0 + 100 + i, expect=changed)
    assert (acct / 'safety_audit.jsonl').stat().st_size == size and lockout(acct)['refused_more'] == 355
    press(acct, 'on', pin=None, now=hour0 + HOUR + 5, expect=changed)        # the next hour: one line says how many
    lines = audit(acct)
    assert len(lines) == 22 and lines[20] == {'at': S._iso(hour0 + HOUR + 5), 'refused_more': 355,
                                              'in_the_hour_from': S._iso(hour0)}
    assert lines[21]['result'] == 'refused' and lockout(acct)['refused_lines'] == 1
    assert lockout(acct)['refused_more'] == 0
    # wrong PINs are refused presses too, under the same cap; an accepted press is always written
    for i in range(30):
        press(acct, 'off', pin='nope', now=hour0 + HOUR + 10 + i)
    assert len(audit(acct)) == 21 + 20
    assert S.press(str(acct), 'off', None, 'command line', hour0 + HOUR + 60, need_pin=False)[0] is True
    assert audit(acct)[-1]['result'] == 'done' and audit(acct)[-1]['by'] == 'command line'
    assert not found((acct / 'safety_audit.jsonl').read_text(), PIN)


def test_an_accepted_press_of_a_later_hour_also_writes_the_count_of_the_refused_ones(acct):
    hour0 = (T0 // HOUR) * HOUR + HOUR
    for i in range(25):
        press(acct, 'on', pin=None, now=hour0 + i, expect={'period': 'x', 'enabled': True})
    assert press(acct, 'off', now=hour0 + 3 * HOUR)[0] is True
    lines = audit(acct)
    assert lines[-2]['refused_more'] == 5 and lines[-1]['result'] == 'done' and len(lines) == 22


def test_an_audit_file_that_cannot_be_written_does_not_stop_a_press(acct, monkeypatch):
    real = builtins.open

    def no_audit(path, mode='r', *a, **k):
        if str(path).endswith('safety_audit.jsonl'):
            raise PermissionError(13, 'Permission denied')
        return real(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', no_audit, raising=False)
    assert press(acct, 'off') == (True, 'Safety is OFF since 14:07:10 UTC.')
    assert press(acct, 'off', pin='nope', now=T0 + 1)[1].startswith('Wrong PIN')
    assert read(acct / 'safety_switch.json')['enabled'] is False


# ───────────────────────────── the command line: need_pin=False ─────────────────────────────

def test_the_command_line_needs_no_pin_ignores_the_lock_and_always_unblocks(acct):
    for i in range(5):
        press(acct, 'off', pin='nope', now=T0 - 100 + i)             # the buttons are locked
    (acct / 'safety_pin.txt').unlink()                               # and there is no PIN at all
    cli = lambda action, now: S.press(str(acct), action, None, 'command line', now, need_pin=False)   # noqa: E731
    ok, msg = cli('unblock', T0)                                     # nothing is blocked: it still starts afresh
    assert (ok, msg) == (True, 'Unblocked at 14:07:10 UTC. Counting again from the current balance.')
    r1 = read(acct / 'safety_restart.json')
    assert r1['scope'] == 'account' and r1['why'] == 'unblock from the command line' and r1['by'] == 'command line'
    ok, msg = cli('unblock', T0 + 1)                                 # every time
    r2 = read(acct / 'safety_restart.json')
    assert ok and r2['id'] != r1['id'] and r2['id'].startswith('20261121_140711-')
    assert cli('off', T0 + 2) == (True, 'Safety is OFF since 14:07:12 UTC.')
    assert cli('off', T0 + 3) == (True, 'The safety is already OFF.')
    assert cli('on', T0 + 4)[0] is True and cli('on', T0 + 5) == (True, 'The safety is already ON.')
    assert [a['by'] for a in audit(acct) if a['result'] == 'done'] == ['command line'] * 4
    assert lockout(acct)['locked_until'] > T0                        # the lock of the page is not its business


def test_one_command_on_the_server_clears_a_block_of_one_bot_too(acct):
    gold, btc = running(acct)
    for i in range(3):
        gold.on_trade_closed(T0 - 300 + i, i, -5.0)
    see((gold, btc), T0 - 200, 1400.0)
    assert gold.view()['bot_blocked']
    assert S.press(str(acct), 'unblock', None, 'command line', T0, need_pin=False)[0] is True
    assert read(acct / 'safety_restart.json')['scope'] == 'account'
    for v in see((gold, btc), T0 + 5, 1400.0):
        assert v['blocked'] is False and v['streak']['count'] == 0 and v['drop']['peak'] == 1400.0


def test_new_account_removes_the_claim_and_starts_afresh_from_the_command_line_only(acct):
    (acct / 'account_claim.json').write_text('{"login_tail": "...5678"}')
    before = snap(acct)
    assert press(acct, 'new-account') == (False, 'This is done on the server only: run "safety.bat new-account" there.')
    assert not differs(snap(acct), before)
    ok, msg = S.press(str(acct), 'new-account', None, 'command line', T0, need_pin=False)
    assert ok and msg == ('The account of this folder was cleared at 14:07:10 UTC. The first bot that starts sets the '
                          'new account, and counting starts from its balance.')
    assert not (acct / 'account_claim.json').exists()
    r = read(acct / 'safety_restart.json')
    assert r['scope'] == 'account' and r['why'] == 'new-account' and r['account_id'] == r['id']
    ok, msg = S.press(str(acct), 'new-account', None, 'command line', T0 + 5, need_pin=False)       # no claim: fine
    assert ok and read(acct / 'safety_restart.json')['id'] != r['id']
    assert [a['action'] for a in audit(acct)] == ['new-account', 'new-account']


def test_new_account_changes_nothing_when_the_claim_cannot_be_removed(acct, monkeypatch):
    (acct / 'account_claim.json').write_text('{}')
    real = os.remove

    def remove(path, *a, **k):
        if str(path).endswith('account_claim.json'):
            raise PermissionError(13, 'Permission denied')           # a running bot holds it
        return real(path, *a, **k)
    monkeypatch.setattr(os, 'remove', remove)
    ok, msg = S.press(str(acct), 'new-account', None, 'command line', T0, need_pin=False)
    assert ok is False and msg.startswith('The safety files cannot be written right now.')
    assert (acct / 'account_claim.json').exists() and not (acct / 'safety_restart.json').exists()


def test_fresh_start_ids_are_the_time_and_six_random_hex_digits(acct):
    ids = []
    for i in range(300):
        S.press(str(acct), 'unblock', None, 'command line', T0, need_pin=False)      # all in the same second
        ids.append(restart_id(acct))
    assert all(a != b for a, b in zip(ids, ids[1:]))                 # every press is another id than the one before
    assert len(set(ids)) >= 298                                      # (300 draws of 16 million: a repeat is rare)
    for one in ids:
        assert S._ID_OK.match(one) and one.startswith('20261121_140710-') and len(one) == 22 and one != 'start'
        assert S.block_path(str(acct), one).endswith(f'safety_block_{one}.json')


def test_a_new_id_is_never_the_one_in_use_and_never_one_that_has_a_block_file(acct, monkeypatch):
    """Two presses in the same second can draw the same six digits. The second must not write the id that is in
    use (the bots would see no press at all), nor an id under which a block file waits (an old block would block
    the new start)."""
    draws = iter(['aaaaaa',                                          # the first press
                  'aaaaaa', 'bbbbbb',                                # the second: the id in use, then a free one
                  'cccccc', 'bbbbbb', 'dddddd'])                     # the third: one with a block file, the one in use
    monkeypatch.setattr(S, '_new_id', lambda now: f'{S._name_stamp(now)}-{next(draws)}')
    cli = lambda: S.press(str(acct), 'unblock', None, 'command line', T0, need_pin=False)     # noqa: E731
    assert cli()[0] and restart_id(acct) == '20261121_140710-aaaaaa'
    assert cli()[0] and restart_id(acct) == '20261121_140710-bbbbbb'
    (acct / 'safety_block_20261121_140710-cccccc.json').write_text('{}')
    assert cli()[0] and restart_id(acct) == '20261121_140710-dddddd'
    assert S.read_controls(str(acct))['block'] is None


def test_the_id_of_the_last_account_start_is_carried_through_unblocks_of_one_bot(acct):
    gold, btc = running(acct)
    S.press(str(acct), 'unblock', None, 'command line', T0, need_pin=False)
    account_id = restart_id(acct)
    see((gold, btc), T0 + 5, 1500.0)
    for round_ in range(2):
        for i in range(3):
            gold.on_trade_closed(T0 + 100 * (round_ + 1) + i, f'{round_}-{i}', -5.0)
        see((gold, btc), T0 + 100 * (round_ + 1) + 10, 1500.0)
        assert press(acct, 'unblock', now=T0 + 100 * (round_ + 1) + 20)[0] is True
        r = read(acct / 'safety_restart.json')
        assert r['scope'] == 'bot' and r['account_id'] == account_id and r['id'] != account_id
        g = see((gold, btc), T0 + 100 * (round_ + 1) + 30, 1500.0)[0]
        assert g['blocked'] is False and g['started_at'] == T0 + 6   # the account's figures were not started again


# ───────────────────────────── the command line itself: main() ─────────────────────────────

def test_main_status_of_an_account_that_was_never_used(tmp_path, capsys):
    d = tmp_path / 'acct'
    assert S.main(['status', '--account-dir', str(d)], now=T0) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [f'Account folder: {d}',
                   'It is not there yet: no bot or dashboard of this account has started on this server.']
    assert not d.exists()                                            # status creates nothing


def test_main_status_says_the_switch_the_blocks_and_each_bot_with_its_age(acct, capsys):
    gold, btc = running(acct, now=T0 - 600)
    for i in range(3):
        btc.on_trade_closed(T0 - 500 + i, i, -5.0)
    lose((gold, btc), T0 - 400, 1190.0)
    tick(gold, T0 - 3, 1190.0)                                       # gold still runs; the BTC bot stopped 396 s ago
    assert S.main(['status', f'--account-dir={acct}'], now=T0) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == f'Account folder: {acct}'
    assert lines[1] == 'Safety: ON (nobody has switched it yet).'
    assert lines[2] == "Counting: from each bot's first start (nobody has pressed Unblock or ON yet)."
    assert lines[3].startswith('ACCOUNT BLOCKED since 21 Nov 14:00 UTC. The account fell 20.7% below its high '
                               '(limit 20%): balance $1,190.00, high $1,500.00 on 21 Nov.')
    assert lines[3].endswith('bot (acct_x9) saw it.') or lines[3].endswith('bot (acct_b9) saw it.')
    assert lines[4] == f"PIN of the buttons: set, file {acct / 'safety_pin.txt'}"
    assert 'The BTC bot (acct_b9): NOT RUNNING: last seen 6 minutes ago (21 Nov 14:00 UTC).' in lines
    assert 'The gold bot (acct_x9): seen 3 seconds ago.' in lines
    assert any(l.strip().startswith('The BTC bot opens no new trade since 21 Nov 13:58: it lost 3 trades in a row')
               for l in lines)
    assert any(l.strip() == 'Drop from the high 20.7% of the 20% limit, loss today 20.7% of the 10% limit, losing '
                            'trades in a row 0 of 3.' for l in lines)
    assert not found(out, PIN) and not found(out, '12345678')                  # never the PIN, never the account number
    out.encode('ascii')                                              # plain text for any console of the server


def test_main_status_after_presses_and_with_a_locked_page(acct, capsys):
    S.press(str(acct), 'off', None, 'command line', T0 - 7200, need_pin=False)
    S.press(str(acct), 'unblock', None, 'command line', T0 - 3600, need_pin=False)
    for i in range(5):
        press(acct, 'unblock', pin='nope', now=T0 - 60 + i)
    (acct / 'safety_pin.txt').write_text('1 2 3')
    assert S.main(['status', '--account-dir', str(acct)], now=T0) == 0
    lines = capsys.readouterr().out.splitlines()
    assert 'Safety: OFF since 21 Nov 12:07 UTC, by command line.' in lines
    assert 'Counting started again on 21 Nov 13:07 UTC (unblock from the command line, by command line).' in lines
    assert 'Account block: none.' in lines
    assert f"PIN of the buttons: NOT usable, file {acct / 'safety_pin.txt'}" in lines
    assert 'The buttons are locked until 21 Nov 14:16 UTC after wrong PINs (this command line is not).' in lines
    assert 'No bot of this account has written its status yet.' in lines


def test_main_runs_each_command_through_press_as_the_command_line(acct, capsys):
    gold, btc = running(acct)
    lose((gold, btc), T0 - 400, 1190.0)
    (acct / 'account_claim.json').write_text('{}')
    assert S.main(['unblock', '--account-dir', str(acct)], now=T0) == 0
    assert capsys.readouterr().out == 'Unblocked at 14:07:10 UTC. Counting again from the current balance.\n'
    assert see((gold, btc), T0 + 5, 1190.0)[0]['blocked'] is False
    assert S.main(['off', '--account-dir', str(acct)], now=T0 + 10) == 0
    assert capsys.readouterr().out == 'Safety is OFF since 14:07:20 UTC.\n'
    assert S.main(['OFF', '--account-dir', str(acct)], now=T0 + 11) == 0
    assert capsys.readouterr().out == 'The safety is already OFF.\n'
    assert S.main(['--account-dir', str(acct), 'on'], now=T0 + 20) == 0
    assert capsys.readouterr().out == 'Safety is ON since 14:07:30 UTC. Counting starts from the current balance.\n'
    assert S.main(['new-account', '--account-dir', str(acct)], now=T0 + 30) == 0
    assert capsys.readouterr().out.startswith('The account of this folder was cleared at 14:07:40 UTC.')
    assert not (acct / 'account_claim.json').exists()
    done = [a for a in audit(acct) if a.get('result') == 'done']
    assert [a['action'] for a in done] == ['unblock', 'off', 'on', 'new-account']
    assert all(a['by'] == 'command line' for a in done)


def test_main_answers_1_when_a_command_is_refused(acct, capsys):
    (acct / 'safety_restart.json').write_bytes(b'{"id": ')
    assert S.main(['off', '--account-dir', str(acct)], now=T0) == 1
    assert capsys.readouterr().out == RESTART_UNREADABLE + '\n'
    assert S.main(['new-account', '--account-dir', str(acct)], now=T0) == 1
    capsys.readouterr()
    assert S.main(['status', '--account-dir', str(acct)], now=T0) == 0       # status still says what it can
    assert 'Some safety files cannot be read right now' in capsys.readouterr().out


@pytest.mark.parametrize('argv', [[], ['help'], ['unblock', 'now'], ['--account-dir'], ['status', '--account-dir='],
                                  ['toggle', '--account-dir', 'x'], ['-h']])
def test_main_prints_how_to_use_it_when_the_command_is_not_understood(argv, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert S.main(argv, now=T0) == 2
    out = capsys.readouterr().out
    assert out.startswith('Usage: python safety.py status|unblock|on|off|new-account [--account-dir FOLDER]')
    assert 'No PIN is asked here' in out and list(tmp_path.iterdir()) == []


def test_main_without_a_folder_takes_it_from_the_branchs_constants(tmp_path, capsys, monkeypatch):
    out_dir = tmp_path / 'bot_output'
    fake = types.SimpleNamespace(OUTPUT_DIR=str(out_dir), ACCOUNT_FOLDER='the_account', SAFETY_DEFAULT_ON=True)
    monkeypatch.setitem(sys.modules, 'constants', fake)
    assert S.main(['off'], now=T0) == 0
    assert capsys.readouterr().out == 'Safety is OFF since 14:07:10 UTC.\n'
    d = tmp_path / 'the_account'                                     # beside the bot's folder, as safety.account_dir says
    assert read(d / 'safety_switch.json')['enabled'] is False and not out_dir.exists()
    assert S.main(['status'], now=T0 + 60) == 0
    assert capsys.readouterr().out.splitlines()[:2] == [f'Account folder: {d}',
                                                        'Safety: OFF since 21 Nov 14:07 UTC, by command line.']
    # a branch whose safety is off until somebody turns it on
    fake.SAFETY_DEFAULT_ON, fake.ACCOUNT_FOLDER = False, 'another_account'
    assert S.main(['off'], now=T0) == 0 and capsys.readouterr().out == 'The safety is already OFF.\n'
    assert S.main(['on'], now=T0) == 0
    assert read(tmp_path / 'another_account' / 'safety_switch.json')['enabled'] is True
    capsys.readouterr()


def test_main_says_so_when_the_branchs_constants_cannot_give_the_folder(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, 'constants', types.SimpleNamespace(OUTPUT_DIR=str(tmp_path / 'bot_output')))
    assert S.main(['status'], now=T0) == 1
    out = capsys.readouterr().out
    assert out.startswith('The account folder of this branch cannot be found in constants.py (AttributeError')
    assert out.rstrip().endswith('Give it with --account-dir FOLDER.') and list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == 'nt', reason='on Windows the folder of the constants is the real one')
@pytest.mark.parametrize('command', ['status', 'unblock', 'on', 'off', 'new-account'])
def test_main_does_not_make_a_windows_folder_on_another_system(command, tmp_path, capsys, monkeypatch):
    """A branch's OUTPUT_DIR is C:\\Alcadeias\\<branch>. Run on a Mac, 'safety.py on' must not make a folder of
    that name in the working folder: it says where to run it instead."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, 'constants', types.SimpleNamespace(
        OUTPUT_DIR='C:\\Somewhere\\some_branch', ACCOUNT_FOLDER='some_account', SAFETY_DEFAULT_ON=True))
    assert S.main([command], now=T0) == 1
    out = capsys.readouterr().out
    assert out == ('The account folder of this branch is C:\\Somewhere\\some_account, a folder of the Windows '
                   'server. Run this on the server, or give a folder with --account-dir FOLDER.\n')
    assert list(tmp_path.iterdir()) == []


def test_main_reads_the_clock_only_when_no_time_is_given(acct, capsys, monkeypatch):
    monkeypatch.setattr(S.time, 'time', lambda: T0 + 3600)
    assert S.main(['off', '--account-dir', str(acct)]) == 0
    assert capsys.readouterr().out == 'Safety is OFF since 15:07:10 UTC.\n'
    monkeypatch.setattr(S.time, 'time', lambda: 1 / 0)               # every other function takes `now`
    tr = bot(acct)
    assert tr.load(T0) and tick(tr, T0, 1500.0)['enabled'] is False
    assert S.press(str(acct), 'on', None, WEB, T0 + 5)[0] is True
    assert S.read_controls(str(acct))['enabled'] is True and S.read_statuses(str(acct))[GOLD]['at'] == T0
    assert S.main(['status', '--account-dir', str(acct)], now=T0 + 6) == 0
    capsys.readouterr()
