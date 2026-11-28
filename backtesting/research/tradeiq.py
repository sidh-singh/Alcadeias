"""
TradeIQ's four RSI replacements on gold and BTC: the pre-registered grid on Development and Validation.

    python -B -m backtesting.research.tradeiq grid                     # the variants of PREREG 6 (no data is read)
    python -B -m backtesting.research.tradeiq run [--symbols XAUUSDm BTCUSDm] [--out DIR]
    python -B -m backtesting.research.tradeiq select [--out DIR]       # PREREG 7: selection, RSI comparison, DSR / SPA
    python -B -m backtesting.research.tradeiq freeze                   # PREREG 8: FINALISTS.md and its sha256, once
    python -B -m backtesting.research.tradeiq exam                     # PREREG 8: the finalists over the hold-out
    python -B -m backtesting.research.tradeiq holdout                  # every variant over the hold-out and 2019-end
    python -B -m backtesting.research.tradeiq curves                   # PREREG 8: the $2,000 account curves
    python -B -m backtesting.research.tradeiq bots                     # the bots' five designs, rebuilt from final10
    python -B -m backtesting.research.tradeiq claims                   # PREREG 9: CLAIMS.md

The plan is ``backtest_results/tradeiq_rsi/PREREG.md`` (frozen), read with ``DEVIATIONS.md``: section 6 (the rules)
and section 7 (the scores and the selection), with the clarifications 1-3, 6-7 (the harness) and 19-26 (this code);
section 8 (the exam and the money) and 9 (the claims) with 27-37.
The indicators are ``tradeiq_ind.py``. The data, the execution and the scores are ``tradeiq_market.py``, and through it
``external.py``. The deflated Sharpe and the SPA test are ``silver.py``'s. Existing modules are imported, never edited.

THE HOLD-OUT. Every path loads, runs and scores through ``tradeiq_market``, whose guard serves nothing at or after
2024-07-01 00:00 UTC until ``FINALISTS.md`` and its sha256 exist. ``run`` and ``select`` never reach it: ``run_variant``
runs Development, Validation and D+V only, and ``select`` writes ``CANDIDATES.md``, who WOULD be the finalists.
``freeze`` writes ``FINALISTS.md`` once (it refuses a second time, and refuses while the code differs from the code
that wrote the results). Only after it do ``exam``, ``holdout``, ``curves`` and ``claims`` compute anything inside the
hold-out (they refuse before; the guard refuses anyway). ``bots`` reads final10's published runs, not the study's data.

Outputs (``backtest_results/tradeiq_rsi/`` unless ``--out``)
-----------------------------------------------------------
``run``:
  grid.csv               the variants (id = symbol|tf|indicator|family|filter|stop)
  results_dev_val.csv    one row per variant and window (dev, val, devval = the two together as one run): every score
                         of PREREG 7 at x1.0 costs, and the same with the suffix ``_x15`` at x1.5
  trades_dev_val.csv.gz  every trade of the dev and val runs, at both costs
  quarters_dev_val.csv   P/L per calendar quarter of the dev and val runs, at both costs
  weekly_dev_val.csv.gz  P/L per week (Saturday 00:00 UTC edges) of the dev and val runs, at both costs
  buy_and_hold.csv       0.01 lot bought at the ask at each window's first M1 open, sold at the bid at its last close
  state_checks.csv       per symbol and timeframe: bars the windows read, missing values and exact ties on them
  run_info.csv           when, on what data, with which code (git blob ids)
``select``:
  qualification.csv      per variant: the four rules of PREREG 7, the rank on dev + val, the would-be finalists
  vs_rsi.csv, vs_rsi_summary.csv   each oscillator's variant against the RSI variant of the same row
  multiple_testing.csv   per symbol: the deflated Sharpe of the best variant, the SPA and Reality Check p-values
  vs_buy_and_hold.csv    each would-be finalist per window next to buy-and-hold of the same span (DEVIATIONS 28)
  exam_rule_rates.csv    per symbol and window: the rows that pass PREREG 8's rule, R2 (long only) and the others
  runners_up.csv         the best qualifier of each indicator without a slot, against the last would-be finalist
  curves.csv             the rows of PREREG 8's account curves (DEVIATIONS 29)
  vs_f0.csv, vs_f0_summary.csv     each filtered variant against the same variant without a filter (DEVIATIONS 30)
  claims.csv             the evidence for each claim of PREREG 9, per symbol and window (DEVIATIONS 31)
  CANDIDATES.md          the qualifiers and the would-be finalists, with their numbers
``freeze``: FINALISTS.md, FINALISTS.md.sha256 (the finalists, their rule rows and numbers, the code's blob ids)
``exam``:   exam.csv, exam_trades.csv, exam_buy_and_hold.csv, exam_info.csv, EXAM.md (the verdicts)
``holdout``: results_holdout.csv, results_full.csv (every variant, x1.0 and _x15), trades_holdout.csv.gz,
  buy_and_hold_exam.csv, state_checks_full.csv, holdout_info.csv, holdout_checks.csv, vs_rsi_holdout_summary.csv,
  vs_f0_holdout_summary.csv, exam_rule_rates_holdout.csv; EXAM.md again with them
``curves``: curves_full.csv, curves_holdout.csv (daily equity of the $2,000 account and per 0.01 lot), curves_summary.csv
``bots``:   curves_bots_full.csv, curves_bots_holdout.csv, bots_check.csv, the bots' rows of curves_summary.csv
``claims``: CLAIMS.md, claims_all.csv

The rules (PREREG 6, DEVIATIONS 1-2 and 19-21)
-------------------------------------------
A state per bar of the signal timeframe, +1 long, 0 flat, -1 short, decided at the bar's close and executed by
``tradeiq_market.run``. An entry happens only where the state changes (also after a stop, DEVIATIONS 1); the window's
first bar takes the state (DEVIATIONS 2).
* R1: the side of the line's middle (RSI, LaRSI, VWRSI 50; TSI 0); QQE: the colour of the last bar that was not gray.
* R2: R1 with the short state flat.
* R3: QQE's colour (GRAY flat); VWRSI: flat while the consolidation score is above 0, else the side of 50.
* R4: up through the low level long, down through the high level short, held in between (RSI 30 / 70, LaRSI and
  VWRSI 20 / 80, TSI -30 / +30).
* CTL-SIGNAL: the TSI crossing its signal line; CTL-WHITE: QQE's white line crossing 0 (held in between).
* MA200 alone: R1 the side of the close against its MA200, R2 long or flat.
* Filters on R1, R2, R3 of the five oscillators: F0 none; F1 the bar's close against its MA200; F2-4H / F2-1D the last
  CLOSED 4H / 1D bar's close against its MA200 (``tradeiq_market.htf_at``: the last higher bar whose close time is at
  or before the signal bar's close); F3 the TSI's side of 0. A state the filter does not allow is flat.
* Stops: S0 none; S1 3 x ATR(14) of the signal timeframe from the entry fill (``tradeiq_market.s1_stop``).
* "VWRSI-RV": BTC's VWRSI rows on Binance's BTCUSDT spot volume (``tradeiq_market.binance_volume``).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from . import tradeiq_ind as I
from . import tradeiq_market as TM

SYMBOLS = TM.SYMBOLS
TFS = ("1H", "4H", "1D")
OSCILLATORS = ("RSI", "LaRSI", "VWRSI", "TSI", "QQE")
RV = "VWRSI-RV"                                     # BTC's VWRSI on Binance volume (PREREG 2)
FILTERS: Dict[str, Tuple[str, ...]] = {"1H": ("F0", "F1", "F2-4H", "F2-1D", "F3"),
                                       "4H": ("F0", "F1", "F2-1D", "F3"),
                                       "1D": ("F0", "F1", "F3")}
STOPS = ("S0", "S1")
MIDDLE = {"RSI": 50.0, "LaRSI": 50.0, "VWRSI": 50.0, RV: 50.0, "TSI": 0.0}
LEVELS = {"RSI": (30.0, 70.0), "LaRSI": (20.0, 80.0), "VWRSI": (20.0, 80.0), RV: (20.0, 80.0), "TSI": (-30.0, 30.0)}
GROUP = {RV: "VWRSI"}                               # the finalist rule's indicator (DEVIATIONS 24)
MIN_TRADES = {"1H": 30, "4H": 30, "1D": 15}         # PREREG 7, rule 2
RUN_WINDOWS = ("dev", "val", "devval")
COSTS = (1.0, 1.5)
N_FINALISTS = 3
STUDY_DIR = REPO_ROOT / "backtest_results" / "tradeiq_rsi"
CODE_FILES = ("backtesting/research/tradeiq.py", "backtesting/research/tradeiq_ind.py",
              "backtesting/research/tradeiq_market.py", "backtesting/research/external.py",
              "backtesting/research/silver.py")
IDENT = ("vid", "symbol", "tf", "indicator", "family", "filter", "stop", "group")
SCORES = ("net", "trades", "win_rate", "profit_factor", "max_dd", "profit_dd", "pos_q", "n_q", "pos_q_share",
          "sharpe_w", "avg_hold_h", "time_in_mkt", "max_losing_streak", "avg_win", "avg_loss", "best_trade",
          "worst_trade", "n_long", "n_short", "long_pnl", "short_pnl", "n_stops", "slippage", "weeks", "sr_w_raw",
          "skew_w", "kurt_w", "n_q_exposed", "n_decisions")


def has_rv(symbol: str) -> bool:
    return symbol.startswith("BTC")


# ───────────────────────────── the grid (PREREG 6, DEVIATIONS 22) ─────────────────────────────

@dataclass(frozen=True)
class Variant:
    symbol: str
    tf: str
    indicator: str          # RSI, LaRSI, VWRSI, VWRSI-RV, TSI, QQE, MA200
    family: str             # R1, R2, R3, R4, CTL-SIGNAL, CTL-WHITE
    filt: str               # F0, F1, F2-4H, F2-1D, F3
    stop: str               # S0, S1

    @property
    def vid(self) -> str:
        return f"{self.symbol}|{self.tf}|{self.indicator}|{self.family}|{self.filt}|{self.stop}"

    @property
    def rule(self) -> Tuple[str, str, str, str]:
        """What decides the state series (the stop does not)."""
        return (self.tf, self.indicator, self.family, self.filt)

    @property
    def group(self) -> str:
        return GROUP.get(self.indicator, self.indicator)

    def ident(self) -> Dict[str, str]:
        return {"vid": self.vid, "symbol": self.symbol, "tf": self.tf, "indicator": self.indicator,
                "family": self.family, "filter": self.filt, "stop": self.stop, "group": self.group}

    @staticmethod
    def of(vid: str) -> "Variant":
        s, tf, ind, fam, f, st = vid.split("|")
        return Variant(s, tf, ind, fam, f, st)


def rule_rows(symbol: str, tf: str) -> List[Tuple[str, str, str]]:
    """(indicator, family, filter) of one symbol and timeframe, in the order of PREREG 6's grid sentence."""
    osc = OSCILLATORS + ((RV,) if has_rv(symbol) else ())
    rows = [(ind, fam, f) for ind in osc for fam in ("R1", "R2") for f in FILTERS[tf]]
    rows += [(ind, "R3", f) for ind in osc if ind in ("VWRSI", RV, "QQE") for f in FILTERS[tf]]
    rows += [(ind, "R4", "F0") for ind in osc if ind != "QQE"]
    rows += [("TSI", "CTL-SIGNAL", "F0"), ("QQE", "CTL-WHITE", "F0"), ("MA200", "R1", "F0"), ("MA200", "R2", "F0")]
    return rows


def grid(symbol: str) -> List[Variant]:
    """Every variant of one symbol: 336 on gold, 414 on BTC (DEVIATIONS 22)."""
    if symbol not in SYMBOLS:
        raise ValueError(f"{symbol}: not in this study")
    return [Variant(symbol, tf, ind, fam, f, s) for tf in TFS for ind, fam, f in rule_rows(symbol, tf) for s in STOPS]


def grid_frame(symbols: Sequence[str] = SYMBOLS) -> pd.DataFrame:
    return pd.DataFrame([v.ident() for s in symbols for v in grid(s)])


# ───────────────────────────── the lines and the states (DEVIATIONS 19-20) ─────────────────────────────

def lines_of(mk: TM.TMarket, tf: str) -> Dict[str, np.ndarray]:
    """Every line the rules read on ``mk.tbars(tf)``, with the scripts' defaults (``tradeiq_ind``)."""
    b = mk.tbars(tf)
    c = b.c
    vw = I.vwrsi(c, b.vol)
    ts = I.bjorgum_tsi(c)
    q = I.qqe_mod(c)
    L = {"close": c, "RSI": I.plain_rsi(c), "LaRSI": I.laguerre_rsi(c), "VWRSI": vw.rsi, "VWRSI:score": vw.score,
         "TSI": ts.tsi, "TSI:signal": ts.signal, "QQE:color": q.color, "QQE:white": q.white,
         "QQE:srsi1": q.srsi1, "QQE:srsi2": q.srsi2, "QQE:upper": q.bb_upper, "QQE:lower": q.bb_lower,
         "MA200": I.ma200(c)}
    if has_rv(mk.symbol):
        bv, miss = TM.binance_volume(mk, tf)
        vr = I.vwrsi(c, bv)
        L[RV], L[RV + ":score"], L["binance_missing"] = vr.rsi, vr.score, miss
    return L


def side(x, mid: float) -> np.ndarray:
    """+1 above ``mid``, -1 below, 0 on it or where ``x`` has no value (DEVIATIONS 19)."""
    x = np.asarray(x, np.float64)
    with np.errstate(invalid="ignore"):
        return np.where(x > mid, 1, np.where(x < mid, -1, 0)).astype(np.int8)


def hold(up, dn) -> np.ndarray:
    """The side of the last event (``up`` long, ``dn`` short), held until the opposite one; 0 before the first."""
    up, dn = np.asarray(up, bool), np.asarray(dn, bool)
    if up.shape != dn.shape:
        raise ValueError("up and dn must have one shape")
    if np.any(up & dn):
        raise ValueError("a bar with both a long and a short event")
    ev = np.where(up, 1, np.where(dn, -1, 0)).astype(np.int8)
    last = np.maximum.accumulate(np.where(ev != 0, np.arange(len(ev)), -1))
    return np.where(last >= 0, ev[np.maximum(last, 0)], 0).astype(np.int8)


def raw_state(L: Dict[str, np.ndarray], indicator: str, family: str) -> np.ndarray:
    """The state of a rule before its filter."""
    if indicator == "MA200":
        s = side(L["close"] - L["MA200"], 0.0)
        return {"R1": s, "R2": np.maximum(s, 0)}[family].astype(np.int8)
    if indicator == "QQE":
        col = np.asarray(L["QQE:color"])
        if family == "R1":
            return hold(col == I.BLUE, col == I.RED)
        if family == "R2":
            return np.maximum(hold(col == I.BLUE, col == I.RED), 0).astype(np.int8)
        if family == "R3":
            return np.where(col == I.BLUE, 1, np.where(col == I.RED, -1, 0)).astype(np.int8)
        if family == "CTL-WHITE":
            w = L["QQE:white"]
            return hold(I.crossover(w, 0.0), I.crossunder(w, 0.0))
        raise ValueError(f"QQE has no family {family}")
    if indicator == "TSI" and family == "CTL-SIGNAL":
        return hold(I.crossover(L["TSI"], L["TSI:signal"]), I.crossunder(L["TSI"], L["TSI:signal"]))
    if indicator not in MIDDLE:
        raise ValueError(f"unknown indicator {indicator}")
    x = L[indicator]
    if family in ("R1", "R2"):
        s = side(x, MIDDLE[indicator])
        return s if family == "R1" else np.maximum(s, 0).astype(np.int8)
    if family == "R3":
        if indicator not in ("VWRSI", RV):
            raise ValueError(f"{indicator} has no R3")
        score = L[indicator + ":score"]
        with np.errstate(invalid="ignore"):
            trending = np.isfinite(score) & (score <= 0.0)          # the score is >= 0: "not above 0" is 0
        return np.where(trending, side(x, 50.0), 0).astype(np.int8)
    if family == "R4":
        lo, hi = LEVELS[indicator]
        return hold(I.crossover(x, lo), I.crossunder(x, hi))
    raise ValueError(f"{indicator} has no family {family}")


def allowed_of(L: Dict[str, np.ndarray], filt: str, f2: Optional[Tuple[np.ndarray, np.ndarray]] = None
               ) -> Tuple[np.ndarray, np.ndarray]:
    """(long allowed, short allowed) per bar of a filter; ``f2`` is the F2 pair of ``htf_sides``."""
    n = len(L["close"])
    with np.errstate(invalid="ignore"):
        if filt == "F0":
            return np.ones(n, bool), np.ones(n, bool)
        if filt == "F1":
            return L["close"] > L["MA200"], L["close"] < L["MA200"]
        if filt == "F3":
            return L["TSI"] > 0.0, L["TSI"] < 0.0
    if filt in ("F2-4H", "F2-1D"):
        if f2 is None:
            raise ValueError(f"{filt} needs the higher timeframe's sides")
        return f2
    raise ValueError(f"unknown filter {filt}")


def apply_filter(raw: np.ndarray, al: np.ndarray, ash: np.ndarray) -> np.ndarray:
    """A state the filter does not allow becomes flat (PREREG 6)."""
    return np.where((raw == 1) & al, 1, np.where((raw == -1) & ash, -1, 0)).astype(np.int8)


def htf_sides(htf: TM.TBars, ltf: TM.TBars, close=None, ma=None) -> Tuple[np.ndarray, np.ndarray]:
    """
    F2: per bar of ``ltf``, whether the last ``htf`` bar CLOSED at its close (close time at or before the ltf bar's)
    closed above / below its MA200. ``close`` / ``ma`` default to the htf bars' close and its ``tradeiq_ind.ma200``.
    Before the first closed htf bar, and where the MA200 has no value, neither side is allowed.
    """
    c = htf.c if close is None else np.asarray(close, np.float64)
    m = I.ma200(c) if ma is None else np.asarray(ma, np.float64)
    with np.errstate(invalid="ignore"):
        up, dn = (c > m).astype(np.float64), (c < m).astype(np.float64)
    return TM.htf_at(htf, up, ltf, 0.0) == 1.0, TM.htf_at(htf, dn, ltf, 0.0) == 1.0


class Study:
    """One symbol's bars, lines, filters, stops and states on the three timeframes, on what the guard serves."""

    def __init__(self, mk: TM.TMarket):
        if not isinstance(mk, TM.TMarket) or mk.cost != 1.0:
            raise TypeError("Study takes the TMarket itself (tradeiq_market.load)")
        self.mk = mk
        self.symbol = mk.symbol
        self.bars = {tf: mk.tbars(tf) for tf in TFS}
        self.lines = {tf: lines_of(mk, tf) for tf in TFS}
        self.f2 = {(tf, f): htf_sides(self.bars[f[3:]], self.bars[tf])
                   for tf in TFS for f in FILTERS[tf] if f.startswith("F2-")}
        self.stops = {tf: TM.s1_stop(self.bars[tf]) for tf in TFS}
        self._states: Dict[Tuple[str, str, str, str], np.ndarray] = {}

    def state(self, v: Variant) -> np.ndarray:
        if v.symbol != self.symbol:
            raise ValueError(f"{v.vid}: not a variant of {self.symbol}")
        key = v.rule
        if key not in self._states:
            tf, ind, fam, filt = key
            L = self.lines[tf]
            raw = raw_state(L, ind, fam)
            al, ash = allowed_of(L, filt, self.f2.get((tf, filt)))
            st = apply_filter(raw, al, ash)
            st.setflags(write=False)
            self._states[key] = st
        return self._states[key]

    def checks(self, start: str = "2019-01-01") -> pd.DataFrame:
        """
        Per timeframe, on the bars the windows read (from the first bar closing after ``start``, and the bar before it,
        whose values the crosses compare with): missing values of every line a rule or a filter reads, and exact ties
        with the levels the rules read (DEVIATIONS 19). The ties are counted, not refused.
        """
        a_s = TM.s_of(start)
        rows = []
        for tf in TFS:
            b, L = self.bars[tf], self.lines[tf]
            sel = np.flatnonzero((b.tc > a_s) & (b.ex < len(self.mk)))
            ix = np.arange(max(int(sel[0]) - 1, 0), int(sel[-1]) + 1)
            names = ["RSI", "LaRSI", "VWRSI", "VWRSI:score", "TSI", "TSI:signal", "QQE:white", "QQE:srsi1",
                     "QQE:srsi2", "QQE:upper", "QQE:lower", "MA200"] + ([RV, RV + ":score"] if has_rv(self.symbol) else [])
            missing = {n: int(np.sum(~np.isfinite(np.asarray(L[n], float)[ix]))) for n in names}
            missing["S1 ATR"] = int(np.sum(~np.isfinite(self.stops[tf][ix])))
            ties = {}
            for ind in ("RSI", "LaRSI", "VWRSI", "TSI") + ((RV,) if has_rv(self.symbol) else ()):
                for lvl in (MIDDLE[ind],) + LEVELS[ind]:
                    ties[f"{ind}={lvl:g}"] = int(np.sum(L[ind][ix] == lvl))
            ties["TSI=signal"] = int(np.sum(L["TSI"][ix] == L["TSI:signal"][ix]))
            ties["white=0"] = int(np.sum(L["QQE:white"][ix] == 0.0))
            ties["QQE srsi2-50=+-3"] = int(np.sum(np.abs(L["QQE:srsi2"][ix] - 50.0) == 3.0))
            ties["QQE srsi1-50=band"] = int(np.sum((L["QQE:srsi1"][ix] - 50.0 == L["QQE:upper"][ix])
                                                   | (L["QQE:srsi1"][ix] - 50.0 == L["QQE:lower"][ix])))
            ties["close=MA200"] = int(np.sum(L["close"][ix] == L["MA200"][ix]))
            for f in FILTERS[tf]:
                if f.startswith("F2-"):
                    hb = self.bars[f[3:]]
                    k = np.searchsorted(hb.tc, b.tc[ix], side="right") - 1
                    ma = I.ma200(hb.c)
                    missing[f"{f} MA200"] = int(np.sum((k < 0) | ~np.isfinite(ma[np.maximum(k, 0)])))
                    ties[f"{f} close=MA200"] = int(np.sum(hb.c[np.maximum(k, 0)] == ma[np.maximum(k, 0)]))
            rows.append({"symbol": self.symbol, "tf": tf, "first_bar_close": str(TM.utc(b.tc[sel[0]])),
                         "last_bar_close": str(TM.utc(b.tc[sel[-1]])), "bars_read": int(len(ix)),
                         "missing_total": int(sum(missing.values())), "ties_total": int(sum(ties.values())),
                         **{f"missing {k}": v for k, v in missing.items()}, **{f"tie {k}": v for k, v in ties.items()},
                         "binance_hours_missing": int(np.sum(L["binance_missing"][ix])) if "binance_missing" in L else 0})
        return pd.DataFrame(rows)


