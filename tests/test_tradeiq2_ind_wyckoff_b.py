"""
Port B (the oracle) of "Wyckoff [theUltimator5]": ``tests/tradeiq2_oracle_wyckoff.py`` (study 2, PREREG 6.3).

1. The helpers and the Pine primitives by hand, with the specification's own cases (maps/wyckoff.md section 6).
2. One hand-computed case for every trap of the specification's risk list (section 6, "Risks"), named after it:
   the engine is fed a flat history (o = c = 100, h = 101, l = 99, volume 1000: true range 2, so the ATR is 2, the
   average effort 1000, liveLen 4 and the prior-trend score 0), a campaign state is set by hand, and the bars that
   follow are worked out in the comments. Source line numbers refer to the study's copy of the Pine source.
3. Invariants on synthetic bars: truncation (the outputs up to bar T do not change when the bars after T are
   removed), the three entry modes of one pass against three single-mode passes, the mirror image (negated prices),
   the volume-free mode.
4. Real bars (skipped without the tick store): both symbols, 1H / 4H / 1D, bars up to 2024-06-30 only (tradeiq_market
   with end="2024-07-01"; BTC on Binance volume): the engine runs, no NaN where the contract says values exist, the
   specification's cross-check vectors, truncation and start invariance on gold 4H.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_wyckoff as O  # noqa: E402

nan = math.nan
H1 = 3600


# ───────────────────────────── helpers ─────────────────────────────

def flat(n=120, o=100.0, h=101.0, l=99.0, c=100.0, v=1000.0, mintick=0.01):
    """An engine after ``n`` identical bars (open times n * 1 h); its trace is switched on afterwards."""
    eng = O.Engine(mintick, H1)
    for i in range(n):
        eng.step(o, h, l, c, v, i * H1 * 1000)
    eng.trace = {}
    return eng


def bar(eng, o, h, l, c, v=1000.0):
    """Feed one bar; return the outputs at its close and a copy of the engine's locals."""
    i = len(eng.close)
    out = eng.step(o, h, l, c, v, i * H1 * 1000)
    return out, dict(eng.trace)


def ws(**fields):
    """A hand-made campaign state (every field not named keeps its Pine default)."""
    s = O.WS()
    O.f_initPivotHistory(s)
    for k, x in fields.items():
        assert hasattr(s, k), k
        setattr(s, k, x)
    return s


def bits(out):
    return {k for k, b in O.EVENT_BITS.items() if O.f_hasBit(out["sig"], b)}


def synth(n, seed):
    """Regime-switching random walk (t(3) shocks) on a 0.01 grid, volume rising with the bar's shock, 1 h bars."""
    rng = np.random.default_rng(seed)
    seg = 150
    drift = np.repeat(rng.choice([-0.35, -0.15, 0.0, 0.0, 0.0, 0.15, 0.35], n // seg + 1), seg)[:n]
    shock = rng.standard_t(3, n)
    c = 2000 + np.cumsum(drift + shock)
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.1, n)
    w = np.abs(rng.normal(0, 0.6, n)) + 0.2
    h = np.maximum(o, c) + w * rng.uniform(0.1, 1.0, n)
    lo = np.minimum(o, c) - w * rng.uniform(0.1, 1.0, n)
    v = np.round(np.exp(rng.normal(6.0, 0.35, n)) * (1.0 + 1.5 * np.abs(shock)))
    o, h, lo, c = (np.round(x * 100) / 100 for x in (o, h, lo, c))
    h = np.maximum.reduce([h, o, c])
    lo = np.minimum.reduce([lo, o, c])
    t = 1_500_000_000 + H1 * np.arange(n)
    return o, h, lo, c, v, t


def same(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        return bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))
    return bool(np.array_equal(a, b))


# ───────────────────────────── 1. helpers and primitives by hand ─────────────────────────────

def test_helpers_spec_cases():
    # f_excursionRecoveryLimit for p = 2..10 (lines 666-667): max(3, round(0.75 p)), ties up
    assert [O.f_excursionRecoveryLimit(p) for p in range(2, 11)] == [3, 3, 3, 4, 5, 5, 6, 7, 8]
    # f_phaseBMinBars (654-658): clamp(round(max(6p, rATR p)), 30, 60)
    assert O.f_phaseBMinBars(4, 5.0) == 30 and O.f_phaseBMinBars(4, 10.0) == 40 and O.f_phaseBMinBars(10, 8.0) == 60
    assert O.f_phaseBMinBars(5, 7.3) == 37                           # round(36.5) = 37 (ties up)
    # f_phaseCToDMinBars (660-661): max(3, int(p / 2))
    assert [O.f_phaseCToDMinBars(p) for p in (4, 7, 8, 10)] == [3, 3, 4, 5]
    # f_robustEdge (690-698)
    assert O.f_robustEdge(10.0, nan, nan, 8.0, True) == 9.0           # (10 + 8) / 2
    assert O.f_robustEdge(10.0, 12.0, nan, 8.0, True) == 9.5          # ((10 + 12) / 2 + 8) / 2
    assert O.f_robustEdge(10.0, 12.0, 9.0, 8.0, True) == 10.0         # median 10, above the original 8
    assert O.f_robustEdge(18.0, nan, nan, 20.0, False) == 19.0
    assert O.f_robustEdge(7.0, nan, nan, 8.0, True) == 8.0            # never below the original low
    # trendBars / trendEnd for liveLen 2..10 (lines 1117-1118)
    tb = [max(25, min(200, O.pround(L * 8.0))) for L in range(2, 11)]
    te = [max(2, min(8, O.pround(L * 0.75))) for L in range(2, 11)]
    assert tb == [25, 25, 32, 40, 48, 56, 64, 72, 80] and te == [2, 2, 3, 4, 5, 5, 6, 7, 8]
    # liveLen at aRatio 0.625: round(4 * 0.625) = round(2.5) = 3 (lines 1086-1087)
    assert max(2, min(10, O.pround(4 * 0.625))) == 3
    # confidence milestones (615-616): after the ST 50, a Phase C test 65, the SOS 80, the LPS 90, Phase E 100
    f = O.f_structureConfidence
    assert [f(1, 1, 1, 1, 0, 0, 0, 0), f(1, 1, 1, 1, 1, 0, 0, 0), f(1, 1, 1, 1, 1, 1, 0, 0),
            f(1, 1, 1, 1, 1, 1, 1, 0), f(1, 1, 1, 1, 1, 1, 1, 1)] == [50, 65, 80, 90, 100]
    # f_validationScore (618-633): the maximum before Phase D is 95, after it capped at 100
    assert O.f_validationScore(40, True, 4.0, 2, 1, 2, True, 3.0, True, False, False, False) == 95
    assert O.f_validationScore(40, True, 4.0, 2, 1, 2, True, 3.0, True, True, True, True) == 100
    assert O.f_validationScore(-15, False, 10.0, 1, 0, 1, False, 1.5, False, False, False, False) == 5 + 5 + 8 + 8 + 5
    # f_phaseIdleLimit (669-680): A 45 / 30, B 125, C 50, D 100 for p = 4; none in Phase E
    assert [O.f_phaseIdleLimit(1, True, 4), O.f_phaseIdleLimit(1, False, 4), O.f_phaseIdleLimit(2, False, 4),
            O.f_phaseIdleLimit(3, False, 4), O.f_phaseIdleLimit(4, False, 4)] == [45, 30, 125, 50, 100]
    assert O.na(O.f_phaseIdleLimit(5, True, 4)) and O.f_phaseIdleLimit(2, False, 7) == 140
    # f_testClass: near and holding with a close and lower effort / range -> GOOD; not holding -> FAILED
    assert O.f_testClass(True, True, True, 9.0, 0.9, 10.0, 1.0) == O.TEST_GOOD
    assert O.f_testClass(True, True, True, 9.1, 0.9, 10.0, 1.0) == O.TEST_POOR
    assert O.f_testClass(True, False, True, 1.0, 0.1, 10.0, 1.0) == O.TEST_FAILED
    assert O.f_testClass(False, True, True, 1.0, 0.1, 10.0, 1.0) == O.TEST_NONE
    assert O.f_hasBit(O.BIT_SC | O.BIT_ST, O.BIT_ST) and not O.f_hasBit(O.BIT_SC, O.BIT_ST)
    assert O.f_addBit(O.BIT_ST, O.BIT_ST) == O.BIT_ST


