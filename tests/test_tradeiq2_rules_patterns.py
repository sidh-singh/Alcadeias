"""
Study 2's rule rows of "Harmonic & Chart Patterns [AI-AlgoCode]" (``backtesting/research/tradeiq2_rules_patterns.py``):
PREREG section 6.7 (HP-HF, HP-HC, HP-CF, HP-CS, HP-CC, HP-DRAWN) with sections 4 (execution, absolute levels), 5
(filters on event rules) and 7 (families, eligibility).

1. The grid: exactly PREREG 6.7's rows per symbol, the numbers written here from the plan's "Size" line; families,
   eligibility, ids and filter tokens; the driver's grid check accepts them.
2. Hand-made bars. Hourly bars whose depth-5 zigzag has exactly the swings designed (straight legs of 6 bars), 60 M1
   bars an hour, then a hand-made M1 continuation. Two designs: a Bull Bat (X 100, A 120, B 110, C 116, D falling
   through 110: its first forming bar is the leg's 4th bar, D = 108, AD = 12, SL 106.44, TP1 112.584, TP2 115.416) and a
   double bottom (120, 100, the neckline 108, 100.5: armed when the next high is added, forming at the first close
   above 108, h = 7.5, SL 104.25, TP1 115.5, TP2 120.135). For every rule: the decision bar, the side, the levels, the
   fill at the next M1 open, every exit (target, stop with one extra spread, a gap through the stop, the 30-bar time
   stop, TP2, the 50/50 legs); section 4's absolute-level rules; the skip rule; one entry per instance (D moving, an
   instance returning); HP-CS's order (a fill at p2, a gap fill, the cancel at the next swing); HP-DRAWN's look-ahead.
3. Filters: the gate at the decision close only (an entry removed, an open trade never closed), the order gate at the
   placement close, the filter of each slot and timeframe, FR's meaning (the ribbon of the higher timeframe).
4. An independent reading of the rows on random-walk bars: the candidates rebuilt with plain loops from the port's
   raw output and the PREREG's text.
5. Causality: every candidate, Exec row and trade decided up to a time T is unchanged when the data after T is
   removed; HP-DRAWN's look-ahead is exactly its confirmation delay.
6. Real bars (skipped without the tick store; bars to 2023-01-01 only, the hold-out is never loaded): the Development
   counts of the porting notes reproduced, and a smoke run of one row of each rule type through the harness on
   2019-01-01 to 2019-06-30. Counts and geometry only: the runs' profit or loss is never read, asserted or printed.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_patterns as HP
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_patterns as R
from backtesting.research import tradeiq_market as TM

T0 = TM.s_of("2019-03-04")          # a Monday, 00:00 UTC
SP = 0.02                           # the hand-made markets' spread
SYM = "BTCUSDm"                     # around the clock: no session gaps in the hand-made bars
EPS = 1e-9
# PREREG 6.7 "Size: 27 HF + 3 HC + 12 CF + 4 CS + 2 CC = 48 eligible rows per symbol"
PREREG_ROWS = {"HP-HF": 27, "HP-HC": 3, "HP-CF": 12, "HP-CS": 4, "HP-CC": 2}
PREREG_ELIGIBLE = 48
# PREREG 7: HP-HARMONIC = the harmonic rows, HP-CHART = the chart-pattern rows (27 + 3 and 12 + 4 + 2)
PREREG_FAMILIES = {"HP-HARMONIC": 30, "HP-CHART": 18}
# HP-DRAWN, information only (the plan gives no number): harmonic 1H, 4H, 1D and chart 1H, 4H x ALL, SHOWN (reading 8)
DRAWN_ROWS = {"HP-HARMONIC": 6, "HP-CHART": 4}

BAT = [95, 105, 96, 106, 97, 107, 100, 120, 110, 116, 104]        # L H L H L H, then X A B C and D's leg to 104
BAT_HF_BAR = 63                                                  # D's leg's 4th bar: low 108, close 108.05
DB = [105, 95, 104, 96, 103, 97, 120, 100, 108, 100.5, 113, 109]  # H L H L H L, 120 100 108 100.5, D 113, a low 109
DB_CS_BAR, DB_CF_BAR, DB_D_BAR, DB_CC_BAR = 61, 63, 65, 69


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' guards point at empty folders: the hold-outs are closed."""
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d2


# ───────────────────────────── hand-made bars ─────────────────────────────

def zz_hours(points, leg=6, w=0.1):
    """Hourly (h, l, c, up) whose depth-5 zigzag has exactly the swings ``points`` (alternating highs and lows),
    point k on bar leg*(k+1) - 1: a lead-in from the second point's level, then straight legs of ``leg`` bars; up-leg
    bars h = v, l = v - w, c = v - w/2, down-leg bars h = v + w, l = v, c = v + w/2 (v on the leg)."""
    pts = [float(p) for p in points]
    vals, ups, prev = [], [], pts[1]
    for p in pts:
        for j in range(1, leg + 1):
            vals.append(prev + (p - prev) * j / leg)
            ups.append(p > prev)
        prev = p
    v, up = np.array(vals), np.array(ups)
    return np.where(up, v, v + w), np.where(up, v - w, v), np.where(up, v - w / 2, v + w / 2), up


def hour_anchors(h, l, c, up):
    """The M1 polyline of the hours: low -> high -> close (up bars) or high -> low -> close (down bars), anchors at
    minutes 0, 30 and 60 of each hour, so each hour's high, low and close are exact."""
    out = []
    for k in range(len(h)):
        a, b = (l[k], h[k]) if up[k] else (h[k], l[k])
        out += [(60 * k, float(a)), (60 * k + 30, float(b)), (60 * k + 60, float(c[k]))]
    return out


def m1_bars(anchors):
    """(o, h, l, c) of M1 bars along a polyline of (minute, price) anchors (minutes non-decreasing from 0): bar m opens
    at the path's value at minute m and closes at its value at m + 1, no wicks; two anchors at one minute are a jump
    there (the bar ending at that minute closes at the first, the next one opens at the second)."""
    mins = np.array([a[0] for a in anchors], np.int64)
    vals = np.array([a[1] for a in anchors], np.float64)
    if mins[0] != 0 or np.any(np.diff(mins) < 0):
        raise ValueError("anchors must start at minute 0 and not go back")
    n = int(mins[-1])

    def at(m, close):
        i = np.flatnonzero(mins == m)
        if len(i):
            return vals[i[0]] if close else vals[i[-1]]
        k = int(np.searchsorted(mins, m))
        m0, v0, m1_, v1 = mins[k - 1], vals[k - 1], mins[k], vals[k]
        return v0 + (v1 - v0) * (m - m0) / (m1_ - m0)

    o = np.array([at(m, False) for m in range(n)])
    c = np.array([at(m + 1, True) for m in range(n)])
    return o, np.maximum(o, c), np.minimum(o, c), c


def hand_market(points, upto=None, cont=(), edit=None, sp=SP):
    """A BTCUSDm market from ``T0``: the hours of ``zz_hours(points)`` up to bar ``upto`` (all when None; ``edit(h, l,
    c)`` may change them first), then the M1 continuation ``cont`` ((minute from the end of those hours, price)
    anchors). Returns the market."""
    h, l, c, up = zz_hours(points)
    k = len(h) if upto is None else upto + 1
    h, l, c, up = h[:k].copy(), l[:k].copy(), c[:k].copy(), up[:k].copy()
    if edit is not None:
        edit(h, l, c)
    anchors = hour_anchors(h, l, c, up) + [(60 * k + m, float(p)) for m, p in cont]
    o, hh, ll, cc = m1_bars(anchors)
    n = len(o)
    m1 = {"t": T0 + 60 * np.arange(n, dtype=np.int64), "o": o, "h": hh, "l": ll, "c": cc,
          "spread_mean": np.full(n, float(sp)), "n": np.ones(n)}
    return M.TMarket2(SYM, m1)


def vspec(rule, tf="1H", target="TP1", slot="F0", drawn="", symbol=SYM):
    """A row's Spec (``drawn``: 'HALL', 'HSHOWN', 'CALL', 'CSHOWN' for HP-DRAWN's harmonic / chart sets)."""
    fam = "HP-HARMONIC" if rule in ("HP-HF", "HP-HC") else "HP-CHART"
    if rule == "HP-DRAWN":
        fam = "HP-HARMONIC" if drawn.startswith("H") else "HP-CHART"
        drawn = drawn[1:]
    return R.Spec(symbol, tf, fam, rule, target, slot, drawn)


def variant(rule, tf="1H", target="TP1", slot="F0", drawn="", symbol=SYM):
    """A registered row (``vspec``'s arguments)."""
    v = vspec(rule, tf, target, slot, drawn, symbol).variant()
    assert R.spec_of(v).id == v.id
    return v


def run(mk, v, cost=1.0, ctx=None):
    ctx = ctx or M.Context(mk)
    return M.run_exec(mk, R.build(v, ctx), T0, mk.end_s, cost)


def hour_ix(k, minute=0):
    """The M1 index of minute ``minute`` of hour ``k`` (the hand-made markets have every minute)."""
    return 60 * k + minute


def first_m1(mk, start, cond):
    j = np.flatnonzero(cond(mk))
    j = j[j >= start]
    return int(j[0])


# ───────────────────────────── 1. the grid ─────────────────────────────

