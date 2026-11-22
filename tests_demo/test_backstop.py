"""
A broker-side backstop (finding 3 of the demo review: no broker stop at all, so a position was unprotected while
the bot or the terminal was down). A design with a stop sends every fill (entry, add) with a request sl
BACKSTOP_FACTOR (2) basket stop distances (STOP_VOL x unit, capped) beyond it and no tp; the bot's own stop is
nearer, so in normal operation it always closes first and nothing the backtest does changes. A design without a
stop (the live levers) keeps the live request. A position the backstop closes is booked by the existing "closed
outside the bot" path: its realised loss and its closing time from the deal history, then the loss pause.
"""
import pytest

from conftest import NO_LADDER, SCALED, F, MAGIC, baskets, deals_of, market, recording_states, run_bot
from conftest import differs

V3LITE = dict(VOL_TF='H1', VOL_LEN=24, TARGET_USD_PER_UNIT=None, STOP_LOSS_USD_PER_UNIT=None, TARGET_VOL=8.0,
              STOP_VOL=8.0, VOL_CAP_USD_PER_UNIT=0.0)
BTC_TOP2 = dict(V3LITE, TARGET_VOL=10.0, VOL_CAP_USD_PER_UNIT=12.0)


def test_the_backstop_distance_is_twice_the_basket_stop(mods):
    app = mods(**V3LITE).app
    assert app.design_has_stop() and app.BACKSTOP_FACTOR == 2.0
    lv = app.basket_levels(9.4, 1.0)                         # gold: a stop of 8 x 9.4 = $75.20 per unit
    assert app.backstop_distance(lv['stop_usd_per_unit'], 1.0) == pytest.approx(150.4)
    btc = mods(**BTC_TOP2).app
    lv = btc.basket_levels(1500.0, 0.01)                     # BTC: the unit capped at 1,200, a stop of 9,600 $-moves
    assert btc.backstop_distance(lv['stop_usd_per_unit'], 0.01) == pytest.approx(19200.0)
    live = mods().app                                        # no stop: no backstop
    assert not live.design_has_stop() and live.backstop_distance(None, 1.0) is None
    assert mods(STOP_LOSS_USD_PER_UNIT=4.0).app.design_has_stop()
    assert mods(BACKSTOP_FACTOR=1.0).app.design_problems()   # it must lie beyond the bot's own stop


def _bot(mods, **ov):
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock, **ov)
    return m, fake, F.make_bot(m, fake, 'XAUUSDm', F.Run())


def test_a_leg_of_a_design_with_a_stop_carries_the_backstop_and_no_target(mods):
    m, fake, bot = _bot(mods, **V3LITE)
    bid, ask = fake.quote()
    resp, sl = bot._open_leg(1, 'XAUUSDm', 0.01, 75.2, 1.0, ask)
    o = fake.orders[-1]
    assert bot._order_done(resp) and sl == round(ask - 150.4, 3) and o['sl'] == sl and o['tp'] == 0.0
    resp, sl = bot._open_leg(-1, 'XAUUSDm', 0.02, 75.2, 1.0, bid)
    o = fake.orders[-1]
    assert bot._order_done(resp) and sl == round(bid + 150.4, 3) and o['sl'] == sl and o['tp'] == 0.0
    assert [p['sl'] for p in fake.positions] == [round(ask - 150.4, 3), round(bid + 150.4, 3)]
    resp, sl = bot._open_leg(1, 'XAUUSDm', 0.01, None, 1.0, ask)     # a distance not known: no backstop
    assert sl == 0.0 and fake.orders[-1]['sl'] == 0.0 and fake.orders[-1]['tp'] == 0.0


def test_a_design_without_a_stop_keeps_the_live_request(mods):
    m, fake, bot = _bot(mods)
    bid, ask = fake.quote()
    resp, sl = bot._open_leg(1, 'XAUUSDm', 0.01, None, 1.0, ask)
    o = fake.orders[-1]
    assert sl is None and o['sl'] == ask - ask * 1 and o['tp'] == ask + ask * 1      # the live auto sl / tp
    resp, sl = bot._open_leg(-1, 'XAUUSDm', 0.01, None, 1.0, bid)
    o = fake.orders[-1]
    assert sl is None and o['sl'] == o['price'] * 2 and o['tp'] == 0.0


