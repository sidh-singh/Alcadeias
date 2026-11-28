"""
Study 2's Heikin Ashi rules (``backtesting/research/tradeiq2_rules_ha.py``): the rows of PREREG 6.8 (the management
overlays M1-M5 and HA-AND on the nine bases, the entry controls HA-H1 / HA-H2), executed by ``tradeiq2_market``.

(a) The grid: the rows per symbol are the PREREG's numbers (written here from its text): 9 bases x 6 overlays = 54
    HA-MANAGED, 2 rules x 2 sides x 2 filters x 3 timeframes = 24 HA-ENTRY, all eligible; the bases are study 1's
    frozen finalists and the ribbon's RIB-LS / RIB-LO x X0 x F0 rows; the ids carry the tokens the driver selects and
    pairs rows by, and the driver's grid check accepts them.
(b) Hand-made bars with an injected Heikin Ashi series (and an injected base state, S1 or ribbon, through the
    Context's cache, so that every event, fill and level is known by hand): M1 exits at a flip against the position
    and not at one in favour or on the entry bar, and the base waits for its own state to change; M4 at the rare
    age of the position's colour only; M2 / M3 tighten to the tighter of break-even and the bar's low (high), a level
    below the bid becomes the stop, a crossed one is a market exit (PREREG 4), break-even is the run's own fill (also
    at x1.5), events of the other colour do nothing, a WEAK run tightens from its second candle on; M5 = M1 + M2;
    HA-AND gates the base's entries at their decision close (state bases: per episode; ribbon bases: at the flip)
    and never closes a trade; HA-H1 / HA-H2's states, LO, and their filters as state filters.
(c) Filters: each row asks exactly its filter (HA-ENTRY: F0 or the timeframe's F2; the ribbon bases F0; study 1's
    bases their own study-1 filters, not the context's).
(d) The real port: the overlay arrays, the colour gate and the entry states are the port's events read as the
    module docstring says (by-hand loops on random bars); ``and_state`` and ``h1_state`` against plain loops.
(e) The bases and one trade per event: on a synthetic market, study 1's finalists' states and S1 are study 1's own
    (``tradeiq.Study``); every overlay row keeps its base's entries and only shortens its trades, HA-AND keeps a
    subset of the base's trades unchanged; HA-H1 takes at most one trade per streak, from its first STRONG candle,
    HA-H2 one per streak from its flip.
(f) Causality: every decision of a bar closing at or before T is the same when the data after T is removed (all 78
    rows of both symbols; synthetic bars here, the study's bars in (g)).
(g) Real data (skipped when the store is absent; read to 2019-07-01 only): causality; study 1's finalists' states and
    S1 on the study-2 market (gold from 2016) equal study 1's own on its market on every bar of 2019-H1; and an
    execution smoke test on Development data (2019-01-01 to 2019-06-30) for one row of each rule type through
    ``tradeiq2_market.run_variant``. Its profit or loss is neither printed, asserted nor reported: only counts,
    times, sides and exit reasons are checked.
"""

from __future__ import annotations

import gc
import hashlib
import json

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import tradeiq as T1
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_ind_ha as HA
from backtesting.research import tradeiq2_ind_ribbon as RB
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_ha as H
from backtesting.research import tradeiq2_rules_ribbon as R

T0 = TM.s_of("2019-03-04")              # a Monday, 00:00 UTC
SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")
NAN = float("nan")
LA = "XAUUSDm|1H|LaRSI|R2|F1|S0"         # gold's 1H finalist without a stop (long only)
VW = "BTCUSDm|1D|VWRSI|R3|F0|S1"         # BTC's 1D finalist with S1, both sides


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


def by_id(symbol):
    return {v.id: v for v in H.variants(symbol)}


def V(vid):
    return by_id(vid.split("|")[0])[vid]


def managed(symbol, overlay, base):
    return V(f"{symbol}|{base.split('|')[1]}|HA-MANAGED|{overlay}|{H.base_token(base)}")


# ───────────────────────────── (a) the grid ─────────────────────────────

# PREREG 6.8: "Size: 9 bases x 6 = 54 rows per symbol" (M1, M2, M3, M4, M5, HA-AND; bases: study 1's three
# finalists on each symbol, RIB-LS x X0 x F0 and RIB-LO x X0 x F0 on 1H, 4H and 1D); entry rules "LS and LO; F0 and
# F2 (1D: F1); 1H, 4H and 1D. 24 rows per symbol". Section 6.8 marks no row "not eligible" or "information only";
# the entry rules are controls, which PREREG 7 lets qualify.
PLAN = {("HA-MANAGED", True): 9 * 6, ("HA-ENTRY", True): 2 * 2 * 2 * 3}
FINALISTS = {"XAUUSDm": ["XAUUSDm|1H|QQE|R2|F2-4H|S0", "XAUUSDm|1H|LaRSI|R2|F1|S0", "XAUUSDm|4H|RSI|R2|F1|S0"],
             "BTCUSDm": ["BTCUSDm|1D|LaRSI|R2|F3|S1", "BTCUSDm|1D|VWRSI|R3|F0|S1", "BTCUSDm|4H|TSI|R2|F1|S0"]}
F2_OF = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}          # PREREG 6.8 "F2 (1D: F1)", as 6.3 / 6.4 / 6.7


@pytest.mark.parametrize("symbol", SYMS)
def test_a_the_rows_per_symbol_are_the_preregs(symbol):
    vs = H.variants(symbol)
    assert len(vs) == 54 + 24 == 78
    got = {}
    for v in vs:
        got[(v.family, v.eligible)] = got.get((v.family, v.eligible), 0) + 1
    assert got == PLAN and H.plan_counts(symbol) == PLAN and H.EXPECTED == PLAN
    ids = [v.id for v in vs]
    assert len(set(ids)) == len(ids)
    for v in vs:
        assert isinstance(v, M.Variant) and v.symbol == symbol and v.tf in TFS and v.script == "HA"
        assert v.id.startswith(f"{symbol}|{v.tf}|{v.family}|") and not any(ch.isspace() for ch in v.id)
        assert v.family in ("HA-MANAGED", "HA-ENTRY") and v.eligible is True
        assert "information only" not in v.info and "not eligible" not in v.info
        assert v.info == ("control" if v.family == "HA-ENTRY" else "")
        json.loads(v.ident()["params"])                                         # JSON-able
    man = [v for v in vs if v.family == "HA-MANAGED"]
    bases = []
    for v in man:
        if v.params["base"] not in bases:
            bases.append(v.params["base"])
    want = FINALISTS[symbol] + [f"{symbol}|{tf}|RIB|{s}|X0|F0" for tf in TFS for s in ("LS", "LO")]
    assert bases == want == list(H.bases(symbol))
    for b in bases:
        rows = [v for v in man if v.params["base"] == b]
        assert [v.params["overlay"] for v in rows] == ["M1", "M2", "M3", "M4", "M5", "HA-AND"]
        assert all(v.tf == b.split("|")[1] and v.params["ha_tf"] == v.tf for v in rows)  # HA on the base's timeframe
        assert all(v.id == f"{symbol}|{v.tf}|HA-MANAGED|{v.params['overlay']}|{H.base_token(b)}" for v in rows)
        assert all(H.base_of(v) == b for v in rows)
        assert all(v.params["base_kind"] == ("event" if "|RIB|" in b else "state") for v in rows)
    ent = [v for v in vs if v.family == "HA-ENTRY"]
    combos = {(v.tf, v.params["rule"], v.params["side"], v.params["filter"]) for v in ent}
    assert combos == {(tf, r, s, f) for tf in TFS for r in ("HA-H1", "HA-H2") for s in ("LS", "LO")
                      for f in ("F0", F2_OF[tf])}
    assert all(v.id == f"{symbol}|{v.tf}|HA-ENTRY|{v.params['rule']}|{v.params['side']}|{v.params['filter']}"
               for v in ent)
    assert all(v.params["stop"] == "none" and v.params["kind"] == "state" and H.base_of(v) is None for v in ent)