@pytest.mark.parametrize("symbol", M.SYMBOLS)
def test_the_grid_is_exactly_prereg_67(symbol):
    vs = R.variants(symbol)
    ids = [v.id for v in vs]
    assert len(ids) == len(set(ids))
    rule = lambda v: v.id.split("|")[3]
    elig = [v for v in vs if v.eligible]
    assert len(elig) == PREREG_ELIGIBLE == sum(PREREG_ROWS.values())
    for r, n in PREREG_ROWS.items():
        assert sum(1 for v in elig if rule(v) == r) == n, r
    for fam, n in PREREG_FAMILIES.items():
        assert sum(1 for v in elig if v.family == fam) == n, fam
        assert sum(1 for v in vs if v.family == fam and not v.eligible) == DRAWN_ROWS[fam], fam
    assert all(not v.eligible for v in vs if rule(v) == "HP-DRAWN")
    assert all(v.eligible for v in vs if rule(v) != "HP-DRAWN")
    for v in vs:
        assert v.symbol == symbol and v.script == "HP" and v.family in ("HP-HARMONIC", "HP-CHART")
        assert v.id.startswith(f"{symbol}|{v.tf}|{v.family}|") and not any(ch.isspace() for ch in v.id)
        assert R.spec_of(v).variant() == v
    # timeframes, targets and filters per rule (PREREG 6.7), the filter token = tradeiq2_filters' name
    want_f = {"1H": {"F0", "F2-4H", "FR"}, "4H": {"F0", "F2-1D", "FR"}, "1D": {"F0", "F1", "FR"}}
    grid = {}
    for v in vs:
        t = v.id.split("|")
        grid.setdefault(rule(v), set()).add((v.tf, t[-2], t[-1]) if rule(v) != "HP-DRAWN" else (v.tf, t[4], v.family))
    assert grid["HP-HF"] == {(tf, tg, f) for tf in ("1H", "4H", "1D") for tg in ("TP1", "TP2", "50/50")
                             for f in want_f[tf]}
    assert grid["HP-HC"] == {(tf, "TP1", "F0") for tf in ("1H", "4H", "1D")}
    assert grid["HP-CF"] == {(tf, tg, f) for tf in ("1H", "4H") for tg in ("TP1", "TP2") for f in want_f[tf]}
    assert grid["HP-CS"] == {(tf, "TP1", f) for tf in ("1H", "4H") for f in want_f[tf] - {"FR"}}
    assert grid["HP-CC"] == {(tf, "TP1", "F0") for tf in ("1H", "4H")}
    assert grid["HP-DRAWN"] == ({(tf, st, "HP-HARMONIC") for tf in ("1H", "4H", "1D") for st in ("ALL", "SHOWN")}
                                | {(tf, st, "HP-CHART") for tf in ("1H", "4H") for st in ("ALL", "SHOWN")})
    # families: harmonic rules HP-HARMONIC, chart rules HP-CHART (PREREG 7)
    for v in vs:
        if rule(v) in ("HP-HF", "HP-HC"):
            assert v.family == "HP-HARMONIC"
        elif rule(v) in ("HP-CF", "HP-CS", "HP-CC"):
            assert v.family == "HP-CHART"
    # info: controls, the 50/50 note (PREREG 4), information only
    for v in vs:
        if rule(v) == "HP-DRAWN":
            assert v.info.startswith("information only")
        elif rule(v) in ("HP-HC", "HP-CC"):
            assert v.info == "control"
        elif "|50/50|" in v.id:
            assert "0.02 lot" in v.info
        else:
            assert v.info == ""
    # every filtered eligible row has its F0 twin (the driver pairs rows by swapping the filter token)
    for v in elig:
        t = v.id.split("|")
        if t[-1] != "F0":
            assert "|".join(t[:-1] + ["F0"]) in ids
        assert v.params["filter"] == t[-1]
    with pytest.raises(ValueError):
        R.variants("USTECm")


def test_spec_of_refuses_rows_that_are_not_registered():
    v = variant("HP-HF")
    with pytest.raises(ValueError):
        R.spec_of(M.Variant(v.id.replace("TP1", "TP3"), v.symbol, v.tf, v.script, v.family))
    with pytest.raises(ValueError):
        R.spec_of(M.Variant(v.id, v.symbol, "4H", v.script, v.family))
    with pytest.raises(ValueError):
        R.spec_of(M.Variant(v.id, v.symbol, v.tf, "RIB", v.family))
    rebuilt = M.Variant(v.id, v.symbol, v.tf, v.script, v.family, v.eligible, v.info, {})   # as from grid.csv
    assert R.spec_of(rebuilt) == R.spec_of(v)


def test_the_drivers_grid_check_accepts_the_module():
    D = pytest.importorskip("backtesting.research.tradeiq2")
    if not hasattr(D, "checked_grid"):
        pytest.skip("the driver has no checked_grid")
    grid, pairs = D.checked_grid({"patterns": R})
    assert len(pairs) == 2 * len(R.variants("XAUUSDm"))
    assert set(grid.group) == {"HP"}


def test_describe_names_the_rule():
    for v in R.variants("XAUUSDm"):
        text = R.describe(v)
        s = R.spec_of(v)
        assert s.rule in text and "30th bar after D" in text and "stop " in text
        assert ("placement close" in text) == (s.rule == "HP-CS")


def test_table_lists_the_candidates_in_times_and_levels():
    utc = lambda s: pd.Timestamp(int(s), unit="s", tz="UTC")
    mk = hand_market(BAT, BAT_HF_BAR, HC_CONT)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    t = R.table(variant("HP-HF"), ctx)
    assert list(t.decision_bar) == [BAT_HF_BAR] and list(t.pattern) == ["Bull Bat"] and t.allowed.all()
    assert t.decision_close.iloc[0] == utc(T0 + 3600 * (BAT_HF_BAR + 1)) == t.fill_open.iloc[0]
    assert t.d_close.iloc[0] == utc(b.tc[BAT_HF_BAR]) and t.time_stop_close.isna().all()    # bar 93 is past the data
    assert abs(t.sl.iloc[0] - 106.44) < EPS and t.side.iloc[0] == 1
    t = R.table(variant("HP-HC"), ctx)
    assert list(t.decision_bar) == [66] and t.detected_close.iloc[0] == utc(b.tc[66])
    assert t.d_close.iloc[0] == utc(b.tc[BAT_HF_BAR])
    mk = hand_market(DB)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    t = R.table(variant("HP-CS"), ctx)
    assert list(t.decision_bar) == [DB_CS_BAR] and t.buy.iloc[0] == 108.0 and np.isnan(t.sell.iloc[0])
    assert t.cancel.iloc[0] == utc(b.tc[DB_CC_BAR]) and t.allowed_buy.all() and not t.allowed_sell.any()
    t = R.table(variant("HP-DRAWN", drawn="CSHOWN"), ctx)
    assert list(t.decision_bar) == [DB_D_BAR] and t.detected_close.iloc[0] == utc(b.tc[DB_CC_BAR])
    assert t.fill_open.iloc[0] == utc(T0 + 3600 * (DB_D_BAR + 1)) and t.drawn.all()


# ───────────────────────────── 2. hand-made bars: the designs ─────────────────────────────

def test_the_hand_made_designs_give_the_planned_events():
    """The swings are the designed points; the Bull Bat's first forming bar and levels, the double bottom's armed,
    forming and confirmed bars and levels, computed by hand in the module docstring of this file."""
    mk = hand_market(BAT)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    out = HP.patterns(b.h, b.l, b.c)
    assert list(out["swings"]["price"]) == [float(p) for p in BAT]
    ev = R.events(ctx, "1H")
    hf = ev["hf"]
    assert list(hf["bar"]) == [BAT_HF_BAR] and list(hf["pid"]) == [11] and list(hf["side"]) == [1]
    # AD = 120 - 108 = 12: SL = 108 - 0.13 x 12, TP1 = 108 + 0.382 x 12, TP2 = 108 + 0.618 x 12
    assert abs(hf["sl"][0] - 106.44) < EPS and abs(hf["tp1"][0] - 112.584) < EPS and abs(hf["tp2"][0] - 115.416) < EPS
    assert abs(hf["close"][0] - 108.05) < EPS and hf["d_bar"][0] == BAT_HF_BAR
    fm = out["forming"]
    key = fm.loc[fm.first_hit & (fm.t_bar == BAT_HF_BAR), "instance_key"].iloc[0]
    # the instance is the first hit on D's leg's 4th, 5th and 6th bars while D moves (108, 106, 104): one entry
    same = fm[fm.first_hit.to_numpy() & np.array([k == key for k in fm.instance_key], bool)]
    assert list(same.t_bar) == [63, 64, 65] and list(same.b0) == [63, 64, 65]
    assert len(ev["hc"]["bar"]) == 0                                           # no swing after D yet

    mk = hand_market(DB)
    ctx = M.Context(mk)
    ev = R.events(ctx, "1H")
    cs, cf, cc = ev["cs"], ev["cf"], ev["cc"]
    assert list(cs["bar"]) == [DB_CS_BAR] and list(cs["pid"]) == [23] and list(cs["sides"]) == [1]
    assert cs["buy"][0] == 108.0 and np.isnan(cs["sell"][0])
    assert abs(cs["buy_stop"][0] - 104.25) < EPS and abs(cs["buy_target"][0] - 115.5) < EPS
    assert cs["next_add"][0] == DB_CC_BAR and cs["until"][0] == int(ctx.bars("1H").tc[DB_CC_BAR])
    assert cs["close"][0] < 108.0                                              # armed, not yet broken out
    assert list(cf["bar"]) == [DB_CF_BAR] and list(cf["pid"]) == [23] and list(cf["n_ids"]) == [1]
    assert abs(cf["sl"][0] - 104.25) < EPS and abs(cf["tp1"][0] - 115.5) < EPS and abs(cf["tp2"][0] - 120.135) < EPS
    assert cf["close"][0] > 108.0 and cf["d_bar"][0] == DB_CF_BAR
    assert list(cc["bar"]) == [DB_CC_BAR] and list(cc["d_bar"]) == [DB_D_BAR] and list(cc["pid"]) == [23]
    assert abs(cc["close"][0] - ctx.bars("1H").c[DB_CC_BAR]) < EPS
    dc = ev["drawn_chart"]
    assert list(dc["bar"]) == [DB_D_BAR] and list(dc["t_conf"]) == [DB_CC_BAR] and bool(dc["drawn"][0])


