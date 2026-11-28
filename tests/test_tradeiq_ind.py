"""
The TradeIQ study's indicators (``backtesting/research/tradeiq_ind.py``).

1. Hand-worked cases for every helper and indicator, from both independent ports (the arithmetic is in the comments).
2. TradingView's own output for the helpers (values read on TradingView by the authors of the PineTS project and
   recorded in its tests), including the evidence on the ``ta.ema`` seed and the ``ta.hma`` half length.
3. Invariants: ranges, the QQE bands around the RSI, the colour logic, the TSI against the price drift, constant and
   zero volume, the first bars, no look-ahead, inputs left alone, na refused inside a series.
4. The oracle ``tests/tradeiq_oracle.py`` (port B and its Pine VM): the same floats, bit for bit, on synthetic bars.
5. Real bars (skipped when the tick store is absent): both symbols, 1H / 4H / 1D, from the data start to the hold-out
   start with the guard closed: bit for bit equal to the oracle (BTC also on Binance volume), external.py's RSI, ATR
   and SMA, and a few values recorded when the ports were reconciled.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq_oracle as O  # noqa: E402

nan = math.nan


def same(a, b):
    """Equal floats (bit for bit up to the sign of zero), NaN where the other is NaN."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def close_to(a, b, tol=1e-12):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    if a.shape != b.shape or not np.array_equal(np.isnan(a), np.isnan(b)):
        return False
    ok = ~np.isnan(a)
    return bool(np.all(np.abs(a[ok] - b[ok]) <= tol * np.maximum(1.0, np.abs(b[ok]))))


def first_valid(x):
    f = np.flatnonzero(~np.isnan(np.asarray(x, np.float64)))
    return int(f[0]) if len(f) else None


def walk(n, seed, drift=0.0, start=2000.0, vol=1.0):
    rng = np.random.default_rng(seed)
    return start + np.cumsum(drift + vol * rng.standard_normal(n))


def bars(n, seed, decimals=None):
    """Random high / low / close and a tick volume; ``decimals`` rounds the prices, so some changes are exactly 0."""
    rng = np.random.default_rng(seed)
    c = walk(n, seed)
    h = c + np.abs(rng.standard_normal(n))
    lo = c - np.abs(rng.standard_normal(n))
    if decimals is not None:
        c, h, lo = (np.round(x, decimals) for x in (c, h, lo))
    v = rng.integers(1, 200, n).astype(float)
    return h, lo, c, v


# ───────────────────────────── 1. the helpers, by hand ─────────────────────────────

def test_hist_and_change():
    assert same(I.hist([1.0, 3.0, 2.0], 1), [nan, 1, 3])           # x[1]: na on the first bar
    assert same(I.hist([1.0, 3.0, 2.0], 2), [nan, nan, 1])
    assert same(I.change([1.0, 3.0, 2.0]), [nan, 2, -1])           # 3 - 1, 2 - 3
    assert same(I.change([nan, 3.0, 2.0]), [nan, nan, -1])         # na in, na out
    with pytest.raises(ValueError):
        I.hist([1.0, 2.0], -1)


def test_sma():
    # pine_sma adds x[i] / 3 from this bar back: bar 2 = 3/3 + 2/3 + 1/3 = 2, bar 3 = 3, bar 4 = 4
    assert close_to(I.sma([1, 2, 3, 4, 5], 3), [nan, nan, 2, 3, 4])
    s = 0.0 + 3.0 / 3                                               # the exact float of that order
    s = s + 2.0 / 3
    s = s + 1.0 / 3
    assert I.sma([1.0, 2, 3], 3)[2] == s
    # leading na: the mean starts once `length` values exist
    assert close_to(I.sma([nan, 1, 2, 3], 2), [nan, nan, 1.5, 2.5])
    assert close_to(I.sma([nan, nan, 1.0, 2, 3, 4], 2), [nan, nan, nan, 1.5, 2.5, 3.5])
    assert same(I.sma([1.0, 2.0], 3), [nan, nan])                  # fewer bars than the length: all na


def test_math_sum():
    assert same(I.math_sum([1, 2, 3, 4], 3), [nan, nan, 6, 9])     # 1+2+3, 2+3+4
    assert same(I.math_sum(np.ones(12), 10)[8:], [nan, 10, 10, 10])
    assert same(I.math_sum([nan, 2.0, 3.0, 4.0], 2), [nan, nan, 5, 7])


def test_wma():
    # weights (3 - i) * 3 = 9, 6, 3 (norm 18): bar 2 = (3*9 + 2*6 + 1*3) / 18 = 42/18; bar 3 = (4*9 + 3*6 + 2*3) / 18
    assert close_to(I.wma([1, 2, 3, 4], 3), [nan, nan, 42 / 18, 60 / 18])
    # leading na: weights 4, 2 on bars 2, 1: (2*4 + 1*2) / 6
    assert close_to(I.wma([nan, 1.0, 2.0], 2), [nan, nan, 10 / 6])


def test_hma_floor_half_and_lengths():
    # On a straight line x_t = t + 1 a WMA(n) lags by (n - 1)/3.
    x = np.arange(1.0, 31.0)
    # HMA(5): half floor(5/2) = 2, sqrt floor(2.236) = 2: wma2 = x - 1/3, wma5 = x - 4/3, raw = 2(x - 1/3) - (x - 4/3)
    # = x + 2/3, hma = wma2(raw) = x + 1/3; first on bar 5 (raw from bar 4)
    h5 = I.hma(x, 5)
    assert first_valid(h5) == 5
    assert np.allclose(h5[5:], x[5:] + 1 / 3, rtol=0, atol=1e-12)
    # the reading DEVIATIONS 12 rejects, a rounded half (3): raw = 2(x - 2/3) - (x - 4/3) = x, hma = x - 1/3
    rounded = I.wma(2.0 * I.wma(x, 3) - I.wma(x, 5), 2)
    assert np.allclose(rounded[5:], x[5:] - 1 / 3, rtol=0, atol=1e-12)
    assert same(I.hma(x, 5.0), h5)                                  # range_score's v = 10/2 is the float 5.0
    # HMA(4): half 2, sqrt 2: raw = 2(x - 1/3) - (x - 1) = x + 1/3, hma = x; first on bar 4
    h4 = I.hma(x, 4)
    assert first_valid(h4) == 4 and np.allclose(h4[4:], x[4:], rtol=0, atol=1e-12)
    # HMA(20): wma10 = x - 3, wma20 = x - 19/3, raw = x + 1/3, sqrt -> 4: hma = raw - 1 = x - 2/3; first on bar 22
    h20 = I.hma(x, 20)
    assert first_valid(h20) == 22
    assert np.allclose(h20[22:], x[22:] - 2 / 3, rtol=0, atol=1e-12)
    for bad in (4.5, 1, 0):
        with pytest.raises(ValueError):
            I.hma(x, bad)


