"""
The bot trades on this branch's demo account only (finding 1 of the demo review). Another process attached to the
terminal (a live bot, the bot of another slot) may log it into another account at any time, so:
  * initialize_mt5 refuses an account that is not a demo account, not a hedging account, or not the login of
    the credentials, and remembers the login (it logs in only on a terminal that holds no account:
    test_terminal_in_use.py);
  * the command line and load_credentials refuse mode 'live' (before the credentials file is opened);
  * every poll and every order_send read account_info() first: another account -> nothing is synced, decided
    or sent, an ERROR event, until the demo account is back.
"""
import io
import json
import sys

import pytest

from conftest import NO_LADDER, F, booked_outside, deals_of, market, quiet_window, recording_states, run_bot

CREDS = {'terminal_path': r'C:\fake\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}


def _bot(mods, seconds=60):
    fake, clock = market(seconds)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS)
    return m, fake, bot, run


@pytest.mark.parametrize('logged_in, trade_mode, margin_mode, needle', [
    (True, 0, 2, None),                                 # the terminal holds it already: demo, hedging, this login
    (False, 0, 2, None),                                # no account yet: the bot logs in
    (True, 2, 2, 'is not a demo account'),              # a real account
    (False, 1, 2, 'is not a demo account'),             # a contest account
    (True, 0, 0, 'is not a hedging account'),           # netting
])
def test_initialize_accepts_only_the_demo_hedging_login(mods, capsys, logged_in, trade_mode, margin_mode, needle):
    m, fake, bot, run = _bot(mods)
    bot.mt5_initialized, bot.position_helper = False, None
    fake.logged_in, fake.trade_mode, fake.margin_mode = logged_in, trade_mode, margin_mode
    ok = bot.initialize_mt5()
    names = [c[0] for c in fake.calls]
    login = [] if logged_in else ['login']               # a login only on a terminal without an account
    if needle is None:
        assert ok and bot.mt5_initialized and bot._account_login == 1 and names == ['initialize'] + login
        assert bot.position_helper.order_guard == bot._order_guard        # every order behind the guard
    else:
        assert not ok and not bot.mt5_initialized and bot._account_login is None
        assert names == ['initialize'] + login + ['shutdown'] and bot.position_helper is None
        assert needle in capsys.readouterr().out


def test_a_login_that_lands_on_another_account_is_refused(mods, capsys):
    """The terminal held no account; between the bot's login and its account read another process logged it into
    account 7: refused (the login of the credentials), nothing initialised."""
    m, fake, bot, run = _bot(mods)
    bot.mt5_initialized, bot.position_helper = False, None
    fake.logged_in = False
    login = fake.login

    def raced(**k):
        login(**k)
        fake.account_login = 7
        return True
    fake.login = raced
    assert bot.initialize_mt5() is False and not bot.mt5_initialized and bot.position_helper is None
    assert 'not the login of the credentials' in capsys.readouterr().out


def test_load_credentials_refuses_live_before_opening_the_file(mods):
    m = mods()
    opened = []

    def no_open(*a, **k):
        opened.append(a)
        raise AssertionError('the credentials file must not be opened')
    m.app.open = no_open
    bot = m.app.MT5TradingBot(mode='live', target_symbol='XAUUSDm')
    assert bot.load_credentials() is False and bot.credentials is None and not opened


def test_load_credentials_still_reads_the_demo_block(mods):
    """(a stand-in file: the branch's own mt5_credentials.json is never read by the tests)"""
    m = mods()
    text = json.dumps({'demo': CREDS})
    m.app.open = lambda path, *a, **k: io.StringIO(text) if str(path).endswith('mt5_credentials.json') else None
    bot = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')
    assert bot.load_credentials() is True and bot.credentials == CREDS