# ───────────────────────────── running and scoring (PREREG 7, DEVIATIONS 6-7, 23) ─────────────────────────────

def run_variant(study: Study, v: Variant, window: str, cost: float = 1.0) -> TM.Run:
    """One variant over one named window (dev, val, devval) at one cost."""
    if window not in RUN_WINDOWS:
        raise ValueError(f"{window}: this module runs only {', '.join(RUN_WINDOWS)} (the hold-out is the exam's)")
    a, z = TM.window(window, v.symbol)
    stop = study.stops[v.tf] if v.stop == "S1" else None
    return TM.run(study.mk, study.bars[v.tf], study.state(v), a, z, stop=stop, cost=cost)


def scores(r: TM.Run) -> Dict[str, float]:
    """PREREG 7 for one run, per 0.01 lot after costs, unrounded (``tradeiq_market.metrics`` plus the trade stats)."""
    m = TM.metrics(r)
    pnl = r.trades.pnl.to_numpy(np.float64)
    w, lo = pnl[pnl > 0], pnl[pnl < 0]
    gw, gl = float(w.sum()), float(-lo.sum())
    return {
        "net": float(m["net_exact"]), "trades": int(len(pnl)),
        "win_rate": 100.0 * len(w) / len(pnl) if len(pnl) else np.nan,
        "profit_factor": gw / gl if gl > 0 else (np.inf if gw > 0 else np.nan),
        "max_dd": float(m["max_dd"]), "profit_dd": float(m["profit_dd"]),
        "pos_q": int(m["pos_q"]), "n_q": int(m["n_q"]), "pos_q_share": float(m["pos_q_share"]),
        "sharpe_w": float(m["sharpe_w"]), "avg_hold_h": float(m["avg_hold_h"]), "time_in_mkt": float(m["time_in_mkt"]),
        "max_losing_streak": int(m["max_losing_streak"]),
        "avg_win": float(w.mean()) if len(w) else np.nan, "avg_loss": float(lo.mean()) if len(lo) else np.nan,
        "best_trade": float(pnl.max()) if len(pnl) else np.nan, "worst_trade": float(pnl.min()) if len(pnl) else np.nan,
        "n_long": int(m["n_long"]), "n_short": int(m["n_short"]), "long_pnl": float(m["long_pnl"]),
        "short_pnl": float(m["short_pnl"]), "n_stops": int(m["n_stops"]), "slippage": float(m["slippage"]),
        "weeks": int(m["weeks"]), "sr_w_raw": float(m["sr_w_raw"]), "skew_w": float(m["skew_w"]),
        "kurt_w": float(m["kurt_w"]), "n_q_exposed": int(m["n_q_exposed"]), "n_decisions": int(r.n_decisions),
    }


def _suffix(cost: float) -> str:
    return "" if cost == 1.0 else "_x" + f"{cost:g}".replace(".", "")


def _quarter_label(t: int) -> str:
    ts = TM.utc(t)
    return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"


def run_symbol(symbol: str, log=print, variants: Optional[Sequence[Variant]] = None) -> Dict[str, pd.DataFrame]:
    """Every variant of ``symbol`` over dev, val and devval at x1.0 and x1.5 (the data the guard serves)."""
    t0 = time.time()
    mk = TM.load(symbol)
    st = Study(mk)
    checks = st.checks()
    bad = checks[checks.missing_total > 0]
    if len(bad):
        raise AssertionError(f"{symbol}: lines without a value on bars the windows read:\n{bad.T}")
    vs = list(grid(symbol) if variants is None else variants)
    res, trd, qtr, wkl = [], [], [], []
    for n, v in enumerate(vs):
        for w in RUN_WINDOWS:
            row: Dict[str, object] = {**v.ident(), "window": w}
            kept = {}
            for cost in COSTS:
                r = run_variant(st, v, w, cost)
                row.update({k + _suffix(cost): val for k, val in scores(r).items()})
                row["start"], row["end"] = r.start, r.end
                if w == "devval":
                    continue
                tr = r.trades.drop(columns=["entry_ix", "exit_ix"])
                tr.insert(0, "cost", cost)
                tr.insert(0, "window", w)
                tr.insert(0, "vid", v.vid)
                trd.append(tr)
                kept[cost] = (TM.quarter_pnl(r), TM.weekly_pnl(r))
            res.append(row)
            if w == "devval":
                continue
            (q0, qa, ha), (w0, wa) = kept[1.0]
            (q1, qb, hb), (w1, wb) = kept[1.5]
            if not (np.array_equal(q0, q1) and np.array_equal(w0, w1)):
                raise AssertionError("the quarters / weeks of the two costs differ")
            qtr.append(pd.DataFrame({"vid": v.vid, "window": w, "quarter": [_quarter_label(x) for x in q0],
                                     "start": [str(TM.utc(x).date()) for x in q0], "pnl": qa, "pnl_x15": qb,
                                     "held": ha, "held_x15": hb}))
            wkl.append(pd.DataFrame({"vid": v.vid, "window": w, "week_start": [str(TM.utc(x)) for x in w0],
                                     "pnl": wa, "pnl_x15": wb}))
        if (n + 1) % 50 == 0 or n + 1 == len(vs):
            log(f"  {symbol}: {n + 1} / {len(vs)} variants ({time.time() - t0:.0f} s)")
    bh = []
    for w in RUN_WINDOWS:
        a, z = TM.window(w, symbol)
        for cost in COSTS:
            bh.append({"symbol": symbol, "window": w, "start": a, "end": z, "cost": cost,
                       **TM.buy_and_hold(mk, a, z, cost)})
    info = {"symbol": symbol, "m1_bars": int(len(mk)), "first_m1": str(TM.utc(mk.t[0])),
            "last_m1": str(TM.utc(mk.t[-1])), "served_until": str(TM.utc(mk.end_s)), "variants": len(vs),
            "runs": len(vs) * len(RUN_WINDOWS) * len(COSTS), "seconds": round(time.time() - t0, 1)}
    return {"results": pd.DataFrame(res), "trades": pd.concat(trd, ignore_index=True),
            "quarters": pd.concat(qtr, ignore_index=True), "weekly": pd.concat(wkl, ignore_index=True),
            "buy_and_hold": pd.DataFrame(bh), "state_checks": checks, "info": pd.DataFrame([info])}


def blob_id(path: Path) -> str:
    """The git blob id of a file (what ``git hash-object`` prints), computed without git."""
    body = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def code_blobs() -> Dict[str, str]:
    return {"blob " + f.split("/")[-1]: blob_id(REPO_ROOT / f) for f in CODE_FILES}


GZ = {"method": "gzip", "mtime": 0}          # reproducible gzip bytes


def run_grid(symbols: Sequence[str] = SYMBOLS, out: Path = STUDY_DIR, log=print) -> Dict[str, pd.DataFrame]:
    """``run``: every symbol one at a time (one symbol's M1 bars in memory), then the CSVs."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    code = code_blobs()                              # the code that runs (checked again after the runs)
    parts: Dict[str, List[pd.DataFrame]] = {}
    for s in symbols:
        log(f"{s}: loading and running {len(grid(s))} variants x {len(RUN_WINDOWS)} windows x {len(COSTS)} costs")
        got = run_symbol(s, log)
        for k, v in got.items():
            parts.setdefault(k, []).append(v)
        del got
    allp = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}
    if code_blobs() != code:
        raise RuntimeError("a code file changed while the grid ran: nothing written")
    info = allp["info"]
    info["written_utc"] = str(pd.Timestamp.now(tz="UTC").floor("s"))
    for k, v in code.items():
        info[k] = v
    grid_frame(symbols).to_csv(out / "grid.csv", index=False)
    allp["results"].to_csv(out / "results_dev_val.csv", index=False)
    allp["trades"].to_csv(out / "trades_dev_val.csv.gz", index=False, compression=GZ)
    allp["quarters"].to_csv(out / "quarters_dev_val.csv", index=False)
    allp["weekly"].to_csv(out / "weekly_dev_val.csv.gz", index=False, compression=GZ)
    allp["buy_and_hold"].to_csv(out / "buy_and_hold.csv", index=False)
    allp["state_checks"].to_csv(out / "state_checks.csv", index=False)
    info.to_csv(out / "run_info.csv", index=False)
    log(f"wrote {out}")
    return allp


# ───────────────────────────── the selection (PREREG 7, DEVIATIONS 23-24) ─────────────────────────────

def read_results(out: Path = STUDY_DIR) -> pd.DataFrame:
    return pd.read_csv(Path(out) / "results_dev_val.csv", float_precision="round_trip")


def qualification(res: pd.DataFrame) -> pd.DataFrame:
    """
    Per variant: PREREG 7's four rules and the would-be finalists.
    q1 Development net > 0 at x1.0 and at x1.5; q2 Development trades >= 30 (1H, 4H) / 15 (1D) at x1.0;
    q3 Development profit / max drawdown >= 1.0 and positive quarters >= 50% at x1.0; q4 Validation net > 0 at x1.0.
    Finalists: per symbol, the qualifiers with the highest profit / max drawdown on dev + val together (one
    continuous run, x1.0), at most one per indicator (VWRSI-RV is the VWRSI), at most three.
    """
    by = {w: res[res.window == w].set_index("vid") for w in RUN_WINDOWS}
    d, v, dv = by["dev"], by["val"], by["devval"]
    if not (d.index.equals(v.index) and d.index.equals(dv.index)):
        raise ValueError("every variant needs its dev, val and devval rows")
    q = d[["symbol", "tf", "indicator", "family", "filter", "stop", "group"]].copy()
    q["dev_net"], q["dev_net_x15"], q["dev_trades"] = d.net, d.net_x15, d.trades
    q["dev_profit_dd"], q["dev_pos_q_share"], q["dev_sharpe_w"] = d.profit_dd, d.pos_q_share, d.sharpe_w
    q["val_net"], q["val_net_x15"], q["val_profit_dd"], q["val_trades"] = v.net, v.net_x15, v.profit_dd, v.trades
    q["devval_net"], q["devval_net_x15"], q["devval_max_dd"], q["devval_profit_dd"] = (
        dv.net, dv.net_x15, dv.max_dd, dv.profit_dd)
    q["q1"] = (d.net > 0) & (d.net_x15 > 0)
    q["q2"] = d.trades >= d.tf.map(MIN_TRADES)
    q["q3"] = (d.profit_dd >= 1.0) & (d.pos_q_share >= 0.5)            # NaN (no drawdown) is no pass
    q["q4"] = v.net > 0
    q["qualifies"] = q.q1 & q.q2 & q.q3 & q.q4
    q["rank"] = np.nan
    q["finalist"] = False
    for s, g in q[q.qualifies].groupby("symbol"):
        order = g.assign(_a=-g.devval_profit_dd.fillna(-np.inf), _b=-g.dev_profit_dd.fillna(-np.inf),
                         _c=g.index).sort_values(["_a", "_b", "_c"])
        q.loc[order.index, "rank"] = np.arange(1, len(order) + 1)
        taken = []
        for vid, row in order.iterrows():
            if len(taken) == N_FINALISTS:
                break
            if row.group not in taken:
                taken.append(row.group)
                q.loc[vid, "finalist"] = True
    return q.reset_index()


# ───────────────────────────── the comparison with the RSI (PREREG 7, DEVIATIONS 25) ─────────────────────────────

def vs_rsi(res: pd.DataFrame) -> pd.DataFrame:
    """Each oscillator's R1 / R2 / R4 variant against the RSI variant of the same family, filter, stop, tf, symbol."""
    rows = []
    idx = res.set_index(["vid", "window"])
    for _, r in res[(res.window == "dev") & res.indicator.isin(["LaRSI", "VWRSI", RV, "TSI", "QQE"])
                    & res.family.isin(["R1", "R2", "R4"])].iterrows():
        rv = Variant(r.symbol, r.tf, "RSI", r.family, r["filter"], r["stop"]).vid
        if (rv, "dev") not in idx.index:
            raise AssertionError(f"{r.vid}: no RSI counterpart {rv}")
        row = {"vid": r.vid, "rsi_vid": rv, **{k: r[k] for k in ("symbol", "tf", "indicator", "group", "family",
                                                                  "filter", "stop")}}
        for w in ("dev", "val"):
            a, b = idx.loc[(r.vid, w)], idx.loc[(rv, w)]
            pa, pb = float(a.profit_dd), float(b.profit_dd)
            row.update({f"{w}_net": a.net, f"{w}_rsi_net": b.net, f"{w}_win_net": bool(a.net > b.net),
                        f"{w}_profit_dd": pa, f"{w}_rsi_profit_dd": pb,
                        f"{w}_win_pdd": (pa > pb) if (math.isfinite(pa) and math.isfinite(pb)) else np.nan,
                        f"{w}_trades": int(a.trades), f"{w}_rsi_trades": int(b.trades),
                        f"{w}_fewer_trades": bool(a.trades < b.trades),
                        f"{w}_losing_streak": int(a.max_losing_streak), f"{w}_rsi_losing_streak": int(b.max_losing_streak)})
        rows.append(row)
    return pd.DataFrame(rows)


def vs_rsi_summary(vs: pd.DataFrame) -> pd.DataFrame:
    """Wins against the RSI per symbol and indicator, and by timeframe and family within it."""
    out = []
    for by in (["symbol", "indicator"], ["symbol", "indicator", "tf"], ["symbol", "indicator", "family"]):
        for key, g in vs.groupby(by, sort=False):
            key = key if isinstance(key, tuple) else (key,)
            row = {"by": "+".join(by[1:]), **dict(zip(by, key)), "n": int(len(g))}
            for w in ("dev", "val"):
                wp = g[f"{w}_win_pdd"].dropna().astype(bool)
                row.update({f"{w}_wins_net": int(g[f"{w}_win_net"].sum()), f"{w}_wins_pdd": int(wp.sum()),
                            f"{w}_n_pdd": int(len(wp)), f"{w}_fewer_trades": int(g[f"{w}_fewer_trades"].sum()),
                            f"{w}_shorter_streak": int((g[f"{w}_losing_streak"] < g[f"{w}_rsi_losing_streak"]).sum()),
                            f"{w}_median_trades_ratio": float(np.median(g[f"{w}_trades"] / g[f"{w}_rsi_trades"].clip(lower=1)))})
            out.append(row)
    cols = ["by", "symbol", "indicator", "tf", "family"]
    d = pd.DataFrame(out)
    return d[[c for c in cols if c in d] + [c for c in d if c not in cols]]


# ───────────────────────────── question 2: a filter against no filter (DEVIATIONS 30) ─────────────────────────────

FILTERED = ("F1", "F2-4H", "F2-1D", "F3")
MA200_FILTERS = ("F1", "F2-4H", "F2-1D")


def vs_f0(res: pd.DataFrame) -> pd.DataFrame:
    """Each filtered R1 / R2 / R3 variant against the variant of the same symbol, timeframe, indicator, family and stop
    with F0. The TSI's F3 rows are not compared: they are its F0 rows (DEVIATIONS 22)."""
    rows = []
    idx = res.set_index(["vid", "window"])
    sel = res[(res.window == "dev") & res.family.isin(["R1", "R2", "R3"]) & res["filter"].isin(FILTERED)
              & ~((res.indicator == "TSI") & (res["filter"] == "F3"))]
    for _, r in sel.iterrows():
        v0 = Variant(r.symbol, r.tf, r.indicator, r.family, "F0", r["stop"]).vid
        if (v0, "dev") not in idx.index:
            raise AssertionError(f"{r.vid}: no F0 counterpart {v0}")
        row = {"vid": r.vid, "f0_vid": v0, **{k: r[k] for k in ("symbol", "tf", "indicator", "group", "family",
                                                                "filter", "stop")}}
        for w in ("dev", "val"):
            a, b = idx.loc[(r.vid, w)], idx.loc[(v0, w)]
            pa, pb = float(a.profit_dd), float(b.profit_dd)
            row.update({f"{w}_net": a.net, f"{w}_f0_net": b.net, f"{w}_win_net": bool(a.net > b.net),
                        f"{w}_profit_dd": pa, f"{w}_f0_profit_dd": pb,
                        f"{w}_win_pdd": (pa > pb) if (math.isfinite(pa) and math.isfinite(pb)) else np.nan,
                        f"{w}_max_dd": a.max_dd, f"{w}_f0_max_dd": b.max_dd,
                        f"{w}_trades": int(a.trades), f"{w}_f0_trades": int(b.trades)})
        rows.append(row)
    return pd.DataFrame(rows)


def _most(k: int, n: int) -> bool:
    """More than half (DEVIATIONS 30-31); nothing to count is no majority."""
    return n > 0 and 2 * k > n


def verdict(dev_ok: bool, val_ok: bool, dev_bad: Optional[bool] = None, val_bad: Optional[bool] = None,
            words: Tuple[str, str, str] = ("holds", "does not hold", "mixed")) -> str:
    """Both windows say yes: the first word; both say no (``*_bad``, by default ``not *_ok``): the second; else the
    third (DEVIATIONS 30-31)."""
    dev_bad = (not dev_ok) if dev_bad is None else dev_bad
    val_bad = (not val_ok) if val_bad is None else val_bad
    if dev_ok and val_ok:
        return words[0]
    if dev_bad and val_bad:
        return words[1]
    return words[2]


def vs_f0_summary(vf: pd.DataFrame) -> pd.DataFrame:
    """Wins against F0 per symbol and filter, and by timeframe and by indicator within it, with DEVIATIONS 30's word:
    "helps" (more than half of the pairs won on net and on P/DD, in Development and in Validation), "does not help"
    (at most half on both scores in both windows) or "mixed"."""
    out = []
    for by in (["symbol", "filter"], ["symbol", "filter", "tf"], ["symbol", "filter", "indicator"]):
        for key, g in vf.groupby(by, sort=False):
            key = key if isinstance(key, tuple) else (key,)
            row = {"by": "+".join(by[1:]), **dict(zip(by, key)), "n": int(len(g))}
            ok, bad = {}, {}
            for w in ("dev", "val"):
                wp = g[f"{w}_win_pdd"].dropna().astype(bool)
                kn, kp = int(g[f"{w}_win_net"].sum()), int(wp.sum())
                row.update({f"{w}_wins_net": kn, f"{w}_wins_pdd": kp, f"{w}_n_pdd": int(len(wp))})
                ok[w] = _most(kn, len(g)) and _most(kp, len(wp))
                bad[w] = not _most(kn, len(g)) and not _most(kp, len(wp))
            row["verdict"] = verdict(ok["dev"], ok["val"], bad["dev"], bad["val"],
                                     ("helps", "does not help", "mixed"))
            out.append(row)
    cols = ["by", "symbol", "filter", "tf", "indicator"]
    d = pd.DataFrame(out)
    return d[[c for c in cols if c in d] + [c for c in d if c not in cols]]


