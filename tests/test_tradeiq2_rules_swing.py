"""
Study 2's Swing Profile rule rows (``backtesting/research/tradeiq2_rules_swing.py``; PREREG 6.4 with sections 4, 5 and
7).

(a) The grid: the rows per symbol are the PREREG's (the numbers are written here from its text), with their ids,
    families, eligibility, the filters of each timeframe and the placebo; the driver's grid check accepts them and its
    claim-11 pairing finds each placebo row's POC row.
(b) Entry and exit semantics on hand-made bars with a hand-made profile (``use_profile``): the touch and hold, W1 (the
    swing stop and target, the flip exit), W2 (1.5 ATR, 2R), W3 (the finished leg's POC, after the flip bar, no flip
    exit), the placebo's 50% level, one candidate per anchor (also after the anchor's trade has closed), the tags, one
    position at a time, the flag-against case of reading R3, long only.
(c) PREREG 4's absolute-level rules through these rules: a fill beyond the target or the stop is dropped, the targets
    are measured from the actual fill, x1.5 recomputes them from its own fill.
(d) The filters: F0 / FD / F2 / LO, the F2 slot per timeframe asked for at build, FD's leg (forming or finished), the
    filter before the one-per-anchor rule (R2), checked at the decision close only, never closing an open trade.
(e) The real port on a synthetic market: the profile is the port on the context's bars and PREREG 2's volume; the
    touch-and-hold bars and the candidates equal a plain-Python transcription of the rules; causality (truncation);
    ``warm`` fills the cache that ``build`` reads.
(f) An execution smoke test on real Development bars (2019-01-01 to 2019-06-30, the market loaded only to 2019-07-01):
    one row of each rule type through tradeiq2_market's runner. Its profit or loss is neither printed nor asserted.
(g) Claims 11 and 12 (PREREG 8; readings R9 and R10): the exact one-sided Mann-Whitney U test on hand cases and
    against every split of small tied samples; the spans, touches, pairs and sizes on hand-made legs; both claims on a
    synthetic ``tradeiq2.Evidence`` (short synthetic windows, hand-made profiles and bars), through the driver's
    registry: the rows, the verdicts, the legs left out at a window's start, nothing read outside the windows; and on
    the real port's output on a synthetic market, equal to a plain-Python transcription. No real bar is read.

The hand-made market: M1 bars round the clock from Monday 2019-03-04 (study 2's guard scores no window before 2019 on
gold); every 1H bar opens and closes at 100.00 with a high of 100.50 (minute 10) and a low of 99.50 (minute 20), so its
true range is 1.00 and ATR(14) is exactly 1.00 from bar 13 on; the spread is 0.20 (a buy fills at 100.20). A level at
99.80 is touched and held by every bar from above (low 99.50 <= 99.80 < close 100.00), a level at 100.20 from below.
"""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_swing as SP
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_swing as RS

T0 = TM.s_of("2019-03-04")            # a Monday, 00:00 UTC
HOUR = 3600
GOLD, BTC = M.GOLD, M.BTC
NAN = math.nan

# PREREG 6.4 "Size: 3 x 4 x 2 = 24 eligible rows, plus 12 placebo rows, per symbol": 24 = (W1, W2, W3) x (F0, FD, F2,
# LO) x (1H, 4H); the placebo = (W1, W2, W3) x (F0, F2) x (1H, 4H), "control; not eligible". Section 7: family SP.
PREREG_ROWS = {GOLD: {("SP", True): 24, ("SP", False): 12}, BTC: {("SP", True): 24, ("SP", False): 12}}
F2_OF = {"1H": "F2-4H", "4H": "F2-1D"}


# ───────────────────────────── fixtures and helpers ─────────────────────────────

@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' folders as the guards see them: empty tmp folders (no FINALISTS.md: the hold-outs are closed)."""
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)


def hourly_m1(hours, base=100.0, sp=0.2):
    """The hand-made M1 bars (see the module docstring)."""
    k = hours * 60
    t = T0 + 60 * np.arange(k, dtype=np.int64)
    o = np.full(k, float(base))
    m = np.arange(k) % 60
    h, lo = o + 0.02, o - 0.02
    h[m == 10] = base + 0.5
    lo[m == 20] = base - 0.5
    return {"t": t, "o": o, "h": h, "l": lo, "c": o.copy(), "spread_mean": np.full(k, float(sp)), "n": np.ones(k)}


def ix(hour, minute=0):
    """The M1 index of minute ``minute`` of hour ``hour`` in the hand-made market."""
    return hour * 60 + minute


def ctx_of(m1, symbol=GOLD):
    return M.Context(M.TMarket2(symbol, m1))


class Prof:
    """A hand-made Swing Profile output (the port's contract, ``SP.KEYS``) for ``n`` bars: no swing point, no flip and
    no finished leg unless set."""

    def __init__(self, n):
        self.n = n
        self.a = {"is_down_move": np.zeros(n, bool), "hs_bar": np.full(n, -1, np.int64), "hs_price": np.full(n, NAN),
                  "ls_bar": np.full(n, -1, np.int64), "ls_price": np.full(n, NAN), "flip": np.zeros(n, bool),
                  "f_dir": np.zeros(n, np.int8), "f_lo": np.full(n, NAN), "f_hi": np.full(n, NAN),
                  "f_poc": np.full(n, NAN), "f_poc_ties": np.zeros(n, np.int64), "f_delta_pct": np.full(n, NAN),
                  "f_total": np.full(n, NAN)}
        self.rows = []

    def forming(self, a, z, hs, ls, poc=NAN, delta=0.25):
        """Bars a .. z-1: the stored swing high ``hs`` = (bar, price) and low ``ls`` = (bar, price), the forming leg's
        POC and delta (its direction and range follow from the two points, as in the port)."""
        s = slice(a, z)
        self.a["hs_bar"][s], self.a["hs_price"][s] = hs
        self.a["ls_bar"][s], self.a["ls_price"][s] = ls
        self.a["f_dir"][s] = int(np.sign(hs[0] - ls[0]))
        self.a["f_lo"][s], self.a["f_hi"][s] = min(hs[1], ls[1]), max(hs[1], ls[1])
        self.a["f_poc"][s] = poc
        self.a["f_poc_ties"][s] = 1 if np.isfinite(poc) else 0
        self.a["f_delta_pct"][s] = delta
        self.a["f_total"][s] = 100.0
        return self

    def flag(self, a, z, down):
        """``is_down_move`` on bars a .. z-1 (True: the last extreme was a new 50-bar high; the flips follow)."""
        self.a["is_down_move"][a:z] = down
        return self

    def leg(self, flip_bar, d, poc, lo=99.0, hi=101.0, delta=-0.25, start=None, atr=1.0):
        """A finished leg (``legs`` row) of side ``d`` (+1 the up leg, -1 the down leg) known from ``flip_bar``; its
        older swing bar ``start`` (default 20 bars before the flip) and ATR(200) at the flip ``atr``."""
        self.rows.append({"flip_bar": flip_bar, "dir": d,
                          "start_bar": max(flip_bar - 20, 0) if start is None else start,
                          "end_bar": max(flip_bar - 10, 0), "lo": lo, "hi": hi, "poc": poc,
                          "poc_all": (poc,) if np.isfinite(poc) else (), "delta_pct": delta, "total": 100.0,
                          "fifty": (lo + hi) / 2.0, "atr_at_flip": atr})
        return self

    def out(self):
        a = {k: v.copy() for k, v in self.a.items()}
        dn = a["is_down_move"]
        before = np.zeros(self.n, bool)
        before[1:] = dn[:-1]
        a["flip"] = dn != before                                   # the port's l.90
        rows = sorted(self.rows, key=lambda r: r["flip_bar"])
        legs = pd.DataFrame({k: [r[k] for r in rows] for k in SP.LEG_COLUMNS}) if rows else \
            pd.DataFrame({k: [] for k in SP.LEG_COLUMNS})
        legs = legs.astype({"flip_bar": np.int64, "dir": np.int8, "start_bar": np.int64, "end_bar": np.int64,
                            **{k: np.float64 for k in ("lo", "hi", "poc", "delta_pct", "total", "fifty",
                                                       "atr_at_flip")}})
        legs["poc_all"] = pd.Series([r["poc_all"] for r in rows], dtype=object)
        return {**{k: a[k] for k in SP.KEYS[:-1]}, "legs": legs[list(SP.LEG_COLUMNS)]}


def market_with(prof, hours=120, m1=None, symbol=GOLD, tf="1H"):
    """A hand-made market (or ``m1``) whose ``tf`` profile is ``prof`` (a ``Prof``)."""
    ctx = ctx_of(hourly_m1(hours) if m1 is None else m1, symbol)
    if prof is not None:
        RS.use_profile(ctx, tf, prof.out())
    return ctx


def variant(symbol, tf, rule, level="POC", filt="F0"):
    got = [v for v in RS.variants(symbol) if v.tf == tf and v.params["rule"] == rule and v.params["level"] == level
           and v.params["filter"] == filt]
    assert len(got) == 1, (symbol, tf, rule, level, filt)
    return got[0]


def build(ctx, rule, level="POC", filt="F0", tf="1H", symbol=GOLD):
    return RS.build(variant(symbol, tf, rule, level, filt), ctx)


def run(ctx, ex, cost=1.0):
    return M.run_exec(ctx.mk, ex, T0, int(ctx.mk.t[-1]) + 60, cost)


def rows(r):
    tr = r.trades
    return list(zip(tr.side, tr.entry_ix, tr.exit_ix, np.round(tr.entry, 9), np.round(tr.exit, 9), tr.reason))


def up_leg(n=120, a=20, z=40, poc=99.8, **kw):
    """An up leg forming on bars a .. z-1 (swing low 99.00 at bar 10, swing high 101.00 at bar 15) under an up move
    (the flag True from bar 5) that a flip to a new low ends at bar 30."""
    return Prof(n).forming(a, z, hs=(15, 101.0), ls=(10, 99.0), poc=poc, **kw).flag(5, 30, True)


# ───────────────────────────── (a) the grid ─────────────────────────────

