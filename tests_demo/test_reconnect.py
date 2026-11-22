"""
The bot connects to the terminal again after it was restarted or the connection to it was lost (finding 4 of
the demo review: every call answered None for ever). Every poll checks terminal_info() first; a poll without
the terminal decides and sends nothing; after 5 such polls in a row the bot calls mt5.shutdown() and
initialize_mt5() again (with the account checks: the real, hedging account of its credentials), and while that
fails tries again after 5, 10, 30, then every 60 s. It never ends the process: a bot that holds trades keeps trying.
(The launcher, which starts app.py again 30 s after it exits: test_launchers.py.)

A long outage does not fill the 200-entry strategy log (finding 4 of the re-review: 4 hours down wrote 243
RECONNECT_FAILED events): RECONNECT_FAILED is logged for each reason (the terminal's last_error aside) when it is
first seen, then at most every 15 minutes for that reason (fix D of the third round: the limit remembered only the
last reason, so two alternating reasons were logged on every attempt); TERMINAL_RECONNECTED reports the attempts and
the outage's length.
"""
import pytest

from conftest import NO_LADDER, F, booked_outside, deals_of, market, quiet_window, recording_states, run_bot
from conftest import differs, found

OTHER = 87654321              # another real account on the same server (an old bot's)
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]


def _tries(fake, t0):
    """Seconds after t0 of every initialize() the bot made."""
    return [round(t / 1000.0 - t0, 1) for name, t in fake.calls if name == 'initialize']


