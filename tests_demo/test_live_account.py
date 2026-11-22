"""
The bot trades one account only: the real, hedging account of its credentials. Another program attached to the
terminal (the other bot of the account, an old bot, the owner) may log it into another account at any time, so:
  * initialize_mt5 accepts only the account of the credentials (the number and the server), and only if it is a real
    and a hedging account; it logs in only on a terminal that holds no account (test_terminal_in_use.py);
  * the account is compared in ONE way everywhere (_same_account): the number as a whole number -- also when the
    credentials file has it as text -- and the server without spaces around it, letter case aside;
  * every poll, the read right after the positions and every order_send read account_info() first, in this order:
    the account of the credentials, a real account, a hedging account. Anything else -> nothing is synced, decided
    or sent (opens AND closes: they would reach another account), an ERROR event, until the account is back;
  * a bot without loaded credentials has no account: it refuses every poll and every order. It never takes the
    first account it sees as its own (the forward-test code did, for its replays);
  * what leaves the bot -- events, the facts kept for the trace -- carries the account's tail (...5678), never the
    number.
"""
import json

import pytest

from conftest import (NO_LADDER, ROOT, SCALED, F, booked_outside, deals_of, market, quiet_window, recording_states,
                      run_bot)
from conftest import differs, found

OWN = (F.ACCOUNT_LOGIN, F.ACCOUNT_SERVER)
TAIL = '...' + str(F.ACCOUNT_LOGIN)[-4:]
OTHER_REAL = 87654321               # another real account on the same server (an old bot's)
OLD_DEMO = (99, 'Fake-Demo')        # an account of the forward test


def _bot(mods, seconds=200, **ov):
    fake, clock = market(seconds)
    m = mods(fake=fake, clock=clock, **ov)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    return m, fake, bot, run


def _no_number_in(*things):
    """No account number in what left the bot (the tail only)."""
    text = json.dumps(things, default=str)
    return str(F.ACCOUNT_LOGIN) not in text and str(OTHER_REAL) not in text


# ───────────────────────────── at the start ─────────────────────────────

@pytest.mark.parametrize('logged_in, trade_mode, margin_mode, needle', [
    (True, 'REAL', 'RETAIL_HEDGING', None),                             # the terminal holds it already: no login
    (False, 'REAL', 'RETAIL_HEDGING', None),                            # no account yet: the bot logs in
    (True, 'DEMO', 'RETAIL_HEDGING', 'is not a real account'),          # the right number and server, a demo account
    (False, 'CONTEST', 'RETAIL_HEDGING', 'is not a real account'),
    (True, 'REAL', 'RETAIL_NETTING', 'is not a hedging account'),
    (True, 'REAL', 'EXCHANGE', 'is not a hedging account'),
])
def test_initialize_accepts_only_the_real_hedging_account_of_the_credentials(mods, capsys, logged_in, trade_mode,
                                                                             margin_mode, needle):
    m, fake, bot, run = _bot(mods)
    bot.mt5_initialized, bot.position_helper = False, None
    fake.logged_in = logged_in
    fake.trade_mode = getattr(fake, 'ACCOUNT_TRADE_MODE_' + trade_mode)
    fake.margin_mode = getattr(fake, 'ACCOUNT_MARGIN_MODE_' + margin_mode)
    ok = bot.initialize_mt5()
    names = [c[0] for c in fake.calls]
    login = [] if logged_in else ['login']               # a login only on a terminal without an account
    if needle is None:
        assert ok and bot.mt5_initialized and names == ['initialize'] + login
        assert (fake.account_login, fake.server) == OWN
        assert bot.position_helper.order_guard == bot._order_guard        # every order behind the guard
        assert bot._init_problem is None
    else:
        assert not ok and not bot.mt5_initialized
        assert names == ['initialize'] + login + ['shutdown'] and bot.position_helper is None
        assert needle in capsys.readouterr().out and needle in bot._init_problem and TAIL in bot._init_problem
    assert _no_number_in(bot._boot_lines, bot._init_problem)


def test_a_login_that_lands_on_another_account_is_refused(mods, capsys):
    """The terminal held no account; between the bot's login and its account read another process logged it into
    another real account: refused (not the account of the credentials), nothing initialised."""
    m, fake, bot, run = _bot(mods)
    bot.mt5_initialized, bot.position_helper = False, None
    fake.logged_in = False
    login = fake.login

    def raced(**k):
        login(**k)
        fake.account_login = OTHER_REAL
        return True
    fake.login = raced
    assert bot.initialize_mt5() is False and not bot.mt5_initialized and bot.position_helper is None
    out = capsys.readouterr().out
    assert f"not this bot's account {TAIL}" in out and '...4321' in out


