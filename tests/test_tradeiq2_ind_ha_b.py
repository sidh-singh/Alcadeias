"""
Port B (the oracle) of LunqFX's "Heikin Ashi Candles, Trend Strength & Trend Age Stats", ``tests/tradeiq2_oracle_ha.py``
(study 2, PREREG 6.8).

1. One hand-computed test per trap of the spec's porting risks (``maps/orb_session_swing_ha.md`` 4.6 "Risks", nine
   items), named after it: the ``haO`` start value, a tie counted as bullish, the order of the phase tests, a
   zero-range bar being STRONG, WEAK comparing with ``body[1]``, ``strongRun`` reset at a flip before ``evInd`` is
   evaluated, ``evFirstSt`` firing on the flip bar, streak lengths pushed at the flip, ``rareNow`` computed causally.
   Each builds bars by hand and states the expected values with their arithmetic.
2. The spec's other test cases (4.6 "Tests" 1-8; most are inside the trap tests) and the module's own choices: the
   5000 cap, ``survive`` and SK / SN on a hand-made list of streaks, ``weak_run``, the contract, the inputs.
3. Truncation invariance: the outputs up to bar T are unchanged when the bars after T are removed, and a streak's row
   appears exactly at the close of its flip bar.
4. Real bars (skipped when the tick store is absent): both symbols, the 1H / 4H / 1D bars PREREG 6.8 uses for this
   script, from the data start to 2024-06-30 (study 1's guard pointed at an empty folder, so the hold-out cannot be
   served): it runs, every value the contract defines exists, an independent numpy / bisect formulation agrees bit
   for bit, and a cut at one T changes nothing before it.

Port A (``backtesting/research/tradeiq2_ind_ha.py``) was not read or imported; the two are compared later.
"""

from __future__ import annotations

import bisect
import inspect
import math
import sys
from collections import deque
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_ha as O  # noqa: E402

F, T_ = False, True              # short names for the expected bool lists (``T`` is a candle shape below)


# ───────────────────────────── helpers ─────────────────────────────

