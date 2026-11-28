"""
Port A of "Wyckoff [theUltimator5]" (``backtesting/research/tradeiq2_ind_wyckoff.py``), study 2.

1. The helpers by hand: Pine rounding, the phase lengths, the robust edge, the scores, the pivots.
2. One hand-computed case per trap of the specification's risk list (the study's ``maps/wyckoff.md`` section 6),
   named after it (``test_trap01_...`` to ``test_trap12_...``). Most drive one or two bars of the engine from a
   hand-built state (``W.run`` on hand-built series), so every condition can be checked by hand; the arithmetic is in
   the comments.
3. Properties on synthetic bars: truncation invariance (no look-ahead), the mirror (negated prices), the compiled
   kernel against its plain Python body, the contract's invariants, the no-volume switch, inputs left alone.
4. Real bars (skipped when the tick store is absent; bars up to 2024-06-30 only, the hold-out is never loaded): a smoke
   check of both symbols on 1H / 4H / 1D, the specification's cross-check vectors (from an unreviewed scratch port;
   each was investigated, see the comments), the start-invariance and volume-source facts. Counts only, no profit.
"""

from __future__ import annotations

import gc
import math

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_wyckoff as W
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

nan = math.nan
R = {name: i for i, name in enumerate(W._ROWS)}
F = {name: i for i, name in enumerate(W.FIELDS)}
MT = 0.001


# ───────────────────────────── helpers ─────────────────────────────

def bars(n, o=94.0, h=95.0, l=93.0, c=94.0, v=100.0):
    """n identical bars (arrays, so single bars can be edited)."""
    return [np.full(n, float(x)) for x in (o, h, l, c, v)]


def make_pre(o, h, l, c, v, live=4, **cols):
    """``W.series`` of the bars with no pivot candidates, the swing length ``live`` on every bar (also the climax
    bar's ``preLen``), no trend score (``TBVALID`` 0), and the named columns of P overridden (scalars or arrays)."""
    pre = W.series(o, h, l, c, v, np.arange(len(c)) * 3600.0, mintick=MT)
    pre["PHC"][:] = nan
    pre["PLC"][:] = nan
    P = pre["P"]
    P[:, R["LIVE"]] = live
    P[:, R["PRE"]] = live
    P[:, R["TBVALID"]] = 0.0
    for k, val in cols.items():
        P[:, R[k]] = val
    return pre


def state(**kw):
    S = W.TEMPLATE.copy()
    for k, val in kw.items():
        S[F[k]] = val
    return S


def glob(regime=0, last_pl=nan, last_ph=nan, used=(0, 0, 0)):
    G = np.array([regime, last_pl, last_ph, *used], np.float64)
    assert len(G) == W.NG
    return G


def step(pre, S, G, t0, t1):
    return W.run(pre, S, G, t0, t1, mintick=MT, tf_seconds=3600.0)


def phase_b_accum(t, **kw):
    """A selling-climax campaign in Phase B, mature on bar t (checked in test_trap01): SC low 90 (climax effort 300,
    spread 10, ATR 4), AR 100, so a 10-point range of 2.5 climax ATRs; two secondary tests (efforts 110 + 90, spreads
    7 + 5: means 100 and 6; the last one 90 / 5); one opposite test (effort 100, spread 6, bar 30, at 99.5); two
    traversals; Phase B from bar 10; no failed test; a birth trend of -40."""
    base = dict(STOP=1, PHASE=2, START=0, PIVLEN=4, BIRTH=-40.0, CLBAR=0, CLPX=90.0, CLEFF=300.0, CLSPR=10.0,
                CLATR=4.0, ABSORBED=1, OLO=90.0, RLO=90.0, OHI=100.0, RHI=100.0, ARRUNPX=100.0, ARRUNBAR=5, AROK=1,
                ARBAR=5, STCOUNT=2, STN=2, STEFF=200.0, STSPR=12.0, LGEFF=90.0, LGSPR=5.0, STBAR=20, STPX=91.0,
                OPPCOUNT=1, OPN=1, OPEFF=100.0, OPSPR=6.0, OPLASTBAR=30, OPLASTPX=99.5, TRAV=2, LZONE=1, LZONEBAR=30,
                BSTART=10, LASTACT=t - 5, LASTEVTIME=0.0, CFPRIOR=1, CFCLIMAX=1, CFAR=1, CFST=1)
    base.update(kw)
    return state(**base)


def outside_pivot_bars(n=110, j=96, h_j=95.5):
    """Bars inside the 90-100 range (close 94) with bar j an outside bar from 91.5 to h_j, close 93.5, effort 80:
    its spread 4 and close position (93.5 - 91.5) / 4 = 0.5. ATR 4, average effort 100."""
    o, h, l, c, v = bars(n)
    o[j], h[j], l[j], c[j], v[j] = 93.5, h_j, 91.5, 93.5, 80.0
    return o, h, l, c, v


ATR4 = dict(A=4.0, ATRRAW=4.0, APREV=4.0, AVG=100.0, AVGRAW=100.0, AVGPREV=100.0)


def wyckoff_like(n, seed, start=2000.0):
    """Synthetic bars with Wyckoff-like structure: trends, each ending in a wide heavy climax bar, then ranges with
    occasional probes. Seeds 2 and 3 give full campaigns (secondary tests, springs, SOS, entries, Phase E)."""
    rng = np.random.default_rng(seed)
    c, o, h, l, v = (np.empty(n) for _ in range(5))
    px, i, mode, left, drift, level, width, climax = start, 0, "trend", 0, 0.0, start, 10.0, False
    while i < n:
        if left <= 0:
            if mode == "trend":
                mode, left, level, width = "range", int(rng.integers(60, 260)), px, rng.uniform(4, 12)
            else:
                mode, left, drift = "trend", int(rng.integers(40, 160)), rng.choice([-1, 1]) * rng.uniform(0.15, 0.5)
            climax = mode == "range"
        op = px
        if mode == "trend":
            step_ = drift + rng.standard_normal()
            vb = 100.0 * rng.uniform(0.7, 1.3)
        else:
            step_ = 0.08 * (level - px) + rng.standard_normal() * 1.2
            if rng.random() < 0.03:
                step_ += rng.choice([-1, 1]) * width * rng.uniform(0.4, 0.9)
            vb = 100.0 * rng.uniform(0.5, 1.1)
        cl = op + step_
        wick = abs(rng.standard_normal()) * 0.6 + 0.2
        hi, lo = max(op, cl) + wick * rng.random(), min(op, cl) - wick * rng.random()
        if climax:
            w = rng.uniform(4, 8)
            if drift < 0:
                lo = min(op, cl) - w
                cl = lo + w * rng.uniform(0.4, 0.8)
                hi = max(op, cl) + 0.3
            else:
                hi = max(op, cl) + w
                cl = hi - w * rng.uniform(0.4, 0.8)
                lo = min(op, cl) - 0.3
            vb = 100.0 * rng.uniform(2.5, 4.0)
            climax = False
        o[i], h[i], l[i], c[i], v[i] = op, hi, lo, cl, round(vb)
        px, left, i = cl, left - 1, i + 1
    return o, h, l, c, v


_SYN = {}


def synthetic(seed, n=6000):
    if (seed, n) not in _SYN:
        o, h, l, c, v = wyckoff_like(n, seed)
        _SYN[(seed, n)] = (o, h, l, c, v, np.arange(n) * 3600.0)
    return _SYN[(seed, n)]


def same(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return False
    if a.dtype.kind == "f" or b.dtype.kind == "f":
        a, b = a.astype(float), b.astype(float)
        return bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))
    return bool(np.array_equal(a, b))


# ───────────────────────────── 1. helpers by hand ─────────────────────────────

