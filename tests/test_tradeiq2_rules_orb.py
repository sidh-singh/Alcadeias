"""
Study 2's ORB rules (``backtesting/research/tradeiq2_rules_orb.py``): the rows of PREREG 6.5 (O1-O5, the filters, the
controls, ORB-CX and TIGHT), their entries, exits, stops and filters, executed by ``tradeiq2_market``, and the
functions of claims 6-9 (PREREG 8).

(a) The grid: the rows per symbol are the PREREG's numbers (written here from its text), with unique ids that carry
    the tokens the driver pairs rows by (HV -> LV, O4 -> O2 / O3, F2 -> F0, a version token -> the plan's row).
(b) Hand-made bars (continuous M1 bars of gold in January 2019, New York = UTC-5, so every level, fill and exit is
    known by hand), run through the real port: O1's label entry, its close-based trail (a wick does not exit, the
    trail never moves down), the script's order (a bear label on the trail-exit bar opens no short; a later one does),
    the 16:00 decision cut and the 16:55 flat time (M5 and M15); an early close (13:30, the reopen at 18:00), where
    every exit decided at the flat bar is booked at its last M1 close before the break (``close_gap``, reading 3): O1's
    trail cap and a trail firing on the flat bar, O2 / O3 / O4 (long, short, x1.5; a stop inside the flat bar wins),
    O5's trail cap and a fill inside the flat bar (F0, HV); an O1 trail exit before the flat bar keeps the next M1
    open after a hole, an O5 one does not (the flag is the order's); O2 / O3 / O4's absolute levels from the ACTUAL
    fill (a gap through the stop, x1.5, an entry beyond its target dropped); O5's OCO stop orders (placed at 10:00,
    cancelled at 16:00, the far-side stop, the trail from the fill's bar, one trade a day).
(c) Filters: HV / LV at the label bar (the SMA(20) with the bar included), F2 / LO at the label's close (never
    closing a trade; a refused label blocks nothing), O5's F2 / LO at the placement and HV at the fill bar's close;
    TIGHT (Session Hunter's adr); ORB-CX's range and order window; the literal UTC-5 clock in summer; BTC on 7 days.
(d) O4's target from the past breakouts (60 needed, the furthest level at 50%), against a brute-force count; on a
    market where an M1 bar opens at every close the ``close_gap`` flags change nothing.
(e) Causality: every entry and exit decided at a bar closing at or before T (with its ``close_gap`` once the flat time
    has passed), and every O5 order whose post-session bar (where the port counts the session) opens before T, is the
    same when the data after T is removed (every row, a synthetic 300-day market cut at eleven times, among them 10:00,
    13:45 and 16:30 New York; the study's bars in (g)).
(f) Claims 6-9 on synthetic bars against brute-force counts from the M1 bars, and on synthetic results.
(g) Real data (skipped when the store is absent; read to 2019-07-01 only): O1 x F0 is the port's own trade logic,
    causality, and an execution smoke test on Development data (2019-01-01 to 2019-06-30) for one row of each rule
    type through ``tradeiq2_market.run_variant`` (every trade flat by its flat bar's close, early closes included).
    Its profit or loss is neither printed, asserted nor reported: only counts, times and levels are checked.
"""

from __future__ import annotations

import dataclasses
import gc
import json

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_ind_session as SHI
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_orb as R

DAY = 86400
T0 = TM.s_of("2019-01-07")              # a Monday, 00:00 UTC = Sunday 19:00 New York (EST, UTC-5)
SYMS = ("XAUUSDm", "BTCUSDm")


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' folders as the guards see them: empty tmp folders (no FINALISTS.md: the hold-outs are closed)."""
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d2


# ───────────────────────────── (a) the grid ─────────────────────────────

# PREREG 6.5 "Size: 2 timeframes x 5 rules x 5 filter sets = 50 rows per symbol, plus 10 LO rows on gold, 8 ORB-CX
# rows and 4 TIGHT rows; plus the controls". The controls (not eligible): "LV only (O1-O4)" x 2 timeframes = 8, "the
# script's literal fixed UTC-5 clock (O1)" x 2 = 2, "BTC on all 7 days (O1)" x 2 = 2 (BTC). ORB-CX is gold only
# ("ORB-CX, gold only: ... for O1 and O5, with F0 and F2-4H": 2 x 2 x 2 = 8), LO gold only, TIGHT "on O1 and O5"
# (x 2 timeframes = 4, both symbols). PREREG 7 counts 738 eligible on gold and 720 on BTC: ORB's 72 - 54 = 18 is the
# gold-only LO and ORB-CX rows.
PLAN = {"XAUUSDm": {("ORB", True): 50 + 10 + 8 + 4, ("ORB", False): 8 + 2},
        "BTCUSDm": {("ORB", True): 50 + 4, ("ORB", False): 8 + 2 + 2}}


def by_id(symbol):
    return {v.id: v for v in R.variants(symbol)}


def V(vid):
    return by_id(vid.split("|")[0])[vid]


@pytest.mark.parametrize("symbol", SYMS)
def test_a_the_rows_per_symbol_are_the_preregs(symbol):
    vs = R.variants(symbol)
    assert len(vs) == (82 if symbol == "XAUUSDm" else 66) == sum(PLAN[symbol].values())
    got = {}
    for v in vs:
        got[(v.family, v.eligible)] = got.get((v.family, v.eligible), 0) + 1
    assert got == PLAN[symbol] and R.plan_counts(symbol) == PLAN[symbol]
    ids = [v.id for v in vs]
    assert len(set(ids)) == len(ids)
    for v in vs:
        assert isinstance(v, M.Variant) and v.symbol == symbol and v.tf in ("M5", "M15")
        assert v.id.startswith(f"{symbol}|{v.tf}|ORB|") and not any(ch.isspace() for ch in v.id)
        assert v.family == "ORB" and v.script == "ORB" and isinstance(v.eligible, bool)
        assert "information only" not in v.info                  # PREREG 6.5 has no information-only row
        assert json.loads(v.ident()["params"])["rule"] == v.id.split("|")[3]
    main = [v for v in vs if len(v.id.split("|")) == 5 and v.eligible and v.params["filter"] != "LO"]
    assert {(v.tf, v.params["rule"], v.params["filter"]) for v in main} == {
        (tf, r, f) for tf in ("M5", "M15") for r in ("O1", "O2", "O3", "O4", "O5")
        for f in ("F0", "HV", "F2-4H", "F2-1D", "HV+F2-4H")}
    lo = sorted(v.id for v in vs if v.params["filter"] == "LO")
    cx = sorted(v.id for v in vs if v.params["version"] == "ORB-CX")
    tight = sorted(v.id for v in vs if v.params["range"] == "tight")
    if symbol == "XAUUSDm":
        assert lo == sorted(f"{symbol}|{tf}|ORB|{r}|LO" for tf in ("M5", "M15") for r in R.RULES)
        assert cx == sorted(f"{symbol}|{tf}|ORB|{r}|{f}|ORB-CX" for tf in ("M5", "M15") for r in ("O1", "O5")
                            for f in ("F0", "F2-4H"))
    else:
        assert lo == [] and cx == []
    assert tight == sorted(f"{symbol}|{tf}|ORB|{r}|F0|TIGHT" for tf in ("M5", "M15") for r in ("O1", "O5"))
    assert all(v.eligible for v in vs if v.id in set(lo) | set(cx) | set(tight))
    ctl = {v.id: v for v in vs if not v.eligible}
    want = {f"{symbol}|{tf}|ORB|{r}|LV" for tf in ("M5", "M15") for r in ("O1", "O2", "O3", "O4")}
    want |= {f"{symbol}|{tf}|ORB|O1|F0|UTC-5" for tf in ("M5", "M15")}
    if symbol == "BTCUSDm":
        want |= {f"{symbol}|{tf}|ORB|O1|F0|7D" for tf in ("M5", "M15")}
    assert set(ctl) == want
    assert all("control" in v.info and "not eligible" in v.info for v in ctl.values())
    assert {v.params["clock"] for v in ctl.values() if v.params["version"] == "UTC-5"} == {"utc-5"}
    assert all(v.params["days"] == ("all" if v.params["version"] == "7D" else "weekdays") for v in vs)


def test_a_the_claim_markets_have_no_orb_row_and_the_drivers_table_agrees():
    for s in ("USTECm", "EURUSDm", "GBPUSDm"):
        assert R.variants(s) == []
    with pytest.raises(ValueError):
        R.variants("ETHUSDm")
    from backtesting.research import tradeiq2 as D
    rows = [r for r in D.COUNT_TABLE if r[0] == "orb"]
    table = {(fam, el): (g, b) for _, fam, el, g, b, _ in rows}
    assert table == {(f, e): (PLAN["XAUUSDm"][(f, e)], PLAN["BTCUSDm"][(f, e)]) for (f, e) in PLAN["XAUUSDm"]}
    pairs, problems = D.collect({"orb": R})
    assert problems == [] and len(pairs) == 82 + 66
    assert D.count_differences(D.grid_frame(pairs), D.PREREG_COUNTS, ["orb"]).empty


def _swap(vid, old, new):
    t = vid.split("|")
    if t.count(old) != 1:
        return None
    return "|".join(x for x in ((new if x == old else x) for x in t) if x is not None)


def test_a_ids_pair_the_way_the_driver_pairs_them():
    for s in SYMS:
        ids = by_id(s)
        for v in ids.values():
            r, f, ver = v.params["rule"], v.params["filter"], v.params["version"]
            if f == "HV" and ver == "NY" and r != "O5":                         # claim 7: HV -> LV, same rule
                assert _swap(v.id, "HV", "LV") in ids
            if f == "HV" and r == "O5":
                assert _swap(v.id, "HV", "LV") not in ids                       # "LV only (O1-O4)"
            if r == "O4" and v.eligible:                                       # claim 8: O4 -> O2 / O3
                assert _swap(v.id, "O4", "O2") in ids and _swap(v.id, "O4", "O3") in ids
            if f in ("F2-4H", "F2-1D"):                                         # the driver's vs_f0
                assert _swap(v.id, f, "F0") in ids
            for tok in ("ORB-CX", "UTC-5", "7D", "TIGHT"):                      # a version -> the plan's row
                if tok in v.id.split("|"):
                    assert _swap(v.id, tok, None) in ids
            assert v.params["filter"] in v.id.split("|")
        for tf in ("M5", "M15"):                                                # claim 9's pair
            assert f"{s}|{tf}|ORB|O1|F0" in ids and f"{s}|{tf}|ORB|O1|F0|UTC-5" in ids


def test_a_describe_and_build_refuse_rows_outside_the_plan():
    ch = Chart()
    ctx = M.Context(ch.market("BTCUSDm"))
    ctx.volume = lambda tf, source="auto": ctx.bars(tf).vol
    for v in R.variants("BTCUSDm") + R.variants("XAUUSDm"):
        assert len(R.describe(v)) > 200
    with pytest.raises(ValueError):
        R.build(M.Variant("BTCUSDm|M5|ORB|O6|F0", "BTCUSDm", "M5", "ORB", "ORB"), ctx)
    with pytest.raises(ValueError):
        R.build(V("XAUUSDm|M5|ORB|O1|F0"), ctx)                                # a gold row on BTC's context
    with pytest.raises(ValueError):
        R.build(M.Variant("BTCUSDm|M5|ORB|O1|LO", "BTCUSDm", "M5", "ORB", "ORB"), ctx)   # LO is gold's only
    with pytest.raises(ValueError):
        R.build(M.Variant("BTCUSDm|M5|ORB|O1|F0", "BTCUSDm", "M15", "ORB", "ORB"), ctx)  # id and tf disagree
    assert isinstance(R.build(V("BTCUSDm|M5|ORB|O1|F0"), ctx), M.Exec)


