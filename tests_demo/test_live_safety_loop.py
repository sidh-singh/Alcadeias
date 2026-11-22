"""
The auto-safety in the poll loop (app.py, spec 5.7, 5.8, 6.2, 6.3), both loops, on the fake terminal with the
real safety.py and its files in the test's own account folder (tmp_path / ACCOUNT_FOLDER, beside the bot's
tmp_path / 'bot_output'):
  * blocked or held: no entry, no ladder add, no pyramid -- and buy() / sell() refuse what a test slips past the
    poll's own tests (open_guard) -- while every exit still fires in its poll;
  * an unblock lets the bot trade on as if it had never been blocked; the switch OFF, or ON and never tripped, sends
    exactly the requests of a bot without the safety;
  * without a usable Tracker, or one that fails: blocked while ON, trading again once OFF is pressed;
  * the losing-trades rule: each closed trade counted once, with all its legs, also across a restart between the
    close and its result, and after 10 minutes without a result;
  * 5.8: a pyramid missed in a block by more than one add step: no more adds for that trade;
  * an old bot on this MetaTrader 5 (6.2 B), another program trading this symbol (6.3).
The Turtle's crafted long trip (test_turtle_bot.py: entry at 457.5 s, adds at 840.6, 1137.7 and 1434.8 s, every
leg closed at its stop at 2227.9 s, the end at 3000 s) is the market of most of them.
"""
import importlib.util
import json
import os
import types

import pytest

import test_turtle_bot as TB
from conftest import DEFAULTS, F, MAGIC, NO_LADDER, ROOT, SCALED, START, market, run_bot
from conftest import differs, found

_spec = importlib.util.spec_from_file_location('safety_of_the_tests', ROOT / 'safety.py')
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

OLD_TERMINAL = r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'


def acct(tmp_path):
    """The account folder of every bot of this test (beside tmp_path / 'bot_output')."""
    return tmp_path / str(DEFAULTS['ACCOUNT_FOLDER'])


