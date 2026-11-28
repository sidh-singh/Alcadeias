"""
Port B (the oracle) of BOSWaves' Trend Target Ribbon, ``tests/tradeiq2_oracle_ribbon.py`` (study 2, PREREG 6.1).

1. One hand-computed test per trap of the spec's porting risks (``maps/ribbon_patterns.md`` A6 "Risks", nine items),
   named after it: the stop scope, the ALMA weight orientation (and the unfloored m), the population stdev, the RMA
   seed, no reset to 0 after a stop, the entry at the close (not the next M1 open), the stop from the fill (not the
   script's absolute level), the entry-bar target touches, the old position on a flip bar. Each builds bars by hand
   and states the expected values with their arithmetic; where a wrong reading is easy to write, the test also shows
   that it gives another value.
2. The spec's other test cases (A6 "Test cases"): ALMA on a ramp, a constant and an impulse; the stdev against numpy
   (ddof=0) on every window; the strict thresholds at the exact critical values; flat -> up -> flat -> down; no flip
   when only the slope or only the band holds; the stop's clamp branches; the closed forms of the trend and of the
   literal stop; the ``ta.lowest`` call site; an independent numpy formulation of every float line.
3. Truncation invariance: the outputs up to bar T are unchanged when the bars after T are removed.
4. Real bars (skipped when the tick store is absent): both symbols, the 1H / 4H / 1D bars the PREREG uses for this
   script, from the data start to 2024-06-30 (study 1's guard pointed at an empty folder, so the hold-out cannot be
   served): it runs, every value the contract defines exists, the invariants hold, a cut at one T changes nothing
   before it, and the numpy formulation agrees.

Port A (``backtesting/research/tradeiq2_ind_ribbon.py``) was not read or imported; the two are compared later.
"""

from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest
from numpy.lib.stride_tricks import sliding_window_view

from backtesting.data import store
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_ribbon as O  # noqa: E402

nan = math.nan
LAG = 6.6607021454             # the ALMA(34, 0.85, 6) lag on a linear ramp (spec A1)
FLOATS = ("alma", "dev", "atr", "slope", "conviction", "edge_up", "edge_dn",
          "risk_long", "risk_short", "risk_long_lit", "risk_short_lit")


# ───────────────────────────── helpers ─────────────────────────────

def from_close(c, w=0.25):
    """Bars from closes: open = the previous close (the first bar opens at its close), high / low = the body +- w."""
    c = np.asarray(c, np.float64)
    o = np.r_[c[0], c[:-1]]
    return o, np.maximum(o, c) + w, np.minimum(o, c) - w, c.copy()


def walk(n, seed, p0=1500.0, vol=2.0):
    """A random walk with wicks (gold-like for p0 = 1500, BTC-like for p0 = 30000, vol = 100), with a few gaps."""
    rng = np.random.default_rng(seed)
    c = p0 + np.cumsum(rng.normal(0.0, vol, n))
    o = np.r_[p0, c[:-1]] + rng.normal(0.0, vol / 4, n) * (rng.random(n) < 0.05)
    h = np.maximum(o, c) + rng.uniform(0.0, vol, n)
    l = np.minimum(o, c) - rng.uniform(0.0, vol, n)
    return o, h, l, c


