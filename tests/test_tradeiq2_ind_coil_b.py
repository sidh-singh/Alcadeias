"""
Port B (the oracle) of the coil breakout, ``tests/tradeiq2_oracle_coil.py`` (study 2, PREREG 6.9; the rule is the
study's own: TradeIQ's Coil Breakout AI is private and has no source).

1. One hand-computed test per trap, named after it. The spec is PREREG 6.9 with the contract of the two ports; it has
   no porting-risks section of its own, so the traps are the contract's edge cases (a run of exactly 5 and of 6, a
   breakout on the 12th and on the 13th armed bar, a newer coil replacing an armed one, a close exactly at box_hi)
   and the Pine details the rule rests on (strict bands, population stdev, Wilder ATR(20) with its first true range,
   the warm-up, the DMI's +DM / -DM rule, its na first bar, its smoothing, its DX guard, fixnan) and the readings of
   the oracle's docstring (the box over the whole run, armed from the first bar after the run, the close not the
   wick, once per coil, a shorter newer run, the replacement bar, the breakout bar, a run open at the last bar).
   Each builds bars by hand and states the expected values with their arithmetic.
2. An independent formulation (numpy for the lines; the coil from the runs of the squeeze series, not bar by bar)
   agrees bit for bit on synthetic bars and on random squeeze series that exercise every path; the primitives equal
   study 1's verified Pine oracle (``tests/tradeiq_oracle.py``) bit for bit; the contract; the inputs.
3. Truncation invariance: the outputs up to bar T are unchanged when the bars after T are removed.
4. Real bars (skipped when the tick store is absent): both symbols, the 1H / 4H / 1D bars PREREG 6.9 uses, from the
   data start to 2024-06-30 (study 1's guard pointed at an empty folder, so the hold-out cannot be served): it runs,
   every value the contract defines exists and nothing else does, the formulation and study 1's primitives agree bit
   for bit, events exist in 2019-2022, and a cut at one T changes nothing before it.

Port A (``backtesting/research/tradeiq2_ind_coil.py``) was not read or imported; the two are compared later.
"""

from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_coil as O  # noqa: E402
import tradeiq_oracle as S1  # noqa: E402  (study 1's verified Pine oracle, read-only)

NAN = float("nan")


# ───────────────────────────── helpers ─────────────────────────────

def same(a, b) -> bool:
    """Bit-for-bit equality, NaN equal to NaN, dtypes equal."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        return bool(np.array_equal(a.view(np.int64), b.view(np.int64)) or np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def L(a):
    return np.asarray(a).tolist()


def nan_list(a):
    """A float array as a list with None for NaN (for readable expected lists)."""
    return [None if (x != x) else x for x in np.asarray(a, dtype=float).tolist()]


class Tape:
    """Hand-made input of ``coil_from_squeeze``: squeeze flags with each bar's high, low and close."""

    def __init__(self):
        self.sq, self.h, self.l, self.c = [], [], [], []

    def add(self, sq, h, l, c):
        self.sq.append(bool(sq))
        self.h.append(float(h))
        self.l.append(float(l))
        self.c.append(float(c))
        return self

    def quiet(self, k, hi=101.0, lo=99.0, close=100.0):
        """k squeeze bars, each with this high, low and close (the box of a run of them is [lo, hi])."""
        for _ in range(k):
            self.add(True, hi, lo, close)
        return self

    def bar(self, close, sq=False, hi=None, lo=None):
        """One bar at ``close`` (a dot bar: high = low = close unless given)."""
        return self.add(sq, close if hi is None else hi, close if lo is None else lo, close)

    def bars(self, k, close, sq=False):
        for _ in range(k):
            self.bar(close, sq)
        return self

    def run(self, **kw):
        return O.coil_from_squeeze(np.array(self.sq), np.array(self.h), np.array(self.l), np.array(self.c), **kw)


class Bars:
    """Hand-made OHLC bars for the full ``coil``: ``flat(p)`` is O = H = L = C = p, ``wick(p, up, dn)`` is O = C = p
    with H = p + up, L = p - dn."""

    def __init__(self):
        self.o, self.h, self.l, self.c = [], [], [], []

    def add(self, o, h, l, c):
        for a, v in zip((self.o, self.h, self.l, self.c), (o, h, l, c)):
            a.append(float(v))
        return self

    def flat(self, p, k=1):
        for _ in range(k):
            self.add(p, p, p, p)
        return self

    def wick(self, p, up, dn=None):
        return self.add(p, p + up, p - (up if dn is None else dn), p)

    def arrays(self):
        return tuple(np.array(x) for x in (self.o, self.h, self.l, self.c))

    def coil(self, **kw):
        return O.coil(*self.arrays(), **kw)

    def lines(self, **kw):
        o, h, l, c = self.arrays()
        return O.squeeze_lines(h, l, c, **kw)


def quiet_start(k_run):
    """The workhorse of the end-to-end cases (squeeze states verified in the tests' comments):

    - bars 0-19 flat at 100: the bands exist from bar 19, where basis = 100 exactly (20 x 100/20), sd = 0 and ATR(20)
      = the mean of 20 true ranges of 0 = 0, so the bands equal the channel: no squeeze (strict);
    - bar 20: O = C = 100, H = 110, L = 90: TR = 20, ATR = 20/20 + 0.95 x 0 = 1.0, sd = 0: squeeze (channel +-1.5);
    - bars 21 .. 19 + k_run: flat at 100: TR = 0, ATR = 0.95^m > 0, sd = 0: squeeze. The run is bars 20 .. 19 + k_run,
      its box [90, 110] (bar 20's wick)."""
    return Bars().flat(100.0, 20).wick(100.0, 10.0).flat(100.0, k_run - 1)


# ───────────────────────────── the independent formulation ─────────────────────────────

def shift(x, i):
    x = np.asarray(x, np.float64)
    if i == 0:
        return x.copy()
    out = np.full(x.size, np.nan)
    if x.size > i:
        out[i:] = x[:-i]
    return out


def f_sma(x, n):
    s = np.zeros(len(x))
    for i in range(n):                                   # pine_sma's order: x[0] / n first
        s = s + shift(x, i) / n
    return s


def f_stdev(x, n):
    avg = f_sma(x, n)
    ss = np.zeros(len(x))
    with np.errstate(invalid="ignore"):
        for i in range(n):
            d = shift(x, i) + (-avg)
            d = np.where(np.abs(d) <= 1e-10, 0.0, d)
            ss = ss + d * d
    return np.sqrt(ss / n)


def f_rma(x, n):
    seed = f_sma(x, n)
    out = np.full(len(x), np.nan)
    a = 1 / n
    v = np.nan
    for t in range(len(x)):
        v = seed[t] if np.isnan(v) else a * x[t] + (1 - a) * v
        out[t] = v
    return out


def f_tr(h, l, c, handle_na):
    pc = shift(c, 1)
    with np.errstate(invalid="ignore"):
        tr = np.maximum(np.maximum(h - l, np.abs(h - pc)), np.abs(l - pc))
    if len(tr):
        tr[0] = (h[0] - l[0]) if handle_na else np.nan
    return tr


def f_squeeze(h, l, c, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5):
    basis, dev = f_sma(c, bb_len), bb_mult * f_stdev(c, bb_len)
    ma, atr = f_sma(c, kc_len), f_rma(f_tr(h, l, c, True), kc_len)
    with np.errstate(invalid="ignore"):
        sq = (basis + dev < ma + kc_mult * atr) & (basis - dev > ma - kc_mult * atr)
    return sq, dict(basis=basis, dev=dev, ma=ma, atr=atr)


