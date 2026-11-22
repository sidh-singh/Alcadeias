"""
The account's deposits and withdrawals, as the safety needs them (spec 5.5 / 5.7): MT5PositionHelper.get_cash_deals.

The safety's percentages must not move when the owner pays money in or takes it out, so it asks for the balance
operations the broker booked -- deals of type DEAL_TYPE_BALANCE, without a symbol and without a magic number --
and tells them from trading results. A read that fails is not "no deposit": it answers None, and the safety then
waits for a read that works. (The poll loop's use of it -- when to read, what to hand the Tracker -- is tested with
the Tracker in the loop.)
"""
from conftest import MAGIC, F, market


def _helper(mods, seconds=600):
    fake, clock = market(seconds)
    m = mods(fake=fake, clock=clock)
    return m, m.mt5_helper.MT5PositionHelper(fake)


def test_deposits_and_withdrawals_and_nothing_else_oldest_first(mods):
    m, h = _helper(mods)
    now = m.clock.time()
    late = m.fake.add_balance_operation(-250.0, time_s=now - 10)            # a withdrawal
    early = m.fake.add_balance_operation(1500.0, time_s=now - 3600.25)      # the first deposit
    m.fake.add_deal(1, 1, 1, 0.01, 2000.0, -12.5, now - 600, magic=MAGIC)  # a trade of this bot: not cash
    m.fake.add_deal(2, 0, 1, 0.05, 2000.0, 40.0, now - 500, magic=0)       # a trade by hand: not cash either
    got = h.get_cash_deals(now - 86400, now + 86400)
    assert got == [{'ticket': early, 'amount': 1500.0, 'time': now - 3600.25},
                   {'ticket': late, 'amount': -250.0, 'time': now - 10}]
    assert all(isinstance(c['time'], float) and isinstance(c['ticket'], int) for c in got)


def test_only_the_window_asked_for_is_read(mods):
    m, h = _helper(mods)
    now = m.clock.time()
    m.fake.add_balance_operation(100.0, time_s=now - 7200)
    inside = m.fake.add_balance_operation(200.0, time_s=now - 60)
    asked = []
    get = m.fake.history_deals_get

    def spy(date_from, date_to, **k):
        asked.append((date_from.timestamp(), date_to.timestamp(), date_from.tzinfo is not None))
        return get(date_from, date_to, **k)
    m.fake.history_deals_get = spy
    got = h.get_cash_deals(now - 3600, now + 86400)
    assert [c['ticket'] for c in got] == [inside]
    assert asked == [(now - 3600, now + 86400, True)]                       # one read, in UTC


def test_an_account_without_cash_lines_answers_an_empty_list(mods):
    m, h = _helper(mods)
    now = m.clock.time()
    assert h.get_cash_deals(now - 86400, now) == []


def test_a_history_that_cannot_be_read_answers_none_never_an_exception(mods):
    m, h = _helper(mods)
    now = m.clock.time()
    m.fake.add_balance_operation(100.0, time_s=now - 60)
    m.fake.history_none = True                                              # the terminal answers None
    assert h.get_cash_deals(now - 86400, now) is None
    m.fake.history_none = False

    def boom(*a, **k):
        raise RuntimeError('IPC broken')
    m.fake.history_deals_get = boom
    assert h.get_cash_deals(now - 86400, now) is None
    assert h.get_cash_deals('not a time', now) is None


def test_a_deal_the_terminal_describes_only_in_part_is_left_out(mods):
    m, h = _helper(mods)
    now = m.clock.time()
    good = m.fake.add_balance_operation(300.0, time_s=now - 30)
    broken = F.types.SimpleNamespace(type=m.fake.DEAL_TYPE_BALANCE, ticket=None, profit=5.0, time=int(now))
    real = m.fake.history_deals_get
    m.fake.history_deals_get = lambda *a, **k: tuple(real(*a, **k)) + (broken,)
    assert [c['ticket'] for c in h.get_cash_deals(now - 86400, now)] == [good]