def block_file(tmp_path, restart_id='start'):
    """An account block of the counting under `restart_id`, as the bot that met a limit first leaves it."""
    folder = acct(tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    with open(S.block_path(str(folder), restart_id), 'w', encoding='utf-8') as f:
        f.write('{}')


def press(tmp_path, action, clock):
    """safety.bat <action> on the server (no PIN)."""
    ok, msg = S.press(str(acct(tmp_path)), action, None, 'command line', clock.time(), need_pin=False)
    assert ok, msg


def status_of(tmp_path):
    with open(S.status_path(str(acct(tmp_path)), DEFAULTS['BRANCH']), encoding='utf-8') as f:
        return json.load(f)


def names(run):
    return [e['event'] for e in run.events]


def turtle(tmp_path, segments=None, restarts=(), at=(), on_bot=None, overrides=None, books=None, setup=None,
           **kw):
    """The Turtle bot on the crafted market (default: the long trip); `at` = [(seconds after START, fn(fake))]."""
    fake, clock = TB._market(segments or TB._long_trip(), restarts=restarts)
    for t, fn in at:
        fake.at(START + t, fn)
    if setup is not None:
        setup(fake, clock)
    run = TB._run(fake, clock, tmp_path / 'state', overrides=overrides, on_bot=on_bot, books=books, **kw)
    run.fake, run.clock = fake, clock
    return run


def orders(fake):
    return [dict(o) for o in fake.orders]


def opens_after(fake, t):
    return [o for o in TB._opens(fake) if o['_t_ms'] / 1000.0 >= START + t]


def recording_results(calls):
    """on_bot: every Tracker.on_trade_closed of every bot of the run, as (bot, trade_key, net_pl)."""
    def on_bot(bot, n):
        start = bot._safety_start

        def wrapped(symbol):
            ok = start(symbol)
            tr = bot._tracker
            if tr is not None and not getattr(tr, '_recorded', False):
                real = tr.on_trade_closed

                def counted(now, key, pnl):
                    calls.append((n, key, pnl))
                    return real(now, key, pnl)
                tr.on_trade_closed = counted
                tr._recorded = True
            return ok
        bot._safety_start = wrapped
    return on_bot


def both(*hooks):
    def on_bot(bot, n):
        for h in hooks:
            if h is not None:
                h(bot, n)
    return on_bot


@pytest.fixture(scope='module')
def ref(tmp_path_factory):
    """The long trip without anything in the way (the safety ON, no limit)."""
    fake, clock = TB._market(TB._long_trip())
    run = TB._run(fake, clock, tmp_path_factory.mktemp('ref'))
    assert not run.errors, run.errors[:3]
    run.fake = fake
    run.opens, run.closes = TB._opens(fake), TB._closes(fake)
    assert len(run.opens) == 4 and len(run.closes) == 4
    return run


def _t(order):
    return order['_t_ms'] / 1000.0 - START


def deep():
    """The long trip, but falling on to 2.5 N below the buy level: deep enough for the stop of a trade of two
    legs (entry and first add), which the long trip never reaches."""
    b, n = TB.LV['buy'], TB.LV['n']
    return TB._long_trip()[:2] + [(b + 1.6 * n, b - 2.5 * n, 900), (b - 2.5 * n, b - 2.0 * n, 300)]


# ───────────────────────────── blocked: nothing new, every exit ─────────────────────────────

def test_blocked_from_the_start_the_turtle_opens_nothing_and_each_poll_says_why(tmp_path, ref):
    block_file(tmp_path)
    run = turtle(tmp_path)
    assert not TB._opens(run.fake) and not run.fake.positions
    holds = [p['open_hold'] for p in run.polls if p['open_hold']]
    assert holds and {h['why'] for h in holds} == {'safety'} and {h['kind'] for h in holds} == {'entry'}
    ev = names(run)
    assert ev.count('SAFETY_BLOCKED') == 1 and 'BUY_EXECUTED' not in ev and 'BUY_REFUSED' not in ev
    skips = [e for e in run.events if e['event'] == 'SAFETY_SKIP']
    assert 1 <= len(skips) <= 4                                   # once per kind and side, again after 15 minutes
    assert skips[0]['details']['hold']['why'] == 'safety' and skips[0]['details']['kind'] == 'entry'


def test_a_block_while_a_turtle_trade_is_open_ends_its_adds_and_its_stop_still_closes_every_leg(tmp_path, ref):
    """The block comes after the first add: no more add, and each leg is closed in the very poll the price reaches
    the trade's stop (the book's own exit), as unblocked."""
    t_block = _t(ref.opens[1]) + 5.0
    books = []
    run = turtle(tmp_path, segments=deep(), at=[(t_block, lambda f: block_file(tmp_path))], books=books)
    opens = TB._opens(run.fake)
    assert [o['_t_ms'] for o in opens] == [o['_t_ms'] for o in ref.opens[:2]]      # the entry and one add, no more
    closes = TB._closes(run.fake)
    assert len(closes) == 2 and not run.fake.positions
    # the stop of the 2-leg trade, and the first tick at or below it: the close went out at the next poll
    stop = [b['stop'] for b in books if b['side'] == 1 and b['_t'] < closes[0]['_t_ms'] / 1000.0][-1]
    fake = run.fake
    hit = next(int(t) for t, b in zip(fake.t_ms, fake.bid) if t / 1000.0 > START + t_block and b <= stop)
    assert 0 <= closes[0]['_t_ms'] - hit <= 1500
    held = [p['open_hold'] for p in run.polls if p['open_hold']]
    assert held and {h['kind'] for h in held} == {'pyramid'} and {h['why'] for h in held} == {'safety'}


def test_a_blocked_turtle_trade_closes_at_the_same_moment_as_an_unblocked_one(tmp_path, ref):
    """A restart after the last add: from it on the blocked bot and the unblocked one send the same closes at the
    same times (the exits are never behind the safety)."""
    t_r = _t(ref.opens[3]) + 30.0
    free = turtle(tmp_path / 'free', restarts=(t_r,))
    blocked = turtle(tmp_path, restarts=(t_r,), on_bot=lambda bot, n: block_file(tmp_path) if n == 1 else None)
    assert blocked.restarts == free.restarts == 1
    assert not differs(TB._closes(blocked.fake), TB._closes(free.fake)) and len(TB._closes(free.fake)) == 4
    assert 'SAFETY_BLOCKED' in names(blocked) and 'SAFETY_BLOCKED' not in names(free)


def test_an_unblock_lets_the_turtle_trade_as_if_it_had_never_been_blocked(tmp_path, ref):
    block_file(tmp_path)
    run = turtle(tmp_path, at=[(200.0, lambda f: press(tmp_path, 'unblock', f.clock))])
    assert not differs(orders(run.fake), orders(ref.fake))
    ev = names(run)
    assert ev.index('SAFETY_BLOCKED') < ev.index('SAFETY_UNBLOCKED') < ev.index('BUY_EXECUTED')


# ───────────────────────────── the switch, and no usable safety ─────────────────────────────

def _no_tracker(bot, n):
    """A safety that cannot be built (e.g. its folder cannot be made): no Tracker at all."""
    bot._safety_start = lambda symbol: False


def _raising_poll(bot, n):
    start = bot._safety_start

    def wrapped(symbol):
        ok = start(symbol)
        if bot._tracker is not None:
            def poll(*a, **k):
                raise RuntimeError('the safety check broke')
            bot._tracker.poll = poll
        return ok
    bot._safety_start = wrapped


@pytest.mark.parametrize('broken', [_no_tracker, _raising_poll], ids=['no_tracker', 'raising_poll'])
def test_without_a_usable_safety_nothing_opens_while_on_and_trading_resumes_once_off_is_pressed(tmp_path, ref,
                                                                                               broken):
    on = turtle(tmp_path / 'on', on_bot=broken)
    assert not TB._opens(on.fake)
    held = [p['open_hold'] for p in on.polls if p['open_hold']]
    assert held and {h['why'] for h in held} == {'safety'}
    assert 'SAFETY_ERROR' in names(on)
    # the same, and the owner turns the safety OFF before the breakout: the bot trades as the strategy says
    off = turtle(tmp_path, on_bot=broken, at=[(300.0, lambda f: press(tmp_path, 'off', f.clock))])
    assert not differs(orders(off.fake), orders(ref.fake))


@pytest.mark.slow
def test_off_or_on_and_never_tripped_sends_the_requests_of_a_bot_without_the_safety(tmp_path):
    """The basket loop on a market of many baskets, some lost: (a) no safety at all (the Tracker's two places in
    the poll stubbed out); (b) the limits of the branch as written, never reached here; (c) a limit of one losing
    trade, with the switch OFF: every request, its time included, is the same. (d) The same limit ON blocks after
    the first loss: the safety is really in the loop."""
    def run(sub, ov, on_bot=None):
        fake, clock = market(2400, seed=21)
        r = run_bot(fake, clock, overrides={**SCALED, **ov}, state_dir=tmp_path / sub, on_new_bot=on_bot)
        r.fake = fake
        return r

    def stubbed(bot, n):
        bot._safety_start = lambda symbol: True
        bot._safety_poll = lambda symbol, account_info: (setattr(bot, '_opens_stop', None) or
                                                         {'enabled': True, 'blocked': False, 'hold': False})
        bot._safety_after_orders = lambda *a, **k: None
    bare = run('bare', {}, stubbed)
    limits = {k: DEFAULTS.get(k) for k in ('SAFETY_DROP_PCT', 'SAFETY_DAY_PCT', 'SAFETY_STREAK_N')}
    from conftest import AS_WRITTEN
    as_written = run('as_written', {k: AS_WRITTEN[k] for k in limits})
    off = run('off', {'SAFETY_STREAK_N': 1, 'SAFETY_DEFAULT_ON': False})
    on = run('on', {'SAFETY_STREAK_N': 1})
    lost = [b for b in F_baskets(bare.fake) if b['pnl'] < 0]
    assert len(F_baskets(bare.fake)) >= 4 and lost
    assert 'SAFETY_BLOCKED' not in names(as_written)
    assert orders(as_written.fake) == orders(bare.fake) == orders(off.fake)
    assert len(TB._opens(on.fake)) < len(TB._opens(bare.fake)) and 'SAFETY_BLOCKED' in names(on)


def F_baskets(fake):
    from conftest import baskets
    return baskets(fake, magic=MAGIC)


# ───────────────────────────── the basket's add and entry ─────────────────────────────

@pytest.mark.slow
def test_a_held_ladder_add_is_not_sent_its_basket_keeps_its_arming_and_still_closes(tmp_path):
    """The flag of the poll (here forced to 'safety' from a moment inside a basket, before its add): no add, the
    arming as the votes have it, and the basket closes at its stop or target as it would."""
    ov = dict(SCALED, STOP_VOL=6.0, TARGET_VOL=3.0)           # (test_ladder.py: room for the add)
    fake0, clock0 = market(1800, seed=4)
    ref = run_bot(fake0, clock0, overrides=ov, state_dir=tmp_path / 'ref')
    adds = [e for e in ref.events if e['event'] in ('BUY_MORE_EXECUTED', 'SELL_MORE_EXECUTED')]
    assert adds, 'the market has no ladder add'
    t_hold = adds[0]['t'] / 1000.0 - 20.0

    def held_from(bot, n):
        check = bot._opens_check

        def forced(view, now):
            return {'why': 'safety', 'until': None, 'refusals': 0} if now >= t_hold else check(view, now)
        bot._opens_check = forced
    fake, clock = market(1800, seed=4)
    run = run_bot(fake, clock, overrides=ov, state_dir=tmp_path / 'run', on_new_bot=held_from)
    late = [o for o in fake.orders if o['_t_ms'] / 1000.0 >= t_hold and 'position' not in o]
    assert not late                                                 # no add, no entry from then on
    kinds = {p['open_hold']['kind'] for p in run.polls if p['open_hold']}
    assert 'add' in kinds
    armed = [p['ladder_armed'] for p in run.polls if p['open_hold'] and p['open_hold']['kind'] == 'add']
    assert any(armed)                                               # (the arming was left as the votes had it)
    closes = [o for o in fake.orders if 'position' in o and o['_t_ms'] / 1000.0 >= t_hold]
    assert closes                                                   # the basket still closed


def test_open_guard_refuses_an_open_and_never_a_close(mods):
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    seen = []
    bot._install_order_guard()
    bot.position_helper.order_observer = lambda *a: seen.append(a)
    helper = bot.position_helper
    assert helper.open_guard is not None and helper.order_guard is not None
    bot._opens_stop = {'why': 'safety', 'until': None, 'refusals': 0}
    with bot.mt5_lock:
        assert helper.buy('XAUUSDm', 0.01, sl=0.0, tp=0.0, auto_sltp=False) is None
        assert helper.sell('XAUUSDm', 0.01, sl=0.0, tp=0.0, auto_sltp=False) is None
    assert m.fake.orders == [] and [a[2] for a in seen] == ['safety', 'safety']
    assert all(a[4] and set(a[4]) == {'bid', 'ask', 't_msc'} for a in seen)     # the quote, beside the request
    assert all(set(a[0]) == set(seen[0][0]) and 'quote' not in a[0] for a in seen)
    # a close goes through whatever the flag says
    m.fake.add_position(0, 0.01, 2000.0, m.clock.time() - 60, magic=MAGIC)
    with bot.mt5_lock:
        res = helper.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 1 and not m.fake.positions
    # the flag cleared: the open goes out, request exactly as without a guard
    bot._opens_stop = None
    with bot.mt5_lock:
        r = helper.buy('XAUUSDm', 0.01, sl=1990.0, tp=0.0, auto_sltp=False)
    assert r is not None and r.retcode == m.fake.TRADE_RETCODE_DONE
    sent = {k: v for k, v in m.fake.orders[-1].items() if k != '_t_ms'}
    assert set(sent) == {'action', 'symbol', 'volume', 'type', 'price', 'type_time', 'type_filling', 'sl', 'tp',
                         'magic', 'comment'}


# ───────────────────────────── the losing-trades rule: each trade once, with all its legs ─────────────────────────────

def _legs_pnl(fake, ids):
    return round(sum(d.profit + d.swap + d.commission + d.fee for d in fake.deals if d.position_id in set(ids)), 2)


def test_a_turtle_close_refused_once_then_finished_counts_once_with_all_its_legs(tmp_path, ref):
    t_exit = _t(ref.closes[0])
    calls = []

    def refuse_one(fake, clock):
        orig = fake.positions_get

        def positions_get(symbol=None, **k):
            now = fake.clock.time() - START
            fake.fail_close_tickets = ({fake.positions[0]['ticket']} if t_exit - 5 <= now < t_exit + 20
                                       and fake.positions else set())
            return orig(symbol=symbol, **k)
        fake.positions_get = positions_get
    run = turtle(tmp_path, setup=refuse_one, on_bot=recording_results(calls))
    closes = [e['details'] for e in run.events if e['event'] == 'CLOSE_BUY']
    assert closes[0]['failed'] == 1 and closes[-1]['failed'] == 0 and len(closes) >= 2
    ids = sorted({o['position'] for o in TB._closes(run.fake)})
    assert len(ids) == 4
    assert calls == [(0, min(ids), _legs_pnl(run.fake, ids))]
    assert calls[0][2] < 0                                          # the long trip loses at its stop


def test_a_restart_between_a_close_and_its_result_still_counts_the_trade_once(tmp_path, ref):
    """The deal history shows the closing deals only 60 s after the close; the bot restarts 20 s after it. The
    trade waits in state/safety_closes.json, and the bot after the restart counts it, once."""
    t_exit = _t(ref.closes[0])
    calls = []

    def late_history(fake, clock):
        orig = fake.history_deals_get

        def history_deals_get(date_from=None, date_to=None, **k):
            out = orig(date_from, date_to, **k)
            if out is None or fake.clock.time() - START >= t_exit + 60:
                return out
            return tuple(d for d in out if not (d.entry == 1 and d.time - START >= t_exit - 1))
        fake.history_deals_get = history_deals_get
    run = turtle(tmp_path, restarts=(t_exit + 20,), setup=late_history, on_bot=recording_results(calls))
    assert run.restarts == 1
    ids = sorted({o['position'] for o in TB._closes(run.fake)})
    assert calls == [(1, min(ids), _legs_pnl(run.fake, ids))]
    saved = json.loads((tmp_path / 'state' / 'safety_closes.json').read_text(encoding='utf-8'))
    assert saved['queue'] == [] and saved['turtle'] is None
    assert saved['branch'] == DEFAULTS['BRANCH'] and 'login_sha' in saved and not found(json.dumps(saved), str(F.ACCOUNT_LOGIN))
    state = json.loads((tmp_path / 'state' / 'safety_state.json').read_text(encoding='utf-8'))
    assert [str(k) for k in state['counted_trades']].count(str(min(ids))) == 1 and state['streak'] == 1


def test_a_result_the_history_never_shows_counts_after_ten_minutes_with_what_the_bot_saw(tmp_path, ref):
    t_exit = _t(ref.closes[0])
    calls = []
    run = turtle(tmp_path, at=[(t_exit - 2, lambda f: setattr(f, 'history_none', True))],
                 on_bot=recording_results(calls))
    assert len(calls) == 1
    unknown = [e for e in run.events if e['event'] == 'CLOSE_RESULT_UNKNOWN']
    assert len(unknown) == 1 and 600 <= unknown[0]['t'] / 1000.0 - START - t_exit <= 605
    seen = [e['details']['total_profit'] for e in run.events if e['event'] == 'CLOSE_BUY'][0]
    assert calls[0][2] == pytest.approx(seen) and seen < 0


def _pos(pid, profit=0.0):
    """A position of this bot as the terminal lists it (what the close-queue code reads of it)."""
    return types.SimpleNamespace(ticket=pid, identifier=pid, profit=profit, time=START, time_msc=START * 1000)


def _basket_bot(mods, tmp_path, ids=(101, 102, 103)):
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run(), state_dir=tmp_path / 'state')
    now = m.clock.time()
    basket = bot._new_basket('BUY', 1, {'target_usd_per_unit': 5.0, 'stop_usd_per_unit': 5.0, 'gap_px': 1.0,
                                        'vol_unit_raw': None, 'vol_unit': None}, now - 600)
    basket['ids'], basket['first_time'] = list(ids), now - 600
    bot._closes, bot._closes_dirty = {'turtle': None, 'queue': []}, False
    return bot, {'basket': basket, 'last_close': None}, now


