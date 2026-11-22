"""
How a start ends, and what the launcher does with it.

The launcher (start_job.bat) starts app.py again 30 s after it ends -- unless it ended with EXIT_NEEDS_OWNER (78):
then it says that the bot will NOT start again by itself, and stops. So the exit code must tell the two kinds of
failure apart:
  * what only the owner can put right ends with 78 and ONE clear line that says what to change -- the last line
    the window shows: a design or a deployment block that cannot run, symbols.json or the credentials file wrong
    as written, an account on another server than the file names, an account that is not real / not hedging /
    not kept in US dollars, an account folder that belongs to another account (test_live_claims.py), the old
    account (test_live_old_account.py), another mode word (test_live_start.py), a second process of the bot
    (test_live_process_lock.py), a safety.py that cannot be loaded;
  * everything that may heal by itself ends with 1: the terminal not there yet or logged into another account, an
    account not known, a login the server refused, a file that cannot be read this moment.
A bot that holds trades must come back by itself after an unattended restart, so 78 is decided with care: at the
start only (a reconnect never ends the process), for a file only when all three start attempts, 5 s apart, gave
the same answer (a pull may be rewriting it), and for the account only when the terminal is connected and a second
read 2 s later says the same (a terminal that has just started may not have filled in its account yet).
(The stand-in files are made here: the branch's own mt5_credentials.json is never read by a test.)
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import (AS_WRITTEN, BRANCH, DEFAULTS, ROOT, F, account_folder, boot_text, market, names_calls,
                      stand_in_files, start_job, symbols_config)
from conftest import found

SECRET = 'S3cret-Pa55-of-a-test'
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
PARTNER = DEFAULTS['PARTNER_BRANCH']


def _last_line(capsys):
    return capsys.readouterr().out.strip().splitlines()[-1]


def _needs_owner(m, bot, reached):
    """The start ended with 78, never reached the trading loop, and sent nothing."""
    return bot.exit_code == m.app.EXIT_NEEDS_OWNER == 78 and not reached and m.fake.orders == []


def _heals(m, bot, reached):
    return bot.exit_code == m.app.EXIT_RETRY == 1 and not reached and m.fake.orders == []


# ───────────────────────────── a start that is right ─────────────────────────────

def test_a_real_hedging_usd_account_with_good_files_starts(mods, capsys):
    """The control of every test below: the same start with nothing wrong reaches the trading loop."""
    m = mods()
    opened = stand_in_files(m)
    bot, reached = start_job(m)
    assert reached and bot._owner_verdict is None and bot._init_problem is None
    assert names_calls(m.fake) == ['initialize', 'shutdown']        # attached, no login; detached when the job ended
    assert opened.count('mt5_credentials.json') == 1                # one attempt was enough
    assert not found(capsys.readouterr().out, 'cannot start')


# ───────────────────────────── the branch's own settings ─────────────────────────────

NOT_A_HASH = 'zz-not-a-fingerprint-zz'


@pytest.mark.parametrize('name, value, says', [
    ('MAGIC', None, 'MAGIC must be a whole number above 0'),        # no mark: every position would be this bot's
    ('MAGIC', 0, 'MAGIC must be a whole number above 0'),
    ('MAGIC', -5, 'MAGIC must be a whole number above 0'),
    ('MAGIC', True, 'MAGIC must be a whole number above 0'),
    ('MAGIC', 12345.0, 'MAGIC must be a whole number above 0'),
    ('ACCOUNT_SHARE', 0, 'ACCOUNT_SHARE must be a number above 0 and at most 1'),
    ('ACCOUNT_SHARE', 1.5, 'ACCOUNT_SHARE must be a number above 0 and at most 1'),
    ('ACCOUNT_SHARE', None, 'ACCOUNT_SHARE must be a number above 0 and at most 1'),
    ('LOG_KEEP_DAYS', 0, 'LOG_KEEP_DAYS must be a whole number of 1 or more'),
    ('LOG_KEEP_DAYS', 7.5, 'LOG_KEEP_DAYS must be a whole number of 1 or more'),
    ('LOG_KEEP_DAYS', None, 'LOG_KEEP_DAYS must be a whole number of 1 or more'),
    ('LOG_KEEP_DAYS', True, 'LOG_KEEP_DAYS must be a whole number of 1 or more'),
    ('OLD_LOGINS_SHA256', (), 'this branch was not finished by the generator'),
    ('OLD_LOGINS_SHA256', None, 'this branch was not finished by the generator'),
    ('OLD_LOGINS_SHA256', ['a' * 64], 'this branch was not finished by the generator'),      # a list, not a tuple
    ('OLD_LOGINS_SHA256', (NOT_A_HASH,), 'this branch was not finished by the generator'),
    ('OLD_LOGINS_SHA256', ('A' * 64,), 'this branch was not finished by the generator'),     # never equal to a hash
    ('OLD_LOGINS_SHA256', ('a' * 64, 12345678), 'this branch was not finished by the generator'),
    ('SAFETY_DEFAULT_ON', 1, 'SAFETY_DEFAULT_ON must be True or False'),
    ('SAFETY_DEFAULT_ON', None, 'SAFETY_DEFAULT_ON must be True or False'),
    ('SAFETY_DROP_PCT', 'twenty', 'SAFETY_DROP_PCT must be a percentage'),
    ('SAFETY_DROP_PCT', -1, 'SAFETY_DROP_PCT must be a percentage'),
    ('SAFETY_DROP_PCT', 100, 'SAFETY_DROP_PCT must be a percentage'),       # a limit that can never be met
    ('SAFETY_DAY_PCT', True, 'SAFETY_DAY_PCT must be a percentage'),
    ('SAFETY_STREAK_N', 2.5, 'SAFETY_STREAK_N must be a whole number'),
    ('SAFETY_STREAK_N', -1, 'SAFETY_STREAK_N must be a whole number'),
    ('SAFETY_STREAK_N', '5', 'SAFETY_STREAK_N must be a whole number'),
    ('ACCOUNT_FOLDER', '', 'ACCOUNT_FOLDER must be the name of the account'),
    ('ACCOUNT_FOLDER', None, 'ACCOUNT_FOLDER must be the name of the account'),
    ('ACCOUNT_FOLDER', 'the/account', 'ACCOUNT_FOLDER must be the name of the account'),
    ('ACCOUNT_FOLDER', '..', 'ACCOUNT_FOLDER must be the name of the account'),
    ('STRATEGY', 'grid', "is not 'basket' or 'turtle'"),            # a design lever, as before
])
def test_a_branch_whose_settings_cannot_run_needs_the_owner(mods, capsys, name, value, says):
    """constants.py is checked once, before anything is read or attached to. A value that cannot run stops the
    start for good -- starting again changes nothing -- and never switches a check off quietly: MAGIC None was "no
    mark at all" (every position of the symbol is this bot's), an empty OLD_LOGINS_SHA256 was "no old-account
    check"."""
    m = mods(**{name: value})
    opened = stand_in_files(m)
    bot, reached = start_job(m)
    assert _needs_owner(m, bot, reached)
    assert m.fake.calls == [] and 'mt5_credentials.json' not in opened       # before the file, before the terminal
    out = capsys.readouterr().out
    assert f'✗ Design: ' in out and says in out
    last = out.strip().splitlines()[-1]
    assert last.startswith(f'✗ constants.py of {BRANCH} cannot be used') and 'git checkout -- constants.py' in last
    line = [rec for rec in bot._boot_lines if rec[1] == 'ERROR'][-1]
    assert line[3].startswith('the design in constants.py is refused: ') and says in line[3]
    assert line[4] == {'exit_code': 78, 'needs_owner': 'DESIGN_REFUSED'}
    assert not found(out, NOT_A_HASH) and not found(boot_text(bot), NOT_A_HASH)        # a value of that constant is never shown


