"""
René Balke's strategies as rebuilt in ``backtesting/research/balke.py``.

* The server clock: New York + 7 h, so GMT+2 in winter and GMT+3 in summer.
* Range Breakout on hand-made bars: the levels, the order and close times, a side already passed is skipped, the stop
  (1% of the entry, or the other side of the range), one fill cancels the other.
* ATR Breakout: an oversized candle that closes near its extreme is a signal, an ordinary one is not.
* Go Long and Turnaround Tuesday: their clock times and the moving-average rule.
* The multi-position account: overlapping trades are all taken; on trades that never overlap it is the
  single-position account to the cent.
* The cost scenario and the buy-and-hold reference.
* No look-ahead: every rule makes the same decisions up to a time T when the history after T is removed or replaced.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import balke as B
from backtesting.research import external as E
from backtesting.research import final10 as F

DAY = 86400
MIN = 60


def utc(when: str) -> int:
    return int(store.to_ms(when) // 1000)


def bars(t, o, h, l, c, spread=0.2):
    n = len(t)
    f = lambda x: np.asarray(x, np.float64)
    return {"t": np.asarray(t, np.int64), "o": f(o), "h": f(h), "l": f(l), "c": f(c),
            "spread_mean": np.full(n, float(spread)), "n": np.ones(n, np.int64)}


def minute_bars(start: str, end: str, price: float = 100.0, spread: float = 0.2):
    t = np.arange(utc(start), utc(end), MIN, dtype=np.int64)
    p = np.full(len(t), price)
    return bars(t, p, p.copy(), p.copy(), p.copy(), spread)


def gold(m1):
    return E.Market("XAUUSDm", m1)


def index(m1, symbol="US30m"):
    return B.SpecMarket(symbol, m1, **B.INDEX_SPECS[symbol])


def at(m1, when: str) -> int:
    return int(np.searchsorted(m1["t"], utc(when)))


# ───────────────────────────── the clock ─────────────────────────────

def test_the_server_clock_is_new_york_plus_seven_hours():
    m = gold(bars([utc("2024-01-15 10:00"), utc("2024-07-15 10:00")], [1, 1], [1, 1], [1, 1], [1, 1]))
    srv = B.server_clock(m)
    assert srv[0] - m.t[0] == 2 * 3600            # winter: GMT+2
    assert srv[1] - m.t[1] == 3 * 3600            # US summer time: GMT+3
    back = B.server_to_utc(srv)
    assert (back == m.t).all()


def test_the_clock_switches_on_the_us_dates_not_the_european_ones():
    # 2024: the US moved its clocks on 10 Mar, Europe on 31 Mar; in between New York is UTC-4
    m = gold(bars([utc("2024-03-20 10:00")], [1], [1], [1], [1]))
    assert B.server_clock(m)[0] - m.t[0] == 3 * 3600


# ───────────────────────────── Range Breakout ─────────────────────────────

def rb_day(spread=0.2, close_at_high=False, crash=True, close_near_high=False):
    """Monday 4 Mar 2024 (GMT+2): flat at 100; inside the range (01:05 - 04:05 UTC) one bar reaches 101 and one 99;
    at 05:00 UTC the price breaks up; at 10:00 UTC it falls to 98, through the long's stop and the sell level."""
    m1 = minute_bars("2024-03-04 00:00", "2024-03-04 18:00", 100.0, spread)
    i = at(m1, "2024-03-04 02:00")
    m1["h"][i] = 101.0
    j = at(m1, "2024-03-04 03:00")
    m1["l"][j] = 99.0
    if close_at_high:
        k = at(m1, "2024-03-04 04:04")
        m1["h"][k] = m1["c"][k] = 101.0
    if close_near_high:                                       # the bid below the level, the ask above it
        k = at(m1, "2024-03-04 04:04")
        m1["h"][k] = m1["c"][k] = 100.9
    b = at(m1, "2024-03-04 05:00")
    m1["h"][b], m1["c"][b] = 102.0, 101.5
    m1["o"][b + 1:] = m1["h"][b + 1:] = m1["l"][b + 1:] = m1["c"][b + 1:] = 101.5
    if crash:
        x = at(m1, "2024-03-04 10:00")
        m1["l"][x], m1["c"][x] = 98.0, 98.5
        m1["o"][x + 1:] = m1["h"][x + 1:] = m1["l"][x + 1:] = m1["c"][x + 1:] = 98.5
    return m1


