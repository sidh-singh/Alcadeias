"""
How a real-money bot is started, which credentials it loads, and how its process ends.

  * `app.py live --symbol X` is the only start. main() reads the mode word itself (argparse would answer a wrong
    word with its own text and exit code 2): anything but `live` -- no word at all, the old `demo` -- prints how to
    start the bot and ends with EXIT_NEEDS_OWNER before a bot exists. load_credentials and execute_job refuse
    another word too, before the credentials file is opened.
  * The bot reads the "live" block of mt5_credentials.json and no other, through ONE normalisation: the account
    number as a whole number (from a JSON whole number or a string of digits), the server and terminal_path without
    spaces around them. A block that cannot be used leaves the bot without an account; the reason names the key
    and never holds a value of the file (a password can sit on the wrong line).
  * The exit code tells the launcher what to do: 0 after Ctrl+C (stop), EXIT_NEEDS_OWNER = 78 for a start only the
    owner can put right (stop, and say so), 1 for everything else (start again after 30 s). 78 is no code a crash
    gives: Python ends with 1 or 2, a Windows abort() with 3.
(The stand-in credentials are made here: the branch's own mt5_credentials.json is never read by a test.)
"""
import builtins
import io
import json
import sys

import pytest

from conftest import BRANCH, F
from conftest import found

SECRET = 'S3cret-Pa55-of-a-test'
HOW_TO_START = f'This is the real-money branch {BRANCH}: start it with "start_job.bat live".'


def _file(m, text):
    """app.py finds `text` where it opens mt5_credentials.json; every other file is the real one. Returns the list
    of the opens it saw."""
    opened = []

    def fake_open(path, *a, **k):
        if str(path).endswith('mt5_credentials.json'):
            opened.append(str(path))
            return io.StringIO(text)
        return builtins.open(path, *a, **k)
    m.app.open = fake_open
    return opened


# ───────────────────────────── the mode word ─────────────────────────────

@pytest.mark.parametrize('argv', [
    ['demo', '--symbol', 'XAUUSDm'],            # how the forward-test branches were started
    ['--symbol', 'XAUUSDm'],                    # no word at all (a double-click on an old shortcut)
    ['real', '--symbol', 'XAUUSDm'],
    ['', '--symbol', 'XAUUSDm'],
    ['livee', '--symbol', 'XAUUSDm'],
])
def test_the_command_line_starts_nothing_without_the_word_live(mods, monkeypatch, capsys, argv):
    m = mods()
    made = []
    monkeypatch.setattr(m.app, 'MT5TradingBot', lambda *a, **k: made.append((a, k)))
    monkeypatch.setattr(sys, 'argv', ['app.py'] + argv)
    with pytest.raises(SystemExit) as e:
        m.app.main()
    assert e.value.code == m.app.EXIT_NEEDS_OWNER and not made          # refused before a bot exists
    assert HOW_TO_START in capsys.readouterr().out
    assert m.fake.calls == []                                           # and before any terminal call


@pytest.mark.parametrize('word', ['live', 'LIVE'])
@pytest.mark.parametrize('code', [0, 1, 78])
def test_the_command_line_live_runs_the_bot_and_ends_with_its_exit_code(mods, monkeypatch, word, code):
    m = mods()
    made = []

    class Bot:
        def __init__(self, mode=None, target_symbol=None):
            made.append((mode, target_symbol))
            self.exit_code = None

        def execute_job(self):
            self.exit_code = code
            return code == 0
    monkeypatch.setattr(m.app, 'MT5TradingBot', Bot)
    monkeypatch.setattr(sys, 'argv', ['app.py', word, '--symbol', 'BTCUSDm'])
    with pytest.raises(SystemExit) as e:
        m.app.main()
    assert e.value.code == code and made == [('live', 'BTCUSDm')]


def test_the_exit_codes_are_the_launchers(mods):
    """0 = stopped by the owner, 78 = needs the owner, 1 = may heal by itself. 78 is none of the codes a crashed
    process ends with (1 and 2: Python; 3: abort() on Windows; 120: Python could not flush at exit)."""
    a = mods().app
    assert (a.EXIT_OK, a.EXIT_RETRY, a.EXIT_NEEDS_OWNER) == (0, 1, 78)
    assert a.EXIT_NEEDS_OWNER not in (0, 1, 2, 3, 120)


def _job(mods, mode='live'):
    m = mods()
    m.app.print = lambda *a, **k: None
    bot = m.app.MT5TradingBot(mode=mode, target_symbol='XAUUSDm')
    return m, bot


