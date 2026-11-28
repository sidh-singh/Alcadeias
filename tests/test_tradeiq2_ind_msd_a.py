"""
Port A of the Market Structure Dashboard (``backtesting/research/tradeiq2_ind_msd.py``).

1. One hand-computed test per trap of the map's porting risks (structure.md section 6, risks 1-11), named after it.
   Each also runs the wrong reading on the same bars (``PineRow``, a plain-Python transcription of ``calcAll`` with a
   switch per misreading) and checks that it answers differently: the case tells the readings apart (the map's
   "mutation tests").
2. The rest of the map's test list: pivots, structure, the swing factor's thresholds, the label against the float rule,
   the maximum score, weekly bars (gold's Sunday stub, BTC's Monday, a holiday Friday, a forming last week), model B
   (equal to A at every higher-timeframe close; inside a bar equal to a recomputation on the data cut at T).
3. The numba kernel against ``PineRow`` on random bars (rounded prices make ties), and the dashboard against a
   plain-Python reference (a per-bar merge loop and the script's float label rule).
4. Truncation invariance: outputs up to chart bar T do not change when the bars after T are removed, nor when the
   forming higher bars' prices are scrambled; also with the M1 data cut at T and every bar rebuilt.
5. Real bars (skipped when the tick store is absent): both symbols, the 1H / 4H / 1D charts of PREREG 6.2, from the data
   start to 2024-06-30 with the hold-out guard closed.

Every test runs with the guard pointed at an empty folder (FINALISTS.md absent: nothing at or after 2024-07-01).
"""

from __future__ import annotations

import bisect
import math
from types import SimpleNamespace

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_msd as MSD
from backtesting.research import tradeiq_market as TM

nan = math.nan
isnan = math.isnan
DAY = 86400
H1 = 3600
T0 = TM.s_of("2019-01-07")          # a Monday, 00:00 UTC
SYMS = ("XAUUSDm", "BTCUSDm")
TICK = 0.001


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The study folder seen by the hold-out guard: an empty tmp folder (the hold-out is closed)."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


# ───────────────────────────── bars for the hand cases ─────────────────────────────

def bars_of(o, h, l, c, step=H1, t0=T0, symbol="XAUUSDm"):
    o, h, l, c = (np.asarray(x, np.float64) for x in (o, h, l, c))
    t = t0 + step * np.arange(len(c), dtype=np.int64)
    return SimpleNamespace(symbol=symbol, t=t, tc=t + step, o=o, h=h, l=l, c=c)


def candles(rows, **kw):
    """Bars from a list of (open, high, low, close)."""
    o, h, l, c = zip(*rows)
    return bars_of(o, h, l, c, **kw)


def path(knots, n, w=0.25):
    """[o, h, l, c] along the piecewise-linear path through ``knots`` (bar, value): open = close = the path, high /
    low = the path +- w. Between knots the path is monotone, so with knots 6+ bars apart every peak / trough knot is a
    strict pivot high / low (path +- w) reported 5 bars later, and no other bar is one."""
    xs, ys = zip(*knots)
    p = np.interp(np.arange(n), xs, ys)
    return [p.copy(), p + w, p - w, p.copy()]


def stair(n):
    """Bar i: open 10i+1, high 10i+15, low 10i, close 10i+14. On every bar k >= 3 the bars k-3..k-1 make a bull FVG
    (low[1] = 10k-10 > high[3] = 10k-15; middle green; low[1] < high[2] = 10k-5; low[2] = 10k-20 < high[3]): zone
    top 10k-10, bottom 10k-15, never mitigated by the stair (low[k] = 10k)."""
    return [(10 * i + 1, 10 * i + 15, 10 * i, 10 * i + 14) for i in range(n)]


def steps(c0, n, s, a, b):
    """n bars from close c0: open = the previous close, high = it + a, low = it - b, close = it + s (s < 0 falls).
    With a + b >= 2|s| no FVG forms (a bull gap needs 2s > a + b, a bear gap -2s > a + b)."""
    out, c = [], float(c0)
    for _ in range(n):
        out.append((c, c + a, c - b, c + s))
        c += s
    return out


def same(a, b):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


# ───────────────────────────── PineRow: calcAll in plain Python, with the misreadings ─────────────────────────────

class PineRow:
    """
    ``calcAll`` (lines 333-623) for one row, statement by statement in plain Python: Pine's ``var`` state as locals
    that survive the bar loop, arrays as lists with index 0 the newest. The defaults are the script; each switch is a
    wrong reading of one of the map's risks:

    ties "left" / "right" (``>=`` on that side of a pivot), override "curr" (the real-time override against
    currH / currL), ob_cap / fvg_cap None (no 6-slot cap), pop_first False (cap after the mitigation), ob_by "wick",
    fvg_by "close", search_cap None (no 50-bar cap), window_from_pivot (search from the pivot bar itself),
    set_before False (test the break before storing a new pivot), clear_after_break False, touch_overlaps False
    (touching zones do not overlap), fvg_offset 0 (the pattern on bars [0]-[2]), green_prev False (green = body only),
    middle_only False (no ``low[1] < high[2] and low[2] < high[3]``), tie_to_bear False, sentinel inf, latest_on_tie
    False (the earliest extreme candle), one_pivot_per_bar (if / elif: a high and a low on one bar keep the high only).
    """

    def __init__(self, ties="strict", override="prev", ob_cap=6, fvg_cap=6, pop_first=True, ob_by="close",
                 fvg_by="wick", search_cap=50, window_from_pivot=False, set_before=True, clear_after_break=True,
                 touch_overlaps=True, fvg_offset=1, green_prev=True, middle_only=True, tie_to_bear=True,
                 sentinel=100000.0, latest_on_tie=True, one_pivot_per_bar=False):
        self.ties, self.override, self.ob_cap, self.fvg_cap = ties, override, ob_cap, fvg_cap
        self.pop_first, self.ob_by, self.fvg_by, self.search_cap = pop_first, ob_by, fvg_by, search_cap
        self.window_from_pivot, self.set_before, self.clear_after_break = window_from_pivot, set_before, clear_after_break
        self.touch_overlaps, self.fvg_offset, self.green_prev = touch_overlaps, fvg_offset, green_prev
        self.middle_only, self.tie_to_bear, self.sentinel = middle_only, tie_to_bear, sentinel
        self.latest_on_tie, self.one_pivot_per_bar = latest_on_tie, one_pivot_per_bar

    def _pivot(self, x, k, high, L=5):
        p = k - L
        if p - L < 0:
            return nan
        v = x[p]

        def beats(a, b, eq):
            return (a >= b if eq else a > b) if high else (a <= b if eq else a < b)

        left = all(beats(v, x[p - i], self.ties == "left") for i in range(1, L + 1))
        right = all(beats(v, x[p + i], self.ties == "right") for i in range(1, L + 1))
        return v if (left and right) else nan

    def _nearest(self, zones, close):
        S = self.sentinel
        bull = bear = S
        for z in zones:
            if z.dir == 1:
                d = z.top - close
                if abs(d) < abs(bull):
                    bull = d
            else:
                d = z.bottom - close
                if abs(d) < abs(bear):
                    bear = d
        wins = abs(bull) < abs(bear) if self.tie_to_bear else abs(bull) <= abs(bear)
        if wins and abs(bull) < S:
            return 1
        if abs(bear) < S:
            return -1
        return 0

    def _detect_ob(self, d, pivot_bar, k, h, l, obs):
        bars_back = k - pivot_bar - 1 + (1 if self.window_from_pivot else 0)
        lim = max(0, bars_back if self.search_cap is None else min(bars_back, self.search_cap))
        price, other, idx = (l[k], h[k], k) if d > 0 else (h[k], l[k], k)
        for i in range(0, lim + 1):
            v = l[k - i] if d > 0 else h[k - i]
            if d > 0:
                better = v < price if self.latest_on_tie else v <= price
            else:
                better = v > price if self.latest_on_tie else v >= price
            if better:
                price, other, idx = v, (h[k - i] if d > 0 else l[k - i]), k - i
        top, bottom = (other, price) if d > 0 else (price, other)
        for z in obs:
            hit = (top >= z.bottom and bottom <= z.top) if self.touch_overlaps else (top > z.bottom and bottom < z.top)
            if z.dir == d and hit:
                return None
        obs.insert(0, SimpleNamespace(dir=d, top=top, bottom=bottom, bar=idx))
        if self.pop_first and self.ob_cap is not None and len(obs) > self.ob_cap:
            obs.pop()
        return top, bottom

    def run(self, o, h, l, c):
        o, h, l, c = (list(map(float, x)) for x in (o, h, l, c))
        n = len(c)
        keys = ("pivot_high", "pivot_low", "swing_h", "swing_l", "struct", "ob", "fvg", "bos", "n_ob", "n_fvg",
                "fvg_new", "ob_top", "ob_bottom")
        out = {k: [] for k in keys}
        prevH = currH = prevL = currL = nan                    # calcSwingHL (lines 334-336)
        s_prevH = s_currH = s_prevL = s_currL = nan            # calcStructure's own SwingData (lines 370-378)
        highType = lowType = 0
        lastPH = lastPHBar = lastPL = lastPLBar = nan          # PivotData (line 569)
        obs, fvgs = [], []
        green = [c[i] > o[i] or (self.green_prev and i >= 1 and c[i] > c[i - 1]) for i in range(n)]
        red = [c[i] < o[i] or (self.green_prev and i >= 1 and c[i] < c[i - 1]) for i in range(n)]
        for k in range(n):
            ph = self._pivot(h, k, True)
            pl = self._pivot(l, k, False)
            if self.one_pivot_per_bar and not isnan(ph):
                pl = nan
            if not isnan(ph):
                prevH, currH = currH, ph
            if not isnan(pl):
                prevL, currL = currL, pl
            if not isnan(ph):
                s_prevH, s_currH = s_currH, ph
                if not isnan(s_prevH):
                    highType = 1 if s_currH > s_prevH else -1
            if not isnan(pl):
                s_prevL, s_currL = s_currL, pl
                if not isnan(s_prevL):
                    lowType = 1 if s_currL > s_prevL else -1
            rtHigh, rtLow = highType, lowType
            refL = s_prevL if self.override == "prev" else s_currL
            refH = s_prevH if self.override == "prev" else s_currH
            if not isnan(refL) and c[k] < refL:
                rtLow = -1
            if not isnan(refH) and c[k] > refH:
                rtHigh = 1
            sb = 1 if (rtHigh == 1 and rtLow == 1) else (-1 if (rtHigh == -1 and rtLow == -1) else 0)

            def store_new():
                nonlocal lastPH, lastPHBar, lastPL, lastPLBar
                if not isnan(ph):
                    lastPH, lastPHBar = ph, k - 5
                if not isnan(pl):
                    lastPL, lastPLBar = pl, k - 5

            if self.set_before:
                store_new()
            c1 = c[k - 1] if k >= 1 else nan
            bull = bear = False
            bullBar = bearBar = 0
            if not isnan(lastPH) and c[k] > lastPH and c1 <= lastPH and not isnan(lastPHBar):
                bull, bullBar = True, int(lastPHBar)
                if self.clear_after_break:
                    lastPH = lastPHBar = nan
            if not isnan(lastPL) and c[k] < lastPL and c1 >= lastPL and not isnan(lastPLBar):
                bear, bearBar = True, int(lastPLBar)
                if self.clear_after_break:
                    lastPL = lastPLBar = nan
            if not self.set_before:
                store_new()
            made = None
            if bull:
                made = self._detect_ob(1, bullBar, k, h, l, obs) or made
            if bear:
                made = self._detect_ob(-1, bearBar, k, h, l, obs) or made
            lo_, hi_ = (c[k], c[k]) if self.ob_by == "close" else (l[k], h[k])
            for i in range(len(obs) - 1, -1, -1):
                if (obs[i].dir == 1 and lo_ < obs[i].bottom) or (obs[i].dir == -1 and hi_ > obs[i].top):
                    obs.pop(i)
            while not self.pop_first and self.ob_cap is not None and len(obs) > self.ob_cap:
                obs.pop()
            obDir = self._nearest(obs, c[k])
            a = self.fvg_offset
            fdir, ftop, fbot = 0, nan, nan
            if k - a - 2 >= 0:
                i1, i2, i3 = k - a, k - a - 1, k - a - 2          # [1], [2], [3] for a = 1
                mo = self.middle_only
                if l[i1] > h[i3] and green[i2] and ((l[i1] < h[i2] and l[i2] < h[i3]) or not mo):
                    fdir, ftop, fbot = 1, l[i1], h[i3]
                if h[i1] < l[i3] and red[i2] and ((h[i1] > l[i2] and h[i2] > l[i3]) or not mo):
                    fdir, ftop, fbot = -1, l[i3], h[i1]
            if fdir != 0:
                fvgs.insert(0, SimpleNamespace(dir=fdir, top=ftop, bottom=fbot, bar=k - 3))
                if self.pop_first and self.fvg_cap is not None and len(fvgs) > self.fvg_cap:
                    fvgs.pop()
            lo_, hi_ = (l[k], h[k]) if self.fvg_by == "wick" else (c[k], c[k])
            for i in range(len(fvgs) - 1, -1, -1):
                if (fvgs[i].dir == 1 and lo_ < fvgs[i].bottom) or (fvgs[i].dir == -1 and hi_ > fvgs[i].top):
                    fvgs.pop(i)
            while not self.pop_first and self.fvg_cap is not None and len(fvgs) > self.fvg_cap:
                fvgs.pop()
            fvgDir = self._nearest(fvgs, c[k])
            for key, v in (("pivot_high", ph), ("pivot_low", pl), ("swing_h", currH), ("swing_l", currL),
                           ("struct", sb), ("ob", obDir), ("fvg", fvgDir), ("bos", 1 if bull else (-1 if bear else 0)),
                           ("n_ob", len(obs)), ("n_fvg", len(fvgs)), ("fvg_new", fdir),
                           ("ob_top", made[0] if made else nan), ("ob_bottom", made[1] if made else nan)):
                out[key].append(v)
        return {k: np.asarray(v, np.float64) for k, v in out.items()}


