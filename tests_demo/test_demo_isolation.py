"""
Demo isolation: every order carries MAGIC and the comment; every position read used for a decision, and
every close, keeps only this bot's positions; units come from the virtual balance (VIRTUAL_START_BALANCE +
this bot's own closed P/L since VIRTUAL_START_DATE) with the live unit rule, re-derived only while flat.
"""
import pytest

from conftest import COMMENT, F, MAGIC, SCALED, START, market, run_bot


@pytest.mark.slow
def test_foreign_positions_are_invisible_and_untouched(tmp_path):
    fake, clock = market(1800, seed=21)
    foreign = [fake.add_position(0, 0.05, 1990.0, START - 7200, magic=0, comment='manual'),
               fake.add_position(1, 0.02, 2010.0, START - 3600, magic=777, comment='other bot')]
    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path)
    assert not run.errors, run.errors[:3]
    mine = [d for d in fake.deals if d.entry == 0 and d.magic == MAGIC]
    assert len(mine) >= 2                                   # it traded although the account held positions
    assert [p['ticket'] for p in fake.positions if p['magic'] != MAGIC] == foreign       # never closed
    assert all(o.get('position') not in foreign for o in fake.orders)
    for o in fake.orders:                                    # opens, adds and closes
        assert o['magic'] == MAGIC and o['comment'] == COMMENT
    # the counts it decided on never included them (a foreign BUY 0.05 and SELL 0.02 are always open)
    assert all(not (p['nb'] and p['ns']) for p in run.polls)


def test_position_reads_and_closes_keep_only_this_bots_positions(mods):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    h = m.mt5_helper.MT5PositionHelper(fake)
    now = clock.time()
    fake.add_position(0, 0.01, 1999.0, now - 50, magic=MAGIC)
    fake.add_position(0, 0.07, 1990.0, now - 60, magic=0)
    fake.add_position(1, 0.03, 2001.0, now - 40, magic=42)
    buy = h.get_buy_positions('XAUUSDm')
    assert buy['count'] == 1 and buy['total_volume'] == 0.01
    assert h.get_sell_positions('XAUUSDm') is None
    res = h.close_by_type('XAUUSDm', 0)
    assert res['closed_count'] == 1 and res['total_positions'] == 1
    assert sorted(p['magic'] for p in fake.positions) == [0, 42]


def test_order_comment_is_cut_to_31_characters(mods):
    h = mods(ORDER_COMMENT='x' * 40).mt5_helper
    assert h.order_comment() == 'x' * 31
    assert mods().mt5_helper.order_comment() == COMMENT
    assert mods(ORDER_COMMENT='mine').mt5_helper.order_comment() == 'mine'


def test_dashboard_deal_history_is_this_bots(mods):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    h = m.mt5_helper.MT5PositionHelper(fake)
    now = clock.time()
    fake.add_deal(1, 1, 1, 0.01, 2000.0, 5.0, now - 30, magic=MAGIC)
    fake.add_deal(2, 1, 1, 0.01, 2000.0, -9.0, now - 20, magic=0)
    deals = h.get_deal_history(F.datetime.fromtimestamp(now - 100, tz=F.timezone.utc),
                               F.datetime.fromtimestamp(now + 100, tz=F.timezone.utc))
    assert [d['profit'] for d in deals] == [5.0]


# ───────────────────────────── the virtual balance ─────────────────────────────

def _bot(mods, balance=2000.0, **ov):
    fake, clock = market(120, balance=balance)
    m = mods(fake=fake, clock=clock, **ov)
    return m, fake, clock, F.make_bot(m, fake, 'XAUUSDm', F.Run())


def test_virtual_balance_counts_this_bots_deals_since_the_start_date(mods):
    m, fake, clock, bot = _bot(mods, balance=50000.0)
    now = clock.time()
    start = m.app._virtual_start_ts()
    fake.add_deal(10, 1, 1, 0.01, 2000.0, 400.0, start - 3600, magic=MAGIC)       # before the start date
    fake.add_deal(11, 1, 1, 0.01, 2000.0, 120.0, start + 3600, magic=MAGIC)
    fake.add_deal(12, 0, 1, 0.01, 2000.0, -20.0, start + 7200, magic=MAGIC, commission=-0.5, swap=-1.25)
    fake.add_deal(13, 1, 1, 0.01, 2000.0, 999.0, start + 7300, magic=555)           # another bot
    # a position of this bot closed from the terminal: its closing deal has no magic but the same position
    pid = fake.add_position(0, 0.01, 2000.0, now - 900, magic=MAGIC)
    fake.positions.clear()
    fake.add_deal(pid, 1, 1, 0.01, 2003.0, 3.0, now - 600, magic=0)
    assert bot._virtual_balance(now) == pytest.approx(2000.0 + 120.0 - 20.0 - 0.5 - 1.25 + 3.0)


def test_virtual_balance_falls_back_to_the_last_value_then_the_start(mods):
    m, fake, clock, bot = _bot(mods)
    now = clock.time()
    fake.add_deal(11, 1, 1, 0.01, 2000.0, 700.0, now - 60, magic=MAGIC)
    assert bot._virtual_balance(now) == 2700.0
    fake.history_none = True
    assert bot._virtual_balance(now) == 2700.0           # the terminal gives no history: the last value read
    fresh = F.make_bot(m, fake, 'XAUUSDm', F.Run())
    assert fresh._virtual_balance(now) == 2000.0         # nothing read yet: the start balance (the smaller unit)


@pytest.mark.parametrize('extra, account, start_date, want', [
    (0.0, 50000.0, '2026-11-16', 1),          # a big demo account: still sized as a fresh $2,000 one
    (3000.0, 50000.0, '2026-11-16', 3),       # 2000 + 3000 -> floor(5000 / 2500) + 1
    (30000.0, 50000.0, '2026-11-16', 10),     # capped at unit_max_limit
    (0.0, 50000.0, None, 10),                 # None: the account balance, as live (floor(50000/2500)+1 -> 10)
    (0.0, 5000.0, None, 3),
])
def test_units_while_flat_come_from_the_virtual_balance(tmp_path, extra, account, start_date, want):
    fake, clock = market(30, balance=account)
    if extra:
        fake.add_deal(1, 1, 1, 0.01, 2000.0, extra, START - 600, magic=MAGIC)
        fake.balance -= extra                  # keep the account balance as given
    run = run_bot(fake, clock, overrides={'VIRTUAL_START_DATE': start_date}, state_dir=tmp_path)
    assert not run.errors
    flat = [p for p in run.polls if p['nb'] == 0 and p['ns'] == 0]
    assert flat and all(p['units'] == want for p in flat)