# ───────────────────────────── multiple testing (PREREG 7, DEVIATIONS 26) ─────────────────────────────

def bootstrap_pvalues(D: np.ndarray, B_: int = 5000, block: float = 8.0, seed: int = 20261117) -> Dict[str, float]:
    """
    Hansen's SPA and White's Reality Check on D (weeks x variants of weekly P/L, benchmark flat) from the same
    stationary-bootstrap resamples as ``silver.spa_test`` (its draws, in its order): the SPA p-value and best index are
    ``silver.spa_test``'s exactly; the Reality Check compares max sqrt(T) x mean with the bootstrap maxima of
    sqrt(T) x (resampled mean - mean).
    """
    D = np.asarray(D, np.float64)
    T, _ = D.shape
    keep = np.flatnonzero(D.std(axis=0) > 0)
    Dk = D[:, keep]
    dbar = Dk.mean(axis=0)
    rng = np.random.default_rng(seed)
    p_new = 1.0 / block
    stats = np.zeros((B_, Dk.shape[1]))
    for b in range(B_):
        idx = np.empty(T, np.int64)
        idx[0] = rng.integers(T)
        u = rng.random(T)
        r = rng.integers(T, size=T)
        for t in range(1, T):
            idx[t] = r[t] if u[t] < p_new else (idx[t - 1] + 1) % T
        stats[b] = Dk[idx].mean(axis=0)
    omega = np.sqrt(T) * stats.std(axis=0)
    omega = np.where(omega > 0, omega, np.inf)
    tstat = np.sqrt(T) * dbar / omega
    t_spa = max(float(tstat.max()), 0.0)
    thr = -math.sqrt(2.0 * math.log(math.log(T)))
    mu_c = np.where(tstat >= thr, dbar, 0.0)
    tb = np.maximum((np.sqrt(T) * (stats - mu_c[None, :]) / omega).max(axis=1), 0.0)
    v_rc = float(np.sqrt(T) * dbar.max())
    vb = (np.sqrt(T) * (stats - dbar[None, :])).max(axis=1)
    return {"spa_p": float((tb >= t_spa).mean()), "spa_best": int(keep[int(np.argmax(tstat))]),
            "rc_p": float((vb >= v_rc).mean()), "rc_best": int(keep[int(np.argmax(dbar))]), "n_used": int(len(keep))}


def weekly_matrix(weekly: pd.DataFrame, vids: Sequence[str], window: str = "dev", col: str = "pnl") -> np.ndarray:
    w = weekly[weekly.window == window]
    m = w.pivot(index="week_start", columns="vid", values=col)
    if m.isna().any().any():
        raise ValueError("the variants' weeks do not line up")
    return m.sort_index()[list(vids)].to_numpy(np.float64)


def within_group_variance(x, groups) -> Tuple[float, float]:
    """(the pooled variance of ``x`` around the mean of its group, sum of squares over n - number of groups; the share
    of the total sum of squares that lies between the groups' means)."""
    x = np.asarray(x, np.float64)
    g = np.asarray(groups)
    if x.shape != g.shape or not np.all(np.isfinite(x)):
        raise ValueError("x must be finite and have the shape of groups")
    mu = pd.Series(x).groupby(g).transform("mean").to_numpy()
    ss_w, ss_t = float(np.sum((x - mu) ** 2)), float(np.sum((x - x.mean()) ** 2))
    k = len(np.unique(g))
    if len(x) <= k:
        raise ValueError("fewer values than groups + 1")
    return ss_w / (len(x) - k), (1.0 - ss_w / ss_t) if ss_t > 0 else 0.0


def multiple_testing(res: pd.DataFrame, weekly: pd.DataFrame, qual: pd.DataFrame) -> pd.DataFrame:
    """Per symbol: the deflated Sharpe of the best Development variant (and of each would-be finalist) for N = the
    variants run on that symbol, and the SPA / Reality Check p-values over all of them (dev weekly P/L, x1.0).
    E[max] uses the variance of the N trials' raw weekly Sharpe ratios (DEVIATIONS 26), and for information the null
    variance 1 / (T - 1) and the pooled within-timeframe variance (added on review, after the run: on BTC most of the
    spread lies between the timeframes, as the costs make most 1H rows lose)."""
    from . import silver as S                       # imported here: it registers extra symbols on import
    rows = []
    for s in [x for x in SYMBOLS if x in set(res.symbol)]:
        d = res[(res.symbol == s) & (res.window == "dev")].reset_index(drop=True)
        W = weekly_matrix(weekly, d.vid.tolist())
        T, N = W.shape
        sr = d.sr_w_raw.to_numpy(np.float64)
        if not np.allclose(W.mean(axis=0) / np.where(W.std(axis=0, ddof=1) > 0, W.std(axis=0, ddof=1), np.inf),
                           sr, rtol=1e-9, atol=1e-12):
            raise AssertionError("the weekly file and the results disagree on the weekly Sharpe")
        var = float(np.nanvar(sr, ddof=1))
        var_w, between = within_group_variance(sr, d.tf.to_numpy())
        sr0, sr0_null = S.expected_max_sr(var, N), S.expected_max_sr(1.0 / (T - 1), N)
        sr0_w = S.expected_max_sr(var_w, N)
        p_spa, ib = S.spa_test(W)
        bp = bootstrap_pvalues(W)
        if not (bp["spa_p"] == p_spa and bp["spa_best"] == ib):
            raise AssertionError("the bootstrap does not reproduce silver.spa_test")
        best = d.loc[int(np.argmax(d.sharpe_w.to_numpy()))]
        fin = qual[(qual.symbol == s) & qual.finalist].sort_values("rank")
        picks = [("best dev Sharpe", best.vid)] + [(f"would-be finalist {j} (rank {int(r['rank'])})", r.vid)
                                                   for j, (_, r) in enumerate(fin.iterrows(), 1)]
        for role, vid in picks:
            x = d[d.vid == vid].iloc[0]
            rows.append({"symbol": s, "role": role, "vid": vid, "N": N, "T_weeks": T,
                         "sharpe_w_ann": float(x.sharpe_w), "sr_w_raw": float(x.sr_w_raw),
                         "skew_w": float(x.skew_w), "kurt_w": float(x.kurt_w),
                         "var_sr_trials": var, "e_max_sr_ann": sr0 * math.sqrt(52.0),
                         "e_max_sr_null_ann": sr0_null * math.sqrt(52.0),
                         "dsr": S.dsr(float(x.sr_w_raw), T, float(x.skew_w), float(x.kurt_w), sr0),
                         "dsr_null": S.dsr(float(x.sr_w_raw), T, float(x.skew_w), float(x.kurt_w), sr0_null),
                         "spa_p": p_spa, "spa_best_vid": d.vid.iloc[ib], "rc_p": bp["rc_p"],
                         "rc_best_vid": d.vid.iloc[bp["rc_best"]], "n_in_bootstrap": bp["n_used"],
                         "var_sr_within_tf": var_w, "between_tf_share": between,
                         "e_max_sr_within_tf_ann": sr0_w * math.sqrt(52.0),
                         "dsr_within_tf": S.dsr(float(x.sr_w_raw), T, float(x.skew_w), float(x.kurt_w), sr0_w)})
    return pd.DataFrame(rows)


# ───────────────────────────── the exam against buy-and-hold (DEVIATIONS 28) ─────────────────────────────

EXAM_MIN_PDD = 0.5          # PREREG 8: a finalist passes when net > 0 at x1.0 and profit / max drawdown >= 0.5


def exam_rule(net, profit_dd) -> np.ndarray:
    """PREREG 8's pass rule on arrays (a profit / max drawdown that does not exist is no pass)."""
    net, pdd = np.asarray(net, np.float64), np.asarray(profit_dd, np.float64)
    with np.errstate(invalid="ignore"):
        return (net > 0) & (pdd >= EXAM_MIN_PDD)


def _bh(bh: pd.DataFrame, symbol: str, window: str) -> pd.Series:
    b = bh[(bh.symbol == symbol) & (bh.window == window) & (bh.cost == 1.0)]
    if len(b) != 1:
        raise ValueError(f"buy_and_hold: {len(b)} rows for {symbol} {window} at x1.0")
    return b.iloc[0]


def vs_buy_and_hold(res: pd.DataFrame, bh: pd.DataFrame, vids: Sequence[str],
                    windows: Sequence[str] = RUN_WINDOWS) -> pd.DataFrame:
    """DEVIATIONS 28: each variant of ``vids`` per window at x1.0 next to buy-and-hold of 0.01 lot over the same span:
    net, max drawdown, profit / max drawdown, PREREG 8's rule for both, and the exposure-matched buy-and-hold (the
    variant's time in the market x buy-and-hold's net)."""
    idx = res.set_index(["vid", "window"])
    rows = []
    seen: Dict[str, int] = {}
    for vid in vids:
        s = Variant.of(vid).symbol
        seen[s] = j = seen.get(s, 0) + 1                # the variant's number within its symbol
        for w in windows:
            x, b = idx.loc[(vid, w)], _bh(bh, s, w)
            pdd, bpdd = float(x.profit_dd), float(b.bh_profit_dd)
            em = float(x.time_in_mkt) * float(b.bh_net)
            rows.append({"symbol": s, "n": j, "vid": vid, "window": w, "net": float(x.net), "max_dd": float(x.max_dd),
                         "profit_dd": pdd, "exam_rule": bool(exam_rule(x.net, pdd)),
                         "time_in_mkt": float(x.time_in_mkt), "n_long": int(x.n_long), "n_short": int(x.n_short),
                         "bh_net": float(b.bh_net), "bh_max_dd": float(b.bh_max_dd), "bh_profit_dd": bpdd,
                         "bh_exam_rule": bool(exam_rule(b.bh_net, bpdd)), "bh_exposure_matched_net": em,
                         "pdd_above_bh": bool(pdd > bpdd) if (math.isfinite(pdd) and math.isfinite(bpdd)) else np.nan,
                         "net_above_exposure_matched": bool(x.net > em)})
    return pd.DataFrame(rows)


def exam_rule_rates(res: pd.DataFrame, bh: pd.DataFrame, qual: pd.DataFrame,
                    windows: Sequence[str] = RUN_WINDOWS) -> pd.DataFrame:
    """DEVIATIONS 28: per symbol and window, the rows that pass PREREG 8's rule: the R2 rows (long only, MA200 alone's
    included), the other rows, all rows, the qualifiers, and buy-and-hold."""
    rows = []
    for s in [x for x in SYMBOLS if x in set(res.symbol)]:
        qs = set(qual[(qual.symbol == s) & qual.qualifies].vid)
        for w in windows:
            d = res[(res.symbol == s) & (res.window == w)]
            ok = exam_rule(d.net, d.profit_dd)
            r2 = (d.family == "R2").to_numpy()
            for name, m in (("R2 rows (long only)", r2), ("other rows", ~r2), ("all rows", np.ones(len(d), bool)),
                            ("qualifiers", d.vid.isin(qs).to_numpy())):
                rows.append({"symbol": s, "window": w, "rows": name, "n": int(m.sum()), "pass": int(ok[m].sum()),
                             "share": float(ok[m].mean()) if m.any() else np.nan})
            b = _bh(bh, s, w)
            p = bool(exam_rule(b.bh_net, b.bh_profit_dd))
            rows.append({"symbol": s, "window": w, "rows": "buy-and-hold", "n": 1, "pass": int(p), "share": float(p)})
    return pd.DataFrame(rows)


def runners_up(qual: pd.DataFrame, res: pd.DataFrame) -> pd.DataFrame:
    """
    Per symbol with three would-be finalists: the best qualifier of each indicator without a slot, against the last
    finalist (PREREG 7's rule takes it only with a higher D+V profit / max drawdown): the gap, and the D+V net it
    needed at its own drawdown to take the slot. The x1.5 values of the pair are added for information.
    """
    dv = res[res.window == "devval"].set_index("vid")
    rows = []
    for s in [x for x in SYMBOLS if x in set(qual.symbol)]:
        qs = qual[(qual.symbol == s) & qual.qualifies].sort_values("rank")
        fin = qs[qs.finalist]
        if len(fin) < N_FINALISTS:
            continue
        last = fin.iloc[-1]
        for g in GROUPS:
            if g in set(fin.group):
                continue
            c = qs[qs.group == g]
            if not len(c):
                continue
            c = c.iloc[0]
            rows.append({"symbol": s, "indicator": g, "vid": c.vid, "rank": int(c["rank"]),
                         "devval_net": float(c.devval_net), "devval_max_dd": float(c.devval_max_dd),
                         "devval_profit_dd": float(c.devval_profit_dd), "last_finalist": last.vid,
                         "last_finalist_rank": int(last["rank"]), "last_finalist_profit_dd": float(last.devval_profit_dd),
                         "gap_profit_dd": float(last.devval_profit_dd - c.devval_profit_dd),
                         "net_needed": float(last.devval_profit_dd * c.devval_max_dd - c.devval_net),
                         "devval_profit_dd_x15": float(dv.loc[c.vid, "profit_dd_x15"]),
                         "last_finalist_profit_dd_x15": float(dv.loc[last.vid, "profit_dd_x15"])})
    return pd.DataFrame(rows)


# ───────────────────────────── PREREG 8's comparison curves (DEVIATIONS 29) ─────────────────────────────

GROUPS = ("RSI", "LaRSI", "VWRSI", "TSI", "QQE", "MA200")      # the six indicators of DEVIATIONS 24


def rsi_baseline(vid: str) -> str:
    """DEVIATIONS 29: the RSI row with the variant's family, filter, stop and timeframe (DEVIATIONS 25's pair); R3 and
    the two controls take the RSI's R1 row; MA200 alone the RSI's row of its family with F0; an RSI row is its own."""
    v = Variant.of(vid)
    if v.indicator == "RSI":
        return vid
    fam = v.family if v.family in ("R1", "R2", "R4") else "R1"
    return Variant(v.symbol, v.tf, "RSI", fam, v.filt, v.stop).vid


def curves(qual: pd.DataFrame) -> pd.DataFrame:
    """
    DEVIATIONS 29, per symbol: the would-be finalists; the best variant of each indicator (its qualifier first in PREREG
    7's order, else, with no qualifier, its variant with the highest D+V profit / max drawdown, ties as DEVIATIONS 24);
    the RSI baseline of each finalist. One row per role (a variant can have several).
    """
    rows = []
    for s in [x for x in SYMBOLS if x in set(qual.symbol)]:
        qs = qual[qual.symbol == s].set_index("vid")
        fin = qs[qs.finalist].sort_values("rank")

        def add(role, vid):
            r = qs.loc[vid]
            rows.append({"symbol": s, "role": role, "vid": vid, "group": r.group, "qualifies": bool(r.qualifies),
                         "rank": r["rank"], "finalist": bool(r.finalist), "dev_net": float(r.dev_net),
                         "val_net": float(r.val_net), "devval_net": float(r.devval_net),
                         "devval_max_dd": float(r.devval_max_dd), "devval_profit_dd": float(r.devval_profit_dd)})
        for j, vid in enumerate(fin.index, 1):
            add(f"finalist {j}", vid)
        for g in GROUPS:
            gq = qs[qs.group == g]
            if not len(gq):
                continue
            ok = gq[gq.qualifies]
            if len(ok):
                vid = ok.sort_values("rank").index[0]
            else:
                vid = gq.assign(_a=-gq.devval_profit_dd.fillna(-np.inf), _b=-gq.dev_profit_dd.fillna(-np.inf),
                                _c=gq.index).sort_values(["_a", "_b", "_c"]).index[0]
            add(f"best {g}", vid)
        for j, vid in enumerate(fin.index, 1):
            add(f"RSI baseline of finalist {j}", rsi_baseline(vid))
    return pd.DataFrame(rows)


# ───────────────────────────── PREREG 9's claims: the evidence (DEVIATIONS 31) ─────────────────────────────

FOUR = ("LaRSI", "VWRSI", RV, "TSI", "QQE")         # the four replacements (BTC's RV rows with the VWRSI)


def _ratio_median(g: pd.DataFrame, w: str) -> float:
    return float(np.median(g[f"{w}_trades"] / g[f"{w}_rsi_trades"].clip(lower=1))) if len(g) else np.nan


