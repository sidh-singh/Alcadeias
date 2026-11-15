"""
The study of strategies from the literature (``backtesting/research/external.py``).

* The simulator on hand-made bars: fills at the ask and the bid, the stop before the target, gaps, stop-entry
  orders, pyramid adds, the break-even move, the pause after a loss, one position at a time.
* The account: the bot's unit rule, risk and exposure sizing rounded down (zero-size trades), the wipe-out,
  the drawdown from the running peak, the target-position book.
* The strategy rules on small examples: day bars, the Donchian model, the Turtle filter, Supertrend,
  session clocks.
* No look-ahead: for every strategy and parameter set, for the bot's filters and for V3-lite, the decisions
  and the trades up to a time T are the same when the history after T is removed or replaced.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as E

DAY = 86400
T0 = store.to_ms("2024-03-04") // 1000          # a Monday, 00:00 UTC


# ───────────────────────────── helpers ─────────────────────────────

def market(o, h, l, c, spread=0.2, symbol="XAUUSDm", t0=T0, step=60):
    n = len(c)
    f = lambda x: np.asarray(x, np.float64)
    sp = np.full(n, float(spread)) if np.isscalar(spread) else f(spread)
    return E.Market(symbol, {"t": t0 + step * np.arange(n, dtype=np.int64), "o": f(o), "h": f(h), "l": f(l), "c": f(c),
                             "spread_mean": sp, "n": np.ones(n, np.int64)})


def flat(n, price=100.0):
    return [price] * n, [price] * n, [price] * n, [price] * n


def plan(m, rows, **kw):
    """rows: dicts with 'bar' (the decision is executed at the open of that bar) and plan fields."""
    fields = set()
    for r in rows:
        fields |= set(r) - {"bar"}
    cols = {k: [r.get(k, {"want": 0, "xl": False, "xs": False, "pmax": 1}.get(k, np.nan)) for r in rows] for k in fields}
    return E.make_plan(m, [int(m.t[r["bar"]]) for r in rows], **cols, **kw)


def trades(m, p, start=0, end=None):
    path = E.run_path(m, p, start, len(m) if end is None else end)
    return [dict(dir=int(path.dir[i]), eix=int(path.eix[i]), epx=round(float(path.epx[i]), 6), xix=int(path.xix[i]),
                 xpx=round(float(path.xpx[i]), 6), why=E.WHY_NAMES[int(path.why[i])], legs=int(path.nleg[i]))
            for i in range(len(path))], path


def gold_like(days=420, seed=5, start="2024-03-03"):
    """Gold's sessions: Sunday from 22:05 UTC, a daily break 20:57-22:02, Friday until 20:57, nothing on Saturday."""
    rng = np.random.default_rng(seed)
    t0 = store.to_ms(start) // 1000
    t = t0 + 60 * np.arange(days * 1440, dtype=np.int64)
    minute = (t % DAY) // 60
    weekday = ((t // DAY) + 4) % 7                          # 0 = Sunday
    in_break = (minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)
    keep = ~in_break & (weekday != 6)
    keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
    t = t[keep]
    n = len(t)
    vol = 0.35 * np.exp(0.6 * np.sin(np.arange(n) / 4000.0) + 0.3 * np.sin(np.arange(n) / 611.0))
    drift = 0.004 * np.sin(np.arange(n) / 60000.0)
    c = 2000.0 + np.cumsum(rng.normal(0.0, 1.0, n) * vol + drift)
    o = np.concatenate(([2000.0], c[:-1])) + rng.normal(0.0, 0.02, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5, n)) * vol
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5, n)) * vol
    sp = 0.16 + 0.1 * rng.random(n)
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": sp, "n": rng.integers(5, 60, n)}


def btc_like(days=420, seed=11, start="2024-03-03"):
    """Around the clock, with one hole of six hours."""
    rng = np.random.default_rng(seed)
    t0 = store.to_ms(start) // 1000
    t = t0 + 60 * np.arange(days * 1440, dtype=np.int64)
    t = t[~((t >= t0 + 200 * DAY) & (t < t0 + 200 * DAY + 6 * 3600))]
    n = len(t)
    vol = 25.0 * np.exp(0.6 * np.sin(np.arange(n) / 9000.0))
    drift = 0.3 * np.sin(np.arange(n) / 90000.0)
    c = 60000.0 + np.cumsum(rng.normal(0.0, 1.0, n) * vol + drift)
    o = np.concatenate(([60000.0], c[:-1])) + rng.normal(0.0, 1.0, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5, n)) * vol
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5, n)) * vol
    sp = 15.0 + 5.0 * rng.random(n)
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": sp, "n": rng.integers(5, 60, n)}


