"""
The basket simulator behind the loss-recovery comparison (``backtesting/research/recovery.py``).

The comparison is only worth reading if the simulator does simple things exactly: a buy pays the
ask and is closed at the bid, a stop inside a bar is met before a target, a ladder holds the sizes it
says, a hedge lock freezes the result and nothing more. Every case below is small enough to check by
hand; the expected numbers in the comments are worked out from the prices, not copied from a run.

Conventions the tests rely on (see the module docstring): bars are bid bars, ``ask = bid + spread``,
an entry is made at the close of its bar, P/L = price difference x units x USD per 1.00 of price,
distances are multiples of the ATR given to the frame (1.0 unless a test says otherwise).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import recovery as R

MECH = {m.name: m for m in R.mechanisms()}
SIMULATED = [m for m in R.mechanisms() if not m.rule]
SIM_FIELDS = ["pnl", "mae", "max_units", "volume", "spread_paid"]


# ───────────────────────────── helpers ─────────────────────────────

def frame(bars, spread=0.0, atr=1.0, k=1.0, **features) -> R.Frame:
    """A frame from (open, high, low, close) rows; the entry of every test is at the close of row 0."""
    o, h, l, c = (np.array(x, float) for x in zip(*bars))
    return R.Frame.synthetic(o, h, l, c, spread=spread, atr=atr, k=k, **features)


def walk(points, step=0.25):
    """Small bars that follow a line through ``points`` without ever leaving it (no gap, no spike)."""
    bars = [(points[0],) * 4]
    for a, b in zip(points[:-1], points[1:]):
        n = max(int(round(abs(b - a) / step)), 1)
        xs = np.linspace(a, b, n + 1)
        bars += [(p, max(p, q), min(p, q), q) for p, q in zip(xs[:-1], xs[1:])]
    return bars


def one(fr, mech, side=1, entry=0, **kw):
    return R.simulate(fr, [entry], [side], mech, **kw).iloc[0]


def custom(mult=(1.0,) * 8, **params) -> R.Mechanism:
    return R.Mechanism("test", "test", "", "", {getattr(R, name): v for name, v in params.items()}, mult)


def random_frame(seed, n=600, spread=(0.01, 0.03), gaps=False) -> R.Frame:
    """A random walk with continuous bars, random indicator states and random vote signals."""
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0.0, 0.12, n))
    o = np.concatenate([[c[0]], c[:-1]])
    if gaps:
        o = o + rng.normal(0.0, 0.3, n) * (rng.random(n) < 0.03)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.06, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.06, n))
    return R.Frame.synthetic(
        o, h, l, c, spread=rng.uniform(spread[0], spread[1], n), atr=1.0,
        rsi=rng.uniform(15.0, 85.0, (len(R.LADDER_TFS), n)),
        ev=rng.choice([-1, 0, 1], (4, n), p=[0.1, 0.8, 0.1]),
        vote=rng.choice([-1, 0, 1], n, p=[0.04, 0.92, 0.04]))


def mirror(fr: R.Frame, about=200.0) -> R.Frame:
    """The same market upside down: a long there is a short here, bid and ask swap roles."""
    return R.Frame.synthetic(about - (fr.o + fr.sp), about - (fr.l + fr.sp), about - (fr.h + fr.sp), about - (fr.c + fr.sp),
                             spread=fr.sp, atr=fr.atr, k=fr.k, rsi=100.0 - fr.rsi, ev=-fr.ev, vote=-fr.vote)


FLAT = (100.0, 100.0, 100.0, 100.0)


# ───────────────────────────── P/L arithmetic ─────────────────────────────

def test_one_unit_is_one_dollar_per_dollar_of_gold_and_one_cent_per_dollar_of_btc():
    assert R.usd_per_point("XAUUSDm") == pytest.approx(1.0)       # 0.01 lot = 1 oz
    assert R.usd_per_point("BTCUSDm") == pytest.approx(0.01)      # 0.01 lot = 0.01 BTC


def test_a_long_pays_the_ask_and_is_closed_at_the_bid():
    # entry at the close 100 with spread 0.2 -> bought at 100.2; target 1 ATR above the price paid = bid 101.2
    fr = frame([FLAT, (100, 102, 100, 101.5)], spread=0.2)
    r = one(fr, MECH[R.REFERENCE], +1)
    assert r.pnl == pytest.approx(1.0) and r.reason == R.R_TARGET and r.close_idx == 1
    assert r.spread_paid == pytest.approx(0.2)                    # half a spread on the way in, half on the way out
    assert r.mae == pytest.approx(-0.2)                           # worst moment: just after the entry, one spread down


def test_a_short_is_sold_at_the_bid_and_bought_back_at_the_ask():
    # sold at 100; target when the ASK is 99, i.e. bid 98.8
    fr = frame([FLAT, (100, 100, 98.9, 98.9), (98.9, 98.9, 98.8, 98.8)], spread=0.2)
    r = one(fr, MECH[R.REFERENCE], -1)
    assert r.pnl == pytest.approx(1.0) and r.reason == R.R_TARGET and r.close_idx == 2     # bid 98.9 was not enough


def test_a_basket_still_open_at_the_end_is_closed_at_the_last_quote():
    hold = custom(P_STOP_ATR=50, P_TGT_ATR=50)
    fr = frame([FLAT, (100, 100.6, 100, 100.5)], spread=0.2)
    assert one(fr, hold, +1).pnl == pytest.approx(100.5 - 100.2)          # sold at the last bid
    assert one(fr, hold, -1).pnl == pytest.approx(100.0 - (100.5 + 0.2))  # bought back at the last ask
    assert one(fr, hold, +1).reason == R.R_END


def test_btc_amounts():
    # 0.01 lot of BTC: a 500 move is 5 USD. Bought at 60,018; stop at bid 59,518; target at bid 60,518.
    k = R.usd_per_point("BTCUSDm")
    up = frame([(60000,) * 4, (60000, 60600, 60000, 60600)], spread=18.0, atr=500.0, k=k)
    down = frame([(60000,) * 4, (60000, 60000, 59400, 59400)], spread=18.0, atr=500.0, k=k)
    assert one(up, MECH[R.REFERENCE], +1).pnl == pytest.approx(5.0)
    assert one(down, MECH[R.REFERENCE], +1).pnl == pytest.approx(-5.0)
    assert one(up, MECH[R.REFERENCE], +1).spread_paid == pytest.approx(0.18)
    assert one(up, MECH["Fixed stop $20, target $20 (the V2 exit)"], +1).reason == R.R_END    # 20 USD is a 2,000 move


def test_each_fill_uses_the_spread_of_its_own_bar():
    # short from bid 100 (spread 0.2). Later the spread is 0.6: the ask reaches 99 only when the bid is 98.4
    fr = frame([FLAT, (100, 100, 98.5, 99.9), (99.9, 99.9, 98.4, 98.4)], spread=[0.2, 0.6, 0.6])
    r = one(fr, MECH[R.REFERENCE], -1)
    assert r.close_idx == 2 and r.pnl == pytest.approx(1.0)
    assert r.spread_paid == pytest.approx(0.1 + 0.3)


# ───────────────────────────── the order inside a bar, and gaps ─────────────────────────────

@pytest.mark.parametrize("side", [+1, -1])
def test_stop_before_target_when_one_bar_holds_both(side):
    fr = frame([FLAT, (100, 101.6, 98.4, 100)], spread=0.2)
    r = one(fr, MECH[R.REFERENCE], side)
    assert r.pnl == pytest.approx(-1.0) and r.reason == R.R_STOP
    # the optimistic reading exists only as a sensitivity switch
    assert one(fr, MECH[R.REFERENCE], side, path=R.PATH_FAVOURABLE_FIRST).pnl == pytest.approx(1.0)


def test_shortest_path_reading_takes_the_far_side_of_the_close_first():
    # a bar that closes above its open is read as open -> low -> high -> close, one that closes below as open -> high -> low
    up = frame([FLAT, (100, 101.6, 98.4, 100.5)], spread=0.2)
    down = frame([FLAT, (100, 101.6, 98.4, 99.5)], spread=0.2)
    assert one(up, MECH[R.REFERENCE], +1, path=R.PATH_SHORTEST).pnl == pytest.approx(-1.0)      # low first: the long's stop
    assert one(down, MECH[R.REFERENCE], +1, path=R.PATH_SHORTEST).pnl == pytest.approx(1.0)     # high first: its target
    assert one(up, MECH[R.REFERENCE], -1, path=R.PATH_SHORTEST).pnl == pytest.approx(1.0)
    assert one(down, MECH[R.REFERENCE], -1, path=R.PATH_SHORTEST).pnl == pytest.approx(-1.0)
    for fr in (up, down):                                         # the result itself never depends on the close
        assert one(fr, MECH[R.REFERENCE], +1).pnl == one(fr, MECH[R.REFERENCE], -1).pnl == pytest.approx(-1.0)


def test_a_level_counts_when_it_is_exactly_touched():
    assert one(frame([FLAT, (100, 101.2, 100, 100)], spread=0.2), MECH[R.REFERENCE], +1).pnl == pytest.approx(1.0)
    assert one(frame([FLAT, (100, 100, 99.2, 100)], spread=0.2), MECH[R.REFERENCE], +1).pnl == pytest.approx(-1.0)
    assert one(frame([FLAT, (100, 101.19, 99.21, 100)], spread=0.2), MECH[R.REFERENCE], +1).reason == R.R_END


def test_a_gap_through_the_stop_is_filled_at_the_open():
    # long: stop at bid 99.2, the next bar opens at 98.0 -> sold at 98.0, not at 99.2
    assert one(frame([FLAT, (98.0, 98.5, 97.5, 98.2)], spread=0.2), MECH[R.REFERENCE], +1).pnl == pytest.approx(98.0 - 100.2)
    # short: stop when the ask is 101, the next bar opens at bid 102.0 -> bought back at 102.2
    assert one(frame([FLAT, (102.0, 102.5, 101.5, 102.0)], spread=0.2), MECH[R.REFERENCE], -1).pnl == pytest.approx(100.0 - 102.2)


def test_a_gap_through_the_target_is_filled_at_the_open_too():
    assert one(frame([FLAT, (103.0, 103.5, 102.5, 103.0)], spread=0.2), MECH[R.REFERENCE], +1).pnl == pytest.approx(103.0 - 100.2)


# ───────────────────────────── the live ladder ─────────────────────────────

def ladder_rsi(n, **bars):
    """RSI 50 everywhere except the bars named ``b<index>=(M1, M5, M15, H1, H4)``."""
    rsi = np.full((len(R.LADDER_TFS), n), 50.0)
    for name, values in bars.items():
        rsi[:, int(name[1:])] = values
    return rsi


def test_live_ladder_sizes_are_1_2_3_5_8_13():
    # every tier oversold at the entry: the whole ladder goes in at one price, 32 units
    fr = frame([FLAT, (100, 100.3, 100, 100.3)], spread=0.2, rsi=ladder_rsi(2, b0=(30, 30, 30, 30, 30)))
    r = one(fr, MECH["Live ladder, no stop"], +1)
    assert r.max_units == 32 and r.volume == 32 and r.adds == 5
    assert r.mae == pytest.approx(-32 * 0.2)                      # 32 units, one spread down at once
    # the target is 1 USD for the whole basket: 32 units need only 1/32 above the price paid
    assert r.pnl == pytest.approx(1.0) and r.reason == R.R_TARGET
    assert r.spread_paid == pytest.approx(32 * 0.2)


def test_live_ladder_tiers_are_taken_in_order_each_on_its_own_timeframe():
    lad = MECH["Live ladder, no stop"]
    # M1 oversold, M5 not: only the x2 add, although M15 is oversold as well
    assert one(frame([FLAT, FLAT], rsi=ladder_rsi(2, b0=(30, 50, 30, 30, 30))), lad, +1).max_units == 3
    # M1 not oversold: nothing, whatever the slower timeframes say
    assert one(frame([FLAT, FLAT], rsi=ladder_rsi(2, b0=(50, 30, 30, 30, 30))), lad, +1).max_units == 1
    # a short basket adds on overbought readings, not on oversold ones
    assert one(frame([FLAT, FLAT], rsi=ladder_rsi(2, b0=(70, 70, 50, 50, 50))), lad, -1).max_units == 1 + 2 + 3
    assert one(frame([FLAT, FLAT], rsi=ladder_rsi(2, b0=(30, 30, 30, 30, 30))), lad, -1).max_units == 1
    # exactly on the threshold counts (35 / 65)
    assert one(frame([FLAT, FLAT], rsi=ladder_rsi(2, b0=(35, 50, 50, 50, 50))), lad, +1).max_units == 3
    assert one(frame([FLAT, FLAT], rsi=ladder_rsi(2, b0=(65, 50, 50, 50, 50))), lad, -1).max_units == 3


def test_live_ladder_adds_at_the_close_at_which_its_rsi_gets_there():
    # x2 at the close of bar 1 (bid 99, ask 99.2), x3 at the close of bar 2 (ask 98.2); spread 0.2
    fr = frame([FLAT, (100, 100, 99, 99), (99, 99, 98, 98), (98, 98.5, 98, 98.5)], spread=0.2,
               rsi=ladder_rsi(4, b1=(30, 50, 50, 50, 50), b2=(50, 30, 50, 50, 50)))
    r = one(fr, MECH["Live ladder, no stop"], +1)
    # average price paid = (100.2 + 2 x 99.2 + 3 x 98.2) / 6 = 98.8667; sold at the last bid 98.5
    assert r.max_units == 6 and r.adds == 2
    assert r.pnl == pytest.approx(6 * 98.5 - (100.2 + 2 * 99.2 + 3 * 98.2))
    assert r.mae == pytest.approx(6 * 98.0 - (100.2 + 2 * 99.2 + 3 * 98.2))     # worst at bid 98, all six units in


def test_live_ladder_without_a_stop_has_no_floor_and_with_one_stops_at_it():
    bars = walk([100.0, 60.0])
    rsi = np.full((len(R.LADDER_TFS), len(bars)), 30.0)
    fr = frame(bars, spread=0.2, rsi=rsi)
    free = one(fr, MECH["Live ladder, no stop"], +1)
    assert free.pnl == pytest.approx(32 * (60.0 - 100.2)) and free.reason == R.R_END
    capped = one(fr, MECH["Live ladder, basket stop $60"], +1)
    assert capped.pnl == pytest.approx(-60.0) and capped.reason == R.R_BUDGET
    assert capped.max_units == 32


# ───────────────────────────── averaging down inside a budget ─────────────────────────────

def test_spacing_puts_the_stop_one_step_beyond_the_last_add():
    # 2 adds, budget 3: adds 0.5 and 1.0 below, stop 1.5 below; the three units then lose 1.5 + 1.0 + 0.5 = 3
    assert R.level_spacing(3, 2) == pytest.approx(0.5)
    assert R.level_spacing(3, 1) == pytest.approx(1.0)
    assert R.level_spacing(3, 4) == pytest.approx(0.2)
    for budget in (1, 2, 3):
        for adds in (1, 2, 3, 4):
            d = R.level_spacing(budget, adds)
            assert sum((adds + 1) * d - i * d for i in range(adds + 1)) == pytest.approx(budget)


def test_equal_ladder_fills_at_its_levels_and_exits_over_the_average():
    # bought at 100, 99.5 and 99.0 (no spread): average 99.5, target 0.5 above it = 100.0
    fr = frame([FLAT, (100, 100, 98.9, 99.0), (99.0, 100.1, 99.0, 100.1)])
    r = one(fr, MECH["Budget 3 R, 2 adds 0.5 ATR apart"], +1)
    assert r.adds == 2 and r.max_units == 3 and r.reason == R.R_TARGET
    assert r.pnl == pytest.approx(3 * 0.5)
    assert r.mae == pytest.approx((98.9 - 100) + (98.9 - 99.5) + (98.9 - 99.0))
    # the same path without adds is still waiting for 100.5
    assert one(fr, MECH["Budget 3 R, no add"], +1).reason == R.R_END


@pytest.mark.parametrize("mech", [m for m in SIMULATED if m.name.startswith("Budget") or m.name.startswith("Add when")],
                         ids=lambda m: m.name)
@pytest.mark.parametrize("side", [+1, -1])
def test_the_worst_case_of_a_budget_ladder_is_its_budget(mech, side):
    # a market that only goes against the basket, without gaps: the loss is the budget, whatever was added on the way
    fr = frame(walk([100.0, 100.0 - 12.0 * side], step=0.05), spread=0.01, ev=1 * side)
    r = one(fr, mech, side)
    assert r.pnl == pytest.approx(-mech.params[R.P_STOP_BUDGET_ATR])
    assert r.mae == pytest.approx(r.pnl) and r.reason == R.R_BUDGET
    assert r.max_units <= int(mech.position)


def test_usd_cap_applies_when_it_is_the_smaller_budget():
    # ATR 30: three ATR would be 90 USD on one unit, the cap of 60 comes first
    fr = frame(walk([4000.0, 3800.0], step=1.0), spread=0.2, atr=30.0)
    assert one(fr, MECH[R.CAPPED_LADDER], +1).pnl == pytest.approx(-60.0)
    assert one(fr, MECH["Budget 3 R, 2 adds 0.5 ATR apart"], +1).pnl == pytest.approx(-90.0)


def test_session_calendar_follows_the_clock():
    def at(text):
        return int(R.session_calendar(np.array([pd.Timestamp(text).value // 10**9]))[0])

    assert at("2026-11-12 20:29") == 0 and at("2026-11-12 20:30") == 1      # a Thursday: the daily break
    assert at("2026-11-12 23:04") == 1 and at("2026-11-12 23:05") == 0
    assert at("2026-11-13 20:29") == 0 and at("2026-11-13 20:30") == 2      # a Friday: the weekend starts
    assert at("2026-11-14 12:00") == 2 and at("2026-11-15 23:59") == 2 and at("2026-11-16 00:00") == 0


def test_flat_over_closures_closes_the_basket_and_opens_none():
    weekend, every = MECH[R.CAPPED_LADDER + ", flat over the weekend"], MECH[R.CAPPED_LADDER + ", flat over every market closure"]
    bars = [FLAT, (100, 100, 99.6, 99.7), (99.7, 99.7, 99.7, 99.7), (99.7, 101, 99.7, 101)]
    # the daily break begins at the close of bar 2: only the stricter rule sells there (bought at 100, sold at 99.7)
    daily = frame(bars, session=[0, 0, 1, 1])
    r = one(daily, every, +1)
    assert r.reason == R.R_CLOSURE and r.close_idx == 2 and r.pnl == pytest.approx(-0.3)
    assert one(daily, weekend, +1).reason == R.R_TARGET
    # the weekend begins there: both sell
    assert one(frame(bars, session=[0, 0, 2, 2]), weekend, +1).close_idx == 2
    assert one(frame(bars, session=[0, 0, 2, 2]), every, +1).close_idx == 2
    # an entry inside the window is not taken at all
    r = R.simulate(frame(bars, session=[2, 2, 2, 2]), [0], [1], weekend).iloc[0]
    assert not r.taken and r.pnl == 0 and r.volume == 0 and r.reason == R.R_NOT_TAKEN
    assert R.simulate(frame(bars, session=[1, 1, 1, 1]), [0], [1], weekend).iloc[0].taken
    assert not R.simulate(frame(bars, session=[1, 1, 1, 1]), [0], [1], every).iloc[0].taken
    # the plain ladder knows no calendar
    assert one(frame(bars, session=[2, 2, 2, 2]), MECH[R.CAPPED_LADDER], +1).reason == R.R_TARGET


def test_every_basket_carries_the_loss_it_was_built_not_to_exceed():
    risk = np.array([10.0, 30.0])                                 # the value of one ATR on one unit at two entries
    assert MECH[R.REFERENCE].budget(risk).tolist() == [10.0, 30.0]
    assert MECH["Fixed stop 2 ATR, target 1 ATR"].budget(risk).tolist() == [20.0, 60.0]
    assert MECH["Fixed stop $20, target $20 (the V2 exit)"].budget(risk).tolist() == [20.0, 20.0]
    assert MECH["Budget 3 R, 2 adds 0.5 ATR apart"].budget(risk).tolist() == [30.0, 90.0]
    assert MECH[R.CAPPED_LADDER].budget(risk).tolist() == [30.0, 60.0]              # the smaller of 3 R and 60 USD
    assert MECH["Live ladder, basket stop $60"].budget(risk).tolist() == [60.0, 60.0]
    assert MECH["Stop and reverse, double size"].budget(risk).tolist() == [30.0, 90.0]   # 1 R, then 2 units x 1 R
    assert MECH["Trailing stop 1 ATR, no target"].budget(risk).tolist() == [10.0, 30.0]
    for name in ("Live ladder, no stop", "Pyramid, 2 adds", "Hedge lock, unlocked by the next vote signal",
                 "Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12", "Martingale: double after a loss, up to x8"):
        assert np.isnan(MECH[name].budget(risk)).all(), name


def test_a_gap_is_what_takes_a_basket_beyond_its_budget():
    lad = MECH["Budget 3 R, 2 adds 0.5 ATR apart"]
    # a slide without gaps ends exactly on the budget; a gap of 5 through the stop costs 5 more on the single unit held
    smooth = R.simulate(frame(walk([100.0, 90.0], step=0.05)), [0], [1], lad)
    gapped = R.simulate(frame([FLAT, (92.0, 92.0, 91.0, 91.0)]), [0], [1], lad)
    both = pd.concat([smooth, gapped], ignore_index=True)
    assert both["budget"].tolist() == [3.0, 3.0]
    assert both["pnl"].tolist() == pytest.approx([-3.0, -8.0])
    s = R._summary(both, None)
    assert s["over_budget_n"] == 1 and s["over_budget_max"] == pytest.approx(5.0) and s["budget_max"] == 3.0
    assert "over_budget_n" not in R._summary(R.simulate(frame(walk([100.0, 90.0])), [0], [1], MECH["Live ladder, no stop"]), None)


def test_an_add_the_budget_cannot_carry_is_not_made():
    # budget 1, adds 0.167 apart, but a spread of 0.2: the second add would cost more than what is left
    fr = frame(walk([100.0, 98.0], step=0.05), spread=0.2)
    r = one(fr, MECH["Budget 1 R, 2 adds 0.17 ATR apart"], +1)
    assert r.adds == 1 and r.pnl == pytest.approx(-1.0)


def test_levels_passed_by_a_gap_are_filled_at_the_open_and_the_stop_comes_first():
    lad = MECH["Budget 3 R, 2 adds 0.5 ATR apart"]
    # opens at 98.8, below both levels: both adds at 98.8; average (100 + 2 x 98.8) / 3 = 99.2, target 99.7
    r = one(frame([FLAT, (98.8, 99.8, 98.5, 99.7)]), lad, +1)
    assert r.adds == 2 and r.pnl == pytest.approx((99.7 - 100) + 2 * (99.7 - 98.8))
    # opens at 96, beyond the budget of the single unit: closed there, nothing is added on the way out
    r = one(frame([FLAT, (96.0, 96.5, 95.5, 96.0)]), lad, +1)
    assert r.adds == 0 and r.pnl == pytest.approx(-4.0) and r.reason == R.R_BUDGET


def test_a_signal_add_needs_its_event_its_direction_and_its_distance():
    sig = MECH["Add when the M5 MACD histogram turns"]           # event row 0, at least 0.5 ATR beyond the last fill

    def run(close1, event, side=+1, row=0):
        ev = np.zeros((4, 3), np.int8)
        ev[row, 1] = event
        up = 100 + (close1 - 100)
        bars = [FLAT, (100, max(100, up), min(100, up), close1), (close1, close1, close1, close1)]
        return one(frame(bars, ev=ev), sig, side)

    assert run(99.4, +1).adds == 1                               # 0.6 below, the histogram turns up: add
    assert run(99.7, +1).adds == 0                               # only 0.3 below
    assert run(99.4, -1).adds == 0                               # the event favours shorts
    assert run(99.4, +1, row=1).adds == 0                        # another signal's event
    assert run(100.6, -1, side=-1).adds == 1                     # the short mirror
    assert run(100.6, +1, side=-1).adds == 0
    # the add is made at that close: bought at 100 and 99.4, average 99.7, sold at the last bid 99.4
    assert run(99.4, +1).pnl == pytest.approx(2 * 99.4 - (100 + 99.4))


# ───────────────────────────── stops that follow the price, scale-out, pyramid ─────────────────────────────

def test_break_even_moves_the_stop_to_the_price_paid():
    be = MECH["Break-even at +0.5 ATR (stop 1, target 1)"]
    # bought at 100.2; at bid 100.7 the stop moves to 100.2; the fall then costs nothing instead of 1.0
    fr = frame([FLAT, (100, 100.8, 100, 100.8), (100.8, 100.8, 99.0, 99.5)], spread=0.2)
    assert one(fr, be, +1).pnl == pytest.approx(0.0) and one(fr, be, +1).reason == R.R_STOP
    assert one(fr, MECH[R.REFERENCE], +1).pnl == pytest.approx(-1.0)
    # armed at the high and met again on the way to the close of the same bar
    assert one(frame([FLAT, (100, 100.8, 100, 100.1), FLAT], spread=0.2), be, +1).close_idx == 1
    # not armed below the trigger
    assert one(frame([FLAT, (100, 100.6, 100, 100.6), (100.6, 100.6, 99.0, 99.0)], spread=0.2), be, +1).pnl == pytest.approx(-1.0)


def test_trailing_stop_follows_the_best_price():
    tr = MECH["Trailing stop 1 ATR, no target"]
    fr = frame([FLAT, (100, 102.4, 100, 102.4), (102.4, 102.4, 101.0, 101.0)])
    assert one(fr, tr, +1).pnl == pytest.approx(1.4)              # best 102.4, stop 101.4
    assert one(frame([FLAT, (100, 102.4, 100, 101.2), FLAT]), tr, +1).pnl == pytest.approx(1.4)   # inside one bar
    assert one(frame([FLAT, (100, 100.5, 99.0, 99.0)]), tr, +1).pnl == pytest.approx(-1.0)        # never above the first stop
    short = frame([FLAT, (100, 100, 97.6, 97.6), (97.6, 99.0, 97.6, 99.0)])
    assert one(short, tr, -1).pnl == pytest.approx(1.4)


def test_scale_out_closes_half_and_protects_the_rest():
    so = MECH["Scale-out: half at +1 ATR, rest trailed by 1 ATR"]
    # half sold at 101 (+0.5); the rest trails 1 behind the best price 103 and is sold at 102 (+1.0)
    assert one(frame([FLAT, (100, 103, 100, 103), (103, 103, 101.5, 101.5)]), so, +1).pnl == pytest.approx(0.5 + 1.0)
    # half at 101, best 101.2: the stop is 100.2 (above the price paid); the rest makes 0.5 x 0.2
    r = one(frame([FLAT, (100, 101.2, 100, 101.2), (101.2, 101.2, 99.5, 99.5)]), so, +1)
    assert r.pnl == pytest.approx(0.5 + 0.1) and r.max_units == 1
    # before the scale-out there is no trailing: best 100.9, stop still 99
    assert one(frame([FLAT, (100, 100.9, 100, 100.9), (100.9, 100.9, 99.0, 99.0)]), so, +1).pnl == pytest.approx(-1.0)


def test_pyramid_adds_in_profit_and_trails_the_whole_basket():
    py = MECH["Pyramid, 2 adds"]
    # bought at 100, 101 and 102; best 103.5; all three sold at 102.5
    fr = frame([FLAT, (100, 101.5, 100, 101.5), (101.5, 103.5, 101.5, 103.5), (103.5, 103.5, 102.0, 102.0)])
    r = one(fr, py, +1)
    assert r.adds == 2 and r.max_units == 3
    assert r.pnl == pytest.approx(2.5 + 1.5 + 0.5)


@pytest.mark.parametrize("seed", range(20))
def test_pyramid_and_trailing_stop_never_lose_more_than_the_first_stop(seed):
    # without gaps and without spread, adding every 1 ATR behind a 1 ATR trailing stop cannot cost more than 1 R
    fr = random_frame(seed, spread=(0.0, 0.0))
    idx, dirs = np.arange(0, 500, 25), np.where(np.arange(20) % 2, 1, -1)
    for name in ("Trailing stop 1 ATR, no target", "Pyramid, 2 adds", "Pyramid, 4 adds",
                 "Break-even at +0.5 ATR (stop 1, target 1)", "Scale-out: half at +1 ATR, rest trailed by 1 ATR"):
        r = R.simulate(fr, idx, dirs, MECH[name])
        assert r["pnl"].min() >= -1.0 - 1e-9, name


# ───────────────────────────── hedge lock ─────────────────────────────

def test_a_lock_freezes_the_result_whatever_the_market_does_next():
    lock = MECH["Hedge lock, both legs closed 4 h later"]
    for dest in (60.0, 140.0):
        # bought at 100.2, locked by a sale at 99.2: -1.0 is fixed; closing both legs costs one more spread
        fr = frame([FLAT, (100, 100, 99.0, 99.0)] + walk([99.0, dest])[1:], spread=0.2)
        r = one(fr, lock, +1)
        assert r.pnl == pytest.approx(-1.0 - 0.2) and r.max_units == 2
        assert r.mae == pytest.approx(-1.2)


def test_timed_lock_is_closed_when_its_time_is_up():
    n = R.LOCK_HOLD_BARS + 40
    bars = [FLAT, (100, 100, 99.0, 99.0)] + [(99.0,) * 4] * n
    spread = np.full(len(bars), 0.2)
    spread[1 + R.LOCK_HOLD_BARS] = 0.5                           # the spread at the moment of the unlock is the one paid
    r = one(frame(bars, spread=spread), MECH["Hedge lock, both legs closed 4 h later"], +1)
    assert r.close_idx == 1 + R.LOCK_HOLD_BARS and r.reason == R.R_UNLOCK
    assert r.pnl == pytest.approx(-1.0 - 0.5)


def test_lock_then_unlock_is_close_then_reenter_worked_example():
    lock, twin = MECH["Hedge lock, unlocked by the next vote signal"], MECH["Close at -1 ATR, re-enter on the next vote signal"]
    # long from 100.2, locked at 99.2. At the close of bar 1 (bid 98.0, ask 98.2) the votes say BUY:
    #   lock: the short leg is bought back at 98.2 (+1.0); the long is kept, stop 97.2, target 99.2; sold at 99.2 (-1.0)
    #   twin: the long is sold at 99.2 (-1.0); a new long at 98.2 is sold at 99.2 (+1.0)
    up = frame([FLAT, (100, 100, 98.0, 98.0), (98.0, 99.5, 98.0, 99.5)], spread=0.2, vote=[0, 1, 0])
    a, b = one(up, lock, +1), one(up, twin, +1)
    assert a.pnl == pytest.approx(0.0) and b.pnl == pytest.approx(0.0)
    assert a.volume == b.volume == 2 and a.spread_paid == pytest.approx(b.spread_paid) == pytest.approx(0.4)
    assert a.max_units == 2 and b.max_units == 1
    # the votes say SELL instead: the long leg is sold at 98.0 (-2.2), the short from 99.2 is kept,
    # target when the ask is 97.0 (+2.2).  twin: -1.0, then a new short from 98.0 to ask 97.0 (+1.0)
    down = frame([FLAT, (100, 100, 98.0, 98.0), (98.0, 98.0, 96.5, 96.5)], spread=0.2, vote=[0, -1, 0])
    a, b = one(down, lock, +1), one(down, twin, +1)
    assert a.pnl == pytest.approx(0.0) and b.pnl == pytest.approx(0.0)
    assert a.reason == b.reason == R.R_TARGET


@pytest.mark.parametrize("seed", range(12))
def test_lock_then_unlock_equals_close_then_reenter_on_random_markets(seed):
    fr = random_frame(100 + seed, gaps=bool(seed % 2))
    idx = np.arange(0, 560, 7)
    dirs = np.where(np.arange(len(idx)) % 3 == 0, -1, 1)
    a = R.simulate(fr, idx, dirs, MECH["Hedge lock, unlocked by the next vote signal"])
    b = R.simulate(fr, idx, dirs, MECH["Close at -1 ATR, re-enter on the next vote signal"])
    assert (a["close_idx"] == b["close_idx"]).all() and (a["reason"] == b["reason"]).all()
    assert a["max_units"].max() == 2 and b["max_units"].max() == 1  # the visible difference: two positions held, not one
    # a lock still on when the history ends has both legs open; the twin is flat by then
    still_locked = ((a["reason"] == R.R_END) & (a["volume"] != b["volume"])).to_numpy()
    done = ~still_locked
    assert done.sum() > 40
    assert np.abs(a["pnl"] - b["pnl"])[done].max() < 1e-9          # the same money, fill by fill
    assert (a["volume"] == b["volume"])[done].all()
    assert np.abs(a["spread_paid"] - b["spread_paid"])[done].max() < 1e-12
    # getting out of a lock that was never unlocked costs one spread more than having closed
    assert np.allclose((a["pnl"] - b["pnl"])[still_locked], -fr.sp[-1], atol=1e-9)


@pytest.mark.parametrize("seed", range(6))
def test_timed_lock_is_the_plain_stop_minus_one_more_spread(seed):
    fr = random_frame(200 + seed)
    idx = np.arange(0, 300, 5)
    dirs = np.where(np.arange(len(idx)) % 2, 1, -1)
    ref = R.simulate(fr, idx, dirs, MECH[R.REFERENCE])
    lock = R.simulate(fr, idx, dirs, MECH["Hedge lock, both legs closed 4 h later"])
    stopped = (ref["reason"] == R.R_STOP).to_numpy()
    assert stopped.any() and (~stopped).any()
    extra = fr.sp[lock["close_idx"].to_numpy()]                   # the spread at which the two legs are closed
    assert np.allclose(lock["pnl"][stopped], ref["pnl"][stopped] - extra[stopped], atol=1e-9)
    assert np.allclose(lock["pnl"][~stopped], ref["pnl"][~stopped], atol=1e-12)


# ───────────────────────────── zone recovery, stop and reverse ─────────────────────────────

def test_zone_leg_sizes():
    assert R.zone_sizes(1.0, 1.0, 4) == pytest.approx([1, 3, 6, 12])
    assert R.zone_sizes(0.5, 1.0, 4) == pytest.approx([1, 2.5, 3.75, 5.625])
    assert R.zone_worst(1.0, 1.0, 4) == pytest.approx(15.0)       # 15 units sold one zone below where they are bought back
    assert R.zone_worst(0.5, 1.0, 4) == pytest.approx(8.125 * 0.5)


@pytest.mark.parametrize("points, legs, pnl", [
    ([100, 101], 1, 1.0),                                         # straight to the target
    ([100, 99, 98], 2, -2.0 + 3 * 1.0),                           # 1 long loses 2, 3 shorts make 1 each
    ([100, 99, 100, 101], 3, 7 * 1.0 - 3 * 2.0),                  # 7 longs make 1 each, 3 shorts lose 2 each
    ([100, 99, 100, 99, 98], 4, -7 * 2.0 + 15 * 1.0),
    ([100, 99, 100, 99, 100], 4, -15.0),                          # no leg left at the edge: 15 shorts lose 1 each
])
def test_zone_recovery_pays_the_first_target_from_any_leg_until_the_legs_run_out(points, legs, pnl):
    r = one(frame(walk([float(p) for p in points])), MECH["Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12"], +1)
    assert r.pnl == pytest.approx(pnl) and r.adds == legs - 1
    assert r.max_units == pytest.approx(sum([1, 3, 6, 12][:legs]))
    assert r.reason == (R.R_MAX_LEGS if pnl < 0 else R.R_TARGET)
    short = one(frame(walk([200.0 - p for p in points])), MECH["Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12"], -1)
    assert short.pnl == pytest.approx(pnl)


def test_zone_recovery_pays_the_spread_on_every_leg():
    # one zig-zag with a spread of 0.02: long 1 at 100.02, short 3 at 99.02, closed when the ask is 98.02
    r = one(frame(walk([100.0, 99.0, 97.5]), spread=0.02), MECH["Zone 1 ATR, target 1 ATR, legs 1 / 3 / 6 / 12"], +1)
    assert r.pnl == pytest.approx((98.0 - 100.02) + 3 * (99.02 - 98.02))
    assert r.spread_paid == pytest.approx(4 * 0.02)


def test_stop_and_reverse():
    same, double = MECH["Stop and reverse, same size"], MECH["Stop and reverse, double size"]
    # long from 100 stopped at 99 (-1); short from 99, target 98 (+1 per unit)
    wins = frame(walk([100.0, 97.5]))
    assert one(wins, same, +1).pnl == pytest.approx(0.0) and one(wins, double, +1).pnl == pytest.approx(1.0)
    assert one(wins, double, +1).max_units == 2 and one(wins, double, +1).volume == 3
    # stopped twice: -1 and -1 per unit of the reversed position; there is no second reversal
    loses = frame(walk([100.0, 99.0, 100.5, 97.0]))
    assert one(loses, same, +1).pnl == pytest.approx(-2.0) and one(loses, double, +1).pnl == pytest.approx(-3.0)
    assert one(loses, same, +1).reason == R.R_STOP


# ───────────────────────────── the same rules written out plainly ─────────────────────────────

def plain_stop_target(fr, e, side, stop_atr=1.0, tgt_atr=1.0):
    """The reference trade bar by bar in raw prices, long and short spelt out separately."""
    a, k, last = fr.atr[e], fr.k, len(fr) - 1
    if side == 1:
        paid = fr.c[e] + fr.sp[e]
        stop, tgt = paid - stop_atr * a, paid + tgt_atr * a           # both are bid levels
        for j in range(e + 1, len(fr)):
            if fr.o[j] <= stop or fr.o[j] >= tgt:                     # the open is already beyond a level
                return (fr.o[j] - paid) * k, j
            if fr.l[j] <= stop:                                       # the stop is met first
                return (stop - paid) * k, j
            if fr.h[j] >= tgt:
                return (tgt - paid) * k, j
        return (fr.c[last] - paid) * k, last
    got = fr.c[e]
    stop, tgt = got + stop_atr * a, got - tgt_atr * a                 # both are ask levels
    for j in range(e + 1, len(fr)):
        s = fr.sp[j]
        if fr.o[j] + s >= stop or fr.o[j] + s <= tgt:
            return (got - fr.o[j] - s) * k, j
        if fr.h[j] + s >= stop:
            return (got - stop) * k, j
        if fr.l[j] + s <= tgt:
            return (got - tgt) * k, j
    return (got - fr.c[last] - fr.sp[last]) * k, last


def plain_budget_ladder_long(fr, e, budget_atr, adds, target_over_average=R.SMALL_TARGET_ATR):
    """A long equal-lot ladder inside a budget, bar by bar: a list of prices paid and nothing else."""
    a, k, last = fr.atr[e], fr.k, len(fr) - 1
    step, budget = R.level_spacing(budget_atr, adds) * a if adds else 0.0, budget_atr * a * k
    paid = [fr.c[e] + fr.sp[e]]
    may_add = adds > 0

    def result(bid):
        return k * (len(paid) * bid - sum(paid))

    for j in range(e + 1, len(fr)):
        s = fr.sp[j]
        for start, end in ((fr.o[j], fr.l[j]), (fr.l[j], fr.h[j]), (fr.h[j], fr.c[j])):
            x = start
            while True:
                n = len(paid)
                stop = sum(paid) / n - budget / (k * n)               # bid at which the budget is gone
                target = sum(paid) / n + target_over_average * a
                level = paid[0] - n * step - s if may_add and n <= adds else None      # bid at which the next unit is bought
                if x <= stop or x >= target:
                    return result(x), j
                if end < x:
                    if level is not None and level >= max(end, stop) and level > stop:
                        fill = min(level, x)
                        if result(fill) - k * s <= -budget:           # the add itself would break the budget
                            may_add = False
                            continue
                        paid.append(fill + s)
                        x = fill
                        continue
                    if stop >= end:
                        return result(stop), j
                    break
                if level is not None and level >= x:                  # passed by a gap or by the last move
                    if result(x) - k * s <= -budget:
                        may_add = False
                        continue
                    paid.append(x + s)
                    continue
                if end > x and target <= end:
                    return result(target), j
                break
    return result(fr.c[last]), last


def test_reference_trade_against_its_plain_restatement(real):
    symbol, m1, fr = real
    assert not fr.hole.any()
    for kind in ("votes", "random"):
        idx, dirs = R.entry_list(fr, kind)
        got = R.simulate(fr, idx, dirs, MECH[R.REFERENCE])
        want = [plain_stop_target(fr, int(e), int(d)) for e, d in zip(idx, dirs)]
        assert len(idx) > 30 and set(dirs) == {-1, 1}
        assert np.allclose(got["pnl"], [w[0] for w in want], atol=1e-9)
        assert (got["close_idx"] == [w[1] for w in want]).all()
    wide = R.simulate(fr, idx, dirs, MECH["Fixed stop 1 ATR, target 2 ATR"])
    want = [plain_stop_target(fr, int(e), int(d), 1.0, 2.0) for e, d in zip(idx, dirs)]
    assert np.allclose(wide["pnl"], [w[0] for w in want], atol=1e-9)


@pytest.mark.parametrize("name, budget, adds", [("Budget 3 R, no add", 3, 0), ("Budget 3 R, 1 add 1 ATR apart", 3, 1),
                                                ("Budget 3 R, 2 adds 0.5 ATR apart", 3, 2), ("Budget 3 R, 4 adds 0.2 ATR apart", 3, 4),
                                                ("Budget 1 R, 2 adds 0.17 ATR apart", 1, 2), ("Budget 2 R, 2 adds 0.33 ATR apart", 2, 2)])
def test_budget_ladder_against_its_plain_restatement(real, name, budget, adds):
    symbol, m1, fr = real
    idx, _ = R.entry_list(fr, "random")
    got = R.simulate(fr, idx, np.ones(len(idx), np.int8), MECH[name])
    want = [plain_budget_ladder_long(fr, int(e), budget, adds) for e in idx]
    assert np.allclose(got["pnl"], [w[0] for w in want], atol=1e-7)
    assert (got["close_idx"] == [w[1] for w in want]).all()
    if adds:
        assert got["adds"].max() == adds                          # the comparison includes full ladders


# ───────────────────────────── mirror symmetry ─────────────────────────────

@pytest.mark.parametrize("mech", SIMULATED, ids=lambda m: m.name)
def test_a_short_is_the_mirror_image_of_a_long(mech):
    fr = random_frame(7, gaps=True)
    mi = mirror(fr)
    idx = np.arange(0, 560, 9)
    a = R.simulate(fr, idx, np.ones(len(idx), np.int8), mech)
    b = R.simulate(mi, idx, -np.ones(len(idx), np.int8), mech)
    assert (a["close_idx"] == b["close_idx"]).all() and (a["reason"] == b["reason"]).all()
    for col in SIM_FIELDS:
        assert np.allclose(a[col], b[col], atol=1e-8), col


# ───────────────────────────── rules on the sequence of baskets ─────────────────────────────

def baskets(pnl, entry_idx=None, close_idx=None, mae=None, day=None, risk=1.0) -> pd.DataFrame:
    n = len(pnl)
    entry_idx = np.arange(n) * 10 if entry_idx is None else np.asarray(entry_idx)
    return pd.DataFrame({
        "entry_idx": entry_idx, "close_idx": entry_idx + 5 if close_idx is None else close_idx,
        "pnl": np.asarray(pnl, float), "mae": np.minimum(np.asarray(pnl, float), 0.0) if mae is None else np.asarray(mae, float),
        "max_units": 1.0, "volume": 1.0, "spread_paid": 0.1, "risk": risk, "budget": risk, "size": 1.0, "taken": True,
        "reason": R.R_STOP,
        "entry_time": (np.zeros(n, int) if day is None else np.asarray(day)) * 86400 + entry_idx * 60,
        "close_time": 0})


def test_martingale_and_anti_martingale_sizes():
    b = baskets([-1, -1, -1, -1, +1, -1, +1, +1])
    mart = R.resize_by_outcome(b, "martingale", 8)
    assert mart["size"].tolist() == [1, 2, 4, 8, 8, 1, 2, 1]      # doubles after each loss, capped at 8, back to 1 after a win
    assert mart["pnl"].tolist() == [-1, -2, -4, -8, 8, -1, 2, 1]
    anti = R.resize_by_outcome(b, "anti-martingale", 8)
    assert anti["size"].tolist() == [1, 1, 1, 1, 1, 2, 1, 2]
    assert mart["spread_paid"].tolist() == pytest.approx((0.1 * mart["size"]).tolist())
    assert mart["budget"].tolist() == mart["size"].tolist()       # eight units behind one stop can lose eight times as much


def test_daily_loss_limit_skips_the_rest_of_the_day_only():
    b = baskets([-1, -1, +1, -1, -1, +1], day=[0, 0, 0, 0, 1, 1])
    lim = R.daily_loss_limit(b, 2.0)
    assert lim["taken"].tolist() == [True, True, False, False, True, True]
    assert lim["pnl"].tolist() == [-1, -1, 0, 0, -1, 1]
    assert R.daily_loss_limit(b, 1.0)["taken"].tolist() == [True, False, False, False, True, False]
    # R is each basket's own risk: a loss of 30 on a risk of 20 is 1.5 R
    assert R.daily_loss_limit(baskets([-30, -30], risk=20.0), 1.0)["taken"].tolist() == [True, False]


def test_account_replay_holds_one_basket_at_a_time():
    # the second entry (bar 3) arrives while the first basket (bars 0-5) is open: skipped
    b = baskets([+10, -500, -20], entry_idx=[0, 3, 5], close_idx=[5, 9, 12])
    acc = R.account_replay(b, 2000.0)
    assert acc["acct_taken"] == 2 and acc["acct_net"] == pytest.approx(-10.0)
    assert acc["acct_max_dd"] == pytest.approx(20.0) and not acc["acct_wiped"]


def test_account_replay_drawdown_counts_floating_losses_and_a_wipe_ends_it():
    b = baskets([+100, +50, -100], mae=[-300, -900, -100])
    acc = R.account_replay(b, 2000.0)
    # balance 2,000 -> 2,100 -> 2,150 -> 2,050; the deepest point is 2,100 - 900 = 1,200, measured from 2,100
    assert acc["acct_max_dd"] == pytest.approx(900.0) and acc["acct_net"] == pytest.approx(50.0)
    wiped = R.account_replay(baskets([+100, +1, +100], mae=[0, -2100, 0]), 2000.0)
    assert wiped["acct_wiped"] and wiped["acct_net"] == pytest.approx(-2000.0) and wiped["acct_taken"] == 2
    assert wiped["acct_wiped_by"] == "one basket"                  # that basket alone floated more than the account
    assert R.account_replay(baskets([-1500, -600, +100]), 2000.0)["acct_wiped"]       # losses alone reach zero
    bled = R.account_replay(baskets([-30.0] * 80), 2000.0)        # no basket loses more than 1.5 %, the account still ends at zero
    assert bled["acct_wiped"] and bled["acct_wiped_by"] == "many losses" and bled["acct_taken"] == 67
    assert acc["acct_wiped_by"] == ""


def test_clustered_standard_error():
    x = np.array([1.0, -1.0, 2.0, -2.0, 3.0, -3.0])
    # every observation its own cluster: the usual standard error of the mean (with the small-sample factor n / (n - 1))
    assert R.clustered_se(x, np.arange(6)) == pytest.approx(x.std(ddof=1) / np.sqrt(6))
    # the same numbers moving together inside two weeks are worth two observations, not six
    assert R.clustered_se(x, np.array([0, 0, 0, 1, 1, 1])) > 0
    assert R.clustered_se(np.array([1.0, 1.0, -1.0, -1.0]), np.array([0, 0, 1, 1])) == pytest.approx(1.0)
    assert np.isnan(R.clustered_se(x, np.zeros(6)))


# ───────────────────────────── entry lists ─────────────────────────────

def test_the_list_waits_for_the_reference_trade_to_close():
    fr = random_frame(3, n=2000)
    fr.vote[:] = np.where(np.arange(2000) % 2, 1, -1)             # a signal at every close
    idx, dirs = R.entry_list(fr, "votes")
    ref = R.simulate(fr, idx, dirs, MECH[R.REFERENCE])
    assert len(idx) > 20
    assert (idx[1:] >= ref["close_idx"].to_numpy()[:-1]).all()    # never two reference trades at once
    assert (idx[1:] == ref["close_idx"].to_numpy()[:-1]).all()    # and no signal is wasted once flat
    assert (dirs == fr.vote[idx]).all()


def test_trend_list_takes_only_votes_in_the_direction_of_the_trend():
    fr = random_frame(4, n=3000)
    fr.trend[:] = np.where(np.arange(3000) // 500 % 2, 1, -1)
    idx, dirs = R.entry_list(fr, "trend")
    assert len(idx) > 5 and (dirs == fr.trend[idx]).all() and (fr.vote[idx] == dirs).all()
    assert (R.entry_candidates(fr, "trend") != 0).sum() < (R.entry_candidates(fr, "votes") != 0).sum()


def test_random_list_is_a_coin_flip_that_depends_on_time_and_seed_only():
    fr = random_frame(5, n=20000)
    cand = R.entry_candidates(fr, "random")
    share, longs = (cand != 0).mean(), (cand[cand != 0] == 1).mean()
    assert abs(share - R.RANDOM_ENTRY_PROB) < 0.02 and abs(longs - 0.5) < 0.02
    assert (cand == R.entry_candidates(fr, "random")).all()
    assert (cand != R.entry_candidates(fr, "random", seed=1)).any()
    # the same timestamps give the same draws whatever else is loaded around them
    part = R.Frame.synthetic(fr.o[5000:9000], fr.h[5000:9000], fr.l[5000:9000], fr.c[5000:9000], t=fr.t[5000:9000])
    assert (R.entry_candidates(part, "random") == cand[5000:9000]).all()
    assert abs(np.corrcoef(cand[:-1] != 0, cand[1:] != 0)[0, 1]) < 0.03


def test_entries_need_an_open_market_and_respect_the_first_date():
    fr = random_frame(6, n=1500)
    fr.vote[:] = 1
    fr.ok[:700] = False
    idx, _ = R.entry_list(fr, "votes")
    assert idx.min() >= 700
    idx, _ = R.entry_list(fr, "votes", first_s=int(fr.t[1000]) + 60)
    assert idx.min() == 1000


def test_mechanism_list_is_fixed():
    names = [m.name for m in R.mechanisms()]
    assert names[0] == R.REFERENCE and len(set(names)) == len(names) == 42
    assert all((m.control or R.REFERENCE) in names for m in R.mechanisms())
    assert all(m.twin in names for m in R.mechanisms() if m.twin)


# ───────────────────────────── no look-ahead (real bars) ─────────────────────────────

FEATURES = ["atr", "trend", "rsi", "ev", "vote", "m15_close", "session"]


@pytest.fixture(scope="module", params=["XAUUSDm", "BTCUSDm"])
def real(request, fixture_store):
    m1 = store.load_m1(request.param, store.to_ms("2026-10-01"), store.to_ms("2026-12-01"), fixture_store)
    return request.param, m1, R.build_frame(request.param, m1)


def test_real_frame_is_usable(real):
    symbol, m1, fr = real
    assert fr.ok.sum() > 0.5 * len(fr) and np.isfinite(fr.atr[fr.ok]).all()
    assert set(np.unique(fr.vote)) <= {-1, 0, 1} and (fr.vote != 0).sum() > 100
    assert (fr.vote[~fr.m15_close] == 0).all()
    assert ((fr.t[fr.m15_close] + 60) % 900 == 0).all()            # votes exist only where an M15 bar closes
    assert fr.session.any() == (symbol == "XAUUSDm")               # BTC has no closure to be flat for


@pytest.mark.parametrize("keep", [0.37, 0.61, 0.83, 0.97])
def test_nothing_known_at_a_close_changes_when_later_bars_are_removed(real, keep):
    symbol, m1, full = real
    n = int(len(full) * keep) + 7                                  # an arbitrary bar, not a bar boundary of any timeframe
    cut = R.build_frame(symbol, {key: v[:n] for key, v in m1.items()})
    for name in FEATURES:
        a, b = getattr(cut, name), getattr(full, name)[..., :n]
        assert np.array_equal(a, b, equal_nan=True), name
    # the two fields that look at the TIME of the next bar agree for every bar that has a next bar
    for name in ("live", "hole", "ok"):
        assert np.array_equal(getattr(cut, name)[:n - 1], getattr(full, name)[:n - 1]), name


@pytest.mark.parametrize("keep", [0.55, 0.9])
def test_entries_and_closed_baskets_do_not_depend_on_later_bars(real, keep):
    symbol, m1, full = real
    n = int(len(full) * keep) + 3
    cut = R.build_frame(symbol, {key: v[:n] for key, v in m1.items()})
    for kind in R.LISTS:
        idx_full, dirs_full = R.entry_list(full, kind)
        idx_cut, dirs_cut = R.entry_list(cut, kind)
        early = idx_full < n - 1
        assert early.sum() > 10
        assert np.array_equal(idx_cut, idx_full[early]) and np.array_equal(dirs_cut, dirs_full[early])
        compared = 0
        for mech in SIMULATED:
            a = R.simulate(full, idx_cut, dirs_cut, mech)
            b = R.simulate(cut, idx_cut, dirs_cut, mech)
            done = (a["close_idx"] < n - 1).to_numpy()             # baskets that were over before the cut
            pd.testing.assert_frame_equal(a[done], b[done], check_exact=True)
            compared += bool(done.any())
        assert compared >= len(SIMULATED) - 2                      # (a 20 USD exit on BTC can outlast the fixture)


def test_poisoning_the_future_changes_nothing_before_it(real):
    symbol, m1, full = real
    n = int(len(full) * 0.7)
    bad = {key: v.copy() for key, v in m1.items()}
    for key in ("o", "h", "l", "c", "ask_c"):
        bad[key][n:] *= 3.0                                        # every later price is nonsense
    poisoned = R.build_frame(symbol, bad)
    for name in FEATURES:
        assert np.array_equal(getattr(poisoned, name)[..., :n], getattr(full, name)[..., :n], equal_nan=True), name


def test_ladder_rsi_is_the_live_rsi_of_the_forming_bar(real):
    from backtesting.analysis.signal import live_indicator
    symbol, m1, fr = real
    ind = live_indicator()
    rng = np.random.default_rng(11)
    for tier, tf in enumerate(R.LADDER_TFS):
        bars = store.resample_bars(m1, tf)
        for j in rng.integers(len(fr) // 2, len(fr), 12):
            q = int(np.searchsorted(bars["t"], fr.t[j], side="right")) - 1          # the bar of this timeframe that is forming
            series = pd.Series(np.append(bars["c"][max(0, q - 400):q], fr.c[j]))    # its closed predecessors + the price now
            assert fr.rsi[tier, j] == pytest.approx(float(ind.calculate_rsi(series, 14).iloc[-1]), abs=1e-6)


def test_trend_and_atr_come_from_the_last_closed_h1_bar(real):
    from backtesting.analysis.signal import live_indicator
    symbol, m1, fr = real
    h1 = store.resample_bars(m1, 3600)
    sig = live_indicator().calculate_macd(pd.Series(h1["c"]))["signal"].to_numpy()
    atr = R.wilder_atr(h1["h"], h1["l"], h1["c"])
    rng = np.random.default_rng(12)
    for j in rng.integers(len(fr) // 2, len(fr), 40):
        closed = np.flatnonzero(h1["t"] + 3600 <= fr.t[j] + 60)   # H1 bars that have ended by the close of M1 bar j
        assert fr.trend[j] == np.sign(sig[closed[-1]]) and fr.atr[j] == atr[closed[-1]]
    # half past the hour: the hour that is still forming is not among the closed bars
    j = int(np.flatnonzero(fr.t % 3600 == 1800)[-1])
    last_closed = h1["t"][np.flatnonzero(h1["t"] + 3600 <= fr.t[j] + 60)[-1]]
    assert last_closed < fr.t[j] // 3600 * 3600
    # the last minute of an hour: that hour has just closed and is the one read
    j = int(np.flatnonzero(fr.t % 3600 == 3540)[-1])
    assert h1["t"][np.flatnonzero(h1["t"] + 3600 <= fr.t[j] + 60)[-1]] == fr.t[j] // 3600 * 3600


def test_closure_gaps_measure_the_jump_over_a_silence():
    # an hour of silence with a jump of 2, then two days of silence with a jump of 5; ATR 2
    t = np.array([0, 60, 120, 120 + 3600, 180 + 3600, 180 + 3600 + 2 * 86400, 240 + 3600 + 2 * 86400])
    c = np.array([100, 100, 100, 102, 102, 107, 107.0])
    daily, weekend = R.closure_gaps(R.Frame.synthetic(c, c, c, c, t=t, atr=2.0))
    assert (daily["closure"], daily["n"], daily["max_usd"], daily["max_r"]) == ("daily break", 1, 2.0, 1.0)
    assert (weekend["closure"], weekend["n"], weekend["max_usd"], weekend["max_r"]) == ("weekend or holiday", 1, 5.0, 2.5)


def test_wilder_atr_by_hand():
    h, l, c = np.array([10.0, 12.0, 11.0, 15.0]), np.array([9.0, 10.0, 9.0, 11.0]), np.array([9.5, 11.0, 10.0, 14.0])
    # true ranges: 1, 2.5 (12 - 9.5), 2, 5 (15 - 10); ATR(2): seed (1 + 2.5) / 2 = 1.75, then 1.875, then 3.4375
    assert R.wilder_atr(h, l, c, 2)[1:] == pytest.approx([1.75, 1.875, 3.4375])


# ───────────────────────────── the result files and the report tables ─────────────────────────────

def test_evaluate_summarise_and_report_tables(tmp_path, monkeypatch):
    fr = random_frame(9, n=4000)
    idx, dirs = R.entry_list(fr, "votes")
    res = R.evaluate(fr, idx, dirs)
    assert set(res) == set(MECH)
    rows, halves = R.summarise(res, R.mechanisms(), {"symbol": "TEST", "period": "DEV", "list": "votes"})
    by = {r["mechanism"]: r for r in rows}
    ref = by[R.REFERENCE]
    assert ref["n"] == len(idx) and ref["exp"] == pytest.approx(res[R.REFERENCE]["pnl"].mean())
    assert ref["gross"] == pytest.approx(ref["exp"] + ref["spread_paid"])
    assert by["Hedge lock, unlocked by the next vote signal"]["twin_max_abs_diff"] < 1e-9
    assert by["Daily loss limit 1 R"]["n"] < ref["n"]
    # the baskets in which a ladder added, against the same baskets without the adds
    lad, flat = res["Budget 3 R, 2 adds 0.5 ATR apart"], res["Budget 3 R, no add"]
    added = (lad["adds"] > 0).to_numpy()
    row = by["Budget 3 R, 2 adds 0.5 ATR apart"]
    assert 0 < row["added_n"] == added.sum() < len(idx)
    assert row["added_exp"] == pytest.approx(lad["pnl"][added].mean()) and row["added_ctrl_exp"] == pytest.approx(flat["pnl"][added].mean())
    assert row["added_ctrl_win_pct"] == pytest.approx((flat["pnl"][added] > 0).mean() * 100)
    assert "added_n" not in by["Budget 3 R, no add"] and "added_n" not in by["Martingale: double after a loss, up to x8"]
    assert by["Martingale: double after a loss, up to x8"]["max_units"] <= 8
    assert sum(h["n"] for h in halves if h["mechanism"] == R.REFERENCE) == len(idx)
    for row in rows:
        for tag in R.OTHER_READINGS:
            row.update({f"{col}_{tag}": row.get(col) for col in ("exp", "acct_net", "acct_wiped")})
    gaps = [{"symbol": "TEST", "period": "DEV", "list": "", "order": 0, "closure": "daily break", "n": 3, "median_usd": 1.0,
             "p99_usd": 2.0, "max_usd": 2.5, "median_r": 0.1, "p99_r": 0.2, "max_r": 0.25}]
    for name, data in (("recovery_mechanisms.csv", rows), ("recovery_mechanisms_halfyears.csv", halves),
                       ("recovery_mechanisms_gaps.csv", gaps)):
        R._merge(tmp_path / name, pd.DataFrame(data)).to_csv(tmp_path / name, index=False)
    report = tmp_path / "report.md"
    tags = ["design", "main:TEST:votes", "cost:TEST:votes", "halves:TEST:votes", "change:TEST:votes", "order:TEST:votes",
            "adds:TEST:votes", "budget:TEST"]
    report.write_text("intro\n\n" + "\n\ntext stays\n\n".join(f"<!-- table {tag} -->\nold\n<!-- /table -->" for tag in tags + ["gaps:TEST"])
                      + "\n", encoding="utf-8")
    assert R.update_report(report, tmp_path) == len(tags) + 1
    text = report.read_text(encoding="utf-8")
    assert "old" not in text and text.count("text stays") == len(tags) and text.startswith("intro")
    assert text.count("| " + R.REFERENCE + " |") >= len(tags) - 1 and text.count("| Mechanism |") == len(tags)
    assert "| daily break | DEV | 3 | $1.00 | $2.00 | $2.50 | 0.2 |" in text
    assert R.update_report(report, tmp_path) == len(tags) + 1 and report.read_text(encoding="utf-8") == text   # idempotent
    summary = R.render("summary:votes", tmp_path)
    assert summary.count("\n") == len(R.SUMMARY_ROWS) + 1 and set(R.SUMMARY_ROWS) <= set(MECH)
    assert "TEST: expectancy per entry" in summary
    overview = R.render("overview", tmp_path)
    assert overview.count("| " + R.REFERENCE + " |") == 1 and "(of 1)" in overview and "| 1.0 to 1.0 |" in overview
