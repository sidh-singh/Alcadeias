"""
The bot's own login.

A login switches the account of every program attached to the terminal, and a refused one is a failed login on a
real trade server. So the bot logs in only on a terminal that showed no account for the whole grace period (a
minute: a terminal just started logs into its saved account by itself) -- and then only when all of this holds:
  * the credentials file holds a password, and one that is not a stand-in (PLACEHOLDER, CHANGE_ME, xxx);
  * no other account has claimed this MetaTrader 5 (test_live_claims.py);
  * the login budget allows it: <account folder>/login_attempt.json, written BEFORE each login, is missing, or
    this branch's credentials file changed since its own last login, or the wait for the logins that did not go
    through is over: 15 min, 30 min, 1 h, 2 h, then 6 h each time. The two bots of the account share it, and the
    same budget holds when a running bot reconnects.
Otherwise the bot does not log in: it says what the owner can do, detaches, and ends with 1 -- never with "needs the
owner": the launcher keeps attaching every 30 s, so a terminal that finishes logging into its saved account, or
that the owner logs in by hand, is picked up at once. A login the server refuses is the same: exit 1 at the
start, RECONNECT_FAILED on a reconnect. A start that passes the account checks deletes the record.
(Before: a wrong password in the file was a failed login every 90 s, from two bots, for as long as nobody looked.)
"""
import json
import os
from datetime import datetime, timezone

import pytest

from conftest import DEFAULTS, F, account_folder, boot_text, market, names_calls, stand_in_files, start_job
from conftest import found

TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
PATH = F.TERMINAL_PATH
WAITS = [900, 1800, 3600, 7200, 21600, 21600, 21600]
RIGHT = 'the-right-password'
NOT_LOGGED_IN = (f'MetaTrader 5 at {PATH} is not logged into any account. Log it into {TAIL} by hand (File > Login to '
                 f'Trade Account, Save password). The bot does not log in itself: ')


def _world(mods, seconds=600, logged_in=False, **overrides):
    """The bot's modules on a terminal that shows no account (and has none saved), with a clock that never ends."""
    fake, clock = market(seconds)
    clock.end_ms = 10 ** 15
    m = mods(fake=fake, clock=clock, **overrides)
    if not logged_in:
        fake.logged_in, fake.account_login = False, 0
    return m


def _budget_path(m):
    return account_folder(m) / 'login_attempt.json'


def _budget(m):
    return json.loads(_budget_path(m).read_text(encoding='utf-8'))


