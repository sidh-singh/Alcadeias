"""
Local columnar tick store.

Each monthly Exness ZIP is parsed once into three numpy archives under
``data/store/<SYMBOL>/<YYYY>_<MM>/``:

``ticks.npz``  every tick                      -> t_ms (int64, UTC ms), bid, ask
``sec.npz``    the LAST tick of every second   -> t_ms (its true ms time), bid, ask
``m1.npz``     M1 bars built from BID prices   -> t (bar open, epoch s), o h l c,
               ask_c (ask at the closing tick), spread_mean, spread_max, n (ticks)

Why three resolutions:

* The live bot polls MT5 roughly once a second and only ever acts on the latest tick,
  so the per-second series reproduces what a 1 s poll sees *exactly* while being ~5x
  smaller than raw ticks -- that is what parameter sweeps run on.
* Raw ticks drive the high-fidelity runs (arbitrary poll period / phase / latency) and
  the parity test against the real live code.
* M1 bars supply the indicator warm-up history before a test window and the candles
  for the charts. MT5 builds its bars from Bid, so do we.

Server time on Exness MT5 is UTC+0, which is why bars are bucketed on plain UTC epochs.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .exness import MonthFile, month_range

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "exness"
DEFAULT_STORE_DIR = REPO_ROOT / "data" / "store"

STORE_VERSION = 3


# ───────────────────────────── time helpers ─────────────────────────────

def to_ms(x) -> int:
    """date / datetime / ISO string / epoch-ms -> UTC epoch milliseconds."""
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, str):
        x = pd.Timestamp(x)
    if isinstance(x, pd.Timestamp):
        if x.tzinfo is None:
            x = x.tz_localize("UTC")
        return int(x.tz_convert("UTC").value // 1_000_000)
    if isinstance(x, datetime):
        if x.tzinfo is None:
            x = x.replace(tzinfo=timezone.utc)
        return int(x.timestamp() * 1000)
    if isinstance(x, date):
        return int(datetime(x.year, x.month, x.day, tzinfo=timezone.utc).timestamp() * 1000)
    raise TypeError(f"cannot convert {type(x)} to epoch ms")


def ms_to_dt(ms) -> pd.Timestamp:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC")


# ───────────────────────────── parsing ─────────────────────────────

def parse_month_zip(zip_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Parse one Exness monthly ZIP -> (t_ms, bid, ask, stats).

    The CSV is ``"Exness","Symbol","Timestamp","Bid","Ask"`` with UTC timestamps such
    as ``2026-11-01 23:01:30.160Z``. Rows are cleaned conservatively: only rows that
    cannot be real quotes are dropped (non-positive prices, ask < bid), and the count
    of everything dropped is returned in ``stats`` so nothing is hidden.
    """
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"no CSV inside {zip_path}")
        with z.open(names[0]) as f:
            df = pd.read_csv(
                f, header=0, usecols=[2, 3, 4], names=["x", "sym", "ts", "bid", "ask"],
                dtype={"ts": "string", "bid": "float64", "ask": "float64"},
                engine="c",
            )
    n_raw = len(df)
    ts = pd.to_datetime(df["ts"], format="ISO8601", utc=True)
    t_ms = (ts.astype("int64") // 1_000_000).to_numpy(dtype=np.int64) \
        if str(ts.dtype).endswith("[ns, UTC]") else \
        (ts.astype("datetime64[ns, UTC]").astype("int64") // 1_000_000).to_numpy(dtype=np.int64)
    bid = df["bid"].to_numpy(dtype=np.float64)
    ask = df["ask"].to_numpy(dtype=np.float64)
    del df, ts

    bad = ~(np.isfinite(bid) & np.isfinite(ask)) | (bid <= 0) | (ask <= 0) | (ask < bid)
    n_bad = int(bad.sum())
    if n_bad:
        keep = ~bad
        t_ms, bid, ask = t_ms[keep], bid[keep], ask[keep]

    # The archive is chronological; guard anyway (stable sort keeps same-ms order).
    n_unsorted = int((np.diff(t_ms) < 0).sum())
    if n_unsorted:
        order = np.argsort(t_ms, kind="stable")
        t_ms, bid, ask = t_ms[order], bid[order], ask[order]

    stats = {
        "rows_raw": int(n_raw),
        "rows_kept": int(len(t_ms)),
        "rows_dropped_invalid": n_bad,
        "rows_out_of_order": n_unsorted,
        "first": ms_to_dt(t_ms[0]).isoformat() if len(t_ms) else None,
        "last": ms_to_dt(t_ms[-1]).isoformat() if len(t_ms) else None,
    }
    return t_ms, bid, ask, stats


# ───────────────────────────── reductions ─────────────────────────────

def reduce_to_seconds(t_ms: np.ndarray, bid: np.ndarray, ask: np.ndarray):
    """
    The ticks a one-second poll on whole seconds can ever act on, with their true timestamps.

    Kept: the last tick of every second [s, s+1) -- so every bar close is exact -- and the
    last tick stamped exactly on a whole second. A poll at T sees every tick with t <= T, so
    a tick at exactly T is visible to it even when more ticks follow inside the same second;
    without the second rule that poll would be shown the previous second's quote instead.
    """
    if len(t_ms) == 0:
        return t_ms, bid, ask
    sec = t_ms // 1000
    last_of_second = np.diff(sec, append=sec[-1] + 1) != 0
    last_of_stamp = np.diff(t_ms, append=t_ms[-1] + 1) != 0
    keep = np.flatnonzero(last_of_second | ((t_ms % 1000 == 0) & last_of_stamp))
    return t_ms[keep], bid[keep], ask[keep]


def build_bars(t_ms: np.ndarray, bid: np.ndarray, ask: np.ndarray, tf_seconds: int = 60) -> Dict[str, np.ndarray]:
    """OHLC bars from BID ticks (MT5 convention). Bars exist only where ticks exist."""
    if len(t_ms) == 0:
        z = np.zeros(0)
        return {"t": np.zeros(0, np.int64), "o": z, "h": z, "l": z, "c": z,
                "ask_c": z, "spread_mean": z, "spread_max": z, "n": np.zeros(0, np.int64)}
    bar = t_ms // (tf_seconds * 1000)
    first = np.flatnonzero(np.diff(bar, prepend=bar[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bar) - 1)
    spread = ask - bid
    n = (last - first + 1).astype(np.int64)
    return {
        "t": (bar[first] * tf_seconds).astype(np.int64),
        "o": bid[first].copy(),
        "h": np.maximum.reduceat(bid, first),
        "l": np.minimum.reduceat(bid, first),
        "c": bid[last].copy(),
        "ask_c": ask[last].copy(),
        "spread_mean": np.add.reduceat(spread, first) / n,
        "spread_max": np.maximum.reduceat(spread, first),
        "n": n,
    }


def resample_bars(m1: Dict[str, np.ndarray], tf_seconds: int) -> Dict[str, np.ndarray]:
    """Aggregate M1 bars to a higher timeframe on UTC epoch boundaries (MT5-style)."""
    if tf_seconds == 60 or len(m1["t"]) == 0:
        return m1
    bar = m1["t"] // tf_seconds
    first = np.flatnonzero(np.diff(bar, prepend=bar[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bar) - 1)
    n = np.add.reduceat(m1["n"], first)
    return {
        "t": (bar[first] * tf_seconds).astype(np.int64),
        "o": m1["o"][first].copy(),
        "h": np.maximum.reduceat(m1["h"], first),
        "l": np.minimum.reduceat(m1["l"], first),
        "c": m1["c"][last].copy(),
        "ask_c": m1["ask_c"][last].copy(),
        "spread_mean": np.add.reduceat(m1["spread_mean"] * m1["n"], first) / n,
        "spread_max": np.maximum.reduceat(m1["spread_max"], first),
        "n": n,
    }


# ───────────────────────────── build ─────────────────────────────

def month_dir(store_dir: Path, symbol: str, year: int, month: int) -> Path:
    return Path(store_dir) / symbol / f"{year:04d}_{month:02d}"


def build_month(symbol: str, year: int, month: int,
                raw_dir: Path = DEFAULT_RAW_DIR, store_dir: Path = DEFAULT_STORE_DIR,
                force: bool = False, keep_ticks: bool = True, log=print) -> Optional[dict]:
    """Parse one monthly ZIP into the store. Idempotent; rebuilds when the ZIP changed."""
    mf = MonthFile(symbol, year, month)
    zp = mf.path(Path(raw_dir))
    if not zp.exists():
        return None
    out = month_dir(store_dir, symbol, year, month)
    meta_p = out / "meta.json"
    src_sig = {"size": zp.stat().st_size, "mtime": int(zp.stat().st_mtime)}
    if meta_p.exists() and not force:
        try:
            meta = json.loads(meta_p.read_text())
            if (meta.get("source") == src_sig and meta.get("store_version") == STORE_VERSION
                    and (meta.get("has_ticks") or not keep_ticks)):
                return meta
        except ValueError:
            pass

    out.mkdir(parents=True, exist_ok=True)
    if meta_p.exists() and not force and (out / "ticks.npz").exists():
        try:
            old = json.loads(meta_p.read_text())
        except ValueError:
            old = {}
        if old.get("source") == src_sig and old.get("store_version") == 2:
            with np.load(out / "ticks.npz") as z:
                s_t, s_bid, s_ask = reduce_to_seconds(z["t_ms"], z["bid"], z["ask"])
            np.savez(out / "sec.npz", t_ms=s_t, bid=s_bid, ask=s_ask)
            old.update(store_version=STORE_VERSION, seconds=int(len(s_t)))
            meta_p.write_text(json.dumps(old, indent=2))
            log(f"  upgraded {symbol} {year}-{month:02d} to store v{STORE_VERSION}: {len(s_t):,} per-second rows")
            return old
    t_ms, bid, ask, stats = parse_month_zip(zp)
    s_t, s_bid, s_ask = reduce_to_seconds(t_ms, bid, ask)
    m1 = build_bars(t_ms, bid, ask, 60)
    if keep_ticks:
        np.savez_compressed(out / "ticks.npz", t_ms=t_ms, bid=bid, ask=ask)
    np.savez(out / "sec.npz", t_ms=s_t, bid=s_bid, ask=s_ask)
    np.savez(out / "m1.npz", **m1)
    spread = ask - bid
    meta = {
        "symbol": symbol, "year": year, "month": month,
        "store_version": STORE_VERSION, "source": src_sig, "has_ticks": bool(keep_ticks),
        "ticks": int(len(t_ms)), "seconds": int(len(s_t)), "m1_bars": int(len(m1["t"])),
        "spread_median": float(np.median(spread)) if len(spread) else None,
        "spread_mean": float(spread.mean()) if len(spread) else None,
        "spread_p99": float(np.quantile(spread, 0.99)) if len(spread) else None,
        "bid_min": float(bid.min()) if len(bid) else None,
        "bid_max": float(bid.max()) if len(bid) else None,
        **stats,
    }
    meta_p.write_text(json.dumps(meta, indent=2))
    log(f"  built {symbol} {year}-{month:02d}: {meta['ticks']:,} ticks, {meta['seconds']:,} s, "
        f"{meta['m1_bars']:,} M1 bars, median spread {meta['spread_median']:.3f}")
    return meta


def build_range(symbols: Iterable[str], start: date, end: date,
                raw_dir: Path = DEFAULT_RAW_DIR, store_dir: Path = DEFAULT_STORE_DIR,
                force: bool = False, keep_ticks: bool = True, log=print) -> List[dict]:
    out = []
    for sym in symbols:
        for (y, m) in month_range(start, end):
            meta = build_month(sym, y, m, raw_dir, store_dir, force=force, keep_ticks=keep_ticks, log=log)
            if meta:
                out.append(meta)
    return out


# ───────────────────────────── load ─────────────────────────────

def available_months(symbol: str, store_dir: Path = DEFAULT_STORE_DIR) -> List[Tuple[int, int]]:
    base = Path(store_dir) / symbol
    if not base.exists():
        return []
    out = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and (p / "meta.json").exists():
            y, m = p.name.split("_")
            out.append((int(y), int(m)))
    return out


def _load(symbol: str, kind: str, start_ms: int, end_ms: int, store_dir: Path,
          time_key: str, time_scale: int) -> Dict[str, np.ndarray]:
    """Concatenate the monthly archives of ``kind`` covering [start_ms, end_ms)."""
    s, e = ms_to_dt(start_ms), ms_to_dt(max(end_ms - 1, start_ms))
    parts: List[Dict[str, np.ndarray]] = []
    for (y, m) in month_range(date(s.year, s.month, 1), date(e.year, e.month, 1)):
        p = month_dir(store_dir, symbol, y, m) / f"{kind}.npz"
        if not p.exists():
            continue
        with np.load(p) as z:
            d = {k: z[k] for k in z.files}
        t = d[time_key].astype(np.int64) * time_scale
        lo = int(np.searchsorted(t, start_ms, side="left"))
        hi = int(np.searchsorted(t, end_ms, side="left"))
        if hi > lo:
            parts.append({k: v[lo:hi] for k, v in d.items()})
    if not parts:
        return {}
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def load_ticks(symbol: str, start, end, store_dir: Path = DEFAULT_STORE_DIR) -> Dict[str, np.ndarray]:
    """Every tick in [start, end): t_ms, bid, ask."""
    return _load(symbol, "ticks", to_ms(start), to_ms(end), Path(store_dir), "t_ms", 1)


def load_sec(symbol: str, start, end, store_dir: Path = DEFAULT_STORE_DIR) -> Dict[str, np.ndarray]:
    """Last tick of every second in [start, end): t_ms, bid, ask."""
    return _load(symbol, "sec", to_ms(start), to_ms(end), Path(store_dir), "t_ms", 1)


def load_m1(symbol: str, start, end, store_dir: Path = DEFAULT_STORE_DIR) -> Dict[str, np.ndarray]:
    """M1 bid bars whose open time is in [start, end)."""
    return _load(symbol, "m1", to_ms(start), to_ms(end), Path(store_dir), "t", 1000)


def data_span(symbol: str, store_dir: Path = DEFAULT_STORE_DIR) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    """First / last tick time available in the store for a symbol."""
    months = available_months(symbol, store_dir)
    if not months:
        return None
    first = json.loads((month_dir(store_dir, symbol, *months[0]) / "meta.json").read_text())
    last = json.loads((month_dir(store_dir, symbol, *months[-1]) / "meta.json").read_text())
    return pd.Timestamp(first["first"]), pd.Timestamp(last["last"])