def test_range_breakout_places_its_orders_at_the_range_edges_at_his_times():
    m = gold(rb_day())
    b = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0)
    p = b.plan
    order = np.flatnonzero(np.isfinite(p.f["bstop"]) | np.isfinite(p.f["sstop"]))
    assert len(order) == 1
    k = order[0]
    assert p.dt[k] == utc("2024-03-04 04:05")                 # 06:05 server time
    assert p.f["bstop"][k] == 101.0 and p.f["sstop"][k] == 99.0
    assert p.f["slf"][k] == pytest.approx(0.01)
    close = np.flatnonzero(p.xl & p.xs)
    assert len(close) == 1 and p.dt[close[0]] == utc("2024-03-04 16:55")   # 18:55 server time
    assert b.risk_sizing.mode == "risk" and b.risk_sizing.rf == pytest.approx(0.01)


def test_one_fill_cancels_the_other_and_the_stop_is_one_percent_of_the_entry():
    m = gold(rb_day())
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0).plan
    path = E.run_path(m, p, 0, len(m))
    assert len(path) == 1                                     # the sell stop at 99 is gone after the buy fill
    assert path.dir[0] == 1 and path.epx[0] == pytest.approx(101.0)
    assert E.WHY_NAMES[int(path.why[0])] == "stop"
    assert path.xpx[0] == pytest.approx(101.0 * 0.99)


def test_without_a_crash_the_trade_is_closed_at_his_close_time():
    m = gold(rb_day(crash=False))
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0).plan
    path = E.run_path(m, p, 0, len(m))
    assert len(path) == 1 and m.t[path.xix[0]] == utc("2024-03-04 16:55")
    assert path.xpx[0] == pytest.approx(101.5)                # a long closes on the bid


def test_a_side_whose_level_is_already_passed_is_skipped():
    # the range's last bar closes at the high: the ask is above the buy level, MT5 would refuse the buy stop
    m = gold(rb_day(close_at_high=True))
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0).plan
    k = np.flatnonzero(np.isfinite(p.f["sstop"]))[0]
    assert np.isnan(p.f["bstop"][k]) and p.f["sstop"][k] == 99.0


def test_a_buy_stop_below_the_ask_is_skipped_even_when_the_bid_is_below_the_level():
    m = gold(rb_day(close_near_high=True))                    # bid 100.9 < 101 <= ask 101.1
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0).plan
    k = np.flatnonzero(np.isfinite(p.f["sstop"]))[0]
    assert np.isnan(p.f["bstop"][k]) and p.f["sstop"][k] == 99.0


def test_the_factor_stop_sits_at_the_other_side_of_the_range():
    m = gold(rb_day())
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "factor", 1.0, 1.0).plan
    k = np.flatnonzero(np.isfinite(p.f["bstop"]))[0]
    assert p.f["bsl"][k] == 99.0 and p.f["ssl"][k] == 101.0


def test_weekends_are_skipped_unless_asked_for():
    m1 = minute_bars("2024-03-09 00:00", "2024-03-09 18:00")      # a Saturday
    m1["h"][120] = 101.0
    m1["l"][150] = 99.0
    m = E.Market("BTCUSDm", m1)
    with pytest.raises(ValueError):
        B.range_breakout(m, (3, 5), (6, 5), (18, 55), "factor", 1.0, 1.0)
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "factor", 1.0, 1.0, weekdays_only=False).plan
    assert np.isfinite(p.f["bstop"]).sum() == 1


# ───────────────────────────── ATR Breakout ─────────────────────────────

