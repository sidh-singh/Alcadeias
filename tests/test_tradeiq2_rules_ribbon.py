"""
Study 2's ribbon rules (``backtesting/research/tradeiq2_rules_ribbon.py``): the rows of PREREG 6.1 (RIB, ALMA-X,
RIB-LIT) and 6.10 (STK), their entries, exits, stops and filters, executed by ``tradeiq2_market``.

(a) The grid: the rows per symbol are the PREREG's numbers (written here from its text), with unique ids that carry
    the tokens the driver pairs rows by (XP / XBE -> X0, a filter -> F0, ALMA-X -> RIB x X0 x F0, the HA bases).
(b) Hand-made bars with an injected ribbon (the port's contract, set through the Context's cache, so every flip, stop
    and price is known by hand): a flip opens, the opposite flip exits and reverses (LS), LO, a stop then flat until
    the next flip, XT2, XP (two legs), XBE (break-even from the next M1 bar), RIB-LIT's literal stop, ALMA-X's own
    flips at the ALMA cross; the absolute-level rules of PREREG 4 (the stop from the ACTUAL fill, also at x1.5 and
    after a gap; nothing dropped; the tightenings an HA overlay passes through ``rib_exec``).
(c) Filters: on the event rule the filter is read at the flip's close only and never closes an open trade (a refused
    flip still ends the other side's trade); each row asks exactly its filter; on a synthetic market the real F1,
    F2, F3, FR and FS gate exactly the F0 entries they allow, FR is the higher ribbon's trend of the last closed bar,
    FS the dashboard's label.
(d) STK: the state is the ribbon trend where the context allows it (a state filter: the position closes when the
    context turns), S1 = 3 x ATR from the fill, flat after a stop until the state changes; on the synthetic market
    RM / RA / RMA use FS, the higher MA200 of PREREG 6.10 and both.
(e) One trade per flip: every trade starts at a flip of its side, no flip has two, nothing is busy or dropped.
(f) Causality: every decision of a bar closing at or before T is the same when the data after T is removed (all 163
    rows, synthetic bars here and the study's bars in (g)).
(g) Real data (skipped when the store is absent; read to 2019-07-01 only): causality, no flip without a stop, and an
    execution smoke test on Development data (2019-01-01 to 2019-06-30) for one row of each rule type through
    ``tradeiq2_market.run_variant``. Its profit or loss is neither printed, asserted nor reported: only counts, times
    and stop geometry are checked.
"""

from __future__ import annotations

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_ribbon as RB
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_ribbon as R

DAY = 86400
T0 = TM.s_of("2019-03-04")              # a Monday, 00:00 UTC
SYMS = ("XAUUSDm", "BTCUSDm")
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

# PREREG 6.1 "Size: 2 sides x 4 exits x 17 filter slots = 136 rows, plus 6 ALMA-X rows, plus 3 RIB-LIT rows, per
# symbol"; 6.10 "Size: 3 x 2 x 3 = 18 rows per symbol"; RIB-LIT "(sensitivity; not eligible)"; PREREG 7: controls
# (ALMA-X) can qualify. The 17 filter slots: 1H 7 (F0, F1, F2-4H, F2-1D, FR, F3, FS), 4H 6, 1D 4.
PLAN = {("RIB", True): 136, ("RIB", False): 3, ("ALMA-X", True): 6, ("STK", True): 18}
PLAN_RIB_TF = {"1H": 2 * 4 * 7, "4H": 2 * 4 * 6, "1D": 2 * 4 * 4}
PLAN_FILTERS = {"1H": {"F0", "F1", "F2-4H", "F2-1D", "FR", "F3", "FS"}, "4H": {"F0", "F1", "F2-1D", "FR", "F3", "FS"},
                "1D": {"F0", "F1", "F3", "FS"}}


def by_id(symbol):
    return {v.id: v for v in R.variants(symbol)}


@pytest.mark.parametrize("symbol", SYMS)
def test_a_the_rows_per_symbol_are_the_preregs(symbol):
    vs = R.variants(symbol)
    assert len(vs) == 136 + 6 + 3 + 18 == 163
    got = {}
    for v in vs:
        got[(v.family, v.eligible)] = got.get((v.family, v.eligible), 0) + 1
    assert got == PLAN and R.plan_counts(symbol) == PLAN
    assert sum(PLAN_RIB_TF.values()) == 136
    for tf, n in PLAN_RIB_TF.items():
        assert sum(1 for v in vs if v.family == "RIB" and v.eligible and v.tf == tf) == n
    ids = [v.id for v in vs]
    assert len(set(ids)) == len(ids)
    for v in vs:
        assert isinstance(v, M.Variant) and v.symbol == symbol and v.tf in ("1H", "4H", "1D")
        assert v.id.startswith(f"{symbol}|{v.tf}|{v.family}|") and not any(ch.isspace() for ch in v.id)
        assert v.family in ("RIB", "ALMA-X", "STK") and isinstance(v.eligible, bool)
        assert v.script == ("STK" if v.family == "STK" else "RIB")
        assert "information only" not in v.info                # PREREG 6.1 / 6.10 have no information-only row
        assert M.Variant(**{k: getattr(v, k) for k in ("id", "symbol", "tf", "script", "family", "eligible",
                                                       "info", "params")}).ident()["params"]      # JSON-able
    lit = [v for v in vs if not v.eligible]
    assert [v.id for v in lit] == [f"{symbol}|{tf}|RIB|RIB-LIT|LS|X0|F0" for tf in ("1H", "4H", "1D")]
    assert all(v.info == "sensitivity; not eligible" and v.params["stop"] == "literal" for v in lit)


