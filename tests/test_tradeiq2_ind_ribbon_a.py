"""
Port A of the Trend Target Ribbon (``backtesting/research/tradeiq2_ind_ribbon.py``).

1. One hand-computed test per trap of the map's porting risks (``ribbon_patterns.md`` A6, "Risks": nine lines, the
   ALMA line taken as two traps, orientation and floor), named after it. Each also runs the wrong reading on the same
   bars (``PineScript``, a plain-Python bar-by-bar transcription of the script's computing lines with one switch per
   misreading) and checks that it answers differently. The four traps that belong to the harness (the entry at the
   close, the stop from the fill, entry-bar target touches, the old position on a flip bar) are checked on what the
   port gives the harness (the flip bar and the stop distance) and on the script's own position bookkeeping, which the
   transcription keeps (L180-187, L215-330, L419-422, L495-631). ``trap01c`` (and the third input set of section 3)
   was added at the reconciliation with port B: the literal call's na before bar_index stop_lookback - 1, the one
   mismatch between the ports, which this port had missed.
2. The rest of the map's test list (A6, "Test cases"): ALMA on a ramp, a constant and an impulse; the deviation
   against numpy; the strict thresholds; flat -> up-ramp -> flat -> down-ramp; one condition alone never sets up; the
   clamp branches; the literal and intended stops on a hand-made flip sequence (trap 1); the warm-up bars.
3. The vectorised port against the transcription on random bars, bit for bit (also with other inputs).
4. Truncation invariance: the outputs up to bar T do not change when the bars after T are removed.
5. Real bars (skipped when the tick store is absent): both symbols, 1H / 4H / 1D (PREREG 6.1), from the data start to
   2024-06-30 with the hold-out guard closed: the NaN pattern of the contract, ranges, the transcription bit for bit,
   truncation, and the ATR against ``external.wilder_atr``.

Every test runs with the guard pointed at an empty folder (FINALISTS.md absent: nothing at or after 2024-07-01).
Line numbers L... are those of the owner's copy of the script.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_ribbon as RIB
from backtesting.research import tradeiq_market as TM

NAN = math.nan
SYMS = ("XAUUSDm", "BTCUSDm")
FLOAT_KEYS = ("alma", "dev", "atr", "slope", "conviction", "edge_up", "edge_dn", "risk_long", "risk_short",
              "risk_long_lit", "risk_short_lit")


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


def outputs_equal(x, y, upto=None) -> bool:
    """Every key of the contract equal (floats bit for bit, NaN to NaN; bool / int8 exactly), on bars [0, upto)."""
    for k in RIB.KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if upto is not None:
            a, b = a[:upto], b[:upto]
        if k in FLOAT_KEYS:
            if not same(a, b):
                return False
        elif not (a.dtype == b.dtype and np.array_equal(a, b)):
            return False
    return True


# ───────────────────────────── the transcription (the script, bar by bar) ─────────────────────────────

def _pmax(a, b):
    """``math.max``: na if either is na."""
    return NAN if (a != a or b != b) else (a if a > b else b)


def _pmin(a, b):
    return NAN if (a != a or b != b) else (a if a < b else b)


def _nz(x, y):
    return y if x != x else x


class LocalCall:
    """
    A ``ta.lowest(src, n)`` / ``ta.highest(src, n)`` call site inside ``if flip`` (L281, L315-317): it runs only when
    called. ``mode="calls"`` (the contract): it stores only the values it was called with and returns the extreme of
    the last n of them, from bar_index n - 1 on even with fewer values. ``mode="full"`` (an alternative): na until it
    holds n values. ``mode="global"`` (an alternative): it reads the chart's last n bars of the series at each call.
    ``prev()`` is ``[1]`` on the call's result: its result at the previous execution.
    """

    def __init__(self, n, fn, mode="calls", series=None):
        self.n, self.fn, self.mode, self.series = n, fn, mode, series
        self.values, self.results = [], []

    def call(self, value, bar_index):
        if self.mode == "global":
            r = self.fn(self.series[bar_index - self.n + 1:bar_index + 1]) if bar_index >= self.n - 1 else NAN
        else:
            self.values.append(value)
            last = self.values[-self.n:]
            short = bar_index < self.n - 1 or (self.mode == "full" and len(last) < self.n)
            r = NAN if short else self.fn(last)
        self.results.append(r)
        return r

    def prev(self):
        return self.results[-2] if len(self.results) >= 2 else NAN


class PineScript:
    """
    The script's computing lines, transcribed bar by bar in plain Python floats from the source (L88-114, L120-128,
    L180-187, L215-330, L419-422, L495-631); ``run`` returns the contract's arrays plus the script's own positions.
    Switches (default = the script as written, the contract's readings):

    * ``alma_reversed``: weight i on ``close[i]`` instead of ``close[length - 1 - i]``; ``alma_floor``: m floored;
    * ``stdev_sample``: divide by length - 1; ``atr_seed``: "sma" (pine_rma) or "first" (the first true range);
      ``tr0``: "hl" (the first true range is high - low) or "na";
    * ``strict``: False makes the setups ``>=`` / ``<=``;
    * ``stop``: the position's structure stop: "intended", "literal" (the contract's), "literal_full" or
      "literal_global" (``LocalCall`` modes);
    * ``reset_after_stop``: the trend goes back to 0 when the position is stopped out;
    * ``old_stop_on_flip_bar``: the old position's stop is checked on a flip bar before it is frozen (the order the
      harness's M1 stop check has).

    Each position: dir, entry_bar, entry, risk, stop, end_bar, end_why ("stop" / "flip" / None), ``hit_bar`` (the bar
    each target T1..T4 got its check mark, the script's L626-631, the entry bar included) and ``hit_after`` (the same
    counted from the bar after the entry only).
    """

    OPTS = dict(alma_reversed=False, alma_floor=False, stdev_sample=False, atr_seed="sma", tr0="hl", strict=True,
                stop="intended", reset_after_stop=False, old_stop_on_flip_bar=False)

    def __init__(self, **kw):
        self.o = dict(self.OPTS)
        self.p = dict(RIB.DEFAULTS)
        for k, v in kw.items():
            if k in self.o:
                self.o[k] = v
            elif k in self.p:
                self.p[k] = v
            else:
                raise TypeError(k)

    def run(self, o, h, l, c):
        o, h, l, c = ([float(v) for v in np.asarray(x, np.float64)] for x in (o, h, l, c))
        P, S = self.p, self.o
        na_, nd, sl, nr, lb = (int(P[k]) for k in ("alma_len", "dev_len", "slope_len", "atr_len", "stop_lookback"))
        m = P["alma_offset"] * (na_ - 1)
        if S["alma_floor"]:
            m = float(math.floor(m))
        s = na_ / P["alma_sigma"]
        W = [math.exp(-1 * math.pow(i - m, 2) / (2 * math.pow(s, 2))) for i in range(na_)]
        alpha = 1.0 / nr
        N = len(c)
        out = {k: np.full(N, NAN) for k in FLOAT_KEYS}
        bull_a, bear_a = np.zeros(N, bool), np.zeros(N, bool)
        trend_a, flip_a = np.zeros(N, np.int8), np.zeros(N, np.int8)
        calls = {mode: (LocalCall(lb, min, mode, l), LocalCall(lb, max, mode, h))
                 for mode in ("calls", "full", "global")}
        almas, trs = [], []
        atr_prev = NAN
        trend = 0
        pos = None                     # the open (or last) position of the script
        positions = []
        for t in range(N):
            # L88: ta.alma
            if t >= na_ - 1:
                norm = acc = 0.0
                for i in range(na_):
                    norm = norm + W[i]
                    x = c[t - i] if S["alma_reversed"] else c[t - (na_ - 1 - i)]
                    acc = acc + x * W[i]
                a = acc / norm
            else:
                a = NAN
            almas.append(a)
            # L89: ta.stdev (pine_stdev: the mean as pine_sma, deviations of at most 1e-10 are 0)
            if t >= nd - 1:
                avg = 0.0
                for i in range(nd):
                    avg = avg + c[t - i] / nd
                ss = 0.0
                for i in range(nd):
                    d = c[t - i] + -avg
                    if abs(d) <= 1e-10:
                        d = 0.0
                    ss = ss + d * d
                dev = math.sqrt(ss / (nd - 1 if S["stdev_sample"] else nd))
            else:
                dev = NAN
            # L90: ta.atr = ta.rma(true range); pine_rma: na(sum[1]) ? ta.sma(tr, n) : alpha*tr + (1-alpha)*sum[1]
            if t == 0:
                tr = h[0] - l[0] if S["tr0"] == "hl" else NAN
            else:
                tr = max(max(h[t] - l[t], abs(h[t] - c[t - 1])), abs(l[t] - c[t - 1]))
            trs.append(tr)
            if S["atr_seed"] == "first":
                atr = tr if atr_prev != atr_prev else alpha * tr + (1 - alpha) * atr_prev
            elif atr_prev != atr_prev:
                last = trs[-nr:]
                if len(last) == nr and all(v == v for v in last):
                    acc = 0.0
                    for i in range(nr):
                        acc = acc + trs[-1 - i] / nr
                    atr = acc
                else:
                    atr = NAN
            else:
                atr = alpha * tr + (1 - alpha) * atr_prev
            atr_prev = atr
            # L92: slope; L94-98: setups
            a_back = almas[t - sl] if t >= sl else NAN
            slope = (a - a_back) / atr if atr > 0 else 0.0
            upper = a + dev * P["dev_mult"]
            lower = a - dev * P["dev_mult"]
            if S["strict"]:
                bull = slope > P["slope_min"] and c[t] > upper
                bear = slope < -P["slope_min"] and c[t] < lower
            else:
                bull = slope >= P["slope_min"] and c[t] >= upper
                bear = slope <= -P["slope_min"] and c[t] <= lower
            # L100-114: trend and flips
            bull_flip = bear_flip = False
            if trend != 1 and bull:
                trend = 1
                bull_flip = True
            elif trend != -1 and bear:
                trend = -1
                bear_flip = True
            flip = bull_flip or bear_flip
            # L120-128
            distance = abs(c[t] - a) / atr if atr > 0 else 0.0
            conviction = _pmax(0.0, _pmin(1.0, abs(slope) * 2.0 + distance * 0.35))
            lo_r, hi_r = atr * P["min_stop_atr"], atr * P["max_stop_atr"]
            # the intended stop at every bar: ta.lowest(low, 12)[1] / ta.highest(high, 12)[1] as global series
            ssl = min(l[t - lb:t]) if t >= lb else NAN
            ssh = max(h[t - lb:t]) if t >= lb else NAN
            r_long = _pmin(_pmax(_nz(c[t] - ssl, lo_r), lo_r), hi_r)
            r_short = _pmin(_pmax(_nz(ssh - c[t], lo_r), lo_r), hi_r)
            # the literal stop: only the call of the ternary's taken branch runs, and only on a flip bar
            lit = {}
            if flip:
                side = 0 if bull_flip else 1
                for mode, pair in calls.items():
                    pair[side].call(l[t] if bull_flip else h[t], t)
                    lit[mode] = pair[side].prev()
            for k, v in (("alma", a), ("dev", dev), ("atr", atr), ("slope", slope), ("conviction", conviction),
                         ("edge_up", a + dev * P["edge_mult"]), ("edge_dn", a - dev * P["edge_mult"]),
                         ("risk_long", r_long), ("risk_short", r_short)):
                out[k][t] = v
            if bull_flip:
                out["risk_long_lit"][t] = _pmin(_pmax(_nz(c[t] - lit["calls"], lo_r), lo_r), hi_r)
            if bear_flip:
                out["risk_short_lit"][t] = _pmin(_pmax(_nz(lit["calls"] - c[t], lo_r), lo_r), hi_r)
            bull_a[t], bear_a[t], trend_a[t] = bull, bear, trend
            flip_a[t] = 1 if bull_flip else (-1 if bear_flip else 0)

            # the script's position: freeze (L215-277), new position (L281-330, 419-422), active (L495-631)
            active = pos is not None and pos["end_why"] is None
            if S["old_stop_on_flip_bar"] and flip and active and t > pos["entry_bar"]:
                if (l[t] <= pos["stop"]) if pos["dir"] == 1 else (h[t] >= pos["stop"]):
                    pos["end_bar"], pos["end_why"] = t, "stop"
                    active = False
            if flip and active:
                pos["end_bar"], pos["end_why"] = t, "flip"
            if flip:
                d = 1 if trend == 1 else -1
                entry = c[t]
                if S["stop"] == "intended":
                    struct = ssl if d == 1 else ssh
                else:
                    struct = lit[{"literal": "calls", "literal_full": "full", "literal_global": "global"}[S["stop"]]]
                raw = entry - struct if d == 1 else struct - entry
                risk = _pmin(_pmax(_nz(raw, lo_r), lo_r), hi_r)
                pos = dict(dir=d, entry_bar=t, entry=entry, risk=risk, stop=entry - d * risk, end_bar=None,
                           end_why=None, hit_bar=[None] * 4, hit_after=[None] * 4)
                positions.append(pos)
            if pos is not None and pos["end_why"] is None:
                d = pos["dir"]
                if t > pos["entry_bar"] and ((l[t] <= pos["stop"]) if d == 1 else (h[t] >= pos["stop"])):
                    pos["end_bar"], pos["end_why"] = t, "stop"
                    if S["reset_after_stop"]:
                        trend = 0
                else:
                    for i in range(4):
                        target = pos["entry"] + d * pos["risk"] * (i + 1)
                        if (h[t] >= target) if d == 1 else (l[t] <= target):
                            if pos["hit_bar"][i] is None:
                                pos["hit_bar"][i] = t
                            if t > pos["entry_bar"] and pos["hit_after"][i] is None:
                                pos["hit_after"][i] = t
        out.update(bull_setup=bull_a, bear_setup=bear_a, trend=trend_a, flip=flip_a)
        out["positions"] = positions
        return out


# ───────────────────────────── bars for the hand cases ─────────────────────────────

def path(knots, n, half=0.5):
    """[o, h, l, c] along the piecewise-linear close path through ``knots`` (bar, value): high / low = close +- half,
    open = the previous close (the first bar: its own close)."""
    xs, ys = zip(*knots)
    c = np.interp(np.arange(n), xs, ys)
    o = np.concatenate(([c[0]], c[:-1]))
    return [o, c + half, c - half, c]


def flat_up_flat_down():
    """Path A: 100 flat to bar 80, +0.4 a bar to 124 at bar 140, flat to 220, -0.4 a bar to 100 at 280, flat to 360.
    True range 1 on every bar (|change| <= 0.5), so the ATR is 1 (to 3e-16) from bar 13."""
    return path([(0, 100), (80, 100), (140, 124), (220, 124), (280, 100), (360, 100)], 361)


def rising_zigzag():
    """Path E: flat to bar 80, then 36 legs of 36 bars, alternately up to 118 + j/4 and down to 100 + j/4 (leg j), so
    the troughs and the peaks rise; high / low = close +- 1.5, so the true range and the ATR are 3."""
    knots, t = [(0, 100.0), (80, 100.0)], 80
    for j in range(1, 37):
        t += 36
        knots.append((t, (118.0 if j % 2 else 100.0) + 0.25 * j))
    return path(knots, t + 1, half=1.5), [k for k, _ in knots]


def random_bars(n, seed, decimals=None, start=2000.0, vol=1.0):
    rng = np.random.default_rng(seed)
    c = start + np.cumsum(vol * rng.standard_normal(n))
    h = c + np.abs(vol * rng.standard_normal(n))
    lo = c - np.abs(vol * rng.standard_normal(n))
    o = np.concatenate(([c[0]], c[:-1])) + 0.1 * vol * rng.standard_normal(n)
    if decimals is not None:
        o, h, lo, c = (np.round(x, decimals) for x in (o, h, lo, c))
        h, lo = np.maximum(h, np.maximum(o, c)), np.minimum(lo, np.minimum(o, c))
    return [o, h, lo, c]


def weights(m, length=34, sigma=6.0):
    """ALMA weights by hand: w_i = exp(-(i - m)^2 / (2 s^2)), s = length / sigma."""
    s = length / sigma
    return np.array([math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)])


# ───────────────────────────── 1. the traps (ribbon_patterns.md A6, "Risks") ─────────────────────────────

def test_trap01_stop_scope_intended_vs_literal():
    """L315-317 sit in ``if flip`` and in a ternary. Intended: the lowest low of the 12 bars before the flip bar.
    Literal: the lowest of the lows of the previous up to 12 BULL-FLIP bars ([1] = the call's previous result; the
    first flip's is na -> 0.75 ATR). Shorts mirror it with the highs of the bear-flip bars."""
    (o, h, l, c), knots = rising_zigzag()
    out = RIB.ribbon(o, h, l, c)
    f = out["flip"]
    idx = np.flatnonzero(f)
    # one flip per leg, alternating, the bull flips on the up legs
    assert len(idx) == 36 and np.array_equal(np.searchsorted(knots, idx) - 1, np.arange(1, 37))
    assert np.array_equal(f[idx], np.tile([1, -1], 18))
    bf, sf = np.flatnonzero(f == 1), np.flatnonzero(f == -1)
    atr = out["atr"]
    assert np.allclose(atr[80:], 3.0, rtol=0, atol=1e-12)              # true range 3 on every bar
    lows, highs = l[bf], h[sf]
    for j, t in enumerate(bf):
        lo, hi = atr[t] * 0.75, atr[t] * 3.0
        intended = min(max(c[t] - l[t - 12:t].min(), lo), hi)
        literal = lo if j == 0 else min(max(c[t] - lows[max(0, j - 12):j].min(), lo), hi)
        assert out["risk_long"][t] == intended and out["risk_long_lit"][t] == literal, j
    for j, t in enumerate(sf):
        lo, hi = atr[t] * 0.75, atr[t] * 3.0
        intended = min(max(h[t - 12:t].max() - c[t], lo), hi)
        literal = lo if j == 0 else min(max(highs[max(0, j - 12):j].max() - c[t], lo), hi)
        assert out["risk_short"][t] == intended and out["risk_short_lit"][t] == literal, j
    # the literal stop exists on the flip bars of its side only
    assert np.isnan(np.delete(out["risk_long_lit"], bf)).all() and np.isnan(np.delete(out["risk_short_lit"], sf)).all()
    # numbers: the first bull flip's literal stop is na -> 0.75 ATR; the troughs rise 0.25 a leg, so the literal raw
    # risk grows with the buffer, hits the 3-ATR cap, and falls back to 7.5 (2.5 ATR) once only 12 flips are kept
    r = out["risk_long_lit"][bf] / atr[bf]
    assert abs(r[0] - 0.75) < 1e-15 and np.all(np.diff(r[:10]) > 0) and np.allclose(r[10:13], 3.0)
    assert np.allclose(r[13:], 2.5)
    # the readings differ on every bull flip; the 12-flip buffer matters from the 14th; shorts: the earlier bear
    # flips' highs are BELOW the close (rising peaks), raw < 0 -> 0.75 ATR, while the intended stop is ~2 ATR
    assert np.all(out["risk_long"][bf] != out["risk_long_lit"][bf])
    every = np.array([atr[t] * 0.75 if j == 0 else min(max(c[t] - lows[:j].min(), atr[t] * 0.75), atr[t] * 3.0)
                      for j, t in enumerate(bf)])
    assert np.all(every[13:] != out["risk_long_lit"][bf][13:]) and same(every[:13], out["risk_long_lit"][bf][:13])
    assert np.allclose(out["risk_short_lit"][sf] / atr[sf], 0.75) and np.all(out["risk_short"][sf] / atr[sf] > 1.9)
    # the script's own positions take these distances: intended by default, literal with the literal stop
    for mode, key_l, key_s in (("intended", "risk_long", "risk_short"), ("literal", "risk_long_lit", "risk_short_lit")):
        pos = PineScript(stop=mode).run(o, h, l, c)["positions"]
        assert len(pos) == 36
        for p in pos:
            want = out[key_l if p["dir"] == 1 else key_s][p["entry_bar"]]
            assert p["risk"] == want and p["stop"] == p["entry"] - p["dir"] * want
    # the wrong readings answer differently: na until 12 values (0.75 ATR on bull flips 2-12), the global lows
    alt = {}
    for mode in ("literal_full", "literal_global"):
        pos = PineScript(stop=mode).run(o, h, l, c)["positions"]
        alt[mode] = np.array([p["risk"] for p in pos if p["dir"] == 1])
    assert np.allclose(alt["literal_full"][:12] / atr[bf][:12], 0.75) and same(alt["literal_full"][12:],
                                                                                 out["risk_long_lit"][bf][12:])
    assert np.sum(alt["literal_full"] != out["risk_long_lit"][bf]) == 11
    assert np.sum(alt["literal_global"] != out["risk_long_lit"][bf]) >= 15


def test_trap01b_literal_buffer_by_hand():
    """The call-site buffer on its own: ``ta.lowest(v, 3)[1]`` at the executions of a call fed 5, 3, 8, 1, 9, 7, 6 is
    na, 5, 3, 3, 1, 1, 1 (the previous execution's extreme of the last 3 values); ``ta.highest`` gives na, 5, 5, 8, 8,
    9, 9."""
    v = np.array([5.0, 3.0, 8.0, 1.0, 9.0, 7.0, 6.0])
    assert same(RIB._previous_calls(v, 3, True), [NAN, 5, 3, 3, 1, 1, 1])
    assert same(RIB._previous_calls(v, 3, False), [NAN, 5, 5, 8, 8, 9, 9])
    assert same(RIB._previous_calls(v[:1], 3, True), [NAN]) and len(RIB._previous_calls(v[:0], 3, True)) == 0
    for mode_low in (True, False):
        call = LocalCall(3, min if mode_low else max)
        got = []
        for x in v:
            call.call(x, 100)
            got.append(call.prev())
        assert same(got, RIB._previous_calls(v, 3, mode_low))
    # executions at bar_index 0 and 1 (below length - 1 = 2) have an na result, so the [1] of the next execution is na
    # too (added at the reconciliation with port B): na, na, na, then min(5, 3, 8) = 3, 1, 1, 1 / 8, 8, 9, 9
    at = [0, 1, 5, 6, 7, 8, 9]
    assert same(RIB._previous_calls(v, 3, True, at), [NAN, NAN, NAN, 3, 1, 1, 1])
    assert same(RIB._previous_calls(v, 3, False, at), [NAN, NAN, NAN, 8, 8, 9, 9])
    for mode_low in (True, False):
        call = LocalCall(3, min if mode_low else max)
        got = []
        for x, b in zip(v, at):
            call.call(x, b)
            got.append(call.prev())
        assert same(got, RIB._previous_calls(v, 3, mode_low, at))


def test_trap01c_literal_call_before_bar_index_lookback_minus_1():
    """Found at the reconciliation with port B (the port used to give a value here). The literal call's window rule
    (PineTS's account of TradingView, the contract's reading): na while the chart's bar_index < stop_lookback - 1,
    so a flip before bar 49 with ``stop_lookback=50`` leaves na in the call's result and the NEXT flip of that side
    gets ``nz`` -> 0.75 ATR. Only other inputs can flip that early (the defaults flip from bar 36, the rule needs
    bar 11). Zigzag: flat 100 to bar 9, legs of 15 bars, +-1 a bar, high / low = the body +- 0.25; ALMA, deviation and
    ATR of 5 bars, slope over 1 bar. Bull flips at 10, 41, 71, 101 (lows 99.75, 100.75, 100.75, 100.75), bear flips
    at 26, 56, 86, 116 (highs 114.25). Long at 71: [1] = the result at bar 41 (< 49) = na -> 0.75 ATR (the old port:
    102 - 99.75 = 2.25); at 101: [1] = the result at bar 71 = min(99.75, 100.75, 100.75) -> 102 - 99.75 = 2.25. Short
    at 56: [1] = the result at 26 = na -> 0.75 ATR (the old port: 114.25 - 113 = 1.25); at 86 and 116: 1.25."""
    c = [100.0] * 10
    level = 100.0
    for j in range(8):
        step = 1.0 if j % 2 == 0 else -1.0
        c += [level + step * k for k in range(1, 16)]
        level += 15 * step
    c = np.array(c)
    o = np.concatenate(([c[0]], c[:-1]))
    h, lo = np.maximum(o, c) + 0.25, np.minimum(o, c) - 0.25
    kw = dict(alma_len=5, dev_len=5, slope_len=1, atr_len=5, stop_lookback=50)
    out = RIB.ribbon(o, h, lo, c, **kw)
    f = out["flip"]
    assert np.flatnonzero(f == 1).tolist() == [10, 41, 71, 101] and np.flatnonzero(f == -1).tolist() == [26, 56, 86, 116]
    atr = out["atr"]
    want_long = {10: 0.75 * atr[10], 41: 0.75 * atr[41], 71: 0.75 * atr[71], 101: 2.25}
    want_short = {26: 0.75 * atr[26], 56: 0.75 * atr[56], 86: 1.25, 116: 1.25}
    for t, w in want_long.items():
        assert out["risk_long_lit"][t] == w and 0.75 * atr[t] <= w <= 3 * atr[t], t
    for t, w in want_short.items():
        assert out["risk_short_lit"][t] == w and 0.75 * atr[t] <= w <= 3 * atr[t], t
    assert abs(c[71] - lo[[10, 41]].min() - 2.25) < 1e-12 and abs(h[26] - c[56] - 1.25) < 1e-12   # the old values
    assert outputs_equal(out, PineScript(**kw).run(o, h, lo, c))
    # the script's defaults on the same bars flip from bar 36 on, so the rule never applies there
    assert int(np.flatnonzero(RIB.ribbon(o, h, lo, c)["flip"])[0]) >= 36


def test_trap02_alma_weight_orientation():
    """Weight i applies to close[33 - i] (i = 33 is the current bar). On x_t = t the ALMA is t - 6.6607021454; the
    reversed weights give t - 26.34. On a unit impulse the current bar carries w_33 / sum(w), 0.683 of the peak weight,
    and the peak is 5 bars back."""
    w = weights(0.85 * 33)
    lag = float(np.sum(w * (33 - np.arange(34))) / w.sum())
    assert abs(lag - 6.6607021454) < 1e-9
    x = np.arange(200.0)
    a = RIB.alma(x)
    assert np.isnan(a[:33]).all() and np.allclose(a[33:], x[33:] - 6.6607021454, rtol=0, atol=1e-9)
    imp = np.zeros(120)
    imp[50] = 1.0
    ai = RIB.alma(imp)
    assert np.allclose(ai[50:84], w[::-1] / w.sum(), rtol=0, atol=1e-15)   # j bars after the impulse: w_(33-j)
    assert np.all(ai[33:50] == 0.0) and np.all(ai[84:] == 0.0)
    assert int(np.nanargmax(ai)) == 55 and abs(w[33] / w.max() - 0.6828446557529847) < 1e-12
    # the reversed reading: lag 26.34 on the ramp, the flip of path A moves
    rev = PineScript(alma_reversed=True).run(*path([(0, 0.0), (199, 199.0)], 200))
    assert np.allclose(rev["alma"][33:], x[33:] - 26.33929785461735, rtol=0, atol=1e-9)
    bars = flat_up_flat_down()
    good, bad = RIB.ribbon(*bars)["flip"], PineScript(alma_reversed=True).run(*bars)["flip"]
    assert np.flatnonzero(good).tolist() == [83, 223] and np.flatnonzero(bad).tolist() != [83, 223]


def test_trap03_alma_offset_is_not_floored():
    """m = 0.85 * 33 = 28.05, not floor(28.05) = 28 (``ta.alma``'s floor defaults to false and the script passes four
    arguments, L88): the impulse response is the m = 28.05 weights; on a ramp the lag is 6.6607, floored 6.6917."""
    assert 0.85 * 33 == 28.05 and math.floor(0.85 * 33) == 28
    w, wf = weights(28.05), weights(28.0)
    imp = np.zeros(120)
    imp[50] = 1.0
    got = RIB.ribbon(np.zeros(120), imp, imp, imp)["alma"]
    assert np.allclose(got[50:84], w[::-1] / w.sum(), rtol=0, atol=1e-15)
    assert np.max(np.abs(got[50:84] - wf[::-1] / wf.sum())) > 1e-4
    assert np.allclose(RIB.alma(imp, floor=True)[50:84], wf[::-1] / wf.sum(), rtol=0, atol=1e-15)
    x = np.arange(200.0)
    lag_f = float(np.sum(wf * (33 - np.arange(34))) / wf.sum())
    assert abs(lag_f - 6.6916552212920495) < 1e-12
    assert np.allclose(RIB.alma(x, floor=True)[33:], x[33:] - lag_f, rtol=0, atol=1e-9)
    # the floored reading answers differently on the same bars: some flip of a random walk moves
    bars = random_bars(3000, 7)
    good = RIB.ribbon(*bars)
    bad = PineScript(alma_floor=True).run(*bars)
    assert not np.array_equal(good["flip"], bad["flip"])
    assert same(PineScript().run(*bars)["alma"], good["alma"])


def test_trap04_population_stdev_not_the_sample_one():
    """``ta.stdev``'s ``biased`` defaults to true: on 99, 101, 99, ... the deviation is 1 (the sample one would be
    sqrt(34/33) = 1.01504); on random closes it equals numpy's ddof=0 on every 34-bar window."""
    x = np.where(np.arange(80) % 2 == 0, 99.0, 101.0)
    d = RIB.ribbon(x, x + 0.5, x - 0.5, x)["dev"]
    assert np.isnan(d[:33]).all() and np.allclose(d[33:], 1.0, rtol=0, atol=1e-12)
    assert abs(PineScript(stdev_sample=True).run(x, x + 0.5, x - 0.5, x)["dev"][40] - math.sqrt(34 / 33)) < 1e-12
    bars = random_bars(2000, 11)
    out = RIB.ribbon(*bars)
    c = bars[3]
    ref = np.std(np.lib.stride_tricks.sliding_window_view(c, 34), axis=1, ddof=0)
    assert np.allclose(out["dev"][33:], ref, rtol=1e-12, atol=0)
    # the sample reading answers differently: a bar that is a bull setup only with the population deviation
    bad = PineScript(stdev_sample=True).run(*bars)
    j = np.flatnonzero(out["bull_setup"] & ~bad["bull_setup"])
    assert len(j) > 0
    k = int(j[0])
    a, dv = out["alma"][k], out["dev"][k]
    assert out["slope"][k] > 0.08 and a + dv * 0.65 < c[k] <= a + dv * math.sqrt(34 / 33) * 0.65 + 1e-9


def test_trap05_rma_seed_is_the_sma_of_the_first_14_true_ranges():
    """``ta.atr(14)`` = ``ta.rma(ta.tr(true), 14)``: na on bars 0-12, the mean of the first 14 true ranges at bar 13
    (the true range of bar 0 is high - low), then Wilder's update. Hand case: close 100, high / low 100 +- (i + 1) / 2,
    so the true range of bar i is i + 1: ATR = 7.5 at bar 13, (13 * 7.5 + 15) / 14 at bar 14."""
    n = 30
    i = np.arange(n, dtype=float)
    c = np.full(n, 100.0)
    h, lo = 100.0 + (i + 1) / 2, 100.0 - (i + 1) / 2
    atr = RIB.ribbon(c, h, lo, c)["atr"]
    assert np.isnan(atr[:13]).all()
    want = [7.5]
    for k in range(14, n):
        want.append((13 * want[-1] + (k + 1)) / 14)
    assert np.allclose(atr[13:], want, rtol=1e-14, atol=0)
    # the wrong seeds: the first true range (a value from bar 0), or a bar-0 true range of na (first value at bar 14)
    first = PineScript(atr_seed="first").run(c, h, lo, c)["atr"]
    assert first[0] == 1.0 and abs(first[13] - 7.5) > 1.0
    tr_na = PineScript(tr0="na").run(c, h, lo, c)["atr"]
    assert np.isnan(tr_na[:14]).all() and abs(tr_na[14] - 8.5) < 1e-12
    # the seed only matters in the warm-up: on a random walk the two seeds agree to 1e-12 after a few hundred bars
    bars = random_bars(1500, 5)
    good, bad = RIB.ribbon(*bars)["atr"], PineScript(atr_seed="first").run(*bars)["atr"]
    rel = np.abs(bad - good) / good
    assert rel[13] > 1e-3 and np.all(rel[600:] < 1e-12)


def test_trap06_no_reset_to_zero_after_a_stop():
    """A stopped-out position ends the drawing only (L498-580); the trend stays +1, so the bull setups after the stop
    are no flip. Path: flat 100, +0.4 a bar from bar 80, one wick down to 98 at bar 100. Bull flip at 83: risk = 101.2
    - min(low[71..82]) = 101.2 - 99.5 = 1.7 (inside [0.75, 3] ATR, ATR = 1), stop 99.5; bar 100's low 98 <= 99.5 stops
    it. The misreading (trend back to 0 after the stop) flips again at the next bull setup, bar 101."""
    o, h, l, c = path([(0, 100), (80, 100), (200, 148)], 201)
    l = l.copy()
    l[100] = c[100] - 10.0
    out = RIB.ribbon(o, h, l, c)
    assert abs(c[83] - 101.2) < 1e-12 and l[71:83].min() == 99.5
    assert out["risk_long"][83] == c[83] - 99.5 and abs(out["risk_long"][83] - 1.7) < 1e-12
    assert np.flatnonzero(out["flip"]).tolist() == [83] and out["flip"][83] == 1
    assert l[84:100].min() > 99.5 >= l[100]
    pos = PineScript().run(o, h, l, c)["positions"]
    assert len(pos) == 1 and (pos[0]["end_bar"], pos[0]["end_why"]) == (100, "stop") and pos[0]["stop"] == 99.5
    assert out["bull_setup"][101:].all() and np.all(out["trend"][83:] == 1)
    bad = PineScript(reset_after_stop=True).run(o, h, l, c)
    assert np.flatnonzero(bad["flip"]).tolist() == [83, 101]


def test_trap07_entry_at_the_close_not_at_the_next_m1_open():
    """The flip is a decision at the flip bar's close (``entryPrice := close``, L310; 0 bars of delay): it is on bar
    83 itself, known with the bars cut at 83, and its 1R is measured from close[83]. The harness fills at the next M1
    open; here bar 84 opens 0.9 above (a gap): the stop distance from that open, 102.1 - min(low[72..83]) = 2.6, or the
    distance at bar 84, 2.1, would be the misreadings; the port's is 1.7 at bar 83."""
    o, h, l, c = flat_up_flat_down()
    o = o.copy()
    o[84] = c[83] + 0.9
    out = RIB.ribbon(o, h, l, c)
    cut = RIB.ribbon(o[:84], h[:84], l[:84], c[:84])
    assert out["flip"][83] == 1 and out["flip"][84] == 0 and cut["flip"][83] == 1
    assert outputs_equal(cut, out, 84)
    assert abs(out["risk_long"][83] - 1.7) < 1e-12 and out["risk_long"][83] == c[83] - l[71:83].min()
    from_open = min(max(o[84] - l[72:84].min(), 0.75 * out["atr"][84]), 3 * out["atr"][84])
    assert abs(from_open - 2.6) < 1e-12 and abs(out["risk_long"][84] - 2.1) < 1e-12
    assert out["risk_long"][83] != from_open
    pos = PineScript().run(o, h, l, c)["positions"]
    assert pos[0]["entry_bar"] == 83 and pos[0]["entry"] == c[83]


def test_trap08_stop_from_the_fill_not_the_scripts_absolute_level():
    """The port returns the script's ``riskDist`` (entry - stop, L326-330) as a distance: the script's stop is the
    absolute level close - 1.7 = 99.5; the harness sets it 1.7 below its fill (102.1 after the gap: 100.4). Taking the
    level 99.5 from that fill would make 1R 2.6 and move every R target; both stops are built from the same 1.7."""
    o, h, l, c = flat_up_flat_down()
    o = o.copy()
    o[84] = c[83] + 0.9
    out = RIB.ribbon(o, h, l, c)
    for mode, key in (("intended", "risk_long"), ("literal", "risk_long_lit")):
        p = PineScript(stop=mode).run(o, h, l, c)["positions"][0]
        assert p["entry_bar"] == 83 and p["risk"] == out[key][83] and abs(p["entry"] - p["stop"] - out[key][83]) < 1e-12
    risk, fill = out["risk_long"][83], o[84]
    level = c[83] - risk                                          # the script's stop (L330)
    assert abs(level - 99.5) < 1e-12 and abs((fill - risk) - 100.4) < 1e-12
    assert abs((fill - level) - 2.6) < 1e-12                       # the absolute level's 1R from the fill
    # the literal first flip takes 0.75 ATR: from the fill the stop is fill - 0.75 ATR
    assert out["risk_long_lit"][83] == 0.75 * out["atr"][83]


def test_trap09_entry_bar_target_touches_are_not_counted():
    """L620-631 run on the entry bar too (``stoppedNow`` needs ``bar_index > entryBar``), so the flip bar's own high,
    reached BEFORE the entry at its close, can tick targets. Path: flat 100 (+-0.2), +0.4 a bar from bar 80, flat at
    101.2 from bar 83; the bull flip at 82 has a wick to 103.3. 1R = 100.8 - min(low[70..81]) = 100.8 - 99.8 = 1.0:
    T1 = 101.8 and T2 = 102.8 are ticked on the entry bar; after it the highs stay at 101.4, so no target is touched
    and the position ends at the bear flip (its stop, 99.8, is never reached)."""
    o, h, l, c = path([(0, 100), (80, 100), (83, 101.2), (200, 101.2), (260, 89.2), (300, 89.2)], 301, half=0.2)
    h = h.copy()
    h[82] = c[82] + 2.5
    out = RIB.ribbon(o, h, l, c)
    f = out["flip"]
    assert np.flatnonzero(f).tolist()[0] == 82 and f[82] == 1
    t = int(np.flatnonzero(f == -1)[0])
    r = out["risk_long"][82]
    assert abs(c[82] - 100.8) < 1e-12 and l[70:82].min() == 99.8 and r == c[82] - 99.8
    assert 0.75 * out["atr"][82] < r < 3 * out["atr"][82] and abs(r - 1.0) < 1e-12
    targets = c[82] + r * np.arange(1, 5)
    assert h[82] >= targets[1] and h[82] < targets[2] and h[83:t + 1].max() < targets[0]
    p = PineScript().run(o, h, l, c)["positions"][0]
    assert (p["end_bar"], p["end_why"]) == (t, "flip") and l[83:t + 1].min() > p["stop"]
    assert p["hit_bar"] == [82, 82, None, None]                   # the script's check marks
    assert p["hit_after"] == [None, None, None, None]             # what happened after the entry


def test_trap10_the_old_position_on_a_flip_bar():
    """On a flip bar the old position is frozen (L215-277) before the active-position block (L495-501), which then
    sees the NEW position (``bar_index > entryBar`` false): the old one is never stop-checked on the flip bar. Path:
    the long of bar 83 (stop 99.5) rides the ramp to 116 at bar 120; bar 121 crashes to 90, a bear flip whose low
    89.5 is far through 99.5. The script ends the long by the flip at 121; the M1 order (stop first) ends it by the
    stop. The port's flip is the same either way."""
    o, h, l, c = path([(0, 100), (80, 100), (120, 116), (200, 116)], 201)
    c = c.copy()
    c[121:] = 90.0
    o, h, l = np.concatenate(([c[0]], c[:-1])), c + 0.5, c - 0.5
    out = RIB.ribbon(o, h, l, c)
    assert np.flatnonzero(out["flip"]).tolist() == [83, 121] and out["flip"][121] == -1
    assert out["slope"][121] < -0.08 and c[121] < out["alma"][121] - 0.65 * out["dev"][121]
    stop = c[83] - out["risk_long"][83]
    assert abs(stop - 99.5) < 1e-12 and l[84:121].min() > stop >= l[121]
    script = PineScript().run(o, h, l, c)["positions"]
    m1 = PineScript(old_stop_on_flip_bar=True).run(o, h, l, c)["positions"]
    assert (script[0]["end_bar"], script[0]["end_why"]) == (121, "flip")
    assert (m1[0]["end_bar"], m1[0]["end_why"]) == (121, "stop")
    assert [p["entry_bar"] for p in script] == [p["entry_bar"] for p in m1] == [83, 121]
    assert np.array_equal(RIB.ribbon(o, h, l, c)["flip"], PineScript(old_stop_on_flip_bar=True).run(o, h, l, c)["flip"])


# ───────────────────────────── 2. the map's other test cases ─────────────────────────────

def test_alma_on_a_ramp_a_constant_and_an_impulse():
    w = weights(28.05)
    x = 1000.0 + 0.5 * np.arange(300.0)
    assert np.allclose(RIB.alma(x)[33:], x[33:] - 0.5 * 6.6607021454, rtol=0, atol=1e-9)
    for v in (1024.0, 0.5, 2.0 ** 11):                              # a power of two: exact
        assert np.all(RIB.alma(np.full(60, v))[33:] == v)
    k = np.full(60, 2034.567)
    assert np.allclose(RIB.alma(k)[33:], 2034.567, rtol=2e-16 * 34, atol=0)
    for j in range(34):                                             # a unit impulse j bars back
        imp = np.zeros(40)
        imp[39 - j] = 1.0
        assert abs(RIB.alma(imp)[39] - w[33 - j] / w.sum()) < 1e-16
    assert len(RIB.alma(np.arange(10.0))) == 10 and np.isnan(RIB.alma(np.arange(10.0))).all()
    centred = RIB.alma(np.arange(5.0), 3, 0.5, 1.0)                 # symmetric weights on a ramp: the middle value
    assert np.allclose(centred[2:], [1.0, 2.0, 3.0], rtol=0, atol=1e-15)


def test_stdev_equals_numpy_population_on_every_window():
    for seed in (1, 2):
        c = random_bars(1200, seed)[3]
        d = RIB.ribbon(c, c + 1, c - 1, c)["dev"]
        ref = np.std(np.lib.stride_tricks.sliding_window_view(c, 34), axis=1, ddof=0)
        assert np.isnan(d[:33]).all() and np.allclose(d[33:], ref, rtol=1e-12, atol=0)
    x = np.full(50, 123.456)                                         # a constant: exactly 0 (the 1e-10 rule)
    assert np.all(RIB.ribbon(x, x + 1, x - 1, x)["dev"][33:] == 0.0)


def test_strict_thresholds():
    """Strict ``>`` / ``<`` (L97-98). On path A the slope crosses 0.08 between bars 82 (0.073) and 83 (0.152), while
    the close is already above the band at 82: 82 is no setup, 83 is. Exactly at the threshold is no setup: with
    ``slope_min`` = the slope of bar 83, or ``dev_mult`` such that alma + dev * dev_mult == close at bar 83 exactly,
    bar 83 is not a setup; one step inside, it is. The misreading (``>=``) sets up at the threshold."""
    bars = flat_up_flat_down()
    c = bars[3]
    out = RIB.ribbon(*bars)
    assert out["slope"][82] < 0.08 < out["slope"][83] and c[82] > out["alma"][82] + 0.65 * out["dev"][82]
    assert not out["bull_setup"][82] and out["bull_setup"][83]
    s83 = float(out["slope"][83])
    assert not RIB.ribbon(*bars, slope_min=s83)["bull_setup"][83]
    assert RIB.ribbon(*bars, slope_min=math.nextafter(s83, 0.0))["bull_setup"][83]
    assert PineScript(slope_min=s83, strict=False).run(*bars)["bull_setup"][83]
    a, d, cc = float(out["alma"][83]), float(out["dev"][83]), float(c[83])
    below = (cc - a) / d                                            # the largest dev_mult whose band is below the close
    while a + d * below >= cc:
        below = math.nextafter(below, -math.inf)
    while a + d * math.nextafter(below, math.inf) < cc:
        below = math.nextafter(below, math.inf)
    m = math.nextafter(below, math.inf)                             # the next one: the band is exactly the close
    assert a + d * m == cc
    exact = RIB.ribbon(*bars, dev_mult=m)
    assert exact["slope"][83] == s83 and not exact["bull_setup"][83]
    assert RIB.ribbon(*bars, dev_mult=below)["bull_setup"][83]
    assert PineScript(dev_mult=m, strict=False).run(*bars)["bull_setup"][83]
    # the mirror for the bear side, on the mirrored path
    mir = [200.0 - x for x in (bars[0], bars[2], bars[1], bars[3])]
    mo = RIB.ribbon(*mir)
    assert np.array_equal(mo["bear_setup"], out["bull_setup"]) and np.array_equal(mo["flip"], -out["flip"])
    s83m = -float(mo["slope"][83])
    assert not RIB.ribbon(*mir, slope_min=s83m)["bear_setup"][83]
    assert RIB.ribbon(*mir, slope_min=math.nextafter(s83m, 0.0))["bear_setup"][83]


def test_flat_up_flat_down_one_bull_flip_the_trend_persists_one_bear_flip():
    out = RIB.ribbon(*flat_up_flat_down())
    assert np.flatnonzero(out["flip"]).tolist() == [83, 223] and out["flip"][83] == 1 and out["flip"][223] == -1
    assert np.all(out["trend"][:83] == 0) and np.all(out["trend"][83:223] == 1) and np.all(out["trend"][223:] == -1)
    assert np.flatnonzero(out["bull_setup"])[-1] == 140 and not out["bear_setup"][:223].any()
    assert not (out["bull_setup"][141:223] | out["bear_setup"][141:223]).any()    # the flat: no setup, the trend stays
    assert out["bear_setup"][224:280].sum() == 56 and np.all(out["flip"][224:] == 0)  # later setups: no flip


def test_one_condition_alone_never_sets_up():
    """A setup needs the slope AND the close beyond the band. Bars with only one of them occur (path A's bar 82 has
    only the band; the end of its up-ramp only the slope; random walks both kinds) and none is a setup or a flip."""
    for bars in (flat_up_flat_down(), random_bars(4000, 3), random_bars(4000, 4, decimals=1)):
        out = RIB.ribbon(*bars)
        c = bars[3]
        with np.errstate(invalid="ignore"):
            sl_up, band_up = out["slope"] > 0.08, c > out["alma"] + out["dev"] * 0.65
            sl_dn, band_dn = out["slope"] < -0.08, c < out["alma"] - out["dev"] * 0.65
        assert np.array_equal(out["bull_setup"], sl_up & band_up) and np.array_equal(out["bear_setup"], sl_dn & band_dn)
        for alone in (sl_up & ~band_up, band_up & ~sl_up, sl_dn & ~band_dn, band_dn & ~sl_dn):
            assert alone.any()
            assert not (out["bull_setup"][alone] | out["bear_setup"][alone]).any() and np.all(out["flip"][alone] == 0)
    a = RIB.ribbon(*flat_up_flat_down())
    c = flat_up_flat_down()[3]
    assert a["slope"][82] < 0.08 and c[82] > a["alma"][82] + 0.65 * a["dev"][82] and a["flip"][82] == 0   # band only
    assert a["slope"][141:150].min() > 0.08 and not a["bull_setup"][141:150].any()      # only the slope after the ramp


def test_clamp_branches():
    """riskDist = min(max(nz(raw, 0.75 ATR), 0.75 ATR), 3 ATR) (L326-328) for raw < 0, 0 < raw < 0.75 ATR, raw inside,
    raw > 3 ATR and a missing raw."""
    o, h, l, c = path([(0, 100), (80, 100), (120, 116), (200, 116)], 201)
    c = c.copy()
    c[121:] = 90.0
    o, h, l = np.concatenate(([c[0]], c[:-1])), c + 0.5, c - 0.5
    out = RIB.ribbon(o, h, l, c)
    atr = out["atr"]
    assert c[121] - l[109:121].min() < 0 and out["risk_long"][121] == 0.75 * atr[121]      # raw < 0 (the crash)
    assert 0 < c[60] - l[48:60].min() < 0.75 * atr[60] and out["risk_long"][60] == 0.75 * atr[60]   # 0.5 < 0.75
    assert out["risk_long"][83] == c[83] - l[71:83].min() and 0.75 * atr[83] < out["risk_long"][83] < 3 * atr[83]
    assert c[100] - l[88:100].min() > 3 * atr[100] and out["risk_long"][100] == 3 * atr[100]   # 5.3 > 3
    assert out["risk_short"][121] == 3 * atr[121] and out["risk_short"][60] == 0.75 * atr[60]
    # a missing raw: the 20-bar structure exists from bar 20, the ATR from bar 13
    w = RIB.ribbon(o, h, l, c, stop_lookback=20)
    assert np.isnan(w["risk_long"][:13]).all() and np.isnan(w["risk_short"][:13]).all()
    assert np.array_equal(w["risk_long"][13:20], 0.75 * w["atr"][13:20])
    assert np.array_equal(w["risk_short"][13:20], 0.75 * w["atr"][13:20])
    assert w["risk_long"][20] == max(c[20] - l[0:20].min(), 0.75 * w["atr"][20])
    # the literal reading's first flip of each side: na -> 0.75 ATR
    assert out["risk_long_lit"][83] == 0.75 * atr[83] and out["risk_short_lit"][121] == 0.75 * atr[121]


def test_warm_up_bars_and_the_first_values():
    """alma / dev / edges from bar 33, atr and the risks from 13, the slope and the conviction 0.0 on bars 0-12 (the
    ATR is na, so ``atr > 0`` is false), NaN on 13-35 and values from 36; no setup before 36."""
    bars = random_bars(400, 21)
    out = RIB.ribbon(*bars)
    first = {k: int(np.flatnonzero(~np.isnan(out[k]))[0]) for k in ("alma", "dev", "atr", "edge_up", "edge_dn",
                                                                      "risk_long", "risk_short")}
    assert first == {"alma": 33, "dev": 33, "atr": 13, "edge_up": 33, "edge_dn": 33, "risk_long": 13,
                     "risk_short": 13}
    for k in ("alma", "dev", "atr", "edge_up", "edge_dn", "risk_long", "risk_short"):
        assert not np.isnan(out[k][first[k]:]).any(), k
    for k in ("slope", "conviction"):
        assert np.all(out[k][:13] == 0.0) and np.isnan(out[k][13:36]).all() and not np.isnan(out[k][36:]).any(), k
    assert not (out["bull_setup"][:36] | out["bear_setup"][:36]).any() and np.all(out["trend"][:36] == 0)
    with np.errstate(invalid="ignore"):
        assert np.all((out["conviction"][36:] >= 0) & (out["conviction"][36:] <= 1))
    other = RIB.ribbon(*bars, alma_len=20, dev_len=25, slope_len=5, atr_len=10, stop_lookback=8)
    assert int(np.flatnonzero(~np.isnan(other["alma"]))[0]) == 19 and np.isnan(other["edge_up"][:24]).all()
    sl = other["slope"]
    assert np.all(sl[:9] == 0.0) and np.isnan(sl[9:24]).all() and not np.isnan(sl[24:]).any()


def test_conviction_and_the_ribbon_edges_by_hand():
    """L120-128 on bar 130 of path A (its window and the one 3 bars back on the up-ramp): the slope is 0.4 * 3 / 1 =
    1.2, so conviction = min(1, |slope| * 2 + |close - alma| / ATR * 0.35) = 1; on the flat after the ramp (bar 152)
    it is the formula's value, below 1; the edges are alma +- 0.55 dev on every bar."""
    bars = flat_up_flat_down()
    out = RIB.ribbon(*bars)
    c = bars[3]
    assert abs(out["slope"][130] - 1.2) < 1e-9 and out["conviction"][130] == 1.0
    k = 152
    want = abs(out["slope"][k]) * 2.0 + abs(c[k] - out["alma"][k]) / out["atr"][k] * 0.35
    assert 0 < want < 1 and out["conviction"][k] == want
    assert same(out["edge_up"], out["alma"] + out["dev"] * 0.55)
    assert same(out["edge_dn"], out["alma"] - out["dev"] * 0.55)


def test_trend_closed_form_flips_alternate_and_never_return_to_zero():
    for seed in (1, 2, 3):
        out = RIB.ribbon(*random_bars(5000, seed, decimals=1))
        side = np.where(out["bull_setup"], 1, np.where(out["bear_setup"], -1, 0))
        tr, fl = out["trend"], out["flip"]
        last = 0
        for t in range(len(side)):
            prev = last
            if side[t] != 0:
                last = side[t]
            assert tr[t] == last and fl[t] == (side[t] if side[t] != 0 and side[t] != prev else 0)
        nz = np.flatnonzero(fl)
        assert len(nz) > 20 and np.all(fl[nz][1:] != fl[nz][:-1]) and np.all(tr[nz[0]:] != 0)
        assert not (out["bull_setup"] & out["bear_setup"]).any()


def test_output_keys_dtypes_and_inputs():
    bars = random_bars(300, 9)
    copies = [x.copy() for x in bars]
    out = RIB.ribbon(*bars)
    assert tuple(out) == RIB.KEYS and len(RIB.KEYS) == 15
    for k, v in out.items():
        assert isinstance(v, np.ndarray) and v.shape == (300,), k
        want = {"bull_setup": np.bool_, "bear_setup": np.bool_, "trend": np.int8, "flip": np.int8}.get(k, np.float64)
        assert v.dtype == want, k
    assert all(np.array_equal(a, b) for a, b in zip(bars, copies))           # inputs left alone
    assert outputs_equal(RIB.ribbon(*[list(x) for x in bars]), out)          # lists are fine
    # the open is not read
    assert outputs_equal(RIB.ribbon(bars[0] * 0 + 7.0, *bars[1:]), out)
    for n in (0, 1, 5, 13, 34, 36):
        tiny = RIB.ribbon(*[x[:n] for x in bars])
        assert all(len(v) == n for v in tiny.values())
        assert outputs_equal(tiny, out, n) if n else True
    with pytest.raises(ValueError):
        RIB.ribbon(bars[0], bars[1], bars[2], bars[3][:-1])
    bad = bars[3].copy()
    bad[50] = np.nan
    with pytest.raises(ValueError):
        RIB.ribbon(bars[0], bars[1], bars[2], bad)
    with pytest.raises(ValueError):
        RIB.ribbon(*[np.vstack([x, x]) for x in bars])
    for kw in ({"alma_len": 0}, {"atr_len": 2.5}, {"slope_min": -0.1}, {"stop_lookback": True}, {"dev_mult": np.inf}):
        with pytest.raises(ValueError):
            RIB.ribbon(*bars, **kw)
    with pytest.raises(ValueError):
        RIB.alma(bars[3], sigma=0.0)


# ───────────────────────────── 3. the port against the transcription ─────────────────────────────

@pytest.mark.parametrize("seed,decimals", [(1, None), (2, None), (3, 1), (4, 0), (5, 2)])
def test_port_equals_the_transcription_bit_for_bit_on_random_bars(seed, decimals):
    """Every output, bit for bit, on random walks (rounded prices give equal closes, flat stretches and ties)."""
    bars = random_bars(2500, seed, decimals=decimals, vol=0.5 if decimals == 0 else 1.0)
    port, ref = RIB.ribbon(*bars), PineScript().run(*bars)
    assert outputs_equal(port, ref)
    assert (port["flip"] != 0).sum() > 20


@pytest.mark.parametrize("kw", [dict(alma_len=20, alma_offset=0.5, alma_sigma=3.0, dev_len=10, dev_mult=0.2,
                                     slope_len=1, slope_min=0.0, atr_len=5, stop_lookback=3, min_stop_atr=0.25,
                                     max_stop_atr=8.0, edge_mult=1.0),
                                dict(alma_len=5, dev_len=50, slope_len=10, slope_min=1.0, atr_len=30,
                                     stop_lookback=50, min_stop_atr=3.0, max_stop_atr=1.0),
                                # flips before bar stop_lookback - 1 (added at the reconciliation, trap01c)
                                dict(alma_len=5, dev_len=5, slope_len=1, slope_min=0.02, atr_len=5, stop_lookback=50)])
def test_port_equals_the_transcription_with_other_inputs(kw):
    bars = random_bars(2000, 8)
    port = RIB.ribbon(*bars, **kw)
    assert outputs_equal(port, PineScript(**kw).run(*bars))
    if kw.get("stop_lookback") == 50 and kw.get("dev_len") == 5:
        early = np.flatnonzero(port["flip"][:kw["stop_lookback"] - 1])
        assert len(early) >= 2                                     # the case is exercised on both sides
        assert set(port["flip"][early]) == {-1, 1}


def test_port_equals_the_transcription_on_the_hand_paths():
    for bars in (flat_up_flat_down(), rising_zigzag()[0]):
        assert outputs_equal(RIB.ribbon(*bars), PineScript().run(*bars))


# ───────────────────────────── 4. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_outputs_to_t_do_not_change_when_the_bars_after_t_are_removed(seed):
    bars = random_bars(3000, seed, decimals=1 if seed == 3 else None)
    full = RIB.ribbon(*bars)
    flips = np.flatnonzero(full["flip"])
    cuts = [0, 1, 12, 13, 33, 36, 37, 500, 1777, 2999, int(flips[5]), int(flips[5]) + 1, int(flips[-1])]
    for T in cuts:
        part = RIB.ribbon(*[x[:T + 1] for x in bars])
        assert outputs_equal(part, full, T + 1), T


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
        out = RIB.ribbon(b.o, b.h, b.l, b.c)
        assert tuple(out) == RIB.KEYS
        for k, v in out.items():
            assert v.shape == (n,), (tf, k)
        # no NaN where the contract says values exist, NaN where it says none
        for k, f0 in (("alma", 33), ("dev", 33), ("edge_up", 33), ("edge_dn", 33), ("atr", 13), ("risk_long", 13),
                      ("risk_short", 13)):
            assert np.isnan(out[k][:f0]).all() and np.isfinite(out[k][f0:]).all(), (tf, k)
        for k in ("slope", "conviction"):
            assert np.all(out[k][:13] == 0.0) and np.isnan(out[k][13:36]).all() and np.isfinite(out[k][36:]).all()
        bf, sf = out["flip"] == 1, out["flip"] == -1
        assert np.isfinite(out["risk_long_lit"][bf]).all() and np.isnan(out["risk_long_lit"][~bf]).all(), tf
        assert np.isfinite(out["risk_short_lit"][sf]).all() and np.isnan(out["risk_short_lit"][~sf]).all(), tf
        # ranges and structure
        assert np.all((out["conviction"][36:] >= 0) & (out["conviction"][36:] <= 1)) and np.all(out["atr"][13:] > 0)
        atr = out["atr"]
        for k, m in (("risk_long", np.ones(n, bool)), ("risk_short", np.ones(n, bool)), ("risk_long_lit", bf),
                     ("risk_short_lit", sf)):
            r = out[k][m & (np.arange(n) >= 13)]
            lo, hi = 0.75 * atr[m & (np.arange(n) >= 13)], 3 * atr[m & (np.arange(n) >= 13)]
            assert np.all((r >= lo) & (r <= hi)), (tf, k)
        assert not (out["bull_setup"] & out["bear_setup"]).any()
        nz = np.flatnonzero(out["flip"])
        assert len(nz) > 30 and np.all(out["flip"][nz][1:] != out["flip"][nz][:-1])
        assert np.all(out["trend"][:nz[0]] == 0) and np.all(out["trend"][nz[0]:] != 0)
        assert int(b.tc[nz[0]]) < a19                                       # the trend exists before 2019
        assert set(np.unique(out["trend"][int(np.searchsorted(b.tc, a19)):])) == {-1, 1}


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_equal_the_transcription_bit_for_bit(symbol, real):
    tbars = real(symbol)
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        port = RIB.ribbon(b.o, b.h, b.l, b.c)
        ref = PineScript().run(b.o, b.h, b.l, b.c)
        assert outputs_equal(port, ref), tf
        # the ATR primitive against external.py's Wilder ATR (another update order)
        wa = X.wilder_atr(b.h, b.l, b.c, 14)
        assert np.nanmax(np.abs(port["atr"][13:] - wa[13:]) / wa[13:]) < 1e-12, tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_truncation_invariance(symbol, real):
    tbars = real(symbol)
    for tf in ("1H", "4H", "1D"):
        b = tbars[tf]
        full = RIB.ribbon(b.o, b.h, b.l, b.c)
        for when in ("2020-03-16 12:00", "2022-11-09 00:00"):
            j = int(np.searchsorted(b.tc, TM.s_of(when), side="right")) - 1
            part = RIB.ribbon(b.o[:j + 1], b.h[:j + 1], b.l[:j + 1], b.c[:j + 1])
            assert outputs_equal(part, full, j + 1), (tf, when)