def test_a_row_counts_per_symbol_are_the_preregs():
    for s, want in PREREG_ROWS.items():
        vs = RS.variants(s)
        assert dict(Counter((v.family, v.eligible) for v in vs)) == want, s
        el = [v for v in vs if v.eligible]
        pl = [v for v in vs if not v.eligible]
        assert dict(Counter(v.params["rule"] for v in el)) == {"W1": 8, "W2": 8, "W3": 8}
        assert dict(Counter(v.tf for v in el)) == {"1H": 12, "4H": 12}
        assert dict(Counter(v.params["filter"] for v in el)) == {"F0": 6, "FD": 6, "F2-4H": 3, "F2-1D": 3, "LO": 6}
        assert {v.params["level"] for v in el} == {"POC"} and {v.params["level"] for v in pl} == {"L50"}
        assert dict(Counter((v.params["rule"], v.tf) for v in pl)) == {(r, tf): 2 for r in RS.RULES for tf in RS.TFS}
        assert dict(Counter(v.params["filter"] for v in pl)) == {"F0": 6, "F2-4H": 3, "F2-1D": 3}
        assert RS.plan_counts(s) == want
    for s in M.CLAIM_SYMBOLS:
        assert RS.variants(s) == []
    with pytest.raises(ValueError):
        RS.variants("XAGUSDm")
    assert RS.EXPECTED == PREREG_ROWS


def test_a_ids_fields_and_filters_per_timeframe():
    for s in M.SYMBOLS:
        vs = RS.variants(s)
        ids = [v.id for v in vs]
        assert len(set(ids)) == len(ids)
        for v in vs:
            t = v.id.split("|")
            assert t[:3] == [s, v.tf, "SP"] and len(t) == 6 and v.script == "SP" and v.family == "SP"
            assert not any(ch.isspace() for ch in v.id) and isinstance(v.eligible, bool)
            p = dict(v.params)
            assert (t[3], t[4], t[5]) == (p["rule"], p["level"], p["filter"])
            assert p["filter"] in ("F0", "FD", "LO", F2_OF[v.tf])
            assert p["volume"] == ("tick" if s == GOLD else "binance")
            assert p["side"] == ("LO" if p["filter"] == "LO" else "LS")
            assert v.eligible == (p["level"] == "POC") and ("not eligible" in v.info) == (not v.eligible)
            json.dumps(p)
            sp = RS.spec_of(v)
            assert sp.rule.name == t[3] and sp.level == t[4] and sp.filter == t[5] and sp.placebo == (not v.eligible)
            assert RS.describe(v).startswith("Swing Profile [BigBeluga] ")
            assert ("placebo" in RS.describe(v)) == (not v.eligible)
        for tf in RS.TFS:
            assert {v.params["filter"] for v in vs if v.tf == tf and v.eligible} == {"F0", "FD", F2_OF[tf], "LO"}
            assert {v.params["filter"] for v in vs if v.tf == tf and not v.eligible} == {"F0", F2_OF[tf]}
    with pytest.raises(ValueError):
        RS.spec_of(M.Variant("XAUUSDm|1H|SP|W1|POC|F2-1D", GOLD, "1H", "SP", "SP"))      # not 1H's F2
    with pytest.raises(ValueError):
        RS.spec_of(M.Variant("XAUUSDm|1H|SP|W1|L50|FD", GOLD, "1H", "SP", "SP"))         # the placebo has no FD


def test_a_the_drivers_grid_check_accepts_the_rows():
    D = pytest.importorskip("backtesting.research.tradeiq2")
    g, _ = D.checked_grid({"swing": RS})
    assert len(g) == 72 and set(g.family) == {"SP"} and set(g.group) == {"SP"}
    assert int(g.eligible.sum()) == 48


def test_a_the_drivers_claim_11_pairing_finds_each_placebo_rows_poc_row():
    """The driver pairs a placebo row with the eligible SP row of the same timeframe that carries its W and F tokens
    and neither FD nor LO (``tradeiq2._claim11``): it must find exactly the POC row of the same rule and filter."""
    D = pytest.importorskip("backtesting.research.tradeiq2")
    for s in M.SYMBOLS:
        vs = RS.variants(s)
        tok = {v.id: D.tokens_of(v.id, dict(v.params)) for v in vs}
        for v in (x for x in vs if not x.eligible):
            t = tok[v.id]
            w = [x for x in ("W1", "W2", "W3") if x in t]
            f = [x for x in ("F0", "F2", "F2-4H", "F2-1D") if x in t]
            assert len(w) == 1 and len(f) == 1, v.id
            m = [u.id for u in vs if u.eligible and u.tf == v.tf and w[0] in tok[u.id] and f[0] in tok[u.id]
                 and not ({"FD", "LO"} & tok[u.id])]
            assert m == [v.id.replace("|L50|", "|POC|")], v.id


# ───────────────────────────── (b) entries and exits on hand-made bars ─────────────────────────────

def test_b_the_hand_made_market():
    ctx = ctx_of(hourly_m1(120))
    b, a = ctx.bars("1H"), ctx.atr("1H")
    assert len(b) == 120 and np.all(b.h == 100.5) and np.all(b.l == 99.5) and np.all(b.c == 100.0)
    assert np.isnan(a[12]) and np.all(a[13:] == 1.0)
    assert list(b.ex[:3]) == [ix(1), ix(2), ix(3)]


def test_b_the_touch_and_hold_shape():
    """Long: low <= level < close (the low may equal the level, the close may not); short: high >= level > close."""
    n = 12
    h, lo, c, atr = np.full(n, 100.5), np.full(n, 99.5), np.full(n, 100.0), np.ones(n)
    p = Prof(n).forming(0, 6, hs=(5, 101.0), ls=(2, 99.0)).forming(6, 12, hs=(3, 101.0), ls=(5, 99.0))   # up; down
    p.a["f_poc"][:] = [99.5, 99.4, 100.0, 99.99, NAN, 99.8, 100.5, 100.6, 100.0, 100.01, 99.5, NAN]
    prof = RS._pack(p.out(), n)
    t = RS.triggers(prof, h, lo, c, atr, "W1")
    assert list(t["bar"]) == [0, 3, 5, 6, 9] and list(t["side"]) == [1, 1, 1, -1, -1]
    assert list(t["anchor"]) == [2, 2, 2, 3, 3]
    assert list(t["level"]) == [99.5, 99.99, 99.8, 100.5, 100.01]
    p.a["f_dir"][5] = 0                                                   # both stored points one outside bar
    assert 5 not in RS.triggers(RS._pack(p.out(), n), h, lo, c, atr, "W1")["bar"]


def test_b_w1_long_the_swing_stop_and_target_and_the_flip_exit():
    p = up_leg()
    ctx = market_with(p)
    E = build(ctx, "W1").entries
    assert list(E.bar) == [20] and list(E.side) == [1]                   # bars 20 .. 39 all touch: the first only
    assert E.stop_level[0] == 99.0 and E.target_level[0] == 101.0       # the leg's swing low and swing high
    assert np.isnan(E.target_r[0]) and list(E.tag) == [10]               # the anchor: the swing low's bar
    ex = build(ctx, "W1")
    assert ex.kind == "events" and ex.exit_long[30] and not ex.exit_long[29] and ex.exit_short[5]
    r = run(ctx, ex)
    # filled at the open after bar 20's close at the ask; the flip to a new low at bar 30 closes it at the next open
    assert rows(r) == [(1, ix(21), ix(31), 100.2, 100.0, "signal")]
    assert r.trades.risk[0] == pytest.approx(1.2) and r.trades.bar[0] == 20 and r.trades.tag[0] == 10


def test_b_w1_target_and_stop():
    m1 = hourly_m1(120)
    m1["h"][ix(25, 40)] = 101.2
    ctx = market_with(up_leg(), m1=m1)
    r = run(ctx, build(ctx, "W1"))
    assert rows(r) == [(1, ix(21), ix(25, 40), 100.2, 101.0, "target")]
    m1 = hourly_m1(120)
    m1["l"][ix(25, 30)] = 98.5
    ctx = market_with(up_leg(), m1=m1)
    r = run(ctx, build(ctx, "W1"))
    assert rows(r) == [(1, ix(21), ix(25, 30), 100.2, 98.8, "stop")]   # one spread worse than the level


def test_b_w1_short_mirrors_it():
    p = Prof(120).forming(20, 40, hs=(10, 101.0), ls=(15, 99.0), poc=100.2).flag(30, 120, True)
    ctx = market_with(p)
    ex = build(ctx, "W1")
    E = ex.entries
    assert list(E.bar) == [20] and list(E.side) == [-1] and list(E.tag) == [10]     # the anchor: the swing high
    assert E.stop_level[0] == 101.0 and E.target_level[0] == 99.0
    assert ex.exit_short[30] and not ex.exit_long[30]
    r = run(ctx, ex)
    assert rows(r) == [(-1, ix(21), ix(31), 100.0, 100.2, "signal")]   # a sell at the bid, out at the ask


def test_b_one_candidate_per_anchor_and_none_after_its_trade_closed():
    p = Prof(120)
    p.forming(20, 35, hs=(15, 101.0), ls=(10, 99.0), poc=99.8)
    p.forming(35, 45, hs=(33, 101.5), ls=(10, 99.0), poc=99.8)         # the leg extends: the same anchor (10)
    p.forming(50, 61, hs=(33, 101.5), ls=(45, 98.8), poc=100.2)        # a down leg from the swing high of bar 33
    p.forming(70, 81, hs=(65, 101.2), ls=(45, 98.8), poc=99.8)         # an up leg from the swing low of bar 45
    p.flag(62, 120, True)                                               # a flip to a new high closes the short
    m1 = hourly_m1(120)
    m1["h"][ix(23, 30)] = 101.1                                         # the first trade reaches its target early
    ctx = market_with(p, m1=m1)
    E = build(ctx, "W1").entries
    assert list(E.bar) == [20, 50, 70] and list(E.side) == [1, -1, 1] and list(E.tag) == [10, 33, 45]
    tr = RS.trigger_table(ctx, "1H", "W1")
    assert int((tr["anchor"] == 10).sum()) == 25                       # bars 20 .. 44 touch: anchor 10's only trade
    r = run(ctx, build(ctx, "W1"))
    assert list(r.trades.bar) == [20, 50, 70] and list(r.trades.reason) == ["target", "signal", "end"]
    assert list(r.trades.exit_ix)[:2] == [ix(23, 30), ix(63)] and r.counts["busy"] == 0
    assert r.counts["candidates"] == 3 and r.counts["taken"] == 3