def test_a_each_timeframe_has_the_preregs_filters_exits_sides_and_controls():
    vs = R.variants("XAUUSDm")
    for tf in ("1H", "4H", "1D"):
        rib = [v for v in vs if v.family == "RIB" and v.eligible and v.tf == tf]
        combos = {(v.params["side"], v.params["exit"], v.params["filter"]) for v in rib}
        assert len(combos) == len(rib)
        assert combos == {(s, e, f) for s in ("LS", "LO") for e in ("X0", "XT2", "XP", "XBE") for f in PLAN_FILTERS[tf]}
        assert all(v.id.endswith(f"|{v.params['side']}|{v.params['exit']}|{v.params['filter']}") for v in rib)
        assert all(v.params["stop"] == "intended" and v.params["rule"] == f"RIB-{v.params['side']}" for v in rib)
        alma = [v for v in vs if v.family == "ALMA-X" and v.tf == tf]
        assert sorted(v.id for v in alma) == sorted(f"XAUUSDm|{tf}|ALMA-X|{s}|X0|F0" for s in ("LS", "LO"))
        assert all(v.eligible and v.params["trend"] == "alma-cross" and v.params["stop"] == "intended" for v in alma)
        stk = [v for v in vs if v.family == "STK" and v.tf == tf]
        assert sorted(v.id for v in stk) == sorted(f"XAUUSDm|{tf}|STK|{r}|{s}|S1" for r in ("STK-RM", "STK-RA",
                                                                                          "STK-RMA")
                                                   for s in ("LS", "LO"))
        ma = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}[tf]                     # PREREG 6.10
        ctx_of = {v.params["rule"]: tuple(v.params["context"]) for v in stk}
        assert ctx_of == {"STK-RM": ("FS",), "STK-RA": (ma,), "STK-RMA": ("FS", ma)}
        assert all(v.params["stop"] == "S1" for v in stk)
    assert R.variants("USTECm") == [] and R.variants("EURUSDm") == [] and R.variants("GBPUSDm") == []
    with pytest.raises(ValueError):
        R.variants("ETHUSDm")


def _swap(vid, old, new):
    t = vid.split("|")
    return "|".join(new if x == old else x for x in t) if t.count(old) == 1 else None


def test_a_ids_pair_the_way_the_driver_pairs_them():
    for s in SYMS:
        ids = by_id(s)
        rib = [v for v in ids.values() if v.family == "RIB" and v.eligible]
        for v in rib:
            if v.params["exit"] in ("XP", "XBE", "XT2"):                       # claims 2 and 3
                assert _swap(v.id, v.params["exit"], "X0") in ids
            if v.params["exit"] == "XP":
                assert _swap(v.id, "XP", "XT2") in ids
            f = v.params["filter"]
            if f != "F0":                                                       # vs_f0: the same row with F0
                assert _swap(v.id, f, "F0") in ids
        for v in (v for v in ids.values() if v.family == "ALMA-X"):            # claim 1: exactly one RIB partner
            side = v.params["side"]
            mates = [x for x in rib if x.tf == v.tf and {side, "X0", "F0"} <= set(x.id.split("|"))]
            assert [x.id for x in mates] == [f"{s}|{v.tf}|RIB|{side}|X0|F0"]
        for tf in ("1H", "4H", "1D"):                                           # PREREG 6.8's Heikin Ashi bases
            assert f"{s}|{tf}|RIB|LS|X0|F0" in ids and f"{s}|{tf}|RIB|LO|X0|F0" in ids


def test_a_describe_and_build_refuse_rows_outside_the_plan():
    o = np.full(720, 9000.0)
    ctx = M.Context(M.TMarket2("BTCUSDm", {"t": T0 + 60 * np.arange(720, dtype=np.int64), "o": o, "h": o + 1.0,
                                           "l": o - 1.0, "c": o.copy(), "spread_mean": np.full(720, 10.0),
                                           "n": np.ones(720)}))
    for v in R.variants("BTCUSDm"):
        assert len(R.describe(v)) > 80
    with pytest.raises(ValueError):
        R.build(M.Variant("BTCUSDm|1H|RIB|LS|X9|F0", "BTCUSDm", "1H", "RIB", "RIB"), ctx)
    with pytest.raises(ValueError):
        R.build(by_id("XAUUSDm")["XAUUSDm|1H|RIB|LS|X0|F0"], ctx)             # a gold row on BTC's context
    with pytest.raises(ValueError):
        R.build(M.Variant("BTCUSDm|4H|RIB|LS|X0|F2-4H", "BTCUSDm", "4H", "RIB", "RIB"), ctx)   # not a 4H filter
    with pytest.raises(ValueError):
        R.build(M.Variant("BTCUSDm|1H|RIB|LS|X0|F0", "BTCUSDm", "4H", "RIB", "RIB"), ctx)      # id and tf disagree
    assert isinstance(R.build(by_id("BTCUSDm")["BTCUSDm|1H|RIB|LS|X0|F0"], ctx), M.Exec)


# ───────────────────────────── hand-made bars and an injected ribbon ─────────────────────────────

def flat(k, p=100.0):
    o = np.full(k, p)
    return o, o + 0.02, o - 0.02, o.copy()


def level(bars, a, z, p):
    """Minutes [a, z) at price p (open = close = p, high p + 0.02, low p - 0.02)."""
    o, h, l, c = bars
    o[a:z], c[a:z], h[a:z], l[a:z] = p, p, p + 0.02, p - 0.02


def market(bars, sp=0.2, symbol="XAUUSDm"):
    """Continuous M1 bars from T0 (1H bar b holds minutes 60b .. 60b + 59; a decision at its close fills at minute
    60(b + 1)); XAUUSDm makes $1 per $1 of price on 0.01 lot."""
    o, h, l, c = (np.asarray(x, np.float64) for x in bars)
    k = len(o)
    return M.TMarket2(symbol, {"t": T0 + 60 * np.arange(k, dtype=np.int64), "o": o, "h": h, "l": l, "c": c,
                               "spread_mean": np.full(k, float(sp)), "n": np.ones(k)})


