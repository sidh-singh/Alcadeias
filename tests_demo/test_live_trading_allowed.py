"""
A MetaTrader 5 that lets no program trade: a warning, never a refusal.

Four switches stop every order of a program, and with each of them the bot can neither open nor CLOSE:
  * terminal_info().trade_allowed false        the Algo Trading button of MetaTrader 5 is off;
  * terminal_info().tradeapi_disabled true     the option that blocks trading from Python;
  * account_info().trade_allowed false         the account may not trade (an investor password, the broker);
  * account_info().trade_expert false          the broker does not let programs trade the account.
The bot says so the moment it sees one -- a console line and an event TRADING_NOT_ALLOWED that names which, at the
start and while it runs; TRADING_ALLOWED when it is over -- and goes on exactly as before: the start is not
refused, no poll is skipped, and every order is still sent (a close must still be tried: the switch may be back on
the next second, and an order the terminal refuses is logged as refused). A field the terminal does not report at
all counts as no problem. The trace builds its red banner from the same facts (bot._terminal, bot._acct).
"""
import json

import pytest

from conftest import F, market, stand_in_files, start_job
from conftest import found

SWITCHES = {
    'algo_trading_off': ('terminal_trade_allowed', False, 'Algo Trading is switched off in MetaTrader 5'),
    'python_api_disabled': ('tradeapi_disabled', True, 'MetaTrader 5 blocks trading from Python'),
    'account_trade_disabled': ('account_trade_allowed', False, 'the account may not trade'),
    'account_expert_disabled': ('trade_expert', False, 'the broker does not let programs trade this account'),
}
ORDER = ['algo_trading_off', 'python_api_disabled', 'account_trade_disabled', 'account_expert_disabled']


def _bot(mods, seconds=300):
    fake, clock = market(seconds)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    return m, fake, bot, run


def _events(run):
    return [e for e in run.events if e['event'].startswith('TRADING_')]


@pytest.mark.parametrize('reason', ORDER)
def test_the_start_goes_on_and_says_which_switch_is_off(mods, capsys, reason):
    knob, value, says = SWITCHES[reason]
    m = mods()
    setattr(m.fake, knob, value)
    stand_in_files(m)
    events = []
    bot, reached = start_job(m, events=events)
    assert reached and bot._owner_verdict is None                   # never a refusal
    assert [e['event'] for e in events] == ['TRADING_NOT_ALLOWED'] and events[0]['tag'] == 'ERROR'
    d = events[0]['details']
    assert d['reasons'] == [reason]
    assert d['problem'].startswith(f'MetaTrader 5 does not let this bot trade: {says}')
    assert d['problem'].endswith('Until that is changed the bot can neither open nor close: its open trades have only '
                                 'their stop at the broker.')
    assert f"WARNING: {d['problem']}" in capsys.readouterr().out
    assert bot._trade_blocked == [reason]


def test_nothing_is_said_while_every_switch_is_on(mods, capsys):
    m = mods()
    stand_in_files(m)
    events = []
    bot, reached = start_job(m, events=events)
    assert reached and events == [] and bot._trade_blocked == []
    assert not found(capsys.readouterr().out, 'does not let this bot trade')


def test_a_switch_that_goes_off_while_the_bot_runs_is_said_once_and_no_poll_is_refused(mods, capsys):
    """Every poll passes the guard as before; the event comes when it starts, when it changes, and when it is over --
    not once a poll."""
    m, fake, bot, run = _bot(mods)
    for _ in range(5):
        assert bot._poll_guard('XAUUSDm')
        fake.clock.sleep(1)
    assert _events(run) == []
    fake.terminal_trade_allowed = False                             # the owner clicks Algo Trading off
    for _ in range(30):
        assert bot._poll_guard('XAUUSDm')                           # never a refusal
        fake.clock.sleep(1)
    assert [(e['event'], e['details']['reasons']) for e in _events(run)] == [('TRADING_NOT_ALLOWED', ['algo_trading_off'])]
    fake.trade_expert = False                                       # ... and the broker switches programs off too
    for _ in range(5):
        assert bot._poll_guard('XAUUSDm')
        fake.clock.sleep(1)
    assert _events(run)[-1]['details']['reasons'] == ['algo_trading_off', 'account_expert_disabled']
    assert len(_events(run)) == 2
    fake.terminal_trade_allowed, fake.trade_expert = True, True     # both back on
    for _ in range(5):
        assert bot._poll_guard('XAUUSDm')
        fake.clock.sleep(1)
    last = _events(run)[-1]
    assert (last['event'], last['tag'], last['details']['was']) == (
        'TRADING_ALLOWED', 'SIGNAL', ['algo_trading_off', 'account_expert_disabled'])
    assert len(_events(run)) == 3 and bot._trade_blocked == []
    out = capsys.readouterr().out
    assert out.count('WARNING: MetaTrader 5 does not let this bot trade') == 2
    assert out.count('note: MetaTrader 5 lets this bot trade again') == 1
    assert not [e for e in run.events if e['event'] in ('ACCOUNT_REFUSED', 'TERMINAL_ERROR')]


