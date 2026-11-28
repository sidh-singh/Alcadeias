"""
Port A of "Harmonic & Chart Patterns [AI-AlgoCode]" (``backtesting/research/tradeiq2_ind_patterns.py``), study 2.

1. One hand-computed case per trap of the specification's risk list (``maps/ribbon_patterns.md`` B6 "Risks"), named
   after it, ``test_trap01_...`` to ``test_trap11_...``. The zigzag cases are built from bars whose swings are known by
   construction (``zz_bars``: straight legs of 6 bars; the k-th point lands on bar 6k + 5) and checked first; the
   arithmetic is in the comments.
2. Facts of the script found while porting: Bear Gartley can never fire; Bull ALT AB=CD has Bull AB=CD's windows.
3. Properties on synthetic bars: truncation invariance (no look-ahead), a literal bar-by-bar emulation of the Pine
   (newest-first lists with unshift / pop at 60, makeQ, detect) equal to the vectorised port, the compiled zigzag equal
   to its Python body, the output contract, inputs left alone.
4. When the Pine source is on this machine (``TRADEIQ2_PATTERNS_SOURCE`` or the study's scratch copy; skipped
   otherwise): the generated table regenerated from the text, and the 38 predicates transliterated mechanically from
   the text at test time (``P.get(k)`` -> ``P[k]``, ``?:`` -> ``if else``), equal to the port on random, boundary and
   one-ulp sets. The source is read, never copied into the repository.
5. Real bars (skipped when the tick store is absent; bars to 2024-06-30 only, the hold-out is never loaded): a smoke
   check of both symbols on 1H / 4H / 1D (the timeframes PREREG 6.7 uses; the script reads no volume), the literal
   emulation on the daily bars, the start-offset convergence of the spec. Counts only, no profit.
"""

from __future__ import annotations

import gc
import inspect
import math
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_patterns as HP
from backtesting.research import tradeiq_market as TM

nan = math.nan
SOURCE_CANDIDATES = (
    os.environ.get("TRADEIQ2_PATTERNS_SOURCE", ""),
    "/private/tmp/claude-501/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/"
    "scratchpad/study2/src/Harmonic and Chart Patterns Script.txt",
    "/Users/sidharthsingh/Desktop/study/indicator/Harmonic and Chart Patterns Script.txt",
)


# ───────────────────────────── helpers ─────────────────────────────

def same(a, b):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def zz_bars(points, leg=6, w=0.1):
    """Bars whose depth-5 zigzag has exactly the swings ``points`` (alternating highs and lows), point k on bar
    leg*(k+1) - 1: a straight lead-in of ``leg`` bars from the second point's level to the first point, then straight
    legs of ``leg`` bars. Up-leg bars: h = v, l = v - w, c = v - w/2; down-leg bars: h = v + w, l = v, c = v + w/2
    (v on the leg), so each turning bar carries its point exactly and is the extreme of its leg."""
    pts = [float(p) for p in points]
    vals, ups, prev = [], [], pts[1]
    for p in pts:
        for j in range(1, leg + 1):
            vals.append(prev + (p - prev) * j / leg)
            ups.append(p > prev)
        prev = p
    v, up = np.array(vals), np.array(ups)
    return np.where(up, v, v + w), np.where(up, v - w, v), np.where(up, v - w / 2, v + w / 2)


def run_points(points, leg=6, edit=None):
    """patterns() on zz_bars(points) (``edit(h, l, c)`` may change single bars first), with the swings checked."""
    h, l, c = zz_bars(points, leg)
    if edit is not None:
        edit(h, l, c)
    out = HP.patterns(h, l, c)
    sw = out["swings"]
    assert list(sw["price"]) == [float(p) for p in points]
    assert list(sw["bar"]) == [leg * (k + 1) - 1 for k in range(len(points))]
    return out, (h, l, c)


def piv_at(out, t):
    """pivP after bar t, newest first (the live swing's value at t, then the fixed ones)."""
    n = int(out["n_swings"][t])
    fixed = out["swings"]["price"].to_numpy()[:n - 1][::-1]
    return np.concatenate([[out["live_price"][t]], fixed])


def rand_bars(n, seed, decimals=None):
    rng = np.random.default_rng(seed)
    c = 2000.0 + np.cumsum(rng.standard_normal(n))
    h = c + np.abs(rng.standard_normal(n))
    lo = c - np.abs(rng.standard_normal(n))
    if decimals is not None:                         # rounded prices: ties within the 5-bar windows
        h, lo, c = (np.round(x, decimals) for x in (h, lo, c))
        h, lo = np.maximum(h, c), np.minimum(lo, c)
    return h, lo, c


def random_sets(m, seed):
    """m swing sets of 11 (newest first) that alternate strictly, P0 a high or a low at random, with log-normal legs,
    a trend and a converging / diverging amplitude per set, and a close c0 around P2."""
    rng = np.random.default_rng(seed)
    legs = np.exp(rng.normal(0.0, 0.6, (m, 10)))
    drift = rng.normal(0.0, 0.5, (m, 1))
    amp = np.exp(rng.normal(0.0, 0.15, (m, 1)) * np.arange(10)[None, :])
    up0 = rng.random(m) < 0.5
    Q = np.zeros((m, 11))
    Q[:, 10] = 100.0
    for k in range(9, -1, -1):
        hi = (k % 2 == 0) == up0                     # P_k is a high
        step = legs[:, k] * amp[:, k]
        Q[:, k] = Q[:, k + 1] + np.where(hi, step, -step) + 0.5 * drift[:, 0]
    c0 = Q[:, 2] + rng.normal(0.0, 1.0, m) * np.abs(Q[:, 1] - Q[:, 2])
    return Q, c0


def source_text():
    for p in SOURCE_CANDIDATES:
        if p and Path(p).is_file():
            return Path(p).read_text(encoding="utf-8")
    return None


def need_source():
    text = source_text()
    if text is None:
        pytest.skip("the Pine source of the script is not on this machine (set TRADEIQ2_PATTERNS_SOURCE)")
    return text


def _pine_expr(e):
    e = re.sub(r"P\.get\((\d+)\)", r"P[\1]", e)
    e = re.sub(r"\btrue\b", "True", e)
    e = re.sub(r"\bfalse\b", "False", e)
    m = re.match(r"^(\w+) \? \((.*)\) : \((.*)\)$", e)
    if m:
        e = f"(({m.group(2)}) if {m.group(1)} else ({m.group(3)}))"
    assert "?" not in e and ":" not in e, e
    return e


def source_oracle(text):
    """The script's predicates and the cases of ``check``, transliterated from the source text: id -> f(P, c0) on Python
    floats. Rules: the ratio region's ``Name = value`` lines are Python already; each ``name(args) =>`` function of the
    region "Pattern rules" (L293-480) becomes a def (``float x = e`` -> ``x = e``, the last line is returned);
    ``P.get(k)`` -> ``P[k]``, ``true`` / ``false`` -> ``True`` / ``False``, ``c ? (a) : (b)`` -> ``(a) if c else (b)``;
    ``and`` and the arithmetic are the same in both languages (precedence, float division)."""
    lines = text.split("\n")
    a = next(i for i, s in enumerate(lines) if s.startswith("//#region") and "Pattern rules" in s)
    z = next(i for i, s in enumerate(lines) if s.startswith("check(int id"))
    r0 = next(i for i, s in enumerate(lines) if s.startswith("//#region") and "Ratios" in s)
    r1 = next(i for i in range(r0 + 1, len(lines)) if lines[i].startswith("//#endregion"))
    py = [lines[i] for i in range(r0 + 1, r1)]
    i = a + 1
    while i < z:
        s = lines[i]
        if not s.strip():
            i += 1
            continue
        m = re.match(r"^(\w+)\((.*)\) =>$", s)
        assert m, (i + 1, s)
        args = [x.strip().split()[-1] for x in m.group(2).split(",")]
        body = []
        i += 1
        while i < z and lines[i].startswith("    "):
            body.append(lines[i][4:])
            i += 1
        py.append(f"def {m.group(1)}({', '.join(args)}):")
        for b in body[:-1]:
            mm = re.match(r"^float (\w+) = (.*)$", b)
            assert mm, b
            py.append(f"    {mm.group(1)} = {_pine_expr(mm.group(2))}")
        py.append(f"    return {_pine_expr(body[-1])}")
    ns = {}
    exec(compile("\n".join(py), "<pine predicates>", "exec"), ns)
    fns = {}
    j = z + 2
    while lines[j].strip() != "=> false":
        m = re.match(r"^\s+(\d+) => (.*)$", lines[j])
        fns[int(m.group(1))] = eval(compile(f"lambda P, c0: {_pine_expr(m.group(2))}", "<case>", "eval"), ns)
        j += 1
    assert sorted(fns) == list(range(38))
    return fns


