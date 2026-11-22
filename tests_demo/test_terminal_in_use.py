"""
The bot never logs in on a terminal that holds another account. A login switches the account of EVERY process
attached to the terminal: the bots of another account would be locked out, and this bot would trade real money on
whatever the switch left behind. So initialize_mt5 reads account_info() right after initialize():
  * no account -> it logs in (only after the whole grace period: a terminal just started logs into its saved
    account; and only when its login rules allow it: test_live_login.py);
  * this bot's account (the number and the server of the credentials) -> no login;
  * any other account -> no login: mt5.shutdown() (detach), an ERROR event TERMINAL_IN_USE (when it starts or
    changes, then at most every 15 min, also across the launcher's restarts of app.py), and it is retried with the
    existing back-off (start-up: 3 attempts, then the launcher; reconnect: 5, 10, 30, then every 60 s);
  * this bot's account NUMBER on another server -> no login either, and its own answer (SERVER_MISMATCH: the
    "server" of the credentials file is the thing to correct; test_live_needs_owner.py).
The two bots of one account (gold and BTC) share one terminal and one account: both are let in.
What the event and its text carry of an account is its tail (...4321), never the number.
"""
import json
import time as real_time
from datetime import datetime, timezone

import pytest

from conftest import F, market
from conftest import found

PATH = F.TERMINAL_PATH
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
REAL, DEMO = 2, 0
OWN = (F.ACCOUNT_LOGIN, F.ACCOUNT_SERVER, REAL)
OTHER = (87654321, F.ACCOUNT_SERVER, REAL)      # another real account on the same server (an old bot's)
OTHER_TEXT = f'another account (...4321 on {F.ACCOUNT_SERVER})'


def _fresh(mods, seconds=120):
    fake, clock = market(seconds)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)       # (with the credentials of the fake's account)
    bot.mt5_initialized, bot.position_helper = False, None
    return m, fake, clock, bot, run


def _in_use(run):
    return [e for e in run.events if e['event'] == 'TERMINAL_IN_USE']


def _hold(fake, login_server_mode):
    fake.account_login, fake.server, fake.trade_mode = login_server_mode
    fake.logged_in = True


def _names(fake):
    return [c[0] for c in fake.calls]


@pytest.mark.parametrize('login, server, trade_mode', [
    OTHER,                                      # another real account: only the number differs
    (87654321, 'Fake-Real2', REAL),             # ... on another server
    (99, 'Fake-Demo', DEMO),                    # an account of the forward test
])
def test_a_terminal_that_holds_another_account_is_left_alone(mods, capsys, login, server, trade_mode):
    m, fake, clock, bot, run = _fresh(mods)
    _hold(fake, (login, server, trade_mode))
    for _ in range(3):                                          # (the start-up's three attempts)
        assert bot.initialize_mt5() is False
    assert _names(fake) == ['initialize', 'shutdown'] * 3       # never a login
    assert (fake.account_login, fake.server, fake.trade_mode) == (login, server, trade_mode)    # left as it was
    assert not bot.mt5_initialized and bot.position_helper is None
    ev = _in_use(run)
    assert len(ev) == 1 and ev[0]['tag'] == 'ERROR'             # one event, not one per attempt
    problem = ev[0]['details']['problem']
    tail = '...' + str(login)[-4:]
    assert problem.startswith(f"TERMINAL_IN_USE: MetaTrader 5 at {PATH} is logged into another account ({tail} on "
                              f"{server}), not this bot's {TAIL}. ")
    assert 'First make sure the old bot of this account is stopped.' in problem
    assert 'install a second MetaTrader 5 in its own folder' in problem
    assert problem.endswith('The bot never switches the account itself; it tries again every 30 seconds.')
    assert bot._init_problem == problem
    d = ev[0]['details']
    assert (d['login_tail'], d['server'], d['own_login_tail'], d['terminal_path']) == (tail, server, TAIL, PATH)
    assert d['trade_mode'] == {DEMO: 'demo', REAL: 'real'}[trade_mode]
    assert 'Refused: TERMINAL_IN_USE' in capsys.readouterr().out
    assert (bot._acct['login_tail'], bot._acct['server']) == (tail, server)     # what the trace is told it found
    text = json.dumps(run.events)                               # the tail of an account, never its number
    assert not found(text, str(F.ACCOUNT_LOGIN)) and not found(text, str(OTHER[0]))