# ───────────────────────────── 2a. HP-HF: entry and exits ─────────────────────────────

def test_hf_market_entry_at_the_next_m1_open_and_the_target_at_tp1():
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (120, 113.0)])
    r = run(mk, variant("HP-HF"))
    assert r.counts["candidates"] >= 1 and r.counts["dropped_stop"] == 0 and r.counts["dropped_target"] == 0
    tr = r.trades.iloc[0]
    j = hour_ix(BAT_HF_BAR + 1)                                    # decided at bar 63's close, filled at 64:00
    assert tr.entry_ix == j and tr.side == 1 and tr.bar == BAT_HF_BAR and tr.tag == 11
    assert abs(tr.entry - (108.05 + SP)) < EPS                     # a buy at the ask
    assert abs(tr.risk - (108.05 + SP - 106.44)) < 1e-9            # the stop level as a distance from the fill
    want = first_m1(mk, j, lambda m: m.h >= 112.584 - 1e-12)
    assert tr.reason == "target" and tr.exit_ix == want and abs(tr.exit - 112.584) < 1e-9
    assert abs(tr.pnl - mk.k * (112.584 - tr.entry)) < 1e-9
    assert abs(tr.r - (112.584 - tr.entry) / (108.05 + SP - 106.44)) < 1e-6


def test_hf_stop_at_its_level_with_one_extra_spread():
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (60, 106.0)])
    tr = run(mk, variant("HP-HF")).trades.iloc[0]
    want = first_m1(mk, hour_ix(64), lambda m: m.l <= 106.44 + 1e-12)
    assert tr.reason == "stop" and tr.exit_ix == want
    assert abs(tr.exit - (106.44 - SP)) < 1e-9 and abs(tr.slippage - mk.k * SP) < 1e-12
    assert abs(tr.r - (106.44 - SP - tr.entry) / (tr.entry - 106.44)) < 1e-6


def test_hf_a_gap_through_the_stop_fills_at_the_open():
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (10, 108.0), (10, 106.0), (30, 106.0)])
    tr = run(mk, variant("HP-HF")).trades.iloc[0]
    assert tr.reason == "gap stop" and tr.exit_ix == hour_ix(64, 10) and abs(tr.exit - (106.0 - SP)) < 1e-9


def test_hf_time_stop_at_the_close_of_the_30th_bar_after_d():
    path = [(0, 108.05)] + [(180 * i, 110.0 if i % 2 else 107.0) for i in range(1, 16)]
    mk = hand_market(BAT, BAT_HF_BAR, path)
    ctx = M.Context(mk)
    r = run(mk, variant("HP-HF"), ctx=ctx)
    tr = r.trades.iloc[0]
    b = ctx.bars("1H")
    xb = BAT_HF_BAR + 30                                            # D's bar + 30
    assert R.rows_of(vspec("HP-HF"), ctx)["exit_bar"][0] == xb
    assert tr.reason == "signal" and tr.exit_ix == b.ex[xb] == hour_ix(xb + 1)
    assert abs(tr.exit - mk.o[b.ex[xb]]) < EPS                       # a long leaves at the bid of that open


def test_hf_entries_filled_at_or_beyond_the_stop_or_the_target_are_dropped():
    # the close of bar 63 is 108.05 (not past TP1), then the next hour opens below the stop / above TP1
    r = run(hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (0, 106.2), (60, 106.2)]), variant("HP-HF"))
    assert r.counts["candidates"] == 1 and r.counts["dropped_stop"] == 1 and len(r.trades) == 0
    r = run(hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (0, 113.0), (60, 113.0)]), variant("HP-HF"))
    assert r.counts["candidates"] == 1 and r.counts["dropped_target"] == 1 and len(r.trades) == 0
    # a fill exactly on the stop or on the target is dropped too (spread 0: the fill is the open itself)
    ev = R.events(M.Context(hand_market(BAT, sp=0.0)), "1H")["hf"]
    for level, kind in ((float(ev["sl"][0]), "dropped_stop"), (float(ev["tp1"][0]), "dropped_target")):
        mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (0, level), (60, level)], sp=0.0)
        r = run(mk, variant("HP-HF"))
        assert mk.o[hour_ix(BAT_HF_BAR + 1)] == level
        assert r.counts[kind] == 1 and len(r.trades) == 0


def test_hf_x15_recomputes_the_fill_and_the_distances():
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (120, 113.0)])
    a = run(mk, variant("HP-HF"), 1.0).trades.iloc[0]
    b = run(mk, variant("HP-HF"), 1.5).trades.iloc[0]
    assert abs(a.entry - (108.05 + SP)) < EPS and abs(b.entry - (108.05 + 1.5 * SP)) < EPS
    assert abs(b.risk - (108.05 + 1.5 * SP - 106.44)) < 1e-9
    assert b.reason == "target" and abs(b.exit - 112.584) < 1e-9        # the level, not the x1.0 distance


def test_hf_skip_rule_close_at_or_beyond_tp1():
    tp1 = R.events(M.Context(hand_market(BAT)), "1H")["hf"]["tp1"][0]

    def at(close):
        def edit(h, l, c):
            c[BAT_HF_BAR] = close
            h[BAT_HF_BAR] = max(h[BAT_HF_BAR], close)
        mk = hand_market(BAT, BAT_HF_BAR, [(0, close), (60, close)], edit=edit)
        ctx = M.Context(mk)
        ev = R.events(ctx, "1H")["hf"]
        assert list(ev["bar"]) == [BAT_HF_BAR] and ev["tp1"][0] == tp1          # the same instance and plan
        return ctx
    for close, kept in ((tp1, False), (tp1 + 0.001, False), (tp1 - 0.001, True)):
        ctx = at(close)
        assert (len(R.rows_of(vspec("HP-HF"), ctx)["bar"]) == 1) == kept
        assert (len(R.rows_of(vspec("HP-HC"), ctx)["bar"]) == 0)                # no confirmation in these bars
    # the chart rows have no skip rule: only the fill-based drop (reading 4)
    assert not R.Spec(SYM, "1H", "HP-CHART", "HP-CF").skips_past_tp1
    assert not R.Spec(SYM, "1H", "HP-CHART", "HP-CC").skips_past_tp1
    assert R.Spec(SYM, "1H", "HP-HARMONIC", "HP-DRAWN", drawn="ALL").skips_past_tp1


def test_hf_tp2_and_the_5050_legs():
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (240, 117.0)])
    fill = 108.05 + SP
    t1 = run(mk, variant("HP-HF", target="TP1")).trades.iloc[0]
    t2 = run(mk, variant("HP-HF", target="TP2")).trades.iloc[0]
    r = run(mk, variant("HP-HF", target="50/50"))
    assert t1.reason == "target" and abs(t1.exit - 112.584) < 1e-9
    assert t2.reason == "target" and abs(t2.exit - 115.416) < 1e-9 and t2.exit_ix > t1.exit_ix
    assert len(r.legs) == 2 and [w for w, _ in r.legs] == [0.5, 0.5] and not r.single
    h = r.trades.iloc[0]
    assert h.entry_ix == t1.entry_ix and abs(h.entry - fill) < EPS and h.reasons == "target|target"
    assert h.exit_ix == t2.exit_ix                                        # the last leg out
    assert abs(h.pnl - mk.k * (0.5 * (112.584 - fill) + 0.5 * (115.416 - fill))) < 1e-9
    assert abs(h.risk - (fill - 106.44)) < 1e-9
    # 50/50: an entry is dropped when its fill is at or beyond either target (DEVIATIONS 6)
    r = run(hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (0, 113.0), (60, 113.0)]), variant("HP-HF", target="50/50"))
    assert r.counts["dropped_target"] == 1 and len(r.trades) == 0


def test_hf_one_entry_per_instance_while_d_moves():
    """The Bull Bat stays the first hit while the live D falls from 108 to 104 (bars 63-65) and then on to 103 for 40
    hours (every bar a new low, no new swing): one candidate, at its first bar, and its time stop keeps the D of the
    decision (bar 63), not the D that moved."""
    mk = hand_market(BAT, None, [(0, 104.05), (2400, 103.0)])
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    out = HP.patterns(b.h, b.l, b.c)
    assert out["live_bar"][-1] == len(b) - 1 and out["n_swings"][-1] == len(BAT)       # D moved, no swing added
    rows = R.rows_of(vspec("HP-HF"), ctx)
    assert list(rows["bar"]) == [BAT_HF_BAR] and list(rows["exit_bar"]) == [BAT_HF_BAR + 30]
    r = run(mk, variant("HP-HF"), ctx=ctx)
    # (the designed leg's next bar opens at 106.1, below the stop 106.44: the one candidate is dropped, section 4)
    assert mk.o[hour_ix(BAT_HF_BAR + 1)] < rows["sl"][0]
    assert r.counts["candidates"] == 1 and r.counts["dropped_stop"] == 1 and len(r.trades) == 0