def test_contract_keys_and_types():
    o, h, l, c, v, t = synthetic(2, 1500)
    out = W.wyckoff(o, h, l, c, v, t)
    assert tuple(out) == W.CONTRACT_KEYS
    assert set(W.CONTRACT_KEYS) == {"phase", "outcome", "campaign", "range_lo", "range_hi", "hard_lo", "hard_hi",
                                    "ev_sc", "ev_bc", "ev_ar", "ev_st", "ev_spring", "ev_utad", "ev_test", "ev_ctest",
                                    "ev_sos", "ev_sow", "ev_lps", "ev_lpsy", "ev_phase_e", "climax", "climax_px",
                                    "exc", "exc_px", "entry_std", "entry_agg", "entry_con", "in_cde"}
    kinds = {"phase": np.int8, "outcome": np.int8, "campaign": np.int32, "climax": np.int8, "exc": np.int8,
             "entry_std": np.int8, "entry_agg": np.int8, "entry_con": np.int8, "in_cde": np.bool_}
    for k, arr in out.items():
        assert len(arr) == len(c), k
        if k in kinds:
            assert arr.dtype == kinds[k], k
        elif k.startswith("ev_"):
            assert arr.dtype == np.bool_, k
        else:
            assert arr.dtype == np.float64, k


def test_pine_round_and_lengths():
    # math.round ties up; Python's round(4.5) is 4 (banker's rounding)
    assert W._round(2.5) == 3.0 and W._round(4.5) == 5.0 and W._round(4.4999999) == 4.0 and round(4.5) == 4
    assert W._round(0.49999999999999994) == 0.0       # floor(x + 0.5) would give 1
    assert W._round(-2.5) == -2.0 and W._round(-2.6) == -3.0
    assert list(W.pine_round([0.5, 1.5, 2.5, 7.5])) == [1.0, 2.0, 3.0, 8.0]
    # f_excursionRecoveryLimit for p = 2..10: max(3, round(0.75 p)) = 3, 3, 3, 4, 5, 5, 6, 7, 8 (p = 6: 4.5 -> 5)
    assert [W._rec_limit(p) for p in range(2, 11)] == [3, 3, 3, 4, 5, 5, 6, 7, 8]
    # f_phaseBMinBars: (4, 5) -> max(30, round(max(24, 20))) = 30; (4, 10) -> 40; (10, 8) -> min(80, 60) = 60
    assert W._phase_b_min(4, 5.0) == 30 and W._phase_b_min(4, 10.0) == 40 and W._phase_b_min(10, 8.0) == 60
    assert W._phase_b_min(5, 6.1) == 31                # round(30.5) = 31 (ties up)
    # f_phaseCToDMinBars: max(3, int(p / 2)), truncated: 4 -> 3, 7 -> 3, 8 -> 4, 10 -> 5
    assert [W._phase_c_to_d_min(p) for p in (4, 7, 8, 10)] == [3, 3, 4, 5]
    assert [W._phase_a_min(p) for p in (2, 3, 4, 7)] == [6, 6, 8, 14]
    assert [W._phase_d_min(p) for p in (2, 4, 7)] == [4, 4, 7]
    # f_phaseIdleLimit: A with an AR max(45, 6p), without max(30, 4p); B max(125, 20p); C max(50, 8p); D max(100, 16p)
    assert [W._idle_limit(1, True, 4), W._idle_limit(1, False, 10), W._idle_limit(2, False, 7),
            W._idle_limit(3, False, 7), W._idle_limit(4, False, 7), W._idle_limit(5, False, 4)] == [45, 40, 140, 56,
                                                                                                  112, -1]


def test_trend_bars_and_end_tables():
    # trendBars = clamp(round(8 L), 25, 200), trendEnd = clamp(round(0.75 L), 2, 8) for liveLen L = 2..10
    tb_n, tb_e, valid, _, _ = W.trend_parts(np.arange(9.0) + 100, np.ones(9), np.full(9, nan), np.arange(2, 11), MT)
    assert list(tb_n) == [25, 25, 32, 40, 48, 56, 64, 72, 80]
    assert list(tb_e) == [2, 2, 3, 4, 5, 5, 6, 7, 8]
    assert not valid.any()                                          # close[e + n] does not exist on bars 0..8


def test_robust_edge():
    assert W._robust_edge(10.0, nan, nan, 8.0, True) == 9.0          # (10 + 8) / 2
    assert W._robust_edge(10.0, 12.0, nan, 8.0, True) == 9.5         # ((10 + 12) / 2 + 8) / 2
    assert W._robust_edge(10.0, 12.0, 9.0, 8.0, True) == 10.0        # median 10
    assert W._robust_edge(18.0, nan, nan, 20.0, False) == 19.0       # a high edge never above the original
    assert W._robust_edge(7.0, nan, nan, 8.0, True) == 8.0           # a low edge never below the original
    assert W._robust_edge(nan, nan, nan, 8.0, True) == 8.0
    # the median as written: e1 + e2 + e3 - max - min, in that order of rounding
    e1, e2, e3 = 1800.123, 1800.456, 1799.999
    assert W._robust_edge(e1, e2, e3, 1700.0, True) == e1 + e2 + e3 - e2 - e3


def test_scores_milestones():
    # f_structureConfidence: 50 after the ST, 65 at a Phase C test, 80 at the SOS, 90 at the LPS, 100 in Phase E
    sc = W._structure_confidence
    assert sc(True, True, True, True, False, False, False, False) == 50
    assert sc(True, True, True, True, True, False, False, False) == 65
    assert sc(True, True, True, True, True, True, False, False) == 80
    assert sc(True, True, True, True, True, True, True, False) == 90
    assert sc(True, True, True, True, True, True, True, True) == 100
    vs = W._validation_score
    assert vs(40.0, True, 2.5, 2, 1, 2, True, 5.25, True, True, True, False) == 100     # capped
    assert vs(40.0, True, 2.5, 2, 1, 2, True, 5.25, True, False, False, False) == 95    # at most 95 before D
    # trend 5 (|20|), range 5 (1.2: within 1.125..12 only), STs 8 (one), opp or trav 8, cause 5 (1.5): 31
    assert vs(-20.0, False, 1.2, 1, 0, 1, False, 1.5, False, False, False, False) == 31
    assert vs(nan, False, 0.0, 0, 0, 0, False, 0.0, False, False, False, False) == 0     # na trend: nothing
    assert W._cause_units(2, 90, 4, 2.5) == 90 / 24 + 1.0 + 0.5


def test_pivots_strict_and_ties():
    x = np.array([1.0, 2.0, 5.0, 2.0, 1.0, 3.0, 3.0, 1.0, 0.0])
    ph = W.pivots(x, 2, True)
    assert np.isnan(ph[:4]).all() and ph[4] == 5.0                 # x[2] = 5, confirmed 2 bars later
    assert np.isnan(ph[5:]).all()                                  # 3.0, 3.0: a tie is no pivot (strict)
    left, right = W.pivots(x, 2, True, ties="left"), W.pivots(x, 2, True, ties="right")
    assert left[8] == 3.0 and np.isnan(left[7])                    # x[6] equals its left neighbour: bar 6 + 2
    assert right[7] == 3.0 and np.isnan(right[8])                  # x[5] equals its right neighbour: bar 5 + 2
    pl = W.pivots(-x, 2, False)
    assert same(pl, -ph)
    assert np.isnan(W.pivots(x, 5, True)).all()                    # fewer than 11 bars


def test_highest_lowest_na_until_full_length():
    x = np.array([3.0, 1.0, 2.0, 5.0])
    assert same(W.highest(x, 3), [nan, nan, 3.0, 5.0])
    assert same(W.lowest(x, 3), [nan, nan, 1.0, 1.0])
    assert same(W.highest(x, 5), [nan] * 4)


# ───────────────────────────── 2. the traps (maps/wyckoff.md section 6) ─────────────────────────────