def test_a_the_bases_are_study_1s_frozen_finalists_and_the_ribbons_rows():
    """PREREG 6.8 reads the finalists from tradeiq_rsi/FINALISTS.md; the file read is the frozen one (its sha256)."""
    f = T1.STUDY_DIR / T1.FINALISTS_MD
    if not f.exists():
        pytest.skip("study 1's FINALISTS.md is not on this machine")
    want = (T1.STUDY_DIR / (T1.FINALISTS_MD + ".sha256")).read_text(encoding="utf-8").split()[0].strip().lower()
    assert hashlib.sha256(f.read_bytes()).hexdigest() == want
    vids, _ = T1.read_frozen(T1.STUDY_DIR)
    for s in SYMS:
        assert list(H.STUDY1_FINALISTS[s]) == [x for x in vids if x.startswith(s + "|")] == FINALISTS[s]
        grid1 = {v.vid for v in T1.grid(s)}
        assert set(FINALISTS[s]) <= grid1                                       # study 1's grid.csv ids
        rib = {v.id for v in R.variants(s)}
        for tf in TFS:
            assert f"{s}|{tf}|RIB|LS|X0|F0" in rib and f"{s}|{tf}|RIB|LO|X0|F0" in rib


def test_a_the_driver_accepts_the_grid_and_finds_each_overlay_and_base_by_its_tokens():
    T2 = pytest.importorskip("backtesting.research.tradeiq2")
    if not all(hasattr(T2, n) for n in ("checked_grid", "ha_base", "tokens_of", "swap", "VS_F0_FILTERS")):
        pytest.skip("the study driver has no checked_grid / ha_base / tokens_of")
    g, pairs = T2.checked_grid({"ha": H})                       # the plan's COUNT_TABLE rows for this module
    assert len(g) == 2 * 78 and set(g.group) == {"HA"}
    for s in SYMS:
        ids = by_id(s)
        for v in ids.values():
            toks = T2.tokens_of(v.id, dict(v.params))
            if v.family == "HA-MANAGED":
                assert T2.ha_base(v, {"ha": H}) == v.params["base"]
                for o in H.OVERLAYS:                             # claims 3 / 4 select the rows of one overlay
                    assert (o in toks) == (v.params["overlay"] == o), (v.id, o)
                assert not [t for t in T2.id_tokens(v.id)[2:] if t in T2.VS_F0_FILTERS]
            else:
                f = v.params["filter"]
                if f != "F0":                                    # vs_f0: the same row with F0
                    assert T2.swap(v.id, f, "F0") in ids
                assert not set(H.OVERLAYS) & toks


def test_a_describe_and_build_refuse_rows_outside_the_plan():
    mk = market(flat(3 * 1440))
    ctx = M.Context(mk)
    for s in SYMS:
        for v in H.variants(s):
            d = H.describe(v)
            assert len(d) > 100
            if v.family == "HA-MANAGED":
                assert v.params["base"] in d
    assert H.variants("USTECm") == [] and H.variants("EURUSDm") == [] and H.variants("GBPUSDm") == []
    with pytest.raises(ValueError):
        H.variants("ETHUSDm")
    with pytest.raises(ValueError):
        H.build(M.Variant("XAUUSDm|1H|HA-MANAGED|M6|RIB-LS-X0-F0", "XAUUSDm", "1H", "HA", "HA-MANAGED"), ctx)
    with pytest.raises(ValueError):                                             # id and timeframe disagree
        H.build(M.Variant("XAUUSDm|1H|HA-ENTRY|HA-H1|LS|F0", "XAUUSDm", "4H", "HA", "HA-ENTRY"), ctx)
    with pytest.raises(ValueError):                                             # not a 4H filter of the plan
        H.build(M.Variant("XAUUSDm|4H|HA-ENTRY|HA-H1|LS|F2-4H", "XAUUSDm", "4H", "HA", "HA-ENTRY"), ctx)
    with pytest.raises(ValueError):                                             # a BTC row on gold's context
        H.build(V("BTCUSDm|1H|HA-ENTRY|HA-H2|LS|F0"), ctx)
    with pytest.raises(ValueError):
        H.managed_exec(ctx, "XAUUSDm|1H|RSI|R2|F1|S0", "M1")                   # not one of the nine bases
    with pytest.raises(ValueError):
        H.overlay_arrays(ctx, "1H", "HA-AND")                                   # HA-AND is an entry gate
    with pytest.raises(ValueError):
        H.base_of(M.Variant("XAUUSDm|1H|RIB|LS|X0|F0", "XAUUSDm", "1H", "RIB", "RIB"))


# ───────────────────────────── hand-made bars and injected series ─────────────────────────────

def flat(k, p=100.0, w=0.02):
    o = np.full(k, p)
    return o, o + w, o - w, o.copy()


def level(bars, a, z, p, w=0.02):
    """Minutes [a, z) at price p (open = close = p, high p + w, low p - w)."""
    o, h, l, c = bars
    o[a:z], c[a:z], h[a:z], l[a:z] = p, p, p + w, p - w


def market(bars, sp=0.2, symbol="XAUUSDm"):
    """Continuous M1 bars from T0 (1H bar b holds minutes 60b .. 60b + 59, a 1D bar d minutes 1440d .. 1440d + 1439;
    a decision at a bar's close fills at the first minute of the next bar)."""
    o, h, l, c = (np.asarray(x, np.float64) for x in bars)
    k = len(o)
    return M.TMarket2(symbol, {"t": T0 + 60 * np.arange(k, dtype=np.int64), "o": o, "h": h, "l": l, "c": c,
                               "spread_mean": np.full(k, float(sp)), "n": np.ones(k)})


def btc_days(days, p=20000.0):
    return flat(days * 1440, p, 1.0)


def fake_ha(n, dirs, ind=(), weak=None, rare=(), strong=()):
    """A Heikin Ashi output with the port's per-bar keys: the colours ``dirs`` (flips where they change), INDECISION
    after STRONG at ``ind``, the WEAK runs ``weak`` ({bar: run}), rare ages at ``rare``, first STRONG candles at
    ``strong``."""
    d = np.asarray(dirs, np.int8)
    assert d.shape == (n,)
    flip = np.zeros(n, bool)
    flip[1:] = d[1:] != d[:-1]
    age = np.ones(n, np.int32)
    for t in range(1, n):
        age[t] = 1 if flip[t] else age[t - 1] + 1
    ev_ind = np.zeros(n, bool)
    ev_ind[list(ind)] = True
    assert not (ev_ind & flip).any(), "the port never has INDECISION-after-STRONG on a flip candle"
    wr = np.zeros(n, np.int32)
    for b, k in (weak or {}).items():
        wr[b] = k
    rare_now = np.zeros(n, bool)
    rare_now[list(rare)] = True
    evf = np.zeros(n, bool)
    evf[list(strong)] = True
    z = np.zeros(n)
    out = {"ha_o": z, "ha_h": z, "ha_l": z, "ha_c": z, "dir": d, "phase": np.ones(n, np.int8), "flip": flip,
           "age": age, "strong_run": np.zeros(n, np.int32), "weak_run": wr, "ev_ind": ev_ind,
           "ev_first_strong": evf, "pct_below": np.full(n, NAN), "rare_now": rare_now}
    assert set(out) == set(HA.KEYS) - {"streaks"}
    return out


def inject_ha(ctx, tf, out):
    got = ctx.get(H.MODULE, tf, H.HA_PARAMS, lambda: out)
    assert got is out
    return out


def inject_base(ctx, base, state, s1=None):
    tf = base.split("|")[1]
    st = np.asarray(state, np.int8)
    assert st.shape == (len(ctx.bars(tf)),)
    assert ctx.get(H.MODULE, tf, H.study1_params(base), lambda: st) is st
    if s1 is not None:
        ctx.get(H.MODULE, tf, H.S1_PARAMS, lambda: np.full(len(st), float(s1)))
    return st


def fake_ribbon(n, flips, risk=1.0):
    """A ribbon output with the port's keys (tradeiq2_ind_ribbon.KEYS): the given flips (they must alternate), the
    trend they make, the intended risk ``risk`` on every bar."""
    flip = np.zeros(n, np.int8)
    for b, s in flips.items():
        flip[b] = s
    trend, again = R.side_trend(flip == 1, flip == -1)
    assert np.array_equal(again, flip), "the hand-made flips must alternate"
    out = {k: np.zeros(n) for k in RB.KEYS}
    rl = np.full(n, float(risk))
    out.update(bull_setup=flip == 1, bear_setup=flip == -1, flip=flip, trend=trend, risk_long=rl, risk_short=rl.copy(),
               risk_long_lit=np.where(flip == 1, rl, NAN), risk_short_lit=np.where(flip == -1, rl, NAN),
               alma=np.full(n, NAN), atr=np.ones(n))
    return {k: out[k] for k in RB.KEYS}


def inject_ribbon(ctx, tf, flips, risk=1.0):
    out = fake_ribbon(len(ctx.bars(tf)), flips, risk)
    assert ctx.get(R.MODULE, tf, R.RIBBON_PARAMS, lambda: out) is out
    return out