def _hm(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime('%H:%M UTC')


def _launcher(m, seconds, wait_s=30.0, events=None):
    """What start_job.bat does for `seconds`: it starts app.py again `wait_s` after it ended, unless it ended with 0
    or 78 (or the start reached the trading loop). Returns the exit codes."""
    codes, end = [], m.clock.time() + seconds
    while m.clock.time() < end:
        bot, reached = start_job(m, events=events)
        codes.append('started' if reached else bot.exit_code)
        if reached or bot.exit_code in (0, 78):
            break
        m.clock.sleep(wait_s)
    return codes


# ───────────────────────────── the grace period ─────────────────────────────

def test_the_grace_period_is_a_minute(mods):
    assert mods().app._ACCOUNT_GRACE_S == 60.0


@pytest.mark.parametrize('own', [True, False])
def test_a_terminal_that_logs_into_its_saved_account_within_the_minute_is_never_logged_in_by_the_bot(mods, own):
    """After a reboot of the server the terminal needs 45 s to log into its saved account. The bot reads the account
    again every second: its own account -> used, no login; another account -> left alone. (With the 15 s of the
    forward-test code the bot would have logged in over it at second 15.)"""
    m = _world(mods, logged_in=True)
    m.fake.login_delay_s = 45.0
    if not own:
        m.fake.account_login = 87654321
    stand_in_files(m)
    t0 = m.clock.time()
    bot, reached = start_job(m)
    assert 'login' not in names_calls(m.fake) and m.fake.logins == []
    assert reached is own
    if own:
        assert names_calls(m.fake) == ['initialize', 'shutdown']    # one attempt; detached when the job ended
        assert bot._boot_lines and any("no login: the terminal already holds this bot's account" in rec[3]
                                       for rec in bot._boot_lines)
    else:                                                           # left alone the second the other account showed
        assert bot._init_problem.startswith('TERMINAL_IN_USE: ') and m.fake.account_login == 87654321
        assert [(n, round(t / 1000.0 - t0)) for n, t in m.fake.calls[:2]] == [('initialize', 0), ('shutdown', 45)]
    assert not _budget_path(m).exists()


def test_no_account_for_the_whole_minute_and_nothing_in_the_way_the_bot_logs_in(mods, capsys):
    m = _world(mods)
    stand_in_files(m)
    t0 = m.clock.time()
    seen = {}
    login = m.fake.login

    def spy(**k):
        seen.update(k, record=_budget(m), t=m.clock.time())
        return login(**k)
    m.fake.login = spy
    bot, reached = start_job(m)
    assert reached and names_calls(m.fake) == ['initialize', 'login', 'shutdown']
    assert seen['t'] - t0 == pytest.approx(60.0) and seen['login'] == F.ACCOUNT_LOGIN
    # the record was on the disk BEFORE the login was sent
    r = seen['record']
    assert (r['at'], r['failed'], r['code'], r['by']) == (seen['t'], 1, None, DEFAULTS['BRANCH'])
    assert not _budget_path(m).exists()                             # the start passed the checks: the record is gone
    assert 'the terminal showed no account for 60 s: logging in' in capsys.readouterr().out


# ───────────────────────────── a password that is one ─────────────────────────────

@pytest.mark.parametrize('password', ['', '   ', None, 123456, True, 'PLACEHOLDER', 'placeholder', 'CHANGE_ME',
                                      'change_me', 'xxx', 'XXX', ' Placeholder '])
def test_without_a_password_in_the_file_the_bot_never_logs_in(mods, capsys, password):
    """The owner may leave the password out of the file (the repository is public) and log the terminal in by hand
    with 'Save password'. The bot then never tries a login -- and that is no reason to stop for good: it ends with
    1, and starts by itself the moment the terminal holds the account."""
    m = _world(mods)
    stand_in_files(m, credentials=dict(F.CREDS, login_pass=password))
    events = []
    bot, reached = start_job(m, events=events)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and m.fake.logins == []
    assert names_calls(m.fake) == ['initialize', 'shutdown'] * 3
    text = NOT_LOGGED_IN + 'mt5_credentials.json holds no password for it. It looks again every 30 seconds.'
    assert bot._init_problem == f'LOGIN_WAIT: {text}'
    out = capsys.readouterr().out
    assert f'✗ Not logging in: {text}' in out
    assert out.strip().splitlines()[-1] == '✗ All init attempts failed: the launcher starts the bot again in 30 seconds.'
    assert [e['event'] for e in events] == ['LOGIN_WAIT']           # once, not at every attempt
    d = events[0]['details']
    assert (d['why'], d['own_login_tail'], d['server'], d['terminal_path']) == ('no_password', TAIL,
                                                                                 F.ACCOUNT_SERVER, PATH)
    assert not _budget_path(m).exists()                             # no login was made: nothing to remember
    # the owner logs the terminal in by hand: the launcher's next start runs, with no login by the bot
    m.fake.logged_in, m.fake.account_login = True, F.ACCOUNT_LOGIN
    bot, reached = start_job(m)
    assert reached and m.fake.logins == []


def test_a_password_left_out_of_the_file_is_the_same(mods):
    m = _world(mods)
    block = dict(F.CREDS)
    del block['login_pass']
    stand_in_files(m, credentials=block)
    bot, reached = start_job(m)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and m.fake.logins == []


@pytest.mark.parametrize('password', ['x', 'xxxx', 'placeholder1', 'Change-Me', 'p4ss word'])
def test_anything_else_is_a_password_and_is_sent_as_it_is(mods, password):
    m = _world(mods)
    m.fake.password = password
    stand_in_files(m, credentials=dict(F.CREDS, login_pass=password))
    bot, reached = start_job(m)
    assert reached and [g['ok'] for g in m.fake.logins] == [True]


# ───────────────────────────── a login the server refuses ─────────────────────────────

@pytest.mark.parametrize('error', [(-6, 'Terminal: Authorization failed'), (-2, 'Terminal: Invalid params'),
                                   (-10005, 'IPC timeout'), (-1, 'Terminal: Call failed')])
def test_a_refused_login_ends_with_1_whatever_its_code_and_is_not_tried_again_at_once(mods, capsys, error):
    """-6 is the terminal's general 'not authorised', not proof of a wrong password, and after an unattended restart
    the bot must come back by itself: a refused login is never 'needs the owner'. And it is ONE login: the other two
    start attempts of the process, and the launcher's next starts, do not try the password again."""
    m = _world(mods)
    m.fake.login_error = error
    stand_in_files(m)
    events = []
    t0 = m.clock.time()
    bot, reached = start_job(m, events=events)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY and bot._owner_verdict is None
    assert len(m.fake.logins) == 1 and names_calls(m.fake).count('initialize') == 3
    r = _budget(m)
    assert (r['at'], r['failed'], r['code'], r['by']) == (t0 + 60.0, 1, error[0], DEFAULTS['BRANCH'])
    refused = (f'The server refused account {TAIL} on {F.ACCOUNT_SERVER}: check login_id, login_pass and server. '
               f'The bot tries the password again at {_hm(t0 + 60 + 900)}; a MetaTrader 5 that is logged in by hand '
               f'is used at once.')
    out = capsys.readouterr().out
    assert f'✗ Login failed: {error}. {refused}' in out
    waiting = (NOT_LOGGED_IN + f"the bot's own login was refused at {_hm(t0 + 60)} and it tries the password again at "
               f'{_hm(t0 + 60 + 900)}. It looks again every 30 seconds.')
    assert out.count(f'✗ Not logging in: {waiting}') == 2           # the second and the third attempt
    assert [e['event'] for e in events] == ['LOGIN_REFUSED', 'LOGIN_WAIT']
    d = events[0]['details']
    assert d['problem'] == f'LOGIN_REFUSED: {refused} (last_error {error})'
    assert (d['failed'], d['next_login_at'], d['own_login_tail']) == (1, t0 + 60 + 900, TAIL)
    w = events[1]['details']
    assert (w['why'], w['refused_at'], w['next_login_at'], w['failed'], w['code']) == (
        'login_budget', t0 + 60, t0 + 60 + 900, 1, error[0])
    text = json.dumps(events) + boot_text(bot) + out + _budget_path(m).read_text()
    assert not found(text, str(F.ACCOUNT_LOGIN)) and not found(text, F.CREDS['login_pass'])
    # the launcher's next starts, 30 s apart: no login, exit 1 each time
    assert _launcher(m, 600) == [1, 1, 1] and len(m.fake.logins) == 1


def test_a_slow_terminal_and_a_wrong_password_one_login_per_step_of_the_budget(mods):
    """The case the budget is for. The terminal never shows its account within the minute, and the password in the
    file is wrong. The launcher starts the bot every 30 s for 24 hours (about 380 processes, 3 start attempts
    each): the bot tries the password when the minute is over, then 15 min, 30 min, 1 h, 2 h and three times 6 h
    after the login before -- eight logins in a day, where the forward-test rule made one at every attempt (over a
    thousand)."""
    m = _world(mods, logged_in=True)
    m.fake.login_delay_s = 75.0                                     # still logging in when the minute is over
    m.fake.password = RIGHT                                         # ... and the file holds another password
    stand_in_files(m)
    t0 = m.clock.time()
    codes = _launcher(m, 24 * 3600)
    assert set(codes) == {1} and len(codes) > 350                   # never 78, never started: it keeps trying
    times = [g['t_ms'] / 1000.0 - t0 for g in m.fake.logins]
    assert not any(g['ok'] for g in m.fake.logins)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert times[0] == pytest.approx(60.0) and len(times) == 8, times
    for gap, wait in zip(gaps, WAITS):
        assert wait <= gap < wait + 300, (gaps, WAITS)              # at the first attempt after the wait is over
    r = _budget(m)
    assert r['failed'] == 8 and r['code'] == -6 and r['at'] == pytest.approx(t0 + times[-1])


def test_the_two_bots_of_an_account_share_the_budget(mods):
    """Gold and BTC of one account restart side by side on the same terminal with the same wrong password: one
    login per step for the ACCOUNT, not one per bot. (Their credentials files are two files with two dates: the
    other bot's file is no 'corrected file' for this one.)"""
    m = _world(mods)
    m.fake.password = RIGHT
    stand_in_files(m)
    stats = {DEFAULTS['BRANCH']: (1_000_000_000, 400), DEFAULTS['PARTNER_BRANCH']: (2_000_000_000, 400)}
    real_stat = m.app.MT5TradingBot._file_stat
    m.app.MT5TradingBot._file_stat = staticmethod(
        lambda path: stats[m.app.BRANCH] if str(path).endswith('mt5_credentials.json') else real_stat(path))
    t0 = m.clock.time()
    by = []
    while m.clock.time() < t0 + 4 * 3600:
        for branch in stats:                                        # the two launchers, one after the other
            m.app.BRANCH = branch
            before = len(m.fake.logins)
            bot, reached = start_job(m)
            assert not reached and bot.exit_code == 1
            by += [branch] * (len(m.fake.logins) - before)
        m.clock.sleep(30)
    times = [g['t_ms'] / 1000.0 - t0 for g in m.fake.logins]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) == 5 and all(wait <= gap < wait + 500 for gap, wait in zip(gaps, WAITS)), gaps
    assert len(by) == 5 and by[0] == DEFAULTS['BRANCH']             # (then whichever bot attaches first after a wait)
    files = _budget(m)['files']                                     # each branch's own file, as it was at its login
    assert files and all(tuple(files[b]) == stats[b] for b in files) and set(files) == set(by)