def _closed(bot, state, positions, closed, failed, now, reason='stop_loss'):
    lc = bot._after_close('XAUUSDm', state, 'BUY', {'closed_count': len(closed), 'failed_count': failed,
                                                    'closed_tickets': list(closed)}, positions, reason, now)
    bot._closes_basket(lc)
    return lc


def test_a_basket_closed_at_once_keeps_the_pl_of_its_close_to_stand_in_for_its_result(mods, tmp_path):
    bot, state, now = _basket_bot(mods, tmp_path)
    legs = {101: -30.0, 102: -34.0, 103: 4.0}
    lc = _closed(bot, state, {'total_profit': -60.0, 'positions': [_pos(i, p) for i, p in legs.items()]},
                 legs, 0, now)
    assert lc is not None and 'partial_close' not in lc
    assert [(e['trade_key'], e['ids'], e['decision_pnl']) for e in bot._closes['queue']] == [(101, [101, 102, 103],
                                                                                              -60.0)]


def test_a_basket_closed_over_two_polls_has_no_pl_of_its_close_to_count(mods, tmp_path):
    """A leg the terminal refused to close once: the close takes two polls, and the P/L the second one sees is that
    of the last leg only (+4.00; the basket lost 60.00). Had the history never shown the result, that figure would
    have counted a losing trade as a win and set the losing-trades count back to 0. Such a close has no P/L of its
    own to stand in: after 10 minutes without the history it counts as a loss."""
    bot, state, now = _basket_bot(mods, tmp_path)
    legs = {101: -30.0, 102: -34.0, 103: 4.0}
    assert _closed(bot, state, {'total_profit': -60.0, 'positions': [_pos(i, p) for i, p in legs.items()]},
                   (101, 102), 1, now) is None
    assert state['basket']['close_pending'] is True and bot._closes['queue'] == []
    lc = _closed(bot, state, {'total_profit': 4.0, 'positions': [_pos(103, 4.0)]}, (103,), 0, now + 1, 'close_retry')
    assert lc is not None and lc['partial_close'] is True and state['basket'] is None
    assert [(e['trade_key'], e['ids'], e['decision_pnl']) for e in bot._closes['queue']] == [(101, [101, 102, 103],
                                                                                              None)]