def test_b_w2_poc_minus_1_5_atr_and_2r():
    m1 = hourly_m1(120)
    m1["h"][ix(25, 40)] = 104.1
    ctx = market_with(up_leg(), m1=m1)
    E = build(ctx, "W2").entries
    assert list(E.bar) == [20] and E.stop_level[0] == pytest.approx(99.8 - 1.5) and list(E.target_r) == [2.0]
    assert np.isnan(E.target_level[0]) and list(E.tag) == [10]
    r = run(ctx, build(ctx, "W2"))
    # risk 100.20 - 98.30 = 1.90 from the actual fill; target 100.20 + 3.80 = 104.00
    assert rows(r) == [(1, ix(21), ix(25, 40), 100.2, 104.0, "target")]
    assert r.trades.risk[0] == pytest.approx(1.9) and r.trades.r[0] == pytest.approx(2.0)
    ctx = market_with(Prof(120).forming(20, 40, hs=(10, 101.0), ls=(15, 99.0), poc=100.2).flag(30, 120, True))
    E = build(ctx, "W2").entries
    assert list(E.side) == [-1] and E.stop_level[0] == pytest.approx(100.2 + 1.5)
    r = run(ctx, build(ctx, "W2"))
    assert rows(r) == [(-1, ix(21), ix(31), 100.0, 100.2, "signal")]   # W2 keeps W1's flip exit


def _w3_market(m1=None, delta_down=-0.25, delta_up=0.25):
    """A down leg finished at bar 30 (POC 99.80: a long after it) and an up leg finished at bar 60 (POC 100.20: a
    short after it); the flag True on 30 .. 59."""
    p = Prof(120).flag(30, 60, True)
    p.leg(30, -1, 99.8, delta=delta_down).leg(60, 1, 100.2, delta=delta_up)
    return market_with(p, m1=m1)


def test_b_w3_the_finished_legs_poc_after_the_flip_bar_without_a_flip_exit():
    ctx = _w3_market()
    E = build(ctx, "W3").entries
    # the flip bars 30 and 60 have the shape too, but W3's window starts after the flip bar (reading R4)
    assert list(E.bar) == [31, 61] and list(E.side) == [1, -1] and list(E.tag) == [30, 60]
    assert list(E.stop_level) == pytest.approx([99.8 - 1.5, 100.2 + 1.5]) and list(E.target_r) == [2.0, 2.0]
    b = ctx.bars("1H")
    alt = RS.triggers(RS.profile(ctx, "1H"), b.h, b.l, b.c, ctx.atr("1H"), "W3", flip_bar=True)
    assert alt["bar"][0] == 30 and 60 in alt["bar"]
    ex = build(ctx, "W3")
    assert ex.exit_long is None and ex.exit_short is None
    r = run(ctx, ex)
    # no exit but the stop and the 2R target: the long is still open at bar 61, so the short of the next leg is busy
    assert rows(r) == [(1, ix(32), ix(120) - 1, 100.2, 100.0, "end")] and r.counts["busy"] == 1
    m1 = hourly_m1(120)
    m1["h"][ix(40, 30)] = 104.1                                         # target 100.20 + 2 x 1.90 = 104.00
    ctx = _w3_market(m1)
    r = run(ctx, build(ctx, "W3"))
    assert rows(r) == [(1, ix(32), ix(40, 30), 100.2, 104.0, "target"), (-1, ix(62), ix(120) - 1, 100.0, 100.2, "end")]


def test_b_w3_window_ends_at_the_next_flip_bar():
    """Leg 30's POC (99.80) is held by every bar, but only bars 31 and 32 are in its window: the flip of bar 33 makes
    leg 33 (POC 100.00, which no close holds from below) the just-finished leg, then leg 50 from bar 51."""
    p = Prof(120).flag(30, 33, True).leg(30, -1, 99.8).leg(33, 1, 100.0)
    p.flag(50, 120, True).leg(50, -1, 99.8)
    ctx = market_with(p)
    t = RS.trigger_table(ctx, "1H", "W3")
    assert list(t["bar"][:4]) == [31, 32, 51, 52] and list(t["anchor"][:4]) == [30, 30, 50, 50]
    assert list(t["leg"][:4]) == [0, 0, 2, 2] and not np.isin([33, 34, 49, 50], t["bar"]).any()
    assert list(build(ctx, "W3").entries.bar) == [31, 51]
    assert RS.active_leg([30, 33, 50], 52)[[29, 30, 31, 33, 49, 50, 51]].tolist() == [-1, 0, 0, 1, 1, 2, 2]


def test_b_the_placebo_uses_the_legs_50_percent_level():
    # forming leg 99.00 .. 100.60 (50% = 99.80) with its POC at 100.00, which no bar holds above
    p = Prof(120).forming(20, 40, hs=(15, 100.6), ls=(10, 99.0), poc=100.0).flag(5, 30, True)
    p.leg(60, -1, 100.0, lo=99.0, hi=100.6)                            # a finished leg likewise (fifty 99.80)
    ctx = market_with(p)
    for rule in ("W1", "W2", "W3"):
        assert len(build(ctx, rule).entries) == 0, rule
    E1, E2, E3 = (build(ctx, r, "L50").entries for r in ("W1", "W2", "W3"))
    assert list(E1.bar) == [20] and E1.stop_level[0] == 99.0 and E1.target_level[0] == 100.6
    assert list(E2.bar) == [20] and E2.stop_level[0] == pytest.approx(99.8 - 1.5) and list(E2.target_r) == [2.0]
    assert list(E3.bar) == [61] and E3.stop_level[0] == pytest.approx(99.8 - 1.5) and list(E3.tag) == [60]
    t = RS.trigger_table(ctx, "1H", "W1", "L50")
    assert np.all(t["level"] == (99.0 + 100.6) / 2.0)
    assert build(ctx, "W1", "L50").exit_long[30] and build(ctx, "W3", "L50").exit_long is None


def test_b_one_position_at_a_time():
    p = up_leg(z=26).forming(26, 60, hs=(15, 101.0), ls=(24, 99.1), poc=100.2)   # a short anchor from bar 26 on
    p.flag(5, 120, True)                                                         # no flip: the long stays open
    ctx = market_with(p)
    r = run(ctx, build(ctx, "W1"))
    assert list(r.trades.bar) == [20] and r.counts["busy"] == 1 and r.counts["candidates"] == 2


def test_b_a_trade_decided_with_the_flag_already_against_it_reading_r3():
    """The stored pair is still the up leg on the flip bar (22) to a new low and after it; the first touch comes on
    that bar. Its own flip is no exit (the per-bar exits act from the next bar); the next flip to a new low is."""
    p = Prof(120).forming(18, 30, hs=(15, 101.0), ls=(10, 99.0), poc=100.0)    # no touch at a POC of 100.00
    p.a["f_poc"][22:30] = 99.8
    p.flag(5, 22, True).flag(40, 50, True)                             # flips: to a new low at 22 and at 50
    ctx = market_with(p)
    E = build(ctx, "W1").entries
    assert list(E.bar) == [22] and not RS.profile(ctx, "1H")["is_down_move"][22]
    r = run(ctx, build(ctx, "W1"))
    assert rows(r) == [(1, ix(23), ix(51), 100.2, 100.0, "signal")]
    win = (str(TM.utc(T0)), str(TM.utc(T0 + 120 * HOUR)))
    ec = RS.event_counts(ctx, win).set_index("vid")
    assert ec.loc["XAUUSDm|1H|SP|W1|POC|F0", "n_flag_against"] == 1
    assert ec.loc["XAUUSDm|1H|SP|W1|POC|F0", "n_on_flip_bar"] == 1


def test_b_long_only():
    p = up_leg().forming(50, 70, hs=(45, 101.0), ls=(48, 99.0), poc=100.2)   # a down leg: shorts
    ctx = market_with(p)
    assert list(build(ctx, "W1").entries.side) == [1, -1]
    ex = build(ctx, "W1", filt="LO")
    assert list(ex.entries.side) == [1] and ex.exit_short is None and ex.exit_long is not None
    assert list(build(ctx, "W2", filt="LO").entries.bar) == [20]


def test_b_build_refuses_a_row_of_another_symbol_or_not_of_the_grid():
    ctx = market_with(up_leg())
    with pytest.raises(ValueError):
        RS.build(variant(BTC, "1H", "W1"), ctx)
    with pytest.raises(ValueError):
        RS.build(M.Variant("XAUUSDm|1H|SP|W4|POC|F0", GOLD, "1H", "SP", "SP"), ctx)
    with pytest.raises(ValueError):
        RS.build(M.Variant("XAUUSDm|1H|SP|W1|POC|F0", GOLD, "4H", "SP", "SP"), ctx)     # its timeframe differs


def test_b_use_profile_refuses_a_second_profile_and_bad_ones():
    ctx = market_with(up_leg())
    with pytest.raises(ValueError):
        RS.use_profile(ctx, "1H", up_leg().out())
    bad = up_leg().out()
    bad["f_poc"] = bad["f_poc"][:-1]
    with pytest.raises(ValueError):
        RS.use_profile(ctx_of(hourly_m1(120)), "1H", bad)
    with pytest.raises(ValueError):
        RS.use_profile(ctx_of(hourly_m1(120)), "1D", up_leg().out())


# ───────────────────────────── (c) the absolute-level rules (PREREG 4) ─────────────────────────────

def _gap_from(m1, hour, level):
    """Every M1 bar from ``hour`` on shifted to ``level`` (the hourly pattern kept)."""
    a = ix(hour)
    d = level - 100.0
    for k in ("o", "h", "l", "c"):
        m1[k][a:] += d


def test_c_a_fill_beyond_the_target_or_the_stop_is_dropped():
    m1 = hourly_m1(120)
    _gap_from(m1, 21, 101.5)                                            # the ask at the fill 101.70 >= target 101.00
    ctx = market_with(up_leg(), m1=m1)
    r = run(ctx, build(ctx, "W1"))
    assert len(r.trades) == 0 and r.counts["dropped_target"] == 1 and r.counts["candidates"] == 1
    m1 = hourly_m1(120)
    _gap_from(m1, 21, 98.5)                                             # the ask 98.70 <= stop 99.00
    ctx = market_with(up_leg(), m1=m1)
    r = run(ctx, build(ctx, "W1"))
    assert len(r.trades) == 0 and r.counts["dropped_stop"] == 1
    r = run(ctx, build(ctx, "W2"))                                       # W2's stop 98.30 is below the ask: taken
    assert r.counts["taken"] == 1 and r.trades.risk[0] == pytest.approx(98.7 - 98.3)


