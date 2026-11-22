"""
The rules of safety.py against the conventions the limits were calibrated with (spec 5.1: "These are the conventions
of the calibration replay"): random accounts with a gold and a BTC bot are played twice, once through a plain
restatement of those conventions (`reference` below) and once through safety.decide / count_trade, and must block
at the same bookings, for the same rules, and skip the same trades.

The conventions, as the calibration states them:
  - a rule is checked right after a booking (a closed trade), on the booked balance;
  - DROP: the balance is X % or more below its highest value since the start or the last unblock of the account;
  - DAY: the balance is Y % or more below the balance booked before 00:00 UTC of the booking's day, or below the
    balance at an account unblock later that day;
  - STREAK: N closed trades of that bot in a row with a loss; any other result sets the count to 0;
  - DROP and DAY block both bots, STREAK its own bot; a blocked bot opens nothing, an open trade runs to its close
    and is booked; while the account is blocked nothing new trips;
  - the owner unblocks D hours after a block: after an account block everything counts again from the balance of
    then (the high, the day, both counts); after a STREAK block that bot's count is 0 and nothing else changes.

How a replay must drive the rules (the same holds for a replay through safety.Tracker): poll once with the balance
BEFORE each booking, then with the balance after it. The live bot polls every second, so the first poll of a UTC
day finds the balance of 00:00; a replay that polled only after bookings would hand the day its first loss as its
starting balance. confirm_s=0 with a cash read at the poll's own time judges a booking in the poll that sees it.

Run:  python3 -B -m pytest tests_demo/test_safety_replay.py -q -p no:cacheprovider
"""
import importlib.util
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location('safety_tested_replay', ROOT / 'safety.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()

HOUR, DAY = 3600, 86400
START = 1795219200 + 7 * HOUR                 # 21 Nov 2026 07:00 UTC, in whole seconds
GOLD, BTC = 'acct_x9', 'acct_b9'


def random_account(rng, days, drift, sigma):
    """(time, 'open' / 'close', bot, result) of two bots, each trading one trade after the other; sorted by time,
    closes before opens, gold before BTC, as the calibration books them."""
    events = []
    for bot in (0, 1):
        t = START + rng.randrange(0, 6 * HOUR)
        while t < START + days * DAY:
            length = int(rng.choice([60, 900, HOUR, 5 * HOUR, 30 * HOUR]) * rng.uniform(0.2, 2.0)) + 1
            result = round(rng.gauss(drift, sigma), 2)
            events.append((t, 1, bot, result))
            events.append((t + length, 0, bot, result))
            t += length + int(rng.choice([0, 1, 60, HOUR, 9 * HOUR]) * rng.uniform(0, 2))
    events.sort()
    return [(t, 'close' if kind == 0 else 'open', bot, result) for t, kind, bot, result in events]


def _met(reference_balance, balance, limit):
    if limit is None or not reference_balance > 0:
        return False
    return round((reference_balance - balance) / reference_balance * 100.0, 6) >= limit


def reference(events, drop, day_limit, streak_limits, hold, start_balance=1500.0):
    """The calibration's conventions, written out plainly. Returns the blocks [(time, bot, drop, day, streak)], the
    final balance and how many trades each bot skipped."""
    balance = high = day_start = start_balance
    day = START // DAY
    streak, in_trade, skipped = [0, 0], [False, False], [0, 0]
    account_until, bot_until = None, [None, None]
    blocks = []
    for t, what, bot, result in events:
        if account_until is not None and t >= account_until:           # the owner unblocks the account
            high, day, day_start, streak = balance, account_until // DAY, balance, [0, 0]
            account_until = None
        for k in (0, 1):
            if bot_until[k] is not None and t >= bot_until[k]:         # ...or one bot
                streak[k], bot_until[k] = 0, None
        if what == 'open':
            in_trade[bot] = account_until is None and bot_until[bot] is None
            skipped[bot] += not in_trade[bot]
            continue
        if not in_trade[bot]:
            continue
        in_trade[bot] = False
        if t // DAY != day:
            day, day_start = t // DAY, balance                         # the balance booked before 00:00
        balance += result
        streak[bot] = streak[bot] + 1 if result < 0 else 0
        if account_until is not None:
            continue                                                   # blocked already: nothing new trips
        high = max(high, balance)
        hit_drop, hit_day = _met(high, balance, drop), _met(day_start, balance, day_limit)
        hit_streak = (streak_limits[bot] is not None and bot_until[bot] is None
                      and streak[bot] >= streak_limits[bot])
        if hit_drop or hit_day or hit_streak:
            blocks.append((t, bot, hit_drop, hit_day, hit_streak))
            if hit_drop or hit_day:
                account_until = t + hold
            if hit_streak:
                bot_until[bot] = t + hold
    return blocks, balance, skipped


def through_the_rules(events, drop, day_limit, streak_limits, hold, start_balance=1500.0):
    """The same account through safety.decide and safety.count_trade: two bots with a state each, one account
    folder played by `controls` and `block_files`, and an owner who unblocks `hold` seconds after a block."""
    limits = [S.Limits(drop, day_limit, streak_limits[k]) for k in (0, 1)]
    state = [S.new_state(GOLD), S.new_state(BTC)]
    controls = {'restart_status': 'missing', 'restart_id': None, 'restart_scope': None, 'restart_account_id': None,
                'enabled': True}
    block_files, presses = set(), [0]
    balance = start_balance
    in_trade, skipped = [False, False], [0, 0]
    account_until, bot_until = None, [None, None]
    blocks = []

    def poll(k, t, bal):
        target = controls['restart_id'] or state[k]['period'] or 'start'
        c = dict(controls, block_id=target, block_exists=target in block_files)
        state[k], out = S.decide(state[k], limits[k], float(t), bal, [], float(t), 0, c, confirm_s=0.0)
        if out['tripped']:
            block_files.add(state[k]['period'])                        # the block file of that id
        return out

    def account_blocked(k):
        return S.account_blocked(state[k], {'block_id': state[k]['period'],
                                            'block_exists': state[k]['period'] in block_files})

    for k in (0, 1):
        poll(k, START, balance)
    for t, what, bot, result in events:
        if account_until is not None and t >= account_until:           # press('unblock') on a blocked account
            presses[0] += 1
            new = f'20261121_000000-{presses[0]:06x}'
            controls.update(restart_status='ok', restart_id=new, restart_scope='account', restart_account_id=new)
            for k in (0, 1):
                poll(k, account_until, balance)
            account_until = None
        for k in (0, 1):
            if bot_until[k] is not None and t >= bot_until[k]:
                # (The calibration gives each bot its own D hours. The real Unblock lifts every bot block of the
                # account with one press; played here bot by bot, what it does to one bot is exactly this.)
                state[k] = dict(state[k], streak=0, bot_block=None)
                bot_until[k] = None
        if what == 'open':
            in_trade[bot] = not account_blocked(bot) and state[bot]['bot_block'] is None
            skipped[bot] += not in_trade[bot]
            continue
        if not in_trade[bot]:
            continue
        in_trade[bot] = False
        for k in (0, 1):
            poll(k, t, balance)                                        # the balance before the booking
        blocked_before = account_blocked(0) or account_blocked(1)
        balance += result
        state[bot], happened = S.count_trade(state[bot], limits[bot], float(t), f'{t}-{bot}', result, True)
        hit_streak = any(e['event'] == 'trip' for e in happened)
        outs = [poll(k, t, balance) for k in (0, 1)]                   # ...and after it
        if blocked_before:
            if hit_streak:
                state[bot] = dict(state[bot], bot_block=None)          # (the account unblock would lift it anyway)
            continue
        rules = set()
        for k in (0, 1):
            if outs[k]['tripped']:
                rules |= set(state[k]['account_block']['rules'])
        if rules or hit_streak:
            blocks.append((t, bot, 'DROP' in rules, 'DAY' in rules, hit_streak))
            if rules:
                account_until = t + hold
            if hit_streak:
                bot_until[bot] = t + hold
    return blocks, balance, skipped


@pytest.mark.parametrize('seed', range(8))
def test_random_accounts_block_where_the_calibrations_conventions_block(seed):
    rng = random.Random(1000 + seed)
    total = 0
    for _ in range(6):
        events = random_account(rng, rng.choice([15, 40, 90]), rng.choice([-1.5, -4.0, 0.5]), rng.choice([15, 40, 90]))
        drop = rng.choice([None, 10.0, 15.0, 20.0, 35.0])
        day_limit = rng.choice([None, 5.0, 10.0, 12.5, 20.0])
        streak_limits = (rng.choice([None, 3, 5, 9]), rng.choice([None, 3, 5, 10]))
        hold = int(rng.choice([4, 24, 72, 168]) * HOUR)
        expected = reference(events, drop, day_limit, streak_limits, hold)
        got = through_the_rules(events, drop, day_limit, streak_limits, hold)
        assert got[0] == expected[0], (seed, drop, day_limit, streak_limits, hold)
        assert abs(got[1] - expected[1]) < 1e-6 and got[2] == expected[2]
        total += len(expected[0])
    assert total > 0                                                 # (the accounts of this seed did block)


def test_the_replay_meets_every_kind_of_block():
    """The random accounts above are worth something only if they block for each rule, alone and together."""
    rng = random.Random(4242)
    kinds = set()
    blocks = 0
    for _ in range(40):
        events = random_account(rng, 60, rng.choice([-1.5, -4.0]), rng.choice([40, 90]))
        expected = reference(events, 15.0, 7.5, (3, 4), 24 * HOUR)
        got = through_the_rules(events, 15.0, 7.5, (3, 4), 24 * HOUR)
        assert got == expected
        blocks += len(expected[0])
        kinds |= {(d, y, s) for _, _, d, y, s in expected[0]}
    assert blocks > 150
    assert {(True, False, False), (False, True, False), (False, False, True), (True, True, False)} <= kinds
