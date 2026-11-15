"""
Strategies from the literature, on the bot's bars, costs and account, standalone and combined with the bot's logic.

    python -m backtesting.research.external run    [--symbols XAUUSDm BTCUSDm] [--cache DIR] [--out DIR]
    python -m backtesting.research.external tables [--out DIR] [--update backtest_results/improve/external_strategies.md]

``run`` writes ``external_strategies.csv`` (one row per symbol, strategy, variant and period),
``external_strategies_blocks.csv`` (the same runs cut into quarter blocks) and
``external_v3lite_quarters.csv`` (the bar-level V3-lite on fresh quarterly accounts, for comparison
with the tick engine) to ``backtest_results/improve/``; ``tables`` prints the markdown tables of
``external_strategies.md`` or refreshes them in place. What was chosen and why is in that report.

The model
---------
* Data. M1 bid bars of the tick store from 2022-12-01 on (December 2022 only warms the indicators
  up); nothing earlier is ever read. ``ask = bid + the bar's mean spread``. One unit is 0.01 lot:
  gold pays 1 USD per 1.00 of price, BTC 0.01 USD.
* Bars of a strategy's timeframe are built from the M1 bars on UTC boundaries (MT5 on Exness runs
  on UTC). A UTC day with fewer than six hours of quotes (gold's Sunday evening, holiday stubs) is
  merged into the next day, so a "20-day" window is 20 trading days.
* Signals are read on CLOSED bars of the strategy's timeframe: a bar may be used from its close
  time on. The order is filled at the open of the first M1 bar at or after that time: a buy at
  the ask, a sell at the bid. Intraday rules decide at fixed clock times (the close of the M1 bar
  ending then) and need a quote within three minutes of the decision to enter.
* Stops, targets, trailing stops, pyramid adds and stop-entry orders are checked on every M1 bar:
  first a gap at the open (filled at the open), then the unfavourable extreme before the favourable
  one, so a bar that reaches both the stop and the target is a stop. A stop-entry order filled
  inside a bar is assumed to have met the bar's opposite extreme afterwards (it can be stopped in
  its own bar, it cannot reach its target there). Stops of a buy are on the bid, of a sell on the
  ask; a buy-stop entry triggers on the ask, a sell-stop entry on the bid.
* One position per strategy (the Turtle may pyramid up to four units of one position).
* Account. $2,000, nothing withdrawn, no swap (the bot's backtester treats the Standard account as
  swap-free). Sizing: the bot's unit rule (unit = floor(balance / 2,500) + 1, at most 10, re-derived
  when a position opens) unless a row says otherwise; risk-based rows use the rule their source
  prescribes, rounded DOWN to the 0.01-lot step - a trade whose budget cannot buy 0.01 lot is taken
  at zero size, so the strategy's sequence of trades is unchanged. The account is wiped when its
  equity, marked at the worst price of an M1 bar, reaches 0.
* Max drawdown is measured against the running peak of the equity marked at M1 closes, with the
  troughs at the worst price inside each M1 bar.
* Every period is its own account: it starts flat with $2,000 at the period start (indicators see
  all the history before it, which is allowed - it is the past) and whatever is open at the end is
  closed at the last bar's close.

``tests/test_external.py`` checks the simulator on hand-made bars and that every strategy, the
bot's filters and V3-lite make the same decisions up to a time T when the history after T is
removed or replaced.
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..analysis.signal import votes
from ..config import REPO_ROOT, SYMBOLS as SPECS
from ..data import store
from ..engine.kernels import vol_array

OUT = REPO_ROOT / "backtest_results" / "improve"
SYMBOLS = ("XAUUSDm", "BTCUSDm")
EARLIEST = "2022-12-01"            # nothing before this is ever read
DATA_END = "2026-11-13"            # exclusive
# [start, end) in UTC
PERIODS: Dict[str, Tuple[str, str]] = {
    "2023": ("2023-02-01", "2024-01-01"),
    "2024-25": ("2024-01-01", "2025-07-01"),
    "2025-26": ("2025-07-01", "2026-11-13"),
}
ACCOUNT = 2000.0
STEP_UP = 2500.0
UNIT_MAX = 10
QUARTER_S = 365.25 / 4 * 86400
DAY = 86400
NY = "America/New_York"
LIVE_S = 180.0                     # an intraday order needs a quote within three minutes (the bot's own rule)
DAY_MIN_BARS = 360                 # a UTC day with fewer M1 bars is merged into the next day
INF = math.inf
NAN = math.nan

# why a trade ended
WHY_SIGNAL, WHY_STOP, WHY_TARGET, WHY_END, WHY_GAP_STOP, WHY_GAP_TARGET = 1, 2, 3, 4, 5, 6
WHY_NAMES = {1: "signal", 2: "stop", 3: "target", 4: "end", 5: "gap stop", 6: "gap target"}

# the quarter blocks of the tick engine's V3-lite results (fresh $2,000 each), for the comparison table
ENGINE_BLOCKS: Dict[str, List[str]] = {
    "2023": ["2023-02-01", "2023-05-01", "2023-08-01", "2023-11-01", "2024-01-01"],
    "2024-25": ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01", "2025-04-01", "2025-07-01"],
    "2025-26": ["2025-08-13", "2025-11-13", "2026-02-13", "2026-05-13", "2026-08-13", "2026-11-13"],
}
# tick engine, V3-lite, average per quarter (IMPROVEMENT.md, round 2): FINAL 2023, CONFIRM, DEV
ENGINE_V3LITE = {"XAUUSDm": {"2023": 106.0, "2024-25": 152.0, "2025-26": 404.0},
                 "BTCUSDm": {"2023": 7.0, "2024-25": 48.0, "2025-26": 114.0}}


# ───────────────────────────── market data ─────────────────────────────

@dataclass
class Bars:
    """Bars of one timeframe built from M1 bars. ``tc``: the time from which the bar is closed and may be read;
    ``ex``: the M1 bar whose open fills an order decided at ``tc``; ``i0`` / ``i1``: its first and last M1 bar."""
    t: np.ndarray
    tc: np.ndarray
    i0: np.ndarray
    i1: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    ex: np.ndarray

    def __len__(self) -> int:
        return int(len(self.t))


class Market:
    """M1 bid bars of one symbol plus what is derived from them (bars, local clocks), computed on demand."""

    def __init__(self, symbol: str, m1: Dict[str, np.ndarray]):
        self.symbol = symbol
        spec = SPECS[symbol]
        self.k = spec.contract_size * 0.01                 # USD per 1.00 of price on one unit (0.01 lot)
        self.tick = 10.0 ** (-spec.digits)
        self.around_the_clock = spec.data_hole_s > 0        # BTC: 7 days a week, no daily break
        self.t = np.ascontiguousarray(m1["t"], np.int64)
        self.o = np.ascontiguousarray(m1["o"], np.float64)
        self.h = np.ascontiguousarray(m1["h"], np.float64)
        self.l = np.ascontiguousarray(m1["l"], np.float64)
        self.c = np.ascontiguousarray(m1["c"], np.float64)
        self.sp = np.ascontiguousarray(m1["spread_mean"], np.float64)
        self.n = np.ascontiguousarray(m1["n"], np.float64)
        self._bars: Dict[str, Bars] = {}
        self._local: Dict[str, np.ndarray] = {}

    def __len__(self) -> int:
        return int(len(self.t))

    @property
    def year_days(self) -> float:
        """Days in a year of this market's daily bars (annualisation)."""
        return 365.0 if self.around_the_clock else 261.0

    def bars(self, tf: str) -> Bars:
        if tf not in self._bars:
            self._bars[tf] = day_bars(self) if tf == "D1" else tf_bars(self, {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400}[tf])
        return self._bars[tf]

    def local(self, tz: str = NY) -> np.ndarray:
        """Wall-clock seconds of every M1 bar's open in ``tz`` (as if that clock were UTC)."""
        if tz not in self._local:
            self._local[tz] = local_seconds(self.t, tz)
        return self._local[tz]

    def ix(self, when) -> int:
        """Index of the first M1 bar at or after ``when``."""
        return int(np.searchsorted(self.t, store.to_ms(when) // 1000, side="left"))


def load_market(symbol: str, store_dir: Path = store.DEFAULT_STORE_DIR, earliest: str = EARLIEST,
                end: str = DATA_END) -> Market:
    """M1 bars [earliest, end). The defaults are this study's span; ``final10.py`` reads a longer history."""
    m1 = store.load_m1(symbol, earliest, end, store_dir)
    if not m1 or len(m1["t"]) == 0:
        raise FileNotFoundError(f"no M1 bars for {symbol} from {earliest} in the store")
    return Market(symbol, m1)


def _group(m: Market, bucket: np.ndarray, t_open: np.ndarray, t_close: np.ndarray, keep: Optional[np.ndarray] = None) -> Bars:
    idx = np.arange(len(m), dtype=np.int64)
    if keep is not None:
        idx, bucket, t_open, t_close = idx[keep], bucket[keep], t_open[keep], t_close[keep]
    if len(idx) == 0:
        z, zi = np.zeros(0), np.zeros(0, np.int64)
        return Bars(zi, zi, zi, zi, z, z, z, z, zi)
    first = np.flatnonzero(np.diff(bucket, prepend=bucket[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bucket) - 1)
    i0, i1 = idx[first], idx[last]
    h = np.maximum.reduceat(m.h[idx], first)
    l = np.minimum.reduceat(m.l[idx], first)
    tc = t_close[first].astype(np.int64)
    return Bars(t_open[first].astype(np.int64), tc, i0, i1, m.o[i0].copy(), h, l, m.c[i1].copy(),
                np.searchsorted(m.t, tc, side="left").astype(np.int64))


def tf_bars(m: Market, tf_s: int) -> Bars:
    b = m.t // tf_s
    return _group(m, b, b * tf_s, b * tf_s + tf_s)


def day_bars(m: Market, min_bars: int = DAY_MIN_BARS) -> Bars:
    """UTC days; a day with fewer than ``min_bars`` M1 bars is merged into the next full day (it closes when that day ends)."""
    if len(m) == 0:
        return tf_bars(m, DAY)
    day = m.t // DAY
    first = np.flatnonzero(np.diff(day, prepend=day[0] - 1) != 0)
    count = np.diff(np.append(first, len(day)))
    days = day[first]
    group = np.empty(len(days), np.int64)
    opens, closes = [], []
    g, start = 0, -1
    for d in range(len(days)):
        if start < 0:
            start = int(days[d])
        group[d] = g
        if count[d] >= min_bars:
            opens.append(start * DAY)
            closes.append((int(days[d]) + 1) * DAY)
            g, start = g + 1, -1
    per_bar = np.repeat(group, count)
    keep = per_bar < g
    opens_a = np.asarray(opens + [0], np.int64)
    closes_a = np.asarray(closes + [0], np.int64)
    return _group(m, per_bar, opens_a[np.minimum(per_bar, g)], closes_a[np.minimum(per_bar, g)], keep)


def local_seconds(t_utc: np.ndarray, tz: str) -> np.ndarray:
    """UTC epoch seconds -> the wall-clock time in ``tz``, as epoch seconds of that clock."""
    if len(t_utc) == 0:
        return np.zeros(0, np.int64)
    idx = pd.to_datetime(np.asarray(t_utc, np.int64), unit="s", utc=True).tz_convert(tz).tz_localize(None)
    return idx.values.astype("datetime64[s]").astype(np.int64)


def utc_of_local(local_s: np.ndarray, tz: str) -> np.ndarray:
    """Wall-clock seconds in ``tz`` -> UTC epoch seconds (-1 for a time that does not exist or is ambiguous)."""
    local_s = np.asarray(local_s, np.int64)
    if len(local_s) == 0:
        return np.zeros(0, np.int64)
    idx = pd.DatetimeIndex(pd.to_datetime(local_s, unit="s")).tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    bad = idx.isna()
    out = np.full(len(local_s), -1, np.int64)
    ok = ~bad
    out[ok] = idx[ok].tz_convert("UTC").tz_localize(None).values.astype("datetime64[s]").astype(np.int64)
    return out


def value_at(tc: np.ndarray, values: np.ndarray, T: np.ndarray, default=0):
    """``values`` of the last bar closed by each time in ``T`` (``default`` before the first one)."""
    i = np.searchsorted(tc, np.asarray(T, np.int64), side="right") - 1
    out = np.asarray(values)[np.maximum(i, 0)]
    return np.where(i >= 0, out, default)


# ───────────────────────────── indicators (closed bars; element i uses bars 0..i) ─────────────────────────────

def sma(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, np.float64)).rolling(n, min_periods=n).mean().to_numpy()


def roll_max(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, np.float64)).rolling(n, min_periods=n).max().to_numpy()


def roll_min(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, np.float64)).rolling(n, min_periods=n).min().to_numpy()


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's moving average (RMA), seeded with the simple mean of the first n values; NaN before."""
    x = np.asarray(x, np.float64)
    out = np.full(len(x), np.nan)
    good = np.flatnonzero(np.isfinite(x))
    if len(good) < n:
        return out
    s = good[0]
    if s + n > len(x):
        return out
    v = float(np.mean(x[s:s + n]))
    out[s + n - 1] = v
    for i in range(s + n, len(x)):
        v = (v * (n - 1) + x[i]) / n
        out[i] = v
    return out


