"""
The bot never logs in on a terminal that holds another account (finding 1 of the re-review). A login switches the
account of EVERY process attached to the terminal: the bots of another slot were locked out, and a live bot on the
same terminal was pulled off the real account. Now initialize_mt5 reads account_info() right after initialize():
  * no account -> it logs in;
  * this bot's account (the login and the server of the credentials) -> no login;
  * any other account -> no login: mt5.shutdown() (detach), an ERROR event TERMINAL_IN_USE (when it starts or
    changes, then at most every 15 min, also across the launcher's restarts of app.py), and it is retried with the
    existing back-off (start-up: 3 attempts, then the launcher; reconnect: 5, 10, 30, then every 60 s).
"""
import json
import time as real_time
from datetime import datetime, timezone

import pytest

from conftest import F, market

CREDS = {'terminal_path': r'C:\slot6\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}


def _fresh(mods, seconds=120):
    fake, clock = market(seconds)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS)
    bot.mt5_initialized, bot.position_helper = False, None
    return m, fake, clock, bot, run


def _in_use(run):
    return [e for e in run.events if e['event'] == 'TERMINAL_IN_USE']


@pytest.mark.parametrize('login, server, trade_mode', [
    (7, 'Fake-Demo', 0),            # the demo account of another slot
    (1, 'Fake-Real', 2),            # the same login number on another server: another account
    (99, 'Fake-Real', 2),           # a live bot's real account
])
def test_a_terminal_that_holds_another_account_is_left_alone(mods, capsys, login, server, trade_mode):
    m, fake, clock, bot, run = _fresh(mods)
    fake.account_login, fake.server, fake.trade_mode = login, server, trade_mode
    for _ in range(3):                                          # (the start-up's three attempts)
        assert bot.initialize_mt5() is False
    assert [c[0] for c in fake.calls] == ['initialize', 'shutdown'] * 3          # never a login
    assert (fake.account_login, fake.server, fake.trade_mode) == (login, server, trade_mode)    # left as it was
    assert not bot.mt5_initialized and bot.position_helper is None and bot._account_login is None
    ev = _in_use(run)
    assert len(ev) == 1 and ev[0]['tag'] == 'ERROR'             # one event, not one per attempt
    problem = ev[0]['details']['problem']
    assert problem.startswith('TERMINAL_IN_USE: the terminal at C:\\slot6\\terminal64.exe is logged into another '
                              f'account {login} (')
    assert 'give this slot its own MT5 installation' in problem and bot._init_problem == problem
    assert ev[0]['details']['login'] == login and ev[0]['details']['server'] == server
    assert ev[0]['details']['trade_mode'] == {0: 'demo', 2: 'real'}[trade_mode]
    assert 'Refused: TERMINAL_IN_USE' in capsys.readouterr().out


def test_the_terminal_holding_this_bots_account_is_not_logged_in_again(mods):
    m, fake, clock, bot, run = _fresh(mods)
    assert bot.initialize_mt5() is True and bot._account_login == 1
    assert [c[0] for c in fake.calls] == ['initialize']        # (before: initialize, login)
    fake.server = ' fake-demo '                                # the server name as the terminal spells it
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5() is True and [c[0] for c in fake.calls] == ['initialize', 'initialize']
    assert not _in_use(run)


def test_a_terminal_without_an_account_is_logged_in(mods):
    m, fake, clock, bot, run = _fresh(mods)
    fake.logged_in, fake.account_login = False, 0
    assert bot.initialize_mt5() is True
    assert [c[0] for c in fake.calls] == ['initialize', 'login'] and fake.account_login == 1
    assert not _in_use(run)


