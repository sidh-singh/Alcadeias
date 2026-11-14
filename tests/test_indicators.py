"""
The numba indicator kernels against the LIVE indicator code (``indicator.py``).

The live bot recomputes, on every ~1 s poll and for every timeframe, RSI and MACD over
the last 500 bars *including the still-forming one* and then reads the direction of the
latest RSI / MACD-histogram pivot (``Indicator.latest_pivot_slope``). Those signs are
the only inputs of every entry, force-close and profit-book decision, and the forming-bar
RSI drives every ladder add. The fast engine never calls that code: it pre-computes
closed-bar values once (``indicator_arrays`` / ``pivot_arrays``) and updates the forming
bar with closed-form recursions inside ``run_kernel``.

This module is the independent proof that the two are the same numbers:

* closed-bar RSI / MACD arrays                     == ``calculate_rsi`` / ``calculate_macd``
* the forming-bar update                           == the live functions on history + [price]
* ``pivot_arrays`` + ``slope_sign``                == ``latest_pivot_slope(...)['sign']``
* what the real kernel sees and decides at a poll  == the live indicator + strategy code
                                                      evaluated on the same bars

None of it goes through the reference engine (``reference.py``), so a mistake shared by
the simulated MT5 terminal and the kernel could not hide here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import constants as live_constants
from indicator import Indicator
from strategy import Strategy

from backtesting.config import BacktestConfig, TF_SECONDS
from backtesting.data import store
from backtesting.engine import fast
from backtesting.engine import kernels as K

IND = Indicator()
TOL = 1e-9

# (rsi_len, macd_fast, macd_slow, macd_signal). The first is the live setting.
PARAM_SETS = [
    (14, 12, 26, 9),
    (7, 5, 13, 4),
    (21, 8, 21, 5),
    (2, 3, 10, 16),
    (9, 26, 12, 9),      # fast > slow: legal, the macd line just flips sign
    (14, 12, 12, 9),     # fast == slow: macd is identically 0
    (1, 1, 2, 1),        # the shortest lengths the recursions accept
    (30, 19, 39, 9),
]
PARAM_IDS = ["-".join(map(str, p)) for p in PARAM_SETS]
SYMBOLS = ("XAUUSDm", "BTCUSDm")


# ───────────────────────────── helpers ─────────────────────────────

def kernel_arrays(closes, rsi_len, mf, ms, msig) -> dict:
    C = np.ascontiguousarray(closes, dtype=np.float64)
    AG, AL, RSI, EF, ES, SG, HIST = K.indicator_arrays(C, int(rsi_len), int(mf), int(ms), int(msig))
    return dict(AG=AG, AL=AL, rsi=RSI, EF=EF, ES=ES, macd=EF - ES, signal=SG, hist=HIST)


def live_arrays(closes, rsi_len, mf, ms, msig) -> dict:
    s = pd.Series(np.asarray(closes, dtype=float))
    rsi = IND.calculate_rsi(s, length=rsi_len, ma_type="RMA")
    macd = IND.calculate_macd(s, fast=mf, slow=ms, signal=msig)
    return dict(rsi=rsi.to_numpy(), macd=macd["macd"].to_numpy(), signal=macd["signal"].to_numpy(),
                hist=macd["hist"].to_numpy())


def assert_same(kernel: np.ndarray, live: np.ndarray, what: str, atol: float = TOL) -> None:
    """Equal within ``atol`` wherever the live value is defined, and undefined (NaN) in the same places."""
    assert kernel.shape == live.shape, f"{what}: length {kernel.shape} vs live {live.shape}"
    assert np.array_equal(np.isnan(kernel), np.isnan(live)), f"{what}: defined on different bars than live"
    ok = ~np.isnan(live)
    if ok.any():
        worst = float(np.max(np.abs(kernel[ok] - live[ok])))
        assert worst <= atol, f"{what}: max |kernel - live| = {worst:.3e} > {atol:.0e}"


def random_walk_closes(seed: int, n: int = 600) -> np.ndarray:
    """Synthetic closes at three realistic price scales: ~100, gold (~4,000, 3 dp), bitcoin (~74,000, 2 dp)."""
    rng = np.random.default_rng(seed)
    kind = seed % 3
    if kind == 0:
        return 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.002, n)))
    if kind == 1:
        return np.round(4000.0 + np.cumsum(rng.normal(0.0, 1.5, n)), 3)
    return np.round(74000.0 + np.cumsum(rng.normal(0.0, 40.0, n)), 2)


def fixture_m1_closes(fixture_store, symbol: str, n: int) -> np.ndarray:
    span = store.data_span(symbol, fixture_store)
    m1 = store.load_m1(symbol, span[0], span[1] + pd.Timedelta(minutes=1), fixture_store)
    return np.ascontiguousarray(m1["c"][-n:], dtype=np.float64)


def forming_bar_values(closed, price, rsi_len, mf, ms, msig):
    """
    The forming-bar update exactly as ``run_kernel`` performs it (kernels.py, the block
    "indicators on the forming bar"): bar ``k = len(closed)`` is still forming at ``price``;
    everything else comes from the recursion states left by closed bar ``k - 1``.

    Returns (rsi, macd, signal, hist).
    """
    C = np.ascontiguousarray(closed, dtype=np.float64)
    AG, AL, _rsi, EF, ES, SG, _hist = K.indicator_arrays(C, int(rsi_len), int(mf), int(ms), int(msig))
    k = len(C)
    a_rsi = 1.0 / rsi_len
    a_f, a_s, a_sg = 2.0 / (mf + 1.0), 2.0 / (ms + 1.0), 2.0 / (msig + 1.0)
    # RSI
    d = price - C[k - 1]
    g = d if d > 0.0 else 0.0
    l = -d if d < 0.0 else 0.0
    ag = a_rsi * g + (1.0 - a_rsi) * AG[k - 1]
    al = a_rsi * l + (1.0 - a_rsi) * AL[k - 1]
    if al == 0.0 or ag != ag or al != al:
        rsi = 100.0
    else:
        rsi = 100.0 - (100.0 / (1.0 + ag / al))
    # MACD
    ef = a_f * price + (1.0 - a_f) * EF[k - 1]
    es = a_s * price + (1.0 - a_s) * ES[k - 1]
    macd = ef - es
    sg1 = a_sg * macd + (1.0 - a_sg) * SG[k - 1]
    return rsi, macd, sg1, macd - sg1


# ───────────────────────────── closed-bar arrays ─────────────────────────────

@pytest.mark.parametrize("params", PARAM_SETS, ids=PARAM_IDS)
@pytest.mark.parametrize("seed", range(6))
def test_closed_bar_rsi_and_macd_match_live_on_random_walks(seed, params):
    """
    Protects: the RSI (Wilder RMA, SMA-seeded) and MACD (SMA-seeded EMAs) the live bot
    computes with ``Indicator.calculate_rsi`` / ``calculate_macd``. The kernel must give
    the same value on every bar of a 600-bar history -- including the warm-up bars the
    live code fills with RSI 100 and leaves NaN for MACD -- for the live lengths and for
    any other lengths a parameter sweep may try.
    """
    closes = random_walk_closes(seed)
    k, live = kernel_arrays(closes, *params), live_arrays(closes, *params)
    for name in ("rsi", "macd", "signal", "hist"):
        assert_same(k[name], live[name], f"{name} {params} seed {seed}")


@pytest.mark.parametrize("params", PARAM_SETS, ids=PARAM_IDS)
@pytest.mark.parametrize("symbol", SYMBOLS)
def test_closed_bar_rsi_and_macd_match_live_on_real_m1_closes(fixture_store, symbol, params):
    """
    Protects: the same equality on REAL Exness M1 closes (flat stretches, gaps over the
    weekend, 2-3 decimal prices) -- the data the backtest actually runs on.
    """
    closes = fixture_m1_closes(fixture_store, symbol, 1500)
    assert len(closes) == 1500
    k, live = kernel_arrays(closes, *params), live_arrays(closes, *params)
    for name in ("rsi", "macd", "signal", "hist"):
        assert_same(k[name], live[name], f"{symbol} {name} {params}")


@pytest.mark.parametrize("params", PARAM_SETS, ids=PARAM_IDS)
def test_recursion_states_match_the_live_moving_averages(params):
    """
    Protects: the recursion STATES the forming-bar update starts from (average gain / loss,
    fast / slow EMA, signal line). They must be the live ``Indicator._ma`` series bar for
    bar, otherwise every intrabar RSI / MACD value would drift from the live one.
    """
    rsi_len, mf, ms, msig = params
    closes = random_walk_closes(11)
    k = kernel_arrays(closes, *params)
    s = pd.Series(closes)
    delta = s.diff()
    assert_same(k["AG"], IND._ma(delta.clip(lower=0), rsi_len, "RMA").to_numpy(), "average gain")
    assert_same(k["AL"], IND._ma((-delta).clip(lower=0), rsi_len, "RMA").to_numpy(), "average loss")
    assert_same(k["EF"], IND._ma(s, mf, "EMA").to_numpy(), "fast EMA")
    assert_same(k["ES"], IND._ma(s, ms, "EMA").to_numpy(), "slow EMA")


@pytest.mark.parametrize("params", PARAM_SETS, ids=PARAM_IDS)
def test_short_histories_match_live_bar_for_bar(params):
    """
    Protects: the warm-up edge. With fewer bars than an indicator needs the live code
    returns RSI 100 (``fillna(100)``) and NaN MACD; the kernel must switch from
    "undefined" to "defined" on exactly the same bar for every history length.
    """
    base = random_walk_closes(4, 80)
    for n in range(0, 81):
        closes = base[:n]
        k, live = kernel_arrays(closes, *params), live_arrays(closes, *params)
        for name in ("rsi", "macd", "signal", "hist"):
            assert_same(k[name], live[name], f"{name} {params} with {n} bars")


@pytest.mark.parametrize("shape", ["flat", "rising", "falling", "flat_then_rising", "staircase"])
def test_degenerate_price_paths_match_live(shape):
    """
    Protects: the RSI division edge cases. No losses -> RSI 100 (live: avg_loss 0 gives
    inf or NaN, then fillna(100)); no gains -> RSI 0; a dead-flat market -> RSI 100.
    These happen for real on quiet M1 bars and right after the weekend gap.
    """
    n = 120
    closes = {
        "flat": np.full(n, 4000.0),
        "rising": 4000.0 + 0.25 * np.arange(n),
        "falling": 4000.0 - 0.25 * np.arange(n),
        "flat_then_rising": np.r_[np.full(60, 4000.0), 4000.0 + 0.5 * np.arange(60)],
        "staircase": 4000.0 + np.repeat(np.arange(n // 4), 4) * 0.1,
    }[shape]
    for params in PARAM_SETS:
        k, live = kernel_arrays(closes, *params), live_arrays(closes, *params)
        for name in ("rsi", "macd", "signal", "hist"):
            assert_same(k[name], live[name], f"{shape} {name} {params}")
    live14 = live_arrays(closes, 14, 12, 26, 9)["rsi"]
    if shape in ("flat", "rising"):
        assert np.all(live14 == 100.0)
    if shape == "falling":
        assert np.all(live14[14:] == 0.0) and np.all(live14[:14] == 100.0)


# ───────────────────────────── the forming-bar update ─────────────────────────────

def _min_history(params) -> int:
    """Shortest closed history for which every recursion state of bar k-1 is defined."""
    rsi_len, mf, ms, msig = params
    return max(rsi_len + 1, max(mf, ms) + msig - 1)


def test_forming_bar_update_matches_live_on_history_plus_price():
    """
    Protects: the values the live bot acts on. On every poll it appends the current Bid
    as the close of the forming bar and recomputes RSI / MACD over the whole window. The
    kernel instead advances the recursions by one step from the last CLOSED bar. For 600
    random (history, new price) cases -- prices that barely move, jump, or do not move at
    all -- RSI, the MACD line, the signal line and the histogram must equal the live
    functions evaluated on history + [price] to 1e-9.
    """
    rng = np.random.default_rng(20261114)
    n_cases = 0
    for case in range(600):
        params = PARAM_SETS[case % len(PARAM_SETS)]
        closes = random_walk_closes(int(rng.integers(0, 10_000)), 600)
        k = int(rng.integers(_min_history(params), 600))
        hist_closes = closes[:k]
        last = hist_closes[-1]
        scale = float(np.std(np.diff(closes))) or 1.0
        shock = rng.choice([0.0, 0.05, 1.0, 5.0, 40.0]) * scale * rng.normal()
        price = float(last + shock)
        rsi, macd, sig, hst = forming_bar_values(hist_closes, price, *params)
        live = live_arrays(np.append(hist_closes, price), *params)
        tag = f"case {case} params {params} k={k} shock={shock:.4g}"
        assert abs(rsi - live["rsi"][-1]) <= TOL, f"RSI {tag}: {rsi} vs live {live['rsi'][-1]}"
        assert abs(macd - live["macd"][-1]) <= TOL, f"MACD {tag}"
        assert abs(sig - live["signal"][-1]) <= TOL, f"signal {tag}"
        assert abs(hst - live["hist"][-1]) <= TOL, f"hist {tag}"
        # the signal line's sign picks the MACD pivot side in the live loop
        assert np.sign(sig) == np.sign(live["signal"][-1]), f"signal sign {tag}"
        n_cases += 1
    assert n_cases == 600


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_forming_bar_update_matches_live_on_real_closes_and_intrabar_prices(fixture_store, symbol):
    """
    Protects: the same forming-bar equality on real bars, with the forming price walking
    through the real Bid range of the next bar (its open, high, low and close) -- what a
    1 s poll sees inside one M1 bar.
    """
    span = store.data_span(symbol, fixture_store)
    m1 = store.load_m1(symbol, span[0], span[1] + pd.Timedelta(minutes=1), fixture_store)
    c = np.ascontiguousarray(m1["c"], dtype=np.float64)
    rng = np.random.default_rng(7)
    checked = 0
    for k in rng.integers(700, len(c) - 1, 60):
        k = int(k)
        closed = c[k - 600:k]
        for price in (m1["o"][k], m1["h"][k], m1["l"][k], m1["c"][k]):
            rsi, macd, sig, hst = forming_bar_values(closed, float(price), 14, 12, 26, 9)
            live = live_arrays(np.append(closed, price), 14, 12, 26, 9)
            assert abs(rsi - live["rsi"][-1]) <= TOL
            assert abs(macd - live["macd"][-1]) <= TOL
            assert abs(sig - live["signal"][-1]) <= TOL
            assert abs(hst - live["hist"][-1]) <= TOL
            checked += 1
    assert checked == 240


def test_live_500_bar_window_equals_the_full_history_recursion():
    """
    Protects: an assumption the fast engine relies on. The live bot re-seeds RSI / MACD
    from scratch on the last 500 bars every poll; the kernel carries one recursion over
    the whole prepared history (600 warm-up bars plus the test window). The two differ
    only by the seed's decayed weight, which must be far below the 1e-9 tolerance --
    otherwise long backtests would slowly drift away from live values.
    """
    closes = random_walk_closes(2, 3000)       # bitcoin-like scale, the worst case in absolute terms
    full = kernel_arrays(closes, 14, 12, 26, 9)
    for end in (500, 777, 1500, 2999):
        live = live_arrays(closes[end - 499:end + 1], 14, 12, 26, 9)   # the 500 bars ending at `end`
        assert abs(full["rsi"][end] - live["rsi"][-1]) <= TOL
        assert abs(full["hist"][end] - live["hist"][-1]) <= TOL
        assert abs(full["signal"][end] - live["signal"][-1]) <= TOL


# ───────────────────────────── pivots: pivot_arrays + slope_sign ─────────────────────────────

def live_sign(v: np.ndarray, k: int, x: float, lookback: int, width: int, ob, os_, side) -> int:
    """What the live bot reads: the pivot slope sign of (closed bars v[:k], forming value x), 500-bar window."""
    series = np.append(v[:k], x)[-500:]
    return IND.latest_pivot_slope(series, lookback=lookback, width=width,
                                  ob_level=ob, os_level=os_, side=side)["sign"]


def kernel_sign(v, piv, k: int, x: float, lookback: int, width: int, side, base: int = 0) -> int:
    ph, pl, ch, cl = piv
    return int(K.slope_sign(v, ph, pl, ch, cl, int(base), int(k), float(x), int(width), int(lookback),
                            bool(side != "low"), bool(side != "high")))


def kernel_pivots(v: np.ndarray, width: int, ob, os_):
    use_band = ob is not None
    return K.pivot_arrays(v, int(width), bool(use_band), float(ob) if use_band else 0.0,
                          float(os_) if use_band else 0.0)


def _rsi_like(rng, n: int) -> np.ndarray:
    """A bounded 0..100 series with turns in and out of the overbought / oversold zones."""
    kind = int(rng.integers(0, 4))
    if kind == 0:      # mean-reverting around 50
        phi, sd = rng.uniform(0.6, 0.98), rng.uniform(2.0, 12.0)
        x = np.empty(n)
        x[0] = rng.uniform(20, 80)
        e = rng.normal(0.0, sd, n)
        for i in range(1, n):
            x[i] = 50.0 + phi * (x[i - 1] - 50.0) + e[i]
    elif kind == 1:    # random walk (clipped -> plateaus at 0 / 100)
        x = rng.uniform(20, 80) + np.cumsum(rng.normal(0.0, rng.uniform(1.0, 9.0), n))
    elif kind == 2:    # oscillation + noise: clean, regular pivots
        t = np.arange(n)
        x = (50.0 + rng.uniform(10, 45) * np.sin(2 * np.pi * t / rng.uniform(5, 40) + rng.uniform(0, 6.3))
             + rng.normal(0.0, rng.uniform(0.0, 6.0), n))
    else:              # a real RSI of a random walk, from the live indicator itself
        closes = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n + 30))
        x = IND.calculate_rsi(pd.Series(closes), length=int(rng.integers(3, 15))).to_numpy()[30:]
    return np.clip(x, 0.0, 100.0)


def _hist_like(rng, n: int) -> np.ndarray:
    """A zero-centred oscillating series at an arbitrary scale (MACD histogram)."""
    scale = 10.0 ** rng.uniform(-3, 1.7)
    kind = int(rng.integers(0, 3))
    if kind == 0:
        phi = rng.uniform(0.5, 0.97)
        x = np.empty(n)
        x[0] = rng.normal()
        e = rng.normal(0.0, 1.0, n)
        for i in range(1, n):
            x[i] = phi * x[i - 1] + e[i]
    elif kind == 1:
        t = np.arange(n)
        x = np.sin(2 * np.pi * t / rng.uniform(5, 40) + rng.uniform(0, 6.3)) + rng.normal(0.0, rng.uniform(0, 0.5), n)
    else:              # a real MACD histogram of a random walk, from the live indicator
        closes = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n + 40))
        x = IND.calculate_macd(pd.Series(closes), fast=5, slow=11, signal=4)["hist"].to_numpy()[40:]
        return x * scale
    return x * scale


def _random_series(rng):
    """One closed-bar series plus the band it is read with. Returns (v, ob, os, rsi_like)."""
    n = int(rng.choice([40, 60, 90, 130, 560, 700], p=[0.3, 0.3, 0.2, 0.14, 0.03, 0.03]))
    rsi_like = bool(rng.random() < 0.6)
    v = _rsi_like(rng, n) if rsi_like else _hist_like(rng, n)
    if rng.random() < 0.45:                       # quantise -> equal neighbours, exact ties with the band
        v = np.round(v, 1) if rsi_like else np.round(v / (np.nanstd(v) + 1e-12), 1) * (np.nanstd(v) + 1e-12)
    if rng.random() < 0.15:                       # explicit plateaus
        for _ in range(int(rng.integers(1, 5))):
            i = int(rng.integers(0, n - 3))
            v[i:i + int(rng.integers(2, 5))] = v[i]
    if rng.random() < 0.3:                        # NaN warm-up prefix (the MACD histogram starts with 33 NaNs)
        v[:int(rng.integers(1, min(45, n - 2)))] = np.nan
    ob = os_ = None
    if rng.random() < (0.6 if rsi_like else 0.15):
        ob, os_ = float(rng.uniform(55, 70)), float(rng.uniform(30, 45))
        if rng.random() < 0.5:                    # integer levels meet quantised values exactly
            ob, os_ = float(round(ob)), float(round(os_))
    return np.ascontiguousarray(v, dtype=np.float64), ob, os_, rsi_like


def _forming_value(rng, v: np.ndarray, k: int, width: int, rsi_like: bool) -> float:
    """A forming-bar value: realistic, or deliberately tied with a pivot candidate, or extreme."""
    r = rng.random()
    finite = v[np.isfinite(v)]
    spread = float(np.std(finite)) if len(finite) > 1 else 1.0
    prev = v[k - 1] if k > 0 and np.isfinite(v[k - 1]) else (float(np.mean(finite)) if len(finite) else 0.0)
    if r < 0.35:
        x = float(v[k]) if np.isfinite(v[k]) else prev            # the value the bar really closes at
    elif r < 0.65:
        x = prev + rng.normal(0.0, 0.6 * spread + 1e-9)           # an intrabar wiggle
    elif r < 0.80 and k - width >= 0:
        x = float(v[k - width])                                    # tie with the newest pivot candidate
    elif r < 0.90 and k > 0:
        x = float(v[int(rng.integers(max(0, k - 25), k))])          # tie with some bar in the window
    elif r < 0.97:
        x = float(rng.choice([0.0, 100.0]) if rsi_like else rng.normal(0.0, 5.0 * spread + 1e-9))
    else:
        x = float("nan")                                           # the live code returns "no direction"
    if rsi_like and x == x:
        x = float(min(100.0, max(0.0, x)))
    return x


def test_pivot_slope_sign_equals_live_latest_pivot_slope_property():
    """
    THE independent proof of the pivot logic.

    Protects: every slope sign the strategy scores. Live, the sign is
    ``Indicator.latest_pivot_slope(series)['sign']`` on (closed bars + the forming value):
    scan back from the newest confirmable bar, take the FIRST pivot (strictly above /
    below ``width`` neighbours on both sides, inside the OB/OS band if one is given, on
    the side the MACD signal line selects) and compare the current value with it.

    The kernel splits that into ``pivot_arrays`` (pre-computed once per timeframe over the
    WHOLE closed array, future bars included) and ``slope_sign`` (a constant-time lookup
    at poll time). More than 30,000 random cases over RSI-like series in 0..100 and
    MACD-histogram-like series around 0 -- widths 1..4, lookbacks 6..30, with and without
    OB/OS bands (ob 55..70, os 30..45), side None / 'high' / 'low', plateaus and ties
    (series quantised to one decimal, forming values tied with a pivot), NaN prefixes,
    NaN forming values, series longer than the live 500-bar window -- must agree in
    EVERY case. Because ``pivot_arrays`` sees the bars after K as well, agreement also
    shows the lookup never uses them.
    """
    rng = np.random.default_rng(424242)
    n_cases = 0
    n_nonzero = 0
    seen = {"band": 0, "noband": 0, "high": 0, "low": 0, "both": 0, "nan_x": 0, "long": 0,
            "width": set(), "lookback": set(), "signs": set()}
    mismatches = []
    for _series in range(700):
        v, ob, os_, rsi_like = _random_series(rng)
        n = len(v)
        width = int(rng.integers(1, 5))
        piv = kernel_pivots(v, width, ob, os_)
        seen["band" if ob is not None else "noband"] += 1
        seen["width"].add(width)
        for _case in range(46):
            k = int(rng.integers(0, n)) if rng.random() < 0.25 else int(rng.integers(max(0, n - 60), n))
            if n > 500 and rng.random() < 0.7:
                k = int(rng.integers(500, n))                 # beyond the live 500-bar fetch
                seen["long"] += 1
            lookback = int(rng.integers(6, 31))
            side = (None, "high", "low")[int(rng.integers(0, 3))]
            x = _forming_value(rng, v, k, width, rsi_like)
            want = live_sign(v, k, x, lookback, width, ob, os_, side)
            got = kernel_sign(v, piv, k, x, lookback, width, side)
            n_cases += 1
            n_nonzero += want != 0
            seen["both" if side is None else side] += 1
            seen["nan_x"] += x != x
            seen["lookback"].add(lookback)
            seen["signs"].add(want)
            if got != want:
                mismatches.append(dict(n=n, k=k, x=x, width=width, lookback=lookback, ob=ob, os=os_,
                                       side=side, live=want, kernel=got, tail=v[max(0, k - 8):k].tolist()))
    assert not mismatches, f"{len(mismatches)} of {n_cases} cases differ from the live code; first: {mismatches[0]}"
    # the property was really exercised
    assert n_cases >= 30_000
    assert n_nonzero >= 0.4 * n_cases, "too few cases with a pivot in the window"
    assert seen["signs"] == {-1, 0, 1}
    assert seen["width"] == {1, 2, 3, 4} and seen["lookback"] == set(range(6, 31))
    assert min(seen["band"], seen["noband"]) >= 150
    assert min(seen["high"], seen["low"], seen["both"]) >= 8_000
    assert seen["nan_x"] >= 300 and seen["long"] >= 500


def test_pivot_slope_sign_live_settings_on_real_indicator_series(fixture_store):
    """
    Protects: the exact live configuration (PEAK_LOOKBACK 20, PIVOT_WIDTH 2, RSI band
    60 / 40, MACD side from the signal line) on real RSI(14) and MACD(12,26,9) histogram
    series of both fixture symbols, at every bar and for several forming values per bar.
    """
    lookback, width = live_constants.PEAK_LOOKBACK, live_constants.PIVOT_WIDTH
    ob, os_ = float(live_constants.RSI_PEAK_OB), float(live_constants.RSI_PEAK_OS)
    rng = np.random.default_rng(99)
    n_cases = 0
    for symbol in SYMBOLS:
        closes = fixture_m1_closes(fixture_store, symbol, 900)
        arr = kernel_arrays(closes, 14, 12, 26, 9)
        rsi, hist = np.ascontiguousarray(arr["rsi"]), np.ascontiguousarray(arr["hist"])
        piv_r = kernel_pivots(rsi, width, ob, os_)
        piv_m = kernel_pivots(hist, width, None, None)
        for k in range(40, 900):
            for x_r, x_m in ((rsi[k], hist[k]),
                             (float(np.clip(rsi[k - 1] + rng.normal(0, 4), 0, 100)),
                              float(hist[k - 1] + rng.normal(0, np.nanstd(hist) * 0.5)))):
                assert kernel_sign(rsi, piv_r, k, x_r, lookback, width, None) == \
                    live_sign(rsi, k, x_r, lookback, width, ob, os_, None)
                for side in (None, "high", "low"):
                    assert kernel_sign(hist, piv_m, k, x_m, lookback, width, side) == \
                        live_sign(hist, k, x_m, lookback, width, None, None, side)
                n_cases += 4
    assert n_cases == 2 * 860 * 2 * 4


def test_pivot_lookup_never_reads_bars_at_or_after_the_forming_bar():
    """
    Protects: NO LOOKAHEAD in the pivot bookkeeping. ``pivot_arrays`` is computed over the
    whole series, so at forming bar K it holds entries derived from bars that have not
    happened yet. Replacing everything from bar K onwards with garbage must not change
    the sign read at K.
    """
    rng = np.random.default_rng(31337)
    n_cases = 0
    for _ in range(150):
        v, ob, os_, rsi_like = _random_series(rng)
        n = len(v)
        width = int(rng.integers(1, 5))
        piv = kernel_pivots(v, width, ob, os_)
        for _case in range(12):
            k = int(rng.integers(max(0, n - 60), n))
            poisoned = v.copy()
            poisoned[k:] = rng.choice([np.nan, 1e9, -1e9, 0.0, 50.0], size=n - k)
            piv_p = kernel_pivots(poisoned, width, ob, os_)
            lookback = int(rng.integers(6, 31))
            side = (None, "high", "low")[int(rng.integers(0, 3))]
            x = _forming_value(rng, v, k, width, rsi_like)
            assert kernel_sign(poisoned, piv_p, k, x, lookback, width, side) == \
                kernel_sign(v, piv, k, x, lookback, width, side)
            n_cases += 1
    assert n_cases == 1800


def test_slope_sign_reads_one_timeframe_inside_the_flattened_arrays():
    """
    Protects: the layout ``Prepared.flat`` hands to the kernel. All timeframes are
    concatenated into one array and each is addressed by its offset (``base``); pivot
    indices stay relative to the timeframe. Reading timeframe #2 through its offset must
    give exactly what it gives on its own (a wrong offset would silently score one
    timeframe with another's pivots).
    """
    rng = np.random.default_rng(5)
    for _ in range(40):
        a, ob, os_, _ = _random_series(rng)
        b = _rsi_like(rng, int(rng.integers(40, 120)))
        width = int(rng.integers(1, 5))
        pa, pb = kernel_pivots(a, width, ob, os_), kernel_pivots(b, width, ob, os_)
        flat_v = np.ascontiguousarray(np.concatenate([a, b]))
        flat_p = tuple(np.ascontiguousarray(np.concatenate([x, y])) for x, y in zip(pa, pb))
        for _case in range(25):
            k = int(rng.integers(0, len(b)))
            x = float(np.clip(50 + rng.normal(0, 25), 0, 100))
            lookback = int(rng.integers(6, 31))
            side = (None, "high", "low")[int(rng.integers(0, 3))]
            assert kernel_sign(flat_v, flat_p, k, x, lookback, width, side, base=len(a)) == \
                kernel_sign(b, pb, k, x, lookback, width, side) == \
                live_sign(b, k, x, lookback, width, ob, os_, side)


def test_pivot_slope_sign_with_lookback_not_larger_than_width():
    """
    Protects: sweeps over ``peak_lookback`` / ``pivot_width``. For a degenerate pair
    (lookback <= width) the live code finds no pivot at all, so a live bot configured
    that way would never trade; the backtest must say the same.
    """
    rng = np.random.default_rng(8)
    bad = 0
    for _ in range(60):
        v = np.ascontiguousarray(np.clip(50 + np.cumsum(rng.normal(0, 6, 40)), 0, 100))
        for width in (1, 2, 3, 4):
            piv = kernel_pivots(v, width, None, None)
            for lookback in range(1, width + 1):
                for k in range(len(v)):
                    x = float(np.clip(v[k - 1] + rng.normal(0, 6), 0, 100)) if k else 50.0
                    bad += kernel_sign(v, piv, k, x, lookback, width, None) != \
                        live_sign(v, k, x, lookback, width, None, None, None)
    assert bad == 0


# ───────────────────────────── through the real kernel ─────────────────────────────

def _live_view_of_poll(prep: fast.Prepared, cfg: BacktestConfig, slope_tfs, t_poll: int):
    """
    What the live loop (app.py: process_symbol) computes at poll time ``t_poll`` from the
    same bars the kernel was given: {TIMEFRAME_x: rsi}, {tf: {'rsi': slope, 'macd': slope}}.
    Mirrors app.py line for line: 500 bars per timeframe with the forming bar closed at the
    latest Bid, RSI on all of them, MACD + the two pivot slopes on the slope timeframes.
    """
    ptr = int(np.searchsorted(prep.t_ms, t_poll, side="right")) - 1
    bid = float(prep.bid[ptr])
    rsi_mtf, slopes = {}, {}
    for tf in prep.tfs:
        k = int(np.searchsorted(prep.start_row[tf], ptr, side="right")) - 1      # the forming bar
        closes = pd.Series(np.append(prep.closes[tf][:k], bid)[-live_constants.RSI_CANDLE_COUNT:])
        rsi_s = IND.calculate_rsi(closes, length=live_constants.RSI_LENGTH, ma_type=live_constants.RSI_MA_TYPE)
        rsi_mtf["TIMEFRAME_" + tf] = float(rsi_s.iloc[-1])
        if tf in slope_tfs:
            macd_df = IND.calculate_macd(closes, fast=live_constants.MACD_FAST, slow=live_constants.MACD_SLOW,
                                         signal=live_constants.MACD_SIGNAL)
            rsi_slope = IND.latest_pivot_slope(rsi_s, lookback=live_constants.PEAK_LOOKBACK,
                                               width=live_constants.PIVOT_WIDTH,
                                               ob_level=live_constants.RSI_PEAK_OB,
                                               os_level=live_constants.RSI_PEAK_OS)
            sig = float(macd_df["signal"].iloc[-1])
            side = "high" if sig > 0 else ("low" if sig < 0 else None)
            macd_slope = IND.latest_pivot_slope(macd_df["hist"], lookback=live_constants.PEAK_LOOKBACK,
                                                width=live_constants.PIVOT_WIDTH, side=side)
            slopes[tf] = {"rsi": rsi_slope, "macd": macd_slope}
    return bid, rsi_mtf, slopes


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_kernel_polls_match_live_indicators_and_strategy_on_real_ticks(symbol, live_cfg, prepared, live_variant):
    """
    Protects: the whole decision the kernel takes on a poll, against the live code, on
    real ticks -- without the reference engine in between.

    The fast engine is run with its per-poll trace on. For a sample of 400+ polls per
    window (every poll that produced a signal, the first poll of every minute and a
    regular sample of the rest) the test rebuilds what ``app.py`` would have fetched at
    that instant from the prepared bars, runs the LIVE ``Indicator`` and the LIVE
    ``Strategy.calculate_signal`` on it with the kernel's own position / profit / unit /
    cooldown state, and requires:
      * the same Bid, and the same forming-bar RSI on all five ladder timeframes (1e-9),
      * the same OPEN / FORCE-CLOSE (/ BOOK) scores,
      * the same signal (BUY, SELL, CLOSE_*, *_MORE or nothing).
    """
    cfg = live_cfg(symbol)
    prep = prepared(symbol, mode="ticks")
    res = fast.run(cfg, prep, trace=True)
    tr = res.trace
    assert len(tr) > 2000 and res.counters["trace_overflow"] == 0
    slope_tfs = {t.replace("TIMEFRAME_", "") for t in live_constants.SLOPE_TIMEFRAMES}
    assert slope_tfs <= set(prep.tfs)
    strat = Strategy()

    t_all = tr[:, K.T_T].astype(np.int64)
    pick = (tr[:, K.T_SIGNAL] != 0) | (t_all % 60_000 == 0) | (np.arange(len(tr)) % 8 == 0)
    rows = np.flatnonzero(pick)
    assert len(rows) >= 300
    signals_checked = set()
    for i in rows:
        row = tr[i]
        bid, rsi_mtf, slopes = _live_view_of_poll(prep, cfg, slope_tfs, int(row[K.T_T]))
        when = store.ms_to_dt(int(row[K.T_T]))
        assert bid == row[K.T_BID], f"{when}: kernel read Bid {row[K.T_BID]}, the latest tick is {bid}"
        for q, tf in enumerate(cfg.ladder_tfs):
            live_rsi = rsi_mtf["TIMEFRAME_" + tf]
            assert abs(live_rsi - row[K.T_RSI0 + q]) <= TOL, \
                f"{when}: RSI {tf} live {live_rsi!r} vs kernel {row[K.T_RSI0 + q]!r}"
        n_signed = int(row[K.T_NPOS])
        units = int(row[K.T_UNITS])
        pos = {"count": abs(n_signed), "total_profit": float(row[K.T_PROFIT]), "first_profit": 0.0,
               "total_volume": 0.0}
        buy_sig, sell_sig, an = strat.calculate_signal(
            None, pos if n_signed > 0 else None, pos if n_signed < 0 else None, units,
            close_threshold=units, rsi_value=rsi_mtf["TIMEFRAME_M1"], rsi_mtf=rsi_mtf, slopes=slopes,
            entry_allowed=bool(row[K.T_ENTRY_ALLOWED]))
        assert an["open_score"] == row[K.T_OPEN_SCORE], f"{when}: open score live {an['open_score']}"
        assert an["fc_score"] == row[K.T_FC_SCORE], f"{when}: force-close score live {an['fc_score']}"
        if live_variant == "netting":
            assert an["book_score"] == row[K.T_BOOK_SCORE], f"{when}: book score live {an['book_score']}"
        live_code = buy_sig.value or sell_sig.value
        assert live_code == int(row[K.T_SIGNAL]), \
            f"{when}: live signal {buy_sig.name}/{sell_sig.name} vs kernel {fast.SIGNAL_NAMES[int(row[K.T_SIGNAL])]}"
        signals_checked.add(live_code)
    # the sample covered entries and exits, not only quiet polls
    assert 0 in signals_checked and (signals_checked & {1, 2}) and (signals_checked & {3, 4})


def test_forming_bar_rsi_matches_live_from_a_cold_start():
    """
    Protects: runs that start where the tick store starts. With no warm-up history the
    first bars of every timeframe are computed from whatever exists; the kernel's
    forming-bar RSI must still be the live value on every poll (the live code yields 100
    until ``rsi_length`` deltas exist and a real number from then on).
    """
    rng = np.random.default_rng(7)
    start = store.to_ms("2026-11-11 10:00")
    n_sec = 25 * 60
    t_ms = start + np.arange(n_sec, dtype=np.int64) * 1000 + rng.integers(0, 900, n_sec)
    bid = np.round(4000.0 + np.cumsum(rng.normal(0.0, 0.15, n_sec)), 3)
    ask = bid + 0.2
    ids, first, closes = fast._window_bars(t_ms, bid, TF_SECONDS["M1"])
    prep = fast.Prepared("XAUUSDm", start, start + n_sec * 1000, "ticks", t_ms, bid, ask, ["M1"],
                         {"M1": closes.astype(np.float64)}, {"M1": ids * 60}, {"M1": 0}, {"M1": first})
    cfg = BacktestConfig(symbol="XAUUSDm", start="2026-11-11 10:00", end="2026-11-11 10:25",
                         open_weights={"M1": 1}, fc_weights={"M1": 1}, ladder_tfs=["M1"], window_enabled=False)
    tr = fast.run(cfg, prep, trace=True).trace
    assert len(tr) > 1400
    worst = 0.0
    for row in tr:
        ptr = int(np.searchsorted(t_ms, int(row[K.T_T]), side="right")) - 1
        k = int(np.searchsorted(first, ptr, side="right")) - 1
        live = float(IND.calculate_rsi(pd.Series(np.append(closes[:k], bid[ptr])), length=14).iloc[-1])
        worst = max(worst, abs(live - row[K.T_RSI0]))
    assert worst <= TOL
