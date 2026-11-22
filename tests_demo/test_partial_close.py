"""
A basket some of whose legs were closed outside the bot (finding 3 of the re-review). Each leg carries its own
broker-side backstop; with an add (XAU Top 1) the entry's lies nearer than the add's, so a move through it while
the bot or the terminal is down closes the entry and leaves the add. The bot did not book that ("known ids, none
new": no change), kept the gone leg in the basket, judged its stop on the listed leg only and could add again. Now a
leg gone without a close of this bot (no close_pending) marks the basket: the other legs are closed at once on that
poll and the whole basket is booked as closed outside the bot -- the realised P/L of every leg from the deal
history, then the loss pause as after any close.

Fix E of the third review round: the basket learnt an add's position id only from the next positions read, about
2 s after the add. A terminal outage or a restart in that window, with the entry's backstop closing the entry
meanwhile, left a state that knew only the entry: the add was taken over as a new basket, which could add again.
Now the add's position id is recorded from the order's answer at once (_record_fill), kept 10 s while the terminal
does not list it (as the entry's fill), and saved with the state.
"""
import types

import pytest

from conftest import SCALED, F, MAGIC, START, baskets, booked_outside, market, recording_states, run_bot

WIDE = dict(SCALED, STOP_VOL=6.0, TARGET_VOL=3.0)      # the scaled Top 1 shape with room after its one add


def _two_leg_basket(mods, tmp_path):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock, **SCALED)
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run(), state_dir=tmp_path / 'state')     # (never the real OUTPUT_DIR)
    now = clock.time()
    e = fake.add_position(0, 0.01, 2000.0, now - 300, magic=MAGIC)          # the entry
    a = fake.add_position(0, 0.01, 1995.0, now - 200, magic=MAGIC)          # the add, 5 below
    b = bot._new_basket('BUY', 1, m.app.basket_levels(5.0, 1.0), now - 300)
    b.update(ids=[e, a], first_time=now - 300)
    return m, fake, clock, bot, {'basket': b, 'last_close': None}, e, a


def test_a_leg_gone_outside_the_bot_marks_the_basket_to_close(mods, tmp_path):
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
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


def test_the_bots_own_partial_close_is_not_a_leg_closed_outside(mods, tmp_path):
    """A close of the bot that left a leg behind (close_pending): the legs it closed are gone, the basket is not
    marked as closed outside, and the rest is closed as a retry."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
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


def test_a_backstop_partial_close_estimates_a_loss_until_the_history_has_it(mods, tmp_path):
    """The history does not show the leg closed outside yet: the basket is booked as a loss (the longer pause) until
    it does (then the realised P/L of every leg replaces it)."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
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
@pytest.mark.parametrize('lag', [12.0, 0.5, 1.5])
def test_a_backstop_that_closes_one_leg_while_the_terminal_is_down(tmp_path, two_leg_reference, lag):
    """The terminal is gone for 8 s, `lag` s after the add; meanwhile the price spikes for one tick through the
    entry's backstop (not the add's) and comes back. When the bot is connected again it finds only the add: it closes
    it at once and books the basket as closed outside the bot, the realised P/L of both legs, and the next entry waits
    the pause after a loss. (Before finding 3: the add stayed open on its own. Before fix E, with the outage 0.5 or
    1.5 s after the add -- before the next positions read listed it -- the add was taken over as a new basket and
    added again 470 s later.)"""
    b, t_add, (sl_entry, sl_add) = two_leg_reference
    buy = b['side'] == 0
    t_down = t_add + lag
    fake, clock = market(1800, seed=21)
    i = int((fake.t_ms >= (t_down + 3.0) * 1000).argmax())                 # one tick, 3 s into the outage
    spike = (sl_entry + sl_add) / 2.0                                       # beyond the entry's backstop only
    fake.bid[i], fake.ask[i] = (spike, spike + 0.12) if buy else (spike - 0.12, spike)
    fake.down(t_down, t_down + 8.0)
    saved = []

    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=recording_states(saved))
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
    assert not [s for s in saved if (s.get('basket') or {}).get('opened_by') == 'rebuild']     # (fix E: no take-over)


# ───────────────────────────── fix E: an add is a leg of the basket from its fill ─────────────────────────────

