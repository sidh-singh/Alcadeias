"""
A basket the bot has just opened is kept while the terminal does not list its position yet (finding 2 of the
demo review). The terminal answers asynchronously and six bots share it: the position of a fill can be missing
from positions_get() for a poll or two. The basket was dropped at once, the next poll saw "flat" and opened a
second basket. Now a basket without positions is kept _PENDING_FILL_S (10 s) after it opened and its side counts
as in a basket (no entry); only after that is it dropped.

The final review of the third fix round (fix E's nearby case, the entry): the basket learnt its entry's position id
only from the next positions read, about 1 s after the fill. If the bot stopped or the terminal went down in that
second, and the entry's broker-side backstop closed it meanwhile, the first poll back found a basket without ids and
nothing listed: it was dropped as a fill that "never showed up", nothing was booked, and the bot entered again at
once instead of pausing after the loss. Now the entry's position id is recorded from the order's answer at once
(_record_fill, as for an add) and saved with the state: an entry gone before its first listing is a basket closed
outside the bot, booked with its realised loss, and the pause after a loss follows.
"""
import os
import types

import pytest

from conftest import NO_LADDER, SCALED, F, MAGIC, market, recording_states, run_bot


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


# ───────────────────────────── the entry is a leg of the basket from its fill ─────────────────────────────

WIDE = dict(SCALED, STOP_VOL=6.0, TARGET_VOL=3.0)      # the scaled Top 1 shape (as test_partial_close.py)
CREDS = {'terminal_path': r'C:\fake\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}


def test_the_entry_is_recorded_from_its_order(tmp_path):
    """The state the entry's own poll saves already holds the entry's position id (its order's ticket), waiting to be
    listed; the next positions read lists it, and from then on the basket is as before."""
    fake, clock = market(600, seed=21)
    fake.list_delay_ms = 4000                               # (listed only after the poll that follows the entry)
    saved = []
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=recording_states(saved))
    assert not run.errors, run.errors[:3]
    entry = next(o for o in fake.orders if 'position' not in o)
    ticket = next(d.position_id for d in fake.deals if d.entry == 0 and d.time_msc == entry['_t_ms'])
    first = next(s['basket'] for s in saved if s.get('basket'))
    assert first['ids'] == [ticket] and first['unlisted'][0]['id'] == ticket and first['first_time'] is None
    listed = next(s['basket'] for s in saved if (s.get('basket') or {}).get('first_time'))
    assert listed['ids'] == [ticket] and 'unlisted' not in listed
    assert listed['first_time'] == pytest.approx(entry['_t_ms'] / 1000.0, abs=0.001)


def test_an_entry_never_listed_is_kept_10_s_then_booked_as_closed_outside(mods):
    """Unit level: with nothing listed, the recorded entry keeps the basket 10 s (no second entry); then it is booked
    as closed outside the bot -- not dropped -- with the P/L and the time of its closing deal from the history."""
    m, fake, clock, bot = _bot(mods)
    now = clock.time()
    p = fake.add_position(0, 0.01, 2000.0, now, magic=MAGIC)           # the entry ...
    clock.sleep(4)
    assert fake.close_by_broker(p)                                       # ... closed by its backstop 4 s later
    t_out = clock.time()
    b = bot._new_basket('BUY', 1, m.app.basket_levels(None, 1.0), now)
    assert bot._record_fill(b, types.SimpleNamespace(retcode=10009, order=p, deal=0), now)
    state = {'basket': b, 'last_close': None}
    assert not bot._sync_basket('XAUUSDm', 'XAUUSDm', state, None, None, 0.01, 1.0, now + 9.9)
    assert state['basket'] is b and m.app.fill_pending(b, now + 9.9)
    assert bot._sync_basket('XAUUSDm', 'XAUUSDm', state, None, None, 0.01, 1.0, now + 10.0)
    lc = state['last_close']
    assert state['basket'] is None and lc['reason'] == 'closed_outside' and lc['ids'] == [p]
    assert bot._resolve_last_close(state, now + 10.0)
    realised = round(sum(d.profit for d in fake.deals if d.position_id == p), 2)
    assert lc['resolved'] and lc['source'] == 'history' and lc['pnl'] == realised and lc['lost'] == (realised < 0)
    assert lc['time'] == pytest.approx(t_out, abs=0.001)               # the pause runs from its closing deal


@pytest.fixture(scope='module')
def first_entry(tmp_path_factory):
    """A replay of the scaled Top 1 shape: the time of its first entry and that entry's broker-side backstop."""
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=WIDE, state_dir=tmp_path_factory.mktemp('first_entry_ref'))
    assert not ref.errors, ref.errors[:3]
    o = next(o for o in fake0.orders if 'position' not in o)
    return o['_t_ms'] / 1000.0, o['sl'], o['type'] == 0