def run(mk, ex, cost=1.0, start=T0):
    return M.run_exec(mk, ex, start, int(mk.t[-1]) + 60, cost)


def rows(r):
    tr = r.trades
    return [(int(a), int(b), int(c), round(float(d), 9), round(float(e), 9), str(f))
            for a, b, c, d, e, f in zip(tr.side, tr.entry_ix, tr.exit_ix, tr.entry, tr.exit, tr.reason)]


def base_exec(ctx, base):
    """The base alone: study 1's finalist as its state Exec (study 1's run), or the ribbon's own row."""
    if "|RIB|" in base:
        return R.build({v.id: v for v in R.variants(base.split("|")[0])}[base], ctx)
    return M.state_exec(base.split("|")[1], H.study1_state(ctx, base), H.study1_stop(ctx, base))


def no_drops(r):
    return r.counts["dropped_stop"] == 0 and r.counts["dropped_target"] == 0


# ───────────────────────────── (b) M1 and M4: the exits ─────────────────────────────

def test_b_m1_exits_a_long_at_a_flip_to_bearish_not_in_favour_nor_on_the_entry_bar_then_waits_for_the_base():
    n = 14
    mk = market(flat(60 * n))
    ctx = M.Context(mk)
    st = inject_base(ctx, LA, [0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0])
    # flips: bar 2 to bullish (in favour), 4 to bearish, 6 bullish, 7 bearish (the second long's entry bar), 9
    # bullish, 10 bearish, 12 bullish
    inject_ha(ctx, "1H", fake_ha(n, [-1, -1, 1, 1, -1, -1, 1, -1, -1, 1, -1, -1, 1, 1]))
    ex = H.build(managed("XAUUSDm", "M1", LA), ctx)
    assert ex.kind == "state" and ex.overlays and ex.stop is None and np.array_equal(ex.state, st)
    assert list(np.flatnonzero(ex.exit_long)) == [4, 7, 10] and list(np.flatnonzero(ex.exit_short)) == [2, 6, 9, 12]
    assert ex.tighten_long is None and ex.tighten_short is None and ex.tighten_be is None
    r = run(mk, ex)
    # the first long is out at bar 4's close (minute 300); the base stays +1 on bar 5: flat until it changes; the
    # second long enters at bar 7's close although bar 7 flipped bearish (not acted on) and leaves at bar 10's flip
    assert rows(r) == [(1, 120, 300, 100.2, 100.0, "signal"), (1, 480, 660, 100.2, 100.0, "signal")]
    assert r.counts["taken"] == 2 and r.counts["busy"] == 0 and no_drops(r)
    assert rows(run(mk, base_exec(ctx, LA))) == [(1, 120, 420, 100.2, 100.0, "signal"),
                                                 (1, 480, 780, 100.2, 100.0, "signal")]


def test_b_m1_exits_a_short_at_a_flip_to_bullish():
    mk = market(btc_days(8), sp=10.0, symbol="BTCUSDm")
    ctx = M.Context(mk)
    assert len(ctx.bars("1D")) == 8
    inject_base(ctx, VW, [0, -1, -1, -1, -1, 0, 0, 0], s1=1000.0)
    inject_ha(ctx, "1D", fake_ha(8, [1, 1, -1, 1, 1, 1, 1, 1]))                 # day 2 bearish (in favour), day 3 up
    r = run(mk, H.build(managed("BTCUSDm", "M1", VW), ctx))
    assert rows(r) == [(-1, 2880, 5760, 20000.0, 20010.0, "signal")]           # sold at the bid, bought at the ask
    assert np.allclose(r.trades.risk, 1000.0)                                  # R from study 1's S1
    assert rows(run(mk, base_exec(ctx, VW))) == [(-1, 2880, 8640, 20000.0, 20010.0, "signal")]


def test_b_m4_exits_when_a_streak_of_the_positions_colour_reaches_its_rare_age():
    n = 12
    mk = market(flat(60 * n))
    ctx = M.Context(mk)
    inject_base(ctx, LA, [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0])
    # a bearish streak's rare age at bar 3 (the other colour: nothing), a bullish one's at bar 6
    inject_ha(ctx, "1H", fake_ha(n, [-1] * 4 + [1] * 8, rare=(3, 6)))
    ex = H.build(managed("XAUUSDm", "M4", LA), ctx)
    assert list(np.flatnonzero(ex.exit_long)) == [6] and list(np.flatnonzero(ex.exit_short)) == [3]
    assert rows(run(mk, ex)) == [(1, 120, 420, 100.2, 100.0, "signal")]


def test_b_m4_on_a_short_and_m1_m4_on_the_ribbon_bases():
    mk = market(btc_days(8), sp=10.0, symbol="BTCUSDm")
    ctx = M.Context(mk)
    inject_base(ctx, VW, [0, -1, -1, -1, -1, -1, 0, 0], s1=1000.0)
    inject_ha(ctx, "1D", fake_ha(8, [1, -1, -1, -1, -1, -1, -1, -1], rare=(4,)))
    assert rows(run(mk, H.build(managed("BTCUSDm", "M4", VW), ctx))) == [(-1, 2880, 7200, 20000.0, 20010.0,
                                                                          "signal")]
    # the ribbon: a bull flip at bar 1 and a bear flip at bar 6 (RIB-LS: long, then short); HA flips bearish at
    # bar 3 (the long is out, flat until the bear flip) and bullish at bar 9 (the short is out)
    n = 12
    mk = market(flat(60 * n))
    ctx = M.Context(mk)
    inject_ribbon(ctx, "1H", {1: 1, 6: -1})
    inject_ha(ctx, "1H", fake_ha(n, [1, 1, 1, -1, -1, -1, -1, -1, -1, 1, 1, 1], rare=(2,)))
    ls = "XAUUSDm|1H|RIB|LS|X0|F0"
    ex = H.build(managed("XAUUSDm", "M1", ls), ctx)
    assert ex.kind == "events" and list(ex.entries.bar) == [1, 6]
    assert list(np.flatnonzero(ex.exit_long)) == [3, 6] and list(np.flatnonzero(ex.exit_short)) == [1, 9]
    assert rows(run(mk, ex)) == [(1, 120, 240, 100.2, 100.0, "signal"), (-1, 420, 600, 100.0, 100.2, "signal")]
    assert rows(run(mk, base_exec(ctx, ls))) == [(1, 120, 420, 100.2, 100.0, "signal"),
                                                 (-1, 420, 719, 100.0, 100.2, "end")]
    lo = "XAUUSDm|1H|RIB|LO|X0|F0"                                              # M4: the bullish rare age at bar 2
    ex = H.build(managed("XAUUSDm", "M4", lo), ctx)
    assert ex.exit_short is None and list(ex.entries.bar) == [1]
    assert rows(run(mk, ex)) == [(1, 120, 180, 100.2, 100.0, "signal")]


# ───────────────────────────── (b) M2, M3, M5: the tightenings (PREREG 4's absolute-level rules) ─────────────────

def m2_case(bars, dirs=None, n=12):
    mk = market(bars)
    ctx = M.Context(mk)
    inject_base(ctx, LA, [0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0])
    inject_ha(ctx, "1H", fake_ha(n, [1] * n if dirs is None else dirs, ind=(4,)))
    return mk, ctx, H.build(managed("XAUUSDm", "M2", LA), ctx)


def test_b_m2_raises_the_stop_to_the_bars_low_when_it_is_above_break_even_and_below_the_bid():
    bars = flat(720)
    level(bars, 240, 300, 101.0)                     # bar 4, the INDECISION candle: low 100.98
    level(bars, 300, 420, 101.5)                     # the open that executes the tightening: bid 101.5 > 100.98
    bars[2][350] = 100.9                             # reaches the new stop at minute 350
    mk, ctx, ex = m2_case(bars)
    assert list(np.flatnonzero(np.isfinite(ex.tighten_long))) == [4] and ex.tighten_long[4] == pytest.approx(100.98)
    assert list(np.flatnonzero(ex.tighten_be)) == [4] and np.isnan(ex.tighten_short).all()
    assert ex.exit_long is None and ex.exit_short is None
    r = run(mk, ex)
    # the stop fills at its level, one extra spread is charged: 100.98 - 0.2
    assert rows(r) == [(1, 120, 350, 100.2, 100.78, "stop")]
    assert r.counts["tighten_rows"] == 1 and r.counts["tighten_exits"] == 0 and no_drops(r)
    assert rows(run(mk, base_exec(ctx, LA))) == [(1, 120, 600, 100.2, 100.0, "signal")]


