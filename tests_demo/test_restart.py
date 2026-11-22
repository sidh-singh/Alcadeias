"""
Restart recovery. The open basket's fixed distances, its ladder arming and the loss pause are kept in
OUTPUT_DIR/state/<symbol>_state.json, so a restart changes nothing; without the file they are rebuilt from
the terminal: the unit from the oldest position's volume, the volatility unit from the bars at its open
time, the pause from the deal history.
"""
import json
import os

import pytest

from conftest import F, MAGIC, SCALED, START, baskets, market, run_bot

SECONDS = 2400
SEED = 21


def _deals(fake):
    return [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in fake.deals]


@pytest.fixture(scope='module')
def reference(tmp_path_factory):
    """One run without a restart, to compare with."""
    fake, clock = market(SECONDS, seed=SEED)
    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path_factory.mktemp('ref'))
    assert not run.errors
    return run, fake


def _quiet_gap(run, fake, pred):
    """A time between two polls, the first satisfying pred(poll) and sending no order, to restart at
    (so the process dies in its 1 s loop sleep, as a supervisor restart would find it)."""
    order_t = {o['_t_ms'] for o in fake.orders}
    polls = run.polls
    for p, q in zip(polls, polls[1:]):
        if pred(p) and p['t'] not in order_t and q['t'] - p['t'] >= 1000:
            return (p['t'] + q['t']) / 2000.0 - START
    raise AssertionError('no such poll')


def _restarted(reference, tmp_path, pred, drop_state=False):
    run0, fake0 = reference
    at = _quiet_gap(run0, fake0, pred)
    fake, clock = market(SECONDS, seed=SEED, restarts=[at])
    seen = {}

    def on_new_bot(bot, n):
        if n > 0 and drop_state:                 # the process comes back without its state file
            path = bot._state_path('XAUUSDm')
            with open(path) as f:
                seen['before'] = json.load(f)
            os.remove(path)

    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path / 'state',
                    on_new_bot=on_new_bot)
    assert not run.errors, run.errors[:3]
    assert run.restarts == 1
    return run, fake, seen, at


@pytest.mark.slow
def test_a_restart_inside_a_basket_changes_nothing_with_the_state_file(reference, tmp_path):
    run, fake, _, at = _restarted(reference, tmp_path, lambda p: p['nb'] + p['ns'] > 0 and p['t'] > (START + 300) * 1000)
    assert _deals(fake) == _deals(reference[1])


@pytest.mark.slow
def test_a_restart_inside_a_loss_pause_keeps_the_pause(reference, tmp_path):
    run0, fake0 = reference
    lost = [b for b in baskets(fake0, magic=MAGIC) if b['pnl'] < 0]
    assert lost
    t_close = lost[0]['t_close']
    pred = lambda p: p['nb'] + p['ns'] == 0 and p['t'] > (t_close + 5) * 1000
    run, fake, _, at = _restarted(reference, tmp_path, pred)
    assert _deals(fake) == _deals(fake0)
    run, fake, seen, at = _restarted(reference, tmp_path / 'b', pred, drop_state=True)
    assert _deals(fake) == _deals(fake0)                  # rebuilt from the deal history: the same pause
    assert seen['before']['last_close']['lost'] is True


@pytest.mark.slow
def test_without_the_state_file_the_basket_is_rebuilt_from_the_terminal(reference, tmp_path):
    pred = lambda p: p['nb'] + p['ns'] > 0 and p['t'] > (START + 300) * 1000
    run, fake, seen, at = _restarted(reference, tmp_path, pred, drop_state=True)
    before = seen['before']['basket']
    after = [p['levels'] for p in run.polls if p['t'] > (START + at) * 1000 and p['levels']][0]
    assert after['units'] == before['units']
    assert after['vol_unit'] == before['vol_unit']            # the unit of the bars at the open time
    assert after['stop_usd'] == round(before['stop_usd_per_unit'] * before['units'], 2)
    assert after['target_usd'] == round(before['target_usd_per_unit'] * before['units'], 2)
    assert after['gap_px'] == before['gap_px']
    assert after['ladder_armed'] in (False, True)


def test_units_of_an_open_basket_come_from_its_oldest_position(mods, tmp_path):
    """A basket of 3 units found open with no state file keeps 3 units (live restarted at 1)."""
    fake, clock = market(20)
    fake.add_position(0, 0.03, 1999.0, START - 3000, magic=MAGIC)
    fake.add_position(0, 0.03, 1990.0, START - 2000, magic=MAGIC)
    wide = dict(SCALED, MAX_ADDS=0, TARGET_VOL=10000.0, STOP_VOL=10000.0)      # keep it open
    run = run_bot(fake, clock, overrides=wide, state_dir=tmp_path)
    assert not run.errors
    held = [p for p in run.polls if p['nb'] == 2]
    assert held and all(p['units'] == 3 for p in held)
    state = json.load(open(tmp_path / 'XAUUSDm_state.json'))
    assert state['basket']['opened_by'] == 'rebuild' and state['basket']['units'] == 3
    assert state['basket']['vol_unit'] > 0 and state['basket']['vol_source'] == 'bars_at_open'