def claims(res: pd.DataFrame, vs: pd.DataFrame, vf: pd.DataFrame) -> pd.DataFrame:
    """
    DEVIATIONS 31: each part of each claim of PREREG 9, per symbol, on the rows it is about, in Development and in
    Validation separately; the part holds on a symbol when it holds in both windows, does not hold when it fails in
    both, and is mixed otherwise. "Most" = more than half, "every" = all, "about half" = a median ratio in
    [0.375, 0.625] (nearer to 1/2 than to 1/4 or 3/4), "far fewer" = a median ratio <= 0.5. Wins: net at x1.0.
    """
    rows = []

    def add(claim, part, symbol, about, dev, val, dev_ok, val_ok, note=""):
        rows.append({"claim": claim, "part": part, "symbol": symbol, "rows": about, "dev": dev, "val": val,
                     "dev_ok": dev_ok, "val_ok": val_ok, "verdict": verdict(dev_ok, val_ok), "note": note})

    def untestable(claim, part, symbol, why):
        rows.append({"claim": claim, "part": part, "symbol": symbol, "rows": "", "dev": "", "val": "",
                     "dev_ok": np.nan, "val_ok": np.nan, "verdict": "cannot be tested", "note": why})

    def count(mask_dev, mask_val, n):
        return int(mask_dev.sum()), int(mask_val.sum()), int(n)

    def frac(k, n):
        return f"{k}/{n}"

    by = {w: res[res.window == w].set_index("vid") for w in ("dev", "val")}
    untestable(1, "half of 8 alternatives could not beat the RSI", "both",
               "the other four alternatives of the video are not in the grid")
    for s in [x for x in SYMBOLS if x in set(res.symbol)]:
        v = vs[vs.symbol == s]
        f = vf[vf.symbol == s]
        d, va = by["dev"][by["dev"].symbol == s], by["val"][by["val"].symbol == s]
        inds = ["QQE", "TSI", "VWRSI"] + ([RV] if has_rv(s) else []) + ["LaRSI"]
        # 1. these four beat the RSI on most markets
        for ind in inds:
            g = v[v.indicator == ind]
            kd, kv, n = count(g.dev_win_net, g.val_win_net, len(g))
            add(1, f"{ind} beats the RSI in most of its pairs", s, f"{ind}'s RSI pairs (DEVIATIONS 25)",
                frac(kd, n), frac(kv, n), _most(kd, n), _most(kv, n))
        # 2. QQE: fewer trades in every pair, beats it on most, shorter losing streaks
        g = v[v.indicator == "QQE"]
        kd, kv, n = count(g.dev_fewer_trades, g.val_fewer_trades, len(g))
        add(2, "QQE takes fewer trades than the RSI in every pair", s, "QQE's RSI pairs", frac(kd, n), frac(kv, n),
            n > 0 and kd == n, n > 0 and kv == n)
        kd, kv, n = count(g.dev_win_net, g.val_win_net, len(g))
        add(2, "QQE beats the RSI in most pairs", s, "QQE's RSI pairs", frac(kd, n), frac(kv, n), _most(kd, n),
            _most(kv, n))
        kd, kv, n = count(g.dev_losing_streak < g.dev_rsi_losing_streak, g.val_losing_streak < g.val_rsi_losing_streak,
                          len(g))
        add(2, "QQE has a shorter longest losing streak in most pairs", s, "QQE's RSI pairs", frac(kd, n),
            frac(kv, n), _most(kd, n), _most(kv, n))
        # 3. TSI: the zero line works, the signal line is a coin flip, beats the RSI with about half the trades
        zd = d[(d.indicator == "TSI") & d.family.isin(["R1", "R2"]) & (d["filter"] == "F0")]
        zv = va.loc[zd.index]
        kd, kv, n = count(zd.net > 0, zv.net > 0, len(zd))
        add(3, "the zero line works: TSI R1 / R2 with F0 make money in most rows", s, "TSI R1, R2 with F0",
            frac(kd, n), frac(kv, n), _most(kd, n), _most(kv, n))
        sig = d[(d.indicator == "TSI") & (d.family == "CTL-SIGNAL")]
        zero = [Variant(s, x.tf, "TSI", "R1", "F0", x["stop"]).vid for _, x in sig.iterrows()]
        kd = int((d.loc[zero].net.to_numpy() > sig.net.to_numpy()).sum())
        kv = int((va.loc[zero].net.to_numpy() > va.loc[sig.index].net.to_numpy()).sum())
        n = len(sig)
        pos = f"signal-line rows with net > 0: {int((sig.net > 0).sum())}/{n} (dev), " \
              f"{int((va.loc[sig.index].net > 0).sum())}/{n} (val)"
        add(3, "the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs", s,
            "TSI R1 F0 against CTL-SIGNAL, same timeframe and stop", frac(kd, n), frac(kv, n), _most(kd, n),
            _most(kv, n), pos)
        g = v[v.indicator == "TSI"]
        md, mv = _ratio_median(g, "dev"), _ratio_median(g, "val")
        add(3, "TSI takes about half the RSI's trades (median ratio in [0.375, 0.625])", s,
            "TSI's RSI pairs: median of trades / RSI's",
            f"{md:.2f}", f"{mv:.2f}", 0.375 <= md <= 0.625, 0.375 <= mv <= 0.625)
        # 4. VWRSI: the trend rule on every crypto timeframe, the 20 / 80 reversals, real volume
        for ind in ("VWRSI",) + ((RV,) if has_rv(s) else ()):
            if has_rv(s):
                g = v[(v.indicator == ind) & v.family.isin(["R1", "R2"])]
                per = {tf: count(x.dev_win_net, x.val_win_net, len(x)) for tf, x in g.groupby("tf", sort=False)}
                per = {tf: per[tf] for tf in TFS if tf in per}
                add(4, f"{ind}'s trend rule beats the RSI on every crypto timeframe (most pairs on each)", s,
                    f"{ind} R1, R2 against RSI R1, R2, per timeframe",
                    ", ".join(f"{tf} {frac(a, n)}" for tf, (a, _, n) in per.items()),
                    ", ".join(f"{tf} {frac(b, n)}" for tf, (_, b, n) in per.items()),
                    bool(per) and all(_most(a, n) for a, _, n in per.values()),
                    bool(per) and all(_most(b, n) for _, b, n in per.values()))
            g = v[(v.indicator == ind) & (v.family == "R4")]
            kd, kv, n = count(g.dev_win_net, g.val_win_net, len(g))
            add(4, f"{ind}'s 20 / 80 reversals are no better than the RSI's (it wins at most half)", s,
                f"{ind} R4 against RSI R4", frac(kd, n), frac(kv, n), n > 0 and not _most(kd, n),
                n > 0 and not _most(kv, n))
        if has_rv(s):
            rv = d[d.indicator == RV]
            tick = [x.replace(f"|{RV}|", "|VWRSI|") for x in rv.index]
            kd = int((rv.net.to_numpy() > d.loc[tick].net.to_numpy()).sum())
            kv = int((va.loc[rv.index].net.to_numpy() > va.loc[tick].net.to_numpy()).sum())
            add(4, "the VWRSI needs real volume: on Binance volume it beats tick volume in most rows", s,
                "VWRSI-RV against the same VWRSI row on tick volume", frac(kd, len(rv)), frac(kv, len(rv)),
                _most(kd, len(rv)), _most(kv, len(rv)))
        else:
            untestable(4, "the VWRSI's trend rule on crypto; it needs real volume", s,
                       "not a crypto market: the gold CFD has tick volume only")
        # 5. LaRSI
        g = v[v.indicator == "LaRSI"]
        per = {tf: count(x.dev_win_net, x.val_win_net, len(x)) for tf, x in g.groupby("tf", sort=False)}
        per = {tf: per[tf] for tf in TFS if tf in per}
        add(5, "LaRSI beats the RSI in most pairs on every timeframe", s, "LaRSI's RSI pairs, per timeframe",
            ", ".join(f"{tf} {frac(a, n)}" for tf, (a, _, n) in per.items()),
            ", ".join(f"{tf} {frac(b, n)}" for tf, (_, b, n) in per.items()),
            bool(per) and all(_most(a, n) for a, _, n in per.values()),
            bool(per) and all(_most(b, n) for _, b, n in per.values()))
        md, mv = _ratio_median(g, "dev"), _ratio_median(g, "val")
        add(5, "LaRSI takes far fewer trades than the RSI (median ratio <= 0.5)", s,
            "LaRSI's RSI pairs: median of trades / RSI's", f"{md:.2f}", f"{mv:.2f}", md <= 0.5, mv <= 0.5)
        la = d[(d.indicator == "LaRSI") & (d.tf == "1H") & (d["filter"] == "F0")]
        kd, kv, n = count(la.net > 0, va.loc[la.index].net > 0, len(la))
        add(5, "on 1H LaRSI on its own mostly did not make money (net > 0 in at most half)", s,
            "LaRSI 1H rows with F0", frac(kd, n), frac(kv, n), n > 0 and not _most(kd, n), n > 0 and not _most(kv, n))
        share = {w: {tf: float((x[(x.indicator == "LaRSI") & (x.tf == tf)].net > 0).mean()) for tf in TFS}
                 for w, x in (("dev", d), ("val", va))}
        add(5, "4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H)", s,
            "LaRSI rows, share with net > 0 per timeframe",
            ", ".join(f"{tf} {share['dev'][tf]:.0%}" for tf in TFS), ", ".join(f"{tf} {share['val'][tf]:.0%}" for tf in TFS),
            share["dev"]["4H"] > share["dev"]["1H"] and share["dev"]["1D"] > share["dev"]["1H"],
            share["val"]["4H"] > share["val"]["1H"] and share["val"]["1D"] > share["val"]["1H"])
        for name, fl in (("TSI > 0 (F3)", ("F3",)), ("MA200 (F1, F2)", MA200_FILTERS)):
            g = f[(f.indicator == "LaRSI") & f["filter"].isin(fl)]
            kd, kv, n = count(g.dev_win_net, g.val_win_net, len(g))
            add(5, f"pair LaRSI with a trend filter: {name} beats no filter in most pairs", s,
                f"LaRSI with {name} against F0 (DEVIATIONS 30)", frac(kd, n), frac(kv, n), _most(kd, n), _most(kv, n))
        # 6. all four best on 4H and 1D; on 1H even the best struggled
        four = {w: x[x.indicator.isin(FOUR)] for w, x in (("dev", d), ("val", va))}
        share = {w: {tf: float((x[x.tf == tf].net > 0).mean()) for tf in TFS} for w, x in four.items()}
        add(6, "the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0)", s,
            "the four's rows" + (" (with the RV rows)" if has_rv(s) else "") + ", share with net > 0 per timeframe",
            ", ".join(f"{tf} {share['dev'][tf]:.0%}" for tf in TFS), ", ".join(f"{tf} {share['val'][tf]:.0%}" for tf in TFS),
            share["dev"]["1H"] < min(share["dev"]["4H"], share["dev"]["1D"]),
            share["val"]["1H"] < min(share["val"]["4H"], share["val"]["1D"]))
        best = {w: {tf: float(x[x.tf == tf].net.max()) for tf in TFS} for w, x in four.items()}
        add(6, "on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row)", s,
            "the four's best row by net, per timeframe",
            ", ".join(f"{tf} {_usd(best['dev'][tf])}" for tf in TFS), ", ".join(f"{tf} {_usd(best['val'][tf])}" for tf in TFS),
            best["dev"]["1H"] < min(best["dev"]["4H"], best["dev"]["1D"]),
            best["val"]["1H"] < min(best["val"]["4H"], best["val"]["1D"]))
    out = pd.DataFrame(rows)
    part = {p: i for i, p in enumerate(dict.fromkeys(out.part))}          # a part's place: where it first appears
    sym = {x: i for i, x in enumerate(("both",) + SYMBOLS)}
    out = out.assign(_p=out.part.map(part), _s=out.symbol.map(sym)).sort_values(["claim", "_p", "_s"], kind="stable")
    return out.drop(columns=["_p", "_s"]).reset_index(drop=True)


# ───────────────────────────── CANDIDATES.md ─────────────────────────────

def _usd(x) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return f"{x:+,.0f}" if abs(x) >= 10 else f"{x:+,.2f}"


def _dd(x) -> str:
    """A drawdown, in dollars, without a sign."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return f"{x:,.0f}" if abs(x) >= 10 else f"{x:,.2f}"


def _num(x, nd=2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return f"{x:.{nd}f}"


def _md(header: Sequence[str], body: Iterable[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def _short(vid: str) -> str:
    return "`" + "|".join(vid.split("|")[1:]) + "`"


WINDOW_NAME = {"dev": "Development", "val": "Validation", "devval": "D+V"}


def _yes(x) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return "yes" if bool(x) else "no"


def candidates_md(res: pd.DataFrame, qual: pd.DataFrame, vs: pd.DataFrame, summ: pd.DataFrame, mt: pd.DataFrame,
                  bh: pd.DataFrame, checks: pd.DataFrame, info: pd.DataFrame, vbh: pd.DataFrame,
                  rates: pd.DataFrame, ru: pd.DataFrame, cv: pd.DataFrame, vfs: pd.DataFrame,
                  cl: pd.DataFrame) -> str:
    syms = [s for s in SYMBOLS if s in set(res.symbol)]
    name = {"XAUUSDm": "Gold (XAUUSDm)", "BTCUSDm": "BTC (BTCUSDm)"}
    out = ["# TradeIQ's RSI replacements: the candidates after Development and Validation", "",
           f"Written by `python -B -m backtesting.research.tradeiq select` on "
           f"{pd.Timestamp.now(tz='UTC').strftime('%d %b %Y %H:%M')} UTC from the CSVs of `run` "
           f"(written {info.written_utc.iloc[0]}). **This is not `FINALISTS.md`.** Nothing is frozen, and no result of "
           "the hold-out (from 2024-07-01) exists: the guard of `tradeiq_market.py` served the data only up to "
           "2024-06-30 23:59 UTC. The would-be finalists below are what PREREG section 7's rule gives; they become "
           "finalists only when `FINALISTS.md` and its sha256 are written.", "",
           "Per 0.01 lot after Exness costs (spread at every fill, one extra spread on every stop fill). Development "
           "2019-01-01 to 2022-12-31, Validation 2023-01-01 to 2024-06-30, D+V the two together as one continuous "
           "run. Profit / DD = net profit / max drawdown. The rules are PREREG section 6 with DEVIATIONS 1-3, 6-7 and "
           "19-26; x1.5 scales the spread of every M1 bar (DEVIATIONS 27). The tables against buy-and-hold, of the "
           "filters, of the comparison curves and of the video's claims follow DEVIATIONS 28-31, which were written "
           "after the review of this run and before any result of the hold-out.", ""]
    # what was run
    rows = []
    for s in syms:
        g = res[(res.symbol == s) & (res.window == "dev")]
        i = info[info.symbol == s].iloc[0]
        rows.append([name[s], len(g), int((g.indicator == RV).sum()), f"{i.first_m1[:10]} .. {i.served_until[:16]}",
                     f"{int(i.m1_bars):,}", int(i.runs)])
    out += ["## What was run", "",
            _md(["Symbol", "Variants", "of them RV", "M1 data served", "M1 bars", "Runs (3 windows x 2 costs)"], rows),
            "", f"Total: {int(res[res.window == 'dev'].shape[0])} variants (DEVIATIONS 22). Code that wrote the CSVs "
            "(git blob ids): " + ", ".join(f"`{c[5:]}` {info[c].iloc[0][:12]}" for c in info.columns
                                           if c.startswith("blob ")) + ". "
            + ("It is the code in the working tree now." if all(info[k].iloc[0] == v for k, v in code_blobs().items())
               else "**It differs from the code in the working tree now** (see `run_info.csv`)."), ""]
    ck = checks.groupby("symbol")[["missing_total", "ties_total", "bars_read"]].sum()
    out += ["State checks (`state_checks.csv`): on the bars the windows read, "
            + "; ".join(f"{s} {int(ck.loc[s, 'bars_read']):,} bars, {int(ck.loc[s, 'missing_total'])} missing values, "
                        f"{int(ck.loc[s, 'ties_total'])} exact ties with a level" for s in syms) + ".", ""]
    # headline
    out += ["## Headline", ""]
    rows = []
    for s in syms:
        d, v = res[(res.symbol == s) & (res.window == "dev")], res[(res.symbol == s) & (res.window == "val")]
        qs = qual[qual.symbol == s]
        both = (d.set_index("vid").net > 0) & (v.set_index("vid").net > 0)
        rows.append([name[s], len(d), int((d.net > 0).sum()), int((v.net > 0).sum()), int(both.sum()),
                     int(qs.q1.sum()), int((qs.q1 & qs.q2).sum()), int((qs.q1 & qs.q2 & qs.q3).sum()),
                     int(qs.qualifies.sum()), int(qs.finalist.sum())])
    out += [_md(["Symbol", "Variants", "Dev net > 0 (x1.0)", "Val net > 0 (x1.0)", "Both > 0",
                 "Rule 1 (dev > 0 at x1.0 and x1.5)", "Rules 1-2", "Rules 1-3", "Qualify (rules 1-4)",
                 "Would-be finalists"], rows), ""]
    for s in syms:
        rows = []
        d, v = res[(res.symbol == s) & (res.window == "dev")], res[(res.symbol == s) & (res.window == "val")]
        for ind in ["RSI", "LaRSI", "VWRSI", RV, "TSI", "QQE", "MA200"]:
            dd, vv = d[d.indicator == ind], v[v.indicator == ind]
            if not len(dd):
                continue
            qq = qual[(qual.symbol == s) & (qual.indicator == ind)]
            rows.append([ind, len(dd), int((dd.net > 0).sum()), int((vv.net > 0).sum()), int(qq.qualifies.sum()),
                         _usd(float(dd.net.median())), _usd(float(vv.net.median())), _usd(float(dd.net.max())),
                         _usd(float(vv.net.max()))])
        out += [f"{name[s]} by indicator:", "",
                _md(["Indicator", "Variants", "Dev net > 0", "Val net > 0", "Qualify", "Median dev net",
                     "Median val net", "Best dev net", "Best val net"], rows), ""]
    for s in syms:
        rows = []
        d, v = res[(res.symbol == s) & (res.window == "dev")], res[(res.symbol == s) & (res.window == "val")]
        for tf in TFS:
            dd, vv = d[d.tf == tf], v[v.tf == tf]
            qq = qual[(qual.symbol == s) & (qual.tf == tf)]
            rows.append([tf, len(dd), int((dd.net > 0).sum()), int((vv.net > 0).sum()), int(qq.qualifies.sum()),
                         _usd(float(dd.net.median())), _usd(float(vv.net.median()))])
        out += [f"{name[s]} by timeframe:", "",
                _md(["TF", "Variants", "Dev net > 0", "Val net > 0", "Qualify", "Median dev net", "Median val net"],
                    rows), ""]
    # buy and hold
    rows = []
    for s in syms:
        for w in RUN_WINDOWS:
            b1 = bh[(bh.symbol == s) & (bh.window == w) & (bh.cost == 1.0)].iloc[0]
            b15 = bh[(bh.symbol == s) & (bh.window == w) & (bh.cost == 1.5)].iloc[0]
            rows.append([name[s], {"dev": "Development", "val": "Validation", "devval": "D+V"}[w], _usd(b1.bh_net),
                         _usd(b15.bh_net), _dd(b1.bh_max_dd), _num(b1.bh_profit_dd)])
    out += ["Buy-and-hold of 0.01 lot, for reference:", "",
            _md(["Symbol", "Window", "Net x1.0", "Net x1.5", "Max DD", "Profit / DD"], rows), ""]
    # qualifiers and finalists
    for s in syms:
        qs = qual[(qual.symbol == s) & qual.qualifies].sort_values("rank")
        out += [f"## {name[s]}: the qualifiers", ""]
        if not len(qs):
            out += ["**No variant qualifies.** The finalist rule gives no finalist: the answer is \"none\".", ""]
        else:
            out += [_md(["Rank", "Variant", "Dev net", "Dev x1.5", "Dev trades", "Dev P/DD", "Dev +Q", "Val net",
                         "Val P/DD", "D+V net", "D+V P/DD", "Would-be finalist"],
                        [[int(r["rank"]), _short(r.vid), _usd(r.dev_net), _usd(r.dev_net_x15), int(r.dev_trades),
                          _num(r.dev_profit_dd), f"{r.dev_pos_q_share:.0%}", _usd(r.val_net), _num(r.val_profit_dd),
                          _usd(r.devval_net), _num(r.devval_profit_dd), "**yes**" if r.finalist else ""]
                         for _, r in qs.iterrows()]), ""]
        fin = qs[qs.finalist]
        out += [f"### {name[s]}: who WOULD be the finalists", ""]
        if not len(fin):
            out += ["None.", ""]
        else:
            m = mt[mt.symbol == s].drop_duplicates("vid").set_index("vid")
            idx = res.set_index(["vid", "window"])
            rows = []
            for _, r in fin.iterrows():
                d, v, dv = idx.loc[(r.vid, "dev")], idx.loc[(r.vid, "val")], idx.loc[(r.vid, "devval")]
                rows.append([int(r["rank"]), _short(r.vid), r.group, _usd(d.net), _usd(d.net_x15), _dd(d.max_dd),
                             int(d.trades), f"{d.win_rate:.0f}%", _num(d.profit_factor), _num(d.sharpe_w),
                             _usd(v.net), _usd(v.net_x15), _dd(v.max_dd), int(v.trades), _usd(dv.net), _dd(dv.max_dd),
                             _num(dv.profit_dd), f"{d.time_in_mkt:.0%}", _num(d.avg_hold_h, 0),
                             _num(float(m.loc[r.vid, "dsr"]), 3) if r.vid in m.index else "-"])
            out += [_md(["#", "Variant", "Indicator", "Dev net", "Dev x1.5", "Dev DD", "Dev trades", "Dev win",
                         "Dev PF", "Dev Sharpe", "Val net", "Val x1.5", "Val DD", "Val trades", "D+V net", "D+V DD",
                         "D+V P/DD", "Dev time in mkt", "Dev hold (h)", "DSR"], rows), ""]
            # against buy-and-hold (DEVIATIONS 28)
            b = vbh[vbh.symbol == s]
            rows = [[int(r.n), _short(r.vid), WINDOW_NAME[r.window], _usd(r.net), _dd(r.max_dd), _num(r.profit_dd),
                     _yes(r.exam_rule), f"{r.time_in_mkt:.0%}", int(r.n_short), _usd(r.bh_net), _dd(r.bh_max_dd),
                     _num(r.bh_profit_dd), _usd(r.bh_exposure_matched_net), _yes(r.pdd_above_bh),
                     _yes(r.net_above_exposure_matched)] for _, r in b.iterrows()]
            n_long_only = int(b.groupby("vid").n_short.sum().eq(0).sum())
            out += [f"{name[s]}: the would-be finalists against buy-and-hold of the same span (x1.0, DEVIATIONS 28). "
                    f"{n_long_only} of the {b.vid.nunique()} never go short. \"Exam rule\" is PREREG 8's pass rule "
                    "(net > 0 and P/DD >= 0.5), applied here to these windows for information; \"exposure-matched\" "
                    "is the time in the market x buy-and-hold's net.", "",
                    _md(["#", "Variant", "Window", "Net", "Max DD", "P/DD", "Exam rule", "Time in mkt", "Shorts",
                         "B&H net", "B&H DD", "B&H P/DD", "Exposure-matched B&H", "P/DD above B&H",
                         "Net above exp.-matched"], rows), ""]
            # the indicators without a slot (R1-F3 of the review)
            r_ = ru[ru.symbol == s]
            if len(r_):
                last = r_.iloc[0]
                rows = [[r.indicator, _short(r.vid), int(r["rank"]), _usd(r.devval_net), _dd(r.devval_max_dd),
                         f"{r.devval_profit_dd:.4f}", f"{r.gap_profit_dd:.4f}", _usd(r.net_needed),
                         f"{r.devval_profit_dd_x15:.2f} / {r.last_finalist_profit_dd_x15:.2f}"] for _, r in r_.iterrows()]
                close = r_.sort_values("gap_profit_dd").iloc[0]
                out += [f"{name[s]}: the best qualifier of each indicator without a slot, against the third would-be "
                        f"finalist `{'|'.join(last.last_finalist.split('|')[1:])}` (rank {int(last.last_finalist_rank)}, "
                        f"D+V P/DD {last.last_finalist_profit_dd:.4f}). \"Net needed\": the D+V net at which, with its "
                        "own drawdown, it would have taken the slot.", "",
                        _md(["Indicator", "Best qualifier", "Rank", "D+V net", "D+V DD", "D+V P/DD", "Gap (P/DD)",
                             "Net needed", "D+V P/DD x1.5 (it / the third)"], rows), "",
                        f"The closest is the {close.indicator}: {_usd(close.net_needed)} more D+V net over 5.5 years "
                        f"({close.net_needed / close.devval_net:.2%} of its D+V net) would have given it the third "
                        "slot. The order of the slots is a selection rule, not a comparison: it is no evidence that "
                        f"the {last.last_finalist.split('|')[2]} is better than the {close.indicator}. The indicators "
                        "are compared in the RSI table and in the claims below.", ""]
        # the near misses: the best by D+V among those failing exactly one rule
        nq = qual[(qual.symbol == s) & ~qual.qualifies].copy()
        nq["fails"] = (~nq.q1).astype(int) + (~nq.q2).astype(int) + (~nq.q3).astype(int) + (~nq.q4).astype(int)
        nm = nq[nq.fails == 1].sort_values("devval_profit_dd", ascending=False).head(5)
        if len(nm):
            rows = [[_short(r.vid), ",".join(k for k in ("q1", "q2", "q3", "q4") if not r[k]), _usd(r.dev_net),
                     _usd(r.dev_net_x15), int(r.dev_trades), _num(r.dev_profit_dd), f"{r.dev_pos_q_share:.0%}",
                     _usd(r.val_net), _num(r.devval_profit_dd)] for _, r in nm.iterrows()]
            out += [f"{name[s]}: the five best by D+V profit / DD among the variants that fail exactly one rule "
                    "(for information; they are not candidates):", "",
                    _md(["Variant", "Fails", "Dev net", "Dev x1.5", "Dev trades", "Dev P/DD", "Dev +Q", "Val net",
                         "D+V P/DD"], rows), ""]
    # multiple testing
    out += ["## Multiple testing (Development weekly P/L, x1.0)", ""]
    rows = [[name[r.symbol], r.role, _short(r.vid), r.N, r.T_weeks, _num(r.sharpe_w_ann), _num(r.e_max_sr_ann),
             _num(r.dsr, 3), _num(r.e_max_sr_null_ann), _num(r.dsr_null, 3), _num(r.e_max_sr_within_tf_ann),
             _num(r.dsr_within_tf, 3), _num(r.spa_p, 3), _num(r.rc_p, 3)] for _, r in mt.iterrows()]
    sh = mt.drop_duplicates("symbol").set_index("symbol")
    dsr_cols = ("dsr", "dsr_null", "dsr_within_tf")

    def span(c):
        return f"{mt[c].min():.3f}-{mt[c].max():.3f}"
    none_apart = (all(float(mt[c].max()) < 0.95 for c in dsr_cols) and float(sh.spa_p.min()) > 0.05
                  and float(sh.rc_p.min()) > 0.05)
    out += [_md(["Symbol", "Role", "Variant", "N", "Weeks", "Sharpe (ann.)", "E[max] (as run)", "DSR (as run)",
                 "E[max] (null var.)", "DSR (null var.)", "E[max] (within-TF var.)", "DSR (within-TF var.)", "SPA p",
                 "Reality Check p"], rows), "",
            "DSR (deflated Sharpe ratio, Bailey and Lopez de Prado): the probability that the variant's true Sharpe "
            "ratio exceeds E[max], the expected best Sharpe ratio of N trials without skill, given its weekly Sharpe, "
            "skew and kurtosis over the weeks. E[max] needs the variance of the trials' Sharpe ratios: \"as run\" "
            "(DEVIATIONS 26) the spread of the N variants' Sharpe ratios; \"null var.\" the trials' Sharpe variance "
            "under no skill, 1 / (weeks - 1); \"within-TF var.\" (added after the run, on review) the spread around "
            "each timeframe's mean, pooled. The share of the spread that lies between the timeframes' means is "
            + ", ".join(f"{sh.loc[s, 'between_tf_share']:.0%} on {name[s]}" for s in sh.index)
            + " (on BTC the costs make most 1H rows lose, which widens the spread and raises the as-run E[max]). "
            "SPA / Reality Check: the p-value of \"no variant of the symbol beats staying flat\", over all N variants "
            "at once (DEVIATIONS 26).", "",
            f"Over the rows above: DSR {span('dsr')} as run, {span('dsr_null')} with the null variance and "
            f"{span('dsr_within_tf')} with the within-timeframe variance; SPA p "
            + " / ".join(f"{sh.loc[s, 'spa_p']:.3f}" for s in sh.index) + " and Reality Check p "
            + " / ".join(f"{sh.loc[s, 'rc_p']:.3f}" for s in sh.index) + " (" + " / ".join(name[s] for s in sh.index)
            + "). "
            + ("By none of these figures can a Development Sharpe ratio be told apart from the best of N trials "
               "without skill (a DSR of 0.95 and a p-value of 0.05 are common bars in the literature). "
               if none_apart else "")
            + "The plan sets no threshold for them: under PREREG 7 they are information, and the would-be finalists "
            "go to the exam as the rule selects them.", ""]
    # vs RSI
    out += ["## Against the plain RSI (PREREG 7, question 1)", "",
            "Each oscillator's variant against the RSI variant with the same family (R1, R2, R4), filter, stop, "
            "timeframe and symbol. Wins = strictly better (DEVIATIONS 25).", ""]
    s1 = summ[summ.by == "indicator"]
    rows = [[name[r.symbol], r.indicator, r.n, f"{r.dev_wins_net}", f"{r.dev_wins_pdd} / {r.dev_n_pdd}",
             f"{r.val_wins_net}", f"{r.val_wins_pdd} / {r.val_n_pdd}", f"{r.dev_fewer_trades}",
             _num(r.dev_median_trades_ratio)] for _, r in s1.iterrows()]
    out += [_md(["Symbol", "Indicator", "Pairs", "Dev wins (net)", "Dev wins (P/DD)", "Val wins (net)",
                 "Val wins (P/DD)", "Dev fewer trades", "Dev median trades / RSI's"], rows), ""]
    s2 = summ[summ.by == "indicator+tf"]
    rows = [[name[r.symbol], r.indicator, r.tf, r.n, r.dev_wins_net, r.dev_wins_pdd, r.val_wins_net, r.val_wins_pdd]
            for _, r in s2.iterrows()]
    out += ["By timeframe:", "", _md(["Symbol", "Indicator", "TF", "Pairs", "Dev wins (net)", "Dev wins (P/DD)",
                                      "Val wins (net)", "Val wins (P/DD)"], rows), ""]
    # the exam's rule on Development and Validation (DEVIATIONS 28)
    n_fin = int(vbh.vid.nunique())
    n_lo = int(vbh.groupby("vid").n_short.sum().eq(0).sum())
    out += ["## PREREG 8's pass rule on Development and Validation (DEVIATIONS 28)", "",
            "How many rows would pass the exam's rule (net > 0 at x1.0 and profit / max drawdown >= 0.5) on the windows "
            "already run. The rule is the exam's and stays; this table shows how often it is met by rows that only "
            f"hold longs (the R2 rows; {n_lo} of the {n_fin} would-be finalists never go short) and by buy-and-hold.",
            ""]
    rows = []
    for s in syms:
        for w in RUN_WINDOWS:
            g = rates[(rates.symbol == s) & (rates.window == w)].set_index("rows")
            rows.append([name[s], WINDOW_NAME[w]] + [f"{int(g.loc[k, 'pass'])}/{int(g.loc[k, 'n'])} "
                                                     f"({g.loc[k, 'share']:.0%})" for k in
                                                     ("R2 rows (long only)", "other rows", "qualifiers")]
                        + [_yes(g.loc["buy-and-hold", "pass"])])
    out += [_md(["Symbol", "Window", "R2 rows (long only)", "Other rows", "Qualifiers", "Buy-and-hold"], rows), ""]
    # question 2 (DEVIATIONS 30)
    out += ["## Question 2: the filters against no filter (DEVIATIONS 30)", "",
            "Each filtered R1 / R2 / R3 variant against the same variant with F0 (the TSI's F3 rows, equal to its F0 "
            "rows, are left out). Wins = strictly better. F1 = MA200 on the signal timeframe, F2-4H / F2-1D = MA200 on "
            "the 4H / 1D chart (the owner's idea), F3 = TSI > 0. \"Helps\": more than half of the pairs won on net and "
            "on P/DD in both windows; \"does not help\": at most half on both in both; otherwise \"mixed\".", ""]
    g1 = vfs[vfs.by == "filter"]
    rows = [[name[r.symbol], r["filter"], int(r.n), r.dev_wins_net, f"{r.dev_wins_pdd} / {r.dev_n_pdd}", r.val_wins_net,
             f"{r.val_wins_pdd} / {r.val_n_pdd}", f"**{r.verdict}**"] for _, r in g1.iterrows()]
    out += [_md(["Symbol", "Filter", "Pairs", "Dev wins (net)", "Dev wins (P/DD)", "Val wins (net)", "Val wins (P/DD)",
                 "Verdict"], rows), "", "By timeframe:", ""]
    g2 = vfs[vfs.by == "filter+tf"]
    rows = [[name[r.symbol], r["filter"], r.tf, int(r.n), r.dev_wins_net, r.dev_wins_pdd, r.val_wins_net,
             r.val_wins_pdd, r.verdict] for _, r in g2.iterrows()]
    out += [_md(["Symbol", "Filter", "TF", "Pairs", "Dev wins (net)", "Dev wins (P/DD)", "Val wins (net)",
                 "Val wins (P/DD)", "Verdict"], rows), ""]
    # section 8's curves (DEVIATIONS 29)
    out += ["## PREREG 8's account curves: the rows (DEVIATIONS 29)", "",
            "Chosen from Development and Validation only, before any hold-out result exists. The curves themselves "
            "(2019-01-01 to the data end, and the hold-out alone) are drawn after the exam.", ""]
    rows = []
    for s in syms:
        c = cv[cv.symbol == s]
        for vid, g in c.groupby("vid", sort=False):
            r = g.iloc[0]
            rows.append([name[s], "; ".join(g.role), _short(vid), _yes(r.qualifies),
                         int(r["rank"]) if r.qualifies else "-", _usd(r.devval_net), _dd(r.devval_max_dd),
                         _num(r.devval_profit_dd)])
    out += [_md(["Symbol", "Roles", "Variant", "Qualifies", "Rank", "D+V net", "D+V DD", "D+V P/DD"], rows), ""]
    # section 9's claims (DEVIATIONS 31)
    out += ["## PREREG 9: the evidence for the video's claims (DEVIATIONS 31)", "",
            "Each part of a claim on the rows it is about, per symbol, in Development and in Validation separately; "
            "it holds when it holds in both windows, does not hold when it fails in both, and is mixed otherwise. "
            "These are the counts the verdicts of `RESULTS.md` will rest on; the hold-out is added after the exam, "
            "for information.", ""]
    rows = [[int(r.claim), r.part, name.get(r.symbol, r.symbol), r.dev, r.val, f"**{r.verdict}**", r.note]
            for _, r in cl.iterrows()]
    out += [_md(["Claim", "Part", "Symbol", "Development", "Validation", "Verdict", "Note"], rows), ""]
    out += ["## Files", "",
            "`grid.csv`, `results_dev_val.csv` (one row per variant and window; `_x15` = x1.5 costs), "
            "`trades_dev_val.csv.gz`, `quarters_dev_val.csv`, `weekly_dev_val.csv.gz`, `buy_and_hold.csv`, "
            "`state_checks.csv`, `run_info.csv`, `qualification.csv`, `vs_rsi.csv`, `vs_rsi_summary.csv`, "
            "`multiple_testing.csv`, `vs_buy_and_hold.csv`, `exam_rule_rates.csv`, `runners_up.csv`, `curves.csv`, "
            "`vs_f0.csv`, `vs_f0_summary.csv`, `claims.csv`.", ""]
    return "\n".join(out)


def select(out: Path = STUDY_DIR, log=print) -> Dict[str, pd.DataFrame]:
    """``select``: the selection, the RSI comparison and the multiple testing from ``run``'s CSVs; CANDIDATES.md."""
    out = Path(out)
    if (out / "FINALISTS.md").exists():
        log("note: FINALISTS.md exists; select does not read or change it")
    res = read_results(out)
    weekly = pd.read_csv(out / "weekly_dev_val.csv.gz", float_precision="round_trip")
    bh = pd.read_csv(out / "buy_and_hold.csv", float_precision="round_trip")
    checks = pd.read_csv(out / "state_checks.csv")
    info = pd.read_csv(out / "run_info.csv")
    want = grid_frame([s for s in SYMBOLS if s in set(res.symbol)])
    for w in RUN_WINDOWS:
        got = res[res.window == w].vid.tolist()
        if got != want.vid.tolist():
            raise AssertionError(f"results_dev_val.csv: the {w} rows are not the grid")
    qual = qualification(res)
    vs = vs_rsi(res)
    summ = vs_rsi_summary(vs)
    mt = multiple_testing(res, weekly, qual)
    fin = [v for s in SYMBOLS for v in qual[(qual.symbol == s) & qual.finalist].sort_values("rank").vid]
    vbh = vs_buy_and_hold(res, bh, fin)
    rates = exam_rule_rates(res, bh, qual)
    ru = runners_up(qual, res)
    cv = curves(qual)
    vf = vs_f0(res)
    vfs = vs_f0_summary(vf)
    cl = claims(res, vs, vf)
    got = {"qualification": qual, "vs_rsi": vs, "vs_rsi_summary": summ, "multiple_testing": mt,
           "vs_buy_and_hold": vbh, "exam_rule_rates": rates, "runners_up": ru, "curves": cv, "vs_f0": vf,
           "vs_f0_summary": vfs, "claims": cl}
    for k, v in got.items():
        v.to_csv(out / f"{k}.csv", index=False)
    (out / "CANDIDATES.md").write_text(candidates_md(res, qual, vs, summ, mt, bh, checks, info, vbh, rates, ru, cv,
                                                     vfs, cl), encoding="utf-8")
    log(f"wrote {out / 'CANDIDATES.md'}")
    return got


