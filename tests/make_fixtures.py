"""
Regenerate the miniature tick store the test-suite runs on.

    python tests/make_fixtures.py

It cuts short, event-rich windows of *real* Exness ticks out of the full store
(``data/store``, built by ``python -m backtesting data``) together with the M1 history
the indicators need to warm up, and writes them in the normal store layout under
``tests/fixtures/store``. The fixtures are committed, so the tests need no download.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.data import store  # noqa: E402

FIXTURE_STORE = ROOT / "tests" / "fixtures" / "store"

# symbol -> (window start, window end, days of M1 history kept before the window)
WINDOWS = {
    # a full BUY ladder, force-closes and target closes inside one hour
    "BTCUSDm": ("2026-11-09 06:00", "2026-11-09 07:00", 12),
    # longs and shorts, a ladder add, target and force-close exits
    "XAUUSDm": ("2026-11-11 15:00", "2026-11-11 15:45", 12),
}


def main() -> None:
    for symbol, (a, z, warm_days) in WINDOWS.items():
        a_ms, z_ms = store.to_ms(a), store.to_ms(z)
        w_ms = a_ms - warm_days * 86_400_000
        ticks = store.load_ticks(symbol, a_ms, z_ms)
        sec = store.load_sec(symbol, a_ms, z_ms)
        m1 = store.load_m1(symbol, w_ms, z_ms)
        if not ticks or not m1:
            raise SystemExit(f"{symbol}: the full store has no data for {a} .. {z}; run `python -m backtesting data`")
        # one month directory per calendar month touched (the loaders walk month by month)
        months = sorted({(int(t.year), int(t.month)) for t in
                         (store.ms_to_dt(w_ms), store.ms_to_dt(a_ms), store.ms_to_dt(z_ms - 1))})
        for (y, m) in months:
            lo = store.to_ms(f"{y:04d}-{m:02d}-01")
            hi = store.to_ms(f"{y + (m == 12):04d}-{(m % 12) + 1:02d}-01")
            out = store.month_dir(FIXTURE_STORE, symbol, y, m)
            out.mkdir(parents=True, exist_ok=True)

            def cut(d, key, scale):
                t = d[key].astype(np.int64) * scale
                keep = (t >= lo) & (t < hi)
                return {k: v[keep] for k, v in d.items()}

            tk, sc, mm = cut(ticks, "t_ms", 1), cut(sec, "t_ms", 1), cut(m1, "t", 1000)
            np.savez_compressed(out / "ticks.npz", **tk)
            np.savez_compressed(out / "sec.npz", **sc)
            np.savez_compressed(out / "m1.npz", **mm)
            first = int(mm["t"][0]) * 1000 if len(mm["t"]) else lo
            last = int(tk["t_ms"][-1]) if len(tk["t_ms"]) else (int(mm["t"][-1]) * 1000 if len(mm["t"]) else lo)
            (out / "meta.json").write_text(json.dumps({
                "symbol": symbol, "year": y, "month": m, "store_version": store.STORE_VERSION,
                "fixture": True, "has_ticks": True,
                "ticks": int(len(tk["t_ms"])), "seconds": int(len(sc["t_ms"])), "m1_bars": int(len(mm["t"])),
                "first": store.ms_to_dt(first).isoformat(), "last": store.ms_to_dt(last).isoformat(),
                "window": [a, z], "warm_days": warm_days,
            }, indent=2), encoding="utf-8")
            print(f"{symbol} {y}-{m:02d}: {len(tk['t_ms']):,} ticks, {len(sc['t_ms']):,} s, {len(mm['t']):,} M1 bars")
    size = sum(p.stat().st_size for p in FIXTURE_STORE.rglob("*") if p.is_file())
    print(f"fixtures: {size / 1e6:.2f} MB in {FIXTURE_STORE}")


if __name__ == "__main__":
    main()
