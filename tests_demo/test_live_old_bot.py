"""
An old bot that still runs on the server.

The old bots (the hedging_* branches) have no account check and no magic number: an old bot trades whatever account
its MetaTrader 5 is logged into, takes every position of its symbol for its own -- it would add to this bot's trades
and close them at $1 of profit -- and logs that terminal into its own account at every start. Every credentials
file arrives naming the MetaTrader 5 the old bots use.

The new bot cannot stop an old one; it can see it. An old bot rewrites account.json, XAUUSDm.json and BTCUSDm.json
in ITS output folder -- the folder the new bots' own folders are in -- about once a second, and nothing of the
real-money branches writes there. _old_bot_alive(): the newest of those files changed less than 120 s ago; looked at
every 10 s and kept as a flag (the poll loop reads the flag; no terminal call, never inside mt5_lock).

Rule A, at the start: an old bot alive AND this bot's terminal_path is the old bots' MetaTrader 5 -> the bot does
not attach at all, says what to do, and ends with 1 -- it starts by itself once the old bot is stopped. On another
MetaTrader 5 the old bot trades the account that MetaTrader 5 holds: the bot starts, with a note in its window (the
banner is the poll loop's).
"""
import os

import pytest

from conftest import NO_LADDER, START, F, boot_text, market, names_calls, run_bot, stand_in_files, start_job
from conftest import account_folder, found

OLD = r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'       # the old bots' MetaTrader 5
OWN = r'C:\MT5 of this account\terminal64.exe'                     # an installation of this account's own
TEXT = ('An old bot is running on this server and uses the same MetaTrader 5. It trades whatever account that '
        "MetaTrader 5 is logged into, and it would add to and close this bot's trades. Stop it; this bot then starts "
        'by itself.')


@pytest.fixture(autouse=True)
def _installed():
    """Both installations exist on the fake server."""
    F.INSTALLED.update({OLD, OWN})
    try:
        yield
    finally:
        F.INSTALLED.difference_update({OLD, OWN})


def _old_bot_writes(tmp_path, name, clock, ago=1.0):
    """The old bot rewrote `name` in its output folder `ago` seconds before the clock's now."""
    path = tmp_path / name
    path.write_text('{}')
    t = clock.time() - ago
    os.utime(path, (t, t))
    return path


def _world(mods, seconds=600):
    fake, clock = market(seconds)
    clock.end_ms = 10 ** 15
    return mods(fake=fake, clock=clock)


# ───────────────────────────── the flag ─────────────────────────────

def test_an_old_bot_is_alive_while_one_of_its_files_was_changed_in_the_last_two_minutes(mods, tmp_path):
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    assert bot._old_bot_alive() is False and bot._old_bot_age_s is None      # no such file: no old bot
    for name in ('account.json', 'XAUUSDm.json', 'BTCUSDm.json'):
        path = _old_bot_writes(tmp_path, name, m.clock, ago=30)
        assert bot._old_bot_alive(force=True) is True and bot._old_bot_age_s == 30.0, name
        for ago, alive in ((119.0, True), (120.0, False), (121.0, False), (86400.0, False), (0.0, True)):
            _old_bot_writes(tmp_path, name, m.clock, ago=ago)
            assert bot._old_bot_alive(force=True) is alive and bot._old_bot_age_s == ago, (name, ago)
            assert bot._old_bot_alive_flag is alive
        path.unlink()
    assert bot._old_bot_alive(force=True) is False and bot._old_bot_age_s is None


def test_the_age_of_the_old_bots_files_is_handed_to_the_trace_only_while_it_is_alive(mods, tmp_path):
    """_foreign (the poll local the trace reads, and the dashboard's amber banner from it): old_bot_age_s is the age
    of the old bot's newest file while the old bot is alive, None otherwise -- the old bots' files stay in the parent
    folder long after they were stopped, and an age of days must not read as "an old bot is running"."""
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    path = _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=3600.0)       # stopped an hour ago
    assert bot._old_bot_alive(force=True) is False and bot._old_bot_age_s == 3600.0
    fo = bot._foreign_now()
    assert fo['old_bot_age_s'] is None and fo['old_bot_same_terminal'] is False
    for ago, alive in ((30.0, True), (119.0, True), (120.0, False), (86400.0 * 30, False), (5.0, True)):
        _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=ago)
        assert bot._old_bot_alive(force=True) is alive
        assert bot._foreign_now()['old_bot_age_s'] == (ago if alive else None), ago
    path.unlink()
    assert bot._old_bot_alive(force=True) is False and bot._foreign_now()['old_bot_age_s'] is None