# ───────────────────────────── PREREG 8: the freeze (DEVIATIONS 32) ─────────────────────────────

FINALISTS_MD = "FINALISTS.md"
EXAM_WINDOWS = ("holdout", "full")           # PREREG 3 and 8: computed only once FINALISTS.md is frozen
SYMBOL_NAME = {"XAUUSDm": "Gold (XAUUSDm)", "BTCUSDm": "BTC (BTCUSDm)"}
TF_TEXT = {"1H": "1-hour", "4H": "4-hour", "1D": "daily"}
LINE_TEXT = {"RSI": "RSI(14) of the close", "LaRSI": "100 x Laguerre RSI (alpha 0.2) of the close",
             "VWRSI": "volume-weighted RSI (AlgoAlpha, 14) on the bar's tick volume",
             RV: "volume-weighted RSI (AlgoAlpha, 14) on Binance BTCUSDT spot volume",
             "TSI": "Bjorgum TSI x 100 (speed Fast: 5 / 25)"}
FILTER_TEXT = {"F0": "no filter",
               "F1": "a long only while the bar closed above its 200-bar SMA, a short only below it",
               "F2-4H": "a long only while the last CLOSED 4-hour bar closed above its 200-bar SMA, a short only below it",
               "F2-1D": "a long only while the last CLOSED daily bar closed above its 200-bar SMA, a short only below it",
               "F3": "a long only while the TSI (5 / 25) of the bar is above 0, a short only below it"}
STOP_TEXT = {"S0": "no stop: exits by the rule only",
             "S1": "a stop 3 x ATR(14) of the signal timeframe from the entry fill, never moved (one extra spread on a "
                   "stop fill); after a stop, flat until the state changes"}


def rule_text(vid: str) -> str:
    """A variant's rule row in words (PREREG 6, DEVIATIONS 19-21)."""
    v = Variant.of(vid)
    if v.indicator == "QQE":
        fam = {"R1": "long after a BLUE bar and short after a RED bar, held through GRAY bars (stop-and-reverse)",
               "R2": "long after a BLUE bar, held through GRAY bars, flat after a RED bar (long only)",
               "R3": "long on a BLUE bar, short on a RED bar, flat on a GRAY bar",
               "CTL-WHITE": "long when the white line crosses above 0, short when it crosses below (stop-and-reverse)"
               }[v.family]
        fam = ("QQE MOD (RSI 6, smoothing 5, factors 3.0 / 1.61, threshold 3, Bollinger 50 x 0.35): " + fam
               + "; BLUE = secondary RSI - 50 > 3 and primary RSI - 50 above the upper band, RED the mirror, GRAY "
                 "neither")
    elif v.indicator == "MA200":
        fam = {"R1": "long while the close is above its 200-bar SMA, short while below (stop-and-reverse)",
               "R2": "long while the close is above its 200-bar SMA, flat while below (long only)"}[v.family]
    elif v.family == "CTL-SIGNAL":
        fam = (f"{LINE_TEXT['TSI']}: long when it crosses above its signal line (EMA 14), short when it crosses "
               "below (stop-and-reverse)")
    else:
        line, mid = LINE_TEXT[v.indicator], MIDDLE[v.indicator]
        if v.family == "R1":
            fam = f"long while the {line} is above {mid:g}, short while below (stop-and-reverse)"
        elif v.family == "R2":
            fam = f"long while the {line} is above {mid:g}, flat while below (long only)"
        elif v.family == "R3":
            fam = (f"flat while the consolidation score (length 10) of the {line} is above 0; otherwise long while "
                   "the line is above 50, short while below")
        else:
            lo, hi = LEVELS[v.indicator]
            fam = (f"{line}: long when it crosses up through {lo:g}, short when it crosses down through {hi:g}, "
                   "held in between (stop-and-reverse)")
    return (f"{TF_TEXT[v.tf]} bars of the bid (UTC); {fam}; filter: {FILTER_TEXT[v.filt]}; stop: {STOP_TEXT[v.stop]}. "
            "Decided at the bar's close, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid).")


def git_blobs(files: Sequence[str] = CODE_FILES) -> Dict[str, str]:
    """``git hash-object`` of the code files (a read-only git command: nothing is written to the repository)."""
    import subprocess
    got = subprocess.run(["git", "hash-object", "--", *files], cwd=REPO_ROOT, capture_output=True, text=True,
                         check=True).stdout.split()
    if len(got) != len(files):
        raise RuntimeError(f"git hash-object printed {len(got)} ids for {len(files)} files")
    return {"blob " + f.split("/")[-1]: h for f, h in zip(files, got)}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finalists_of(qual: pd.DataFrame) -> List[str]:
    """PREREG 7's finalists, symbol by symbol (gold first), in rank order."""
    return [v for s in SYMBOLS for v in qual[(qual.symbol == s) & qual.finalist].sort_values("rank").vid]