def literal_run(h, l, c, depth=5, newest=True):
    """The script bar by bar as written (L540-581, L780-781, L807-808): pivP / pivB / pivC newest first, unshift and
    pop at 60, makeQ with its clamp, ``detect`` one swing set at a time. Returns the confirmed and forming hits as
    (t, id, Q, QB, c0) and per bar (added, pivP.size()), and the final pivP / pivB / pivC."""
    piv_p, piv_b, piv_c = [], [], []
    zdir = 0
    conf, form, per_bar = [], [], []
    for t in range(len(c)):
        added = False
        if t >= depth - 1:
            wh, wl = h[t - depth + 1:t], l[t - depth + 1:t]
            is_hi = bool(h[t] >= wh.max()) if newest else bool(h[t] > wh.max())
            is_lo = bool(l[t] <= wl.min()) if newest else bool(l[t] < wl.min())
        else:
            is_hi = is_lo = False
        if is_hi:
            if zdir == 1:
                if h[t] > piv_p[0]:
                    piv_p[0], piv_b[0], piv_c[0] = h[t], t, c[t]
            elif len(piv_p) == 0 or abs(h[t] - piv_p[0]) >= piv_p[0] * 0.0 / 100:
                piv_p.insert(0, h[t])
                piv_b.insert(0, t)
                piv_c.insert(0, c[t])
                zdir, added = 1, True
        if is_lo:
            if zdir == -1:
                if l[t] < piv_p[0]:
                    piv_p[0], piv_b[0], piv_c[0] = l[t], t, c[t]
            elif len(piv_b) == 0 or piv_b[0] != t:
                if len(piv_p) == 0 or abs(piv_p[0] - l[t]) >= piv_p[0] * 0.0 / 100:
                    piv_p.insert(0, l[t])
                    piv_b.insert(0, t)
                    piv_c.insert(0, c[t])
                    zdir, added = -1, True
        if len(piv_p) > 60:
            piv_p.pop()
            piv_b.pop()
            piv_c.pop()
        n = len(piv_p)
        if added and n >= 12:
            q, qb = HP.make_q(piv_p, 1), [piv_b[min(1 + k, n - 1)] for k in range(11)]
            for pid in HP.detect(q, piv_c[1]):
                conf.append((t, pid, q, qb, piv_c[1]))
        if n >= 11:
            q, qb = HP.make_q(piv_p, 0), [piv_b[min(k, n - 1)] for k in range(11)]
            for pid in HP.detect(q, c[t]):
                form.append((t, pid, q, qb, c[t]))
        per_bar.append((added, n))
    return conf, form, per_bar, (piv_p, piv_b, piv_c)


def assert_rows_equal_literal(df, rows, close):
    """The port's rows against literal_run's (t, id, Q, QB, c0), with the plan levels recomputed from Q."""
    assert len(df) == len(rows)
    if not rows:
        return
    t = np.array([r[0] for r in rows])
    ids = np.array([r[1] for r in rows])
    assert np.array_equal(df["t_bar"].to_numpy(), t) and np.array_equal(df["id"].to_numpy(), ids)
    Q = np.array([r[2] for r in rows])
    QB = np.array([r[3] for r in rows])
    assert same(df["c0"], [r[4] for r in rows])
    assert same(df["close"], np.asarray(close)[t])
    for k in range(9):
        inside = HP.PTS[ids] > k
        assert same(df[f"p{k}"], np.where(inside, Q[:, k], nan))
        assert np.array_equal(df[f"b{k}"].to_numpy(), np.where(inside, QB[:, k], -1))
    unit, e, sl, t1, t2 = HP.plan_levels(ids, Q)
    for col, want in (("unit", unit), ("entry", e), ("sl", sl), ("tp1", t1), ("tp2", t2)):
        assert same(df[col], want), col


# ───────────────────────────── 1. the traps of the spec's risk list ─────────────────────────────

def test_trap01_ratio_constants_parsed_from_the_source_not_mirrored():
    R = HP.RATIOS
    # 144 constants in the source's order (L146-289), every one read by exactly one case of check
    assert len(R) == 144 and HP.SOURCE_LINES["ratios"] == (146, 289)
    used = [k for pid in range(22) for k in HP.CALLS[pid][2]]
    assert len(used) == 144 and sorted(used) == sorted(R)
    assert all(HP.CALLS[pid][1] is None and HP.CALLS[pid][2] == () for pid in range(22, 38))
    # bullish is not the mirror of bearish (values quoted by the spec, B1.4): 8 of the 11 bear / bull pairs differ
    assert (R["Bearish_Bat_XD_min"], R["Bearish_Bat_XD_max"]) == (0.3, 1.8)
    assert (R["Bullish_Bat_XD_min"], R["Bullish_Bat_XD_max"]) == (0.5, 2.5)
    assert (R["Bearish_Gartley_XD_min"], R["Bearish_Gartley_BD_min"], R["Bearish_Gartley_BD_max"]) == \
        (1.618, 2.618, 3.618)
    pairs = [(a, b) for a, b in zip(range(11), range(11, 22))]
    differ = [a for a, b in pairs if [R[k] for k in HP.CALLS[a][2]] != [R[k] for k in HP.CALLS[b][2]]]
    assert differ == [0, 1, 2, 3, 4, 5, 8, 10], differ           # Shark, AB=CD and 5-0 are mirrored
    # by hand: a bearish Bat and its mirror image p -> 200 - p. Bear (id 0), X=100 A=0 B=50 C=20 D=40:
    # XB = 50/100 = 0.5 in (0.382, 0.70); AC = 20/50 = 0.4 in (0.382, 1.886); BD = 20/30 = 0.667 in (0.618, 2.618);
    # XD = 40/100 = 0.4 in (0.3, 1.8). The mirror (X=100 A=200 B=150 C=180 D=160) has the same four ratios, but the
    # bullish XD window is (0.5, 2.5): Bull Bat (id 11) rejects it (D must be below 200 - 100*0.5 = 150).
    bear = np.array([40.0, 20, 50, 0, 100, 10, 90, 10, 90, 10, 90])
    assert bool(HP.check(0, bear, nan)) and not bool(HP.check(11, 200.0 - bear, nan))


def test_trap01b_the_table_regenerates_from_the_source():
    text = need_source()
    parsed = HP.parse_pine_source(text)
    assert parsed["names"] == HP.NAMES
    assert {k: float(v) for k, (v, _) in parsed["ratios"].items()} == HP.RATIOS
    assert list(parsed["ratios"]) == list(HP.RATIOS)                       # the order too
    assert {k: v[:3] for k, v in parsed["calls"].items()} == HP.CALLS
    assert parsed["lines"] == HP.SOURCE_LINES
    # the block in the module is exactly the generator's output (nothing retyped or edited by hand)
    src = Path(HP.__file__).read_text(encoding="utf-8").split("\n")
    a = next(i for i, s in enumerate(src) if s.startswith("# >>> GENERATED"))
    z = next(i for i, s in enumerate(src) if s.startswith("# <<< GENERATED"))
    assert "\n".join(src[a + 3:z]) == HP.render_tables(parsed)
    if parsed["sha256"] != HP.SOURCE_SHA256:
        pytest.skip("another copy of the source (different bytes) with the same tables")
    # the inputs the module keeps as named constants (L19, L21, L26, L35-41) are the source's defaults
    lines = text.split("\n")

    def default(var):
        m = next(re.match(rf"^{var}\s*= input\.(?:int|float)\(([0-9.]+),", s) for s in lines
                 if re.match(rf"^{var}\s*= input", s))
        return float(m.group(1))
    assert (default("depth"), default("devPct"), default("histMax")) == (HP.DEPTH, HP.DEV_PCT, HP.HIST_MAX)
    assert (default("slK"), default("tp1K"), default("tp2K")) == (HP.SL_K, HP.TP1_K, HP.TP2_K)
    assert (default("cslK"), default("ctp1K"), default("ctp2K"), default("planBars")) == \
        (HP.CSL_K, HP.CTP1_K, HP.CTP2_K, HP.PLAN_BARS)
    # every pattern is enabled by default (L48-92), so EN (L105-115) is all true
    en = [s for s in lines if re.match(r"^(use|en)\w+\s*= input\.bool\(", s)]
    assert len(en) == 3 + 38 and all("input.bool(true," in s for s in en)