@pytest.mark.slow
def test_in_the_loop_every_leg_has_its_backstop_and_the_bots_stop_closes_first(tmp_path):
    """The scaled design (stop 2 units, one add): every entry and add carries sl = its fill -/+ 2 x 2 x the basket's
    unit and no tp; the broker never closes anything (the bot's stop always came first): the same fills as on a
    terminal that ignores sl / tp."""
    fake, clock = market(1800, seed=4)
    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path / 'a')
    assert not run.errors, run.errors[:3]
    opens = [o for o in fake.orders if 'position' not in o]
    assert len(opens) >= 6 and any(len(b['legs']) == 2 for b in baskets(fake, magic=MAGIC))
    for o in opens:
        fill = next(d for d in fake.deals if d.entry == 0 and d.time_msc == o['_t_ms'])
        unit = next(p['levels']['vol_unit'] for p in run.polls if p['t'] > o['_t_ms'] and p['levels'])
        dist = 2.0 * SCALED['STOP_VOL'] * unit
        want = fill.price - dist if fill.type == 0 else fill.price + dist
        assert abs(o['sl'] - want) <= 0.0005 + 1e-9 and o['tp'] == 0.0
    assert not [d for d in fake.deals if d.reason in (fake.DEAL_REASON_SL, fake.DEAL_REASON_TP)]
    fake2, clock2 = market(1800, seed=4)
    fake2.execute_stops = False
    run_bot(fake2, clock2, overrides=SCALED, state_dir=tmp_path / 'b')
    assert not differs(deals_of(fake), deals_of(fake2))


@pytest.mark.slow
def test_a_gap_through_the_backstop_is_booked_as_closed_outside_the_bot(tmp_path):
    """The price jumps beyond the backstop between two polls (the bot cannot act in between; the broker's stop
    closes the position at the gap price). The bot books the basket as closed outside the bot: the realised loss
    and the time of the closing deal from the history, then the pause after a loss (240 s) from that time."""
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=NO_LADDER, state_dir=tmp_path / 'ref')
    b = next(x for x in baskets(fake0, magic=MAGIC) if x['t_close'] - x['t_open'] >= 10)
    unit = next(p['levels']['vol_unit'] for p in ref.polls if p['t'] > b['t_open'] * 1000 and p['levels'])
    backstop = 2.0 * NO_LADDER['STOP_VOL'] * unit
    fake, clock = market(1800, seed=21)
    i = int((fake.t_ms >= (b['t_open'] + 5) * 1000).argmax())
    jump = -1.5 * backstop if b['side'] == 0 else 1.5 * backstop       # against the basket, past its backstop
    fake.bid[i:] += jump
    fake.ask[i:] += jump
    saved = []
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run', on_new_bot=recording_states(saved))
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    assert len(by_broker) == 1 and by_broker[0].time_msc == fake.t_ms[i] and by_broker[0].profit < 0
    t_out = by_broker[0].time_msc / 1000.0
    assert not [o for o in fake.orders if 'position' in o and b['t_open'] * 1000 <= o['_t_ms'] <= t_out * 1000 + 5000]
    booked = [s['last_close'] for s in saved if (s.get('last_close') or {}).get('reason') == 'closed_outside']
    assert booked and booked[0]['side'] == ('BUY' if b['side'] == 0 else 'SELL')
    final = booked[-1]
    assert final['resolved'] and final['source'] == 'history' and final['lost'] is True
    assert final['pnl'] == round(by_broker[0].profit, 2) and final['time'] == pytest.approx(t_out)
    later = [e['t'] / 1000.0 for e in run.events if e['event'] in ('BUY_EXECUTED', 'SELL_EXECUTED') and e['t'] > t_out * 1000]
    assert later and later[0] >= t_out + NO_LADDER['LOSS_COOLDOWN_S']