def test_the_command_line_refuses_live(mods, monkeypatch, capsys):
    m = mods()
    made = []
    monkeypatch.setattr(m.app, 'MT5TradingBot', lambda *a, **k: made.append((a, k)))
    monkeypatch.setattr(sys, 'argv', ['app.py', 'live', '--symbol', 'XAUUSDm'])
    with pytest.raises(SystemExit) as e:
        m.app.main()
    assert e.value.code == 2 and not made                   # refused before a bot exists
    assert 'demo only' in capsys.readouterr().err


def test_no_order_is_sent_while_the_terminal_holds_another_account(mods):
    m, fake, bot, run = _bot(mods)
    assert bot._poll_guard('XAUUSDm')                        # the first poll: demo login 1 is this bot's account
    h = bot.position_helper
    assert h.order_guard == bot._order_guard
    assert bot._order_done(h.buy('XAUUSDm', 0.01)) and len(fake.orders) == 1
    fake.account_login = 2                                   # another (demo) account
    assert h.buy('XAUUSDm', 0.01) is None and h.sell('XAUUSDm', 0.01) is None
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 0 and res['failed_count'] == 1
    assert len(fake.orders) == 1 and len(fake.positions) == 1  # nothing reached the terminal
    ev = [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED']
    assert len(ev) == 1 and ev[0]['tag'] == 'ERROR'          # one event for the problem, not one per order
    assert 'account 2' in ev[0]['details']['problem'] and ev[0]['details']['demo_login'] == 1
    assert not bot._poll_guard('XAUUSDm')                    # and the polls decide nothing
    fake.account_login, fake.trade_mode = 1, fake.ACCOUNT_TRADE_MODE_REAL      # the same login on a real server
    assert h.buy('XAUUSDm', 0.01) is None and not bot._poll_guard('XAUUSDm')
    assert 'not a demo account' in [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED'][-1]['details']['problem']
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_DEMO           # the demo account is back
    assert bot._poll_guard('XAUUSDm') and run.events[-1]['event'] == 'ACCOUNT_OK'
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 1 and not fake.positions and len(fake.orders) == 2


@pytest.mark.slow
def test_a_switch_to_another_account_mid_basket_changes_nothing(tmp_path):
    """A live bot logs the shared terminal into the real account for a minute while this bot holds a basket; that
    account shows none of this bot's positions. Nothing is booked as closed outside the bot, nothing is sent, and
    when the demo account is back the bot takes the same decisions and fills as without the switch."""
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=NO_LADDER, state_dir=tmp_path / 'ref')
    assert not ref.errors, ref.errors[:3]
    t0 = quiet_window(ref, fake0, 60)

    fake, clock = market(1800, seed=21)
    stash = {}

    def to_live(f):
        stash['positions'], f.positions = f.positions, []
        f.account_login, f.trade_mode = 99, f.ACCOUNT_TRADE_MODE_REAL

    def back(f):
        f.positions = stash['positions']
        f.account_login, f.trade_mode = 1, f.ACCOUNT_TRADE_MODE_DEMO
    fake.at(t0 + 0.5, to_live)
    fake.at(t0 + 60.5, back)
    saved = []
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run', on_new_bot=recording_states(saved))
    assert saved and not booked_outside(saved)     # (unguarded: a phantom 'closed_outside', then a rebuilt basket)
    assert deals_of(fake) == deals_of(fake0)
    assert not any((t0 + 0.5) * 1000 <= o['_t_ms'] <= (t0 + 60.5) * 1000 for o in fake.orders)
    assert not any((t0 + 0.5) * 1000 < p['t'] < (t0 + 60.5) * 1000 for p in run.polls)   # no poll decided
    events = [e['event'] for e in run.events]
    assert events.count('ACCOUNT_REFUSED') == 1 and events.count('ACCOUNT_OK') == 1
    refused = [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED'][0]
    assert refused['tag'] == 'ERROR' and 'not a demo account' in refused['details']['problem']
    assert len(run.errors) == 1 and 'not trading' in run.errors[0]          # the one WARNING line