def _done(ticket):
    """The terminal's answer to a filled market order: its ticket is the position's identifier (hedging account)."""
    return types.SimpleNamespace(retcode=10009, order=ticket, deal=ticket + 400000, price=0.0, volume=0.01)


def _listed(h, *tickets):
    """This bot's buy positions as a positions read lists them, only `tickets` (a position not listed yet is left
    out)."""
    p = h.get_buy_positions('XAUUSDm')
    keep = [x for x in (p or {}).get('positions', []) if x.ticket in tickets]
    return dict(p, count=len(keep), positions=keep) if keep else None


def _sync(bot, state, positions, now):
    return bot._sync_basket('XAUUSDm', 'XAUUSDm', state, positions, None, 0.01, 1.0, now)


def test_an_add_is_recorded_from_its_order_and_saved_with_the_state(mods, tmp_path):
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
    h = m.mt5_helper.MT5PositionHelper(fake)
    b = state['basket']
    b['ids'] = [e]                                                          # the state before the add
    now = clock.time()
    assert bot._record_fill(b, _done(a), now) and b['ids'] == [e, a] and bot._unlisted(b) == {a: now}
    bot._save_state('XAUUSDm', state)
    loaded = bot._load_state('XAUUSDm')['basket']                           # (a restarted bot reads it back)
    assert loaded['ids'] == [e, a] and bot._unlisted(loaded) == {a: now}
    # not listed yet (the terminal lists it later): it is still a leg, nothing is closed outside the bot
    assert not _sync(bot, state, _listed(h, e), now + 2.0)
    assert not b['close_pending'] and 'outside_ids' not in b and b['ids'] == [e, a]
    # listed: the add is no longer waiting
    assert _sync(bot, state, _listed(h, e, a), now + 3.0)
    assert b['ids'] == [e, a] and 'unlisted' not in b and not b['close_pending']
    assert not bot._record_fill(b, _done(0), now)                            # (no ticket: nothing recorded)


