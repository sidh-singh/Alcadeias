"""
The live bots' MetaTrader 5 (fix F of the third review round; changed in v3.9.2-demo.8). The six demo branches'
mt5_credentials.json name C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe as terminal_path, the installation
every live branch uses: a login there would switch the account of every program attached to it, a live bot's too. So on
that installation (its terminal64.exe or its folder, in any case, with '/' or '\\', doubled separators, '.', spaces) a
demo bot never logs in. It attaches, and runs only while the terminal already holds this bot's own demo account (logged
in by hand, as on a server that runs only demo bots). Another account there is TERMINAL_IN_USE; no account for the whole
grace period is LIVE_TERMINAL_PATH, and the bot detaches. An empty terminal_path (initialize() would pick a terminal
itself) is refused before any terminal call. The strategy log has LIVE_TERMINAL_PATH at most every 15 minutes, also
across the launchers' restarts of app.py (every 30 s).
"""
import json
import os
import re
import time as real_time
from datetime import datetime, timezone

import pytest

from conftest import DEMO_BRANCH, F, market

LIVE = r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'
CREDS = {'terminal_path': LIVE, 'login_id': 1, 'login_pass': 'not-a-password', 'server': 'Fake-Demo'}
SLOT = re.search(r'(\d+)$', DEMO_BRANCH).group(1)
TODO = (f'install a separate MetaTrader 5 for slot {SLOT} and set terminal_path in mt5_credentials.json to its '
        f'terminal64.exe')
SPELLINGS = [
    LIVE,
    'C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe',              # forward slashes
    'c:\\program files\\metatrader 5 exness\\TERMINAL64.EXE',           # another case
    'C:\\\\Program Files\\\\MetaTrader 5 EXNESS\\\\terminal64.exe',      # doubled separators
    'C:\\Program Files\\MetaTrader 5 EXNESS\\.\\terminal64.exe',         # a '.' in it
    '  C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe  ',        # spaces around it
    'C:\\Program Files\\MetaTrader 5 EXNESS\\',                          # its folder
]


def _bot(mods, path):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS, terminal_path=path)
    bot.mt5_initialized, bot.position_helper = False, None
    return m, fake, clock, bot, run


def _names(fake):
    return [c[0] for c in fake.calls]


def _no_account(fake):
    fake.logged_in, fake.account_login = False, 0


@pytest.mark.parametrize('path', SPELLINGS)
def test_the_live_bots_terminal_holding_this_bots_account_is_used_without_a_login(mods, path):
    """The owner's demo server: that MetaTrader 5 is logged into the slot's demo account by hand."""
    m, fake, clock, bot, run = _bot(mods, path)
    assert bot.initialize_mt5() is True
    assert 'login' not in _names(fake) and 'initialize' in _names(fake)
    assert bot._account_login == 1 and bot._init_problem is None and not run.events