def finalists_md(res: pd.DataFrame, qual: pd.DataFrame, info: pd.DataFrame, blobs: Dict[str, str],
                 inputs: Dict[str, str]) -> str:
    """FINALISTS.md: the finalists of PREREG 7, their rule rows, their Development and Validation numbers, the code."""
    fins = finalists_of(qual)
    idx = res.set_index(["vid", "window"])
    q = qual.set_index("vid")
    syms = [s for s in SYMBOLS if s in set(qual.symbol)]
    out = ["# TradeIQ's RSI replacements: the finalists (frozen)", "",
           f"Written by `python -B -m backtesting.research.tradeiq freeze` on "
           f"{pd.Timestamp.now(tz='UTC').strftime('%d %b %Y %H:%M')} UTC. Until this file and its sha256 "
           "(`FINALISTS.md.sha256`) existed, the guard of `tradeiq_market.py` served no data from 2024-07-01 00:00 UTC "
           "on, so no result of the hold-out existed when the finalists below were chosen. The file is written once: "
           "`freeze` refuses to write it again, and the guard closes the hold-out again if its sha256 stops matching.",
           "", "The rule (PREREG 7, DEVIATIONS 23-24): a variant qualifies when (1) its Development net profit is "
           "above 0 at x1.0 and at x1.5 costs, (2) it has at least 30 Development trades (1H, 4H) or 15 (1D), (3) its "
           "Development profit / max drawdown is at least 1.0 with at least 50% of the quarters positive, and (4) its "
           "Validation net profit is above 0 at x1.0. The finalists of a symbol are its three qualifiers with the "
           "highest profit / max drawdown over Development + Validation together (one continuous run, 2019-01-01 to "
           "2024-06-30, x1.0), at most one per indicator (RSI, LaRSI, VWRSI with its Binance-volume rows, TSI, QQE, "
           "MA200 alone); ties by Development's profit / max drawdown, then by the id. The finalists were recomputed "
           "from `results_dev_val.csv` by this command and are those of `qualification.csv` and `CANDIDATES.md`.", "",
           "## The finalists", "",
           "The exam (`python -B -m backtesting.research.tradeiq exam`) reads its variants from this block, one id "
           "per line (symbol | timeframe | indicator | family | filter | stop):", "", "```text"]
    out += fins + ["```", ""]
    for s in syms:
        fs = [v for v in fins if Variant.of(v).symbol == s]
        n_q = int(qual[(qual.symbol == s)].qualifies.sum())
        out += [f"### {SYMBOL_NAME[s]}: {len(fs)} finalist{'s' if len(fs) != 1 else ''} ({n_q} qualifiers)", ""]
        if not fs:
            out += ["**No variant qualifies: there is no finalist on this symbol, and the answer is \"none\".**", ""]
            continue
        rows = []
        for j, vid in enumerate(fs, 1):
            v = Variant.of(vid)
            rows.append([j, int(q.loc[vid, "rank"]), f"`{vid}`", v.group, v.tf, v.family, v.filt, v.stop])
        out += [_md(["#", "Rank", "Variant", "Indicator", "TF", "Family", "Filter", "Stop"], rows), ""]
        out += ["The rule rows:", ""]
        out += [f"{j}. `{vid}`: {rule_text(vid)}" for j, vid in enumerate(fs, 1)] + [""]
        rows = []
        for j, vid in enumerate(fs, 1):
            d, va, dv = idx.loc[(vid, "dev")], idx.loc[(vid, "val")], idx.loc[(vid, "devval")]
            rows.append([j, _short(vid), _usd(d.net), _usd(d.net_x15), int(d.trades), _dd(d.max_dd),
                         _num(d.profit_dd), f"{int(d.pos_q)}/{int(d.n_q)}", f"{d.win_rate:.0f}%",
                         _num(d.profit_factor), _num(d.sharpe_w), f"{d.time_in_mkt:.0%}"])
        out += ["Development, 2019-01-01 to 2022-12-31 (per 0.01 lot after costs):", "",
                _md(["#", "Variant", "Net x1.0", "Net x1.5", "Trades", "Max DD", "Profit / DD", "Positive quarters",
                     "Win rate", "Profit factor", "Weekly Sharpe (ann.)", "Time in market"], rows), ""]
        rows = []
        for j, vid in enumerate(fs, 1):
            va, dv = idx.loc[(vid, "val")], idx.loc[(vid, "devval")]
            rows.append([j, _short(vid), _usd(va.net), _usd(va.net_x15), int(va.trades), _dd(va.max_dd),
                         _num(va.profit_dd), f"{int(va.pos_q)}/{int(va.n_q)}", _usd(dv.net), _dd(dv.max_dd),
                         f"{dv.profit_dd:.4f}"])
        out += ["Validation, 2023-01-01 to 2024-06-30, and Development + Validation as one run:", "",
                _md(["#", "Variant", "Val net x1.0", "Val net x1.5", "Val trades", "Val max DD", "Val profit / DD",
                     "Val positive quarters", "D+V net", "D+V max DD", "D+V profit / DD (the ranking)"], rows), ""]
    a = {s: TM.window("holdout", s) for s in syms}
    out += ["## The exam (PREREG 8)", "",
            "Each finalist is run over the hold-out, " + "; ".join(
                f"{SYMBOL_NAME[s]} {a[s][0]} 00:00 to {a[s][1]} 00:00 UTC (exclusive)" for s in syms)
            + " (the data end, `DATA.md`), as one continuous run that starts flat at its first bar (DEVIATIONS 2, 7), "
              "at x1.0 and x1.5 costs. **It passes when its hold-out net profit is above 0 at x1.0 and its profit / max "
              "drawdown is at least 0.5** (DEVIATIONS 33). The result is reported next to buy-and-hold of 0.01 lot "
              "over the same span (DEVIATIONS 28).", "",
            "## The selection's inputs and the code", "",
            "The sha256 of the files the finalists were read from:", "",
            _md(["File", "sha256"], [[f"`{k}`", f"`{v}`"] for k, v in inputs.items()]), "",
            f"The code (git blob ids, `git hash-object`). `run_info.csv` records the code that wrote "
            f"`results_dev_val.csv` (written {info.written_utc.iloc[0]}): it is the code below, and it is the code "
            "that computes the hold-out.", "", "```text"]
    out += [f"{k} {v}" for k, v in blobs.items()] + ["```", ""]
    rows = [[name[5:], f"`{v}`", "yes" if all(info[name] == v) else "**no**"] for name, v in blobs.items()]
    out += [_md(["File", "Blob id now", "Equal to run_info.csv"], rows), ""]
    return "\n".join(out)


def read_frozen(out: Path = STUDY_DIR) -> Tuple[List[str], Dict[str, str]]:
    """The finalists' ids and the code's blob ids from FINALISTS.md's ``text`` blocks."""
    text = (Path(out) / FINALISTS_MD).read_text(encoding="utf-8")
    vids, blobs, inside = [], {}, False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = line.strip() == "```text"
            continue
        s = line.strip()
        if not inside or not s:
            continue
        if s.startswith("blob "):
            _, f, h = s.split()
            blobs["blob " + f] = h
        else:
            vids.append(Variant.of(s).vid)
    return vids, blobs


def _require_frozen(out: Path) -> None:
    """The hold-out is computed only into the study folder whose FINALISTS.md the guard reads, and only once it is
    frozen (``tradeiq_market.finalists_frozen``)."""
    if Path(out).resolve() != Path(TM.STUDY_DIR).resolve():
        raise ValueError(f"{out}: the hold-out is written only to the study folder the guard reads ({TM.STUDY_DIR})")
    if not TM.finalists_frozen():
        raise TM.HoldOutError(f"{Path(out) / FINALISTS_MD} with a matching sha256 does not exist: run `freeze` first")


def freeze(out: Path = STUDY_DIR, log=print) -> Path:
    """
    PREREG 8: FINALISTS.md (the finalists of PREREG 7, their rule rows, their Development and Validation numbers, the
    code's git blob ids) and its sha256, from ``run``'s and ``select``'s files. Refuses to write it a second time, and
    refuses when the code differs from the code that wrote ``results_dev_val.csv`` (``run_info.csv``) or when the
    selection on disk is not the one the results give.
    """
    out = Path(out)
    f, h = out / FINALISTS_MD, out / (FINALISTS_MD + ".sha256")
    if f.exists() or h.exists():
        raise FileExistsError(f"{f} exists: FINALISTS.md is written once and never again")
    res = read_results(out)
    want = grid_frame([s for s in SYMBOLS if s in set(res.symbol)])
    for w in RUN_WINDOWS:
        if res[res.window == w].vid.tolist() != want.vid.tolist():
            raise AssertionError(f"results_dev_val.csv: the {w} rows are not the grid")
    qual = qualification(res)
    disk = pd.read_csv(out / "qualification.csv")
    a = qual[qual.finalist].sort_values(["symbol", "rank"])[["vid", "rank"]].reset_index(drop=True)
    b = disk[disk.finalist].sort_values(["symbol", "rank"])[["vid", "rank"]].reset_index(drop=True)
    if not (a.vid.tolist() == b.vid.tolist() and np.array_equal(a["rank"].to_numpy(), b["rank"].to_numpy())
            and qual.qualifies.tolist() == disk.qualifies.tolist()):
        raise AssertionError("qualification.csv is not the selection results_dev_val.csv gives: run `select` first")
    info = pd.read_csv(out / "run_info.csv")
    blobs = code_blobs()
    if git_blobs() != blobs:
        raise AssertionError("git hash-object and blob_id disagree")
    stale = [k for k, v in blobs.items() if not (info[k] == v).all()]
    if stale:
        raise RuntimeError(f"{', '.join(k[5:] for k in stale)} differ from the code that wrote results_dev_val.csv "
                           "(run_info.csv): run `run` and `select` with this code first")
    inputs = {n: sha256_of(out / n) for n in ("results_dev_val.csv", "qualification.csv", "run_info.csv",
                                               "CANDIDATES.md")}
    text = finalists_md(res, qual, info, blobs, inputs)
    f.write_text(text, encoding="utf-8")
    h.write_text(f"{sha256_of(f)}  {FINALISTS_MD}\n", encoding="utf-8")
    if read_frozen(out) != (finalists_of(qual), blobs):
        raise AssertionError("FINALISTS.md does not read back as written")
    if Path(out).resolve() == Path(TM.STUDY_DIR).resolve() and not TM.finalists_frozen():
        raise AssertionError("the guard does not see FINALISTS.md as frozen")
    log(f"wrote {f} and {h.name} (sha256 {sha256_of(f)})")
    return f


# ───────────────────────────── PREREG 8: the exam (DEVIATIONS 33-34) ─────────────────────────────

def run_window(study: Study, v: Variant, window: str, cost: float = 1.0) -> TM.Run:
    """One variant over any window of ``tradeiq_market.WINDOWS``: ``run_variant``'s execution, and also the hold-out
    and the full span (2019-01-01 to the data end), which the guard serves only once FINALISTS.md is frozen."""
    if window not in TM.WINDOWS:
        raise ValueError(f"{window}: not a window of tradeiq_market.WINDOWS")
    a, z = TM.window(window, v.symbol)
    stop = study.stops[v.tf] if v.stop == "S1" else None
    return TM.run(study.mk, study.bars[v.tf], study.state(v), a, z, stop=stop, cost=cost)


def window_rows(study: Study, variants: Sequence[Variant], windows: Sequence[str],
                trades_windows: Sequence[str] = (), log=print) -> Tuple[List[dict], List[pd.DataFrame]]:
    """``run_symbol``'s rows (one per variant and window: the scores at x1.0, and with ``_x15`` at x1.5, in its column
    order) for any windows, and the trades of the windows in ``trades_windows`` at both costs."""
    t0 = time.time()
    rows, trd = [], []
    for n, v in enumerate(variants):
        for w in windows:
            row: Dict[str, object] = {**v.ident(), "window": w}
            for cost in COSTS:
                r = run_window(study, v, w, cost)
                row.update({k + _suffix(cost): val for k, val in scores(r).items()})
                row["start"], row["end"] = r.start, r.end
                if w in trades_windows:
                    tr = r.trades.drop(columns=["entry_ix", "exit_ix"])
                    tr.insert(0, "cost", cost)
                    tr.insert(0, "window", w)
                    tr.insert(0, "vid", v.vid)
                    trd.append(tr)
            rows.append(row)
        if (n + 1) % 50 == 0 or n + 1 == len(variants):
            log(f"  {study.symbol}: {n + 1} / {len(variants)} variants ({time.time() - t0:.0f} s)")
    return rows, trd


def _market_info(mk: TM.TMarket, t0: float) -> Dict[str, object]:
    return {"symbol": mk.symbol, "m1_bars": int(len(mk)), "first_m1": str(TM.utc(mk.t[0])),
            "last_m1": str(TM.utc(mk.t[-1])), "served_until": str(TM.utc(mk.end_s)),
            "seconds": round(time.time() - t0, 1)}


def exam(out: Path = STUDY_DIR, log=print) -> pd.DataFrame:
    """
    PREREG 8's exam: every finalist of FINALISTS.md over the hold-out at x1.0 and x1.5; the verdict (net > 0 at x1.0
    and profit / max drawdown >= 0.5, DEVIATIONS 33); buy-and-hold of 0.01 lot over the same span next to it
    (DEVIATIONS 28). Writes exam.csv, exam_trades.csv, exam_buy_and_hold.csv, exam_info.csv and EXAM.md.
    """
    out = Path(out)
    _require_frozen(out)
    vids, frozen = read_frozen(out)
    qual = qualification(read_results(out))
    if vids != finalists_of(qual):
        raise AssertionError("FINALISTS.md's finalists are not those results_dev_val.csv gives")
    code = code_blobs()
    rows, trd, bh, info = [], [], [], []
    for s in SYMBOLS:
        vs = [Variant.of(v) for v in vids if Variant.of(v).symbol == s]
        if not vs:
            continue
        t0 = time.time()
        mk = TM.load(s)
        st = Study(mk)
        got, t_ = window_rows(st, vs, ("holdout",), ("holdout",), log)
        rows += got
        trd += t_
        a, z = TM.window("holdout", s)
        for cost in COSTS:
            bh.append({"symbol": s, "window": "holdout", "start": a, "end": z, "cost": cost,
                       **TM.buy_and_hold(mk, a, z, cost)})
        info.append(_market_info(mk, t0))
        del st, mk
    ex = pd.DataFrame(rows)
    q = qual.set_index("vid")
    ex.insert(ex.columns.get_loc("window") + 1, "rank", [int(q.loc[v, "rank"]) for v in ex.vid])
    ex["pass"] = exam_rule(ex.net, ex.profit_dd)
    ex["pass_x15"] = exam_rule(ex.net_x15, ex.profit_dd_x15)                   # for information
    bhf = pd.DataFrame(bh)
    vb = vs_buy_and_hold(ex, bhf, vids, windows=("holdout",))
    keep = ["bh_net", "bh_max_dd", "bh_profit_dd", "bh_exam_rule", "bh_exposure_matched_net", "pdd_above_bh",
            "net_above_exposure_matched"]
    ex = ex.merge(vb[["vid"] + keep], on="vid", how="left", validate="one_to_one")
    ex["edge_over_bh"] = ex["pass"] & (ex.pdd_above_bh == True)                # noqa: E712 (NaN is no)
    inf = pd.DataFrame(info)
    inf["written_utc"] = str(pd.Timestamp.now(tz="UTC").floor("s"))
    inf["finalists_sha256"] = sha256_of(out / FINALISTS_MD)
    for k, v in code.items():
        inf[k] = v
    inf["code_as_frozen"] = all(frozen.get(k) == v for k, v in code.items())
    ex.to_csv(out / "exam.csv", index=False)
    pd.concat(trd, ignore_index=True).to_csv(out / "exam_trades.csv", index=False)
    bhf.to_csv(out / "exam_buy_and_hold.csv", index=False)
    inf.to_csv(out / "exam_info.csv", index=False)
    (out / "EXAM.md").write_text(exam_md(out), encoding="utf-8")
    log(f"wrote {out / 'EXAM.md'}")
    return ex


def _pf(x) -> str:
    return "inf" if (isinstance(x, float) and math.isinf(x)) else _num(x)


def exam_md(out: Path = STUDY_DIR) -> str:
    """EXAM.md from exam.csv, exam_buy_and_hold.csv and exam_info.csv; with the information of every variant's
    hold-out (``holdout``'s files) once they exist."""
    out = Path(out)
    ex = pd.read_csv(out / "exam.csv", float_precision="round_trip")
    inf = pd.read_csv(out / "exam_info.csv")
    bh = pd.read_csv(out / "exam_buy_and_hold.csv", float_precision="round_trip")
    vids, frozen = read_frozen(out)
    syms = [s for s in SYMBOLS if s in set(ex.symbol)]
    i0 = inf.iloc[0]
    out_ = ["# TradeIQ's RSI replacements: the exam (PREREG 8)", "",
            f"The verdicts were computed by `python -B -m backtesting.research.tradeiq exam` on {i0.written_utc} "
            f"(UTC), after `FINALISTS.md` was frozen (sha256 `{i0.finalists_sha256}`). The code that computed them is "
            + ("the code FINALISTS.md records (git blob ids in `exam_info.csv`)." if bool(i0.code_as_frozen) else
               "**not** the code FINALISTS.md records: see `exam_info.csv` and DEVIATIONS.")
            + " Per 0.01 lot after Exness costs, over the hold-out: "
            + "; ".join(f"{SYMBOL_NAME[s]} {r.start} to {r.end} (exclusive)"
                        for s in syms for _, r in bh[(bh.symbol == s) & (bh.cost == 1.0)].iterrows())
            + ", one continuous run per finalist that starts flat at its first bar.", "",
            "**The rule (PREREG 8, DEVIATIONS 33): a finalist passes when its hold-out net profit is above 0 at x1.0 "
            "costs and its profit / max drawdown is at least 0.5.** x1.5 is reported for information.", ""]
    out_ += ["## The verdicts", ""]
    rows = []
    for _, r in ex.iterrows():
        rows.append([SYMBOL_NAME[r.symbol], _short(r.vid), int(r["rank"]), _usd(r.net), _usd(r.net_x15),
                     _dd(r.max_dd), _num(r.profit_dd), int(r.trades), f"{r.win_rate:.0f}%" if np.isfinite(r.win_rate)
                     else "-", _pf(r.profit_factor), f"{int(r.pos_q)}/{int(r.n_q)}", f"{r.time_in_mkt:.0%}",
                     "**PASS**" if r["pass"] else "**FAIL**"])
    out_ += [_md(["Symbol", "Finalist", "Rank", "Net x1.0", "Net x1.5", "Max DD", "Profit / DD", "Trades", "Win rate",
                  "Profit factor", "Positive quarters", "Time in market", "Verdict"], rows), ""]
    for s in syms:
        g = ex[ex.symbol == s]
        out_ += [f"{SYMBOL_NAME[s]}: {int(g['pass'].sum())} of {len(g)} finalists pass."]
    out_ += [""]
    out_ += ["## Against buy-and-hold of the same span (DEVIATIONS 28)", "",
             "Both markets rose over Development and Validation, and a long-only finalist can pass the rule by holding "
             "a rising market. So a pass counts as evidence of an edge over holding the market only if the finalist's "
             "hold-out profit / max drawdown is also above buy-and-hold's. \"Exposure-matched\" = the finalist's time in "
             "the market x buy-and-hold's net.", ""]
    rows = []
    for _, r in ex.iterrows():
        rows.append([SYMBOL_NAME[r.symbol], _short(r.vid), _usd(r.net), _dd(r.max_dd), _num(r.profit_dd),
                     int(r.n_short), f"{r.time_in_mkt:.0%}", _usd(r.bh_net), _dd(r.bh_max_dd), _num(r.bh_profit_dd),
                     _yes(r.bh_exam_rule), _usd(r.bh_exposure_matched_net), _yes(r.pdd_above_bh),
                     _yes(r.net_above_exposure_matched), "**yes**" if r.edge_over_bh else "no"])
    out_ += [_md(["Symbol", "Finalist", "Net", "Max DD", "Profit / DD", "Shorts", "Time in mkt", "B&H net", "B&H DD",
                  "B&H P/DD", "B&H meets the rule", "Exposure-matched B&H", "P/DD above B&H", "Net above exp.-matched",
                  "Pass AND P/DD above B&H"], rows), ""]
    out_ += ["In words:", ""]
    for _, r in ex.iterrows():
        what = "passes" if r["pass"] else "fails"
        why = (f"net {_usd(r.net)} (x1.5: {_usd(r.net_x15)}), max drawdown ${_dd(r.max_dd)}, profit / DD "
               f"{_num(r.profit_dd)}")
        if r["pass"]:
            tail = ("and its profit / DD is above buy-and-hold's "
                    f"({_num(r.bh_profit_dd)}): evidence of an edge over holding the market." if r.edge_over_bh else
                    f"but buy-and-hold of the same span did better on profit / DD ({_num(r.bh_profit_dd)}, net "
                    f"{_usd(r.bh_net)}): the pass does not tell its timing apart from the rise of the market.")
        else:
            tail = (f"Buy-and-hold of the same span: net {_usd(r.bh_net)}, profit / DD {_num(r.bh_profit_dd)}.")
        out_ += [f"- {SYMBOL_NAME[r.symbol]} `{'|'.join(r.vid.split('|')[1:])}` {what}: {why}; {tail}"]
    out_ += [""]
    extra = out / "holdout_checks.csv"
    if (out / "results_holdout.csv").exists() and extra.exists():
        out_ += exam_information_md(out, ex)
    else:
        out_ += ["## For information", "", "The hold-out of every variant (`results_holdout.csv`) is computed after "
                 "this exam (`python -B -m backtesting.research.tradeiq holdout`); its figures are added here then.", ""]
    out_ += ["## Files", "", "`exam.csv` (the finalists' hold-out scores at x1.0 and `_x15` at x1.5, the verdict, "
             "buy-and-hold), `exam_trades.csv` (their hold-out trades at both costs), `exam_buy_and_hold.csv`, "
             "`exam_info.csv` (the data served, the code's blob ids, FINALISTS.md's sha256)"
             + (", `results_holdout.csv`, `results_full.csv`, `trades_holdout.csv.gz`, `buy_and_hold_exam.csv`, "
                "`state_checks_full.csv`, `holdout_checks.csv`, `vs_rsi_holdout_summary.csv`, "
                "`vs_f0_holdout_summary.csv`, `exam_rule_rates_holdout.csv`." if extra.exists() else "."), ""]
    return "\n".join(out_)


# ───────────────────────────── PREREG 8: the hold-out of every variant, for information (DEVIATIONS 34) ─────────────

def as_two_windows(res: pd.DataFrame, first: str, second: str) -> pd.DataFrame:
    """The rows of windows ``first`` and ``second`` relabelled "dev" and "val", so that the comparisons written for
    Development and Validation (``vs_rsi``, ``vs_f0``, ``claims``) run unchanged on them."""
    a, b = res[res.window == first], res[res.window == second]
    if a.vid.tolist() != b.vid.tolist():
        raise ValueError(f"the {first} and {second} rows are not the same variants")
    return pd.concat([a.assign(window="dev"), b.assign(window="val")], ignore_index=True)


