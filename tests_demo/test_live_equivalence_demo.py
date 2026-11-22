"""
The live bot sends the orders of the demo bot the owner tested (spec, section 13, "Equivalence with the demo
trees"): the central proof that the real-money layer changed nothing of the strategy.

For each of the five designs (demo_equiv.DESIGNS):
  reference  the demo branch at its pinned commit -- xv3 b3a11f9 (Gold V3-lite), xt2 9270618 (Gold Top 2),
             xt1 4581685 (Gold Top 1), bt2 da85e9a (BTC Top 2), bs2 660932b (BTC Turtle System 2) -- read from git
             and run as it is: its constants.py whole, its symbols.json;
  live       this tree stamped as the branch generator does it: this tree's files, with the design block of that
             demo commit's constants.py as written (taken from the commit, nothing typed here) and that branch's
             symbol and trading window.
On one fake market (demo_equiv.py; pinned) three replays of the whole bot loop:
  (a) the demo tree;
  (b) the live tree with the safety OFF (no limit, the switch off);
  (c) the live tree with the safety ON at that design's real limits (demo_equiv.LIMITS: those of the first account
      that runs it; the design of this tree itself: the limits written in its constants.py, demo_equiv.on_limits).
Equal in every poll: the time of the poll, every order request as a whole dict (every key, every value and its
type, and the fake time it was sent at; only "magic" and "comment" are left out, and each tree must have put its
own there), what the poll decided, and at the end the deals (time, type, entry, volume, price, profit, reason),
the open positions and the balance. A difference is reported with its first poll and both requests.

Sizing, made comparable honestly. The demo bot sizes from its virtual balance (VIRTUAL_START_BALANCE of its commit
+ its own closed profit), the live bot from ACCOUNT_SHARE x the balance of the real account. So:
  * the fake account starts with exactly the demo commit's VIRTUAL_START_BALANCE and nobody else trades it: the
    account balance and the virtual balance are then the same number after every close. (The demo tree needs a demo
    account and the live tree a real one: that word of the fake account is the only thing that differs.);
  * (b), (c) and the restart replay: ACCOUNT_SHARE = 1.0 and the step_up_balance of the demo branch's symbols.json
    on both sides (Top 2 and BTC Top 2 trade 2 units there, the others 1);
  * one replay more per loop (a basket, the basket with the ladder add, the Turtle): both sides at a step that
    makes 3 units (and, after the first winning basket, 4), once with ACCOUNT_SHARE = 1.0 and once with
    ACCOUNT_SHARE = 0.5 on half that step -- the live bot on half the balance against the demo tree at twice the
    live step.

A quiet market proves nothing, so each test first asserts what its market made the demo bot do (and the live bot
then did the same, poll for poll, and its own events tell the same story): a basket closed at its target and one
closed at its stop, followed by the loss pause (an entry was wanted after the ordinary 300 s pause had run out, and
none was sent); for xt1 a ladder add; for bs2 a pyramid, then a D1 bar closing that raises the stop, then the exit
at that stop (the Turtle has no target and no loss pause: its only exit is its stop, 2N or the exit channel when
that is tighter); and, in a replay of its own, one restart of the bot inside an open trade, both trees at the same
fake time (xt1: before the add, bs2: before the pyramid, so each is sent by the restarted bot; the others: the next
basket is opened by it). With ALCADEIAS_PROOF=1 also the whole loss pause of a 12-hour and a 4-hour design, across
00:00 UTC: the entry after it goes on the poll the pause ends, in both trees.

The (c) replay also asserts that the safety never blocked and never held an order (no block file in the account
folder, nothing in the audit file but its one start, no poll that held an open back, no event of a hold, a block
or a refusal, no view of the Tracker that says blocked, hold or error) and that it really ran: its Tracker polled
in (nearly) every poll and left its state file in the bot folder. Every other live replay but (b) runs as the bot
ships, safety ON at those limits, with the same "never blocked" checks; after the restart the Tracker polls on from
its own state (no second start). That a Tracker is in the poll loop at all is asserted in (c) (where one polls, it
must poll throughout, after a restart too).

Without git or a pinned commit the tests skip and say why; with ALCADEIAS_PROOF=1 that is a failure (both tested
without a replay). The replays are slow (marker "slow"; about 6 minutes in all); the replay of the whole loss
pause runs only with ALCADEIAS_PROOF=1 (about 4 minutes more) and is skipped with that reason otherwise.
"""
import json