# The harmonic predicates as data (read from L296-320): inR terms (orientation, A, B, window, d) and plain comparisons
def harmonic_terms(pid):
    fname, bear, keys = HP.CALLS[pid]
    v = [HP.RATIOS[k] for k in keys]
    if fname == "pcBat":
        return [(bear, 4, 3, v[0], v[1], 2), (bear, 2, 3, v[2], v[3], 1), (bear, 2, 1, v[4], v[5], 0),
                (bear, 4, 3, v[6], v[7], 0)], []
    if fname == "pcShark":
        if bear:
            return [(False, 3, 2, v[0], v[1], 1), (True, 2, 1, v[2], v[3], 0), (True, 4, 3, v[4], v[5], 0)], \
                [(3, 4), (2, 4)]
        return [(True, 3, 2, v[0], v[1], 1), (False, 2, 1, v[2], v[3], 0), (False, 4, 3, v[4], v[5], 0)], \
            [(4, 3), (4, 2)]
    if fname == "pcABCD":
        return [(bear, 2, 3, v[0], v[1], 1), (bear, 2, 1, v[2], v[3], 0)], []
    if fname == "pc50":
        if bear:
            return [(True, 4, 3, v[0], v[1], 2), (False, 3, 2, v[2], v[3], 1), (True, 2, 1, v[4], v[5], 0)], \
                [(5, 4), (5, 3)]
        return [(False, 4, 3, v[0], v[1], 2), (True, 3, 2, v[2], v[3], 1), (False, 2, 1, v[4], v[5], 0)], \
            [(4, 5), (3, 5)]
    assert fname == "pc3Drives"
    return [(bear, 4, 3, v[0], v[1], 2), (bear, 2, 1, v[2], v[3], 0)], []