def test_a_corrected_credentials_file_may_be_tried_at_once(mods):
    """The owner corrects the password on GitHub and pulls: the file of this branch has another date and size than
    at its last refused login, so the bot may try the new password at its next start -- it does not sit out a wait
    of up to six hours."""
    m = _world(mods)
    m.fake.password = RIGHT
    stat = [(1_000_000_000, 400)]
    real_stat = m.app.MT5TradingBot._file_stat
    m.app.MT5TradingBot._file_stat = staticmethod(
        lambda path: stat[0] if str(path).endswith('mt5_credentials.json') else real_stat(path))
    stand_in_files(m)
    assert _launcher(m, 3600 + 1800) and len(m.fake.logins) == 3    # refused three times: the next wait is an hour
    assert _budget(m)['failed'] == 3
    stand_in_files(m, credentials=dict(F.CREDS, login_pass=RIGHT))
    assert _launcher(m, 200) == [1] and len(m.fake.logins) == 3     # the same file as before (as far as the bot sees)
    stat[0] = (1_000_000_500, 412)                                  # pulled: another date, another size
    t = m.clock.time()
    assert _launcher(m, 200) == ['started']
    assert len(m.fake.logins) == 4 and m.fake.logins[-1]['ok'] and m.fake.logins[-1]['t_ms'] / 1000.0 - t == 60.0
    assert not _budget_path(m).exists()