import pytest

import demo_equiv as E
from conftest import AS_WRITTEN, COMMENT, MAGIC
from conftest import differs

CODES = tuple(E.DESIGNS)
STEP_3_UNITS = 700            # a step_up_balance that sizes the demo bot's $2,000 at 3 units (and $2,100 at 4)


# ───────────────────────── the trees and the replays, made once ─────────────────────────

@pytest.fixture(scope='module')
def design(tmp_path_factory):
    """design(code): the two trees of a design. Skips (ALCADEIAS_PROOF=1: fails) when git cannot give the demo tree."""
    made = {}

    def get(code):
        if code not in made:
            try:
                made[code] = E.build_design(code, tmp_path_factory.mktemp(f'{code}_demo_tree'),
                                            tmp_path_factory.mktemp(f'{code}_live_tree'))
            except E.NotThere as e:
                made[code] = e
        if isinstance(made[code], E.NotThere):
            E.not_there(str(made[code]))
        return made[code]
    return get


@pytest.fixture(scope='module')
def replay(design, tmp_path_factory):
    """replay(code, which): one replay, made on first use and kept for the tests of this file.
    which: 'demo' / 'off' / 'on' on the design's market; 'demo restart' / 'on restart' with the bot restarted once
    inside a trade; 'demo 3 units' / 'on 3 units' / 'on half share' at the 3-unit step; 'demo long' / 'on long' on
    the market of the whole loss pause."""
    made = {}

    def get(code, which):
        key = (code, which)
        if key not in made:
            d = design(code)
            # every bot in a folder of its own, named bot_output: the account folder beside it is private too
            out = tmp_path_factory.mktemp(f"{code}_{which.replace(' ', '_')}") / 'bot_output'
            fake, clock = E.market(d, restart='restart' in which, long='long' in which)
            limits = E.on_limits(code)
            if which in ('demo', 'demo restart', 'demo long'):
                made[key] = E.replay_demo(d, fake, clock, out)
            elif which == 'off':
                made[key] = E.replay_live(d, fake, clock, out, share=1.0, limits=None)
            elif which in ('on', 'on restart', 'on long'):
                made[key] = E.replay_live(d, fake, clock, out, share=1.0, limits=limits)
            elif which == 'demo 3 units':
                made[key] = E.replay_demo(d, fake, clock, out, step=STEP_3_UNITS)
            elif which == 'on 3 units':
                made[key] = E.replay_live(d, fake, clock, out, share=1.0, limits=limits, step=STEP_3_UNITS)
            elif which == 'on half share':
                made[key] = E.replay_live(d, fake, clock, out, share=0.5, limits=limits, step=STEP_3_UNITS / 2)
            else:
                raise KeyError(which)
        return made[key]
    return get


# ───────────────────────── what every comparison asserts ─────────────────────────

def _ran_clean(r):
    assert not r.run.errors, f'the {r.name} bot printed errors: {r.run.errors[:3]}'
    assert r.polls and r.fake.orders, f'the {r.name} bot sent nothing'


def _same(ref, live):
    """The live replay did what the demo replay did, and each bot marked its orders as its own."""
    _ran_clean(ref)
    _ran_clean(live)
    diff = E.difference(ref, live)
    assert diff is None, f'{ref.design.code}: the live bot did not do what the demo bot did.\n{diff}'
    assert not differs(E.requests(ref), E.requests(live))                                   # (said once more, plainly)
    assert ref.fake.balance == live.fake.balance
    # the only two keys left out: each tree's own magic number and comment, on every request
    d = ref.design
    assert d.demo['MAGIC'] != MAGIC
    assert {(o.get('magic'), o.get('comment')) for o in ref.fake.orders} == {(d.demo['MAGIC'], d.demo_comment)}
    assert {(o.get('magic'), o.get('comment')) for o in live.fake.orders} == {(MAGIC, COMMENT)}


def _unheld(r, restart_at=None):
    """A live replay in which the safety held nothing back -- and, where it polled at all, polled throughout (a
    tree with no Tracker in its loop is failed once, by the ON test)."""
    assert E.never_blocked(r) == [], f'{r.design.code}, {r.name}'
    assert E.safety_gaps(r, restart_at) == [], f'{r.design.code}, {r.name}'