def test_ema_both_seeds():
    # alpha = 2 / (3 + 1) = 0.5: first value 2; 0.5*4 + 0.5*2 = 3; 0.5*6 + 0.5*3 = 4.5; 0.5*8 + 0.5*4.5 = 6.25
    assert same(I.ema([2, 4, 6, 8], 3), [2, 3, 4.5, 6.25])
    assert same(I.ema([10.0, 11.0, 12.0], 3), [10, 10.5, 11.25])
    # alpha = 2/(4+1) = 0.4: 10; 0.4*20 + 0.6*10 = 14; 0.4*20 + 0.6*14 = 16.4
    assert close_to(I.ema([10.0, 20.0, 20.0], 4), [10, 14, 16.4])
    assert same(I.ema([nan, 2, 4], 3), [nan, 2, 3])                # leading na: the first value starts it
    # the SMA seed (DEVIATIONS 11, only to measure it): na, na, 6/3 + 4/3 + 2/3 = 4, then 0.5*8 + 0.5*4 = 6
    assert close_to(I.ema([2, 4, 6, 8], 3, seed="sma"), [nan, nan, 4, 6])
    assert close_to(I.ema([10.0, 11.0, 12.0, 14.0], 3, seed="sma"), [nan, nan, 11, 12.5])
    with pytest.raises(ValueError):
        I.ema([1.0, 2.0], 2, seed="zero")


def test_rma():
    # alpha = 1/3; seed on bar 2 = 3/3 + 2/3 + 1/3 = 2; bar 3 = 4/3 + (2/3)*2 = 8/3; bar 4 = 5/3 + (2/3)(8/3) = 31/9
    assert close_to(I.rma([1, 2, 3, 4, 5], 3), [nan, nan, 2, 8 / 3, 31 / 9])
    assert close_to(I.rma([nan, 1, 2, 3, 4], 3), [nan, nan, nan, 2, 8 / 3])
    # seeded with the SMA of the first 3 values (bars 1..3: (4 + 0 + 2)/3 = 2), then 5/3 + (2/3)*2
    assert close_to(I.rma([nan, 4.0, 0.0, 2.0, 5.0], 3), [nan, nan, nan, 2, 5 / 3 + (2 / 3) * 2])


def test_stdev():
    # mean 5, squared deviations 9,1,1,1,0,0,4,16 = 32: biased sqrt(32/8) = 2, unbiased sqrt(32/7)
    x = [2, 4, 4, 4, 5, 5, 7, 9]
    assert close_to(I.stdev(x, 8), [nan] * 7 + [2.0])
    assert close_to(I.stdev(x, 8, biased=False), [nan] * 7 + [math.sqrt(32 / 7)])
    # a constant window: pine_sma's mean of fifty 0.1 is 0.10000000000000007, so every deviation is -6.9e-17; deviations
    # of at most 1e-10 count as 0 (the reference's isZero), so the result is exactly 0
    assert I.stdev([0.1] * 50, 50)[-1] == 0.0
    assert I.stdev([49.9] * 5, 5)[-1] == 0.0
    assert same(I.stdev(np.full(6, 0.1), 5), [nan, nan, nan, nan, 0.0, 0.0])
    with pytest.raises(ValueError):
        I.stdev(x, 1, biased=False)


def test_rsi_by_hand():
    # x = 1,2,3,2,3, length 2: gains na,1,1,0,1; losses na,0,0,1,0 (alpha 1/2)
    # rma(gains): bar 2 = 1, bar 3 = 0.5, bar 4 = 0.75; rma(losses): bar 2 = 0, bar 3 = 0.5, bar 4 = 0.25
    # RSI: bar 2 loss average 0 -> 100; bar 3 rs = 1 -> 50; bar 4 rs = 3 -> 75
    assert close_to(I.rsi([1, 2, 3, 2, 3], 2), [nan, nan, 100, 50, 75])
    # close 10 11 10 12: rma(gains) bar 2 = (1+0)/2 = 0.5, bar 3 = 0.5*2 + 0.25 = 1.25; rma(losses) 0.5, 0.25
    # -> bar 2: 50; bar 3: rs = 5 -> 100 - 100/6
    assert close_to(I.rsi([10.0, 11, 10, 12], 2), [nan, nan, 50, 100 - 100 / 6])
    assert same(I.rsi([1.0, 2, 3, 4], 2), [nan, nan, 100, 100])    # only gains: loss average 0 -> 100
    assert same(I.rsi([5, 4, 3, 2, 1], 2), [nan, nan, 0, 0, 0])     # only losses: gain average 0 -> 0
    assert same(I.rsi([5, 5, 5, 5], 2), [nan, nan, 100, 100])       # no move: down == 0 is tested first
    assert first_valid(I.plain_rsi(walk(300, 1))) == 14           # 14 changes: bars 1..14


def test_tsi_by_hand():
    # x = 10,11,13,12: pc = na,1,2,-1; long 3 (alpha 0.5), short 2 (alpha 2/3), first-value seeds
    # ema(pc,3) = 1, 1.5, 0.25; ema(.,2) = 1, (2/3)1.5 + (1/3)1 = 4/3, (2/3)0.25 + (1/3)(4/3) = 11/18
    # ema(|pc|,3) = 1, 1.5, 1.25; ema(.,2) = 1, 4/3, (2/3)1.25 + (1/3)(4/3) = 23/18; tsi = 1, 1, 11/23
    assert close_to(I.tsi([10, 11, 13, 12], 2, 3), [nan, 1, 1, 11 / 23])
    assert np.isnan(I.tsi([10, 10, 11], 2, 3)[1])                  # 0 / 0 before any move: na
    # long 2, short 1 (an EMA of length 1 is the identity), close 10 11 10: ema2(pc) = 1, (2/3)(-1) + (1/3) = -1/3;
    # ema2(|pc|) = 1, 1 -> tsi = 100, -33.33; signal ema2: 100, (2/3)(-33.33) + (1/3)(100)
    t = I.bjorgum_tsi([10.0, 11.0, 10.0], short=1, long=2, signal=2)
    assert close_to(t.tsi, [nan, 100, -100 / 3])
    assert close_to(t.signal, [nan, 100, (2 / 3) * (-100 / 3) + (1 / 3) * 100])
    t0 = I.bjorgum_tsi([10.0, 10.0, 11.0])
    assert np.isnan(t0.tsi[:2]).all() and t0.tsi[2] == 100.0