def test_b_m2_a_level_the_bid_has_already_crossed_is_a_market_exit_at_that_open():
    bars = flat(720)
    level(bars, 240, 300, 101.0)                     # the level 100.98 ...
    level(bars, 300, 420, 100.5)                     # ... is above the bid 100.5 at minute 300
    mk, ctx, ex = m2_case(bars)
    r = run(mk, ex)
    assert rows(r) == [(1, 120, 300, 100.2, 100.5, "signal")]                 # no extra spread: a market exit
    assert r.counts["tighten_exits"] == 1 and r.counts["tighten_rows"] == 0


def test_b_m2_break_even_is_the_runs_own_fill_at_both_costs():
    bars = flat(720)
    level(bars, 240, 300, 100.1)                     # the bar's low 100.08 is below the fill: break-even binds
    level(bars, 300, 420, 100.25)
    bars[2][350] = 100.1
    mk, ctx, ex = m2_case(bars)
    # x1.0: filled at 100.2, the stop moves to 100.2 (below the bid 100.25) and is hit at minute 350
    assert rows(run(mk, ex, 1.0)) == [(1, 120, 350, 100.2, 100.0, "stop")]
    # x1.5: filled at 100.3, break-even 100.3 is above the bid 100.25: a market exit at minute 300
    r15 = run(mk, ex, 1.5)
    assert rows(r15) == [(1, 120, 300, 100.3, 100.25, "signal")] and r15.counts["tighten_exits"] == 1


def test_b_m2_ignores_the_other_colours_indecision():
    bars = flat(720)
    level(bars, 240, 300, 101.0)
    level(bars, 300, 420, 101.5)
    bars[2][350] = 100.9
    mk, ctx, ex = m2_case(bars, dirs=[1, 1, -1, -1, -1, -1, -1, 1, 1, 1, 1, 1])   # bar 4 is a bearish candle
    assert np.isnan(ex.tighten_long).all() and list(np.flatnonzero(np.isfinite(ex.tighten_short))) == [4]
    assert ex.tighten_short[4] == pytest.approx(101.02)                          # a short's level: the bar's high
    assert rows(run(mk, ex)) == [(1, 120, 600, 100.2, 100.0, "signal")]       # the long is left alone


def test_b_m2_on_a_short_with_study_1s_s1_tightens_from_the_fill_and_the_ask_reaches_it():
    days = 10
    bars = btc_days(days)
    level(bars, 3 * 1440, days * 1440, 19900.0, 1.0)  # from day 3 on at 19 900 (high 19 901)
    bars[1][4500] = 19950.0                           # day 3's high: the INDECISION candle's level 19 950
    bars[1][8800] = 19945.0                           # day 6: the ask high 19 955 reaches the new stop
    mk = market(bars, sp=10.0, symbol="BTCUSDm")
    ctx = M.Context(mk)
    inject_base(ctx, VW, [0, -1, -1, -1, -1, -1, -1, -1, 0, 0], s1=50.0)      # S1: 20 000 + 50
    inject_ha(ctx, "1D", fake_ha(days, [-1] * days, ind=(3,)))
    ex = H.build(managed("BTCUSDm", "M2", VW), ctx)
    assert ex.tighten_short[3] == pytest.approx(19950.0) and np.isnan(ex.tighten_long).all()
    r = run(mk, ex)
    # min(fill 20 000, 19 950) = 19 950 lies above the ask 19 910 at day 4's open: the new stop; the stop fills at
    # its level and one spread is charged (19 950 + 10)
    assert rows(r) == [(-1, 2880, 8800, 20000.0, 19960.0, "stop")]
    assert np.allclose(r.trades.risk, 50.0) and r.counts["tighten_rows"] == 1
    assert rows(run(mk, base_exec(ctx, VW))) == [(-1, 2880, 12960, 20000.0, 19910.0, "signal")]


def test_b_m3_tightens_from_the_second_weak_candle_in_a_row_of_the_positions_colour_and_at_each_one_after():
    n = 12
    bars = flat(60 * n)
    level(bars, 240, 300, 101.0)                     # bar 4: the second WEAK candle in a row, low 100.98
    level(bars, 300, 360, 101.5)                     # bar 5: the third, low 101.48
    level(bars, 360, 720, 102.0)
    bars[2][400] = 101.3                             # below 101.48 (the third's level), above 100.98 (the second's)
    mk = market(bars)
    ctx = M.Context(mk)
    inject_base(ctx, LA, [0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0])
    inject_ha(ctx, "1H", fake_ha(n, [1] * 8 + [-1] * 4, weak={3: 1, 4: 2, 5: 3, 10: 2}))
    ex = H.build(managed("XAUUSDm", "M3", LA), ctx)
    assert list(np.flatnonzero(np.isfinite(ex.tighten_long))) == [4, 5]          # a run of 1 does not count
    assert list(np.flatnonzero(np.isfinite(ex.tighten_short))) == [10]           # a bearish pair: shorts only
    assert list(np.flatnonzero(ex.tighten_be)) == [4, 5, 10]
    r = run(mk, ex)
    assert rows(r) == [(1, 120, 400, 100.2, 101.28, "stop")]                  # 101.48 - one spread
    assert r.counts["tighten_rows"] == 2


def test_b_m5_is_m1_plus_m2():
    n = 12
    bars = flat(60 * n)
    level(bars, 180, 240, 101.0)                     # bar 3: INDECISION after STRONG, low 100.98
    level(bars, 240, 720, 101.5)
    mk = market(bars)
    ctx = M.Context(mk)
    inject_base(ctx, LA, [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0])
    inject_ha(ctx, "1H", fake_ha(n, [1] * 6 + [-1] * 6, ind=(3,)))
    m1, m2, m5 = (H.build(managed("XAUUSDm", o, LA), ctx) for o in ("M1", "M2", "M5"))
    for k in ("exit_long", "exit_short"):
        assert np.array_equal(getattr(m5, k), getattr(m1, k)) and getattr(m2, k) is None
    for k in ("tighten_long", "tighten_short", "tighten_be"):
        assert np.array_equal(getattr(m5, k), getattr(m2, k), equal_nan=k != "tighten_be") and getattr(m1, k) is None
    r5 = run(mk, m5)
    assert rows(r5) == [(1, 120, 420, 100.2, 101.5, "signal")] and r5.counts["tighten_rows"] == 1
    assert rows(run(mk, m1)) == rows(r5) and run(mk, m1).counts["tighten_rows"] == 0
    assert rows(run(mk, m2)) == [(1, 120, 660, 100.2, 101.5, "signal")]


def test_b_m2_on_a_ribbon_short_and_no_entry_is_ever_dropped():
    n = 12
    bars = flat(60 * n)
    level(bars, 480, 540, 99.0)                      # bar 8 (bearish INDECISION): high 99.02
    level(bars, 540, 720, 98.5)                      # the ask 98.7 at minute 540 is below 99.02: the new stop
    bars[1][650] = 99.0                              # the ask high 99.2 reaches it
    mk = market(bars)
    ctx = M.Context(mk)
    inject_ribbon(ctx, "1H", {1: 1, 6: -1})
    inject_ha(ctx, "1H", fake_ha(n, [1, 1, 1] + [-1] * 9, ind=(8,)))
    r = run(mk, H.build(managed("XAUUSDm", "M2", "XAUUSDm|1H|RIB|LS|X0|F0"), ctx))
    assert rows(r) == [(1, 120, 420, 100.2, 100.0, "signal"), (-1, 420, 650, 100.0, 99.22, "stop")]
    assert np.allclose(r.trades.risk, 1.0) and r.counts["tighten_rows"] == 1 and no_drops(r)


# ───────────────────────────── (b) HA-AND: the entry gate ─────────────────────────────

def test_b_ha_and_on_a_state_base_takes_an_episode_only_when_its_first_bar_has_the_colour():
    n = 14
    mk = market(flat(60 * n))
    ctx = M.Context(mk)
    base = inject_base(ctx, LA, [0, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 0])
    dirs = [-1, -1, 1, 1, 1, 1, -1, -1, -1, -1, 1, 1, 1, 1]
    inject_ha(ctx, "1H", fake_ha(n, dirs))
    ex = H.build(managed("XAUUSDm", "HA-AND", LA), ctx)
    # episode 1 (bars 1-3) starts on a bearish candle: refused, also later when the colour agrees (bar 2); episode 2
    # (bars 5-8) starts bullish: taken, and the bearish candles from bar 6 do not close it; episode 3 taken
    assert ex.kind == "state" and not ex.overlays and ex.stop is None
    assert list(ex.state) == [0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 0]
    assert np.array_equal(ex.state, H.and_state(base, dirs))
    want = [(1, 360, 600, 100.2, 100.0, "signal"), (1, 660, 780, 100.2, 100.0, "signal")]
    assert rows(run(mk, ex)) == want
    b = rows(run(mk, base_exec(ctx, LA)))
    assert b == [(1, 120, 300, 100.2, 100.0, "signal")] + want and set(want) <= set(b)      # a subset of the base's
    # a window that starts inside a taken episode takes it (as the continuous rule holds it), one inside a refused
    # episode does not
    assert rows(run(mk, ex, start=T0 + 420 * 60)) == [(1, 480, 600, 100.2, 100.0, "signal")] + want[1:]
    assert rows(run(mk, ex, start=T0 + 120 * 60)) == want


