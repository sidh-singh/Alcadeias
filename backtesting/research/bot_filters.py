"""
Entry filters on the bots' own designs (study 3): the filters, the regime composition, the guard, the runs, the score.

    python -B -m backtesting.research.bot_filters identity --symbol XAUUSDm --work DIR [--no-full]
    python -B -m backtesting.research.bot_filters identity-turtle --work DIR
    python -B -m backtesting.research.bot_filters dev --design xau_v3lite [--stage singles|pairs] [--ports] [--workers 4]
    python -B -m backtesting.research.bot_filters score            # Development yardstick and candidates
    python -B -m backtesting.research.bot_filters confirm --design xau_v3lite [--workers 4]
    python -B -m backtesting.research.bot_filters select           # candidates, confirmed finalists per design
    python -B -m backtesting.research.bot_filters freeze           # FINALISTS.md + sha256 (opens the guard)
    python -B -m backtesting.research.bot_filters mt               # multiple_testing.csv (PREREG 7)
    python -B -m backtesting.research.bot_filters exam --design xau_v3lite --vids ... [--workers 4]
    python -B -m backtesting.research.bot_filters compare --design xau_v3lite [--vids ...] [--workers 4] [--out DIR]
    python -B -m backtesting.research.bot_filters export [--out DIR] [--compare-dir DIR]

``dev`` runs the base and the always-allow filter first and refuses to run any variant unless the identity filter's
24 accounts equal the base's (PREREG 2). One symbol at a time: a gold per-second prepare of 2021-2026 holds about
2.7 GB, BTC's about twice that; run BTC alone.

The plan is ``backtest_results/bot_filters/PREREG.md`` (frozen; sha256 in ``PREREG.md.sha256``) with
``DEVIATIONS.md``. What was built and checked, with the numbers, is in ``BUILD.md`` there. Nothing under
``backtesting/engine/``, ``config.py`` or the live files is edited: the designs run exactly as FINAL10 runs them and
the filters enter through what already exists.

The five designs (PREREG 2)
---------------------------
* Gold V3-lite, Top 1, Top 2 and BTC Top 2 on the tick engine: ``experiments.live_config(symbol, start, end)`` with
  ``final10.own_designs(symbol)[name]`` (round 4's designs JSON), prepared with M1, M5, M15, H1, H4 (FINAL10's
  ``run_ticks``). Per second with one loop timing for Development and the 5-year account; raw ticks under eight loop
  timings (``analysis.robustness.live_timing(seed)``, seeds 1-8) for the confirmation and the exam.
* BTC Turtle System 2 + the bot's votes on ``external.py``'s M1-bar model: ``external.filtered(external.turtle(m, 2)
  .plan, m, bot_signals(m).votes_at)`` with the bot's unit rule, accounts by ``final10._bar_account`` (FINAL10's
  ``run_bars``), the market from 2018-01-01 (``final10.HISTORY_FROM``).
* Accounts: $2,000, nothing withdrawn, the unit rule, Exness bid/ask on every fill, no swap, stop-out at equity 0.

The filters (PREREG 3)
----------------------
Each filter says at every moment whether a long and whether a short may open. Values come from CLOSED bars:

* H1 and H4: the bid bars on UTC boundaries built from the M1 store (``external.tf_bars``, via
  ``tradeiq_market.TMarket.tbars``, exactly study 1's bars); D1: UTC days, a day of fewer than 360 M1 bars merged into
  the next (``external.day_bars``). The indicators run over the full history from the symbol's first M1 bar in the
  store (``HISTORY_FROM``: gold from 2016-01 if those months are in the store, else its first bar, 2017-01-03; BTC
  2018-01-01), with Pine semantics (``tradeiq_ind``: ``ta.sma`` and the four verified ports of study 1).
* A bar's value takes effect at the FIRST TICK AT OR AFTER ITS CLOSE: on the tick engine ``prep.t_ms[searchsorted(
  prep.t_ms, close_ms, 'left')]`` of the very rows the run reads (``bar_steps``); that is the instant the kernel
  itself moves its forming-bar index on (``kernels.py`` L840-845: bar k+1 starts at its first row) and MT5 sees bar k
  closed. On the M1-bar model at the first M1 bar opening at or after the close (``external.value_at``: a bar closed
  at ``tc <= T``). Before a filter's first value nothing is allowed.
* SESS-KZ / SESS-LN read the New York wall clock of the entry poll (the kernel's poll time ``T``; on the M1-bar model
  the open of the M1 bar of the fill): New York's offset from UTC is a whole number of hours, so the sessions change
  exactly at UTC hour boundaries, which is where their steps sit (``clock_steps``; DST from the tz database).
* The 59 single filters per design (``single_filters``), in PREREG 3's table order:

  | id | long allowed | short allowed |
  |---|---|---|
  | SIDE{n}-{tf} | close > SMA(n) | close < SMA(n) |
  | SLOPE{n}-{tf} | SMA(n) > SMA(n) 5 bars earlier | SMA(n) < SMA(n) 5 bars earlier |
  | TREND{n}-{tf} | SIDE and SLOPE | SIDE and SLOPE |
  | CROSS-{tf} | SMA(50) > SMA(200) | SMA(50) < SMA(200) |
  | LGATE200-{tf} | close > SMA(200) | always |
  | SGATE200-{tf} | always | close < SMA(200) |
  | TSI-{tf} | TSI(5, 25) > 0 (``tradeiq_ind.bjorgum_tsi``) | TSI < 0 |
  | LARSI-{tf} | Laguerre RSI (alpha 0.2) > 50 | < 50 |
  | QQE-{tf} | QQE MOD colour is not RED (``qqe_mod(c).color``) | colour is not BLUE |
  | VWRSI-{tf} | volume-weighted RSI(14) > 50 (gold: tick volume; BTC: Binance volume) | < 50 |
  | RIB-{tf} | the Trend Target Ribbon's trend is up (study 2's port) | down |
  | MSD-{tf} | the Market Structure Dashboard says LEAN BULL or BULLISH | LEAN BEAR or BEARISH |
  | HA-{tf} | the last closed Heikin Ashi candle is bullish (study 2's port) | bearish |
  | SESS-KZ | New York 02:00-05:00 or 07:00-11:00 | the same |
  | SESS-LN | New York 02:00-11:00 | the same |

  with n = 50, 100, 200 and tf = H1, H4, D1. A comparison with na (warm-up) is false: SIDE, SLOPE, TREND, CROSS, TSI,
  LARSI and VWRSI allow neither side until their lines exist, LGATE200 / SGATE200 keep their "always" side, and QQE's
  colour is GRAY (both allowed) before its Bollinger band exists (``tradeiq_ind`` docstring). RIB, MSD and HA come from
  the TradeIQ 2027 study's ports (lazy imports of ``tradeiq2_ind_ribbon.ribbon(o, h, l, c)['trend']``,
  ``tradeiq2_ind_msd.structure_dashboard(rows, chart_tf)['label']``, ``tradeiq2_ind_ha.heikin_ashi(o, h, l, c)['dir']``);
  they run once those ports have passed their reconciliation (PREREG 3), and raise ``PortMissing`` until they exist.
* Stage 2 (``stage2_pairs``): the AND of every pair among a design's three best single filters by Development score,
  only from filters whose score beats the base's (at most 3 pairs).

The regime composition (PREREG 2; tick designs)
----------------------------------------------
``fast.run(cfg, prep, regime=(times_ms, values))`` is the engine's backtest-only entry gate: from ``times_ms[i]`` on
a new basket may open only in the direction ``values[i]`` (+1 / -1; 0 none; 0 before the first time), checked at the
order stage right before the trend gate (``kernels.py`` L1214-1219). It gates new baskets only: Top 1's add and every
exit are untouched, and a blocked poll leaves the pause and agreement state alone. It cannot say "both sides", but all
four designs gate on the H1 trend (``trend_tf='H1'``: the sign of the MACD signal line of the last closed H1 bar,
L1015-1022), so the regime is composed as

    regime(T) = trend_H1(T)   if the filter allows that side at T,   else 0

on the union of the two series' change times (``compose``). ``trend_series`` rebuilds trend_H1 from the very prepare
the run reads: the signal line ``prep.flat(cfg)['SG']`` of bar k applies from the first row of bar k+1
(``prep.start_row``), which is where the kernel's forming-bar index moves on; times the trend mode (+1 for all four).
With the always-allow filter (``ALLOW``) the regime is trend_H1 itself and the run is the design fill for fill: the
polls the trend gate blocked move to the regime counter (``identity_ticks``; tests).

The Turtle (PREREG 2)
---------------------
Its filters are one-sided gates on the plan, ``plan.copy(alw_l, alw_s, m_l, m_s)`` after the votes filter
(``turtle_gate``): ``alw_*`` at the decision times, ``m_*`` per M1 bar for the stop-entry fills. Only first fills are
gated; pyramid adds are not. The Turtle exit overlays HA-M1 (a Heikin Ashi colour flip against the position) and HA-M4
(the streak in the position's direction reaches its rare age) on H4 and D1 are built with ``PathPlan`` rows only, no
edit of ``external.py`` (``turtle_exit_plan``); see that function for how the H4 rows keep the Turtle's order
semantics exactly.

Windows and the guard (PREREG 4)
--------------------------------
* Development: FINAL10's 23 round-4 quarters (``DEV_QUARTERS``), each a fresh $2,000 account, plus the continuous
  5-year account 2021-11-13 to 2026-11-13 (``FIVE_Y``). Tick designs: all 24 are cut from ONE per-second prepare of
  2021-01-01 to 2026-11-13 (its own 600-bar warm-up, as FINAL10), which is exact in per-second mode.
* Sealed: T1 (both symbols: a stub 2018-11-13 to 2019-01-01, the eight quarters of 2019-2020, the continuous account),
  T2 (gold: the quarters of 2017 from 2017-01-03 and of 2018 to 2018-10-01, a stub to 2018-11-13, the continuous
  account) and the forward window from 2026-11-13. ``guard`` refuses every scored window that is not inside
  [2021-01-01, 2026-11-13], base designs included, until ``FINALISTS.md`` and ``FINALISTS.md.sha256`` exist in the
  study folder and the hash matches (``freeze`` writes them). Older bars may be READ by indicators (warm-up); they are
  never scored before the freeze.

The score (PREREG 5)
--------------------
``yardstick``: FINAL10's selection yardstick (``final10.evidence``): per period the mean net profit per fresh quarter,
score = mean of the five period values / max(worst quarter max DD %, 1), periods up, wiped, eligibility (4 of 5 up, no
wipe, worst-quarter DD <= 50%, mean > 0). ``better``: higher score, no fewer periods up, mean profit >= 90% of the
base's (the base's own value when it is 0 or below, the exam's convention), no wipe and DD <= 50%. ``candidates``: the
three better variants with the highest scores; the confirmation reruns them and the base on raw ticks under eight
timings, the median per quarter (FINAL10 round 4); ``finalists``: up to two confirmed per design. ``exam_pass`` /
``exam_verdict`` are PREREG 6; ``multiple_testing`` PREREG 7 (Hansen's SPA on the 5-year daily P&L differences
against the base with ``tradeiq.bootstrap_pvalues``, which reproduces ``silver.spa_test``; the deflated Sharpe with
``silver.expected_max_sr`` / ``silver.dsr``).

The comparison page (PREREG 6, after the exam)
---------------------------------------------
``compare`` (``run_compare``) runs the owner's comparison accounts of a design: its base and, by default, its frozen
finalists (FINALISTS.md, ``read_finalists``) on 8y, 5y and new per second (cut from one 8-year prepare) and on 1y on
raw ticks under the eight timings; the Turtle on the M1-bar model. ``compare_gate`` refuses it before the freeze, before
study 2's exam file ``backtest_results/tradeiq_2027/EXAM.md`` exists (8y and new start 2018-11-13, inside study 2's
sealed gold Early window; compare_page keeps the same rule for its own pre-2019 P/L, both symbols), and before the
design's exam is complete (``exam_missing``). ``export`` (``export_compare``) turns every ``compare_<key>.csv`` /
``daily_compare_<key>.csv`` present into the comparison page's files for source ``bot_filters`` (compare_page's
contract v2; checked with ``compare_page.validate`` before they replace the old ones).

What is known when (no look-ahead)
----------------------------------
Every allow value of a bar filter is a function of that bar and the bars before it (Pine semantics, element i uses
bars 0..i), and it is used only from the first tick at or after the bar's close; a session filter reads the clock of
the poll itself; trend_H1 is the kernel's own closed-bar value at the kernel's own switching instant. The Heikin Ashi
exits are decided at the close of the H4 / D1 bar and executed at the next M1 open; the rare age uses only the streaks
finished before the bar.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import json
import multiprocessing as mp
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from ..data import store
from . import external as X
from . import final10 as F
from . import tradeiq_ind as I
from . import tradeiq_market as TM

STUDY_DIR = REPO_ROOT / "backtest_results" / "bot_filters"
SYMBOLS = ("XAUUSDm", "BTCUSDm")
NY = "America/New_York"
ACCOUNT = 2000.0
TFS_PREP = ("M1", "M5", "M15", "H1", "H4")      # what FINAL10 prepared for its tick runs (PREREG 2)
SEEDS = tuple(range(1, 9))                       # FINAL10's eight loop timings
RECORD_S = 3600                                  # equity samples every hour (final, DD and fills do not depend on it)
P5 = F.P5                                        # 2021, 2022, 2023, 2024-25, 2025-26
MAX_DD_PCT = F.MAX_DD_PCT                        # 50
MIN_PERIODS_UP = F.MIN_PERIODS_UP                # 4
PROFIT_FLOOR = 0.90                              # PREREG 5 (3): at least 90% of the base's mean profit per quarter
# the M1 history the filters read: from the store's first bar on or after this (gold's 2016 months if downloaded)
HISTORY_FROM = {"XAUUSDm": "2016-01-01", "BTCUSDm": "2018-01-01"}
TURTLE_HISTORY = F.HISTORY_FROM["BTCUSDm"]       # FINAL10's Turtle market starts 2018-01-01
CODE_FILES = ("backtesting/research/bot_filters.py", "backtesting/research/tradeiq_ind.py",
              "backtesting/research/tradeiq_market.py", "backtesting/research/external.py",
              "backtesting/research/final10.py", "backtesting/engine/fast.py", "backtesting/engine/kernels.py")
PORT_FILES = ("backtesting/research/tradeiq2_ind_ribbon.py", "backtesting/research/tradeiq2_ind_msd.py",
              "backtesting/research/tradeiq2_ind_ha.py")


# ───────────────────────────── the designs ─────────────────────────────

@dataclass(frozen=True)
class Design:
    key: str
    symbol: str
    engine: str              # "ticks": the tick engine; "bars": external.py's M1-bar model
    own: Optional[str]       # the design's name in round 4's designs JSON (tick designs)
    name: str


DESIGNS: Dict[str, Design] = {d.key: d for d in (
    Design("xau_v3lite", "XAUUSDm", "ticks", "V3-lite", "Gold V3-lite"),
    Design("xau_top1", "XAUUSDm", "ticks", "Top 1", "Gold Top 1"),
    Design("xau_top2", "XAUUSDm", "ticks", "Top 2", "Gold Top 2"),
    Design("btc_top2", "BTCUSDm", "ticks", "Top 2", "BTC Top 2"),
    Design("btc_turtle", "BTCUSDm", "bars", None, "BTC Turtle System 2 + bot votes"),
)}
TURTLE_LABEL = "Turtle [alt] + bot votes"         # its row in final10/runs_BTCUSDm_warm.csv


def design_cfg(key: str, start, end, record_s: int = RECORD_S, extra: Optional[dict] = None):
    """The design's configuration over [start, end) exactly as ``final10._tick_one`` builds it, sampled every
    ``record_s`` seconds; ``extra`` adds overrides (a loop timing)."""
    from .. import experiments as E
    d = DESIGNS[key]
    if d.engine != "ticks":
        raise ValueError(f"{key} does not run on the tick engine")
    cfg = E.live_config(d.symbol, start=str(start), end=str(end)).replace(**F.own_designs(d.symbol)[d.own])
    return cfg.replace(**{"record_interval_s": int(record_s), **(extra or {})})


def published_5y(key: str) -> dict:
    """The design's published five-year account (FINAL10): final equity, max DD %, trades."""
    d = DESIGNS[key]
    if d.engine == "ticks":
        t = pd.read_csv(F.OUT / f"runs_{d.symbol}_ticks.csv")
        r = t[(t.label == d.own) & (t.window == "5y")].iloc[0]
    else:
        t = pd.read_csv(F.OUT / "runs_BTCUSDm_warm.csv")
        r = t[(t.label == TURTLE_LABEL) & (t.window == "5y")].iloc[0]
    return {"final_equity": float(r.final_equity), "max_dd_pct": float(r.max_dd_pct), "trades": int(r.trades)}


# ───────────────────────────── the windows (PREREG 4) ─────────────────────────────

@dataclass(frozen=True)
class Window:
    stage: str               # dev | t1 | t2 | forward | compare
    period: str              # what it is scored in: a P5 period, "5y", "T1", "T2", ...
    name: str
    start: str
    end: str
    continuous: bool = False  # one account over the whole window (not a quarter)


