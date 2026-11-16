"""
The tests write nothing outside pytest's tmp folders (fix A of the third review round). test_partial_close.py built
bots without a state_dir, and test_live_equivalence.py replayed the live baseline without one: their files went to
OUTPUT_DIR, an absolute Windows path. On the server that is the running demo bot's own folder: a test run there
wrote the bot's state file (a fake loss of 2026-11-17 that blocks its entries for 4 to 12 hours) and could have
written a live bot's folder; on macOS it left a folder named 'C:\\Alcadeias\\demo_hedging_<branch>' in the working
folder. conftest.py now puts the OUTPUT_DIR of every bot the tests build (this branch's and the live baseline) into
the test's tmp_path, refuses any write into the real output folder, and fails the run if one was tried or such a
folder appeared in the working folder.

The final review of the third fix round: that write check patched only builtins.open, os.makedirs, os.mkdir,
os.replace and os.rename, so pathlib, io.open and os.open wrote into the real folder unrefused (on Windows nothing
else would have seen it). It is an audit hook now, which sees every file operation. And a run without python3 -B left
pytest's bytecode of conftest.py in tests_demo/__pycache__ (pytest writes it before conftest.py can turn bytecode
off): the run now fails on it, and the documented command has -B.
"""
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import conftest as C
from conftest import DEFAULTS, F, market


def test_a_bot_built_without_a_state_dir_writes_in_the_tests_tmp_path(mods, tmp_path):
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())             # no state_dir (as test_partial_close.py had)
    assert bot.state_dir is None
    bot._save_state('XAUUSDm', {'basket': None, 'last_close': {'time': 1.0, 'pnl': -5.0, 'lost': True}})
    logger = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')      # the real file log
    logger.symbols = ['XAUUSDm']
    logger._log_event('XAUUSDm', 'TEST_EVENT', 'SIGNAL', {})
    out = Path(m.app.OUTPUT_DIR)
    assert out == tmp_path / 'bot_output' and Path(m.constants.OUTPUT_DIR) == out
    assert (out / 'state' / 'XAUUSDm_state.json').is_file()
    assert (out / 'logs' / 'XAUUSDm_strategy_log.json').is_file()
    assert out != Path(DEFAULTS['OUTPUT_DIR'])
    assert not [p.name for p in Path.cwd().iterdir() if p.name.startswith('C:')]      # (the macOS leak)


def test_the_live_baseline_writes_in_the_tests_tmp_path(baseline_root, tmp_path):
    fake, clock = market(60)
    with F.bot_modules(baseline_root, fake, clock) as m:        # (test_live_equivalence.py's baseline load)
        assert Path(m.app.OUTPUT_DIR) == tmp_path / 'bot_output'
        assert Path(m.constants.OUTPUT_DIR) == tmp_path / 'bot_output'


def test_an_output_folder_the_test_chose_is_kept(mods, tmp_path):
    m = mods(OUTPUT_DIR=str(tmp_path / 'mine'))
    assert m.app.OUTPUT_DIR == str(tmp_path / 'mine')


def test_the_real_output_folder_is_recognised(tmp_path):
    real = C.REAL_OUTPUT_DIR
    assert real == DEFAULTS['OUTPUT_DIR'] and C.is_real_output(real)
    assert C.is_real_output(os.path.join(real, 'state', 'x.json'))
    assert not C.is_real_output(tmp_path) and not C.is_real_output(tmp_path / 'bot_output' / 'state')


