"""
Study 2's data, guard and execution harness (``backtesting/research/tradeiq2_market.py``).

(a) The guard: nothing at or after 2024-07-01 is loaded, served or scored, and no window overlapping gold's Early
    window is scored, until FINALISTS.md of the study-2 folder is frozen (written in tmp_path only); never gold before
    2017, BTC before 2019, a claim market before its Development start.
(b) Bars: M5 / M15 on UTC boundaries with study 1's tick volume and spread; 1W = ISO weeks of the merged 1D bars;
    1H / 4H / 1D are study 1's bars.
(c) The New York clock across daylight saving; Session Hunter's day key.
(d) Binance 5m klines: stamps in ms and us, the 5-minute grid, alignment on M5, sums on M15.
(e) Execution on hand-made bars: the two kernel traps of the spec (orb_session_swing_ha.md 0.4: a buy filled at 100.20
    with a stop level of 101 must not book +0.80; a ratchet above the price must not book a fake profit), a target and
    a stop in one M1 bar, a gap through the stop, a stop entry at max(level, ask), OCO, a time stop, break-even after
    1R, two legs, two lanes, absolute targets from the actual fill, x1.5 recomputing every distance, R statistics; a
    STATE Exec through the event engine is study 1's ``run`` exactly; the summed marks are study 1's marks.
Real-data tests read the store and data/raw/binance up to the hold-out start only (skipped when absent) and run no
rule of the study: bars, clocks, volumes and one placeholder random state (not a rule) for the engine's identity.
"""

from __future__ import annotations

import hashlib
import math
import zipfile

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_market as M

DAY = 86400
T0 = TM.s_of("2019-03-04")          # a Monday, 00:00 UTC
SYMS = ("XAUUSDm", "BTCUSDm")


# ───────────────────────────── fixtures and helpers ─────────────────────────────

@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' folders as the guards see them: empty tmp folders (no FINALISTS.md: the hold-outs are closed)."""
    d2 = tmp_path / "study2"
    d2.mkdir()
    d1 = tmp_path / "study1"
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d2


def freeze(d, text="# Finalists\n\nFinalists: 0\n"):
    (d / "FINALISTS.md").write_text(text, encoding="utf-8")
    (d / "FINALISTS.md.sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "  FINALISTS.md\n")


def m1_dict(o, h=None, l=None, c=None, sp=0.2, t=None, n=None, t0=T0, step=60):
    o = np.asarray(o, np.float64)
    k = len(o)
    c = o.copy() if c is None else np.asarray(c, np.float64)
    h = np.maximum(o, c) + 0.02 if h is None else np.asarray(h, np.float64)
    l = np.minimum(o, c) - 0.02 if l is None else np.asarray(l, np.float64)
    t = t0 + step * np.arange(k, dtype=np.int64) if t is None else np.asarray(t, np.int64)
    spa = np.full(k, float(sp)) if np.isscalar(sp) else np.asarray(sp, np.float64)
    nn = np.ones(k) if n is None else np.asarray(n, np.float64)
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": spa, "n": nn}


def market(o, h=None, l=None, c=None, sp=0.2, t=None, n=None, symbol="XAUUSDm", t0=T0, end_s=None):
    return M.TMarket2(symbol, m1_dict(o, h, l, c, sp, t, n, t0), end_s)


def flat(k=360, p=100.0):
    o = np.full(k, p)
    return o, o + 0.02, o - 0.02


def gold_like(days=40, seed=5, start="2019-03-03"):
    """Gold's sessions: Sunday from 22:05 UTC, a daily break 20:57-22:02, Friday until 20:57, nothing on Saturday."""
    rng = np.random.default_rng(seed)
    t0 = TM.s_of(start)
    t = t0 + 60 * np.arange(days * 1440, dtype=np.int64)
    minute = (t % DAY) // 60
    weekday = ((t // DAY) + 4) % 7                           # 0 = Sunday
    keep = ~((minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)) & (weekday != 6)
    keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
    t = t[keep]
    n = len(t)
    c = 1300.0 + np.cumsum(rng.normal(0.0, 0.4, n))
    o = np.concatenate(([1300.0], c[:-1])) + rng.normal(0.0, 0.02, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.2, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.2, n))
    sp = 0.16 + 0.1 * rng.random(n)
    return dict(t=t, o=o, h=h, l=l, c=c, spread_mean=sp, n=rng.integers(5, 60, n).astype(np.float64))


def btc_like(days=30, seed=7, start="2019-03-04"):
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    c = 4000.0 + np.cumsum(rng.normal(0.0, 3.0, n))
    o = np.concatenate(([4000.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 2.0, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 2.0, n))
    return dict(t=t, o=o, h=h, l=l, c=c, spread_mean=np.full(n, 10.0) + rng.random(n), n=np.ones(n))


def ref_sum_marks(cm, trades, ia, iz):
    """A second, plain-Python reading of the summed marks (tradeiq2_market._sum_marks's docstring): per M1 bar, the
    exits at its open booked first, then the bar marked (the peak over the close marks of the trades that outlive it
    plus what exits inside it, the trough over everyone's worst mark), then the exits inside the bar booked.
    ``trades``: (side, weight, entry bar, exit bar, entry price, exit price, why)."""
    k = cm.k
    at_open = (X.WHY_SIGNAL, X.WHY_GAP_STOP, X.WHY_GAP_TARGET)
    bal = peak = dd = 0.0
    ec, ew = [], []
    for j in range(ia, iz):
        booked = [T for T in trades if T[3] == j and T[6] in at_open and T[2] < j]
        if booked:
            bal += sum(w * k * d * (xp - ep) for d, w, e, x, ep, xp, why in booked)
            if not [T for T in trades if T[2] < j < T[3] or (T[2] < j and T[3] == j and T[6] not in at_open)]:
                dd = max(dd, peak - bal)
                peak = max(peak, bal)
        live = [T for T in trades if T[2] <= j and (T[3] > j or (T[3] == j and T[6] not in at_open))]
        if not live:
            ec.append(bal)
            ew.append(bal)
            continue
        keep = [T for T in live if T[3] > j]
        gone = [T for T in live if T[3] == j]
        close = lambda d: cm.c[j] if d == 1 else cm.c[j] + cm.sp[j]
        worst = lambda d: cm.l[j] if d == 1 else cm.h[j] + cm.sp[j]
        uc = sum(w * k * d * (close(d) - ep) for d, w, e, x, ep, xp, why in keep)
        uw = sum(w * k * d * (worst(d) - ep) for d, w, e, x, ep, xp, why in keep)
        uw += sum(w * k * d * ((worst(d) if why in (X.WHY_TARGET, X.WHY_END) else xp) - ep)
                  for d, w, e, x, ep, xp, why in gone)
        realized = sum(w * k * d * (xp - ep) for d, w, e, x, ep, xp, why in gone)
        if keep:
            peak = max(peak, bal + realized + uc)
        dd = max(dd, peak - (bal + uw))
        ew.append(bal + uw)
        bal += realized
        ec.append(bal + uc)
        peak = max(peak, bal + uc)
    return np.asarray(ec), np.asarray(ew), bal, dd


def _check_against_reference(r):
    f = M._flat_trades(r.legs)
    trades = list(zip(f["dir"], f["w"], f["eix"], f["xix"], f["epx"], f["xpx"], f["why"]))
    ec, ew, bal, dd = ref_sum_marks(r.m, trades, r.ia, r.iz)
    assert np.allclose(ec, r.ec, atol=1e-9, rtol=0) and np.allclose(ew, r.ew, atol=1e-9, rtol=0)
    assert bal == pytest.approx(r.net, abs=1e-9) and dd == pytest.approx(r.max_dd, abs=1e-9)


def run6(m, ex, cost=1.0, a=T0, z=None):
    return M.run_exec(m, ex, a, int(m.t[-1]) + 60 if z is None else z, cost)


def rows(r):
    tr = r.trades
    return list(zip(tr.side, tr.entry_ix, tr.exit_ix, np.round(tr.entry, 9), np.round(tr.exit, 9), tr.reason))


# ───────────────────────────── (e) the kernel traps of the spec ─────────────────────────────

def test_e_trap_a_buy_filled_at_100_20_with_a_stop_level_of_101_books_nothing():
    """orb_session_swing_ha.md 0.4: external's kernel given the level as the initial stop (trl) books a fake +0.80;
    the harness drops the entry because its fill (100.20) is beyond its stop (101)."""
    o, h, l = flat()
    m = market(o, h, l)
    b = m.tbars("1H")
    # the trap itself, in the raw kernel: a "stop" exit at 101.00 for +0.80
    p = X.run_path(m, X.make_plan(m, [int(m.t[b.ex[0]])], want=[1], trl=[101.0]), 0, len(m))
    assert p.why[0] == X.WHY_STOP and p.epx[0] == pytest.approx(100.2) and p.xpx[0] == pytest.approx(101.0)
    # the harness: no trade, counted as dropped
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=101.0)))
    assert len(r.trades) == 0 and r.net == 0.0 and r.counts["dropped_stop"] == 1
    # at the fill exactly is dropped too; a short mirrors it (filled at the bid 100.00, stop level 99.90)
    assert run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=100.2))).counts["dropped_stop"] == 1
    assert run6(m, M.event_exec("1H", entries=M.entries([0], [-1], stop_level=99.9))).counts["dropped_stop"] == 1
    # a level below the fill becomes the distance |fill - level| from the actual fill
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.0, exit_bar=3)))
    assert rows(r) == [(1, 60, 240, 100.2, 100.0, "signal")]
    assert r.trades.risk[0] == pytest.approx(1.2) and r.trades.r[0] == pytest.approx(-0.2 / 1.2)