def test_all_four_at_once_are_named_in_one_line_in_a_fixed_order(mods):
    m, fake, bot, run = _bot(mods)
    for knob, value, _ in SWITCHES.values():
        setattr(fake, knob, value)
    assert bot._poll_guard('XAUUSDm')
    (event,) = _events(run)
    assert event['details']['reasons'] == ORDER == bot._trading_not_allowed()
    for _, _, says in SWITCHES.values():
        assert says in event['details']['problem']
    assert '\n' not in event['details']['problem']


def test_every_order_is_still_sent_a_close_too(mods):
    """Exits must still be tried. The warning changes nothing in the order path: the open and the close go to the
    terminal as without it (what the terminal answers is the terminal's)."""
    m, fake, bot, run = _bot(mods)
    fake.terminal_trade_allowed, fake.tradeapi_disabled = False, True
    fake.account_trade_allowed, fake.trade_expert = False, False
    assert bot._poll_guard('XAUUSDm')
    h = bot.position_helper
    assert bot._order_done(h.buy('XAUUSDm', 0.01)) and len(fake.orders) == 1
    result = h.close_by_type('XAUUSDm', 0)
    assert result['closed_count'] == 1 and len(fake.orders) == 2 and not fake.positions
    assert bot._account_problem() is None                           # the account guard does not know these switches


@pytest.mark.parametrize('hidden', [{'trade_allowed'}, {'tradeapi_disabled'}, {'trade_expert'},
                                    {'trade_allowed', 'tradeapi_disabled', 'trade_expert'}])
def test_a_field_the_terminal_does_not_report_counts_as_no_problem(mods, hidden):
    """An older terminal build that has no tradeapi_disabled, a broker that reports no trade_expert: no warning --
    and no exception -- for what cannot be known."""
    m, fake, bot, run = _bot(mods)
    fake.hide = set(hidden)
    fake.terminal_trade_allowed, fake.tradeapi_disabled = False, True       # (would be problems, were they reported)
    fake.account_trade_allowed, fake.trade_expert = False, False
    assert bot._poll_guard('XAUUSDm')
    reasons = bot._trading_not_allowed()
    assert ('algo_trading_off' in reasons) is ('trade_allowed' not in hidden)       # (both trade_allowed fields go)
    assert ('account_trade_disabled' in reasons) is ('trade_allowed' not in hidden)
    assert ('python_api_disabled' in reasons) is ('tradeapi_disabled' not in hidden)
    assert ('account_expert_disabled' in reasons) is ('trade_expert' not in hidden)
    if len(hidden) == 3:
        assert reasons == [] and _events(run) == []


def test_the_reasons_come_from_what_the_guard_has_just_read_no_terminal_call_of_their_own(mods, monkeypatch):
    m, fake, bot, run = _bot(mods)
    fake.trade_expert = False
    assert bot._poll_guard('XAUUSDm')
    calls = []
    for name in ('terminal_info', 'account_info'):
        monkeypatch.setattr(fake, name, lambda *a, _n=name, **k: calls.append(_n))
    assert bot._trading_not_allowed() == ['account_expert_disabled'] and calls == []
    bot._check_trading_allowed('XAUUSDm')
    assert calls == []
    bot._terminal, bot._acct = None, None                           # nothing read yet: nothing to say
    assert bot._trading_not_allowed() == []


def test_the_warning_can_never_fail_a_poll(mods):
    m, fake, bot, run = _bot(mods)
    fake.terminal_trade_allowed = False

    def boom(*a, **k):
        raise RuntimeError('the log cannot be written')
    bot._log_event = boom
    assert bot._poll_guard('XAUUSDm') is True                       # the event failed: the poll goes on
    bot._trading_not_allowed = boom
    assert bot._poll_guard('XAUUSDm') is True


def test_a_reconnect_says_it_again_only_when_it_changed(mods):
    """The helper is new after a reconnect; what the bot knows about the switches is not."""
    m, fake, bot, run = _bot(mods)
    fake.terminal_trade_allowed = False
    assert bot._poll_guard('XAUUSDm')
    t0 = fake.clock.time()
    fake.down(t0 + 0.5, t0 + 20.5)
    for _ in range(120):
        fake.clock.sleep(1)
        if bot._poll_guard('XAUUSDm') and fake.clock.time() > t0 + 21:
            break
    assert bot.mt5_initialized and len(_events(run)) == 1
    assert not found(json.dumps(run.events), str(F.ACCOUNT_LOGIN))
