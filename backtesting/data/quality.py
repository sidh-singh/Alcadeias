"""
Data-quality report for the tick store.

A backtest is only as good as its data, so before any result is trusted this module
measures the feed itself: coverage, gaps, spread behaviour and price jumps. It reads the
per-second and M1 stores (fast) plus the build metadata of every month.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from . import store


HOLE = "hole in the archive"


def _gap_kind(symbol: str, a_ms: int, b_ms: int) -> str:
    """
    Classify a silence. Gold has a weekly session with a daily break, so most of its silences
    are the market being shut; BTC trades around the clock, so hours of silence there can only
    be missing history (``SymbolSpec.data_hole_s``; the engine treats those specially).
    """
    from ..config import SYMBOLS
    a, b = store.ms_to_dt(a_ms), store.ms_to_dt(b_ms)
    hours = (b_ms - a_ms) / 3.6e6
    hole_s = SYMBOLS[symbol].data_hole_s if symbol in SYMBOLS else 0.0
    if hole_s > 0:
        if hours * 3600.0 >= hole_s:
            return HOLE
        return "short pause (maintenance)" if hours <= 1.0 else "other"
    if hours >= 40 and a.dayofweek in (4, 5) and b.dayofweek in (6, 0):
        return "weekend"
    if 0.8 <= hours <= 1.3 and a.hour in (20, 21, 22):
        return "daily break"
    if hours >= 20:
        return "holiday / long close"
    if 1.3 < hours <= 6 and b.hour in (22, 23) and a.hour >= 16:
        return "early close before the daily break (holiday)"
    if hours <= 0.5:
        return "short pause"
    return "other"


def quality_report(symbol: str, start, end, store_dir: Path = store.DEFAULT_STORE_DIR) -> Dict:
    start_ms, end_ms = store.to_ms(start), store.to_ms(end)
    sec = store.load_sec(symbol, start_ms, end_ms, store_dir)
    m1 = store.load_m1(symbol, start_ms, end_ms, store_dir)
    if not sec:
        raise ValueError(f"no data for {symbol} in the requested window")
    t, bid, ask = sec["t_ms"], sec["bid"], sec["ask"]
    spread = ask - bid

    # build metadata (per month): raw tick counts and anything the parser dropped
    months = []
    s, e = store.ms_to_dt(start_ms), store.ms_to_dt(end_ms - 1)
    from .exness import month_range
    from datetime import date
    for (y, m) in month_range(date(s.year, s.month, 1), date(e.year, e.month, 1)):
        p = store.month_dir(store_dir, symbol, y, m) / "meta.json"
        if p.exists():
            meta = json.loads(p.read_text(encoding="utf-8"))
            months.append({k: meta.get(k) for k in (
                "year", "month", "ticks", "seconds", "m1_bars", "rows_dropped_invalid",
                "rows_out_of_order", "spread_median", "spread_mean", "spread_p99", "first", "last")})

    # gaps between consecutive ticks (per-second series keeps true ms timestamps)
    dt = np.diff(t)
    order = np.argsort(dt)[::-1][:400]
    gaps: List[dict] = []
    for i in order:
        if dt[i] < 180_000:
            break
        gaps.append({"from": store.ms_to_dt(t[i]).isoformat(), "to": store.ms_to_dt(t[i + 1]).isoformat(),
                     "minutes": round(float(dt[i]) / 60000.0, 1), "kind": _gap_kind(symbol, int(t[i]), int(t[i + 1])),
                     "price_jump": round(float(bid[i + 1] - bid[i]), 3),
                     "price_jump_pct": round(float(bid[i + 1] / bid[i] - 1.0) * 100.0, 4)})
    kinds = pd.Series([g["kind"] for g in gaps]).value_counts().to_dict() if gaps else {}
    unexplained = [g for g in gaps if g["kind"] == "other"]
    holes = sorted((g for g in gaps if g["kind"] == HOLE), key=lambda g: g["from"])

    # activity per UTC day
    day = pd.to_datetime(t, unit="ms", utc=True).floor("D")
    per_day = pd.Series(1, index=day).groupby(level=0).sum()
    all_days = pd.date_range(store.ms_to_dt(start_ms).floor("D"), store.ms_to_dt(end_ms - 1).floor("D"), freq="D")
    missing = [d for d in all_days if d not in per_day.index]
    if symbol.startswith("XAU"):
        missing = [d for d in missing if d.dayofweek != 5]   # gold is shut on Saturdays

    # spread through the day
    hour = pd.to_datetime(t, unit="ms", utc=True).hour
    by_hour = pd.DataFrame({"h": hour, "s": spread}).groupby("h")["s"].agg(["median", "mean", "max"])

    # price jumps second-to-second and M1 ranges
    ret = np.abs(np.diff(bid) / bid[:-1])
    live = dt < 5000                      # ignore the jump across a real gap
    jr = ret[live]
    rng = (m1["h"] - m1["l"]) / m1["c"] if m1 else np.zeros(0)

    return {
        "symbol": symbol,
        "window": [store.ms_to_dt(start_ms).isoformat(), store.ms_to_dt(end_ms).isoformat()],
        "first_tick": store.ms_to_dt(t[0]).isoformat(),
        "last_tick": store.ms_to_dt(t[-1]).isoformat(),
        "ticks_total": int(sum(m["ticks"] or 0 for m in months)) if months else None,
        "active_seconds": int(len(t)),
        "m1_bars": int(len(m1["t"])) if m1 else 0,
        "rows_dropped_invalid": int(sum(m["rows_dropped_invalid"] or 0 for m in months)),
        "rows_out_of_order": int(sum(m["rows_out_of_order"] or 0 for m in months)),
        "timestamps_monotonic": bool(np.all(dt >= 0)),
        "price": {"min": float(bid.min()), "max": float(bid.max()),
                  "first": float(bid[0]), "last": float(bid[-1])},
        "spread": {"min": float(spread.min()), "median": float(np.median(spread)),
                   "mean": float(spread.mean()), "p95": float(np.quantile(spread, 0.95)),
                   "p99": float(np.quantile(spread, 0.99)), "p999": float(np.quantile(spread, 0.999)),
                   "max": float(spread.max()),
                   "non_positive": int((spread <= 0).sum()),
                   "pct_of_price_median": float(np.median(spread / bid) * 100.0)},
        "spread_by_hour_utc": {int(h): {"median": float(r["median"]), "mean": float(r["mean"]), "max": float(r["max"])}
                               for h, r in by_hour.iterrows()},
        "gaps_over_3min": {"count": len(gaps), "by_kind": kinds,
                           "largest": gaps[:12], "unexplained": unexplained[:25], "holes": holes},
        "days": {"with_ticks": int(len(per_day)), "missing": [d.strftime("%Y-%m-%d") for d in missing],
                 "seconds_per_day_min": int(per_day.min()), "seconds_per_day_median": int(per_day.median()),
                 "seconds_per_day_max": int(per_day.max())},
        "jumps": {"max_1s_move_pct": float(jr.max() * 100.0) if len(jr) else 0.0,
                  "moves_over_0p1pct": int((jr > 0.001).sum()), "moves_over_0p5pct": int((jr > 0.005).sum()),
                  "m1_range_p99_pct": float(np.quantile(rng, 0.99) * 100.0) if len(rng) else 0.0,
                  "m1_range_max_pct": float(rng.max() * 100.0) if len(rng) else 0.0},
        "months": months,
    }


def format_quality(q: Dict) -> str:
    sp, g, d, j = q["spread"], q["gaps_over_3min"], q["days"], q["jumps"]
    lines = [
        f"{q['symbol']}  {q['first_tick'][:19]} .. {q['last_tick'][:19]} UTC",
        f"  ticks {q['ticks_total']:,} | active seconds {q['active_seconds']:,} | M1 bars {q['m1_bars']:,}",
        f"  dropped rows {q['rows_dropped_invalid']} | out-of-order rows {q['rows_out_of_order']} | "
        f"monotonic {q['timestamps_monotonic']}",
        f"  price {q['price']['min']:,.2f} .. {q['price']['max']:,.2f}",
        f"  spread median {sp['median']:.3f} ({sp['pct_of_price_median']:.4f}% of price) | p99 {sp['p99']:.3f} | "
        f"max {sp['max']:.3f} | non-positive {sp['non_positive']}",
        f"  gaps > 3 min: {g['count']} {g['by_kind']} | unexplained {len(g['unexplained'])}",
        *[f"  HOLE in the archive: {h['from'][:16]} .. {h['to'][:16]} UTC ({h['minutes'] / 60:.1f} h, price "
          f"{h['price_jump_pct']:+.2f}% across it)" for h in g.get("holes", [])],
        f"  days with ticks {d['with_ticks']} | unexpected missing days {d['missing'] or 'none'}",
        f"  largest 1 s move {j['max_1s_move_pct']:.3f}% | 1 s moves > 0.1%: {j['moves_over_0p1pct']} | "
        f"M1 range p99 {j['m1_range_p99_pct']:.3f}%",
    ]
    return "\n".join(lines)