def test_trap01_order_of_operations_within_a_bar():
    """The order of section 1.5 is load-bearing. (a) The terminal test of the low side is evaluated before the high
    side: an outside pivot bar that qualifies at both edges gives an ACCUMULATION terminal test, and the high side is
    then skipped because the phase is C; without the pivot low the same bar gives a DISTRIBUTION one. (b) The Phase D
    demotion (step 1) comes before the pivot events (step 6): one bar can demote and enter Phase C again."""
    t = 100
    o, h, l, c, v = outside_pivot_bars()
    # mature on bar 100 (f_matureWS): Phase B, age 100 - 10 = 90 >= f_phaseBMinBars(4, 2.5) = 30, 2 STs, height
    # 10 / 4 = 2.5 ATRs within 1.125..16, support 4 of 4 (1 opposite test, 2 traversals, clean, last ST 90 <= 100 and
    # 5 <= 6 * 1.05)
    S = phase_b_accum(t)
    assert W._mature(S, 4, 4.0, float(t), MT)
    # (a) both pivots on bar 100 (pLen 4: the pivot bar is 96)
    pre = make_pre(o, h, l, c, v, **ATR4)
    pre["PLC"][t, 4], pre["PHC"][t, 4] = 91.5, 95.5
    # low side (reference: the STs, mean effort 100, spread 6, last at 91 on bar 20): later 96 >= 23; near 91.5 <= 90
    # + 4 * 1.25; holds 91.5 >= 90 - 0.6; higher 91.5 >= 91 - 0.6; effort 80 <= 85 and spread 4 <= 5.1 (and <= 6.3);
    # score 80 <= 85, 4 <= 5.1, close position 0.5 >= 0.5: 3
    # high side (reference: the opposite test, 100 / 6, bar 30, 99.5): later 96 >= 33; near 95.5 >= 100 - 5; holds
    # 95.5 <= 100.6; lower 95.5 <= 100.1; 80 <= 85, 4 <= 5.1; score 3 (0.5 <= 0.5): it would qualify as well
    out = step(pre, S, glob(), t, t + 1)
    assert out["ev_ctest"][t] and out["phase"][t] == 3 and out["outcome"][t] == 1
    assert S[F["OUTC"]] == 1 and S[F["TESTSCORE"]] == 3 and S[F["CREADY"]] == t
    # the entry check (Standard): confidence 65 >= 60; validation 10 (|-40|) + 15 + 10 (2.5 ATRs) + 15 (2 STs) + 15
    # (opposite test and 2 traversals) + 10 (clean) + 10 (cause 90/24 + 1 + 0.5 = 5.25) + 10 (terminal) = 95 >= 50;
    # readiness 7 (outcome, phase C, terminal, confidence, validation, (94 - 100) / 4 <= 2, age 0) >= 6; score 3 >= 2
    assert out["dbg_val"][t] == 95 and out["dbg_conf"][t] == 65
    assert out["entry_std"][t] == 1 and out["entry_agg"][t] == 1 and out["entry_con"][t] == 0
    pre["PLC"][t, 4] = nan                                         # without the pivot low: the high side
    out = step(pre, phase_b_accum(t), glob(), t, t + 1)
    assert out["ev_ctest"][t] and out["outcome"][t] == -1 and out["entry_std"][t] == -1
    # (b) Phase D (accumulation) on bar 100 whose last three closes (94) are below mid-range 95 and above the
    # invalidation level 90 - 4 * 0.5 = 88: demotion to B (lastBadBar 100), still mature (support: opposite test,
    # traversals, effort drying up; not clean), then the pivot low of bar 96 makes the terminal test of (a)
    S = phase_b_accum(t, PHASE=4, OUTC=1, STRBAR=80, DSTART=80, CFSTRENGTH=1, CFTEST=1, TESTTIME=1.0, TESTSCORE=3,
                      CREADY=70)
    pre["PLC"][t, 4] = 91.5
    out = step(pre, S, glob(used=(1, 1, 0)), t, t + 1)
    assert out["dbg_demoted"][t] == 1 and out["ev_ctest"][t]
    assert out["phase"][t] == 3 and out["outcome"][t] == 1 and S[F["LASTBAD"]] == t
    assert not out["in_cde"][t]                                    # the demotion on this bar ends the hold (X-S)
    assert out["entry_std"][t] == 0 and out["entry_agg"][t] == 0   # the slots stayed used (trap 9)


def test_trap02_plen_from_the_start_of_the_bar_and_dedup():
    """pLen is read from the state at the start of the bar: a bar that seeds a campaign (whose pivLen = preLen = 5)
    still reads its pivots with liveLen = 3; the next bar reads them with 5. A pivot counts only if its bar is after
    lastPLBar, which a reset leaves alone."""
    n, t = 60, 40
    o, h, l, c, v = bars(n, o=99.0, h=100.0, l=98.0, c=99.0)
    o[t], h[t], l[t], c[t], v[t] = 99.0, 101.0, 97.0, 99.0, 200.0
    pre = make_pre(o, h, l, c, v, live=3, AVGPREV=100.0, APREV=2.0)
    P = pre["P"]
    P[:, R["PRE"]] = 5.0
    # a selling climax on bar 40: trend -20 (TBBASE, no pivots in the window) <= -15, a new low, effort 200 >= 100 *
    # 1.8, spread 4 >= 2 * 1.5, close position 0.5 >= 0.35, effort >= the prior 30-bar high 150: score 6
    P[t, R["TBVALID"]], P[t, R["TBBASE"]], P[t, R["TBSMA"]], P[t, R["TBN"]], P[t, R["TBE"]] = 1, -20.0, 0.0, 25, 2
    P[t, R["NEWLOW"]], P[t, R["EFFHI"]] = 1.0, 150.0
    pre["PLC"][t, 5] = 95.0                                        # a candidate of length 5 only: not read on bar 40
    pre["PLC"][t + 1, 5] = 96.0                                    # read on bar 41 (pLen = pivLen = 5)
    pre["PLC"][t + 1, 3] = 97.0                                    # ... and not this one
    S, G = W.new_state()
    out = step(pre, S, G, t, t + 2)
    assert out["campaign"][t] == t and out["phase"][t] == 1 and S[F["PIVLEN"]] == 5.0   # id = the seed bar
    assert out["dbg_trend"][t] == -20.0
    assert out["dbg_plen"][t] == 3 and np.isnan(out["dbg_pl"][t]) and out["dbg_new_pl"][t] == 0
    assert out["dbg_plen"][t + 1] == 5 and out["dbg_pl"][t + 1] == 96.0 and out["dbg_new_pl"][t + 1] == 1
    assert G[W.G_LASTPL] == t + 1 - 5
    # dedup across a reset: a Phase A campaign (absorbed, AR found, no range high) idle since bar 10 goes stale on
    # bar 60 (60 - 10 > max(45, 6 * 4)); lastPLBar 57 survives it
    n = 70
    o, h, l, c, v = bars(n, o=100.0, h=101.0, l=99.0, c=100.0)
    pre = make_pre(o, h, l, c, v, **ATR4)
    for k in (60, 61, 62):
        pre["PLC"][k, 4] = 99.0                                    # pivot bars 56, 57, 58
    S = state(STOP=1, PHASE=1, START=5, PIVLEN=4, CLBAR=5, CLPX=95.0, CLEFF=300.0, CLSPR=10.0, CLATR=2.0,
              ABSORBED=1, OLO=95.0, RLO=95.0, ARRUNPX=99.0, ARRUNBAR=8, AROK=1, LASTACT=10, CFPRIOR=1, CFCLIMAX=1)
    G = glob(last_pl=57.0)
    out = step(pre, S, G, 60, 63)
    assert out["dbg_reset"][60] == W.RS_STALE and out["campaign"][60] == -1
    assert [out["dbg_new_pl"][k] for k in (60, 61, 62)] == [0.0, 0.0, 1.0]   # bars 56 and 57 are not after 57
    assert G[W.G_LASTPL] == 58.0


def test_trap03_state_outside_the_campaign_is_not_reset():
    """regime, lastPLBar and lastPHBar live outside WS: an ending Phase E and a new climax on the same bar replace
    the campaign and keep them (regime keeps the markup of the old campaign)."""
    n, t = 60, 50
    o, h, l, c, v = bars(n, o=94.0, h=95.0, l=93.0, c=94.0)
    o[t], h[t], l[t], c[t], v[t] = 94.0, 104.0, 92.0, 93.0, 200.0
    pre = make_pre(o, h, l, c, v, **ATR4)
    P = pre["P"]
    P[:, R["APREV"]] = 2.0
    # a buying climax on bar 50: trend +20 >= 15, a new high, effort 200 >= 180, spread 12 >= 3, close position
    # (93 - 92) / 12 <= 0.65, effort >= 150: score 6
    P[t, R["TBVALID"]], P[t, R["TBBASE"]], P[t, R["TBSMA"]], P[t, R["TBN"]], P[t, R["TBE"]] = 1, 20.0, 0.0, 25, 2
    P[t, R["NEWHIGH"]], P[t, R["EFFHI"]] = 1.0, 150.0
    # Phase E of an accumulation: range 90-100 (mid 95); the highest of the last 3 closes (94) is below 95: EEND
    S = state(STOP=1, OUTC=1, PHASE=5, START=0, PIVLEN=4, BIRTH=-40.0, RHI=100.0, RLO=90.0, OHI=100.0, OLO=90.0,
              ESTART=40, CLATR=4.0, LASTACT=45, CFACCEPT=1)
    G = glob(regime=1, last_pl=44.0, last_ph=45.0, used=(1, 1, 1))
    out = step(pre, S, G, t, t + 1)
    assert out["dbg_reset"][t] == W.RS_EEND
    assert out["campaign"][t] == t and out["phase"][t] == 1 and S[F["STOP"]] == -1     # the new campaign's seed bar
    assert G[W.G_REGIME] == 1 and G[W.G_LASTPL] == 44.0 and G[W.G_LASTPH] == 45.0
    assert list(G[W.G_USED:]) == [0.0, 0.0, 0.0]                  # the entry slots belong to the campaign


