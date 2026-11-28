"""
Port A of the Heikin Ashi Trend Age script (``backtesting/research/tradeiq2_ind_ha.py``).

1. One hand-computed test per trap of the map's porting risks (``orb_session_swing_ha.md`` 4.6, "Risks": nine
   lines), named after it. Each also runs the wrong reading on the same bars (``PineScript``, a plain-Python
   bar-by-bar transcription of the script's computing lines with one switch per misreading) and checks that it
   answers differently. The bars are dyadic (every price a multiple of a power of 1/2), so every value is exact and
   the expected numbers are written out by hand.
2. The rest of the map's test list (4.6, "Tests"): the event sequences, the rare-age crossing once per streak,
   ``survive`` and SK / SN on a hand-made list of streaks; also the 5,000-streak cap, the panel helper, the keys,
   dtypes and input checks.
3. The port against the transcription on random bars, bit for bit (also with other inputs and a small cap).
4. Truncation invariance: the outputs up to bar T do not change when the bars after T are removed.
5. Real bars (skipped when the tick store is absent): both symbols, 1H / 4H / 1D (PREREG 6.8), from the data start
   to 2024-06-30 with the hold-out guard closed: no NaN where the contract says values exist, the structure of the
   streaks and events, the transcription bit for bit, truncation.

Every test runs with the guard pointed at an empty folder (FINALISTS.md absent: nothing at or after 2024-07-01).
Line numbers l. are those of the plain-text copy of the script the study ported from.
"""

from __future__ import annotations

import math
from bisect import bisect_left, insort

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_ha as HA
from backtesting.research import tradeiq_market as TM

NAN = math.nan
SYMS = ("XAUUSDm", "BTCUSDm")
ARRAY_KEYS = tuple(k for k in HA.KEYS if k != "streaks")
DTYPES = {"ha_o": np.float64, "ha_h": np.float64, "ha_l": np.float64, "ha_c": np.float64, "dir": np.int8,
          "phase": np.int8, "flip": np.bool_, "age": np.int32, "strong_run": np.int32, "weak_run": np.int32,
          "ev_ind": np.bool_, "ev_first_strong": np.bool_, "pct_below": np.float64, "rare_now": np.bool_}
STREAK_DTYPES = {"start_bar": np.int64, "end_bar": np.int64, "dir": np.int8, "length": np.int32,
                 "had_strong": np.bool_, "strong_at": np.int32, "ran_5_after_strong": np.bool_}
S, T_, W_, I_ = HA.STRONG, HA.STEADY, HA.WEAK, HA.INDECISION


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The study folder seen by the hold-out guard: an empty tmp folder (the hold-out is closed)."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


