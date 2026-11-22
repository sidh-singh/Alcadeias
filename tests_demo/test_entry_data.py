"""
No fresh entry on data the poll does not have (findings 6 and 7 of the demo review).

Votes unknown (finding 6): a timeframe whose rates fetch failed left no votes, which the scores read as 0, so
with ENTRY_AGREE_S = 0 a failed M15 fetch passed the "M15 not against" gate. Now an entry is blocked ('votes
unknown') while any timeframe of OPEN_SCORE_WEIGHTS, FORCE_CLOSE_SCORE_WEIGHTS, TREND_TF or VOL_TF has no data
this poll; exits and stops keep working; a ladder tier without data neither adds nor arms.

A full history (finding 7): the volatility unit and the trend accepted a short history (the EWMA unit off by up
to 12% on BTC with 100 H1 bars). Now an entry needs at least 300 closed bars of VOL_TF and TREND_TF ('volatility
unknown' otherwise), and so does the unit of a basket rebuilt after a restart (its levels wait otherwise).
"""
import numpy as np
import pytest

from conftest import NO_LADDER, SCALED, F, MAGIC, START, baskets, crafted_market, market, run_bot

# the agreement section on its own timeframe (M2), the backtester's ENTRY_AGREE_S = 0
AGREE_M2 = dict(NO_LADDER, FORCE_CLOSE_SCORE_WEIGHTS={'M2': 1}, SLOPE_TIMEFRAMES=['TIMEFRAME_M1', 'TIMEFRAME_M2'])
# the scaled ladder (one macd_turn add, room for it) with its tier on a timeframe no entry reads
LADDER_M2 = dict(SCALED, STOP_VOL=6.0, TARGET_VOL=3.0, LADDER_TFS=['M2', 'M5', 'M15', 'H1', 'H4'])


def test_an_entry_needs_every_timeframe_it_reads(mods):
    app = mods(OPEN_SCORE_WEIGHTS={'H1': 1}, FORCE_CLOSE_SCORE_WEIGHTS={'M15': 1}, ENTRY_AGREE_S=0,
               TREND_TF='H1', VOL_TF='H1', TARGET_VOL=8.0, STOP_VOL=8.0, TARGET_USD_PER_UNIT=None).app
    assert app.entry_timeframes() == ['H1', 'M15']
    assert app.entry_block_reason(1, 1, 9.4, 1.0) is None
    assert app.entry_block_reason(1, 1, 9.4, 1.0, no_data=['M15']) == 'votes unknown'
    assert app.entry_block_reason(-1, -1, 9.4, 1.0, no_data=['TIMEFRAME_H1']) == 'votes unknown'
    assert app.entry_block_reason(1, 1, 9.4, 1.0, no_data=['M1', 'H6']) is None     # not read by the entry
    live = mods().app                                      # the live sections H1 + M15, M15
    assert live.entry_timeframes() == ['H1', 'M15'] and live.entry_block_reason(1, 0, None, 1.0, ['M15']) == 'votes unknown'


def _entries(fake):
    return [d for d in fake.deals if d.entry == 0 and d.magic == MAGIC]


@pytest.mark.slow
def test_no_entry_while_the_agreement_timeframe_has_no_data(tmp_path):
    fake0, clock0 = market(1200, seed=5)
    run_bot(fake0, clock0, overrides=AGREE_M2, state_dir=tmp_path / 'ref')
    assert len(_entries(fake0)) >= 3                       # with its M2 votes the design trades
    fake, clock = market(1200, seed=5)
    fake.fail_rates('M2', 0, 1e12)                         # the M2 fetch fails on every poll
    run = run_bot(fake, clock, overrides=AGREE_M2, state_dir=tmp_path / 'run')
    assert not _entries(fake)                              # (before the fix: entries with the M2 score read as 0)
    blocked = [e for e in run.events if e['event'] in ('BUY_SIGNAL', 'SELL_SIGNAL')]
    assert blocked and all('votes unknown' in e['details']['note'] and e['details']['no_data'] == ['M2']
                           for e in blocked)
    assert all(p['no_data'] == ['M2'] for p in run.polls if p['fresh'])


@pytest.mark.slow
def test_exits_and_stops_keep_working_without_the_votes(tmp_path):
    """The M2 fetch starts failing a second after the first entry: that basket is still closed by the bot at its
    stop or target, and no entry follows while the data is missing."""
    fake0, clock0 = market(1200, seed=5)
    run_bot(fake0, clock0, overrides=AGREE_M2, state_dir=tmp_path / 'ref')
    first = baskets(fake0, magic=MAGIC)[0]
    fake, clock = market(1200, seed=5)
    fake.fail_rates('M2', first['t_open'] + 1, 1e12)
    run = run_bot(fake, clock, overrides=AGREE_M2, state_dir=tmp_path / 'run')
    closes = [e for e in run.events if e['event'] in ('CLOSE_BUY', 'CLOSE_SELL')]
    assert len(closes) == 1 and closes[0]['details']['reason'] in ('stop_loss', 'target')
    assert len(_entries(fake)) == 1 and not fake.positions
    assert baskets(fake, magic=MAGIC)[0]['t_close'] == pytest.approx(first['t_close'])     # as without the failure