def wilder_rsi(c: np.ndarray, n: int) -> np.ndarray:
    c = np.asarray(c, np.float64)
    d = np.diff(c, prepend=np.nan)
    ag = wilder(np.where(np.isfinite(d), np.maximum(d, 0.0), np.nan), n)
    al = wilder(np.where(np.isfinite(d), np.maximum(-d, 0.0), np.nan), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(al > 0, 100.0 - 100.0 / (1.0 + ag / al), np.where(ag > 0, 100.0, 50.0))
    return np.where(np.isfinite(ag) & np.isfinite(al), rsi, np.nan)


def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    prev = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    if len(tr):
        tr[0] = h[0] - l[0]
    return tr


def wilder_atr(h, l, c, n: int) -> np.ndarray:
    return wilder(true_range(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)), n)


def returns(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, np.float64)
    r = np.full(len(c), np.nan)
    r[1:] = c[1:] / c[:-1] - 1.0
    return r


# ───────────────────────────── the bot's own signals ─────────────────────────────

@dataclass
class BotSignals:
    """The bot's votes on closed bars: M15 agreement (+1 both votes up, -1 both down), H1 votes as V3-lite reads
    them (open score with the grey fill, +1 / -1 when it reaches 2), the H1 trend (sign of the MACD signal line)
    and the H1 volatility unit (exponentially weighted mean absolute close-to-close change, 24 bars)."""
    m15_tc: np.ndarray
    m15_ex: np.ndarray
    m15_agree: np.ndarray
    h1_tc: np.ndarray
    h1_open: np.ndarray
    h1_trend: np.ndarray
    h1_vol: np.ndarray

    def votes_at(self, T) -> np.ndarray:
        return value_at(self.m15_tc, self.m15_agree, T, 0)

    def trend_at(self, T) -> np.ndarray:
        return value_at(self.h1_tc, self.h1_trend, T, 0)


def bot_signals(m: Market, cache_dir: Optional[Path] = None) -> BotSignals:
    path = None
    if cache_dir is not None:
        path = Path(cache_dir) / f"external_botsig_{m.symbol}_{len(m)}_{int(m.t[0])}_{int(m.t[-1])}_{m.c[-1]:.5f}.npz"
        if path.exists():
            with np.load(path) as z:
                return BotSignals(**{k: z[k] for k in z.files})
    m15, h1 = m.bars("M15"), m.bars("H1")
    v15 = votes(pd.Series(m15.c))
    agree = np.where((v15["macd"] == 1) & (v15["rsi"] == 1), 1, np.where((v15["macd"] == -1) & (v15["rsi"] == -1), -1, 0))
    v1 = votes(pd.Series(h1.c))
    r, mm = v1["rsi"].to_numpy(np.int64), v1["macd"].to_numpy(np.int64)
    rr = np.where((r == 0) & (mm != 0), mm, r)              # grey fill: a 0 borrows the other indicator's sign
    mf = np.where((mm == 0) & (r != 0), r, mm)
    score = rr + mf
    sig = BotSignals(m15_tc=m15.tc, m15_ex=m15.ex, m15_agree=agree.astype(np.int8), h1_tc=h1.tc,
                     h1_open=np.where(score >= 2, 1, np.where(score <= -2, -1, 0)).astype(np.int8),
                     h1_trend=v1["trend"].to_numpy(np.float64).astype(np.int8),
                     h1_vol=np.asarray(vol_array(np.ascontiguousarray(h1.c, np.float64), 24), np.float64))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **{k: getattr(sig, k) for k in sig.__dataclass_fields__})
    return sig


# ───────────────────────────── plans ─────────────────────────────

FLOATS = ("sl", "slf", "slcap", "tp", "tpr", "ber", "bstop", "sstop", "bsl", "ssl", "trl", "trs", "pstep", "rk", "expo")


@dataclass
class PathPlan:
    """
    Decisions of a strategy, one per row, in time order. ``dt`` decision time, ``dx`` the M1 bar whose open
    executes it. ``want`` the entry direction while flat, ``xl`` / ``xs`` close a long / a short. Stops for an
    entry of this decision: ``sl`` price distance, ``slf`` fraction of the entry, ``slcap`` cap on the distance as a
    fraction, ``bsl`` / ``ssl`` absolute levels for a fill of the buy / sell stop order (the tightest applies).
    ``tp`` target distance, ``tpr`` target in multiples of the initial risk, ``ber`` stop to break-even after
    this many R. ``bstop`` / ``sstop`` stop-entry orders valid until the next decision (one fill cancels both).
    ``trl`` / ``trs`` trailing stop levels from this decision on. ``pstep`` / ``pmax`` pyramid: add a unit every
    ``pstep`` in favour, up to ``pmax`` units, all stops then ``sl`` from the last fill. ``rk`` the price distance
    a risk-sized row risks its fraction on (else the initial stop distance), ``expo`` exposure for exposure sizing.
    ``alw_l`` / ``alw_s`` filters on entries at the decision, ``m_l`` / ``m_s`` on stop-entry fills per M1 bar.
    """
    dt: np.ndarray
    dx: np.ndarray
    want: np.ndarray
    xl: np.ndarray
    xs: np.ndarray
    f: Dict[str, np.ndarray]
    pmax: np.ndarray
    alw_l: np.ndarray
    alw_s: np.ndarray
    live_s: float = INF
    pause_win_s: float = 0.0
    pause_loss_s: float = 0.0
    orders: bool = False
    m_l: Optional[np.ndarray] = None
    m_s: Optional[np.ndarray] = None

    def __len__(self) -> int:
        return int(len(self.dt))

    def copy(self, **kw) -> "PathPlan":
        d = dict(dt=self.dt, dx=self.dx, want=self.want, xl=self.xl, xs=self.xs, f=self.f, pmax=self.pmax,
                 alw_l=self.alw_l, alw_s=self.alw_s, live_s=self.live_s, pause_win_s=self.pause_win_s,
                 pause_loss_s=self.pause_loss_s, orders=self.orders, m_l=self.m_l, m_s=self.m_s)
        d.update(kw)
        return PathPlan(**d)


@dataclass
class TargetPlan:
    """Target positions: at each decision hold ``w`` x equity of notional (signed). A change is traded when it is a
    signal (``force``) or larger than ``thr`` x the target; ``active`` False rows are only used to open the first
    position of a period. ``cap_lev`` caps the notional at that multiple of equity."""
    dt: np.ndarray
    dx: np.ndarray
    w: np.ndarray
    force: np.ndarray
    active: np.ndarray
    thr: float = 0.0
    cap_lev: float = 0.0

    def __len__(self) -> int:
        return int(len(self.dt))


def make_plan(m: Market, dt, want=None, xl=None, xs=None, pmax=None, live_s: float = INF, pause_win_s: float = 0.0,
              pause_loss_s: float = 0.0, orders: bool = False, **floats) -> PathPlan:
    dt = np.asarray(dt, np.int64)
    K = len(dt)
    order = np.argsort(dt, kind="stable")

    def arr(x, dtype, fill):
        if x is None:
            return np.full(K, fill, dtype)
        a = np.asarray(x)
        if a.ndim == 0:
            return np.full(K, a.item(), dtype)
        return a.astype(dtype)[order]

    dt = dt[order]
    dx = np.searchsorted(m.t, dt, side="left").astype(np.int64)
    f = {name: arr(floats.get(name), np.float64, NAN) for name in FLOATS}
    unknown = set(floats) - set(FLOATS)
    if unknown:
        raise TypeError(f"unknown plan fields {sorted(unknown)}")
    plan = PathPlan(dt=dt, dx=dx, want=arr(want, np.int64, 0), xl=arr(xl, np.bool_, False), xs=arr(xs, np.bool_, False),
                    f=f, pmax=arr(pmax, np.int64, 1), alw_l=np.ones(K, np.bool_), alw_s=np.ones(K, np.bool_),
                    live_s=float(live_s), pause_win_s=float(pause_win_s), pause_loss_s=float(pause_loss_s), orders=orders)
    keep = dx < len(m)
    if not keep.all():
        plan = select(plan, keep)
    return plan


def select(plan: PathPlan, keep: np.ndarray) -> PathPlan:
    return plan.copy(dt=plan.dt[keep], dx=plan.dx[keep], want=plan.want[keep], xl=plan.xl[keep], xs=plan.xs[keep],
                     f={k: v[keep] for k, v in plan.f.items()}, pmax=plan.pmax[keep], alw_l=plan.alw_l[keep],
                     alw_s=plan.alw_s[keep])


def merge_plans(m: Market, parts: Sequence[dict], **common) -> PathPlan:
    """One plan from several groups of decisions (each a dict of make_plan arguments)."""
    keys = set()
    for p in parts:
        keys |= set(p)
    dt = np.concatenate([np.asarray(p["dt"], np.int64) for p in parts])
    kw = {}
    for k in keys - {"dt"}:
        cols = []
        for p in parts:
            n = len(np.asarray(p["dt"]))
            v = p.get(k)
            if v is None:
                fill = {"want": 0, "xl": False, "xs": False, "pmax": 1}.get(k, NAN)
                cols.append(np.full(n, fill))
            else:
                a = np.asarray(v)
                cols.append(np.full(n, a.item()) if a.ndim == 0 else a)
        kw[k] = np.concatenate(cols)
    kw.update(common)
    return make_plan(m, dt, **kw)


def filtered(plan: PathPlan, m: Market, dir_at: Callable[[np.ndarray], np.ndarray]) -> PathPlan:
    """The plan with entries kept only where ``dir_at`` (a direction known at that time) agrees with them."""
    d = np.asarray(dir_at(plan.dt))
    kw = dict(alw_l=plan.alw_l & (d == 1), alw_s=plan.alw_s & (d == -1))
    if plan.orders:
        dm = np.asarray(dir_at(m.t))
        ml = dm == 1 if plan.m_l is None else plan.m_l & (dm == 1)
        ms = dm == -1 if plan.m_s is None else plan.m_s & (dm == -1)
        kw.update(m_l=np.ascontiguousarray(ml), m_s=np.ascontiguousarray(ms))
    return plan.copy(**kw)


# ───────────────────────────── kernels ─────────────────────────────

@njit(cache=True)
def _tightest(d, px, sl, slf, slcap, lvl, trail):
    """
    The initial stop of a position entered at ``px`` in direction ``d``: the tightest of the specifications given
    (NaN = not given): a distance, a fraction of the entry, an absolute level whose distance is capped at ``slcap``
    of the entry, a trailing level. -inf / +inf when there is none.
    """
    st = -np.inf if d == 1 else np.inf
    if sl == sl:
        v = px - d * sl
        st = max(st, v) if d == 1 else min(st, v)
    if slf == slf:
        v = px * (1.0 - d * slf)
        st = max(st, v) if d == 1 else min(st, v)
    if lvl == lvl:
        v = lvl
        if slcap == slcap:
            cap = px * (1.0 - d * slcap)
            v = max(v, cap) if d == 1 else min(v, cap)
        st = max(st, v) if d == 1 else min(st, v)
    if trail == trail:
        st = max(st, trail) if d == 1 else min(st, trail)
    return st