def test_ctrl_c_ends_the_job_with_0(mods):
    """Stopped by the owner: the launcher must not start the bot again (before: Ctrl+C ended with 1 and the bot came
    back 30 s later)."""
    m, bot = _job(mods)
    bot._init_cycle = lambda: True

    def interrupted():
        raise KeyboardInterrupt
    bot.run_multithreaded_processing = interrupted
    assert bot.execute_job() is False and bot.exit_code == m.app.EXIT_OK
    m, bot = _job(mods)                                   # also while it is still starting

    def interrupted_start():
        raise KeyboardInterrupt
    bot._init_cycle = interrupted_start
    assert bot.execute_job() is False and bot.exit_code == m.app.EXIT_OK


def test_a_start_that_fails_or_crashes_ends_with_1(mods):
    """Three failed start attempts, or an exception out of the job: the launcher starts the bot again (it may heal
    by itself: a terminal still starting, a file being rewritten by a pull)."""
    m, bot = _job(mods)
    tries = []
    bot._init_cycle = lambda: tries.append(1) and False
    said = []
    m.app.print = lambda *a, **k: said.append(' '.join(str(x) for x in a))
    assert bot.execute_job() is False and len(tries) == 3 and bot.exit_code == m.app.EXIT_RETRY
    # what the window says is true: the launcher starts the bot again (it said "Restart start_job.bat" before)
    assert said[-1].strip() == '✗ All init attempts failed: the launcher starts the bot again in 30 seconds.'
    assert not any('Restart start_job.bat' in line for line in said)
    m, bot = _job(mods)

    def crash():
        raise RuntimeError('boom')
    bot._init_cycle = crash
    assert bot.execute_job() is False and bot.exit_code == m.app.EXIT_RETRY


def test_a_trading_loop_that_comes_back_by_itself_ends_with_1(mods, capsys):
    """Only Ctrl+C is "stopped by the owner". Nothing else is meant to end the trading loop, so a loop that comes
    back without it ends with 1 and the launcher starts the bot again: a bot with open trades must not stay down
    (before: it ended with 0 and the launcher printed that the owner had stopped it)."""
    m = mods()
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    bot._init_cycle = lambda: True
    bot.run_multithreaded_processing = lambda: None
    assert bot.execute_job() is True and bot.exit_code == m.app.EXIT_RETRY
    assert 'the launcher starts the bot again in 30 seconds' in capsys.readouterr().out
    assert bot._boot_lines[-1][4] == {'exit_code': m.app.EXIT_RETRY}        # the log line carries the exit code


@pytest.mark.parametrize('mode', ['demo', 'DEMO', 'real', ''])
def test_a_bot_made_with_another_mode_word_never_starts(mods, capsys, mode):
    """Behind main(): a bot object made with another word (a script, a harness) refuses the job and the credentials
    before the file is opened, and nothing reaches the terminal. It needs the owner: starting it again changes
    nothing."""
    m = mods()
    opened = _file(m, json.dumps({'live': F.CREDS, 'demo': F.CREDS}))
    bot = m.app.MT5TradingBot(mode=mode, target_symbol='XAUUSDm')
    assert bot.load_credentials() is False and bot.credentials is None and not opened
    assert bot.execute_job() is False and bot.exit_code == m.app.EXIT_NEEDS_OWNER
    assert not opened and m.fake.calls == []
    assert HOW_TO_START in capsys.readouterr().out


# ───────────────────────────── the credentials ─────────────────────────────

def test_the_bot_reads_the_live_block_and_no_other(mods):
    m = mods()
    other = dict(F.CREDS, login_id=99, server='Fake-Demo')
    opened = _file(m, json.dumps({'demo': other, 'live': F.CREDS}))
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is True and len(opened) == 1
    assert bot.credentials == F.CREDS and (bot._login, bot._server) == (F.ACCOUNT_LOGIN, F.ACCOUNT_SERVER)
    # a file without a "live" block: nothing is loaded, whatever else it holds -- and a bot that had loaded its
    # block before is left without an account, not with the older one
    _file(m, json.dumps({'demo': F.CREDS}))
    assert bot.load_credentials() is False and bot.credentials is None and bot._login is None
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is False and bot.credentials is None and bot._login is None


@pytest.mark.parametrize('changes', [
    {},                                             # as the generator's file has it: a whole number
    {'login_id': str(F.ACCOUNT_LOGIN)},             # the owner typed the quotes
    {'login_id': f'  {F.ACCOUNT_LOGIN} '},
    {'server': f'  {F.ACCOUNT_SERVER}  '},
    {'terminal_path': f' {F.TERMINAL_PATH} '},
    {'keep_old_account': True, 'note': 'anything'},     # other keys are kept as they are
])
def test_the_credentials_are_normalised_once_at_load(mods, changes):
    m = mods()
    block = dict(F.CREDS, **changes)
    _file(m, json.dumps({'live': block}))
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is True
    c = bot.credentials
    assert c['login_id'] == F.ACCOUNT_LOGIN and type(c['login_id']) is int and bot._login == F.ACCOUNT_LOGIN
    assert c['server'] == F.ACCOUNT_SERVER == bot._server and c['terminal_path'] == F.TERMINAL_PATH
    assert c['login_pass'] == F.CREDS['login_pass']
    assert {k: c[k] for k in changes if k not in ('login_id', 'server', 'terminal_path')} == \
           {k: v for k, v in changes.items() if k not in ('login_id', 'server', 'terminal_path')}
    assert bot._login_tail == '...' + str(F.ACCOUNT_LOGIN)[-4:]