def test_primitives_by_hand():
    s = [1.0, 4.0, 2.0, 8.0]
    assert O.na(O.ta_sma(s[:2], 3)) and O.ta_sma(s, 3) == 8.0 / 3 + 2.0 / 3 + 4.0 / 3   # newest first
    assert O.ta_sum(s, 3) == 14.0 and O.na(O.ta_sum(s[:2], 3))
    assert O.ta_highest(s, 2) == 8.0 and O.ta_lowest(s, 3) == 2.0 and O.na(O.ta_highest(s, 5))
    assert O.at(s, 0) == 8.0 and O.at(s, 3) == 1.0 and O.na(O.at(s, 4))
    hi = [1.0, 2.0, 5.0, 2.0, 1.0]
    assert O.ta_pivothigh(hi, 2, 2) == 5.0 and O.na(O.ta_pivothigh(hi[:4], 2, 2))
    tie = [1.0, 5.0, 5.0, 2.0, 1.0]                  # equal highs: no pivot under the strict reading
    assert O.na(O.ta_pivothigh(tie, 2, 2)) and O.ta_pivothigh(tie, 2, 2, "nonstrict") == 5.0
    lo = [3.0, 2.0, 1.0, 2.0, 3.0]
    assert O.ta_pivotlow(lo, 2, 2) == 1.0 and O.ta_pivotlow(lo, 1, 2) == 1.0
    assert O.na(O.ta_pivotlow(lo, 2, 1))             # centre 1 bar back is 2.0, above the 1.0 before it
    assert O.pmax(nan, 1.0) != O.pmax(nan, 1.0) and O.pmin(2.0, 1.0) == 1.0 and O.nz(nan, 3) == 3
    assert O.infer_mintick([1234.567, 1.5]) == 0.001 and O.infer_mintick([60123.45]) == 0.01


def test_flat_history_baseline():
    eng = flat()
    out, tr = bar(eng, 100, 101, 99, 100)
    assert abs(tr["a"] - 2.0) < 1e-12 and tr["avgEff"] == 1000.0 and tr["avgEffPrev"] == 1000.0
    assert tr["liveLen"] == 4 and tr["trendBars"] == 32 and tr["trendEnd"] == 3 and tr["trendScore"] == 0.0
    assert O.na(tr["ph"]) and O.na(tr["pl"]) and tr["cPos"] == 0.5
    assert out["phase"] == 0 and out["campaign"] == -1 and O.na(eng.lastPLBar)


# ───────────────────────────── 2. the traps (specification section 6), one hand case each ─────────────────────────────

def _phase_d_accum(std_used: bool):
    """An SC campaign in Phase D after a tested spring at 88: range 90-110 (mid 100), climax ATR 2 (rATR 10), Phase B
    from bar 60 with 2 STs, 1 opposite test and 2 traversals; the Standard entry slot used or free."""
    return ws(stopSide=1, outcome=1, phase=4, ev=O.EV_SOS, startBar=40, climaxBar=40, climaxPrice=90.0,
              climaxEff=5000.0, climaxSpr=8.0, climaxATR=2.0, climaxScore=5, absorbed=True, pivLen=4, birthTrend=-40.0,
              origLow=90.0, origHigh=110.0, rangeLow=90.0, rangeHigh=110.0, arOK=True, arBar=45, arPrice=110.0,
              arRunPrice=110.0, arRunBar=45, stCount=2, stN=2, stEffSum=1800.0, stSprSum=3.6, lastGoodEff=900.0,
              lastGoodSpr=1.8, stBar=70, stPrice=90.5, oppCount=1, opN=1, opEffSum=900.0, opSprSum=1.8, opLastBar=80,
              opLastPrice=109.0, travCount=2, lastZone=1, lastZoneBar=80, bStartBar=60, exc=True, excTested=True,
              excBar=95, excPrice=88.0, excEff=1500.0, excSpr=3.0, excScore=3, testPrice=89.0, testScore=2,
              testTime=99 * H1 * 1000.0, cReadyBar=100, strBar=110, strPrice=111.0, strScore=3, dStartBar=110,
              lastActBar=119, lastEventBar=110, cfPrior=True, cfClimax=True, cfAR=True, cfST=True, cfExc=True,
              cfTest=True, cfStrength=True,
              entryTime={"Standard": 105 * H1 * 1000.0 if std_used else nan, "Aggressive": nan, "Conservative": nan},
              entryKind={"Standard": O.ENTRY_TEST if std_used else 0, "Aggressive": 0, "Conservative": 0})


def _demote_then_utad(std_used: bool):
    """Bars 120-122 on top of the flat history: two closes under 100, then a bar that closes under mid-range (demotion)
    and pierces the range high (a UTAD on the same bar); returns the engine and the outputs of bar 122."""
    eng = flat()
    eng.s = _phase_d_accum(std_used)
    o120, _ = bar(eng, 100, 100.5, 98.5, 99.0)       # highest of the last 3 closes: 100, not < mid 100
    o121, _ = bar(eng, 99, 99.5, 97.5, 98.5)         # still 100
    o122, t122 = bar(eng, 99, 111, 95, 96.0)         # 99 < 100: demotion, then the probe step sees Phase B
    assert o120["phase"] == o121["phase"] == 4 and o120["in_cde"] and o121["in_cde"]
    return eng, o122, t122


def test_trap01_order_of_operations_within_a_bar():
    """Retirement (lines 1206-1218) runs before the probes (1531-1610), on the same bar. Bar 122: the highest of the
    last 3 closes is 99 < mid-range 100, so the Phase D campaign is demoted to B first (the invalidation needs the
    higher of 2 closes, 98.5, under the spring 88 - 0.5 ATR: no). The probe step then sees Phase B with a mature range:
    bAge = 122 - 60 = 62 >= bMin = clamp(round(max(24, 10 * 4)), 30, 60) = 40, 2 STs, rATR = 20 / 2 = 10 (sane), and
    support = opp + traversals + effort drying up (900 <= 1800 / 2, 1.8 <= 1.05 * 1.8) = 3 (clean is lost: the
    demotion marks a bad test now). ATR: TR = max(111 - 95, 111 - 98.5, 98.5 - 95) = 16, a = (16 + 13 * 2) / 14 = 3.
    The high pierces 110 by 1 (within 0.15 a = 0.45 .. 2.5 a = 7.5), the close 96 is back inside, and the recovery
    score is 4 of 4: cPos = (96 - 95) / 16 = 0.06 <= 0.45, effort 1000 <= 1.5 * 1000, close < open, range 16 >= 0.5 a.
    So the same bar ends in Phase C with a UTAD: distribution. Probes before retirement would have seen Phase D (no
    probe there). The bar also loses the accumulation outcome, so in_cde is False on it, and True on the next bar."""
    eng, o, tr = _demote_then_utad(std_used=False)
    assert abs(tr["a"] - 3.0) < 1e-12 and tr["mature2"] and tr["resetWhy"] == -1
    assert o["phase"] == 3 and o["outcome"] == -1 and o["campaign"] == 40
    assert bits(o) == {"ev_utad"} and o["exc"] == -1 and o["exc_px"] == 111.0
    assert o["hard_hi"] == 111.0 and o["hard_lo"] == 90.0 and o["range_lo"] == 90.0 and o["range_hi"] == 110.0
    assert eng.s.lastBadBar == 122 and eng.rsCounts[O.RS_DEMOTE] == 1
    assert o["in_cde"] is False
    o123, _ = bar(eng, 99.5, 101, 99, 100.0)
    assert o123["phase"] == 3 and o123["outcome"] == -1 and o123["in_cde"] is True


