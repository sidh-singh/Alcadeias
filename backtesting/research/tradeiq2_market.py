"""
TradeIQ's "9 best TradingView indicators going into 2027" (study 2): the data, the hold-out guard and the execution
harness that the nine rule modules are written against.

    python -B -m backtesting.research.tradeiq2_market spans                      # the store's span per symbol
    python -B -m backtesting.research.tradeiq2_market fetch-binance5 [--last-day 2026-11-26]
    python -B -m backtesting.research.tradeiq2_market check-binance5            # PREREG 2's check of the 5m klines

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen) with ``DEVIATIONS.md``; the data are in ``DATA.md``.
Study 1's harness (``tradeiq_market.py``) and ``external.py`` are imported, never edited: the bars, the plans, the
fills, the stops, the marks, the trades, the scores and the account are theirs. What this module adds:

* THE STUDY-2 GUARD (PREREG 3). Study 1's guard is open (its FINALISTS.md is frozen), so it protects nothing here.
  ``frozen()`` is True only when ``backtest_results/tradeiq_2027/FINALISTS.md`` and its ``.sha256`` exist and the hash
  matches. Until then nothing at or after 2024-07-01 00:00 UTC is loaded, served or scored (``_guard``), and no window
  that overlaps gold's Early window [2017-01-01, 2019-01-01) is scored. Always: gold is never scored before
  2017-01-01 (its 2016 bars are warm-up), BTC never before 2019-01-01, a claim market never before its Development
  start (USTECm 2020-07-01, EURUSDm and GBPUSDm 2019-01-01). Every violation raises ``HoldOutError`` (a subclass of
  study 1's). ``load`` serves the data up to the hold-out start only, so nothing after it is even in memory. Study 1's
  functions used here (``TMarket.tbars``, ``run``, ``metrics``, ...) keep calling study 1's guard as well; it is open
  because study 1's FINALISTS.md is frozen, and if that file were changed they would refuse the hold-out again.
* ``load(symbol, end=None)``: the M1 bid bars of XAUUSDm (from 2016-01-01 when all twelve 2016 months are in the store,
  else 2017-01-01), BTCUSDm (2018-01-01), USTECm (2020-06-01), EURUSDm and GBPUSDm (2017-11-01), as a ``TMarket2``, a
  study-1 ``TMarket`` whose ``tbars`` also serves 'M5', 'M15' (UTC boundaries, ``external.tf_bars``) and '1W' (ISO
  Monday-start weeks of the merged 1D bars). 1H, 4H and 1D are study 1's bars exactly. Volume = the sum of the M1 tick
  counts and the spread is tick-weighted, as ``TMarket.tbars``.
* The New York clock for chart bars (``ny_minute``, ``ny_date``, ``ny_weekday``, ``sh_day_key``, ``utc_of_ny``).
* BTC volume (PREREG 2): Binance BTCUSDT spot 5m klines on M5 and M15, study 1's 1h klines on 1H, 4H, 1D and 1W.
* The execution types (``Variant``, ``Entries``, ``Orders``, ``Leg``, ``Exec``, ``Context``) and ``run_exec``, which
  executes an ``Exec`` over one window on ``external.make_plan`` / ``external.run_path`` and returns a ``Run2`` (a
  study-1 ``Run``) that ``tradeiq_market.metrics``, ``weekly_pnl``, ``quarter_pnl`` and ``unit_curve`` accept;
  ``account_curve`` here also handles legs and lanes. ``run_variant`` scores a variant over named windows (PREREG 7).

How an Exec is executed (PREREG 4; DEVIATIONS 1-7 of study 1 hold unchanged)
---------------------------------------------------------------------------
* A decision is taken at the close of a signal bar and filled at the open of the first M1 bar at or after that close
  (``bars.ex``): a buy at the ask (bid + that M1 bar's mean spread), a sell at the bid. Every decision is stamped with
  its fill bar's open (study 1's DEVIATIONS 4). Stops are checked on every M1 bar; a gap through a stop fills at the
  open; one extra spread is charged on every stop fill (study 1's ``_stop_slippage``); a target is a limit touched
  inside an M1 bar; when one M1 bar touches both, the stop wins; a stop-entry order fills at max(level, ask at the
  open) for a buy and min(level, bid at the open) for a sell. These are ``external._path_kernel``'s rules.
* A STATE Exec with nothing but a per-bar stop distance is study 1's ``tradeiq_market.run``, called as it is. With
  overlays (targets, break-even, legs, extra exits, stop tightening) the same state is turned, per window, into the
  entries ``run`` would make (an entry where the state changes, and at the window's first bar; the exit where it
  changes again) and executed as below; the two are identical when there is no overlay (tests).
* EVENT Execs are executed one position at a time. Each candidate entry, in time order, is taken when the position is
  flat at its fill bar (after an exit at an M1 open a new position may fill at that same open; after an exit inside an
  M1 bar, from the next bar), else it is skipped ("busy"). The taken position is executed alone by
  ``external.run_path`` on a plan of its own rows: the entry, its stop tightenings and its first exit decision. So an
  exit decision can never close another trade (``_path_kernel`` closes whatever position is open).
* Absolute levels (PREREG 4, the kernel trap of the spec): a stop or target level L becomes a distance from the actual
  fill, |fill - L|; an entry whose fill is at or beyond its stop or any of its targets is dropped; a tightened stop is
  applied only below the bid (long) / above the ask (short) at the open of the M1 bar that executes it, otherwise it
  becomes a market exit at that open; the x1.5 run recomputes every fill, distance and comparison on its own spreads.
* Exits before a gap (``close_gap``, a flag per entry / order row; harness reading 15 of this study's DEVIATIONS). A
  row's own fixed exit decision, the close of bar xb (its ``exit_bar``; for an order the earlier of that and
  ``on_fill``'s, at the earliest the fill's bar), fills at the open of ``bars.ex[xb]``. When the market closes early
  that open is the reopen, and PREREG 6.5's "flat at the last chart-bar close at or before 16:55 New York" would be
  held over the break. With ``close_gap`` True, when that decision is what ends the position (no exit mask and no
  crossed tightening ends it first) and no M1 bar opens at the bar's close (``cm.t[bars.ex[xb]] > bars.tc[xb]``: an
  early close, a weekend, a data hole), the exit is booked at the close of the bar's last M1 bar, ``bars.i1[xb]``,
  instead: at the bid of that close for a long, the ask for a short, with no extra spread. It is the run of a position
  still open at a window's end (the position's run simply ends after that M1 bar, and ``external._path_kernel`` closes
  it at that close), so a stop or a target touched before the close wins, every leg still open ends there, the marks
  and the accounts hold the position through that M1 bar, and the next candidate may fill from the next M1 bar (the
  reopen) on. The trade row reads as a time exit: reason 'signal' (``X.WHY_SIGNAL``'s), exit time that M1 bar's close,
  ``exit_ix`` that bar. The path keeps ``X.WHY_END``, because every mark and account kernel (study 1's
  ``_unit_marks``, ``_sum_marks`` here, ``external._account_kernel``, ``balke._multi_kernel``, the driver's sizing)
  reads a signal exit as one at a bar's open, and the position is held through that bar. ``Run2.counts['close_gap']``
  counts the positions it closed. Not a gap: an M1 bar opening at the bar's close, and the end of the data held (no M1
  bar after the bar at all). A bar whose last M1 bar is past the window is closed by the window's end, as before.
  When an exit mask falls on the row's own exit bar, the row's own exit decides, so it is booked at the close too; a
  window end inside the gap after the own exit bar only renames that window-end exit 'signal' and counts it (the
  price and P/L are the same). Otherwise exit masks, tightenings and stops are unaffected; without a gap, or with the
  flag False, nothing changes. What it takes as known: whether an M1 bar opens at that close shows in the bars only
  at the reopen, and the booking takes it as known at the close. For gold's early closes that is the published
  trading schedule; a hole in the data (BTC's, and one gold session to 2024-06-30 missing the M1 bar at the flat
  bar's close) could not be known then.
* Legs (PREREG 4's partial exits): weights summing to 1, identical entries (an entry is taken when every leg is flat),
  each leg its own target or break-even. P/L is the weighted sum; the drawdown is measured on the summed M1 marks.
* Lanes (Session Hunter's presets): several single-position Execs whose results are summed; the account is
  ``balke``'s multi-position account kernel.

The API at a glance (what the rule modules use)
-----------------------------------------------
    mk = load(symbol)                        # TMarket2 to the hold-out start (to the data end once frozen)
    ctx = Context(mk)                        # ctx.bars(tf), ctx.atr(tf), ctx.volume(tf), ctx.ny(tf), ctx.allow(tf, F)
    ctx.get(module, tf, params, fn)          # the indicator cache, keyed by (module, symbol, tf, params)
    ex = state_exec(tf, state, stop=None, target_r=.., be_r=.., legs=.., exit_long=.., tighten_long=.., ...)
    ex = event_exec(tf, entries=entries(bar, side, stop_level=.., stop_dist=.., target_level=.., target_r=..,
                                        be_r=.., exit_bar=.., risk=.., tag=.., close_gap=..), legs=.., exit_long=..)
    ex = event_exec(tf, orders=orders(bar, until, buy=.., sell=.., buy_stop=.., sell_stop=.., buy_target=..,
                                      target_r=.., exit_bar=.., close_gap=..), on_fill=.., fill_long=.., ...)
    ex = lanes_exec([ex_a, ex_b, ...])
    r = run_exec(mk, ex, start, end, cost=1.0)       # a Run2; metrics(r), scores(r), r_stats(r), account_curve(r)
    res = run_variant(ctx, Variant(...), ex)         # rows per window (dev, val, devval) at x1.0 and x1.5
    htf_at(htf_bars, values, ltf_bars)               # the last CLOSED higher bar (htf_at_open: at the bar's open)
    window_span(name, symbol), WINDOWS, MIN_TRADES, ny_minute / ny_date / ny_weekday / sh_day_key / utc_of_ny

Times are ISO strings, Timestamps (UTC) or epoch seconds (int), as in study 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from ..config import REPO_ROOT, SYMBOLS as SPECS
from ..data import store
from . import external as X
from . import tradeiq_market as TM

s_of, utc = TM.s_of, TM.utc
DAY = 86400
WEEK = 7 * DAY
NY = X.NY

# ───────────────────────────── the study's symbols, spans and windows (PREREG 2, 3) ─────────────────────────────

GOLD, BTC = "XAUUSDm", "BTCUSDm"
SYMBOLS = (GOLD, BTC)
CLAIM_SYMBOLS = ("USTECm", "EURUSDm", "GBPUSDm")          # PREREG 8: information only
ALL_SYMBOLS = SYMBOLS + CLAIM_SYMBOLS
GOLD_EARLY_START = "2016-01-01"                           # used when all twelve 2016 months are in the store
DATA_START = {GOLD: "2017-01-01", BTC: "2018-01-01", "USTECm": "2020-06-01", "EURUSDm": "2017-11-01",
              "GBPUSDm": "2017-11-01"}
# the claim markets are not in the engine's config: their contracts (balke.INDEX_SPECS, multisymbol's FX specs)
CLAIM_CONTRACTS = {"USTECm": dict(contract_size=1.0, digits=2), "EURUSDm": dict(contract_size=100000.0, digits=5),
                   "GBPUSDm": dict(contract_size=100000.0, digits=5)}
# the data end: gold and BTC are study 1's (the store as refreshed on 28 Nov 2026); the claim markets end where their
# store ended when this module was written (their last tick's minute; DATA.md)
LAST_TICK = {**TM.LAST_TICK, "USTECm": "2026-11-13 21:54:59.935", "EURUSDm": "2026-11-15 23:59:53.426",
             "GBPUSDm": "2026-11-15 23:59:59.828"}
DATA_END = {**TM.DATA_END, "USTECm": "2026-11-13 21:55", "EURUSDm": "2026-11-16", "GBPUSDm": "2026-11-16"}
DATA_END_S = {k: s_of(v) for k, v in DATA_END.items()}
HOLDOUT_START = TM.HOLDOUT_START                           # 2024-07-01: the first instant of the hold-out
CUT_S = s_of(HOLDOUT_START)
EARLY = ("2017-01-01", "2019-01-01")                       # gold's Early window (exam 2)
EARLY_S = (s_of(EARLY[0]), s_of(EARLY[1]))
DEV_START = {GOLD: "2019-01-01", BTC: "2019-01-01", "USTECm": "2020-07-01", "EURUSDm": "2019-01-01",
             "GBPUSDm": "2019-01-01"}
# the first instant a window of the symbol may start at (always, frozen or not)
SCORE_FROM = {GOLD: EARLY[0], BTC: "2019-01-01", "USTECm": "2020-07-01", "EURUSDm": "2019-01-01",
              "GBPUSDm": "2019-01-01"}
SCORE_FROM_S = {k: s_of(v) for k, v in SCORE_FROM.items()}
# PREREG 3: (start, end) with end None = the symbol's data end; "dev" / "devval" / "full" start at DEV_START
WINDOWS: Dict[str, Tuple[Optional[str], Optional[str]]] = {
    "dev": (None, "2023-01-01"),
    "val": ("2023-01-01", HOLDOUT_START),
    "devval": (None, HOLDOUT_START),
    "holdout": (HOLDOUT_START, None),
    "full": (None, None),
    "early": EARLY,
}
WINDOW_NAMES = {"dev": "Development", "val": "Validation", "devval": "Development + Validation",
                "holdout": "Hold-out (exam 1)", "full": "Development start to the data end", "early": "Early (exam 2)"}
RUN_WINDOWS = ("dev", "val", "devval")                     # what is scored before FINALISTS.md is frozen
EXAM_WINDOWS = ("holdout", "full", "early")                # computed only once it is
COSTS = (1.0, 1.5)
TFS = ("M5", "M15", "1H", "4H", "1D", "1W")
TF_SECONDS = {"M5": 300, "M15": 900, "1H": 3600, "4H": 14400, "1D": DAY, "1W": WEEK}
MIN_TRADES = {"M5": 30, "M15": 30, "1H": 30, "4H": 30, "1D": 15}     # PREREG 5 (Development)
STUDY_DIR = REPO_ROOT / "backtest_results" / "tradeiq_2027"


def window_span(name: str, symbol: str) -> Tuple[str, str]:
    """(start, end) of a named window for ``symbol``, ISO strings, end exclusive (PREREG 3). 'early' is gold's only."""
    if name not in WINDOWS:
        raise ValueError(f"{name}: not a window of this study ({', '.join(WINDOWS)})")
    if symbol not in ALL_SYMBOLS:
        raise ValueError(f"{symbol}: not a symbol of this study")
    if name == "early" and symbol != GOLD:
        raise ValueError(f"the Early window is gold's only (PREREG 3), not {symbol}'s")
    a, z = WINDOWS[name]
    return (DEV_START[symbol] if a is None else a), (DATA_END[symbol] if z is None else z)


# ───────────────────────────── the study-2 guard (PREREG 3) ─────────────────────────────

class HoldOutError(TM.HoldOutError):
    """A request reached data or a window that study 2's plan keeps closed (PREREG 3): the hold-out or gold's Early
    window before FINALISTS.md is frozen, or a window before a symbol's first scored day."""


