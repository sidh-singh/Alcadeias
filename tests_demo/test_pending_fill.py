"""
A basket the bot has just opened is kept while the terminal does not list its position yet (finding 2 of the
demo review). The terminal answers asynchronously and six bots share it: the position of a fill can be missing
from positions_get() for a poll or two. The basket was dropped at once, the next poll saw "flat" and opened a
second basket. Now a basket without positions is kept _PENDING_FILL_S (10 s) after it opened and its side counts
as in a basket (no entry); only after that is it dropped.
"""
import pytest

from conftest import NO_LADDER, F, MAGIC, market, recording_states, run_bot


def _bot(mods):
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    return m, fake, clock, F.make_bot(m, fake, 'XAUUSDm', F.Run())


def test_an_unlisted_fill_is_kept_for_10_s_then_dropped(mods):
    m, fake, clock, bot = _bot(mods)
    now = clock.time()
    lv = m.app.basket_levels(None, 1.0)
    for age, kept in ((0.0, True), (9.9, True), (10.0, False), (60.0, False)):
        state = {'basket': bot._new_basket('BUY', 2, lv, now - age), 'last_close': None}
        changed = bot._sync_basket('XAUUSDm', 'XAUUSDm', state, None, None, 0.01, 1.0, now)
        assert (state['basket'] is not None) == kept and changed == (not kept), age
        assert state['last_close'] is None                    # never booked as a close
        assert m.app.fill_pending(state['basket'], now) == kept


def test_the_listed_position_joins_the_pending_basket(mods):
    m, fake, clock, bot = _bot(mods)
    now = clock.time()
    state = {'basket': bot._new_basket('SELL', 1, m.app.basket_levels(None, 1.0), now - 3), 'last_close': None}
    fake.add_position(1, 0.01, 2000.0, now - 2.5, magic=MAGIC)
    h = m.mt5_helper.MT5PositionHelper(fake)
    assert bot._sync_basket('XAUUSDm', 'XAUUSDm', state, None, h.get_sell_positions('XAUUSDm'), 0.01, 1.0, now)
    b = state['basket']
    assert b['opened_by'] == 'bot' and len(b['ids']) == 1 and not m.app.fill_pending(b, now)


@pytest.mark.slow
@pytest.mark.parametrize('delay_ms', [1500, 4000])
def test_a_slow_listing_never_opens_a_second_basket(tmp_path, delay_ms):
    """The terminal lists every position only `delay_ms` after its fill (the code before this fix opened a second
    basket on most entries): one entry per basket, never two positions open, every basket gets its position."""
    fake, clock = market(1800, seed=21)
    fake.list_delay_ms = delay_ms
    saved = []
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path, on_new_bot=recording_states(saved))
    assert not run.errors, run.errors[:3]
    entries = [e['t'] for e in run.events if e['event'] in ('BUY_EXECUTED', 'SELL_EXECUTED')]
    assert len(entries) >= 3 and all(b - a > 10_000 for a, b in zip(entries, entries[1:]))
    opens = sorted([(d.time_msc, 1) for d in fake.deals if d.entry == 0 and d.magic == MAGIC]
                   + [(d.time_msc, -1) for d in fake.deals if d.entry == 1])
    level = peak = 0
    for _, k in opens:
        level += k
        peak = max(peak, level)
    assert peak == 1
    pending = [p for p in run.polls if p['nb'] + p['ns'] == 0 and p['levels'] is None and not p['entry_allowed']]
    assert pending                                              # the polls before the listing: no entry allowed
    with_ids = {tuple(s['basket']['ids']) for s in saved if s.get('basket') and s['basket'].get('ids')}
    assert len(with_ids) == len(entries) and all(len(ids) == 1 for ids in with_ids)
    assert all(s['basket']['opened_by'] == 'bot' for s in saved if s.get('basket'))