def same(a, b) -> bool:
    """Bit-for-bit equality, NaN equal to NaN."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        return bool(np.array_equal(a.view(np.int64), b.view(np.int64)) or np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def flips(r):
    f = np.flatnonzero(r["flip"])
    return list(zip(f.tolist(), r["flip"][f].tolist()))


def path_fufd():
    """Flat 100 for 60 bars, up 1 a bar to 140 (bars 60-99), flat 140 (100-159), down to 100 (160-199), flat 100."""
    return from_close(np.r_[np.full(60, 100.0), 100 + np.arange(1, 41.0), np.full(60, 140.0),
                            140 - np.arange(1, 41.0), np.full(40, 100.0)])


def path_three_bull_flips():
    """Five flips at hand-chosen levels (the stop-scope trap): bull flips at 60 (level 110), 270 (100), 470 (100.25),
    bear flips at 160 (from 150) and 370 (from 140). Every flat bar has low = level - 0.25, high = level + 0.25."""
    return from_close(np.concatenate([
        np.full(60, 110.0), 110 + np.arange(1, 41.0), np.full(60, 150.0), 150 - np.arange(1, 51.0),
        np.full(60, 100.0), 100 + np.arange(1, 41.0), np.full(60, 140.0), 140 - np.arange(1, 40.0), [100.25],
        np.full(60, 100.25), 100.25 + np.arange(1, 41.0), np.full(30, 140.25)]))


def alma_weights_np(n=34, offset=0.85, sigma=6.0):
    i = np.arange(n, dtype=np.float64)
    m, s = offset * (n - 1), n / sigma
    return np.exp(-((i - m) ** 2) / (2.0 * s * s))


def np_ribbon(o, h, l, c):
    """An independent vectorised formulation of every float line (other arithmetic, so equal to ~1e-12, not bitwise)."""
    o, h, l, c = (np.asarray(x, np.float64) for x in (o, h, l, c))
    n = c.size
    w = alma_weights_np()
    alma = np.full(n, np.nan)
    dev = np.full(n, np.nan)
    if n >= 34:
        win = sliding_window_view(c, 34)                    # win[k] = c[k .. k+33]: weight i on close[33 - i]
        alma[33:] = win @ w / w.sum()
        dev[33:] = win.std(axis=1)                          # ddof = 0: the population deviation
    tr = h - l
    tr[1:] = np.maximum(np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1])), np.abs(l[1:] - c[:-1]))
    atr = np.full(n, np.nan)
    if n >= 14:
        atr[13] = tr[:14].mean()
        for t in range(14, n):
            atr[t] = (atr[t - 1] * 13.0 + tr[t]) / 14.0
    a3 = np.full(n, np.nan)
    a3[3:] = alma[:-3]
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = atr > 0
        slope = np.where(pos, (alma - a3) / atr, 0.0)
        dist = np.where(pos, np.abs(c - alma) / atr, 0.0)
        conviction = np.clip(np.abs(slope) * 2.0 + dist * 0.35, 0.0, 1.0)
    lo = np.full(n, np.nan)
    hi = np.full(n, np.nan)
    if n > 12:
        lo[12:] = sliding_window_view(l, 12).min(axis=1)[:-1]   # min(low[t-12 .. t-1])
        hi[12:] = sliding_window_view(h, 12).max(axis=1)[:-1]

    def clamp(raw):
        lo_r, hi_r = 0.75 * atr, 3.0 * atr
        with np.errstate(invalid="ignore"):
            return np.minimum(np.maximum(np.where(np.isnan(raw), lo_r, raw), lo_r), hi_r)

    return {"alma": alma, "dev": dev, "atr": atr, "slope": slope, "conviction": conviction,
            "edge_up": alma + 0.55 * dev, "edge_dn": alma - 0.55 * dev,
            "upper": alma + 0.65 * dev, "lower": alma - 0.65 * dev,
            "risk_long": clamp(c - lo), "risk_short": clamp(hi - c)}


def check_cross(r, o, h, l, c, rtol=1e-9):
    """The oracle against ``np_ribbon``: the floats to rtol (scaled by the price for the price lines), the setups
    exactly wherever the margin to the thresholds exceeds 1e-7 of the scale."""
    q = np_ribbon(o, h, l, c)
    scale = float(np.max(np.abs(c)))
    for k in ("alma", "edge_up", "edge_dn"):
        assert same(np.isnan(r[k]), np.isnan(q[k])), k
        assert np.allclose(r[k], q[k], rtol=0, atol=rtol * scale, equal_nan=True), k
    for k in ("dev", "atr", "risk_long", "risk_short"):
        assert same(np.isnan(r[k]), np.isnan(q[k])), k
        assert np.allclose(r[k], q[k], rtol=1e-8, atol=rtol * scale, equal_nan=True), k
    for k in ("slope", "conviction"):
        assert same(np.isnan(r[k]), np.isnan(q[k])), k
        assert np.allclose(r[k], q[k], rtol=1e-8, atol=1e-8, equal_nan=True), k
    with np.errstate(invalid="ignore"):
        bull = (q["slope"] > 0.08) & (c > q["upper"])
        bear = (q["slope"] < -0.08) & (c < q["lower"])
        clear = (np.abs(q["slope"] - 0.08) > 1e-7) & (np.abs(q["slope"] + 0.08) > 1e-7) & \
                (np.abs(c - q["upper"]) > 1e-7 * scale) & (np.abs(c - q["lower"]) > 1e-7 * scale)
    assert np.array_equal(r["bull_setup"][clear], bull[clear])
    assert np.array_equal(r["bear_setup"][clear], bear[clear])


def trend_closed_form(bull_setup, bear_setup):
    """Spec A1 step 6: the trend is the side of the most recent setup bar (0 before the first); a flip is the first
    setup bar of the other side."""
    n = len(bull_setup)
    trend = np.zeros(n, np.int8)
    flip = np.zeros(n, np.int8)
    side = 0
    for t in range(n):
        if bull_setup[t]:
            side = 1
        elif bear_setup[t]:
            side = -1
        trend[t] = side
        if side != 0 and (t == 0 or trend[t - 1] != side):
            flip[t] = side
    return trend, flip


def literal_closed_form(r, l, h, c, full=False):
    """Spec A2 (literal): the k-th bull flip's structure low = min of the lows of bull flips k-12 .. k-1 (none for
    k = 1); ``full``: none until k = 13. Bear flips mirror it with the highs. Then the same clamp."""
    out_l = np.full(len(c), np.nan)
    out_s = np.full(len(c), np.nan)
    for side, src, out in ((1, l, out_l), (-1, h, out_s)):
        bars = np.flatnonzero(r["flip"] == side)
        for k, t in enumerate(bars, start=1):
            prev = [float(src[b]) for b in bars[max(0, k - 13):k - 1]]   # flips max(1, k-12) .. k-1
            if not prev or (full and k <= 12):
                level = nan
            else:
                level = min(prev) if side == 1 else max(prev)
            raw = c[t] - level if side == 1 else level - c[t]
            a = float(r["atr"][t])
            lo_r, hi_r = a * 0.75, a * 3.0
            raw = lo_r if math.isnan(raw) else raw
            out[t] = min(max(raw, lo_r), hi_r)
    return out_l, out_s


def check_where_values_exist(r, c, warm_alma=33, warm_atr=13, warm_slope=36):
    """The contract's NaN map: values exist exactly where the module docstring says (default inputs)."""
    n = len(c)
    assert set(r) == set(O.KEYS) and all(len(v) == n for v in r.values())
    t = np.arange(n)
    for k in ("alma", "dev", "edge_up", "edge_dn"):
        assert np.all(np.isnan(r[k][t < warm_alma])) and np.all(np.isfinite(r[k][t >= warm_alma])), k
    assert np.all(np.isnan(r["atr"][t < warm_atr])) and np.all(r["atr"][t >= warm_atr] > 0)
    for k in ("slope", "conviction"):
        assert np.all(r[k][t < warm_atr] == 0.0), k                                    # atr > 0 is false on na
        assert np.all(np.isnan(r[k][(t >= warm_atr) & (t < warm_slope)])), k          # alma[3] is na
        assert np.all(np.isfinite(r[k][t >= warm_slope])), k
    assert np.all((r["conviction"][t >= warm_slope] >= 0) & (r["conviction"][t >= warm_slope] <= 1))
    for k in ("risk_long", "risk_short"):
        v = r[k]
        assert np.all(np.isnan(v[t < warm_atr])) and np.all(np.isfinite(v[t >= warm_atr])), k
        a = r["atr"][t >= warm_atr]
        assert np.all(v[t >= warm_atr] >= a * 0.75) and np.all(v[t >= warm_atr] <= a * 3.0), k
    for k, side in (("risk_long_lit", 1), ("risk_short_lit", -1)):
        on = r["flip"] == side
        assert np.all(np.isfinite(r[k][on])) and np.all(np.isnan(r[k][~on])), k
        assert np.all(r[k][on] >= r["atr"][on] * 0.75) and np.all(r[k][on] <= r["atr"][on] * 3.0), k
    assert not np.any(r["bull_setup"] & r["bear_setup"])
    assert not np.any(r["bull_setup"][t < warm_slope]) and not np.any(r["bear_setup"][t < warm_slope])
    assert set(np.unique(r["trend"])) <= {-1, 0, 1} and set(np.unique(r["flip"])) <= {-1, 0, 1}
    nz = np.flatnonzero(r["trend"] != 0)
    if nz.size:                                              # 0 before the first flip, never 0 again
        assert np.all(r["trend"][:nz[0]] == 0) and np.all(r["trend"][nz[0]:] != 0)
    prev = np.r_[0, r["trend"][:-1]]
    assert np.array_equal(r["flip"], np.where(r["trend"] != prev, r["trend"], 0).astype(np.int8))