def test_a_basket_leg_its_close_took_but_no_read_had_listed_leaves_no_pl_of_the_close(mods, tmp_path):
    """An add filled a moment ago is not listed yet; the stop's close finds and closes it with the entry. The P/L of
    this poll's positions is the entry's alone: not the trade's."""
    bot, state, now = _basket_bot(mods, tmp_path, ids=(101, 102))
    bot._set_unlisted(state['basket'], {102: now - 0.5})
    lc = _closed(bot, state, {'total_profit': -3.0, 'positions': [_pos(101, -3.0)]}, (101, 102), 0, now)
    assert lc is not None and lc['partial_close'] is True
    assert [(e['ids'], e['decision_pnl']) for e in bot._closes['queue']] == [([101, 102], None)]


@pytest.mark.parametrize('ever, decision', [((202, 203), 4.0), ((201, 202, 203), None)],
                         ids=['every leg in this close', 'a leg closed by hand before'])
def test_a_turtle_close_keeps_its_pl_only_when_it_took_every_leg_the_trade_ever_had(mods, ever, decision):
    """A leg closed by hand inside the stop leaves the Turtle's trade on (its stop kept); at the trade's exit the
    positions' P/L holds only the legs left. So that exit has no P/L of its own to stand in for the result."""
    m = mods()
    bot = F.make_bot(m, m.fake, 'XAUUSDm', F.Run())
    t = m.clock.time() - 3600
    bot._closes = {'turtle': {'entry_time': t, 'ids': list(ever), 'decision_pnl': None}, 'queue': []}
    st = {'side': 1, 'entry_time': t, 'closing': False,
          'legs': [{'ticket': 202, 'price': 2000.0, 'time': t}, {'ticket': 203, 'price': 2001.0, 'time': t + 60}]}
    bot._turtle_close_seen(st, {'total_profit': 4.0, 'positions': [_pos(202, 1.5), _pos(203, 2.5)]})
    assert [(e['trade_key'], e['ids'], e['decision_pnl']) for e in bot._closes['queue']] == [
        (min(ever), sorted(ever), decision)]
    assert bot._closes['turtle'] is None


