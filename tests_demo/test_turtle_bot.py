"""
The Turtle in the bot (STRATEGY = 'turtle'): app.py's loop on the fake terminal. A crafted BTC-like market
(contract size 1, 0.01 lot = $0.01 per $1) with 200 days of history and a scripted M15 vote: the entry at the
breakout level with the vote, the adds every 0.5N from the actual fills, the one stop, every leg closed at it, no
re-entry the same day, the orders (magic, comment, no broker SL / TP, unit x 0.01 lot), the closed-bar reads, the
unit from the virtual balance, the brake, the book in the state file and its rebuild after a restart, the design
checks and the dashboard.
"""
import importlib.util
import json
import os
import re
import sys

import numpy as np
import pytest

from conftest import COMMENT, DEFAULTS, F, MAGIC, ROOT, START, run_bot

_spec = importlib.util.spec_from_file_location('bot_turtle', ROOT / 'turtle.py')
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

SYMBOL = 'BTCUSDm'
SPREAD = 10.0
TURTLE = {'STRATEGY': 'turtle', 'TURTLE_SYSTEM': 2, 'DESIGN_NAME': 'btc_turtle_s2', 'TURTLE_MIN_D1_BARS': 100}


def _warm(days=200):
    """One bar every 15 minutes for `days` days before START: a 30-day swing of +-500 and a daily one of +-300
    around 60,000 (so the 55-day channel is about 59,200 .. 60,800 and N about 600)."""
    n = days * 96
    t = (int(START) - 900 * np.arange(n, 0, -1)).astype(np.int64)
    x = (t - t[0]) / 86400.0
    p = np.round(60000 + 500 * np.sin(2 * np.pi * x / 30.0) + 300 * np.sin(2 * np.pi * x), 2)
    return {'t': t, 'o': p, 'h': p + 5, 'l': p - 5, 'c': p, 'n': np.ones(n, np.int64)}


WARM = _warm()


def _levels(system=2, warm=WARM):
    """The levels the bot must find at START: the closed D1 bars of the fake terminal (resampled like it)."""
    d1 = F.resample(warm, 86400)
    d1 = {k: v[-600:] for k, v in d1.items()}
    closed = d1['t'] + 86400 <= START
    rows = T.daily_rows(d1['o'][closed], d1['h'][closed], d1['l'][closed], d1['c'][closed], system=system)
    return T.row_levels(rows, d1['t'][closed], int(closed.sum()) - 1)


LV = _levels()


def _market(segments, balance=2000.0, restarts=()):
    """Ticks every second from START + 1 s: the bid along `segments` [(from, to, seconds)], ask = bid + SPREAD."""
    bid = np.round(np.concatenate([np.linspace(a, b, s, endpoint=False) for a, b, s in segments]), 2)
    k = len(bid)
    t_ms = (int(START) * 1000 + 1000 + 1000 * np.arange(k)).astype(np.int64)
    clock = F.FakeClock(START + 1.5, START + k, restarts_s=[START + r for r in restarts])
    fake = F.FakeMT5(SYMBOL, t_ms, bid, bid + SPREAD, clock, warm_m1=WARM, contract_size=1.0, balance=balance)
    return fake, clock


def _long_trip():
    """Up through the buy level, on by 1.6N (three adds), down through the stop, back above the level."""
    b, n = LV['buy'], LV['n']
    return [(b - 200, b + 50, 600), (b + 50, b + 1.6 * n, 900), (b + 1.6 * n, b - 1.0 * n, 900), (b - 1.0 * n, b + 100, 600)]


def _short_trip():
    s, n = LV['sell'], LV['n']
    return [(s + 200, s - 50, 600), (s - 50, s - 1.6 * n, 900), (s - 1.6 * n, s + 1.0 * n, 900), (s + 1.0 * n, s - 100, 600)]


class Vote:
    """A scripted M15 vote in place of turtle.closed_bar_vote: value(t) at the terminal time t of the call; it
    records what it was given."""

    def __init__(self, fake, value):
        self.fake, self.value, self.calls = fake, value, []

    def __call__(self, closes, indicator, **kw):
        t = self.fake.t_ms[self.fake.ptr] / 1000.0
        self.calls.append({'t': t, 'last_close': float(closes[-1]), 'n': len(closes)})
        v = int(self.value(t))
        return v, {'rsi': {'sign': v}, 'macd': {'sign': v}}