def atr_market(signal="bull"):
    """210 quiet hours (each H1 candle 1.0 high to low), then one candle 5.0 high to low, then quiet again."""
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 00:00") + 230 * 3600, MIN, dtype=np.int64)
    n = len(t)
    o = np.full(n, 100.0)
    h, l, c = o + 0.0, o - 0.0, o.copy()
    hour = (t - t[0]) // 3600
    first = np.flatnonzero(np.diff(hour, prepend=-1) != 0)
    h[first + 10] = 100.5
    l[first + 20] = 99.5
    s = first[210]
    if signal == "bull":
        h[s:s + 60] = np.linspace(100.2, 105.0, 60)
        c[s:s + 60] = np.linspace(100.1, 104.6, 60)
        o[s + 1:s + 60] = c[s:s + 59]
        l[s:s + 60] = np.minimum(o[s:s + 60], c[s:s + 60]) - 0.05
        l[s] = 100.0
        c[s + 60:] = o[s + 60:] = h[s + 60:] = l[s + 60:] = 104.6
        h[first[first > s] + 10] = 105.1
        l[first[first > s] + 20] = 104.1
    elif signal in ("bear", "small"):
        size = 5.0 if signal == "bear" else 2.0               # "small": 2x the ATR, under the 2.5x threshold
        h[s:s + 60] = np.linspace(100.0, 100.05, 60)
        c[s:s + 60] = np.linspace(99.9, 100.0 - size + 0.4, 60)
        o[s + 1:s + 60] = c[s:s + 59]
        l[s:s + 60] = np.minimum(o[s:s + 60], c[s:s + 60]) - 0.05
        l[s + 59] = 100.0 - size
        h[s:s + 60] = np.maximum(h[s:s + 60], np.maximum(o[s:s + 60], c[s:s + 60]))
        if signal == "small":                                 # closes at its high: bullish, near the extreme
            c[s:s + 60] = np.linspace(100.0, 101.9, 60)
            o[s + 1:s + 60] = c[s:s + 59]
            h[s:s + 60] = np.maximum(o[s:s + 60], c[s:s + 60]) + 0.02
            l[s:s + 60] = np.minimum(o[s:s + 60], c[s:s + 60]) - 0.02
            l[s] = 100.0 - 0.0
        c[s + 60:] = o[s + 60:] = h[s + 60:] = l[s + 60:] = c[s + 59]
        h[first[first > s] + 10] = c[s + 59] + 0.5
        l[first[first > s] + 20] = c[s + 59] - 0.5
    elif signal == "middle":                                  # big, but it closes in the middle of its range
        h[s + 10] = 105.0
        l[s + 20] = 100.0
        c[s:s + 60] = 102.5
        o[s + 1:s + 60] = 102.5
    return E.Market("XAUUSDm", bars(t, o, h, l, c, 0.2)), t[first[211]]


def test_an_oversized_candle_closing_at_its_high_is_a_buy_at_the_next_candle():
    m, t_next = atr_market("bull")
    b = B.atr_breakout(m)
    p = b.plan
    assert len(p) == 1
    assert p.dt[0] == t_next and p.want[0] == 1
    assert p.f["slf"][0] == pytest.approx(0.005) and p.f["tpr"][0] == pytest.approx(4.0)
    assert b.risk_sizing.rf == pytest.approx(0.005)


def test_an_oversized_candle_closing_at_its_low_is_a_sell():
    m, t_next = atr_market("bear")
    p = B.atr_breakout(m).plan
    assert len(p) == 1 and p.dt[0] == t_next and p.want[0] == -1


def test_a_candle_of_twice_the_atr_is_below_the_threshold():
    m, _ = atr_market("small")
    b = m.bars("H1")
    rng = b.h - b.l
    assert rng.max() > 1.8 * np.median(rng)                  # a clearly bigger candle, closing near its high
    assert len(B.atr_breakout(m).plan) == 0


def test_an_oversized_candle_closing_in_its_middle_is_no_signal():
    m, _ = atr_market("middle")
    assert len(B.atr_breakout(m).plan) == 0


# ───────────────────────────── several positions at once ─────────────────────────────

def overlap_market():
    """Two buys an hour apart; both reach their 2% target later, the second one first in price terms."""
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 12:00"), MIN, dtype=np.int64)
    p = np.full(len(t), 100.0)
    m1 = bars(t, p, p.copy(), p.copy(), p.copy(), 0.1)
    r = at(m1, "2024-03-04 06:00")
    for name in ("o", "h", "l", "c"):
        m1[name][r:] = 103.0
    m1["o"][r] = 100.0
    return E.Market("XAUUSDm", m1)


def test_every_signal_opens_its_own_trade_while_others_are_open():
    m = overlap_market()
    dts = [utc("2024-03-04 01:00"), utc("2024-03-04 02:00")]
    plan = E.make_plan(m, dts, want=1, slf=0.005, tpr=4.0)
    single = E.run_path(m, plan, 0, len(m))
    assert len(single) == 1                                   # one position at a time takes only the first
    both = B.every_signal(m, plan, 0, len(m))
    assert len(both) == 2 and list(m.t[both.eix]) == dts
    assert (np.asarray([E.WHY_NAMES[int(w)] for w in both.why]) == "target").all()


def test_the_multi_position_account_adds_up_overlapping_trades():
    m = overlap_market()
    plan = E.make_plan(m, [utc("2024-03-04 01:00"), utc("2024-03-04 02:00")], want=1, slf=0.005, tpr=4.0)
    res, daily, tr = B.multi_account(m, plan, E.BOT, 0, len(m))
    assert len(tr) == 2 and res.skipped == 0
    # 1 unit each (balance < $2,500): bought at the ask 100.1, the target 2% of the entry above (4 x the 0.5% stop)
    assert tr["pnl"].tolist() == pytest.approx([0.02 * 100.1, 0.02 * 100.1])
    assert res.final == pytest.approx(E.ACCOUNT + 2 * 0.02 * 100.1)