def test_c_the_targets_are_measured_from_the_actual_fill_and_x15_recomputes_them():
    m1 = hourly_m1(120)
    _gap_from(m1, 21, 100.5)                                            # fill 100.70: risk 2.40, target 105.50
    m1["h"][ix(26, 40)] = 105.6
    ctx = market_with(up_leg(), m1=m1)
    r = run(ctx, build(ctx, "W2"))
    assert rows(r) == [(1, ix(21), ix(26, 40), 100.7, 105.5, "target")] and r.trades.risk[0] == pytest.approx(2.4)
    # x1.5: the fill 100.80 gives a risk of 2.50 and a target of 105.80, which the high of 105.60 does not reach
    r15 = run(ctx, build(ctx, "W2"), cost=1.5)
    assert rows(r15) == [(1, ix(21), ix(31), 100.8, 100.5, "signal")] and r15.trades.risk[0] == pytest.approx(2.5)
    # W1's absolute target: the same level from either fill
    m1 = hourly_m1(120)
    m1["h"][ix(25, 40)] = 101.2
    ctx = market_with(up_leg(), m1=m1)
    for cost, fill in ((1.0, 100.2), (1.5, 100.3)):
        r = run(ctx, build(ctx, "W1"), cost=cost)
        assert rows(r) == [(1, ix(21), ix(25, 40), fill, 101.0, "target")]
        assert r.trades.risk[0] == pytest.approx(fill - 99.0)


# ───────────────────────────── (d) the filters ─────────────────────────────

def test_d_the_f2_slot_of_each_timeframe_and_lo_are_asked_for_at_build():
    seen = []
    n = {"1H": 120, "4H": 30}
    ctx = ctx_of(hourly_m1(120))
    for tf in RS.TFS:
        RS.use_profile(ctx, tf, Prof(n[tf]).out())
    ctx.allow = lambda tf, name: (seen.append((tf, name)), (np.ones(n[tf], bool), np.ones(n[tf], bool)))[1]
    for v in RS.variants(GOLD):
        RS.build(v, ctx)
    # per timeframe: F0 for 3 rules and their 3 placebo rows, F2 likewise, LO for 3 rules; FD is the module's own
    assert Counter(seen) == {("1H", "F0"): 6, ("1H", "F2-4H"): 6, ("1H", "LO"): 3, ("4H", "F0"): 6,
                             ("4H", "F2-1D"): 6, ("4H", "LO"): 3}
    with pytest.raises(ValueError):
        RS.allow_of(ctx, "4H", "W1", "F2-4H")


def test_d_fd_the_forming_legs_delta_on_the_trades_side_before_the_one_per_anchor_rule():
    p = up_leg()
    p.a["f_delta_pct"][20:25] = -0.1                                   # "a leg up with weak buying": no long
    ctx = market_with(p)
    assert list(build(ctx, "W1", filt="F0").entries.bar) == [20]
    E = build(ctx, "W1", filt="FD").entries
    assert list(E.bar) == [25] and list(E.tag) == [10]                 # a later touch of the same anchor (R2)
    al, ash = RS.fd_allow(ctx, "1H", "W2")
    assert not al[20] and al[25] and not ash[25]
    for d, kept in ((0.1, False), (0.0, False), (NAN, False), (-0.1, True)):
        q = Prof(120).forming(20, 40, hs=(10, 101.0), ls=(15, 99.0), poc=100.2, delta=d)
        assert len(build(market_with(q), "W2", filt="FD").entries) == int(kept), d


def test_d_fd_on_w3_reads_the_finished_legs_delta():
    """W3 trades against the finished leg: a long after a down leg needs that leg's delta above 0 (weak selling), a
    short after an up leg its delta below 0 ("a leg up with weak buying", reading R6)."""
    E = build(_w3_market(delta_down=0.1, delta_up=-0.1), "W3", filt="FD").entries
    assert list(E.bar) == [31, 61]
    E = build(_w3_market(delta_down=-0.1, delta_up=0.1), "W3", filt="FD").entries
    assert len(E) == 0
    E = build(_w3_market(delta_down=0.1, delta_up=0.1), "W3", filt="FD").entries
    assert list(E.bar) == [31]


def test_d_a_filter_gates_the_decision_close_and_never_closes_an_open_trade():
    ctx = market_with(up_leg())
    al, ash = np.zeros(120, bool), np.zeros(120, bool)
    al[21:26] = True                                                    # refuses bar 20, then allows 21 .. 25 only
    asked = []
    ones = np.ones(120, bool)
    ctx.allow = lambda tf, name: (asked.append(name), (ones, ones) if name == "F0" else (al, ash))[1]
    E = build(ctx, "W1", filt="F2-4H").entries
    assert list(E.bar) == [21] and asked == ["F2-4H"]
    r = run(ctx, build(ctx, "W1", filt="F2-4H"))
    assert rows(r) == [(1, ix(22), ix(31), 100.2, 100.0, "signal")]  # out at the flip, not when the filter turned


# ───────────────────────────── (e) the real port on a synthetic market ─────────────────────────────

def walk(n, seed):
    """A random walk of 1H bars with wicks (tick-like integer volumes)."""
    r = np.random.default_rng(seed)
    c = 1000.0 + np.cumsum(r.standard_t(4, n) * 2.0)
    o = np.r_[c[0], c[:-1]] + r.normal(0, 0.5, n)
    h = np.maximum(o, c) + r.exponential(1.0, n)
    lo = np.minimum(o, c) - r.exponential(1.0, n)
    v = r.integers(1, 40, n).astype(np.float64)
    return o, h, lo, c, v


def m1_of_hours(o, h, lo, c, v, sp=0.3):
    """60 M1 bars per 1H bar, round the clock from T0: the path open -> low -> high -> close (an up bar) or open ->
    high -> low -> close, so the 1H bar built from them is (o, h, l, c) exactly; the tick volume v on its first M1."""
    n = len(o)
    up = c >= o
    p1, p2 = np.where(up, lo, h), np.where(up, h, lo)
    seg = np.linspace(0.0, 1.0, 21)[1:]
    path = np.concatenate([o[:, None] + (p1 - o)[:, None] * seg, p1[:, None] + (p2 - p1)[:, None] * seg,
                           p2[:, None] + (c - p2)[:, None] * seg], axis=1)
    path = np.minimum(np.maximum(path, lo[:, None]), h[:, None])
    path[:, 19], path[:, 39], path[:, 59] = p1, p2, c
    opens = np.concatenate([o[:, None], path[:, :-1]], axis=1)
    k = n * 60
    tick = np.zeros((n, 60))
    tick[:, 0] = v
    return {"t": T0 + 60 * np.arange(k, dtype=np.int64), "o": opens.ravel(), "h": np.maximum(opens, path).ravel(),
            "l": np.minimum(opens, path).ravel(), "c": path.ravel(), "spread_mean": np.full(k, float(sp)),
            "n": tick.ravel()}


@pytest.fixture(scope="module")
def syn():
    bars = walk(3600, 0)
    m1 = m1_of_hours(*bars)
    return {"m1": m1, "bars": bars, "ctx": M.Context(M.TMarket2(GOLD, m1))}


def ref_triggers(p, h, lo, c, atr, rule, level):
    """The touch-and-hold bars of PREREG 6.4 by a plain loop over the bars (the transcription of the module docstring):
    (bar, side, anchor, stop, target or None)."""
    fb = [int(x) for x in p["legs"]["flip_bar"]]
    out = []
    for t in range(len(c)):
        if rule in ("W1", "W2"):
            d = int(p["f_dir"][t])
            if d == 0:
                continue
            lvl = p["f_poc"][t] if level == "POC" else (p["f_lo"][t] + p["f_hi"][t]) / 2.0
            anchor = int(p["ls_bar"][t]) if d == 1 else int(p["hs_bar"][t])
        else:
            before = [k for k, f in enumerate(fb) if f < t]
            if not before or t in fb:                                  # after the flip bar, up to the next flip bar
                continue
            k = before[-1]
            row = p["legs"].iloc[k]
            d = -int(row["dir"])
            lvl = float(row["poc"] if level == "POC" else row["fifty"])
            anchor = fb[k]
        if not math.isfinite(lvl):
            continue
        if not ((d == 1 and lo[t] <= lvl < c[t]) or (d == -1 and h[t] >= lvl > c[t])):
            continue
        if rule == "W1":
            stop = p["ls_price"][t] if d == 1 else p["hs_price"][t]
            target = p["hs_price"][t] if d == 1 else p["ls_price"][t]
        else:
            stop, target = lvl - d * 1.5 * atr[t], None
            if not (atr[t] > 0):
                continue
        out.append((t, d, anchor, float(stop), None if target is None else float(target)))
    return out


def test_e_the_profile_is_the_port_on_the_bars_and_the_volume(syn, monkeypatch):
    ctx, (o, h, lo, c, v) = syn["ctx"], syn["bars"]
    b = ctx.bars("1H")
    assert np.array_equal(b.o, o) and np.array_equal(b.h, h) and np.array_equal(b.l, lo) and np.array_equal(b.c, c)
    assert np.array_equal(b.vol, v)
    p = RS.profile(ctx, "1H")
    ref = SP.swing_profile(o, h, lo, c, v)
    for k in SP.KEYS[:-1]:
        assert p[k].dtype == ref[k].dtype and not p[k].flags.writeable, k
        assert np.array_equal(p[k], ref[k], equal_nan=p[k].dtype.kind == "f"), k
    assert p["legs"].equals(ref["legs"]) and RS.profile(ctx, "1H") is p
    assert len(p["legs"]) >= 40 and np.isfinite(p["f_poc"][400:]).all()
    # BTC reads Binance's volume (PREREG 2), here a stand-in served by tradeiq2_market's binance_volume
    fake = np.arange(len(b), dtype=np.float64) % 17
    monkeypatch.setattr(M, "binance_volume", lambda mk, tf: (fake.copy(), np.zeros(len(fake), np.int64)))
    cb = M.Context(M.TMarket2(BTC, syn["m1"]))
    pb = RS.profile(cb, "1H")
    refb = SP.swing_profile(o, h, lo, c, fake)
    assert np.array_equal(pb["f_poc"], refb["f_poc"], equal_nan=True) and pb["legs"].equals(refb["legs"])
    assert not np.array_equal(pb["f_poc"], p["f_poc"], equal_nan=True)