def test_a_file_changed_and_still_wrong_starts_the_waits_again_from_15_minutes(mods):
    m = _world(mods)
    m.fake.password = RIGHT
    stat = [(1_000_000_000, 400)]
    real_stat = m.app.MT5TradingBot._file_stat
    m.app.MT5TradingBot._file_stat = staticmethod(
        lambda path: stat[0] if str(path).endswith('mt5_credentials.json') else real_stat(path))
    stand_in_files(m)
    _launcher(m, 3600 + 1800)
    assert _budget(m)['failed'] == 3
    stat[0] = (1_000_000_500, 400)
    t = m.clock.time()
    _launcher(m, 1000)
    r = _budget(m)
    assert len(m.fake.logins) == 5 and r['failed'] == 2             # tried at once (1), then 15 minutes later (2)
    assert m.fake.logins[4]['t_ms'] / 1000.0 - m.fake.logins[3]['t_ms'] / 1000.0 >= 900
    assert m.fake.logins[3]['t_ms'] / 1000.0 - t == 60.0


def test_the_terminal_logged_in_by_hand_is_picked_up_at_once_and_the_record_is_cleared(mods):
    """While the bot waits for its budget the owner logs the terminal in by hand: the next attach finds the account
    and starts -- no login by the bot -- and the record of the refused login is deleted (it is over)."""
    m = _world(mods)
    m.fake.password = RIGHT
    stand_in_files(m)
    t0 = m.clock.time()
    m.fake.at(t0 + 700, lambda f: (setattr(f, 'logged_in', True), setattr(f, 'account_login', F.ACCOUNT_LOGIN)))
    codes = _launcher(m, 3600)
    assert codes[-1] == 'started' and set(codes[:-1]) == {1}
    assert len(m.fake.logins) == 1 and not _budget_path(m).exists()
    assert m.clock.time() - t0 < 700 + 70                           # picked up within the second it showed