@pytest.mark.parametrize("sizing", [E.BOT, E.Sizing("risk", rf=0.01), E.Sizing("expo")])
def test_without_overlaps_the_multi_position_account_is_the_single_position_one(sizing):
    m1 = gold_like(days=30)
    m = E.Market("XAUUSDm", m1)
    gl = B.go_long(m)                                        # one trade a day, closed the same day
    plan = gl.plan if sizing.mode != "expo" else gl.risk
    if sizing.mode == "risk":
        plan = plan.copy(f={**plan.f, "slf": np.full(len(plan), 0.003)})
    a, z = 0, len(m)
    r1, d1, _ = F._bar_account(E, m, plan, sizing, a, z)
    r2, d2, _ = B.multi_account(m, plan, sizing, a, z)
    assert r2.final == pytest.approx(r1.final, abs=1e-9)
    assert r2.max_dd == pytest.approx(r1.max_dd, abs=1e-12)
    assert len(r2.trades_pnl) == len(r1.trades_pnl) and r2.skipped == r1.skipped
    assert np.allclose(d1.to_numpy(), d2.to_numpy(), equal_nan=True)


def test_a_long_and_a_short_open_at_once_are_marked_on_their_own_sides():
    """A buy at 01:00 and a sell at 02:00 (hedging). From 03:00 the price rises 1.0: the long gains on the bid, the
    short loses on the ask; both close at the window's end."""
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 06:00"), MIN, dtype=np.int64)
    p = np.full(len(t), 100.0)
    m1 = bars(t, p, p.copy(), p.copy(), p.copy(), 0.2)
    r = at(m1, "2024-03-04 03:00")
    for name in ("o", "h", "l", "c"):
        m1[name][r:] = 101.0
    m = E.Market("XAUUSDm", m1)
    plan = E.make_plan(m, [utc("2024-03-04 01:00"), utc("2024-03-04 02:00")], want=[1, -1], slf=0.05)
    res, daily, tr = B.multi_account(m, plan, E.BOT, 0, len(m))
    assert list(tr["side"]) == ["BUY", "SELL"]
    # long: bought at the ask 100.2, closed at the bid 101.0; short: sold at the bid 100.0, closed at the ask 101.2
    assert tr["pnl"].tolist() == pytest.approx([101.0 - 100.2, 100.0 - 101.2])
    assert res.final == pytest.approx(E.ACCOUNT + (101.0 - 100.2) + (100.0 - 101.2))
    # the trough: both open at 02:00 - 03:00, marked at the long's bid low and the short's ask high
    assert res.max_dd == pytest.approx((0.2 + 0.2) / E.ACCOUNT, rel=0.02)


def test_the_multi_position_account_is_wiped_when_the_equity_reaches_zero():
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 03:00"), MIN, dtype=np.int64)
    p = np.full(len(t), 100.0)
    m1 = bars(t, p, p.copy(), p.copy(), p.copy(), 0.0)
    crash = at(m1, "2024-03-04 02:00")
    m1["l"][crash] = 1.0
    m = E.Market("XAUUSDm", m1)
    plan = E.make_plan(m, [utc("2024-03-04 01:00")], want=1, expo=1.0)
    saved = E.ACCOUNT
    E.ACCOUNT = 50.0
    try:                                                      # exposure sizing: 1 oz is worth $100 > the $50 balance
        res, _, _ = B.multi_account(m, plan, E.Sizing("expo"), 0, len(m))
        assert res.skipped == 1 and res.final == pytest.approx(50.0)
        res, _, _ = B.multi_account(m, plan, E.BOT, 0, len(m))     # the unit rule buys 1 oz anyway
        assert res.wiped and res.final == 0.0 and res.max_dd == 1.0
        assert res.trades_pnl.sum() == pytest.approx(-50.0)         # the trade loses what the account held
    finally:
        E.ACCOUNT = saved


def test_an_unfilled_breakout_order_is_cancelled_at_the_close_time():
    """The range is 99 - 101; the price stays inside until after 18:55 server time, then breaks out: no trade."""
    m1 = minute_bars("2024-03-04 00:00", "2024-03-04 20:00")
    m1["h"][at(m1, "2024-03-04 02:00")] = 101.0
    m1["l"][at(m1, "2024-03-04 03:00")] = 99.0
    late = at(m1, "2024-03-04 17:30")                         # 19:30 server time, after the 18:55 cancel
    m1["h"][late:] = 103.0
    m1["c"][late:] = m1["o"][late:] = m1["l"][late:] = 102.5
    m = gold(m1)
    p = B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0).plan
    assert len(E.run_path(m, p, 0, len(m))) == 0