def test_trap04_math_round_ties_up_and_int_truncates():
    """math.round rounds ties up (recLimit(6) = 5, Python's round gives 4) and int() truncates; liveLen at
    aRatio = 0.625 exactly is round(2.5) = 3."""
    assert W._rec_limit(6) == 5 and max(3, round(6 * 0.75)) == 4
    assert W._phase_c_to_d_min(7) == 3 and W._phase_c_to_d_min(9) == 4
    # an ATR series whose SMA50 is exactly 40 on bar 49 (every term / 50 and every partial sum is exact): 47 values of
    # 40.625 (0.8125 each), 2 of 32.8125 (0.65625), then 25 (0.5): 38.1875 + 1.3125 + 0.5 = 40; 25 / 40 = 0.625
    a = np.r_[np.full(47, 40.625), 32.8125, 32.8125, 25.0]
    assert I.sma(a, 50)[49] == 40.0
    live = W.adaptive_len(a)
    assert live[49] == 3.0                                          # 4 * 0.625 = 2.5 -> 3 (Python: 2)
    assert (live[:49] == 4.0).all()                                 # aRatio 1 while the SMA50 is na
    # int(math.round(x)) in f_phaseBMinBars: round(5 * 6.1) = round(30.5) = 31
    assert W._phase_b_min(5, 6.1) == 31


def test_trap05_na_until_full_length_and_nz_fallbacks():
    """Pine's ATR, SMA and highest / lowest are na until their full length and the engine falls back through
    nz(x, current); avgEffPrev and aPrev are the previous bar's averages."""
    n = 60
    o, h, l, c, v = bars(n, o=100.0, h=102.0, l=98.0, c=100.0)
    v[:] = np.arange(1.0, n + 1)                                    # effort = volume 1, 2, 3, ...
    h[5] = 104.0                                                    # a wider bar: spread 6
    s = W.series(o, h, l, c, v, np.arange(n) * 3600.0, mintick=MT)
    # ATR(14): na on bars 0..12, so a = the bar's spread there; aPrev = a until the ATR exists one bar back
    assert np.isnan(s["atrraw"][:13]).all() and not np.isnan(s["atrraw"][13])
    assert same(s["a"][:13], s["spr"][:13]) and s["a"][5] == 6.0
    assert s["aprev"][13] == s["a"][13] == s["atrraw"][13] and s["aprev"][14] == s["atrraw"][13]
    assert s["aprev"][5] == s["a"][5] == 6.0
    # SMA50 of effort: na on bars 0..48: avgEff = effort, avgEffPrev = avgEff there; then the previous bar's SMA
    assert np.isnan(s["avgraw"][:49]).all() and s["avgraw"][49] == I.sma(v, 50)[49]
    assert same(s["avg"][:49], v[:49]) and s["avgprev"][10] == 11.0
    assert s["avgprev"][49] == s["avgraw"][49] and s["avgprev"][50] == s["avgraw"][49]
    # the 30-bar prior low / high: na on bars 0..29, so no new low before bar 30 even at the lowest low so far
    assert np.isnan(s["prior_lo"][:30]).all() and s["prior_lo"][30] == 98.0
    assert not s["newlow"][:30].any() and s["newlow"][30]           # 98 <= 98 on bar 30
    assert np.isnan(s["hic2"][0]) and s["hic2"][1] == 100.0 and np.isnan(s["reff"][:2]).all()
    # nz(close[1], close) / nz(close[3], close) on the first bars
    assert s["c1"][0] == c[0] and s["res3up"][0] == 0.0


def test_trap06_readiness_uses_pivotlen_and_birth_trend():
    """f_entryReadinessWS takes its validation with nz(s.pivLen, pivotLen = 4) and s.birthTrend (L971), the entry
    check with nz(s.pivLen, liveLen) and trendScore (L1733). With pivLen and birthTrend na they differ; inside a
    seeded campaign both are always set (f_seed), so on real bars the two calls agree."""
    t = 100.0
    S = phase_b_accum(int(t), PHASE=3, OUTC=1, CFTEST=1, TESTTIME=1.0, TESTSCORE=3, CREADY=96, PIVLEN=nan,
                      BIRTH=nan, LASTEVTIME=t * 3600e3, LASTBAD=t - 10)
    # the entry check's call with liveLen 7 and trendScore 40: trend 10, clean (badAge 10 < round(7 * 2) = 14: no),
    # cause 90 / 42 + 1 + 0.5 = 3.64 -> 10: 10 + 15 + 10 + 15 + 15 + 0 + 10 + 10 = 85
    assert W._validation(S, 7, 40.0, 4.0, t, MT) == 85
    # the readiness call with 4 and na: trend 0, clean (10 >= 8: yes), cause 90 / 24 + 1.5 -> 10: 0 + 15 + 10 + 15 + 15
    # + 10 + 10 + 10 = 85; with a floor of 90 neither passes, with 85 both
    assert W._validation(S, 4, nan, 4.0, t, MT) == 85
    S2 = S.copy()
    S2[F["LASTBAD"]] = t - 9                                        # badAge 9: clean with p = 4, not with p = 7
    assert W._validation(S2, 7, 40.0, 4.0, t, MT) == 85             # trend +10, clean 0
    assert W._validation(S2, 4, nan, 4.0, t, MT) == 85              # trend 0, clean +10
    S2[F["LASTBAD"]] = t - 20                                       # clean for both: 95 against 85
    assert W._validation(S2, 7, 40.0, 4.0, t, MT) == 95 and W._validation(S2, 4, nan, 4.0, t, MT) == 85
    # readiness with floor 90: outcome, phase C, terminal, confidence 65 >= 60, distance (94 - 100) / 4 <= 2, age 0;
    # validation 85 < 90: 6. The entry check's own validation (95) would have counted.
    assert W._readiness(S2, 60, 90, 4.0, t, 94.0, t * 3600e3, 3600e3, MT) == 6
    S2[F["BIRTH"]] = 40.0
    assert W._readiness(S2, 60, 90, 4.0, t, 94.0, t * 3600e3, 3600e3, MT) == 7