def _lot(d, units):
    return pytest.approx(units * d.mtqty)


# ───────────────────────── what each market must have made the bots do ─────────────────────────

def _basket_story(r, units=None):
    """The basket market of a design, as the replay `r` lived it: a basket closed at its target, the next one at
    its stop, then the loss pause; for the ladder design an add in the first basket. Returns (the closed baskets,
    the number of polls in which the loss pause alone held an entry back)."""
    d, c = r.design, r.design.demo
    assert [reason for _, _, reason in E.exits(r)] == ['target', 'stop_loss']
    (i_target, _, _), (i_stop, t_stop, _) = E.exits(r)
    won, lost = E.closed_baskets(r)
    assert won['pnl'] > 0 > lost['pnl'] and won['t_close'] < lost['t_open']
    assert r.fake.balance == pytest.approx(d.balance + won['pnl'] + lost['pnl']) and not r.fake.positions
    closed = E.events(r, 'CLOSE_BUY', 'CLOSE_SELL')
    assert [(e['details']['reason'], e['details']['lost']) for e in closed] == [('target', False), ('stop_loss', True)]
    assert [e['details']['realised_pnl'] for e in closed] == [won['pnl'], lost['pnl']]
    # the target and the stop are the design's: so many volatility units (capped), for the basket's unit count
    levels = r.polls[i_target]['levels']
    unit = levels['vol_unit']
    usd_per_price = d.mtqty * E.BASKET_MARKETS[d.code]['contract']            # USD per unit for a 1.0 price move
    measured = r.polls[min(E.requests_by_poll(r))]['vol']                     # the H1 unit on the poll of the entry
    cap = c['VOL_CAP_USD_PER_UNIT'] / usd_per_price if c['VOL_CAP_USD_PER_UNIT'] else None
    assert measured > 0 and unit == pytest.approx(min(measured, cap) if cap else measured)
    if d.code == 'xt2':
        assert measured > cap                                                 # this market is wild enough: the cap binds
    usd = unit * usd_per_price * levels['units']
    assert levels['target_usd'] == pytest.approx(c['TARGET_VOL'] * usd, abs=0.006)
    assert levels['stop_usd'] == pytest.approx(c['STOP_VOL'] * usd, abs=0.006)
    assert won['pnl'] > levels['target_usd'] and lost['pnl'] <= -r.polls[i_stop]['levels']['stop_usd']
    if units is not None:
        assert levels['units'] == units
    first = E.opens(r)[0]
    assert first['volume'] == _lot(d, levels['units'])
    assert first['sl'] > 0 and first['tp'] == 0.0                             # the broker-side backstop, no target
    # the ordinary pause after the winner: the next entry came when it had run out, not before
    pause = c['REENTRY_COOLDOWN_SECONDS']
    assert pause <= lost['t_open'] - won['t_close'] < pause + 5
    # the ladder
    adds = E.events(r, 'BUY_MORE_EXECUTED', 'SELL_MORE_EXECUTED')
    if c['MAX_ADDS']:
        assert len(won['legs']) == 2 and len(adds) == 1, 'no ladder add in the first basket'
        entry, add = won['legs']
        gap = levels['gap_px']
        assert gap == pytest.approx(c['LADDER_GAP_VOL'] * unit) and gap > 0
        worse = (entry['price_in'] - add['price_in']) if won['side'] == 0 else (add['price_in'] - entry['price_in'])
        assert worse >= gap                                                   # at least the gap against the entry
        assert add['vol'] == _lot(d, c['LADDER_MULTIPLIERS'][1] * levels['units'])
        i_add = next(i for i, p in enumerate(r.polls) if 'MORE' in p['buy'] + p['sell'])
        i_open = next(i for i, p in enumerate(r.polls) if p['nb'] + p['ns'])
        assert any(p['ladder_armed'] for p in r.polls[i_open:i_add])          # armed by a vote against the basket
        assert len({o['_t_ms'] for o in E.closes(r)[:2]}) == 1                # both legs closed by one decision
    else:
        assert all(len(b['legs']) == 1 for b in (won, lost)) and not adds
    # the loss pause: after the stop no entry, although one was wanted when the ordinary pause was over
    loss_pause = c['LOSS_COOLDOWN_S']
    assert loss_pause > 10 * pause
    after = r.polls[i_stop + 1:]
    assert after and all(not p['entry_allowed'] and p['nb'] + p['ns'] == 0 for p in after)
    assert all(o['_t_ms'] <= t_stop + 1000 for o in r.fake.orders)            # nothing was sent after the stop's close
    held = [p for p in after if p['t'] >= t_stop + (pause + 2) * 1000 and E.entry_wanted(d, p)]
    assert len(held) >= 20, 'the market does not show the loss pause holding an entry back'
    for p in held:
        assert p['pause_left'] == pytest.approx(loss_pause - (p['t'] - t_stop) / 1000.0, abs=3.0)
    return (won, lost), len(held)