# ───────────────────────────── 5.8: a pyramid missed during a block ─────────────────────────────

def test_a_pyramid_the_block_held_back_is_taken_after_it_while_within_one_add_step(tmp_path, ref):
    """Blocked from just after the first add until a little after the price passed the second add's level (less
    than one add step beyond it): that add goes out on the first poll after the unblock, and the trade takes its
    third add as before."""
    t1, t2 = _t(ref.opens[1]) + 5.0, _t(ref.opens[2]) + 20.0
    run = turtle(tmp_path, at=[(t1, lambda f: block_file(tmp_path)),
                               (t2, lambda f: press(tmp_path, 'unblock', f.clock))])
    opens = TB._opens(run.fake)
    assert len(opens) == 4 and _t(opens[2]) - t2 <= 3.0
    assert 'TURTLE_ADDS_STOPPED' not in names(run)


def test_a_pyramid_missed_by_more_than_one_add_step_stops_the_adds_of_that_trade(tmp_path, ref):
    """Blocked from just after the first add until after the last add of the free run (the price far beyond the
    level held back): no more adds for this trade, its stop and exit as before; the side file says so."""
    t1, t2 = _t(ref.opens[1]) + 5.0, _t(ref.opens[3]) + 50.0
    run = turtle(tmp_path, segments=deep(), at=[(t1, lambda f: block_file(tmp_path)),
                                                (t2, lambda f: press(tmp_path, 'unblock', f.clock))])
    opens = TB._opens(run.fake)
    assert len(opens) == 2 and not run.fake.positions and len(TB._closes(run.fake)) == 2
    stopped = [e for e in run.events if e['event'] == 'TURTLE_ADDS_STOPPED']
    assert len(stopped) == 1 and stopped[0]['t'] / 1000.0 - START >= t2
    side = json.loads((tmp_path / 'state' / f'{TB.SYMBOL}_turtle_side.json').read_text(encoding='utf-8'))
    assert side['trade'] is None                                    # (cleared at the exit)