@pytest.mark.parametrize("tf", ["1H", "4H"])
def test_e_touches_and_candidates_equal_a_plain_transcription(syn, tf):
    ctx = syn["ctx"]
    b = ctx.bars(tf)
    p = RS.profile(ctx, tf)
    atr = np.asarray(ctx.atr(tf))
    n_multi = 0
    f2 = {"kept": 0, "removed": 0}
    for rule in RS.RULES:
        for level in RS.LEVELS:
            t = RS.trigger_table(ctx, tf, rule, level)
            ref = ref_triggers(p, b.h, b.l, b.c, atr, rule, level)
            got = list(zip(t["bar"].tolist(), t["side"].tolist(), t["anchor"].tolist(), t["stop"].tolist(),
                           [None if not math.isfinite(x) else x for x in t["target"].tolist()]))
            assert got == ref, (tf, rule, level)
            assert t["valid"].all()
            for filt in (("F0", "FD", "LO", F2_OF[tf]) if level == "POC" else ("F0", F2_OF[tf])):
                al, ash = RS.allow_of(ctx, tf, rule, filt)
                if filt == F2_OF[tf]:                                     # tradeiq2_filters' own masks
                    assert al is F.allow(ctx, tf, filt)[0] and ash is F.allow(ctx, tf, filt)[1]
                    ok = np.asarray([al[bar] if d == 1 else ash[bar] for bar, d, *_ in ref], bool)
                    f2["kept"] += int(ok.sum())
                    f2["removed"] += int((~ok).sum())
                seen, want = set(), []
                for (bar, d, anchor, *_ ) in ref:                       # the first allowed touch of each anchor
                    if (al[bar] if d == 1 else ash[bar]) and (d, anchor) not in seen:
                        seen.add((d, anchor))
                        want.append((bar, d, anchor))
                E = RS.rule_entries(ctx, tf, rule, level, filt)
                assert list(zip(E.bar.tolist(), E.side.tolist(), E.tag.tolist())) == want, (tf, rule, level, filt)
            n_multi += len(ref) - len({(d, a) for _, d, a, *_ in ref})
    assert n_multi > 50                                                  # anchors are touched more than once
    if tf == "1H":                                                       # the 4H MA200 exists from about bar 800
        assert f2["kept"] > 0 and f2["removed"] > 0, f2


def test_e_causality_decisions_up_to_t_do_not_change_when_the_bars_after_t_are_removed(syn):
    """Cuts at UTC day boundaries: every entry decided up to the cut (bar, side, levels, tag) and every flip exit up to
    it is the same in the cut market."""
    full = syn["ctx"]
    m1 = syn["m1"]
    total = 0
    for cut_day in (31, 64, 97, 133):
        end = T0 + cut_day * 86400
        keep = m1["t"] < end
        part = M.Context(M.TMarket2(GOLD, {k: a[keep] for k, a in m1.items()}))
        for v in RS.variants(GOLD):
            exf, exp = RS.build(v, full), RS.build(v, part)
            Ef, Ep = exf.entries, exp.entries
            n2 = len(part.bars(v.tf))
            assert np.array_equal(full.bars(v.tf).c[:n2], part.bars(v.tf).c)
            k = Ef.bar < n2
            assert np.array_equal(Ep.bar, Ef.bar[k]) and np.array_equal(Ep.side, Ef.side[k]), (cut_day, v.id)
            for f in ("stop_level", "target_level", "target_r"):
                assert np.array_equal(getattr(Ep, f), getattr(Ef, f)[k], equal_nan=True), (cut_day, v.id, f)
            assert np.array_equal(Ep.tag, Ef.tag[k]), (cut_day, v.id)
            for side in ("exit_long", "exit_short"):
                a, z = getattr(exf, side), getattr(exp, side)
                assert (a is None) == (z is None) and (a is None or np.array_equal(a[:n2], z)), (cut_day, v.id)
            total += int(k.sum())
    assert total >= 300, total


def test_e_warm_fills_the_cache_the_rows_read(syn):
    ctx = M.Context(M.TMarket2(GOLD, syn["m1"]))
    RS.warm(ctx, RS.variants(GOLD))
    keys = {(k[0], k[2]) for k in ctx.cache}
    for tf in RS.TFS:
        assert (RS.MODULE, tf) in keys and ("atr", tf) in keys and ("filter", tf) in keys
    n = len(ctx.cache)
    for v in RS.variants(GOLD):
        RS.build(v, ctx)
    assert len(ctx.cache) == n


def test_e_event_counts_are_counts_of_the_candidates(syn):
    ctx = syn["ctx"]
    win = (str(TM.utc(T0)), str(TM.utc(int(ctx.mk.t[-1]) + 60)))
    ec = RS.event_counts(ctx, win).set_index("vid")
    assert len(ec) == 36
    for v in RS.variants(GOLD):
        E = RS.build(v, ctx).entries
        n_in = int((ctx.bars(v.tf).ex[E.bar] < len(ctx.mk.t)).sum())         # filled inside the window
        assert ec.loc[v.id, "candidates"] == n_in == ec.loc[v.id, "cand_long"] + ec.loc[v.id, "cand_short"], v.id
        assert ec.loc[v.id, "touch_bars"] >= ec.loc[v.id, "allowed_bars"] >= ec.loc[v.id, "candidates"]
    w3 = ec[ec.rule == "W3"]
    assert (w3.n_flag_against == 0).all() and (w3.n_on_flip_bar == 0).all() and (w3.n_w3_flip_bar_alt > 0).any()


# ───────────────────────────── (f) real Development bars: an execution smoke test ─────────────────────────────

SMOKE_END = "2019-07-01"
SMOKE_WINDOW = ("2019-01-01", SMOKE_END)
SMOKE_ROWS = [("1H", "W1", "POC", "F0"), ("1H", "W2", "POC", "FD"), ("1H", "W3", "POC", "F2-4H"),
              ("4H", "W1", "POC", "LO"), ("4H", "W2", "POC", "F2-1D"), ("4H", "W3", "POC", "F0"),
              ("1H", "W1", "L50", "F2-4H"), ("4H", "W2", "L50", "F0"), ("1H", "W3", "L50", "F0")]
REASONS = {"W1": {"signal", "stop", "gap stop", "target", "gap target", "end"},
           "W2": {"signal", "stop", "gap stop", "target", "gap target", "end"},
           "W3": {"stop", "gap stop", "target", "gap target", "end"}}


@pytest.fixture(scope="module", params=["XAUUSDm", "BTCUSDm"])
def real_ctx(request, tmp_path_factory):
    """One symbol's market from its data start to 2019-07-01 only (nothing later is read), one at a time."""
    symbol = request.param
    months = set(store.available_months(symbol))
    start = M.data_start(symbol)
    if (2019, 6) not in months or (int(start[:4]), int(start[5:7])) not in months:
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    if symbol == BTC and not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.s_of(SMOKE_END)):
        pytest.skip("the Binance klines are not on this machine")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", tmp_path_factory.mktemp("closed_study2"))
        mk = M.load(symbol, end=SMOKE_END)
    assert mk.end_s == TM.s_of(SMOKE_END) and int(mk.t[-1]) + 60 <= TM.s_of(SMOKE_END)
    yield M.Context(mk)


def test_f_one_row_of_each_rule_type_runs_on_real_development_bars(real_ctx):
    """Development only (2019-01-01 to 2019-06-30). The run must work and its bookkeeping must hold; its profit or
    loss is neither printed nor asserted."""
    ctx = real_ctx
    s = ctx.symbol
    n_runs = 0
    for tf, rule, level, filt in SMOKE_ROWS:
        v = variant(s, tf, rule, level, filt)
        ex = RS.build(v, ctx)
        assert ex.kind == "events" and ex.label == v.id
        E = ex.entries
        assert len(E) > 0, v.id
        assert len(set(zip(E.side.tolist(), E.tag.tolist()))) == len(E)             # one candidate per anchor
        b = ctx.bars(tf)
        for cost in M.COSTS:
            r = M.run_exec(ctx.mk, ex, *SMOKE_WINDOW, cost)
            c, tr = r.counts, r.trades
            assert c["candidates"] == c["taken"] + c["busy"] + c["dropped_stop"] + c["dropped_target"], v.id
            assert c["taken"] == len(tr) and c["unfilled"] == 0 and r.kind == "events"
            if len(tr):
                assert set(tr.reason) <= REASONS[rule], v.id
                assert set(tr.side) <= ({1} if filt == "LO" else {-1, 1})
                assert (tr.risk > 0).all() and np.isfinite(tr.r).all() and np.isfinite(tr.pnl).all()
                assert (tr.exit_ix >= tr.entry_ix).all()
                assert (tr.entry_time >= pd.Timestamp(SMOKE_WINDOW[0], tz="UTC")).all()
                assert (tr.exit_time <= pd.Timestamp(SMOKE_END, tz="UTC")).all()
                assert len(set(zip(tr.side.tolist(), tr.tag.tolist()))) == len(tr)   # one trade per anchor
                row = {int(bb): q for q, bb in enumerate(E.bar)}
                assert set(tr.bar) <= set(row), v.id                              # every trade is one of the entries
                for t in tr.itertuples(index=False):
                    q = row[int(t.bar)]
                    assert int(t.entry_ix) == int(b.ex[t.bar]) and int(t.side) == int(E.side[q])
                    assert int(t.tag) == int(E.tag[q])
                    if t.reason == "signal":                               # a flip against it, after its bar
                        mask = ex.exit_long if t.side == 1 else ex.exit_short
                        j = int(np.searchsorted(b.ex, int(t.exit_ix)))
                        assert j > int(t.bar) and int(b.ex[j]) == int(t.exit_ix) and mask[j], v.id
            M.metrics(r)                                    # the driver's scores can be computed (not shown)
            n_runs += 1
    assert n_runs == 2 * len(SMOKE_ROWS)


# ───────────────────────────── (g) claims 11 and 12 (PREREG 8; readings R9 and R10) ─────────────────────────────
#
# The claim windows (M.WINDOWS patched; nothing of the real windows is read): on the hand-made 1H bars from T0,
# Development holds bars 10 .. 39 (they open at or after 10:00 on the first day and close by 16:00 on the second) and
# Validation bars 40 .. 63 (claim 11's market of 64 hours) or 40 .. 71 (claim 12's of 72 hours).

C_DEV = ("2019-03-04 10:00", "2019-03-05 16:00")


def c_val(hours):
    return (C_DEV[1], str(TM.utc(T0 + hours * HOUR))[:16])


def claim_evidence(monkeypatch, m1, profs, hours, symbol=GOLD):
    """A ``tradeiq2.Evidence`` over the hand-made market ``m1`` (``hours`` 1H bars from T0) whose Context holds the
    profiles ``profs`` ({tf: Prof}), with the claim windows above and the 36 SP rows of ``symbol`` as its results (the
    POC rows net 10 in Development and 1 in Validation, the placebo rows 5 and 2)."""
    D = pytest.importorskip("backtesting.research.tradeiq2")
    monkeypatch.setitem(M.WINDOWS, "dev", C_DEV)
    monkeypatch.setitem(M.WINDOWS, "val", c_val(hours))
    mk = M.TMarket2(symbol, m1)
    rows = [{"vid": v.id, "module": "swing", "symbol": symbol, "tf": v.tf, "script": v.script, "family": v.family,
             "group": "SP", "eligible": v.eligible, "info": v.info, "params": json.dumps(dict(v.params)),
             "window": w, "net": net}
            for v in RS.variants(symbol)
            for w, net in (("dev", 10.0 if v.eligible else 5.0), ("val", 1.0 if v.eligible else 2.0))]
    res = pd.DataFrame(rows)
    grid = res[res.window == "dev"][["vid", "params"]].reset_index(drop=True)
    ev = D.Evidence(Path("."), res, grid, pd.DataFrame(), {"swing": RS}, loader=lambda s, end: mk)
    for tf, p in profs.items():
        RS.use_profile(ev.context(symbol), tf, p.out())
    return D, ev