def test_the_entry_closed_outside_before_the_add_is_listed_closes_the_add(mods, tmp_path):
    """The review's case: the state knows the entry and the recorded add, the entry's backstop closed the entry, and
    the first positions read lists only the add -- a leg closed outside the bot, not a basket to take over."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
    h = m.mt5_helper.MT5PositionHelper(fake)
    b = state['basket']
    b['ids'] = [e]
    now = clock.time()
    bot._record_fill(b, _done(a), now)
    assert fake.close_by_broker(e)
    assert _sync(bot, state, _listed(h, a), now + 8.0)
    assert state['basket'] is b and b.get('opened_by') == 'bot'             # (before: a basket rebuilt from the add)
    assert b['close_pending'] and b['outside_ids'] == [e] and b['ids'] == [e, a] and state['last_close'] is None


def test_an_add_that_never_shows_counts_as_closed_outside_after_10_s(mods, tmp_path):
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
    h = m.mt5_helper.MT5PositionHelper(fake)
    b = state['basket']
    now = clock.time()
    bot._record_fill(b, _done(424242), now)                                  # filled, then gone before any listing
    assert not _sync(bot, state, _listed(h, e, a), now + 9.0)
    assert _sync(bot, state, _listed(h, e, a), now + 10.0)
    assert b['close_pending'] and b['outside_ids'] == [424242] and b['ids'] == [e, a, 424242]


def test_with_nothing_listed_a_recorded_add_keeps_the_basket_10_s(mods, tmp_path):
    """No position listed while a recorded add is younger than 10 s: the basket waits (as for the entry's fill), no
    entry; after 10 s with nothing listed it is booked as closed outside the bot, every leg's id with it."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
    b = state['basket']
    now = clock.time()
    bot._record_fill(b, _done(424242), now)
    assert fake.close_by_broker(e) and fake.close_by_broker(a)
    assert not _sync(bot, state, None, now + 5.0) and state['basket'] is b and m.app.fill_pending(b, now + 5.0)
    assert _sync(bot, state, None, now + 10.0) and state['basket'] is None and not m.app.fill_pending(b, now + 10.0)
    lc = state['last_close']
    assert lc['reason'] == 'closed_outside' and lc['ids'] == [e, a, 424242]


def test_an_add_listed_under_another_id_is_that_add(mods, tmp_path):
    """(Defensive: on MT5 the position of a market order has the order's ticket as its id.) A recorded add is not
    listed while an unknown position of the basket's side is: that position is the add."""
    m, fake, clock, bot, state, e, a = _two_leg_basket(mods, tmp_path)
    h = m.mt5_helper.MT5PositionHelper(fake)
    b = state['basket']
    b['ids'] = [e]
    now = clock.time()
    bot._record_fill(b, _done(777), now)
    assert _sync(bot, state, _listed(h, e, a), now + 2.0)
    assert b['ids'] == [e, a] and 'unlisted' not in b and not b['close_pending']


def test_a_close_while_the_add_is_not_listed_yet_waits_for_it(mods, tmp_path):
    """The bot closes the basket (its stop) while the terminal has not listed the add yet: the close is not
    finished -- the add is closed on the next poll that lists it, and the basket is booked whole then."""
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock, **SCALED)
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run(), state_dir=tmp_path / 'state')
    h = m.mt5_helper.MT5PositionHelper(fake)
    now = clock.time()
    e = fake.add_position(0, 0.01, 2000.0, now - 300, magic=MAGIC)
    a = fake.add_position(0, 0.01, 1995.0, now, magic=MAGIC)                  # the add, filled just now
    fake.list_delay_ms = 3000                                                   # listed 3 s after its fill
    b = bot._new_basket('BUY', 1, m.app.basket_levels(5.0, 1.0), now - 300)
    b.update(ids=[e], first_time=now - 300)
    state = {'basket': b, 'last_close': None}
    bot._record_fill(b, _done(a), now)
    clock.sleep(1)
    res = h.close_by_type('XAUUSDm', 0)                                         # lists the entry only
    assert res['closed_count'] == 1 and res['closed_tickets'] == [e]
    assert bot._after_close('XAUUSDm', state, 'BUY', res, _listed(h, e), 'stop_loss', clock.time()) is None
    assert state['basket'] is b and b['close_pending'] and state['last_close'] is None    # (before: booked, [e] only)
    clock.sleep(1)
    assert h.get_buy_positions('XAUUSDm') is None                               # the next read lists nothing yet:
    assert not _sync(bot, state, None, clock.time()) and state['basket'] is b     # the basket waits for its add,
    assert m.app.fill_pending(b, clock.time()) and state['last_close'] is None    # no entry, nothing booked
    clock.sleep(2)
    assert _sync(bot, state, h.get_buy_positions('XAUUSDm'), clock.time())    # the add is listed now
    assert not b.get('outside_ids')                                             # (the bot closed the entry itself)
    res = h.close_by_type('XAUUSDm', 0)
    lc = bot._after_close('XAUUSDm', state, 'BUY', res, {'total_profit': 0.0, 'positions': []}, 'close_retry',
                          clock.time())
    realised = round(sum(d.profit for d in fake.deals if d.position_id in (e, a)), 2)
    assert state['basket'] is None and lc['ids'] == [e, a] and lc['resolved'] and lc['pnl'] == realised


def test_a_close_that_also_closed_the_unlisted_add_books_the_basket_at_once(mods, tmp_path):
    """The final review of the third fix round: the poll's positions read does not list the add yet (filled 1 s ago),
    but the close's own read does, so the bot's close closes both legs. That close is complete: the basket is booked at
    once, with both legs and the close's own reason. (Before: the add, still waiting in `unlisted`, made the close look
    partial -- close_pending, nothing booked -- and 9 s later the basket was booked as closed outside the bot.)"""
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock, **SCALED)
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run(), state_dir=tmp_path / 'state')
    h = m.mt5_helper.MT5PositionHelper(fake)
    now = clock.time()
    e = fake.add_position(0, 0.01, 2000.0, now - 300, magic=MAGIC)
    a = fake.add_position(0, 0.01, 1995.0, now, magic=MAGIC)                  # the add, filled just now
    b = bot._new_basket('BUY', 1, m.app.basket_levels(5.0, 1.0), now - 300)
    b.update(ids=[e], first_time=now - 300)
    state = {'basket': b, 'last_close': None}
    bot._record_fill(b, _done(a), now)
    clock.sleep(1)
    fake.list_delay_ms = 3000
    pos = h.get_buy_positions('XAUUSDm')                                        # the poll's read: the entry only
    assert pos['count'] == 1 and not _sync(bot, state, pos, clock.time())
    fake.list_delay_ms = 0                                                      # listed when the close reads
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 2 and res['failed_count'] == 0 and sorted(res['closed_tickets']) == [e, a]
    lc = bot._after_close('XAUUSDm', state, 'BUY', res, pos, 'stop_loss', clock.time())
    realised = round(sum(d.profit for d in fake.deals if d.position_id in (e, a)), 2)
    assert lc is not None and state['basket'] is None and state['last_close'] is lc
    assert lc['reason'] == 'stop_loss' and lc['ids'] == [e, a] and 'outside_ids' not in lc
    assert lc['resolved'] and lc['source'] == 'history' and lc['pnl'] == realised and lc['time'] == clock.time()