def test_e_trap_a_ratchet_above_the_price_is_a_market_exit_not_a_fake_profit():
    """A later decision raising the stop to 102 while price is near 100: the raw kernel exits at 102.00 (+1.80); the
    harness exits at the next M1 open at the bid instead."""
    o, h, l = flat()
    m = market(o, h, l)
    b = m.tbars("1H")
    plan = X.make_plan(m, m.t[[b.ex[0], b.ex[2]]], want=[1, 0], sl=[1.0, np.nan], trl=[np.nan, 102.0])
    p = X.run_path(m, plan, 0, len(m))
    assert p.why[0] == X.WHY_STOP and p.xpx[0] == pytest.approx(102.0)           # +1.80, a fake profit
    tight = np.full(len(b), np.nan)
    tight[2] = 102.0
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), tighten_long=tight))
    assert rows(r) == [(1, 60, 180, 100.2, 100.0, "signal")]
    assert r.trades.pnl[0] == pytest.approx(-0.2) and r.counts["tighten_exits"] == 1
    # a short: a level below the ask at the open is a market exit at the ask
    tight_s = np.full(len(b), np.nan)
    tight_s[2] = 100.1                                                           # ask at the open 100.20
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [-1], stop_dist=1.0), tighten_short=tight_s))
    assert rows(r) == [(-1, 60, 180, 100.0, 100.2, "signal")]
    # a level below the bid is applied as the new stop, and the stop then fills at that level
    lo = l.copy()
    lo[200] = 99.5
    m2 = market(o, h, lo)
    tight[2] = 99.8
    r = run6(m2, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), tighten_long=tight))
    assert rows(r) == [(1, 60, 200, 100.2, 99.6, "stop")] and r.counts["tighten_rows"] == 1
    # a looser level than the current stop changes nothing
    tight[2] = 98.0
    r = run6(m2, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, exit_bar=4), tighten_long=tight))
    assert rows(r) == [(1, 60, 300, 100.2, 100.0, "signal")]


# ───────────────────────────── (e) fills, stops, targets, orders ─────────────────────────────

def test_e_a_crossed_tightening_after_the_position_has_closed_does_nothing():
    o, h, l = flat()
    l[100] = 98.0                                                               # stopped at minute 100
    m = market(o, h, l)
    tight = np.full(6, np.nan)
    tight[2] = 102.0                                                            # crossed at minute 180's open
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), tighten_long=tight))
    assert rows(r) == [(1, 60, 100, 100.2, 99.0, "stop")]
    assert r.counts["tighten_exits"] == 0 and r.counts["tighten_rows"] == 0


def test_e_runs_without_trades_and_mixed_lanes():
    o, h, l = flat(600)
    m = market(o, h, l)
    legs = (M.Leg(0.5, target_r=2.0), M.Leg(0.5, no_target=True))
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=101.0), legs=legs))
    assert len(r.trades) == 0 and r.net == 0.0 and r.max_dd == 0.0 and np.all(r.ec == 0) and not r.single
    TM.metrics(r), M.scores(r), M.account_curve(r)
    empty = M.event_exec("1H", entries=M.entries(np.zeros(0, np.int64), np.zeros(0, np.int64)))
    r = run6(m, M.lanes_exec([empty, empty]))
    assert len(r.trades) == 0 and r.net == 0.0 and r.kind == "lanes"
    # a STATE lane (study 1's run) next to an EVENTS lane
    st = np.array([0, 1, 1, 0, 0, 0, 0, 0, 0, 0])
    la = M.state_exec("1H", st)
    lb = M.event_exec("1H", entries=M.entries([2], [-1], exit_bar=6))
    r = run6(m, M.lanes_exec([la, lb]))
    ra, rb = run6(m, la), run6(m, lb)
    assert r.net == pytest.approx(ra.net + rb.net) and list(r.trades.lane) == [0, 1]
    assert r.counts["taken"] == 2 and r.n_decisions == ra.n_decisions + rb.n_decisions


def test_e_a_target_and_a_stop_in_one_m1_bar_the_stop_wins():
    o, h, l = flat()
    h[100], l[100] = 101.5, 99.0
    m = market(o, h, l)
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, target_dist=1.0)))
    assert rows(r) == [(1, 60, 100, 100.2, 99.0, "stop")]                       # 99.20, one spread worse
    assert r.trades.pnl[0] == pytest.approx(-1.2) and r.trades.slippage[0] == pytest.approx(0.2)
    # the target alone in a bar fills at the target (no slippage)
    h2, l2 = h.copy(), l.copy()
    l2[100] = 99.9
    r = run6(market(o, h2, l2), M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, target_dist=1.0)))
    assert rows(r) == [(1, 60, 100, 100.2, 101.2, "target")] and r.trades.r[0] == pytest.approx(1.0)


def test_e_a_gap_through_the_stop_fills_at_the_open_one_spread_worse():
    o, h, l = flat()
    o[150], h[150], l[150] = 98.0, 98.02, 97.98
    m = market(o, h, l)
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.0)))
    assert rows(r) == [(1, 60, 150, 100.2, 97.8, "gap stop")]
    o2, h2, l2 = flat()
    o2[150], h2[150], l2[150] = 102.0, 102.02, 101.98
    r = run6(market(o2, h2, l2), M.event_exec("1H", entries=M.entries([0], [-1], stop_level=101.0, exit_bar=4)))
    assert rows(r) == [(-1, 60, 150, 100.0, 102.4, "gap stop")]                # the ask opened at 102.20


def test_e_absolute_targets_are_distances_from_the_actual_fill_and_crossed_ones_drop_the_entry():
    o, h, l = flat()
    h[120] = 101.05
    m = market(o, h, l)
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.0, target_level=101.0)))
    assert rows(r) == [(1, 60, 120, 100.2, 101.0, "target")]                   # the level itself, not fill + 1.0
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.0, target_level=100.1)))
    assert len(r.trades) == 0 and r.counts["dropped_target"] == 1               # the ask fill is beyond the target
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [-1], stop_level=101.0, target_level=100.0)))
    assert r.counts["dropped_target"] == 1                                      # a short filled at 100.00 = target