# ───────────────────────────── 0. the contract ─────────────────────────────

def test_contract_keys_dtypes_and_signature():
    sig = inspect.signature(O.ribbon)
    assert list(sig.parameters) == ["o", "h", "l", "c", "alma_len", "alma_offset", "alma_sigma", "dev_len",
                                    "dev_mult", "slope_len", "slope_min", "atr_len", "stop_lookback",
                                    "min_stop_atr", "max_stop_atr", "edge_mult"]
    defaults = {k: p.default for k, p in sig.parameters.items() if p.default is not inspect.Parameter.empty}
    assert defaults == dict(alma_len=34, alma_offset=0.85, alma_sigma=6.0, dev_len=34, dev_mult=0.65, slope_len=3,
                            slope_min=0.08, atr_len=14, stop_lookback=12, min_stop_atr=0.75, max_stop_atr=3.0,
                            edge_mult=0.55)
    r = O.ribbon(*walk(300, 1))
    assert tuple(r) == O.KEYS
    for k in FLOATS:
        assert r[k].dtype == np.float64 and r[k].shape == (300,), k
    assert r["bull_setup"].dtype == np.bool_ and r["bear_setup"].dtype == np.bool_
    assert r["trend"].dtype == np.int8 and r["flip"].dtype == np.int8


def test_where_values_exist_on_synthetic_bars():
    for seed, p0, vol in ((1, 1500.0, 2.0), (2, 30000.0, 100.0)):
        o, h, l, c = walk(900, seed, p0, vol)
        r = O.ribbon(o, h, l, c)
        check_where_values_exist(r, c)
        assert len(flips(r)) > 10


def test_inputs_refused_and_left_alone():
    o, h, l, c = walk(120, 3)
    keep = [x.copy() for x in (o, h, l, c)]
    O.ribbon(o, h, l, c)
    assert all(same(a, b) for a, b in zip(keep, (o, h, l, c)))
    bad = c.copy()
    bad[50] = nan
    with pytest.raises(ValueError):
        O.ribbon(o, h, l, bad)
    with pytest.raises(ValueError):
        O.ribbon(o, h, l, c[:-1])
    with pytest.raises(ValueError):
        O.ribbon(o, h, l, c, alma_len=0)
    with pytest.raises(ValueError):
        O.script_positions(o, h, l, c, target_count=5)                  # L39: 2 .. 4 targets
    with pytest.raises(ValueError):
        O.script_positions(o, h, l, c, stop="fill")
    assert all(len(v) == 0 for v in O.ribbon([], [], [], []).values())


# ───────────────────────────── 1. the traps (spec A6 "Risks") ─────────────────────────────

def test_trap_stop_scope_literal_vs_intended():
    """L315-317 sit inside ``if flip`` and a ternary. Intended: the 12 bars before the flip bar. Literal: the lows
    (highs) of the earlier bull (bear) flip bars, ``[1]`` = the previous execution."""
    o, h, l, c = path_three_bull_flips()
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1), (160, -1), (270, 1), (370, -1), (470, 1)]
    a = r["atr"]
    # the flip bars (open, high, low, close): every one sits after a 60-bar flat at its level
    assert (o[60], h[60], l[60], c[60]) == (110.0, 111.25, 109.75, 111.0)
    assert (o[270], h[270], l[270], c[270]) == (100.0, 101.25, 99.75, 101.0)
    assert (o[470], h[470], l[470], c[470]) == (100.25, 101.5, 100.0, 101.25)
    assert (o[160], h[160], l[160], c[160]) == (150.0, 150.25, 148.75, 149.0)
    assert (o[370], h[370], l[370], c[370]) == (140.0, 140.25, 138.75, 139.0)
    # every flip's ATR is about 0.58: the clamp is [0.44, 1.75]
    for t, _ in flips(r):
        assert 0.57 < a[t] < 0.59
    # INTENDED: the 12 bars before each flip are flat at its level, so raw = 1 + 0.25 = 1.25, inside the clamp
    for t in (60, 270, 470):
        assert r["risk_long"][t] == 1.25                     # close - (level - 0.25)
    for t in (160, 370):
        assert r["risk_short"][t] == 1.25                    # (level + 0.25) - close
    # LITERAL, longs: k = 1 has no previous execution -> nz -> 0.75 ATR;
    # k = 2: 101 - low(flip 1) = 101 - 109.75 = -8.75 < 0 -> 0.75 ATR;
    # k = 3: 101.25 - min(109.75, 99.75) = 1.5, inside the clamp -> 1.5 (the intended reading says 1.25)
    assert r["risk_long_lit"][60] == a[60] * 0.75
    assert r["risk_long_lit"][270] == a[270] * 0.75
    assert r["risk_long_lit"][470] == 1.5
    # LITERAL, shorts: k = 1 -> 0.75 ATR; k = 2: high(flip 1) - 139 = 150.25 - 139 = 11.25 > 3 ATR -> 3 ATR
    assert r["risk_short_lit"][160] == a[160] * 0.75
    assert r["risk_short_lit"][370] == a[370] * 3.0
    # defined on that side's flips only
    assert set(np.flatnonzero(np.isfinite(r["risk_long_lit"]))) == {60, 270, 470}
    assert set(np.flatnonzero(np.isfinite(r["risk_short_lit"]))) == {160, 370}
    # the measured alternative (na until 12 values were buffered) floors all of them
    alt = O._ribbon_vm(o, h, l, c, lit_full=True)
    assert alt["risk_long_lit"][470] == a[470] * 0.75 and alt["risk_short_lit"][370] == a[370] * 0.75
    for k in O.KEYS:                                         # and changes nothing else
        if k not in ("risk_long_lit", "risk_short_lit"):
            assert same(alt[k], r[k]), k