def test_cross_family_ties_and_levels():
    a = [1, 2, 3, 2, 1, 1, 3]
    # bar 2: 3 > 2 after 2 <= 2 -> crossover and cross
    # bar 3: 2 against 2 after 3 > 2 -> (a > b) changed: a cross, but neither crossover nor crossunder (2 < 2 is false)
    # bar 4: 1 < 2 after 2 >= 2 -> crossunder, but (a > b) is false on both bars: no cross
    # bar 6: 3 > 2 after 1 <= 2 -> crossover and cross
    assert I.crossover(a, 2).tolist() == [False, False, True, False, False, False, True]
    assert I.crossunder(a, 2).tolist() == [False, False, False, False, True, False, False]
    assert I.cross(a, 2).tolist() == [False, False, True, True, False, False, True]
    # the other reading of ta.cross (crossover or crossunder) differs exactly at those ties (DEVIATIONS 14)
    either = I.crossover(a, 2) | I.crossunder(a, 2)
    assert either.tolist() == [False, False, True, False, True, False, True]
    assert I.crossover(2, [3, 1]).tolist() == [False, True]       # a number for the first argument
    # leading na: the first bar with both values has no previous one -> false
    assert I.crossover([nan, 1.0, 3.0], [2.0, 2.0, 2.0]).tolist() == [False, False, True]
    assert I.cross([nan, 3.0, 1.0], 2).tolist() == [False, False, True]
    assert I.cross([1.0, 3.0], [nan, 2.0]).tolist() == [False, False]
    assert I.cross([nan, nan], [1.0, 2.0]).tolist() == [False, False]
    with pytest.raises(ValueError):
        I.crossover(1, 2)


def test_true_range_and_atr():
    h, lo, c = [10, 12, 11], [8, 9, 9], [9, 11, 10]
    # tr0 = 10 - 8 = 2 (no previous close); tr1 = max(3, |12-9|, |9-9|) = 3; tr2 = max(2, |11-11|, |9-11|) = 2
    assert same(I.true_range(h, lo, c), [2, 3, 2])
    # rma(tr, 2): bar 1 = (3 + 2)/2 = 2.5; bar 2 = 0.5*2 + 0.5*2.5 = 2.25
    assert close_to(I.atr(h, lo, c, 2), [nan, 2.5, 2.25])
    # tr = 2, max(3, 3, 0) = 3, max(4, 0, 4) = 4; atr2: 2.5, 0.5*4 + 0.5*2.5 = 3.25
    assert same(I.true_range([10, 12, 11], [8, 9, 7], [9, 11, 8]), [2, 3, 4])
    assert same(I.atr([10, 12, 11], [8, 9, 7], [9, 11, 8], 2), [nan, 2.5, 3.25])
    hh, ll, cc, _ = bars(100, 3)
    a14 = I.atr14(hh, ll, cc)
    assert first_valid(a14) == 13
    assert a14[13] == pytest.approx(np.mean(I.true_range(hh, ll, cc)[:14]), rel=1e-14)
    with pytest.raises(ValueError):
        I.true_range([1.0, 2.0], [0.5], [1.0, 1.5])


def test_ma200_and_lengths():
    c = walk(500, 4)
    s = I.ma200(c)
    assert first_valid(s) == 199
    assert s[199] == pytest.approx(c[:200].mean(), rel=1e-13) and s[450] == pytest.approx(c[251:451].mean(), rel=1e-13)
    assert close_to(I.ma200(np.arange(1.0, 401.0))[199:202], [100.5, 101.5, 102.5])
    for bad in (0, -1, 2.5, True):
        with pytest.raises(ValueError):
            I.sma(c, bad)


# ───────────────────────────── 1b. the indicators, by hand ─────────────────────────────

def test_laguerre_by_hand():
    # gamma = 0.8. Bar 0 (src 10, every [1] is na -> nz 0):
    #   L0 = 0.2*10 = 2; L1 = -0.8*2 = -1.6; L2 = 1.28; L3 = -1.024
    #   cu = (2 + 1.6) + 0 + (1.28 + 1.024) = 5.904; cd = 1.28 + 1.6 = 2.88; LaRSI = 5.904 / 8.784 (= 41/61 for any price)
    # Bar 1 (src 11): L0 = 2.2 + 1.6 = 3.8; L1 = -3.04 + 2 - 1.28 = -2.32; L2 = 1.856 - 1.6 + 1.024 = 1.28;
    #   L3 = -1.024 + 1.28 - 0.8192 = -0.5632; cu = 6.12 + 0 + 1.8432 = 7.9632; cd = 3.6
    out = I.laguerre_rsi([10, 11])
    assert out[0] == pytest.approx(100 * 5.904 / 8.784, rel=1e-12)
    assert out[1] == pytest.approx(100 * 7.9632 / 11.5632, rel=1e-12)
    assert I.laguerre_rsi([2000.0])[0] == pytest.approx(100 * 41 / 61, rel=1e-12)
    # bar 1 with s0 = s1 = 100: L0 = 36, L1 = -21.6, L2 = 11.52, L3 = -4.608; cu = 57.6 + 16.128 = 73.728; cd = 33.12
    assert I.laguerre_rsi([100.0, 100.0])[1] == pytest.approx(100 * 73.728 / 106.848, rel=1e-12)
    # (1 - gamma) is computed as the script writes it: 0.19999999999999996, not alpha
    g = 1 - 0.2
    l0 = (1 - g) * 3.0
    l1 = -g * l0
    l2 = -g * l1
    l3 = -g * l2
    assert I.laguerre_rsi([3.0])[0] == 100 * (((l0 - l1) + (l2 - l3)) / (((l0 - l1) + (l2 - l3)) + (l2 - l1)))
    assert same(I.laguerre_rsi([nan]), [0.0])                       # an na source: every ternary takes 0 -> LaRSI 0
    assert np.all(I.laguerre_rsi(np.arange(1.0, 300.0))[200:] == 100)       # rising: L0 > L1 > L2 > L3, cd = 0
    assert np.all(I.laguerre_rsi(np.arange(1000.0, 700.0, -1.0))[200:] == 0)
    x = np.linspace(100, 200, 400)
    assert np.all(I.laguerre_rsi(x)[100:] == 100) and np.all(I.laguerre_rsi(x[::-1].copy())[100:] == 0)
    r = I.laguerre_rsi(walk(5000, 5))
    assert np.all((r >= 0) & (r <= 100)) and not np.isnan(r).any()   # defined from bar 0


def test_vwrsi_by_hand():
    # close 10,11,10,12, volume 1,2,1,3, length 2: change na,1,-1,2
    # gains*vol = na,2,0,6 -> rma: bar 2 = (0+2)/2 = 1, bar 3 = 0.5*6 + 0.5*1 = 3.5
    # losses*vol = na,0,1,0 -> rma: bar 2 = (1+0)/2 = 0.5, bar 3 = 0.25
    # the volume rma starts a bar earlier (volume is never na): bar 1 = (2+1)/2 = 1.5, bar 2 = 1.25, bar 3 = 2.125
    # up = 1/1.25 = 0.8, down = 0.5/1.25 = 0.4 -> rs 2 -> 66.67; bar 3: up/down = 3.5/0.25 = 14 -> 93.33
    r = I.vwrsi([10.0, 11, 10, 12], [1.0, 2, 1, 3], length=2)
    assert close_to(r.up, [nan, nan, 0.8, 3.5 / 2.125])
    assert close_to(r.down, [nan, nan, 0.4, 0.25 / 2.125])
    assert close_to(r.rsi, [nan, nan, 100 - 100 / 3, 100 - 100 / 15])
    # constant volume: the weights cancel and the line is the RSI (rounding aside)
    c = walk(2000, 6)
    vc = I.vwrsi(c, np.full(2000, 37.0)).rsi
    assert np.allclose(vc[14:], I.plain_rsi(c)[14:], rtol=0, atol=1e-9) and first_valid(vc) == 14
    with pytest.raises(ValueError):
        I.vwrsi(c, np.where(np.arange(2000) == 500, nan, 1.0))     # an na volume is refused (DEVIATIONS 5: 0 instead)