def test_the_terminal_holding_this_bots_account_is_not_logged_in_again(mods):
    m, fake, clock, bot, run = _fresh(mods)
    assert bot.initialize_mt5() is True and bot._init_problem is None
    assert _names(fake) == ['initialize']                       # no login
    fake.server = f' {F.ACCOUNT_SERVER.lower()} '               # the server name as the terminal spells it
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5() is True and _names(fake) == ['initialize', 'initialize']
    assert not _in_use(run)


def test_a_terminal_without_an_account_is_logged_in(mods):
    m, fake, clock, bot, run = _fresh(mods)
    fake.logged_in, fake.account_login = False, 0
    assert bot.initialize_mt5() is True
    assert _names(fake) == ['initialize', 'login'] and (fake.account_login, fake.server) == OWN[:2]
    assert not _in_use(run)


def test_the_two_bots_of_one_account_share_the_terminal(mods):
    """Gold and BTC of one account: the same credentials, one terminal. The first finds no account and logs in; the
    second finds its own account there and uses it without a login; both pass every poll."""
    fake, clock = market(120)
    fake.logged_in, fake.account_login = False, 0
    fake.shutdown = lambda: fake.calls.append(('shutdown', clock.now_ms)) or True   # (detaches only its own process)
    m = mods(fake=fake, clock=clock)
    runs = [F.Run(), F.Run()]
    bots = []
    for run in runs:
        b = F.make_bot(m, fake, 'XAUUSDm', run, credentials=F.CREDS)
        b.mt5_initialized, b.position_helper = False, None
        assert b.initialize_mt5() is True
        bots.append(b)
    assert _names(fake) == ['initialize', 'login', 'initialize']
    for _ in range(30):
        assert all(b._poll_guard('XAUUSDm') for b in bots)
        clock.sleep(1)
    assert not [e for run in runs for e in run.events if e['tag'] == 'ERROR']


def test_two_accounts_on_one_terminal_the_second_bot_does_not_take_it_over(mods):
    """Two accounts whose credentials name one terminal that holds no account. The first bot logs in and trades; the
    other account's bot finds that account and leaves it alone, every time the launcher starts it again (3 attempts
    5 s apart, then 30 s): the first is never disturbed. (Otherwise the second would log in over the first, which
    then refuses every poll, and the first's next reconnect or restart would swap them back.)"""
    fake, clock = market(600)
    fake.logged_in, fake.account_login = False, 0
    fake.shutdown = lambda: fake.calls.append(('shutdown', clock.now_ms)) or True   # (detaches only its own process)
    m = mods(fake=fake, clock=clock)
    first, second = 11111111, 22222222

    def account_bot(login, run):
        b = F.make_bot(m, fake, 'XAUUSDm', run, credentials=F.account_credentials(login_id=login))
        b.mt5_initialized, b.position_helper = False, None
        return b
    run1, run2 = F.Run(), F.Run()
    bot1 = account_bot(first, run1)
    assert bot1.initialize_mt5() is True and fake.account_login == first
    allowed, starts = 0, []
    for k in range(300):                                        # 5 minutes, one poll a second
        if k % 45 == 0:
            bot2 = account_bot(second, run2)                    # the launcher starts the other bot's app.py (again)
        if k % 45 in (0, 5, 10):
            starts.append(bot2.initialize_mt5())
        allowed += bool(bot1._poll_guard('XAUUSDm'))
        clock.sleep(1)
    assert allowed == 300 and len(starts) == 21 and not any(starts)
    assert _names(fake).count('login') == 1 and fake.account_login == first
    ev = _in_use(run2)
    assert len(ev) == 7 and all(f'another account (...1111 on {F.ACCOUNT_SERVER})' in e['details']['problem']
                                for e in ev)
    assert not [e for e in run1.events if e['tag'] == 'ERROR']