# ───────────────────────────── 2b. HP-HC and HP-DRAWN (harmonic) ─────────────────────────────

HC_CONT = [(0, 108.05), (60, 109.0), (120, 110.0), (180, 111.0), (300, 113.0)]    # a new high on bar 66, close 111


def test_hc_enters_at_the_confirmation_close_not_at_d():
    mk = hand_market(BAT, BAT_HF_BAR, HC_CONT)
    ctx = M.Context(mk)
    rows = R.rows_of(vspec("HP-HC"), ctx)
    assert list(rows["bar"]) == [66] and list(rows["d_bar"]) == [BAT_HF_BAR] and list(rows["t_conf"]) == [66]
    assert abs(rows["close"][0] - 111.0) < EPS and abs(rows["tp1"][0] - 112.584) < EPS     # 111 < TP1: kept
    xb = BAT_HF_BAR + 30                                                                  # the fixed D + 30
    assert list(rows["exit_bar"]) == [xb if xb < len(ctx.bars("1H")) else -1]
    tr = run(mk, variant("HP-HC"), ctx=ctx).trades.iloc[0]
    assert tr.entry_ix == hour_ix(67) and tr.bar == 66 and tr.side == 1 and abs(tr.entry - (111.0 + SP)) < EPS
    assert abs(tr.risk - (111.0 + SP - 106.44)) < 1e-9
    assert tr.reason == "target" and abs(tr.exit - 112.584) < 1e-9


def test_hc_is_skipped_when_the_confirmation_close_is_past_tp1():
    # a straight rise: the new high comes on bar 65 at 113, past TP1 = 112.584, so HP-HC skips it
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (120, 113.0)])
    ctx = M.Context(mk)
    hc = R.events(ctx, "1H")["hc"]
    assert list(hc["bar"]) == [65] and hc["close"][0] >= hc["tp1"][0]
    assert len(R.rows_of(vspec("HP-HC"), ctx)["bar"]) == 0


def test_drawn_enters_at_ds_bar_with_look_ahead():
    """The full Bull Bat (D falls to 104 on bar 65), then a rise that adds the next high on bar 67 (close 109 < TP1):
    HP-DRAWN enters at the close of D's bar (65) with D = 104's plan, although the pattern is known only on bar 67;
    HP-HF entered at bar 63 with the live D = 108; HP-HC enters at bar 67."""
    cont = [(0, 104.05), (60, 106.0), (120, 109.0), (240, 111.0)]
    mk = hand_market(BAT, None, cont)
    ctx = M.Context(mk)
    for st in ("HALL", "HSHOWN"):
        rows = R.rows_of(vspec("HP-DRAWN", drawn=st), ctx)
        assert list(rows["bar"]) == [65] and list(rows["t_conf"]) == [67] and list(rows["d_bar"]) == [65]
        # AD = 120 - 104 = 16: SL = 104 - 2.08, TP1 = 104 + 6.112
        assert abs(rows["sl"][0] - 101.92) < EPS and abs(rows["tp1"][0] - 110.112) < EPS
        tr = run(mk, variant("HP-DRAWN", drawn=st), ctx=ctx).trades.iloc[0]
        assert tr.entry_ix == hour_ix(66) and tr.bar == 65 and abs(tr.entry - (104.05 + SP)) < EPS
    hf = R.rows_of(vspec("HP-HF"), ctx)
    assert list(hf["bar"]) == [63] and abs(hf["sl"][0] - 106.44) < EPS
    assert list(R.rows_of(vspec("HP-HC"), ctx)["bar"]) == [67]
    # the look-ahead: cut before the confirmation, the drawn row does not exist, though its decision bar does
    early = M.Context(hand_market(BAT, None, cont[:2]))
    assert len(early.bars("1H")) == 67 and len(R.rows_of(vspec("HP-DRAWN", drawn="HALL"), early)["bar"]) == 0


# ───────────────────────────── 2c. HP-CF, HP-CC, HP-DRAWN (chart) ─────────────────────────────

def test_cf_market_entry_at_the_first_forming_close_with_the_chart_plan():
    c63 = float(hand_market(DB, DB_CF_BAR).tbars("1H").c[DB_CF_BAR])
    mk = hand_market(DB, DB_CF_BAR, [(0, c63), (360, 121.0)])
    ctx = M.Context(mk)
    close = ctx.bars("1H").c[DB_CF_BAR]
    for target, level in (("TP1", 115.5), ("TP2", 120.135)):
        tr = run(mk, variant("HP-CF", target=target), ctx=ctx).trades.iloc[0]
        assert tr.bar == DB_CF_BAR and tr.entry_ix == hour_ix(DB_CF_BAR + 1) and tr.side == 1 and tr.tag == 23
        assert abs(tr.entry - (mk.o[hour_ix(DB_CF_BAR + 1)] + SP)) < EPS
        assert abs(tr.risk - (tr.entry - 104.25)) < 1e-9                       # SL = p2 - 0.5 h = 108 - 3.75
        assert tr.reason == "target" and abs(tr.exit - level) < 1e-9
    assert close > 108.0


def test_cf_an_instance_that_returns_is_not_entered_again():
    """Bar 63 closes above the neckline (the first bar), bar 64 back below it, bar 65 above again with a higher live
    high (D moves, the key stays): one candidate only."""
    c63 = hand_market(DB, DB_CF_BAR).tbars("1H").c[DB_CF_BAR]
    cont = [(0, float(c63)), (30, 107.4), (60, 107.5), (120, 109.5), (180, 110.0)]
    mk = hand_market(DB, DB_CF_BAR, cont)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    out = HP.patterns(b.h, b.l, b.c)
    fm = out["forming"]
    db = fm[fm.id == 23]
    assert list(db.t_bar) == [63, 65, 66] and list(db.first_bar_of_instance) == [True, False, False]
    assert b.c[64] < 108.0 < b.c[65] and out["live_bar"][65] == 65                # back below, then D moved
    rows = R.rows_of(vspec("HP-CF"), ctx)
    assert list(rows["bar"]) == [DB_CF_BAR] and list(rows["d_bar"]) == [DB_CF_BAR]


def test_cc_enters_at_the_confirmation_close():
    mk = hand_market(DB, DB_CC_BAR, [(0, 110.0), (240, 116.0)])
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    rows = R.rows_of(vspec("HP-CC"), ctx)
    assert list(rows["bar"]) == [DB_CC_BAR] and list(rows["d_bar"]) == [DB_D_BAR]
    xb = DB_D_BAR + 30
    assert list(rows["exit_bar"]) == [xb if xb < len(b) else -1] and rows["close"][0] == b.c[DB_CC_BAR]
    tr = run(mk, variant("HP-CC"), ctx=ctx).trades.iloc[0]
    assert tr.bar == DB_CC_BAR and tr.entry_ix == hour_ix(DB_CC_BAR + 1) and abs(tr.entry - (110.0 + SP)) < EPS
    assert abs(tr.risk - (110.0 + SP - 104.25)) < 1e-9 and tr.reason == "target" and abs(tr.exit - 115.5) < 1e-9
    # HP-DRAWN (chart) enters at the close of D's bar (65) instead
    for st in ("CALL", "CSHOWN"):
        tr = run(mk, variant("HP-DRAWN", drawn=st), ctx=ctx).trades.iloc[0]
        assert tr.bar == DB_D_BAR and tr.entry_ix == hour_ix(DB_D_BAR + 1)
        assert abs(tr.entry - (mk.o[hour_ix(DB_D_BAR + 1)] + SP)) < EPS


def test_cc_time_stop_counts_from_d_not_from_the_entry():
    """HP-CC decides on bar 69 but its D is bar 65: the time stop is the close of bar 95 (65 + 30), 26 bars after the
    entry. The price then swings between 106 and 112 (inside SL 104.25 and TP1 115.5) for 40 hours."""
    path = [(0, 110.0)] + [(180 * i, 112.0 if i % 2 else 106.0) for i in range(1, 15)]
    mk = hand_market(DB, DB_CC_BAR, path)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    rows = R.rows_of(vspec("HP-CC"), ctx)
    assert list(rows["bar"]) == [DB_CC_BAR] and list(rows["exit_bar"]) == [DB_D_BAR + 30]
    tr = run(mk, variant("HP-CC"), ctx=ctx).trades.iloc[0]
    assert tr.entry_ix == hour_ix(DB_CC_BAR + 1) and tr.reason == "signal"
    assert tr.exit_ix == b.ex[DB_D_BAR + 30] == hour_ix(DB_D_BAR + 31) and abs(tr.exit - mk.o[tr.exit_ix]) < EPS


# ───────────────────────────── 2d. HP-CS: the stop order ─────────────────────────────

def test_cs_stop_order_fills_at_the_neckline_then_tp1():
    c61 = float(hand_market(DB, DB_CS_BAR).tbars("1H").c[DB_CS_BAR])
    mk = hand_market(DB, DB_CS_BAR, [(0, c61), (360, 116.0)])
    ctx = M.Context(mk)
    r = run(mk, variant("HP-CS"), ctx=ctx)
    assert r.counts["candidates"] >= 1 and r.counts["dropped_stop"] == 0
    tr = r.trades.iloc[0]
    jf = first_m1(mk, hour_ix(DB_CS_BAR + 1), lambda m: m.h + SP >= 108.0)       # the ask reaches p2
    assert tr.entry_ix == jf and tr.entry == 108.0 and tr.side == 1 and tr.tag == 23
    assert tr.bar == int(np.searchsorted(ctx.bars("1H").i0, jf, side="right") - 1)   # the bar holding the fill
    assert abs(tr.risk - 3.75) < 1e-9                                            # 108 - (108 - 0.5 x 7.5)
    assert tr.reason == "target" and abs(tr.exit - 115.5) < 1e-9