def test_the_settings_of_this_branch_as_written_pass(mods):
    m = mods(**{k: v for k, v in AS_WRITTEN.items() if k.startswith('SAFETY_')})
    assert m.app.deployment_problems() == []
    assert mods().app.deployment_problems() == []                   # ... and with the limits off, as the replays run


@pytest.mark.parametrize('limits', [
    dict(SAFETY_DROP_PCT=0, SAFETY_DAY_PCT=0, SAFETY_STREAK_N=0),   # 0 = that rule is off, as None is
    dict(SAFETY_DROP_PCT=33, SAFETY_DAY_PCT=7.5, SAFETY_STREAK_N=4),
    dict(SAFETY_DROP_PCT=99.9, SAFETY_DAY_PCT=None, SAFETY_STREAK_N=1),
])
def test_limits_the_safety_accepts_are_accepted(mods, limits):
    m = mods(**limits)
    assert m.app.deployment_problems() == []
    m.app.safety.Limits(*limits.values())                           # (what the bot will give the safety)


def test_a_replay_refuses_the_same_settings(mods):
    """Behind execute_job: the trading loop itself does not run on a block that cannot be used (a harness that
    calls process_symbol directly)."""
    m = mods(MAGIC=None)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    with pytest.raises(ValueError, match='MAGIC must be a whole number above 0'):
        bot.process_symbol('XAUUSDm')
    assert m.fake.orders == []