def test_the_stop_of_adds_is_kept_across_a_restart(tmp_path, ref):
    t1, t2 = _t(ref.opens[1]) + 5.0, _t(ref.opens[3]) + 50.0
    run = turtle(tmp_path, segments=deep(), restarts=(t2 + 60.0,),
                 at=[(t1, lambda f: block_file(tmp_path)), (t2, lambda f: press(tmp_path, 'unblock', f.clock))])
    assert run.restarts == 1 and len(TB._opens(run.fake)) == 2 and not run.fake.positions
    assert len(TB._closes(run.fake)) == 2


# ───────────────────────────── 6.2 B: an old bot on this MetaTrader 5 ─────────────────────────────

def _old_bot_files(tmp_path, fake, clock, until_s):
    """The old bot's files in the folder above OUTPUT_DIR, rewritten every 30 s of the fake clock up to until_s."""
    path = tmp_path / 'XAUUSDm.json'

    def touch(f):
        path.write_text('{}', encoding='utf-8')
        t = f.clock.time()
        os.utime(path, (t, t))
    for s in range(0, int(until_s), 30):
        fake.at(START + s, touch)
    touch(fake)


@pytest.mark.parametrize('switch_off', [False, True], ids=['on', 'off'])
def test_an_old_bot_on_this_metatrader_blocks_every_open_whatever_the_switch(tmp_path, ref, switch_off):
    def setup(fake, clock):
        _old_bot_files(tmp_path, fake, clock, 3000)
        if switch_off:
            folder = acct(tmp_path)
            folder.mkdir(parents=True, exist_ok=True)
            S.press(str(folder), 'off', None, 'command line', clock.time(), need_pin=False)
    run = turtle(tmp_path, setup=setup, credentials=F.account_credentials(None, terminal_path=OLD_TERMINAL))
    assert not TB._opens(run.fake)
    held = {p['open_hold']['why'] for p in run.polls if p['open_hold']}
    assert held == {'old_bot'}
    assert names(run).count('OLD_BOT_SAME_TERMINAL') == 1