@njit(cache=True)
def _path_kernel(t, o, h, l, c, sp,
                 dx, dt, want, xl, xs,
                 sl, slf, slcap, tp, tpr, ber, bstop, sstop, bsl, ssl, trl, trs, pstep, pmax, rk, expo,
                 alw_l, alw_s, m_l, m_s, live_s, start_ix, end_ix, pause_win, pause_loss):
    """
    The trades of one plan between ``start_ix`` and ``end_ix`` (exclusive), at one unit. Returns per trade:
    direction, entry bar and first fill, exit bar and price, reason, the risk distance, the exposure, first leg
    and number of legs; and per leg: its entry bar and fill. Prices are what was paid: buys at the ask.
    """
    K = dx.shape[0]
    pm = 1
    for q in range(K):
        if pmax[q] > pm:
            pm = pmax[q]
    cap_t = 2 * K + 4
    T_dir = np.zeros(cap_t, np.int64)
    T_eix = np.zeros(cap_t, np.int64)
    T_epx = np.zeros(cap_t)
    T_xix = np.zeros(cap_t, np.int64)
    T_xpx = np.zeros(cap_t)
    T_why = np.zeros(cap_t, np.int64)
    T_risk = np.zeros(cap_t)
    T_expo = np.zeros(cap_t)
    T_leg0 = np.zeros(cap_t, np.int64)
    T_nleg = np.zeros(cap_t, np.int64)
    L_eix = np.zeros(cap_t * pm, np.int64)
    L_epx = np.zeros(cap_t * pm)
    nt = 0
    nl = 0
    pos = 0
    e_px = 0.0
    stop = 0.0
    target = 0.0
    be_lvl = np.nan
    sl_d = np.nan
    p_step = np.nan
    p_max = 1
    units = 0
    last_fill = 0.0
    o_k = -1
    o_b = np.nan
    o_s = np.nan
    next_ok = -1e300
    kk = 0
    while kk < K and dx[kk] < start_ix:
        kk += 1
    for j in range(start_ix, end_ix):
        exited = False
        ask_o = o[j] + sp[j]
        xp = 0.0
        why = 0
        pl = 0.0
        # 1. a gap through the stop or the target at the open
        if pos != 0:
            if pos == 1:
                if o[j] <= stop:
                    xp, why = o[j], 5
                elif o[j] >= target:
                    xp, why = o[j], 6
            else:
                if ask_o >= stop:
                    xp, why = ask_o, 5
                elif ask_o <= target:
                    xp, why = ask_o, 6
            if why != 0:
                pl = 0.0
                for q in range(T_leg0[nt], T_leg0[nt] + units):
                    pl += pos * (xp - L_epx[q])
                T_xix[nt] = j
                T_xpx[nt] = xp
                T_why[nt] = why
                T_nleg[nt] = units
                nt += 1
                pos = 0
                next_ok = t[j] + (pause_loss if pl < 0 else pause_win)
        # 2. decisions executed at this open
        while kk < K and dx[kk] == j:
            closed = 0
            if (pos == 1 and xl[kk]) or (pos == -1 and xs[kk]):
                xp = o[j] if pos == 1 else ask_o
                pl = 0.0
                for q in range(T_leg0[nt], T_leg0[nt] + units):
                    pl += pos * (xp - L_epx[q])
                T_xix[nt] = j
                T_xpx[nt] = xp
                T_why[nt] = 1
                T_nleg[nt] = units
                nt += 1
                closed = pos
                pos = 0
                next_ok = t[j] + (pause_loss if pl < 0 else pause_win)
            if pos == 1 and trl[kk] == trl[kk] and trl[kk] > stop:
                stop = trl[kk]
            if pos == -1 and trs[kk] == trs[kk] and trs[kk] < stop:
                stop = trs[kk]
            d = want[kk]
            if (pos == 0 and d != 0 and d != closed and dt[kk] >= next_ok and (t[j] - dt[kk]) <= live_s
                    and ((d == 1 and alw_l[kk]) or (d == -1 and alw_s[kk]))):
                px = ask_o if d == 1 else o[j]
                st = _tightest(d, px, sl[kk], slf[kk], np.nan, np.nan, trl[kk] if d == 1 else trs[kk])
                rsk = abs(px - st) if (st > -np.inf and st < np.inf) else np.nan
                tg = np.inf if d == 1 else -np.inf
                if tp[kk] == tp[kk]:
                    tg = px + d * tp[kk]
                elif tpr[kk] == tpr[kk] and rsk == rsk:
                    tg = px + d * tpr[kk] * rsk
                pos = d
                e_px = px
                stop = st
                target = tg
                be_lvl = px + d * ber[kk] * rsk if (ber[kk] == ber[kk] and rsk == rsk) else np.nan
                sl_d = sl[kk]
                p_step = pstep[kk]
                p_max = pmax[kk]
                units = 1
                last_fill = px
                T_dir[nt] = d
                T_eix[nt] = j
                T_epx[nt] = px
                T_risk[nt] = rk[kk] if rk[kk] == rk[kk] else rsk
                T_expo[nt] = expo[kk]
                T_leg0[nt] = nl
                L_eix[nl] = j
                L_epx[nl] = px
                nl += 1
            o_k = kk
            o_b = bstop[kk]
            o_s = sstop[kk]
            kk += 1
        # 3. inside the bar: stop before target, then adds and the break-even move
        if pos == 1:
            if l[j] <= stop:
                xp, why = stop, 2
            elif h[j] >= target:
                xp, why = target, 3
            else:
                why = 0
                while units < p_max and p_step == p_step:
                    lvl = last_fill + p_step
                    if h[j] + sp[j] >= lvl:
                        fp = max(lvl, ask_o)
                        L_eix[nl] = j
                        L_epx[nl] = fp
                        nl += 1
                        units += 1
                        last_fill = fp
                        if sl_d == sl_d and fp - sl_d > stop:
                            stop = fp - sl_d
                    else:
                        break
                if be_lvl == be_lvl and h[j] >= be_lvl and stop < e_px:
                    stop = e_px
            if why != 0:
                pl = 0.0
                for q in range(T_leg0[nt], T_leg0[nt] + units):
                    pl += xp - L_epx[q]
                T_xix[nt] = j
                T_xpx[nt] = xp
                T_why[nt] = why
                T_nleg[nt] = units
                nt += 1
                pos = 0
                exited = True
                next_ok = t[j] + 60 + (pause_loss if pl < 0 else pause_win)
        elif pos == -1:
            if h[j] + sp[j] >= stop:
                xp, why = stop, 2
            elif l[j] + sp[j] <= target:
                xp, why = target, 3
            else:
                why = 0
                while units < p_max and p_step == p_step:
                    lvl = last_fill - p_step
                    if l[j] <= lvl:
                        fp = min(lvl, o[j])
                        L_eix[nl] = j
                        L_epx[nl] = fp
                        nl += 1
                        units += 1
                        last_fill = fp
                        if sl_d == sl_d and fp + sl_d < stop:
                            stop = fp + sl_d
                    else:
                        break
                if be_lvl == be_lvl and l[j] + sp[j] <= be_lvl and stop > e_px:
                    stop = e_px
            if why != 0:
                pl = 0.0
                for q in range(T_leg0[nt], T_leg0[nt] + units):
                    pl += L_epx[q] - xp
                T_xix[nt] = j
                T_xpx[nt] = xp
                T_why[nt] = why
                T_nleg[nt] = units
                nt += 1
                pos = 0
                exited = True
                next_ok = t[j] + 60 + (pause_loss if pl < 0 else pause_win)
        # 4. stop-entry orders (flat since the start of the bar)
        if pos == 0 and not exited and o_k >= 0 and t[j] >= next_ok:
            hb = o_b == o_b and h[j] + sp[j] >= o_b and m_l[j]
            hs = o_s == o_s and l[j] <= o_s and m_s[j]
            if hb and hs:
                if (o_b - ask_o) <= (o[j] - o_s):
                    hs = False
                else:
                    hb = False
            if hb or hs:
                d = 1 if hb else -1
                px = max(o_b, ask_o) if d == 1 else min(o_s, o[j])
                st = _tightest(d, px, sl[o_k], slf[o_k], slcap[o_k], bsl[o_k] if d == 1 else ssl[o_k],
                               trl[o_k] if d == 1 else trs[o_k])
                rsk = abs(px - st) if (st > -np.inf and st < np.inf) else np.nan
                tg = np.inf if d == 1 else -np.inf
                if tp[o_k] == tp[o_k]:
                    tg = px + d * tp[o_k]
                elif tpr[o_k] == tpr[o_k] and rsk == rsk:
                    tg = px + d * tpr[o_k] * rsk
                pos = d
                e_px = px
                stop = st
                target = tg
                be_lvl = px + d * ber[o_k] * rsk if (ber[o_k] == ber[o_k] and rsk == rsk) else np.nan
                sl_d = sl[o_k]
                p_step = pstep[o_k]
                p_max = pmax[o_k]
                units = 1
                last_fill = px
                T_dir[nt] = d
                T_eix[nt] = j
                T_epx[nt] = px
                T_risk[nt] = rk[o_k] if rk[o_k] == rk[o_k] else rsk
                T_expo[nt] = expo[o_k]
                T_leg0[nt] = nl
                L_eix[nl] = j
                L_epx[nl] = px
                nl += 1
                o_b = np.nan
                o_s = np.nan
                # the bar's opposite extreme is taken to come after the fill
                hit = (l[j] <= stop) if d == 1 else (h[j] + sp[j] >= stop)
                if hit:
                    T_xix[nt] = j
                    T_xpx[nt] = stop
                    T_why[nt] = 2
                    T_nleg[nt] = 1
                    nt += 1
                    pos = 0
                    pl = d * (stop - px)
                    next_ok = t[j] + 60 + (pause_loss if pl < 0 else pause_win)
        # 5. the end of the period
        if j == end_ix - 1 and pos != 0:
            xp = c[j] if pos == 1 else c[j] + sp[j]
            T_xix[nt] = j
            T_xpx[nt] = xp
            T_why[nt] = 4
            T_nleg[nt] = units
            nt += 1
            pos = 0
    return (T_dir[:nt], T_eix[:nt], T_epx[:nt], T_xix[:nt], T_xpx[:nt], T_why[:nt], T_risk[:nt], T_expo[:nt],
            T_leg0[:nt], T_nleg[:nt], L_eix[:nl], L_epx[:nl])


@njit(cache=True)
def _account_kernel(t, o, h, l, c, sp, k,
                    T_dir, T_eix, T_epx, T_xix, T_xpx, T_why, T_risk, T_expo, T_leg0, T_nleg, L_eix, L_epx,
                    mode, rf, cap_lev, brake, bnd, years, bal0, step_up, unit_max):
    """
    Sizes the trades of a path on one account and marks it on every M1 bar. mode 0: the bot's unit rule;
    1: ``rf`` of equity (the Turtle brake's notional with ``brake``) over the trade's risk distance; 2: the
    trade's exposure x equity of notional. Lots are rounded down to whole units of 0.01 lot.
    """
    nt = T_dir.shape[0]
    nb = bnd.shape[0]
    steps = np.zeros(nt)
    pnl = np.zeros(nt)
    eqb = np.full(nb, np.nan)
    bal = bal0
    peak = bal0
    maxdd = 0.0
    wiped = False
    wipe_ix = -1
    n_done = 0
    bi = 0
    year = -1
    ys = bal0
    for i in range(nt):
        n_done = i + 1
        e = T_eix[i]
        x = T_xix[i]
        d = T_dir[i]
        while bi < nb and bnd[bi] <= e:
            eqb[bi] = bal
            bi += 1
        yr = np.searchsorted(years, t[e], side="right")
        if yr != year:
            year = yr
            ys = bal
        s = 0.0
        if mode == 0:
            s = math.floor(bal / step_up) + 1.0
            if s > unit_max:
                s = unit_max
        elif mode == 1:
            notional = bal
            if brake and bal < ys:
                notional = ys * 0.8 ** math.floor((ys - bal) / ys / 0.1 + 1e-12)
            if T_risk[i] > 0:
                s = math.floor(rf * notional / (T_risk[i] * k) + 1e-9)
        else:
            if T_expo[i] == T_expo[i] and T_expo[i] > 0:
                s = math.floor(T_expo[i] * bal / (T_epx[i] * k) + 1e-9)
        if cap_lev > 0:
            smax = math.floor(cap_lev * bal / (T_epx[i] * k) + 1e-9)
            if s > smax:
                s = smax
        if s < 0:
            s = 0.0
        steps[i] = s
        if s == 0:
            continue
        for j in range(e, x + 1):
            uc = 0.0
            uw = 0.0
            for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
                if L_eix[q] > j:
                    continue
                ep = L_epx[q]
                if j == x:
                    mc = T_xpx[i]
                    why = T_why[i]
                    if why == 3 or why == 4:
                        mw = l[j] if d == 1 else h[j] + sp[j]
                    else:
                        mw = T_xpx[i]
                else:
                    mc = c[j] if d == 1 else c[j] + sp[j]
                    mw = l[j] if d == 1 else h[j] + sp[j]
                uc += s * k * d * (mc - ep)
                uw += s * k * d * (mw - ep)
            if j < x and bal + uc > peak:
                peak = bal + uc
            ew = bal + uw
            if ew <= 0.0:
                wiped = True
                wipe_ix = j
                pnl[i] = -bal
                bal = 0.0
                maxdd = 1.0
                break
            dd = (peak - ew) / peak
            if dd > maxdd:
                maxdd = dd
            if j < x:
                while bi < nb and bnd[bi] == j + 1:
                    eqb[bi] = bal + uc
                    bi += 1
        if wiped:
            break
        pl = 0.0
        for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
            pl += s * k * d * (T_xpx[i] - L_epx[q])
        pnl[i] = pl
        bal += pl
        if bal > peak:
            peak = bal
        while bi < nb and bnd[bi] <= x + 1:
            eqb[bi] = bal
            bi += 1
    while bi < nb:
        eqb[bi] = bal
        bi += 1
    return steps, pnl, bal, maxdd, wiped, wipe_ix, n_done, eqb