def test_trap_alma_weight_orientation():
    """Weight i applies to close[33 - i] (the reference's ``series[windowsize - i - 1]``): the current bar has 0.683
    of the peak weight and the lag on a ramp is 6.66 bars; reversed weights would give 26.34."""
    n = 120
    x = np.arange(n, dtype=np.float64)
    r = O.ribbon(x, x + 0.5, x - 0.5, x)
    lag = x[33:] - r["alma"][33:]
    assert np.allclose(lag, LAG, rtol=0, atol=1e-9)
    w = np.array(O.Alma(34, 0.85, 6.0).w)
    reversed_lag = float(np.sum(w * np.arange(34)) / w.sum())        # weight i on close[i]
    assert abs(reversed_lag - 26.339297854617) < 1e-9 and abs(lag[0] - reversed_lag) > 19
    # a unit impulse at bar 50: the response j bars later is w[33 - j] / sum(w), largest 5 bars later (i = 28)
    imp = np.zeros(n)
    imp[50] = 1.0
    ri = O.ribbon(imp, imp, imp, imp)["alma"]
    wn = alma_weights_np() / alma_weights_np().sum()
    for j in range(34):
        assert ri[50 + j] == pytest.approx(wn[33 - j], rel=1e-12, abs=0), j
    assert np.all(ri[84:] == 0.0) and np.all(ri[33:50] == 0.0)
    assert int(np.nanargmax(ri)) == 55
    assert ri[50] == pytest.approx(0.0577622438999643, rel=1e-12)            # the current bar's share
    assert abs(ri[50] - wn[0]) > 0.05                                         # not the oldest weight (3.4e-7)


def test_trap_alma_m_not_floored():
    """``ta.alma(src, 34, 0.85, 6.0)`` passes no ``floor``: m = 0.85 * 33 = 28.05, not 28."""
    site = O.Alma(34, 0.85, 6.0)
    assert site.m == 0.85 * 33 and site.m != 28.0 and abs(site.m - 28.05) < 1e-12
    assert site.s == 34 / 6.0
    floored = O.Alma(34, 0.85, 6.0, floor=True)
    assert floored.m == 28.0
    x = np.arange(100, dtype=np.float64)
    ours = np.array([v for v in map(site, x)])
    flo = np.array([v for v in map(floored, x)])
    assert np.allclose(x[33:] - ours[33:], LAG, atol=1e-9)
    assert np.allclose(x[33:] - flo[33:], 6.6916552212920, atol=1e-9)        # the floored lag: 0.031 bars more
    o, h, l, c = path_fufd()
    a = O.ribbon(o, h, l, c)["alma"]
    b = O._ribbon_vm(o, h, l, c, floor=True)["alma"]
    assert np.nanmax(np.abs(a - b)) > 0.01


def test_trap_population_stdev():
    """``ta.stdev`` defaults to biased = true: divide by 34. 17 x 1020 and 17 x 1088: mean 1054, every deviation
    +-34, so the population deviation is exactly 34; the sample one would be 34 * sqrt(34 / 33) = 34.511."""
    c = np.tile([1020.0, 1088.0], 17)
    r = O.ribbon(c, c + 1, c - 1, c)
    assert np.all(np.isnan(r["dev"][:33]))
    assert r["dev"][33] == 34.0
    assert r["dev"][33] == float(np.std(c, ddof=0)) and abs(r["dev"][33] - float(np.std(c, ddof=1))) > 0.5
    sample = O._ribbon_vm(c, c + 1, c - 1, c, biased=False)["dev"][33]
    assert sample == pytest.approx(34 * math.sqrt(34 / 33), rel=1e-14)
    # the reference's SUM() zeroes deviations of at most 1e-10: 34 closes of 1500.1 have the pine_sma mean
    # 1500.0999999999988 (34 inexact quotients), so every raw deviation is 1.1e-12, and the deviation is exactly 0
    k = np.full(40, 1500.1)
    mean = 0.0
    for _ in range(34):
        mean = mean + 1500.1 / 34
    assert mean != 1500.1 and 0 < 1500.1 - mean <= 1e-10
    assert np.all(O.ribbon(k, k + 1, k - 1, k)["dev"][33:] == 0.0)


def test_trap_rma_seed():
    """``ta.atr``: TR of bar 0 = high - low; the RMA starts on bar 13 with the plain mean of TR[0..13], then
    alpha = 1/14. Bar 0 spans 93-107 (TR 14), every later bar 96.5-103.5 around a close of 100 (TR 7)."""
    n = 30
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = np.full(n, 103.5)
    l = np.full(n, 96.5)
    h[0], l[0] = 107.0, 93.0
    a = O.ribbon(o, h, l, c)["atr"]
    assert np.all(np.isnan(a[:13]))
    assert a[13] == 7.5                                       # (14 + 13 x 7) / 14 = 105 / 14 = 7.5, exact
    assert a[14] == (1 / 14) * 7.0 + (1 - 1 / 14) * 7.5      # alpha * TR + (1 - alpha) * ATR[1] = 7.4642857...
    assert a[14] == pytest.approx(7.4642857142857, rel=1e-13)
    # wrong readings give other numbers: an RMA started from its first value (14), a first TR of na, an EMA
    first = 14.0
    for _ in range(13):
        first = (1 / 14) * 7.0 + (1 - 1 / 14) * first
    assert first == pytest.approx(7 + 7 * (13 / 14) ** 13, rel=1e-12) and abs(first - a[13]) > 2
    tr_na_seed = 7.0                                          # mean of TR[1..14] on bar 14
    assert abs(tr_na_seed - a[14]) > 0.4
    site = O.Atr(14)
    trs = []
    for t in range(n):
        site(h[t], l[t], c[t])
        trs.append(site.tr)
    assert trs[0] == 14.0 and all(v == 7.0 for v in trs[1:])
    # gaps: after a close of 100, a bar 109-112 has TR max(3, |112 - 100|, |109 - 100|) = 12; after its close of 111,
    # a bar 99-101 has TR max(2, |101 - 111|, |99 - 111|) = 12
    site = O.Atr(14)
    got = []
    for hh, ll, cc in ((103.5, 96.5, 100.0), (112.0, 109.0, 111.0), (101.0, 99.0, 100.0)):
        site(hh, ll, cc)
        got.append(site.tr)
    assert got == [7.0, 12.0, 12.0]


