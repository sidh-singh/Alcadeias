"""
The terminal of a real-money bot, and the old bots' MetaTrader 5.

The credentials files of the real-money branches arrive naming one terminal_path: the MetaTrader 5 the old bots use
(C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe), until the owner gives an account its own installation. For
the forward-test bots that installation was forbidden ground (never a login there). For a real-money bot it is the
terminal of its account like any other, and the rules are the same on every terminal:
  * it holds this bot's account -> used as it is, no login;
  * it holds another account -> left alone (TERMINAL_IN_USE; test_terminal_in_use.py);
  * it shows no account for the grace period -> the bot logs in, when its login rules allow one (a password in the
    file, no other account's claim on that MetaTrader 5, the login budget: test_live_login.py);
  * no terminal_path at all -> credentials that cannot be used: refused before any terminal call, so
    mt5.initialize() never attaches to a MetaTrader 5 it picks itself; only the owner can change the file, so the
    job ends with EXIT_NEEDS_OWNER and the launcher does not start it again.
What is left of the old rule is its path helper, _old_bots_terminal(path): it recognises that installation however
the path is spelt. The rule about an old bot that still runs on the server needs it (test_live_old_bot.py).
"""
import builtins
import io
import json
import os

import pytest

from conftest import ROOT, F, market
from conftest import found

OLD = r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'
SPELLINGS = [
    OLD,
    'C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe',              # forward slashes
    'c:\\program files\\metatrader 5 exness\\TERMINAL64.EXE',           # another case
    'C:\\\\Program Files\\\\MetaTrader 5 EXNESS\\\\terminal64.exe',      # doubled separators
    'C:\\Program Files\\MetaTrader 5 EXNESS\\.\\terminal64.exe',         # a '.' in it
    '  C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe  ',        # spaces around it
    'C:\\Program Files\\MetaTrader 5 EXNESS\\',                          # its folder
]
OWN_INSTALLATIONS = [
    r'C:\MT5 account 2\terminal64.exe',
    r'C:\Program Files\MetaTrader 5 EXNESS account 2\terminal64.exe',   # a folder that only starts like it
    r'D:\Program Files\MetaTrader 5 EXNESS\terminal64.exe',             # another drive
]


def _bot(mods, path):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run, credentials=F.account_credentials(terminal_path=path))
    bot.mt5_initialized, bot.position_helper = False, None
    paths = []
    attach = fake.initialize

    def initialize(*a, **k):
        paths.append(k.get('path'))
        return attach(*a, **k)
    fake.initialize = initialize
    return m, fake, clock, bot, run, paths


def _names(fake):
    return [c[0] for c in fake.calls]


def _no_account(fake):
    fake.logged_in, fake.account_login = False, 0


# ───────────────────────────── the path helper ─────────────────────────────

@pytest.mark.parametrize('path', SPELLINGS)
def test_the_old_bots_terminal_is_recognised_however_it_is_spelt(mods, path):
    assert mods().app._old_bots_terminal(path) is True


@pytest.mark.parametrize('path', OWN_INSTALLATIONS + ['', r'C:\Program Files'])
def test_another_installation_is_not_the_old_bots(mods, path):
    assert mods().app._old_bots_terminal(path) is False


@pytest.mark.skipif(os.name == 'nt', reason='symbolic links need extra rights on Windows')
def test_another_spelling_of_the_same_installation_is_the_old_bots(mods, tmp_path, monkeypatch):
    """(On the server: a short 8.3 name, a link or a junction to that installation.)"""
    old = tmp_path / 'MetaTrader 5 EXNESS' / 'terminal64.exe'
    old.parent.mkdir()
    old.write_text('')
    (tmp_path / 'mt5').symlink_to(old.parent)
    m = mods()
    monkeypatch.setattr(m.app, '_OLD_BOT_TERMINALS', (str(old),))
    assert m.app._old_bots_terminal(str(tmp_path / 'mt5' / 'terminal64.exe')) is True
    assert m.app._old_bots_terminal(str(tmp_path / 'mt5')) is True
    assert m.app._old_bots_terminal(str(tmp_path / 'other' / 'terminal64.exe')) is False


def test_the_names_of_the_forward_test_rule_are_gone(mods):
    a = mods().app
    for name in ('_LIVE_TERMINAL_PATHS', '_live_terminal', '_slot_name'):
        assert not hasattr(a, name), name
    for name in ('_never_login_here', '_terminal_path_problem', '_no_account_on_live_terminal_problem',
                 '_is_own_account', '_login_problem'):
        assert not hasattr(a.MT5TradingBot, name), name
    # (the refusals a launcher restart can repeat every 30 s; the forward test's LIVE_TERMINAL_PATH is not one)
    assert a.MT5TradingBot._LIMITED_EVENTS == ('TERMINAL_IN_USE', 'SERVER_MISMATCH', 'LOGIN_WAIT', 'LOGIN_REFUSED',
                                               'OLD_BOT_SAME_TERMINAL')
    assert not found((ROOT / 'app.py').read_text(encoding='utf-8'), 'LIVE_TERMINAL_PATH')
    assert a._account_name() == f'account {a.ACCOUNT_SLOT}'         # the account's number, not a digit of the label