def _turtle_story(r, units=None):
    """The Turtle's market, as the replay `r` lived it: the breakout entry, a pyramid, a D1 bar closing that raises
    the stop from 2N to the exit channel, the exit at that stop."""
    d, c = r.design, r.design.demo
    entry, add = E.opens(r)
    assert entry['type'] == add['type'] == r.fake.ORDER_TYPE_BUY and len(E.opens(r)) == 2
    (ev_entry,) = E.events(r, 'BUY_EXECUTED')
    (ev_add,) = E.events(r, 'BUY_MORE_EXECUTED')
    (ev_exit,) = E.events(r, 'CLOSE_BUY')
    n = ev_entry['details']['n_entry']
    assert ev_entry['details']['fill'] >= ev_entry['details']['level'] and ev_entry['details']['vote'] == 1
    assert ev_entry['details']['stop_origin'] == '2N'
    if units is not None:
        assert ev_entry['details']['units'] == units
    assert entry['volume'] == add['volume'] == _lot(d, ev_entry['details']['units'])
    # the pyramid: half an N above the entry's fill, in a later minute; the stop follows it, still 2N
    assert ev_add['details']['fill'] >= ev_entry['details']['fill'] + c['TURTLE_ADD_N'] * n
    assert ev_add['details']['stop'] == pytest.approx(ev_add['details']['fill'] - c['TURTLE_STOP_N'] * n)
    assert entry['sl'] > 0 and add['sl'] > entry['sl'] and entry['tp'] == add['tp'] == 0.0     # the backstops
    # the D1 bar of the entry's day closes with the trade open: the stop goes up to the exit channel
    levels = [e for e in E.events(r, 'TURTLE_LEVELS') if e['details']['trade'] == 'BUY']
    assert len(levels) == 1, 'no D1 bar closed while the trade was open'
    (day,) = levels
    midnight = (E.TURTLE_DAY + 86400) * 1000
    assert ev_add['t'] < midnight <= day['t'] < ev_exit['t']
    assert day['details']['stop_origin'] == 'channel' and day['details']['stop'] > ev_add['details']['stop']
    # the exit: the bid through that stop, every leg closed by one decision
    assert (ev_exit['details']['reason'], ev_exit['details']['stop_origin']) == ('stop', 'channel')
    assert ev_exit['details']['stop'] == day['details']['stop']
    assert len(E.closes(r)) == 2 and len({o['_t_ms'] for o in E.closes(r)}) == 1
    assert all(o['price'] <= day['details']['stop'] for o in E.closes(r))
    assert [reason for _, _, reason in E.exits(r)] == ['stop']
    (trade,) = E.closed_baskets(r)
    assert len(trade['legs']) == 2 and trade['pnl'] < 0 and not r.fake.positions
    assert r.fake.balance == pytest.approx(d.balance + trade['pnl'])
    return (trade,), 0


def _story(r, units=None):
    return (_turtle_story if r.design.turtle else _basket_story)(r, units)