def test_the_bot_logs_in_with_the_number_as_a_whole_number(mods):
    """The credentials file may have the account number as text ("12345678"): the terminal is given the whole
    number (it refuses text), with the server as normalised."""
    m, fake, bot, run = _bot(mods)
    bot.mt5_initialized, bot.position_helper = False, None
    bot.credentials = F.account_credentials(fake, login_id=f' {F.ACCOUNT_LOGIN} ', server=f' {F.ACCOUNT_SERVER} ')
    fake.logged_in = False
    seen = {}
    login = fake.login

    def spy(**k):
        seen.update(k)
        return login(**k)
    fake.login = spy
    assert bot.initialize_mt5() is True
    assert seen['login'] == F.ACCOUNT_LOGIN and type(seen['login']) is int and seen['server'] == F.ACCOUNT_SERVER
    assert seen['password'] == F.CREDS['login_pass']


# ───────────────────────────── one way to compare the account ─────────────────────────────

@pytest.mark.parametrize('login_id, server', [
    (F.ACCOUNT_LOGIN, F.ACCOUNT_SERVER),
    (str(F.ACCOUNT_LOGIN), F.ACCOUNT_SERVER),                   # the number as text in the credentials file
    (F.ACCOUNT_LOGIN, F.ACCOUNT_SERVER.upper()),                # the server in another letter case
    (f' {F.ACCOUNT_LOGIN}', f'  {F.ACCOUNT_SERVER.lower()} '),
])
def test_the_same_account_with_a_text_login_and_a_server_in_another_case(mods, login_id, server):
    """One comparison at the start, on every poll and before every order: a bot whose file spells the account
    another way starts AND keeps trading (two different comparisons would start it and then refuse every poll and
    every close)."""
    m, fake, bot, run = _bot(mods)
    bot.credentials = F.account_credentials(login_id=login_id, server=server)
    acct = fake.account_info()
    assert bot._same_account(acct) is True
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5() is True and [c[0] for c in fake.calls] == ['initialize']        # no login
    assert bot._poll_guard('XAUUSDm') and bot._account_problem() is None
    h = bot.position_helper
    assert bot._order_done(h.buy('XAUUSDm', 0.01)) and h.close_by_type('XAUUSDm', 0)['closed_count'] == 1
    fake.server = f' {F.ACCOUNT_SERVER.swapcase()} '            # ... and as the terminal spells it
    assert bot._same_account(fake.account_info()) is True and bot._poll_guard('XAUUSDm')
    assert not [e for e in run.events if e['tag'] == 'ERROR']


def test_what_is_not_the_same_account(mods):
    import types
    m, fake, bot, run = _bot(mods)
    same = bot._same_account
    ok = dict(login=F.ACCOUNT_LOGIN, server=F.ACCOUNT_SERVER)
    assert same(types.SimpleNamespace(**ok)) is True
    assert same(types.SimpleNamespace(**dict(ok, login=str(F.ACCOUNT_LOGIN)))) is True      # (a terminal that says text)
    for other in (dict(ok, login=OTHER_REAL),                   # another number
                  dict(ok, server='Fake-Real2'),                # the same number on another server: another account
                  dict(ok, server=''), dict(ok, server=None),   # a field the terminal does not fill
                  dict(ok, login=0), dict(ok, login=None), dict(ok, login='x'),
                  dict(login=F.ACCOUNT_LOGIN), dict(server=F.ACCOUNT_SERVER), {}):       # a field it does not report
        assert same(types.SimpleNamespace(**other)) is False, other
    assert same(None) is False


# ───────────────────────────── no account without credentials ─────────────────────────────