def test_trap_no_reset_after_stop():
    """A stop ends the position, not the trend: the trend stays +1, the bull setups of a second rally are not flips,
    and the next position is the bear flip's short."""
    o, h, l, c = from_close(np.concatenate([
        np.full(60, 100.0), 100 + np.arange(1, 41.0), np.full(30, 140.0), 140 + np.arange(1, 21.0),
        np.full(30, 160.0), 160 - np.arange(1, 41.0)]))
    l[115] = 99.0                                            # a wick in the flat at 140, through the long's stop
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1), (180, -1)]
    assert np.all(r["trend"][60:180] == 1)                    # through the stop bar and the second rally
    rally = np.flatnonzero(r["bull_setup"][116:180]) + 116
    assert rally.size >= 10 and np.all(rally >= 130) and np.all(r["flip"][rally] == 0)
    pos = O.script_positions(o, h, l, c, stop="intended")
    assert [(p["dir"], p["entry_bar"], p["end_bar"], p["end"]) for p in pos] == [(1, 60, 115, "stop"),
                                                                                 (-1, 180, None, None)]
    # the long: entry 101, risk 101 - 99.75 = 1.25, stop 99.75; the lows after the entry stay >= 100.75 until 115
    assert (pos[0]["entry"], pos[0]["risk"], pos[0]["stop"]) == (101.0, 1.25, 99.75)
    assert np.all(l[61:115] >= 100.75)


def test_trap_entry_at_close_not_next_open():
    """The risk is measured from the flip bar's CLOSE (entryPrice := close, L310), not from the next bar's open (where
    the harness fills). Flat 100 (low 99.75) for 60 bars, the bull flip bar closes at 101, the next bar gaps to 105."""
    o, h, l, c = from_close(np.r_[np.full(60, 100.0), [101.0], np.full(20, 106.0)])
    o[61] = 105.0                                            # the gap: the fill would be about 105
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1)]
    a60 = r["atr"][60]
    assert 0.57 < a60 < 0.58                                 # clamp [0.43, 1.71]
    assert r["risk_long"][60] == 1.25                         # 101 - min(low[48..59]) = 101 - 99.75
    from_open = min(max(o[61] - 99.75, 0.75 * a60), 3.0 * a60)
    assert from_open == 3.0 * a60 and from_open != 1.25      # 105 - 99.75 = 5.25 would hit the 3-ATR cap
    # bar 61 is not read at bar 60: remove it, or change it, and bar 60 is the same
    cut = O.ribbon(o[:61], h[:61], l[:61], c[:61])
    o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
    o2[61], h2[61], l2[61], c2[61] = 90.0, 101.0, 89.0, 95.0
    other = O.ribbon(o2, h2, l2, c2)
    for k in O.KEYS:
        assert same(cut[k], r[k][:61]) and same(other[k][:61], r[k][:61]), k
    assert O.script_positions(o, h, l, c, stop="intended")[0]["entry"] == 101.0


def test_trap_stop_from_fill_not_absolute_level():
    """The contract's risk is a DISTANCE (riskDist); the script draws its stop at the absolute level close - dir *
    riskDist (L330). PREREG 6.1 sets the stop riskDist from the fill, so 1R stays riskDist whatever the fill."""
    o, h, l, c = path_three_bull_flips()
    r = O.ribbon(o, h, l, c)
    pos = O.script_positions(o, h, l, c, stop="intended")
    assert [(p["dir"], p["entry_bar"]) for p in pos] == [(1, 60), (-1, 160), (1, 270), (-1, 370), (1, 470)]
    for p in pos:
        t = p["entry_bar"]
        risk = r["risk_long"][t] if p["dir"] == 1 else r["risk_short"][t]
        assert p["risk"] == risk and p["entry"] == c[t]
        assert p["stop"] == c[t] - p["dir"] * risk
    # the long of bar 60: close 111, risk 1.25 -> the script's level 109.75 (the flat's low). A fill at 111.40 (the
    # next M1 open at the ask): the plan's stop is 111.40 - 1.25 = 110.15; the script's level would put 1.65 = 1.32R
    # between the fill and the stop
    assert pos[0]["stop"] == 109.75
    fill = 111.40
    assert fill - pos[0]["risk"] == pytest.approx(110.15, abs=1e-12)
    assert (fill - pos[0]["stop"]) / pos[0]["risk"] == pytest.approx(1.32, abs=1e-12)
    # the short of bar 160: close 149, risk 1.25 -> the level 150.25; its targets are 147.75, 146.5, 145.25, 144
    assert pos[1]["stop"] == 150.25 and pos[1]["targets"] == (147.75, 146.5, 145.25, 144.0)


def test_trap_entry_bar_touches_not_counted():
    """The script ticks a target on the entry bar (the Active Position block runs on it, L495, and only the stop test
    has ``bar_index > entryBar``), i.e. on the part of the bar BEFORE the entry close. Such a touch must not count."""
    o, h, l, c = from_close(np.r_[np.full(60, 100.0), [101.0], np.full(40, 101.0)])
    h[60] = 103.0                                            # the flip bar's upper wick, before its close of 101
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1)]
    pos = O.script_positions(o, h, l, c, stop="intended")
    assert len(pos) == 1
    p = pos[0]
    assert (p["entry"], p["risk"], p["stop"]) == (101.0, 1.25, 99.75)          # 101 - 99.75 = 1.25 (inside)
    assert p["targets"] == (102.25, 103.5, 104.75, 106.0)                       # 101 + k x 1.25
    assert p["hit_bar"] == [60, None, None, None]            # T1 ticked on the entry bar itself (103 >= 102.25) ...
    assert float(np.max(h[61:])) == 101.25                    # ... and never touched after the entry
    honest = [next((t for t in range(61, len(c)) if h[t] >= T), None) for T in p["targets"]]
    assert honest == [None, None, None, None]
    # with the literal stop (0.75 ATR = 0.522 on the first flip) three targets tick on the entry bar
    lit = O.script_positions(o, h, l, c, stop="literal")[0]
    assert lit["risk"] == r["atr"][60] * 0.75 and lit["hit_bar"] == [60, 60, 60, None]
    # the entry bar's own low is not tested against the stop (bar_index > entryBar): a flip bar whose wick reaches
    # below its own stop opens a position that is not stopped on that bar
    o2, h2, l2, c2 = from_close(np.r_[np.full(60, 100.0), [101.0], np.full(40, 101.0)])
    l2[60] = 99.3                                            # below the stop 99.75 (the raw risk is still 1.25)
    assert flips(O.ribbon(o2, h2, l2, c2)) == [(60, 1)]
    (p2,) = O.script_positions(o2, h2, l2, c2, stop="intended")
    assert p2["stop"] == 99.75 and l2[60] < p2["stop"] and p2["end"] is None