def test_trap02_plen_from_start_of_bar_and_pivot_dedup_across_resets():
    """pLen is read from the state at the START of the bar (line 1105) and the pivot is deduplicated by
    ``pivBar > lastPLBar`` (1319), a var outside the campaign. Bar 120 has the only low of 97 among lows of 99.
    A Phase A campaign with pivLen 2, unabsorbed for 10 bars (> 8), is set before bar 122: on bar 122 pLen = 2, so
    the pivot low two bars back (bar 120, window 118-122) is found and is new; the same bar retires the campaign
    (RS_ABSORB, line 1186). On bar 124, with no campaign, pLen = liveLen = 4 finds bar 120 again (window 116-124),
    but 120 is not > lastPLBar = 120: not new. Without the campaign, bar 122 uses pLen 4 (centre 118: no pivot) and
    the pivot is new on bar 124."""
    def run(with_campaign):
        eng = flat()
        bar(eng, 100, 101, 97, 100)                  # bar 120
        bar(eng, 100, 101, 99, 100)                  # bar 121
        if with_campaign:
            eng.s = ws(stopSide=1, phase=1, ev=O.EV_SC, startBar=112, climaxBar=112, climaxPrice=95.0, origLow=95.0,
                       rangeLow=95.0, climaxEff=3000.0, climaxSpr=6.0, climaxATR=2.0, pivLen=2, birthTrend=-40.0,
                       lastActBar=112)
        o122, t122 = bar(eng, 100, 101, 99, 100)
        o123, t123 = bar(eng, 100, 101, 99, 100)
        o124, t124 = bar(eng, 100, 101, 99, 100)
        return eng, (t122, t123, t124), o122

    eng, (t122, t123, t124), o122 = run(True)
    assert t122["liveLen"] == 4 and t122["pLen"] == 2 and t122["pl"] == 97.0 and t122["pivBar"] == 120
    assert t122["newPL"] and t122["resetWhy"] == O.RS_ABSORB and o122["phase"] == 0
    assert t123["pLen"] == 4 and O.na(t123["pl"])
    assert t124["pLen"] == 4 and t124["pl"] == 97.0 and t124["pivBar"] == 120 and not t124["newPL"]
    assert eng.lastPLBar == 120

    eng, (t122, t123, t124), _ = run(False)
    assert t122["pLen"] == 4 and O.na(t122["pl"]) and not t122["newPL"]
    assert t124["newPL"] and eng.lastPLBar == 120


def test_trap03_state_outside_the_campaign_survives_resets():
    """``regime``, ``regimeBar``, the preliminary support fields and ``lastPLBar`` / ``lastPHBar`` (lines 1093-1101)
    are vars of f_engine, not fields of the campaign: a reset (``s := WS.new()``, line 1233) leaves them alone.
    (a) A Phase B campaign idle for 130 bars > max(125, 20 * 4) is retired as stale on bar 120; the outside state is
    unchanged. (b) What it changes: a Phase D accumulation without an LPS, 10 bars in D (>= max(4, 5)), the last 5
    closes 112 above the range high 110 and confidence 80 >= 75 is accepted into Phase E (line 1704) unless the
    regime left by an earlier campaign is a markdown: then an LPS is required (eOppOKU, line 1702)."""
    eng = flat()
    eng.regime, eng.regimeBar = O.REGIME_MARKDOWN, 30
    eng.prelimBar, eng.prelimTime, eng.prelimPrice, eng.prelimDir, eng.prelimScore = 110, 110 * H1 * 1000, 98.5, 1, 4
    eng.lastPLBar, eng.lastPHBar = 112, 113
    eng.s = ws(stopSide=1, phase=2, ev=O.EV_ST, startBar=-20, climaxBar=-20, climaxPrice=90.0, origLow=90.0,
               rangeLow=90.0, origHigh=110.0, rangeHigh=110.0, climaxATR=2.0, pivLen=4, absorbed=True, arOK=True,
               stCount=1, bStartBar=-10, lastActBar=119 - 130)
    o, tr = bar(eng, 100, 101, 99, 100)
    assert tr["resetWhy"] == O.RS_STALE and o["phase"] == 0
    assert (eng.regime, eng.regimeBar) == (O.REGIME_MARKDOWN, 30)
    assert (eng.prelimBar, eng.prelimPrice, eng.prelimDir, eng.prelimScore) == (110, 98.5, 1, 4)
    assert (eng.lastPLBar, eng.lastPHBar) == (112, 113)

    def phase_d(regime):
        e = flat(o=112.0, h=113.0, l=111.0, c=112.0)
        e.regime = regime
        e.s = ws(stopSide=1, outcome=1, phase=4, ev=O.EV_SOS, startBar=40, climaxBar=40, climaxPrice=90.0,
                 origLow=90.0, rangeLow=90.0, origHigh=110.0, rangeHigh=110.0, climaxATR=2.0, pivLen=4,
                 birthTrend=-40.0, absorbed=True, arOK=True, stCount=2, bStartBar=60, cfPrior=True, cfClimax=True,
                 cfAR=True, cfST=True, cfTest=True, testScore=2, cfStrength=True, strBar=110, dStartBar=110,
                 lastActBar=119)
        return e, bar(e, 112, 113, 111, 112)[0]

    e, o = phase_d(O.REGIME_NONE)
    assert o["phase"] == 5 and "ev_phase_e" in bits(o) and e.regime == O.REGIME_MARKUP and e.regimeBar == 120
    e, o = phase_d(O.REGIME_MARKDOWN)
    assert o["phase"] == 4 and not bits(o) and e.regime == O.REGIME_MARKDOWN


def test_trap04_round_half_up_and_int_truncation():
    """``math.round`` rounds ties up, ``int()`` truncates. By hand: round(4.5) = 5, round(2.5) = 3, round(-2.5) = -2;
    int(3.5) = 3, int(-3.5) = -3. In the engine: a pivLen-6 campaign has recLimit = max(3, round(6 * 0.75 = 4.5)) = 5
    (Python's round gives 4). A probe opened 5 bars before bar 120 (extreme 88.5, 1.5 = 0.75 ATR under the range low
    90) recovers on bar 120: close 100.8 > 90, cPos = 1.8 / 2 = 0.9, effort 1000 <= 1500, close > open, range 2 >= 1:
    4 of 4, and recAge 5 <= 5. Phase B is not mature (12 bars < 30), so it is stored as a provisional spring: exc = +1
    at 88.5, no Spring bit (line 1576-1586). With round-half-even the probe would be 5 > 4 bars old: a failed probe."""
    assert (O.pround(4.5), O.pround(2.5), O.pround(-2.5), O.pround(3.4999)) == (5, 3, -2, 3)
    assert O.pround(0.49999999999999994) == 0         # floor(x + 0.5) would give 1
    assert (O.ptrunc(3.5), O.ptrunc(-3.5), O.ptrunc(3.0)) == (3, -3, 3)
    assert O.f_excursionRecoveryLimit(6) == 5 and round(6 * 0.75) == 4

    def run():
        eng = flat()
        eng.s = ws(stopSide=1, phase=2, ev=O.EV_ST, startBar=100, climaxBar=100, climaxPrice=90.0, origLow=90.0,
                   rangeLow=90.0, origHigh=110.0, rangeHigh=110.0, climaxEff=5000.0, climaxSpr=8.0, climaxATR=2.0,
                   pivLen=6, birthTrend=-40.0, absorbed=True, arOK=True, arBar=104, stCount=1, stN=1,
                   stEffSum=900.0, stSprSum=1.8, stBar=108, bStartBar=108, lastActBar=119, pend=True, pendEdge=1,
                   pendStartBar=115, pendExtBar=115, pendExt=88.5, pendEff=1500.0, pendSpr=3.0)
        return eng, bar(eng, 99.5, 101, 99, 100.8)

    eng, (o, tr) = run()
    assert tr["recLimit2"] == 5 and tr["probeOpen"] and not tr["mature2"]
    assert o["exc"] == 1 and o["exc_px"] == 88.5 and not bits(o) and o["phase"] == 2
    assert eng.s.provEdge == 1 and eng.s.provBar == 115 and eng.s.provPrice == 88.5 and not eng.s.pend

    with pytest.MonkeyPatch.context() as mp:              # the alternative reading: Python's round-half-even
        mp.setattr(O, "pround", lambda x: int(round(x)))
        eng, (o, tr) = run()
    assert tr["recLimit2"] == 4 and not tr["probeOpen"]
    assert o["exc"] == 0 and not eng.s.pend and eng.s.lastBadBar == 120 and eng.s.pendCoolBar == 126


