"""
Study 2's coil rules (``backtesting/research/tradeiq2_rules_coil.py``): the rows of PREREG 6.9 (COIL-RIB, COIL-MA and
COIL-0 with the exits X-TR / X-3R and the grades BIG / VOL / ADX / ALL3), their entries, stops, exits, trend filters
and grades, executed by ``tradeiq2_market``.

(a) The grid: the rows per symbol are the PREREG's numbers (written here from its text: 30 COIL-RIB + 3 COIL-MA + 3
    COIL-0 = 36 per symbol, all eligible, family COIL), with unique ids that carry the tokens the driver pairs rows by
    (a grade -> none for claim 20, X-3R -> X-TR, COIL-MA / COIL-RIB -> COIL-0); none on the claim markets; the
    driver's own grid check accepts them.
(b) The pieces on plain arrays, by hand: the stop distance and its clamp; the trend trail (the closes since the entry
    start after the breakout bar, each bar's own ATR, no ratchet, strict, shorts mirrored; against a plain loop); the
    grades (inclusive; the volume SMA includes the bar); the coil ordinals.
(c) Hand-made bars with an injected coil (the port's contract, set through the Context's cache together with the
    ATR, the ribbon trend and F1), so every price is known by hand: the entry at the breakout's close filled at the
    next M1 open; the stop from the ACTUAL fill (also at x1.5 and after a gap through the box: nothing is dropped, the
    absolute-level rules of PREREG 4 never bite); X-TR's exit at the close filled at the next open; X-3R's target; the
    stop inside the bar, also against the target and after a gap; shorts mirrored; one position at a time (busy, no
    reversal); re-entry at the exit's open; tags = coils.
(d) Trend filters at the breakout's close: COIL-RIB the same timeframe's ribbon trend, COIL-MA F1, COIL-0 none; a
    filter never closes an open trade; each row asks exactly its filter (and only VOL / ALL3 read the volume).
(e) Grades at the breakout bar on hand-made bars (the bar's range, its tick volume against its 20-bar SMA, the ADX);
    BTC's VOL reads the Binance volume.
(f) The real port on a synthetic market with coils on every timeframe: COIL-0's entries are the port's breakouts with
    the stop and trail computed by hand; every gate keeps exactly the breakouts it allows; one trade per coil, also
    when a coil's breakout is refused; the harness's trades (fills, one at a time, exits by the trail or the stop).
(g) Causality: every decision of a bar closing at or before T is the same when the data after T is removed (all 36
    rows; synthetic bars here, the study's bars in (h)).
(h) Real data (skipped when the store is absent; read to 2019-07-01 only): causality, every breakout has a stop in
    [0.75, 3] ATR, BTC's VOL reads Binance volume, and an execution smoke test on Development data (2019-01-01 to
    2019-06-30) for one row of each rule type through ``tradeiq2_market.run_variant``. Its profit or loss is neither
    printed, asserted nor reported: only counts, times and stop geometry are checked.

Every test runs with both guards pointed at empty folders (no FINALISTS.md: nothing at or after 2024-07-01).
"""

from __future__ import annotations

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_coil as CI
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_coil as C

T0 = TM.s_of("2019-03-04")              # a Monday, 00:00 UTC
SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")
NAN = float("nan")


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

# PREREG 6.9 "Size: COIL-RIB x {X-TR, X-3R} x {none, BIG, VOL, ADX, ALL3} x 3 timeframes = 30 rows; COIL-MA and COIL-0
# x X-TR x none x 3 timeframes = 6 rows. 36 rows per symbol." PREREG 6.9 marks no row "not eligible" or "information
# only"; PREREG 7's family of the coil is COIL (and COIL counts as its own script for the finalists).
PLAN_ROWS = 36
PLAN = {("COIL", True): 36}
PLAN_RULES = {"COIL-RIB": 2 * 5 * 3, "COIL-MA": 3, "COIL-0": 3}
GRADES = ("none", "BIG", "VOL", "ADX", "ALL3")


def by_id(symbol):
    return {v.id: v for v in C.variants(symbol)}


def V(vid):
    return by_id(vid.split("|")[0])[vid]


@pytest.mark.parametrize("symbol", SYMS)
def test_a_the_rows_per_symbol_are_the_preregs(symbol):
    vs = C.variants(symbol)
    assert len(vs) == PLAN_ROWS == sum(PLAN_RULES.values()) == 30 + 6
    got, rules = {}, {}
    for v in vs:
        got[(v.family, v.eligible)] = got.get((v.family, v.eligible), 0) + 1
        rules[v.params["rule"]] = rules.get(v.params["rule"], 0) + 1
    assert got == PLAN and C.plan_counts(symbol) == PLAN and rules == PLAN_RULES
    ids = [v.id for v in vs]
    assert len(set(ids)) == len(ids)
    for v in vs:
        p = v.params
        assert isinstance(v, M.Variant) and v.symbol == symbol and v.tf in TFS
        assert v.script == "COIL" and v.family == "COIL" and v.eligible is True and v.info == ""
        assert v.id == f"{symbol}|{v.tf}|COIL|{p['rule']}|{p['exit']}|{p['grade']}"
        assert not any(ch.isspace() for ch in v.id)
        assert p["filter"] == {"COIL-RIB": "ribbon", "COIL-MA": "F1", "COIL-0": "F0"}[p["rule"]]
        assert p["stop"] == C.STOP_NAME
        assert M.Variant(**{k: getattr(v, k) for k in ("id", "symbol", "tf", "script", "family", "eligible",
                                                       "info", "params")}).ident()["params"]      # JSON-able
    for tf in TFS:
        rib = {(v.params["exit"], v.params["grade"]) for v in vs if v.tf == tf and v.params["rule"] == "COIL-RIB"}
        assert rib == {(e, g) for e in ("X-TR", "X-3R") for g in GRADES}
        for rule in ("COIL-MA", "COIL-0"):
            assert [(v.params["exit"], v.params["grade"]) for v in vs if v.tf == tf and v.params["rule"] == rule] == \
                [("X-TR", "none")]


def test_a_no_rows_on_the_claim_markets_and_other_symbols_raise():
    assert C.variants("USTECm") == [] and C.variants("EURUSDm") == [] and C.variants("GBPUSDm") == []
    with pytest.raises(ValueError):
        C.variants("ETHUSDm")


def _swap(vid, old, new):
    t = vid.split("|")
    return "|".join(new if x == old else x for x in t) if t.count(old) == 1 else None


def test_a_ids_pair_the_way_the_driver_pairs_them():
    for s in SYMS:
        ids = by_id(s)
        for v in ids.values():
            p = v.params
            if p["grade"] != "none":                                      # claim 20: a grade against no grade
                assert _swap(v.id, p["grade"], "none") in ids
            if p["exit"] == "X-3R":
                assert _swap(v.id, "X-3R", "X-TR") in ids
            if p["rule"] != "COIL-0" and p["grade"] == "none" and p["exit"] == "X-TR":
                assert _swap(v.id, p["rule"], "COIL-0") in ids
        assert sum(1 for v in ids.values() if v.tf == "4H") == 12           # claim 20 reads the 4H rows