def test_trap_old_position_on_flip_bar():
    """On a flip bar the freeze (L215-277) ends the old position BEFORE the stop test (L495), which then sees the
    new position: the flip bar's low is never checked against the old long's stop. A harness checking stops on M1
    bars exits at the stop inside that bar instead."""
    o, h, l, c = from_close(np.r_[np.full(60, 100.0), 100 + np.arange(1, 41.0), np.full(60, 140.0)])
    o = np.r_[o, 140.0, np.full(20, 130.0)]
    h = np.r_[h, 140.0, np.full(20, 130.25)]
    l = np.r_[l, 99.0, np.full(20, 129.75)]                 # bar 160 falls from 140 to 99 and closes at 130
    c = np.r_[c, 130.0, np.full(20, 130.0)]
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1), (160, -1)]
    for stop in ("intended", "literal"):
        old, new = O.script_positions(o, h, l, c, stop=stop)
        assert old["dir"] == 1 and old["end_bar"] == 160 and old["end"] == "flip", stop
        assert l[160] <= old["stop"], stop                   # 99 <= 99.75 (intended) / 100.57 (literal)
        assert np.all(l[61:160] > old["stop"]), stop         # nothing before the flip bar reached it
        assert new["dir"] == -1 and new["entry_bar"] == 160 and new["entry"] == 130.0, stop
    assert O.script_positions(o, h, l, c, stop="intended")[0]["stop"] == 99.75


# ───────────────────────────── 2. the spec's test cases ─────────────────────────────

def test_alma_ramp_constant_impulse():
    x = np.arange(200, dtype=np.float64) * 3.0 + 1000.0                 # x_t = 1000 + 3t: alma = x_t - 3 x 6.66
    a = O.ribbon(x, x + 1, x - 1, x)["alma"]
    assert np.all(np.isnan(a[:33]))
    assert np.allclose(x[33:] - a[33:], 3 * LAG, rtol=0, atol=1e-8)
    for v in (128.0, 1.0, 4096.0):                                       # a power of 2: exactly the constant
        k = np.full(60, v)
        assert np.all(O.ribbon(k, k, k, k)["alma"][33:] == v)
    for v in (1234.56, 0.1, 30000.0, 64000.123):                         # otherwise within rounding
        k = np.full(60, v)
        assert np.allclose(O.ribbon(k, k, k, k)["alma"][33:], v, rtol=1e-15, atol=0)
    w = alma_weights_np()
    for j in (0, 1, 5, 20, 33):
        imp = np.zeros(80)
        imp[40] = 1.0
        assert O.ribbon(imp, imp, imp, imp)["alma"][40 + j] == pytest.approx(w[33 - j] / w.sum(), rel=1e-12)


def test_stdev_equals_numpy_population_on_every_window():
    for seed, p0, vol in ((4, 1500.0, 2.0), (5, 30000.0, 100.0)):
        o, h, l, c = walk(400, seed, p0, vol)
        dev = O.ribbon(o, h, l, c)["dev"]
        want = sliding_window_view(c, 34).std(axis=1, ddof=0)
        assert np.all(np.isnan(dev[:33]))
        assert np.allclose(dev[33:], want, rtol=1e-9, atol=0)
        assert not np.allclose(dev[33:], sliding_window_view(c, 34).std(axis=1, ddof=1), rtol=1e-3, atol=0)


def test_strict_slope_threshold():
    """slope > slopeMin is strict (L97-98): with slope_min set to the bar's slope exactly there is no setup; one ulp
    lower, there is."""
    o, h, l, c = path_fufd()
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1), (160, -1)]
    s = float(r["slope"][60])
    assert c[60] > r["alma"][60] + r["dev"][60] * 0.65                  # the band holds at bar 60
    assert not O.ribbon(o, h, l, c, slope_min=s)["bull_setup"][60]
    assert O.ribbon(o, h, l, c, slope_min=float(np.nextafter(s, -np.inf)))["bull_setup"][60]
    sb = float(r["slope"][160])                                          # slope < -slopeMin, strict
    assert sb < 0 and c[160] < r["alma"][160] - r["dev"][160] * 0.65
    assert not O.ribbon(o, h, l, c, slope_min=-sb)["bear_setup"][160]
    assert O.ribbon(o, h, l, c, slope_min=float(np.nextafter(-sb, -np.inf)))["bear_setup"][160]