def test_two_slots_on_one_terminal_the_second_bot_does_not_take_it_over(mods):
    """Slot 6 (login 6) and slot 7 (login 7) on one terminal that holds no account. Slot 6 logs in and trades; slot
    7's start-up finds slot 6's account and leaves it alone, every time the launcher starts it again (3 attempts 5 s
    apart, then 30 s): slot 6 is never disturbed. (Before: slot 7 logged in over slot 6, which then refused every
    poll, and slot 6's next reconnect or restart would have swapped them back.)"""
    fake, clock = market(600)
    fake.logged_in, fake.account_login = False, 0
    fake.shutdown = lambda: fake.calls.append(('shutdown', clock.now_ms)) or True   # (detaches only its own process)
    m = mods(fake=fake, clock=clock)

    def slot_bot(lid, run):
        b = F.make_bot(m, fake, 'XAUUSDm', run)
        b.credentials = dict(CREDS, login_id=lid, terminal_path=r'C:\shared\terminal64.exe')
        b.mt5_initialized, b.position_helper = False, None
        return b
    run6, run7 = F.Run(), F.Run()
    slot6 = slot_bot(6, run6)
    assert slot6.initialize_mt5() is True and fake.account_login == 6
    allowed, starts = 0, []
    for k in range(300):                                        # 5 minutes, one poll a second
        if k % 45 == 0:
            slot7 = slot_bot(7, run7)                           # the launcher starts slot 7's app.py (again)
        if k % 45 in (0, 5, 10):
            starts.append(slot7.initialize_mt5())
        allowed += bool(slot6._poll_guard('XAUUSDm'))
        clock.sleep(1)
    assert allowed == 300 and len(starts) == 21 and not any(starts)
    assert [c[0] for c in fake.calls].count('login') == 1 and fake.account_login == 6
    ev = _in_use(run7)
    assert len(ev) == 7 and all('another account 6 (demo, Fake-Demo)' in e['details']['problem'] for e in ev)
    assert not [e for e in run6.events if e['tag'] == 'ERROR']


def test_a_reconnect_never_logs_in_over_another_account(mods):
    """The terminal restarts and comes back logged into a live bot's real account: the bot does not log in over it
    (it keeps retrying with the back-off and decides nothing), and connects again once its own account is back."""
    m, fake, clock, bot, run = _fresh(mods, seconds=1200)
    assert bot.initialize_mt5() is True
    t0 = clock.time()
    fake.down(t0 + 0.5, t0 + 30.5)

    def live_bot_logs_in(f):
        f.account_login, f.server, f.trade_mode = 99, 'Fake-Real', f.ACCOUNT_TRADE_MODE_REAL
    fake.at(t0 + 20, live_bot_logs_in)

    def demo_is_back(f):
        f.account_login, f.server, f.trade_mode = 1, 'Fake-Demo', f.ACCOUNT_TRADE_MODE_DEMO
    fake.at(t0 + 1050, demo_is_back)
    ok_at = None
    for k in range(1, 1150):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = k
            break
    assert 'login' not in [c[0] for c in fake.calls]                        # never a login
    assert ok_at is not None and 1050 < ok_at <= 1111 and bot._account_login == 1
    ev = _in_use(run)
    assert [round(e['t'] / 1000.0 - t0) for e in ev] == [50, 950]           # when it starts, then 15 min later
    assert all('another account 99 (real, Fake-Real)' in e['details']['problem'] for e in ev)
    assert run.events[-1]['event'] == 'TERMINAL_RECONNECTED'


LIVE = (99, 'Fake-Real', 2)          # a live bot's real account


def _hold(fake, login_server_mode):
    fake.account_login, fake.server, fake.trade_mode = login_server_mode
    fake.logged_in = True


def _names(fake):
    return [c[0] for c in fake.calls]


@pytest.mark.parametrize('answer', ['ipc_timeout', 'login_0', 'still_logging_in'])
def test_a_momentary_no_account_answer_is_never_a_login(mods, answer):
    """Fix B of the third review round: right after initialize() account_info() answers None or login 0 for a moment
    on a terminal that holds a live account -- an IPC timeout on a busy terminal, a login-0 answer, or a terminal
    just started (or restarted) that logs into its saved account for 3 s. Never a login (before: the bot read it as
    'no account' and logged in, switching the live account off); the account is read again, and the live one is
    refused (TERMINAL_IN_USE) when it shows."""
    m, fake, clock, bot, run = _fresh(mods)
    _hold(fake, LIVE)
    if answer == 'still_logging_in':
        fake.login_delay_s = 3.0
    else:
        fake.account_answers = [answer]
    t0 = clock.time()
    first = bot.initialize_mt5()
    problem = bot._init_problem
    for _ in range(2):                                          # (the start-up's other two attempts, 5 s apart)
        clock.sleep(5)
        assert bot.initialize_mt5() is False
    assert first is False and 'login' not in _names(fake) and _names(fake) == ['initialize', 'shutdown'] * 3
    assert (fake.account_login, fake.server, fake.trade_mode) == LIVE                  # left as it was
    ev = _in_use(run)
    assert len(ev) == 1 and 'another account 99 (real, Fake-Real)' in ev[0]['details']['problem']
    if answer == 'ipc_timeout':                                 # the account not known: detached, tried again
        assert problem.startswith('account not known: account_info() answered None (last_error (-10005')
        assert round(ev[0]['t'] / 1000.0 - t0) == 5
    else:                                                       # read again: the live account shows
        assert problem.startswith('TERMINAL_IN_USE')
        assert round(ev[0]['t'] / 1000.0 - t0) == (1 if answer == 'login_0' else 3)