def test_cs_stop_after_the_fill_with_one_extra_spread():
    c61 = float(hand_market(DB, DB_CS_BAR).tbars("1H").c[DB_CS_BAR])
    mk = hand_market(DB, DB_CS_BAR, [(0, c61), (120, 109.0), (240, 103.0)])
    tr = run(mk, variant("HP-CS")).trades.iloc[0]
    assert tr.entry == 108.0 and tr.reason == "stop" and abs(tr.exit - (104.25 - SP)) < 1e-9
    assert tr.exit_ix == first_m1(mk, tr.entry_ix, lambda m: m.l <= 104.25 + 1e-12)


def test_cs_a_gap_over_the_neckline_fills_at_the_open():
    c61 = float(hand_market(DB, DB_CS_BAR).tbars("1H").c[DB_CS_BAR])
    mk = hand_market(DB, DB_CS_BAR, [(0, c61), (0, 109.0), (300, 116.0)])
    tr = run(mk, variant("HP-CS")).trades.iloc[0]
    assert tr.entry_ix == hour_ix(DB_CS_BAR + 1) and abs(tr.entry - (109.0 + SP)) < EPS    # max(p2, ask at open)
    assert abs(tr.risk - (109.0 + SP - 104.25)) < 1e-9                                     # from the actual fill
    assert tr.reason == "target" and abs(tr.exit - 115.5) < 1e-9
    # a gap beyond TP1: the fill is at or beyond the target, so the entry is dropped
    r = run(hand_market(DB, DB_CS_BAR, [(0, c61), (0, 116.0), (60, 116.0)]), variant("HP-CS"))
    assert r.counts["dropped_target"] == 1 and len(r.trades) == 0


def test_cs_order_is_cancelled_when_the_next_swing_is_added():
    """After the placement (bar 61) the price falls to a new 5-bar low on bar 64 (a swing is added: the key is no
    longer armed), then rises through 108: the bar-61 order has expired at bar 64's close and does not fill."""
    c61 = float(hand_market(DB, DB_CS_BAR).tbars("1H").c[DB_CS_BAR])
    cont = [(0, c61), (60, 103.5), (120, 102.8), (180, 102.0), (420, 110.0)]
    mk = hand_market(DB, DB_CS_BAR, cont)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    out = HP.patterns(b.h, b.l, b.c)
    assert out["added"][64] and not out["added"][62:64].any()
    rows = R.rows_of(vspec("HP-CS"), ctx)
    i = int(np.flatnonzero(rows["bar"] == DB_CS_BAR)[0])
    assert rows["next_add"][i] == 64 and rows["until"][i] == int(b.tc[64])
    xb = DB_CS_BAR + 30
    assert rows["exit_bar"][i] == (xb if xb < len(b) else -1)
    ex = R.build(variant("HP-CS"), ctx)
    one = M.event_exec("1H", orders=ex.orders.take(ex.orders.bar == DB_CS_BAR))
    r = M.run_exec(mk, one, T0, mk.end_s)
    assert r.counts["candidates"] == 1 and r.counts["unfilled"] == 1 and len(r.trades) == 0
    # without the cancel the same order would have filled at 108 on the way up
    late = M.orders(one.orders.bar, R.NEVER, buy=one.orders.buy, buy_stop=one.orders.buy_stop,
                    buy_target=one.orders.buy_target, tag=one.orders.tag)
    r = M.run_exec(mk, M.event_exec("1H", orders=late), T0, mk.end_s)
    assert len(r.trades) == 1 and r.trades.entry.iloc[0] == 108.0


def test_cs_order_placed_after_the_breakout_fills_at_the_next_open():
    """Reading 6: bar 61 adds the high and already closes above the neckline (108.5 > 108). The order is still placed
    at p2 and fills at the next M1 open, max(p2, ask) = the ask; HP-CF enters there too (its first bar is bar 61)."""
    def edit(h, l, c):
        c[DB_CS_BAR] = 108.5
        h[DB_CS_BAR] = 108.5
    mk = hand_market(DB, DB_CS_BAR, [(0, 108.5), (300, 116.0)], edit=edit)
    ctx = M.Context(mk)
    cs = R.rows_of(vspec("HP-CS"), ctx)
    assert list(cs["bar"]) == [DB_CS_BAR] and cs["close"][0] > cs["buy"][0] == 108.0
    tr = run(mk, variant("HP-CS"), ctx=ctx).trades.iloc[0]
    assert tr.entry_ix == hour_ix(DB_CS_BAR + 1) and abs(tr.entry - (108.5 + SP)) < EPS
    assert abs(tr.risk - (108.5 + SP - 104.25)) < 1e-9 and tr.reason == "target" and abs(tr.exit - 115.5) < 1e-9
    cf = run(mk, variant("HP-CF"), ctx=ctx).trades.iloc[0]
    assert (cf.entry_ix, cf.entry, cf.bar) == (tr.entry_ix, tr.entry, DB_CS_BAR)


def test_cs_both_directions_armed_on_one_bar_make_one_oco_order(monkeypatch):
    """Never seen on real or random bars (and not in 12 million random swing sets): if a bullish and a bearish chart
    key are first armed on one bar, the bar's order carries both sides at p2, each with its own plan (the guard of
    reading 6). ``armed`` is stubbed to arm Double Top (22) and Double Bottom (23) on bar 10 only."""
    n = 40
    q = np.tile(np.array([0.0, 100.0, 108.0, 100.0, 120.0, 97, 103, 96, 104, 95, 105]), (n, 1))
    q[:, 0] = np.arange(n)                                    # Q0 marks the bar for the stub
    qb = np.tile(np.arange(10, -1, -1) * 6, (n, 1))
    qb[:, 0] = np.arange(n)
    added = np.zeros(n, bool)
    added[[10, 20]] = True
    out = {"forming_q": q, "forming_qbar": qb, "added": added, "n_piv": np.full(n, 11)}
    monkeypatch.setattr(HP, "armed", lambda pid, P: (P[..., 0] == 10) & (pid in (22, 23)))
    tc = T0 + 3600 * (np.arange(n, dtype=np.int64) + 1)
    o = R._armed_orders(out, tc, np.full(n, 104.0))
    assert list(o["bar"]) == [10] and list(o["sides"]) == [0] and list(o["pid"]) == [22] and list(o["n_keys"]) == [2]
    assert o["buy"][0] == o["sell"][0] == 108.0                                 # p2 for both
    assert o["buy_stop"][0] == 108.0 - 0.5 * 8 and o["sell_stop"][0] == 108.0 + 0.5 * 8
    assert o["buy_target"][0] == 108.0 + 8 and o["sell_target"][0] == 108.0 - 8
    assert o["until"][0] == tc[20] and o["next_add"][0] == 20
    O = M.orders(o["bar"], o["until"], buy=o["buy"], sell=o["sell"], buy_stop=o["buy_stop"], sell_stop=o["sell_stop"],
                 buy_target=o["buy_target"], sell_target=o["sell_target"])
    assert len(O) == 1 and np.isfinite(O.buy[0]) and np.isfinite(O.sell[0])
    al, ash = np.ones(n, bool), np.ones(n, bool)
    ash[10] = False
    G = F.gate_orders(O, al, ash)                                               # a filter removes one side only
    assert np.isfinite(G.buy[0]) and np.isnan(G.sell[0])


def test_cs_cancel_time_is_the_next_swing_or_the_plan_horizon():
    """On random-walk bars: every order's cancel time is the earlier of the close of the next bar that adds a swing
    and the close of bar D + 30 (D = the live swing at the placement)."""
    mk = M.TMarket2(SYM, rw_m1(60, 4))
    ctx = M.Context(mk)
    for tf in ("1H", "4H"):
        b = ctx.bars(tf)
        out = HP.patterns(b.h, b.l, b.c)
        adds = np.flatnonzero(out["added"])
        cs = R.events(ctx, tf)["cs"]
        assert len(cs["bar"]) > 5
        for t, until, d, nxt in zip(cs["bar"], cs["until"], cs["d_bar"], cs["next_add"]):
            assert out["added"][t] and d == out["forming_qbar"][t, 0] == t
            k = adds[adds > t]
            assert nxt == (k[0] if len(k) else -1)
            want = min(int(b.tc[k[0]]) if len(k) else R.NEVER, int(b.tc[d + 30]) if d + 30 < len(b) else R.NEVER)
            assert until == want


# ───────────────────────────── 3. filters ─────────────────────────────

def masks_for(ctx, tf, long_ok=None):
    """(allow_long, allow_short) for ``tf``: all True, with ``long_ok`` {bar: bool} overriding allow_long."""
    n = len(ctx.bars(tf))
    al, ash = np.ones(n, bool), np.ones(n, bool)
    for k, v in (long_ok or {}).items():
        al[k] = v
    return al, ash