def _ratio_in(P, bear, a, b, mn, mx, d):
    """inR in the spec's words (B1.3): r = (d - B) / (A - B) strictly inside (mn, mx), and A > B if bear, A < B if not
    (another floating-point form than the script's; equal away from the window's edges)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (P[:, d] - P[:, b]) / (P[:, a] - P[:, b])
    ok = P[:, a] > P[:, b] if bear else P[:, a] < P[:, b]
    return ok & (r > mn) & (r < mx)


def restated(pid, P, c0):
    """Every predicate restated from the source (ratio form for inR); P (m, 11), c0 (m,)."""
    p = [P[:, k] for k in range(11)]
    if pid <= 21:
        terms, less = harmonic_terms(pid)
        out = np.ones(len(P), bool)
        for t in terms:
            out &= _ratio_in(P, *t)
        for i, j in less:                                    # P[i] < P[j]
            out &= p[i] < p[j]
        return out
    p1, p2, p3, p4, p5, p6, p7, p8 = p[1:9]
    if pid == 22:
        return ((p3 - p4) / 2 > p3 - p2) & _ratio_in(P, True, 3, 2, 0.8, 1.2, 1) & (p4 < p2) & (p2 < p1) & (c0 < p2)
    if pid == 23:
        return ((p4 - p3) / 2 > p2 - p3) & _ratio_in(P, False, 3, 2, 0.8, 1.2, 1) & (p4 > p2) & (p2 > p1) & (c0 > p2)
    if pid in (24, 26):
        k = 2 if pid == 24 else 1.5
        lo, hi = (1.2, 2.5) if pid == 24 else (0.8, 1.2)
        return (((p5 - p6) / k > p5 - p4) & (p1 < p3) & _ratio_in(P, True, 5, 4, lo, hi, 3)
                & _ratio_in(P, False, 4, 3, 0.8, 1.2, 2) & (c0 < p2))
    if pid in (25, 27):
        k = 2 if pid == 25 else 1.5
        lo, hi = (1.2, 2.5) if pid == 25 else (0.8, 1.2)
        return (((p6 - p5) / k > p4 - p5) & (p1 > p3) & _ratio_in(P, False, 5, 4, lo, hi, 3)
                & _ratio_in(P, True, 4, 3, 0.8, 1.2, 2) & (c0 > p2))
    rising = (p8 < p6) & (p6 < p4) & (p4 < p2) & (p7 < p5) & (p5 < p3) & (p3 < p1)
    falling = (p8 > p6) & (p6 > p4) & (p4 > p2) & (p7 > p5) & (p5 > p3) & (p3 > p1)
    if pid == 28:
        return rising & (p7 - p6 > p5 - p4) & (p5 - p4 > p3 - p2) & (c0 < p2)
    if pid == 29:
        return falling & (p6 - p7 > p4 - p5) & (p4 - p5 > p2 - p3) & (c0 > p2)
    if pid == 30:
        return rising & (p7 - p6 < p5 - p4) & (p5 - p4 < p3 - p2) & (c0 < p2)
    if pid == 31:
        return falling & (p6 - p7 < p4 - p5) & (p4 - p5 < p2 - p3) & (c0 > p2)
    if pid == 32:
        return ((p6 - p7) / 1.2 > p6 - p5) & (p6 > p4) & (p4 > p2) & (p5 < p3) & (p3 < p1) & (c0 > p2)
    if pid == 33:
        return ((p7 - p6) / 1.2 > p5 - p6) & (p6 < p4) & (p4 < p2) & (p5 > p3) & (p3 > p1) & (c0 < p2)
    bull_core = ((p6 - p7) / 1.2 > p6 - p5) & (p6 > p5) & (p2 > p5) & (p6 > p4) & (p4 > p2) & (p5 > p3) & (p3 > p1)
    bear_core = ((p7 - p6) / 1.2 > p5 - p6) & (p6 < p5) & (p2 < p5) & (p6 < p4) & (p4 < p2) & (p5 < p3) & (p3 < p1)
    if pid == 34:
        return bull_core & ((p6 - p5) / 1.7 > p2 - p1) & (c0 > p2)
    if pid == 35:
        return bear_core & ((p5 - p6) / 1.7 > p1 - p2) & (c0 < p2)
    if pid == 36:
        return bull_core & (p2 - p1 < 1.2 * (p6 - p5)) & (p2 - p1 > 0.8 * (p6 - p5)) & (c0 > p2)
    assert pid == 37
    return bear_core & (p1 - p2 < 1.2 * (p5 - p6)) & (p1 - p2 > 0.8 * (p5 - p6)) & (c0 < p2)


def boundary_sets(pid, P, c0):
    """Sets derived from positive instances of ``pid``: each tested point of each inR term moved exactly onto the
    script's bound (its own floating-point form) and one ulp to either side; for the chart patterns also every pair of
    swings made equal and the close put on the neckline p2, with the same one-ulp neighbours."""
    outP, outC = [], []
    for q, c in zip(P, c0):
        if pid <= 21:
            terms, _ = harmonic_terms(pid)
        else:
            terms = []
        for bear, a, b, mn, mx, d in terms:
            for x in (mn, mx):
                bound = (q[a] - q[b]) * x + q[b] if bear else q[b] - (q[b] - q[a]) * x
                for f in (lambda v: v, lambda v: np.nextafter(v, np.inf), lambda v: np.nextafter(v, -np.inf)):
                    qq = q.copy()
                    qq[d] = f(bound)
                    outP.append(qq)
                    outC.append(c)
        if pid >= 22:
            n = HP.PTS[pid]
            for i in range(1, n):
                for j in range(1, n):
                    if i != j:
                        for f in (lambda v: v, lambda v: np.nextafter(v, np.inf), lambda v: np.nextafter(v, -np.inf)):
                            qq = q.copy()
                            qq[i] = f(q[j])
                            outP.append(qq)
                            outC.append(c)
            for f in (lambda v: v, lambda v: np.nextafter(v, np.inf), lambda v: np.nextafter(v, -np.inf)):
                outP.append(q.copy())
                outC.append(f(q[2]))
    return np.array(outP), np.array(outC)


def test_trap02_predicates_transcribed_mechanically_and_strict():
    # (a) strict: no <= or >= in any predicate of the port (L293-480 have none either, checked below with the source)
    for fn in [HP.in_r] + [f for name, f in vars(HP).items() if name.startswith("pc_")]:
        body = inspect.getsource(fn)
        assert "<=" not in body and ">=" not in body, fn.__name__
    # (b) a Bear Bat by hand (X=100 A=0 B=50 C=20 D=40, see trap 1): true; D exactly on the BD bound
    # (P2 - P1) * 0.618 + P1 = 30 * 0.618 + 20 = 38.54 is outside (strict) and one ulp above it inside (XD = 0.3854
    # stays inside (0.3, 1.8), XB and AC do not move)
    q = np.array([40.0, 20, 50, 0, 100, 10, 90, 10, 90, 10, 90])
    assert bool(HP.check(0, q, nan))
    edge = (50.0 - 20.0) * 0.618 + 20.0
    q[0] = edge
    assert not bool(HP.check(0, q, nan))
    q[0] = np.nextafter(edge, np.inf)
    assert bool(HP.check(0, q, nan))
    # (c) the restatement (ratio form) agrees with the port on 400,000 random alternating sets; every id but Bear
    # Gartley (4, which can never fire, see below) has positive cases among them
    hits = np.zeros(38, int)
    for seed in range(2):
        Q, c0 = random_sets(200_000, seed)
        H = HP.hit_matrix(Q, c0)
        for pid in range(38):
            assert np.array_equal(H[:, pid], restated(pid, Q, c0)), pid
        hits += H.sum(axis=0)
    assert hits[4] == 0 and all(hits[i] > 0 for i in range(38) if i != 4), hits


def test_trap02b_predicates_equal_the_source_transliterated():
    text = need_source()
    fns = source_oracle(text)
    region = text.split("\n")[292:480]                                # L293-480
    assert not any("<=" in s or ">=" in s for s in region)
    Q, c0 = random_sets(30_000, 7)
    H = HP.hit_matrix(Q, c0)
    probes_P, probes_c = [Q], [c0]
    for pid in range(38):
        pos = np.flatnonzero(H[:, pid])[:12]
        if len(pos):
            bp, bc = boundary_sets(pid, Q[pos], c0[pos])
            probes_P.append(bp)
            probes_c.append(bc)
    P = np.concatenate(probes_P)
    C = np.concatenate(probes_c)
    H = HP.hit_matrix(P, C)
    mismatch = 0
    for r in range(len(P)):
        q = [float(x) for x in P[r]]
        c = float(C[r])
        for pid in range(38):
            mismatch += bool(fns[pid](q, c)) != bool(H[r, pid])
    assert len(P) > 50_000 and mismatch == 0


def test_trap03_inR_orientation_and_predicates_28_33_kept_literally():
    # the spec's cases (B6): inR(true, 10, 0, .382, .886, 5) is true: 10*0.382 = 3.82 < 5 < 8.86 = 10*0.886
    assert HP.in_r(True, 10.0, 0.0, 0.382, 0.886, 5.0)
    assert not HP.in_r(True, 10.0, 0.0, 0.382, 0.886, 9.0)          # above 8.86
    assert not HP.in_r(True, 0.0, 10.0, 0.382, 0.886, 5.0)          # A < B: bounds 6.18 and 1.14, an empty interval
    lo, hi = (10.0 - 0.0) * 0.382 + 0.0, (10.0 - 0.0) * 0.886 + 0.0
    assert not HP.in_r(True, 10.0, 0.0, 0.382, 0.886, lo) and not HP.in_r(True, 10.0, 0.0, 0.382, 0.886, hi)
    assert HP.in_r(True, 10.0, 0.0, 0.382, 0.886, np.nextafter(lo, 99)) and \
        HP.in_r(True, 10.0, 0.0, 0.382, 0.886, np.nextafter(hi, -99))
    # bullish: B - (B - A) * mx < d < B - (B - A) * mn: A=0, B=10 gives 1.14 < 5 < 6.18; swapped A, B is empty
    assert HP.in_r(False, 0.0, 10.0, 0.382, 0.886, 5.0)
    assert not HP.in_r(False, 10.0, 0.0, 0.382, 0.886, 5.0)
    assert not HP.in_r(False, 0.0, 10.0, 0.382, 0.886, 10.0 - (10.0 - 0.0) * 0.382)
    assert not HP.in_r(True, 5.0, 5.0, 0.382, 0.886, 5.0)          # A == B: d < B and d > B
    # 28-33 never compare two adjacent swings, so each passes with the alternation shifted by one (P1 a low for the
    # bearish wedge / triangle, P6 a low for the pennant): hand-made sets, the margins in the comments
    shifted = {
        # p8<p6<p4<p2: 110<111<112<113; p7<p5<p3<p1: 109<109.5<109.8<110; p7-p6=-2 > p5-p4=-2.5 > p3-p2=-3.2; c0 112<113
        28: ([114, 110, 113, 109.8, 112, 109.5, 111, 109, 110, 108, 112], 112.0),
        # the mirror: highs at the odd indexes; p6-p7=-2 > p4-p5=-2.5 > p2-p3=-3.2; c0 108 > p2 107
        29: ([106, 110, 107, 110.2, 108, 110.5, 109, 111, 110, 112, 108], 108.0),
        # widths p7-p6=-2 < p5-p4=-1.5 < p3-p2=-1.2: a converging shape passes as an "expanding" triangle
        30: ([114, 112.9, 113, 111.8, 112, 110.5, 111, 109, 110, 108, 112], 112.0),
        31: ([106, 107.1, 107, 108.2, 108, 109.5, 109, 111, 110, 112, 108], 108.0),
        # p6=110 is a low: (p6-p7)/1.2 = -0.83 > p6-p5 = -2; lows 110>109>108, highs 112<113<114; c0 109 > 108
        32: ([107, 114, 108, 113, 109, 112, 110, 111, 109, 112, 108], 109.0),
        33: ([113, 106, 112, 107, 111, 108, 110, 109, 111, 108, 112], 111.0),
    }
    for pid, (q, c0) in shifted.items():
        q = np.array(q, float)
        hi_at = [k for k in range(1, 10) if q[k] > q[k - 1] and q[k] > q[k + 1]]
        lo_at = [k for k in range(1, 10) if q[k] < q[k - 1] and q[k] < q[k + 1]]
        assert len(hi_at) + len(lo_at) == 9                          # a strict zigzag
        assert bool(HP.check(pid, q, c0)), pid
    # 34-37 do compare adjacent swings (p6 > p5 or p6 < p5): their shifted sets fail
    assert not bool(HP.check(34, np.array(shifted[32][0], float), 109.0))


def test_trap04_first_hit_in_registry_order():
    # D = 100.5 (low), C = 110.3, B = 107, A = 110, X = 100 on the same swings:
    # Bull Shark (17): (C-B)/(A-B) = 3.3/3 = 1.1 in (1, 3.618); (C-D)/(C-B) = 9.8/3.3 = 2.97 in (1, 3.24);
    #   (A-D)/(A-X) = 9.5/10 = 0.95 in (0.886, 2.13); X < A, X < B.
    # Double Top (22): (A-X)/2 = 5 > A-B = 3; (C-B)/(A-B) = 1.1 in (0.8, 1.2); X < B < C; c0 < B.
    # Every bearish harmonic needs D above C and every other bullish one (C-A)/(B-A) or the like in a window that 1.1
    # misses, so the first hit in registry order is the bullish 17, whose direction the alert takes.
    lead = [104, 108, 103.5, 108.5, 104.2, 109, 103.8, 108.7]
    q = np.array([100.5, 110.3, 107, 110, 100] + lead[::-1][:6], float)
    hits = HP.detect(q, 100.55)
    assert hits[0] == 17 and 22 in hits and HP.dir_of(17) == 1 and HP.dir_of(22) == -1
    out, _ = run_points(lead + [100, 110, 107, 110.3, 100.5, 104])
    cf = out["confirmed"]
    # D is the 13th swing (bar 77), the next one (104) is added on bar 80: the confirmation
    assert set(cf["t_bar"]) == {80} and list(cf["id"]) == hits
    first = cf[cf["first_hit"]]
    assert list(first["id"]) == [17] and list(first["dir"]) == [1]
    assert not bool(cf.loc[cf["id"] == 22, "first_hit"].iloc[0])
    fm = out["forming"]
    at_d = fm[fm["t_bar"] == 77]                                     # the forming detection at D's own close
    assert list(at_d["id"][:1]) == [17] and 22 in set(at_d["id"]) and at_d["first_hit"].sum() == 1


T5 = [104, 109, 103, 111, 102, 108, 100, 110, 105, 112.5, 99, 108]


def test_trap05_twelve_swings_for_confirmed_eleven_for_forming():
    # 12 swings; s_k on bar 6k + 5. s6..s9 = 100, 110, 105, 112.5 is a Bear AB=CD: (105-100)/(110-100) = 0.5 in
    # (0.382, 0.886), (112.5-105)/(110-105) = 1.5 in (1.13, 2.618). s6..s10 (99) is a Bull Shark (trap 4's arithmetic:
    # (112.5-105)/(110-105) = 1.5, (112.5-99)/7.5 = 1.8, (110-99)/10 = 1.1).
    out, (_, _, c) = run_points(T5)
    sw, n = out["swings"], out["n_swings"]
    born = sw["born_bar"].to_numpy()
    assert n[born[9]] == 10 and n[born[10]] == 11 and n[born[11]] == 12
    cf = out["confirmed"]
    # confirmed only where a swing is added with pivP.size() >= 12: the bar where s11 is added, D = s10
    assert set(cf["t_bar"]) == {born[11]} and 17 in set(cf["id"]) and set(cf["b0"]) == {65}
    assert sw["fixed_bar"].iloc[10] == born[11]                      # the confirmation bar fixes D
    # where s10 is added there are 11 swings: no confirmed detection, although makeQ(1) would clamp q[10] = pivP[10]
    # and find the Bear AB=CD on s9..s6
    piv = piv_at(out, born[10])
    assert len(piv) == 11 and 7 in HP.detect(HP.make_q(piv, 1), sw["close_at_set"].iloc[9])
    assert not (cf["t_bar"] == born[10]).any()
    # forming needs 11: none while there are 10, although a clamped makeQ(0) shows the AB=CD forming on bars 58-60
    fm = out["forming"]
    ten = np.flatnonzero(n == 10)
    clamped = [t for t in ten if 7 in HP.detect(HP.make_q(piv_at(out, t), 0), c[t])]
    assert clamped == [58, 59, 60]
    assert not fm["t_bar"].isin(ten).any()
    assert len(fm) and fm["t_bar"].min() >= born[10] and (n[fm["t_bar"]] >= 11).all()


def test_trap06_c0_is_the_close_of_d_for_confirmed_and_the_close_for_forming():
    # Double Bottom (23) on X'=120 (high), 100, neckline p2 = 108, second bottom 100.5, then D = 112 (bar 71) and the
    # next low 95 (added on bar 73): (120-100)/2 = 10 > 108-100 = 8; (108-100.5)/(108-100) = 0.94 in (0.8, 1.2).
    pts = [106, 113, 105, 114, 104, 115, 106, 120, 100, 108, 100.5, 112, 95]

    def wick(close, low):
        def edit(h, l, c):
            c[71], l[71] = close, low                                 # D's bar closes back under / over the neckline
        return edit
    # A: D's bar closes at 107 < 108. The confirmed detection reads pivC[1] = 107: no Double Bottom, though the
    # forming one was seen at the closes 108.12 (bar 69), 110.03 (70) and 109.22 (72), all above the neckline.
    out, (_, _, c) = run_points(pts, edit=wick(107.0, 106.9))
    assert out["swings"]["close_at_set"].iloc[11] == 107.0 and out["swings"]["born_bar"].iloc[12] == 73
    assert not (out["confirmed"]["id"] == 23).any()
    db = out["forming"][out["forming"]["id"] == 23]
    assert list(db["t_bar"]) == [69, 70, 72] and same(db["c0"], c[[69, 70, 72]]) and (db["c0"] > 108).all()
    # B: D's bar closes at 110 > 108, the confirmation bar (73) at 106.38 < 108: confirmed, with c0 = 110
    out, (_, _, c) = run_points(pts, edit=wick(110.0, 109.9))
    cf = out["confirmed"]
    row = cf[cf["id"] == 23]
    assert list(row["t_bar"]) == [73] and list(row["c0"]) == [110.0] and c[73] < 108
    assert same(row["close"], [c[73]])


def test_trap07_zigzag_highs_first_and_the_low_side_guard():
    h = [10.0, 10.5, 10.2, 10.4, 11.0, 11.5, 11.0, 10.8, 10.6, 10.4, 11.2, 10.0, 10.1, 10.2, 10.3, 10.5]
    l = [9.0, 9.5, 9.2, 9.4, 8.5, 8.0, 9.0, 9.1, 9.2, 9.3, 8.8, 9.0, 9.1, 9.2, 9.3, 8.5]
    c = [9.5, 10.0, 9.7, 9.9, 9.0, 8.5, 9.5, 9.6, 9.7, 9.8, 9.0, 9.5, 9.6, 9.7, 9.8, 9.0]
    out = HP.patterns(h, l, c)
    # bar 4, zdir 0: an outside bar (11 the highest, 8.5 the lowest of bars 0-4): the high branch runs first and adds
    # a high; the low branch then sees zdir 1 and pivB[0] == 4, and adds nothing
    # bar 5, zdir 1: an outside bar with a higher high (11.5 > 11): the high moves to bar 5; its low 8.0 is dropped
    # bar 10, zdir 1: 11.2 is the highest of bars 6-10 but not above 11.5 (no move); 8.8 is the lowest of 6-10 and
    #   the newest swing is on bar 5, not 10: a new low
    # bar 15, zdir -1: 10.5 the highest of 11-15 and 8.5 the lowest, below the swing low 8.8: a new high is added
    #   first, then the guard drops the low; the swing low stays at bar 10, 8.8
    assert list(np.flatnonzero(out["is_hi"])) == [4, 5, 10, 15]
    assert list(np.flatnonzero(out["is_lo"])) == [4, 5, 10, 15]
    assert list(np.flatnonzero(out["added"])) == [4, 10, 15]
    sw = out["swings"]
    assert list(sw["bar"]) == [5, 10, 15] and list(sw["price"]) == [11.5, 8.8, 10.5]
    assert list(sw["is_high"]) == [True, False, True] and list(sw["close_at_set"]) == [8.5, 9.0, 9.0]
    assert list(sw["born_bar"]) == [4, 10, 15] and list(sw["fixed_bar"]) == [10, 15, -1]
    assert list(out["n_swings"]) == [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3]


def test_zigzag_tied_high_within_five_bars():
    # bar 4 sets a low (9); bar 6's high 11.0 ties bar 2's 11.0 inside the window 2-6. The newest bar among equal
    # values wins (this port's reading): isHi on bar 6 and, with zdir -1, a new high there. With the other reading the
    # offset is bar 2's, no high is set on bar 6, and none later in these bars.
    h = np.array([12.0, 11.5, 11.0, 10.5, 10.0, 10.8, 11.0, 10.9, 10.7])
    l = np.array([11.0, 10.5, 10.0, 9.5, 9.0, 9.6, 9.8, 9.7, 9.65])
    c = (h + l) / 2
    z = HP.zigzag(h, l, c)
    assert list(np.flatnonzero(z["is_hi"])) == [6] and list(z["sw_bar"]) == [4, 6] and list(z["sw_price"]) == [9, 11]
    z = HP.zigzag(h, l, c, tie="oldest")
    assert not z["is_hi"].any() and list(z["sw_bar"]) == [4]
    # zdir 1 and a high equal to the swing high: isHi, but the move needs a strictly higher high
    h2 = np.append(h, [11.0])
    l2 = np.append(l, [9.9])
    z = HP.zigzag(h2, l2, (h2 + l2) / 2)
    assert z["is_hi"][9] and list(z["sw_bar"]) == [4, 6]
    with pytest.raises(ValueError):
        HP.zigzag(h, l, c, tie="first")


def test_trap08_forming_detection_at_every_bar():
    # The script detects the forming pattern on its last bar only; at every close t the port gives what that last bar
    # would show if the chart ended at t (the data truncated at t)
    h, l, c = rand_bars(600, 11)
    full = HP.patterns(h, l, c)["forming"]
    assert full["t_bar"].nunique() > 0.2 * 600                      # forming patterns on many bars, not just the last
    cols = [x for x in full.columns if x != "first_bar_of_instance"]
    for t in range(120, 600, 3):
        part = HP.patterns(h[:t + 1], l[:t + 1], c[:t + 1])["forming"]
        a = part[part["t_bar"] == t].reset_index(drop=True)
        b = full[full["t_bar"] == t].reset_index(drop=True)
        pd.testing.assert_frame_equal(a[cols], b[cols])
        assert list(a["first_bar_of_instance"]) == list(b["first_bar_of_instance"])


def test_trap09_makeq_index_clamping():
    p = [5.0, 4.0, 3.0, 2.0, 1.0]                                   # pivP, newest first, n = 5
    assert list(HP.make_q(p, 0)) == [5, 4, 3, 2, 1, 1, 1, 1, 1, 1, 1]  # q[k] = pivP[min(k, 4)]
    assert list(HP.make_q(p, 1)) == [4, 3, 2, 1, 1, 1, 1, 1, 1, 1, 1]
    twelve = [float(x) for x in range(12)]
    assert list(HP.make_q(twelve, 1)) == twelve[1:]                 # 12 swings, s = 1: no clamp
    assert list(HP.make_q(twelve[:11], 0)) == twelve[:11]           # 11 swings, s = 0: no clamp
    assert list(HP.make_q(twelve[:11], 1)) == twelve[1:11] + [10.0]  # 11 swings, s = 1: q[10] clamped
    with pytest.raises(ValueError):
        HP.make_q([], 0)
    # in the port the guards keep the clamp away: the forming set on the bar where the 11th swing is added is pivP[0..10]
    # (the live s10 at that bar, then s9..s0), the confirmed set where the 12th is added is pivP[1..11]
    out, _ = run_points(T5)
    t = int(out["swings"]["born_bar"].iloc[10])
    assert same(out["forming_q"][t], piv_at(out, t)) and out["forming_qbar"][t][1:].tolist() == \
        [6 * k + 5 for k in range(9, -1, -1)]
    assert np.isnan(out["forming_q"][t - 1]).all() and (out["forming_qbar"][t - 1] == -1).all()
    cf = out["confirmed"]
    r = cf.iloc[0]
    assert [r[f"p{k}"] for k in range(r["n_pts"])] == [99.0, 112.5, 105.0, 110.0, 100.0]


def test_trap10_q3_of_the_5_0_is_its_b():
    # Bear 5-0 (id 9), Q5..Q0 = X A B C D E = 90, 100, 95, 102.5, 87.5, 105.5:
    # (C-B)/(A-B) = 7.5/5 = 1.5 in (1, 3.618); (C-D)/(C-B) = 15/7.5 = 2 in (1, 3.24); (E-D)/(C-D) = 18/15 = 1.2 in
    # (0.886, 2.13); X < A and X < B. The plan reads Q3 whatever the pattern: here the 5-0's B (95), not its A (100):
    # AD = |95 - 105.5| = 10.5; dir -1: SL = 105.5 + 0.13*10.5 = 106.865, TP1 = 105.5 - 0.382*10.5 = 101.489,
    # TP2 = 105.5 - 0.618*10.5 = 99.011.
    q = np.array([105.5, 87.5, 102.5, 95, 100, 90, 101, 92, 101, 92, 101], float)
    assert bool(HP.check(9, q, nan)) and HP.pts_of(9) == 6 and HP.dir_of(9) == -1
    unit, e, sl, t1, t2 = HP.plan_levels(9, q)
    assert unit == 10.5 and e == 105.5
    assert sl == 105.5 - (-1 * 0.13) * 10.5 and abs(sl - 106.865) < 1e-12
    assert t1 == 105.5 + (-1 * 0.382) * 10.5 and abs(t1 - 101.489) < 1e-12
    assert t2 == 105.5 + (-1 * 0.618) * 10.5 and abs(t2 - 99.011) < 1e-12
    # a chart pattern's unit is h = |Q1 - Q2| around the neckline p2 (Double Top, dir -1): Q1 = 110.3, Q2 = 107
    u, e, sl, t1, t2 = HP.plan_levels(22, np.array([100.5, 110.3, 107, 110, 100, 0, 0, 0, 0, 0, 0], float))
    assert abs(u - 3.3) < 1e-12 and e == 107 and sl == 107 - (-1 * 0.5) * u and t1 == 107 - u and \
        t2 == 107 + (-1 * 1.618) * u
    # no unit, no plan (the script's `if ad > 0` / `if h > 0`)
    assert all(math.isnan(x) for x in HP.plan_levels(7, np.array([5.0, 1, 4, 5, 0, 0, 0, 0, 0, 0, 0]))[1:])


def test_trap11_the_overlap_gate_does_not_gate_alerts():
    # T5 with two swings in front: the Bear AB=CD on s8..s11 (bars 53-71) is confirmed on bar 73, the Bull Shark on
    # s8..s12 (bars 53-77) on bar 80. Their spans overlap over [53, 71]: 18 bars of the shorter span's 18, more than
    # half, so the shark is not drawn (L785); its alert fires all the same (L793-795, outside the gate).
    out, _ = run_points([103.6, 108.4] + T5)
    cf = out["confirmed"]
    first = cf[cf["first_hit"]]
    assert list(first["t_bar"]) == [73, 80] and list(first["id"]) == [7, 17]
    assert list(first["b3"]) == [53, 59] and list(first["b4"]) == [-1, 53]
    assert HP.overlaps([(53, 71)], 53, 77) and (71 - 53) / min(77 - 53, 71 - 53) > 0.5
    assert list(first["drawn"]) == [True, False]
    assert list(cf["id"]) == [7, 8, 17] and not cf.loc[~cf["first_hit"], "drawn"].any()
    # the gate keeps the newest 15 drawn patterns; non-overlapping spans are all drawn
    assert not HP.overlaps([(0, 10)], 10, 20) and not HP.overlaps([(0, 10)], 6, 20) and HP.overlaps([(0, 10)], 4, 12)


# ───────────────────────────── 2. facts of the script ─────────────────────────────

def test_bear_gartley_can_never_fire():
    # pcBat bearish with X = 1, A = 0: B = xb, C = xb*ac (C < B needs ac < 1), D = C + (B - C)*bd, so
    # XD = xb*(ac + (1 - ac)*bd), increasing in xb and bd, decreasing in ac. Over the open windows XB (0.382, 0.618),
    # AC (0.382, 0.886), BD (2.618, 3.618) its supremum is 0.618*(0.382 + 0.618*3.618) = 1.6178770 < 1.618, the lower
    # edge of the XD window (1.618, 2.618): no set of swings satisfies all four (L210-217).
    R = HP.RATIOS
    sup = R["Bearish_Gartley_XB_max"] * (R["Bearish_Gartley_AC_min"] + (1 - R["Bearish_Gartley_AC_min"])
                                        * R["Bearish_Gartley_BD_max"])
    assert sup < R["Bearish_Gartley_XD_min"] and abs(sup - 1.617877032) < 1e-9
    Q, c0 = random_sets(100_000, 3)
    # sets built on the edges of the three windows: still below the XD window
    xb = np.random.default_rng(1).uniform(0.382, 0.618, 1000)
    ac = np.random.default_rng(2).uniform(0.382, 0.886, 1000)
    bd = np.random.default_rng(3).uniform(2.618, 3.618, 1000)
    B, C = xb, xb * ac
    D = C + (B - C) * bd
    E = np.column_stack([D, C, B, np.zeros(1000), np.ones(1000)] + [np.full(1000, 0.5)] * 6)
    assert not HP.hit_matrix(Q, c0)[:, 4].any() and not HP.hit_matrix(E, np.zeros(1000))[:, 4].any()
    assert (D < 1.618).all()


def test_bull_alt_abcd_has_the_windows_of_bull_abcd():
    # L258-261 and L266-269 hold the same four numbers, so Bull ALT AB=CD (19) fires exactly with Bull AB=CD (18) and
    # is never a first hit; the bearish pair differs (BD 1.27-1.618 against 1.13-2.618)
    v18 = [HP.RATIOS[k] for k in HP.CALLS[18][2]]
    assert v18 == [HP.RATIOS[k] for k in HP.CALLS[19][2]] == [0.382, 0.886, 1.13, 2.618]
    assert [HP.RATIOS[k] for k in HP.CALLS[8][2]] == [0.382, 0.886, 1.27, 1.618]
    Q, c0 = random_sets(50_000, 4)
    H = HP.hit_matrix(Q, c0)
    assert np.array_equal(H[:, 18], H[:, 19]) and H[:, 18].sum() > 1000


# ───────────────────────────── 3. properties on synthetic bars ─────────────────────────────

def _frames_equal_until(a, b, t):
    a = a[a["t_bar"] <= t].reset_index(drop=True)
    b = b[b["t_bar"] <= t].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("seed", [21, 22])
def test_truncation_invariance(seed):
    """Every row with t_bar <= T and every per-bar value at bars <= T are unchanged when the bars after T are removed;
    the swings of the truncated run are the full run's, but its last (live) one, which may move later."""
    h, l, c = rand_bars(2500, seed)
    full = HP.patterns(h, l, c)
    for T in (150, 777, 1500, 2498):
        part = HP.patterns(h[:T + 1], l[:T + 1], c[:T + 1])
        for k in ("n_swings", "added", "n_piv", "is_hi", "is_lo", "live_bar", "live_price"):
            assert same(part[k], full[k][:T + 1]), k
        assert same(part["forming_q"], full["forming_q"][:T + 1])
        assert np.array_equal(part["forming_qbar"], full["forming_qbar"][:T + 1])
        _frames_equal_until(part["forming"], full["forming"], T)
        _frames_equal_until(part["confirmed"], full["confirmed"], T)
        ps, fs = part["swings"], full["swings"]
        m = len(ps)
        pd.testing.assert_frame_equal(ps.iloc[:m - 1], fs.iloc[:m - 1])
        live = fs.iloc[m - 1]
        assert ps["born_bar"].iloc[-1] == live["born_bar"] and ps["fixed_bar"].iloc[-1] == -1
        assert (ps["bar"].iloc[-1] == live["bar"] and ps["price"].iloc[-1] == live["price"]) or live["bar"] > T