@pytest.mark.skipif(os.name == 'nt', reason='on Windows the real folder is the running bot\'s: not even tried there')
def test_a_write_in_the_real_output_folder_is_refused(tmp_path, monkeypatch):
    """Whatever function makes the write (before the final review pathlib, io.open and os.open were not refused).
    (Off Windows the real path is a name in the working folder: here the working folder is tmp_path, so even a guard
    that failed would write only there.)"""
    monkeypatch.chdir(tmp_path)
    state = os.path.join(C.REAL_OUTPUT_DIR, 'state')
    target = os.path.join(state, 'XAUUSDm_state.json')
    (tmp_path / 'a.tmp').write_text('x')
    (tmp_path / 'tree').mkdir()
    a = str(tmp_path / 'a.tmp')
    writes = {
        'os.makedirs': lambda: os.makedirs(state, exist_ok=True),
        'os.mkdir': lambda: os.mkdir(C.REAL_OUTPUT_DIR),
        'Path.mkdir': lambda: Path(state).mkdir(parents=True, exist_ok=True),
        'open w': lambda: open(target, 'w'),
        'open a': lambda: open(target, 'a'),
        'open r+': lambda: open(target, 'r+'),
        'io.open': lambda: io.open(target, 'wb'),
        'os.open': lambda: os.open(target, os.O_WRONLY | os.O_CREAT, 0o644),
        'Path.write_text': lambda: Path(target).write_text('{"fake": "loss"}'),
        'Path.write_bytes': lambda: Path(target).write_bytes(b'x'),
        'Path.open': lambda: Path(target).open('w'),
        'Path.touch': lambda: Path(target).touch(),
        'os.replace': lambda: os.replace(a, target),
        'os.rename': lambda: os.rename(a, target),
        'Path.rename': lambda: Path(a).rename(target),
        'os.link': lambda: os.link(a, target),
        'os.symlink': lambda: os.symlink(a, target),
        'os.remove': lambda: os.remove(target),
        'Path.unlink': lambda: Path(target).unlink(),
        'os.rmdir': lambda: os.rmdir(state),
        'os.truncate': lambda: os.truncate(target, 0),
        'os.utime': lambda: os.utime(target),
        'os.chmod': lambda: os.chmod(target, 0o644),
        'shutil.copyfile': lambda: shutil.copyfile(a, target),
        'shutil.copy': lambda: shutil.copy(a, target),
        'shutil.copytree': lambda: shutil.copytree(str(tmp_path / 'tree'), state),
        'shutil.move': lambda: shutil.move(a, target),
        'shutil.rmtree': lambda: shutil.rmtree(C.REAL_OUTPUT_DIR),
    }
    n = len(C.REFUSED_WRITES)
    for name, write in writes.items():
        before = len(C.REFUSED_WRITES)
        with pytest.raises(PermissionError, match='refused'):
            write()
        assert len(C.REFUSED_WRITES) > before, name
    assert sorted(p.name for p in tmp_path.iterdir()) == ['a.tmp', 'tree']        # nothing was written
    del C.REFUSED_WRITES[n:]                  # (tried on purpose: not writes of this run to report at its end)


def test_writes_elsewhere_and_reads_of_the_real_folder_are_not_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    n = len(C.REFUSED_WRITES)
    Path('out').mkdir()
    Path('out', 'x.json').write_text('{}')
    os.replace(os.path.join('out', 'x.json'), os.path.join('out', 'y.json'))
    shutil.rmtree('out')
    with pytest.raises(FileNotFoundError):
        open(os.path.join(C.REAL_OUTPUT_DIR, 'state', 'XAUUSDm_state.json'))      # a read is not a write
    assert len(C.REFUSED_WRITES) == n


def test_stray_bytecode_is_found_only_when_python_may_write_it(tmp_path):
    cache = tmp_path / '__pycache__'
    assert C.stray_bytecode(False, None, tmp_path) == []
    cache.mkdir()
    (cache / 'conftest.cpython-310-pytest-8.3.5.pyc').write_bytes(b'')
    assert C.stray_bytecode(False, None, tmp_path) == [str(cache / 'conftest.cpython-310-pytest-8.3.5.pyc')]
    assert C.stray_bytecode(True, None, tmp_path) == []                 # -B / PYTHONDONTWRITEBYTECODE
    assert C.stray_bytecode(False, str(tmp_path / 'prefix'), tmp_path) == []      # PYTHONPYCACHEPREFIX


def test_a_run_without_python_B_fails_on_the_bytecode_it_leaves(tmp_path):
    """A pytest run on a copy of this conftest.py (with one empty test) leaves pytest's bytecode of conftest.py in the
    copy's tests_demo/__pycache__ without -B, and then fails; with -B it writes none and passes. (Before the final
    review: both runs passed, the first one leaving the bytecode behind.)"""
    branch = tmp_path / 'branch'
    tests = branch / 'tests_demo'
    tests.mkdir(parents=True)
    for name in ('conftest.py', 'fake_mt5.py'):
        shutil.copy(C.HERE / name, tests / name)
    shutil.copy(C.ROOT / 'constants.py', branch / 'constants.py')
    (tests / 'test_one.py').write_text('def test_one():\n    pass\n')
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
    (tmp_path / 'cwd').mkdir()

    def run(*flags, k=0):
        return subprocess.run([sys.executable, *flags, '-m', 'pytest', str(tests / 'test_one.py'), '-q',
                               '-p', 'no:cacheprovider', f'--basetemp={tmp_path / f"bt{k}"}'],
                              cwd=tmp_path / 'cwd', env=env, capture_output=True, text=True, timeout=300)
    plain = run(k=1)
    assert plain.returncode != 0 and 'bytecode written into the branch' in plain.stdout, plain.stdout[-2000:]
    assert list((tests / '__pycache__').glob('conftest.*.pyc'))
    shutil.rmtree(tests / '__pycache__')
    with_b = run('-B', k=2)
    assert with_b.returncode == 0, with_b.stdout[-2000:]
    assert not (tests / '__pycache__').exists() and not list((tmp_path / 'cwd').iterdir())
