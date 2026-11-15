"""
constants.py: the live defaults, the four commented design examples, the design checks, and the dashboard's
imports.
"""
import importlib.util
import re

import pytest

from conftest import DEFAULTS, DEMO_BRANCH, F, MAGIC, ROOT, market


def _constants_with(block, tmp_path):
    """constants.py with `block` appended at the end (how a demo branch sets its design)."""
    src = (ROOT / 'constants.py').read_text() + '\n' + block + '\n'
    path = tmp_path / 'constants_design.py'
    path.write_text(src)
    spec = importlib.util.spec_from_file_location('constants_design', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _example_blocks():
    text = (ROOT / 'constants.py').read_text()
    blocks = {}
    for name, body in re.findall(r"# ── (XAU V3-lite|XAU Top 2|XAU Top 1|BTC Top 2) ──\n((?:# [A-Z_].*\n)+)", text):
        blocks[name] = '\n'.join(line[2:] for line in body.splitlines())
    return blocks


def test_levers_default_to_the_live_bot():
    """The default section of constants.py (above the design examples; a design block goes after them)."""
    import types
    c = types.SimpleNamespace(**DEFAULTS)
    assert c.DESIGN_NAME == 'live' and c.STRATEGY == 'basket'
    assert c.FORCE_CLOSE_ENABLED is True and c.TREND_TF is None and c.VOL_TF is None and c.VOL_LEN == 24
    assert c.TARGET_USD_PER_UNIT == 'live' and c.STOP_LOSS_USD_PER_UNIT is None
    assert (c.TARGET_VOL, c.STOP_VOL, c.VOL_CAP_USD_PER_UNIT, c.LOSS_COOLDOWN_S) == (0.0, 0.0, 0.0, 0)
    assert c.MAX_ADDS == 99 and c.LADDER_TRIGGER == 'rsi_level' and c.LADDER_TFS == ['M1', 'M5', 'M15', 'H1', 'H4']
    assert c.LADDER_GAP_VOL == 0.0 and c.LADDER_MULTIPLIERS is None
    assert c.OPEN_SCORE_WEIGHTS == {'H1': 1, 'M15': 1} and c.FORCE_CLOSE_SCORE_WEIGHTS == {'M15': 1}
    assert c.ENTRY_S == 2 and c.ENTRY_AGREE_S == 2 and c.LADDER_S == 2 and c.FORCE_CLOSE_S == 1
    assert c.REENTRY_COOLDOWN_SECONDS == 300 and c.STRATEGY_HEDGE == 1
    assert c.ORDER_COMMENT is None and c.VIRTUAL_START_BALANCE == 2000.0 and c.VIRTUAL_START_DATE == '2026-11-16'
    assert isinstance(MAGIC, int) and MAGIC > 0 and DEMO_BRANCH.startswith('demo_')


def test_the_branch_constants_as_written_run(mods):
    """constants.py as it is on this branch, design block (if any) included, is a design the bot accepts."""
    m = mods(_as_written=True)
    assert m.app.design_problems() == [], m.app.design_problems()
    assert m.constants.MAGIC == MAGIC and m.constants.DEMO_BRANCH == DEMO_BRANCH


def test_the_four_example_blocks_are_the_designs(tmp_path):
    blocks = _example_blocks()
    assert set(blocks) == {'XAU V3-lite', 'XAU Top 2', 'XAU Top 1', 'BTC Top 2'}
    common = dict(OPEN_SCORE_WEIGHTS={'H1': 1}, FORCE_CLOSE_ENABLED=False, TREND_TF='H1', VOL_TF='H1', VOL_LEN=24,
                  TARGET_USD_PER_UNIT=None, STOP_LOSS_USD_PER_UNIT=None, FORCE_CLOSE_SCORE_WEIGHTS={'M15': 1})
    want = {
        'XAU V3-lite': dict(ENTRY_AGREE_S=2, TARGET_VOL=8, STOP_VOL=8, VOL_CAP_USD_PER_UNIT=0, LOSS_COOLDOWN_S=43200, MAX_ADDS=0),
        'XAU Top 2': dict(ENTRY_AGREE_S=0, TARGET_VOL=8, STOP_VOL=4, VOL_CAP_USD_PER_UNIT=12, LOSS_COOLDOWN_S=43200, MAX_ADDS=0),
        'XAU Top 1': dict(ENTRY_AGREE_S=0, TARGET_VOL=10, STOP_VOL=8, VOL_CAP_USD_PER_UNIT=0, LOSS_COOLDOWN_S=14400, MAX_ADDS=1,
                          LADDER_TRIGGER='macd_turn', LADDER_GAP_VOL=1, LADDER_MULTIPLIERS=[1, 1, 1, 1]),
        'BTC Top 2': dict(ENTRY_AGREE_S=0, TARGET_VOL=10, STOP_VOL=8, VOL_CAP_USD_PER_UNIT=12, LOSS_COOLDOWN_S=14400, MAX_ADDS=0),
    }
    for name, block in blocks.items():
        c = _constants_with(block, tmp_path)
        for k, v in dict(common, **want[name]).items():
            assert getattr(c, k) == v, (name, k)
        if name == 'XAU Top 1':
            assert c.LADDER_TFS[0] == 'M5'


@pytest.mark.parametrize('name', ['XAU V3-lite', 'XAU Top 2', 'XAU Top 1', 'BTC Top 2'])
def test_each_example_design_is_accepted_and_reads_the_votes_it_needs(mods, tmp_path, name):
    c = _constants_with(_example_blocks()[name], tmp_path)
    names = ('OPEN_SCORE_WEIGHTS', 'ENTRY_AGREE_S', 'FORCE_CLOSE_ENABLED', 'TREND_TF', 'VOL_TF', 'VOL_LEN',
             'TARGET_USD_PER_UNIT', 'STOP_LOSS_USD_PER_UNIT', 'TARGET_VOL', 'STOP_VOL', 'VOL_CAP_USD_PER_UNIT',
             'LOSS_COOLDOWN_S', 'MAX_ADDS', 'LADDER_TRIGGER', 'LADDER_TFS', 'LADDER_GAP_VOL', 'LADDER_MULTIPLIERS',
             'DESIGN_NAME')
    m = mods(**{k: getattr(c, k) for k in names})
    assert m.app.design_problems() == []
    tfs = m.strategy.Strategy.slope_timeframes()
    assert 'TIMEFRAME_H1' in tfs and 'TIMEFRAME_M15' in tfs          # M15 still read: the entry agreement
    assert ('TIMEFRAME_M5' in tfs) == (name == 'XAU Top 1')
    assert m.strategy.Strategy.ladder_tiers() == (['M5'] if name == 'XAU Top 1' else [])
    assert name.split()[0] in ('XAU', 'BTC') and m.app.design_summary()


@pytest.mark.parametrize('ov, needle', [
    ({'STRATEGY': 'turtle'}, 'Turtle'),
    ({'STRATEGY': 'grid'}, 'STRATEGY'),
    ({'TARGET_VOL': 8.0}, 'needs VOL_TF'),
    ({'VOL_CAP_USD_PER_UNIT': 12.0}, 'needs VOL_TF'),
    ({'VOL_TF': 'H7'}, 'VOL_TF'),
    ({'TREND_TF': 'X1'}, 'TREND_TF'),
    ({'LADDER_TRIGGER': 'moon_phase'}, 'LADDER_TRIGGER'),
    ({'LADDER_MULTIPLIERS': [2, 1]}, 'LADDER_MULTIPLIERS[0]'),
    ({'MAX_ADDS': -1}, 'MAX_ADDS'),
    ({'TARGET_USD_PER_UNIT': 'half'}, 'TARGET_USD_PER_UNIT'),
    ({'VIRTUAL_START_DATE': 'soon'}, 'VIRTUAL_START_DATE'),
    ({'VOL_LEN': 1}, 'VOL_LEN'),
])
def test_designs_the_bot_cannot_run_are_refused(mods, tmp_path, ov, needle):
    m = mods(**ov)
    problems = m.app.design_problems()
    assert any(needle in p for p in problems), problems
    with pytest.raises(ValueError, match='refused'):
        F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), state_dir=tmp_path).process_symbol('XAUUSDm')