def _run(fake, clock, tmp_path, vote=None, overrides=None, books=None, on_bot=None, **kw):
    """Replay the bot with the Turtle design; `books` collects every book saved (a copy, with the time)."""
    vote = vote or Vote(fake, lambda t: 1)

    def on_new_bot(bot, n):
        sys.modules[type(bot).__module__].T.closed_bar_vote = vote
        if books is not None:
            save = bot._save_turtle_state

            def recording(symbol, st):
                books.append(dict(json.loads(json.dumps(st)), _t=clock.time(), _bot=n))
                save(symbol, st)
            bot._save_turtle_state = recording
        if on_bot is not None:
            on_bot(bot, n)

    run = run_bot(fake, clock, overrides={**TURTLE, **(overrides or {})}, symbol=SYMBOL, state_dir=tmp_path,
                  on_new_bot=on_new_bot, **kw)
    run.vote = vote
    return run


def _opens(fake):
    return [o for o in fake.orders if 'position' not in o]


def _closes(fake):
    return [o for o in fake.orders if 'position' in o]


def _deal_ins(fake):
    return [d for d in fake.deals if d.entry == 0]


@pytest.fixture(scope='module')
def long_run(tmp_path_factory):
    fake, clock = _market(_long_trip())
    books = []
    run = _run(fake, clock, tmp_path_factory.mktemp('turtle_long'), books=books)
    run.fake, run.books = fake, books
    run.state_dir = tmp_path_factory.getbasetemp()
    return run


def test_a_long_from_the_breakout_to_the_stop(long_run):
    run, fake = long_run, long_run.fake
    assert not run.errors, run.errors[:3]
    opens, ins = _opens(fake), _deal_ins(fake)
    assert len(opens) == 4 and all(o['type'] == fake.ORDER_TYPE_BUY for o in opens)
    fills = [d.price for d in ins]
    # the entry: the first tick whose ask reached the buy level
    i0 = int(np.flatnonzero(fake.ask >= LV['buy'])[0])
    assert fills[0] == pytest.approx(fake.ask[i0], abs=1.0) and fills[0] >= LV['buy']
    # every add: the first ask at or above the previous ACTUAL fill + 0.5 N (N frozen at the entry)
    for k in (1, 2, 3):
        assert fills[k] >= fills[k - 1] + LV['add_step'] - 1e-9
        assert fills[k] - (fills[k - 1] + LV['add_step']) < 2.0             # taken as soon as it was there
    # one stop for all legs: 2N below the newest fill (tighter than the 20-day low), every leg closed at once
    stop = fills[3] - LV['stop_dist']
    assert stop > LV['trail_long']
    closes = _closes(fake)
    assert len(closes) == 4 and len({c['_t_ms'] for c in closes}) == 1
    t_exit = closes[0]['_t_ms']
    i_exit = int(np.searchsorted(fake.t_ms, t_exit, side='right')) - 1
    assert fake.bid[i_exit] <= stop < fake.bid[np.flatnonzero(fake.t_ms < t_exit - 1500)[-1]]
    ev = [e for e in run.events if e['event'] == 'CLOSE_BUY']
    assert len(ev) == 1 and ev[0]['details']['stop'] == pytest.approx(stop) and ev[0]['details']['stop_origin'] == '2N'
    assert ev[0]['details']['reason'] == 'stop'
    # back above the buy level the same day: the D1 bar's orders are used, no second entry
    assert fake.ask[i_exit:].max() >= LV['buy'] and not fake.positions
    assert all(o['_t_ms'] < t_exit for o in opens)


def test_the_orders_carry_the_magic_the_comment_and_a_backstop_but_no_target(long_run):
    """Every leg goes out with a broker-side backstop 1 N beyond the trade's stop at its fill (never moved) and no
    broker target; the stop that closed the trade is the bot's own, always nearer (the broker closed nothing)."""
    fake = long_run.fake
    for o in fake.orders:
        assert o['magic'] == MAGIC and o['comment'] == COMMENT
    fills = [d.price for d in _deal_ins(fake)]
    for k, o in enumerate(_opens(fake)):
        assert o['volume'] == pytest.approx(0.01)                              # unit 1 at $2,000, every leg
        stop = max(max(fills[:k + 1]) - LV['stop_dist'], LV['trail_long'])    # the trade's stop with this leg
        assert o['sl'] == pytest.approx(round(stop - LV['n'], 3)) and o['tp'] == 0.0
    assert not [d for d in fake.deals if d.reason in (fake.DEAL_REASON_SL, fake.DEAL_REASON_TP)]
    ev = [e['details'] for e in long_run.events if e['event'] in ('BUY_EXECUTED', 'BUY_MORE_EXECUTED')]
    assert [e['backstop_sl'] for e in ev] == [o['sl'] for o in _opens(fake)]