DEV_START, DEV_END = "2021-01-01", "2026-11-13"
DEV_QUARTERS: Tuple[Window, ...] = tuple(Window("dev", p, n, a, z) for p, n, a, z in (
    ("2021", "H1", "2021-01-01", "2021-04-01"), ("2021", "H2", "2021-04-01", "2021-07-01"),
    ("2021", "H3", "2021-07-01", "2021-10-01"), ("2021", "H4", "2021-10-01", "2022-01-01"),
    ("2022", "H5", "2022-01-01", "2022-04-01"), ("2022", "H6", "2022-04-01", "2022-07-01"),
    ("2022", "H7", "2022-07-01", "2022-10-01"), ("2022", "H8", "2022-10-01", "2023-01-01"),
    ("2023", "F1", "2023-02-01", "2023-05-01"), ("2023", "F2", "2023-05-01", "2023-08-01"),
    ("2023", "F3", "2023-08-01", "2023-11-01"), ("2023", "F4", "2023-11-01", "2024-01-01"),
    ("2024-25", "C1", "2024-01-01", "2024-04-01"), ("2024-25", "C2", "2024-04-01", "2024-07-01"),
    ("2024-25", "C3", "2024-07-01", "2024-10-01"), ("2024-25", "C4", "2024-10-01", "2025-01-01"),
    ("2024-25", "C5", "2025-01-01", "2025-04-01"), ("2024-25", "C6", "2025-04-01", "2025-07-01"),
    ("2025-26", "HO1", "2025-08-13", "2025-11-13"), ("2025-26", "HO2", "2025-11-13", "2026-02-13"),
    ("2025-26", "OOS2", "2026-02-13", "2026-05-13"), ("2025-26", "OOS1", "2026-05-13", "2026-08-13"),
    ("2025-26", "IS", "2026-08-13", "2026-11-13")))
FIVE_Y = Window("dev", "5y", "5y", "2021-11-13", "2026-11-13", True)
DEV_WINDOWS: Tuple[Window, ...] = DEV_QUARTERS + (FIVE_Y,)


def _quarters(stage: str, edges: Sequence[str], names: Sequence[str]) -> Tuple[Window, ...]:
    return tuple(Window(stage, stage.upper(), n, a, z) for n, a, z in zip(names, edges[:-1], edges[1:]))


T1_QUARTERS = _quarters("t1", ["2018-11-13", "2019-01-01", "2019-04-01", "2019-07-01", "2019-10-01", "2020-01-01",
                               "2020-04-01", "2020-07-01", "2020-10-01", "2021-01-01"],
                        ["T1-stub", "2019Q1", "2019Q2", "2019Q3", "2019Q4", "2020Q1", "2020Q2", "2020Q3", "2020Q4"])
T1_CONT = Window("t1", "T1", "T1", "2018-11-13", "2021-01-01", True)
T2_QUARTERS = _quarters("t2", ["2017-01-03", "2017-04-01", "2017-07-01", "2017-10-01", "2018-01-01", "2018-04-01",
                               "2018-07-01", "2018-10-01", "2018-11-13"],
                        ["2017Q1", "2017Q2", "2017Q3", "2017Q4", "2018Q1", "2018Q2", "2018Q3", "T2-stub"])
T2_CONT = Window("t2", "T2", "T2", "2017-01-03", "2018-11-13", True)
FORWARD_START = "2026-11-13"
# the owner's comparison page, after the exam (PREREG 6): 8 years, 5 years, the new window per second; the last year
# on raw ticks under eight timings
COMPARE_SEC = (Window("compare", "8y", "8y", "2018-11-13", DEV_END, True),
               Window("compare", "5y", "5y", "2021-11-13", DEV_END, True),
               Window("compare", "new", "new", "2018-11-13", "2021-01-01", True))
COMPARE_1Y = Window("compare", "1y", "1y", "2025-11-13", DEV_END, True)


def _latest(*when) -> str:
    """The latest of several dates (compared as instants, not as strings)."""
    return max((str(w) for w in when), key=TM.s_of)


def forward_window(symbol: str, store_dir: Path = store.DEFAULT_STORE_DIR) -> Window:
    """2026-11-13 to the end of the minute of the store's last tick (information only, PREREG 4)."""
    span = store.data_span(symbol, store_dir)
    if span is None:
        raise FileNotFoundError(f"no {symbol} data in the store")
    end = (span[1].floor("min") + pd.Timedelta(minutes=1)).tz_convert(None)
    return Window("forward", "forward", "forward", FORWARD_START, str(end), True)


def exam_windows(symbol: str) -> Dict[str, Tuple[Tuple[Window, ...], Window]]:
    """The sealed windows of a symbol: T1 for both, T2 for gold (BTC has no unread history, PREREG 4)."""
    out = {"t1": (T1_QUARTERS, T1_CONT)}
    if symbol.startswith("XAU"):
        out["t2"] = (T2_QUARTERS, T2_CONT)
    return out


# ───────────────────────────── the guard ─────────────────────────────

class SealedWindowError(PermissionError):
    """A run reached a sealed window (T1, T2, forward or anything outside Development) before the freeze."""


DEV_START_S, DEV_END_S = TM.s_of(DEV_START), TM.s_of(DEV_END)


def finalists_frozen(study_dir: Optional[Path] = None) -> bool:
    """True when FINALISTS.md and FINALISTS.md.sha256 both exist in the study folder and the hash matches."""
    d = Path(STUDY_DIR if study_dir is None else study_dir)
    try:
        body = (d / "FINALISTS.md").read_bytes()
        want = (d / "FINALISTS.md.sha256").read_text(encoding="utf-8").split()
    except OSError:
        return False
    return bool(want) and hashlib.sha256(body).hexdigest() == want[0].strip().lower()


def guard(start, end, what: str) -> None:
    """
    THE check of every scored window (and of every data load past the Development end): a window that does not lie
    inside [2021-01-01, 2026-11-13] is sealed (T1, T2, the forward window, the comparison accounts) and raises
    ``SealedWindowError`` until the finalists are frozen. Base designs are not exempt (PREREG 4 and 6: the base is run on
    T1 / T2 only for the exam comparison, after the freeze).
    """
    a, z = TM.s_of(start), TM.s_of(end)
    if not a < z:
        raise ValueError(f"{what}: empty window {start} .. {end}")
    if (a < DEV_START_S or z > DEV_END_S) and not finalists_frozen():
        raise SealedWindowError(f"{what}: {TM.utc(a)} .. {TM.utc(z)} is outside Development ({DEV_START} .. "
                                f"{DEV_END}) and {Path(STUDY_DIR) / 'FINALISTS.md'} with a matching sha256 does not "
                                f"exist (PREREG 4)")


def guard_data_end(end, what: str) -> None:
    """Data past the Development end (the forward window) may be loaded only after the freeze."""
    if TM.s_of(end) > DEV_END_S and not finalists_frozen():
        raise SealedWindowError(f"{what}: data to {end} reaches past {DEV_END} before the freeze (PREREG 4)")


# ───────────────────────────── the filters (PREREG 3) ─────────────────────────────

FILTER_TFS = ("H1", "H4", "D1")
TM_TF = {"H1": "1H", "H4": "4H", "D1": "1D"}       # tradeiq_market's names of the same bars
MA_LENGTHS = (50, 100, 200)
SLOPE_LAG = 5
MA_FAMILIES = ("SIDE", "SLOPE", "TREND")
ONE_FAMILIES = ("CROSS", "LGATE200", "SGATE200", "TSI", "LARSI", "QQE", "VWRSI", "RIB", "MSD", "HA")
# New York wall-clock hours in which entries are allowed (02:00-05:00 or 07:00-11:00; 02:00-11:00), end exclusive
SESSIONS = {"SESS-KZ": (2, 3, 4, 7, 8, 9, 10), "SESS-LN": (2, 3, 4, 5, 6, 7, 8, 9, 10)}
PORTS = {"RIB": "tradeiq2_ind_ribbon", "MSD": "tradeiq2_ind_msd", "HA": "tradeiq2_ind_ha"}
MSD_BULL = ("LEAN BULL", "BULLISH")
MSD_BEAR = ("LEAN BEAR", "BEARISH")
MSD_ROWS = {"H1": ("1H", "4H", "1D", "1W"), "H4": ("4H", "1D", "1W"), "D1": ("1D", "1W")}


class PortMissing(ImportError):
    """A TradeIQ 2027 port (ribbon, dashboard, Heikin Ashi) is not in the repository yet."""


@dataclass(frozen=True)
class Filter:
    family: str
    tf: Optional[str] = None       # None: a clock filter (SESS-*)
    n: Optional[int] = None        # the SMA length of SIDE / SLOPE / TREND

    @property
    def fid(self) -> str:
        if self.tf is None:
            return self.family
        return f"{self.family}{self.n if self.n else ''}-{self.tf}"

    @property
    def clock(self) -> bool:
        return self.tf is None


def single_filters() -> List[Filter]:
    """The 59 single filters of PREREG 3, in the table's order."""
    out = [Filter(fam, tf, n) for fam in MA_FAMILIES for n in MA_LENGTHS for tf in FILTER_TFS]
    out += [Filter(fam, tf) for fam in ONE_FAMILIES for tf in FILTER_TFS]
    out += [Filter(s) for s in SESSIONS]
    return out


SINGLE_IDS: Tuple[str, ...] = tuple(f.fid for f in single_filters())
_BY_ID = {f.fid: f for f in single_filters()}


def filter_of(fid: str) -> Filter:
    try:
        return _BY_ID[fid]
    except KeyError:
        raise ValueError(f"unknown filter {fid!r}") from None


@dataclass(frozen=True, eq=False)
class BarSides:
    """Per closed bar of a filter's timeframe: its close time ``tc`` (UTC s) and whether a long (``al``) / a short
    (``as_``) may open from that instant on."""
    tc: np.ndarray
    al: np.ndarray
    as_: np.ndarray

    def __post_init__(self):
        if not (len(self.tc) == len(self.al) == len(self.as_)):
            raise ValueError("tc, al, as_ must have one length")
        if len(self.tc) > 1 and not bool(np.all(np.diff(self.tc) > 0)):
            raise ValueError("bar close times must increase")

    def at(self, T_s) -> Tuple[np.ndarray, np.ndarray]:
        """The allow pair of the last bar closed at or before each time (UTC s); nothing before the first close."""
        T = np.asarray(T_s, np.int64)
        i = np.searchsorted(self.tc, T, side="right") - 1
        ok = i >= 0
        ii = np.maximum(i, 0)
        return ok & self.al[ii], ok & self.as_[ii]


ALWAYS_MS = -(1 << 62)


@dataclass(frozen=True, eq=False)
class Steps:
    """A step function of time (UTC ms): from ``t[j]`` on the allow pair is (``al[j]``, ``as_[j]``); before ``t[0]``
    nothing is allowed."""
    t: np.ndarray
    al: np.ndarray
    as_: np.ndarray

    def __post_init__(self):
        if not (len(self.t) == len(self.al) == len(self.as_)) or len(self.t) == 0:
            raise ValueError("steps: t, al, as_ must have one length, at least 1")
        if len(self.t) > 1 and not bool(np.all(np.diff(self.t) > 0)):
            raise ValueError("steps: times must strictly increase")

    def at(self, T_ms) -> Tuple[np.ndarray, np.ndarray]:
        T = np.asarray(T_ms, np.int64)
        i = np.searchsorted(self.t, T, side="right") - 1
        ok = i >= 0
        ii = np.maximum(i, 0)
        return ok & self.al[ii], ok & self.as_[ii]


ALLOW = Steps(np.asarray([ALWAYS_MS], np.int64), np.asarray([True]), np.asarray([True]))


def _compress(t: np.ndarray, *vals: np.ndarray):
    """Keep the first entry and every entry whose values differ from the previous one (the same step function)."""
    keep = np.ones(len(t), bool)
    if len(t) > 1:
        same = np.ones(len(t) - 1, bool)
        for v in vals:
            same &= v[1:] == v[:-1]
        keep[1:] = ~same
    return (t[keep],) + tuple(v[keep] for v in vals)


def stamp_rows(t_ms: np.ndarray, tc_s: np.ndarray) -> np.ndarray:
    """Index of the first row at or after each close (``len(t_ms)``: the bar closes after the last row)."""
    return np.searchsorted(np.asarray(t_ms, np.int64), np.asarray(tc_s, np.int64) * 1000, side="left")


def bar_steps(t_ms: np.ndarray, sides: BarSides) -> Steps:
    """
    The filter on the rows of a prepare: each bar's value from the first row at or after its close. Bars that close
    before the first row all land on it and the last of them holds; bars that close after the last row never take
    effect. A filter with no bar inside the rows allows nothing.
    """
    t_ms = np.asarray(t_ms, np.int64)
    i = stamp_rows(t_ms, sides.tc)
    ok = i < len(t_ms)
    if not ok.any():
        return Steps(np.asarray([ALWAYS_MS], np.int64), np.asarray([False]), np.asarray([False]))
    t, al, ash = t_ms[i[ok]], np.asarray(sides.al)[ok].astype(bool), np.asarray(sides.as_)[ok].astype(bool)
    last = np.ones(len(t), bool)
    last[:-1] = t[1:] != t[:-1]
    t, al, ash = _compress(t[last], al[last], ash[last])
    return Steps(t, al, ash)