def test_a_design_with_a_stop_and_a_ladder_needs_an_add_gap(mods, tmp_path):
    """A stop with a ladder that can add in favour of the basket (LADDER_GAP_VOL = 0): an add far in favour carries a
    broker-side backstop inside the basket's stop -- the broker would close it while the bot's own stop has not fired
    (finding 5 of the re-review). Refused; with a gap every add is against the basket and its backstop lies beyond
    the stop. The designs the branches ship all pass (test_each_example_design_is_accepted_...)."""
    vol = dict(VOL_TF='H1', TARGET_USD_PER_UNIT=None, TARGET_VOL=10.0, STOP_VOL=8.0)
    for ov in (dict(vol, MAX_ADDS=1, LADDER_TRIGGER='macd_turn'),       # XAU Top 1 without its gap
               dict(vol),                                               # a stop with the live RSI ladder
               {'STOP_LOSS_USD_PER_UNIT': 4.0}):                        # a $ stop with the live ladder
        m = mods(**ov)
        problems = m.app.design_problems()
        assert any('LADDER_GAP_VOL > 0' in p for p in problems), (ov, problems)
        with pytest.raises(ValueError, match='LADDER_GAP_VOL'):
            F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), state_dir=tmp_path).process_symbol('XAUUSDm')
    for ov in (dict(vol, MAX_ADDS=1, LADDER_TRIGGER='macd_turn', LADDER_GAP_VOL=1.0),     # XAU Top 1
               dict(vol, MAX_ADDS=0),                                                    # no ladder
               {}):                                                                      # no stop: the live bot
        assert mods(**ov).app.design_problems() == [], ov