def test_trap07_cformal_bonuses_for_an_untested_spring():
    """In Phase C with an untested spring (cFormal false) the SOS check adds 13 to the validation and 30 to the
    confidence, asks for 2 closes more (3 above 65% or a break) and a strength score of 2."""
    t = 100
    o, h, l, c, v = bars(110, o=99.5, h=101.5, l=99.0, c=101.0)
    pre = make_pre(o, h, l, c, v, A=2.0, ATRRAW=2.0, APREV=2.0, AVG=100.0, AVGRAW=100.0, AVGPREV=100.0, SOS=2.0)
    base = dict(STOP=1, OUTC=1, PHASE=3, START=t - 30, PIVLEN=4, BIRTH=-40.0, CLATR=4.0, ABSORBED=1, OLO=90.0,
                RLO=90.0, OHI=100.0, RHI=100.0, STCOUNT=1, STN=1, STEFF=100.0, STSPR=6.0, BSTART=t - 24,
                LASTBAD=t - 3, EXC=1, EXCTESTED=0, EXCBAR=t - 5, EXCPX=89.0, EXCEFF=150.0, EXCSPR=5.0, LASTACT=t - 1,
                LASTEVTIME=0.0, CFPRIOR=1, CFCLIMAX=1, CFAR=1, CFST=1, CFEXC=1)
    # validation: trend 10 + absorbed 15 + range 2.5 ATRs 10 + one ST 8 + opposite / traversals 0 + clean 0 (badAge
    # 3 < 8) + cause 24 / 24 + 0.5 = 1.5 -> 5 + terminal 0 = 48; + 13 = 61 >= 60. Confidence 50; + 30 = 80 >= 45.
    S = state(**base)
    assert W._validation(S, 4, 0.0, 2.0, float(t), MT) == 48 and W._conf(S) == 50
    # age: the spring bar is 5 >= 3 bars back; close 101 > 100 + 2 * 0.15: a break; strength score 2 >= 2
    out = step(pre, S, glob(), t, t + 1)
    assert out["ev_sos"][t] and out["phase"][t] == 4
    # Aggressive takes the SOS when no test happened: confidence 80 >= 55, validation 48 + 10 (spring + SOS) + 3 = 61
    # >= 50, readiness 6 (outcome, phase, strength, confidence, validation, distance 0.5) >= 5
    assert out["entry_agg"][t] == 1 and out["entry_std"][t] == 0
    # the same spring, tested: cFormal; validation 48 + 10 (terminal) = 58 < 60, no SOS
    S = state(**{**base, "EXCTESTED": 1, "CFTEST": 1, "TESTTIME": 1.0, "TESTSCORE": 2, "CREADY": t - 4})
    assert W._validation(S, 4, 0.0, 2.0, float(t), MT) == 58
    out = step(pre, S, glob(), t, t + 1)
    assert not out["ev_sos"][t] and out["phase"][t] == 3
    # the +30: an untested spring with confidence 25 (no AR, no ST flags) still promotes: 25 + 30 = 55 >= 45
    S = state(**{**base, "CFAR": 0, "CFST": 0})
    assert W._conf(S) == 25
    out = step(pre, S, glob(), t, t + 1)
    assert out["ev_sos"][t]


def test_trap08_probe_open_suspends_invalidation_and_stale():
    """While an excursion probe is open (at most recLimit(p) = 3 bars old for p = 4) the Phase C invalidation and the
    stale reset are not checked."""
    t = 100
    # Phase C (accumulation by a terminal test): hard level min(90, 90) = 90; ATR 2: invalidation when the higher of
    # the last 2 closes is below 90 - 1 = 89. A spring probe opened 2 bars ago at 89.2.
    base = dict(STOP=1, OUTC=1, PHASE=3, START=0, PIVLEN=4, BIRTH=-40.0, CLATR=4.0, ABSORBED=1, OLO=90.0,
                RLO=90.0, OHI=100.0, RHI=100.0, STCOUNT=2, STN=2, BSTART=10, CREADY=t - 6, CFTEST=1, TESTTIME=1.0,
                TESTSCORE=3, PEND=1, PENDEDGE=1, PENDSTART=t - 2, PENDEXTBAR=t - 2, PENDEXT=89.2, PENDEFF=100.0,
                PENDSPR=3.0, LASTACT=t - 1, LASTEVTIME=0.0, CFPRIOR=1, CFCLIMAX=1, CFAR=1, CFST=1)
    o, h, l, c, v = bars(110, o=89.0, h=89.5, l=88.0, c=88.5)
    c[t - 1] = 88.6                                                 # the higher of the last 2 closes: 88.6 < 89
    pre = make_pre(o, h, l, c, v, A=2.0, ATRRAW=2.0, APREV=2.0, AVG=100.0, AVGRAW=100.0, AVGPREV=100.0)
    S = state(**base)
    out = step(pre, S, glob(), t, t + 1)
    assert out["dbg_reset"][t] == -1 and out["phase"][t] == 3      # the probe (age 2 <= 3) suspends the check
    assert S[F["PEND"]] == 1 and S[F["PENDEXT"]] == 88.0           # still pending, extended to the bar's low
    out = step(pre, state(**{**base, "PENDSTART": t - 4}), glob(), t, t + 1)
    assert out["dbg_reset"][t] == W.RS_INVALID and out["campaign"][t] == -1    # age 4 > 3: not open
    # the stale reset: closes 89.5 (no invalidation), last activity 60 bars ago (> max(50, 8 * 4))
    o, h, l, c, v = bars(110, o=89.5, h=90.0, l=89.0, c=89.5)
    pre = make_pre(o, h, l, c, v, A=2.0, ATRRAW=2.0, APREV=2.0, AVG=100.0, AVGRAW=100.0, AVGPREV=100.0)
    out = step(pre, state(**{**base, "LASTACT": t - 60}), glob(), t, t + 1)
    assert out["dbg_reset"][t] == -1 and out["phase"][t] == 3
    out = step(pre, state(**{**base, "LASTACT": t - 60, "PENDSTART": t - 4}), glob(), t, t + 1)
    assert out["dbg_reset"][t] == W.RS_STALE


def test_trap09_demotion_keeps_the_used_entry_slot():
    """f_demoteToB clears the C/D events and the outcome but not s.entryTime: after a demotion the campaign cannot
    fire a second entry in a mode it already used, even when a new terminal test qualifies."""
    t = 100
    o, h, l, c, v = outside_pivot_bars(n=110, j=t - 3, h_j=95.0)    # pivot bar 97 (spread 3.5, close position 4/7)
    pre = make_pre(o, h, l, c, v, **ATR4)
    pre["PLC"][t + 1, 4] = 91.5
    d_state = dict(PHASE=4, OUTC=1, STRBAR=80, DSTART=80, CFSTRENGTH=1, CFTEST=1, TESTTIME=1.0, TESTSCORE=3,
                   CREADY=70)
    for used, want in (((1, 1, 0), 0), ((0, 0, 0), 1)):
        S = phase_b_accum(t, **d_state)
        G = glob(used=used)
        out = step(pre, S, G, t, t + 2)
        # bar 100: closes 94 < 95, demoted; bar 101: the pivot low of bar 97 is a terminal test (mature: age 91, not
        # clean, support 3); Standard quality: confidence 65, validation 95 - 10 (not clean) = 85, readiness 7
        assert out["dbg_demoted"][t] == 1 and out["phase"][t] == 2 and out["outcome"][t] == 0
        assert out["ev_ctest"][t + 1] and out["phase"][t + 1] == 3 and out["dbg_val"][t + 1] == 85
        assert out["entry_std"][t + 1] == want and out["entry_agg"][t + 1] == want
        assert G[W.G_USED] == 1.0                                   # used before, or used now


def test_trap10_plused_blocks_only_the_ab_blocks_not_traversals():
    """A pivot low that makes the A -> B transition (plUsed) is not tested again by the Phase B block (one ST, not
    two), but it still sets the zone for the traversal count."""
    t = 30
    o, h, l, c, v = bars(40)
    o[26], h[26], l[26], c[26] = 91.0, 92.5, 90.5, 91.8           # pivot bar 26: spread 2, close position 0.65
    o[30], h[30], l[30], c[30] = 98.5, 99.8, 97.8, 98.0           # pivot bar 30 (for bar 34): spread 2
    pre = make_pre(o, h, l, c, v, **ATR4)
    pre["PLC"][30, 4] = 90.5
    pre["PHC"][34, 4] = 99.8
    S = state(STOP=1, PHASE=1, START=0, PIVLEN=4, BIRTH=-40.0, CLBAR=0, CLPX=90.0, CLEFF=300.0, CLSPR=10.0,
              CLATR=4.0, ABSORBED=1, OLO=90.0, RLO=90.0, ARRUNPX=100.0, ARRUNBAR=10, AROK=1, LASTACT=29,
              LASTEVTIME=0.0, CFPRIOR=1, CFCLIMAX=1)
    out = step(pre, S, glob(), 30, 31)
    # A -> B on bar 30: near (|90.5 - 90| <= 3), holds, close 0.65 >= 0.45, effort 100 <= 270, spread 2 <= 9: GOOD,
    # score 6; age 26 >= 8; space 26 - 10 >= 4. rangeLow = robust edge (90.5 + 90) / 2 = 90.25
    assert out["ev_ar"][30] and out["ev_st"][30] and out["phase"][30] == 2
    assert S[F["STCOUNT"]] == 1 and S[F["RLO"]] == 90.25 and S[F["RHI"]] == 100.0
    # the same pivot sets the zone: 90.5 <= 90.25 + 9.75 * 0.25
    assert S[F["LZONE"]] == -1 and S[F["LZONEBAR"]] == 26 and S[F["TRAV"]] == 0
    out = step(pre, S, glob(last_pl=26.0), 31, 35)
    # bar 34: the pivot high of bar 30 (99.8 >= 100 - 2.4375) is in the top quarter: one traversal; it is also an
    # opposite test (99.8 >= 100 - 3, inside the cap, effort and spread under 1.2 x the climax's)
    assert S[F["TRAV"]] == 1 and S[F["LZONE"]] == 1 and S[F["LZONEBAR"]] == 30 and S[F["OPPCOUNT"]] == 1
    assert S[F["STCOUNT"]] == 1