def test_e_a_stop_entry_fills_at_max_of_its_level_and_the_ask():
    o, h, l = flat()
    h[70] = 100.4                                                               # the ask high 100.60 reaches 100.50
    m = market(o, h, l)
    until = int(m.t[-1]) + 60
    ex = M.event_exec("1H", orders=M.orders([0], until, buy=100.5, buy_stop=99.5), exit_long=_at(6, 4))
    r = run6(m, ex)
    assert rows(r) == [(1, 70, 300, 100.5, 100.0, "signal")] and r.trades.bar[0] == 1
    # a gap: the ask opens at 101.20, above the level: the fill is the ask
    o2, h2, l2 = flat()
    o2[70:], h2[70:], l2[70:] = 101.0, 101.02, 100.98
    r = run6(market(o2, h2, l2), M.event_exec("1H", orders=M.orders([0], until, buy=100.5, buy_stop=99.5),
                                              exit_long=_at(6, 4)))
    assert rows(r)[0][:4] == (1, 70, 300, 101.2)
    # a sell stop fills at min(level, bid at the open), on the bid low
    o3, h3, l3 = flat()
    o3[80:], h3[80:], l3[80:] = 99.0, 99.02, 98.98
    r = run6(market(o3, h3, l3), M.event_exec("1H", orders=M.orders([0], until, sell=99.5, sell_stop=100.5),
                                              exit_short=_at(6, 4)))
    assert rows(r)[0][:4] == (-1, 80, 300, 99.0)
    # an order that expires before it is reached fills nothing
    r = run6(m, M.event_exec("1H", orders=M.orders([0], T0 + 3600 + 5 * 60, buy=100.5, buy_stop=99.5)))
    assert len(r.trades) == 0 and r.counts["unfilled"] == 1


def _at(n, *bars):
    a = np.zeros(n, bool)
    a[list(bars)] = True
    return a


def test_e_oco_one_fill_cancels_the_other_and_the_nearer_side_wins_a_bar_that_reaches_both():
    o, h, l = flat()
    l[80] = 99.4                                                                # the sell side fills first
    h[200] = 100.7                                                              # the buy side would fill later
    m = market(o, h, l)
    until = int(m.t[-1]) + 60
    ex = M.event_exec("1H", orders=M.orders([0], until, buy=100.5, sell=99.5, buy_stop=99.5, sell_stop=100.5),
                      exit_short=_at(6, 2))
    r = run6(m, ex)
    assert rows(r) == [(-1, 80, 180, 99.5, 100.2, "signal")]                    # no buy afterwards
    # both sides in one bar: the buy level is 0.30 above the ask open, the sell level 0.50 below the bid open
    h2, l2 = h.copy(), l.copy()
    h2[80], l2[80] = 100.4, 99.4
    r = run6(market(o, h2, l2), M.event_exec("1H", orders=M.orders([0], until, buy=100.5, sell=99.5,
                                                                     stop_dist=2.0), exit_long=_at(6, 2)))
    assert rows(r) == [(1, 80, 180, 100.5, 100.0, "signal")]
    # the fill's own bar can stop it (its opposite extreme is taken to come after the fill), not reach its target
    h3, l3 = h.copy(), l.copy()
    h3[80], l3[80] = 100.4, 99.6
    r = run6(market(o, h3, l3), M.event_exec("1H", orders=M.orders([0], until, buy=100.5, buy_stop=99.7,
                                                                     buy_target=100.3)))
    assert r.counts["dropped_target"] == 1                                       # 100.50 is beyond 100.30
    r = run6(market(o, h3, l3), M.event_exec("1H", orders=M.orders([0], until, buy=100.5, buy_stop=99.7)))
    assert rows(r) == [(1, 80, 80, 100.5, 99.5, "stop")]


def test_e_on_fill_gives_a_stop_order_its_exit_from_the_fills_bar():
    o, h, l = flat()
    h[130] = 100.4                                                              # fills inside bar 2 (M1 120..179)
    m = market(o, h, l)
    seen = []

    def exit_of(fill_bar, side):
        seen.append((fill_bar, side))
        return fill_bar + 1

    ex = M.event_exec("1H", orders=M.orders([0], int(m.t[-1]) + 60, buy=100.5, buy_stop=99.5), on_fill=exit_of)
    r = run6(m, ex)
    assert seen == [(2, 1)] and rows(r) == [(1, 130, 240, 100.5, 100.0, "signal")]
    # per-bar exits act from the fill's own bar on
    ex = M.event_exec("1H", orders=M.orders([0], int(m.t[-1]) + 60, buy=100.5, buy_stop=99.5), exit_long=_at(6, 1, 2))
    assert rows(run6(m, ex)) == [(1, 130, 180, 100.5, 100.0, "signal")]


def test_e_a_time_stop_exits_at_the_next_open_after_the_close_of_its_bar():
    o = 100.0 + 0.01 * np.arange(360)
    m = market(o)
    r = run6(m, M.event_exec("1H", entries=M.entries([1], [1], exit_bar=4)))
    assert rows(r) == [(1, 120, 300, round(o[120] + 0.2, 9), round(o[300], 9), "signal")]
    assert r.trades.exit_time[0] == TM.utc(T0 + 5 * 3600)
    # per-bar exits act from the bar after the entry's decision bar: one at bar 1 itself is ignored
    r = run6(m, M.event_exec("1H", entries=M.entries([1], [1]), exit_long=_at(6, 1, 3)))
    assert rows(r)[0][2] == 240
    # an exit decision whose fill is past the window closes at the window's last M1 close
    r = run6(m, M.event_exec("1H", entries=M.entries([1], [-1])))
    assert rows(r) == [(-1, 120, 359, round(o[120], 9), round(o[359] + 0.2, 9), "end")]


def _up_at_100():
    """100.00 until minute 99, 101.00 from minute 100 (lows 100.98, above the break-even level 100.20)."""
    o, h, l = flat()
    o[100:], h[100:], l[100:] = 101.0, 101.02, 100.98
    return o, h, l


def test_e_break_even_after_1r():
    o, h, l = _up_at_100()
    h[100] = 101.3                                                              # +1R (fill 100.20, risk 1.00)
    l[150] = 100.1                                                              # back below the fill
    m = market(o, h, l)
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, be_r=1.0)))
    assert rows(r) == [(1, 60, 150, 100.2, 100.0, "stop")]                      # at the fill, one spread worse
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0)))
    assert r.trades.reason[0] == "end"                                         # without it, still open
    # a bar that reaches 1R moves the stop for the next bars only: the same bar's dip below the fill does not stop
    o2, h2, l2 = _up_at_100()
    h2[150], l2[150] = 101.3, 100.1
    r = run6(market(o2, h2, l2), M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, be_r=1.0)))
    assert r.trades.reason[0] == "end"
    # break-even with an absolute stop level: 1R from the actual fill (100.20 - 99.20)
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.2, be_r=1.0)))
    assert rows(r) == [(1, 60, 150, 100.2, 100.0, "stop")]
    # x1.5: the fill is 100.30, 1R = 1.10, so 101.30 is not reached at minute 100 and the stop stays at 99.20
    assert run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.2, be_r=1.0)), 1.5).trades.reason[0] \
        == "end"


def test_e_tighten_be_takes_the_tighter_of_break_even_and_the_level():
    o, h, l = flat()
    o[150:], h[150:], l[150:] = 100.5, 100.52, 100.48
    l[200] = 100.1
    m = market(o, h, l)
    tight, be = np.full(6, np.nan), np.zeros(6, bool)
    tight[2], be[2] = 99.5, True                                                # BE (100.20) is tighter than 99.50
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), tighten_long=tight, tighten_be=be))
    assert rows(r) == [(1, 60, 200, 100.2, 100.0, "stop")]
    tight[2] = 100.3                                                            # the level is tighter
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), tighten_long=tight, tighten_be=be))
    assert rows(r) == [(1, 60, 200, 100.2, 100.1, "stop")]


def test_e_cost_x15_recomputes_fills_distances_and_comparisons():
    o, h, l = flat()
    l[100] = 98.9
    m = market(o, h, l)
    ex = M.event_exec("1H", entries=M.entries([0], [1], stop_level=99.0, target_r=2.0))
    r1, r15 = run6(m, ex, 1.0), run6(m, ex, 1.5)
    assert r1.trades.risk[0] == pytest.approx(1.2) and r15.trades.risk[0] == pytest.approx(1.3)
    assert r1.trades.entry[0] == pytest.approx(100.2) and r15.trades.entry[0] == pytest.approx(100.3)
    assert r1.trades.exit[0] == pytest.approx(98.8) and r15.trades.exit[0] == pytest.approx(98.7)
    # a short's tightening just above the x1.0 ask (100.20) but below the x1.5 ask (100.30)
    tight = np.full(6, np.nan)
    tight[2] = 100.25
    ex = M.event_exec("1H", entries=M.entries([0], [-1], stop_dist=2.0), tighten_short=tight, exit_short=_at(6, 4))
    r1, r15 = run6(m, ex, 1.0), run6(m, ex, 1.5)
    assert r1.counts["tighten_rows"] == 1 and r1.trades.reason[0] == "signal" and r1.trades.exit_ix[0] == 300
    assert r15.counts["tighten_exits"] == 1 and r15.trades.exit_ix[0] == 180
    # the drop rule on each cost's own fill: a long's stop level of 100.25 lies above the x1.0 fill (100.20: dropped)
    # and below the x1.5 fill (100.30: taken, and stopped at once by the bid, a real loss)
    ex = M.event_exec("1H", entries=M.entries([0], [1], stop_level=100.25, exit_bar=4))
    assert run6(m, ex, 1.0).counts["dropped_stop"] == 1
    r15 = run6(m, ex, 1.5)
    assert rows(r15) == [(1, 60, 60, 100.3, 99.95, "stop")] and r15.trades.pnl[0] < 0