def ny_hour(T_s) -> np.ndarray:
    """The New York wall-clock hour (0-23) at each UTC time (s)."""
    loc = X.local_seconds(np.asarray(T_s, np.int64), NY)
    return ((loc % 86400) // 3600).astype(np.int64)


def clock_steps(fid: str, a_ms: int, z_ms: int) -> Steps:
    """
    SESS-KZ / SESS-LN over [a_ms, z_ms]: both sides allowed while the New York clock of the poll is inside the
    session. New York's offset from UTC is a whole number of hours (DST included), so the steps sit exactly on UTC
    hour boundaries: the hour starting at h is in the session iff its New York hour is.
    """
    hours = SESSIONS[fid]
    h0 = (int(a_ms) // 3_600_000 - 1) * 3600
    h1 = (int(z_ms) // 3_600_000 + 2) * 3600
    hs = np.arange(h0, h1, 3600, dtype=np.int64)
    ok = np.isin(ny_hour(hs), hours)
    t, al, ash = _compress(hs * 1000, ok, ok.copy())
    return Steps(t, al, ash)


def and_steps(a: Steps, b: Steps) -> Steps:
    """Both filters at once (a stage-2 pair): allowed where both allow, on the union of their change times."""
    u = np.union1d(a.t, b.t)
    l1, s1 = a.at(u)
    l2, s2 = b.at(u)
    t, al, ash = _compress(u, l1 & l2, s1 & s2)
    return Steps(t, al, ash)


def _port(family: str):
    try:
        return importlib.import_module(f"backtesting.research.{PORTS[family]}")
    except ImportError as e:
        raise PortMissing(f"{family}: backtesting/research/{PORTS[family]}.py (the TradeIQ 2027 port) is not "
                          f"importable yet: {e}") from e


def _msd_sides(label) -> Tuple[np.ndarray, np.ndarray]:
    """LEAN BULL / BULLISH allow longs, LEAN BEAR / BEARISH shorts. Accepts the labels as strings or as the signed
    grades +2 / +1 / 0 / -1 / -2."""
    lab = np.asarray(label)
    if lab.dtype.kind in "iuf":
        with np.errstate(invalid="ignore"):
            return lab > 0, lab < 0
    s = np.char.upper(np.char.strip(lab.astype(str)))
    return np.isin(s, MSD_BULL), np.isin(s, MSD_BEAR)


@dataclass(frozen=True, eq=False)
class WeekBars:
    """ISO (Monday-start) weeks of the merged D1 bars, for the dashboard's W row: a week opens with its first day bar
    and closes with its last one (``tc`` = that day bar's close)."""
    t: np.ndarray
    tc: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray

    def __len__(self) -> int:
        return int(len(self.t))


def week_bars(d1, end_s: Optional[int] = None) -> WeekBars:
    """Group the D1 bars by the Monday-based week of (close - 1 s): the week a day bar belongs to is the week of its
    last second, so a Sunday stub merged into Monday counts with that Monday's week. ``end_s``: the end of the data;
    a last week that could still receive day bars (its ISO end, the next Monday 00:00 UTC, is after ``end_s``) closes
    at that ISO end, so that nothing reads it before it can be complete (the port's ``weekly_bars`` rule). Only a
    fallback: the dashboard's rows come from the port's own ``rows_for`` when it has one."""
    last = np.asarray(d1.tc, np.int64) - 1
    # 1970-01-01 was a Thursday: shift by 3 days so that weeks start on Monday 00:00 UTC
    wk = (last + 3 * 86400) // (7 * 86400)
    first = np.flatnonzero(np.diff(wk, prepend=wk[0] - 1) != 0)
    lst = np.append(first[1:] - 1, len(wk) - 1)
    tc = np.asarray(d1.tc, np.int64)[lst].copy()
    if end_s is not None and len(tc):
        iso_end = int(wk[-1]) * 7 * 86400 - 3 * 86400 + 7 * 86400
        if int(end_s) < iso_end:
            tc[-1] = iso_end
    return WeekBars(np.asarray(d1.t)[first], tc, np.asarray(d1.o)[first],
                    np.maximum.reduceat(np.asarray(d1.h), first), np.minimum.reduceat(np.asarray(d1.l), first),
                    np.asarray(d1.c)[lst])


class FilterBook:
    """
    One symbol's M1 bid bars from ``HISTORY_FROM`` (the store's first bar on or after it) to ``end`` as a
    ``tradeiq_market.TMarket`` (study 1's bars, tick volume, Binance volume), and every filter's closed-bar sides,
    computed on demand and cached. ``end`` past the Development end needs the freeze.
    """

    def __init__(self, symbol: str, end: str = DEV_END, store_dir: Path = store.DEFAULT_STORE_DIR,
                 history_from: Optional[str] = None):
        guard_data_end(end, f"{symbol} filter bars")
        m = X.load_market(symbol, Path(store_dir), earliest=history_from or HISTORY_FROM[symbol], end=str(end))
        self.symbol = symbol
        self.end = str(end)
        self.mk = TM.TMarket(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp,
                                      "n": m.n}, TM.s_of(end))
        self.history_from = str(TM.utc(self.mk.t[0]))
        self._lines: Dict[Tuple[str, str], np.ndarray] = {}
        self._sides: Dict[str, BarSides] = {}

    def bars(self, tf: str):
        return self.mk.tbars(TM_TF[tf])

    def line(self, tf: str, name: str) -> np.ndarray:
        """One indicator line per bar of ``tf`` (Pine semantics, element i from bars 0..i)."""
        key = (tf, name)
        if key not in self._lines:
            b = self.bars(tf)
            c = b.c
            if name.startswith("SMA"):
                v = I.sma(c, int(name[3:]))
            elif name == "TSI":
                v = I.bjorgum_tsi(c).tsi                        # TSI(5, 25), study 1's port
            elif name == "LARSI":
                v = I.laguerre_rsi(c, 0.2)
            elif name == "QQE":
                v = I.qqe_mod(c).color.astype(np.int64)         # BLUE 1 / RED -1 / GRAY 0
            elif name == "VWRSI":
                vol = TM.binance_volume(self.mk, TM_TF[tf])[0] if self.symbol.startswith("BTC") else b.vol
                v = I.vwrsi(c, vol).rsi
            elif name == "RIB":
                v = np.asarray(_port("RIB").ribbon(b.o, b.h, b.l, b.c)["trend"], np.float64)
            elif name == "HA":
                v = np.asarray(_port("HA").heikin_ashi(b.o, b.h, b.l, b.c)["dir"], np.float64)
            elif name == "HA_RARE":
                # the port's own causal rare-age series when it has one (the reconciled port wins), else ``rare_age``
                h = _port("HA").heikin_ashi(b.o, b.h, b.l, b.c)
                key = next((k for k in HA_RARE_KEYS if k in h), None)
                v = (np.asarray(h[key], bool) if key else rare_age(np.asarray(h["dir"], np.float64))).astype(np.float64)
            elif name == "MSD":
                v = self._msd_label(tf)
            else:
                raise ValueError(f"unknown line {name}")
            if len(v) != len(b):
                raise AssertionError(f"{name} on {tf}: {len(v)} values for {len(b)} bars")
            self._lines[key] = v
        return self._lines[key]

    def _msd_label(self, tf: str) -> np.ndarray:
        """The dashboard's bias label per bar of the chart ``tf``, its rows at or above the chart (1H: 1H, 4H, D, W;
        4H: 4H, D, W; 1D: D, W) on closed bars ("model A", study 2's PREREG 6.2)."""
        M = _port("MSD")
        if hasattr(M, "rows_for"):
            rows = M.rows_for(self.mk)                 # the port's 1H / 4H / 1D and weekly bars (end-aware)
        else:
            rows = {r: (week_bars(self.bars("D1"), self.mk.end_s) if r == "1W" else self.mk.tbars(r))
                    for r in MSD_ROWS[tf]}
        return np.asarray(M.structure_dashboard(rows, TM_TF[tf])["label"])

    def sides(self, fid: str) -> BarSides:
        """The closed-bar allow pair of a bar filter (PREREG 3's table), complete bars only."""
        if fid in self._sides:
            return self._sides[fid]
        f = filter_of(fid)
        if f.clock:
            raise ValueError(f"{fid} reads the clock, not bars: use clock_steps / masks")
        b = self.bars(f.tf)
        c = b.c
        L = lambda name: self.line(f.tf, name)      # noqa: E731
        with np.errstate(invalid="ignore"):
            if f.family in MA_FAMILIES:
                ma = L(f"SMA{f.n}")
                side_l, side_s = c > ma, c < ma
                past = I.hist(ma, SLOPE_LAG)
                slope_l, slope_s = ma > past, ma < past
                al, ash = {"SIDE": (side_l, side_s), "SLOPE": (slope_l, slope_s),
                           "TREND": (side_l & slope_l, side_s & slope_s)}[f.family]
            elif f.family == "CROSS":
                al, ash = L("SMA50") > L("SMA200"), L("SMA50") < L("SMA200")
            elif f.family == "LGATE200":
                al, ash = c > L("SMA200"), np.ones(len(c), bool)
            elif f.family == "SGATE200":
                al, ash = np.ones(len(c), bool), c < L("SMA200")
            elif f.family == "TSI":
                al, ash = L("TSI") > 0.0, L("TSI") < 0.0
            elif f.family == "LARSI":
                al, ash = L("LARSI") > 50.0, L("LARSI") < 50.0
            elif f.family == "QQE":
                col = L("QQE")
                al, ash = col != I.RED, col != I.BLUE
            elif f.family == "VWRSI":
                al, ash = L("VWRSI") > 50.0, L("VWRSI") < 50.0
            elif f.family in ("RIB", "HA"):
                v = L(f.family)
                al, ash = v > 0, v < 0
            elif f.family == "MSD":
                al, ash = _msd_sides(L("MSD"))
            else:
                raise ValueError(fid)
        keep = np.asarray(b.complete, bool)
        s = BarSides(np.asarray(b.tc, np.int64)[keep], np.asarray(al, bool)[keep], np.asarray(ash, bool)[keep])
        self._sides[fid] = s
        return s

    def steps(self, fid: str, t_ms: np.ndarray) -> Steps:
        """The filter (or an ``&``-pair) on a prepare's rows (tick engine)."""
        parts = fid.split("&")
        if len(parts) > 1:
            out = self.steps(parts[0], t_ms)
            for p in parts[1:]:
                out = and_steps(out, self.steps(p, t_ms))
            return out
        f = filter_of(fid)
        if f.clock:
            return clock_steps(fid, int(t_ms[0]), int(t_ms[-1]))
        return bar_steps(t_ms, self.sides(fid))

    def masks(self, fid: str, T_s) -> Tuple[np.ndarray, np.ndarray]:
        """The filter (or an ``&``-pair) at times ``T_s`` (UTC s) on the M1-bar model: a bar closed at ``tc <= T``;
        a session filter on the New York hour of ``T``."""
        al = np.ones(len(np.asarray(T_s)), bool)
        ash = al.copy()
        for p in fid.split("&"):
            f = filter_of(p)
            if f.clock:
                ok = np.isin(ny_hour(T_s), SESSIONS[p])
                l1, s1 = ok, ok
            else:
                l1, s1 = self.sides(p).at(T_s)
            al &= l1
            ash &= s1
        return al, ash


# ───────────────────────────── the regime composition (tick designs) ─────────────────────────────

def trend_series(prep, cfg) -> Tuple[np.ndarray, np.ndarray]:
    """
    The kernel's own trend gate as a step function of time: the sign of the MACD signal line of the trend timeframe's
    last CLOSED bar (``kernels.py`` L1015-1022), times the trend mode. Bar k's value holds from the first row of bar
    k+1, which is where the kernel's forming-bar index moves on (L840-845; warm-up bars have no row, so the last warm-up
    bar's value starts at the first row). Before the first entry the kernel sees no live quote or no closed bar: 0.
    """
    tf = cfg.trend_tf
    if not tf:
        raise ValueError("the design has no trend timeframe: the regime cannot express 'both sides'")
    flat = prep.flat(cfg)
    f = prep.tfs.index(tf)
    o, nb = int(flat["off"][f]), int(flat["nb"][f])
    sg = np.asarray(flat["SG"][o:o + nb], np.float64)
    rows = np.asarray(prep.start_row[tf], np.int64)
    if len(rows) != nb:
        raise AssertionError("the prepare's bars and its flat arrays disagree")
    k = np.arange(nb - 1)
    r = rows[k + 1]
    ok = r >= 0
    with np.errstate(invalid="ignore"):
        v = np.where(sg[k[ok]] > 0.0, 1, np.where(sg[k[ok]] < 0.0, -1, 0)).astype(np.int64)
    v *= 1 if cfg.trend_mode >= 0 else -1
    return np.asarray(prep.t_ms, np.int64)[r[ok]], v


def compose(trend: Tuple[np.ndarray, np.ndarray], steps: Steps) -> Tuple[np.ndarray, np.ndarray]:
    """
    regime(T) = trend(T) if the filter allows that side at T, else 0, on the union of the change times (PREREG 2).
    Before the first trend time the trend is 0 and before the filter's first step nothing is allowed, so the regime is
    0 there (the kernel's own value before its first regime time). Entries equal to the previous one are dropped.
    """
    tt, tv = np.asarray(trend[0], np.int64), np.asarray(trend[1], np.int64)
    if len(tt) > 1 and not bool(np.all(np.diff(tt) > 0)):
        raise ValueError("trend times must strictly increase")
    u = np.union1d(tt, steps.t)
    i = np.searchsorted(tt, u, side="right") - 1
    trend_u = np.where(i >= 0, tv[np.maximum(i, 0)], 0)
    al, ash = steps.at(u)
    rv = np.where((trend_u == 1) & al, 1, np.where((trend_u == -1) & ash, -1, 0)).astype(np.int64)
    t, v = _compress(u, rv)
    return np.ascontiguousarray(t, np.int64), np.ascontiguousarray(v, np.int64)


def regime_at(regime: Tuple[np.ndarray, np.ndarray], T_ms) -> np.ndarray:
    """The kernel's reading of a regime series at poll times (``kernels.py`` L1023-1026): 0 before the first time."""
    t, v = regime
    i = np.searchsorted(t, np.asarray(T_ms, np.int64), side="right") - 1
    return np.where(i >= 0, np.asarray(v)[np.maximum(i, 0)], 0)


# ───────────────────────────── the Turtle (M1-bar model) ─────────────────────────────

def turtle_base(m, sig) -> X.PathPlan:
    """FINAL10's row "Turtle [alt] + bot votes": System 2 with the bot's M15 votes (``final10._bar_plan``)."""
    return X.filtered(X.turtle(m, 2).plan, m, sig.votes_at)


def turtle_gate(plan: X.PathPlan, m, al_dt, as_dt, al_m1, as_m1) -> X.PathPlan:
    """One-sided gates on top of the votes (PREREG 2): entries at the decisions (``alw_*``) and stop-entry fills per
    M1 bar (``m_*``) only where the filter allows that side; pyramid adds and exits are untouched."""
    if plan.m_l is None or plan.m_s is None:
        raise ValueError("the Turtle's plan has stop-entry orders: m_l / m_s are expected")
    return plan.copy(alw_l=plan.alw_l & np.asarray(al_dt, bool), alw_s=plan.alw_s & np.asarray(as_dt, bool),
                     m_l=np.ascontiguousarray(plan.m_l & np.asarray(al_m1, bool)),
                     m_s=np.ascontiguousarray(plan.m_s & np.asarray(as_m1, bool)))


def turtle_filtered(plan: X.PathPlan, m, book: FilterBook, fid: str) -> X.PathPlan:
    al_dt, as_dt = book.masks(fid, plan.dt)
    al_m, as_m = book.masks(fid, m.t)
    return turtle_gate(plan, m, al_dt, as_dt, al_m, as_m)


EXITS = ("HA-M1-H4", "HA-M1-D1", "HA-M4-H4", "HA-M4-D1")
RARE_PCT = 90.0
RARE_MIN_STREAKS = 50          # study 2's PREREG 6.8: a rare-age rule needs 50 finished streaks of that colour
HA_RARE_KEYS = ("rare_now", "rare")   # what the HA port may call its causal rare-age series


def ha_flips(direction) -> Tuple[np.ndarray, np.ndarray]:
    """HA-M1: (exit a long, exit a short) at the close of the bar where the Heikin Ashi colour flips against the
    position: bullish to bearish, bearish to bullish."""
    d = np.asarray(direction, np.float64)
    prev = np.concatenate([[np.nan], d[:-1]])
    return (d < 0) & (prev > 0), (d > 0) & (prev < 0)


def rare_age(direction, pct: float = RARE_PCT, min_n: int = RARE_MIN_STREAKS) -> np.ndarray:
    """
    The script's ``rareNow`` (LunqFX l.209-212), computed causally on every bar (study 2's PREREG 6.8): the streak's
    age is the number of bars of the current colour; at a flip the finished streak's length joins its colour's list;
    ``pctBelow(a)`` is the share (%) of FINISHED streaks of the current colour shorter than ``a``. rareNow is true when
    pctBelow(age) reaches ``pct`` while pctBelow(age - 1) was below it (at most once per streak), and only once
    ``min_n`` streaks of that colour have finished.
    """
    import bisect
    d = np.asarray(direction, np.float64)
    out = np.zeros(len(d), bool)
    lists = {1: [], -1: []}
    age, sdir = 0, 0
    for i, x in enumerate(d):
        if not np.isfinite(x) or x == 0:
            age, sdir = 0, 0
            continue
        c = 1 if x > 0 else -1
        if sdir != 0 and c != sdir:
            bisect.insort(lists[sdir], age)
            age = 1
        else:
            age += 1
        sdir = c
        L = lists[c]
        if len(L) >= min_n:
            now = 100.0 * bisect.bisect_left(L, age) / len(L)
            before = 100.0 * bisect.bisect_left(L, age - 1) / len(L)
            out[i] = now >= pct and before < pct
    return out


def exit_flags(book: FilterBook, exit_id: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(close times, exit a long, exit a short) of one Heikin Ashi overlay on its timeframe's complete bars."""
    _, method, tf = exit_id.split("-")
    if exit_id not in EXITS:
        raise ValueError(exit_id)
    b = book.bars(tf)
    d = book.line(tf, "HA")
    if method == "M1":
        xl, xs = ha_flips(d)
    else:
        r = book.line(tf, "HA_RARE") > 0
        xl, xs = r & (d > 0), r & (d < 0)
    keep = np.asarray(b.complete, bool)
    return np.asarray(b.tc, np.int64)[keep], xl[keep], xs[keep]


def turtle_exit_plan(base: X.PathPlan, m, tc, xl, xs, a_ix: int, z_ix: int, max_iter: int = 100_000) -> X.PathPlan:
    """
    The Turtle with an exit overlay, built from ``PathPlan`` rows only (no edit of ``external.py``), for the window
    [a_ix, z_ix) of the M1 bars.

    * A flag at a close equal to a plan decision (D1, and the H4 closes at 00:00 UTC) is OR-ed into that row's
      ``xl`` / ``xs``: the kernel exits at the next M1 open and the same row then arms the new day's stop-entry orders
      (a re-entry needs a new 55-day extreme: "an event rule waits for its next event").
    * Any other flagged close (H4) becomes a new decision row that copies every field of the last plan row before it
      (``_path_kernel`` re-arms the stop-entry orders at every decision, L645-647, and reads the fields of the row that
      armed them at a fill). Two things keep the Turtle's own semantics exactly: an order filled since the day's
      decision stays cancelled until the next one (one fill cancels both, L757-758), and after an H4 exit the base
      stays flat until the next decision (PREREG: "after a Heikin Ashi exit the base stays flat until its own state
      changes"). So a new row carries no orders (NaN levels) when a fill happened earlier in its day, when it or an
      earlier new row of its day closed the position, or when its day's decision lies before the window (the kernel
      skips rows before the start, L564). Which rows those are depends on the path, so the plan is rebuilt until it is a
      fixed point; every pass fixes the earliest event, whose prefix of the path no longer changes.
    A new row whose flag finds no position against it re-arms the same levels: a no-op. With no flag at all the plan is
    the base itself.
    """
    tc = np.asarray(tc, np.int64)
    xl = np.asarray(xl, bool)
    xs = np.asarray(xs, bool)
    flag = xl | xs
    tc, xl, xs = tc[flag], xl[flag], xs[flag]
    K = len(base)
    on_row = np.searchsorted(base.dt, tc, side="left")
    hit = (on_row < K) & (base.dt[np.minimum(on_row, K - 1)] == tc)
    bxl, bxs = base.xl.copy(), base.xs.copy()
    np.logical_or.at(bxl, on_row[hit], xl[hit])
    np.logical_or.at(bxs, on_row[hit], xs[hit])
    nt, nxl, nxs = tc[~hit], xl[~hit], xs[~hit]
    nt_dx = np.searchsorted(m.t, nt, side="left").astype(np.int64)
    keep = nt_dx < len(m)
    nt, nxl, nxs, nt_dx = nt[keep], nxl[keep], nxs[keep], nt_dx[keep]
    src = np.searchsorted(base.dt, nt, side="right") - 1          # the plan row each new row copies
    n_new = len(nt)
    if n_new == 0:
        return base.copy(xl=bxl, xs=bxs)
    # one plan: the base rows and the new rows, by decision time (new times never equal a base time)
    dt = np.concatenate([base.dt, nt])
    order = np.argsort(dt, kind="stable")
    is_new = np.concatenate([np.zeros(K, bool), np.ones(n_new, bool)])[order]
    srcs = np.concatenate([np.arange(K), np.maximum(src, 0)])[order]
    no_src = np.concatenate([np.zeros(K, bool), src < 0])[order]
    # plan positions of the new rows; ``nt`` is in time order and the sort is stable, so position j is new row j
    pos_new = np.flatnonzero(is_new)

    def col(a, fill_new=None):
        a = np.asarray(a)
        out = a[srcs].copy()
        if fill_new is not None:
            out[is_new] = fill_new
        return out

    f_base = {k: col(v) for k, v in base.f.items()}
    for k in f_base:
        f_base[k][no_src] = np.nan
    plan0 = base.copy(dt=dt[order], dx=np.concatenate([base.dx, nt_dx])[order],
                      want=col(base.want, 0), xl=np.concatenate([bxl, nxl])[order],
                      xs=np.concatenate([bxs, nxs])[order],
                      f=f_base, pmax=col(base.pmax), alw_l=col(base.alw_l, False), alw_s=col(base.alw_s, False))
    # the day (base row) of every new row, and whether that day's decision is inside the window
    day = np.where(no_src[pos_new], -1, srcs[pos_new])
    outside = (day < 0) | (base.dx[np.maximum(day, 0)] < a_ix)
    cancel = outside.copy()                                       # new rows that carry no orders
    base_dx = base.dx
    for _ in range(max_iter):
        fb = dict(plan0.f)
        bs, ss = fb["bstop"].copy(), fb["sstop"].copy()
        bs[pos_new[cancel]] = np.nan
        ss[pos_new[cancel]] = np.nan
        fb["bstop"], fb["sstop"] = bs, ss
        plan = plan0.copy(f=fb)
        p = X.run_path(m, plan, a_ix, z_ix)
        # the events of this path in the kernel's order: by M1 bar, and inside a bar the decisions' exits (step 2)
        # before the stop-entry fills (step 4)
        events = []
        for e in p.eix:
            k = int(np.searchsorted(base_dx, e, side="right") - 1)      # the day the fill belongs to
            if k >= 0:
                events.append((int(e), 1, k, "fill"))
        for d_, x, why in zip(p.dir, p.xix, p.why):
            if why != X.WHY_SIGNAL:
                continue
            at = np.flatnonzero(plan.dx == x)
            for q in at:                                           # the first row at that bar that exits this side
                if (d_ > 0 and plan.xl[q]) or (d_ < 0 and plan.xs[q]):
                    if is_new[q]:
                        events.append((int(x), 0, int(q), "exit"))
                    break
        events.sort()
        changed = False
        for when, _, ref, kind in events:
            if kind == "fill":
                aff = (day == ref) & (plan.dx[pos_new] > when)
            else:
                j = int(np.searchsorted(pos_new, ref))
                aff = (day == day[j]) & (np.arange(n_new) >= j)
            if (aff & ~cancel).any():
                cancel |= aff
                changed = True
                break
        if not changed:
            return plan
    raise RuntimeError("the exit overlay did not reach a fixed point")


# ───────────────────────────── the variants ─────────────────────────────

BASE, IDENTITY = "BASE", "ALLOW"


@dataclass(frozen=True)
class Variant:
    vid: str

    @property
    def kind(self) -> str:
        if self.vid == BASE:
            return "base"
        if self.vid == IDENTITY:
            return "identity"
        if self.vid.startswith("EXIT:"):
            return "exit"
        return "pair" if "&" in self.vid else "single"

    @property
    def fids(self) -> Tuple[str, ...]:
        return tuple(self.vid.split("&")) if self.kind in ("single", "pair") else ()

    @property
    def exit(self) -> Optional[str]:
        return self.vid[5:] if self.kind == "exit" else None


def pair_vid(a: str, b: str) -> str:
    """One name per pair: the two filters in the table's order."""
    ia, ib = SINGLE_IDS.index(a), SINGLE_IDS.index(b)
    return f"{a}&{b}" if ia < ib else f"{b}&{a}"


def uses_port(vid: str) -> bool:
    """A variant that reads one of study 2's ports (RIB, MSD, HA rows and the Turtle's Heikin Ashi exits)."""
    v = Variant(vid)
    return v.kind == "exit" or any(filter_of(f).family in PORTS for f in v.fids)


def stage1_vids(key: str, ports: bool = True) -> List[str]:
    """The base, the identity filter, the 59 singles, and for the Turtle its four exit overlays. ``ports=False``
    leaves out the rows that read study 2's ports (RIB, MSD, HA and the exits): PREREG 3 runs them only once those
    ports have passed their reconciliation."""
    out = [BASE, IDENTITY] + list(SINGLE_IDS)
    if DESIGNS[key].engine == "bars":
        out += [f"EXIT:{e}" for e in EXITS]
    return out if ports else [v for v in out if not uses_port(v)]


def check_vids(vids: Iterable[str]) -> None:
    for v in vids:
        var = Variant(v)
        for f in var.fids:
            filter_of(f)
        if var.kind == "exit" and var.exit not in EXITS:
            raise ValueError(f"unknown exit {var.exit}")


# ───────────────────────────── running ─────────────────────────────

_G: dict = {}                    # what forked workers inherit: the prepare, the trend series, the filter steps

COLUMNS = ["design", "symbol", "vid", "kind", "stage", "window", "period", "start", "end", "mode", "seed",
           "final_equity", "net", "return_pct", "max_dd_pct", "trades", "wiped", "wiped_at", "blocked_regime",
           "blocked_trend", "skipped_trades", "run_s", "history_from"]


def _append(path: Path, rows: List[dict], columns: Sequence[str] = COLUMNS) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for c in columns:
        if c not in df:
            df[c] = np.nan
    df[list(columns)].to_csv(path, mode="a", header=not path.exists(), index=False)


def read_rows(path: Path) -> pd.DataFrame:
    """A results file, the last row of each (vid, stage, window, mode, seed) kept (a resumed run may repeat one)."""
    if not Path(path).exists():
        return pd.DataFrame(columns=COLUMNS)
    d = pd.read_csv(path, dtype={"period": str, "window": str})
    d["seed"] = d["seed"].fillna(0).astype(int)
    return d.drop_duplicates(["vid", "stage", "window", "mode", "seed"], keep="last").reset_index(drop=True)


def read_daily(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=["design", "vid", "window", "date", "equity"])
    d = pd.read_csv(path, parse_dates=["date"])
    return d.drop_duplicates(["vid", "window", "date"], keep="last").reset_index(drop=True)


def _done(rows: pd.DataFrame, windows: Sequence[Window], mode: str, seeds: Sequence[int] = (0,)) -> set:
    """Variants with a row for every window and seed of a stage."""
    if rows.empty:
        return set()
    want = {(w.name, int(s)) for w in windows for s in seeds}
    r = rows[rows["mode"] == mode]
    have: Dict[str, set] = {}
    for vid, win, sd in zip(r["vid"], r["window"].astype(str), r["seed"].astype(int)):
        have.setdefault(vid, set()).add((win, int(sd)))
    return {v for v, s in have.items() if want <= s}


def _tick_row(key: str, vid: str, w: Window, res, mode: str, seed: int, run_s: float) -> dict:
    sc, ct = res.scalars, res.counters
    final = float(sc["final_equity"])
    wiped = bool(sc["stopped_out"])
    return dict(design=key, symbol=DESIGNS[key].symbol, vid=vid, kind=Variant(vid).kind, stage=w.stage,
                window=w.name, period=w.period, start=w.start, end=w.end, mode=mode, seed=int(seed),
                final_equity=round(final, 6), net=round(final - ACCOUNT, 6),
                return_pct=round((final - ACCOUNT) / ACCOUNT * 100.0, 6), max_dd_pct=round(float(sc["max_drawdown_pct"]), 6),
                trades=int(len(res.baskets)), wiped=wiped,
                wiped_at=str(pd.Timestamp(int(sc["last_poll_ms"]), unit="ms")) if wiped else "",
                blocked_regime=int(ct.get("polls_entry_blocked_regime", 0)),
                blocked_trend=int(ct.get("polls_entry_blocked_trend", 0)), skipped_trades=0, run_s=round(run_s, 2),
                history_from=_G.get("history_from", ""))


def _regime_of(key: str, vid: str):
    """The regime series of a variant on the prepare in ``_G`` (None for the base: the design as published)."""
    v = Variant(vid)
    if v.kind == "base":
        return None
    if v.kind == "identity":
        return compose(_G["trend"][key], ALLOW)
    if v.kind not in ("single", "pair"):
        raise ValueError(f"{vid}: not a tick-engine variant")
    st = _G["steps"][v.fids[0]]
    for f in v.fids[1:]:
        st = and_steps(st, _G["steps"][f])
    return compose(_G["trend"][key], st)


def _sec_task(task: tuple) -> dict:
    """One variant on every window of a stage, cut from the per-second prepare in ``_G``."""
    from ..engine import fast
    key, vid, windows = task
    prep = _G["prep"]
    t0 = time.time()
    reg = _regime_of(key, vid)
    rows, daily = [], []
    for w in windows:
        cfg = design_cfg(key, w.start, w.end)
        t1 = time.time()
        res = fast.run(cfg, prep, light=not w.continuous, regime=reg)
        rows.append(_tick_row(key, vid, w, res, "sec", 0, time.time() - t1))
        if w.continuous:
            d = F._tick_daily(res)
            daily += [dict(design=key, vid=vid, window=w.name, date=str(t.date()), equity=round(float(e), 6))
                      for t, e in d.items()]
        del res
    return dict(vid=vid, rows=rows, daily=daily, seconds=time.time() - t0)


def _tick_task(task: tuple) -> dict:
    """One variant under one loop timing on the raw-tick prepare of one window in ``_G``."""
    from ..analysis.robustness import live_timing
    from ..engine import fast
    key, vid, w, seed = task
    t0 = time.time()
    reg = _regime_of(key, vid)
    res = fast.run(design_cfg(key, w.start, w.end, extra=live_timing(int(seed))), _G["prep"], light=True, regime=reg)
    return dict(vid=vid, rows=[_tick_row(key, vid, w, res, "ticks", seed, time.time() - t0)], daily=[],
                seconds=time.time() - t0)


def _map(fn: Callable, tasks: List[tuple], workers: int):
    """Tasks in a fork pool (the workers share the prepared rows copy-on-write, ``sizing._pool``'s pattern), or in this
    process when ``workers <= 1``."""
    if workers <= 1 or len(tasks) <= 1:
        for t in tasks:
            yield fn(t)
        return
    ctx = mp.get_context("fork")
    with ctx.Pool(min(workers, len(tasks))) as pool:
        for out in pool.imap_unordered(fn, tasks, chunksize=1):
            yield out


def _filter_steps(symbol: str, fids: Iterable[str], t_ms: np.ndarray, store_dir: Path, end: str = DEV_END,
                  book: Optional[FilterBook] = None) -> Dict[str, Steps]:
    fids = sorted(set(fids))
    if not fids:
        return {}
    bk = book or FilterBook(symbol, end, store_dir)
    _G["history_from"] = bk.history_from
    return {f: bk.steps(f, t_ms) for f in fids}


def _warm_kernel(key: str, prep) -> None:
    """The compiled kernel and the indicator arrays, made before the workers fork."""
    from ..engine import fast
    a = pd.Timestamp(prep.start_ms, unit="ms")
    fast.run(design_cfg(key, str(a), str(a + pd.Timedelta(days=2))), prep, light=True)


def run_sec_stage(key: str, vids: Sequence[str], windows: Sequence[Window], sink: Path, daily_sink: Path,
                  workers: int = 4, prep=None, store_dir: Path = store.DEFAULT_STORE_DIR, log=print) -> pd.DataFrame:
    """
    Tick designs, per second, one loop timing: every variant on every window, all cut from ONE per-second prepare of
    the windows' span (its own 600-bar warm-up, FINAL10's mode; exact in per-second mode). Resume-safe: variants with
    a row for every window in ``sink`` are skipped. ``prep``: a prepare to reuse (it must cover the windows).
    """
    from ..engine import fast
    d = DESIGNS[key]
    check_vids(vids)
    for w in windows:
        guard(w.start, w.end, f"{key} {w.name}")
    todo = [v for v in vids if v not in _done(read_rows(sink), windows, "sec")]
    log(f"{key}: {len(todo)} of {len(vids)} variants to run on {len(windows)} windows per second -> {sink}")
    if not todo:
        return read_rows(sink)
    a = min(w.start for w in windows)
    z = max(w.end for w in windows)
    t0 = time.time()
    if prep is None:
        prep = fast.prepare(d.symbol, a, z, list(TFS_PREP), mode="sec", store_dir=store_dir)
    elif not (prep.mode == "sec" and prep.start_ms <= store.to_ms(a) and prep.end_ms >= store.to_ms(z)):
        raise ValueError("the prepare given does not cover the windows per second")
    cfg = design_cfg(key, a, z)
    _G.update(prep=prep, trend={key: trend_series(prep, cfg)}, history_from="")
    _G["steps"] = _filter_steps(d.symbol, [f for v in todo for f in Variant(v).fids], prep.t_ms, store_dir,
                                end=_latest(DEV_END, z))
    _warm_kernel(key, prep)
    log(f"{key}: {prep.n_rows:,} per-second rows, trend and {len(_G['steps'])} filters ready "
        f"({time.time() - t0:.0f}s)")
    tasks = [(key, v, tuple(windows)) for v in todo]
    t0 = time.time()
    for i, out in enumerate(_map(_sec_task, tasks, workers)):
        _append(daily_sink, out["daily"], ["design", "vid", "window", "date", "equity"])
        _append(sink, out["rows"])
        r5 = [r for r in out["rows"] if r["window"] == "5y"]
        log(f"  [{i + 1}/{len(tasks)} {time.time() - t0:6.0f}s] {key} {out['vid']}: {out['seconds']:.0f}s"
            + (f", 5y final {r5[0]['final_equity']:.2f}" if r5 and Variant(out['vid']).kind in ('base', 'identity')
               else ""))
    return read_rows(sink)


def run_tick_stage(key: str, vids: Sequence[str], windows: Sequence[Window], sink: Path, workers: int = 4,
                   seeds: Sequence[int] = SEEDS, store_dir: Path = store.DEFAULT_STORE_DIR, log=print) -> pd.DataFrame:
    """
    Tick designs on raw ticks under the eight loop timings (FINAL10 round 4): ONE raw-tick prepare per window with its
    own warm-up, never cut from a longer jittered prepare (the first poll would take an extra jitter draw:
    ``ladder/BUILD.md``). The regime is composed on that prepare's own rows and its own trend. Resume-safe per
    (variant, window, seed).
    """
    from ..engine import fast
    d = DESIGNS[key]
    check_vids(vids)
    for w in windows:
        guard(w.start, w.end, f"{key} {w.name}")
    book = None
    _G["history_from"] = ""
    fids = sorted({f for v in vids for f in Variant(v).fids})
    if fids:
        book = FilterBook(d.symbol, _latest(DEV_END, *(w.end for w in windows)), store_dir)
        _G["history_from"] = book.history_from
    t_all = time.time()
    for w in windows:
        have = read_rows(sink)
        have = have[(have["mode"] == "ticks") & (have["window"].astype(str) == w.name)]
        done = set(zip(have["vid"], have["seed"].astype(int)))
        todo = [(v, int(s)) for v in vids for s in seeds if (v, int(s)) not in done]
        if not todo:
            continue
        t0 = time.time()
        prep = fast.prepare(d.symbol, w.start, w.end, list(TFS_PREP), mode="ticks", store_dir=store_dir)
        cfg = design_cfg(key, w.start, w.end)
        _G.update(prep=prep, trend={key: trend_series(prep, cfg)})
        _G["steps"] = {f: book.steps(f, prep.t_ms) for f in fids} if book else {}
        _warm_kernel(key, prep)
        log(f"{key} {w.name}: {prep.n_rows:,} ticks ready ({time.time() - t0:.0f}s), {len(todo)} runs")
        for out in _map(_tick_task, [(key, v, w, s) for v, s in todo], workers):
            _append(sink, out["rows"])
        _G.pop("prep", None)
        del prep
        gc.collect()
        log(f"  {key} {w.name} done ({time.time() - t0:.0f}s; {time.time() - t_all:.0f}s in all)")
    return read_rows(sink)


def _bar_row(key: str, vid: str, w: Window, res, run_s: float, history_from: str) -> dict:
    final = float(res.final)
    return dict(design=key, symbol=DESIGNS[key].symbol, vid=vid, kind=Variant(vid).kind, stage=w.stage,
                window=w.name, period=w.period, start=w.start, end=w.end, mode="bars", seed=0,
                final_equity=round(final, 6), net=round(final - ACCOUNT, 6),
                return_pct=round((final - ACCOUNT) / ACCOUNT * 100.0, 6), max_dd_pct=round(float(res.max_dd) * 100.0, 6),
                trades=int(len(res.trades_pnl)), wiped=bool(res.wiped),
                wiped_at=str(TM.utc(res.wipe_t)) if res.wiped and res.wipe_t is not None else "",
                blocked_regime=np.nan, blocked_trend=np.nan, skipped_trades=int(res.skipped), run_s=round(run_s, 3),
                history_from=history_from)


class TurtleRunner:
    """The Turtle on external's M1-bar model: the market from 2018-01-01 (FINAL10's), the bot's votes, the base plan,
    and every variant's plan per window."""

    def __init__(self, end: str = DEV_END, store_dir: Path = store.DEFAULT_STORE_DIR, cache_dir: Optional[Path] = None,
                 log=print):
        t0 = time.time()
        self.book = FilterBook("BTCUSDm", end, store_dir, history_from=TURTLE_HISTORY)
        self.m = self.book.mk
        self.sig = X.bot_signals(self.m, cache_dir)
        self.base = turtle_base(self.m, self.sig)
        self._plans: Dict[str, X.PathPlan] = {}
        log(f"Turtle: {len(self.m):,} M1 bars {TM.utc(self.m.t[0])} .. {TM.utc(self.m.t[-1])}, votes and plan ready "
            f"({time.time() - t0:.0f}s)")

    def ix(self, w: Window) -> Tuple[int, int]:
        a_s, z_s = TM.s_of(w.start), TM.s_of(w.end)
        return int(np.searchsorted(self.m.t, a_s, "left")), int(np.searchsorted(self.m.t, z_s, "left"))

    def plan(self, vid: str, w: Window) -> X.PathPlan:
        """The variant's plan (the same for every window but for the exit overlays, which are built per window)."""
        v = Variant(vid)
        if v.kind == "exit":
            a_ix, z_ix = self.ix(w)
            tc, xl, xs = exit_flags(self.book, v.exit)
            return turtle_exit_plan(self.base, self.m, tc, xl, xs, a_ix, z_ix)
        if vid not in self._plans:
            if v.kind == "base":
                p = self.base
            elif v.kind == "identity":
                n_dt, n_m = len(self.base.dt), len(self.m.t)
                p = turtle_gate(self.base, self.m, np.ones(n_dt, bool), np.ones(n_dt, bool), np.ones(n_m, bool),
                                np.ones(n_m, bool))
            else:
                p = turtle_filtered(self.base, self.m, self.book, vid)
            self._plans = {vid: p}                 # one at a time: a plan holds two masks of every M1 bar
        return self._plans[vid]

    def account(self, vid: str, w: Window):
        a_ix, z_ix = self.ix(w)
        res, daily, trades = F._bar_account(X, self.m, self.plan(vid, w), X.BOT, a_ix, z_ix)
        return res, daily, trades


def run_bar_stage(key: str, vids: Sequence[str], windows: Sequence[Window], sink: Path, daily_sink: Path,
                  runner: Optional[TurtleRunner] = None, store_dir: Path = store.DEFAULT_STORE_DIR,
                  cache_dir: Optional[Path] = None, log=print) -> pd.DataFrame:
    """The Turtle: every variant on every window, a fresh $2,000 account each (``final10._bar_account``)."""
    if DESIGNS[key].engine != "bars":
        raise ValueError(f"{key} is not the M1-bar design")
    check_vids(vids)
    for w in windows:
        guard(w.start, w.end, f"{key} {w.name}")
    todo = [v for v in vids if v not in _done(read_rows(sink), windows, "bars")]
    log(f"{key}: {len(todo)} of {len(vids)} variants to run on {len(windows)} windows -> {sink}")
    if not todo:
        return read_rows(sink)
    run = runner or TurtleRunner(_latest(DEV_END, *(w.end for w in windows)), store_dir, cache_dir, log)
    for vid in todo:
        t0 = time.time()
        rows, daily = [], []
        for w in windows:
            t1 = time.time()
            res, dser, _ = run.account(vid, w)
            rows.append(_bar_row(key, vid, w, res, time.time() - t1, run.book.history_from))
            if w.continuous:
                daily += [dict(design=key, vid=vid, window=w.name, date=str(t.date()), equity=round(float(e), 6))
                          for t, e in dser.items()]
        _append(daily_sink, daily, ["design", "vid", "window", "date", "equity"])
        _append(sink, rows)
        log(f"  {key} {vid}: {time.time() - t0:.1f}s")
    return read_rows(sink)


def dev_paths(key: str, out: Path = STUDY_DIR) -> Tuple[Path, Path]:
    return Path(out) / f"dev_{key}.csv", Path(out) / f"daily5y_{key}.csv"


class IdentityError(AssertionError):
    """The always-allow filter did not reproduce the design (PREREG 2): no variant may run."""


def check_identity(rows: pd.DataFrame, windows: Sequence[Window] = DEV_WINDOWS) -> int:
    """The identity filter's accounts equal the base's on every window (final equity, max DD, trades, wiped); returns
    the number of accounts compared."""
    cols = ["final_equity", "max_dd_pct", "trades", "wiped"]
    names = [w.name for w in windows]
    a = rows[rows["vid"] == BASE].set_index("window").reindex(names)[cols]
    b = rows[rows["vid"] == IDENTITY].set_index("window").reindex(names)[cols]
    if a.isna().any().any() or b.isna().any().any():
        raise IdentityError("the base or the identity filter is missing a window")
    if not a.astype(str).equals(b.astype(str)):
        bad = [n for n in names if not a.loc[n].astype(str).equals(b.loc[n].astype(str))]
        raise IdentityError(f"the identity filter differs from the base on {bad}")
    return len(names)


def run_dev(key: str, vids: Optional[Sequence[str]] = None, out: Path = STUDY_DIR, workers: int = 4, prep=None,
            store_dir: Path = store.DEFAULT_STORE_DIR, cache_dir: Optional[Path] = None, log=print) -> pd.DataFrame:
    """
    PREREG 4's Development format for one design: the 23 fresh quarters and the 5-year account per variant
    (``stage1_vids`` by default). The base and the always-allow filter run first, and no other variant runs unless the
    identity filter's 24 accounts equal the base's (PREREG 2: "this identity check runs before any variant").
    """
    vids = list(vids) if vids is not None else stage1_vids(key)
    sink, daily = dev_paths(key, out)
    first = [BASE, IDENTITY]
    rest = [v for v in vids if v not in first]
    d = DESIGNS[key]
    if d.engine == "bars":
        run = None
        if not {BASE, IDENTITY} <= _done(read_rows(sink), DEV_WINDOWS, "bars") or rest:
            for w in DEV_WINDOWS:
                guard(w.start, w.end, f"{key} {w.name}")
            run = TurtleRunner(DEV_END, store_dir, cache_dir, log)
        run_bar_stage(key, first, DEV_WINDOWS, sink, daily, runner=run, store_dir=store_dir, log=log)
        n = check_identity(read_rows(sink))
        log(f"{key}: the identity filter equals the base on all {n} accounts")
        return run_bar_stage(key, rest, DEV_WINDOWS, sink, daily, runner=run, store_dir=store_dir, log=log) \
            if rest else read_rows(sink)
    from ..engine import fast
    if prep is None and (rest or not {BASE, IDENTITY} <= _done(read_rows(sink), DEV_WINDOWS, "sec")):
        for w in DEV_WINDOWS:
            guard(w.start, w.end, f"{key} {w.name}")
        t0 = time.time()
        prep = fast.prepare(d.symbol, DEV_START, DEV_END, list(TFS_PREP), mode="sec", store_dir=store_dir)
        log(f"{key}: per-second prepare {DEV_START} .. {DEV_END} ({time.time() - t0:.0f}s)")
    run_sec_stage(key, first, DEV_WINDOWS, sink, daily, workers, prep, store_dir, log)
    n = check_identity(read_rows(sink))
    log(f"{key}: the identity filter equals the base on all {n} accounts")
    return run_sec_stage(key, rest, DEV_WINDOWS, sink, daily, workers, prep, store_dir, log) if rest \
        else read_rows(sink)


def run_confirm(key: str, vids: Sequence[str], out: Path = STUDY_DIR, workers: int = 4,
                store_dir: Path = store.DEFAULT_STORE_DIR, log=print) -> pd.DataFrame:
    """PREREG 5's confirmation: the candidates and the base on the 23 quarters on raw ticks, eight timings each."""
    if DESIGNS[key].engine != "ticks":
        raise ValueError("the Turtle's model has no loop timing: it needs no confirmation (PREREG 5)")
    vids = [BASE] + [v for v in vids if v != BASE]
    return run_tick_stage(key, vids, DEV_QUARTERS, Path(out) / f"confirm_{key}.csv", workers, SEEDS, store_dir, log)


def run_exam(key: str, vids: Sequence[str], out: Path = STUDY_DIR, workers: int = 4,
             store_dir: Path = store.DEFAULT_STORE_DIR, cache_dir: Optional[Path] = None, log=print) -> pd.DataFrame:
    """
    PREREG 6, after the freeze only (the guard refuses it before): each finalist and its base on the sealed windows
    of the symbol. Tick designs: every quarter on raw ticks under the eight timings (median per quarter), and the same
    quarters plus the continuous account per second beside them. The Turtle: the M1-bar model. Then the forward
    window per second / on the M1-bar model, for information.
    """
    d = DESIGNS[key]
    vids = [BASE] + [v for v in vids if v != BASE]
    for qs, cont in exam_windows(d.symbol).values():
        for w in qs + (cont,):
            guard(w.start, w.end, f"{key} exam {w.name}")        # before anything is read
    fw = forward_window(d.symbol, store_dir)
    out = Path(out)
    res = []
    for name, (qs, cont) in exam_windows(d.symbol).items():
        if d.engine == "bars":
            res.append(run_bar_stage(key, vids, qs + (cont,), out / f"exam_{key}.csv", out / f"daily_exam_{key}.csv",
                                     store_dir=store_dir, cache_dir=cache_dir, log=log))
        else:
            res.append(run_tick_stage(key, vids, qs, out / f"exam_{key}.csv", workers, SEEDS, store_dir, log))
            res.append(run_sec_stage(key, vids, qs + (cont,), out / f"exam_sec_{key}.csv",
                                     out / f"daily_exam_{key}.csv", workers, None, store_dir, log))
    if d.engine == "bars":
        res.append(run_bar_stage(key, vids, (fw,), out / f"forward_{key}.csv", out / f"daily_forward_{key}.csv",
                                 store_dir=store_dir, cache_dir=cache_dir, log=log))
    else:
        res.append(run_sec_stage(key, vids, (fw,), out / f"forward_{key}.csv", out / f"daily_forward_{key}.csv",
                                 workers, None, store_dir, log))
    return pd.concat(res, ignore_index=True)


# ───────────────────────────── the score (PREREG 5) ─────────────────────────────

def quarter_table(rows: pd.DataFrame, windows: Sequence[Window] = DEV_QUARTERS) -> pd.DataFrame:
    """Per variant and quarter: net and max DD (the median over the loop timings when several ran, FINAL10 round 4),
    trades (median), and whether any run was wiped."""
    names = {w.name: w for w in windows}
    r = rows[rows["window"].astype(str).isin(names)].copy()
    if r.empty:
        return pd.DataFrame(columns=["vid", "window", "period", "net", "dd", "trades", "wiped", "runs"])
    r["wiped"] = r["wiped"].astype(str).str.lower().isin(["true", "1"])
    q = r.groupby(["vid", "window"], sort=False).agg(net=("net", "median"), dd=("max_dd_pct", "median"),
                                                      trades=("trades", "median"), wiped=("wiped", "any"),
                                                      runs=("net", "size")).reset_index()
    q["period"] = q["window"].map(lambda n: names[n].period)
    return q


def yardstick(q: pd.DataFrame, periods: Sequence[str] = P5, n_quarters: Optional[int] = None) -> pd.DataFrame:
    """
    FINAL10's selection yardstick per variant (``final10.evidence``): each period's value is the mean net profit per
    fresh quarter; ``mean_q`` the mean of the period values; ``dd_fresh`` the worst quarter's max DD %;
    score = mean_q / max(dd_fresh, 1); eligible: at least 4 of the periods up, no account wiped, dd_fresh <= 50, mean
    above 0. ``n_quarters``: when given, a variant missing a quarter is an error.
    """
    rows = []
    for vid, g in q.groupby("vid", sort=False):
        if n_quarters is not None and len(g) != n_quarters:
            raise ValueError(f"{vid}: {len(g)} quarters, {n_quarters} expected")
        per = g.groupby("period")["net"].mean()
        vals = {p: float(per.get(p, np.nan)) for p in periods}
        rows.append(dict(vid=vid, **vals, dd_fresh=float(g["dd"].max()), lost_q=int((g["net"] < 0).sum()),
                         n_q=int(len(g)), wiped=bool(g["wiped"].any()), trades=float(g["trades"].sum())))
    Y = pd.DataFrame(rows)
    if Y.empty:
        return Y
    Y["periods_up"] = (Y[list(periods)] > 0).sum(axis=1)
    Y["mean_q"] = Y[list(periods)].mean(axis=1)
    Y["score"] = Y["mean_q"] / Y["dd_fresh"].clip(lower=1.0)
    Y["eligible"] = ((Y["periods_up"] >= MIN_PERIODS_UP) & (~Y["wiped"]) & (Y["dd_fresh"] <= MAX_DD_PCT)
                     & (Y["mean_q"] > 0))
    Y["kind"] = [Variant(v).kind for v in Y["vid"]]
    return Y


def profit_floor(base_mean: float) -> float:
    """90% of the base's mean profit per quarter; the base's own value when it is 0 or below (the exam's convention,
    PREREG 6, used for Development too where PREREG 5 is silent)."""
    return PROFIT_FLOOR * base_mean if base_mean > 0 else base_mean


def meets_floor(mean_q: float, base_mean: float) -> bool:
    """``mean_q >= profit_floor(base_mean)``, with a margin of 1e-9 of the base so that exactly 90% is not lost to
    rounding (0.9 * 100 is 90.00000000000001 in floating point)."""
    return bool(mean_q >= profit_floor(base_mean) - 1e-9 * max(abs(base_mean), 1.0))


def better(v, b) -> bool:
    """PREREG 5: a variant is better than its base when its score is higher, it has no fewer periods up, its mean profit
    per quarter is at least 90% of the base's, no account is wiped and its worst-quarter DD is at most 50%."""
    return bool(v["score"] > b["score"] and v["periods_up"] >= b["periods_up"]
                and meets_floor(float(v["mean_q"]), float(b["mean_q"])) and not bool(v["wiped"])
                and v["dd_fresh"] <= MAX_DD_PCT)


def mark_better(Y: pd.DataFrame, base_vid: str = BASE) -> pd.DataFrame:
    b = Y[Y["vid"] == base_vid]
    if len(b) != 1:
        raise ValueError(f"the base {base_vid} must be in the table once")
    b = b.iloc[0]
    Y = Y.copy()
    Y["better"] = [better(r, b) if r["vid"] != base_vid else False for _, r in Y.iterrows()]
    Y["beats_base_score"] = Y["score"] > float(b["score"])
    return Y


def _rank(Y: pd.DataFrame) -> pd.DataFrame:
    return Y.sort_values(["score", "mean_q", "vid"], ascending=[False, False, True], kind="stable")


def candidates(Y: pd.DataFrame, base_vid: str = BASE, k: int = 3) -> List[str]:
    """The three better variants (single, pair or Turtle exit) with the highest Development scores."""
    Y = mark_better(Y, base_vid)
    c = Y[Y["better"] & Y["kind"].isin(["single", "pair", "exit"])]
    return _rank(c)["vid"].head(k).tolist()


def stage2_pairs(Y: pd.DataFrame, base_vid: str = BASE) -> List[str]:
    """The AND of every pair among the three best single filters by Development score, only from filters whose score
    beats the base's; fewer than two such filters: no pairs (PREREG 3)."""
    Y = mark_better(Y, base_vid)
    s = _rank(Y[(Y["kind"] == "single") & Y["beats_base_score"]])["vid"].head(3).tolist()
    return [pair_vid(a, b) for i, a in enumerate(s) for b in s[i + 1:]]


def finalists(cands: Sequence[str], Yc: Optional[pd.DataFrame], base_vid: str = BASE, k: int = 2) -> List[str]:
    """Up to two confirmed candidates with the highest confirmed scores; ``Yc`` is the confirmation's yardstick (None
    for the Turtle, which needs no confirmation: its candidates in their Development order)."""
    if Yc is None:
        return list(cands)[:k]
    Yc = mark_better(Yc, base_vid)
    ok = Yc[Yc["vid"].isin(cands) & Yc["better"]]
    return _rank(ok)["vid"].head(k).tolist()


def window_score(q: pd.DataFrame) -> dict:
    """A sealed window's yardstick over its quarters (PREREG 6): mean net per quarter / max(worst quarter DD, 1)."""
    m = float(q["net"].mean())
    dd = float(q["dd"].max())
    return {"mean_q": m, "dd_worst": dd, "score": m / max(dd, 1.0), "n_q": int(len(q)), "wiped": bool(q["wiped"].any())}


def exam_pass(fin: dict, base: dict) -> bool:
    """PREREG 6: the finalist's score over the window's quarters is at least the base's, and its mean profit per quarter
    at least 90% of the base's (at least the base's when the base's mean is 0 or below)."""
    return bool(fin["score"] >= base["score"] and meets_floor(fin["mean_q"], base["mean_q"]))


def exam_verdict(key: str, rows: pd.DataFrame, finalist_vids: Sequence[str]) -> pd.DataFrame:
    """Per finalist: the window scores (median of the raw-tick timings for the tick designs) against the base's and
    whether it passes every window its symbol needs (gold: T1 and T2; BTC: T1)."""
    sym = DESIGNS[key].symbol
    mode = "bars" if DESIGNS[key].engine == "bars" else "ticks"
    out = []
    for vid in finalist_vids:
        rec = {"design": key, "vid": vid}
        ok_all = True
        for name, (qs, _) in exam_windows(sym).items():
            q = quarter_table(rows[rows["mode"] == mode], qs)
            b, f = q[q["vid"] == BASE], q[q["vid"] == vid]
            if len(b) != len(qs) or len(f) != len(qs):
                raise ValueError(f"{key} {vid} {name}: not every quarter ran")
            sb, sf = window_score(b), window_score(f)
            passed = exam_pass(sf, sb)
            ok_all &= passed
            rec.update({f"{name}_score": sf["score"], f"{name}_base_score": sb["score"], f"{name}_mean_q": sf["mean_q"],
                        f"{name}_base_mean_q": sb["mean_q"], f"{name}_pass": passed})
        rec["passes"] = ok_all
        out.append(rec)
    return pd.DataFrame(out)


# ───────────────────────────── the freeze ─────────────────────────────

def blob_id(path: Path) -> str:
    """The git blob id of a file (what ``git hash-object`` prints), computed without git."""
    body = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def rule_text(key: str, vid: str) -> str:
    """A variant in words (FINALISTS.md)."""
    v = Variant(vid)
    if v.kind == "base":
        return "the design as published (no filter)"
    if v.kind == "exit":
        _, method, tf = v.exit.split("-")
        what = ("a Heikin Ashi colour flip against the position" if method == "M1" else
                "the Heikin Ashi streak in the position's direction reaching its rare age (90th percentile, causal)")
        return f"exit at the close of {tf} bars on {what}"
    parts = []
    for fid in v.fids:
        f = filter_of(fid)
        if f.clock:
            parts.append(f"{fid}: entries only at New York hours {list(SESSIONS[fid])}")
        else:
            parts.append(f"{fid}: {f.family}{'(' + str(f.n) + ')' if f.n else ''} on closed {f.tf} bars")
    return " AND ".join(parts)


def freeze(chosen: Dict[str, List[str]], scores: Optional[Dict[str, pd.DataFrame]] = None,
           study_dir: Optional[Path] = None, note: str = "") -> Path:
    """
    Write FINALISTS.md (per design its finalists in words, their Development and confirmed scores, and the git blob
    ids of the code that computes them) and FINALISTS.md.sha256. After this the guard opens T1, T2 and the forward
    window. Refuses to overwrite an existing freeze.
    """
    d = Path(STUDY_DIR if study_dir is None else study_dir)
    f, h = d / "FINALISTS.md", d / "FINALISTS.md.sha256"
    if f.exists() or h.exists():
        raise FileExistsError(f"{f} already exists: a freeze is written once")
    lines = ["# Entry filters on the bots' designs: the finalists (frozen)", "",
             f"Written {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC, before T1, T2 or the forward window was "
             "computed for anything. The sha256 of this file is in `FINALISTS.md.sha256`.", ""]
    if note:
        lines += [note, ""]
    lines += ["| Design | Finalist | Rule | Development score | Confirmed score |", "|---|---|---|---|---|"]
    for key, vids in chosen.items():
        if not vids:
            lines.append(f"| {DESIGNS[key].name} | none | no filter improved it | | |")
            continue
        for vid in vids:
            sc = scores.get(key) if scores else None
            dev = cf = ""
            if sc is not None and vid in set(sc["vid"]):
                r = sc[sc["vid"] == vid].iloc[0]
                dev = f"{r['score']:.3f}" if "score" in r else ""
                cf = f"{r['confirmed_score']:.3f}" if "confirmed_score" in r and pd.notna(r["confirmed_score"]) else ""
            lines.append(f"| {DESIGNS[key].name} | `{vid}` | {rule_text(key, vid)} | {dev} | {cf} |")
    lines += ["", "Code (git blob ids):", ""]
    for p in CODE_FILES + PORT_FILES:
        path = REPO_ROOT / p
        if path.exists():
            lines.append(f"- `{p}`: {blob_id(path)}")
    body = ("\n".join(lines) + "\n").encode("utf-8")
    d.mkdir(parents=True, exist_ok=True)
    f.write_bytes(body)
    h.write_text(f"{hashlib.sha256(body).hexdigest()}  FINALISTS.md\n", encoding="utf-8")
    return f


# ───────────────────────────── multiple testing (PREREG 7) ─────────────────────────────

def daily_matrix(daily: pd.DataFrame, vids: Sequence[str], window: str = "5y") -> Tuple[pd.DatetimeIndex, np.ndarray]:
    """Equity at the start of each day per variant on the union of the days any of them has (a day a variant has no
    sample carries its last value), days x variants."""
    d = daily[(daily["window"] == window) & daily["vid"].isin(vids)]
    p = d.pivot_table(index="date", columns="vid", values="equity", aggfunc="last").sort_index()
    missing = [v for v in vids if v not in p.columns]
    if missing:
        raise ValueError(f"no daily equity for {missing}")
    p = p[list(vids)].ffill()
    if p.isna().any().any():
        raise ValueError("a variant has no equity on the first day")
    return p.index, p.to_numpy(np.float64)


def multiple_testing(key: str, daily: pd.DataFrame, Y: Optional[pd.DataFrame] = None, final_equity: Optional[dict] = None,
                     B_: int = 5000, seed: int = 20261128) -> pd.DataFrame:
    """
    PREREG 7 for one design. SPA: Hansen's p-value for "some variant beats the base", over all its variants (singles,
    pairs, exits; not the base or the identity filter), on the daily P&L differences of their 5-year accounts against
    the base (``tradeiq.bootstrap_pvalues``: ``silver.spa_test``'s stationary bootstrap, benchmark 0, plus White's
    Reality Check), with a mean block of eight weeks in days (study 1's eight weeks). Deflated Sharpe: for the variant
    with the best 5-year daily Sharpe (and the best Development score when ``Y`` is given), the DSR of its daily returns
    given N = the number of variants and the variance of their Sharpe ratios (``silver.expected_max_sr`` / ``dsr``).
    ``final_equity``: vid -> final equity of the 5-year account, to close the last day.
    """
    from . import silver as S
    from .tradeiq import bootstrap_pvalues
    vids = [v for v in dict.fromkeys(daily.loc[daily["window"] == "5y", "vid"]) if Variant(v).kind in
            ("single", "pair", "exit")]
    # only variants whose Development record is complete (a 5-year account; all 23 quarters when Y is given)
    if final_equity is not None:
        vids = [v for v in vids if v in final_equity]
    if Y is not None:
        vids = [v for v in vids if v in set(Y["vid"])]
    if not vids:
        raise ValueError("no variant has a 5-year daily equity")
    days, E = daily_matrix(daily, [BASE] + vids)
    if final_equity is not None:
        E = np.vstack([E, [final_equity[v] for v in [BASE] + vids]])
    pnl = np.diff(E, axis=0)
    D = pnl[:, 1:] - pnl[:, :1]
    T = D.shape[0]
    weeks = max((days[-1] - days[0]).days / 7.0, 1.0)
    block = 8.0 * T / weeks
    bp = bootstrap_pvalues(D, B_=B_, block=block, seed=seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.diff(E, axis=0) / E[:-1]
    R = R[:, 1:]
    sd = R.std(axis=0, ddof=1)
    sr = np.where(sd > 0, R.mean(axis=0) / np.where(sd > 0, sd, 1.0), 0.0)
    N = len(vids)
    var = float(np.var(sr, ddof=1)) if N > 1 else 0.0
    sr0 = S.expected_max_sr(var, N) if N > 1 else 0.0
    picks = [("best 5y daily Sharpe", vids[int(np.argmax(sr))])]
    if Y is not None:
        y = _rank(Y[Y["vid"].isin(vids)])
        if len(y):
            picks.append(("best Development score", y["vid"].iloc[0]))
    out = []
    for role, vid in picks:
        j = vids.index(vid)
        r = pd.Series(R[:, j])
        out.append({"design": key, "role": role, "vid": vid, "N": N, "T_days": T, "block_days": block,
                    "sr_daily": float(sr[j]), "skew": float(r.skew()), "kurt": float(r.kurt() + 3.0),
                    "var_sr_trials": var, "e_max_sr": sr0,
                    "dsr": S.dsr(float(sr[j]), T, float(r.skew()), float(r.kurt() + 3.0), sr0),
                    "spa_p": bp["spa_p"], "spa_best_vid": vids[bp["spa_best"]], "rc_p": bp["rc_p"],
                    "rc_best_vid": vids[bp["rc_best"]], "n_in_bootstrap": bp["n_used"]})
    return pd.DataFrame(out)


# ───────────────────────────── the identity checks ─────────────────────────────

def identity_ticks(symbol: str, work: Path, full: bool = True, workers: int = 1,
                   store_dir: Path = store.DEFAULT_STORE_DIR, keys: Optional[Sequence[str]] = None,
                   log=print) -> pd.DataFrame:
    """
    PREREG 2's identity check before any variant: per tick design of ``symbol``, the 5-year account cut from the one
    per-second prepare of 2021-01-01 to 2026-11-13 (a) without a regime and (b) with the always-allow filter composed
    with the rebuilt trend; both must equal FINAL10's published 5-year account and (b)'s fills must equal (a)'s.
    ``full``: then the Development format for the base and the identity filter (23 quarters + 5y, per-variant run
    time), written to ``work``; the 24 accounts must be equal pair by pair.
    """
    from ..engine import fast
    keys = list(keys) if keys else [k for k, d in DESIGNS.items() if d.symbol == symbol and d.engine == "ticks"]
    work = Path(work)
    t0 = time.time()
    prep = fast.prepare(symbol, DEV_START, DEV_END, list(TFS_PREP), mode="sec", store_dir=store_dir)
    t_prep = time.time() - t0
    log(f"{symbol}: {prep.n_rows:,} per-second rows {DEV_START} .. {DEV_END} ({t_prep:.1f}s)")
    out = []
    for key in keys:
        pub = published_5y(key)
        cfg = design_cfg(key, FIVE_Y.start, FIVE_Y.end)
        trend = trend_series(prep, design_cfg(key, DEV_START, DEV_END))
        reg = compose(trend, ALLOW)
        t1 = time.time()
        a = fast.run(cfg, prep)
        ta = time.time() - t1
        t1 = time.time()
        b = fast.run(cfg, prep, regime=reg)
        tb = time.time() - t1
        same = a.fills.reset_index(drop=True).equals(b.fills.reset_index(drop=True))
        rec = dict(symbol=symbol, design=key, rows=prep.n_rows, prepare_s=round(t_prep, 1),
                   published_final=pub["final_equity"], published_dd=pub["max_dd_pct"], published_trades=pub["trades"],
                   base_final=round(float(a.scalars["final_equity"]), 2), base_dd=round(float(a.scalars["max_drawdown_pct"]), 3),
                   base_trades=int(len(a.baskets)), allow_final=round(float(b.scalars["final_equity"]), 2),
                   allow_dd=round(float(b.scalars["max_drawdown_pct"]), 3), allow_trades=int(len(b.baskets)),
                   fills=int(len(a.fills)), fills_identical=bool(same),
                   base_blocked_trend=int(a.counters["polls_entry_blocked_trend"]),
                   allow_blocked_regime=int(b.counters["polls_entry_blocked_regime"]),
                   allow_blocked_trend=int(b.counters["polls_entry_blocked_trend"]),
                   regime_entries=int(len(reg[0])), base_run_s=round(ta, 1), allow_run_s=round(tb, 1))
        rec["equals_published"] = bool(abs(rec["base_final"] - pub["final_equity"]) < 0.005
                                       and rec["base_trades"] == pub["trades"]
                                       and abs(round(rec["base_dd"], 2) - round(pub["max_dd_pct"], 2)) < 0.006)
        log(json.dumps(rec))
        out.append(rec)
        del a, b
        gc.collect()
    if full:
        for key in keys:
            sink, daily = work / f"dev_{key}.csv", work / f"daily5y_{key}.csv"
            run_dev(key, [BASE, IDENTITY], work, workers, prep=prep, store_dir=store_dir, log=log)
            r = read_rows(sink)
            a, b = (r[r.vid == v].set_index("window").sort_index() for v in (BASE, IDENTITY))
            cols = ["final_equity", "max_dd_pct", "trades", "wiped"]
            same = bool(a[cols].equals(b[cols]))
            rec = next(x for x in out if x["design"] == key)
            rec.update(dev_accounts=int(len(a)), dev_identical=same,
                       dev_run_s_base=round(float(a["run_s"].sum()), 1), dev_run_s_allow=round(float(b["run_s"].sum()), 1),
                       dev_5y_final=float(a.loc["5y", "final_equity"]))
            log(f"{key}: Development format, {len(a)} accounts, base = identity filter: {same}; run time per variant "
                f"{rec['dev_run_s_base']:.0f}s (base) / {rec['dev_run_s_allow']:.0f}s (identity)")
    del prep
    gc.collect()
    df = pd.DataFrame(out)
    work.mkdir(parents=True, exist_ok=True)
    df.to_csv(work / f"identity_{symbol}.csv", index=False)
    return df


PATH_FIELDS = ("dir", "eix", "epx", "xix", "xpx", "why", "nleg", "leix", "lepx")


def same_path(p, q) -> bool:
    """Two ``external.run_path`` results are the same trades, leg for leg."""
    return all(np.array_equal(getattr(p, k), getattr(q, k)) for k in PATH_FIELDS)


def inert_flags(m, base_path, tc) -> Tuple[np.ndarray, np.ndarray]:
    """
    Exit flags at the closes ``tc`` that the base path never meets: "exit a long" only while the base is flat or
    short at that close's execution bar, "exit a short" only while flat or long, both while flat. Fed to
    ``turtle_exit_plan`` they create a new decision row at (nearly) every H4 close without ever closing a trade, so
    the plan must reproduce the base path exactly: a check of how the new rows re-arm and cancel the Turtle's
    stop-entry orders (one fill cancels both until the next D1 decision; rows of a day whose decision lies before the
    window carry no orders).
    """
    dx = np.searchsorted(m.t, np.asarray(tc, np.int64), side="left")
    held = np.zeros(len(m) + 1, np.int64)
    for d_, e, x in zip(base_path.dir, base_path.eix, base_path.xix):
        held[e:x + 1] = d_                    # the side held at each bar from the entry bar to the exit bar
    side = held[np.minimum(dx, len(m))]
    return side <= 0, side >= 0


def identity_turtle(work: Path, store_dir: Path = store.DEFAULT_STORE_DIR, cache_dir: Optional[Path] = None,
                    log=print) -> pd.DataFrame:
    """
    The Turtle's identity checks on the M1-bar model, on every Development window and the 5-year account:
    (1) the base and the no-op gate (every mask true) give the published 5-year account and the same trades, leg for
    leg; (2) the exit overlay without flags is the base; (3) the exit overlay with inert flags at every H4 close
    (``inert_flags``) is the base trade for trade.
    """
    work = Path(work)
    run = TurtleRunner(DEV_END, store_dir, cache_dir, log)
    pub = published_5y("btc_turtle")
    out = []
    for vid in (BASE, IDENTITY):
        t0 = time.time()
        res, daily, trades = run.account(vid, FIVE_Y)
        out.append(dict(design="btc_turtle", vid=vid, window="5y", final=round(res.final, 2),
                        dd=round(res.max_dd * 100.0, 4), trades=int(len(res.trades_pnl)),
                        published_final=pub["final_equity"], published_dd=pub["max_dd_pct"],
                        published_trades=pub["trades"], run_s=round(time.time() - t0, 3)))
        log(json.dumps(out[-1]))
    h4 = run.book.bars("H4")
    tc4 = np.asarray(h4.tc, np.int64)[np.asarray(h4.complete, bool)]
    ident, empty_ok, inert_ok, n_rows, iters = [], [], [], [], []
    t0 = time.time()
    for w in DEV_WINDOWS:
        a_ix, z_ix = run.ix(w)
        p0 = X.run_path(run.m, run.plan(BASE, w), a_ix, z_ix)
        p1 = X.run_path(run.m, run.plan(IDENTITY, w), a_ix, z_ix)
        ident.append(same_path(p0, p1))
        empty = turtle_exit_plan(run.base, run.m, np.zeros(0, np.int64), np.zeros(0, bool), np.zeros(0, bool),
                                 a_ix, z_ix)
        empty_ok.append(same_path(p0, X.run_path(run.m, empty, a_ix, z_ix)))
        xl, xs = inert_flags(run.m, p0, tc4)
        plan = turtle_exit_plan(run.base, run.m, tc4, xl, xs, a_ix, z_ix)
        n_rows.append(int(len(plan) - len(run.base)))
        inert_ok.append(same_path(p0, X.run_path(run.m, plan, a_ix, z_ix)))
    df = pd.DataFrame(out)
    df["dev_windows"] = len(DEV_WINDOWS)
    df["gate_identical_windows"] = int(sum(ident))
    df["empty_overlay_identical_windows"] = int(sum(empty_ok))
    df["inert_h4_overlay_identical_windows"] = int(sum(inert_ok))
    df["inert_h4_rows_5y"] = n_rows[-1]
    df["check_s"] = round(time.time() - t0, 1)
    log(f"Turtle: gate = base on {sum(ident)}/{len(ident)} windows, empty overlay {sum(empty_ok)}/{len(ident)}, "
        f"inert H4 overlay {sum(inert_ok)}/{len(ident)} ({n_rows[-1]} H4 rows in the 5-year plan)")
    work.mkdir(parents=True, exist_ok=True)
    df.to_csv(work / "identity_turtle.csv", index=False)
    return df


# ───────────────────────────── the comparison page (PREREG 6, after the exam) ─────────────────────────────

SID = "bot_filters"                    # the comparison page's source id (compare_page.SOURCES)
COMPARE_DATA = REPO_ROOT / "backtest_results" / "compare" / "data"
# study 2's exam file. The comparison windows 8y and new start 2018-11-13, inside study 2's sealed gold Early window
# (2017-2018): the workflow computes no P/L on bars before 2019-01-01 until this file exists (compare_page's rule for
# its own 8y / new rows, ``--allow-pre-2019``; both symbols)
STUDY2_EXAM = REPO_ROOT / "backtest_results" / "tradeiq_2027" / "EXAM.md"
COMPARE_WINDOWS: Tuple[Window, ...] = COMPARE_SEC + (COMPARE_1Y,)


class CompareRefused(PermissionError):
    """The comparison accounts may not run, or be exported, yet: study 2's exam file, the design's exam or the frozen
    FINALISTS.md is missing."""


def _cell(s) -> str:
    """A markdown table cell for matching: without code or emphasis marks, single spaces, lower case."""
    return " ".join(str(s).strip().strip("`*_").split()).lower()


def read_finalists(study_dir: Optional[Path] = None) -> Dict[str, List[str]]:
    """
    The frozen finalists per design, in their order, from FINALISTS.md's table (``freeze``: | Design | Finalist |
    Rule | ...). The columns are found by their names, not their places. A design is its name (``Design.name``) or its
    key, in any case and spacing; a finalist cell is a variant id with or without backticks, or "none", "-" or empty
    (no finalist). Every id is checked (``check_vids``) and must be a filter variant (single, pair or Turtle exit).
    Raises ``ValueError`` on an unknown design, a bad id or a file without the table; a design the table does not list
    is not in the result. The sha256 is ``finalists_frozen``'s business, not this function's.
    """
    d = Path(STUDY_DIR if study_dir is None else study_dir)
    text = (d / "FINALISTS.md").read_text(encoding="utf-8")
    names: Dict[str, str] = {}
    for k, des in DESIGNS.items():
        names[_cell(des.name)] = k
        names[_cell(k)] = k
    out: Dict[str, List[str]] = {}
    cols: Optional[Tuple[int, int]] = None
    tables = 0
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            cols = None                                  # a table ends at the first line that is not a row
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cols is None:
            low = [_cell(c) for c in cells]
            if "design" in low and "finalist" in low:
                cols = (low.index("design"), low.index("finalist"))
                tables += 1
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):          # the header's separator row
            continue
        if len(cells) <= max(cols):
            raise ValueError(f"FINALISTS.md: a row without a design or finalist cell: {line!r}")
        name, cell = cells[cols[0]], cells[cols[1]]
        key = names.get(_cell(name))
        if key is None:
            raise ValueError(f"FINALISTS.md: unknown design {name!r} (one of {[x.name for x in DESIGNS.values()]})")
        fins = out.setdefault(key, [])
        vid = cell.strip().strip("`").strip()
        if _cell(vid) in ("", "none", "-", "—", "n/a"):
            continue
        check_vids([vid])
        if Variant(vid).kind not in ("single", "pair", "exit"):
            raise ValueError(f"FINALISTS.md: {key}'s finalist {vid!r} is not a filter variant")
        if vid not in fins:
            fins.append(vid)
    if not tables:
        raise ValueError(f"{d / 'FINALISTS.md'}: no table with a Design and a Finalist column")
    return out


def exam_missing(key: str, vids: Sequence[str], out: Optional[Path] = None) -> List[str]:
    """
    What ``run_exam`` has not written yet for the base and ``vids`` in ``out`` (empty: the exam is complete): every
    quarter of every sealed window of the symbol (T1; gold also T2) on raw ticks under the eight timings
    (``exam_<key>.csv``) and per second with the continuous account (``exam_sec_<key>.csv``) for the tick designs;
    the quarters and the continuous account on the M1-bar model for the Turtle. The forward window (information only)
    is not required.
    """
    d = DESIGNS[key]
    out = Path(STUDY_DIR if out is None else out)
    vids = [BASE] + [v for v in vids if v != BASE]
    miss: List[str] = []
    rows = read_rows(out / f"exam_{key}.csv")
    sec = read_rows(out / f"exam_sec_{key}.csv") if d.engine == "ticks" else None
    for name, (qs, cont) in exam_windows(d.symbol).items():
        if d.engine == "bars":
            done = _done(rows, qs + (cont,), "bars")
            miss += [f"{v} {name.upper()} (M1-bar model)" for v in vids if v not in done]
        else:
            done_t = _done(rows, qs, "ticks", SEEDS)
            done_s = _done(sec, qs + (cont,), "sec")
            miss += [f"{v} {name.upper()} (raw ticks, {len(SEEDS)} timings)" for v in vids if v not in done_t]
            miss += [f"{v} {name.upper()} (per second)" for v in vids if v not in done_s]
    return miss


def compare_gate(key: str, out: Optional[Path] = None) -> List[str]:
    """
    What ``run_compare`` checks before anything is read; returns the design's frozen finalists (FINALISTS.md).
    Refuses (1) before the freeze: ``SealedWindowError`` (8y and new read T1; PREREG 6 runs these accounts after the
    exam); (2) while study 2's exam file does not exist: ``CompareRefused`` (8y and new start 2018-11-13, inside study
    2's sealed gold Early window; no P/L is computed on bars before 2019-01-01 until then, on either symbol, as
    compare_page does); (3) while the design's exam is not complete in ``out``: ``CompareRefused`` (``exam_missing``
    for the base and every finalist). A design without a finalist has no exam, so (3) does not apply to it.
    """
    if key not in DESIGNS:
        raise ValueError(f"unknown design {key!r}")
    if not finalists_frozen():
        raise SealedWindowError(f"compare {key}: {Path(STUDY_DIR) / 'FINALISTS.md'} with a matching sha256 does not "
                                "exist: the comparison accounts read T1 and come after the freeze and the exam "
                                "(PREREG 4, 6)")
    if not Path(STUDY2_EXAM).exists():
        raise CompareRefused(f"compare {key}: study 2's exam file {STUDY2_EXAM} does not exist: 8y and new start "
                             "2018-11-13, inside study 2's sealed Early window (gold 2017-2018), and no P/L is "
                             "computed on bars before 2019-01-01 until it exists (compare_page's rule)")
    fins = read_finalists().get(key, [])
    miss = exam_missing(key, fins, out) if fins else []
    if miss:
        raise CompareRefused(f"compare {key}: the exam is not complete ({len(miss)} missing, e.g. "
                             f"{'; '.join(miss[:3])}): run `exam --design {key} --vids {' '.join(fins)}` first")
    return fins


def run_compare(key: str, vids: Optional[Sequence[str]] = None, out: Path = STUDY_DIR, workers: int = 4,
                store_dir: Path = store.DEFAULT_STORE_DIR, cache_dir: Optional[Path] = None, log=print) -> pd.DataFrame:
    """
    The accounts of the owner's comparison page, after the exam (PREREG 6): 8 years, 5 years and the new window per
    second (cut from one 8-year prepare) and the last year on raw ticks under the eight timings; the Turtle on the
    M1-bar model. They mix in-sample and test data and say so where shown (``export_compare``). ``vids``: None = the
    design's frozen finalists (FINALISTS.md); the base always runs. ``compare_gate`` refuses before anything is read
    (the freeze, study 2's exam file, this design's exam); the guard still checks every window.
    """
    fins = compare_gate(key, out)
    vids = list(fins) if vids is None else list(vids)
    check_vids(vids)
    vids = [BASE] + [v for v in vids if v != BASE]
    log(f"{key}: comparison accounts of {', '.join(vids)} (FINALISTS.md: {', '.join(fins) or 'no finalist'})")
    out = Path(out)
    if DESIGNS[key].engine == "bars":
        return run_bar_stage(key, vids, COMPARE_SEC + (COMPARE_1Y,), out / f"compare_{key}.csv",
                             out / f"daily_compare_{key}.csv", store_dir=store_dir, cache_dir=cache_dir, log=log)
    a = run_sec_stage(key, vids, COMPARE_SEC, out / f"compare_{key}.csv", out / f"daily_compare_{key}.csv", workers,
                      None, store_dir, log)
    b = run_tick_stage(key, vids, (COMPARE_1Y,), out / f"compare_{key}.csv", workers, SEEDS, store_dir, log)
    return pd.concat([a, b], ignore_index=True)


# the designs as the page names them: FINAL10's names and families (compare_page.final10_series_and_metrics)
DESIGN_SHORT = {"xau_v3lite": "V3-lite", "xau_top1": "Top 1", "xau_top2": "Top 2", "btc_top2": "Top 2",
                "btc_turtle": "Turtle System 2 + bot votes"}
DESIGN_FAMILY = {"xau_v3lite": "V3-lite", "xau_top1": "Top 1-3 (optimiser v4)", "xau_top2": "Top 1-3 (optimiser v4)",
                 "btc_top2": "Top 1-3 (optimiser v4)", "btc_turtle": "Turtle"}
TF_WORDS = {"H1": "1H", "H4": "4H", "D1": "daily"}
FAMILY_WORDS = {"SIDE": "MA{n} side", "SLOPE": "MA{n} slope", "TREND": "MA{n} side and slope",
                "CROSS": "MA50 / MA200 cross", "LGATE200": "longs only above MA200",
                "SGATE200": "shorts only below MA200", "TSI": "TSI side", "LARSI": "Laguerre RSI side",
                "QQE": "QQE MOD colour", "VWRSI": "volume-weighted RSI side", "RIB": "Trend Target Ribbon",
                "MSD": "Market Structure Dashboard", "HA": "Heikin Ashi colour"}
SESSION_WORDS = {"SESS-KZ": "New York kill zones (02-05, 07-11)", "SESS-LN": "New York 02:00-11:00 only"}
EXIT_WORDS = {"M1": "exit on a {tf} Heikin Ashi flip", "M4": "exit at the {tf} Heikin Ashi streak's rare age"}
# PREREG 4: design-filter pairs that earlier work ran on T1; their T1 (the new window) is "not a clean test"
T1_NOT_CLEAN = {"xau_v3lite": ("SIDE200-D1",), "xau_top1": ("SIDE200-D1", "SIDE50-H4"),
                "btc_turtle": ("SIDE200-D1", "LGATE200-D1")}
# ``sample`` (compare_page's v2 column): the finalists were chosen on Development (2021-01-01 to 2026-11-13) and the
# designs tuned on 2021-2026 data (FINAL10 §3, §5); 5y and 1y lie inside it, new is T1 (the exam's sealed window) and
# 8y holds both (PREREG 6: these accounts are labelled as mixing in-sample and test data)
COMPARE_SAMPLE = {"8y": "mixed", "5y": "in", "new": "out", "1y": "in"}
SAMPLE_NOTE = {"8y": "mixes in-sample data (2021-2026: Development, where the finalists were chosen) with the sealed "
                     "test window T1 (13 Nov 2018 - 1 Jan 2021)",
               "5y": "in-sample: inside Development (2021-01-01 to 2026-11-13), where the finalists were chosen",
               "new": "out of sample: T1, the exam's sealed test window",
               "1y": "in-sample: inside Development, where the finalists were chosen"}
ENGINE_NOTE = {"ticks": "tick engine: 8y, 5y and new per second with one loop timing (cut from one 8-year prepare), "
                        "1y on raw ticks under 8 loop timings",
               "bars": "the M1-bar model (external.py as FINAL10 runs it), its market from 2018-01-01"}
DEV_FORMAT = {"ticks": "per second, one loop timing", "bars": "on the M1-bar model"}
MARKS = {"sec": "second", "ticks": "tick", "bars": "M1"}         # the marks of each run mode's max DD


def filter_words(fid: str) -> str:
    """A single filter in plain words, its timeframe first: "SIDE200-H4" is "4H MA200 side"."""
    f = filter_of(fid)
    if f.clock:
        return SESSION_WORDS[fid]
    return f"{TF_WORDS[f.tf]} {FAMILY_WORDS[f.family].format(n=f.n)}"


def variant_words(vid: str) -> str:
    """A variant's filter in plain words (a pair: both, joined by "and"), or the Turtle's exit; "" for the base."""
    v = Variant(vid)
    if v.kind == "base":
        return ""
    if v.kind == "identity":
        return "always-allow filter (identity check)"
    if v.kind == "exit":
        _, method, tf = v.exit.split("-")
        return EXIT_WORDS[method].format(tf=TF_WORDS[tf])
    return " and ".join(filter_words(f) for f in v.fids)


def variant_label(key: str, vid: str) -> str:
    """The page's label: "V3-lite + 4H MA200 side", "V3-lite (base, no added filter)"."""
    short = DESIGN_SHORT[key]
    v = Variant(vid)
    if v.kind == "base":
        return f"{short} (base, no added filter)"
    return f"{short}, {variant_words(vid)}" if v.kind == "exit" else f"{short} + {variant_words(vid)}"


def variant_tf(vid: str) -> str:
    """The timeframe of a variant's filter or exit in the page's names (1H, 4H, 1D; a pair on two of them: "1H+4H");
    "" for the base and the session filters."""
    v = Variant(vid)
    if v.kind == "exit":
        return TM_TF[v.exit.split("-")[2]]
    tfs = {filter_of(f).tf for f in v.fids if not filter_of(f).clock}
    return "+".join(TM_TF[t] for t in FILTER_TFS if t in tfs)


def variant_filter(key: str, vid: str) -> str:
    """The ``filter`` column: the variant's filter in words. The Turtle's design already filters its entries by the
    bot's votes (FINAL10's "bot votes"), which comes first; an exit follows a ';'."""
    words = variant_words(vid)
    if DESIGNS[key].engine != "bars":
        return words
    if Variant(vid).kind == "exit":
        return f"bot votes; {words}"
    return "bot votes" + (f" + {words}" if words else "")


def _truthy(x) -> bool:
    return str(x).strip().lower() in ("true", "1", "1.0")


def compare_accounts(key: str, rows: pd.DataFrame) -> Tuple[Dict[Tuple[str, str], dict], List[str]]:
    """
    The comparison accounts of one design from ``compare_<key>.csv`` (``run_compare``'s rows, ``read_rows``):
    ((vid, window) -> account, what is missing). Per second (8y, 5y, new) and on the M1-bar model (the Turtle, every
    window) an account is its one run. On raw ticks (the tick designs' 1y) it is the eight loop timings in FINAL10's 1y
    convention (``final10.run_ticks``): the final equity and the max DD are their medians; trades and wiped are the
    middle (upper-median) timing run's, the runs sorted by final equity (ties by seed); the range of the finals and
    the number of wiped timings are kept. A window counts only with every run it needs, over its own dates.
    """
    d = DESIGNS[key]
    r = rows[rows["design"].astype(str) == key]
    r = r.assign(vid=r["vid"].astype(str), window=r["window"].astype(str), mode=r["mode"].astype(str))
    out: Dict[Tuple[str, str], dict] = {}
    vids = list(dict.fromkeys(r["vid"]))
    missing = [] if BASE in vids else [f"{BASE}: the base runs with every comparison"]
    for vid in vids:
        for w in COMPARE_WINDOWS:
            mode = "bars" if d.engine == "bars" else ("ticks" if w.name == COMPARE_1Y.name else "sec")
            seeds = SEEDS if mode == "ticks" else (0,)
            g = r[(r["vid"] == vid) & (r["window"] == w.name) & (r["mode"] == mode) & r["seed"].isin(seeds)]
            if set(g["seed"].astype(int)) != set(seeds):
                missing.append(f"{vid} {w.name}: {g['seed'].nunique()} of {len(seeds)} {mode} runs")
                continue
            if not ((g["start"].astype(str).str[:10] == w.start).all() and (g["end"].astype(str).str[:10] == w.end)
                    .all()):
                missing.append(f"{vid} {w.name}: its rows are not over {w.start} .. {w.end}")
                continue
            g = g.sort_values("seed", kind="stable").sort_values("final_equity", kind="stable")
            mid = g.iloc[len(g) // 2]
            fe = g["final_equity"].to_numpy(np.float64)
            wiped = _truthy(mid["wiped"])
            out[(vid, w.name)] = dict(
                mode=mode, start=w.start, end=w.end, runs=int(len(g)), seed=int(mid["seed"]),
                final=float(np.median(fe)), dd=float(np.median(g["max_dd_pct"].to_numpy(np.float64))),
                trades=int(mid["trades"]), wiped=wiped,
                wiped_at=str(mid["wiped_at"]) if wiped and not pd.isna(mid["wiped_at"]) else "",
                final_min=float(fe.min()), final_max=float(fe.max()),
                wiped_runs=int(sum(_truthy(x) for x in g["wiped"])))
    return out, missing


def compare_curve(daily: pd.DataFrame, final: float, start: str, end: str, wiped_at: str = "") -> pd.DataFrame:
    """
    The contract's curve (date, equity_usd) of one account from its daily rows (``final10._tick_daily`` /
    ``final10._bar_account``: the equity at the start of each UTC day with a mark, the window's first day holding the
    $2,000): compare_page's ``eod_from_sod``, the convention of FINAL10's curves of the same designs on the page. The
    opening row is dated the day before the window starts and holds the $2,000; day D ends at the next marked day's
    opening mark (gold's Friday carries Sunday evening's); the last day ends at the account's final equity. A wiped
    account's curve stops on the day it was wiped (``wiped_at``): the tick engine's samples stop there, the M1-bar model
    marks the empty account on to the window's end.
    """
    from . import compare_page as CP
    days = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    d = daily.assign(day=days).sort_values("day", kind="stable")
    d = d[(d["day"] >= start) & (d["day"] < end)]
    if wiped_at:
        t = pd.Timestamp(wiped_at)
        d = d[d["day"] <= (t.tz_convert("UTC") if t.tzinfo is not None else t).strftime("%Y-%m-%d")]
    return CP.eod_from_sod(d["day"].tolist(), d["equity"].to_numpy(np.float64), float(final), start)


def _dev_scores(key: str, folder: Path, log=print) -> Dict[str, dict]:
    """vid -> the Development yardstick (``score_dev``: score, periods up, FINAL10's eligibility) from the study
    folder's ``dev_<key>.csv``; {} without the file or without a complete base."""
    if not dev_paths(key, folder)[0].exists():
        return {}
    try:
        Y = score_dev(key, folder)
    except (KeyError, ValueError) as e:
        log(f"  {key}: no Development scores ({e})")
        return {}
    if Y.empty or "score" not in Y:
        return {}
    return {str(r["vid"]): dict(score=float(r["score"]), periods_up=int(r["periods_up"]), eligible=bool(r["eligible"]))
            for r in Y.to_dict("records")}


def exam_results(key: str, fins: Sequence[str], folder: Optional[Path] = None) -> Dict[str, dict]:
    """vid -> {"exam": "pass" | "fail", "windows": "T1 pass, T2 fail"} of the design's finalists from
    ``exam_<key>.csv`` (PREREG 6: gold must pass T1 and T2, BTC T1); {} while the exam is not complete."""
    folder = Path(STUDY_DIR if folder is None else folder)
    if not fins or exam_missing(key, fins, folder):
        return {}
    ex = exam_verdict(key, read_rows(folder / f"exam_{key}.csv"), list(fins))
    names = list(exam_windows(DESIGNS[key].symbol))
    return {str(r["vid"]): {"exam": "pass" if r["passes"] else "fail",
                            "windows": ", ".join(f"{n.upper()} {'pass' if r[f'{n}_pass'] else 'fail'}" for n in names)}
            for r in ex.to_dict("records")}


def _compare_series(key: str, vid: str, fins: Sequence[str], dev: Dict[str, dict], exam: Dict[str, dict],
                    study: str) -> dict:
    d = DESIGNS[key]
    v = Variant(vid)
    role = "base" if v.kind == "base" else ("finalist" if vid in fins else "variant")
    sc, ex = dev.get(vid), exam.get(vid, {})
    notes = ["study 3: entry filters on the bots' designs (backtest_results/bot_filters)",
             "the design as published (FINAL10's): the base its filters are measured against" if v.kind == "base"
             else (rule_text(key, vid) or variant_words(vid)), ENGINE_NOTE[d.engine]]
    if role == "finalist":
        notes.append(f"finalist {list(fins).index(vid) + 1} of {len(fins)} (FINALISTS.md)")
    elif role == "variant":
        notes.append("not a finalist (FINALISTS.md)")
    if sc:
        notes.append(f"Development score {sc['score']:.3f} with {sc['periods_up']} of 5 periods up, "
                     f"{'' if sc['eligible'] else 'not '}eligible by FINAL10's rule (FINAL10's yardstick on its 23 "
                     f"quarters, {DEV_FORMAT[d.engine]})")
    if ex:
        notes.append(f"exam (PREREG 6): {ex['windows']}, so {ex['exam']}")
    dirty = [f for f in v.fids if f in T1_NOT_CLEAN.get(key, ())]
    tags = []
    if dirty:
        notes.append(f"T1 (the new window) is not a clean test of {', '.join(dirty)} on this design (PREREG 4)")
        tags.append("T1 not a clean test (PREREG 4)")
    kind = "rule" if d.engine == "bars" else ("bot" if v.kind == "base" else "bot+filter")
    return dict(series_id=f"{SID}:{key}|{vid}", source=SID, study=study, symbol=d.symbol, label=variant_label(key, vid),
                kind=kind, family=DESIGN_FAMILY[key], tf=variant_tf(vid), filter=variant_filter(key, vid), role=role,
                eligible=int(bool(sc and sc["eligible"])), exam=ex.get("exam", ""), notes="; ".join(notes),
                sizing="unit rule", tags=";".join(tags))


def _compare_metrics(series_id: str, w: Window, a: dict, source_file: str, score: Optional[float]) -> dict:
    final = float(a["final"])
    net = final - ACCOUNT
    years = (TM.s_of(a["end"]) - TM.s_of(a["start"])) / (365.25 * 86400.0)
    cagr = ((final / ACCOUNT) ** (1.0 / years) - 1.0) * 100.0 if final > 0 else -100.0
    if a["mode"] == "ticks":
        notes = [f"raw ticks under the {a['runs']} loop timings (seeds {SEEDS[0]}-{SEEDS[-1]}): final equity and max "
                 f"DD are their median (finals ${a['final_min']:,.2f} to ${a['final_max']:,.2f}); trades and wiped are "
                 "the middle (upper-median) timing run's, FINAL10's 1y convention; no daily curve (the raw-tick runs "
                 "keep none)"]
        if a["wiped_runs"]:
            notes.append(f"{a['wiped_runs']} of {a['runs']} timings wiped")
    elif a["mode"] == "sec":
        notes = ["per second with one loop timing (FINAL10's 8y / 5y mode), cut from one 8-year prepare; max DD on the "
                 "per-second marks"]
    else:
        notes = ["the M1-bar model; max DD on the marks of every M1 bar"]
    if a["wiped"] and a["wiped_at"]:
        notes.append(f"wiped at {a['wiped_at']}")
    notes.append(SAMPLE_NOTE[w.name])
    return dict(series_id=series_id, window=w.name, start=a["start"], end=a["end"], cost=1.0, basis="account",
                start_usd=ACCOUNT, final_usd=final, net_usd=net, return_pct=net / ACCOUNT * 100.0, cagr_pct=cagr,
                max_dd_usd="", max_dd_pct=float(a["dd"]), p_dd="", trades=int(a["trades"]), win_rate_pct="",
                profit_factor="", sharpe_w="", pos_quarters_pct="", worst_quarter_usd="", wiped=int(bool(a["wiped"])),
                dd_marks=MARKS[a["mode"]], score_final10="" if score is None else float(score),
                source_file=source_file, sample=COMPARE_SAMPLE[w.name], derived="", row_notes="; ".join(notes))


def export_compare(data: Optional[Path] = None, compare_dir: Optional[Path] = None, log=print) -> Dict[str, object]:
    """
    The comparison page's files of source ``bot_filters`` (compare_page's contract v2) from every
    ``compare_<key>.csv`` / ``daily_compare_<key>.csv`` in ``compare_dir`` (the study folder; its frozen FINALISTS.md
    gives the roles, ``exam_<key>.csv`` the exam and ``dev_<key>.csv`` the Development score and FINAL10's
    eligibility), into ``data`` (backtest_results/compare/data):
      ``bot_filters__series.csv``  per design its base (role base) and every variant compared: the finalists (role
                                   finalist, FINALISTS.md's order) and any other (variant); FINAL10's unit rule
                                   (``sizing`` "unit rule": units = floor(balance / 2,500) + 1, at most 10, x 0.01 lot);
      ``bot_filters__metrics.csv`` per series 8y, 5y, new and 1y at x1.0, account basis (``compare_accounts``): the max
                                   DD % on the run's own marks (second, tick, M1); no max DD in $ and so no P/DD (the
                                   runs keep none on those marks, and a daily curve is coarser); CAGR from the final
                                   equity (compare_page's definition); Sharpe and the quarters from the daily curve
                                   (``compare_page.fill_from_curve``, listed in ``derived``); ``sample`` per window;
      ``bot_filters__curves_<window>.csv.gz``  the daily curves (``compare_curve``) of the accounts that have one: every
                                   per-second and M1-bar account; the tick designs' 1y (eight raw-tick timings) has
                                   none.
    The files are written into a temporary folder and checked there with ``compare_page.validate``; only then are this
    source's old files replaced, so the data folder never holds half an export. An incomplete comparison (a frozen
    finalist not compared, a window without every run it needs, a curve without its daily rows) raises ``ValueError``
    and writes nothing.
    """
    from . import compare_page as CP
    data = Path(COMPARE_DATA if data is None else data)
    cdir = Path(STUDY_DIR if compare_dir is None else compare_dir)
    keys = [k for k in DESIGNS if (cdir / f"compare_{k}.csv").exists()]
    if not keys:
        raise FileNotFoundError(f"no compare_<design>.csv in {cdir}: run `compare` first")
    if not finalists_frozen(cdir):
        raise CompareRefused(f"export: {cdir / 'FINALISTS.md'} with a matching sha256 does not exist (the roles and "
                             "the exam come from it)")
    frozen = read_finalists(cdir)
    study = CP.SOURCES[SID]["study"]
    series: List[dict] = []
    metrics: List[dict] = []
    curves: Dict[str, List[pd.DataFrame]] = {}
    problems: List[str] = []
    for key in keys:
        path = cdir / f"compare_{key}.csv"
        rows = read_rows(path)
        acc, miss = compare_accounts(key, rows)
        problems += [f"{key}: {m}" for m in miss]
        daily = read_daily(cdir / f"daily_compare_{key}.csv")
        daily = daily.assign(vid=daily["vid"].astype(str), window=daily["window"].astype(str))
        fins = frozen.get(key, [])
        vids = list(dict.fromkeys(rows.loc[rows["design"].astype(str) == key, "vid"].astype(str)))
        check_vids(vids)
        # PREREG 6: every finalist and its base (a `compare --vids` of some of them is not the design's comparison)
        problems += [f"{key}: {f}: a finalist in FINALISTS.md without comparison runs (`compare --design {key}`)"
                     for f in fins if f not in vids]
        order = [v for v in [BASE] + list(fins) if v in vids] + [v for v in vids if v != BASE and v not in fins]
        dev = _dev_scores(key, cdir, log)
        exam = exam_results(key, fins, cdir)
        src = CP._rel(path)
        for vid in order:
            s = _compare_series(key, vid, fins, dev, exam, study)
            series.append(s)
            score = dev[vid]["score"] if vid in dev else None
            for w in COMPARE_WINDOWS:
                a = acc.get((vid, w.name))
                if a is None:
                    continue                                   # listed in ``problems``
                row = _compare_metrics(s["series_id"], w, a, src, score)
                curve = None
                if a["mode"] != "ticks":
                    g = daily[(daily["vid"] == vid) & (daily["window"] == w.name)]
                    try:
                        curve = compare_curve(g, a["final"], a["start"], a["end"], a["wiped_at"] if a["wiped"] else "")
                    except ValueError as e:
                        problems.append(f"{key}: {vid} {w.name}: no daily curve in daily_compare_{key}.csv ({e})")
                        continue
                    curve.insert(0, "series_id", s["series_id"])
                    curves.setdefault(w.name, []).append(curve)
                metrics.append(CP.fill_from_curve(row, curve))
        log(f"  {key}: {len(order)} series ({', '.join(order)})")
    if problems:
        raise ValueError("export: the comparison runs are not complete, nothing was written (`compare` resumes):\n  "
                         + "\n  ".join(problems[:30]))
    se = CP._finish_series(series)
    me = CP._finish_metrics(metrics)
    cv = {w: pd.concat(v, ignore_index=True) for w, v in curves.items()}
    data.mkdir(parents=True, exist_ok=True)
    tmp = data / f".{SID}.tmp{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        CP.write_source(SID, se, me, cv, data=tmp, replace=True)
        rep = CP.validate(tmp)
        if rep["errors"]:
            raise ValueError("export: the files break the comparison page's contract (nothing replaced):\n  "
                             + "\n  ".join(rep["errors"][:30]))
        for old in data.glob(f"{SID}__*"):
            old.unlink()
        for new in sorted(tmp.iterdir()):
            os.replace(new, data / new.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log(f"{SID}: {len(se)} series, {len(me)} metrics rows, curves {', '.join(sorted(cv)) or '-'} -> {data}"
        + (f"; {len(rep['warnings'])} warnings" if rep["warnings"] else ""))
    return dict(series=se, metrics=me, curves=cv, warnings=rep["warnings"])


# ───────────────────────────── the command line ─────────────────────────────

def score_dev(key: str, out: Path = STUDY_DIR) -> pd.DataFrame:
    """The Development yardstick of every variant of a design that has all 23 quarters, with "better"."""
    rows = read_rows(dev_paths(key, out)[0])
    q = quarter_table(rows[rows["mode"].isin(["sec", "bars"])])
    full = q.groupby("vid")["window"].transform("size") == len(DEV_QUARTERS)
    Y = yardstick(q[full], n_quarters=len(DEV_QUARTERS))
    return mark_better(Y) if (Y["vid"] == BASE).any() else Y


def score_confirm(key: str, out: Path = STUDY_DIR, seeds: Sequence[int] = SEEDS) -> pd.DataFrame:
    """The confirmation's yardstick (the median of the eight timings per quarter); every variant in it must have all
    23 quarters under every timing."""
    rows = read_rows(Path(out) / f"confirm_{key}.csv")
    rows = rows[rows["mode"] == "ticks"]
    q = quarter_table(rows)
    if len(q) and not (q["runs"] == len(seeds)).all():
        raise ValueError(f"{key}: the confirmation is not complete (a quarter without its {len(seeds)} timings)")
    return mark_better(yardstick(q, n_quarters=len(DEV_QUARTERS)))


def choose(out: Path = STUDY_DIR, keys: Sequence[str] = tuple(DESIGNS)) -> Dict[str, dict]:
    """PREREG 5 per design: the candidates by Development score, the confirmation (tick designs) and the finalists.
    A design with no better variant has no finalist ("no filter improved it")."""
    res: Dict[str, dict] = {}
    for key in keys:
        Y = score_dev(key, out)
        cands = candidates(Y)
        Yc = None
        if cands and DESIGNS[key].engine == "ticks":
            Yc = score_confirm(key, out)
            missing = [v for v in [BASE] + cands if v not in set(Yc["vid"])]
            if missing:
                raise ValueError(f"{key}: {missing} have not been confirmed (run `confirm`)")
        res[key] = dict(dev=Y, confirm=Yc, candidates=cands, finalists=finalists(cands, Yc) if cands else [])
    return res


def freeze_choice(choice: Dict[str, dict], study_dir: Optional[Path] = None, note: str = "") -> Path:
    """``freeze`` with the scores of ``choose`` (Development and confirmed)."""
    scores = {}
    for key, c in choice.items():
        s = c["dev"][["vid", "score"]].copy()
        if c["confirm"] is not None:
            s = s.merge(c["confirm"][["vid", "score"]].rename(columns={"score": "confirmed_score"}), on="vid", how="left")
        scores[key] = s
    return freeze({k: c["finalists"] for k, c in choice.items()}, scores, study_dir, note)


def run_multiple_testing(out: Path = STUDY_DIR, keys: Sequence[str] = tuple(DESIGNS), B_: int = 5000) -> pd.DataFrame:
    """PREREG 7 for every design with Development results: ``multiple_testing.csv``."""
    res = []
    for key in keys:
        sink, daily = dev_paths(key, out)
        if not sink.exists():
            continue
        rows = read_rows(sink)
        fe = rows[rows["window"] == FIVE_Y.name].set_index("vid")["final_equity"].to_dict()
        res.append(multiple_testing(key, read_daily(daily), score_dev(key, out), fe, B_=B_))
    df = pd.concat(res, ignore_index=True) if res else pd.DataFrame()
    df.to_csv(Path(out) / "multiple_testing.csv", index=False)
    return df


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -B -m backtesting.research.bot_filters")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("identity", help="the tick designs' identity checks (base and always-allow, 5y + Development)")
    p.add_argument("--symbol", required=True, choices=SYMBOLS)
    p.add_argument("--work", required=True)
    p.add_argument("--no-full", action="store_true")
    p.add_argument("--workers", type=int, default=1)
    p = sub.add_parser("identity-turtle")
    p.add_argument("--work", required=True)
    p.add_argument("--cache", default=None)
    p = sub.add_parser("dev")
    p.add_argument("--design", required=True, choices=list(DESIGNS))
    p.add_argument("--stage", default="singles", choices=["singles", "pairs"])
    p.add_argument("--ports", action="store_true",
                   help="also the rows that read study 2's ports (RIB, MSD, HA, the Turtle's exits): only once those "
                        "ports are reconciled (PREREG 3)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", default=str(STUDY_DIR))
    p.add_argument("--cache", default=None)
    p = sub.add_parser("score")
    p.add_argument("--out", default=str(STUDY_DIR))
    p = sub.add_parser("confirm")
    p.add_argument("--design", required=True, choices=[k for k, d in DESIGNS.items() if d.engine == "ticks"])
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", default=str(STUDY_DIR))
    p = sub.add_parser("select", help="candidates, confirmation results and finalists per design (prints)")
    p.add_argument("--out", default=str(STUDY_DIR))
    p = sub.add_parser("freeze", help="write FINALISTS.md and its sha256 from `select` (once)")
    p.add_argument("--out", default=str(STUDY_DIR))
    p = sub.add_parser("mt", help="PREREG 7: multiple_testing.csv")
    p.add_argument("--out", default=str(STUDY_DIR))
    p = sub.add_parser("exam")
    p.add_argument("--design", required=True, choices=list(DESIGNS))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", default=str(STUDY_DIR))
    p.add_argument("--vids", nargs="+", required=True)
    p = sub.add_parser("compare", help="the comparison page's accounts of a design (8y, 5y, new per second; 1y on raw "
                                       "ticks; the Turtle on the M1-bar model), after the freeze, study 2's exam file "
                                       "and the design's exam")
    p.add_argument("--design", required=True, choices=list(DESIGNS))
    p.add_argument("--vids", nargs="+", default=None,
                   help="default: the design's finalists in FINALISTS.md (the base always runs)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", default=str(STUDY_DIR))
    p.add_argument("--cache", default=None)
    p = sub.add_parser("export", help="the comparison page's files of source bot_filters from every compare_<key>.csv")
    p.add_argument("--out", default=str(COMPARE_DATA), help="the comparison page's data folder")
    p.add_argument("--compare-dir", default=str(STUDY_DIR),
                   help="the folder of compare_<key>.csv, daily_compare_<key>.csv, FINALISTS.md and the exam")
    a = ap.parse_args(argv)
    if a.cmd == "identity":
        identity_ticks(a.symbol, Path(a.work), full=not a.no_full, workers=a.workers)
    elif a.cmd == "identity-turtle":
        identity_turtle(Path(a.work), cache_dir=Path(a.cache) if a.cache else None)
    elif a.cmd == "dev":
        if a.stage == "singles":
            run_dev(a.design, stage1_vids(a.design, ports=a.ports), Path(a.out), a.workers,
                    cache_dir=Path(a.cache) if a.cache else None)
        else:
            Y = score_dev(a.design, Path(a.out))
            pairs = stage2_pairs(Y)
            print(f"{a.design}: stage-2 pairs {pairs}")
            if pairs:
                run_dev(a.design, pairs, Path(a.out), a.workers, cache_dir=Path(a.cache) if a.cache else None)
    elif a.cmd == "score":
        for key in DESIGNS:
            if dev_paths(key, Path(a.out))[0].exists():
                Y = score_dev(key, Path(a.out))
                print(f"{key}: {len(Y)} variants scored; candidates {candidates(Y) if (Y['vid'] == BASE).any() else []}")
    elif a.cmd == "confirm":
        Y = score_dev(a.design, Path(a.out))
        run_confirm(a.design, candidates(Y), Path(a.out), a.workers)
    elif a.cmd in ("select", "freeze"):
        keys = [k for k in DESIGNS if dev_paths(k, Path(a.out))[0].exists()]
        ch = choose(Path(a.out), keys)
        for k, c in ch.items():
            print(f"{k}: candidates {c['candidates']}, finalists {c['finalists'] or 'none (no filter improved it)'}")
        if a.cmd == "freeze":
            if set(keys) != set(DESIGNS):
                raise SystemExit(f"not every design has Development results: {sorted(set(DESIGNS) - set(keys))}")
            print(freeze_choice(ch, Path(a.out)))
    elif a.cmd == "mt":
        print(run_multiple_testing(Path(a.out)).to_string())
    elif a.cmd == "exam":
        run_exam(a.design, a.vids, Path(a.out), a.workers)
    elif a.cmd == "compare":
        try:
            run_compare(a.design, a.vids, Path(a.out), a.workers, cache_dir=Path(a.cache) if a.cache else None)
        except (SealedWindowError, CompareRefused) as e:
            raise SystemExit(f"compare refused: {e}")
    elif a.cmd == "export":
        try:
            export_compare(Path(a.out), Path(a.compare_dir))
        except (CompareRefused, FileNotFoundError) as e:
            raise SystemExit(f"export refused: {e}")


if __name__ == "__main__":
    main()
