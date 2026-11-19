"""
Ladder study: the extra MT5 timeframes M4, M6, M12, M20, H3 and W1.

Importing this module registers them in ``config.TF_SECONDS`` (the dict object the engine reads at run time).
No existing configuration reads any of them, so no existing result can change (proved by the bit-identity
check in ``ladder_checks``).

* M4, M6, M12, M20 and H3 divide a day (86,400 s), so plain epoch bucketing (``t // tf_s``) reproduces MT5's
  bar opens, exactly as for the timeframes ``config.py`` already lists.
* W1 does not: epoch day 0 (1 Jan 1970) was a Thursday, and MT5's weekly bar opens on Sunday 00:00 server time
  (Exness server time = UTC). Its bar id is ``(t - 3 days) // 7 days``. The functions below take that offset;
  ``fast.prepare`` / ``store.resample_bars`` do not, so a W1 configuration must go through
  ``ladder_engine.prepare`` (which builds W1 itself and never passes it to the original code).
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from ..config import TF_SECONDS

NEW_TFS: Dict[str, int] = {"M4": 240, "M6": 360, "M12": 720, "M20": 1200, "H3": 10800, "W1": 604800}
W1_OFFSET_S = 3 * 86400          # 1970-01-04 00:00 UTC was the first Sunday after the epoch
OFFSET_S: Dict[str, int] = {"W1": W1_OFFSET_S}
OFFSET_TFS = tuple(OFFSET_S)

for _tf, _s in NEW_TFS.items():
    if TF_SECONDS.get(_tf, _s) != _s:
        raise RuntimeError(f"timeframe {_tf} already registered with another length")
TF_SECONDS.update(NEW_TFS)


def tf_offset(tf: str) -> int:
    """Seconds by which the bar grid of ``tf`` is shifted from the epoch grid (W1: 3 days, else 0)."""
    return OFFSET_S.get(tf, 0)


def bar_id(t_s, tf: str):
    """Bar number of epoch second(s) ``t_s`` on the MT5 grid of ``tf``."""
    return (np.asarray(t_s, np.int64) - tf_offset(tf)) // TF_SECONDS[tf]


def bar_open_s(ids, tf: str):
    """Open time (epoch s) of bar number(s) ``ids``."""
    return np.asarray(ids, np.int64) * TF_SECONDS[tf] + tf_offset(tf)


def window_bars(t_ms: np.ndarray, bid: np.ndarray, tf: str):
    """In-window bars from rows on the grid of ``tf``: (bar id, first row, close) -- ``fast._window_bars`` with the offset."""
    bar = (t_ms // 1000 - tf_offset(tf)) // TF_SECONDS[tf]
    first = np.flatnonzero(np.diff(bar, prepend=bar[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bar) - 1)
    return bar[first], first.astype(np.int64), bid[last]


def resample_ohlc(m1: Dict[str, np.ndarray], tf: str) -> Dict[str, np.ndarray]:
    """M1 bid bars aggregated to ``tf`` on its MT5 grid: t (bar open, epoch s), o, h, l, c, n."""
    if len(m1["t"]) == 0:
        z = np.zeros(0)
        return {"t": np.zeros(0, np.int64), "o": z, "h": z, "l": z, "c": z}
    tf_s = TF_SECONDS[tf]
    bar = (np.asarray(m1["t"], np.int64) - tf_offset(tf)) // tf_s
    first = np.flatnonzero(np.diff(bar, prepend=bar[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bar) - 1)
    return {"t": (bar[first] * tf_s + tf_offset(tf)).astype(np.int64),
            "o": np.asarray(m1["o"])[first].astype(np.float64),
            "h": np.maximum.reduceat(np.asarray(m1["h"], np.float64), first),
            "l": np.minimum.reduceat(np.asarray(m1["l"], np.float64), first),
            "c": np.asarray(m1["c"])[last].astype(np.float64)}