def test_a_refused_design_stops_the_job_before_it_connects(mods):
    m = mods(STRATEGY='turtle')
    called = []
    m.fake.initialize = lambda *a, **k: called.append('initialize') or True
    m.fake.login = lambda *a, **k: called.append('login') or True
    bot = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')
    assert bot.execute_job() is False
    assert called == []


def test_dashboard_still_imports_and_draws_the_new_analysis(mods, tmp_path):
    pytest.importorskip('dash')
    import sys
    sys.path.insert(0, str(ROOT))
    try:
        sys.modules.pop('dashboard', None)
        m = mods()                                    # constants etc. from this branch
        import dashboard
        analysis = {'slopes': {'H1': {'rsi': {'sign': 1}, 'macd': {'sign': 1}},
                               'M5': {'rsi': {'sign': 0}, 'macd': {'sign': -1}}},
                    'entry_direction': 'WAIT', 'entry_allowed': False, 'exit_reason': 'stop_loss',
                    'open_score': 2, 'fc_score': -1, 'design': 'xau_top1', 'trend': -1, 'force_close_enabled': False,
                    'basket_levels': {'units': 1, 'target_usd': 94.0, 'stop_usd': 75.2, 'gap_px': 9.4,
                                      'vol_unit': 9.4, 'ladder_armed': True},
                    'pause_left_s': 3600.0, 'loss_pause_s': 14400, 'last_close_lost': True,
                    'virtual_balance': 2034.5}
        panel = dashboard.build_slope_panel('XAUUSDm', analysis)
        text = str(panel)
        for bit in ('design xau_top1', 'trend ▼ down', 'stop $75.20 · target $94.00 · add armed',
                    'virtual balance $2,034.50', 'entry pause 1.0 h left (after a loss)',
                    'FORCE-CLOSE OFF · ENTRY AGREEMENT ONLY'):
            assert bit in text, bit
        assert dashboard.build_slope_panel('XAUUSDm', {}) is not None          # an old / empty payload
    finally:
        sys.modules.pop('dashboard', None)
        sys.path.remove(str(ROOT))
