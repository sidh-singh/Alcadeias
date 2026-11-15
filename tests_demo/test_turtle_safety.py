"""
The demo review's fixes in the Turtle's own loop (STRATEGY = 'turtle'). Every poll first checks that the terminal
answers and holds this bot's demo account (findings 1 and 4), and a positions read that fails skips the poll
(finding 5) -- the book is never matched with positions that are not this account's or not known, so an open trade
is not ended as "closed outside the bot"; polls in which the reference run decided nothing are skipped exactly: the
trade is the same. Every leg carries a broker-side backstop 1 N beyond the trade's stop at its fill (finding 3); a
leg it closes is handled as one closed outside the bot.

The re-review: the account is read again right after the positions (finding 2), and a leg closed outside the bot
at or beyond the trade's stop -- its backstop -- ends the trade at once, also when the price is back inside the
stop by the time the bot sees it (finding 3, checked: with the price still beyond it the bot's own stop already
closed the other legs right after); a leg closed by hand inside the stop leaves the trade on (test_turtle_bot.py).
"""
import pytest

from conftest import MAGIC, START, F
from test_turtle_bot import LV, SYMBOL, TURTLE, _closes, _long_trip, _market, _opens, _run

CREDS = {'terminal_path': r'C:\fake\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}
QUIET = (845.0, 935.0)        # after the long trip's second add (841 s), before its third (1138 s): nothing is due
OUTSIDE = ('TURTLE_CLOSED_OUTSIDE', 'TURTLE_LEG_CLOSED_OUTSIDE', 'TURTLE_REBUILT')


@pytest.fixture(scope='module')
def reference(tmp_path_factory):
    fake, clock = _market(_long_trip())
    run = _run(fake, clock, tmp_path_factory.mktemp('turtle_ref'))
    assert not run.errors, run.errors[:3]
    opens = [round(o['_t_ms'] / 1000.0 - START) for o in _opens(fake)]
    assert len(opens) == 4 and opens[1] < QUIET[0] and QUIET[1] < opens[2]
    return fake


def _same_trade(fake, ref):
    assert [o['_t_ms'] for o in _opens(fake)] == [o['_t_ms'] for o in _opens(ref)]
    assert [o['_t_ms'] for o in _closes(fake)] == [o['_t_ms'] for o in _closes(ref)]
    assert [(d.price, d.volume) for d in fake.deals] == [(d.price, d.volume) for d in ref.deals]
    assert not fake.positions


def _nothing_sent(fake, a, b):
    return not [o for o in fake.orders if (START + a) * 1000 <= o['_t_ms'] <= (START + b) * 1000]


@pytest.mark.slow
def test_a_failed_positions_read_mid_trade_changes_nothing(reference, tmp_path):
    fake, clock = _market(_long_trip())
    fake.fail_positions(START + QUIET[0], START + QUIET[1])
    run = _run(fake, clock, tmp_path)
    _same_trade(fake, reference)
    events = [e['event'] for e in run.events]
    assert not set(OUTSIDE) & set(events)                     # (before: the trade ended "closed outside the bot")
    assert events.count('TERMINAL_ERROR') == 1 and events.count('TERMINAL_OK') == 1


@pytest.mark.slow
@pytest.mark.parametrize('lands', ['before_the_poll', 'between_the_account_check_and_the_positions_read'])
def test_another_account_on_the_terminal_mid_trade_changes_nothing(reference, tmp_path, lands):
    """A live bot logs the shared terminal into the real account for a minute: that account shows none of this
    bot's legs. Nothing is synced or sent until the demo account is back, and the trade goes on as it would have --
    also when the switch lands after the poll's account check, just before its positions read (finding 2 of the
    re-review: the legs looked closed outside the bot): the account is read again right after the positions."""
    fake, clock = _market(_long_trip())
    stash = {}

    def to_live(f):
        stash['positions'], f.positions = f.positions, []
        f.account_login, f.trade_mode = 99, f.ACCOUNT_TRADE_MODE_REAL

    def back(f):
        f.positions = stash['positions']
        f.account_login, f.trade_mode = 1, f.ACCOUNT_TRADE_MODE_DEMO
    if lands == 'before_the_poll':
        fake.at(START + QUIET[0], to_live)
    else:
        fake.on_call('positions_get', START + QUIET[0], to_live)
    fake.at(START + QUIET[0] + 60, back)
    run = _run(fake, clock, tmp_path)
    _same_trade(fake, reference)
    assert _nothing_sent(fake, *QUIET)
    events = [e['event'] for e in run.events]
    assert not set(OUTSIDE) & set(events)
    assert events.count('ACCOUNT_REFUSED') == 1 and events.count('ACCOUNT_OK') == 1


@pytest.mark.slow
def test_a_terminal_restart_mid_trade_is_ridden_out(reference, tmp_path):
    """The terminal is gone for 45 s: the polls decide nothing, the bot connects again after 5 failed polls and
    then after 5, 10 and 30 s; the fourth attempt finds it back, and the trade goes on as it would have. Of the three
    failures (one reason) only the first is logged; TERMINAL_RECONNECTED counts them and the outage."""
    fake, clock = _market(_long_trip())
    a = START + QUIET[0]
    fake.down(a, a + 45)

    def creds(bot, n):
        bot.credentials = dict(CREDS)
    run = _run(fake, clock, tmp_path, on_bot=creds)
    tries = [round(t / 1000.0 - a) for name, t in fake.calls if name == 'initialize']
    assert len(tries) == 4 and tries[1] - tries[0] == 5 and tries[2] - tries[1] == 10 and tries[3] - tries[2] == 30
    _same_trade(fake, reference)
    events = [e['event'] for e in run.events]
    assert not set(OUTSIDE) & set(events)
    assert events.count('RECONNECT_FAILED') == 1 and events.count('TERMINAL_RECONNECTED') == 1
    back = next(e['details'] for e in run.events if e['event'] == 'TERMINAL_RECONNECTED')
    assert back['attempt'] == 4 and back['failed_attempts'] == 3 and back['outage_s'] == pytest.approx(49, abs=1)


@pytest.mark.slow
def test_a_gap_through_every_backstop_ends_the_trade_as_closed_outside_the_bot(tmp_path):
    """The price gaps 5 N down while the trade holds its four legs (the bot cannot act in between): the broker's
    backstops close the four legs at the gap price; the bot ends the trade as closed outside it, sends no close of
    its own and takes no new entry on the day's used orders."""
    fake, clock = _market(_long_trip())
    i = int((fake.t_ms >= (START + 1600) * 1000).argmax())          # after the fourth leg (1435 s), before the stop
    fake.bid[i:] -= 5 * LV['n']
    fake.ask[i:] -= 5 * LV['n']
    books = []
    run = _run(fake, clock, tmp_path, books=books)
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    assert len(by_broker) == 4 and {d.time_msc for d in by_broker} == {int(fake.t_ms[i])}
    assert len(_opens(fake)) == 4 and not _closes(fake) and not fake.positions
    events = [e['event'] for e in run.events]
    assert events.count('TURTLE_CLOSED_OUTSIDE') == 1 and 'CLOSE_BUY' not in events
    assert books[-1]['side'] == 0 and books[-1]['armed'] is False and books[-1]['last_exit_time'] is not None


def _backstops(ref):
    """The broker-side backstop (request sl) of each of the long trip's four legs, oldest first."""
    sl = [o['sl'] for o in _opens(ref)]
    assert len(sl) == 4 and sl == sorted(sl)            # a later leg's backstop is nearer (the stop only rises)
    return sl


@pytest.mark.slow
def test_a_gap_through_the_newest_legs_backstop_ends_the_trade_at_its_stop(reference, tmp_path):
    """The price gaps to between the fourth leg's backstop and the third's and stays there (finding 3 of the
    re-review, checked): the broker closes the fourth leg; on its next poll the bot finds the price beyond the
    trade's stop -- a leg's backstop always lies beyond it -- and closes the other three at once, at its own stop."""
    sl = _backstops(reference)
    fake, clock = _market(_long_trip())
    i = int((fake.t_ms >= (START + 1600) * 1000).argmax())          # after the fourth leg (1435 s), before the stop
    shift = fake.bid[i] - (sl[3] + sl[2]) / 2.0
    fake.bid[i:] -= shift
    fake.ask[i:] -= shift
    books = []
    run = _run(fake, clock, tmp_path, books=books)
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    fourth = [d for d in fake.deals if d.entry == 0][3].position_id
    assert len(by_broker) == 1 and by_broker[0].position_id == fourth and by_broker[0].time_msc == fake.t_ms[i]
    closes = _closes(fake)
    assert len(closes) == 3 and len({c['_t_ms'] for c in closes}) == 1 and closes[0]['_t_ms'] <= fake.t_ms[i] + 1500
    assert fourth not in {c['position'] for c in closes} and len(_opens(fake)) == 4 and not fake.positions
    events = [e for e in run.events if e['event'] in ('TURTLE_LEG_CLOSED_OUTSIDE', 'CLOSE_BUY', 'TURTLE_CLOSED_OUTSIDE')]
    assert [e['event'] for e in events] == ['TURTLE_LEG_CLOSED_OUTSIDE', 'CLOSE_BUY']
    assert events[0]['details']['tickets'] == [fourth] and events[1]['details']['positions_closed'] == 3
    assert books[-1]['side'] == 0 and books[-1]['armed'] is False


@pytest.mark.slow
def test_a_backstop_that_closes_a_leg_while_the_terminal_is_down_ends_the_trade(reference, tmp_path):
    """The terminal is gone for 8 s; meanwhile one tick spikes through the fourth leg's backstop and the price comes
    back above the trade's stop. Connected again, the bot finds three legs, and the deal history shows the fourth
    closed beyond the trade's stop: the stop was passed while the bot could not look, so the other three are closed
    at once (before: they were kept, the stop 600 s away, as after a leg closed by hand inside the stop)."""
    sl = _backstops(reference)
    fake, clock = _market(_long_trip())
    a = START + 1590.0
    i = int((fake.t_ms >= (a + 4.0) * 1000).argmax())
    spike = (sl[3] + sl[2]) / 2.0
    fake.bid[i], fake.ask[i] = spike, spike + (fake.ask[i] - fake.bid[i])
    fake.down(a, a + 8.0)

    def creds(bot, n):
        bot.credentials = dict(CREDS)
    run = _run(fake, clock, tmp_path, on_bot=creds)
    by_broker = [d for d in fake.deals if d.reason == fake.DEAL_REASON_SL]
    fourth = [d for d in fake.deals if d.entry == 0][3].position_id
    assert len(by_broker) == 1 and by_broker[0].position_id == fourth and by_broker[0].time_msc == fake.t_ms[i]
    closes = _closes(fake)
    assert len(closes) == 3 and len({c['_t_ms'] for c in closes}) == 1 and closes[0]['_t_ms'] <= (a + 20.0) * 1000
    assert len(_opens(fake)) == 4 and not fake.positions                    # no add in place of the fourth leg
    leg = next(e['details'] for e in run.events if e['event'] == 'TURTLE_LEG_CLOSED_OUTSIDE')
    assert leg['tickets'] == [fourth] and leg['beyond_stop'] is True
    close = next(e['details'] for e in run.events if e['event'] == 'CLOSE_BUY')
    assert close['reason'] == 'stop_passed_outside' and close['positions_closed'] == 3


def test_where_a_leg_closed_outside_the_bot_is_read_from_the_deal_history(mods):
    """True: closed at or beyond the trade's stop; False: closed inside it; None: the history does not show it (the
    bot then closes the other legs too: it cannot tell the stop was not passed)."""
    fake, clock = _market(_long_trip())
    m = mods(fake=fake, clock=clock, **TURTLE)
    bot = F.make_bot(m, fake, SYMBOL, F.Run())
    now = clock.time()
    bid, ask = fake.quote()
    inside = fake.add_position(0, 0.01, bid + 500.0, now - 600, magic=MAGIC)
    beyond = fake.add_position(0, 0.01, bid + 900.0, now - 300, magic=MAGIC)
    fake.close_by_broker(inside)
    fake.close_by_broker(beyond)
    stop = bid + 0.5                                                         # the bid now is just below it
    assert bot._turtle_closed_beyond_stop([inside], 1, bid - 1.0, now - 600, now) is False
    assert bot._turtle_closed_beyond_stop([inside, beyond], 1, stop, now - 600, now) is True
    assert bot._turtle_closed_beyond_stop([inside], -1, bid - 1.0, now - 600, now) is True    # a short's stop
    assert bot._turtle_closed_beyond_stop([inside, 12345], 1, bid - 1.0, now - 600, now) is None   # not all there
    fake.history_none = True
    assert bot._turtle_closed_beyond_stop([inside], 1, bid - 1.0, now - 600, now) is None