def test_the_newest_of_its_files_counts(mods, tmp_path):
    """The old gold bot is stopped (its file is a day old), the old BTC bot still runs: an old bot is alive."""
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=86400)
    _old_bot_writes(tmp_path, 'account.json', m.clock, ago=3)
    _old_bot_writes(tmp_path, 'BTCUSDm.json', m.clock, ago=4)
    assert bot._old_bot_alive(force=True) is True and bot._old_bot_age_s == 3.0


def test_a_file_dated_a_little_ahead_of_this_clock_is_fresh_one_dated_far_ahead_is_not(mods, tmp_path):
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    _old_bot_writes(tmp_path, 'account.json', m.clock, ago=-60)
    assert bot._old_bot_alive(force=True) is True
    _old_bot_writes(tmp_path, 'account.json', m.clock, ago=-3600)   # (a file with a wrong date is not a running bot)
    assert bot._old_bot_alive(force=True) is False


def test_only_the_old_bots_own_files_in_the_folder_beside_this_bot_count(mods, tmp_path):
    """This bot's own account.json and <SYMBOL>.json are in ITS folder, and it rewrites them every poll: they are not
    the old bot's. Nor is any other file of the folder the bots' folders are in."""
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    own = tmp_path / 'bot_output'
    own.mkdir(exist_ok=True)
    for path in (own / 'account.json', own / 'XAUUSDm.json', own / 'BTCUSDm.json', tmp_path / 'EURUSDm.json',
                 tmp_path / 'XAUUSDm_trace.json', tmp_path / 'active_config.json'):
        path.write_text('{}')
        t = m.clock.time() - 1
        os.utime(path, (t, t))
    assert bot._old_bot_alive(force=True) is False and bot._old_bot_age_s is None


def test_the_files_are_looked_at_every_ten_seconds_and_the_flag_is_kept_between(mods, tmp_path, monkeypatch):
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    looked = []
    stat = os.stat
    monkeypatch.setattr(os, 'stat', lambda p, *a, **k: (looked.append(str(p)) if str(p).endswith('.json') and
                                                         os.path.dirname(str(p)) == str(tmp_path) else None,
                                                         stat(p, *a, **k))[1])
    assert bot._old_bot_alive() is False and len(looked) == 3       # the three files, once
    _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=0)       # the old bot starts
    looked.clear()
    for _ in range(9):                                              # the polls of the next 9 s: the flag, no file read
        m.clock.sleep(1)
        assert bot._old_bot_alive() is False
    assert looked == []
    m.clock.sleep(1)
    assert bot._old_bot_alive() is True and len(looked) == 3        # 10 s after the last look
    assert bot._old_bot_age_s == 10.0 and bot._old_bot_alive_flag is True
    looked.clear()
    assert bot._old_bot_alive(force=True) is True and len(looked) == 3      # (the start asks for a fresh look)


def test_looking_for_an_old_bot_never_raises_and_calls_no_terminal(mods, tmp_path, monkeypatch):
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    calls = []
    for name in ('terminal_info', 'account_info', 'positions_get', 'symbol_info_tick'):
        monkeypatch.setattr(m.fake, name, lambda *a, _n=name, **k: calls.append(_n))
    _old_bot_writes(tmp_path, 'account.json', m.clock, ago=1)
    assert bot._old_bot_alive(force=True) is True and calls == []

    def boom(*a, **k):
        raise RuntimeError('anything')
    monkeypatch.setattr(m.app, '_parent_folder', boom)
    assert bot._old_bot_alive(force=True) is False and bot._old_bot_age_s is None      # no old bot seen, no exception
    monkeypatch.undo()
    m.app.OUTPUT_DIR = str(tmp_path / 'no' / 'such' / 'folder' / 'bot_output')
    assert bot._old_bot_alive(force=True) is False


def test_same_terminal_means_alive_and_on_the_old_bots_metatrader(mods, tmp_path):
    """The flag the poll loop reads for its own rule (no new trade beside an old bot): no file is read by it."""
    m = _world(mods)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), credentials=F.account_credentials(terminal_path=OLD))
    assert bot._old_bot_same_terminal() is False
    _old_bot_writes(tmp_path, 'account.json', m.clock, ago=1)
    assert bot._old_bot_same_terminal() is False                    # (the flag is as old as the last look)
    bot._old_bot_alive(force=True)
    assert bot._old_bot_same_terminal() is True
    bot.credentials = F.account_credentials(terminal_path=OWN)
    assert bot._old_bot_same_terminal() is False                    # alive, but on another MetaTrader 5
    bot.credentials = None
    assert bot._old_bot_same_terminal() is False


