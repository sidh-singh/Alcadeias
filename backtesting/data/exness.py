"""
Exness public tick-history downloader.

Exness publishes every tick (bid + ask, millisecond timestamps, UTC) of every symbol,
*including the account-type suffix* the live bot trades (``XAUUSDm``, ``BTCUSDm`` =
Standard account), as one ZIP per calendar month:

    https://ticks.ex2archive.com/ticks/<SYMBOL>/<YYYY>/<MM>/Exness_<SYMBOL>_<YYYY>_<MM>.zip

That is the broker's own feed for the exact instrument, so spreads, gaps and session
breaks in the backtest are the ones the live account actually saw. The current month's
file is re-published daily (it grows), so it is re-fetched whenever the remote size or
Last-Modified changes.

Only the standard library is used here so the downloader runs anywhere.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

BASE_URL = "https://ticks.ex2archive.com/ticks"
# A plain, generic client string. Nothing identifying the user or project is ever sent.
USER_AGENT = "Mozilla/5.0 (compatible; tick-history-client)"
CHUNK = 1 << 20  # 1 MiB


@dataclass(frozen=True)
class MonthFile:
    symbol: str
    year: int
    month: int

    @property
    def name(self) -> str:
        return f"Exness_{self.symbol}_{self.year:04d}_{self.month:02d}.zip"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.symbol}/{self.year:04d}/{self.month:02d}/{self.name}"

    def path(self, raw_dir: Path) -> Path:
        return Path(raw_dir) / self.symbol / self.name

    def meta_path(self, raw_dir: Path) -> Path:
        return self.path(raw_dir).with_suffix(".zip.meta.json")


def month_range(start: date, end: date) -> List[Tuple[int, int]]:
    """Inclusive list of (year, month) covering start..end."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _head(url: str, timeout: float = 30.0) -> Optional[dict]:
    """Remote size / Last-Modified, or None when the month is not published."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {
                "size": int(r.headers.get("Content-Length") or 0),
                "last_modified": r.headers.get("Last-Modified") or "",
                "etag": r.headers.get("ETag") or "",
            }
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise


def _zip_ok(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None and len(z.namelist()) > 0
    except (zipfile.BadZipFile, OSError):
        return False


def download_month(mf: MonthFile, raw_dir: Path, force: bool = False,
                   retries: int = 5, log=print) -> Optional[Path]:
    """
    Fetch one monthly ZIP into ``raw_dir/<symbol>/``. Resumable, verified.

    Returns the local path, or None when Exness has not published that month.
    Skips the download when the local copy already matches the remote size and
    Last-Modified (so re-running is cheap and the growing current month refreshes).
    """
    dest = mf.path(raw_dir)
    meta_p = mf.meta_path(raw_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)

    remote = None
    for attempt in range(retries):
        try:
            remote = _head(mf.url)
            break
        except Exception as e:  # network hiccup -> retry with backoff
            if attempt == retries - 1:
                raise
            log(f"  HEAD retry {attempt + 1} for {mf.name}: {e}")
            time.sleep(2 * (attempt + 1))
    if remote is None:
        log(f"  {mf.name}: not published (skipped)")
        return None

    if dest.exists() and not force:
        try:
            local = json.loads(meta_p.read_text())
        except (OSError, ValueError):
            local = {}
        if (dest.stat().st_size == remote["size"]
                and local.get("last_modified") == remote["last_modified"]):
            log(f"  {mf.name}: up to date ({remote['size'] / 1e6:.1f} MB)")
            return dest

    part = dest.with_suffix(".zip.part")
    for attempt in range(retries):
        try:
            have = part.stat().st_size if part.exists() else 0
            if have > remote["size"]:
                part.unlink()
                have = 0
            headers = {"User-Agent": USER_AGENT}
            if have:
                headers["Range"] = f"bytes={have}-"
            req = urllib.request.Request(mf.url, headers=headers)
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=120) as r:
                if have and r.status != 206:  # server ignored the range -> restart
                    have = 0
                mode = "ab" if have else "wb"
                with open(part, mode) as f:
                    while True:
                        buf = r.read(CHUNK)
                        if not buf:
                            break
                        f.write(buf)
            got = part.stat().st_size
            if got != remote["size"]:
                raise IOError(f"size mismatch {got} != {remote['size']}")
            if not _zip_ok(part):
                part.unlink(missing_ok=True)
                raise IOError("corrupt zip")
            os.replace(part, dest)
            meta_p.write_text(json.dumps({**remote, "url": mf.url}, indent=2))
            dt = max(time.time() - t0, 1e-6)
            log(f"  {mf.name}: {got / 1e6:.1f} MB in {dt:.0f}s ({got / 1e6 / dt:.1f} MB/s)")
            return dest
        except Exception as e:
            if attempt == retries - 1:
                raise
            log(f"  retry {attempt + 1} for {mf.name}: {e}")
            time.sleep(3 * (attempt + 1))
    return None


def download_range(symbols: Iterable[str], start: date, end: date, raw_dir: Path,
                   force: bool = False, log=print) -> List[Path]:
    """Download every monthly file covering start..end for each symbol."""
    out = []
    for sym in symbols:
        log(f"[{sym}] {start} .. {end}")
        for (y, m) in month_range(start, end):
            p = download_month(MonthFile(sym, y, m), Path(raw_dir), force=force, log=log)
            if p is not None:
                out.append(p)
    return out


if __name__ == "__main__":  # python -m backtesting.data.exness XAUUSDm BTCUSDm 2026-01 2026-11 <dir>
    import sys

    *syms, a, b, d = sys.argv[1:]
    ya, ma = (int(x) for x in a.split("-"))
    yb, mb = (int(x) for x in b.split("-"))
    download_range(syms, date(ya, ma, 1), date(yb, mb, 1), Path(d))