@pytest.mark.parametrize("seed,decimals", [(31, None), (32, 1)])
def test_literal_emulation_equals_the_port(seed, decimals):
    """The Pine as written, bar by bar (literal_run), against the port: swings, per-bar state, every confirmed and
    forming hit with its swings, closes and plan levels. decimals=1 rounds the prices, so the 5-bar windows have ties."""
    h, l, c = rand_bars(1400, seed, decimals)
    out = HP.patterns(h, l, c)
    conf, form, per_bar, (piv_p, piv_b, piv_c) = literal_run(h, l, c)
    assert [a for a, _ in per_bar] == out["added"].tolist() and [n for _, n in per_bar] == out["n_piv"].tolist()
    sw = out["swings"]
    assert len(sw) > 60 and len(piv_p) == 60                         # the script's list holds the newest 60
    assert sw["price"].tolist()[::-1][:60] == piv_p and sw["bar"].tolist()[::-1][:60] == piv_b
    assert sw["close_at_set"].tolist()[::-1][:60] == piv_c
    assert_rows_equal_literal(out["confirmed"], conf, c)
    assert_rows_equal_literal(out["forming"], form, c)
    assert len(conf) > 50 and len(form) > 500
    if decimals is not None:
        assert out["is_hi"].sum() > HP.zigzag(h, l, c, tie="oldest")["is_hi"].sum()   # ties did occur