def same(a, b) -> bool:
    """Bit-for-bit equality, NaN equal to NaN, dtypes equal."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        return bool(np.array_equal(a.view(np.int64), b.view(np.int64)) or np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def walk(n, seed, p0=1500.0, vol=2.0):
    """A random walk with wicks (gold-like for p0 = 1500, BTC-like for p0 = 30000, vol = 100), with a few gaps."""
    rng = np.random.default_rng(seed)
    c = p0 + np.cumsum(rng.normal(0.0, vol, n))
    o = np.r_[p0, c[:-1]] + rng.normal(0.0, vol / 4, n) * (rng.random(n) < 0.05)
    h = np.maximum(o, c) + rng.uniform(0.0, vol, n) * (rng.random(n) < 0.9)
    l = np.minimum(o, c) - rng.uniform(0.0, vol, n) * (rng.random(n) < 0.9)
    return o, h, l, c


class HA:
    """
    Bars built from the Heikin Ashi candles a test wants. Bar 0 is given as a raw bar. Every later bar is given as a
    shape: a function of the bar's ``haO``, which is known before the bar (``(haO[1] + haC[1]) / 2``, l.81), that
    returns the wanted (haC, haH, haL). The bar is then H = haH, L = haL, O = C = (4 haC - haH - haL) / 2: it gives
    ``haC = (O + H + L + C) / 4`` exactly (asserted: the shapes use small dyadic numbers) and keeps haH / haL as the
    candle's extremes (``haH = max(H, haO, haC) = H``, ``haL = min(L, haO, haC) = L``).
    """

    def __init__(self, o, h, l, c):
        self.o, self.h, self.l, self.c = [float(o)], [float(h)], [float(l)], [float(c)]
        self.hao = (float(o) + float(c)) / 2.0
        self.hac = (float(o) + float(h) + float(l) + float(c)) / 4.0

    def add(self, shape, *args):
        hao = (self.hao + self.hac) / 2.0
        hac, hah, hal = shape(hao, *args)
        m = (4.0 * hac - hah - hal) / 2.0
        assert hal <= m <= hah and hah >= max(hao, hac) and hal <= min(hao, hac), shape.__name__
        got = (m + hah + hal + m) / 4.0
        assert got == hac, (shape.__name__, got, hac)
        self.o.append(m)
        self.h.append(hah)
        self.l.append(hal)
        self.c.append(m)
        self.hao, self.hac = hao, got
        return self

    def times(self, shape, k, *args):
        for _ in range(k):
            self.add(shape, *args)
        return self

    def bars(self, upto=None):
        z = len(self.o) if upto is None else upto
        return (np.array(self.o[:z]), np.array(self.h[:z]), np.array(self.l[:z]), np.array(self.c[:z]))

    def run(self, upto=None, **kw):
        return O.heikin_ashi(*self.bars(upto), **kw)


# the shapes, as functions of the candle's haO = p (body, wicks and range in the comments)
def S(p, s=4.0):        # STRONG bull: body s, upper wick s, NO lower wick (rng 2s)
    return p + s, p + 2 * s, p


def Sd(p, s=4.0):       # STRONG bear: body s, lower wick s, no upper wick
    return p - s, p, p - 2 * s


def T(p, s=4.0):        # bull with both wicks s: rng 3s, body s = rng / 3 (not a doji), oppW s > 0.05 rng (not
    return p + s, p + 2 * s, p - s          # STRONG): WEAK if dir == dir[1] and s < body[1], else STEADY


def Td(p, s=4.0):       # the bear mirror of T
    return p - s, p + s, p - 2 * s


def D(p, e=1.0, w=4.0):     # bull doji: body e, both wicks w, rng e + 2w; e = 1, w = 4: 1 <= 0.25 * 9, 4 >= 0.9
    return p + e, p + e + w, p - w


def Dd(p, e=1.0, w=4.0):    # bear doji
    return p - e, p + w, p - e - w


def Z(p):               # a zero-range candle at haO: O = H = L = C = haO
    return p, p, p


def tie(p, w=4.0):      # haC == haO (body 0), both wicks w: a doji, bullish by the tie
    return p, p + w, p - w


def bull0():
    """Bar 0, a bull doji: O = C = 100, H = 102, L = 99: haO = 100, haC = 401 / 4 = 100.25, haH = 102, haL = 99; rng 3,
    body 0.25 <= 0.75, wicks 1.75 and 1 >= 0.3: INDECISION, bullish. The next haO is 100.125."""
    return HA(100.0, 102.0, 99.0, 100.0)


def bear0():
    """Bar 0, a bear doji: O = C = 100, H = 101, L = 98: haO = 100, haC = 399 / 4 = 99.75; rng 3, body 0.25, wicks 1 and
    1.75: INDECISION, bearish."""
    return HA(100.0, 101.0, 98.0, 100.0)


def rows(r):
    return [tuple(x) for x in r["streaks"].itertuples(index=False, name=None)]


def L(a):
    return np.asarray(a).tolist()


# ───────────────────────────── an independent formulation (numpy, bisect) ─────────────────────────────

def formulation(o, h, l, c, strong_tol=0.05, doji_max=0.25, ahead_n=5, rare_pct=90, min_streaks=50, keep=O.KEEP):
    """The same contract written another way: numpy for the candles, the phases and the flips; the streaks from the
    flips; ``pct_below`` from per-colour sorted lists (``bisect``) of the lengths known at each bar, with the cap."""
    o, h, l, c = (np.asarray(x, np.float64) for x in (o, h, l, c))
    n = len(o)
    hac = (o + h + l + c) / 4.0
    hao = np.empty(n)
    if n:
        hao[0] = (o[0] + c[0]) / 2.0
    for t in range(1, n):
        hao[t] = (hao[t - 1] + hac[t - 1]) / 2.0
    hah = np.maximum(h, np.maximum(hao, hac))
    hal = np.minimum(l, np.minimum(hao, hac))
    d = np.where(hac >= hao, 1, -1).astype(np.int8)
    rng = hah - hal
    body = np.abs(hac - hao)
    upw = hah - np.maximum(hao, hac)
    low = np.minimum(hao, hac) - hal
    opp = np.where(d == 1, low, upw)
    doji = (rng > 0) & (body <= doji_max * rng) & (np.minimum(upw, low) >= 0.1 * rng)
    strong = ~doji & (opp <= strong_tol * rng)
    weak = ~doji & ~strong & np.r_[False, d[1:] == d[:-1]] & np.r_[False, body[1:] < body[:-1]]
    phase = np.where(doji, 3, np.where(strong, 0, np.where(weak, 2, 1))).astype(np.int8)
    flip = np.r_[False, d[1:] != d[:-1]] if n else np.zeros(0, bool)
    starts = np.flatnonzero(np.r_[True, flip[1:]]) if n else np.zeros(0, np.int64)
    sid = np.cumsum(flip)
    age = (np.arange(n) - starts[sid] + 1).astype(np.int32) if n else np.zeros(0, np.int32)
    ss = np.r_[0, np.cumsum(strong)]
    in_streak = ss[1:] - ss[starts[sid]] if n else np.zeros(0, np.int64)     # STRONG candles of the streak so far
    first = strong & (in_streak == 1)
    srun = np.zeros(n, np.int32)
    wrun = np.zeros(n, np.int32)
    for t in range(n):
        new = t == 0 or flip[t]
        srun[t] = (1 if new else srun[t - 1] + 1) if strong[t] else 0
        wrun[t] = (1 if new else wrun[t - 1] + 1) if weak[t] else 0
    ev_ind = (phase == 3) & ~flip & np.r_[False, srun[:-1] >= 2] if n else np.zeros(0, bool)
    recs = []
    for k in range(len(starts) - 1):
        a, z = int(starts[k]), int(starts[k + 1]) - 1
        fs = np.flatnonzero(strong[a:z + 1])
        sat = int(fs[0]) + 1 if len(fs) else 0
        recs.append((a, z, int(d[a]), z - a + 1, bool(len(fs)), sat, bool(len(fs)) and (z - a + 1) - sat >= ahead_n))
    fifo = {1: deque(), -1: deque()}
    srt = {1: [], -1: []}
    done = {1: 0, -1: 0}                  # finished streaks of each colour, the cap's dropped ones included
    pct = np.full(n, np.nan)
    rare = np.zeros(n, bool)
    nxt = 0
    for t in range(n):
        if flip[t]:
            ln = recs[nxt][3]
            col = recs[nxt][2]
            nxt += 1
            fifo[col].append(ln)
            bisect.insort(srt[col], ln)
            done[col] += 1
            if keep is not None and len(fifo[col]) > keep:
                old = fifo[col].popleft()
                del srt[col][bisect.bisect_left(srt[col], old)]
        arr = srt[int(d[t])]
        m = len(arr)
        if m:
            pct[t] = 100.0 * bisect.bisect_left(arr, int(age[t])) / m
            prev = 100.0 * bisect.bisect_left(arr, int(age[t]) - 1) / m
            rare[t] = (done[int(d[t])] >= min_streaks and pct[t] >= rare_pct
                       and (age[t] == 1 or prev < rare_pct))
    frame = pd.DataFrame(recs, columns=list(O.STREAK_COLUMNS)).astype(O.STREAK_DTYPES)
    return {"ha_o": hao, "ha_h": hah, "ha_l": hal, "ha_c": hac, "dir": d, "phase": phase, "flip": flip, "age": age,
            "strong_run": srun, "weak_run": wrun, "ev_ind": ev_ind, "ev_first_strong": first, "pct_below": pct,
            "rare_now": rare, "streaks": frame}


def check_cross(r, o, h, l, c, **kw):
    want = formulation(o, h, l, c, **kw)
    for k in O.KEYS:
        assert same(r[k], want[k]), k
    pd.testing.assert_frame_equal(r["streaks"], want["streaks"])


def check_where_values_exist(r):
    """Every value the contract defines exists: the candles everywhere; ``pct_below`` from the bar of the second
    flip on (a finished streak of each colour exists), NaN before it, in [0, 100]."""
    n = len(r["ha_c"])
    for k in ("ha_o", "ha_h", "ha_l", "ha_c"):
        assert bool(np.all(np.isfinite(r[k]))), k
    assert bool(np.all(np.isin(r["dir"], (-1, 1)))) and bool(np.all(np.isin(r["phase"], (0, 1, 2, 3))))
    assert bool(np.all(r["age"] >= 1)) and bool(np.all(r["strong_run"] >= 0)) and bool(np.all(r["weak_run"] >= 0))
    assert bool(np.all(r["ha_h"] >= np.maximum(r["ha_o"], r["ha_c"])))
    assert bool(np.all(r["ha_l"] <= np.minimum(r["ha_o"], r["ha_c"])))
    fl = np.flatnonzero(r["flip"])
    second = int(fl[1]) if len(fl) > 1 else n
    p = r["pct_below"]
    assert bool(np.all(np.isnan(p[:second]))) and bool(np.all(np.isfinite(p[second:])))
    assert bool(np.all((p[second:] >= 0.0) & (p[second:] <= 100.0)))
    assert not bool(np.any(r["rare_now"][:second]))


def check_once_per_streak(r):
    sid = np.cumsum(r["flip"])
    ids = sid[r["rare_now"]]
    assert len(ids) == len(np.unique(ids))


# ───────────────────────────── 1. the traps (spec 4.6 "Risks") ─────────────────────────────

def test_trap_hao_start_value():
    # the spec's "Heikin Ashi values worked by hand for 4 bars" (4.6 test 1)
    o, h, l, c = [10.0, 13.0, 14.5, 11.5], [14.0, 15.0, 14.75, 11.75], [10.0, 12.5, 11.0, 9.0], [13.0, 14.5, 11.5, 9.5]
    r = O.heikin_ashi(o, h, l, c)
    # bar 0: haC = (10 + 14 + 10 + 13) / 4 = 11.75; haO = (10 + 13) / 2 = 11.5 (haO[1] is na: not open = 10, not
    #        (nz(haO[1]) + nz(haC[1])) / 2 = 0)
    # bar 1: haC = (13 + 15 + 12.5 + 14.5) / 4 = 13.75;   haO = (11.5 + 11.75) / 2 = 11.625
    # bar 2: haC = (14.5 + 14.75 + 11 + 11.5) / 4 = 12.9375; haO = (11.625 + 13.75) / 2 = 12.6875
    # bar 3: haC = (11.5 + 11.75 + 9 + 9.5) / 4 = 10.4375;  haO = (12.6875 + 12.9375) / 2 = 12.8125
    assert L(r["ha_c"]) == [11.75, 13.75, 12.9375, 10.4375]
    assert L(r["ha_o"]) == [11.5, 11.625, 12.6875, 12.8125]
    # haH = max(high, haO, haC); bar 3: the candle's open 12.8125 is above the bar's high 11.75
    assert L(r["ha_h"]) == [14.0, 15.0, 14.75, 12.8125]
    # haL = min(low, haO, haC); bar 1: the candle's open 11.625 is below the bar's low 12.5
    assert L(r["ha_l"]) == [10.0, 11.625, 11.0, 9.0]
    # bar 0: bull (11.75 >= 11.5), rng 4, body 0.25 <= 1, wicks 2.25 and 1.5 >= 0.4: INDECISION
    # bar 1: bull, rng 3.375, body 2.125 (not a doji), lower wick 0 <= 0.16875: STRONG (the streak's first, age 2)
    # bar 2: bull (12.9375 >= 12.6875), rng 3.75, body 0.25 <= 0.9375, wicks 1.8125 and 1.6875 >= 0.375: INDECISION;
    #        only 1 STRONG before it: no evInd
    # bar 3: bear: a flip; rng 3.8125, body 2.375, upper wick 0: STRONG, the new streak's first (age 1)
    assert L(r["dir"]) == [1, 1, 1, -1] and L(r["phase"]) == [3, 0, 3, 0]
    assert L(r["flip"]) == [F, F, F, T_] and L(r["age"]) == [1, 2, 3, 1] and L(r["strong_run"]) == [0, 1, 0, 1]
    assert L(r["ev_first_strong"]) == [F, T_, F, T_] and L(r["ev_ind"]) == [F, F, F, F]
    assert rows(r) == [(0, 2, 1, 3, True, 2, False)]
    assert bool(np.all(np.isnan(r["pct_below"])))      # no finished streak of the current colour yet

    # the seed is forgotten: a chart that starts at bar k has bit-identical candles after at most 64 bars
    for seed, p0, vol in ((1, 1500.0, 2.0), (2, 30000.0, 100.0)):
        o, h, l, c = walk(600, seed, p0, vol)
        full = O.heikin_ashi(o, h, l, c)
        for k in (1, 7, 50, 333):
            part = O.heikin_ashi(o[k:], h[k:], l[k:], c[k:])
            assert part["ha_o"][0] == (o[k] + c[k]) / 2.0 != full["ha_o"][k]
            eq = part["ha_o"] == full["ha_o"][k:]
            j = int(np.argmax(eq))
            assert eq[j] and 0 < j <= 64 and bool(np.all(eq[j:])), (seed, k, j)
            for key in ("ha_c", "ha_h", "ha_l", "dir"):
                assert same(part[key][j:], full[key][k + j:]), key
            assert same(part["phase"][j + 1:], full["phase"][k + j + 1:])      # phase also reads body[1]


def test_trap_tie_counts_bullish():
    # one bar with O + C = H + L: haO = (10 + 10) / 2 = 10 and haC = (10 + 11 + 9 + 10) / 4 = 10: a tie
    r = O.heikin_ashi([10.0], [11.0], [9.0], [10.0])
    assert r["ha_o"][0] == r["ha_c"][0] == 10.0
    assert r["dir"][0] == 1                       # haC >= haO (a strict > would give -1)
    assert r["phase"][0] == O.INDECISION          # body 0, rng 2, wicks 1 and 1 >= 0.2
    # after a bear streak a tie is a flip to bull: bear doji, STRONG bear, STRONG bear, then haC == haO
    b = bear0().add(Sd).add(Sd).add(tie)
    r = b.run()
    assert r["ha_c"][3] == r["ha_o"][3]
    assert L(r["dir"]) == [-1, -1, -1, 1] and L(r["flip"]) == [F, F, F, T_] and L(r["age"]) == [1, 2, 3, 1]
    assert L(r["phase"]) == [3, 0, 0, 3]
    assert rows(r) == [(0, 2, -1, 3, True, 2, False)]


def test_trap_phase_test_order():
    # (a) a doji whose body is smaller than the previous same-colour bar's: INDECISION, not WEAK (4.6 test 4)
    #     bar 1 T(4): bull, rng 12, body 4 > 3: STEADY. bar 2 D(1, 4): bull, rng 9, body 1 <= 2.25, wicks 4 >= 0.9:
    #     a doji; WEAK's test also holds there (dir == dir[1], 1 < 4)
    r = bull0().add(T, 4.0).add(D, 1.0, 4.0).run()
    assert L(r["phase"]) == [3, 1, 3] and L(r["weak_run"]) == [0, 0, 0]
    # (b) a STRONG candle with a smaller body than the previous same-colour bar's: STRONG, not WEAK
    #     bar 2 S(2): rng 4, body 2 < 4 (WEAK's test holds), lower wick 0 <= 0.2: STRONG
    r = bull0().add(T, 4.0).add(S, 2.0).run()
    assert L(r["phase"]) == [3, 1, 0] and L(r["strong_run"]) == [0, 0, 1]

    # (c) INDECISION before STRONG. A bull candle with body 1, upper wick 6, lower wick 1 (rng 8): a doji (1 <= 2, both
    #     wicks >= 0.8); its opposite wick 1 is <= strongTol * rng only for strongTol >= 0.125
    def both(p):
        return p + 1.0, p + 7.0, p - 1.0

    b = bull0().add(both)
    assert L(b.run()["phase"]) == [3, 3]                                   # 0.05: not STRONG anyway
    assert L(b.run(strong_tol=0.2)["phase"]) == [3, 3]                     # both tests hold: the doji test is first
    # with dojiMax 0.05 bar 1's body 1 > 0.4: no doji, so STRONG (oppW 1 <= 1.6); bar 0 (body 0.25 > 0.15, oppW 1 >
    # 0.6, and bar 0 cannot be WEAK) becomes STEADY
    assert L(b.run(strong_tol=0.2, doji_max=0.05)["phase"]) == [1, 0]
    # (d) WEAK before STEADY: bar 2 T(2) after T(4) of the same colour
    assert L(bull0().add(T, 4.0).add(T, 2.0).run()["phase"]) == [3, 1, 2]


def test_trap_zero_range_bar_is_strong():
    # O = H = L = C = 100: haO = 100 = haC, haH = haL = 100: rng 0, so isDoji fails (rng > 0), and oppW = 0 <= 0.05 * 0
    r = O.heikin_ashi([100.0], [100.0], [100.0], [100.0])
    assert r["phase"][0] == O.STRONG and r["dir"][0] == 1                  # STRONG, bullish by the tie
    assert r["ev_first_strong"][0] and r["strong_run"][0] == 1             # bar 0 starts the first streak
    # after a bear candle: bar 0 bear doji (haO 100, haC 99.75), so bar 1's haO is 99.875; a flat bar at 99.875 has zero
    # range: STRONG and bullish, a flip, and the new streak's first STRONG candle
    r = bear0().add(Z).run()
    assert r["ha_h"][1] == r["ha_l"][1] == 99.875
    assert L(r["dir"]) == [-1, 1] and L(r["flip"]) == [F, T_] and L(r["phase"]) == [3, 0]
    assert L(r["ev_first_strong"]) == [F, T_]
    # inside a bull streak a zero-range candle extends a STRONG run, and a doji after it is an evInd
    r = bull0().add(S).add(Z).add(D).run()
    assert L(r["phase"]) == [3, 0, 0, 3] and L(r["strong_run"]) == [0, 1, 2, 0] and L(r["ev_ind"]) == [F, F, F, T_]


def test_trap_weak_compares_with_previous_body():
    # body[1] is the previous bar's body, whatever that bar's phase; the test is strict; a flip bar is never WEAK
    b = bull0().add(S, 4.0)          # bar 1: STRONG, body 4
    b.add(T, 3.0)                    # bar 2: 3 < 4 (the previous bar is STRONG): WEAK
    b.add(T, 2.0)                    # bar 3: 2 < 3: WEAK
    b.add(T, 2.5)                    # bar 4: 2.5 > 2 (though < 4: only body[1] counts): STEADY
    b.add(T, 2.5)                    # bar 5: 2.5 == 2.5, not <: STEADY
    b.add(D, 1.0, 4.0)               # bar 6: a doji: INDECISION
    b.add(T, 0.5)                    # bar 7: rng 1.5, body 0.5 > 0.375, oppW 0.5; 0.5 < 1 (a doji before it): WEAK
    b.add(Td, 0.25)                  # bar 8: bear, a flip: 0.25 < 0.5 but dir != dir[1]: STEADY
    r = b.run()
    assert L(r["dir"]) == [1] * 8 + [-1]
    assert L(r["phase"]) == [3, 0, 2, 2, 1, 1, 3, 2, 1]
    assert L(r["weak_run"]) == [0, 0, 1, 2, 0, 0, 0, 1, 0]
    # bar 0 cannot be WEAK (dir[1] and body[1] are na): O = C = 100, H = 110, L = 99: haC = 102.25, rng 11, body 2.25,
    # lower wick 1 < 1.1 (no doji), oppW 1 > 0.55 (not STRONG): STEADY
    r = O.heikin_ashi([100.0], [110.0], [99.0], [100.0])
    assert r["ha_c"][0] == 102.25 and r["phase"][0] == O.STEADY


def test_trap_strong_run_reset_at_flip_before_ev_ind():
    # (4.6 test 5) STRONG, STRONG, INDECISION gives evInd
    r = bull0().add(S).add(S).add(D).run()
    assert L(r["strong_run"]) == [0, 1, 2, 0] and L(r["ev_ind"]) == [F, F, F, T_]
    # STRONG, STEADY, INDECISION does not (T(4) after S(4): body 4 == 4, so STEADY, and strongRun drops to 0)
    r = bull0().add(S).add(T).add(D).run()
    assert L(r["phase"]) == [3, 0, 1, 3] and L(r["ev_ind"]) == [F, F, F, F]
    # neither does an opposite-colour doji: it is a flip, and l.147 resets strongRun to 0 before l.156 reads it
    r = bull0().add(S).add(S).add(Dd).run()
    assert L(r["flip"]) == [F, F, F, T_] and r["phase"][3] == O.INDECISION
    assert r["strong_run"][2] == 2 and L(r["ev_ind"]) == [F, F, F, F]
    # 3 STRONG, then two dojis: only the first (the first resets the run)
    r = bull0().add(S).add(S).add(S).add(D).add(D).run()
    assert L(r["strong_run"]) == [0, 1, 2, 3, 0, 0] and L(r["ev_ind"]) == [F, F, F, F, T_, F]
    # a STRONG run of the previous streak never counts: bear STRONG x2, then a STRONG bull flip bar (run reset, then 1),
    # a doji (run 1 < 2: no), STRONG x2 and a doji (yes)
    r = bear0().add(Sd).add(Sd).add(S).add(D).add(S).add(S).add(D).run()
    assert L(r["strong_run"]) == [0, 1, 2, 1, 0, 1, 2, 0]
    assert L(r["ev_ind"]) == [F, F, F, F, F, F, F, T_]


def test_trap_first_strong_on_flip_bar():
    # (4.6 test 6) a STRONG flip bar gives evFirstSt at age 1: strongAt was reset at l.146, before l.158
    b = bull0()                       # bar 0: bull doji, age 1
    b.add(S)                          # bar 1: the bull streak's first STRONG candle, age 2
    b.add(S)                          # bar 2: STRONG again: no event
    b.add(Sd)                         # bar 3: bear flip, STRONG: the new streak's first, age 1
    b.add(Sd)                         # bar 4: no event
    b.add(T)                          # bar 5: bull flip, STEADY
    b.add(T)                          # bar 6: STEADY (equal body)
    b.add(S)                          # bar 7: the bull streak's first STRONG candle, age 3
    r = b.run()
    assert L(r["age"]) == [1, 2, 3, 1, 2, 1, 2, 3]
    assert L(r["ev_first_strong"]) == [F, T_, F, T_, F, F, F, T_]
    assert rows(r) == [(0, 2, 1, 3, True, 2, False), (3, 4, -1, 2, True, 1, False)]


def test_trap_streak_lengths_pushed_at_flip():
    # streaks: bull 3 (bars 0-2), bear 2 (3-4), bull 1 (5), bear 4 (6-9, a STRONG at age 3), bull (10-13, running)
    b = bull0().times(T, 2).times(Td, 2).add(T).add(Td).add(Td).add(Sd).add(Td).times(T, 4)
    r = b.run()
    assert L(np.flatnonzero(r["flip"])) == [3, 5, 6, 10]
    assert L(r["age"]) == [1, 2, 3, 1, 2, 1, 1, 2, 3, 4, 1, 2, 3, 4]
    # each length is `age` before the reset, pushed at the flip bar into the FINISHED streak's colour
    assert rows(r) == [(0, 2, 1, 3, False, 0, False), (3, 4, -1, 2, False, 0, False), (5, 5, 1, 1, False, 0, False),
                       (6, 9, -1, 4, True, 3, False)]
    # pct_below at bar t uses the current colour's array at t's close:
    #   bars 0-4: no finished streak of the current colour: na
    #   bar 5 (bull, age 1): bull [3]: 0 of 1 below 1 -> 0
    #   bars 6-9 (bear, ages 1-4): bear [2] (the bear streak 3-4, pushed at bar 5): 0, 0 (2 < 2 is false), 100, 100
    #   bars 10-13 (bull, ages 1-4): bull [3, 1]: 0, 50, 50, 100
    want = [math.nan] * 5 + [0.0, 0.0, 0.0, 100.0, 100.0, 0.0, 50.0, 50.0, 100.0]
    assert same(r["pct_below"], np.array(want))
    # a streak is known only at its flip bar's close: the run that ends at bar 2 has no row, the run to bar 3 has it
    assert rows(b.run(upto=3)) == [] and rows(b.run(upto=4)) == [(0, 2, 1, 3, False, 0, False)]
    # the arrays as the script holds them at a bar's close
    assert O.lengths_known_at(r["streaks"], 1, 9) == [3, 1] and O.lengths_known_at(r["streaks"], -1, 9) == [2]
    assert O.lengths_known_at(r["streaks"], -1, 10) == [2, 4] and O.lengths_known_at(r["streaks"], -1, 4) == []


def rare_bars():
    """Bull streaks of lengths 1, 2, ..., 10, each followed by a bear streak of length 1, then a bull streak of 12.
    Bull streak k starts at bar (k - 1)(k + 2) / 2 and ends at that + k - 1; the last one covers bars 65-76."""
    b = bull0()                                       # bar 0: the bull streak of length 1
    b.add(Td)
    for k in range(2, 11):
        b.times(T, k).add(Td)
    b.times(T, 12)
    return b


def test_trap_rare_now_computed_causally():
    b = rare_bars()
    r = b.run(min_streaks=10)
    assert len(r["ha_c"]) == 77
    st = r["streaks"]
    assert L(st[st["dir"] == 1]["length"]) == list(range(1, 11)) and L(st[st["dir"] == -1]["length"]) == [1] * 10
    # in the last bull streak (bars 65-76, ages 1-12) the bull array is [1, ..., 10] (n = 10): pct(a) = 100 (a - 1) / 10
    # up to a = 11, then 100
    assert L(r["pct_below"][65:]) == [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 100.0]
    # rareNow (l.212): pNow >= 90 while pPrev = pct(age - 1) < 90: age 10 only (bar 74); ages 11 and 12 have pPrev >= 90
    assert L(np.flatnonzero(r["rare_now"])) == [74]
    assert L(np.flatnonzero(b.run(min_streaks=10, rare_pct=80)["rare_now"])) == [73]    # pct(9) = 80, pct(8) = 70
    # the PREREG's minimum of finished streaks of that colour: bull streak k has n = k - 1 of them, and its last bar
    # (age k) is a crossing (pct(k) = 100, pct(k - 1) = 100 (k - 2) / (k - 1) < 90 for k <= 10)
    assert L(np.flatnonzero(b.run(min_streaks=1)["rare_now"])) == [3, 7, 12, 18, 25, 33, 42, 52, 63, 74]
    assert L(np.flatnonzero(b.run(min_streaks=9)["rare_now"])) == [63, 74]
    assert L(np.flatnonzero(b.run(min_streaks=11)["rare_now"])) == []
    assert not bool(b.run()["rare_now"].any())                # the default 50: never on this chart
    # causal: rare_now at bar t is what the script computes when bar t is the chart's LAST bar (barstate.islast). The
    # script itself, run on all 77 bars, computes it on bar 76 only (age 12: false) and is false on every other bar
    for t in range(77):
        last = b.run(upto=t + 1, min_streaks=1)
        assert bool(last["rare_now"][-1]) == bool(b.run(min_streaks=1)["rare_now"][t]), t
    # the bear streaks all have length 1: pct(1) = 0 < 90, never rare
    assert not bool((r["rare_now"] & (r["dir"] == -1)).any())


# ───────────────────────────── 2. the spec's other cases and the module's choices ─────────────────────────────

def test_cap_keeps_the_last_5000():
    """Reading 9: each colour's array keeps its 5000 most recent lengths (l.131-132), shown here with a cap of 3. Bull
    streaks 9, 1, 1, 1 (bear streaks of 1 between), then a fifth bull streak: at its age 2 the capped array is [1, 1, 1]
    (100 below 2) and the full one [9, 1, 1, 1] (75)."""
    b = bull0().times(T, 8).add(Td)
    for _ in range(3):
        b.add(T).add(Td)
    b.times(T, 3)
    o, h, l, c = b.bars()
    cap3 = O._transcribe(o, h, l, c, keep=3)
    full = O._transcribe(o, h, l, c, keep=None)
    r = O.heikin_ashi(o, h, l, c)
    t = len(o) - 2                                    # age 2 of the last bull streak
    assert r["age"][t] == 2 and r["dir"][t] == 1
    assert cap3["pct_below"][t] == 100.0 and full["pct_below"][t] == 75.0 and r["pct_below"][t] == 75.0
    pd.testing.assert_frame_equal(cap3["streaks"], full["streaks"])          # the frame lists every streak
    assert O.lengths_known_at(r["streaks"], 1, t, keep=3) == [1, 1, 1]
    assert O.KEEP == 5000
    for k in O.KEYS:
        assert same(r[k], O._transcribe(o, h, l, c, keep=5000)[k]), k
    # reading 11: the minimum counts every FINISHED streak of the colour, also those the cap dropped. Four bull
    # streaks have finished at bar t (9, 1, 1, 1; the cap of 3 keeps [1, 1, 1]): at age 2 the capped percentage
    # reaches 100 from 0 at age 1, a crossing; four streaks meet a minimum of 4 though the array holds 3 (before the
    # reconciliation this port counted the array and said no), not a minimum of 5. Without the cap it is 75: none.
    assert L(np.flatnonzero(O._transcribe(o, h, l, c, min_streaks=4, keep=3)["rare_now"])) == [t]
    assert not bool(O._transcribe(o, h, l, c, min_streaks=5, keep=3)["rare_now"].any())
    assert not bool(O._transcribe(o, h, l, c, min_streaks=4, keep=None)["rare_now"].any())
    check_cross(O._transcribe(o, h, l, c, min_streaks=4, keep=3), o, h, l, c, min_streaks=4, keep=3)


def test_survive_and_sk_sn_on_hand_made_streaks():
    # (4.6 test 8) survive (l.176-184): reached A = x >= A; went X more = x >= A + X
    assert O.survive([1, 2, 3, 5, 8, 13], 3, 5) == (4, 2)          # 3, 5, 8, 13 reached 3; 8 and 13 reached 8
    assert O.survive([5, 10], 5, 5) == (2, 1) and O.survive([], 1, 5) == (0, 0)
    assert O.survive([1, 1, 2], 4, 5) == (0, 0)
    # SN / SK (l.133-139): bear doji (bar 0); bull A: STRONG at age 1, length 7 (7 - 1 = 6 >= 5: SK); a bear of 1;
    # bull B: STRONG at age 3, length 7 (4 < 5); a bear of 1; bull C: no STRONG, length 3; then a bear streak that
    # ends C
    b = bear0().add(S).times(T, 6).add(Td).times(T, 2).add(S).times(T, 4).add(Td).times(T, 3).add(Td)
    r = b.run()
    assert rows(r) == [(0, 0, -1, 1, False, 0, False), (1, 7, 1, 7, True, 1, True), (8, 8, -1, 1, False, 0, False),
                       (9, 15, 1, 7, True, 3, False), (16, 16, -1, 1, False, 0, False), (17, 19, 1, 3, False, 0, False)]
    assert O.strong_continuation(r["streaks"], 1) == (2, 1) and O.strong_continuation(r["streaks"], -1) == (0, 0)
    assert O.strong_continuation(r["streaks"], 1, upto_flip_bar=8) == (1, 1)      # B is known at bar 16
    assert O.strong_continuation(b.run(ahead_n=4)["streaks"], 1) == (2, 2)       # B: 4 >= 4
    assert O.strong_continuation(b.run(ahead_n=7)["streaks"], 1) == (2, 0)       # A: 6 < 7
    assert O.survive(O.lengths_known_at(r["streaks"], 1, 20), 3, 5) == (3, 0)    # [7, 7, 3]: none reached 8


def test_weak_run_counts_consecutive_weak_candles():
    # PREREG M3's "2 consecutive WEAK candles": bodies 4 (STRONG), 3, 2, 1 (WEAK x3), 1.5 (STEADY), 1 (WEAK)
    r = bull0().add(S, 4.0).add(T, 3.0).add(T, 2.0).add(T, 1.0).add(T, 1.5).add(T, 1.0).run()
    assert L(r["phase"]) == [3, 0, 2, 2, 2, 1, 2] and L(r["weak_run"]) == [0, 0, 1, 2, 3, 0, 1]


def test_contract_keys_dtypes_and_signature():
    sig = inspect.signature(O.heikin_ashi)
    assert list(sig.parameters) == ["o", "h", "l", "c", "strong_tol", "doji_max", "ahead_n", "rare_pct", "min_streaks"]
    assert [sig.parameters[k].default for k in ("strong_tol", "doji_max", "ahead_n", "rare_pct", "min_streaks")] == \
        [0.05, 0.25, 5, 90, 50]
    o, h, l, c = walk(400, 3)
    r = O.heikin_ashi(o, h, l, c)
    assert list(r) == list(O.KEYS) + ["streaks"]
    want = {"ha_o": "float64", "ha_h": "float64", "ha_l": "float64", "ha_c": "float64", "dir": "int8", "phase": "int8",
            "flip": "bool", "age": "int32", "strong_run": "int32", "weak_run": "int32", "ev_ind": "bool",
            "ev_first_strong": "bool", "pct_below": "float64", "rare_now": "bool"}
    for k, dt in want.items():
        assert r[k].dtype == np.dtype(dt) and r[k].shape == (400,), k
    st = r["streaks"]
    assert list(st.columns) == list(O.STREAK_COLUMNS)
    assert [str(st[k].dtype) for k in O.STREAK_COLUMNS] == ["int64", "int64", "int8", "int32", "bool", "int32", "bool"]
    assert len(st) == int(r["flip"].sum())
    e = O.heikin_ashi([], [], [], [])
    assert all(e[k].shape == (0,) and e[k].dtype == np.dtype(want[k]) for k in O.KEYS)
    assert list(e["streaks"].columns) == list(O.STREAK_COLUMNS) and len(e["streaks"]) == 0
    assert [str(e["streaks"][k].dtype) for k in O.STREAK_COLUMNS] == [str(st[k].dtype) for k in O.STREAK_COLUMNS]


def test_inputs_refused_and_left_alone():
    o, h, l, c = walk(50, 4)
    keep = [x.copy() for x in (o, h, l, c)]
    O.heikin_ashi(o, h, l, c)
    assert all(same(a, b) for a, b in zip((o, h, l, c), keep))
    bad = c.copy()
    bad[7] = np.nan
    for args in ((o, h, l, bad), (o, h, l, np.r_[c[:-1], np.inf]), (o, h, l, c[:-1]), (o[None, :], h, l, c)):
        with pytest.raises(ValueError):
            O.heikin_ashi(*args)
    for kw in ({"strong_tol": -0.01}, {"strong_tol": 0.31}, {"doji_max": 0.04}, {"doji_max": 0.51},
               {"ahead_n": 0}, {"ahead_n": 51}, {"ahead_n": 2.5}, {"rare_pct": 49}, {"rare_pct": 100},
               {"rare_pct": 90.5}, {"min_streaks": -1}, {"rare_pct": True}, {"ahead_n": math.inf},
               {"rare_pct": -math.inf}, {"min_streaks": math.inf}, {"min_streaks": math.nan}):
        with pytest.raises(ValueError):
            O.heikin_ashi(o, h, l, c, **kw)
    # integral numbers and lists are accepted
    a = O.heikin_ashi(o.tolist(), h.tolist(), l.tolist(), c.tolist(), ahead_n=5.0, rare_pct=np.int64(90))
    b = O.heikin_ashi(o, h, l, c)
    assert all(same(a[k], b[k]) for k in O.KEYS)


def test_formulation_agrees_on_synthetic_bars():
    for seed, p0, vol in ((5, 1500.0, 2.0), (6, 30000.0, 100.0), (7, 50.0, 0.3)):
        o, h, l, c = walk(2500, seed, p0, vol)
        r = O.heikin_ashi(o, h, l, c)
        check_where_values_exist(r)
        check_once_per_streak(r)
        check_cross(r, o, h, l, c)
        assert int(r["rare_now"].sum()) > 0 and int(r["ev_ind"].sum()) > 0 and int((r["weak_run"] >= 2).sum()) > 0
        kw = dict(strong_tol=0.2, doji_max=0.3, ahead_n=3, rare_pct=75, min_streaks=5)
        check_cross(O.heikin_ashi(o, h, l, c, **kw), o, h, l, c, **kw)
        k3 = O._transcribe(o, h, l, c, keep=40)
        check_cross(k3, o, h, l, c, keep=40)


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed, p0, vol", [(8, 1500.0, 2.0), (9, 30000.0, 100.0)])
def test_truncation_invariance(seed, p0, vol):
    o, h, l, c = walk(1500, seed, p0, vol)
    full = O.heikin_ashi(o, h, l, c)
    fl = np.flatnonzero(full["flip"]).tolist()
    rare = np.flatnonzero(full["rare_now"]).tolist()
    assert len(rare) >= 3
    cuts = sorted({0, 1, 2, 60, 700, 1499} | set(fl[:3]) | {f - 1 for f in fl[:3]} | set(fl[200:203])
                  | set(rare[:3]) | {x - 1 for x in rare[:3]})
    st = full["streaks"]
    for t in cuts:
        part = O.heikin_ashi(o[:t + 1], h[:t + 1], l[:t + 1], c[:t + 1])
        for k in O.KEYS:
            assert same(part[k], full[k][:t + 1]), (t, k)
        known = st[st["end_bar"] + 1 <= t].reset_index(drop=True)          # rows known at bar t's close
        pd.testing.assert_frame_equal(part["streaks"], known)


# ───────────────────────────── 4. the real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H / 1D bars of one symbol from its data start to 2024-07-01 00:00 UTC (exclusive), with study
    1's hold-out guard pointed at an empty folder; only the arrays the script reads are kept (OHLC, no volume)."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            cache.clear()                                    # one symbol in memory at a time
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end=TM.HOLDOUT_START)
                bars = {}
                for tf in ("1H", "4H", "1D"):
                    b = mk.tbars(tf)
                    bars[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(),
                                  c=b.c.copy(), complete=b.complete.copy())
            del mk
            cache[symbol] = bars
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    rows_ = real(symbol)
    dev_a, dev_z = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")
    cut = TM.s_of("2021-06-15 12:00")
    for tf, b in rows_.items():
        assert int(b.tc[-1]) <= TM.CUT_S and bool(b.complete.all()), tf              # nothing from the hold-out
        r = O.heikin_ashi(b.o, b.h, b.l, b.c)
        check_where_values_exist(r)
        check_once_per_streak(r)
        check_cross(r, b.o, b.h, b.l, b.c)
        dev = (b.tc >= dev_a) & (b.tc < dev_z)                                       # bars closing in 2019-2022
        for k, least in (("flip", 200), ("ev_first_strong", 100), ("ev_ind", 20), ("rare_now", 10)):
            assert int(r[k][dev].sum()) >= least, (tf, k, int(r[k][dev].sum()))
        assert bool(np.isfinite(r["pct_below"][b.tc >= dev_a]).all()), tf           # warmed up before 2019
        i = int(np.searchsorted(b.tc, cut, side="right")) - 1                         # a cut at one T
        part = O.heikin_ashi(b.o[:i + 1], b.h[:i + 1], b.l[:i + 1], b.c[:i + 1])
        for k in O.KEYS:
            assert same(part[k], r[k][:i + 1]), (tf, k)
        st = r["streaks"]
        pd.testing.assert_frame_equal(part["streaks"], st[st["end_bar"] + 1 <= i].reset_index(drop=True))