def test_trap05_na_warmup_and_nz_fallbacks():
    """ATR, SMA, highest/lowest and pivots are na until their full length; the engine falls back through nz (lines
    1067-1072): ``a = nz(atr, range)``, ``avgEff = nz(sma50, effort)``, and ``aPrev`` / ``avgEffPrev`` are the
    previous bar's raw values with the current bar's fallback. Bars 0-31: o = c = 100, high 101, low 99, except bar 5
    (102 / 98) and the lows of bars 29 (97) and 30 (96.5); volume 1000 + 10 i. True range 2, bar 5: 4, bar 29:
    max(4, 1, 3) = 4, bar 30: 4.5. Hand values: a = the bar's range on bars 0-12 (4 on bar 5); bar 13 = the SMA of the
    14 true ranges, (13 * 2 + 4) / 14; bar 14 = (2 + 13 * a13) / 14 and aPrev(14) = a13; aPrev(13) = a13 (the
    previous ATR is na). avgEff = the bar's own volume before bar 49. priorLo (the lowest low of the 30 bars before)
    is na through bar 29, so bar 29's 97 is no new low; on bar 30 it is 97 and 96.5 <= 97 is a new low. Pivots need
    2 * 4 + 1 bars: na through bar 7."""
    eng = O.Engine(0.01, H1)
    eng.trace = {}
    tr = {}
    for i in range(32):
        h, lo = (102.0, 98.0) if i == 5 else (101.0, 97.0 if i == 29 else 96.5 if i == 30 else 99.0)
        eng.step(100.0, h, lo, 100.0, 1000.0 + 10 * i, i * H1 * 1000)
        tr[i] = dict(eng.trace)
    trs = [2.0] * 14
    trs[5] = 4.0
    a13 = 0.0
    for x in reversed(trs):                           # ta.sma: sum of x[i] / 14, newest first
        a13 = a13 + x / 14
    assert all(O.na(tr[i]["atrRaw"]) for i in range(13))
    assert tr[0]["a"] == 2.0 and tr[5]["a"] == 4.0 and tr[12]["a"] == 2.0 and tr[5]["aPrev"] == 4.0
    assert tr[13]["a"] == a13 and tr[13]["aPrev"] == a13
    assert tr[14]["a"] == (1.0 / 14) * 2.0 + (1.0 - 1.0 / 14) * a13 and tr[14]["aPrev"] == a13
    assert tr[13]["avgEff"] == 1130.0 and tr[13]["avgEffPrev"] == 1130.0 and tr[31]["avgEff"] == 1310.0
    assert O.na(tr[29]["priorLo"]) and not tr[29]["newLow"]
    assert tr[30]["priorLo"] == 97.0 and tr[30]["newLow"] and tr[31]["priorLo"] == 96.5
    assert all(O.na(tr[i]["ph"]) and O.na(tr[i]["pl"]) for i in range(8)) and tr[0]["liveLen"] == 4
    assert tr[31]["trendScore"] == 0.0                # close[e + n] = close[3 + 32] does not exist yet


def test_trap06_readiness_uses_pivotlen_and_birthtrend():
    """f_entryReadinessWS counts validation with ``nz(s.pivLen, pivotLen)`` and ``s.birthTrend`` (line 971), the
    entry check with ``nz(s.pivLen, liveLen)`` and the bar's trend score (1733). They differ only when pivLen or
    birthTrend is na, which f_seed never leaves (line 735-736), so inside the engine both agree; the case below pins
    the reading on a hand-made state: pivLen na, birthTrend na, liveLen 3, trend 40, a bad test 7 bars ago.
    Readiness's validation (p = 4, trend na): trend 0, absorbed 15, rATR 10 / 2 = 5 -> 10, 2 STs 15, no opposite test
    or traversal 0, clean: 7 < round(8) -> 0, cause 24 / 24 + 0.5 = 1.5 -> 5, terminal 10: 55. The entry check's
    (p = 3, trend 40): 10 + 15 + 10 + 15 + 0 + (7 >= 6: 10) + (24 / 18 + 0.5 = 1.83: 5) + 10 = 75. Readiness with
    the Conservative floor 60: outcome, phase C, terminal (no excursion, a test), distance (105 - 110) / 2 <= 2 and
    age 0 count, confidence 65 < 75 and validation 55 < 60 do not: 5 (6 with the entry check's arguments)."""
    B = O.Bar(200, 200 * H1 * 1000, 105.0, 106.0, 104.0, 105.0, 0.01, H1)
    s = ws(stopSide=1, outcome=1, phase=3, startBar=100, absorbed=True, rangeHigh=110.0, rangeLow=100.0,
           climaxATR=2.0, stCount=2, lastBadBar=193, bStartBar=176, cfPrior=True, cfClimax=True, cfAR=True,
           cfST=True, cfTest=True, lastEventTime=float(B.time))
    assert O.f_validationWS(s, O.nz(s.pivLen, 4), s.birthTrend, 2.0, B) == 55
    assert O.f_validationWS(s, O.nz(s.pivLen, 3), 40.0, 2.0, B) == 75
    assert O.f_confWS(s) == 65
    assert O.f_entryReadinessWS(s, 75, 60, 2.0, B) == 5
    s.pivLen, s.birthTrend = 3, 40.0                  # what f_seed always sets: then the two calls agree
    assert O.f_validationWS(s, O.nz(s.pivLen, 4), s.birthTrend, 2.0, B) == O.f_validationWS(s, 3, -5.0, 2.0, B) == 75
    assert O.f_entryReadinessWS(s, 75, 60, 2.0, B) == 6


def _untested_spring(tested: bool):
    """Phase C accumulation after a spring at 98 (range 100-120, climax ATR 2: rATR 10), Phase B from bar 115, a bad
    test on bar 120, one opposite test, no traversal, birth trend 20; the spring tested (excTested, cfTest) or not."""
    return ws(stopSide=1, outcome=1, phase=3, ev=O.EV_TEST if tested else O.EV_SPRING, startBar=60, climaxBar=60,
              climaxPrice=100.0, origLow=100.0, rangeLow=100.0, origHigh=120.0, rangeHigh=120.0, climaxEff=5000.0,
              climaxSpr=8.0, climaxATR=2.0, pivLen=4, birthTrend=20.0, absorbed=True, arOK=True, arBar=64,
              stCount=2, stN=2, stEffSum=1800.0, stSprSum=3.6, lastGoodEff=900.0, lastGoodSpr=1.8, stBar=116,
              oppCount=1, opN=1, travCount=0, bStartBar=115, lastBadBar=120, exc=True, excTested=tested, excBar=117,
              excPrice=98.0, excEff=2000.0, excSpr=4.0, cReadyBar=118 if tested else nan, cfTest=tested,
              testScore=2 if tested else 0, cfPrior=True, cfClimax=True, cfAR=True, cfST=True, cfExc=True,
              lastActBar=119)