def _entry_gone_while_down(tmp_path, first_entry, mode):
    """The bot stops (`mode` 'crash': the process dies; 'outage': the terminal is gone) 0.5 s after the first entry,
    before the next positions read lists it, for 60 s; 30 s in, one tick goes through the entry's backstop."""
    t_entry, sl, buy = first_entry
    t_cut = t_entry + 0.5
    fake, clock = market(1800, seed=21)
    i = int((fake.t_ms >= (t_cut + 30.0) * 1000).argmax())
    spike = sl - 0.5 if buy else sl + 0.5
    fake.bid[i], fake.ask[i] = (spike, spike + 0.12) if buy else (spike - 0.12, spike)
    saved, at_restart = [], []
    if mode == 'crash':
        clock.restarts_ms = [int(round(t_cut * 1000))]
    else:
        fake.down(t_cut, t_cut + 60.0)

    bots = []

    def on_new_bot(bot, n):
        bot.credentials = dict(CREDS)
        bots.append(bot)
        recording_states(saved)(bot, n)
        if mode == 'crash' and n == 1:
            at_restart.append(dict((saved[-1].get('basket') or {}) if saved else {}))
            clock.now_ms += 60_000                                       # down 60 s
    trace = tmp_path / 'trace'                       # (both bots' trace and text log, as in one OUTPUT_DIR)
    run = run_bot(fake, clock, overrides=WIDE, state_dir=tmp_path, on_new_bot=on_new_bot, trace_dir=trace)
    for bot in bots:
        for tr in list((getattr(bot, '_tracers', None) or {}).values()):
            tr._flush()
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    assert len(by_broker) == 1 and by_broker[0].time_msc == fake.t_ms[i]   # the entry, at the spike
    entry_id = by_broker[0].position_id
    realised = round(sum(d.profit for d in fake.deals if d.position_id == entry_id), 2)
    booked = [s['last_close'] for s in saved if (s.get('last_close') or {}).get('ids') == [entry_id]]
    assert booked, 'the entry closed outside the bot was never booked'
    lc = booked[-1]
    assert lc['reason'] == 'closed_outside' and lc['resolved'] and lc['source'] == 'history'
    assert lc['pnl'] == realised and realised < 0 and lc['lost'] is True
    assert lc['time'] == pytest.approx(by_broker[0].time_msc / 1000.0, abs=0.001)
    later = [o['_t_ms'] / 1000.0 for o in fake.orders if 'position' not in o and o['_t_ms'] > t_cut * 1000]
    assert not later or later[0] >= lc['time'] + WIDE['LOSS_COOLDOWN_S']     # the pause after a loss
    assert not [s for s in saved if (s.get('basket') or {}).get('opened_by') == 'rebuild']
    # the text log (tracelog.py) says the same: one CLOSE line, the pause after the loss, and no error of the trace
    # (before the final step's fix: UnboundLocalError on this poll and on every poll after it, no CLOSE, no PAUSE line)
    lines = []
    for name in sorted(os.listdir(trace / 'logs')):
        if name.endswith('.log'):
            with open(trace / 'logs' / name, encoding='utf-8') as f:
                lines += f.read().splitlines()
    assert lines and not [ln for ln in lines if '| ERROR | TRACE |' in ln]
    gone = [ln for ln in lines if f'| CLOSE | CLOSE | the {"BUY" if buy else "SELL"} entry [{entry_id}] is gone before '
            'the terminal listed it' in ln]
    assert len(gone) == 1 and f'realised -${-realised:,.2f}, its closing deal at ' in gone[0], gone
    pause = [ln for ln in lines if '| INFO | PAUSE | entry pause started: ' in ln and f'(loss -${-realised:,.2f})' in ln]
    assert len(pause) == 1, pause
    return run, at_restart, entry_id


@pytest.mark.slow
def test_a_restart_right_after_the_entry_books_the_entry_its_backstop_closed(tmp_path, first_entry):
    """(Before: the state at the restart knew no position of the basket; the entry, closed by its backstop meanwhile,
    was dropped as a fill that never showed up, nothing was booked, and the bot entered again 0.6 s after it was back
    instead of pausing 240 s after the loss.)"""
    run, at_restart, entry_id = _entry_gone_while_down(tmp_path, first_entry, 'crash')
    assert run.restarts == 1 and at_restart[0]['ids'] == [entry_id]       # saved with the state at the fill


@pytest.mark.slow
def test_an_outage_right_after_the_entry_books_the_entry_its_backstop_closed(tmp_path, first_entry):
    """(Before: the same with the terminal gone instead: the bot entered again 1.1 s after it reconnected.)"""
    run, at_restart, entry_id = _entry_gone_while_down(tmp_path, first_entry, 'outage')
    assert [e for e in run.events if e['event'] == 'TERMINAL_RECONNECTED']