def test_a_describe_build_and_the_drivers_grid_check_accept_the_rows():
    o = np.full(720, 100.0)
    ctx = M.Context(M.TMarket2("XAUUSDm", {"t": T0 + 60 * np.arange(720, dtype=np.int64), "o": o, "h": o + 1.0,
                                           "l": o - 1.0, "c": o.copy(), "spread_mean": np.full(720, 0.2),
                                           "n": np.ones(720)}))
    for v in C.variants("XAUUSDm"):
        text = C.describe(v)
        assert len(text) > 200 and v.params["rule"] in text
    v = V("XAUUSDm|1H|COIL|COIL-0|X-TR|none")
    ex = C.build(v, ctx)
    assert isinstance(ex, M.Exec) and ex.kind == "events" and ex.label == v.id and len(ex.entries) == 0
    with pytest.raises(ValueError):
        C.build(M.Variant("XAUUSDm|1H|COIL|COIL-MA|X-TR|BIG", "XAUUSDm", "1H", "COIL", "COIL"), ctx)   # not a row
    with pytest.raises(ValueError):
        C.build(M.Variant("XAUUSDm|1H|COIL|COIL-0|X-TR|none", "XAUUSDm", "4H", "COIL", "COIL"), ctx)  # tf differs
    with pytest.raises(ValueError):
        C.build(V("BTCUSDm|1H|COIL|COIL-0|X-TR|none"), ctx)                  # a BTC row on gold's context
    with pytest.raises(ValueError):
        C.coil_entries(ctx, "1H", "COIL-0", "X-TR", "BIG")                   # COIL-0 has no grades
    with pytest.raises(ValueError):
        C.coil_entries(ctx, "M15", "COIL-0", "X-TR", "none")                 # not a coil timeframe
    try:                                                                     # the driver's contract and counts
        from backtesting.research import tradeiq2 as D
    except Exception as e:                                                   # pragma: no cover - the driver is
        pytest.skip(f"the driver does not import here: {e!r}")               # written in parallel
    grid, pairs = D.checked_grid({"coil": C})
    assert len(grid) == 2 * PLAN_ROWS and set(grid.family) == {"COIL"} and grid.eligible.all()
    assert set(grid.group) == {"COIL"}
    assert D.describe({"coil": C}, "coil", pairs[0][1]) == C.describe(pairs[0][1])


# ───────────────────────────── (b) the pieces, by hand ─────────────────────────────

def test_b_the_stop_is_the_opposite_edge_clamped_to_0_75_3_atr():
    close = np.full(8, 100.0)
    side = np.array([1, 1, 1, -1, -1, -1, 1, 1])
    hi = np.array([100.0, 100.0, 100.0, 100.5, 102.0, 105.0, 100.0, 100.0])
    lo = np.array([99.5, 98.0, 95.0, 99.0, 99.0, 99.0, 95.0, 95.0])
    atr = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, NAN])
    d = C.stop_distance(close, hi, lo, side, atr)
    # long: close - box low = 0.5 -> 0.75 (floor), 2.0, 5.0 -> 3.0 (cap); short: box high - close = 0.5 -> 0.75,
    # 2.0, 5.0 -> 3.0; ATR 2: 5.0 within [1.5, 6.0]; no ATR: none
    assert np.allclose(d[:7], [0.75, 2.0, 3.0, 0.75, 2.0, 3.0, 5.0]) and np.isnan(d[7])


def loop_trail(c, atr, e, d, mult=3.0, first=None, ratchet=False, atr_fixed=None):
    """A plain bar loop of X-TR (and, with ``first`` / ``ratchet`` / ``atr_fixed``, the readings not taken)."""
    ext, lvl = first, None
    for b in range(e + 1, len(c)):
        ext = c[b] if ext is None else (max(ext, c[b]) if d == 1 else min(ext, c[b]))
        a = atr[b] if atr_fixed is None else atr_fixed
        if not np.isfinite(a):
            continue
        L = ext - mult * a if d == 1 else ext + mult * a
        if ratchet and lvl is not None:
            L = max(L, lvl) if d == 1 else min(L, lvl)
        lvl = L
        if (d == 1 and c[b] < L) or (d == -1 and c[b] > L):
            return b
    return -1


def test_b_the_trail_by_hand():
    one = np.ones(6)
    # a long from bar 0: closes 101, 103, 104 after it, then 100.9 < 104 - 3 x 1: out at the close of bar 4
    assert list(C.trail_exits([100.0, 101.0, 103.0, 104.0, 100.9, 99.0], one, [0], [1])) == [4]
    # strict: a close of exactly 104 - 3 is not below it
    assert list(C.trail_exits([100.0, 101.0, 103.0, 104.0, 101.0, 101.0], one, [0], [1])) == [-1]
    # a short mirrors it: the lowest close 96 + 3 = 99 < 99.1 (out at bar 4); 99.0 is not above 99
    assert list(C.trail_exits([100.0, 99.0, 97.0, 96.0, 99.1, 99.1], one, [0], [-1])) == [4]
    assert list(C.trail_exits([100.0, 99.0, 97.0, 96.0, 99.0, 99.0], one, [0], [-1])) == [-1]
    # reading 1: the breakout close (bar 0, 100.0) is not a close "since the entry". The closes after it start at
    # 98.4; the trail level is then 98.4 - 1.5 = 96.9 and the first exit is bar 4 (98.3 < 99.9 - 1.5). Counting the
    # breakout close would have exited at bar 1 (98.4 < 100 - 1.5)
    c = [100.0, 98.4, 98.0, 99.9, 98.3]
    a = [1.0, 0.5, 0.5, 0.5, 0.5]
    assert list(C.trail_exits(c, a, [0], [1])) == [4]
    assert loop_trail(np.asarray(c), np.asarray(a), 0, 1, first=100.0) == 1
    # reading 2: each bar's own ATR, no ratchet. Bar 2's level is 102 - 3 x 0.2 = 101.4; bar 4's ATR is 1.0, so its
    # level is 102 - 3 = 99 and 101.3 does not exit. A ratchet (101.4) or the breakout bar's ATR (0.2) would
    c = np.asarray([100.0, 101.0, 102.0, 101.5, 101.3])
    a = np.asarray([0.2, 1.0, 0.2, 0.2, 1.0])
    assert list(C.trail_exits(c, a, [0], [1])) == [-1]
    assert loop_trail(c, a, 0, 1, ratchet=True) == 4 and loop_trail(c, a, 0, 1, atr_fixed=0.2) == 4
    # a NaN ATR decides nothing; the trail of an entry on the last bar has no bar to exit at
    assert list(C.trail_exits([100.0, 104.0, 90.0, 90.0], [1.0, 1.0, NAN, 1.0], [0, 3], [1, 1])) == [3, -1]
    with pytest.raises(ValueError):
        C.trail_exits([1.0, 2.0], [1.0, 1.0], [0], [0])


def test_b_the_trail_equals_a_plain_loop_on_random_series():
    rng = np.random.default_rng(4)
    for n in (5, 300, 4000):
        c = 1000.0 + np.cumsum(rng.normal(0.0, 1.0, n))
        a = np.abs(rng.normal(1.5, 0.5, n))
        a[: min(13, n)] = NAN                                           # an ATR warm-up
        bar = np.sort(rng.choice(n, size=min(n, 60), replace=False))
        side = rng.choice([-1, 1], size=len(bar))
        got = C.trail_exits(c, a, bar, side)
        want = [loop_trail(c, a, int(e), int(d)) for e, d in zip(bar, side)]
        assert list(got) == want
        assert ((got == -1) | (got > bar)).all()
        for mult in (0.5, 6.0):
            assert list(C.trail_exits(c, a, bar, side, mult)) == [loop_trail(c, a, int(e), int(d), mult)
                                                                 for e, d in zip(bar, side)]


