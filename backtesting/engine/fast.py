"""
Fast engine: data preparation + a thin wrapper around the numba kernel.

Typical use::

    from backtesting.config import BacktestConfig
    from backtesting.engine.fast import run

    res = run(BacktestConfig.live("XAUUSDm"))
    print(res.summary())

``prepare`` loads the rows and builds the per-timeframe bar closes once; many
configurations (a sweep) can then be run against the same ``Prepared`` object.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import BacktestConfig, TF_SECONDS
from ..data import store
from . import kernels as K

SIGNAL_NAMES = {0: "DO_NOTHING", 1: "BUY", 2: "SELL", 3: "CLOSE_BUY", 4: "CLOSE_SELL",
                5: "BUY_MORE", 6: "SELL_MORE"}
REASON_NAMES = {K.R_NONE: "", K.R_TARGET: "target", K.R_BOOK: "book", K.R_FORCE: "force_close",
                K.R_STOPOUT: "stop_out", K.R_STOPLOSS: "stop_loss", K.R_END: "end", K.R_TIME: "time_stop",
                K.R_HOLE: "data_hole"}
ACTION_NAMES = {K.ACT_OPEN: "open", K.ACT_ADD: "add", K.ACT_CLOSE: "close"}

DEFAULT_WARM_BARS = 600   # the live bot fetches 500 bars per timeframe; this fully converges RSI/MACD


@dataclass
class Prepared:
    """Rows + per-timeframe bars for one symbol/window, reusable across configurations."""
    symbol: str
    start_ms: int
    end_ms: int
    mode: str                         # 'sec' (last tick per second) or 'ticks' (every tick)
    t_ms: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    tfs: List[str]
    closes: Dict[str, np.ndarray]     # warm-up bars followed by in-window bars
    bar_t: Dict[str, np.ndarray]      # bar open time (epoch s), same layout
    nwarm: Dict[str, int]
    start_row: Dict[str, np.ndarray]  # first row of each bar (-1 for warm-up bars)
    # silences of five minutes or more, (from_ms, to_ms), in the warm-up history and inside the window
    gaps: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), np.int64))
    # time of the first quote the history holds at or after ``end_ms`` (-1: not looked up, the end is used)
    after_ms: int = -1
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def n_rows(self) -> int:
        return int(len(self.t_ms))

    def flat(self, cfg: BacktestConfig) -> dict:
        """Flattened per-timeframe arrays for the indicator parameters in ``cfg`` (cached)."""
        key = (cfg.rsi_length, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal,
               cfg.pivot_width, float(cfg.rsi_peak_ob), float(cfg.rsi_peak_os))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        n_tf = len(self.tfs)
        off = np.zeros(n_tf, np.int64)
        nb = np.zeros(n_tf, np.int64)
        nwarm = np.zeros(n_tf, np.int64)
        parts = {k: [] for k in ("START_ROW", "C", "AG", "AL", "RSI", "EF", "ES", "SG", "HIST",
                                 "R_PH", "R_PL", "R_CH", "R_CL", "M_PH", "M_PL", "M_CH", "M_CL")}
        pos = 0
        for f, tf in enumerate(self.tfs):
            C = np.ascontiguousarray(self.closes[tf], dtype=np.float64)
            AG, AL, RSI, EF, ES, SG, HIST = K.indicator_arrays(
                C, cfg.rsi_length, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
            r_ph, r_pl, r_ch, r_cl = K.pivot_arrays(RSI, cfg.pivot_width, True,
                                                    float(cfg.rsi_peak_ob), float(cfg.rsi_peak_os))
            m_ph, m_pl, m_ch, m_cl = K.pivot_arrays(HIST, cfg.pivot_width, False, 0.0, 0.0)
            off[f] = pos
            nb[f] = len(C)
            nwarm[f] = self.nwarm[tf]
            pos += len(C)
            for name, arr in (("START_ROW", self.start_row[tf]), ("C", C), ("AG", AG), ("AL", AL),
                              ("RSI", RSI), ("EF", EF), ("ES", ES), ("SG", SG), ("HIST", HIST),
                              ("R_PH", r_ph), ("R_PL", r_pl), ("R_CH", r_ch), ("R_CL", r_cl),
                              ("M_PH", m_ph), ("M_PL", m_pl), ("M_CH", m_ch), ("M_CL", m_cl)):
                parts[name].append(arr)
        out = {k: np.ascontiguousarray(np.concatenate(v)) for k, v in parts.items()}
        out.update(off=off, nb=nb, nwarm=nwarm)
        self._cache[key] = out
        return out


def _window_bars(t_ms: np.ndarray, bid: np.ndarray, tf_s: int):
    """In-window bars from rows: (bar id, first row, close)."""
    bar = t_ms // (tf_s * 1000)
    first = np.flatnonzero(np.diff(bar, prepend=bar[0] - 1) != 0)
    last = np.append(first[1:] - 1, len(bar) - 1)
    return bar[first], first.astype(np.int64), bid[last]


def prepare(symbol: str, start, end, tfs: Sequence[str], mode: str = "sec",
            warm_bars: int = DEFAULT_WARM_BARS, store_dir: Path = store.DEFAULT_STORE_DIR) -> Prepared:
    """
    Load rows for [start, end) and build bar closes for every timeframe in ``tfs``.

    Indicator warm-up comes from M1 bars *before* ``start`` (up to ``warm_bars`` bars per
    timeframe), so the first poll of the window already sees converged RSI / MACD, just as
    the live bot does with its 500-bar fetch.
    """
    start_ms, end_ms = store.to_ms(start), store.to_ms(end)
    rows = store.load_ticks(symbol, start_ms, end_ms, store_dir) if mode == "ticks" \
        else store.load_sec(symbol, start_ms, end_ms, store_dir)
    if not rows or len(rows["t_ms"]) == 0:
        raise ValueError(f"no {mode} data for {symbol} in [{store.ms_to_dt(start_ms)}, {store.ms_to_dt(end_ms)}) "
                         f"- run `python -m backtesting data` first")
    t_ms = np.ascontiguousarray(rows["t_ms"], dtype=np.int64)
    bid = np.ascontiguousarray(rows["bid"], dtype=np.float64)
    ask = np.ascontiguousarray(rows["ask"], dtype=np.float64)

    tfs = sorted(set(tfs), key=TF_SECONDS.get)
    span = store.data_span(symbol, store_dir)
    hist_start_ms = store.to_ms(span[0]) if span else start_ms
    max_tf = max(TF_SECONDS[tf] for tf in tfs)
    # enough calendar time for warm_bars of the slowest timeframe, weekend gaps included
    want_ms = int(warm_bars * max_tf * 1000 * 1.7) + 7 * 86400 * 1000
    warm_from = max(hist_start_ms, start_ms - want_ms)
    m1 = store.load_m1(symbol, warm_from, start_ms, store_dir) if warm_from < start_ms else {}

    closes, bar_t, nwarm, start_row = {}, {}, {}, {}
    for tf in tfs:
        tf_s = TF_SECONDS[tf]
        ids, first, c = _window_bars(t_ms, bid, tf_s)
        if m1 and len(m1["t"]):
            wb = store.resample_bars(m1, tf_s)
            w_ids, w_c = wb["t"] // tf_s, wb["c"]
            # a bar straddling `start` belongs to the window (its close is an in-window tick)
            keep = w_ids < ids[0]
            w_ids, w_c = w_ids[keep][-warm_bars:], w_c[keep][-warm_bars:]
        else:
            w_ids, w_c = np.zeros(0, np.int64), np.zeros(0)
        closes[tf] = np.concatenate([w_c, c]).astype(np.float64)
        bar_t[tf] = np.concatenate([w_ids, ids]).astype(np.int64) * tf_s
        nwarm[tf] = int(len(w_c))
        start_row[tf] = np.concatenate([np.full(len(w_c), -1, np.int64), first])
    # the quotes of the last minutes before the window, only to time a session break that ended there exactly
    pre = store.load_sec(symbol, start_ms - _PRE_MS, start_ms, store_dir) if warm_from < start_ms else {}
    pre_t = np.asarray(pre["t_ms"], np.int64) if pre and len(pre["t_ms"]) else np.zeros(0, np.int64)
    return Prepared(symbol, start_ms, end_ms, mode, t_ms, bid, ask, list(tfs),
                    closes, bar_t, nwarm, start_row, _silences(m1, t_ms, np.concatenate([pre_t, t_ms[:1]])),
                    after_ms=_next_quote_ms(symbol, end_ms, store_dir))


_PRE_MS = 600_000      # how far before the window the exact quote times are looked at
_AFTER_MS = 7 * 86_400_000     # how far past the window the time of the next quote is looked for


def _next_quote_ms(symbol: str, end_ms: int, store_dir: Path = store.DEFAULT_STORE_DIR) -> int:
    """
    The time of the first quote the history holds at or after the end of a window (to the second),
    or the end itself when the history stops there. Only this TIME is used, never the price: a
    window whose last quote is followed by half an hour or more without one ended with the market
    closed, and an order sent after that quote has to be refused there as it is everywhere else.
    """
    nxt = store.load_sec(symbol, end_ms, end_ms + _AFTER_MS, store_dir)
    return int(nxt["t_ms"][0]) if nxt and len(nxt["t_ms"]) else int(end_ms)


def _silences(m1: dict, t_ms: np.ndarray, pre_t: Optional[np.ndarray] = None, at_least_ms: int = 300_000) -> np.ndarray:
    """
    (from_ms, to_ms) of every silence of ``at_least_ms`` or more in the warm-up M1 history and the window rows.

    An M1 bar only says that a quote fell somewhere inside its minute, so a silence read off the bars
    starts at a minute's end and ends at a minute's start. ``pre_t`` (the quote times of the last minutes
    before the window) lets a silence that ended there be timed to its first quote, which is what the
    broker's close-only period after a session break is counted from.
    """
    out = []
    if m1 and len(m1["t"]) > 0:
        mt = np.asarray(m1["t"], np.int64) * 1000
        for i in np.flatnonzero(np.diff(mt) >= at_least_ms + 60_000):
            end = int(mt[i + 1])
            if pre_t is not None and len(pre_t) and end >= int(pre_t[0]) - 60_000:
                k = int(np.searchsorted(pre_t, end))
                if k < len(pre_t) and int(pre_t[k]) < end + 60_000:
                    end = int(pre_t[k])                      # the first quote of that minute
            out.append((int(mt[i]) + 60_000, end))
        if len(t_ms) and int(t_ms[0]) - (int(mt[-1]) + 60_000) >= at_least_ms:
            out.append((int(mt[-1]) + 60_000, int(t_ms[0])))
    if len(t_ms) > 1:
        for i in np.flatnonzero(np.diff(t_ms) >= at_least_ms):
            out.append((int(t_ms[i]), int(t_ms[i + 1])))
    return np.array(sorted(out), dtype=np.int64).reshape(-1, 2)


@dataclass
class Result:
    cfg: BacktestConfig
    fills: pd.DataFrame
    baskets: pd.DataFrame
    equity: pd.DataFrame
    counters: Dict[str, int]
    scalars: Dict[str, float]
    trace: Optional[np.ndarray] = None
    runtime_s: float = 0.0
    mode: str = "sec"
    warm_bars: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        from ..analysis.metrics import summarize
        return summarize(self)


_COUNTER_NAMES = {
    K.K_POLLS: "polls", K.K_LIVE: "polls_live", K.K_FLAT_LIVE: "polls_flat",
    K.K_ENTRIES: "entries", K.K_ADDS: "ladder_adds",
    K.K_CLOSE_TARGET: "closes_target", K.K_CLOSE_BOOK: "closes_book", K.K_CLOSE_FORCE: "closes_force",
    K.K_CLOSE_STOPOUT: "closes_stop_out", K.K_CLOSE_SL: "closes_stop_loss",
    K.K_BLOCK_COOLDOWN: "polls_entry_blocked_cooldown", K.K_BLOCK_BRAKE: "polls_entry_blocked_window",
    K.K_BLOCK_CHOP: "polls_entry_blocked_chop", K.K_LADDER_GATED: "polls_ladder_blocked_gate",
    K.K_MARGIN_REJECT: "margin_rejects", K.K_FILL_OVERFLOW: "fill_overflow",
    K.K_BASKET_OVERFLOW: "basket_overflow", K.K_LADDER_EXHAUSTED: "polls_ladder_exhausted",
    K.K_DEAD_SKIPS: "dead_market_skips", K.K_TRACE_OVERFLOW: "trace_overflow",
    K.K_BLOCK_CONFIRM: "polls_entry_blocked_confirm", K.K_BLOCK_HOURS: "polls_entry_blocked_hours",
    K.K_CLOSE_TIME: "closes_time_stop", K.K_LADDER_SPACED: "polls_ladder_blocked_spacing",
    K.K_CLOSE_HOLE: "closes_data_hole", K.K_BLOCK_HOLE: "polls_entry_blocked_data_hole",
    K.K_BLOCK_CLOSED: "orders_refused_market_closed",
    K.K_BLOCK_REOPEN: "polls_order_blocked_close_only",
    K.K_BLOCK_TREND: "polls_entry_blocked_trend", K.K_BLOCK_SPREAD: "polls_entry_blocked_spread",
}
_SCALAR_NAMES = {
    K.S_FINAL_BALANCE: "final_balance", K.S_FINAL_EQUITY: "final_equity",
    K.S_MAX_EQUITY: "max_equity", K.S_MIN_EQUITY: "min_equity",
    K.S_MAX_DD_ABS: "max_drawdown_usd", K.S_MAX_DD_PCT: "max_drawdown_pct",
    K.S_MAX_LOTS: "max_lots", K.S_MAX_NPOS: "max_positions",
    K.S_MIN_MARGIN_LEVEL: "min_margin_level_pct", K.S_OPEN_PROFIT_END: "open_profit_at_end",
    K.S_MAX_MARGIN: "max_margin_used", K.S_BLOWN: "stopped_out", K.S_LAST_T: "last_poll_ms",
    K.S_MAX_FLOAT_LOSS: "max_floating_loss", K.S_OPEN_NPOS_END: "open_positions_at_end",
    K.S_OPEN_MAE_END: "open_mae_at_end", K.S_OPEN_UNITS_END: "open_units_at_end",
    K.S_OPEN_LOTS_END: "open_lots_at_end",
}


def _kernel_inputs(cfg: BacktestConfig, prep: Prepared):
    tfs = prep.tfs
    idx = {tf: i for i, tf in enumerate(tfs)}
    missing = [tf for tf in cfg.timeframes() if tf not in idx]
    if missing:
        raise ValueError(f"timeframes {missing} not in the prepared set {tfs}")
    n_tf = len(tfs)
    w = {k: np.zeros(n_tf) for k in ("or", "om", "fr", "fm", "br", "bm")}
    need_slope = np.zeros(n_tf, np.uint8)
    need_rsi = np.zeros(n_tf, np.uint8)
    for tf, (r, m) in cfg.open_weights.items():
        w["or"][idx[tf]], w["om"][idx[tf]] = r, m
        need_slope[idx[tf]] = 1
    for tf, (r, m) in cfg.fc_weights.items():
        w["fr"][idx[tf]], w["fm"][idx[tf]] = r, m
        need_slope[idx[tf]] = 1
    if cfg.book_enabled:
        for tf, (r, m) in cfg.book_weights.items():
            w["br"][idx[tf]], w["bm"][idx[tf]] = r, m
            need_slope[idx[tf]] = 1
    n_tiers = cfg.n_ladder_adds
    ladder_tf = np.zeros(max(n_tiers, 1), np.int64)
    for q in range(n_tiers):
        ladder_tf[q] = idx[cfg.ladder_tfs[q]]
        need_rsi[idx[cfg.ladder_tfs[q]]] = 1
    mult = np.asarray(list(cfg.ladder_multipliers) + [cfg.ladder_multipliers[-1]] * 64, dtype=np.float64)[:64]
    hour_ok = np.ones(24, np.uint8)
    if cfg.entry_hours_utc is not None:
        hour_ok[:] = 0
        for h in cfg.entry_hours_utc:
            hour_ok[int(h) % 24] = 1

    ci = np.zeros(K.CI_N, np.int64)
    ci[K.CI_START_MS] = max(store.to_ms(cfg.start), prep.start_ms)
    ci[K.CI_END_MS] = min(store.to_ms(cfg.end), prep.end_ms)
    ci[K.CI_AFTER_MS] = prep.after_ms if prep.after_ms >= 0 else prep.end_ms
    ci[K.CI_POLL_MS] = int(cfg.poll_interval_ms)
    ci[K.CI_LATENCY_MS] = int(cfg.latency_ms)
    ci[K.CI_OPEN_DELAY_MS] = int(cfg.open_order_delay_ms)
    ci[K.CI_ADD_DELAY_MS] = int(cfg.add_order_delay_ms)
    ci[K.CI_COOLDOWN_MS] = int(round(cfg.reentry_cooldown_s * 1000))
    ci[K.CI_LOSS_COOLDOWN_MS] = int(round(cfg.loss_cooldown_s * 1000))
    ci[K.CI_TREND_TF] = idx[cfg.trend_tf] if cfg.trend_tf else -1
    ci[K.CI_TREND_MODE] = 1 if cfg.trend_mode >= 0 else -1
    ci[K.CI_LIVENESS_MS] = int(round(cfg.market_lookback_s * 1000))
    ci[K.CI_UNIT_MAX] = int(cfg.unit_max_limit)
    ci[K.CI_FIXED_UNITS] = int(cfg.fixed_units)
    ci[K.CI_LOOKBACK] = int(cfg.peak_lookback)
    ci[K.CI_WIDTH] = int(cfg.pivot_width)
    ci[K.CI_WINDOW_ENABLED] = int(cfg.window_enabled)
    ci[K.CI_WIN_START] = int(cfg.window_start_min)
    ci[K.CI_WIN_END] = int(cfg.window_end_min)
    ci[K.CI_BRAKE] = int(cfg.brake)
    ci[K.CI_BOOK_ENABLED] = int(cfg.book_enabled)
    ci[K.CI_GREY_OPEN] = int(cfg.open_grey_fill)
    ci[K.CI_GREY_BOOK] = int(cfg.book_grey_fill)
    ci[K.CI_GREY_FC] = int(cfg.fc_grey_fill)
    ci[K.CI_SLOPE_CLOSED] = int(cfg.slope_on_closed_bars)
    ci[K.CI_LADDER_CLOSED] = int(cfg.ladder_on_closed_bars)
    ci[K.CI_ALLOW_LONG] = int(cfg.allow_long)
    ci[K.CI_ALLOW_SHORT] = int(cfg.allow_short)
    ci[K.CI_MIN_HOLD_MS] = int(round(cfg.min_hold_s * 1000))
    ci[K.CI_FC_CONFIRM_MS] = int(round(cfg.fc_confirm_s * 1000))
    ci[K.CI_ENTRY_CONFIRM_MS] = int(round(cfg.entry_confirm_s * 1000))
    ci[K.CI_N_TIERS] = int(n_tiers)
    ci[K.CI_REC_MS] = int(cfg.record_interval_s * 1000)
    ci[K.CI_FC_ENABLED] = int(cfg.force_close_enabled)
    ci[K.CI_TARGET_ON] = int(cfg.target_usd_per_unit is not None)
    ci[K.CI_SL_ON] = int(cfg.stop_loss_usd_per_unit is not None)
    ci[K.CI_HOURS_ON] = int(cfg.entry_hours_utc is not None)
    ci[K.CI_LADDER_INTERVAL_MS] = int(round(cfg.ladder_min_interval_s * 1000))
    ci[K.CI_MAX_HOLD_MS] = int(round(cfg.max_hold_s * 1000))
    ci[K.CI_TARGET_PER_LOT] = int(cfg.target_per_lot)
    ci[K.CI_REOPEN_DAILY_MS] = int(round(cfg.close_only_after_break_s * 1000))
    ci[K.CI_REOPEN_WEEKLY_MS] = int(round(cfg.close_only_after_weekend_s * 1000))
    ci[K.CI_JITTER_MS] = int(cfg.poll_jitter_ms)
    ci[K.CI_JITTER_SEED] = int(cfg.poll_jitter_seed)
    hole_ms = int(round(cfg.effective_data_hole_s * 1000))
    ci[K.CI_HOLE_MS] = hole_ms
    ci[K.CI_HOLE_QUARANTINE_MS] = int(round(cfg.effective_data_hole_quarantine_s * 1000))
    ci[K.CI_HOLE_UNTIL0] = -(1 << 60)
    ci[K.CI_REOPEN_UNTIL0] = -(1 << 60)
    # What a run inherits from the silences that were over by the first quote it can see (a run that
    # starts inside a silence sees its first quote when the silence ends, after its own start).
    first_seen = max(int(ci[K.CI_START_MS]), int(prep.t_ms[0])) if len(prep.t_ms) else int(ci[K.CI_START_MS])
    past = prep.gaps[prep.gaps[:, 1] <= first_seen] if len(prep.gaps) else prep.gaps
    if len(past):
        length = past[:, 1] - past[:, 0]
        if hole_ms > 0 and (length >= hole_ms).any():
            # a hole in the history that ended before (or as) this run starts: its quarantine still applies
            ci[K.CI_HOLE_UNTIL0] = int(past[length >= hole_ms][:, 1].max()) + ci[K.CI_HOLE_QUARANTINE_MS]
        # the latest session break: the broker's close-only window after it may still be running
        last = past[-1]
        if last[1] - last[0] >= 86_400_000:
            ci[K.CI_REOPEN_UNTIL0] = int(last[1]) + ci[K.CI_REOPEN_WEEKLY_MS]
        elif last[1] - last[0] >= K.SESSION_BREAK_MS:
            ci[K.CI_REOPEN_UNTIL0] = int(last[1]) + ci[K.CI_REOPEN_DAILY_MS]
    ci[K.CI_RSI_LEN] = int(cfg.rsi_length)
    ci[K.CI_MACD_FAST] = int(cfg.macd_fast)
    ci[K.CI_MACD_SLOW] = int(cfg.macd_slow)
    ci[K.CI_MACD_SIGNAL] = int(cfg.macd_signal)

    cf = np.zeros(K.CF_N, np.float64)
    cf[K.CF_BALANCE] = cfg.initial_balance
    cf[K.CF_LEVERAGE] = cfg.effective_leverage
    cf[K.CF_CONTRACT] = cfg.spec.contract_size
    cf[K.CF_MTQTY] = cfg.mtqty
    cf[K.CF_STEP_UP] = cfg.step_up_balance
    cf[K.CF_ENTRY_S] = cfg.entry_s
    cf[K.CF_ENTRY_AGREE_S] = cfg.entry_agree_s
    cf[K.CF_LADDER_S] = cfg.ladder_s
    cf[K.CF_FORCE_CLOSE_S] = cfg.force_close_s
    cf[K.CF_BOOK_S] = cfg.book_s
    cf[K.CF_TARGET] = cfg.target_usd_per_unit if cfg.target_usd_per_unit is not None else 0.0
    cf[K.CF_PROTECT] = cfg.profit_protect_usd_per_unit
    cf[K.CF_RSI_OS] = cfg.rsi_oversold
    cf[K.CF_RSI_OB] = cfg.rsi_overbought
    cf[K.CF_SPREAD_MULT] = cfg.spread_mult
    cf[K.CF_EXTRA_SPREAD] = cfg.extra_spread
    cf[K.CF_SLIPPAGE] = cfg.slippage
    cf[K.CF_COMMISSION] = cfg.commission_per_lot
    cf[K.CF_STOP_OUT] = cfg.stop_out_level
    cf[K.CF_SL] = cfg.stop_loss_usd_per_unit if cfg.stop_loss_usd_per_unit is not None else 0.0
    cf[K.CF_LADDER_GAP] = cfg.ladder_min_gap
    cf[K.CF_MAX_SPREAD] = cfg.entry_max_spread
    cf[K.CF_RSI_ALPHA] = 1.0 / cfg.rsi_length
    cf[K.CF_MACD_AF] = 2.0 / (cfg.macd_fast + 1.0)
    cf[K.CF_MACD_AS] = 2.0 / (cfg.macd_slow + 1.0)
    cf[K.CF_MACD_ASG] = 2.0 / (cfg.macd_signal + 1.0)
    return w, need_rsi, need_slope, ladder_tf, mult, hour_ok, ci, cf


def run(cfg: BacktestConfig, prep: Optional[Prepared] = None, mode: str = "sec",
        trace: bool = False, light: bool = False, max_fills: int = 200_000,
        store_dir: Path = store.DEFAULT_STORE_DIR, warn_off_grid: bool = True) -> Result:
    """
    Run one backtest.

    mode   'sec' = poll the last tick of each second (exact for a 1 s poll on whole
           seconds); 'ticks' = every tick (needed for sub-second poll phase / latency).
    trace  record every live poll's signal + scores (parity testing; small windows only).
    light  skip the per-minute equity series and the DataFrames' extras (sweeps).
    """
    t0 = time.time()
    if prep is None:
        prep = prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode=mode, store_dir=store_dir)
    flat = prep.flat(cfg)
    w, need_rsi, need_slope, ladder_tf, mult, hour_ok, ci, cf = _kernel_inputs(cfg, prep)
    if prep.mode == "sec" and warn_off_grid:
        # The per-second series holds what a poll on a whole second can see. A timing value that is not a
        # whole number of seconds moves polls or fills off that grid, where the quote in force is usually
        # not in the series: the setting would then be applied only partly, without any sign of it.
        off = [name for name, v in (("start", ci[K.CI_START_MS]), ("poll_interval_ms", ci[K.CI_POLL_MS]),
                                    ("open_order_delay_ms", ci[K.CI_OPEN_DELAY_MS]),
                                    ("add_order_delay_ms", ci[K.CI_ADD_DELAY_MS]),
                                    ("latency_ms", ci[K.CI_LATENCY_MS]))
               if int(v) % 1000]
        if int(ci[K.CI_JITTER_MS]) > 0:
            off.append("poll_jitter_ms")          # any jitter moves polls off the whole second
        if off:
            warnings.warn(f"{', '.join(off)} not a whole number of seconds: the per-second series cannot represent "
                          f"that, use mode='ticks'", RuntimeWarning, stacklevel=2)
    span_ms = int(ci[K.CI_END_MS] - ci[K.CI_START_MS])
    n_eq = 2 if (light or cfg.record_interval_s <= 0) else span_ms // (cfg.record_interval_s * 1000) + 16
    if light:
        ci[K.CI_REC_MS] = 0
    n_trace = span_ms // max(int(cfg.poll_interval_ms), 1) + 16 if trace else 0

    while True:
        fills = np.zeros((max_fills, K.F_N))
        baskets = np.zeros((max(max_fills // 2, 16), K.B_N))
        eq = np.zeros((max(n_eq, 1), K.E_N))
        tr = np.zeros((n_trace, K.T_N))
        counters = np.zeros(K.K_N, np.int64)
        scal = np.zeros(K.S_N)
        K.run_kernel(prep.t_ms, prep.bid, prep.ask,
                     flat["off"], flat["nb"], flat["nwarm"], flat["START_ROW"],
                     flat["C"], flat["AG"], flat["AL"], flat["RSI"],
                     flat["EF"], flat["ES"], flat["SG"], flat["HIST"],
                     flat["R_PH"], flat["R_PL"], flat["R_CH"], flat["R_CL"],
                     flat["M_PH"], flat["M_PL"], flat["M_CH"], flat["M_CL"],
                     need_rsi, need_slope,
                     w["or"], w["om"], w["fr"], w["fm"], w["br"], w["bm"],
                     ladder_tf, mult, hour_ok, ci, cf,
                     fills, baskets, eq, tr, counters, scal)
        if counters[K.K_FILL_OVERFLOW] == 0 and counters[K.K_BASKET_OVERFLOW] == 0:
            break
        max_fills *= 4   # never silently truncate the trade log

    nf, nbk = int(scal[K.S_N_FILLS]), int(scal[K.S_N_BASKETS])
    ne, nt = int(scal[K.S_N_EQ]), int(scal[K.S_N_TRACE])
    res = Result(
        cfg=cfg,
        fills=_fills_frame(fills[:nf], prep.tfs),
        baskets=_baskets_frame(baskets[:nbk]),
        equity=_equity_frame(eq[:ne]),
        counters={name: int(counters[i]) for i, name in _COUNTER_NAMES.items()},
        scalars={name: float(scal[i]) for i, name in _SCALAR_NAMES.items()},
        trace=tr[:nt].copy() if trace else None,
        runtime_s=time.time() - t0,
        mode=prep.mode,
        warm_bars=dict(prep.nwarm),
    )
    res.scalars["initial_balance"] = float(cfg.initial_balance)
    res.scalars["rows"] = float(prep.n_rows)
    if res.scalars["stopped_out"] and len(res.equity):
        # the kernel stops before it takes another sample: close the series with the account as the stop-out left it
        last = res.equity.iloc[-1].copy()
        last["time"] = _ts(np.array([res.scalars["last_poll_ms"]]))[0]
        last["balance"] = last["equity"] = res.scalars["final_balance"]
        last["lots"], last["n_pos"] = 0.0, 0
        res.equity = pd.concat([res.equity, last.to_frame().T], ignore_index=True).astype(res.equity.dtypes.to_dict())
    return res


def _ts(ms: np.ndarray) -> pd.DatetimeIndex:
    # nanoseconds on every pandas version (pandas 3 no longer converts to them by default)
    return pd.to_datetime(ms.astype(np.int64), unit="ms", utc=True).as_unit("ns")


def _fills_frame(a: np.ndarray, tfs: List[str]) -> pd.DataFrame:
    if len(a) == 0:
        return pd.DataFrame(columns=["time", "fill_time", "action", "side", "lots", "price", "profit",
                                     "balance", "basket", "reason", "units", "open_score", "fc_score",
                                     "book_score", "n_pos", "bid", "ask", "tier", "basket_profit",
                                     "pos_open_time", "pos_open_price"])
    tier = a[:, K.F_TIER].astype(int)
    return pd.DataFrame({
        "time": _ts(a[:, K.F_T]),
        "fill_time": _ts(a[:, K.F_FILL_T]),
        "action": [ACTION_NAMES[int(x)] for x in a[:, K.F_ACTION]],
        "side": np.where(a[:, K.F_SIDE] > 0, "BUY", "SELL"),
        "lots": a[:, K.F_LOTS],
        "price": a[:, K.F_PRICE],
        "profit": a[:, K.F_PROFIT],
        "balance": a[:, K.F_BALANCE],
        "basket": a[:, K.F_BASKET].astype(int),
        "reason": [REASON_NAMES[int(x)] for x in a[:, K.F_REASON]],
        "units": a[:, K.F_UNITS].astype(int),
        "open_score": a[:, K.F_OPEN_SCORE],
        "fc_score": a[:, K.F_FC_SCORE],
        "book_score": a[:, K.F_BOOK_SCORE],
        "n_pos": a[:, K.F_NPOS].astype(int),
        "bid": a[:, K.F_BID],
        "ask": a[:, K.F_ASK],
        "tier": [tfs[i] if i >= 0 else "" for i in tier],
        "basket_profit": a[:, K.F_BASKET_PROFIT],
        "pos_open_time": _ts(a[:, K.F_POS_OPEN_T]),
        "pos_open_price": a[:, K.F_POS_OPEN_PRICE],
    })


def _baskets_frame(a: np.ndarray) -> pd.DataFrame:
    if len(a) == 0:
        return pd.DataFrame(columns=["basket", "side", "open_time", "close_time", "duration_s", "n_pos",
                                     "lots", "pnl", "reason", "units", "mae", "mfe", "first_price",
                                     "avg_price", "close_price", "open_score", "fc_score", "commission",
                                     "balance", "profit_seen"])
    return pd.DataFrame({
        "basket": a[:, K.B_ID].astype(int),
        "side": np.where(a[:, K.B_SIDE] > 0, "BUY", "SELL"),
        "open_time": _ts(a[:, K.B_OPEN_T]),
        "close_time": _ts(a[:, K.B_CLOSE_T]),
        "duration_s": (a[:, K.B_CLOSE_T] - a[:, K.B_OPEN_T]) / 1000.0,
        "n_pos": a[:, K.B_NPOS].astype(int),
        "lots": a[:, K.B_LOTS],
        "pnl": a[:, K.B_PNL],
        "reason": [REASON_NAMES[int(x)] for x in a[:, K.B_REASON]],
        "units": a[:, K.B_UNITS].astype(int),
        "mae": a[:, K.B_MAE],
        "mfe": a[:, K.B_MFE],
        "first_price": a[:, K.B_FIRST_PRICE],
        "avg_price": a[:, K.B_AVG_PRICE],
        "close_price": a[:, K.B_CLOSE_PRICE],
        "open_score": a[:, K.B_OPEN_SCORE],
        "fc_score": a[:, K.B_FC_SCORE],
        "commission": a[:, K.B_COMMISSION],
        "balance": a[:, K.B_BALANCE],
        "profit_seen": a[:, K.B_PROFIT_SEEN],
    })


def _equity_frame(a: np.ndarray) -> pd.DataFrame:
    if len(a) == 0:
        return pd.DataFrame(columns=["time", "balance", "equity", "lots", "n_pos", "open_score",
                                     "fc_score", "book_score", "units", "bid", "ask"])
    return pd.DataFrame({
        "time": _ts(a[:, K.E_T]),
        "balance": a[:, K.E_BALANCE],
        "equity": a[:, K.E_EQUITY],
        "lots": a[:, K.E_LOTS],
        "n_pos": a[:, K.E_NPOS].astype(int),
        "open_score": a[:, K.E_OPEN_SCORE],
        "fc_score": a[:, K.E_FC_SCORE],
        "book_score": a[:, K.E_BOOK_SCORE],
        "units": a[:, K.E_UNITS].astype(int),
        "bid": a[:, K.E_BID],
        "ask": a[:, K.E_ASK],
    })