@njit(cache=True)
def _target_kernel(t, o, h, l, c, sp, k, dx, w, force, active, thr, cap_lev, start_ix, end_ix, bnd, bal0):
    """
    Holds a target notional (``w`` x equity, rounded to the nearest 0.01 lot) traded at the open of the
    decision's bar: buys at the ask, sells at the bid. Returns the round trips (flat -> position -> flat or a
    reversal) with their P/L, the number of orders, and the account figures.
    """
    K = dx.shape[0]
    nb = bnd.shape[0]
    eqb = np.full(nb, np.nan)
    rt_pnl = np.zeros(K + 2)
    rt_dir = np.zeros(K + 2, np.int64)
    rt_eix = np.zeros(K + 2, np.int64)
    rt_xix = np.zeros(K + 2, np.int64)
    n_rt = 0
    n_tx = 0
    cash = bal0
    q = 0.0
    rt_start = bal0
    rt_open = -1
    peak = bal0
    maxdd = 0.0
    wiped = False
    wipe_ix = -1
    first = True
    last_ec = bal0
    bi = 0
    kk = 0
    while kk < K and dx[kk] < start_ix:
        kk += 1
    for j in range(start_ix, end_ix):
        while bi < nb and bnd[bi] <= j:
            eqb[bi] = last_ec
            bi += 1
        while kk < K and dx[kk] == j:
            if active[kk] or first:
                px = o[j]
                if q > 0:
                    eq = cash + q * k * o[j]
                elif q < 0:
                    eq = cash + q * k * (o[j] + sp[j])
                else:
                    eq = cash
                tgt = 0.0
                if eq > 0 and w[kk] == w[kk]:
                    tgt = math.floor(abs(w[kk]) * eq / (px * k) + 0.5)
                    if cap_lev > 0:
                        lim = math.floor(cap_lev * eq / (px * k) + 1e-9)
                        if tgt > lim:
                            tgt = lim
                    if w[kk] < 0:
                        tgt = -tgt
                diff = tgt - q
                if diff != 0 and (force[kk] or first or abs(diff) > thr * abs(tgt)):
                    if q != 0 and (tgt == 0 or (tgt > 0) != (q > 0)):
                        cp = o[j] if q > 0 else o[j] + sp[j]
                        after = cash + q * k * cp
                        rt_pnl[n_rt] = after - rt_start
                        rt_dir[n_rt] = 1 if q > 0 else -1
                        rt_eix[n_rt] = rt_open
                        rt_xix[n_rt] = j
                        n_rt += 1
                        rt_start = after
                    if (q == 0 and tgt != 0) or (q != 0 and tgt != 0 and (tgt > 0) != (q > 0)):
                        if q == 0:
                            rt_start = cash
                        rt_open = j
                    fill = o[j] + sp[j] if diff > 0 else o[j]
                    cash -= diff * fill * k
                    q = tgt
                    n_tx += 1
                first = False
            kk += 1
        if q > 0:
            ec = cash + q * k * c[j]
            ew = cash + q * k * l[j]
        elif q < 0:
            ec = cash + q * k * (c[j] + sp[j])
            ew = cash + q * k * (h[j] + sp[j])
        else:
            ec = cash
            ew = cash
        if ew <= 0.0:
            wiped = True
            wipe_ix = j
            if q != 0:
                rt_pnl[n_rt] = -rt_start + 0.0
                rt_dir[n_rt] = 1 if q > 0 else -1
                rt_eix[n_rt] = rt_open
                rt_xix[n_rt] = j
                n_rt += 1
            cash = 0.0
            q = 0.0
            maxdd = 1.0
            last_ec = 0.0
            break
        if ec > peak:
            peak = ec
        dd = (peak - ew) / peak
        if dd > maxdd:
            maxdd = dd
        last_ec = ec
        if j == end_ix - 1 and q != 0:
            cp = c[j] if q > 0 else c[j] + sp[j]
            cash = cash + q * k * cp
            rt_pnl[n_rt] = cash - rt_start
            rt_dir[n_rt] = 1 if q > 0 else -1
            rt_eix[n_rt] = rt_open
            rt_xix[n_rt] = j
            n_rt += 1
            q = 0.0
            n_tx += 1
            last_ec = cash
    while bi < nb:
        eqb[bi] = last_ec
        bi += 1
    return rt_pnl[:n_rt], rt_dir[:n_rt], rt_eix[:n_rt], rt_xix[:n_rt], n_tx, last_ec, maxdd, wiped, wipe_ix, eqb


# ───────────────────────────── running a plan ─────────────────────────────

@dataclass(frozen=True)
class Sizing:
    mode: str = "bot"          # "bot": the bot's unit rule; "risk": rf of equity per rk; "expo": exposure x equity
    rf: float = 0.0
    cap_lev: float = 0.0
    brake: bool = False
    label: str = "bot unit rule"