# ───────────────────────────── rule A: the start ─────────────────────────────

@pytest.mark.parametrize('path', [OLD, 'c:/program files/metatrader 5 exness/TERMINAL64.EXE'])
def test_a_bot_does_not_start_beside_an_old_bot_on_the_same_metatrader(mods, tmp_path, capsys, path):
    """The old bot of this account is still running and the credentials name its MetaTrader 5 (as every file does
    when it arrives). The new bot does not even attach: no terminal call. It says what to do and ends with 1 --
    not 78: once the old bot is stopped it starts by itself."""
    m = _world(mods)
    stand_in_files(m, credentials=F.account_credentials(terminal_path=path))
    _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=1)
    events = []
    bot, reached = start_job(m, events=events)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY == 1 and bot._owner_verdict is None
    assert m.fake.calls == [] and m.fake.orders == []               # before mt5.initialize: nothing was attached to
    assert bot._init_problem == f'OLD_BOT_SAME_TERMINAL: {TEXT}'
    out = capsys.readouterr().out
    assert out.count(f'✗ Not attaching: {TEXT}') == 3               # each of the three attempts looked again
    assert out.strip().splitlines()[-1] == '✗ All init attempts failed: the launcher starts the bot again in 30 seconds.'
    assert [e['event'] for e in events] == ['OLD_BOT_SAME_TERMINAL']    # once, not at every attempt
    d = events[0]['details']
    assert d['problem'] == f'OLD_BOT_SAME_TERMINAL: {TEXT}' and d['terminal_path'] == path.strip()
    assert d['old_bot_age_s'] == 1.0 and events[0]['tag'] == 'ERROR'
    assert not (tmp_path / 'terminal_claims').exists()              # nothing was claimed either


def test_it_starts_by_itself_once_the_old_bot_is_stopped(mods, tmp_path):
    """The launcher starts the bot every 30 s. The old bot writes its files until the owner stops it; two minutes
    after its last write the new bot starts."""
    m = _world(mods)
    stand_in_files(m, credentials=F.account_credentials(terminal_path=OLD))
    t0 = m.clock.time()
    stopped_at = t0 + 300
    codes = []
    while m.clock.time() < t0 + 900:
        _old_bot_writes(tmp_path, 'account.json', m.clock, ago=max(0.0, m.clock.time() - stopped_at))
        bot, reached = start_job(m)
        codes.append('started' if reached else bot.exit_code)
        if reached:
            break
        for _ in range(30):                                         # (the old bot goes on writing meanwhile)
            m.clock.sleep(1)
            _old_bot_writes(tmp_path, 'account.json', m.clock, ago=max(0.0, m.clock.time() - stopped_at))
    assert codes[-1] == 'started' and set(codes[:-1]) == {1} and len(codes) > 3
    assert 420 <= m.clock.time() - t0 < 420 + 60                    # 120 s after the old bot's last write
    assert names_calls(m.fake) == ['initialize', 'shutdown']        # and not one terminal call before


def test_an_old_bot_on_another_metatrader_does_not_stop_the_start(mods, tmp_path, capsys):
    """This account has its own installation: the old bot trades the account ITS MetaTrader 5 is logged into. The
    bot starts, and says so in its window at the start (spec 6.4: the 6.2 texts are printed at the start too) -- as a
    note, not a refusal and not an event: the banner and its event are the poll loop's, from the flag."""
    m = _world(mods)
    stand_in_files(m, credentials=F.account_credentials(terminal_path=OWN))
    _old_bot_writes(tmp_path, 'BTCUSDm.json', m.clock, ago=1)
    events = []
    bot, reached = start_job(m, events=events)
    out = capsys.readouterr().out
    tail = '...' + str(F.ACCOUNT_LOGIN)[-4:]
    assert reached and not events and not found(out, TEXT)
    note = [ln for ln in out.splitlines() if ln.startswith('⚠ An old bot is running on this server')]
    assert len(note) == 1 and note[0].startswith(
        "⚠ An old bot is running on this server, with another MetaTrader 5 than this bot's. This bot starts. Make "
        f'sure the old bot does not trade account {tail}')
    assert str(F.ACCOUNT_LOGIN) not in note[0] and not found(boot_text(bot), str(F.ACCOUNT_LOGIN))
    assert any(rec[1:3] == ('WARN', 'START') and rec[4] == {'old_bot_age_s': 1.0} for rec in bot._boot_lines)
    assert bot._old_bot_alive_flag is True and bot._old_bot_same_terminal() is False


