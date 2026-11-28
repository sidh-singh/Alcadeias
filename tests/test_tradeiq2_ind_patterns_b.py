"""
Port B (the oracle) of "Harmonic & Chart Patterns [AI-AlgoCode]": ``tests/tradeiq2_oracle_patterns.py`` (study 2,
PREREG 6.7; the specification is the study's maps/ribbon_patterns.md part B).

1. One hand-computed test per trap of the specification's risk list (B6, "Risks"), each named after its trap. The bars
   and swing sets are built by hand, and the comments work out each swing, bar and level.
2. The 38 predicates against an independent "spec form" of them. Each condition is written as a linear slack (> 0
   when it holds), with inR read as the specification states it: r = (d - B) / (A - B) strictly inside (mn, mx), and
   A > B for bear, A < B otherwise. Per id: an instance inside every window, and a just-outside negative for every
   condition that can fail alone. A condition that cannot fail alone is explained: a redundant inequality (proved
   below) or a dead window edge (Bat family, by vertex enumeration). The spec's "midpoint of every ratio window" is
   often infeasible, because XD (Bat) or p4 (Shark) follows from the other ratios, so the positive instance is the
   one with the largest smallest margin.
3. The source checks (skipped when the Pine source is not on this machine):
   - the generated tables regenerate from it;
   - a mechanical Pine -> Python translation of its rule region (L293-522) equals the hand transcription.
   The source is looked up in $TRADEIQ2_PATTERNS_SOURCE, then in the owner's folder named in PREREG section 1.
4. Invariants on synthetic bars: truncation, start offset, the plan levels against the swing points.
5. Real bars (skipped without the tick store): both symbols, 1H / 4H / 1D (the timeframes PREREG 6.7 uses), bars up
   to 2024-06-30 only (tradeiq_market.load(symbol, end="2024-07-01")). The script reads only high, low and close, so
   no volume is loaded. The checks: the oracle runs, there is no NaN where the contract says values exist, the gates
   and invariants hold, and the Bear Gartley never fires.

Source line numbers (``Lnnn``) refer to the study's copy of the Pine source (``Harmonic and Chart Patterns
Script.txt``).
"""

from __future__ import annotations

import itertools
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_patterns as O  # noqa: E402

C0 = 9                                    # index of c0 in an instance vector x = (p0, ..., p8, c0)
SOURCE_ENV = "TRADEIQ2_PATTERNS_SOURCE"
SOURCE_DIR = Path("/Users/sidharthsingh/Desktop/study/indicator")          # PREREG 1 (read-only, outside the repo)
SOURCE_NAMES = ("Harmonic and Chart Patterns Script.txt", "Harmonic and Chart Patterns Script.rtf")


# ───────────────────────────── helpers ─────────────────────────────

def Qv(*p):
    """An 11-swing set (Q[0] = D). The swings not given are 0.0; Q9 and Q10 are never read by any predicate."""
    q = [float(v) for v in p]
    return q + [0.0] * (11 - len(q))


def legs(points, k=5):
    """
    Zero-range bars (high = low = close = the price) whose zigzag swings are exactly ``points`` (alternating
    extremes, oldest first). A 5-bar lead-in moves 1.0 per bar towards points[0] and ends on it at bar 4. Then come
    ``k`` strictly monotonic bars per leg, each leg ending on the next point. A leg of k >= 5 bars ends with ``depth``
    bars of its own, so its last bar is the extreme of the window and the swing of that leg ends there. No bar inside a
    leg can make a swing of the other kind. Returns (prices, ext) with ext[i] = the bar of points[i].
    """
    first_low = points[1] > points[0]
    for i in range(len(points) - 1):
        assert (points[i + 1] > points[i]) == ((i % 2 == 0) == first_low), "the points must alternate"
    px = [points[0] + (1.0 if first_low else -1.0) * (4 - j) for j in range(5)]
    ext = [4]
    for a, b in zip(points[:-1], points[1:]):
        px += [a + (b - a) * j / k for j in range(1, k + 1)]
        ext.append(len(px) - 1)
    return np.array(px, float), ext


def run(px):
    return O.patterns(px, px, px)


def swing_list(r):
    s = r["swings"]
    return list(zip(s["bar"].tolist(), s["price"].tolist()))


def script_after(h, l, c, t):
    """A Script fed bars 0..t: its state after the close of bar t."""
    sc = O.Script()
    for i in range(t + 1):
        sc.step(float(h[i]), float(l[i]), float(c[i]))
    return sc


def synth(n, seed):
    """A t(3) random walk on a 0.01 grid with random wicks: many swings, all 38 predicates get exercised."""
    rng = np.random.default_rng(seed)
    c = 1000 + np.cumsum(rng.standard_t(3, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.7, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.7, n))
    h, lo, c = (np.round(x, 2) for x in (h, lo, c))
    return np.maximum(h, c), np.minimum(lo, c), c