def holdout(out: Path = STUDY_DIR, log=print) -> Dict[str, pd.DataFrame]:
    """
    After the exam (PREREG 8): every variant over the hold-out and over the full span (2019-01-01 to the data end) at
    x1.0 and x1.5, for information; and, on the same load of the data, Development, Validation and D+V again, which must
    reproduce results_dev_val.csv byte for byte. Writes results_holdout.csv, results_full.csv,
    trades_holdout.csv.gz, buy_and_hold_exam.csv, state_checks_full.csv, holdout_checks.csv, the hold-out's
    comparisons, and EXAM.md again with them.
    """
    out = Path(out)
    _require_frozen(out)
    if not (out / "exam.csv").exists():
        raise FileNotFoundError("exam.csv: the finalists' exam comes first (PREREG 8)")
    parts: Dict[str, List[pd.DataFrame]] = {}
    for s in SYMBOLS:
        t0 = time.time()
        log(f"{s}: loading and running {len(grid(s))} variants x 5 windows x {len(COSTS)} costs")
        mk = TM.load(s)
        st = Study(mk)
        checks = st.checks()
        if (checks.missing_total > 0).any():
            raise AssertionError(f"{s}: lines without a value on bars the windows read:\n{checks.T}")
        rows, trd = window_rows(st, grid(s), RUN_WINDOWS + EXAM_WINDOWS, ("holdout",), log)
        for name, ws in (("check", RUN_WINDOWS), ("holdout", ("holdout",)), ("full", ("full",))):
            parts.setdefault(name, []).append(pd.DataFrame([r for r in rows if r["window"] in ws]))
        parts.setdefault("trades", []).append(pd.concat(trd, ignore_index=True))
        bh = []
        for w in EXAM_WINDOWS:
            a, z = TM.window(w, s)
            for cost in COSTS:
                bh.append({"symbol": s, "window": w, "start": a, "end": z, "cost": cost,
                           **TM.buy_and_hold(mk, a, z, cost)})
        parts.setdefault("bh", []).append(pd.DataFrame(bh))
        parts.setdefault("state_checks", []).append(checks)
        parts.setdefault("info", []).append(pd.DataFrame([_market_info(mk, t0)]))
        del st, mk
    got = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}
    # the reproduction of Development and Validation on the data to the data end
    again = got.pop("check").to_csv(index=False).encode("utf-8")
    same_dev_val = again == (out / "results_dev_val.csv").read_bytes()
    # the finalists' rows are the exam's
    ex = pd.read_csv(out / "exam.csv", float_precision="round_trip")
    ho = got["holdout"]
    base = [c for c in ho.columns]
    mine = pd.read_csv(io.StringIO(ho[ho.vid.isin(ex.vid)].to_csv(index=False)), float_precision="round_trip")
    mine = mine.set_index("vid").loc[ex.vid].reset_index()
    exam_same = bool(mine[base].equals(ex[base]))
    code = code_blobs()
    _, frozen = read_frozen(out)
    chk = pd.DataFrame([{"check": "dev, val and devval rerun on the data to the data end equal results_dev_val.csv "
                                  "byte for byte", "result": bool(same_dev_val)},
                        {"check": "the finalists' rows of results_holdout.csv equal exam.csv", "result": exam_same},
                        {"check": "the code is the code FINALISTS.md records",
                         "result": all(frozen.get(k) == v for k, v in code.items())},
                        {"check": "lines without a value on the bars the windows read, 2019 to the data end",
                         "result": int(got["state_checks"].missing_total.sum())},
                        {"check": "exact ties with a level on those bars (a tie is the flat state, DEVIATIONS 19)",
                         "result": int(got["state_checks"].ties_total.sum())}])
    info = got.pop("info")
    info["written_utc"] = str(pd.Timestamp.now(tz="UTC").floor("s"))
    for k, v in code.items():
        info[k] = v
    got["holdout"].to_csv(out / "results_holdout.csv", index=False)
    got["full"].to_csv(out / "results_full.csv", index=False)
    got["trades"].to_csv(out / "trades_holdout.csv.gz", index=False, compression=GZ)
    got["bh"].to_csv(out / "buy_and_hold_exam.csv", index=False)
    got["state_checks"].to_csv(out / "state_checks_full.csv", index=False)
    info.to_csv(out / "holdout_info.csv", index=False)
    # the hold-out's comparisons, for information (DEVIATIONS 28, 30, 34)
    qual = qualification(read_results(out))
    allr = pd.concat([got["holdout"], got["full"]], ignore_index=True)
    two = as_two_windows(allr, "holdout", "full")
    vsr = vs_rsi_summary(vs_rsi(two))
    vf0 = vs_f0_summary(vs_f0(two))
    ren = {c: c.replace("dev_", "holdout_").replace("val_", "full_") for c in set(vsr.columns) | set(vf0.columns)}
    vsr.rename(columns=ren).to_csv(out / "vs_rsi_holdout_summary.csv", index=False)
    vf0.drop(columns=["verdict"]).rename(columns=ren).to_csv(out / "vs_f0_holdout_summary.csv", index=False)
    exam_rule_rates(allr, got["bh"], qual, windows=EXAM_WINDOWS).to_csv(out / "exam_rule_rates_holdout.csv",
                                                                         index=False)
    chk.to_csv(out / "holdout_checks.csv", index=False)
    (out / "EXAM.md").write_text(exam_md(out), encoding="utf-8")
    if not (same_dev_val and exam_same):
        raise AssertionError(f"a check failed (holdout_checks.csv):\n{chk}")
    log(f"wrote {out / 'results_holdout.csv'}, {out / 'results_full.csv'} and EXAM.md")
    return got


def exam_information_md(out: Path, ex: pd.DataFrame) -> List[str]:
    """EXAM.md's information: every variant's hold-out (DEVIATIONS 28, 30, 34)."""
    rates = pd.read_csv(out / "exam_rule_rates_holdout.csv")
    vsr = pd.read_csv(out / "vs_rsi_holdout_summary.csv")
    vf0 = pd.read_csv(out / "vs_f0_holdout_summary.csv")
    chk = pd.read_csv(out / "holdout_checks.csv")
    ho = pd.read_csv(out / "results_holdout.csv", float_precision="round_trip")
    qual = pd.read_csv(out / "qualification.csv")
    syms = [s for s in SYMBOLS if s in set(ho.symbol)]
    o = ["## For information: every variant over the hold-out (DEVIATIONS 28, 30, 34)", "",
         "Computed after the verdicts above by `python -B -m backtesting.research.tradeiq holdout` (`results_holdout.csv`;"
         " `results_full.csv` holds every variant over 2019-01-01 to the data end). None of it changes a verdict.", "",
         "Checks (`holdout_checks.csv`):", ""]
    o += [_md(["Check", "Result"], [[r.check, r.result] for _, r in chk.iterrows()]), ""]
    o += ["PREREG 8's rule (net > 0 at x1.0 and profit / DD >= 0.5) over the hold-out and over the full span, by kind "
          "of row (R2 = long only, MA200 alone's included):", ""]
    rows = []
    for s in syms:
        for w in EXAM_WINDOWS:
            g = rates[(rates.symbol == s) & (rates.window == w)].set_index("rows")
            rows.append([SYMBOL_NAME[s], {"holdout": "Hold-out", "full": "Full span"}[w]]
                        + [f"{int(g.loc[k, 'pass'])}/{int(g.loc[k, 'n'])} ({g.loc[k, 'share']:.0%})"
                           for k in ("R2 rows (long only)", "other rows", "qualifiers", "all rows")]
                        + [_yes(g.loc["buy-and-hold", "pass"])])
    o += [_md(["Symbol", "Window", "R2 rows (long only)", "Other rows", "Qualifiers", "All rows", "Buy-and-hold"], rows),
          ""]
    rows = []
    for s in syms:
        h = ho[ho.symbol == s]
        qs = set(qual[(qual.symbol == s) & qual.qualifies].vid)
        hq = h[h.vid.isin(qs)]
        rows.append([SYMBOL_NAME[s], len(h), int((h.net > 0).sum()), _usd(float(h.net.median())),
                     len(hq), int((hq.net > 0).sum()), _usd(float(hq.net.median())), _usd(float(h.net.max()))])
    o += ["Hold-out net at x1.0, every variant and the qualifiers (a variant chosen by its hold-out result would be "
          "chosen on the exam's data, so none is named here; every row is in `results_holdout.csv`):", "",
          _md(["Symbol", "Variants", "Net > 0", "Median net", "Qualifiers", "Qualifiers net > 0",
               "Qualifiers median net", "Highest net"], rows), ""]
    s1 = vsr[vsr.by == "indicator"]
    rows = [[SYMBOL_NAME[r.symbol], r.indicator, int(r.n), f"{int(r.holdout_wins_net)}",
             f"{int(r.holdout_wins_pdd)} / {int(r.holdout_n_pdd)}", f"{int(r.full_wins_net)}",
             f"{int(r.full_wins_pdd)} / {int(r.full_n_pdd)}", _num(r.holdout_median_trades_ratio)]
            for _, r in s1.iterrows()]
    o += ["Question 1 in the hold-out: each oscillator's variant against the RSI variant of the same row (DEVIATIONS "
          "25; wins = strictly better):", "",
          _md(["Symbol", "Indicator", "Pairs", "Hold-out wins (net)", "Hold-out wins (P/DD)", "Full-span wins (net)",
               "Full-span wins (P/DD)", "Hold-out median trades / RSI's"], rows), ""]
    g1 = vf0[vf0.by == "filter"]
    rows = [[SYMBOL_NAME[r.symbol], r["filter"], int(r.n), int(r.holdout_wins_net),
             f"{int(r.holdout_wins_pdd)} / {int(r.holdout_n_pdd)}", int(r.full_wins_net),
             f"{int(r.full_wins_pdd)} / {int(r.full_n_pdd)}"] for _, r in g1.iterrows()]
    o += ["Question 2 in the hold-out: each filtered variant against the same variant without a filter (DEVIATIONS 30; "
          "F1 / F2-4H / F2-1D = the MA200 filters, F3 = TSI > 0):", "",
          _md(["Symbol", "Filter", "Pairs", "Hold-out wins (net)", "Hold-out wins (P/DD)", "Full-span wins (net)",
               "Full-span wins (P/DD)"], rows), ""]
    return o


# ───────────────────────────── PREREG 8: the account curves (DEVIATIONS 29, 35) ─────────────────────────────

BH = "buy-and-hold"
F10_END = "2026-11-13"                       # the end of final10's runs (final10.DATA_END): the bots' curves end there
X_ACCOUNT = 2000.0                           # external.ACCOUNT: the start of every account curve


def bh_vid(symbol: str) -> str:
    return f"{symbol}|{BH}"


def bh_run(mk: TM.TMarket, start, end, cost: float = 1.0) -> TM.Run:
    """Buy-and-hold of 0.01 lot (DEVIATIONS 6: bought at the ask at the window's first M1 open, sold at the bid at its
    last close) as a ``tradeiq_market.Run``, built as ``tradeiq_market.buy_and_hold`` builds it, so that the account and
    unit curves apply to it."""
    from . import external as X
    if not isinstance(mk, TM.TMarket) or mk.cost != 1.0:
        raise TypeError("bh_run() takes the TMarket itself")
    a_s, z_s, ia, iz = TM._window_ix(mk, start, end)
    cm = mk.costed(cost)
    plan = X.make_plan(cm, np.asarray([mk.t[ia]], np.int64), want=np.asarray([1]))
    p = X.run_path(cm, plan, ia, iz)
    ec, ew, pos, bal, maxdd = TM._unit_marks(cm.c, cm.h, cm.l, cm.sp, cm.k, p.dir, p.eix, p.xix, p.epx, p.xpx, p.why,
                                             ia, iz)
    return TM.Run(mk.symbol, BH, str(TM.utc(a_s)), str(TM.utc(z_s)), a_s, z_s, ia, iz, float(cost), False, cm, p,
                  TM._trades(cm, p), ec, ew, pos, float(bal), float(maxdd), 1)


def best_rsi_r1(qual: pd.DataFrame, symbol: str) -> str:
    """DEVIATIONS 35: the RSI's R1 row (the side of 50, both sides) first in PREREG 7's order (its qualifier with the
    highest D+V profit / max drawdown; with no qualifier, its row with the highest D+V profit / max drawdown; ties as
    DEVIATIONS 24). Chosen on Development and Validation only."""
    g = qual[(qual.symbol == symbol) & (qual.indicator == "RSI") & (qual.family == "R1")]
    ok = g[g.qualifies]
    if len(ok):
        return ok.sort_values("rank").vid.iloc[0]
    return g.assign(_a=-g.devval_profit_dd.fillna(-np.inf), _b=-g.dev_profit_dd.fillna(-np.inf),
                    _c=g.vid).sort_values(["_a", "_b", "_c"]).vid.iloc[0]


def curve_rows(out: Path = STUDY_DIR) -> pd.DataFrame:
    """PREREG 8's curves, per symbol: curves.csv's rows (DEVIATIONS 29: the finalists, the best variant of each
    indicator, MA200 alone's included, and each finalist's RSI baseline), recomputed and checked against the file; the
    RSI's best R1 row (DEVIATIONS 35); buy-and-hold of 0.01 lot."""
    qual = qualification(read_results(out))
    cv = curves(qual)
    disk = pd.read_csv(Path(out) / "curves.csv")
    if cv[["symbol", "role", "vid"]].values.tolist() != disk[["symbol", "role", "vid"]].values.tolist():
        raise AssertionError("curves.csv is not the selection results_dev_val.csv gives")
    rows = []
    for s in [x for x in SYMBOLS if x in set(cv.symbol)]:
        rows += [{"symbol": s, "role": r.role, "vid": r.vid} for _, r in cv[cv.symbol == s].iterrows()]
        rows.append({"symbol": s, "role": "best RSI R1 (DEVIATIONS 35)", "vid": best_rsi_r1(qual, s)})
        rows.append({"symbol": s, "role": "buy-and-hold of 0.01 lot", "vid": bh_vid(s)})
    return pd.DataFrame(rows)


def account_of(r: TM.Run):
    """``tradeiq_market.account_curve`` and the account behind it (``external.account`` on the same day edges), whose
    sized trades the summary needs."""
    from . import external as X
    curve, summ = TM.account_curve(r)
    e = TM._edges_days(r.a_s, r.z_s)
    bnd = np.concatenate([[r.ia], r.ia + np.searchsorted(r.m.t[r.ia:r.iz], e[1:-1], side="left"), [r.iz]])
    res = X.account(r.m, r.path, X.BOT, bnd.astype(np.int64))
    if not (np.array_equal(res.blocks, curve.equity.to_numpy()) and res.final == summ["final"]):
        raise AssertionError("the account differs from tradeiq_market.account_curve")
    return curve, summ, res


def daily_dd_pct(equity) -> float:
    """The largest fall of a daily equity series below its running peak, % of the peak."""
    e = np.asarray(equity, np.float64)
    peak = np.maximum.accumulate(e)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, (peak - e) / peak, 0.0)
    return float(dd.max() * 100.0) if len(e) else np.nan


def curve_metrics(time_s: np.ndarray, equity: np.ndarray, final: float, max_dd_pct: float, a_s: int, z_s: int,
                  pnl: np.ndarray, wiped: bool, wiped_at, common_end: str = F10_END) -> Dict[str, object]:
    """``final10.account_metrics`` on a daily curve (its last point is the end), the drawdown on the daily marks, and
    the same figures to ``common_end`` (the end of the bots' curves) where the curve reaches past it."""
    from . import final10 as F
    tm = pd.to_datetime(np.asarray(time_s, np.int64), unit="s", utc=True)
    daily = pd.Series(np.asarray(equity, np.float64)[:-1], index=tm[:-1])
    m = F.account_metrics(daily, float(final), float(max_dd_pct), int(a_s), int(z_s), np.asarray(pnl, np.float64),
                          bool(wiped), wiped_at)
    m["max_dd_daily_pct"] = round(daily_dd_pct(equity), 4)
    c = TM.s_of(common_end)
    k = np.flatnonzero(np.asarray(time_s) == c)
    if a_s < c <= z_s and len(k):
        e = np.asarray(equity, np.float64)[: k[0] + 1]
        yrs = (c - a_s) / F.YEAR_S
        m.update(common_end=common_end, equity_common=round(float(e[-1]), 2),
                 cagr_common_pct=round(((e[-1] / X_ACCOUNT) ** (1.0 / yrs) - 1.0) * 100.0, 4) if e[-1] > 0 else -100.0,
                 max_dd_daily_common_pct=round(daily_dd_pct(e), 4))
    return m