def test_filters_gate_the_entry_at_its_decision_close_only(monkeypatch):
    mk = hand_market(BAT, BAT_HF_BAR, [(0, 108.05), (120, 113.0)])
    ctx = M.Context(mk)
    seen = []

    def fake(cfg):
        def allow(ctx_, tf, name):
            seen.append((tf, name))
            return cfg[name]
        return allow
    n = len(ctx.bars("1H"))
    no_long_at_63 = masks_for(ctx, "1H", {BAT_HF_BAR: False})
    no_long_after = masks_for(ctx, "1H", {k: False for k in range(BAT_HF_BAR + 1, n)})
    monkeypatch.setattr(F, "allow", fake({"F0": masks_for(ctx, "1H"), "F2-4H": no_long_at_63, "FR": no_long_after}))
    base = run(mk, variant("HP-HF"), ctx=ctx).trades.iloc[0]
    assert base.entry_ix == hour_ix(BAT_HF_BAR + 1)
    r = run(mk, variant("HP-HF", slot="F2"), ctx=ctx)                 # F2 on 1H is F2-4H: the long is not allowed
    assert r.counts["candidates"] == 0 and len(r.trades) == 0           # (bar 63 is these bars' only HF candidate)
    tr = run(mk, variant("HP-HF", slot="FR"), ctx=ctx).trades.iloc[0]  # allowed at 63, never again: kept, own exit
    assert (tr.entry_ix, tr.exit_ix, tr.reason, tr.exit) == (base.entry_ix, base.exit_ix, base.reason, base.exit)
    assert ("1H", "F2-4H") in seen and ("1H", "FR") in seen and ("1H", "F0") in seen
    # 50/50 legs stay aligned with the entries the gate keeps
    r = run(mk, variant("HP-HF", target="50/50", slot="FR"), ctx=ctx)
    assert len(r.trades) == 1 and r.trades.entry_ix.iloc[0] == base.entry_ix
    assert r.trades.reasons.iloc[0] == "target|end"                    # TP1 taken, TP2 (115.416) never reached


def test_filters_gate_stop_orders_at_their_placement_close(monkeypatch):
    c61 = float(hand_market(DB, DB_CS_BAR).tbars("1H").c[DB_CS_BAR])
    mk = hand_market(DB, DB_CS_BAR, [(0, c61), (360, 116.0)])
    ctx = M.Context(mk)
    n = len(ctx.bars("1H"))
    cfg = {"F2-4H": masks_for(ctx, "1H", {DB_CS_BAR: False}), "F0": masks_for(ctx, "1H")}
    monkeypatch.setattr(F, "allow", lambda ctx_, tf, name: cfg[name])
    r = run(mk, variant("HP-CS", slot="F2"), ctx=ctx)
    assert r.counts["candidates"] == 0 and len(r.trades) == 0
    cfg["F2-4H"] = masks_for(ctx, "1H", {k: False for k in range(DB_CS_BAR + 1, n)})   # turns after the placement
    tr = run(mk, variant("HP-CS", slot="F2"), ctx=ctx).trades.iloc[0]
    assert tr.entry == 108.0 and tr.reason == "target"


def test_each_row_reads_the_filter_of_its_slot_and_timeframe(monkeypatch):
    mk = M.TMarket2(SYM, rw_m1(40, 2))
    ctx = M.Context(mk)
    seen = set()

    def allow(ctx_, tf, name):
        seen.add((tf, name))
        n = len(ctx_.bars(tf))
        return np.ones(n, bool), np.ones(n, bool)
    monkeypatch.setattr(F, "allow", allow)
    for v in R.variants(SYM):
        R.build(v, ctx)
    want = {("1H", "F0"), ("1H", "F2-4H"), ("1H", "FR"), ("4H", "F0"), ("4H", "F2-1D"), ("4H", "FR"),
            ("1D", "F0"), ("1D", "F1"), ("1D", "FR")}
    assert seen == want


def test_f1_and_f2_are_the_ma200_sides_of_the_own_or_the_last_closed_higher_bar(rw):
    """F1 on 1D, F2-4H on 1H, F2-1D on 4H (the F2 slot, reading 1) as ``tradeiq2_filters.allow`` gives them, against
    an independent reading: SMA(close, 200) of that timeframe, the last bar closed at the signal bar's close, strict
    sides, neither before the average exists (PREREG 5)."""
    ctx = M.Context(rw)
    for tf, name, htf in (("1D", "F1", "1D"), ("1H", "F2-4H", "4H"), ("4H", "F2-1D", "1D")):
        assert R.filter_name("F2", tf) == name
        hb, lb = ctx.bars(htf), ctx.bars(tf)
        c = hb.c
        ma = np.full(len(c), np.nan)
        cs = np.concatenate(([0.0], np.cumsum(c)))
        ma[199:] = (cs[200:] - cs[:-200]) / 200.0
        up, dn = c > np.nan_to_num(ma, nan=np.inf), c < np.nan_to_num(ma, nan=-np.inf)
        if htf == tf:
            want_l, want_s = up, dn
        else:
            i = np.searchsorted(hb.tc, lb.tc, side="right") - 1
            want_l = np.where(i >= 0, up[np.maximum(i, 0)], False)
            want_s = np.where(i >= 0, dn[np.maximum(i, 0)], False)
        al, ash = F.allow(ctx, tf, name)
        if tf == "1H":
            assert al.any() and ash.any()
        assert np.array_equal(al, want_l) and np.array_equal(ash, want_s), (tf, name)


def test_fr_is_the_ribbon_trend_of_the_higher_timeframe(rw):
    """FR as these rows read it (``tradeiq2_filters.allow``): 1H rows the last closed 4H bar's ribbon trend, 4H rows the
    last closed 1D bar's, 1D rows the 1D ribbon itself (PREREG 5)."""
    RB = pytest.importorskip("backtesting.research.tradeiq2_ind_ribbon")
    ctx = M.Context(rw)
    for tf, htf in (("1H", "4H"), ("4H", "1D"), ("1D", "1D")):
        hb, lb = ctx.bars(htf), ctx.bars(tf)
        tr = np.asarray(RB.ribbon(hb.o, hb.h, hb.l, hb.c)["trend"], np.float64)
        if htf == tf:
            want = tr
        else:
            i = np.searchsorted(hb.tc, lb.tc, side="right") - 1              # the last higher bar closed by then
            want = np.where(i >= 0, tr[np.maximum(i, 0)], 0.0)
        al, ash = F.allow(ctx, tf, "FR")
        assert np.array_equal(al, want == 1.0) and np.array_equal(ash, want == -1.0)
        assert not (al & ash).any()
        if tf != "1D":
            assert al.any() and ash.any()


# ───────────────────────────── 4. an independent reading on random-walk bars ─────────────────────────────

