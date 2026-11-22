"""
Sizing on a real account. Two bots share the account, so each sizes from its SHARE of the account balance:

    sizing balance = round(ACCOUNT_SHARE x account balance, 2)
    units          = max(1, min(unit_max_limit, floor(sizing balance / step_up_balance) + 1))

  * the balance is the account's booked balance (closed trades of both bots, deposits, withdrawals), read with the
    poll's own account read: no deal history is read for the size;
  * the unit is derived only where the forward-test code derived it: the basket loop on every flat poll, the Turtle
    at its entry decision (and, for the figure it shows, while flat). An open basket / Turtle trade keeps the unit
    of its entry whatever the balance does, also across a restart (from its state; without it, from its oldest
    position's volume);
  * while the sizing balance is not known, or not above 0, NO new trade is opened (the forward-test code opened one
    unit): the poll local _open_hold says why. An open trade is still managed and closed;
  * how a trade was sized (account balance, share, sizing balance, step, units) is kept with it: in the basket's
    state, and for the Turtle in its side file beside the book.
The share and the steps are set by each test (no value of the deployment block is written here).
"""
import json
import os

import pytest

import test_turtle_bot as TB
from conftest import MAGIC, NO_LADDER, START, F, baskets, market, run_bot
from conftest import found

KEYS = {'share', 'account_balance', 'sizing_balance', 'step', 'units', 'lot', 'unit_max',
        'next_unit_at_account_balance', 'source', 't'}