def same(a, b) -> bool:
    """Equal values (bit for bit up to the sign of zero), NaN where the other is NaN, same shape."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def streaks_upto(st: pd.DataFrame, upto: int) -> pd.DataFrame:
    """The streaks finished by the close of bar ``upto - 1`` (their flip bar ``end_bar + 1`` at most ``upto - 1``)."""
    return st[st["end_bar"] + 1 <= upto - 1].reset_index(drop=True)


def frames_equal(x: pd.DataFrame, y: pd.DataFrame) -> bool:
    if tuple(x.columns) != HA.STREAK_COLUMNS or tuple(y.columns) != HA.STREAK_COLUMNS or len(x) != len(y):
        return False
    return all(x[k].dtype == y[k].dtype and np.array_equal(x[k].to_numpy(), y[k].to_numpy()) for k in x.columns)


def outputs_equal(x, y, upto=None) -> bool:
    """Every key of the contract equal (floats bit for bit, NaN to NaN; ints and bools exactly, same dtype), on bars
    [0, upto); the streaks then those finished by bar upto - 1."""
    for k in ARRAY_KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if upto is not None:
            a, b = a[:upto], b[:upto]
        if a.dtype != b.dtype:
            return False
        if a.dtype == np.float64:
            if not same(a, b):
                return False
        elif not np.array_equal(a, b):
            return False
    sx, sy = x["streaks"], y["streaks"]
    if upto is not None:
        sx, sy = streaks_upto(sx, upto), streaks_upto(sy, upto)
    return frames_equal(sx.reset_index(drop=True), sy.reset_index(drop=True))


def arrays(bars):
    """(o, h, l, c) float64 arrays from a list of (open, high, low, close)."""
    return tuple(np.array(v, dtype=np.float64) for v in zip(*bars))


# ───────────────────────────── the transcription (the script, bar by bar) ─────────────────────────────

class PineScript:
    """
    The script's computing lines transcribed bar by bar in plain Python floats from the source (l.79-94, 99-160,
    166-173, 204-212), plus the contract's ``weak_run`` and ``min_streaks``; ``run`` returns the contract's dict.
    Switches (the default is the script as written, read as the contract reads it); every other value is a
    misreading a trap test must tell apart:

      ha_start   "oc2"       l.81 ``(open + close) / 2`` on the first bar      | "open": haO = open on the first bar
      tie        "bull"      l.85 ``haC >= haO``                              | "bear": ``haC > haO`` is bullish
      order      ("ind", "strong", "weak")  l.94                                | any other order of the three tests
      zero       "strong"    l.94: a zero range is STRONG (0 <= 0)             | "excluded": STRONG needs rng > 0
      weak_ref   "body1"     l.94 ``dir == dir[1] and body < body[1]``
                 | "last_trend": compare with the last non-INDECISION candle of the streak
                 | "real": compare the real bodies ``|close - open|``     | "any_colour": no colour test
      ind        "after_reset"  l.147 resets strongRun, then l.156          | "before_reset": evInd from the run
                                                                              strongRun had before the flip
      run_reset  True        l.147                                         | False: strongRun not reset at a flip
      first      "script"    l.146 resets strongAt, l.158 after the flip   | "not_on_flip": the check only on
                                                                              continuing bars | "no_reset": strongAt
                                                                              never reset
      push       "finished"  l.127-130: ``age`` into ``sDir``'s array      | "new_colour": into ``dir``'s array |
                                                                              "age_plus_1": the flip bar counted
      rare       "causal"    PREREG 6.8: l.210-212 at every bar           | "last_bar": the script as written
                                                                              (only ``if barstate.islast``)
      keep       5000        l.131-132                                     | None: every finished streak
      count      "loop"      l.170-172                                     | "bisect": a sorted copy (the same
                                                                              counts, fast enough for real bars)
      panel      False       True: also the panel's numbers at every bar (l.242-284), into ``self.panels``

    The streak records (``streaks``) are always the true streaks; a misread push only changes the arrays.
    """

    def __init__(self, strong_tol=0.05, doji_max=0.25, ahead_n=5, rare_pct=90, min_streaks=50, *, ha_start="oc2",
                 tie="bull", order=("ind", "strong", "weak"), zero="strong", weak_ref="body1", ind="after_reset",
                 run_reset=True, first="script", push="finished", rare="causal", keep=5000, count="loop",
                 panel=False):
        self.strong_tol, self.doji_max, self.ahead_n, self.rare_pct = strong_tol, doji_max, ahead_n, rare_pct
        self.min_streaks = min_streaks
        self.ha_start, self.tie, self.order, self.zero, self.weak_ref = ha_start, tie, tuple(order), zero, weak_ref
        self.ind, self.run_reset, self.first, self.push, self.rare = ind, run_reset, first, push, rare
        self.keep, self.count, self.panel = keep, count, panel
        self.panels = []

    def _pct(self, arr, srt, v):
        """pctBelow(a, v), l.166-173."""
        n = len(arr)
        if n == 0:
            return NAN
        if self.count == "loop":
            c = 0
            for x in arr:
                if x < v:
                    c += 1
        else:
            c = bisect_left(srt, v)
        return 100.0 * c / n

    def run(self, o, h, l, c):
        o, h, l, c = ([float(v) for v in x] for x in (o, h, l, c))
        n = len(c)
        res = {k: [] for k in ARRAY_KEYS}
        arrs = {1: [], -1: []}                     # var array<int> bullL / bearL (l.99-100), oldest first
        srt = {1: [], -1: []}                      # sorted copies ("bisect")
        total = {1: 0, -1: 0}
        sn = {1: 0, -1: 0}                         # bullSN / bearSN (l.101, 103)
        sk = {1: 0, -1: 0}                         # bullSK / bearSK (l.102, 104)
        s_dir, age, strong_at, strong_run = 0, 0, 0, 0      # var int sDir, age, strongAt, strongRun (l.106-109)
        weak_run, start = 0, 0
        rows = []
        ha_o1 = ha_c1 = dir1 = body1 = rbody1 = None
        trend_body = None                          # "last_trend": the last non-INDECISION body of the streak
        for t in range(n):
            # l.79-83
            ha_c = (o[t] + h[t] + l[t] + c[t]) / 4.0
            if ha_o1 is None:
                ha_o = (o[t] + c[t]) / 2.0 if self.ha_start == "oc2" else o[t]
            else:
                ha_o = (ha_o1 + ha_c1) / 2.0
            ha_h = max(h[t], max(ha_o, ha_c))
            ha_l = min(l[t], min(ha_o, ha_c))
            # l.85-90
            d = (1 if ha_c >= ha_o else -1) if self.tie == "bull" else (1 if ha_c > ha_o else -1)
            rng = ha_h - ha_l
            body = abs(ha_c - ha_o)
            up_w = ha_h - max(ha_o, ha_c)
            lo_w = min(ha_o, ha_c) - ha_l
            opp_w = lo_w if d == 1 else up_w
            # l.93-94
            is_ind = rng > 0 and body <= self.doji_max * rng and min(up_w, lo_w) >= 0.1 * rng
            is_strong = opp_w <= self.strong_tol * rng and (self.zero == "strong" or rng > 0)
            if self.weak_ref == "body1":
                is_weak = dir1 is not None and d == dir1 and body < body1
            elif self.weak_ref == "last_trend":
                is_weak = dir1 is not None and d == dir1 and trend_body is not None and body < trend_body
            elif self.weak_ref == "real":
                is_weak = dir1 is not None and d == dir1 and abs(c[t] - o[t]) < rbody1
            elif self.weak_ref == "any_colour":
                is_weak = body1 is not None and body < body1
            else:
                raise ValueError(self.weak_ref)
            tests = {"ind": (is_ind, 3), "strong": (is_strong, 0), "weak": (is_weak, 2)}
            phase = 1
            for name in self.order:
                hit, code = tests[name]
                if hit:
                    phase = code
                    break
            # l.115-154
            flip = s_dir != 0 and d != s_dir
            ev_first = False
            run_before = strong_run
            if s_dir == 0:
                s_dir, age, start = d, 1, t
            elif flip:
                pushed = age + 1 if self.push == "age_plus_1" else age
                col = d if self.push == "new_colour" else s_dir
                arrs[col].append(pushed)
                insort(srt[col], pushed)
                total[col] += 1
                if self.keep is not None and len(arrs[col]) > self.keep:
                    old = arrs[col].pop(0)
                    del srt[col][bisect_left(srt[col], old)]
                if strong_at > 0:
                    sn[s_dir] += 1
                    sk[s_dir] += 1 if age - strong_at >= self.ahead_n else 0
                rows.append((start, t - 1, s_dir, age, strong_at))
                s_dir, age, start = d, 1, t
                if self.first != "no_reset":
                    strong_at = 0
                if self.run_reset:
                    strong_run = 0
                weak_run = 0
                trend_body = None
            else:
                age += 1
            if t == 0:
                trend_body = None
            # l.156-160
            ev_ind = phase == 3 and (run_before if (self.ind == "before_reset" and flip) else strong_run) >= 2
            strong_run = strong_run + 1 if phase == 0 else 0
            if phase == 0 and strong_at == 0 and not (self.first == "not_on_flip" and flip):
                strong_at = age
                ev_first = True
            weak_run = weak_run + 1 if phase == 2 else 0
            # l.204-212
            cur, cur_s = arrs[s_dir], srt[s_dir]
            p_now = self._pct(cur, cur_s, age)
            p_prev = self._pct(cur, cur_s, age - 1) if age > 1 else 0.0
            rare = (not math.isnan(p_now) and p_now >= self.rare_pct
                    and (math.isnan(p_prev) or p_prev < self.rare_pct or age == 1)
                    and total[s_dir] >= self.min_streaks)
            if self.rare == "last_bar":
                rare = rare and t == n - 1
            if self.panel:                                   # l.242-284
                r = sum(1 for x in cur if x >= age)
                g = sum(1 for x in cur if x >= age + self.ahead_n)
                self.panels.append({"dir": s_dir, "n": len(cur), "age": age, "pct_below": p_now, "reached": r,
                                    "went": g, "sn": sn[s_dir], "sk": sk[s_dir]})
            for k, v in (("ha_o", ha_o), ("ha_h", ha_h), ("ha_l", ha_l), ("ha_c", ha_c), ("dir", d),
                         ("phase", phase), ("flip", flip), ("age", age), ("strong_run", strong_run),
                         ("weak_run", weak_run), ("ev_ind", ev_ind), ("ev_first_strong", ev_first),
                         ("pct_below", p_now), ("rare_now", rare)):
                res[k].append(v)
            ha_o1, ha_c1, dir1, body1, rbody1 = ha_o, ha_c, d, body, abs(c[t] - o[t])
            if phase != 3:
                trend_body = body
        out = {k: np.array(v, dtype=DTYPES[k]) for k, v in res.items()}
        rec = np.array(rows, dtype=np.int64).reshape(-1, 5)
        had = rec[:, 4] > 0
        out["streaks"] = pd.DataFrame({
            "start_bar": rec[:, 0].astype(np.int64), "end_bar": rec[:, 1].astype(np.int64),
            "dir": rec[:, 2].astype(np.int8), "length": rec[:, 3].astype(np.int32), "had_strong": had,
            "strong_at": rec[:, 4].astype(np.int32),
            "ran_5_after_strong": had & (rec[:, 3] - rec[:, 4] >= self.ahead_n)}, columns=list(HA.STREAK_COLUMNS))
        return out


def pine(bars, **kw):
    return PineScript(**kw).run(*bars)


# ───────────────────────────── bar builders ─────────────────────────────

SHAPES = {"S": (1.0, 0.0, 0.5),       # (HA body, wick against the colour, wick with the colour): STRONG
          "T": (1.0, 0.5, 0.5),       # STEADY (the body equals a STRONG body, so never WEAK after one)
          "I": (0.25, 1.0, 1.0)}      # INDECISION


def build(items, p0=100.0):
    """
    Bars whose Heikin Ashi candles have the given colours and shapes. Bar 0 is flat at ``p0`` (O = H = L = C): its HA
    candle has zero range (haO = haC = p0), so it is bullish (a tie) and STRONG. Each item is ``(kind, d)`` with kind
    in ``SHAPES``, ``("W", d, body)`` (a candle with that body and both wicks equal to it: neither STRONG nor
    INDECISION, so WEAK after a larger body of its colour), ``("Z",)`` (a tie: HA body 0, wicks 1 and 1, so a
    bullish INDECISION) or ``("F",)`` (a flat bar at the HA open: a zero-range, bullish, STRONG candle). The bar has
    H = haH, L = haL and O = C = (4 haC - H - L) / 2, which must lie in [L, H] (checked). With these shapes every
    price is dyadic with a small denominator, hence every value exact.
    """
    bars = [(p0, p0, p0, p0)]
    hao, hac = p0, p0
    for it in items:
        hao = (hao + hac) / 2.0
        if it[0] == "F":
            bars.append((hao, hao, hao, hao))
            hac = hao
            continue
        if it[0] == "W":
            _, d, b = it
            body, opp, wt = b, b, b
        elif it[0] == "Z":
            d, (body, opp, wt) = 1, (0.0, 1.0, 1.0)
        else:
            body, opp, wt = SHAPES[it[0]]
            d = it[1]
        hac = hao + d * body
        if d == 1:
            hi, lo = hac + wt, hao - opp
        else:
            hi, lo = hao + opp, hac - wt
        oc = (4.0 * hac - hi - lo) / 2.0
        assert lo <= oc <= hi, it
        bars.append((oc, hi, lo, oc))
    return arrays(bars)


def colour_bars(runs):
    """Bars whose HA colours make streaks of the given lengths, alternating from bullish (bar 0 is the first bullish
    candle), all of shape S (STRONG): ``runs = [3, 2, 1]`` gives B B B R R B."""
    items = []
    d = 1
    for i, k in enumerate(runs):
        items += [("S", d)] * (k - 1 if i == 0 else k)
        d = -d
    return build(items)


def random_built(n, seed):
    """``n`` bars of random ``build`` shapes (STRONG, STEADY, INDECISION, WEAK-shaped with bodies 1/2, 1/4, 1/8, ties
    and flat bars) with a colour that changes with probability 0.3: exact ties, zero ranges and WEAK runs."""
    rng = np.random.default_rng(seed)
    kinds = ("S", "T", "I", "W", "Z", "F")
    prob = (0.35, 0.15, 0.2, 0.2, 0.05, 0.05)
    items, d = [], 1
    for _ in range(n - 1):
        if rng.random() < 0.3:
            d = -d
        k = kinds[int(rng.choice(6, p=prob))]
        if k == "W":
            items.append(("W", d, float(rng.choice([0.5, 0.25, 0.125]))))
        elif k in ("Z", "F"):
            items.append((k,))
        else:
            items.append((k, d))
    return build(items, p0=1000.0)


def random_bars(n, seed, decimals=None, flat_every=0):
    """A random walk of OHLC bars; ``decimals`` rounds every price (ties haC == haO become common); ``flat_every``
    inserts runs of 80 flat bars (O = H = L = C) so that zero-range HA candles occur."""
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n))
    o = np.r_[100.0, c[:-1]] + rng.normal(0.0, 0.3, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.6, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.6, n))
    if flat_every:
        for s in range(flat_every, n - 80, flat_every):
            p = c[s - 1]
            o[s:s + 80] = h[s:s + 80] = l[s:s + 80] = c[s:s + 80] = p
    if decimals is not None:
        o, h, l, c = (np.round(x, decimals) for x in (o, h, l, c))
        h = np.maximum(h, np.maximum(o, c))
        l = np.minimum(l, np.minimum(o, c))
    return o, h, l, c


# ───────────────────────────── 1. the traps (map 4.6, "Risks"), one test each ─────────────────────────────

TRAP1 = [(10, 14, 9, 12), (12, 13, 11.5, 13), (13, 13.5, 12, 12.5), (12.5, 12.75, 11, 11.25)]
TRAP2 = [(100, 100, 100, 100), (98.75, 100, 98.5, 98.75), (99.5, 100.5, 98.5, 99.5), (98.25, 99.5, 98, 98.25)]
TRAP3 = [(100, 100, 100, 100), (101.25, 101.5, 100, 101.25), (101.125, 101.25, 100.5, 101.125),
         (101.125, 102, 99.75, 101.125), (100.9375, 102.5, 100.625, 100.9375)]
TRAP4 = [(100, 100, 100, 100), (101.25, 101.5, 100, 101.25), (100.5, 100.5, 100.5, 100.5),
         (99.25, 100.5, 99, 99.25), (100, 100, 100, 100)]
TRAP5 = [(100, 100, 100, 100), (101.25, 101.5, 100, 101.25), (101.25, 101.5, 100, 101.25),
         (100.9375, 101.625, 100, 100.9375), (101.1875, 101.3125, 100.5625, 101.1875),
         (101.125, 101.1875, 100.8125, 101.125), (101.09375, 101.125, 100.9375, 101.09375),
         (100.984375, 101.0625, 100.96875, 100.984375)]
TRAP6 = [(100, 100, 100, 100), (101.25, 101.5, 100, 101.25), (100.125, 101.5, 99.25, 100.125),
         (101.625, 101.875, 100.375, 101.625), (102.125, 102.375, 100.875, 102.125),
         (100.125, 101.375, 99.875, 100.125), (100.5, 101.875, 99.625, 100.5), (99.5, 100.75, 99.25, 99.5),
         (98.75, 100.75, 98.75, 98.75), (99.375, 100.75, 98.5, 99.375), (98.375, 99.625, 98.125, 98.375),
         (97.875, 99.125, 97.625, 97.875), (98.25, 99.625, 97.375, 98.25), (98.125, 99.5, 97.25, 98.125)]


def test_trap1_the_ha_open_start_value():
    """l.81: haO = (open + close) / 2 on the first bar, then (haO[1] + haC[1]) / 2. By hand:
    bar 0 (10, 14, 9, 12): haC = 45/4 = 11.25, haO = (10 + 12)/2 = 11, haH = 14, haL = 9;
    bar 1 (12, 13, 11.5, 13): haC = 49.5/4 = 12.375, haO = (11 + 11.25)/2 = 11.125, haH = 13, haL = 11.125;
    bar 2 (13, 13.5, 12, 12.5): haC = 51/4 = 12.75, haO = (11.125 + 12.375)/2 = 11.75, haH = 13.5, haL = 11.75;
    bar 3 (12.5, 12.75, 11, 11.25): haC = 47.5/4 = 11.875, haO = (11.75 + 12.75)/2 = 12.25, haH = 12.75, haL = 11."""
    bars = arrays(TRAP1)
    out = HA.heikin_ashi(*bars)
    assert out["ha_o"].tolist() == [11.0, 11.125, 11.75, 12.25]
    assert out["ha_c"].tolist() == [11.25, 12.375, 12.75, 11.875]
    assert out["ha_h"].tolist() == [14.0, 13.0, 13.5, 12.75]
    assert out["ha_l"].tolist() == [9.0, 11.125, 11.75, 11.0]
    # bar 0: body 0.25 <= 0.25*5, wicks 2.75 / 2 >= 0.5: INDECISION; bars 1-2: no lower wick: STRONG; bar 3: bearish
    # (11.875 < 12.25), body 0.375 <= 0.4375, wicks 0.5 / 0.875 >= 0.175: INDECISION, a flip
    assert out["dir"].tolist() == [1, 1, 1, -1] and out["phase"].tolist() == [I_, S, S, I_]
    assert out["flip"].tolist() == [False, False, False, True] and out["age"].tolist() == [1, 2, 3, 1]
    assert out["ev_first_strong"].tolist() == [False, True, False, False]
    assert not out["ev_ind"].any()                       # bar 3 is a flip bar (trap 6)
    assert outputs_equal(out, pine(bars))
    wrong = pine(bars, ha_start="open")                  # haO = open on the first bar: 10, 10.625, 11.5, 12.125
    assert wrong["ha_o"].tolist() == [10.0, 10.625, 11.5, 12.125]
    assert not same(wrong["ha_o"], out["ha_o"])


def test_trap2_a_tie_counts_as_bullish():
    """l.85: haC >= haO is bullish. Bar 0 is flat at 100 (haC = haO = 100); bar 1 a bearish STRONG candle (haO 100,
    haC 99); bar 2 (99.5, 100.5, 98.5, 99.5): haO = (100 + 99)/2 = 99.5 and haC = 398/4 = 99.5, a tie: bullish, so a
    flip (an INDECISION: body 0, wicks 1 and 1); bar 3 bearish again (haO 99.5, haC 98.5)."""
    bars = arrays(TRAP2)
    out = HA.heikin_ashi(*bars)
    assert out["ha_o"].tolist() == [100.0, 100.0, 99.5, 99.5] and out["ha_c"].tolist() == [100.0, 99.0, 99.5, 98.5]
    assert out["ha_c"][0] == out["ha_o"][0] and out["ha_c"][2] == out["ha_o"][2]
    assert out["dir"].tolist() == [1, -1, 1, -1]
    assert out["flip"].tolist() == [False, True, True, True] and out["age"].tolist() == [1, 1, 1, 1]
    assert out["phase"].tolist() == [S, S, I_, S]
    st = out["streaks"]
    assert st["dir"].tolist() == [1, -1, 1] and st["length"].tolist() == [1, 1, 1]
    assert st["start_bar"].tolist() == [0, 1, 2] and st["end_bar"].tolist() == [0, 1, 2]
    assert outputs_equal(out, pine(bars))
    wrong = pine(bars, tie="bear")                       # a tie read as bearish: one bearish streak of 4
    assert wrong["dir"].tolist() == [-1, -1, -1, -1] and not wrong["flip"].any()
    assert wrong["age"].tolist() == [1, 2, 3, 4]


def test_trap3_the_order_of_the_phase_tests():
    """l.94: INDECISION, then STRONG, then WEAK, then STEADY. Bars 0-2 are bullish STRONG (no lower wick) with bodies
    0, 1, 0.5: bar 2's smaller body would be WEAK, but STRONG comes first. Bar 3 (haO 100.75, haC 101, haH 102,
    haL 99.75): body 0.25 <= 0.25 * 2.25 and wicks 1 / 1 >= 0.225: INDECISION, though its body is smaller than bar
    2's (WEAK comes after). Bar 4 (haO 100.875, haC 101.25, haH 102.5, haL 100.625): body 0.375 <= 0.46875, wicks
    1.25 / 0.25 >= 0.1875: INDECISION; its lower wick 0.25 is also <= 0.15 * 1.875 = 0.28125, so with strong_tol 0.15
    it meets STRONG too, and INDECISION still wins."""
    bars = arrays(TRAP3)
    out = HA.heikin_ashi(*bars)
    assert out["ha_o"].tolist() == [100.0, 100.0, 100.5, 100.75, 100.875]
    assert out["ha_c"].tolist() == [100.0, 101.0, 101.0, 101.0, 101.25]
    assert out["phase"].tolist() == [S, S, S, I_, I_]
    assert out["ev_ind"].tolist() == [False, False, False, True, False]
    tol = HA.heikin_ashi(*bars, strong_tol=0.15)
    assert tol["phase"].tolist() == [S, S, S, I_, I_]
    assert outputs_equal(out, pine(bars)) and outputs_equal(tol, pine(bars, strong_tol=0.15))
    assert pine(bars, order=("weak", "ind", "strong"))["phase"].tolist() == [S, S, W_, W_, I_]
    assert pine(bars, order=("ind", "weak", "strong"))["phase"].tolist() == [S, S, W_, I_, I_]
    assert pine(bars, strong_tol=0.15, order=("strong", "ind", "weak"))["phase"].tolist() == [S, S, S, I_, S]
    # with the default tolerance (0.05 < 0.1) STRONG and INDECISION exclude each other: their order cannot matter
    assert pine(bars, order=("strong", "ind", "weak"))["phase"].tolist() == [S, S, S, I_, I_]


def test_trap4_a_zero_range_bar_is_strong():
    """l.94: oppW <= strongTol * rng holds as 0 <= 0 when rng == 0. Bar 0 is flat at 100 (haO = haC = 100); bar 2 is
    flat at 100.5 = (100 + 101)/2, its haO; bar 4 is flat at 100 = (100.5 + 99.5)/2. Each has haO = haC = haH = haL:
    a tie (bullish) and STRONG; bar 4 is a flip to bullish and the new streak's first STRONG candle."""
    bars = arrays(TRAP4)
    out = HA.heikin_ashi(*bars)
    assert out["ha_o"].tolist() == [100.0, 100.0, 100.5, 100.5, 100.0]
    assert out["ha_c"].tolist() == [100.0, 101.0, 100.5, 99.5, 100.0]
    assert out["ha_h"].tolist() == [100.0, 101.5, 100.5, 100.5, 100.0]
    assert out["ha_l"].tolist() == [100.0, 100.0, 100.5, 99.0, 100.0]
    assert (out["ha_h"] - out["ha_l"]).tolist() == [0.0, 1.5, 0.0, 1.5, 0.0]
    assert out["phase"].tolist() == [S, S, S, S, S] and out["dir"].tolist() == [1, 1, 1, -1, 1]
    assert out["flip"].tolist() == [False, False, False, True, True] and out["age"].tolist() == [1, 2, 3, 1, 1]
    assert out["strong_run"].tolist() == [1, 2, 3, 1, 1]
    assert out["ev_first_strong"].tolist() == [True, False, False, True, True]
    assert outputs_equal(out, pine(bars))
    wrong = pine(bars, zero="excluded")         # STRONG needs a range: bar 0 STEADY, bar 2 WEAK (0 < 1), bar 4 STEADY
    assert wrong["phase"].tolist() == [T_, S, W_, S, T_]
    assert wrong["ev_first_strong"].tolist() == [False, True, False, True, False]