def _restart_story(r):
    """The restart replay: the bot died once inside an open trade, the next bot took the trade over and managed it
    to its end, and opened what came after."""
    d = r.design
    assert r.run.restarts == 1
    t_restart = E.restart_time(d) * 1000.0
    before = [p for p in r.polls if p['t'] < t_restart]
    after = [p for p in r.polls if p['t'] >= t_restart]
    assert before and after and after[0]['t'] - before[-1]['t'] < 3000
    last, first = before[-1], after[0]
    assert last['nb'] + last['ns'] == 1 and (first['nb'], first['ns']) == (last['nb'], last['ns'])     # in a trade
    late = [o for o in E.opens(r) if o['_t_ms'] > t_restart]
    if d.turtle:
        assert len(late) == 1                                             # the pyramid, by the restarted bot
        assert [reason for _, _, reason in E.exits(r)] == ['stop'] and not r.fake.positions
        assert [e['details']['stop_origin'] for e in E.events(r, 'CLOSE_BUY')] == ['channel']
        assert not E.events(r, 'TURTLE_REBUILT')                          # the book was read back, not rebuilt
        return
    # the basket's own distances, back from the state file
    assert first['levels'] == dict(last['levels'], ladder_armed=first['levels']['ladder_armed'])
    assert [reason for _, _, reason in E.exits(r)] == ['target']
    assert len(late) == (2 if d.demo['MAX_ADDS'] else 1)                  # (the ladder add,) the next basket's entry
    if d.demo['MAX_ADDS']:
        assert last['ladder_armed'] and first['ladder_armed']             # the arming came back from the state file
        assert len(E.events(r, 'BUY_MORE_EXECUTED', 'SELL_MORE_EXECUTED')) == 1
    assert r.polls[-1]['nb'] + r.polls[-1]['ns'] == 1 and len(r.fake.positions) == 1      # the next basket is open


# ───────────────────────── the tests ─────────────────────────

@pytest.mark.parametrize('code', CODES)
def test_the_live_tree_of_a_design_differs_from_its_demo_commit_in_the_deployment_only(code, design):
    """Before any market: the stamped live tree holds every constant of the demo commit with the same value -- the
    whole file, not only the levers of the design block -- except the deployment block; what only one side has is
    the demo's three names, the deployment and the version, and (a basket design) the Turtle's unused constants."""
    d = design(code)
    deployment = E.deployment_names()
    assert d.dropped == ['VIRTUAL_START_DATE']                      # the one line the live code has no name for
    assert d.levers and 'DESIGN_NAME' in d.levers
    for name in d.levers:                                           # every lever the design block sets, as written
        assert name not in deployment and repr(d.live[name]) == repr(d.demo[name]), name
    assert d.live['DESIGN_NAME'] == d.design_name
    assert set(d.demo) - set(d.live) == E.DEMO_ONLY
    only_live = set(d.live) - set(d.demo) - deployment - {'VERSION'}
    if d.turtle:
        assert only_live == set()
    else:
        assert only_live and all(n.startswith('TURTLE_') for n in only_live) and d.live['STRATEGY'] == 'basket'
    for name in sorted((set(d.demo) & set(d.live)) - deployment):
        assert type(d.live[name]) is type(d.demo[name]) and repr(d.live[name]) == repr(d.demo[name]), name
    if E.constants_of(E.ROOT)['DESIGN_NAME'] == d.design_name:
        # This tree's own design: its ON replays run at the limits written here (E.on_limits), so on a stamped
        # branch they prove exactly the limits that ship there (whatever they are: no value is typed here) ...
        written = (AS_WRITTEN['SAFETY_DROP_PCT'], AS_WRITTEN['SAFETY_DAY_PCT'], AS_WRITTEN['SAFETY_STREAK_N'])
        assert E.on_limits(code) == written == E.written_limits()
        # ... and its symbols.json is the demo branch's (symbol, trading window, ...), the step aside
        own, demo = (json.loads((root / 'symbols.json').read_text(encoding='utf-8')) for root in (E.ROOT, d.demo_root))
        for cfg in (own, demo):
            for sym in cfg['symbols']:
                sym.pop('step_up_balance')
        assert own == demo


def test_without_git_or_a_pinned_commit_the_proof_skips_and_in_the_release_run_it_fails(monkeypatch, tmp_path):
    """What keeps the proof from passing by being left out: every way the demo tree can be missing -- git cannot
    be run, a commit that is not in the repository -- is NotThere, and NotThere is a skip that says why; with
    ALCADEIAS_PROOF=1 (the lead's release run) it is a failure."""
    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'git'")
    with monkeypatch.context() as m:
        m.setattr(E.subprocess, 'run', no_git)
        with pytest.raises(E.NotThere, match='git cannot be run'):
            E.export_demo_tree('xt2', tmp_path)
    with monkeypatch.context() as m:                  # (git there or not: the same NotThere)
        m.setitem(E.DESIGNS, 'xt2', ('0' * 40, 'xau_top2', 'XAUUSDm'))
        with pytest.raises(E.NotThere):
            E.export_demo_tree('xt2', tmp_path)
    monkeypatch.setattr(E, 'PROOF', False)
    with pytest.raises(pytest.skip.Exception, match='the reason'):
        E.not_there('the reason')
    monkeypatch.setattr(E, 'PROOF', True)
    with pytest.raises(pytest.fail.Exception, match='ALCADEIAS_PROOF=1 and the demo tree cannot be read'):
        E.not_there('the reason')


