"""
The demo bot never attaches to the live bots' MetaTrader 5 (fix F of the third review round). The six demo branches'
mt5_credentials.json still name C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe as terminal_path, the
installation every live branch uses: one login there, the bot's or that of a program attached with it, switches the
account of every live bot on it. So the bot refuses to start while terminal_path is that installation (its
terminal64.exe or its folder, in any case, with '/' or '\\', with doubled separators), or is empty (initialize()
would pick a terminal itself): before mt5.initialize() is ever called, with one ERROR line LIVE_TERMINAL_PATH in the
strategy log that says what to do, repeated at most every 15 minutes, also across the launchers' restarts of app.py
(every 30 s), which stay harmless: no terminal call at all.
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


def _bot(mods, path):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS, terminal_path=path)
    bot.mt5_initialized, bot.position_helper = False, None
    return m, fake, clock, bot, run


@pytest.mark.parametrize('path', [
    LIVE,
    'C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe',              # forward slashes
    'c:\\program files\\metatrader 5 exness\\TERMINAL64.EXE',           # another case
    'C:\\\\Program Files\\\\MetaTrader 5 EXNESS\\\\terminal64.exe',      # doubled separators
    'C:\\Program Files\\MetaTrader 5 EXNESS\\.\\terminal64.exe',         # a '.' in it
    '  C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe  ',        # spaces around it
    'C:\\Program Files\\MetaTrader 5 EXNESS\\',                          # its folder
    '',                                                                   # empty: initialize() would pick one
])
def test_the_live_bots_terminal_is_refused_before_any_terminal_call(mods, capsys, path):
    m, fake, clock, bot, run = _bot(mods, path)
    for _ in range(3):                                          # (the start-up's three attempts)
        assert bot.initialize_mt5() is False
    assert fake.calls == []                                     # not even initialize(): it never attaches
    assert not bot.mt5_initialized and bot.position_helper is None and bot._account_login is None
    assert [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH'] and run.events[0]['tag'] == 'ERROR'
    problem = run.events[0]['details']['problem']
    assert problem.startswith('LIVE_TERMINAL_PATH: terminal_path') and problem.endswith(TODO)
    assert bot._init_problem == problem and 'Refused before attaching to any terminal' in capsys.readouterr().out


@pytest.mark.parametrize('path', [
    r'C:\MT5 slot 6\terminal64.exe',
    r'C:\Program Files\MetaTrader 5 EXNESS slot 6\terminal64.exe',      # a folder that only starts like it
    r'D:\Program Files\MetaTrader 5 EXNESS\terminal64.exe',             # another drive
])
def test_a_slots_own_terminal_is_used(mods, path):
    m, fake, clock, bot, run = _bot(mods, path)
    assert bot.initialize_mt5() is True and [c[0] for c in fake.calls] == ['initialize'] and not run.events


@pytest.mark.skipif(os.name == 'nt', reason='symbolic links need extra rights on Windows')
def test_another_spelling_of_the_same_installation_is_refused(mods, tmp_path, monkeypatch):
    """(On the server: a short 8.3 name, a link or a junction to the live installation.)"""
    live = tmp_path / 'MetaTrader 5 EXNESS' / 'terminal64.exe'
    live.parent.mkdir()
    live.write_text('')
    (tmp_path / 'mt5').symlink_to(live.parent)
    m, fake, clock, bot, run = _bot(mods, str(tmp_path / 'mt5' / 'terminal64.exe'))
    monkeypatch.setattr(m.app, '_LIVE_TERMINAL_PATHS', (str(live),))
    assert bot.initialize_mt5() is False and fake.calls == []
    assert [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH']


def test_the_job_stops_before_connecting(mods):
    """execute_job: the three start-up attempts are refused, the job ends (the launcher starts it again 30 s later),
    and nothing reached a terminal."""
    m, fake, clock, bot, run = _bot(mods, LIVE)
    bot.load_credentials = lambda: setattr(bot, 'credentials', dict(CREDS)) or True     # (never the real file)
    bot.load_symbols = lambda: True
    assert bot.execute_job() is False
    assert fake.calls == [] and [e['event'] for e in run.events] == ['LIVE_TERMINAL_PATH']


def test_the_launchers_restarts_stay_harmless(mods, tmp_path, monkeypatch):
    """The launcher starts app.py again 30 s after it exits: every start is refused before any terminal call, and the
    strategy log gets LIVE_TERMINAL_PATH at most every 15 minutes (a new process reads its newest entry)."""
    m = mods(OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr(m.app, 'time', real_time)               # the log's times are the wall clock
    log = tmp_path / 'logs' / 'XAUUSDm_strategy_log.json'

    def new_process():
        bot = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')
        bot.credentials, bot.symbols = dict(CREDS), ['XAUUSDm']
        for _ in range(3):
            assert bot.initialize_mt5() is False
    for _ in range(5):
        new_process()
    entries = json.loads(log.read_text())
    assert [e['event'] for e in entries] == ['LIVE_TERMINAL_PATH']
    assert entries[0]['tag'] == 'ERROR' and entries[0]['details']['problem'].endswith(TODO)
    assert entries[0]['details']['terminal_path'] == LIVE
    entries[0]['utc_time'] = datetime.fromtimestamp(real_time.time() - 901, tz=timezone.utc).isoformat()
    log.write_text(json.dumps(entries))
    new_process()                                               # 15 minutes later: once more
    assert [e['event'] for e in json.loads(log.read_text())] == ['LIVE_TERMINAL_PATH'] * 2
    assert m.fake.calls == []