def test_trap5_weak_compares_with_the_previous_bars_body():
    """l.94: WEAK = same colour as the previous candle and body < body[1], whatever the previous candle's phase. HA
    bodies 0, 1, 0.5, 0.125, 0.25, 0.125, 0.0625 (bullish), then 0.03125 (bearish). Bar 2 (wicks 0.5 / 0.5): smaller
    than bar 1's: WEAK. Bar 3: INDECISION. Bar 4 (0.25, wicks 0.25 / 0.25): larger than the doji's 0.125 before it:
    STEADY, although smaller than bar 2's. Bars 5-6: WEAK twice (weak_run 1, 2). Bar 7: a smaller body but a flip
    (the colour differs from the previous candle's): STEADY, and weak_run is reset."""
    bars = arrays(TRAP5)
    out = HA.heikin_ashi(*bars)
    body = np.abs(out["ha_c"] - out["ha_o"])
    assert body.tolist() == [0.0, 1.0, 0.5, 0.125, 0.25, 0.125, 0.0625, 0.03125]
    assert out["dir"].tolist() == [1, 1, 1, 1, 1, 1, 1, -1]
    assert out["phase"].tolist() == [S, S, W_, I_, T_, W_, W_, T_]
    assert out["weak_run"].tolist() == [0, 0, 1, 0, 0, 1, 2, 0]
    assert outputs_equal(out, pine(bars))
    last = pine(bars, weak_ref="last_trend")    # against the last non-INDECISION body: bar 4 becomes WEAK
    assert last["phase"].tolist() == [S, S, W_, I_, W_, W_, W_, T_]
    assert last["weak_run"].tolist() == [0, 0, 1, 0, 1, 2, 3, 0]
    real = pine(bars, weak_ref="real")          # the real bodies (all 0 here): no WEAK at all
    assert real["phase"].tolist() == [S, S, T_, I_, T_, T_, T_, T_]
    anyc = pine(bars, weak_ref="any_colour")    # no colour test: the flip bar becomes WEAK
    assert anyc["phase"].tolist() == [S, S, W_, I_, T_, W_, W_, W_]