def test_b_ha_and_on_a_both_sided_state_base_needs_the_bearish_colour_for_a_short():
    days = 12
    mk = market(btc_days(days), sp=10.0, symbol="BTCUSDm")
    ctx = M.Context(mk)
    inject_base(ctx, VW, [0, -1, -1, 0, 1, 1, 0, -1, -1, 0, 0, 0], s1=1000.0)
    inject_ha(ctx, "1D", fake_ha(days, [1, -1, -1, -1, -1, 1, 1, 1, -1, -1, -1, -1]))
    ex = H.build(managed("BTCUSDm", "HA-AND", VW), ctx)
    assert list(ex.state) == [0, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0] and np.allclose(ex.stop, 1000.0)
    assert rows(run(mk, ex)) == [(-1, 2880, 5760, 20000.0, 20010.0, "signal")]


def test_b_ha_and_on_a_ribbon_base_gates_the_flip_at_its_close():
    n = 12
    mk = market(flat(60 * n))
    ctx = M.Context(mk)
    inject_ribbon(ctx, "1H", {1: 1, 4: -1, 7: 1})
    inject_ha(ctx, "1H", fake_ha(n, [-1] * 7 + [1] * 5))      # bull flip on a bearish candle: refused
    ls = H.build(managed("XAUUSDm", "HA-AND", "XAUUSDm|1H|RIB|LS|X0|F0"), ctx)
    assert ls.kind == "events" and list(ls.entries.bar) == [4, 7] and list(ls.entries.side) == [-1, 1]
    assert ls.tighten_long is None and list(np.flatnonzero(ls.exit_short)) == [1, 7]
    assert rows(run(mk, ls)) == [(-1, 300, 480, 100.0, 100.2, "signal"), (1, 480, 719, 100.2, 100.0, "end")]
    lo = H.build(managed("XAUUSDm", "HA-AND", "XAUUSDm|1H|RIB|LO|X0|F0"), ctx)
    assert rows(run(mk, lo)) == [(1, 480, 719, 100.2, 100.0, "end")]


# ───────────────────────────── (b) HA-H1 and HA-H2: the entry controls ─────────────────────────────

H_DIRS = [1, 1, 1, 1, -1, -1, -1, -1, 1, 1, 1, -1, -1, -1]       # flips at bars 4, 8, 11
H_STRONG = (2, 4, 10)        # first STRONG candles: bar 2, the flip candle 4, bar 10; none in the streak from bar 11


def h_ctx(n=14):
    mk = market(flat(60 * n))
    ctx = M.Context(mk)
    inject_ha(ctx, "1H", fake_ha(n, H_DIRS, strong=H_STRONG))
    return mk, ctx


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


def test_b_ha_h1_is_in_from_the_first_strong_candle_of_a_streak_and_out_at_the_flip():
    mk, ctx = h_ctx()
    h = H.ha_of(ctx, "1H")
    assert list(H.h1_state(h)) == [0, 0, 1, 1, -1, -1, -1, -1, 0, 0, 1, 0, 0, 0]
    ls = H.build(V("XAUUSDm|1H|HA-ENTRY|HA-H1|LS|F0"), ctx)
    assert ls.kind == "state" and not ls.overlays and ls.stop is None
    r = run(mk, ls)
    # in at bar 2's close; the STRONG flip candle of bar 4 reverses at once; out at the flip of bar 8 (not STRONG);
    # in at bar 10, out at the flip of bar 11; the last streak has no STRONG candle
    assert rows(r) == [(1, 180, 300, 100.2, 100.0, "signal"), (-1, 300, 540, 100.0, 100.2, "signal"),
                       (1, 660, 720, 100.2, 100.0, "signal")]
    assert r.trades.risk.isna().all() and not set(r.trades.reason) & {"stop", "gap stop"}
    lo = H.build(V("XAUUSDm|1H|HA-ENTRY|HA-H1|LO|F0"), ctx)
    assert list(lo.state) == [0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]
    assert rows(run(mk, lo)) == [(1, 180, 300, 100.2, 100.0, "signal"), (1, 660, 720, 100.2, 100.0, "signal")]


def test_b_ha_h2_is_the_colour_stop_and_reverse():
    mk, ctx = h_ctx()
    ls = H.build(V("XAUUSDm|1H|HA-ENTRY|HA-H2|LS|F0"), ctx)
    assert list(ls.state) == H_DIRS and ls.stop is None
    # the window's first bar takes the state (study 1's DEVIATIONS 2), then a reversal at every flip
    assert rows(run(mk, ls)) == [(1, 60, 300, 100.2, 100.0, "signal"), (-1, 300, 540, 100.0, 100.2, "signal"),
                                 (1, 540, 720, 100.2, 100.0, "signal"), (-1, 720, 839, 100.0, 100.2, "end")]
    lo = H.build(V("XAUUSDm|1H|HA-ENTRY|HA-H2|LO|F0"), ctx)
    assert rows(run(mk, lo)) == [(1, 60, 300, 100.2, 100.0, "signal"), (1, 540, 720, 100.2, 100.0, "signal")]


def test_b_the_entry_rules_filter_is_a_state_filter():
    """PREREG 5 on a state rule: a state the filter does not allow is flat, so the position closes when the filter
    turns against it and opens where it turns in favour (here mid-streak, on a candle that is not STRONG)."""
    mk, ctx = h_ctx()
    n = 14
    al, ash = np.ones(n, bool), np.ones(n, bool)
    al[2] = False                                     # the first STRONG candle of bar 2 is refused: in at bar 3
    ash[6] = False                                    # the short is closed at bar 6 and reopened at bar 7
    al[10] = False                                    # the third long never opens
    asked = masks(ctx, {"F2-4H": (al, ash)})
    ex = H.build(V("XAUUSDm|1H|HA-ENTRY|HA-H1|LS|F2-4H"), ctx)
    assert asked == [("1H", "F2-4H")]
    assert list(ex.state) == [0, 0, 0, 1, -1, -1, 0, -1, 0, 0, 0, 0, 0, 0]
    assert rows(run(mk, ex)) == [(1, 240, 300, 100.2, 100.0, "signal"), (-1, 300, 420, 100.0, 100.2, "signal"),
                                 (-1, 480, 540, 100.0, 100.2, "signal")]
    h2 = H.build(V("XAUUSDm|1H|HA-ENTRY|HA-H2|LO|F2-4H"), ctx)
    assert list(h2.state) == [1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0]


# ───────────────────────────── (c) filters ─────────────────────────────

def test_c_each_row_asks_exactly_its_filters():
    for s in SYMS:
        mk = market(flat(3 * 1440), symbol=s)
        ctx = M.Context(mk)
        for tf in TFS:
            n = len(ctx.bars(tf))
            inject_ha(ctx, tf, fake_ha(n, [1] * n))
            inject_ribbon(ctx, tf, {})
        for b in H.STUDY1_FINALISTS[s]:
            n = len(ctx.bars(b.split("|")[1]))
            inject_base(ctx, b, np.zeros(n, np.int8), s1=1.0)
        asked = masks(ctx, {})
        for v in H.variants(s):
            del asked[:]
            H.build(v, ctx)
            assert all(tf == v.tf for tf, _ in asked), v.id
            names = {name for _, name in asked}
            if v.family == "HA-ENTRY":
                assert names == {v.params["filter"]}, (v.id, names)
            elif "|RIB|" in v.params["base"]:
                assert names == {"F0"}, (v.id, names)                 # the ribbon base's own F0
            else:
                assert names == set(), (v.id, names)                  # study 1's filter: study 1's own functions


# ───────────────────────────── (d) the real port, read as the docstring says ─────────────────────────────