def ref_run(b, **mut):
    return PineRow(**mut).run(b.o, b.h, b.l, b.c)


# ───────────────────────────── a plain-Python dashboard (the merge and the label) ─────────────────────────────

def ref_dashboard(rows, tf, mintick, row_close=False, strict_merge=False, rows_counted=None):
    """Lines 692-737 and 1323-1346 per chart bar, with ``PineRow`` for the rows: the last row bar with tc <= the chart
    bar's tc (``strict_merge``: tc <), the swing factor with the chart close (``row_close``: the row's own close),
    ``biasPct = points / maxScore * 100`` against 50 / 20 / -50 / -20 as floats. ``rows_counted``: the rows that count
    (default: the active ones)."""
    names = rows_counted or MSD.ACTIVE_ROWS[tf]
    chart = rows[tf]
    vals = {r: ref_run(rows[r]) for r in names}
    tcs = {r: [int(x) for x in rows[r].tc] for r in names}
    out = {"label": [], "score": [], "max_score": []}
    for r in names:
        for f in ("s", "struct", "ob", "fvg", "swing"):
            out[f"{f}_{r}"] = []
    for j in range(len(chart.c)):
        T = int(chart.tc[j])
        points = max_score = 0
        for r in names:
            w = MSD.WEIGHTS[r]
            max_score += w * 4
            k = (bisect.bisect_left(tcs[r], T) if strict_merge else bisect.bisect_right(tcs[r], T)) - 1
            if k < 0:
                st = ob = fv = 0
                sh = sl = nan
            else:
                st, ob, fv = (int(vals[r][x][k]) for x in ("struct", "ob", "fvg"))
                sh, sl = vals[r]["swing_h"][k], vals[r]["swing_l"][k]
            close = float(rows[r].c[k]) if (row_close and k >= 0) else float(chart.c[j])
            if isnan(sh) or isnan(sl):
                sw = 0                                        # math.max(na, mintick) = na: every comparison false
            else:
                pct = (close - sl) / max(sh - sl, mintick) * 100
                sw = -1 if pct < 0 else 1 if pct > 100 else 1 if pct < 30 else -1 if pct > 70 else 0
            s = st + ob + fv + sw
            points += s * w
            for f, v in (("s", s), ("struct", st), ("ob", ob), ("fvg", fv), ("swing", sw)):
                out[f"{f}_{r}"].append(v)
        pct = points / max_score * 100
        out["label"].append(2 if pct > 50 else 1 if pct > 20 else -2 if pct < -50 else -1 if pct < -20 else 0)
        out["score"].append(points)
        out["max_score"].append(max_score)
    return {k: np.asarray(v) for k, v in out.items()}


# ───────────────────────────── nested synthetic rows (24/7, UTC-aligned) ─────────────────────────────