def downtrend_with_climax(vol_flat=None):
    """300 bars falling 0.5 a bar (spread 0.9 = the ATR, no pivots), then a climax bar 3 below the last close,
    spread 3.2, close position 1.5 / 3.2. Volume 100 with 300 on the climax, or a flat heartbeat."""
    n = 320
    c = 300.0 - 0.5 * np.arange(n)
    o = np.r_[c[0] + 0.5, c[:-1]]
    h, l = np.maximum(o, c) + 0.2, np.minimum(o, c) - 0.2
    k = 300
    o[k] = c[k - 1]
    h[k], l[k] = o[k] + 0.2, c[k - 1] - 3.0
    c[k] = l[k] + 1.5
    c[k + 1:] = c[k] + 0.3
    o[k + 1:] = c[k]
    h[k + 1:], l[k + 1:] = c[k] + 0.6, c[k] - 0.2
    v = np.full(n, 100.0)
    v[k] = 300.0
    if vol_flat is not None:
        v[:] = vol_flat
    return o, h, l, c, v, k


def test_trap11_the_volume_source_decides_the_climax_gate():
    """The climax needs effort >= 1.8 x the previous average (x 0.8 in a strong trend). With a heartbeat volume
    (Exness BTC ticks: flat) the gate never opens; with real volume (Binance) it does; without volume the script
    uses the range."""
    o, h, l, c, v, k = downtrend_with_climax()
    t = np.arange(len(c)) * 3600.0
    s = W.series(o, h, l, c, v, t, mintick=MT)
    out = W.wyckoff(o, h, l, c, v, t)
    # bar 300: a strong downtrend (disp -45, efficiency -25, SMA -10, no swings: -80), a new 30-bar low; effort 300 >=
    # 100 * 1.8 * 0.8 = 144; spread 3.2 >= 0.9 * 1.5 * 0.8; close position 0.47 >= 0.35; 300 >= the prior high 100
    tr = W.run(s, *W.new_state())["dbg_trend"]
    assert tr[k] <= -35 and s["newlow"][k] and s["eff"][k] >= s["avgprev"][k] * 1.8 * 0.8
    assert out["campaign"][k] == k and out["phase"][k] == 1 and (out["campaign"][:k] == -1).all()
    o, h, l, c, v, k = downtrend_with_climax(vol_flat=60.0)
    out = W.wyckoff(o, h, l, c, v, t)
    assert (out["campaign"] == -1).all()                            # 60 < 60 * 1.44: no climax ever
    out = W.wyckoff(o, h, l, c, v, t, no_vol=True)                  # effort = range: 3.2 >= 0.9 * 1.44
    assert out["campaign"][k] == k


def test_trap12_path_dependence_on_where_the_history_starts():
    """regime is set by every Phase E and never cleared, so a campaign's SOS can depend on a Phase E before the data
    starts: a young accumulation (10 bars) after a markdown needs 25 bars (ageOKBull). Real bars:
    test_real_start_invariance."""
    t = 100
    o, h, l, c, v = bars(110, o=99.5, h=101.5, l=99.0, c=101.0)
    pre = make_pre(o, h, l, c, v, A=2.0, ATRRAW=2.0, APREV=2.0, AVG=100.0, AVGRAW=100.0, AVGPREV=100.0, SOS=3.0)
    # Phase C by a terminal test 4 bars ago (>= 3), validation 90 >= 60, confidence 65 >= 45; close 101 > 100.3,
    # strength 3 >= 3
    kw = dict(PHASE=3, OUTC=1, START=t - 10, BSTART=t - 9, CFTEST=1, TESTTIME=1.0, TESTSCORE=3, CREADY=t - 4)
    for regime, want in ((0, True), (-1, False), (1, True)):
        S = phase_b_accum(t, **kw)
        out = step(pre, S, glob(regime=regime), t, t + 1)
        assert bool(out["ev_sos"][t]) == want, regime


# ───────────────────────────── 3. properties on synthetic bars ─────────────────────────────

@pytest.mark.parametrize("seed", [2, 3])
def test_truncation_invariance(seed):
    o, h, l, c, v, t = synthetic(seed)
    full = W.wyckoff(o, h, l, c, v, t)
    assert int(sum((full[k] != 0).sum() for k in ("entry_std", "entry_agg", "exc", "climax"))) > 5
    for T in (700, 2345, 4100, 5999):
        part = W.wyckoff(o[:T], h[:T], l[:T], c[:T], v[:T], t[:T])
        for k in W.CONTRACT_KEYS:
            assert same(part[k], full[k][:T]), (seed, T, k)


def _mirror_ok(bars6, mintick=MT):
    o, h, l, c, v, t = bars6
    a = W.run(W.series(o, h, l, c, v, t, mintick=mintick), *W.new_state(), mintick=mintick)
    b = W.run(W.series(-o, -l, -h, -c, v, t, mintick=mintick), *W.new_state(), mintick=mintick)
    # a new pivot low and a new pivot high on one bar break the symmetry only where both pivot blocks act: in
    # Phase B (or a Phase D demoted on that bar), where the low side is evaluated first
    prev = np.r_[0, a["phase"][:-1]]
    both = np.flatnonzero((a["dbg_new_pl"] == 1) & (a["dbg_new_ph"] == 1) & ((prev == 2) | (prev == 4)))
    stop = int(both[0]) if len(both) else len(c)
    sl = slice(0, stop)
    pairs = [("ev_sc", "ev_bc"), ("ev_spring", "ev_utad"), ("ev_sos", "ev_sow"), ("ev_lps", "ev_lpsy")]
    for x, y in pairs:
        assert same(a[x][sl], b[y][sl]) and same(a[y][sl], b[x][sl]), (x, y)
    for k in ("ev_ar", "ev_st", "ev_test", "ev_ctest", "ev_phase_e", "phase", "campaign", "in_cde"):
        assert same(a[k][sl], b[k][sl]), k
    for k in ("outcome", "climax", "exc", "entry_std", "entry_agg", "entry_con"):
        assert same(a[k][sl], -b[k][sl]), k
    for x, y in (("range_lo", "range_hi"), ("hard_lo", "hard_hi"), ("climax_px", "climax_px"), ("exc_px", "exc_px")):
        p, q = a[x][sl], -b[y][sl]
        assert np.array_equal(np.isnan(p), np.isnan(q)), x
        ok = ~np.isnan(p)
        assert np.allclose(p[ok], q[ok], rtol=1e-12, atol=0), x     # the median of three rounds differently
    assert same(a["dbg_trend"][sl], -b["dbg_trend"][sl])
    return stop, a


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_mirror_of_negated_prices(seed):
    """Negated prices (high <-> -low) give the mirrored campaigns: SC <-> BC, spring <-> UTAD, SOS <-> SOW,
    LPS <-> LPSY, outcomes and entries negated, the same phases and campaign ids; until the first bar where a new
    pivot high and a new pivot low are both reported in Phase B (or D), where the low-first order breaks the
    symmetry."""
    stop, a = _mirror_ok(synthetic(seed))
    assert stop > 2000
    assert int((a["climax"][:stop] != 0).sum()) >= 3
    assert int(sum((a[k][:stop] != 0).sum() for k in ("entry_std", "entry_agg", "entry_con"))) >= 1


