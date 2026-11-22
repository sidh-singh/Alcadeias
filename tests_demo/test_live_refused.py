"""
Refused opening orders (app.py, spec 7), both loops: truthful events (BUY_EXECUTED / BUY_MORE_EXECUTED ... only
for a fill; BUY_REFUSED / ... with the retcode and the broker's comment, the first 3 of a streak one by one, then a
line at most every 30 s), and the slower retry: while a streak of refusals is younger than 4 minutes the bot tries
again at its poll's pace, exactly as the demo bot; then once per 30 s, after 15 minutes once a minute -- a time
tested where the safety is tested, no sleep, never for a close; only an answer of the broker counts; a fill, or
10 minutes without an open wanted, ends it.
"""
import types

import pytest

import test_turtle_bot as TB
from conftest import F, START
from conftest import differs

REFUSED = types.SimpleNamespace(retcode=10018, comment='market closed', order=0, deal=0, price=0.0, volume=0.0)
FILLED = types.SimpleNamespace(retcode=10009, comment='done', order=7, deal=8, price=2000.0, volume=0.01)
FREE = {'enabled': True, 'blocked': False, 'hold': False}


def _turtle(tmp_path, refuse_from=None, refuse_to=None, segments=None, on_bot=None):
    fake, clock = TB._market(segments or TB._long_trip())
    if refuse_from is not None:
        fake.at(START + refuse_from, lambda f: setattr(f, 'refuse_orders', 10 ** 9))
        fake.at(START + refuse_to, lambda f: setattr(f, 'refuse_orders', 0))
    run = TB._run(fake, clock, tmp_path / 'state', on_bot=on_bot)
    run.fake = fake
    return run


def _attempts(fake, after=0.0):
    return [o['_t_ms'] / 1000.0 - START for o in TB._opens(fake) if o['_t_ms'] / 1000.0 - START >= after]


def test_a_refused_entry_is_never_logged_as_executed_and_the_refusals_are_counted_not_repeated(tmp_path):
    """The entry refused for 100 s from the breakout: BUY_REFUSED with the retcode and the broker's comment, the
    first three one by one, then at most one line per 30 s with the count; BUY_EXECUTED once, for the fill."""
    run = _turtle(tmp_path, refuse_from=450.0, refuse_to=550.0)
    ev = [e for e in run.events if e['event'] in ('BUY_REFUSED', 'BUY_EXECUTED')]
    refused = [e for e in ev if e['event'] == 'BUY_REFUSED']
    assert [e['event'] for e in ev][-1] == 'BUY_EXECUTED' and [e['event'] for e in ev].count('BUY_EXECUTED') == 1
    attempts = _attempts(run.fake)
    n = len(attempts) - 1                                           # (the last attempt filled)
    assert n >= 30
    first = refused[:3]
    assert [e['details']['refusals'] for e in first] == [1, 2, 3] and not any(e['details'].get('summary') for e in first)
    assert all(e['details']['retcode'] == 10018 and e['details']['comment'] == 'market closed' for e in refused)
    later = refused[3:]
    assert later and all(e['details']['summary'] for e in later)
    times = [e['t'] / 1000.0 for e in refused[2:]]
    assert all(b - a >= 30.0 for a, b in zip(times, times[1:]))
    # every refusal is in the count of the line after it: none is lost, none is a line of its own
    last = refused[-1]['details']
    assert last['refusals'] + sum(1 for t in attempts[:-1] if t > refused[-1]['t'] / 1000.0 - START) == n
    assert not any(e['event'] == 'TURTLE_NOTE' and 'refused' in e['details'].get('note', '') for e in run.events)


@pytest.mark.slow
def test_after_four_minutes_of_refusals_an_open_is_tried_every_30_s_then_every_minute(tmp_path):
    """The entry refused for 20 minutes from the breakout (the price stays beyond its level all along): tried at
    the poll's pace for 4 minutes -- as the demo bot -- then once per 30 s, after 15 minutes once a minute; the
    held polls say why and until when. The fill ends the streak."""
    run = _turtle(tmp_path, refuse_from=450.0, refuse_to=1650.0)
    a = _attempts(run.fake)
    t0 = a[0]
    fast = [x for x in a if x - t0 < 240.0]
    mid = [x for x in a if 240.0 <= x - t0 < 900.0]
    slow = [x for x in a if x - t0 >= 900.0]
    assert max(b - x for x, b in zip(fast, fast[1:])) < 3.0 and len(fast) > 60
    gaps_mid = [b - x for x, b in zip(mid, mid[1:])]
    assert gaps_mid and all(29.0 <= g <= 33.0 for g in gaps_mid)
    gaps_slow = [b - x for x, b in zip(slow, slow[1:])]
    assert gaps_slow and all(59.0 <= g <= 63.0 for g in gaps_slow)
    held = [p['open_hold'] for p in run.polls if p['open_hold']]
    assert held and {h['why'] for h in held} == {'refused_backoff'}
    assert all(h['until'] is not None and h['refusals'] >= 1 and h['kind'] == 'entry' for h in held)
    assert [e['event'] for e in run.events].count('BUY_EXECUTED') == 1


def test_the_slower_retry_never_holds_back_a_close(tmp_path):
    """With the flag of every poll saying 'refused_backoff' from after the last add on, the trade's stop closes
    every leg at the very moments of a bot without it."""
    fake0, clock0 = TB._market(TB._long_trip())
    TB._run(fake0, clock0, tmp_path / 'ref')
    t_r = TB._opens(fake0)[3]['_t_ms'] / 1000.0 - START + 30.0

    def free(path, on_bot=None):
        fake, clock = TB._market(TB._long_trip(), restarts=(t_r,))
        TB._run(fake, clock, path, on_bot=on_bot)
        return fake

    def backoff(bot, n):
        if n == 1:
            bot._opens_check = lambda view, now: {'why': 'refused_backoff', 'until': now + 30.0, 'refusals': 9}
    a = free(tmp_path / 'a')
    b = free(tmp_path / 'b', backoff)
    assert not differs(TB._closes(a), TB._closes(b)) and len(TB._closes(a)) == 4


