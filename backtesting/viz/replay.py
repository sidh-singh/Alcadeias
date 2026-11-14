"""
Replay logic for the Backtest Studio -- pure numpy / pandas / the engine, no Dash.

The Studio lets the owner *watch* a stretch of a finished backtest as if the bot were
running live. Three things live here:

``replay_window``  picks where a replay run has to start so that it shows exactly the
                   trades of the full-period run;
``run_replay``     ONE kernel run over that window with ``trace=True`` (a row per poll);
``ReplaySession``  everything the screen needs at a playhead time, pre-computed once per
                   window and kept server-side: the account state after every poll,
                   candles that form second by second, trade marks, the event log and
                   the plotly figure of one frame.

Why a replay needs an anchor
----------------------------
A kernel run always starts flat, with no re-entry cooldown pending. Started at an
arbitrary time it would therefore trade differently from the full run (it may enter
where the full run was still waiting out a cooldown, or miss a basket that was already
open). It reproduces the full run only when it starts on a poll at which the full run was
in that same fresh state:

* ``basket_open`` -- the poll on which a basket was opened: the full run was flat and its
  cooldown had expired at that instant (otherwise it could not have opened);
* ``flat``        -- any later poll while it was still flat and the cooldown had run out;
* ``run_start``   -- the first poll of the full run.

``replay_window`` takes the latest such poll at or before the requested time, starts the
run exactly there with the balance the full run had at that moment, and reports the
requested time as ``visible_from_ms``; the polls before it are pre-roll and stay hidden.

Two details matter for exactness (both were measured against full runs on real ticks):

* the run must start ON the anchor poll, not one poll before it -- a fresh run that sees
  the previous poll opens there whenever the full run was only held back by its cooldown;
* the tick the full run saw on the anchor poll can be older than one poll (a quiet
  second), so rows from before the anchor have to be loaded. ``run_replay`` therefore
  either reuses the full run's ``Prepared`` (bit-identical inputs) or prepares the window
  with a few minutes of rows in front of the anchor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import BacktestConfig, TF_SECONDS
from ..data import store
from ..engine import fast
from ..engine import kernels as K
from . import theme as T

CANDLE_TFS: Tuple[str, ...] = ("M1", "M5", "M15")   # candle timeframes the replay chart offers
N_CANDLES = 160                 # candles on screen (the last one is the forming one)
DEFAULT_SPAN_S = 6 * 3600       # visible length of a replay window
BASKET_LEAD_S = 30 * 60         # shown before a basket's entry when a basket is picked
BASKET_TAIL_S = 20 * 60         # ... and after its exit
MAX_SPAN_S = 48 * 3600
MAX_RUN_S = 21 * 86400          # longest kernel run with a trace (pre-roll included); ~12 MB of trace per day

_ALIGN_S = 900                  # per-second rows start on a 15-minute boundary (a bar boundary of every candle TF)
_NEVER = np.iinfo(np.int64).max
_SIGNAL = {0: "", 1: "BUY", 2: "SELL", 3: "CLOSE_BUY", 4: "CLOSE_SELL", 5: "BUY_MORE", 6: "SELL_MORE"}
REASON_SHORT = {"target": "target", "force_close": "force-close", "book": "profit-book",
                "stop_loss": "stop-loss", "stop_out": "stop-out", "end": "end", "": ""}


class ReplayError(ValueError):
    """A replay that cannot be built. The message is written for the screen."""


# ───────────────────────────── small helpers ─────────────────────────────

def _ms(series) -> np.ndarray:
    """
    Datetimes (a column of a Result frame, or any datetime Series / index) -> int64 epoch
    milliseconds. The values are brought to nanoseconds first, so the result does not depend
    on the resolution the column happens to have (pandas 3 no longer defaults to nanoseconds).
    A missing time (NaT) comes out as a large negative number, as it does in pandas itself.
    """
    if len(series) == 0:
        return np.zeros(0, np.int64)
    return np.asarray(pd.DatetimeIndex(series).as_unit("ns").asi8 // 1_000_000, dtype=np.int64)


def iso_ms(ms) -> str:
    """Epoch ms -> 'YYYY-MM-DD HH:MM:SS.mmm' (UTC), the form BacktestConfig.start / .end take."""
    return store.ms_to_dt(int(ms)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _iso(ms, unit: str = "ms") -> List[str]:
    """Vector of epoch ms -> ISO strings for a plotly date axis (UTC wall clock, no offset)."""
    a = np.asarray(ms, dtype=np.int64)
    if a.size == 0:
        return []
    return np.datetime_as_string(a.astype("datetime64[ms]"), unit=unit).tolist()


def _iso1(ms, unit: str = "ms") -> str:
    return str(np.datetime_as_string(np.int64(ms).astype("datetime64[ms]"), unit=unit))


def _round2(x):
    """Cents, half away from zero -- the same arithmetic as ``kernels._round2`` (vectorised)."""
    x = np.asarray(x, dtype=np.float64)
    return np.sign(x) * np.floor(np.abs(x) * 100.0 + 0.5) / 100.0


def fmt_price(x: float, digits: int) -> str:
    return f"{x:,.{digits}f}"


def fmt_money(x: float, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    s = f"${abs(x):,.2f}"
    if signed:
        return ("+" if x > 0 else "-" if x < 0 else "") + s
    return ("-" if x < 0 else "") + s


def fmt_dur(s: float) -> str:
    if s is None or (isinstance(s, float) and not math.isfinite(s)):
        return "-"
    s = float(s)
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.1f}m"
    if s < 172800:
        return f"{s / 3600:.1f}h"
    return f"{s / 86400:.1f}d"


def score_range(weights: Dict[str, Tuple[float, float]]) -> float:
    """Largest magnitude a section score can reach: sum(|w_rsi| + |w_macd|) = 2 * sum(|w|) for plain weights."""
    return float(sum(abs(r) + abs(m) for r, m in (weights or {}).values()))


# ───────────────────────────── the window ─────────────────────────────

@dataclass(frozen=True)
class ReplayWindow:
    """Where a replay run starts and what part of it is shown."""
    cfg: BacktestConfig          # the full run's configuration with start / end / initial_balance replaced
    anchor_ms: int               # first poll of the replay run: a poll of the full run at which it was flat and free
    visible_from_ms: int         # the requested time; polls before it are pre-roll
    end_ms: int                  # exclusive
    kind: str                    # 'basket_open' | 'flat' | 'run_start'
    basket_base: int             # the replay run's basket k is the full run's basket basket_base + k
    balance: float               # the full run's balance at the anchor
    run_start_ms: int            # the full run's first poll
    run_end_ms: int              # where its poll loop stopped (cfg.end, or earlier after a stop-out)
    data_end_ms: int             # where its rows ended (cfg.end)

    @property
    def key(self) -> str:
        return f"{self.cfg.key()}:{self.anchor_ms}:{self.visible_from_ms}:{self.end_ms}"

    @property
    def preroll_s(self) -> float:
        return (self.visible_from_ms - self.anchor_ms) / 1000.0


def run_span(result) -> Tuple[int, int]:
    """[first poll, end) of a finished run in epoch ms. The end is where its poll loop actually stopped."""
    cfg = result.cfg
    a, z = store.to_ms(cfg.start), store.to_ms(cfg.end)
    last = result.scalars.get("last_poll_ms")
    if last is not None and math.isfinite(last):
        z = min(z, int(last))     # a stop-out, or ticks running out, ends the run early
    return a, z


def basket_opens(result) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(open poll ms, basket id, balance at the open) of every basket the run opened -- closed or not."""
    f = result.fills
    o = f[f["action"] == "open"]
    return (_ms(o["time"]), o["basket"].to_numpy(dtype=np.int64) if len(o) else np.zeros(0, np.int64),
            o["balance"].to_numpy(dtype=np.float64) if len(o) else np.zeros(0))