def test_turnaround_tuesday_finds_mondays_on_both_sides_of_a_dst_switch():
    """The US clocks moved on Sun 10 Mar 2024: Monday 01:05 server time is 23:05 UTC on Sunday 3 Mar, but 22:05 UTC
    on Sunday 10 Mar."""
    t = np.concatenate([np.arange(utc("2024-03-03 21:00"), utc("2024-03-04 02:00"), MIN),
                        np.arange(utc("2024-03-10 20:00"), utc("2024-03-11 02:00"), MIN)]).astype(np.int64)
    c = np.full(len(t), 100.0)
    m = index(bars(t, c, c, c, c, 2.0))
    days = B._session_days(m, (1, 5), True)
    opens = B.server_to_utc(days * DAY + 65 * MIN)
    assert list(opens) == [utc("2024-03-03 23:05"), utc("2024-03-10 22:05")]
    assert ((days + 3) % 7 == 0).all()                         # both are Mondays on the server clock


def two_trades(gap: bool):
    """A long from bar 10 (1% stop). gap=False: a short from bar 20, and bar 30 falls to 1950, stopping the long out
    while the short stays open. gap=True: the price gaps from 2000 to 1900 at bar 60 through the long's stop, a short
    opens at that same open, and the bar closes at 1850."""
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 02:00"), MIN, dtype=np.int64)
    p = np.full(len(t), 2000.0)
    m1 = bars(t, p, p.copy(), p.copy(), p.copy(), 0.2)
    if gap:
        m1["o"][60:] = m1["h"][60:] = 1900.0
        m1["l"][60:] = m1["c"][60:] = 1850.0
        m1["o"][61:] = m1["h"][61:] = 1850.0
        dts = [int(m1["t"][10]), int(m1["t"][60])]
    else:
        m1["l"][30:] = m1["c"][30:] = m1["o"][31:] = m1["h"][31:] = 1950.0
        dts = [int(m1["t"][10]), int(m1["t"][20])]
    m = E.Market("XAUUSDm", m1)
    return m, E.make_plan(m, dts, want=[1, -1], slf=0.01)


def test_a_stop_out_while_another_trade_stays_open_does_not_raise_the_peak():
    m, plan = two_trades(gap=False)
    res, _, tr = B.multi_account(m, plan, E.BOT, 0, len(m))
    long_pnl = 2000.2 * 0.99 - 2000.2                         # stopped at 1% below its ask entry
    short_close = 2000.0 - (1950.0 + 0.2)                     # the short at bar 30's close, on the ask
    peak = E.ACCOUNT + long_pnl + short_close                 # the highest equity at a close: after bar 30
    trough = E.ACCOUNT + long_pnl + (2000.0 - (2000.0 + 0.2)) # bar 30: the long at its stop, the short at its worst
    assert res.max_dd == pytest.approx((peak - trough) / peak, rel=1e-6)


def test_an_exit_at_the_open_is_booked_before_a_trade_opens_on_that_bar():
    m, plan = two_trades(gap=True)
    for sizing in (E.BOT, E.Sizing("risk", rf=0.02)):         # 2%: the 1% stop on $2,000 buys one 0.01 lot
        r1, d1, _ = F._bar_account(E, m, plan, sizing, 0, len(m))
        r2, d2, _ = B.multi_account(m, plan, sizing, 0, len(m))
        assert len(r1.trades_pnl) == 2 and E.WHY_NAMES[int(E.run_path(m, plan, 0, len(m)).why[0])] == "gap stop"
        assert r2.final == pytest.approx(r1.final, abs=1e-9)
        assert r2.max_dd == pytest.approx(r1.max_dd, abs=1e-12)
        assert np.allclose(d1.to_numpy(), d2.to_numpy(), equal_nan=True)