def test_without_an_old_bot_the_start_says_nothing_of_one(mods, tmp_path, capsys):
    m = _world(mods)
    stand_in_files(m, credentials=F.account_credentials(terminal_path=OWN))
    _old_bot_writes(tmp_path, 'BTCUSDm.json', m.clock, ago=600)     # (its files are there, ten minutes old)
    bot, reached = start_job(m)
    assert reached and not found(capsys.readouterr().out, 'old bot')


def test_without_an_old_bot_the_old_bots_metatrader_is_this_accounts_terminal_like_any_other(mods, tmp_path):
    m = _world(mods)
    stand_in_files(m, credentials=F.account_credentials(terminal_path=OLD))
    _old_bot_writes(tmp_path, 'account.json', m.clock, ago=7200)    # its files are there, two hours old
    bot, reached = start_job(m)
    assert reached and bot._old_bot_alive_flag is False and m.fake.init_paths == [OLD]


def test_a_running_bot_that_reconnects_is_not_kept_from_its_trades_by_an_old_bot(mods, tmp_path):
    """Rule A is the start's. A bot that already runs -- and may hold trades -- loses the terminal while an old bot
    is alive on the same MetaTrader 5: it reconnects (what it may still open then is the poll loop's rule)."""
    m = _world(mods)
    run = F.Run()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', run, credentials=F.account_credentials(terminal_path=OLD))
    assert bot._poll_guard('XAUUSDm')
    t0 = m.clock.time()
    m.fake.down(t0 + 0.5, t0 + 30.5)
    ok = False
    for _ in range(120):
        m.clock.sleep(1)
        _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=0)
        bot._old_bot_alive()                                        # (as the loop does on every pass)
        if bot._poll_guard('XAUUSDm') and m.clock.time() > t0 + 31:
            ok = True
            break
    assert ok and bot.mt5_initialized and bot._old_bot_same_terminal() is True
    assert 'OLD_BOT_SAME_TERMINAL' not in [e['event'] for e in run.events]
    bot.mt5_initialized, bot.position_helper = False, None         # ... while a START there is refused
    assert bot.initialize_mt5() is False and bot._init_problem.startswith('OLD_BOT_SAME_TERMINAL: ')


# ───────────────────────────── never a login beside an old bot ─────────────────────────────

@pytest.mark.parametrize('terminal, refused', [(OLD, True), (OWN, False)])
def test_a_reconnect_never_logs_the_old_bots_metatrader_in_while_an_old_bot_is_alive(mods, tmp_path, capsys,
                                                                                     terminal, refused):
    """A running bot on the old bots' MetaTrader 5, an old bot alive there (its file changes every second). The
    terminal restarts and comes back with no account. A login would switch the account of every program on that
    terminal: the old ladder bot would then trade this real account and add to or close this bot's trades. So the
    bot does not log in -- the line and the event of rule A -- and does so by itself once the old bot has been stopped
    for two minutes. On its own MetaTrader 5 (the old bot trades the account of ITS terminal) the login goes ahead."""
    m = _world(mods, seconds=900)
    run = F.Run()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', run, credentials=F.account_credentials(terminal_path=terminal))
    assert bot._poll_guard('XAUUSDm')
    t0 = m.clock.time()
    stopped_at = t0 + 400                                           # the owner stops the old bot
    m.fake.down(t0 + 0.5, t0 + 30.5)
    m.fake.at(t0 + 10, lambda f: (setattr(f, 'logged_in', False), setattr(f, 'account_login', 0)))
    seen_refused = False
    for _ in range(900):
        m.clock.sleep(1)
        if m.clock.time() < stopped_at:
            _old_bot_writes(tmp_path, 'XAUUSDm.json', m.clock, ago=0)
        bot._old_bot_alive()                                        # (as the loop does on every pass)
        if bot._poll_guard('XAUUSDm'):
            break
        seen_refused = seen_refused or bot._init_problem == f'OLD_BOT_SAME_TERMINAL: {TEXT}'
    logins = [(g['t_ms'] / 1000.0 - t0, g['ok']) for g in m.fake.logins]
    assert bot.mt5_initialized and len(logins) == 1 and logins[0][1] is True
    if refused:
        assert logins[0][0] >= stopped_at - t0 + 120                # not one login while the old bot was alive
        assert seen_refused and f'✗ Not logging in: {TEXT}' in capsys.readouterr().out
        ev = [e for e in run.events if e['event'] == 'OLD_BOT_SAME_TERMINAL']
        assert len(ev) == 1 and ev[0]['details']['problem'] == f'OLD_BOT_SAME_TERMINAL: {TEXT}'
        assert ev[0]['details']['terminal_path'] == OLD and ev[0]['tag'] == 'ERROR'
        assert {e['event'] for e in run.events} >= {'RECONNECT_FAILED', 'TERMINAL_RECONNECTED'}
        assert 'LOGIN_WAIT' not in [e['event'] for e in run.events]
    else:
        assert logins[0][0] < 200 and not seen_refused             # the grace minute and the back-off: no more
        assert 'OLD_BOT_SAME_TERMINAL' not in [e['event'] for e in run.events]
    assert bot.exit_code == m.app.EXIT_RETRY and bot._owner_verdict is None      # a reconnect never ends the bot