def rw_m1(days, seed, trend=False):
    """Seeded BTC-like M1 bars from T0, around the clock (a random walk; ``trend``: drifting regimes of two days)."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    drift = np.repeat(rng.normal(0.0, 0.4, n // 2880 + 1), 2880)[:n] if trend else 0.0
    c = 5000.0 + np.cumsum(rng.normal(0.0, 1.0, n) + drift)
    o = np.concatenate(([5000.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.6, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.6, n))
    return {"t": T0 + 60 * np.arange(n, dtype=np.int64), "o": o, "h": h, "l": l, "c": c,
            "spread_mean": np.full(n, 0.5), "n": np.ones(n)}


@pytest.fixture(scope="module")
def rw():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        mk = M.TMarket2(SYM, rw_m1(200, 11))
    return mk


def reading(b, rule, drawn=""):
    """PREREG 6.7 and the porting notes (8.2-8.6) read with plain loops over the port's raw output: the candidate
    rows (decision bar, side, sl, tp1, tp2, D's bar, pid) before the skip rule, the time stop and the filters."""
    out = HP.patterns(b.h, b.l, b.c)
    fm, cf = out["forming"], out["confirmed"]
    rows = []
    if rule == "HP-HF":
        seen = set()
        for x in fm.itertuples(index=False):
            if x.first_hit and x.id <= 21 and x.instance_key not in seen:
                seen.add(x.instance_key)
                rows.append((x.t_bar, x.dir, x.sl, x.tp1, x.tp2, x.b0, x.id))
    elif rule == "HP-CF":
        seen, by = set(), {}
        for x in fm.itertuples(index=False):
            if x.id >= 22 and x.instance_key not in seen:
                seen.add(x.instance_key)
                by.setdefault(x.t_bar, []).append((x.t_bar, x.dir, x.sl, x.tp1, x.tp2, x.b0, x.id))
        rows = [min(v, key=lambda r: r[6]) for _, v in sorted(by.items())]
    elif rule in ("HP-HC", "HP-CC", "HP-DRAWN"):
        harm = rule == "HP-HC" or drawn.startswith("H")
        for x in cf.itertuples(index=False):
            if x.first_hit and (x.id <= 21) == harm and (not drawn.endswith("SHOWN") or x.drawn):
                rows.append((x.b0 if rule == "HP-DRAWN" else x.t_bar, x.dir, x.sl, x.tp1, x.tp2, x.b0, x.id))
    elif rule == "HP-CS":
        q, qb = out["forming_q"], out["forming_qbar"]
        first = {}
        for t in range(len(b)):
            if out["n_piv"][t] < 11:
                continue
            for pid in range(22, 38):
                if bool(HP.check(pid, q[t], math.inf if HP.DIR[pid] > 0 else -math.inf)):
                    first.setdefault((pid,) + tuple(int(x) for x in qb[t, 1:HP.PTS[pid]]), t)
        by = {}
        for key, t in first.items():
            by.setdefault(t, []).append(key[0])
        for t in sorted(by):
            lv = {}
            for d in (1, -1):
                mine = sorted(p_ for p_ in by[t] if HP.DIR[p_] == d)
                if mine:
                    lv[d] = (mine[0],) + tuple(HP.plan_levels(mine[0], q[t]))   # pid, unit, entry, sl, tp1, tp2
            side = 0 if len(lv) == 2 else next(iter(lv))
            nan = float("nan")
            get = lambda d, k: lv[d][k] if d in lv else nan
            rows.append((t, side, min(v[0] for v in lv.values()), int(qb[t, 0]), get(1, 2), get(1, 3), get(1, 4),
                         get(-1, 2), get(-1, 3), get(-1, 4)))
        return pd.DataFrame(rows, columns=["bar", "side", "pid", "d_bar", "buy", "buy_stop", "buy_target", "sell",
                                           "sell_stop", "sell_target"])
    return pd.DataFrame(rows, columns=["bar", "side", "sl", "tp1", "tp2", "d_bar", "pid"])


@pytest.mark.parametrize("rule,drawn", [("HP-HF", ""), ("HP-HC", ""), ("HP-CF", ""), ("HP-CS", ""), ("HP-CC", ""),
                                        ("HP-DRAWN", "HALL"), ("HP-DRAWN", "HSHOWN"), ("HP-DRAWN", "CALL"),
                                        ("HP-DRAWN", "CSHOWN")])
def test_the_rows_equal_an_independent_reading_of_the_plan(rw, rule, drawn):
    ctx = M.Context(rw)
    harmonic = rule in ("HP-HF", "HP-HC") or drawn.startswith("H")
    total = 0
    for tf in (("1H", "4H", "1D") if harmonic else ("1H", "4H")):
        b = ctx.bars(tf)
        want = reading(b, rule, drawn)
        s = vspec(rule, tf, drawn=drawn)
        if s.skips_past_tp1:
            want = want[~(want.side * (b.c[want.bar.to_numpy()] - want.tp1) >= 0)]
        want = want[want.d_bar + 30 > want.bar].reset_index(drop=True)
        got = R.rows_of(s, ctx)
        assert np.array_equal(got["bar"], want.bar.to_numpy()), (rule, tf)
        assert np.array_equal(got["sides" if rule == "HP-CS" else "side"], want.side.to_numpy()), (rule, tf)
        assert np.array_equal(got["pid"], want.pid.to_numpy()) and np.array_equal(got["d_bar"], want.d_bar.to_numpy())
        cols = ("buy", "buy_stop", "buy_target", "sell", "sell_stop", "sell_target") if rule == "HP-CS" else \
            ("sl", "tp1", "tp2")
        for k in cols:
            assert np.array_equal(got[k], want[k].to_numpy(), equal_nan=True), (rule, tf, k)
        xb = want.d_bar.to_numpy() + 30
        assert np.array_equal(got["exit_bar"], np.where(xb < len(b), xb, -1))
        total += len(want)
    assert total > 10, rule


@pytest.mark.parametrize("rule,target", [("HP-HF", "50/50"), ("HP-HF", "TP2"), ("HP-CF", "TP1"), ("HP-CS", "TP1")])
def test_the_exec_rows_are_the_gated_candidates_with_their_own_levels(rw, monkeypatch, rule, target):
    """The gate removes every other candidate's side: the Exec keeps exactly the others, each with its own stop, target
    (the 50/50 legs' targets line up with the kept entries), time stop and tag."""
    ctx = M.Context(rw)
    s = vspec(rule, "1H", target, "F2")
    rows = R.rows_of(s, ctx)
    n = len(ctx.bars("1H"))
    al, ash = np.ones(n, bool), np.ones(n, bool)
    al[rows["bar"][::2]] = False
    ash[rows["bar"][::2]] = False
    monkeypatch.setattr(F, "allow", lambda ctx_, tf, name: (al, ash))
    ex = R.build(s.variant(), ctx)
    keep = np.ones(len(rows["bar"]), bool)
    keep[::2] = False
    if rule == "HP-CS":
        O = ex.orders
        assert np.array_equal(O.bar, rows["bar"][keep]) and np.array_equal(O.until, rows["until"][keep])
        for k in ("buy", "buy_stop", "buy_target", "sell", "sell_stop", "sell_target"):
            assert np.array_equal(getattr(O, k), rows[k][keep], equal_nan=True), k
        assert np.array_equal(O.exit_bar, rows["exit_bar"][keep]) and np.array_equal(O.tag, rows["pid"][keep])
        return
    E = ex.entries
    assert len(E) == int(keep.sum()) > 3
    assert np.array_equal(E.bar, rows["bar"][keep]) and np.array_equal(E.side, rows["side"][keep])
    assert np.array_equal(E.stop_level, rows["sl"][keep]) and np.array_equal(E.exit_bar, rows["exit_bar"][keep])
    assert np.array_equal(E.tag, rows["pid"][keep]) and np.isnan(E.stop_dist).all() and np.isnan(E.target_r).all()
    if target == "50/50":
        assert np.isnan(E.target_level).all() and [g.weight for g in ex.legs] == [0.5, 0.5]
        assert np.array_equal(ex.legs[0].target_level, rows["tp1"][keep])
        assert np.array_equal(ex.legs[1].target_level, rows["tp2"][keep])
    else:
        assert np.array_equal(E.target_level, rows[target.lower()][keep]) and len(ex.legs) == 1


def test_hp_hf_first_bars_are_ds_bars_and_chart_bars_share_one_plan(rw):
    ctx = M.Context(rw)
    for tf in ("1H", "4H", "1D"):
        ev = R.events(ctx, tf)
        assert np.array_equal(ev["hf"]["bar"], ev["hf"]["d_bar"])            # harmonics do not read the close
        for k in ("hf", "cf", "cs", "hc", "cc"):
            assert np.all(np.diff(ev[k]["bar"]) > 0), (tf, k)                 # one candidate per bar
        assert len(ev["hf"]["bar"]) > 0


# ───────────────────────────── 5. causality ─────────────────────────────

ROW_SPECS = [vspec("HP-HF", tf) for tf in ("1H", "4H", "1D")] + [vspec("HP-HC", tf) for tf in ("1H", "4H", "1D")] + \
    [vspec(r, tf) for r in ("HP-CF", "HP-CS", "HP-CC") for tf in ("1H", "4H")]
RUN_SPECS = [vspec("HP-HF", "1H", "50/50", "FR"), vspec("HP-HF", "4H", "TP2"), vspec("HP-HC", "1H"),
             vspec("HP-CF", "1H", "TP1", "F2"), vspec("HP-CS", "1H", "TP1", "F2"), vspec("HP-CS", "4H"),
             vspec("HP-CC", "1H")]


def _cut(mk, cut_s):
    k = int(np.searchsorted(mk.t, cut_s, side="left"))
    m1 = {"t": mk.t[:k], "o": mk.o[:k], "h": mk.h[:k], "l": mk.l[:k], "c": mk.c[:k], "spread_mean": mk.sp[:k],
          "n": mk.n[:k]}
    return M.TMarket2(mk.symbol, {key: np.array(v) for key, v in m1.items()})


@pytest.mark.parametrize("frac", [0.45, 0.8])
def test_no_look_ahead_candidates_rows_and_trades(rw, frac):
    cut_s = int(T0 + 3600 * round((rw.t[-1] - T0) / 3600 * frac))
    short = _cut(rw, cut_s)
    full_ctx, cut_ctx = M.Context(rw), M.Context(short)
    for s in ROW_SPECS:
        bf, bc = full_ctx.bars(s.tf), cut_ctx.bars(s.tf)
        a, z = R.rows_of(s, full_ctx), R.rows_of(s, cut_ctx)
        ka = bf.tc[a["bar"]] <= cut_s                              # decided by the cut (complete bars)
        kz = bc.tc[z["bar"]] <= cut_s
        assert ka.sum() == kz.sum(), s.id
        for key in a:
            x, y = a[key][ka], z[key][kz]
            if key == "until":                                     # the cancel time: equal once it is in the past
                early = x <= cut_s
                assert np.array_equal(x[early], y[early]) and np.all(y[~early] > cut_s), s.id
                continue
            if key == "next_add":                                  # the next swing: equal once it has come
                known = (x >= 0) & (bf.tc[np.maximum(x, 0)] <= cut_s)
                assert np.array_equal(x[known], y[known]), s.id
                assert np.all((y[~known] == -1) | (bc.tc[np.maximum(y[~known], 0)] > cut_s)), s.id
                continue
            if key == "exit_bar":                                  # the time stop's bar: -1 beyond the data
                inside = a["d_bar"][ka] + 30 < len(bc)
                assert np.array_equal(x[inside], y[inside]) and np.all(y[~inside] == -1), s.id
                continue
            assert np.array_equal(x, y, equal_nan=x.dtype.kind == "f"), (s.id, key)
    # HP-DRAWN looks ahead by its confirmation delay: decided on D's bar, known at t_conf
    for st, tfs in (("HALL", ("1H", "4H", "1D")), ("CALL", ("1H", "4H"))):
        for tf in tfs:
            s = vspec("HP-DRAWN", tf, drawn=st)
            bf, bc = full_ctx.bars(tf), cut_ctx.bars(tf)
            a, z = R.rows_of(s, full_ctx), R.rows_of(s, cut_ctx)
            assert np.all(a["t_conf"] > a["bar"])
            known = bf.tc[a["t_conf"]] <= cut_s                    # confirmed by the cut
            zk = bc.tc[z["t_conf"]] <= cut_s
            assert np.array_equal(a["bar"][known], z["bar"][zk])
            decided = bf.tc[a["bar"]] <= cut_s                     # decided by the cut, known only after it
            assert set(a["bar"][decided & ~known]).isdisjoint(set(z["bar"][zk]))
    # the harness's trades over [T0, cut) are identical on both markets
    for s in RUN_SPECS:
        v = s.variant()
        ra = M.run_exec(rw, R.build(v, full_ctx), T0, cut_s)
        rz = M.run_exec(short, R.build(v, cut_ctx), T0, cut_s)
        assert ra.counts == rz.counts, v.id
        cols = ["entry_time", "exit_time", "side", "entry", "exit", "reason", "pnl", "risk", "tag", "bar"]
        assert ra.trades[cols].equals(rz.trades[cols]), v.id
        assert len(ra.trades) > 0, v.id


# ───────────────────────────── 6. real bars (counts and geometry only) ─────────────────────────────

# the porting notes' section 6 (harness's Development decision bars: closing after 2019-01-01, filled before
# 2023-01-01): per symbol and timeframe, HP-HF entry bars (first-hit reading) and those skipped at or beyond TP1,
# HP-HC and HP-CC (confirmed first hits harmonic / chart), HP-CF chart instances (any chart id), HP-CS armed keys
DEV_COUNTS = {
    ("XAUUSDm", "1H"): dict(hf=1144, skip=85, hc=840, hc_skip=401, cc=110, cf=160, cs=312, cs_broken=85),
    ("XAUUSDm", "4H"): dict(hf=310, skip=14, hc=230, hc_skip=94, cc=30, cf=47, cs=80, cs_broken=26),
    ("XAUUSDm", "1D"): dict(hf=49, skip=2, hc=35, hc_skip=16, cc=6, cf=7, cs=11, cs_broken=3),
    ("BTCUSDm", "1H"): dict(hf=1546, skip=146, hc=1182, hc_skip=562, cc=160, cf=235, cs=421, cs_broken=127),
    ("BTCUSDm", "4H"): dict(hf=403, skip=31, hc=302, hc_skip=135, cc=35, cf=59, cs=113, cs_broken=31),
    ("BTCUSDm", "1D"): dict(hf=69, skip=3, hc=42, hc_skip=20, cc=6, cf=9, cs=25, cs_broken=5),
}
# hc_skip: HP-HC alerts whose detection close is at or beyond TP1 (reading 4); cs_broken: HP-CS's armed keys whose
# placement close is already beyond p2 (reading 6): their orders fill at the next M1 open. Both counted when the rows
# were built (28 Nov 2026) from the same bars.
_REAL: dict = {}


def real(symbol):
    """The symbol's market to 2023-01-01 (one symbol in memory at a time) and its Context; skipped without the store."""
    if symbol in _REAL:
        return _REAL[symbol]
    _REAL.clear()
    start = M.data_start(symbol)
    months = store.available_months(symbol)
    if (2022, 12) not in months or (int(start[:4]), int(start[5:7])) not in months:
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    mk = M.load(symbol, end="2023-01-01")
    assert int(mk.t[-1]) + 60 <= TM.s_of("2023-01-01")          # nothing after Development is in memory
    _REAL[symbol] = (mk, M.Context(mk))
    return _REAL[symbol]


@pytest.mark.parametrize("symbol", M.SYMBOLS)
def test_real_bars_development_counts_of_the_porting_notes(symbol):
    mk, ctx = real(symbol)
    iz = int(np.searchsorted(mk.t, TM.s_of("2023-01-01"), side="left"))
    for tf in ("1H", "4H", "1D"):
        b = ctx.bars(tf)
        dev = (b.tc > TM.s_of("2019-01-01")) & (b.ex < iz)
        ev = R.events(ctx, tf)
        want = DEV_COUNTS[(symbol, tf)]
        hf = ev["hf"]
        d = dev[hf["bar"]]
        cs = ev["cs"]
        p2 = np.where(cs["sides"] == 1, cs["buy"], cs["sell"])
        broken = dev[cs["bar"]] & (cs["sides"] * (cs["close"] - p2) > 0)
        got = dict(hf=int(d.sum()), skip=int((d & (hf["side"] * (hf["close"] - hf["tp1"]) >= 0)).sum()),
                   hc=int(dev[ev["hc"]["bar"]].sum()), cc=int(dev[ev["cc"]["bar"]].sum()),
                   hc_skip=int((dev[ev["hc"]["bar"]] & (ev["hc"]["side"] * (ev["hc"]["close"] - ev["hc"]["tp1"])
                                                        >= 0)).sum()),
                   cf=int(ev["cf"]["n_ids"][dev[ev["cf"]["bar"]]].sum()),
                   cs=int(cs["n_keys"][dev[cs["bar"]]].sum()), cs_broken=int(cs["n_keys"][broken].sum()))
        assert got == want, (symbol, tf, got)
        # the HP-HF rows: the skipped ones removed, no time stop already passed in Development
        rows = R.rows_of(vspec("HP-HF", tf, symbol=symbol), ctx)
        assert int(dev[rows["bar"]].sum()) == want["hf"] - want["skip"]
        # every chart bar of HP-CF points one way; no HP-CS bar has both directions armed in Development
        assert np.all(ev["cs"]["sides"][dev[ev["cs"]["bar"]]] != 0)


SMOKE = [("HP-HF", "1H", "TP1", "F0"), ("HP-HF", "4H", "50/50", "FR"), ("HP-HF", "1D", "TP2", "F2"),
         ("HP-HC", "1D", "TP1", "F0"), ("HP-CF", "1H", "TP2", "F2"), ("HP-CF", "4H", "TP1", "FR"),
         ("HP-CS", "1H", "TP1", "F0"), ("HP-CS", "4H", "TP1", "F2"), ("HP-CC", "4H", "TP1", "F0"),
         ("HP-DRAWN", "1H", "TP1", "HALL"), ("HP-DRAWN", "4H", "TP1", "CSHOWN")]
REASONS = {"target", "stop", "gap stop", "gap target", "signal", "end"}


@pytest.mark.parametrize("symbol", M.SYMBOLS)
def test_real_bars_smoke_run_of_each_rule_type_on_development_2019_h1(symbol):
    """One row of each rule type through ``tradeiq2_market.run_exec`` on 2019-01-01 to 2019-06-30 at x1.0 and x1.5.
    Asserted: the counts add up, every position opens where its candidate says (fill bar, side, the stop as a distance
    from the fill), every exit is one the rule can make and never after its time stop. The profit is never read."""
    mk, ctx = real(symbol)
    a_s, z_s = TM.s_of("2019-01-01"), TM.s_of("2019-07-01")
    iz = int(np.searchsorted(mk.t, z_s, side="left"))
    taken = {}
    for rule, tf, target, slot in SMOKE:
        drawn = slot if rule == "HP-DRAWN" else ""
        v = variant(rule, tf, target, "F0" if rule == "HP-DRAWN" else slot, drawn, symbol)
        ex = R.build(v, ctx)
        b = ctx.bars(tf)
        for cost in (1.0, 1.5):
            r = M.run_exec(mk, ex, a_s, z_s, cost)
            c = r.counts
            tr = r.trades
            assert c["taken"] == len(tr), v.id
            taken[rule] = taken.get(rule, 0) + len(tr)
            if ex.orders is not None:
                O = ex.orders
                inside = (b.tc[O.bar] > a_s) & (b.ex[O.bar] < iz)
                assert c["candidates"] == int(inside.sum())
                assert c["taken"] + c["busy"] + c["unfilled"] + c["dropped_stop"] + c["dropped_target"] == \
                    c["candidates"]
                for x in tr.itertuples(index=False):
                    level = np.where(x.side == 1, O.buy, O.sell)
                    cand = np.flatnonzero(np.isfinite(level) & (b.ex[O.bar] <= x.entry_ix)
                                          & (np.searchsorted(mk.t, O.until, side="left") > x.entry_ix))
                    assert len(cand), v.id
                    q = cand[-1]
                    assert (x.entry >= level[q] - 1e-9) if x.side == 1 else (x.entry <= level[q] + 1e-9)
                    stop = O.buy_stop[q] if x.side == 1 else O.sell_stop[q]
                    assert abs(x.risk - abs(x.entry - stop)) < 1e-6 and x.reason in REASONS
            else:
                E = ex.entries
                inside = (b.tc[E.bar] > a_s) & (b.ex[E.bar] < iz)
                assert c["candidates"] == int(inside.sum())
                assert c["taken"] + c["busy"] + c["dropped_stop"] + c["dropped_target"] == c["candidates"]
                at = {int(k): i for i, k in enumerate(E.bar)}
                for x in tr.itertuples(index=False):
                    i = at[int(x.bar)]
                    assert x.entry_ix == b.ex[E.bar[i]] and x.side == E.side[i] and x.tag == E.tag[i]
                    assert abs(x.risk - abs(x.entry - E.stop_level[i])) < 1e-6
                    xb = int(E.exit_bar[i])
                    if xb >= 0 and b.ex[xb] < iz:
                        assert x.exit_ix <= b.ex[xb], v.id                   # never after the time stop
                    reasons = x.reasons.split("|") if isinstance(getattr(x, "reasons", None), str) else [x.reason]
                    assert set(reasons) <= REASONS
                    if x.reason == "signal":
                        assert x.exit_ix == b.ex[xb]
            if target == "50/50":
                assert len(r.legs) == 2 and all(w == 0.5 for w, _ in r.legs)
    assert set(taken) == set(R.RULES) and all(n > 0 for n in taken.values()), taken   # every rule type traded
    if symbol == M.SYMBOLS[-1]:
        _REAL.clear()