def test_b_grades_by_hand_inclusive_and_the_volume_average_includes_the_bar():
    n = 23
    h, l, atr = np.full(n, 101.0), np.full(n, 100.0), np.ones(n)
    h[20], h[21], h[22] = 101.5, 101.49, 102.0                         # ranges 1.5 (= 1.5 ATR), 1.49, 2.0
    vol = np.full(n, 10.0)
    vol[20], vol[21], vol[22] = 15.2, 16.0, 10.0
    adx = np.full(n, 25.0)
    adx[20], adx[21], adx[22] = 20.0, 19.999, NAN
    g = C.grade_masks(h, l, atr, vol, adx)
    assert set(g) == set(GRADES) and g["none"].all()
    assert list(g["BIG"][20:]) == [True, False, True]                  # "at least 1.5 ATR": inclusive
    # bar 20: SMA(20) of bars 1-20 = (19 x 10 + 15.2) / 20 = 10.26 -> 1.5 x 10.26 = 15.39 > 15.2: no VOL (an average
    # of the 20 bars BEFORE it, 10, would pass it); bar 21: (18 x 10 + 15.2 + 16) / 20 = 10.56 -> 15.84 <= 16: VOL
    assert list(g["VOL"][20:]) == [False, True, False]
    assert not g["VOL"][:19].any()                                     # the SMA's warm-up (bars 0-18) fails
    prior = np.concatenate(([NAN], I.sma(vol, 20)[:-1]))
    assert vol[20] >= 1.5 * prior[20]                                  # the reading not taken would pass bar 20
    assert list(g["ADX"][20:]) == [True, False, False]                 # ADX >= 20; NaN fails
    assert np.array_equal(g["ALL3"], g["BIG"] & g["VOL"] & g["ADX"]) and list(g["ALL3"][20:]) == [False, False, False]


def test_b_coil_ordinals_count_coils_by_their_armed_runs():
    armed = np.array([0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1], bool)
    hi = np.where(armed, 10.0, NAN)
    lo = np.where(armed, 9.0, NAN)
    hi[10], lo[10] = 11.0, 9.5                                         # another box on the next bar: another coil
    assert list(C.coil_ids(armed, hi, lo)) == [-1, 0, 0, -1, 1, 1, 1, -1, -1, 2, 3]


# ───────────────────────────── (c) hand-made bars and an injected coil ─────────────────────────────

def flat(k, p=100.0):
    o = np.full(k, p)
    return o, o + 0.02, o - 0.02, o.copy()


def level(bars, a, z, p):
    """Minutes [a, z) at price p (open = close = p, high p + 0.02, low p - 0.02)."""
    o, h, l, c = bars
    o[a:z], c[a:z], h[a:z], l[a:z] = p, p, p + 0.02, p - 0.02


def market(bars, sp=0.2, symbol="XAUUSDm", n=None):
    """Continuous M1 bars from T0 (1H bar b holds minutes 60b .. 60b + 59; a decision at its close fills at minute
    60(b + 1)); XAUUSDm makes $1 per $1 of price on 0.01 lot; ``n`` the M1 tick counts (the tick volume)."""
    o, h, l, c = (np.asarray(x, np.float64) for x in bars)
    k = len(o)
    return M.TMarket2(symbol, {"t": T0 + 60 * np.arange(k, dtype=np.int64), "o": o, "h": h, "l": l, "c": c,
                               "spread_mean": np.full(k, float(sp)),
                               "n": np.ones(k) if n is None else np.asarray(n, np.float64)})


def fake_coil(nbars, events, adx=30.0):
    """A coil output with the port's keys: per event {bar: (side, box_hi, box_lo)} a coil armed at its breakout bar
    with that box and the breakout there; ``adx`` a scalar or per bar."""
    out = {"squeeze_on": np.zeros(nbars, bool), "run_len": np.zeros(nbars, np.int64), "armed": np.zeros(nbars, bool),
           "box_hi": np.full(nbars, NAN), "box_lo": np.full(nbars, NAN), "breakout": np.zeros(nbars, np.int8),
           "bo_box_hi": np.full(nbars, NAN), "bo_box_lo": np.full(nbars, NAN),
           "adx": np.broadcast_to(np.asarray(adx, np.float64), (nbars,)).copy()}
    for b, (side, hi, lo) in events.items():
        out["armed"][b], out["box_hi"][b], out["box_lo"][b] = True, hi, lo
        out["breakout"][b], out["bo_box_hi"][b], out["bo_box_lo"][b] = side, hi, lo
    return {k: out[k] for k in CI.KEYS}


def hand_ctx(mk, events, tf="1H", atr=1.0, trend=None, f1=None, adx=30.0):
    """A Context whose coil, ATR(14), ribbon trend (default +1 everywhere) and F1 (optional) are injected."""
    ctx = M.Context(mk)
    n = len(ctx.bars(tf))
    co = fake_coil(n, events, adx)
    assert ctx.get(C.MODULE, tf, C.COIL_PARAMS, lambda: co) is co
    a = np.broadcast_to(np.asarray(atr, np.float64), (n,)).copy()
    assert ctx.get("atr", tf, {"n": 14}, lambda: a) is a and ctx.atr(tf) is a
    tr = np.ones(n) if trend is None else np.asarray(trend, np.float64)
    assert ctx.get("ribbon_trend", tf, {}, lambda: tr) is tr and F.ribbon_trend(ctx, tf) is tr
    if f1 is not None:
        pair = tuple(np.asarray(x, bool) for x in f1)
        assert ctx.get("filter", tf, {"name": "F1"}, lambda: pair) is pair and ctx.allow(tf, "F1") is pair
    return ctx


def run(mk, ex, cost=1.0):
    return M.run_exec(mk, ex, T0, int(mk.t[-1]) + 60, cost)


def rows(r):
    tr = r.trades
    return [(int(a), int(b), int(c), round(float(d), 9), round(float(e), 9), str(f))
            for a, b, c, d, e, f in zip(tr.side, tr.entry_ix, tr.exit_ix, tr.entry, tr.exit, tr.reason)]


def no_drops(r):
    return r.counts["dropped_stop"] == 0 and r.counts["dropped_target"] == 0


def long_bars(k=720):
    """1H bars 0-2 at 100 (bar 2 is the breakout bar); bar 3 opens at 100 and closes at 101, bars 4 and 5 close at 103
    and 104, bars 6 on close at 100.9: with ATR 1 the trail (104 - 3 = 101) exits a long at bar 6's close."""
    bars = flat(k)
    level(bars, 181, 240, 101.0)
    level(bars, 240, 300, 103.0)
    level(bars, 300, 360, 104.0)
    level(bars, 360, k, 100.9)
    return bars


LONG = {2: (1, 99.9, 99.1)}            # a long breakout at bar 2's close 100: raw stop 100 - 99.1 = 0.9 (ATR 1)


def test_c_x_tr_enters_at_the_next_m1_open_and_exits_at_the_trail_close():
    mk = market(long_bars())
    ctx = hand_ctx(mk, LONG)
    v = V("XAUUSDm|1H|COIL|COIL-0|X-TR|none")
    ex = C.build(v, ctx)
    assert ex.kind == "events" and ex.label == v.id and len(ex.legs) == 1 and ex.orders is None
    assert ex.exit_long is None and ex.exit_short is None and ex.tighten_long is None and ex.tighten_short is None
    E = ex.entries
    assert list(E.bar) == [2] and list(E.side) == [1] and list(E.tag) == [0] and list(E.exit_bar) == [6]
    assert np.allclose(E.stop_dist, 0.9) and np.isnan(E.stop_level).all() and np.isnan(E.target_r).all()
    assert np.isnan(E.target_level).all() and np.isnan(E.be_r).all()
    r = run(mk, ex)
    # bought at the ask of minute 180 (100.0 + 0.2); the trail's exit decided at bar 6's close (100.9 < 104 - 3),
    # filled at the bid of minute 420; the stop (100.2 - 0.9 = 99.3) is never reached
    assert rows(r) == [(1, 180, 420, 100.2, 100.9, "signal")]
    assert np.allclose(r.trades.risk, 0.9) and list(r.trades.tag) == [0] and list(r.trades.bar) == [2]
    assert r.counts["candidates"] == r.counts["taken"] == 1 and r.counts["busy"] == 0 and no_drops(r)