def test_vwrsi_zero_volume_bars_hold_the_line():
    # DEVIATIONS 5: an hour without a Binance kline has volume 0. Gain*vol = loss*vol = 0, both averages are multiplied
    # by (1 - 1/14), so their ratio, the line, is unchanged (rounding aside); nothing becomes na.
    h, lo, c, v = bars(400, 18)
    v[200:230] = 0.0
    r = I.vwrsi(c, v).rsi
    assert not np.isnan(r[14:]).any()
    assert np.allclose(r[200:230], r[199], rtol=0, atol=1e-10)
    assert abs(r[230] - r[229]) > 1e-6                              # the first bar with volume again moves it


def test_range_score_by_hand_one_flip():
    src = np.array([40.0] * 30 + [60.0] * 60)                       # one flip through 50, on bar 30
    m = len(src)
    # the script's intermediates, computed with the module's helpers as the script writes them:
    t = np.zeros(m)
    t[30] = 1.0                                                     # dir + dir[1] == 0 only on bar 30
    w = 1.0 / I.math_sum(np.ones(m), 10)
    assert np.isnan(w[:9]).all() and np.all(w[9:] == 0.1)          # 1 / math.sum(1, 10)
    p = I.sma(t * w, 10)
    # p = sma(t * 0.1, 10): na before bar 18 (w from bar 9), 0.1/10 on bars 30..39, 0 elsewhere
    assert first_valid(p) == 18 and np.all(p[18:30] == 0) and np.all(p[40:] == 0)
    assert np.allclose(p[30:40], 0.01, rtol=1e-14, atol=0)
    f = I.hma(p, 5) * 5.0
    # f = 5 * hma(p, 5): first on bar 23 (p from 18, wma5 from 22); bar 30: wma2 = (2/3)0.01, wma5 = (5/15)0.01,
    # raw = 0.01, hma = (2/3)0.01, f = 0.1/3; bar 31: wma2 = 0.01, wma5 = (9/15)0.01, raw = 0.014,
    # hma = (2*0.014 + 0.01)/3, f = 0.19/3
    assert first_valid(f) == 23 and np.all(f[23:30] == 0)
    assert f[30] == pytest.approx(0.1 / 3, rel=1e-12) and f[31] == pytest.approx(0.19 / 3, rel=1e-12)
    assert np.all(f[45:] == 0)
    s = I.range_score(src, 10)
    assert same(s, np.maximum(I.hma(f, 20), 0.0))
    # first on bar 45 (= 23 + 19 + 3); exactly 0 once f has been 0 for 23 bars (bar 67)
    assert first_valid(s) == 45 and np.all(s[45:] >= 0) and np.all(s[67:] == 0) and s[45:67].max() > 0
    with pytest.raises(ValueError):
        I.range_score(src, 9)                                       # 9/2 = 4.5 would reach ta.hma: not ported


def test_range_score_by_hand_chop():
    n = 120
    # An RSI alternating around 50 flips every bar: t = 1 from bar 1, w = 1/10 from bar 9, p = 0.1 from bar 18, the
    # HMA of a constant is that constant, f = 0.1 * (5 + (2/3)*5) with 2/3 = 0 (Pine v5 const int division) = 0.5,
    # score = 0.5, histogram 25 (it would be 0.8333 / 41.67 if 2/3 were 0.667: DEVIATIONS 13)
    alt = np.where(np.arange(n) % 2 == 0, 60.0, 40.0)
    rs = I.range_score(alt, 10)
    assert np.isnan(rs[:45]).all() and close_to(rs[45:], np.full(n - 45, 0.5))
    assert same(I.range_score(np.full(n, 70.0), 10)[45:], np.zeros(n - 45))       # never a flip -> 0
    # an na source is "not above 50" (dir = -1): na then below 50 never flips, and the score is valid from bar 45
    s = np.concatenate([np.full(30, nan), np.full(n - 30, 40.0)])
    assert same(I.range_score(s, 10), [nan] * 45 + [0.0] * (n - 45))


def test_bjorgum_tsi_sign_and_first_bars():
    up = np.arange(100.0, 400.0)
    t = I.bjorgum_tsi(up)
    assert np.isnan(t.tsi[0]) and np.all(t.tsi[1:] == 100)          # every change > 0: num == den
    assert same(t.signal, I.ema(t.tsi, 14))
    assert np.all(I.bjorgum_tsi(up[::-1].copy()).tsi[1:] == -100)
    bull = I.bjorgum_tsi(walk(3000, 7, drift=+0.3)).tsi
    bear = I.bjorgum_tsi(walk(3000, 7, drift=-0.3)).tsi
    assert np.nanmean(bull[100:] > 0) > 0.7 and np.nanmean(bear[100:] < 0) > 0.7
    assert np.nanmax(np.abs(I.bjorgum_tsi(walk(3000, 8)).tsi)) <= 100 + 1e-9
    # SMA-seeded EMAs (DEVIATIONS 11): the TSI from bar 1 + 24 + 4 = 29, its signal from 29 + 13 = 42
    ts = I.bjorgum_tsi(walk(300, 9), ema_seed="sma")
    assert first_valid(ts.tsi) == 29 and first_valid(ts.signal) == 42


def test_tsi_sign_against_the_20_bar_change():
    # On a driftless walk the TSI's numerator is a fixed linear filter of the changes, EMA5(EMA25(pc)), with kernel
    # w_k = ab/(b - a) ((1-a)^(k+1) - (1-b)^(k+1)), a = 2/26, b = 2/6. Its correlation rho with the 20-bar change gives
    # P(same sign) = 1/2 + asin(rho)/pi for Gaussian changes (0.876); the denominator is positive.
    a, b = 2 / 26, 2 / 6
    k = np.arange(400)
    w = a * b / (b - a) * ((1 - a) ** (k + 1) - (1 - b) ** (k + 1))
    u = (k < 20).astype(float)
    expect = 0.5 + math.asin((w @ u) / math.sqrt((w @ w) * (u @ u))) / math.pi
    c = walk(20000, 32)
    t = I.bjorgum_tsi(c).tsi
    d20 = c - I.hist(c, 20)
    ok = ~np.isnan(t) & ~np.isnan(d20) & (d20 != 0)
    assert abs(np.mean(np.sign(t[ok]) == np.sign(d20[ok])) - expect) < 0.02
    # with first-value seeds the two EMAs commute (each acts as if the series had always been at its first value)
    pc = I.change(walk(3000, 33))
    assert np.nanmax(np.abs(I.ema(I.ema(pc, 25), 5) - I.ema(I.ema(pc, 5), 25))) < 1e-9