def test_strict_band_threshold():
    """close > alma + dev * devMult is strict. (a) 34 equal closes of 128 after a step from 64: alma = 128 exactly
    (a power of 2), dev = 0 (every deviation is within 1e-10 of 0), so upper = close; the slope is positive (the step
    still has a little weight in alma[3]) and slope_min = 0: no setup. One bar later, at 129, there is one.
    (b) dev_mult chosen so that alma + dev * dev_mult equals the flip bar's close bit for bit: no setup; one ulp less:
    a setup."""
    o, h, l, c = from_close(np.r_[np.full(40, 64.0), np.full(34, 128.0), [129.0]], w=0.0)
    r = O.ribbon(o, h, l, c, slope_min=0.0)
    t = 73
    assert r["alma"][t] == 128.0 and r["dev"][t] == 0.0 and c[t] == 128.0
    assert 0.0 < r["slope"][t] < 0.08 and r["alma"][t] + r["dev"][t] * 0.65 == c[t]
    assert not r["bull_setup"][t] and r["bull_setup"][t + 1]
    o, h, l, c = from_close(np.r_[np.full(40, 128.0), np.full(34, 64.0), [63.0]], w=0.0)    # the bear mirror
    r = O.ribbon(o, h, l, c, slope_min=0.0)
    assert r["alma"][t] == 64.0 and r["dev"][t] == 0.0 and -0.08 < r["slope"][t] < 0.0
    assert r["alma"][t] - r["dev"][t] * 0.65 == c[t] and not r["bear_setup"][t] and r["bear_setup"][t + 1]
    o, h, l, c = path_fufd()
    r = O.ribbon(o, h, l, c)
    a, d = float(r["alma"][60]), float(r["dev"][60])
    m = (c[60] - a) / d
    hits = []
    for k in range(-200, 201):                                           # search some ulps around the quotient
        x = m
        for _ in range(abs(k)):
            x = float(np.nextafter(x, np.inf if k > 0 else -np.inf))
        if a + d * x == c[60]:
            hits.append(x)
    assert hits, "no dev_mult puts the band exactly on the close"
    for x in (min(hits), max(hits)):
        assert not O.ribbon(o, h, l, c, dev_mult=x)["bull_setup"][60]
    below = min(hits)
    while a + d * below >= c[60]:
        below = float(np.nextafter(below, -np.inf))
    assert O.ribbon(o, h, l, c, dev_mult=below)["bull_setup"][60]
    a, d = float(r["alma"][160]), float(r["dev"][160])                  # the bear flip bar: alma - dev * m = close
    m = (a - c[160]) / d
    hits = []
    for k in range(-200, 201):
        x = m
        for _ in range(abs(k)):
            x = float(np.nextafter(x, np.inf if k > 0 else -np.inf))
        if a - d * x == c[160]:
            hits.append(x)
    assert hits, "no dev_mult puts the lower band exactly on the close"
    for x in (min(hits), max(hits)):
        assert not O.ribbon(o, h, l, c, dev_mult=x)["bear_setup"][160]
    below = min(hits)
    while a - d * below <= c[160]:
        below = float(np.nextafter(below, -np.inf))
    assert O.ribbon(o, h, l, c, dev_mult=below)["bear_setup"][160]


def test_flat_up_flat_down_one_flip_each():
    """Flat -> up-ramp -> flat -> down-ramp: exactly one bull flip (the first up bar: slope 0.10 > 0.08 and the close
    far above a band of zero width), the trend persists through the flat, exactly one bear flip."""
    o, h, l, c = path_fufd()
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [(60, 1), (160, -1)]
    assert np.all(r["trend"][:60] == 0) and np.all(r["trend"][60:160] == 1) and np.all(r["trend"][160:] == -1)
    assert not np.any(r["bull_setup"][100:]) and not np.any(r["bear_setup"][:160])
    assert r["bull_setup"][60:100].sum() == 40 and r["bear_setup"][160:200].sum() == 40


def test_no_flip_when_only_slope_or_only_band():
    # only the band: a slow ramp (0.1 a bar) with wide wicks (+-2): the close is above the band on every bar from 36,
    # but the slope peaks at 0.073 < 0.08
    o, h, l, c = from_close(100 + 0.1 * np.arange(300.0), w=2.0)
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [] and np.all(r["trend"] == 0)
    assert np.all(c[36:] > (r["alma"] + r["dev"] * 0.65)[36:]) and 0.07 < np.max(r["slope"][36:]) < 0.08
    assert flips(O.ribbon(o, h, l, c, slope_min=0.07)) != []            # the same bars flip once the slope passes
    # only the slope: a decelerating rise 100 + 50 (1 - exp(-t/40)) with hairline wicks: the slope is far above 0.08
    # on every bar from 36, but the close stays under the band (the window's older, steeper part widens the stdev)
    t = np.arange(400.0)
    o, h, l, c = from_close(100 + 50 * (1 - np.exp(-t / 40)), w=1e-4)
    r = O.ribbon(o, h, l, c)
    assert flips(r) == [] and np.all(r["trend"] == 0)
    assert np.all(r["slope"][36:] > 0.08) and np.all(c[36:] <= (r["alma"] + r["dev"] * 0.65)[36:])
    assert flips(O.ribbon(o, h, l, c, dev_mult=0.1)) != []               # a narrower band lets it flip


def test_risk_clamp_branches():
    """riskDist = min(max(nz(raw, 0.75 ATR), 0.75 ATR), 3 ATR) with an ATR of exactly 7 (every true range is 7; 7/14
    and the RMA step are exact): floor 5.25, cap 21."""
    # an up-ramp of 7 a bar with high = close, low = open: raw long = c_t - low_{t-12} = 13 x 7 = 91 > 21 -> 21;
    # raw short = high_{t-1} - c_t = -7 < 0 -> 5.25
    c = 100.0 + 7.0 * np.arange(40.0)
    o = c - 7.0
    r = O.ribbon(o, c, o, c)
    assert np.all(r["atr"][13:] == 7.0)
    assert np.all(r["risk_long"][13:] == 21.0) and np.all(r["risk_short"][13:] == 5.25)
    assert np.all(np.isnan(r["risk_long"][:13])) and np.all(np.isnan(r["risk_short"][:13]))   # the ATR is na
    # a flat close of 100 inside 96.5-103.5: raw = 3.5 on both sides, 0 < raw < 0.75 ATR -> 5.25
    n = 40
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = np.full(n, 103.5)
    l = np.full(n, 96.5)
    r = O.ribbon(o, h, l, c)
    assert np.all(r["atr"][13:] == 7.0)
    assert np.all(r["risk_long"][13:] == 5.25) and np.all(r["risk_short"][13:] == 5.25)
    # then a bar from 100 to 107 (TR 7): raw long = 107 - 96.5 = 10.5, inside -> 10.5; raw short = 103.5 - 107 < 0
    o2, h2, l2, c2 = (np.r_[x, v] for x, v in ((o, 100.0), (h, 107.0), (l, 100.0), (c, 107.0)))
    r2 = O.ribbon(o2, h2, l2, c2)
    assert r2["atr"][n] == 7.0 and r2["risk_long"][n] == 10.5 and r2["risk_short"][n] == 5.25
    # a missing raw risk (fewer than stop_lookback bars before) with an ATR: nz -> 0.75 ATR
    r3 = O.ribbon(o, h, l, c, stop_lookback=20)
    assert np.all(np.isnan(r3["risk_long"][:13]))
    assert np.all(r3["risk_long"][13:20] == 5.25) and np.all(r3["risk_short"][13:20] == 5.25)
    assert np.all(r3["risk_long"][20:] == 5.25)                          # raw = 3.5 again from bar 20