# ───────────────────────────── hand-made bars ─────────────────────────────

def ny(hhmm, day=0, d0=T0 // DAY):
    """UTC seconds of New York wall time ``hhmm`` on the date ``d0 + day``."""
    h, m = (int(x) for x in hhmm.split(":"))
    return int(M.utc_of_ny(d0 + day, h * 60 + m))


class Chart:
    """Continuous M1 bars from ``t0``: o = c = p, h = p + half, l = p - half, spread ``sp``, one tick each."""

    def __init__(self, days=1, p=100.0, half=0.5, sp=0.2, t0=T0):
        k = days * 1440
        self.t0, self.d0 = t0, t0 // DAY
        self.t = t0 + 60 * np.arange(k, dtype=np.int64)
        self.o, self.c = np.full(k, p), np.full(k, p)
        self.h, self.l = np.full(k, p + half), np.full(k, p - half)
        self.sp, self.n = np.full(k, float(sp)), np.ones(k)

    def ix(self, hhmm, day=0):
        """The minute index of New York ``hhmm`` (the M1 bar opening then)."""
        return int((ny(hhmm, day, self.d0) - self.t0) // 60)

    def seg(self, a, z, p, half=0.5, day=0):
        """New York [a, z) at price p (z may be '24:00' = the next midnight)."""
        i = self.ix(a, day)
        j = self.ix("00:00", day + 1) if z == "24:00" else self.ix(z, day)
        self.o[i:j], self.c[i:j], self.h[i:j], self.l[i:j] = p, p, p + half, p - half
        return self

    def bar(self, hhmm, day=0, **kw):
        i = self.ix(hhmm, day)
        for k, v in kw.items():
            getattr(self, k)[i] = v
        return self

    def arrays(self, keep=None):
        keep = np.ones(len(self.t), bool) if keep is None else keep
        return {"t": self.t[keep], "o": self.o[keep], "h": self.h[keep], "l": self.l[keep], "c": self.c[keep],
                "spread_mean": self.sp[keep], "n": self.n[keep]}

    def market(self, symbol="XAUUSDm", keep=None, end_s=None):
        return M.TMarket2(symbol, self.arrays(keep), end_s)


def range_99_101(ch, day=0, lo=99.0, hi=101.0):
    """The 09:30-10:00 range: a high of ``hi`` at 09:35 and a low of ``lo`` at 09:45 (M1 bars of both M5 and M15)."""
    return ch.bar("09:35", day, h=hi).bar("09:45", day, l=lo)


def masks(ctx, table):
    """``ctx.allow`` replaced: ``table`` maps a filter to (allow_long, allow_short); LO as PREREG 5; every other name
    allows both sides. Returns the list of (tf, name) asked."""
    asked = []

    def allow(tf, name):
        asked.append((tf, name))
        if name in table:
            return tuple(np.asarray(x, bool) for x in table[name](len(ctx.bars(tf))))
        n = len(ctx.bars(tf))
        if name == "LO":
            return np.ones(n, bool), np.zeros(n, bool)
        return np.ones(n, bool), np.ones(n, bool)
    ctx.allow = allow
    return asked


def run(mk, ex, cost=1.0):
    return M.run_exec(mk, ex, T0, int(mk.t[-1]) + 60, cost)


def rows(r):
    tr = r.trades
    return [(int(a), int(b), int(c), round(float(d), 9), round(float(e), 9), str(f))
            for a, b, c, d, e, f in zip(tr.side, tr.entry_ix, tr.exit_ix, tr.entry, tr.exit, tr.reason)]


def bix(ctx, tf, hhmm, day=0):
    """The index of the ``tf`` bar opening at New York ``hhmm``."""
    b = ctx.bars(tf)
    i = int(np.searchsorted(b.t, ny(hhmm, day)))
    assert b.t[i] == ny(hhmm, day)
    return i


def build(ctx, vid):
    return R.build(V(vid), ctx)


def no_gap(ex):
    """The same Exec with every row's ``close_gap`` off: the reading before 28 Nov 2026, whose flat exit always fills
    at the next M1 open, the reopen when the market closed early."""
    if ex.entries is not None:
        return dataclasses.replace(ex, entries=dataclasses.replace(ex.entries, close_gap=None))
    return dataclasses.replace(ex, orders=dataclasses.replace(ex.orders, close_gap=None))


def early_close(ch, close="13:30", reopen="18:00", day=0):
    """``ch``'s market without its M1 bars from New York ``close`` to ``reopen`` (a holiday's early close)."""
    return ch.market(keep=~((ch.t >= ny(close, day)) & (ch.t < ny(reopen, day))))


def m1(mk, hhmm, day=0):
    """The index in ``mk`` of the M1 bar opening at New York ``hhmm``."""
    i = int(np.searchsorted(mk.t, ny(hhmm, day)))
    assert mk.t[i] == ny(hhmm, day)
    return i


def s1():
    """The range 99-101; the 10:00 bar breaks up (close 101.5); at 12:00 the price falls to 96 for the rest of the day
    (that bar closes below the trail AND below the range: a bear label on the long's trail-exit bar)."""
    ch = range_99_101(Chart())
    ch.seg("10:00", "12:00", 101.5).seg("12:00", "24:00", 96.0)
    return ch


# ───────────────────────────── (b) O1, the script's trade ─────────────────────────────

def test_b_o1_enters_at_the_label_exits_at_the_trails_close_and_a_bear_label_on_that_bar_opens_nothing():
    ch = s1()
    mk = ch.market()
    ctx = M.Context(mk)
    S = R.sessions(ctx, "M5")
    assert len(S["day"]) == 1 and S["or_high"][0] == 101.0 and S["or_low"][0] == 99.0 and S["width"][0] == 2.0
    assert list(S[k][0] for k in ("u1", "u2", "u3", "d1", "d2", "d3")) == [103.0, 105.0, 107.0, 97.0, 95.0, 93.0]
    b10, b12 = bix(ctx, "M5", "10:00"), bix(ctx, "M5", "12:00")
    assert S["label_up_bar"][0] == b10 and S["label_dn_bar"][0] == b12       # the script labels both
    assert S["flat_bar"][0] == bix(ctx, "M5", "16:50") and S["entry_end_s"][0] == ny("16:00")
    ex = build(ctx, "XAUUSDm|M5|ORB|O1|F0")
    assert ex.kind == "events" and ex.orders is None and ex.label == "XAUUSDm|M5|ORB|O1|F0"
    E = ex.entries
    assert list(E.bar) == [b10] and list(E.side) == [1] and list(E.exit_bar) == [b12]
    assert np.isnan(E.stop_level).all() and np.isnan(E.stop_dist).all() and np.isnan(E.target_level).all()
    assert list(E.tag) == [T0 // DAY]                                       # the session's New York date
    r = run(mk, ex)
    # filled at the open after the label bar's close (10:05) at the ask, out at the open after 12:00's close at the bid
    assert rows(r) == [(1, ch.ix("10:05"), ch.ix("12:05"), 101.7, 96.0, "signal")]
    assert np.isnan(r.trades.risk).all() and np.isnan(r.trades.r).all()      # no stop, so no R
    T = R.o1_trades(ctx, "M5", R.Row("O1", "F0"))
    assert len(T["busy"]) == 1                                              # the bear label found the long open
    d = R.orb_output(ctx, "M5")["days"]                                     # the port's own trade is the same
    assert (int(d.trade_side[0]), int(d.entry_bar[0]), int(d.exit_bar[0]), d.exit_reason[0]) == (1, b10, b12, "trail")
    assert int(d.trade2_side[0]) == 0


def test_b_o1_a_wick_through_the_trail_does_not_exit_the_trail_never_falls_and_the_flat_time_closes():
    ch = range_99_101(Chart())
    ch.seg("10:00", "24:00", 101.5).bar("11:02", l=97.0)                    # a wick far below the trail
    mk = ch.market()
    ctx = M.Context(mk)
    for tf, flat in (("M5", "16:55"), ("M15", "16:45")):
        r = run(mk, build(ctx, f"XAUUSDm|{tf}|ORB|O1|F0"))
        e = "10:05" if tf == "M5" else "10:15"
        assert rows(r) == [(1, ch.ix(e), ch.ix(flat), 101.7, 101.5, "signal")]
        flat_bar = R.sessions(ctx, tf)["flat_bar"][0]
        assert flat_bar == bix(ctx, tf, "16:50" if tf == "M5" else "16:30")
        trail = np.asarray(R.orb_output(ctx, tf)["trail"])[bix(ctx, tf, "10:00"):flat_bar + 1]
        assert np.isfinite(trail).all() and (np.diff(trail) >= 0).all()      # the script's trail: never down
    # the stop of O2 is a level: the same wick stops it at 99 (one spread charged)
    r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O2|F0"))
    assert rows(r) == [(1, ch.ix("10:05"), ch.ix("11:02"), 101.7, 98.8, "stop")]


def test_b_o1_after_the_trail_closes_the_long_a_later_bear_label_opens_a_short():
    ch = range_99_101(Chart(), lo=97.0)                                     # the range 97-101
    ch.seg("10:00", "10:30", 101.5).seg("10:30", "11:30", 103.0).seg("11:30", "13:00", 99.5)
    ch.seg("13:00", "24:00", 96.0)
    mk = ch.market()
    ctx = M.Context(mk)
    b10, b1130, b13 = (bix(ctx, "M5", x) for x in ("10:00", "11:30", "13:00"))
    T = R.o1_trades(ctx, "M5", R.Row("O1", "F0"))
    assert list(T["bar"]) == [b10, b13] and list(T["side"]) == [1, -1] and len(T["busy"]) == 0
    assert list(T["exit_bar"]) == [b1130, R.sessions(ctx, "M5")["flat_bar"][0]]
    r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O1|F0"))
    assert rows(r) == [(1, ch.ix("10:05"), ch.ix("11:35"), 101.7, 99.5, "signal"),
                       (-1, ch.ix("13:05"), ch.ix("16:55"), 96.0, 96.2, "signal")]
    d = R.orb_output(ctx, "M5")["days"]                                     # the script's two trades
    assert (int(d.trade_side[0]), int(d.exit_bar[0]), d.exit_reason[0]) == (1, b1130, "trail")
    assert (int(d.trade2_side[0]), int(d.entry2_bar[0])) == (-1, b13)


def test_b_decisions_only_up_to_16_00_and_the_flat_bar_of_m5_and_m15():
    ch = Chart(days=2)
    for day in (0, 1):
        range_99_101(ch, day)
    ch.seg("15:55", "19:00", 101.5, day=0)                                  # breaks on the bar closing at 16:00
    ch.seg("16:00", "19:00", 101.5, day=1)                                  # breaks on the bar closing at 16:05 (M5)
    mk = ch.market()
    ctx = M.Context(mk)
    C = R.candidates(ctx, "M5")
    assert list(C["side"]) == [1, 1] and list(C["decided"]) == [True, False] and list(C["ok"]) == [True, False]
    r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O1|F0"))
    assert rows(r) == [(1, ch.ix("16:00"), ch.ix("16:55"), 101.7, 101.5, "signal")]
    # M15: the 15:45 bar closes at 16:00 (a candidate), day 1's 16:00 bar at 16:15 (not); flat at the 16:30 bar's close
    r = run(mk, build(ctx, "XAUUSDm|M15|ORB|O1|F0"))
    assert rows(r) == [(1, ch.ix("16:00"), ch.ix("16:45"), 101.7, 101.5, "signal")]
    assert list(R.candidates(ctx, "M15")["ok"]) == [True, False]
    for v in ("XAUUSDm|M5|ORB|O2|F0", "XAUUSDm|M5|ORB|O4|HV", "XAUUSDm|M5|ORB|O1|LV"):
        assert len(build(ctx, v).entries) <= 1                              # never day 1's late label


def test_b_an_early_close_flat_exit_is_booked_at_the_last_m1_close_before_the_break():
    """A day whose bars stop at 13:30 New York (a holiday close) and resume at 18:00, 1.50 lower: the flat bar is the
    last bar before the break (M5: the 13:25 bar; M15: the 13:15 bar), so the long's last exit decision is its close at
    13:30. No M1 bar opens there, so the exit is booked at the close of the 13:29 M1 bar, the bid 101.5, read as a time
    exit ('signal', exit time 13:30; ``close_gap``, reading 3): flat before the break, as PREREG 6.5 says. Without the
    flag (the reading before 28 Nov 2026) the same decision is held over the break and fills at the 18:00 reopen
    (100.0). A label on the flat bar itself is not a candidate."""
    ch = range_99_101(Chart(days=2))
    ch.seg("10:00", "18:00", 101.5).seg("18:00", "24:00", 100.0)
    mk = early_close(ch)
    ctx = M.Context(mk)
    for tf, flat, e in (("M5", "13:25", "10:05"), ("M15", "13:15", "10:15")):
        S = R.sessions(ctx, tf)
        assert S["flat_bar"][0] == bix(ctx, tf, flat) and ctx.bars(tf).tc[S["flat_bar"][0]] == ny("13:30")
        ex = build(ctx, f"XAUUSDm|{tf}|ORB|O1|F0")
        assert list(ex.entries.exit_bar) == [S["flat_bar"][0]] and list(ex.entries.close_gap) == [True]
        r = run(mk, ex)
        assert rows(r) == [(1, m1(mk, e), m1(mk, "13:29"), 101.7, 101.5, "signal")] and r.counts["close_gap"] == 1
        assert r.trades.exit_time[0] == TM.utc(ny("13:30"))
        old = run(mk, no_gap(ex))
        assert rows(old) == [(1, m1(mk, e), m1(mk, "18:00"), 101.7, 100.0, "signal")] and old.counts["close_gap"] == 0
    ch2 = range_99_101(Chart(days=2))
    ch2.seg("13:25", "24:00", 101.5)                                        # the label is the 13:25 bar's
    ctx2 = M.Context(early_close(ch2))
    C = R.candidates(ctx2, "M5")
    assert list(C["bar"]) == [bix(ctx2, "M5", "13:25")] and list(C["decided"]) == [True]
    assert list(C["room"]) == [False] and len(build(ctx2, "XAUUSDm|M5|ORB|O1|F0").entries) == 0


def test_b_o1_a_trail_firing_on_the_flat_bars_own_close_is_the_flat_decision_booked_before_the_break():
    """The same early close with the price at 97 inside the flat bar (13:25-13:30): the bar closes below the trail
    (the highest low - 2 ATR since the 10:00 label, about 99), so the trail fires on the flat bar's own close. That is
    the flat time's decision too, so the row carries ``close_gap`` and the exit is booked at the 13:29 close (the bid
    97.0), not at the 18:00 reopen (100.0)."""
    ch = range_99_101(Chart(days=2))
    ch.seg("10:00", "13:25", 101.5).seg("13:25", "18:00", 97.0).seg("18:00", "24:00", 100.0)
    mk = early_close(ch)
    ctx = M.Context(mk)
    b = ctx.bars("M5")
    b10, flat = bix(ctx, "M5", "10:00"), bix(ctx, "M5", "13:25")
    atr = np.asarray(R.orb_output(ctx, "M5")["atr"])
    trail = max(b.l[k] - 2.0 * atr[k] for k in range(b10, flat + 1))         # the ratchet, never down
    assert (b.c[b10:flat] > trail).all() and b.c[flat] == 97.0 < trail     # it fires on the flat bar, not before
    T = R.o1_trades(ctx, "M5", R.Row("O1", "F0"))
    assert list(T["exit_bar"]) == [flat] and list(T["flat_exit"]) == [True]
    ex = build(ctx, "XAUUSDm|M5|ORB|O1|F0")
    r = run(mk, ex)
    assert rows(r) == [(1, m1(mk, "10:05"), m1(mk, "13:29"), 101.7, 97.0, "signal")] and r.counts["close_gap"] == 1
    assert rows(run(mk, no_gap(ex))) == [(1, m1(mk, "10:05"), m1(mk, "18:00"), 101.7, 100.0, "signal")]


def test_b_o1_a_trail_exit_before_the_flat_bar_keeps_the_next_m1_open_also_after_a_hole():
    """A normal day (flat bar 16:50) with a data hole from 12:00 to 12:30 New York: the trail fires on the 11:55 bar's
    close (97), an exit decided before the flat bar, so its row has no ``close_gap`` and it fills at the next M1 open,
    the first after the hole (12:30, the bid 98.0), as every decision of the study (PREREG 4). (The bear label on that
    bar finds the long open: busy.) With the flag forced on, the harness would book it at the 11:59 close (97.0)."""
    ch = range_99_101(Chart())
    ch.seg("10:00", "11:55", 101.5).seg("11:55", "12:30", 97.0).seg("12:30", "24:00", 98.0)
    mk = ch.market(keep=~((ch.t >= ny("12:00")) & (ch.t < ny("12:30"))))
    ctx = M.Context(mk)
    b1155 = bix(ctx, "M5", "11:55")
    assert R.sessions(ctx, "M5")["flat_bar"][0] == bix(ctx, "M5", "16:50")
    T = R.o1_trades(ctx, "M5", R.Row("O1", "F0"))
    assert list(T["exit_bar"]) == [b1155] and list(T["flat_exit"]) == [False] and len(T["busy"]) == 1
    ex = build(ctx, "XAUUSDm|M5|ORB|O1|F0")
    assert list(ex.entries.close_gap) == [False]
    r = run(mk, ex)
    assert rows(r) == [(1, m1(mk, "10:05"), m1(mk, "12:30"), 101.7, 98.0, "signal")] and r.counts["close_gap"] == 0
    forced = dataclasses.replace(ex, entries=dataclasses.replace(ex.entries, close_gap=True))
    assert rows(run(mk, forced)) == [(1, m1(mk, "10:05"), m1(mk, "11:59"), 101.7, 97.0, "signal")]


def test_b_o2_o3_o4_flat_exits_on_an_early_close_are_booked_before_the_break_and_a_stop_before_that_close_wins():
    """O2-O4 leave at their stop, their target or the flat bar, and every row carries ``close_gap``. On the early close
    a long whose targets (T1 103, T2 105; O4 is T1 here, fewer than 60 past breakouts) and stop (99) are not reached by
    13:30 leaves at the 13:29 close, the bid 101.5; without the flag it is held to the 18:00 reopen at 97.0 and gaps
    through its stop there (96.8: one spread charged). A stop touched inside the flat bar (13:27) still wins. A short
    (the range broken down at 98.5, the bid fill) leaves at the ask of the 13:29 close: 98.7 at x1.0, 98.8 at x1.5."""
    ch = range_99_101(Chart(days=2))
    ch.seg("10:00", "18:00", 101.5).seg("18:00", "24:00", 97.0)
    mk = early_close(ch)
    ctx = M.Context(mk)
    e, last, reopen = m1(mk, "10:05"), m1(mk, "13:29"), m1(mk, "18:00")
    for rule in ("O2", "O3", "O4"):
        ex = build(ctx, f"XAUUSDm|M5|ORB|{rule}|F0")
        assert list(ex.entries.close_gap) == [True] and list(ex.entries.exit_bar) == [bix(ctx, "M5", "13:25")]
        r = run(mk, ex)
        assert rows(r) == [(1, e, last, 101.7, 101.5, "signal")] and r.counts["close_gap"] == 1, rule
        assert rows(run(mk, no_gap(ex))) == [(1, e, reopen, 101.7, 96.8, "gap stop")], rule
    ch.bar("13:27", l=98.5)                                                 # through the stop 99 before the close
    mk = early_close(ch)
    r = run(mk, build(M.Context(mk), "XAUUSDm|M5|ORB|O2|F0"))
    assert rows(r) == [(1, e, m1(mk, "13:27"), 101.7, 98.8, "stop")] and r.counts["close_gap"] == 0
    ch = range_99_101(Chart(days=2))
    ch.seg("10:00", "18:00", 98.5).seg("18:00", "24:00", 102.0)
    mk = early_close(ch)
    ctx = M.Context(mk)
    for cost, out in ((1.0, 98.7), (1.5, 98.8)):
        r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O2|F0"), cost)
        assert rows(r) == [(-1, e, last, 98.5, out, "signal")] and r.counts["close_gap"] == 1, cost


def test_b_o5_its_trail_cap_on_an_early_close_is_booked_before_the_break():
    """O5's orders carry ``close_gap``. The buy stop fills at 101.0 inside the 11:02 M1 bar; its trail (from the 11:00
    bar) never fires, so its exit is the trail's cap, the flat bar (13:25): booked at the 13:29 close, the bid 101.5.
    Without the flag it is held to the 18:00 reopen at 97.0 and gaps through its stop (99) there (96.8). (One day of
    bars, to 19:00 New York: a second session's orders would fill on its own touches.)"""
    ch = range_99_101(Chart())
    ch.bar("11:02", h=101.3).seg("11:03", "18:00", 101.5).seg("18:00", "24:00", 97.0)
    mk = early_close(ch)
    ctx = M.Context(mk)
    ex = build(ctx, "XAUUSDm|M5|ORB|O5|F0")
    flat = bix(ctx, "M5", "13:25")
    assert list(ex.orders.close_gap) == [True] and list(ex.orders.exit_bar) == [flat]
    assert ex.on_fill(bix(ctx, "M5", "11:00"), 1) == flat
    r = run(mk, ex)
    assert rows(r) == [(1, m1(mk, "11:02"), m1(mk, "13:29"), 101.0, 101.5, "signal")] and r.counts["close_gap"] == 1
    assert rows(run(mk, no_gap(ex))) == [(1, m1(mk, "11:02"), m1(mk, "18:00"), 101.0, 96.8, "gap stop")]


def test_b_o5_a_fill_inside_the_flat_bar_of_an_early_close_leaves_at_its_last_m1_close():
    """The buy stop fills inside the flat bar itself (13:27: the ask high 101.5 reaches 101; the fill at max(101, the
    ask at the open 100.2) = 101.0). The trail started at the flat bar cannot exit on that bar's own close, so on_fill
    gives the flat bar (F0: the trail's cap; HV: that bar is LV, 5 ticks against an SMA of 5, which also ends the trade
    at its close): either way the exit is booked at the 13:29 close (the bid 101.5), where without the flag it would
    gap through the stop (99) at the 18:00 reopen (97.0: 96.8)."""
    ch = range_99_101(Chart())
    ch.bar("13:27", h=101.3).seg("13:28", "18:00", 101.5).seg("18:00", "24:00", 97.0)
    mk = early_close(ch)
    ctx = M.Context(mk)
    flat = bix(ctx, "M5", "13:25")
    assert not bool(np.asarray(R.orb_output(ctx, "M5")["hv"])[flat])
    for f in ("F0", "HV"):
        ex = build(ctx, f"XAUUSDm|M5|ORB|O5|{f}")
        assert ex.on_fill(flat, 1) == flat and list(ex.orders.close_gap) == [True]
        r = run(mk, ex)
        assert rows(r) == [(1, m1(mk, "13:27"), m1(mk, "13:29"), 101.0, 101.5, "signal")], f
        assert list(r.trades.bar) == [flat] and r.counts["close_gap"] == 1, f
        assert rows(run(mk, no_gap(ex))) == [(1, m1(mk, "13:27"), m1(mk, "18:00"), 101.0, 96.8, "gap stop")], f


def test_b_o5_the_flag_is_the_orders_so_an_earlier_trail_exit_before_a_hole_is_booked_at_its_close():
    """The harness's flag is per order and covers whichever of the flat bar and ``on_fill``'s trail bar decides the
    exit, so for O5 (unlike O1, above) a trail exit decided before the flat bar that a data hole follows is booked at
    that bar's last M1 close, not at the next M1 open after the hole (reading 3 counts where this can happen). s8's
    trade with the M1 bars from 13:05 to 13:30 missing: the trail fires on the 13:00 bar's close and the exit is
    booked at the 13:04 close (the bid 100.0); without the flag it fills at the 13:30 open (99.6)."""
    ch = s8()
    ch.seg("13:30", "14:00", 99.6)
    mk = ch.market(keep=~((ch.t >= ny("13:05")) & (ch.t < ny("13:30"))))
    ctx = M.Context(mk)
    ex = build(ctx, "XAUUSDm|M5|ORB|O5|F0")
    assert ex.on_fill(bix(ctx, "M5", "11:00"), 1) == bix(ctx, "M5", "13:00") < R.sessions(ctx, "M5")["flat_bar"][0]
    r = run(mk, ex)
    assert rows(r) == [(1, m1(mk, "11:02"), m1(mk, "13:04"), 101.0, 100.0, "signal")] and r.counts["close_gap"] == 1
    assert rows(run(mk, no_gap(ex))) == [(1, m1(mk, "11:02"), m1(mk, "13:30"), 101.0, 99.6, "signal")]


def test_b_event_table_and_warm_describe_the_rows_geometry():
    ch = s1()
    ctx = M.Context(ch.market())
    R.warm(ctx, R.variants("XAUUSDm"))
    for series in ("orb", "sessions", "candidates", "trail_exits"):
        for version in ("NY", "ORB-CX", "UTC-5"):
            for tf in ("M5", "M15"):
                assert (R.MODULE, "XAUUSDm", tf, M._params_key({"series": series, "version": version})) in ctx.cache
    assert (R.MODULE, "XAUUSDm", "M5", M._params_key({"series": "o4", "version": "NY"})) in ctx.cache
    assert (R.MODULE, "XAUUSDm", "M5", M._params_key({"series": "tight", "version": "NY"})) in ctx.cache
    b10, b12 = bix(ctx, "M5", "10:00"), bix(ctx, "M5", "12:00")
    t1 = R.event_table(ctx, V("XAUUSDm|M5|ORB|O1|F0"))
    assert list(t1.bar) == [b10, b12] and list(t1.taken) == [True, False] and list(t1.busy) == [False, True]
    assert list(t1.exit_bar) == [b12, -1] and t1.decided.all() and t1.allowed.all()
    assert list(t1.close_gap) == [False, False]                             # a trail exit before the flat bar
    t4 = R.event_table(ctx, V("XAUUSDm|M5|ORB|O4|F0"))
    assert list(t4.target_k) == [1, 1] and list(t4.target) == [103.0, 97.0] and list(t4.stop) == [99.0, 101.0]
    assert list(t4.close_gap) == [True, True]
    t5 = R.event_table(ctx, V("XAUUSDm|M5|ORB|O5|F0|TIGHT"))
    assert len(t5) <= 1 and set(t5.columns) >= {"bar", "placed", "until", "buy", "sell", "exit_bar", "tag",
                                                "close_gap"}
    assert t5.close_gap.all()
    assert "tight" in R.event_table(ctx, V("XAUUSDm|M5|ORB|O1|F0|TIGHT")).columns
    d = R.describe(V("BTCUSDm|M15|ORB|O5|HV"))
    assert "Binance" in d and "stop orders" in d and "16:55" in d
    # O4's 60 are past sessions with a breakout of the trade's side decided by 16:00 (reading 5), not any sessions
    assert ("once at least 60 past sessions have a breakout of that side decided by 16:00 New York, else T1"
            in R.describe(V("XAUUSDm|M5|ORB|O4|F0")))
    assert "COMEX" in R.describe(V("XAUUSDm|M5|ORB|O1|F2-4H|ORB-CX"))
    assert "UTC-5" in R.describe(V("XAUUSDm|M5|ORB|O1|F0|UTC-5"))
    assert "TIGHT" in R.describe(V("XAUUSDm|M5|ORB|O5|F0|TIGHT"))


# ───────────────────────────── (b) O2 / O3 / O4: absolute levels ─────────────────────────────

def test_b_o2_o3_targets_and_stops_are_levels_from_the_actual_fill_and_an_entry_beyond_its_target_is_dropped():
    ch = s1()
    mk = ch.market()
    ctx = M.Context(mk)
    b10, b12 = bix(ctx, "M5", "10:00"), bix(ctx, "M5", "12:00")
    E2 = build(ctx, "XAUUSDm|M5|ORB|O2|F0").entries
    assert list(E2.bar) == [b10, b12] and list(E2.side) == [1, -1]
    assert list(E2.stop_level) == [99.0, 101.0] and list(E2.target_level) == [103.0, 97.0]
    flat = R.sessions(ctx, "M5")["flat_bar"][0]
    assert list(E2.exit_bar) == [flat, flat] and np.isnan(E2.stop_dist).all() and np.isnan(E2.target_r).all()
    r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O2|F0"))
    # the long: filled at 101.7, the 12:00 open (96) gaps through its stop 99 (filled at the open, one spread charged);
    # the short at the bear label fills at 96.0, beyond its target 97: dropped (PREREG 4)
    assert rows(r) == [(1, ch.ix("10:05"), ch.ix("12:00"), 101.7, 95.8, "gap stop")]
    assert r.counts["dropped_target"] == 1 and r.counts["busy"] == 0
    assert r.trades.risk[0] == pytest.approx(2.7)                           # |fill - stop level|, not the range
    r3 = run(mk, build(ctx, "XAUUSDm|M5|ORB|O3|F0"))
    assert rows(r3) == [(1, ch.ix("10:05"), ch.ix("12:00"), 101.7, 95.8, "gap stop"),
                        (-1, ch.ix("12:05"), ch.ix("16:55"), 96.0, 96.2, "signal")]
    assert list(r3.trades.risk) == [pytest.approx(2.7), pytest.approx(5.0)]
    # x1.5: every distance from its own fill (101.8; the short's flat exit at the ask 96.3)
    r15 = run(mk, build(ctx, "XAUUSDm|M5|ORB|O3|F0"), 1.5)
    assert rows(r15) == [(1, ch.ix("10:05"), ch.ix("12:00"), 101.8, 95.7, "gap stop"),
                         (-1, ch.ix("12:05"), ch.ix("16:55"), 96.0, 96.3, "signal")]
    assert list(r15.trades.risk) == [pytest.approx(2.8), pytest.approx(5.0)]


def test_b_o2_reaches_t1_inside_a_bar():
    ch = range_99_101(Chart())
    ch.seg("10:00", "11:00", 101.5).seg("11:00", "24:00", 102.6, half=0.2).bar("11:31", h=103.1)
    mk = ch.market()
    ctx = M.Context(mk)
    r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O2|F0"))
    assert rows(r) == [(1, ch.ix("10:05"), ch.ix("11:31"), 101.7, 103.0, "target")]
    r3 = run(mk, build(ctx, "XAUUSDm|M5|ORB|O3|F0"))                        # T2 = 105 is never reached
    assert rows(r3) == [(1, ch.ix("10:05"), ch.ix("16:55"), 101.7, 102.6, "signal")]
    assert r3.trades.r[0] == pytest.approx((102.6 - 101.7) / 2.7)


# ───────────────────────────── (b) O5: the stop orders ─────────────────────────────

def s8():
    """The range 99-101; at 11:02 the ask reaches 101 (the buy stop fills at 101.0); the price runs to 104, falls to
    100 at 13:00 (below the trail, above the stop 99) and to 98 at 14:00 (past the sell stop, cancelled by the fill)."""
    ch = range_99_101(Chart())
    ch.bar("11:02", h=101.3).seg("11:03", "12:00", 101.5).seg("12:00", "13:00", 104.0)
    ch.seg("13:00", "14:00", 100.0).seg("14:00", "24:00", 98.0)
    return ch


def test_b_o5_oco_stop_orders_from_10_00_the_trail_from_the_fills_bar_and_one_trade_a_day():
    ch = s8()
    mk = ch.market()
    ctx = M.Context(mk)
    ex = build(ctx, "XAUUSDm|M5|ORB|O5|F0")
    O = ex.orders
    assert ex.entries is None and ex.on_fill is not None and len(O) == 1
    assert int(O.bar[0]) == bix(ctx, "M5", "09:55") and int(O.until[0]) == ny("16:00")   # placed at 10:00
    assert (O.buy[0], O.sell[0], O.buy_stop[0], O.sell_stop[0]) == (101.0, 99.0, 99.0, 101.0)
    assert int(O.exit_bar[0]) == R.sessions(ctx, "M5")["flat_bar"][0] and int(O.tag[0]) == T0 // DAY
    r = run(mk, ex)
    # the buy fills at max(101, the ask at the open 100.2) inside 11:02; the trail (started at the 11:00 bar) exits at
    # the 13:00 bar's close; the sell side was cancelled by the fill, so 14:00's fall opens nothing
    assert rows(r) == [(1, ch.ix("11:02"), ch.ix("13:05"), 101.0, 100.0, "signal")]
    assert list(r.trades.bar) == [bix(ctx, "M5", "11:00")] and r.trades.risk[0] == pytest.approx(2.0)
    assert r.counts["candidates"] == 1 and r.counts["taken"] == 1 and r.counts["unfilled"] == 0
    assert ex.on_fill(bix(ctx, "M5", "11:00"), 1) == bix(ctx, "M5", "13:00")
    # M15 the same, from the 11:00 M15 bar
    r = run(mk, build(ctx, "XAUUSDm|M15|ORB|O5|F0"))
    assert rows(r) == [(1, ch.ix("11:02"), ch.ix("13:15"), 101.0, 100.0, "signal")]


def test_b_o5_a_touch_after_16_00_does_not_fill_and_a_gap_fills_at_the_open():
    ch = range_99_101(Chart())
    ch.seg("16:10", "24:00", 102.0)
    mk = ch.market()
    r = run(mk, build(M.Context(mk), "XAUUSDm|M5|ORB|O5|F0"))
    assert len(r.trades) == 0 and r.counts["unfilled"] == 1
    ch = range_99_101(Chart())
    ch.seg("11:00", "24:00", 97.5)                                          # gaps below the sell stop 99
    mk = ch.market()
    r = run(mk, build(M.Context(mk), "XAUUSDm|M5|ORB|O5|F0"))
    assert rows(r) == [(-1, ch.ix("11:00"), ch.ix("16:55"), 97.5, 97.7, "signal")]   # min(99, bid 97.5)
    assert r.trades.risk[0] == pytest.approx(101.0 - 97.5)


# ───────────────────────────── (c) filters ─────────────────────────────

def test_c_hv_and_lv_read_the_label_bars_volume_against_its_sma20_with_the_bar_included():
    ch = s1()
    ctx = M.Context(ch.market())
    b10 = bix(ctx, "M5", "10:00")
    hv = np.asarray(R.orb_output(ctx, "M5")["hv"])
    assert not hv[b10]                                                     # 5 ticks against an SMA of 5: not above
    assert len(build(ctx, "XAUUSDm|M5|ORB|O1|HV").entries) == 0
    assert list(build(ctx, "XAUUSDm|M5|ORB|O1|LV").entries.bar) == [b10]
    ch.n[ch.ix("10:00"):ch.ix("10:05")] = 10.0                             # 50 ticks: SMA (19 x 5 + 50) / 20 = 7.25
    ctx = M.Context(ch.market())
    assert bool(np.asarray(R.orb_output(ctx, "M5")["hv"])[b10])
    assert list(build(ctx, "XAUUSDm|M5|ORB|O1|HV").entries.bar) == [b10]
    # LV refuses the HV long, so the (LV) bear label finds no trade open and opens the short (reading 2)
    assert list(build(ctx, "XAUUSDm|M5|ORB|O1|LV").entries.bar) == [bix(ctx, "M5", "12:00")]
    for rule in ("O2", "O3", "O4"):                                        # the bear label (5 ticks) is LV
        assert list(build(ctx, f"XAUUSDm|M5|ORB|{rule}|HV").entries.bar) == [b10]
        assert list(build(ctx, f"XAUUSDm|M5|ORB|{rule}|LV").entries.bar) == [bix(ctx, "M5", "12:00")]


def test_c_f2_and_lo_gate_the_label_at_its_close_a_refused_label_blocks_nothing_and_no_trade_is_closed():
    ch = s1()
    mk = ch.market()
    ctx = M.Context(mk)
    b10, b12 = bix(ctx, "M5", "10:00"), bix(ctx, "M5", "12:00")
    asked = masks(ctx, {"F2-4H": lambda n: (np.zeros(n), np.ones(n))})    # longs refused everywhere
    ex = build(ctx, "XAUUSDm|M5|ORB|O1|F2-4H")
    assert asked == [("M5", "F2-4H")]
    # the long is refused, so the bear label finds no trade open: a short (the script, whose long stays open, would not)
    assert rows(run(mk, ex)) == [(-1, ch.ix("12:05"), ch.ix("16:55"), 96.0, 96.2, "signal")]
    asked.clear()
    ex = build(ctx, "XAUUSDm|M5|ORB|O1|HV+F2-4H")
    assert asked == [("M5", "F2-4H")] and len(ex.entries) == 0              # both labels are LV
    only_at_label = np.zeros(len(ctx.bars("M5")), bool)
    only_at_label[b10] = True
    masks(ctx, {"F2-1D": lambda n: (only_at_label, np.zeros(n))})         # true only on the label's bar
    f2 = build(ctx, "XAUUSDm|M5|ORB|O1|F2-1D")
    f0 = build(ctx, "XAUUSDm|M5|ORB|O1|F0")
    assert list(f2.entries.bar) == [b10] and list(f2.entries.exit_bar) == list(f0.entries.exit_bar) == [b12]
    asked = masks(ctx, {})
    lo = build(ctx, "XAUUSDm|M5|ORB|O3|LO")
    assert asked == [("M5", "LO")] and list(lo.entries.side) == [1]
    assert build(ctx, "XAUUSDm|M5|ORB|O3|F0").entries.side.tolist() == [1, -1]


def test_c_o5_filters_f2_and_lo_at_the_placement_hv_at_the_fill_bars_close():
    ch = s8()
    mk = ch.market()
    ctx = M.Context(mk)
    p = bix(ctx, "M5", "09:55")

    def no_longs_at(bar):
        def f(n):
            al = np.ones(n, bool)
            al[bar] = False
            return al, np.ones(n, bool)
        return f
    asked = masks(ctx, {"F2-4H": no_longs_at(p)})
    ex = build(ctx, "XAUUSDm|M5|ORB|O5|F2-4H")
    assert asked == [("M5", "F2-4H")]
    O = ex.orders
    assert np.isnan(O.buy[0]) and np.isnan(O.buy_stop[0]) and O.sell[0] == 99.0 and O.sell_stop[0] == 101.0
    # no buy side: the touch of 101 fills nothing; 14:00's gap to 98 fills the sell stop at min(99, 98)
    assert rows(run(mk, ex)) == [(-1, ch.ix("14:00"), ch.ix("16:55"), 98.0, 98.2, "signal")]
    masks(ctx, {})
    assert np.isnan(build(ctx, "XAUUSDm|M5|ORB|O5|LO").orders.sell[0])
    assert rows(run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|LO"))) == rows(run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|F0")))
    # HV: the fill's bar (11:00, 5 ticks) is LV, so the trade ends at that bar's close (the 11:05 open, bid 101.5)
    r = run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|HV"))
    assert rows(r) == [(1, ch.ix("11:02"), ch.ix("11:05"), 101.0, 101.5, "signal")]
    ch.n[ch.ix("11:00"):ch.ix("11:05")] = 10.0                             # now that bar is HV: kept, as F0
    mk = ch.market()
    ctx = M.Context(mk)
    masks(ctx, {})
    assert rows(run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|HV"))) == rows(run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|F0")))
    assert rows(run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|HV+F2-4H"))) == rows(run(mk, build(ctx, "XAUUSDm|M5|ORB|O5|F0")))


def test_c_orb_cx_is_the_comex_range_and_its_orders_live_from_its_end_to_16_00():
    ch = Chart()
    ch.bar("08:25", h=101.0).bar("08:40", l=99.0)
    mk = ch.market()
    ctx = M.Context(mk)
    S5, S15 = R.sessions(ctx, "M5", R.CX), R.sessions(ctx, "M15", R.CX)
    assert (S5["or_high"][0], S5["or_low"][0]) == (101.0, 99.0)
    assert (S15["or_high"][0], S15["or_low"][0]) == (100.5, 99.0)          # M15: the bars opening 08:30 and 08:45
    assert S5["start_bar"][0] == bix(ctx, "M5", "08:20") and S15["start_bar"][0] == bix(ctx, "M15", "08:30")
    o5 = build(ctx, "XAUUSDm|M5|ORB|O5|F0|ORB-CX").orders
    o15 = build(ctx, "XAUUSDm|M15|ORB|O5|F0|ORB-CX").orders
    assert int(o5.bar[0]) == bix(ctx, "M5", "08:45") and ctx.bars("M5").tc[o5.bar[0]] == ny("08:50")
    assert int(o15.bar[0]) == bix(ctx, "M15", "08:45") and ctx.bars("M15").tc[o15.bar[0]] == ny("09:00")
    assert int(o5.until[0]) == int(o15.until[0]) == ny("16:00")
    assert R.sessions(ctx, "M5", R.CX)["flat_bar"][0] == R.sessions(ctx, "M5")["flat_bar"][0]


def test_c_the_literal_utc5_clock_is_an_hour_late_in_summer_and_keeps_new_yorks_cut_and_flat_time():
    t0 = TM.s_of("2019-07-08")                                              # a Monday in summer (EDT, UTC-4)
    ch = Chart(t0=t0)
    ctx = M.Context(ch.market())
    for tf in ("M5", "M15"):
        a, b = R.sessions(ctx, tf), R.sessions(ctx, tf, R.UTC5)
        assert (M.ny_minute(a["t0"])[0], M.ny_minute(b["t0"])[0]) == (570, 630)   # 09:30 vs 10:30 New York
        assert a["entry_end_s"][0] == b["entry_end_s"][0] == ny("16:00", 0, t0 // DAY)
        assert a["flat_bar"][0] == b["flat_bar"][0]
    w = Chart()                                                             # in winter the two clocks agree
    ctxw = M.Context(w.market())
    assert R.sessions(ctxw, "M5")["t0"][0] == R.sessions(ctxw, "M5", R.UTC5)["t0"][0] == ny("09:30")


def test_c_btc_on_all_seven_days_adds_the_weekend_sessions():
    ch = Chart(days=7)                                                      # Monday 2019-01-07 .. Sunday
    ctx = M.Context(ch.market("BTCUSDm"))
    ctx.volume = lambda tf, source="auto": ctx.bars(tf).vol                # no Binance file needed here
    for tf in ("M5", "M15"):
        wd, d7 = R.sessions(ctx, tf), R.sessions(ctx, tf, R.D7)
        assert len(wd["day"]) == 5 and len(d7["day"]) == 7
        assert set(((d7["day"] + 3) % 7).tolist()) == set(range(7))
        assert set(((wd["day"] + 3) % 7).tolist()) == set(range(5))
    assert isinstance(build(ctx, "BTCUSDm|M5|ORB|O1|F0|7D"), M.Exec)


# ───────────────────────────── a synthetic 300-day market ─────────────────────────────

SYN_START = "2019-01-07"
SYN_DAYS = 300


def synthetic_m1(symbol="XAUUSDm", days=SYN_DAYS, seed=11):
    """Continuous M1 bars from 2019-01-07 with New York-hours volatility (and a wide opening range on some days), so
    that both sides break out, targets are hit and missed, some ranges are not TIGHT and the MA200s exist."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(SYN_START) + 60 * np.arange(days * 1440, dtype=np.int64)
    loc = M.ny_local(t)
    minute = (loc % DAY) // 60
    vol = np.where((minute >= 570) & (minute < 960), 0.12, 0.05)
    wide = rng.random(days + 2) < 0.12
    day_ix = (loc // DAY) - (loc[0] // DAY)
    vol = np.where((minute >= 570) & (minute < 600) & wide[day_ix], 0.6, vol)
    p0 = 1300.0 if symbol == "XAUUSDm" else 4000.0
    scale = 1.0 if symbol == "XAUUSDm" else 3.0
    c = p0 + scale * np.cumsum(rng.normal(0.0, 1.0, len(t)) * vol + 0.0004)
    o = np.concatenate(([p0], c[:-1]))
    h = np.maximum(o, c) + scale * np.abs(rng.normal(0.0, 0.05, len(t)))
    l = np.minimum(o, c) - scale * np.abs(rng.normal(0.0, 0.05, len(t)))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(len(t), 0.2 * scale),
            "n": rng.integers(1, 30, len(t)).astype(np.float64)}


@pytest.fixture(scope="module")
def synth():
    m1 = synthetic_m1()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        full = M.Context(M.TMarket2("XAUUSDm", m1))
    return full, m1


def truncated(m1, cut_s, symbol="XAUUSDm"):
    """The same market with every M1 bar at or after ``cut_s`` removed (its end at ``cut_s``)."""
    keep = m1["t"] < cut_s
    return M.Context(M.TMarket2(symbol, {k: v[keep] for k, v in m1.items()}, cut_s))


def test_c_tight_is_session_hunters_adr_test_and_gates_o1_and_o5(synth):
    ctx = synth[0]
    for tf in ("M5", "M15"):
        S = R.sessions(ctx, tf)
        b = ctx.bars(tf)
        adr = SHI.day_state(b.t, b.o, b.h, b.l, b.c, R.TF_MIN[tf])["adr"].to_numpy()[S["end_bar"]]
        tight = R.tight_sessions(ctx, tf)
        with np.errstate(invalid="ignore"):
            assert np.array_equal(tight, S["valid"] & np.isfinite(adr) & (S["width"] < 0.5 * adr))
        assert 5 < int((~tight).sum()) < len(tight) - 50                     # both kinds exist
        f0 = R.o1_trades(ctx, tf, R.Row("O1", "F0"))
        tt = R.o1_trades(ctx, tf, R.Row("O1", "F0", tight=True))
        assert tight[tt["session"]].all()
        assert set(tt["bar"]) == {x for x, j in zip(f0["bar"], f0["session"]) if tight[j]}
        o0 = build(ctx, f"XAUUSDm|{tf}|ORB|O5|F0").orders
        ot = build(ctx, f"XAUUSDm|{tf}|ORB|O5|F0|TIGHT").orders
        keep = np.isin(o0.tag, S["day"][tight])
        assert np.array_equal(ot.bar, o0.bar[keep]) and np.array_equal(ot.buy, o0.buy[keep])


def test_c_real_filters_on_the_synthetic_market_gate_exactly_the_labels_they_allow(synth):
    ctx = synth[0]
    for tf in ("M5", "M15"):
        C = R.candidates(ctx, tf)
        base = build(ctx, f"XAUUSDm|{tf}|ORB|O2|F0").entries
        hv = np.asarray(R.orb_output(ctx, tf)["hv"], bool)
        for f in ("HV", "F2-4H", "F2-1D", "HV+F2-4H", "LO", "LV"):
            al, ash = R.entry_allow(ctx, tf, f)
            if f in ("F2-4H", "F2-1D", "LO"):
                a2, s2 = ctx.allow(tf, f)
                assert np.array_equal(al, a2) and np.array_equal(ash, s2)
            if f == "HV+F2-4H":
                a2, s2 = ctx.allow(tf, "F2-4H")
                assert np.array_equal(al, hv & a2) and np.array_equal(ash, hv & s2)
            keep = np.where(base.side == 1, al[base.bar], ash[base.bar])
            got = build(ctx, f"XAUUSDm|{tf}|ORB|O2|{f}").entries
            for k in ("bar", "side", "stop_level", "target_level", "exit_bar", "tag"):
                assert np.array_equal(getattr(got, k), getattr(base, k)[keep]), (tf, f, k)
            assert 0 < keep.sum() < len(keep), (tf, f)
        assert len(base) == int(C["ok"].sum())                             # every ok label of the day is a candidate


# ───────────────────────────── (d) O4's target from the past breakouts ─────────────────────────────

def test_d_o4_choice_needs_60_past_breakouts_and_takes_the_furthest_level_at_50_percent():
    n = 70
    has = np.ones(n, bool)
    hit = np.zeros((n, 3), bool)
    hit[:, 0] = True                                                        # T1 always
    hit[::2, 1] = True                                                      # T2 every other session: 50%
    hit[:7, 2] = True                                                       # T3 rarely
    k, cnt, rate = R.o4_choice(has, hit)
    assert list(cnt[:3]) == [0, 1, 2] and cnt[60] == 60 and np.isnan(rate[0]).all()
    assert (k[:60] == 1).all()                                              # fewer than 60 past breakouts: T1
    assert k[60] == 2 and rate[60, 1] == 0.5                                 # T2 at exactly 50% counts
    assert k[61] == 2 and rate[61, 1] == pytest.approx(31 / 61)
    hit2 = hit.copy()
    hit2[:, 1] = hit2[:, 2] = True                                          # T3 always: the furthest
    assert R.o4_choice(has, hit2)[0][65] == 3
    hit3 = np.zeros((n, 3), bool)                                           # nothing at 50%: T1
    assert (R.o4_choice(has, hit3)[0] == 1).all()
    has2 = has.copy()
    has2[::2] = False                                                       # only sessions with a breakout count
    k2, c2, _ = R.o4_choice(has2, hit2)
    assert c2[-1] == 34 and c2[1] == 0 and c2[2] == 1 and (k2 == 1).all()


def test_d_o4_targets_equal_a_brute_force_count_over_the_past_sessions(synth):
    ctx = synth[0]
    for tf in ("M5", "M15"):
        S = R.sessions(ctx, tf)
        b = ctx.bars(tf)
        T4 = R.o4_targets(ctx, tf)
        nS = len(S["day"])
        for key, side, lv in (("up", 1, ("u1", "u2", "u3")), ("dn", -1, ("d1", "d2", "d3"))):
            hist = []                                                       # (past session, hits) in order
            for j in range(nS):
                ks = [h for h in hist]
                n = len(ks)
                want = 1
                if n >= 60:
                    rates = [sum(x[i] for x in ks) / n for i in range(3)]
                    q = [i + 1 for i in range(3) if rates[i] >= 0.5]
                    want = max(q) if q else 1
                assert T4[f"k_{key}"][j] == want and T4[f"n_{key}"][j] == n, (tf, key, j)
                L = int(S[f"label_{key}_bar"][j])
                Fb = int(S["flat_bar"][j])
                if L >= 0 and Fb >= 0 and b.tc[L] <= S["entry_end_s"][j]:
                    seg = slice(L + 1, Fb + 1)
                    hist.append([bool(b.h[seg].max() >= S[lv[i]][j]) if side == 1 else
                                 bool(b.l[seg].min() <= S[lv[i]][j]) for i in range(3)] if L < Fb else
                                [False, False, False])
        assert (T4["n_up"][-1] >= 60) and len(set(T4["k_up"][T4["n_up"] >= 60].tolist())) >= 1
    def o4_levels(c):
        E = build(c, "XAUUSDm|M5|ORB|O4|F0").entries
        S, T4, C = R.sessions(c, "M5"), R.o4_targets(c, "M5"), R.candidates(c, "M5")
        j = C["session"][C["ok"]]
        k = np.where(E.side == 1, T4["k_up"][j], T4["k_dn"][j])
        lv = np.where(E.side == 1, np.stack([S["u1"], S["u2"], S["u3"]], 1)[j, k - 1],
                      np.stack([S["d1"], S["d2"], S["d3"]], 1)[j, k - 1])
        assert np.array_equal(E.target_level, lv) and (k[:10] == 1).all()
        o2 = build(c, "XAUUSDm|M5|ORB|O2|F0").entries
        assert np.array_equal(E.bar, o2.bar) and np.array_equal(E.stop_level, o2.stop_level)
        return k, E, o2
    k, E, o2 = o4_levels(ctx)
    # on this random walk T2 is reached after about a third of the breakouts: O4 is O2 here
    assert (k == 1).all() and np.array_equal(E.target_level, o2.target_level)
    # the same market with injected after-breakout hits (T1 and T2 always, T3 never): from the 61st breakout of a
    # side on, O4 targets T2
    H = R.after_hits(ctx, "M5")
    fake = dict(H)
    for key in ("up", "dn"):
        fake[f"hit_{key}"] = np.repeat(np.asarray([[True, True, False]]), len(H["complete"]), axis=0) & \
            np.asarray(H[f"has_{key}"])[:, None]
    ctx2 = M.Context(ctx.mk)
    assert ctx2.get(R.MODULE, "M5", {"series": "after_hits", "version": "NY"}, lambda: fake) is fake
    k2, E2, o2 = o4_levels(ctx2)
    T4 = R.o4_targets(ctx2, "M5")
    C = R.candidates(ctx2, "M5")
    j = C["session"][C["ok"]]
    n_past = np.where(E2.side == 1, T4["n_up"][j], T4["n_dn"][j])
    assert np.array_equal(k2, np.where(n_past >= 60, 2, 1)) and (k2 == 2).sum() > 30 and (k2 == 1).sum() > 30


# ───────────────────────────── one trade per side per day, one per day for O5 ─────────────────────────────

def test_d_one_trade_per_side_per_day_for_o1_to_o4_and_one_per_day_for_o5(synth):
    ctx = synth[0]
    mk = ctx.mk
    a, z = "2019-02-01", "2019-10-01"
    for v in R.variants("XAUUSDm"):
        if v.params["version"] != "NY" or v.params["filter"] not in ("F0", "LV", "LO") or v.params["range"] != "every":
            continue
        r = M.run_exec(mk, R.build(v, ctx), a, z)
        tr = r.trades
        assert len(tr) > 20, v.id
        per = tr.groupby(["tag", "side"]).size()
        assert per.max() == 1, v.id                                         # one label per side per day
        if v.params["rule"] == "O5":
            assert tr.groupby("tag").size().max() == 1, v.id                # one cancels the other
        if v.params["rule"] == "O1":
            assert r.counts["busy"] == 0 and r.counts["candidates"] == len(tr)
        if v.params["filter"] == "LO":
            assert (tr.side == 1).all()
        exit_ny = M.ny_local(np.asarray([int(x.timestamp()) for x in tr.exit_time], np.int64))
        entry_ny = M.ny_local(np.asarray([int(x.timestamp()) for x in tr.entry_time], np.int64))
        assert ((exit_ny % DAY) // 60 <= R.FLAT_AT).all() and (exit_ny // DAY == entry_ny // DAY).all(), v.id
        assert ((entry_ny % DAY) // 60 >= 600).all() and ((entry_ny % DAY) // 60 <= R.ENTRY_END).all(), v.id


def test_d_close_gap_changes_nothing_where_an_m1_bar_opens_at_every_close(synth):
    """The synthetic market has an M1 bar at every minute, so no exit decision is followed by a gap: with their
    ``close_gap`` flags (O1's at its flat exits, every O2-O5 row's) the rows give the trades, counts and marks they
    give without them."""
    ctx = synth[0]
    for vid in ("XAUUSDm|M5|ORB|O1|F0", "XAUUSDm|M15|ORB|O3|F0", "XAUUSDm|M5|ORB|O5|F0", "XAUUSDm|M15|ORB|O5|HV"):
        ex = build(ctx, vid)
        flags = ex.entries.close_gap if ex.entries is not None else ex.orders.close_gap
        assert flags.any(), vid
        r1, r0 = (M.run_exec(ctx.mk, x, "2019-02-01", "2019-06-01") for x in (ex, no_gap(ex)))
        assert len(r1.trades) > 20 and r1.trades.equals(r0.trades) and r1.counts == r0.counts, vid
        assert np.array_equal(r1.ec, r0.ec) and np.array_equal(r1.ew, r0.ew) and r1.counts["close_gap"] == 0, vid


# ───────────────────────────── (e) causality ─────────────────────────────

def _known(b, x, upto_s):
    x = np.asarray(x, np.int64)
    return np.where((x >= 0) & (b.tc[np.maximum(x, 0)] <= upto_s), x, -1)


def _known_gap(flag, known_exit, tag, upto_s):
    """A row's ``close_gap`` where it is known by ``upto_s``: its exit is known and its session's flat time (16:55 New
    York of the date ``tag``) has passed, so whether that exit is the flat bar is known; False elsewhere."""
    tag = np.asarray(tag, np.int64)
    cut = np.asarray(M.utc_of_ny(tag, R.FLAT_AT), np.int64) if len(tag) else np.zeros(0, np.int64)
    return np.asarray(flag, bool) & (np.asarray(known_exit) >= 0) & (cut <= upto_s)


def decisions(ctx, v, upto_s):
    """Every decision a row takes by ``upto_s``: entries decided at bars closing at or before it (bar, side, levels,
    tag) with their exit decision when that is known by then (else -1) and its ``close_gap`` once the flat time has
    passed; orders whose post-session bar opens before it (the port counts the session on that bar, opening at the
    instant the range's last bar closes: the module docstring) with their bar, expiry, levels, tag, exit and
    ``close_gap``; and O5's exit for a fill in each bar of the last sessions before ``upto_s``."""
    ex = R.build(v, ctx)
    b = ctx.bars(v.tf)
    if ex.entries is not None:
        E = ex.entries
        m = b.tc[E.bar] <= upto_s
        out = {k: getattr(E, k)[m] for k in ("bar", "side", "stop_level", "target_level", "tag")}
        xb = _known(b, E.exit_bar, upto_s)
        out["exit_bar"] = xb[m]
        out["close_gap"] = _known_gap(E.close_gap, xb, E.tag, upto_s)[m]
        return out
    O = ex.orders
    assert (O.bar + 1 < len(b)).all() and (b.tc[O.bar] <= b.t[O.bar + 1]).all()
    m = b.t[O.bar + 1] < upto_s
    out = {k: getattr(O, k)[m] for k in ("bar", "until", "buy", "sell", "buy_stop", "sell_stop", "tag")}
    xb = _known(b, O.exit_bar, upto_s)
    out["exit_bar"] = xb[m]
    out["close_gap"] = _known_gap(O.close_gap, xb, O.tag, upto_s)[m]
    S = R.sessions(ctx, v.tf, v.params["version"])
    js = np.flatnonzero(b.t[S["post_bar"]] < upto_s)[-3:]                  # the sessions counted by then
    fills = []
    for j in js:
        for k in range(int(S["post_bar"][j]), len(b)):
            if b.tc[k] > upto_s or (S["flat_bar"][j] >= 0 and k > S["flat_bar"][j]):
                break
            fills.append([k] + [int(_known(b, [ex.on_fill(k, d)], upto_s)[0]) for d in (1, -1)])
    out["fills"] = np.asarray(fills, np.int64).reshape(-1, 3)
    return out


def same_decisions(full, part, symbol, upto_s):
    for tf in ("M5", "M15"):
        bf, bp = full.bars(tf), part.bars(tf)
        k = int((bp.tc <= upto_s).sum())
        assert k > 0 and int((bf.tc <= upto_s).sum()) == k
        for f in ("t", "tc", "o", "h", "l", "c", "vol"):
            assert np.array_equal(getattr(bf, f)[:k], getattr(bp, f)[:k])
    n = 0
    for v in R.variants(symbol):
        a, b = decisions(full, v, upto_s), decisions(part, v, upto_s)
        assert a.keys() == b.keys()
        for key in a:
            assert np.array_equal(a[key], b[key], equal_nan=np.asarray(a[key]).dtype.kind == "f"), (v.id, key)
        n += 1
    return n


def test_e_decisions_up_to_t_do_not_change_when_the_bars_after_t_are_removed(synth):
    full, m1 = synth
    days = ("2019-08-05", "2019-09-17", "2019-10-30")                       # three weekdays, every cut on M15's grid
    cuts = [ny(hh, 0, TM.s_of(d) // DAY) for d in days for hh in ("10:00", "13:45", "16:30")]
    cuts += [ny("17:15", 0, TM.s_of("2019-08-05") // DAY), TM.s_of("2019-06-15")]
    for cut in cuts:
        assert cut % 900 == 0
        assert same_decisions(full, truncated(m1, cut), "XAUUSDm", cut) == 82


# ───────────────────────────── (f) claims 6-9 ─────────────────────────────

class FakeEv:
    """What the claim functions read of the driver's Evidence: the symbols, the two windows, the contexts and the
    results rows (``dev`` / ``val`` indexed by id)."""

    def __init__(self, ctxs, dev=None, val=None, windows=("dev", "val")):
        self.symbols = list(ctxs)
        self._ctx = dict(ctxs)
        self.windows = windows
        self.dev = pd.DataFrame(columns=["net"]) if dev is None else dev
        self.val = pd.DataFrame(columns=["net"]) if val is None else val

    def context(self, symbol):
        return self._ctx[symbol]


@pytest.fixture
def synth_windows(monkeypatch):
    monkeypatch.setitem(M.WINDOWS, "dev", ("2019-03-01", "2019-07-01"))
    monkeypatch.setitem(M.WINDOWS, "val", ("2019-07-01", "2019-10-15"))


def _brute_sessions(ctx, tf, start, end):
    """Per complete session opening in [start, end): from the port's days frame and the M1 bars only, the first
    label decided by 16:00 (side, bar), the 16:00 close (the close of the last M1 bar before 16:00 New York), the
    dashboard hits and the after-breakout hits (the M1 extremes from the label bar's close to the flat time: the
    close of the last chart bar closing at or before 16:55, i.e. 16:55 on M5 and 16:45 on M15)."""
    mk, b = ctx.mk, ctx.bars(tf)
    d = R.orb_output(ctx, tf)["days"]
    out = []
    for r in d.itertuples(index=False):
        t0 = int(b.t[r.start_bar])
        if not (TM.s_of(start) <= t0 < TM.s_of(end)):
            continue
        day = int(M.ny_date(np.asarray([t0]))[0])
        cut16, cut1655 = int(M.utc_of_ny(day, 960)), int(M.utc_of_ny(day, 1015))
        cut1655 = int(b.tc[np.searchsorted(b.tc, cut1655, side="right") - 1])     # M15: 16:45
        labs = [(int(x), s) for x, s in ((r.label_up_bar, 1), (r.label_dn_bar, -1)) if x >= 0 and b.tc[x] <= cut16]
        i16 = int(np.searchsorted(mk.t, cut16)) - 1
        c16 = float(mk.c[i16])
        side16 = 1 if c16 > r.or_high else (-1 if c16 < r.or_low else 0)
        after = {}
        for x, s in labs:
            m = (mk.t >= b.tc[x]) & (mk.t < cut1655)
            if s == 1:
                after[1] = [bool(m.any() and mk.h[m].max() >= getattr(r, f"u{k}")) for k in (1, 2, 3)]
            else:
                after[-1] = [bool(m.any() and mk.l[m].min() <= getattr(r, f"d{k}")) for k in (1, 2, 3)]
        out.append({"labs": sorted(labs), "side16": side16, "after": after,
                    "dash": [getattr(r, f"hit_{x}") for x in ("u1", "u2", "u3", "d1", "d2", "d3")]})
    return out


def test_f_claim6_counts_the_1600_close_beyond_the_first_breakouts_side(synth, synth_windows):
    ctx = synth[0]
    ev = FakeEv({"XAUUSDm": ctx})
    got = R.claim6(ev)
    assert len(got) == 4 and {g["symbol"] for g in got} == {"XAUUSDm"}
    for tf in ("M5", "M15"):
        for w, col in (("dev", "dev"), ("val", "val")):
            a, z = M.window_span(w, "XAUUSDm")
            st = R.direction_stats(ctx, tf, a, z)
            br = _brute_sessions(ctx, tf, a, z)
            bo = [x for x in br if x["labs"]]
            same = sum(x["side16"] == x["labs"][0][1] for x in bo)
            opp = sum(x["side16"] == -x["labs"][0][1] for x in bo)
            assert st == {"sessions": len(br), "breakouts": len(bo), "same": same, "opposite": opp,
                          "inside": len(bo) - same - opp}
            assert st["breakouts"] > 30 and st["same"] > 0 and st["opposite"] > 0
            part = [g for g in got if g["rows"].startswith(tf) and "more than half" in g["part"]][0]
            assert part[f"{col}_ok"] == (2 * same > len(bo)) and part[col].startswith(f"{same}/{len(bo)} ")
            part = [g for g in got if g["rows"].startswith(tf) and "more often" in g["part"]][0]
            assert part[f"{col}_ok"] == (same > opp)
    for g in got:
        assert set(g) == {"part", "symbol", "rows", "dev", "val", "dev_ok", "val_ok", "note"}


def test_f_claim8_compares_the_dashboards_unconditional_rates_with_the_rates_after_a_breakout(synth, synth_windows):
    ctx = synth[0]
    got = R.claim8(FakeEv({"XAUUSDm": ctx}))
    assert len(got) == 2 * 3
    for tf in ("M5", "M15"):
        a, z = M.window_span("dev", "XAUUSDm")
        st = R.hit_rate_stats(ctx, tf, a, z)
        br = _brute_sessions(ctx, tf, a, z)
        n_u, n_a = 2 * len(br), sum(len(x["labs"]) for x in br)
        assert (st["n_dashboard"], st["n_after"]) == (n_u, n_a)
        for k in (1, 2, 3):
            x_u = sum(x["dash"][k - 1] + x["dash"][k + 2] for x in br)
            x_a = sum(x["after"][s][k - 1] for x in br for s in x["after"])
            t = st[f"T{k}"]
            assert (t["dashboard_hits"], t["after_hits"]) == (x_u, x_a)
            p = (x_u + x_a) / (n_u + n_a)
            z_ = (x_a / n_a - x_u / n_u) / np.sqrt(p * (1 - p) * (1 / n_u + 1 / n_a)) if 0 < p < 1 else np.nan
            assert t["z"] == pytest.approx(z_, nan_ok=True)
            part = [g for g in got if g["rows"].startswith(tf) and g["part"].startswith(f"T{k}:")][0]
            assert part["dev_ok"] == bool(np.isfinite(z_) and abs(z_) > 1.96)
        assert st["T1"]["after_rate"] > st["T1"]["dashboard_rate"]          # a breakout day reaches T1 more often


def test_f_claim9_the_literal_clocks_range_is_late_on_every_daylight_saving_day(monkeypatch):
    t0 = TM.s_of("2019-02-25")                                              # DST starts on Sunday 2019-03-10
    m2 = synthetic_m1(days=33, seed=4)
    m2["t"] = m2["t"] - m2["t"][0] + t0
    ctx = M.Context(M.TMarket2("XAUUSDm", m2))
    monkeypatch.setitem(M.WINDOWS, "dev", ("2019-02-25", "2019-03-10"))
    monkeypatch.setitem(M.WINDOWS, "val", ("2019-03-10", "2019-03-29"))
    names = ["XAUUSDm|M5|ORB|O1|F0", "XAUUSDm|M15|ORB|O1|F0", "XAUUSDm|M5|ORB|O1|F0|UTC-5",
             "XAUUSDm|M15|ORB|O1|F0|UTC-5"]
    dev = pd.DataFrame({"net": [5.0, -4.0, 2.0, -3.0]}, index=names)        # synthetic results: not a rule's
    val = pd.DataFrame({"net": [5.0, 1.0, 2.0, -3.0]}, index=names)
    got = R.claim9(FakeEv({"XAUUSDm": ctx}, dev, val))
    geo, res = got
    a = R.clock_stats(ctx, "M5", *M.window_span("dev", "XAUUSDm"))
    b = R.clock_stats(ctx, "M5", *M.window_span("val", "XAUUSDm"))
    assert a == {"sessions": 10, "late": 0, "on_time": 10, "dst": 0, "late_not_dst": 0, "dst_not_late": 0}
    assert b == {"sessions": 14, "late": 14, "on_time": 0, "dst": 14, "late_not_dst": 0, "dst_not_late": 0}
    assert geo["dev_ok"] and geo["val_ok"] and geo["val"].startswith("14/14 ")
    assert (res["dev"], res["val"], res["dev_ok"], res["val_ok"]) == ("1/2", "2/2", False, True)
    from backtesting.research import tradeiq2 as D
    with pytest.raises(D.ClaimError):
        R.claim9(FakeEv({"XAUUSDm": ctx}, dev.iloc[:3], val.iloc[:3]))


def test_f_claim7_hv_against_lv_on_the_results_and_the_geometry_for_information(synth, synth_windows):
    ctx = synth[0]
    ids = [(f"XAUUSDm|{tf}|ORB|{r}|HV", f"XAUUSDm|{tf}|ORB|{r}|LV") for tf in ("M5", "M15")
           for r in ("O1", "O2", "O3", "O4")]
    net_d = {}
    net_v = {}
    for i, (h, lv) in enumerate(ids):                                        # synthetic results: HV wins 5 / 8, 3 / 8
        net_d[h], net_d[lv] = (2.0, 1.0) if i < 5 else (1.0, 2.0)
        net_v[h], net_v[lv] = (2.0, 1.0) if i < 3 else (1.0, 2.0)
    dev = pd.DataFrame({"net": pd.Series(net_d)})
    val = pd.DataFrame({"net": pd.Series(net_v)})
    got = R.claim7(FakeEv({"XAUUSDm": ctx}, dev, val))
    assert (got[0]["dev"], got[0]["val"], got[0]["dev_ok"], got[0]["val_ok"]) == ("5/8", "3/8", True, False)
    assert len(got) == 3 and all(np.isnan(g["dev_ok"]) and "HV" in g["dev"] and "LV" in g["dev"] for g in got[1:])
    from backtesting.research import tradeiq2 as D
    with pytest.raises(D.ClaimError):
        R.claim7(FakeEv({"XAUUSDm": ctx}, dev.iloc[1:], val))


def test_f_the_driver_finds_the_claim_functions():
    from backtesting.research import tradeiq2 as D
    for n in (6, 7, 8, 9):
        assert D.extra({"orb": R}, f"claim{n}") is getattr(R, f"claim{n}")


# ───────────────────────────── (g) real data (to 2019-07-01 only) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cache = {}
    d2, d1 = tmp_path_factory.mktemp("closed_study2"), tmp_path_factory.mktemp("closed_study1")

    def get(symbol, end, keep=True):
        """The study's market of ``symbol`` to ``end`` (never past 2019-07-01 here) as a Context; one symbol held at a
        time; ``keep=False``: not cached (the cut markets of the causality test)."""
        key = (symbol, end)
        if key not in cache:
            if (2019, 1) not in store.available_months(symbol):
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            assert TM.s_of(end) <= TM.s_of("2019-07-01")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(M, "STUDY_DIR", d2)
                mp.setattr(TM, "STUDY_DIR", d1)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                ctx = M.Context(M.load(symbol, end=end))
            if not keep:
                return ctx
            for k in [k for k in cache if k[0] != symbol]:
                del cache[k]
            gc.collect()
            cache[key] = ctx
        return cache[key]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_g_real_bars_o1_f0_is_the_scripts_trade_logic_and_decisions_are_causal(symbol, real):
    full = real(symbol, "2019-07-01")
    for tf in ("M5", "M15"):
        T = R.o1_trades(full, tf, R.Row("O1", "F0"))
        d = R.orb_output(full, tf)["days"]
        S = R.sessions(full, tf)
        b = full.bars(tf)
        port = []
        for k in range(len(d)):
            for sd, eb, xb, why in (("trade_side", "entry_bar", "exit_bar", "exit_reason"),
                                    ("trade2_side", "entry2_bar", "exit2_bar", "exit2_reason")):
                e = int(d[eb].iat[k])
                if e < 0 or b.tc[e] > S["entry_end_s"][k] or not (S["flat_bar"][k] < 0 or e < S["flat_bar"][k]):
                    continue
                fl, x = int(S["flat_bar"][k]), int(d[xb].iat[k])
                port.append((e, int(d[sd].iat[k]), x if d[why].iat[k] == "trail" and (fl < 0 or x <= fl) else fl))
        assert list(zip(T["bar"].tolist(), T["side"].tolist(), T["exit_bar"].tolist())) == port and len(port) > 300
    part = real(symbol, "2019-04-01", keep=False)
    assert part.mk.end_s == TM.s_of("2019-04-01")
    assert same_decisions(full, part, symbol, TM.s_of("2019-04-01")) == (82 if symbol == "XAUUSDm" else 66)
    del part
    gc.collect()


SMOKE = ("{s}|M5|ORB|O1|F0", "{s}|M15|ORB|O2|HV", "{s}|M5|ORB|O3|F2-4H", "{s}|M15|ORB|O4|F2-1D",
         "{s}|M5|ORB|O5|HV+F2-4H", "{s}|M15|ORB|O5|F0", "{s}|M5|ORB|O1|F0|TIGHT", "{s}|M15|ORB|O5|F0|TIGHT",
         "{s}|M5|ORB|O2|LV", "{s}|M15|ORB|O1|F0|UTC-5")
SMOKE_GOLD = ("{s}|M5|ORB|O1|LO", "{s}|M5|ORB|O5|LO", "{s}|M15|ORB|O5|F2-4H|ORB-CX", "{s}|M5|ORB|O1|F0|ORB-CX")
SMOKE_BTC = ("{s}|M5|ORB|O1|F0|7D",)
REASONS = {"O1": {"signal", "end"}, "O5": {"signal", "stop", "gap stop", "end"},
           "O2": {"signal", "stop", "gap stop", "target", "gap target", "end"}}


@pytest.mark.parametrize("symbol", SYMS)
def test_g_smoke_one_row_of_each_rule_type_runs_on_development_data(symbol, real, monkeypatch):
    """2019-01-01 to 2019-06-30 through ``run_variant`` (the dev window shortened to the data held): it runs, and its
    trades are where the rule says (counts, times, levels). No profit or loss is looked at."""
    ctx = real(symbol, "2019-07-01")
    monkeypatch.setitem(M.WINDOWS, "dev", (None, "2019-07-01"))
    assert M.window_span("dev", symbol) == ("2019-01-01", "2019-07-01")
    R.warm(ctx, R.variants(symbol))
    a_s = TM.s_of("2019-01-01")
    pats = SMOKE + (SMOKE_GOLD if symbol == "XAUUSDm" else SMOKE_BTC)
    gaps = 0
    for pat in pats:
        v = V(pat.format(s=symbol))
        ex = R.build(v, ctx)
        res = M.run_variant(ctx, v, ex, windows=("dev",), trades_windows=("dev",))
        assert len(res.rows) == 1
        row = res.rows[0]
        assert (row["vid"], row["window"], row["start"], row["end"]) == (v.id, "dev", "2019-01-01", "2019-07-01")
        assert row["eligible"] == v.eligible and row["family"] == "ORB"
        n = int(row["trades"])
        assert n > 40 and int(row["n_taken"]) == n and int(row["n_taken_x15"]) == int(row["trades_x15"]), v.id
        assert int(row["n_busy"]) == 0 and int(row["n_dropped_stop"]) == 0
        b = ctx.bars(v.tf)
        tr = res.trades[res.trades.cost == 1.0]
        rule = v.params["rule"]
        bar = tr.bar.to_numpy()
        entry_s = np.asarray([int(x.timestamp()) for x in tr.entry_time], np.int64)
        exit_s = np.asarray([int(x.timestamp()) for x in tr.exit_time], np.int64)
        e_ny, x_ny = M.ny_local(entry_s), M.ny_local(exit_s)
        assert (b.tc[bar] > a_s).all() and (tr.groupby(["tag", "side"]).size() <= 1).all()
        S = R.sessions(ctx, v.tf, v.params["version"])
        pos = {int(d): i for i, d in enumerate(S["day"])}
        js = np.asarray([pos[int(x)] for x in tr.tag], np.int64)
        flat = S["flat_bar"][js]
        # flat by the flat bar's close: at the next M1 open where one opens at that close, else at the flat bar's last
        # M1 close (close_gap, reading 3), so an early close (e.g. 2019-05-27) is flat before the break too
        assert (flat >= 0).all() and (exit_s <= b.tc[flat]).all(), v.id
        early = b.tc[flat] < S["flat_cut_s"][js] - 900
        assert early.sum() <= 3, v.id
        assert ((x_ny % DAY) // 60 <= R.FLAT_AT).all() and (x_ny // DAY == e_ny // DAY).all(), v.id
        nt = len(ctx.mk.t)                                                  # no M1 bar opens at the flat bar's close:
        gap = (b.ex[flat] < nt) & (ctx.mk.t[np.minimum(b.ex[flat], nt - 1)] > b.tc[flat])
        booked = gap & (tr.reason.to_numpy() == "signal") & (exit_s == ctx.mk.t[b.i1[flat]] + 60)
        assert int(row["n_close_gap"]) == int(booked.sum()), v.id           # booked at its last M1 close
        gaps += int(row["n_close_gap"])
        if rule == "O5":
            assert (tr.groupby("tag").size() <= 1).all() and int(row["n_unfilled"]) >= 0
            start = 530 if v.params["version"] == "ORB-CX" else 600
            assert ((e_ny % DAY) // 60 >= start).all() and ((e_ny % DAY) // 60 < R.ENTRY_END).all(), v.id
            assert (b.i0[bar] <= ctx.mk.t.searchsorted(entry_s)).all()       # the fill lies in its bar
            assert np.isfinite(tr.r).all() and set(tr.reason) <= REASONS["O5"]
        else:
            assert np.array_equal(entry_s, ctx.mk.t[b.ex[bar]])            # filled at the next M1 open
            assert ((M.ny_local(b.tc[bar]) % DAY) // 60 <= R.ENTRY_END).all()
            E = ex.entries
            pos = {int(x): i for i, x in enumerate(E.bar)}
            ix = np.asarray([pos[int(x)] for x in bar], np.int64)
            assert np.array_equal(tr.side.to_numpy(), E.side[ix]) and np.array_equal(tr.tag.to_numpy(), E.tag[ix])
            if rule == "O1":
                assert np.isnan(tr.r).all() and set(tr.reason) <= REASONS["O1"]
            else:
                lvl = E.stop_level[ix]
                fill = tr.entry.to_numpy()
                assert np.allclose(tr.risk.to_numpy(), np.abs(fill - lvl), rtol=1e-9, atol=1e-9)
                assert set(tr.reason) <= REASONS["O2"]
        if v.params["filter"] == "LO":
            assert (tr.side == 1).all()
    # gold's early closes of 2019-H1 (US holidays) leave trades flat before the break; BTC has no such day there
    assert gaps > 0 if symbol == "XAUUSDm" else gaps == 0
    # the claims' geometry runs on the real bars (counts only)
    monkeypatch.setitem(M.WINDOWS, "dev", ("2019-01-01", "2019-04-01"))
    monkeypatch.setitem(M.WINDOWS, "val", ("2019-04-01", "2019-07-01"))
    ev = FakeEv({symbol: ctx})
    for got in (R.claim6(ev), R.claim8(ev)):
        assert got and all(isinstance(g["dev_ok"], bool) and isinstance(g["val_ok"], bool) for g in got)
    st = R.direction_stats(ctx, "M5", "2019-01-01", "2019-07-01")
    assert st["same"] + st["opposite"] + st["inside"] == st["breakouts"] > 80
    cs = R.clock_stats(ctx, "M15", "2019-01-01", "2019-07-01")
    assert cs["late"] == cs["dst"] > 60 and cs["late_not_dst"] == cs["dst_not_late"] == 0