# ───────────────────────────── the record itself ─────────────────────────────

def test_the_waits_are_15_30_60_120_minutes_then_six_hours(mods):
    a = mods().app
    assert [a._login_wait_s(n) for n in range(0, 9)] == [900, 900, 1800, 3600, 7200, 21600, 21600, 21600, 21600]
    assert a._login_wait_s(None) == a._login_wait_s('x') == 21600


def _waiting_bot(mods):
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), credentials=F.CREDS)
    bot.mt5_initialized, bot.position_helper = False, None
    return m, bot


@pytest.mark.parametrize('content', ['', '{"at": ', '[]', '"x"', '{}', '{"at": "yesterday", "failed": 1}',
                                     '{"at": 1.0, "failed": -1}', '{"at": 1.0, "failed": 1.5}', '\x00\x00'])
def test_a_record_that_holds_no_usable_entry_counts_as_the_longest_wait(mods, content):
    """A damaged login_attempt.json: nothing is raised, no login is made on the strength of it, and the bot is not
    locked out for good either -- it counts as the last of the waits, from the time the file was written."""
    m, bot = _waiting_bot(mods)
    path = _budget_path(m)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding='utf-8')
    written = m.clock.time()
    os.utime(path, (written, written))
    for later, allowed in ((0, False), (21599, False), (21600, True)):
        budget = bot._login_budget(written + later)
        assert budget['allowed'] is allowed, later
    assert bot.initialize_mt5() is False and m.fake.logins == []
    assert 'did not go through' in bot._init_problem


def test_a_record_that_cannot_be_read_this_moment_allows_no_login(mods, monkeypatch):
    m, bot = _waiting_bot(mods)
    path = _budget_path(m)
    path.parent.mkdir(parents=True)
    path.mkdir()                                                    # (a folder in its place: the open is refused)
    assert bot._login_budget(m.clock.time()) == {'allowed': False, 'why': 'budget_unreadable', 'failed': 0, 'files': {}}
    assert bot.initialize_mt5() is False and m.fake.logins == []
    assert "the record of the bot's last own login cannot be read right now" in bot._init_problem


def test_without_a_record_on_the_disk_there_is_no_login(mods):
    """The record is written BEFORE the login. When it cannot be written (a full disk, a folder Windows refuses)
    the bot does not log in: without the record nothing would bound the next logins."""
    m, bot = _waiting_bot(mods)

    def disk_full(path, data):
        raise OSError(28, 'No space left on device')
    m.app._write_json_atomic = disk_full
    assert bot.initialize_mt5() is False and m.fake.logins == [] and 'login' not in names_calls(m.fake)
    assert "the record of the bot's own logins cannot be written (OSError: [Errno 28]" in bot._init_problem
    assert bot._init_problem.startswith('LOGIN_WAIT: ')


def test_a_clock_that_was_set_back_does_not_lock_the_login_for_good(mods):
    m, bot = _waiting_bot(mods)
    now = m.clock.time()
    path = _budget_path(m)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'at': now + 86400, 'failed': 1, 'code': -6}), encoding='utf-8')   # "tomorrow"
    assert bot._login_budget(now)['allowed'] is True                # more than the wait away, either side: allowed
    path.write_text(json.dumps({'at': now + 300, 'failed': 1, 'code': -6}), encoding='utf-8')
    assert bot._login_budget(now)['allowed'] is False and bot._login_budget(now + 1200)['allowed'] is True


def test_the_record_holds_no_account_number_and_no_password(mods):
    m = _world(mods)
    m.fake.login_error = (-6, 'Terminal: Authorization failed')
    stand_in_files(m)
    start_job(m)
    r = _budget(m)
    assert set(r) == {'at', 'at_utc', 'failed', 'code', 'cred_mtime_ns', 'cred_size', 'by', 'files'}
    text = _budget_path(m).read_text()
    assert not found(text, str(F.ACCOUNT_LOGIN)) and not found(text, F.CREDS['login_pass'])
    assert [p.name for p in account_folder(m).iterdir()] == ['login_attempt.json']     # no temp file left


# ───────────────────────────── a running bot that reconnects ─────────────────────────────