@pytest.mark.slow
def test_a_restart_right_after_the_add_closes_the_add(tmp_path, two_leg_reference):
    """The bot process dies 0.5 s after the add (in its sleep after the order, before the next positions read) and is
    down 60 s; meanwhile the entry's backstop closes the entry. The state file knows the add (recorded from its
    order): the first poll after the restart closes it and the whole basket is booked as closed outside the bot.
    (Before fix E: the state knew only the entry, the add was taken over as a new basket and added again.)"""
    b, t_add, (sl_entry, sl_add) = two_leg_reference
    buy = b['side'] == 0
    fake, clock = market(1800, seed=21)
    clock.restarts_ms = [int(round((t_add + 0.5) * 1000))]
    i = int((fake.t_ms >= (t_add + 30.5) * 1000).argmax())                  # one tick through the entry's backstop
    spike = (sl_entry + sl_add) / 2.0
    fake.bid[i], fake.ask[i] = (spike, spike + 0.12) if buy else (spike - 0.12, spike)
    saved, at_restart = [], []

    def on_new_bot(bot, n):
        recording_states(saved)(bot, n)
        if n == 1:
            at_restart.append(dict((saved[-1].get('basket') or {}) if saved else {}))
            clock.now_ms += 60_000                                          # down 60 s
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=on_new_bot)
    t_r = t_add + 60.5
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    entry_id = by_broker[0].position_id
    assert run.restarts == 1 and len(by_broker) == 1
    assert len(at_restart[0]['ids']) == 2 and entry_id in at_restart[0]['ids']      # the add was saved with the state
    closes = [o for o in fake.orders if 'position' in o and o['_t_ms'] > t_r * 1000]
    assert closes and closes[0]['_t_ms'] <= (t_r + 3.0) * 1000 and closes[0]['position'] != entry_id
    assert not [o for o in fake.orders if 'position' not in o and t_r * 1000 < o['_t_ms'] < closes[0]['_t_ms']]
    events = [e['event'] for e in run.events if e['t'] > t_r * 1000]
    assert events[:2] == ['LEG_CLOSED_OUTSIDE', 'CLOSE_BUY' if buy else 'CLOSE_SELL']
    lc = [s['last_close'] for s in saved if (s.get('last_close') or {}).get('reason') == 'closed_outside'][-1]
    realised = round(sum(d.profit for d in fake.deals if d.position_id in (entry_id, closes[0]['position'])), 2)
    assert lc['resolved'] and lc['pnl'] == realised and lc['lost'] and lc['outside_ids'] == [entry_id]
    assert not [s for s in saved if (s.get('basket') or {}).get('opened_by') == 'rebuild']


@pytest.mark.slow
def test_an_add_listed_late_changes_nothing(tmp_path):
    """Normal operation with an add the terminal lists 2.5 s after its fill (after the poll that follows the add): the
    recorded add waits, nothing is closed outside the bot, nothing is taken over, the two-leg basket is closed by the
    bot's own rule."""
    fake, clock = market(1800, seed=21)
    fake.list_delay_ms = 2500
    saved = []
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=recording_states(saved))
    assert not run.errors, run.errors[:3]
    assert not [e for e in run.events if e['event'] == 'LEG_CLOSED_OUTSIDE'] and not booked_outside(saved)
    two = [x for x in baskets(fake, magic=MAGIC) if len(x['legs']) == 2]
    assert two and all(d.reason == 3 for d in fake.deals)                    # every close the bot's own
    assert any((s.get('basket') or {}).get('unlisted') for s in saved)       # (the add did wait to be listed)