def test_with_an_old_bot_on_this_metatrader_the_open_trade_is_still_closed_at_its_stop(tmp_path, ref):
    t_r = _t(ref.opens[3]) + 30.0
    free = turtle(tmp_path / 'free', restarts=(t_r,))

    def setup(fake, clock):
        def go(f):
            _old_bot_files(tmp_path, f, f.clock, 3000)
        fake.at(START + t_r + 1, go)
    run = turtle(tmp_path, restarts=(t_r,), setup=setup,
                 credentials=F.account_credentials(None, terminal_path=OLD_TERMINAL))
    assert not differs(TB._closes(run.fake), TB._closes(free.fake)) and 'OLD_BOT_SAME_TERMINAL' in names(run)


# ───────────────────────────── 6.3: another program trading this symbol ─────────────────────────────

def _close_all_outside(reason):
    """All of this bot's positions closed outside it 60 s after the second add, with deals of `reason` and no
    magic number: DEAL_REASON_EXPERT = another program, DEAL_REASON_CLIENT = by hand."""
    def setup(fake, clock, at):
        def go(f):
            b, a = f.quote()
            for p in list(f.positions):
                price = b if p['type'] == 0 else a
                profit = f._pos_profit(p, price, price)
                f.balance += profit
                f._deal(p, 1, p['volume'], price, profit, 0, '', f.clock.now_ms, reason=reason)
                f.positions.remove(p)
        fake.at(START + at, go)
    return setup


@pytest.mark.parametrize('who', ['another_program', 'by_hand', 'broker_stop'])
def test_only_a_close_by_another_program_blocks_this_bot(tmp_path, ref, who):
    at = _t(ref.opens[2]) + 60.0

    def setup(fake, clock):
        if who == 'another_program':
            _close_all_outside(fake.DEAL_REASON_EXPERT)(fake, clock, at)
        elif who == 'by_hand':
            _close_all_outside(fake.DEAL_REASON_CLIENT)(fake, clock, at)
        else:
            fake.at(START + at, lambda f: [f.close_by_broker(p['ticket']) for p in list(f.positions)])
    run = turtle(tmp_path, setup=setup)
    assert 'TURTLE_CLOSED_OUTSIDE' in names(run)
    st = status_of(tmp_path)
    if who == 'another_program':
        assert st['bot_blocked'] is True and 'another program' in ' '.join(st['reasons'])
        assert 'OTHER_PROGRAM' in names(run) and 'SAFETY_BLOCKED' in names(run)
    else:
        assert st['bot_blocked'] is False and 'OTHER_PROGRAM' not in names(run)


def test_the_old_ladder_bots_own_trades_on_this_symbol_block_this_bot_and_are_reported(tmp_path, ref):
    def setup(fake, clock):
        fake.add_position(0, 0.02, 60000.0, START - 600, magic=0, comment='')
        fake.positions[-1]['tp'] = 120000.0                         # the old request: tp = price + 100%
    seen = []

    def watch(bot, n):
        real = bot._foreign_now
        bot._foreign_now = lambda own=None: (lambda v: (seen.append(v), v)[1])(real(own))
    run = turtle(tmp_path, setup=setup, on_bot=watch)
    assert not TB._opens(run.fake)
    ev = names(run)
    assert ev.count('FOREIGN_POSITIONS') == 1 and ev.count('OTHER_PROGRAM') == 1 and 'SAFETY_BLOCKED' in ev
    assert seen and seen[-1]['positions'] == 1 and seen[-1]['examples'][0]['magic'] == 0
    assert seen[-1]['examples'][0]['ticket'].startswith('...') and seen[-1]['old_bot_same_terminal'] is False
    assert status_of(tmp_path)['bot_blocked'] is True
    text = [e for e in run.events if e['event'] == 'FOREIGN_POSITIONS'][0]['details']['problem']
    assert text.startswith(f"Trades that are not this bot's are open on {TB.SYMBOL} in this account (magic 0)")