def cut(m1, n):
    return {k: v[:n] for k, v in m1.items()}


def shocked(m1, n, factor=1.5, seed=99):
    """The same past, another future: from bar n on every price jumps by ``factor`` and is re-drawn, the spread and
    the tick counts change. A jump this size flips any signal, level or bound that reads even one bar too far."""
    rng = np.random.default_rng(seed)
    out = {k: v.copy() for k, v in m1.items()}
    k = len(out["c"]) - n
    path = factor * (1.0 + 0.04 * rng.normal(size=k).cumsum() / math.sqrt(k))
    for name in ("o", "h", "l", "c"):
        out[name] = out[name].astype(np.float64)
        out[name][n:] = out[name][n:] * path
    wide = 0.002 * out["c"][n:]
    out["h"][n:] = np.maximum.reduce([out["h"][n:], out["o"][n:], out["c"][n:]]) + wide
    out["l"][n:] = np.minimum.reduce([out["l"][n:], out["o"][n:], out["c"][n:]]) - wide
    out["spread_mean"][n:] = out["spread_mean"][n:] * 1.8
    out["n"][n:] = out["n"][n:][::-1] * 3
    return out


def futures(h, n_cut):
    """The history cut at n_cut, and two other futures after it (a jump up, a crash)."""
    return (("cut", cut(h, n_cut)), ("jump up", shocked(h, n_cut, 1.5)), ("crash", shocked(h, n_cut, 0.6, seed=7)))


# ───────────────────────────── the simulator ─────────────────────────────

def test_a_buy_fills_at_the_ask_a_sell_at_the_bid_and_a_round_trip_costs_the_spread():
    m = market(*flat(6), spread=0.2)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1), dict(bar=3, xl=True)]))
    assert tr == [dict(dir=1, eix=1, epx=100.2, xix=3, xpx=100.0, why="signal", legs=1)]
    tr, _ = trades(m, plan(m, [dict(bar=1, want=-1), dict(bar=3, xs=True)]))
    assert tr == [dict(dir=-1, eix=1, epx=100.0, xix=3, xpx=100.2, why="signal", legs=1)]
    res = E.account(m, E.run_path(m, plan(m, [dict(bar=1, want=1), dict(bar=3, xl=True)]), 0, len(m)), E.BOT,
                    np.asarray([0, len(m)]))
    assert res.final == pytest.approx(E.ACCOUNT - 0.2)            # 0.01 lot of gold: 1 USD per 1.00


def test_the_stop_is_taken_first_when_one_bar_reaches_both():
    o, h, l, c = flat(6)
    h[2], l[2] = 102.0, 98.0
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1, sl=1.0, tp=1.0)]))
    assert tr[0]["why"] == "stop" and tr[0]["xix"] == 2 and tr[0]["xpx"] == pytest.approx(99.2)


def test_a_gap_through_the_stop_is_filled_at_the_open():
    o, h, l, c = flat(6)
    o[2], h[2], l[2], c[2] = 98.0, 98.5, 97.5, 98.0
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1, sl=1.0)]))
    assert tr[0]["why"] == "gap stop" and tr[0]["xpx"] == 98.0


def test_a_short_is_stopped_and_closed_on_the_ask():
    o, h, l, c = flat(6)
    h[2] = 100.85                                            # ask high 101.05: beyond a stop at 101
    m = market(o, h, l, c, spread=0.2)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=-1, sl=1.0)]))
    assert tr[0]["dir"] == -1 and tr[0]["epx"] == 100.0 and tr[0]["why"] == "stop" and tr[0]["xpx"] == pytest.approx(101.0)


def test_a_target_is_reached_on_the_favourable_extreme_after_the_other_one():
    o, h, l, c = flat(6)
    h[3] = 101.5
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1, sl=1.0, tp=1.0)]))
    assert tr[0]["why"] == "target" and tr[0]["xix"] == 3 and tr[0]["xpx"] == pytest.approx(101.2)