def test_qqe_bands_by_hand_constant_distance():
    # smoothed RSI 50 52 55 53 49 45 47, band distance 2 (na on bar 0): new long = srsi - 2, new short = srsi + 2
    srsi = np.array([50.0, 52, 55, 53, 49, 45, 47])
    q = I.qqe_bands(srsi, np.array([nan, 2, 2, 2, 2, 2, 2]))
    # long band: bar 1 = 50 (no band before); bar 2: 52 > 50 and 55 > 50 -> max(50, 53) = 53; bar 3: 53 > 53 fails ->
    # 51; bar 4: 49 > 51 fails -> 47; bar 5: 45 > 47 fails -> 43; bar 6: 45 > 43 and 47 > 43 -> max(43, 45) = 45
    assert same(q.long, [nan, 50, 53, 51, 47, 43, 45])
    # short band: 54; 55 < 54 fails -> 57; 55 < 57 and 53 < 57 -> min(57, 55) = 55; min(55, 51); min(51, 47); 47 < 47
    # fails -> 49
    assert same(q.short, [nan, 54, 57, 55, 51, 47, 49])
    # ta.cross(srsi, shortBand[1]): srsi > sb[1] is - - T F F F F (47 > 47 false) -> a change on bar 3 only;
    # ta.cross(longBand[1], srsi): lb[1] > srsi is - - F F (53 > 53) T T F -> changes on bars 4 and 6
    assert same(I.cross(srsi, I.hist(q.short, 1)), [False, False, False, True, False, False, False])
    assert same(I.cross(I.hist(q.long, 1), srsi), [False, False, False, False, True, False, True])
    # trend: na until the first cross, 1 on bar 3, -1 on bar 4, kept on bar 5, -1 again on bar 6
    assert same(q.trend, [nan, nan, nan, 1, -1, -1, -1])
    assert same(q.line, [nan, 54, 57, 51, 51, 47, 49])              # long band where trend == 1, else (na too) short
    # The first half of line 45's condition (smoothedRsi[1] > longBand[1]) only matters after a bar with no band
    # distance, where the band touches the RSI. Bar 2 below: 50 > 50 is false, so the band is the new 51 - 2 = 49,
    # not max(50, 49) = 50.
    q0 = I.qqe_bands([49.0, 50.0, 51.0], [nan, 0.0, 2.0])
    assert same(q0.long, [nan, 50, 49])
    # Line 46 alike: on bar 2, 49 < 49 is false, so the short band is the new 48 + 3 = 51, not min(49, 51) = 49.
    q1 = I.qqe_bands([51.0, 49.0, 48.0], [nan, 0.0, 3.0])
    assert same(q1.short, [nan, 49, 51])


def test_qqe_bands_by_hand_from_the_rsi():
    sm = np.array([50.0, 52, 55, 53, 49, 45, 60])
    sa = I.ema(np.abs(I.hist(sm, 1) - sm), 11)
    # the ATR of the RSI: na,2,3,2,4,4,15; its EMA (alpha 1/6, first-value seed): 2; 3/6 + 2*5/6 = 13/6;
    # 2/6 + (13/6)(5/6) = 77/36; 529/216; 3509/1296; 36985/7776
    assert close_to(sa, [nan, 2, 13 / 6, 77 / 36, 529 / 216, 3509 / 1296, 36985 / 7776])
    d = 3.0 * sa
    q = I.qqe_bands(sm, d)
    new_long, new_short = sm - d, sm + d
    # long band: bar 1 = 46; bars 2-4: the RSI and its previous value above the band -> max(prev, new) = 48.5;
    # bar 5: 45 < 48.5 -> the new band; bar 6: 45 and 60 above it -> max(prev, 60 - 3*36985/7776)
    assert close_to(q.long, [nan, 46, 48.5, 48.5, 48.5, new_long[5], max(new_long[5], new_long[6])])
    # short band: bars 2-3 stay 58; bar 4 = min(58, 56.35); bar 5 = min(56.35, 53.12); bar 6: 60 is not below -> new
    assert close_to(q.short, [nan, 58, 58, 58, new_short[4], new_short[5], new_short[6]])
    # bar 5: longBand[1] = 48.5 > 45 now, 48.5 > 49 false before -> trend -1; bar 6: 60 > shortBand[1] = 53.12 now,
    # 45 > 56.35 false before -> trend 1, tested before the long cross that also fires on bar 6
    assert same(q.trend, [nan, nan, nan, nan, nan, -1, 1])
    assert close_to(q.line, [nan, 58, 58, 58, new_short[4], new_short[5], q.long[6]])


def test_qqe_colour_thresholds_are_strict():
    # secondary RSI - 50 against +-3 and primary RSI - 50 against the band, both strict (lines 85-86); ties are GRAY
    p = np.array([60.0, 60.0, 53.0, 40.0, 40.0, 47.0, 55.0, nan, 60.0])
    s = np.array([60.0, 53.0, 60.0, 40.0, 47.0, 40.0, 55.0, 60.0, nan])
    up, lo = np.full(9, 3.0), np.full(9, -3.0)
    # bar 0: 10 > 3 and 10 > 3 -> BLUE; bar 1: 3 > 3 false; bar 2: 3 > 3 (the band) false; bar 3: RED;
    # bars 4, 5: the ties at -3; bar 6: 5 > 3 and 5 > 3 -> BLUE; bars 7, 8: na -> GRAY
    assert I.qqe_colour(p, s, up, lo).tolist() == [1, 0, 0, -1, 0, 0, 1, 0, 0]
    assert I.qqe_colour(p, s, up, lo, threshold=5.0).tolist() == [1, 0, 0, -1, 0, 0, 0, 0, 0]


def test_qqe_mod_structure():
    c = walk(600, 10)
    q = I.qqe_mod(c)
    assert first_valid(q.rsi) == 6 and first_valid(q.srsi1) == 6   # RSI(6) of the changes on bars 1..6
    assert first_valid(q.line1) == 7 and first_valid(q.long1) == 7  # the RSI's ATR needs srsi[1]
    assert first_valid(q.bb_upper) == 56                            # 50 values of line1 - 50
    assert same(q.srsi1, q.srsi2)                                   # both QQEs smooth the same RSI(6) with EMA(5)
    assert q.color.dtype == np.int8 and np.all(q.color[:56] == I.GRAY)
    p50, s50 = q.srsi1 - 50, q.srsi2 - 50
    with np.errstate(invalid="ignore"):
        blue = (s50 > 3) & (p50 > q.bb_upper)
        red = (s50 < -3) & (p50 < q.bb_lower)
    assert np.array_equal(q.color == I.BLUE, blue) and np.array_equal(q.color == I.RED, red)
    assert (q.color == I.BLUE).any() and (q.color == I.RED).any() and (q.color == I.GRAY).any()
    assert same(q.white, q.line2 - 50)
    assert close_to(q.bb_upper - q.bb_basis, 0.35 * I.stdev(q.line1 - 50, 50), 1e-12)
    qs = I.qqe_mod(c, ema_seed="sma")                                # SMA seeds: srsi from 10, bands from 21, BB from 70
    assert first_valid(qs.srsi1) == 10 and first_valid(qs.line1) == 21 and first_valid(qs.bb_upper) == 70