def fake_ribbon(n, flips=None, risk_long=1.0, risk_short=1.0, lit_long=None, lit_short=None, alma=None):
    """A ribbon output with the port's keys: the given flips (they must alternate), the trend they make, the
    intended risks (scalars or per bar), the literal risks on the flip bars, an ALMA (default NaN)."""
    flip = np.zeros(n, np.int8)
    for b, s in (flips or {}).items():
        flip[b] = s
    trend, again = R.side_trend(flip == 1, flip == -1)
    assert np.array_equal(again, flip), "the hand-made flips must alternate"
    out = {k: np.zeros(n) for k in RB.KEYS}
    rl = np.broadcast_to(np.asarray(risk_long, np.float64), (n,)).copy()
    rs = np.broadcast_to(np.asarray(risk_short, np.float64), (n,)).copy()
    out.update(bull_setup=flip == 1, bear_setup=flip == -1, flip=flip, trend=trend, risk_long=rl, risk_short=rs,
               risk_long_lit=np.where(flip == 1, rl if lit_long is None else lit_long, NAN),
               risk_short_lit=np.where(flip == -1, rs if lit_short is None else lit_short, NAN),
               alma=np.full(n, NAN) if alma is None else np.broadcast_to(alma, (n,)).astype(np.float64),
               atr=np.ones(n))
    return {k: out[k] for k in RB.KEYS}


def inject(ctx, tf, out):
    got = ctx.get(R.MODULE, tf, R.RIBBON_PARAMS, lambda: out)
    assert got is out
    return out


def hand_ctx(mk, tf="1H", **kw):
    ctx = M.Context(mk)
    inject(ctx, tf, fake_ribbon(len(ctx.bars(tf)), **kw))
    return ctx


def masks(ctx, table):
    """``ctx.allow`` replaced: ``table`` maps a filter to (allow_long, allow_short); F0 and LO as PREREG 5; every
    other name allows both sides. Returns the list of (tf, name) asked."""
    asked = []

    def allow(tf, name):
        asked.append((tf, name))
        if name in table:
            return tuple(np.asarray(x, bool) for x in table[name])
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


def V(vid):
    return by_id(vid.split("|")[0])[vid]


def no_drops(r):
    return r.counts["dropped_stop"] == 0 and r.counts["dropped_target"] == 0 and r.counts["busy"] == 0


# ───────────────────────────── (b) entries and exits by hand ─────────────────────────────

def test_b_rib_ls_x0_a_flip_opens_and_the_opposite_flip_exits_and_reverses():
    mk = market(flat(720))
    ctx = hand_ctx(mk, flips={1: 1, 4: -1, 7: 1})
    v = V("XAUUSDm|1H|RIB|LS|X0|F0")
    ex = R.build(v, ctx)
    assert ex.kind == "events" and ex.label == v.id and len(ex.legs) == 1 and ex.orders is None
    E = ex.entries
    assert list(E.bar) == [1, 4, 7] and list(E.side) == [1, -1, 1] and list(E.tag) == [0, 1, 2]
    assert np.allclose(E.stop_dist, 1.0) and np.isnan(E.stop_level).all() and np.isnan(E.target_r).all()
    assert np.isnan(E.be_r).all() and (E.exit_bar == -1).all()
    assert list(np.flatnonzero(ex.exit_long)) == [4] and list(np.flatnonzero(ex.exit_short)) == [1, 7]
    r = run(mk, ex)
    # fills at the open after the flip bar's close: a buy at the ask (100.2), a sell at the bid (100.0)
    assert rows(r) == [(1, 120, 300, 100.2, 100.0, "signal"), (-1, 300, 480, 100.0, 100.2, "signal"),
                       (1, 480, 719, 100.2, 100.0, "end")]
    assert np.allclose(r.trades.risk, 1.0) and list(r.trades.tag) == [0, 1, 2] and list(r.trades.bar) == [1, 4, 7]
    assert r.counts["candidates"] == 3 and r.counts["taken"] == 3 and no_drops(r)


def test_b_rib_lo_a_bear_flip_closes_the_long_and_opens_nothing():
    mk = market(flat(720))
    ctx = hand_ctx(mk, flips={1: 1, 4: -1, 7: 1})
    ex = R.build(V("XAUUSDm|1H|RIB|LO|X0|F0"), ctx)
    assert list(ex.entries.bar) == [1, 7] and list(ex.entries.tag) == [0, 2] and ex.exit_short is None
    r = run(mk, ex)
    assert rows(r) == [(1, 120, 300, 100.2, 100.0, "signal"), (1, 480, 719, 100.2, 100.0, "end")]


def test_b_after_a_stop_the_rule_is_flat_until_the_next_flip():
    bars = flat(720)
    bars[2][200] = 99.1                               # the low reaches the stop 100.2 - 1.0 = 99.2 at minute 200
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 6: -1})          # the trend stays up on bars 2-5: no flip, no new entry
    r = run(mk, R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx))
    # the stop fills at its level, one extra spread is charged (99.2 - 0.2); the next trade is the bear flip's
    assert rows(r) == [(1, 120, 200, 100.2, 99.0, "stop"), (-1, 420, 719, 100.0, 100.2, "end")]
    assert r.trades.slippage.iloc[0] == pytest.approx(0.2) and no_drops(r)


def test_b_xt2_all_out_at_2r_then_flat_until_the_next_flip():
    bars = flat(720)
    bars[1][250] = 102.3                              # the high reaches 2R = 100.2 + 2 x 1.0 = 102.2
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 8: -1})
    ex = R.build(V("XAUUSDm|1H|RIB|LS|XT2|F0"), ctx)
    assert np.allclose(ex.entries.target_r, 2.0) and np.isnan(ex.entries.be_r).all()
    assert rows(run(mk, ex)) == [(1, 120, 250, 100.2, 102.2, "target"), (-1, 540, 719, 100.0, 100.2, "end")]
    x0 = run(mk, R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx))
    assert rows(x0) == [(1, 120, 540, 100.2, 100.0, "signal"), (-1, 540, 719, 100.0, 100.2, "end")]