def walk(days=40, seed=5, symbol="XAUUSDm", p0=2000.0, vol=0.3, start="2019-01-07"):
    """Around the clock, a random walk with day-long trends, so that the candles flip, run and stall on every
    timeframe."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    drift = np.repeat(rng.normal(0.0, 0.1 * vol, n // 1440 + 1), 1440)[:n]
    c = p0 + np.cumsum(drift + rng.normal(0.0, vol, n))
    o = np.concatenate(([p0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5 * vol, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5 * vol, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(n, 0.2), "n": np.ones(n)}


def test_d_the_overlays_and_the_entry_states_are_the_ports_events_of_the_positions_colour():
    ctx = M.Context(M.TMarket2("XAUUSDm", walk()))
    seen = {"ind": 0, "weak2": 0, "rare": 0, "flip": 0, "strong": 0}
    for tf in TFS:
        b = ctx.bars(tf)
        h = HA.heikin_ashi(b.o, b.h, b.l, b.c)                    # the port itself, computed again
        got = H.ha_of(ctx, tf)
        for k in got:
            assert np.array_equal(got[k], h[k], equal_nan=True) and not got[k].flags.writeable
        n = len(b)
        ov = {o: H.overlay_arrays(ctx, tf, o) for o in H.EXIT_OVERLAYS}
        gl, gs = H.colour_gate(ctx, tf)
        seen_strong, h1 = False, []
        for t in range(n):
            d = int(h["dir"][t])
            fl, ind, wr, rare = bool(h["flip"][t]), bool(h["ev_ind"][t]), int(h["weak_run"][t]), bool(h["rare_now"][t])
            seen["flip"] += fl
            seen["ind"] += ind
            seen["weak2"] += wr == 2
            seen["rare"] += rare
            for o in ("M1", "M5"):
                assert ov[o]["exit_long"][t] == (fl and d == -1) and ov[o]["exit_short"][t] == (fl and d == 1)
            assert ov["M4"]["exit_long"][t] == (rare and d == 1) and ov["M4"]["exit_short"][t] == (rare and d == -1)
            for o, trig in (("M2", ind), ("M5", ind), ("M3", wr >= 2)):
                tl, ts, be = ov[o]["tighten_long"][t], ov[o]["tighten_short"][t], ov[o]["tighten_be"][t]
                assert (tl == b.l[t]) if (trig and d == 1) else np.isnan(tl)
                assert (ts == b.h[t]) if (trig and d == -1) else np.isnan(ts)
                assert be == trig
            for o in ("M2", "M3"):
                assert ov[o]["exit_long"] is None and ov[o]["exit_short"] is None
            for o in ("M1", "M4"):
                assert ov[o]["tighten_long"] is None and ov[o]["tighten_be"] is None
            assert gl[t] == (d == 1) and gs[t] == (d == -1)
            if t == 0 or fl:                                       # a plain loop for HA-H1
                seen_strong = False
            if h["ev_first_strong"][t]:
                seen_strong = True
                seen["strong"] += 1
            h1.append(d if seen_strong else 0)
            if ind:                                                # the port's facts the reading rests on
                assert not fl and b.l[t] == h["ha_l"][t] and b.h[t] == h["ha_h"][t]
            if wr >= 2:
                assert not fl and (b.l[t] == h["ha_l"][t] if d == 1 else b.h[t] == h["ha_h"][t])
        assert list(H.h1_state(h)) == h1
        for side in ("LS", "LO"):
            for f in ("F0", F2_OF[tf]):
                al, ash = ctx.allow(tf, f)
                for rule, raw in (("HA-H1", np.asarray(h1)), ("HA-H2", h["dir"].astype(np.int64))):
                    if side == "LO":
                        raw = np.where(raw == 1, 1, 0)
                    want = np.where((raw == 1) & al, 1, np.where((raw == -1) & ash, -1, 0))
                    st = H.entry_state(ctx, tf, rule, side, f)
                    assert np.array_equal(st, want) and not st.flags.writeable
    assert min(seen.values()) > 0, seen                            # the case is not empty


def test_d_and_state_against_a_plain_loop():
    rng = np.random.default_rng(17)
    for _ in range(200):
        n = int(rng.integers(0, 60))
        st = rng.choice([-1, 0, 1], n, p=[0.3, 0.3, 0.4])
        st = np.repeat(st, rng.integers(1, 4, n))[:n] if n else st
        col = rng.choice([-1, 1], len(st))
        want, ok = [], False
        for t in range(len(st)):
            if st[t] != 0 and (t == 0 or st[t] != st[t - 1]):
                ok = col[t] == st[t]
            want.append(int(st[t]) if (st[t] != 0 and ok) else 0)
        got = H.and_state(st, col)
        assert got.dtype == np.int8 and list(got) == want
    with pytest.raises(ValueError):
        H.and_state([1, 0], [1])


# ───────────────────────────── (e) the bases, and one trade per event ─────────────────────────────

def synth_m1(symbol, days=450, seed=3, start="2018-03-05"):
    """Around the clock, a random walk with two-day trends (the filters' test market), so that the bases change
    state, the ribbon flips and the MA200s change sides on every timeframe."""
    rng = np.random.default_rng(seed)
    p0, vol, sp = (20000.0, 2.0, 10.0) if symbol == "BTCUSDm" else (1300.0, 0.15, 0.2)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    drift = np.repeat(rng.normal(0.0, 0.015 * vol, n // 2880 + 1), 2880)[:n]
    c = p0 + np.cumsum(drift + rng.normal(0.0, vol, n))
    o = np.concatenate(([p0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.5 * vol, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.5 * vol, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(n, sp), "n": rng.integers(1, 9, n) * 1.0}


def binance_files_present(end="2019-07-01"):
    return all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.s_of(end))


@pytest.fixture(scope="module", params=SYMS)
def synth(request):
    """One symbol's synthetic market and Context (BTC's study-1 lines read Binance's 1h klines of those dates, study
    1's VWRSI-RV line: skipped without them)."""
    sym = request.param
    if sym == "BTCUSDm" and not binance_files_present():
        pytest.skip("the Binance 1h klines are not on this machine")
    m1 = synth_m1(sym)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        mp.setattr(TM, "STUDY_DIR", TM.STUDY_DIR.parent / "__no_such_study_1__")
        ctx = M.Context(M.TMarket2(sym, m1))
    yield sym, ctx, m1
    del ctx
    gc.collect()


def test_e_study_1s_bases_are_study_1s_states_and_stops_and_the_overlays_keep_them(synth):
    sym, ctx, _ = synth
    st1 = T1.Study(ctx.mk)                                         # study 1's own composition, on the same market
    for base in H.STUDY1_FINALISTS[sym]:
        v1 = T1.Variant.of(base)
        st = H.study1_state(ctx, base)
        assert np.array_equal(st, st1.state(v1)) and not st.flags.writeable
        assert (st == 1).any() and ((st == -1).any() == (v1.family == "R3")), base
        stop = H.study1_stop(ctx, base)
        assert (stop is None) == (v1.stop == "S0")
        if stop is not None:
            assert np.array_equal(stop, st1.stops[v1.tf], equal_nan=True)
        for o in H.OVERLAYS:
            ex = H.build(managed(sym, o, base), ctx)
            assert ex.kind == "state" and ex.tf == v1.tf and ex.label.endswith(H.base_token(base))
            if stop is None:
                assert ex.stop is None
            else:
                assert np.array_equal(ex.stop, stop, equal_nan=True)
            want = H.and_state(st, H.ha_of(ctx, v1.tf)["dir"]) if o == "HA-AND" else st
            assert np.array_equal(ex.state, want), (base, o)
            assert ex.overlays == (o != "HA-AND")


def test_e_the_ribbon_bases_are_the_ribbons_rows_with_the_overlays_added(synth):
    sym, ctx, _ = synth
    refused = 0
    for tf in TFS:
        for side in ("LS", "LO"):
            base = f"{sym}|{tf}|RIB|{side}|X0|F0"
            b0 = base_exec(ctx, base)
            gl, gs = H.colour_gate(ctx, tf)
            for o in H.OVERLAYS:
                ex = H.build(managed(sym, o, base), ctx)
                assert ex.kind == "events" and len(ex.legs) == 1
                E, E0 = ex.entries, b0.entries
                if o == "HA-AND":
                    keep = np.where(E0.side == 1, gl[E0.bar], gs[E0.bar])
                    assert keep.sum() > 0
                    refused += int((~keep).sum())
                    for k in ("bar", "side", "stop_dist", "tag"):
                        assert np.array_equal(getattr(E, k), getattr(E0, k)[keep])
                    assert np.array_equal(ex.exit_long, b0.exit_long)
                    continue
                for k in ("bar", "side", "stop_dist", "tag", "target_r", "be_r", "exit_bar"):
                    assert np.array_equal(getattr(E, k), getattr(E0, k), equal_nan=True)
                ov = H.overlay_arrays(ctx, tf, o)
                xl = b0.exit_long if ov["exit_long"] is None else b0.exit_long | ov["exit_long"]
                assert np.array_equal(ex.exit_long, xl)
                if side == "LS":
                    xs = b0.exit_short if ov["exit_short"] is None else b0.exit_short | ov["exit_short"]
                    assert np.array_equal(ex.exit_short, xs)
                else:
                    assert ex.exit_short is None and ex.tighten_short is None
                if ov["tighten_long"] is not None:
                    assert np.array_equal(ex.tighten_long, ov["tighten_long"], equal_nan=True)
                    assert np.array_equal(ex.tighten_be, ov["tighten_be"])
                    if side == "LS":
                        assert np.array_equal(ex.tighten_short, ov["tighten_short"], equal_nan=True)
    assert refused > 0                                # the gate refuses some flips (not a vacuous check)


WIN = ("2019-01-01", "2019-05-20")


def test_e_every_overlay_row_keeps_its_bases_entries_and_ha_and_a_subset_of_its_trades(synth):
    """The trades' times and sides only (no profit or loss): M1-M5 take exactly the base's entries (after a Heikin
    Ashi exit the base waits for its own next entry) and end no later than the base's trade; HA-AND's trades are
    some of the base's trades, unchanged."""
    sym, ctx, _ = synth
    acted = {o: 0 for o in H.OVERLAYS}
    n_base = 0
    for base in H.bases(sym):
        b0 = M.run_exec(ctx.mk, base_exec(ctx, base), *WIN)
        t0 = b0.trades
        key0 = list(zip(t0.entry_ix, t0.exit_ix, t0.side, t0.reason))
        n_base += len(t0)
        if base.split("|")[1] != "1D":
            assert len(t0) > 0, base
        for o in H.OVERLAYS:
            r = M.run_exec(ctx.mk, H.build(managed(sym, o, base), ctx), *WIN)
            tr = r.trades
            assert no_drops(r) and r.counts["busy"] == 0
            if o == "HA-AND":
                key = list(zip(tr.entry_ix, tr.exit_ix, tr.side, tr.reason))
                assert set(key) <= set(key0), (base, o)
                acted[o] += len(key0) - len(key)
                continue
            assert np.array_equal(tr.entry_ix.to_numpy(), t0.entry_ix.to_numpy()), (base, o)
            assert np.array_equal(tr.side.to_numpy(), t0.side.to_numpy())
            assert (tr.exit_ix.to_numpy() <= t0.exit_ix.to_numpy()).all(), (base, o)
            acted[o] += int((tr.exit_ix.to_numpy() < t0.exit_ix.to_numpy()).sum())
            acted[o] += r.counts["tighten_rows"] + r.counts["tighten_exits"]
            assert set(tr.reason) <= {"signal", "stop", "gap stop", "end"}
    assert n_base > 50 and min(acted.values()) > 0, acted          # every overlay changes some trade


def test_e_ha_h1_takes_one_trade_per_streak_from_its_first_strong_candle_and_ha_h2_one_from_its_flip(synth):
    sym, ctx, _ = synth
    a_s = TM.s_of(WIN[0])
    for tf in TFS:
        b = ctx.bars(tf)
        h = H.ha_of(ctx, tf)
        streak = np.cumsum(h["flip"])
        for rule in ("HA-H1", "HA-H2"):
            for side in ("LS", "LO"):
                r = M.run_exec(ctx.mk, H.build(V(f"{sym}|{tf}|HA-ENTRY|{rule}|{side}|F0"), ctx), *WIN)
                tr = r.trades
                if tf != "1D":
                    assert len(tr) > 10
                bar = tr.bar.to_numpy()
                first = b.tc[np.maximum(bar - 1, 0)] <= a_s                  # the window's first bar
                assert np.array_equal(tr.entry_ix.to_numpy(), b.ex[bar])     # filled at the next M1 open
                assert np.array_equal(tr.side.to_numpy(), h["dir"][bar].astype(np.int64))
                at = h["ev_first_strong"][bar] if rule == "HA-H1" else h["flip"][bar]
                assert (at | first).all(), (tf, rule, side)
                assert len(set(streak[bar])) == len(bar)                     # one trade per streak
                if side == "LO":
                    assert (tr.side == 1).all()
                assert tr.risk.isna().all() and set(tr.reason) <= {"signal", "end"}


# ───────────────────────────── (f) causality ─────────────────────────────

def decisions(ctx, v, upto_s):
    """Every decision a row takes at bars closing at or before ``upto_s``: the state and the stop (state rows), the
    entries (ribbon bases), the per-bar exits and the tightenings."""
    ex = H.build(v, ctx)
    b = ctx.bars(v.tf)
    keep = b.tc <= upto_s
    out = {}
    for k in ("exit_long", "exit_short", "tighten_long", "tighten_short", "tighten_be"):
        a = getattr(ex, k)
        out[k] = np.zeros(0) if a is None else np.asarray(a)[keep]
    if ex.kind == "state":
        out["state"] = ex.state[keep]
        out["stop"] = np.zeros(0) if ex.stop is None else np.asarray(ex.stop)[keep]
    else:
        E = ex.entries
        m = b.tc[E.bar] <= upto_s
        out.update({f"entries.{k}": getattr(E, k)[m] for k in E.__dataclass_fields__})
    return out


def same_decisions(full, part, symbol, upto_s):
    for tf in TFS:
        bf, bp = full.bars(tf), part.bars(tf)
        k = int((bp.tc <= upto_s).sum())
        assert k > 0 and int((bf.tc <= upto_s).sum()) == k
        for f in ("t", "tc", "o", "h", "l", "c"):
            assert np.array_equal(getattr(bf, f)[:k], getattr(bp, f)[:k])
    n = 0
    for v in H.variants(symbol):
        a, b = decisions(full, v, upto_s), decisions(part, v, upto_s)
        assert a.keys() == b.keys()
        for key in a:
            assert np.array_equal(a[key], b[key], equal_nan=np.asarray(a[key]).dtype.kind == "f"), (v.id, key)
        n += 1
    return n


def truncated(m1, symbol, cut_s):
    keep = m1["t"] < cut_s
    return M.Context(M.TMarket2(symbol, {k: v[keep] for k, v in m1.items()}))


def cuts_before_events(ctx, after):
    """Cut times that remove a decision a one-bar look-ahead would move: the open of the first bar after ``after`` with
    a Heikin Ashi flip, an INDECISION after STRONG, a WEAK pair, a rare age, a first STRONG candle, or a change of a
    study-1 base's state, on each timeframe."""
    out = set()
    a_s = TM.s_of(after)
    for tf in TFS:
        b = ctx.bars(tf)
        h = H.ha_of(ctx, tf)
        series = [h["flip"], h["ev_ind"], h["weak_run"] >= 2, h["rare_now"], h["ev_first_strong"]]
        for base in H.STUDY1_FINALISTS[ctx.symbol]:
            if base.split("|")[1] == tf:
                st = H.study1_state(ctx, base).astype(np.int64)
                series.append(np.r_[False, st[1:] != st[:-1]])
        for s in series:
            ix = np.flatnonzero(s)
            ix = ix[b.t[ix] > a_s]
            if len(ix):
                out.add(int(b.t[ix[0]]))
    return sorted(out)


def test_f_decisions_up_to_t_do_not_change_when_the_bars_after_t_are_removed(synth):
    sym, full, m1 = synth
    cuts = [TM.s_of("2019-02-15 13:37")] + cuts_before_events(full, "2018-12-01")
    assert len(cuts) >= 10
    for cut in cuts:
        assert same_decisions(full, truncated(m1, sym, cut), sym, cut) == 78


# ───────────────────────────── (g) real data (to 2019-07-01 only) ─────────────────────────────

REAL_END = "2019-07-01"


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cache = {}
    d2, d1 = tmp_path_factory.mktemp("closed_study2"), tmp_path_factory.mktemp("closed_study1")

    def get(symbol, end=REAL_END, keep=True, study1=False):
        """The study's market of ``symbol`` to ``end`` (never past 2019-07-01 here) as a Context (``study1``: study
        1's own market, ``tradeiq_market.load``); ``keep=False``: not cached (the cut markets), so memory holds
        little more than one symbol at a time."""
        key = (symbol, end, study1)
        if key not in cache:
            first = int(M.data_start(symbol)[:4])
            months = store.available_months(symbol)
            if (2019, 6) not in months or (first, 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            if symbol == "BTCUSDm" and not binance_files_present():
                pytest.skip("the Binance 1h klines are not on this machine")
            assert TM.s_of(end) <= TM.s_of(REAL_END)
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(M, "STUDY_DIR", d2)
                mp.setattr(TM, "STUDY_DIR", d1)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                got = TM.load(symbol, end=end) if study1 else M.Context(M.load(symbol, end=end))
            if not keep:
                return got
            cache[key] = got
        return cache[key]
    yield get
    cache.clear()
    gc.collect()


@pytest.mark.parametrize("symbol", SYMS)
def test_g_real_bars_causality(symbol, real):
    full = real(symbol)
    assert full.mk.end_s == TM.s_of(REAL_END)
    assert int(full.bars("1H").t[0]) < TM.s_of(M.data_start(symbol)) + 7 * 86400   # from the study's data start
    part = real(symbol, "2019-04-01", keep=False)
    assert same_decisions(full, part, symbol, TM.s_of("2019-04-01")) == 78
    del part
    b = full.bars("1H")                                # also cut right before a 1H flip and a 1H INDECISION
    for key in ("flip", "ev_ind"):
        ix = np.flatnonzero(H.ha_of(full, "1H")[key])
        cut = int(b.t[ix[b.t[ix] > TM.s_of("2019-05-01")][0]])
        part = real(symbol, str(TM.utc(cut).tz_localize(None)), keep=False)
        assert same_decisions(full, part, symbol, cut) == 78
        del part
    gc.collect()


@pytest.mark.parametrize("symbol", SYMS)
def test_g_study_1s_finalists_on_the_study_2_market_are_study_1s_own_states_in_2019(symbol, real):
    """Study 1's market starts gold in 2017, the study's in 2016 (its warm-up months): on every bar closing after
    2019-01-01 the finalists' states and S1 distances are equal (BTC's markets start together)."""
    ctx, mk1 = real(symbol), real(symbol, study1=True)
    st1 = T1.Study(mk1)
    a_s = TM.s_of("2019-01-01")
    for base in H.STUDY1_FINALISTS[symbol]:
        v1 = T1.Variant.of(base)
        b2, b1 = ctx.bars(v1.tf), st1.bars[v1.tf]
        k = int(np.searchsorted(b2.t, b1.t[0]))
        for f in ("t", "tc", "o", "h", "l", "c", "vol"):
            assert np.array_equal(getattr(b2, f)[k:], getattr(b1, f)), (base, f)
        sel1 = np.flatnonzero(b1.tc > a_s)
        sel2 = sel1 + k
        s2, s1 = H.study1_state(ctx, base)[sel2], st1.state(v1)[sel1]
        assert np.array_equal(s2, s1), base
        assert len(sel1) > 100 and (s1 == 1).any() and (s1 == 0).any()
        if v1.stop == "S1":
            assert np.array_equal(H.study1_stop(ctx, base)[sel2], st1.stops[v1.tf][sel1], equal_nan=True)
    del st1
    gc.collect()


SMOKE = {
    "XAUUSDm": ("XAUUSDm|1H|HA-MANAGED|M1|QQE-R2-F2-4H-S0", "XAUUSDm|1H|HA-MANAGED|M2|LaRSI-R2-F1-S0",
                "XAUUSDm|4H|HA-MANAGED|M3|RSI-R2-F1-S0", "XAUUSDm|1H|HA-MANAGED|M4|RIB-LS-X0-F0",
                "XAUUSDm|4H|HA-MANAGED|M5|RIB-LO-X0-F0", "XAUUSDm|1H|HA-MANAGED|HA-AND|QQE-R2-F2-4H-S0",
                "XAUUSDm|4H|HA-MANAGED|HA-AND|RIB-LS-X0-F0", "XAUUSDm|1H|HA-ENTRY|HA-H1|LS|F2-4H",
                "XAUUSDm|4H|HA-ENTRY|HA-H2|LO|F0", "XAUUSDm|1D|HA-ENTRY|HA-H2|LS|F1"),
    "BTCUSDm": ("BTCUSDm|4H|HA-MANAGED|M1|TSI-R2-F1-S0", "BTCUSDm|1D|HA-MANAGED|M2|VWRSI-R3-F0-S1",
                "BTCUSDm|1D|HA-MANAGED|M3|LaRSI-R2-F3-S1", "BTCUSDm|1H|HA-MANAGED|M4|RIB-LS-X0-F0",
                "BTCUSDm|1H|HA-MANAGED|M5|RIB-LS-X0-F0", "BTCUSDm|1D|HA-MANAGED|HA-AND|VWRSI-R3-F0-S1",
                "BTCUSDm|4H|HA-MANAGED|HA-AND|RIB-LO-X0-F0", "BTCUSDm|1H|HA-ENTRY|HA-H1|LO|F2-4H",
                "BTCUSDm|4H|HA-ENTRY|HA-H1|LS|F2-1D", "BTCUSDm|1H|HA-ENTRY|HA-H2|LS|F0"),
}


@pytest.mark.parametrize("symbol", SYMS)
def test_g_smoke_one_row_of_each_rule_type_runs_on_development_data(symbol, real, monkeypatch):
    """2019-01-01 to 2019-06-30 through ``run_variant`` (the dev window shortened to the data held), at x1.0 and x1.5:
    it runs, and its trades are where the rule says (times, sides, exit reasons, counts). No profit or loss is
    looked at."""
    ctx = real(symbol)
    monkeypatch.setitem(M.WINDOWS, "dev", (None, REAL_END))
    assert M.window_span("dev", symbol) == ("2019-01-01", REAL_END)
    H.warm(ctx, H.variants(symbol))
    a_s = TM.s_of("2019-01-01")
    overlays = set()
    for vid in SMOKE[symbol]:
        v = V(vid)
        ex = H.build(v, ctx)
        res = M.run_variant(ctx, v, ex, windows=("dev",), trades_windows=("dev",))
        assert len(res.rows) == 1
        row = res.rows[0]
        assert (row["vid"], row["window"], row["start"], row["end"]) == (v.id, "dev", "2019-01-01", REAL_END)
        assert row["eligible"] is True and row["family"] == v.family and row["script"] == "HA"
        for suf in ("", "_x15"):
            assert int(row["n_taken" + suf]) == int(row["trades" + suf])
            assert int(row["n_busy" + suf]) == 0
            assert int(row["n_dropped_stop" + suf]) == 0 and int(row["n_dropped_target" + suf]) == 0
        if v.tf != "1D":
            assert int(row["trades"]) > 0, v.id
        b = ctx.bars(v.tf)
        for cost in (1.0, 1.5):
            tr = res.trades[res.trades.cost == cost]
            bar = tr.bar.to_numpy()
            entry_s = np.asarray([int(x.timestamp()) for x in tr.entry_time], np.int64)
            assert np.array_equal(entry_s, ctx.mk.t[b.ex[bar]]) and (b.tc[bar] > a_s).all()
            assert set(tr.reason) <= {"signal", "stop", "gap stop", "end"}
            if v.family == "HA-ENTRY":
                st = ex.state
                prev = np.where(bar >= 1, st[np.maximum(bar - 1, 0)], 0)
                first = b.tc[np.maximum(bar - 1, 0)] <= a_s
                assert (st[bar] == tr.side.to_numpy()).all() and ((st[bar] != prev) | first).all()
                assert tr.risk.isna().all() and set(tr.reason) <= {"signal", "end"}
                if v.params["side"] == "LO":
                    assert (tr.side == 1).all()
                continue
            base = v.params["base"]
            o = v.params["overlay"]
            overlays.add(o)
            r0 = M.run_exec(ctx.mk, base_exec(ctx, base), "2019-01-01", REAL_END, cost)
            t0 = r0.trades
            if o == "HA-AND":                                  # some of the base's trades, unchanged
                k0 = set(zip(t0.entry_time, t0.exit_time, t0.side, t0.reason))
                assert set(zip(tr.entry_time, tr.exit_time, tr.side, tr.reason)) <= k0, v.id
                continue
            # M1-M5: the base's entries, every trade ending no later than the base's
            assert np.array_equal(b.ex[bar], t0.entry_ix.to_numpy()), v.id
            assert np.array_equal(tr.side.to_numpy(), t0.side.to_numpy())
            x = np.asarray([int(z.timestamp()) for z in tr.exit_time], np.int64)
            x0 = np.asarray([int(z.timestamp()) for z in t0.exit_time], np.int64)
            assert (x <= x0).all(), v.id
            if "|RIB|" in base or T1.Variant.of(base).stop == "S1":
                assert np.isfinite(tr.risk.to_numpy()).all()
    assert overlays == set(H.OVERLAYS)