# ───────────────────────────── symbols.json ─────────────────────────────

def _one(**entry):
    return symbols_config(symbols=[dict({'symbol': 'XAUUSDm', 'is_active': True, 'step_up_balance': 2500,
                                         'unit_max_limit': 10}, **entry)])


def _without(key):
    cfg = _one()
    del cfg['symbols'][0][key]
    return cfg


@pytest.mark.parametrize('symbols, says', [
    (FileNotFoundError(2, 'No such file'), 'symbols.json is missing in '),
    ('{"brake": 0, "symbols": [', 'is not valid JSON (line 1, column 26)'),
    ('', 'is not valid JSON (line 1, column 1)'),
    ({'brake': 0}, 'holds no active symbol'),
    ('[1, 2]', 'holds no active symbol'),
    ({'symbols': 'XAUUSDm'}, 'holds no active symbol'),
    (_one(is_active=False), 'holds no active symbol'),
    (symbols_config('BTCUSDm'), 'does not hold the symbol XAUUSDM this bot was started for (active in it: BTCUSDm)'),
    (_one(step_up_balance=0), '"step_up_balance" of XAUUSDm must be a number above 0'),
    (_one(step_up_balance=-2500), '"step_up_balance" of XAUUSDm must be a number above 0'),
    (_one(step_up_balance='2500'), '"step_up_balance" of XAUUSDm must be a number above 0'),
    (_one(step_up_balance=True), '"step_up_balance" of XAUUSDm must be a number above 0'),
    (_without('step_up_balance'), '"step_up_balance" of XAUUSDm must be a number above 0'),
    (_one(unit_max_limit=0), '"unit_max_limit" of XAUUSDm must be a whole number of 1 or more'),
    (_one(unit_max_limit=2.5), '"unit_max_limit" of XAUUSDm must be a whole number of 1 or more'),
    (_one(unit_max_limit='10'), '"unit_max_limit" of XAUUSDm must be a whole number of 1 or more'),
    (_one(unit_max_limit=True), '"unit_max_limit" of XAUUSDm must be a whole number of 1 or more'),
    (_without('unit_max_limit'), '"unit_max_limit" of XAUUSDm must be a whole number of 1 or more'),
])
def test_a_symbols_file_that_is_wrong_as_written_needs_the_owner(mods, capsys, symbols, says):
    """symbols.json is the owner's file (he sets the step and the cap there). Missing, not JSON, without this bot's
    symbol, or with a step or a cap that cannot size a trade: the same answer at all three attempts, so the bot
    ends with 78 -- before any terminal call -- and its last line says what to change."""
    m = mods()
    opened = stand_in_files(m, symbols=symbols)
    bot, reached = start_job(m)
    assert _needs_owner(m, bot, reached) and m.fake.calls == []
    assert opened.count('mt5_credentials.json') == 3                # three attempts, each as far as this file
    last = _last_line(capsys)
    assert last.startswith('✗ ') and says in last and 'symbols.json' in last
    line = bot._boot_lines[-1]
    assert line[1:3] == ('ERROR', 'START') and says in line[3] and line[4]['exit_code'] == 78
    assert line[3].startswith('all 3 start attempts failed with the same answer, which only the owner can change: ')


@pytest.mark.parametrize('step, cap', [(2500, 10), (1250.5, 1), (0.01, 500)])
def test_a_step_and_a_cap_that_can_size_a_trade_are_accepted(mods, step, cap):
    m = mods()
    stand_in_files(m, symbols=_one(step_up_balance=step, unit_max_limit=cap))
    bot, reached = start_job(m)
    assert reached and bot.symbol_configs['XAUUSDm']['step_up_balance'] == step


def test_the_symbol_is_found_whatever_its_letter_case_and_an_inactive_one_is_passed_over(mods):
    m = mods()
    cfg = symbols_config(symbols=[
        {'symbol': 'BTCUSDm', 'is_active': False, 'step_up_balance': 0, 'unit_max_limit': 0},   # (not this bot's)
        {'symbol': 'XAUUSDm', 'is_active': True, 'step_up_balance': 1250, 'unit_max_limit': 10}])
    stand_in_files(m, symbols=cfg)
    bot, reached = start_job(m, symbol='xauusdm')
    assert reached and bot.symbols == ['XAUUSDm']