def test_a_bot_without_credentials_refuses_every_poll_and_every_order(mods, capsys):
    """No "take the first account seen": on a perfectly good real account a bot that was given no credentials decides
    nothing and sends nothing -- not on the first poll, not later, not a close -- and attaches to no terminal."""
    m, fake, bot, run = _bot(mods)
    bot.credentials = None
    h = bot.position_helper
    for _ in range(5):
        assert not bot._poll_guard('XAUUSDm')
        assert h.buy('XAUUSDm', 0.01) is None and h.sell('XAUUSDm', 0.01) is None
        fake.clock.sleep(1)
    fake.add_position(0, 0.01, 2000.0, fake.clock.time() - 60, magic=m.constants.MAGIC)     # its own, from before
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 0 and res['failed_count'] == 1 and fake.orders == [] and len(fake.positions) == 1
    assert bot._login is None and bot._account_bad and 'no usable account details' in bot._account_bad
    ev = [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED']
    assert len(ev) == 1 and ev[0]['tag'] == 'ERROR' and ev[0]['details']['own_login_tail'] is None
    bot.mt5_initialized, bot.position_helper = False, None
    assert bot.initialize_mt5() is False and fake.calls == []           # refused before any terminal call
    assert 'Refused before attaching to any terminal' in capsys.readouterr().out
    # with its credentials it trades at once (nothing was remembered against it)
    bot.credentials = F.account_credentials(fake)
    assert bot.initialize_mt5() is True and bot._poll_guard('XAUUSDm')
    assert run.events[-1]['event'] == 'ACCOUNT_OK'


def test_a_replay_without_credentials_sends_nothing(tmp_path):
    """The whole loop: a market on which the bot trades (the same replay with credentials opens baskets) and a bot
    whose credentials were taken away: no poll decides, no order."""
    fake0, clock0 = market(600, seed=5)
    ref = run_bot(fake0, clock0, overrides=SCALED, state_dir=tmp_path / 'ref')
    assert not ref.errors and len(fake0.orders) >= 2

    def no_credentials(bot, n):
        bot.credentials = None
    fake, clock = market(600, seed=5)
    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path / 'run', on_new_bot=no_credentials)
    assert fake.orders == [] and fake.deals == [] and run.polls == []
    assert [e['event'] for e in run.events] == ['ACCOUNT_REFUSED']
    assert len(run.errors) == 1 and 'not trading' in run.errors[0]


def test_no_code_adopts_an_account(mods):
    """The bot keeps no "login it found": the reference is the credentials, and nothing else can become it."""
    m, fake, bot, run = _bot(mods)
    assert not hasattr(bot, '_account_login') and not found((ROOT / 'app.py').read_text(encoding='utf-8'), '_account_login')
    bot.credentials = None
    for _ in range(3):
        bot._account_problem()
    assert bot._login is None and bot.credentials is None


# ───────────────────────────── every poll, every order ─────────────────────────────