@pytest.mark.parametrize('changes, key', [
    ({'login_id': float(F.ACCOUNT_LOGIN)}, 'login_id'),         # 12345678.0: not a whole number of the file
    ({'login_id': True}, 'login_id'),
    ({'login_id': '12a45678'}, 'login_id'),
    ({'login_id': ''}, 'login_id'),
    ({'login_id': None}, 'login_id'),
    ({'login_id': 0}, 'login_id'),                              # what a terminal answers while it holds no account
    ({'login_id': '0'}, 'login_id'),
    ({'login_id': -F.ACCOUNT_LOGIN}, 'login_id'),
    ({'login_id': SECRET}, 'login_id'),                         # the password typed on the wrong line
    ({'server': ''}, 'server'),
    ({'server': '   '}, 'server'),
    ({'server': None}, 'server'),
    ({'terminal_path': ''}, 'terminal_path'),                   # initialize() would pick a terminal itself
    ({'terminal_path': '  '}, 'terminal_path'),
    ({'terminal_path': None}, 'terminal_path'),
])
def test_a_block_that_cannot_be_used_loads_nothing_and_shows_none_of_its_values(mods, capsys, changes, key):
    m = mods()
    block = dict(F.CREDS, login_pass=SECRET, **changes)
    _file(m, json.dumps({'live': block}))
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is False
    assert bot.credentials is None and bot._login is None and bot._server is None and bot._login_tail is None
    out = capsys.readouterr().out
    assert key in out and not found(out, SECRET)
    lines = ' '.join(str(rec[3]) for rec in bot._boot_lines)        # what goes to the text log
    assert key in lines and not found(lines, SECRET) and not found(lines, str(F.ACCOUNT_LOGIN))
    assert bot.initialize_mt5() is False and m.fake.calls == []     # and it attaches to no terminal


@pytest.mark.parametrize('text', ['', '{"live": ', '[1, 2]', '"live"', 'null', '{"live": null}', '{"live": [1]}'])
def test_a_file_without_a_usable_live_block_loads_nothing(mods, text):
    m = mods()
    m.app.print = lambda *a, **k: None
    _file(m, text)
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is False and bot.credentials is None and bot._login is None


def test_a_json_fault_is_reported_by_its_place_never_by_its_text(mods, capsys):
    """An edit on GitHub that lost a comma: the message says where (line and column), and no character of the file
    -- it holds the password -- reaches the console or the log."""
    m = mods()
    _file(m, '{\n  "live": {\n    "login_id": 12345678\n    "login_pass": "%s"\n  }\n}\n' % SECRET)
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is False and bot.credentials is None
    out = capsys.readouterr().out
    lines = ' '.join(str(rec[3]) for rec in bot._boot_lines)
    for text in (out, lines):
        assert 'line 4, column 5' in text and not found(text, SECRET) and not found(text, 'login_pass')


def test_credentials_given_to_the_bot_directly_pass_the_same_normalisation(mods):
    """A replay or a test hands the bot its block (bot.credentials = ...): the same one normalisation, so the
    account is compared the same way whoever loaded it; None unloads it."""
    m = mods()
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.credentials is None and bot._login is None
    bot.credentials = F.account_credentials(login_id=f' {F.ACCOUNT_LOGIN} ', server=' Fake-Real ')
    assert bot.credentials['login_id'] == F.ACCOUNT_LOGIN and bot.credentials['server'] == 'Fake-Real'
    assert (bot._login, bot._server, bot._login_tail) == (F.ACCOUNT_LOGIN, 'Fake-Real', '...5678')
    bot.credentials = F.account_credentials(login_id=1.5)
    assert bot.credentials is None and bot._login is None and 'login_id' in bot._credentials_problem
    bot.credentials = dict(F.CREDS)
    assert bot._login == F.ACCOUNT_LOGIN
    with pytest.raises(TypeError):                          # never edited in place: the checks would not follow
        bot.credentials['login_id'] = 87654321
    assert bot.credentials['login_id'] == F.ACCOUNT_LOGIN == bot._login
    bot.credentials = None
    assert bot.credentials is None and bot._login is None and bot._server is None
