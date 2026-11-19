"""
Ladder study: closed-bar indicator series for the engine (third-indicator ladder triggers, add gates, entry
confirmations, ATR for sizing, the abnormal-day rule).

Bars come from the stored M1 bid bars (the MT5 convention), aggregated on each timeframe's MT5 grid
(``ladder_tfs``; W1 opens on Sunday 00:00). The value of a bar is in force from the bar's CLOSE time
(open + length) on, so a decision at time T only ever reads bars that closed by T. Element i of every indicator
uses bars 0..i only. The ``research/external.py`` helpers are reused where they exist (``wilder``,
``wilder_rsi``, ``true_range``, ``wilder_atr``, ``_supertrend``).

A series is ``(t_ms, values)``: from ``t_ms[i]`` on the value is ``values[i]``.
* trigger series: +1 a buy add is allowed (oversold side), -1 a sell add, 0 neither;
* mask series (gates): bit 0 buys allowed, bit 1 sells allowed (3 both, 0 none). A value not yet known is 0.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..config import TF_SECONDS
from ..data import store
from ..engine import kernels as K
from . import ladder_tfs as LT
from . import external as X

CACHE_DIR = Path(os.environ.get("LADDER_CACHE_DIR", os.path.join(tempfile.gettempdir(), "alcadeias_ladder_cache")))
Series = Tuple[np.ndarray, np.ndarray]

_M1: Dict[str, dict] = {}
_BARS: Dict[tuple, dict] = {}
_SER: Dict[str, Series] = {}


# ───────────────────────────── bars ─────────────────────────────

def m1_history(symbol: str, store_dir: Path = store.DEFAULT_STORE_DIR) -> dict:
    """Every stored M1 bid bar of the symbol: t (open, epoch s), o, h, l, c (cached on disk and in memory)."""
    if symbol in _M1:
        return _M1[symbol]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"m1_{symbol}.npz"
    if p.exists():
        with np.load(p) as z:
            d = {k: z[k] for k in ("t", "o", "h", "l", "c")}
    else:
        span = store.data_span(symbol, store_dir)
        m1 = store.load_m1(symbol, span[0], span[1] + pd.Timedelta(days=1), store_dir)
        d = {"t": np.asarray(m1["t"], np.int64), **{k: np.asarray(m1[k], np.float64) for k in ("o", "h", "l", "c")}}
        np.savez(p, **d)
    _M1[symbol] = d
    return d


def bars(symbol: str, tf: str) -> dict:
    """OHLC bars of ``tf`` on its MT5 grid, plus ``tc_ms`` = the time each bar's values come into force (its close)."""
    key = (symbol, tf)
    if key not in _BARS:
        b = LT.resample_ohlc(m1_history(symbol), tf)
        b["tc_ms"] = (b["t"] + TF_SECONDS[tf]) * 1000
        _BARS[key] = b
    return _BARS[key]


# ───────────────────────────── indicators (closed bars; element i uses bars 0..i) ─────────────────────────────

def sma(x: np.ndarray, n: int) -> np.ndarray:
    return X.sma(x, n)


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """EMA (alpha 2/(n+1)) seeded with the simple mean of the first n values, as the bot's MACD seeds its EMAs."""
    x = np.asarray(x, np.float64)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    return _ema_seeded(x, n, out)


@njit(cache=True)
def _ema_seeded(x, n, out):
    a = 2.0 / (n + 1.0)
    s = 0.0
    for i in range(n):
        s += x[i]
    v = s / n
    out[n - 1] = v
    for i in range(n, x.shape[0]):
        v = a * x[i] + (1.0 - a) * v
        out[i] = v
    return out


@njit(cache=True)
def _mean_abs_dev(x, n):
    out = np.full(x.shape[0], np.nan)
    for i in range(n - 1, x.shape[0]):
        m = 0.0
        for j in range(i - n + 1, i + 1):
            m += x[j]
        m /= n
        d = 0.0
        for j in range(i - n + 1, i + 1):
            d += abs(x[j] - m)
        out[i] = d / n
    return out