def same_frame(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    for k in a.columns:
        x, y = a[k].to_numpy(), b[k].to_numpy()
        if x.dtype.kind == "f":
            if not np.all((x == y) | (np.isnan(x) & np.isnan(y))):
                return False
        elif not all(u == v for u, v in zip(x, y)):
            return False
    return True


def rows_of(r, key, t_bar=None, id=None):
    df = r[key]
    if t_bar is not None:
        df = df[df["t_bar"] == t_bar]
    if id is not None:
        df = df[df["id"] == id]
    return df


# ───────────────────────────── the spec form of the 38 predicates ─────────────────────────────
# Written from the specification (B1.3-B1.5) and the predicate lines it cites, independently of the module's
# transcription: every condition is a linear slack g(x) of x = (p0..p8, c0), true when g(x) > 0. Each inR is three
# slacks: its orientation, and r > mn and r < mx, multiplied out by the sign of A - B.

def win(prefix, key):
    return O.RATIOS[f"{prefix}_{key}_min"], O.RATIOS[f"{prefix}_{key}_max"]


def R(bear, iA, iB, iD, w, tag):
    mn, mx = w
    if bear:          # A > B and mn < (d - B) / (A - B) < mx
        return [(tag + ":orient", lambda x: x[iA] - x[iB]),
                (tag + ":lo", lambda x: (x[iD] - x[iB]) - mn * (x[iA] - x[iB])),
                (tag + ":hi", lambda x: mx * (x[iA] - x[iB]) - (x[iD] - x[iB]))]
    return [(tag + ":orient", lambda x: x[iB] - x[iA]),          # A < B: dividing by A - B < 0 flips both
            (tag + ":lo", lambda x: mn * (x[iA] - x[iB]) - (x[iD] - x[iB])),
            (tag + ":hi", lambda x: (x[iD] - x[iB]) - mx * (x[iA] - x[iB]))]


def G(tag, f):
    return [(tag, f)]


BAT = {0: "Bearish_Bat", 1: "Bearish_ALT_Bat", 2: "Bearish_Butterfly", 3: "Bearish_Crab", 4: "Bearish_Gartley",
       5: "Bearish_Deep_Crab", 11: "Bullish_Bat", 12: "Bullish_ALT_Bat", 13: "Bullish_Butterfly", 14: "Bullish_Crab",
       15: "Bullish_Gartley", 16: "Bullish_Deep_Crab"}
SHARK = {6: "Bearish_Shark", 17: "Bullish_Shark"}
ABCD = {7: "Bearish_Trend", 8: "Bearish_ALT_Trend", 18: "Bullish_Trend", 19: "Bullish_ALT_Trend"}
FIVE0 = {9: "BearishPattern", 20: "BullishPattern"}
DRIVES = {10: "Bearish_Tree_Drives", 21: "Bullish_Tree_Drives"}


def spec(id):
    bear = id <= 10
    if id in BAT:          # XB = (B - A)/(X - A), AC = (C - A)/(B - A), BD = (D - C)/(B - C), XD = (D - A)/(X - A)
        p = BAT[id]
        return (R(bear, 4, 3, 2, win(p, "XB"), "XB") + R(bear, 2, 3, 1, win(p, "AC"), "AC")
                + R(bear, 2, 1, 0, win(p, "BD"), "BD") + R(bear, 4, 3, 0, win(p, "XD"), "XD"))
    if id in SHARK:        # L299-305
        p = SHARK[id]
        if bear:
            return (R(False, 3, 2, 1, win(p, "AC"), "AC") + R(True, 2, 1, 0, win(p, "BD"), "BD")
                    + R(True, 4, 3, 0, win(p, "XD"), "XD")
                    + G("p4>p3", lambda x: x[4] - x[3]) + G("p4>p2", lambda x: x[4] - x[2]))
        return (R(True, 3, 2, 1, win(p, "AC"), "AC") + R(False, 2, 1, 0, win(p, "BD"), "BD")
                + R(False, 4, 3, 0, win(p, "XD"), "XD")
                + G("p4<p3", lambda x: x[3] - x[4]) + G("p4<p2", lambda x: x[2] - x[4]))
    if id in ABCD:         # L307-308: 4 points
        p = ABCD[id]
        return R(bear, 2, 3, 1, win(p, "AC"), "AC") + R(bear, 2, 1, 0, win(p, "BD"), "BD")
    if id in FIVE0:        # L310-317: 6 points
        p = FIVE0[id]
        if bear:
            return (R(True, 4, 3, 2, win(p, "AC"), "AC") + R(False, 3, 2, 1, win(p, "BD"), "BD")
                    + R(True, 2, 1, 0, win(p, "CE"), "CE")
                    + G("p5<p4", lambda x: x[4] - x[5]) + G("p5<p3", lambda x: x[3] - x[5]))
        return (R(False, 4, 3, 2, win(p, "AC"), "AC") + R(True, 3, 2, 1, win(p, "BD"), "BD")
                + R(False, 2, 1, 0, win(p, "CE"), "CE")
                + G("p5>p4", lambda x: x[5] - x[4]) + G("p5>p3", lambda x: x[5] - x[3]))
    if id in DRIVES:       # L319-320: the second ratio takes the BD constants (L494, L505)
        p = DRIVES[id]
        return R(bear, 4, 3, 2, win(p, "AC"), "AC") + R(bear, 2, 1, 0, win(p, "BD"), "BD")
    c = C0
    if id == 22:
        return (G("(p3-p4)/2>p3-p2", lambda x: (x[3] - x[4]) / 2 - (x[3] - x[2])) + R(True, 3, 2, 1, (0.8, 1.2), "R1")
                + G("p4<p2", lambda x: x[2] - x[4]) + G("p2<p1", lambda x: x[1] - x[2]) + G("c0<p2", lambda x: x[2] - x[c]))
    if id == 23:
        return (G("(p4-p3)/2>p2-p3", lambda x: (x[4] - x[3]) / 2 - (x[2] - x[3])) + R(False, 3, 2, 1, (0.8, 1.2), "R1")
                + G("p4>p2", lambda x: x[4] - x[2]) + G("p2>p1", lambda x: x[2] - x[1]) + G("c0>p2", lambda x: x[c] - x[2]))
    if id in (24, 26):
        k = 2 if id == 24 else 1.5
        w1 = (1.2, 2.5) if id == 24 else (0.8, 1.2)
        return (G("(p5-p6)/k>p5-p4", lambda x: (x[5] - x[6]) / k - (x[5] - x[4])) + G("p1<p3", lambda x: x[3] - x[1])
                + R(True, 5, 4, 3, w1, "R1") + R(False, 4, 3, 2, (0.8, 1.2), "R2") + G("c0<p2", lambda x: x[2] - x[c]))
    if id in (25, 27):
        k = 2 if id == 25 else 1.5
        w1 = (1.2, 2.5) if id == 25 else (0.8, 1.2)
        return (G("(p6-p5)/k>p4-p5", lambda x: (x[6] - x[5]) / k - (x[4] - x[5])) + G("p1>p3", lambda x: x[1] - x[3])
                + R(False, 5, 4, 3, w1, "R1") + R(True, 4, 3, 2, (0.8, 1.2), "R2") + G("c0>p2", lambda x: x[c] - x[2]))
    if id in (28, 30):     # the same orderings; 28: ranges p7-p6 > p5-p4 > p3-p2, 30: the reverse
        s = 1.0 if id == 28 else -1.0
        return (G("p8<p6", lambda x: x[6] - x[8]) + G("p6<p4", lambda x: x[4] - x[6]) + G("p4<p2", lambda x: x[2] - x[4])
                + G("p7<p5", lambda x: x[5] - x[7]) + G("p5<p3", lambda x: x[3] - x[5]) + G("p3<p1", lambda x: x[1] - x[3])
                + G("rng76~54", lambda x: s * ((x[7] - x[6]) - (x[5] - x[4])))
                + G("rng54~32", lambda x: s * ((x[5] - x[4]) - (x[3] - x[2]))) + G("c0<p2", lambda x: x[2] - x[c]))
    if id in (29, 31):     # 29: ranges p6-p7 > p4-p5 > p2-p3, 31: the reverse
        s = 1.0 if id == 29 else -1.0
        return (G("p8>p6", lambda x: x[8] - x[6]) + G("p6>p4", lambda x: x[6] - x[4]) + G("p4>p2", lambda x: x[4] - x[2])
                + G("p7>p5", lambda x: x[7] - x[5]) + G("p5>p3", lambda x: x[5] - x[3]) + G("p3>p1", lambda x: x[3] - x[1])
                + G("rng67~45", lambda x: s * ((x[6] - x[7]) - (x[4] - x[5])))
                + G("rng45~23", lambda x: s * ((x[4] - x[5]) - (x[2] - x[3]))) + G("c0>p2", lambda x: x[c] - x[2]))
    if id == 32:
        return (G("pole", lambda x: (x[6] - x[7]) / 1.2 - (x[6] - x[5])) + G("p6>p4", lambda x: x[6] - x[4])
                + G("p4>p2", lambda x: x[4] - x[2]) + G("p5<p3", lambda x: x[3] - x[5]) + G("p3<p1", lambda x: x[1] - x[3])
                + G("c0>p2", lambda x: x[c] - x[2]))
    if id == 33:
        return (G("pole", lambda x: (x[7] - x[6]) / 1.2 - (x[5] - x[6])) + G("p6<p4", lambda x: x[4] - x[6])
                + G("p4<p2", lambda x: x[2] - x[4]) + G("p5>p3", lambda x: x[5] - x[3]) + G("p3>p1", lambda x: x[3] - x[1])
                + G("c0<p2", lambda x: x[2] - x[c]))
    if id in (34, 36):
        tail = (G("(p6-p5)/1.7>p2-p1", lambda x: (x[6] - x[5]) / 1.7 - (x[2] - x[1])) if id == 34 else
                G("pp<maxP", lambda x: (x[6] - x[5]) * 1.2 - (x[2] - x[1]))
                + G("pp>minP", lambda x: (x[2] - x[1]) - (x[6] - x[5]) * 0.8))
        return (G("pole", lambda x: (x[6] - x[7]) / 1.2 - (x[6] - x[5])) + G("p6>p5", lambda x: x[6] - x[5])
                + G("p2>p5", lambda x: x[2] - x[5]) + G("p6>p4", lambda x: x[6] - x[4]) + G("p4>p2", lambda x: x[4] - x[2])
                + G("p5>p3", lambda x: x[5] - x[3]) + G("p3>p1", lambda x: x[3] - x[1]) + tail
                + G("c0>p2", lambda x: x[c] - x[2]))
    if id in (35, 37):
        tail = (G("(p5-p6)/1.7>p1-p2", lambda x: (x[5] - x[6]) / 1.7 - (x[1] - x[2])) if id == 35 else
                G("pp<maxP", lambda x: (x[5] - x[6]) * 1.2 - (x[1] - x[2]))
                + G("pp>minP", lambda x: (x[1] - x[2]) - (x[5] - x[6]) * 0.8))
        return (G("pole", lambda x: (x[7] - x[6]) / 1.2 - (x[5] - x[6])) + G("p6<p5", lambda x: x[5] - x[6])
                + G("p2<p5", lambda x: x[5] - x[2]) + G("p6<p4", lambda x: x[4] - x[6]) + G("p4<p2", lambda x: x[2] - x[4])
                + G("p5<p3", lambda x: x[3] - x[5]) + G("p3<p1", lambda x: x[1] - x[3]) + tail
                + G("c0<p2", lambda x: x[2] - x[c]))
    raise KeyError(id)


SPEC = {i: spec(i) for i in range(38)}


def slacks(id, x):
    return np.array([f(x) for _, f in SPEC[id]])


def height(id, x):
    n = O.ptsOf(id)
    v = list(x[:n]) + ([x[C0]] if id >= 22 else [])
    return max(v) - min(v)


def margin(id, x):
    return float(slacks(id, x).min() / height(id, x))


def only_fails(id, x, tag):
    """True when, in the spec form, exactly the slack ``tag`` is negative and every other one positive."""
    s = slacks(id, x)
    tags = [t for t, _ in SPEC[id]]
    j = tags.index(tag)
    return bool(s[j] < 0 and all(s[k] > 0 for k in range(len(s)) if k != j))


def oracle(id, x):
    q = [float(v) for v in x[:9]] + [float(x[8]), float(x[8])]
    return O.check(id, q, float(x[C0]))


# Harmonic instances from their ratios, in normalised coordinates (s = +1 bearish, -1 bullish).
# Bat:    A = 0, X = s, B = s xb, C = s ac xb, D = s xd   (then BD = (xd - ac xb) / (xb (1 - ac)))
# Shark:  p2 = 0, p3 = -s, p1 = -s r1, p0 = s r1 (r2 - 1), p4 = s(-1 + (r1 (r2 - 1) + 1) / r3)
# AB=CD:  A = 0, B = s, C = s r1, D = s (r1 + r2 (1 - r1))
# 5-0:    p3 = 0, p4 = s, p2 = s r1, p1 = s r1 (1 - r2), p0 = s r1 (1 - r2 + r3 r2), p5 = -s m
# Drives: p3 = 0, p4 = s, p2 = s r1, p1 = s (r1 - k), p0 = s (r1 - k + r2 k)

def harm_points(id, prm):
    """The instance x = (p0..p8, c0) of the ratios ``prm``. Each entry may be an array, and x then has one column per
    candidate."""
    s = 1.0 if id <= 10 else -1.0
    x = np.zeros((10,) + np.shape(prm[0]))
    if id in BAT:
        xb, ac, xd = prm
        x[3], x[4], x[2], x[1], x[0] = 0.0, s, s * xb, s * ac * xb, s * xd
    elif id in SHARK:
        r1, r2, r3 = prm
        x[2], x[3], x[1], x[0] = 0.0, -s, -s * r1, s * r1 * (r2 - 1)
        x[4] = s * (-1 + (r1 * (r2 - 1) + 1) / r3)
    elif id in ABCD:
        r1, r2 = prm
        x[3], x[2], x[1], x[0] = 0.0, s, s * r1, s * (r1 + r2 * (1 - r1))
    elif id in FIVE0:
        r1, r2, r3, m = prm
        x[3], x[4], x[2], x[1] = 0.0, s, s * r1, s * r1 * (1 - r2)
        x[0], x[5] = s * r1 * (1 - r2 + r3 * r2), -s * m
    else:
        r1, r2, k = prm
        x[3], x[4], x[2], x[1], x[0] = 0.0, s, s * r1, s * (r1 - k), s * (r1 - k + r2 * k)
    x[C0] = x[0]
    return x


def inside(w, n=13):
    return list(np.linspace(w[0], w[1], n + 2)[1:-1])


def grid(w, n=13):
    """``n`` uniform points inside the window ``w``, plus points 1e-6, 1e-4, 1e-3 and 1e-2 of its width inside each
    edge: the corners where a nearly dead edge is still live."""
    a, b = w
    d = b - a
    edge = [a + f * d for f in (1e-6, 1e-4, 1e-3, 1e-2)] + [b - f * d for f in (1e-6, 1e-4, 1e-3, 1e-2)]
    return sorted(inside(w, n) + edge)


def harm_params(id):
    """The free parameters of a harmonic id: [(atom tag, window)] plus its extra free values."""
    if id in BAT:
        p = BAT[id]
        ac = win(p, "AC")
        return [("XB", win(p, "XB")), ("AC", (ac[0], min(ac[1], 1.0))), ("XD", win(p, "XD"))], None
    if id in SHARK:
        p = SHARK[id]
        return [("AC", win(p, "AC")), ("BD", win(p, "BD")), ("XD", win(p, "XD"))], None
    if id in ABCD:
        p = ABCD[id]
        return [("AC", win(p, "AC")), ("BD", win(p, "BD"))], None
    if id in FIVE0:
        p = FIVE0[id]
        return [("AC", win(p, "AC")), ("BD", win(p, "BD")), ("CE", win(p, "CE"))], [0.25, 0.5, 1.0]
    p = DRIVES[id]
    return [("AC", win(p, "AC")), ("BD", win(p, "BD"))], [0.25, 0.5, 1.0, 2.0]


def harm_base(id):
    """The instance with the largest smallest normalised margin on a grid inside every window."""
    params, extra = harm_params(id)
    grids = [inside(w) for _, w in params] + ([extra] if extra else [])
    best, bx = -math.inf, None
    for prm in itertools.product(*grids):
        x = harm_points(id, prm)
        m = margin(id, x)
        if m > best:
            best, bx = m, x
    return bx


def _mesh(grids):
    return [g.ravel() for g in np.meshgrid(*[np.asarray(v, float) for v in grids], indexing="ij")]


def harm_negative(id, tag):
    """
    A just-outside negative for the condition ``tag`` (e.g. "XB:lo"), built in ratio space. The ratio is set a
    fraction delta (1e-2, then 1e-3, then 1e-4) of its window's width beyond the edge. The other free parameters run
    over ``grid`` inside their windows. The ratio that the others determine (BD of the Bat family, p4 of the Shark)
    is solved for. The first delta with a candidate where only ``tag`` fails returns the one with the largest margin
    elsewhere; None when none exists.
    """
    params, extra = harm_params(id)
    names = [a for a, _ in params]
    atom, side = tag.split(":") if ":" in tag else (tag, "")
    tags = [t for t, _ in SPEC[id]]
    j_tag = tags.index(tag)
    for delta in (1e-2, 1e-3, 1e-4):
        def out(w):
            return w[0] - delta * (w[1] - w[0]) if side == "lo" else w[1] + delta * (w[1] - w[0])
        if atom in names:
            j = names.index(atom)
            w = win(BAT[id], "AC") if (id in BAT and atom == "AC") else params[j][1]  # AC's own edge, even >= 1
            grids = [[out(w)] if i == j else grid(params[i][1]) for i in range(len(params))] + ([extra] if extra else [])
            x = harm_points(id, _mesh(grids))
        elif id in BAT and atom == "BD":                     # BD follows from the others: solve for XD
            xb, ac = _mesh([grid(params[0][1]), grid(params[1][1])])
            bd = out(win(BAT[id], "BD"))
            x = harm_points(id, (xb, ac, ac * xb + bd * xb * (1 - ac)))
        elif id in SHARK and tag in ("p4>p2", "p4<p2"):      # p4 beyond p2 <=> r1 (r2 - 1) + 1 > r3
            r1, r2 = _mesh([grid(params[0][1]), grid(params[1][1])])
            x = harm_points(id, (r1, r2, (r1 * (r2 - 1) + 1) * (1 + delta)))
        elif id in FIVE0 and tag in ("p5<p3", "p5>p3"):      # p5 on the wrong side of p3: m < 0
            x = harm_points(id, _mesh([inside(w, 7) for _, w in params] + [[-delta]]))
        else:
            return None
        sl = slacks(id, x)                                   # (n slacks, candidates)
        others = np.delete(sl, j_tag, axis=0)
        ok = (sl[j_tag] < 0) & (others > 0).all(axis=0)
        if ok.any():
            n = O.ptsOf(id)
            h = x[:n].max(axis=0) - x[:n].min(axis=0)
            m = np.where(ok, others.min(axis=0) / h, -np.inf)
            return x[:, int(np.argmax(m))].copy()
    return None


def bat_dead_edges(id):
    """
    The window edges of a Bat-family id that no instance can cross while every other condition holds. The free
    ratios are (xb, ac, bd) in their windows, with ac < 1 because BD's orientation needs C short of B, and
    xd = xb (ac + bd (1 - ac)) must fall in the XD window. xd is multilinear in (xb, ac, bd), so its range over a box,
    or over a face of it, is spanned by the vertices. An edge of XB / AC / BD is live when xd's range on that face
    meets the open XD window. An XD edge is live when it lies strictly inside xd's range over the box. AC's upper edge
    is dead whenever it is >= 1.
    """
    p = BAT[id]
    XB, AC, BD, XD = (win(p, k) for k in ("XB", "AC", "BD", "XD"))
    ac_hi = min(AC[1], 1.0)

    def rng(xbs, acs, bds):
        v = [a * (b + c * (1 - b)) for a in xbs for b in acs for c in bds]
        return min(v), max(v)

    xbs, acs, bds = list(XB), [AC[0], ac_hi], list(BD)
    faces = {"XB:lo": ([XB[0]], acs, bds), "XB:hi": ([XB[1]], acs, bds), "AC:lo": (xbs, [AC[0]], bds),
             "BD:lo": (xbs, acs, [BD[0]]), "BD:hi": (xbs, acs, [BD[1]])}
    dead = set()
    if AC[1] < 1.0:
        faces["AC:hi"] = (xbs, [AC[1]], bds)
    else:
        dead.add("AC:hi")
    for tag, f in faces.items():
        lo, hi = rng(*f)
        if not (hi > XD[0] and lo < XD[1]):
            dead.add(tag)
    lo, hi = rng(xbs, acs, bds)
    for tag, edge in (("XD:lo", XD[0]), ("XD:hi", XD[1])):
        if not lo < edge < hi:
            dead.add(tag)
    return dead, (lo, hi)


# Chart patterns: hand-built instances x = (p0, ..., p8, c0). p0 is never read (spec B1.5); it is set to a value
# beyond the breakout. Each satisfies its predicate with every slack worked out in test_trap_38_predicates...
CHART = {
    22: [50, 100, 70, 100, 0, 90, 10, 80, 20, 60],       # (100-0)/2=50 > 30; r=(100-70)/(100-70)=1; c0 60 < 70
    23: [150, 0, 30, 0, 100, 10, 90, 20, 80, 40],        # mirror: (100-0)/2=50 > 30; r=1; c0 40 > 30
    24: [50, 100, 70, 125.5, 70, 100, 0, 90, 10, 60],    # 50 > 30; head r=(125.5-70)/30=1.85; r2=1; 100<125.5
    25: [150, 100, 130, 74.5, 130, 100, 200, 110, 190, 140],
    26: [50, 98, 70, 100, 70, 100, 0, 90, 10, 60],       # 100/1.5=66.7 > 30; r1=1; r2=1; 98 < 100
    27: [150, 102, 130, 100, 130, 100, 200, 110, 190, 140],
    28: [28, 109, 30, 107, 20, 104, 10, 100, 0, 25],     # lows 0<10<20<30, highs 100<104<107<109, 90>84>77
    29: [172, 91, 170, 93, 180, 96, 190, 100, 200, 175],
    30: [28, 160, 30, 135, 20, 115, 10, 100, 0, 25],     # ranges 90 < 95 < 105
    31: [172, 40, 170, 65, 180, 85, 190, 100, 200, 175],
    32: [85, 80, 90, 75, 95, 70, 100, 0, 50, 92],        # pole 100/1.2=83.3 > 30; highs 100>95>90; lows 70<75<80
    33: [115, 120, 110, 125, 105, 130, 100, 200, 150, 108],
    34: [80, 77.5, 88, 78, 95, 80, 100, 0, 50, 89],      # (100-80)/1.7=11.76 > 88-77.5=10.5
    35: [120, 122.5, 112, 122, 105, 120, 100, 200, 150, 111],
    36: [80, 76, 96, 78, 98, 80, 100, 0, 50, 97],        # pp=20 in (16, 24)
    37: [120, 124, 104, 122, 102, 120, 100, 200, 150, 103],
}

# Conditions that can never fail alone, because the other conditions imply them (proofs in each comment).
REDUNDANT = {
    6: {"p4>p3"},                 # it IS the XD orientation of inR(true, p4, p3, ...) (L305)
    17: {"p4<p3"},                # it IS the XD orientation of inR(false, p4, p3, ...)
    9: {"p5<p4"},                 # p5 < p3 and p3 < p4 (AC orientation of inR(true, p4, p3, ...))
    20: {"p5>p4"},                # p5 > p3 and p3 > p4
    22: {"p4<p2", "p2<p1"},       # (p3-p4)/2 > p3-p2 <=> p2 > (p3+p4)/2; with p2 < p3 (R1) that gives p4 < p2;
                                  # R1: p1 > p2 + 0.8 (p3 - p2) > p2
    23: {"p4>p2", "p2>p1"},       # the mirror
    28: {"p6<p4", "p4<p2"},       # p5-p4 > p3-p2 <=> p2-p4 > p3-p5 > 0; p7-p6 > p5-p4 <=> p4-p6 > p5-p7 > 0
    29: {"p6>p4", "p4>p2"},       # the mirror
    30: {"p7<p5", "p5<p3"},       # p7-p6 < p5-p4 <=> p5-p7 > p4-p6 > 0; p5-p4 < p3-p2 <=> p3-p5 > p2-p4 > 0
    31: {"p7>p5", "p5>p3"},       # the mirror
    34: {"p6>p5"},                # p6 > p4 > p2 > p5
    35: {"p6<p5"},                # p6 < p4 < p2 < p5
    36: {"p6>p5"},                # p6 > p4 > p2 > p5
    37: {"p6<p5"},                # p6 < p4 < p2 < p5
}


# Ratios that never decide: Bull Butterfly XD 0.2-3.5 contains the 0.382-1.212 its XB, AC and BD allow; Bull Crab
# XD 0.2-2.5 contains 0.482-1.662 (bat_dead_edges' range).
IDLE_RATIOS = {13: {"XD"}, 14: {"XD"}}


def coefs(f):
    z = np.zeros(10)
    return np.array([f(np.eye(10)[v]) - f(z) for v in range(10)])


def relax(A, b, x0, iters=20000, lam=1.5):
    """A point with A x >= b, by over-relaxed projections onto the most violated row (Agmon-Motzkin); None when
    none is found within ``iters``. It is used only on the chart patterns, whose regions are not thin."""
    nrm = np.linalg.norm(A, axis=1)
    An, bn = A / nrm[:, None], b / nrm
    x = np.array(x0, float)
    for _ in range(iters):
        r = An @ x - bn
        i = int(np.argmin(r))
        if r[i] >= 0:
            return x
        x = x + lam * (-r[i]) * An[i]
    return None


def chart_negative(id, tag, eps=0.002, m=1e-4):
    """A point where only ``tag`` fails, by between eps and 2 eps of the pattern's height, and every other slack
    holds with margin m (all slacks are linear); None when the relaxation finds none."""
    b0 = np.array(CHART[id], float)
    H = height(id, b0)
    rows = [(t, coefs(f)) for t, f in SPEC[id]]
    A, bb = [], []
    for t, a in rows:
        if t == tag:
            A += [-a, a]
            bb += [eps * H, -2 * eps * H]
        else:
            A.append(a)
            bb.append(m * H * np.linalg.norm(a))
    for v in range(10):
        e = np.eye(10)[v]
        A += [e, -e]
        bb += [b0[v] - 20 * H, -(b0[v] + 20 * H)]
    return relax(np.array(A), np.array(bb), b0)


_NEG = {}


def negative(id, tag):
    """The just-outside negative of ``tag`` for ``id`` (cached; None when none exists)."""
    if (id, tag) not in _NEG:
        _NEG[id, tag] = harm_negative(id, tag) if id <= 21 else chart_negative(id, tag)
    return _NEG[id, tag]


# ───────────────────────────── 1. the traps (spec B6 "Risks"), one test each ─────────────────────────────

def test_trap_144_constants_parsed_not_retyped_and_bullish_not_mirror_of_bearish():
    # the generated table: 144 constants in min/max pairs (min < max), each used by exactly one harmonic case
    assert len(O.RATIOS) == 144 and len(O.NAMES) == 38 and sorted(O.HARMONIC_CALLS) == list(range(22))
    assert all(k.endswith(("_min", "_max")) for k in O.RATIOS)
    for k in O.RATIOS:
        if k.endswith("_min"):
            assert O.RATIOS[k] < O.RATIOS[k[:-4] + "_max"], k
    used = sorted(a for _, _, args in O.HARMONIC_CALLS.values() for a in args)
    assert used == sorted(O.RATIOS)
    # values the specification quotes from the source (B1.4), an independent read of the same lines
    assert win("Bearish_Gartley", "XD") == (1.618, 2.618) and win("Bearish_Gartley", "BD") == (2.618, 3.618)
    assert win("Bullish_Gartley", "XD") == (0.2, 2.5)
    assert win("Bearish_Bat", "XD") == (0.3, 1.8) and win("Bullish_Bat", "XD") == (0.5, 2.5)
    # bullish is not the mirror of bearish: most window pairs differ
    # (by family, bearish against bullish: Bat 4, ALT Bat 5, Butterfly 7, Crab 8, Gartley 8, Deep Crab 7, Shark 0,
    # AB=CD 0, ALT AB=CD 2, 5-0 0, Three Drives 2 of the 72 constants differ)
    pairs = [k for k in O.RATIOS if k.startswith("Bearish")]
    differ = [k for k in pairs if O.RATIOS[k] != O.RATIOS["Bullish" + k[len("Bearish"):]]]
    assert len(pairs) == 72 and len(differ) == 43
    # the bullish ALT AB=CD has the AB=CD's windows: id 19 always hits with 18 and is never the first hit
    assert win("Bullish_ALT_Trend", "AC") == win("Bullish_Trend", "AC")
    assert win("Bullish_ALT_Trend", "BD") == win("Bullish_Trend", "BD")
    assert win("Bearish_ALT_Trend", "BD") != win("Bearish_Trend", "BD")
    # a hand case: a bearish Bat with XD = 0.4 (inside the bearish 0.3-1.8, below the bullish 0.5)
    #   X = 200, A = 100, B = 150 (XB 0.5), C = 120 (AC 0.4), D = 140 (BD (140-120)/(150-120) = 0.667, XD 0.4)
    bear = Qv(140, 120, 150, 100, 200)
    assert O.check(0, bear, 0.0)
    # its mirror (300 - x) has the same four ratios, but XD 0.4 is not in the bullish window: no Bull Bat
    #   inR(false, X=100, A=200, 0.5, 2.5, D=160): 160 < 200 - (200 - 100) * 0.5 = 150 is false
    mirror = Qv(160, 180, 150, 200, 100)
    assert not O.check(11, mirror, 0.0)
    assert not O.inR(False, 100.0, 200.0, 0.5, 2.5, 160.0) and O.inR(True, 200.0, 100.0, 0.3, 1.8, 140.0)


def test_trap_38_predicates_transcribed_mechanically_and_strict():
    # Strictness at the exact boundary, with the boundary computed by the script's own expression:
    # inR's lower bound (A - B) * mn + B and upper bound (A - B) * mx + B are both excluded.
    A, B = 10.0, 0.0
    assert not O.inR(True, A, B, 0.382, 0.886, (A - B) * 0.382 + B)
    assert not O.inR(True, A, B, 0.382, 0.886, (A - B) * 0.886 + B)
    assert not O.inR(False, B, A, 0.382, 0.886, A - (A - B) * 0.382)
    # chart comparisons at equality are false: Double Top with c0 = p2, then with (p3 - p4)/2 = p3 - p2
    assert O.pcDoubleTop(Qv(50, 100, 70, 100, 0), 69.0) and not O.pcDoubleTop(Qv(50, 100, 70, 100, 0), 70.0)
    assert not O.pcDoubleTop(Qv(50, 100, 50, 100, 0), 40.0)          # (100-0)/2 = 50 = 100-50: not >
    # Bull Flag with pp = p2 - p1 exactly at maxP = (p6 - p5) * 1.2 = 24, then at minP = 16
    assert O.pcBullFlag(Qv(80, 76, 96, 78, 98, 80, 100, 0), 97.0)
    assert not O.pcBullFlag(Qv(80, 72, 96, 78, 98, 80, 100, 0), 97.0)   # pp = 24
    assert not O.pcBullFlag(Qv(80, 76, 92, 78, 98, 80, 100, 0), 97.0)   # pp = 92 - 76 = 16 = minP

    # Per id: an instance inside every window, and a just-outside negative for every condition that can fail alone.
    for id in range(38):
        if id == 4:
            continue                                            # Bear Gartley: no instance exists (below)
        x = harm_base(id) if id <= 21 else np.array(CHART[id], float)
        assert margin(id, x) > 0, (id, margin(id, x))
        assert oracle(id, x), f"id {id}: the instance inside every window must hit"
        missing = set()
        for tag, _ in SPEC[id]:
            if tag.endswith(":orient"):
                continue
            neg = negative(id, tag)
            if neg is None:
                missing.add(tag)
                continue
            assert only_fails(id, neg, tag), (id, tag)
            assert not oracle(id, neg), f"id {id}: just outside {tag} must not hit"
        expected = set(REDUNDANT.get(id, set()))
        if id in BAT:
            expected |= bat_dead_edges(id)[0]
        assert missing == expected, (id, sorted(missing), sorted(expected))
        # every ratio has a side that a just-outside negative crosses, except a ratio whose window contains every
        # value the other windows allow (then it never decides anything)
        ratios = {t.split(":")[0] for t, _ in SPEC[id] if ":" in t}
        idle = {r for r in ratios if {r + ":lo", r + ":hi"} <= missing}
        assert idle == IDLE_RATIOS.get(id, set()), (id, sorted(idle))
        for r in idle:
            lo, hi = bat_dead_edges(id)[1]
            assert win(BAT[id], r)[0] <= lo and hi <= win(BAT[id], r)[1], (id, r, lo, hi)

    # The Bear Gartley (id 4) can never fire. Its largest XD is at xb max, ac min, bd max:
    # 0.618 * (0.382 + 3.618 * (1 - 0.382)) = 1.61788, short of its XD minimum 1.618 (bat_dead_edges' range).
    lo, hi = bat_dead_edges(4)[1]
    assert hi < O.RATIOS["Bearish_Gartley_XD_min"] and abs(hi - 1.617877032) < 1e-9
    corner = harm_points(4, (0.6179, 0.3821, 0.6179 * (0.3821 + 3.6179 * (1 - 0.3821))))
    assert not oracle(4, corner)


def test_trap_orientation_of_inR_and_predicates_28_33_not_fixed():
    # inR, the specification's cases (B6 "Test cases"): orientation and strictness
    assert O.inR(True, 10.0, 0.0, 0.382, 0.886, 5.0)          # r = 0.5
    assert not O.inR(True, 10.0, 0.0, 0.382, 0.886, 9.0)      # r = 0.9 > 0.886
    assert not O.inR(True, 0.0, 10.0, 0.382, 0.886, 5.0)      # A, B swapped: the window is empty
    assert not O.inR(True, 10.0, 0.0, 0.382, 0.886, 3.82)     # 3.82 <= (10 - 0) * 0.382 + 0 in doubles
    assert O.inR(False, 0.0, 10.0, 0.382, 0.886, 5.0)         # bull: A < B, r = (5 - 10)/(0 - 10) = 0.5
    assert not O.inR(False, 10.0, 0.0, 0.382, 0.886, 5.0)     # bull with A > B: empty
    # Predicates 28-33 never say which swings are highs, so each passes with both alternations. In "even = lows",
    # p0 (D) is a low; in "even = highs", D is a high. Both are ported literally, with no high/low check added.
    normal = {28: CHART[28], 29: CHART[29], 30: CHART[30], 31: CHART[31], 32: CHART[32], 33: CHART[33]}
    shifted = {
        # 28: even = highs 100<110<120<130, odd = lows 0<5<12<20; p7-p6=-110 > p5-p4=-115 > p3-p2=-118; c0 125<130
        28: [0, 20, 130, 12, 120, 5, 110, 0, 100, 125],
        # 29: even = lows 100>90>80>70, odd = highs 210>205>201>198; -120 > -125 > -131; c0 75 > 70
        29: [0, 198, 70, 201, 80, 205, 90, 210, 100, 75],
        # 30: even = highs 100<110<120<130, odd = lows 0<12<26<42; -110 < -108 < -104; c0 125 < 130
        30: [0, 42, 130, 26, 120, 12, 110, 0, 100, 125],
        # 31: even = lows 100>90>80>70, odd = highs 210>198>184>168; -120 < -118 < -114; c0 75 > 70
        31: [0, 168, 70, 184, 80, 198, 90, 210, 100, 75],
        # 32: even = lows 50>45>40, odd = highs 60<65<70, p7 = 55: (50-55)/1.2 = -4.17 > 50-60 = -10; c0 45 > 40
        32: [0, 70, 40, 65, 45, 60, 50, 55, 0, 45],
        # 33: the mirror (200 - x) of 32's: (145-150)/1.2 = -4.17 > 140-150 = -10; 150<155<160; 140>135>130
        33: [0, 130, 160, 135, 155, 140, 150, 145, 0, 155],
    }
    for id in range(28, 34):
        xn, xs = np.array(normal[id], float), np.array(shifted[id], float)
        even_n = xn[2] > xn[1]                       # is p2 above p1 (even swings the highs)?
        even_s = xs[2] > xs[1]
        assert even_n != even_s, id                  # the two cases really use opposite alternations
        assert oracle(id, xn) and oracle(id, xs), id
        assert margin(id, xn) > 0 and margin(id, xs) > 0, id


def test_trap_first_hit_order():
    # Q = D 5, C 104, B 60, A 100, X 0 (+ 50, 40, 45, 35, 48, 30), c0 = 5:
    # - Bull Shark (17): (104-60)/(100-60) = 1.1 in (1, 3.618); (5-104)/(60-104) = 2.25 in (1, 3.24);
    #   (5-100)/(0-100) = 0.95 in (0.886, 2.13); X 0 < A 100 and X 0 < B 60.
    # - Double Top (22): (100-0)/2 = 50 > 100-60 = 40; (104-60)/(100-60) = 1.1 in (0.8, 1.2); 0 < 60 < 104; c0 5 < 60.
    # - ids 0-10 need D high (orientation); 11-16, 18, 19: AC = (104-100)/(60-100) = -0.1 < 0.182; 20: (60-100)/
    #   (0-100) = 0.4 < 1; 21: 0.4 < 1; 23-37 fail on p1..p8 (23: -50 > -40 false; 24, 26: (p5-p6)/k < 50;
    #   25, 27: inR orientation 50 < 0 false; 28, 30: 40 < 0 false; 29, 31: 35 > 40 false; 32: 0 > 60 false;
    #   33, 35, 37: the pole (45-40)/1.2 > 10 false; 34, 36: 40 > 50 false).
    q = Qv(5, 104, 60, 100, 0, 50, 40, 45, 35, 48, 30)
    assert O.detect(q, 5.0) == [17, 22]
    assert O.dirOf(17) == 1 and O.dirOf(22) == -1
    # The same swings through the zigzag. The 12th swing (the high 50) is added at bar 57, the 3rd bar of the last
    # leg: 32 is the highest of 24.8, 5, 14, 23, 32. At that bar the bullish harmonic leads, so the script draws,
    # names and alerts a BULLISH pattern, while a bearish Double Top holds on the same swings (L783, L793-794).
    px, ext = legs([30, 48, 35, 45, 40, 50, 0, 100, 60, 104, 5, 50])
    r = run(px)
    assert swing_list(r) == [(b, float(p)) for b, p in zip(ext, [30, 48, 35, 45, 40, 50, 0, 100, 60, 104, 5, 50])]
    c = rows_of(r, "confirmed", t_bar=57)
    assert c["id"].tolist() == [17, 22] and c["first_hit"].tolist() == [True, False]
    assert c["dir"].tolist() == [1, -1] and c["kind"].tolist() == ["harmonic", "chart"]
    assert c["n_hits"].tolist() == [2, 2] and c["c0"].tolist() == [5.0, 5.0]
    assert len(r["confirmed"]) == 2


# The swings of the gate, forming and overlap tests (oldest first). s7..s10 (100, 200, 140, 230) are a Bear AB=CD
# with D = s10: AC = (140-100)/(200-100) = 0.4 in (0.382, 0.886), BD = (230-140)/(200-140) = 1.5 in (1.13, 2.618)
# and in ALT's (1.27, 1.618). s7..s11 (D = 50) are a Bull Shark: AC = (230-140)/(200-140) = 1.5,
# BD = (50-230)/(140-230) = 2 in (1, 3.24), XD = (50-200)/(100-200) = 1.5 in (0.886, 2.13), 100 < 200, 100 < 140.
GATE_POINTS = [150, 250, 160, 240, 170, 230, 100, 200, 140, 230, 50, 120]


def test_trap_size_gates_12_confirmed_11_forming():
    px, ext = legs(GATE_POINTS)
    assert ext == [4, 9, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59]
    r = run(px)
    assert swing_list(r) == [(b, float(p)) for b, p in zip(ext, GATE_POINTS)]
    ns = r["n_swings"]
    # s10 is added at bar 46 (176 tops 164, 152, 140, 158), s11 at bar 51 (158 under 194, 212, 230, 194),
    # s12 at bar 57 (92 tops 86, 50, 64, 78)
    assert np.flatnonzero(r["added"]).tolist()[-3:] == [46, 51, 57]
    assert ns[45] == 9 and ns[46] == 10 and ns[51] == 11 and ns[57] == 12
    # Forming needs 11 swings. At bars 48-49 (10 swings, the live D at 212 and 230), the script's detection would
    # find the Bear AB=CD: (212-140)/(200-140) = 1.2 is in (1.13, 2.618). The gate keeps it silent.
    sc = script_after(px, px, px, 49)
    assert len(sc.pivP) == 10 and 7 in O.detect(sc.makeQ(0), 230.0)
    assert r["forming"]["t_bar"].min() >= 51 and (ns[r["forming"]["t_bar"].to_numpy()] >= 11).all()
    # Confirmed needs 12. At bar 51 the 11th swing fixes s10 = 230, a Bear AB=CD and ALT AB=CD (7 and 8), but
    # pivP.size() is 11: no confirmed row, no alert.
    sc = script_after(px, px, px, 51)
    assert len(sc.pivP) == 11 and {7, 8} <= set(O.detect(sc.makeQ(1), sc.pivC[1]))
    assert rows_of(r, "confirmed", t_bar=51).empty
    # At bar 57 the 12th swing fixes s11 = 50: the Bull Shark is confirmed and leads (ids 0-16 fail: D is low,
    # and AC = (230-200)/(140-200) = -0.5 for the Bull Bat family).
    c = rows_of(r, "confirmed", t_bar=57)
    assert c["id"].iloc[0] == 17 and bool(c["first_hit"].iloc[0])
    assert c["xs"].iloc[0] == (34, 39, 44, 49, 54) and c["ys"].iloc[0] == (100.0, 200.0, 140.0, 230.0, 50.0)
    assert r["confirmed"]["t_bar"].unique().tolist() == [57]


# Swings of the c0 test: a Double Top X 0 (bar 34), A 100 (39), B = neckline 70 (44), C 98 (49). The bars after
# bar 49 are written by hand.
C0_POINTS = [60, 95, 55, 90, 50, 85, 0, 100, 70, 98]


def c0_bars(variant):
    px, ext = legs(C0_POINTS)
    assert ext[-4:] == [34, 39, 44, 49]
    h, l, c = list(px), list(px), list(px)
    tail = [(90, 90, 90),                      # 50: no swing (81.2 is lower)
            (80, 80, 80),                      # 51: the lowest of the last 5 -> swing 11, a low (n = 11)
            (72, 72, 72),                      # 52: the live low moves to 72
            (66, 66, 66),                      # 53: to 66, close 66 < 70
            (76, 50, 75 if variant == "A" else 55),   # 54: low 50 (the final D), close 75 (A) or 55 (B)
            (70, 60, 62),                      # 55: inside: no swing; close 62 < 70
            (78, 64, 65 if variant == "A" else 77)]   # 56: 78 tops 72, 66, 76, 70 -> swing 12 (n = 12): confirmation
    for hh, ll, cc in tail:
        h.append(float(hh))
        l.append(float(ll))
        c.append(float(cc))
    return np.array(h), np.array(l), np.array(c)


def test_trap_c0_is_pivC1_for_confirmed_and_close_for_forming():
    # Double Top with p1 = 98, p2 = 70, p3 = 100, p4 = 0: (100-0)/2 = 50 > 30; (98-70)/(100-70) = 0.933 in (0.8,1.2);
    # 0 < 70 < 98; the breakout is c0 < 70.
    for variant in ("A", "B"):
        h, l, c = c0_bars(variant)
        r = O.patterns(h, l, c)
        assert swing_list(r)[-3:] == [(49, 98.0), (54, 50.0), (56, 78.0)]
        assert np.flatnonzero(r["added"]).tolist()[-2:] == [51, 56]
        # CONFIRMED at bar 56 reads c0 = pivC[1] = the close of the D bar (54): 75 in A, 55 in B. The close of the
        # confirmation bar itself (65 in A, 77 in B) would give the opposite answer in both variants.
        conf = rows_of(r, "confirmed", t_bar=56)
        if variant == "A":
            # nothing else can hit these swings (Q = 50, 98, 70, 100, 0, 85, 50, 90, 55, 95, 60): every bullish
            # harmonic fails AC (Bat family (98-100)/(70-100) = 0.07, Shark 0.93 < 1, AB=CD 0.07) or its first
            # ratio (5-0, Drives: 0.3 < 1), and every other chart predicate fails an ordering
            assert conf.empty
        else:
            assert conf["id"].tolist() == [22] and conf["c0"].tolist() == [55.0]
        sc = script_after(h, l, c, 56)
        assert O.check(22, sc.makeQ(1), float(c[56])) == (variant == "A")   # the other reading flips both
        # FORMING reads the close of each bar: with D live, the Double Top shows at the closes below 70
        f = rows_of(r, "forming", id=22)
        want = [53, 55] if variant == "A" else [53, 54, 55]          # A: bar 54 closes at 75 > 70
        assert f["t_bar"].tolist() == want
        assert f["c0"].tolist() == [float(c[t]) for t in want]
        # at bar 55 pivC[0] (the close of the D bar 54) is 75 in A, and the row is there because close 62 < 70
        assert f["d_bar"].tolist() == [53] + [54] * (len(want) - 1)
        # the plan: h = |98 - 70| = 28, entry p2 = 70, sl = 70 + 0.5*28 = 84, tp1 = 42, tp2 = 70 - 1.618*28
        row = f.iloc[0]
        assert (row["entry"], row["sl"], row["tp1"]) == (70.0, 84.0, 42.0)
        assert row["tp2"] == pytest.approx(70.0 - 1.618 * 28.0, abs=1e-12)


def test_trap_zigzag_highs_first_and_guard_on_lows_only():
    # bars (high, low, close); depth 5
    bars = [(20, 19, 19.5), (19, 18, 18.5), (18, 17, 17.5), (17, 16, 16.5),
            (16, 15, 15.5),     # 4: the lowest of 0-4 -> swing low 15 (zdir -1); 20 (bar 0) is the highest
            (21, 14, 20),       # 5: OUTSIDE bar, zdir -1: the high branch runs first and unshifts the high 21;
                                #    then zdir = 1 and pivB[0] == 5 blocks the low 14 (lower than the swing low 15)
            (22, 13, 21),       # 6: OUTSIDE bar, zdir 1, higher high: the swing high moves to 22 (pivB[0] := 6);
                                #    the guard blocks the low 13 again
            (21, 14, 15), (20, 14.5, 15), (19, 15, 16), (18, 15.5, 16),   # 7-10: no swing (22 and 13 dominate)
            (21.5, 12, 13),     # 11: OUTSIDE bar, zdir 1, high 21.5 <= 22: the high branch does nothing; the guard
                                #     passes (pivB[0] = 6), so the bar becomes a swing LOW 12
            (21.5, 13, 21),     # 12: a high tied with bar 11's 21.5 within the window: newest-first -> isHi
            (21.5, 14, 20)]     # 13: tied again; zdir 1 and 21.5 > 21.5 is false: the swing does not move
    h, l, c = (np.array([b[k] for b in bars], float) for k in range(3))
    r = O.patterns(h, l, c)
    sw = r["swings"]
    assert list(zip(sw["bar"], sw["price"], sw["close_at_set"], sw["is_high"])) == [
        (4, 15.0, 15.5, False), (6, 22.0, 21.0, True), (11, 12.0, 13.0, False), (12, 21.5, 21.0, True)]
    assert np.flatnonzero(r["added"]).tolist() == [4, 5, 11, 12]       # bar 6 moved a swing; it added none
    assert r["n_swings"].tolist() == [0, 0, 0, 0, 1, 2, 2, 2, 2, 2, 2, 3, 4, 4]
    # under the other tie reading (R1, the oldest bar wins) bar 12 is not a high: the swing list stops at bar 11
    ro = O.patterns(h, l, c, _ties="oldest")
    assert swing_list(ro) == [(4, 15.0), (6, 22.0), (11, 12.0)]
    # zdir 0 (no swing yet): an outside bar is only a high, and its low is dropped
    h0 = np.array([15, 14, 13, 12, 20], float)
    l0 = np.array([5, 6, 7, 8, 1], float)
    r0 = O.patterns(h0, l0, (h0 + l0) / 2)
    assert swing_list(r0) == [(4, 20.0)] and bool(r0["swings"]["is_high"].iloc[0])
    # na before bar depth-1 (R2): bar 0-3 cannot make a swing even when they are extremes
    assert r0["n_swings"].tolist() == [0, 0, 0, 0, 1]
    assert O.ta_highestbars([1.0, 2.0, 3.0, 4.0], 5) is None and O.ta_highestbars([1.0, 9.0, 3.0, 4.0, 9.0], 5) == 0
    assert O.ta_highestbars([1.0, 9.0, 3.0, 4.0, 9.0], 5, "oldest") == -3
    assert O.ta_lowestbars([5.0, 1.0, 3.0, 1.0, 2.0], 5) == -1 and O.ta_lowestbars([5.0, 1.0, 3.0, 1.0, 2.0], 5, "oldest") == -3


def test_trap_forming_detection_at_every_bar():
    # In the gate test's bars the Bull Shark forms while s11 is live: at bar 53 (live D 86: (86-200)/(100-200) =
    # 1.14 in (0.886, 2.13)), bar 54 (D 50) and bars 55-56 (D stays 50 while price rises). Bar 52 (D 122:
    # XD 0.78 < 0.886) is too early. At bar 57 the next swing fixes D and the instance becomes the confirmed one.
    px, _ = legs(GATE_POINTS)
    r = run(px)
    f = rows_of(r, "forming", id=17)
    assert f["t_bar"].tolist() == [53, 54, 55, 56]
    assert f["d_price"].tolist() == [86.0, 50.0, 50.0, 50.0]          # the live D as it was at each close
    assert f["entry"].tolist() == [86.0, 50.0, 50.0, 50.0]
    assert f["first_bar_of_instance"].tolist() == [True, False, False, False]
    assert set(f["instance_key"]) == {(17, 49, 44, 39, 34)}
    # Forming at bar t = the script's last-bar detection on the bars up to t (L802-813 with the chart ending at t)
    for t in range(48, 60):
        last = O.patterns(px[:t + 1], px[:t + 1], px[:t + 1])["forming"]
        assert same_frame(last[last["t_bar"] == t].reset_index(drop=True),
                          r["forming"][r["forming"]["t_bar"] == t].reset_index(drop=True)), t
    # a forming pattern that vanishes keeps the rows it had: the c0 test's variant A shows the Double Top at bars 53
    # and 55, not 54. The return at 55 is the same instance (R4): its first bar stays 53.
    h, l, c = c0_bars("A")
    fa = rows_of(O.patterns(h, l, c), "forming", id=22)
    assert fa["t_bar"].tolist() == [53, 55] and fa["first_bar_of_instance"].tolist() == [True, False]
    assert set(fa["instance_key"]) == {(22, 49, 44, 39, 34)}


def test_trap_makeQ_index_clamping():
    sc = O.Script()
    sc.pivP = [5.0, 4.0, 3.0]                                  # newest first
    assert sc.makeQ(0) == [5.0, 4.0] + [3.0] * 9               # q[k] = pivP[min(s + k, n - 1)]
    assert sc.makeQ(1) == [4.0] + [3.0] * 10
    sc.pivP = [float(v) for v in range(11, 0, -1)]             # 11 swings: 11, 10, ..., 1
    assert sc.makeQ(1)[9] == sc.makeQ(1)[10] == 1.0            # with s = 1 the clamp would bind at 11 swings...
    assert sc.makeQ(0) == sc.pivP                              # ...but the forming gate (>= 11) needs no clamp
    sc.pivP = [float(v) for v in range(12, 0, -1)]
    assert sc.makeQ(1) == sc.pivP[1:12]                        # and the confirmed gate (>= 12) needs none either
    sc.pivP = []
    with pytest.raises(IndexError):                            # Pine: array.get out of bounds (unreachable)
        sc.makeQ(0)
    # The clamp could only touch Q9 and Q10, and no predicate reads past P[8], so they never change a detection
    rng = np.random.default_rng(5)
    for _ in range(3000):
        q = list(rng.uniform(0, 100, 11))
        c0 = float(rng.uniform(0, 100))
        q2 = q[:9] + [float(rng.uniform(0, 100)), float(rng.uniform(0, 100))]
        assert O.detect(q, c0) == O.detect(q2, c0)


def test_trap_Q3_of_the_5_0():
    # A Bear 5-0 (id 9): p5 95, p4 110, p3 100, p2 120, p1 80, p0 140 (Q order).
    #   AC = (120-100)/(110-100) = 2 in (1, 3.618); BD = (80-120)/(100-120) = 2 in (1, 3.24);
    #   CE = (140-80)/(120-80) = 1.5 in (0.886, 2.13); p5 95 < p4 110 and < p3 100.
    q = Qv(140, 80, 120, 100, 110, 95)
    assert O.check(9, q, 0.0) and O.ptsOf(9) == 6
    # The plan reads Q3 (L703), whatever the pattern: here Q3 = 100, the point the 6-point drawing labels "B"
    # (labels "XABCDE" oldest first, L658). AD = |100 - 140| = 40, dir -1: sl = 140 + 0.13*40 = 145.2,
    # tp1 = 140 - 0.382*40 = 124.72, tp2 = 140 - 0.618*40 = 115.28. "A" (Q4 = 110) would give AD 30 and sl 143.9.
    e, sl, t1, t2, zl, zh = O.planLevels(9, q)
    assert e == 140.0
    assert sl == pytest.approx(145.2, abs=1e-12) and t1 == pytest.approx(124.72, abs=1e-12)
    assert t2 == pytest.approx(115.28, abs=1e-12)
    assert (zl, zh) == pytest.approx((140.0 - 2.4, 140.0 + 2.4), abs=1e-12)
    assert abs(sl - 143.9) > 1.0
    # the bullish 5-0 the same way: the mirror (300 - x), dir +1, AD = 40
    e, sl, t1, t2, _, _ = O.planLevels(20, Qv(160, 220, 180, 200, 190, 205))
    assert O.check(20, Qv(160, 220, 180, 200, 190, 205), 0.0)
    assert (e, sl, t1, t2) == pytest.approx((160.0, 154.8, 175.28, 184.72), abs=1e-12)


# The overlap test's swings: the gate test's patterns two swings later (so both pass the gate). s8 = 210 keeps
# the Bat family out at the AB=CD (XB = (200-100)/(210-100) = 0.909, beyond every bearish XB window), and the Bear
# Shark needs (140-200)/(100-200) = 0.6 > 1: so the Bear AB=CD (7) leads at bar 61 and the Bull Shark (17) at bar 67.
OVERLAP_POINTS = [150, 250, 160, 240, 170, 260, 180, 210, 100, 200, 140, 230, 50, 120]


def test_trap_overlap_gate_does_not_gate_alerts():
    px, ext = legs(OVERLAP_POINTS)
    assert ext[-6:] == [44, 49, 54, 59, 64, 69]
    r = run(px)
    first = r["confirmed"][r["confirmed"]["first_hit"]].reset_index(drop=True)
    assert first["t_bar"].tolist()[-2:] == [61, 67] and first["id"].tolist()[-2:] == [7, 17]
    assert first["xs"].iloc[-2] == (44, 49, 54, 59) and first["xs"].iloc[-1] == (44, 49, 54, 59, 64)
    # overlaps (L767-777): lo = max(44, 44) = 44, hi = min(64, 59) = 59, len = min(20, 15) = 15, 15 / 15 > 0.5:
    # the Shark is not drawn (L785). Its alert (bullConf, L793) and its row are there all the same.
    drawn = O.drawn_mask(r["confirmed"])
    assert len(drawn) == len(first) and drawn.tolist()[-2:] == [True, False]
    # the gate by hand: a span half covered (ratio 0.5) is drawn, more than half is not; a history of 15 drops the
    # oldest (L790-792)
    df = pd.DataFrame({"t_bar": [1, 2, 3], "first_hit": [True] * 3, "xs": [(0, 10), (5, 15), (4, 16)]})
    assert O.drawn_mask(df).tolist() == [True, True, False]   # (10-5)/10 = 0.5 is not > 0.5; (10-4)/10 = 0.6
    df = pd.DataFrame({"t_bar": range(17), "first_hit": [True] * 17,
                       "xs": [(100 * i, 100 * i + 10) for i in range(16)] + [(0, 10)]})
    assert O.drawn_mask(df).tolist() == [True] * 17          # the first pattern left pats after 15 others


# ───────────────────────────── 2. the spec's other test cases ─────────────────────────────

def test_registry_tables_by_hand():
    # dirOf (L117-125): 0-10 bearish, 11-21 bullish, the bearish chart ids 22 24 26 28 30 33 35 37
    assert [O.dirOf(i) for i in range(38)] == [-1] * 11 + [1] * 11 + [-1, 1, -1, 1, -1, 1, -1, 1, -1, 1,
                                                                      1, -1, 1, -1, 1, -1]
    # ptsOf (L128-142): AB=CD 4, 5-0 6, Double Top/Bottom 5, H&S/Triple 7, wedges/triangles 9, the rest 8
    want = [5] * 7 + [4, 4, 6, 5] + [5] * 7 + [4, 4, 6, 5] + [5, 5] + [7] * 4 + [9] * 4 + [8] * 6
    assert [O.ptsOf(i) for i in range(38)] == want
    assert O.NAMES[0] == "Bear Bat" and O.NAMES[21] == "Bull Three Drives" and O.NAMES[37] == "Bear Flag"
    assert [O.kindOf(i) for i in (0, 21, 22, 37)] == ["harmonic", "harmonic", "chart", "chart"]
    assert O.check(38, Qv(), 0.0) is False and O.check(-1, Qv(), 0.0) is False   # "=> false" (L522)


def test_confirmation_bar_is_the_bar_of_the_next_swing():
    # In the c0 test (variant B) the Double Top's D is the low 50 of bar 54. It is confirmed at bar 56, where the
    # next swing (the high 78) appears, and not at bar 54 or 55 although D is already final there. The row's
    # points never move afterwards.
    h, l, c = c0_bars("B")
    r = O.patterns(h, l, c)
    conf = rows_of(r, "confirmed", id=22)
    assert conf["t_bar"].tolist() == [56] and conf["d_bar"].tolist() == [54]
    assert conf["xs"].iloc[0] == (34, 39, 44, 49, 54) and conf["ys"].iloc[0] == (0.0, 100.0, 70.0, 98.0, 50.0)
    # on synthetic bars: every confirmed row sits on an added bar with >= 12 swings, and its D is the swing that
    # was newest just before the addition
    h, l, c = synth(4000, 11)
    r = O.patterns(h, l, c)
    bars = r["swings"]["bar"].to_numpy()
    assert len(r["confirmed"]) > 50
    for t, d in zip(r["confirmed"]["t_bar"], r["confirmed"]["d_bar"]):
        assert r["added"][t] and r["n_swings"][t] >= 12
        j = int(np.searchsorted(bars, d))                          # D's place in the final swing list
        assert bars[j] == d and r["n_swings"][t] == j + 2           # D, then the swing added at t
        assert bars[j + 1] >= t                                     # (which may have moved on after t)


def test_plan_levels_follow_the_swing_points():
    """Every row's levels against its own points: harmonic AD = |Q3 - Q0| (ys[-4], ys[-1]); chart h = |Q1 - Q2|
    and entry = Q2 (ys[-2], ys[-3])."""
    h, l, c = synth(6000, 3)
    r = O.patterns(h, l, c)
    for key in ("confirmed", "forming"):
        df = r[key]
        assert len(df) > 100 and set(df["kind"]) == {"harmonic", "chart"}
        for row in df.itertuples():
            ys, d = row.ys, row.dir
            assert len(ys) == len(row.xs) == row.n_pts and row.xs[-1] == row.d_bar <= row.t_bar
            if row.kind == "harmonic":
                ad = abs(ys[-4] - ys[-1])
                want = (ys[-1], ys[-1] - d * O.SL_K * ad, ys[-1] + d * O.TP1_K * ad, ys[-1] + d * O.TP2_K * ad)
            else:
                ad = abs(ys[-2] - ys[-3])
                want = (ys[-3], ys[-3] - d * O.CSL_K * ad, ys[-3] + d * O.CTP1_K * ad, ys[-3] + d * O.CTP2_K * ad)
            got = (row.entry, row.sl, row.tp1, row.tp2)
            if ad > 0:
                assert got == want
            else:
                assert all(math.isnan(v) for v in got)              # na, as the script (L704, L713)


def test_truncation_invariance():
    """Outputs up to bar T are unchanged when the bars after T are removed (no look-ahead anywhere)."""
    h, l, c = synth(3000, 7)
    full = O.patterns(h, l, c)
    for T in (60, 99, 500, 1234, 2000, 2998):
        part = O.patterns(h[:T + 1], l[:T + 1], c[:T + 1])
        assert np.array_equal(part["n_swings"], full["n_swings"][:T + 1])
        assert np.array_equal(part["added"], full["added"][:T + 1])
        for key in ("confirmed", "forming"):
            a = full[key][full[key]["t_bar"] <= T].reset_index(drop=True)
            assert same_frame(part[key], a), (key, T)
        # the swing list of the cut run is the full run's state after bar T
        sc = script_after(h, l, c, T)
        assert [tuple(s) for s in sc.log] == list(part["swings"].itertuples(index=False, name=None))


def test_start_offset_convergence():
    """Started later, the zigzag meets the full run's swings within a few swings and agrees from then on. The
    events whose swings all lie after the meeting point agree too (spec B1.1: 48-79 bars on real bars)."""
    h, l, c = synth(4000, 21)
    full = O.patterns(h, l, c)
    fs = full["swings"]
    for s in (300, 1000):
        late = O.patterns(h[s:], l[s:], c[s:])
        ls = late["swings"].copy()
        ls["bar"] += s
        a = list(fs[fs["bar"] >= s].itertuples(index=False, name=None))
        b = list(ls.itertuples(index=False, name=None))
        k = next(i for i in range(len(b)) if b[i:] == a[len(a) - len(b) + i:])
        assert b[k][0] - s < 150, (s, b[k][0] - s)
        t_ok = ls["bar"].iloc[k + 12]           # from here every swing a detection reads is a common one
        for key in ("confirmed", "forming"):
            x = full[key][full[key]["t_bar"] >= t_ok].reset_index(drop=True)
            y = late[key].copy()
            y["t_bar"] += s
            y["d_bar"] += s
            y["xs"] = [tuple(v + s for v in xs) for xs in y["xs"]]
            if key == "forming":
                y["instance_key"] = [(kk[0],) + tuple(v + s for v in kk[1:]) for kk in y["instance_key"]]
            y = y[y["t_bar"] >= t_ok].reset_index(drop=True)
            assert same_frame(x, y), (key, s)


# ───────────────────────────── 3. the Pine source (skipped when absent) ─────────────────────────────

def _source():
    cands = [Path(os.environ[SOURCE_ENV])] if os.environ.get(SOURCE_ENV) else []
    cands += [SOURCE_DIR / n for n in SOURCE_NAMES]
    for p in cands:
        if p.is_file():
            return O.read_source(p)
    pytest.skip(f"the Pine source is not on this machine (set {SOURCE_ENV})")


def test_generated_tables_regenerate_from_source():
    text = _source()
    names, ratios, calls, spans = O.generate_tables(text)
    assert tuple(names) == O.NAMES
    assert list(ratios) == list(O.RATIOS) and all(ratios[k][0] == O.RATIOS[k] for k in ratios)
    assert calls == O.HARMONIC_CALLS
    assert spans == {"names": (96, 103), "ratios": (146, 289), "calls": (484, 505)}
    block = O.generated_block(text)
    module = (Path(__file__).resolve().parent / "tradeiq2_oracle_patterns.py").read_text(encoding="utf-8")
    assert block in module


def _split_top(s, sep):
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and s.startswith(sep, i):
            return s[:i], s[i + len(sep):]
    return None


def _expr(s):
    """A Pine expression of the rule region in Python: P.get(k) -> P[k], true/false, and the ternary."""
    s = s.strip()
    t = _split_top(s, " ? ")
    if t is not None:
        cond, rest = t
        a, b = _split_top(rest, " : ")
        return f"(({_expr(a)}) if ({_expr(cond)}) else ({_expr(b)}))"
    s = re.sub(r"P\.get\((\d+)\)", r"P[\1]", s)
    s = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", s))
    assert " ? " not in s and "math." not in s and "na(" not in s, s
    return s


def translate_rules(lines):
    """The functions from ``inR`` to ``check`` (L293-522), mechanically: ``name(params) =>`` and its indented body
    become a ``def``; ``float x = e`` an assignment; the last line the return value; ``switch id`` an if-chain."""
    i0 = next(i for i, s in enumerate(lines) if s.startswith("inR("))
    i1 = next(i for i, s in enumerate(lines) if s.startswith("detect("))
    out, i = [], i0
    while i < i1:
        s = lines[i]
        if not s.strip() or s.lstrip().startswith("//"):
            i += 1
            continue
        m = re.match(r"^(\w+)\((.*)\) =>\s*$", s)
        assert m, (i + 1, s)
        name, params = m.group(1), [p.split()[-1] for p in m.group(2).split(",")]
        body = []
        i += 1
        while i < i1 and lines[i].startswith("    "):
            body.append(lines[i].strip())
            i += 1
        out.append(f"def {name}({', '.join(params)}):")
        if name == "check":
            assert body[0] == "switch id"
            for b in body[1:]:
                m2 = re.match(r"^(\d+)? ?=> (.*)$", b)
                if m2.group(1) is None:
                    out.append(f"    return {_expr(m2.group(2))}")
                else:
                    out.append(f"    if id == {m2.group(1)}: return {_expr(m2.group(2))}")
            continue
        for b in body[:-1]:
            m2 = re.match(r"^(?:float|int|bool) (\w+) = (.*)$", b)
            assert m2, b
            out.append(f"    {m2.group(1)} = {_expr(m2.group(2))}")
        out.append(f"    return {_expr(body[-1])}")
    return "\n".join(out)


def test_rules_equal_a_mechanical_translation_of_the_source():
    lines = O.source_lines(_source())
    ns = {}
    for s in lines:                            # the constants, read again with a regex of this test's own
        m = re.match(r"^(\w+_(?:min|max)) = ([0-9.]+)$", s.strip())
        if m:
            ns[m.group(1)] = float(m.group(2))
    assert len(ns) == 144
    exec(compile(translate_rules(lines), "<pine rules>", "exec"), ns)
    T = ns
    rng = np.random.default_rng(13)
    samples = []
    for id in range(38):
        b = harm_base(id) if id <= 21 else np.array(CHART[id], float)
        samples.append(b)
        H = max(b) - min(b)
        for sc in (1e-6, 1e-4, 1e-3, 1e-2, 0.05, 0.2, 0.5):
            samples += [b + rng.normal(0, sc * H, 10) for _ in range(120)]
        for tag, _ in SPEC[id]:
            if not tag.endswith(":orient") and id != 4:
                neg = negative(id, tag)
                if neg is not None:
                    samples.append(neg)
    samples += [rng.uniform(0, 100, 10) for _ in range(6000)]
    hits = np.zeros(38, int)
    for x in samples:
        q = [float(v) for v in x[:9]] + [float(x[8]), float(x[8])]
        c0 = float(x[C0])
        for id in range(38):
            a = O.check(id, q, c0)
            assert a == T["check"](id, q, c0), (id, list(x))
            hits[id] += a
    assert (np.delete(hits, 4) > 100).all() and hits[4] == 0          # every id exercised; the Bear Gartley never
    # inR at its exact bounds, in both orientations
    for A, B, mn, mx in ((10.0, 0.0, 0.382, 0.886), (0.0, 10.0, 0.382, 0.886), (3.3, 1.1, 1.13, 2.618)):
        for d in ((A - B) * mn + B, (A - B) * mx + B, B - (B - A) * mn, B - (B - A) * mx, (A + B) / 2):
            for bear in (True, False):
                assert O.inR(bear, A, B, mn, mx, d) == T["inR"](bear, A, B, mn, mx, d)


# ───────────────────────────── 5. real bars (skipped without the tick store) ─────────────────────────────

D_START, D_END = "2019-01-01", "2023-01-01"         # Development: bars closing in 2019-2022


@pytest.fixture(scope="module")
def real():
    """1H / 4H / 1D TBars of a symbol from its data start to 2024-06-30 (``end="2024-07-01"``), complete bars only,
    and the oracle's result on each (cached). One symbol is in memory at a time."""
    from backtesting.data import store
    from backtesting.research import tradeiq_market as TM
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            cache.clear()
            mk = TM.load(symbol, end="2024-07-01")
            out = {}
            for tf in ("1H", "4H", "1D"):
                b = mk.tbars(tf)
                keep = b.complete & (b.tc <= TM.CUT_S)
                out[tf] = {"t": b.t[keep], "tc": b.tc[keep], "h": b.h[keep], "l": b.l[keep], "c": b.c[keep]}
                out[tf]["r"] = O.patterns(out[tf]["h"], out[tf]["l"], out[tf]["c"])
            del mk
            cache[symbol] = (TM, out)
        return cache[symbol]

    return get


def _check_contract(r, n, what):
    sw = r["swings"]
    assert list(sw.columns) == list(O.SWING_COLUMNS), what
    assert not sw[["price", "close_at_set"]].isna().any().any(), what
    assert (np.diff(sw["bar"].to_numpy()) > 0).all(), what
    assert (sw["is_high"].to_numpy()[1:] != sw["is_high"].to_numpy()[:-1]).all(), what     # strict alternation
    ns, added = r["n_swings"], r["added"]
    assert len(ns) == len(added) == n and ns[-1] == len(sw), what
    assert np.array_equal(np.diff(np.r_[0, ns]), added.astype(np.int64)), what
    for key, cols in (("confirmed", O.ROW_COLUMNS), ("forming", O.FORMING_COLUMNS)):
        df = r[key]
        assert list(df.columns) == list(cols) and len(df) > 0, (what, key)
        num = ["d_price", "c0", "entry", "sl", "tp1", "tp2"]
        size = np.array([abs(ys[-4] - ys[-1]) if k == "harmonic" else abs(ys[-2] - ys[-3])
                         for k, ys in zip(df["kind"], df["ys"])])
        assert not df.loc[size > 0, num].isna().any().any(), (what, key)          # values exist where AD, h > 0
        assert df.loc[size == 0, ["entry", "sl", "tp1", "tp2"]].isna().all().all(), (what, key)
        assert all(not any(math.isnan(v) for v in ys) for ys in df["ys"]), (what, key)
        assert (df["d_bar"] <= df["t_bar"]).all() and (df["n_pts"] == df["ys"].map(len)).all(), (what, key)
        assert 4 not in set(df["id"]), (what, key)                                  # the Bear Gartley never fires
        g = df.groupby("t_bar")
        assert (g["first_hit"].sum() == 1).all() and (g["id"].first() == g["id"].min()).all(), (what, key)
    gate_c = ns[r["confirmed"]["t_bar"].to_numpy()]
    assert (gate_c >= 12).all() and added[r["confirmed"]["t_bar"].to_numpy()].all(), what
    assert (ns[r["forming"]["t_bar"].to_numpy()] >= 11).all(), what


def test_real_bars_truncation_gold_4h(real):
    TM, out = real("XAUUSDm")
    d = out["4H"]
    r = d["r"]
    T = int(np.searchsorted(d["tc"], TM.s_of("2021-03-01")))
    part = O.patterns(d["h"][:T + 1], d["l"][:T + 1], d["c"][:T + 1])
    for key in ("confirmed", "forming"):
        a = r[key][r[key]["t_bar"] <= T].reset_index(drop=True)
        assert same_frame(part[key], a), key
    assert np.array_equal(part["n_swings"], r["n_swings"][:T + 1])


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    TM, out = real(symbol)
    for tf in ("1H", "4H", "1D"):
        d = out[tf]
        assert int(d["tc"][-1]) <= TM.CUT_S and int(d["t"][-1]) < TM.CUT_S          # nothing from the hold-out
        r = d["r"]
        _check_contract(r, len(d["t"]), f"{symbol} {tf}")
        dev = (d["tc"] > TM.s_of(D_START)) & (d["tc"] <= TM.s_of(D_END))
        bars_per_swing = dev.sum() / max(1, r["added"][dev].sum())
        assert 5.0 < bars_per_swing < 10.0, (symbol, tf, bars_per_swing)          # spec B1.1: about 7