def test_c_x_3r_takes_3r_from_the_fill_inside_an_m1_bar():
    bars = long_bars()
    bars[1][200] = 103.2                                    # minute 200's high passes 100.2 + 3 x 0.9 = 102.9
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    ex = C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-3R|none"), ctx)
    assert np.allclose(ex.entries.target_r, 3.0) and list(ex.entries.exit_bar) == [6]
    assert rows(run(mk, ex)) == [(1, 180, 200, 100.2, 102.9, "target")]
    # X-TR on the same bars ignores the wick: the trail reads closes
    assert rows(run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-TR|none"), ctx))) == \
        [(1, 180, 420, 100.2, 100.9, "signal")]


def test_c_the_stop_is_checked_inside_every_m1_bar_and_wins_over_the_target():
    bars = long_bars()
    bars[2][200] = 99.25                                    # minute 200's low reaches the stop 99.3
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    r = run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx))
    # filled at the stop level, one extra spread charged (99.3 - 0.2); the rule then waits for the next breakout
    assert rows(r) == [(1, 180, 200, 100.2, 99.1, "stop")] and r.trades.slippage.iloc[0] == pytest.approx(0.2)
    bars[1][200] = 103.2                                    # the same M1 bar also touches the 3R target: the stop wins
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    assert rows(run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-3R|none"), ctx))) == \
        [(1, 180, 200, 100.2, 99.1, "stop")]
    bars = long_bars()
    level(bars, 200, 201, 99.0)                             # a gap through the stop fills at the open, less a spread
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    assert rows(run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx))) == \
        [(1, 180, 200, 100.2, 98.8, "gap stop")]


def test_c_shorts_mirror_the_stop_the_trail_and_the_target():
    bars = flat(720)
    level(bars, 181, 240, 99.0)
    level(bars, 240, 300, 97.0)
    level(bars, 300, 360, 96.0)
    level(bars, 360, 720, 99.1)
    mk = market(bars)
    short = {2: (-1, 100.9, 100.1)}                         # raw stop: box high 100.9 - close 100 = 0.9
    ctx = hand_ctx(mk, short, trend=-np.ones(12))
    ex = C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-TR|none"), ctx)
    assert list(ex.entries.side) == [-1] and np.allclose(ex.entries.stop_dist, 0.9) and list(ex.entries.exit_bar) == [6]
    # sold at the bid (100.0); the lowest close since the entry is 96, and 99.1 > 96 + 3 at bar 6: bought back at
    # the ask of minute 420 (99.1 + 0.2); the stop 100.9 is never reached by the ask
    assert rows(run(mk, ex)) == [(-1, 180, 420, 100.0, 99.3, "signal")]
    bars[2][200] = 97.0                                     # the ask low (97.2) passes 100.0 - 3 x 0.9 = 97.3
    mk = market(bars)
    ctx = hand_ctx(mk, short, trend=-np.ones(12))
    assert rows(run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-3R|none"), ctx))) == \
        [(-1, 180, 200, 100.0, 97.3, "target")]


def test_c_the_stop_distance_is_clamped_at_the_breakout_close():
    mk = market(flat(720))
    ev = {2: (1, 99.9, 99.5), 5: (1, 99.9, 98.0), 8: (-1, 105.0, 100.1)}   # raw 0.5, 2.0 and 5.0
    ctx = hand_ctx(mk, ev, atr=np.array([1.0] * 8 + [2.0] * 4))
    E = C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx).entries
    # 0.5 -> 0.75 x ATR 1 (the floor); 2.0 stays; 5.0 with ATR 2 lies inside [1.5, 6]
    assert list(E.bar) == [2, 5, 8] and np.allclose(E.stop_dist, [0.75, 2.0, 5.0])
    ctx = hand_ctx(mk, ev, atr=1.0)
    assert np.allclose(C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx).entries.stop_dist, [0.75, 2.0, 3.0])


def test_c_the_stop_and_the_target_are_set_from_the_actual_fill_at_both_costs():
    bars = long_bars()
    bars[2][200] = 99.35                                    # x1.0's stop (99.3) holds, x1.5's (100.3 - 0.9) is hit
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    ex = C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx)
    r1, r15 = run(mk, ex), run(mk, ex, 1.5)
    assert rows(r1) == [(1, 180, 420, 100.2, 100.9, "signal")]
    assert rows(r15) == [(1, 180, 200, 100.3, 99.1, "stop")]                # 99.4 less 1.5 spreads (0.3)
    assert np.allclose(r1.trades.risk, 0.9) and np.allclose(r15.trades.risk, 0.9) and no_drops(r1) and no_drops(r15)
    bars = long_bars()
    bars[1][210] = 102.95                                   # reaches x1.0's target 102.9, not x1.5's 103.0
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    ex = C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-3R|none"), ctx)
    assert rows(run(mk, ex)) == [(1, 180, 210, 100.2, 102.9, "target")]
    assert rows(run(mk, ex, 1.5)) == [(1, 180, 240, 100.3, 103.0, "target")]   # bar 4's high (103.02) reaches it


def test_c_a_fill_through_the_box_is_taken_with_the_stop_from_the_fill_nothing_is_dropped():
    bars = flat(720)
    level(bars, 180, 720, 98.5)                             # the open after the breakout close gaps below the box
    mk = market(bars)
    ctx = hand_ctx(mk, LONG)
    r = run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx))
    # filled at 98.7, below the box low 99.1 (and below close - stop = 99.1): the stop is 98.7 - 0.9 = 97.8
    assert rows(r) == [(1, 180, 719, 98.7, 98.5, "end")] and np.allclose(r.trades.risk, 0.9) and no_drops(r)
    # an absolute level at the box edge would be dropped by PREREG 4's rule (the reading the plan does not make)
    ra = run(mk, M.event_exec("1H", entries=M.entries([2], [1], stop_level=99.1)))
    assert rows(ra) == [] and ra.counts["dropped_stop"] == 1


def test_c_one_position_at_a_time_a_breakout_while_a_trade_is_open_is_skipped():
    mk = market(long_bars(960))
    ev = {2: (1, 99.9, 99.1), 4: (-1, 106.0, 103.5), 8: (1, 100.5, 99.5)}
    ctx = hand_ctx(mk, ev)
    r = run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx))
    # the short of bar 4 comes while the long is open: skipped (no reversal, the long keeps its trail); the long of
    # bar 8 fills at minute 540 (100.9 + 0.2) and runs to the end (no close after it falls 3 ATR)
    assert rows(r) == [(1, 180, 420, 100.2, 100.9, "signal"), (1, 540, 959, 101.1, 100.9, "end")]
    assert list(r.trades.tag) == [0, 2] and list(r.trades.bar) == [2, 8]
    assert r.counts["candidates"] == 3 and r.counts["taken"] == 2 and r.counts["busy"] == 1 and no_drops(r)


def test_c_a_breakout_at_the_trails_exit_bar_fills_at_the_same_open():
    mk = market(long_bars())
    ctx = hand_ctx(mk, {2: (1, 99.9, 99.1), 6: (-1, 101.5, 101.0)})
    r = run(mk, C.build(V("XAUUSDm|1H|COIL|COIL-0|X-TR|none"), ctx))
    assert rows(r) == [(1, 180, 420, 100.2, 100.9, "signal"), (-1, 420, 719, 100.9, 101.1, "end")]
    assert r.counts["busy"] == 0 and list(r.trades.tag) == [0, 1]