# ───────────────────────────── the credentials file ─────────────────────────────

def _block(**changes):
    return dict(F.CREDS, login_pass=SECRET, **changes)


@pytest.mark.parametrize('credentials, says', [
    (FileNotFoundError(2, 'No such file'), 'mt5_credentials.json is missing in '),
    ('{\n  "live": {\n    "login_id": 12345678\n    "login_pass": "%s"\n  }\n}\n' % SECRET,
     'is not valid JSON (line 4, column 5)'),
    ('', 'is not valid JSON (line 1, column 1)'),
    (UnicodeDecodeError('utf-8', SECRET.encode() + b'\xe4', 21, 22, 'invalid continuation byte'), 'is not UTF-8 text'),
    (json.dumps({'demo': _block()}), 'has no "live" block'),
    ('[1, 2]', 'has no "live" block'),
    (json.dumps({'live': None}), 'cannot be used: the block is missing'),
    (_block(login_id=SECRET), 'cannot be used: login_id must be the account number'),
    (_block(login_id=0), 'cannot be used: login_id must be the account number'),
    (_block(login_id=12345678.5), 'cannot be used: login_id must be the account number'),
    (_block(server='  '), 'cannot be used: server is empty'),
    (_block(terminal_path=''), 'cannot be used: terminal_path is empty'),
    (_block(terminal_path=r'C:\Nowhere\terminal64.exe'), 'does not name a file on this server'),
    (_block(terminal_path=SECRET), 'does not name a file on this server'),      # the password on the wrong line
])
def test_a_credentials_file_that_is_wrong_as_written_needs_the_owner(mods, capsys, credentials, says):
    """Missing, not JSON, not UTF-8, without a usable "live" block, or naming a terminal_path that is no file on this
    server: the same answer at all three attempts -> 78, before any terminal call, with a last line that says what to
    change. No character of the file reaches the console or the log: it holds the password."""
    m = mods()
    opened = stand_in_files(m, credentials=credentials)
    bot, reached = start_job(m)
    assert _needs_owner(m, bot, reached) and m.fake.calls == []
    assert opened.count('mt5_credentials.json') == 3 and bot.credentials is None and bot._login is None
    out = capsys.readouterr().out
    last = out.strip().splitlines()[-1]
    assert last.startswith('✗ ') and says in last and 'mt5_credentials.json' in last
    line = bot._boot_lines[-1]
    assert line[1:3] == ('ERROR', 'START') and says in line[3] and line[4]['exit_code'] == 78
    for text in (out, boot_text(bot)):                              # nothing of the file's content
        assert not found(text, SECRET) and not found(text, str(F.ACCOUNT_LOGIN))
    assert out.count(last) == 2             # said in full when it was first met, and once more as the last word
    assert out.count('The same answer as the attempt before') == 2


def test_a_terminal_path_that_is_a_file_on_this_server_is_accepted(mods, tmp_path):
    """The bot's own check (os.path.isfile; the tests answer it for the fake's installation): a file is, a folder or
    a path that does not exist is not."""
    m = mods()
    exe = tmp_path / 'MetaTrader 5 of this account' / 'terminal64.exe'
    exe.parent.mkdir()
    exe.write_text('')
    is_file = m.real_terminal_file_exists
    assert is_file(str(exe)) is True
    assert is_file(str(exe.parent)) is False and is_file(str(tmp_path / 'no' / 'terminal64.exe')) is False
    assert is_file('') is False and is_file(None) is False and is_file('a\x00b') is False       # never raises
    m.app._terminal_file_exists = is_file
    stand_in_files(m, credentials=_block(terminal_path=str(exe)))
    bot, reached = start_job(m)
    assert reached and m.fake.init_paths == [str(exe)]


@pytest.mark.parametrize('error', [PermissionError(13, 'Permission denied'), OSError(5, 'Input/output error'),
                                   BlockingIOError(11, 'Resource temporarily unavailable')])