def test_no_order_is_sent_while_the_terminal_holds_another_account(mods):
    m, fake, bot, run = _bot(mods)
    assert bot._poll_guard('XAUUSDm')                        # the first poll: the account of the credentials
    h = bot.position_helper
    assert h.order_guard == bot._order_guard
    assert bot._order_done(h.buy('XAUUSDm', 0.01)) and len(fake.orders) == 1
    fake.account_login = OTHER_REAL                          # another real account on the same server
    assert h.buy('XAUUSDm', 0.01) is None and h.sell('XAUUSDm', 0.01) is None
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 0 and res['failed_count'] == 1
    assert len(fake.orders) == 1 and len(fake.positions) == 1  # nothing reached the terminal
    ev = [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED']
    assert len(ev) == 1 and ev[0]['tag'] == 'ERROR'          # one event for the problem, not one per order
    problem = ev[0]['details']['problem']
    assert problem == (f"MetaTrader 5 is logged into account ...4321 on {F.ACCOUNT_SERVER}, not this bot's account "
                       f"{TAIL} on {F.ACCOUNT_SERVER}")
    assert ev[0]['details']['own_login_tail'] == TAIL and ev[0]['details']['request']['symbol'] == 'XAUUSDm'
    assert not bot._poll_guard('XAUUSDm')                    # and the polls decide nothing

    def last_problem():
        return [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED'][-1]['details']['problem']
    fake.account_login, fake.server = OWN[0], 'Fake-Real2'   # the same number on another server: another account
    assert h.buy('XAUUSDm', 0.01) is None and not bot._poll_guard('XAUUSDm')
    assert "not this bot's account" in last_problem() and 'Fake-Real2' in last_problem()
    fake.server, fake.trade_mode = OWN[1], fake.ACCOUNT_TRADE_MODE_DEMO        # its number and server, a demo account
    assert h.buy('XAUUSDm', 0.01) is None and not bot._poll_guard('XAUUSDm')
    assert f'account {TAIL} is not a real account' in last_problem() and 'reports it as demo' in last_problem()
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_CONTEST
    assert not bot._poll_guard('XAUUSDm') and 'reports it as contest' in last_problem()
    fake.trade_mode, fake.margin_mode = fake.ACCOUNT_TRADE_MODE_REAL, fake.ACCOUNT_MARGIN_MODE_RETAIL_NETTING
    assert h.sell('XAUUSDm', 0.01) is None and not bot._poll_guard('XAUUSDm')     # the margin mode on every poll too
    assert f'account {TAIL} is not a hedging account' in last_problem()
    assert len(fake.orders) == 1 and len(fake.positions) == 1
    fake.margin_mode = fake.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING                  # the bot's account is back
    assert bot._poll_guard('XAUUSDm') and run.events[-1]['event'] == 'ACCOUNT_OK'
    assert run.events[-1]['details']['login_tail'] == TAIL
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 1 and not fake.positions and len(fake.orders) == 2
    assert _no_number_in(run.events)


def test_the_guard_checks_in_one_order(mods):
    """The terminal answers and is connected; the account of the credentials; a real account; a hedging account.
    The first that fails is the problem named (an account that is another one is not also called a demo account)."""
    m, fake, bot, run = _bot(mods)
    fake.account_login, fake.server = OLD_DEMO
    fake.trade_mode, fake.margin_mode = fake.ACCOUNT_TRADE_MODE_DEMO, fake.ACCOUNT_MARGIN_MODE_RETAIL_NETTING
    fake.connected = False
    assert not bot._poll_guard('XAUUSDm') and bot._guard_why[0] == 'terminal' and bot._account_bad is None
    fake.connected = True
    assert not bot._poll_guard('XAUUSDm') and bot._guard_why[0] == 'account'
    assert "not this bot's account" in bot._account_bad and 'real account' not in bot._account_bad
    fake.account_login, fake.server = OWN
    assert not bot._poll_guard('XAUUSDm') and 'is not a real account' in bot._account_bad
    assert 'hedging' not in bot._account_bad
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_REAL
    assert not bot._poll_guard('XAUUSDm') and 'is not a hedging account' in bot._account_bad
    fake.margin_mode = fake.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
    assert bot._poll_guard('XAUUSDm') and bot._account_bad is None


def test_the_facts_kept_for_the_trace_have_the_tail_not_the_number(mods):
    """bot._acct (what the terminal said last about its account) and bot._terminal (about itself): set where the
    terminal is read anyway, also on a poll that is refused."""
    m, fake, bot, run = _bot(mods)
    assert bot._acct is None and bot._terminal is None
    assert bot._poll_guard('XAUUSDm')
    assert bot._acct == {'login_tail': TAIL, 'server': F.ACCOUNT_SERVER, 'currency': 'USD', 'leverage': fake.leverage,
                         'trade_allowed': True, 'trade_expert': True, 'trade_mode': fake.ACCOUNT_TRADE_MODE_REAL,
                         'margin_mode': fake.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING}
    assert bot._terminal == {'build': fake.build, 'ping_ms': round(fake.ping_last / 1000.0, 1), 'trade_allowed': True,
                             'tradeapi_disabled': False, 'connected': True}
    fake.account_login, fake.currency, fake.trade_expert = OTHER_REAL, 'EUR', False
    fake.terminal_trade_allowed, fake.tradeapi_disabled = False, True
    assert not bot._poll_guard('XAUUSDm')
    assert (bot._acct['login_tail'], bot._acct['currency'], bot._acct['trade_expert']) == ('...4321', 'EUR', False)
    assert (bot._terminal['trade_allowed'], bot._terminal['tradeapi_disabled']) == (False, True)
    assert _no_number_in(bot._acct, bot._terminal)
    fake.connected = False
    assert not bot._poll_guard('XAUUSDm') and bot._terminal['connected'] is False


# ───────────────────────────── in the loop ─────────────────────────────

@pytest.fixture(scope='module')
def switch_reference(tmp_path_factory):
    fake0, clock0 = market(1800, seed=21)
    ref = run_bot(fake0, clock0, overrides=NO_LADDER, state_dir=tmp_path_factory.mktemp('switch_ref'))
    assert not ref.errors, ref.errors[:3]
    return fake0, quiet_window(ref, fake0, 60)


@pytest.mark.slow
@pytest.mark.parametrize('lands', ['before_the_poll', 'between_the_account_check_and_the_positions_read'])
def test_a_switch_to_another_account_mid_basket_changes_nothing(tmp_path, switch_reference, lands):
    """An old bot logs the shared terminal into its own real account for a minute while this bot holds a basket; that
    account shows none of this bot's positions. Nothing is booked as closed outside the bot, nothing is sent, and
    when this bot's account is back it takes the same decisions and fills as without the switch -- also when the
    switch lands after the poll's account check, just before its positions read (that poll would read the other
    account's empty positions and book the basket as closed outside the bot, then rebuild it): the account is read
    again right after the positions."""
    fake0, t0 = switch_reference
    fake, clock = market(1800, seed=21)
    stash = {}

    def to_other(f):
        stash['positions'], f.positions = f.positions, []
        f.account_login = OTHER_REAL                    # real, hedging, the same server: only the number differs

    def back(f):
        f.positions = stash['positions']
        f.account_login = F.ACCOUNT_LOGIN
    if lands == 'before_the_poll':
        fake.at(t0 + 0.5, to_other)                     # the poll's first call (terminal_info) already sees it
    else:
        fake.on_call('positions_get', t0 + 0.5, to_other)
    fake.at(t0 + 60.5, back)
    saved = []
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run', on_new_bot=recording_states(saved))
    assert saved and not booked_outside(saved)     # (unguarded: a phantom 'closed_outside', then a rebuilt basket)
    assert not differs(deals_of(fake), deals_of(fake0))
    assert not any((t0 + 0.5) * 1000 <= o['_t_ms'] <= (t0 + 60.5) * 1000 for o in fake.orders)
    assert not any((t0 + 0.5) * 1000 < p['t'] < (t0 + 60.5) * 1000 for p in run.polls)   # no poll decided
    events = [e['event'] for e in run.events]
    assert events.count('ACCOUNT_REFUSED') == 1 and events.count('ACCOUNT_OK') == 1
    refused = [e for e in run.events if e['event'] == 'ACCOUNT_REFUSED'][0]
    assert refused['tag'] == 'ERROR' and "not this bot's account" in refused['details']['problem']
    assert len(run.errors) == 1 and 'not trading' in run.errors[0]          # the one WARNING line
    assert _no_number_in(run.events, run.errors)


@pytest.mark.slow
def test_a_switch_inside_the_close_decision_books_nothing(tmp_path, switch_reference):
    """Another program logs the terminal into another account (here an old demo account) after the poll's account
    re-read, just before the close reads the positions again, so close_by_type finds none of this bot's positions
    (closed 0, failed 0). Checked, and safe: nothing is booked (no last close, nothing closed outside the bot or
    rebuilt), nothing is sent, and the close is decided again when this bot's account is back."""
    fake0, _ = switch_reference
    t_close = next(o['_t_ms'] for o in fake0.orders if 'position' in o) / 1000.0     # the reference's first close
    fake, clock = market(1800, seed=21)
    stash, switched, saved = {}, [], []

    def to_other(f):
        stash['positions'], f.positions = f.positions, []
        (f.account_login, f.server), f.trade_mode = OLD_DEMO, f.ACCOUNT_TRADE_MODE_DEMO

    def back(f):
        f.positions = stash['positions']
        (f.account_login, f.server), f.trade_mode = OWN, f.ACCOUNT_TRADE_MODE_REAL

    def on_new_bot(bot, n):
        recording_states(saved)(bot, n)
        close = bot.position_helper.close_by_type

        def close_by_type(symbol, pos_type):
            if not switched:                                # the switch lands inside the close decision
                switched.append(clock.time())
                to_other(fake)
                fake.at(clock.time() + 60, back)
            return close(symbol, pos_type)
        bot.position_helper.close_by_type = close_by_type
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run', on_new_bot=on_new_bot)
    assert switched and switched[0] == pytest.approx(t_close, abs=0.01)
    ok = next(e['t'] for e in run.events if e['event'] == 'ACCOUNT_OK') / 1000.0
    closes = [e for e in run.events if e['event'] in ('CLOSE_BUY', 'CLOSE_SELL')]
    assert closes[0]['details']['positions_closed'] == 0 and closes[0]['details']['realised_pnl'] is None
    assert closes[1]['t'] / 1000.0 == pytest.approx(ok, abs=0.5) and closes[1]['details']['positions_closed'] >= 1
    booked = [s['last_close']['time'] for s in saved if s.get('last_close')]
    assert booked and min(booked) >= ok - 0.5               # nothing booked while the basket was still open
    assert saved and not booked_outside(saved)
    assert not [o for o in fake.orders if t_close * 1000 < o['_t_ms'] < (ok - 0.5) * 1000]