# ───────────────────────────── (e) one position at a time, legs, lanes ─────────────────────────────

def test_e_an_event_rule_takes_no_new_trade_while_one_is_open_and_waits_for_its_next_event():
    o, h, l = flat(600)
    l[100] = 98.0                                                               # the first trade is stopped
    m = market(o, h, l)
    E = M.entries([0, 1, 2, 5], [1, -1, 1, -1], stop_dist=1.0, exit_bar=[3, 4, 6, 8])
    r = run6(m, M.event_exec("1H", entries=E))
    # entry 0 stopped at M1 100; entry 1 (decided 02:00, filled 120) comes after it; entry 2 is busy; entry 3 later
    assert [(s, a, b) for s, a, b, *_ in rows(r)] == [(1, 60, 100), (-1, 120, 300), (-1, 360, 540)]
    assert r.counts["busy"] == 1 and r.counts["taken"] == 3 and r.counts["candidates"] == 4
    # an exit at an M1 open lets the next entry fill at that same open (a reversal)
    E = M.entries([0, 3], [1, -1], exit_bar=[3, 6])
    assert [(s, a, b) for s, a, b, *_ in rows(run6(m, M.event_exec("1H", entries=E)))] == [(1, 60, 240), (-1, 240, 420)]


def test_e_the_window_reads_entries_decided_after_its_start_and_closes_at_its_end():
    o = 100.0 + 0.01 * np.arange(480)
    m = market(o)
    E = M.entries([1, 2, 6], [1, 1, -1])
    r = M.run_exec(m, M.event_exec("1H", entries=E), T0 + 7200, T0 + 6 * 3600)
    # bar 1 closes at 02:00 = the window's start: not in it; bar 6's fill (07:00) is past its end
    assert rows(r) == [(1, 180, 359, round(o[180] + 0.2, 9), round(o[359], 9), "end")]
    assert r.n_decisions == 1


def test_e_two_legs_half_at_2r_and_the_rest_at_the_exit():
    o, h, l = flat()
    h[150] = 102.3                                                              # 2R for a long filled at 100.20
    l[250] = 99.5
    m = market(o, h, l)
    legs = (M.Leg(0.5, target_r=2.0), M.Leg(0.5, no_target=True))
    ex = M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, exit_bar=4), legs=legs)
    r = run6(m, ex)
    assert len(r.trades) == 1 and not r.single
    tr = r.trades.iloc[0]
    assert tr.pnl == pytest.approx(0.5 * 2.0 + 0.5 * (100.0 - 100.2))
    assert tr.reasons == "target|signal" and tr.reason == "signal" and tr.exit_ix == 300
    assert tr.r == pytest.approx(tr.pnl / 1.0)
    # the drawdown is measured on the summed marks: one leg's worst mark at minute 250 is halved
    # the target bar (minute 150): the peak takes the target leg's +1.00 and the other leg's close mark (-0.10) first,
    # then the trough is both legs' worst marks (the low 99.98: -0.11 each), as balke's multi-position kernel marks
    one = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0, exit_bar=4)))
    assert r.max_dd == pytest.approx(0.9 + 0.22)
    _check_against_reference(r)
    assert r.net == pytest.approx(0.5 * 2.0 + 0.5 * one.net)
    assert np.allclose(r.ec[-1], r.net)
    # identical entries: when one leg's fill is beyond its target the whole entry is dropped
    legs2 = (M.Leg(0.5, target_level=100.1), M.Leg(0.5, no_target=True))
    r2 = run6(m, M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), legs=legs2))
    assert len(r2.trades) == 0 and r2.counts["dropped_target"] == 1
    # weights must sum to 1
    with pytest.raises(ValueError):
        M.event_exec("1H", entries=M.entries([0], [1], stop_dist=1.0), legs=(M.Leg(0.5), M.Leg(0.6)))


def test_e_two_legs_wait_for_both_legs_to_be_flat_before_the_next_entry():
    o, h, l = flat(600)
    h[100] = 102.3                                                              # the target leg leaves at 100
    m = market(o, h, l)
    legs = (M.Leg(0.5, target_r=2.0), M.Leg(0.5, no_target=True))
    E = M.entries([0, 2, 5], [1, 1, 1], stop_dist=1.0, exit_bar=[4, 6, 8])
    r = run6(m, M.event_exec("1H", entries=E, legs=legs))
    # entry 1 (filled 180) comes while the no-target leg is still open: busy for both legs
    assert list(r.trades.entry_ix) == [60, 360] and r.counts["busy"] == 1


def test_e_two_lanes_are_summed_and_the_account_is_balkes_multi_position_kernel():
    g = gold_like(days=20)
    m = M.TMarket2("XAUUSDm", g)
    b = m.tbars("1H")
    n = len(b)
    rng = np.random.default_rng(4)
    bars_a = np.sort(rng.choice(np.arange(20, n - 30), 25, replace=False))
    bars_b = np.sort(rng.choice(np.arange(20, n - 30), 25, replace=False))
    la = M.event_exec("1H", entries=M.entries(bars_a, 1, stop_dist=3.0, exit_bar=bars_a + 6))
    lb = M.event_exec("1H", entries=M.entries(bars_b, -1, stop_dist=3.0, exit_bar=bars_b + 4))
    a, z = TM.s_of("2019-03-05"), TM.s_of("2019-03-22")
    ra, rb = M.run_exec(m, la, a, z), M.run_exec(m, lb, a, z)
    r = M.run_exec(m, M.lanes_exec([la, lb]), a, z)
    assert r.kind == "lanes" and len(r.trades) == len(ra.trades) + len(rb.trades)
    assert r.net == pytest.approx(ra.net + rb.net, abs=1e-9)
    assert np.allclose(r.ec, ra.ec + rb.ec, atol=1e-9)
    _check_against_reference(r)
    assert set(r.trades.lane) == {0, 1} and np.all(np.diff(r.trades.entry_ix.to_numpy()) >= 0)
    both = (ra.pos != 0) & (rb.pos != 0)
    assert both.any() and np.all(r.pos[both] == 2)                             # a long and a short at once
    s = TM.metrics(r)
    assert s["trades"] == len(r.trades) and s["net_exact"] == pytest.approx(r.net)
    # the account: balke's multi-position kernel on the lanes' trades
    from backtesting.research import balke as B
    curve, acc = M.account_curve(r)
    f = M._flat_trades(r.legs)
    e = TM._edges_days(r.a_s, r.z_s)
    bnd = np.concatenate([[r.ia], r.ia + np.searchsorted(m.t[r.ia:r.iz], e[1:-1]), [r.iz]])
    out = B._multi_kernel(r.m.c, r.m.h, r.m.l, r.m.sp, r.m.k, f["eix"], f["epx"], f["xix"], f["xpx"], f["why"],
                          f["dir"], f["risk"], np.full(len(f["eix"]), np.nan), 0, 0.0, r.ia, r.iz,
                          bnd[1:-1].astype(np.int64), X.ACCOUNT, X.STEP_UP, float(X.UNIT_MAX))
    assert acc["final"] == pytest.approx(out[2]) and curve.equity.iloc[-1] == pytest.approx(out[2])
    assert acc["final"] == pytest.approx(X.ACCOUNT + r.net, abs=1e-6)          # one unit throughout at $2,000
    # study 1's account_curve refuses a run without a single path
    with pytest.raises(TypeError):
        TM.account_curve(r)