@pytest.mark.parametrize('which', ['mt5_credentials.json', 'symbols.json'])
def test_a_file_that_cannot_be_read_this_moment_is_tried_again_never_the_owners_problem(mods, capsys, which, error):
    """A pull is rewriting the file, or Windows refuses the open: nothing the owner must change. Three attempts,
    then the process ends with 1 and the launcher starts it again."""
    m = mods()
    stand_in_files(m, **{'credentials' if which.startswith('mt5') else 'symbols': error})
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and m.fake.calls == [] and bot._owner_verdict is None
    out = capsys.readouterr().out
    assert f'{which} could not be read this time ({type(error).__name__})' in out
    assert out.strip().splitlines()[-1] == '✗ All init attempts failed: the launcher starts the bot again in 30 seconds.'
    assert bot._boot_lines[-1][4] == {'exit_code': 1}


@pytest.mark.parametrize('good_from', [2, 3])
@pytest.mark.parametrize('which', ['credentials', 'symbols'])
def test_a_file_that_a_pull_is_rewriting_does_not_stop_the_bot(mods, capsys, which, good_from):
    """The file is half-written at the first attempt(s) and whole a few seconds later: the bot starts. Before the
    three-attempts rule a file read in the middle of a pull would have been 'not valid JSON' and the end of the
    process."""
    m = mods()
    calls = []

    def being_rewritten():
        calls.append(1)
        if which == 'credentials':
            return '{"live": {"login_id": 123' if len(calls) < good_from else F.CREDS
        # (symbols.json is also read once before the attempts, for the name of the lock file)
        return '{"symbols": [{"symb' if len(calls) < good_from + 1 else symbols_config()
    stand_in_files(m, **{which: being_rewritten})
    bot, reached = start_job(m)
    assert reached and bot.exit_code != m.app.EXIT_NEEDS_OWNER
    out = capsys.readouterr().out
    assert out.count('Init attempt') == good_from - 1 and not found(out, 'cannot start')


def test_three_different_answers_are_not_the_owners_problem(mods, capsys):
    """'The same answer' is the test: a file that reads differently each time is still being written."""
    m = mods()
    texts = iter(['{"live": ', '{"live": {"login_id": ', FileNotFoundError(2, 'gone for a moment')])
    stand_in_files(m, credentials=lambda: next(texts))
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and m.fake.calls == []
    assert not found(capsys.readouterr().out, 'cannot start')


def test_an_owner_answer_twice_and_another_failure_once_is_not_the_owners_problem(mods):
    m = mods()
    answers = iter(['{"live": ', '{"live": ', PermissionError(13, 'held by a pull')])
    stand_in_files(m, credentials=lambda: next(answers))
    bot, reached = start_job(m)
    assert _heals(m, bot, reached)


# ───────────────────────────── the account the terminal holds ─────────────────────────────

def test_the_right_number_on_another_server_needs_the_owner(mods, capsys):
    """A new account often sits on another server than the old one, and the "server" of the file was not changed
    with it. The terminal, logged in by hand, holds the bot's number on its real server: not "another account in
    this MetaTrader 5, install a second one", but one word of the file to correct."""
    m = mods()
    m.fake.server = 'Fake-Real9'
    stand_in_files(m)
    events = []
    bot, reached = start_job(m, events=events)
    assert _needs_owner(m, bot, reached)
    assert names_calls(m.fake) == ['initialize', 'shutdown'] * 3 and m.fake.server == 'Fake-Real9'     # never a login
    line = (f'MetaTrader 5 is logged into account {TAIL} on Fake-Real9, but mt5_credentials.json says '
            f'{F.ACCOUNT_SERVER}. Correct "server" in the "live" block and start again.')
    assert _last_line(capsys) == f'✗ {line}'
    assert bot._init_problem == f'SERVER_MISMATCH: {line}'
    assert [e['event'] for e in events] == ['SERVER_MISMATCH']       # once, not at every attempt
    d = events[0]['details']
    assert (d['login_tail'], d['server'], d['own_server'], d['own_login_tail']) == (TAIL, 'Fake-Real9',
                                                                                    F.ACCOUNT_SERVER, TAIL)
    assert not found(json.dumps(events) + boot_text(bot), str(F.ACCOUNT_LOGIN))
    assert not account_folder(m).exists()                           # nothing was claimed for an account not accepted


def test_a_server_that_is_only_spelt_differently_is_the_same_server(mods):
    m = mods()
    m.fake.server = f'  {F.ACCOUNT_SERVER.upper()} '
    stand_in_files(m)
    bot, reached = start_job(m)
    assert reached