def test_a_foreign_trade_without_the_old_bots_mark_is_reported_but_blocks_nothing(tmp_path, ref):
    def setup(fake, clock):
        fake.add_position(0, 0.02, 60000.0, START - 600, magic=271023, comment='live10_bt2')
    run = turtle(tmp_path, setup=setup)
    assert [o['_t_ms'] for o in TB._opens(run.fake)] == [o['_t_ms'] for o in ref.opens]
    ev = [e for e in run.events if e['event'] == 'FOREIGN_POSITIONS']
    assert len(ev) == 1 and 'the BTC bot of account 10' in ev[0]['details']['problem']
    assert 'OTHER_PROGRAM' not in names(run)


# ───────────────────────────── each new hook that fails: the stop still closes ─────────────────────────────

def _raise(*a, **k):
    raise RuntimeError('broken on purpose')


HOOKS = {
    'tracker.poll': lambda bot: setattr(bot._tracker, 'poll', _raise),
    'tracker.flush': lambda bot: setattr(bot._tracker, 'flush', _raise),
    'tracker.take_events': lambda bot: setattr(bot._tracker, 'take_events', _raise),
    'tracker.needs_cash': lambda bot: setattr(bot._tracker, 'needs_cash', _raise),
    'tracker.on_trade_closed': lambda bot: setattr(bot._tracker, 'on_trade_closed', _raise),
    'get_cash_deals': lambda bot: setattr(bot.position_helper, 'get_cash_deals', _raise),
    'basket_pnl': lambda bot: setattr(bot, '_basket_pnl', _raise),
    'journal': lambda bot: setattr(bot, '_journal', _raise),
    'foreign_note': lambda bot: setattr(bot, '_old_bot_trades_text', _raise),
    'opens_check': lambda bot: setattr(bot, '_opens_check', _raise),
    'safety_poll_view': lambda bot: setattr(bot, '_safety_poll_view', _raise),
    'closes_save': lambda bot: setattr(bot, '_save_closes', _raise),
    'safety_events': lambda bot: setattr(bot, '_safety_events', _raise),
    'clean_ids': lambda bot: setattr(bot, '_clean_ids', _raise),
}


@pytest.mark.parametrize('hook', sorted(HOOKS))
def test_each_new_hook_made_to_raise_still_lets_the_stop_close_in_its_poll(tmp_path, ref, hook):
    t_r = _t(ref.opens[3]) + 30.0
    free = turtle(tmp_path / 'free', restarts=(t_r,))

    def broken(bot, n):
        if n != 1:
            return
        start = bot._safety_start

        def wrapped(symbol):
            ok = start(symbol)
            HOOKS[hook](bot)
            return ok
        bot._safety_start = wrapped
    run = turtle(tmp_path, restarts=(t_r,), on_bot=broken)
    assert not differs(TB._closes(run.fake), TB._closes(free.fake)) and len(TB._closes(free.fake)) == 4


# ───────────────────────────── the cash read ─────────────────────────────

def test_the_cash_read_is_handed_to_the_next_poll_and_a_deposit_is_no_profit(tmp_path):
    """A deposit while flat: the Tracker gets the balance operations read at the end of the poll before it (time
    of that read, UTC seconds on the bot's clock), and the high moves with the deposit, not the percentages."""
    seen = []

    def watch(bot, n):
        start = bot._safety_start

        def wrapped(symbol):
            ok = start(symbol)
            real = bot._tracker.poll

            def poll(now, balance, cash_deals=None, cash_read_at=None, pending_results=0):
                seen.append((now, balance, None if cash_deals is None else list(cash_deals), cash_read_at))
                return real(now, balance, cash_deals, cash_read_at, pending_results)
            bot._tracker.poll = poll
            return ok
        bot._safety_start = wrapped
    segments = [(TB.LV['buy'] - 400, TB.LV['buy'] - 300, 300)]       # no breakout: flat all along
    run = turtle(tmp_path, segments=segments, on_bot=watch,
                 at=[(100.0, lambda f: f.add_balance_operation(500.0))],
                 overrides={'SAFETY_DROP_PCT': 20.0, 'SAFETY_DAY_PCT': 10.0})
    assert not run.errors, run.errors[:3]
    reads = [s for s in seen if s[2] is not None]
    assert reads and all(s[3] is not None and s[3] <= s[0] and s[0] - s[3] < 3.0 for s in reads)
    dep = [s for s in reads if any(c['amount'] == 500.0 for c in s[2])]
    assert dep and abs(dep[0][2][-1]['time'] - (START + 100)) < 2.0
    assert all(s[2] is None and s[3] is None for s in seen if s not in reads)
    view = status_of(tmp_path)
    assert view['drop']['pct'] == 0.0 and view['drop']['peak'] == pytest.approx(2500.0)
    assert view['state'] == 'on'