def f_states(sq, h, l, c, min_bars=6, armed_bars=12):
    """The coil from the RUNS of the squeeze series (no bar-by-bar state): each run of >= min_bars bars that ends
    before the last bar is armed from the bar after its end for armed_bars bars, cut before the bar on which the next
    such run reaches min_bars, and up to its first close beyond the box."""
    sq = np.asarray(sq, bool)
    h, l, c = (np.asarray(x, np.float64) for x in (h, l, c))
    n = len(c)
    idx = np.arange(n)
    start = sq & ~np.r_[False, sq[:-1]]
    end = sq & ~np.r_[sq[1:], False]
    last_start = np.maximum.accumulate(np.where(start, idx, -1)) if n else idx
    run_len = np.where(sq, idx - last_start + 1, 0).astype(np.int64)
    coils = [(s, e) for s, e in zip(np.flatnonzero(start), np.flatnonzero(end)) if e - s + 1 >= min_bars]
    armed = np.zeros(n, bool)
    bo = np.zeros(n, np.int8)
    box_hi, box_lo = np.full(n, np.nan), np.full(n, np.nan)
    for k, (s, e) in enumerate(coils):
        if e == n - 1:
            continue                                       # the run is still open at the last bar: never armed
        hi, lo = h[s:e + 1].max(), l[s:e + 1].min()
        first, last = e + 1, min(e + armed_bars, n - 1)
        if k + 1 < len(coils):
            last = min(last, coils[k + 1][0] + min_bars - 2)   # the next coil reaches min_bars on start + min_bars - 1
        win = np.arange(first, last + 1)
        hit = win[(c[win] > hi) | (c[win] < lo)]
        if len(hit):
            last = int(hit[0])
            bo[last] = 1 if c[last] > hi else -1
        armed[first:last + 1] = True
        box_hi[first:last + 1], box_lo[first:last + 1] = hi, lo
    nz = bo != 0
    return dict(squeeze_on=sq.copy(), run_len=run_len, armed=armed, box_hi=box_hi, box_lo=box_lo, breakout=bo,
                bo_box_hi=np.where(nz, box_hi, np.nan), bo_box_lo=np.where(nz, box_lo, np.nan))