@pytest.mark.slow
def test_a_ladder_tier_without_data_neither_arms_nor_adds(tmp_path):
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=LADDER_M2, state_dir=tmp_path / 'ref')
    assert any(len(b['legs']) == 2 for b in baskets(fake0, magic=MAGIC))       # with its M2 votes it adds
    assert any(p['ladder_armed'] for p in ref.polls)
    fake, clock = market(1800, seed=21)
    fake.fail_rates('M2', 0, 1e12)
    run = run_bot(fake, clock, overrides=LADDER_M2, state_dir=tmp_path / 'run')
    assert len(_entries(fake)) >= 2                                            # entries go on (M2 is not theirs)
    assert not [e for e in run.events if e['event'] in ('BUY_MORE_EXECUTED', 'SELL_MORE_EXECUTED')]
    assert all(len(b['legs']) == 1 for b in baskets(fake, magic=MAGIC)) and len(fake.positions) <= 1
    assert not any(p['ladder_armed'] for p in run.polls)                       # a missing vote never armed it


# ───────────────────────────── a full history (finding 7) ─────────────────────────────

def _h1(n, seed=8):
    return 2000 + np.cumsum(np.random.default_rng(seed).normal(0, 4, n))


def test_a_short_history_blocks_the_entry_as_volatility_unknown(mods):
    app = mods(TREND_TF='H1', VOL_TF='H1', TARGET_VOL=8.0, STOP_VOL=8.0, TARGET_USD_PER_UNIT=None).app
    assert app._MIN_CLOSED_BARS == 300
    assert app.entry_block_reason(1, 1, 9.4, 1.0) is None
    assert app.entry_block_reason(1, 1, 9.4, 1.0, short_history=['H1']) == 'volatility unknown'
    assert app.entry_block_reason(1, -1, 9.4, 1.0, short_history=['H1']) == 'trend'        # the order of the gates
    assert mods(VOL_TF='H1', RSI_CANDLE_COUNT=300).app.design_problems()                     # 299 closed bars: never


@pytest.mark.parametrize('closed, known', [(299, False), (300, True)])
def test_the_unit_needs_300_closed_bars(tmp_path, closed, known):
    fake, clock = crafted_market(_h1(closed), [2000.0] * 15)       # `closed` H1 bars, then the forming one
    run = run_bot(fake, clock, overrides={'VOL_TF': 'H1', 'VOL_LEN': 24}, state_dir=tmp_path)
    fresh = [p for p in run.polls if p['fresh']]
    assert fresh and not run.errors
    I = run.mods.indicator.Indicator
    for p in fresh:
        if known:
            assert p['vol'] == I.vol_unit(_h1(closed), 24) and p['short_history'] == []
        else:
            assert p['vol'] is None and p['short_history'] == ['H1']


def test_a_short_trend_history_is_reported(tmp_path):
    fake, clock = crafted_market(_h1(600), [2000.0] * 15)          # 600 H1 bars = 150 H4 bars
    run = run_bot(fake, clock, overrides={'TREND_TF': 'H4', 'VOL_TF': 'H1'}, state_dir=tmp_path)
    fresh = [p for p in run.polls if p['fresh']]
    assert fresh and all(p['short_history'] == ['H4'] and p['vol'] is not None for p in fresh)


@pytest.mark.parametrize('closed, known', [(250, False), (400, True)])
def test_a_rebuilt_basket_needs_a_full_history_at_its_open(mods, closed, known):
    fake, clock = crafted_market(_h1(closed), [2000.0] * 15)
    m = mods(fake=fake, clock=clock, VOL_TF='H1', TARGET_VOL=8.0, STOP_VOL=8.0, TARGET_USD_PER_UNIT=None)
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run())
    t_open = START - 1800                                          # the last closed bar's hour
    v = bot._vol_unit_at('XAUUSDm', t_open)
    assert (v is not None) == known
    fake.add_position(0, 0.01, 2000.0, t_open, magic=MAGIC)
    plist = m.mt5_helper.MT5PositionHelper(fake).get_buy_positions('XAUUSDm')['positions']
    b = bot._rebuild_basket('XAUUSDm', 'BUY', plist, 0.01, 1.0, clock.time())
    assert b['levels_pending'] == (not known) and (b['stop_usd_per_unit'] is None) == (not known)