def test_b_xp_half_out_at_2r_the_other_half_at_the_opposite_flip():
    bars = flat(720)
    bars[1][250] = 102.3
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 8: -1})
    ex = R.build(V("XAUUSDm|1H|RIB|LS|XP|F0"), ctx)
    assert [g.weight for g in ex.legs] == [0.5, 0.5] and ex.legs[0].target_r == 2.0 and ex.legs[1].no_target
    assert np.isnan(ex.entries.target_r).all()
    r = run(mk, ex)
    assert [w for w, _ in r.legs] == [0.5, 0.5] and not r.single
    target, rest = r.legs[0][1], r.legs[1][1]
    assert list(target.eix) == [120, 540] and list(rest.eix) == [120, 540]                 # identical entries
    assert int(target.xix[0]) == 250 and int(target.why[0]) == X.WHY_TARGET and target.xpx[0] == pytest.approx(102.2)
    assert int(rest.xix[0]) == 540 and int(rest.why[0]) == X.WHY_SIGNAL and rest.xpx[0] == pytest.approx(100.0)
    tr = r.trades
    assert len(tr) == 2 and list(tr.entry_ix) == [120, 540] and int(tr.exit_ix[0]) == 540
    assert tr.reasons[0] == "target|signal" and tr.reason[0] == "signal"
    assert tr.pnl[0] == pytest.approx(0.5 * (102.2 - 100.2) + 0.5 * (100.0 - 100.2))
    assert tr.exit[0] == pytest.approx(0.5 * 102.2 + 0.5 * 100.0) and tr.risk[0] == pytest.approx(1.0)
    assert r.net == pytest.approx(float(tr.pnl.sum())) and no_drops(r)


def test_b_xbe_the_stop_moves_to_the_fill_once_1r_is_touched_from_the_next_m1_bar():
    bars = flat(720)
    level(bars, 190, 261, 101.0)
    bars[1][200] = 101.3                              # 1R = 100.2 + 1.0 = 101.2 touched at minute 200 ...
    bars[2][200] = 100.1                              # ... and the fill (100.2) crossed in that same M1 bar: no exit
    bars[2][260] = 100.1                              # the break-even stop at 100.2 is hit at minute 260
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 8: -1})
    ex = R.build(V("XAUUSDm|1H|RIB|LS|XBE|F0"), ctx)
    assert np.allclose(ex.entries.be_r, 1.0) and np.isnan(ex.entries.target_r).all()
    # the stop fills at the fill's level, one spread is charged: a break-even exit loses the spread
    assert rows(run(mk, ex)) == [(1, 120, 260, 100.2, 100.0, "stop"), (-1, 540, 719, 100.0, 100.2, "end")]
    x0 = run(mk, R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx))
    assert rows(x0)[0] == (1, 120, 540, 100.2, 100.0, "signal")


def test_b_the_stop_is_risk_dist_from_the_actual_fill_at_both_costs_and_nothing_is_dropped():
    """PREREG 4: a level becomes a distance from the actual fill. The open after the flip gaps to 101 (the flip bar
    closed at 100): the long fills at 101.2 and its stop is 100.2, not 99.0 (the close minus 1R) nor 100.0. At x1.5
    it fills at 101.3 and its stop is 100.3, so the dip to 100.25 stops only the x1.5 run."""
    bars = flat(720)
    level(bars, 120, 300, 101.0)
    bars[2][250] = 100.25
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 8: -1})
    ex = R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx)
    r1, r15 = run(mk, ex, 1.0), run(mk, ex, 1.5)
    assert rows(r1)[0] == (1, 120, 300, 101.2, 99.8, "gap stop")          # the 100.0 open gaps through 100.2
    assert rows(r15)[0] == (1, 120, 250, 101.3, 100.0, "stop")             # 100.3 - 0.3
    assert r1.trades.risk[0] == pytest.approx(1.0) and r15.trades.risk[0] == pytest.approx(1.0)
    assert no_drops(r1) and no_drops(r15)
    # a short mirrors it: filled at the bid 101.0, its stop at 102.0 is reached by the ask high only at x1.5
    bars = flat(720)
    level(bars, 120, 300, 101.0)
    bars[1][250] = 101.75
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: -1, 8: 1})
    ex = R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx)
    assert rows(run(mk, ex, 1.0))[0] == (-1, 120, 540, 101.0, 100.2, "signal")
    assert rows(run(mk, ex, 1.5))[0] == (-1, 120, 250, 101.0, 102.3, "stop")


def test_b_rib_lit_takes_the_literal_stop_and_the_eligible_rows_the_intended_one():
    mk = market(flat(720))
    ctx = hand_ctx(mk, flips={1: 1, 4: -1}, risk_long=1.0, risk_short=1.0, lit_long=2.5, lit_short=0.75)
    lit = R.build(V("XAUUSDm|1H|RIB|RIB-LIT|LS|X0|F0"), ctx)
    assert list(lit.entries.bar) == [1, 4] and np.allclose(lit.entries.stop_dist, [2.5, 0.75])
    assert np.allclose(R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx).entries.stop_dist, [1.0, 1.0])
    assert np.allclose(run(mk, lit).trades.risk, [2.5, 0.75])
    with pytest.raises(ValueError):
        R.flip_entries(ctx, "1H", trend="alma-cross", stop="literal")


def test_b_alma_x_trades_the_close_crossing_the_alma_not_the_ribbons_flips():
    bars = flat(540)
    level(bars, 180, 360, 101.0)                      # hours 3-5 close above the ALMA (100.5)
    level(bars, 360, 420, 100.5)                      # hour 6 closes exactly on it: no setup, the trend holds
    mk = market(bars)
    n = 9
    ctx = hand_ctx(mk, flips={2: 1}, alma=100.5, risk_long=2.0 + 0.01 * np.arange(n),
                   risk_short=2.5 + 0.01 * np.arange(n))
    sig = R.signals(ctx, "1H", "alma-cross")
    assert list(sig["trend"]) == [-1, -1, -1, 1, 1, 1, 1, -1, -1]
    assert list(sig["flip"]) == [-1, 0, 0, 1, 0, 0, 0, -1, 0]
    ex = R.build(V("XAUUSDm|1H|ALMA-X|LS|X0|F0"), ctx)
    assert list(ex.entries.bar) == [0, 3, 7] and list(ex.entries.side) == [-1, 1, -1]
    assert np.allclose(ex.entries.stop_dist, [2.5, 2.03, 2.57])          # the intended risk of the cross bar
    assert list(np.flatnonzero(ex.exit_long)) == [0, 7] and list(np.flatnonzero(ex.exit_short)) == [3]
    assert rows(run(mk, ex)) == [(-1, 60, 240, 100.0, 101.2, "signal"), (1, 240, 480, 101.2, 100.0, "signal"),
                                 (-1, 480, 539, 100.0, 100.2, "end")]
    lo = R.build(V("XAUUSDm|1H|ALMA-X|LO|X0|F0"), ctx)
    assert list(lo.entries.bar) == [3] and rows(run(mk, lo)) == [(1, 240, 480, 101.2, 100.0, "signal")]
    rib = R.build(V("XAUUSDm|1H|RIB|LS|X0|F0"), ctx)                      # the ribbon's own flip: bar 2 only
    assert list(rib.entries.bar) == [2]


