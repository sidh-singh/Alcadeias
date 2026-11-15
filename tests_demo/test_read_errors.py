"""
positions_get() answering None is a terminal error, not "no positions" (finding 5 of the demo review). Read as
flat it booked this bot's open basket as closed outside the bot (a phantom close, a pause, a rebuild, possibly a
second entry). Now the read raises TerminalReadError and the poll that meets it syncs, books and decides
nothing; a close that cannot see the positions closes nothing and reports a failure.
"""
import pytest

from conftest import (NO_LADDER, F, MAGIC, booked_outside, deals_of, market, quiet_window, recording_states,
                      run_bot)


def _helper(mods):
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    return m, fake, m.mt5_helper.MT5PositionHelper(fake)


def test_a_failed_positions_read_raises_instead_of_reading_flat(mods):
    m, fake, h = _helper(mods)
    now = fake.clock.time()
    fake.add_position(0, 0.01, 1999.0, now - 50, magic=MAGIC)
    assert h.get_buy_positions('XAUUSDm')['count'] == 1 and h.get_sell_positions('XAUUSDm') is None   # none: None
    fake.fail_positions(now - 1, now + 10)
    for read in (h.get_buy_positions, h.get_sell_positions):
        with pytest.raises(m.mt5_helper.TerminalReadError, match='positions_get'):
            read('XAUUSDm')


def test_a_close_that_cannot_see_the_positions_closes_nothing_and_fails(mods):
    m, fake, h = _helper(mods)
    now = fake.clock.time()
    fake.add_position(0, 0.01, 1999.0, now - 50, magic=MAGIC)
    fake.fail_positions(now - 1, now + 10)
    res = h.close_by_type('XAUUSDm', 0)
    assert res['success'] is False and res['closed_count'] == 0 and res['failed_count'] == 1
    assert 'positions_get' in res['errors'][0] and not fake.orders and len(fake.positions) == 1


@pytest.mark.slow
def test_positions_unknown_for_a_while_mid_basket_change_nothing(tmp_path):
    """positions_get answers None for 20 s while the bot holds a basket: those polls are skipped (an ERROR event when
    it starts, TERMINAL_OK when it is over), nothing is booked as closed outside the bot, and the bot takes the
    same decisions and fills as without the error."""
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=NO_LADDER, state_dir=tmp_path / 'ref')
    assert not ref.errors, ref.errors[:3]
    t0 = quiet_window(ref, fake0, 20)

    fake, clock = market(1800, seed=21)
    fake.fail_positions(t0 + 0.5, t0 + 20.5)
    saved = []
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run', on_new_bot=recording_states(saved))
    assert saved and not booked_outside(saved)
    assert deals_of(fake) == deals_of(fake0)
    assert not any((t0 + 0.5) * 1000 < p['t'] < (t0 + 20.5) * 1000 for p in run.polls)    # nothing decided
    events = [e for e in run.events if e['event'] in ('TERMINAL_ERROR', 'TERMINAL_OK')]
    assert [e['event'] for e in events] == ['TERMINAL_ERROR', 'TERMINAL_OK']
    assert events[0]['tag'] == 'ERROR' and 'positions_get' in events[0]['details']['problem']
    assert events[1]['details']['failed_polls'] == 20
    assert len(run.errors) == 1 and 'poll skipped' in run.errors[0]