def test_compiled_kernel_equals_its_python_body():
    o, h, l, c, v, t = synthetic(2, 3000)
    pre = W.series(o, h, l, c, v, t, mintick=MT)
    S1, G1 = W.new_state()
    S2, G2 = W.new_state()
    a = W.run(pre, S1, G1, mintick=MT)
    b = W.run(pre, S2, G2, mintick=MT, python=True)
    for k in a:
        assert same(a[k], b[k]), k
    assert same(S1, S2) and same(G1, G2)
    assert int((a["entry_agg"] != 0).sum()) >= 1


@pytest.mark.parametrize("seed", [2, 3, 4, 5])
def test_contract_invariants(seed):
    o, h, l, c, v, t = synthetic(seed)
    out = W.wyckoff(o, h, l, c, v, t)
    _check_invariants(out)


def _check_invariants(out):
    ph, oc, cid = out["phase"], out["outcome"], out["campaign"]
    assert ((cid == -1) == (ph == 0)).all()
    assert set(np.unique(ph)) <= set(range(6)) and set(np.unique(oc)) <= {-1, 0, 1}
    assert (oc[ph <= 2] == 0).all()                                 # an outcome only from Phase C on
    assert not out["in_cde"][(ph < 3) | (oc == 0)].any()
    assert (np.diff(cid[cid >= 0]) >= 0).all()                      # ids in order of seeding
    first = np.flatnonzero((cid >= 0) & (cid != np.r_[-1, cid[:-1]]))
    assert (cid[first] == first).all()                              # the id is the seed bar (s.startBar)
    for k, px in (("climax", "climax_px"), ("exc", "exc_px")):
        assert np.array_equal(out[k] != 0, ~np.isnan(out[px])), k
    assert np.array_equal(out["climax"] != 0, out["ev_sc"] | out["ev_bc"])
    assert not (out["ev_sc"] & out["ev_bc"]).any()
    hold = ph >= 2
    assert not np.isnan(out["range_lo"][hold]).any() and not np.isnan(out["range_hi"][hold]).any()
    assert (out["range_lo"][hold] < out["range_hi"][hold]).all()
    assert not np.isnan(out["hard_lo"][oc == 1]).any() and not np.isnan(out["hard_hi"][oc == -1]).any()
    test_bit = out["ev_test"] | out["ev_ctest"]
    lps_bit = out["ev_lps"] | out["ev_lpsy"]
    sos_bit = out["ev_sos"] | out["ev_sow"]
    for mode, bits in (("std", test_bit | lps_bit), ("agg", test_bit | sos_bit), ("con", lps_bit)):
        e = out[f"entry_{mode}"]
        fire = e != 0
        assert (e[fire] == oc[fire]).all(), mode                    # the direction is the outcome at the close
        assert bits[fire].all(), mode
        assert out["in_cde"][fire].all(), mode
        ids = cid[fire]
        assert len(ids) == len(np.unique(ids)), mode                # one entry per campaign and mode
    return True


def test_no_volume_switch():
    """ta.cum(volume) <= 0 keeps effort = range: zero volume and no_vol=True are the same; once any volume appears
    the switch is off for good (a later zero volume is an effort of 0)."""
    o, h, l, c, v, t = synthetic(3, 2000)
    z = W.wyckoff(o, h, l, c, np.zeros(len(c)), t)
    nv = W.wyckoff(o, h, l, c, v, t, no_vol=True)
    nan_v = W.wyckoff(o, h, l, c, np.full(len(c), nan), t)          # nz(volume)
    for k in W.CONTRACT_KEYS:
        assert same(z[k], nv[k]) and same(nan_v[k], nv[k]), k
    v2 = v.copy()
    v2[:100] = 0.0
    v2[500:510] = 0.0
    s = W.series(o, h, l, c, v2, t, mintick=MT)
    assert same(s["eff"][:100], s["spr"][:100]) and same(s["eff"][100:], v2[100:])
    assert (s["eff"][500:510] == 0).all()


def test_inputs_not_modified_and_no_na_prices():
    o, h, l, c, v, t = synthetic(2, 800)
    keep = [x.copy() for x in (o, h, l, c, v, t)]
    W.wyckoff(o, h, l, c, v, t)
    assert all(np.array_equal(a, b) for a, b in zip(keep, (o, h, l, c, v, t)))
    c2 = c.copy()
    c2[10] = nan
    with pytest.raises(ValueError):
        W.wyckoff(o, h, l, c2, v, t)
    with pytest.raises(ValueError):
        W.wyckoff(o[:-1], h, l, c, v, t)


def test_timeframe_seconds_and_mintick_are_immaterial_here():
    """tf_seconds only scales ageBars, which is 0 on every bar an entry can fire; on these bars the mintick floor
    never binds."""
    o, h, l, c, v, t = synthetic(2)
    a = W.wyckoff(o, h, l, c, v, t)
    for kw in ({"tf_seconds": 1.0}, {"tf_seconds": 86400.0 * 30}, {"mintick": 0.01}):
        b = W.wyckoff(o, h, l, c, v, t, **kw)
        for k in W.CONTRACT_KEYS:
            assert same(a[k], b[k]), (kw, k)


# ───────────────────────────── 4. real bars (the hold-out is never loaded) ─────────────────────────────

END = "2024-07-01"
DEV = (TM.s_of("2019-01-01"), TM.s_of("2023-01-01"))


@pytest.fixture(scope="module")
def real():
    """Per symbol: 1H / 4H / 1D bars up to 2024-06-30 (open times, close times, OHLC, tick volume) and, for BTC,
    Binance volume; the market is dropped once the bars are taken (one symbol in memory at a time)."""
    cache = {}

    def get(symbol):
        if symbol not in cache:
            cache.clear()
            gc.collect()
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            mk = TM.load(symbol, end=END)
            out = {}
            for tf in ("1H", "4H", "1D"):
                b = mk.tbars(tf)
                d = {"t": b.t.copy(), "tc": b.tc.copy(), "o": b.o.copy(), "h": b.h.copy(), "l": b.l.copy(),
                     "c": b.c.copy(), "tick": b.vol.astype(float)}
                if symbol.startswith("BTC"):
                    if not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
                        pytest.skip("the Binance klines are not on this machine")
                    d["binance"] = TM.binance_volume(mk, tf)[0]
                out[tf] = d
            del mk
            gc.collect()
            cache[symbol] = out
        return cache[symbol]
    return get


def _run(d, vol, symbol, no_vol=False):
    return W.wyckoff(d["o"], d["h"], d["l"], d["c"], d[vol], d["t"], no_vol=no_vol, mintick=W.MINTICK[symbol])


def _entries(out, d, mode="std"):
    e = out[f"entry_{mode}"]
    win = (d["tc"] > DEV[0]) & (d["tc"] <= DEV[1])
    rows = []
    for i in np.flatnonzero((e != 0) & win):
        kind = ("test" if out["ev_test"][i] else "ctest" if out["ev_ctest"][i] else
                "lps" if out["ev_lps"][i] or out["ev_lpsy"][i] else "sos")
        rows.append((TM.utc(d["t"][i]).strftime("%Y-%m-%d %H:%M"), "L" if e[i] > 0 else "S", kind))
    return rows


def _dev_count(out, d, key, sign=None):
    win = (d["tc"] > DEV[0]) & (d["tc"] <= DEV[1])
    x = out[key][win]
    return int((x != 0).sum() if sign is None else (np.sign(x) == sign).sum())


@pytest.mark.parametrize("symbol,vol", [("XAUUSDm", "tick"), ("BTCUSDm", "binance"), ("BTCUSDm", "tick")])
def test_real_smoke(symbol, vol, real):
    """Every series the PREREG runs (6.3: gold on tick volume, BTC on Binance volume, BTC on tick volume as the
    control; 1H, 4H, 1D) runs to 2024-06-30 and has values wherever the contract says they exist."""
    for tf, d in real(symbol).items():
        assert d["tc"][-1] <= TM.CUT_S
        out = _run(d, vol, symbol)
        _check_invariants(out)
        e = out["entry_std"] != 0
        if e.any():
            hard = np.where(out["entry_std"][e] > 0, out["hard_lo"][e], out["hard_hi"][e])
            assert np.isfinite(hard).all(), tf


