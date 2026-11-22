"""
The H1 trend and the volatility unit are read on the last CLOSED bar, as the backtester does
(kernels.py: SG[off + K - 1] and VOL[off + K - 1]); the forming bar is excluded.
"""
import numpy as np
import pandas as pd
import pytest

from conftest import crafted_market, run_bot


def _kernel_vol_array(C, n):
    """backtesting/engine/kernels.py vol_array, transcribed."""
    out = np.zeros(C.shape[0])
    v = abs(C[1] - C[0])
    out[1] = v
    for k in range(2, C.shape[0]):
        v += (abs(C[k] - C[k - 1]) - v) / n
        out[k] = v
    out[:min(int(n), C.shape[0])] = 0.0
    return out


# ───────────────────────────── the volatility unit ─────────────────────────────

def test_vol_unit_is_the_backtester_ewma_of_absolute_close_changes(mods):
    I = mods().indicator.Indicator
    rng = np.random.default_rng(5)
    c = 2000 + np.cumsum(rng.normal(0, 3, 499))
    v = I.vol_unit(c, 24)
    assert v == _kernel_vol_array(c, 24)[-1]                          # the same recursion, bit for bit
    ewm = pd.Series(c).diff().abs().iloc[1:].ewm(alpha=1 / 24, adjust=False).mean().iloc[-1]
    assert v == pytest.approx(ewm, rel=1e-12)
    assert v != pytest.approx(np.abs(np.diff(c[-25:])).mean(), rel=1e-2)   # not a 24-bar simple mean
    # 499 closed bars give the value of the whole history (the kernel's warm-up) to ~1e-9
    longer = np.concatenate([c[0] - np.cumsum(rng.normal(0, 3, 5000))[::-1], c])
    assert I.vol_unit(longer, 24) == pytest.approx(v, rel=1e-8)


def test_vol_unit_is_unknown_until_vol_len_changes_were_averaged(mods):
    I = mods().indicator.Indicator
    c = np.arange(40, dtype=float)
    assert I.vol_unit(c[:24], 24) == 0.0        # 23 bar-to-bar changes: unknown
    assert I.vol_unit(c[:25], 24) == 1.0        # 24: known
    assert I.vol_unit(np.full(40, 5.0), 24) == 0.0   # never moved: 0, and 0 opens nothing


def test_the_bot_measures_the_unit_on_the_closed_h1_bars(tmp_path):
    rng = np.random.default_rng(8)
    h1 = 2000 + np.cumsum(rng.normal(0, 4, 600))
    forming = h1[-1] + 30.0                          # a big move inside the forming hour
    fake, clock = crafted_market(h1, [forming] * 20)
    run = run_bot(fake, clock, overrides={'VOL_TF': 'H1', 'VOL_LEN': 24}, state_dir=tmp_path)
    I = run.mods.indicator.Indicator
    fresh = [p for p in run.polls if p['fresh']]
    assert fresh and not run.errors
    closed = h1[-499:]                               # 500 bars fetched = 499 closed + the forming one
    want = I.vol_unit(closed, 24)
    assert all(p['vol'] == want for p in fresh)
    assert want != pytest.approx(I.vol_unit(np.r_[closed, forming], 24), rel=1e-3)   # the forming bar would move it


# ───────────────────────────── the H1 trend ─────────────────────────────

def _decline_then_jump():
    """H1 closes declining 0.05 per bar (MACD signal line about -0.35), then a forming bar 40 above:
    the forming bar's signal line is positive, the last closed bar's is negative."""
    return 2000.0 - 0.05 * np.arange(600), 40.0


def test_the_trend_is_the_signal_line_of_the_last_closed_bar_not_the_forming_one(tmp_path):
    h1, jump = _decline_then_jump()
    forming = h1[-1] + jump
    fake, clock = crafted_market(h1, [forming] * 20)
    run = run_bot(fake, clock, overrides={'TREND_TF': 'H1'}, state_dir=tmp_path)
    assert not run.errors
    macd = run.mods.indicator.Indicator().calculate_macd(pd.Series(np.r_[h1[-499:], forming]))
    assert macd['signal'].iloc[-2] < 0 < macd['signal'].iloc[-1]       # the two bars disagree here
    fresh = [p for p in run.polls if p['fresh']]
    assert fresh and all(p['trend'] == -1 for p in fresh)


def test_an_up_trend_reads_plus_one(tmp_path):
    h1 = 2000.0 + 0.05 * np.arange(600)
    fake, clock = crafted_market(h1, [h1[-1]] * 10)
    run = run_bot(fake, clock, overrides={'TREND_TF': 'H1'}, state_dir=tmp_path)
    assert all(p['trend'] == 1 for p in run.polls if p['fresh'])


def test_no_trend_filter_by_default(tmp_path):
    h1, jump = _decline_then_jump()
    fake, clock = crafted_market(h1, [h1[-1] + jump] * 10)
    run = run_bot(fake, clock, state_dir=tmp_path)
    assert all(p['trend'] is None for p in run.polls if p['fresh'])


def test_trend_gate_blocks_the_other_side_and_a_zero_trend_blocks_both(mods):
    app = mods(TREND_TF='H1').app
    assert app.entry_block_reason(1, 1, None, 1.0) is None
    assert app.entry_block_reason(-1, -1, None, 1.0) is None
    assert app.entry_block_reason(1, -1, None, 1.0) == 'trend'
    assert app.entry_block_reason(-1, 1, None, 1.0) == 'trend'
    assert app.entry_block_reason(1, 0, None, 1.0) == 'trend'        # signal exactly 0 or NaN
    assert app.entry_block_reason(-1, 0, None, 1.0) == 'trend'


def test_volatility_gate_blocks_an_entry_while_the_unit_is_unknown(mods):
    app = mods(VOL_TF='H1', TARGET_VOL=8.0, STOP_VOL=8.0, TARGET_USD_PER_UNIT=None).app
    assert app.entry_block_reason(1, 0, 0.0, 1.0) == 'volatility unknown'
    assert app.entry_block_reason(1, 0, None, 1.0) == 'volatility unknown'
    assert app.entry_block_reason(1, 0, float('nan'), 1.0) == 'volatility unknown'
    assert app.entry_block_reason(1, 0, 2.5, None) == 'contract size unknown'
    assert app.entry_block_reason(1, 0, 2.5, 1.0) is None