BOT = Sizing()
_MODE = {"bot": 0, "risk": 1, "expo": 2}
_YEARS = np.asarray([store.to_ms(f"{y}-01-01") // 1000 for y in range(2015, 2031)], np.int64)


@dataclass
class Path_:
    dir: np.ndarray
    eix: np.ndarray
    epx: np.ndarray
    xix: np.ndarray
    xpx: np.ndarray
    why: np.ndarray
    risk: np.ndarray
    expo: np.ndarray
    leg0: np.ndarray
    nleg: np.ndarray
    leix: np.ndarray
    lepx: np.ndarray

    def __len__(self) -> int:
        return int(len(self.dir))


def run_path(m: Market, plan: PathPlan, start_ix: int, end_ix: int) -> Path_:
    n = len(m)
    ml = plan.m_l if plan.m_l is not None else np.ones(n, np.bool_)
    ms = plan.m_s if plan.m_s is not None else np.ones(n, np.bool_)
    f = plan.f
    out = _path_kernel(m.t, m.o, m.h, m.l, m.c, m.sp, plan.dx, plan.dt, plan.want, plan.xl, plan.xs,
                       f["sl"], f["slf"], f["slcap"], f["tp"], f["tpr"], f["ber"], f["bstop"], f["sstop"], f["bsl"],
                       f["ssl"], f["trl"], f["trs"], f["pstep"], plan.pmax, f["rk"], f["expo"],
                       plan.alw_l, plan.alw_s, ml, ms, float(plan.live_s), int(start_ix), int(end_ix),
                       float(plan.pause_win_s), float(plan.pause_loss_s))
    return Path_(*out)


@dataclass
class Result:
    trades_pnl: np.ndarray       # per sized trade, USD
    trades_dir: np.ndarray
    trades_eix: np.ndarray
    trades_xix: np.ndarray
    skipped: int                 # trades taken at zero size
    final: float
    max_dd: float                # fraction of the running peak
    wiped: bool
    wipe_t: Optional[int]
    blocks: np.ndarray           # equity at the block boundaries (first = start, last = end)
    orders: int = 0


def account(m: Market, p: Path_, sizing: Sizing, bnd: np.ndarray) -> Result:
    """Sizes the path on a $2,000 account; ``bnd`` are the M1 indices of the quarter-block edges (first = start, last = end)."""
    steps, pnl, bal, dd, wiped, wix, n_done, eqb = _account_kernel(
        m.t, m.o, m.h, m.l, m.c, m.sp, m.k, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why, p.risk, p.expo, p.leg0, p.nleg,
        p.leix, p.lepx, _MODE[sizing.mode], float(sizing.rf), float(sizing.cap_lev), bool(sizing.brake),
        np.asarray(bnd[1:-1], np.int64), _YEARS, ACCOUNT, STEP_UP, float(UNIT_MAX))
    done = np.arange(len(steps)) < n_done
    sel = np.flatnonzero(done & (steps > 0))
    skipped = int((done & (steps == 0)).sum())
    blocks = np.concatenate([[ACCOUNT], eqb, [bal]])
    return Result(pnl[sel], p.dir[sel], p.eix[sel], p.xix[sel], skipped, float(bal), float(dd), bool(wiped),
                  int(m.t[wix]) if wiped else None, blocks, orders=int(len(sel) + p.nleg[sel].sum()))


def run_target(m: Market, plan: TargetPlan, start_ix: int, end_ix: int, bnd: np.ndarray) -> Result:
    rp, rd, re, rx, n_tx, bal, dd, wiped, wix, eqb = _target_kernel(
        m.t, m.o, m.h, m.l, m.c, m.sp, m.k, plan.dx, plan.w, plan.force, plan.active, float(plan.thr),
        float(plan.cap_lev), int(start_ix), int(end_ix), np.asarray(bnd[1:-1], np.int64), ACCOUNT)
    return Result(rp, rd, re, rx, 0, float(bal), float(dd), bool(wiped), int(m.t[wix]) if wiped else None,
                  np.concatenate([[ACCOUNT], eqb, [bal]]), orders=int(n_tx))


def block_bounds(m: Market, start: str, end: str, months: int = 3) -> np.ndarray:
    """M1 indices of quarter-block boundaries from ``start`` (blocks of ``months``; the last one may be shorter)."""
    a, z = pd.Timestamp(start), pd.Timestamp(end)
    edges = [a]
    while edges[-1] + pd.DateOffset(months=months) < z:
        edges.append(edges[-1] + pd.DateOffset(months=months))
    edges.append(z)
    return np.asarray([m.ix(e) for e in edges], np.int64)


def metrics(res: Result, start: str, end: str) -> Dict[str, object]:
    q = (store.to_ms(end) - store.to_ms(start)) / 1000.0 / QUARTER_S
    pnl = res.trades_pnl
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    net = res.final - ACCOUNT
    blocks = np.diff(res.blocks)
    return {
        "quarters": round(q, 3),
        "net": round(net, 2),
        "net_per_q": round(net / q, 2),
        "trades": int(len(pnl)),
        "trades_per_q": round(len(pnl) / q, 2),
        "skipped_trades": int(res.skipped),
        "win_rate": round(len(wins) / len(pnl) * 100.0, 1) if len(pnl) else np.nan,
        "avg_win": round(float(wins.mean()), 2) if len(wins) else np.nan,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else np.nan,
        "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if len(losses) and losses.sum() < 0 else (np.inf if len(wins) else np.nan),
        "max_dd_pct": round(res.max_dd * 100.0, 2),
        "worst_trade": round(float(pnl.min()), 2) if len(pnl) else np.nan,
        "wiped": bool(res.wiped),
        "wiped_at": str(pd.Timestamp(res.wipe_t, unit="s").date()) if res.wiped else "",
        "final_equity": round(res.final, 2),
        "orders": int(res.orders),
        "blocks": " ".join(f"{x:+.0f}" for x in blocks),
        "losing_blocks": int((blocks < 0).sum()),
        "n_blocks": int(len(blocks)),
    }


# ───────────────────────────── the strategies ─────────────────────────────

@dataclass
class Built:
    """What one strategy with one parameter set gives: the bot-sized trade plan, the risk-sized plan its source
    prescribes (or None), and its trend / regime state over time for filtering V3-lite (or None)."""
    plan: PathPlan
    risk: Optional[object] = None
    risk_sizing: Optional[Sizing] = None
    regime: Optional[Tuple[np.ndarray, np.ndarray]] = None
    note: str = ""


def _sign(x: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(x), np.sign(x), 0.0).astype(np.int64)


# 1. time-series momentum ------------------------------------------------------------------

def month_starts(m: Market) -> np.ndarray:
    """00:00 UTC of the first day of every month after the first bar, up to the last bar."""
    a = pd.Timestamp(int(m.t[0]), unit="s").to_period("M").to_timestamp() + pd.DateOffset(months=1)
    z = pd.Timestamp(int(m.t[-1]), unit="s")
    if a > z:
        return np.zeros(0, np.int64)
    return (pd.date_range(a, z, freq="MS").asi8 // 1_000_000_000).astype(np.int64)


def tsmom(m: Market, alt: bool = False) -> Built:
    """Moskowitz-Ooi-Pedersen / Hurst-Ooi-Pedersen: sign of the 1, 3 and 12-month returns, equal weight, held a month."""
    d1 = m.bars("D1")
    C = d1.c
    ks = (30, 91, 365) if m.around_the_clock else (21, 63, 252)
    if alt:
        ks = ks[2:]
    S = np.zeros(len(C))
    for k in ks:
        s = np.zeros(len(C))
        if len(C) > k:
            s[k:] = np.sign(C[k:] / C[:-k] - 1.0)
        S += s                                   # a horizon longer than the history counts as 0
    S /= len(ks)
    r = pd.Series(returns(C))
    mu = r.ewm(com=60, adjust=True, ignore_na=True).mean()
    var = ((r - mu) ** 2).ewm(com=60, adjust=True, ignore_na=True).mean()
    n_ret = r.notna().cumsum().to_numpy()
    sigma = np.sqrt(m.year_days * var.to_numpy())
    sigma_prev = np.concatenate([[np.nan], sigma[:-1]])          # day t is sized with sigma of t-1
    ok = np.concatenate([[False], n_ret[:-1] >= 60])
    M = month_starts(m)
    b = np.searchsorted(d1.tc, M, side="right") - 1
    good = b >= 0
    M, b = M[good], b[good]
    state = _sign(S[b])
    w = np.where(ok[b] & (sigma_prev[b] > 0), np.clip(S[b] * 0.40 / sigma_prev[b], -2.0, 2.0), 0.0)
    w = np.nan_to_num(w)
    st_at = lambda T: value_at(M, state, T, 0)
    dt = np.concatenate([d1.tc, M])
    s_now = st_at(dt)
    plan = make_plan(m, dt, want=s_now, xl=s_now != 1, xs=s_now != -1)
    # risk-sized: rebalanced at the month starts; the daily rows only open the position of an account that starts
    # between two month starts (with the weight of the last month start)
    order = np.argsort(dt, kind="stable")
    rdt = dt[order]
    rw = value_at(M, w, rdt, 0.0).astype(np.float64)
    ractive = np.concatenate([np.zeros(len(d1.tc), np.bool_), np.ones(len(M), np.bool_)])[order]
    rdx = np.searchsorted(m.t, rdt, side="left")
    keep = rdx < len(m)
    risk = TargetPlan(dt=rdt[keep], dx=rdx[keep], w=rw[keep], force=np.ones(int(keep.sum()), np.bool_),
                      active=ractive[keep], thr=0.0, cap_lev=2.0)
    return Built(plan, risk, Sizing("target", label="40% vol target per instrument, 2x cap, monthly"), (M, state))


# 2. Turtle -----------------------------------------------------------------------------------

def turtle_n(tr: np.ndarray, n: int = 20) -> np.ndarray:
    """N = (19 x N_prev + TR) / 20, seeded with the simple mean of the first 20 true ranges."""
    return wilder(tr, n)


@njit(cache=True)
def _turtle_s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, tick):
    """
    The System 1 filter, decided at each day's close for the next day: True = trade the 20-day breakout,
    False = only the 55-day failsafe. A hypothetical one-unit System 1 (2N stop, 10-day exit, no adds) is run on
    the daily bars; a breakout is skipped when the last hypothetical breakout trade made money. The outcome of a
    trade is known from the close of the day it ended.
    """
    nb = O.shape[0]
    use20 = np.zeros(nb, np.bool_)
    hyp = 0
    entry = 0.0
    stop = 0.0
    last_win = False
    for b in range(nb):
        if b >= 1:
            if hyp == 0 and hi20[b - 1] == hi20[b - 1] and N[b - 1] == N[b - 1]:
                up_l = hi20[b - 1] + tick
                dn_l = lo20[b - 1] - tick
                up = H[b] >= up_l
                dn = L[b] <= dn_l
                if up and dn:
                    if up_l - O[b] <= O[b] - dn_l:
                        dn = False
                    else:
                        up = False
                if up:
                    hyp = 1
                    entry = max(up_l, O[b])
                    stop = entry - 2.0 * N[b - 1]
                    if L[b] <= stop:
                        hyp = 0
                        last_win = False
                elif dn:
                    hyp = -1
                    entry = min(dn_l, O[b])
                    stop = entry + 2.0 * N[b - 1]
                    if H[b] >= stop:
                        hyp = 0
                        last_win = False
            elif hyp == 1:
                ex = stop
                if lo10[b - 1] == lo10[b - 1] and lo10[b - 1] > ex:
                    ex = lo10[b - 1]
                if O[b] <= ex:
                    last_win = O[b] > entry
                    hyp = 0
                elif L[b] <= ex:
                    last_win = ex > entry
                    hyp = 0
            elif hyp == -1:
                ex = stop
                if hi10[b - 1] == hi10[b - 1] and hi10[b - 1] < ex:
                    ex = hi10[b - 1]
                if O[b] >= ex:
                    last_win = O[b] < entry
                    hyp = 0
                elif H[b] >= ex:
                    last_win = ex < entry
                    hyp = 0
        use20[b] = hyp == 0 and not last_win
    return use20


def turtle(m: Market, system: int = 1) -> Built:
    """The Original Turtle Trading Rules: Donchian breakouts on daily bars, 2N stop, pyramid every N/2 up to 4 units."""
    d1 = m.bars("D1")
    O, H, L, C = d1.o, d1.h, d1.l, d1.c
    N = turtle_n(true_range(H, L, C), 20)
    hi20, lo20 = roll_max(H, 20), roll_min(L, 20)
    hi55, lo55 = roll_max(H, 55), roll_min(L, 55)
    hi10, lo10 = roll_max(H, 10), roll_min(L, 10)
    if system == 1:
        use20 = _turtle_s1_use20(O, H, L, N, hi20, lo20, lo10, hi10, m.tick)
        hi_e, lo_e = np.where(use20, hi20, hi55), np.where(use20, lo20, lo55)
        trl, trs = lo10, hi10
    else:
        hi_e, lo_e = hi55, lo55
        trl, trs = lo20, hi20
    ok = np.isfinite(N) & np.isfinite(hi_e) & np.isfinite(lo_e)
    plan = make_plan(m, d1.tc, bstop=np.where(ok, hi_e + m.tick, NAN), sstop=np.where(ok, lo_e - m.tick, NAN),
                     sl=np.where(ok, 2.0 * N, NAN), pstep=np.where(ok, 0.5 * N, NAN), pmax=4, rk=N, trl=trl, trs=trs,
                     orders=True)
    return Built(plan, plan, Sizing("risk", rf=0.01, brake=True, label="1% of equity per N, 20% cut per 10% drawdown"))


# 3. Donchian ensemble ----------------------------------------------------------------------------

LOOKBACKS = (5, 10, 20, 30, 60, 90, 150, 250, 360)


@njit(cache=True)
def _donchian_model(C, up, dn, mid, long_short):
    nb = C.shape[0]
    pos = np.zeros(nb, np.int64)
    p = 0
    ts = 0.0
    for b in range(nb):
        if p == 1:
            if C[b] <= ts:
                p = 0
            elif mid[b] > ts:
                ts = mid[b]
        elif p == -1:
            if C[b] >= ts:
                p = 0
            elif mid[b] < ts:
                ts = mid[b]
        if p == 0 and up[b] == up[b]:
            if C[b] >= up[b]:
                p = 1
                ts = mid[b]
            elif long_short and C[b] <= dn[b]:
                p = -1
                ts = mid[b]
        pos[b] = p
    return pos


def donchian_ensemble(m: Market, long_short: bool = False) -> Built:
    """Zarattini, Pagani & Barbon (2025): nine Donchian close-breakout models with a ratcheting midline stop, vol-targeted."""
    d1 = m.bars("D1")
    C = d1.c
    pos = np.zeros((len(LOOKBACKS), len(C)), np.int64)
    for i, n in enumerate(LOOKBACKS):
        up, dn = roll_max(C, n), roll_min(C, n)
        pos[i] = _donchian_model(C, up, dn, (up + dn) / 2.0, long_short)
    r = returns(C)
    sigma = pd.Series(r).rolling(90, min_periods=90).std().to_numpy() * math.sqrt(m.year_days)
    wn = np.where(sigma > 0, np.minimum(0.25 / sigma, 2.0), 0.0)
    wn = np.nan_to_num(wn)
    w = (wn[None, :] * pos).mean(axis=0)
    changed = np.ones(len(C), np.bool_)
    changed[1:] = (pos[:, 1:] != pos[:, :-1]).any(axis=0)
    net = pos.sum(axis=0)
    state = np.where(net >= 5, 1, np.where(net <= -5, -1, 0))        # the nine-model average rounds to a whole unit
    plan = make_plan(m, d1.tc, want=state, xl=state != 1, xs=state != -1)
    risk = TargetPlan(dt=d1.tc, dx=d1.ex, w=w, force=changed, active=np.ones(len(C), np.bool_), thr=0.20, cap_lev=2.0)
    keep = d1.ex < len(m)
    risk = TargetPlan(dt=d1.tc[keep], dx=d1.ex[keep], w=w[keep], force=changed[keep], active=risk.active[keep],
                      thr=0.20, cap_lev=2.0)
    regime = np.where(net > 0, 1, np.where(net < 0, -1, 0)) if long_short else np.where(net > 0, 1, 0)
    return Built(plan, risk, Sizing("target", label="25% vol target, 2x cap, 20% rebalance threshold"), (d1.tc, regime))


# 4. moving-average rules ------------------------------------------------------------------------

def sma_cross(m: Market, fast: int, slow: int, tf: str = "M5") -> Built:
    """Urquhart et al.: always in the market, long while SMA(fast) > SMA(slow) of M5 closes, reversed on the cross."""
    b = m.bars(tf)
    state = _sign(sma(b.c, fast) - sma(b.c, slow))
    plan = make_plan(m, b.tc, want=state, xl=state == -1, xs=state == 1)
    return Built(plan, regime=(b.tc, state))


def price_over_sma(m: Market, n: int = 50, tf: str = "D1") -> Built:
    """Long while the daily close is above its 50-day SMA, flat otherwise (long / cash)."""
    b = m.bars(tf)
    s = sma(b.c, n)
    state = np.where(np.isfinite(s) & (b.c > s), 1, 0)
    plan = make_plan(m, b.tc, want=state, xl=state != 1)
    return Built(plan, regime=(b.tc, state))


# 5. Supertrend ------------------------------------------------------------------------------------

@njit(cache=True)
def _supertrend(H, L, C, atr, mult):
    """KivancOzbilgic's Pine Supertrend: +1 / -1 per bar (0 until the ATR exists)."""
    nb = C.shape[0]
    tr = np.zeros(nb, np.int64)
    up_prev = np.nan
    dn_prev = np.nan
    trend = 1
    started = False
    for b in range(nb):
        if atr[b] != atr[b]:
            continue
        src = (H[b] + L[b]) / 2.0
        up = src - mult * atr[b]
        dn = src + mult * atr[b]
        if started:
            up1 = up_prev
            dn1 = dn_prev
            if C[b - 1] > up1:
                up = max(up, up1)
            if C[b - 1] < dn1:
                dn = min(dn, dn1)
            if trend == -1 and C[b] > dn1:
                trend = 1
            elif trend == 1 and C[b] < up1:
                trend = -1
        started = True
        up_prev = up
        dn_prev = dn
        tr[b] = trend
    return tr


def supertrend(m: Market, long_only: bool = False, tf: str = "H4", period: int = 10, mult: float = 3.0) -> Built:
    b = m.bars(tf)
    trend = _supertrend(b.h, b.l, b.c, wilder_atr(b.h, b.l, b.c, period), mult)
    if long_only:
        state = np.where(trend == 1, 1, 0)
        plan = make_plan(m, b.tc, want=state, xl=trend == -1)
    else:
        state = trend
        plan = make_plan(m, b.tc, want=trend, xl=trend == -1, xs=trend == 1)
    return Built(plan, regime=(b.tc, state))


# 6. session breakouts ---------------------------------------------------------------------------------

def london_breakout(m: Market, clock: str = "server") -> Built:
    """
    Asian range / London breakout (MQL5 blog 777540): range 03:00-08:00 server time, range 0.30-1.60% of price,
    OCO stop orders beyond it, stop at the other side capped at 0.6%, target 2.5R, break-even at 1.5R, flat 21:00.
    ``clock`` "server": the usual New-York-close server clock (New York + 7 h); "utc": the same hours on Exness's UTC clock.
    """
    loc = (m.local(NY) + 7 * 3600) if clock == "server" else m.t
    day = loc // DAY
    minute = (loc % DAY) // 60
    dow = (day + 3) % 7
    in_rng = (minute >= 180) & (minute < 480) & (dow <= 4)
    idx = np.flatnonzero(in_rng)
    dts, b_, s_, bl_, sl_ = [], [], [], [], []
    xdt = []
    if len(idx):
        g = day[idx]
        first = np.flatnonzero(np.diff(g, prepend=g[0] - 1) != 0)
        H = np.maximum.reduceat(m.h[idx], first)
        L = np.minimum.reduceat(m.l[idx], first)
        cnt = np.diff(np.append(first, len(idx)))
        last = idx[np.append(first[1:] - 1, len(idx) - 1)]
        spr = np.add.reduceat(m.sp[idx], first) / cnt
        D = g[first]
        px = m.c[last]
        rng = H - L
        ok = (cnt >= 60) & (rng >= 0.003 * px) & (rng <= 0.016 * px)
        buf = np.maximum(2.0 * spr, 0.05 * rng)
        start = D * DAY + 8 * 3600
        stop_t = D * DAY + 21 * 3600
        if clock == "server":
            start, stop_t = utc_of_local(start - 7 * 3600, NY), utc_of_local(stop_t - 7 * 3600, NY)
        good = (start > 0) & (stop_t > 0)
        dts = start[good]
        b_ = np.where(ok, H + buf, NAN)[good]
        s_ = np.where(ok, L - buf, NAN)[good]
        bl_ = np.where(ok, L, NAN)[good]
        sl_ = np.where(ok, H, NAN)[good]
        xdt = stop_t[good]
    plan = merge_plans(m, [dict(dt=dts, bstop=b_, sstop=s_, bsl=bl_, ssl=sl_, slcap=0.006, tpr=2.5, ber=1.5),
                           dict(dt=xdt, xl=True, xs=True)], orders=True)
    return Built(plan, plan, Sizing("risk", rf=0.01, label="1% of equity at risk"))


def daily_vol_breakout(m: Market) -> Built:
    """Unger-style BTC breakout: buy stop at the previous daily close + ATR(2) of daily bars, stop 8%, out at the day's end."""
    d1 = m.bars("D1")
    tr = true_range(d1.h, d1.l, d1.c)
    atr2 = pd.Series(tr).rolling(2, min_periods=2).mean().to_numpy()
    plan = make_plan(m, d1.tc, xl=True, bstop=np.where(np.isfinite(atr2), d1.c + atr2, NAN), slf=0.08, orders=True)
    return Built(plan)


# 7. intraday sessions: noise area and last-half-hour momentum ------------------------------------------------

@dataclass
class Sessions:
    start: np.ndarray        # UTC
    end: np.ndarray
    checks: np.ndarray       # (n_sessions, n_checks) UTC decision times, -1 = none


def sessions(m: Market, kind: str) -> Sessions:
    """
    'comex': 08:20-13:30 New York on weekdays, checks at :00 and :30; 'broker': 18:00 New York (the evening
    before) to 16:30, checks at :00 and :30; 'utc': every UTC day 00:00-24:00, checks at :00 and :30.
    """
    if kind == "utc":
        days = np.unique(m.t // DAY)
        start = days * DAY
        end = start + DAY
        offs = np.arange(1, 48) * 1800
        checks = start[:, None] + offs[None, :]
        return Sessions(start, end, checks)
    loc = m.local(NY)
    ldays = np.arange(int(loc[0] // DAY), int(loc[-1] // DAY) + 2)    # + the session that opens on the last evening
    ldays = ldays[(ldays + 3) % 7 <= 4]
    if kind == "comex":
        a, z = 8 * 3600 + 20 * 60, 13 * 3600 + 30 * 60
    elif kind == "broker":
        a, z = -6 * 3600, 16 * 3600 + 30 * 60
    else:
        raise ValueError(kind)
    first_check = (a // 1800 + 1) * 1800
    offs = np.arange(first_check, z, 1800)
    start = utc_of_local(ldays * DAY + a, NY)
    end = utc_of_local(ldays * DAY + z, NY)
    checks = utc_of_local((ldays[:, None] * DAY + offs[None, :]).ravel(), NY).reshape(len(ldays), len(offs))
    good = (start > 0) & (end > 0)
    return Sessions(start[good], end[good], checks[good])


def mean_of_last_valid(x: np.ndarray, n: int, how: str = "mean") -> np.ndarray:
    """
    Per column, the mean (or standard deviation) of the last ``n`` values that exist BEFORE each row (rows where a
    value is missing - a holiday, a gap in the quotes - are skipped, not counted as a break).
    """
    x = np.asarray(x, np.float64)
    one = x.ndim == 1
    x2 = x[:, None] if one else x
    out = np.full(x2.shape, np.nan)
    for j in range(x2.shape[1]):
        s = pd.Series(x2[:, j])
        v = s.dropna()
        r = v.rolling(n, min_periods=n)
        incl = (r.mean() if how == "mean" else r.std()).reindex(s.index)
        out[:, j] = incl.ffill().shift(1).to_numpy()
    return out[:, 0] if one else out


def price_before(m: Market, T: np.ndarray, not_before: np.ndarray) -> np.ndarray:
    """Close of the last M1 bar that ended by T and opened at or after ``not_before`` (NaN when there is none)."""
    j = np.searchsorted(m.t, np.asarray(T, np.int64) - 60, side="right") - 1
    ok = (j >= 0) & (np.asarray(T) > 0)
    jj = np.maximum(j, 0)
    ok &= m.t[jj] >= not_before
    return np.where(ok, m.c[jj], np.nan), np.where(ok, jj, -1)


def noise_area(m: Market, kind: Optional[str] = None) -> Built:
    """
    Zarattini, Aziz & Barbon (2024) 'Beat the Market': at :00 / :30 go long above the upper bound of the 14-day
    noise area, short below the lower bound; trail with the bound or the session VWAP; flat at the session end.
    """
    kind = kind or ("utc" if m.around_the_clock else "comex")
    ss = sessions(m, kind)
    nS, nC = ss.checks.shape
    j0 = np.searchsorted(m.t, ss.start, side="left")
    has = (j0 < len(m)) & (m.t[np.minimum(j0, len(m) - 1)] < ss.end)
    op = np.where(has, m.o[np.minimum(j0, len(m) - 1)], np.nan)
    cl, _ = price_before(m, ss.end, ss.start)
    P, jP = price_before(m, ss.checks.ravel(), np.repeat(ss.start, nC))
    P = P.reshape(nS, nC)
    jP = jP.reshape(nS, nC)
    move = np.abs(P / op[:, None] - 1.0)
    sig = mean_of_last_valid(move, 14)                         # the previous 14 sessions with a price at that time
    prev_cl = pd.Series(cl).ffill().shift(1).to_numpy()        # the previous session's close
    ub = np.maximum(op, prev_cl)[:, None] * (1.0 + sig)
    lb = np.minimum(op, prev_cl)[:, None] * (1.0 - sig)
    typ = (m.h + m.l + m.c) / 3.0
    cpv = np.concatenate([[0.0], np.cumsum(typ * m.n)])
    cv = np.concatenate([[0.0], np.cumsum(m.n)])
    jj = np.maximum(jP, 0)
    base = np.repeat(j0, nC).reshape(nS, nC)
    vol = cv[jj + 1] - cv[base]
    vwap = np.where((jP >= 0) & (vol > 0), (cpv[jj + 1] - cpv[base]) / np.where(vol > 0, vol, 1.0), np.nan)
    good = np.isfinite(P) & np.isfinite(ub) & np.isfinite(lb) & np.isfinite(vwap) & (ss.checks > 0)
    want = np.where(good & (P > ub), 1, np.where(good & (P < lb), -1, 0))
    xl = good & (P < np.maximum(ub, vwap))
    xs = good & (P > np.minimum(lb, vwap))
    sret = np.full(len(cl), np.nan)                            # close-to-close returns between sessions with a close
    ok_cl = np.flatnonzero(np.isfinite(cl))
    sret[ok_cl[1:]] = cl[ok_cl[1:]] / cl[ok_cl[:-1]] - 1.0
    sd14 = mean_of_last_valid(sret, 14, how="std")              # the 14 daily returns before the day
    expo = np.where(sd14 > 0, np.minimum(4.0, 0.02 / sd14), NAN)
    dt = ss.checks.ravel()
    sel = dt > 0
    plan = merge_plans(m, [dict(dt=dt[sel], want=want.ravel()[sel], xl=xl.ravel()[sel], xs=xs.ravel()[sel],
                                expo=np.repeat(expo, nC)[sel]),
                           dict(dt=ss.end, xl=True, xs=True)], live_s=LIVE_S)
    return Built(plan, plan, Sizing("expo", cap_lev=4.0, label="2% daily vol target, 4x cap"))


def last_half_hour(m: Market, alt: bool = False) -> Built:
    """
    Intraday momentum (Gao et al. 2018; Baltussen et al. 2021): trade the last half hour of the session in the
    direction of the return since the previous session's close. Gold: COMEX hours, signal at 13:00 New York
    (alt: the first half hour, to 08:50), hold 13:00-13:30. BTC proxy: the US cash session, signal at 15:30
    (alt: at 10:00), hold 15:30-16:00 New York.
    """
    loc = m.local(NY)
    ldays = np.unique(loc // DAY)
    ldays = ldays[(ldays + 3) % 7 <= 4]
    hm = lambda hh, mm: hh * 3600 + mm * 60
    if m.around_the_clock:
        close_t, sig_t, ent_t, ext_t = hm(16, 0), (hm(10, 0) if alt else hm(15, 30)), hm(15, 30), hm(16, 0)
    else:
        close_t, sig_t, ent_t, ext_t = hm(13, 30), (hm(8, 50) if alt else hm(13, 0)), hm(13, 0), hm(13, 30)
    T_close = utc_of_local(ldays * DAY + close_t, NY)
    T_sig = utc_of_local(ldays * DAY + sig_t, NY)
    T_ent = utc_of_local(ldays * DAY + ent_t, NY)
    T_ext = utc_of_local(ldays * DAY + ext_t, NY)
    fresh = 15 * 60                                            # a price is taken only from the last quarter hour
    c_day, _ = price_before(m, T_close, T_close - fresh)
    p_sig, _ = price_before(m, T_sig, T_sig - fresh)
    prev = pd.Series(c_day).ffill().shift(1).to_numpy()          # the previous trading day's close
    r = p_sig / prev - 1.0
    want = np.where(np.isfinite(r) & (T_ent > 0), np.sign(r), 0).astype(np.int64)
    ok = T_ent > 0
    plan = merge_plans(m, [dict(dt=T_ent[ok], want=want[ok]), dict(dt=T_ext[T_ext > 0], xl=True, xs=True)], live_s=LIVE_S)
    return Built(plan)


# 8. Connors RSI(2) ------------------------------------------------------------------------------------------------

def connors_rsi2(m: Market, lo: float = 5.0, hi: float = 95.0) -> Built:
    d1 = m.bars("D1")
    C = d1.c
    rsi2 = wilder_rsi(C, 2)
    s200, s5 = sma(C, 200), sma(C, 5)
    ok = np.isfinite(rsi2) & np.isfinite(s200) & np.isfinite(s5)
    want = np.where(ok & (C > s200) & (rsi2 < lo), 1, np.where(ok & (C < s200) & (rsi2 > hi), -1, 0))
    xl = ok & ((C > s5) | (C < s200))
    xs = ok & ((C < s5) | (C > s200))
    plan = make_plan(m, d1.tc, want=want, xl=xl, xs=xs)
    regime = np.where(np.isfinite(s200), np.sign(C - s200), 0).astype(np.int64)
    return Built(plan, regime=(d1.tc, regime))


# 9. Bitcoin MAX / MIN and the 22:00 UTC hour -------------------------------------------------------------------------

def max_min(m: Market, n: int = 10) -> Built:
    """Padysak & Vojtko (2022): long for the next day when the close is the 10-day highest or lowest close."""
    d1 = m.bars("D1")
    mx, mn = roll_max(d1.c, n), roll_min(d1.c, n)
    state = np.where(np.isfinite(mx) & ((d1.c >= mx) | (d1.c <= mn)), 1, 0)
    return Built(make_plan(m, d1.tc, want=state, xl=state != 1))


def seasonality_22utc(m: Market) -> Built:
    """Padysak & Vojtko (2022): buy at 22:00 UTC, sell at 00:00 UTC, every day."""
    days = np.unique(m.t // DAY)
    plan = merge_plans(m, [dict(dt=days * DAY + 22 * 3600, want=1), dict(dt=days * DAY + DAY, xl=True)], live_s=LIVE_S)
    return Built(plan)


# 10. V3-lite at bar level --------------------------------------------------------------------------------------------

def trading_window(symbol: str) -> Tuple[bool, int, int]:
    """The bot's trading window for the symbol (on, start, end in minutes since Monday 00:00 UTC), as the engine reads it:
    gold Monday 01:00 - Friday 22:00, BTC Monday 00:00 - Sunday 23:59."""
    from ..config import BacktestConfig
    cfg = BacktestConfig.live(symbol, repo_root=REPO_ROOT)
    return bool(cfg.window_enabled), int(cfg.window_start_min), int(cfg.window_end_min)


def in_trading_window(symbol: str, T: np.ndarray) -> np.ndarray:
    on, a, z = trading_window(symbol)
    T = np.asarray(T, np.int64)
    if not on or a == z:
        return np.ones(len(T), np.bool_)
    mow = ((T // DAY + 3) % 7) * 1440 + (T % DAY) // 60
    return (mow >= a) & (mow < z) if a < z else (mow >= a) | (mow < z)


def v3lite(m: Market, sig: BotSignals) -> PathPlan:
    """
    The bot's V3-lite on closed M15 bars: H1 votes say BUY (SELL), both M15 votes agree, the H1 trend agrees, inside
    the bot's trading window (gold Monday 01:00 - Friday 22:00 UTC, BTC all week); stop = target = 8 H1 volatility
    units from the fill; 12 h pause after a loss, 5 min after a win; a quote within three minutes of the decision.
    """
    T = sig.m15_tc
    i = np.searchsorted(sig.h1_tc, T, side="right") - 1
    ii = np.maximum(i, 0)
    has = i >= 0
    h1_open = np.where(has, sig.h1_open[ii], 0)
    trend = np.where(has, sig.h1_trend[ii], 0)
    vol = np.where(has, sig.h1_vol[ii], 0.0)
    in_win = in_trading_window(m.symbol, T)
    a = sig.m15_agree.astype(np.int64)
    d = np.where((a != 0) & (h1_open == a) & (trend == a) & in_win & (vol > 0), a, 0)
    return make_plan(m, T, want=d, sl=np.where(vol > 0, 8.0 * vol, NAN), tp=np.where(vol > 0, 8.0 * vol, NAN),
                     live_s=LIVE_S, pause_win_s=300.0, pause_loss_s=43200.0)


# ───────────────────────────── the registry ─────────────────────────────

@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    family: str
    timeframe: str
    params: Dict[str, Tuple[str, Callable[[Market], Built]]]        # label -> (description, builder) for gold
    params_btc: Optional[Dict[str, Tuple[str, Callable[[Market], Built]]]] = None
    in_scope: Tuple[str, ...] = SYMBOLS

    def for_symbol(self, symbol: str) -> Dict[str, Tuple[str, Callable[[Market], Built]]]:
        return self.params_btc if (self.params_btc is not None and symbol.startswith("BTC")) else self.params


STRATEGIES: List[Strategy] = [
    Strategy("tsmom", "Time-series momentum (Moskowitz-Ooi-Pedersen; Hurst-Ooi-Pedersen)", "momentum", "D1",
             {"default": ("1/3/12-month signs, equal weight, monthly", lambda m: tsmom(m)),
              "alt": ("12-month sign only (MOP-12)", lambda m: tsmom(m, alt=True))}),
    Strategy("turtle", "Turtle Donchian breakout (Original Turtle Rules)", "breakout", "D1",
             {"default": ("System 1: 20-day entry with the skip-after-winner filter and 55-day failsafe, 10-day exit",
                          lambda m: turtle(m, 1)),
              "alt": ("System 2: 55-day entry, 20-day exit", lambda m: turtle(m, 2))}),
    Strategy("donchian", "Donchian ensemble, vol-targeted (Zarattini-Pagani-Barbon 2025)", "trend following", "D1",
             {"default": ("9 lookbacks 5-360 days, long only", lambda m: donchian_ensemble(m)),
              "alt": ("the same, long and short (appendix variant)", lambda m: donchian_ensemble(m, long_short=True))}),
    Strategy("ma", "Long-horizon moving-average rule (Urquhart et al.; 50-day SMA on BTC)", "trend following", "M5 / D1",
             {"default": ("gold M5 SMA 41 / 356, always in", lambda m: sma_cross(m, 41, 356)),
              "alt": ("gold M5 SMA 34 / 339", lambda m: sma_cross(m, 34, 339))},
             {"default": ("BTC D1 close above SMA 50, long / cash", lambda m: price_over_sma(m, 50)),
              "alt": ("the gold rule on BTC: M5 SMA 41 / 356", lambda m: sma_cross(m, 41, 356))}),
    Strategy("supertrend", "Supertrend (ATR 10 x 3) stop and reverse", "trend following", "H4",
             {"default": ("H4, always in", lambda m: supertrend(m)),
              "alt": ("H4, long only", lambda m: supertrend(m, long_only=True))}),
    Strategy("london", "Asian-range / London breakout (gold); daily volatility breakout (BTC)", "breakout", "M1 orders",
             {"default": ("range 03-08 server (New York + 7 h), flat 21:00 server", lambda m: london_breakout(m, "server")),
              "alt": ("the same hours read on Exness's UTC clock", lambda m: london_breakout(m, "utc"))},
             {"default": ("buy stop at the previous close + ATR(2), stop 8%, out at the day's end",
                          lambda m: daily_vol_breakout(m))}),
    Strategy("noise", "Noise-area intraday momentum with VWAP trail (Zarattini-Aziz-Barbon 2024)", "intraday momentum", "M1, every 30 min",
             {"default": ("COMEX session 08:20-13:30 New York", lambda m: noise_area(m, "comex")),
              "alt": ("broker day 18:00-16:30 New York", lambda m: noise_area(m, "broker"))},
             {"default": ("UTC day 00:00-24:00", lambda m: noise_area(m, "utc"))}),
    Strategy("lasthalf", "Last half-hour intraday momentum (Gao et al.; Baltussen et al.)", "momentum", "M1, timed",
             {"default": ("signal = return to 13:00, hold 13:00-13:30 New York", lambda m: last_half_hour(m)),
              "alt": ("signal = return to 08:50 (first half hour)", lambda m: last_half_hour(m, alt=True))},
             {"default": ("US session proxy: return to 15:30, hold 15:30-16:00 New York", lambda m: last_half_hour(m)),
              "alt": ("return to 10:00 (first half hour)", lambda m: last_half_hour(m, alt=True))}),
    Strategy("rsi2", "Connors RSI(2) pullback with the 200-day trend", "mean reversion", "D1",
             {"default": ("RSI(2) 5 / 95, exit at SMA 5", lambda m: connors_rsi2(m)),
              "alt": ("RSI(2) 10 / 90", lambda m: connors_rsi2(m, 10.0, 90.0))}),
    Strategy("maxmin", "Bitcoin 10-day MAX / MIN composite (Padysak-Vojtko 2022)", "other", "D1",
             {"default": ("long the next day after a 10-day highest or lowest close", lambda m: max_min(m)),
              "alt": ("22:00-00:00 UTC hold, every day (same paper)", lambda m: seasonality_22utc(m))},
             in_scope=("BTCUSDm",)),
]
STRATEGY_BY_KEY = {s.key: s for s in STRATEGIES}

VARIANTS = ("standalone", "risk-sized", "+ bot votes", "+ H1 trend", "V3-lite + regime")


# ───────────────────────────── the study ─────────────────────────────

def _period_ix(m: Market, period: str) -> Tuple[int, int, str, str]:
    a, z = PERIODS[period]
    return m.ix(a), m.ix(z), a, z


def _run(m: Market, plan, sizing: Sizing, a_ix: int, z_ix: int, bnd: np.ndarray) -> Result:
    if isinstance(plan, TargetPlan):
        return run_target(m, plan, a_ix, z_ix, bnd)
    return account(m, run_path(m, plan, a_ix, z_ix), sizing, bnd)


def fresh_quarters(m: Market, plan, sizing: Sizing, period: str) -> Dict[str, object]:
    """The plan on a fresh $2,000 account in every quarter block of the tick engine's tables (the bot's own format)."""
    edges = ENGINE_BLOCKS[period]
    nets, dds, wiped = [], [], False
    for a, z in zip(edges[:-1], edges[1:]):
        a_ix, z_ix = m.ix(a), m.ix(z)
        res = _run(m, plan, sizing, a_ix, z_ix, np.asarray([a_ix, z_ix], np.int64))
        nets.append(res.final - ACCOUNT)
        dds.append(res.max_dd)
        wiped |= res.wiped
    nets = np.asarray(nets)
    return {"fresh_avg_q": round(float(nets.mean()), 2), "fresh_lost": int((nets < 0).sum()), "fresh_n": int(len(nets)),
            "fresh_worst": round(float(nets.min()), 2), "fresh_dd_worst": round(float(max(dds)) * 100.0, 2),
            "fresh_wiped": bool(wiped), "fresh_blocks": " ".join(f"{x:+.0f}" for x in nets)}


def evaluate(m: Market, sig: BotSignals, log=print) -> Tuple[List[dict], List[dict]]:
    """Every strategy, parameter set and variant on every period: one row each, and the quarter blocks."""
    rows: List[dict] = []
    blocks: List[dict] = []
    v3 = v3lite(m, sig)
    jobs: List[Tuple[str, str, str, str, str, object, Sizing]] = []
    jobs.append(("v3lite", "V3-lite (bar level)", "reference", "H1 votes + M15 agree + H1 trend, 8 / 8 vol units",
                 "standalone", v3, BOT))
    for s in STRATEGIES:
        for label, (desc, build) in s.for_symbol(m.symbol).items():
            t0 = time.time()
            b = build(m)
            jobs.append((s.key, s.name, label, desc, "standalone", b.plan, BOT))
            if b.risk is not None:
                jobs.append((s.key, s.name, label, desc, "risk-sized", b.risk, b.risk_sizing))
            jobs.append((s.key, s.name, label, desc, "+ bot votes", filtered(b.plan, m, sig.votes_at), BOT))
            jobs.append((s.key, s.name, label, desc, "+ H1 trend", filtered(b.plan, m, sig.trend_at), BOT))
            if b.regime is not None:
                rt, rv = b.regime
                jobs.append((s.key, s.name, label, desc, "V3-lite + regime",
                             filtered(v3, m, lambda T, rt=rt, rv=rv: value_at(rt, rv, T, 0)), BOT))
            log(f"  {m.symbol} {s.key} {label}: built in {time.time() - t0:.1f}s")
    for key, name, label, desc, variant, plan, sizing in jobs:
        for per in PERIODS:
            a_ix, z_ix, a, z = _period_ix(m, per)
            bnd = block_bounds(m, a, z)
            res = _run(m, plan, sizing, a_ix, z_ix, bnd)
            mt = metrics(res, a, z)
            mt.update(fresh_quarters(m, plan, sizing, per))
            scope = "yes" if (key == "v3lite" or m.symbol in STRATEGY_BY_KEY[key].in_scope) else "no"
            row = dict(symbol=m.symbol, strategy=key, name=name, params=label, rule=desc, variant=variant,
                       sizing=sizing.label, period=per, start=a, end=z, in_source_scope=scope, **mt)
            rows.append(row)
            for qi, (x0, x1) in enumerate(zip(res.blocks[:-1], res.blocks[1:])):
                blocks.append(dict(symbol=m.symbol, strategy=key, params=label, variant=variant, period=per, block=qi,
                                   start_equity=round(float(x0), 2), end_equity=round(float(x1), 2),
                                   pnl=round(float(x1 - x0), 2)))
    return rows, blocks


V3LITE_SETTINGS = dict(trend_tf="H1", open_weights={"H1": 1}, entry_agree_s=2.0, max_adds=0, force_close_enabled=False,
                       vol_tf="H1", vol_len=24, target_vol=8.0, stop_vol=8.0, target_usd_per_unit=None,
                       stop_loss_usd_per_unit=None, loss_cooldown_s=43200.0)


def engine_v3lite(symbols: Sequence[str], engine_store: Path, out: Path = OUT, cache_dir: Optional[Path] = None,
                  store_dir: Path = store.DEFAULT_STORE_DIR, log=print) -> pd.DataFrame:
    """
    V3-lite three ways on the tick engine's quarter blocks, fresh $2,000 each: the engine as the live bot runs it
    (votes on the still-forming bar, one fixed poll grid), the engine with the votes read on closed bars
    (``slope_on_closed_bars``), and this module's bar-level simulator. ``engine_store`` is a tick store holding only
    the months from EARLIEST on (the engine reads the span of whatever store it is given).
    """
    from ..config import BacktestConfig
    from ..engine import fast
    rows = []
    for sym in symbols:
        m = load_market(sym, store_dir)
        sig = bot_signals(m, cache_dir)
        plan = v3lite(m, sig)
        for per, edges in ENGINE_BLOCKS.items():
            for a, z in zip(edges[:-1], edges[1:]):
                for label, extra in (("engine, votes on the forming bar (live)", {}),
                                     ("engine, votes on closed bars", {"slope_on_closed_bars": True})):
                    cfg = BacktestConfig.live(sym, repo_root=REPO_ROOT, start=a, end=z, **V3LITE_SETTINGS, **extra)
                    res = fast.run(cfg, mode="sec", store_dir=engine_store, light=True)
                    pl = res.baskets["pnl"].to_numpy() if len(res.baskets) else np.zeros(0)
                    rows.append(dict(symbol=sym, period=per, start=a, end=z, run=label,
                                     net=round(float(res.scalars["final_balance"]) - ACCOUNT, 2), trades=int(len(pl)),
                                     win_rate=round(float((pl > 0).mean() * 100.0), 1) if len(pl) else np.nan))
                a_ix, z_ix = m.ix(a), m.ix(z)
                res = account(m, run_path(m, plan, a_ix, z_ix), BOT, np.asarray([a_ix, z_ix], np.int64))
                mt = metrics(res, a, z)
                rows.append(dict(symbol=sym, period=per, start=a, end=z, run="bar level, closed bars (this study)",
                                 net=mt["net"], trades=mt["trades"], win_rate=mt["win_rate"]))
                log(f"  {sym} {a}: " + ", ".join(f"{r['net']:+.0f}" for r in rows[-3:]))
    d = pd.DataFrame(rows)
    Path(out).mkdir(parents=True, exist_ok=True)
    d.to_csv(Path(out) / "external_v3lite_engine.csv", index=False)
    return d


def run(symbols: Sequence[str] = SYMBOLS, out: Path = OUT, cache_dir: Optional[Path] = None,
        store_dir: Path = store.DEFAULT_STORE_DIR, log=print) -> None:
    rows, blocks = [], []
    for sym in symbols:
        t0 = time.time()
        m = load_market(sym, store_dir)
        log(f"{sym}: {len(m):,} M1 bars {pd.Timestamp(int(m.t[0]), unit='s')} .. {pd.Timestamp(int(m.t[-1]), unit='s')}")
        sig = bot_signals(m, cache_dir)
        log(f"{sym}: the bot's votes ready ({time.time() - t0:.0f}s)")
        r, b = evaluate(m, sig, log)
        rows += r
        blocks += b
        log(f"{sym}: {len(r)} rows ({time.time() - t0:.0f}s)")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "external_strategies.csv", index=False)
    pd.DataFrame(blocks).to_csv(out / "external_strategies_blocks.csv", index=False)
    log(f"wrote {out / 'external_strategies.csv'}")


# ───────────────────────────── tables ─────────────────────────────

def _usd(x) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    return f"{'+' if x > 0 else '−' if x < 0 else ''}${abs(x):,.0f}"


def _md(header: List[str], body: List[List[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def summary(d: pd.DataFrame) -> pd.DataFrame:
    """One row per symbol x strategy x params x variant: per-period net per quarter, worst drawdown, trades, wipes."""
    keys = ["symbol", "strategy", "name", "params", "rule", "variant", "sizing", "in_source_scope"]
    out = []
    for k, g in d.groupby(keys, sort=False):
        r = dict(zip(keys, k))
        per = {p: g[g["period"] == p].iloc[0] for p in PERIODS if (g["period"] == p).any()}
        for p, x in per.items():
            r[f"q_{p}"] = x["net_per_q"]
            r[f"dd_{p}"] = x["max_dd_pct"]
            r[f"n_{p}"] = x["trades"]
            r[f"wiped_{p}"] = bool(x["wiped"])
        r["net_total"] = float(sum(x["net"] for x in per.values()))
        r["quarters"] = float(sum(x["quarters"] for x in per.values()))
        r["dd_worst"] = float(max(x["max_dd_pct"] for x in per.values()))
        r["trades_per_q"] = float(sum(x["trades"] for x in per.values())) / r["quarters"]
        r["wiped_any"] = any(bool(x["wiped"]) for x in per.values())
        r["wiped_in"] = ", ".join(p for p, x in per.items() if bool(x["wiped"]))
        r["losing_blocks"] = int(sum(x["losing_blocks"] for x in per.values()))
        r["n_blocks"] = int(sum(x["n_blocks"] for x in per.values()))
        r["skipped"] = int(sum(x["skipped_trades"] for x in per.values()))
        if all("fresh_avg_q" in x for x in per.values()):
            for p, x in per.items():
                r[f"fresh_{p}"] = x["fresh_avg_q"]
            r["fresh_lost"] = int(sum(x["fresh_lost"] for x in per.values()))
            r["fresh_n"] = int(sum(x["fresh_n"] for x in per.values()))
            r["fresh_wiped"] = any(bool(x["fresh_wiped"]) for x in per.values())
            r["fresh_dd_worst"] = float(max(x["fresh_dd_worst"] for x in per.values()))
        out.append(r)
    return pd.DataFrame(out)


def table_symbol(s: pd.DataFrame, symbol: str, which: str = "default") -> str:
    g = s[(s["symbol"] == symbol) & ((s["params"] == which) | (s["strategy"] == "v3lite"))]
    if which != "default":
        g = g[g["strategy"] != "v3lite"]
    header = ["Strategy", "Variant", "2023 / q", "2024-25 / q", "2025-26 / q", "Total, 3 periods", "Max DD", "Trades / q",
              "Losing quarters", "Wiped"]
    body = []
    for _, r in g.iterrows():
        nm = "V3-lite, bar level (reference)" if r["strategy"] == "v3lite" else STRATEGY_BY_KEY[r["strategy"]].name.split(" (")[0]
        if r["in_source_scope"] == "no":
            nm += " (outside its source's scope)"
        var = r["variant"] if r["variant"] != "risk-sized" else f"risk-sized: {r['sizing']}"
        body.append([nm, var, _usd(r["q_2023"]), _usd(r["q_2024-25"]), _usd(r["q_2025-26"]), _usd(r["net_total"]),
                     f"{r['dd_worst']:.0f}%", f"{r['trades_per_q']:.1f}", f"{r['losing_blocks']} of {r['n_blocks']}",
                     r["wiped_in"] or "no"])
    return _md(header, body)


def _fresh(r) -> str:
    if "fresh_2023" not in r or pd.isna(r.get("fresh_n")):
        return "n/a"
    return (" / ".join(_usd(r[f"fresh_{p}"]) for p in PERIODS)
            + f" ({int(r['fresh_lost'])} of {int(r['fresh_n'])} lost, worst DD {r['fresh_dd_worst']:.0f}%)")


def table_top(s: pd.DataFrame, symbol: str, n: int = 5) -> str:
    g = s[(s["symbol"] == symbol) & (s["dd_worst"] < 50.0) & (~s["wiped_any"]) & (s["strategy"] != "v3lite")]
    g = g.sort_values("net_total", ascending=False).head(n)
    header = ["#", "Strategy", "Parameters", "Variant", "Total, 3 periods", "2023 / q", "2024-25 / q", "2025-26 / q",
              "Max DD", "Trades / q", "Losing quarters", "Fresh $2,000 each quarter: 2023 / 2024-25 / 2025-26 per q"]
    body = []
    for i, (_, r) in enumerate(g.iterrows(), 1):
        body.append([str(i), STRATEGY_BY_KEY[r["strategy"]].name.split(" (")[0], r["rule"], r["variant"] if r["variant"] != "risk-sized" else f"risk-sized ({r['sizing']})",
                     _usd(r["net_total"]), _usd(r["q_2023"]), _usd(r["q_2024-25"]), _usd(r["q_2025-26"]),
                     f"{r['dd_worst']:.0f}%", f"{r['trades_per_q']:.1f}", f"{r['losing_blocks']} of {r['n_blocks']}", _fresh(r)])
    return _md(header, body)


def table_v3_check(ed: pd.DataFrame) -> str:
    """V3-lite three ways (tick engine live-style, tick engine with closed-bar votes, bar level), fresh $2,000 per quarter."""
    runs = ["engine, votes on the forming bar (live)", "engine, votes on closed bars", "bar level, closed bars (this study)"]
    header = ["Symbol", "Period", "Tick engine, published (8 timings)", "Tick engine, live votes, 1 timing",
              "Tick engine, closed-bar votes", "Bar level (this study)", "Trades / q (engine closed-bar, bar level)"]
    body = []
    for sym in SYMBOLS:
        for per in PERIODS:
            g = ed[(ed["symbol"] == sym) & (ed["period"] == per)]
            if not len(g):
                continue
            cell = []
            for run in runs:
                x = g[g["run"] == run]
                cell.append(f"{_usd(float(x['net'].mean()))} ({int((x['net'] < 0).sum())} of {len(x)} lost)")
            tq = [g[g["run"] == r]["trades"].mean() for r in runs[1:]]
            body.append([sym, per, _usd(ENGINE_V3LITE[sym][per])] + cell + [f"{tq[0]:.0f}, {tq[1]:.0f}"])
    return _md(header, body)


def render(out: Path = OUT) -> str:
    d = pd.read_csv(Path(out) / "external_strategies.csv")
    s = summary(d)
    parts = []
    for sym in SYMBOLS:
        if not (s["symbol"] == sym).any():
            continue
        parts.append(f"### {sym}: default parameters\n\n" + table_symbol(s, sym, "default"))
        parts.append(f"### {sym}: alternative parameter sets\n\n" + table_symbol(s, sym, "alt"))
    for sym in SYMBOLS:
        if (s["symbol"] == sym).any():
            parts.append(f"### Top 5 on {sym} (max drawdown under 50% in every period, never wiped)\n\n" + table_top(s, sym))
    ep = Path(out) / "external_v3lite_engine.csv"
    if ep.exists():
        parts.append("### V3-lite three ways (fresh $2,000 per quarter, average per quarter)\n\n" + table_v3_check(pd.read_csv(ep)))
    return "\n\n".join(parts)


BEGIN, END_MARK = "<!-- tables:begin -->", "<!-- tables:end -->"


def update_report(path: Path, out: Path = OUT) -> None:
    text = Path(path).read_text(encoding="utf-8")
    a, z = text.index(BEGIN) + len(BEGIN), text.index(END_MARK)
    Path(path).write_text(text[:a] + "\n\n" + render(out) + "\n\n" + text[z:], encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.external", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run every strategy and variant, write the CSV files")
    r.add_argument("--symbols", nargs="+", default=list(SYMBOLS), choices=list(SYMBOLS))
    r.add_argument("--out", type=Path, default=OUT)
    r.add_argument("--cache", type=Path, default=None, help="directory for the bot's votes (computed once per symbol)")
    e = sub.add_parser("engine-check", help="V3-lite on the tick engine (forming / closed-bar votes) against the bar level")
    e.add_argument("--engine-store", type=Path, required=True,
                   help="a tick store holding only the months from 2022-12 on")
    e.add_argument("--symbols", nargs="+", default=list(SYMBOLS), choices=list(SYMBOLS))
    e.add_argument("--out", type=Path, default=OUT)
    e.add_argument("--cache", type=Path, default=None)
    t = sub.add_parser("tables", help="print the markdown tables, or refresh them in a report")
    t.add_argument("--out", type=Path, default=OUT)
    t.add_argument("--update", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.symbols, a.out, a.cache)
    elif a.cmd == "engine-check":
        engine_v3lite(a.symbols, a.engine_store, a.out, a.cache)
    elif a.update:
        update_report(a.update, a.out)
        print(f"updated {a.update}")
    else:
        print(render(a.out))


if __name__ == "__main__":
    main()
