"""
The support / resistance study (``backtesting/research/sr_trades.py``).

Four things are pinned down here:

* the bar-level trade simulator on hand-made bars: where a buy and a sell are filled, that the stop
  is taken before the target when one bar reaches both, gaps, the time stop, one position at a
  time, an order filled inside its bar;
* the level logic on hand-made bars: when a swing is known, how days and weeks are cut, how a zone
  is armed, touched, broken, retested and retired, where a rule puts its stop and target, and what
  a placebo price is;
* no look-ahead: everything computed on history cut off at an arbitrary bar, or followed by a
  different future, is identical for every decision up to that bar;
* the figures: the summary of a known list of trades, the comparison with placebo sets, and a whole
  run with its tables on the bundled real bars.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import sr_trades as S

DAY = 86400


# ───────────────────────────── helpers ─────────────────────────────

def sim(o, h, l, c, cands, spread=0.0, hold_s=0.0, step=60):
    """
    Run the simulator on small bars. ``cands`` = [(bar, direction, stop, target), ...] are market
    orders at the close of their bar; a fifth value is the bid quote at which an order was filled
    inside its bar instead.
    """
    n = len(c)
    f = lambda x: np.asarray(x, np.float64)
    sp = np.full(n, float(spread)) if np.isscalar(spread) else f(spread)
    bar = np.asarray([k[0] for k in cands], np.int64)
    d = np.asarray([k[1] for k in cands], np.int64)
    inbar = np.asarray([len(k) > 4 for k in cands], np.int64)
    quote = f([k[4] if len(k) > 4 else c[k[0]] for k in cands])
    out = S.simulate(np.arange(n, dtype=np.int64) * step, f(o), f(h), f(l), f(c), sp, bar, d,
                     S.market_fill(quote, sp[bar], d) if len(cands) else quote, inbar,
                     f([k[2] for k in cands]), f([k[3] for k in cands]), float(hold_s))
    names = ("cand", "bar_in", "bar_out", "price_in", "price_out", "why")
    return [dict(zip(names, (x.item() for x in row))) for row in zip(*out)]


def flat(n, price=100.0):
    """n bars that open, trade and close at one price."""
    return [price] * n, [price] * n, [price] * n, [price] * n


def gold_like_m1(days=75, seed=5, start="2024-03-03"):
    """
    Synthetic M1 bars with gold's session pattern: Sunday from 22:05, a daily break 20:57 - 22:02,
    Friday until 20:57, nothing on Saturday; a random walk with changing volatility and a small spread.
    """
    rng = np.random.default_rng(seed)
    t0 = store.to_ms(start) // 1000
    t = t0 + 60 * np.arange(days * 1440, dtype=np.int64)
    minute = (t % DAY) // 60
    weekday = ((t // DAY) + 4) % 7                           # 0 = Sunday
    in_break = (minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)
    keep = ~in_break & (weekday != 6)
    keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
    t = t[keep]
    n = len(t)
    vol = 0.35 * np.exp(0.6 * np.sin(np.arange(n) / 4000.0) + 0.3 * np.sin(np.arange(n) / 611.0))
    step = rng.normal(0.0, 1.0, n) * vol
    c = 2000.0 + np.cumsum(step)
    o = np.concatenate(([2000.0], c[:-1])) + rng.normal(0.0, 0.02, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5, n)) * vol
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5, n)) * vol
    sp = 0.16 + 0.1 * rng.random(n)
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "ask_c": c + sp, "spread_mean": sp, "spread_max": sp * 1.5,
            "n": np.full(n, 30, np.int64)}


def cut(m1, n):
    return {k: v[:n] for k, v in m1.items()}


def everything(symbol, m1):
    """Frames, levels, zones, events and one placebo set of an M1 history."""
    fr = S.build_frames(symbol, m1)
    raw = S.raw_levels(fr)
    zones = S.build_zones(raw)
    ev = S.scan_events(fr, zones)
    return fr, raw, zones, ev, S.placebo_prices(zones, 3, ev.lives)


PER_BAR = ("atr", "trend_h4", "trend_d1", "adx_h4", "rsi15", "bull_div", "bear_div", "h1_new", "h1_c",
           "m15_new", "m15_o", "m15_h", "m15_l", "m15_c")
EVENT_FIELDS = ("bar", "zone", "type", "dir", "breaks", "touches", "touches_side", "n_src", "mask", "ext", "price")


def assert_same_past(full, part, n):
    """``part`` was computed from the first n bars only (or from another future): its past must equal ``full``."""
    fr, raw, zones, ev, fake = full
    fr2, raw2, zones2, ev2, fake2 = part
    now = int(fr.T[n - 1])
    for name in PER_BAR:
        np.testing.assert_array_equal(getattr(fr, name)[:n], getattr(fr2, name)[:n], err_msg=name)
    a, b = raw["t"] <= now, raw2["t"] <= now
    for name in ("t", "price", "src", "kind", "atr"):
        np.testing.assert_array_equal(raw[name][a], raw2[name][b], err_msg=f"level {name}")
    np.testing.assert_array_equal(np.minimum(raw["expire"][a], now + 1), np.minimum(raw2["expire"][b], now + 1))
    k = int((zones.t <= now).sum())
    assert k == int((zones2.t <= now).sum())
    for name in ("price", "t", "atr", "kind"):
        np.testing.assert_array_equal(getattr(zones, name)[:k], getattr(zones2, name)[:k], err_msg=f"zone {name}")
    a, b = zones.j_t <= now, zones2.j_t <= now
    for name in ("j_t", "j_zone", "j_src"):
        np.testing.assert_array_equal(getattr(zones, name)[a], getattr(zones2, name)[b], err_msg=name)
    np.testing.assert_array_equal(fake[:k], fake2[:k], err_msg="placebo prices")
    a, b = ev.bar < n, ev2.bar < n
    for name in EVENT_FIELDS:
        np.testing.assert_array_equal(getattr(ev, name)[a], getattr(ev2, name)[b], err_msg=f"event {name}")
    for rule in S.RULES:
        for p in (S.Params(), S.Params(entry="touch")):
            ca, cb = S.candidates(fr, ev, rule, p), S.candidates(fr2, ev2, rule, p)
            for x, y in zip(ca, cb):
                np.testing.assert_array_equal(x[ca[0] < n], y[cb[0] < n], err_msg=f"candidates of rule {rule.key}, {p.entry}")
    return k, int(a.sum())


# ───────────────────────────── simulator ─────────────────────────────

def test_buy_fills_at_the_ask_and_a_flat_round_trip_costs_the_spread():
    o, h, l, c = flat(5)
    (tr,) = sim(o, h, l, c, [(0, +1, 90.0, 110.0)], spread=0.4, hold_s=120)
    assert tr["price_in"] == pytest.approx(100.4)          # bought at bid + spread
    assert (tr["bar_in"], tr["bar_out"], tr["why"]) == (0, 2, S.EXIT_TIME)
    assert tr["price_out"] - tr["price_in"] == pytest.approx(-0.4)   # sold at the bid: the spread is the cost


def test_sell_fills_at_the_bid_and_is_closed_on_the_ask():
    o, h, l, c = flat(5)
    (tr,) = sim(o, h, l, c, [(0, -1, 110.0, 90.0)], spread=0.4, hold_s=120)
    assert tr["price_in"] == pytest.approx(100.0)          # sold at the bid
    assert tr["price_out"] == pytest.approx(100.4)         # bought back at bid + spread
    # the stop of a short is reached by the ASK: bid high 109.7 + 0.4 >= 110
    o, h, l, c = flat(4)
    h[2] = 109.7
    (tr,) = sim(o, h, l, c, [(0, -1, 110.0, 90.0)], spread=0.4)
    assert (tr["bar_out"], tr["why"], tr["price_out"]) == (2, S.EXIT_STOP, 110.0)
    # and its target only when the ask is there: a bid low of 90.2 is not enough, 89.6 is
    o, h, l, c = flat(5)
    l[2], l[3] = 90.2, 89.6
    (tr,) = sim(o, h, l, c, [(0, -1, 110.0, 90.0)], spread=0.4)
    assert (tr["bar_out"], tr["why"], tr["price_out"]) == (3, S.EXIT_TARGET, 90.0)


def test_stop_is_taken_first_when_one_bar_reaches_both():
    o, h, l, c = flat(4)
    h[2], l[2] = 106.0, 94.0                                # the same bar trades through target and stop
    (buy,) = sim(o, h, l, c, [(0, +1, 95.0, 105.0)])
    assert (buy["bar_out"], buy["why"], buy["price_out"]) == (2, S.EXIT_STOP, 95.0)
    (sell,) = sim(o, h, l, c, [(0, -1, 105.0, 95.0)])
    assert (sell["bar_out"], sell["why"], sell["price_out"]) == (2, S.EXIT_STOP, 105.0)
    # with the stop out of reach the same bar is a win
    (buy,) = sim(o, h, l, c, [(0, +1, 93.0, 105.0)])
    assert (buy["why"], buy["price_out"]) == (S.EXIT_TARGET, 105.0)


def test_entry_bar_itself_cannot_stop_or_fill_the_trade():
    o, h, l, c = flat(4)
    h[0], l[0] = 120.0, 80.0                                # the range of the entry bar lies before the entry
    (tr,) = sim(o, h, l, c, [(0, +1, 95.0, 105.0)])
    assert (tr["bar_out"], tr["why"]) == (3, S.EXIT_END)


def test_gap_through_the_stop_fills_at_the_open_and_a_target_never_better_than_its_price():
    o, h, l, c = flat(4)
    o[2], h[2], l[2], c[2] = 92.0, 93.0, 91.0, 92.5         # opens below the stop of a buy
    (tr,) = sim(o, h, l, c, [(0, +1, 95.0, 105.0)])
    assert (tr["why"], tr["price_out"]) == (S.EXIT_STOP, 92.0)
    (tr,) = sim(o, h, l, c, [(0, -1, 105.0, 95.0)])         # for a sell the same bar gaps beyond its target
    assert (tr["why"], tr["price_out"]) == (S.EXIT_TARGET, 95.0)
    o, h, l, c = flat(4)
    o[2], h[2], l[2], c[2] = 108.0, 109.0, 107.0, 108.0     # opens above the stop of a sell
    (tr,) = sim(o, h, l, c, [(0, -1, 105.0, 95.0)], spread=0.5)
    assert (tr["why"], tr["price_out"]) == (S.EXIT_STOP, 108.5)


def test_order_filled_inside_a_bar_can_be_stopped_by_that_bar_but_not_paid_by_it():
    o, h, l, c = flat(5)
    h[1], l[1] = 106.0, 94.0                                # bar 1 trades through the entry, the stop and the target
    (tr,) = sim(o, h, l, c, [(1, +1, 95.0, 105.0, 99.0)], spread=0.2)       # bought when the bid reached 99
    assert tr["price_in"] == pytest.approx(99.2)
    assert (tr["bar_in"], tr["bar_out"], tr["why"], tr["price_out"]) == (1, 1, S.EXIT_STOP, 95.0)
    (tr,) = sim(o, h, l, c, [(1, -1, 105.0, 95.0, 101.0)], spread=0.2)      # sold at 101, the ask then reaches 105
    assert (tr["price_in"], tr["bar_out"], tr["why"], tr["price_out"]) == (101.0, 1, S.EXIT_STOP, 105.0)
    l[1] = 96.0                                             # the stop of the buy is now out of reach in bar 1 ...
    h[3] = 105.0                                            # ... and the target comes two bars later
    (tr,) = sim(o, h, l, c, [(1, +1, 95.0, 105.0, 99.0)], spread=0.2)
    assert (tr["bar_out"], tr["why"], tr["price_out"]) == (3, S.EXIT_TARGET, 105.0)         # bar 1's own high does not count
    # the same order sent at the close of bar 1 is untouched by bar 1 and can be followed by another on its exit bar
    trades = sim(o, h, l, c, [(1, +1, 95.0, 105.0), (3, -1, 110.0, 90.0)])
    assert [(t["bar_in"], t["bar_out"]) for t in trades] == [(1, 3), (3, 4)]


def test_one_position_at_a_time():
    o, h, l, c = flat(12)
    h[5] = 105.0                                            # the first buy reaches its target in bar 5
    l[8] = 99.0                                             # the sell entered at the close of bar 5 reaches its target in bar 8
    trades = sim(o, h, l, c, [(0, +1, 90.0, 105.0), (2, +1, 90.0, 101.0), (3, -1, 110.0, 99.0),
                              (5, -1, 110.0, 99.0), (7, +1, 90.0, 120.0)])
    assert [tr["cand"] for tr in trades] == [0, 3]          # 1 and 2 arrive while the first is open; 4 while the second is
    assert [(tr["bar_in"], tr["bar_out"], tr["why"]) for tr in trades] == [(0, 5, S.EXIT_TARGET), (5, 8, S.EXIT_TARGET)]
    # without the first position the skipped candidates would have traded
    assert [tr["cand"] for tr in sim(o, h, l, c, [(2, +1, 90.0, 101.0), (3, -1, 110.0, 99.0)])] == [0]
    assert [tr["cand"] for tr in sim(o, h, l, c, [(3, -1, 110.0, 99.0)])] == [0]


def test_time_stop_counts_wall_clock_time_and_the_end_of_data_closes_the_rest():
    o, h, l, c = flat(6, 100.0)
    c[3] = 101.0
    h[3] = 101.0
    (tr,) = sim(o, h, l, c, [(0, +1, 90.0, 110.0)], hold_s=180)       # bars are 60 s: the third bar after entry
    assert (tr["bar_out"], tr["why"], tr["price_out"]) == (3, S.EXIT_TIME, 101.0)
    (tr,) = sim(o, h, l, c, [(0, +1, 90.0, 110.0)], hold_s=180, step=3600)   # hourly bars: the very next bar
    assert (tr["bar_out"], tr["why"]) == (1, S.EXIT_TIME)
    (tr,) = sim(o, h, l, c, [(0, +1, 90.0, 110.0)])                    # no time stop
    assert (tr["bar_out"], tr["why"]) == (5, S.EXIT_END)
    assert sim(o, h, l, c, [(5, +1, 90.0, 110.0)]) == []               # nothing can be entered on the last bar


# ───────────────────────────── bars and levels ─────────────────────────────

def test_swing_needs_k_bars_on_each_side():
    h = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3, 2, 1], float)
    l = h - 0.5
    hi, lo = S.swing_points(h, l, 3)
    assert hi.tolist() == [3] and lo.tolist() == [6]
    hi, lo = S.swing_points(h, l, 1)
    assert hi.tolist() == [3, 8] and lo.tolist() == [6]
    # equal highs: only the first of them is the swing
    h = np.array([1, 2, 5, 5, 2, 1, 0], float)
    assert S.swing_points(h, h - 0.5, 2)[0].tolist() == [2]
    assert S.swing_points(h[:4], h[:4] - 0.5, 2)[0].tolist() == []     # too few bars after it


def test_swing_level_is_known_only_after_the_bars_to_its_right_have_closed():
    m1 = gold_like_m1(days=30)
    fr = S.build_frames("XAUUSDm", m1)
    lp = S.LevelParams()
    raw = S.raw_levels(fr, lp)
    for bars, src, k in ((fr.h1, S.SRC_H1, lp.k_h1), (fr.h4, S.SRC_H4, lp.k_h4), (fr.d1, S.SRC_D1, lp.k_d1)):
        mine = raw["src"] == src
        assert mine.any()
        for t_known, price, kind in zip(raw["t"][mine], raw["price"][mine], raw["kind"][mine]):
            closed = bars.tc <= t_known                     # the bars a trader has at that moment
            series = bars.h[closed] if kind > 0 else bars.l[closed]
            j = len(series) - 1 - k                         # the swing bar: exactly k closed bars to its right
            assert series[j] == price
            assert price == (series[j - k:].max() if kind > 0 else series[j - k:].min())
    # previous-day levels: the high / low of a day, known when that day is over
    day = raw["src"] == S.SRC_PD
    assert set(raw["t"][day]) <= set(fr.d1.tc.tolist())
    j = np.searchsorted(fr.d1.tc, raw["t"][day])
    assert np.all((raw["price"][day] == fr.d1.h[j]) | (raw["price"][day] == fr.d1.l[j]))


def test_short_days_are_merged_into_the_next_full_day_and_weeks_start_on_sunday():
    m1 = gold_like_m1(days=21)                              # starts on Sunday 2024-03-03
    d1, w1 = S.day_bars(m1, 360), S.week_bars(m1)
    first_monday = store.to_ms("2024-03-04") // 1000
    assert d1.t[0] == first_monday - DAY                    # the Sunday evening opens Monday's bar ...
    assert d1.tc[0] == first_monday + DAY                   # ... which closes when Monday ends
    assert np.all(np.diff(d1.tc) >= DAY)
    sunday_open = m1["o"][0]
    assert d1.o[0] == sunday_open
    monday = (m1["t"] >= first_monday - DAY) & (m1["t"] < first_monday + DAY)
    assert d1.h[0] == m1["h"][monday].max() and d1.l[0] == m1["l"][monday].min()
    assert len(d1) == 15                                    # three weeks of five trading days
    assert np.all((w1.t // DAY + 4) % 7 == 0) and np.all(w1.tc - w1.t == 7 * DAY)
    # a short day at the very end forms no bar yet
    upto = int(np.searchsorted(m1["t"], first_monday + 7 * DAY - 3600))      # stop inside the second Sunday evening
    assert len(S.day_bars(cut(m1, upto), 360)) == 5


def scan(bars, zone_price=100.0, atr=10.0, h1_closes=(), m15=(), zone_w=0.15, arm_w=1.0, joins=((0, 0),), with_lives=False):
    """
    Run the event scan on hand-made M1 bars [(high, low, close), ...] around zones known from
    ``joins`` = ((bar, zone), ...). ``h1_closes`` = {bar: close of the H1 bar that has just closed},
    ``m15`` = {bar: (open, high, low, close) of the M15 bar that has just closed}.
    """
    n = len(bars)
    f = lambda k: np.asarray([b[k] for b in bars], np.float64)
    T = 60 * (1 + np.arange(n, dtype=np.int64))
    h1_new, h1_c = np.zeros(n, np.bool_), np.full(n, np.nan)
    for b, px in dict(h1_closes).items():
        h1_new[b], h1_c[b] = True, px
    m_new, m_o, m_h, m_l, m_c = np.zeros(n, np.bool_), *(np.full(n, np.nan) for _ in range(4))
    for b, (bo, bh, bl, bc) in dict(m15).items():
        m_new[b], m_o[b], m_h[b], m_l[b], m_c[b] = True, bo, bh, bl, bc
    zp = np.atleast_1d(np.asarray(zone_price, np.float64))
    j_t = np.asarray([T[b] for b, _ in joins], np.int64)
    j_zone = np.asarray([q for _, q in joins], np.int64)
    E, lives, *_ = S._scan(T, f(0), f(1), f(2), np.full(n, float(atr)), h1_new, h1_c, m_new, m_o, m_h, m_l, m_c, zp,
                           j_t, j_zone, np.zeros(len(joins), np.int64), np.full(len(joins), 10 ** 9, np.int64), zone_w, arm_w)
    kinds = {S.EV_TOUCH: "touch", S.EV_REV: "reversal", S.EV_BREAK: "break"}
    events = [(int(e[0]), kinds[int(e[2])], int(e[3]), int(e[4]), int(e[5])) for e in E]    # bar, type, dir, breaks, touches
    if with_lives:                                           # (zone, first bar closed while live, bar of retirement or None)
        bar = lambda t: None if t > T[-1] else int(t // 60 - 1)
        return events, [(int(q), bar(a), bar(b)) for q, a, b in lives]
    return events


def test_zone_is_touched_only_when_armed_and_from_its_current_side():
    # level 100, ATR 10: the zone is 98.5 .. 101.5 and a close 10 away arms it
    bars = [(115, 114, 115),        # 0  the level becomes known at this close, price 15 above: support, armed
            (115, 103, 104),        # 1  comes down, not yet in the zone
            (104, 101.5, 102),      # 2  low reaches the top of the zone -> touch (buy)
            (103, 100, 102),        # 3  still there: no second touch
            (109, 102, 109),        # 4  9 away: not far enough to arm
            (109, 101, 102),        # 5  back in the zone, not armed -> nothing
            (111, 102, 110.5),      # 6  closes 10.5 away -> armed again
            (110, 101.2, 103)]      # 7  second touch, one touch before it
    assert scan(bars) == [(2, "touch", +1, 0, 0), (7, "touch", +1, 0, 1)]


def test_level_is_not_traded_before_it_is_known():
    bars = [(115, 114, 115), (115, 100, 101), (112, 101, 112), (112, 100.5, 101)]
    assert scan(bars, joins=((0, 0),)) == [(1, "touch", +1, 0, 0), (3, "touch", +1, 0, 1)]
    # the same bars, but the level only becomes known at the close of bar 1: bar 1 itself is no touch,
    # the level starts unarmed (price is 1 away), is armed by bar 2 and touched by bar 3
    assert scan(bars, joins=((1, 0),)) == [(3, "touch", +1, 0, 0)]
    # and a level that becomes known at the close of the last bar produces nothing
    assert scan(bars, joins=((3, 0),)) == []


def test_break_turns_the_role_then_a_first_return_is_a_retest_and_a_second_break_retires_the_zone():
    bars = [(115, 114, 115),        # 0  known; support
            (112, 101, 102),        # 1  touch (buy)
            (102, 96, 97),          # 2  trades below the zone; no H1 close yet -> still support
            (99, 96, 98.4),         # 3  H1 closes at 98.4, beyond 98.5 -> break downwards; now resistance
            (98, 88, 89),           # 4  closes 11 below -> armed
            (98.6, 90, 97),         # 5  high reaches the bottom of the zone from below -> the retest (sell)
            (97, 85, 86),           # 6  away again -> armed
            (103, 95, 102),         # 7  touch from below once more (second since the break) ...
            (104, 101, 103),        # 8  ... and the H1 closes above 101.5 -> second break: retired
            (118, 103, 117),        # 9  far above
            (117, 99, 100)]         # 10 back at the old level: nothing, the zone is gone
    assert scan(bars, h1_closes={3: 98.4, 8: 103.0}) == [
        (1, "touch", +1, 0, 0), (3, "break", -1, 0, 1), (5, "touch", -1, 1, 1), (7, "touch", -1, 1, 2), (8, "break", +1, 1, 3)]
    # an H1 close inside the zone is not a break
    assert scan(bars[:4], h1_closes={3: 98.6}) == [(1, "touch", +1, 0, 0)]
    # the zone is live from the close at which it became known until its second break ...
    assert scan(bars, h1_closes={3: 98.4, 8: 103.0}, with_lives=True)[1] == [(0, 0, 8)]
    # ... and a new level at the same price starts it afresh: unbroken, untouched, on the side price is on
    events, lives = scan(bars, h1_closes={3: 98.4, 8: 103.0}, joins=((0, 0), (9, 0)), with_lives=True)
    assert events[-1] == (10, "touch", +1, 0, 0) and lives == [(0, 0, 8), (0, 9, None)]


def test_reversal_bar_must_reach_the_zone_and_close_back_beyond_the_level_and_its_own_open():
    bars = [(115, 114, 115), (112, 100.5, 101), (103, 99, 102.5), (104, 102, 103)]
    # M15 bar closing at bar 2: opened 101, low 99 (in the zone), closed 102.5 above the level and above its open
    assert ("reversal", +1) in [(e[1], e[2]) for e in scan(bars, m15={2: (101.0, 103.0, 99.0, 102.5)})]
    for bad in ((103.0, 103.5, 99.0, 102.5),       # closes below its open
                (99.5, 100.0, 99.0, 99.9),         # closes below the level
                (102.0, 104.0, 101.6, 103.0)):     # never reached the zone
        assert "reversal" not in [e[1] for e in scan(bars, m15={2: bad})]


def test_rule_geometry_stop_beyond_the_zone_and_target_a_multiple_of_the_risk():
    m1 = gold_like_m1(days=40)
    fr, raw, zones, ev, _ = everything("XAUUSDm", m1)
    p = S.Params()
    for key in ("b2", "c", "d", "b2.rev"):
        rule = S.RULE_BY_KEY[key]
        bar, d, stop, target, risk, zone, price, inbar = S.candidates(fr, ev, rule, p)
        assert len(bar) > 0 and not inbar.any()
        hit = np.flatnonzero((ev.type == rule.event) & (ev.breaks == rule.breaks))
        a = fr.atr[bar]
        level = np.empty(len(bar))
        for k, (b, dd) in enumerate(zip(bar, d)):           # the level of the event behind each entry
            prices = ev.price[hit][(ev.bar[hit] == b) & (ev.dir[hit] == dd)]
            level[k] = prices[np.argmin(np.abs(prices - dd * 0.5 * a[k] - stop[k]))]
        entry = np.where(d > 0, fr.c[bar] + fr.spread[bar], fr.c[bar])          # ask for a buy, bid for a sell
        np.testing.assert_array_equal(price, entry)
        np.testing.assert_allclose(stop, level - d * 0.5 * a)                     # 0.15 zone + 0.35 beyond it
        np.testing.assert_array_equal(zones.price[zone], level)                   # ... of the zone the entry names
        np.testing.assert_allclose(risk, d * (entry - stop))
        np.testing.assert_allclose(target, entry + d * 2.0 * risk)
        assert np.all(risk >= p.min_risk_w * a) and np.all(risk <= p.max_risk_w * a)
        beyond = d * (fr.c[bar] - level) / a
        assert np.all(beyond > p.zone_w) if rule.event == S.EV_BREAK else np.all(beyond >= -p.zone_w)
    # the trend filter splits the bounces into two disjoint halves, the level's timeframe into three classes
    n = {r.key: len(S.candidates(fr, ev, r, p)[0]) for r in S.RULES}
    assert n["a"] > 0 and n["b1"] > 0 and n["a"] + n["b1"] <= n["b2"]
    assert n["b2.h1"] + n["b2.h4"] + n["b2.d1"] == n["b2"] and n["d.h1"] + n["d.h4"] + n["d.d1"] == n["d"]
    assert min(n["b2.h1"], n["b2.h4"], n["b2.d1"]) > 0
    for key, limit in (("b2.rsi", n["b2"]), ("b2.div", n["b2"]), ("b2.src2", n["b2"]), ("c+", n["c"]), ("d+", n["d"]), ("e", n["b2"])):
        assert 0 < n[key] < limit
    assert n["b2.fresh"] + n["b2.tested"] == n["b2"]
    with_trend = S.candidates(fr, ev, S.RULE_BY_KEY["a"], p)
    assert np.all(with_trend[1] * fr.trend_h4[with_trend[0]] > 0)


def test_entering_on_the_touch_fills_at_the_zone_edge_with_what_was_known_before_the_bar():
    m1 = gold_like_m1(days=40)
    fr, raw, zones, ev, _ = everything("XAUUSDm", m1)
    close, touch = S.Params(), S.Params(entry="touch")
    for key in ("b2", "a", "c"):
        rule = S.RULE_BY_KEY[key]
        bar, d, stop, target, risk, zone, price, inbar = S.candidates(fr, ev, rule, touch)
        assert len(bar) > 10 and inbar.all()
        a = fr.atr[bar - 1]                                 # the ATR of the M1 close before the touch bar
        level = zones.price[zone]
        edge = level + d * 0.15 * a
        quote = np.where(d > 0, np.minimum(edge, fr.o[bar]), np.maximum(edge, fr.o[bar]))   # the edge, or the open beyond it
        np.testing.assert_allclose(price, np.where(d > 0, quote + fr.spread[bar], quote))
        assert np.all(np.where(d > 0, fr.l[bar] <= edge, fr.h[bar] >= edge))                # the bid did get there
        np.testing.assert_allclose(stop, level - d * 0.5 * a)
        np.testing.assert_allclose(target, price + d * 2.0 * risk)
        if rule.trend:
            assert np.all(d * fr.trend_h4[bar - 1] > 0)
        # the touch entry does not wait for the close: let every third touch bar close far through its zone -
        # the same orders are still sent, while an entry at the close leaves exactly those out
        pick = np.arange(len(bar)) % 3 == 0
        c2 = fr.c.copy()
        c2[bar[pick]] = level[pick] - d[pick] * 0.4 * fr.atr[bar[pick]]
        fr2 = dataclasses.replace(fr, c=c2)
        again = S.candidates(fr2, ev, rule, touch)
        np.testing.assert_array_equal(again[0], bar)
        np.testing.assert_array_equal(again[6], price)
        at_close = S.candidates(fr2, ev, rule, close)
        kept = set(zip(at_close[0].tolist(), at_close[5].tolist()))
        assert not any(pair in kept for pair in zip(bar[pick].tolist(), zone[pick].tolist()))
        assert sum(pair in kept for pair in zip(bar[~pick].tolist(), zone[~pick].tolist())) > 0.8 * (~pick).sum()
    # the reversal bar and the breakout are entered at the close of their bar under either setting
    for key in ("b2.rev", "d"):
        for x, y in zip(S.candidates(fr, ev, S.RULE_BY_KEY[key], close), S.candidates(fr, ev, S.RULE_BY_KEY[key], touch)):
            np.testing.assert_array_equal(x, y)
    tr = S.run_rule(fr, ev, S.RULE_BY_KEY["b2"], touch)
    assert len(tr) > 10 and np.all(tr.t_in[1:] >= tr.t_out[:-1]) and np.all(tr.t_out >= tr.t_in)
    assert np.all(tr.r[tr.why == S.EXIT_STOP] <= -1.0 + 1e-9)
    np.testing.assert_allclose(tr.r[tr.why == S.EXIT_TARGET], 2.0)


def test_trades_of_a_rule_never_overlap():
    m1 = gold_like_m1(days=40)
    fr, raw, zones, ev, _ = everything("XAUUSDm", m1)
    for key in ("b2", "d"):
        tr = S.run_rule(fr, ev, S.RULE_BY_KEY[key])
        assert len(tr) > 5 and tr.n_candidates >= len(tr)
        assert np.all(tr.t_in[1:] >= tr.t_out[:-1]) and np.all(tr.t_out > tr.t_in)
        assert np.all(tr.risk > 0)
        buys = tr.dir > 0
        np.testing.assert_array_equal(tr.cost[buys], fr.spread[np.searchsorted(fr.T, tr.t_in[buys])])     # paid at the entry
        np.testing.assert_array_equal(tr.cost[~buys], fr.spread[np.searchsorted(fr.T, tr.t_out[~buys])])  # paid at the exit
        won, lost = tr.why == S.EXIT_TARGET, tr.why == S.EXIT_STOP
        np.testing.assert_allclose(tr.r[won], 2.0)                    # a target pays exactly twice the risk
        assert np.all(tr.r[lost] <= -1.0 + 1e-9)                      # a stop costs the risk, more after a gap


def test_placebo_prices_are_away_from_every_level_known_at_that_time():
    m1 = gold_like_m1(days=40)
    fr, raw, zones, ev, fake = everything("XAUUSDm", m1)
    assert len(zones) > 50
    shift = np.abs(fake - zones.price) / zones.atr
    assert np.all(shift >= 1.0 - 1e-9) and np.all(shift <= 3.0 + 1e-9)
    assert 0.3 < np.mean(fake > zones.price) < 0.7                    # up and down about equally often
    zone, born, gone = ev.lives
    known = np.flatnonzero(zones.t <= fr.T[-1])                       # every zone founded inside the data goes live ...
    first_life = np.unique(zone, return_index=True)[1]
    np.testing.assert_array_equal(zone[first_life], known)
    assert np.all(gone > born) and np.all(born >= zones.t[zone])
    assert np.all(born[first_life] - zones.t[known] <= 4 * DAY)       # ... at the first M1 close after it is known
    near = 0
    for q in range(len(zones)):                                       # the real zones live when zone q is founded
        live = (born <= zones.t[q]) & (gone > zones.t[q]) & (zone != q)
        if live.any():
            near += np.abs(zones.price[zone[live]] - fake[q]).min() < 0.5 * zones.atr[q] - 1e-9
    assert near <= 0.02 * len(zones)                                  # all but the rare zone with no free price
    np.testing.assert_array_equal(fake, S.placebo_prices(zones, 3, ev.lives))     # a seed fixes the set
    assert not np.array_equal(fake, S.placebo_prices(zones, 4, ev.lives))
    assert np.all(np.abs(S.placebo_prices(zones, 3) - zones.price) >= zones.atr - 1e-9)   # also without the live spans
    # the same zones at other prices: same levels and lifetimes, a different set of events
    ev2 = S.scan_events(fr, zones, fake)
    assert len(ev2) > 0 and not np.array_equal(ev.bar[:50], ev2.bar[:50])


def test_level_class_is_the_highest_timeframe_in_the_zone():
    bit = lambda *src: sum(1 << s for s in src)
    masks = np.array([bit(S.SRC_H1), bit(S.SRC_PD), bit(S.SRC_H1, S.SRC_PD), bit(S.SRC_H1, S.SRC_H4),
                      bit(S.SRC_H4, S.SRC_PD), bit(S.SRC_H1, S.SRC_H4, S.SRC_D1), bit(S.SRC_PW), bit(S.SRC_H1, S.SRC_PW)])
    assert S.level_class(masks).tolist() == [1, 1, 1, 2, 2, 3, 3, 3]


# ───────────────────────────── no look-ahead ─────────────────────────────

def test_truncated_history_gives_the_same_past_synthetic():
    m1 = gold_like_m1(days=75)
    full = everything("XAUUSDm", m1)
    n_all = len(m1["t"])
    t = m1["t"]
    rng = np.random.default_rng(42)
    cuts = sorted(set(rng.integers(n_all // 3, n_all - 1, size=5).tolist()))
    cuts.append(int(np.flatnonzero(t % 3600 == 3540)[len(t) // 150]) + 1)        # exactly on an H1 close
    cuts.append(int(np.flatnonzero(t % DAY == 0)[40]))                           # the last bar before midnight
    cuts.append(int(np.flatnonzero(((t // DAY + 4) % 7 == 0))[-200]))            # inside a Sunday evening
    seen_zones = seen_events = 0
    for n in cuts:
        k, e = assert_same_past(full, everything("XAUUSDm", cut(m1, n)), n)
        seen_zones, seen_events = max(seen_zones, k), max(seen_events, e)
    assert seen_zones > 100 and seen_events > 300            # the comparison was not empty


def test_a_different_future_does_not_change_the_past():
    m1 = gold_like_m1(days=60, seed=8)
    other = gold_like_m1(days=60, seed=9)
    full = everything("XAUUSDm", m1)
    for share in (0.41, 0.55, 0.62, 0.74, 0.87, 0.93):
        n = int(len(m1["t"]) * share)
        shift = m1["c"][n - 1] - other["c"][n - 1]
        mixed = {k: v.copy() for k, v in m1.items()}
        for k in ("o", "h", "l", "c", "ask_c"):
            mixed[k][n:] = other[k][n:] + shift             # same past, another path afterwards
        assert not np.array_equal(mixed["c"], m1["c"])
        k, e = assert_same_past(full, everything("XAUUSDm", mixed), n)
        assert k > 40 and e > 150                           # the comparison was not empty


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_truncated_history_gives_the_same_past_real_bars(symbol, fixture_store):
    m1 = store.load_m1(symbol, store.to_ms("2026-10-01"), store.to_ms("2026-12-01"), store_dir=fixture_store)
    n_all = len(m1["t"])
    assert n_all > 10000
    full = everything(symbol, m1)
    assert len(full[3]) > 20
    rng = np.random.default_rng(1)
    for n in sorted(rng.integers(n_all // 2, n_all - 1, size=4).tolist()):
        assert_same_past(full, everything(symbol, cut(m1, n)), n)


def test_trades_closed_before_a_cut_are_the_same_with_and_without_the_later_bars():
    m1 = gold_like_m1(days=60)
    n = int(len(m1["t"]) * 0.7)
    fr, _, _, ev, _ = everything("XAUUSDm", m1)
    fr2, _, _, ev2, _ = everything("XAUUSDm", cut(m1, n))
    now = fr.T[n - 1]
    for key in ("a", "b2", "c", "d", "e", "b2.rev"):
        full, part = S.run_rule(fr, ev, S.RULE_BY_KEY[key]), S.run_rule(fr2, ev2, S.RULE_BY_KEY[key])
        np.testing.assert_array_equal(full.t_in[full.t_in <= now][: len(part)], part.t_in)      # the same entries
        done = part.why != S.EXIT_END
        assert done.sum() >= len(part) - 1
        np.testing.assert_array_equal(full.pnl[: len(part)][done], part.pnl[done])              # and the same results


# ───────────────────────────── statistics ─────────────────────────────

def test_a_run_on_the_bundled_bars_is_stored_and_tabulated(tmp_path, fixture_store, monkeypatch):
    """The whole path on twelve days of real BTC bars: rules on real and placebo levels, the stored run, the tables."""
    monkeypatch.setenv("ALCADEIAS_STORE_DIR", str(fixture_store))
    monkeypatch.setitem(S.PERIODS, "FIXTURE", ("2026-10-28", "2026-11-10"))
    monkeypatch.setattr(S, "WARMUP_DAYS", 4)
    assert S.months_present("BTCUSDm", "FIXTURE") == (2, 2)
    S.run("FIXTURE", symbols=("BTCUSDm",), sets=("base", "plain placebo"), out=tmp_path, n_placebo=3, log=lambda *_: None)
    res = json.loads((tmp_path / "FIXTURE_BTCUSDm_base.json").read_text(encoding="utf-8"))
    assert list(res["rules"]) == [r.key for r in S.RULES] and res["set"] == "base"
    assert res["zones"] > 20 and res["events"]["touch"] > 5 and 0 < res["density"]["share_of_time_in_a_zone"] < 0.5
    assert res["span"][0] == store.to_ms("2026-11-01") // 1000          # four days of warm-up, then entries
    b2 = res["rules"]["b2"]
    assert b2["n"] > 0 and b2["candidates"] >= b2["n"] and b2["placebo"]["sets"] == 3
    assert b2["total_usd"] == pytest.approx(b2["exp_usd"] * b2["n"])
    assert sum(h["n"] for h in b2["halves"].values()) == b2["n"]
    wanted = lambda key: res["rules"][key]["candidates"]                # entries wanted, before the one-position limit
    assert wanted("b2.h1") + wanted("b2.h4") + wanted("b2.d1") == wanted("b2") and wanted("a") + wanted("b1") <= wanted("b2")
    plain = json.loads((tmp_path / "FIXTURE_BTCUSDm_plain_placebo.json").read_text(encoding="utf-8"))
    assert plain["rules"]["b2"]["exp_r"] == b2["exp_r"]                 # the same real trades, another control
    text = S.tables(["FIXTURE"], tmp_path, symbols=("BTCUSDm",))
    for needle in ("### What was run", "b2: Bounce, any trend", "d+: Breakout on the H1 close, with the trend",
                   "real \u2212 placebo", "2026H2", "How often a bounce works"):
        assert needle in text, needle
    assert text.count("\n| ") > 120 and "nan" not in text               # 26 rules in several tables, every cell filled or "-"
    with pytest.raises(ValueError):                                      # the reserved year cannot be read by accident
        monkeypatch.setitem(S.PERIODS, "EARLY", ("2023-06-01", "2023-07-01"))
        S.load_frames("BTCUSDm", "EARLY")

def test_summary_figures_on_a_known_list_of_trades():
    t0 = store.to_ms("2026-02-02") // 1000
    t_in = t0 + DAY * np.array([0, 1, 2, 9, 10, 170], np.int64)
    pnl = np.array([2.0, -1.0, -1.0, -1.0, 4.0, -2.0])
    tr = S.Trades(t_in, t_in + 3600, np.array([1, 1, -1, -1, 1, -1]), pnl, np.array([1.0, 1.0, 1.0, 1.0, 2.0, 2.0]),
                  np.array([2, 1, 1, 1, 2, 1]), n_candidates=9)
    s = S.summarize(tr, unit=0.01, days=182.625)
    assert (s["n"], s["candidates"]) == (6, 9)
    assert s["win_rate"] == pytest.approx(2 / 6)
    assert s["avg_win"] == pytest.approx(0.03) and s["avg_loss"] == pytest.approx(-0.0125)
    assert s["exp_usd"] == pytest.approx(0.01 / 6) and s["total_usd"] == pytest.approx(0.01)
    assert s["per_quarter_usd"] == pytest.approx(0.005)                # two quarters
    assert s["exp_r"] == pytest.approx((2 - 1 - 1 - 1 + 2 - 1) / 6)
    assert (s["worst_run"], s["worst_run_usd"]) == (3, pytest.approx(-0.03))
    assert set(s["halves"]) == {"2026H1", "2026H2"} and s["halves"]["2026H2"]["n"] == 1
    assert (s["long_n"], s["short_n"]) == (3, 3)


def test_placebo_comparison_counts_the_sets_that_do_at_least_as_well():
    t0 = store.to_ms("2026-02-02") // 1000
    rng = np.random.default_rng(0)

    def trades(mean, n=400):
        t_in = t0 + np.sort(rng.integers(0, 200 * DAY, n))
        r = rng.normal(mean, 1.0, n)
        return S.Trades(t_in, t_in + 60, np.ones(n, np.int64), r, np.ones(n), np.ones(n, np.int64))

    real = trades(0.5)
    fakes = [trades(0.0) for _ in range(12)]
    out = S.compare_with_placebo(real, fakes, unit=1.0)
    assert out["sets"] == 12 and out["beaten_by"] == 0
    assert out["diff_r"] == pytest.approx(real.r.mean() - np.concatenate([f.r for f in fakes]).mean())
    assert out["diff_lo"] > 0.25 and out["diff_hi"] < 0.75 and 0.02 < out["diff_se"] < 0.12
    assert out["real_win"] > out["placebo_win"]
    assert set(out["halves"]) == {"2026H1", "2026H2"}                  # 200 days from 2 February 2026
    for hy, x in out["halves"].items():
        assert x["diff_r"] == pytest.approx(x["real_r"] - x["placebo_r"]) and 0.2 < x["diff_r"] < 0.8
    assert sum(x["n"] for x in out["halves"].values()) == len(real)
    same = S.compare_with_placebo(fakes[0], fakes[1:], unit=1.0)
    assert same["diff_lo"] < 0 < same["diff_hi"]                       # no effect: the interval covers zero
    # placebo trades split by where their zone's placebo price lies: zones 0-4 beyond the swing, 5-9 inside the range
    for f in fakes:
        f.zone = rng.integers(0, 10, len(f))
        f.pnl = np.where(f.zone < 5, 1.0, -1.0)
    flags = [np.arange(10) < 5 for _ in fakes]
    split = S.compare_with_placebo(real, fakes, unit=1.0, outward=flags)
    assert split["placebo_beyond_r"] == 1.0 and split["placebo_inside_r"] == -1.0
    assert split["placebo_beyond_n"] + split["placebo_inside_n"] == pytest.approx(400, abs=1)
