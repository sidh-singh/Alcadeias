"""
A basket some of whose legs were closed outside the bot (finding 3 of the re-review). Each leg carries its own
broker-side backstop; with an add (XAU Top 1) the entry's lies nearer than the add's, so a move through it while
the bot or the terminal is down closes the entry and leaves the add. The bot did not book that ("known ids, none
new": no change), kept the gone leg in the basket, judged its stop on the listed leg only and could add again. Now a
leg gone without a close of this bot (no close_pending) marks the basket: the other legs are closed at once on that
poll and the whole basket is booked as closed outside the bot -- the realised P/L of every leg from the deal
history, then the loss pause as after any close.
"""
import pytest

from conftest import SCALED, F, MAGIC, START, baskets, market, recording_states, run_bot

CREDS = {'terminal_path': r'C:\fake\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}
WIDE = dict(SCALED, STOP_VOL=6.0, TARGET_VOL=3.0)      # the scaled Top 1 shape with room after its one add


def _two_leg_basket(mods):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock, **SCALED)
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run())
    now = clock.time()
    e = fake.add_position(0, 0.01, 2000.0, now - 300, magic=MAGIC)          # the entry
    a = fake.add_position(0, 0.01, 1995.0, now - 200, magic=MAGIC)          # the add, 5 below
    b = bot._new_basket('BUY', 1, m.app.basket_levels(5.0, 1.0), now - 300)
    b.update(ids=[e, a], first_time=now - 300)
    return m, fake, clock, bot, {'basket': b, 'last_close': None}, e, a


def test_a_leg_gone_outside_the_bot_marks_the_basket_to_close(mods):
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods)
    h = m.mt5_helper.MT5PositionHelper(fake)
    assert fake.close_by_broker(e)                                          # the entry's backstop
    now = clock.time()
    assert bot._sync_basket('XAUUSDm', 'XAUUSDm', state, h.get_buy_positions('XAUUSDm'), None, 0.01, 1.0, now)
    b = state['basket']                                                     # (before: no change at all)
    assert b['close_pending'] is True and b['outside_ids'] == [e] and b['ids'] == [e, a]
    assert state['last_close'] is None                                     # booked once the rest is out
    # marked once: the next poll (the close not done yet) changes nothing more
    assert not bot._sync_basket('XAUUSDm', 'XAUUSDm', state, h.get_buy_positions('XAUUSDm'), None, 0.01, 1.0, now)
    # the bot closes the add and books the whole basket: both legs' realised P/L, from the history
    res = h.close_by_type('XAUUSDm', 0)
    lc = bot._after_close('XAUUSDm', state, 'BUY', res, {'total_profit': -5.0, 'positions': []}, 'leg_closed_outside',
                          clock.time())
    realised = round(sum(d.profit for d in fake.deals if d.position_id in (e, a)), 2)
    assert state['basket'] is None and state['last_close'] is lc
    assert lc['reason'] == 'closed_outside' and lc['ids'] == [e, a] and lc['outside_ids'] == [e]
    assert lc['resolved'] and lc['source'] == 'history' and lc['pnl'] == realised and lc['lost'] == (realised < 0)


def test_the_bots_own_partial_close_is_not_a_leg_closed_outside(mods):
    """A close of the bot that left a leg behind (close_pending): the legs it closed are gone, the basket is not
    marked as closed outside, and the rest is closed as a retry."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods)
    h = m.mt5_helper.MT5PositionHelper(fake)
    fake.fail_close_tickets = {a}
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 1 and res['failed_count'] == 1
    assert bot._after_close('XAUUSDm', state, 'BUY', res, h.get_buy_positions('XAUUSDm'), 'stop_loss',
                            clock.time()) is None
    assert state['basket']['close_pending'] is True
    assert not bot._sync_basket('XAUUSDm', 'XAUUSDm', state, h.get_buy_positions('XAUUSDm'), None, 0.01, 1.0,
                                clock.time())
    assert 'outside_ids' not in state['basket']


def test_a_backstop_partial_close_estimates_a_loss_until_the_history_has_it(mods):
    """The history does not show the leg closed outside yet: the basket is booked as a loss (the longer pause) until
    it does (then the realised P/L of every leg replaces it)."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods)
    h = m.mt5_helper.MT5PositionHelper(fake)
    assert fake.close_by_broker(e)
    bot._sync_basket('XAUUSDm', 'XAUUSDm', state, h.get_buy_positions('XAUUSDm'), None, 0.01, 1.0, clock.time())
    res = h.close_by_type('XAUUSDm', 0)
    fake.history_none = True
    lc = bot._after_close('XAUUSDm', state, 'BUY', res, {'total_profit': 3.0, 'positions': []}, 'leg_closed_outside',
                          clock.time())
    assert lc['reason'] == 'closed_outside' and lc['lost'] is True and not lc['resolved']
    fake.history_none = False
    assert bot._resolve_last_close(state, clock.time()) and lc['resolved'] and lc['source'] == 'history'