def test_the_reconnects_back_off_5_10_30_then_every_60_s(mods):
    fake, clock = market(600)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    t0 = clock.time()
    fake.down(t0, t0 + 10_000)                                  # the terminal does not come back
    for _ in range(300):                                        # one poll a second
        assert not bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    assert _tries(fake, t0) == [4, 9, 19, 49, 109, 169, 229, 289]     # the 5th failed poll, then +5 +10 +30 +60 ...
    failed = [e for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert len(failed) == 1 and failed[0]['details']['attempt'] == 1 and failed[0]['details']['next_in_s'] == 5
    assert failed[0]['tag'] == 'ERROR' and 'initialize failed' in failed[0]['details']['why']   # (the same 7 times more)
    first = [e for e in run.events if e['event'] == 'TERMINAL_ERROR']
    assert len(first) == 1 and 'terminal_info() returned None' in first[0]['details']['problem']


def test_a_long_outage_does_not_fill_the_log(mods):
    """4 hours without the terminal, then it is back: RECONNECT_FAILED on the first failure, then every 15 minutes
    (16 events, not 243, in the 200-entry log), and TERMINAL_RECONNECTED with the number of attempts and how long it
    lasted."""
    fake, clock = market(4 * 3600 + 300)
    m = mods(fake=fake, clock=clock)
    m.app.print = lambda *a, **k: None
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    t0 = clock.time()
    fake.down(t0, t0 + 4 * 3600)
    k = 0
    while not bot._poll_guard('XAUUSDm'):
        clock.sleep(1)
        k += 1
        assert k < 4 * 3600 + 120
    failed = [round(e['t'] / 1000.0 - t0) for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert failed == [4] + [949 + 900 * n for n in range(15)]          # (the attempts at 9, 19, 49, 109 ... not)
    assert len(_tries(fake, t0)) == 244                                # every attempt was made: 243 failed
    back = [e for e in run.events if e['event'] == 'TERMINAL_RECONNECTED']
    assert len(back) == 1 and back[0]['details']['attempt'] == 244 and back[0]['details']['failed_attempts'] == 243
    assert back[0]['details']['outage_s'] == pytest.approx(14449, abs=1)
    assert len(run.events) == 18                                       # TERMINAL_ERROR, 16 x RECONNECT_FAILED, back


def test_a_new_reason_is_logged_at_once(mods):
    """The terminal is back but holds another account: that failure is logged at once (its reason changed), then
    every 15 minutes again."""
    fake, clock = market(1500)
    m = mods(fake=fake, clock=clock)
    m.app.print = lambda *a, **k: None
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    t0 = clock.time()
    fake.down(t0, t0 + 100)
    fake.at(t0 + 99, lambda f: setattr(f, 'account_login', OTHER))
    for _ in range(1400):
        bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    failed = [(round(e['t'] / 1000.0 - t0), e['details']['why'].split(':')[0])
              for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert failed == [(4, 'initialize failed'), (109, 'TERMINAL_IN_USE'), (1009, 'TERMINAL_IN_USE')]


def test_alternating_reasons_do_not_fill_the_log(mods):
    """Fix D of the third review round: a terminal that keeps restarting -- down 60 s, then up 60 s and held by
    another account, for 4 hours -- fails the reconnects with two reasons in turn ('initialize failed',
    TERMINAL_IN_USE). The 15-minute limit remembered only the last reason, so every attempt was logged (240
    RECONNECT_FAILED in 4 hours). Now each reason is logged when it is first seen, then at most every 15 minutes, with
    the failures not logged since; every attempt is still made."""
    fake, clock = market(4 * 3600 + 300)
    m = mods(fake=fake, clock=clock)
    m.app.print = lambda *a, **k: None
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    t0 = clock.time()
    fake.account_login = OTHER
    for k in range(4 * 30):
        fake.down(t0 + k * 120, t0 + k * 120 + 60)
    for _ in range(4 * 3600):
        bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    failed = [e for e in run.events if e['event'] == 'RECONNECT_FAILED']
    by_reason = {}
    for e in failed:
        by_reason.setdefault(e['details']['why'].split(':')[0], []).append(e['t'] / 1000.0 - t0)
    assert sorted(by_reason) == ['TERMINAL_IN_USE', 'initialize failed']
    for times in by_reason.values():
        assert 15 <= len(times) <= 17 and all(b - a >= 900 for a, b in zip(times, times[1:]))
    assert sum(e['details']['not_logged_since'] for e in failed) > 150        # (the failures in between, counted)
    assert len(_tries(fake, t0)) > 200 and len(run.events) < 60               # (before: 256 events)


@pytest.mark.slow
def test_a_terminal_restart_mid_basket_is_ridden_out(tmp_path):
    """The terminal is gone for 45 s while the bot holds a basket. The polls decide nothing, the bot connects again
    after 5 failed polls and then after 5, 10 and 30 s, the fourth attempt finds the terminal back: the same login,
    nothing booked as closed outside the bot, and the same decisions and fills as without the restart."""
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=NO_LADDER, state_dir=tmp_path / 'ref')
    t0 = quiet_window(ref, fake0, 60)

    fake, clock = market(1800, seed=21)
    fake.down(t0 + 0.5, t0 + 45.5)
    saved = []
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run', on_new_bot=recording_states(saved))
    assert _tries(fake, t0) == [5, 10, 20, 50]
    # the terminal came back holding this bot's account: no login (finding 1 of the re-review)
    assert [n for n, t in fake.calls if t >= (t0 + 50) * 1000] == ['shutdown', 'initialize']
    assert saved and not booked_outside(saved)
    assert not differs(deals_of(fake), deals_of(fake0))
    assert not any((t0 + 0.5) * 1000 <= o['_t_ms'] <= (t0 + 50.5) * 1000 for o in fake.orders)
    assert not any((t0 + 0.5) * 1000 < p['t'] < (t0 + 50.5) * 1000 for p in run.polls)
    events = [e['event'] for e in run.events if e['event'].startswith(('TERMINAL', 'RECONNECT'))]
    assert events == ['TERMINAL_ERROR', 'RECONNECT_FAILED', 'TERMINAL_RECONNECTED', 'TERMINAL_OK']   # (one failure
    back = [e for e in run.events if e['event'] == 'TERMINAL_RECONNECTED'][0]['details']           # logged of three)
    assert back['login_tail'] == TAIL and back['attempt'] == 4 and back['failed_attempts'] == 3
    assert back['outage_s'] == pytest.approx(49, abs=1)                  # from the first poll without it


def test_a_reconnect_onto_another_account_is_refused(mods):
    """The terminal comes back holding an account that is not a real one (the number and the server of the
    credentials, but a demo account): initialize_mt5 refuses it, the bot keeps trying -- it never ends the process --
    and trades again only once its real account is back."""
    fake, clock = market(300)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    t0 = clock.time()
    assert bot._poll_guard('XAUUSDm')
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 10, lambda f: setattr(f, 'trade_mode', f.ACCOUNT_TRADE_MODE_DEMO))
    fake.at(t0 + 70, lambda f: setattr(f, 'trade_mode', f.ACCOUNT_TRADE_MODE_REAL))
    ok_at = None
    for k in range(1, 120):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = k
            break
    failed = [e['details']['why'] for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert any('is not a real account' in w for w in failed)    # the attempt at 50 s finds the demo account
    assert _tries(fake, t0) == [5, 10, 20, 50, 110]             # (the back-off goes on) ... 110 s: real again
    assert ok_at == 111 and bot._account_bad is None and bot.mt5_initialized
    assert not found(str(run.events), str(F.ACCOUNT_LOGIN))          # the events carry the tail, never the number


def test_not_connected_to_the_trade_server_only_waits(mods):
    """terminal_info().connected False: the polls decide nothing, but the bot does not log the shared terminal in
    again (the terminal reconnects by itself)."""
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    fake.connected = False
    for _ in range(30):
        assert not bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    assert fake.calls == []
    ev = [e for e in run.events if e['event'] == 'TERMINAL_ERROR']
    assert len(ev) == 1 and 'not connected to the trade server' in ev[0]['details']['problem']
    fake.connected = True
    assert bot._poll_guard('XAUUSDm')
