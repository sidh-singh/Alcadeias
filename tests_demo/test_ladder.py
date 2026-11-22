"""
The ladder levers: MAX_ADDS, LADDER_TFS tiers, LADDER_TRIGGER 'macd_turn' with its arming state, the
LADDER_GAP_VOL gap and LADDER_MULTIPLIERS sizes (kernels.py L1093-1147, L1326-1351):
  * armed on any poll that reaches the ladder branch (no exit fired, an add left) with the tier's MACD
    vote not with the basket (<= 0 for a buy); armed stays armed until an add fills;
  * the add is sent on a later such poll with the vote with the basket, the OPEN score not fully against
    it (open_score > -LADDER_S for a buy) and the price at least the gap worse than the last fill.
"""
import pytest

from conftest import MAGIC, SCALED, baskets, market, run_bot

TOP1 = dict(FORCE_CLOSE_ENABLED=False, MAX_ADDS=1, LADDER_TRIGGER='macd_turn',
            LADDER_TFS=['M5', 'M15', 'H1', 'H1', 'H1'], LADDER_MULTIPLIERS=[1, 1, 1, 1],
            OPEN_SCORE_WEIGHTS={'H1': 1}, ENTRY_AGREE_S=0)


def _pos(count, profit=0.0, vol=0.01):
    return {'count': count, 'total_profit': profit, 'total_volume': round(vol * count, 2), 'first_profit': profit,
            'first_volume': vol, 'last_profit': profit, 'last_volume': vol, 'positions': []}


def _slopes(h1=(1, 1), m15=(0, 0), m5_macd=0):
    return {'H1': {'rsi': {'sign': h1[0]}, 'macd': {'sign': h1[1]}},
            'M15': {'rsi': {'sign': m15[0]}, 'macd': {'sign': m15[1]}},
            'M5': {'rsi': {'sign': 0}, 'macd': {'sign': m5_macd}}}


class _Basket:
    """Drives Strategy.calculate_signal poll by poll for one basket, carrying the arming like app.py does."""

    def __init__(self, s, side=1, gap=0.0, last_fill=2000.0, stop=None, target=None):
        self.s, self.st, self.side, self.gap, self.last_fill = s, s.Strategy(), side, gap, last_fill
        self.armed, self.count, self.stop, self.target = False, 1, stop, target

    def poll(self, vote, bid=2000.0, ask=2000.1, h1=(1, 1), profit=0.0):
        pos = _pos(self.count, profit)
        buy, sell = (pos, None) if self.side > 0 else (None, pos)
        if self.side < 0:
            h1 = (-h1[0], -h1[1])
        b, s_, an = self.st.calculate_signal(None, buy, sell, 1, close_threshold=self.target,
                                             stop_threshold=self.stop, rsi_mtf={}, slopes=_slopes(h1=h1, m5_macd=vote),
                                             ladder_armed=self.armed, ladder_gap=self.gap,
                                             last_fill_price=self.last_fill, bid=bid, ask=ask)
        self.armed = an['ladder_armed']
        sig = b if self.side > 0 else s_
        return sig.name, an


def test_macd_turn_needs_a_vote_against_the_basket_before_the_add(mods):
    s = mods(**TOP1).strategy
    k = _Basket(s)
    assert k.poll(+1)[0] == 'DO_NOTHING' and not k.armed        # with the basket from the start: not armed
    assert k.poll(+1)[0] == 'DO_NOTHING'
    assert k.poll(0)[0] == 'DO_NOTHING' and k.armed              # grey arms it
    assert k.poll(-1)[0] == 'DO_NOTHING' and k.armed
    name, an = k.poll(+1)
    assert name == 'BUY_MORE' and an['ladder_tier'] == 'M5'      # the turn back with the basket fires


def test_macd_turn_for_a_sell_mirrors(mods):
    s = mods(**TOP1).strategy
    k = _Basket(s, side=-1)
    assert k.poll(-1)[0] == 'DO_NOTHING' and not k.armed
    assert k.poll(+1)[0] == 'DO_NOTHING' and k.armed
    assert k.poll(-1)[0] == 'SELL_MORE'


def test_arming_survives_polls_the_gate_or_the_gap_refuse(mods):
    s = mods(**TOP1).strategy
    k = _Basket(s, gap=5.0, last_fill=2000.0)
    k.poll(-1)
    assert k.armed
    # H1 fully against the buy (open_score -2 <= -LADDER_S): gated, still armed
    assert k.poll(+1, h1=(-1, -1))[0] == 'DO_NOTHING' and k.armed
    # with the basket again but the ask only 4.9 below the last fill: gap refuses, still armed
    assert k.poll(+1, bid=1995.0, ask=1995.1)[0] == 'DO_NOTHING' and k.armed
    # 5.0 below (last fill - ask >= gap): the add goes
    assert k.poll(+1, bid=1994.9, ask=1995.0)[0] == 'BUY_MORE'