def test_the_reference_must_be_the_demo_branch_of_its_design(monkeypatch, tmp_path):
    """A pinned commit of another design, or a commit that is not a demo branch at all (this tree's own), is
    refused before any replay: the comparison would prove nothing."""
    (tmp_path / 'other').mkdir()
    (tmp_path / 'live').mkdir()
    try:
        monkeypatch.setitem(E.DESIGNS, 'xv3', (E.DESIGNS['xt2'][0], 'xau_v3lite', 'XAUUSDm'))
        with pytest.raises(AssertionError, match="holds the design 'xau_top2', not 'xau_v3lite'"):
            E.export_demo_tree('xv3', tmp_path / 'other')
        monkeypatch.setitem(E.DESIGNS, 'xv3', ('HEAD', 'xau_v3lite', 'XAUUSDm'))
        with pytest.raises(AssertionError, match='is not a demo branch'):
            E.export_demo_tree('xv3', tmp_path / 'live')
    except E.NotThere as e:
        E.not_there(str(e))
    assert not any(p.name in E._NEVER for p in tmp_path.rglob('*'))      # (never the credentials file)


@pytest.mark.slow
@pytest.mark.parametrize('code', CODES)
def test_the_live_bot_sends_the_orders_of_the_demo_bot(code, replay):
    """(a) against (b): the live layer without its breaker. The market made the demo bot trade (a target, a stop
    and the loss pause, the add, the pyramid and the D1 change), and the live bot did the same in every poll."""
    demo, off = replay(code, 'demo'), replay(code, 'off')
    _story(demo)
    _same(demo, off)
    _story(off)                                                      # (its own events tell the same story)
    _unheld(off)
    assert all(v['enabled'] is False for v in off.views)             # (where a Tracker polls: it is switched off)


@pytest.mark.slow
@pytest.mark.parametrize('code', CODES)
def test_with_the_safety_on_at_its_real_limits_the_live_bot_sends_the_same_orders(code, replay):
    """(a) against (c): the live bot as it ships, the safety ON at the design's limits. It sends the same orders,
    the safety never blocked and never held one -- and it really was in the loop."""
    demo, on = replay(code, 'demo'), replay(code, 'on')
    _story(demo)
    _same(demo, on)
    _story(on)
    _unheld(on)
    drop, day, streak = E.on_limits(code)
    for v in on.views:
        assert v['enabled'] is True and v['limits'] == {'drop_pct': drop, 'day_pct': day, 'streak_n': streak}, v
    # The safety really ran: its Tracker wrote its state into the bot folder. (Without this the replay above is
    # the OFF replay again and proves nothing about the safety.)
    state = E.safety_state_file(on)
    assert state.is_file(), (f'{code}: the ON replay left no {state.name} in {state.parent} (Tracker polls seen: '
                             f'{len(on.views)}): the safety did not run in the poll loop')
    assert len(on.views) >= 0.9 * len(on.polls), f'the Tracker polled {len(on.views)} times in {len(on.polls)} polls'
    assert all(v['state'] == 'on' for v in on.views)                 # watching, never checking, blocked or failing
    saved = json.loads(state.read_text(encoding='utf-8'))
    assert saved.get('account_block') is None and saved.get('bot_block') is None, saved
    assert len(E.fresh_starts(on)) == 1 and E.block_files(on) == []  # the first start is in the audit file; no block