# ───────────────────────────── 2. TradingView's own output ─────────────────────────────

# BINANCE:BTCUSDC 1W, bars 9..40 of a chart starting 2018-12-10 (2019-02-11 .. 2019-09-16), as recorded in the PineTS
# project's tests/namespaces/ta/ta-late-first-call-wide.test.ts ("Every expected value was read on TradingView").
_W_HIGH = [3652.61, 4184.27, 3880.0, 3949.99, 4046.34, 4053.15, 4130.0, 5377.98, 5469.0, 5360.0, 5650.0, 5825.0, 7535.58,
           8395.47, 8787.0, 9088.0, 8752.45, 9386.37, 11290.0, 13864.42, 12040.0, 13174.99, 11100.0, 10691.59, 11077.0,
           12315.55, 11550.78, 10952.1, 10638.85, 10923.0, 10538.91, 10382.75]
_W_LOW = [3520.1, 3613.87, 3655.25, 3666.0, 3786.0, 3863.95, 3861.25, 4050.0, 4903.54, 4941.13, 4805.74, 5053.56, 5563.91,
          6841.02, 7464.94, 7988.88, 7441.21, 7524.35, 8938.57, 10300.0, 9668.33, 10101.0, 9077.0, 9120.0, 9356.28,
          10971.67, 9730.6, 9751.7, 9315.07, 9741.46, 9857.0, 9600.0]
_W_CLOSE = [3628.54, 3721.64, 3784.63, 3897.55, 3967.01, 3973.06, 4093.12, 5192.3, 5161.56, 5297.0, 5152.9, 5713.84,
            6947.86, 8200.0, 8733.12, 8743.6, 7638.29, 8988.07, 10847.25, 10748.93, 11480.77, 10180.0, 10589.32, 9534.99,
            10974.15, 11539.4, 10316.56, 10136.39, 9758.57, 10398.27, 10314.99, 10025.82]


def test_tradingview_values_btcusdc_weekly():
    """Each function first called on bar 9, so its warm-up starts there; TradingView's values on bars 9..15, 20, 40
    (printed with 3 decimals). ta.ema matches only with the SMA seed (DEVIATIONS 11), ta.hma only with the floored
    half length (DEVIATIONS 12)."""
    h, lo, c = np.array(_W_HIGH), np.array(_W_LOW), np.array(_W_CLOSE)
    at = [0, 1, 2, 3, 4, 5, 6, 11, 31]
    tv = {
        "sma": [nan] * 4 + [3799.874, 3868.778, 3943.074, 5303.52, 10126.808],
        "ema": [nan] * 4 + [3799.874, 3857.603, 3936.108, 5204.442, 10203.55],
        "rma": [nan] * 4 + [3799.874, 3834.511, 3886.233, 4872.586, 10171.739],
        "wma": [nan] * 4 + [3856.731, 3914.459, 3989.24, 5372.481, 10149.16],
        "hma": [nan] * 5 + [4028.746, 4087.182, 5545.561, 10224.605],
        "stdev": [nan] * 4 + [120.982, 100.083, 101.156, 211.478, 225.829],
        "rsi": [nan] * 5 + [100, 100, 90.356, 46.493],
        "msum": [nan] * 4 + [18999.37, 19343.89, 19715.37, 26517.6, 50634.04],
        "atr": [nan] * 4 + [294.398, 273.358, 272.437, 598.948, 1257.278],
    }
    mine = {"sma": I.sma(c, 5), "ema": I.ema(c, 5, seed="sma"), "rma": I.rma(c, 5), "wma": I.wma(c, 5),
            "hma": I.hma(c, 5), "stdev": I.stdev(c, 5), "rsi": I.rsi(c, 5), "msum": I.math_sum(c, 5),
            "atr": I.atr(h, lo, c, 5)}
    for k, want in tv.items():
        got = mine[k][at]
        want = np.array(want)
        assert np.array_equal(np.isnan(got), np.isnan(want)), k
        ok = ~np.isnan(want)
        assert np.all(np.abs(got[ok] - want[ok]) <= 6e-4), (k, got, want)
    first = I.ema(c, 5)[at]                                          # the plan's seed: a value from bar 0, and another
    assert not np.isnan(first[0]) and abs(first[4] - 3799.874) > 30
    rounded = I.wma(2.0 * I.wma(c, 3) - I.wma(c, 5), 2)[at]          # a rounded HMA half does not match TradingView
    assert np.max(np.abs(rounded[5:] - np.array(tv["hma"][5:]))) > 1.0


def test_tradingview_wma_with_leading_na():
    """ta.wma(x, 5) on a bar_index-driven source that is na on bars 0..6 (PineTS tests/namespaces/ta/
    warmup-leading-na.test.ts, values read on TradingView in Oct 2026): na until five values exist."""
    pat = [5.0, 3, 8, 6, 2, 9, 4, 7, 1, 6, 3, 10, 5, 2, 8, 4]
    i = np.arange(30)
    x = np.array([pat[k % 16] for k in i])
    lead = np.where(i < 7, nan, x)
    want = [nan] * 11 + [5.9333333333, 5.8, 4.8, 5.7333333333, 5.2, 4.9333333333, 4.3333333333, 5.5333333333,
                         5.6666666667, 4.6, 6, 5.4666666667, 5.8666666667, 4.3333333333, 4.8, 4, 5.9333333333, 5.8, 4.8]
    assert close_to(I.wma(lead, 5), want, 1e-9)


# ───────────────────────────── 3. invariants ─────────────────────────────

def test_ranges_and_na_only_in_the_warm_up():
    for seed in range(3):
        h, lo, c, v = bars(4000, 100 + seed)
        a = I.compute_all(h, lo, c, v)
        for k in ("rsi", "larsi", "vwrsi", "qqe_srsi1", "qqe_srsi2"):
            x = a[k][~np.isnan(a[k])]
            assert len(x) > 3900 and np.all((x >= 0) & (x <= 100)), k
        assert np.nanmax(np.abs(a["tsi"])) <= 100 + 1e-9
        s = a["vwrsi_score"][~np.isnan(a["vwrsi_score"])]
        assert np.all(s >= 0) and (s == 0).any() and (s > 0).any()
        assert same(a["vwrsi_hist"], a["vwrsi_score"] * 50)
        assert np.all(a["atr14"][13:] > 0)
        for k, arr in a.items():                                     # na only before the first value
            f = first_valid(arr)
            assert f is not None and not np.isnan(arr[f:].astype(float)).any(), k