def test_a_stop_entry_order_fills_at_its_level_or_at_the_open_and_can_be_stopped_in_its_own_bar():
    o, h, l, c = flat(8)
    h[2] = 101.5                                             # ask high 101.7 reaches the buy stop at 101
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, bstop=101.0, bsl=99.0)], orders=True))
    assert tr[0]["eix"] == 2 and tr[0]["epx"] == 101.0 and tr[0]["why"] == "end"
    l[2] = 98.5                                              # the same bar also reaches the stop at 99
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, bstop=101.0, bsl=99.0)], orders=True))
    assert tr[0]["eix"] == 2 and tr[0]["xix"] == 2 and tr[0]["why"] == "stop" and tr[0]["xpx"] == 99.0
    o, h, l, c = flat(8)
    o[2], h[2], l[2], c[2] = 102.0, 102.5, 101.8, 102.0      # opens above the order: filled at the open ask
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, bstop=101.0)], orders=True))
    assert tr[0]["epx"] == pytest.approx(102.2)


def test_one_fill_cancels_the_other_order_and_an_order_lasts_until_the_next_decision():
    o, h, l, c = flat(10)
    h[2] = 101.5
    l[5] = 98.0
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, bstop=101.0, sstop=99.0, bsl=99.5, ssl=100.5), dict(bar=4, xl=True)],
                           orders=True))
    assert [(x["dir"], x["eix"], x["xix"]) for x in tr] == [(1, 2, 4)]          # the sell stop died with the fill
    o, h, l, c = flat(10)
    h[6] = 101.5
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, bstop=101.0), dict(bar=4)], orders=True))
    assert tr == []                                           # replaced by the next decision before price got there


def test_the_pyramid_adds_in_favour_and_moves_every_stop_to_its_distance_from_the_last_fill():
    o, h, l, c = flat(8)
    h[2] = 101.5                                             # ask high 101.7: adds at 100.7, 101.2, 101.7
    l[4] = 99.6                                              # below the moved stop 101.7 - 2 = 99.7
    m = market(o, h, l, c)
    tr, path = trades(m, plan(m, [dict(bar=1, want=1, sl=2.0, pstep=0.5, pmax=4)]))
    assert tr[0]["legs"] == 4 and tr[0]["why"] == "stop" and tr[0]["xix"] == 4
    assert list(np.round(path.lepx, 6)) == [100.2, 100.7, 101.2, 101.7]
    assert tr[0]["xpx"] == pytest.approx(99.7)


def test_the_stop_moves_to_break_even_after_the_bar_that_reached_the_trigger():
    o, h, l, c = flat(8)
    h[2] = 101.8                                             # entry 100.2, R = 1: break-even trigger at 101.7
    for i in range(3, 8):
        o[i] = h[i] = l[i] = c[i] = 101.0
    l[2] = 100.3                                             # above the old stop 99.2: the trigger bar is not stopped
    l[4] = 100.0
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1, sl=1.0, tpr=2.5, ber=1.5)]))
    assert tr[0]["why"] == "stop" and tr[0]["xix"] == 4 and tr[0]["xpx"] == pytest.approx(100.2)
    l[2] = 100.1                                             # the stop moves only after the bar: 100.1 is above 99.2
    m = market(o, h, l, c)
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1, sl=1.0, tpr=2.5, ber=1.5)]))
    assert tr[0]["xix"] == 4


def test_a_pause_after_a_loss_blocks_entries_for_its_length_only():
    o, h, l, c = flat(200)
    l[2] = 98.0
    m = market(o, h, l, c)
    p = plan(m, [dict(bar=1, want=1, sl=1.0), dict(bar=20, want=1), dict(bar=80, want=1)], pause_loss_s=3600.0,
             pause_win_s=0.0)
    tr, _ = trades(m, p)
    assert [x["eix"] for x in tr] == [1, 80]


def test_one_position_at_a_time_and_no_same_side_reentry_on_the_bar_that_closed_it():
    m = market(*flat(10))
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1), dict(bar=2, want=1), dict(bar=3, want=1, xl=True),
                               dict(bar=5, want=-1, xl=True)]))
    assert [(x["dir"], x["eix"], x["xix"]) for x in tr] == [(1, 1, 3), (-1, 5, 9)]


def test_an_entry_needs_a_quote_soon_after_an_intraday_decision():
    m = market(*flat(6), step=600)                            # ten minutes between bars
    p = E.make_plan(m, [int(m.t[1]) - 300], want=[1], live_s=180.0)
    assert trades(m, p)[0] == []
    p = E.make_plan(m, [int(m.t[1]) - 120], want=[1], live_s=180.0)
    assert len(trades(m, p)[0]) == 1


