"""
The TradeIQ study's data and execution harness (``backtesting/research/tradeiq_market.py``).

(a) external.py's own pure-state strategies give the same trades and P/L, to the cent, through the adapter as through
    external.py's path, on a real Development window of gold and BTC (and the same account curve).
(b) No look-ahead: bars and results up to a time T do not change when the data after T is removed (real data).
(c) Hand-made bars: a buy fills at the next M1 open at the ask, a sell at the bid; a stop inside a bar fills at the stop
    and a gap through it at the open, each one spread worse; x1.5 costs; DEVIATIONS 1-4 and 7.
(d) The hold-out guard refuses anything past 2024-06-30 23:59:59 UTC and opens only with a FINALISTS.md whose sha256
    matches (written in tmp_path only).
(e) The tick volume of a bar is the sum of its M1 tick counts (hand-made and real bars).
Also: the per-unit marks against external's account kernel, every score on a hand-built run, the account curve with
the unit rule, the Binance volume (ms and microsecond stamps, alignment, sums, gaps).

Every test runs with the guard pointed at an empty folder, so the real FINALISTS.md is never read; the real-data tests
read data/store and data/raw/binance up to the hold-out start only, and are skipped when those are absent.
"""

from __future__ import annotations

import hashlib
import io
import math
import zipfile

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq_market as TM

DAY = 86400
T0 = TM.s_of("2019-03-04")          # a Monday, 00:00 UTC
SYMS = ("XAUUSDm", "BTCUSDm")


# ───────────────────────────── fixtures and helpers ─────────────────────────────

@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The study folder seen by the guard: an empty tmp folder (FINALISTS.md absent: the hold-out is closed)."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