def test_compiled_zigzag_equals_its_python_body():
    h, l, c = rand_bars(3000, 41, decimals=1)
    for newest in (True, False):
        a = HP._zigzag_kernel(h, l, c, 5, 0.0, newest)
        b = HP._zigzag_kernel.py_func(h, l, c, 5, 0.0, newest)
        assert all(np.array_equal(x, y, equal_nan=True) for x, y in zip(a, b))


def test_output_contract_and_invariants():
    h, l, c = rand_bars(3000, 51)
    out = HP.patterns(h, l, c)
    for k in ("swings", "n_swings", "added", "confirmed", "forming"):
        assert k in out
    base = ["t_bar", "id", "name", "kind", "dir", "first_hit", "n_hits", "n_pts", "c0", "close"] + \
        [f"p{k}" for k in range(9)] + [f"b{k}" for k in range(9)] + ["unit", "entry", "sl", "tp1", "tp2"]
    assert list(out["confirmed"].columns) == base + ["drawn"]
    assert list(out["forming"].columns) == base + ["instance_key", "first_bar_of_instance"]
    assert list(out["swings"].columns) == ["bar", "price", "close_at_set", "is_high", "born_bar", "fixed_bar"]
    sw = out["swings"]
    assert (np.diff(sw["bar"]) > 0).all() and (sw["is_high"].to_numpy()[1:] != sw["is_high"].to_numpy()[:-1]).all()
    assert (sw["born_bar"] <= sw["bar"]).all() and (sw["fixed_bar"].iloc[:-1] > sw["bar"].iloc[:-1]).all()
    assert np.array_equal(np.flatnonzero(out["added"]), sw["born_bar"].to_numpy())
    for name in ("confirmed", "forming"):
        df = out[name]
        assert (np.diff(df["t_bar"]) >= 0).all()
        g = df.groupby("t_bar")
        assert (g["first_hit"].sum() == 1).all() and (g["id"].min() == df.loc[df["first_hit"], "id"].values).all()
        assert (g.size() == g["n_hits"].first()).all()
        assert (df["dir"] == HP.DIR[df["id"]]).all() and (df["n_pts"] == HP.PTS[df["id"]]).all()
        assert set(df["kind"]) <= {"harmonic", "chart"} and ((df["kind"] == "harmonic") == (df["id"] <= 21)).all()
        P = df[[f"p{k}" for k in range(9)]].to_numpy()
        B = df[[f"b{k}" for k in range(9)]].to_numpy()
        inside = np.arange(9)[None, :] < df["n_pts"].to_numpy()[:, None]
        assert np.isfinite(P[inside]).all() and np.isnan(P[~inside]).all() and (B[~inside] == -1).all()
        Bi = np.where(inside, B, -10 ** 9)
        assert (np.diff(Bi, axis=1)[inside[:, 1:]] < 0).all()        # newest first, strictly
        assert (B[:, 0] <= df["t_bar"]).all()
        ok = df["unit"].to_numpy() > 0
        assert np.isfinite(df.loc[ok, ["entry", "sl", "tp1", "tp2"]].to_numpy()).all()
        d = df["dir"].to_numpy()[ok]
        assert ((df["sl"].to_numpy()[ok] - df["entry"].to_numpy()[ok]) * d < 0).all()
        assert ((df["tp2"].to_numpy()[ok] - df["tp1"].to_numpy()[ok]) * d > 0).all()
    cf = out["confirmed"]
    # the confirmation bar is the bar where the swing after D is added (D's fixed_bar), and c0 is D's close
    d_idx = np.searchsorted(sw["bar"].to_numpy(), cf["b0"].to_numpy())
    assert np.array_equal(sw["bar"].to_numpy()[d_idx], cf["b0"].to_numpy())
    assert np.array_equal(sw["fixed_bar"].to_numpy()[d_idx], cf["t_bar"].to_numpy())
    assert same(sw["close_at_set"].to_numpy()[d_idx], cf["c0"])
    fm = out["forming"]
    assert same(fm["c0"], fm["close"]) and same(fm["c0"], c[fm["t_bar"]])
    assert (fm["instance_key"].map(len) == fm["n_pts"]).all()
    assert fm["first_bar_of_instance"].sum() == fm["instance_key"].nunique()
    keyed = fm.groupby("instance_key")["t_bar"]
    assert (fm.loc[fm["first_bar_of_instance"], "t_bar"].to_numpy() ==
            keyed.min().reindex(fm.loc[fm["first_bar_of_instance"], "instance_key"]).to_numpy()).all()
    # an instance lives while its D is the live swing: on each of its bars Q1 is the second newest swing
    i1 = np.searchsorted(sw["bar"].to_numpy(), fm["b1"].to_numpy())
    assert np.array_equal(out["n_swings"][fm["t_bar"].to_numpy()] - 2, i1)
    q = out["forming_q"]
    have = np.minimum(out["n_swings"], 60) >= 11
    assert np.isfinite(q[have]).all() and np.isnan(q[~have]).all()