def test_the_end_of_a_period_closes_at_the_last_close_and_nothing_starts_before_its_start():
    m = market(*flat(10))
    tr, _ = trades(m, plan(m, [dict(bar=1, want=1), dict(bar=6, want=-1, xl=True)]), start=3, end=8)
    assert tr == [dict(dir=-1, eix=6, epx=100.0, xix=7, xpx=100.2, why="end", legs=1)]


# ───────────────────────────── the account ─────────────────────────────

def _path(m, rows):
    return E.run_path(m, plan(m, rows), 0, len(m))


def test_the_bot_unit_rule_steps_up_with_the_balance():
    o, h, l, c = flat(20)
    for i in range(3, 20):
        o[i] = h[i] = l[i] = c[i] = 700.0                       # +599.8 a unit on the first trade
    m = market(o, h, l, c)
    res = E.account(m, _path(m, [dict(bar=1, want=1), dict(bar=4, xl=True), dict(bar=5, want=1), dict(bar=8, xl=True)]),
                    E.BOT, np.asarray([0, len(m)]))
    assert res.trades_pnl[0] == pytest.approx(599.8)
    assert res.trades_pnl[1] == pytest.approx(-0.4)                 # balance 2,599.8 -> unit 2 pays the spread twice


def test_risk_sizing_rounds_down_and_a_trade_it_cannot_size_is_taken_at_zero_size():
    m = market(*flat(20))
    rows = [dict(bar=1, want=1, sl=30.0), dict(bar=3, xl=True), dict(bar=5, want=1, sl=9.0), dict(bar=7, xl=True)]
    res = E.account(m, _path(m, rows), E.Sizing("risk", rf=0.01), np.asarray([0, len(m)]))
    assert res.skipped == 1 and len(res.trades_pnl) == 1
    assert res.trades_pnl[0] == pytest.approx(-0.2 * 2)            # $20 / $9 -> 2 units
    res = E.account(m, _path(m, [dict(bar=1, want=1, expo=2.0), dict(bar=3, xl=True)]),
                    E.Sizing("expo", cap_lev=1.0), np.asarray([0, len(m)]))
    assert res.trades_pnl[0] == pytest.approx(-0.2 * 19)          # 2x capped at 1x: $2,000 / $100.2 -> 19 units


def test_the_turtle_brake_sizes_on_a_smaller_notional_after_a_drawdown():
    o, h, l, c = flat(30)
    for i in range(3, 30):
        o[i] = h[i] = l[i] = c[i] = 80.0
    m = market(o, h, l, c)
    rows = [dict(bar=1, want=1, rk=1.0), dict(bar=4, xl=True), dict(bar=5, want=1, rk=1.0), dict(bar=7, xl=True)]
    plain = E.account(m, _path(m, rows), E.Sizing("risk", rf=0.01), np.asarray([0, len(m)]))
    brake = E.account(m, _path(m, rows), E.Sizing("risk", rf=0.01, brake=True), np.asarray([0, len(m)]))
    # trade 1: 1% of $2,000 per 1.00 of risk = 20 units, -20.2 each = -$404 (a 20.2% drawdown from the year's start)
    assert plain.trades_pnl[0] == brake.trades_pnl[0] == pytest.approx(-404.0)
    # trade 2: plain sizes on $1,596 (15 units); the brake on $2,000 x 0.8^2 = $1,280 (12 units)
    assert plain.trades_pnl[1] == pytest.approx(-0.2 * 15)
    assert brake.trades_pnl[1] == pytest.approx(-0.2 * 12)


def test_the_account_is_wiped_at_zero_equity_and_trades_after_it_are_not_taken():
    o, h, l, c = flat(30)
    l[3] = -5000.0                                              # an impossible spike: equity below zero
    m = market(o, h, l, c)
    res = E.account(m, _path(m, [dict(bar=1, want=1), dict(bar=5, xl=True), dict(bar=8, want=1), dict(bar=10, xl=True)]),
                    E.Sizing("expo"), np.asarray([0, len(m)]))
    assert res.trades_pnl.size == 0                             # exposure sizing without an exposure: nothing sized
    res = E.account(m, _path(m, [dict(bar=1, want=1), dict(bar=5, xl=True), dict(bar=8, want=1), dict(bar=10, xl=True)]),
                    E.BOT, np.asarray([0, len(m)]))
    assert res.wiped and res.final == 0.0 and len(res.trades_pnl) == 1 and res.trades_pnl[0] == -E.ACCOUNT
    assert res.max_dd == 1.0