def test_e_the_account_of_two_legs_is_the_50_50_mix_per_unit():
    t = T0 + 3600 * np.arange(12, dtype=np.int64)
    p = np.array([1000, 1000, 1000, 1700, 1700, 1700, 2000, 2000, 2000, 2000, 2000, 2000], np.float64)
    m = market(p, h=p + 0.1, l=p - 0.1, c=p, sp=0.2, t=t)
    legs = (M.Leg(0.5, target_r=1.0), M.Leg(0.5, no_target=True))
    ex = M.event_exec("1H", entries=M.entries([0, 4], 1, stop_dist=100.0, exit_bar=[2, 8]), legs=legs)
    r = M.run_exec(m, ex, int(t[0]), int(t[-1]) + 60)
    # each position: the target leg's open gaps through its 1R target (a gap target at the open), the other leg exits
    # at its exit decision's open, both at the same price: +699.80 and +299.80 per unit
    assert list(np.round(r.trades.pnl, 6)) == [699.8, 299.8]
    assert [x.split("|") for x in r.trades.reasons] == [["gap target", "signal"], ["gap target", "signal"]]
    curve, acc = M.account_curve(r)
    # 1 unit at $2,000; 2 units once the balance passed $2,500: the second position earns 2 x 299.80
    assert acc["final"] == pytest.approx(2000 + 699.8 + 2 * 299.8) and acc["positions"] == 2
    assert acc["leg_weight"] == 0.5 and curve.equity.iloc[0] == 2000.0


# ───────────────────────────── (e) the state form is study 1's run ─────────────────────────────

def _random_states(n, seed, p=0.12):
    rng = np.random.default_rng(seed)
    flips = np.cumsum(rng.random(n) < p)
    return np.where(flips % 3 == 0, 1, np.where(flips % 3 == 1, -1, 0)).astype(np.int64)


@pytest.mark.parametrize("cost", [1.0, 1.5])
@pytest.mark.parametrize("sym", SYMS)
def test_e_a_state_exec_through_the_event_engine_is_study_1s_run_exactly(cost, sym):
    g = gold_like(days=60) if sym == "XAUUSDm" else btc_like(days=45)
    m = M.TMarket2(sym, g)
    for tf in ("1H", "4H"):
        b = m.tbars(tf)
        st = _random_states(len(b), 3, p=0.3)
        stop = TM.s1_stop(b, 1.0)
        a, z = TM.s_of("2019-03-06 13:00"), TM.s_of("2019-04-15")
        r1 = TM.run(m, b, st, a, z, stop=stop, cost=cost)
        fast = M.run_exec(m, M.state_exec(tf, st, stop), a, z, cost)
        slow = M.run_exec(m, M.state_exec(tf, st, stop, exit_long=np.zeros(len(b), bool)), a, z, cost)
        assert slow.kind == "state" and "busy" in slow.counts and len(r1.trades) > 20
        assert (r1.trades.reason == "stop").sum() + (r1.trades.reason == "gap stop").sum() > 5
        for r in (fast, slow):
            cols = ["entry_time", "exit_time", "side", "entry", "exit", "reason", "pnl", "slippage", "hold_h",
                    "entry_ix", "exit_ix"]
            assert r.trades[cols].equals(r1.trades[cols]), (tf, sym)
            assert np.array_equal(r.ec, r1.ec) and np.array_equal(r.ew, r1.ew) and np.array_equal(r.pos, r1.pos)
            assert r.net == r1.net and r.max_dd == r1.max_dd and r.n_decisions == r1.n_decisions
            s, s1 = TM.metrics(r), TM.metrics(r1)
            assert all((s[k] == s1[k]) or (isinstance(s[k], float) and math.isnan(s[k]) and math.isnan(s1[k]))
                       for k in s1)
        # without a stop too
        r1 = TM.run(m, b, st, a, z, cost=cost)
        slow = M.run_exec(m, M.state_exec(tf, st, exit_short=np.zeros(len(b), bool)), a, z, cost)
        assert rows(slow) == rows(r1) and slow.net == r1.net and slow.max_dd == r1.max_dd


def test_e_a_state_exec_with_a_target_stays_flat_until_its_state_changes():
    o, h, l = flat(480)
    h[100] = 102.0
    m = market(o, h, l)
    st = np.array([1, 1, 1, 1, 0, 1, 1, 1])
    r = run6(m, M.state_exec("1H", st, np.full(8, 1.0), target_r=1.0))
    assert [(a, b, why) for _, a, b, _, _, why in rows(r)] == [(60, 100, "target"), (360, 479, "end")]


def test_sum_marks_are_study_1s_unit_marks_for_trades_that_do_not_overlap():
    g = gold_like(days=30)
    m = M.TMarket2("XAUUSDm", g)
    b = m.tbars("1H")
    st = _random_states(len(b), 9)
    for cost in (1.0, 1.5):
        r = TM.run(m, b, st, "2019-03-06", "2019-03-30", stop=TM.s1_stop(b, 1.0), cost=cost)
        p, cm = r.path, r.m
        assert len(p) > 20
        ec, ew, pos, bal, dd = M._sum_marks(cm.c, cm.h, cm.l, cm.sp, cm.k, p.dir, np.ones(len(p)), p.eix, p.xix,
                                            p.epx, p.xpx, p.why, r.ia, r.iz)
        assert np.array_equal(ec, r.ec) and np.array_equal(ew, r.ew) and np.array_equal(pos, r.pos)
        assert bal == r.net and dd == r.max_dd


# ───────────────────────────── scores, R, run_variant ─────────────────────────────

def test_r_statistics_and_the_study_1_score_functions_accept_a_run2():
    o, h, l = flat(600)
    h[100] = 102.3                                                              # trade 1: +2R target
    l[400] = 98.0                                                               # trade 2: stopped, -1.2 = -1R
    m = market(o, h, l)
    E = M.entries([0, 5], [1, 1], stop_dist=[1.0, 1.2], target_r=2.0)
    r = run6(m, M.event_exec("1H", entries=E))
    assert list(r.trades.reason) == ["target", "stop"]
    rs = M.r_stats(r)
    assert rs["r_trades"] == 2 and rs["win_rate_r"] == 50.0
    assert list(np.round(r.trades.r, 9)) == [2.0, round(-1.4 / 1.2, 9)]
    assert rs["pf_r"] == pytest.approx(2.0 / (1.4 / 1.2)) and rs["avg_r"] == pytest.approx((2.0 - 1.4 / 1.2) / 2)
    s = M.scores(r)
    assert s["trades"] == 2 and s["n_stops"] == 1 and s["avg_r"] == rs["avg_r"] and s["n_taken"] == 2
    TM.weekly_pnl(r), TM.quarter_pnl(r), TM.unit_curve(r)
    curve, acc = M.account_curve(r)
    assert acc["final"] == pytest.approx(X.ACCOUNT + r.net)
    # no stop: no R
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], exit_bar=3)))
    assert M.r_stats(r)["r_trades"] == 0 and np.isnan(M.r_stats(r)["avg_r"])
    # a given risk gives an R without a stop
    r = run6(m, M.event_exec("1H", entries=M.entries([0], [1], exit_bar=3, risk=0.5)))
    assert r.trades.r[0] == pytest.approx(-0.2 / 0.5)
    with pytest.raises(ValueError):
        run6(m, M.event_exec("1H", entries=M.entries([0], [1], target_r=2.0)))  # an R target needs a stop


def test_run_variant_rows_per_window_and_cost(monkeypatch):
    g = gold_like(days=60, start="2022-12-04")
    m = M.TMarket2("XAUUSDm", g)
    ctx = M.Context(m)
    monkeypatch.setitem(M.WINDOWS, "dev", ("2022-12-06", "2023-01-01"))
    monkeypatch.setitem(M.WINDOWS, "val", ("2023-01-01", "2023-01-31"))
    monkeypatch.setitem(M.WINDOWS, "devval", ("2022-12-06", "2023-01-31"))
    b = ctx.bars("1H")
    v = M.Variant("XAUUSDm|1H|TEST|X", "XAUUSDm", "1H", "TEST", "TEST", params={"stop": "S1"})
    ex = M.state_exec("1H", _random_states(len(b), 2), TM.s1_stop(b))
    res = M.run_variant(ctx, v, ex, keep_runs=True, keep_curves=True)
    assert [x["window"] for x in res.rows] == ["dev", "val", "devval"]
    row = res.rows[0]
    assert row["vid"] == v.id and "net" in row and "net_x15" in row and "avg_r_x15" in row
    assert row["trades"] > 5 and row["trades"] == row["trades_x15"] and row["slippage_x15"] > row["slippage"]
    assert set(res.trades.window) == {"dev", "val"} and set(res.trades.cost) == {1.0, 1.5}
    assert {"pnl", "pnl_x15", "held", "held_x15"} <= set(res.quarters.columns)
    assert {"pnl", "pnl_x15"} <= set(res.weekly.columns) and len(res.curves) > 0
    with pytest.raises(M.HoldOutError):
        M.run_variant(ctx, v, ex, windows=("early",))                           # gold's Early window: frozen only
    with pytest.raises(M.HoldOutError):
        M.run_variant(ctx, v, ex, windows=("holdout",))
    slim = res.runs[("devval", 1.0)]
    assert slim.ec is None and M.account_curve(slim)[1]["final"] == pytest.approx(X.ACCOUNT + row_net(res, "devval"))
    with pytest.raises(ValueError):
        M.run_variant(ctx, M.Variant("x", "BTCUSDm", "1H", "T", "T"), ex)