def aggregate(b, key, symbol="XAUUSDm"):
    first = np.flatnonzero(np.diff(key, prepend=key[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(key) - 1)
    return SimpleNamespace(symbol=symbol, t=b.t[first], tc=b.tc[last], o=b.o[first],
                           h=np.maximum.reduceat(b.h, first), l=np.minimum.reduceat(b.l, first), c=b.c[last])


def nest(h1):
    """The four rows of 24/7 hourly bars: 4H and 1D by UTC bucket, 1W by ``weekly_bars``."""
    d1 = aggregate(h1, h1.t // DAY)
    return {"1H": h1, "4H": aggregate(h1, h1.t // (4 * H1)), "1D": d1, "1W": MSD.weekly_bars(d1)}


def random_h1(weeks, seed, vol=1.0, dec=None, start=1500.0):
    """Hourly bars from T0 (a Monday) with drift regimes, so every row gets trends, pivots, breaks and zones."""
    rng = np.random.default_rng(seed)
    n = weeks * 7 * 24
    drift = np.repeat(rng.normal(0, 0.15 * vol, n // 120 + 1), 120)[:n]
    c = start + np.cumsum(drift + rng.normal(0, vol, n))
    o = np.concatenate(([start], c[:-1])) + rng.normal(0, 0.05 * vol, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.6 * vol, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.6 * vol, n))
    if dec is not None:
        o, h, l, c = (np.round(x, dec) for x in (o, h, l, c))
    return bars_of(o, h, l, c)


@pytest.fixture(scope="module")
def synth():
    return nest(random_h1(60, 7))


# ───────────────────────────── 1. the traps (structure.md section 6, risks 1-11) ─────────────────────────────

def test_trap01_pivot_ties_are_strict_on_both_sides():
    # highs 0 1 2 3 4 10 10 5 4 3 2 1 0: bars 5 and 6 tie at 10, so neither is a strict pivot high (bar 5 ties on its
    # right, bar 6 on its left). The other readings each find one: ">=" on the left gives bar 6 (reported on bar 11),
    # ">=" on the right bar 5 (reported on bar 10). The lows mirror it on a second series (lows 100 - those highs).
    h = np.array([0, 1, 2, 3, 4, 10, 10, 5, 4, 3, 2, 1, 0], float)
    b = bars_of(h, h, h - 1, h)
    lo = 100.0 - h
    bl = bars_of(lo, lo + 1, lo, lo)
    r, rl = MSD.row_values(b), MSD.row_values(bl)
    assert np.isnan(r["pivot_high"]).all() and np.isnan(rl["pivot_low"]).all()
    left, right = ref_run(b, ties="left"), ref_run(b, ties="right")
    assert np.flatnonzero(np.isfinite(left["pivot_high"])).tolist() == [11] and left["pivot_high"][11] == 10
    assert np.flatnonzero(np.isfinite(right["pivot_high"])).tolist() == [10] and right["pivot_high"][10] == 10
    left, right = ref_run(bl, ties="left"), ref_run(bl, ties="right")
    assert np.flatnonzero(np.isfinite(left["pivot_low"])).tolist() == [11] and left["pivot_low"][11] == 90
    assert np.flatnonzero(np.isfinite(right["pivot_low"])).tolist() == [10] and right["pivot_low"][10] == 90
    # and one strictly higher bar in the tie is a pivot under every reading
    h2 = h.copy()
    h2[6] = 10.5
    b2 = bars_of(h2, h2, h2 - 1, h2)
    assert np.flatnonzero(np.isfinite(MSD.row_values(b2)["pivot_high"])).tolist() == [11]


def test_trap02_structure_override_uses_the_older_pivot_and_ties_are_lh():
    # Knots: lows 95 @5, 100 @17, 101 @29 (pivot lows 94.75, 99.75, 100.75: HL, HL -> lowType +1); highs 110 @11,
    # 105 @23 (pivot highs 110.25, 105.25 -> LH: highType -1), then a rise to 112 @40 and back to 106 @46.
    # Known on bar 28 (23 + 5): prevH = 110.25, currH = 105.25 -> structure 0 (LH + HL).
    # Bars 36-38 close at 108, 109, 110: above currH (105.25) but not above prevH (110.25): the override (line 413,
    # against prevH) does not fire -> 0. Read against currH it would fire -> +1.
    # Bars 39-41 close at 111, 112, 111 > 110.25: rtHighType = 1 -> +1; bars 42-44 close at 110, 109, 108: back to 0
    # (the override is not stored); bar 45 reports the pivot high 112.25 @40 (HH, stored) -> +1.
    o, h, l, c = path([(0, 100), (5, 95), (11, 110), (17, 100), (23, 105), (29, 101), (36, 108), (40, 112), (46, 106),
                       (50, 106)], 51)
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    want = {28: 0, 35: 0, 36: 0, 37: 0, 38: 0, 39: 1, 40: 1, 41: 1, 42: 0, 43: 0, 44: 0, 45: 1, 50: 1}
    assert {k: int(r["struct"][k]) for k in want} == want
    assert r["pivot_high"][28] == 105.25 and r["high_type"][28] == -1 and r["low_type"][34] == 1
    assert r["high_type"][39] == 1 and r["high_type"][42] == -1      # the type after the override, bar by bar
    mutant = ref_run(b, override="curr")
    assert mutant["struct"][36:39].tolist() == [1, 1, 1]              # the "fixed" override reads +1 here
    # an equal pivot high is "LH" (line 384: currH > prevH ? 1 : -1): peaks 110 @11 and 110 @23
    o, h, l, c = path([(0, 100), (5, 95), (11, 110), (17, 100), (23, 110), (29, 101), (34, 104)], 35)
    r = MSD.row_values(bars_of(o, h, l, c))
    assert r["pivot_high"][28] == 110.25 and r["high_type"][28] == -1


def test_trap03_swing_factor_uses_the_chart_close():
    # A 4H row along knots 105 @0, 100 @5, 110 @11, 102 @17, 114 @25 with a wide 4H bar 19 (open 104, high 109.5, low
    # 100.5, close 105); every other 4H bar is four identical 1H bars. On 4H bar 18 the row's swing high is 110.25
    # (pivot @11, known on bar 16) and its swing low 99.75 (pivot @5, known on bar 10): range 10.5.
    # Inside 4H bar 19 the 1H closes are 101, 105, 109, 105 (the last closes the 4H bar). Model A keeps the 4H row at
    # bar 18 for the first three, and the swing factor takes the 1H close:
    #   (101 - 99.75) / 10.5 * 100 = 11.9  -> +1;  (105 - 99.75) / 10.5 = 50.0 -> 0;  (109 - 99.75) / 10.5 = 88.1 -> -1.
    # With the 4H row's own close (bar 18: 103.5 -> 35.7%) all three would be 0.
    o4, h4, l4, c4 = path([(0, 105), (5, 100), (11, 110), (17, 102), (25, 114), (40, 120)], 41)
    o4[19], h4[19], l4[19], c4[19] = 104.0, 109.5, 100.5, 105.0
    o1, h1, l1, c1 = (np.repeat(x, 4) for x in (o4, h4, l4, c4))
    inside = [(104.0, 106.0, 100.5, 101.0), (101.0, 105.5, 100.8, 105.0), (105.0, 109.5, 104.5, 109.0),
              (109.0, 109.2, 104.6, 105.0)]
    for i, (a, bb, cc, d) in enumerate(inside):
        o1[76 + i], h1[76 + i], l1[76 + i], c1[76 + i] = a, bb, cc, d
    rows = nest(bars_of(o1, h1, l1, c1))
    assert np.array_equal(rows["4H"].h, h4) and np.array_equal(rows["4H"].l, l4) and np.array_equal(rows["4H"].c, c4)
    r4 = MSD.row_values(rows["4H"])
    assert r4["swing_h"][18] == 110.25 and r4["swing_l"][18] == 99.75 and r4["swing_h"][19] == 110.25
    out = MSD.structure_dashboard(rows, "1H")
    assert out["swing_4H"][76:80].tolist() == [1, 0, -1, 0]
    wrong = ref_dashboard(rows, "1H", TICK, row_close=True)
    assert wrong["swing_4H"][76:79].tolist() == [0, 0, 0]
    assert np.array_equal(out["swing_4H"], ref_dashboard(rows, "1H", TICK)["swing_4H"])


def test_trap04_zone_caps_pop_before_mitigation_obs_by_close_fvgs_by_wick():
    # (a) The FVG cap is not display-only: a stair of 10 bars makes 8 bull gaps (bars 3..10), the array keeps 6.
    #     A gradual fall (no gap: a + b >= 2s) then removes them by the wick until bar 19 (low 29) has none left: 0.
    #     Without the cap the gaps of bars 3 [15, 20] and 4 [25, 30] would survive the low 29: +1.
    b = candles(stair(10) + steps(104, 10, -7, 2, 12))
    r = MSD.row_values(b)
    assert r["fvg_new"][3:11].tolist() == [1] * 8 and r["n_fvg"][8:11].tolist() == [6, 6, 6]
    assert r["n_fvg"][19] == 0 and r["fvg"][19] == 0
    assert ref_run(b, fvg_cap=None)["fvg"][19] == 1
    # (b) The cap pops BEFORE the mitigation: 6 bull gaps (stair bars 0..7, gaps found on bars 3..8), then bars 8-10
    #     make a bear gap found on bar 11 (high[1] = 70 < low[3] = 72, middle red, 70 > low[2] = 66, 76 > 72: top 72,
    #     bottom 70). Bar 11: unshift (7) -> pop the oldest, the bull gap [15, 20] -> its low 62 removes the bull gap
    #     [65, 70] -> 5 zones. Capping after the mitigation keeps 6 (the gap [15, 20] stays).
    #     A gradual fall to a low of 21 on bar 24 then leaves the bear gap alone (-1), or the bear gap and [15, 20]
    #     (top 20 is 4 below the close 24, the bear bottom 70 is 46 above: +1).
    rows = stair(8) + [(85, 90, 72, 75), (75, 76, 66, 67), (67, 70, 66.5, 68), (68, 69, 62, 63), (63, 67, 57, 60),
                       (60, 62, 54, 57)] + steps(57, 11, -3, 2, 6)
    b = candles(rows)
    r, late = MSD.row_values(b), ref_run(b, pop_first=False)
    assert r["fvg_new"][11] == -1 and r["n_fvg"][10] == 6 and r["n_fvg"][11] == 5 and late["n_fvg"][11] == 6
    assert b.c[24] == 24 and r["n_fvg"][24] == 1 and r["fvg"][24] == -1 and late["fvg"][24] == 1
    # (c) Order blocks are removed by the CLOSE: the bull order block [101.75, 105.25] (made on bar 23, see trap 5)
    #     survives bar 31 (low 101.5 below its bottom, close 102 above) and goes on bar 32 (close 101.7).
    o, h, l, c = path([(0, 105), (5, 100), (11, 110), (17, 102), (25, 114), (30, 103)], 31)
    l[11], l[19] = 95.0, 101.75
    extra = [(103, 103.5, 101.5, 102.0), (102, 102.5, 101.6, 101.7), (101.7, 102, 101.2, 101.5)]
    o, h, l, c = (np.concatenate([x, [e[i] for e in extra]]) for i, x in enumerate((o, h, l, c)))
    b = bars_of(o, h, l, c)
    r, wick = MSD.row_values(b), ref_run(b, ob_by="wick")
    assert (r["ob_top"][23], r["ob_bottom"][23]) == (105.25, 101.75)
    assert r["n_ob"][30:33].tolist() == [1, 1, 0] and r["ob"][30:33].tolist() == [1, 1, 0]
    assert wick["n_ob"][31] == 0
    # (d) FVGs are removed by the WICK, also on the bar that finds them: bars 0-2 make the bull gap [12, 14] found on
    #     bar 3, whose low 11.9 removes it although it closes at 17.5. By the close it would stay (+1).
    b = candles([(10, 12, 9, 11), (11, 17, 11.5, 16), (16, 18, 14, 17), (17, 18, 11.9, 17.5), (17.5, 18, 17, 17.6)])
    r, by_close = MSD.row_values(b), ref_run(b, fvg_by="close")
    assert r["fvg_new"][3] == 1 and r["n_fvg"][3] == 0 and r["fvg"][3] == 0
    assert by_close["n_fvg"][3] == 1 and by_close["fvg"][3] == 1
    # (e) The order-block cap: a rising zigzag (troughs 100, 104, ... every 12 bars, peaks 10 above them) breaks each
    #     pivot high on the way up (bars 21, 33, ..., 105; the first: 110.67 after 109 > 110.25) and makes the bull
    #     order block of the trough before it ([103.75, 104.25], [107.75, 108.25], ...: no two touch). The 7th and 8th
    #     unshifts pop the two oldest: 6 zones held; with no cap, 8.
    knots = [(0, 104)]
    for i in range(9):
        knots += [(5 + 12 * i, 100 + 4 * i), (11 + 12 * i, 110 + 4 * i)]
    o, h, l, c = path(knots, knots[-1][0] + 1)
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    k = np.flatnonzero(r["bos"])
    assert k.tolist() == list(range(21, 106, 12)) and (r["bos"][k] == 1).all()
    assert [(r["ob_bottom"][i], r["ob_top"][i]) for i in k] == [(103.75 + 4 * j, 104.25 + 4 * j) for j in range(8)]
    assert r["n_ob"][k].tolist() == [1, 2, 3, 4, 5, 6, 6, 6] and ref_run(b, ob_cap=None)["n_ob"][-1] == 8


def test_trap05_order_block_search_window_cap_ties_overlap_and_pivot_order():
    # (a) Window (pivot, break], ties to the latest bar. Knots 105 @0, 100 @5, 110 @11, 102 @17, 114 @25; the pivot
    #     bar 11 has a long lower wick (low 95), bar 19's low equals bar 17's (101.75; its high is 105.25). The pivot
    #     high 110.25 @11 is known on bar 16; bar 23 closes at 111 after 109.5: a bull break. The search covers
    #     i = 0..min(23 - 11 - 1, 50) = 11, bars 12..23 (not the pivot bar 11): lowest low 101.75 on bars 17 and 19,
    #     the strict "<" from the current bar back keeps bar 19 -> zone [101.75, 105.25].
    #     From the pivot bar: [95, 110.25]; the earliest tie: [101.75, 102.25].
    o, h, l, c = path([(0, 105), (5, 100), (11, 110), (17, 102), (25, 114)], 26)
    l[11], l[19] = 95.0, 101.75
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    assert r["bos"][23] == 1 and (r["bos"][:23] == 0).all()
    assert (r["ob_top"][23], r["ob_bottom"][23]) == (105.25, 101.75)
    a = ref_run(b, window_from_pivot=True)
    assert (a["ob_top"][23], a["ob_bottom"][23]) == (110.25, 95.0)
    a = ref_run(b, latest_on_tie=False)
    assert (a["ob_top"][23], a["ob_bottom"][23]) == (102.25, 101.75)
    # (b) The 50-bar cap and (c) the touching overlap. The pivot high 110.25 @11, then flat bars (high 106, low 104:
    #     ties, no pivot) to bar 74 with a spike low 90 on bar 14 and a low 100 on bar 40; bar 75 closes at 111.
    #     barsBack = 75 - 11 - 1 = 63 -> capped at 50: bars 25..75 -> bar 40: zone [100, 106]. Uncapped: bar 14,
    #     [90, 107.25]. Then a pivot high 120.25 @81 (known on 86), a pull-back to the low 106.0 on bar 87 and the break
    #     of bar 94 (121.875 after 119.75): the zone [106, 107.25] touches the first one's top (106 <= 106): rejected.
    #     With a strict overlap test it would be added (2 zones).
    o, h, l, c = path([(0, 105), (5, 100), (11, 110), (16, 105)], 17)
    o, h, l, c = (np.concatenate([x, np.full(58, v)]) for x, v in zip((o, h, l, c), (105.0, 106.0, 104.0, 105.0)))
    l[14], l[40] = 90.0, 100.0
    o, h, l, c = (np.append(x, v) for x, v in zip((o, h, l, c), (105.0, 111.5, 104.5, 111.0)))
    o2, h2, l2, c2 = path([(0, 111), (6, 120), (12, 107), (20, 124)], 21)
    l2[12] = 106.0
    o, h, l, c = (np.concatenate([x, y[1:]]) for x, y in zip((o, h, l, c), (o2, h2, l2, c2)))
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    assert np.flatnonzero(r["bos"]).tolist() == [75, 94]
    assert (r["ob_top"][75], r["ob_bottom"][75]) == (106.0, 100.0) and np.isnan(r["ob_top"][94]) and r["n_ob"][94] == 1
    a = ref_run(b, search_cap=None)
    assert (a["ob_top"][75], a["ob_bottom"][75]) == (107.25, 90.0)
    a = ref_run(b, touch_overlaps=False)
    assert (a["ob_top"][94], a["ob_bottom"][94]) == (107.25, 106.0) and a["n_ob"][94] == 2
    # (d) The new pivot is stored BEFORE the break test (lines 544-553). The pivot high 110.25 @11 stays unbroken;
    #     bar 20 has a high of 115 (closing at 108), known as a pivot on bar 25, which closes at 112 after 110: bar 25
    #     stores 115 first, and 112 < 115 is no break. Testing first would break 110.25 on bar 25. Bar 27 (115.5 after
    #     113.5) breaks 115 under both.
    o, h, l, c = path([(0, 105), (5, 100), (11, 110), (16, 104), (19, 107)], 20)
    extra = [(107, 115, 106.5, 108), (108, 109, 107, 108.5), (108.5, 109.5, 107.5, 109), (109, 110, 108, 109.5),
             (109.5, 110.1, 108.5, 110.0), (110, 113, 109.5, 112), (112, 114, 111.5, 113.5), (113.5, 116, 113, 115.5)]
    o, h, l, c = (np.concatenate([x, [e[i] for e in extra]]) for i, x in enumerate((o, h, l, c)))
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    assert r["pivot_high"][25] == 115 and np.flatnonzero(r["bos"]).tolist() == [27]
    assert (r["ob_top"][27], r["ob_bottom"][27]) == (109.0, 107.0)        # bars 21..27: the lowest low, bar 21
    assert np.flatnonzero(ref_run(b, set_before=False)["bos"]).tolist() == [25, 27]
    # (e) Each pivot breaks once, and an unbroken pivot is overwritten. Pivot highs 110.25 @11 (known 16) and 107.25
    #     @22 (known 27, replacing the unbroken 110.25); bar 30 closes at 107.5 after 106: the break of 107.25. Bar 32
    #     crosses 110.25 (110.5 after 109): nothing, that pivot is gone; bar 35 crosses 107.25 again (108 after 106.5):
    #     nothing, it was used. Not clearing it after the break would break it again on bar 35.
    o, h, l, c = path([(0, 105), (5, 100), (11, 110), (17, 102), (22, 107), (27, 103), (33, 112), (34, 106.5), (35, 108),
                       (38, 111), (40, 111.5)], 41)
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    assert np.flatnonzero(np.isfinite(r["pivot_high"])).tolist() == [16, 27, 38]
    assert np.flatnonzero(r["bos"]).tolist() == [30]
    assert np.flatnonzero(ref_run(b, clear_after_break=False)["bos"]).tolist() == [30, 35]
    # (f) The earliest break: 6 bars after the pivot bar (the 5th right bar is below the pivot, so is its close). The
    #     window is bars 6..11 (barsBack 5); the lowest low is bar 10's 108.6 (high 109.5).
    hh = [101, 102, 103, 104, 105, 110, 109.9, 109.8, 109.7, 109.6, 109.5, 111.5]
    cc = [100.5, 101.5, 102.5, 103.5, 104.5, 109, 109.4, 109.3, 109.2, 109.1, 109.0, 111]
    ll = [100, 101, 102, 103, 104, 108, 109.0, 108.9, 108.8, 108.7, 108.6, 109.0]
    r = MSD.row_values(bars_of(cc, hh, ll, cc))
    assert r["pivot_high"][10] == 110 and r["bos"][10] == 0 and r["bos"][11] == 1
    assert (r["ob_top"][11], r["ob_bottom"][11]) == (109.5, 108.6)


def test_trap06_fvg_pattern_on_bars_1_to_3_and_green_by_close():
    # (a) Found on bar k from bars k-3..k-1: the stair's first gap (bars 0-2) is found on bar 3, zone [15, 20]
    #     (top = low[1] of bar 2 = 20, bottom = high[3] of bar 0 = 15). On bars [0]-[2] it would appear on bar 2.
    b = candles(stair(4))
    r = MSD.row_values(b)
    assert r["fvg_new"].tolist() == [0, 0, 0, 1] and r["fvg"][3] == 1
    assert ref_run(b, fvg_offset=0)["fvg_new"][2] == 1
    # (b) _green = close > open OR close > close[1] (line 251): the middle candle has a red body (open 16, close 14)
    #     but closes above the first (11): green. low[1] = 13 > high[3] = 12, 13 < high[2] = 17, low[2] = 11.5 < 12:
    #     a bull gap [12, 13] on bar 3. Green by the body alone: none.
    b = candles([(10, 12, 9, 11), (16, 17, 11.5, 14), (14, 16, 13, 15), (15, 16, 14, 15.5)])
    assert MSD.row_values(b)["fvg"].tolist() == [0, 0, 0, 1] and ref_run(b, green_prev=False)["fvg"][3] == 0
    # (c) _red likewise: a green body (13 -> 15) closing below the first candle (19): a bear gap [17, 18] on bar 3.
    b = candles([(20, 21, 18, 19), (13, 18.5, 12, 15), (15, 17, 14, 16), (16, 16.5, 15, 15.5)])
    assert MSD.row_values(b)["fvg"].tolist() == [0, 0, 0, -1] and ref_run(b, green_prev=False)["fvg"][3] == 0
    # (d) Only the middle candle makes the gap (low[1] < high[2] and low[2] < high[3]): here the gap already sits
    #     between bars 0 and 1 (low 12.5 >= high 12), so there is none; without those conditions there would be one.
    b = candles([(10, 12, 9, 11), (12.5, 17, 12.5, 16), (16, 18, 14, 17), (17, 18, 16, 17.5)])
    assert MSD.row_values(b)["fvg_new"].tolist() == [0, 0, 0, 0] and ref_run(b, middle_only=False)["fvg"][3] == 1


def test_trap07_the_100000_sentinel_and_nearest_ties_go_bearish():
    # (a) A tie between the nearest bull and bear zones is bearish (line 446 needs |bull| < |bear|): the bull gap
    #     [95, 100] (bars 0-2, found on 3), a gap-free rise, the bear gap [110, 115] (bars 11-13, found on 14), whose
    #     bar closes at 105: |100 - 105| = |110 - 105| = 5 -> -1. Ties to the bull side would say +1.
    rows = [(94, 95, 93, 94.5), (94.5, 102, 94, 101.5), (101.5, 105.5, 100, 102.5)] + steps(102.5, 8, 2, 3, 1)
    rows += [(118.5, 119, 115, 116), (116, 116.5, 108, 108.5), (108.5, 110, 107, 109), (109, 109.5, 104, 105)]
    b = candles(rows)
    r = MSD.row_values(b)
    assert r["fvg_new"][3] == 1 and r["fvg_new"][14] == -1 and r["n_fvg"][14] == 2
    assert r["fvg"][13] == 1 and r["fvg"][14] == -1 and ref_run(b, tie_to_bear=False)["fvg"][14] == 1
    # (b) The sentinel: both best distances start at the price 100000.0, so a zone 100000 or more away is invisible.
    #     The bull gap [99995, 100000], then bars whose lows all sit at 99996 (no gap can form, none is mitigated)
    #     carry the close to 200010; a last close of 200000.01 puts the zone's top 100000.01 below: 0. At 199999.99:
    #     +1. Starting from infinity, the zone would count: +1. (BTC needs a close above $100k: only in the hold-out.)
    base = [(99990, 99995, 99989, 99994), (99994, 100010, 99993, 100008), (100008, 100012, 100000, 100010)]
    c = 100010.0
    for _ in range(20):
        base.append((c, c + 5001, 99996, c + 5000))
        c += 5000
    for last, want in ((200000.01, 0), (199999.99, 1)):
        b = candles(base + [(c, c + 1, 99996, last)])
        r = MSD.row_values(b)
        assert r["n_fvg"][-1] == 1 and r["fvg"][-1] == want, last
        assert ref_run(b, sentinel=math.inf)["fvg"][-1] == 1
    # (c) no zone: 0
    assert MSD.row_values(candles(stair(3)))["fvg"].tolist() == [0, 0, 0]


def test_trap08_strict_thresholds_and_inactive_rows():
    # (a) The label in integers equals the float rule biasPct = p / m * 100 for every reachable score; the
    #     boundaries: 22/44 = 50% exactly is LEAN BULL (not > 50), 23/44 BULLISH; 9/44 = 20.45% LEAN BULL, 8/44 =
    #     18.2% NEUTRAL; 18/36 and 14/28 (50%) LEAN; 7/36 = 19.4% and 5/28 = 17.9% NEUTRAL, 8/36 and 6/28 LEAN.
    for m in (44, 36, 28):
        p = np.arange(-m, m + 1)
        flt = [2 if x / m * 100 > 50 else 1 if x / m * 100 > 20 else -2 if x / m * 100 < -50 else -1 if x / m * 100 < -20
               else 0 for x in p]
        assert MSD.label_of(p, m).tolist() == flt
    cases = {(22, 44): 1, (23, 44): 2, (9, 44): 1, (8, 44): 0, (-22, 44): -1, (-23, 44): -2, (-9, 44): -1, (-8, 44): 0,
             (18, 36): 1, (19, 36): 2, (8, 36): 1, (7, 36): 0, (14, 28): 1, (15, 28): 2, (6, 28): 1, (5, 28): 0}
    for (p, m), want in cases.items():
        assert MSD.label_of([p], m)[0] == want, (p, m)
    # (b) Rows below the chart count neither in the points nor in the maximum (line 692, 1336-1340): on a 4H chart the
    #     1H row is ignored (the maximum is 4 x (2 + 3 + 4) = 36, not 44), whatever its bars say.
    rows = nest(random_h1(20, 3))
    out = MSD.structure_dashboard(rows, "4H")
    assert (out["max_score"] == 36).all() and not any(k.endswith("_1H") for k in out)
    other = dict(rows)
    other["1H"] = SimpleNamespace(**{**vars(rows["1H"]), "c": rows["1H"].c[::-1].copy()})
    again = MSD.structure_dashboard(other, "4H")
    assert all(np.array_equal(out[k], again[k]) for k in out)
    counted = ref_dashboard(rows, "4H", TICK, rows_counted=("1H", "4H", "1D", "1W"))
    assert (counted["max_score"] == 44).all() and not np.array_equal(counted["label"], out["label"])
    assert {tf: int(MSD.structure_dashboard(rows, tf)["max_score"][0]) for tf in MSD.CHART_TFS} == \
        {"1H": 44, "4H": 36, "1D": 28}


def test_trap09_merge_at_close_and_weekly_bars(synth):
    # (a) A higher row's value is visible at the chart bar whose close equals the row bar's close (tc <= T), not one
    #     hour earlier, and equals tradeiq_market.htf_at; a "<" merge would show it one chart bar late.
    rows = synth
    out = MSD.structure_dashboard(rows, "1H")
    for r in ("4H", "1D", "1W"):
        rv = MSD.row_values(rows[r])
        for f in ("struct", "ob", "fvg"):
            assert np.array_equal(out[f"{f}_{r}"], TM.htf_at(rows[r], rv[f], rows["1H"], default=0)), (r, f)
        key = rv["struct"] * 9 + rv["ob"] * 3 + rv["fvg"]
        ch = np.flatnonzero(np.diff(key) != 0) + 1                      # row bars whose values differ from the last
        assert len(ch) >= 5, r
        for k in ch[:12]:
            j = int(np.searchsorted(rows["1H"].tc, rows[r].tc[k]))
            assert rows["1H"].tc[j] == rows[r].tc[k]
            for f in ("struct", "ob", "fvg"):
                assert out[f"{f}_{r}"][j] == rv[f][k] and out[f"{f}_{r}"][j - 1] == rv[f][k - 1], (r, k, f)
    late = ref_dashboard(rows, "1H", TICK, strict_merge=True)
    assert not np.array_equal(late["struct_4H"], out["struct_4H"])
    # (b) The weekly bar: the ISO week of the day bar's tc - 1 s (see also test_weekly_bars_*). A day bar closing on
    #     Monday 00:00 belongs to the week before; one closing on Tuesday 00:00 to the new week.
    days = SimpleNamespace(t=np.array([T0 - DAY, T0]), tc=np.array([T0, T0 + DAY]), o=np.array([1.0, 2.0]),
                           h=np.array([1.5, 2.5]), l=np.array([0.5, 1.5]), c=np.array([1.2, 2.2]))
    w = MSD.weekly_bars(days)
    assert len(w) == 2 and w.tc.tolist() == [T0, T0 + DAY] and w.week_start.tolist() == [T0 - 7 * DAY, T0]


def test_trap10_inverted_swing_ranges():
    # (a) By hand (swingBiasDir, lines 705-708): when the last pivot high is below the last pivot low the range is one
    #     tick and the factor is the side of the close against swingL (pct < 0 -> -1; pct > 100 -> +1; 0 -> +1).
    #     swingH 105.25, swingL 111.75, tick 0.001: close 116 -> (4.25 / 0.001) * 100 -> +1; 109 -> -1; 111.75 -> 0%
    #     -> +1; 111.7505 (50% of a tick) -> 0; 111.7509 (90%) -> -1. Read with |H - L| = 6.5: 116 -> 65.4% -> 0.
    sh, sl = 105.25, 111.75
    got = MSD.swing_factor([116.0, 109.0, 111.75, 111.7505, 111.7509], [sh] * 5, [sl] * 5, 0.001)
    assert got.tolist() == [1, -1, 1, 0, -1]
    assert (116.0 - sl) / abs(sh - sl) * 100 < 70                       # the |range| reading's 65.4%
    # (b) On bars: pivot highs 105.25 @11 (known 16); pivot lows 94.75 @17 (known 22) and 111.75 @29 (known 34): a V
    #     dip after a rally without a pivot high (the peak 125 @27 is topped within 5 bars). Bars 34-40 have swingH <
    #     swingL; bar 40 closes at 116 -> +1 (65.4% -> 0 with the |range|); the pivot high 132.25 @36 (known 41) ends it.
    o, h, l, c = path([(0, 100), (5, 98), (11, 105), (17, 95), (27, 125), (29, 112), (32, 128), (36, 132), (40, 116),
                       (42, 109)], 43)
    b = bars_of(o, h, l, c)
    r = MSD.row_values(b)
    inv = np.flatnonzero(r["swing_h"] < r["swing_l"])
    assert inv.tolist() == list(range(34, 41)) and r["swing_h"][40] == 105.25 and r["swing_l"][40] == 111.75
    f = MSD.swing_factor(c, r["swing_h"], r["swing_l"], TICK)
    assert f[40] == 1 and f[41] == 1 and f[42] == -1                    # 41: (112.5 - 111.75) / 20.5 = 3.7% -> +1


def test_trap11_outside_bar_both_pivots():
    # Bar 5 (high 20, low 0) is both a strict pivot high and a strict pivot low (the other bars: highs 10, lows 5,
    # ties, no pivot); bar 10 reports both, and both updates happen (lines 341-348, 380-396, 544-550): swing 20 / 0.
    # Bar 12 (25 / -1) is another: reported on 17 as HH (+1) and LL (-1) -> structure 0 (mixed). The order of the two
    # updates (high first) moves only the label strings. A port with if / elif would drop the low.
    h = np.full(18, 10.0)
    l = np.full(18, 5.0)
    h[5], l[5], h[12], l[12] = 20.0, 0.0, 25.0, -1.0
    c = np.full(18, 7.5)
    b = bars_of(c, h, l, c)
    r = MSD.row_values(b)
    assert (r["pivot_high"][10], r["pivot_low"][10], r["swing_h"][10], r["swing_l"][10]) == (20, 0, 20, 0)
    assert (r["high_type"][17], r["low_type"][17], r["struct"][17]) == (1, -1, 0)
    assert np.isnan(ref_run(b, one_pivot_per_bar=True)["swing_l"][10])
    # both pivots of the outside bar 12 feed the break tracking (lastPHBar = lastPLBar = 12): a close above 25 breaks
    # the high on bar 18 (the search covers bars 13..18, all lows 5: the strict "<" keeps the break bar itself, zone
    # [5, 26.5]), then a close below -1 breaks the low on bar 20
    c2 = np.concatenate([c, [26.0, 7.5, -2.0]])
    h2 = np.concatenate([h, [26.5, 10.0, 10.0]])
    l2 = np.concatenate([l, [5.0, 5.0, -2.5]])
    r2 = MSD.row_values(bars_of(c2, h2, l2, c2))
    assert np.flatnonzero(r2["bos"]).tolist() == [18, 20] and r2["bos"][18] == 1 and r2["bos"][20] == -1
    assert (r2["ob_top"][18], r2["ob_bottom"][18]) == (26.5, 5.0)


# ───────────────────────────── 2. the rest of the map's test list ─────────────────────────────

def test_pivots_are_reported_five_bars_late_and_never_in_the_first_ten_bars():
    h = np.array([1, 2, 3, 4, 5, 10, 5, 4, 3, 2, 1, 0], float)
    r = MSD.row_values(bars_of(h, h, h - 0.5, h))
    assert np.flatnonzero(np.isfinite(r["pivot_high"])).tolist() == [10] and r["pivot_high"][10] == 10
    assert np.isnan(r["swing_h"][:10]).all() and r["swing_h"][10] == 10
    # a strict maximum on bar 3 has only 3 bars on its left: never a pivot
    h = np.array([1, 2, 3, 9, 5, 4, 3, 2, 1, 0, -1, -2], float)
    assert np.isnan(MSD.row_values(bars_of(h, h, h - 0.5, h))["pivot_high"]).all()
    # equal lows on both sides of a minimum do not matter beyond the 5 bars
    lo = np.array([0, 9, 9, 9, 9, 9, 1, 9, 9, 9, 9, 9, 0], float)
    r = MSD.row_values(bars_of(lo + 1, lo + 2, lo, lo + 1))
    assert np.flatnonzero(np.isfinite(r["pivot_low"])).tolist() == [11] and r["pivot_low"][11] == 1


def test_structure_hh_hl_is_bullish_lh_ll_bearish_mixed_neutral():
    # HH + HL: lows 100 @5, 104 @17; highs 110 @11, 116 @23 -> both types +1 from bar 28
    o, h, l, c = path([(0, 104), (5, 100), (11, 110), (17, 104), (23, 116), (29, 110), (34, 113)], 35)
    r = MSD.row_values(bars_of(o, h, l, c))
    assert r["struct"][:28].tolist() == [0] * 28 and r["struct"][28:].tolist() == [1] * 7
    # LH + LL: the mirror -> -1 from bar 28
    r = MSD.row_values(bars_of(-o, -l, -h, -c))
    assert r["struct"][:28].tolist() == [0] * 28 and r["struct"][28:].tolist() == [-1] * 7
    # HH + LL (an expanding range): mixed -> 0 (the series ends before the low @29 is reported)
    o, h, l, c = path([(0, 104), (5, 100), (11, 110), (17, 96), (23, 116), (29, 106), (33, 107.6)], 34)
    r = MSD.row_values(bars_of(o, h, l, c))
    assert r["high_type"][28] == 1 and r["low_type"][28] == -1 and (r["struct"] == 0).all()


def test_swing_factor_thresholds():
    # swingL 100, swingH 110 (range 10): pct = (close - 100) / 10 * 100 in floats, as the script
    L, H = 100.0, 110.0
    cases = {100.0: 1,       # 0%: not < 0, not > 100, < 30 -> +1
             102.9: 1,       # 29%
             103.0: 0,       # 3 / 10 * 100 = 30.0 exactly in floats: not < 30, not > 70 -> 0
             105.0: 0,
             107.0: 0,       # 7 / 10 * 100 = 70.0 exactly: not > 70 -> 0
             107.1: -1,      # 71%
             110.0: -1,      # 100%: not > 100, > 70 -> -1
             110.001: 1,     # above 100% -> +1
             99.999: -1}     # below 0% -> -1
    got = MSD.swing_factor(list(cases), [H] * len(cases), [L] * len(cases), TICK)
    assert got.tolist() == list(cases.values())
    assert (103.0 - L) / (H - L) * 100 == 30 and (107.0 - L) / (H - L) * 100 == 70
    # na swings -> 0; a zero range -> one tick
    assert MSD.swing_factor([105.0, 105.0, 105.0], [nan, 110.0, nan], [100.0, nan, nan], TICK).tolist() == [0, 0, 0]
    assert MSD.swing_factor([100.0, 100.0004, 100.0008, 99.9], [100.0] * 4, [100.0] * 4, TICK).tolist() == [1, 0, -1, -1]


def test_a_row_before_its_first_closed_bar_scores_zero_but_counts_in_the_maximum(synth):
    rows = synth
    out = MSD.structure_dashboard(rows, "1D")
    first_w = int(np.searchsorted(rows["1D"].tc, rows["1W"].tc[0]))     # the 1D bar that closes the first week
    assert first_w > 0 and (out["max_score"] == 28).all()
    for f in ("struct", "ob", "fvg", "swing", "s"):
        assert (out[f"{f}_1W"][:first_w] == 0).all()
    assert np.array_equal(out["score"][:first_w], 3 * out["s_1D"][:first_w])


def test_dashboard_equals_the_plain_python_reference(synth):
    seen = set()
    for tf in MSD.CHART_TFS:
        out = MSD.structure_dashboard(synth, tf)
        ref = ref_dashboard(synth, tf, TICK)
        for k in ref:
            assert np.array_equal(out[k], ref[k]), (tf, k)
        names = MSD.ACTIVE_ROWS[tf]
        assert set(out) == {"label", "score", "max_score", "bos", "bos_trend"} | \
            {f"{f}_{r}" for r in names for f in ("s", "struct", "ob", "fvg", "swing")}
        assert np.array_equal(out["score"], sum(MSD.WEIGHTS[r] * out[f"s_{r}"] for r in names))
        for r in names:
            assert np.array_equal(out[f"s_{r}"], out[f"struct_{r}"].astype(int) + out[f"ob_{r}"] + out[f"fvg_{r}"]
                                  + out[f"swing_{r}"])
        assert len(np.unique(out["label"])) >= 3, tf
        seen |= set(np.unique(out["label"]).tolist())
    assert seen == {-2, -1, 0, 1, 2}                                     # every label occurs on these bars


def test_bos_and_bos_trend_follow_the_chart_row(synth):
    for tf in MSD.CHART_TFS:
        out = MSD.structure_dashboard(synth, tf)
        rv = MSD.row_values(synth[tf])
        assert np.array_equal(out["bos"], rv["bos"])
        trend, want = 0, []
        for v in rv["bos"]:
            trend = v if v != 0 else trend
            want.append(trend)
        assert out["bos_trend"].tolist() == want and set(np.unique(out["bos"])) == {-1, 0, 1}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_kernel_equals_the_transcription_on_random_bars(seed):
    for dec in (None, 1, 0):
        b = random_h1(12, seed, vol=1.0 + seed, dec=dec)
        mine, ref = MSD.row_values(b), ref_run(b)
        for k in ref:
            assert same(mine[k], ref[k]), (seed, dec, k)
        assert int(mine["n_ob"].max()) >= 3 and int(mine["n_fvg"].max()) == 6


def _calendar_market(symbol, days, seed, gold=True, start="2019-03-03", friday_short=None):
    """A synthetic TMarket: gold's sessions (Sunday from 22:05 UTC, a break 20:57-22:02, Friday to 20:57) or 24/7."""
    rng = np.random.default_rng(seed)
    t0 = TM.s_of(start)
    t = t0 + 60 * np.arange(days * 1440, dtype=np.int64)
    if gold:
        minute = (t % DAY) // 60
        weekday = ((t // DAY) + 4) % 7                           # 0 = Sunday
        keep = ~((minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)) & (weekday != 6)
        keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
        if friday_short is not None:                             # a holiday Friday: open only to 03:00
            fd = TM.s_of(friday_short)
            keep &= ~((t >= fd + 3 * 3600) & (t < fd + DAY))
        t = t[keep]
    n = len(t)
    base = 1300.0 if gold else 9000.0
    c = base + np.cumsum(rng.normal(0.0, 0.4 if gold else 8.0, n))
    o = np.concatenate(([base], c[:-1])) + rng.normal(0.0, 0.02, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.2 if gold else 4.0, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.2 if gold else 4.0, n))
    m1 = dict(t=t, o=o, h=h, l=l, c=c, spread_mean=np.full(n, 0.2), n=np.ones(n))
    return TM.TMarket(symbol, m1, None), m1


def test_weekly_bars_gold_sunday_stub_btc_monday_and_a_holiday_friday():
    mk, m1 = _calendar_market("XAUUSDm", 35, 1, gold=True, start="2019-03-03", friday_short="2019-03-22")
    d = mk.tbars("1D")
    w = MSD.weekly_bars(d, end_s=mk.end_s)
    # gold: the Sunday stub (22:05-24:00, 115 M1 bars) is merged into Monday's day bar (open Sunday 00:00, close
    # Tuesday 00:00), which starts the new week; a week closes with Friday's day bar (Saturday 00:00).
    sun = TM.s_of("2019-03-03")
    assert d.t[0] == sun and d.tc[0] == sun + 2 * DAY
    assert w.t[0] == sun and w.tc[0] == TM.s_of("2019-03-09") and w.week_start[0] == TM.s_of("2019-03-04")
    i0 = int(np.searchsorted(m1["t"], sun))
    i1 = int(np.searchsorted(m1["t"], TM.s_of("2019-03-09"))) - 1
    assert w.o[0] == m1["o"][i0] and w.c[0] == m1["c"][i1]
    assert w.h[0] == m1["h"][i0:i1 + 1].max() and w.l[0] == m1["l"][i0:i1 + 1].min()
    assert (w.d1 - w.d0 + 1)[:2].tolist() == [5, 5]
    # the holiday Friday 22 March (180 M1 bars) is merged into Monday 25 March: it moves into the next week, whose
    # bar opens on Friday 00:00; the holiday week ends with Thursday's day bar (Friday 00:00)
    k = int(np.flatnonzero(w.week_start == TM.s_of("2019-03-18"))[0])
    assert w.tc[k] == TM.s_of("2019-03-22") and w.t[k + 1] == TM.s_of("2019-03-22")
    assert w.tc[k + 1] == TM.s_of("2019-03-30") and (w.d1 - w.d0 + 1)[k:k + 2].tolist() == [4, 5]
    assert w.complete[:-1].all() and not w.complete[-1]                  # the data ends on Friday 5 April
    # BTC: seven day bars from Monday 00:00 to Monday 00:00
    mk, _ = _calendar_market("BTCUSDm", 21, 2, gold=False, start="2019-03-04")
    w = MSD.weekly_bars(mk.tbars("1D"), end_s=mk.end_s)
    assert w.t.tolist() == [TM.s_of("2019-03-04") + 7 * DAY * i for i in range(3)]
    assert w.tc.tolist() == [TM.s_of("2019-03-11") + 7 * DAY * i for i in range(3)]
    assert (w.d1 - w.d0 + 1).tolist() == [7, 7, 7] and w.complete.all()


def test_weekly_bars_a_forming_last_week_is_never_read_as_closed():
    # 24/7 data from Monday 4 March to Thursday 9 May 2019 00:00: nine full weeks and a forming one (Mon-Wed). Without
    # end_s that forming week would close at its last day bar (Thursday 00:00) and the last 1H bar would read it.
    mk, _ = _calendar_market("BTCUSDm", 66, 3, gold=False, start="2019-03-04")
    d = mk.tbars("1D")
    w_all = MSD.weekly_bars(d)
    w = MSD.weekly_bars(d, end_s=mk.end_s)
    assert len(w) == 10 and w_all.tc[-1] == TM.s_of("2019-05-09") and w_all.complete.all()
    assert not w.complete[-1] and w.tc[-1] == TM.s_of("2019-05-13") and w.complete[:-1].all()
    assert np.array_equal(w.tc[:-1], w_all.tc[:-1]) and np.array_equal(w.c, w_all.c)
    rows = MSD.rows_for(mk)
    assert rows["1W"].tc[-1] == TM.s_of("2019-05-13")
    h1 = rows["1H"]
    assert (np.searchsorted(w.tc, h1.tc, side="right") - 1).max() == len(w) - 2
    assert (np.searchsorted(w_all.tc, h1.tc, side="right") - 1)[-1] == len(w) - 1


def test_convergence_between_two_start_dates():
    # The map's pre-registered check: the row from its first bar and from 26 weeks later agree from some bar on (the
    # 6-slot arrays and the pivots forget the start), and disagree on the bar before that.
    b = random_h1(60, 9)
    for days in (0, 182):
        cv = MSD.convergence(b, days * DAY)
        a = int(np.searchsorted(b.t, b.t[0] + days * DAY))
        assert cv["late_start"] == b.t[a] and cv["first_agree"] is not None
        k = int(np.searchsorted(b.t, cv["first_agree"]))
        full = MSD.row_values(b)
        late = MSD.row_values(SimpleNamespace(**{f: getattr(b, f)[a:] for f in ("t", "tc", "o", "h", "l", "c")}))
        for f in ("struct", "ob", "fvg", "swing_h", "swing_l"):
            assert same(full[f][k:], late[f][k - a:]), (days, f)
        if days == 0:
            assert cv["n_disagree"] == 0 and k == 0
        else:
            assert cv["n_disagree"] > 0 and k > a
            assert not all(same(full[f][k - 1:k], late[f][k - 1 - a:k - a])
                           for f in ("struct", "ob", "fvg", "swing_h", "swing_l"))


# ───────────────────────────── model B ─────────────────────────────

def _closing(rows, tf, r):
    """Chart bars that close a bar of row r."""
    return np.flatnonzero(np.isin(rows[tf].tc, rows[r].tc))


def test_model_b_equals_a_at_every_higher_timeframe_close(synth):
    for tf in MSD.CHART_TFS:
        a = MSD.structure_dashboard(synth, tf, "A")
        b = MSD.structure_dashboard(synth, tf, "B")
        assert np.array_equal(a["bos"], b["bos"]) and np.array_equal(a["max_score"], b["max_score"])
        for r in MSD.ACTIVE_ROWS[tf][1:]:
            j = _closing(synth, tf, r)
            assert len(j) == len(synth[r].t)
            for f in ("s", "struct", "ob", "fvg", "swing"):
                assert np.array_equal(a[f"{f}_{r}"][j], b[f"{f}_{r}"][j]), (tf, r, f)
            assert not np.array_equal(a[f"s_{r}"], b[f"s_{r}"]), (tf, r)    # inside the bars the forming bar shows
        for f in (f"s_{tf}", f"struct_{tf}", f"swing_{tf}"):
            assert np.array_equal(a[f], b[f])


def _cut_row(bars, k, part):
    """Bars 0..k-1 of a row and, as its bar k, the partial bar ``part`` (o, h, l, c)."""
    return SimpleNamespace(t=bars.t[:k + 1], tc=bars.tc[:k + 1], o=np.append(bars.o[:k], part[0]),
                           h=np.append(bars.h[:k], part[1]), l=np.append(bars.l[:k], part[2]),
                           c=np.append(bars.c[:k], part[3]))


def test_model_b_inside_a_bar_equals_a_recomputation_on_the_data_cut_at_t(synth):
    rng = np.random.default_rng(5)
    for tf in MSD.CHART_TFS:
        chart = synth[tf]
        b = MSD.structure_dashboard(synth, tf, "B")
        for r in MSD.ACTIVE_ROWS[tf][1:]:
            row = synth[r]
            for j in rng.choice(np.arange(len(chart.t) // 4, len(chart.t)), 25, replace=False):
                k = int(np.searchsorted(row.t, chart.t[j], side="right") - 1)
                f = int(np.searchsorted(chart.t, row.t[k]))
                part = (chart.o[f], chart.h[f:j + 1].max(), chart.l[f:j + 1].min(), chart.c[j])
                rv = MSD.row_values(_cut_row(row, k, part))
                assert b[f"struct_{r}"][j] == rv["struct"][-1] and b[f"ob_{r}"][j] == rv["ob"][-1]
                assert b[f"fvg_{r}"][j] == rv["fvg"][-1]
                sw = MSD.swing_factor([chart.c[j]], rv["swing_h"][-1:], rv["swing_l"][-1:], TICK)[0]
                assert b[f"swing_{r}"][j] == sw, (tf, r, j)


# ───────────────────────────── 4. truncation invariance ─────────────────────────────

def _upto(bars, keep):
    return SimpleNamespace(**{k: (v[keep] if isinstance(v, np.ndarray) and v.shape == bars.t.shape else v)
                              for k, v in vars(bars).items()})


@pytest.mark.parametrize("tf", MSD.CHART_TFS)
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(synth, tf):
    rows = {r: SimpleNamespace(**{f: getattr(synth[r], f) for f in ("symbol", "t", "tc", "o", "h", "l", "c")})
            for r in synth}
    chart = rows[tf]
    full = {m: MSD.structure_dashboard(rows, tf, m) for m in ("A", "B")}
    rng = np.random.default_rng(11)
    for j in sorted(rng.choice(np.arange(30, len(chart.t) - 1), 12, replace=False)):
        T = int(chart.tc[j])
        opened = {r: _upto(rows[r], rows[r].t < T) for r in rows}           # with the forming bars ...
        scrambled = {}
        for r, b in opened.items():                                         # ... and with their prices scrambled
            b2 = SimpleNamespace(**vars(b))
            form = b.tc > T
            b2.h, b2.l, b2.c = b.h.copy(), b.l.copy(), b.c.copy()
            b2.h[form] += 1000.0
            b2.l[form] -= 1000.0
            b2.c[form] = b2.l[form]
            scrambled[r] = b2
        closed = {r: _upto(rows[r], rows[r].tc <= T) for r in rows}
        for m in ("A", "B"):
            for cut in (opened, scrambled) + ((closed,) if m == "A" else ()):
                part = MSD.structure_dashboard(cut, tf, m)
                for k in full[m]:
                    assert np.array_equal(part[k], full[m][k][:j + 1]), (tf, m, j, k)


@pytest.mark.parametrize("gold", [True, False])
def test_outputs_to_t_do_not_change_when_the_m1_data_after_t_is_removed(gold):
    sym = "XAUUSDm" if gold else "BTCUSDm"
    mk, m1 = _calendar_market(sym, 150, 4, gold=gold, start="2019-03-03" if gold else "2019-03-04")
    rows = MSD.rows_for(mk)
    full = {tf: MSD.structure_dashboard(rows, tf) for tf in MSD.CHART_TFS}
    rng = np.random.default_rng(12)
    h1 = rows["1H"]
    cand = np.arange(500, len(h1) - 1)
    wd = ((h1.tc[cand] - 1) // DAY + 4) % 7                                 # 0 = Sunday
    if gold:
        # a cut inside gold's weekend (after Friday's close, before Monday 00:00) is the documented conservative case
        # of weekly_bars(end_s): the day bars cannot show that the week is over
        cand = cand[(wd != 6) & ~((wd == 0) & (((h1.tc[cand] - 1) % DAY) < 23 * 3600 + 3599))]
    for T in h1.tc[sorted(rng.choice(cand, 6, replace=False))]:
        keep = m1["t"] < T
        cut = TM.TMarket(sym, {k: v[keep] for k, v in m1.items()}, int(T))
        rc = MSD.rows_for(cut)
        for tf in MSD.CHART_TFS:
            part = MSD.structure_dashboard(rc, tf)
            n = int(np.sum(rows[tf].tc <= T))
            assert n > 10 and np.array_equal(rc[tf].tc[:n], rows[tf].tc[:n])
            for k in full[tf]:
                assert np.array_equal(part[k][:n], full[tf][k][:n]), (sym, tf, int(T), k)


def test_inputs_are_checked(synth):
    with pytest.raises(ValueError):
        MSD.structure_dashboard(synth, "15m")
    with pytest.raises(ValueError):
        MSD.structure_dashboard(synth, "1H", model="C")
    with pytest.raises(ValueError):
        MSD.structure_dashboard({k: v for k, v in synth.items() if k != "1W"}, "1D")
    nosym = {k: SimpleNamespace(**{**vars(v), "symbol": None}) if hasattr(v, "__dict__") else v for k, v in synth.items()}
    with pytest.raises(ValueError):
        MSD.structure_dashboard(nosym, "1D")
    assert np.array_equal(MSD.structure_dashboard(nosym, "1D", mintick=TICK)["label"],
                          MSD.structure_dashboard(synth, "1D")["label"])
    bad = dict(synth)
    bad["1D"] = SimpleNamespace(**{**vars(synth["1D"]), "c": np.where(np.arange(len(synth["1D"].t)) == 5, nan,
                                                                      synth["1D"].c)})
    with pytest.raises(ValueError):
        MSD.structure_dashboard(bad, "1D")
    keep = [x.copy() for x in (synth["4H"].h, synth["4H"].c)]
    MSD.structure_dashboard(synth, "4H", "B")
    assert np.array_equal(keep[0], synth["4H"].h) and np.array_equal(keep[1], synth["4H"].c)


# ───────────────────────────── 5. real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            cache.clear()                                   # one symbol in memory at a time (a reload takes ~1 s)
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end="2024-07-01")
                rows = MSD.rows_for(mk)
                m1 = (mk.o, mk.h, mk.l, mk.c)
            cache[symbol] = (rows, m1)
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_smoke(symbol, real):
    rows, _ = real(symbol)
    for r, b in rows.items():
        assert len(b) > 300 and int(b.tc[-1]) <= TM.CUT_S, r                   # nothing from the hold-out
    assert rows["1W"].complete.all()                                       # the data ends on Monday 2024-07-01
    tick = MSD.MINTICK[symbol]
    for tf in MSD.CHART_TFS:
        out = MSD.structure_dashboard(rows, tf)
        n = len(rows[tf])
        names = MSD.ACTIVE_ROWS[tf]
        assert set(out) == {"label", "score", "max_score", "bos", "bos_trend"} | \
            {f"{f}_{r}" for r in names for f in ("s", "struct", "ob", "fvg", "swing")}
        for k, v in out.items():
            assert v.shape == (n,) and v.dtype.kind == "i" and np.isfinite(v.astype(float)).all(), (tf, k)
        assert (out["max_score"] == MSD.MAX_SCORE[tf]).all()
        assert np.array_equal(out["label"], MSD.label_of(out["score"], MSD.MAX_SCORE[tf]))
        assert np.array_equal(out["score"], sum(MSD.WEIGHTS[r] * out[f"s_{r}"] for r in names))
        for r in names:
            for f in ("struct", "ob", "fvg", "swing"):
                assert set(np.unique(out[f"{f}_{r}"])) <= {-1, 0, 1}, (tf, r, f)
            assert np.abs(out[f"s_{r}"]).max() <= 4
        assert set(np.unique(out["label"])) == {-2, -1, 0, 1, 2}, tf
        # from 2019 every row has values: swings, and the merged values equal htf_at of the row's own values
        a = int(np.searchsorted(rows[tf].tc, TM.s_of("2019-01-01")))
        for r in names:
            rv = MSD.row_values(rows[r])
            sh = TM.htf_at(rows[r], rv["swing_h"], rows[tf])
            sl = TM.htf_at(rows[r], rv["swing_l"], rows[tf])
            assert np.isfinite(sh[a:]).all() and np.isfinite(sl[a:]).all(), (tf, r)
            assert np.array_equal(out[f"swing_{r}"], MSD.swing_factor(rows[tf].c, sh, sl, tick))
            assert np.array_equal(out[f"struct_{r}"], TM.htf_at(rows[r], rv["struct"], rows[tf], default=0))
        # the BOS-trend has two sides and starts before 2019
        assert out["bos_trend"][a] != 0 and set(np.unique(out["bos_trend"][a:])) == {-1, 1}


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_kernel_equals_the_transcription_on_every_row(symbol, real):
    rows, _ = real(symbol)
    for r in MSD.ROWS:
        mine, ref = MSD.row_values(rows[r]), ref_run(rows[r])
        for k in ref:
            assert same(mine[k], ref[k]), (r, k)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_model_b_equals_a_at_closes_and_a_recomputation_inside(symbol, real):
    rows, (o1, h1, l1, c1) = real(symbol)
    rng = np.random.default_rng(13)
    for tf in MSD.CHART_TFS:
        a = MSD.structure_dashboard(rows, tf, "A")
        b = MSD.structure_dashboard(rows, tf, "B")
        chart = rows[tf]
        for r in MSD.ACTIVE_ROWS[tf][1:]:
            j = _closing(rows, tf, r)          # gold's week closes on Saturday 00:00, when no 1H bar closes
            assert len(j) > 0.75 * len(rows[r]) or (symbol, tf, r) == ("XAUUSDm", "1H", "1W")
            for f in ("s", "struct", "ob", "fvg", "swing"):
                assert np.array_equal(a[f"{f}_{r}"][j], b[f"{f}_{r}"][j]), (tf, r, f)
            # inside a bar: the recomputation with the bar cut at the chart close, from the M1 bars
            row = rows[r]
            day = rows["1D"]
            for jj in rng.choice(np.arange(len(chart) // 2, len(chart)), 8, replace=False):
                k = int(np.searchsorted(row.t, chart.t[jj], side="right") - 1)
                if not (k >= 0 and chart.tc[jj] <= row.tc[k]):
                    continue
                m0 = int(day.i0[row.d0[k]]) if r == "1W" else int(row.i0[k])
                m9 = int(chart.i1[jj])
                part = (o1[m0], h1[m0:m9 + 1].max(), l1[m0:m9 + 1].min(), c1[m9])
                rv = MSD.row_values(_cut_row(row, k, part))
                got = (b[f"struct_{r}"][jj], b[f"ob_{r}"][jj], b[f"fvg_{r}"][jj], b[f"swing_{r}"][jj])
                sw = MSD.swing_factor([chart.c[jj]], rv["swing_h"][-1:], rv["swing_l"][-1:], MSD.MINTICK[symbol])[0]
                assert got == (rv["struct"][-1], rv["ob"][-1], rv["fvg"][-1], sw), (tf, r, int(jj))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_truncation_invariance(symbol, real):
    rows, _ = real(symbol)
    for tf in MSD.CHART_TFS:
        full = MSD.structure_dashboard(rows, tf)
        for when in ("2020-11-17 13:00", "2022-06-01 00:00"):
            T = TM.s_of(when)
            j = int(np.searchsorted(rows[tf].tc, T, side="right") - 1)
            Tj = int(rows[tf].tc[j])
            cut = {r: _upto(SimpleNamespace(**{f: getattr(rows[r], f) for f in ("symbol", "t", "tc", "o", "h", "l", "c")}),
                            rows[r].t < Tj) for r in rows}
            part = MSD.structure_dashboard(cut, tf)
            for k in full:
                assert np.array_equal(part[k], full[k][:j + 1]), (tf, when, k)