def test_only_an_answer_of_the_broker_counts_and_a_fill_or_ten_quiet_minutes_end_the_streak(mods):
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    clock = m.clock

    def advance(s):
        clock.now_ms += int(s * 1000)
    # no answer at all (a guard stopped it, or the terminal did not answer): logged, never a slower retry
    for _ in range(5):
        bot._note_open_answer('XAUUSDm', 'BUY', None, {}, None)
    advance(300)
    assert bot._opens_check(FREE, clock.time()) is None and bot._refusal['first'] is None
    # the broker refuses: at the poll's pace for 4 minutes, then once per 30 s
    t0 = clock.time()
    bot._note_open_answer('XAUUSDm', 'BUY', REFUSED, {}, None)
    advance(239)
    bot._note_open_answer('XAUUSDm', 'BUY', REFUSED, {}, None)
    assert bot._opens_check(FREE, clock.time()) is None                   # (still younger than 4 minutes)
    advance(2)
    hold = bot._opens_check(FREE, clock.time())
    assert hold['why'] == 'refused_backoff' and hold['until'] == pytest.approx(t0 + 239 + 30) and hold['refusals'] == 2
    assert hold['since'] == pytest.approx(t0)          # the streak's first refusal (the dashboard's banner names it)
    advance(28)
    assert bot._opens_check(FREE, clock.time()) is None                   # its next try
    # held, the order is the flag's: _open_held says so for an add as for an entry
    bot._note_open_answer('XAUUSDm', 'BUY', REFUSED, {}, None)
    bot._opens_stop = bot._opens_check(FREE, clock.time())
    h = bot._open_held('add', 'BUY', 2000.0)
    assert h['why'] == 'refused_backoff' and h['kind'] == 'add' and h['refusals'] == 3
    assert h['since'] == pytest.approx(t0)
    # every other reason has no 'since' (None): it is the refusal streak's alone
    for why in ('old_bot', 'safety', 'safety_checking'):
        bot._opens_stop = {'why': why, 'until': None, 'refusals': 0}
        assert bot._open_held('entry', 'BUY', 2000.0)['since'] is None
    bot._opens_stop = None
    assert bot._open_held('entry', 'BUY', 2000.0, sizing_known=False)['since'] is None
    bot._opens_stop = bot._opens_check(FREE, clock.time())
    # after 15 minutes once a minute
    advance(900 - (clock.time() - t0) + 1)
    bot._note_open_answer('XAUUSDm', 'BUY', REFUSED, {}, None)
    assert bot._opens_check(FREE, clock.time())['until'] == pytest.approx(clock.time() + 60.0)
    # a fill ends the streak
    bot._note_open_answer('XAUUSDm', 'BUY', FILLED, {}, None)
    assert bot._refusal is None and bot._opens_check(FREE, clock.time()) is None
    # 10 minutes without an open wanted end it too
    bot._note_open_answer('XAUUSDm', 'SELL', REFUSED, {}, None)
    advance(250)
    bot._note_open_answer('XAUUSDm', 'SELL', REFUSED, {}, None)
    advance(601)
    assert bot._opens_check(FREE, clock.time()) is None and bot._refusal is None
    names = [e['event'] for e in bot_events(bot)]
    assert 'BUY_EXECUTED' in names and names.count('BUY_EXECUTED') == 1 and 'SELL_EXECUTED' not in names


def bot_events(bot):
    # make_bot records the events into the Run it was given; find it through the replaced _log_event
    run = bot._log_event.__closure__
    for cell in run or ():
        if isinstance(cell.cell_contents, F.Run):
            return cell.cell_contents.events
    return []


def test_the_safety_and_the_old_bot_come_before_the_slower_retry_and_a_balance_not_known_holds_only_entries(mods):
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    bot._opens_stop = None
    assert bot._open_held('entry', 'BUY', 1.0, sizing_known=False)['why'] == 'balance_unknown'
    assert bot._open_held('add', 'BUY', 1.0, sizing_known=False) is None
    assert bot._open_held('pyramid', 'SELL', 1.0, sizing_known=False) is None
    for why in ('old_bot', 'safety', 'safety_checking'):
        bot._opens_stop = {'why': why, 'until': None, 'refusals': 0}
        for kind in ('entry', 'add', 'pyramid'):
            assert bot._open_held(kind, 'BUY', 1.0, sizing_known=False)['why'] == why
    bot._opens_stop = {'why': 'refused_backoff', 'until': 5.0, 'refusals': 4}
    assert bot._open_held('entry', 'BUY', 1.0, sizing_known=False)['why'] == 'balance_unknown'
    assert bot._open_held('entry', 'BUY', 1.0)['why'] == 'refused_backoff'
    # the order of the flag: an old bot first (the switch does not lift it), then a block, then a hold
    bot._old_bot_same_terminal = lambda: True
    assert bot._opens_check({'blocked': True, 'hold': True}, 0.0)['why'] == 'old_bot'
    bot._old_bot_same_terminal = lambda: False
    assert bot._opens_check({'blocked': True, 'hold': True}, 0.0)['why'] == 'safety'
    assert bot._opens_check({'blocked': False, 'hold': True}, 0.0)['why'] == 'safety_checking'
    assert bot._opens_check({'blocked': False, 'hold': False, 'enabled': False}, 0.0) is None