def claim11_market(n=64):
    """1H bars at 100.00 with a high of 100.20 and a low of 99.80, except the bars named, and eight finished legs (the
    50% level of each in its comment). Spans (claim 11): 1 = bars 6 .. 12 (cut by Development's start), 2 = 13 .. 20
    and 3 = 21 .. 30 (Development), 4 = 31 .. 45 (across the two windows: cut by Validation's start), 5 = 46 .. 50,
    6 = 51 .. 55 (leg 5 has no POC) and 7 = 56 .. 60 (Validation); leg 7 (flip 60) is the last and has none."""
    o = np.full(n, 100.0)
    c, h, lo, v = o.copy(), o + 0.2, o - 0.2, np.ones(n)
    h[11] = 101.0          # span 1: leg 0's POC (and its 50% level)
    lo[12] = 98.9          # leg 1's flip bar: through leg 1's POC and 50% level, which exist only from its close
    lo[16] = 99.6          # span 2: leg 1's POC exactly (equality counts), not its 50% level
    h[30] = 100.6          # span 3's end bar (leg 3's flip): leg 2's POC exactly and its 50% level
    lo[42] = 99.3          # span 4: leg 3's POC and 50% level
    h[48] = 100.35         # span 5: leg 4's 50% level, not its POC
    lo[53] = 99.0          # span 6: leg 5's 50% level
    p = Prof(n)
    p.leg(5, -1, 101.0, lo=99.0, hi=102.0)                            # 100.50
    p.leg(12, 1, 99.6, lo=98.0, hi=100.0)                             # 99.00
    p.leg(20, -1, 100.6, lo=99.0, hi=101.6)                           # 100.30
    p.leg(30, 1, 99.3, lo=98.5, hi=100.5)                             # 99.50
    p.leg(45, -1, 100.9, lo=99.5, hi=101.1)                           # 100.30
    p.leg(50, 1, NAN, lo=99.0, hi=100.0)                              # 99.50
    p.leg(55, -1, 100.4, lo=99.6, hi=101.0)                           # 100.30
    p.leg(60, 1, 99.9, lo=99.0, hi=100.5)                             # 99.75; every bar after it touches its POC
    # the forming leg's levels (claim 11's verdict part): POC / 50% level per bar, the 50% level in the comment
    p.forming(6, 13, (5, 101.0), (2, 99.0), poc=100.0)                # 100.00: span 1 (cut) touches both
    p.forming(13, 21, (12, 98.0), (5, 101.0), poc=100.1)              # 99.50: span 2, only the POC (lo[16] 99.6)
    p.forming(21, 31, (20, 101.0), (12, 99.0), poc=100.1)             # 100.00: span 3, both
    p.forming(31, 46, (30, 101.0), (20, 99.0), poc=100.0)             # span 4 (cut by Validation's start)
    p.forming(46, 48, (-1, NAN), (40, 99.6), poc=100.0)               # no 50% level: these POC touches do not count
    p.forming(48, 51, (45, 100.6), (40, 99.6), poc=101.5)             # 100.10: span 5, only the 50% level
    p.forming(56, 61, (55, 97.0), (50, 101.0), poc=99.9)              # 99.00: span 7, only the POC; span 6 has none
    return (o, h, lo, c, v), p


# claim 12's pairs: (the up leg's delta, the next leg's high - low); Development's up legs flip at 13, 16, .., 37 and
# Validation's at 43, 46, .., 64, each next leg flipping one bar later from a swing one bar before the up leg's flip
C12_DEV = [(-0.2, 9.0), (-0.1, 8.0), (-0.3, 7.0), (0.2, 1.0), (0.4, 2.0), (0.1, 3.0), (0.3, 4.0), (0.25, 5.0),
           (0.0, 4.5)]
C12_VAL = [(-0.5, 2.5), (-0.4, 1.5), (0.1, 2.0), (0.2, 3.0), (0.3, 4.0), (0.4, 5.0), (0.5, 6.0), (NAN, 6.5)]


def claim12_market(n=72):
    """``hourly_m1`` (every 1H bar's true range 1.00, so ATR(14) is 1.00 from bar 13) with bar 61's high at 101.50
    (true range 2.00: ATR(14) 15/14 there), and the legs: an up leg flipping at 8 whose next leg starts at bar 9
    (before Development), the pairs of C12_DEV and C12_VAL, an up leg flipping at 39 whose next leg runs from bar 38
    to bar 41 (across the windows), and a last up leg (68) with no next leg. Every leg's ATR(200) is 2.00, which claim
    12 must not read."""
    m1 = hourly_m1(n)
    m1["h"][ix(61, 10)] = 101.5
    p = Prof(n)
    p.leg(8, 1, 99.8, delta=-0.9, atr=2.0).leg(11, -1, 99.8, lo=70.0, hi=100.0, start=9, atr=2.0)
    for first, pairs in ((13, C12_DEV), (43, C12_VAL)):
        for i, (dl, size) in enumerate(pairs):
            u = first + 3 * i
            p.leg(u, 1, 99.8, delta=dl, atr=2.0)
            p.leg(u + 1, -1, 99.8, lo=100.0 - size, hi=100.0, start=u - 1, atr=2.0)
        if first == 13:
            p.leg(39, 1, 99.8, delta=-0.9, atr=2.0).leg(41, -1, 99.8, lo=80.0, hi=100.0, start=38, atr=2.0)
    p.leg(68, 1, 99.8, delta=-0.9, atr=2.0)
    return m1, p


def test_g_the_exact_mann_whitney_u_test_by_hand_and_against_every_split():
    mw = RS.mann_whitney_greater
    assert mw([5.0], [1.0, 2.0, 3.0]) == (3.0, pytest.approx(1 / 4))             # x above all: 1 rank of 4
    assert mw([5.0, 6.0], [1.0, 2.0, 3.0]) == (6.0, pytest.approx(1 / 10))       # the top 2 ranks of 5: 1 / C(5, 2)
    assert mw([10.0, 11.0, 12.0], [1.0, 2.0, 3.0, 4.0, 5.0]) == (15.0, pytest.approx(1 / 56))
    assert mw([1.0], [2.0, 3.0]) == (0.0, pytest.approx(1.0))
    assert mw([2.0], [1.0, 3.0]) == (1.0, pytest.approx(2 / 3))
    assert mw([2.0], [2.0, 1.0]) == (1.5, pytest.approx(2 / 3))                  # a tie: midranks 2.5, 2.5, 1
    assert mw([2.5, 1.5], [2.0, 3.0, 4.0, 5.0, 5.6]) == (1.0, pytest.approx(20 / 21))   # ranks 1 and 3 of 7
    assert all(math.isnan(z) for z in mw([], [1.0]) + mw([1.0], []))
    assert (RS._p_text(1 / 56), RS._p_text(20 / 21), RS._p_text(1 / 3003)) == ("p = 0.018", "p = 0.952", "p < 0.001")
    with pytest.raises(ValueError):
        mw([NAN], [1.0])
    # every split of small tied samples, counted
    rng = np.random.default_rng(7)
    for _ in range(60):
        x = rng.integers(0, 4, rng.integers(1, 6)).astype(float)
        y = rng.integers(0, 4, rng.integers(1, 6)).astype(float)
        pooled, m = np.concatenate([x, y]), len(x)

        def u_of(a, b):
            return sum(float(p > q) + 0.5 * float(p == q) for p in a for q in b)
        u0 = u_of(x, y)
        splits = list(itertools.combinations(range(len(pooled)), m))
        ge = sum(u_of(pooled[list(cs)], np.delete(pooled, list(cs))) >= u0 for cs in splits)
        u, p = mw(x, y)
        assert u == u0 and p == pytest.approx(ge / len(splits), abs=1e-12), (x, y)


def test_g_the_verdict_of_each_window(monkeypatch):
    """Claim 11: strictly more legs touch the POC (a tie does not hold) and the one-sided sign test on the discordant
    legs gives p strictly below 0.05; claim 12: a strictly higher median after a negative delta and p strictly below
    0.05; no verdict (NaN) without a leg or a test."""
    h11 = RS.claim11_holds
    x11 = {"n": 40, "poc": 30, "fifty": 22, "testable": True, "p": 0.049}
    assert h11(x11) is True and h11(dict(x11, p=0.05)) is False and h11(dict(x11, fifty=30)) is False
    assert h11(dict(x11, poc=20, p=0.01)) is False and math.isnan(h11(dict(x11, testable=False)))
    assert math.isnan(h11({"n": 0, "poc": 0, "fifty": 0, "testable": False, "p": NAN}))
    # the sign test by hand: P(X >= k), X ~ Binomial(n, 1/2)
    st = RS.sign_test_greater
    assert st(5, 5) == 1 / 32 and st(4, 5) == 6 / 32 and st(0, 3) == 1.0 and st(7, 10) == pytest.approx(176 / 1024)
    assert math.isnan(st(0, 0))
    with pytest.raises(ValueError):
        st(4, 3)
    # testable from 5 discordant legs (0.5 ** 5 < 0.05), not from 4 (0.5 ** 4 >= 0.05); the boundary is strict
    c = RS._claim11_counts
    five = c(np.array([1, 1, 1, 1, 1, 1, 0], bool), np.array([0, 0, 0, 0, 0, 1, 0], bool))
    assert (five["poc_only"], five["fifty_only"], five["testable"]) == (5, 0, True) and five["p"] == 1 / 32
    assert h11(five) is True
    four = c(np.array([1, 1, 1, 1, 1], bool), np.array([0, 0, 0, 0, 1], bool))
    assert (four["poc_only"], four["testable"]) == (4, False) and math.isnan(h11(four))
    mixed = c(np.array([1, 1, 1, 1, 0, 0], bool), np.array([0, 0, 0, 0, 1, 1], bool))   # 4 against 2: p = 22 / 64
    assert mixed["testable"] and mixed["p"] == 22 / 64 and h11(mixed) is False
    h12 = RS.claim12_holds
    x = {"testable": True, "median_neg": 3.1, "median_pos": 3.0, "p": 0.049}
    assert h12(x) is True and h12(dict(x, p=0.05)) is False and h12(dict(x, median_neg=3.0)) is False
    assert h12(dict(x, median_neg=2.0, p=0.01)) is False and math.isnan(h12(dict(x, testable=False)))
    monkeypatch.setattr(RS, "CLAIM_P", 1 / 16)                            # the boundary: 0.5 ** 4 == CLAIM_P
    assert not c(np.array([1, 1, 1, 1], bool), np.zeros(4, bool))["testable"]
    assert c(np.array([1, 1, 1, 1, 1], bool), np.zeros(5, bool))["testable"]


