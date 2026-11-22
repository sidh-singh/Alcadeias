"""
One process per branch.

Two processes of one bot -- a second window, a scheduled task plus a start by hand -- share the magic number, the
symbol, the account and the state files. Both see "flat" and both send the entry in the same second: twice the
size the unit rule allows; each then takes the other's position for a leg of its own basket. So, before anything
else, a starting bot takes an exclusive system lock, without waiting, on OUTPUT_DIR/state/<SYMBOL>.lock and keeps
the file open for as long as it runs:
  * held by another process -> one line ("... is already running in another window ...") and EXIT_NEEDS_OWNER:
    the launcher does not start it again, and the second process touched nothing (no terminal call, no file of the
    running bot);
  * the system frees the lock when the process ends, however it ends: a crash leaves nothing to clean up, and the
    launcher's restart 30 s later is never refused by its own predecessor;
  * if the locking call itself fails for another reason than "held", the bot starts with a warning: a lock that
    cannot be asked must not keep a bot from its open trades.
On this PC the lock is fcntl.flock; on the server (Windows) msvcrt.locking, whose Python side is tested here with
a stand-in for the msvcrt module -- what Windows itself does cannot be tested on this system.
"""
import errno
import gc
import os
import subprocess
import sys
import types

import pytest

from conftest import BRANCH, ROOT, F, stand_in_files, start_job, symbols_config
from conftest import found

LINE = f'✗ This bot ({BRANCH}) is already running in another window on this server. This window stops.'


def _lock_path(m, symbol='XAUUSDm'):
    return os.path.join(m.app.OUTPUT_DIR, 'state', f'{symbol}.lock')


def _tree(path):
    """Every file under a folder with its size and its modification time."""
    out = {}
    for folder, _, files in os.walk(path):
        for name in files:
            p = os.path.join(folder, name)
            st = os.stat(p)
            out[os.path.relpath(p, path)] = (st.st_size, st.st_mtime_ns)
    return out


def test_a_second_process_of_the_same_bot_ends_with_78_and_touches_nothing(mods, capsys):
    """While the first bot is in its trading loop a second one is started on the same folder: it prints the line,
    ends with 78, and has neither read the credentials nor called the terminal nor written a file. When the first
    has ended, the next start runs."""
    m = mods()
    opened = stand_in_files(m)
    second = {}

    def while_the_first_runs(first):
        assert os.path.isfile(_lock_path(m))                        # the first holds the lock
        calls, files, reads = list(m.fake.calls), _tree(m.app.OUTPUT_DIR), opened.count('mt5_credentials.json')
        capsys.readouterr()
        bot, reached = start_job(m)
        second.update(bot=bot, reached=reached, out=capsys.readouterr().out,
                      untouched=(m.fake.calls == calls and _tree(m.app.OUTPUT_DIR) == files
                                 and opened.count('mt5_credentials.json') == reads))
    first, reached = start_job(m, loop=while_the_first_runs)
    assert reached and first.exit_code == m.app.EXIT_RETRY          # (its stand-in loop came back)
    bot = second['bot']
    assert bot.exit_code == m.app.EXIT_NEEDS_OWNER == 78 and not second['reached']
    assert second['out'].strip() == LINE                            # one line, and nothing else
    assert second['untouched'] and m.fake.orders == []
    assert bot._process_locks == {} and not bot.mt5_initialized
    # the first has ended: its lock is free, the launcher's next start is not refused by its predecessor
    again, reached = start_job(m)
    assert reached and again.exit_code != m.app.EXIT_NEEDS_OWNER