def _anchor(result, when_ms: int, run_a: int) -> Tuple[int, float, int, str]:
    """(anchor poll, balance, first basket id, kind) for a requested time inside the run."""
    cfg = result.cfg
    poll = int(cfg.poll_interval_ms)
    cooldown = int(round(cfg.reentry_cooldown_s * 1000))
    start = (run_a, float(cfg.initial_balance), 0, "run_start")
    if cfg.entry_confirm_s > 0:
        # The entry-confirmation lever keeps "how long has the direction held" across polls;
        # a fresh run has no such history, so only the true start reproduces the full run.
        return start
    ot, oid, obal = basket_opens(result)
    i = int(np.searchsorted(ot, when_ms, side="right")) - 1
    if i < 0:
        # nothing opened yet: every poll so far found the run in its initial state
        g = run_a + ((when_ms - run_a) // poll) * poll
        return (int(g), float(cfg.initial_balance), 0, "flat") if g > run_a else start
    b = result.baskets
    bid_ = int(oid[i])
    row = b[b["basket"] == bid_]
    if len(row):
        close_ms = int(_ms(row["close_time"])[0])
        if close_ms <= when_ms:
            # polls after a close stay on the grid close + k * poll (dead-market skips keep the phase)
            g = close_ms + ((when_ms - close_ms) // poll) * poll
            if g > close_ms and g - close_ms >= cooldown:
                return int(g), float(row["balance"].iloc[0]), bid_ + 1, "flat"
    return int(ot[i]), float(obal[i]), bid_, "basket_open"


def replay_window(result, when, span_s: float = DEFAULT_SPAN_S, max_run_s: float = MAX_RUN_S) -> ReplayWindow:
    """
    The replay run that shows ``[when, when + span_s)`` of a finished run exactly.

    ``result`` is the full-period ``Result`` (its ``cfg`` must be the configuration it was
    run with, over ``cfg.start .. cfg.end``). ``when`` is clamped into the run. The returned
    window's ``cfg`` differs from ``result.cfg`` only in ``start`` (the anchor poll), ``end``
    and ``initial_balance``.
    """
    cfg = result.cfg
    poll = int(cfg.poll_interval_ms)
    run_a, run_z = run_span(result)
    if run_z - run_a < poll:
        raise ReplayError("This run has no polls to replay.")
    when_ms = min(max(store.to_ms(when), run_a), run_z - poll)
    end_ms = min(when_ms + int(round(span_s * 1000)), run_z)
    if end_ms <= when_ms:
        raise ReplayError("Nothing to replay at that time.")
    anchor, balance, base, kind = _anchor(result, when_ms, run_a)
    if end_ms - anchor > max_run_s * 1000:
        raise ReplayError(
            f"Replaying {store.ms_to_dt(when_ms):%Y-%m-%d %H:%M} needs a run from {store.ms_to_dt(anchor):%Y-%m-%d %H:%M} "
            f"({(end_ms - anchor) / 86_400_000:.0f} days) to reproduce the open basket exactly - too long to trace. "
            "Pick a time closer to that basket's entry.")
    cfg_w = cfg.replace(start=iso_ms(anchor), end=iso_ms(end_ms), initial_balance=float(balance))
    return ReplayWindow(cfg=cfg_w, anchor_ms=int(anchor), visible_from_ms=int(when_ms), end_ms=int(end_ms),
                        kind=kind, basket_base=int(base), balance=float(balance),
                        run_start_ms=int(run_a), run_end_ms=int(run_z), data_end_ms=int(store.to_ms(cfg.end)))


def window_for_basket(result, basket_id: int, lead_s: float = BASKET_LEAD_S, tail_s: float = BASKET_TAIL_S,
                      min_span_s: float = DEFAULT_SPAN_S, max_span_s: float = MAX_SPAN_S) -> Tuple[ReplayWindow, int]:
    """A window around one basket of the full run and the playhead that sits on its entry poll."""
    ot, oid, _ = basket_opens(result)
    hit = np.flatnonzero(oid == int(basket_id))
    if len(hit) == 0:
        raise ReplayError(f"Basket #{basket_id} is not in this run.")
    open_ms = int(ot[hit[0]])
    b = result.baskets
    row = b[b["basket"] == int(basket_id)]
    held = float(row["duration_s"].iloc[0]) if len(row) else 0.0
    span = min(max(min_span_s, held + lead_s + tail_s), max_span_s)
    win = replay_window(result, open_ms - int(lead_s * 1000), span)
    return win, min(max(open_ms, win.visible_from_ms), win.end_ms)


def neighbour_basket(result, t_ms: int, direction: int) -> Optional[Tuple[int, int]]:
    """(basket id, open poll ms) of the next (+1) / previous (-1) basket entry relative to a time."""
    ot, oid, _ = basket_opens(result)
    if len(ot) == 0:
        return None
    if direction > 0:
        i = int(np.searchsorted(ot, t_ms, side="right"))
        return (int(oid[i]), int(ot[i])) if i < len(ot) else None
    i = int(np.searchsorted(ot, t_ms, side="left")) - 1
    return (int(oid[i]), int(ot[i])) if i >= 0 else None


# ───────────────────────────── the run ─────────────────────────────

def prepare_window(window: ReplayWindow, store_dir: Path = store.DEFAULT_STORE_DIR) -> fast.Prepared:
    """
    Rows + bars for one window when the full run's ``Prepared`` is not at hand.

    Rows start a few minutes before the anchor so its first poll finds the tick the full
    run saw -- but never before the full run's own start, whose first poll saw nothing
    older. They end a little after the window so a delayed fill (``latency_ms``) reads the
    same later quote. The indicator warm-up is rebuilt from the M1 history in front of the
    window; after ~600 bars the recursions agree with the full run's far below double
    precision, so the trades match -- but only the full run's own ``Prepared`` is
    bit-identical.
    """
    cfg = window.cfg
    lead = int(cfg.market_lookback_s * 1000) + 2 * int(cfg.poll_interval_ms) + 60_000
    data_a = max(window.anchor_ms - lead, window.run_start_ms)
    data_z = max(min(window.end_ms + int(cfg.latency_ms) + 1000, window.data_end_ms), window.end_ms)
    try:
        return fast.prepare(cfg.symbol, data_a, data_z, cfg.timeframes(), mode="sec", store_dir=store_dir)
    except ValueError as e:
        raise ReplayError(f"No tick data in the store for {cfg.symbol} around "
                          f"{store.ms_to_dt(window.visible_from_ms):%Y-%m-%d %H:%M} UTC.") from e


def run_replay(window: ReplayWindow, prep: Optional[fast.Prepared] = None,
               store_dir: Path = store.DEFAULT_STORE_DIR):
    """
    One kernel run over the window with a per-poll trace.

    Pass the ``Prepared`` the full run used (it must hold every timeframe the configuration
    reads and start no later than the anchor) for a bit-identical replay; otherwise the
    window is prepared from the store.
    """
    cfg = window.cfg
    if prep is not None:
        missing = [tf for tf in cfg.timeframes() if tf not in prep.tfs]
        if prep.symbol != cfg.symbol or missing or prep.start_ms > window.anchor_ms or prep.end_ms < window.end_ms:
            prep = None
    if prep is None:
        prep = prepare_window(window, store_dir)
    res = fast.run(cfg, prep, trace=True, store_dir=store_dir)
    if res.counters.get("trace_overflow", 0):
        raise ReplayError("The replay trace overflowed - shorten the window.")
    return res


# ───────────────────────────── candles ─────────────────────────────

class _Bars:
    """Bars of one timeframe: history (from stored M1 bars) followed by the bars of the per-second rows."""
    __slots__ = ("tf_s", "t", "o", "h", "l", "c", "first", "n_hist")

    def __init__(self, tf_s: int, hist: Dict[str, np.ndarray], rows_t: np.ndarray, rows_bid: np.ndarray):
        self.tf_s = int(tf_s)
        if hist and len(hist.get("t", [])):
            hb = store.resample_bars(hist, tf_s)
            ht, ho, hh, hl, hc = hb["t"], hb["o"], hb["h"], hb["l"], hb["c"]
        else:
            ht = np.zeros(0, np.int64)
            ho = hh = hl = hc = np.zeros(0)
        if len(rows_t):
            wb = store.build_bars(rows_t, rows_bid, rows_bid, tf_s)
            first = (np.cumsum(wb["n"]) - wb["n"]).astype(np.int64)
            wt, wo, wh, wl, wc = wb["t"], wb["o"], wb["h"], wb["l"], wb["c"]
        else:
            first = np.zeros(0, np.int64)
            wt = np.zeros(0, np.int64)
            wo = wh = wl = wc = np.zeros(0)
        self.n_hist = int(len(ht))
        self.t = np.concatenate([ht, wt]).astype(np.int64)            # bar open, epoch s
        self.o = np.concatenate([ho, wo]).astype(np.float64)
        self.h = np.concatenate([hh, wh]).astype(np.float64)
        self.l = np.concatenate([hl, wl]).astype(np.float64)
        self.c = np.concatenate([hc, wc]).astype(np.float64)
        self.first = np.concatenate([np.full(self.n_hist, -1, np.int64), first])   # first row of each bar


# ───────────────────────────── the session ─────────────────────────────

class ReplaySession:
    """
    One replay window, ready to be drawn at any playhead time.

    Everything here is derived once from the replay run (its trace, fills and baskets) and
    the per-second rows of the visible window; drawing a frame only slices these arrays.

    The state a frame shows is the state AFTER the poll at or before the playhead has been
    executed: a poll that opens a basket shows the position, the poll that closes it shows
    the account flat with the new balance.
    """

    def __init__(self, window: ReplayWindow, result, rows: Dict[str, np.ndarray],
                 hist_m1: Dict[str, np.ndarray], n_candles: int = N_CANDLES):
        if result.trace is None:
            raise ReplayError("The replay run carries no trace.")
        self.window = window
        self.cfg: BacktestConfig = window.cfg
        self.symbol = self.cfg.symbol
        self.digits = int(self.cfg.spec.digits)
        self.contract = float(self.cfg.spec.contract_size)
        self.n_candles = int(n_candles)
        self.vis_ms = int(window.visible_from_ms)
        self.end_ms = int(window.end_ms)
        self.has_book = bool(self.cfg.book_enabled)
        self.tiers: List[str] = list(self.cfg.ladder_tfs[: self.cfg.n_ladder_adds])
        self.ranges = {"open": score_range(self.cfg.open_weights), "fc": score_range(self.cfg.fc_weights),
                       "book": score_range(self.cfg.book_weights) if self.has_book else 0.0}
        self.fills = result.fills
        self.baskets = result.baskets
        self.counters = dict(result.counters)

        # ── per-poll columns of the trace ──
        tr = result.trace
        self.t = tr[:, K.T_T].astype(np.int64)
        self.n = int(len(self.t))
        self.bid = tr[:, K.T_BID].copy()
        self.ask = tr[:, K.T_ASK].copy()
        self.open_score = tr[:, K.T_OPEN_SCORE].copy()
        self.fc_score = tr[:, K.T_FC_SCORE].copy()
        self.book_score = tr[:, K.T_BOOK_SCORE].copy()
        self.signal = tr[:, K.T_SIGNAL].astype(np.int8)
        self.npos_pre = tr[:, K.T_NPOS].astype(np.int32)        # signed, before the poll's order
        self.profit_pre = tr[:, K.T_PROFIT].copy()
        self.units = tr[:, K.T_UNITS].astype(np.int32)
        self.allowed_pre = tr[:, K.T_ENTRY_ALLOWED] > 0.5
        self.brake = tr[:, K.T_BRAKE] > 0.5
        n_rsi = min(len(self.tiers), K.T_N - K.T_RSI0)
        self.rsi = tr[:, K.T_RSI0:K.T_RSI0 + n_rsi].copy()
        self.vis0 = int(np.searchsorted(self.t, self.vis_ms, side="left"))

        self._build_account()
        self._build_events()

        # ── candles: stored M1 history, then per-second rows of the window ──
        self._row_t = np.ascontiguousarray(rows.get("t_ms", np.zeros(0, np.int64)), dtype=np.int64)
        self._row_bid = np.ascontiguousarray(rows.get("bid", np.zeros(0)), dtype=np.float64)
        self._bars = {tf: _Bars(TF_SECONDS[tf], hist_m1, self._row_t, self._row_bid) for tf in CANDLE_TFS}

    # ── construction ──

    @classmethod
    def build(cls, window: ReplayWindow, result=None, prep: Optional[fast.Prepared] = None,
              store_dir: Path = store.DEFAULT_STORE_DIR, n_candles: int = N_CANDLES) -> "ReplaySession":
        """Run the window (unless ``result`` is given) and load what the candles need."""
        if result is None:
            result = run_replay(window, prep, store_dir)
        symbol = window.cfg.symbol
        rows_a = (window.visible_from_ms // (_ALIGN_S * 1000)) * (_ALIGN_S * 1000)
        rows = None
        if prep is not None and prep.mode == "sec" and prep.symbol == symbol and prep.start_ms <= rows_a \
                and prep.end_ms >= window.end_ms:
            i0 = int(np.searchsorted(prep.t_ms, rows_a, side="left"))
            i1 = int(np.searchsorted(prep.t_ms, window.end_ms, side="left"))
            rows = {"t_ms": prep.t_ms[i0:i1].copy(), "bid": prep.bid[i0:i1].copy()}
        if rows is None:
            rows = store.load_sec(symbol, rows_a, window.end_ms, store_dir) or {}
        # enough M1 history for a full screen of the slowest candle timeframe, weekend included
        depth_ms = (n_candles * max(TF_SECONDS[tf] for tf in CANDLE_TFS) + 4 * 86400) * 1000
        hist = store.load_m1(symbol, rows_a - depth_ms, rows_a, store_dir) or {}
        return cls(window, result, rows, hist, n_candles=n_candles)

    def _build_account(self) -> None:
        """Post-execution account state for every poll, and the position / mark tables."""
        n, f, b = self.n, self.fills, self.baskets
        base = self.window.basket_base
        cooldown = int(round(self.cfg.reentry_cooldown_s * 1000))
        self.npos = np.zeros(n, np.int32)               # signed
        self.lots = np.zeros(n, np.float64)             # signed
        self.avg = np.full(n, np.nan)
        self.balance = np.full(n, float(self.window.balance))
        self.floating = np.zeros(n, np.float64)
        self.cool_until = np.zeros(n, np.int64)
        self.basket_units = np.zeros(n, np.int32)
        self.fill_poll = np.zeros(n, bool)              # polls that carried an order

        ft = _ms(f["time"])
        nf = len(ft)
        action = f["action"].to_numpy() if nf else np.zeros(0, object)
        side = np.where(f["side"].to_numpy() == "BUY", 1, -1) if nf else np.zeros(0, int)
        lots = f["lots"].to_numpy(dtype=np.float64) if nf else np.zeros(0)
        price = f["price"].to_numpy(dtype=np.float64) if nf else np.zeros(0)
        fbasket = f["basket"].to_numpy(dtype=np.int64) if nf else np.zeros(0, np.int64)
        funits = f["units"].to_numpy(dtype=np.int64) if nf else np.zeros(0, np.int64)
        fbal = f["balance"].to_numpy(dtype=np.float64) if nf else np.zeros(0)
        fidx = np.searchsorted(self.t, ft)
        if nf and (fidx.max(initial=0) >= n or not np.array_equal(self.t[np.minimum(fidx, max(n - 1, 0))], ft)):
            raise ReplayError("The replay trace and its fills disagree - the engine output changed shape.")
        b_close = _ms(b["close_time"])
        b_bal = b["balance"].to_numpy(dtype=np.float64) if len(b) else np.zeros(0)

        # every position the run opened: for the entry-price lines
        p_open, p_price, p_lots, p_side, p_basket = [], [], [], [], []
        p_close: List[int] = []
        cur_p: List[float] = []
        cur_l: List[float] = []
        cur_ids: List[int] = []
        cur_side, cur_units, bal, cool = 0, 0, float(self.window.balance), 0

        def flush(a: int, z: int) -> None:
            if z <= a:
                return
            self.balance[a:z] = bal
            self.cool_until[a:z] = cool
            if cur_l:
                tot = float(sum(cur_l))
                self.npos[a:z] = cur_side * len(cur_l)
                self.lots[a:z] = cur_side * tot
                self.avg[a:z] = sum(l * p for l, p in zip(cur_l, cur_p)) / tot
                self.basket_units[a:z] = cur_units
                acc = np.zeros(z - a)
                for p, l in zip(cur_p, cur_l):          # same order and arithmetic as the kernel
                    if cur_side > 0:
                        acc += _round2((self.bid[a:z] - p) * l * self.contract)
                    else:
                        acc += _round2((p - self.ask[a:z]) * l * self.contract)
                self.floating[a:z] = _round2(acc)

        seg = 0
        k = 0
        while k < nf:
            p_idx = int(fidx[k])
            flush(seg, p_idx)
            self.fill_poll[p_idx] = True
            j = k
            while j < nf and fidx[j] == p_idx:
                if action[j] == "close":
                    j += 1
                    continue
                if action[j] == "open":
                    cur_p, cur_l, cur_ids = [], [], []
                    cur_side, cur_units = int(side[j]), int(funits[j])
                cur_ids.append(len(p_open))
                cur_p.append(float(price[j]))
                cur_l.append(float(lots[j]))
                p_open.append(int(ft[j]))
                p_price.append(float(price[j]))
                p_lots.append(float(lots[j]))
                p_side.append(int(side[j]))
                p_basket.append(int(fbasket[j]) + base)
                p_close.append(_NEVER)
                j += 1
            if action[k] == "close":
                lb = int(fbasket[k])
                for pid in cur_ids:
                    p_close[pid] = int(ft[k])
                # the basket row carries the balance after commission; the fills only before it
                bal = float(b_bal[lb]) if lb < len(b_bal) and b_close[lb] == ft[k] else float(fbal[j - 1])
                cool = int(ft[k]) + cooldown
                cur_p, cur_l, cur_ids, cur_side, cur_units = [], [], [], 0, 0
            seg = p_idx
            k = j
        flush(seg, n)
        self.equity = self.balance + self.floating

        self.p_open = np.asarray(p_open, np.int64)
        self.p_close = np.asarray(p_close, np.int64)
        self.p_price = np.asarray(p_price, np.float64)
        self.p_lots = np.asarray(p_lots, np.float64)
        self.p_side = np.asarray(p_side, np.int64)
        self.p_basket = np.asarray(p_basket, np.int64)

        # marks. Pre-roll marks are shown only for a basket that is still open when the visible part begins.
        vis = self.vis_ms
        open_at_vis = set(self.p_basket[(self.p_open < vis) & (self.p_close >= vis)].tolist())
        keep = np.array([(t >= vis) or (int(bk) + base in open_at_vis) for t, bk in zip(ft, fbasket)], bool) \
            if nf else np.zeros(0, bool)
        is_open = (action == "open") & keep if nf else keep
        is_add = (action == "add") & keep if nf else keep
        tier = f["tier"].to_numpy() if nf else np.zeros(0, object)
        self.m_open = dict(t=ft[is_open], price=price[is_open], side=side[is_open], lots=lots[is_open],
                           basket=fbasket[is_open] + base, units=funits[is_open],
                           open_score=f["open_score"].to_numpy(float)[is_open] if nf else np.zeros(0),
                           fc_score=f["fc_score"].to_numpy(float)[is_open] if nf else np.zeros(0))
        self.m_add = dict(t=ft[is_add], price=price[is_add], side=side[is_add], lots=lots[is_add],
                          basket=fbasket[is_add] + base,
                          n_pos=f["n_pos"].to_numpy(int)[is_add] if nf else np.zeros(0, int),
                          tier=tier[is_add],
                          floating=f["basket_profit"].to_numpy(float)[is_add] if nf else np.zeros(0))
        if len(b):
            bk = b_close >= vis
            self.m_exit = dict(t=b_close[bk], price=b["close_price"].to_numpy(float)[bk],
                               open_t=_ms(b["open_time"])[bk], first_price=b["first_price"].to_numpy(float)[bk],
                               side=np.where(b["side"].to_numpy() == "BUY", 1, -1)[bk],
                               pnl=b["pnl"].to_numpy(float)[bk], reason=b["reason"].to_numpy()[bk],
                               n_pos=b["n_pos"].to_numpy(int)[bk], lots=b["lots"].to_numpy(float)[bk],
                               held=b["duration_s"].to_numpy(float)[bk], mae=b["mae"].to_numpy(float)[bk],
                               basket=b["basket"].to_numpy(np.int64)[bk] + base)
        else:
            z = np.zeros(0)
            zi = np.zeros(0, np.int64)
            self.m_exit = dict(t=zi, price=z, open_t=zi, first_price=z, side=zi, pnl=z, reason=np.zeros(0, object),
                               n_pos=zi, lots=z, held=z, mae=z, basket=zi)
        self._open_at_vis = open_at_vis

    def _build_events(self) -> None:
        """The event log: every fill, one line per basket close, and entry signals that were not filled."""
        f, b, base, d = self.fills, self.baskets, self.window.basket_base, self.digits
        ev: List[Tuple[int, int, str, str, str]] = []      # (t_ms, order, tag, text, detail)
        ft = _ms(f["time"])
        vis = self.vis_ms
        if len(f):
            for t, act, sd, lots, price, bk, npos, tier, units, osc, fsc in zip(
                    ft, f["action"], f["side"], f["lots"], f["price"], f["basket"], f["n_pos"], f["tier"],
                    f["units"], f["open_score"], f["fc_score"]):
                full_id = int(bk) + base
                if t < vis and full_id not in self._open_at_vis:
                    continue
                if act == "open":
                    ev.append((int(t), 0, sd, f"{lots:.2f} @ {fmt_price(price, d)}",
                               f"basket #{full_id} · unit {int(units)} · OPEN {osc:+g} / FC {fsc:+g}"))
                elif act == "add":
                    ev.append((int(t), 0, "ADD", f"{sd} {lots:.2f} @ {fmt_price(price, d)}",
                               f"position {int(npos)} · {tier} RSI tier"))
        if len(b):
            for t, reason, pnl, npos, lots, held, bk in zip(_ms(b["close_time"]), b["reason"], b["pnl"], b["n_pos"],
                                                            b["lots"], b["duration_s"], b["basket"]):
                if t < vis:
                    continue
                ev.append((int(t), 1, "CLOSE", f"{REASON_SHORT.get(reason, reason)} {fmt_money(float(pnl))}",
                           f"basket #{int(bk) + base} · {int(npos)} pos · {lots:.2f} lot · held {fmt_dur(float(held))}"))
        # entry signals the account did not take (trading window / brake / margin): first poll of each streak
        if self.n:
            want = (self.signal == 1) | (self.signal == 2)
            unfilled = want & ~self.fill_poll
            starts = np.flatnonzero(unfilled & ~np.concatenate([[False], unfilled[:-1]]))
            for i in starts[starts >= self.vis0]:
                why = "trading window closed" if self.brake[i] else "not filled (entry filter or margin)"
                ev.append((int(self.t[i]), 0, "SKIP", f"{_SIGNAL[int(self.signal[i])]} signal - {why}", ""))
        ev.sort(key=lambda e: (e[0], e[1]))
        self.events = ev
        self._event_t = np.asarray([e[0] for e in ev], np.int64)

    # ── the playhead ──

    def clamp(self, t_ms) -> int:
        return int(min(max(int(t_ms), self.vis_ms), self.end_ms))

    def poll_index(self, t_ms) -> int:
        """Index of the last poll at or before a time (-1 before the first poll)."""
        return int(np.searchsorted(self.t, int(t_ms), side="right")) - 1

    def row_index(self, t_ms) -> int:
        return int(np.searchsorted(self._row_t, int(t_ms), side="right")) - 1

    def step(self, t_ms, n: int) -> int:
        """The playhead moved by ``n`` polls (visible polls only)."""
        t_ms = self.clamp(t_ms)
        if self.n == 0 or n == 0:
            return t_ms
        if n > 0:
            i = int(np.searchsorted(self.t, t_ms, side="right")) + (n - 1)
            return self.end_ms if i >= self.n else self.clamp(self.t[i])
        i = int(np.searchsorted(self.t, t_ms, side="left")) + n
        return self.vis_ms if i < self.vis0 else self.clamp(self.t[i])

    def frame_key(self, t_ms, tf: str) -> Tuple[int, int, str]:
        """Two playheads with the same key draw the same frame."""
        return self.poll_index(t_ms), self.row_index(t_ms), tf

    # ── what the side panel shows ──

    def state(self, t_ms) -> dict:
        t_ms = self.clamp(t_ms)
        cfg = self.cfg
        i = self.poll_index(t_ms)
        j = self.row_index(t_ms)
        s = dict(t_ms=t_ms, poll=i, symbol=self.symbol, digits=self.digits, has_book=self.has_book,
                 tiers=list(self.tiers), ranges=dict(self.ranges), npos=0, side=0, lots=0.0, avg=None,
                 balance=float(self.window.balance), floating=0.0, equity=float(self.window.balance),
                 units=1, basket_units=0, open_score=0.0, fc_score=0.0, book_score=0.0, rsi=[], armed=None,
                 ladder_full=False, cooldown_s=0.0, brake=False, signal="", bid=None, ask=None, spread=None,
                 live=False, positions=[], status=[], target=None, poll_ms=None)
        if j >= 0 and i < 0:
            s["bid"] = float(self._row_bid[j])
        if i < 0:
            s["status"] = ["waiting for the first tick"]
            return s
        npos = int(self.npos[i])
        side = 1 if npos > 0 else -1 if npos < 0 else 0
        count = abs(npos)
        o, fcs, bks = float(self.open_score[i]), float(self.fc_score[i]), float(self.book_score[i])
        cool = max(0.0, (int(self.cool_until[i]) - t_ms) / 1000.0)
        live = (t_ms - int(self.t[i])) <= cfg.market_lookback_s * 1000 + 2 * cfg.poll_interval_ms
        mask = (self.p_open <= self.t[i]) & (self.t[i] < self.p_close)
        positions = [dict(lots=float(l), price=float(p), t_ms=int(t0))
                     for l, p, t0 in zip(self.p_lots[mask], self.p_price[mask], self.p_open[mask])]
        s.update(npos=npos, side=side, lots=float(self.lots[i]), avg=None if count == 0 else float(self.avg[i]),
                 balance=float(self.balance[i]), floating=float(self.floating[i]), equity=float(self.equity[i]),
                 units=int(self.units[i]), basket_units=int(self.basket_units[i]),
                 open_score=o, fc_score=fcs, book_score=bks, rsi=[float(x) for x in self.rsi[i]],
                 cooldown_s=cool, brake=bool(self.brake[i]), signal=_SIGNAL.get(int(self.signal[i]), ""),
                 bid=float(self.bid[i]), ask=float(self.ask[i]), spread=float(self.ask[i] - self.bid[i]),
                 live=bool(live), positions=positions, poll_ms=int(self.t[i]))
        if count >= 1:
            if count <= len(self.tiers):
                s["armed"] = count - 1                    # the tier that would add the next position
            elif len(self.tiers):
                s["ladder_full"] = True
            u = max(int(self.basket_units[i]), 1)
            s["target"] = (cfg.profit_protect_usd_per_unit * u if cfg.book_enabled
                           else cfg.target_usd_per_unit * u if cfg.target_usd_per_unit is not None else None)

        # one-line reading of what the bot is waiting for
        st: List[str] = []
        if not live:
            st.append("market closed - no ticks")
        elif count == 0:
            want = 1 if o >= cfg.entry_s else -1 if o <= -cfg.entry_s else 0
            agree = (want > 0 and fcs >= cfg.entry_agree_s) or (want < 0 and fcs <= -cfg.entry_agree_s)
            name = "BUY" if want > 0 else "SELL"
            if want == 0:
                st.append(f"flat - OPEN score inside ±{cfg.entry_s:g}")
            elif not agree:
                st.append(f"OPEN wants {name} - waiting for FORCE-CLOSE to agree "
                          f"({'≥ +' if want > 0 else '≤ -'}{cfg.entry_agree_s:g})")
            elif cool > 0:
                st.append(f"{name} ready - re-entry cooldown")
            elif self.brake[i]:
                st.append(f"{name} ready - outside the trading window")
            else:
                st.append(f"{name} ready")
            if cool > 0 and (want == 0 or not agree):
                st.append("re-entry cooldown running")
        else:
            gate_ok = o > -cfg.ladder_s if side > 0 else o < cfg.ladder_s
            if s["ladder_full"]:
                st.append(f"ladder full ({count} positions) - waiting for an exit")
            elif s["armed"] is not None:
                tfn = self.tiers[s["armed"]]
                lim = f"≤ {cfg.rsi_oversold:g}" if side > 0 else f"≥ {cfg.rsi_overbought:g}"
                st.append(f"next add when {tfn} RSI {lim}" + ("" if gate_ok else " - blocked by the OPEN score"))
            else:
                st.append("holding - ladder off")
        s["status"] = st
        return s

    def recent_events(self, t_ms, limit: int = 60) -> List[dict]:
        """Events up to the playhead, latest first."""
        k = int(np.searchsorted(self._event_t, self.clamp(t_ms), side="right"))
        out = []
        for t, _, tag, text, detail in reversed(self.events[max(0, k - limit):k]):
            out.append(dict(t_ms=t, time=_iso1(t, "s")[11:], date=_iso1(t, "s")[:10], tag=tag, text=text, detail=detail))
        return out

    def basket_marks(self) -> List[Tuple[int, int]]:
        """(open poll ms, full-run basket id) of the entries inside the visible part."""
        m = self.m_open
        return [(int(t), int(b)) for t, b in zip(m["t"], m["basket"]) if t >= self.vis_ms]

    # ── candles ──

    def candles(self, t_ms, tf: str, n: Optional[int] = None) -> Dict[str, np.ndarray]:
        """
        The last ``n`` candles at a playhead. Closed bars come whole; the final one is built
        only from the per-second rows up to the playhead, so it grows tick by tick.
        """
        n = int(n or self.n_candles)
        B = self._bars[tf]
        j = self.row_index(self.clamp(t_ms))
        if j < 0:
            k = B.n_hist
            lo = max(0, k - n)
            return dict(t=B.t[lo:k].copy(), o=B.o[lo:k].copy(), h=B.h[lo:k].copy(), l=B.l[lo:k].copy(),
                        c=B.c[lo:k].copy(), forming=False, tf_s=B.tf_s)
        b = int(np.searchsorted(B.first, j, side="right")) - 1          # the bar holding row j
        lo = max(0, b - (n - 1))
        seg = self._row_bid[B.first[b]:j + 1]
        return dict(t=B.t[lo:b + 1].copy(),
                    o=np.append(B.o[lo:b], seg[0]), h=np.append(B.h[lo:b], seg.max()),
                    l=np.append(B.l[lo:b], seg.min()), c=np.append(B.c[lo:b], seg[-1]),
                    forming=True, tf_s=B.tf_s)

    # ── the frame ──

    def _steps(self, v: np.ndarray, a: int, z: int, cap: int = 700) -> Tuple[np.ndarray, np.ndarray]:
        """A piecewise-constant per-poll series over polls [a, z] as its change points (plus both ends)."""
        if z < a:
            return np.zeros(0, np.int64), np.zeros(0)
        seg = v[a:z + 1]
        idx = np.flatnonzero(np.diff(seg) != 0) + 1
        idx = np.unique(np.concatenate([[0], idx, [len(seg) - 1]]))
        if len(idx) > cap:      # a very wide view of a flickering score: thin it evenly, keep both ends
            idx = idx[np.unique(np.linspace(0, len(idx) - 1, cap).astype(int))]
        return self.t[a + idx], seg[idx]

    def _envelope(self, v: np.ndarray, a: int, z: int, buckets: int = 220) -> Tuple[np.ndarray, np.ndarray]:
        """Per-poll series over polls [a, z], thinned to first / min / max / last per time bucket."""
        if z < a:
            return np.zeros(0, np.int64), np.zeros(0)
        m = z - a + 1
        if m <= 4 * buckets:
            return self.t[a:z + 1], v[a:z + 1]
        edges = np.linspace(a, z + 1, buckets + 1).astype(np.int64)
        keep: List[int] = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            if hi <= lo:
                continue
            w = v[lo:hi]
            keep.extend({lo, lo + int(w.argmin()), lo + int(w.argmax()), hi - 1})
        idx = np.asarray(sorted(set(keep)), np.int64)
        return self.t[idx], v[idx]

    def figure(self, t_ms, tf: str = "M1") -> dict:
        """
        The plotly figure of one frame, as a plain dict (cheap to build ~2.5 times a second).

        Three stacked panels on one time axis: candles with the fills, the entry-price lines
        of the open positions and their average; the section scores; the floating P/L of the
        open basket. Nothing after the playhead is in it.
        """
        if tf not in CANDLE_TFS:
            tf = CANDLE_TFS[0]
        cfg = self.cfg
        t_ms = self.clamp(t_ms)
        cd = self.candles(t_ms, tf)
        tf_ms = cd["tf_s"] * 1000
        ct = cd["t"] * 1000                              # bar open, ms
        i = self.poll_index(t_ms)
        d = self.digits
        data: List[dict] = []
        shapes: List[dict] = []
        notes: List[dict] = []

        if len(ct):
            x_lo = int(ct[0])
            x_hi = int(ct[-1]) + tf_ms
        else:
            x_lo, x_hi = t_ms - self.n_candles * tf_ms, t_ms + tf_ms
        pad = max(int((x_hi - x_lo) * 0.012), tf_ms // 2)
        x_rng = [_iso1(x_lo - pad), _iso1(x_hi + pad)]
        line_lo = max(x_lo, self.vis_ms)                 # nothing of the pre-roll is drawn

        # ── price panel ──
        if len(ct):
            data.append(dict(
                type="candlestick", x=_iso(ct + tf_ms // 2), open=cd["o"].tolist(), high=cd["h"].tolist(),
                low=cd["l"].tolist(), close=cd["c"].tolist(), name=f"{self.symbol} {tf}", xaxis="x", yaxis="y",
                increasing=dict(line=dict(color=T.UP, width=1), fillcolor=T.UP),
                decreasing=dict(line=dict(color=T.DOWN, width=1), fillcolor=T.DOWN),
                showlegend=False, hoverlabel=dict(namelength=0)))
        y_lo = float(cd["l"].min()) if len(ct) else (float(self.bid[i]) if i >= 0 else 0.0)
        y_hi = float(cd["h"].max()) if len(ct) else (float(self.bid[i]) if i >= 0 else 1.0)
        span_y = max(y_hi - y_lo, abs(y_hi) * 2e-5, 10.0 ** (-d))

        npos = int(self.npos[i]) if i >= 0 else 0
        if npos != 0:
            now = self.t[i]
            m = (self.p_open <= now) & (now < self.p_close)
            col = T.UP if npos > 0 else T.DOWN
            xs: List[Optional[str]] = []
            ys: List[Optional[float]] = []
            right = _iso1(x_hi + pad)
            for t0, p in zip(self.p_open[m], self.p_price[m]):
                xs += [_iso1(max(int(t0), x_lo - pad)), right, None]
                ys += [float(p), float(p), None]
            data.append(dict(type="scatter", mode="lines", x=xs, y=ys, xaxis="x", yaxis="y",
                             line=dict(color=col, width=1), opacity=0.55, hoverinfo="skip", showlegend=False))
            avg = float(self.avg[i])
            t_first = int(self.p_open[m].min())
            data.append(dict(type="scatter", mode="lines", x=[_iso1(max(t_first, x_lo - pad)), right], y=[avg, avg],
                             xaxis="x", yaxis="y", line=dict(color=T.ACCENT, width=1.4), hoverinfo="skip",
                             showlegend=False))
            notes.append(dict(xref="paper", x=0.004, xanchor="left", yref="y", y=avg, yanchor="bottom", yshift=2,
                              text=f"avg entry {fmt_price(avg, d)} · {abs(float(self.lots[i])):.2f} lot",
                              showarrow=False, font=dict(color=T.INK_2, size=11)))
            # keep the entries in view unless they are far away from the candles
            lo_e, hi_e = float(self.p_price[m].min()), float(self.p_price[m].max())
            y_lo = min(y_lo, max(lo_e, y_lo - 1.5 * span_y))
            y_hi = max(y_hi, min(hi_e, y_hi + 1.5 * span_y))

        # entry -> exit connectors and the marks, for fills up to the playhead inside the view
        ring = dict(color=T.SURFACE, width=1.5)
        ex = self.m_exit
        em = (ex["t"] <= t_ms) & (ex["t"] >= x_lo - pad)
        for won, color in ((True, T.UP), (False, T.DOWN)):
            g = em & ((ex["pnl"] > 0) if won else (ex["pnl"] <= 0))
            if g.any():
                xs, ys = [], []
                for t0, t1, p0, p1 in zip(ex["open_t"][g], ex["t"][g], ex["first_price"][g], ex["price"][g]):
                    xs += [_iso1(max(int(t0), x_lo - pad)), _iso1(int(t1)), None]
                    ys += [float(p0), float(p1), None]
                data.append(dict(type="scatter", mode="lines", x=xs, y=ys, xaxis="x", yaxis="y",
                                 line=dict(color=color, width=1), opacity=0.4, hoverinfo="skip", showlegend=False))
        mo = self.m_open
        g = (mo["t"] <= t_ms) & (mo["t"] >= x_lo - pad)
        if g.any():
            buy = mo["side"][g] > 0
            data.append(dict(
                type="scatter", mode="markers", x=_iso(mo["t"][g]), y=mo["price"][g].tolist(), xaxis="x", yaxis="y",
                name="Entry", showlegend=False,
                marker=dict(symbol=np.where(buy, "triangle-up", "triangle-down").tolist(), size=13,
                            color=np.where(buy, T.UP, T.DOWN).tolist(), line=ring),
                customdata=np.stack([mo["lots"][g], mo["basket"][g], mo["units"][g], mo["open_score"][g],
                                     mo["fc_score"][g]], axis=1).tolist(),
                text=np.where(buy, "BUY", "SELL").tolist(),
                hovertemplate=("<b>OPEN %{text}</b> %{customdata[0]:.2f} lot @ %{y:,." + str(d) + "f}"
                               "<br>basket #%{customdata[1]:.0f} · unit %{customdata[2]:.0f}"
                               "<br>OPEN score %{customdata[3]:+.0f} · FC score %{customdata[4]:+.0f}"
                               "<br>%{x|%H:%M:%S}<extra></extra>")))
        ma = self.m_add
        g = (ma["t"] <= t_ms) & (ma["t"] >= x_lo - pad)
        if g.any():
            buy = ma["side"][g] > 0
            colors = np.where(buy, T.UP, T.DOWN).tolist()
            data.append(dict(
                type="scatter", mode="markers", x=_iso(ma["t"][g]), y=ma["price"][g].tolist(), xaxis="x", yaxis="y",
                name="Ladder add", showlegend=False,
                marker=dict(symbol=np.where(buy, "triangle-up-open", "triangle-down-open").tolist(), size=11,
                            color=colors, line=dict(color=colors, width=1.8)),
                customdata=np.stack([ma["lots"][g], ma["n_pos"][g], ma["basket"][g], ma["floating"][g]], axis=1).tolist(),
                text=[f"{'BUY' if s > 0 else 'SELL'} · {tr} RSI tier" for s, tr in zip(ma["side"][g], ma["tier"][g])],
                hovertemplate=("<b>ADD %{text}</b><br>%{customdata[0]:.2f} lot @ %{y:,." + str(d) + "f} · position %{customdata[1]:.0f}"
                               "<br>basket #%{customdata[2]:.0f} floating %{customdata[3]:+,.2f} before the add"
                               "<br>%{x|%H:%M:%S}<extra></extra>")))
        if em.any():
            won = ex["pnl"][em] > 0
            sym = [T.REASON_SYMBOL.get(r, "circle") for r in ex["reason"][em]]
            colors = np.where(won, T.UP, T.DOWN).tolist()
            data.append(dict(
                type="scatter", mode="markers", x=_iso(ex["t"][em]), y=ex["price"][em].tolist(), xaxis="x", yaxis="y",
                name="Exit", showlegend=False,
                marker=dict(symbol=sym, size=12, color=colors,
                            line=dict(color=[c if s == "x" else T.SURFACE for c, s in zip(colors, sym)],
                                      width=[2.2 if s == "x" else 1.5 for s in sym])),
                customdata=np.stack([ex["pnl"][em], ex["n_pos"][em], ex["lots"][em], ex["held"][em], ex["basket"][em],
                                     ex["mae"][em]], axis=1).tolist(),
                text=[REASON_SHORT.get(r, r) for r in ex["reason"][em]],
                hovertemplate=("<b>CLOSE</b> (%{text}) @ %{y:,." + str(d) + "f}"
                               "<br>basket #%{customdata[4]:.0f} · %{customdata[1]:.0f} pos · %{customdata[2]:.2f} lot"
                               "<br>P/L <b>%{customdata[0]:+,.2f}</b> · worst floating %{customdata[5]:+,.2f}"
                               "<br>held %{customdata[3]:,.0f}s · %{x|%H:%M:%S}<extra></extra>")))

        # the live quote: a hairline at the bid with its price tag on the axis
        j = self.row_index(t_ms)
        bid_now = float(self._row_bid[j]) if j >= 0 else (float(self.bid[i]) if i >= 0 else None)
        if bid_now is not None:
            shapes.append(dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=bid_now, y1=bid_now,
                               line=dict(color=T.INK_MUTED, width=1), opacity=0.55, layer="above"))
            notes.append(dict(xref="paper", x=1.0, xanchor="left", xshift=3, yref="y", y=bid_now, yanchor="middle",
                              text=fmt_price(bid_now, d), showarrow=False, bgcolor=T.SURFACE_2, bordercolor=T.AXIS,
                              borderwidth=1, borderpad=2, font=dict(color=T.INK, size=11)))
            y_lo, y_hi = min(y_lo, bid_now), max(y_hi, bid_now)
        py_pad = max((y_hi - y_lo) * 0.07, 10.0 ** (-d))
        y_rng = [y_lo - py_pad, y_hi + py_pad]
        step = (y_rng[1] - y_rng[0]) / 6.0
        dec = int(min(max(0, math.ceil(-math.log10(step)) if step > 0 else 0), d))

        # ── score panel ──
        a = max(int(np.searchsorted(self.t, line_lo, side="left")), self.vis0)
        series = [("open", "open_score", self.open_score, 2.6), ("fc", "fc_score", self.fc_score, 1.5)]
        if self.has_book:
            series.append(("book", "book_score", self.book_score, 1.5))
        s_max = 1.0
        for key, col_key, arr, width in series:
            s_max = max(s_max, self.ranges[key])
            xs_, ys_ = self._steps(arr, a, i)
            data.append(dict(type="scatter", mode="lines", x=_iso(xs_), y=ys_.tolist(), xaxis="x", yaxis="y2",
                             name=T.SCORE_LABEL[col_key], line=dict(color=T.SCORE_COLOR[col_key], width=width, shape="hv"),
                             hovertemplate=T.SCORE_LABEL[col_key] + " %{y:+.0f} · %{x|%H:%M:%S}<extra></extra>"))

        top = int(math.floor(s_max + 1e-9))
        s_step = 1 if top <= 2 else 2 if top <= 6 else 4
        s_ticks = [v for v in range(-top, top + 1) if v % s_step == 0]

        # ── floating P/L panel ──
        xs_, ys_ = self._envelope(self.floating, a, i)
        fx = _iso(xs_)
        up = np.clip(ys_, 0.0, None)
        dn = np.clip(ys_, None, 0.0)
        data.append(dict(type="scatter", mode="lines", x=fx, y=up.tolist(), xaxis="x", yaxis="y3", fill="tozeroy",
                         fillcolor="rgba(45,171,146,0.22)", line=dict(width=0), hoverinfo="skip", showlegend=False))
        data.append(dict(type="scatter", mode="lines", x=fx, y=dn.tolist(), xaxis="x", yaxis="y3", fill="tozeroy",
                         fillcolor="rgba(217,74,74,0.22)", line=dict(width=0), hoverinfo="skip", showlegend=False))
        data.append(dict(type="scatter", mode="lines", x=fx, y=ys_.tolist(), xaxis="x", yaxis="y3", name="Floating P/L",
                         line=dict(color=T.INK_2, width=1.6), showlegend=False,
                         hovertemplate="floating %{y:+,.2f} · %{x|%H:%M:%S}<extra></extra>"))
        p_lo = min(float(ys_.min()) if len(ys_) else 0.0, 0.0)
        p_hi = max(float(ys_.max()) if len(ys_) else 0.0, 0.0)
        units_now = max(int(self.basket_units[i]) if i >= 0 and npos != 0 else (int(self.units[i]) if i >= 0 else 1), 1)
        goal = (cfg.profit_protect_usd_per_unit if cfg.book_enabled else cfg.target_usd_per_unit)
        if goal is not None:
            gy = float(goal) * units_now
            p_hi = max(p_hi, gy)
            shapes.append(dict(type="line", xref="paper", x0=0, x1=1, yref="y3", y0=gy, y1=gy,
                               line=dict(color=T.CONTEXT, width=1)))
            notes.append(dict(xref="paper", x=0.996, xanchor="right", yref="y3", y=gy, yanchor="bottom",
                              text=("book armed above " if cfg.book_enabled else "target ") + fmt_money(gy),
                              showarrow=False, font=dict(color=T.INK_MUTED, size=10.5)))
        if cfg.stop_loss_usd_per_unit is not None:
            sy = -float(cfg.stop_loss_usd_per_unit) * units_now
            p_lo = min(p_lo, sy)
            shapes.append(dict(type="line", xref="paper", x0=0, x1=1, yref="y3", y0=sy, y1=sy,
                               line=dict(color=T.CONTEXT, width=1)))
            notes.append(dict(xref="paper", x=0.996, xanchor="right", yref="y3", y=sy, yanchor="top",
                              text="stop-loss " + fmt_money(sy), showarrow=False, font=dict(color=T.INK_MUTED, size=10.5)))
        pp = max((p_hi - p_lo) * 0.14, 0.2)

        # panel captions
        for y_top, text in ((1.0, f"{self.symbol} · bid · {tf} candles"), (0.375, "Section scores"),
                            (0.165, "Floating P/L of the open basket, USD")):
            notes.append(dict(xref="paper", yref="paper", x=0.0, y=y_top, xanchor="left", yanchor="bottom",
                              text=text, showarrow=False, font=dict(color=T.INK_MUTED, size=11)))

        # hide long no-tick gaps (the daily break, the weekend) so the candles stay adjacent
        breaks = []
        if len(ct) > 1:
            gap_min = max(8 * tf_ms, 15 * 60_000)
            for k in np.flatnonzero(np.diff(ct) > gap_min):
                a_ms, z_ms = int(ct[k]) + tf_ms, int(ct[k + 1])
                breaks.append(dict(values=[_iso1(a_ms)], dvalue=z_ms - a_ms))

        layout = T.plotly_layout(
            margin=dict(l=10, r=78, t=22, b=30), hovermode="closest", dragmode="pan", showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=0.372, xanchor="right", x=1.0,
                        bgcolor="rgba(0,0,0,0)", font=dict(color=T.INK_2, size=11)),
            uirevision=f"{self.window.key}:{tf}", shapes=shapes, annotations=notes,
            xaxis=T.axis(type="date", anchor="y3", domain=[0.0, 1.0], range=x_rng, rangebreaks=breaks,
                         rangeslider=dict(visible=False), showspikes=True, spikemode="across", spikesnap="cursor",
                         spikethickness=1, spikecolor=T.AXIS, spikedash="solid", automargin=False),
            yaxis=T.axis(domain=[0.43, 1.0], side="right", range=y_rng, tickformat=f",.{dec}f", automargin=False),
            yaxis2=T.axis(domain=[0.215, 0.37], side="right", range=[-s_max - 0.6, s_max + 0.6],
                          tickmode="array", tickvals=s_ticks, ticktext=[f"{v:+d}" if v else "0" for v in s_ticks],
                          zeroline=True, zerolinecolor=T.AXIS, automargin=False),
            yaxis3=T.axis(domain=[0.0, 0.16], side="right", range=[p_lo - pp, p_hi + pp], zeroline=True,
                          zerolinecolor=T.AXIS, tickformat="+,.2f", nticks=5, automargin=False),
        )
        return dict(data=data, layout=layout)
