"""
What do the two slope votes actually say?

An entry needs the RSI vote and the MACD vote of the agreement timeframe (M15 live) to point
the same way. This module measures, on closed bars and with the live ``indicator.py``
functions themselves:

* how the MACD vote relates to the trend its own signal line shows,
* which kind of pivot the RSI vote is measured from,
* what price did after the "both votes agree" state.

It describes the signal, not the trading result: no spread, no ladder, no exits. The live
bot reads the same votes on the still-forming bar about once a second; sampling them at
each bar close keeps the observations comparable and non-repainting.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Dict, Sequence

import numpy as np
import pandas as pd

from ..config import REPO_ROOT, TF_SECONDS, load_live_constants
from ..data import store

_INDICATOR_CACHE: dict = {}


def live_indicator(live_root: Path = REPO_ROOT):
    """An instance of the live ``Indicator`` class, loaded from ``live_root/indicator.py`` itself."""
    path = (Path(live_root) / "indicator.py").resolve()
    stamp = path.stat().st_mtime_ns
    hit = _INDICATOR_CACHE.get(str(path))
    if hit is None or hit[0] != stamp:
        name = "_alcadeias_live_indicator_" + hashlib.sha1(str(path).encode()).hexdigest()[:10]
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hit = (stamp, mod)
        _INDICATOR_CACHE[str(path)] = hit
    return hit[1].Indicator()


def votes(close: pd.Series, live_root: Path = REPO_ROOT, first: int = 0) -> pd.DataFrame:
    """
    The RSI and MACD pivot-slope votes at every closed bar from index ``first`` on, computed
    exactly as ``app.py`` does (same functions, same constants), with the bar itself as the
    current value.

    Columns: trend (sign of the MACD signal line), macd (vote), rsi (vote),
    rsi_side ('high' / 'low' / None: the pivot the RSI vote was measured from).
    """
    c = load_live_constants(live_root)
    ind = live_indicator(live_root)
    rsi = ind.calculate_rsi(close, c.RSI_LENGTH)
    macd = ind.calculate_macd(close, fast=c.MACD_FAST, slow=c.MACD_SLOW, signal=c.MACD_SIGNAL)
    hist, sig = macd["hist"], macd["signal"].to_numpy(float)
    look = int(c.PEAK_LOOKBACK) + 2 * int(c.PIVOT_WIDTH) + 2      # the function only ever looks this far back
    rows = []
    for i in range(first, len(close)):
        lo = max(0, i + 1 - look)
        s = sig[i]
        side = "high" if s > 0 else ("low" if s < 0 else None)
        m = ind.latest_pivot_slope(hist.iloc[lo:i + 1], lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH, side=side)
        r = ind.latest_pivot_slope(rsi.iloc[lo:i + 1], lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH,
                                   ob_level=c.RSI_PEAK_OB, os_level=c.RSI_PEAK_OS)
        rows.append((float(np.sign(s)) if s == s else 0.0, m["sign"], r["sign"], r["side"]))
    return pd.DataFrame(rows, columns=["trend", "macd", "rsi", "rsi_side"], index=close.index[first:])


def _pct(mask) -> float:
    return round(float(np.mean(mask)) * 100.0, 1) if len(mask) else float("nan")


def vote_study(symbol: str, start, end, live_root: Path = REPO_ROOT, tfs: Sequence[str] = ("M15", "H1"),
               horizons: Sequence[int] = (1, 4, 16), store_dir: Path = store.DEFAULT_STORE_DIR) -> Dict[str, dict]:
    """Per timeframe: what the votes are made of and what followed the states in which both agree."""
    start_ms, end_ms = store.to_ms(start), store.to_ms(end)
    out: Dict[str, dict] = {}
    for tf in tfs:
        tf_s = TF_SECONDS[tf]
        warm_ms = int(600 * tf_s * 1000 * 1.7)
        m1 = store.load_m1(symbol, start_ms - warm_ms, end_ms, store_dir)
        if not m1 or len(m1["t"]) == 0:
            continue
        b = store.resample_bars(m1, tf_s)
        close = pd.Series(np.asarray(b["c"], float))
        first = int(np.searchsorted(b["t"], start_ms // 1000))
        if first >= len(close):
            continue
        v = votes(close, live_root, first=first).reset_index(drop=True)
        px = close.to_numpy()[first:]
        n = len(v)
        up, dn = (v["macd"] == 1) & (v["rsi"] == 1), (v["macd"] == -1) & (v["rsi"] == -1)
        res = {
            "bars": int(n),
            "macd_vote": {
                "against_signal_line_trend_pct": _pct((v["macd"] != 0) & (v["macd"] == -v["trend"])),
                "with_signal_line_trend_pct": _pct((v["macd"] != 0) & (v["macd"] == v["trend"])),
                "grey_pct": _pct(v["macd"] == 0),
            },
            "rsi_vote": {
                "up_pct": _pct(v["rsi"] == 1), "down_pct": _pct(v["rsi"] == -1), "grey_pct": _pct(v["rsi"] == 0),
                # an "up" vote measured from an oversold pivot low is a bounce; from an overbought high it is a breakout
                "up_votes_measured_from_an_oversold_low_pct": _pct(v.loc[v["rsi"] == 1, "rsi_side"] == "low"),
                "down_votes_measured_from_an_overbought_high_pct": _pct(v.loc[v["rsi"] == -1, "rsi_side"] == "high"),
            },
            "both_up_share_pct": _pct(up), "both_down_share_pct": _pct(dn),
            "after": {},
        }
        for h in horizons:
            if n <= h:
                continue
            move = px[h:] - px[:-h]
            u, d = up.to_numpy()[:-h], dn.to_numpy()[:-h]
            res["after"][f"{h}_bars"] = {
                "both_up": {"n": int(u.sum()), "closed_higher_pct": _pct(move[u] > 0), "mean_move": round(float(move[u].mean()), 4) if u.any() else float("nan")},
                "both_down": {"n": int(d.sum()), "closed_lower_pct": _pct(move[d] < 0), "mean_move": round(float(move[d].mean()), 4) if d.any() else float("nan")},
                "all_bars": {"n": int(len(move)), "closed_higher_pct": _pct(move > 0), "mean_move": round(float(move.mean()), 4)},
            }
        out[tf] = res
    return out


PERIODS = [("HO1", "Aug–Nov 2025"), ("HO2", "Nov 2025–Feb 2026"), ("OOS2", "Feb–May 2026"), ("OOS1", "May–Aug 2026"),
           ("IS", "Aug–Nov 2026"), ("ALL", "All fifteen months")]


def vote_table(out: Path, symbol: str, tf: str, horizon: int = 4):
    """The vote study of ``experiments.stage_signal`` as one row per period (None when the stage has not run)."""
    import json
    p = Path(out) / "signal" / f"{symbol}.json"
    if not p.exists():
        return None
    j = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for key, label in PERIODS:
        r = (j.get(key) or {}).get(tf)
        if not r or f"{horizon}_bars" not in r["after"]:
            continue
        a = r["after"][f"{horizon}_bars"]
        rows.append({
            "period": label, "bars": r["bars"],
            "macd_against_trend_pct": r["macd_vote"]["against_signal_line_trend_pct"],
            "rsi_up_from_oversold_low_pct": r["rsi_vote"]["up_votes_measured_from_an_oversold_low_pct"],
            "rsi_down_from_overbought_high_pct": r["rsi_vote"]["down_votes_measured_from_an_overbought_high_pct"],
            "both_up_share_pct": r["both_up_share_pct"],
            "higher_after_both_up_pct": a["both_up"]["closed_higher_pct"],
            "higher_all_bars_pct": a["all_bars"]["closed_higher_pct"],
            "both_down_share_pct": r["both_down_share_pct"],
            "lower_after_both_down_pct": a["both_down"]["closed_lower_pct"],
            "lower_all_bars_pct": round(100.0 - a["all_bars"]["closed_higher_pct"], 1),
        })
    return pd.DataFrame(rows) if rows else None