def test_trap07_cformal_bonuses_for_an_untested_spring():
    """An untested spring gets +13 validation and +30 confidence for the C -> D test (lines 1615-1621). Flat history at
    114 (high 115, low 113). Bar 121 = (114, 116.2, 113.8, 116), volume 2400: TR = max(2.4, 2.2, 0.2) = 2.4, a =
    (2.4 + 26) / 14 = 2.03, relE = 2400 / 1028 = 2.33, range / a = 1.18, cPos = 2.2 / 2.4 = 0.92, body 2 >= 1.01:
    sosScore 4; the last 3 closes 114, 114, 116 >= 100 + 0.65 * 20 = 113. Validation on bar 121: trend 20 -> 5,
    absorbed 15, rATR 10 -> 5, 2 STs 15, an opposite test 8, not clean (bad test 1 bar ago), cause 6 / 24 + 0.5 < 1.5
    -> 0: 48 untested; the tested spring adds the terminal 10: 58. Untested: 48 + 13 = 61 >= 60 -> SOS, Phase D (and
    the Aggressive SOS entry: confidence 80, validation 48 + 10 + 3 = 61, readiness 7 of 9: all but the terminal test
    and the LPS); tested: 58 < 60, no bonus -> stays in C.
    Bar 120 (flat) has no strength (sosScore 0, no multi-bar SOS, no 3-bar rise), so neither moves there."""
    def run(tested):
        eng = flat(o=114.0, h=115.0, l=113.0, c=114.0)
        eng.s = _untested_spring(tested)
        o120, _ = bar(eng, 114, 115, 113, 114)
        o121, t121 = bar(eng, 114, 116.2, 113.8, 116.0, v=2400.0)
        return eng, o120, o121, t121

    eng, o120, o121, tr = run(False)
    assert o120["phase"] == 3 and tr["sosScore"] == 4
    assert o121["phase"] == 4 and "ev_sos" in bits(o121) and eng.s.strBar == 121
    assert o121["entries"]["Aggressive"] == 1 and o121["entries"]["Standard"] == 0
    eng, o120, o121, tr = run(True)
    assert o121["phase"] == 3 and not bits(o121) and o121["entries"]["Aggressive"] == 0


def _phase_c_ctest(probe: bool, last_act: int = 119):
    """Phase C accumulation entered by a terminal test (no spring): range 100-120, hard level min(100, 100) = 100;
    with a probe opened on bar 119 at 98 (depth 2 ATR-units of 1), or without a probe and in cooldown."""
    extra = (dict(pend=True, pendEdge=1, pendStartBar=119, pendExtBar=119, pendExt=98.0, pendEff=1500.0, pendSpr=3.0)
             if probe else dict(pendCoolBar=200))
    return ws(stopSide=1, outcome=1, phase=3, ev=O.EV_CTEST_ACC, startBar=40, climaxBar=40, climaxPrice=100.0,
              origLow=100.0, rangeLow=100.0, origHigh=120.0, rangeHigh=120.0, climaxEff=5000.0, climaxSpr=8.0,
              climaxATR=2.0, pivLen=4, birthTrend=-40.0, absorbed=True, arOK=True, stCount=2, stN=2,
              stEffSum=1800.0, stSprSum=3.6, bStartBar=60, cfPrior=True, cfClimax=True, cfAR=True, cfST=True,
              cfTest=True, testScore=2, cReadyBar=110, lastActBar=last_act, **extra)


def test_trap08_open_probe_suspends_phase_c_invalidation_and_stale():
    """``probeOpen`` (a probe at most recLimit(4) = 3 bars old, line 1171) suspends the Phase C invalidation (1198)
    and the stale reset (1227). Invalidation: bars 120 (close 98.6) and 121 (close 98.8): the higher of the last 2
    closes on bar 121 is 98.8 < 100 - 0.5 * a, a = (1 + 13 * 2.0286) / 14 = 1.955, i.e. 99.02. With the probe (2 bars
    old, not recovered: closes under 100, depth 100 - 98 = 2 within 0.15 a .. 2.5 a) the campaign survives bars 121
    and 122; on bar 123 the probe is 4 > 3 bars old and the same test retires it. Without a probe (cooldown, so none
    can open) bar 121 retires it. Stale: last activity 61 bars ago > max(50, 8 * 4) = 50; a bar closing at 99.8
    (no invalidation: max(100, 99.8) >= 99) retires the campaign without a probe and not with one."""
    eng = flat()
    eng.s = _phase_c_ctest(probe=True)
    o120, t120 = bar(eng, 100, 100.5, 98.1, 98.6)
    o121, t121 = bar(eng, 98.6, 99.3, 98.3, 98.8)
    o122, t122 = bar(eng, 98.8, 99.2, 98.4, 98.9)
    o123, t123 = bar(eng, 98.9, 99.1, 98.5, 98.7)
    assert t121["probeOpen"] and t122["probeOpen"] and not t123["probeOpen"]
    assert o120["phase"] == o121["phase"] == o122["phase"] == 3 and o121["outcome"] == 1
    assert t123["resetWhy"] == O.RS_INVALID and o123["phase"] == 0 and o123["in_cde"] is False

    eng = flat()
    eng.s = _phase_c_ctest(probe=False)
    o120, _ = bar(eng, 100, 100.5, 98.1, 98.6)
    o121, t121 = bar(eng, 98.6, 99.3, 98.3, 98.8)
    assert o120["phase"] == 3 and t121["resetWhy"] == O.RS_INVALID and o121["phase"] == 0

    for probe, want in ((True, 3), (False, 0)):
        eng = flat()
        eng.s = _phase_c_ctest(probe=probe, last_act=59)
        o, tr = bar(eng, 100, 100.5, 99.5, 99.8)
        assert o["phase"] == want and tr["resetWhy"] == (-1 if probe else O.RS_STALE)


def test_trap09_demotion_keeps_the_used_entry_slot():
    """f_demoteToB (909-930) does not clear ``entryTime``, so a campaign that has taken its Standard entry and is
    demoted cannot take another (line 1729). The scenario of trap 1 continues: the UTAD of bar 122 (111, effort
    1000, range 16) is tested by the pivot high of bar 127 (108, effort 700 <= 800, range 9 <= 12.8, cPos 0.06),
    known on bar 131 (pLen 4): 108 >= 110 - 1.25 * 3.35 and <= 111 + 0.15 * 3.35. Quality on bar 131: confidence 65
    (the demotion cleared the SOS), validation 90, readiness 7, test score 3. With the Standard slot used before the
    demotion no Standard entry fires; the Aggressive slot is free and fires; with the slot free both fire (short)."""
    def run(std_used):
        eng, _, _ = _demote_then_utad(std_used)
        assert O.na(eng.s.entryTime["Standard"]) != std_used        # the demotion kept the slot as it was
        outs = [bar(eng, 99.5, 101, 99, 100.0)]                     # 123
        outs += [bar(eng, 100, 101, 99, 100.0) for _ in range(3)]   # 124-126 (126: the UTAD bar is a pivot, not a test)
        outs.append(bar(eng, 100, 108, 99, 99.5, v=700.0))          # 127: the test's pivot bar
        outs.append(bar(eng, 99.5, 101, 99, 100.0))                 # 128
        outs += [bar(eng, 100, 101, 99, 100.0) for _ in range(3)]   # 129-131
        return eng, outs

    eng, outs = run(std_used=True)
    o131, t131 = outs[-1]
    assert outs[3][1]["newPH"] and outs[3][1]["pivBar"] == 122 and not bits(outs[3][0])
    assert t131["newPH"] and t131["pivBar"] == 127 and abs(t131["pA"] - 3.3497) < 1e-3
    assert bits(o131) == {"ev_test"} and eng.s.excTested and eng.s.testScore == 3
    assert o131["entries"] == {"Standard": 0, "Aggressive": -1, "Conservative": 0}
    assert O.f_confWS(eng.s) == 65
    eng, outs = run(std_used=False)
    assert outs[-1][0]["entries"] == {"Standard": -1, "Aggressive": -1, "Conservative": 0}
    assert eng.s.entryKind["Standard"] == O.ENTRY_TEST