def test_an_old_bot_that_starts_during_the_grace_minute_gets_no_login_at_the_start_either(mods, tmp_path, capsys):
    """Rule A passed (no old bot yet); MetaTrader 5 shows no account; 20 s later an old bot starts on it. At the end
    of the grace minute the bot does not log in: the same line, the same event, exit 1 (it starts by itself later)."""
    m = _world(mods)
    m.fake.logged_in, m.fake.account_login = False, 0
    stand_in_files(m, credentials=F.account_credentials(terminal_path=OLD))
    t0 = m.clock.time()

    def old_bot(f):                                                 # rewrites its file every second from now on
        _old_bot_writes(tmp_path, 'account.json', m.clock, ago=0)
        f.at(m.clock.time() + 1.0, old_bot)
    m.fake.at(t0 + 20, old_bot)
    events = []
    bot, reached = start_job(m, events=events)
    assert not reached and bot.exit_code == m.app.EXIT_RETRY == 1 and bot._owner_verdict is None
    assert m.fake.logins == [] and 'login' not in names_calls(m.fake)
    assert bot._init_problem == f'OLD_BOT_SAME_TERMINAL: {TEXT}'
    out = capsys.readouterr().out
    assert out.count(f'✗ Not logging in: {TEXT}') == 1 and out.count(f'✗ Not attaching: {TEXT}') == 2
    assert [e['event'] for e in events] == ['OLD_BOT_SAME_TERMINAL']    # once, not at every attempt
    assert not (account_folder(m) / 'login_attempt.json').exists()  # no login was even prepared


# ───────────────────────────── the loop keeps the flag fresh ─────────────────────────────

@pytest.mark.parametrize('refused', [False, True])
def test_the_poll_loop_looks_every_ten_seconds_on_every_pass_a_refused_one_too(tmp_path, refused):
    """While the bot runs an old bot is started (its file is written from second 20 on). The loop sees it within
    10 s -- also when every pass is refused by the guard (the old bot has just switched the terminal to its own
    account: exactly when the flag matters)."""
    fake, clock = market(60)
    stamps = []

    def old_bot(f):                                                 # rewrites its file every second from now on
        path = tmp_path / 'account.json'
        path.write_text('{}')
        os.utime(path, (clock.time(), clock.time()))
        if clock.time() < START + 58:
            f.at(clock.time() + 1.0, old_bot)
    fake.at(START + 20, old_bot)
    if refused:
        fake.at(START + 5, lambda f: setattr(f, 'account_login', 87654321))

    def on_new_bot(bot, n):
        look = bot._old_bot_alive

        def recording(force=False):
            alive = look(force)
            stamps.append((round(clock.time() - START, 1), alive, bot._old_bot_checked_at - START))
            return alive
        bot._old_bot_alive = recording
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'state', on_new_bot=on_new_bot)
    assert len(stamps) >= 50                                        # asked on every pass
    looks = sorted({round(at, 1) for _, _, at in stamps})
    assert all(9.9 <= b - a <= 11.1 for a, b in zip(looks, looks[1:])), looks      # the files: every 10 s
    first_alive = min(t for t, alive, _ in stamps if alive)
    assert 20 <= first_alive <= 31
    assert all(alive for t, alive, _ in stamps if t > 31)
    if refused:
        assert all(p['t'] < (START + 5) * 1000 for p in run.polls)  # no pass decided anything after the switch
        assert [e['event'] for e in run.events if e['event'].startswith('ACCOUNT')] == ['ACCOUNT_REFUSED']
    else:
        assert len(run.polls) >= 50 and not run.errors