def test_real_cross_check_vectors_gold(real):
    """The specification's vectors (scratch port, Development): every one is reproduced. Standard entries gold 1H
    4, 4H 2, 1D 0; climax confirmations 157 (52 SC / 105 BC), 50, 6; volume-free 1H: 15 Standard entries."""
    d = real("XAUUSDm")
    o1 = _run(d["1H"], "tick", "XAUUSDm")
    assert _entries(o1, d["1H"]) == [("2020-07-16 07:00", "S", "ctest"), ("2021-06-28 19:00", "L", "test"),
                                     ("2021-10-31 23:00", "S", "lps"), ("2021-11-23 04:00", "S", "lps")]
    o4 = _run(d["4H"], "tick", "XAUUSDm")
    assert _entries(o4, d["4H"]) == [("2020-05-24 20:00", "S", "test"), ("2022-01-04 08:00", "L", "lps")]
    o1d = _run(d["1D"], "tick", "XAUUSDm")
    assert _entries(o1d, d["1D"]) == []
    assert (_dev_count(o1, d["1H"], "climax", 1), _dev_count(o1, d["1H"], "climax", -1)) == (52, 105)
    assert _dev_count(o4, d["4H"], "climax") == 50 and _dev_count(o1d, d["1D"], "climax") == 6
    # the spec's spring / UTAD family counts 66 / 11 / 0: the recovery bars (64 / 11 / 0) plus the 2 / 0 / 0 bars on
    # which a breakout adopts a provisional spring (ev_spring with ev_sos), which are not recovery bars (the contract)
    for out, dd, want_exc, want_adopt in ((o1, d["1H"], 64, 2), (o4, d["4H"], 11, 0), (o1d, d["1D"], 0, 0)):
        win = (dd["tc"] > DEV[0]) & (dd["tc"] <= DEV[1])
        adopt = ((out["ev_spring"] & out["ev_sos"]) | (out["ev_utad"] & out["ev_sow"])) & win
        assert (_dev_count(out, dd, "exc"), int(adopt.sum())) == (want_exc, want_adopt)
    nv = _run(d["1H"], "tick", "XAUUSDm", no_vol=True)
    assert len(_entries(nv, d["1H"])) == 15


def test_real_cross_check_vectors_btc(real):
    """BTC on Binance volume: Standard entries 1H 14 (2019-02-23 15:00 S to 2022-12-06 04:00 S), 4H 5 (the spec's
    list), 1D 0; climax confirmations 375 / 95 / 18; spring / UTAD 123 / 26 / 4 with the adoption bars (122 / 25 / 4
    recovery bars). On Exness tick volume (the control): 1 / 0 / 0 Standard entries."""
    d = real("BTCUSDm")
    out = {tf: _run(d[tf], "binance", "BTCUSDm") for tf in d}
    e1 = _entries(out["1H"], d["1H"])
    assert len(e1) == 14 and e1[0][:2] == ("2019-02-23 15:00", "S") and e1[-1][:2] == ("2022-12-06 04:00", "S")
    assert [x[:2] for x in _entries(out["4H"], d["4H"])] == [("2019-01-24 16:00", "L"), ("2020-06-10 12:00", "S"),
                                                            ("2020-07-04 12:00", "L"), ("2021-06-25 00:00", "L"),
                                                            ("2021-12-25 00:00", "L")]
    assert _entries(out["4H"], d["4H"])[-1][2] == "lps"
    assert _entries(out["1D"], d["1D"]) == []
    assert [_dev_count(out[tf], d[tf], "climax") for tf in ("1H", "4H", "1D")] == [375, 95, 18]
    assert [_dev_count(out[tf], d[tf], "exc") for tf in ("1H", "4H", "1D")] == [122, 25, 4]
    tick = [len(_entries(_run(d[tf], "tick", "BTCUSDm"), d[tf])) for tf in ("1H", "4H", "1D")]
    assert tick == [1, 0, 0]


def test_real_entry_stop_geometry(real):
    """The spec's geometry for claim 16 (no profit): the distance from the entry close to the hard level, in ATR(14)
    of the entry bar, median 2.7 at Standard test entries (n 18), 4.8 at Aggressive SOS entries (n 14), 6.8 at
    Standard LPS entries (n 7), pooled over gold (tick) and BTC (Binance), 1H / 4H / 1D, Development."""
    dist = {"test": [], "sos": [], "lps": []}
    for symbol, vol in (("XAUUSDm", "tick"), ("BTCUSDm", "binance")):
        for tf, d in real(symbol).items():
            out = _run(d, vol, symbol)
            atr = I.atr(d["h"], d["l"], d["c"], 14)
            win = (d["tc"] > DEV[0]) & (d["tc"] <= DEV[1])
            for mode, kinds in (("std", ("test", "ctest", "lps")), ("agg", ("sos",))):
                e = out[f"entry_{mode}"]
                for i in np.flatnonzero((e != 0) & win):
                    kind = ("test" if out["ev_test"][i] or out["ev_ctest"][i] else
                            "lps" if out["ev_lps"][i] or out["ev_lpsy"][i] else "sos")
                    if kind == "test" and mode == "agg":
                        continue
                    hard = out["hard_lo"][i] if e[i] > 0 else out["hard_hi"][i]
                    dist[kind].append(abs(d["c"][i] - hard) / atr[i])
    assert {k: len(x) for k, x in dist.items()} == {"test": 18, "sos": 14, "lps": 7}
    med = {k: round(float(np.median(x)), 1) for k, x in dist.items()}
    assert med == {"test": 2.7, "sos": 4.8, "lps": 6.8}


def test_real_start_invariance(real):
    """Trap 12 on real bars: gold 4H started 300 bars before 2019 differs from the run from the data start inside
    Development (entries included); with 1,000 bars of history it is identical (the spec's finding). Gold 1H and 1D
    are identical with 300 bars."""
    d = real("XAUUSDm")
    for tf, hist_bars, want_same in (("4H", 300, False), ("4H", 1000, True), ("1H", 300, True), ("1D", 300, True)):
        dd = d[tf]
        base = _run(dd, "tick", "XAUUSDm")
        k0 = int(np.searchsorted(dd["tc"], DEV[0], side="right")) - hist_bars
        cut = {k: x[k0:] for k, x in dd.items()}
        alt = _run(cut, "tick", "XAUUSDm")
        win = (cut["tc"] > DEV[0]) & (cut["tc"] <= DEV[1])
        base_ids = np.where(base["campaign"] >= 0, base["campaign"] - k0, -1)   # seed bars, counted from the cut
        diff = [k for k in W.CONTRACT_KEYS
                if not same((base_ids if k == "campaign" else base[k])[k0:][win], alt[k][win])]
        assert (not diff) == want_same, (tf, hist_bars, diff)
        if not want_same:
            assert "entry_std" in diff


def test_real_btc_volume_source(real):
    """Trap 11 on real bars: the climax volume gate (effort >= 1.8 x the previous average) on BTC 1H passes on under
    1% of bars with Exness tick volume (a heartbeat) and on about 10% with Binance volume."""
    d = real("BTCUSDm")["1H"]
    rate = {}
    for vol in ("tick", "binance"):
        s = W.series(d["o"], d["h"], d["l"], d["c"], d[vol], d["t"], mintick=W.MINTICK["BTCUSDm"])
        rate[vol] = float(np.mean(s["eff"][50:] >= s["avgprev"][50:] * 1.8))
    assert rate["tick"] < 0.01 and 0.05 < rate["binance"] < 0.2, rate


@pytest.mark.parametrize("symbol,vol,tf,min_bars", [("XAUUSDm", "tick", "1H", 15000),
                                                     ("BTCUSDm", "binance", "1H", 3000),
                                                     ("BTCUSDm", "binance", "1D", 2372)])
def test_real_mirror(symbol, vol, tf, min_bars, real):
    """The mirror of negated prices on real bars, up to the first symmetry-breaking bar (gold 1H: 15,442 bars with 56
    climax confirmations; BTC 1D: the whole series)."""
    d = real(symbol)[tf]
    stop, a = _mirror_ok((d["o"], d["h"], d["l"], d["c"], d[vol], d["t"].astype(float)), W.MINTICK[symbol])
    assert stop >= min_bars and int((a["climax"][:stop] != 0).sum()) >= 25