def test_trap10_plused_blocks_ab_tests_not_traversals():
    """``plUsed`` (set by the A -> B transition, line 1390) only keeps the same pivot out of the Phase B test blocks
    (1413); the traversal block (1465-1475) reads ``newPL`` and counts it. Phase A: SC low 95, AR 106 (bar 108),
    climax effort 5000 / range 8. Bar 120 (low 96, close 99, range 4) is a pivot low known on bar 124: |96 - 95| = 1
    <= 0.75 * pA (pA = ATR of bar 120 = (4 + 26) / 14 = 2.14), holds, cPos 0.75, effort and range under 0.9 of the
    climax's, 20 bars after the climax >= 8, 12 after the AR >= 4: the ST, Phase B from bar 120, range low
    max(95, (96 + 95) / 2) = 95.5. The same pivot is in the low zone (96 <= 95.5 + 0.25 * 10.5) and sets lastZone -1.
    Bar 126 (high 104) is a pivot high known on bar 130, in the top zone (104 >= 106 - 2.625) and near the edge, with
    the climax's effort cap: an opposite test, and the move from the low zone to the top zone is 1 traversal (it would
    be 0 if plUsed had also blocked the traversal block)."""
    eng = flat()
    eng.s = ws(stopSide=1, phase=1, ev=O.EV_SC, startBar=100, climaxBar=100, climaxPrice=95.0, origLow=95.0,
               rangeLow=95.0, climaxEff=5000.0, climaxSpr=8.0, climaxATR=2.0, climaxScore=5, absorbed=True,
               cfPrior=True, cfClimax=True, pivLen=4, birthTrend=-40.0, arOK=True, arRunPrice=106.0, arRunBar=108,
               rangeHigh=106.0, origHigh=106.0, lastActBar=119)
    bar(eng, 99.5, 100, 96, 99)                                     # 120
    for _ in range(3):
        bar(eng, 100, 101, 99, 100)                                 # 121-123
    o124, t124 = bar(eng, 100, 101, 99, 100)
    assert t124["newPL"] and t124["pivBar"] == 120 and bits(o124) == {"ev_ar", "ev_st"}
    s = eng.s
    assert s.phase == 2 and s.bStartBar == 120 and s.rangeLow == 95.5 and s.rangeHigh == 106.0
    assert s.stCount == 1 and s.lastZone == -1 and s.lastZoneBar == 120 and s.travCount == 0
    bar(eng, 100, 101, 99, 100)                                     # 125
    bar(eng, 100, 104, 99.5, 100.5)                                 # 126
    for _ in range(3):
        bar(eng, 100, 101, 99, 100)                                 # 127-129
    o130, t130 = bar(eng, 100, 101, 99, 100)
    assert t130["newPH"] and t130["pivBar"] == 126 and not t130["newPL"]
    assert s.oppCount == 1 and s.travCount == 1 and s.lastZone == 1 and s.lastZoneBar == 126


def test_trap11_volume_source_and_no_vol():
    """Effort is the bar's volume, or its range while the cumulative volume is still 0 (lines 1063-1066; the switch
    is permanent once volume appears). The climax gate is effort >= 1.8 x the previous bar's 50-bar average (1255).
    (a) A heartbeat volume (60 on every bar, like Exness BTC ticks) leaves relE at 1 and never opens the gate, even on
    a bar 4 times as wide; a real volume of 150 on that bar opens it (150 >= 1.8 * 60). (b) Zero volume: effort =
    range, so the wide bar (range 8 vs 2) opens it: 8 >= 1.8 * 2. (c) Volume from bar 10 on: effort is the range on
    bars 0-9, the volume after, and 0 (not the range) on a later bar without volume."""
    def run(vols, wide_at):
        eng = O.Engine(0.01, H1)
        eng.trace = {}
        out = []
        for i, v in enumerate(vols):
            h, lo = (104.0, 96.0) if i == wide_at else (101.0, 99.0)
            eng.step(100.0, h, lo, 100.0, v, i * H1 * 1000)
            out.append(dict(eng.trace))
        return out

    tr = run([60.0] * 70, 60)
    # the reference SMA sums 60 / 50 fifty times: 60.00000000000006, not 60
    assert tr[60]["eff"] == 60.0 and abs(tr[60]["avgEffPrev"] - 60.0) < 1e-9 and not tr[60]["volHit"]
    tr = run([60.0] * 60 + [150.0] + [60.0] * 9, 60)
    assert tr[60]["eff"] == 150.0 and tr[60]["volHit"] and tr[60]["sprHit"]
    tr = run([0.0] * 70, 60)
    assert tr[60]["eff"] == 8.0 and abs(tr[60]["avgEffPrev"] - 2.0) < 1e-12 and tr[60]["volHit"]
    tr = run([0.0] * 10 + [500.0] * 10 + [0.0] + [500.0] * 9, -1)
    assert [tr[i]["eff"] for i in (0, 9, 10, 20, 21)] == [2.0, 2.0, 500.0, 0.0, 500.0]
    o, h, lo, c, v, t = synth(600, 3)
    assert all(same(a, b) for a, b in zip(O.wyckoff(o, h, lo, c, v, t, no_vol=True).values(),
                                          O.wyckoff(o, h, lo, c, np.zeros(600), t).values()))


def test_trap12_path_dependence_on_history_start():
    """The outputs depend on where the bars start. (a) The ATR's RMA remembers its seed: 40 bars of true range 2, but
    bar 3 is 9 wide. From bar 0 the seed (bar 13) is (13 * 2 + 9) / 14 = 2.5 and a decays to 2 + 0.5 (13/14)^k; from
    bar 5 the seed is 2 and stays 2. (b) The regime is never reset: a Phase D distribution without an LPSY, 10 bars in
    D, the last 5 closes 98 under the range low 100 and confidence 80 is accepted into Phase E (markdown) when the
    history holds no earlier campaign, and not when an earlier one left a markup (eOppOKD, line 1716). The real-data
    test below shows the size of the effect (gold 4H started 300 bars before 2019 changes events in 2022)."""
    bars_ = [(100.0, 105.5, 96.5, 100.0) if i == 3 else (100.0, 101.0, 99.0, 100.0) for i in range(40)]

    def a_series(start):
        eng = O.Engine(0.01, H1)
        eng.trace = {}
        out = []
        for i, (o, h, lo, c) in enumerate(bars_[start:]):
            eng.step(o, h, lo, c, 1000.0, i * H1 * 1000)
            out.append(eng.trace["a"])
        return out

    full, late = a_series(0), a_series(5)
    assert abs(full[13] - 2.5) < 1e-12 and abs(full[39] - (2 + 0.5 * (13 / 14) ** 26)) < 1e-12
    assert all(abs(x - 2.0) < 1e-12 for x in late[13:]) and abs(full[39] - late[34]) > 0.07

    def phase_d_dist(regime):
        e = flat(o=98.0, h=99.0, l=97.0, c=98.0)
        e.regime = regime
        e.s = ws(stopSide=-1, outcome=-1, phase=4, ev=O.EV_SOW, startBar=40, climaxBar=40, climaxPrice=120.0,
                 origHigh=120.0, rangeHigh=120.0, origLow=100.0, rangeLow=100.0, climaxATR=2.0, pivLen=4,
                 birthTrend=40.0, absorbed=True, arOK=True, stCount=2, bStartBar=60, cfPrior=True, cfClimax=True,
                 cfAR=True, cfST=True, cfTest=True, testScore=2, cfStrength=True, strBar=110, dStartBar=110,
                 lastActBar=119)
        return e, bar(e, 98, 99, 97, 98)[0]

    e, o = phase_d_dist(O.REGIME_NONE)
    assert o["phase"] == 5 and "ev_phase_e" in bits(o) and e.regime == O.REGIME_MARKDOWN
    e, o = phase_d_dist(O.REGIME_MARKUP)
    assert o["phase"] == 4 and not bits(o)


# ───────────────────────────── 3. invariants on synthetic bars ─────────────────────────────

@pytest.fixture(scope="module")
def synthetic():
    out = {}
    for seed in (16, 19):
        o, h, lo, c, v, t = synth(8000, seed)
        out[seed] = ((o, h, lo, c, v, t), O.wyckoff(o, h, lo, c, v, t))
    return out


