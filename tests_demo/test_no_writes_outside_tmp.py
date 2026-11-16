"""
The tests write nothing outside pytest's tmp folders (fix A of the third review round). test_partial_close.py built
bots without a state_dir, and test_live_equivalence.py replayed the live baseline without one: their files went to
OUTPUT_DIR, an absolute Windows path. On the server that is the running demo bot's own folder: a test run there
wrote the bot's state file (a fake loss of 2026-11-17 that blocks its entries for 4 to 12 hours) and could have
written a live bot's folder; on macOS it left a folder named 'C:\\Alcadeias\\demo_hedging_<branch>' in the working
folder. conftest.py now puts the OUTPUT_DIR of every bot the tests build (this branch's and the live baseline) into
the test's tmp_path, refuses any write into the real output folder, and fails the run if one was tried or such a
folder appeared in the working folder.
"""
import os
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
    """(Off Windows the real path is a name in the working folder: here the working folder is tmp_path, so even a
    guard that failed would write only there.)"""
    monkeypatch.chdir(tmp_path)
    target = os.path.join(C.REAL_OUTPUT_DIR, 'state', 'XAUUSDm_state.json')
    n = len(C.REFUSED_WRITES)
    with pytest.raises(PermissionError):
        os.makedirs(os.path.dirname(target), exist_ok=True)
    with pytest.raises(PermissionError):
        open(target, 'w')
    with pytest.raises(PermissionError):
        os.replace(str(tmp_path / 'a.tmp'), target)
    assert len(C.REFUSED_WRITES) == n + 3 and not list(tmp_path.iterdir())
    del C.REFUSED_WRITES[n:]                  # (tried on purpose: not a write of this run to report at its end)