def _units(share, balance, step, cap):
    """The rule, written out."""
    return max(1, min(cap, int(round(share * balance, 2) // step) + 1))


def _at(run, a, b=None):
    """The polls decided at terminal second `a` (.. `b`) after START."""
    b = a + 1 if b is None else b
    return [p for p in run.polls if (START + a) * 1000 <= p['t'] < (START + b) * 1000]


def _braked(bot, n):
    bot.symbols_config['brake'] = 1         # no entry: the bot stays flat and shows its unit on every poll


# ───────────────────────────── the pieces ─────────────────────────────

def test_the_sizing_balance_is_the_share_of_the_account_balance(mods):
    m = mods(ACCOUNT_SHARE=0.5)
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    assert bot._sizing_balance({'balance': 1500.0}) == (750.0, 1500.0)
    assert bot._sizing_balance({'balance': 1512.42, 'equity': 9.0}) == (756.21, 1512.42)      # to the cent
    assert bot._sizing_balance({'balance': 0.0}) == (0.0, 0.0)             # known: the caller opens nothing on it
    assert bot._sizing_balance({'balance': -20.0}) == (-10.0, -20.0)
    for unknown in (None, {}, {'equity': 5.0}, {'balance': None}, {'balance': '1500'}, {'balance': float('nan')},
                    {'balance': float('inf')}, {'balance': True}, 1500.0):
        assert bot._sizing_balance(unknown) == (None, None), unknown
    m = mods(ACCOUNT_SHARE=1.0)
    assert F.make_bot(m, m.fake, 'XAUUSDm', F.Run())._sizing_balance({'balance': 1500.0}) == (1500.0, 1500.0)
    m = mods(ACCOUNT_SHARE=0.3)
    assert F.make_bot(m, m.fake, 'XAUUSDm', F.Run())._sizing_balance({'balance': 1000.05}) == (300.01, 1000.05)


@pytest.mark.parametrize('share', [0, -0.5, 1.01, 2, None, 'half', True, float('nan')])
def test_a_share_that_is_none_is_refused_and_sizes_nothing(mods, tmp_path, share):
    """ACCOUNT_SHARE must be above 0 and at most 1: the design check refuses the start, and even past it the
    balance counts as unknown (no entry) rather than as the whole account."""
    m = mods(ACCOUNT_SHARE=share)
    assert any('ACCOUNT_SHARE' in p for p in m.app.design_problems())
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), state_dir=tmp_path)
    assert bot._sizing_balance({'balance': 1500.0}) == (None, None)
    with pytest.raises(ValueError, match='ACCOUNT_SHARE'):
        bot.process_symbol('XAUUSDm')
    assert mods(ACCOUNT_SHARE=1).app.design_problems() == [] and mods(ACCOUNT_SHARE=0.01).app.design_problems() == []


def test_the_sizing_record(mods):
    a = mods(ACCOUNT_SHARE=0.5).app
    rec = a.sizing_record(1512.4, 756.2, 1250, 1, 0.01, 10, 'balance', 123.0)
    assert set(rec) == KEYS
    assert rec == {'share': 0.5, 'account_balance': 1512.4, 'sizing_balance': 756.2, 'step': 1250, 'units': 1,
                   'lot': 0.01, 'unit_max': 10, 'next_unit_at_account_balance': 2500.0, 'source': 'balance', 't': 123.0}
    assert a.sizing_record(9000.0, 4500.0, 1750, 3, 0.01, 10, 'balance')['next_unit_at_account_balance'] == 10500.0
    assert a.sizing_record(9e9, 4.5e9, 1250, 10, 0.01, 10, 'balance')['next_unit_at_account_balance'] is None  # the cap
    assert a.sizing_record(100.0, 50.0, 0, 1, 0.01, 10, 'balance')['next_unit_at_account_balance'] is None     # no step
    assert a.sizing_record(4000.0, 2000.0, 1250, 2, 0.01, 10, 'balance')['lot'] == 0.02
    # an open trade: the record of its entry, or -- taken over from the terminal -- its unit alone
    kept = a.open_trade_sizing(rec, 1, 1250, 0.01, 10)
    assert kept == dict(rec, source='entry')
    for record in (None, {}, dict(rec, units=2)):                   # none, or not this trade's
        got = a.open_trade_sizing(record, 1, 1250, 0.01, 10)
        assert (got['source'], got['units'], got['account_balance'], got['sizing_balance']) == ('positions', 1, None, None)
    assert 'x the account balance' in a.design_summary() and '0.5' in a.design_summary()
    # it is only a record: whatever symbols.json holds, it never raises (a poll must not be lost to it)
    for step, units, mtqty, cap in (('2500', 1, 0.01, 10), (2500, 1, 0.01, '10'), (None, None, None, None),
                                    (0, 1, 0.01, 10), (float('nan'), 2, 0.01, 10), (2500, 'two', 0.01, 10)):
        odd = a.sizing_record(1000.0, 500.0, step, units, mtqty, cap, 'balance')
        assert set(odd) == KEYS and odd['next_unit_at_account_balance'] is None
    odd = a.sizing_record(1000.0, 500.0, 2500, 1, 'x', 10, 'balance')
    assert odd['lot'] is None and odd['next_unit_at_account_balance'] == 5000.0


# ───────────────────────────── the basket loop ─────────────────────────────

@pytest.mark.parametrize('share, step, cap, balances', [
    (0.5, 1250, 10, [1500.0, 2499.98, 2500.0, 2500.02, 4999.98, 5000.0, 7499.99, 24999.0, 25000.0, 90000.0]),
    (0.5, 2500, 3, [1500.0, 4999.98, 5000.0, 9999.98, 10000.0, 60000.0]),
    (1.0, 2500, 10, [2000.0, 2499.99, 2500.0, 5000.0]),             # the whole account (a bot alone on it)
    (0.25, 1750, 10, [1500.0, 6999.96, 7000.0, 14000.0]),
])
def test_units_while_flat_are_the_share_of_the_balance_over_the_step(tmp_path, share, step, cap, balances):
    """The step at the right balances and the cap: a cent under a step is the lower unit, on it the next one."""
    fake, clock = market(10 * len(balances) + 5, balance=balances[0])
    for k, bal in enumerate(balances):
        fake.at(START + 10 * k, lambda f, bal=bal: setattr(f, 'balance', bal))
    run = run_bot(fake, clock, overrides={'ACCOUNT_SHARE': share}, state_dir=tmp_path, step_up=step, max_limit=cap,
                  on_new_bot=_braked)
    assert not run.errors and not fake.orders
    for k, bal in enumerate(balances):
        polls = _at(run, 10 * k + 2, 10 * k + 9)
        want = _units(share, bal, step, cap)
        assert polls and {p['units'] for p in polls} == {want}, (bal, want)
        s = polls[-1]['sizing']
        assert set(s) == KEYS
        assert (s['share'], s['account_balance'], s['sizing_balance']) == (share, bal, round(share * bal, 2))
        assert (s['step'], s['units'], s['unit_max'], s['source']) == (step, want, cap, 'balance')
        assert s['lot'] == pytest.approx(want * 0.01)
        assert s['next_unit_at_account_balance'] == (None if want >= cap else pytest.approx(want * step / share))
    # the checks themselves: the list holds both sides of a step, and the cap
    wants = [_units(share, bal, step, cap) for bal in balances]
    assert wants == sorted(wants) and wants[0] == 1 and len(set(wants)) >= 3 and wants[-1] <= cap


def test_the_unit_follows_deposits_withdrawals_and_the_other_bots_trades(tmp_path):
    """The balance is the ACCOUNT's: a deposit, the other bot's closed trade and a withdrawal move this bot's unit
    on the next flat poll. No deal history is read for it."""
    fake, clock = market(60, balance=2000.0)
    fake.at(START + 10, lambda f: f.add_balance_operation(3000.0))                     # 5,000: half is 2,500
    fake.at(START + 20, lambda f: f.add_deal(900001, 1, 1, 0.05, 2000.0, 5000.0, START + 20, magic=MAGIC + 1))
    fake.at(START + 30, lambda f: f.add_balance_operation(-8500.0))                    # 1,500
    history, cash = [], []
    get = fake.history_deals_get
    fake.history_deals_get = lambda *a, **k: history.append(1) or get(*a, **k)

    def on_new_bot(bot, n):
        _braked(bot, n)
        # (the safety reads the account's balance operations while it checks a change of the balance: its reads,
        # not the size's)
        reads = bot.position_helper.get_cash_deals

        def cash_read(*a, **k):
            cash.append(len(history))
            out = reads(*a, **k)
            history[cash[-1]:] = []
            return out
        bot.position_helper.get_cash_deals = cash_read
    run = run_bot(fake, clock, overrides={'ACCOUNT_SHARE': 0.5}, state_dir=tmp_path, step_up=2500,
                  on_new_bot=on_new_bot)
    assert cash                                                     # (the safety did read them)
    assert not run.errors and not fake.orders
    assert [{p['units'] for p in _at(run, a, a + 8)} for a in (1, 11, 21, 31)] == [{1}, {2}, {3}, {1}]
    assert [_at(run, a)[0]['sizing']['account_balance'] for a in (5, 15, 25, 35)] == [2000.0, 5000.0, 10000.0, 1500.0]
    # the size needs no history read (the forward-test code read the deal history on every flat poll): what is
    # left is the one read of a start without a state file and the trace's own
    assert len(run.polls) >= 55 and len(history) <= 5


@pytest.fixture(scope='module')
def reference(tmp_path_factory):
    """A replay in which the bot opens and closes several one-leg baskets at 1 unit ($2,000, half of it counted)."""
    fake, clock = market(900, seed=5)
    run = run_bot(fake, clock, overrides=dict(NO_LADDER, ACCOUNT_SHARE=0.5), state_dir=tmp_path_factory.mktemp('sz'))
    assert not run.errors, run.errors[:3]
    bs = baskets(fake, magic=MAGIC)
    assert len(bs) >= 3 and all(len(b['legs']) == 1 and b['legs'][0]['vol'] == 0.01 for b in bs)
    second = bs[1]
    assert second['t_close'] - second['t_open'] > 120       # long enough to act in its middle
    return fake, run, [(b['t_open'] - START, b['t_close'] - START) for b in bs]


def test_every_basket_keeps_the_record_of_how_it_was_sized(reference):
    fake, run, spans = reference
    a, b = spans[1]
    inside = _at(run, a + 5, b - 5)
    flat_before = _at(run, a - 5, a - 1)
    assert inside and flat_before and {p['sizing']['source'] for p in flat_before} == {'balance'}
    recs = [p['sizing'] for p in inside]
    assert {r['source'] for r in recs} == {'entry'} and all(r == recs[0] for r in recs)
    assert set(recs[0]) == KEYS and recs[0]['units'] == 1 and recs[0]['share'] == 0.5
    # the balance of the poll that opened it: the start balance and the first basket's result
    entry_balance = round(2000.0 + baskets(fake, magic=MAGIC)[0]['pnl'], 2)
    assert recs[0]['account_balance'] == entry_balance and recs[0]['sizing_balance'] == round(entry_balance / 2, 2)
    assert recs[0]['t'] == pytest.approx(START + a, abs=1.5)


def test_an_open_basket_keeps_its_unit_and_the_next_one_gets_the_new_unit(reference, tmp_path):
    """Flat-only re-derivation: $4,000 arrive while a 1-unit basket is open. It stays a 1-unit basket (its lot, its
    target and stop) until it closes; the next one opens with 2 units."""
    fake0, run0, spans = reference
    a, b = spans[1]
    fake, clock = market(900, seed=5)
    fake.at(START + a + 30, lambda f: f.add_balance_operation(4000.0))
    run = run_bot(fake, clock, overrides=dict(NO_LADDER, ACCOUNT_SHARE=0.5), state_dir=tmp_path)
    assert not run.errors, run.errors[:3]
    bs = baskets(fake, magic=MAGIC)
    assert [(x['t_open'], x['t_close']) for x in bs[:2]] == [(x['t_open'], x['t_close']) for x in baskets(fake0, MAGIC)[:2]]
    assert [x['legs'][0]['vol'] for x in bs[:2]] == [0.01, 0.01] and bs[2]['legs'][0]['vol'] == 0.02
    after = _at(run, a + 35, b - 2)
    assert after and {p['units'] for p in after} == {1} and {p['levels']['units'] for p in after} == {1}
    assert {p['sizing']['source'] for p in after} == {'entry'}
    assert {p['sizing']['account_balance'] for p in after} == {_at(run0, a + 35)[0]['sizing']['account_balance']}
    flat = [p for p in _at(run, b + 2, bs[2]['t_open'] - START - 1) if p['nb'] == 0 and p['ns'] == 0]
    assert flat and {p['units'] for p in flat} == {2} and {p['sizing']['source'] for p in flat} == {'balance'}
    third = _at(run, bs[2]['t_open'] - START + 3)[0]
    assert third['units'] == 2 and third['levels']['units'] == 2 and third['sizing']['source'] == 'entry'
    assert third['sizing']['account_balance'] > 5900


@pytest.mark.slow
@pytest.mark.parametrize('drop_state', [False, True])
def test_a_restart_with_an_open_basket_keeps_its_unit(reference, tmp_path, drop_state):
    """The balance says 2 units when the bot restarts inside its 1-unit basket: with the state file the basket is
    read back with its unit and the record of its sizing; without it the unit comes from the open position's volume
    (the balances of the entry are then not known). Either way it is managed as 1 unit, and the next basket gets 2."""
    fake0, run0, spans = reference
    a, b = spans[1]
    fake, clock = market(900, seed=5, restarts=[a + 60.5])
    fake.at(START + a + 30, lambda f: f.add_balance_operation(4000.0))

    def on_new_bot(bot, n):
        if n > 0 and drop_state:
            os.remove(bot._state_path('XAUUSDm'))
    run = run_bot(fake, clock, overrides=dict(NO_LADDER, ACCOUNT_SHARE=0.5), state_dir=tmp_path, on_new_bot=on_new_bot)
    assert run.restarts == 1 and not run.errors, run.errors[:3]
    after = [p for p in _at(run, a + 62, b - 2) if p['nb'] + p['ns'] > 0]
    assert after and {p['units'] for p in after} == {1} and {p['levels']['units'] for p in after} == {1}
    first = after[0]['sizing']
    if drop_state:
        assert (first['source'], first['units'], first['account_balance']) == ('positions', 1, None)
    else:
        assert first == _at(run0, a + 40)[0]['sizing']          # the record of the entry, read back
    bs = baskets(fake, magic=MAGIC)
    assert [x['legs'][0]['vol'] for x in bs[:2]] == [0.01, 0.01]
    assert len(bs) >= 3 and bs[2]['legs'][0]['vol'] == 0.02


def _no_balance(bot, a, b):
    """From terminal second `a` to `b` after START the poll's account read answers nothing (the account checks of
    the poll still pass: the balance alone is not known)."""
    read = bot.position_helper.get_account_info
    clock = bot.position_helper.mt5.clock

    def get_account_info():
        return None if START + a <= clock.time() < START + b else read()
    bot.position_helper.get_account_info = get_account_info


def test_no_entry_while_the_balance_is_not_known(reference, tmp_path):
    """The second basket of the reference opens when its entry pause ends. Here the balance is not known from 30 s
    before that until 30 s after: no order in that time although the strategy wants the entry on every poll
    (_open_hold says why, the strategy log gets one line), and the entry goes out on the first poll that knows the
    balance again."""
    fake0, run0, spans = reference
    a = spans[1][0]
    fake, clock = market(900, seed=5)
    run = run_bot(fake, clock, overrides=dict(NO_LADDER, ACCOUNT_SHARE=0.5), state_dir=tmp_path,
                  on_new_bot=lambda bot, n: _no_balance(bot, a - 30, a + 30))
    assert not run.errors, run.errors[:3]
    opens = [o['_t_ms'] / 1000.0 - START for o in fake.orders if 'position' not in o]
    assert opens[0] == pytest.approx(spans[0][0], abs=0.01)                 # the first basket as in the reference
    assert not [t for t in opens if a - 30 <= t < a + 30]                   # nothing while the balance is unknown
    assert opens[1] == pytest.approx(a + 30, abs=1.5)                       # then at once
    held = [p for p in _at(run, a - 30, a + 30) if p['open_hold']]
    assert held and held[0]['t'] / 1000.0 - START == pytest.approx(a, abs=1.5)      # from the poll that wanted it
    side = {0: 'BUY', 1: 'SELL'}[baskets(fake0, MAGIC)[1]['side']]
    for p in held:
        h = p['open_hold']
        assert set(h) == {'why', 'side', 'kind', 'price', 'until', 'refusals', 'since'}
        assert (h['why'], h['side'], h['kind'], h['until'], h['refusals'], h['since']) == (
            'balance_unknown', side, 'entry', None, 0, None)
        assert h['price'] > 0 and p[side.lower()] == side                   # the signal stands; no order
        assert p['sizing']['source'] == 'unknown' and p['sizing']['account_balance'] is None and p['units'] == 1
    assert len(held) >= 25                                                  # every poll of the window that wanted it
    assert not [p for p in run.polls if p['open_hold'] and not (a - 30 <= p['t'] / 1000.0 - START < a + 30)]
    notes = [e for e in run.events if e['event'] == f'{side}_SIGNAL' and 'Entry held' in e['details'].get('note', '')]
    assert len(notes) == 1 and 'balance is not known' in notes[0]['details']['note']        # once, not per poll
    assert notes[0]['details']['hold']['why'] == 'balance_unknown'


@pytest.mark.parametrize('balance', [0.0, -35.5])
def test_no_entry_on_an_account_that_is_not_funded(tmp_path, balance):
    """A balance of 0 or below (the account not funded yet, or overdrawn): the forward-test code opened one unit;
    a real-money bot opens nothing."""
    fake, clock = market(400, seed=5, balance=balance)
    run = run_bot(fake, clock, overrides=dict(NO_LADDER, ACCOUNT_SHARE=0.5), state_dir=tmp_path)
    assert fake.orders == [] and not run.errors
    held = [p for p in run.polls if p['open_hold']]
    assert held and {p['open_hold']['why'] for p in held} == {'balance_unknown'}
    assert held[0]['sizing']['account_balance'] == balance and held[0]['sizing']['source'] == 'unknown'


@pytest.mark.slow
def test_an_open_basket_is_still_closed_while_the_balance_is_not_known(reference, tmp_path):
    """Exits never wait for the balance: it is unknown from the middle of the second basket to the end of the run.
    The basket closes on the poll it closes on in the reference; no new basket follows."""
    fake0, run0, spans = reference
    a, b = spans[1]
    fake, clock = market(900, seed=5)
    run = run_bot(fake, clock, overrides=dict(NO_LADDER, ACCOUNT_SHARE=0.5), state_dir=tmp_path,
                  on_new_bot=lambda bot, n: _no_balance(bot, a + 30, 10 ** 9))
    assert not run.errors, run.errors[:3]
    ref = [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in fake0.deals]
    got = [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in fake.deals]
    assert got == ref[:4] and len(ref) > 4                  # two baskets opened and closed as in the reference, no third
    assert any(p['open_hold'] for p in _at(run, b, 900))


# ───────────────────────────── the Turtle ─────────────────────────────

def _turtle(tmp_path, balance, share, restarts=(), on_bot=None, step=2500, cap=10, trip=None, **kw):
    fake, clock = TB._market(trip or TB._long_trip(), balance=balance, restarts=restarts)
    run = TB._run(fake, clock, tmp_path, overrides={'ACCOUNT_SHARE': share}, on_bot=on_bot, step_up=step,
                  max_limit=cap, **kw)
    return fake, run


def _entry_of(run):
    return [e for e in run.events if e['event'] == 'BUY_EXECUTED'][0]['details']


@pytest.mark.parametrize('share, balance, step, cap', [
    (0.5, 2000.0, 2500, 10),            # 1 unit
    (0.5, 4999.98, 2500, 10),           # a cent under the step: still 1
    (0.5, 5000.0, 2500, 10),            # on the step: 2
    (0.5, 7600.0, 2500, 10),            # 2
    (1.0, 2600.0, 2500, 10),            # the whole account: 2
    (0.5, 90000.0, 2500, 3),            # the cap
])
def test_the_turtle_unit_is_its_share_of_the_balance_and_every_leg_has_it(tmp_path, share, balance, step, cap):
    fake, run = _turtle(tmp_path, balance, share, step=step, cap=cap)
    assert not run.errors, run.errors[:3]
    want = _units(share, balance, step, cap)
    opens = TB._opens(fake)
    assert len(opens) == 4 and {round(o['volume'], 6) for o in opens} == {round(want * 0.01, 6)}    # the entry, 3 adds
    entry = _entry_of(run)
    assert entry['units'] == want and entry['account_balance'] == balance
    assert entry['sizing_balance'] == round(share * balance, 2)
    in_trade = [p for p in run.polls if p['nb'] > 0]
    recs = [p['sizing'] for p in in_trade]
    assert in_trade and {p['units'] for p in in_trade} == {want} and all(r == recs[0] for r in recs)
    assert set(recs[0]) == KEYS and recs[0]['source'] == 'entry'
    assert (recs[0]['share'], recs[0]['account_balance'], recs[0]['sizing_balance']) == (share, balance, round(share * balance, 2))
    assert (recs[0]['step'], recs[0]['units'], recs[0]['unit_max']) == (step, want, cap)


def test_a_turtle_trade_keeps_its_unit_whatever_the_balance_does(tmp_path):
    """$6,000 arrive after the entry (1 unit) and before the adds: every add is the trade's unit. Flat again, the
    unit shown is the new balance's at once."""
    ref_fake, ref = _turtle(tmp_path / 'ref', 2000.0, 0.5)
    t_entry = TB._opens(ref_fake)[0]['_t_ms'] / 1000.0
    fake, clock = TB._market(TB._long_trip(), balance=2000.0)
    fake.at(t_entry + 20, lambda f: f.add_balance_operation(6000.0))
    run = TB._run(fake, clock, tmp_path / 'run', overrides={'ACCOUNT_SHARE': 0.5})
    assert not run.errors, run.errors[:3]
    assert [o['volume'] for o in TB._opens(fake)] == [0.01] * 4
    assert [o['_t_ms'] for o in fake.orders] == [o['_t_ms'] for o in ref_fake.orders]         # the same trade
    in_trade = [p for p in run.polls if p['nb'] > 0]
    assert {p['units'] for p in in_trade} == {1} and {p['sizing']['account_balance'] for p in in_trade} == {2000.0}
    t_exit = TB._closes(fake)[0]['_t_ms']
    flat_after = [p for p in run.polls if p['t'] > t_exit + 1500]
    assert flat_after and {p['units'] for p in flat_after} == {2}
    assert flat_after[0]['sizing']['source'] == 'balance' and flat_after[0]['sizing']['account_balance'] > 7000


def test_the_turtle_enters_only_when_the_balance_is_known(tmp_path):
    """The breakout comes while the balance is not known: no entry (the armed orders stay armed, _open_hold says
    why, a note in the log); known again 150 s later with the price still beyond the level: the entry, at the
    market, sized from that balance."""
    ref_fake, ref = _turtle(tmp_path / 'ref', 5200.0, 0.5)
    t0 = TB._opens(ref_fake)[0]['_t_ms'] / 1000.0 - START                # the reference's entry
    until = t0 + 150
    fake, run = _turtle(tmp_path / 'run', 5200.0, 0.5, on_bot=lambda bot, n: _no_balance(bot, 0, until))
    assert not run.errors, run.errors[:3]
    opens = TB._opens(fake)
    assert opens and opens[0]['_t_ms'] / 1000.0 - START == pytest.approx(until, abs=1.5)
    assert opens[0]['volume'] == pytest.approx(0.02) and _entry_of(run)['units'] == 2          # half of 5,200: 2 units
    assert TB._deal_ins(fake)[0].price > TB._deal_ins(ref_fake)[0].price                     # later, at the market
    held = [p for p in run.polls if p['open_hold']]
    assert held and held[0]['t'] / 1000.0 - START == pytest.approx(t0, abs=1.5)
    assert all(START + t0 - 1.5 <= p['t'] / 1000.0 < START + until for p in held) and len(held) >= 100
    for p in held:
        h = p['open_hold']
        assert (h['why'], h['side'], h['kind'], h['until'], h['refusals']) == ('balance_unknown', 'BUY', 'entry', None, 0)
        assert h['price'] >= TB.LV['buy'] and p['buy'] == 'DO_NOTHING' and p['nb'] == 0
        assert p['sizing']['source'] == 'unknown'
    notes = [e for e in run.events if e['event'] == 'TURTLE_NOTE' and 'entry held' in e['details'].get('note', '')]
    assert 1 <= len(notes) <= 2 and 'balance is not known' in notes[0]['details']['note']     # at most every 5 min
    assert not [e for e in run.events if e['event'] == 'BUY_EXECUTED' and e['t'] < (START + until - 1) * 1000]


@pytest.mark.parametrize('balance', [0.0, -12.0])
def test_the_turtle_opens_nothing_on_an_account_that_is_not_funded(tmp_path, balance):
    fake, run = _turtle(tmp_path, balance, 0.5, trip=TB._long_trip()[:2])
    assert fake.orders == [] and not run.errors
    held = [p for p in run.polls if p['open_hold']]
    assert held and {p['open_hold']['why'] for p in held} == {'balance_unknown'}
    assert held[-1]['sizing']['account_balance'] == balance


@pytest.mark.slow
def test_the_turtle_stop_still_closes_while_the_balance_is_not_known(tmp_path):
    """Exits never wait for the balance: unknown from after the second add to the end, the trade takes its adds
    (they use the trade's unit) and is closed at its stop exactly as in the run that knows it."""
    ref_fake, ref = _turtle(tmp_path / 'ref', 2000.0, 0.5)
    t_add2 = TB._opens(ref_fake)[2]['_t_ms'] / 1000.0 - START
    fake, run = _turtle(tmp_path / 'run', 2000.0, 0.5, on_bot=lambda bot, n: _no_balance(bot, t_add2 + 30, 10 ** 9))
    assert not run.errors, run.errors[:3]
    assert [(o['_t_ms'], o['volume'], o.get('position')) for o in fake.orders] == \
           [(o['_t_ms'], o['volume'], o.get('position')) for o in ref_fake.orders]
    assert len(TB._closes(fake)) == 4 and not fake.positions


def _side_file(tmp_path):
    path = tmp_path / f'{TB.SYMBOL}_turtle_side.json'
    return json.loads(path.read_text()) if path.exists() else None


@pytest.mark.slow
@pytest.mark.parametrize('drop', ['nothing', 'book', 'side', 'both'])
def test_a_restart_inside_a_turtle_trade_keeps_its_unit_and_its_sizing_record(tmp_path, drop):
    """2 units at the entry (half of $5,200); a withdrawal then leaves $1,000; the bot restarts after the second
    add. The trade stays at 2 units -- from its book, or without the book from the first leg's volume -- and its
    last add is 0.02 too. The record of its sizing comes back from the side file beside the book (also when the
    book is gone: it knows the trade by its first fill); without the side file only the unit is known."""
    ref_fake, ref = _turtle(tmp_path / 'ref', 5200.0, 0.5)
    t_entry = TB._opens(ref_fake)[0]['_t_ms'] / 1000.0
    t_add2 = TB._opens(ref_fake)[2]['_t_ms'] / 1000.0
    fake, clock = TB._market(TB._long_trip(), balance=5200.0, restarts=[t_add2 + 30.5 - START])
    fake.at(t_entry + 20, lambda f: f.add_balance_operation(-4200.0))

    def on_bot(bot, n):
        if n > 0 and drop in ('book', 'both'):
            os.remove(bot._turtle_state_path(TB.SYMBOL))
        if n > 0 and drop in ('side', 'both'):
            os.remove(bot._turtle_side_path(TB.SYMBOL))
    run = TB._run(fake, clock, tmp_path / 'run', overrides={'ACCOUNT_SHARE': 0.5}, on_bot=on_bot)
    assert run.restarts == 1 and not run.errors, run.errors[:3]
    assert [o['volume'] for o in TB._opens(fake)] == [0.02] * 4 and not fake.positions
    assert [o['_t_ms'] for o in fake.orders] == [o['_t_ms'] for o in ref_fake.orders]
    after = [p for p in run.polls if p['t'] > (t_add2 + 32) * 1000 and p['nb'] > 0]
    assert after and {p['units'] for p in after} == {2}
    rec = after[0]['sizing']
    if drop in ('side', 'both'):
        assert (rec['source'], rec['units'], rec['account_balance'], rec['sizing_balance']) == ('positions', 2, None, None)
    else:
        assert (rec['source'], rec['units'], rec['account_balance'], rec['sizing_balance']) == ('entry', 2, 5200.0, 2600.0)
        before = [p for p in run.polls if p['t'] < (t_add2 + 28) * 1000 and p['nb'] > 0]
        assert rec == before[-1]['sizing']
    # flat again: the unit of the balance of then (under $1,000 and the trade's result)
    flat = [p for p in run.polls if p['t'] > TB._closes(fake)[0]['_t_ms'] + 1500]
    assert flat and {p['units'] for p in flat} == {1} and flat[0]['sizing']['source'] == 'balance'


def test_the_turtle_side_file_holds_the_entry_and_no_account_number(tmp_path):
    """state/<symbol>_turtle_side.json: written when the trade opens (beside the book), emptied once it has ended;
    it names the account by its tail and its SHA-256 only."""
    seen = []

    def on_bot(bot, n):
        save = bot._save_turtle_side

        def spy(symbol, rec):
            save(symbol, rec)
            seen.append((bot.position_helper.mt5.clock.time(), _side_file(tmp_path)))
        bot._save_turtle_side = spy
    fake, run = _turtle(tmp_path, 5200.0, 0.5, on_bot=on_bot)
    assert not run.errors, run.errors[:3]
    assert len(seen) == 2                                    # at the entry, and when the trade had ended
    (t_in, at_entry), (t_out, at_exit) = seen
    assert t_in == pytest.approx(TB._opens(fake)[0]['_t_ms'] / 1000.0, abs=1.5)
    t_closed = TB._closes(fake)[0]['_t_ms'] / 1000.0
    assert t_closed < t_out <= t_closed + 2.5               # on the first poll that lists none of its positions
    trade = at_entry['trade']
    assert (trade['side'], trade['units'], trade['ticket']) == (1, 2, TB._deal_ins(fake)[0].position_id)
    assert trade['sizing']['account_balance'] == 5200.0 and trade['sizing']['units'] == 2
    assert at_exit['trade'] is None
    for doc in (at_entry, at_exit):
        assert (doc['symbol'], doc['magic']) == (TB.SYMBOL, MAGIC) and doc['branch']
        assert doc['login_tail'] == '...' + str(F.ACCOUNT_LOGIN)[-4:] and len(doc['login_sha']) == 64
        assert not found(json.dumps(doc), str(F.ACCOUNT_LOGIN))
    assert not [p.name for p in tmp_path.iterdir() if p.name.endswith('.tmp')]


@pytest.mark.slow
def test_the_side_file_waits_for_a_trade_whose_book_was_lost_and_whose_bars_come_late(tmp_path):
    """A restart inside a trade without the book, and the terminal gives no D1 bars for the first 20 s: the bot
    cannot rebuild the trade yet (its book is flat although its positions are open). The record of the trade stays
    until it can -- it is not thrown away as "the trade has ended" -- and then says how the trade was sized."""
    ref_fake, ref = _turtle(tmp_path / 'ref', 5200.0, 0.5)
    t_add2 = TB._opens(ref_fake)[2]['_t_ms'] / 1000.0
    at = t_add2 + 30.5
    fake, clock = TB._market(TB._long_trip(), balance=5200.0, restarts=[at - START])
    fake.fail_rates('D1', at, at + 20)

    def on_bot(bot, n):
        if n > 0:
            os.remove(bot._turtle_state_path(TB.SYMBOL))
    run = TB._run(fake, clock, tmp_path / 'run', overrides={'ACCOUNT_SHARE': 0.5}, on_bot=on_bot)
    assert run.restarts == 1
    waiting = [p for p in run.polls if at * 1000 < p['t'] < (at + 19) * 1000]
    assert waiting and all(p['nb'] == 3 for p in waiting)               # its three legs, no book yet
    after = [p for p in run.polls if p['t'] > (at + 25) * 1000 and p['nb'] > 0]
    rec = after[0]['sizing']
    assert (rec['source'], rec['units'], rec['account_balance'], rec['sizing_balance']) == ('entry', 2, 5200.0, 2600.0)
    assert [o['volume'] for o in TB._opens(fake)] == [0.02] * 4 and not fake.positions


def test_a_side_file_of_another_trade_or_another_account_is_not_this_trades(mods, tmp_path):
    m = mods(**TB.TURTLE)
    bot = F.make_bot(m, m.fake, TB.SYMBOL, F.Run(), state_dir=tmp_path)
    assert bot._load_turtle_side(TB.SYMBOL) is None                         # no file
    book = dict(TB.T.new_state(), side=1, units=2, entry_time=1000.0, legs=[{'price': 1.0, 'time': 1000.0, 'ticket': 11},
                                                                           {'price': 2.0, 'time': 1100.0, 'ticket': 12}])
    rec = bot._turtle_side_record(book, {'units': 2, 'account_balance': 5200.0})
    assert rec == {'entry_time': 1000.0, 'ticket': 11, 'side': 1, 'units': 2,
                   'sizing': {'units': 2, 'account_balance': 5200.0}}
    bot._save_turtle_side(TB.SYMBOL, rec)
    assert bot._load_turtle_side(TB.SYMBOL) == rec
    sizing = bot._turtle_side_sizing
    assert sizing(book, rec) == rec['sizing']
    assert sizing(dict(book, entry_time=999.0), rec) == rec['sizing']       # rebuilt: known by its first fill
    assert sizing(dict(book, entry_time=999.0, legs=book['legs'][1:]), rec) is None      # not this trade
    assert sizing(dict(book, side=0), rec) is None and sizing(book, None) is None
    assert sizing(dict(book, entry_time=999.0, legs=[None, 'x']), rec) is None             # never raises
    # the file of another symbol or another bot is not read as this bot's
    assert bot._load_turtle_side('XAUUSDm') is None
    path = tmp_path / f'{TB.SYMBOL}_turtle_side.json'
    doc = json.loads(path.read_text())
    # ... and the file of another account (a credentials change) is put aside, as every state file of another
    # account is (test_live_state_files.py), and the bot of the new account starts without a record
    run2 = F.Run()
    other = F.make_bot(m, m.fake, TB.SYMBOL, run2, state_dir=tmp_path, credentials=F.account_credentials(login_id=87654321))
    assert other._load_turtle_side(TB.SYMBOL) is None and not path.exists()
    aside = [p for p in tmp_path.iterdir() if p.name.startswith(path.name + '.other-account-')]
    assert len(aside) == 1 and json.loads(aside[0].read_text()) == doc
    assert [e['event'] for e in run2.events] == ['STATE_OTHER_ACCOUNT']
    aside[0].rename(path)                                                   # (back, for the checks below)
    assert bot._load_turtle_side(TB.SYMBOL) == rec
    path.write_text(json.dumps(dict(doc, magic=MAGIC + 1)))
    assert bot._load_turtle_side(TB.SYMBOL) is None
    path.write_text('{not json')
    assert bot._load_turtle_side(TB.SYMBOL) is None                         # unreadable: no record, no error
    # a write that fails is noted, never raised
    bot.state_dir = str(tmp_path / 'a_file')
    (tmp_path / 'a_file').write_text('x')
    bot._save_turtle_side(TB.SYMBOL, rec)