def test_inputs_left_alone_and_bad_inputs_refused():
    h, l, c = rand_bars(500, 61)
    keep = [x.copy() for x in (h, l, c)]
    HP.patterns(h, l, c)
    assert all(np.array_equal(a, b) for a, b in zip(keep, (h, l, c)))
    bad = c.copy()
    bad[100] = nan
    with pytest.raises(ValueError):
        HP.patterns(h, l, bad)
    with pytest.raises(ValueError):
        HP.patterns(h[:-1], l, c)
    for depth in (1, 51, 2.5, True):
        with pytest.raises(ValueError):
            HP.patterns(h, l, c, depth=depth)
    assert len(HP.patterns(h, l, c, depth=2)["swings"]) > len(HP.patterns(h, l, c, depth=9)["swings"])
    empty = HP.patterns([], [], [])
    assert len(empty["swings"]) == 0 and len(empty["confirmed"]) == 0 and len(empty["forming"]) == 0
    with pytest.raises(ValueError):
        HP.armed(5, np.zeros(11))
    # armed: a chart predicate without its breakout conjunct
    q = np.array([100.5, 110.3, 107, 110, 100, 108.7, 103.8, 109, 104.2, 108.5, 103.5])
    assert bool(HP.armed(22, q)) and bool(HP.check(22, q, 106.9)) and not bool(HP.check(22, q, 107.0))