# ───────────────────────────── (d) trend filters ─────────────────────────────

FOUR = {2: (1, 99.9, 99.1), 5: (-1, 100.9, 100.1), 8: (1, 99.9, 99.1), 11: (-1, 100.9, 100.1)}


def test_d_the_trend_filter_is_read_at_the_breakout_close():
    mk = market(flat(960))
    trend = np.ones(16)
    trend[5], trend[8], trend[11] = 1.0, 0.0, -1.0          # bar 5 up (a short refused), 8 none yet, 11 down
    al, ash = np.zeros(16, bool), np.zeros(16, bool)
    al[8], ash[5] = True, True                              # F1: the long of bar 8 and the short of bar 5 only
    ctx = hand_ctx(mk, FOUR, trend=trend, f1=(al, ash))
    want = {"COIL-RIB": [2, 11], "COIL-MA": [5, 8], "COIL-0": [2, 5, 8, 11]}
    for rule, bars_ in want.items():
        E = C.build(V(f"XAUUSDm|1H|COIL|{rule}|X-TR|none"), ctx).entries
        assert list(E.bar) == bars_, rule
        assert list(E.tag) == [{2: 0, 5: 1, 8: 2, 11: 3}[b] for b in bars_]
    for g in GRADES[1:]:                                    # the graded COIL-RIB rows start from the same gate
        assert set(C.build(V(f"XAUUSDm|1H|COIL|COIL-RIB|X-3R|{g}"), ctx).entries.bar) <= {2, 11}


def test_d_a_filter_never_closes_an_open_trade():
    mk = market(long_bars())
    trend = -np.ones(12)
    trend[2] = 1.0                                          # up at the breakout, down from the next bar on
    al, ash = np.zeros(12, bool), np.zeros(12, bool)
    al[2] = True                                            # F1 allows the long at bar 2 only
    ctx = hand_ctx(mk, LONG, trend=trend, f1=(al, ash))
    want = [(1, 180, 420, 100.2, 100.9, "signal")]
    for rule in ("COIL-RIB", "COIL-MA", "COIL-0"):
        ex = C.build(V(f"XAUUSDm|1H|COIL|{rule}|X-TR|none"), ctx)
        assert ex.exit_long is None and ex.exit_short is None and rows(run(mk, ex)) == want, rule


def test_d_each_row_asks_exactly_its_filter_and_only_vol_reads_the_volume(monkeypatch):
    mk = market(flat(720))
    asked = []
    real_ribbon = F.ribbon_trend
    monkeypatch.setattr(F, "ribbon_trend", lambda ctx, tf: asked.append(("ribbon", tf)) or real_ribbon(ctx, tf))
    for v in C.variants("XAUUSDm"):
        ctx = M.Context(mk)
        n = len(ctx.bars(v.tf))
        ctx.get(C.MODULE, v.tf, C.COIL_PARAMS, lambda: fake_coil(n, {}))
        ctx.get("ribbon_trend", v.tf, {}, lambda: np.ones(n))
        real_allow, real_volume = ctx.allow, ctx.volume
        ctx.allow = lambda tf, name, _a=real_allow: asked.append((tf, name)) or _a(tf, name)
        ctx.volume = lambda tf, source="auto", _v=real_volume: asked.append(("volume", tf)) or _v(tf, source)
        asked.clear()
        C.build(v, ctx)
        p = v.params
        want = {"COIL-RIB": [("ribbon", v.tf)], "COIL-MA": [(v.tf, "F1")], "COIL-0": [(v.tf, "F0")]}[p["rule"]]
        if p["grade"] in ("VOL", "ALL3"):
            want = want + [("volume", v.tf)]
        assert asked == want, (v.id, asked)


# ───────────────────────────── (e) grades at the breakout bar ─────────────────────────────

def test_e_the_grades_read_the_breakout_bars_range_volume_and_adx():
    """30 hours at 100 (tick volume 60 an hour; ATR 1). Breakouts at bars 12, 22, 25 and 28. Bar 12 opens 2 above
    bar 11's close (98): its range is 0.04 but its true range 2.02, so it is no BIG bar (the range decides, reading 4);
    the volume SMA does not exist yet (no VOL); ADX 30. Bar 22 ranges 1.62 (BIG), has 120 ticks against an SMA(20) of
    (19 x 60 + 120) / 20 = 63 (VOL: 120 >= 94.5) and ADX 25; bar 25 ranges 1.2 (no BIG), 120 ticks against (18 x 60
    + 2 x 120) / 20 = 66 (VOL: 120 >= 99) and ADX 19.5 (no); bar 28 ranges 2.02 (BIG), 60 ticks against 66 (no VOL)
    and ADX 40."""
    bars = flat(1800)
    level(bars, 11 * 60, 12 * 60, 98.0)
    n = np.ones(1800)
    for b in (22, 25):
        n[60 * b: 60 * b + 60] = 2.0
    bars[1][22 * 60 + 30] = 101.6
    bars[1][25 * 60 + 30] = 101.18
    bars[1][28 * 60 + 30] = 102.0
    mk = market(bars, n=n)
    adx = np.full(30, 30.0)
    adx[22], adx[25], adx[28] = 25.0, 19.5, 40.0
    ev = {12: (1, 99.9, 99.1), 22: (1, 99.9, 99.1), 25: (1, 99.9, 99.1), 28: (1, 99.9, 99.1)}
    ctx = hand_ctx(mk, ev, adx=adx)
    b = ctx.bars("1H")
    k = [12, 22, 25, 28]
    assert np.allclose(b.vol[[21] + k[1:]], [60, 120, 120, 60])
    assert np.allclose(b.h[k] - b.l[k], [0.04, 1.62, 1.2, 2.02]) and b.c[11] == 98.0 and b.h[12] - b.c[11] >= 1.5
    want = {"none": [12, 22, 25, 28], "BIG": [22, 28], "VOL": [22, 25], "ADX": [12, 22, 28], "ALL3": [22]}
    for g, bars_ in want.items():
        for ex_ in ("X-TR", "X-3R"):
            assert list(C.build(V(f"XAUUSDm|1H|COIL|COIL-RIB|{ex_}|{g}"), ctx).entries.bar) == bars_, (g, ex_)
    # a grade refuses a breakout; it never makes a later close of the same coil an entry (the port has one
    # breakout per coil, and the rule's entries are exactly the port's breakout bars that pass)
    assert set(C.build(V("XAUUSDm|1H|COIL|COIL-RIB|X-TR|ALL3"), ctx).entries.tag) == {1}


def test_e_btc_vol_reads_the_binance_volume_not_the_tick_volume():
    mk = market(flat(1800, 9000.0), sp=10.0, symbol="BTCUSDm", n=np.ones(1800))
    ctx = hand_ctx(mk, {22: (1, 8999.0, 8990.0), 25: (1, 8999.0, 8990.0)})
    nb = len(ctx.bars("1H"))
    vol = np.full(nb, 100.0)
    vol[25] = 400.0                                          # Binance: bar 25 surges, bar 22 does not
    ctx.get("volume", "1H", {"source": "binance"}, lambda: (vol, np.zeros(nb, np.int64)))
    assert ctx.volume("1H") is vol and np.allclose(ctx.bars("1H").vol, 60.0)       # the tick volume is flat
    assert list(C.build(V("BTCUSDm|1H|COIL|COIL-RIB|X-TR|VOL"), ctx).entries.bar) == [25]
    assert list(C.build(V("BTCUSDm|1H|COIL|COIL-RIB|X-TR|none"), ctx).entries.bar) == [22, 25]