def test_g_claim_11_spans_and_touches_by_hand():
    bars, p = claim11_market()
    _, h, lo, _, _ = bars
    prof = RS._pack(p.out(), 64)
    sp = RS.claim11_spans(prof)
    assert list(sp["leg"]) == list(range(7)) and list(sp["first"]) == [6, 13, 21, 31, 46, 51, 56]
    assert list(sp["end"]) == [12, 20, 30, 45, 50, 55, 60] and list(sp["dir"]) == [-1, 1, -1, 1, -1, 1, -1]
    assert list(sp["poc"][:5]) == [101.0, 99.6, 100.6, 99.3, 100.9] and np.isnan(sp["poc"][5])
    assert list(RS.touches(h, lo, sp["first"], sp["end"], sp["poc"])) == [True, True, True, True, False, False,
                                                                          False]
    assert list(RS.touches(h, lo, sp["first"], sp["end"], sp["fifty"])) == [True, False, True, True, True, True,
                                                                            False]
    # the flip bar is not read: read from leg 1's flip bar (12), span 2 would touch its 50% level (99.00)
    assert RS.touches(h, lo, [12], [20], [99.0])[0] and not RS.touches(h, lo, [13], [20], [99.0])[0]
    assert not RS.touches(h, lo, [21], [29], [100.6])[0]                 # span 3 touches only on its end bar
    with pytest.raises(ValueError):
        RS.touches(h, lo, [5], [64], [100.0])                            # a span past the bars
    one = RS._pack(Prof(64).leg(30, 1, 99.9).out(), 64)
    assert len(RS.claim11_spans(one)["first"]) == 0                      # a single leg: no span
    # the forming levels (the verdict part): per bar, both NaN where either is missing
    fp, f5 = RS.forming_levels(prof)
    assert np.isnan(fp[46:48]).all() and np.isnan(f5[46:48]).all() and prof["f_poc"][46] == 100.0
    assert np.isnan(fp[51:56]).all() and fp[56] == 99.9 and f5[56] == 99.0 and f5[48] == pytest.approx(100.1)
    assert list(RS.touches_at(h, lo, sp["first"], sp["end"], fp)) == [True, True, True, True, False, False, True]
    assert list(RS.touches_at(h, lo, sp["first"], sp["end"], f5)) == [True, False, True, True, True, False,
                                                                      False]
    # read without the both-levels rule, span 5's bars 46 .. 47 would touch the POC
    assert RS.touches_at(h, lo, [46], [50], prof["f_poc"])[0] and not RS.touches_at(h, lo, [46], [50], fp)[0]
    assert RS.touches_at(h, lo, [13], [13], np.full(64, 100.2))[0]    # equality counts
    assert not RS.touches_at(h, lo, [13], [13], np.full(64, 100.21))[0] and len(RS.touches_at(h, lo, [], [], fp)) == 0
    with pytest.raises(ValueError):
        RS.touches_at(h, lo, [5], [64], fp)                              # a span past the bars
    with pytest.raises(ValueError):
        RS.touches_at(h, lo, [5], [6], fp[:10])                          # one level per bar


def test_g_claim_12_pairs_and_sizes_by_hand():
    m1, p = claim12_market()
    ctx = ctx_of(m1)
    a = ctx.atr("1H")
    assert np.isnan(a[12]) and a[13] == 1.0 and a[60] == 1.0 and a[61] == pytest.approx(15 / 14)
    prof = RS._pack(p.out(), 72)
    pr = RS.claim12_pairs(prof)
    ups = [8] + [13 + 3 * i for i in range(9)] + [39] + [43 + 3 * j for j in range(8)]
    assert list(pr["flip"]) == ups and list(pr["leg"]) == list(range(0, 37, 2)) and list(pr["next"]) == \
        list(range(1, 38, 2))
    assert list(pr["next_first"]) == [9] + [u - 1 for u in ups[1:10]] + [38] + [u - 1 for u in ups[11:]]
    assert list(pr["next_end"]) == [11] + [u + 1 for u in ups[1:10]] + [41] + [u + 1 for u in ups[11:]]
    assert list(pr["sign"]) == [-1, -1, -1, -1, 1, 1, 1, 1, 1, 0, -1, -1, -1, 1, 1, 1, 1, 1, 0]   # 0 and NaN: 0
    size = RS.next_leg_size(prof, a, pr)
    assert np.isnan(size[0])                                             # no ATR(14) at bar 8 yet
    assert list(size[1:10]) == [s for _, s in C12_DEV] and size[10] == 20.0
    assert list(size[11:17]) == [s for _, s in C12_VAL[:6]]
    assert size[17] == pytest.approx(6.0 * 14 / 15)                      # the ATR(14) of the up leg's flip bar (61)
    a64 = 15 / 14
    for _ in range(3):                                                    # Wilder's ATR(14) decays back: bars 62-64
        a64 = (13 * a64 + 1.0) / 14
    assert size[18] == pytest.approx(6.5 / a64) and a[62] != a[61]
    # a window too small for the test: Validation's first three pairs only (bars 40 .. 50)
    b = ctx.bars("1H")
    win = (b.t >= M.s_of(C_DEV[1])) & (b.tc <= T0 + 51 * HOUR)
    x = RS.claim12_stats(prof, a, win)
    assert (x["n_neg"], x["n_pos"], x["n_none"], x["cut"]) == (2, 1, 0, 1)
    assert x["u"] == 1.0 and x["p"] == pytest.approx(2 / 3) and not x["testable"]     # 1 / C(3, 2) >= 0.05
    assert x["median_neg"] == 2.0 and x["median_pos"] == 2.0
    # the boundary is strict: Development's first six pairs (bars 12 .. 29), 3 against 3, 1 / C(6, 3) = 0.05 exactly
    win = (b.t >= T0 + 12 * HOUR) & (b.tc <= T0 + 30 * HOUR)
    x = RS.claim12_stats(prof, a, win)
    assert (x["n_neg"], x["n_pos"], x["n_none"], x["cut"]) == (3, 3, 0, 0) and x["u"] == 9.0
    assert x["p"] == pytest.approx(0.05) and not x["testable"] and math.isnan(RS.claim12_holds(x))
    win = (b.t >= T0 + 12 * HOUR) & (b.tc <= T0 + 33 * HOUR)            # 3 against 4: 1 / 35 < 0.05
    x = RS.claim12_stats(prof, a, win)
    assert (x["n_neg"], x["n_pos"]) == (3, 4) and x["testable"] and x["p"] == pytest.approx(1 / 35)


def test_g_claim_11_on_a_synthetic_evidence(monkeypatch):
    bars, p = claim11_market()
    D, ev = claim_evidence(monkeypatch, m1_of_hours(*bars), {"1H": p, "4H": Prof(16)}, 64)
    assert ev.symbols == [GOLD] and list(np.flatnonzero(ev.in_window(GOLD, "1H", "dev"))) == list(range(10, 40))
    assert list(np.flatnonzero(ev.in_window(GOLD, "1H", "val"))) == list(range(40, 64))
    rows = RS.claim11(ev)
    assert [r["symbol"] for r in rows] == [GOLD] * 4 and [r["rows"][:3] for r in rows] == ["1H:", "1H:", "4H:", "4H:"]
    nt = "; not tested (too few legs touch only one level for p < 0.05)"
    r = rows[0]                                                           # the verdict part: the forming levels
    assert r["part"].startswith("price touches the forming leg's POC") and "f_poc" in r["note"]
    assert r["dev"] == ("POC touched in 2/2 legs (100.0%), the 50% level in 1/2 (50.0%); only the POC 1, only the 50% "
                        "level 0" + nt + "; 1 left out (began before the window)")
    assert r["val"] == ("POC touched in 1/2 legs (50.0%), the 50% level in 1/2 (50.0%); only the POC 1, only the 50% "
                        "level 1" + nt + "; 1 left out (began before the window); 1 without a level")
    assert math.isnan(r["dev_ok"]) and math.isnan(r["val_ok"]) and r["verdict"] == "cannot be tested"
    assert r["start"] == str(TM.utc(T0 + 13 * HOUR)) and r["end"] == str(TM.utc(T0 + 61 * HOUR))   # bars 13 .. 60
    i = rows[1]                                                           # information: the just-finished leg's
    assert i["part"].endswith("(information)") and i["verdict"] == "information" and "legs.poc" in i["note"]
    assert i["dev"] == ("POC touched in 2/2 legs (100.0%), the 50% level in 1/2 (50.0%); only the POC 1, only the 50% "
                        "level 0" + nt + "; 1 left out (began before the window)")
    assert i["val"] == ("POC touched in 0/2 legs (0.0%), the 50% level in 1/2 (50.0%); only the POC 0, only the 50% "
                        "level 1" + nt + "; 1 left out (began before the window); 1 without a level")
    assert math.isnan(i["dev_ok"]) and math.isnan(i["val_ok"]) and (i["start"], i["end"]) == (r["start"], r["end"])
    for q in rows[2:]:                                                    # 4H: no leg
        assert q["dev"] == q["val"] == "no leg" and "start" not in q
        assert math.isnan(q["dev_ok"]) and math.isnan(q["val_ok"])
    assert rows[2]["verdict"] == "cannot be tested" and rows[3]["verdict"] == "information"
    # Development's counts: two legs, one of them discordant, so no test
    st = RS.claim11_stats(RS.profile(ev.context(GOLD), "1H"), *bars[1:3], ev.in_window(GOLD, "1H", "dev"))
    assert (st["n"], st["poc_only"], st["fifty_only"], st["testable"]) == (2, 1, 0, False)
    # through the driver's registry: its window check, then its W1-W3 against the placebo
    got = D.CLAIMS[11][1](ev)
    assert got[:4] == rows and len(got) == 5 and got[4]["dev"] == "12/12" and got[4]["val"] == "0/12"
    cl, errors = D.claims_table(ev, numbers=[11])
    assert errors == [] and list(cl.verdict) == ["cannot be tested", "information", "cannot be tested",
                                                 "information", "mixed"]
    # nothing outside the windows is read: bars 0 .. 9 through every level change no row
    o, h, lo, c, v = (x.copy() for x in bars)
    h[:10], lo[:10] = 110.0, 90.0
    with pytest.MonkeyPatch.context() as mp:
        _, ev2 = claim_evidence(mp, m1_of_hours(o, h, lo, c, v), {"1H": p, "4H": Prof(16)}, 64)
        assert RS.claim11(ev2) == rows
    # the samples, counted without any touch
    cc = RS.claim_counts(ev.context(GOLD), "dev").set_index("tf")
    assert cc.loc["1H", ["legs", "c11_legs", "c11_cut", "c11_no_level", "c11f_legs", "c11f_no_level"]].tolist() == \
        [8, 2, 1, 0, 2, 0]
    cv = RS.claim_counts(ev.context(GOLD), c_val(64)).set_index("tf")
    assert cv.loc["1H", ["c11_legs", "c11_cut", "c11_no_level", "c11f_legs", "c11f_no_level"]].tolist() == \
        [2, 1, 1, 2, 1]
    assert cc.loc["4H", ["legs", "c11_legs", "c11_cut", "c11f_legs"]].tolist() == [0, 0, 0, 0]


