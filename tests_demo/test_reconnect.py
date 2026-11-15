"""
The bot connects to the terminal again after it was restarted or the connection to it was lost (finding 4 of
the demo review: every call answered None for ever). Every poll checks terminal_info() first; a poll without
the terminal decides and sends nothing; after 5 such polls in a row the bot calls mt5.shutdown() and
initialize_mt5() again (with the demo-account checks), and while that fails tries again after 5, 10, 30, then
every 60 s. The launchers start app.py again 30 s after it exits (demo only).
"""
import re

import pytest

from conftest import (NO_LADDER, F, ROOT, booked_outside, deals_of, market, quiet_window, recording_states,
                      run_bot)

CREDS = {'terminal_path': r'C:\fake\terminal64.exe', 'login_id': 1, 'login_pass': 'not-a-password',
         'server': 'Fake-Demo'}


def _with_credentials(*hooks):
    """on_new_bot: the bot gets stand-in credentials (initialize_mt5 needs them), then the other hooks run."""
    def on_new_bot(bot, n):
        bot.credentials = dict(CREDS)
        for h in hooks:
            h(bot, n)
    return on_new_bot


def _tries(fake, t0):
    """Seconds after t0 of every initialize() the bot made."""
    return [round(t / 1000.0 - t0, 1) for name, t in fake.calls if name == 'initialize']


def test_the_reconnects_back_off_5_10_30_then_every_60_s(mods):
    fake, clock = market(600)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS)
    t0 = clock.time()
    fake.down(t0, t0 + 10_000)                                  # the terminal does not come back
    for _ in range(300):                                        # one poll a second
        assert not bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    assert _tries(fake, t0) == [4, 9, 19, 49, 109, 169, 229, 289]     # the 5th failed poll, then +5 +10 +30 +60 ...
    failed = [e for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert [e['details']['next_in_s'] for e in failed] == [5, 10, 30, 60, 60, 60, 60, 60]
    assert all(e['tag'] == 'ERROR' and 'initialize failed' in e['details']['why'] for e in failed)
    first = [e for e in run.events if e['event'] == 'TERMINAL_ERROR']
    assert len(first) == 1 and 'terminal_info() returned None' in first[0]['details']['problem']


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
    run = run_bot(fake, clock, overrides=NO_LADDER, state_dir=tmp_path / 'run',
                  on_new_bot=_with_credentials(recording_states(saved)))
    assert _tries(fake, t0) == [5, 10, 20, 50]
    # the terminal came back holding this bot's account: no login (finding 1 of the re-review)
    assert [n for n, t in fake.calls if t >= (t0 + 50) * 1000] == ['shutdown', 'initialize']
    assert saved and not booked_outside(saved)
    assert deals_of(fake) == deals_of(fake0)
    assert not any((t0 + 0.5) * 1000 <= o['_t_ms'] <= (t0 + 50.5) * 1000 for o in fake.orders)
    assert not any((t0 + 0.5) * 1000 < p['t'] < (t0 + 50.5) * 1000 for p in run.polls)
    events = [e['event'] for e in run.events if e['event'].startswith(('TERMINAL', 'RECONNECT'))]
    assert events == ['TERMINAL_ERROR', 'RECONNECT_FAILED', 'RECONNECT_FAILED', 'RECONNECT_FAILED',
                      'TERMINAL_RECONNECTED', 'TERMINAL_OK']
    assert [e for e in run.events if e['event'] == 'TERMINAL_RECONNECTED'][0]['details']['login'] == 1


def test_a_reconnect_onto_another_account_is_refused(mods):
    """The terminal comes back logged into the real account: initialize_mt5 refuses it (finding 1), the bot keeps
    trying and trades again only once the demo account is back."""
    fake, clock = market(300)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS)
    t0 = clock.time()
    assert bot._poll_guard('XAUUSDm')
    fake.down(t0 + 0.5, t0 + 30.5)
    fake.at(t0 + 10, lambda f: setattr(f, 'trade_mode', f.ACCOUNT_TRADE_MODE_REAL))
    fake.at(t0 + 70, lambda f: setattr(f, 'trade_mode', f.ACCOUNT_TRADE_MODE_DEMO))
    ok_at = None
    for k in range(1, 120):
        clock.sleep(1)
        if bot._poll_guard('XAUUSDm'):
            ok_at = k
            break
    failed = [e['details']['why'] for e in run.events if e['event'] == 'RECONNECT_FAILED']
    assert any('not a demo account' in w for w in failed)       # the attempt at 50 s finds the real account
    assert _tries(fake, t0) == [5, 10, 20, 50, 110]             # (the back-off goes on) ... 110 s: demo again
    assert ok_at == 111 and bot._account_login == 1


def test_not_connected_to_the_trade_server_only_waits(mods):
    """terminal_info().connected False: the polls decide nothing, but the bot does not log the shared terminal in
    again (the terminal reconnects by itself)."""
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    bot.credentials = dict(CREDS)
    fake.connected = False
    for _ in range(30):
        assert not bot._poll_guard('XAUUSDm')
        clock.sleep(1)
    assert fake.calls == []
    ev = [e for e in run.events if e['event'] == 'TERMINAL_ERROR']
    assert len(ev) == 1 and 'not connected to the trade server' in ev[0]['details']['problem']
    fake.connected = True
    assert bot._poll_guard('XAUUSDm')


@pytest.mark.parametrize('name', sorted(p.name for p in ROOT.glob('start_*.bat') if p.name != 'start_dashboard.bat'))
def test_the_launchers_start_app_py_again_30_s_after_it_exits_on_demo(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    lines = [line.strip() for line in text.splitlines()]
    refuse = lines.index('if /i "%MODE%"=="live" (')
    assert lines[refuse + 2] == 'exit /b 1'                      # live is refused before anything runs
    label = lines.index(':run_bot')
    run = next(i for i, line in enumerate(lines) if 'app.py %MODE%' in line)
    back = lines.index('goto run_bot')
    assert refuse < label < run < back
    loop = lines[run:back]
    assert 'if /i not "%MODE%"=="demo" goto ' in ' '.join(loop)  # the loop is for demo only
    assert any(re.fullmatch(r'ping -n 31 127\.0\.0\.1 > nul', line) for line in loop)     # a 30 s pause