def test_another_server_that_is_gone_at_the_second_look_does_not_stop_the_bot(mods, capsys):
    """A terminal that has just started may not have filled in its account yet: the first read names another server,
    the read 2 s later the right one. That attempt fails, the next one passes: the bot starts."""
    m = mods()
    t0 = m.clock.time()
    m.fake.server = 'Fake-Real9'
    m.fake.at(t0 + 1.0, lambda f: setattr(f, 'server', F.ACCOUNT_SERVER))
    stand_in_files(m)
    bot, reached = start_job(m)
    assert reached and bot.exit_code != m.app.EXIT_NEEDS_OWNER
    out = capsys.readouterr().out
    assert out.count('Init attempt 1/3 failed') == 1 and not found(out, 'cannot start')


def test_another_server_on_a_terminal_that_is_not_connected_is_not_the_owners_problem_yet(mods):
    m = mods()
    m.fake.server, m.fake.connected = 'Fake-Real9', False
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and bot._init_problem.startswith('SERVER_MISMATCH: ')
    assert 'login' not in names_calls(m.fake)


def test_a_server_the_terminal_does_not_name_is_not_the_owners_problem(mods):
    m = mods()
    m.fake.server = ''
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and 'on a server it does not name' in bot._init_problem
    assert 'login' not in names_calls(m.fake)


KINDS = {
    'demo': (dict(trade_mode=0), 'is not a real account: MetaTrader 5 reports it as demo',
             'This branch trades real money only'),
    'contest': (dict(trade_mode=1), 'is not a real account: MetaTrader 5 reports it as contest',
                'This branch trades real money only'),
    'netting': (dict(margin_mode=0), 'is not a hedging account', 'This bot needs a hedging account'),
    'exchange': (dict(margin_mode=1), 'is not a hedging account', 'This bot needs a hedging account'),
    'euro': (dict(currency='EUR'), 'is kept in EUR. This bot counts in US dollars: use a USD account.', None),
    'cent': (dict(currency='USC'), 'is kept in USC. This bot counts in US dollars: use a USD account.', None),
}


@pytest.mark.parametrize('kind', sorted(KINDS))
def test_an_account_of_a_kind_this_bot_does_not_trade_needs_the_owner(mods, capsys, kind):
    """The number and the server of the credentials, but a demo or contest account, a netting account, or an
    account kept in another currency (the unit rule, every target and every stop count in US dollars): only another
    account puts that right. 78, and the bot never trades it."""
    changes, says, what = KINDS[kind]
    m = mods()
    for name, value in changes.items():
        setattr(m.fake, name, value)
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _needs_owner(m, bot, reached)
    assert names_calls(m.fake) == ['initialize', 'shutdown'] * 3     # attached, read, let go: never a login
    last = _last_line(capsys)
    assert last.startswith(f'✗ Account {TAIL} ') and says in last
    if what:
        assert what in last and 'mt5_credentials.json' in last and BRANCH in last and PARTNER in last
    assert bot._boot_lines[-1][4]['exit_code'] == 78
    assert not account_folder(m).exists() and not found(boot_text(bot), str(F.ACCOUNT_LOGIN))


@pytest.mark.parametrize('currency', ['USD', 'usd', ' USD '])
def test_a_usd_account_is_accepted_however_the_terminal_spells_it(mods, currency):
    m = mods()
    m.fake.currency = currency
    stand_in_files(m)
    assert start_job(m)[1]


@pytest.mark.parametrize('kind', ['demo', 'netting', 'euro'])
def test_a_kind_that_is_right_at_the_second_look_does_not_stop_the_bot(mods, capsys, kind):
    """'real' and 'hedging' are both 2 and a field not filled in yet reads 0: one unsettled read after a reboot of
    the server must not leave the bot down. The kind is read again 2 s later; right then, the attempt fails and the
    next one, 5 s later, starts the bot."""
    changes, _, _ = KINDS[kind]
    m = mods()
    right = {name: getattr(m.fake, name) for name in changes}
    for name, value in changes.items():
        setattr(m.fake, name, value)
    m.fake.at(m.clock.time() + 1.0, lambda f: [setattr(f, name, value) for name, value in right.items()])
    stand_in_files(m)
    bot, reached = start_job(m)
    assert reached and bot.exit_code != m.app.EXIT_NEEDS_OWNER
    out = capsys.readouterr().out
    assert out.count('Init attempt 1/3 failed') == 1 and not found(out, 'cannot start')