def frozen() -> bool:
    """True when STUDY_DIR/FINALISTS.md and FINALISTS.md.sha256 both exist and the hash matches (PREREG 7)."""
    f, h = Path(STUDY_DIR) / "FINALISTS.md", Path(STUDY_DIR) / "FINALISTS.md.sha256"
    try:
        body = f.read_bytes()
        want = h.read_text(encoding="utf-8").split()
    except OSError:
        return False
    return bool(want) and hashlib.sha256(body).hexdigest() == want[0].strip().lower()


def _guard(end_s, what: str) -> None:
    """
    THE hold-out check of study 2: every path that loads, serves or scores data calls it. ``end_s`` is the exclusive
    end (UTC s) of what the request touches (a minute opening at t touches [t, t + 60), a bar touches up to its close).
    Anything past HOLDOUT_START raises unless FINALISTS.md of STUDY_DIR is frozen.
    """
    end_s = int(end_s)
    if end_s > CUT_S and not frozen():
        raise HoldOutError(f"{what}: reaches {utc(end_s)}, past the hold-out start {HOLDOUT_START} 00:00 UTC, and "
                           f"{Path(STUDY_DIR) / 'FINALISTS.md'} with a matching sha256 does not exist")


def _score_guard(symbol: str, a_s, z_s, what: str) -> None:
    """
    The check before anything is scored on [a_s, z_s): ``_guard`` on its end; never before the symbol's first scored
    day (gold 2017-01-01: its 2016 bars are warm-up only; BTC 2019-01-01; the claim markets their Development start);
    for gold, no window overlapping the Early window [2017-01-01, 2019-01-01) until FINALISTS.md is frozen.
    """
    a_s, z_s = int(a_s), int(z_s)
    _guard(z_s, what)
    if symbol not in SCORE_FROM_S:
        raise ValueError(f"{symbol}: not a symbol of this study")
    if a_s < SCORE_FROM_S[symbol]:
        raise HoldOutError(f"{what}: {symbol} is never scored before {SCORE_FROM[symbol]} (PREREG 3); "
                           f"the window starts {utc(a_s)}")
    if symbol == GOLD and a_s < EARLY_S[1] and z_s > EARLY_S[0] and not frozen():
        raise HoldOutError(f"{what}: overlaps gold's Early window {EARLY[0]} .. {EARLY[1]}, which is scored only after "
                           f"{Path(STUDY_DIR) / 'FINALISTS.md'} is frozen (PREREG 3)")


# ───────────────────────────── the market and its bars ─────────────────────────────

def data_start(symbol: str, store_dir: Path = store.DEFAULT_STORE_DIR) -> str:
    """The first day ``load`` reads: gold from 2016-01-01 when all twelve 2016 months are in the store (PREREG 2's
    warm-up for the Early window), else 2017-01-01; the other symbols their DATA_START."""
    if symbol not in DATA_START:
        raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(ALL_SYMBOLS)})")
    if symbol == GOLD:
        months = set(store.available_months(symbol, store_dir))
        if all((2016, m) in months for m in range(1, 13)):
            return GOLD_EARLY_START
    return DATA_START[symbol]


class TMarket2(TM.TMarket):
    """
    Study 1's ``TMarket`` over study 2's span, also for the claim markets (whose contracts come from CLAIM_CONTRACTS,
    as ``balke.SpecMarket`` does). ``tbars`` adds 'M5', 'M15' and '1W'; '1H', '4H' and '1D' are study 1's bars, built by
    ``TMarket.tbars`` itself. Construction and every ``tbars`` call pass study 2's guard. ``costed(1.5)`` is study 1's
    cost copy (a plain ``TMarket`` sharing the arrays, with every M1 spread x1.5), used only for execution.
    """

    def __init__(self, symbol: str, m1: Dict[str, np.ndarray], end_s: Optional[int] = None):
        if symbol in CLAIM_CONTRACTS:
            spec = CLAIM_CONTRACTS[symbol]
            self.symbol = symbol
            self.k = spec["contract_size"] * 0.01
            self.tick = 10.0 ** (-spec["digits"])
            self.around_the_clock = False
            self.t = np.ascontiguousarray(m1["t"], np.int64)
            for name, key in (("o", "o"), ("h", "h"), ("l", "l"), ("c", "c"), ("sp", "spread_mean"), ("n", "n")):
                setattr(self, name, np.ascontiguousarray(m1[key], np.float64))
            self._bars, self._local = {}, {}
        elif symbol in SPECS:
            X.Market.__init__(self, symbol, m1)
        else:
            raise ValueError(f"{symbol}: not a symbol of this study ({', '.join(ALL_SYMBOLS)})")
        if len(self.t) == 0:
            raise ValueError(f"{symbol}: no M1 bars")
        if len(self.t) > 1 and not bool(np.all(np.diff(self.t) > 0)):
            raise ValueError(f"{symbol}: M1 times must increase")
        last = int(self.t[-1]) + 60
        self.end_s = last if end_s is None else int(end_s)
        if last > self.end_s:
            raise ValueError(f"{symbol}: M1 bars past the market's end {utc(self.end_s)}")
        _guard(last, f"{symbol} M1 bars")
        self.cost = 1.0
        self._tb: Dict[str, TM.TBars] = {}
        self._costed: Dict[float, TM.TMarket] = {}
        self._binance = None            # study 1's 1h klines (tradeiq_market.binance_volume)
        self._binance5 = None           # the 5m klines (binance_volume_5m)
        self._ones = None               # all-True stop-entry masks for external.run_path

    def tbars(self, tf: str) -> TM.TBars:
        """The bars of ``tf`` ('M5', 'M15', '1H', '4H', '1D' or '1W'); see the module docstring."""
        if self.cost != 1.0:
            raise ValueError("bars come from the market itself, not from a cost copy")
        _guard(int(self.t[-1]) + 60, f"{self.symbol} {tf} bars")
        if tf in TM.TFS:
            return TM.TMarket.tbars(self, tf)
        if tf not in self._tb:
            if tf in ("M5", "M15"):
                self._tb[tf] = self._tbars_of(self.bars(tf), tf)
            elif tf == "1W":
                self._tb[tf] = self._weeks()
            else:
                raise ValueError(f"{tf}: not a timeframe of this study ({', '.join(TFS)})")
        return self._tb[tf]

    def _tbars_of(self, b: X.Bars, tf: str) -> TM.TBars:
        """``TMarket.tbars``'s construction on external's bars ``b``: tick volume and tick-weighted spread."""
        if len(b) == 0:
            raise ValueError(f"{self.symbol}: no {tf} bars")
        if not (np.all(b.i0[1:] == b.i1[:-1] + 1) and np.all(b.i1 >= b.i0)):
            raise AssertionError(f"{self.symbol} {tf}: bars do not tile the M1 bars")
        top = int(b.i1[-1]) + 1
        vol = np.add.reduceat(self.n[:top], b.i0)
        spv = np.add.reduceat(self.sp[:top] * self.n[:top], b.i0)
        with np.errstate(divide="ignore", invalid="ignore"):
            spread = np.where(vol > 0, spv / vol, np.nan)
        return TM.TBars(self.symbol, tf, b.t, b.tc, b.i0, b.i1, b.ex, b.o, b.h, b.l, b.c, vol, spread,
                        (b.i1 - b.i0 + 1).astype(np.int64), b.tc <= self.end_s, self.t)

    def _weeks(self) -> TM.TBars:
        """
        PREREG 2's weekly bars: the ISO (Monday-start, UTC) weeks of the merged 1D bars. A 1D bar belongs to the week
        of its LAST UTC day (the day that ends at its close, tc - 1 s), so gold's Sunday session, merged into Monday's
        bar, opens the new week, and a short day merged into the next full day goes with that day. Open time = the
        first 1D bar's open, close time = the last 1D bar's close; OHLC, M1 span, tick volume and spread as for the
        other bars. A last week that the data end cuts before its ISO end (the next Monday 00:00 UTC) may still get
        days: its close time is that ISO end, so it is not complete and ``htf_at`` never reads it as closed. This is
        ``tradeiq2_ind_msd.weekly_bars`` exactly (the dashboard's weekly row; tests).
        """
        d = self.tbars("1D")
        last_day = (d.tc - 1) // DAY
        week = (last_day + 3) // 7                         # epoch day 0 is a Thursday: weeks counted from Mondays
        first = np.flatnonzero(np.diff(week, prepend=week[0] - 1) != 0)
        last = np.append(first[1:] - 1, len(week) - 1)
        i0, i1 = d.i0[first], d.i1[last]
        tc = d.tc[last].copy()
        iso_end = (int(week[first[-1]]) * 7 - 3) * DAY + WEEK
        if self.end_s < iso_end:
            tc[-1] = iso_end
        b = X.Bars(d.t[first].copy(), tc.copy(), i0.copy(), i1.copy(), d.o[first].copy(),
                   np.maximum.reduceat(d.h, first), np.minimum.reduceat(d.l, first), d.c[last].copy(),
                   np.searchsorted(self.t, tc, side="left").astype(np.int64))
        return self._tbars_of(b, "1W")

    def ones(self) -> np.ndarray:
        """An all-True mask over the M1 bars, shared by every plan of this market (``external.run_path``'s stop-entry
        masks; without it each call would allocate two). Never modify it."""
        if self._ones is None or len(self._ones) != len(self.t):
            self._ones = np.ones(len(self.t), np.bool_)
        return self._ones


def load(symbol: str, end=None, store_dir: Path = store.DEFAULT_STORE_DIR) -> TMarket2:
    """
    The M1 bars of ``symbol`` from ``data_start(symbol)`` to ``end`` (exclusive). ``end=None``: the symbol's data end
    once FINALISTS.md is frozen, until then the hold-out start. An explicit ``end`` past the hold-out start raises
    while the hold-out is closed (before anything is read); an ``end`` past the data end raises always.
    """
    start = data_start(symbol, store_dir)
    if end is None:
        end_s = DATA_END_S[symbol] if frozen() else min(CUT_S, DATA_END_S[symbol])
    else:
        end_s = s_of(end)
    if end_s > DATA_END_S[symbol]:
        raise ValueError(f"{symbol}: {utc(end_s)} is past the study's data end {DATA_END[symbol]} (DATA.md)")
    _guard(end_s, f"load {symbol} to {utc(end_s)}")
    m1 = store.load_m1(symbol, start, str(utc(end_s).tz_localize(None)), Path(store_dir))
    if not m1 or len(m1["t"]) == 0:
        raise FileNotFoundError(f"no M1 bars for {symbol} from {start} in the store "
                                f"(python -m backtesting data --symbols {symbol} ...)")
    mk = TMarket2(symbol, {"t": m1["t"], "o": m1["o"], "h": m1["h"], "l": m1["l"], "c": m1["c"],
                           "spread_mean": m1["spread_mean"], "n": m1["n"]}, end_s)
    if end_s == DATA_END_S[symbol] and Path(store_dir) == store.DEFAULT_STORE_DIR:
        span = store.data_span(symbol, store_dir)
        if span is None or span[1] < pd.Timestamp(LAST_TICK[symbol], tz="UTC"):
            raise ValueError(f"{symbol}: the store ends before the study's last tick {LAST_TICK[symbol]}")
    return mk


def htf_at(htf: TM.TBars, values, ltf: TM.TBars, default=np.nan) -> np.ndarray:
    """``values`` of the last higher-timeframe bar CLOSED at each lower bar's close: study 1's ``htf_at`` (PREREG 5:
    every filter and every higher-timeframe value)."""
    return TM.htf_at(htf, values, ltf, default)


def htf_at_open(htf: TM.TBars, values, ltf: TM.TBars, default=np.nan) -> np.ndarray:
    """``values`` of the last higher-timeframe bar closed at or before each lower bar's OPEN. PREREG 6.6's one
    exception: Session Hunter's 1H EMA200, ``request.security(..., ema[1], lookahead_on)``, is the EMA of the last 1H
    bar closed at or before the chart bar's open (a chart bar inside an hour reads the hour before it)."""
    return X.value_at(htf.tc, np.asarray(values, np.float64), ltf.t, default)


def atr14(bars: TM.TBars, n: int = 14) -> np.ndarray:
    """Pine ``ta.atr(n)`` (Wilder RMA seeded with an SMA) of the signal bars, as study 1's S1 reads it
    (``external.wilder_atr``; PREREG 5: ATR)."""
    return X.wilder_atr(bars.h, bars.l, bars.c, n)


# ───────────────────────────── the New York clock (PREREG 2) ─────────────────────────────

def ny_local(t) -> np.ndarray:
    """UTC epoch seconds -> New York wall-clock seconds (America/New_York, daylight saving; ``external.local_seconds``)."""
    return X.local_seconds(np.asarray(t, np.int64).ravel(), NY).reshape(np.shape(t))


def ny_minute(t) -> np.ndarray:
    """Minutes since New York midnight (0..1439) of each UTC instant ``t``. For chart bars pass the bars' OPEN times
    (``bars.t``): Pine's ``time`` is a bar's open."""
    return (ny_local(t) % DAY) // 60


def ny_date(t) -> np.ndarray:
    """The New York calendar date of each UTC instant ``t``, as an epoch day number (days since 1970-01-01)."""
    return ny_local(t) // DAY


def ny_weekday(t) -> np.ndarray:
    """The weekday of the New York date of ``t``: 0 = Monday ... 6 = Sunday."""
    return (ny_date(t) + 3) % 7


def sh_day_key(t) -> np.ndarray:
    """Session Hunter's day key ``dk``: the New York date of ``time + 4h`` (its l.127-140), an epoch day number. A
    trading day runs from 20:00 to 20:00 New York, so the Asia session belongs to the next day. Its weekday is
    ``(sh_day_key(t) + 3) % 7``."""
    return ny_date(np.asarray(t, np.int64) + 4 * 3600)


def utc_of_ny(ny_day, minute) -> np.ndarray:
    """The UTC epoch second of New York wall-clock ``minute`` (0..1439) on New York epoch day ``ny_day``; -1 where
    that wall-clock time does not exist or is ambiguous (the daylight-saving changes, at 02:00-03:00)."""
    d = np.asarray(ny_day, np.int64)
    mi = np.asarray(minute, np.int64)
    d, mi = np.broadcast_arrays(d, mi)
    return X.utc_of_local((d * DAY + mi * 60).ravel(), NY).reshape(d.shape)


# ───────────────────────────── BTC volume: Binance BTCUSDT spot (PREREG 2) ─────────────────────────────

BINANCE_PATH_5M = "klines/BTCUSDT/5m"
FIVE_MS = 300_000


def _binance_files_5m(last_day: str = TM.BINANCE_LAST_DAY, root: Path = TM.BINANCE_DIR
                      ) -> List[Tuple[str, int, int, str, Path]]:
    """(label, period start s, period end s, url, local path) of the 5m kline zips: monthly from 2018-01 up to the
    month before ``last_day``'s, then daily of that month up to ``last_day`` (study 1's layout for 1h)."""
    d_last = pd.Timestamp(last_day).date()
    out = []
    y, m = TM.BINANCE_FROM
    while (y, m) < (d_last.year, d_last.month):
        name = f"BTCUSDT-5m-{y:04d}-{m:02d}.zip"
        a = s_of(f"{y:04d}-{m:02d}-01")
        z = s_of(f"{y + (m == 12):04d}-{m % 12 + 1:02d}-01")
        out.append((f"{y:04d}-{m:02d}", a, z, f"{TM.BINANCE_URL}/monthly/{BINANCE_PATH_5M}/{name}",
                    Path(root) / "spot" / "monthly" / BINANCE_PATH_5M / name))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    d = date(d_last.year, d_last.month, 1)
    while d <= d_last:
        name = f"BTCUSDT-5m-{d.isoformat()}.zip"
        a = s_of(d.isoformat())
        out.append((d.isoformat(), a, a + DAY, f"{TM.BINANCE_URL}/daily/{BINANCE_PATH_5M}/{name}",
                    Path(root) / "spot" / "daily" / BINANCE_PATH_5M / name))
        d += timedelta(days=1)
    return out