@pytest.mark.skipif(os.name == 'nt', reason='the other process of this test locks with fcntl')
def test_a_bot_running_in_another_process_holds_the_lock_until_it_ends(mods, capsys, tmp_path):
    """Across real processes: another process holds the lock file of this bot's folder (as a running bot does). A
    start here ends with 78. That process is killed (a crash: nothing cleans up) -- the lock is free at once."""
    m = mods()
    stand_in_files(m)
    path = _lock_path(m)
    os.makedirs(os.path.dirname(path))
    holder = subprocess.Popen(
        [sys.executable, '-B', '-c',
         'import fcntl, os, sys, time\n'
         'fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)\n'
         'fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
         'print("locked", flush=True)\n'
         'time.sleep(120)\n', path], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == 'locked'
        bot, reached = start_job(m)
        assert bot.exit_code == 78 and not reached and m.fake.calls == []
        assert capsys.readouterr().out.strip() == LINE
    finally:
        holder.kill()
        holder.wait(timeout=30)
        holder.stdout.close()
    bot, reached = start_job(m)
    assert reached


def test_a_lock_that_is_let_go_a_moment_later_does_not_stop_the_start(mods, capsys):
    """The process before this one has just ended and the system frees its lock a moment later: the lock is asked
    three times, a second apart, before the bot says that it is already running."""
    m = mods()
    stand_in_files(m)
    asked = []
    lock_fd = m.app._lock_fd

    def held_at_first(fd):
        asked.append(m.clock.time())
        return lock_fd(fd) if len(asked) >= 3 else False
    m.app._lock_fd = held_at_first
    bot, reached = start_job(m)
    assert reached and len(asked) == 3 and asked[2] - asked[0] == pytest.approx(2.0)
    assert not found(capsys.readouterr().out, 'already running')
    m.app._lock_fd = lambda fd: asked.append('again') or False     # held for good: three tries, then the refusal
    bot, reached = start_job(m)
    assert bot.exit_code == 78 and not reached and asked[3:] == ['again'] * 3
    assert bot._process_locks == {}                                 # (the file it opened to ask is closed again)


def test_the_lock_is_free_again_however_the_job_ended(mods, capsys):
    """The job ends with 78 (a branch that cannot run), with 1 (a failed start), by Ctrl+C or by an exception: in
    every case the lock is let go with it -- the next start of the same folder is never refused as 'already
    running'."""
    m = mods()
    stand_in_files(m)

    def ctrl_c(bot):
        raise KeyboardInterrupt

    def crash(bot):
        raise RuntimeError('boom')
    for how in ('needs_owner', 'failed_start', 'ctrl_c', 'crash'):
        if how == 'needs_owner':
            m.app.MAGIC = None
            bot, _ = start_job(m)
            m.app.MAGIC = m.constants.MAGIC
            assert bot.exit_code == 78
        elif how == 'failed_start':
            m.fake.account_login = 87654321
            bot, _ = start_job(m)
            m.fake.account_login = F.ACCOUNT_LOGIN
            assert bot.exit_code == 1
        else:
            bot, _ = start_job(m, loop=ctrl_c if how == 'ctrl_c' else crash)
            assert bot.exit_code == (0 if how == 'ctrl_c' else 1)
        assert bot._process_locks == {}, how
        after, reached = start_job(m)
        assert reached and after.exit_code != 78, how
    assert not found(capsys.readouterr().out, 'already running')


def test_a_bot_object_that_goes_away_lets_its_lock_go(mods):
    """A bot that took the lock and never finished its job (a test, a script): the lock goes with the object, as it
    goes with the process."""
    m = mods()
    stand_in_files(m)
    a = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    b = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert a._take_process_lock() is True and list(a._process_locks) == [_lock_path(m)]
    assert a._take_process_lock() is True                           # (asked again by the same bot: it holds it)
    assert b._take_process_lock() is False and b._process_locks == {}
    del a
    gc.collect()
    assert b._take_process_lock() is True
    b._release_process_lock()
    assert b._process_locks == {}


@pytest.mark.parametrize('error', [OSError(errno.ENOLCK, 'No locks available'),
                                   OSError(errno.EBADF, 'Bad file descriptor'), RuntimeError('no such call here')])
def test_a_locking_call_that_fails_for_another_reason_is_a_warning_not_a_refusal(mods, capsys, error):
    """Anything but 'held': the bot cannot tell whether it runs twice -- and starts. Refusing would leave a bot down
    with its trades open because of a file system that has no locks."""
    m = mods()
    stand_in_files(m)

    def failing(fd):
        raise error
    m.app._lock_fd = failing
    bot, reached = start_job(m)
    assert reached and bot.exit_code != m.app.EXIT_NEEDS_OWNER
    out = capsys.readouterr().out
    assert f'⚠ Could not check whether {BRANCH} already runs on this server' in out
    assert 'Make sure this bot runs in one window only.' in out and not found(out, 'already running')
    assert any(rec[1] == 'WARN' and 'could not be used' in rec[3] for rec in bot._boot_lines)


def test_a_state_folder_that_cannot_be_made_is_a_warning_not_a_refusal(mods, capsys, tmp_path):
    m = mods()
    stand_in_files(m)
    blocked = tmp_path / 'a_file'
    blocked.write_text('x')
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    bot.state_dir = str(blocked / 'state')                          # a folder inside a file: it cannot be made
    assert bot._take_process_lock() is True and bot._process_locks == {}
    assert 'Could not check whether' in capsys.readouterr().out


def test_the_lock_file_is_named_by_the_symbol_with_safe_characters_only(mods):
    """OUTPUT_DIR/state/<SYMBOL>.lock, the symbol as symbols.json spells it (the launcher's word in another letter
    case is the same file); a word that is no symbol cannot name a file outside the state folder."""
    m = mods()
    stand_in_files(m)
    bot = m.app.MT5TradingBot(mode='live', target_symbol='xauusdm')
    assert bot._process_lock_names() == ['XAUUSDm']
    bot = m.app.MT5TradingBot(mode='live', target_symbol='../../Windows/x:y*z')
    assert bot._take_process_lock() is True
    (path,) = bot._process_locks
    assert os.path.dirname(path) == os.path.join(m.app.OUTPUT_DIR, 'state')
    assert os.path.basename(path) == '.._.._WINDOWS_X_Y_Z.lock'
    bot._release_process_lock()
    stand_in_files(m, symbols=FileNotFoundError())                  # no symbols.json: the word it was started with
    assert m.app.MT5TradingBot(mode='live', target_symbol='xauusdm')._process_lock_names() == ['XAUUSDM']
    assert m.app.MT5TradingBot(mode='live')._process_lock_names() == ['bot']


def test_a_process_for_every_active_symbol_holds_the_lock_of_each(mods):
    """`app.py live` without --symbol trades every active symbol of symbols.json: it holds the lock of each, so a
    process started for one of them is refused -- and the other way round."""
    m = mods()
    both = symbols_config(symbols=[
        {'symbol': 'XAUUSDm', 'is_active': True, 'step_up_balance': 2500, 'unit_max_limit': 10},
        {'symbol': 'BTCUSDm', 'is_active': True, 'step_up_balance': 2500, 'unit_max_limit': 10},
        {'symbol': 'EURUSDm', 'is_active': False, 'step_up_balance': 2500, 'unit_max_limit': 10}])
    stand_in_files(m, symbols=both)
    every = m.app.MT5TradingBot(mode='live')
    assert every._process_lock_names() == ['XAUUSDm', 'BTCUSDm']
    assert every._take_process_lock() is True and len(every._process_locks) == 2
    one = m.app.MT5TradingBot(mode='live', target_symbol='BTCUSDm')
    assert one._take_process_lock() is False
    every._release_process_lock()
    assert one._take_process_lock() is True
    assert every._take_process_lock() is False and every._process_locks == {}    # none kept when one is refused
    other = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert other._take_process_lock() is True                       # another symbol: another bot


def test_the_bots_of_two_folders_do_not_lock_each_other(mods, tmp_path):
    m = mods()
    stand_in_files(m)
    a = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert a._take_process_lock() is True
    m.app.OUTPUT_DIR = str(tmp_path / 'another_bot' / 'bot_output')
    b = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert b._take_process_lock() is True


# ───────────────────────────── the Windows side ─────────────────────────────

class _Msvcrt(types.ModuleType):
    """A stand-in for the msvcrt module: locking() notes how it was called and answers as Windows does -- a byte
    another handle has locked is a PermissionError (errno 13, 'locking violation')."""
    LK_NBLCK = 2

    def __init__(self):
        super().__init__('msvcrt')
        self.calls = []
        self.locked = {}                    # the file (device, inode) -> the handle that holds byte 0
        self.error = None

    def locking(self, fd, mode, nbytes):
        self.calls.append({'position': os.lseek(fd, 0, os.SEEK_CUR), 'mode': mode, 'nbytes': nbytes})
        if self.error is not None:
            raise self.error
        st = os.fstat(fd)
        key = (st.st_dev, st.st_ino)
        holder = self.locked.setdefault(key, fd)
        if holder != fd:
            try:                            # (a handle that was closed -- its number may be another file's by
                held = os.fstat(holder)     # now -- holds nothing any more)
                still = (held.st_dev, held.st_ino) == key
            except OSError:
                still = False
            if still:
                raise PermissionError(errno.EACCES, 'Permission denied')
            self.locked[key] = fd


@pytest.fixture
def windows(mods, monkeypatch):
    m = mods()
    stand_in_files(m)
    msvcrt = _Msvcrt()
    monkeypatch.setitem(sys.modules, 'msvcrt', msvcrt)
    m.app._ON_WINDOWS = True
    return m, msvcrt


def test_on_windows_the_first_byte_of_the_file_is_locked_without_waiting(windows, tmp_path):
    """msvcrt.locking locks from the file position: the bot always goes to the first byte first (two processes that
    locked different bytes would both 'hold the lock'), locks one byte, and never waits (LK_NBLCK)."""
    m, msvcrt = windows
    path = tmp_path / 'X.lock'
    path.write_bytes(b'something a stray write left in it')
    fd = os.open(path, os.O_RDWR)
    try:
        os.lseek(fd, 0, os.SEEK_END)                                # the position is anywhere
        assert m.app._lock_fd(fd) is True
        assert msvcrt.calls == [{'position': 0, 'mode': msvcrt.LK_NBLCK, 'nbytes': 1}]
        other = os.open(path, os.O_RDWR)
        try:
            assert m.app._lock_fd(other) is False                   # 'locking violation': held
        finally:
            os.close(other)
    finally:
        os.close(fd)


@pytest.mark.parametrize('error, answer', [
    (PermissionError(errno.EACCES, 'Permission denied'), False),    # held (what LK_NBLCK answers)
    (OSError(errno.EDEADLK, 'Resource deadlock avoided'), False),   # held (what the waiting modes answer)
    (OSError(errno.EBADF, 'Bad file descriptor'), None),            # the call itself failed
    (OSError(errno.EINVAL, 'Invalid argument'), None),
])
def test_on_windows_only_a_locking_violation_means_already_running(windows, tmp_path, error, answer):
    m, msvcrt = windows
    msvcrt.error = error
    fd = os.open(tmp_path / 'X.lock', os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if answer is None:
            with pytest.raises(OSError):
                m.app._lock_fd(fd)
        else:
            assert m.app._lock_fd(fd) is answer
    finally:
        os.close(fd)


def test_on_windows_a_second_process_ends_with_78_and_a_failing_call_is_a_warning(windows, capsys):
    """The whole start on the Windows side of the code."""
    m, msvcrt = windows
    second = {}

    def while_the_first_runs(first):
        capsys.readouterr()
        bot, reached = start_job(m)
        second.update(code=bot.exit_code, reached=reached, out=capsys.readouterr().out)
    first, reached = start_job(m, loop=while_the_first_runs)
    assert reached and second['code'] == 78 and not second['reached'] and second['out'].strip() == LINE
    assert all(c == {'position': 0, 'mode': msvcrt.LK_NBLCK, 'nbytes': 1} for c in msvcrt.calls)
    assert len(msvcrt.calls) == 1 + 3                               # the first; the second asked three times
    bot, reached = start_job(m)                                     # the first has ended: free again
    assert reached
    msvcrt.error = OSError(errno.EINVAL, 'Invalid argument')
    bot, reached = start_job(m)
    assert reached and 'Could not check whether' in capsys.readouterr().out


def test_the_lock_module_of_the_other_system_is_never_imported(mods):
    """fcntl does not exist on Windows and msvcrt not here: each is imported only inside its own branch."""
    import ast
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    top = {alias.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
           for alias in getattr(node, 'names', [])} | {node.module for node in tree.body
                                                       if isinstance(node, ast.ImportFrom)}
    assert 'fcntl' not in top and 'msvcrt' not in top
    assert mods().app._ON_WINDOWS is (os.name == 'nt')