def test_qqe_invariants():
    h, lo, c, v = bars(4000, 22, decimals=2)
    q = I.qqe_mod(c)
    for lb, r, sb in ((q.long1, q.srsi1, q.short1), (q.long2, q.srsi2, q.short2)):
        ok = ~np.isnan(lb)
        assert np.all(lb[ok] <= r[ok]) and np.all(r[ok] <= sb[ok])   # the long band below the RSI, the short above
    assert same(q.line1, np.where(q.trend1 == 1, q.long1, q.short1))
    assert set(np.unique(q.color).tolist()) <= {-1, 0, 1}
    ok = ~np.isnan(q.bb_basis)
    assert np.all(q.bb_upper[ok] >= q.bb_basis[ok]) and np.all(q.bb_lower[ok] <= q.bb_basis[ok])
    blue, red = q.color == I.BLUE, q.color == I.RED
    assert np.all(q.srsi2[blue] - 50 > 3) and np.all(q.srsi1[blue] - 50 > q.bb_upper[blue])
    assert np.all(q.srsi2[red] - 50 < -3) and np.all(q.srsi1[red] - 50 < q.bb_lower[red])
    assert min(int(np.sum(q.color == k)) for k in (-1, 0, 1)) > 50


def test_first_bars():
    h, lo, c, v = bars(400, 41, decimals=2)
    a = I.compute_all(h, lo, c, v)
    want = {"rsi": 14, "larsi": 0, "vwrsi": 14, "vwrsi_score": 45, "vwrsi_hist": 45, "tsi": 1, "tsi_signal": 1,
            "qqe_srsi1": 6, "qqe_srsi2": 6, "qqe_line1": 7, "qqe_line2": 7, "qqe_bb_basis": 56, "qqe_bb_upper": 56,
            "qqe_bb_lower": 56, "qqe_white": 7, "ma200": 199, "atr14": 13}
    assert {k: first_valid(a[k]) for k in want} == want
    assert a["tsi_signal"][1] == a["tsi"][1] and abs(a["tsi"][1]) == 100.0       # one change: +-100
    assert abs(a["larsi"][0] - 100 * 41 / 61) < 1e-12
    q = I.qqe_mod(c)
    k = first_valid(q.trend1)                                        # the trend is na until its first cross ...
    assert k > 7 and same(q.line1[7:k], q.short1[7:k])               # ... and the line is the short band until then
    assert set(I.compute_all(h, lo, c, v)) == set(want) | {"qqe_color"}


@pytest.mark.parametrize("seed", ["first", "sma"])
def test_no_look_ahead(seed):
    h, lo, c, v = bars(1500, 16)
    full = I.compute_all(h, lo, c, v, ema_seed=seed)
    for k in (60, 333, 1000):
        part = I.compute_all(h[:k], lo[:k], c[:k], v[:k], ema_seed=seed)
        for name, arr in full.items():
            assert same(part[name], arr[:k]), (name, k)


def test_inputs_not_modified():
    h, lo, c, v = bars(300, 17)
    keep = [x.copy() for x in (h, lo, c, v)]
    I.compute_all(h, lo, c, v)
    I.qqe_mod(c)
    I.vwrsi(c, v)
    assert all(np.array_equal(a, b) for a, b in zip(keep, (h, lo, c, v)))


def test_an_na_inside_a_series_is_refused():
    x = np.array([1.0, 2.0, nan, 3.0, 4.0, 5.0])
    for fn in (lambda: I.sma(x, 2), lambda: I.math_sum(x, 2), lambda: I.wma(x, 2), lambda: I.hma(x, 2),
               lambda: I.ema(x, 2), lambda: I.rma(x, 2), lambda: I.stdev(x, 2), lambda: I.crossover(x, 2.0),
               lambda: I.crossunder(2.0, x), lambda: I.cross(x, x)):
        with pytest.raises(ValueError):
            fn()
    with pytest.raises(ValueError):
        I.sma(np.ones((2, 2)), 2)


# ───────────────────────────── 4. the oracle: port B and its Pine VM ─────────────────────────────

def _oracle_lines(h, lo, c, v, ema_seed="first"):
    t = O.table(h, lo, c, v)
    q = O.qqe_mod(c, ema_seed=ema_seed)
    ts = O.bjorgum_tsi(c, ema_seed=ema_seed)
    return {"rsi": t["rsi14"], "larsi": t["larsi"], "vwrsi": t["vwrsi"], "vwrsi_score": t["vwrsi_range_score"],
            "vwrsi_hist": t["vwrsi_consolidation"], "tsi": ts.tsi, "tsi_signal": ts.signal, "qqe_srsi1": q.rsi_p,
            "qqe_srsi2": q.rsi_s, "qqe_line1": q.tl_p, "qqe_line2": q.tl_s, "qqe_bb_basis": q.bb_basis,
            "qqe_bb_upper": q.bb_upper, "qqe_bb_lower": q.bb_lower, "qqe_color": q.color, "qqe_white": q.white,
            "ma200": t["sma200"], "atr14": t["atr14"],
            "long1": q.long_p, "short1": q.short_p, "trend1": q.trend_p, "long2": q.long_s, "short2": q.short_s,
            "trend2": q.trend_s}


def _module_lines(h, lo, c, v, ema_seed="first"):
    a = I.compute_all(h, lo, c, v, ema_seed=ema_seed)
    q = I.qqe_mod(c, ema_seed=ema_seed)
    a.update({"long1": q.long1, "short1": q.short1, "trend1": q.trend1, "long2": q.long2, "short2": q.short2,
              "trend2": q.trend2})
    return a


def _assert_equal_to_oracle(h, lo, c, v, ema_seed="first", where=""):
    mine, theirs = _module_lines(h, lo, c, v, ema_seed), _oracle_lines(h, lo, c, v, ema_seed)
    assert set(mine) == set(theirs)
    for k in mine:
        a, b = mine[k].astype(float), theirs[k]
        if k == "qqe_color":                                         # port B: NaN while the smoothed RSI is na
            r = np.isnan(mine["qqe_srsi2"])                          # (bars 0..5; 0..9 with SMA seeds); here GRAY
            assert np.all(a[r] == I.GRAY) and np.isnan(b[r]).all(), where
            a, b = a[~r], b[~r]
        assert same(a, b), (where, k, np.flatnonzero(~((a == b) | (np.isnan(a) & np.isnan(b))))[:5])


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_equal_to_port_b_bit_for_bit(seed):
    h, lo, c, v = bars(3000, seed, decimals=2)                       # rounded prices: some changes are exactly 0
    v[1000:1040] = 0.0                                               # a stretch without volume (DEVIATIONS 5)
    _assert_equal_to_oracle(h, lo, c, v, where=f"seed {seed}")
    h, lo, c, v = bars(2500, 50 + seed)
    _assert_equal_to_oracle(h, lo, c, v, ema_seed="sma", where=f"seed {50 + seed}, SMA seeds")