def test_g_claim_12_on_a_synthetic_evidence(monkeypatch):
    m1, p = claim12_market()
    D, ev = claim_evidence(monkeypatch, m1, {"1H": p, "4H": Prof(18)}, 72)
    rows = RS.claim12(ev)
    r = rows[0]
    # Development: after delta < 0 the next legs are 9, 8 and 7 ATR, after delta > 0 1 .. 5: U = 15 of 15, p = 1 / 56
    assert r["dev"] == ("delta < 0: 3 up legs, median next leg 8.00 ATR; delta > 0: 5, median 3.00 ATR; U 15, "
                        "one-sided p = 0.018; 1 with a delta of 0 or none; 1 left out (began before the window)")
    # Validation: 2.5 and 1.5 ATR against 2, 3, 4, 5 and 6 / (15 / 14) = 5.6: ranks 1 and 3 of 7, p = 20 / 21
    assert r["val"] == ("delta < 0: 2 up legs, median next leg 2.00 ATR; delta > 0: 5, median 4.00 ATR; U 1, "
                        "one-sided p = 0.952; 1 with a delta of 0 or none; 1 left out (began before the window)")
    assert r["dev_ok"] is True and r["val_ok"] is False and "verdict" not in r
    assert r["start"] == str(TM.utc(T0 + 12 * HOUR)) and r["end"] == str(TM.utc(T0 + 66 * HOUR))   # bars 12 .. 65
    assert "tick volume" in r["note"]
    q = rows[1]
    assert q["verdict"] == "cannot be tested" and q["dev"].endswith("not tested (a group is empty or too small for "
                                                                    "p < 0.05)")
    st = RS.claim12_stats(RS.profile(ev.context(GOLD), "1H"), ev.context(GOLD).atr("1H"), ev.in_window(GOLD, "1H",
                                                                                                    "dev"))
    assert st["p"] == pytest.approx(1 / 56) and st["testable"] and (st["median_neg"], st["median_pos"]) == (8.0, 3.0)
    got = D.CLAIMS[12][1](ev)
    assert got == rows
    cl, errors = D.claims_table(ev, numbers=[12])
    assert errors == [] and list(cl.verdict) == ["mixed", "cannot be tested"]
    cc = RS.claim_counts(ev.context(GOLD), "dev").set_index("tf")
    assert cc.loc["1H", ["c12_neg", "c12_pos", "c12_none", "c12_cut", "c12_no_size"]].tolist() == [3, 5, 1, 1, 0]
    assert cc.loc["1H", "c12_min_p"] == pytest.approx(1 / 56) and math.isnan(cc.loc["4H", "c12_min_p"])
    cv = RS.claim_counts(ev.context(GOLD), "val").set_index("tf")
    assert cv.loc["1H", ["c12_neg", "c12_pos", "c12_none", "c12_cut"]].tolist() == [2, 5, 1, 1]
    # one window testable, the other not: the part cannot be tested (Validation cut to bars 40 .. 50: 2 against 1)
    with pytest.MonkeyPatch.context() as mp:
        _, ev3 = claim_evidence(mp, m1, {"1H": p, "4H": Prof(18)}, 51)
        r3 = RS.claim12(ev3)[0]
        assert r3["dev"] == r["dev"] and r3["dev_ok"] is True and math.isnan(r3["val_ok"])
        assert r3["verdict"] == "cannot be tested" and r3["val"].startswith("delta < 0: 2 up legs")
    # a BTC evidence reads its profile as the rules do (the Binance volume's cache key): the note names it
    _, evb = claim_evidence(monkeypatch, m1, {"1H": p, "4H": Prof(18)}, 72, symbol=BTC)
    rb = RS.claim12(evb)
    assert [x["dev"] for x in rb] == [x["dev"] for x in rows] and "Binance BTCUSDT volume" in rb[0]["note"]


def test_g_a_claim_row_outside_the_windows_is_refused_by_the_driver(monkeypatch):
    """The rows carry the first open and the last close they counted; the driver's window check reads them."""
    m1, p = claim12_market()
    D, ev = claim_evidence(monkeypatch, m1, {"1H": p, "4H": Prof(18)}, 72)
    rows = RS.claim12(ev)
    ev.check_rows(rows, "swing.claim12")
    with pytest.raises(D.ClaimWindowError):
        ev.check_rows([dict(rows[0], start="2019-03-03 23:00")], "swing.claim12")


def ref_claim11(p, h, lo, mask, levels="forming"):
    """Claim 11 by a plain loop over the finished legs (the transcription of reading R9): the forming leg's levels per
    bar (the verdict part), or the just-finished leg's (information)."""
    legs = p["legs"]
    fb = [int(x) for x in legs["flip_bar"]]
    out = dict(n=0, poc=0, fifty=0, poc_only=0, fifty_only=0, cut=0)
    for k in range(len(fb) - 1):
        a, z = fb[k] + 1, fb[k + 1]
        if not mask[z]:
            continue
        if not mask[a]:
            out["cut"] += 1
            continue
        if levels == "last":
            lp, lf = float(legs["poc"].iloc[k]), float(legs["fifty"].iloc[k])
            if not (math.isfinite(lp) and math.isfinite(lf)):
                continue
            tp = any(lo[t] <= lp <= h[t] for t in range(a, z + 1))
            t5 = any(lo[t] <= lf <= h[t] for t in range(a, z + 1))
        else:
            both = [t for t in range(a, z + 1) if math.isfinite(float(p["f_poc"][t]))
                    and math.isfinite(float(p["f_lo"][t])) and math.isfinite(float(p["f_hi"][t]))]
            if not both:
                continue
            tp = any(lo[t] <= float(p["f_poc"][t]) <= h[t] for t in both)
            t5 = any(lo[t] <= (float(p["f_lo"][t]) + float(p["f_hi"][t])) / 2.0 <= h[t] for t in both)
        out["n"] += 1
        out["poc"] += tp
        out["fifty"] += t5
        out["poc_only"] += tp and not t5
        out["fifty_only"] += t5 and not tp
    d = out["poc_only"] + out["fifty_only"]
    out["p"] = sum(math.comb(d, i) for i in range(out["poc_only"], d + 1)) / 2 ** d if d else NAN
    return out


def ref_claim12(p, atr, mask):
    """Claim 12's two groups by a plain loop (the transcription of reading R10)."""
    legs = p["legs"]
    neg, pos, none, cut = [], [], 0, 0
    for j in range(len(legs) - 1):
        if int(legs["dir"].iloc[j]) != 1:
            continue
        s0, z = int(legs["start_bar"].iloc[j + 1]), int(legs["flip_bar"].iloc[j + 1])
        if not mask[z]:
            continue
        if s0 < 0 or not mask[s0]:
            cut += 1
            continue
        a = float(atr[int(legs["flip_bar"].iloc[j])])
        size = (float(legs["hi"].iloc[j + 1]) - float(legs["lo"].iloc[j + 1])) / a if a > 0 else NAN
        if not math.isfinite(size):
            continue
        d = float(legs["delta_pct"].iloc[j])
        if d < 0:
            neg.append(size)
        elif d > 0:
            pos.append(size)
        else:
            none += 1
    return neg, pos, none, cut


@pytest.mark.parametrize("tf", ["1H", "4H"])
def test_g_the_claims_on_the_real_port_equal_a_plain_transcription(syn, tf):
    ctx = syn["ctx"]
    b = ctx.bars(tf)
    p = RS.profile(ctx, tf)
    atr = np.asarray(ctx.atr(tf))
    n_total = n_u = 0
    for a, z in ((T0 + 10 * 86400, T0 + 80 * 86400), (T0 + 80 * 86400, T0 + 150 * 86400)):
        mask = (b.t >= a) & (b.tc <= z)
        for lv in ("forming", "last"):
            got, want = RS.claim11_stats(p, b.h, b.l, mask, lv), ref_claim11(p, b.h, b.l, mask, lv)
            pw = want.pop("p")
            assert {k: got[k] for k in want} == want, (tf, a, lv)
            assert (math.isnan(pw) and math.isnan(got["p"])) or got["p"] == pytest.approx(pw, abs=1e-15), (tf, a, lv)
            assert got["testable"] == (0.5 ** (got["poc_only"] + got["fifty_only"]) < 0.05 and
                                       got["poc_only"] + got["fifty_only"] > 0)
            assert len(got["first"]) == got["n"] and mask[got["first"]].all() and mask[got["end"]].all()
            assert got["cut"] <= 1                                       # spans do not overlap: one crosses a start
        with pytest.raises(ValueError):
            RS.claim11_stats(p, b.h, b.l, mask, "drawn")
        x = RS.claim12_stats(p, atr, mask)
        neg, pos, none, cut = ref_claim12(p, atr, mask)
        assert (x["n_neg"], x["n_pos"], x["n_none"], x["cut"]) == (len(neg), len(pos), none, cut), (tf, a)
        if neg and pos:
            assert x["median_neg"] == np.median(neg) and x["median_pos"] == np.median(pos)
            assert x["u"] == sum(float(u > v) + 0.5 * float(u == v) for u in neg for v in pos)
            n_u += 1
        n_total += got["n"] + x["n_neg"] + x["n_pos"]
    # 1H: 26 spans and 13 pairs (1 after a negative delta) in each window; 4H: 5 + 2 and 7 + 3
    assert n_total >= (60 if tf == "1H" else 12) and n_u >= (2 if tf == "1H" else 0), (n_total, n_u)
