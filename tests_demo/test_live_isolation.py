"""
Two bots share one real account (gold and BTC), and the owner may trade it by hand: every order of this bot
carries its MAGIC and its comment (the branch's label), and every position read used for a decision, and every
close, keeps only this bot's positions. (Sizing from its share of the account balance: test_live_sizing.py.)
"""
import pytest

from conftest import BRANCH, COMMENT, DEFAULTS, F, MAGIC, SCALED, START, market, run_bot


@pytest.mark.slow
def test_foreign_positions_are_invisible_and_untouched(tmp_path):
    fake, clock = market(1800, seed=21)
    foreign = [fake.add_position(0, 0.05, 1990.0, START - 7200, magic=0, comment='manual'),
               fake.add_position(1, 0.02, 2010.0, START - 3600, magic=777, comment='other bot')]
    run = run_bot(fake, clock, overrides=SCALED, state_dir=tmp_path)
    # the one warning is that they are there (6.1: once, while they stay), naming their magic numbers; neither has
    # the old ladder bot's mark (a comment, a magic), so nothing is blocked for them
    assert len(run.errors) == 1 and "Trades that are not this bot's are open on XAUUSDm" in run.errors[0], run.errors[:3]
    assert 'magic 0' in run.errors[0] and 'magic 777' in run.errors[0]
    events = [e['event'] for e in run.events]
    assert events.count('FOREIGN_POSITIONS') == 1 and 'OTHER_PROGRAM' not in events and 'SAFETY_BLOCKED' not in events
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


def test_the_order_comment_is_the_branch_label_cut_to_31_characters(mods):
    h = mods(ORDER_COMMENT='x' * 40).mt5_helper
    assert h.order_comment() == 'x' * 31
    assert mods().mt5_helper.order_comment() == COMMENT
    assert mods(ORDER_COMMENT='mine').mt5_helper.order_comment() == 'mine'
    if DEFAULTS['ORDER_COMMENT'] is None:
        assert COMMENT == BRANCH[:31] and COMMENT            # the label of the deployment block
    assert mods(ORDER_COMMENT=None, BRANCH='b' * 40).mt5_helper.order_comment() == 'b' * 31
    assert mods(ORDER_COMMENT=None, BRANCH=None).mt5_helper.order_comment() == ''       # no label: no comment


def test_dashboard_deal_history_is_this_bots(mods):
    fake, clock = market(120)
    m = mods(fake=fake, clock=clock)
    h = m.mt5_helper.MT5PositionHelper(fake)
    now = clock.time()
    fake.add_deal(1, 1, 1, 0.01, 2000.0, 5.0, now - 30, magic=MAGIC)
    fake.add_deal(2, 1, 1, 0.01, 2000.0, -9.0, now - 20, magic=0)
    fake.add_balance_operation(500.0, now - 10)             # a deposit is nobody's trade
    deals = h.get_deal_history(F.datetime.fromtimestamp(now - 100, tz=F.timezone.utc),
                               F.datetime.fromtimestamp(now + 100, tz=F.timezone.utc))
    assert [d['profit'] for d in deals] == [5.0]
    own = h.get_bot_deals(F.datetime.fromtimestamp(now - 100, tz=F.timezone.utc),
                          F.datetime.fromtimestamp(now + 100, tz=F.timezone.utc))
    assert [d.profit for d in own] == [5.0]


def test_no_guard_hangs_on_the_label(mods):
    """The label is only a label. Without one (the forward-test code switched every account check off with an empty
    DEMO_BRANCH) the bot is as strict: another mode word, missing credentials, another account, an account that is
    not real or not hedging are refused all the same."""
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock, BRANCH=None)
    assert m.app.BRANCH is None and m.mt5_helper.BRANCH is None
    wrong = m.app.MT5TradingBot(mode='demo', target_symbol='XAUUSDm')
    assert wrong.load_credentials() is False and wrong.execute_job() is False
    assert wrong.exit_code == m.app.EXIT_NEEDS_OWNER
    run = F.Run()
    bot = F.make_bot(m, fake, 'XAUUSDm', run)
    assert bot._poll_guard('XAUUSDm')
    for change in (dict(account_login=99), dict(server='Fake-Demo'), dict(trade_mode=fake.ACCOUNT_TRADE_MODE_DEMO),
                   dict(margin_mode=fake.ACCOUNT_MARGIN_MODE_RETAIL_NETTING)):
        was = {k: getattr(fake, k) for k in change}
        for k, v in change.items():
            setattr(fake, k, v)
        assert not bot._poll_guard('XAUUSDm') and bot.position_helper.buy('XAUUSDm', 0.01) is None, change
        for k, v in was.items():
            setattr(fake, k, v)
        assert bot._poll_guard('XAUUSDm')
    bot.credentials = None
    assert not bot._poll_guard('XAUUSDm') and fake.orders == []