def fetch_binance_5m(last_day: str = TM.BINANCE_LAST_DAY, root: Path = TM.BINANCE_DIR, force: bool = False,
                     log=print) -> pd.DataFrame:
    """
    Download every 5m kline zip of BTCUSDT spot from 2018-01 to ``last_day`` with its .CHECKSUM (sha256 verified)
    into ``root`` (the URL's layout), with study 1's ``_http`` (generic user agent, nothing identifying sent), and check
    each file's times (only the two time columns are read, so no price or volume of the hold-out is looked at): open
    times increasing and inside the file's period, distinct once floored to the 5-minute grid; counted, not refused:
    klines off the 5-minute grid and klines that do not close at the slot's last ms. Writes and returns the inventory.
    """
    rows = []
    for label, a, z, url, path in _binance_files_5m(last_day, root):
        path.parent.mkdir(parents=True, exist_ok=True)
        ck = path.with_name(path.name + ".CHECKSUM")
        got = "cached"
        if force or not TM._checksum_ok(path):
            want = TM._http(url + ".CHECKSUM").decode("utf-8")
            body = TM._http(url)
            if hashlib.sha256(body).hexdigest() != want.split()[0].lower():
                body = TM._http(url)
                if hashlib.sha256(body).hexdigest() != want.split()[0].lower():
                    raise IOError(f"{path.name}: sha256 does not match its CHECKSUM")
            part = path.with_name(path.name + ".part")
            part.write_bytes(body)
            part.replace(path)
            ck.write_text(want, encoding="utf-8")
            got = "downloaded"
        if not TM._checksum_ok(path):
            raise IOError(f"{path.name}: sha256 does not match its CHECKSUM")
        k = TM.read_klines(path, times_only=True)
        ot, ct = k["open_ms"], k["close_ms"]
        slot = (ot // FIVE_MS) * FIVE_MS
        ok = (bool(np.all(np.diff(ot) > 0)) and bool(np.all(np.diff(slot) > 0))
              and bool(np.all((ot >= a * 1000) & (ot < z * 1000))))
        rows.append({"file": path.name, "period": label, "status": got, "sha256_ok": True, "rows": int(len(ot)),
                     "expected_slots": int((z - a) // 300), "us_rows": int(k["us_rows"]), "times_ok": ok,
                     "off_grid": int((ot % FIVE_MS != 0).sum()), "short_close": int((ct != ot + FIVE_MS - 1).sum()),
                     "first": str(pd.Timestamp(int(ot[0]), unit="ms")) if len(ot) else "",
                     "last": str(pd.Timestamp(int(ot[-1]), unit="ms")) if len(ot) else ""})
        if got == "downloaded":
            log(f"  {path.name}: {len(ot)} klines, {'us' if k['us_rows'] else 'ms'} stamps, times {'ok' if ok else 'BAD'}")
    inv = pd.DataFrame(rows)
    Path(root).mkdir(parents=True, exist_ok=True)
    inv.to_csv(Path(root) / "BTCUSDT_5m_inventory.csv", index=False)
    return inv


def load_binance_5m(end=None, start=None, root: Path = TM.BINANCE_DIR,
                    last_day: str = TM.BINANCE_LAST_DAY) -> Dict[str, np.ndarray]:
    """
    The 5m klines of the slots in [start, end) (``end=None``: the BTC data end once FINALISTS.md is frozen, until then
    the hold-out start). Only the files of that span are opened. ``t``: the UTC 5-minute slot (s) a kline opens in
    (klines off the grid are floored to it, as study 1's DEVIATIONS 8 did for hours); ``off_grid``: those klines.
    """
    if end is None:
        end_s = DATA_END_S[BTC] if frozen() else CUT_S
    else:
        end_s = s_of(end)
    a_s = 0 if start is None else s_of(start)
    _guard(end_s, f"Binance 5m klines to {utc(end_s)}")
    parts = []
    for label, a, z, url, path in _binance_files_5m(last_day, root):
        if a >= end_s:
            break
        if z <= a_s:
            continue
        if not path.exists():
            raise FileNotFoundError(f"{path}: run `python -B -m backtesting.research.tradeiq2_market fetch-binance5`")
        parts.append(TM.read_klines(path))
    if not parts:
        raise FileNotFoundError(f"no Binance 5m klines under {root}")
    k = {key: np.concatenate([p[key] for p in parts]) for key in parts[0] if key != "us_rows"}
    ot = k.pop("open_ms")
    k.pop("close_ms")
    t = (ot // FIVE_MS) * 300
    k["off_grid"] = ot % FIVE_MS != 0
    order = np.argsort(t, kind="stable")
    t = t[order]
    k = {key: v[order] for key, v in k.items()}
    if len(t) > 1 and not bool(np.all(np.diff(t) > 0)):
        raise ValueError("Binance 5m klines: two klines in one 5-minute slot")
    keep = (t >= a_s) & (t + 300 <= end_s)
    return {"t": t[keep], **{key: v[keep] for key, v in k.items()}}


def binance_volume_5m(mk: TMarket2, tf: str, root: Path = TM.BINANCE_DIR) -> Tuple[np.ndarray, np.ndarray]:
    """
    BTCUSDT spot volume (BTC) on ``mk.tbars(tf)`` for 'M5' and 'M15', and per bar the number of its M5 bars without a
    Binance kline (volume 0: no trade on Binance then). M5: the kline whose open time is the bar's open (UTC). M15:
    the sum over our M5 bars inside it ("the sum of three"; a Binance slot inside one of our data holes belongs to no
    bar, study 1's DEVIATIONS 5 for hours).
    """
    if not mk.symbol.startswith("BTC"):
        raise ValueError("the Binance volume is for BTC only")
    if tf not in ("M5", "M15"):
        raise ValueError(f"{tf}: the 5m klines serve M5 and M15 (1H and up: tradeiq_market.binance_volume)")
    m5 = mk.tbars("M5")
    if mk._binance5 is None:
        mk._binance5 = load_binance_5m(end=mk.end_s, start=(int(mk.t[0]) // 300) * 300, root=root)
    kl = mk._binance5
    j = np.searchsorted(kl["t"], m5.t)
    jj = np.minimum(j, len(kl["t"]) - 1)
    hit = (j < len(kl["t"])) & (kl["t"][jj] == m5.t)
    v5 = np.where(hit, kl["volume"][jj], 0.0)
    miss5 = (~hit).astype(np.int64)
    if tf == "M5":
        return v5, miss5
    hb = mk.tbars(tf)
    own = np.searchsorted(hb.i0, m5.i0, side="right") - 1
    oo = np.maximum(own, 0)
    inside = (own >= 0) & (m5.i1 <= hb.i1[oo])
    if np.any((own >= 0) & (m5.i0 <= hb.i1[oo]) & (m5.i1 > hb.i1[oo])):
        raise AssertionError(f"{tf}: an M5 bar straddles a {tf} bar boundary")
    vol = np.bincount(own[inside], weights=v5[inside], minlength=len(hb))
    miss = np.bincount(own[inside], weights=miss5[inside], minlength=len(hb)).astype(np.int64)
    return vol, miss


def binance_volume(mk: TMarket2, tf: str, root: Path = TM.BINANCE_DIR) -> Tuple[np.ndarray, np.ndarray]:
    """BTC's Binance volume on any timeframe: the 5m klines on M5 / M15, study 1's 1h klines (its
    ``binance_volume``, sums over our 1H bars) on 1H, 4H, 1D and 1W. Returns (volume, bars' sub-bars without a kline)."""
    if tf in ("M5", "M15"):
        return binance_volume_5m(mk, tf, root=root)
    _guard(mk.end_s, f"{mk.symbol} Binance volume")
    return TM.binance_volume(mk, tf, root=root)


def binance_check_5m(mk: TMarket2, root: Path = TM.BINANCE_DIR) -> Dict[str, object]:
    """
    PREREG 2's check of the 5m klines on the span ``mk`` holds (to the hold-out start while it is closed): bar times,
    gaps, and the correlation of Binance and Exness M5 closes (levels, overall and by year; log returns at lags of
    -2..2 bars, the best of which must be lag 0). Passes when the close correlation is above 0.999, the best lag is 0
    and the times increase.
    """
    m5 = mk.tbars("M5")
    kl = load_binance_5m(end=mk.end_s, start=(int(mk.t[0]) // 300) * 300, root=root)
    t = kl["t"]
    a = max(int(t[0]), int(m5.t[0]))
    d = np.diff(t)
    gaps = [{"after": str(utc(t[i])), "before": str(utc(t[i + 1])), "missing_slots": int(d[i] // 300 - 1)}
            for i in np.flatnonzero(d != 300)]
    j = np.searchsorted(t, m5.t)
    jj = np.minimum(j, len(t) - 1)
    hit = (j < len(t)) & (t[jj] == m5.t)
    ours_missing = m5.t[(m5.t >= a) & ~hit]
    e_c, b_c = m5.c[hit], kl["close"][jj[hit]]
    years = pd.to_datetime(m5.t[hit], unit="s").year
    per_year = {int(y): float(np.corrcoef(e_c[years == y], b_c[years == y])[0, 1]) for y in np.unique(years)}
    g0 = min(int(t[0]), int(m5.t[0]))
    n_g = (max(int(t[-1]), int(m5.t[-1])) - g0) // 300 + 1
    E = np.full(n_g, np.nan)
    B = np.full(n_g, np.nan)
    E[(m5.t - g0) // 300] = m5.c
    B[(t - g0) // 300] = kl["close"]
    re, rb = np.diff(np.log(E)), np.diff(np.log(B))
    yr = pd.to_datetime(g0 + 300 * np.arange(1, n_g), unit="s").year.to_numpy()   # the year of each return's end
    lags, lags_y = {}, {}
    for L in (-2, -1, 0, 1, 2):
        x, y = (re[L:], rb[:len(rb) - L]) if L >= 0 else (re[:L], rb[-L:])
        yy = yr[L:] if L >= 0 else yr[:L]
        ok = np.isfinite(x) & np.isfinite(y)
        lags[L] = float(np.corrcoef(x[ok], y[ok])[0, 1])
        for v in np.unique(yy[ok]):
            sel = ok & (yy == v)
            lags_y.setdefault(int(v), {})[L] = float(np.corrcoef(x[sel], y[sel])[0, 1])
    rel = np.abs(b_c / e_c - 1.0)
    out = {
        "span": f"{utc(m5.t[0])} .. {utc(mk.end_s)}",
        "binance_klines": int(len(t)), "exness_m5_bars": int(len(m5)), "matched": int(hit.sum()),
        "exness_bars_without_kline": int(len(ours_missing)),
        "klines_outside_exness_bars": int((~np.isin(t, m5.t)).sum()),
        "binance_gaps": len(gaps), "binance_gap_slots": int(sum(g["missing_slots"] for g in gaps)),
        "binance_gaps_first": gaps[:5], "binance_gap_last": gaps[-1] if gaps else None,
        "largest_gap_slots": int(max((g["missing_slots"] for g in gaps), default=0)),
        "klines_off_grid": int(kl["off_grid"].sum()),
        "klines_off_grid_span": (f"{utc(t[kl['off_grid']][0])} .. {utc(t[kl['off_grid']][-1])}"
                                 if kl["off_grid"].any() else ""),
        "times_increasing": bool(np.all(d > 0)),
        "corr_close": float(np.corrcoef(e_c, b_c)[0, 1]), "corr_close_by_year": per_year,
        "corr_logret_by_lag_bars": lags, "best_lag_bars": int(max(lags, key=lags.get)),
        "corr_logret_lag0_by_year": {y: d[0] for y, d in lags_y.items()},
        "best_lag_bars_by_year": {y: int(max(d, key=d.get)) for y, d in lags_y.items()},
        "median_abs_rel_diff": float(np.median(rel)), "p99_abs_rel_diff": float(np.quantile(rel, 0.99)),
    }
    out["passes"] = bool(out["corr_close"] > 0.999 and out["best_lag_bars"] == 0 and out["times_increasing"])
    out["lag0_best_every_year"] = bool(all(v == 0 for v in out["best_lag_bars_by_year"].values()))
    return out


# ───────────────────────────── the types the rule modules use ─────────────────────────────

@dataclass(frozen=True)
class Variant:
    """
    One row of the grid (PREREG 6-7). ``id`` is unique per symbol (convention: ``symbol|tf|script|...``); ``script``
    the script it belongs to (RIB, MSD, WY, SP, ORB, SH, HP, HA, COIL, STK); ``family`` PREREG 7's family (RIB, ALMA-X,
    MSD-ALONE, ...); ``eligible`` False for controls and information rows that are scored but never selected;
    ``info`` a short note (e.g. "control", "information only"); ``params`` the rule's settings (filter, exit, stop,
    ...), JSON-able values, kept out of hashing.
    """
    id: str
    symbol: str
    tf: str
    script: str
    family: str
    eligible: bool = True
    info: str = ""
    params: Mapping[str, object] = field(default_factory=dict, hash=False, compare=False)

    def ident(self) -> Dict[str, object]:
        return {"vid": self.id, "symbol": self.symbol, "tf": self.tf, "script": self.script, "family": self.family,
                "eligible": bool(self.eligible), "info": self.info,
                "params": json.dumps(dict(self.params), sort_keys=True, default=str)}


def _col(x, n: int, dtype, name: str, fill) -> np.ndarray:
    if x is None:
        return np.full(n, fill, dtype)
    a = np.asarray(x)
    if a.ndim == 0:
        return np.full(n, a.item(), dtype)
    if a.shape != (n,):
        raise ValueError(f"{name}: shape {a.shape}, expected ({n},)")
    return a.astype(dtype)


def _positive_or_nan(a: np.ndarray, name: str) -> None:
    bad = np.isfinite(a) & ~(a > 0)
    if bad.any() or np.isinf(a).any():
        raise ValueError(f"{name}: must be > 0 or NaN (row {int(np.flatnonzero(bad | np.isinf(a))[0])})")


def _at_most_one(cols: Sequence[np.ndarray], names: Sequence[str], what: str) -> None:
    both = np.sum([np.isfinite(c) for c in cols], axis=0) > 1
    if np.any(both):
        raise ValueError(f"{what}: more than one of {', '.join(names)} given (row {int(np.flatnonzero(both)[0])})")


def _flags(x, n: int, name: str) -> np.ndarray:
    """A True / False column of ``n`` rows: None = all False, a scalar is broadcast; bools, or the integers 0 and 1."""
    if x is None:
        return np.zeros(n, np.bool_)
    a = np.asarray(x)
    if a.dtype.kind not in "biu" or (a.dtype.kind != "b" and not np.isin(a, (0, 1)).all()):
        raise ValueError(f"{name}: True or False per row (or one value for all)")
    return _col(a, n, np.bool_, name, False)


@dataclass(eq=False)
class Entries:
    """
    Market entries of an event Exec, one row each (build with ``entries``). The entry is decided at the close of
    signal bar ``bar`` and fills at the open of ``bars.ex[bar]`` (a buy at the ask, a sell at the bid), side ``side``.
    Stop: ``stop_level`` (absolute; becomes |fill - level| from the actual fill) or ``stop_dist`` (from the fill), at
    most one; none = no stop. Target: ``target_level`` (absolute), ``target_dist`` or ``target_r`` (a multiple of the
    initial risk |fill - stop|), at most one. ``be_r``: the stop moves to the fill once price has gone ``be_r`` x the
    initial risk in favour (``external``'s ``ber``: the bid high for a long, the ask low for a short, checked inside
    each M1 bar after its stop and target; it applies from the next M1 bar). ``exit_bar``: the first exit decision of
    this entry's own (a time stop = the close of bar k, an exit signal at a later close; -1 none); it must be later than
    ``bar``. ``risk``: a price distance used as the trade's R when it has no stop (NaN: the stop distance). ``tag``: the
    rule's own integer per entry (a setup, a campaign), carried to the trades. ``close_gap`` (True / False, default
    False): when the row's ``exit_bar`` is what ends the position and no M1 bar opens at that bar's close (an early
    close, a weekend, a data hole: ``bars.ex[exit_bar]`` is the reopen), the exit is booked at the close of the bar's
    last M1 bar (``bars.i1[exit_bar]``, the bid for a long, the ask for a short) as a position still open at a
    window's end, not at the reopen; the trade row reads as a time exit ('signal'). A stop or a target touched before
    that close wins; exit masks and tightenings are unaffected (the module docstring has the whole reading).
    """
    bar: np.ndarray
    side: np.ndarray
    stop_level: np.ndarray
    stop_dist: np.ndarray
    target_level: np.ndarray
    target_dist: np.ndarray
    target_r: np.ndarray
    be_r: np.ndarray
    exit_bar: np.ndarray
    risk: np.ndarray
    tag: np.ndarray
    close_gap: Optional[np.ndarray] = None          # None: all False (a table built before the flag existed)

    def __post_init__(self) -> None:
        self.close_gap = _flags(self.close_gap, len(self.bar), "close_gap")

    def __len__(self) -> int:
        return int(len(self.bar))

    def take(self, keep) -> "Entries":
        keep = np.asarray(keep)
        return Entries(**{k: getattr(self, k)[keep] for k in self.__dataclass_fields__})


def entries(bar, side, *, stop_level=None, stop_dist=None, target_level=None, target_dist=None, target_r=None,
            be_r=None, exit_bar=None, risk=None, tag=None, close_gap=None) -> Entries:
    """Build and check an ``Entries`` table; scalars are broadcast, NaN (or -1 for ``exit_bar``) means "none".
    ``close_gap``: True / False per row or one for all (None: False): book the row's own ``exit_bar`` at the last M1
    close before a gap instead of at the reopen (``Entries``; harness reading 15)."""
    bar = np.asarray(bar, np.int64).ravel()
    n = len(bar)
    side = _col(side, n, np.int64, "side", 0)
    if not np.all(np.isin(side, (-1, 1))):
        raise ValueError("side must be +1 (long) or -1 (short)")
    f = {k: _col(v, n, np.float64, k, np.nan) for k, v in
         (("stop_level", stop_level), ("stop_dist", stop_dist), ("target_level", target_level),
          ("target_dist", target_dist), ("target_r", target_r), ("be_r", be_r), ("risk", risk))}
    for k in ("stop_dist", "target_dist", "target_r", "be_r", "risk"):
        _positive_or_nan(f[k], k)
    if np.isinf(f["stop_level"]).any() or np.isinf(f["target_level"]).any():
        raise ValueError("levels must be finite or NaN")
    _at_most_one([f["stop_level"], f["stop_dist"]], ("stop_level", "stop_dist"), "entries")
    _at_most_one([f["target_level"], f["target_dist"], f["target_r"]], ("target_level", "target_dist", "target_r"),
                 "entries")
    xb = _col(exit_bar, n, np.int64, "exit_bar", -1)
    if np.any((xb >= 0) & (xb <= bar)) or np.any(xb < -1):
        raise ValueError("exit_bar must be -1 or later than the entry's bar")
    return Entries(bar=bar, side=side, exit_bar=xb, tag=_col(tag, n, np.int64, "tag", 0), close_gap=close_gap, **f)


@dataclass(eq=False)
class Orders:
    """
    Stop-entry orders of an event Exec, one row each (build with ``orders``): placed at the close of signal bar
    ``bar`` (active from the open of ``bars.ex[bar]``), cancelled at the first M1 bar opening at or after ``until``
    (UTC s). ``buy`` / ``sell``: the buy-stop and sell-stop levels (NaN: that side is absent; both: one cancels the
    other). A buy fills at max(buy, ask at the open) once the ask reaches ``buy`` inside an M1 bar, a sell at
    min(sell, bid at the open) once the bid reaches ``sell``; when both sides are reached in one M1 bar, the one nearer
    the open fills; the fill's own bar can stop it (its opposite extreme is taken to come after the fill), not reach
    its target (``external._path_kernel``). Stops: ``buy_stop`` / ``sell_stop`` (absolute) or ``stop_dist`` (from the
    fill). Targets: ``buy_target`` / ``sell_target`` (absolute, a distance from the actual fill), ``target_dist`` or
    ``target_r``. ``be_r``, ``exit_bar``, ``risk``, ``tag`` as for ``Entries``; a fixed ``exit_bar`` before the fill's
    bar exits at the close of the fill's bar. Each order fills at most once. A newer order replaces an older one that
    has not filled; an order placed while a position is open becomes active when it closes (until ``until``).
    ``close_gap`` as for ``Entries``, for the order's own fixed exit: the earlier of ``exit_bar`` and the bar
    ``on_fill`` returns, at the earliest the fill's bar (a fill in the last M1 bar before a gap exits at its close).
    """
    bar: np.ndarray
    until: np.ndarray
    buy: np.ndarray
    sell: np.ndarray
    buy_stop: np.ndarray
    sell_stop: np.ndarray
    stop_dist: np.ndarray
    buy_target: np.ndarray
    sell_target: np.ndarray
    target_dist: np.ndarray
    target_r: np.ndarray
    be_r: np.ndarray
    exit_bar: np.ndarray
    risk: np.ndarray
    tag: np.ndarray
    close_gap: Optional[np.ndarray] = None          # None: all False (a table built before the flag existed)

    def __post_init__(self) -> None:
        self.close_gap = _flags(self.close_gap, len(self.bar), "close_gap")

    def __len__(self) -> int:
        return int(len(self.bar))

    def take(self, keep) -> "Orders":
        keep = np.asarray(keep)
        return Orders(**{k: getattr(self, k)[keep] for k in self.__dataclass_fields__})


def orders(bar, until, *, buy=None, sell=None, buy_stop=None, sell_stop=None, stop_dist=None, buy_target=None,
           sell_target=None, target_dist=None, target_r=None, be_r=None, exit_bar=None, risk=None,
           tag=None, close_gap=None) -> Orders:
    """Build and check an ``Orders`` table; scalars are broadcast, NaN (or -1 for ``exit_bar``) means "none".
    ``close_gap``: True / False per row or one for all (None: False): book the order's own fixed exit (``exit_bar`` or
    ``on_fill``'s) at the last M1 close before a gap instead of at the reopen (``Orders``; harness reading 15)."""
    bar = np.asarray(bar, np.int64).ravel()
    n = len(bar)
    if isinstance(until, (str, int, np.integer, pd.Timestamp)):
        until = np.full(n, s_of(until), np.int64)
    else:
        until = np.asarray([s_of(u) for u in np.asarray(until).ravel()], np.int64)
    if until.shape != (n,):
        raise ValueError(f"until: shape {until.shape}, expected ({n},)")
    f = {k: _col(v, n, np.float64, k, np.nan) for k, v in
         (("buy", buy), ("sell", sell), ("buy_stop", buy_stop), ("sell_stop", sell_stop), ("stop_dist", stop_dist),
          ("buy_target", buy_target), ("sell_target", sell_target), ("target_dist", target_dist),
          ("target_r", target_r), ("be_r", be_r), ("risk", risk))}
    for k in ("stop_dist", "target_dist", "target_r", "be_r", "risk"):
        _positive_or_nan(f[k], k)
    if any(np.isinf(f[k]).any() for k in ("buy", "sell", "buy_stop", "sell_stop", "buy_target", "sell_target")):
        raise ValueError("levels must be finite or NaN")
    if np.any(~np.isfinite(f["buy"]) & ~np.isfinite(f["sell"])):
        raise ValueError("an order without a buy or a sell level")
    _at_most_one([f["buy_stop"], f["stop_dist"]], ("buy_stop", "stop_dist"), "orders")
    _at_most_one([f["sell_stop"], f["stop_dist"]], ("sell_stop", "stop_dist"), "orders")
    _at_most_one([f["buy_target"], f["target_dist"], f["target_r"]], ("buy_target", "target_dist", "target_r"), "orders")
    _at_most_one([f["sell_target"], f["target_dist"], f["target_r"]], ("sell_target", "target_dist", "target_r"),
                 "orders")
    with np.errstate(invalid="ignore"):
        if np.any(f["buy_stop"] >= f["buy"]) or np.any(f["sell_stop"] <= f["sell"]):
            raise ValueError("a buy order's stop must lie below its level, a sell order's above")
    xb = _col(exit_bar, n, np.int64, "exit_bar", -1)
    if np.any((xb >= 0) & (xb <= bar)) or np.any(xb < -1):
        raise ValueError("exit_bar must be -1 or later than the order's bar")
    return Orders(bar=bar, until=until, exit_bar=xb, tag=_col(tag, n, np.int64, "tag", 0), close_gap=close_gap,
                  **f)


@dataclass(frozen=True, eq=False)
class Leg:
    """
    One leg of a position split into legs with identical entries (PREREG 4: "half at 2R, let the rest run").
    ``weight``: its share (the weights of an Exec sum to 1). Its target: the entry's own, unless the leg gives one of
    ``target_level`` / ``target_dist`` / ``target_r`` (entries; scalars or arrays aligned with the entries),
    ``buy_target`` / ``sell_target`` / ``target_dist`` / ``target_r`` (orders), or ``no_target=True``; then that
    replaces the entry's target for this leg. ``be_r``: this leg's break-even (None: the entry's).
    """
    weight: float
    no_target: bool = False
    target_level: object = None
    target_dist: object = None
    target_r: object = None
    buy_target: object = None
    sell_target: object = None
    be_r: object = None

    @property
    def own_target(self) -> bool:
        return self.no_target or any(getattr(self, k) is not None for k in
                                     ("target_level", "target_dist", "target_r", "buy_target", "sell_target"))


ONE_LEG = (Leg(1.0),)


@dataclass(eq=False)
class Exec:
    """
    What a variant hands the harness (build with ``state_exec``, ``event_exec`` or ``lanes_exec``):

    * STATE: ``state`` per signal bar (+1 / 0 / -1, decided at the bar's close) and ``stop`` (None, or a price distance
      per bar taken at the entry's decision bar and set from the fill): study 1's ``run`` with DEVIATIONS 1-7 (an entry
      only where the state changes, also after a stop or a target; the window's first bar takes the state; what is
      open at the window's end closes at its last M1 close). Optional overlays: ``target_r`` / ``be_r`` (scalar or per
      bar), ``legs``, ``exit_long`` / ``exit_short`` and the tightening arrays (below). After an overlay exit the
      state rule stays flat until its state changes.
    * EVENTS: ``entries`` (market entries) or ``orders`` (stop-entry orders), not both; one position at a time; a
      candidate arriving while a position is open is skipped ("an event rule waits for its next event"). A row with
      ``close_gap`` has its own fixed exit booked at the last M1 close before a gap (``Entries``; harness reading 15).
    * LANES: ``lanes``, single-position STATE / EVENTS Execs of one symbol executed independently and summed.

    Per-signal-bar overlays (STATE and EVENTS): ``exit_long[b]`` / ``exit_short[b]`` close an open long / short at the
    close of bar b; ``tighten_long[b]`` / ``tighten_short[b]``: an absolute stop level for an open long / short decided
    at the close of bar b (NaN none; ``tighten_be[b]`` True: the tighter of that level and break-even = the entry's
    fill). A tightened level is applied at the open of ``bars.ex[b]`` only if it lies below the bid (long) / above the
    ask (short) there, else that open is a market exit; a level looser than the current stop changes nothing. These
    overlays act from the bar after a market entry's decision bar, and from the bar that contains a stop-order's fill.
    ``on_fill(fill_bar, side) -> exit_bar``: for orders, the first exit decision of the trade, given the signal bar
    that contains its fill (-1 none; e.g. a trail that starts at the entry). ``fill_long`` / ``fill_short``: per M1
    bar masks allowing a stop-order fill of that side (None: always).
    """
    tf: str
    state: Optional[np.ndarray] = None
    stop: Optional[np.ndarray] = None
    target_r: object = None
    be_r: object = None
    entries: Optional[Entries] = None
    orders: Optional[Orders] = None
    legs: Tuple[Leg, ...] = ONE_LEG
    exit_long: Optional[np.ndarray] = None
    exit_short: Optional[np.ndarray] = None
    tighten_long: Optional[np.ndarray] = None
    tighten_short: Optional[np.ndarray] = None
    tighten_be: Optional[np.ndarray] = None
    on_fill: Optional[Callable[[int, int], int]] = None
    fill_long: Optional[np.ndarray] = None
    fill_short: Optional[np.ndarray] = None
    lanes: Tuple["Exec", ...] = ()
    label: str = ""

    @property
    def kind(self) -> str:
        return "lanes" if self.lanes else ("state" if self.state is not None else "events")

    @property
    def overlays(self) -> bool:
        """True when a STATE Exec needs more than study 1's ``run`` (targets, break-even, legs, exits, tightening)."""
        return (self.target_r is not None or self.be_r is not None or tuple(self.legs) != ONE_LEG
                or any(getattr(self, k) is not None for k in
                       ("exit_long", "exit_short", "tighten_long", "tighten_short")))


def _legs_of(legs) -> Tuple[Leg, ...]:
    legs = tuple(legs) if legs else ONE_LEG
    if not all(isinstance(g, Leg) for g in legs):
        raise TypeError("legs must be Leg objects")
    w = np.asarray([g.weight for g in legs], np.float64)
    if not (np.all(w > 0) and abs(float(w.sum()) - 1.0) <= 1e-9):
        raise ValueError(f"leg weights must be > 0 and sum to 1, got {list(w)}")
    return legs


def state_exec(tf: str, state, stop=None, *, target_r=None, be_r=None, legs=None, exit_long=None, exit_short=None,
               tighten_long=None, tighten_short=None, tighten_be=None, label: str = "") -> Exec:
    """A STATE Exec (see ``Exec``): ``state`` per bar of ``tf``, ``stop`` None or a distance per bar."""
    st = TM._states(state, len(np.asarray(state)))
    return Exec(tf=tf, state=st, stop=None if stop is None else np.asarray(stop, np.float64), target_r=target_r,
                be_r=be_r, legs=_legs_of(legs), exit_long=exit_long, exit_short=exit_short,
                tighten_long=tighten_long, tighten_short=tighten_short, tighten_be=tighten_be, label=label)


def event_exec(tf: str, entries: Optional[Entries] = None, orders: Optional[Orders] = None, *, legs=None,
               exit_long=None, exit_short=None, tighten_long=None, tighten_short=None, tighten_be=None,
               on_fill=None, fill_long=None, fill_short=None, label: str = "") -> Exec:
    """An EVENTS Exec (see ``Exec``): market ``entries`` or stop-entry ``orders`` of timeframe ``tf``. A row whose
    ``close_gap`` is True has its own fixed exit (``exit_bar``; for orders also ``on_fill``'s) booked at the close of
    that bar's last M1 bar when no M1 bar opens at the bar's close, instead of at the reopen; the per-bar overlays
    given here (exit masks, tightenings) and the stops are unaffected (module docstring, harness reading 15)."""
    if (entries is None) == (orders is None):
        raise ValueError("an event Exec has entries or orders (one of them; lanes can mix)")
    if on_fill is not None and orders is None:
        raise ValueError("on_fill is for orders (market entries carry their exit_bar)")
    return Exec(tf=tf, entries=entries, orders=orders, legs=_legs_of(legs), exit_long=exit_long,
                exit_short=exit_short, tighten_long=tighten_long, tighten_short=tighten_short,
                tighten_be=tighten_be, on_fill=on_fill, fill_long=fill_long, fill_short=fill_short, label=label)


def lanes_exec(lanes: Sequence[Exec], label: str = "") -> Exec:
    """A LANES Exec: single-position Execs (STATE or EVENTS) executed independently and summed (PREREG 4)."""
    lanes = tuple(lanes)
    if not lanes or any(not isinstance(x, Exec) or x.kind == "lanes" for x in lanes):
        raise ValueError("lanes are one or more STATE / EVENTS Execs")
    return Exec(tf=lanes[0].tf if len({x.tf for x in lanes}) == 1 else "+".join(x.tf for x in lanes), lanes=lanes,
                label=label)


def _params_key(params) -> object:
    """A hashable, canonical form of a parameter mapping (nested dicts, lists, numbers, strings)."""
    if isinstance(params, Mapping):
        return tuple(sorted((str(k), _params_key(v)) for k, v in params.items()))
    if isinstance(params, (list, tuple)):
        return tuple(_params_key(v) for v in params)
    if isinstance(params, np.ndarray):
        raise TypeError("arrays cannot be cache keys: pass their parameters instead")
    if isinstance(params, np.generic):
        return params.item()
    hash(params)
    return params


class Context:
    """
    One symbol's state for the rule modules: the market (``mk``, a ``TMarket2`` the guard served), its bars per
    timeframe (``bars(tf)``), a cache of indicator outputs keyed by (module, symbol, tf, params) (``get``), the volume
    PREREG 2 assigns (``volume``), the New York clock of the bars' open times, and the filters of PREREG 5
    (``allow``, computed by ``tradeiq2_filters`` and cached here).
    """

    def __init__(self, mk: TMarket2):
        if not isinstance(mk, TMarket2) or mk.cost != 1.0:
            raise TypeError("Context takes the TMarket2 itself (tradeiq2_market.load)")
        self.mk = mk
        self.symbol = mk.symbol
        self.cache: Dict[tuple, object] = {}
        self._bars: Dict[str, TM.TBars] = {}

    def bars(self, tf: str) -> TM.TBars:
        if tf not in self._bars:
            self._bars[tf] = self.mk.tbars(tf)
        return self._bars[tf]

    def get(self, module: str, tf: str, params, fn: Callable[[], object]):
        """The cached value of (module, symbol, tf, params), computed by ``fn()`` the first time. Arrays should be
        returned read-only (``a.setflags(write=False)``) when callers might modify them."""
        key = (str(module), self.symbol, str(tf), _params_key(params))
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]

    def volume(self, tf: str, source: str = "auto") -> np.ndarray:
        """PREREG 2: gold (and the claim markets) tick volume; BTC Binance BTCUSDT spot volume (``binance_volume``).
        ``source='tick'`` gives the tick volume on any symbol (Wyckoff's BTC control)."""
        if source not in ("auto", "tick", "binance"):
            raise ValueError(f"volume source {source}")
        if source == "tick" or (source == "auto" and not self.symbol.startswith("BTC")):
            return self.bars(tf).vol
        return self.get("volume", tf, {"source": "binance"}, lambda: self._binance(tf))[0]

    def volume_missing(self, tf: str) -> np.ndarray:
        """BTC: per bar, the number of its sub-bars (M5 for M5/M15, 1H above) without a Binance kline."""
        return self.get("volume", tf, {"source": "binance"}, lambda: self._binance(tf))[1]

    def _binance(self, tf: str):
        v, miss = binance_volume(self.mk, tf)
        v.setflags(write=False)
        miss.setflags(write=False)
        return v, miss

    def atr(self, tf: str, n: int = 14) -> np.ndarray:
        """PREREG 5's ATR: Pine ``ta.atr(n)`` of the signal bars (``atr14``), cached."""
        return self.get("atr", tf, {"n": n}, lambda: _ro(atr14(self.bars(tf), n)))

    def ny(self, tf: str) -> Dict[str, np.ndarray]:
        """The New York clock of the bars' OPEN times: minute of the day, date (epoch day), weekday (0 = Monday),
        Session Hunter's day key and its weekday. Cached."""
        def make():
            t = self.bars(tf).t
            loc = ny_local(t)
            dk = sh_day_key(t)
            return {k: _ro(v) for k, v in (("minute", (loc % DAY) // 60), ("date", loc // DAY),
                                           ("weekday", (loc // DAY + 3) % 7), ("day_key", dk),
                                           ("day_key_weekday", (dk + 3) % 7))}
        return self.get("ny", tf, {}, make)

    def allow(self, tf: str, name: str) -> Tuple[np.ndarray, np.ndarray]:
        """(allow_long, allow_short) per signal bar of filter ``name`` (PREREG 5): ``tradeiq2_filters.allow``."""
        from . import tradeiq2_filters as F2
        return F2.allow(self, tf, name)

    def run(self, ex: Exec, window: str, cost: float = 1.0) -> "Run2":
        a, z = window_span(window, self.symbol)
        return run_exec(self.mk, ex, a, z, cost)


def _ro(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


# ───────────────────────────── the result of a run ─────────────────────────────

class _NoSinglePath:
    """``Run2.path`` of a run with several legs or lanes: there is no single-position path, so study 1's
    ``account_curve`` (``external.account``, one position at a time) must not be used; ``account_curve`` here is."""

    def __getattr__(self, name):
        raise TypeError("this run has several legs or lanes: use tradeiq2_market.account_curve (not tradeiq_market's)")

    def __len__(self) -> int:
        raise TypeError("this run has several legs or lanes: see Run2.legs / Run2.lanes")


@dataclass(eq=False)
class Run2(TM.Run):
    """
    Study 1's ``Run`` (so ``tradeiq_market.metrics``, ``weekly_pnl``, ``quarter_pnl``, ``unit_curve`` and ``eq_at`` read
    it) plus: ``kind`` (state / events / lanes); ``legs``: per leg (weight, its slippage-adjusted ``Path_``); ``lanes``:
    the lanes' own ``Run2``s; ``counts``: candidates, taken, busy, dropped and the like. ``trades`` has one row per
    position (legs combined: weighted P/L, the last leg's exit and reason, every leg's reason in ``reasons``) and the
    columns ``risk`` (the initial risk distance, price; NaN without a stop) and ``r`` (P/L over the risk in dollars),
    ``tag``, ``bar`` (the decision bar of the entry; for orders the bar of the fill) and ``lane``. ``path`` is the
    single-position path, or a guard object when there are several legs or lanes. A close_gap exit (harness reading
    15) reads 'signal' in ``trades`` (``reason`` / ``reasons``), with the exit time of the M1 bar's close it was booked
    at; its paths (``path``, ``legs``) keep ``X.WHY_END`` at that bar, which every mark and account kernel reads as an
    exit at the bar's close; ``counts['close_gap']`` counts those positions.
    """
    kind: str = "state"
    legs: Tuple[Tuple[float, X.Path_], ...] = ()
    lanes: Tuple["Run2", ...] = ()
    counts: Dict[str, int] = field(default_factory=dict)
    label: str = ""

    @property
    def single(self) -> bool:
        return not isinstance(self.path, _NoSinglePath)

    def slim(self) -> "Run2":
        """The run without its per-M1-bar arrays (``ec``, ``ew``, ``pos``) and with the trades reduced to what the
        account needs: enough for ``account_curve``, small enough to keep for many variants."""
        keep = [c for c in ("pnl", "entry_ix", "exit_ix", "side", "risk", "r") if c in self.trades.columns]
        return replace(self, ec=None, ew=None, pos=None, trades=self.trades[keep].copy(),
                       lanes=tuple(x.slim() for x in self.lanes))


# ───────────────────────────── the engine ─────────────────────────────

@njit(cache=True)
def _sum_marks(c, h, l, sp, k, d, w, eix, xix, epx, xpx, why, ia, iz):
    """
    The per-unit equity of a set of weighted trades that may overlap (legs, lanes) over the M1 bars [ia, iz), from 0
    at ia, in the event order of ``balke._multi_kernel`` without sizing: at each bar first the exits at its open (a
    signal, a gap through the stop or the target) are booked, then the entries at it open, then the bar is marked:
    every open trade at its close mark (bid for a long, ask for a short) and its worst mark (the low, or the high +
    spread; an exit's own price on its exit bar, the bar's extreme for a target or the window's end), the running
    peak taken over the close marks of the trades that outlive the bar first, then the drawdown against the sum of the
    worst marks; then the exits inside the bar are booked. Trades are sorted by entry bar. For trades that never
    overlap and have weight 1 this is ``tradeiq_market._unit_marks`` exactly (tests). ``pos``: the side held through
    the bar (2 = both sides at once, lanes only).
    """
    n = iz - ia
    nt = d.shape[0]
    ec = np.zeros(n)
    ew = np.zeros(n)
    pos = np.zeros(n, np.int8)
    opened = np.empty(nt, np.int64)
    n_open = 0
    nxt = 0
    bal = 0.0
    peak = 0.0
    maxdd = 0.0
    for j in range(ia, iz):
        if n_open > 0:
            m = 0
            booked = False
            for q in range(n_open):
                i = opened[q]
                if xix[i] == j and (why[i] == 1 or why[i] == 5 or why[i] == 6):
                    bal += w[i] * k * d[i] * (xpx[i] - epx[i])
                    booked = True
                else:
                    opened[m] = i
                    m += 1
            n_open = m
            if booked and n_open == 0:
                if peak - bal > maxdd:
                    maxdd = peak - bal
                if bal > peak:
                    peak = bal
        while nxt < nt and eix[nxt] <= j:
            if eix[nxt] == j:
                opened[n_open] = nxt
                n_open += 1
            nxt += 1
        if n_open == 0:
            ec[j - ia] = bal
            ew[j - ia] = bal
            continue
        uc_keep = 0.0
        uw = 0.0
        realized = 0.0
        keep = 0
        side = 0
        for q in range(n_open):
            i = opened[q]
            held = True
            if xix[i] == j:
                mw = xpx[i]
                if why[i] == 3 or why[i] == 4:
                    mw = l[j] if d[i] == 1 else h[j] + sp[j]
                uw += w[i] * k * d[i] * (mw - epx[i])
                realized += w[i] * k * d[i] * (xpx[i] - epx[i])
                held = why[i] == 4
            else:
                mc = c[j] if d[i] == 1 else c[j] + sp[j]
                mw = l[j] if d[i] == 1 else h[j] + sp[j]
                uc_keep += w[i] * k * d[i] * (mc - epx[i])
                uw += w[i] * k * d[i] * (mw - epx[i])
                keep += 1
            if held:
                if side == 0:
                    side = d[i]
                elif side != d[i]:
                    side = 2
        pos[j - ia] = side
        if keep > 0 and bal + realized + uc_keep > peak:
            peak = bal + realized + uc_keep
        e_w = bal + uw
        if peak - e_w > maxdd:
            maxdd = peak - e_w
        if keep < n_open:
            bal += realized
            m = 0
            for q in range(n_open):
                i = opened[q]
                if xix[i] != j:
                    opened[m] = i
                    m += 1
            n_open = m
        ec[j - ia] = bal + uc_keep
        ew[j - ia] = e_w
        if bal + uc_keep > peak:
            peak = bal + uc_keep
    return ec, ew, pos, bal, maxdd


def _next_true(mask: Optional[np.ndarray], n: int) -> np.ndarray:
    """nxt[i] = the smallest b >= i with mask[b] (n when none), for i in 0..n."""
    out = np.full(n + 1, n, np.int64)
    if mask is None:
        return out
    m = np.asarray(mask, bool)
    if m.shape != (n,):
        raise ValueError(f"an exit mask has shape {m.shape}, the bars {n}")
    idx = np.flatnonzero(m)
    pos = np.searchsorted(idx, np.arange(n + 1), side="left")
    out[pos < len(idx)] = idx[pos[pos < len(idx)]]
    return out


def _bar_array(x, n: int, name: str, dtype=np.float64, fill=np.nan) -> Optional[np.ndarray]:
    if x is None:
        return None
    a = np.asarray(x)
    if a.ndim == 0:
        return np.full(n, a.item(), dtype)
    if a.shape != (n,):
        raise ValueError(f"{name} has shape {a.shape}, the bars {n}")
    return a.astype(dtype)


@dataclass
class _Overlays:
    nxt: Dict[int, np.ndarray]            # side -> next bar with a per-bar exit for that side
    tix: Dict[int, np.ndarray]            # side -> bars with a tightening level
    tlev: Dict[int, Optional[np.ndarray]]
    tbe: np.ndarray


def _overlays(ex: Exec, n: int) -> _Overlays:
    tl = _bar_array(ex.tighten_long, n, "tighten_long")
    ts = _bar_array(ex.tighten_short, n, "tighten_short")
    for a, nm in ((tl, "tighten_long"), (ts, "tighten_short")):
        if a is not None and np.isinf(a).any():
            raise ValueError(f"{nm}: levels must be finite or NaN")
    tbe = _bar_array(ex.tighten_be, n, "tighten_be", np.bool_, False)
    return _Overlays(nxt={1: _next_true(ex.exit_long, n), -1: _next_true(ex.exit_short, n)},
                     tix={1: np.zeros(0, np.int64) if tl is None else np.flatnonzero(np.isfinite(tl)),
                          -1: np.zeros(0, np.int64) if ts is None else np.flatnonzero(np.isfinite(ts))},
                     tlev={1: tl, -1: ts}, tbe=np.zeros(n, np.bool_) if tbe is None else tbe)


CHUNK = 1 << 15                     # M1 bars a position without an exit decision is first run for
# the counts of every run (Run2.counts; metrics() reports them as n_<key>):
#   candidates      entries / orders decided inside the window
#   taken           positions opened
#   busy            candidates skipped because a position was open (an order: replaced or expired meanwhile)
#   dropped_stop    entries whose fill was at or beyond their stop (PREREG 4)
#   dropped_target  entries whose fill was at or beyond one of their targets (PREREG 4)
#   unfilled        orders that expired (or were replaced) without a fill
#   tighten_rows    stop tightenings applied while the position was open
#   tighten_exits   tightenings already crossed at their open that closed the position there (PREREG 4)
#   close_gap       positions a close_gap row's own exit closed at the last M1 close before a gap (harness reading 15)
COUNT_KEYS = ("candidates", "taken", "busy", "dropped_stop", "dropped_target", "unfilled", "tighten_rows",
              "tighten_exits", "close_gap")


class _Sim:
    """The per-position executor of one Exec over one window on the costed market ``cm`` (see the module docstring)."""

    def __init__(self, mk: TMarket2, cm: TM.TMarket, bars: TM.TBars, ex: Exec, ia: int, iz: int):
        self.mk, self.cm, self.bars, self.ex = mk, cm, bars, ex
        self.ia, self.iz = ia, iz
        self.n = len(bars)
        self.by_bar = ex.state is not None          # a STATE Exec's leg arrays are per bar, an EVENTS Exec's per row
        self.ov = _overlays(ex, self.n)
        self.legs = _legs_of(ex.legs)
        self.ones = mk.ones()
        self.ml = self.ones if ex.fill_long is None else self._m1_mask(ex.fill_long, "fill_long")
        self.ms = self.ones if ex.fill_short is None else self._m1_mask(ex.fill_short, "fill_short")
        self.free = ia
        self.out = [{k: [] for k in ("dir", "eix", "epx", "xix", "xpx", "why", "risk")} for _ in self.legs]
        self.meta = {k: [] for k in ("tag", "bar", "gap")}       # gap: the M1 bar of a close_gap exit (-1 none)
        self.counts = {k: 0 for k in COUNT_KEYS}

    def _m1_mask(self, x, name: str) -> np.ndarray:
        a = np.ascontiguousarray(np.asarray(x, np.bool_))
        if a.shape != (len(self.cm.t),):
            raise ValueError(f"{name}: a mask per M1 bar of the market ({len(self.cm.t)}), got {a.shape}")
        return a

    # one position: its plan's rows after the entry row, and its run
    def _rows_after(self, d: int, fill: float, b_from: int, xb: int) -> Tuple[List[Tuple[int, float]], int, bool]:
        """The tightening rows (M1 bar, level) of a position of side ``d`` filled at ``fill``, decided at bars
        b_from .. xb-1; its first exit decision bar (a tightening already crossed at the open that executes it ends the
        position there: PREREG 4); and whether that happened. The bid (long) or the ask (short) of that open is the
        costed market's, so the x1.5 run compares on its own spread."""
        ov, ex_, cm = self.ov, self.bars.ex, self.cm
        rows: List[Tuple[int, float]] = []
        idx, lev = ov.tix[d], ov.tlev[d]
        if lev is None or len(idx) == 0:
            return rows, xb, False
        lo = int(np.searchsorted(idx, b_from, side="left"))
        hi = int(np.searchsorted(idx, xb, side="left"))
        for b in idx[lo:hi]:
            b = int(b)
            jb = int(ex_[b])
            if jb >= self.iz:
                break
            L = float(lev[b])
            if ov.tbe[b]:
                L = max(L, fill) if d == 1 else min(L, fill)
            px_open = cm.o[jb] if d == 1 else cm.o[jb] + cm.sp[jb]
            if (d == 1 and L >= px_open) or (d == -1 and L <= px_open):
                return rows, b, True
            rows.append((jb, L))
        return rows, xb, False

    def _count_tight(self, rows: List[Tuple[int, float]], xb: int, crossed: bool, ps: List[X.Path_]) -> None:
        """Count the tightenings that acted: the rows executed while the position was open (before its exit, or at
        the open of an exit inside that bar), and a crossed tightening that closed it."""
        at_open = (X.WHY_SIGNAL, X.WHY_GAP_STOP, X.WHY_GAP_TARGET)
        last = max(ps, key=lambda p: int(p.xix[0]))
        x, why = int(last.xix[0]), int(last.why[0])
        self.counts["tighten_rows"] += sum(1 for jb, _ in rows if jb < x or (jb == x and why not in at_open))
        if crossed and any(int(p.xix[0]) == int(self.bars.ex[xb]) and int(p.why[0]) == X.WHY_SIGNAL for p in ps):
            self.counts["tighten_exits"] += 1

    def _gap_exit(self, xb: int, jf: int) -> int:
        """
        Where a close_gap row's own exit decision at the close of bar ``xb`` is booked (harness reading 15): the M1
        bar ``bars.i1[xb]``, at whose close it is booked, when no M1 bar opens at the bar's close (the bar that would
        execute the exit, ``bars.ex[xb]``, opens after ``bars.tc[xb]``: an early close, a weekend, a data hole) and that
        M1 bar is inside the window; -1 otherwise: an M1 bar opening at the close (no gap: the exit fills at its open as
        before), no M1 bar after the bar in the data held (their end, not a gap), or the bar's last M1 bar past the
        window (the window's end closes the position, as before). ``jf``: the position's fill M1 bar, which that close
        cannot precede (``xb`` is later than an entry's bar, and never before an order fill's bar).
        """
        b, t = self.bars, self.cm.t
        jx = int(b.ex[xb])
        if jx >= len(t) or int(t[jx]) <= int(b.tc[xb]):
            return -1
        x = int(b.i1[xb])
        if not x < jx:
            raise AssertionError(f"bar {xb}: its last M1 bar is not before the M1 bar that executes its close")
        if x >= self.iz:
            return -1
        if x < jf:
            raise AssertionError(f"a close_gap exit at the close of {utc(t[x])} comes before the position's fill at "
                                 f"{utc(t[jf])}")
        return x

    def _plan(self, j: int, entry: Dict[str, float], rows: List[Tuple[int, float]], xb: int, d: int,
              order: Optional[Dict[str, float]] = None, gap_ix: int = -1) -> Tuple[X.PathPlan, Optional[int]]:
        """The position's plan: the entry (or order) row at M1 bar ``j``, the tightening rows, the exit row (at
        ``bars.ex[xb]`` when that is inside the window). With ``gap_ix`` >= 0 (a close_gap exit, ``_gap_exit``) there
        is no exit row: the run ends after M1 bar ``gap_ix`` and ``external._path_kernel``'s end-of-period exit closes
        what is still open at that bar's close (``X.WHY_END``), exactly as at a window's end. Returns the plan and the
        run's end (None: no exit row, the window's end)."""
        t, ex_ = self.cm.t, self.bars.ex
        z = None
        dx = [j] + [jb for jb, _ in rows]
        exit_row = False
        if gap_ix >= 0:
            if max(dx) > gap_ix:
                raise AssertionError("a row of the position's plan executes after its close_gap exit")
            z = gap_ix + 1
        elif xb < self.n and int(ex_[xb]) < self.iz:
            dx.append(int(ex_[xb]))
            z = int(ex_[xb]) + 1
            exit_row = True
        K = len(dx)
        dt = t[np.asarray(dx, np.int64)]
        want = np.zeros(K, np.int64)
        xl = np.zeros(K, np.bool_)
        xs = np.zeros(K, np.bool_)
        if exit_row:
            xl[-1], xs[-1] = d == 1, d == -1
        f = {k: np.full(K, np.nan) for k in ("sl", "tp", "tpr", "ber", "rk", "trl", "trs", "bstop", "sstop",
                                             "bsl", "ssl")}
        if order is None:
            want[0] = d
        for k, v in entry.items():
            f[k][0] = v
        if order is not None:
            for k, v in order.items():
                f[k][0] = v
        tcol = "trl" if d == 1 else "trs"
        for q, (_, L) in enumerate(rows):
            f[tcol][q + 1] = L
        plan = X.make_plan(self.cm, dt, want=want, xl=xl, xs=xs, **f)
        if len(plan) != K or not np.array_equal(plan.dx, np.asarray(dx, np.int64)):
            raise AssertionError("a row of the position's plan does not execute at its M1 bar")
        plan.m_l, plan.m_s = self.ml, self.ms
        return plan, z

    def _run(self, plan: X.PathPlan, j: int, z: Optional[int]) -> X.Path_:
        """Run a one-position plan from M1 bar j to z (or, without an exit row, in growing chunks to the window end:
        a position still open at a chunk's end is run again with a longer one)."""
        chunk = CHUNK
        while True:
            zz = z if z is not None else min(self.iz, j + chunk)
            p = X.run_path(self.cm, plan, j, zz)
            if len(p) != 1:
                raise AssertionError(f"a one-position plan made {len(p)} trades")
            if z is None and int(p.why[0]) == X.WHY_END and zz < self.iz:
                chunk *= 8
                continue
            return p

    def _targets(self, d: int, fill: float, own: Dict[str, float], c: int, kind: str) -> Optional[List[Dict[str, float]]]:
        """Per leg: the kernel fields of its target and break-even (tp from an absolute level from the actual fill),
        or None when the fill is at or beyond one of the targets (the entry is dropped). ``c``: the entry's row (an
        EVENTS Exec) or its decision bar (a STATE Exec), which indexes a leg's per-entry arrays."""
        out = []
        for g in self.legs:
            if g.own_target:
                if kind == "entry":
                    lv = _leg_value(g.target_level, c)
                else:
                    lv = _leg_value(g.buy_target if d == 1 else g.sell_target, c)
                td, tr = _leg_value(g.target_dist, c), _leg_value(g.target_r, c)
                if g.no_target:
                    lv = td = tr = np.nan
                if sum(math.isfinite(x) for x in (lv, td, tr)) > 1:
                    raise ValueError("a leg gives more than one target")
            else:
                lv, td, tr = own["level"], own["dist"], own["r"]
            be = own["be"] if g.be_r is None else _leg_value(g.be_r, c)
            f: Dict[str, float] = {}
            if math.isfinite(lv):
                dist = d * (lv - fill)
                if not dist > 0:
                    return None
                f["tp"] = dist
            elif math.isfinite(td):
                f["tp"] = td
            elif math.isfinite(tr):
                f["tpr"] = tr
            if math.isfinite(be):
                f["ber"] = be
            out.append(f)
        return out

    def _book(self, ps: List[X.Path_], tag: int, bar: int, gap_ix: int = -1) -> None:
        """Book a position's legs. The next candidate may fill at the M1 bar of an exit at an open, else from the bar
        after its exit; a close_gap exit (``gap_ix``) is an exit at that bar's close (``X.WHY_END``): from the next."""
        free = 0
        for q, p in enumerate(ps):
            o = self.out[q]
            for k in ("dir", "eix", "epx", "xix", "xpx", "why", "risk"):
                o[k].append(getattr(p, k)[0])
            x, why = int(p.xix[0]), int(p.why[0])
            free = max(free, x if why in (X.WHY_SIGNAL, X.WHY_GAP_STOP, X.WHY_GAP_TARGET) else x + 1)
        self.free = free
        self.meta["tag"].append(tag)
        self.meta["bar"].append(bar)
        self.meta["gap"].append(gap_ix)
        self.counts["taken"] += 1
        if gap_ix >= 0 and any(int(p.why[0]) == X.WHY_END and int(p.xix[0]) == gap_ix for p in ps):
            self.counts["close_gap"] += 1

    def _needs_stop(self, sl: float, legs_f: List[Dict[str, float]]) -> None:
        if not math.isfinite(sl) and any(("tpr" in f) or ("ber" in f) for f in legs_f):
            raise ValueError("an R target or a break-even move needs a stop (its initial risk)")

    # the candidates
    def entries(self, E: Entries, a_s: int) -> None:
        bars, cm = self.bars, self.cm
        if len(E) and (E.bar.min() < 0 or E.bar.max() >= self.n or E.exit_bar.max() >= self.n):
            raise ValueError("an entry's bar or exit bar is outside the bars")
        ex_ = bars.ex
        win = (bars.tc[E.bar] > a_s) & (ex_[E.bar] < self.iz)
        idx = np.flatnonzero(win)
        idx = idx[np.argsort(ex_[E.bar[idx]], kind="stable")]
        self.counts["candidates"] += int(len(idx))
        for c in idx:
            c = int(c)
            e = int(E.bar[c])
            j = int(ex_[e])
            if j < self.free:
                self.counts["busy"] += 1
                continue
            d = int(E.side[c])
            fill = cm.o[j] + cm.sp[j] if d == 1 else cm.o[j]
            sl = np.nan
            if math.isfinite(E.stop_level[c]):
                sl = d * (fill - E.stop_level[c])
                if not sl > 0:
                    self.counts["dropped_stop"] += 1
                    continue
            elif math.isfinite(E.stop_dist[c]):
                sl = float(E.stop_dist[c])
            own = {"level": float(E.target_level[c]), "dist": float(E.target_dist[c]), "r": float(E.target_r[c]),
                   "be": float(E.be_r[c])}
            legs_f = self._targets(d, fill, own, e if self.by_bar else c, "entry")
            if legs_f is None:
                self.counts["dropped_target"] += 1
                continue
            self._needs_stop(sl, legs_f)
            own = int(E.exit_bar[c]) if E.exit_bar[c] >= 0 else self.n       # the row's own fixed exit (n: none)
            xb = min(own, int(self.ov.nxt[d][e + 1]))
            rows, xb, crossed = self._rows_after(d, fill, e + 1, xb)
            # close_gap: only when the row's own exit is what ends the position (an exit mask or a crossed
            # tightening that ends it first fills at its open as before)
            gx = self._gap_exit(xb, j) if (E.close_gap[c] and own < self.n and xb == own) else -1
            base = {"sl": sl}
            if math.isfinite(E.risk[c]):
                base["rk"] = float(E.risk[c])
            ps = []
            for f in legs_f:
                plan, z = self._plan(j, {**base, **f}, rows, xb, d, gap_ix=gx)
                p = self._run(plan, j, z)
                if int(p.eix[0]) != j or float(p.epx[0]) != fill or int(p.dir[0]) != d:
                    raise AssertionError("a market entry did not fill at its bar's open")
                ps.append(p)
            self._count_tight(rows, xb, crossed, ps)
            self._book(ps, int(E.tag[c]), e, gx)

    def orders(self, O: Orders, a_s: int) -> None:
        bars, cm, t = self.bars, self.cm, self.cm.t
        if len(O) and (O.bar.min() < 0 or O.bar.max() >= self.n or O.exit_bar.max() >= self.n):
            raise ValueError("an order's bar or exit bar is outside the bars")
        ex_ = bars.ex
        win = (bars.tc[O.bar] > a_s) & (ex_[O.bar] < self.iz)
        idx = np.flatnonzero(win)
        idx = idx[np.argsort(ex_[O.bar[idx]], kind="stable")]
        starts = ex_[O.bar[idx]]
        if len(starts) > 1 and np.any(np.diff(starts) == 0):
            raise ValueError("two orders placed at the same M1 open (put both sides in one order)")
        self.counts["candidates"] += int(len(idx))
        for q, c in enumerate(idx):
            c = int(c)
            j0 = max(int(starts[q]), self.free)
            jz = min(int(np.searchsorted(t, O.until[c], side="left")), self.iz)
            if q + 1 < len(idx):
                jz = min(jz, int(starts[q + 1]))                     # a newer order replaces this one
            if j0 >= jz:
                self.counts["busy" if int(starts[q]) < self.free else "unfilled"] += 1
                continue
            order = {"bstop": float(O.buy[c]), "sstop": float(O.sell[c]), "bsl": float(O.buy_stop[c]),
                     "ssl": float(O.sell_stop[c]), "sl": float(O.stop_dist[c])}
            plan1, _ = self._plan(j0, {}, [], self.n, 1, order=order)
            p1 = X.run_path(cm, plan1, j0, jz)
            if len(p1) == 0:
                self.counts["unfilled"] += 1
                continue
            jf, fill, d = int(p1.eix[0]), float(p1.epx[0]), int(p1.dir[0])
            lvl = O.buy_stop[c] if d == 1 else O.sell_stop[c]
            if math.isfinite(lvl):
                sl = d * (fill - lvl)
                if not sl > 0:
                    self.counts["dropped_stop"] += 1
                    continue
            else:
                sl = float(O.stop_dist[c])
            own = {"level": float(O.buy_target[c] if d == 1 else O.sell_target[c]), "dist": float(O.target_dist[c]),
                   "r": float(O.target_r[c]), "be": float(O.be_r[c])}
            legs_f = self._targets(d, fill, own, c, "order")
            if legs_f is None:
                self.counts["dropped_target"] += 1
                continue
            self._needs_stop(sl, legs_f)
            bf = int(np.searchsorted(bars.i0, jf, side="right") - 1)
            if jf > int(bars.i1[-1]):
                bf = self.n             # no signal bar holds the fill (1D: a trailing short day): no bar exits it
            elif not (bf >= 0 and bars.i0[bf] <= jf <= bars.i1[bf]):
                raise AssertionError("a fill outside the signal bars")
            xb = int(O.exit_bar[c]) if O.exit_bar[c] >= 0 else self.n
            if self.ex.on_fill is not None and bf < self.n:
                xf = int(self.ex.on_fill(bf, d))
                if xf >= 0:
                    if xf < bf:
                        raise ValueError(f"on_fill returned exit bar {xf} before the fill's bar {bf}")
                    xb = min(xb, xf)
            xb = max(xb, bf)
            own = xb                                    # the order's own fixed exit: exit_bar or on_fill's (n: none)
            xb = min(xb, int(self.ov.nxt[d][bf]))
            rows, xb, crossed = self._rows_after(d, fill, bf, xb)
            gx = self._gap_exit(xb, jf) if (O.close_gap[c] and own < self.n and xb == own) else -1
            base = dict(order)
            if math.isfinite(O.risk[c]):
                base["rk"] = float(O.risk[c])
            ps = []
            for f in legs_f:
                plan, z = self._plan(j0, {}, rows, xb, d, order={**base, **f}, gap_ix=gx)
                p = self._run(plan, j0, z)
                if int(p.eix[0]) != jf or float(p.epx[0]) != fill or int(p.dir[0]) != d:
                    raise AssertionError("a stop order did not fill as in its first pass")
                ps.append(p)
            self._count_tight(rows, xb, crossed, ps)
            self._book(ps, int(O.tag[c]), bf, gx)

    def paths(self) -> List[X.Path_]:
        """Per leg, the positions as an ``external.Path_`` (one leg per trade), before the stop slippage."""
        out = []
        for o in self.out:
            nt = len(o["dir"])
            a = {k: np.asarray(o[k], np.float64 if k in ("epx", "xpx", "risk") else np.int64) for k in o}
            out.append(X.Path_(dir=a["dir"], eix=a["eix"], epx=a["epx"], xix=a["xix"], xpx=a["xpx"], why=a["why"],
                               risk=a["risk"], expo=np.full(nt, np.nan), leg0=np.arange(nt, dtype=np.int64),
                               nleg=np.ones(nt, np.int64), leix=a["eix"].copy(), lepx=a["epx"].copy()))
        return out


def _leg_value(v, c: int) -> float:
    if v is None:
        return np.nan
    a = np.asarray(v, np.float64)
    return float(a) if a.ndim == 0 else float(a[c])


def _state_entries(ex: Exec, bars: TM.TBars, a_s: int, iz: int) -> Tuple[Entries, int]:
    """The entries study 1's ``run`` would make from ``ex.state`` over the window (DEVIATIONS 1, 2, 7): at the
    window's first bar and wherever the state changes, unless the new state is flat; each with its exit decision at
    the next change. Returns them and the number of decision bars in the window."""
    st = ex.state
    sel = np.flatnonzero((bars.tc > a_s) & (bars.ex < iz))
    if len(sel) == 0:
        return entries(np.zeros(0, np.int64), np.zeros(0, np.int64)), 0
    if not np.all(np.diff(sel) == 1):
        raise AssertionError("window bars are not contiguous")
    s = st[sel]
    prev = np.where(sel >= 1, st[np.maximum(sel - 1, 0)], 0)
    changed = s != prev
    changed[0] = True
    ch = np.flatnonzero(changed)
    ent = ch[s[ch] != 0]
    nxt = np.searchsorted(ch, ent, side="right")
    exit_bar = np.where(nxt < len(ch), sel[ch[np.minimum(nxt, len(ch) - 1)]], -1)
    bar = sel[ent]
    stop = None
    if ex.stop is not None:
        if ex.stop.shape != (len(bars),):
            raise ValueError(f"stop has shape {ex.stop.shape}, the bars {len(bars)}")
        stop = ex.stop[bar]
        bad = ~(np.isfinite(stop) & (stop > 0))
        if bad.any():
            raise ValueError(f"no valid stop distance at the entry decided at {utc(bars.tc[bar[bad][0]])}: "
                             f"{stop[bad][0]}")
    tr = _bar_array(ex.target_r, len(bars), "target_r")
    be = _bar_array(ex.be_r, len(bars), "be_r")
    return entries(bar, s[ent], stop_dist=stop, target_r=None if tr is None else tr[bar],
                   be_r=None if be is None else be[bar], exit_bar=exit_bar), int(len(sel))


def _check_exec(ex: Exec, bars: TM.TBars) -> None:
    n = len(bars)
    if ex.state is not None:
        TM._states(ex.state, n)
        if ex.entries is not None or ex.orders is not None:
            raise ValueError("a STATE Exec has no entries or orders")
        if ex.on_fill is not None or ex.fill_long is not None or ex.fill_short is not None:
            raise ValueError("on_fill and fill masks are for orders")
    elif (ex.entries is None) == (ex.orders is None):
        raise ValueError("an event Exec has entries or orders (one of them)")
    for k in ("exit_long", "exit_short", "tighten_long", "tighten_short", "tighten_be"):
        v = getattr(ex, k)
        if v is not None and np.asarray(v).shape != (n,):
            raise ValueError(f"{k} has shape {np.asarray(v).shape}, the bars {n}")


def _window(mk: TMarket2, start, end) -> Tuple[int, int, int, int]:
    a_s, z_s = s_of(start), s_of(end)
    _score_guard(mk.symbol, a_s, z_s, f"window {utc(a_s)} .. {utc(z_s)}")
    return TM._window_ix(mk, a_s, z_s)


def _with_r(tr: pd.DataFrame, risk: np.ndarray, k: float) -> pd.DataFrame:
    tr = tr.copy()
    risk = np.asarray(risk, np.float64)
    tr["risk"] = risk
    with np.errstate(divide="ignore", invalid="ignore"):
        tr["r"] = np.where(np.isfinite(risk) & (risk > 0), tr.pnl.to_numpy() / (k * risk), np.nan)
    return tr


def _gap_exits(p: X.Path_, gap: Optional[np.ndarray]) -> np.ndarray:
    """Per trade of the leg path ``p`` (one per position): True where a close_gap exit closed it, i.e. its exit is
    the end-of-run exit (``X.WHY_END``) at the M1 bar its position's close_gap booked (``gap``, -1 none)."""
    if gap is None or len(p) == 0:
        return np.zeros(len(p), bool)
    gap = np.asarray(gap, np.int64)
    return (gap >= 0) & (p.why == X.WHY_END) & (p.xix == gap)


def _as_time_exits(tr: pd.DataFrame, mask: np.ndarray) -> pd.DataFrame:
    """The trade rows of close_gap exits (``mask``) read as time exits: reason 'signal' (``X.WHY_SIGNAL``'s name).
    Their exit price, time (the M1 bar's close) and ``exit_ix`` are those of the close they were booked at."""
    if len(mask) and bool(np.any(mask)):
        reason = tr["reason"].to_numpy(dtype=object).copy()
        reason[mask] = TM.REASONS[X.WHY_SIGNAL]
        tr["reason"] = reason
    return tr


def _run_single(mk: TMarket2, ex: Exec, bars: TM.TBars, a_s: int, z_s: int, ia: int, iz: int, cost: float) -> Run2:
    """One STATE or EVENTS Exec over one window (see ``run_exec``)."""
    cm = mk.costed(cost)
    _check_exec(ex, bars)
    if ex.state is not None and not ex.overlays:
        r = TM.run(mk, bars, ex.state, a_s, z_s, stop=ex.stop, cost=cost)
        tr = _with_r(r.trades, r.path.risk, cm.k)
        tr["tag"], tr["bar"], tr["lane"] = 0, np.searchsorted(bars.ex, tr.entry_ix.to_numpy()), 0
        counts = {k: 0 for k in COUNT_KEYS}
        counts["candidates"] = counts["taken"] = int(len(r.path))       # a state rule takes every change
        return Run2(**{f: getattr(r, f) for f in TM.Run.__dataclass_fields__ if f != "trades"}, trades=tr,
                    kind="state", legs=((1.0, r.path),), counts=counts, label=ex.label)
    sim = _Sim(mk, cm, bars, ex, ia, iz)
    if ex.state is not None:
        E, n_dec = _state_entries(ex, bars, a_s, iz)
        sim.entries(E, a_s)
    elif ex.entries is not None:
        sim.entries(ex.entries, a_s)
        n_dec = sim.counts["candidates"]
    else:
        sim.orders(ex.orders, a_s)
        n_dec = sim.counts["candidates"]
    paths = [TM._stop_slippage(cm, p) for p in sim.paths()]
    weights = [float(g.weight) for g in sim.legs]
    tags = np.asarray(sim.meta["tag"], np.int64)
    bar_of = np.asarray(sim.meta["bar"], np.int64)
    gap = np.asarray(sim.meta["gap"], np.int64)
    stopped = _has_stop(ex)
    if len(paths) == 1:
        p = paths[0]
        ec, ew, pos, bal, maxdd = TM._unit_marks(cm.c, cm.h, cm.l, cm.sp, cm.k, p.dir, p.eix, p.xix, p.epx, p.xpx,
                                                 p.why, ia, iz)
        tr = _as_time_exits(_with_r(TM._trades(cm, p), p.risk, cm.k), _gap_exits(p, gap))
        path = p
    else:
        tr, ec, ew, pos, bal, maxdd = _combine_legs(cm, paths, weights, ia, iz, gap)
        path = _NoSinglePath()
    tr["tag"], tr["bar"], tr["lane"] = tags, bar_of, 0
    net = float(bal)
    if abs(net - float(tr.pnl.sum())) > 1e-6 * max(1.0, abs(net)):
        raise AssertionError("the equity curve and the trades disagree")
    return Run2(mk.symbol, bars.tf, str(utc(a_s)), str(utc(z_s)), a_s, z_s, ia, iz, float(cost), stopped, cm, path,
                tr, ec, ew, pos, net, float(maxdd), int(n_dec), kind=ex.kind,
                legs=tuple(zip(weights, paths)), counts=dict(sim.counts), label=ex.label)


def _has_stop(ex: Exec) -> bool:
    if ex.entries is not None:
        return bool(np.isfinite(ex.entries.stop_level).any() or np.isfinite(ex.entries.stop_dist).any())
    if ex.orders is not None:
        o = ex.orders
        return bool(np.isfinite(o.buy_stop).any() or np.isfinite(o.sell_stop).any() or np.isfinite(o.stop_dist).any())
    return ex.stop is not None


def _flat_trades(parts: Sequence[Tuple[float, X.Path_]]) -> Dict[str, np.ndarray]:
    """Every leg-trade of ``parts`` (weight, path) as weighted rows sorted by entry bar (stable)."""
    cols = {k: np.concatenate([getattr(p, k) for _, p in parts]) for k in ("dir", "eix", "epx", "xix", "xpx", "why",
                                                                           "risk")}
    cols["w"] = np.concatenate([np.full(len(p), w) for w, p in parts])
    order = np.argsort(cols["eix"], kind="stable")
    return {k: v[order] for k, v in cols.items()}


def _marks(cm: TM.TMarket, parts: Sequence[Tuple[float, X.Path_]], ia: int, iz: int):
    f = _flat_trades(parts)
    return _sum_marks(cm.c, cm.h, cm.l, cm.sp, float(cm.k), f["dir"].astype(np.int64), f["w"].astype(np.float64),
                      f["eix"].astype(np.int64), f["xix"].astype(np.int64), f["epx"].astype(np.float64),
                      f["xpx"].astype(np.float64), f["why"].astype(np.int64), int(ia), int(iz))


def _combine_legs(cm: TM.TMarket, paths: Sequence[X.Path_], weights: Sequence[float], ia: int, iz: int,
                  gap: Optional[np.ndarray] = None):
    """One trades row per position from its legs (identical entries; ``tradeiq_market._trades`` per leg): the weighted
    P/L, slippage and exit price, the exit time, bar and reason of the last leg out (a tie: the later leg), every leg's
    reason in ``reasons`` (a leg a close_gap exit closed, ``gap`` per position, reads 'signal'); and the marks of the
    weighted sum (``_sum_marks``)."""
    per = [_as_time_exits(TM._trades(cm, p), _gap_exits(p, gap)) for p in paths]
    n = len(per[0])
    if any(len(x) != n for x in per) or any(not np.array_equal(p.eix, paths[0].eix) for p in paths) or \
            any(not np.array_equal(p.epx, paths[0].epx) for p in paths):
        raise AssertionError("the legs' entries differ")
    w = np.asarray(weights, np.float64)
    exit_s = np.stack([cm.t[p.xix] + np.where(p.why == X.WHY_END, 60, 0) for p in paths]) if n else \
        np.zeros((len(paths), 0), np.int64)
    order_key = exit_s * len(paths) + np.arange(len(paths))[:, None]
    last = np.argmax(order_key, axis=0) if n else np.zeros(0, np.int64)
    cols = np.arange(n)
    entry_s = cm.t[paths[0].eix]
    xs = exit_s[last, cols] if n else np.zeros(0, np.int64)
    reasons = np.stack([x.reason.to_numpy(dtype=object) for x in per]) if n else np.zeros((len(per), 0), object)
    tr = pd.DataFrame({
        "entry_time": pd.to_datetime(entry_s, unit="s", utc=True),
        "exit_time": pd.to_datetime(xs, unit="s", utc=True),
        "side": paths[0].dir.astype(np.int64),
        "entry": paths[0].epx,
        "exit": np.sum([wi * x.exit.to_numpy() for wi, x in zip(w, per)], axis=0) if n else np.zeros(0),
        "reason": reasons[last, cols] if n else np.zeros(0, object),
        "pnl": np.sum([wi * x.pnl.to_numpy() for wi, x in zip(w, per)], axis=0) if n else np.zeros(0),
        "slippage": np.sum([wi * x.slippage.to_numpy() for wi, x in zip(w, per)], axis=0) if n else np.zeros(0),
        "hold_h": (xs - entry_s) / 3600.0,
        "entry_ix": paths[0].eix.astype(np.int64),
        "exit_ix": np.stack([p.xix for p in paths])[last, cols].astype(np.int64) if n else np.zeros(0, np.int64),
        "reasons": ["|".join(str(v) for v in reasons[:, i]) for i in range(n)],
    })
    tr = _with_r(tr, paths[0].risk, cm.k)
    ec, ew, pos, bal, maxdd = _marks(cm, list(zip(w, paths)), ia, iz)
    return tr, ec, ew, pos, bal, maxdd


def run_exec(mk: TMarket2, ex: Exec, start, end, cost: float = 1.0) -> Run2:
    """
    Execute ``ex`` over [start, end) at spread multiplier ``cost`` (1.0, or 1.5 for the stress) and return a ``Run2``.
    The window is scored as a continuous run that starts flat; the indicators behind ``ex`` see all the history
    before it. A STATE Exec without overlays is ``tradeiq_market.run`` itself; everything else runs one position at a
    time on ``external.make_plan`` / ``external.run_path`` with study 1's ``_stop_slippage``, ``_unit_marks`` (one
    leg) and ``_trades``. Lanes are run one by one and summed. Study 2's guard applies to the market and the window.
    """
    if not isinstance(mk, TMarket2) or mk.cost != 1.0:
        raise TypeError("run_exec() takes the TMarket2 itself (tradeiq2_market.load); the cost copy is made here")
    if not isinstance(ex, Exec):
        raise TypeError("run_exec() takes an Exec (state_exec / event_exec / lanes_exec)")
    _guard(int(mk.t[-1]) + 60, f"{mk.symbol} market")
    a_s, z_s, ia, iz = _window(mk, start, end)
    if ex.kind != "lanes":
        return _run_single(mk, ex, mk.tbars(ex.tf), a_s, z_s, ia, iz, cost)
    runs = [_run_single(mk, x, mk.tbars(x.tf), a_s, z_s, ia, iz, cost) for x in ex.lanes]
    cm = runs[0].m
    parts = [(w, p) for r in runs for (w, p) in r.legs]
    ec, ew, pos, bal, maxdd = _marks(cm, parts, ia, iz)
    trs = []
    for q, r in enumerate(runs):
        tr = r.trades.copy()
        tr["lane"] = q
        trs.append(tr)
    tr = pd.concat(trs, ignore_index=True)
    tr = tr.iloc[np.argsort(tr.entry_ix.to_numpy(), kind="stable")].reset_index(drop=True)
    net = float(bal)
    if abs(net - float(tr.pnl.sum())) > 1e-6 * max(1.0, abs(net)):
        raise AssertionError("the lanes' equity and their trades disagree")
    counts = {key: int(sum(r.counts.get(key, 0) for r in runs)) for key in COUNT_KEYS}
    return Run2(mk.symbol, ex.tf, str(utc(a_s)), str(utc(z_s)), a_s, z_s, ia, iz, float(cost),
                any(r.stopped for r in runs), cm, _NoSinglePath(), tr, ec, ew, pos, net, float(maxdd),
                int(sum(r.n_decisions for r in runs)), kind="lanes", legs=tuple(parts), lanes=tuple(runs),
                counts=counts, label=ex.label)


# ───────────────────────────── scores and accounts (PREREG 7) ─────────────────────────────

def r_stats(r: Run2) -> Dict[str, float]:
    """R-multiple statistics over the trades that have an initial risk (a stop, or an entry's ``risk``): their number,
    the average R, the profit factor in R, the win rate in % (R > 0) and the total R. R = the trade's P/L after costs
    (legs combined) over k x its initial risk distance from the fill."""
    R = r.trades["r"].to_numpy(np.float64) if "r" in r.trades.columns else np.zeros(0)
    R = R[np.isfinite(R)]
    pos, neg = R[R > 0].sum(), -R[R < 0].sum()
    return {"r_trades": int(len(R)), "avg_r": float(R.mean()) if len(R) else np.nan,
            "pf_r": float(pos / neg) if neg > 0 else (np.inf if pos > 0 else np.nan),
            "win_rate_r": 100.0 * float((R > 0).mean()) if len(R) else np.nan, "total_r": float(R.sum())}


def metrics(r: Run2) -> Dict[str, object]:
    """``tradeiq_market.metrics`` (PREREG 7 per 0.01 lot after costs) after study 2's guard, plus ``r_stats``, the
    run's kind and its counts (candidates, taken, busy, dropped_stop, dropped_target, unfilled, tighten_rows,
    tighten_exits)."""
    _score_guard(r.symbol, r.a_s, r.z_s, f"{r.symbol} run")
    out = TM.metrics(r)
    out.update(r_stats(r))
    out["kind"] = getattr(r, "kind", "state")
    out.update({f"n_{k}": int(v) for k, v in getattr(r, "counts", {}).items()})
    return out


SCORE_KEYS = ("net", "trades", "win_rate", "profit_factor", "max_dd", "profit_dd", "pos_q", "n_q", "pos_q_share",
              "sharpe_w", "avg_hold_h", "time_in_mkt", "max_losing_streak", "avg_win", "avg_loss", "best_trade",
              "worst_trade", "n_long", "n_short", "long_pnl", "short_pnl", "n_stops", "slippage", "weeks", "sr_w_raw",
              "skew_w", "kurt_w", "n_q_exposed", "n_decisions", "r_trades", "avg_r", "pf_r", "win_rate_r", "total_r")


def scores(r: Run2) -> Dict[str, float]:
    """PREREG 7 for one run, unrounded, in study 1's ``scores`` columns plus the R statistics and the counts."""
    m = metrics(r)
    pnl = r.trades.pnl.to_numpy(np.float64)
    w, lo = pnl[pnl > 0], pnl[pnl < 0]
    gw, gl = float(w.sum()), float(-lo.sum())
    out = {
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
    out.update({k: m[k] for k in ("r_trades", "avg_r", "pf_r", "win_rate_r", "total_r")})
    out.update({k: v for k, v in m.items() if k.startswith("n_") and k not in out})
    return out


def account_curve(r: Run2, sizing: X.Sizing = X.BOT) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """
    PREREG 4 / 7's $2,000 account with the bot's unit rule (unit = floor(balance / 2,500) + 1, at most 10, set when a
    position opens), marked at the worst price of each M1 bar, wiped at equity 0. One leg and one lane: study 1's
    ``account_curve`` (``external.account``). Legs or lanes: ``balke._multi_kernel`` (each trade sized from the
    balance when it opens; legs open together, so they get the same unit, and the leg weight scales its P/L: the
    "50/50 mix per unit" of PREREG 4, which live needs at least 0.02 lot per unit). Returns the equity at every UTC
    midnight and a summary, as study 1's.
    """
    _score_guard(r.symbol, r.a_s, r.z_s, f"{r.symbol} run")
    if r.single:
        return TM.account_curve(r, sizing)
    if sizing.mode != "bot" or sizing.brake or sizing.cap_lev:
        raise ValueError("legs and lanes: only the bot's unit rule")
    from . import balke as B
    f = _flat_trades(r.legs)
    w = np.unique(f["w"]) if len(f["w"]) else np.ones(1)
    if len(w) != 1:
        raise ValueError(f"legs of unequal weights {list(w)}: the multi-position account takes one weight")
    cm = r.m
    e = TM._edges_days(r.a_s, r.z_s)
    bnd = np.concatenate([[r.ia], r.ia + np.searchsorted(cm.t[r.ia:r.iz], e[1:-1], side="left"), [r.iz]])
    steps, pnl, bal, dd, wiped, wix, n_done, eqb = B._multi_kernel(
        cm.c, cm.h, cm.l, cm.sp, float(cm.k) * float(w[0]), f["eix"].astype(np.int64), f["epx"].astype(np.float64),
        f["xix"].astype(np.int64), f["xpx"].astype(np.float64), f["why"].astype(np.int64), f["dir"].astype(np.int64),
        f["risk"].astype(np.float64), np.full(len(f["eix"]), np.nan), 0, 0.0, int(r.ia), int(r.iz),
        np.asarray(bnd[1:-1], np.int64), X.ACCOUNT, X.STEP_UP, float(X.UNIT_MAX))
    blocks = np.concatenate([[X.ACCOUNT], eqb, [bal]])
    curve = pd.DataFrame({"time": pd.to_datetime(e, unit="s", utc=True), "equity": blocks})
    done = np.arange(len(steps)) < n_done
    summary = {"start_equity": X.ACCOUNT, "final": float(bal), "net": float(bal) - X.ACCOUNT,
               "max_dd_pct": float(dd) * 100.0, "wiped": bool(wiped),
               "wiped_at": str(utc(cm.t[wix])) if wiped else "", "trades": int((done & (steps > 0)).sum()),
               "skipped": int((done & (steps == 0)).sum()),
               "max_units": float(steps[done].max()) if done.any() else np.nan,
               "positions": int(len(r.trades)), "leg_weight": float(w[0])}
    return curve, summary


def unit_curve(r: Run2) -> pd.DataFrame:
    """Daily per-unit equity of the run (``tradeiq_market.unit_curve``), after study 2's guard."""
    _score_guard(r.symbol, r.a_s, r.z_s, f"{r.symbol} run")
    return TM.unit_curve(r)


def buy_and_hold(mk: TMarket2, start, end, cost: float = 1.0) -> Dict[str, float]:
    """The reference (PREREG 7): ``tradeiq_market.buy_and_hold`` after study 2's guard."""
    a_s, z_s = s_of(start), s_of(end)
    _score_guard(mk.symbol, a_s, z_s, f"buy-and-hold {utc(a_s)} .. {utc(z_s)}")
    return TM.buy_and_hold(mk, a_s, z_s, cost)


# ───────────────────────────── variants over windows ─────────────────────────────

def _suffix(cost: float) -> str:
    return "" if cost == 1.0 else "_x" + f"{cost:g}".replace(".", "")


def _quarter_label(t: int) -> str:
    ts = utc(t)
    return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"


@dataclass
class VariantResult:
    """``run_variant``'s output: ``rows`` (one per window: the variant's identity, the window, its span, and every
    score at x1.0 and with the suffix ``_x15`` at x1.5), ``trades`` (the windows in ``trades_windows``, both costs),
    ``quarters`` and ``weekly`` (the P/L per calendar quarter and per week from Saturday 00:00 UTC, both costs, for
    PREREG 7's quarters and the SPA test), ``curves`` (the daily per-unit equity, when ``keep_curves``) and ``runs``
    (slim ``Run2``s by (window, cost) for ``account_curve``, when ``keep_runs``)."""
    variant: Variant
    rows: List[Dict[str, object]]
    trades: pd.DataFrame
    quarters: pd.DataFrame
    weekly: pd.DataFrame
    curves: pd.DataFrame
    runs: Dict[Tuple[str, float], Run2]


def run_variant(ctx: Context, variant: Variant, ex: Exec, windows: Sequence[str] = RUN_WINDOWS,
                costs: Sequence[float] = COSTS, trades_windows: Sequence[str] = ("dev", "val"),
                keep_runs: bool = False, keep_curves: bool = False) -> VariantResult:
    """
    One variant over the named ``windows`` (PREREG 3; 'early' is gold's) at each cost. Each window is one continuous
    run from flat (``run_exec``). Study 2's guard applies to each window: before FINALISTS.md is frozen only 'dev',
    'val' and 'devval' can be scored, and never 'early' (gold's Early window).
    """
    if variant.symbol != ctx.symbol:
        raise ValueError(f"{variant.id}: not a variant of {ctx.symbol}")
    tfs = {x.tf for x in ex.lanes} if ex.kind == "lanes" else {ex.tf}
    if variant.tf not in tfs and variant.tf != ex.tf:
        raise ValueError(f"{variant.id}: its timeframe {variant.tf} is not the Exec's {ex.tf}")
    rows, trd, qtr, wkl, crv, runs = [], [], [], [], [], {}
    for w in windows:
        a, z = window_span(w, variant.symbol)
        row: Dict[str, object] = {**variant.ident(), "window": w, "start": a, "end": z}
        kept = {}
        for cost in costs:
            r = run_exec(ctx.mk, ex, a, z, cost)
            row.update({k + _suffix(cost): v for k, v in scores(r).items()})
            if w in trades_windows:
                tr = r.trades.drop(columns=["entry_ix", "exit_ix"])
                tr.insert(0, "cost", cost)
                tr.insert(0, "window", w)
                tr.insert(0, "vid", variant.id)
                trd.append(tr)
            kept[cost] = (TM.quarter_pnl(r), TM.weekly_pnl(r))
            if keep_curves:
                uc = TM.unit_curve(r)
                uc.insert(0, "cost", cost)
                uc.insert(0, "window", w)
                uc.insert(0, "vid", variant.id)
                crv.append(uc)
            if keep_runs:
                runs[(w, float(cost))] = r.slim()
        rows.append(row)
        (q0, _, _), (w0, _) = kept[costs[0]]
        q = {"vid": variant.id, "window": w, "quarter": [_quarter_label(x) for x in q0],
             "start": [str(utc(x).date()) for x in q0]}
        wk = {"vid": variant.id, "window": w, "week_start": [str(utc(x)) for x in w0]}
        for cost in costs:
            (qa, pa, ha), (wa, xa) = kept[cost]
            if not (np.array_equal(qa, q0) and np.array_equal(wa, w0)):
                raise AssertionError("the quarters / weeks of the costs differ")
            q["pnl" + _suffix(cost)], q["held" + _suffix(cost)] = pa, ha
            wk["pnl" + _suffix(cost)] = xa
        qtr.append(pd.DataFrame(q))
        wkl.append(pd.DataFrame(wk))
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    return VariantResult(variant, rows, cat(trd), cat(qtr), cat(wkl), cat(crv), runs)


# ───────────────────────────── command line ─────────────────────────────

def spans(store_dir: Path = store.DEFAULT_STORE_DIR) -> pd.DataFrame:
    """The store's span per symbol (the first / last tick of its first / last month's meta.json; no bar is read)."""
    rows = []
    for sym in ALL_SYMBOLS:
        months = store.available_months(sym, store_dir)
        span = store.data_span(sym, store_dir)
        rows.append({"symbol": sym, "months": len(months),
                     "first_month": f"{months[0][0]:04d}-{months[0][1]:02d}" if months else "",
                     "last_month": f"{months[-1][0]:04d}-{months[-1][1]:02d}" if months else "",
                     "first_tick": str(span[0]) if span else "", "last_tick": str(span[1]) if span else "",
                     "load_from": data_start(sym, store_dir), "data_end": DATA_END[sym]})
    return pd.DataFrame(rows)


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backtesting.research.tradeiq2_market")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spans", help="the store's span per symbol")
    f = sub.add_parser("fetch-binance5", help="download and verify the Binance BTCUSDT 5m klines")
    f.add_argument("--last-day", default=TM.BINANCE_LAST_DAY)
    f.add_argument("--force", action="store_true")
    sub.add_parser("check-binance5", help="PREREG 2's check of the 5m klines on the open span")
    args = ap.parse_args(argv)
    if args.cmd == "spans":
        print(spans().to_string(index=False))
    elif args.cmd == "fetch-binance5":
        inv = fetch_binance_5m(args.last_day, force=args.force)
        print(inv.groupby("status").size().to_string())
        print(f"{len(inv)} files, {int(inv.rows.sum())} klines, {int((inv.us_rows > 0).sum())} files with us stamps, "
              f"times ok in all: {bool(inv.times_ok.all())}, slots short of the calendar: "
              f"{int((inv.expected_slots - inv.rows).sum())}, off the grid: {int(inv.off_grid.sum())}")
    elif args.cmd == "check-binance5":
        mk = load(BTC, end=None if frozen() else HOLDOUT_START)
        print(json.dumps(binance_check_5m(mk), indent=1, default=str))


if __name__ == "__main__":
    main()