# ───────────────────────────── (f) the real port on a synthetic market ─────────────────────────────

def coil_like(days=540, seed=17, start="2018-01-01"):
    """Around the clock: an hourly level that rests (8 to 900 hours, a tiny drift: the squeezes) and moves (2 to 30
    hours: a drift, a trend, a shock then a drift, or a fake-out the other way first), interpolated inside each hour,
    with M1 noise around it; tick counts that surge in some moves. Coils and breakouts occur on 1H, 4H and 1D, and
    every gate of the rule both keeps and refuses some of them."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    hours = days * 24
    lvl, noise, surge = np.zeros(hours), np.ones(hours), np.ones(hours)
    p, h = 1300.0, 0
    while h < hours:
        rest = int(rng.choice([rng.integers(8, 60), rng.integers(60, 200), rng.integers(200, 900)], p=[0.6, 0.3, 0.1]))
        s = rng.uniform(0.6, 1.4)
        for _ in range(rest):
            if h >= hours:
                break
            p += rng.normal(0.0, 0.05)
            lvl[h], noise[h] = p, s
            h += 1
        d = rng.choice([-1.0, 1.0])
        kind = int(rng.integers(0, 4))
        burst = int(rng.integers(2, 30))
        vs = rng.choice([1.0, 3.0])
        for q in range(burst):
            if h >= hours:
                break
            if kind == 0:
                step = rng.uniform(0.1, 0.6)
            elif kind == 1:
                step = rng.uniform(0.5, 2.0)
            elif kind == 2:
                step = rng.uniform(6, 25) if q == 0 else rng.uniform(0.2, 1.0)
            else:
                step = -rng.uniform(0.3, 0.8) if q < 6 else rng.uniform(0.6, 2.5)
            p += d * step + rng.normal(0.0, 0.5 * s)
            lvl[h], noise[h], surge[h] = p, s * (1.0 + 0.5 * (kind == 2) * (q == 0)), vs
            h += 1
    L = np.interp(np.arange(n) / 60.0, np.arange(hours) + 1.0, lvl)
    c = L + rng.normal(0.0, 1.0, n) * np.repeat(noise, 60)[:n]
    o = np.concatenate(([c[0]], c[:-1])) + rng.normal(0.0, 0.05, n)
    hi = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.2, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.2, n))
    ticks = np.round(rng.uniform(5, 30, n) * np.repeat(surge, 60)[:n])
    return {"t": t, "o": o, "h": hi, "l": lo, "c": c, "spread_mean": np.full(n, 0.2), "n": ticks}


SYNTH_FROM = "2019-01-01"               # gold is never scored before 2019 while the Early window is closed


@pytest.fixture(scope="module")
def synth():
    """The synthetic market's Context and its M1 arrays (``truncated`` cuts them)."""
    m1 = coil_like()
    return M.Context(M.TMarket2("XAUUSDm", m1)), m1


def truncated(m1, cut_s):
    """The same market with every M1 bar at or after ``cut_s`` removed."""
    keep = m1["t"] < cut_s
    return M.Context(M.TMarket2("XAUUSDm", {k: v[keep] for k, v in m1.items()}))


def test_f_coil_0s_entries_are_the_ports_breakouts_with_the_stop_and_trail_by_hand(synth):
    ctx = synth[0]
    for tf in TFS:
        b = ctx.bars(tf)
        co = CI.coil(b.o, b.h, b.l, b.c)                            # the port, called afresh
        k = np.flatnonzero(co["breakout"] != 0)
        assert len(k) >= (5 if tf == "1D" else 25), tf
        d = co["breakout"][k].astype(np.int64)
        atr = M.atr14(b)
        raw = np.where(d == 1, b.c[k] - co["bo_box_lo"][k], co["bo_box_hi"][k] - b.c[k])
        stop = np.minimum(np.maximum(raw, 0.75 * atr[k]), 3.0 * atr[k])
        for ex_ in ("X-TR", "X-3R"):
            E = C.build(V(f"XAUUSDm|{tf}|COIL|COIL-RIB|{ex_}|none"), ctx).entries
            assert set(E.bar) <= set(k)
        E = C.build(V(f"XAUUSDm|{tf}|COIL|COIL-0|X-TR|none"), ctx).entries
        assert np.array_equal(E.bar, k) and np.array_equal(E.side, d) and np.array_equal(E.stop_dist, stop)
        assert ((E.stop_dist >= 0.75 * atr[k] - 1e-12) & (E.stop_dist <= 3.0 * atr[k] + 1e-12)).all()
        assert list(E.exit_bar) == [loop_trail(b.c, atr, int(e), int(s)) for e, s in zip(k, d)]
        assert len(set(E.tag)) == len(k) and (np.diff(E.tag) > 0).all()            # one breakout per coil
        armed = co["armed"]
        starts = np.flatnonzero(armed & ~np.concatenate(([False], armed[:-1])))
        assert np.array_equal(E.tag, np.searchsorted(starts, k, side="right") - 1)  # the coil's ordinal
        assert np.isnan(E.target_r).all()


def gates_by_hand(ctx, tf):
    """Per rule its (allow_long, allow_short) and per grade its mask, from the real indicators: the same timeframe's
    ribbon trend, F1, and the grades on the bars' range, ATR(14), tick volume and the port's ADX (called afresh)."""
    b = ctx.bars(tf)
    trend = F.ribbon_trend(ctx, tf)
    ma = I.sma(b.c, 200)                                          # F1: the close against SMA(close, 200)
    with np.errstate(invalid="ignore"):
        f1 = (b.c > ma, b.c < ma)
    rules = {"COIL-RIB": (trend == 1.0, trend == -1.0), "COIL-MA": f1,
             "COIL-0": (np.ones(len(b), bool), np.ones(len(b), bool))}
    return rules, C.grade_masks(b.h, b.l, M.atr14(b), b.vol, CI.coil(b.o, b.h, b.l, b.c)["adx"])


def test_f_every_gate_keeps_exactly_the_breakouts_it_allows(synth):
    ctx = synth[0]
    kept = {}
    by_tf = {tf: gates_by_hand(ctx, tf) for tf in TFS}
    for v in C.variants("XAUUSDm"):
        p = v.params
        E0 = C.build(V(f"XAUUSDm|{v.tf}|COIL|COIL-0|X-TR|none"), ctx).entries
        E = C.build(v, ctx).entries
        (al, ash), g = by_tf[v.tf][0][p["rule"]], by_tf[v.tf][1][p["grade"]]
        keep = np.where(E0.side == 1, al[E0.bar], ash[E0.bar]) & g[E0.bar]
        for f in ("bar", "side", "stop_dist", "exit_bar", "tag"):
            assert np.array_equal(getattr(E, f), getattr(E0, f)[keep]), (v.id, f)
        assert np.isnan(E.target_r).all() if p["exit"] == "X-TR" else np.allclose(E.target_r, 3.0)
        key = p["rule"] if p["grade"] == "none" else p["grade"]
        if p["exit"] == "X-TR":
            got = kept.setdefault(key, [0, 0])
            got[0] += int(keep.sum())
            got[1] += int((~keep).sum())
    # on this market every gate keeps some breakouts and refuses others (over the three timeframes)
    assert kept["COIL-0"][1] == 0 and kept["COIL-0"][0] > 50
    for key in ("COIL-RIB", "COIL-MA", "BIG", "VOL", "ADX", "ALL3"):
        assert kept[key][0] > 0 and kept[key][1] > 0, (key, kept[key])