@pytest.mark.parametrize('kind', ['demo', 'netting', 'euro'])
def test_a_wrong_kind_on_a_terminal_that_is_not_connected_is_not_the_owners_problem_yet(mods, kind):
    changes, says, _ = KINDS[kind]
    m = mods()
    for name, value in changes.items():
        setattr(m.fake, name, value)
    m.fake.connected = False
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and says.split(':')[0] in bot._init_problem and bot._owner_verdict is None


def test_an_account_whose_currency_the_terminal_does_not_say_is_not_traded_and_not_the_owners_problem(mods):
    m = mods()
    m.fake.hide = {'currency'}
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached)
    assert 'does not say which currency' in bot._init_problem and TAIL in bot._init_problem


def test_the_currency_is_checked_when_the_bot_attaches_not_on_every_poll(mods):
    """The guard of every poll and every order stays as it was: the account of the credentials, a real account, a
    hedging account (the currency of an account never changes while the bot runs)."""
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    m.fake.currency = 'EUR'
    assert bot._account_problem() is None and bot._poll_guard('XAUUSDm')
    assert bot._account_check(m.fake.account_info())[0] is None
    assert bot._account_check(m.fake.account_info(), with_currency=True)[0] == 'not_usd'
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5() is False and 'is kept in EUR' in bot._init_problem


# ───────────────────────────── what may heal by itself ─────────────────────────────

def test_a_terminal_that_is_not_there_ends_with_1(mods, capsys):
    m = mods()
    t0 = m.clock.time()
    m.fake.down(t0 - 1, t0 + 3000)
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and bot._init_problem.startswith('initialize failed: ')
    assert names_calls(m.fake) == ['initialize'] * 3
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == '✗ All init attempts failed: the launcher starts the bot again in 30 seconds.'
    # each attempt says what the owner can check, and that nothing has to be done for the bot to try again
    assert out.count(f'MetaTrader 5 at {F.TERMINAL_PATH} did not answer: if this lasts, open that MetaTrader 5 by hand '
                     'and check that it starts and logs in. The bot tries again by itself.') == 3


def test_an_account_that_is_not_known_ends_with_1(mods):
    m = mods()
    real = m.fake.account_info
    m.fake.account_info = lambda: m.fake.account_answers.append('ipc_timeout') or real()      # every read times out
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached) and bot._init_problem.startswith('account not known: ')
    assert 'login' not in names_calls(m.fake)


def test_a_terminal_that_holds_another_account_ends_with_1(mods):
    """Never a login over it, and nothing only the owner of THIS file can change for certain: the owner may be
    logging the terminal into the new account this minute. The launcher keeps trying."""
    m = mods()
    m.fake.account_login = 87654321
    stand_in_files(m)
    events = []
    bot, reached = start_job(m, events=events)
    assert _heals(m, bot, reached) and bot._init_problem.startswith('TERMINAL_IN_USE: ')
    assert names_calls(m.fake) == ['initialize', 'shutdown'] * 3 and m.fake.account_login == 87654321
    assert [e['event'] for e in events] == ['TERMINAL_IN_USE']


def test_an_exception_in_the_start_ends_with_1(mods, capsys):
    m = mods()

    def boom(*a, **k):
        raise RuntimeError('the terminal raised')
    m.fake.initialize = boom
    stand_in_files(m)
    bot, reached = start_job(m)
    assert _heals(m, bot, reached)
    assert 'Job Failed with exception: the terminal raised' in capsys.readouterr().out
    line = bot._boot_lines[-1]
    assert line[3] == 'the job failed: RuntimeError: the terminal raised' and line[4] == {'exit_code': 1}


# ───────────────────────────── only at the start ─────────────────────────────