# ───────────────────────────── 4. real bars (to 2024-06-30 only) ─────────────────────────────

TFS = ("1H", "4H", "1D")


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol: the 1H / 4H / 1D bars (t, tc, h, l, c) from the data start to the hold-out start, loaded with
    end="2024-07-01" and the guard pointed at an empty folder (so it is closed), and the port's output on them."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end="2024-07-01")
                bars = {}
                for tf in TFS:
                    b = mk.tbars(tf)
                    bars[tf] = {k: np.array(getattr(b, k)) for k in ("t", "tc", "h", "l", "c")}
            del mk, b
            gc.collect()
            cache[symbol] = {tf: (x, HP.patterns(x["h"], x["l"], x["c"])) for tf, x in bars.items()}
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_smoke(symbol, real):
    for tf in TFS:
        x, out = real(symbol)[tf]
        assert int(x["tc"][-1]) <= TM.CUT_S                          # nothing from the hold-out
        n = len(x["c"])
        sw, cf, fm = out["swings"], out["confirmed"], out["forming"]
        assert np.isfinite(sw[["price", "close_at_set"]].to_numpy()).all()
        assert (sw["is_high"].to_numpy()[1:] != sw["is_high"].to_numpy()[:-1]).all()
        assert len(out["n_swings"]) == n and len(out["added"]) == n
        for df in (cf, fm):
            P = df[[f"p{k}" for k in range(9)]].to_numpy()
            inside = np.arange(9)[None, :] < df["n_pts"].to_numpy()[:, None]
            assert np.isfinite(P[inside]).all() and np.isfinite(df[["c0", "close"]].to_numpy()).all()
            ok = df["unit"].to_numpy() > 0
            assert ok.mean() > 0.999                                 # a zero unit is (almost) never met
            assert np.isfinite(df.loc[ok, ["unit", "entry", "sl", "tp1", "tp2"]].to_numpy()).all()
            assert (df.groupby("t_bar")["first_hit"].sum() == 1).all()
        assert np.isfinite(out["forming_q"][np.minimum(out["n_swings"], 60) >= 11]).all()
        assert not (cf["id"] == 4).any() and not (fm["id"] == 4).any()   # Bear Gartley never fires
        # the spec's measured rates (B1.1, B2; 2019-2022, an unreconciled scratch port): one swing per ~7 bars
        years = (x["tc"] >= TM.s_of("2019-01-01")) & (x["tc"] < TM.s_of("2023-01-01"))
        per_year = out["added"][years].sum() / 4.0
        want = {("XAUUSDm", "1H"): 851, ("XAUUSDm", "4H"): 228, ("XAUUSDm", "1D"): 35,
                ("BTCUSDm", "1H"): 1258, ("BTCUSDm", "4H"): 312, ("BTCUSDm", "1D"): 52.5}[(symbol, tf)]
        assert abs(per_year / want - 1) < 0.1, (tf, per_year, want)
        assert 5.0 < years.sum() / out["added"][years].sum() < 9.0


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_daily_bars_equal_the_literal_emulation(symbol, real):
    x, out = real(symbol)["1D"]
    conf, form, per_bar, _ = literal_run(x["h"], x["l"], x["c"])
    assert [a for a, _ in per_bar] == out["added"].tolist()
    assert_rows_equal_literal(out["confirmed"], conf, x["c"])
    assert_rows_equal_literal(out["forming"], form, x["c"])


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_start_offset_convergence(symbol, real):
    """The spec (B1.1): zigzags started 300 or 1000 bars later coincide after 48-79 bars, with no mismatch after that.
    Here: the swings, the confirmed and the forming rows of runs started 300 and 1000 bars late are the full run's
    from at most 150 bars after their start on."""
    for tf in ("1H", "4H"):
        x, full = real(symbol)[tf]
        for off in (300, 1000):
            late = HP.patterns(x["h"][off:], x["l"][off:], x["c"][off:])
            fs, ls = full["swings"], late["swings"]
            fb, lb = fs["bar"].to_numpy(), ls["bar"].to_numpy() + off
            fp, lp = fs["price"].to_numpy(), ls["price"].to_numpy()
            fh, lh = fs["is_high"].to_numpy(), ls["is_high"].to_numpy()
            for j in range(len(lb)):                                 # the first late swing from which all agree
                i = int(np.searchsorted(fb, lb[j]))
                if i < len(fb) and len(fb) - i == len(lb) - j and np.array_equal(fb[i:], lb[j:]) and \
                        np.array_equal(fp[i:], lp[j:]) and np.array_equal(fh[i:], lh[j:]):
                    break
            else:
                raise AssertionError(f"{symbol} {tf}: the run started {off} bars late never joins the full one")
            assert lb[j] - off <= 150, (tf, off, lb[j] - off)
            assert np.array_equal(fs["close_at_set"].to_numpy()[i:], ls["close_at_set"].to_numpy()[j:])
            start = int(fs["fixed_bar"].iloc[i + 12])                # from there on both read the same 12 swings
            for k in ("confirmed", "forming"):
                a = full[k][full[k]["t_bar"] >= start].reset_index(drop=True)
                b = late[k][late[k]["t_bar"] + off >= start].reset_index(drop=True)
                assert np.array_equal(a["t_bar"], b["t_bar"] + off) and np.array_equal(a["id"], b["id"])
                assert same(a["entry"], b["entry"]) and same(a["sl"], b["sl"])