@pytest.mark.slow
@pytest.mark.parametrize('code', CODES)
def test_a_restart_inside_an_open_trade_changes_nothing(code, replay):
    """Both bots are restarted at the same fake time inside an open trade (the live one as it ships: safety ON):
    the same orders before and after, the trade managed to its end, the next order sized the same."""
    demo, on = replay(code, 'demo restart'), replay(code, 'on restart')
    _restart_story(demo)
    assert on.run.restarts == 1                                      # the live bot died and came back too
    _same(demo, on)
    _restart_story(on)                                               # (took its trade over from its own files)
    _unheld(on, restart_at=E.restart_time(on.design))
    # the restarted bot read its safety state back: the counting did not start again (one start in the audit file)
    assert len(E.fresh_starts(on)) == 1 and E.safety_state_file(on).is_file()


@pytest.mark.slow
@pytest.mark.parametrize('code', ('xt2', 'xt1', 'bs2'))             # a basket, the one with the ladder add, the Turtle
def test_three_units_and_the_half_share(code, replay):
    """The unit count multiplies every lot: at 3 units on both sides (4 after the first winning basket), and with
    the live bot on half the account balance (ACCOUNT_SHARE = 0.5) against the demo bot at twice its step, the
    orders are the demo bot's."""
    demo = replay(code, 'demo 3 units')
    (first, *later), _ = _story(demo, units=3)
    d = demo.design
    assert E.opens(demo)[0]['volume'] == _lot(d, 3) and {leg['vol'] for leg in first['legs']} == {0.03}
    if later:                                                        # the winner moved the balance over the next step
        assert {leg['vol'] for leg in later[0]['legs']} == {0.04}
    for which, share in (('on 3 units', 1.0), ('on half share', 0.5)):
        live = replay(code, which)
        _same(demo, live)
        _story(live, units=3)
        _unheld(live)
        # every poll's sizing: this share of the account, on this step (the unit count itself is compared poll by
        # poll with the demo bot's, in _same)
        sizing = [p['sizing'] for p in live.polls if p.get('sizing')]
        assert sizing and all((s['share'], s['step']) == (share, STEP_3_UNITS * share) for s in sizing)


@pytest.mark.slow
@pytest.mark.parametrize('code', ('xt2', 'bt2'))                     # a 12-hour and a 4-hour loss pause
def test_the_whole_loss_pause_and_the_entry_at_its_end(code, replay):
    """The longer market: after the stop the market is closed for most of the loss pause and the run crosses 00:00
    UTC; an entry is wanted from the reopening on, and both bots send it on the poll the pause ends."""
    if not E.PROOF:
        pytest.skip('the replay of the whole loss pause runs only with ALCADEIAS_PROOF=1')
    demo, on = replay(code, 'demo long'), replay(code, 'on long')
    d, c = demo.design, demo.design.demo
    assert [reason for _, _, reason in E.exits(demo)] == ['target', 'stop_loss', 'target']
    (i_first, _, _), (i_stop, _, _), (i_last, _, _) = E.exits(demo)
    won, lost, again = E.closed_baskets(demo)
    assert won['pnl'] > 0 > lost['pnl'] and again['pnl'] > 0 and not demo.fake.positions
    loss_pause = c['LOSS_COOLDOWN_S']
    # the entry after the loss: on the first poll after the pause, not a poll earlier
    assert loss_pause <= again['t_open'] - lost['t_close'] < loss_pause + 2
    i_entry = max(i for i in E.requests_by_poll(demo) if i < i_last)
    assert not demo.polls[i_entry - 1]['entry_allowed'] and demo.polls[i_entry]['entry_allowed']
    # ... and it was wanted for the last minutes of the pause, which alone held it
    waited = [p for p in demo.polls[i_entry - 300:i_entry] if E.entry_wanted(d, p)]
    assert len(waited) >= 200 and all(not p['entry_allowed'] for p in waited)
    # in between the market was closed (the bots polled and decided nothing), and a UTC day began
    closed = [p for p in demo.polls[i_stop:i_entry] if not p['fresh']]
    assert len(closed) > 0.8 * loss_pause
    assert int(demo.polls[0]['t'] // 86400000) + 1 == int(demo.polls[-1]['t'] // 86400000)
    # the third basket was opened on the volatility unit of the H1 bar that closed in between, not on the first's
    assert demo.polls[i_last]['levels']['units'] == demo.polls[i_first]['levels']['units']
    assert demo.polls[i_entry]['vol'] != demo.polls[min(E.requests_by_poll(demo))]['vol']
    _same(demo, on)
    _unheld(on)

