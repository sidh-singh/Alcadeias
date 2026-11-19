"""
Ladder study: the fast engine with the study's new paths (``ladder_kernels.run_kernel2``).

* ``LadderConfig`` -- ``BacktestConfig`` plus the new fields, every one off at its default. ``replace`` and
  ``from_dict`` keep the new fields (the base ``replace`` would rebuild a plain ``BacktestConfig`` and drop them).
* ``prepare`` -- ``fast.prepare`` for every timeframe on the epoch grid, plus W1 (Sunday-anchored) built here.
* ``kernel_inputs`` -- ``fast._kernel_inputs`` unchanged, extended by the new slots and inputs.
* ``run`` -- ``fast.run`` with the copied kernel; ``raw=True`` also returns the raw output arrays.

With every new field at its default the results equal ``fast.run`` bit for bit (``ladder_checks.identity``).
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import ladder_tfs as LT          # registers M4, M6, M12, M20, H3, W1 (import before any config is built)
from . import ladder_ind as LI
from . import ladder_kernels as LK
from ..config import BacktestConfig, TF_SECONDS
from ..data import store
from ..engine import fast
from ..engine import kernels as K

TRIGGERS_X = ("macd_hist", "macd_cross", "rsi_macd", "series")
SIZINGS = ("live", "prefund", "voltarget")
HEDGES = ("depth", "counter")
PARTIALS = ("lifo", "overlap")

REASON_NAMES = {**fast.REASON_NAMES, LK.R_WEEKEND: "weekend_flat", LK.R_FINAL: "final_close",
                LK.R_HEDGE_STOP: "hedge_stop", LK.R_PARTIAL: "partial", LK.R_UNWIND: "hedge_unwind",
                LK.R_OVERLAP: "overlap"}
ACTION_NAMES = {**fast.ACTION_NAMES, LK.ACT_HEDGE: "hedge"}
COUNTER_NAMES = {**fast._COUNTER_NAMES,
                 LK.K2_REV_OPEN: "reverse_opens", LK.K2_REV_DROP: "reverse_dropped",
                 LK.K2_HEDGE_OPEN: "hedge_opens", LK.K2_HEDGE_UNWIND: "hedge_unwinds", LK.K2_PARTIAL: "partial_closes",
                 LK.K2_CLOSE_FINAL: "closes_final", LK.K2_CLOSE_WEEKEND: "closes_weekend_flat",
                 LK.K2_CLOSE_HEDGE_STOP: "closes_hedge_stop", LK.K2_BLOCK_FLAT: "polls_entry_blocked_flat_week",
                 LK.K2_BLOCK_ESER: "polls_entry_blocked_gate", LK.K2_BLOCK_SIDE_RSI: "polls_entry_blocked_side_rsi",
                 LK.K2_ADD_BLOCK_TREND: "polls_add_blocked_trend", LK.K2_ADD_BLOCK_SER: "polls_add_blocked_gate",
                 LK.K2_ADD_BLOCK_ABN: "polls_add_blocked_abnormal_day", LK.K2_ADD_BLOCK_HOURS: "polls_add_blocked_hours",
                 LK.K2_CLOSE_OVERLAP: "closes_overlap"}


@dataclass
class LadderConfig(BacktestConfig):
    # ── ladder trigger (None = ladder_trigger of the base config) ──
    ladder_trigger_x: Optional[str] = None       # 'macd_hist' | 'macd_cross' | 'rsi_macd' | 'series'
    trigger_spec: Optional[dict] = None          # 'series': a ladder_ind trigger spec, read on each tier's timeframe
    tier_os: Optional[List[float]] = None        # per-tier RSI levels (tier q uses element q; the last repeats)
    tier_ob: Optional[List[float]] = None
    # ── spacing ──
    gap_growth: float = 1.0                      # add n needs gap x growth^(n-1)
    gap_vol_tf: Optional[str] = None             # the gap in units of this timeframe's volatility (gap_vol_len bars)
    gap_vol_len: int = 14
    gap_vol_mult: float = 0.0
    # ── exits ──
    stop_pct_balance: float = 0.0                # basket stop at this % of the balance when it opened
    max_hold_min_adds: int = 0                   # max_hold_s applies only from this many adds on
    be_after_adds: int = 0                       # from this many adds: target = be_spreads x spread x lots
    be_spreads: float = 1.0
    target_shrink: bool = False                  # target = max(spread x lots, target x unit / positions)
    final_close_tf: Optional[str] = None         # ladder full and this RSI at the level against: close
    # ── add gates ──
    add_trend_tf: Optional[str] = None           # adds only with (+1) / against (-1) this MACD-signal trend
    add_trend_mode: int = 1
    add_gate: Optional[List[dict]] = None        # closed-bar mask gates for adds (ladder_ind specs, AND-ed)
    add_block_utc: Optional[List[int]] = None    # [from, to) minutes of the UTC day without adds
    abnormal_day: Optional[dict] = None          # {"mult": 2.0, "days": 20}: no adds against today's abnormal move
    # ── entries ──
    flat_week: Optional[List[int]] = None        # [from, to) minutes of the week (Mon 00:00 = 0): flat, no new basket
    entry_gate: Optional[List[dict]] = None      # closed-bar mask gates for new baskets (AND-ed)
    side_rsi_tf: Optional[str] = None            # this RSI >= side_rsi_hi: sells only; <= side_rsi_lo: buys only
    side_rsi_hi: float = 70.0
    side_rsi_lo: float = 30.0
    # ── side switching ──
    reverse: bool = False                        # stop-and-reverse after a stop or force-close (once)
    reverse_mult: float = 1.0
    hedge_mode: Optional[str] = None             # 'depth' (hedge-on-depth) | 'counter' (counter-ladder)
    hedge_stop_mult: float = 2.0
    partial: Optional[str] = None                # 'lifo' | 'overlap'
    # ── sizing ──
    sizing: str = "live"                         # 'live' (the bot's unit rule) | 'prefund' | 'voltarget'
    pf_risk: float = 0.30
    pf_atr_mult: float = 1.5
    vt_k: float = 0.0

    def __post_init__(self):
        super().__post_init__()
        tfs = [("gap_vol_tf", self.gap_vol_tf), ("final_close_tf", self.final_close_tf),
               ("add_trend_tf", self.add_trend_tf), ("side_rsi_tf", self.side_rsi_tf)]
        for name, tf in tfs:
            if tf is not None and tf not in TF_SECONDS:
                raise ValueError(f"unknown timeframe {tf!r} in {name}")
        if self.ladder_trigger_x is not None and self.ladder_trigger_x not in TRIGGERS_X:
            raise ValueError(f"unknown ladder_trigger_x {self.ladder_trigger_x!r}; known: {', '.join(TRIGGERS_X)}")
        if self.ladder_trigger_x == "series" and not self.trigger_spec:
            raise ValueError("ladder_trigger_x='series' needs trigger_spec")
        if self.sizing not in SIZINGS:
            raise ValueError(f"sizing is one of {SIZINGS}")
        if self.sizing == "voltarget" and self.vt_k <= 0:
            raise ValueError("sizing='voltarget' needs vt_k > 0")
        if self.hedge_mode is not None and self.hedge_mode not in HEDGES:
            raise ValueError(f"hedge_mode is one of {HEDGES} or None")
        if self.partial is not None and self.partial not in PARTIALS:
            raise ValueError(f"partial is one of {PARTIALS} or None")
        if self.add_trend_mode not in (1, -1):
            raise ValueError("add_trend_mode is +1 or -1")
        if self.gap_growth <= 0 or self.gap_vol_len < 2 or self.gap_vol_mult < 0 or self.stop_pct_balance < 0:
            raise ValueError("gap_growth > 0, gap_vol_len >= 2, gap_vol_mult >= 0, stop_pct_balance >= 0")
        if (self.gap_vol_mult > 0) != (self.gap_vol_tf is not None):
            raise ValueError("gap_vol_mult and gap_vol_tf go together")
        for name in ("add_block_utc", "flat_week"):
            v = getattr(self, name)
            if v is not None and len(v) != 2:
                raise ValueError(f"{name} is [from, to)")

    def timeframes(self) -> List[str]:
        used = set(super().timeframes())
        used |= {tf for tf in (self.gap_vol_tf, self.final_close_tf, self.add_trend_tf, self.side_rsi_tf) if tf}
        return sorted(used, key=TF_SECONDS.get)

    def replace(self, **kw) -> "LadderConfig":
        unknown = sorted(set(kw) - {f.name for f in fields(self)})
        if unknown:
            raise TypeError(f"unknown LadderConfig field(s): {', '.join(unknown)}")
        d = self.to_dict()
        d.update(kw)
        return type(self).from_dict(d)


def live_config(symbol: str, **kw) -> LadderConfig:
    """The live v3.9.2 configuration of this branch (``BacktestConfig.live``) as a LadderConfig."""
    return LadderConfig.live(symbol, **kw)


# ───────────────────────────── data ─────────────────────────────

def prepare(symbol: str, start, end, tfs: Sequence[str], mode: str = "sec", warm_bars: int = fast.DEFAULT_WARM_BARS,
            store_dir: Path = store.DEFAULT_STORE_DIR) -> fast.Prepared:
    """``fast.prepare`` for the epoch-grid timeframes; W1 (Sunday 00:00 grid) is added here the same way."""
    tfs = sorted(set(tfs), key=TF_SECONDS.get)
    base = [tf for tf in tfs if tf not in LT.OFFSET_TFS] or ["M1"]
    prep = fast.prepare(symbol, start, end, base, mode=mode, warm_bars=warm_bars, store_dir=store_dir)
    for tf in tfs:
        if tf in LT.OFFSET_TFS:
            _add_offset_tf(prep, tf, warm_bars)
    return prep


def _add_offset_tf(prep: fast.Prepared, tf: str, warm_bars: int) -> None:
    ids, first, c = LT.window_bars(prep.t_ms, prep.bid, tf)
    m1 = LI.m1_history(prep.symbol)
    before = m1["t"] * 1000 < prep.start_ms
    wb = LT.resample_ohlc({k: v[before] for k, v in m1.items()}, tf)
    w_ids = LT.bar_id(wb["t"], tf)
    keep = w_ids < ids[0]                        # a bar straddling the start belongs to the window
    w_ids, w_c = w_ids[keep][-warm_bars:], wb["c"][keep][-warm_bars:]
    prep.closes[tf] = np.concatenate([w_c, c]).astype(np.float64)
    prep.bar_t[tf] = LT.bar_open_s(np.concatenate([w_ids, ids]), tf).astype(np.int64)
    prep.nwarm[tf] = int(len(w_c))
    prep.start_row[tf] = np.concatenate([np.full(len(w_c), -1, np.int64), first])
    prep.tfs = sorted(set(prep.tfs) | {tf}, key=TF_SECONDS.get)
    prep._cache.clear()


def _vol2(prep: fast.Prepared, n: int) -> np.ndarray:
    key = ("VOL2", int(n), tuple(prep.tfs))
    if key not in prep._cache:
        prep._cache[key] = np.ascontiguousarray(np.concatenate(
            [K.vol_array(np.ascontiguousarray(prep.closes[tf], np.float64), int(n)) for tf in prep.tfs]))
    return prep._cache[key]


# ───────────────────────────── kernel inputs ─────────────────────────────

def _series(cfg: LadderConfig, n_tiers: int, start_ms: int, end_ms: int):
    sym = cfg.symbol
    slots: List[LI.Series] = [(np.zeros(0, np.int64), np.zeros(0))] * LK.SER_TRIG0
    if cfg.entry_gate:
        slots[LK.SER_ENTRY] = LI.combine_and([LI.gate_series(sym, g) for g in cfg.entry_gate])
    if cfg.add_gate:
        slots[LK.SER_ADD] = LI.combine_and([LI.gate_series(sym, g) for g in cfg.add_gate])
    if cfg.sizing != "live":
        slots[LK.SER_ATR] = LI.atr_series(sym, "D1", 14)
    if cfg.abnormal_day:
        ref, thr = LI.abnormal_series(sym, float(cfg.abnormal_day.get("mult", 2.0)), int(cfg.abnormal_day.get("days", 20)))
        slots[LK.SER_ABN_REF], slots[LK.SER_ABN_THR] = ref, thr
    tier_ser = np.full(64, -1, np.int64)
    if cfg.ladder_trigger_x == "series":
        trig_tfs: List[str] = []
        for q in range(n_tiers):
            tf = cfg.ladder_tfs[q]
            if tf not in trig_tfs:
                trig_tfs.append(tf)
            tier_ser[q] = LK.SER_TRIG0 + trig_tfs.index(tf)
        slots = slots + [LI.trigger_series(sym, tf, cfg.trigger_spec) for tf in trig_tfs]
    slots = [LI.window(s, start_ms, end_ms) for s in slots]
    ser_off = np.zeros(len(slots) + 1, np.int64)
    ser_off[1:] = np.cumsum([len(s[0]) for s in slots])
    ser_t = np.ascontiguousarray(np.concatenate([s[0] for s in slots]).astype(np.int64)) if ser_off[-1] else np.zeros(0, np.int64)
    ser_v = np.ascontiguousarray(np.concatenate([s[1] for s in slots]).astype(np.float64)) if ser_off[-1] else np.zeros(0)
    return tier_ser, ser_t, ser_v, ser_off


def kernel_inputs(cfg: BacktestConfig, prep: fast.Prepared):
    """``fast._kernel_inputs`` (unchanged) plus the new slots and inputs of ``run_kernel2``."""
    w, need_rsi, need_slope, ladder_tf, mult, hour_ok, ci, cf = fast._kernel_inputs(cfg, prep)
    idx = {tf: i for i, tf in enumerate(prep.tfs)}
    ci2 = np.zeros(LK.CI2_N, np.int64)
    ci2[:K.CI_N] = ci
    cf2 = np.zeros(LK.CF2_N, np.float64)
    cf2[:K.CF_N] = cf
    for s in (LK.CI2_GAP_TF, LK.CI2_FINAL_TF, LK.CI2_ADD_TREND_TF, LK.CI2_ADD_BLOCK_FROM, LK.CI2_FLAT_FROM, LK.CI2_SIDE_RSI_TF):
        ci2[s] = -1
    ci2[LK.CI2_ADD_TREND_MODE] = 1
    cf2[LK.CF2_GAP_GROWTH] = 1.0
    cf2[LK.CF2_BE_SPREADS] = 1.0
    cf2[LK.CF2_SIDE_RSI_HI] = 70.0
    cf2[LK.CF2_SIDE_RSI_LO] = 30.0
    cf2[LK.CF2_REVERSE_MULT] = 1.0
    cf2[LK.CF2_HEDGE_STOP_MULT] = 2.0
    cf2[LK.CF2_PF_RISK] = 0.30
    cf2[LK.CF2_PF_ATR_MULT] = 1.5
    tier_lv = np.zeros((2, 64))
    tier_lv[0, :] = cf[K.CF_RSI_OS]
    tier_lv[1, :] = cf[K.CF_RSI_OB]
    n_tiers = int(ci[K.CI_N_TIERS])
    VOL2 = prep.flat(cfg)["VOL"]
    if not isinstance(cfg, LadderConfig):
        tier_ser = np.full(64, -1, np.int64)
        ser_t, ser_v, ser_off = np.zeros(0, np.int64), np.zeros(0), np.zeros(LK.SER_TRIG0 + 1, np.int64)
        return w, need_rsi, need_slope, ladder_tf, mult, hour_ok, tier_lv, tier_ser, ser_t, ser_v, ser_off, VOL2, ci2, cf2
    if cfg.ladder_trigger_x is not None:
        ci2[K.CI_LADDER_MODE] = 5 + TRIGGERS_X.index(cfg.ladder_trigger_x)
        if cfg.ladder_trigger_x == "rsi_macd":
            for q in range(n_tiers):
                need_slope[idx[cfg.ladder_tfs[q]]] = 1       # its MACD vote is read (its weights in the scores stay zero)
    if cfg.tier_os is not None or cfg.tier_ob is not None:
        ci2[LK.CI2_TIER_LEVELS] = 1
        for row, lv in ((0, cfg.tier_os), (1, cfg.tier_ob)):
            if lv:
                vals = list(lv) + [lv[-1]] * 64
                tier_lv[row, :] = np.asarray(vals[:64], np.float64)
    cf2[LK.CF2_GAP_GROWTH] = float(cfg.gap_growth)
    if cfg.gap_vol_tf:
        ci2[LK.CI2_GAP_TF] = idx[cfg.gap_vol_tf]
        cf2[LK.CF2_GAP_MULT] = float(cfg.gap_vol_mult)
        VOL2 = _vol2(prep, cfg.gap_vol_len)
    cf2[LK.CF2_STOP_PCT] = float(cfg.stop_pct_balance)
    ci2[LK.CI2_HOLD_MIN_ADDS] = int(cfg.max_hold_min_adds)
    ci2[LK.CI2_BE_AFTER_ADDS] = int(cfg.be_after_adds)
    cf2[LK.CF2_BE_SPREADS] = float(cfg.be_spreads)
    ci2[LK.CI2_TARGET_SHRINK] = int(bool(cfg.target_shrink))
    if cfg.final_close_tf:
        ci2[LK.CI2_FINAL_TF] = idx[cfg.final_close_tf]
        need_rsi[idx[cfg.final_close_tf]] = 1
    if cfg.add_trend_tf:
        ci2[LK.CI2_ADD_TREND_TF] = idx[cfg.add_trend_tf]
        ci2[LK.CI2_ADD_TREND_MODE] = int(cfg.add_trend_mode)
    if cfg.add_block_utc:
        ci2[LK.CI2_ADD_BLOCK_FROM], ci2[LK.CI2_ADD_BLOCK_TO] = int(cfg.add_block_utc[0]), int(cfg.add_block_utc[1])
    ci2[LK.CI2_ABN_ON] = int(bool(cfg.abnormal_day))
    if cfg.flat_week:
        ci2[LK.CI2_FLAT_FROM], ci2[LK.CI2_FLAT_TO] = int(cfg.flat_week[0]), int(cfg.flat_week[1])
    if cfg.side_rsi_tf:
        ci2[LK.CI2_SIDE_RSI_TF] = idx[cfg.side_rsi_tf]
        need_rsi[idx[cfg.side_rsi_tf]] = 1
        cf2[LK.CF2_SIDE_RSI_HI], cf2[LK.CF2_SIDE_RSI_LO] = float(cfg.side_rsi_hi), float(cfg.side_rsi_lo)
    ci2[LK.CI2_REVERSE] = int(bool(cfg.reverse))
    cf2[LK.CF2_REVERSE_MULT] = float(cfg.reverse_mult)
    ci2[LK.CI2_HEDGE_MODE] = 0 if cfg.hedge_mode is None else 1 + HEDGES.index(cfg.hedge_mode)
    cf2[LK.CF2_HEDGE_STOP_MULT] = float(cfg.hedge_stop_mult)
    ci2[LK.CI2_PARTIAL] = 0 if cfg.partial is None else 1 + PARTIALS.index(cfg.partial)
    ci2[LK.CI2_SIZING] = SIZINGS.index(cfg.sizing)
    cf2[LK.CF2_PF_RISK], cf2[LK.CF2_PF_ATR_MULT], cf2[LK.CF2_VT_K] = float(cfg.pf_risk), float(cfg.pf_atr_mult), float(cfg.vt_k)
    tier_ser, ser_t, ser_v, ser_off = _series(cfg, n_tiers, int(ci[K.CI_START_MS]), int(ci[K.CI_END_MS]))
    return w, need_rsi, need_slope, ladder_tf, mult, hour_ok, tier_lv, tier_ser, ser_t, ser_v, ser_off, VOL2, ci2, cf2


# ───────────────────────────── run ─────────────────────────────

def run(cfg: BacktestConfig, prep: Optional[fast.Prepared] = None, mode: str = "sec", trace: bool = False,
        light: bool = False, max_fills: int = 200_000, store_dir: Path = store.DEFAULT_STORE_DIR,
        warn_off_grid: bool = True, regime: Optional[Tuple[np.ndarray, np.ndarray]] = None, raw: bool = False):
    """``fast.run`` with ``run_kernel2``. ``raw=True`` returns ``(Result, arrays)`` with the kernel's raw outputs."""
    t0 = time.time()
    if regime is None:
        reg_t, reg_v = np.zeros(0, np.int64), np.zeros(0, np.int64)
    else:
        reg_t = np.ascontiguousarray(regime[0], np.int64)
        reg_v = np.ascontiguousarray(regime[1], np.int64)
    if prep is None:
        prep = prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode=mode, store_dir=store_dir)
    flat = prep.flat(cfg)
    (w, need_rsi, need_slope, ladder_tf, mult, hour_ok, tier_lv, tier_ser,
     ser_t, ser_v, ser_off, VOL2, ci, cf) = kernel_inputs(cfg, prep)
    if prep.mode == "sec" and warn_off_grid:
        off = [name for name, v in (("start", ci[K.CI_START_MS]), ("poll_interval_ms", ci[K.CI_POLL_MS]),
                                    ("open_order_delay_ms", ci[K.CI_OPEN_DELAY_MS]),
                                    ("add_order_delay_ms", ci[K.CI_ADD_DELAY_MS]), ("latency_ms", ci[K.CI_LATENCY_MS]))
               if int(v) % 1000]
        if int(ci[K.CI_JITTER_MS]) > 0:
            off.append("poll_jitter_ms")
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
        baskets = np.zeros((max(max_fills // 2, 16), LK.B_N2))
        eq = np.zeros((max(n_eq, 1), K.E_N))
        tr = np.zeros((n_trace, K.T_N))
        counters = np.zeros(LK.K2_N, np.int64)
        scal = np.zeros(K.S_N)
        LK.run_kernel2(prep.t_ms, prep.bid, prep.ask,
                       flat["off"], flat["nb"], flat["nwarm"], flat["START_ROW"],
                       flat["C"], flat["AG"], flat["AL"], flat["RSI"],
                       flat["EF"], flat["ES"], flat["SG"], flat["HIST"], flat["VOL"],
                       flat["R_PH"], flat["R_PL"], flat["R_CH"], flat["R_CL"],
                       flat["M_PH"], flat["M_PL"], flat["M_CH"], flat["M_CL"],
                       need_rsi, need_slope,
                       w["or"], w["om"], w["fr"], w["fm"], w["br"], w["bm"], w["ar"], w["am"],
                       ladder_tf, mult, hour_ok, reg_t, reg_v,
                       tier_lv, tier_ser, ser_t, ser_v, ser_off, VOL2,
                       ci, cf, fills, baskets, eq, tr, counters, scal)
        if counters[K.K_FILL_OVERFLOW] == 0 and counters[K.K_BASKET_OVERFLOW] == 0:
            break
        max_fills *= 4
    nf, nbk = int(scal[K.S_N_FILLS]), int(scal[K.S_N_BASKETS])
    ne, nt = int(scal[K.S_N_EQ]), int(scal[K.S_N_TRACE])
    res = fast.Result(
        cfg=cfg, fills=fills_frame(fills[:nf], prep.tfs), baskets=baskets_frame(baskets[:nbk]),
        equity=fast._equity_frame(eq[:ne]),
        counters={name: int(counters[i]) for i, name in COUNTER_NAMES.items()},
        scalars={name: float(scal[i]) for i, name in fast._SCALAR_NAMES.items()},
        trace=tr[:nt].copy() if trace else None, runtime_s=time.time() - t0, mode=prep.mode,
        warm_bars=dict(prep.nwarm))
    res.scalars["initial_balance"] = float(cfg.initial_balance)
    res.scalars["rows"] = float(prep.n_rows)
    if res.scalars["stopped_out"] and len(res.equity):
        last = res.equity.iloc[-1].copy()
        last["time"] = fast._ts(np.array([res.scalars["last_poll_ms"]]))[0]
        last["balance"] = last["equity"] = res.scalars["final_balance"]
        last["lots"], last["n_pos"] = 0.0, 0
        res.equity = pd.concat([res.equity, last.to_frame().T], ignore_index=True).astype(res.equity.dtypes.to_dict())
    if raw:
        return res, {"fills": fills[:nf].copy(), "baskets": baskets[:nbk].copy(), "counters": counters.copy(),
                     "scalars": scal.copy(), "trace": tr[:nt].copy()}
    return res


def fills_frame(a: np.ndarray, tfs: List[str]) -> pd.DataFrame:
    if len(a) == 0:
        return fast._fills_frame(a, tfs)
    tier = a[:, K.F_TIER].astype(int)
    return pd.DataFrame({
        "time": fast._ts(a[:, K.F_T]), "fill_time": fast._ts(a[:, K.F_FILL_T]),
        "action": [ACTION_NAMES[int(x)] for x in a[:, K.F_ACTION]],
        "side": np.where(a[:, K.F_SIDE] > 0, "BUY", "SELL"), "lots": a[:, K.F_LOTS], "price": a[:, K.F_PRICE],
        "profit": a[:, K.F_PROFIT], "balance": a[:, K.F_BALANCE], "basket": a[:, K.F_BASKET].astype(int),
        "reason": [REASON_NAMES[int(x)] for x in a[:, K.F_REASON]], "units": a[:, K.F_UNITS].astype(int),
        "open_score": a[:, K.F_OPEN_SCORE], "fc_score": a[:, K.F_FC_SCORE], "book_score": a[:, K.F_BOOK_SCORE],
        "n_pos": a[:, K.F_NPOS].astype(int), "bid": a[:, K.F_BID], "ask": a[:, K.F_ASK],
        "tier": [tfs[i] if i >= 0 else "" for i in tier], "basket_profit": a[:, K.F_BASKET_PROFIT],
        "pos_open_time": fast._ts(a[:, K.F_POS_OPEN_T]), "pos_open_price": a[:, K.F_POS_OPEN_PRICE],
    })


def baskets_frame(a: np.ndarray) -> pd.DataFrame:
    extra = ("n_opened", "max_ladder", "partial_pnl", "n_hedge", "is_reverse")
    if len(a) == 0:
        d = fast._baskets_frame(a)
        for c in extra:
            d[c] = []
        return d
    return pd.DataFrame({
        "basket": a[:, K.B_ID].astype(int), "side": np.where(a[:, K.B_SIDE] > 0, "BUY", "SELL"),
        "open_time": fast._ts(a[:, K.B_OPEN_T]), "close_time": fast._ts(a[:, K.B_CLOSE_T]),
        "duration_s": (a[:, K.B_CLOSE_T] - a[:, K.B_OPEN_T]) / 1000.0, "n_pos": a[:, K.B_NPOS].astype(int),
        "lots": a[:, K.B_LOTS], "pnl": a[:, K.B_PNL], "reason": [REASON_NAMES[int(x)] for x in a[:, K.B_REASON]],
        "units": a[:, K.B_UNITS].astype(int), "mae": a[:, K.B_MAE], "mfe": a[:, K.B_MFE],
        "first_price": a[:, K.B_FIRST_PRICE], "avg_price": a[:, K.B_AVG_PRICE], "close_price": a[:, K.B_CLOSE_PRICE],
        "open_score": a[:, K.B_OPEN_SCORE], "fc_score": a[:, K.B_FC_SCORE], "commission": a[:, K.B_COMMISSION],
        "balance": a[:, K.B_BALANCE], "profit_seen": a[:, K.B_PROFIT_SEEN],
        "n_opened": a[:, LK.B2_N_OPENED].astype(int), "max_ladder": a[:, LK.B2_MAX_LAD].astype(int),
        "partial_pnl": a[:, LK.B2_PART_PNL], "n_hedge": a[:, LK.B2_N_HEDGE].astype(int),
        "is_reverse": a[:, LK.B2_IS_REV] > 0,
    })