def test_b_side_trend_is_the_ports_trend_machine():
    rng = np.random.default_rng(11)
    c = 100.0 + np.cumsum(rng.normal(0.0, 1.0, 3000))
    h, l = c + rng.random(3000), c - rng.random(3000)
    r = RB.ribbon(c, h, l, c)
    tr, fl = R.side_trend(r["bull_setup"], r["bear_setup"])
    assert np.array_equal(tr, r["trend"]) and np.array_equal(fl, r["flip"]) and (fl != 0).sum() > 20
    with pytest.raises(ValueError):
        R.side_trend([True, True], [False, True])


def test_b_rib_exec_passes_the_heikin_ashi_overlays_through_with_the_absolute_level_rules():
    """The HA rows (PREREG 6.8) add exits, an entry gate and stop tightenings to the RIB-LS / LO x X0 x F0 bases.
    A tightened level above the bid at the open that executes it is a market exit there (PREREG 4); one below the
    bid becomes the stop; after an overlay exit the base waits for its next flip."""
    n = 12
    bars = flat(720)
    bars[2][200] = 99.7
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 4: -1, 7: 1})
    tight = np.full(n, NAN)
    tight[2] = 102.0                                  # decided at bar 2's close, executed at minute 180's open
    r = run(mk, R.rib_exec(ctx, "1H", "LS", "X0", "F0", tighten_long=tight))
    assert rows(r)[:2] == [(1, 120, 180, 100.2, 100.0, "signal"), (-1, 300, 480, 100.0, 100.2, "signal")]
    assert r.counts["tighten_exits"] == 1
    tight[2] = 99.8                                   # below the bid: the new stop, hit by the 99.7 low at 200
    r = run(mk, R.rib_exec(ctx, "1H", "LS", "X0", "F0", tighten_long=tight))
    assert rows(r)[0] == (1, 120, 200, 100.2, 99.6, "stop") and r.counts["tighten_rows"] == 1
    extra = np.zeros(n, bool)
    extra[2] = True                                   # an HA exit at bar 2: flat until the bear flip of bar 4
    r = run(mk, R.rib_exec(ctx, "1H", "LS", "X0", "F0", exit_long=extra))
    assert rows(r)[:2] == [(1, 120, 180, 100.2, 100.0, "signal"), (-1, 300, 480, 100.0, 100.2, "signal")]
    gate = (np.ones(n, bool), np.ones(n, bool))
    gate[0][1] = False                                # HA-AND refuses the bull flip of bar 1
    r = run(mk, R.rib_exec(ctx, "1H", "LO", "X0", "F0", gate=gate))
    assert rows(r) == [(1, 480, 719, 100.2, 100.0, "end")]


# ───────────────────────────── (c) filters ─────────────────────────────

def test_c_an_event_filter_is_read_at_the_flip_and_never_closes_an_open_trade():
    mk = market(flat(720))
    ctx = hand_ctx(mk, flips={1: 1, 4: -1, 7: 1, 9: -1})
    n = 12
    al, ash = np.ones(n, bool), np.ones(n, bool)
    al[2:4] = False                                   # turns against the open long: it stays open
    ash[4] = False                                    # refuses the bear flip's short: the long still exits there
    al[7] = False                                     # refuses the bull flip of bar 7
    asked = masks(ctx, {"F1": (al, ash)})
    r = run(mk, R.build(V("XAUUSDm|1H|RIB|LS|X0|F1"), ctx))
    assert rows(r) == [(1, 120, 300, 100.2, 100.0, "signal"), (-1, 600, 719, 100.0, 100.2, "end")]
    assert ("1H", "F1") in asked
    r = run(mk, R.build(V("XAUUSDm|1H|RIB|LO|X0|F1"), ctx))
    assert rows(r) == [(1, 120, 300, 100.2, 100.0, "signal")]
    # the same row through a state filter would have closed the long at bar 2: the event rule does not
    assert list(R.build(V("XAUUSDm|1H|RIB|LS|X0|F1"), ctx).entries.bar) == [1, 9]


def test_c_each_row_asks_exactly_its_filters():
    mk = market(flat(720))
    ctx = M.Context(mk)
    for tf in ("1H", "4H", "1D"):
        inject(ctx, tf, fake_ribbon(len(ctx.bars(tf))))
    asked = masks(ctx, {})
    for v in R.variants("XAUUSDm"):
        del asked[:]
        R.build(v, ctx)
        names = {name for tf, name in asked}
        assert all(tf == v.tf for tf, _ in asked)
        if v.family == "STK":
            want = set(v.params["context"]) | ({"LO"} if v.params["side"] == "LO" else set())
        else:
            want = {v.params["filter"]}
        assert names == want, (v.id, names)


def btc_like(days=450, seed=3, start="2018-03-05"):
    """Around the clock, a random walk with two-day trends (the filters' test market), so that the ribbons flip on
    every timeframe and every MA200, the TSI and the dashboard change sides."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    drift = np.repeat(rng.normal(0.0, 0.03, n // 2880 + 1), 2880)[:n]
    c = 20000.0 + np.cumsum(drift + rng.normal(0.0, 2.0, n))
    o = np.concatenate(([20000.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 1.0, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 1.0, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(n, 10.0), "n": np.ones(n)}


SYNTH_CUT = "2019-02-15"


@pytest.fixture(scope="module")
def synth():
    """The synthetic market's Context and its M1 arrays (``truncated`` cuts them)."""
    m1 = btc_like()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        full = M.Context(M.TMarket2("BTCUSDm", m1))
    return full, m1