def test_a_reconnect_never_logs_in_over_another_account(mods):
    """The terminal restarts and comes back logged into another real account (an old bot's): the bot does not log in
    over it (it keeps retrying with the back-off and decides nothing), and connects again once its own account is
    back."""
    m, fake, clock, bot, run = _fresh(mods, seconds=1200)
    assert bot.initialize_mt5() is True
    t0 = clock.time()
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 20, lambda f: _hold(f, OTHER))
    fake.at(t0 + 1050, lambda f: _hold(f, OWN))
    ok_at = None
    for k in range(1, 1150):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = k
            break
    assert 'login' not in _names(fake)                                      # never a login
    assert ok_at is not None and 1050 < ok_at <= 1111 and bot._account_bad is None
    ev = _in_use(run)
    assert [round(e['t'] / 1000.0 - t0) for e in ev] == [50, 950]           # when it starts, then 15 min later
    assert all(OTHER_TEXT in e['details']['problem'] for e in ev)
    assert run.events[-1]['event'] == 'TERMINAL_RECONNECTED' and run.events[-1]['details']['login_tail'] == TAIL


@pytest.mark.parametrize('answer', ['ipc_timeout', 'login_0', 'still_logging_in'])
def test_a_momentary_no_account_answer_is_never_a_login(mods, answer):
    """Right after initialize() account_info() answers None or login 0 for a moment on a terminal that holds another
    account -- an IPC timeout on a busy terminal, a login-0 answer, or a terminal just started (or restarted) that
    logs into its saved account for 3 s. Never a login (the bot would read it as 'no account' and log in, switching
    the other account off); the account is read again, and the other one is refused (TERMINAL_IN_USE) when it
    shows."""
    m, fake, clock, bot, run = _fresh(mods)
    _hold(fake, OTHER)
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
    assert (fake.account_login, fake.server, fake.trade_mode) == OTHER                 # left as it was
    ev = _in_use(run)
    assert len(ev) == 1 and OTHER_TEXT in ev[0]['details']['problem']
    if answer == 'ipc_timeout':                                 # the account not known: detached, tried again
        assert problem.startswith('account not known: account_info() answered None (last_error (-10005')
        assert round(ev[0]['t'] / 1000.0 - t0) == 5
    else:                                                       # read again: the other account shows
        assert problem.startswith('TERMINAL_IN_USE')
        assert round(ev[0]['t'] / 1000.0 - t0) == (1 if answer == 'login_0' else 3)


def test_an_account_not_known_is_tried_again_and_then_used(mods):
    """An IPC timeout on the first account read of a terminal that holds this bot's own account: no login, detached;
    the next attempt finds the account and uses it as it is."""
    m, fake, clock, bot, run = _fresh(mods)
    fake.account_answers = ['ipc_timeout']
    assert bot.initialize_mt5() is False and bot._init_problem.startswith('account not known')
    clock.sleep(5)
    assert bot.initialize_mt5() is True and bot._init_problem is None
    assert _names(fake) == ['initialize', 'shutdown', 'initialize'] and not run.events


def test_a_terminal_that_shows_no_account_for_the_grace_period_is_logged_in(mods):
    m, fake, clock, bot, run = _fresh(mods)
    grace = m.app._ACCOUNT_GRACE_S
    fake.logged_in, fake.account_login = False, 0
    t0 = clock.time()
    assert bot.initialize_mt5() is True and fake.account_login == F.ACCOUNT_LOGIN
    assert [(n, round(t / 1000.0 - t0)) for n, t in fake.calls] == [('initialize', 0), ('login', grace)]


def test_a_terminal_connected_to_a_trade_server_that_shows_no_account_is_not_logged_in(mods):
    """Connected to a trade server means logged into some account: login 0 for the whole grace period there is not
    'no account'."""
    m, fake, clock, bot, run = _fresh(mods)
    fake.account_answers = ['login_0'] * int(m.app._ACCOUNT_GRACE_S + 15)
    assert bot.initialize_mt5() is False and 'login' not in _names(fake)
    assert 'connected to a trade server but shows no account' in bot._init_problem


def test_a_terminal_slower_than_the_grace_period_is_logged_in(mods):
    """The known limit of this rule: a terminal still logging into its saved account after the grace period reads as
    holding none, and the bot logs in over it."""
    m, fake, clock, bot, run = _fresh(mods)
    grace = m.app._ACCOUNT_GRACE_S
    _hold(fake, OTHER)
    fake.login_delay_s = grace + 5.0
    t0 = clock.time()
    bot.initialize_mt5()
    assert [(n, round(t / 1000.0 - t0)) for n, t in fake.calls if n == 'login'] == [('login', grace)]