def account_curves(out: Path = STUDY_DIR, log=print) -> Dict[str, pd.DataFrame]:
    """
    PREREG 8's account curves (DEVIATIONS 29, 35) over the full span (2019-01-01 to the data end) and over the hold-out
    alone, at x1.0: a $2,000 account with the bot's unit rule (``tradeiq_market.account_curve``) and the same run per
    0.01 lot (``tradeiq_market.unit_curve``), equity at every UTC midnight. Writes curves_full.csv, curves_holdout.csv
    and the TradeIQ rows of curves_summary.csv.
    """
    out = Path(out)
    _require_frozen(out)
    rows = curve_rows(out)
    ref = {w: pd.read_csv(out / f"results_{w}.csv", float_precision="round_trip").set_index("vid")
           for w in EXAM_WINDOWS if (out / f"results_{w}.csv").exists()}
    curves_w: Dict[str, List[pd.DataFrame]] = {w: [] for w in EXAM_WINDOWS}
    summ = []
    for s in [x for x in SYMBOLS if x in set(rows.symbol)]:
        mk = TM.load(s)
        st = Study(mk)
        rs = rows[rows.symbol == s]
        for vid, g in rs.groupby("vid", sort=False):
            for w in EXAM_WINDOWS:
                if vid == bh_vid(s):
                    r = bh_run(mk, *TM.window(w, s))
                    b = TM.buy_and_hold(mk, *TM.window(w, s))
                    if not (r.net == b["bh_net"] and r.max_dd == b["bh_max_dd"]):
                        raise AssertionError("bh_run differs from tradeiq_market.buy_and_hold")
                else:
                    r = run_window(st, Variant.of(vid), w, 1.0)
                    if w in ref and not (r.net == ref[w].loc[vid, "net"] and r.max_dd == ref[w].loc[vid, "max_dd"]):
                        raise AssertionError(f"{vid} {w}: the run differs from results_{w}.csv")
                curve, cs, res = account_of(r)
                uc = TM.unit_curve(r)
                if not np.array_equal(uc.time.to_numpy(), curve.time.to_numpy()):
                    raise AssertionError("the account and unit curves have different days")
                curves_w[w].append(pd.DataFrame({"symbol": s, "vid": vid, "time": curve.time, "equity": curve.equity,
                                                 "unit_equity": uc.equity, "unit_worst": uc.worst}))
                ts = (curve.time.astype("int64") // 10**9).to_numpy(np.int64)
                m = curve_metrics(ts, curve.equity.to_numpy(), cs["final"], cs["max_dd_pct"], r.a_s, r.z_s,
                                  res.trades_pnl, cs["wiped"], TM.utc(res.wipe_t) if res.wiped else None)
                summ.append({"source": "TradeIQ study", "symbol": s, "name": vid.split("|", 1)[1], "vid": vid,
                             "roles": "; ".join(g.role), "window": w, "start": r.start, "end": r.end,
                             "max_dd_basis": "M1 worst marks", **m, "max_units": cs["max_units"],
                             "skipped_trades": int(cs["skipped"]), "unit_net": float(r.net),
                             "unit_max_dd": float(r.max_dd),
                             "unit_profit_dd": float(r.net / r.max_dd) if r.max_dd > 0 else np.nan})
            log(f"  {s} {vid}: full and hold-out accounts")
        del st, mk
    got = {f"curves_{w}": pd.concat(v, ignore_index=True) for w, v in curves_w.items()}
    got["summary"] = pd.DataFrame(summ)
    for w in EXAM_WINDOWS:
        got[f"curves_{w}"].to_csv(out / f"curves_{w}.csv", index=False)
    _write_summary(out, got["summary"], "TradeIQ study")
    log(f"wrote {out / 'curves_full.csv'}, {out / 'curves_holdout.csv'}")
    return got


def _write_summary(out: Path, part: pd.DataFrame, source: str) -> None:
    """curves_summary.csv holds the TradeIQ rows and the bots' rows; each step replaces its own."""
    p = Path(out) / "curves_summary.csv"
    old = pd.read_csv(p) if p.exists() else pd.DataFrame()
    if len(old):
        old = old[old.source != source]
    pd.concat([old, part], ignore_index=True).to_csv(p, index=False)


# ───────────────────────────── PREREG 8: the designs the bots run today (DEVIATIONS 36) ─────────────────────────────

FINAL10_DIR = REPO_ROOT / "backtest_results" / "final10"
# (symbol, label in final10's files, file group, name): gold V3-lite, Top 1, Top 2; BTC Top 2, Turtle System 2 + votes
BOT_DESIGNS = (("XAUUSDm", "V3-lite", "ticks", "V3-lite"), ("XAUUSDm", "Top 1", "ticks", "Top 1"),
               ("XAUUSDm", "Top 2", "ticks", "Top 2"), ("BTCUSDm", "Top 2", "ticks", "Top 2"),
               ("BTCUSDm", "Turtle [alt] + bot votes", "warm", "Turtle System 2 + bot votes"))
F10_RUNS = {"8y": ("2018-11-13", "2026-11-13"), "5y": ("2021-11-13", "2026-11-13")}     # final10.WINDOWS


@dataclass(frozen=True, eq=False)
class BotRun:
    """One of final10's runs of a design: its trades (sorted, none overlapping), their sizes in units of 0.01 lot per
    position, the daily equity samples and the final equity of its $2,000 account."""
    symbol: str
    label: str
    engine: str                 # "ticks" (the tick engine) or "warm" (external.py's M1 bars)
    window: str
    a_s: int
    z_s: int
    o: np.ndarray               # entry times, UTC s
    c: np.ndarray               # exit times
    pnl: np.ndarray             # USD of the run's account
    units: np.ndarray           # the run's size per position, in units of 0.01 lot
    eq_t: np.ndarray            # daily samples (UTC midnight of the day sampled)
    eq_v: np.ndarray
    final: float                # results.csv: the final equity (an open basket marked)


def _times_s(x) -> np.ndarray:
    return (pd.to_datetime(pd.Series(x), utc=True, format="ISO8601").astype("int64") // 10**9).to_numpy(np.int64)


def unit_rule(balance: float) -> int:
    """The bot's unit rule (PREREG 4): floor(balance / 2,500) + 1 units of 0.01 lot, at most 10."""
    from . import external as X
    return int(min(math.floor(balance / X.STEP_UP) + 1.0, float(X.UNIT_MAX)))


def bot_run(symbol: str, label: str, engine: str, window: str = "8y", f10: Path = FINAL10_DIR) -> BotRun:
    f10 = Path(f10)
    tr = pd.read_csv(f10 / f"trades_{symbol}_{engine}.csv.gz")
    tr = tr[(tr.label == label) & (tr.window == window)].reset_index(drop=True)
    eq = pd.read_csv(f10 / f"equity_{symbol}_{engine}.csv.gz")
    eq = eq[(eq.label == label) & (eq.window == window)].reset_index(drop=True)
    rs = pd.read_csv(f10 / "results.csv")
    r = rs[(rs.symbol == symbol) & (rs.label == label) & (rs.window == window)]
    if len(r) != 1 or not len(tr) or not len(eq):
        raise ValueError(f"final10: no single {window} run of {symbol} {label}")
    o, c = _times_s(tr.open_time), _times_s(tr.close_time)
    k = np.argsort(o, kind="stable")
    legs = tr.legs.to_numpy(np.float64)[k] if engine == "ticks" else 1.0
    u = tr.lots.to_numpy(np.float64)[k] / 0.01 / legs
    if not np.allclose(u, np.round(u), rtol=0, atol=1e-6):
        raise ValueError(f"{symbol} {label}: a size is not a whole number of units")
    a, z = F10_RUNS[window]
    t = _times_s(eq.time)
    if not np.all(np.diff(t) > 0):
        raise ValueError("the equity samples are not in order")
    return BotRun(symbol, label, engine, window, TM.s_of(a), TM.s_of(z), o[k], c[k], tr.pnl.to_numpy(np.float64)[k],
                  np.round(u).astype(np.int64), t, eq.equity.to_numpy(np.float64), float(r.final_equity.iloc[0]))


def bot_checks(b: BotRun) -> Dict[str, object]:
    """What the rebuild rests on, on the run itself: no two trades overlap; each trade's size is the unit rule on the
    balance the run had when it opened ($2,000 + the P/L of the trades closed before it); at a daily sample with no
    trade open over the day's 00:00, the sample is that balance."""
    bal = X_ACCOUNT + np.concatenate([[0.0], np.cumsum(b.pnl)])
    rule = np.asarray([unit_rule(x) for x in bal[:-1]])
    k = np.searchsorted(b.c, b.eq_t, side="left")
    j = np.searchsorted(b.o, b.eq_t, side="left") - 1
    span = (j >= 0) & (b.c[np.maximum(j, 0)] > b.eq_t)
    resid = b.eq_v - bal[k]
    return {"trades": int(len(b.o)), "overlapping_trades": int(np.sum(b.o[1:] < b.c[:-1])),
            "sizes_equal_unit_rule": int(np.sum(rule == b.units)),
            "samples": int(len(b.eq_t)), "samples_with_a_trade_open": int(span.sum()),
            "samples_flat_not_at_balance": int(np.sum(~span & (k < len(b.c)) & (np.abs(resid) > 1e-6))),
            "open_at_end_usd": round(float(b.final - bal[-1]), 4)}


def rebuild(b: BotRun, start, bal0: float = X_ACCOUNT) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """
    A fresh $2,000 account from ``start`` to the run's end on the run's trades (DEVIATIONS 36): the trades opened at or
    after ``start`` (one still open there is dropped: a fresh account starts flat); each sized by the unit rule on this
    account's balance when it opens, with the run's P/L per unit; at each of the run's daily samples, this account's
    balance plus the run's open P/L at the sample times this account's size over the run's; at the end, a basket the
    tick engine left open (marked, not closed) likewise. Also per unit (0.01 lot per position).
    """
    a_s, z_s = TM.s_of(start), b.z_s
    if not b.a_s <= a_s < z_s:
        raise ValueError(f"{start}: outside the run {TM.utc(b.a_s)} .. {TM.utc(b.z_s)}")
    q = b.pnl / b.units
    bal_run = X_ACCOUNT + np.concatenate([[0.0], np.cumsum(b.pnl)])
    open_end = b.final - bal_run[-1]
    has_end = b.engine == "ticks" and abs(open_end) >= 0.005
    u_run_end = unit_rule(bal_run[-1])
    keep = b.o >= a_s
    units = np.zeros(len(q), np.int64)
    pnl = np.zeros(len(q))
    bal = bal0
    for i in np.flatnonzero(keep):
        units[i] = unit_rule(bal)
        pnl[i] = units[i] * q[i]
        bal += pnl[i]
    u_end = unit_rule(bal) if has_end else 0
    final = bal + (open_end / u_run_end * u_end if has_end else 0.0)
    unit_final = float(q[keep].sum()) + (open_end / u_run_end if has_end else 0.0)
    cum = bal0 + np.concatenate([[0.0], np.cumsum(pnl)])
    cq = np.concatenate([[0.0], np.cumsum(np.where(keep, q, 0.0))])
    m = (b.eq_t > a_s) & (b.eq_t < z_s)
    T, E = b.eq_t[m], b.eq_v[m]
    k = np.searchsorted(b.c, T, side="left")                  # the trades closed before the sample
    resid = E - bal_run[k]                                     # the run's open P/L at the sample
    j = np.searchsorted(b.o, T, side="left") - 1               # the last trade opened before it
    jj = np.maximum(j, 0)
    span = (j >= 0) & (b.c[jj] > T)
    tail = (k == len(b.c)) & has_end                           # after the last closed trade: the basket open at the end
    ratio = np.where(span, np.where(keep[jj], units[jj] / b.units[jj], 0.0), np.where(tail, u_end / u_run_end, 0.0))
    per_unit = np.where(span, np.where(keep[jj], 1.0 / b.units[jj], 0.0), np.where(tail, 1.0 / u_run_end, 0.0))
    if np.any(~span & ~tail & (np.abs(resid) > 1e-6)):
        raise AssertionError(f"{b.symbol} {b.label}: an open P/L at a sample with no trade open")
    eq = np.concatenate([[bal0], cum[k] + resid * ratio, [final]])
    ueq = np.concatenate([[0.0], cq[k] + resid * per_unit, [unit_final]])
    times = np.concatenate([[a_s], T, [z_s]]).astype(np.int64)
    wiped = bool(np.any(eq <= 0.0))
    curve = pd.DataFrame({"time": pd.to_datetime(times, unit="s", utc=True), "equity": eq, "unit_equity": ueq})
    met = curve_metrics(times, eq, final, daily_dd_pct(eq), a_s, z_s, pnl[keep], wiped, None)
    met.update(max_units=int(units[keep].max()) if keep.any() else 0, unit_net=round(unit_final, 4),
               unit_max_dd=round(float(np.max(np.maximum.accumulate(ueq) - ueq)), 4),
               dropped_open_at_start=int(np.sum((b.o < a_s) & (b.c > a_s))), open_at_end=bool(has_end))
    return curve, met


def bot_curves(out: Path = STUDY_DIR, f10: Path = FINAL10_DIR, log=print) -> Dict[str, pd.DataFrame]:
    """
    The five designs the bots run today (PREREG 8, DEVIATIONS 36) on fresh $2,000 accounts with the unit rule from
    2019-01-01 and from 2024-07-01, rebuilt from final10's eight-year runs (they end on 2026-11-13); the rebuild checked
    on the runs themselves and against final10's own five-year accounts. Writes curves_bots_full.csv,
    curves_bots_holdout.csv, bots_check.csv and the bots' rows of curves_summary.csv.
    """
    out = Path(out)
    starts = {"full": TM.WINDOWS["full"][0], "holdout": TM.WINDOWS["holdout"][0]}
    curves_w: Dict[str, List[pd.DataFrame]] = {w: [] for w in starts}
    summ, checks = [], []
    for s, label, eng, name in BOT_DESIGNS:
        b8, b5 = bot_run(s, label, eng, "8y", f10), bot_run(s, label, eng, "5y", f10)
        c8, c5 = bot_checks(b8), bot_checks(b5)
        # the rebuild of the five-year account from the eight-year run, against the five-year run itself
        rb, rm = rebuild(b8, F10_RUNS["5y"][0])
        own = pd.Series(b5.eq_v, index=b5.eq_t)
        mine = pd.Series(rb.equity.to_numpy()[1:-1], index=(rb.time.astype("int64") // 10**9).to_numpy()[1:-1])
        both = own.index.intersection(mine.index)
        same_trades = int(np.sum(np.isin(b5.o, b8.o) & np.isin(b5.c, b8.c)))
        checks.append({"symbol": s, "design": name, "final10_label": label, "engine": eng,
                       **{f"run8y_{k}": v for k, v in c8.items()}, **{f"run5y_{k}": v for k, v in c5.items()},
                       "run5y_trades_also_in_run8y": same_trades,
                       "run5y_final": b5.final, "rebuilt5y_final": round(float(rb.equity.iloc[-1]), 2),
                       "rebuilt5y_minus_run5y": round(float(rb.equity.iloc[-1]) - b5.final, 2),
                       "daily_samples_compared": int(len(both)),
                       "daily_max_abs_diff": round(float(np.max(np.abs(own.loc[both] - mine.loc[both]))), 2)
                       if len(both) else np.nan,
                       "daily_samples_equal_to_the_cent": int(np.sum(np.abs(own.loc[both] - mine.loc[both]) < 0.005))})
        for w, a in starts.items():
            curve, met = rebuild(b8, a)
            curves_w[w].append(curve.assign(symbol=s, design=name)[["symbol", "design", "time", "equity",
                                                                    "unit_equity"]])
            summ.append({"source": "the bots' designs (final10)", "symbol": s, "name": name, "vid": f"{s}|{name}",
                         "roles": f"bot design (final10 '{label}', {'tick engine' if eng == 'ticks' else 'M1 bars'})",
                         "window": w, "start": str(TM.utc(TM.s_of(a))), "end": str(TM.utc(b8.z_s)),
                         "max_dd_basis": "daily marks", **met})
        log(f"  {s} {name}: rebuilt; five-year check {checks[-1]['rebuilt5y_minus_run5y']:+.2f}")
    got = {f"curves_bots_{w}": pd.concat(v, ignore_index=True) for w, v in curves_w.items()}
    got["bots_check"] = pd.DataFrame(checks)
    got["summary"] = pd.DataFrame(summ)
    for w in starts:
        got[f"curves_bots_{w}"].to_csv(out / f"curves_bots_{w}.csv", index=False)
    got["bots_check"].to_csv(out / "bots_check.csv", index=False)
    _write_summary(out, got["summary"], "the bots' designs (final10)")
    log(f"wrote {out / 'curves_bots_full.csv'}, {out / 'curves_bots_holdout.csv'}, {out / 'bots_check.csv'}")
    return got


# ───────────────────────────── PREREG 9: the claims on every window (DEVIATIONS 31, 37) ─────────────────────────────

def claims_on(res: pd.DataFrame, window: str) -> pd.DataFrame:
    """DEVIATIONS 31's evidence on one window, by ``claims`` itself: the window's rows stand in for both of its
    windows, so each part's count and test are those of Development and Validation, applied to this window."""
    two = as_two_windows(res, window, window)
    c = claims(two, vs_rsi(two), vs_f0(two))
    note = c.note.str.replace(r" \(dev\), .*$", "", regex=True)
    return pd.DataFrame({"claim": c.claim, "part": c.part, "symbol": c.symbol, window: c.dev,
                         f"{window}_ok": c.dev_ok, f"{window}_note": note})


def claims_all(out: Path = STUDY_DIR) -> pd.DataFrame:
    """claims.csv's verdicts (recomputed from results_dev_val.csv and checked against the file) with the hold-out's
    evidence beside them, for information (DEVIATIONS 37)."""
    out = Path(out)
    res = read_results(out)
    cl = claims(res, vs_rsi(res), vs_f0(res))
    disk = pd.read_csv(out / "claims.csv")
    if cl.verdict.tolist() != disk.verdict.tolist() or cl.part.tolist() != disk.part.tolist():
        raise AssertionError("claims.csv is not what results_dev_val.csv gives")
    ho = pd.read_csv(out / "results_holdout.csv", float_precision="round_trip")
    h = claims_on(ho, "holdout")
    m = cl.merge(h, on=["claim", "part", "symbol"], how="left", validate="one_to_one")
    if len(m) != len(cl):
        raise AssertionError("the claims of the hold-out do not line up")
    m["holdout_word"] = [("cannot be tested" if v == "cannot be tested" else
                          ("holds" if bool(ok) else "does not hold")) for v, ok in zip(m.verdict, m.holdout_ok)]
    return m


def claims_md(out: Path = STUDY_DIR) -> str:
    out = Path(out)
    m = claims_all(out)
    m.to_csv(out / "claims_all.csv", index=False)
    name = dict(SYMBOL_NAME, both="both")
    o = ["# TradeIQ's RSI replacements: the video's claims (PREREG 9)", "",
         f"Written by `python -B -m backtesting.research.tradeiq claims` on "
         f"{pd.Timestamp.now(tz='UTC').strftime('%d %b %Y %H:%M')} UTC. Each claim of the video is split into the parts "
         "it states; each part is counted on the rows it is about, per symbol (DEVIATIONS 31). **The verdict is "
         "DEVIATIONS 31's: a part holds on a symbol when it holds in Development and in Validation, does not hold when "
         "it fails in both, and is mixed otherwise.** The hold-out (2024-07-01 to the data end) is a third window the "
         "selection never saw; its counts, by the same code, are for information (DEVIATIONS 37) and do not change a "
         "verdict. \"Most\" = more than half; \"every\" = all; \"about half\" = a median trade ratio in [0.375, 0.625]; "
         "\"far fewer\" = a median ratio of at most 0.5; a win = strictly more net profit at x1.0 than the RSI variant of "
         "the same row. Per 0.01 lot after Exness costs.", "",
         "## The verdicts", ""]
    rows = []
    for _, r in m.iterrows():
        rows.append([int(r.claim), r.part, name.get(r.symbol, r.symbol), r.dev if isinstance(r.dev, str) else "",
                     r.val if isinstance(r.val, str) else "", f"**{r.verdict}**",
                     r.holdout if isinstance(r.holdout, str) else "", r.holdout_word,
                     "; ".join(x for x in (r.note if isinstance(r.note, str) else "",
                                           ("hold-out: " + r.holdout_note) if isinstance(r.holdout_note, str)
                                           and r.holdout_note and r.verdict != "cannot be tested" else "") if x)])
    o += [_md(["Claim", "Part", "Symbol", "Development", "Validation", "Verdict", "Hold-out (information)",
               "In the hold-out", "Note"], rows), ""]
    o += ["## In short", ""]
    claim_text = {1: "Half of 8 alternatives could not beat the RSI; these four did, on most markets.",
                  2: "QQE MOD takes fewer trades than the RSI on every market and timeframe, and beats it on most, with "
                     "shorter losing streaks.",
                  3: "TSI: the zero line works, the signal line is a coin flip; it beats the RSI on most markets with "
                     "about half the trades.",
                  4: "VWRSI: the trend rule (side of 50) beats the RSI on every crypto market and timeframe; its 20 / 80 "
                     "reversals are no better than the RSI's; it needs real volume (crypto), not tick volume.",
                  5: "Laguerre RSI: beats the RSI on most markets on every timeframe with far fewer trades; on 1H it "
                     "mostly still did not make money on its own; 4H and 1D are where it works; pair it with a trend "
                     "filter (TSI > 0 or MA200).",
                  6: "All four worked best on 4H and 1D; on 1H even the best struggled."}
    for c in sorted(m.claim.unique()):
        g = m[m.claim == c]
        o += [f"**Claim {int(c)}.** \"{claim_text[int(c)]}\"", ""]
        for _, r in g.iterrows():
            o += [f"- {r.part} ({name.get(r.symbol, r.symbol)}): **{r.verdict}**"
                  + ("" if r.verdict == "cannot be tested" else f"; in the hold-out: {r.holdout_word}")
                  + (f" ({r.note})" if r.verdict == "cannot be tested" and isinstance(r.note, str) else "") + "."]
        o += [""]
    counts = m[m.verdict != "cannot be tested"].groupby(["symbol", "verdict"]).size().unstack(fill_value=0)
    o += ["Count of the parts by verdict (DEVIATIONS 31):", "",
          _md(["Symbol", "holds", "does not hold", "mixed"],
              [[name[s], int(counts.loc[s].get("holds", 0)), int(counts.loc[s].get("does not hold", 0)),
                int(counts.loc[s].get("mixed", 0))] for s in SYMBOLS if s in counts.index]), "",
          f"Cannot be tested: {int((m.verdict == 'cannot be tested').sum())} part(s) (see the notes).", "",
          "## Files", "", "`claims.csv` (Development and Validation, written by `select`), `claims_all.csv` (the same "
          "with the hold-out's evidence), `results_dev_val.csv`, `results_holdout.csv`.", ""]
    return "\n".join(o)


def write_claims(out: Path = STUDY_DIR, log=print) -> Path:
    out = Path(out)
    _require_frozen(out)
    (out / "CLAIMS.md").write_text(claims_md(out), encoding="utf-8")
    log(f"wrote {out / 'CLAIMS.md'}")
    return out / "CLAIMS.md"


# ───────────────────────────── command line ─────────────────────────────

def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.tradeiq")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("grid", help="the variants of PREREG 6 (no data is read)")
    r = sub.add_parser("run", help="every variant over dev, val and dev+val at x1.0 and x1.5 -> CSVs")
    r.add_argument("--symbols", nargs="+", default=list(SYMBOLS), choices=SYMBOLS)
    r.add_argument("--out", type=Path, default=STUDY_DIR)
    s = sub.add_parser("select", help="PREREG 7's selection, the RSI comparison and the multiple testing")
    s.add_argument("--out", type=Path, default=STUDY_DIR)
    for cmd, what in (("freeze", "PREREG 8: write FINALISTS.md and its sha256 (once)"),
                      ("exam", "PREREG 8: the finalists over the hold-out -> exam.csv, EXAM.md"),
                      ("holdout", "every variant over the hold-out and the full span (information) -> results_*.csv"),
                      ("curves", "PREREG 8's $2,000 account curves and per-0.01-lot curves -> curves_*.csv"),
                      ("bots", "the bots' five designs rebuilt from final10 -> curves_bots_*.csv"),
                      ("claims", "PREREG 9's claims with the hold-out beside them -> CLAIMS.md")):
        c = sub.add_parser(cmd, help=what)
        c.add_argument("--out", type=Path, default=STUDY_DIR)
    args = ap.parse_args(argv)
    if args.cmd == "grid":
        g = grid_frame()
        print(g.groupby(["symbol", "tf"]).size().to_string())
        print(g.groupby(["symbol"]).size().to_string())
        print(f"total {len(g)} variants")
    elif args.cmd == "run":
        t0 = time.time()
        run_grid(args.symbols, args.out)
        print(f"run: {time.time() - t0:.0f} s")
    elif args.cmd == "select":
        select(args.out)
    elif args.cmd == "freeze":
        freeze(args.out)
    elif args.cmd == "exam":
        exam(args.out)
    elif args.cmd == "holdout":
        t0 = time.time()
        holdout(args.out)
        print(f"holdout: {time.time() - t0:.0f} s")
    elif args.cmd == "curves":
        account_curves(args.out)
    elif args.cmd == "bots":
        bot_curves(args.out)
    elif args.cmd == "claims":
        write_claims(args.out)


if __name__ == "__main__":
    main()