def truncated(m1, cut_s):
    """The same market with every M1 bar at or after ``cut_s`` removed."""
    keep = m1["t"] < cut_s
    return M.Context(M.TMarket2("BTCUSDm", {k: v[keep] for k, v in m1.items()}))


def test_c_real_filters_gate_exactly_the_f0_entries_they_allow_and_change_no_exit(synth):
    ctx = synth[0]
    for tf in ("1H", "4H", "1D"):
        for side in ("LS", "LO"):
            base = R.build(V(f"BTCUSDm|{tf}|RIB|{side}|X0|F0"), ctx)
            E0 = base.entries
            assert len(E0) >= (5 if tf == "1D" else 40)
            for f in R.RIB_FILTERS[tf]:
                ex = R.build(V(f"BTCUSDm|{tf}|RIB|{side}|X0|{f}"), ctx)
                al, ash = ctx.allow(tf, f)
                keep = np.where(E0.side == 1, al[E0.bar], ash[E0.bar])
                for k in ("bar", "side", "stop_dist", "tag"):
                    assert np.array_equal(getattr(ex.entries, k), getattr(E0, k)[keep])
                assert np.array_equal(ex.exit_long, base.exit_long)
                assert (ex.exit_short is None) == (side == "LO")
                if side == "LS":
                    assert np.array_equal(ex.exit_short, base.exit_short)
                if f != "F0" and tf != "1D":
                    assert 0 < keep.sum() < len(keep), (tf, side, f)
    # FR: the higher timeframe's ribbon trend of the last CLOSED higher bar (1H <- 4H, 4H <- 1D); FS: the label
    from backtesting.research import tradeiq2_ind_msd as MS
    for tf, htf in (("1H", "4H"), ("4H", "1D")):
        hb = ctx.bars(htf)
        trend = RB.ribbon(hb.o, hb.h, hb.l, hb.c)["trend"].astype(np.float64)
        at = TM.htf_at(hb, trend, ctx.bars(tf), 0.0)
        al, ash = ctx.allow(tf, "FR")
        assert np.array_equal(al, at == 1.0) and np.array_equal(ash, at == -1.0)
        k = np.searchsorted(hb.tc, ctx.bars(tf).tc, side="right") - 1          # by hand, at a few bars
        for i in np.linspace(300, len(k) - 1, 50).astype(int):
            assert al[i] == (trend[k[i]] == 1.0) and ash[i] == (trend[k[i]] == -1.0)
    for tf in ("1H", "4H", "1D"):
        lab = MS.structure_dashboard({r: ctx.bars(r) for r in F.MSD_ROWS[tf]}, tf)["label"]
        al, ash = ctx.allow(tf, "FS")
        assert np.array_equal(al, lab >= 1) and np.array_equal(ash, lab <= -1) and al.any() and ash.any()


# ───────────────────────────── (d) STK ─────────────────────────────