def test_a_reconnect_onto_a_terminal_still_logging_into_another_account_is_never_a_login(mods):
    """The terminal restarts (30 s) and comes back logging into another saved real account, 3 s after every
    initialize(): the reconnects never log in; once this bot's account is back the bot connects again (otherwise the
    first reconnect would log in over the other account)."""
    m, fake, clock, bot, run = _fresh(mods, seconds=1200)
    assert bot.initialize_mt5() is True
    t0 = clock.time()
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 20, lambda f: _hold(f, OTHER))
    fake.at(t0 + 20, lambda f: setattr(f, 'login_delay_s', 3.0))
    fake.at(t0 + 400, lambda f: _hold(f, OWN))
    ok_at = None
    for _ in range(600):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = clock.time() - t0
            break
    assert 'login' not in _names(fake) and _names(fake).count('initialize') >= 5
    assert ok_at is not None and 400 < ok_at < 470 and bot._account_bad is None
    assert len(_in_use(run)) == 1 and run.events[-1]['event'] == 'TERMINAL_RECONNECTED'


def _log_entries(path):
    with open(path) as f:
        return json.load(f)


def _process(m):
    """A new app.py process on the terminal: three start attempts, all refused."""
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    bot.credentials, bot.symbols = dict(F.CREDS), ['XAUUSDm']
    for _ in range(3):
        assert bot.initialize_mt5() is False