def test_the_book_is_saved_with_n_frozen_at_the_entry(long_run):
    books = [b for b in long_run.books if b['side'] == 1]
    assert books
    assert {b['n_entry'] for b in books} == {LV['n']} and {b['entry_row'] for b in books} == {LV['bar_time']}
    assert {b['units'] for b in books} == {1}
    assert max(len(b['legs']) for b in books) == 4
    last = long_run.books[-1]
    assert last['side'] == 0 and last['armed'] is False and last['row'] == LV['bar_time']
    assert last['last_exit_time'] is not None


def test_the_vote_reads_closed_m15_bars_only(long_run):
    """Every vote was computed on the M15 bars closed by then: the last close it got is the close of the bar that
    ended at the last M15 boundary, not the price of the bar forming."""
    fake, calls = long_run.fake, long_run.vote.calls
    assert len(calls) >= 3
    m15 = fake.bars['M15']
    t_all = m15.t[:m15.n]
    for c in calls:
        b = int(c['t'] // 900) * 900 - 900                     # the bar that closed at the last boundary
        i = int(np.searchsorted(t_all, b))
        assert t_all[i] == b and c['last_close'] == pytest.approx(m15.c[i]), c
        assert c['n'] == min(DEFAULTS['TURTLE_VOTE_BARS'], i + 1)


def test_a_short_mirrors_it(tmp_path):
    fake, clock = _market(_short_trip())
    run = _run(fake, clock, tmp_path, vote=Vote(fake, lambda t: -1))
    assert not run.errors
    opens = _opens(fake)
    fills = [d.price for d in _deal_ins(fake)]
    assert len(opens) == 4 and all(o['type'] == fake.ORDER_TYPE_SELL for o in opens)
    assert fills[0] <= LV['sell']
    for k in (1, 2, 3):
        assert fills[k] <= fills[k - 1] - LV['add_step'] + 1e-9
    closes = _closes(fake)
    assert len(closes) == 4 and len({c['_t_ms'] for c in closes}) == 1
    i_exit = int(np.searchsorted(fake.t_ms, closes[0]['_t_ms'], side='right')) - 1
    assert fake.ask[i_exit] >= min(fills) + LV['stop_dist']                  # a short's stop is on the ask
    assert not fake.positions


def test_the_vote_gates_the_entry_and_a_late_vote_enters_at_the_market(tmp_path):
    """The price is through the buy level from about 08:07 while the vote is 0; the 08:15 close turns it to +1:
    the entry is on the poll that reads that close (2 s after it), at the market, above the level (the backtest's
    vote-delayed fill at the next M1 open)."""
    b = LV['buy']
    fake, clock = _market([(b - 200, b + 50, 600), (b + 50, b + 60, 1200)])
    run = _run(fake, clock, tmp_path, vote=Vote(fake, lambda t: 1 if t >= START + 900 else 0))
    opens = _opens(fake)
    assert opens, 'no entry'
    assert int(np.flatnonzero(fake.ask >= b)[0]) < 600                       # beyond the level well before 08:15
    assert START * 1000 + 900_000 <= opens[0]['_t_ms'] <= START * 1000 + 905_000
    assert _deal_ins(fake)[0].price > b + 30


def test_no_vote_no_entry(tmp_path):
    b = LV['buy']
    fake, clock = _market([(b - 200, b + 300, 1200)])
    run = _run(fake, clock, tmp_path, vote=Vote(fake, lambda t: -1))        # the vote is against the breakout
    assert not _opens(fake) and not run.errors


def test_the_unit_comes_from_the_virtual_balance_and_every_leg_has_it(tmp_path):
    fake, clock = _market(_long_trip())
    fake.add_deal(position_id=7, type_=1, entry=1, volume=0.01, price=60000.0, profit=600.0, time_s=START - 3600,
                  magic=MAGIC)                                                # $2,000 + $600 since the start date
    fake.add_deal(position_id=8, type_=1, entry=1, volume=0.01, price=60000.0, profit=5000.0, time_s=START - 3600,
                  magic=MAGIC + 1)                                            # another bot's deal: not counted
    run = _run(fake, clock, tmp_path)
    opens = _opens(fake)
    assert len(opens) == 4 and {o['volume'] for o in opens} == {0.02}
    entry = [e for e in run.events if e['event'] == 'BUY_EXECUTED'][0]['details']
    assert entry['units'] == 2 and entry['balance'] == pytest.approx(2600.0)


def test_the_brake_stops_new_entries(tmp_path):
    fake, clock = _market(_long_trip()[:2])

    def braked(bot, n):
        bot.symbols_config['brake'] = 1
    run = _run(fake, clock, tmp_path, on_bot=braked)
    assert not _opens(fake)
    assert any(e['event'] == 'TURTLE_NOTE' and 'Brake' in e['details'].get('note', '') for e in run.events)


def _restart_run(tmp_path, drop_state):
    """The long trip with a restart after the second add; the state file kept or removed."""
    fake0, clock0 = _market(_long_trip())
    books0 = []
    _run(fake0, clock0, tmp_path / 'ref', books=books0)
    t_add2 = _opens(fake0)[2]['_t_ms'] / 1000.0
    at = t_add2 + 30.5 - START
    fake, clock = _market(_long_trip(), restarts=[at])
    books = []

    def on_bot(bot, n):
        if n > 0 and drop_state:
            os.remove(bot._turtle_state_path(SYMBOL))
    run = _run(fake, clock, tmp_path / 'run', books=books, on_bot=on_bot)
    assert run.restarts == 1 and not run.errors, run.errors[:3]
    return fake0, books0, fake, books, run


@pytest.mark.parametrize('drop_state', [False, True])
def test_a_restart_mid_trade_keeps_the_trade(tmp_path, drop_state):
    """With the state file the book is read back; without it the trade is rebuilt from the positions (N at the
    entry from the D1 bars, the unit from the first leg's volume, the stop from the fills): the same trade
    either way, and it ends as the run without a restart."""
    fake0, books0, fake, books, run = _restart_run(tmp_path, drop_state)
    before = [b for b in books if b['_bot'] == 0 and b['side'] == 1][-1]
    after = [b for b in books if b['_bot'] == 1 and b['side'] == 1]
    assert len(before['legs']) == 3 and after
    if drop_state:
        assert any(e['event'] == 'TURTLE_REBUILT' for e in run.events)
        assert len(after[0]['legs']) == 3                     # rebuilt and saved on its first poll
    else:
        assert not any(e['event'] == 'TURTLE_REBUILT' for e in run.events)
    keys = ['side', 'units', 'n_entry', 'stop_dist', 'add_step', 'trail_best', 'entry_row', 'row', 'armed']
    if len(after[0]['legs']) == 3:
        keys.append('stop')
    for k in keys:
        assert after[0][k] == (pytest.approx(before[k]) if isinstance(before[k], float) else before[k]), k
    assert len(_opens(fake)) == len(_opens(fake0)) == 4
    assert [d.price for d in _deal_ins(fake)] == pytest.approx([d.price for d in _deal_ins(fake0)], abs=1e-6)
    assert len(_closes(fake)) == 4 and not fake.positions
    assert _closes(fake)[0]['_t_ms'] == _closes(fake0)[0]['_t_ms']


def test_a_flat_restart_without_the_state_file_does_not_take_the_used_orders_again(tmp_path):
    """Entered and stopped out today, restarted flat without the state file: the deal history shows today's entry,
    so the D1 bar's orders stay used even with the price back through the level."""
    trip = _long_trip()
    at = sum(s for _, _, s in trip[:3]) + 60.5                 # after the stop-out, before the price is back up

    def on_bot(bot, n):
        if n > 0:
            os.remove(bot._turtle_state_path(SYMBOL))
    fake, clock = _market(trip, restarts=[at])
    books = []
    run = _run(fake, clock, tmp_path, on_bot=on_bot, books=books)
    assert run.restarts == 1 and not run.errors, run.errors[:3]
    assert len(_closes(fake)) == 4 and _closes(fake)[0]['_t_ms'] < (START + at) * 1000
    assert len(_opens(fake)) == 4 and not fake.positions      # no second entry after the restart
    assert fake.ask[np.searchsorted(fake.t_ms, (START + at) * 1000):].max() >= LV['buy']
    after = [b for b in books if b['_bot'] == 1]
    assert after and after[0]['armed'] is False and after[0]['last_exit_time'] is not None


def _close_by_hand(fake, at, newest_only):
    """From terminal time `at` on, before the bot's next read: this bot's newest position (or all of them) closed
    from the terminal, outside the bot (a deal without its magic number)."""
    orig = fake.positions_get
    done = []

    def positions_get(symbol=None, **k):
        if not done and fake.clock.time() >= at and fake.positions:
            done.append(True)
            b, a = fake.quote()
            for p in ([fake.positions[-1]] if newest_only else list(fake.positions)):
                price = b if p['type'] == 0 else a
                profit = fake._pos_profit(p, price, price)
                fake.balance += profit
                fake._deal(p, 1, p['volume'], price, profit, 0, 'by hand', fake.clock.now_ms)
                fake.positions.remove(p)
        return orig(symbol=symbol, **k)
    fake.positions_get = positions_get
    return done


def _after_second_add(tmp_path):
    fake0, clock0 = _market(_long_trip())
    _run(fake0, clock0, tmp_path / 'ref')
    return _opens(fake0)[2]['_t_ms'] / 1000.0 + 60.0


def test_a_leg_closed_outside_the_bot_keeps_the_stop(tmp_path):
    at = _after_second_add(tmp_path)
    fake, clock = _market(_long_trip())
    done = _close_by_hand(fake, at, newest_only=True)
    books = []
    run = _run(fake, clock, tmp_path / 'run', books=books)
    assert done and not run.errors, run.errors[:3]
    ev = [e for e in run.events if e['event'] == 'TURTLE_LEG_CLOSED_OUTSIDE']
    assert len(ev) == 1 and ev[0]['details']['legs'] == 2 and ev[0]['details']['stop_origin'] == 'kept'
    stops = [b['stop'] for b in books if b['side'] == 1]
    assert stops == sorted(stops)                                          # a long's stop never went down
    assert len(_opens(fake)) == 5                                          # the price was past the next add level
    assert not fake.positions and len(_closes(fake)) == 4                  # four legs open at the stop


def test_a_trade_closed_outside_the_bot_ends_the_book(tmp_path):
    at = _after_second_add(tmp_path)
    fake, clock = _market(_long_trip())
    done = _close_by_hand(fake, at, newest_only=False)
    books = []
    run = _run(fake, clock, tmp_path / 'run', books=books)
    assert done and not run.errors, run.errors[:3]
    assert any(e['event'] == 'TURTLE_CLOSED_OUTSIDE' for e in run.events)
    assert len(_opens(fake)) == 3 and not _closes(fake)                    # no re-entry on the day's used orders
    assert books[-1]['side'] == 0 and books[-1]['armed'] is False


def test_a_refused_close_is_retried_until_every_leg_is_out(tmp_path):
    """The terminal refuses the close of one leg for 20 s: the bot keeps closing on the next polls (whatever the
    price does by then) until the trade is out, and books it once."""
    fake0, clock0 = _market(_long_trip())
    _run(fake0, clock0, tmp_path / 'ref')
    t_exit = _closes(fake0)[0]['_t_ms'] / 1000.0
    fake, clock = _market(_long_trip())
    orig = fake.positions_get

    def positions_get(symbol=None, **k):
        now = fake.clock.time()
        if t_exit - 5 <= now < t_exit + 20 and fake.positions:
            fake.fail_close_tickets = {fake.positions[0]['ticket']}
        else:
            fake.fail_close_tickets = set()
        return orig(symbol=symbol, **k)
    fake.positions_get = positions_get
    books = []
    run = _run(fake, clock, tmp_path / 'run', books=books)
    assert not fake.positions and len(_opens(fake)) == 4
    ev = [e['details'] for e in run.events if e['event'] == 'CLOSE_BUY']
    assert ev[0]['failed'] == 1 and ev[0]['positions_closed'] == 3 and ev[0]['reason'] == 'stop'
    assert all(d['reason'] == 'close_retry' for d in ev[1:]) and ev[-1]['failed'] == 0 and len(ev) > 2
    assert not any(e['event'].startswith('TURTLE_') and 'OUTSIDE' in e['event'] for e in run.events)
    assert books[-1]['side'] == 0 and books[-1]['closing'] is False


def test_turtle_designs_are_accepted_and_bad_ones_refused(mods):
    m = mods(**TURTLE)
    assert m.app.design_problems() == []
    assert 'System 2' in m.app.design_summary() and 'magic' in m.app.design_summary()
    assert 'System 1' in mods(**dict(TURTLE, TURTLE_SYSTEM=1)).app.design_summary()
    for ov, needle in (({'TURTLE_SYSTEM': 3}, 'TURTLE_SYSTEM'), ({'TURTLE_MAX_LEGS': 0}, 'TURTLE_MAX_LEGS'),
                       ({'TURTLE_VOTE_TF': 'M7'}, 'TURTLE_VOTE_TF'), ({'TURTLE_D1_BARS': 50}, 'TURTLE_D1_BARS'),
                       ({'TURTLE_STOP_N': 0}, 'TURTLE_STOP_N'), ({'TURTLE_VOTE_BARS': 10}, 'TURTLE_VOTE_BARS'),
                       ({'TURTLE_BACKSTOP_N': 0}, 'TURTLE_BACKSTOP_N')):
        problems = mods(**dict(TURTLE, **ov)).app.design_problems()
        assert any(needle in p for p in problems), (ov, problems)


def test_the_turtle_constants_are_the_backtests():
    assert (DEFAULTS['TURTLE_N_LEN'], DEFAULTS['TURTLE_STOP_N'], DEFAULTS['TURTLE_ADD_N'], DEFAULTS['TURTLE_MAX_LEGS'],
            DEFAULTS['TURTLE_TICK'], DEFAULTS['TURTLE_VOTE_TF']) == (20, 2.0, 0.5, 4, 0.01, 'M15')
    assert DEFAULTS['STRATEGY'] == 'basket'                     # the defaults stay the live bot


def test_the_two_turtle_example_blocks(mods):
    text = (ROOT / 'constants.py').read_text(encoding='utf-8')
    blocks = dict(re.findall(r"# ── (BTC Turtle System [12] \+ bot votes) ──\n((?:# [A-Z_].*\n)+)", text))
    assert set(blocks) == {'BTC Turtle System 1 + bot votes', 'BTC Turtle System 2 + bot votes'}
    for name, body in blocks.items():
        ns = {}
        exec('\n'.join(line[2:] for line in body.splitlines()), ns)
        assert ns['STRATEGY'] == 'turtle' and ns['TURTLE_SYSTEM'] == int(name.split()[3])
        m = mods(**{k: v for k, v in ns.items() if k.isupper()})
        assert m.app.design_problems() == []


def test_the_dashboard_draws_the_turtle(mods):
    pytest.importorskip('dash')
    sys.path.insert(0, str(ROOT))
    try:
        sys.modules.pop('dashboard', None)
        mods(**TURTLE)
        import dashboard
        flat = {'strategy': 'turtle', 'design': 'btc_turtle_s2', 'entry_direction': 'BUY', 'open_score': 2,
                'fc_score': 2, 'slopes': {'M15': {'rsi': {'sign': 1}, 'macd': {'sign': 1}}},
                'turtle': {'system': 2, 'buy_level': 60804.32, 'sell_level': 59195.68, 'n': 613.09, 'armed': True,
                           'vote': 1, 'side': None, 'legs': 0, 'max_legs': 4}}
        text = str(dashboard.build_slope_panel(SYMBOL, flat))
        assert 'Turtle S2' in text and 'buy ≥ 60,804.32' in text and 'M15 vote ▲' in text
        trade = dict(flat, turtle=dict(flat['turtle'], side='BUY', legs=3, stop=60192.56, stop_origin='2N',
                                       next_add=61725.29))
        text = str(dashboard.build_slope_panel(SYMBOL, trade))
        assert 'BUY 3/4 legs · stop 60,192.56 (2N) · next add 61,725.29' in text
    finally:
        sys.modules.pop('dashboard', None)
        sys.path.remove(str(ROOT))