def freeze(d, text="# Finalists\n\nFinalists: 0\n"):
    (d / "FINALISTS.md").write_text(text, encoding="utf-8")
    (d / "FINALISTS.md.sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "  FINALISTS.md\n")


def market(o, h=None, l=None, c=None, sp=0.2, t=None, n=None, symbol="XAUUSDm", t0=T0, step=60, end_s=None):
    o = np.asarray(o, np.float64)
    k = len(o)
    c = o.copy() if c is None else np.asarray(c, np.float64)
    h = np.maximum(o, c) + 0.02 if h is None else np.asarray(h, np.float64)
    l = np.minimum(o, c) - 0.02 if l is None else np.asarray(l, np.float64)
    t = t0 + step * np.arange(k, dtype=np.int64) if t is None else np.asarray(t, np.int64)
    spa = np.full(k, float(sp)) if np.isscalar(sp) else np.asarray(sp, np.float64)
    nn = np.ones(k) if n is None else np.asarray(n, np.float64)
    return TM.TMarket(symbol, {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": spa, "n": nn}, end_s)


def ramp(k=360, base=100.0, slope=0.01, **kw):
    """Opens rising by ``slope`` a minute, so every fill bar has its own price."""
    o = base + slope * np.arange(k)
    return o, o + 0.5 * slope


def run1h(m, state, a=T0, z=None, **kw):
    b = m.tbars("1H")
    return TM.run(m, b, np.asarray(state), a, z if z is not None else int(m.t[-1]) + 60, **kw)


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


def same(a: dict, b: dict) -> bool:
    """Two dicts of scores are equal, NaN equal to NaN."""
    if a.keys() != b.keys():
        return False
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


def path_rows(p):
    return [(int(p.dir[i]), int(p.eix[i]), float(p.epx[i]), int(p.xix[i]), float(p.xpx[i]), int(p.why[i]))
            for i in range(len(p))]


# ───────────────────────────── (c) fills on hand-made bars ─────────────────────────────

def test_c_a_buy_fills_at_the_next_m1_open_at_the_ask_a_sell_at_the_bid():
    o, c = ramp(360)
    m = market(o, c=c)
    b = m.tbars("1H")
    assert list(b.tc - T0) == [3600 * i for i in range(1, 7)]
    assert list(b.ex) == [60, 120, 180, 240, 300, 360]              # the first M1 bar at or after each close
    r = run1h(m, [0, 1, 1, 0, 0, 0])
    tr = r.trades
    assert len(tr) == 1
    assert (tr.entry_ix[0], tr.exit_ix[0], tr.reason[0]) == (120, 240, "signal")
    assert tr.entry_time[0] == TM.utc(T0 + 7200)                     # decided at 02:00, filled at the 02:00 open
    assert tr.entry[0] == pytest.approx(o[120] + 0.2)                # a buy pays the ask
    assert tr.exit[0] == pytest.approx(o[240])                       # a sell gets the bid
    assert tr.pnl[0] == pytest.approx(o[240] - o[120] - 0.2)         # gold: 1 USD per 1.00 on 0.01 lot
    r = run1h(m, [0, -1, -1, 0, 0, 0])
    tr = r.trades
    assert tr.entry[0] == pytest.approx(o[120]) and tr.exit[0] == pytest.approx(o[240] + 0.2)
    assert tr.pnl[0] == pytest.approx(o[120] - o[240] - 0.2)
    ob, cb = ramp(360, base=60000.0, slope=3.0)
    mb = market(ob, c=cb, sp=15.0, symbol="BTCUSDm")
    tr = run1h(mb, [0, 1, 1, 0, 0, 0]).trades
    assert tr.pnl[0] == pytest.approx(0.01 * (ob[240] - ob[120] - 15.0))   # BTC: 0.01 USD per 1.00


def test_c_a_flip_fills_both_sides_at_the_first_quote_after_the_close_even_across_a_gap():
    """DEVIATIONS 4: no quote from 02:00 to 02:29; the flip decided at 02:00 fills both sides at the 02:30 open."""
    o, c = ramp(360)
    t = T0 + 60 * np.arange(360)
    keep = ~((t >= T0 + 7200) & (t < T0 + 7200 + 1800))
    m = market(o[keep], c=c[keep], t=t[keep])
    b = m.tbars("1H")
    j = int(np.searchsorted(m.t, T0 + 7200 + 1800))
    assert b.ex[1] == j
    st = np.array([1, -1, -1, -1, -1, -1])
    tr = run1h(m, st).trades
    assert list(tr.side) == [1, -1]
    assert tr.exit_ix[0] == j and tr.entry_ix[1] == j
    assert tr.exit[0] == pytest.approx(m.o[j]) and tr.entry[1] == pytest.approx(m.o[j])
    assert tr.reason[1] == "end" and tr.exit[1] == pytest.approx(m.c[-1] + 0.2)
    # external.py's kernel given decisions stamped at the closes opens the short a bar later (why DEVIATIONS 4 exists)
    p = X.run_path(m, X.make_plan(m, b.tc, want=st, xl=st == -1, xs=st == 1), 0, len(m))
    assert int(p.xix[0]) == j and int(p.eix[1]) == int(b.ex[2])


def test_c_a_stop_inside_a_bar_fills_at_the_stop_one_spread_worse():
    o, c = ramp(360)
    stop = np.full(6, 1.0)
    # long: in at the 02:00 ask o[120] + 0.2, stop 1.00 below; minute 150 dips through it without a gap
    lo = np.minimum(o, c) - 0.02
    lo[150] = o[120] + 0.2 - 1.3
    m = market(o, c=c, l=lo)
    tr = run1h(m, [0, 1, 1, 1, 1, 1], stop=stop).trades
    assert len(tr) == 1                                              # flat afterwards: the state did not change
    s_px = o[120] + 0.2 - 1.0
    assert (tr.exit_ix[0], tr.reason[0]) == (150, "stop")
    assert tr.exit[0] == pytest.approx(s_px - 0.2)                   # the stop price, one spread worse
    assert tr.slippage[0] == pytest.approx(0.2)
    assert tr.pnl[0] == pytest.approx(-1.2)
    # short: in at the bid o[120], stop 1.00 above; a stop of a sell is hit when the ask (high + spread) reaches it
    hi = np.maximum(o, c) + 0.02
    hi[150] = o[120] + 1.0 - 0.2 + 0.05
    m = market(o, c=c, h=hi)
    tr = run1h(m, [0, -1, -1, -1, -1, -1], stop=stop).trades
    assert (tr.exit_ix[0], tr.reason[0]) == (150, "stop")
    assert tr.exit[0] == pytest.approx(o[120] + 1.0 + 0.2)
    assert tr.pnl[0] == pytest.approx(-1.2)


def test_c_a_gap_through_the_stop_fills_at_the_open_one_spread_worse():
    o, c = ramp(360)
    stop = np.full(6, 1.0)
    og, cg = o.copy(), c.copy()
    og[150], cg[150] = 99.0, 99.05                                    # long stop at 100.40, the open gaps to 99.00
    m = market(og, c=cg)
    tr = run1h(m, [0, 1, 1, 1, 1, 1], stop=stop).trades
    assert (tr.exit_ix[0], tr.reason[0]) == (150, "gap stop")
    assert tr.exit[0] == pytest.approx(99.0 - 0.2)
    assert tr.pnl[0] == pytest.approx(99.0 - 0.2 - (o[120] + 0.2))
    og, cg = o.copy(), c.copy()
    og[150], cg[150] = 103.0, 103.05                                  # short stop at 102.20, the ask opens at 103.20
    m = market(og, c=cg)
    tr = run1h(m, [0, -1, -1, -1, -1, -1], stop=stop).trades
    assert (tr.exit_ix[0], tr.reason[0]) == (150, "gap stop")
    assert tr.exit[0] == pytest.approx(103.0 + 0.2 + 0.2)
    assert tr.pnl[0] == pytest.approx(o[120] - 103.4)


def test_c_after_a_stop_the_variant_stays_flat_until_its_state_changes():
    """DEVIATIONS 1: stopped at 01:30; no entry at 02:00-04:00 (still long), flat at 05:00, long again at 06:00."""
    o, c = ramp(480)
    lo = np.minimum(o, c) - 0.02
    lo[90] = o[60] + 0.2 - 2.0
    m = market(o, c=c, l=lo)
    st = np.array([1, 1, 1, 1, 0, 1, 1, 1])
    tr = run1h(m, st, stop=np.full(8, 1.0)).trades
    assert list(zip(tr.entry_ix, tr.exit_ix, tr.reason)) == [(60, 90, "stop"), (360, 479, "end")]
    # a flip after the stop is a change of state: the short enters at that close
    st2 = np.array([1, 1, -1, -1, -1, -1, -1, -1])
    tr = run1h(m, st2, stop=np.array([1.0, 1.0] + [10.0] * 6)).trades          # the stop of each entry's own bar
    assert list(zip(tr.side, tr.entry_ix, tr.reason)) == [(1, 60, "stop"), (-1, 180, "end")]
    # external.py's own state plans re-enter at the next close while the state still says long
    b = m.tbars("1H")
    p = X.run_path(m, X.make_plan(m, b.tc, want=st, xl=st != 1, sl=1.0), 0, len(m))
    assert int(p.eix[1]) == 120


def test_c_a_gap_stop_at_the_open_of_a_flip_is_followed_by_the_new_side():
    """DEVIATIONS 4: the long gaps through its stop at the very open where the flip decided at 02:00 fills."""
    o, c = ramp(360)
    og, cg = o.copy(), c.copy()
    og[120:], cg[120:] = 95.0, 95.0                                   # a drop to 95.00 that stays there
    m = market(og, c=cg)
    tr = run1h(m, [1, -1, -1, -1, -1, -1], stop=np.full(6, 2.0)).trades
    assert list(zip(tr.side, tr.entry_ix, tr.exit_ix, tr.reason)) == [(1, 60, 120, "gap stop"), (-1, 120, 359, "end")]
    assert tr.exit[0] == pytest.approx(95.0 - 0.2) and tr.entry[1] == pytest.approx(95.0)


def test_c_the_window_takes_the_state_of_its_first_bar_and_closes_at_its_end():
    """DEVIATIONS 2, 3, 7: window [02:00, 06:00). Bar 1 closes at 02:00, the window's start: not in it; bar 2's
    close (03:00) is the first decision. The decision of 06:00 is outside; the long is closed at the 05:59 close."""
    o, c = ramp(480)
    m = market(o, c=c)
    st = np.array([0, 1, 1, 1, 1, 1, 1, 0])
    r = run1h(m, st, a=T0 + 7200, z=T0 + 6 * 3600)
    tr = r.trades
    assert list(zip(tr.entry_ix, tr.exit_ix, tr.reason)) == [(180, 359, "end")]
    assert tr.exit[0] == pytest.approx(c[359]) and tr.exit_time[0] == TM.utc(T0 + 6 * 3600)
    assert r.n_decisions == 3                                        # the closes of 03:00, 04:00, 05:00
    tr = run1h(m, -st, a=T0 + 7200, z=T0 + 6 * 3600).trades
    assert tr.exit[0] == pytest.approx(c[359] + 0.2)                 # a short is bought back at the ask
    # external.py's own window convention executes the decision stamped at the start (02:00) inside the window
    b = m.tbars("1H")
    p = X.run_path(m, X.make_plan(m, b.tc, want=st, xl=st != 1), 120, 360)
    assert int(p.eix[0]) == 120


def test_c_costs_x15_widen_every_spread():
    o, c = ramp(360)
    m = market(o, c=c)
    tr = run1h(m, [0, 1, 1, 0, 0, 0], cost=1.5).trades
    assert tr.entry[0] == pytest.approx(o[120] + 0.3) and tr.exit[0] == pytest.approx(o[240])
    tr = run1h(m, [0, -1, -1, -1, -1, -1], cost=1.5).trades
    assert tr.exit[0] == pytest.approx(c[359] + 0.3)
    # the short's stop is hit on the wider ask (high + 0.30) though not on the normal one (high + 0.20)
    f = np.full(360, 100.0)
    hi = f + 0.02
    hi[150] = 100.75
    m = market(f, c=f, h=hi)
    st, stop = [0, -1, -1, -1, -1, -1], np.full(6, 1.0)
    assert list(run1h(m, st, stop=stop).trades.reason) == ["end"]
    tr = run1h(m, st, stop=stop, cost=1.5).trades
    assert (tr.exit_ix[0], tr.reason[0]) == (150, "stop")
    assert tr.exit[0] == pytest.approx(101.0 + 0.3)                  # and the slippage is 1.5 spreads too
    m = market(o, c=c)
    bh = TM.buy_and_hold(m, T0, T0 + 6 * 3600, cost=1.5)
    assert bh["bh_entry"] == pytest.approx(o[0] + 0.3) and bh["bh_exit"] == pytest.approx(c[-1])
    # the market itself keeps its spread
    assert np.all(m.sp == 0.2) and m.costed(1.5).cost == 1.5 and m.costed(1.5).t is m.t


def test_c_bad_inputs_are_refused():
    o, c = ramp(360)
    m, m2 = market(o, c=c), market(o, c=c)
    b = m.tbars("1H")
    with pytest.raises(ValueError):
        TM.run(m, b, [0, 1, 1, 0, 0], T0, T0 + 6 * 3600)                     # wrong length
    with pytest.raises(ValueError):
        TM.run(m, b, [0, 1, 2, 0, 0, 0], T0, T0 + 6 * 3600)                  # not a state
    with pytest.raises(ValueError):
        TM.run(m, b, [0, 1, np.nan, 0, 0, 0], T0, T0 + 6 * 3600)
    with pytest.raises(ValueError):
        TM.run(m2, b, [0, 1, 1, 0, 0, 0], T0, T0 + 6 * 3600)                 # bars of another market
    with pytest.raises(ValueError):
        TM.run(m, b, [0, 1, 1, 0, 0, 0], T0, T0 + 7 * 3600)                  # past the data held
    with pytest.raises(ValueError):
        TM.run(m, b, [0, 1, 1, 0, 0, 0], T0, T0 + 6 * 3600, stop=np.array([1, np.nan, 1, 1, 1, 1.0]))
    with pytest.raises(TypeError):
        TM.run(m.costed(1.5), b, [0, 1, 1, 0, 0, 0], T0, T0 + 6 * 3600)
    with pytest.raises(ValueError):
        m.costed(1.5).tbars("1H")


# ───────────────────────────── marks, scores, account ─────────────────────────────

@pytest.mark.parametrize("cost", [1.0, 1.5])
def test_unit_marks_are_external_account_kernels_marks_at_one_unit(cost):
    m = TM.TMarket("XAUUSDm", gold_like())
    b = m.tbars("1H")
    rng = np.random.default_rng(3)
    st = np.where(np.cumsum(rng.random(len(b)) < 0.15) % 3 == 0, 1, np.where(np.cumsum(rng.random(len(b)) < 0.1) % 2, -1, 0))
    a, z = TM.s_of("2019-03-11"), TM.s_of("2019-04-10")
    r = TM.run(m, b, st, a, z, stop=TM.s1_stop(b, 2.0), cost=cost)
    p, cm = r.path, r.m
    assert len(p) > 20 and (r.trades.reason.isin(["stop", "gap stop"])).sum() > 2
    e = TM._edges_days(a, z)
    bnd = r.ia + np.searchsorted(cm.t[r.ia:r.iz], e[1:-1])
    big = 1e9
    steps, pnl, bal, dd, wiped, _, n_done, eqb = X._account_kernel(
        cm.t, cm.o, cm.h, cm.l, cm.c, cm.sp, cm.k, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why, p.risk, p.expo, p.leg0,
        p.nleg, p.leix, p.lepx, 0, 0.0, 0.0, False, bnd.astype(np.int64), X._YEARS, big, 2500.0, 1.0)
    assert np.all(steps == 1) and not wiped and n_done == len(p)
    assert np.allclose(pnl, r.trades.pnl, atol=1e-9, rtol=0)
    assert bal - big == pytest.approx(r.net, abs=1e-5)
    assert np.allclose(eqb - big, TM.eq_at(r, e[1:-1]), atol=1e-5, rtol=0)
    assert r.max_dd == pytest.approx(dd * big, rel=1e-5)               # the same drawdown, in dollars
    assert r.net == pytest.approx(float(r.trades.pnl.sum()), abs=1e-9)


def _hand_run():
    """Hourly quotes from 2019-01-01 to 2019-07-01, no spread, price 100 with four steps; four trades of known P/L."""
    t = TM.s_of("2019-01-01") + 3600 * np.arange(181 * 24, dtype=np.int64)
    steps = [("2019-02-01", 10.0), ("2019-03-01", -4.0), ("2019-05-01", 6.0), ("2019-06-15", 2.0)]
    p = np.full(len(t), 100.0)
    for when, d in steps:
        p[t >= TM.s_of(when)] += d
    m = market(p, h=p, l=p, c=p, sp=0.0, t=t, end_s=TM.s_of("2019-07-01"))
    b = m.tbars("1H")
    tc = b.tc
    s = lambda a, z: (tc >= TM.s_of(a)) & (tc < TM.s_of(z))
    st = np.zeros(len(b), np.int64)
    st[s("2019-01-15", "2019-02-15") | s("2019-02-20", "2019-03-10") | (tc >= TM.s_of("2019-06-01"))] = 1
    st[s("2019-04-10", "2019-05-10")] = -1
    return m, TM.run(m, b, st, "2019-01-01", "2019-07-01")


def test_scores_on_a_hand_built_run():
    m, r = _hand_run()
    tr = r.trades
    assert list(np.round(tr.pnl, 9)) == [10.0, -4.0, -6.0, 2.0] and list(tr.side) == [1, 1, -1, 1]
    last = 720.0 - 1.0 + 1.0 / 60.0               # closed at the close of the last quote, 2019-06-30 23:00 + 1 min
    assert np.allclose(tr.hold_h, [744.0, 432.0, 720.0, last])
    s = TM.metrics(r)
    assert s["net"] == 2.0 and s["trades"] == 4 and s["win_rate"] == 50.0 and s["profit_factor"] == 1.2
    assert (s["avg_win"], s["avg_loss"], s["worst_trade"], s["best_trade"]) == (6.0, -5.0, -6.0, 10.0)
    assert s["max_dd"] == pytest.approx(10.0) and s["profit_dd"] == pytest.approx(0.2)
    assert (s["n_q"], s["pos_q"], s["pos_q_share"], s["n_q_exposed"]) == (2, 1, 0.5, 2)
    assert s["blocks"] == "+6 -4" and s["losing_blocks"] == 1
    assert s["max_losing_streak"] == 2 and s["avg_hold_h"] == pytest.approx((744 + 432 + 720 + last) / 4)
    assert s["time_in_mkt"] == pytest.approx((744 + 432 + 720 + 720) / len(m))
    assert (s["n_long"], s["n_short"], s["long_pnl"], s["short_pnl"]) == (3, 1, 8.0, -6.0)
    wk = np.zeros(27)
    wk[[4, 8, 17, 24]] = [10.0, -4.0, -6.0, 2.0]                     # weeks from Saturday 00:00 UTC
    starts, got = TM.weekly_pnl(r)
    assert np.allclose(got, wk) and TM.utc(starts[1]) == pd.Timestamp("2019-01-05", tz="UTC")
    assert s["weeks"] == 27 and s["sharpe_w"] == pytest.approx(wk.mean() / wk.std(ddof=1) * math.sqrt(52))
    q0, qp, held = TM.quarter_pnl(r)
    assert list(qp) == [6.0, -4.0] and list(held) == [True, True]
    bh = TM.buy_and_hold(m, "2019-01-01", "2019-07-01")
    assert bh["bh_net"] == pytest.approx(14.0) and bh["bh_max_dd"] == pytest.approx(4.0)
    uc = TM.unit_curve(r)
    assert uc.equity.iloc[-1] == pytest.approx(2.0) and uc.equity.max() == pytest.approx(10.0)


def test_the_account_curve_uses_the_bots_unit_rule_and_is_wiped_at_zero():
    t = T0 + 3600 * np.arange(12, dtype=np.int64)
    p = np.array([1000, 1000, 1000, 1700, 1700, 1700, 2000, 2000, 2000, 300, 300, 300], np.float64)
    m = market(p, h=p + 0.1, l=p - 0.1, c=p, sp=0.2, t=t)
    b = m.tbars("1H")
    st = np.array([1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1])
    r = TM.run(m, b, st, int(t[0]), int(t[-1]) + 60)
    assert list(np.round(r.trades.pnl, 6)) == [699.8, 299.8, -1700.2]
    curve, acc = TM.account_curve(r)
    # 1 unit at $2,000; 2 units once the balance passed $2,500 (floor(2699.8 / 2500) + 1); wiped on the third
    assert acc["wiped"] and acc["final"] == 0.0 and acc["trades"] == 3
    res = X.account(r.m, r.path, X.BOT, np.asarray([r.ia, r.iz]))
    assert list(np.round(res.trades_pnl[:2], 6)) == [699.8, 599.6] and res.trades_pnl[2] == pytest.approx(-(2000 + 699.8 + 599.6))
    assert curve.equity.iloc[0] == 2000.0 and curve.equity.iloc[-1] == 0.0


def test_htf_values_are_those_of_the_last_closed_higher_bar():
    o, c = ramp(12 * 60)
    m = market(o, c=c)
    h1, h4 = m.tbars("1H"), m.tbars("4H")
    v = TM.htf_at(h4, [10.0, 20.0, 30.0], h1)
    assert list(np.nan_to_num(v, nan=-1)) == [-1, -1, -1, 10, 10, 10, 10, 20, 20, 20, 20, 30]


# ───────────────────────────── (e) tick volume ─────────────────────────────

def test_e_tick_volume_is_the_sum_of_the_m1_tick_counts_hand_made():
    g = gold_like(days=15)
    m = TM.TMarket("XAUUSDm", g)
    t, n = g["t"], g["n"]
    for tf, sec in (("1H", 3600), ("4H", 14400)):
        b = m.tbars(tf)
        ref = pd.Series(n).groupby(t // sec).sum()
        assert np.array_equal(b.vol, ref.to_numpy()) and np.array_equal(b.t, ref.index.to_numpy() * sec)
        assert np.array_equal(b.n_m1, pd.Series(n).groupby(t // sec).size().to_numpy())
        w = pd.Series(g["spread_mean"] * n).groupby(t // sec).sum().to_numpy() / ref.to_numpy()
        assert np.allclose(b.spread, w, rtol=1e-12)
    d = m.tbars("1D")
    # Sunday's two hours of quotes are merged into Monday: the Monday bar holds their ticks too
    sunday = (((t // DAY) + 4) % 7) == 0
    mon = int(np.flatnonzero(d.t == (t[sunday][0] // DAY) * DAY)[0])
    days = (t // DAY)
    expect = n[(days >= d.t[mon] // DAY) & (days < d.tc[mon] // DAY)].sum()
    assert d.vol[mon] == expect and d.tc[mon] - d.t[mon] == 2 * DAY
    assert d.vol.sum() == n[: d.i1[-1] + 1].sum()


# ───────────────────────────── (d) the hold-out guard ─────────────────────────────

def _m1_month(t, price=2300.0):
    k = len(t)
    p = price + 0.01 * np.arange(k)
    return {"t": t, "o": p, "h": p + 0.05, "l": p - 0.05, "c": p, "ask_c": p + 0.2, "spread_mean": np.full(k, 0.2),
            "spread_max": np.full(k, 0.3), "n": np.full(k, 7, np.int64)}


def _tmp_store(root, symbol="XAUUSDm"):
    """June 24 - July 5 2024 around the clock in a store of its own."""
    t = TM.s_of("2024-06-24") + 60 * np.arange(12 * 1440, dtype=np.int64)
    for (y, mo) in ((2024, 6), (2024, 7)):
        a, z = TM.s_of(f"{y}-{mo:02d}-01"), TM.s_of(f"{y}-{mo + 1:02d}-01")
        sel = (t >= a) & (t < z)
        d = root / symbol / f"{y:04d}_{mo:02d}"
        d.mkdir(parents=True)
        np.savez(d / "m1.npz", **{k: v[sel] for k, v in _m1_month(t).items()})
    return t


def test_d_the_guard_refuses_the_hold_out_while_finalists_md_is_missing(tmp_path, closed_guard):
    assert not TM.finalists_frozen()
    TM._guard(TM.CUT_S, "up to the cut")                                     # 2024-06-30 23:59:59.999 is open
    with pytest.raises(TM.HoldOutError):
        TM._guard(TM.CUT_S + 1, "one second past")
    t = _tmp_store(tmp_path / "store")
    # loading: the default stops at the cut; asking past it raises before anything is read
    m = TM.load("XAUUSDm", store_dir=tmp_path / "store")
    assert m.end_s == TM.CUT_S and int(m.t[-1]) == TM.CUT_S - 60
    with pytest.raises(TM.HoldOutError):
        TM.load("XAUUSDm", end="2024-07-01 00:01", store_dir=tmp_path / "store")
    # a market holding minutes past the cut cannot be built
    with pytest.raises(TM.HoldOutError):
        TM.TMarket("XAUUSDm", _m1_month(t))
    # a window past the cut, on a market that ends at it
    b = m.tbars("1H")
    st = np.ones(len(b), np.int64)
    TM.run(m, b, st, "2024-06-25", "2024-07-01")
    with pytest.raises(TM.HoldOutError):
        TM.run(m, b, st, "2024-06-25", "2024-07-01 00:00:01")
    with pytest.raises(TM.HoldOutError):
        TM.buy_and_hold(m, "2024-06-25", "2024-07-02")
    with pytest.raises(TM.HoldOutError):
        TM.load_binance(end="2024-07-02", root=tmp_path / "binance")
    # the real FINALISTS.md is never consulted here: the guard reads the tmp study folder
    assert TM.STUDY_DIR == closed_guard


def test_d_the_guard_opens_only_with_a_frozen_finalists_md(tmp_path, closed_guard):
    t = _tmp_store(tmp_path / "store")
    (closed_guard / "FINALISTS.md").write_text("Finalists: 1\n")
    assert not TM.finalists_frozen()                                          # no sha256 file
    (closed_guard / "FINALISTS.md.sha256").write_text("0" * 64 + "\n")
    assert not TM.finalists_frozen()                                          # a wrong hash
    freeze(closed_guard)
    assert TM.finalists_frozen()
    m = TM.load("XAUUSDm", end="2024-07-05", store_dir=tmp_path / "store")
    assert int(m.t[-1]) == TM.s_of("2024-07-05") - 60 and m.end_s == TM.s_of("2024-07-05")
    mm = TM.TMarket("XAUUSDm", _m1_month(t))
    b = mm.tbars("1H")
    r = TM.run(mm, b, np.ones(len(b), np.int64), "2024-06-25", "2024-07-05")
    s = TM.metrics(r)
    assert s["trades"] == 1
    TM.account_curve(r)
    # the file changes after the freeze: everything holding hold-out data is refused again
    (closed_guard / "FINALISTS.md").write_text("# Finalists (edited)\n")
    assert not TM.finalists_frozen()
    for call in (lambda: TM.metrics(r), lambda: TM.account_curve(r), lambda: mm.tbars("4H"),
                 lambda: TM.run(mm, b, np.ones(len(b), np.int64), "2024-06-25", "2024-06-30"),
                 lambda: TM.eq_at(r, [TM.CUT_S]),
                 lambda: TM.load("XAUUSDm", end="2024-07-05", store_dir=tmp_path / "store")):
        with pytest.raises(TM.HoldOutError):
            call()


# ───────────────────────────── Binance volume (hand-made files) ─────────────────────────────

def _kline_zip(path, hours, vol, us=False):
    lines = []
    for h, v in zip(hours, vol):
        ot = int(h) * 1000
        ct = ot + 3_599_999
        if us:
            ot, ct = ot * 1000, ct * 1000 + 999
        lines.append(f"{ot},100.0,101.0,99.0,100.5,{v:.8f},{ct},{v * 100:.8f},{int(v * 10)},0,0,0")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(path.name.replace(".zip", ".csv"), "\n".join(lines))


def test_binance_reads_millisecond_and_microsecond_stamps(tmp_path):
    hours = TM.s_of("2025-01-01") + 3600 * np.arange(5)
    _kline_zip(tmp_path / "ms.zip", hours, np.arange(1, 6.0))
    _kline_zip(tmp_path / "us.zip", hours, np.arange(1, 6.0), us=True)
    a, b = TM.read_klines(tmp_path / "ms.zip"), TM.read_klines(tmp_path / "us.zip")
    assert np.array_equal(a["open_ms"], hours * 1000) and np.array_equal(b["open_ms"], hours * 1000)
    assert int(a["us_rows"]) == 0 and int(b["us_rows"]) == 5
    assert np.array_equal(b["close_ms"], hours * 1000 + 3_599_999) and np.allclose(b["volume"], np.arange(1, 6.0))


def test_binance_volume_is_aligned_on_our_1h_bars_and_summed_on_our_bars(tmp_path):
    # BTC around the clock 2019-03-04 .. 07 with a five-hour hole on the 5th; Binance lacks 2019-03-04 07:00
    t = T0 + 60 * np.arange(4 * 1440, dtype=np.int64)
    t = t[~((t >= T0 + DAY + 10 * 3600) & (t < T0 + DAY + 15 * 3600))]
    k = len(t)
    m = TM.TMarket("BTCUSDm", {"t": t, "o": np.full(k, 4000.0), "h": np.full(k, 4001.0), "l": np.full(k, 3999.0),
                               "c": np.full(k, 4000.0), "spread_mean": np.full(k, 10.0), "n": np.ones(k)})
    hours = T0 + 3600 * np.arange(4 * 24)
    vol = 1.0 + np.arange(len(hours), dtype=np.float64)
    keep = hours != T0 + 7 * 3600
    root = tmp_path / "binance"
    _kline_zip(root / "spot" / "monthly" / TM.BINANCE_PATH / "BTCUSDT-1h-2019-03.zip", hours[keep], vol[keep], us=True)
    v1, miss1 = TM.binance_volume(m, "1H", root=root)
    h1 = m.tbars("1H")
    assert len(h1) == 4 * 24 - 5
    want = np.where(h1.t == T0 + 7 * 3600, 0.0, 1.0 + (h1.t - T0) // 3600)
    assert np.array_equal(v1, want) and miss1.sum() == 1 and miss1[7] == 1
    for tf in ("4H", "1D"):
        v, miss = TM.binance_volume(m, tf, root=root)
        hb = m.tbars(tf)
        own = np.searchsorted(hb.t, h1.t, side="right") - 1
        assert np.array_equal(v, np.bincount(own, weights=v1, minlength=len(hb)))
        assert miss.sum() == 1
    d1, _ = TM.binance_volume(m, "1D", root=root)
    assert d1[1] == vol[24:48].sum() - vol[24 + 10:24 + 15].sum()           # the hours of our hole belong to no bar


# ───────────────────────────── real data: (a), (b), (e), stops, Binance ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cache = {}
    closed = tmp_path_factory.mktemp("closed_study")

    def get(symbol, end=None):
        key = (symbol, end)
        if key not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                cache[key] = TM.load(symbol, end=end)
        return cache[key]
    return get


def _ext_cases(mk):
    return [("1D", "close over SMA 50, long / flat", X.price_over_sma(mk, 50, "D1"), False),
            ("4H", "Supertrend 10 x 3, long / flat", X.supertrend(mk, long_only=True, tf="H4"), False),
            ("4H", "Supertrend 10 x 3, stop and reverse", X.supertrend(mk, long_only=False, tf="H4"), True)]


@pytest.mark.parametrize("symbol", SYMS)
def test_a_external_state_strategies_give_identical_trades_through_the_adapter(symbol, real):
    mk = real(symbol)
    assert mk.end_s == TM.CUT_S and int(mk.t[-1]) < TM.CUT_S
    a, z = TM.window("dev", symbol)
    a_s, z_s = TM.s_of(a), TM.s_of(z)
    iz = int(np.searchsorted(mk.t, z_s))
    for tf, name, built, flips in _ext_cases(mk):
        b = mk.tbars(tf)
        rt, state = built.regime
        assert np.array_equal(rt, b.tc)
        r = TM.run(mk, b, state, a, z)
        first = int(np.flatnonzero(b.tc > a_s)[0])
        plan = built.plan
        p0 = X.run_path(mk, plan, int(b.ex[first]), iz)
        if flips:
            # external's plan stamped at the fill bar's open (DEVIATIONS 4) is the adapter's path exactly ...
            p = X.run_path(mk, plan.copy(dt=mk.t[plan.dx]), int(b.ex[first]), iz)
            # ... and with its own close stamps it differs only if some flip's close has no quote
            w = (b.tc > a_s) & (b.ex < iz)
            gap_flips = int(np.sum(w[1:] & (state[1:] * state[:-1] == -1) & (mk.t[np.minimum(b.ex[1:], len(mk) - 1)] != b.tc[1:])))
            assert (path_rows(p0) == path_rows(p)) == (gap_flips == 0), name
        else:
            p = p0
        assert len(r.path) > 10, name
        assert path_rows(r.path) == path_rows(p), name
        pnl_ext = mk.k * p.dir * (p.xpx - p.epx)
        assert np.array_equal(np.round(r.trades.pnl.to_numpy(), 2), np.round(pnl_ext, 2)), name
        assert r.net == pytest.approx(float(pnl_ext.sum()), abs=1e-6)
        bnd = X.block_bounds(mk, a, z)
        ra, rb = X.account(mk, r.path, X.BOT, bnd), X.account(mk, p, X.BOT, bnd)
        assert ra.final == rb.final and np.array_equal(ra.blocks, rb.blocks) and ra.max_dd == rb.max_dd, name


def _test_states(b, seed=11):
    s50 = X.sma(b.c, 50)
    st1 = np.where(np.isfinite(s50), np.where(b.c > s50, 1, -1), 0)
    st2 = X._supertrend(b.h, b.l, b.c, X.wilder_atr(b.h, b.l, b.c, 10), 3.0)
    rng = np.random.default_rng(seed)
    flips = np.cumsum(rng.random(200_000) < 0.04)[: len(b)]
    st3 = np.where(flips % 3 == 0, 1, np.where(flips % 3 == 1, -1, 0))
    return {"sma50": st1, "supertrend": st2, "random": st3}


@pytest.mark.parametrize("symbol", SYMS)
@pytest.mark.parametrize("T", ["2021-03-01", "2020-11-17 13:37"])
def test_b_results_up_to_T_do_not_change_when_the_data_after_T_is_removed(symbol, T, real):
    full, cut = real(symbol), real(symbol, end=T)
    T_s = TM.s_of(T)
    assert int(cut.t[-1]) < T_s and np.array_equal(cut.t, full.t[: len(cut)]) and np.array_equal(cut.c, full.c[: len(cut)])
    for tf in TM.TFS:
        bf, bc = full.tbars(tf), cut.tbars(tf)
        n = int(np.sum(bc.tc <= T_s))
        assert n > 300 and np.all(bc.complete[:n])
        for f in ("t", "tc", "i0", "i1", "ex", "o", "h", "l", "c", "vol", "spread", "n_m1"):
            assert np.array_equal(getattr(bf, f)[:n], getattr(bc, f)[:n]), (tf, f)
        sf, sc = _test_states(bf), _test_states(bc)
        stop_f, stop_c = TM.s1_stop(bf), TM.s1_stop(bc)
        for key in sf:
            assert np.array_equal(sf[key][:n], sc[key][:n])
            for stop, cost in ((None, 1.0), ("S1", 1.5)):
                rf = TM.run(full, bf, sf[key], "2019-01-01", T, stop=None if stop is None else stop_f, cost=cost)
                rc = TM.run(cut, bc, sc[key], "2019-01-01", T, stop=None if stop is None else stop_c, cost=cost)
                assert len(rf.trades) > 3, (tf, key)
                assert rf.trades.equals(rc.trades), (tf, key, stop)
                assert np.array_equal(rf.ec, rc.ec) and rf.max_dd == rc.max_dd
                assert same(TM.metrics(rf), TM.metrics(rc)), (tf, key, stop)


@pytest.mark.parametrize("symbol", SYMS)
def test_e_tick_volume_of_real_bars_is_the_sum_of_their_m1_counts(symbol, real):
    mk = real(symbol)
    ix = np.arange(len(mk))
    for tf in TM.TFS:
        b = mk.tbars(tf)
        own = np.searchsorted(b.i0, ix, side="right") - 1
        inside = (own >= 0) & (ix <= b.i1[np.maximum(own, 0)])
        assert np.array_equal(b.vol, np.bincount(own[inside], weights=mk.n[inside], minlength=len(b)))
        assert np.all(b.vol >= b.n_m1) and np.all(b.vol == np.round(b.vol))
    m1 = {"t": mk.t, "o": mk.o, "h": mk.h, "l": mk.l, "c": mk.c, "ask_c": mk.c + mk.sp, "spread_mean": mk.sp,
          "spread_max": mk.sp, "n": mk.n}
    for tf, sec in (("1H", 3600), ("4H", 14400)):
        ref = store.resample_bars(m1, sec)                     # the repository's own resampler
        b = mk.tbars(tf)
        assert np.array_equal(b.t, ref["t"]) and np.array_equal(b.vol, ref["n"])
        assert np.array_equal(b.c, ref["c"]) and np.allclose(b.spread, ref["spread_mean"], rtol=1e-9)


@pytest.mark.parametrize("symbol", SYMS)
def test_stops_on_real_bars_follow_the_rule(symbol, real):
    mk = real(symbol)
    b = mk.tbars("4H")
    st = _test_states(b)["random"]
    dist = TM.s1_stop(b)
    for cost in (1.0, 1.5):
        r = TM.run(mk, b, st, "2019-01-01", "2023-01-01", stop=dist, cost=cost)
        tr, cm = r.trades, r.m
        hit = tr[tr.reason.isin(["stop", "gap stop"])]
        assert len(hit) > 20
        dec = np.searchsorted(b.ex, tr.entry_ix.to_numpy())              # the decision bar of each entry
        assert np.array_equal(b.ex[dec], tr.entry_ix.to_numpy())
        level = tr.entry - tr.side * dist[dec]
        x = tr.exit_ix.to_numpy()
        sp = cm.sp[x]
        inbar = tr.reason == "stop"
        assert np.allclose(tr.exit[inbar], (level - tr.side * sp)[inbar], atol=1e-6)
        gap = tr.reason == "gap stop"
        opn = np.where(tr.side > 0, cm.o[x], cm.o[x] + sp)
        assert np.allclose(tr.exit[gap], (opn - tr.side * sp)[gap], atol=1e-6)
        assert np.all(np.where(tr.side[gap] > 0, opn[gap] <= level[gap], opn[gap] >= level[gap]))
        # DEVIATIONS 1, 2: every entry but one decided at the window's first bar is decided where the state changes,
        # so no side that was stopped is taken again before the state has changed
        first = int(np.flatnonzero(b.tc > TM.s_of("2019-01-01"))[0])
        assert np.all((st[dec] != st[dec - 1]) | (dec == first))
        nxt = np.flatnonzero(tr.reason.isin(["stop", "gap stop"]).to_numpy()[:-1]) + 1
        assert len(nxt) > 10 and np.all(st[dec[nxt]] != st[dec[nxt] - 1])


def test_binance_volume_of_the_real_files_passes_the_plans_check(real):
    files = TM._binance_files()
    if not all(p.exists() for _, a, _, _, p in files if a < TM.CUT_S):
        pytest.skip("the Binance files are not on this machine")
    mk = real("BTCUSDm")
    chk = TM.binance_check(mk)
    assert chk["passes"] and chk["corr_close"] > 0.999 and chk["best_lag_h"] == 0
    assert chk["matched"] + chk["exness_bars_without_kline"] == chk["exness_1h_bars"]
    v1, m1 = TM.binance_volume(mk, "1H")
    for tf in ("4H", "1D"):
        v, m = TM.binance_volume(mk, tf)
        hb = mk.tbars(tf)
        last = int(hb.i1[-1])
        h1 = mk.tbars("1H")
        inside = h1.i1 <= last
        assert v.sum() == pytest.approx(v1[inside].sum(), rel=1e-12) and m.sum() == m1[inside].sum()
    assert np.all(v1 >= 0) and m1.sum() == chk["exness_bars_without_kline"]
