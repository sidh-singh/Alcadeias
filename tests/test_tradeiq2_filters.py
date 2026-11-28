"""
Study 2's filters (``backtesting/research/tradeiq2_filters.py``, PREREG section 5) on hand-made bars.

F0, F1 (the same timeframe's MA200), F2-4H / F2-1D (the last CLOSED higher bar's MA200, also for M5 / M15 rules; equal
to study 1's ``tradeiq.htf_sides``), F3 (study 1's TSI 5 / 25 on the signal timeframe, the last closed 1H bar's for M5 /
M15), LO; applied as a state filter (study 1's ``apply_filter``) and as an entry gate (at the decision bar only), and
as per-M1 masks for stop-order fills. FR and FS are tested once their modules exist (``pytest.importorskip``).
"""

from __future__ import annotations

import numpy as np
import pytest

from backtesting.research import tradeiq as T1
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_market as M

DAY = 86400


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    return d2


def btc_like(days=450, seed=3, start="2018-03-05"):
    """Around the clock, a random walk with two-day trends, so that every MA200 (the 1D one included, after 200
    days) and the TSI change sides."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    drift = np.repeat(rng.normal(0.0, 0.03, n // 2880 + 1), 2880)[:n]
    c = 20000.0 + np.cumsum(drift + rng.normal(0.0, 2.0, n))
    o = np.concatenate(([5000.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 1.0, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 1.0, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(n, 10.0), "n": np.ones(n)}


@pytest.fixture(scope="module")
def ctx():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        mk = M.TMarket2("BTCUSDm", btc_like())
    return M.Context(mk)


def test_f0_and_lo(ctx):
    for tf in ("M15", "1H", "4H"):
        n = len(ctx.bars(tf))
        al, ash = F.allow(ctx, tf, "F0")
        assert al.all() and ash.all() and len(al) == n
        al, ash = F.allow(ctx, tf, "LO")
        assert al.all() and not ash.any()
    with pytest.raises(ValueError):
        F.allow(ctx, "1H", "F9")


def test_f1_is_the_close_against_the_ma200_of_the_same_timeframe(ctx):
    for tf in ("M5", "1H", "4H", "1D"):
        b = ctx.bars(tf)
        al, ash = F.allow(ctx, tf, "F1")
        ma = I.ma200(b.c)
        with np.errstate(invalid="ignore"):
            assert np.array_equal(al, b.c > ma) and np.array_equal(ash, b.c < ma)
        assert not al[:199].any() and not ash[:199].any()                        # the warm-up allows neither
        if len(b) > 400:
            assert al[199:].any() and ash[199:].any()
    # study 1's F1 on the same lines
    L = {"close": ctx.bars("1H").c, "MA200": I.ma200(ctx.bars("1H").c)}
    a1, s1 = T1.allowed_of(L, "F1")
    al, ash = F.allow(ctx, "1H", "F1")
    assert np.array_equal(a1, al) and np.array_equal(s1, ash)


@pytest.mark.parametrize("tf,name", [("M5", "F2-4H"), ("M15", "F2-1D"), ("1H", "F2-4H"), ("1H", "F2-1D"),
                                     ("4H", "F2-1D")])
def test_f2_is_the_last_closed_higher_bars_ma200_side(ctx, tf, name):
    b, hb = ctx.bars(tf), ctx.bars(F.F2_OF[name])
    al, ash = F.allow(ctx, tf, name)
    a1, s1 = T1.htf_sides(hb, b)                                                 # study 1's function
    assert np.array_equal(al, a1) and np.array_equal(ash, s1)
    # by hand: the higher bar whose close time is at or before the signal bar's close
    ma = I.ma200(hb.c)
    for i in np.linspace(0, len(b) - 1, 400).astype(int):
        k = int(np.searchsorted(hb.tc, b.tc[i], side="right") - 1)
        want_l = k >= 0 and np.isfinite(ma[k]) and hb.c[k] > ma[k]
        want_s = k >= 0 and np.isfinite(ma[k]) and hb.c[k] < ma[k]
        assert al[i] == want_l and ash[i] == want_s
    assert al.any() and ash.any()


def test_f2_is_refused_where_the_plan_does_not_define_it(ctx):
    for tf, name in (("4H", "F2-4H"), ("1D", "F2-1D"), ("1D", "F2-4H")):
        with pytest.raises(ValueError):
            F.allow(ctx, tf, name)


def test_f3_is_study_1s_tsi_side_on_the_signal_timeframe_and_the_last_closed_1h_bar_intraday(ctx):
    for tf in ("1H", "4H", "1D"):
        x = I.bjorgum_tsi(ctx.bars(tf).c, 5, 25).tsi
        al, ash = F.allow(ctx, tf, "F3")
        with np.errstate(invalid="ignore"):
            assert np.array_equal(al, x > 0) and np.array_equal(ash, x < 0)
        L = {"TSI": x, "close": ctx.bars(tf).c}
        a1, s1 = T1.allowed_of(L, "F3")
        assert np.array_equal(a1, al) and np.array_equal(s1, ash)
    h1 = ctx.bars("1H")
    x1 = I.bjorgum_tsi(h1.c, 5, 25).tsi
    for tf in ("M5", "M15"):
        b = ctx.bars(tf)
        al, ash = F.allow(ctx, tf, "F3")
        k = np.searchsorted(h1.tc, b.tc, side="right") - 1
        want = np.where(k >= 0, x1[np.maximum(k, 0)], np.nan)
        with np.errstate(invalid="ignore"):
            assert np.array_equal(al, want > 0) and np.array_equal(ash, want < 0)
        # a bar inside an hour reads the hour before it, not the forming one
        i = int(np.flatnonzero((b.tc % 3600) == 1800)[5])
        assert al[i] == (x1[int(b.tc[i] // 3600 * 3600 - h1.t[0]) // 3600 - 1] > 0)


def test_filters_as_state_filters_and_as_entry_gates(ctx):
    b = ctx.bars("1H")
    rng = np.random.default_rng(1)
    st = rng.integers(-1, 2, len(b)).astype(np.int8)
    al, ash = F.allow(ctx, "1H", "F1")
    assert np.array_equal(F.as_state_filter(st, al, ash), T1.apply_filter(st, al, ash))
    bars = np.sort(rng.choice(np.arange(len(b) - 5), 300, replace=False))
    side = rng.choice([-1, 1], 300)
    E = M.entries(bars, side, stop_dist=50.0, exit_bar=bars + 3)
    G = F.gate_entries(E, al, ash)
    keep = np.where(side == 1, al[bars], ash[bars])
    assert np.array_equal(G.bar, bars[keep]) and np.array_equal(G.exit_bar, (bars + 3)[keep]) and 0 < len(G) < len(E)
    # an entry gate does not close an open trade: the trade exits by its own rule
    r = M.run_exec(ctx.mk, M.event_exec("1H", entries=G), "2019-03-01", "2019-05-01")
    assert len(r.trades) > 0 and set(r.trades.reason) <= {"signal", "stop", "gap stop", "end"}
    # orders: the sides not allowed at the placement close are removed
    O = M.orders(bars[:50], TM.s_of("2019-12-31"), buy=1e6, sell=1.0, buy_stop=0.5 * 1e6, sell_stop=2.0)
    GO = F.gate_orders(O, al, ash)
    kb, ks = al[bars[:50]], ash[bars[:50]]
    assert len(GO) == int((kb | ks).sum())
    assert np.array_equal(np.isfinite(GO.buy), kb[kb | ks]) and np.array_equal(np.isfinite(GO.sell), ks[kb | ks])
    assert np.array_equal(np.isfinite(GO.buy_stop), np.isfinite(GO.buy))
    # combined filters are their AND
    a2, s2 = F.allow(ctx, "1H", "F2-4H")
    ca, cs = F.combine((al, ash), (a2, s2))
    assert np.array_equal(ca, al & a2) and np.array_equal(cs, ash & s2)


def test_fill_masks_read_the_last_closed_signal_bar(ctx):
    b = ctx.bars("1H")
    al, ash = F.allow(ctx, "1H", "F1")
    ml, ms = F.fill_masks(ctx, "1H", al, ash)
    t = ctx.mk.t
    assert len(ml) == len(t) and ml.dtype == np.bool_
    for j in np.linspace(0, len(t) - 1, 500).astype(int):
        k = int(np.searchsorted(b.tc, t[j], side="right") - 1)
        assert ml[j] == (k >= 0 and al[k]) and ms[j] == (k >= 0 and ash[k])
    assert not ml[:60].any()                                                     # before the first 1H close


def test_filters_are_cached_and_read_only(ctx):
    a1 = F.allow(ctx, "4H", "F1")
    a2 = ctx.allow("4H", "F1")
    assert a1[0] is a2[0] and not a1[0].flags.writeable
    assert F.available("M5") == ["F0", "F1", "F2-4H", "F2-1D", "F3", "LO"]
    assert F.available("1D") == ["F0", "F1", "F3", "LO", "FR", "FS"]


def test_fr_is_the_higher_timeframes_ribbon_trend(ctx):
    RB = pytest.importorskip("backtesting.research.tradeiq2_ind_ribbon")
    for tf, htf in F.RIBBON_TF.items():
        hb, b = ctx.bars(htf), ctx.bars(tf)
        tr = np.asarray(RB.ribbon(hb.o, hb.h, hb.l, hb.c)["trend"], np.float64)
        al, ash = F.allow(ctx, tf, "FR")
        if htf == tf:
            assert np.array_equal(al, tr == 1) and np.array_equal(ash, tr == -1)
        else:
            k = np.searchsorted(hb.tc, b.tc, side="right") - 1
            v = np.where(k >= 0, tr[np.maximum(k, 0)], np.nan)
            assert np.array_equal(al, v == 1) and np.array_equal(ash, v == -1)
    with pytest.raises(ValueError):
        F.allow(ctx, "M15", "FR")


def test_fs_is_the_dashboards_label_on_the_signal_chart(ctx):
    MS = pytest.importorskip("backtesting.research.tradeiq2_ind_msd")
    for tf, rows in F.MSD_ROWS.items():
        lab = np.asarray(MS.structure_dashboard({r: ctx.bars(r) for r in rows}, tf)["label"], np.float64)
        al, ash = F.allow(ctx, tf, "FS")
        with np.errstate(invalid="ignore"):
            assert np.array_equal(al, lab >= 1) and np.array_equal(ash, lab <= -1)
        assert not (al & ash).any()
    with pytest.raises(ValueError):
        F.allow(ctx, "M5", "FS")