def test_trap6_strong_run_is_reset_at_a_flip_before_ev_ind():
    """l.147 (strongRun := 0 at a flip) runs before l.156 (evInd := phase == 3 and strongRun >= 2). Colours
    + + - + + - - - - - - - - -, phases S S I S S S I S T I S S I I:
    bar 2: a bearish doji right after two bullish STRONG candles, but a flip bar: no evInd;
    bar 6: a bearish doji after bullish S S and the bearish S of the flip bar 5: strongRun is 1, no evInd;
    bar 9: S T I: no evInd; bar 12: S S I of one streak: evInd; bar 13: a second doji: strongRun 0, no evInd."""
    bars = arrays(TRAP6)
    out = HA.heikin_ashi(*bars)
    assert out["dir"].tolist() == [1, 1, -1, 1, 1, -1, -1, -1, -1, -1, -1, -1, -1, -1]
    assert out["phase"].tolist() == [S, S, I_, S, S, S, I_, S, T_, I_, S, S, I_, I_]
    assert out["flip"].tolist() == [False, False, True, True, False, True] + [False] * 8
    assert out["age"].tolist() == [1, 2, 1, 1, 2, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert out["strong_run"].tolist() == [1, 2, 0, 1, 2, 1, 0, 1, 0, 0, 1, 2, 0, 0]
    assert np.flatnonzero(out["ev_ind"]).tolist() == [12]
    assert outputs_equal(out, pine(bars))
    assert np.flatnonzero(pine(bars, ind="before_reset")["ev_ind"]).tolist() == [2, 12]
    no_reset = pine(bars, run_reset=False)
    assert np.flatnonzero(no_reset["ev_ind"]).tolist() == [2, 6, 12]
    assert no_reset["strong_run"].tolist() == [1, 2, 0, 1, 2, 3, 0, 1, 0, 0, 1, 2, 0, 0]


def test_trap7_ev_first_strong_fires_on_the_flip_bar():
    """l.146 resets strongAt at a flip and l.158-160 then runs on the flip bar itself: the STRONG flip bars 3 and 5 of
    the trap-6 bars are their streaks' first STRONG candles, at age 1 (bar 0 is the first streak's)."""
    bars = arrays(TRAP6)
    out = HA.heikin_ashi(*bars)
    ev = np.flatnonzero(out["ev_first_strong"]).tolist()
    assert ev == [0, 3, 5]
    assert out["flip"][[3, 5]].all() and out["age"][[3, 5]].tolist() == [1, 1]
    st = out["streaks"]                                  # bars 0-1 (bull), 2 (bear, a doji only), 3-4 (bull)
    assert st["start_bar"].tolist() == [0, 2, 3] and st["end_bar"].tolist() == [1, 2, 4]
    assert st["strong_at"].tolist() == [1, 0, 1] and st["had_strong"].tolist() == [True, False, True]
    assert outputs_equal(out, pine(bars))
    assert np.flatnonzero(pine(bars, first="not_on_flip")["ev_first_strong"]).tolist() == [0, 4, 7]
    assert np.flatnonzero(pine(bars, first="no_reset")["ev_first_strong"]).tolist() == [0]


def test_trap8_streak_lengths_are_pushed_at_the_flip():
    """l.126-130: at the flip bar the finished streak's age (not counting the flip bar) goes into the array of ITS
    colour; the current streak's percentage reads the array of the current colour. Colours B B B R R B R R R B B:
    finished streaks bull 3 (bars 0-2), bear 2 (3-4), bull 1 (5), bear 3 (6-8). pct_below:
    bars 0-4 NaN (no finished streak of their colour); bar 5 bull age 1 vs [3]: 0; bar 6 bear age 1 vs [2]: 0;
    bar 7 age 2: 0; bar 8 age 3: 2 < 3: 100; bar 9 bull age 1 vs [3, 1]: 0; bar 10 age 2: 1 < 2: 50."""
    bars = colour_bars([3, 2, 1, 3, 2])
    out = HA.heikin_ashi(*bars)
    assert out["dir"].tolist() == [1, 1, 1, -1, -1, 1, -1, -1, -1, 1, 1]
    assert (out["phase"] == S).all()
    assert same(out["pct_below"], [NAN] * 5 + [0.0, 0.0, 0.0, 100.0, 0.0, 50.0])
    st = out["streaks"]
    assert st["start_bar"].tolist() == [0, 3, 5, 6] and st["end_bar"].tolist() == [2, 4, 5, 8]
    assert st["dir"].tolist() == [1, -1, 1, -1] and st["length"].tolist() == [3, 2, 1, 3]
    assert out["age"].tolist() == [1, 2, 3, 1, 2, 1, 1, 2, 3, 1, 2]
    assert outputs_equal(out, pine(bars))
    assert same(pine(bars, push="new_colour")["pct_below"], [NAN] * 3 + [0.0, 0.0, 0.0, 0.0, 50.0, 50.0, 0.0, 0.0])
    assert same(pine(bars, push="age_plus_1")["pct_below"], [NAN] * 5 + [0.0] * 6)
    # the rare-age crossing on these bars (one finished streak suffices with min_streaks=1, rare_pct=50):
    # bar 8 (0 -> 100) and bar 10 (0 -> 50)
    assert np.flatnonzero(HA.heikin_ashi(*bars, rare_pct=50, min_streaks=1)["rare_now"]).tolist() == [8, 10]


def trap9_bars():
    """Bullish streaks of 1, 2, ..., 10 candles, each followed by one bearish candle, then a bullish streak of 12."""
    runs = []
    for k in range(1, 11):
        runs += [k, 1]
    return colour_bars(runs + [12])


def test_trap9_rare_now_is_computed_causally():
    """l.209-212 run only on the chart's last bar; PREREG 6.8 evaluates them at every bar. The k-th bullish streak
    (k = 2..10, last bar 3, 7, 12, 18, 25, 33, 42, 52, 63) reaches 100 % at its age k against the k - 1 earlier
    bullish streaks 1..k-1, having been below 90 % at age k - 1; the final streak (bars 65-76) against 1..10 is at
    100 * 9/10 = 90.0 exactly at age 10 (bar 74; >= holds) and 80 at age 9. The bearish streaks (all 1) are never
    rare. ``min_streaks`` counts the finished streaks of the colour: 10 leaves bar 74 only, 9 adds bar 63."""
    bars = trap9_bars()
    assert len(bars[0]) == 77
    lens = HA.heikin_ashi(*bars)["streaks"]
    assert lens["length"].tolist() == sum(([k, 1] for k in range(1, 11)), [])
    every = [3, 7, 12, 18, 25, 33, 42, 52, 63, 74]
    assert np.flatnonzero(HA.heikin_ashi(*bars, min_streaks=1)["rare_now"]).tolist() == every
    assert np.flatnonzero(HA.heikin_ashi(*bars, min_streaks=0)["rare_now"]).tolist() == every
    assert np.flatnonzero(HA.heikin_ashi(*bars, min_streaks=9)["rare_now"]).tolist() == [63, 74]
    out = HA.heikin_ashi(*bars, min_streaks=10)
    assert np.flatnonzero(out["rare_now"]).tolist() == [74]
    assert out["pct_below"][74] == 90.0 and out["pct_below"][73] == 80.0 and out["age"][74] == 10
    assert not HA.heikin_ashi(*bars, min_streaks=11)["rare_now"].any()
    assert not HA.heikin_ashi(*bars)["rare_now"].any()                 # the plan's 50: not reached here
    assert outputs_equal(out, pine(bars, min_streaks=10))
    # the script as written: only the last bar can say rare; at bar 76 (age 12) 100 % follows 100 %: never
    assert not pine(bars, min_streaks=10, rare="last_bar")["rare_now"].any()
    cut = tuple(x[:75] for x in bars)                                    # a chart that ends at bar 74
    assert np.flatnonzero(pine(cut, min_streaks=10, rare="last_bar")["rare_now"]).tolist() == [74]


# ───────────────────────────── 2. the map's other tests (4.6, "Tests") and the contract ─────────────────────────────

def test_event_sequences_of_the_map():
    """Map 4.6 test 5: STRONG, STRONG, INDECISION gives evInd; STRONG, STEADY, INDECISION does not; neither does an
    opposite-colour doji after STRONG, STRONG (in the bearish colour too)."""
    seqs = {
        "a": [("S", -1), ("S", -1), ("S", -1), ("I", -1)],   # bear S S S I: evInd at the doji
        "b": [("S", -1), ("S", -1), ("T", -1), ("I", -1)],   # bear S S T I: none
        "c": [("S", -1), ("S", -1), ("S", -1), ("I", 1)],    # bear S S S, then a bullish doji (a flip): none
        "d": [("S", 1), ("S", 1), ("I", -1)],                # bull S S S, then a bearish doji (a flip): none
        "e": [("S", 1), ("S", 1), ("I", 1)],                 # bull S S S I (bar 0 is STRONG too): evInd
        "f": [("T", -1), ("S", 1)],                          # a STRONG flip bar: evFirstSt at age 1 (map test 6)
    }
    out = {}
    for k, items in seqs.items():
        bars = build(items)
        out[k] = HA.heikin_ashi(*bars)
        assert outputs_equal(out[k], pine(bars)), k
    a, b, c, d, e, f = (out[k] for k in "abcdef")
    assert a["phase"].tolist() == [S, S, S, S, I_] and np.flatnonzero(a["ev_ind"]).tolist() == [4]
    assert b["phase"].tolist() == [S, S, S, T_, I_] and not b["ev_ind"].any()
    assert c["phase"].tolist() == [S, S, S, S, I_] and c["flip"][4] and not c["ev_ind"].any()
    assert d["phase"].tolist() == [S, S, S, I_] and d["flip"][3] and not d["ev_ind"].any()
    assert np.flatnonzero(e["ev_ind"]).tolist() == [3] and e["strong_run"].tolist() == [1, 2, 3, 0]
    assert f["phase"].tolist() == [S, T_, S] and f["flip"].tolist() == [False, True, True]
    assert f["age"].tolist() == [1, 1, 1] and f["ev_first_strong"].tolist() == [True, False, True]


def test_survive_and_strong_continuation_by_hand():
    """Map 4.6 test 8. ``survive`` on a hand-made list, and SK / SN (l.133-139) on hand-made streaks: after the flat
    bar 0 (bull, STRONG, 1 candle), bear S T (2), bull T T S S S S S S (8, first STRONG at age 3: 8 - 3 = 5 more),
    bear T S T T T T T (7, at age 2: 5 more), bull T T T (3, none), bear T (1, none), bull S T T T T (5, at 1: 4 more),
    then a bearish S (the current streak). Bull SN 3, SK 1; bear SN 2, SK 1 (aheadN 5)."""
    assert HA.survive([1, 8, 3, 5], 3, 5) == (3, 1)
    assert HA.survive([1, 8, 3, 5], 1, 5) == (4, 1)
    assert HA.survive([1, 8, 3, 5], 6, 5) == (1, 0)
    assert HA.survive([], 2, 5) == (0, 0)
    assert HA.pct_below_of([1, 8, 3, 5], 4) == 50.0 and HA.pct_below_of([2, 2, 2], 2) == 0.0
    assert HA.pct_below_of([1, 2, 3], 3) == 100.0 * 2 / 3 and math.isnan(HA.pct_below_of([], 3))
    items = ([("S", -1), ("T", -1)] + [("T", 1)] * 2 + [("S", 1)] * 6 + [("T", -1), ("S", -1)] + [("T", -1)] * 5
             + [("T", 1)] * 3 + [("T", -1)] + [("S", 1)] + [("T", 1)] * 4 + [("S", -1)])
    bars = build(items)
    out = HA.heikin_ashi(*bars)
    want_phase = [S, S, T_, T_, T_, S, S, S, S, S, S, T_, S, T_, T_, T_, T_, T_, T_, T_, T_, T_, S, T_, T_, T_, T_, S]
    assert out["phase"].tolist() == want_phase
    st = out["streaks"]
    assert st["start_bar"].tolist() == [0, 1, 3, 11, 18, 21, 22]
    assert st["end_bar"].tolist() == [0, 2, 10, 17, 20, 21, 26]
    assert st["dir"].tolist() == [1, -1, 1, -1, 1, -1, 1]
    assert st["length"].tolist() == [1, 2, 8, 7, 3, 1, 5]
    assert st["strong_at"].tolist() == [1, 1, 3, 2, 0, 0, 1]
    assert st["had_strong"].tolist() == [True, True, True, True, False, False, True]
    assert st["ran_5_after_strong"].tolist() == [False, False, True, True, False, False, False]
    bull, bear = st[st["dir"] == 1], st[st["dir"] == -1]
    assert (int(bull["had_strong"].sum()), int(bull["ran_5_after_strong"].sum())) == (3, 1)
    assert (int(bear["had_strong"].sum()), int(bear["ran_5_after_strong"].sum())) == (2, 1)
    # the panel at the last bar (bear, age 1, bear lengths [2, 7, 1]) and at bar 26 (bull age 5, bull [1, 8, 3])
    assert HA.panel_at(out, 27) == {"dir": -1, "n": 3, "age": 1, "pct_below": 0.0, "reached": 3, "went": 1,
                                    "sn": 2, "sk": 1}
    assert HA.panel_at(out, 26) == {"dir": 1, "n": 3, "age": 5, "pct_below": 100.0 * 2 / 3, "reached": 1,
                                    "went": 0, "sn": 2, "sk": 1}
    p = PineScript(panel=True)
    ref = p.run(*bars)
    assert outputs_equal(out, ref) and p.panels[27] == HA.panel_at(out, 27) and p.panels[26] == HA.panel_at(out, 26)
    assert HA.kept_lengths(st, 27, -1).tolist() == [2, 7, 1] and HA.kept_lengths(st, 26, 1).tolist() == [1, 8, 3]
    assert HA.kept_lengths(st, 21, -1).tolist() == [2, 7]            # bear 21 is pushed at bar 22, not before


def test_the_5000_streak_cap():
    """l.131-132: an array keeps its last 5,000 finished streaks. Bull streaks: 50 of 4 candles, then 4,951 of 1,
    each followed by a bearish candle, then a final bullish streak of 5. The 5,001st bullish push drops the first
    4-streak: at ages 2-4 the final streak is longer than 4,951 of the kept 5,000 (99.02 %); with every streak kept,
    4,951 of 5,001. The bearish array (5,001 streaks of 1) is capped too. A hand case of the same mechanism with a cap
    of 3: bull 5, 1, 1, 1, then the final bull at age 2 is longer than 3 of the kept [1, 1, 1] (100 %), not 3 of 4."""
    runs = []
    for _ in range(50):
        runs += [4, 1]
    for _ in range(4951):
        runs += [1, 1]
    bars = colour_bars(runs + [5])
    n = len(bars[0])
    assert n == 50 * 5 + 4951 * 2 + 5
    out = HA.heikin_ashi(*bars)
    tail = out["pct_below"][n - 5:]
    capped = 100.0 * 4951 / 5000
    assert tail.tolist() == [0.0, capped, capped, capped, 100.0]
    allh = HA._heikin_ashi(*bars, 0.05, 0.25, 5, 90, 50, keep=None)
    assert allh["pct_below"][n - 5:].tolist() == [0.0] + [100.0 * 4951 / 5001] * 3 + [100.0]
    assert len(out["streaks"]) == 10002 and len(HA.kept_lengths(out["streaks"], n - 1, 1)) == 5000
    assert HA.kept_lengths(out["streaks"], n - 1, 1)[:49].tolist() == [4] * 49
    assert outputs_equal(out, pine(bars, count="bisect"))
    assert outputs_equal(allh, pine(bars, count="bisect", keep=None))
    small = colour_bars([5, 1, 1, 1, 1, 1, 1, 1, 2])          # bull 5, 1, 1, 1 then bull 2
    k3 = HA._heikin_ashi(*small, 0.05, 0.25, 5, 90, 1, keep=3)
    assert k3["pct_below"][-1] == 100.0
    assert HA._heikin_ashi(*small, 0.05, 0.25, 5, 90, 1, keep=None)["pct_below"][-1] == 75.0
    assert outputs_equal(k3, pine(small, min_streaks=1, keep=3))


def test_output_keys_dtypes_and_inputs():
    o, h, l, c = random_bars(300, 7)
    keep = [x.copy() for x in (o, h, l, c)]
    out = HA.heikin_ashi(list(o), h, l, c)
    assert tuple(out) == HA.KEYS
    for k in ARRAY_KEYS:
        assert out[k].dtype == DTYPES[k] and out[k].shape == (300,), k
    st = out["streaks"]
    assert tuple(st.columns) == HA.STREAK_COLUMNS
    assert {k: st[k].dtype for k in st.columns} == {k: np.dtype(v) for k, v in STREAK_DTYPES.items()}
    assert all(np.array_equal(a, b) for a, b in zip(keep, (o, h, l, c)))     # inputs untouched
    assert HA.PHASE_NAMES[HA.STRONG] == "STRONG" and HA.PHASE_NAMES[HA.INDECISION] == "INDECISION"
    assert (HA.STRONG, HA.STEADY, HA.WEAK, HA.INDECISION) == (0, 1, 2, 3)      # l.92
    # empty and one-bar charts
    e = HA.heikin_ashi([], [], [], [])
    assert all(len(e[k]) == 0 for k in ARRAY_KEYS) and len(e["streaks"]) == 0
    assert tuple(e["streaks"].columns) == HA.STREAK_COLUMNS
    one = HA.heikin_ashi([1.0], [2.0], [0.5], [1.5])
    assert one["age"].tolist() == [1] and not one["flip"][0] and math.isnan(one["pct_below"][0])
    assert outputs_equal(one, pine(([1.0], [2.0], [0.5], [1.5])))
    # input checks
    with pytest.raises(ValueError):
        HA.heikin_ashi(o[:-1], h, l, c)
    bad = c.copy()
    bad[5] = np.nan
    with pytest.raises(ValueError):
        HA.heikin_ashi(o, h, l, bad)
    for kw in ({"strong_tol": 0.31}, {"strong_tol": -0.01}, {"doji_max": 0.04}, {"doji_max": 0.51},
               {"ahead_n": 0}, {"ahead_n": 51}, {"ahead_n": 2.5}, {"rare_pct": 49}, {"rare_pct": 100},
               {"rare_pct": 90.5}, {"min_streaks": -1}, {"ahead_n": True}):
        with pytest.raises(ValueError):
            HA.heikin_ashi(o, h, l, c, **kw)
    assert outputs_equal(HA.heikin_ashi(o, h, l, c, ahead_n=5.0, rare_pct=90.0), out)


# ───────────────────────────── 3. the port against the transcription ─────────────────────────────

@pytest.mark.parametrize("seed,decimals,flat", [(1, None, 0), (2, 0, 0), (3, 1, 0), (4, None, 700), (5, 0, 500)])
def test_port_equals_the_transcription_bit_for_bit_on_random_bars(seed, decimals, flat):
    bars = random_bars(4000, seed, decimals, flat)
    out = HA.heikin_ashi(*bars)
    ref = pine(bars)
    assert outputs_equal(out, ref)
    # what the random bars exercise (exact ties need the dyadic bars of the next test)
    assert set(np.unique(out["phase"]).tolist()) == {0, 1, 2, 3}
    assert out["ev_ind"].any() and out["ev_first_strong"].any() and out["rare_now"].any()
    assert (out["weak_run"] >= 2).any()


@pytest.mark.parametrize("seed", [61, 62, 63])
def test_port_equals_the_transcription_on_random_dyadic_shapes(seed):
    """Random sequences of exact HA shapes: ties (haC == haO), zero ranges, INDECISION after STRONG runs, WEAK runs."""
    bars = random_built(5000, seed)
    out = HA.heikin_ashi(*bars)
    assert outputs_equal(out, pine(bars))
    tie = out["ha_c"] == out["ha_o"]
    zero = (out["ha_h"] - out["ha_l"]) == 0.0
    assert tie.sum() > 100 and zero.sum() > 100 and (out["dir"][tie] == 1).all()
    assert (out["phase"][zero] == S).all() and (out["phase"][tie & ~zero] == I_).all()
    assert out["ev_ind"].sum() > 50 and (out["weak_run"] >= 2).sum() > 5 and out["rare_now"].sum() > 50
    for kw in (dict(strong_tol=0.15), dict(strong_tol=0.3, doji_max=0.5, ahead_n=2, rare_pct=60, min_streaks=3)):
        assert outputs_equal(HA.heikin_ashi(*bars, **kw), pine(bars, **kw)), kw


@pytest.mark.parametrize("kw", [dict(strong_tol=0.2, doji_max=0.4), dict(strong_tol=0.0, doji_max=0.05),
                                dict(ahead_n=1, rare_pct=50, min_streaks=0), dict(ahead_n=50, rare_pct=99),
                                dict(strong_tol=0.3, doji_max=0.5, ahead_n=3, rare_pct=75, min_streaks=5)])
def test_port_equals_the_transcription_with_other_inputs(kw):
    bars = random_bars(3000, 11, 1, 600)
    assert outputs_equal(HA.heikin_ashi(*bars, **kw), pine(bars, **kw))


@pytest.mark.parametrize("keep", [1, 2, 7, 40])
def test_port_equals_the_transcription_with_a_small_cap(keep):
    bars = random_bars(3000, 21, 0)
    out = HA._heikin_ashi(*bars, 0.05, 0.25, 5, 90, 3, keep=keep)
    assert outputs_equal(out, pine(bars, min_streaks=3, keep=keep))
    assert outputs_equal(out, pine(bars, min_streaks=3, keep=keep, count="bisect"))


def test_the_transcriptions_counting_methods_agree_and_the_panel_helper():
    bars = random_bars(1500, 31, 1, 400)
    p = PineScript(panel=True, min_streaks=5)
    ref = p.run(*bars)
    assert outputs_equal(ref, pine(bars, min_streaks=5, count="bisect"))
    out = HA.heikin_ashi(*bars, min_streaks=5)
    assert outputs_equal(out, ref)
    for t in list(range(0, 1500, 37)) + [1499]:
        got = HA.panel_at(out, t)
        want = p.panels[t]
        assert {k: v for k, v in got.items() if k != "pct_below"} == {k: v for k, v in want.items() if k != "pct_below"}
        assert same([got["pct_below"]], [want["pct_below"]]) and same([got["pct_below"]], [out["pct_below"][t]])


@pytest.mark.parametrize("seed", [41, 42])
def test_rare_now_at_most_once_per_streak_and_only_after_min_streaks(seed):
    """Map 4.6 test 7, as a property: per streak at most one rare-age bar; none before the colour has min_streaks
    finished streaks; and at the rare bar the percentage has just reached rare_pct."""
    bars = random_bars(6000, seed, 1)
    for ms in (0, 20, 50):
        out = HA.heikin_ashi(*bars, min_streaks=ms)
        sid = np.cumsum(out["flip"])
        rare = np.flatnonzero(out["rare_now"])
        assert len(rare) > 0 and len(np.unique(sid[rare])) == len(rare)
        st = out["streaks"]
        for t in rare:
            d = int(out["dir"][t])
            assert int(((st["dir"] == d) & (st["end_bar"] < t)).sum()) >= ms
            assert out["pct_below"][t] >= 90 and out["age"][t] > 1
            assert HA.pct_below_of(HA.kept_lengths(st, t, d), out["age"][t] - 1) < 90


# ───────────────────────────── 4. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed", [51, 52, 53])
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(seed):
    bars = random_bars(3000, seed, decimals=0 if seed == 53 else None, flat_every=900 if seed == 52 else 0)
    full = HA.heikin_ashi(*bars, min_streaks=10)
    flips = np.flatnonzero(full["flip"])
    rare = np.flatnonzero(full["rare_now"])
    cuts = [0, 1, 2, 50, 777, 2999, int(flips[3]), int(flips[3]) - 1, int(flips[-1]), int(rare[0]), int(rare[-1])]
    for t in cuts:
        part = HA.heikin_ashi(*[x[:t + 1] for x in bars], min_streaks=10)
        assert outputs_equal(part, full, t + 1), t
        assert frames_equal(part["streaks"], streaks_upto(full["streaks"], t + 1)), t


# ───────────────────────────── 5. real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H / 1D bars of a symbol from its data start to 2024-06-30 (``load(symbol, end="2024-07-01")``
    with the guard pointed at an empty folder), one symbol in memory at a time."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            cache.clear()
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end="2024-07-01")
                tb = {tf: mk.tbars(tf) for tf in TM.TFS}
            del mk
            cache[symbol] = tb
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_smoke(symbol, real):
    tbars = real(symbol)
    a19 = TM.s_of("2019-01-01")
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        n = len(b)
        assert n > 1500 and int(b.tc[-1]) <= TM.CUT_S, tf                     # nothing from the hold-out
        out = HA.heikin_ashi(b.o, b.h, b.l, b.c)
        assert tuple(out) == HA.KEYS
        for k in ARRAY_KEYS:
            assert out[k].shape == (n,) and out[k].dtype == DTYPES[k], (tf, k)
        # values everywhere the contract says they exist
        for k in ("ha_o", "ha_h", "ha_l", "ha_c"):
            assert np.isfinite(out[k]).all(), (tf, k)
        st = out["streaks"]
        first_done = {d: int(st.loc[st["dir"] == d, "end_bar"].iloc[0]) + 1 for d in (1, -1)}
        want_nan = np.arange(n) < np.where(out["dir"] == 1, first_done[1], first_done[-1])
        assert np.array_equal(np.isnan(out["pct_below"]), want_nan), tf
        assert max(first_done.values()) < int(np.searchsorted(b.tc, a19)), tf   # the statistics exist before 2019
        pb = out["pct_below"][~want_nan]
        assert ((pb >= 0) & (pb <= 100)).all()
        # the HA candle and the codes
        assert (out["ha_h"] >= np.maximum(out["ha_o"], out["ha_c"])).all() and (out["ha_h"] >= b.h).all()
        assert (out["ha_l"] <= np.minimum(out["ha_o"], out["ha_c"])).all() and (out["ha_l"] <= b.l).all()
        assert set(np.unique(out["dir"]).tolist()) == {-1, 1}
        assert set(np.unique(out["phase"]).tolist()) == {0, 1, 2, 3}
        # the streak bookkeeping
        d = out["dir"]
        assert not out["flip"][0] and np.array_equal(out["flip"][1:], d[1:] != d[:-1]), tf
        age = out["age"]
        assert age[0] == 1 and np.array_equal(age[1:], np.where(out["flip"][1:], 1, age[:-1] + 1)), tf
        assert not (out["ev_ind"] & out["flip"]).any() and (out["phase"][out["ev_ind"]] == I_).all()
        assert (out["phase"][out["ev_first_strong"]] == S).all()
        assert not (out["flip"] & (out["phase"] == W_)).any() and not out["weak_run"][out["flip"]].any()
        sid = np.cumsum(out["flip"])
        fs = np.flatnonzero(out["ev_first_strong"])
        assert len(np.unique(sid[fs])) == len(fs)                               # once per streak
        rare = np.flatnonzero(out["rare_now"])
        assert len(rare) > 0 and len(np.unique(sid[rare])) == len(rare)
        assert len(st) == int(out["flip"].sum()) and (st["length"] >= 1).all()
        assert st["start_bar"].iloc[0] == 0 and np.array_equal(st["start_bar"].to_numpy()[1:],
                                                               st["end_bar"].to_numpy()[:-1] + 1)
        assert np.array_equal(st["end_bar"].to_numpy() + 1, np.flatnonzero(out["flip"]))
        assert (st["dir"].to_numpy()[1:] != st["dir"].to_numpy()[:-1]).all()
        assert np.array_equal(st["length"].to_numpy(), age[np.flatnonzero(out["flip"]) - 1])


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_equal_the_transcription_bit_for_bit(symbol, real):
    tbars = real(symbol)
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        port = HA.heikin_ashi(b.o, b.h, b.l, b.c)
        ref = pine((b.o, b.h, b.l, b.c), count="bisect")
        assert outputs_equal(port, ref), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_truncation_invariance(symbol, real):
    tbars = real(symbol)
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        full = HA.heikin_ashi(b.o, b.h, b.l, b.c)
        for when in ("2020-03-16 12:00", "2022-11-09 00:00"):
            j = int(np.searchsorted(b.tc, TM.s_of(when), side="right")) - 1
            part = HA.heikin_ashi(b.o[:j + 1], b.h[:j + 1], b.l[:j + 1], b.c[:j + 1])
            assert outputs_equal(part, full, j + 1), (tf, when)