@pytest.mark.parametrize('path', SPELLINGS)
def test_the_live_bots_terminal_with_no_account_is_never_logged_in(mods, capsys, path):
    m, fake, clock, bot, run = _bot(mods, path)
    _no_account(fake)
    for _ in range(3):                                          # (the start-up's three attempts)
        assert bot.initialize_mt5() is False
    assert 'login' not in _names(fake) and 'initialize' in _names(fake)      # attached, never a login
    assert fake.account_login == 0 and not fake.logged_in                    # the terminal is left as it was
    assert not bot.mt5_initialized and bot._account_login is None
    assert [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH'] and run.events[0]['tag'] == 'ERROR'
    problem = run.events[0]['details']['problem']
    assert problem.startswith('LIVE_TERMINAL_PATH: the MetaTrader 5 at ') and 'never logs in there' in problem
    assert f"into slot {SLOT}'s demo account by hand" in problem and problem.endswith(TODO)
    assert bot._init_problem == problem and 'Refused, no login' in capsys.readouterr().out


@pytest.mark.parametrize('path', [LIVE, 'C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe'])
def test_the_live_bots_terminal_holding_another_account_is_left_alone(mods, path):
    m, fake, clock, bot, run = _bot(mods, path)
    fake.account_login, fake.server, fake.trade_mode = 99, 'Fake-Real', fake.ACCOUNT_TRADE_MODE_REAL
    assert bot.initialize_mt5() is False
    assert 'login' not in _names(fake) and (fake.account_login, fake.server) == (99, 'Fake-Real')
    assert [e['event'] for e in run.events] == ['TERMINAL_IN_USE']


def test_an_empty_terminal_path_is_refused_before_any_terminal_call(mods, capsys):
    m, fake, clock, bot, run = _bot(mods, '')
    for _ in range(3):
        assert bot.initialize_mt5() is False
    assert fake.calls == []                                     # not even initialize(): it never attaches
    assert not bot.mt5_initialized and bot.position_helper is None and bot._account_login is None
    assert [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH'] and run.events[0]['tag'] == 'ERROR'
    problem = run.events[0]['details']['problem']
    assert problem.startswith('LIVE_TERMINAL_PATH: terminal_path in mt5_credentials.json is empty')
    assert problem.endswith(TODO)
    assert bot._init_problem == problem and 'Refused before attaching to any terminal' in capsys.readouterr().out


@pytest.mark.parametrize('path', [
    r'C:\MT5 slot 6\terminal64.exe',
    r'C:\Program Files\MetaTrader 5 EXNESS slot 6\terminal64.exe',      # a folder that only starts like it
    r'D:\Program Files\MetaTrader 5 EXNESS\terminal64.exe',             # another drive
])
def test_a_slots_own_terminal_is_used(mods, path):
    m, fake, clock, bot, run = _bot(mods, path)
    assert bot.initialize_mt5() is True and _names(fake) == ['initialize'] and not run.events


def test_a_slots_own_terminal_with_no_account_is_logged_in(mods):
    m, fake, clock, bot, run = _bot(mods, r'C:\MT5 slot 6\terminal64.exe')
    _no_account(fake)
    assert bot.initialize_mt5() is True and 'login' in _names(fake) and fake.account_login == 1


@pytest.mark.skipif(os.name == 'nt', reason='symbolic links need extra rights on Windows')
def test_another_spelling_of_the_same_installation_is_never_logged_in(mods, tmp_path, monkeypatch):
    """(On the server: a short 8.3 name, a link or a junction to the live installation.)"""
    live = tmp_path / 'MetaTrader 5 EXNESS' / 'terminal64.exe'
    live.parent.mkdir()
    live.write_text('')
    (tmp_path / 'mt5').symlink_to(live.parent)
    m, fake, clock, bot, run = _bot(mods, str(tmp_path / 'mt5' / 'terminal64.exe'))
    monkeypatch.setattr(m.app, '_LIVE_TERMINAL_PATHS', (str(live),))
    _no_account(fake)
    assert bot.initialize_mt5() is False and 'login' not in _names(fake)
    assert [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH']


def test_the_job_on_the_live_bots_terminal_with_no_account_stops_without_a_login(mods):
    """execute_job: the three start-up attempts are refused, the job ends (the launcher starts it again 30 s later),
    and the terminal was never logged in."""
    m, fake, clock, bot, run = _bot(mods, LIVE)
    _no_account(fake)
    bot.load_credentials = lambda: setattr(bot, 'credentials', dict(CREDS)) or True     # (never the real file)
    bot.load_symbols = lambda: True
    assert bot.execute_job() is False
    assert 'login' not in _names(fake) and [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH']


def test_the_launchers_restarts_stay_harmless(mods, tmp_path, monkeypatch):
    """The launcher starts app.py again 30 s after it exits: with an empty terminal_path every start is refused before
    any terminal call, and the strategy log gets LIVE_TERMINAL_PATH at most every 15 minutes (a new process reads its
    newest entry)."""
    m = mods(OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr(m.app, 'time', real_time)               # the log's times are the wall clock
    log = tmp_path / 'logs' / 'XAUUSDm_strategy_log.json'

    def new_process():
        bot = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')
        bot.credentials, bot.symbols = dict(CREDS, terminal_path=''), ['XAUUSDm']
        for _ in range(3):
            assert bot.initialize_mt5() is False
    for _ in range(5):
        new_process()
    entries = json.loads(log.read_text())
    assert [e['event'] for e in entries] == ['LIVE_TERMINAL_PATH']
    assert entries[0]['tag'] == 'ERROR' and entries[0]['details']['problem'].endswith(TODO)
    assert entries[0]['details']['terminal_path'] == ''
    entries[0]['utc_time'] = datetime.fromtimestamp(real_time.time() - 901, tz=timezone.utc).isoformat()
    log.write_text(json.dumps(entries))
    new_process()                                               # 15 minutes later: once more
    assert [e['event'] for e in json.loads(log.read_text())] == ['LIVE_TERMINAL_PATH'] * 2
    assert m.fake.calls == []