# ───────────────────────────── attaching ─────────────────────────────

@pytest.mark.parametrize('path', SPELLINGS + OWN_INSTALLATIONS)
def test_a_terminal_holding_this_bots_account_is_used_without_a_login(mods, path):
    """Whichever installation the credentials name -- the old bots' one too: it is this account's terminal now."""
    m, fake, clock, bot, run, paths = _bot(mods, path)
    assert bot.initialize_mt5() is True
    assert _names(fake) == ['initialize'] and paths == [path.strip()]       # attached by path, never with credentials
    assert bot._init_problem is None and not run.events


@pytest.mark.parametrize('path', [OLD, OWN_INSTALLATIONS[0]])
def test_a_terminal_holding_another_account_is_left_alone(mods, path):
    m, fake, clock, bot, run, paths = _bot(mods, path)
    fake.account_login, fake.server = 87654321, 'Fake-Real2'
    assert bot.initialize_mt5() is False
    assert 'login' not in _names(fake) and (fake.account_login, fake.server) == (87654321, 'Fake-Real2')
    assert [e['event'] for e in run.events] == ['TERMINAL_IN_USE']
    assert run.events[0]['details']['terminal_path'] == path


@pytest.mark.parametrize('path', [OLD, OWN_INSTALLATIONS[0]])
def test_a_terminal_with_no_account_is_logged_into_the_bots_account(mods, path):
    """The same rule on every terminal (the forward-test bots never logged in on the old bots' one): no account for
    the whole grace period, then the bot logs in, with the "live" block."""
    m, fake, clock, bot, run, paths = _bot(mods, path)
    _no_account(fake)
    t0 = clock.time()
    assert bot.initialize_mt5() is True
    assert _names(fake) == ['initialize', 'login'] and (fake.account_login, fake.server) == (F.ACCOUNT_LOGIN,
                                                                                            F.ACCOUNT_SERVER)
    assert round(fake.calls[1][1] / 1000.0 - t0) == m.app._ACCOUNT_GRACE_S


# ───────────────────────────── no terminal_path ─────────────────────────────

@pytest.mark.parametrize('path', ['', '   ', None])
def test_without_a_terminal_path_nothing_reaches_the_terminal(mods, capsys, path):
    m, fake, clock, bot, run, paths = _bot(mods, path)
    assert bot.credentials is None                              # not usable: the bot has no account
    for _ in range(3):                                          # (the start-up's three attempts)
        assert bot.initialize_mt5() is False
    assert fake.calls == [] and paths == []                     # not even initialize(): it never attaches
    assert not bot.mt5_initialized and bot.position_helper is None and not run.events
    assert 'terminal_path is empty' in bot._init_problem
    assert 'Refused before attaching to any terminal' in capsys.readouterr().out


def _credentials_file(m, block):
    def fake_open(path, *a, **k):
        if str(path).endswith('mt5_credentials.json'):
            return io.StringIO(json.dumps({'live': block}))
        return builtins.open(path, *a, **k)
    m.app.open = fake_open


def test_the_job_without_a_terminal_path_ends_without_a_terminal_call(mods, capsys):
    """execute_job: the credentials are refused at the load in each of the three start attempts. Only the owner can
    put a terminal_path into the file, so the job ends with EXIT_NEEDS_OWNER (the launcher does not start it again
    every 30 s) and its last line says what to change."""
    m = mods()
    _credentials_file(m, F.account_credentials(terminal_path=''))
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.execute_job() is False and bot.exit_code == m.app.EXIT_NEEDS_OWNER
    assert m.fake.calls == [] and bot.credentials is None
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith('✗ The "live" block of mt5_credentials.json in ') and 'terminal_path is empty' in last


def test_starting_it_again_by_hand_stays_harmless(mods, tmp_path):
    """The owner starts the launcher again, and again, before he has put the file right: every start is refused
    before any terminal call, and nothing is added to the 200-entry strategy log (the refusal is in the start block
    of the text log)."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    m.app.print = lambda *a, **k: None
    _credentials_file(m, F.account_credentials(terminal_path='  '))
    for _ in range(5):
        bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
        assert bot.execute_job() is False and bot.exit_code == m.app.EXIT_NEEDS_OWNER
    assert m.fake.calls == []
    assert not (out / 'logs' / 'XAUUSDm_strategy_log.json').exists()
    logs = sorted(p.name for p in (out / 'logs').iterdir())
    assert logs and all('terminal_path is empty' in (out / 'logs' / n).read_text(encoding='utf-8')
                        for n in logs if n.endswith('.log'))