def test_an_account_not_known_is_tried_again_and_then_used(mods):
    """An IPC timeout on the first account read of a terminal that holds this bot's own account: no login, detached;
    the next attempt finds the account and uses it as it is."""
    m, fake, clock, bot, run = _fresh(mods)
    fake.account_answers = ['ipc_timeout']
    assert bot.initialize_mt5() is False and bot._init_problem.startswith('account not known')
    clock.sleep(5)
    assert bot.initialize_mt5() is True and bot._account_login == 1
    assert _names(fake) == ['initialize', 'shutdown', 'initialize'] and not run.events


def test_a_terminal_that_shows_no_account_for_15_s_is_logged_in(mods):
    m, fake, clock, bot, run = _fresh(mods)
    fake.logged_in, fake.account_login = False, 0
    t0 = clock.time()
    assert bot.initialize_mt5() is True and fake.account_login == 1
    assert [(n, round(t / 1000.0 - t0)) for n, t in fake.calls] == [('initialize', 0), ('login', 15)]


def test_a_terminal_connected_to_a_trade_server_that_shows_no_account_is_not_logged_in(mods):
    """Connected to a trade server means logged into some account: login 0 for the whole grace period there is not
    'no account'."""
    m, fake, clock, bot, run = _fresh(mods)
    fake.account_answers = ['login_0'] * 30
    assert bot.initialize_mt5() is False and 'login' not in _names(fake)
    assert 'connected to a trade server but shows no account' in bot._init_problem


def test_a_terminal_slower_than_the_grace_period_is_logged_in(mods):
    """The limit the README names: a terminal still logging into its saved account after 15 s reads as holding none,
    and the bot logs in over it. Only a separate MetaTrader 5 per slot closes this."""
    m, fake, clock, bot, run = _fresh(mods)
    _hold(fake, LIVE)
    fake.login_delay_s = 20.0
    t0 = clock.time()
    bot.initialize_mt5()
    assert [(n, round(t / 1000.0 - t0)) for n, t in fake.calls if n == 'login'] == [('login', 15)]


def test_a_reconnect_onto_a_terminal_still_logging_into_a_live_account_is_never_a_login(mods):
    """The terminal restarts (30 s) and comes back logging into a live bot's saved real account, 3 s after every
    initialize(): the reconnects never log in; once the demo account is back the bot connects again (before: the
    first reconnect logged in over the live account)."""
    m, fake, clock, bot, run = _fresh(mods, seconds=1200)
    assert bot.initialize_mt5() is True
    t0 = clock.time()
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 20, lambda f: _hold(f, LIVE))
    fake.at(t0 + 20, lambda f: setattr(f, 'login_delay_s', 3.0))
    fake.at(t0 + 400, lambda f: _hold(f, (1, 'Fake-Demo', 0)))
    ok_at = None
    for _ in range(600):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = clock.time() - t0
            break
    assert 'login' not in _names(fake) and _names(fake).count('initialize') >= 5
    assert ok_at is not None and 400 < ok_at < 470 and bot._account_login == 1
    assert len(_in_use(run)) == 1 and run.events[-1]['event'] == 'TERMINAL_RECONNECTED'


def _log_entries(path):
    with open(path) as f:
        return json.load(f)


def test_the_launchers_restarts_do_not_fill_the_log(mods, tmp_path, monkeypatch):
    """app.py exits after its three start-up attempts and the launcher starts it again 30 s later: a new process
    reads the newest entry of the strategy log and does not repeat TERMINAL_IN_USE for 15 minutes."""
    m = mods(OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr(m.app, 'time', real_time)               # the log's times are the wall clock
    m.fake.account_login, m.fake.trade_mode = 99, m.fake.ACCOUNT_TRADE_MODE_REAL
    log = tmp_path / 'logs' / 'XAUUSDm_strategy_log.json'

    def new_process():
        bot = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')
        bot.credentials, bot.symbols = dict(CREDS), ['XAUUSDm']
        for _ in range(3):
            assert bot.initialize_mt5() is False
    new_process()
    new_process()
    assert [e['event'] for e in _log_entries(log)] == ['TERMINAL_IN_USE']
    entries = _log_entries(log)
    entries[0]['utc_time'] = datetime.fromtimestamp(real_time.time() - 901, tz=timezone.utc).isoformat()
    log.write_text(json.dumps(entries))
    new_process()                                               # 15 minutes later: once more
    assert [e['event'] for e in _log_entries(log)] == ['TERMINAL_IN_USE', 'TERMINAL_IN_USE']
    assert 'login' not in [c[0] for c in m.fake.calls]
