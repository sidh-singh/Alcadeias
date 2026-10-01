"""
Backtest data loader — OFFLINE, no MT5 sign-in required.

Two sources (in priority order):
  1. A local CSV (``--csv path``) — use this to drop in MT5-exported broker-exact
     bars (BTCUSDm). Columns accepted: time/open/high/low/close[/volume], where
     ``time`` may be ISO text or epoch ms/seconds.
  2. Binance public klines (BTCUSDT 1m) — no API key / no login. Fetched over
     plain HTTPS and cached under backtest/data/ so later runs are instant.

BTCUSDT (Binance spot, USD-stablecoin) is used as a *proxy* for the broker's
BTCUSD when no broker CSV is supplied — it tracks BTCUSD within a small basis and
is more than close enough to study how the parameters and logic behave. For
broker-exact fills, export M1 bars from MT5 and pass them with --csv.

Everything downstream is built by causal resampling of these M1 bars, so the
simulation only ever sees data up to the decision minute (no look-ahead).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Public klines mirrors, tried in order. All serve the identical /api/v3/klines
# endpoint with NO authentication.
_BINANCE_HOSTS = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api.binance.us",
)

_MS_MIN = 60_000


def idx_to_ms(index) -> np.ndarray:
    """Epoch-milliseconds for a (tz-aware) DatetimeIndex, robust to the pandas
    datetime resolution (ns/us/ms/s all normalise correctly). ``.asi8`` returns
    the index's *own* unit, so we normalise via numpy datetime64[ms]. tz is
    dropped first (values already represent UTC) to avoid a numpy tz warning."""
    if getattr(index, "tz", None) is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    return index.to_numpy().astype("datetime64[ms]").astype("int64")


# ───────────────────────── Binance public fetch ─────────────────────────
def _http_get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (backtest)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _fetch_binance_klines(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Page 1-minute klines in [start_ms, end_ms). Returns raw OHLCV DataFrame."""
    last_err = None
    for host in _BINANCE_HOSTS:
        rows = []
        cursor = start_ms
        ok = True
        try:
            while cursor < end_ms:
                url = (
                    f"{host}/api/v3/klines?symbol={symbol}&interval=1m"
                    f"&startTime={cursor}&endTime={end_ms}&limit=1000"
                )
                batch = _http_get_json(url)
                if not batch:
                    break
                rows.extend(batch)
                nxt = batch[-1][0] + _MS_MIN
                if nxt <= cursor:      # no forward progress → done
                    break
                cursor = nxt
                if len(batch) < 1000:  # reached the live edge
                    break
                time.sleep(0.12)       # be polite to the public endpoint
                pct = min(100.0, 100.0 * (cursor - start_ms) / max(1, end_ms - start_ms))
                print(f"\r  fetching {symbol} 1m from {host.split('//')[1]} … {pct:5.1f}%",
                      end="", flush=True)
            print()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            print(f"\n  host {host} failed ({type(e).__name__}); trying next mirror…")
            ok = False
        if ok and rows:
            df = pd.DataFrame(rows, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "qav", "trades", "tbb", "tbq", "ignore",
            ])
            df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
            for c in ("open", "high", "low", "close", "volume"):
                df[c] = df[c].astype(float)
            df["open_time"] = df["open_time"].astype("int64")
            df = df.drop_duplicates(subset="open_time").sort_values("open_time")
            return df
    raise RuntimeError(
        "Could not fetch public klines from any mirror "
        f"(last error: {type(last_err).__name__ if last_err else 'empty'}). "
        "If this machine is offline, export M1 bars from MT5 and pass them with --csv."
    )


# ───────────────────────── CSV (broker-exact) path ─────────────────────────
def _load_csv(path: str) -> pd.DataFrame:
    """Load a user CSV of M1 bars. Flexible column naming and time formats."""
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    t = pick("time", "date", "datetime", "timestamp", "open_time")
    o = pick("open", "o")
    h = pick("high", "h")
    l = pick("low", "l")
    c = pick("close", "c")
    v = pick("volume", "tick_volume", "vol", "v")
    if not all([t, o, h, l, c]):
        raise ValueError(f"CSV {path} must have time/open/high/low/close columns; got {list(df.columns)}")

    out = pd.DataFrame()
    ts = df[t]
    if np.issubdtype(ts.dtype, np.number):
        # epoch: seconds if ~10 digits, ms if ~13
        unit = "ms" if ts.astype("int64").iloc[-1] > 10_000_000_000 else "s"
        idx = pd.to_datetime(ts, unit=unit, utc=True)
    else:
        idx = pd.to_datetime(ts, utc=True)
    out["open_time"] = idx_to_ms(pd.DatetimeIndex(idx))  # epoch ms (resolution-robust)
    out["open"] = df[o].astype(float)
    out["high"] = df[h].astype(float)
    out["low"] = df[l].astype(float)
    out["close"] = df[c].astype(float)
    out["volume"] = df[v].astype(float) if v else 1.0
    out = out.drop_duplicates(subset="open_time").sort_values("open_time")
    return out