def test_f_one_trade_per_coil_also_when_its_breakout_is_refused(synth):
    """A refused breakout spends its coil (reading 7): the later closes beyond the same box, inside what was left of
    its 12 armed bars, are no entries of any row."""
    ctx = synth[0]
    later = 0
    for tf in TFS:
        b = ctx.bars(tf)
        co = C.coil_of(ctx, tf)
        ids = C.coil_ids(co["armed"], co["box_hi"], co["box_lo"])
        k = np.flatnonzero(co["breakout"] != 0)
        entry_bars = {v.id: set(C.build(v, ctx).entries.bar.tolist()) for v in C.variants("XAUUSDm") if v.tf == tf}
        for e in k:
            first = int(np.flatnonzero(ids == ids[e])[0])          # the coil's first armed bar
            hi, lo = co["bo_box_hi"][e], co["bo_box_lo"][e]
            after = [j for j in range(e + 1, min(first + 12, len(b))) if b.c[j] > hi or b.c[j] < lo]
            after = [j for j in after if co["breakout"][j] == 0]   # not another coil's breakout
            later += len(after)
            for bars_ in entry_bars.values():
                assert not (set(after) & bars_)
        for vid, bars_ in entry_bars.items():
            assert bars_ <= set(k.tolist()), vid
    assert later > 0                                              # such closes exist here


def test_f_warm_computes_everything_build_reads(synth):
    """The driver calls ``warm`` in the parent before it forks: afterwards building every row adds nothing to the
    Context's cache, so the workers share every array (copy-on-write)."""
    ctx = M.Context(M.TMarket2("XAUUSDm", synth[1]))
    C.warm(ctx, C.variants("XAUUSDm"))
    keys = set(ctx.cache)
    assert {(C.MODULE, "XAUUSDm", tf) for tf in TFS} <= {k[:3] for k in keys}
    for v in C.variants("XAUUSDm"):
        C.build(v, ctx)
    assert set(ctx.cache) == keys


@pytest.mark.parametrize("vid", ["XAUUSDm|1H|COIL|COIL-0|X-TR|none", "XAUUSDm|1H|COIL|COIL-RIB|X-3R|none",
                                 "XAUUSDm|4H|COIL|COIL-MA|X-TR|none", "XAUUSDm|4H|COIL|COIL-RIB|X-3R|VOL",
                                 "XAUUSDm|1D|COIL|COIL-0|X-TR|none"])
def test_f_the_harness_trades_where_the_rule_says(synth, vid):
    ctx = synth[0]
    v = V(vid)
    ex = C.build(v, ctx)
    E, b = ex.entries, ctx.bars(v.tf)
    for cost in (1.0, 1.5):
        r = M.run_exec(ctx.mk, ex, SYNTH_FROM, int(ctx.mk.t[-1]) + 60, cost)
        tr = r.trades
        inside = (b.tc[E.bar] > TM.s_of(SYNTH_FROM)) & (b.ex[E.bar] < r.iz)
        assert r.counts["candidates"] == int(inside.sum()) == r.counts["taken"] + r.counts["busy"]
        assert r.counts["taken"] == len(tr) > 0 and no_drops(r)
        pos = {int(x): i for i, x in enumerate(E.bar)}
        ix = np.asarray([pos[int(x)] for x in tr.bar], np.int64)                  # every trade is an entry
        assert np.array_equal(tr.side.to_numpy(), E.side[ix]) and np.array_equal(tr.tag.to_numpy(), E.tag[ix])
        assert len(set(tr.tag)) == len(tr)                                        # one trade per coil
        assert np.array_equal(tr.entry_ix.to_numpy(), b.ex[E.bar[ix]])            # the next M1 open
        assert (tr.entry_ix.to_numpy()[1:] >= tr.exit_ix.to_numpy()[:-1]).all()   # one at a time
        assert np.allclose(tr.risk.to_numpy(), E.stop_dist[ix], rtol=1e-12, atol=1e-12)    # 1R from the fill
        xb = E.exit_bar[ix]
        has = (xb >= 0) & (b.ex[np.maximum(xb, 0)] < r.iz)
        assert (tr.exit_ix.to_numpy()[has] <= b.ex[xb[has]]).all()                # out by the trail's fill at latest
        sig = (tr.reason == "signal").to_numpy()
        assert np.array_equal(tr.exit_ix.to_numpy()[sig], b.ex[xb[sig]])          # a signal exit is the trail's
        allowed = {"signal", "stop", "gap stop", "end"} | ({"target", "gap target"} if v.params["exit"] == "X-3R"
                                                           else set())
        assert set(tr.reason) <= allowed
        if v.tf == "1H":                                                         # the trail does exit trades
            assert sig.sum() > 0 and (r.counts["busy"] > 0 or v.params["rule"] != "COIL-0")


# ───────────────────────────── (g) causality ─────────────────────────────

ENTRY_FIELDS = ("bar", "side", "stop_level", "stop_dist", "target_level", "target_dist", "target_r", "be_r", "risk",
                "tag")
BIG_S = np.iinfo(np.int64).max


def decisions(ctx, v, upto_s):
    """Every decision a row takes at bars closing at or before ``upto_s``: its entries there, and for each of them the
    trail's exit if it is decided at or before ``upto_s`` (else -1: not decided yet)."""
    ex = C.build(v, ctx)
    b = ctx.bars(v.tf)
    E = ex.entries
    m = b.tc[E.bar] <= upto_s
    out = {k: getattr(E, k)[m] for k in ENTRY_FIELDS}
    xb = E.exit_bar[m]
    tcx = np.where(xb >= 0, b.tc[np.maximum(xb, 0)], BIG_S)
    out["exit_bar"] = np.where(tcx <= upto_s, xb, -1)
    assert ex.exit_long is None and ex.exit_short is None and len(ex.legs) == 1
    return out


def same_decisions(full, part, symbol, upto_s):
    for tf in TFS:
        bf, bp = full.bars(tf), part.bars(tf)
        k = int((bp.tc <= upto_s).sum())
        assert k > 0 and int((bf.tc <= upto_s).sum()) == k
        for f in ("t", "tc", "o", "h", "l", "c", "vol"):
            assert np.array_equal(getattr(bf, f)[:k], getattr(bp, f)[:k])
    n = 0
    for v in C.variants(symbol):
        a, b = decisions(full, v, upto_s), decisions(part, v, upto_s)
        assert a.keys() == b.keys()
        for key in a:
            assert np.array_equal(a[key], b[key], equal_nan=np.asarray(a[key]).dtype.kind == "f"), (v.id, key)
        n += 1
    return n


def cuts_at_breakouts(ctx, after):
    """Cut times that a one-bar look-ahead would trip on: the open of the first breakout bar after ``after`` on each
    timeframe, and the open of the bar after it (a trade just entered, its trail undecided)."""
    out = set()
    for tf in TFS:
        b = ctx.bars(tf)
        k = C.breakouts(ctx, tf)["bar"]
        k = k[b.t[k] > TM.s_of(after)]
        out.add(int(b.t[k[0]]))
        out.add(int(b.t[k[0] + 1]))
    return sorted(out)


def test_g_decisions_up_to_t_do_not_change_when_the_bars_after_t_are_removed(synth):
    full, m1 = synth
    cuts = [TM.s_of("2019-02-15")] + cuts_at_breakouts(full, "2018-11-01")
    assert len(cuts) >= 5
    for cut in cuts:
        assert same_decisions(full, truncated(m1, cut), "XAUUSDm", cut) == PLAN_ROWS