def test_trend_closed_form():
    for seed, p0, vol in ((6, 1500.0, 2.0), (7, 30000.0, 100.0), (8, 50.0, 0.3)):
        r = O.ribbon(*walk(1500, seed, p0, vol))
        trend, flip = trend_closed_form(r["bull_setup"], r["bear_setup"])
        assert same(trend, r["trend"]) and same(flip, r["flip"])
        assert (r["flip"] != 0).sum() > 20


def test_literal_stop_closed_form_and_window_roll():
    """Over 3000 bars with dozens of flips per side, the literal stop equals the closed form (the previous up to 12
    same-side flip bars); from the 14th bull flip on the window has rolled (flip 1 no longer counts)."""
    for seed, p0, vol in ((9, 1500.0, 2.0), (10, 30000.0, 100.0)):
        o, h, l, c = walk(3000, seed, p0, vol)
        r = O.ribbon(o, h, l, c)
        want_l, want_s = literal_closed_form(r, l, h, c)
        assert same(r["risk_long_lit"], want_l) and same(r["risk_short_lit"], want_s)
        bulls = np.flatnonzero(r["flip"] == 1)
        assert bulls.size >= 20
        alt = O._ribbon_vm(o, h, l, c, lit_full=True)
        alt_l, alt_s = literal_closed_form(r, l, h, c, full=True)
        assert same(alt["risk_long_lit"], alt_l) and same(alt["risk_short_lit"], alt_s)
        first12 = bulls[:12]
        assert np.all(alt["risk_long_lit"][first12] == r["atr"][first12] * 0.75)


def test_extreme_call_site():
    """``ta.lowest`` at one call site, executed at chosen bars: its window holds its own executions' values."""
    site = O.Extreme(3, "min")
    got = [(site(v, b), site.prev()) for v, b in ((5.0, 0), (4.0, 1), (6.0, 2), (7.0, 9), (8.0, 20), (9.0, 21))]
    # bar 0 and 1 are below bar_index 2 = length - 1: na; from bar 2 the min of the last <= 3 values seen
    assert [g[0] for g in got][2:] == [4.0, 4.0, 6.0, 7.0]
    assert all(math.isnan(g[0]) for g in got[:2])
    assert math.isnan(got[0][1]) and math.isnan(got[1][1]) and math.isnan(got[2][1])     # [1] = previous result
    assert [g[1] for g in got][3:] == [4.0, 4.0, 6.0]
    first = O.Extreme(12, "max")
    assert first(3.0, 40) == 3.0 and math.isnan(first.prev())           # one value, at bar 40: a value already
    full = O.Extreme(3, "max", full=True)
    assert all(math.isnan(full(v, b)) for v, b in ((1.0, 50), (2.0, 60)))
    assert full(0.5, 70) == 2.0


def test_numpy_cross_check():
    for seed, p0, vol in ((11, 1500.0, 2.0), (12, 30000.0, 100.0), (13, 50.0, 0.3)):
        o, h, l, c = walk(1200, seed, p0, vol)
        check_cross(O.ribbon(o, h, l, c), o, h, l, c)


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

@pytest.mark.parametrize("seed, p0, vol", [(14, 1500.0, 2.0), (15, 30000.0, 100.0)])
def test_truncation_invariance(seed, p0, vol):
    o, h, l, c = walk(700, seed, p0, vol)
    full = O.ribbon(o, h, l, c)
    ft = [f for f, _ in flips(full)]
    cuts = sorted({0, 1, 12, 13, 33, 35, 36, 37, 100, 350, 699} | set(ft[:3]) | {f - 1 for f in ft[:3]})
    for T in cuts:
        part = O.ribbon(o[:T + 1], h[:T + 1], l[:T + 1], c[:T + 1])
        for k in O.KEYS:
            assert same(part[k], full[k][:T + 1]), (T, k)
    pos = O.script_positions(o, h, l, c)
    T = 400
    early = O.script_positions(o[:T + 1], h[:T + 1], l[:T + 1], c[:T + 1])
    done = [p for p in pos if p["end_bar"] is not None and p["end_bar"] <= T]
    assert [p for p in early if p["end_bar"] is not None] == done


# ───────────────────────────── 4. the real bars (to 2024-06-30, the guard closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Study 1's 1H / 4H / 1D bars of one symbol from its data start to 2024-07-01 00:00 UTC (exclusive), with study
    1's hold-out guard pointed at an empty folder; only the arrays the ribbon reads are kept."""
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
    rows = real(symbol)
    dev_a, dev_z = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")
    T = TM.s_of("2021-06-15 12:00")
    for tf, b in rows.items():
        assert int(b.tc[-1]) <= TM.CUT_S and bool(b.complete.all()), tf              # nothing from the hold-out
        r = O.ribbon(b.o, b.h, b.l, b.c)
        check_where_values_exist(r, b.c)
        dev = (b.t >= dev_a) & (b.tc <= dev_z)                                      # bars in 2019-2022
        assert (r["flip"][dev] == 1).sum() >= 5 and (r["flip"][dev] == -1).sum() >= 5, tf
        assert np.all(r["trend"][b.tc > dev_a] != 0), tf                              # warmed up before 2019
        check_cross(r, b.o, b.h, b.l, b.c)
        want_l, want_s = literal_closed_form(r, b.l, b.h, b.c)
        assert same(r["risk_long_lit"], want_l) and same(r["risk_short_lit"], want_s), tf
        trend, flip = trend_closed_form(r["bull_setup"], r["bear_setup"])
        assert same(trend, r["trend"]) and same(flip, r["flip"]), tf
        i = int(np.searchsorted(b.tc, T, side="right")) - 1                          # a cut at one T
        part = O.ribbon(b.o[:i + 1], b.h[:i + 1], b.l[:i + 1], b.c[:i + 1])
        for k in O.KEYS:
            assert same(part[k], r[k][:i + 1]), (tf, k)