def test_sell_gap_is_judged_on_the_bid(mods):
    s = mods(**TOP1).strategy
    k = _Basket(s, side=-1, gap=5.0, last_fill=2000.0)
    k.poll(+1)
    assert k.poll(-1, bid=2004.99, ask=2005.1)[0] == 'DO_NOTHING'
    assert k.poll(-1, bid=2005.0, ask=2005.1)[0] == 'SELL_MORE'


def test_no_arming_on_polls_where_an_exit_fires(mods):
    s = mods(**TOP1).strategy
    k = _Basket(s, stop=10.0)
    assert k.poll(-1, profit=-10.0)[0] == 'CLOSE_BUY'            # the stop fired: the ladder branch is not reached
    assert not k.armed


def test_max_adds_limits_the_tiers(mods):
    s = mods(**TOP1).strategy
    k = _Basket(s)
    k.count = 2                                                   # the one add is taken: no tier left
    k.poll(-1)
    assert not k.armed and k.poll(+1)[0] == 'DO_NOTHING'
    assert mods(MAX_ADDS=0).strategy.Strategy.ladder_tiers() == []
    assert mods().strategy.Strategy.ladder_tiers() == ['M1', 'M5', 'M15', 'H1', 'H4']


def test_add_sizes(mods):
    st = mods(LADDER_MULTIPLIERS=[1, 1, 1, 1]).strategy.Strategy()
    assert st.next_add_volume(0.01, 1, 1, 0.01) == 0.01           # the design: one unit
    assert st.next_add_volume(0.03, 1, 3, 0.01) == 0.03
    assert st.next_add_volume(0.02, 9, 1, 0.01) == 0.01           # padded with its last element
    live = mods().strategy.Strategy()
    assert live.next_add_volume(0.01, 1, 1, 0.01) == 0.02          # live Fibonacci: 2 units first
    assert live.next_add_volume(0.03, 2, 1, 0.01) == 0.03


def test_the_macd_turn_tier_gets_its_votes_computed(mods):
    st = mods(**TOP1).strategy.Strategy
    assert st.slope_timeframes() == ['TIMEFRAME_H1', 'TIMEFRAME_M15', 'TIMEFRAME_M5']
    assert mods().strategy.Strategy.slope_timeframes() == ['TIMEFRAME_H1', 'TIMEFRAME_M15']


@pytest.mark.slow
def test_in_the_loop_each_add_is_one_unit_after_a_turn_and_one_unit_against_the_entry(tmp_path):
    """The scaled design with a 6-unit stop (room for the add): every add is 1 unit, sent on a poll whose M1
    MACD vote is with the basket after some poll since the entry where it was not, at >= 1 unit (the unit
    fixed at the open) against the entry fill; never a second add."""
    ov = dict(SCALED, STOP_VOL=6.0, TARGET_VOL=3.0)
    fake, clock = market(1800, seed=4)
    run = run_bot(fake, clock, overrides=ov, state_dir=tmp_path)
    assert not run.errors, run.errors[:3]
    bs = baskets(fake, magic=MAGIC)
    two_legs = [b for b in bs if len(b['legs']) == 2]
    assert len(two_legs) >= 2
    assert all(len(b['legs']) <= 2 for b in bs)                                  # MAX_ADDS 1
    polls = run.polls
    for b in two_legs:
        first, add = b['legs']
        side = 1 if b['side'] == 0 else -1
        assert add['vol'] == first['vol'] == 0.01                               # LADDER_MULTIPLIERS [1, ...]
        i_open = next(i for i, p in enumerate(polls) if p['t'] == round(first['t_in'] * 1000))
        i_add = next(i for i, p in enumerate(polls) if p['t'] == round(add['t_in'] * 1000))
        assert polls[i_add]['buy' if side > 0 else 'sell'] == ('BUY_MORE' if side > 0 else 'SELL_MORE')
        vote = lambda p: (p['votes'].get('M1') or (0, 0))[1]
        assert vote(polls[i_add]) * side > 0
        assert any(vote(p) * side <= 0 for p in polls[i_open + 1:i_add])        # armed in between
        gap = polls[i_open + 1]['levels']['gap_px']                             # fixed at the open
        assert gap > 0 and all(p['levels']['gap_px'] == gap for p in polls[i_open + 1:i_add + 1])
        if side > 0:
            assert first['price_in'] - add['price_in'] >= gap - 1e-9            # buy: the ask a unit lower
        else:
            assert add['price_in'] - first['price_in'] >= gap - 1e-9            # sell: the bid a unit higher
