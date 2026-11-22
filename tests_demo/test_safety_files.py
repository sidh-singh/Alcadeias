"""
The file shell of the auto-safety (safety.Tracker, read_controls, read_statuses, ensure_pin): what is written
where and by whom, what a bot does when a file is missing, half-written, locked or cannot be written, and what
happens when two bots use one account folder in the same instant. Every file is in the test's tmp_path.

The rules themselves are tested without files in test_safety_core.py; the buttons in test_safety_press.py.
The limits and branch names here are test values ('acct_x9' a gold bot, 'acct_b9' a BTC bot).

Run:  python3 -B -m pytest tests_demo/test_safety_files.py -q -p no:cacheprovider
"""
import builtins
import errno
import importlib.util
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import found

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location('safety_tested_files', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()

T0 = datetime(2026, 11, 21, 14, 5, tzinfo=timezone.utc).timestamp()          # 21 Nov 14:05 UTC
GOLD, BTC = 'acct_x9', 'acct_b9'
LOGIN = 12345678
FORBIDDEN_IN_A_FILE_NAME = set('<>:"/\\|?*')                                  # spec rule 12


def limits():
    return S.Limits(20.0, 10.0, 3)


def bot(tmp_path, branch=GOLD, partner=BTC, lim=None, login=LOGIN, **kw):
    """A Tracker as app.py builds it: the account folder beside the bot's own folder."""
    return S.Tracker(str(tmp_path / 'acct'), str(tmp_path / branch / 'state' / 'safety_state.json'), branch, partner,
                     lim or limits(), login=login, **kw)


def tick(tr, now, balance, cash=None, read_at=None, waiting=0):
    """One poll of the bot: the safety before the decision, the files after the orders."""
    view = tr.poll(now, balance, cash, read_at, waiting)
    tr.flush(now)
    return view


def start(tr, now, balance):
    assert tr.load(now) is True
    tick(tr, now, balance)
    return tick(tr, now + 1, balance, [], now + 0.5)             # the first cash read: nothing to see


def settle(tr, now, balance, cash=()):
    tick(tr, now, balance)
    return tick(tr, now + 4, balance, list(cash), now + 3.5)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def audit(tmp_path):
    f = tmp_path / 'acct' / 'safety_audit.jsonl'
    return [json.loads(line) for line in f.read_text(encoding='utf-8').splitlines()] if f.exists() else []


def acct_files(tmp_path):
    d = tmp_path / 'acct'
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def write_restart(tmp_path, new_id, scope='account', account_id=None, by='test'):
    (tmp_path / 'acct').mkdir(exist_ok=True)
    (tmp_path / 'acct' / 'safety_restart.json').write_text(json.dumps(
        {'id': new_id, 'scope': scope, 'account_id': account_id or (new_id if scope == 'account' else 'start'),
         'at': '2026-11-21T14:10:00Z', 't': T0 + 300, 'by': by, 'why': 'test'}), encoding='utf-8')


def write_switch(tmp_path, enabled):
    (tmp_path / 'acct').mkdir(exist_ok=True)
    (tmp_path / 'acct' / 'safety_switch.json').write_text(json.dumps(
        {'enabled': enabled, 'at': '2026-11-21T14:10:00Z', 't': T0 + 300, 'by': 'test'}), encoding='utf-8')


@contextmanager
def refusing(monkeypatch, match, modes='rwxa', error=PermissionError(13, 'Permission denied')):
    """While inside: open() of a path that `match` accepts, in one of `modes`, is refused, as Windows does while
    another program holds the file. Only safety.py's own open() is replaced (a module global shadows the builtin)."""
    real = builtins.open
    seen = []

    def fake(path, mode='r', *a, **k):
        if match(str(path)) and set(mode) & set(modes):
            seen.append((str(path), mode))
            raise error
        return real(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', fake, raising=False)
    try:
        yield seen
    finally:
        monkeypatch.delattr(S, 'open', raising=False)


@contextmanager
def watching_the_disk(monkeypatch):
    """While inside: every file operation safety.py could make is recorded (and still done)."""
    calls = []
    real_open = builtins.open

    def spy_open(path, mode='r', *a, **k):
        calls.append(('open', os.path.basename(str(path)), mode))
        return real_open(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', spy_open, raising=False)
    for name in ('stat', 'replace', 'remove', 'makedirs', 'listdir', 'rename', 'mkdir', 'fsync'):
        real = getattr(os, name)

        def spy(*a, _real=real, _name=name, **k):
            calls.append((_name, os.path.basename(str(a[0])) if a and isinstance(a[0], (str, os.PathLike)) else ''))
            return _real(*a, **k)
        monkeypatch.setattr(os, name, spy)
    try:
        yield calls
    finally:
        monkeypatch.undo()


# ───────────────────────────── the files a bot writes, and what a restart keeps ─────────────────────────────

def test_a_missing_account_folder_is_created_and_the_first_poll_writes_state_and_status(tmp_path):
    tr = bot(tmp_path)
    assert not (tmp_path / 'acct').exists()
    assert tr.view()['blocked'] is True and 'not loaded yet' in tr.view()['error']       # nothing usable before load
    assert tr.load(T0) is True and (tmp_path / 'acct').is_dir()
    assert tr.load(T0 + 1) is True                                   # a second call changes nothing
    v = tick(tr, T0, 1500.0)
    assert v['blocked'] is False and v['error'] is None and v['period'] == 'start'
    assert v['account_dir'] == str(tmp_path / 'acct') and v['login_tail'] == '...5678'
    assert acct_files(tmp_path) == ['safety_audit.jsonl', 'safety_status_acct_x9.json']
    state = read(tmp_path / GOLD / 'state' / 'safety_state.json')
    assert state['version'] == 1 and state['branch'] == GOLD and state['login_sha'] == S.login_sha(LOGIN)
    assert state['peak'] == 1500.0 and state['period'] == 'start' and state['started_at'] == T0
    status = read(tmp_path / 'acct' / 'safety_status_acct_x9.json')
    assert status['branch'] == GOLD and status['partner_branch'] == BTC and status['at'] == T0
    assert status['limits'] == {'drop_pct': 20.0, 'day_pct': 10.0, 'streak_n': 3}
    assert status['login_tail'] == '...5678' and status['login_sha'] == S.login_sha(LOGIN)
    assert status['blocked'] is False and status['bot_block'] is None and status['written_at'] == T0
    assert [(a['event'], a['scope'], a['by']) for a in audit(tmp_path)] == [('fresh_start', 'first', 'bot acct_x9')]


def test_a_restart_keeps_everything(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1700.0, [{'ticket': 7, 'amount': 200.0, 'time': T0 + 9.5}])
    settle(tr, T0 + 20, 1620.0)
    tr.on_trade_closed(T0 + 25, 9001, -40.0)
    tr.on_trade_closed(T0 + 26, 9002, -40.0)
    tick(tr, T0 + 30, 1600.0)                                        # a change still being checked
    before = json.loads(json.dumps(tr._state))
    assert before['change_first'] == T0 + 30 and before['streak'] == 2 and before['peak'] == 1700.0

    again = bot(tmp_path)                                            # the process starts again
    assert again.load(T0 + 40) is True
    assert again._state == before
    assert again.view()['streak']['count'] == 2 and again.view()['drop']['peak'] == 1700.0
    v = tick(again, T0 + 41, 1600.0)
    assert v['pending'] is True and again.needs_cash() is True
    v = tick(again, T0 + 45, 1600.0, [], T0 + 44.5)
    assert v['pending'] is False and v['drop']['balance'] == 1600.0 and v['day']['cash'] == 200.0
    assert again.on_trade_closed(T0 + 46, 9002, -40.0)['streak']['count'] == 2      # counted before the restart
    assert again.on_trade_closed(T0 + 47, 9003, -40.0)['bot_blocked'] is True       # the third loss in a row


def test_a_restart_in_the_middle_of_a_check_reads_the_history_before_it_calls_a_fall_a_loss(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    tick(tr, T0 + 10, 1000.0)                                        # 500 withdrawn; the process dies 1 s later
    again = bot(tmp_path)
    assert again.load(T0 + 600) is True and again.needs_cash() is True
    v = tick(again, T0 + 601, 1000.0)                                # the fall is 10 minutes old: still only held
    assert v['hold'] and v['pending'] and not v['blocked']
    v = tick(again, T0 + 602, 1000.0, [{'ticket': 9, 'amount': -500.0, 'time': T0 + 9.4}], T0 + 601.5)
    assert not v['hold'] and not v['blocked'] and v['drop']['peak'] == 1000.0 and v['drop']['pct'] == 0.0
    assert not (tmp_path / 'acct' / 'safety_block_start.json').exists()


def test_a_restart_keeps_a_block_of_the_bot_and_a_block_of_the_account(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -10.0)
    v = settle(tr, T0 + 10, 1190.0)
    assert v['blocked'] and v['account_blocked'] and v['bot_blocked']
    again = bot(tmp_path)
    assert again.load(T0 + 100) is True
    v = again.view()                                                 # blocked from the first moment, before any poll
    assert v['blocked'] and v['account_blocked'] and v['bot_blocked'] and v['blocked_scope'] == 'account'
    v = tick(again, T0 + 101, 1190.0)
    assert v['blocked'] and v['since'] == T0 + 14 and len(v['reasons']) == 5


def test_the_status_file_is_rewritten_when_the_view_changes_and_at_least_every_20_seconds(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    path = tmp_path / 'acct' / 'safety_status_acct_x9.json'
    written = []
    real = S._write_atomic
    monkeypatch.setattr(S, '_write_atomic', lambda p, text, durable=False: (written.append(os.path.basename(p)),
                                                                           real(p, text, durable))[1])
    for dt in range(2, 19):                                          # nothing changes: nothing is written
        tick(tr, T0 + dt, 1500.0)
    assert written == [] and read(path)['at'] in (T0, T0 + 1)
    tick(tr, T0 + 21.5, 1500.0)                                      # 20 s after the last write
    assert written == ['safety_status_acct_x9.json'] and read(path)['at'] == T0 + 21.5
    assert read(path)['written_at'] == T0 + 21.5
    tick(tr, T0 + 22, 1400.0)                                        # the view changed (a change is being checked)
    assert written[1:] == ['safety_state.json', 'safety_status_acct_x9.json'] and read(path)['pending'] is True
    assert S.STATUS_EVERY_S < S.PARTNER_STALE_S                      # a running bot is never taken for a stopped one


def test_a_poll_touches_no_file_except_the_one_it_creates_when_a_limit_is_met(tmp_path, monkeypatch):
    """Spec rule 2: nothing may sit between the poll's positions read and its orders. poll(), on_trade_closed()
    and note_other_program() work in memory; the one exception is the exclusive creation of the block file."""
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    write_switch(tmp_path, True)
    with watching_the_disk(monkeypatch) as calls:
        tr.poll(T0 + 5, 1500.0)
        tr.poll(T0 + 6, None)
        tr.poll(T0 + 7, 1400.0, [{'ticket': 1, 'amount': 5.0, 'time': T0}], T0 + 6.5, 2)
        tr.poll(T0 + 11, 1400.0, [], T0 + 10.5)                      # settles
        tr.on_trade_closed(T0 + 12, 'a', -1.0)
        tr.on_trade_closed(T0 + 13, 'b', -1.0)
        tr.on_trade_closed(T0 + 14, 'c', -1.0)                       # this bot is blocked: still no file
        tr.note_other_program(T0 + 15, 'another program holds 1 trade of its own on XAUUSDm')
        tr.needs_cash(), tr.cash_since(), tr.view(), tr.take_events()
    assert calls == []
    with watching_the_disk(monkeypatch) as calls:
        tr.poll(T0 + 20, 1100.0)
        v = tr.poll(T0 + 24, 1100.0, [], T0 + 23.5)                  # the drop limit is met
    assert v['account_blocked'] is True
    assert calls == [('open', 'safety_block_start.json', 'x')]
    with watching_the_disk(monkeypatch) as calls:
        tr.flush(T0 + 24)                                            # everything else happens here
    assert ('open', 'safety_restart.json', 'rb') in calls and ('open', 'safety_switch.json', 'rb') in calls
    assert ('stat', 'safety_block_start.json') in calls and ('open', 'safety_audit.jsonl', 'a') in calls
    replaced = sorted(name.split('.json.')[0] for kind, name in [c[:2] for c in calls] if kind == 'replace')
    assert replaced == ['safety_state', 'safety_status_acct_x9']     # the state and the status, each moved into place


def test_flush_reads_the_folder_and_writes_only_this_bots_files(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    write_restart(tmp_path, '20261121_141000-aaaaaa')
    write_switch(tmp_path, True)
    (tmp_path / 'acct' / 'safety_pin.txt').write_text('246810\n')
    (tmp_path / 'acct' / 'safety_lockout.json').write_text('{"wrong": 2}')
    (tmp_path / 'acct' / 'account_claim.json').write_text('{}')
    owners = {n: (tmp_path / 'acct' / n).read_bytes() for n in ('safety_restart.json', 'safety_switch.json',
                                                                'safety_pin.txt', 'safety_lockout.json',
                                                                'account_claim.json')}
    tick(tr, T0 + 5, 1500.0)                                         # reads the press...
    tick(tr, T0 + 6, 1500.0, [], T0 + 5.5)                           # ...and counts under its id from here
    settle(tr, T0 + 10, 1100.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 20 + i, i, -1.0)
    tick(tr, T0 + 30, 1100.0)
    assert tr.view()['account_blocked'] and tr.view()['bot_blocked']
    for n, content in owners.items():
        assert (tmp_path / 'acct' / n).read_bytes() == content, n       # a bot never writes what press writes
    assert sorted(set(acct_files(tmp_path)) - set(owners)) == [
        'safety_audit.jsonl', 'safety_block_20261121_141000-aaaaaa.json', 'safety_status_acct_x9.json']


# ───────────────────────────── the block of the account ─────────────────────────────

def test_a_trip_sets_the_block_in_the_state_first_then_creates_the_file(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    tr.poll(T0 + 10, 1194.0)
    order = []
    real = S._create_exclusive

    def create(path, text):
        order.append(('state has the block', tr._state['account_block'] is not None
                      and tr._state['account_block']['period'] == 'start'))
        order.append(('file', os.path.basename(path)))
        return real(path, text)
    monkeypatch.setattr(S, '_create_exclusive', create)
    v = tr.poll(T0 + 14, 1194.0, [], T0 + 13.5)
    assert order == [('state has the block', True), ('file', 'safety_block_start.json')]
    assert v['blocked'] and v['account_blocked'] and v['blocked_scope'] == 'account' and v['since'] == T0 + 14
    blk = read(tmp_path / 'acct' / 'safety_block_start.json')
    assert blk['period'] == 'start' and blk['rules'] == ['DROP', 'DAY'] and blk['branch'] == GOLD
    assert blk['at'] == T0 + 14 and blk['at_utc'] == '2026-11-21T14:05:14Z' and blk['login_tail'] == '...5678'
    assert blk['numbers']['balance'] == 1194.0 and blk['numbers']['peak'] == 1500.0
    assert round(blk['numbers']['drop_pct'], 2) == 20.4 and blk['numbers']['drop_limit'] == 20.0
    assert blk['reasons'] == [
        'The account fell 20.4% below its high (limit 20%): balance $1,194.00, high $1,500.00 on 21 Nov.',
        'The account lost 20.4% on 21 Nov, UTC day (limit 10%): balance $1,194.00, $1,500.00 when counting started '
        'that day at 14:05.', 'The gold bot (acct_x9) saw it.']
    assert v['reasons'][1:] == blk['reasons']
    tr.flush(T0 + 14)
    assert read(tmp_path / GOLD / 'state' / 'safety_state.json')['account_block']['period'] == 'start'
    trips = [a for a in audit(tmp_path) if a['event'] == 'trip']
    assert len(trips) == 1 and trips[0]['scope'] == 'account' and trips[0]['rules'] == ['DROP', 'DAY']
    assert trips[0]['by'] == 'bot acct_x9' and trips[0]['at'] == '2026-11-21T14:05:14Z'
    assert trips[0]['numbers']['balance'] == 1194.0


@pytest.mark.parametrize('error', [PermissionError(13, 'Permission denied'),
                                   OSError(errno.ENOSPC, 'No space left on device')])
def test_a_block_file_that_cannot_be_created_still_blocks_and_is_tried_again_at_every_flush(tmp_path, monkeypatch,
                                                                                            error):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    tr.poll(T0 + 10, 1190.0)
    with refusing(monkeypatch, lambda p: 'safety_block_' in p, modes='x', error=error) as tries:
        v = tr.poll(T0 + 14, 1190.0, [], T0 + 13.5)
        assert v['blocked'] and v['account_blocked'] and v['error'] is None          # the state holds the block
        assert v['reasons'][1].startswith('The account fell 20.7% below its high')
        assert len(tries) == 1 and not (tmp_path / 'acct' / 'safety_block_start.json').exists()
        tr.flush(T0 + 14)
        tr.flush(T0 + 15)
        assert len(tries) == 3                                       # again at every flush
        assert read(tmp_path / GOLD / 'state' / 'safety_state.json')['account_block']['rules'] == ['DROP', 'DAY']
        assert read(tmp_path / 'acct' / 'safety_status_acct_x9.json')['account_blocked'] is True
        v = tick(tr, T0 + 73.9, 1190.0)
        assert v['error'] is None and v['blocked']
        v = tick(tr, T0 + 74, 1190.0)                                # a minute: the safety check is failing
        assert v['blocked'] and v['state'] == 'error' and v['since'] == T0 + 14
        assert v['error'].startswith('the block file could not be written since 14:05 UTC (')
        assert type(error).__name__ in v['error']
        assert v['reasons'][0] == S.ERROR_SENTENCE and v['reasons'][1].startswith('Both bots open no new trade')
        # a restart in this state: the block is in the state file
        again = bot(tmp_path)
        assert again.load(T0 + 80) is True and again.view()['account_blocked'] is True
        assert tick(again, T0 + 81, 1190.0)['blocked'] is True
    v = tick(tr, T0 + 90, 1190.0)                                    # the folder works again: created at this flush
    assert (tmp_path / 'acct' / 'safety_block_start.json').exists()
    v = tick(tr, T0 + 91, 1190.0)
    assert v['error'] is None and v['blocked'] and v['state'] == 'account_blocked'
    assert read(tmp_path / 'acct' / 'safety_block_start.json')['branch'] == GOLD


def test_a_block_file_whose_content_cannot_be_written_still_blocks(tmp_path, monkeypatch):
    """The disk fills between creating the file and writing it: the empty file is the block."""
    tr = bot(tmp_path)
    other = bot(tmp_path, BTC, GOLD)
    start(tr, T0, 1500.0)
    start(other, T0, 1500.0)
    real = builtins.open

    class Full:
        def __init__(self, f):
            self.f = f

        def write(self, text):
            raise OSError(errno.ENOSPC, 'No space left on device')

        def close(self):
            self.f.close()

    monkeypatch.setattr(S, 'open', lambda p, mode='r', *a, **k: Full(real(p, mode, *a, **k)) if mode == 'x'
                        else real(p, mode, *a, **k), raising=False)
    tr.poll(T0 + 10, 1190.0)
    v = tr.poll(T0 + 14, 1190.0, [], T0 + 13.5)
    monkeypatch.delattr(S, 'open')
    assert (tmp_path / 'acct' / 'safety_block_start.json').read_bytes() == b''
    assert v['blocked'] and v['error'] is None
    tr.flush(T0 + 14)
    tick(other, T0 + 15, 1500.0)
    v = tick(other, T0 + 16, 1500.0)                                 # the other bot: blocked by the empty file
    assert v['blocked'] and v['account_blocked'] and v['since'] is not None
    assert v['reasons'][1] == 'The details of this block cannot be read.'
    c = S.read_controls(str(tmp_path / 'acct'))
    assert c['block']['readable'] is False and c['block']['period'] == 'start' and c['block']['reasons'] == []
    assert tick(tr, T0 + 17, 1190.0)['reasons'][1].startswith('The account fell')    # it knows its own numbers


@pytest.mark.parametrize('content', [b'', b'{', b'\xff\xfe\x00', b'[1, 2]', b'null'])
def test_an_empty_or_unreadable_block_file_still_blocks(tmp_path, content):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    (tmp_path / 'acct' / 'safety_block_start.json').write_bytes(content)
    tr.flush(T0 + 5)
    v = tick(tr, T0 + 6, 1500.0)
    assert v['blocked'] and v['account_blocked'] and v['blocked_scope'] == 'account'
    assert v['reasons'][1] == 'The details of this block cannot be read.'
    assert tr._state['account_block'] is None and tr._state['block_exists_last'] is True


def test_a_block_file_of_another_id_is_ignored(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    (tmp_path / 'acct' / 'safety_block_20261101_090000-0f0f0f.json').write_text('{"rules": ["DROP"]}')
    tr.flush(T0 + 5)
    assert tick(tr, T0 + 6, 1500.0)['blocked'] is False
    # and the other way round: an old block of the id 'start' does not block after an Unblock wrote a new id
    (tmp_path / 'acct' / 'safety_block_start.json').write_text('{}')
    tr.flush(T0 + 7)
    assert tick(tr, T0 + 8, 1500.0)['blocked'] is True
    write_restart(tmp_path, '20261121_141000-bbbbbb')
    tr.flush(T0 + 9)
    v = tick(tr, T0 + 10, 1500.0)
    assert v['blocked'] is False and v['period'] == '20261121_141000-bbbbbb'


def test_the_other_bot_is_blocked_by_the_file_at_its_next_poll_and_shows_the_first_bots_numbers(tmp_path):
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD, S.Limits(20.0, 10.0, 9))
    start(gold, T0, 1500.0)
    start(btc, T0 + 600, 1300.0)                                     # started later: its own high is lower
    v = settle(gold, T0 + 700, 1190.0)                               # 20.67 % for gold, 8.5 % for BTC
    assert v['account_blocked']
    v = btc.poll(T0 + 704.5, 1190.0)
    assert v['blocked'] is False                                     # not yet known to it...
    btc.flush(T0 + 704.5)
    v = btc.poll(T0 + 705.5, 1190.0)                                 # ...one poll later it is
    assert v['blocked'] and v['account_blocked'] and v['blocked_scope'] == 'account' and v['since'] == T0 + 704
    assert v['reasons'] == [
        'Both bots open no new trade and add nothing to open trades since 21 Nov 14:16. Open trades keep their stop '
        'and target. Press Unblock to trade again.',
        'The account fell 20.7% below its high (limit 20%): balance $1,190.00, high $1,500.00 on 21 Nov.',
        'The account lost 20.7% on 21 Nov, UTC day (limit 10%): balance $1,190.00, $1,500.00 when counting started '
        'that day at 14:05.', 'The gold bot (acct_x9) saw it.']
    assert btc._state['account_block'] is None                       # it met no limit itself
    assert sorted(n for n in acct_files(tmp_path) if n.startswith('safety_block_')) == ['safety_block_start.json']


def test_two_bots_racing_to_trip_both_end_blocked_with_one_file(tmp_path):
    for round_ in range(25):
        folder = tmp_path / f'r{round_}'
        gold, btc = bot(folder), bot(folder, BTC, GOLD)
        start(gold, T0, 1500.0)
        start(btc, T0, 1500.0)
        gold.poll(T0 + 10, 1190.0)
        btc.poll(T0 + 10, 1190.0)
        gate = threading.Barrier(2)
        views = {}

        def trip(tr, name):
            gate.wait()
            views[name] = tr.poll(T0 + 14, 1190.0, [], T0 + 13.5)
        threads = [threading.Thread(target=trip, args=(gold, 'gold')), threading.Thread(target=trip, args=(btc, 'btc'))]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        for name in ('gold', 'btc'):
            assert views[name]['blocked'] and views[name]['account_blocked'], (round_, name)
        blocks = [n for n in acct_files(folder) if n.startswith('safety_block_')]
        assert blocks == ['safety_block_start.json'], (round_, blocks)
        winner = read(folder / 'acct' / 'safety_block_start.json')          # one whole file, of one of the two
        assert winner['branch'] in (GOLD, BTC) and winner['rules'] == ['DROP', 'DAY']
        assert gold._state['account_block']['period'] == btc._state['account_block']['period'] == 'start'
        gold.flush(T0 + 14), btc.flush(T0 + 14)
        v1, v2 = tick(gold, T0 + 15, 1190.0), tick(btc, T0 + 15, 1190.0)
        seen_by = f"The {'gold' if winner['branch'] == GOLD else 'BTC'} bot ({winner['branch']}) saw it."
        assert v1['reasons'][-1] == v2['reasons'][-1] == seen_by     # both show the same first bot


def test_a_block_file_removed_by_hand_is_made_again_by_the_bot_that_holds_the_block(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1190.0)
    f = tmp_path / 'acct' / 'safety_block_start.json'
    f.unlink()
    v = tick(tr, T0 + 20, 1190.0)                                    # blocks never end by themselves
    assert v['blocked'] and f.exists() and read(f)['branch'] == GOLD
    assert tick(tr, T0 + 21, 1190.0)['account_blocked'] is True


def test_when_the_folder_cannot_be_asked_the_last_known_answer_about_the_block_stays(tmp_path, monkeypatch):
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD)
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    settle(gold, T0 + 10, 1190.0)
    tick(btc, T0 + 15, 1500.0)
    assert tick(btc, T0 + 16, 1500.0)['account_blocked'] is True
    real = os.stat

    def stat(path, *a, **k):
        if 'safety_block_' in str(path):
            raise PermissionError(13, 'Permission denied')
        return real(path, *a, **k)
    monkeypatch.setattr(os, 'stat', stat)
    for dt in (20, 21, 22):
        assert tick(btc, T0 + dt, 1500.0)['account_blocked'] is True     # not "no block": the answer of before
    # a new process that cannot ask either: the answer is in its state file
    again = bot(tmp_path, BTC, GOLD)
    assert again.load(T0 + 30) is True and again.view()['account_blocked'] is True
    assert tick(again, T0 + 31, 1500.0)['blocked'] is True
    monkeypatch.setattr(os, 'stat', real)
    assert S.read_controls(str(tmp_path / 'acct'))['block'] is not None


# ───────────────────────────── a state file that fails ─────────────────────────────

def test_a_state_write_that_fails_blocks_after_a_minute_while_on_and_a_restart_starts_from_the_old_file(tmp_path,
                                                                                                         monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    saved = state_file.read_bytes()
    real = S._replace_retry
    tries = []

    def refuse_state(src, dst, *a, **k):
        if dst.endswith('safety_state.json'):
            tries.append(dst)
            raise PermissionError(13, 'Permission denied')
        return real(src, dst, *a, **k)
    monkeypatch.setattr(S, '_replace_retry', refuse_state)
    v = settle(tr, T0 + 10, 1400.0)                                  # a loss of 6.7 %: the state cannot be saved
    tr.on_trade_closed(T0 + 15, 'a', -100.0)
    assert v['error'] is None and v['blocked'] is False and len(tries) == 1
    for dt in (15, 16, 17, 18):
        tick(tr, T0 + dt, 1400.0)
    assert len(tries) == 2                                           # tried again every 5 s, not on every poll
    v = tick(tr, T0 + 69.9, 1400.0)
    assert v['error'] is None and v['blocked'] is False
    v = tick(tr, T0 + 71, 1400.0)                                    # a minute after the first failure
    assert v['blocked'] is True and v['state'] == 'error' and v['blocked_scope'] is None and v['since'] == T0 + 10
    assert v['error'].startswith('the safety state could not be saved since 14:05 UTC (PermissionError')
    assert v['reasons'] == [S.ERROR_SENTENCE]
    assert read(tmp_path / 'acct' / 'safety_status_acct_x9.json')['error'] == v['error']     # the dashboard sees it
    assert state_file.read_bytes() == saved                          # the old file is whole
    assert [p.name for p in state_file.parent.iterdir()] == ['safety_state.json']    # no temp file left behind
    # OFF: the failing check blocks nothing
    write_switch(tmp_path, False)
    tr.flush(T0 + 72)
    v = tick(tr, T0 + 73, 1400.0)
    assert v['blocked'] is False and v['error'] is not None and v['state'] == 'off'
    # the process dies and starts again: it reads the OLD state, sees the loss again and judges it again
    again = bot(tmp_path)
    assert again.load(T0 + 100) is True and again._state['settled_balance'] == 1500.0
    assert again._state['streak'] == 0                               # (the losing trade it could not save is lost)
    monkeypatch.setattr(S, '_replace_retry', real)
    write_switch(tmp_path, True)
    again.flush(T0 + 100)
    v = settle(again, T0 + 101, 1400.0)
    assert v['error'] is None and v['blocked'] is False and v['drop']['balance'] == 1400.0
    assert round(v['drop']['pct'], 2) == 6.67 and read(state_file)['settled_balance'] == 1400.0
    # and the first Tracker: once the write works its error is gone
    tr.flush(T0 + 200)
    assert tick(tr, T0 + 201, 1400.0)['error'] is None


def test_a_state_file_that_cannot_be_read_is_tried_again_and_never_put_aside(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    tick(tr, T0 + 10, 1500.0)
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    saved = state_file.read_bytes()
    again = bot(tmp_path)
    with refusing(monkeypatch, lambda p: p.endswith('safety_state.json'), modes='r'):
        assert again.load(T0 + 20) is False                          # another program holds it this moment
        assert again.load(T0 + 21) is False
        v = again.poll(T0 + 21, 1500.0)                              # (app.py does not poll it; if it did:)
        assert v['blocked'] is True and v['state'] == 'error' and v['since'] == T0 + 20
        assert v['error'].startswith('the safety state could not be loaded (the state file cannot be read: '
                                     'PermissionError')
        assert again.needs_cash() is False
    assert state_file.read_bytes() == saved and [p.name for p in state_file.parent.iterdir()] == ['safety_state.json']
    assert again.load(T0 + 22) is True                               # readable again: nothing was lost
    v = tick(again, T0 + 23, 1500.0)
    assert v['bot_blocked'] is True and v['error'] is None and v['streak']['count'] == 3


def test_a_state_path_that_is_a_folder_cannot_be_read_either(tmp_path):
    (tmp_path / GOLD / 'state' / 'safety_state.json').mkdir(parents=True)
    tr = bot(tmp_path)
    assert tr.load(T0) is False and tr.view()['blocked'] is True
    assert (tmp_path / GOLD / 'state' / 'safety_state.json').is_dir()


@pytest.mark.parametrize('content', [b'', b'{"version": 1, "peak": 15', b'\xff\xfe{\x00}\x00', b'[]',
                                     b'{"version": 99}', b'{"version": 1, "period": "a b/c"}'])
def test_a_state_file_that_is_not_a_state_is_put_aside_and_the_bot_starts_as_new(tmp_path, content):
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    state_file.parent.mkdir(parents=True)
    state_file.write_bytes(content)
    tr = bot(tmp_path)
    assert tr.load(T0 + 10) is True
    kept = sorted(p.name for p in state_file.parent.iterdir())
    assert kept == ['safety_state.json.not-readable-20261121_140510']
    assert (state_file.parent / kept[0]).read_bytes() == content    # nothing is thrown away
    v = tick(tr, T0 + 11, 1500.0)
    assert v['blocked'] is False and v['period'] == 'start' and v['drop']['peak'] == 1500.0
    ev = tr.take_events()
    assert [e['event'] for e in ev] == ['state_put_aside', 'fresh_start']
    assert ev[0]['why'] == 'not-readable' and ev[0]['kept_as'] == kept[0]
    assert [a['event'] for a in audit(tmp_path)] == ['state_put_aside', 'fresh_start']
    assert read(state_file)['peak'] == 1500.0


def test_a_state_put_aside_keeps_the_bots_block_when_its_own_status_file_still_shows_it(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    tick(tr, T0 + 10, 1500.0)
    assert read(tmp_path / 'acct' / 'safety_status_acct_x9.json')['bot_blocked'] is True
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    state_file.write_bytes(b'{"version": 1, "peak": 15')            # half a file
    again = bot(tmp_path)
    assert again.load(T0 + 20) is True
    v = again.view()
    assert v['blocked'] and v['bot_blocked'] and v['streak']['count'] == 3 and v['since'] == T0 + 7
    v = tick(again, T0 + 21, 1480.0)                                 # the figures start again, the block does not
    assert v['bot_blocked'] and v['drop']['peak'] == 1480.0 and v['period'] == 'start'
    assert v['reasons'][0].startswith('The gold bot opens no new trade since 21 Nov 14:05: it lost 3 trades in a row')
    assert again._state['bot_block'] == {'rule': 'STREAK', 'text': 'it lost 3 trades in a row (limit 3)',
                                         'count': 3, 'limit': 3, 'at': T0 + 7}


def test_the_status_file_is_read_again_when_it_is_held_for_a_moment_at_that_point(tmp_path, monkeypatch):
    """The dashboard reads the status file every few seconds. If it holds it in the very moment a bot with a damaged
    state file looks for its block there, one refused read must not cost the block."""
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    tick(tr, T0 + 10, 1500.0)
    (tmp_path / GOLD / 'state' / 'safety_state.json').write_bytes(b'{')
    real = builtins.open
    refused = []
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)

    def held_once(path, mode='r', *a, **k):
        if str(path).endswith('safety_status_acct_x9.json') and 'r' in mode and not refused:
            refused.append(str(path))
            raise PermissionError(13, 'Permission denied')
        return real(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', held_once, raising=False)
    again = bot(tmp_path)
    assert again.load(T0 + 20) is True and len(refused) == 1
    assert again.view()['bot_blocked'] is True and again.view()['streak']['count'] == 3


def test_a_state_file_that_is_gone_keeps_the_block_too_but_not_after_an_unblock(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    tr.note_other_program(T0 + 5, 'another program holds 2 trades of its own on XAUUSDm')
    settle(tr, T0 + 10, 1190.0)
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    state_file.unlink()                                              # the state folder was cleaned
    (tmp_path / 'acct' / 'safety_block_start.json').unlink()
    again = bot(tmp_path)
    assert again.load(T0 + 20) is True
    v = again.view()
    assert v['account_blocked'] and v['bot_blocked'] and v['blocked']
    assert again._state['bot_block']['rule'] == 'OTHER_PROGRAM' and again._state['account_block']['rules']
    tick(again, T0 + 21, 1190.0)
    assert (tmp_path / 'acct' / 'safety_block_start.json').exists()  # and the block file is made again
    # the same loss of the state file after an Unblock: the status is of the old id, nothing is kept
    state_file.unlink()
    write_restart(tmp_path, '20261121_150000-cccccc')
    third = bot(tmp_path)
    assert third.load(T0 + 30) is True
    v = tick(third, T0 + 31, 1190.0)
    assert v['blocked'] is False and v['period'] == '20261121_150000-cccccc' and v['streak']['count'] == 0


def test_a_state_of_another_account_is_put_aside_and_nothing_of_it_is_kept(tmp_path):
    tr = bot(tmp_path, login=LOGIN)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    settle(tr, T0 + 10, 1190.0)
    moved = bot(tmp_path, login=87654321)                            # the branch now trades another account
    assert moved.load(T0 + 100) is True
    names_ = sorted(p.name for p in (tmp_path / GOLD / 'state').iterdir())
    assert names_ == ['safety_state.json.other-account-20261121_140640']
    assert moved._state['bot_block'] is None and moved._state['streak'] == 0 and moved._state['peak'] is None
    assert moved._state['login_sha'] == S.login_sha(87654321)
    ev = moved.take_events()
    assert ev[0]['event'] == 'state_put_aside' and ev[0]['why'] == 'other-account'
    # (the account folder still holds the old account's block file: app.py's account claim stops that mix-up)
    same = bot(tmp_path, login='87654321')                           # the login as text: the same account
    tick(moved, T0 + 101, 900.0)
    assert same.load(T0 + 102) is True and same._state['peak'] == 900.0
    assert len(list((tmp_path / GOLD / 'state').iterdir())) == 2


def test_a_state_of_another_account_keeps_no_block_even_from_a_status_file_without_an_account(tmp_path):
    tr = bot(tmp_path, login=LOGIN)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    tick(tr, T0 + 10, 1500.0)
    status_file = tmp_path / 'acct' / 'safety_status_acct_x9.json'
    status = read(status_file)
    assert status['bot_blocked'] is True
    del status['login_sha']                                          # (as an older status file might be)
    status_file.write_text(json.dumps(status))
    moved = bot(tmp_path, login=87654321)
    assert moved.load(T0 + 100) is True
    assert moved._state['bot_block'] is None and moved._state['streak'] == 0
    assert tick(moved, T0 + 101, 900.0)['blocked'] is False


def test_a_damaged_state_and_an_unreadable_restart_file_together_still_keep_the_block(tmp_path, monkeypatch):
    write_restart(tmp_path, '20261120_101500-a1b2c3')
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    tick(tr, T0 + 10, 1500.0)
    (tmp_path / GOLD / 'state' / 'safety_state.json').write_bytes(b'{"version": 1, ')
    again = bot(tmp_path)
    with refusing(monkeypatch, lambda p: p.endswith('safety_restart.json'), modes='r'):
        assert again.load(T0 + 100) is True                          # the id is taken from its own status file
        v = tick(again, T0 + 101, 1500.0)
        assert v['bot_blocked'] and v['blocked'] and v['period'] == '20261120_101500-a1b2c3'
    v = tick(again, T0 + 102, 1500.0)                                # the restart file reads again: the same id
    v = tick(again, T0 + 103, 1500.0)
    assert v['bot_blocked'] and v['streak']['count'] == 3 and v['period'] == '20261120_101500-a1b2c3'
    assert [e['scope'] for e in again.take_events() if e['event'] == 'fresh_start'] == ['first']


def test_a_bot_that_starts_under_an_id_whose_block_file_exists_is_blocked_from_its_first_poll(tmp_path):
    """The gold bot was stopped. Meanwhile the owner unblocked the account and the BTC bot met the limit again
    under the new id. The gold bot's first poll after its start must already be blocked: it reads the block file
    of the id it is about to count under, not of the id in its old state."""
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD)
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    tick(gold, T0 + 5, 1500.0)                                       # ...and the gold bot stops
    write_restart(tmp_path, '20261121_141000-abab12')
    tick(btc, T0 + 300, 1500.0)
    tick(btc, T0 + 301, 1500.0, [], T0 + 300.5)
    assert settle(btc, T0 + 310, 1190.0)['account_blocked']
    assert (tmp_path / 'acct' / 'safety_block_20261121_141000-abab12.json').exists()
    again = bot(tmp_path)
    assert again.load(T0 + 400) is True
    v = again.poll(T0 + 401, 1190.0)                                 # its very first poll
    assert v['period'] == '20261121_141000-abab12' and v['blocked'] and v['account_blocked']
    assert v['reasons'][-1] == 'The BTC bot (acct_b9) saw it.' and v['drop']['peak'] == 1190.0
    # the same while it runs: the poll after the one whose flush read the new id
    third, fourth = bot(tmp_path / 'z'), bot(tmp_path / 'z', BTC, GOLD)
    start(third, T0, 1500.0)
    start(fourth, T0, 1500.0)
    (tmp_path / 'z' / 'acct' / 'safety_block_20261121_150000-cdcd34.json').write_text('{}')
    write_restart(tmp_path / 'z', '20261121_150000-cdcd34')
    third.flush(T0 + 10)
    assert third.poll(T0 + 11, 1500.0)['account_blocked'] is True


def test_a_state_without_an_account_is_accepted_and_a_tracker_without_a_login_checks_none(tmp_path):
    tr = bot(tmp_path, login=None)
    start(tr, T0, 1500.0)
    assert tr.view()['login_tail'] == '...?' and tr._state['login_sha'] is None
    with_login = bot(tmp_path, login=LOGIN)
    assert with_login.load(T0 + 5) is True and with_login._state['peak'] == 1500.0
    tick(with_login, T0 + 6, 1500.0)
    assert read(tmp_path / GOLD / 'state' / 'safety_state.json')['login_sha'] == S.login_sha(LOGIN)
    without = bot(tmp_path, login=None)
    assert without.load(T0 + 7) is True and without._state['peak'] == 1500.0


def test_an_account_folder_that_cannot_be_made_is_not_usable_until_it_can(tmp_path):
    (tmp_path / 'acct').write_text('a file where the folder should be')
    tr = bot(tmp_path)
    assert tr.load(T0) is False
    v = tr.poll(T0 + 1, 1500.0)
    assert v['blocked'] is True and 'cannot be made' in v['error'] and v['state'] == 'error'
    tr.flush(T0 + 1)                                                 # does not raise either
    (tmp_path / 'acct').unlink()
    assert tr.load(T0 + 2) is True
    assert tick(tr, T0 + 3, 1500.0)['blocked'] is False


def test_a_tracker_without_a_state_path_saves_nothing_and_still_works(tmp_path):
    tr = S.Tracker(str(tmp_path / 'acct'), None, GOLD, None, limits(), confirm_s=0.0)
    assert tr.load(T0) is True
    assert tr.poll(T0, 1500.0, [], T0)['blocked'] is False
    v = tr.poll(T0 + 60, 1190.0, [], T0 + 60)                        # confirm_s 0: judged in the poll that sees it
    tr.flush(T0 + 60)
    assert v['blocked'] and v['partner'] is None and (tmp_path / 'acct' / 'safety_block_start.json').exists()
    assert not (tmp_path / GOLD).exists()


def test_a_state_file_that_lacks_a_number_starts_counting_again_and_keeps_count_and_blocks(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    settle(tr, T0 + 10, 1400.0)
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    state = read(state_file)
    del state['peak']                                                # (edited by hand, or cut by another version)
    state['day0'] = 'a lot'
    state_file.write_text(json.dumps(state))
    again = bot(tmp_path)
    assert again.load(T0 + 100) is True
    v = again.view()
    assert v['bot_blocked'] and v['streak']['count'] == 3 and v['drop']['peak'] is None and v['drop']['pct'] == 0.0
    v = tick(again, T0 + 101, 1400.0)                                # no crash on the missing number
    assert v['error'] is None and v['bot_blocked'] and v['drop']['peak'] == 1400.0 and v['day']['day0'] == 1400.0
    assert again.on_trade_closed(T0 + 102, 2, -1.0)['streak']['count'] == 3          # still counted before


@pytest.mark.parametrize('damaged', ['yes', True, 7, [], {}, {'rule': 'UNKNOWN'}])
def test_a_damaged_block_entry_in_the_state_file_still_blocks(tmp_path, damaged):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    state_file = tmp_path / GOLD / 'state' / 'safety_state.json'
    state = read(state_file)
    state['bot_block'] = damaged                                     # anything but null is a block
    state['account_block'] = damaged
    state_file.write_text(json.dumps(state))
    again = bot(tmp_path)
    assert again.load(T0 + 100) is True
    v = tick(again, T0 + 101, 1500.0)
    assert v['blocked'] and v['bot_blocked'] and v['account_blocked'] and v['error'] is None
    assert v['reasons'][-1].startswith('The gold bot opens no new trade: it lost too many trades in a row.')
    assert (tmp_path / 'acct' / 'safety_block_start.json').exists()  # the account block gets its file


# ───────────────────────────── none of the five raises ─────────────────────────────

class Fault(RuntimeError):
    pass


def broken(*a, **k):
    raise Fault('a fault nobody expected')


def test_a_fault_inside_poll_becomes_an_error_that_blocks_while_on_and_only_while_on(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    good = S.decide
    monkeypatch.setattr(S, 'decide', broken)
    v = tr.poll(T0 + 10, 1500.0)                                     # does not raise
    assert v['blocked'] is True and v['state'] == 'error' and v['since'] == T0 + 10 and v['at'] == T0 + 10
    assert v['error'] == 'the safety check: Fault: a fault nobody expected'
    assert v['reasons'] == [S.ERROR_SENTENCE] and v['account_blocked'] is False and tr.view() is v
    tr.flush(T0 + 10)
    assert read(tmp_path / 'acct' / 'safety_status_acct_x9.json')['error'] == v['error']
    v = tr.poll(T0 + 11, 1500.0)
    assert v['blocked'] and v['since'] == T0 + 10                    # failing since the first time
    write_switch(tmp_path, False)                                    # the owner turns the safety OFF
    tr.flush(T0 + 11)
    v = tr.poll(T0 + 12, 1500.0)
    assert v['blocked'] is False and v['enabled'] is False and v['error'] is not None
    assert v['reasons'][0].startswith('No limit is applied')
    write_switch(tmp_path, True)
    tr.flush(T0 + 12)
    assert tr.poll(T0 + 13, 1500.0)['blocked'] is True
    monkeypatch.setattr(S, 'decide', good)                           # it works again: the error is gone
    v = tr.poll(T0 + 14, 1500.0)
    assert v['blocked'] is False and v['error'] is None and v['state'] == 'on'
    assert v['reasons'] == ['Watching account ...5678. New trades are allowed.']


def test_when_not_even_the_view_can_be_made_the_bot_still_gets_one_with_every_key(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    good = tr.view()
    monkeypatch.setattr(S, 'build_view', broken)
    v = tr.poll(T0 + 10, 1500.0)
    assert sorted(v) == sorted(good) and sorted(v['drop']) == sorted(good['drop'])
    assert sorted(v['day']) == sorted(good['day']) and sorted(v['streak']) == sorted(good['streak'])
    assert v['blocked'] is True and v['enabled'] is True and v['reasons'] == [S.ERROR_SENTENCE]
    assert v['error'] == 'the safety check: Fault: a fault nobody expected' and v['since'] == T0 + 10
    assert v['limits'] == good['limits'] and v['login_tail'] == '...5678' and v['account_dir'] == good['account_dir']
    json.dumps(v, allow_nan=False)
    write_switch(tmp_path, False)
    tr.flush(T0 + 10)                                                # (the status cannot be made either: no raise)
    v = tr.poll(T0 + 11, 1500.0)
    assert v['blocked'] is False and v['enabled'] is False and v['state'] == 'off'
    monkeypatch.undo()
    assert tr.poll(T0 + 12, 1500.0)['error'] is None


def test_a_fault_while_counting_a_trade_or_noting_another_program_is_an_error_too(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    monkeypatch.setattr(S, 'count_trade', broken)
    v = tr.on_trade_closed(T0 + 5, 'a', -1.0)
    assert v['blocked'] and v['error'] == 'counting a closed trade: Fault: a fault nobody expected'
    assert tr.poll(T0 + 6, 1500.0)['error'] is None                  # a poll that works clears it
    monkeypatch.setattr(S, 'note_other', broken)
    v = tr.note_other_program(T0 + 7, 'another program holds 1 trade of its own on XAUUSDm')
    assert v['blocked'] and v['error'] == 'noting another program: Fault: a fault nobody expected'
    for odd_time in (None, 'now', [1]):                              # even a time that is no time does not raise
        assert tr.poll(odd_time, 1500.0)['blocked'] is True
        assert tr.on_trade_closed(odd_time, 'b', -1.0)['blocked'] is True
        assert tr.note_other_program(odd_time, 'x')['blocked'] is True
        assert tr.flush(odd_time) is None
    assert tr.poll(T0 + 8, 1500.0)['error'] is None


def test_a_fault_inside_flush_does_not_raise_shows_at_the_next_poll_and_does_not_stop_the_other_steps(tmp_path,
                                                                                                    monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    monkeypatch.setattr(tr, '_flush_status', broken)
    tr.poll(T0 + 10, 1400.0)
    assert tr.flush(T0 + 10) is None
    assert read(tmp_path / GOLD / 'state' / 'safety_state.json')['seen_balance'] == 1400.0   # the state was saved
    v = tr.poll(T0 + 11, 1400.0)
    assert v['blocked'] is True and v['state'] == 'error' and v['since'] == T0 + 10
    assert v['error'] == 'the safety files: Fault: a fault nobody expected'
    monkeypatch.undo()
    tr.flush(T0 + 11)                                                # every step works again
    v = tr.poll(T0 + 12, 1400.0)
    assert v['error'] is None and v['blocked'] is False
    monkeypatch.setattr(tr, '_flush_folder', broken)                 # the step that reads what the owner pressed
    write_switch(tmp_path, False)
    tr.flush(T0 + 13)
    v = tr.poll(T0 + 14, 1400.0)
    assert v['blocked'] is True and v['enabled'] is True             # it cannot see the OFF: it stays on the safe side


def test_a_fault_inside_load_is_not_usable_and_is_tried_again(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    monkeypatch.setattr(S, '_read_json', broken)
    assert tr.load(T0) is False
    v = tr.view()
    assert v['blocked'] is True and 'Fault: a fault nobody expected' in v['error'] and v['at'] == T0
    assert tr.poll(T0 + 1, 1500.0)['blocked'] is True and tr.load('soon') is False
    monkeypatch.undo()
    assert tr.load(T0 + 2) is True and tick(tr, T0 + 3, 1500.0)['error'] is None


def test_a_rise_that_cannot_be_judged_for_ten_minutes_is_a_failing_check(tmp_path):
    """A rise waits for the cash history however long it takes (it may be a deposit), and while it waits nothing
    new is judged: 500 paid in and 400 of it lost would go unseen. After ten minutes of polls without a readable
    history the bot says that it cannot check, and opens nothing while the safety is ON."""
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    tick(tr, T0 + 100, 2000.0)                                       # paid in, or won: only the history tells
    for dt in range(105, 700, 5):                                    # ...and most of it is gone again
        v = tick(tr, T0 + dt, 1600.0)
        assert v['pending'] and not v['hold'] and not v['blocked'] and v['error'] is None
    assert v['drop']['balance'] == 1500.0                            # nothing was judged: the history cannot be read
    v = tick(tr, T0 + 700, 1600.0)                                   # ten minutes of polls
    assert v['blocked'] is True and v['state'] == 'error' and v['since'] == T0 + 100
    assert v['error'] == ("the account's cash history could not be read since 14:06 UTC, so a change of the balance "
                          'cannot be judged')
    assert v['reasons'] == [S.ERROR_SENTENCE] and v['blocked_scope'] is None
    v = tick(tr, T0 + 800, 1600.0, [{'ticket': 3, 'amount': 500.0, 'time': T0 + 99.5}], T0 + 799.5)
    assert v['error'] is None and v['pending'] is False              # the history reads again: judged at once
    assert v['account_blocked'] is True and v['reasons'][1].startswith('The account fell 20.0% below its high')


def test_only_time_the_bot_really_watched_counts_towards_that(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    tick(tr, T0 + 100, 2000.0)
    assert tick(tr, T0 + 5000, 2000.0)['error'] is None              # the polls paused for an hour: not ten minutes
    for dt in range(5000, 5300, 5):
        assert tick(tr, T0 + dt, None)['error'] is None              # polls without a balance are no watching
    for dt in range(5300, 5880, 10):
        assert tick(tr, T0 + dt, 2000.0)['error'] is None
    again = bot(tmp_path)                                            # the bot is started again: ten minutes anew
    assert again.load(T0 + 5890) is True
    for dt in range(5890, 6490, 10):
        assert tick(again, T0 + dt, 2000.0)['error'] is None
    assert tick(again, T0 + 6500, 2000.0)['error'] is not None
    # a fall never gets there: it is taken as a loss after a minute
    other = bot(tmp_path / 'b')
    start(other, T0, 1500.0)
    for dt in range(100, 900, 5):
        v = tick(other, T0 + dt, 1450.0)
    assert v['error'] is None and v['pending'] is False and v['drop']['balance'] == 1450.0
    # and with both account rules off there is nothing the history could change: no failing check
    off = bot(tmp_path / 'c', lim=S.Limits(None, None, 3))
    start(off, T0, 1500.0)
    for dt in range(100, 900, 5):
        v = tick(off, T0 + dt, 2000.0)
    assert v['error'] is None and v['pending'] is True and v['blocked'] is False


def test_what_a_bot_remembers_for_the_journal_and_writes_to_the_audit_file_is_bounded(tmp_path):
    """A fault that made a bot trip and start afresh on every poll must not fill the disk or the memory."""
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    hour = (T0 // 3600) * 3600 + 3600                                # a full hour: 15:00 to 16:00
    lines_before = len(audit(tmp_path))
    for i in range(120):
        write_restart(tmp_path, f'20261121_1500{i % 60:02d}-{i:06x}', scope='bot')
        tr.flush(hour + i * 10)
        tr.poll(hour + i * 10 + 1, 1500.0)                           # a fresh start (of one bot)...
        tr.note_other_program(hour + i * 10 + 2, 'another program holds 1 trade of its own on XAUUSDm')   # ...a block
        tr.flush(hour + i * 10 + 3)
    lines = audit(tmp_path)[lines_before:]
    assert len(lines) == 30                                          # 240 things happened in that hour
    assert len(tr._events) == 200 and len(tr.take_events()) == 200 and tr.take_events() == []
    tr.note_other_program(hour + 3600 + 5, 'x')                      # (blocked already: nothing new)
    write_restart(tmp_path, '20261121_160100-ffffff', scope='bot')
    tr.flush(hour + 3600 + 10)
    tr.poll(hour + 3600 + 11, 1500.0)
    tr.flush(hour + 3600 + 12)
    lines = audit(tmp_path)[lines_before:]
    assert lines[30] == {'at': S._iso(hour + 3600 + 12), 'by': 'bot acct_x9', 'more': 210}   # said once, next hour
    assert lines[31]['event'] == 'fresh_start' and len(lines) == 32


def test_a_file_step_that_failed_is_tried_again_after_the_clock_was_set_back(tmp_path, monkeypatch):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    real = S._replace_retry
    tries = []

    def refuse_state(src, dst, *a, **k):
        if dst.endswith('safety_state.json'):
            tries.append(dst)
            raise PermissionError(13, 'Permission denied')
        return real(src, dst, *a, **k)
    monkeypatch.setattr(S, '_replace_retry', refuse_state)
    tick(tr, T0 + 10, 1400.0)
    tick(tr, T0 + 11, 1400.0)
    assert len(tries) == 1                                           # the next try is due at T0 + 15
    tick(tr, T0 - 3600, 1400.0)                                      # the server's clock was set back an hour
    assert len(tries) == 2                                           # ...which must not mean "wait an hour"


def test_the_files_that_matter_are_on_the_disk_before_they_replace_the_old_ones(tmp_path, monkeypatch):
    """A power cut right after a move must not leave an empty state or restart file under the real name."""
    synced = []
    real_open, real_fsync, real_replace = builtins.open, os.fsync, os.replace
    names_by_fd = {}

    def spy_open(path, mode='r', *a, **k):
        f = real_open(path, mode, *a, **k)
        if 'w' in mode:
            names_by_fd[f.fileno()] = os.path.basename(str(path)).split('.json')[0]
        return f
    monkeypatch.setattr(S, 'open', spy_open, raising=False)
    monkeypatch.setattr(os, 'fsync', lambda fd: (synced.append(names_by_fd.get(fd)), real_fsync(fd))[1])
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    assert 'safety_state' in synced and 'safety_status_acct_x9' not in synced
    del synced[:]
    acct = str(tmp_path / 'acct')
    assert S.press(acct, 'off', None, 'command line', T0 + 5, need_pin=False)[0] is True
    assert S.press(acct, 'on', None, 'command line', T0 + 6, need_pin=False)[0] is True
    assert synced == ['safety_switch', 'safety_restart', 'safety_switch']
    monkeypatch.setattr(os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError(22, 'Invalid argument')))
    assert S.press(acct, 'off', None, 'command line', T0 + 7, need_pin=False)[0] is True     # a flush that fails
    assert read(tmp_path / 'acct' / 'safety_switch.json')['enabled'] is False                # is no failed write


def test_what_is_written_is_strict_json():
    with pytest.raises(ValueError):
        S._dumps({'peak': float('nan')})                             # never a file another reader cannot parse
    assert json.loads(S._dumps({'b': 1, 'a': [1.5, None, 'x']})) == {'a': [1.5, None, 'x'], 'b': 1}


# ───────────────────────────── what the owner pressed: restart file and switch ─────────────────────────────

def test_a_failed_first_read_of_the_restart_file_after_a_restart_while_blocked_keeps_the_block(tmp_path,
                                                                                               monkeypatch):
    """The review's case: after a restart the first read of the restart file fails for a moment. Read as 'missing'
    it would look like another id, and the bot would start afresh by itself: the block and the high gone."""
    write_restart(tmp_path, '20261120_101500-a1b2c3')
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    for i in range(3):
        tr.on_trade_closed(T0 + 5 + i, i, -1.0)
    settle(tr, T0 + 10, 1190.0)
    assert tr.view()['period'] == '20261120_101500-a1b2c3' and tr.view()['blocked']
    again = bot(tmp_path)
    with refusing(monkeypatch, lambda p: p.endswith('safety_restart.json'), modes='r'):
        assert again.load(T0 + 100) is True
        for dt in (101, 102, 103):
            v = tick(again, T0 + dt, 1190.0)
            assert v['blocked'] and v['account_blocked'] and v['bot_blocked']
            assert v['period'] == '20261120_101500-a1b2c3' and v['drop']['peak'] == 1500.0
    v = tick(again, T0 + 104, 1190.0)                                # readable again: the same id, nothing happens
    v = tick(again, T0 + 105, 1190.0)
    assert v['blocked'] and v['streak']['count'] == 3 and v['drop']['peak'] == 1500.0
    assert 'fresh_start' not in [e['event'] for e in again.take_events()]


@pytest.mark.parametrize('content', [b'', b'{"id": ', b'{"id": "../../x", "scope": "account"}', b'{"id": 5}',
                                     b'{"scope": "account"}', b'[]', b'\xff\xfe'])
def test_a_restart_file_that_is_half_written_or_wrong_starts_nothing(tmp_path, content):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1190.0)
    (tmp_path / 'acct' / 'safety_restart.json').write_bytes(content)
    tr.flush(T0 + 20)
    v = tick(tr, T0 + 21, 1190.0)
    assert v['blocked'] and v['period'] == 'start' and v['drop']['peak'] == 1500.0
    c = S.read_controls(str(tmp_path / 'acct'))
    assert c['readable'] is False and c['period'] is None and c['block'] is None
    assert sorted(n for n in acct_files(tmp_path) if 'block' in n) == ['safety_block_start.json']    # no odd file name


def test_a_restart_file_that_disappears_starts_nothing(tmp_path):
    write_restart(tmp_path, '20261120_101500-a1b2c3')
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1190.0)
    (tmp_path / 'acct' / 'safety_restart.json').unlink()
    tr.flush(T0 + 20)
    v = tick(tr, T0 + 21, 1190.0)
    assert v['blocked'] and v['period'] == '20261120_101500-a1b2c3'  # not back to the id 'start'


def test_an_unblock_of_the_account_is_taken_by_both_bots_at_their_next_poll(tmp_path):
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD)
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    for i in range(3):
        btc.on_trade_closed(T0 + 5 + i, i, -1.0)
    settle(gold, T0 + 10, 1190.0)
    settle(btc, T0 + 10, 1190.0)
    assert gold.view()['blocked'] and btc.view()['bot_blocked'] and btc.view()['account_blocked']
    write_restart(tmp_path, '20261121_141000-dddddd')
    for tr in (gold, btc):
        v = tick(tr, T0 + 300, 1190.0)                               # this poll still has the old id...
        assert v['blocked'] is True
        v = tick(tr, T0 + 301, 1190.0)                               # ...the next one has read the press
        assert v['blocked'] is False and v['period'] == '20261121_141000-dddddd'
        assert v['drop'] == {'pct': 0.0, 'limit': 20.0, 'peak': 1190.0, 'peak_at': T0 + 301, 'balance': 1190.0}
        assert v['day']['day0'] == 1190.0 and v['day']['since'] == 'restart' and v['streak']['count'] == 0
        assert v['day']['start_balance'] == 1500.0                   # today's own start is not moved
        assert tr.needs_cash() is True and tr.cash_since() == T0 + 301 - 86400
    fresh = [a for a in audit(tmp_path) if a['event'] == 'fresh_start' and a['scope'] == 'account']
    assert sorted(a['by'] for a in fresh) == ['bot acct_b9', 'bot acct_x9']
    assert all(a['id'] == '20261121_141000-dddddd' and a['balance'] == 1190.0 for a in fresh)
    # the old block file is still there and blocks nobody
    assert (tmp_path / 'acct' / 'safety_block_start.json').exists()
    assert tick(gold, T0 + 302, 1190.0)['blocked'] is False


def test_an_unblock_of_one_bot_leaves_the_account_figures_and_the_other_bot_alone(tmp_path):
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD)
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    settle(gold, T0 + 10, 1400.0)
    settle(btc, T0 + 10, 1400.0)
    for i in range(3):
        gold.on_trade_closed(T0 + 20 + i, i, -1.0)
    btc.on_trade_closed(T0 + 20, 'x', -1.0)
    btc.on_trade_closed(T0 + 21, 'y', -1.0)
    tick(gold, T0 + 30, 1400.0), tick(btc, T0 + 30, 1400.0)
    assert gold.view()['bot_blocked'] and not btc.view()['blocked']
    write_restart(tmp_path, '20261121_141000-eeeeee', scope='bot')
    for tr in (gold, btc):
        tick(tr, T0 + 300, 1400.0)
        v = tick(tr, T0 + 301, 1400.0)
        assert v['blocked'] is False and v['period'] == '20261121_141000-eeeeee'
        assert v['drop']['peak'] == 1500.0 and round(v['drop']['pct'], 2) == 6.67       # the high stays
        assert v['day']['day0'] == 1500.0 and v['started_at'] == T0
    assert gold.view()['streak']['count'] == 0 and btc.view()['streak']['count'] == 2


def test_the_switch_off_blocks_nothing_and_on_again_by_a_new_id_starts_fresh(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1190.0)
    assert tr.view()['blocked']
    write_switch(tmp_path, False)
    tick(tr, T0 + 20, 1190.0)
    v = tick(tr, T0 + 21, 1190.0)
    assert v['enabled'] is False and v['blocked'] is False and v['hold'] is False and v['state'] == 'off'
    assert v['account_blocked'] is True
    v = settle(tr, T0 + 30, 800.0)                                   # tracking goes on, nothing trips
    assert v['blocked'] is False and v['drop']['balance'] == 800.0 and round(v['drop']['pct'], 1) == 46.7
    assert [n for n in acct_files(tmp_path) if n.startswith('safety_block_')] == ['safety_block_start.json']
    write_restart(tmp_path, '20261121_150000-ffffff')                # press('on'): the id first...
    write_switch(tmp_path, True)                                     # ...then the switch
    tick(tr, T0 + 100, 800.0)
    v = tick(tr, T0 + 101, 800.0)
    assert v['enabled'] and v['blocked'] is False and v['drop'] == {
        'pct': 0.0, 'limit': 20.0, 'peak': 800.0, 'peak_at': T0 + 101, 'balance': 800.0}
    assert [e['enabled'] for e in tr.take_events() if e['event'] == 'switch'] == [False, True]


@pytest.mark.parametrize('content', [b'', b'{"enabled": ', b'{"enabled": "false"}', b'{"enabled": 0}', b'[]'])
def test_a_switch_file_that_cannot_be_read_keeps_the_last_known_value(tmp_path, content):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    write_switch(tmp_path, False)
    tick(tr, T0 + 5, 1500.0)
    assert tick(tr, T0 + 6, 1500.0)['enabled'] is False
    (tmp_path / 'acct' / 'safety_switch.json').write_bytes(content)
    tick(tr, T0 + 7, 1500.0)
    assert tick(tr, T0 + 8, 1500.0)['enabled'] is False              # still OFF: nobody said ON
    # a new process whose first read fails: the value of its state file
    again = bot(tmp_path)
    assert again.load(T0 + 9) is True and tick(again, T0 + 10, 1500.0)['enabled'] is False
    c = S.read_controls(str(tmp_path / 'acct'))
    assert c['readable'] is False and c['enabled'] is True           # (who has no last value: the safe side, ON)
    (tmp_path / 'acct' / 'safety_switch.json').unlink()              # missing is an answer: the default
    tick(again, T0 + 11, 1500.0)
    assert tick(again, T0 + 12, 1500.0)['enabled'] is True


def test_a_first_start_with_an_unreadable_switch_file_takes_the_default(tmp_path):
    (tmp_path / 'acct').mkdir()
    (tmp_path / 'acct' / 'safety_switch.json').write_bytes(b'{"enabled": ')
    on = bot(tmp_path)
    assert on.load(T0) is True and tick(on, T0 + 1, 1500.0)['enabled'] is True
    off = bot(tmp_path, BTC, GOLD, default_on=False)
    assert off.load(T0) is True and tick(off, T0 + 1, 1500.0)['enabled'] is False
    (tmp_path / 'acct' / 'safety_switch.json').unlink()
    tick(off, T0 + 2, 1500.0)
    assert tick(off, T0 + 3, 1500.0)['enabled'] is False             # missing: this branch's default


# ───────────────────────────── the cash read the bot owes ─────────────────────────────

def test_needs_cash_and_cash_since(tmp_path):
    tr = bot(tmp_path)
    assert tr.needs_cash() is False and tr.cash_since() == 0.0       # before load: nothing to read
    assert tr.load(T0) is True
    assert tr.needs_cash() is False and tr.cash_since() == T0 - 86400
    tick(tr, T0, None)                                               # no balance yet: not started
    assert tr.needs_cash() is False
    tick(tr, T0 + 1, 1500.0)
    assert tr.needs_cash() is True and tr.cash_since() == T0 + 1 - 86400     # the first read: a day back
    tick(tr, T0 + 2, 1500.0, None, None)                             # the read failed
    assert tr.needs_cash() is True
    tick(tr, T0 + 3, 1500.0, [], T0 + 2.5)
    assert tr.needs_cash() is False and tr.cash_since() == T0 + 2.5 - 3600   # then an hour before the last good read
    tick(tr, T0 + 10, 1450.0)
    assert tr.needs_cash() is True                                   # a change is being checked
    tick(tr, T0 + 11, 1450.0, [], T0 + 10.5)
    assert tr.needs_cash() is True and tr.cash_since() == T0 + 10.5 - 3600
    tick(tr, T0 + 14, 1450.0, [], T0 + 13.5)
    assert tr.needs_cash() is False


def test_the_events_for_the_journal(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    assert [e['event'] for e in tr.take_events()] == ['fresh_start', 'cash_start']
    assert tr.take_events() == []
    tick(tr, T0 + 10, 1000.0)                                        # a withdrawal: held while it is checked
    for dt in (11, 12, 15, 21):
        tick(tr, T0 + dt, 1000.0)                                    # the reads fail for 11 s
    v = tick(tr, T0 + 22, 1000.0, [{'ticket': 5, 'amount': -500.0, 'time': T0 + 9.6}], T0 + 21.5)
    assert v['hold'] is False and v['blocked'] is False
    ev = tr.take_events()
    assert [e['event'] for e in ev] == ['hold', 'cash', 'hold_end']
    assert ev[0]['why'] == 'limit' and ev[0]['since'] == T0 + 10 and ev[0]['seconds'] == 11.0
    assert ev[1]['found_after_s'] == 11.5 and ev[1]['counted'] is True and ev[1]['branch'] == GOLD
    assert ev[2]['seconds'] == 12.0
    tr.on_trade_closed(T0 + 30, 'a', -5.0)
    assert [(e['event'], e['in_a_row']) for e in tr.take_events()] == [('trade', 1)]


# ───────────────────────────── the other bot of the account ─────────────────────────────

def test_the_partner_part_of_the_view_comes_from_the_other_bots_status_file(tmp_path):
    gold = bot(tmp_path, GOLD, BTC, S.Limits(20.0, 10.0, 10))
    btc = bot(tmp_path, BTC, GOLD, S.Limits(20.0, 10.0, 9))          # its own losing-trades limit: no difference
    start(gold, T0, 1500.0)
    assert gold.view()['partner'] is None                            # the BTC bot has never run
    start(btc, T0 + 2, 1500.0)
    settle(btc, T0 + 10, 1440.0)
    v = tick(gold, T0 + 15, 1440.0)
    v = tick(gold, T0 + 16, 1440.0)
    assert v['partner'] == {'branch': BTC, 'seen_at': T0 + 14, 'blocked': False, 'bot_blocked': False,
                            'drop_pct': pytest.approx(4.0), 'day_pct': pytest.approx(4.0), 'limits_differ': False,
                            'account_differs': False, 'period': 'start', 'stale': False}
    v = tick(gold, T0 + 80, 1440.0)                                  # the BTC bot has stopped: 66 s without a status
    assert v['partner']['stale'] is True and v['partner']['seen_at'] == T0 + 14
    (tmp_path / 'acct' / 'safety_status_acct_b9.json').write_bytes(b'{"at": ')       # half a file: the last one stays
    tick(gold, T0 + 81, 1440.0)
    assert tick(gold, T0 + 81.5, 1440.0)['partner']['seen_at'] == T0 + 14
    (tmp_path / 'acct' / 'safety_status_acct_b9.json').unlink()
    tick(gold, T0 + 82, 1440.0)
    assert tick(gold, T0 + 83, 1440.0)['partner'] is None


def test_the_partner_with_other_account_limits_or_another_account(tmp_path):
    gold = bot(tmp_path, GOLD, BTC, S.Limits(20.0, 10.0, 10), login=12345678)
    other_limits = bot(tmp_path, BTC, GOLD, S.Limits(25.0, 10.0, 9), login=12345678)
    start(gold, T0, 1500.0)
    start(other_limits, T0, 1500.0)
    tick(gold, T0 + 2, 1500.0)
    p = tick(gold, T0 + 3, 1500.0)['partner']
    assert p['limits_differ'] is True and p['account_differs'] is False
    other_account = bot(tmp_path / 'x', BTC, GOLD, S.Limits(20.0, 10.0, 9), login=99995678)
    other_account.account_dir = gold.account_dir                     # same folder, another account, same last digits
    start(other_account, T0 + 10, 700.0)
    tick(gold, T0 + 12, 1500.0)
    p = tick(gold, T0 + 13, 1500.0)['partner']
    assert p['account_differs'] is True and p['limits_differ'] is False


def test_the_status_of_a_stopped_bot_is_not_refreshed_by_the_other(tmp_path):
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD)
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    for dt in range(2, 200, 7):
        tick(gold, T0 + dt, 1500.0)                                  # only gold runs
    assert read(tmp_path / 'acct' / 'safety_status_acct_b9.json')['at'] <= T0 + 1
    assert read(tmp_path / 'acct' / 'safety_status_acct_x9.json')['at'] >= T0 + 170
    st = S.read_statuses(str(tmp_path / 'acct'))
    assert sorted(st) == [BTC, GOLD] and st[GOLD]['partner']['stale'] is True


# ───────────────────────────── read_controls, read_statuses, ensure_pin ─────────────────────────────

def test_read_controls_of_a_folder_that_is_not_there_gives_the_defaults(tmp_path):
    c = S.read_controls(str(tmp_path / 'nowhere'))
    assert c == {'enabled': True, 'period': 'start', 'scope': None, 'block': None, 'locked_until': None,
                 'pin_set': False, 'readable': True, 'pressed_at': None, 'pressed_by': None, 'pressed_why': None,
                 'switched_at': None, 'switched_by': None}
    assert S.read_controls(str(tmp_path / 'nowhere'), default_on=False)['enabled'] is False
    assert not (tmp_path / 'nowhere').exists()                       # reading creates nothing
    assert S.read_statuses(str(tmp_path / 'nowhere')) == {}
    for junk in (None, 5, b'x'):
        assert S.read_controls(junk)['enabled'] is True              # never raises: the poll loop calls it


def test_read_controls_answers_even_when_reading_goes_wrong(tmp_path, monkeypatch):
    """app.py calls it in the poll loop when it has no Tracker: it must get an answer, and the safe one."""
    (tmp_path / 'acct').mkdir()
    write_switch(tmp_path, False)
    def broken(*a, **k):
        raise RuntimeError('a fault nobody expected')
    monkeypatch.setattr(S, '_read_restart', broken)
    c = S.read_controls(str(tmp_path / 'acct'))
    assert c['readable'] is False and c['enabled'] is True and c['block'] is None and c['period'] is None
    assert S.read_controls(str(tmp_path / 'acct'), default_on=False)['enabled'] is False


def test_read_controls_says_what_the_files_say(tmp_path):
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    acct = str(tmp_path / 'acct')
    write_restart(tmp_path, '20261121_141000-abcdef', scope='bot', by='dashboard acct_x9 from 10.0.0.9')
    write_switch(tmp_path, False)
    (tmp_path / 'acct' / 'safety_pin.txt').write_text('135790')
    (tmp_path / 'acct' / 'safety_lockout.json').write_text(json.dumps({'wrong': 0, 'locked_until': T0 + 900}))
    c = S.read_controls(acct)
    assert c['enabled'] is False and c['period'] == '20261121_141000-abcdef' and c['scope'] == 'bot'
    assert c['block'] is None and c['locked_until'] == T0 + 900 and c['pin_set'] is True and c['readable'] is True
    assert c['pressed_at'] == T0 + 300 and c['pressed_by'] == 'dashboard acct_x9 from 10.0.0.9'
    assert c['switched_at'] == T0 + 300 and c['switched_by'] == 'test'
    tick(tr, T0 + 400, 1500.0)
    write_switch(tmp_path, True)
    tick(tr, T0 + 401, 1500.0)
    settle(tr, T0 + 402, 1190.0)
    blk = S.read_controls(acct)['block']
    assert blk['period'] == '20261121_141000-abcdef' and blk['readable'] is True and blk['branch'] == GOLD
    assert blk['rules'] == ['DROP', 'DAY'] and blk['at'] == T0 + 406 and blk['numbers']['balance'] == 1190.0
    assert blk['reasons'][0].startswith('The account fell 20.7% below its high') and blk['file_time'] > 0
    assert not found(json.dumps(c), 'PIN') and not found(json.dumps(S.read_controls(acct)), '135790')


def test_read_statuses_skips_what_it_cannot_read(tmp_path):
    gold, btc = bot(tmp_path), bot(tmp_path, BTC, GOLD)
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    d = tmp_path / 'acct'
    (d / 'safety_status_acct_q1.json').write_bytes(b'{"at": 1')     # half a file
    (d / 'safety_status_acct_q2.json').write_text('[1, 2]')
    (d / 'safety_status_named_by_file.json').write_text('{"at": 5}')
    (d / 'safety_status_x.json.123.0a0b0c0d.tmp').write_text('{"at": 6}')            # a temp file is not a status
    st = S.read_statuses(str(d))
    assert sorted(st) == [BTC, GOLD, 'named_by_file']
    assert st[GOLD]['branch'] == GOLD and st[GOLD]['period'] == 'start' and st[BTC]['login_tail'] == '...5678'


def test_ensure_pin_makes_six_digits_once_and_never_touches_an_existing_file(tmp_path):
    acct = tmp_path / 'deep' / 'acct'
    assert S.ensure_pin(str(acct)) is None                           # it never returns the PIN
    pin = (acct / 'safety_pin.txt').read_text()
    assert re.fullmatch(r'\d{6}\n', pin) and S.pin_path(str(acct)) == str(acct / 'safety_pin.txt')
    assert S.ensure_pin(str(acct)) is None and (acct / 'safety_pin.txt').read_text() == pin
    (acct / 'safety_pin.txt').write_text('my own pin')               # the owner's file, even a bad one
    S.ensure_pin(str(acct))
    assert (acct / 'safety_pin.txt').read_text() == 'my own pin'
    assert S.read_controls(str(acct))['pin_set'] is False            # (a space: not a usable PIN)
    assert len({(S.ensure_pin(str(tmp_path / f'a{i}')), (tmp_path / f'a{i}' / 'safety_pin.txt').read_text())[1]
                for i in range(20)}) > 15                            # random, not a fixed number
    (tmp_path / 'blocked').write_text('a file, not a folder')
    assert S.ensure_pin(str(tmp_path / 'blocked')) is None           # never raises
    assert S.ensure_pin(str(tmp_path / 'blocked' / 'acct')) is None


def test_two_dashboards_starting_at_once_make_one_pin(tmp_path):
    acct = str(tmp_path / 'acct')
    gate = threading.Barrier(8)

    def go():
        gate.wait()
        S.ensure_pin(acct)
    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert os.listdir(acct) == ['safety_pin.txt']
    assert re.fullmatch(r'\d{6}\n', (tmp_path / 'acct' / 'safety_pin.txt').read_text())


# ───────────────────────────── Windows: a move that is refused for a moment ─────────────────────────────

def test_a_refused_move_is_tried_again_briefly_and_then_given_up(tmp_path, monkeypatch):
    naps = []

    class Clock:
        @staticmethod
        def sleep(s):
            naps.append(s)
    monkeypatch.setattr(S, 'time', Clock)
    real = os.replace
    fails = {'n': 3}

    def replace(src, dst):
        if fails['n'] > 0:
            fails['n'] -= 1
            raise PermissionError(13, 'Permission denied')           # a reader has the old file open
        return real(src, dst)
    monkeypatch.setattr(os, 'replace', replace)
    target = tmp_path / 'acct' / 'safety_switch.json'
    S._write_atomic(str(target), '{"enabled": true}')
    assert target.read_text() == '{"enabled": true}' and naps == [0.005, 0.01, 0.02]
    assert os.listdir(tmp_path / 'acct') == ['safety_switch.json']
    fails['n'] = 99
    del naps[:]
    with pytest.raises(PermissionError):
        S._write_atomic(str(target), '{"enabled": false}')
    assert naps == list(S._REPLACE_WAITS_S) and sum(naps) < 0.3      # about a quarter of a second, then it gives up
    assert target.read_text() == '{"enabled": true}'                 # the old file is whole
    assert os.listdir(tmp_path / 'acct') == ['safety_switch.json']   # and no temp file is left
    fails['n'] = 0
    monkeypatch.setattr(os, 'replace', lambda s, d: (_ for _ in ()).throw(OSError(errno.ENOSPC, 'full')))
    with pytest.raises(OSError):
        S._write_atomic(str(target), 'x')                            # another error is not retried
    assert naps == list(S._REPLACE_WAITS_S)


def test_every_write_uses_a_temp_file_of_its_own_name(tmp_path, monkeypatch):
    seen = []
    real = os.replace
    monkeypatch.setattr(os, 'replace', lambda s, d: (seen.append((os.path.basename(s), os.path.basename(d))),
                                                    real(s, d))[1])
    tr = bot(tmp_path)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1400.0)
    assert len(seen) >= 4 and len({s for s, _ in seen}) == len(seen)         # never the same temp name twice
    for tmp, final in seen:
        assert re.fullmatch(re.escape(final) + r'\.\d+\.[0-9a-f]{8}\.tmp', tmp), tmp
        assert tmp.startswith(final + f'.{os.getpid()}.')


def test_old_temp_files_of_a_crash_are_swept_at_load_and_nothing_else_is(tmp_path):
    d = tmp_path / 'acct'
    d.mkdir()
    old = ['safety_status_acct_x9.json.4242.0a1b2c3d.tmp', 'safety_restart.json.17.ffffffff.tmp']
    keep = ['safety_switch.json.99.00000000.tmp',                    # young: a write in progress
            'safety_pin.txt', 'safety_audit.jsonl', 'safety_status_acct_b9.json', 'notes.tmp',
            'safety_status_acct_x9.json.tmp', 'safety_x.json.12.XYZ.tmp', 'account_claim.json']
    for n in old + keep:
        (d / n).write_text('x')
    for n in old + keep[1:]:
        os.utime(d / n, (T0 - 200000, T0 - 200000))
    os.utime(d / keep[0], (T0 - 60, T0 - 60))
    tr = bot(tmp_path)
    assert tr.load(T0) is True
    assert sorted(p.name for p in d.iterdir()) == sorted(keep)


# ───────────────────────────── file names (spec rule 12) and what never goes into a file ─────────────────────────────

def test_no_file_name_the_module_builds_holds_a_character_windows_refuses(tmp_path, monkeypatch):
    built = set()
    real_open, real_replace = builtins.open, os.replace

    def spy_open(path, mode='r', *a, **k):
        built.add(os.path.basename(str(path)))
        return real_open(path, mode, *a, **k)
    monkeypatch.setattr(S, 'open', spy_open, raising=False)
    monkeypatch.setattr(os, 'replace', lambda s, d: (built.update({os.path.basename(s), os.path.basename(d)}),
                                                    real_replace(s, d))[1])
    odd = 'live:1/x*t?2<>|"\\'                                       # a branch name nobody should use
    tr = S.Tracker(str(tmp_path / 'acct'), str(tmp_path / 'bot' / 'state' / 'safety_state.json'), odd, 'b|t:2',
                   limits(), login=LOGIN)
    start(tr, T0, 1500.0)
    settle(tr, T0 + 10, 1190.0)
    S.ensure_pin(str(tmp_path / 'acct'))
    for action in ('unblock', 'off', 'on', 'new-account'):
        S.press(str(tmp_path / 'acct'), action, None, 'command line', T0 + 20, need_pin=False)
    S.press(str(tmp_path / 'acct'), 'off', 'nope', 'dashboard x from 1.2.3.4', T0 + 21)
    tick(tr, T0 + 30, 1190.0)
    tick(tr, T0 + 31, 1190.0, [], T0 + 30.5)                         # counts under the pressed id from here
    settle(tr, T0 + 32, 900.0)                                       # and is blocked under it
    (tmp_path / 'bot' / 'state' / 'safety_state.json').write_text('not json')
    assert bot_at(tmp_path, odd).load(T0 + 40) is True               # put aside as not readable
    other = S.Tracker(str(tmp_path / 'acct'), str(tmp_path / 'bot' / 'state' / 'safety_state.json'), odd, None,
                      limits(), login=555)
    tr.on_trade_closed(T0 + 41, 'k', -1.0)
    tr.flush(T0 + 41)                                                # the running bot writes its state again
    assert other.load(T0 + 50) is True                               # ...and that is put aside as another account's
    on_disk = {p.name for folder in (tmp_path / 'acct', tmp_path / 'bot' / 'state') for p in folder.iterdir()}
    names_ = built | on_disk
    assert len(names_) > 15
    for name in names_:
        assert not (set(name) & FORBIDDEN_IN_A_FILE_NAME), name
        assert re.fullmatch(r'[A-Za-z0-9_.-]+', name), name
    assert 'safety_status_live_1_x_t_2_____.json' in names_
    stamped = [n for n in names_ if '.not-readable-' in n or '.other-account-' in n or n.startswith('safety_block_2')]
    assert len(stamped) >= 3
    for name in stamped:                                             # times in names: yyyymmdd_hhmmss, UTC
        assert re.search(r'20261121_1405\d\d', name), name


def bot_at(tmp_path, branch):
    return S.Tracker(str(tmp_path / 'acct'), str(tmp_path / 'bot' / 'state' / 'safety_state.json'), branch, None,
                     limits(), login=LOGIN)


def test_the_full_account_number_and_the_pin_are_in_no_file(tmp_path):
    """Spec rule 9: files hold the tail ...5678 or the SHA-256 of the number, never the number."""
    acct = str(tmp_path / 'acct')
    gold, btc = bot(tmp_path, login=LOGIN), bot(tmp_path, BTC, GOLD, login=str(LOGIN))
    S.ensure_pin(acct)
    pin = (tmp_path / 'acct' / 'safety_pin.txt').read_text().strip()
    start(gold, T0, 1500.0)
    start(btc, T0, 1500.0)
    for i in range(3):
        gold.on_trade_closed(T0 + 5 + i, i, -1.0)
    settle(gold, T0 + 10, 1190.0)
    tick(btc, T0 + 15, 1190.0)
    S.press(acct, 'unblock', 'wrong1', 'dashboard acct_x9 from 10.0.0.9', T0 + 20)
    S.press(acct, 'unblock', pin, 'dashboard acct_x9 from 10.0.0.9', T0 + 21)
    S.press(acct, 'off', pin, 'dashboard acct_x9 from 10.0.0.9', T0 + 22)
    tick(gold, T0 + 30, 1190.0), tick(btc, T0 + 30, 1190.0)
    files = [p for folder in (tmp_path / 'acct', tmp_path / GOLD / 'state', tmp_path / BTC / 'state')
             for p in folder.iterdir()]
    assert len(files) >= 9
    for p in files:
        text = p.read_text(encoding='utf-8')
        assert not found(text, str(LOGIN)), p.name
        if p.name != 'safety_pin.txt':
            assert not found(text, pin) and not found(text, 'wrong1'), p.name
    assert '...5678' in (tmp_path / 'acct' / 'safety_status_acct_x9.json').read_text()