def test_an_exit_at_the_open_keeps_the_other_open_trades():
    """A short from bar 5 stays open to the end; a long from bar 10 is gapped through its stop at bar 60's open, where
    a new short opens. Each trade is 1 unit; the price ends at 1850."""
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 02:00"), MIN, dtype=np.int64)
    p = np.full(len(t), 2000.0)
    m1 = bars(t, p, p.copy(), p.copy(), p.copy(), 0.2)
    m1["o"][60:] = m1["h"][60:] = 1900.0
    m1["l"][60:] = m1["c"][60:] = 1850.0
    m1["o"][61:] = m1["h"][61:] = 1850.0
    m = E.Market("XAUUSDm", m1)
    plan = E.make_plan(m, [int(t[5]), int(t[10]), int(t[60])], want=[-1, 1, -1], slf=0.01)
    res, _, tr = B.multi_account(m, plan, E.BOT, 0, len(m))
    expected = [2000.0 - (1850.0 + 0.2), 1900.0 - 2000.2, 1900.0 - (1850.0 + 0.2)]
    assert tr["pnl"].tolist() == pytest.approx(expected)
    assert res.final == pytest.approx(E.ACCOUNT + sum(expected))


def test_the_unit_rule_steps_up_between_overlapping_trades():
    """$2,400: a long from bar 5 takes its $100 target in a gap at bar 15 (+149.80), lifting the balance over $2,500;
    a long from bar 10 stays open; a third long at bar 30 is sized from the new balance: 2 units."""
    t = np.arange(utc("2024-03-04 00:00"), utc("2024-03-04 01:00"), MIN, dtype=np.int64)
    p = np.full(len(t), 2000.0)
    m1 = bars(t, p, p.copy(), p.copy(), p.copy(), 0.2)
    for name in ("o", "h", "l", "c"):
        m1[name][15:] = 2150.0
    m = E.Market("XAUUSDm", m1)
    plan = E.merge_plans(m, [dict(dt=[int(t[5])], want=1, tp=100.0), dict(dt=[int(t[10]), int(t[30])], want=1)])
    saved = E.ACCOUNT
    E.ACCOUNT = 2400.0
    try:
        res, _, tr = B.multi_account(m, plan, E.BOT, 0, len(m))
    finally:
        E.ACCOUNT = saved
    assert tr["lots"].tolist() == pytest.approx([0.01, 0.01, 0.02])
    assert tr["pnl"].tolist() == pytest.approx([2150.0 - 2000.2, 2150.0 - 2000.2, 2 * (2150.0 - 2150.2)])
    assert res.final == pytest.approx(2400.0 + 2 * (2150.0 - 2000.2) + 2 * (2150.0 - 2150.2))


def test_btc_range_breakout_keeps_the_spring_forward_sunday():
    """On Sun 10 Mar 2024 the server clock skips 09:00 - 09:59 (New York 02:00 - 02:59): the orders go in at the first
    time that exists, 10:00 server = 07:00 UTC."""
    m1 = minute_bars("2024-03-10 00:00", "2024-03-10 20:00", 60000.0, 10.0)
    m1["h"][at(m1, "2024-03-10 03:00")] = 60500.0
    m1["l"][at(m1, "2024-03-10 04:00")] = 59500.0
    m = E.Market("BTCUSDm", m1)
    p = B.range_breakout(m, (5, 0), (9, 0), (20, 0), "factor", 1.0, 1.0, weekdays_only=False).plan
    k = np.flatnonzero(np.isfinite(p.f["bstop"]))
    assert len(k) == 1 and p.dt[k[0]] == utc("2024-03-10 07:00")
    assert p.f["bstop"][k[0]] == 60500.0 and p.f["sstop"][k[0]] == 59500.0
    assert utc("2024-03-10 17:00") in p.dt[p.xl]                 # 20:00 server time in US summer time