def test_drawdown_is_from_the_running_peak_with_troughs_at_the_worst_price_of_a_bar():
    o, h, l, c = flat(20)
    for i in range(3, 20):
        o[i] = h[i] = l[i] = c[i] = 600.0
    l[5] = 300.0                                                # the trough inside a bar: 300
    m = market(o, h, l, c)
    res = E.account(m, _path(m, [dict(bar=1, want=1), dict(bar=10, xl=True)]), E.BOT, np.asarray([0, len(m)]))
    peak = E.ACCOUNT + (600.0 - 100.2)
    trough = E.ACCOUNT + (300.0 - 100.2)
    assert res.max_dd == pytest.approx((peak - trough) / peak)


def test_quarter_blocks_split_the_equity_of_an_open_position_at_the_block_edge():
    o, h, l, c = flat(20)
    for i in range(6, 20):
        o[i] = h[i] = l[i] = c[i] = 110.0
    m = market(o, h, l, c)
    res = E.account(m, _path(m, [dict(bar=1, want=1), dict(bar=12, xl=True)]), E.BOT, np.asarray([0, 8, len(m)]))
    assert list(np.round(res.blocks, 4)) == [E.ACCOUNT, round(E.ACCOUNT + 9.8, 4), round(E.ACCOUNT + 9.8, 4)]


def test_the_target_book_trades_only_what_changes_and_pays_the_spread_on_it():
    m = market(*flat(20))
    tp = E.TargetPlan(dt=m.t[[1, 4, 8]], dx=np.asarray([1, 4, 8]), w=np.asarray([1.0, 1.1, 0.0]),
                      force=np.asarray([True, False, True]), active=np.ones(3, np.bool_), thr=0.2)
    res = E.run_target(m, tp, 0, len(m), np.asarray([0, len(m)]))
    # $2,000 at 100 -> 20 units bought at 100.2; 1.1 is within 20% of the position: kept; then closed at 100
    assert res.orders == 2 and len(res.trades_pnl) == 1 and res.trades_pnl[0] == pytest.approx(-0.2 * 20)
    assert res.final == pytest.approx(E.ACCOUNT - 4.0)
    tp = E.TargetPlan(dt=m.t[[1, 4]], dx=np.asarray([1, 4]), w=np.asarray([1.0, -0.5]), force=np.ones(2, np.bool_),
                      active=np.ones(2, np.bool_), thr=0.0)
    res = E.run_target(m, tp, 0, len(m), np.asarray([0, len(m)]))
    # reversal: the long round trip ends at the flip, the short one at the end of the period
    assert len(res.trades_pnl) == 2 and list(res.trades_dir) == [1, -1]
    assert res.trades_pnl.sum() == pytest.approx(res.final - E.ACCOUNT)


# ───────────────────────────── the rules on small examples ─────────────────────────────

