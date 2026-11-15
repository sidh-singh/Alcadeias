"""
The pause after a losing basket (LOSS_COOLDOWN_S): after a basket whose realised P/L (deal history) is below
zero the next entry waits LOSS_COOLDOWN_S instead of REENTRY_COOLDOWN_SECONDS, counted from the close
decision; after a winner the ordinary pause. Only the last basket counts.
"""
import pytest

from conftest import F, MAGIC, SCALED, baskets, market, run_bot


@pytest.mark.slow
def test_a_losing_basket_is_followed_by_the_longer_pause(tmp_path):
    fake, clock = market(5400, seed=21)
    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path)
    assert not run.errors, run.errors[:3]
    b = baskets(fake, magic=MAGIC)
    assert len(b) >= 6
    lost = [x['pnl'] < 0 for x in b[:-1]]
    waits = [b[i + 1]['t_open'] - b[i]['t_close'] for i in range(len(b) - 1)]
    assert any(lost) and not all(lost)
    for was_lost, wait in zip(lost, waits):
        assert wait >= (240 if was_lost else 30) - 1e-6
    assert any(w < 240 for was_lost, w in zip(lost, waits) if not was_lost)    # winners do not wait the long pause
    # the bot logged the realised result of each close
    closes = [e for e in run.events if e['event'] in ('CLOSE_BUY', 'CLOSE_SELL')]
    assert closes and all(e['details']['realised_pnl'] is not None for e in closes)
    assert [e['details']['lost'] for e in closes][:len(lost)] == lost


def _bot(mods, **ov):
    fake, clock = market(600)
    m = mods(fake=fake, clock=clock, **ov)
    return m, fake, clock, F.make_bot(m, fake, 'XAUUSDm', F.Run())


def test_lost_is_the_realised_result_not_the_one_seen_at_the_decision(mods):
    m, fake, clock, bot = _bot(mods, LOSS_COOLDOWN_S=3600)
    now = clock.time()
    # the basket was +0.40 when the bot decided to close it, but filled at -0.20 (slippage)
    pid = fake.add_position(0, 0.01, 2000.0, now - 600, magic=MAGIC)
    fake.positions.clear()
    fake.add_deal(pid, 1, 1, 0.01, 1999.8, -0.20, now - 0.1, magic=MAGIC)
    state = {'basket': None, 'last_close': {'time': now, 'pnl': 0.40, 'lost': False, 'resolved': False,
                                            'source': 'decision', 'ids': [pid], 'open_time': now - 600, 'attempts': 0}}
    assert bot._resolve_last_close(state, now)
    lc = state['last_close']
    assert lc['resolved'] and lc['source'] == 'history' and lc['pnl'] == -0.2 and lc['lost'] is True


def test_without_history_the_decision_time_result_stands(mods):
    m, fake, clock, bot = _bot(mods, LOSS_COOLDOWN_S=3600)
    fake.history_none = True
    now = clock.time()
    state = {'basket': None, 'last_close': {'time': now, 'pnl': -1.5, 'lost': True, 'resolved': False,
                                            'source': 'decision', 'ids': [123], 'open_time': now - 60, 'attempts': 0}}
    for _ in range(m.app._RESOLVE_ATTEMPTS - 1):
        assert not bot._resolve_last_close(state, now)
    assert bot._resolve_last_close(state, now)            # gives up: the decision-time loss stands
    assert state['last_close']['resolved'] and state['last_close']['lost'] is True


def test_the_pause_is_rebuilt_from_the_deal_history(mods):
    m, fake, clock, bot = _bot(mods, LOSS_COOLDOWN_S=43200)
    now = clock.time()
    a = fake.add_position(1, 0.01, 2000.0, now - 7200, magic=MAGIC)
    b = fake.add_position(1, 0.01, 2010.0, now - 7000, magic=MAGIC)
    fake.positions.clear()
    fake.add_deal(a, 0, 1, 0.01, 2020.0, -20.0, now - 3600, magic=MAGIC)
    fake.add_deal(b, 0, 1, 0.01, 2020.0, -10.0, now - 3600, magic=MAGIC)
    other = fake.add_position(0, 0.01, 2000.0, now - 100, magic=777)     # another bot's trade, closed later
    fake.positions.clear()
    fake.add_deal(other, 1, 1, 0.01, 2050.0, 50.0, now - 50, magic=777)
    lc = bot._last_close_from_history(now)
    assert lc['time'] == pytest.approx(now - 3600) and lc['pnl'] == -30.0 and lc['lost'] is True
    assert sorted(lc['ids']) == sorted([a, b])