def test_synthetic_runs_reach_every_phase(synthetic):
    for seed, (_, r) in synthetic.items():
        assert set(np.unique(r["phase"])) >= {0, 1, 2, 3, 4}, seed
        assert set(r) == set(O.OUTPUT_KEYS)
    assert 5 in synthetic[16][1]["phase"]
    (_, r16), (_, r19) = synthetic[16], synthetic[19]
    assert (r16["entry_std"] != 0).sum() >= 1 and (r16["entry_con"] != 0).sum() >= 1
    assert (r19["entry_std"] == -1).sum() >= 1 or (r19["entry_con"] == -1).sum() >= 1


def test_truncation_invariance(synthetic):
    """Outputs up to bar T are unchanged when the bars after T are removed (no look-ahead)."""
    for seed, (bars_, full) in synthetic.items():
        n = len(bars_[0])
        events = np.flatnonzero((full["entry_std"] != 0) | (full["entry_agg"] != 0) | full["ev_sos"] | full["ev_sow"])
        cuts = sorted({n // 4, n // 2, n - 2, *(int(i) for i in events[:3])})
        for T in cuts:
            cut = O.wyckoff(*(x[:T + 1] for x in bars_))
            for k in O.OUTPUT_KEYS:
                assert same(full[k][:T + 1], cut[k]), (seed, T, k)


def test_entry_modes_one_pass_equals_three_passes(synthetic):
    """The entry check writes only its own slot (lines 1729-1747), so one pass with three slots equals three runs
    of the script, one per entryStrictness."""
    for seed, (bars_, full) in synthetic.items():
        for mode, key in O.ENTRY_KEY.items():
            single = O.wyckoff(*bars_, _modes=(mode,))
            assert same(single[key], full[key]), (seed, mode)
            for k in O.OUTPUT_KEYS:
                if not k.startswith("entry_"):
                    assert same(single[k], full[k]), (seed, mode, k)
                elif k != key:
                    assert not single[k].any()


def test_mirror_image(synthetic):
    """Negated prices (high <-> low) give the same bars with SC <-> BC, spring <-> UTAD, SOS <-> SOW, LPS <-> LPSY and
    the outcome, entries and levels negated: every comparison of the engine has its exact mirror, and negation is
    exact in floating point (the low side is evaluated first, so a bar with a new pivot high and low at once could
    break the symmetry; it does not happen here). The range levels agree to one ulp, not bit for bit: f_robustEdge's
    median ``e1 + e2 + e3 - max - min`` (line 693) subtracts the max first on both sides, which for negated edges is
    the min first, a different rounding (up to 2.3e-13 at price 2000 on seed 16)."""
    swap = {"ev_sc": "ev_bc", "ev_bc": "ev_sc", "ev_spring": "ev_utad", "ev_utad": "ev_spring", "ev_sos": "ev_sow",
            "ev_sow": "ev_sos", "ev_lps": "ev_lpsy", "ev_lpsy": "ev_lps"}
    for seed, ((o, h, lo, c, v, t), r) in synthetic.items():
        m = O.wyckoff(-o, -lo, -h, -c, v, t)
        for k in O.EVENT_BITS:
            assert same(r[k], m[swap.get(k, k)]), (seed, k)
        for k in ("outcome", "climax", "exc", "entry_std", "entry_agg", "entry_con", "climax_px", "exc_px"):
            assert same(r[k], -m[k]), (seed, k)
        for k in ("phase", "campaign", "in_cde"):
            assert same(r[k], m[k]), (seed, k)
        for a_, b_ in (("range_lo", "range_hi"), ("range_hi", "range_lo"), ("hard_lo", "hard_hi"),
                       ("hard_hi", "hard_lo")):
            x, y = r[a_], -m[b_]
            assert np.array_equal(np.isnan(x), np.isnan(y)), (seed, a_)
            ok = ~np.isnan(x)
            assert np.all(np.abs(x[ok] - y[ok]) <= 1e-9), (seed, a_)


def test_contract_shapes_and_x_s_derivation(synthetic):
    for seed, ((o, h, lo, c, v, t), r) in synthetic.items():
        n = len(c)
        dtypes = {"phase": np.int8, "outcome": np.int8, "campaign": np.int32, "climax": np.int8, "exc": np.int8,
                  "entry_std": np.int8, "entry_agg": np.int8, "entry_con": np.int8}
        for k in O.OUTPUT_KEYS:
            assert len(r[k]) == n
            if k in dtypes:
                assert r[k].dtype == dtypes[k], k
            elif k.startswith("ev_") or k == "in_cde":
                assert r[k].dtype == bool, k
            else:
                assert r[k].dtype == np.float64, k
        _check_contract_values(r)


def _check_contract_values(r, where=""):
    """What the contract says exists, exists; and the X-S exit can be read from in_cde."""
    ph, out, camp = r["phase"], r["outcome"], r["campaign"]
    assert np.array_equal(ph == 0, camp == -1), where
    assert np.array_equal(out != 0, np.isin(ph, (3, 4, 5))), where          # an outcome only in Phases C-E
    assert not (r["in_cde"] & (out == 0)).any(), where
    inb = ph >= 2
    assert not np.isnan(r["range_lo"][inb]).any() and not np.isnan(r["range_hi"][inb]).any(), where
    assert not np.isnan(r["hard_lo"][inb]).any() and not np.isnan(r["hard_hi"][inb]).any(), where
    assert np.isnan(r["range_lo"][ph == 0]).all() and np.isnan(r["hard_hi"][ph == 0]).all(), where
    a_sc = (ph == 1) & ~np.isnan(r["hard_lo"])
    assert not np.isnan(r["range_lo"][a_sc]).any(), where
    assert np.array_equal(r["climax"] != 0, r["ev_sc"] | r["ev_bc"]), where
    assert np.array_equal(r["climax"] == 1, r["ev_sc"]), where
    assert np.array_equal(~np.isnan(r["climax_px"]), r["climax"] != 0), where
    assert np.array_equal(~np.isnan(r["exc_px"]), r["exc"] != 0), where
    for k in ("entry_std", "entry_agg", "entry_con"):
        e = np.flatnonzero(r[k] != 0)
        assert np.array_equal(r[k][e], out[e]), (where, k)                  # the direction is the outcome
        hard = np.where(r[k][e] == 1, r["hard_lo"][e], r["hard_hi"][e])
        assert not np.isnan(hard).any(), (where, k)                          # the S-W stop level exists
    # within a run of in_cde the campaign and the outcome do not change
    run = r["in_cde"][1:] & r["in_cde"][:-1]
    assert np.array_equal(camp[1:][run], camp[:-1][run]) and np.array_equal(out[1:][run], out[:-1][run]), where


# ───────────────────────────── 4. real bars ─────────────────────────────

D_START, D_END = "2019-01-01", "2023-01-01"         # Development: bars closing in 2019-2022


@pytest.fixture(scope="module")
def real():
    """Bars of a symbol from its data start to 2024-06-30 (``end="2024-07-01"``): 1H / 4H / 1D TBars, the market's
    tick, and for BTC the Binance volume when its files are on this machine; engine results are cached."""
    from backtesting.data import store
    from backtesting.research import tradeiq_market as TM
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            mk = TM.load(symbol, end="2024-07-01")
            tb = {tf: mk.tbars(tf) for tf in ("1H", "4H", "1D")}
            rv = {}
            if symbol.startswith("BTC"):
                if not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
                    pytest.skip("the Binance files are not on this machine")
                rv = {tf: TM.binance_volume(mk, tf)[0] for tf in tb}
            cache[symbol] = {"tick": mk.tick, "bars": tb, "rv": rv, "runs": {}, "TM": TM}
            del mk
        return cache[symbol]

    def run(symbol, tf, vol="main"):
        d = get(symbol)
        key = (tf, vol)
        if key not in d["runs"]:
            b = d["bars"][tf]
            v = d["rv"][tf] if (symbol.startswith("BTC") and vol == "main") else b.vol
            d["runs"][key] = O.wyckoff(b.o, b.h, b.l, b.c, v, b.t, mintick=d["tick"])
        return d["bars"][tf], d["runs"][key]

    return get, run


def _dev(TM, b):
    return (b.tc > TM.s_of(D_START)) & (b.tc <= TM.s_of(D_END))


def _entries(TM, b, r, key="entry_std", dev=True):
    m = (r[key] != 0) & (_dev(TM, b) if dev else True)
    return [(str(TM.utc(b.t[i]))[:16], int(r[key][i])) for i in np.flatnonzero(m)]


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    get, run = real
    d = get(symbol)
    TM = d["TM"]
    assert O.infer_mintick(d["bars"]["1H"].o, d["bars"]["1H"].c) == d["tick"]   # the default mintick is the config's
    for tf in ("1H", "4H", "1D"):
        b, r = run(symbol, tf)
        assert int(b.tc[-1]) <= TM.CUT_S and int(b.t[-1]) < TM.CUT_S            # nothing from the hold-out
        assert set(r) == set(O.OUTPUT_KEYS) and all(len(x) == len(b) for x in r.values())
        _check_contract_values(r, f"{symbol} {tf}")
        assert set(np.unique(r["phase"])) >= {0, 1, 2}, tf
        assert (r["climax"] != 0).sum() > 0, tf


def test_real_bars_cross_check_vectors(real):
    """The specification's vectors (section 6, from an unreviewed scratch port; Standard entries, bar open times UTC,
    Development). Port B reproduces every entry and the climax counts; its spring / UTAD recoveries (the WY-SP family)
    are the scratch port's counts minus the B -> D adoptions of a provisional excursion, which the scratch port counted
    a second time on the adoption bar (gold 1H 2, BTC 1H 1, BTC 4H 1): PREREG 6.3 enters WY-SP at the recovery bar."""
    get, run = real
    TM = get("XAUUSDm")["TM"]
    b, r = run("XAUUSDm", "1H")
    assert _entries(TM, b, r) == [("2020-07-16 07:00", -1), ("2021-06-28 19:00", 1), ("2021-10-31 23:00", -1),
                                  ("2021-11-23 04:00", -1)]
    assert "ev_ctest" in {k for k in O.EVENT_BITS if r[k][np.searchsorted(b.t, TM.s_of("2020-07-16 07:00"))]}
    dev = _dev(TM, b)
    assert ((r["climax"] == 1) & dev).sum() == 52 and ((r["climax"] == -1) & dev).sum() == 105
    assert ((r["exc"] != 0) & dev).sum() == 66 - 2
    b, r = run("XAUUSDm", "4H")
    assert _entries(TM, b, r) == [("2020-05-24 20:00", -1), ("2022-01-04 08:00", 1)]
    assert ((r["climax"] != 0) & _dev(TM, b)).sum() == 50 and ((r["exc"] != 0) & _dev(TM, b)).sum() == 11
    b, r = run("XAUUSDm", "1D")
    assert _entries(TM, b, r) == [] and ((r["climax"] != 0) & _dev(TM, b)).sum() == 6
    assert ((r["exc"] != 0) & _dev(TM, b)).sum() == 0

    b, r = run("BTCUSDm", "4H")
    assert _entries(TM, b, r) == [("2019-01-24 16:00", 1), ("2020-06-10 12:00", -1), ("2020-07-04 12:00", 1),
                                  ("2021-06-25 00:00", 1), ("2021-12-25 00:00", 1)]
    assert "ev_lps" in {k for k in O.EVENT_BITS if r[k][np.searchsorted(b.t, TM.s_of("2021-12-25 00:00"))]}
    assert ((r["climax"] != 0) & _dev(TM, b)).sum() == 95 and ((r["exc"] != 0) & _dev(TM, b)).sum() == 26 - 1
    b, r = run("BTCUSDm", "1H")
    e = _entries(TM, b, r)
    assert len(e) == 14 and e[0] == ("2019-02-23 15:00", -1) and e[-1] == ("2022-12-06 04:00", -1)
    assert ((r["climax"] != 0) & _dev(TM, b)).sum() == 375 and ((r["exc"] != 0) & _dev(TM, b)).sum() == 123 - 1
    b, r = run("BTCUSDm", "1D")
    assert _entries(TM, b, r) == [] and ((r["climax"] != 0) & _dev(TM, b)).sum() == 18
    assert ((r["exc"] != 0) & _dev(TM, b)).sum() == 4
    # the control: BTC on Exness tick volume (a heartbeat; trap 11) gives 1 / 0 / 0 Standard entries
    assert [len(_entries(TM, *run("BTCUSDm", tf, vol="tick"))) for tf in ("1H", "4H", "1D")] == [1, 0, 0]


def test_real_bars_in_cde_same_bar_break(real):
    """in_cde differs from "outcome != 0" on one bar of the six series: BTC 1H 2023-11-22 00:00 (Validation), where the
    campaign of the 2023-11-17 19:00 Standard long is demoted from Phase D (3 closes under mid-range) and re-enters
    Phase C with a spring on the same bar. The X-S exit of that long is this bar; the Standard slot stays used."""
    get, run = real
    TM = get("BTCUSDm")["TM"]
    for symbol in ("XAUUSDm", "BTCUSDm"):
        for tf in ("1H", "4H", "1D"):
            b, r = run(symbol, tf)
            odd = np.flatnonzero((r["outcome"] != 0) & ~r["in_cde"])
            if (symbol, tf) != ("BTCUSDm", "1H"):
                assert len(odd) == 0, (symbol, tf)
                continue
            assert [str(TM.utc(b.t[i]))[:16] for i in odd] == ["2023-11-22 00:00"]
            i = int(odd[0])
            assert r["phase"][i - 1] == 4 and r["phase"][i] == 3 and r["outcome"][i - 1] == r["outcome"][i] == 1
            assert r["campaign"][i - 1] == r["campaign"][i] and r["ev_spring"][i] and r["exc"][i] == 1
            k = int(np.searchsorted(b.t, TM.s_of("2023-11-17 19:00")))
            assert r["entry_std"][k] == 1 and r["campaign"][k] == r["campaign"][i] and r["in_cde"][k + 1:i].all()


def test_real_bars_truncation_and_start_invariance(real):
    """Gold 4H: truncation at 4 points changes nothing before the cut; starting the bars 1,000 or more bars before
    2019 gives the same outputs from 2019 on as starting at the data start (2017), starting 300 bars before does not
    (the regime and pivot state, trap 12: the 2022-01-04 LPS entry is among the differences)."""
    get, run = real
    TM = get("XAUUSDm")["TM"]
    b, full = run("XAUUSDm", "4H")
    tick = get("XAUUSDm")["tick"]
    cols = (b.o, b.h, b.l, b.c, b.vol, b.t)
    n = len(b)
    for T in (n // 3, n // 2, (2 * n) // 3, n - 7):
        cut = O.wyckoff(*(x[:T + 1] for x in cols), mintick=tick)
        assert all(same(full[k][:T + 1], cut[k]) for k in O.OUTPUT_KEYS), T
    i19 = int(np.searchsorted(b.tc, TM.s_of(D_START), side="right"))

    def from_start(keep):
        k0 = i19 - keep
        r = O.wyckoff(*(x[k0:] for x in cols), mintick=tick)
        diff = np.zeros(n - i19, bool)
        for k in O.OUTPUT_KEYS:
            a_, b_ = full[k][i19:], r[k][i19 - k0:]
            if k == "campaign":
                a_ = np.where(a_ >= 0, a_ - k0, -1)
            diff |= ~((a_ == b_) | (np.isnan(a_) & np.isnan(b_))) if a_.dtype.kind == "f" else (a_ != b_)
        return diff

    assert not from_start(1000).any()
    d300 = from_start(300)
    i_lps = int(np.searchsorted(b.t, TM.s_of("2022-01-04 08:00"))) - i19
    assert d300.any() and d300[i_lps]
