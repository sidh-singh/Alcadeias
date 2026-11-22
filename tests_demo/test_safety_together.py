"""
Two bots, two dashboards and a command line on one account folder at the same time, as five real processes
(spec 5.3: who writes what, and what a reader may meet). Each process works through safety.py only and stops with
an error at the first exception or at the first file it finds damaged. One run is on a quiet disk; in the other
every process is also refused file operations at random, the way Windows refuses a read or a move while another
program holds the file. Afterwards the folder must be whole, and one press must bring both bots to the same state.

The processes run this file's worker script from the test's tmp_path with python -B (no bytecode in the branch).

Run:  python3 -B -m pytest tests_demo/test_safety_together.py -q -p no:cacheprovider
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location('safety_tested_together', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()
T0 = datetime(2026, 11, 21, 14, 5, tzinfo=timezone.utc).timestamp()
GOLD, BTC = 'acct_x9', 'acct_b9'
PIN = '864213'

WORKER = r'''
import builtins, importlib.util, json, os, random, sys, traceback
sys.dont_write_bytecode = True
root, role, folder, branch, partner, seed, rounds, faults = sys.argv[1:9]
spec = importlib.util.spec_from_file_location('safety_worker', os.path.join(root, 'safety.py'))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
rng = random.Random(int(seed))
acct = os.path.join(folder, 'acct')
T0, PIN, rounds, faults = float(sys.argv[9]), sys.argv[10], int(rounds), float(faults)

if faults:
    # What Windows does while another program holds a file: a read, a creation or a move is refused.
    real_open, real_replace, real_stat = builtins.open, os.replace, os.stat

    def refuse():
        raise PermissionError(13, 'Permission denied')

    def flaky_open(path, mode='r', *a, **k):
        if 'safety_' in str(path) and rng.random() < faults:
            refuse()
        return real_open(path, mode, *a, **k)

    def flaky_replace(src, dst):
        if rng.random() < faults:
            refuse()
        return real_replace(src, dst)

    def flaky_stat(path, *a, **k):
        if 'safety_block_' in str(path) and rng.random() < faults:
            refuse()
        return real_stat(path, *a, **k)

    S.open = flaky_open
    os.replace, os.stat = flaky_replace, flaky_stat
    S.time.sleep = lambda s: None                       # (the waits between two tries are not what is tested)

KEYS = {'enabled', 'blocked', 'hold', 'pending', 'account_blocked', 'bot_blocked', 'blocked_scope', 'reasons',
        'since', 'period', 'at', 'started_at', 'error', 'drop', 'day', 'streak', 'partner', 'limits', 'account_dir',
        'login_tail'}


def balance_at(i):
    """One account for both bots: it falls 22 % at round 40 and again every 60 rounds after."""
    falls = 0 if i < 40 else 1 + (i - 40) // 60
    return round(1500.0 * 0.78 ** falls, 2)


def bot():
    tr = S.Tracker(acct, os.path.join(folder, branch, 'state', 'safety_state.json'), branch, partner,
                   S.Limits(20.0, 10.0, 3), login=12345678)
    cash, cash_at, trades = None, None, 0
    for i in range(rounds):
        now = T0 + i
        if not tr.load(now):
            assert tr.poll(now, balance_at(i))['blocked'] is True       # no usable safety: nothing opens
            continue
        if faults and rng.random() < 0.02:                              # the process is started again
            tr = S.Tracker(acct, os.path.join(folder, branch, 'state', 'safety_state.json'), branch, partner,
                           S.Limits(20.0, 10.0, 3), login=12345678)
            continue
        view = tr.poll(now, balance_at(i), cash, cash_at, 0)
        assert KEYS <= set(view), sorted(KEYS - set(view))
        assert view['blocked'] in (True, False) and isinstance(view['reasons'], list) and view['reasons']
        assert view['blocked'] == (view['enabled'] and (view['account_blocked'] or view['bot_blocked']
                                                        or view['error'] is not None))
        json.dumps(view, allow_nan=False)
        if not faults:
            assert view['error'] is None, view['error']
        if rng.random() < 0.15:
            trades += 1
            tr.on_trade_closed(now, f'{branch}-{trades}', rng.choice([-5.0, -5.0, 7.0]))
        if rng.random() < 0.01:
            tr.note_other_program(now, 'another program holds 1 trade of its own on its market')
        cash, cash_at = None, None
        if tr.needs_cash() and rng.random() < 0.8:
            assert tr.cash_since() < now
            cash, cash_at = [], now + 0.5
        tr.flush(now)
    assert tr.take_events() is not None


def page():
    by = f'dashboard {branch} from 10.0.0.{seed}'
    for i in range(rounds):
        now = T0 + i
        c = S.read_controls(acct)
        assert c['enabled'] in (True, False) and (c['period'] is None or isinstance(c['period'], str))
        assert c['block'] is None or isinstance(c['block'].get('reasons'), list)
        for name, status in S.read_statuses(acct).items():
            assert status['branch'] == name and isinstance(status['reasons'], list)
        roll = rng.random()
        if roll < 0.25:
            seen = {'period': c['period'], 'enabled': c['enabled']}
            action = rng.choice(['unblock', 'unblock', 'off', 'on'])
            pin = PIN if rng.random() < 0.85 else 'wrong-pin'
            ok, message = S.press(acct, action, pin, by, now, expect=seen)
            assert isinstance(ok, bool) and isinstance(message, str) and message and PIN not in message
            if not faults and pin == PIN and ok:
                assert 'cannot be' not in message, message
        elif roll < 0.3:
            S.ensure_pin(acct)


def command_line():
    for i in range(rounds):
        now = T0 + i
        roll = rng.random()
        if roll < 0.06:
            ok, message = S.press(acct, rng.choice(['unblock', 'on', 'off', 'on']), None, 'command line', now,
                                  need_pin=False)
            assert isinstance(ok, bool) and message
            if not faults:
                assert ok is True, message
        elif roll < 0.3:
            lines = S.status_lines(acct, now)
            assert lines and all(isinstance(line, str) for line in lines) and PIN not in '\n'.join(lines)


try:
    {'bot': bot, 'page': page, 'command_line': command_line}[role]()
except BaseException:
    traceback.print_exc()
    sys.exit(1)
print('done')
'''


def _run_together(tmp_path, rounds, faults):
    (tmp_path / 'acct').mkdir()
    (tmp_path / 'acct' / 'safety_pin.txt').write_text(PIN + '\n')
    script = tmp_path / 'worker.py'
    script.write_text(WORKER, encoding='utf-8')
    jobs = [('bot', GOLD, BTC, 1), ('bot', BTC, GOLD, 2), ('page', GOLD, BTC, 3), ('page', BTC, GOLD, 4),
            ('command_line', GOLD, BTC, 5)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    procs = [subprocess.Popen([sys.executable, '-B', str(script), str(ROOT), role, str(tmp_path), branch, partner,
                               str(seed), str(rounds), str(faults), repr(T0), PIN],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(tmp_path), env=env)
             for role, branch, partner, seed in jobs]
    results = [(job, p.communicate(timeout=120), p.returncode) for job, p in zip(jobs, procs)]
    for job, (out, err), code in results:
        assert code == 0 and out.strip() == 'done', (job, err[-3000:])


def _the_folder_is_whole(tmp_path):
    acct = tmp_path / 'acct'
    names = sorted(p.name for p in acct.iterdir())
    assert not [n for n in names if n.endswith('.tmp')], names           # no temp file left behind
    for name in names:
        assert re.fullmatch(r'[A-Za-z0-9_.-]+', name), name
    restart = json.loads((acct / 'safety_restart.json').read_text())     # the press files: whole JSON, always
    assert S._ID_OK.match(restart['id']) and restart['scope'] in ('account', 'bot')
    assert isinstance(json.loads((acct / 'safety_switch.json').read_text())['enabled'], bool)
    lock = json.loads((acct / 'safety_lockout.json').read_text())
    assert lock['wrong'] >= 0 and lock['lock_s'] >= 600.0
    for name in names:
        if name.startswith('safety_status_'):
            assert json.loads((acct / name).read_text())['branch'] in (GOLD, BTC)
        if name.startswith('safety_block_'):
            text = (acct / name).read_text()
            assert text == '' or json.loads(text)['branch'] in (GOLD, BTC), name    # one whole file per id, or empty
    lines = (acct / 'safety_audit.jsonl').read_text().splitlines()
    assert len(lines) > 10
    for line in lines:
        entry = json.loads(line)                                         # every audit line is one whole JSON line
        assert 'at' in entry and PIN not in line and '12345678' not in line
    for branch in (GOLD, BTC):
        state = json.loads((tmp_path / branch / 'state' / 'safety_state.json').read_text())
        assert state['branch'] == branch and S.state_from_file(state) is not None
    assert (acct / 'safety_pin.txt').read_text() == PIN + '\n'           # nobody touched the owner's PIN
    return names


def _one_press_brings_both_bots_to_the_same_state(tmp_path, now):
    acct = str(tmp_path / 'acct')
    assert S.press(acct, 'on', None, 'command line', now, need_pin=False)[0] is True
    assert S.press(acct, 'unblock', None, 'command line', now + 1, need_pin=False)[0] is True
    current = S.read_controls(acct)
    assert current['enabled'] is True and current['block'] is None and current['readable'] is True
    for branch, partner in ((GOLD, BTC), (BTC, GOLD)):
        tr = S.Tracker(acct, str(tmp_path / branch / 'state' / 'safety_state.json'), branch, partner,
                       S.Limits(20.0, 10.0, 3), login=12345678)
        assert tr.load(now + 2) is True
        view = None
        for i in range(3):
            view = tr.poll(now + 3 + i, 700.0, [], now + 2.5 + i)
            tr.flush(now + 3 + i)
        assert view['period'] == current['period'] and view['blocked'] is False and view['error'] is None
        assert view['drop']['peak'] == 700.0 and view['streak']['count'] == 0


ROUNDS = 600                                  # polls of each bot, a second apart; about half a second of real time


def test_five_processes_on_one_account_folder(tmp_path):
    _run_together(tmp_path, rounds=ROUNDS, faults=0)
    names = _the_folder_is_whole(tmp_path)
    assert [n for n in names if n.startswith('safety_block_')]           # the account did get blocked on the way
    assert {'safety_status_acct_b9.json', 'safety_status_acct_x9.json'} <= set(names)
    _one_press_brings_both_bots_to_the_same_state(tmp_path, T0 + ROUNDS + 100)


@pytest.mark.parametrize('faults', [0.05, 0.3])
def test_five_processes_while_the_disk_refuses_reads_and_moves_at_random(tmp_path, faults):
    """5 % is a busy server; 30 % is far beyond anything real, and still nothing may raise or be left damaged."""
    _run_together(tmp_path, rounds=ROUNDS, faults=faults)
    _the_folder_is_whole(tmp_path)
    _one_press_brings_both_bots_to_the_same_state(tmp_path, T0 + ROUNDS + 100)