@pytest.fixture(scope='module')
def two_leg_reference(tmp_path_factory):
    """A replay of the scaled Top 1 shape (one add) and its first basket with two legs, held well after the add."""
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=WIDE, state_dir=tmp_path_factory.mktemp('two_leg_ref'))
    assert not ref.errors, ref.errors[:3]
    b = next(x for x in baskets(fake0, magic=MAGIC) if len(x['legs']) == 2)
    t_add = b['legs'][1]['t_in']
    assert b['t_close'] - t_add > 120
    opens = [o for o in fake0.orders if 'position' not in o and b['t_open'] * 1000 <= o['_t_ms'] <= t_add * 1000]
    assert len(opens) == 2
    return b, t_add, [o['sl'] for o in opens]


@pytest.mark.slow
def test_a_backstop_that_closes_one_leg_while_the_terminal_is_down(tmp_path, two_leg_reference):
    """The terminal is gone for 8 s, 12 s after the add; meanwhile the price spikes for one tick through the entry's
    backstop (not the add's) and comes back. When the bot is connected again it finds only the add: it closes it at
    once and books the basket as closed outside the bot, the realised P/L of both legs, and the next entry waits the
    pause after a loss. (Before: the add stayed open on its own.)"""
    b, t_add, (sl_entry, sl_add) = two_leg_reference
    buy = b['side'] == 0
    t_down = t_add + 12.0
    fake, clock = market(1800, seed=21)
    i = int((fake.t_ms >= (t_down + 3.0) * 1000).argmax())                 # one tick, 3 s into the outage
    spike = (sl_entry + sl_add) / 2.0                                       # beyond the entry's backstop only
    fake.bid[i], fake.ask[i] = (spike, spike + 0.12) if buy else (spike - 0.12, spike)
    fake.down(t_down, t_down + 8.0)
    saved = []

    def on_new_bot(bot, n):
        bot.credentials = dict(CREDS)
        recording_states(saved)(bot, n)
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=on_new_bot)
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    entry_id = by_broker[0].position_id
    assert len(by_broker) == 1 and by_broker[0].time_msc == fake.t_ms[i]   # the entry, at the spike
    closes = [o for o in fake.orders if 'position' in o and o['_t_ms'] > t_down * 1000]
    assert closes and closes[0]['_t_ms'] <= (t_down + 15.0) * 1000         # the add, right after the reconnect
    add_id = closes[0]['position']
    assert add_id != entry_id
    assert not [o for o in fake.orders if 'position' not in o and t_down * 1000 < o['_t_ms'] < closes[0]['_t_ms']]
    events = [e for e in run.events if e['event'] in ('LEG_CLOSED_OUTSIDE', 'CLOSE_BUY', 'CLOSE_SELL')
              and e['t'] > t_down * 1000]
    assert events[0]['event'] == 'LEG_CLOSED_OUTSIDE' and events[0]['details']['legs_gone'] == [entry_id]
    assert events[1]['details']['reason'] == 'leg_closed_outside'
    booked = [s['last_close'] for s in saved if (s.get('last_close') or {}).get('reason') == 'closed_outside']
    assert booked
    lc = booked[-1]
    realised = round(sum(d.profit for d in fake.deals if d.position_id in (entry_id, add_id)), 2)
    assert sorted(lc['ids']) == sorted([entry_id, add_id]) and lc['outside_ids'] == [entry_id]
    assert lc['resolved'] and lc['source'] == 'history' and lc['pnl'] == realised and realised < 0 and lc['lost']
    assert lc['time'] == pytest.approx(closes[0]['_t_ms'] / 1000.0, abs=1.0)
    later = [e['t'] / 1000.0 for e in run.events if e['event'] in ('BUY_EXECUTED', 'SELL_EXECUTED')
             and e['t'] > closes[0]['_t_ms']]
    assert not later or later[0] >= lc['time'] + WIDE['LOSS_COOLDOWN_S']