def test_the_launchers_restarts_do_not_fill_the_log(mods, tmp_path, monkeypatch):
    """app.py exits after its three start-up attempts and the launcher starts it again 30 s later: a new process
    reads the newest entry of the strategy log and does not repeat TERMINAL_IN_USE for 15 minutes."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    monkeypatch.setattr(m.app, 'time', real_time)               # the log's times are the wall clock
    _hold(m.fake, OTHER)
    log = out / 'logs' / 'XAUUSDm_strategy_log.json'
    _process(m)
    _process(m)
    assert [e['event'] for e in _log_entries(log)] == ['TERMINAL_IN_USE']
    entries = _log_entries(log)
    entries[0]['utc_time'] = datetime.fromtimestamp(real_time.time() - 901, tz=timezone.utc).isoformat()
    log.write_text(json.dumps(entries))
    _process(m)                                                 # 15 minutes later: once more
    assert [e['event'] for e in _log_entries(log)] == ['TERMINAL_IN_USE', 'TERMINAL_IN_USE']
    assert 'login' not in _names(m.fake)
    assert not found(log.read_text(), str(F.ACCOUNT_LOGIN)) and not found(log.read_text(), str(OTHER[0]))


def test_a_metatrader_folder_named_after_the_account_never_puts_the_number_into_the_log(mods, tmp_path, monkeypatch):
    """The owner gave the account its own MetaTrader 5, in a folder named after the account. The events about that
    terminal carry its path and problem texts that name it: the strategy log -- the dashboard's History tab shows it
    -- gets the tail instead of the number. A problem that lasts is still logged once across the launcher's restarts
    (the next process finds the masked entry and knows it)."""
    own_path = rf'C:\MT5_{F.ACCOUNT_LOGIN}\terminal64.exe'
    F.INSTALLED.add(own_path)
    try:
        out = tmp_path / 'bot_output'
        m = mods(OUTPUT_DIR=str(out))
        monkeypatch.setattr(m.app, 'time', real_time)           # the log's times are the wall clock
        _hold(m.fake, OTHER)
        log = out / 'logs' / 'XAUUSDm_strategy_log.json'
        for _ in range(2):
            bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
            bot.credentials, bot.symbols = dict(F.CREDS, terminal_path=own_path), ['XAUUSDm']
            for _ in range(3):
                assert bot.initialize_mt5() is False
        entries = _log_entries(log)
        assert [e['event'] for e in entries] == ['TERMINAL_IN_USE']             # once, not at every start
        d = entries[0]['details']
        assert d['terminal_path'] == rf'C:\MT5_{TAIL}\terminal64.exe' and f'C:\\MT5_{TAIL}\\' in d['problem']
        assert not found(log.read_text(encoding='utf-8'), str(F.ACCOUNT_LOGIN))
    finally:
        F.INSTALLED.discard(own_path)


def test_the_number_is_masked_wherever_it_stands_in_what_the_strategy_log_gets(mods):
    m = mods()
    hide = m.app._hide_login
    n, tail = F.ACCOUNT_LOGIN, TAIL
    details = {'terminal_path': rf'C:\MT5_{n}\terminal64.exe', 'zeros': f'C:/MT5-00{n}/x', 'login': n,
               'nested': [{'why': f'account {n} on Fake-Real'}, (n, 'x')], f'key {n}': 1, n: 'a number as key',
               'other': f'{n}9 and 9{n} are other numbers', 'flag': True, 'price': float(n),
               'obj': type('Request', (), {'__str__': lambda self: f'request of {n}'})()}
    out = hide(details, n, tail)
    assert out['terminal_path'] == rf'C:\MT5_{tail}\terminal64.exe' and out['zeros'] == f'C:/MT5-{tail}/x'
    assert out['login'] == tail and out['nested'] == [{'why': f'account {tail} on Fake-Real'}, [tail, 'x']]
    assert out[f'key {tail}'] == 1 and out[tail] == 'a number as key' and out['obj'] == f'request of {tail}'
    assert out['other'] == details['other'] and out['flag'] is True              # other numbers are left alone
    assert hide(details, None, None) is details                                  # no account: as it is
    loop = {'a': f'{n}'}
    loop['self'] = loop
    assert hide(loop, n, tail)['a'] == tail                                       # (a container that holds itself)


# ───────────────── the limit per problem (TERMINAL_IN_USE) ─────────────────

def test_two_other_accounts_in_turn_do_not_fill_the_log(mods):
    """TERMINAL_IN_USE must not remember only the problem it logged last: a terminal held in turn by two other
    accounts would then log every reconnect attempt (240 TERMINAL_IN_USE in 4 hours, enough to overwrite the
    200-entry strategy log in 3.3 hours). Each problem is limited on its own: logged when it is first seen, then at
    most every 15 minutes."""
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    clock.end_ms = 10 ** 15
    t0 = clock.time()
    fake.down(t0, t0 + 30)
    attach = fake.initialize
    n = {'k': 0}

    def initialize(*a, **k):                                   # each attach finds the other of the two accounts
        ok = attach(*a, **k)
        n['k'] += 1
        _hold(fake, OTHER if n['k'] % 2 else (99, 'Fake-Demo', DEMO))
        return ok
    fake.initialize = initialize
    for _ in range(4 * 3600):
        bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    times = {}
    for e in _in_use(run):
        times.setdefault(e['details']['login_tail'], []).append(e['t'] / 1000.0)
    assert n['k'] > 200 and sorted(times) == ['...4321', '...99'] and 'login' not in _names(fake)
    for t in times.values():                                   # (otherwise: every 120 s, 120 each)
        assert len(t) <= 4 * 3600 // 900 + 1 and all(b - a >= 900 for a, b in zip(t, t[1:]))


def test_the_launchers_restarts_with_two_other_accounts_in_turn_do_not_fill_the_log(mods, tmp_path, monkeypatch):
    """Across the launcher's restarts too: each start finds the terminal held by the other of two accounts. The log
    gets each account's TERMINAL_IN_USE once, not one line per start. A start after the bot ran (another entry at
    the head of the log) logs the problem again at once."""
    out = tmp_path / 'bot_output'
    m = mods(OUTPUT_DIR=str(out))
    monkeypatch.setattr(m.app, 'time', real_time)               # the log's times are the wall clock
    log = out / 'logs' / 'XAUUSDm_strategy_log.json'
    for _ in range(3):
        _hold(m.fake, OTHER)
        _process(m)
        _hold(m.fake, (99, 'Fake-Demo', DEMO))
        _process(m)
    assert [(e['event'], e['details']['login_tail']) for e in _log_entries(log)] == [('TERMINAL_IN_USE', '...99'),
                                                                                     ('TERMINAL_IN_USE', '...4321')]
    entries = _log_entries(log)
    entries.insert(0, {'time': entries[0]['time'], 'utc_time': entries[0]['utc_time'], 'symbol': 'XAUUSDm',
                       'event': 'TERMINAL_OK', 'tag': 'SIGNAL', 'details': {}})      # the bot ran in between
    log.write_text(json.dumps(entries))
    _hold(m.fake, OTHER)
    _process(m)
    assert [e['event'] for e in _log_entries(log)][:2] == ['TERMINAL_IN_USE', 'TERMINAL_OK']
    assert 'login' not in _names(m.fake)