def test_short_days_are_merged_into_the_next_full_day():
    m = E.Market("XAUUSDm", gold_like(days=10))
    d1 = m.bars("D1")
    dow = ((d1.t // DAY) + 3) % 7                              # 0 = Monday
    assert 6 in set(dow.tolist())                              # a bar that opens on Sunday ...
    assert set(((d1.tc - 1) // DAY + 3) % 7) <= {0, 1, 2, 3, 4}     # ... closes with Monday; none ends on a weekend
    assert (d1.ex <= len(m)).all() and (m.t[np.minimum(d1.ex, len(m) - 1)] >= np.where(d1.ex < len(m), d1.tc, 0)).all()


def test_donchian_model_enters_on_the_highest_close_and_ratchets_its_midline_stop():
    C = np.asarray([10, 11, 12, 13, 14, 12.4, 12.9, 11.5, 15.0], float)
    up, dn = E.roll_max(C, 3), E.roll_min(C, 3)
    pos = E._donchian_model(C, up, dn, (up + dn) / 2.0, False)
    # enters at bar 2 (12 = highest of 3); midline 11, 12, 13 -> stop 13 at bar 4; 12.4 <= 13 exits at bar 5
    assert list(pos) == [0, 0, 1, 1, 1, 0, 0, 0, 1]


def test_turtle_system_one_skips_the_breakout_after_a_winning_one():
    nb = 80
    O = np.full(nb, 100.0)
    # a breakout at bar 30 that runs to 112, holds, and falls through the 10-day low at 111 on bar 50: a winner
    O[30:40] = np.linspace(102, 112, 10)
    O[40:51] = 112.0
    O[51:] = 106.0
    H, L = O + 1.0, O - 1.0
    L[50] = 105.0
    N = np.full(nb, 1.0)
    hi20, lo20 = E.roll_max(H, 20), E.roll_min(L, 20)
    hi10, lo10 = E.roll_max(H, 10), E.roll_min(L, 10)
    use20 = E._turtle_s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, 0.01)
    assert use20[29] and not use20[30] and not use20[45]       # no breakout is taken while the last one is open
    assert not use20[50] and not use20[60]                     # it won: the next one needs the 55-day failsafe
    # the same with a fall through the 2N stop instead: a loser, so the next 20-day breakout is taken
    O2 = np.full(nb, 100.0)
    O2[30] = 101.5
    O2[31:] = 99.0
    H2, L2 = O2 + 1.0, O2 - 1.0
    use20 = E._turtle_s1_use20(O2, H2, L2, N, E.roll_max(H2, 20), E.roll_min(L2, 20), E.roll_min(L2, 10),
                               E.roll_max(H2, 10), 0.01)
    assert not use20[30] and use20[31]


def test_supertrend_flips_on_a_close_through_the_opposite_line():
    C = np.concatenate([np.linspace(100, 120, 30), np.linspace(120, 90, 30)])
    H, L = C + 0.5, C - 0.5
    tr = E._supertrend(H, L, C, E.wilder_atr(H, L, C, 10), 3.0)
    assert tr[9] == 1 and tr[29] == 1 and tr[-1] == -1
    flip = int(np.flatnonzero(tr == -1)[0])
    assert 30 < flip < 45


def test_session_clocks_follow_new_york_daylight_saving():
    days = 400
    m = E.Market("XAUUSDm", gold_like(days=days))
    s = E.sessions(m, "comex")
    t = pd.to_datetime(s.start, unit="s", utc=True)
    summer = t.month == 7
    winter = t.month == 1
    assert set(t[summer].strftime("%H:%M")) == {"12:20"} and set(t[winter].strftime("%H:%M")) == {"13:20"}
    b = E.london_breakout(m, "server").plan
    starts = pd.to_datetime(b.dt[~b.xl], unit="s", utc=True)
    stops = pd.to_datetime(b.dt[b.xl], unit="s", utc=True)
    assert set(starts[starts.month == 7].strftime("%H:%M")) == {"05:00"}     # 08:00 server = 05:00 UTC in summer
    assert set(starts[starts.month == 1].strftime("%H:%M")) == {"06:00"}     # and 06:00 UTC in winter
    assert set(stops[stops.month == 7].strftime("%H:%M")) == {"18:00"}       # flat at 21:00 server
    u = E.london_breakout(m, "utc").plan
    assert set(pd.to_datetime(u.dt[~u.xl], unit="s", utc=True).strftime("%H:%M")) == {"08:00"}


def test_the_last_half_hour_trade_is_entered_at_13_00_and_closed_at_13_30_new_york():
    m = E.Market("XAUUSDm", gold_like(days=60))
    b = E.last_half_hour(m).plan
    ent = pd.to_datetime(b.dt[b.want != 0], unit="s", utc=True).tz_convert(E.NY)
    ext = pd.to_datetime(b.dt[b.xl], unit="s", utc=True).tz_convert(E.NY)
    assert set(ent.strftime("%H:%M")) == {"13:00"} and set(ext.strftime("%H:%M")) == {"13:30"}


# ───────────────────────────── no look-ahead ─────────────────────────────

@pytest.fixture(scope="module")
def histories():
    return {"XAUUSDm": gold_like(), "BTCUSDm": btc_like()}


def _cuts(m, plan: E.PathPlan, n_events: int = 8):
    """
    Where to cut the history: three odd places spread over its second half, and a minute or a few after
    ``n_events`` of the plan's own events (a change of the wanted side or of an exit, a new stop-entry order), where a
    rule that reads even one bar, or a few minutes, too far would see the missing or the different future.
    """
    n = len(m)
    out = [int(n * f) + k for f, k in ((0.62, 131), (0.79, 977), (0.93, 3))]
    w = plan.want
    prev = np.concatenate([[0], w[:-1]])
    late = plan.dt > m.t[n // 2]
    entries = late & (((w != 0) & (w != prev)) | np.isfinite(plan.f["bstop"]) | np.isfinite(plan.f["sstop"]))
    exits = late & (((w == 0) & (prev != 0)) | (np.diff(plan.xl.astype(np.int64), prepend=0) != 0)
                    | (np.diff(plan.xs.astype(np.int64), prepend=0) != 0))
    for ev, k_ev in ((entries, n_events - n_events // 3), (exits, n_events // 3)):
        idx = np.flatnonzero(ev)
        if len(idx) and k_ev:
            pick = idx[np.linspace(0, len(idx) - 1, min(k_ev, len(idx))).round().astype(np.int64)]
            offs = 60 + 37 * (np.arange(len(pick)) % 5)             # 60 .. 208 seconds after the decision
            out += [int(np.searchsorted(m.t, plan.dt[k] + o, side="left")) for k, o in zip(pick, offs)]
    return tuple(sorted({c for c in out if n // 4 < c < n - 2}))


def _same_plan(full: E.PathPlan, part: E.PathPlan, n_cut: int, what: str):
    a = full.dx < n_cut
    b = part.dx < n_cut
    assert a.sum() == b.sum(), what
    np.testing.assert_array_equal(full.dt[a], part.dt[b], err_msg=f"{what}: dt")
    for name in ("dx", "want", "xl", "xs", "pmax", "alw_l", "alw_s"):
        np.testing.assert_array_equal(getattr(full, name)[a], getattr(part, name)[b], err_msg=f"{what}: {name}")
    for name in E.FLOATS:
        np.testing.assert_array_equal(full.f[name][a], part.f[name][b], err_msg=f"{what}: {name}")
    if full.m_l is not None:
        np.testing.assert_array_equal(full.m_l[:n_cut], part.m_l[:n_cut], err_msg=f"{what}: m_l")
        np.testing.assert_array_equal(full.m_s[:n_cut], part.m_s[:n_cut], err_msg=f"{what}: m_s")


def _same_trades(m_full, p_full, m_part, p_part, n_cut, what, end_part=None, full_path=None):
    a = full_path if full_path is not None else E.run_path(m_full, p_full, 0, len(m_full))
    b = E.run_path(m_part, p_part, 0, len(m_part) if end_part is None else end_part)
    ka, kb = a.xix < n_cut - 1, b.xix < n_cut - 1
    assert ka.sum() == kb.sum(), f"{what}: {ka.sum()} trades against {kb.sum()}"
    for name in ("dir", "eix", "epx", "xix", "xpx", "why", "risk", "expo", "nleg"):
        np.testing.assert_array_equal(getattr(a, name)[ka], getattr(b, name)[kb], err_msg=f"{what}: {name}")
    return int(ka.sum())


def _same_target(m_full, t_full, m_part, t_part, n_cut, what):
    a, b = t_full.dx < n_cut, t_part.dx < n_cut
    assert a.sum() == b.sum(), what
    for name in ("dt", "dx", "w", "force", "active"):
        np.testing.assert_array_equal(getattr(t_full, name)[a], getattr(t_part, name)[b], err_msg=f"{what}: {name}")
    ra = E.run_target(m_full, t_full, 0, len(m_full), np.asarray([0, len(m_full)]))
    rb = E.run_target(m_part, t_part, 0, len(m_part), np.asarray([0, len(m_part)]))
    ka, kb = ra.trades_xix < n_cut - 1, rb.trades_xix < n_cut - 1
    np.testing.assert_allclose(ra.trades_pnl[ka], rb.trades_pnl[kb], rtol=0, atol=1e-9, err_msg=f"{what}: round trips")


CASES = [(sym, s.key, label) for sym in ("XAUUSDm", "BTCUSDm") for s in E.STRATEGIES for label in s.for_symbol(sym)]


@pytest.mark.parametrize("symbol,key,label", CASES, ids=[f"{a}-{b}-{c}" for a, b, c in CASES])
def test_a_strategy_decides_and_trades_the_same_up_to_t_without_or_with_another_future(histories, symbol, key, label):
    build = E.STRATEGY_BY_KEY[key].for_symbol(symbol)[label][1]
    h = histories[symbol]
    full_m = E.Market(symbol, h)
    full = build(full_m)
    full_path = E.run_path(full_m, full.plan, 0, len(full_m))
    n_trades = 0
    for n_cut in _cuts(full_m, full.plan):
        for kind, data in futures(h, n_cut):
            m2 = E.Market(symbol, data)
            part = build(m2)
            what = f"{symbol} {key} {label} {kind} at {n_cut}"
            _same_plan(full.plan, part.plan, n_cut, what)
            n_trades += _same_trades(full_m, full.plan, m2, part.plan, n_cut, what, full_path=full_path)
            if isinstance(full.risk, E.TargetPlan):
                _same_target(full_m, full.risk, m2, part.risk, n_cut, what + " (risk-sized)")
            if full.regime is not None:
                T = int(full_m.t[n_cut - 1])           # as far as the cut history's own clock reaches
                ta, va = full.regime
                tb, vb = part.regime
                np.testing.assert_array_equal(va[ta <= T], vb[tb <= T], err_msg=what + ": regime")
    if not (key == "tsmom" and label == "alt"):     # the 12-month sign needs a year of the 14 months of history
        assert n_trades > 0, f"{symbol} {key} {label}: no trade to compare"


@pytest.fixture(scope="module")
def short_histories():
    return {"XAUUSDm": gold_like(days=45, seed=3), "BTCUSDm": btc_like(days=30, seed=4)}


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_the_bot_filters_and_v3lite_decide_the_same_up_to_t(short_histories, symbol):
    h = short_histories[symbol]
    full_m = E.Market(symbol, h)
    full_sig = E.bot_signals(full_m)
    full_v3 = E.v3lite(full_m, full_sig)
    st_full = E.supertrend(full_m)
    lo_full = E.london_breakout(full_m) if symbol == "XAUUSDm" else E.daily_vol_breakout(full_m)
    assert (full_v3.want != 0).sum() > 0
    cuts = _cuts(full_m, full_v3, n_events=4)
    for n_cut, (kind, data) in ((c, f) for c in cuts for f in futures(h, c)):
        T = int(full_m.t[n_cut])
        m2 = E.Market(symbol, data)
        sig = E.bot_signals(m2)
        a, b = full_sig.m15_tc < T, sig.m15_tc < T
        np.testing.assert_array_equal(full_sig.m15_agree[a], sig.m15_agree[b], err_msg=f"{kind}: M15 votes")
        a, b = full_sig.h1_tc < T, sig.h1_tc < T
        for name in ("h1_open", "h1_trend", "h1_vol"):
            np.testing.assert_array_equal(getattr(full_sig, name)[a], getattr(sig, name)[b], err_msg=f"{kind}: {name}")
        v3 = E.v3lite(m2, sig)
        _same_plan(full_v3, v3, n_cut, f"{kind}: V3-lite")
        _same_trades(full_m, full_v3, m2, v3, n_cut, f"{kind}: V3-lite")
        for name, fa, fb in (("votes", full_sig.votes_at, sig.votes_at), ("trend", full_sig.trend_at, sig.trend_at)):
            pa = E.filtered(st_full.plan, full_m, fa)
            pb = E.filtered(E.supertrend(m2).plan, m2, fb)
            _same_plan(pa, pb, n_cut, f"{kind}: supertrend + {name}")
            _same_trades(full_m, pa, m2, pb, n_cut, f"{kind}: supertrend + {name}")
            pa = E.filtered(lo_full.plan, full_m, fa)
            pb = E.filtered((E.london_breakout(m2) if symbol == "XAUUSDm" else E.daily_vol_breakout(m2)).plan, m2, fb)
            _same_plan(pa, pb, n_cut, f"{kind}: orders + {name}")
            _same_trades(full_m, pa, m2, pb, n_cut, f"{kind}: orders + {name}")
        rt, rv = st_full.regime
        ra = E.filtered(full_v3, full_m, lambda x: E.value_at(rt, rv, x, 0))
        rt2, rv2 = E.supertrend(m2).regime
        rb = E.filtered(v3, m2, lambda x: E.value_at(rt2, rv2, x, 0))
        _same_plan(ra, rb, n_cut, f"{kind}: V3-lite + regime")
        _same_trades(full_m, ra, m2, rb, n_cut, f"{kind}: V3-lite + regime")


def test_a_period_account_only_sees_its_own_trades():
    """Running from a later start gives the same trades as the full run from that point for a state-free plan."""
    m = E.Market("XAUUSDm", gold_like(days=60))
    b = E.supertrend(m)
    start = len(m) // 2
    p = E.run_path(m, b.plan, start, len(m))
    assert (p.eix >= start).all()
    assert p.dir.size == 0 or p.eix[0] >= start