def stoch_k(h, l, c, n: int = 14, smooth: int = 3) -> np.ndarray:
    """Slow %K: SMA(smooth) of 100 (C - LL_n) / (HH_n - LL_n); 50 where the range is zero."""
    hh, ll = X.roll_max(h, n), X.roll_min(l, n)
    rng = hh - ll
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where(rng > 0, 100.0 * (c - ll) / rng, 50.0)
    raw[~np.isfinite(hh)] = np.nan
    return X.sma(raw, smooth) if smooth > 1 else raw


def williams_r(h, l, c, n: int = 14) -> np.ndarray:
    hh, ll = X.roll_max(h, n), X.roll_min(l, n)
    rng = hh - ll
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(rng > 0, -100.0 * (hh - c) / rng, -50.0)
    out[~np.isfinite(hh)] = np.nan
    return out


def cci(h, l, c, n: int = 20) -> np.ndarray:
    tp = (np.asarray(h, np.float64) + np.asarray(l, np.float64) + np.asarray(c, np.float64)) / 3.0
    ma = X.sma(tp, n)
    md = _mean_abs_dev(tp, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(md > 0, (tp - ma) / (0.015 * md), 0.0 * md)


def bb_pctb(c, n: int = 20, k: float = 2.0) -> np.ndarray:
    s = pd.Series(np.asarray(c, np.float64))
    ma = s.rolling(n, min_periods=n).mean().to_numpy()
    sd = s.rolling(n, min_periods=n).std(ddof=0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(sd > 0, (s.to_numpy() - (ma - k * sd)) / (2.0 * k * sd), 0.5 + 0.0 * sd)


def ema_dist_atr(h, l, c, n_ema: int = 20, n_atr: int = 14) -> np.ndarray:
    e = ema(c, n_ema)
    at = X.wilder_atr(h, l, c, n_atr)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(at > 0, (np.asarray(c, np.float64) - e) / at, np.nan)


def rsi(c, n: int) -> np.ndarray:
    return X.wilder_rsi(c, n)


def adx(h, l, c, n: int = 14):
    """Wilder's ADX with +DI / -DI (RMA smoothing, seeded with the mean of the first n values)."""
    h, l, c = (np.asarray(v, np.float64) for v in (h, l, c))
    up = np.full(len(h), np.nan)
    dn = np.full(len(h), np.nan)
    up[1:] = h[1:] - h[:-1]
    dn[1:] = l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdm[0] = mdm[0] = np.nan
    tr = X.true_range(h, l, c)
    tr[0] = np.nan
    atr_, sp, sm = X.wilder(tr, n), X.wilder(pdm, n), X.wilder(mdm, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi = np.where(atr_ > 0, 100.0 * sp / atr_, 0.0 * atr_)
        mdi = np.where(atr_ > 0, 100.0 * sm / atr_, 0.0 * atr_)
        den = pdi + mdi
        dx = np.where(den > 0, 100.0 * np.abs(pdi - mdi) / den, 0.0 * den)
    return X.wilder(dx, n), pdi, mdi


def supertrend(h, l, c, n: int = 10, mult: float = 3.0) -> np.ndarray:
    h, l, c = (np.asarray(v, np.float64) for v in (h, l, c))
    return X._supertrend(h, l, c, X.wilder_atr(h, l, c, n), float(mult))


@njit(cache=True)
def _donchian_state(h, l, c, n):
    out = np.zeros(c.shape[0], np.int64)
    st = 0
    for i in range(c.shape[0]):
        if i >= n:
            hi = h[i - n]
            lo = l[i - n]
            for j in range(i - n + 1, i):
                if h[j] > hi:
                    hi = h[j]
                if l[j] < lo:
                    lo = l[j]
            if c[i] > hi:
                st = 1
            elif c[i] < lo:
                st = -1
        out[i] = st
    return out


def donchian_side(h, l, c, n: int = 20) -> np.ndarray:
    """+1 after a close above the previous n bars' highest high, -1 after one below their lowest low (held until the other)."""
    return _donchian_state(*(np.asarray(v, np.float64) for v in (h, l, c)), int(n))


def variance_ratio(c, q: int = 4, n: int = 100) -> np.ndarray:
    """VR(q) over the last n bars: Var(q-bar log return) / (q Var(1-bar log return)); the q-bar sums overlap."""
    r = np.full(len(c), np.nan)
    r[1:] = np.diff(np.log(np.asarray(c, np.float64)))
    s1 = pd.Series(r)
    v1 = s1.rolling(n, min_periods=n).var(ddof=1).to_numpy()
    rq = s1.rolling(q, min_periods=q).sum()
    vq = rq.rolling(n - q + 1, min_periods=n - q + 1).var(ddof=1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(v1 > 0, vq / (q * v1), np.nan)


def macd_signal(c) -> np.ndarray:
    """The bot's MACD(12, 26, 9) signal line on closed bars (SMA-seeded EMAs, ``kernels.indicator_arrays``)."""
    return K.indicator_arrays(np.ascontiguousarray(c, np.float64), 14, 12, 26, 9)[5]


# ───────────────────────────── triggers and gates ─────────────────────────────

def indicator_values(b: dict, spec: dict) -> np.ndarray:
    """The indicator a trigger / zone spec names, per bar."""
    ind = spec["ind"]
    h, l, c = b["h"], b["l"], b["c"]
    if ind == "stoch":
        return stoch_k(h, l, c, int(spec.get("n", 14)), int(spec.get("smooth", 3)))
    if ind == "willr":
        return williams_r(h, l, c, int(spec.get("n", 14)))
    if ind == "cci":
        return cci(h, l, c, int(spec.get("n", 20)))
    if ind == "bb":
        return bb_pctb(c, int(spec.get("n", 20)), float(spec.get("k", 2.0)))
    if ind == "emadist":
        return ema_dist_atr(h, l, c, int(spec.get("n", 20)), int(spec.get("atr", 14)))
    if ind == "rsi":
        return rsi(c, int(spec.get("n", 2)))
    raise ValueError(f"unknown indicator {ind!r}")


def trigger_values(symbol: str, tf: str, spec: dict) -> np.ndarray:
    """+1 where the indicator is at or below spec['lo'] (a buy add may go in), -1 at or above spec['hi'], else 0."""
    v = indicator_values(bars(symbol, tf), spec)
    out = np.zeros(len(v), np.int64)
    with np.errstate(invalid="ignore"):
        out[v <= float(spec["lo"])] = 1
        out[v >= float(spec["hi"])] = -1
    return out


def gate_values(symbol: str, spec: dict) -> np.ndarray:
    """Mask per bar of spec['tf'] (bit 0 buys allowed, bit 1 sells allowed) for one gate spec."""
    kind, tf = spec["kind"], spec["tf"]
    b = bars(symbol, tf)
    h, l, c = b["h"], b["l"], b["c"]
    m = np.zeros(len(c), np.int64)
    with np.errstate(invalid="ignore"):
        if kind == "ema_side":                       # buys above the EMA, sells below
            e = ema(c, int(spec["n"]))
            m[c >= e] = 1
            m[c < e] = 2
        elif kind == "macd_trend":                   # the sign of the bot's MACD signal line
            sg = macd_signal(c)
            m[sg > 0] = 1
            m[sg < 0] = 2
        elif kind == "supertrend":
            st = supertrend(h, l, c, int(spec.get("n", 10)), float(spec.get("mult", 3.0)))
            m[st > 0] = 1
            m[st < 0] = 2
        elif kind == "donchian":
            st = donchian_side(h, l, c, int(spec.get("n", 20)))
            m[st > 0] = 1
            m[st < 0] = 2
        elif kind in ("adx_below", "adx_di", "adx_above_block"):
            a, pdi, mdi = adx(h, l, c, int(spec.get("n", 14)))
            thr = float(spec["thr"])
            known = np.isfinite(a)
            if kind == "adx_below":                  # trade only in a weak trend
                m[known & (a < thr)] = 3
            elif kind == "adx_above_block":          # nothing while the trend is strong
                m[known & ~(a > thr)] = 3
            else:                                    # a strong trend: only its side; a weak one: both
                m[known & (a < thr)] = 3
                strong = known & (a >= thr)
                m[strong & (pdi > mdi)] = 1
                m[strong & (pdi <= mdi)] = 2
        elif kind == "zone":                         # an oscillator zone: buys at the low one, sells at the high one
            tv = trigger_values(symbol, tf, spec["ind"])
            m[tv > 0] = 1
            m[tv < 0] = 2
        elif kind == "vr_below":
            vr = variance_ratio(c, int(spec.get("q", 4)), int(spec.get("n", 100)))
            m[vr < float(spec.get("thr", 1.0))] = 3
        elif kind == "atr_pct_block":                # nothing while ATR is above its rolling quantile over N days
            at = X.wilder_atr(h, l, c, int(spec.get("n", 14)))
            s = pd.Series(at, index=pd.to_datetime(b["tc_ms"], unit="ms"))
            q = s.rolling(f"{int(spec.get('days', 100))}D", min_periods=1).quantile(float(spec.get("q", 0.9))).to_numpy()
            m[np.isfinite(at) & ~(at > q)] = 3
        else:
            raise ValueError(f"unknown gate kind {kind!r}")
    return m


def compress(t_ms: np.ndarray, v: np.ndarray) -> Series:
    """Keep the first point and every point where the value changes (same series, fewer points)."""
    v = np.asarray(v)
    if len(v) == 0:
        return np.zeros(0, np.int64), np.zeros(0)
    keep = np.ones(len(v), bool)
    keep[1:] = v[1:] != v[:-1]
    return np.asarray(t_ms, np.int64)[keep], v[keep].astype(np.float64)


def _cached(key: dict, build) -> Series:
    k = json.dumps(key, sort_keys=True, default=str)
    if k not in _SER:
        _SER[k] = build()
    return _SER[k]


def trigger_series(symbol: str, tf: str, spec: dict) -> Series:
    return _cached({"what": "trigger", "symbol": symbol, "tf": tf, **spec},
                   lambda: compress(bars(symbol, tf)["tc_ms"], trigger_values(symbol, tf, spec)))


def gate_series(symbol: str, spec: dict) -> Series:
    return _cached({"what": "gate", "symbol": symbol, **spec},
                   lambda: compress(bars(symbol, spec["tf"])["tc_ms"], gate_values(symbol, spec)))


def combine_and(series: Sequence[Series]) -> Series:
    """Bitwise AND of mask series (each value in force from its time; 0 before a series' first point)."""
    series = [s for s in series if s is not None]
    if not series:
        return np.zeros(0, np.int64), np.zeros(0)
    if len(series) == 1:
        return series[0]
    t = np.unique(np.concatenate([s[0] for s in series]))
    out = np.full(len(t), 3, np.int64)
    for st, sv in series:
        i = np.searchsorted(st, t, side="right") - 1
        val = np.where(i >= 0, sv[np.maximum(i, 0)], 0).astype(np.int64)
        out &= val
    return compress(t, out)


def atr_series(symbol: str, tf: str = "D1", n: int = 14) -> Series:
    """Wilder ATR(n) of closed ``tf`` bars, in price units (unit sizing)."""
    def build():
        b = bars(symbol, tf)
        at = X.wilder_atr(b["h"], b["l"], b["c"], n)
        ok = np.isfinite(at)
        return b["tc_ms"][ok].astype(np.int64), at[ok]
    return _cached({"what": "atr", "symbol": symbol, "tf": tf, "n": n}, build)


def abnormal_series(symbol: str, mult: float = 2.0, days: int = 20) -> Tuple[Series, Series]:
    """(last D1 close, mult x mean |D1 return| over the last ``days`` closed D1 bars), each from the D1 close on."""
    def build_ref():
        b = bars(symbol, "D1")
        return b["tc_ms"].astype(np.int64), b["c"].copy()

    def build_thr():
        b = bars(symbol, "D1")
        r = np.abs(X.returns(b["c"]))
        m = pd.Series(r).rolling(days, min_periods=days).mean().to_numpy() * mult
        ok = np.isfinite(m)
        return b["tc_ms"][ok].astype(np.int64), m[ok]
    return (_cached({"what": "abn_ref", "symbol": symbol}, build_ref),
            _cached({"what": "abn_thr", "symbol": symbol, "mult": mult, "days": days}, build_thr))


def window(s: Series, start_ms: int, end_ms: int) -> Series:
    """The part of a series a run of [start, end) can read: the point in force at the start and every later one before the end."""
    t, v = s
    if len(t) == 0:
        return t, v
    a = max(int(np.searchsorted(t, start_ms, side="right")) - 1, 0)
    z = int(np.searchsorted(t, end_ms, side="left"))
    return t[a:z], v[a:z]
