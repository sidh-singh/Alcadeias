"""
The demo review's terminal and account fixes in the Turtle's own loop (STRATEGY = 'turtle'): every poll first
checks that the terminal answers and holds this bot's demo account (findings 1 and 4), and a positions read that
fails skips the poll (finding 5) -- the book is never matched with positions that are not this account's or not
known, so an open trade is not ended as "closed outside the bot". Polls in which the reference run decided nothing
are skipped exactly: the trade is the same.
"""
import pytest

from conftest import START
from test_turtle_bot import _closes, _long_trip, _market, _opens, _run

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
def test_another_account_on_the_terminal_mid_trade_changes_nothing(reference, tmp_path):
    """A live bot logs the shared terminal into the real account for a minute: that account shows none of this
    bot's legs. Nothing is synced or sent until the demo account is back, and the trade goes on as it would have."""
    fake, clock = _market(_long_trip())
    stash = {}

    def to_live(f):
        stash['positions'], f.positions = f.positions, []
        f.account_login, f.trade_mode = 99, f.ACCOUNT_TRADE_MODE_REAL

    def back(f):
        f.positions = stash['positions']
        f.account_login, f.trade_mode = 1, f.ACCOUNT_TRADE_MODE_DEMO
    fake.at(START + QUIET[0], to_live)
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
    then after 5, 10 and 30 s; the fourth attempt finds it back, and the trade goes on as it would have."""
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
    assert events.count('RECONNECT_FAILED') == 3 and events.count('TERMINAL_RECONNECTED') == 1