@pytest.mark.parametrize('what', ['server', 'demo', 'netting', 'euro'])
def test_a_reconnect_never_ends_the_process_whatever_it_finds(mods, what):
    """A running bot loses the terminal and finds it back holding its number on another server, or as an account of
    another kind. On the start that is the owner's to put right; here the bot holds trades: it never ends, it logs
    the failed reconnect, keeps trying with the back-off, and trades again once its account is back."""
    fake, clock = market(600)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    assert bot._poll_guard('XAUUSDm')
    t0 = clock.time()
    changes = dict(server='Fake-Real9') if what == 'server' else KINDS[what][0]
    right = {name: getattr(fake, name) for name in changes}
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 10, lambda f: [setattr(f, k, v) for k, v in changes.items()])
    fake.at(t0 + 200, lambda f: [setattr(f, k, v) for k, v in right.items()])
    ok_at = None
    for k in range(1, 400):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = k
            break
    assert ok_at is not None and 200 < ok_at < 300 and bot.mt5_initialized
    assert bot._owner_verdict is None and bot.exit_code == m.app.EXIT_RETRY     # nothing was decided about the end
    why = [e['details']['why'] for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert any(('SERVER_MISMATCH' if what == 'server' else KINDS[what][1].split(':')[0]) in w for w in why)
    assert 'login' not in names_calls(fake) and run.events[-1]['event'] == 'TERMINAL_RECONNECTED'


# ───────────────────────────── safety.py that cannot be loaded ─────────────────────────────

_TREE_FILES = ('app.py', 'mt5_helper.py', 'indicator.py', 'strategy.py', 'constants.py', 'turtle.py', 'safety.py',
               'symbols.json')


def _copy_of_the_tree(tmp_path):
    """The bot's own files in a folder of the test, with an empty module in the place of MetaTrader5 (the start
    never gets as far as a terminal call here). The credentials file is not copied."""
    copy = tmp_path / 'branch'
    copy.mkdir()
    for name in _TREE_FILES:
        shutil.copy(ROOT / name, copy / name)
    (copy / 'MetaTrader5.py').write_text('"""no terminal here"""\n')
    return copy


def _run_app(copy, *args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, '-B', '-X', 'utf8', 'app.py', *args], cwd=copy, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


@pytest.mark.parametrize('damage', ['missing', 'not python', 'raises'])
def test_a_safety_py_that_cannot_be_loaded_ends_the_process_with_78(tmp_path, damage):
    """The bot does not run without safety.py, and starting it again cannot repair a file: as a program it says what
    to do and ends with 78 (an import error would end with 1, and the launcher would start it every 30 s for ever)."""
    copy = _copy_of_the_tree(tmp_path)
    assert _run_app(copy, '--help').returncode == 0                 # the copy itself loads
    if damage == 'missing':
        (copy / 'safety.py').unlink()
    elif damage == 'not python':
        (copy / 'safety.py').write_text('<<<<<<< HEAD\ndef account_dir(:\n', encoding='utf-8')
    else:
        (copy / 'safety.py').write_text('raise RuntimeError("half a file")\n', encoding='utf-8')
    done = _run_app(copy, 'live', '--symbol', 'XAUUSDm')
    assert done.returncode == 78, done.stderr[-2000:]
    line = done.stdout.strip().splitlines()[-1]
    assert line.startswith(f'safety.py in {copy.resolve()} could not be loaded (') and 'git pull' in line
    assert not found(done.stderr, 'Traceback')
    assert sorted(p.name for p in copy.iterdir()) == sorted(
        set(_TREE_FILES) - ({'safety.py'} if damage == 'missing' else set()) | {'MetaTrader5.py'})     # nothing written


def test_a_safety_py_that_cannot_be_loaded_fails_an_import_as_any_import_does(tmp_path):
    """Imported by something else (a test, a replay), app.py does not end the importing process: the import fails."""
    copy = _copy_of_the_tree(tmp_path)
    (copy / 'safety.py').write_text('raise RuntimeError("half a file")\n', encoding='utf-8')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    done = subprocess.run([sys.executable, '-B', '-c', 'import app'], cwd=copy, env=env, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 1 and 'RuntimeError: half a file' in done.stderr


# ───────────────────────────── the texts ─────────────────────────────

def test_every_line_for_the_owner_is_one_line_and_names_no_account_number(mods, capsys):
    """What _needs_owner is given is what the owner reads as the window's last word: one line, no line break, and
    an account only as its tail."""
    m = mods()
    seen = []
    for setup in (lambda: stand_in_files(m, credentials=FileNotFoundError()),
                  lambda: stand_in_files(m, symbols=_one(step_up_balance=0)),
                  lambda: (stand_in_files(m), setattr(m.fake, 'server', 'Fake-Real9')),
                  lambda: (setattr(m.fake, 'server', F.ACCOUNT_SERVER), setattr(m.fake, 'currency', 'EUR'))):
        setup()
        bot, reached = start_job(m)
        assert bot.exit_code == 78 and bot._owner_verdict is not None
        seen.append(bot._owner_verdict[1])
    capsys.readouterr()
    assert len(set(seen)) == 4
    for line in seen:
        assert '\n' not in line and str(F.ACCOUNT_LOGIN) not in line and line.endswith('.')
        assert not re.search(r'\b(epoch|latch|rebase|period|slot|demo|virtual)\b', line, re.I)