def test_the_same_budget_holds_when_a_running_bot_reconnects(mods):
    """The terminal restarts under a running bot and comes back showing no account; the password in the file is
    wrong. The bot reconnects with its back-off for 12 hours: it never ends, and it tries the password once per
    step of the budget -- not at every reconnect (the forward-test rule: one login a minute, 720 of them)."""
    fake, clock = market(600)
    clock.end_ms = 10 ** 15
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    m.app.print = lambda *a, **k: None
    assert bot._poll_guard('XAUUSDm')
    t0 = clock.time()
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 10, lambda f: (setattr(f, 'logged_in', False), setattr(f, 'account_login', 0),
                                setattr(f, 'password', RIGHT)))
    while clock.time() < t0 + 12 * 3600:
        clock.sleep(1)
        assert not bot._poll_guard('XAUUSDm')
    times = [g['t_ms'] / 1000.0 - t0 for g in fake.logins]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) == 6 and all(wait <= gap < wait + 200 for gap, wait in zip(gaps, WAITS)), (times, gaps)
    assert bot.exit_code == m.app.EXIT_RETRY and bot._owner_verdict is None      # nothing ended, nothing was decided
    why = {e['details']['why'].split(':')[0] for e in run.events if e['event'] == 'RECONNECT_FAILED'}
    assert why == {'initialize failed', 'LOGIN_REFUSED', 'LOGIN_WAIT'}
    assert len(run.events) < 120                                    # (12 hours of failing reconnects, kept short)
    # the owner logs the terminal in by hand: the next reconnect finds the account, no login, and the bot trades on
    fake.logged_in, fake.account_login = True, F.ACCOUNT_LOGIN
    n = len(fake.logins)
    for _ in range(200):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            break
    assert bot.mt5_initialized and len(fake.logins) == n and not _budget_path(m).exists()
    assert run.events[-1]['event'] == 'TERMINAL_RECONNECTED'


def test_no_file_is_touched_and_no_event_is_written_while_the_reconnect_holds_the_terminal_lock(mods, monkeypatch):
    """A reconnect makes its terminal calls inside mt5_lock; the login record, the claims and the strategy log are
    read and written between them, with the lock free (no order, close or terminal read waits for the disk)."""
    import builtins
    fake, clock = market(600)
    clock.end_ms = 10 ** 15
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    m.app.print = lambda *a, **k: None
    assert bot._poll_guard('XAUUSDm')
    seen = {'terminal_unlocked': 0, 'files_locked': [], 'events_locked': []}
    for name in ('initialize', 'login', 'account_info', 'shutdown', 'terminal_info'):
        def wrapped(*a, _call=getattr(fake, name), **k):
            seen['terminal_unlocked'] += not bot.mt5_lock.locked()
            return _call(*a, **k)
        setattr(fake, name, wrapped)
    folder = str(account_folder(m).parent)

    def watching(op):
        def call(path, *a, **k):
            if bot.mt5_lock.locked() and str(path).startswith(folder):
                seen['files_locked'].append((op.__name__, str(path)))
            return op(path, *a, **k)
        return call
    m.app.open = watching(builtins.open)
    for name in ('replace', 'remove', 'makedirs', 'link', 'stat', 'listdir'):
        monkeypatch.setattr(os, name, watching(getattr(os, name)))
    log_event = bot._log_event
    bot._log_event = lambda *a, **k: (seen['events_locked'].append(a[1]) if bot.mt5_lock.locked() else None,
                                      log_event(*a, **k))[1]
    t0 = clock.time()
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 10, lambda f: (setattr(f, 'logged_in', False), setattr(f, 'account_login', 0),
                                setattr(f, 'login_error', (-6, 'Terminal: Authorization failed'))))
    fake.at(t0 + 1500, lambda f: (setattr(f, 'logged_in', True), setattr(f, 'account_login', 87654321)))
    fake.at(t0 + 2500, lambda f: setattr(f, 'account_login', F.ACCOUNT_LOGIN))
    for _ in range(3000):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm') and clock.time() > t0 + 2500:
            break
    assert bot.mt5_initialized and len(fake.logins) == 2            # refused, 15 minutes, refused; then by hand
    events = {e['event'] for e in run.events}
    assert {'LOGIN_REFUSED', 'LOGIN_WAIT', 'TERMINAL_IN_USE', 'RECONNECT_FAILED', 'TERMINAL_RECONNECTED'} <= events
    assert seen['terminal_unlocked'] == 0                           # every terminal call inside the lock
    assert seen['files_locked'] == [] and seen['events_locked'] == []