def test_equal_to_port_b_on_the_helpers():
    h, lo, c, v = bars(1500, 60, decimals=1)
    x = c - c.mean()
    for n in (1, 2, 5, 14, 50):
        assert same(I.sma(c, n), O.sma(c, n)) and same(I.wma(c, n), O.wma(c, n)) and same(I.rma(c, n), O.rma(c, n))
        assert same(I.ema(c, n), O.ema(c, n)) and same(I.ema(c, n, seed="sma"), O.ema(c, n, seed="sma"))
        assert same(I.stdev(x, n), O.stdev(x, n)) and same(I.math_sum(x, n), O.math_sum(x, n))
        assert same(I.rsi(c, n), O.rsi(c, n)) and same(I.atr(h, lo, c, n), O.atr(h, lo, c, n))
    for n in (2, 4, 5, 9, 20):
        assert same(I.hma(c, n), O.hma(c, n))
    assert same(I.tsi(c, 13, 25) * 100.0, O.bjorgum_tsi(c, 13, 25).tsi)
    for f_mine, f_theirs in ((I.crossover, O.crossover), (I.crossunder, O.crossunder), (I.cross, O.cross)):
        assert np.array_equal(f_mine(c, I.sma(c, 5)), f_theirs(c, O.sma(c, 5)))


def test_equal_to_port_b_pine_vm():
    """Port B's second transcription: one state object per Pine call site, bar by bar in plain Python."""
    h, lo, c, v = bars(2500, 11, decimals=2)
    assert same(I.plain_rsi(c), O.vm_rsi14(c))
    assert same(I.laguerre_rsi(c), O.vm_larsi(c))
    vr, vs = O.vm_vwrsi(c, v)
    w = I.vwrsi(c, v)
    assert same(w.rsi, vr) and same(w.score, vs) and same(w.hist, vs * 50)
    vt, vsig = O.vm_tsi(c)
    t = I.bjorgum_tsi(c)
    assert same(t.tsi, vt) and same(t.signal, vsig)
    ref = O.vm_qqe(c)
    q = I.qqe_mod(c)
    for mine, k in ((q.line1, "tl_p"), (q.line2, "tl_s"), (q.srsi1, "rsi_p"), (q.srsi2, "rsi_s"), (q.bb_basis, "basis"),
                    (q.bb_upper, "upper"), (q.bb_lower, "lower"), (q.white, "white")):
        assert same(mine, ref[k]), k
    assert same(q.color[6:], ref["color"][6:]) and np.isnan(ref["color"][:6]).all()


# ───────────────────────────── 5. the real bars (the guard closed) ─────────────────────────────

_RECORDED = {   # bar open (UTC) -> rsi, larsi, vwrsi, score, tsi, signal, qqe_line1, white, bb_upper, colour, ma200, atr14
    ("XAUUSDm", "4H", "2019-01-02 00:00"): (62.543219, 100.0, 57.012604, 0.0, 25.48456, 26.97014, 66.317239, 14.071837,
                                            16.536462, 0, 1239.6473, 4.189442),
    ("XAUUSDm", "4H", "2023-01-02 20:00"): (69.39103, 100.0, 64.294931, 0.045587, 30.630956, 16.472772, 69.889319,
                                            23.586971, 10.882947, 1, 1782.45892, 7.752657),
    ("XAUUSDm", "1D", "2023-01-02 00:00"): (64.133917, 100.0, 65.475895, 0.0, 21.991522, 19.006171, 56.642077,
                                            10.047024, 11.193638, 1, 1780.58109, 22.91054),
    ("BTCUSDm", "4H", "2019-01-01 00:00"): (40.960669, 46.661711, 40.912105, 0.12776, -14.719383, -4.698282, 43.741966,
                                            -10.231163, 1.721303, -1, 3740.12735, 87.849391),
    ("BTCUSDm", "1D", "2023-01-01 00:00"): (43.998742, 4.550517, 43.459992, 0.0, -12.833899, -8.874265, 44.126405,
                                            -8.705615, -0.01063, -1, 19697.4929, 333.336625),
}
_RECORDED_COLS = ("rsi", "larsi", "vwrsi", "vwrsi_score", "tsi", "tsi_signal", "qqe_line1", "qqe_white", "qqe_bb_upper",
                  "qqe_color", "ma200", "atr14")


@pytest.fixture(scope="module")
def real_bars(tmp_path_factory):
    """The 1H / 4H / 1D bars of a symbol from its data start to the hold-out start (the guard pointed at an empty
    folder), with the Binance volume for BTC when its files are on this machine."""
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
                mk = TM.load(symbol)
                out = {tf: mk.tbars(tf) for tf in TM.TFS}
                rv = {}
                if symbol.startswith("BTC") and all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
                    rv = {tf: TM.binance_volume(mk, tf)[0] for tf in TM.TFS}
            del mk
            cache[symbol] = (out, rv)
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_equal_to_port_b_and_external(symbol, real_bars):
    tbars, rv = real_bars(symbol)
    for tf, b in tbars.items():
        assert b.tc[-1] <= TM.CUT_S                                  # nothing from the hold-out
        h, lo, c, v = b.h, b.l, b.c, b.vol.astype(float)
        _assert_equal_to_oracle(h, lo, c, v, where=f"{symbol} {tf}")
        if tf in rv:                                                 # BTC: the VWRSI on Binance volume (RV)
            mine, theirs = I.vwrsi(c, rv[tf]), O.vwrsi(c, rv[tf])
            assert same(mine.rsi, theirs.rsi) and same(mine.score, theirs.range_score), tf
        a = I.compute_all(h, lo, c, v)
        for k, x in a.items():
            assert not np.isnan(x[250:].astype(float)).any(), (tf, k)
        assert np.nanmax(np.abs(a["rsi"] - X.wilder_rsi(c, 14))) < 1e-12
        wa = X.wilder_atr(h, lo, c, 14)
        assert np.nanmax(np.abs(a["atr14"] - wa) / wa) < 1e-13      # the S1 stop's ATR, another update order
        assert np.nanmax(np.abs(a["ma200"] - X.sma(c, 200)) / c) < 1e-13


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_recorded_values(symbol, real_bars):
    """Values printed (6 decimals) when the ports were reconciled: a guard against both implementations changing."""
    tbars, _ = real_bars(symbol)
    for (sym, tf, when), want in _RECORDED.items():
        if sym != symbol:
            continue
        b = tbars[tf]
        i = int(np.searchsorted(b.t, TM.s_of(when)))
        assert int(b.t[i]) == TM.s_of(when)
        a = I.compute_all(b.h, b.l, b.c, b.vol)
        got = [float(a[k][i]) for k in _RECORDED_COLS]
        assert np.allclose(got, want, rtol=0, atol=1e-6), (sym, tf, when, got)