def test_d_stk_is_a_state_rule_the_context_closes_and_reopens_it_and_a_stop_waits_for_a_change():
    bars = flat(1080)                                  # 18 hours
    bars[2][500] = 99.1                                # stops the second long (S1 = 1.0 from 100.2) at minute 500
    mk = market(bars)
    ctx = hand_ctx(mk, flips={1: 1, 12: -1})          # trend +1 on bars 1-11, -1 from bar 12
    n = 18
    ctx.get(R.MODULE, "1H", R.S1_PARAMS, lambda: np.ones(n))                  # S1 injected: 1.0
    fs_l, fs_s = np.zeros(n, bool), np.zeros(n, bool)
    fs_l[1:4] = True
    fs_l[6:12] = True
    fs_s[12:16] = True
    f2_l, f2_s = np.ones(n, bool), np.zeros(n, bool)
    f2_l[8] = False
    f2_s[12:14] = True
    masks(ctx, {"FS": (fs_l, fs_s), "F2-4H": (f2_l, f2_s)})
    up, dn = [1] * 11, [-1] * 6
    trend = np.asarray([0] + up + dn)
    assert np.array_equal(ctx.get(R.MODULE, "1H", R.RIBBON_PARAMS, lambda: None)["trend"], trend)
    want = {
        ("STK-RM", "LS"): [0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, -1, -1, -1, -1, 0, 0],
        ("STK-RM", "LO"): [0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
        ("STK-RA", "LS"): [0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, -1, -1, 0, 0, 0, 0],
        ("STK-RA", "LO"): [0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
        ("STK-RMA", "LS"): [0, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, -1, -1, 0, 0, 0, 0],
        ("STK-RMA", "LO"): [0, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
    }
    for (rule, side), st in want.items():
        ex = R.build(V(f"XAUUSDm|1H|STK|{rule}|{side}|S1"), ctx)
        assert ex.kind == "state" and not ex.overlays and list(ex.state) == st, (rule, side)
        assert np.allclose(ex.stop, 1.0)
    r = run(mk, R.build(V("XAUUSDm|1H|STK|STK-RM|LS|S1"), ctx))
    # long 1-3, closed when FS turns at bar 4; again from bar 6, stopped at minute 500, no re-entry while the state
    # stays +1 (bars 7-11); short from bar 12 until the state turns flat at bar 16
    assert rows(r) == [(1, 120, 300, 100.2, 100.0, "signal"), (1, 420, 500, 100.2, 99.0, "stop"),
                       (-1, 780, 1020, 100.0, 100.2, "signal")]
    assert np.allclose(r.trades.risk, 1.0)


def test_d_stk_on_real_indicators_uses_fs_the_higher_ma200_and_s1(synth):
    ctx = synth[0]
    for tf in ("1H", "4H", "1D"):
        trend = R.ribbon_of(ctx, tf)["trend"]
        ma = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}[tf]
        fs, f2 = ctx.allow(tf, "FS"), ctx.allow(tf, ma)
        both = (fs[0] & f2[0], fs[1] & f2[1])
        s1 = 3.0 * np.asarray(M.atr14(ctx.bars(tf)))
        for rule, (al, ash) in (("STK-RM", fs), ("STK-RA", f2), ("STK-RMA", both)):
            ls = np.where((trend == 1) & al, 1, np.where((trend == -1) & ash, -1, 0))
            ex = R.build(V(f"BTCUSDm|{tf}|STK|{rule}|LS|S1"), ctx)
            assert np.array_equal(ex.state, ls) and np.array_equal(ex.stop, s1, equal_nan=True)
            lo = R.build(V(f"BTCUSDm|{tf}|STK|{rule}|LO|S1"), ctx)
            assert np.array_equal(lo.state, np.where(ls == 1, 1, 0))
            if tf != "1D":
                assert (ls == 1).any() and (ls == -1).any()
        assert np.array_equal(R.s1_stop(ctx, tf), TM.s1_stop(ctx.bars(tf)), equal_nan=True)      # study 1's S1


# ───────────────────────────── (e) one trade per flip ─────────────────────────────

@pytest.mark.parametrize("exit_", ["X0", "XT2", "XP", "XBE"])
def test_e_every_trade_starts_at_a_flip_of_its_side_and_no_flip_has_two(synth, exit_):
    ctx = synth[0]
    a, z = "2019-01-01", "2019-05-20"
    a_s = TM.s_of(a)
    for tf in ("1H", "4H"):
        b = ctx.bars(tf)
        flip = R.ribbon_of(ctx, tf)["flip"]
        for side in ("LS", "LO"):
            for f in ("F0", "F3"):
                ex = R.build(V(f"BTCUSDm|{tf}|RIB|{side}|{exit_}|{f}"), ctx)
                r = M.run_exec(ctx.mk, ex, a, z)
                tr = r.trades
                inside = (b.tc[ex.entries.bar] > a_s) & (b.ex[ex.entries.bar] < r.iz)
                assert r.counts["candidates"] == int(inside.sum()) == r.counts["taken"] == len(tr) > 0
                assert no_drops(r)
                bar = tr.bar.to_numpy()
                assert np.array_equal(flip[bar], tr.side.to_numpy()) and len(set(tr.tag)) == len(tr)
                assert np.array_equal(tr.entry_ix.to_numpy(), b.ex[bar])                    # the next M1 open
                assert (tr.entry_ix.to_numpy()[1:] >= tr.exit_ix.to_numpy()[:-1]).all()      # one at a time
                # every trade is out by the next flip's fill
                nxt = np.searchsorted(np.flatnonzero(flip), bar, side="right")
                fl = np.flatnonzero(flip)
                has = nxt < len(fl)
                assert (tr.exit_ix.to_numpy()[has] <= b.ex[fl[nxt[has]]]).all()
                if side == "LO":
                    assert (tr.side == 1).all()


# ───────────────────────────── (f) causality ─────────────────────────────

def decisions(ctx, v, upto_s):
    """Every decision a row takes at bars closing at or before ``upto_s``: entries (bar, side, stop, target,
    break-even, tag), per-bar exits and legs (events); the state and the stop per bar (STK)."""
    ex = R.build(v, ctx)
    b = ctx.bars(v.tf)
    keep = b.tc <= upto_s
    if ex.kind == "state":
        return {"state": ex.state[keep], "stop": np.asarray(ex.stop)[keep]}
    E = ex.entries
    m = b.tc[E.bar] <= upto_s
    out = {k: getattr(E, k)[m] for k in E.__dataclass_fields__}
    out["exit_long"] = np.asarray(ex.exit_long)[keep]
    out["exit_short"] = np.zeros(0) if ex.exit_short is None else np.asarray(ex.exit_short)[keep]
    out["legs"] = np.asarray([(g.weight, np.nan if g.target_r is None else g.target_r, g.no_target)
                              for g in ex.legs], np.float64)
    return out


def same_decisions(full, part, symbol, upto_s):
    for tf in ("1H", "4H", "1D"):
        bf, bp = full.bars(tf), part.bars(tf)
        k = int((bp.tc <= upto_s).sum())
        assert k > 0 and int((bf.tc <= upto_s).sum()) == k
        for f in ("t", "tc", "o", "h", "l", "c"):
            assert np.array_equal(getattr(bf, f)[:k], getattr(bp, f)[:k])
    n = 0
    for v in R.variants(symbol):
        a, b = decisions(full, v, upto_s), decisions(part, v, upto_s)
        assert a.keys() == b.keys()
        for key in a:
            assert np.array_equal(a[key], b[key], equal_nan=np.asarray(a[key]).dtype.kind == "f"), (v.id, key)
        n += 1
    return n


def cuts_before_flips(ctx, after):
    """Cut times that remove a decision a one-bar look-ahead would move: the open of the first flip bar (the ribbon's
    and ALMA-X's) and of the first STK-RMA state change after ``after`` on each timeframe."""
    out = set()
    for tf in ("1H", "4H", "1D"):
        b = ctx.bars(tf)
        st = R.stk_state(ctx, tf, "STK-RMA", "LS")
        change = np.flatnonzero(np.diff(st.astype(np.int64)) != 0) + 1
        for ix in (np.flatnonzero(R.signals(ctx, tf)["flip"]), np.flatnonzero(R.signals(ctx, tf, "alma-cross")["flip"]),
                   change):
            ix = ix[b.t[ix] > TM.s_of(after)]
            out.add(int(b.t[ix[0]]))
    return sorted(out)


def test_f_decisions_up_to_t_do_not_change_when_the_bars_after_t_are_removed(synth):
    full, m1 = synth
    cuts = [TM.s_of(SYNTH_CUT)] + cuts_before_flips(full, "2018-12-01")
    assert len(cuts) >= 5
    for cut in cuts:
        assert same_decisions(full, truncated(m1, cut), "BTCUSDm", cut) == 163


# ───────────────────────────── (g) real data (to 2019-07-01 only) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cache = {}
    d2, d1 = tmp_path_factory.mktemp("closed_study2"), tmp_path_factory.mktemp("closed_study1")

    def get(symbol, end, keep=True):
        """The study's market of ``symbol`` to ``end`` (never past 2019-07-01 here) as a Context; ``keep=False``: not
        cached (the cut markets of the causality test), so memory holds little more than one symbol at a time."""
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
            cache[key] = ctx
        return cache[key]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_g_real_bars_causality_and_every_flip_has_a_stop(symbol, real):
    full, part = real(symbol, "2019-07-01"), real(symbol, "2019-04-01", keep=False)
    assert full.mk.end_s == TM.s_of("2019-07-01") and part.mk.end_s == TM.s_of("2019-04-01")
    assert same_decisions(full, part, symbol, TM.s_of("2019-04-01")) == 163
    del part
    cut = TM.s_of("2019-05-01")                       # also cut right before a 1H flip (the open of its bar)
    b = full.bars("1H")
    fl = np.flatnonzero(R.signals(full, "1H")["flip"])
    cut = int(b.t[fl[b.t[fl] > cut][0]])
    part = real(symbol, str(TM.utc(cut).tz_localize(None)), keep=False)
    assert same_decisions(full, part, symbol, cut) == 163
    del part
    for tf in ("1H", "4H", "1D"):
        for trend in ("ribbon", "alma-cross"):
            ft = R.flip_table(full, tf, trend)
            assert len(ft["bar"]) > 10 and np.isfinite(ft["risk"]).all() and (ft["risk"] > 0).all()
            with np.errstate(invalid="ignore"):
                assert ((ft["risk_atr"] >= 0.75 - 1e-12) & (ft["risk_atr"] <= 3.0 + 1e-12)).all()
            if trend == "ribbon":
                assert np.isfinite(ft["risk_lit"]).all() and (ft["risk_lit"] > 0).all()
            n_all = int((R.signals(full, tf, trend)["flip"] != 0).sum())
            assert len(R.flip_entries(full, tf, "LS", trend)) == n_all          # every flip opens (LS, F0)


SMOKE = ("{s}|1H|RIB|LS|X0|F0", "{s}|1H|RIB|LO|XT2|F2-4H", "{s}|4H|RIB|LS|XP|FS", "{s}|4H|RIB|LS|XBE|FR",
         "{s}|1H|RIB|LS|XBE|F3", "{s}|4H|RIB|RIB-LIT|LS|X0|F0", "{s}|1H|ALMA-X|LS|X0|F0", "{s}|1H|STK|STK-RM|LS|S1",
         "{s}|4H|STK|STK-RA|LO|S1", "{s}|1D|STK|STK-RMA|LS|S1")
REASONS = {"X0": {"signal", "stop", "gap stop", "end"}, "XBE": {"signal", "stop", "gap stop", "end"},
           "XT2": {"signal", "stop", "gap stop", "end", "target", "gap target"},
           "XP": {"signal", "stop", "gap stop", "end", "target", "gap target"}}


@pytest.mark.parametrize("symbol", SYMS)
def test_g_smoke_one_row_of_each_rule_type_runs_on_development_data(symbol, real, monkeypatch):
    """2019-01-01 to 2019-06-30 through ``run_variant`` (the dev window shortened to the data held): it runs, and
    its trades are where the rule says (counts, times, stop geometry). No profit or loss is looked at."""
    ctx = real(symbol, "2019-07-01")
    monkeypatch.setitem(M.WINDOWS, "dev", (None, "2019-07-01"))
    assert M.window_span("dev", symbol) == ("2019-01-01", "2019-07-01")
    R.warm(ctx, R.variants(symbol))
    a_s = TM.s_of("2019-01-01")
    for pat in SMOKE:
        v = V(pat.format(s=symbol))
        ex = R.build(v, ctx)
        res = M.run_variant(ctx, v, ex, windows=("dev",), trades_windows=("dev",))
        assert len(res.rows) == 1
        row = res.rows[0]
        assert (row["vid"], row["window"], row["start"], row["end"]) == (v.id, "dev", "2019-01-01", "2019-07-01")
        assert row["eligible"] == v.eligible and row["family"] == v.family
        n = int(row["trades"])
        assert int(row["n_taken"]) == n and int(row["n_taken_x15"]) == int(row["trades_x15"])
        if v.tf != "1D":
            assert n > 0, v.id
        b = ctx.bars(v.tf)
        tr = res.trades
        assert set(tr.cost) <= {1.0, 1.5} and (tr.vid == v.id).all()
        bar = tr.bar.to_numpy()
        entry_s = np.asarray([int(x.timestamp()) for x in tr.entry_time], np.int64)
        assert np.array_equal(entry_s, ctx.mk.t[b.ex[bar]])                  # filled at the next M1 open
        assert (b.tc[bar] > a_s).all()
        if ex.kind == "events":
            assert int(row["n_busy"]) == 0 and int(row["n_dropped_stop"]) == 0 and int(row["n_dropped_target"]) == 0
            E = ex.entries
            inside = (b.tc[E.bar] > a_s) & (b.tc[E.bar] <= TM.s_of("2019-07-01"))
            assert int(row["n_candidates"]) <= int(inside.sum())
            pos = {int(x): i for i, x in enumerate(E.bar)}
            ix = np.asarray([pos[int(x)] for x in bar], np.int64)            # every trade is one of the entries
            assert np.array_equal(tr.side.to_numpy(), E.side[ix]) and np.array_equal(tr.tag.to_numpy(), E.tag[ix])
            assert np.allclose(tr.risk.to_numpy(), E.stop_dist[ix], rtol=1e-9, atol=1e-9)   # riskDist from the fill
            ext = v.params["exit"]
            for rs in (tr.reasons if "reasons" in tr.columns and ext == "XP" else tr.reason):
                assert set(str(rs).split("|")) <= REASONS[ext]
            if v.params["side"] == "LO":
                assert (tr.side == 1).all()
        else:
            st = ex.state
            prev = np.where(bar >= 1, st[np.maximum(bar - 1, 0)], 0)
            first = b.tc[bar - 1] <= a_s                                       # the window's first bar
            assert (st[bar] == tr.side.to_numpy()).all() and ((st[bar] != prev) | first).all()
            assert np.allclose(tr.risk.to_numpy(), np.asarray(ex.stop)[bar], rtol=1e-9, atol=1e-9)
            assert set(tr.reason) <= {"signal", "stop", "gap stop", "end"}
            if v.params["side"] == "LO":
                assert (tr.side == 1).all()