# ───────────────────────── public entry point ─────────────────────────
def load_m1(symbol: str = "BTCUSDT", test_days: int = 90, warmup_days: int = 35,
            csv: str | None = None, refresh: bool = False) -> pd.DataFrame:
    """
    Return a 1-minute OHLCV DataFrame indexed by UTC DatetimeIndex, covering
    ``warmup_days`` of history BEFORE the test window plus ``test_days`` of test
    data ending "now". The extra warmup lets every indicator/timeframe converge
    exactly as the live bot's rolling windows do before the scored period starts.

    Adds an integer column ``is_test`` = 1 for bars inside the scored window.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    test_start = now - timedelta(days=test_days)
    fetch_start = test_start - timedelta(days=warmup_days)

    if csv:
        print(f"Loading broker-exact M1 bars from CSV: {csv}")
        raw = _load_csv(csv)
    else:
        cache = os.path.join(DATA_DIR, f"{symbol}_1m.csv")
        start_ms = int(fetch_start.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        raw = None
        if os.path.exists(cache) and not refresh:
            cached = pd.read_csv(cache)
            cov0, cov1 = int(cached["open_time"].iloc[0]), int(cached["open_time"].iloc[-1])
            if cov0 <= start_ms and cov1 >= end_ms - 6 * _MS_MIN:
                print(f"Using cached {symbol} 1m data ({cache})")
                raw = cached
        if raw is None:
            print(f"Fetching {symbol} 1m public klines "
                  f"({fetch_start:%Y-%m-%d} → {now:%Y-%m-%d}, no sign-in)…")
            raw = _fetch_binance_klines(symbol, start_ms, end_ms)
            raw.to_csv(cache, index=False)
            print(f"  cached → {cache}  ({len(raw):,} bars)")

    df = raw.copy()
    df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("dt").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    # Trim to the requested [fetch_start, now] envelope
    df = df[(df.index >= fetch_start) & (df.index <= now)]
    df["is_test"] = (df.index >= test_start).astype(int)

    n_test = int(df["is_test"].sum())
    print(f"Loaded {len(df):,} M1 bars  |  warmup {len(df) - n_test:,}  |  test {n_test:,} "
          f"({df.index[df['is_test'] == 1][0]:%Y-%m-%d %H:%M} → {df.index[-1]:%Y-%m-%d %H:%M} UTC)")
    return df


# ───────────────────────── causal resampling helpers ─────────────────────────
# Minutes per MT5 timeframe name.
TF_MINUTES = {
    "TIMEFRAME_M1": 1, "TIMEFRAME_M5": 5, "TIMEFRAME_M15": 15, "TIMEFRAME_M30": 30,
    "TIMEFRAME_H1": 60, "TIMEFRAME_H4": 240, "TIMEFRAME_H6": 360, "TIMEFRAME_D1": 1440,
}


def resample_ohlc(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Causally resample M1 → higher-TF OHLC (UTC/epoch-aligned, MT5-style closes).

    A bar labelled at its OPEN time b covers [b, b+minutes); its Close is the last
    M1 close inside that window. Empty windows (data gaps) are dropped.
    """
    rule = f"{minutes}min"
    r = m1.resample(rule, origin="epoch", label="left", closed="left")
    out = pd.DataFrame({
        "Open": r["open"].first(),
        "High": r["high"].max(),
        "Low": r["low"].min(),
        "Close": r["close"].last(),
        "Volume": r["volume"].sum(),
    }).dropna(subset=["Close"])
    return out


def close_series_with_closetime(m1: pd.DataFrame, minutes: int):
    """Return (close_time_ms int64[], close float[]) for completed TF bars.

    close_time = bar_open + minutes (the instant the bar finalises), which is what
    we compare the decision minute against to know which bars MT5 would already
    show as completed.
    """
    ohlc = resample_ohlc(m1, minutes)
    open_ms = idx_to_ms(ohlc.index)
    close_ms = open_ms + minutes * _MS_MIN
    return close_ms, ohlc["Close"].to_numpy(dtype=float)