def row_net(res, w):
    return [x for x in res.rows if x["window"] == w][0]["net"]


# ───────────────────────────── (a) the guard ─────────────────────────────

def test_a_the_guard_is_closed_until_finalists_md_of_study_2_is_frozen(closed_guard):
    assert issubclass(M.HoldOutError, TM.HoldOutError) and not M.frozen()
    M._guard(M.CUT_S, "up to the cut")
    with pytest.raises(M.HoldOutError):
        M._guard(M.CUT_S + 1, "one second past")
    (closed_guard / "FINALISTS.md").write_text("Finalists: 1\n")
    assert not M.frozen()
    (closed_guard / "FINALISTS.md.sha256").write_text("0" * 64 + "\n")
    assert not M.frozen()
    freeze(closed_guard)
    assert M.frozen()
    M._guard(M.CUT_S + 1, "open now")
    # study 1's frozen FINALISTS.md does not open study 2's guard
    (closed_guard / "FINALISTS.md").write_text("# edited\n")
    assert not M.frozen()
    freeze(closed_guard.parent / "study1")
    assert TM.finalists_frozen() and not M.frozen()


def test_a_windows_scored_only_where_the_plan_allows(closed_guard):
    g = M._score_guard
    g("XAUUSDm", TM.s_of("2019-01-01"), TM.s_of("2024-07-01"), "devval")
    for sym, a, z in (("XAUUSDm", "2017-01-01", "2019-01-01"), ("XAUUSDm", "2018-06-01", "2019-06-01"),
                      ("XAUUSDm", "2016-06-01", "2016-12-01"), ("BTCUSDm", "2018-06-01", "2019-06-01"),
                      ("USTECm", "2020-06-15", "2021-01-01"), ("EURUSDm", "2018-11-01", "2019-03-01"),
                      ("XAUUSDm", "2024-01-01", "2024-07-02")):
        with pytest.raises(M.HoldOutError):
            g(sym, TM.s_of(a), TM.s_of(z), f"{sym} {a}")
    g("USTECm", TM.s_of("2020-07-01"), TM.s_of("2021-01-01"), "USTECm dev")
    g("BTCUSDm", TM.s_of("2019-01-01"), TM.s_of("2023-01-01"), "BTC dev")
    freeze(closed_guard)
    g("XAUUSDm", TM.s_of("2017-01-01"), TM.s_of("2019-01-01"), "early, frozen")
    g("XAUUSDm", TM.s_of("2024-07-01"), TM.s_of("2026-11-26"), "holdout, frozen")
    for sym, a, z in (("XAUUSDm", "2016-06-01", "2017-06-01"), ("BTCUSDm", "2018-06-01", "2019-06-01")):
        with pytest.raises(M.HoldOutError):
            g(sym, TM.s_of(a), TM.s_of(z), "never")                              # frozen or not
    assert M.window_span("dev", "USTECm") == ("2020-07-01", "2023-01-01")
    assert M.window_span("early", "XAUUSDm") == ("2017-01-01", "2019-01-01")
    assert M.window_span("holdout", "BTCUSDm") == ("2024-07-01", "2026-11-27")
    with pytest.raises(ValueError):
        M.window_span("early", "BTCUSDm")


def test_a_the_guard_on_markets_runs_and_scores(closed_guard, tmp_path):
    t = TM.s_of("2024-06-24") + 60 * np.arange(12 * 1440, dtype=np.int64)
    k = len(t)
    m1 = m1_dict(2300.0 + 0.01 * np.arange(k), t=t)
    with pytest.raises(M.HoldOutError):
        M.TMarket2("XAUUSDm", m1)                                                # minutes past the cut
    cut = t < M.CUT_S
    m = M.TMarket2("XAUUSDm", {k_: v[cut] for k_, v in m1.items()}, M.CUT_S)
    b = m.tbars("1H")
    ex = M.state_exec("1H", np.ones(len(b), np.int64))
    M.run_exec(m, ex, "2024-06-25", "2024-07-01")
    with pytest.raises(M.HoldOutError):
        M.run_exec(m, ex, "2024-06-25", "2024-07-01 00:00:01")
    with pytest.raises(M.HoldOutError):
        M.buy_and_hold(m, "2024-06-25", "2024-07-02")
    freeze(closed_guard)
    with pytest.raises(TM.HoldOutError):
        M.TMarket2("XAUUSDm", m1).tbars("1H")              # study 1's own guard (under TMarket.tbars) is closed here
    freeze(closed_guard.parent / "study1")                 # as it is in the repository: study 1 is frozen
    mm = M.TMarket2("XAUUSDm", m1)
    bb = mm.tbars("1H")
    r = M.run_exec(mm, M.state_exec("1H", np.ones(len(bb), np.int64)), "2024-06-25", "2024-07-05")
    assert M.metrics(r)["trades"] == 1
    (closed_guard / "FINALISTS.md").write_text("# edited after the freeze\n")
    for call in (lambda: M.metrics(r), lambda: M.account_curve(r), lambda: mm.tbars("M5"),
                 lambda: M.run_exec(mm, M.state_exec("1H", np.ones(len(bb), np.int64)), "2024-06-25", "2024-06-30")):
        with pytest.raises(M.HoldOutError):
            call()


def test_a_load_serves_the_data_up_to_the_hold_out_start_only(tmp_path, closed_guard):
    root = tmp_path / "store"
    t = TM.s_of("2024-06-24") + 60 * np.arange(12 * 1440, dtype=np.int64)
    for (y, mo) in ((2024, 6), (2024, 7)):
        a, z = TM.s_of(f"{y}-{mo:02d}-01"), TM.s_of(f"{y}-{mo + 1:02d}-01")
        sel = (t >= a) & (t < z)
        d = root / "BTCUSDm" / f"{y:04d}_{mo:02d}"
        d.mkdir(parents=True)
        p = 60000.0 + np.arange(sel.sum())
        np.savez(d / "m1.npz", t=t[sel], o=p, h=p + 5, l=p - 5, c=p, ask_c=p + 10, spread_mean=np.full(len(p), 10.0),
                 spread_max=np.full(len(p), 12.0), n=np.full(len(p), 3, np.int64))
        (d / "meta.json").write_text('{"first": "%s", "last": "%s"}' % (TM.utc(t[sel][0]), TM.utc(t[sel][-1])))
    m = M.load("BTCUSDm", store_dir=root)
    assert m.end_s == M.CUT_S and int(m.t[-1]) == M.CUT_S - 60 and isinstance(m, TM.TMarket)
    with pytest.raises(M.HoldOutError):
        M.load("BTCUSDm", end="2024-07-01 00:01", store_dir=root)
    with pytest.raises(ValueError):
        M.load("BTCUSDm", end="2026-12-01", store_dir=root)
    freeze(closed_guard)
    freeze(closed_guard.parent / "study1")
    m = M.load("BTCUSDm", end="2024-07-05", store_dir=root)
    assert int(m.t[-1]) == TM.s_of("2024-07-05") - 60


# ───────────────────────────── (b) bars ─────────────────────────────