def test_turnaround_tuesday_reads_the_price_at_its_open_time_not_a_minute_later():
    """At 01:05 server time the bid is above the average, by the close of that minute it is below: no trade."""
    days = [d for d in range(utc("2024-01-02"), utc("2024-02-14"), DAY) if ((d // DAY) + 3) % 7 < 5]
    t = np.asarray([d - 2 * 3600 + k * MIN for d in days for k in range(0, 24 * 60, 5)], np.int64)
    o = np.full(len(t), 100.0)
    c = o.copy()
    j = int(np.flatnonzero(t == utc("2024-02-12") - 2 * 3600 + 65 * MIN)[0])   # Monday 12 Feb, 01:05 server
    o[j], c[j] = 100.4, 98.0
    m = index(bars(t, o, np.maximum(o, c), np.minimum(o, c), c, 2.0))
    p = B.turnaround_tuesday(m, 25).plan
    assert p.want[p.dt == t[j]][0] == 0


# ───────────────────────────── Go Long and Turnaround Tuesday ─────────────────────────────

def test_go_long_buys_at_0105_and_sells_at_2255_server_time():
    m = index(minute_bars("2024-01-15 01:00", "2024-01-17 00:00", 38000.0, 2.0))
    p = B.go_long(m).plan
    buys = p.dt[p.want == 1]
    sells = p.dt[p.xl]
    # winter, GMT+2: 01:05 server = 23:05 UTC the evening before; 22:55 server = 20:55 UTC
    # the data run from 03:00 server time on 15 Jan (more than 90 minutes after that day's 01:05: no entry) to 02:00
    # on 17 Jan (that day's exit is past the data, so the window's end closes it)
    assert list(buys) == [utc("2024-01-15 23:05"), utc("2024-01-16 23:05")]
    assert list(sells) == [utc("2024-01-16 20:55")]


def test_go_long_waits_for_a_late_reopen_on_the_same_session():
    """US summer time (GMT+3): 01:05 server = 22:05 UTC. Exness reopens the index at 22:30 UTC (18:30 New York):
    the buy is the first quote then; the close stays at 22:55 server = 19:55 UTC."""
    m1 = minute_bars("2024-06-10 12:00", "2024-06-11 21:00", 39000.0, 2.0)
    keep = (m1["t"] < utc("2024-06-10 21:00")) | (m1["t"] >= utc("2024-06-10 22:30"))
    m = index({k: v[keep] for k, v in m1.items()})
    p = B.go_long(m).plan
    assert list(p.dt[p.want == 1]) == [utc("2024-06-10 22:30")]
    assert list(p.dt[p.xl]) == [utc("2024-06-11 19:55")]
    assert (p.f["expo"][p.want == 1] == 1.0).all()


def test_turnaround_tuesday_buys_on_monday_only_below_the_average():
    """Thirty weekdays at 100, then a Friday close of 90: on the next Monday the price is below the SMA(25)."""
    days = [d for d in range(utc("2024-01-02"), utc("2024-02-20"), DAY) if ((d // DAY) + 3) % 7 < 5]
    t, c = [], []
    for d in days:
        srv0 = d - 2 * 3600                                   # 00:00 server time on that day, in UTC (GMT+2)
        for k in range(0, 24 * 60, 5):
            t.append(srv0 + k * MIN)
            c.append(100.0)
    t = np.asarray(t, np.int64)
    c = np.asarray(c)
    fri = utc("2024-02-09") - 2 * 3600                        # Friday 9 Feb, server day
    c[(t >= fri)] = 90.0
    mon2 = utc("2024-02-19") - 2 * 3600                       # Monday 19 Feb: back above the average
    c[(t >= mon2)] = 120.0
    m = index(bars(t, c, c, c, c, 2.0))
    p = B.turnaround_tuesday(m, 25).plan
    mon = utc("2024-02-12") - 2 * 3600 + 65 * MIN            # Monday 12 Feb 01:05 server
    k = int(np.flatnonzero(p.dt == mon)[0])
    assert p.want[k] == 1 and p.f["expo"][k] == 0.5
    assert p.want[p.dt == mon2 + 65 * MIN][0] == 0
    assert (utc("2024-02-13") - 2 * 3600 + (22 * 60 + 55) * MIN) in p.dt[p.xl]   # Tuesday 22:55 server
    wd = ((p.dt[p.want == 1] + 2 * 3600) // DAY + 3) % 7
    assert (wd == 0).all()                                    # only Mondays (server days)


# ───────────────────────────── the scenario and the reference ─────────────────────────────

def test_the_spread_scenario_changes_only_the_spread():
    m = E.Market("BTCUSDm", btc_like(days=3))
    s = B.with_spread(m, 0.02)
    assert np.allclose(s.sp, m.c * 0.0002)
    for name in ("t", "o", "h", "l", "c"):
        assert (getattr(s, name) == getattr(m, name)).all()
    assert s.k == m.k and s.symbol == m.symbol and s._bars == {} and s.sp is not m.sp


def test_buy_and_hold_holds_one_position_per_window():
    m = index(minute_bars("2025-11-01 00:00", "2025-12-01 00:00", 40000.0, 2.0))
    a, z = int(np.searchsorted(m.t, utc("2025-11-13"))), len(m)
    path = E.run_path(m, B.buy_hold(m).plan, a, z)
    assert len(path) == 1 and path.dir[0] == 1 and path.eix[0] == a and path.xix[0] == z - 1


# ───────────────────────────── no look-ahead ─────────────────────────────

def gold_like(days=60, seed=5, start="2024-03-03"):
    rng = np.random.default_rng(seed)
    t0 = utc(start)
    t = t0 + 60 * np.arange(days * 1440, dtype=np.int64)
    minute = (t % DAY) // 60
    weekday = ((t // DAY) + 4) % 7                            # 0 = Sunday
    in_break = (minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)
    keep = ~in_break & (weekday != 6)
    keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
    t = t[keep]
    n = len(t)
    c = 2000.0 + np.cumsum(rng.normal(0.0, 0.6, n))
    o = np.concatenate(([2000.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.3, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.3, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": 0.16 + 0.1 * rng.random(n),
            "n": rng.integers(5, 60, n)}


def btc_like(days=60, seed=11, start="2024-03-03"):
    rng = np.random.default_rng(seed)
    t = utc(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    c = 60000.0 + np.cumsum(rng.normal(0.0, 25.0, n))
    o = np.concatenate(([60000.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 12.0, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 12.0, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": 15.0 + 5.0 * rng.random(n),
            "n": rng.integers(5, 60, n)}


def futures(m1, n_cut, seed=99):
    """The history cut at n_cut, and another future after it (every price from n_cut on jumps by half)."""
    rng = np.random.default_rng(seed)
    cut = {k: v[:n_cut] for k, v in m1.items()}
    other = {k: v.copy() for k, v in m1.items()}
    k = len(other["c"]) - n_cut
    path = 1.5 * (1.0 + 0.04 * rng.normal(size=k).cumsum() / math.sqrt(k))
    for name in ("o", "h", "l", "c"):
        other[name] = other[name].astype(np.float64)
        other[name][n_cut:] *= path
    other["h"][n_cut:] = np.maximum.reduce([other["h"][n_cut:], other["o"][n_cut:], other["c"][n_cut:]])
    other["l"][n_cut:] = np.minimum.reduce([other["l"][n_cut:], other["o"][n_cut:], other["c"][n_cut:]])
    other["spread_mean"][n_cut:] *= 1.8
    return (("cut", cut), ("other future", other))


RULES = {
    "range breakout, gold": ("XAUUSDm", lambda m: B.range_breakout(m, (3, 5), (6, 5), (18, 55), "percent", 1.0, 1.0)),
    "range breakout, BTC": ("BTCUSDm", lambda m: B.range_breakout(m, (5, 0), (9, 0), (20, 0), "factor", 1.0, 1.0,
                                                                   weekdays_only=False)),
    "ATR breakout": ("XAUUSDm", lambda m: B.atr_breakout(m, period=50)),
    "go long": ("US30m", lambda m: B.go_long(m)),
    "turnaround tuesday": ("US30m", lambda m: B.turnaround_tuesday(m, 9)),
}


def spiky(m1, every_h=53, size=25.0):
    """gold_like with a strong one-hour ramp every ``every_h`` hours (and the drop back after it): ATR signals both ways."""
    out = {k: v.copy() for k, v in m1.items()}
    hour = (out["t"] - out["t"][0]) // 3600
    for k in range(5, int(hour.max()), every_h):
        idx = np.flatnonzero(hour == k)
        if len(idx) < 30:
            continue
        ramp = np.linspace(0.0, size, len(idx))
        for name in ("o", "h", "l", "c"):
            out[name] = out[name].astype(np.float64)
            out[name][idx] += ramp
    return out


def _market(symbol, m1):
    return index(m1, symbol) if symbol in B.INDEX_SPECS else E.Market(symbol, m1)


@pytest.mark.parametrize("rule", sorted(RULES))
def test_no_rule_reads_the_future(rule):
    symbol, build = RULES[rule]
    m1 = btc_like() if symbol == "BTCUSDm" else spiky(gold_like()) if rule == "ATR breakout" else gold_like()
    full = build(_market(symbol, m1)).plan
    for frac in (0.37, 0.71):
        n_cut = int(len(m1["t"]) * frac)
        T = int(m1["t"][n_cut]) - 3 * MIN                    # an intraday order needs a quote within 3 minutes
        for name, h in futures(m1, n_cut):
            other = build(_market(symbol, h)).plan
            a, b = full.dt < T, other.dt < T
            assert a.sum() > 0, f"{rule}: no decision before T, the check would be empty"
            assert (full.dt[a] == other.dt[b]).all(), f"{rule}, {name}: decision times differ before T"
            assert (full.want[a] == other.want[b]).all() and (full.xl[a] == other.xl[b]).all()
            for f in ("bstop", "sstop", "bsl", "ssl", "slf", "tpr", "expo"):
                assert np.array_equal(full.f[f][a], other.f[f][b], equal_nan=True), f"{rule}, {name}: {f}"