def f_dmi(h, l, c, di_len=14, adx_len=14):
    h, l, c = (np.asarray(x, np.float64) for x in (h, l, c))
    up = h - shift(h, 1)
    down = -(l - shift(l, 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        pdm = np.where(np.isnan(up), np.nan, np.where((up > down) & (up > 0), up, 0.0))
        mdm = np.where(np.isnan(down), np.nan, np.where((down > up) & (down > 0), down, 0.0))
        trur = f_rma(f_tr(h, l, c, False), di_len)
        plus = pd.Series(100 * f_rma(pdm, di_len) / trur).ffill().to_numpy()      # fixnan
        minus = pd.Series(100 * f_rma(mdm, di_len) / trur).ffill().to_numpy()
        s = plus + minus
        dx = np.abs(plus - minus) / np.where(s == 0, 1.0, s)
    return plus, minus, 100 * f_rma(dx, adx_len)


def formulation(o, h, l, c, **kw):
    h, l, c = (np.asarray(x, np.float64) for x in (h, l, c))
    sq_kw = {k: kw[k] for k in ("bb_len", "bb_mult", "kc_len", "kc_mult") if k in kw}
    st_kw = {k: kw[k] for k in ("min_bars", "armed_bars") if k in kw}
    sq, _ = f_squeeze(h, l, c, **sq_kw)
    r = f_states(sq, h, l, c, **st_kw)
    r["adx"] = f_dmi(h, l, c)[2]
    return r


# ───────────────────────────── generic checks ─────────────────────────────

def segments(r):
    """The armed segments [a, z] (consecutive armed bars of one coil)."""
    armed, bo = r["armed"], r["breakout"]
    out, t, n = [], 0, len(armed)
    while t < n:
        if armed[t]:
            a = z = t
            while (z + 1 < n and armed[z + 1] and bo[z] == 0 and r["box_hi"][z + 1] == r["box_hi"][a]
                   and r["box_lo"][z + 1] == r["box_lo"][a]):
                z += 1
            out.append((a, z))
            t = z + 1
        else:
            t += 1
    return out


def check_where_values_exist(r, c, min_bars=6, armed_bars=12, adx_from=27):
    """Every value the contract defines exists, and nothing else does; the events obey the rule."""
    n = len(c)
    assert tuple(r) == O.KEYS
    for k in O.KEYS:
        assert r[k].dtype == O.DTYPES[k] and r[k].shape == (n,), k
    sq, rl, armed, bo = r["squeeze_on"], r["run_len"], r["armed"], r["breakout"]
    assert np.array_equal(rl == 0, ~sq)
    prev = np.r_[0, rl[:-1]]
    assert np.array_equal(rl[sq], prev[sq] + 1)                       # consecutive squeeze bars
    for k in ("box_hi", "box_lo"):
        assert bool(np.isfinite(r[k][armed]).all()) and bool(np.isnan(r[k][~armed]).all()), k
    assert bool((r["box_hi"][armed] >= r["box_lo"][armed]).all())
    nz = bo != 0
    assert bool(armed[nz].all())                                       # a breakout happens while armed
    for k, b in (("bo_box_hi", "box_hi"), ("bo_box_lo", "box_lo")):
        assert bool(np.isnan(r[k][~nz]).all()) and same(r[k][nz], r[b][nz]), k
    assert bool((c[bo == 1] > r["box_hi"][bo == 1]).all()) and bool((c[bo == -1] < r["box_lo"][bo == -1]).all())
    inside = armed & ~nz
    assert bool(((c[inside] <= r["box_hi"][inside]) & (c[inside] >= r["box_lo"][inside])).all())  # none missed
    assert not bool((armed & (rl >= min_bars)).any())                 # a coil of min_bars replaces / is not armed yet
    for a, z in segments(r):
        assert z - a + 1 <= armed_bars and int((bo[a:z + 1] != 0).sum()) <= 1 and bool((bo[a:z] == 0).all())
        # every armed stretch starts on the first non-squeeze bar after a run of at least min_bars bars
        assert a >= 1 and bool(sq[a - 1]) and int(rl[a - 1]) >= min_bars and not bool(sq[a]), (a, z)
    if adx_from is not None:
        assert bool(np.isnan(r["adx"][:adx_from]).all()) and bool(np.isfinite(r["adx"][adx_from:]).all())
        assert bool(((r["adx"][adx_from:] >= 0) & (r["adx"][adx_from:] <= 100)).all())


def regime_bars(n, seed, p0=100.0, tick=0.25, scale=1.0):
    """Synthetic bars on a price grid (``tick``, so that closes tie with box edges): quiet stretches (closes near a
    level, wide wicks: squeezes), trends (steady closes, small wicks) and random walks, in random order and lengths;
    every move is ``scale`` times the sizes below."""
    rng = np.random.default_rng(seed)
    o, h, l, c = (np.empty(n) for _ in range(4))
    level = prev = p0
    t = 0
    while t < n:
        kind = int(rng.integers(0, 3))
        k = int(rng.integers(3, 26))
        drift = float(rng.choice([-1.0, 1.0]) * rng.uniform(0.3, 1.5)) * scale
        for _ in range(k):
            if t >= n:
                break
            if kind == 0:
                close = level + rng.normal(0.0, 0.2) * scale
                up, dn = rng.uniform(0.25, 2.5) * scale, rng.uniform(0.25, 2.5) * scale
            elif kind == 1:
                level += drift
                close = level + rng.normal(0.0, 0.2) * scale
                up, dn = rng.uniform(0.0, 0.5) * scale, rng.uniform(0.0, 0.5) * scale
            else:
                level += rng.normal(0.0, 0.8) * scale
                close, up, dn = level, rng.uniform(0.0, 1.0) * scale, rng.uniform(0.0, 1.0) * scale
            close = round(close / tick) * tick
            o[t], c[t] = prev, close
            h[t] = max(prev, close) + round(up / tick) * tick
            l[t] = min(prev, close) - round(dn / tick) * tick
            prev = close
            t += 1
    return o, h, l, c


def random_squeeze_input(n, seed, tick=0.25):
    """A random squeeze series (runs of 1-9 squeeze bars, gaps of 1-7) with a random walk of closes on a grid."""
    rng = np.random.default_rng(seed)
    sq = np.zeros(n, bool)
    t, on = 0, bool(rng.integers(0, 2))
    while t < n:
        k = int(rng.integers(1, 10)) if on else int(rng.integers(1, 8))
        sq[t:t + k] = on
        t += k
        on = not on
    c = 100.0 + np.cumsum(np.round(rng.normal(0.0, 0.6, n) / tick) * tick)
    h = c + np.round(rng.uniform(0.0, 1.0, n) / tick) * tick
    l = c - np.round(rng.uniform(0.0, 1.0, n) / tick) * tick
    return sq, h, l, c


def paths(r, c, min_bars=6, armed_bars=12):
    """How each armed segment ended, and the special cases it passed through (for coverage)."""
    sq, rl, bo = r["squeeze_on"], r["run_len"], r["breakout"]
    n = len(c)
    cov = dict(long=0, short=0, expired=0, replaced=0, data_end=0, bar1=0, bar12=0, on_squeeze=0, ties=0,
               replaced_close_outside=0)
    cov["ties"] = int((r["armed"] & ((c == r["box_hi"]) | (c == r["box_lo"]))).sum())
    for a, z in segments(r):
        m = z - a + 1
        if bo[z] != 0:
            cov["long" if bo[z] > 0 else "short"] += 1
            cov["bar1"] += m == 1
            cov["bar12"] += m == armed_bars
            cov["on_squeeze"] += bool(sq[z])
        elif m == armed_bars:
            cov["expired"] += 1
        elif z == n - 1:
            cov["data_end"] += 1
        else:
            assert sq[z + 1] and rl[z + 1] == min_bars, (a, z)
            cov["replaced"] += 1
            if c[z + 1] > r["box_hi"][z] or c[z + 1] < r["box_lo"][z]:
                cov["replaced_close_outside"] += 1
    return cov


# ───────────────────────────── 1. the contract's traps (hand-computed) ─────────────────────────────

def test_trap_run_of_exactly_5_is_no_coil_and_6_is():
    """Bar 0 no squeeze; bars 1-5 (5 bars) or 1-6 (6 bars) squeeze with H 101 / L 99 / C 100 (box [99, 101]); then a
    bar closing at 102 (> 101). Five bars are no coil: nothing is armed and 102 is no breakout. Six bars are a coil,
    armed from the first bar after the run, whose close 102 > 101 breaks out (+1) at once."""
    r5 = Tape().bar(100).quiet(5).bar(102).bar(102).run()
    assert L(r5["run_len"]) == [0, 1, 2, 3, 4, 5, 0, 0]
    assert not r5["armed"].any() and not r5["breakout"].any()
    assert np.isnan(r5["box_hi"]).all() and np.isnan(r5["bo_box_hi"]).all()

    r6 = Tape().bar(100).quiet(6).bar(102).bar(102).run()
    assert L(r6["run_len"]) == [0, 1, 2, 3, 4, 5, 6, 0, 0]
    assert L(r6["armed"]) == [False] * 7 + [True, False]
    assert L(r6["breakout"]) == [0] * 7 + [1, 0]
    assert nan_list(r6["box_hi"]) == [None] * 7 + [101.0, None]
    assert nan_list(r6["bo_box_lo"]) == [None] * 7 + [99.0, None]

    # the same through the full rule on OHLC bars (quiet_start's run, then a jump to 111: 2 sd = 11 sqrt(19)/10 = 4.79
    # against 1.5 ATR = 1.5 (0.05 x 11 + 0.95 x 0.95^(k-1)) < 1.99: no squeeze)
    for k, armed in ((5, False), (6, True)):
        b = quiet_start(k).flat(111.0, 3)
        r = b.coil()
        j = 20 + k                                               # the first bar after the run
        assert L(r["squeeze_on"][19:j + 2]) == [False] + [True] * k + [False, False]
        assert L(r["run_len"][19:j + 1]) == [0] + list(range(1, k + 1)) + [0]
        assert bool(r["armed"][j]) is armed and int(r["breakout"][j]) == (1 if armed else 0)
        assert int(np.abs(r["breakout"]).sum()) == (1 if armed else 0)
        if armed:
            assert (r["bo_box_hi"][j], r["bo_box_lo"][j]) == (110.0, 90.0)


def test_trap_breakout_on_the_12th_armed_bar_counts_and_on_the_13th_not():
    """A coil of bars 0-5 (box [99, 101]) is armed on bars 6 .. 17 (6 + 12 - 1). Closes of 100 inside; a close of 102
    on bar 17 (the 12th armed bar) breaks out; the same close on bar 18 (the 13th) does not: the window is over."""
    r12 = Tape().quiet(6).bars(11, 100).bar(102).bar(102).run()
    assert L(np.flatnonzero(r12["armed"])) == list(range(6, 18))
    assert L(np.flatnonzero(r12["breakout"])) == [17] and int(r12["breakout"][17]) == 1

    r13 = Tape().quiet(6).bars(12, 100).bar(102).bar(102).run()
    assert L(np.flatnonzero(r13["armed"])) == list(range(6, 18))
    assert not r13["breakout"].any() and not r13["armed"][18]
    assert np.isnan(r13["box_hi"][18])

    # with armed_bars = 3 the window is bars 6-8
    r3 = Tape().quiet(6).bars(2, 100).bar(102).run(armed_bars=3)
    assert L(np.flatnonzero(r3["armed"])) == [6, 7, 8] and int(r3["breakout"][8]) == 1
    r3b = Tape().quiet(6).bars(3, 100).bar(102).run(armed_bars=3)
    assert L(np.flatnonzero(r3b["armed"])) == [6, 7, 8] and not r3b["breakout"].any()

    # on OHLC bars: quiet_start's run 20-25, box [90, 110]; then flat bars at 104 (no squeeze: j bars of 104 in the
    # window give 2 sd = 0.4 sqrt(j (20 - j)) >= 1.74 while 1.5 ATR <= 1.40 and falls), then 111 > 110
    for which, expect in ((12, 1), (13, 0)):
        b = quiet_start(6).flat(104.0, which - 1).flat(111.0, 2)
        r = b.coil()
        assert L(np.flatnonzero(r["armed"])) == list(range(26, 26 + min(which, 12)))
        assert not r["squeeze_on"][26:].any()
        assert int(r["breakout"][25 + which]) == expect and int(np.abs(r["breakout"]).sum()) == expect


def test_trap_newer_coil_replaces_the_armed_one():
    """Coil 1: bars 0-5 (box [99, 101]), armed from bar 6. A newer run of bars 8-13 with H 103 / L 97 reaches 6 bars on
    bar 13: coil 1 is replaced there (armed on 6-12 only). Bar 14 ends the newer run: coil 2 (box [97, 103]) is armed.
    Its close 102 is above coil 1's box but inside coil 2's: no breakout; bar 15's 104 breaks coil 2 (+1)."""
    t = Tape().quiet(6).bars(2, 100).quiet(6, hi=103.0, lo=97.0).bar(102).bar(104).bar(104)
    r = t.run()
    assert L(r["run_len"]) == [1, 2, 3, 4, 5, 6, 0, 0, 1, 2, 3, 4, 5, 6, 0, 0, 0]
    assert L(np.flatnonzero(r["armed"])) == [6, 7, 8, 9, 10, 11, 12, 14, 15]
    assert nan_list(r["box_hi"][6:16]) == [101.0] * 7 + [None, 103.0, 103.0]
    assert nan_list(r["box_lo"][6:16]) == [99.0] * 7 + [None, 97.0, 97.0]
    assert L(np.flatnonzero(r["breakout"])) == [15] and int(r["breakout"][15]) == 1
    assert (r["bo_box_hi"][15], r["bo_box_lo"][15]) == (103.0, 97.0)

    # a newer run of only 5 bars (8-12) replaces nothing: coil 1 stays armed through bar 17 and bar 13's 102 breaks it
    r5 = Tape().quiet(6).bars(2, 100).quiet(5, hi=103.0, lo=97.0).bar(102).run()
    assert L(np.flatnonzero(r5["armed"])) == list(range(6, 14))
    assert L(np.flatnonzero(r5["breakout"])) == [13] and r5["bo_box_hi"][13] == 101.0

    # on OHLC bars (quiet_start's run 20-25, box [90, 110]):
    # bar 26  flat 104: 2 sd 1.74 > 1.5 ATR 1.40, no squeeze: coil 1 armed (1), inside
    # bar 27  O = C = 104, H 154, L 54: TR 100, ATR = 5 + 0.95 x 0.935 = 5.89, 1.5 ATR 8.83 > 2 sd 2.40: squeeze (1)
    # bars 28-31 flat 104: 1.5 ATR 8.39 .. 7.19 > 2 sd 2.86 .. 3.67: squeeze (2-5); coil 1 still armed (3-6)
    # bar 32  flat 111: TR 7, 1.5 ATR 7.36 > 2 sd 5.58: squeeze (6): the newer run is a coil and replaces coil 1
    #         before the close is tested, so 111 > 110 is no breakout (reading 2)
    # bar 33  flat 134: TR 23, 1.5 ATR 8.72 < 2 sd 15.07: no squeeze: coil 2 (bars 27-32, box [54, 154]) is armed;
    #         134 > 110 but < 154: no breakout
    # bar 34  flat 155 > 154: breakout +1 of coil 2
    b = quiet_start(6).flat(104.0).wick(104.0, 50.0).flat(104.0, 4).flat(111.0).flat(134.0).flat(155.0, 2)
    r = b.coil()
    assert L(r["squeeze_on"][25:35]) == [True, False, True, True, True, True, True, True, False, False]
    assert L(r["run_len"][27:33]) == [1, 2, 3, 4, 5, 6]
    assert L(np.flatnonzero(r["armed"])) == [26, 27, 28, 29, 30, 31, 33, 34]
    assert nan_list(r["box_hi"][26:35]) == [110.0] * 6 + [None, 154.0, 154.0]
    assert L(np.flatnonzero(r["breakout"])) == [34] and (r["bo_box_hi"][34], r["bo_box_lo"][34]) == (154.0, 54.0)


def test_trap_close_exactly_at_box_hi_is_no_breakout():
    """Box [99, 101]. A close of exactly 101 (box_hi) or 99 (box_lo) is no breakout (strict ``>`` / ``<``); the next
    float above 101 is (+1), and in a second coil the next float below 99 is (-1)."""
    up = math.nextafter(101.0, math.inf)
    dn = math.nextafter(99.0, -math.inf)
    r = Tape().quiet(6).bar(101.0).bar(99.0).bar(101.0).bar(up).run()
    assert L(r["armed"][6:]) == [True, True, True, True]
    assert L(r["breakout"][6:]) == [0, 0, 0, 1]
    r = Tape().quiet(6).bar(99.0).bar(101.0).bar(dn).run()
    assert L(r["breakout"][6:]) == [0, 0, -1]
    # with the wick at the edge: H 101.5 > box_hi but C = 101: no breakout (the close decides)
    r = Tape().quiet(6).bar(101.0, hi=101.5, lo=100.0).run()
    assert bool(r["armed"][6]) and int(r["breakout"][6]) == 0


# ───────────────────────────── 1. the rule's other traps (hand-computed) ─────────────────────────────

def test_trap_box_spans_the_whole_run():
    """A run of 9 bars, H 101 / L 99 except bar 1 (L 98) and bar 7 (H 104, L 100): the box is [98, 104], over ALL nine
    bars. The first six bars alone would give [98, 101] and the last six (3-8) [99, 104]. Bar 9's close 102 (it would
    break [98, 101]) and bar 10's 98.5 (it would break [99, 104]) are no breakouts; bar 11's 97.5 < 98 is (-1)."""
    t = Tape().quiet(1).quiet(1, hi=101.0, lo=98.0).quiet(5).quiet(1, hi=104.0, lo=100.0).quiet(1)
    t.bar(102.0).bar(98.5).bar(97.5)
    r = t.run()
    assert L(r["run_len"][:10]) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
    assert (r["box_hi"][9], r["box_lo"][9]) == (104.0, 98.0)
    # first six bars: [98, 101] -> 102 would break; last six bars (3-8): [99, 104] -> 98.5 would break
    assert L(r["breakout"][9:]) == [0, 0, -1]
    assert (r["bo_box_hi"][11], r["bo_box_lo"][11]) == (104.0, 98.0)

    # on OHLC bars: quiet_start's run 20-26 (7 bars) plus bar 27 O = C = 100, H 115, L 100 (sd = 0: squeeze) and bar
    # 28 flat 100: a 9-bar run, box [90, 115]. Bar 29 flat 112: 2 sd 5.23 > 1.5 ATR 2.86: armed (1), 112 < 115 (a box
    # of the first six bars, [90, 110], would break); bar 30 flat 95: 95 > 90 (the last six bars 23-28 give [100,
    # 115], which would break); bar 31 flat 89 < 90: breakout -1.
    b = quiet_start(7).add(100.0, 115.0, 100.0, 100.0).flat(100.0).flat(112.0).flat(95.0).flat(89.0, 2)
    r = b.coil()
    assert L(r["run_len"][20:30]) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
    assert L(np.flatnonzero(r["armed"])) == [29, 30, 31]
    assert (r["box_hi"][29], r["box_lo"][29]) == (115.0, 90.0)
    assert L(r["breakout"][29:]) == [0, 0, -1, 0]


def test_trap_armed_from_the_first_bar_after_the_run():
    """Nothing is armed while the run lasts (even past min_bars); the first bar after the run is armed and its own
    close is tested: a breakout there is a breakout on armed bar 1."""
    r = Tape().quiet(8).bar(103.0).run()
    assert not r["armed"][:8].any() and np.isnan(r["box_hi"][:8]).all()
    assert bool(r["armed"][8]) and int(r["breakout"][8]) == 1
    # min_bars = 3: a 3-bar run is a coil
    r = Tape().bar(100).quiet(3).bar(98.5).run(min_bars=3)
    assert L(r["armed"]) == [False, False, False, False, True] and int(r["breakout"][4]) == -1


def test_trap_breakout_reads_the_close_not_the_wick():
    """Armed bars whose high (or low) pierces the box while the close stays inside are no breakouts."""
    r = Tape().quiet(6).bar(100.5, hi=105.0, lo=100.0).bar(99.5, hi=100.0, lo=95.0).bar(101.25).run()
    assert L(r["breakout"][6:]) == [0, 0, 1]


def test_trap_once_per_coil():
    """After a breakout the coil is used: a later close beyond either edge within the 12 bars is no event, and the
    coil is not armed after its breakout bar."""
    r = Tape().quiet(6).bar(102.0).bar(98.0).bar(103.0).bars(5, 97.0).run()
    assert L(r["breakout"][6:]) == [1, 0, 0, 0, 0, 0, 0, 0]
    assert L(r["armed"][6:]) == [True] + [False] * 7


def test_trap_shorter_newer_run_keeps_the_armed_coil():
    """A newer run of fewer than min_bars bars inside the window: the coil stays armed, its squeeze bars count towards
    the 12 (bars 6 .. 17 whatever the squeeze does), and a close beyond the box on one of those squeeze bars is a
    breakout (reading 3)."""
    r = Tape().quiet(6).bar(100).quiet(4).bars(10, 100).run()
    assert L(np.flatnonzero(r["armed"])) == list(range(6, 18))
    r = Tape().quiet(6).bar(100).quiet(2).bar(101.5, sq=True, hi=101.5, lo=100.0).bars(3, 100).run()
    assert bool(r["squeeze_on"][9]) and int(r["run_len"][9]) == 3
    assert L(np.flatnonzero(r["breakout"])) == [9] and int(r["breakout"][9]) == 1


def test_trap_replacement_bar_cannot_break_the_old_box():
    """Reading 2: on the bar where a newer run reaches min_bars, the old coil is dropped before that bar's close is
    tested. Coil 1 bars 0-5 [99, 101]; newer run bars 7-12, whose 6th bar (12) closes 101.5 > 101 (its own high 102):
    no breakout of coil 1, which is armed on 6-11 only."""
    t = Tape().quiet(6).bar(100).quiet(5, hi=102.0, lo=98.0).quiet(1, hi=102.0, lo=98.0, close=101.5).bar(100)
    r = t.run()
    assert int(r["run_len"][12]) == 6
    assert L(np.flatnonzero(r["armed"])) == [6, 7, 8, 9, 10, 11, 13]
    assert not r["breakout"].any()
    assert (r["box_hi"][13], r["box_lo"][13]) == (102.0, 98.0)            # coil 2, armed on bar 13


def test_trap_breakout_bar_is_armed():
    """Reading 1: the breakout bar is an armed bar (box_* = bo_box_* there); the bar after it is not."""
    r = Tape().quiet(6).bar(100).bar(98.0).bar(100).run()
    assert L(r["armed"][6:]) == [True, True, False]
    assert (r["box_hi"][7], r["box_lo"][7]) == (r["bo_box_hi"][7], r["bo_box_lo"][7]) == (101.0, 99.0)
    assert np.isnan(r["box_hi"][8])


def test_trap_run_open_at_the_last_bar_is_not_armed():
    """A run still going at the last bar is not known to have ended: nothing is armed; one more bar arms it."""
    r = Tape().bar(100).quiet(8).run()
    assert not r["armed"].any() and not r["breakout"].any()
    r = Tape().bar(100).quiet(8).bar(100).run()
    assert L(r["armed"]) == [False] * 9 + [True]


# ───────────────────────────── 1. the squeeze's Pine traps (hand-computed) ─────────────────────────────

def test_trap_squeeze_strict_bands_touching_the_channel():
    """Flat bars: on bar 19 basis = 100, sd = 0 and ATR(20) = 0, so upper_bb == upper_kc == 100: ``<`` is false: no
    squeeze. Bar 20 (O = C = 100, H 110, L 90) gives ATR = 1.0 and the bands strictly inside: squeeze."""
    b = quiet_start(1).flat(100.0)
    ln = b.lines()
    assert (ln["upper_bb"][19], ln["upper_kc"][19], ln["lower_bb"][19], ln["lower_kc"][19]) == (100.0,) * 4
    assert ln["dev"][19] == 0.0 and ln["atr"][19] == 0.0
    assert ln["atr"][20] == 1.0 and (ln["upper_kc"][20], ln["lower_kc"][20]) == (101.5, 98.5)
    assert L(ln["squeeze_on"][18:22]) == [False, False, True, True]


def test_trap_stdev_population_not_sample():
    """Bars 0-19 flat 100; bar 20 O = C = 100, H 105.125, L 94.875 (TR 10.25: ATR = 0.5125); bar 21 flat 102 (TR 2:
    ATR = 0.1 + 0.95 x 0.5125 = 0.586875, 1.5 ATR = 0.8803125). The window of bar 21 holds 19 closes of 100 and one of
    102: mean 100.1, squared deviations 3.8; population sd = sqrt(3.8 / 20) = 0.4358899 (2 sd = 0.8717798 < 0.8803125:
    squeeze), sample sd = sqrt(3.8 / 19) = 0.4472136 (2 sd = 0.8944272: no squeeze)."""
    b = Bars().flat(100.0, 20).add(100.0, 105.125, 94.875, 100.0).flat(102.0)
    ln = b.lines()
    a = 1 / 20                                                    # ta.rma: alpha * tr + (1 - alpha) * rma[1]
    assert ln["atr"][20] == a * 10.25 + (1 - a) * 0.0 and ln["atr"][21] == a * 2.0 + (1 - a) * ln["atr"][20]
    assert abs(ln["atr"][21] - 0.586875) < 1e-15
    assert abs(ln["dev"][21] - 2 * math.sqrt(3.8 / 20)) < 1e-12
    assert 2 * math.sqrt(3.8 / 19) > 1.5 * ln["atr"][21] > ln["dev"][21]          # the trap is live
    assert L(ln["squeeze_on"][19:22]) == [False, True, True]


def test_trap_stdev_zeroes_deviations_up_to_1e_10():
    """``ta.stdev``'s reference code adds ``SUM(x[i], -avg)``, which is 0 when |x[i] - avg| <= 1e-10 (its isZero).
    (a) 20 closes of 1923.456: pine_sma gives 1923.4560000000006 (each 1923.456 / 20 is rounded), so every deviation
    is -6.8e-13: zeroed, and the stdev is exactly 0 (without the zeroing it would be 6.8e-13).
    (b) 19 closes of 100 and one of 100 + 1e-9: the mean is 100 + 5e-11; the 19 deviations of -5e-11 are zeroed and only
    9.5e-10 counts: sd = 9.5e-10 / sqrt(20) = 2.124e-10, not the exact 1e-9 sqrt(19) / 20 = 2.179e-10.
    (c) On bars: bar 0 O = C = 1923.456 with H / L +-8e-12, then flat 1923.456: on bar 19 ATR(20) = 1.59e-11 / 20 =
    7.96e-13 (1.5 ATR = 1.19e-12): with the zeroing the bands are the basis, inside the channel (squeeze); without
    it 2 sd = 1.36e-12 would put them outside."""
    v = 1923.456
    sd = O.Stdev(20)
    vals = [sd(v) for _ in range(20)]
    avg = O.Sma(20)
    a = [avg(v) for _ in range(20)][-1]
    assert a == 1923.4560000000006 and v - a != 0.0 and abs(v - a) <= 1e-10
    assert vals[-1] == 0.0
    sd = O.Stdev(20)
    x = [100.0] * 19 + [100.0 + 1e-9]
    got = [sd(t) for t in x][-1]
    assert abs(got - 9.5e-10 / math.sqrt(20)) < 1e-3 * got and abs(got - 1e-9 * math.sqrt(19) / 20) > 0.02 * got
    b = Bars().add(v, v + 8e-12, v - 8e-12, v).flat(v, 20)
    ln = b.lines()
    assert ln["dev"][19] == 0.0 and abs(ln["atr"][19] - 7.958e-13) < 1e-15
    assert bool(ln["squeeze_on"][19])
    assert not (ln["basis"][19] + 2 * abs(v - ln["basis"][19]) < ln["upper_kc"][19])   # the unzeroed band: outside


def test_trap_channel_width_wilder_atr_not_sma_of_true_range():
    """Bar 20's wick (H 114.25, L 85.75: TR 28.5) leaves the 20-bar SMA of the true range after bar 39, but stays in
    Wilder's ATR as 0.95^m. Bars 21-39 flat 100 (squeeze: sd = 0); bar 40 flat 102: TR 2; ATR(40) = 0.05 x 2 + 0.95 x
    (1.425 x 0.95^19) = 0.610842 (1.5 ATR = 0.916264) > 2 sd = 0.871780: squeeze, run 21. The SMA of the true range
    (the classic TTM squeeze) would be 2 / 20 = 0.1 (1.5 x = 0.15): no squeeze."""
    b = Bars().flat(100.0, 20).add(100.0, 114.25, 85.75, 100.0).flat(100.0, 19).flat(102.0)
    ln = b.lines()
    assert abs(ln["atr"][40] - (0.1 + 0.95 * 1.425 * 0.95 ** 19)) < 1e-12
    assert abs(ln["dev"][40] - 2 * 2 * math.sqrt(19) / 20) < 1e-12
    assert 1.5 * ln["atr"][40] > ln["dev"][40] > 1.5 * 0.1
    r = b.coil()
    assert bool(r["squeeze_on"][40]) and int(r["run_len"][40]) == 21


def test_trap_atr_first_true_range_is_high_minus_low():
    """``ta.atr`` reads ``ta.tr(true)``: bar 0's true range is H - L = 2 (101 - 99). Bars 1-21 flat 100 (TR 0). On
    bar 19 ATR(20) = 2 / 20 = 0.1 > 0 with sd = 0: squeeze on the first bar the bands exist. With an na first true
    range the ATR would be na on bar 19 and 0 on bar 20 (no squeeze on either)."""
    b = Bars().add(100.0, 101.0, 99.0, 100.0).flat(100.0, 21)
    ln = b.lines()
    assert np.isnan(ln["atr"][18]) and ln["atr"][19] == 2.0 / 20 and ln["atr"][20] == 0.95 * 0.1
    assert L(ln["squeeze_on"][17:22]) == [False, False, True, True, True]


def test_trap_bands_na_in_warm_up_no_squeeze():
    """Bars 0-26 all O = C = 100, H 101, L 99 (sd 0, TR 2): every band is na on bars 0-18, so squeeze_on is False there
    (a comparison with na is false) and the first run starts on bar 19 (bars 19-26: 8 bars). Bar 27 flat at 110: TR
    10, ATR = 0.05 x 10 + 0.95 x 2 = 2.4 (1.5 ATR = 3.6) < 2 sd = 2 x 10 sqrt(19) / 20 = 4.36: the run ends, the coil
    (box [99, 101]) is armed on bar 27 and 110 > 101 breaks out."""
    b = Bars()
    for _ in range(27):
        b.wick(100.0, 1.0)
    b.flat(110.0)
    ln = b.lines()
    assert np.isnan(ln["basis"][:19]).all() and np.isnan(ln["atr"][:19]).all() and np.isfinite(ln["atr"][19])
    r = b.coil()
    assert not r["squeeze_on"][:19].any() and L(r["run_len"][17:22]) == [0, 0, 1, 2, 3]
    assert int(r["run_len"][26]) == 8 and not r["squeeze_on"][27] and int(r["breakout"][27]) == 1
    assert (r["bo_box_hi"][27], r["bo_box_lo"][27]) == (101.0, 99.0)
    assert np.isnan(r["adx"][:27]).all() and np.isfinite(r["adx"][27])


# ───────────────────────────── 1. the DMI's traps (hand-computed) ─────────────────────────────

DMI_BARS = [  # (h, l, c); up = h - h[1], down = l[1] - l; TR = max(h - l, |h - c[1]|, |l - c[1]|)
    (10.0, 8.0, 9.0),     # 0: na
    (12.0, 9.0, 11.0),    # 1: up 2, down -1: +DM 2, -DM 0; TR 3
    (11.0, 7.0, 8.0),     # 2: up -1, down 2: +DM 0, -DM 2; TR 4
    (14.0, 9.0, 13.0),    # 3: up 3, down -2: +DM 3, -DM 0; TR 6 (|14 - 8|)
    (15.0, 12.0, 14.0),   # 4: up 1, down -3: +DM 1, -DM 0; TR 3
    (16.0, 11.0, 12.0),   # 5: up 1, down 1: a TIE: +DM 0, -DM 0; TR 5
    (15.0, 13.0, 14.0),   # 6: up -1, down -2: an inside bar: 0, 0; TR 3
]


def dmi_hand():
    """di_len = adx_len = 2 (alpha 0.5), by hand, in the order of the formulas; every RMA value is dyadic (exact).

    trur  bar 2 = 4/2 + 3/2 = 3.5 (SMA of TR 1-2: TR 0 is na); then 0.5 TR + 0.5 trur[1]: 4.75, 3.875, 4.4375, 3.71875
    +rma  bar 2 = 0/2 + 2/2 = 1.0; then 2.0, 1.5, 0.75, 0.375        -rma  1.0; then 0.5, 0.25, 0.125, 0.0625
    DX exactly: bar 2 0, bar 3 (200 - 50) / 250 = 0.6, bars 4-6 5/7.
    ADX = 100 x RMA2(DX): 30, 50.714.., 61.071.., 66.25
    """
    trur = [NAN, NAN, 4 / 2 + 3 / 2]
    rp, rm = [NAN, NAN, 0 / 2 + 2 / 2], [NAN, NAN, 2 / 2 + 0 / 2]
    tr = [NAN, 3.0, 4.0, 6.0, 3.0, 5.0, 3.0]
    pdm, mdm = [NAN, 2.0, 0.0, 3.0, 1.0, 0.0, 0.0], [NAN, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0]
    for t in range(3, 7):
        trur.append(0.5 * tr[t] + (1 - 0.5) * trur[-1])
        rp.append(0.5 * pdm[t] + (1 - 0.5) * rp[-1])
        rm.append(0.5 * mdm[t] + (1 - 0.5) * rm[-1])
    plus = [NAN, NAN] + [100 * rp[t] / trur[t] for t in range(2, 7)]
    minus = [NAN, NAN] + [100 * rm[t] / trur[t] for t in range(2, 7)]
    dx = [NAN, NAN] + [abs(plus[t] - minus[t]) / (plus[t] + minus[t]) for t in range(2, 7)]
    r = [NAN, NAN, NAN, dx[3] / 2 + dx[2] / 2]
    for t in range(4, 7):
        r.append(0.5 * dx[t] + (1 - 0.5) * r[-1])
    return dict(trur=trur, plus=plus, minus=minus, dx=dx, adx=[100 * v for v in r])


def dmi_arrays():
    a = np.array(DMI_BARS)
    return a[:, 0], a[:, 1], a[:, 2]


def test_trap_dmi_wilder_smoothing_hand_values():
    h, l, c = dmi_arrays()
    plus, minus, adx = O.dmi(h, l, c, di_len=2, adx_len=2)
    e = dmi_hand()
    assert same(plus, np.array(e["plus"])) and same(minus, np.array(e["minus"])) and same(adx, np.array(e["adx"]))
    assert e["trur"][2:] == [3.5, 4.75, 3.875, 4.4375, 3.71875]
    exact = [30.0, 100 * 71 / 140, 100 * 171 / 280, 100 * 371 / 560]       # 0.3, 71/140, 171/280, 371/560
    assert np.allclose(adx[3:], exact, rtol=0, atol=1e-12) and abs(adx[6] - 66.25) < 1e-12
    assert same(O.adx(h, l, c, 2, 2), adx)


def test_trap_dm_rule_ties_and_inside_bars():
    """``up > down and up > 0``: on bar 5 up == down == 1 gives 0 to both (a ``>=`` rule would give +DM 1: +rma 1.25,
    not 0.75); bar 6 (inside: up -1, down -2) gives 0 to both. So +DI on bar 5 = 100 x 0.75 / 4.4375 and -DI = 100 x
    0.125 / 4.4375; on bar 6 100 x 0.375 / 3.71875 and 100 x 0.0625 / 3.71875."""
    h, l, c = dmi_arrays()
    plus, minus, _ = O.dmi(h, l, c, di_len=2, adx_len=2)
    assert plus[5] == 100 * 0.75 / 4.4375 and minus[5] == 100 * 0.125 / 4.4375
    assert plus[6] == 100 * 0.375 / 3.71875 and minus[6] == 100 * 0.0625 / 3.71875
    # the larger move wins when both are positive (an outside bar): up 3, down 2 -> +DM 3, -DM 0
    plus2, minus2, _ = O.dmi([10.0, 13.0, 13.0], [8.0, 6.0, 6.0], [9.0, 9.0, 9.0], di_len=1, adx_len=1)
    assert plus2[1] == 100 * 3.0 / 7.0 and minus2[1] == 0.0                # TR 7 (13 - 6); -DM 0 because 2 < 3


def test_trap_dmi_true_range_is_ta_tr_na_on_bar_0():
    """The DMI script's ``ta.tr`` is ``ta.tr(false)``: na on bar 0, so trur starts on bar 2 (di_len 2) as the mean of
    TR 1-2 = 3.5, and +DI on bar 2 is 100 x 1.0 / 3.5 = 28.5714. With ``ta.tr(true)`` (bar 0's TR = 2) trur would start
    on bar 1 (2.5) and be 3.25 on bar 2 (+DI 30.77). DX is a ratio in which trur cancels: the ADX is the same in exact
    arithmetic either way (only last bits), as the docstring's reading 11 says."""
    h, l, c = dmi_arrays()
    plus, minus, adx = O.dmi(h, l, c, di_len=2, adx_len=2)
    assert np.isnan(plus[:2]).all() and plus[2] == 100 * 1.0 / 3.5 and plus[2] != 100 * 1.0 / 3.25
    assert minus[2] == 100 * 1.0 / 3.5


def test_trap_change_na_on_bar_0_dmi_warm_up():
    """``ta.change`` is na on bar 0, so +DM / -DM are na there (not 0): the DM averages start on bar di_len, DX on bar
    di_len and the ADX on bar di_len + adx_len - 1: 3 for (2, 2), 27 for the plan's (14, 14)."""
    h, l, c = dmi_arrays()
    _, _, adx = O.dmi(h, l, c, di_len=2, adx_len=2)
    assert np.isnan(adx[:3]).all() and np.isfinite(adx[3:]).all()
    o, h, l, c = regime_bars(60, 3)
    p, m, a = O.dmi(h, l, c)
    assert np.isnan(p[:14]).all() and np.isfinite(p[14:]).all() and np.isnan(m[:14]).all()
    assert np.isnan(a[:27]).all() and np.isfinite(a[27:]).all()
    _, _, a3 = O.dmi(h, l, c, di_len=3, adx_len=5)
    assert np.isnan(a3[:7]).all() and np.isfinite(a3[7:]).all()


def test_trap_dx_guard_zero_sum():
    """Bars with the same high and low every bar (H 11, L 9, C 10): up = down = 0, so +DM = -DM = 0, +DI = -DI = 0
    and ``sum == 0 ? 1 : sum`` makes DX = 0 / 1 = 0 (not 0 / 0): the ADX is exactly 0 from bar 27."""
    n = 40
    adx = O.adx(np.full(n, 11.0), np.full(n, 9.0), np.full(n, 10.0))
    assert np.isnan(adx[:27]).all() and (adx[27:] == 0.0).all()


def test_trap_fixnan_keeps_na_until_the_first_value():
    """Flat bars 0-19 (O = H = L = C = 100): every true range is 0, trur = 0 and 100 x 0 / 0 is na; fixnan has no
    earlier value, so +DI, -DI and DX stay na. Bar 20 (H 101, L 99, C 100.5): up = down = 1 (a tie: 0, 0), TR 2, trur =
    0.5 x 2 = 1.0, +DI = -DI = 0, DX = 0 (the guard). Bar 21 (H 103, L 100, C 102): up 2, down -1: +DM 2; TR 3; trur
    2.0, +rma 1.0: +DI 50, -DI 0, DX 1.0. The ADX (adx_len 2) starts on bar 21: 100 x (1.0 / 2 + 0 / 2) = 50."""
    h = [100.0] * 20 + [101.0, 103.0]
    l = [100.0] * 20 + [99.0, 100.0]
    c = [100.0] * 20 + [100.5, 102.0]
    plus, minus, adx = O.dmi(h, l, c, di_len=2, adx_len=2)
    assert np.isnan(plus[:20]).all() and np.isnan(minus[:20]).all()
    assert (plus[20], minus[20], plus[21], minus[21]) == (0.0, 0.0, 50.0, 0.0)
    assert np.isnan(adx[:21]).all() and adx[21] == 50.0
    # a plain fixnan: na while there is no value yet; an na after a value repeats the value
    f = O.Fixnan()
    vals = [f(x) for x in (NAN, 1.5, NAN, 2.0, NAN)]
    assert vals[0] != vals[0] and vals[1:] == [1.5, 1.5, 2.0, 2.0]


def test_trap_fixnan_repeats_the_last_value_when_trur_underflows():
    """The one way trur returns to 0 after a value: with di_len = 2 the RMA halves on every flat bar and underflows to
    exactly 0 after about 1075 halvings; 100 x 0 / 0 is na there and fixnan repeats the last +DI / -DI, so DX (0 / 1,
    the guard) and the ADX stay defined. Bars: 0 flat 100; 1 H 101 L 99 C 100 (a tie: 0, 0; TR 2); 2 H 102 L 101 C 102
    (up 1, down -2: +DM 1; TR 2): trur = 2/2 + 2/2 = 2, +rma = 1/2 + 0/2 = 0.5, +DI = 100 x 0.5 / 2 = 25; then 1100
    flat bars at 102 (TR 0, no movement)."""
    h = [100.0, 101.0, 102.0] + [102.0] * 1100
    l = [100.0, 99.0, 101.0] + [102.0] * 1100
    c = [100.0, 100.0, 102.0] + [102.0] * 1100
    plus, minus, adx = O.dmi(h, l, c, di_len=2, adx_len=2)
    assert (plus[2], minus[2], plus[3]) == (25.0, 0.0, 25.0)
    trur_site, tr = O.Rma(2), O.TrueRange(False)
    trur = np.array([trur_site(tr(h[t], l[t], c[t])) for t in range(len(c))])
    z = np.flatnonzero(trur[2:] == 0.0) + 2
    assert len(z) and z[0] > 1000                                          # it underflows (bar 1078)
    assert not np.isnan(plus[2:]).any() and not np.isnan(minus[2:]).any() and not np.isnan(adx[3:]).any()
    assert plus[z[0]] == plus[z[0] - 1] and minus[z[0]] == minus[z[0] - 1]
    assert 0.0 <= adx[-1] < 1e-4                    # DX is 0 once +rma has underflowed: the ADX halves towards 0


# ───────────────────────────── 2. formulation, study 1's primitives, contract, inputs ─────────────────────────────

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_formulation_agrees_on_random_squeeze_series(seed):
    sq, h, l, c = random_squeeze_input(4000, seed)
    for kw in ({}, {"min_bars": 3, "armed_bars": 5}):
        r = O.coil_from_squeeze(sq, h, l, c, **kw)
        f = f_states(sq, h, l, c, **kw)
        for k in f:
            assert same(r[k], f[k]), (seed, kw, k)
    r = O.coil_from_squeeze(sq, h, l, c)
    cov = paths(r, c)
    for k, least in (("long", 30), ("short", 30), ("expired", 15), ("replaced", 15), ("bar1", 10), ("bar12", 1),
                     ("on_squeeze", 20), ("ties", 30), ("replaced_close_outside", 1)):
        assert cov[k] >= least, (seed, k, cov)


@pytest.mark.parametrize("seed, p0, tick, scale", [(11, 100.0, 0.25, 1.0), (12, 1800.0, 0.5, 2.0),
                                                   (13, 30000.0, 5.0, 20.0)])
def test_formulation_agrees_on_synthetic_bars(seed, p0, tick, scale):
    o, h, l, c = regime_bars(3000, seed, p0=p0, tick=tick, scale=scale)
    r = O.coil(o, h, l, c)
    f = formulation(o, h, l, c)
    for k in O.KEYS:
        assert same(r[k], f[k]), (seed, k)
    check_where_values_exist(r, c)
    cov = paths(r, c)            # expiries and replacements: see test_formulation_agrees_on_random_squeeze_series
    assert cov["long"] >= 10 and cov["short"] >= 10 and cov["expired"] + cov["replaced"] >= 1, cov
    # other inputs
    kw = dict(bb_len=10, bb_mult=1.5, kc_len=14, kc_mult=2.0, min_bars=4, armed_bars=8)
    r2, f2 = O.coil(o, h, l, c, **kw), formulation(o, h, l, c, **kw)
    for k in O.KEYS:
        assert same(r2[k], f2[k]), (seed, "kw", k)
    pf, mf, af = f_dmi(h, l, c, 9, 6)
    po, mo, ao = O.dmi(h, l, c, 9, 6)
    assert same(po, pf) and same(mo, mf) and same(ao, af)


@pytest.mark.parametrize("p0, vol", [(1500.0, 2.0), (30000.0, 100.0)])
def test_primitives_equal_study1_oracle(p0, vol):
    """Sma / Stdev / Rma / Atr equal study 1's verified Pine oracle (its numba port and its Pine VM) bit for bit."""
    rng = np.random.default_rng(7)
    n = 800
    c = p0 + np.cumsum(rng.normal(0.0, vol, n))
    h = c + rng.uniform(0.0, vol, n)
    l = c - rng.uniform(0.0, vol, n)
    ln = O.squeeze_lines(h, l, c)
    assert same(ln["basis"], S1.sma(c, 20)) and same(ln["ma"], S1.sma(c, 20))
    assert same(ln["dev"], 2.0 * S1.stdev(c, 20))
    assert same(ln["atr"], S1.atr(h, l, c, 20))
    for n_ in (2, 14, 20):
        mine = [O.Rma(n_), O.Sma(n_), O.Stdev(n_)]
        vm = [S1.Rma(n_), S1.Sma(n_), S1.Stdev(n_)]
        a = np.array([[m(x) for m in mine] for x in c])
        b = np.array([[m(x) for m in vm] for x in c])
        assert same(a, b), n_
    tr = O.TrueRange(True)
    assert same(np.array([tr(h[t], l[t], c[t]) for t in range(n)]), S1.true_range(h, l, c))


def test_contract_keys_dtypes_and_signature():
    o, h, l, c = regime_bars(200, 5)
    r = O.coil(o, h, l, c)
    assert tuple(r) == O.KEYS == ("squeeze_on", "run_len", "armed", "box_hi", "box_lo", "breakout", "bo_box_hi",
                                  "bo_box_lo", "adx")
    assert {k: r[k].dtype for k in O.KEYS} == {k: np.dtype(v) for k, v in O.DTYPES.items()}
    assert r["breakout"].dtype == np.int8 and r["squeeze_on"].dtype == np.bool_ and r["armed"].dtype == np.bool_
    sig = inspect.signature(O.coil)
    assert list(sig.parameters) == ["o", "h", "l", "c", "bb_len", "bb_mult", "kc_len", "kc_mult", "min_bars",
                                    "armed_bars"]
    assert [p.default for p in sig.parameters.values()][4:] == [20, 2.0, 20, 1.5, 6, 12]
    sig = inspect.signature(O.adx)
    assert list(sig.parameters) == ["h", "l", "c", "di_len", "adx_len"]
    assert [p.default for p in sig.parameters.values()][3:] == [14, 14]
    a = O.adx(h, l, c)
    assert isinstance(a, np.ndarray) and a.dtype == np.float64 and same(a, r["adx"])
    e = O.coil(*(np.zeros(0),) * 4)
    assert all(e[k].shape == (0,) and e[k].dtype == O.DTYPES[k] for k in O.KEYS)


def test_inputs_refused_and_left_alone():
    o, h, l, c = regime_bars(100, 6)
    keep = [x.copy() for x in (o, h, l, c)]
    O.coil(o, h, l, c)
    O.adx(h, l, c)
    assert all(same(a, b) for a, b in zip((o, h, l, c), keep))
    bad = c.copy()
    bad[50] = np.nan
    with pytest.raises(ValueError):
        O.coil(o, h, l, bad)
    with pytest.raises(ValueError):
        O.adx(h, l, np.r_[c[:-1], np.inf])
    with pytest.raises(ValueError):
        O.coil(o, h, l, c[:-1])
    with pytest.raises(ValueError):
        O.coil(o[:, None], h, l, c)
    for kw in ({"bb_len": 0}, {"kc_len": 2.5}, {"min_bars": True}, {"armed_bars": 0}, {"kc_mult": np.nan},
               {"bb_mult": -1.0}):
        with pytest.raises(ValueError):
            O.coil(o, h, l, c, **kw)
    with pytest.raises(ValueError):
        O.adx(h, l, c, di_len=0)
    with pytest.raises(ValueError):
        O.coil_from_squeeze(np.full(len(c), 2), h, l, c)


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed, p0, tick, scale", [(21, 100.0, 0.25, 1.0), (22, 30000.0, 5.0, 20.0)])
def test_truncation_invariance(seed, p0, tick, scale):
    o, h, l, c = regime_bars(1200, seed, p0=p0, tick=tick, scale=scale)
    full = O.coil(o, h, l, c)
    sq, armed, bo = full["squeeze_on"], full["armed"], full["breakout"]
    special = set()
    for name, mask in (("run end", sq & ~np.r_[sq[1:], False]), ("armed", armed), ("breakout", bo != 0),
                       ("6th", full["run_len"] == 6)):
        idx = np.flatnonzero(mask)
        assert len(idx) >= 3, name
        special.update(int(x) for x in idx[:: max(1, len(idx) // 6)])
        special.update(int(x) + 1 for x in idx[:3])
    cuts = sorted(x for x in special | {0, 1, 18, 19, 26, 27, 28, 500, 1198} if x < len(c) - 1)
    for t in cuts:
        part = O.coil(o[:t + 1], h[:t + 1], l[:t + 1], c[:t + 1])
        for k in O.KEYS:
            assert same(part[k], full[k][:t + 1]), (t, k)


# ───────────────────────────── 4. the real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H / 1D bars of one symbol from its data start to 2024-07-01 00:00 UTC (exclusive), with study
    1's hold-out guard pointed at an empty folder; only the arrays the rule reads are kept (OHLC; it reads no
    volume)."""
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


# the least events in bars closing in 2019-2022 (about half of what the oracle finds; long, short)
LEAST = {"1H": 100, "4H": 20, "1D": 4}


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    rows = real(symbol)
    dev_a, dev_z = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")
    cut = TM.s_of("2021-06-15 12:00")
    for tf, b in rows.items():
        assert int(b.tc[-1]) <= TM.CUT_S and bool(b.complete.all()), tf               # nothing from the hold-out
        r = O.coil(b.o, b.h, b.l, b.c)
        check_where_values_exist(r, b.c)
        f = formulation(b.o, b.h, b.l, b.c)
        for k in O.KEYS:
            assert same(r[k], f[k]), (tf, k)
        ln = O.squeeze_lines(b.h, b.l, b.c)                                           # study 1's primitives
        assert same(ln["basis"], S1.sma(b.c, 20)) and same(ln["dev"], 2.0 * S1.stdev(b.c, 20))
        assert same(ln["atr"], S1.atr(b.h, b.l, b.c, 20))
        dev = (b.tc >= dev_a) & (b.tc < dev_z)                                        # bars closing in 2019-2022
        assert bool(np.isfinite(ln["atr"][dev]).all()) and bool(np.isfinite(r["adx"][dev]).all())
        bo = r["breakout"][dev]
        assert int((bo == 1).sum()) >= LEAST[tf] and int((bo == -1).sum()) >= LEAST[tf], (tf, int((bo == 1).sum()),
                                                                                           int((bo == -1).sum()))
        assert int(r["squeeze_on"][dev].sum()) >= 10 * LEAST[tf]
        i = int(np.searchsorted(b.tc, cut, side="right")) - 1                         # a cut at one T
        part = O.coil(b.o[:i + 1], b.h[:i + 1], b.l[:i + 1], b.c[:i + 1])
        for k in O.KEYS:
            assert same(part[k], r[k][:i + 1]), (tf, k)