# ───────────────────────────── (h) real data (to 2019-07-01 only) ─────────────────────────────

@pytest.fixture(scope="module", params=SYMS)
def real(request, tmp_path_factory):
    """(symbol, its Context to 2019-07-01, load(end) -> a Context to an earlier end, not kept). Module-scoped and
    parametrized by symbol, so pytest runs every real-data test of one symbol before loading the next: memory holds
    one symbol at a time. Nothing at or after 2019-07-01 is read."""
    symbol = request.param
    if (2019, 1) not in store.available_months(symbol):
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    d2, d1 = tmp_path_factory.mktemp("closed_study2"), tmp_path_factory.mktemp("closed_study1")

    def load(end):
        assert TM.s_of(end) <= TM.s_of("2019-07-01")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(M, "STUDY_DIR", d2)
            mp.setattr(TM, "STUDY_DIR", d1)
            mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
            return M.Context(M.load(symbol, end=end))
    yield symbol, load("2019-07-01"), load


def test_h_real_bars_causality_every_breakout_has_a_stop_and_the_gates_act(real):
    symbol, full, load = real
    part = load("2019-04-01")
    assert full.mk.end_s == TM.s_of("2019-07-01") and part.mk.end_s == TM.s_of("2019-04-01")
    assert same_decisions(full, part, symbol, TM.s_of("2019-04-01")) == PLAN_ROWS
    del part
    b = full.bars("1H")                                         # cut right before a 1H breakout (its bar's open)
    k = C.breakouts(full, "1H")["bar"]
    cut = int(b.t[k[b.t[k] > TM.s_of("2019-05-01")][0]])
    part = load(str(TM.utc(cut).tz_localize(None)))
    assert same_decisions(full, part, symbol, cut) == PLAN_ROWS
    del part
    refused = {}
    for tf in TFS:
        T = C.breakouts(full, tf)
        assert len(T["bar"]) >= (3 if tf == "1D" else 30)
        assert np.isfinite(T["stop"]).all() and (T["stop"] > 0).all()                       # reading 9
        with np.errstate(invalid="ignore"):
            r = T["stop"] / T["atr"]
            assert ((r >= 0.75 - 1e-12) & (r <= 3.0 + 1e-12)).all()
        E0 = C.coil_entries(full, tf)
        assert np.array_equal(E0.bar, T["bar"]) and len(set(E0.tag)) == len(E0)          # every breakout, once
        tab = C.breakout_table(full, tf)
        assert len(tab) == len(T["bar"]) and (tab.stop_atr <= 3.0 + 1e-12).all()
        for key, col in (("ribbon", "ribbon_ok"), ("F1", "f1_ok"), ("BIG", "BIG"), ("VOL", "VOL"), ("ADX", "ADX")):
            got = refused.setdefault(key, [0, 0])
            got[0] += int(tab[col].sum())
            got[1] += int((~tab[col].astype(bool)).sum())
    for key, (kept, ref) in refused.items():
        assert kept > 0 and ref > 0, (symbol, key)
    if symbol == "BTCUSDm":                                         # PREREG 2: BTC's VOL reads Binance volume
        for tf in TFS:
            bb = full.bars(tf)
            bv, _ = M.binance_volume(full.mk, tf)
            atr = np.asarray(full.atr(tf))
            adx = C.coil_of(full, tf)["adx"]
            assert np.array_equal(C.grade_mask(full, tf, "VOL"), C.grade_masks(bb.h, bb.l, atr, bv, adx)["VOL"])
            assert not np.array_equal(C.grade_mask(full, tf, "VOL"), C.grade_masks(bb.h, bb.l, atr, bb.vol, adx)["VOL"])


SMOKE = ("{s}|1H|COIL|COIL-RIB|X-TR|none", "{s}|1H|COIL|COIL-RIB|X-3R|BIG", "{s}|4H|COIL|COIL-RIB|X-TR|VOL",
         "{s}|1H|COIL|COIL-RIB|X-3R|ADX", "{s}|1H|COIL|COIL-RIB|X-TR|ALL3", "{s}|1H|COIL|COIL-MA|X-TR|none",
         "{s}|4H|COIL|COIL-0|X-TR|none", "{s}|1D|COIL|COIL-0|X-TR|none")


def test_h_smoke_one_row_of_each_rule_type_runs_on_development_data(real, monkeypatch):
    """2019-01-01 to 2019-06-30 through ``run_variant`` (the dev window shortened to the data held): it runs, and its
    trades are where the rule says (counts, times, stop geometry). No profit or loss is looked at."""
    symbol, ctx, _ = real
    monkeypatch.setitem(M.WINDOWS, "dev", (None, "2019-07-01"))
    assert M.window_span("dev", symbol) == ("2019-01-01", "2019-07-01")
    C.warm(ctx, C.variants(symbol))
    a_s, z_s = TM.s_of("2019-01-01"), TM.s_of("2019-07-01")
    for pat in SMOKE:
        v = V(pat.format(s=symbol))
        ex = C.build(v, ctx)
        res = M.run_variant(ctx, v, ex, windows=("dev",), trades_windows=("dev",))
        assert len(res.rows) == 1
        row = res.rows[0]
        assert (row["vid"], row["window"], row["start"], row["end"]) == (v.id, "dev", "2019-01-01", "2019-07-01")
        assert row["eligible"] is True and row["family"] == "COIL" and row["script"] == "COIL"
        n = int(row["trades"])
        assert int(row["n_taken"]) == n and int(row["n_taken_x15"]) == int(row["trades_x15"])
        assert int(row["n_dropped_stop"]) == 0 and int(row["n_dropped_target"]) == 0
        b = ctx.bars(v.tf)
        E = ex.entries
        inside = (b.tc[E.bar] > a_s) & (b.tc[E.bar] <= z_s)
        assert int(row["n_candidates"]) <= int(inside.sum())
        assert int(row["n_candidates"]) == int(row["n_taken"]) + int(row["n_busy"])
        if v.params["grade"] == "none" and v.tf == "1H":
            assert n > 0, v.id
        tr = res.trades
        assert set(tr.cost) <= {1.0, 1.5} and (tr.vid == v.id).all()
        bar = tr.bar.to_numpy()
        entry_s = np.asarray([int(x.timestamp()) for x in tr.entry_time], np.int64)
        assert np.array_equal(entry_s, ctx.mk.t[b.ex[bar]])                  # filled at the next M1 open
        assert (b.tc[bar] > a_s).all()
        pos = {int(x): i for i, x in enumerate(E.bar)}
        ix = np.asarray([pos[int(x)] for x in bar], np.int64)                # every trade is one of the entries
        assert np.array_equal(tr.side.to_numpy(), E.side[ix]) and np.array_equal(tr.tag.to_numpy(), E.tag[ix])
        assert np.allclose(tr.risk.to_numpy(), E.stop_dist[ix], rtol=1e-9, atol=1e-9)   # the stop from the fill
        for cost in (1.0, 1.5):
            one = tr[tr.cost == cost]
            assert len(set(one.tag)) == len(one)                              # one trade per coil
            sig = one[one.reason == "signal"]
            xb = E.exit_bar[np.asarray([pos[int(x)] for x in sig.bar], np.int64)]
            exit_s = np.asarray([int(x.timestamp()) for x in sig.exit_time], np.int64)
            assert (xb >= 0).all() and np.array_equal(exit_s, ctx.mk.t[b.ex[xb]])   # the trail's close, next open
        allowed = {"signal", "stop", "gap stop", "end"} | ({"target", "gap target"} if v.params["exit"] == "X-3R"
                                                           else set())
        assert set(tr.reason) <= allowed