def test_b_m5_m15_bars_carry_study_1s_tick_volume_and_spread():
    g = gold_like(days=6)
    m = M.TMarket2("XAUUSDm", g)
    t, n = g["t"], g["n"]
    for tf, sec in (("M5", 300), ("M15", 900)):
        b = m.tbars(tf)
        ref = pd.Series(n).groupby(t // sec).sum()
        assert np.array_equal(b.vol, ref.to_numpy()) and np.array_equal(b.t, ref.index.to_numpy() * sec)
        assert np.array_equal(b.tc, b.t + sec) and np.array_equal(b.ex, np.searchsorted(t, b.tc))
        w = pd.Series(g["spread_mean"] * n).groupby(t // sec).sum().to_numpy() / ref.to_numpy()
        assert np.allclose(b.spread, w, rtol=1e-12) and b.m1_t is m.t and b.tf == tf
    for tf in ("1H", "4H", "1D"):
        b1 = TM.TMarket("XAUUSDm", g).tbars(tf)
        b2 = m.tbars(tf)
        for f in ("t", "tc", "i0", "i1", "ex", "o", "h", "l", "c", "vol", "spread", "n_m1", "complete"):
            assert np.array_equal(getattr(b1, f), getattr(b2, f), equal_nan=True), (tf, f)
    with pytest.raises(ValueError):
        m.tbars("2H")
    with pytest.raises(ValueError):
        m.costed(1.5).tbars("M5")


def test_b_weekly_bars_are_iso_weeks_of_the_merged_daily_bars():
    g = gold_like(days=29, start="2019-03-03")                 # Sunday 3 March .. Sunday 31 March (22:05)
    m = M.TMarket2("XAUUSDm", g)
    d, w = m.tbars("1D"), m.tbars("1W")
    # gold's Sunday session is merged into Monday: each week's first daily bar opens on the Sunday
    assert all(pd.Timestamp(x, unit="s").dayofweek == 6 for x in w.t)
    assert all(pd.Timestamp(x - 1, unit="s").dayofweek == 4 for x in w.tc)       # closes after Friday
    assert len(w) == 4 and np.array_equal(w.i0[1:], w.i1[:-1] + 1)
    for i in range(len(w)):
        inside = (d.i0 >= w.i0[i]) & (d.i1 <= w.i1[i])
        assert inside.sum() == 5 and w.h[i] == d.h[inside].max() and w.l[i] == d.l[inside].min()
        assert w.o[i] == d.o[inside][0] and w.c[i] == d.c[inside][-1] and w.vol[i] == d.vol[inside].sum()
    # BTC around the clock: Monday 00:00 to Monday 00:00
    mb = M.TMarket2("BTCUSDm", btc_like(days=21, start="2019-03-04"))
    wb = mb.tbars("1W")
    assert list(wb.t) == [TM.s_of("2019-03-04") + 7 * DAY * i for i in range(3)] and np.all(wb.tc - wb.t == 7 * DAY)
    v = TM.htf_at(wb, np.arange(3.0), mb.tbars("1D"))
    assert np.isnan(v[:6]).all() and v[6] == 0.0 and v[13] == 1.0             # the last CLOSED week
    # data that end inside a week: that week closes at its ISO end, so nothing reads it as closed
    mc = M.TMarket2("BTCUSDm", btc_like(days=17, start="2019-03-04"))           # ends Thursday 21 March
    wc = mc.tbars("1W")
    assert wc.tc[-1] == TM.s_of("2019-03-25") and not wc.complete[-1] and wc.complete[:-1].all()
    assert wc.ex[-1] == len(mc) and TM.htf_at(wc, np.arange(3.0), mc.tbars("1D"))[-1] == 1.0
    # the dashboard module's own weekly row is the same construction
    MS = pytest.importorskip("backtesting.research.tradeiq2_ind_msd")
    for mm in (m, mb, mc):
        ref = MS.weekly_bars(mm.tbars("1D"), end_s=mm.end_s)
        ww = mm.tbars("1W")
        for f in ("t", "tc", "o", "h", "l", "c"):
            assert np.array_equal(getattr(ref, f), getattr(ww, f)), f


def test_b_htf_values_at_the_close_and_at_the_open_of_the_lower_bar():
    o = 100.0 + 0.01 * np.arange(6 * 60)
    m = market(o)
    m5, h1 = m.tbars("M5"), m.tbars("1H")
    v = np.arange(6.0)
    at_close, at_open = M.htf_at(h1, v, m5), M.htf_at_open(h1, v, m5)
    # the M5 bar 00:55-01:00 closes with the first hour: it reads it at its close, not at its open
    assert np.isnan(at_close[10]) and at_close[11] == 0.0 and np.isnan(at_open[11]) and at_open[12] == 0.0
    assert at_close[23] == 1.0 and at_open[23] == 0.0


# ───────────────────────────── (c) the New York clock ─────────────────────────────

def test_c_new_york_clock_with_daylight_saving_and_session_hunters_day_key():
    winter, summer = TM.s_of("2019-03-08 14:30"), TM.s_of("2019-03-11 13:30")    # both 09:30 New York
    assert list(M.ny_minute([winter, summer])) == [570, 570]
    assert list(M.ny_weekday([winter, summer])) == [4, 0]
    assert M.ny_date(TM.s_of("2019-03-11 03:59"))[()] == M.ny_date(TM.s_of("2019-03-10 12:00"))[()]
    # Session Hunter's day starts at 20:00 New York: 00:59 / 01:00 UTC in winter, 23:59 / 00:00 UTC in summer
    w1, w2 = TM.s_of("2019-01-08 00:59"), TM.s_of("2019-01-08 01:00")
    s1, s2 = TM.s_of("2019-07-08 23:59"), TM.s_of("2019-07-09 00:00")
    dk = M.sh_day_key([w1, w2, s1, s2])
    assert dk[1] == dk[0] + 1 and dk[3] == dk[2] + 1
    assert dk[1] == TM.s_of("2019-01-08") // DAY and dk[3] == TM.s_of("2019-07-09") // DAY
    assert M.utc_of_ny(TM.s_of("2019-07-09") // DAY, 570)[()] == TM.s_of("2019-07-09 13:30")
    assert M.utc_of_ny(TM.s_of("2019-01-09") // DAY, 570)[()] == TM.s_of("2019-01-09 14:30")
    assert M.utc_of_ny(TM.s_of("2019-03-10") // DAY, 150)[()] == -1                # 02:30 does not exist that day
    ctx = M.Context(M.TMarket2("BTCUSDm", btc_like(days=3)))
    ny = ctx.ny("M15")
    # Monday 00:00 UTC is Sunday 19:00 New York: still Sunday's Session Hunter day (it turns at 20:00)
    assert ny["minute"][0] == (19 * 60) and ny["weekday"][0] == 6 and ny["day_key"][0] == TM.s_of("2019-03-03") // DAY
    assert ny["day_key"][4] == TM.s_of("2019-03-04") // DAY and ny["day_key_weekday"][4] == 0


# ───────────────────────────── (d) Binance 5m ─────────────────────────────

def _kline_zip(path, slots, vol, us=False, off=0):
    lines = []
    for s, v in zip(slots, vol):
        ot = int(s) * 1000 + off
        ct = int(s) * 1000 + 299_999
        if us:
            ot, ct = ot * 1000, ct * 1000 + 999
        lines.append(f"{ot},100.0,101.0,99.0,100.5,{v:.8f},{ct},{v * 100:.8f},{int(v * 10)},0,0,0")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(path.name.replace(".zip", ".csv"), "\n".join(lines))


def test_d_binance_5m_volume_on_m5_and_m15_bars(tmp_path):
    t = T0 + 60 * np.arange(2 * 1440, dtype=np.int64)
    t = t[~((t >= T0 + 3600) & (t < T0 + 3600 + 600))]                          # our hole 01:00-01:10
    k = len(t)
    m = M.TMarket2("BTCUSDm", m1_dict(np.full(k, 4000.0), sp=10.0, t=t))
    slots = T0 + 300 * np.arange(2 * 288)
    vol = 1.0 + np.arange(len(slots), dtype=np.float64)
    keep = slots != T0 + 7 * 300                                                # Binance lacks 00:35
    root = tmp_path / "binance"
    _kline_zip(root / "spot" / "monthly" / M.BINANCE_PATH_5M / "BTCUSDT-5m-2019-03.zip", slots[keep], vol[keep],
               us=True)
    kl = M.load_binance_5m(end=T0 + 2 * DAY, start=T0, root=root)
    assert np.array_equal(kl["t"], slots[keep]) and not kl["off_grid"].any()
    v5, miss5 = M.binance_volume_5m(m, "M5", root=root)
    b5 = m.tbars("M5")
    want = np.where(b5.t == T0 + 7 * 300, 0.0, 1.0 + (b5.t - T0) // 300)
    assert np.array_equal(v5, want) and miss5.sum() == 1
    v15, miss15 = M.binance_volume_5m(m, "M15", root=root)
    b15 = m.tbars("M15")
    own = np.searchsorted(b15.t, b5.t, side="right") - 1
    assert np.array_equal(v15, np.bincount(own, weights=v5, minlength=len(b15))) and miss15.sum() == 1
    assert v15[4] == vol[12:15].sum() - vol[12:14].sum()                       # 01:00 bar: only 01:10's M5 bar
    assert np.array_equal(M.Context(m).volume("M5", source="tick"), b5.vol)


def test_d_binance_5m_klines_off_the_grid_are_floored_to_their_slot(tmp_path):
    slots = T0 + 300 * np.arange(6)
    root = tmp_path / "b"
    _kline_zip(root / "spot" / "monthly" / M.BINANCE_PATH_5M / "BTCUSDT-5m-2019-03.zip", slots, np.ones(6),
               off=194_789)
    kl = M.load_binance_5m(end=T0 + DAY, start=T0, root=root)
    assert np.array_equal(kl["t"], slots) and kl["off_grid"].all()
    with pytest.raises(M.HoldOutError):
        M.load_binance_5m(end="2024-07-02", root=root)


# ───────────────────────────── types and checks ─────────────────────────────

def test_bad_inputs_are_refused():
    o, h, l = flat()
    m = market(o, h, l)
    with pytest.raises(ValueError):
        M.entries([0], [2])
    with pytest.raises(ValueError):
        M.entries([0], [1], stop_level=99.0, stop_dist=1.0)
    with pytest.raises(ValueError):
        M.entries([0], [1], target_r=2.0, target_level=101.0)
    with pytest.raises(ValueError):
        M.entries([3], [1], exit_bar=3)
    with pytest.raises(ValueError):
        M.orders([0], T0 + DAY)
    with pytest.raises(ValueError):
        M.orders([0], T0 + DAY, buy=100.5, buy_stop=100.6)
    with pytest.raises(ValueError):
        M.event_exec("1H")
    with pytest.raises(ValueError):
        run6(m, M.event_exec("1H", entries=M.entries([9], [1])))
    with pytest.raises(ValueError):
        run6(m, M.event_exec("1H", entries=M.entries([0], [1]), exit_long=np.zeros(5, bool)))
    with pytest.raises(TypeError):
        M.run_exec(m.costed(1.5), M.event_exec("1H", entries=M.entries([0], [1])), T0, T0 + 3600)
    with pytest.raises(ValueError):
        M.run_exec(m, M.event_exec("1H", orders=M.orders([0, 0], T0 + DAY, buy=101.0)), T0, int(m.t[-1]) + 60)
    with pytest.raises(ValueError):
        M.lanes_exec([])
    ctx = M.Context(m)
    calls = []
    f = lambda: calls.append(1) or np.arange(3)
    a1 = ctx.get("mod", "1H", {"a": 1, "b": [1, 2]}, f)
    a2 = ctx.get("mod", "1H", {"b": (1, 2), "a": 1}, f)
    assert a1 is a2 and calls == [1]
    with pytest.raises(TypeError):
        ctx.get("mod", "1H", {"x": np.arange(2)}, f)
    assert M.Variant("v", "XAUUSDm", "1H", "RIB", "RIB", params={"f": "F0"}).ident()["params"] == '{"f": "F0"}'


# ───────────────────────────── real data (read up to the hold-out start; skipped when absent) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cache = {}
    d2 = tmp_path_factory.mktemp("closed_study2")

    def get(symbol, end):
        key = (symbol, end)
        if key not in cache:
            months = store.available_months(symbol)
            if (2019, 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(M, "STUDY_DIR", d2)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                cache[key] = M.load(symbol, end=end)
        return cache[key]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_m5_m15_bars_are_the_stores_resampled_bars_and_do_not_look_ahead(symbol, real):
    full, cut = real(symbol, "2019-07-01"), real(symbol, "2019-04-17 13:37")
    assert full.end_s == TM.s_of("2019-07-01")
    if symbol == "XAUUSDm" and all((2016, mo) in store.available_months(symbol) for mo in range(1, 13)):
        assert int(full.t[0]) < TM.s_of("2016-01-05")                         # the 2016 warm-up is loaded
    m1 = {"t": full.t, "o": full.o, "h": full.h, "l": full.l, "c": full.c, "ask_c": full.c + full.sp,
          "spread_mean": full.sp, "spread_max": full.sp, "n": full.n}
    T_s = TM.s_of("2019-04-17 13:37")
    for tf, sec in (("M5", 300), ("M15", 900)):
        ref = store.resample_bars(m1, sec)
        b = full.tbars(tf)
        assert np.array_equal(b.t, ref["t"]) and np.array_equal(b.vol, ref["n"]) and np.array_equal(b.c, ref["c"])
        assert np.allclose(b.spread, ref["spread_mean"], rtol=1e-9)
    for tf in ("M5", "M15", "1W"):
        bf, bc = full.tbars(tf), cut.tbars(tf)
        n = int(np.sum(bc.tc <= T_s))
        assert n > 10
        for f in ("t", "tc", "i0", "i1", "ex", "o", "h", "l", "c", "vol", "spread", "n_m1"):
            assert np.array_equal(getattr(bf, f)[:n], getattr(bc, f)[:n]), (tf, f)
    # the definition: a daily bar belongs to the ISO week of its last day; weeks are those groups, in order
    w, d = full.tbars("1W"), full.tbars("1D")
    iso = lambda tc: ((tc - 1) // DAY + 3) // 7
    own = np.searchsorted(w.i0, d.i0, side="right") - 1
    assert np.all(own >= 0) and np.array_equal(iso(d.tc), iso(w.tc)[own]) and np.all(np.diff(iso(w.tc)) > 0)
    assert np.array_equal(w.i0, d.i0[np.flatnonzero(np.diff(own, prepend=-1))])


@pytest.mark.parametrize("symbol", SYMS)
def test_real_the_event_engine_is_study_1s_run_on_a_placeholder_state(symbol, real):
    """A random placeholder state (not a rule of the study): the event engine gives study 1's trades exactly on real
    bars (weekends, gold's daily break, data holes). Only the identity is checked; no result is reported."""
    mk = real(symbol, "2021-01-01")
    for tf in ("1H", "4H"):
        b = mk.tbars(tf)
        st = _random_states(len(b), 17)
        stop = TM.s1_stop(b)
        for cost in (1.0, 1.5):
            r1 = TM.run(mk, b, st, "2019-01-01", "2021-01-01", stop=stop, cost=cost)
            r2 = M.run_exec(mk, M.state_exec(tf, st, stop, exit_long=np.zeros(len(b), bool)), "2019-01-01",
                            "2021-01-01", cost)
            assert rows(r2) == rows(r1) and r2.net == r1.net and r2.max_dd == r1.max_dd
            assert np.array_equal(r2.ec, r1.ec)


def test_real_binance_5m_check_passes(real):
    files = M._binance_files_5m()
    if not all(p.exists() for _, a, _, _, p in files if a < TM.s_of("2019-07-01")):
        pytest.skip("the Binance 5m files are not on this machine")
    mk = real("BTCUSDm", "2019-07-01")
    chk = M.binance_check_5m(mk)
    assert chk["passes"] and chk["corr_close"] > 0.999 and chk["best_lag_bars"] == 0
    assert chk["matched"] + chk["exness_bars_without_kline"] <= chk["exness_m5_bars"]
    v5, miss5 = M.binance_volume(mk, "M5")
    v15, miss15 = M.binance_volume(mk, "M15")
    b15 = mk.tbars("M15")
    inside = mk.tbars("M5").i1 <= b15.i1[-1]
    assert v15.sum() == pytest.approx(v5[inside].sum(), rel=1e-12) and miss15.sum() == miss5[inside].sum()
    v1w, _ = M.binance_volume(mk, "1W")
    assert len(v1w) == len(mk.tbars("1W")) and np.all(v1w >= 0)
