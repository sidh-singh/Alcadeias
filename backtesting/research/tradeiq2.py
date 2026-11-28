"""
TradeIQ's "9 best TradingView indicators going into 2027" on gold and BTC (study 2): the driver.

    python -B -m backtesting.research.tradeiq2 grid     [--study-dir DIR]      # PREREG 6: the variants and their counts
    python -B -m backtesting.research.tradeiq2 run      [--study-dir DIR] [--symbols ..] [--modules ..] [--workers 2]
    python -B -m backtesting.research.tradeiq2 select   [--study-dir DIR]      # PREREG 7: qualifiers, champions, finalists
    python -B -m backtesting.research.tradeiq2 freeze   [--study-dir DIR]      # PREREG 7: FINALISTS.md and its sha256, once
    python -B -m backtesting.research.tradeiq2 exam     [--study-dir DIR] [--workers 2] [--no-base-rate] [--no-recheck]
                                                         [--allow-code-change]   # PREREG 7: the two exams
    python -B -m backtesting.research.tradeiq2 accounts [--study-dir DIR] [--compare-dir DIR] [--workers 2]
                                                         [--allow-code-change] [--no-references]
    python -B -m backtesting.research.tradeiq2 claims   [--study-dir DIR] [--partial]     # PREREG 8: the video's claims
    python -B -m backtesting.research.tradeiq2 report   [--study-dir DIR]      # the tables of RESULTS.md

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (frozen), read with ``DEVIATIONS.md``. The data, the guard and
the execution are ``tradeiq2_market.py`` (M) and ``tradeiq2_filters.py``; the rules are the nine rule modules
``tradeiq2_rules_<key>.py`` (key: ribbon, msd, wyckoff, swing, orb, session, patterns, ha, coil), each with
``variants(symbol) -> [M.Variant]`` and ``build(variant, ctx) -> M.Exec``. They are found by import: the driver works
with any subset that exists (``grid`` and ``run`` say which are missing; ``freeze`` needs all nine). Study 1's driver
(``tradeiq.py``) is imported for its helpers (the bootstrap, the deflated Sharpe, the exam rule, the markdown and the
blob ids), never edited.

THE HOLD-OUT. ``run`` loads every market only up to 2024-07-01 00:00 UTC (``M.load(symbol, end=M.HOLDOUT_START)``,
frozen or not) and scores Development, Validation and the two together; ``select`` writes ``CANDIDATES.md`` and
``FINALISTS.draft.md``, who WOULD be the champions and finalists, never ``FINALISTS.md``. ``freeze`` checks the code,
the data and each would-be champion's Development row on a market cut at the Development end (a look-ahead check
on open data), then writes ``FINALISTS.md`` and, last, ``FINALISTS.md.sha256`` once (``M.frozen()``'s format) and
refuses a second time. ``exam`` and ``accounts`` refuse until ``M.frozen()`` is True for the study folder the guard
reads (and the guard refuses anyway), refuse result code other than FINALISTS.md's (unless ``--allow-code-change``,
which is recorded) and refuse inputs whose sha256 FINALISTS.md does not record; ``run`` and ``select`` refuse once
FINALISTS.md exists. The test-only options (``--rules``, a count table, a loader, a partial freeze) are refused on
the study folder itself (``REAL_STUDY_DIR``).

IDENTITY OF A RESULT. Every per-variant part is stamped with the code's blob ids as they were when the command
started (a snapshot; the files are hashed again before and after each module's batch and the run stops if any
changed), the versions of Python, numpy, pandas and numba, and the data served (``data_identity``: the M1 arrays'
sha1, their span and count, and for BTC the Binance klines' checksums), so a resumed run recomputes whatever another
code, environment or data made.

Outputs (the study folder; study 1's names and layouts where they exist)
------------------------------------------------------------------------
``grid``:     grid.csv (vid, module, symbol, tf, script, family, group, eligible, info, params)
``run``:      results_dev_val.csv (one row per variant and window dev / val / devval: every score of PREREG 7 at x1.0,
              ``_x15`` at x1.5, with the R statistics and the harness's counts), quarters_dev_val.csv,
              trades_dev_val.csv.gz, weekly_dev_val.csv.gz (dev and val, both costs), buy_and_hold.csv, run_info.csv
              (per symbol and module: the data served, the variants done, the code's git blob ids). Each variant is
              computed into ``run_parts/`` (written atomically; a ``.gitignore`` keeps it out of git), so a stopped run
              resumes where it stopped and the CSVs are assembled in grid order (the same bytes for any --workers).
``select``:   qualification.csv, champions.csv, multiple_testing.csv, CANDIDATES.md, FINALISTS.draft.md
``freeze``:   FINALISTS.md, FINALISTS.md.sha256
``exam``:     exam.csv (every champion's exam rows and verdict), exam_full.csv, exam_trades.csv.gz,
              exam_buy_and_hold.csv, exam_info.csv, exam_checks.csv; then every variant (the base rate, resumable):
              results_holdout.csv, results_early.csv, trades_holdout.csv.gz, trades_early.csv.gz, base_rate.csv,
              and (the look-ahead check of every variant, as study 1's) results_recheck_dev_val.csv;
              multiple_testing.csv; EXAM.md
``accounts``: curves_full.csv, curves_holdout.csv, curves_early.csv, curves_summary.csv (the champions, finalists and
              each family's best row; next to them buy-and-hold of 0.01 lot, study 1's six finalists run with study
              1's code, and the bots' designs as study 1 rebuilt them on the same spans) and the comparison page's
              files (COMPARE DATA CONTRACT v1, source tradeiq_2027): <compare>/tradeiq_2027__series.csv, __metrics.csv,
              __curves_<window>.csv.gz
``claims``:   claims.csv (Development and Validation: the verdicts), claims_holdout.csv (once the exam's results
              exist: information), CLAIMS.md. The claims are a registry keyed by PREREG 8's numbers (``CLAIMS``); a
              claim that needs a rule module's function looks it up by the names in ``EXTRAS``.
``report``:   counts.csv, vs_study1_msd.csv (+ _summary), vs_f0.csv (+ _summary, vs_f0_unmatched.csv),
              combos.csv (+ _summary, combos_unmatched.csv: PREREG 6.11's combinations against the scripts alone),
              vs_study1_best.csv, RESULTS_TABLES.md
``--rules``:  tests only: a module whose MODULES / COUNTS / LOADER replace the rule modules, the plan's counts and the
              markets (tests/tradeiq2_stub_rules.py); refused without ``--study-dir`` and on the study folder.

What the plan leaves open is read as ``READINGS`` lists (to be logged in DEVIATIONS.md before the run).
"""

from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import importlib
import importlib.util
import io
import json
import math
import multiprocessing as mp
import os
import pickle
import platform
import queue
import resource
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from . import external as X
from . import tradeiq as T1
from . import tradeiq_market as TM
from . import tradeiq2_market as M

SID = "tradeiq_2027"                                     # the comparison page's source id
STUDY_NAME = "TradeIQ video 2 - 9 indicators for 2027"
# the study folder itself (never patched by the tests, unlike M.STUDY_DIR): the test-only options are refused there
REAL_STUDY_DIR = REPO_ROOT / "backtest_results" / "tradeiq_2027"
STUDY1_DIR = REPO_ROOT / "backtest_results" / "tradeiq_rsi"
COMPARE_DIR = REPO_ROOT / "backtest_results" / "compare" / "data"
RULES_PREFIX = "backtesting.research.tradeiq2_rules_"
SYMBOLS = M.SYMBOLS                                      # the owner's markets: champions, finalists, the exam
CLAIM_SYMBOLS = M.CLAIM_SYMBOLS                          # PREREG 8: information only
ALL_SYMBOLS = SYMBOLS + CLAIM_SYMBOLS
RUN_WINDOWS = M.RUN_WINDOWS                              # dev, val, devval
COSTS = M.COSTS                                          # 1.0, 1.5
TFS = ("M5", "M15", "1H", "4H", "1D")
NAME = {"XAUUSDm": "Gold (XAUUSDm)", "BTCUSDm": "BTC (BTCUSDm)", "USTECm": "Nasdaq (USTECm)",
        "EURUSDm": "EURUSD (EURUSDm)", "GBPUSDm": "GBPUSD (GBPUSDm)"}

# the nine rule modules, in the order of PREREG 6 (the grid's order within a symbol)
MODULE_KEYS = ("ribbon", "msd", "wyckoff", "swing", "orb", "session", "patterns", "ha", "coil")
SECTION = {"ribbon": "6.1 and 6.10", "msd": "6.2", "wyckoff": "6.3", "swing": "6.4", "orb": "6.5", "session": "6.6",
           "patterns": "6.7", "ha": "6.8", "coil": "6.9"}
# PREREG 7's families, in its table's order, and the module each belongs to
FAMILIES = ("RIB", "ALMA-X", "MSD-ALONE", "MSD-FILTER", "BOS", "WY", "WY-DERIVED", "SP", "ORB", "SH", "HP-HARMONIC",
            "HP-CHART", "HA-ENTRY", "HA-MANAGED", "COIL", "STK")
MODULE_FAMILIES = {"ribbon": ("RIB", "ALMA-X", "STK"), "msd": ("MSD-ALONE", "MSD-FILTER", "BOS"),
                   "wyckoff": ("WY", "WY-DERIVED"), "swing": ("SP",), "orb": ("ORB",), "session": ("SH",),
                   "patterns": ("HP-HARMONIC", "HP-CHART"), "ha": ("HA-ENTRY", "HA-MANAGED"), "coil": ("COIL",)}
# PREREG 7, the finalists: "at most one per script. RIB and ALMA-X count as one script; so do MSD-ALONE, MSD-FILTER
# and BOS; WY and WY-DERIVED; HP-HARMONIC and HP-CHART; HA-ENTRY and HA-MANAGED. COIL and STK ... count as one each."
GROUP = {"RIB": "RIB", "ALMA-X": "RIB", "MSD-ALONE": "MSD", "MSD-FILTER": "MSD", "BOS": "MSD", "WY": "WY",
         "WY-DERIVED": "WY", "SP": "SP", "ORB": "ORB", "SH": "SH", "HP-HARMONIC": "HP", "HP-CHART": "HP",
         "HA-ENTRY": "HA", "HA-MANAGED": "HA", "COIL": "COIL", "STK": "STK"}
CLAIM_MODULES = ("session",)            # PREREG 8 claim 10: the only rows on USTECm, EURUSDm and GBPUSDm
WY_FAMILIES = ("WY", "WY-DERIVED")
# rows that look ahead by design (PREREG 6.7: HP-DRAWN, "the plan as drawn back at D, with look-ahead"): information
# only; left out of the look-ahead checks and of the comparison page
LOOKAHEAD_TOKENS = ("HP-DRAWN",)
N_FINALISTS = 3                         # PREREG 7: per symbol, the three champions with the highest D+V P/DD
MIN_PDD = 1.0                           # PREREG 7, rule 3 (inclusive)
MIN_POS_Q = 0.5                         # PREREG 7, rule 3: "at least 50% of the quarters positive" (inclusive)
INSUFFICIENT_EVENTS = 15                # PREREG 6.3: below 15 Development trades, "insufficient events"
EXAM_MIN_PDD = T1.EXAM_MIN_PDD          # PREREG 7, the exam: net > 0 at x1.0 and P/DD >= 0.5

# ───────────────────────────── PREREG 6's counts (the grid check) ─────────────────────────────
#
# (module, family, eligible, gold rows, BTC rows, where the number is in the PREREG). ``None``: the PREREG gives no
# number for those rows (they are counted and printed, not checked). A (module, symbol, family, eligible) the grid
# has and this table does not is an error, so a family label the plan does not know cannot slip through.
COUNT_TABLE: Tuple[Tuple[str, str, bool, Optional[int], Optional[int], str], ...] = (
    ("ribbon", "RIB", True, 136, 136, "6.1 Size: 2 sides x 4 exits x 17 filter slots = 136"),
    ("ribbon", "RIB", False, 3, 3, "6.1 Size: 3 RIB-LIT rows (sensitivity; not eligible)"),
    ("ribbon", "ALMA-X", True, 6, 6, "6.1 Size: 6 ALMA-X rows (control; LS and LO x 3 timeframes)"),
    ("ribbon", "STK", True, 18, 18, "6.10 Size: 3 x 2 x 3 = 18"),
    ("msd", "MSD-ALONE", True, 18, 18, "6.2 Size: 18 alone (A1-A3 x S0, S1 x 3 timeframes)"),
    ("msd", "MSD-FILTER", True, 120, 120, "6.2 Size: 60 MSD-F4 + 60 MSD-F6"),
    ("msd", "BOS", True, 12, 12, "6.2 Size: 12 BOS-trend"),
    ("wyckoff", "WY", True, 36, 36, "6.3 Size: 36 (STD, STD-L, AGG x X-S, X-S3 x F0, F2 x 3 timeframes)"),
    ("wyckoff", "WY-DERIVED", True, 18, 18, "6.3 Size: '36 + 18 = 54 eligible rows' (the text of WY-CL / WY-SP gives "
                                            "2 rules x F0, F2 x 3 timeframes = 12; 18 is WY-CL's 6 plus WY-SP's "
                                            "confirmed and provisional excursions, or its 3R and X-S exits, 12: the "
                                            "lead's reading, to be logged in DEVIATIONS.md)"),
    ("wyckoff", "WY", False, 0, 3, "6.3 Size: 3 control rows on BTC (Exness tick volume; not eligible)"),
    ("swing", "SP", True, 24, 24, "6.4 Size: 3 x 4 x 2 = 24 eligible rows"),
    ("swing", "SP", False, 12, 12, "6.4 Size: 12 placebo rows (not eligible)"),
    ("orb", "ORB", True, 72, 54, "6.5 Size: 50 + 10 LO (gold) + 8 ORB-CX (gold) + 4 TIGHT"),
    ("orb", "ORB", False, 10, 12, "6.5 Controls (not eligible): LV only O1-O4 x 2 timeframes (8), the literal UTC-5 "
                                  "clock O1 x 2 (2), BTC on all 7 days O1 x 2 (2, BTC)"),
    ("session", "SH", True, 116, 116, "6.6 Size: 116 rows per symbol"),
    ("session", "SH", False, None, None, "6.6: the Monday variant with Friday's levels (information only; no number)"),
    ("patterns", "HP-HARMONIC", True, 30, 30, "6.7 Size: 27 HF + 3 HC"),
    ("patterns", "HP-CHART", True, 18, 18, "6.7 Size: 12 CF + 4 CS + 2 CC"),
    ("patterns", "HP-HARMONIC", False, None, None, "6.7: HP-DRAWN (information only; no number)"),
    ("patterns", "HP-CHART", False, None, None, "6.7: HP-DRAWN (information only; no number)"),
    ("ha", "HA-MANAGED", True, 54, 54, "6.8 Size: 9 bases x 6 = 54"),
    ("ha", "HA-ENTRY", True, 24, 24, "6.8: 24 rows per symbol (H1, H2 x LS, LO x F0, F2 x 3 timeframes)"),
    ("coil", "COIL", True, 36, 36, "6.9 Size: 30 COIL-RIB + 6 COIL-MA / COIL-0"),
)
# PREREG 7 "Size: about 1,460 eligible variants (738 on gold, 720 on BTC)": the table's eligible rows sum to these.
PLAN_ELIGIBLE = {M.GOLD: 738, M.BTC: 720}


@dataclass(frozen=True)
class Count:
    """One line of the grid check: the rows of one module, symbol, family and eligibility (None: not checked)."""
    module: str
    symbol: str
    family: str
    eligible: bool
    n: Optional[int]
    where: str


def counts_of(table=COUNT_TABLE) -> Tuple[Count, ...]:
    out = []
    for module, family, eligible, gold, btc, where in table:
        out += [Count(module, M.GOLD, family, eligible, gold, where), Count(module, M.BTC, family, eligible, btc, where)]
    for s in CLAIM_SYMBOLS:
        out.append(Count("session", s, "SH", False, None, "PREREG 8 claim 10: the claim-check rows (information only; "
                                                          "no number)"))
    return tuple(out)


PREREG_COUNTS = counts_of()

# ───────────────────────────── the modules' extras: the names looked up ─────────────────────────────
#
# What the driver asks of a rule module beyond variants() and build(). Each entry: (module key, the attribute names
# tried in order, what it must be). A missing optional extra falls back as stated; a missing required one fails with
# this text, so the lead wires the real names here (or in a small adapter) in a few lines. Every claim function
# (claim5 .. claim16, pooled_test) takes a tradeiq2.Evidence and keeps to CLAIM_RULE (below): it counts only inside
# ev.span / ev.in_window / ev.years, and a row carrying a 'year', 'start' or 'end' outside them is refused.
EXTRAS: Dict[str, Tuple[str, Tuple[str, ...], str]] = {
    "claim_variants": ("session", ("claim_variants",),
                       "claim_variants(symbol) -> [M.Variant]: the claim-check rows of PREREG 8 claim 10 on USTECm, "
                       "EURUSDm, GBPUSDm (eligible=False). Optional: without it variants(symbol) is called for them."),
    "study1_ids": ("msd", ("study1_ids", "study1_pairs", "study1_base_ids", "base_ids"),
                   "study1_ids(variant) -> {study-1 filter: study-1 id} or [study-1 ids]: the F0 / F1 / F2 rows of "
                   "study 1's grid.csv an MSD-F4 / MSD-F6 row is paired with (PREREG 6.2). Optional: without it the "
                   "pairs are matched by the PREREG's names in the id or the params (indicator, R1 / R2, S0 / S1)."),
    "ha_base": ("ha", ("base_of", "base_id", "base_vid"),
                "base_of(variant) -> the id of the base an HA-MANAGED row is paired with (PREREG 6.8: a row of this "
                "grid, or a study-1 finalist's id). Optional: without it params['base'] / ['base_id'] / ['base_vid']."),
    "claim5": ("ha", ("claim5", "claim_5", "calibration"),
               "claim5(ev) -> rows: the panel's 'reached age A, then 5+ more' rates computed before each year against "
               "that year (PREREG 8 claim 5)."),
    "claim6": ("orb", ("claim6", "claim_6"),
               "claim6(ev) -> rows: P(the 16:00 close is beyond the range on the side of the first breakout)."),
    "claim7": ("orb", ("claim7", "claim_7"),
               "claim7(ev) -> rows: HV against LV, same rule. Optional: without it the results' HV / LV pairs."),
    "claim8": ("orb", ("claim8", "claim_8"),
               "claim8(ev) -> rows: the dashboard's unconditional hit rates against the rates after a breakout."),
    "claim9": ("orb", ("claim9", "claim_9"),
               "claim9(ev) -> rows: the literal UTC-5 clock against New York time (O1)."),
    "claim11": ("swing", ("claim11", "claim_11"),
                "claim11(ev) -> rows: how often the forming POC is touched before the leg ends, against the 50% "
                "level."),
    "claim12": ("swing", ("claim12", "claim_12"),
                "claim12(ev) -> rows: the next leg's size after up legs with negative against positive delta."),
    "claim14": ("msd", ("claim14", "claim_14"),
                "claim14(ev) -> rows: the share of chart closes inside a higher-timeframe bar where the forming-bar "
                "score differs from the closed one."),
    "claim15": ("wyckoff", ("pooled_test", "claim15", "claim_15"),
                "pooled_test(ev) -> rows: PREREG 6.3's primary pooled test (WY-STD x X-S x S-W x F0, both symbols, "
                "three timeframes, D+V) in R and in dollars against 1,000 matched placebo sets, with its p-value."),
    "claim16": ("wyckoff", ("claim16", "claim_16"),
                "claim16(ev) -> rows: the stop distance in ATR at Standard against Aggressive and LPS entries, and "
                "the R outcome per entry type."),
}
# per module, optional: describe(variant) -> the rule row in words (FINALISTS.md; flattened to one line, backticks
# replaced); warm(ctx, variants) -> None (shared indicator arrays computed in the parent before the workers fork, so
# they share them copy-on-write)
DESCRIBE_NAMES = ("describe", "rule_text")
WARM_NAMES = ("warm",)
# What every claim function (claim5 .. claim16, pooled_test) must keep to: it counts only inside the evidence's two
# windows (Development and Validation before the freeze; the hold-out after it): ev.span(window, symbol),
# ev.in_window(symbol, tf, window) (a mask over ctx.bars(tf)), ev.years(symbol) (the calendar years clipped to the
# windows). ev.context(symbol) holds the history from the data start for the indicators' warm-up only: no outcome may
# be counted on a bar outside the windows (gold's 2017-2018 are the sealed Early window). A row may carry 'year',
# 'start' or 'end'; a row outside the windows is refused (ClaimWindowError).
CLAIM_RULE = ("count only inside the evidence windows (ev.span, ev.in_window, ev.years); a row with a 'year', 'start' "
              "or 'end' outside them is refused")


# where the plan is silent, this code reads it so (each line names what it can move). Every line is to be logged in
# DEVIATIONS.md before `run` (the PREREG's header: before the result it could affect exists).
READINGS = (
    # the grid
    "grid counts are checked per (module, symbol, family, eligible); RIB-LIT, the ORB controls, SP's placebo, the BTC "
    "Wyckoff control, HP-DRAWN, SH's Monday variant and the claim-market rows keep their script's family with "
    "eligible=False; rows the plan does not number are counted, not checked",
    "ORB controls: LV x O1-O4 x 2 timeframes, the UTC-5 clock x O1 x 2, BTC 7 days x O1 x 2; TIGHT on both symbols, "
    "ORB-CX and LO gold only (738 - 720 = 18)",
    "WY-DERIVED = 18 rows as PREREG 6.3's size line says (its text gives 12): WY-CL's 6 plus WY-SP's 12, either as "
    "confirmed and provisional excursions or as the 3R and X-S exits; the lead picks one, the wyckoff module emits "
    "it, and the count check stops on a module that gives 12",
    "only the session module is asked for USTECm / EURUSDm / GBPUSDm (claim 10); every row there is eligible=False; "
    "their Development starts as PREREG 3 says",
    "ids: 'symbol|tf|...' without white space or backticks; the timeframe one of M5, M15, 1H, 4H, 1D; the family one "
    "of its module's PREREG 7 families",
    # the selection
    "qualification: the minimum trades are PREREG 5's, counted at x1.0; rule 3 is inclusive at P/DD 1.0 and 50% "
    "positive quarters; a P/DD that does not exist (no drawdown) fails, as in study 1; not-eligible rows get q1-q4 "
    "but never qualify",
    "PREREG 6.3's 'insufficient events' (fewer than 15 Development trades on a WY / WY-DERIVED row) is a column and a "
    "verdict word; it changes no qualification",
    "the finalists' script groups come from the family (PREREG 7's list), not from Variant.script; ties between "
    "champions as between qualifiers: D+V P/DD, then Development's, then the id; a missing P/DD sorts last",
    "multiple testing: as PREREG 7 says, N = every variant run on the symbol and SPA / the Reality Check over all of "
    "them (Development weekly P/L, x1.0, study 1's code); the same over the eligible variants only, for information "
    "(HP-DRAWN looks ahead and the controls are no trial of the selection); in select and again in exam",
    # the freeze and the exam
    "the exam: every champion takes it (PREREG 7 'A champion passes exam 1 when'), the finalists among them; "
    "FINALISTS.md lists every champion with its role",
    "run loads every market to 2024-07-01 even after the freeze, and refuses once FINALISTS.md exists, as select does",
    "the look-ahead checks: freeze recomputes each would-be champion's Development row on a market cut at the "
    "Development end and requires results_dev_val.csv's text; the exam recomputes every champion's D, V and D+V, and "
    "(unless --no-recheck) every variant's, on the data to the data end and requires the same text; HP-DRAWN (it "
    "looks ahead by design) is left out; a champion that fails gets the verdict 'void (look-ahead)'. A check that "
    "cuts the data at a window's end cannot see a rule that peeks at most one bar ahead (the decision at the last bar "
    "fills after the window): such rules are the ports' and the rule modules' own tests' to catch",
    "the code a result depends on: the harness, study 1's harness, config.py, store.py, the ports and the rule "
    "module (and Python, numpy, pandas and numba); freeze refuses when any of these or the data served differ from "
    "run_info.csv; exam and accounts refuse result code other than FINALISTS.md's unless --allow-code-change (then the "
    "files are recorded in exam_info.csv and EXAM.md) and refuse inputs whose sha256 FINALISTS.md does not record; "
    "the driver's, silver.py's and final10.py's blobs are recorded, not required",
    "the exam of record: exam.csv is never overwritten by a run with other result code (exam_info.csv)",
    "the base rate: per symbol and window (gold also both), the share passing among all rows, the eligible rows, "
    "qualifiers, champions, finalists and the not-eligible rows, with buy-and-hold (every symbol) and the claim-check "
    "rows (information); results_full.csv is not written for every variant (PREREG 3 has no 'full' window; the "
    "champions' full rows are exam_full.csv)",
    "buy-and-hold beside the exam: study 1's DEVIATIONS 28 (P/DD above buy-and-hold's) and its exposure-matched net "
    "(time in the market x buy-and-hold's net)",
    # the accounts and the page
    "accounts: the champions and each family's best row (its champion, else its eligible row first in PREREG 7's "
    "order) over full, hold-out and (gold) Early at x1.0 and x1.5; every gold / BTC variant over 5y, 1y (both) and "
    "8y, new (gold) at x1.0; next to them buy-and-hold of 0.01 lot and study 1's six finalists (study 1's code on this "
    "study's market) over full, hold-out and Early, and the bots' designs as study 1 rebuilt them from FINAL10's 8y "
    "trades on full and hold-out (the same spans; they cannot be rebuilt on 2017-2018: FINAL10's runs start "
    "2018-11-13)",
    "the account: M.account_curve with FINAL10's unit rule; its USD drawdown on the M1 marks with the trades weighted "
    "by their units; trades, win rate and profit factor per position (legs combined, lanes separate); weekly Sharpe "
    "on the weekly $ P/L (weeks from Saturday 00:00 UTC, partial first and last included, the page's definition); "
    "positive quarters and the worst quarter on the equity at calendar-quarter starts",
    "the page's curve: the opening row the day before the window at $2,000, then per UTC day with an M1 bar the "
    "equity at that day's last close mark; a wiped account's curve stops on the day it was wiped",
    "the page's fields: kind 'rule'; role finalist / champion / qualified / variant; eligible = qualifies (study 1's "
    "meaning on the page); exam = exam 1's pass or fail; label = the id without the symbol; rows that look ahead "
    "(HP-DRAWN) and the claim markets are not exported",
    "partial exits (legs): 'live needs at least 0.02 lot per unit (PREREG 4)' wherever such a row is listed",
    # the comparisons and the claims
    "comparisons pair rows by the PREREG's names as '|'-separated id tokens or param values (XP -> X0, XBE -> X0, F1 "
    "/ F2 / F2-4H / F2-1D / F3 / FR / FS / FD / HV / HV+F2-4H -> F0, LO -> F0 on SP and ORB only, E1 -> E2 / E3, HV "
    "-> LV, O4 -> O2 / O3, a grade -> no grade); a filtered row without an F0 row is paired with its id without the "
    "filter token (SH's F2 / F3 rows with their K2 x E1 row and the script's 1H EMA200)",
    "PREREG 6.11's combinations against the scripts alone: TIGHT -> the same ORB rule with F0, ORB-CX -> the New York "
    "range, STK -> RIB with the same side, X0, F0, WY-DERIVED -> WY-STD x X-S with the same filter; 'helps / does not "
    "help / mixed' is study 1's DEVIATIONS 30",
    "claims: 'most' = more than half, a win = strictly more net at x1.0 (study 1's DEVIATIONS 31); claim 1 'ignores "
    "the noise' = fewer trades than ALMA-X in every pair and more net in most; claim 10's 'nothing held up' = at "
    "most half of the SH rows with net above 0; claim 13's removed trades = the F0 base's trades whose (entry time, "
    "side) the filtered row does not take (a delayed re-entry counts as removed), with their number and net; claim "
    "15 reports events per year with no verdict (the plan gives no number for 'rare'); claim 17 = the share of the "
    "script's WY rows with net above 0 on 4H and 1D against 1H, with the entries per timeframe; claim 18 also "
    "compares the drawn chart patterns with HP-CC / HP-CF",
)


class GridError(ValueError):
    """The rule modules' variants are not PREREG 6's grid (ids, fields or counts)."""


class MissingExtra(LookupError):
    """A claim needs a module function the driver cannot find (see EXTRAS)."""


class StudyFolderError(ValueError):
    """A test-only option (--rules, a count table, a loader, a partial freeze) on the study folder itself."""


class CodeChangedError(RuntimeError):
    """The result code is not the code FINALISTS.md records (exam, accounts) or the code changed during a run."""


class ClaimWindowError(M.HoldOutError):
    """A claim function returned a row counted outside the evidence's windows."""


def _attr(mod, names: Sequence[str]):
    for n in names:
        f = getattr(mod, n, None)
        if f is not None:
            return f
    return None


def extra(modules: Mapping[str, object], name: str, required: bool = True):
    """The module function EXTRAS[name] names, or None (optional), or MissingExtra naming what was expected."""
    key, names, what = EXTRAS[name]
    mod = modules.get(key)
    f = None if mod is None else _attr(mod, names)
    if f is None and required:
        where = f"tradeiq2_rules_{key}" if mod is not None else f"tradeiq2_rules_{key} (not found)"
        raise MissingExtra(f"{where} has none of {', '.join(names)}: expected {what}")
    return f


# ───────────────────────────── the rule modules and the grid (PREREG 6) ─────────────────────────────

def find_modules(keys: Sequence[str] = MODULE_KEYS, prefix: str = RULES_PREFIX) -> Dict[str, ModuleType]:
    """The rule modules that exist (``backtesting.research.tradeiq2_rules_<key>``), imported, by key. A module that
    exists but fails to import raises."""
    out = {}
    for k in keys:
        name = prefix + k
        try:
            spec = importlib.util.find_spec(name)
        except ModuleNotFoundError:
            spec = None
        if spec is not None:
            out[k] = importlib.import_module(name)
    return out


def load_rules(spec: str) -> Tuple[Dict[str, object], Optional[Tuple[Count, ...]], Optional[Callable]]:
    """``--rules`` (tests only): a dotted module name or a .py file whose ``MODULES`` maps keys to rule modules; its
    optional ``COUNTS`` (Count rows) replaces the plan's table and its optional ``LOADER(symbol, end)`` the markets."""
    if spec.endswith(".py"):
        path = Path(spec).resolve()
        mod = sys.modules.get(path.stem)
        if mod is None or Path(getattr(mod, "__file__", "")).resolve() != path:
            s = importlib.util.spec_from_file_location(path.stem, path)
            mod = importlib.util.module_from_spec(s)
            sys.modules[path.stem] = mod
            s.loader.exec_module(mod)
    else:
        mod = importlib.import_module(spec)
    counts = getattr(mod, "COUNTS", None)
    return dict(getattr(mod, "MODULES")), (tuple(counts) if counts is not None else None), getattr(mod, "LOADER", None)


def _require_api(key: str, mod) -> None:
    if key not in MODULE_KEYS:
        raise GridError(f"{key}: not a rule module of this study ({', '.join(MODULE_KEYS)})")
    for n in ("variants", "build"):
        if not callable(getattr(mod, n, None)):
            raise GridError(f"rule module {key}: no {n}() (the contract: variants(symbol) -> [Variant], "
                            "build(variant, ctx) -> Exec)")


def _variant_problems(key: str, symbol: str, v) -> List[str]:
    where = f"{key}.variants({symbol!r})"
    if not isinstance(v, M.Variant):
        return [f"{where}: {v!r} is not a tradeiq2_market.Variant"]
    p = []
    if v.symbol != symbol:
        p.append(f"{where}: {v.id} has symbol {v.symbol}")
    if v.tf not in TFS:
        p.append(f"{where}: {v.id} has timeframe {v.tf!r} (one of {', '.join(TFS)})")
    if not isinstance(v.id, str) or not v.id.startswith(f"{v.symbol}|{v.tf}|"):
        p.append(f"{where}: {v.id!r} does not start with symbol|tf|")
    elif any(ch.isspace() for ch in v.id) or "`" in v.id:
        p.append(f"{where}: {v.id!r} holds white space or a backtick")
    if v.family not in MODULE_FAMILIES[key]:
        p.append(f"{where}: {v.id} has family {v.family!r}, not one of {key}'s ({', '.join(MODULE_FAMILIES[key])})")
    if not isinstance(v.eligible, (bool, np.bool_)):
        p.append(f"{where}: {v.id} has eligible={v.eligible!r} (True / False)")
    if symbol in CLAIM_SYMBOLS and bool(v.eligible):
        p.append(f"{where}: {v.id} is eligible, but the claim markets are information only (PREREG 8)")
    return p


def collect(modules: Mapping[str, object]) -> Tuple[List[Tuple[str, M.Variant]], List[str]]:
    """(module key, variant) for every symbol (gold, BTC, then the claim markets for the session module) and module
    present, in the grid's order; and every problem found (fields, duplicate ids)."""
    pairs, problems, seen = [], [], {}
    for symbol in ALL_SYMBOLS:
        for key in MODULE_KEYS:
            mod = modules.get(key)
            if mod is None or (symbol in CLAIM_SYMBOLS and key not in CLAIM_MODULES):
                continue
            fn = _attr(mod, EXTRAS["claim_variants"][1]) if symbol in CLAIM_SYMBOLS else None
            for v in list((fn or mod.variants)(symbol)):
                bad = _variant_problems(key, symbol, v)
                if bad:
                    problems += bad
                    continue
                if v.id in seen:
                    problems.append(f"duplicate id {v.id!r}: {seen[v.id]} and {key}.variants({symbol!r})")
                    continue
                seen[v.id] = f"{key}.variants({symbol!r})"
                pairs.append((key, v))
    return pairs, problems


GRID_COLUMNS = ("vid", "module", "symbol", "tf", "script", "family", "group", "eligible", "info", "params")


def grid_frame(pairs: Sequence[Tuple[str, M.Variant]]) -> pd.DataFrame:
    rows = []
    for key, v in pairs:
        d = v.ident()
        rows.append({"vid": d["vid"], "module": key, "symbol": d["symbol"], "tf": d["tf"], "script": d["script"],
                     "family": d["family"], "group": GROUP[d["family"]], "eligible": bool(d["eligible"]),
                     "info": d["info"], "params": d["params"]})
    return pd.DataFrame(rows, columns=list(GRID_COLUMNS))


def count_report(grid: pd.DataFrame, counts: Sequence[Count], present: Iterable[str]) -> pd.DataFrame:
    """Every (module, symbol, family, eligible) of the table for the modules present and of the grid: the plan's
    number, the grid's, and whether they agree ('ok', 'DIFFERS', 'not in the plan', 'not checked')."""
    present = set(present)
    got = grid.groupby(["module", "symbol", "family", "eligible"]).size().to_dict() if len(grid) else {}
    want = {(c.module, c.symbol, c.family, bool(c.eligible)): c for c in counts if c.module in present}
    rows = []
    for k, c in want.items():
        g = int(got.get(k, 0))
        status = "not checked" if c.n is None else ("ok" if g == c.n else "DIFFERS")
        rows.append({"module": k[0], "symbol": k[1], "family": k[2], "eligible": k[3],
                     "expected": "-" if c.n is None else c.n, "got": g, "status": status, "where": c.where})
    for k, g in got.items():
        k = (k[0], k[1], k[2], bool(k[3]))
        if k not in want:
            rows.append({"module": k[0], "symbol": k[1], "family": k[2], "eligible": k[3], "expected": "-",
                         "got": int(g), "status": "not in the plan", "where": ""})
    return pd.DataFrame(rows, columns=["module", "symbol", "family", "eligible", "expected", "got", "status", "where"])


def count_differences(grid: pd.DataFrame, counts: Sequence[Count], present: Iterable[str]) -> pd.DataFrame:
    rep = count_report(grid, counts, present)
    return rep[rep.status.isin(["DIFFERS", "not in the plan"])].reset_index(drop=True)


def checked_grid(modules: Mapping[str, object], counts: Optional[Sequence[Count]] = None
                 ) -> Tuple[pd.DataFrame, List[Tuple[str, M.Variant]]]:
    """The grid of the modules present, checked: the contract, the fields, unique ids, and the counts per module,
    symbol, family and eligibility against the plan's table (``COUNT_TABLE``). Raises GridError listing every
    difference."""
    if not modules:
        raise GridError("no rule module found (backtesting/research/tradeiq2_rules_<key>.py)")
    for k, m in modules.items():
        _require_api(k, m)
    pairs, problems = collect(modules)
    if problems:
        raise GridError("the rule modules' variants are not a valid grid:\n  " + "\n  ".join(problems))
    g = grid_frame(pairs)
    diff = count_differences(g, PREREG_COUNTS if counts is None else counts, modules)
    if len(diff):
        raise GridError("the grid's counts differ from the plan's (COUNT_TABLE, PREREG 6-8):\n"
                        + diff.to_string(index=False))
    return g, pairs


# ───────────────────────────── files: atomic writes, reads ─────────────────────────────

GZ = T1.GZ


def _atomic(path: Path, write: Callable[[Path], None]) -> None:
    """``write(tmp)`` then rename over ``path``: a reader never sees a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    gz = str(path).endswith(".gz")
    _atomic(path, lambda p: df.to_csv(p, index=False, compression=GZ if gz else None))


def write_text(text: str, path: Path) -> None:
    _atomic(path, lambda p: p.write_text(text, encoding="utf-8"))


def _bool(x) -> bool:
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    return str(x).strip().lower() in ("true", "1", "yes")


def read_grid(study_dir: Path) -> pd.DataFrame:
    g = pd.read_csv(Path(study_dir) / "grid.csv", dtype=str, keep_default_na=False)
    g["eligible"] = g.eligible.map(_bool)
    return g


def read_results(study_dir: Path, name: str = "results_dev_val.csv") -> pd.DataFrame:
    r = pd.read_csv(Path(study_dir) / name, float_precision="round_trip", dtype={"info": str, "params": str})
    r["info"] = r["info"].fillna("")
    r["eligible"] = r.eligible.map(_bool)
    return r


# ───────────────────────────── the code's identity (git blob ids) ─────────────────────────────

DRIVER = "backtesting/research/tradeiq2.py"
# what a variant's numbers depend on besides its rule module and the ports (a change re-runs it)
RUN_CODE = ("backtesting/research/tradeiq2_market.py", "backtesting/research/tradeiq2_filters.py",
            "backtesting/research/tradeiq_market.py", "backtesting/research/tradeiq_ind.py",
            "backtesting/research/tradeiq.py", "backtesting/research/external.py", "backtesting/research/balke.py",
            "backtesting/config.py", "backtesting/data/store.py")
REPORT_CODE = ("backtesting/research/silver.py", "backtesting/research/final10.py")
INFO_FILES = (DRIVER,) + REPORT_CODE        # their blob ids are recorded, not required to be equal


def _rel(path) -> str:
    p = Path(path).resolve()
    try:
        return p.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def port_files() -> List[str]:
    """The reconciled ports (``tradeiq2_ind_*.py``) in the tree: every rule may read any of them."""
    return sorted(_rel(p) for p in (REPO_ROOT / "backtesting" / "research").glob("tradeiq2_ind_*.py"))


def module_file(mod) -> str:
    f = getattr(mod, "__file__", None)
    if not f:
        raise ValueError(f"{mod!r}: a rule module needs a __file__ (its code's blob id)")
    return _rel(f)


def run_code(mod) -> List[str]:
    """The files a variant of ``mod`` depends on: the harness and study 1's, the ports, the module itself."""
    return list(RUN_CODE) + port_files() + [module_file(mod)]


def _path_of(f: str) -> Path:
    p = Path(f)
    return p if p.is_absolute() else REPO_ROOT / p


def _key(f: str) -> str:
    return "blob " + Path(f).name


def blobs_of(files: Iterable[str]) -> Dict[str, str]:
    """{'blob <file name>': git blob id} (``git hash-object``, computed without git)."""
    out = {}
    for f in files:
        k = _key(f)
        b = T1.blob_id(_path_of(f))
        if out.get(k, b) != b:
            raise ValueError(f"two code files named {Path(f).name}")
        out[k] = b
    return out


def all_code(modules: Mapping[str, object]) -> List[str]:
    files = [DRIVER] + list(RUN_CODE) + port_files() + [module_file(modules[k]) for k in MODULE_KEYS if k in modules]
    return list(dict.fromkeys(files)) + [f for f in REPORT_CODE if (REPO_ROOT / f).exists()]


def info_keys() -> set:
    """The blob keys that are recorded but need not be equal (the driver, the report code)."""
    return {_key(f) for f in INFO_FILES}


def env_versions() -> Dict[str, str]:
    """The environment a result depends on besides the code: Python, numpy, pandas, numba."""
    import numba
    return {"env python": platform.python_version(), "env numpy": np.__version__, "env pandas": pd.__version__,
            "env numba": numba.__version__}


@dataclass
class CodeSnapshot:
    """
    The code's blob ids (every file of ``all_code``) and the environment as they were when a command started, i.e.
    the code its imported modules run. Every part is stamped with these, never with what the disk holds later, and
    ``check`` hashes the result files again: a file edited while a command runs stops it (``CodeChangedError``)
    rather than letting parts computed by the old code carry the new code's id.
    """
    modules: Dict[str, object]
    files: Dict[str, List[str]]                 # module key -> the result files of its variants
    blobs: Dict[str, str]                       # 'blob <name>' -> id, every code file
    env: Dict[str, str]

    @classmethod
    def take(cls, modules: Mapping[str, object]) -> "CodeSnapshot":
        files = {k: run_code(m) for k, m in modules.items()}
        return cls(dict(modules), files, blobs_of(all_code(modules)), env_versions())

    def run_blobs(self, key: str) -> Dict[str, str]:
        return {_key(f): self.blobs[_key(f)] for f in self.files[key]}

    def result_keys(self) -> List[str]:
        return list(dict.fromkeys(_key(f) for fs in self.files.values() for f in fs))

    def harness_blobs(self) -> Dict[str, str]:
        return {_key(f): self.blobs[_key(f)] for f in RUN_CODE}

    def changed(self) -> List[str]:
        """The result files whose blob id is not the snapshot's now (a port added or removed counts)."""
        now_files = {k: run_code(m) for k, m in self.modules.items()}
        if now_files != self.files:
            a = {f for fs in self.files.values() for f in fs}
            b = {f for fs in now_files.values() for f in fs}
            return sorted(Path(f).name + " (added)" for f in b - a) + sorted(Path(f).name + " (removed)" for f in a - b)
        files = list(dict.fromkeys(f for fs in self.files.values() for f in fs))
        now = blobs_of(files)
        return [k[5:] for k in now if now[k] != self.blobs.get(k)]

    def check(self, where: str = "") -> None:
        bad = self.changed()
        if bad:
            raise CodeChangedError(f"the code changed during the run{where}: {', '.join(bad)}. The parts computed "
                                   "before the change keep the code they were computed with; run again")


def code_changes(recorded: Mapping[str, str], now: Mapping[str, str], keys: Iterable[str]) -> List[str]:
    """The files among ``keys`` (and the result files ``recorded`` has that ``now`` lacks) whose blob ids differ."""
    keys = set(keys) | {k for k in recorded if k.startswith("blob ") and k not in info_keys()}
    return sorted(k[5:] for k in keys if str(recorded.get(k, "")) != str(now.get(k, "")))


# ───────────────────────────── the data's identity ─────────────────────────────

DATA_COLS = ("data_sha1", "binance_sha1")


def binance_identity(end_s: int) -> str:
    """A sha1 over the Binance BTCUSDT kline files (study 1's 1h, this study's 5m) whose period starts before
    ``end_s``: each file's .CHECKSUM (the sha256 Binance publishes and the fetch verified), else its size, else
    'missing'. Reads no kline."""
    h = hashlib.sha1()
    lists = []
    for fn in (getattr(TM, "_binance_files", None), getattr(M, "_binance_files_5m", None)):
        if fn is not None:
            lists.append(fn())
    for files in lists:
        for _label, a, _z, _url, path in files:
            if a >= end_s:
                break
            ck = Path(path).with_name(Path(path).name + ".CHECKSUM")
            if ck.exists():
                tag = (ck.read_text(encoding="utf-8").split() or ["empty"])[0].lower()
            elif Path(path).exists():
                tag = f"size {Path(path).stat().st_size}"
            else:
                tag = "missing"
            h.update(f"{Path(path).name} {tag}\n".encode("utf-8"))
    return h.hexdigest()


def data_identity(mk: M.TMarket2, binance: bool = False) -> Dict[str, object]:
    """What a market served: its M1 span and count, its end, the sha1 of its arrays (time, OHLC, spread, ticks) and,
    for BTC from the store (``binance``), the Binance klines' identity (``binance_identity``)."""
    h = hashlib.sha1()
    for a in (mk.t, mk.o, mk.h, mk.l, mk.c, mk.sp, mk.n):
        h.update(np.ascontiguousarray(a).tobytes())
    return {**market_info(mk), "data_sha1": h.hexdigest(),
            "binance_sha1": binance_identity(int(mk.end_s)) if (binance and mk.symbol == M.BTC) else ""}


def market_info(mk: M.TMarket2) -> Dict[str, object]:
    return {"symbol": mk.symbol, "m1_bars": int(len(mk)), "first_m1": str(TM.utc(mk.t[0])),
            "last_m1": str(TM.utc(mk.t[-1])), "served_until": str(TM.utc(mk.end_s))}


# ───────────────────────────── the work: per-variant parts and the fork pool ─────────────────────────────
#
# Each variant of a job is computed into run_parts/<job>/<module>/<symbol>/<sha1 of its id>.pkl.gz (its rows,
# trades, quarters and weeks) with a sidecar .json (the stamp: the variant's identity and params, the windows, the
# costs, the code's blob ids, the environment, the data served; the part's size and sha1). Both are written
# atomically, the sidecar last, so a part is complete exactly when its sidecar exists, matches and describes the file
# next to it (size and sha1); anything else (missing, truncated, damaged, from other code, environment or data) is
# computed again. The CSVs are assembled from the parts in grid order.

PARTS = "run_parts"
DEVVAL, EXAMJOB, ACCJOB = "devval", "exam", "accounts"
IDENT_COLS = ("vid", "module", "symbol", "tf", "script", "family", "group", "eligible", "info", "params")
EXEC_COLS = ("legs", "lanes")                # what the Exec was: its legs (partial exits) and lanes
TRADE_COLS = ("vid", "window", "cost", "entry_time", "exit_time", "side", "entry", "exit", "reason", "pnl", "slippage",
              "hold_h", "risk", "r", "tag", "bar", "lane", "reasons")
QUARTER_COLS = ("vid", "window", "quarter", "start", "pnl", "pnl_x15", "held", "held_x15")
WEEK_COLS = ("vid", "window", "week_start", "pnl", "pnl_x15")


class RunError(RuntimeError):
    """Variants whose build or run raised; their ids and tracebacks are in the message (the others are kept)."""


def parts_root(study_dir: Path) -> Path:
    p = Path(study_dir) / PARTS
    p.mkdir(parents=True, exist_ok=True)
    gi = p / ".gitignore"
    if not gi.exists():
        gi.write_text("# per-variant work files of tradeiq2 run / exam / accounts (resume); not results\n*\n",
                      encoding="utf-8")
    return p


def part_path(study_dir: Path, job: str, key: str, symbol: str, vid: str) -> Path:
    h = hashlib.sha1(vid.encode("utf-8")).hexdigest()[:24]
    return Path(study_dir) / PARTS / job / key / symbol / f"{h}.pkl.gz"


def _side(path: Path) -> Path:
    return path.with_name(path.name.split(".")[0] + ".json")


def _jsonable(x):
    return json.loads(json.dumps(x, sort_keys=True, default=str))


def write_part(path: Path, stamp: dict, body: dict, seconds: float) -> None:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=1, mtime=0) as fh:
        pickle.dump(body, fh, protocol=pickle.HIGHEST_PROTOCOL)
    data = buf.getvalue()
    _atomic(path, lambda p: p.write_bytes(data))
    side = {"stamp": _jsonable(stamp), "size": len(data), "sha1": hashlib.sha1(data).hexdigest(),
            "seconds": round(float(seconds), 3)}
    write_text(json.dumps(side, sort_keys=True), _side(path))


def part_ok(path: Path, stamp: dict) -> bool:
    """The part is complete, undamaged (its size and sha1 are its sidecar's) and was made for ``stamp`` (identity,
    windows, costs, code, environment, data)."""
    try:
        side = json.loads(_side(path).read_text(encoding="utf-8"))
        if side.get("stamp") != _jsonable(stamp):
            return False
        data = Path(path).read_bytes()
        return len(data) == int(side["size"]) and hashlib.sha1(data).hexdigest() == side["sha1"]
    except (OSError, ValueError, KeyError, TypeError):
        return False


def part_seconds(path: Path) -> float:
    try:
        return float(json.loads(_side(path).read_text(encoding="utf-8")).get("seconds", 0.0))
    except (OSError, ValueError):
        return 0.0


class PartError(RunError):
    """A part that passed its sidecar's checks but cannot be read (e.g. pickled by another pandas): incomplete."""


def read_part(path: Path) -> dict:
    data = Path(path).read_bytes()
    side = json.loads(_side(path).read_text(encoding="utf-8"))
    if hashlib.sha1(data).hexdigest() != side["sha1"]:
        raise PartError(f"{path}: its bytes do not match its sidecar")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as fh:
            return pickle.load(fh)
    except Exception as e:  # noqa: BLE001 - any unpickling failure makes the part incomplete
        raise PartError(f"{path}: cannot be read ({type(e).__name__}: {e})") from e


def _drop_part(path: Path) -> None:
    """Mark a part incomplete (its sidecar goes; the next run computes it again)."""
    try:
        _side(path).unlink()
    except FileNotFoundError:
        pass


def _clean_tmp(root: Path) -> None:
    if Path(root).exists():
        for p in Path(root).rglob(".*.tmp*"):
            p.unlink()


def _stamp(job: str, v: M.Variant, blobs: Dict[str, str], data: Mapping[str, object], env: Mapping[str, str],
           **what) -> dict:
    return {"job": job, "vid": v.id, "ident": v.ident(), "blobs": dict(blobs), "data": dict(data), "env": dict(env),
            **what}


_G: Dict[str, object] = {}        # what the forked workers inherit: the work (market, context, module, variants)


@dataclass
class _Work:
    job: str
    key: str
    module: object
    ctx: M.Context
    variants: List[M.Variant]
    paths: List[Path]
    stamps: List[dict]
    compute: Callable[["_Work", M.Variant, dict], dict]


def _task(i: int) -> dict:
    w: _Work = _G["work"]
    v = w.variants[i]
    t0 = time.time()
    try:
        body = w.compute(w, v, w.stamps[i])
        write_part(w.paths[i], w.stamps[i], body, time.time() - t0)
        return {"i": i, "vid": v.id, "seconds": time.time() - t0, "error": "", "rss_mb": _rss_mb()}
    except Exception:  # noqa: BLE001 - reported by the parent with the variant's id
        return {"i": i, "vid": v.id, "seconds": time.time() - t0, "error": traceback.format_exc(), "rss_mb": _rss_mb()}


def _worker(wid: int, tasks, results, held) -> None:
    """A forked worker: task indices from ``tasks`` until None, each result into ``results``; ``held[wid]`` (shared
    memory, written before the work starts) is the index it is working on, -1 between tasks."""
    while True:
        i = tasks.get()
        if i is None:
            return
        held[wid] = i
        r = _task(i)
        held[wid] = -1
        results.put(r)


def _fork_pool(work: _Work, todo: Sequence[int], n: int, note: Callable[[int, dict], None],
               poll: float = 0.5) -> List[dict]:
    """
    ``_task`` over ``todo`` in ``n`` forked workers that share the parent's market, bars and warmed arrays
    copy-on-write (study 1 / sizing.py). Every worker is forked before this process starts any thread (the queues'
    feeders start with the first put). A worker that dies (an OS memory kill, a segfault, os._exit) stops the batch
    with a RunError naming the variants it held, instead of waiting forever for a result that never comes
    (multiprocessing.Pool's behaviour); the parts already written stay valid.
    """
    ctx = mp.get_context("fork")
    tasks, results = ctx.Queue(), ctx.Queue()
    held = ctx.RawArray("q", n)
    for k in range(n):
        held[k] = -1
    procs = [ctx.Process(target=_worker, args=(k, tasks, results, held), daemon=True) for k in range(n)]
    for p in procs:
        p.start()
    for i in todo:
        tasks.put(i)
    for _ in procs:
        tasks.put(None)
    out: List[dict] = []
    ok = False
    try:
        while len(out) < len(todo):
            try:
                x = results.get(timeout=poll)
            except queue.Empty:
                dead = [(k, p.exitcode) for k, p in enumerate(procs) if p.exitcode not in (None, 0)]
                if dead or all(p.exitcode is not None for p in procs):
                    lost = [work.variants[int(held[k])].id for k, _ in dead if int(held[k]) >= 0]
                    raise RunError(
                        f"{work.job} {work.ctx.symbol} {work.key}: "
                        + (", ".join(f"worker {k} died (exit code {c})" for k, c in dead) if dead else
                           "every worker ended") + f" with {len(todo) - len(out)} of {len(todo)} variants not done"
                        + (f"; it held {', '.join(lost)}" if lost else "")
                        + " (the parts already written are kept: run again)")
                continue
            out.append(x)
            note(len(out), x)
        ok = True
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(timeout=10)
        if not ok:
            tasks.cancel_join_thread()
            results.cancel_join_thread()
        tasks.close()
        results.close()
    return out


def _pool(work: _Work, todo: Sequence[int], workers: int, log=print, every: int = 25) -> List[dict]:
    """Run ``work`` on the variants ``todo``: in this process (workers <= 1), or in forked workers (``_fork_pool``).
    Each worker writes its parts. The progress note gives this process's peak memory and the workers' largest."""
    todo = list(todo)
    _G["work"] = work
    t0 = time.time()
    out: List[dict] = []
    peak = [0.0]

    def note(n, r):
        peak[0] = max(peak[0], float(r.get("rss_mb", 0.0)))
        if n % every == 0 or n == len(todo):
            log(f"    {work.job} {work.ctx.symbol} {work.key}: {n} / {len(todo)} variants ({time.time() - t0:.0f} s, "
                f"rss {_rss_mb():.0f} MB here, workers' peak {peak[0]:.0f} MB)")
    try:
        if workers <= 1 or len(todo) <= 1:
            for n, i in enumerate(todo, 1):
                r = _task(i)
                out.append(r)
                note(n, r)
        else:
            out = _fork_pool(work, todo, min(int(workers), len(todo)), note)
    finally:
        _G.pop("work", None)
    bad = [r for r in out if r["error"]]
    if bad:
        raise RunError(f"{len(bad)} of {len(todo)} variants of {work.key} on {work.ctx.symbol} failed (the others are "
                       "kept; run again after the fix):\n" + "\n".join(f"--- {r['vid']}\n{r['error']}" for r in bad[:5]))
    return out


def _rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3


def _warm(ctx: M.Context, mod, variants: Sequence[M.Variant]) -> None:
    """The bars every variant and filter reads, and the module's own ``warm`` (EXTRAS: optional), built in the parent
    before the fork so the workers share them."""
    for tf in sorted({v.tf for v in variants} | {"1H", "4H", "1D", "1W"}, key=list(M.TFS).index):
        ctx.bars(tf)
    w = _attr(mod, WARM_NAMES)
    if w is not None:
        w(ctx, list(variants))


def _load_default(symbol: str, end) -> M.TMarket2:
    return M.load(symbol, end=end)


def exec_shape(ex: M.Exec) -> Dict[str, int]:
    """The Exec's legs (the most of any lane: 2 = PREREG 4's 50/50 partial exits) and lanes."""
    legs = max((len(x.legs) for x in ex.lanes), default=1) if ex.kind == "lanes" else len(ex.legs)
    return {"legs": int(legs), "lanes": int(len(ex.lanes))}


def _build(w: _Work, v: M.Variant) -> M.Exec:
    ex = w.module.build(v, w.ctx)
    if not isinstance(ex, M.Exec):
        raise TypeError(f"{w.key}.build({v.id}) returned {type(ex).__name__}, not a tradeiq2_market.Exec")
    return ex


def _score(w: _Work, v: M.Variant, stamp: dict) -> dict:
    ex = _build(w, v)
    res = M.run_variant(w.ctx, v, ex, windows=tuple(stamp["windows"]), costs=tuple(stamp["costs"]),
                        trades_windows=tuple(stamp["trades_windows"]))
    return {"rows": res.rows, "trades": res.trades, "quarters": res.quarters, "weekly": res.weekly, "kind": ex.kind,
            **exec_shape(ex)}


def _market_part(study_dir: Path, job: str, symbol: str) -> Path:
    return Path(study_dir) / PARTS / job / "_market" / f"{symbol}.json"


BH_COLS = ("symbol", "window", "start", "end", "cost", "bh_net", "bh_max_dd", "bh_profit_dd", "bh_entry", "bh_exit")
INFO_COLS = ("symbol", "m1_bars", "first_m1", "last_m1", "served_until")


def bh_rows(mk: M.TMarket2, windows: Sequence[str]) -> List[dict]:
    """Buy-and-hold of 0.01 lot (PREREG 7's reference) over each window at both costs (study 1's buy_and_hold.csv)."""
    out = []
    for w in windows:
        a, z = span(w, mk.symbol)
        for cost in COSTS:
            out.append({"symbol": mk.symbol, "window": w, "start": a, "end": z, "cost": cost,
                        **M.buy_and_hold(mk, a, z, cost)})
    return out


StampOf = Callable[[M.Variant, Dict[str, str], Mapping[str, object], Mapping[str, str]], dict]


def score_stamp(job: str, windows_of: Callable[[str], Sequence[str]], trades_of: Callable[[str], Sequence[str]]
                ) -> StampOf:
    """The stamp of a scoring job's part: the variant, its windows, the costs, the trades' windows, the code, the
    environment, the data."""
    return lambda v, blobs, data, env: _stamp(job, v, blobs, data, env, windows=list(windows_of(v.symbol)),
                                              costs=list(COSTS), trades_windows=list(trades_of(v.symbol)))


def _market_ok(mpath: Path, mstamp: dict) -> bool:
    try:
        return json.loads(mpath.read_text(encoding="utf-8")).get("stamp") == _jsonable(mstamp)
    except (OSError, ValueError):
        return False


def run_job(study_dir: Path, job: str, pairs: Sequence[Tuple[str, M.Variant]], modules: Mapping[str, object],
            stamp_of: StampOf, compute: Callable, end, bh_windows: Callable[[str], Sequence[str]],
            symbols: Optional[Sequence[str]] = None, keys: Optional[Sequence[str]] = None, workers: int = 2,
            loader=None, log=print, snap: Optional[CodeSnapshot] = None) -> Dict[str, int]:
    """
    Every variant of ``pairs`` (restricted to ``symbols`` / module ``keys``) whose part is not complete for its
    stamp (``stamp_of(variant, blobs, data, env)``): ``compute(work, variant, stamp)`` in the fork pool. One symbol
    at a time: its market (``loader(symbol, end)``) loaded first, always, so that its identity (``data_identity``)
    is part of every stamp; its Context built once in the parent; one module at a time, its cached arrays dropped
    before the next. The code is hashed again before and after each module's batch (``CodeSnapshot.check``): when a
    file changed, that batch's parts are marked incomplete and the job stops. Also the symbol's market identity and
    buy-and-hold over ``bh_windows(symbol)`` (the _market part).
    """
    snap = snap or CodeSnapshot.take(modules)
    loader_fn = loader or _load_default
    root = parts_root(study_dir)
    _clean_tmp(root / job)
    by: Dict[Tuple[str, str], List[M.Variant]] = {}
    for key, v in pairs:
        by.setdefault((v.symbol, key), []).append(v)
    stats = {"computed": 0, "skipped": 0, "markets": 0}
    for symbol in ALL_SYMBOLS:
        if symbols is not None and symbol not in symbols:
            continue
        here = [k for k in MODULE_KEYS if (symbol, k) in by and (keys is None or k in keys)]
        if not here:
            continue
        snap.check(f" (before {symbol})")
        t0 = time.time()
        mk = loader_fn(symbol, end)
        if not isinstance(mk, M.TMarket2) or mk.symbol != symbol:
            raise TypeError(f"the loader gave {mk!r} for {symbol}")
        data = data_identity(mk, binance=loader is None)
        stats["markets"] += 1
        plan = {}
        for key in here:
            vs = by[(symbol, key)]
            stamps = [stamp_of(v, snap.run_blobs(key), data, snap.env) for v in vs]
            paths = [part_path(study_dir, job, key, symbol, v.id) for v in vs]
            todo = [i for i in range(len(vs)) if not part_ok(paths[i], stamps[i])]
            stats["skipped"] += len(vs) - len(todo)
            plan[key] = (vs, stamps, paths, todo)
        mpath = _market_part(study_dir, job, symbol)
        mstamp = {"job": job, "symbol": symbol, "end": str(end), "windows": list(bh_windows(symbol)),
                  "blobs": snap.harness_blobs(), "env": snap.env, "data": data}
        log(f"  {job} {symbol}: {len(mk):,} M1 bars to {TM.utc(mk.end_s)} ({time.time() - t0:.0f} s; data sha1 "
            f"{data['data_sha1'][:12]}); " + ", ".join(f"{k} {len(plan[k][3])}/{len(plan[k][0])}" for k in here)
            + " variants to compute")
        if not _market_ok(mpath, mstamp):
            write_text(json.dumps({"stamp": _jsonable(mstamp), "info": _jsonable(data),
                                   "bh": _jsonable(bh_rows(mk, bh_windows(symbol)))}, sort_keys=True), mpath)
        if not any(p[3] for p in plan.values()):
            del mk
            gc.collect()
            continue
        ctx = M.Context(mk)
        for key in here:
            vs, stamps, paths, todo = plan[key]
            if not todo:
                continue
            snap.check(f" (before {symbol} {key})")
            _warm(ctx, modules[key], [vs[i] for i in todo])
            err: Optional[BaseException] = None
            try:
                _pool(_Work(job, key, modules[key], ctx, vs, paths, stamps, compute), todo, workers, log)
            except BaseException as e:  # noqa: BLE001 - re-raised below, after the code check
                err = e
            try:
                snap.check(f" (while {symbol} {key} ran)")
            except CodeChangedError:
                for i in todo:
                    _drop_part(paths[i])
                raise
            if err is not None:
                raise err
            stats["computed"] += len(todo)
            ctx.cache.clear()
            gc.collect()
        del ctx, mk
        gc.collect()
    return stats


def score_job(study_dir: Path, job: str, pairs: Sequence[Tuple[str, M.Variant]], modules: Mapping[str, object],
              windows_of: Callable[[str], Sequence[str]], trades_of: Callable[[str], Sequence[str]], end,
              symbols: Optional[Sequence[str]] = None, keys: Optional[Sequence[str]] = None, workers: int = 2,
              loader=None, log=print, snap: Optional[CodeSnapshot] = None) -> Dict[str, int]:
    """``run_job`` scoring every variant over ``windows_of(symbol)`` at x1.0 and x1.5 (``M.run_variant``), the
    trades of ``trades_of(symbol)``; buy-and-hold over the same windows."""
    return run_job(study_dir, job, pairs, modules, score_stamp(job, windows_of, trades_of), _score, end, windows_of,
                   symbols=symbols, keys=keys, workers=workers, loader=loader, log=log, snap=snap)


class _CsvStream:
    """A CSV (gzip when the name ends in .gz, with mtime 0: the same bytes for the same rows) written chunk by
    chunk into a temporary file and renamed over the target at the end, so memory holds one chunk at a time."""

    def __init__(self, path: Path, columns: Sequence[str]):
        self.path, self.columns = Path(path), list(columns)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = self.path.with_name(f".{self.path.name}.tmp{os.getpid()}")
        self.raw = open(self.tmp, "wb")
        self.fh = gzip.GzipFile(filename="", mode="wb", fileobj=self.raw, mtime=0) if self.path.suffix == ".gz" \
            else self.raw
        self.rows = 0
        self.fh.write((",".join(self.columns) + "\n").encode("utf-8"))

    def add(self, df: pd.DataFrame) -> None:
        if len(df):
            extra_cols = [c for c in df.columns if c not in self.columns]
            if extra_cols:
                raise ValueError(f"{self.path.name}: unexpected columns {extra_cols}")
            self.fh.write(df.reindex(columns=self.columns).to_csv(index=False, header=False).encode("utf-8"))
            self.rows += len(df)

    def close(self) -> None:
        if self.fh is not self.raw:
            self.fh.close()
        self.raw.close()
        os.replace(self.tmp, self.path)

    def abort(self) -> None:
        try:
            if self.fh is not self.raw:
                self.fh.close()
            self.raw.close()
        finally:
            if self.tmp.exists():
                self.tmp.unlink()


def _row_of(key: str, row: dict, shape: Optional[Mapping[str, int]] = None) -> dict:
    out = {"vid": row["vid"], "module": key, "symbol": row["symbol"], "tf": row["tf"], "script": row["script"],
           "family": row["family"], "group": GROUP[row["family"]], "eligible": bool(row["eligible"]),
           "info": row["info"], "params": row["params"]}
    out.update({k: v for k, v in row.items() if k not in out})
    if shape is not None:
        out.update({k: int(shape[k]) for k in EXEC_COLS})
    return out


def _data_of(study_dir: Path, job: str) -> Dict[str, dict]:
    """Per symbol: the data identity the job's _market part records (the market it last loaded)."""
    out = {}
    for s, j in _market_jsons(study_dir, job).items():
        d = j.get("stamp", {}).get("data")
        if d:
            out[s] = d
    return out


def assemble_scores(study_dir: Path, job: str, pairs: Sequence[Tuple[str, M.Variant]], modules: Mapping[str, object],
                    windows_of: Callable[[str], Sequence[str]], trades_of: Callable[[str], Sequence[str]],
                    results: Mapping[str, Sequence[str]], trades: Mapping[str, Sequence[str]],
                    quarters: Mapping[str, Sequence[str]] = None, weekly: Mapping[str, Sequence[str]] = None,
                    log=print, snap: Optional[CodeSnapshot] = None) -> Dict[str, object]:
    """The job's CSVs from its complete parts, in grid order: ``results`` / ``trades`` / ``quarters`` / ``weekly`` map
    a file name to the windows it holds. A part is complete for the snapshot's code and environment and for the data
    its symbol's _market part records. Variants without a complete part are left out (and counted); a part that
    cannot be read is marked incomplete (the next run computes it)."""
    snap = snap or CodeSnapshot.take(modules)
    quarters, weekly = quarters or {}, weekly or {}
    study_dir = Path(study_dir)
    res_rows: Dict[str, List[dict]] = {f: [] for f in results}
    streams = {f: _CsvStream(study_dir / f, TRADE_COLS) for f in trades}
    qparts: Dict[str, List[pd.DataFrame]] = {f: [] for f in quarters}
    wparts: Dict[str, List[pd.DataFrame]] = {f: [] for f in weekly}
    cols: Optional[List[str]] = None
    done, missing, unreadable = [], [], []
    stamp_of = score_stamp(job, windows_of, trades_of)
    data = _data_of(study_dir, job)
    try:
        for key, v in pairs:
            path = part_path(study_dir, job, key, v.symbol, v.id)
            if v.symbol not in data or not part_ok(path, stamp_of(v, snap.run_blobs(key), data[v.symbol], snap.env)):
                missing.append(v.id)
                continue
            try:
                body = read_part(path)
            except PartError:
                _drop_part(path)
                unreadable.append(v.id)
                missing.append(v.id)
                continue
            rows = [_row_of(key, r, body) for r in body["rows"]]
            for r in rows:
                if cols is None:
                    cols = list(r)
                elif list(r) != cols:
                    raise RunError(f"{v.id}: its row's columns differ from the first variant's")
            for f, ws in results.items():
                res_rows[f] += [r for r in rows if r["window"] in ws]
            tr = body["trades"]
            for f, ws in trades.items():
                if len(tr):
                    streams[f].add(tr[tr.window.isin(ws)])
            for f, ws in quarters.items():
                q = body["quarters"]
                qparts[f].append(q[q.window.isin(ws)].reindex(columns=list(QUARTER_COLS)))
            for f, ws in weekly.items():
                wk = body["weekly"]
                wparts[f].append(wk[wk.window.isin(ws)].reindex(columns=list(WEEK_COLS)))
            done.append(v.id)
        for f, rows in res_rows.items():
            write_csv(pd.DataFrame(rows, columns=cols or list(IDENT_COLS)), study_dir / f)
        for f, parts in qparts.items():
            write_csv(pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(QUARTER_COLS)),
                      study_dir / f)
        for f, parts in wparts.items():
            write_csv(pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(WEEK_COLS)),
                      study_dir / f)
        for s in streams.values():
            s.close()
    except BaseException:
        for s in streams.values():
            s.abort()
        raise
    if unreadable:
        log(f"  note: {len(unreadable)} parts could not be read and are marked incomplete: {', '.join(unreadable[:5])}")
    if missing:
        log(f"  note: {len(missing)} of {len(pairs)} variants have no complete part for this code, environment and "
            f"data (left out of the CSVs; run again): {', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}")
    return {"done": done, "missing": missing}


def _market_jsons(study_dir: Path, job: str) -> Dict[str, dict]:
    out = {}
    for s in ALL_SYMBOLS:
        try:
            out[s] = json.loads(_market_part(study_dir, job, s).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return out


def _now() -> str:
    return str(pd.Timestamp.now(tz="UTC").floor("s"))


def run_info_frame(study_dir: Path, job: str, pairs, modules, done: Sequence[str], windows_of, workers: int,
                   snap: Optional[CodeSnapshot] = None) -> pd.DataFrame:
    """Per symbol and module: the data served (span, count, sha1; BTC's Binance klines), the variants and the
    complete ones, the runs, the compute seconds of their parts, the environment and the git blob ids of every code
    file as the command started (study 1's run_info.csv)."""
    snap = snap or CodeSnapshot.take(modules)
    mj = _market_jsons(study_dir, job)
    done = set(done)
    rows = []
    for s in ALL_SYMBOLS:
        got = mj.get(s, {}).get("info", {})
        info = {k: got.get(k, s if k == "symbol" else "") for k in INFO_COLS + DATA_COLS}
        for key in MODULE_KEYS:
            vs = [v for k, v in pairs if k == key and v.symbol == s]
            if not vs:
                continue
            ok = [v for v in vs if v.id in done]
            sec = sum(part_seconds(part_path(study_dir, job, key, s, v.id)) for v in ok)
            rows.append({**info, "module": key, "variants": len(vs), "done": len(ok),
                         "runs": len(ok) * len(windows_of(s)) * len(COSTS), "seconds": round(sec, 1),
                         "workers": int(workers), "written_utc": _now(), **snap.env, **snap.blobs})
    return pd.DataFrame(rows)


def _write_grid(study_dir: Path, grid: pd.DataFrame, log=print) -> None:
    p = Path(study_dir) / "grid.csv"
    if p.exists():
        old = pd.read_csv(p, dtype=str, keep_default_na=False)
        new = grid.astype(str)
        if not (old.shape == new.shape and (old.columns == new.columns).all() and (old.values == new.values).all()):
            log("  note: grid.csv changed (the rule modules' variants differ from the last grid written)")
    write_csv(grid, p)


def _is_real(study_dir) -> bool:
    return Path(study_dir).resolve() == Path(REAL_STUDY_DIR).resolve()


def _refuse_test_options(study_dir: Path, what: str, modules: Optional[Mapping[str, object]] = None, counts=None,
                         loader=None, require_all: bool = True) -> None:
    """The study folder itself takes only the plan's count table, the store's markets (tradeiq2_market.load), the
    real rule modules (backtesting/research/tradeiq2_rules_<key>.py) and, for the freeze, all nine of them."""
    if not _is_real(study_dir):
        return
    bad = []
    if counts is not None:
        bad.append("a count table other than PREREG 6's (COUNT_TABLE)")
    if loader is not None:
        bad.append("a market loader other than tradeiq2_market.load")
    if not require_all:
        bad.append("a freeze without every rule module")
    for k, m in (modules or {}).items():
        want = (REPO_ROOT / "backtesting" / "research" / f"tradeiq2_rules_{k}.py").resolve()
        f = getattr(m, "__file__", None)
        if not f or Path(f).resolve() != want:
            bad.append(f"rule module '{k}' from {f} (not {_rel(want)})")
    if bad:
        raise StudyFolderError(f"{what} on the study folder {study_dir}: {'; '.join(bad)}. These are for tests on "
                               "other folders only")


def _refuse_frozen(study_dir: Path, what: str) -> None:
    for name in (FINALISTS_MD, FINALISTS_MD + ".sha256"):
        if (Path(study_dir) / name).exists():
            raise FileExistsError(f"{what}: {Path(study_dir) / name} exists, and `{what}` would rewrite the files "
                                  "FINALISTS.md was frozen from")


def run(study_dir: Optional[Path] = None, modules: Optional[Mapping[str, object]] = None,
        counts: Optional[Sequence[Count]] = None, symbols: Optional[Sequence[str]] = None,
        keys: Optional[Sequence[str]] = None, workers: int = 2, loader=None, log=print) -> Dict[str, object]:
    """
    ``run``: every variant of the grid over Development, Validation and the two together (M.RUN_WINDOWS) at x1.0 and
    x1.5, the not-eligible and information rows included; the markets loaded only up to the hold-out start. Resumes
    (complete parts are skipped); then results_dev_val.csv, quarters_dev_val.csv, trades_dev_val.csv.gz,
    weekly_dev_val.csv.gz, buy_and_hold.csv and run_info.csv from every complete part. Refuses once FINALISTS.md
    exists, and the test-only options on the study folder.
    """
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    modules = find_modules() if modules is None else dict(modules)
    _refuse_test_options(study_dir, "run", modules, counts, loader)
    _refuse_frozen(study_dir, "run")
    snap = CodeSnapshot.take(modules)
    grid, pairs = checked_grid(modules, counts)
    missing = [k for k in MODULE_KEYS if k not in modules]
    if missing:
        log(f"note: rule modules not found: {', '.join(missing)}; the grid holds the others only")
    _write_grid(study_dir, grid, log)
    t0 = time.time()
    stats = score_job(study_dir, DEVVAL, pairs, modules, lambda s: RUN_WINDOWS, lambda s: ("dev", "val"),
                      M.HOLDOUT_START, symbols=symbols, keys=keys, workers=workers, loader=loader, log=log, snap=snap)
    snap.check(" (before the CSVs were assembled)")
    got = assemble_scores(study_dir, DEVVAL, pairs, modules, lambda s: RUN_WINDOWS, lambda s: ("dev", "val"),
                          results={"results_dev_val.csv": RUN_WINDOWS}, trades={"trades_dev_val.csv.gz": ("dev", "val")},
                          quarters={"quarters_dev_val.csv": ("dev", "val")},
                          weekly={"weekly_dev_val.csv.gz": ("dev", "val")}, log=log, snap=snap)
    bh = [r for s, j in _market_jsons(study_dir, DEVVAL).items() for r in j.get("bh", [])]
    write_csv(pd.DataFrame(bh, columns=list(BH_COLS)), study_dir / "buy_and_hold.csv")
    write_csv(run_info_frame(study_dir, DEVVAL, pairs, modules, got["done"], lambda s: RUN_WINDOWS, workers, snap),
              study_dir / "run_info.csv")
    log(f"run: {stats['computed']} computed, {stats['skipped']} already complete, {len(got['done'])} of "
        f"{len(pairs)} in the CSVs ({time.time() - t0:.0f} s) -> {study_dir}")
    return {**stats, "done": len(got["done"]), "missing": got["missing"]}


# ───────────────────────────── the selection (PREREG 7) ─────────────────────────────

def check_complete(res: pd.DataFrame, grid: pd.DataFrame, windows: Sequence[str] = RUN_WINDOWS,
                   name: str = "results_dev_val.csv") -> None:
    want = grid.vid.tolist()
    for w in windows:
        got = res[res.window == w].vid.tolist()
        if got != want:
            have = set(got)
            lack = [v for v in want if v not in have]
            raise AssertionError(f"{name}: the {w} rows are not grid.csv's variants ({len(got)} rows, {len(want)} "
                                 f"variants; {len(lack)} missing, e.g. {lack[:3]}): run `run` first")


def _order(g: pd.DataFrame) -> List[str]:
    """PREREG 7's order: the highest D+V profit / max drawdown first; ties by Development's, then by the id."""
    k = pd.DataFrame({"a": -g.devval_profit_dd.astype(float).fillna(-np.inf),
                      "b": -g.dev_profit_dd.astype(float).fillna(-np.inf), "c": g.index.astype(str)}, index=g.index)
    return list(k.sort_values(["a", "b", "c"], kind="mergesort").index)


def qualification(res: pd.DataFrame) -> pd.DataFrame:
    """
    Per variant, PREREG 7 (study 1's rule): q1 Development net > 0 at x1.0 and at x1.5; q2 Development trades >= the
    minimum of PREREG 5 (30 on M5, M15, 1H, 4H; 15 on 1D); q3 Development profit / max drawdown >= 1.0 and positive
    quarters >= 50% (x1.0; a P/DD that does not exist, no drawdown, is no pass); q4 Validation net > 0 at x1.0.
    ``qualifies`` = all four and eligible (not-eligible and information rows are scored, never selected).
    ``rank``: per symbol (gold, BTC), the qualifiers by D+V profit / max drawdown (one continuous run, x1.0), ties by
    Development's, then the id. ``champion``: per symbol and family, the qualifier first in that order.
    ``champion_rank``: the champions of a symbol in that order. ``finalist``: per symbol, the champions in that order,
    at most one per script group (GROUP), at most three. ``insufficient_events``: a WY / WY-DERIVED row with fewer
    than 15 Development trades (PREREG 6.3's verdict; it changes no rule above).
    """
    by = {w: res[res.window == w].set_index("vid") for w in RUN_WINDOWS}
    d, v, dv = by["dev"], by["val"], by["devval"]
    if d.index.has_duplicates or not (d.index.equals(v.index) and d.index.equals(dv.index)):
        raise ValueError("every variant needs exactly one dev, val and devval row, in one order")
    q = d[["module", "symbol", "tf", "script", "family", "group", "eligible", "info"]].copy()
    q["eligible"] = q.eligible.map(_bool).astype(bool)
    for c in EXEC_COLS:                                    # the Exec's legs and lanes (the 0.02-lot note)
        q[c] = d[c].fillna(0).astype(int) if c in d.columns else (1 if c == "legs" else 0)
    q["min_trades"] = d.tf.map(M.MIN_TRADES)
    if q.min_trades.isna().any():
        raise ValueError(f"no minimum of trades for timeframe(s) {sorted(set(d.tf[q.min_trades.isna()]))}")
    q["dev_net"], q["dev_net_x15"], q["dev_trades"] = d.net, d.net_x15, d.trades
    q["dev_max_dd"], q["dev_profit_dd"], q["dev_pos_q_share"], q["dev_sharpe_w"] = (d.max_dd, d.profit_dd,
                                                                                    d.pos_q_share, d.sharpe_w)
    q["val_net"], q["val_net_x15"], q["val_max_dd"], q["val_profit_dd"], q["val_trades"] = (
        v.net, v.net_x15, v.max_dd, v.profit_dd, v.trades)
    q["devval_net"], q["devval_net_x15"], q["devval_max_dd"], q["devval_profit_dd"] = (
        dv.net, dv.net_x15, dv.max_dd, dv.profit_dd)
    with np.errstate(invalid="ignore"):
        q["q1"] = (d.net > 0) & (d.net_x15 > 0)
        q["q2"] = d.trades >= q.min_trades
        q["q3"] = (d.profit_dd >= MIN_PDD) & (d.pos_q_share >= MIN_POS_Q)
        q["q4"] = v.net > 0
    q["qualifies"] = q.q1 & q.q2 & q.q3 & q.q4 & q.eligible
    q["insufficient_events"] = q.family.isin(WY_FAMILIES) & (q.dev_trades < INSUFFICIENT_EVENTS)
    q["rank"] = np.nan
    q["family_rank"] = np.nan
    q["champion"] = False
    q["champion_rank"] = np.nan
    q["finalist"] = False
    for s in SYMBOLS:
        g = q[(q.symbol == s) & q.qualifies]
        if not len(g):
            continue
        order = _order(g)
        q.loc[order, "rank"] = np.arange(1, len(order) + 1)
        fam = q.loc[order, "family"]
        champs = []
        for f in FAMILIES:
            ids = [x for x, y in zip(order, fam) if y == f]
            if ids:
                q.loc[ids, "family_rank"] = np.arange(1, len(ids) + 1)
                champs.append(ids[0])
        champs = [x for x in order if x in set(champs)]
        q.loc[champs, "champion"] = True
        q.loc[champs, "champion_rank"] = np.arange(1, len(champs) + 1)
        taken: List[str] = []
        for x in champs:
            if len(taken) == N_FINALISTS:
                break
            gr = q.at[x, "group"]
            if gr not in taken:
                taken.append(gr)
                q.at[x, "finalist"] = True
    return q.reset_index()


def champions_in_order(qual: pd.DataFrame) -> List[Tuple[str, str]]:
    """(role, id) of every champion, symbol by symbol (gold first), in champion rank order; the role is 'finalist'
    or 'champion' (PREREG 7: the exam is every champion's)."""
    out = []
    for s in SYMBOLS:
        g = qual[(qual.symbol == s) & qual.champion].sort_values("champion_rank")
        out += [("finalist" if bool(f) else "champion", vid) for vid, f in zip(g.vid, g.finalist)]
    return out


def family_best(qual: pd.DataFrame) -> pd.DataFrame:
    """Per symbol and family: its champion, else (no qualifier) its eligible row first in PREREG 7's order (the
    'family's best row' of PREREG 7's accounts and of the report). Families without eligible rows are left out."""
    rows = []
    for s in SYMBOLS:
        for f in FAMILIES:
            g = qual[(qual.symbol == s) & (qual.family == f) & qual.eligible]
            if not len(g):
                continue
            c = g[g.champion]
            vid = c.vid.iloc[0] if len(c) else _order(g.set_index("vid"))[0]
            rows.append({"symbol": s, "family": f, "group": GROUP[f], "vid": vid, "champion": bool(len(c))})
    return pd.DataFrame(rows, columns=["symbol", "family", "group", "vid", "champion"])


def champions_table(qual: pd.DataFrame) -> pd.DataFrame:
    """champions.csv: per symbol and family (PREREG 7's table), the champion or 'none', with its numbers."""
    rows = []
    for s in SYMBOLS:
        for f in FAMILIES:
            g = qual[(qual.symbol == s) & (qual.family == f)]
            c = g[g.champion]
            r = c.iloc[0] if len(c) else None
            rows.append({"symbol": s, "family": f, "group": GROUP[f], "variants": int(len(g)),
                         "eligible": int(g.eligible.sum()), "qualify": int(g.qualifies.sum()),
                         "champion": r.vid if r is not None else "none",
                         "champion_rank": int(r.champion_rank) if r is not None else np.nan,
                         "finalist": bool(r.finalist) if r is not None else False,
                         **{k: (float(r[k]) if r is not None else np.nan) for k in
                            ("dev_net", "dev_net_x15", "dev_trades", "dev_profit_dd", "dev_pos_q_share", "val_net",
                             "val_profit_dd", "devval_net", "devval_max_dd", "devval_profit_dd")}})
    return pd.DataFrame(rows)


MT_UNIVERSES = (("all variants run", False), ("eligible variants", True))


def multiple_testing(res: pd.DataFrame, weekly: pd.DataFrame, qual: pd.DataFrame) -> pd.DataFrame:
    """PREREG 7 by study 1's ``multiple_testing``, per symbol (gold, BTC): the deflated Sharpe of the best Development
    variant and of each would-be finalist, and Hansen's SPA / White's Reality Check (Development weekly P/L, x1.0),
    for two universes (``universe``): 'all variants run' is the PREREG's (N = every variant run on the symbol, the
    bootstrap over all of them, the not-eligible and information rows included); 'eligible variants' leaves those out
    (HP-DRAWN looks ahead and the controls are no trial of the selection), for information. ``N_all`` and
    ``N_eligible`` count both. A universe is left out when a symbol has fewer than 3 of its variants or 4 weeks (the
    bootstrap's floor)."""
    n_all = qual[qual.symbol.isin(SYMBOLS)].groupby("symbol").size()
    n_el = qual[qual.symbol.isin(SYMBOLS) & qual.eligible].groupby("symbol").size()
    out = []
    for universe, eligible_only in MT_UNIVERSES:
        sel = qual[qual.symbol.isin(SYMBOLS) & (qual.eligible if eligible_only else True)]
        keep = set(sel.vid)
        r = res[res.vid.isin(keep)]
        dev = r[r.window == "dev"]
        if dev.empty or (dev.groupby("symbol").size() < 3).any() or (dev.weeks < 4).any():
            continue
        w = weekly[(weekly.window == "dev") & weekly.vid.isin(keep)]
        mt = T1.multiple_testing(r, w, sel)
        mt.insert(0, "universe", universe)
        mt.insert(5, "N_all", [int(n_all.get(s, 0)) for s in mt.symbol])
        mt.insert(6, "N_eligible", [int(n_el.get(s, 0)) for s in mt.symbol])
        out.append(mt)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ───────────────────────────── a variant in words ─────────────────────────────

TF_WORDS = {"M5": "5-minute", "M15": "15-minute", "1H": "1-hour", "4H": "4-hour", "1D": "daily"}
FILTER_KEYS = ("filter", "filt", "filters")
STOP_KEYS = ("stop", "stops", "sl")
FILTER_TOKENS = ("F0", "F1", "F2", "F2-4H", "F2-1D", "F3", "FR", "FS", "LO", "FD", "HV", "LV", "HV+F2-4H", "TIGHT")
STOP_TOKENS = ("S0", "S1", "S-W")


def id_tokens(vid: str) -> List[str]:
    return vid.split("|")


def _params(v) -> Dict[str, object]:
    if isinstance(v, M.Variant):
        return dict(v.params)
    if isinstance(v, Mapping):
        return dict(v)
    try:
        return dict(json.loads(v)) if isinstance(v, str) and v else {}
    except ValueError:
        return {}


def setting(vid: str, params, keys: Sequence[str], tokens: Sequence[str]) -> str:
    """A setting of a variant (its filter, its stop): the params' value under one of ``keys``, else the id's token
    among ``tokens``, else ''."""
    p = _params(params)
    for k in keys:
        if k in p and p[k] not in (None, ""):
            x = p[k]
            return "+".join(map(str, x)) if isinstance(x, (list, tuple)) else str(x)
    hit = [t for t in id_tokens(vid)[2:] if t in tokens]
    if len(hit) > 1 and "LO" in hit:
        hit.remove("LO")                                    # a ribbon's LO is its side; SP's LO filter stands alone
    return hit[0] if len(hit) == 1 else ""


def one_line(text) -> str:
    """Text for one markdown line of FINALISTS.md: line breaks and tabs become spaces and backticks quotes, so no
    module's words can open or close a code block (``read_frozen`` reads the ```text blocks)."""
    s = str(text).replace("`", "'")
    return " ".join(s.split())


LEGS_NOTE = "partial exits: live needs at least 0.02 lot per unit (PREREG 4)"


def legs_note(legs) -> str:
    """PREREG 4: a row with partial exits (two legs) needs at least 0.02 lot per unit live: noted wherever it is."""
    try:
        return LEGS_NOTE if int(legs) > 1 else ""
    except (TypeError, ValueError):
        return ""


def describe(modules: Mapping[str, object], key: str, v: M.Variant) -> str:
    """The rule row in words, on one line: the module's ``describe(variant)`` (EXTRAS) or, without it, the variant's
    fields."""
    f = _attr(modules[key], DESCRIBE_NAMES) if key in modules else None
    if f is not None:
        return one_line(f(v))
    p = dict(v.params)
    words = "; ".join(f"{k} {p[k]}" for k in sorted(p))
    return one_line(f"{TF_WORDS.get(v.tf, v.tf)} bars of the bid (UTC); script {v.script}, family {v.family} (PREREG "
                    f"{SECTION[key]})" + (f"; settings: {words}" if words else "") + ". Decided at the close of a "
                    "signal bar, filled at the open of the next M1 bar (a buy at the ask, a sell at the bid)")


def label_of(vid: str) -> str:
    return " ".join(id_tokens(vid)[1:])


def _short(vid: str) -> str:
    return T1._short(vid)


_usd, _dd, _num, _yes, _md = T1._usd, T1._dd, T1._num, T1._yes, T1._md


def _pct(x) -> str:
    return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.0%}"


# ───────────────────────────── CANDIDATES.md and the finalists' file ─────────────────────────────

def _symbols_in(df: pd.DataFrame, syms: Sequence[str] = SYMBOLS) -> List[str]:
    have = set(df.symbol)
    return [s for s in syms if s in have]


def stale_banner(stale: Sequence[str]) -> List[str]:
    """The banner of a file written from results that other code, environment or data made (``stale_code``)."""
    if not stale:
        return []
    return [f"**Stale results:** {', '.join(stale)} differ from what wrote `results_dev_val.csv` (`run_info.csv`). "
            "These tables describe the old results; run `run` and `select` again before `freeze` (which refuses).", ""]


def stale_code(info: pd.DataFrame, snap: "CodeSnapshot") -> List[str]:
    """The result files and environment entries whose ids now differ from run_info.csv's."""
    if not len(info):
        return []
    rec = {c: str(info[c].iloc[0]) for c in info.columns
           if (c.startswith("blob ") or c.startswith("env ")) and info[c].astype(str).nunique() == 1}
    rec.update({c: "(mixed)" for c in info.columns if (c.startswith("blob ") or c.startswith("env "))
                and info[c].astype(str).nunique() > 1})
    out = code_changes(rec, snap.blobs, snap.result_keys())
    out += [k[4:] for k in snap.env if str(rec.get(k, "")) != str(snap.env[k])]
    return out


def candidates_md(res: pd.DataFrame, qual: pd.DataFrame, champs: pd.DataFrame, mt: pd.DataFrame, bh: pd.DataFrame,
                  info: pd.DataFrame, missing_modules: Sequence[str], stale: Sequence[str] = ()) -> str:
    syms = _symbols_in(qual)
    d_all = res[res.window == "dev"]
    out = ["# TradeIQ's 9 indicators for 2027: the candidates after Development and Validation", "",
           f"Written by `python -B -m backtesting.research.tradeiq2 select` on "
           f"{pd.Timestamp.now(tz='UTC').strftime('%d %b %Y %H:%M')} UTC from the CSVs of `run` (written "
           f"{info.written_utc.iloc[0] if len(info) else '-'}). **This is not `FINALISTS.md`.** Nothing is frozen, and "
           "no result of the hold-out (from 2024-07-01) or of gold's Early window (2017-2018) exists: the guard of "
           "`tradeiq2_market.py` served the data only up to 2024-06-30 23:59 UTC. The would-be champions and "
           "finalists below are what PREREG section 7's rule gives; they become champions and finalists only when "
           "`FINALISTS.md` and its sha256 are written (`freeze`). The same text, as it would be frozen, is "
           "`FINALISTS.draft.md`.", "",
           "Per 0.01 lot after Exness costs (the spread at every fill, one extra spread on every stop fill). "
           "Development 2019-01-01 to 2022-12-31, Validation 2023-01-01 to 2024-06-30, D+V the two together as one "
           "continuous run (the claim markets' Development starts as PREREG 3 says). Profit / DD = net profit / max "
           "drawdown on equity marked at M1 extremes.", ""]
    if missing_modules:
        out += [f"**Partial grid:** the rule modules {', '.join(missing_modules)} were not found, so their rows are "
                "not in this selection.", ""]
    out += stale_banner(stale)
    rows = []
    for s in _symbols_in(d_all, ALL_SYMBOLS):
        g = d_all[d_all.symbol == s]
        i = info[info.symbol == s]
        rows.append([NAME.get(s, s), len(g), int(g.eligible.sum()), int((~g.eligible).sum()),
                     f"{str(i.first_m1.iloc[0])[:10]} .. {str(i.served_until.iloc[0])[:16]}" if len(i) else "-",
                     f"{int(i.m1_bars.iloc[0]):,}" if len(i) and str(i.m1_bars.iloc[0]) != "" else "-",
                     int(i.runs.sum()) if len(i) else 0])
    out += ["## What was run", "", _md(["Symbol", "Variants", "Eligible", "Not eligible / information", "M1 data served",
                                       "M1 bars", "Runs (3 windows x 2 costs)"], rows), ""]
    blob_cols = [c for c in info.columns if c.startswith("blob ")]
    if blob_cols:
        out += ["Code that wrote the CSVs (git blob ids, `run_info.csv`): "
                + ", ".join(f"`{c[5:]}` {str(info[c].iloc[0])[:12]}" for c in blob_cols) + ".", ""]
    rows = []
    for s in syms:
        qs = qual[qual.symbol == s]
        el = qs[qs.eligible]
        rows.append([NAME[s], len(qs), len(el), int((el.dev_net > 0).sum()), int((el.val_net > 0).sum()),
                     int(((el.dev_net > 0) & (el.val_net > 0)).sum()), int((el.q1).sum()), int((el.q1 & el.q2).sum()),
                     int((el.q1 & el.q2 & el.q3).sum()), int(qs.qualifies.sum()), int(qs.champion.sum()),
                     int(qs.finalist.sum())])
    out += ["## Headline", "", _md(["Symbol", "Variants", "Eligible", "Dev net > 0", "Val net > 0", "Both > 0",
                                    "Rule 1", "Rules 1-2", "Rules 1-3", "Qualify (1-4)", "Champions",
                                    "Would-be finalists"], rows), "",
            "Rules 1-3 and the net counts are over the eligible rows. Rule 1: Development net > 0 at x1.0 and x1.5; "
            "2: the minimum of Development trades (PREREG 5); 3: Development P/DD >= 1.0 with at least 50% of the "
            "quarters positive; 4: Validation net > 0 at x1.0.", ""]
    for s in syms:
        qs = qual[qual.symbol == s]
        rows = []
        for f in FAMILIES:
            g = qs[qs.family == f]
            if not len(g):
                continue
            c = g[g.champion]
            rows.append([f, GROUP[f], len(g), int(g.eligible.sum()), int((g.eligible & (g.dev_net > 0)).sum()),
                         int((g.eligible & (g.val_net > 0)).sum()), int(g.qualifies.sum()),
                         _usd(float(g[g.eligible].dev_net.median())) if g.eligible.any() else "-",
                         _short(c.vid.iloc[0]) if len(c) else "none",
                         _num(float(c.devval_profit_dd.iloc[0])) if len(c) else "-"])
        out += [f"### {NAME[s]} by family", "",
                _md(["Family", "Script group", "Variants", "Eligible", "Dev net > 0", "Val net > 0", "Qualify",
                     "Median dev net", "Would-be champion", "Its D+V P/DD"], rows), ""]
        rows = []
        for tf in TFS:
            g = qs[(qs.tf == tf) & qs.eligible]
            if len(g):
                rows.append([tf, len(g), int((g.dev_net > 0).sum()), int((g.val_net > 0).sum()), int(g.qualifies.sum()),
                             _usd(float(g.dev_net.median())), _usd(float(g.val_net.median()))])
        out += [f"{NAME[s]} by timeframe (eligible rows):", "",
                _md(["TF", "Variants", "Dev net > 0", "Val net > 0", "Qualify", "Median dev net", "Median val net"],
                    rows), ""]
    if len(bh):
        rows = []
        for s in _symbols_in(bh, ALL_SYMBOLS):
            for w in RUN_WINDOWS:
                b1 = bh[(bh.symbol == s) & (bh.window == w) & (bh.cost == 1.0)]
                b15 = bh[(bh.symbol == s) & (bh.window == w) & (bh.cost == 1.5)]
                if len(b1):
                    rows.append([NAME.get(s, s), T1.WINDOW_NAME[w], _usd(float(b1.bh_net.iloc[0])),
                                 _usd(float(b15.bh_net.iloc[0])) if len(b15) else "-", _dd(float(b1.bh_max_dd.iloc[0])),
                                 _num(float(b1.bh_profit_dd.iloc[0]))])
        out += ["## Buy-and-hold of 0.01 lot, for reference", "",
                _md(["Symbol", "Window", "Net x1.0", "Net x1.5", "Max DD", "Profit / DD"], rows), ""]
    for s in syms:
        qs = qual[qual.symbol == s]
        ch = qs[qs.champion].sort_values("champion_rank")
        out += [f"## {NAME[s]}: the would-be champions and finalists", ""]
        if not len(ch):
            out += ["**No variant qualifies: no champion, no finalist. The answer is \"none\".**", ""]
            continue
        rows = [[int(r.champion_rank), int(r["rank"]), r.family, r.group, _short(r.vid), _usd(r.dev_net),
                 _usd(r.dev_net_x15), int(r.dev_trades), _num(r.dev_profit_dd), _pct(r.dev_pos_q_share),
                 _usd(r.val_net), _usd(r.devval_net), _dd(r.devval_max_dd), f"{r.devval_profit_dd:.4f}",
                 "**finalist**" if r.finalist else "", legs_note(r.get("legs", 1))] for _, r in ch.iterrows()]
        out += [_md(["#", "Rank", "Family", "Group", "Champion", "Dev net", "Dev x1.5", "Dev trades", "Dev P/DD",
                     "Dev +Q", "Val net", "D+V net", "D+V DD", "D+V P/DD", "Would-be finalist", "Note"], rows), "",
                "Families with no qualifier: " + (", ".join(f for f in FAMILIES if f in set(qs.family)
                                                           and not qs[(qs.family == f)].qualifies.any()) or "none")
                + ".", ""]
        ok = qs[qs.qualifies].sort_values("rank")
        top = ok.head(30)
        out += [f"{NAME[s]}: the qualifiers, {len(ok)} in all (the first {len(top)} by rank; every row is in "
                "`qualification.csv`):", "",
                _md(["Rank", "Variant", "Family", "Dev net", "Dev x1.5", "Dev trades", "Dev P/DD", "Dev +Q", "Val net",
                     "D+V P/DD", "Champion"],
                    [[int(r["rank"]), _short(r.vid), r.family, _usd(r.dev_net), _usd(r.dev_net_x15), int(r.dev_trades),
                      _num(r.dev_profit_dd), _pct(r.dev_pos_q_share), _usd(r.val_net), _num(r.devval_profit_dd),
                      "yes" if r.champion else ""] for _, r in top.iterrows()]), ""]
        nq = qs[qs.eligible & ~qs.qualifies].copy()
        nq["fails"] = (~nq.q1).astype(int) + (~nq.q2).astype(int) + (~nq.q3).astype(int) + (~nq.q4).astype(int)
        nm = nq[nq.fails == 1].sort_values("devval_profit_dd", ascending=False).head(5)
        if len(nm):
            out += [f"{NAME[s]}: the five best by D+V P/DD among the eligible rows that fail exactly one rule (for "
                    "information; they are not candidates):", "",
                    _md(["Variant", "Fails", "Dev net", "Dev x1.5", "Dev trades", "Dev P/DD", "Dev +Q", "Val net",
                         "D+V P/DD"],
                        [[_short(r.vid), ",".join(k for k in ("q1", "q2", "q3", "q4") if not r[k]), _usd(r.dev_net),
                          _usd(r.dev_net_x15), int(r.dev_trades), _num(r.dev_profit_dd), _pct(r.dev_pos_q_share),
                          _usd(r.val_net), _num(r.devval_profit_dd)] for _, r in nm.iterrows()]), ""]
        ie = qs[qs.insufficient_events]
        if len(ie):
            out += [f"{NAME[s]}: {len(ie)} Wyckoff rows have fewer than {INSUFFICIENT_EVENTS} Development trades: "
                    "their verdict is \"insufficient events\" (PREREG 6.3).", ""]
    if len(mt):
        out += ["## Multiple testing (Development weekly P/L, x1.0; PREREG 7)", "",
                _md(["Universe", "Symbol", "Role", "Variant", "N", "N (all rows)", "N (eligible)", "Weeks",
                     "Sharpe (ann.)", "E[max] (as run)", "DSR", "DSR (null var.)", "DSR (within-TF var.)", "SPA p",
                     "Reality Check p"],
                    [[r.universe, NAME[r.symbol], r.role, _short(r.vid), int(r.N), int(r.N_all), int(r.N_eligible),
                      int(r.T_weeks), _num(r.sharpe_w_ann), _num(r.e_max_sr_ann), _num(r.dsr, 3),
                      _num(r.dsr_null, 3), _num(r.dsr_within_tf, 3), _num(r.spa_p, 3), _num(r.rc_p, 3)]
                     for _, r in mt.iterrows()]), "",
                "As study 1 (its DEVIATIONS 26): the deflated Sharpe ratio for N trials with the trials' Sharpe "
                "variance as run, with the null variance and with the within-timeframe variance; SPA and the Reality "
                "Check over all N variants of the universe at once. 'All variants run' is PREREG 7's (N = every "
                "variant run on the symbol); 'eligible variants' leaves out the not-eligible and information rows "
                "(HP-DRAWN looks ahead), for information. PREREG 7 sets no threshold: information.", ""]
    claim_rows = d_all[d_all.symbol.isin(CLAIM_SYMBOLS)]
    if len(claim_rows):
        va = res[res.window == "val"].set_index("vid")
        out += ["## The claim-check rows (PREREG 8, information only)", "",
                _md(["Variant", "Dev net", "Dev trades", "Dev PF", "Dev avg R", "Val net", "Val PF"],
                    [[f"`{r.vid}`", _usd(r.net), int(r.trades), _num(r.profit_factor), _num(r.avg_r),
                      _usd(float(va.loc[r.vid, "net"])), _num(float(va.loc[r.vid, "profit_factor"]))]
                     for _, r in claim_rows.iterrows()]), ""]
    out += ["## Files", "", "`grid.csv`, `results_dev_val.csv` (one row per variant and window; `_x15` = x1.5 costs), "
            "`trades_dev_val.csv.gz`, `quarters_dev_val.csv`, `weekly_dev_val.csv.gz`, `buy_and_hold.csv`, "
            "`run_info.csv`, `qualification.csv`, `champions.csv`, `multiple_testing.csv`, `FINALISTS.draft.md`.", ""]
    return "\n".join(out)


FINALISTS_MD = "FINALISTS.md"
DRAFT_MD = "FINALISTS.draft.md"


def _role_vids(qual: pd.DataFrame) -> List[Tuple[str, str]]:
    return champions_in_order(qual)


PROVENANCE_PLAN = ("the grid was checked against PREREG 6's count table (COUNT_TABLE) and the markets were the "
                   "store's (tradeiq2_market.load)")


def finalists_md(res: pd.DataFrame, qual: pd.DataFrame, grid: pd.DataFrame, info: pd.DataFrame,
                 blobs: Dict[str, str], inputs: Dict[str, str], modules: Mapping[str, object], frozen: bool,
                 env: Optional[Mapping[str, str]] = None, provenance: str = PROVENANCE_PLAN,
                 checks: Sequence[str] = ()) -> str:
    """FINALISTS.md (``frozen``) or FINALISTS.draft.md: every champion and finalist of PREREG 7 with its rule row in
    words (one line each), its Development and Validation numbers, the sha256 of the selection's inputs, the
    environment and the code's git blob ids (PREREG 7, Freezing), each in a ```text block ``read_frozen`` reads."""
    roles = _role_vids(qual)
    idx = res.set_index(["vid", "window"])
    q = qual.set_index("vid")
    gi = grid.set_index("vid")
    now = pd.Timestamp.now(tz="UTC").strftime("%d %b %Y %H:%M")
    title = ("# TradeIQ's 9 indicators for 2027: the champions and finalists (frozen)" if frozen else
             "# TradeIQ's 9 indicators for 2027: the champions and finalists (DRAFT, not frozen)")
    out = [title, ""]
    if frozen:
        out += [f"Written by `python -B -m backtesting.research.tradeiq2 freeze` on {now} UTC. Until this file and its "
                "sha256 (`FINALISTS.md.sha256`) existed, the guard of `tradeiq2_market.py` served no data from "
                "2024-07-01 00:00 UTC on and scored no window overlapping gold's Early window (2017-01-01 to "
                "2018-12-31), so no result of either exam existed when the champions below were chosen. The file is "
                "written once: `freeze` refuses to write it again, and the guard closes again if its sha256 stops "
                "matching.", ""]
    else:
        out += [f"Written by `python -B -m backtesting.research.tradeiq2 select` on {now} UTC: **a draft**. It is what "
                "`freeze` would write now, from the same CSVs; it is not `FINALISTS.md`, nothing is frozen, and the "
                "guard stays closed.", ""]
    out += ["The rule (PREREG 7): a variant qualifies when (1) its Development net profit is above 0 at x1.0 and at "
            "x1.5 costs, (2) it has at least the minimum of Development trades of PREREG 5 (30 on M5, M15, 1H and 4H; "
            "15 on 1D), (3) its Development profit / max drawdown is at least 1.0 with at least 50% of the quarters "
            "positive, and (4) its Validation net profit is above 0 at x1.0; rows marked not eligible or information "
            "only never qualify. The champion of a symbol and family is its qualifier with the highest profit / max "
            "drawdown over Development + Validation together (one continuous run, 2019-01-01 to 2024-06-30, x1.0); "
            "ties go to Development's profit / max drawdown, then to the id. The finalists of a symbol are its three "
            "champions with the highest D+V profit / max drawdown, at most one per script (RIB with ALMA-X; "
            "MSD-ALONE, MSD-FILTER and BOS; WY with WY-DERIVED; HP-HARMONIC with HP-CHART; HA-ENTRY with HA-MANAGED; "
            "every other family on its own), ties as for the champions. They were recomputed from "
            "`results_dev_val.csv` by this command and are those of `qualification.csv` and `CANDIDATES.md`.", "",
            "## The champions and the finalists", "",
            "The exam (`python -B -m backtesting.research.tradeiq2 exam`) reads its variants from this block, one per "
            "line: the role, then the id.", "", "```text"]
    out += [f"{role} {vid}" for role, vid in roles] + ["```", ""]
    for s in SYMBOLS:
        rs = [(role, vid) for role, vid in roles if q.loc[vid, "symbol"] == s]
        n_q = int(qual[qual.symbol == s].qualifies.sum())
        n_f = sum(1 for role, _ in rs if role == "finalist")
        out += [f"### {NAME[s]}: {len(rs)} champion{'s' if len(rs) != 1 else ''}, {n_f} finalist"
                f"{'s' if n_f != 1 else ''} ({n_q} qualifiers)", ""]
        if not rs:
            out += ["**No variant qualifies: there is no champion and no finalist on this symbol, and the answer is "
                    "\"none\".**", ""]
            continue
        rows = []
        for role, vid in rs:
            r = gi.loc[vid]
            rows.append([int(q.loc[vid, "champion_rank"]), int(q.loc[vid, "rank"]), role, r.family, r.group,
                         f"`{vid}`", r.tf, setting(vid, r.params, FILTER_KEYS, FILTER_TOKENS) or "-",
                         setting(vid, r.params, STOP_KEYS, STOP_TOKENS) or "-"])
        out += [_md(["#", "Rank", "Role", "Family", "Script group", "Variant", "TF", "Filter", "Stop"], rows), "",
                "The rule rows:", ""]
        vmap = {v.id: (k, v) for k, v in _pairs_of(grid)}
        for j, (role, vid) in enumerate(rs, 1):
            key, v = vmap[vid]
            mf = module_file(modules[key]) if key in modules else f"tradeiq2_rules_{key}.py"
            b = blobs.get("blob " + Path(mf).name, "-")
            note = legs_note(q.loc[vid, "legs"]) if "legs" in q.columns else ""
            rest = one_line(f"({role}; script {v.script}, family {v.family}, {TF_WORDS.get(v.tf, v.tf)}; filter "
                            f"{setting(vid, v.params, FILTER_KEYS, FILTER_TOKENS) or '-'}, stop "
                            f"{setting(vid, v.params, STOP_KEYS, STOP_TOKENS) or '-'}): {describe(modules, key, v)}."
                            + (f" Note: {note}." if note else "")
                            + f" Code: {Path(mf).name} {b} with the shared files below.")
            out.append(f"{j}. `{vid}` {rest}")
        out.append("")
        rows = []
        for j, (role, vid) in enumerate(rs, 1):
            d = idx.loc[(vid, "dev")]
            rows.append([j, _short(vid), _usd(d.net), _usd(d.net_x15), int(d.trades), _dd(d.max_dd), _num(d.profit_dd),
                         f"{int(d.pos_q)}/{int(d.n_q)}", "-" if not math.isfinite(d.win_rate) else f"{d.win_rate:.0f}%",
                         _num(d.profit_factor), _num(d.avg_r), _num(d.sharpe_w), _pct(d.time_in_mkt)])
        out += ["Development, 2019-01-01 to 2022-12-31 (per 0.01 lot after costs):", "",
                _md(["#", "Variant", "Net x1.0", "Net x1.5", "Trades", "Max DD", "Profit / DD", "Positive quarters",
                     "Win rate", "Profit factor", "Avg R", "Weekly Sharpe (ann.)", "Time in market"], rows), ""]
        rows = []
        for j, (role, vid) in enumerate(rs, 1):
            va, dv = idx.loc[(vid, "val")], idx.loc[(vid, "devval")]
            rows.append([j, _short(vid), _usd(va.net), _usd(va.net_x15), int(va.trades), _dd(va.max_dd),
                         _num(va.profit_dd), f"{int(va.pos_q)}/{int(va.n_q)}", _usd(dv.net), _dd(dv.max_dd),
                         f"{dv.profit_dd:.4f}"])
        out += ["Validation, 2023-01-01 to 2024-06-30, and Development + Validation as one run:", "",
                _md(["#", "Variant", "Val net x1.0", "Val net x1.5", "Val trades", "Val max DD", "Val profit / DD",
                     "Val positive quarters", "D+V net", "D+V max DD", "D+V profit / DD (the ranking)"], rows), ""]
    spans = {s: M.window_span("holdout", s) for s in SYMBOLS}
    early = M.window_span("early", M.GOLD)
    out += ["## The exam (PREREG 7)", "",
            "Each champion is run over the hold-out (exam 1), " + "; ".join(
                f"{NAME[s]} {spans[s][0]} 00:00 to {spans[s][1]} UTC (exclusive)" for s in SYMBOLS)
            + f", and each gold champion also over the Early window (exam 2), {early[0]} to {early[1]} (exclusive), "
              "each as one continuous run that starts flat at its first bar, at x1.0 and x1.5 costs. **A champion "
              "passes an exam when its net profit there is above 0 at x1.0 and its profit / max drawdown is at least "
              "0.5.** Gold's verdicts: passes both, passes the hold-out only, passes Early only, fails; BTC's: pass "
              "or fail. Then the same exam over every variant, for information (the base rate).", "",
            "## The selection's inputs and the code", "",
            f"Provenance: {one_line(provenance)}." + (" Checks before the freeze: " + "; ".join(one_line(c) for c in
                                                                                         checks) + "." if checks
                                                     else ""), "",
            "The sha256 of the files the champions were read from (`exam` and `accounts` refuse files that differ):",
            "", "```text"]
    out += [f"sha256 {k} {v}" for k, v in inputs.items()] + ["```", "", "The environment:", "", "```text"]
    out += [f"env {k[4:]} {v}" for k, v in (env or {}).items()] + ["```", "",
                                                                  "The code (git blob ids, `git hash-object`):", "",
                                                                  "```text"]
    out += [f"{k} {v}" for k, v in blobs.items()] + ["```", ""]
    rows = []
    for k, v in blobs.items():
        same = "-" if k not in info.columns else ("yes" if (info[k].astype(str) == v).all() else "**no**")
        rows.append([k[5:], f"`{v}`", same])
    out += [_md(["File", "Blob id now", "Equal to run_info.csv"], rows), ""]
    return "\n".join(out)


def _pairs_of(grid: pd.DataFrame) -> List[Tuple[str, M.Variant]]:
    """The (module, Variant) pairs of a grid frame (the variants rebuilt from grid.csv's fields)."""
    out = []
    for r in grid.itertuples(index=False):
        out.append((r.module, M.Variant(r.vid, r.symbol, r.tf, r.script, r.family, _bool(r.eligible), r.info,
                                        _params(r.params))))
    return out


@dataclass
class Frozen:
    """What FINALISTS.md's ```text blocks hold: the (role, id) lines, the code's blob ids, the sha256 of the
    selection's inputs and the environment."""
    roles: List[Tuple[str, str]] = field(default_factory=list)
    blobs: Dict[str, str] = field(default_factory=dict)
    inputs: Dict[str, str] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)


def parse_frozen(text: str, name: str = FINALISTS_MD) -> Frozen:
    """FINALISTS.md's ``text`` blocks: 'finalist <id>' / 'champion <id>', 'blob <file> <id>', 'sha256 <file> <hash>'
    and 'env <name> <version>' lines; any other line in such a block is an error."""
    fz, inside = Frozen(), False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = line.strip() == "```text"
            continue
        s = line.strip()
        if not inside or not s:
            continue
        parts = s.split()
        if parts[0] == "blob" and len(parts) == 3:
            fz.blobs["blob " + parts[1]] = parts[2]
        elif parts[0] == "sha256" and len(parts) == 3:
            fz.inputs[parts[1]] = parts[2]
        elif parts[0] == "env" and len(parts) == 3:
            fz.env["env " + parts[1]] = parts[2]
        elif parts[0] in ("finalist", "champion") and len(parts) == 2:
            fz.roles.append((parts[0], parts[1]))
        else:
            raise ValueError(f"{name}: unreadable line in a text block: {s!r}")
    return fz


def read_frozen_all(study_dir: Path, name: str = FINALISTS_MD) -> Frozen:
    return parse_frozen((Path(study_dir) / name).read_text(encoding="utf-8"), name)


def read_frozen(study_dir: Path, name: str = FINALISTS_MD) -> Tuple[List[Tuple[str, str]], Dict[str, str]]:
    """The (role, id) lines and the code's blob ids of FINALISTS.md's ``text`` blocks."""
    fz = read_frozen_all(study_dir, name)
    return fz.roles, fz.blobs


def sha256_of(path: Path) -> str:
    return T1.sha256_of(path)


def _missing_modules(modules) -> List[str]:
    return [k for k in MODULE_KEYS if k not in modules]


INPUT_FILES = ("grid.csv", "results_dev_val.csv", "qualification.csv", "run_info.csv", "CANDIDATES.md")


def _read_info(study_dir: Path) -> pd.DataFrame:
    info = pd.read_csv(Path(study_dir) / "run_info.csv", dtype=str, keep_default_na=False)
    info["runs"] = pd.to_numeric(info.runs, errors="coerce").fillna(0).astype(int)
    return info


def _warn_stale(stale: Sequence[str], what: str, log=print) -> None:
    if stale:
        log(f"WARNING: {', '.join(stale)} differ from what wrote results_dev_val.csv (run_info.csv): {what} describes "
            "the old results; run `run` again (freeze refuses until then)")


def select(study_dir: Optional[Path] = None, modules: Optional[Mapping[str, object]] = None, log=print
           ) -> Dict[str, pd.DataFrame]:
    """``select``: PREREG 7 on ``run``'s CSVs: qualification.csv, champions.csv, multiple_testing.csv,
    CANDIDATES.md and FINALISTS.draft.md (never FINALISTS.md). Refuses once FINALISTS.md exists (it would rewrite
    the files FINALISTS.md was frozen from); warns, and says so in CANDIDATES.md, when the code or the environment
    now differ from run_info.csv's."""
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    _refuse_frozen(study_dir, "select")
    modules = find_modules() if modules is None else dict(modules)
    grid = read_grid(study_dir)
    res = read_results(study_dir)
    check_complete(res, grid)
    weekly = pd.read_csv(study_dir / "weekly_dev_val.csv.gz", float_precision="round_trip")
    bh = pd.read_csv(study_dir / "buy_and_hold.csv", float_precision="round_trip")
    info = _read_info(study_dir)
    present = sorted(set(grid.module))
    snap = CodeSnapshot.take({k: v for k, v in modules.items() if k in present})
    stale = stale_code(info, snap)
    _warn_stale(stale, "CANDIDATES.md", log)
    qual = qualification(res)
    champs = champions_table(qual)
    mt = multiple_testing(res, weekly, qual)
    missing = [k for k in MODULE_KEYS if k not in present]
    write_csv(qual, study_dir / "qualification.csv")
    write_csv(champs, study_dir / "champions.csv")
    write_csv(mt, study_dir / "multiple_testing.csv")
    write_text(candidates_md(res, qual, champs, mt, bh, info, missing, stale), study_dir / "CANDIDATES.md")
    inputs = {n: sha256_of(study_dir / n) for n in INPUT_FILES}
    write_text(finalists_md(res, qual, grid, info, snap.blobs, inputs, modules, frozen=False, env=snap.env),
               study_dir / DRAFT_MD)
    log(f"select: {int(qual.qualifies.sum())} qualifiers, {int(qual.champion.sum())} champions, "
        f"{int(qual.finalist.sum())} finalists -> {study_dir / 'CANDIDATES.md'}, {DRAFT_MD}")
    return {"qualification": qual, "champions": champs, "multiple_testing": mt}


# ───────────────────────────── the freeze (PREREG 7) ─────────────────────────────

def _grid_matches(disk: pd.DataFrame, grid: pd.DataFrame) -> bool:
    a = disk[list(GRID_COLUMNS)].astype(str).reset_index(drop=True)
    b = grid[list(GRID_COLUMNS)].astype(str).reset_index(drop=True)
    return a.shape == b.shape and bool((a.values == b.values).all())


IDENTITY_COLS = ("m1_bars", "first_m1", "last_m1", "served_until") + DATA_COLS


def data_check(info: pd.DataFrame, symbols: Sequence[str], loader=None, end=None, log=print) -> List[str]:
    """Each symbol's market loaded again as ``run`` loaded it (to the hold-out start) against the data identity
    run_info.csv records: the differences (none: an empty list)."""
    loader_fn = loader or _load_default
    end = M.HOLDOUT_START if end is None else end
    out = []
    for s in symbols:
        rec = info[info.symbol == s]
        if not len(rec) or "data_sha1" not in rec.columns:
            out.append(f"{s}: run_info.csv records no data identity")
            continue
        mk = loader_fn(s, end)
        now = data_identity(mk, binance=loader is None)
        del mk
        gc.collect()
        bad = [c for c in IDENTITY_COLS if str(rec[c].iloc[0]) != str(now[c])]
        if bad:
            out.append(f"{s}: {', '.join(f'{c} {rec[c].iloc[0]} -> {now[c]}' for c in bad)}")
    return out


def lookahead_cut_check(study_dir: Path, qual: pd.DataFrame, pairs, modules, loader=None, log=print) -> List[dict]:
    """
    The look-ahead check on open data, before the freeze: each would-be champion's Development row recomputed on a
    market cut at the Development end (``loader(symbol, dev end)``) must be results_dev_val.csv's row, text for text.
    A rule that reads bars after a decision (a whole-sample statistic, a peek of several bars) changes its
    Development row when those bars are cut off; a causal rule cannot. (A peek of one bar cannot show: the decision
    at the last bar fills after the window.)
    """
    loader_fn = loader or _load_default
    vm = _vmap(pairs)
    ref = pd.read_csv(Path(study_dir) / "results_dev_val.csv", dtype=str, keep_default_na=False)
    rcols = list(ref.columns)
    ref = ref.set_index(["vid", "window"])
    rows = []
    for s in SYMBOLS:
        champs = qual[(qual.symbol == s) & qual.champion].sort_values("champion_rank").vid.tolist()
        if not champs:
            continue
        _a, z = M.window_span("dev", s)
        mk = loader_fn(s, z)
        ctx = M.Context(mk)
        for vid in champs:
            key, v = vm[vid]
            ex = modules[key].build(v, ctx)
            r = M.run_variant(ctx, v, ex, windows=("dev",), costs=COSTS, trades_windows=())
            again = _as_str_frame(pd.DataFrame([_row_of(key, x, exec_shape(ex)) for x in r.rows]), rcols)
            want = ref.loc[[(vid, "dev")]].reset_index()[rcols]
            same = bool(again.shape == want.shape and (again.values == want.values).all())
            diff = "" if same else ", ".join(c for c in rcols if str(again[c].iloc[0]) != str(want[c].iloc[0]))
            rows.append({"check": f"the Development row again on the market cut at the Development end ({z}) equals "
                                  "results_dev_val.csv's", "vid": vid, "result": same, "differs": diff})
            ctx.cache.clear()
        log(f"  look-ahead check before the freeze, {s}: {sum(r['result'] for r in rows if r['vid'] in champs)} of "
            f"{len(champs)} champions equal on the market cut at {z}")
        del ctx, mk
        gc.collect()
    return rows


def freeze(study_dir: Optional[Path] = None, modules: Optional[Mapping[str, object]] = None,
           counts: Optional[Sequence[Count]] = None, require_all: bool = True, loader=None, log=print) -> Path:
    """
    PREREG 7, Freezing: FINALISTS.md (every champion and finalist, their rule rows in words, their Development and
    Validation numbers, the sha256 of the selection's inputs, the environment, the code's blob ids) and, last,
    FINALISTS.md.sha256 ("<sha256>  FINALISTS.md", the format ``tradeiq2_market.frozen()`` checks). Refuses when
    either exists; the test-only options on the study folder; when a rule module is missing (``require_all``); when
    grid.csv is not the modules' checked grid; when results_dev_val.csv is not complete; when qualification.csv is
    not the selection the results give; when any code or environment a result depends on, or the data served, differ
    from what wrote the results (run_info.csv; the driver's own blob is recorded, not required); when a would-be
    champion's Development row changes on a market cut at the Development end (``lookahead_cut_check``, written to
    freeze_checks.csv). The text is parsed before anything is written; a failure after FINALISTS.md is written
    removes it (and the .sha256) again, so the guard never opens on a file the exam cannot read.
    """
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    modules = find_modules() if modules is None else dict(modules)
    _refuse_test_options(study_dir, "freeze", modules, counts, loader, require_all)
    f, h = study_dir / FINALISTS_MD, study_dir / (FINALISTS_MD + ".sha256")
    if f.exists() or h.exists():
        raise FileExistsError(f"{f} exists: FINALISTS.md is written once and never again")
    if require_all and _missing_modules(modules):
        raise GridError(f"freeze needs every rule module of PREREG 6; missing: {', '.join(_missing_modules(modules))}")
    snap = CodeSnapshot.take(modules)
    grid, pairs = checked_grid(modules, counts)
    if not _grid_matches(read_grid(study_dir), grid):
        raise GridError("grid.csv is not the rule modules' grid now: run `grid`, `run` and `select` again")
    res = read_results(study_dir)
    check_complete(res, grid)
    qual = qualification(res)
    disk = pd.read_csv(study_dir / "qualification.csv", float_precision="round_trip")
    cols = ["vid", "qualifies", "rank", "champion", "champion_rank", "finalist"]
    a = qual[cols].astype(str).reset_index(drop=True)
    b = disk.reindex(columns=cols).astype(str).reset_index(drop=True)
    if not (a.shape == b.shape and bool((a.values == b.values).all())):
        raise AssertionError("qualification.csv is not the selection results_dev_val.csv gives: run `select` first")
    info = _read_info(study_dir)
    stale = stale_code(info, snap)
    if stale:
        raise RuntimeError(f"{', '.join(stale)} differ from what wrote results_dev_val.csv (run_info.csv): run `run` "
                           "and `select` with this code and environment first")
    if "blob tradeiq2.py" in info.columns and not (info["blob tradeiq2.py"] == snap.blobs.get("blob tradeiq2.py")).all():
        log("note: the driver (tradeiq2.py) differs from the one that wrote the results; its blob id is recorded")
    moved = data_check(info, [s for s in ALL_SYMBOLS if s in set(grid.symbol)], loader, log=log)
    if moved:
        raise RuntimeError("the data served now differ from the data results_dev_val.csv was computed on "
                           "(run_info.csv): " + "; ".join(moved) + ". Run `run` and `select` again")
    checks = lookahead_cut_check(study_dir, qual, pairs, modules, loader, log)
    write_csv(pd.DataFrame(checks, columns=["check", "vid", "result", "differs"]), study_dir / "freeze_checks.csv")
    bad = [c["vid"] for c in checks if not c["result"]]
    if bad:
        raise AssertionError(f"look-ahead: the Development rows of {', '.join(bad)} change on a market cut at the "
                             "Development end (freeze_checks.csv); nothing is frozen")
    git_ok = _git_blobs_agree(snap.blobs)
    if git_ok is False:
        raise AssertionError("git hash-object and blob_id disagree on a code file")
    inputs = {n: sha256_of(study_dir / n) for n in INPUT_FILES}
    provenance = PROVENANCE_PLAN if counts is None and loader is None else (
        "TEST FREEZE: " + ", ".join(x for x in ("a test count table" if counts is not None else "",
                                                "a test market loader" if loader is not None else "") if x))
    done = [f"{sum(c['result'] for c in checks)} of {len(checks)} would-be champions have the same Development row "
            "on a market cut at the Development end", "the data served equal run_info.csv's",
            "the code and the environment equal run_info.csv's"]
    text = finalists_md(res, qual, grid, info, snap.blobs, inputs, modules, frozen=True, env=snap.env,
                        provenance=provenance, checks=done)
    want = (champions_in_order(qual), snap.blobs, inputs, snap.env)
    got = parse_frozen(text)
    if (got.roles, got.blobs, got.inputs, got.env) != want:
        raise AssertionError("FINALISTS.md's text does not parse back to the champions, the code, the inputs and the "
                             "environment (nothing written)")
    snap.check(" (during the freeze)")
    try:
        write_text(text, f)
        back = read_frozen_all(study_dir)
        if (back.roles, back.blobs, back.inputs, back.env) != want:
            raise AssertionError("FINALISTS.md does not read back as written")
        write_text(f"{sha256_of(f)}  {FINALISTS_MD}\n", h)
        if study_dir.resolve() == Path(M.STUDY_DIR).resolve() and not M.frozen():
            raise AssertionError("the guard does not see FINALISTS.md as frozen")
    except BaseException:
        for x in (h, f):
            try:
                x.unlink()
            except FileNotFoundError:
                pass
        raise
    log(f"wrote {f} and {h.name} (sha256 {sha256_of(f)}; git hash-object agrees: {git_ok})")
    return f


def _git_blobs_agree(blobs: Dict[str, str]) -> Optional[bool]:
    """``git hash-object`` of the code files against ``blobs`` (a read-only git command); None without git."""
    import subprocess
    files = [f for f in [DRIVER] + list(RUN_CODE) + port_files() + list(REPORT_CODE) if (REPO_ROOT / f).exists()]
    try:
        got = subprocess.run(["git", "hash-object", "--", *files], cwd=REPO_ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return None
    mine = {"blob " + Path(f).name: h for f, h in zip(files, got)}
    return all(blobs.get(k) == v for k, v in mine.items())


# ───────────────────────────── windows ─────────────────────────────

# the comparison page's common windows (COMPARE DATA CONTRACT v1); 'new' and '8y' start before 2019, so they are
# gold's only (BTC is never scored before 2019-01-01, PREREG 3; gold's start overlaps the Early window: frozen only)
COMMON_WINDOWS = {"5y": ("2021-11-13", "2026-11-13"), "8y": ("2018-11-13", "2026-11-13"),
                  "new": ("2018-11-13", "2021-01-01"), "1y": ("2025-11-13", "2026-11-13")}
GOLD_ONLY = ("8y", "new", "early")


def span(name: str, symbol: str) -> Tuple[str, str]:
    """(start, end) of a study window (M.WINDOWS: dev, val, devval, holdout, full, early) or of a common window of
    the comparison page (COMMON_WINDOWS), ISO, end exclusive."""
    if name in COMMON_WINDOWS:
        if name in GOLD_ONLY and symbol != M.GOLD:
            raise ValueError(f"{name}: gold's only (BTC is never scored before 2019-01-01, PREREG 3)")
        return COMMON_WINDOWS[name]
    return M.window_span(name, symbol)


def applies(name: str, symbol: str) -> bool:
    return symbol == M.GOLD or name not in GOLD_ONLY


def exam_windows(symbol: str) -> Tuple[str, ...]:
    """PREREG 7: exam 1 is the hold-out; a gold champion also takes exam 2 on the Early window."""
    return ("holdout", "early") if symbol == M.GOLD else ("holdout",)


# ───────────────────────────── the exam (PREREG 7) ─────────────────────────────

class FrozenInputsError(RuntimeError):
    """A file FINALISTS.md was frozen from is missing or differs from the sha256 FINALISTS.md records."""


def _require_frozen(study_dir: Path) -> None:
    """The hold-out and the Early window are computed only into the folder whose FINALISTS.md the guard reads, and
    only once it is frozen (``tradeiq2_market.frozen``)."""
    if Path(study_dir).resolve() != Path(M.STUDY_DIR).resolve():
        raise ValueError(f"{study_dir}: the exams are written only to the study folder the guard reads ({M.STUDY_DIR})")
    if not M.frozen():
        raise M.HoldOutError(f"{Path(study_dir) / FINALISTS_MD} with a matching sha256 does not exist: run `freeze` "
                             "first")


def exam_rule(net, profit_dd) -> np.ndarray:
    """PREREG 7's pass rule: net > 0 at x1.0 and profit / max drawdown >= 0.5 (one that does not exist: no pass)."""
    return T1.exam_rule(net, profit_dd)


VOID = "void (look-ahead)"


def verdict_of(symbol: str, holdout_pass: bool, early_pass: Optional[bool]) -> str:
    """PREREG 7: gold 'passes both' / 'passes the hold-out only' / 'passes Early only' / 'fails'; BTC 'pass' / 'fail'."""
    if symbol == M.GOLD:
        h, e = bool(holdout_pass), bool(early_pass)
        return "passes both" if h and e else ("passes the hold-out only" if h else
                                               ("passes Early only" if e else "fails"))
    return "pass" if holdout_pass else "fail"


def _as_str_frame(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """The CSV text of ``df`` in ``columns``, read back as strings: what results_*.csv would hold for these rows."""
    text = df.reindex(columns=list(columns)).to_csv(index=False)
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def _vmap(pairs) -> Dict[str, Tuple[str, M.Variant]]:
    return {v.id: (k, v) for k, v in pairs}


def looks_ahead(vid: str) -> bool:
    """A row that looks ahead by design (LOOKAHEAD_TOKENS: HP-DRAWN, information only)."""
    return any(t in LOOKAHEAD_TOKENS for t in id_tokens(vid)[2:])


def _with_bh(ex: pd.DataFrame, bh: pd.DataFrame) -> pd.DataFrame:
    """Buy-and-hold of 0.01 lot over each row's window at x1.0 next to it (study 1's DEVIATIONS 28): its net, max
    drawdown and P/DD, its exam rule, whether the row's P/DD is above it, and the exposure-matched buy-and-hold (the
    row's time in the market x buy-and-hold's net) with whether the row's net is above that."""
    b = bh[bh.cost == 1.0].set_index(["symbol", "window"])
    out = ex.copy()
    for c in ("bh_net", "bh_max_dd", "bh_profit_dd"):
        out[c] = [float(b.loc[(s, w), c]) if (s, w) in b.index else np.nan for s, w in zip(ex.symbol, ex.window)]
    out["bh_exam_rule"] = exam_rule(out.bh_net, out.bh_profit_dd)
    with np.errstate(invalid="ignore"):
        out["pdd_above_bh"] = np.where(np.isfinite(out.profit_dd) & np.isfinite(out.bh_profit_dd),
                                       out.profit_dd > out.bh_profit_dd, False)
        out["bh_exposure_matched_net"] = out.time_in_mkt.astype(float) * out.bh_net
        out["net_above_exposure_matched"] = np.where(np.isfinite(out.bh_exposure_matched_net),
                                                     out.net > out.bh_exposure_matched_net, False)
    out["edge_over_bh"] = out["pass"] & out.pdd_above_bh
    return out


def frozen_inputs_check(study_dir: Path, fz: "Frozen") -> List[str]:
    """The files FINALISTS.md was frozen from against the sha256 it records: the problems (none: an empty list)."""
    if not fz.inputs:
        return ["FINALISTS.md records no sha256 of its inputs"]
    out = []
    for name, sha in fz.inputs.items():
        p = Path(study_dir) / name
        if not p.exists():
            out.append(f"{name} is missing")
        elif sha256_of(p) != sha:
            out.append(f"{name} differs from the file FINALISTS.md was frozen from")
    return out


def frozen_code_check(fz: "Frozen", snap: CodeSnapshot, allow_code_change: bool, what: str, log=print
                      ) -> Tuple[List[str], List[str]]:
    """The result code against FINALISTS.md's blob ids (the driver's and the report code's are recorded, not
    required): (the files that differ, the environment entries that differ). Different result code raises
    CodeChangedError unless ``allow_code_change`` (then it is recorded); a different environment is a warning (the
    look-ahead checks then show whether a number moved)."""
    changed = code_changes(fz.blobs, snap.blobs, snap.result_keys())
    if changed and not allow_code_change:
        raise CodeChangedError(f"{what}: {', '.join(changed)} differ from the code FINALISTS.md records. Restore the "
                               "frozen code, or pass --allow-code-change to compute with this code (recorded in "
                               "exam_info.csv and EXAM.md)")
    if changed:
        log(f"WARNING: {what} with result code other than FINALISTS.md's ({', '.join(changed)}), as allowed")
    env_changed = [k[4:] for k, v in snap.env.items() if k in fz.env and fz.env[k] != v]
    if env_changed:
        log(f"WARNING: {what}: the environment differs from FINALISTS.md's ({', '.join(env_changed)})")
    return changed, env_changed


def _exam_of_record(study_dir: Path, snap: CodeSnapshot) -> None:
    """exam.csv is never overwritten by a run with other result code than the one that wrote it (exam_info.csv)."""
    p = Path(study_dir) / "exam_info.csv"
    if not p.exists():
        return
    inf = pd.read_csv(p, dtype=str, keep_default_na=False)
    if not len(inf):
        return
    rec = {c: str(inf[c].iloc[0]) for c in inf.columns if c.startswith("blob ")}
    diff = code_changes(rec, snap.blobs, snap.result_keys())
    if diff:
        raise FileExistsError(f"exam.csv was computed with other result code ({', '.join(diff)}; exam_info.csv): the "
                              "exam of record is never overwritten. Move exam*.csv, EXAM.md, results_holdout.csv, "
                              "results_early.csv and base_rate.csv aside to compute it again")


def exam(study_dir: Optional[Path] = None, modules: Optional[Mapping[str, object]] = None,
         counts: Optional[Sequence[Count]] = None, workers: int = 2, loader=None, base_rate: bool = True,
         recheck: bool = True, allow_code_change: bool = False, log=print) -> Dict[str, pd.DataFrame]:
    """
    PREREG 7's exam, only once FINALISTS.md is frozen, with the inputs FINALISTS.md records (their sha256) and its
    result code (``allow_code_change``: other code, recorded). (1) Every champion of FINALISTS.md over the hold-out
    and, for gold, the Early window, at x1.0 and x1.5, and over the full span (for the accounts); its Development,
    Validation and D+V rows computed again on the data to the data end must equal results_dev_val.csv's text (no
    look-ahead; a champion that fails gets the verdict 'void (look-ahead)' and the exam raises after writing); the
    verdicts; buy-and-hold beside them (every symbol) -> exam.csv, exam_full.csv, exam_trades.csv.gz,
    exam_buy_and_hold.csv, exam_info.csv, exam_checks.csv. (2) The base rate: every variant over the same windows
    (and, with ``recheck``, Development, Validation and D+V again: every variant's look-ahead check, as study 1's
    ``holdout``) -> results_holdout.csv, results_early.csv, results_recheck_dev_val.csv, trades_holdout.csv.gz,
    trades_early.csv.gz, base_rate.csv; the champions' rows there must equal exam.csv's. multiple_testing.csv
    again; EXAM.md.
    """
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    modules = find_modules() if modules is None else dict(modules)
    _refuse_test_options(study_dir, "exam", modules, counts, loader)
    _require_frozen(study_dir)
    fz = read_frozen_all(study_dir)
    moved = frozen_inputs_check(study_dir, fz)
    if moved:
        raise FrozenInputsError("exam: " + "; ".join(moved) + " (FINALISTS.md's sha256): restore the frozen files")
    roles = fz.roles
    grid = read_grid(study_dir)
    res = read_results(study_dir)
    check_complete(res, grid)
    qual = qualification(res)
    if roles != champions_in_order(qual):
        raise AssertionError("FINALISTS.md's champions are not those results_dev_val.csv gives")
    snap = CodeSnapshot.take(modules)
    g2, pairs = checked_grid(modules, counts)
    if not _grid_matches(grid, g2):
        raise GridError("grid.csv is not the rule modules' grid now")
    changed, env_changed = frozen_code_check(fz, snap, allow_code_change, "exam", log)
    _exam_of_record(study_dir, snap)
    vm = _vmap(pairs)
    loader_fn = loader or _load_default
    q = qual.set_index("vid")
    ref = pd.read_csv(study_dir / "results_dev_val.csv", dtype=str, keep_default_na=False)
    rcols = list(ref.columns)
    ref = ref.set_index(["vid", "window"])
    rows, full_rows, trd, bh, info, checks = [], [], [], [], [], []
    for s in SYMBOLS:
        mine = [(role, vid) for role, vid in roles if q.loc[vid, "symbol"] == s]
        t0 = time.time()
        mk = loader_fn(s, None)
        if mine:
            ctx = M.Context(mk)
            ws = RUN_WINDOWS + ("holdout", "full") + (("early",) if s == M.GOLD else ())
            for role, vid in mine:
                key, v = vm[vid]
                ex = modules[key].build(v, ctx)
                r = M.run_variant(ctx, v, ex, windows=ws, costs=COSTS, trades_windows=exam_windows(s))
                shape = exec_shape(ex)
                rr = [_row_of(key, x, shape) for x in r.rows]
                extra_cols = {"role": role, "champion_rank": int(q.loc[vid, "champion_rank"])}
                rows += [{**x, **extra_cols} for x in rr if x["window"] in exam_windows(s)]
                full_rows += [{**x, **extra_cols} for x in rr if x["window"] == "full"]
                again = _as_str_frame(pd.DataFrame([x for x in rr if x["window"] in RUN_WINDOWS]), rcols)
                want = ref.loc[[(vid, w) for w in RUN_WINDOWS]].reset_index()[rcols]
                same = bool(again.shape == want.shape and (again.values == want.values).all())
                checks.append({"check": "D, V and D+V again on the data to the data end equal results_dev_val.csv's "
                                        "text", "vid": vid, "result": same,
                               "differs": "" if same else ", ".join(
                                   sorted({c for c in rcols if not (again[c].values == want[c].values).all()}))})
                if len(r.trades):
                    trd.append(r.trades)
                ctx.cache.clear()
            del ctx
        bh += bh_rows(mk, ("holdout", "full") + (("early",) if s == M.GOLD else ()))
        info.append({**data_identity(mk, binance=loader is None), "champions": len(mine),
                     "seconds": round(time.time() - t0, 1)})
        del mk
        gc.collect()
    snap.check(" (during the exam)")
    bhf = pd.DataFrame(bh, columns=list(BH_COLS))
    failed = {c["vid"] for c in checks if not c["result"]}
    ex = pd.DataFrame(rows)
    if len(ex):
        ex["pass"] = exam_rule(ex.net, ex.profit_dd)
        ex["pass_x15"] = exam_rule(ex.net_x15, ex.profit_dd_x15)               # for information
        ex = _with_bh(ex, bhf)
        verdict = {}
        for vid, g in ex.groupby("vid", sort=False):
            p = dict(zip(g.window, g["pass"]))
            verdict[vid] = VOID if vid in failed else verdict_of(g.symbol.iloc[0], p.get("holdout", False),
                                                                 p.get("early"))
        ex["verdict"] = ex.vid.map(verdict)
        ex["lookahead_ok"] = ~ex.vid.isin(failed)
        ex["note"] = [legs_note(x) for x in ex.legs]
        lead = list(IDENT_COLS) + ["role", "champion_rank", "window"]
        ex = ex[lead + [c for c in ex.columns if c not in lead]]
    inf = pd.DataFrame(info)
    inf["written_utc"] = _now()
    inf["finalists_sha256"] = sha256_of(study_dir / FINALISTS_MD)
    for k, v in {**snap.env, **snap.blobs}.items():
        inf[k] = v
    inf["code_as_frozen"] = not changed
    inf["code_changed"] = ", ".join(changed)
    inf["env_changed"] = ", ".join(env_changed)
    write_csv(ex, study_dir / "exam.csv")
    write_csv(pd.DataFrame(full_rows), study_dir / "exam_full.csv")
    write_csv(pd.concat(trd, ignore_index=True).reindex(columns=list(TRADE_COLS)) if trd else
              pd.DataFrame(columns=list(TRADE_COLS)), study_dir / "exam_trades.csv.gz")
    write_csv(bhf, study_dir / "exam_buy_and_hold.csv")
    write_csv(inf, study_dir / "exam_info.csv")
    write_csv(pd.DataFrame(checks, columns=["check", "vid", "result", "differs"]), study_dir / "exam_checks.csv")
    write_text(exam_md(study_dir), study_dir / "EXAM.md")
    log(f"exam: {len(set(ex.vid)) if len(ex) else 0} champions examined -> {study_dir / 'exam.csv'}")
    if failed:
        raise AssertionError(f"look-ahead: the Development / Validation rows of {', '.join(sorted(failed))} changed on "
                             "the data to the data end (exam_checks.csv); their verdicts are void")
    got = {"exam": ex}
    if base_rate:
        got.update(exam_base_rate(study_dir, pairs, modules, qual, workers=workers, loader=loader, log=log,
                                  recheck=recheck, snap=snap))
    weekly = pd.read_csv(study_dir / "weekly_dev_val.csv.gz", float_precision="round_trip")
    write_csv(multiple_testing(res, weekly, qual), study_dir / "multiple_testing.csv")
    write_text(exam_md(study_dir), study_dir / "EXAM.md")
    return got


BASE_SETS = ("all rows", "all eligible rows", "qualifiers", "champions", "finalists",
             "not-eligible and information rows")


def base_rate_table(ho: pd.DataFrame, early: pd.DataFrame, qual: pd.DataFrame, bh: pd.DataFrame) -> pd.DataFrame:
    """PREREG 7's base rate: per symbol and window (gold also 'both'), the share of each set of rows that passes the
    exam's rule (BASE_SETS: 'all rows' = what share of all variants would have passed, PREREG 7's words); buy-and-hold
    beside them; the claim-check rows of the claim markets over the hold-out, for information."""
    rows = []
    b1 = bh[bh.cost == 1.0].set_index(["symbol", "window"]) if len(bh) else None

    def bh_row(s, w):
        if b1 is not None and (s, w) in b1.index:
            p = bool(exam_rule(b1.loc[(s, w), "bh_net"], b1.loc[(s, w), "bh_profit_dd"]))
            rows.append({"symbol": s, "window": w, "rows": "buy-and-hold", "n": 1, "pass": int(p), "share": float(p)})

    for s in SYMBOLS:
        qs = qual[qual.symbol == s]
        sets = dict(zip(BASE_SETS, (qs.vid, qs[qs.eligible].vid, qs[qs.qualifies].vid, qs[qs.champion].vid,
                                    qs[qs.finalist].vid, qs[~qs.eligible].vid)))
        oks = {}
        for w, df in (("holdout", ho), ("early", early)):
            if w == "early" and s != M.GOLD:
                continue
            d = df[df.symbol == s].set_index("vid") if len(df) else pd.DataFrame()
            if not len(d):
                continue
            oks[w] = pd.Series(exam_rule(d.net, d.profit_dd), index=d.index)
        if "holdout" in oks and "early" in oks:
            oks["both"] = oks["holdout"] & oks["early"].reindex(oks["holdout"].index).fillna(False).astype(bool)
        for w, ok in oks.items():
            for name, ids in sets.items():
                ids = [x for x in ids if x in ok.index]
                rows.append({"symbol": s, "window": w, "rows": name, "n": len(ids), "pass": int(ok.loc[ids].sum()),
                             "share": float(ok.loc[ids].mean()) if ids else np.nan})
            if w != "both":
                bh_row(s, w)
    for s in CLAIM_SYMBOLS:
        d = ho[ho.symbol == s].set_index("vid") if len(ho) else pd.DataFrame()
        if not len(d):
            continue
        ok = exam_rule(d.net, d.profit_dd)
        rows.append({"symbol": s, "window": "holdout", "rows": "claim-check rows (information)", "n": int(len(d)),
                     "pass": int(ok.sum()), "share": float(ok.mean())})
        bh_row(s, "holdout")
    return pd.DataFrame(rows, columns=["symbol", "window", "rows", "n", "pass", "share"])


def recheck_rows(study_dir: Path, grid: pd.DataFrame, name: str = "results_recheck_dev_val.csv") -> Dict[str, object]:
    """Every variant's Development, Validation and D+V rows as the exam's base-rate job computed them on the data to
    the data end, against results_dev_val.csv, text for text (study 1's ``holdout`` check); rows that look ahead by
    design (HP-DRAWN) are left out."""
    a = pd.read_csv(Path(study_dir) / "results_dev_val.csv", dtype=str, keep_default_na=False)
    b = pd.read_csv(Path(study_dir) / name, dtype=str, keep_default_na=False)
    if list(a.columns) != list(b.columns):
        return {"result": False, "differs": f"the columns differ: {sorted(set(a.columns) ^ set(b.columns))[:10]}",
                "checked": 0, "left_out": 0}
    keep = [v for v in grid.vid if not looks_ahead(v)]
    ai = a.set_index(["vid", "window"])
    bi = b.set_index(["vid", "window"])
    idx = [(v, w) for v in keep for w in RUN_WINDOWS]
    lack = [x for x in idx if x not in bi.index]
    if lack:
        return {"result": False, "differs": f"{len(lack)} rows missing, e.g. {lack[:3]}", "checked": 0,
                "left_out": len(grid) - len(keep)}
    av, bv = ai.loc[idx].to_numpy(), bi.loc[idx].to_numpy()
    bad = sorted({idx[i][0] for i in np.flatnonzero((av != bv).any(axis=1))})
    return {"result": not bad, "differs": ", ".join(bad[:20]) + (" ..." if len(bad) > 20 else ""),
            "checked": len(keep), "left_out": len(grid) - len(keep)}


def exam_base_rate(study_dir: Path, pairs, modules, qual: pd.DataFrame, workers: int = 2, loader=None, log=print,
                   recheck: bool = True, snap: Optional[CodeSnapshot] = None) -> Dict[str, pd.DataFrame]:
    """(2) of ``exam``: every variant over the hold-out (and gold's Early window) and, with ``recheck``,
    Development, Validation and D+V again (every variant's look-ahead check), resumable like ``run``."""
    _require_frozen(study_dir)
    study_dir = Path(study_dir)
    snap = snap or CodeSnapshot.take(modules)
    t0 = time.time()
    windows_of = (lambda s: RUN_WINDOWS + exam_windows(s)) if recheck else exam_windows
    stats = score_job(study_dir, EXAMJOB, pairs, modules, windows_of, exam_windows, None, workers=workers,
                      loader=loader, log=log, snap=snap)
    snap.check(" (before the base rate's CSVs were assembled)")
    results = {"results_holdout.csv": ("holdout",), "results_early.csv": ("early",)}
    if recheck:
        results["results_recheck_dev_val.csv"] = RUN_WINDOWS
    got = assemble_scores(study_dir, EXAMJOB, pairs, modules, windows_of, exam_windows, results=results,
                          trades={"trades_holdout.csv.gz": ("holdout",), "trades_early.csv.gz": ("early",)}, log=log,
                          snap=snap)
    if got["missing"]:
        raise RunError(f"the base rate lacks {len(got['missing'])} variants: run `exam` again")
    ho = read_results(study_dir, "results_holdout.csv")
    ea = read_results(study_dir, "results_early.csv")
    bh = pd.read_csv(study_dir / "exam_buy_and_hold.csv", float_precision="round_trip")
    claim_bh = [r for s, j in _market_jsons(study_dir, EXAMJOB).items() if s in CLAIM_SYMBOLS
                for r in j.get("bh", []) if r.get("window") == "holdout"]
    if claim_bh:
        bh = pd.concat([bh, pd.DataFrame(claim_bh, columns=list(BH_COLS))], ignore_index=True)
    br = base_rate_table(ho, ea, qual, bh)
    write_csv(br, study_dir / "base_rate.csv")
    ex = (pd.read_csv(study_dir / "exam.csv", dtype=str, keep_default_na=False)
          if (study_dir / "exam.csv").stat().st_size > 1 else pd.DataFrame(columns=["vid", "window"]))
    chk = pd.read_csv(study_dir / "exam_checks.csv", dtype=str, keep_default_na=False) \
        if (study_dir / "exam_checks.csv").stat().st_size > 1 else \
        pd.DataFrame(columns=["check", "vid", "result", "differs"])
    chk = chk[~chk.check.str.startswith("the champions' rows of") & ~chk.check.str.startswith("every variant's")]
    same = []
    for w, df in (("holdout", "results_holdout.csv"), ("early", "results_early.csv")):
        e = ex[ex.window == w]
        if not len(e):
            continue
        allr = pd.read_csv(study_dir / df, dtype=str, keep_default_na=False).set_index("vid")
        cols = [c for c in allr.columns if c in e.columns and c != "vid"]
        a = allr.loc[e.vid, cols].reset_index(drop=True)
        b = e[cols].reset_index(drop=True)
        same.append(bool(a.shape == b.shape and (a.values == b.values).all()))
    new = [{"check": "the champions' rows of results_holdout.csv / results_early.csv equal exam.csv", "vid": "",
            "result": all(same), "differs": ""}]
    rc = None
    if recheck:
        rc = recheck_rows(study_dir, read_grid(study_dir))
        new.append({"check": f"every variant's D, V and D+V again on the data to the data end equal "
                             f"results_dev_val.csv's text ({rc['checked']} variants; {rc['left_out']} that look ahead "
                             "by design left out)", "vid": "", "result": rc["result"], "differs": rc["differs"]})
    chk = pd.concat([chk, pd.DataFrame(new)], ignore_index=True)
    write_csv(chk, study_dir / "exam_checks.csv")
    write_text(exam_md(study_dir), study_dir / "EXAM.md")
    log(f"base rate: {stats['computed']} computed, {stats['skipped']} complete ({time.time() - t0:.0f} s)")
    if not all(same):
        raise AssertionError("the champions' base-rate rows differ from exam.csv (exam_checks.csv)")
    if rc is not None and not rc["result"]:
        raise AssertionError(f"look-ahead: Development / Validation rows changed on the data to the data end for "
                             f"{rc['differs']} (exam_checks.csv)")
    return {"results_holdout": ho, "results_early": ea, "base_rate": br}


def exam_md(study_dir: Path) -> str:
    """EXAM.md from exam.csv, exam_buy_and_hold.csv, exam_info.csv, exam_checks.csv and, once they exist,
    base_rate.csv and multiple_testing.csv."""
    study_dir = Path(study_dir)
    ex = read_results(study_dir, "exam.csv") if (study_dir / "exam.csv").stat().st_size > 1 else pd.DataFrame()
    inf = pd.read_csv(study_dir / "exam_info.csv", keep_default_na=False)
    chk = (pd.read_csv(study_dir / "exam_checks.csv", keep_default_na=False) if (study_dir / "exam_checks.csv").exists()
           and (study_dir / "exam_checks.csv").stat().st_size > 1 else pd.DataFrame())
    i0 = inf.iloc[0] if len(inf) else None
    out = ["# TradeIQ's 9 indicators for 2027: the exam (PREREG 7)", ""]
    if i0 is not None:
        as_frozen = _bool(i0.code_as_frozen)
        out += [f"Computed by `python -B -m backtesting.research.tradeiq2 exam` on {i0.written_utc} (UTC), after "
                f"`FINALISTS.md` was frozen (sha256 `{i0.finalists_sha256}`). The result code is "
                + ("the code FINALISTS.md records." if as_frozen else
                   f"**not** the code FINALISTS.md records ({i0.get('code_changed', '')}; `--allow-code-change`): see "
                   "`exam_info.csv`.")
                + (f" The environment differs from FINALISTS.md's: {i0.get('env_changed')}."
                   if str(i0.get("env_changed", "")) else "")
                + " Per 0.01 lot after Exness costs, one continuous run per champion and window that starts flat "
                  "at its first bar.", ""]
    out += ["**The rule (PREREG 7): a champion passes an exam when its net profit there is above 0 at x1.0 and its "
            "profit / max drawdown is at least 0.5.** Exam 1 is the hold-out (2024-07-01 to the data end); a gold "
            "champion also takes exam 2 on the Early window (2017-01-01 to 2018-12-31). x1.5 is information. A "
            f"champion whose Development or Validation rows change on the data to the data end gets the verdict "
            f"'{VOID}'.", "", "## The verdicts", ""]
    if not len(ex):
        out += ["No champion: no exam.", ""]
    else:
        rows = []
        for _, r in ex.iterrows():
            rows.append([NAME[r.symbol], r.role, r.family, _short(r.vid), r.window, _usd(r.net), _usd(r.net_x15),
                         _dd(r.max_dd), _num(r.profit_dd), int(r.trades), _num(r.profit_factor),
                         f"{int(r.pos_q)}/{int(r.n_q)}", "**PASS**" if _bool(r["pass"]) else "**FAIL**",
                         _usd(r.bh_net), _num(r.bh_profit_dd), _usd(r.bh_exposure_matched_net), r.verdict,
                         legs_note(r.get("legs", 1))])
        out += [_md(["Symbol", "Role", "Family", "Champion", "Exam", "Net x1.0", "Net x1.5", "Max DD", "Profit / DD",
                     "Trades", "Profit factor", "Positive quarters", "Result", "B&H net", "B&H P/DD",
                     "B&H exposure-matched", "Verdict", "Note"], rows), ""]
        for s in SYMBOLS:
            g = ex[ex.symbol == s].drop_duplicates("vid")
            if len(g):
                counts = g.verdict.value_counts()
                out.append(f"- {NAME[s]}: {len(g)} champions; " + ", ".join(f"{k}: {int(v)}" for k, v in
                                                                             counts.items()) + ".")
        out += ["", "A pass counts as evidence of an edge over holding the market only if the champion's profit / "
                "max drawdown is also above buy-and-hold's over the same span (study 1's DEVIATIONS 28; "
                "`edge_over_bh` in `exam.csv`); the exposure-matched buy-and-hold is the champion's time in the market "
                "x buy-and-hold's net (`net_above_exposure_matched`).", ""]
    if (study_dir / "base_rate.csv").exists():
        br = pd.read_csv(study_dir / "base_rate.csv")
        rows = [[NAME.get(r.symbol, r.symbol), r.window, r.rows, f"{int(r['pass'])}/{int(r.n)}", _pct(r.share)]
                for _, r in br.iterrows()]
        out += ["## The base rate (PREREG 7, information)", "",
                "The same exam computed for every variant after the verdicts: the share of each set that passes "
                "('all rows' = every variant of the symbol, the share PREREG 7 asks for).", "",
                _md(["Symbol", "Window", "Rows", "Pass", "Share"], rows), ""]
    if (study_dir / "multiple_testing.csv").exists() and (study_dir / "multiple_testing.csv").stat().st_size > 1:
        mt = pd.read_csv(study_dir / "multiple_testing.csv")
        if len(mt):
            out += ["## Multiple testing (Development weekly P/L; PREREG 7)", "",
                    _md(["Universe", "Symbol", "Role", "Variant", "N", "DSR", "SPA p", "Reality Check p"],
                        [[r.universe, NAME[r.symbol], r.role, _short(r.vid), int(r.N), _num(r.dsr, 3),
                          _num(r.spa_p, 3), _num(r.rc_p, 3)] for _, r in mt.iterrows()]), ""]
    if len(chk):
        out += ["## Checks", "", _md(["Check", "Variant", "Result", "Differs"],
                                     [[r.check, f"`{r.vid}`" if isinstance(r.vid, str) and r.vid else "", r.result,
                                       r.differs if isinstance(r.get("differs", ""), str) else ""]
                                      for _, r in chk.iterrows()]), ""]
    out += ["## Files", "", "`exam.csv` (the champions' exam rows at x1.0 and `_x15`, the result, buy-and-hold, the "
            "verdict), `exam_full.csv` (their full span), `exam_trades.csv.gz`, `exam_buy_and_hold.csv`, "
            "`exam_info.csv`, `exam_checks.csv`, `results_holdout.csv`, `results_early.csv`, "
            "`results_recheck_dev_val.csv`, `trades_holdout.csv.gz`, `trades_early.csv.gz`, `base_rate.csv`, "
            "`multiple_testing.csv`.", ""]
    return "\n".join(out)


# ───────────────────────────── the accounts and the comparison page's files ─────────────────────────────

SERIES_COLS = ("series_id", "source", "study", "symbol", "label", "kind", "family", "tf", "filter", "role", "eligible",
               "exam", "notes")
METRIC_COLS = ("series_id", "window", "start", "end", "cost", "basis", "start_usd", "final_usd", "net_usd",
               "return_pct", "cagr_pct", "max_dd_usd", "max_dd_pct", "p_dd", "trades", "win_rate_pct", "profit_factor",
               "sharpe_w", "pos_quarters_pct", "worst_quarter_usd", "wiped", "dd_marks", "score_final10",
               "source_file")
CURVE_COLS = ("series_id", "date", "equity_usd")
ROLES = ("design", "base", "finalist", "champion", "qualified", "variant", "benchmark")
KINDS = ("bot", "bot+filter", "rule", "benchmark")
DD_MARKS = ("tick", "second", "M1", "hour", "day")
SOURCE_FILE = "backtesting/research/tradeiq2.py accounts"
# PREREG 7's accounts: the champions, finalists and each family's best row over 2019-01-01 to the data end and over
# the hold-out (gold: also the Early window), at both costs; every variant over the comparison page's common windows
# (5y and 1y on both symbols, 8y and new on gold: they start before 2019), at x1.0. (window, which rows: 'focus' or
# 'all', costs)
ACCOUNT_PLAN: Tuple[Tuple[str, str, Tuple[float, ...]], ...] = (
    ("full", "focus", COSTS), ("holdout", "focus", COSTS), ("early", "focus", COSTS),
    ("5y", "all", (1.0,)), ("8y", "all", (1.0,)), ("1y", "all", (1.0,)), ("new", "all", (1.0,)))


def series_id(vid: str, sid: str = SID) -> str:
    return f"{sid}:{vid}"


def _sizing(r: M.Run2):
    """The account of ``M.account_curve(r)`` trade by trade: the same kernel on the same inputs (``external``'s for
    one position at a time, ``balke``'s for legs and lanes), returning per trade of the account (a leg-trade for
    legs / lanes) its units and USD P/L, the trades themselves (sorted by entry, with the position each belongs
    to), the final equity, the max drawdown as a fraction of the running peak, and the wipe-out."""
    from . import balke as B
    cm = r.m
    e = TM._edges_days(r.a_s, r.z_s)
    bnd = np.concatenate([[r.ia], r.ia + np.searchsorted(cm.t[r.ia:r.iz], e[1:-1], side="left"), [r.iz]])
    inner = np.asarray(bnd[1:-1], np.int64)
    if r.single:
        p = r.path
        steps, pnl, bal, dd, wiped, wix, n_done, _ = X._account_kernel(
            cm.t, cm.o, cm.h, cm.l, cm.c, cm.sp, cm.k, p.dir, p.eix, p.epx, p.xix, p.xpx, p.why, p.risk, p.expo,
            p.leg0, p.nleg, p.leix, p.lepx, 0, 0.0, 0.0, False, inner, X._YEARS, X.ACCOUNT, X.STEP_UP,
            float(X.UNIT_MAX))
        n = len(p)
        flat = {"dir": p.dir.astype(np.int64), "eix": p.eix.astype(np.int64), "epx": p.epx.astype(np.float64),
                "xix": p.xix.astype(np.int64), "xpx": p.xpx.astype(np.float64), "why": p.why.astype(np.int64),
                "w": np.ones(n), "owner": np.arange(n, dtype=np.int64)}
    else:
        lanes = r.lanes if r.lanes else (r,)
        parts, owners = [], []
        for q, lr in enumerate(lanes):
            for wt, pth in lr.legs:
                parts.append((wt, pth))
                owners.append(q * 10**9 + np.arange(len(pth), dtype=np.int64))
        cols = {k: np.concatenate([getattr(pth, k) for _, pth in parts]) for k in
                ("dir", "eix", "epx", "xix", "xpx", "why", "risk")}
        cols["w"] = np.concatenate([np.full(len(pth), wt) for wt, pth in parts])
        cols["owner"] = np.concatenate(owners)
        order = np.argsort(cols["eix"], kind="stable")               # M._flat_trades' order
        flat = {k: v[order] for k, v in cols.items()}
        w = np.unique(flat["w"]) if len(flat["w"]) else np.ones(1)
        if len(w) != 1:
            raise ValueError(f"legs of unequal weights {list(w)}")
        for k in ("dir", "eix", "xix", "why"):
            flat[k] = flat[k].astype(np.int64)
        steps, pnl, bal, dd, wiped, wix, n_done, _ = B._multi_kernel(
            cm.c, cm.h, cm.l, cm.sp, float(cm.k) * float(w[0]), flat["eix"], flat["epx"].astype(np.float64),
            flat["xix"], flat["xpx"].astype(np.float64), flat["why"], flat["dir"],
            flat["risk"].astype(np.float64), np.full(len(flat["eix"]), np.nan), 0, 0.0, int(r.ia), int(r.iz), inner,
            X.ACCOUNT, X.STEP_UP, float(X.UNIT_MAX))
    return np.asarray(steps, np.float64), np.asarray(pnl, np.float64), flat, float(bal), float(dd), bool(wiped), \
        int(wix), int(n_done)


def _usd_dd(r: M.Run2, flat: Dict[str, np.ndarray], steps: np.ndarray, final: float, wiped: bool, wix: int) -> float:
    """The account's max drawdown in USD on the M1 marks: the trades weighted by their units (``M._sum_marks``, the
    event order of both account kernels). Checked against the account's final equity; after a wipe-out the
    drawdown is the peak before it (the equity falls to 0)."""
    cm = r.m
    iz = int(r.iz) if not wiped else max(int(wix), int(r.ia) + 1)
    w = flat["w"] * steps
    ec, ew, pos, bal, maxdd = M._sum_marks(cm.c, cm.h, cm.l, cm.sp, float(cm.k), flat["dir"], w.astype(np.float64),
                                           flat["eix"], flat["xix"], flat["epx"].astype(np.float64),
                                           flat["xpx"].astype(np.float64), flat["why"], int(r.ia), iz)
    if not wiped:
        if abs(X.ACCOUNT + float(bal) - final) > 1e-6 * max(1.0, abs(final)):
            raise AssertionError(f"the sized marks end at {X.ACCOUNT + bal:.6f}, the account at {final:.6f}")
        return float(maxdd)
    return float(X.ACCOUNT + max(0.0, float(np.max(ec)) if len(ec) else 0.0))


def _at(curve_t: np.ndarray, eq: np.ndarray, T: np.ndarray) -> np.ndarray:
    k = np.searchsorted(curve_t, T)
    if np.any(k >= len(curve_t)) or np.any(curve_t[np.minimum(k, len(curve_t) - 1)] != T):
        raise AssertionError("an edge is not on the account curve")
    return eq[k]


def _iso_day(day: np.ndarray) -> List[str]:
    return pd.to_datetime(np.asarray(day, np.int64) * M.DAY, unit="s").strftime("%Y-%m-%d").tolist()


def day_marks(r: M.Run2, curve: pd.DataFrame, wiped: bool = False, wix: int = -1) -> pd.DataFrame:
    """The contract's curve (COMPARE DATA CONTRACT v1): the opening row, dated the day before the window starts, at
    the account's $2,000; then per UTC day with an M1 bar in the window, the account's equity at the last mark of
    that day (the close mark, open positions marked): the curve's value at the next midnight (the window's end for
    its last day). A wiped account's curve stops on the day it was wiped (its equity there is 0)."""
    t = r.m.t[r.ia:r.iz]
    days = np.unique(t // M.DAY)
    if wiped and wix >= 0:
        days = days[days <= int(r.m.t[int(wix)] // M.DAY)]
    ct = (curve.time.astype("int64") // 10**9).to_numpy(np.int64)
    nxt = np.minimum((days + 1) * M.DAY, r.z_s)
    eq = _at(ct, curve.equity.to_numpy(np.float64), nxt)
    return pd.DataFrame({"date": _iso_day(np.r_[int(r.a_s // M.DAY) - 1, days]),
                         "equity_usd": np.r_[float(X.ACCOUNT), eq]})


def _sharpe(x: np.ndarray) -> float:
    """mean / sd x sqrt(52) of weekly values; NaN when there are 2 or fewer or they do not vary (the page's
    ``curve_stats`` leaves it blank then)."""
    if len(x) <= 2:
        return np.nan
    sd = float(np.std(x, ddof=1))
    return float(np.mean(x) / sd * math.sqrt(52.0)) if sd > 0 else np.nan


def account_rows(r: M.Run2) -> Tuple[Dict[str, object], Dict[str, object], pd.DataFrame, pd.DataFrame]:
    """One run on the contract's two bases: (account, unit) metric dicts, the study-1 style daily curve (time, equity,
    unit_equity, unit_worst) and the contract's day marks. Account: $2,000 with FINAL10's unit rule
    (``M.account_curve``); unit: 0.01 lot always (``M.scores``). The account's weekly Sharpe is the page's: the weekly
    P/L in $ (equity at Saturday 00:00 UTC, the partial first and last weeks included), mean / sd x sqrt(52)."""
    curve, summ = M.account_curve(r)
    steps, pnl, flat, final, dd, wiped, wix, n_done = _sizing(r)
    if abs(final - float(summ["final"])) > 1e-9 * max(1.0, abs(final)) or abs(dd * 100 - summ["max_dd_pct"]) > 1e-9:
        raise AssertionError("the account trade by trade differs from tradeiq2_market.account_curve")
    usd_dd = _usd_dd(r, flat, steps, final, wiped, wix)
    done = (np.arange(len(steps)) < n_done) & (steps > 0)
    pos = pd.Series(pnl[done]).groupby(flat["owner"][done]).sum().to_numpy(np.float64) if done.any() else np.zeros(0)
    wins, losses = pos[pos > 0], pos[pos < 0]
    years = (r.z_s - r.a_s) / (365.25 * M.DAY)
    net = final - X.ACCOUNT
    ct = (curve.time.astype("int64") // 10**9).to_numpy(np.int64)
    eqc = curve.equity.to_numpy(np.float64)
    wk = np.diff(_at(ct, eqc, TM._edges_weeks(r.a_s, r.z_s)))   # weekly P/L in $ (Saturday 00:00 UTC)
    eq_q = np.diff(_at(ct, eqc, TM._edges_quarters(r.a_s, r.z_s)))
    acc = {"start_usd": X.ACCOUNT, "final_usd": final, "net_usd": net, "return_pct": net / X.ACCOUNT * 100.0,
           "cagr_pct": (((final / X.ACCOUNT) ** (1.0 / years) - 1.0) * 100.0 if final > 0 else -100.0)
           if years > 0 else np.nan,
           "max_dd_usd": usd_dd, "max_dd_pct": dd * 100.0, "p_dd": net / usd_dd if usd_dd > 0 else np.nan,
           "trades": int(len(pos)), "win_rate_pct": 100.0 * len(wins) / len(pos) if len(pos) else np.nan,
           "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else (np.inf if len(wins) else np.nan),
           "sharpe_w": _sharpe(wk), "pos_quarters_pct": 100.0 * float((eq_q > 0).mean()) if len(eq_q) else np.nan,
           "worst_quarter_usd": float(eq_q.min()) if len(eq_q) else np.nan, "wiped": int(wiped),
           "wiped_at": str(TM.utc(r.m.t[int(wix)])) if wiped and wix >= 0 else "",
           "max_units": float(steps[done].max()) if done.any() else 0.0}
    sc = M.scores(r)
    _, qp, _ = TM.quarter_pnl(r)
    unit = {"start_usd": 0.0, "final_usd": sc["net"], "net_usd": sc["net"], "return_pct": np.nan, "cagr_pct": np.nan,
            "max_dd_usd": sc["max_dd"], "max_dd_pct": np.nan, "p_dd": sc["profit_dd"], "trades": sc["trades"],
            "win_rate_pct": sc["win_rate"], "profit_factor": sc["profit_factor"], "sharpe_w": sc["sharpe_w"],
            "pos_quarters_pct": 100.0 * sc["pos_q_share"] if math.isfinite(sc["pos_q_share"]) else np.nan,
            "worst_quarter_usd": float(np.min(qp)) if len(qp) else np.nan, "wiped": 0}
    uc = M.unit_curve(r)
    daily = pd.DataFrame({"time": curve.time, "equity": eqc, "unit_equity": uc.equity.to_numpy(),
                          "unit_worst": uc.worst.to_numpy()})
    return acc, unit, daily, day_marks(r, curve, wiped, wix)


def _accounts(w: _Work, v: M.Variant, stamp: dict) -> dict:
    ex = _build(w, v)
    metrics, curves, daily = [], {}, {}
    for win, a, z, costs in stamp["spans"]:
        for cost in costs:
            r = M.run_exec(w.ctx.mk, ex, a, z, float(cost))
            acc, unit, day, marks = account_rows(r)
            metrics.append({"window": win, "start": a, "end": z, "cost": float(cost), "account": acc, "unit": unit})
            if float(cost) == 1.0:
                curves[win] = marks
                if win in stamp["daily"]:
                    daily[win] = day
    return {"metrics": metrics, "curves": curves, "daily": daily, **exec_shape(ex)}


def _roles(qual: pd.DataFrame) -> Dict[str, str]:
    out = {}
    for r in qual.itertuples(index=False):
        out[r.vid] = ("finalist" if r.finalist else "champion" if r.champion else "qualified" if r.qualifies
                      else "variant")
    return out


def account_plan_of(qual: pd.DataFrame, plan=ACCOUNT_PLAN) -> Dict[str, List[Tuple[str, Tuple[float, ...]]]]:
    """Per gold / BTC variant: the (window, costs) of ``plan`` that apply to it. 'focus' = the champions (finalists
    included) and each family's best row (PREREG 7's accounts); 'all' = every variant but the rows that look ahead by
    design (HP-DRAWN: information only, never on the page); gold-only windows skip BTC."""
    focus = set(qual[qual.champion].vid) | set(family_best(qual).vid)
    out: Dict[str, List[Tuple[str, Tuple[float, ...]]]] = {}
    for r in qual.itertuples(index=False):
        if r.symbol not in SYMBOLS:
            continue
        for win, which, costs in plan:
            if not applies(win, r.symbol) or (which == "focus" and r.vid not in focus):
                continue
            if which == "all" and r.vid not in focus and looks_ahead(r.vid):
                continue
            out.setdefault(r.vid, []).append((win, tuple(float(c) for c in costs)))
    return out


def _as_run2(r: TM.Run) -> M.Run2:
    """A study-1 ``Run`` (one position at a time) as a ``Run2``, so the account and its metrics apply to it."""
    if isinstance(r, M.Run2):
        return r
    return M.Run2(**{f: getattr(r, f) for f in TM.Run.__dataclass_fields__}, kind="state", legs=((1.0, r.path),))


REF_BH = "buy-and-hold of 0.01 lot (PREREG 7's reference)"
REF_S1 = "study 1's finalists (study 1's code on this study's market)"
REF_BOTS = "the bots' designs (study 1's rebuild of FINAL10's 8y trades, reused)"


def _summary_row(source: str, symbol: str, vid: str, role: str, win: str, a, z, acc: Mapping, unit: Mapping,
                 family_best_of: str = "", note: str = "", basis: str = "M1 worst marks", **extra) -> dict:
    return {"source": source, "symbol": symbol, "vid": vid, "role": role, "family_best": family_best_of,
            "window": win, "start": a, "end": z, "max_dd_basis": basis, "note": note,
            **{f"account_{k}": acc.get(k, np.nan) for k in ACC_KEYS}, **{f"unit_{k}": unit.get(k, np.nan)
                                                                         for k in UNIT_KEYS}, **extra}


ACC_KEYS = ("start_usd", "final_usd", "net_usd", "return_pct", "cagr_pct", "max_dd_usd", "max_dd_pct", "p_dd", "trades",
            "win_rate_pct", "profit_factor", "sharpe_w", "pos_quarters_pct", "worst_quarter_usd", "wiped", "wiped_at",
            "max_units")
UNIT_KEYS = ("start_usd", "final_usd", "net_usd", "return_pct", "cagr_pct", "max_dd_usd", "max_dd_pct", "p_dd",
             "trades", "win_rate_pct", "profit_factor", "sharpe_w", "pos_quarters_pct", "worst_quarter_usd", "wiped")


def study1_finalists() -> List[str]:
    """Study 1's six finalists (its frozen FINALISTS.md), symbol by symbol."""
    return T1.read_frozen(STUDY1_DIR)[0]


def _study1_published(window: str) -> Optional[pd.DataFrame]:
    name = {"full": "results_full.csv", "holdout": "results_holdout.csv"}.get(window)
    p = STUDY1_DIR / name if name else None
    return pd.read_csv(p, float_precision="round_trip").set_index("vid") if p is not None and p.exists() else None


def _same_span(win: str, symbol: str) -> bool:
    """This study's window has study 1's span (full and hold-out: the same start and data end)."""
    try:
        return win in TM.WINDOWS and tuple(map(str, span(win, symbol))) == tuple(map(str, TM.window(win, symbol)))
    except (KeyError, ValueError):
        return False


def reference_rows(focus_windows: Sequence[str], loader=None, log=print, with_study1: bool = True,
                   with_bots: bool = True) -> Tuple[List[dict], Dict[str, List[pd.DataFrame]]]:
    """
    What PREREG 7 puts next to this study's accounts, over the same spans (the focus windows: full, the hold-out and
    gold's Early window), x1.0: buy-and-hold of 0.01 lot (``tradeiq.bh_run`` on this study's market: one unit for the
    whole span, so the account never compounds) and study 1's six finalists run with study 1's own code
    (``tradeiq.Study`` and ``tradeiq_market.run`` on this study's market, whose gold history starts 2016; on full and
    the hold-out each run is compared with study 1's published row: ``equals_study1``), as accounts and per 0.01 lot;
    and the bots' designs as study 1 rebuilt them from FINAL10's 8y trades (its published curves_summary.csv) where
    this study's window has study 1's span. FINAL10's runs start 2018-11-13, so the bots have no Early rows.
    """
    loader_fn = loader or _load_default
    fins = study1_finalists() if with_study1 else []
    summary: List[dict] = []
    daily: Dict[str, List[pd.DataFrame]] = {}
    for s in SYMBOLS:
        wins = [w for w in focus_windows if applies(w, s)]
        if not wins:
            continue
        mk = loader_fn(s, None)
        mine = [v for v in fins if v.startswith(s + "|")]
        st = T1.Study(mk) if mine else None
        runs: List[Tuple[str, str, str, Callable]] = [
            (f"{s}|buy-and-hold", "benchmark", REF_BH, lambda a, z, c: T1.bh_run(mk, a, z, c))]
        for vid in mine:
            v1 = T1.Variant.of(vid)
            runs.append((vid, "study 1 finalist", REF_S1,
                         lambda a, z, c, v1=v1: TM.run(st.mk, st.bars[v1.tf], st.state(v1), a, z,
                                                       stop=st.stops[v1.tf] if v1.stop == "S1" else None, cost=c)))
        for win in wins:
            a, z = span(win, s)
            pub = _study1_published(win) if _same_span(win, s) else None
            for vid, role, source, fn in runs:
                r = _as_run2(fn(a, z, 1.0))
                acc, unit, day, _marks = account_rows(r)
                same = ""
                if role == "study 1 finalist" and pub is not None and vid in pub.index:
                    same = bool(float(pub.at[vid, "net"]) == r.net and float(pub.at[vid, "max_dd"]) == r.max_dd)
                summary.append(_summary_row(source, s, vid, role, win, a, z, acc, unit, equals_study1=same))
                daily.setdefault(win, []).append(day.assign(symbol=s, vid=vid)[["symbol", "vid", "time", "equity",
                                                                                "unit_equity", "unit_worst"]])
        log(f"  references {s}: buy-and-hold and {len(mine)} study-1 finalists over {', '.join(wins)}")
        del st, mk
        gc.collect()
    if with_bots:
        summary += study1_bot_rows(focus_windows, log)
    return summary, daily


def study1_bot_rows(focus_windows: Sequence[str], log=print) -> List[dict]:
    """The bots' designs on this study's spans: study 1's rebuilds (tradeiq_rsi/curves_summary.csv), where the span
    is study 1's (full, the hold-out); their accounts are on daily marks and end 2026-11-13 (FINAL10's runs)."""
    p = STUDY1_DIR / "curves_summary.csv"
    if not p.exists():
        return []
    cs = pd.read_csv(p)
    bots = cs[cs.source.astype(str).str.startswith("the bots' designs")]
    out = []
    for r in bots.itertuples(index=False):
        if r.window not in focus_windows or r.symbol not in SYMBOLS or not _same_span(r.window, r.symbol):
            continue
        acc = {"start_usd": X.ACCOUNT, "final_usd": r.final_equity, "net_usd": r.net, "return_pct": r.return_pct,
               "cagr_pct": r.cagr_pct, "max_dd_pct": r.max_dd_pct, "trades": r.trades, "win_rate_pct": r.win_rate_pct,
               "profit_factor": r.profit_factor, "wiped": int(_bool(r.wiped)), "max_units": r.max_units}
        unit = {"net_usd": r.unit_net, "final_usd": r.unit_net, "max_dd_usd": r.unit_max_dd, "start_usd": 0.0}
        out.append(_summary_row(REF_BOTS, r.symbol, r.vid, "design", r.window, r.start, r.end, acc, unit,
                                basis=str(r.max_dd_basis), note=f"{r.roles}; its curve ends {r.common_end} (FINAL10's "
                                                                f"runs): tradeiq_rsi/curves_bots_{r.window}.csv"))
    if not out:
        log("  note: the bots' designs: no rebuild on these spans (study 1's are full and the hold-out to the data end)")
    return out


def accounts(study_dir: Optional[Path] = None, compare_dir: Optional[Path] = None,
             modules: Optional[Mapping[str, object]] = None, counts: Optional[Sequence[Count]] = None,
             plan=ACCOUNT_PLAN, workers: int = 2, loader=None, require_frozen: bool = True,
             allow_code_change: bool = False, references: bool = True, log=print) -> Dict[str, pd.DataFrame]:
    """
    PREREG 7's accounts and the comparison page's files. ``plan``: (window, 'focus' | 'all', costs) rows (the default
    ACCOUNT_PLAN needs the freeze: the hold-out, the Early window and the common windows reach past 2024-07-01 or into
    2017-2018; tests pass Development windows with ``require_frozen=False``, and the guard still refuses anything
    closed). After the freeze it takes FINALISTS.md's inputs and result code (as ``exam``). Writes curves_<window>.csv
    (study 1's layout) and curves_summary.csv for the focus rows and, with ``references``, buy-and-hold, study 1's
    finalists and the bots' designs next to them (``reference_rows``), in the study folder; and
    <compare>/tradeiq_2027__series.csv, __metrics.csv, __curves_<window>.csv.gz (``export_accounts``).
    """
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    compare_dir = Path(COMPARE_DIR if compare_dir is None else compare_dir)
    modules = find_modules() if modules is None else dict(modules)
    _refuse_test_options(study_dir, "accounts", modules, counts, loader)
    snap = CodeSnapshot.take(modules)
    if require_frozen:
        _require_frozen(study_dir)
        fz = read_frozen_all(study_dir)
        moved = frozen_inputs_check(study_dir, fz)
        if moved:
            raise FrozenInputsError("accounts: " + "; ".join(moved) + " (FINALISTS.md's sha256): restore the frozen "
                                    "files")
        frozen_code_check(fz, snap, allow_code_change, "accounts", log)
    grid = read_grid(study_dir)
    res = read_results(study_dir)
    check_complete(res, grid)
    qual = qualification(res)
    g2, pairs = checked_grid(modules, counts)
    if not _grid_matches(grid, g2):
        raise GridError("grid.csv is not the rule modules' grid now")
    todo = account_plan_of(qual, plan)
    focus_windows = tuple(w for w, which, _ in plan if which == "focus")
    pairs = [(k, v) for k, v in pairs if v.id in todo]

    def stamp_of(v, blobs, data, env):
        sp = [[win, *span(win, v.symbol), list(costs)] for win, costs in todo[v.id]]
        return _stamp(ACCJOB, v, blobs, data, env, spans=sp,
                      daily=[w for w in focus_windows if any(w == s[0] for s in sp)])
    t0 = time.time()
    end = None if require_frozen else M.HOLDOUT_START
    stats = run_job(study_dir, ACCJOB, pairs, modules, stamp_of, _accounts, end, lambda s: (), workers=workers,
                    loader=loader, log=log, snap=snap)
    snap.check(" (before the accounts were exported)")
    refs = reference_rows(focus_windows, loader, log) if references else ([], {})
    got = export_accounts(study_dir, compare_dir, pairs, modules, qual, stamp_of, focus_windows, log, snap=snap,
                          refs=refs)
    log(f"accounts: {stats['computed']} computed, {stats['skipped']} complete ({time.time() - t0:.0f} s) -> "
        f"{compare_dir}")
    return got


def _exam_words(study_dir: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """(vid -> 'pass' / 'fail' of exam 1, vid -> the verdict) from exam.csv, when it exists."""
    p = Path(study_dir) / "exam.csv"
    if not p.exists() or p.stat().st_size <= 1:
        return {}, {}
    ex = pd.read_csv(p, dtype=str, keep_default_na=False)
    h = ex[ex.window == "holdout"]
    return ({v: ("pass" if _bool(x) else "fail") for v, x in zip(h.vid, h["pass"])},
            dict(zip(ex.vid, ex.verdict)))


def _round(x, nd: int = 6):
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return int(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    x = float(x)
    if math.isnan(x):
        return ""
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return round(x, nd)


def export_accounts(study_dir: Path, compare_dir: Path, pairs, modules, qual: pd.DataFrame, stamp_of,
                    focus_windows: Sequence[str], log=print, snap: Optional[CodeSnapshot] = None,
                    refs: Tuple[List[dict], Dict[str, List[pd.DataFrame]]] = ([], {})) -> Dict[str, pd.DataFrame]:
    """The contract's files (source tradeiq_2027) and the study folder's curves from the accounts' parts. The export
    is written into a temporary folder and checked there (``check_export``); only then are this source's old files
    removed and the new ones moved in, so the compare folder never holds half an export. Rows that look ahead by
    design are not exported; ``eligible`` is the row's qualification (study 1's meaning on the page)."""
    study_dir, compare_dir = Path(study_dir), Path(compare_dir)
    snap = snap or CodeSnapshot.take(modules)
    roles = _roles(qual)
    q = qual.set_index("vid")
    exam1, verdicts = _exam_words(study_dir)
    fb = family_best(qual)
    best_of = {}
    for r in fb.itertuples(index=False):
        best_of.setdefault(r.vid, []).append(r.family)
    series, metrics, summary = [], [], []
    curves: Dict[str, List[pd.DataFrame]] = {}
    daily: Dict[str, List[pd.DataFrame]] = {}
    missing = []
    data = _data_of(study_dir, ACCJOB)
    for key, v in pairs:
        path = part_path(study_dir, ACCJOB, key, v.symbol, v.id)
        if v.symbol not in data or not part_ok(path, stamp_of(v, snap.run_blobs(key), data[v.symbol], snap.env)):
            missing.append(v.id)
            continue
        try:
            body = read_part(path)
        except PartError:
            _drop_part(path)
            missing.append(v.id)
            continue
        sid = series_id(v.id)
        notes = [x for x in (v.info,) if x]
        if v.id in verdicts:
            notes.append(f"exam: {verdicts[v.id]}")
        if v.id in best_of:
            notes.append("best row of " + ", ".join(best_of[v.id]))
        note = legs_note(body["legs"]) if not body["lanes"] else ""
        if note:
            notes.append(note)
        if body["lanes"]:
            notes.append(f"{body['lanes']} lanes summed (balke.multi_account)")
        export = not looks_ahead(v.id)
        if export:
            series.append({"series_id": sid, "source": SID, "study": STUDY_NAME, "symbol": v.symbol,
                           "label": label_of(v.id), "kind": "rule", "family": v.family, "tf": v.tf,
                           "filter": setting(v.id, v.params, FILTER_KEYS, FILTER_TOKENS), "role": roles[v.id],
                           "eligible": int(bool(q.loc[v.id, "qualifies"])), "exam": exam1.get(v.id, ""),
                           "notes": "; ".join(notes)})
        for m in body["metrics"]:
            for basis in ("account", "unit"):
                x = m[basis]
                if export:
                    metrics.append({"series_id": sid, "window": m["window"], "start": str(m["start"])[:10],
                                    "end": str(m["end"])[:10], "cost": float(m["cost"]), "basis": basis,
                                    **{k: _round(x[k], 4 if k.endswith(("usd", "pct")) else 6) for k in
                                       ("start_usd", "final_usd", "net_usd", "return_pct", "cagr_pct", "max_dd_usd",
                                        "max_dd_pct", "p_dd", "trades", "win_rate_pct", "profit_factor", "sharpe_w",
                                        "pos_quarters_pct", "worst_quarter_usd", "wiped")},
                                    "dd_marks": "M1", "score_final10": "", "source_file": SOURCE_FILE})
            if m["cost"] == 1.0 and m["window"] in focus_windows:
                summary.append(_summary_row("this study", v.symbol, v.id, roles[v.id], m["window"], m["start"],
                                            m["end"], m["account"], m["unit"], ", ".join(best_of.get(v.id, [])),
                                            note))
        if export:
            for win, df in body["curves"].items():
                curves.setdefault(win, []).append(df.assign(series_id=sid)[list(CURVE_COLS)])
        for win, df in body["daily"].items():
            daily.setdefault(win, []).append(df.assign(symbol=v.symbol, vid=v.id)[["symbol", "vid", "time", "equity",
                                                                                   "unit_equity", "unit_worst"]])
    if missing:
        raise RunError(f"{len(missing)} accounts are not complete (run `accounts` again): {missing[:3]}")
    se = pd.DataFrame(series, columns=list(SERIES_COLS))
    me = pd.DataFrame(metrics, columns=list(METRIC_COLS))
    for c in ("return_pct", "max_dd_pct", "cagr_pct"):
        me.loc[me.basis == "unit", c] = ""
    tmp = compare_dir / f".{SID}.tmp{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        write_csv(se, tmp / f"{SID}__series.csv")
        write_csv(me, tmp / f"{SID}__metrics.csv")
        for win, parts in curves.items():
            write_csv(pd.concat(parts, ignore_index=True), tmp / f"{SID}__curves_{_curve_name(win)}.csv.gz")
        problems = check_export(tmp, SID)
        if problems:
            raise AssertionError("the export breaks the COMPARE DATA CONTRACT v1 (nothing replaced):\n  "
                                 + "\n  ".join(problems[:20]))
        for old in compare_dir.glob(f"{SID}__*"):
            old.unlink()
        for new in sorted(tmp.iterdir()):
            os.replace(new, compare_dir / new.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ref_summary, ref_daily = refs
    for win, parts in ref_daily.items():
        daily.setdefault(win, []).extend(parts)
    for win, parts in daily.items():
        write_csv(pd.concat(parts, ignore_index=True), study_dir / f"curves_{win}.csv")
    write_csv(pd.DataFrame(summary + list(ref_summary)), study_dir / "curves_summary.csv")
    return {"series": se, "metrics": me}


def _curve_name(window: str) -> str:
    """The contract's file-name rule: characters other than letters, digits, '.' and '-' become '_'."""
    return "".join(ch if (ch.isalnum() or ch in ".-") else "_" for ch in window)


def check_export(compare_dir: Path, sid: str = SID) -> List[str]:
    """COMPARE DATA CONTRACT v1 on one source's files (the rules of compare_page.validate, on this source alone): the
    columns in order, unique series ids '<sid>:<id>', the value sets, one metrics row per (series, window, cost,
    basis), ISO dates with start < end, final - start = net, '' where the contract says so, curves of known series
    with one increasing row per day, the opening row the day before the window starts at $2,000, no row after the
    window, the last row at the x1.0 account's final equity, and a wiped account's curve ending at its wipe-out (its
    only row at 0). Returns the problems (none: an empty list)."""
    compare_dir = Path(compare_dir)
    p = []
    try:
        se = pd.read_csv(compare_dir / f"{sid}__series.csv", dtype=str, keep_default_na=False)
        me = pd.read_csv(compare_dir / f"{sid}__metrics.csv", dtype=str, keep_default_na=False)
    except OSError as e:
        return [f"missing file: {e}"]
    if list(se.columns) != list(SERIES_COLS):
        p.append(f"series columns {list(se.columns)}")
    if list(me.columns) != list(METRIC_COLS):
        p.append(f"metrics columns {list(me.columns)}")
    if p:
        return p
    if se.series_id.duplicated().any():
        p.append("duplicate series_id")
    if not se.series_id.str.startswith(sid + ":").all():
        p.append(f"a series_id without the prefix {sid}:")
    for col, ok in (("source", (sid,)), ("symbol", SYMBOLS), ("kind", KINDS), ("role", ROLES), ("eligible", ("0", "1")),
                    ("exam", ("pass", "fail", ""))):
        bad = sorted(set(se[col]) - set(ok))
        if bad:
            p.append(f"series.{col} holds {bad}")
    known = set(se.series_id)
    if not set(me.series_id) <= known:
        p.append("metrics rows of unknown series")
    if me.duplicated(["series_id", "window", "cost", "basis"]).any():
        p.append("two metrics rows for one (series_id, window, cost, basis)")
    for col, ok in (("cost", ("1.0", "1.5")), ("basis", ("account", "unit")), ("wiped", ("0", "1")),
                    ("dd_marks", DD_MARKS)):
        bad = sorted(set(me[col]) - set(ok))
        if bad:
            p.append(f"metrics.{col} holds {bad}")
    iso = r"^\d{4}-\d{2}-\d{2}$"
    if not (me.start.str.match(iso).all() and me.end.str.match(iso).all()) or not (me.start < me.end).all():
        p.append("metrics start / end are not ISO dates with start < end")
    acc, unit = me[me.basis == "account"], me[me.basis == "unit"]
    if not ((acc.start_usd.astype(float) == 2000.0).all() and (unit.start_usd.astype(float) == 0.0).all()):
        p.append("start_usd is not 2000 (account) / 0 (unit)")
    for c in ("return_pct", "max_dd_pct"):
        if (unit[c] != "").any():
            p.append(f"unit rows with a {c}")
    num = lambda col: pd.to_numeric(me[col], errors="coerce")             # noqa: E731
    gap = (num("final_usd") - num("start_usd") - num("net_usd")).abs()
    if (gap.isna() | (gap > 0.011)).any():
        p.append(f"final - start != net in {int((gap.isna() | (gap > 0.011)).sum())} metrics rows")

    def day_before(d: str) -> str:
        return (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    for name in sorted(compare_dir.glob(f"{sid}__curves_*.csv.gz")):
        win = name.name[len(sid) + len("__curves_"):-len(".csv.gz")]
        cu = pd.read_csv(name, dtype=str, keep_default_na=False)
        if list(cu.columns) != list(CURVE_COLS):
            p.append(f"{name.name}: columns {list(cu.columns)}")
            continue
        if not set(cu.series_id) <= known:
            p.append(f"{name.name}: unknown series")
        if not cu.date.str.match(iso).all():
            p.append(f"{name.name}: dates not YYYY-MM-DD")
            continue
        for s, g in cu.groupby("series_id", sort=False):
            if not (g.date.iloc[1:].to_numpy() > g.date.iloc[:-1].to_numpy()).all():
                p.append(f"{name.name}: {s} dates not one increasing row per day")
            fin = acc[(acc.series_id == s) & (acc.window.map(_curve_name) == win) & (acc.cost == "1.0")]
            if len(fin) != 1:
                p.append(f"{name.name}: {s} has no x1.0 account metrics row for window {win}")
                continue
            f0 = fin.iloc[0]
            eq = g.equity_usd.astype(float).to_numpy()
            if g.date.iloc[0] != day_before(f0.start) or abs(eq[0] - 2000.0) > 1e-6:
                p.append(f"{name.name}: {s} the opening row is {g.date.iloc[0]} {eq[0]}, not the day before "
                         f"{f0.start} at 2000.0")
            if g.date.iloc[-1] > day_before(f0.end):
                p.append(f"{name.name}: {s} has a row after the window's end {f0.end}")
            if abs(eq[-1] - float(f0.final_usd)) > 1e-3:
                p.append(f"{name.name}: {s} ends at {g.equity_usd.iloc[-1]}, its account at {f0.final_usd}")
            if f0.wiped == "1" and not (eq[-1] <= 1e-9 and (eq[:-1] > 1e-9).all()):
                p.append(f"{name.name}: {s} is wiped but its curve does not stop at the wipe-out")
    return p


# ───────────────────────────── pairs of rows (the comparisons) ─────────────────────────────
#
# Rows are paired by the PREREG's names: an id is split at '|' into tokens, and a counterpart is the id with one
# token replaced (XP -> X0, F1 -> F0, HV -> LV, ...). A row whose id lacks the token is not paired. Where a module
# gives the pairing itself (EXTRAS: study1_ids, ha_base) that comes first.

S1_INDICATORS = ("RSI", "LaRSI", "VWRSI", "VWRSI-RV", "TSI", "QQE")
S1_FILTERS = {"1H": ("F0", "F1", "F2-4H", "F2-1D"), "4H": ("F0", "F1", "F2-1D"), "1D": ("F0", "F1")}
# PREREG 5's filters and PREREG 6.4 / 6.5's (SP's FD, ORB's HV and HV + F2-4H) against F0, within a script (6.11)
VS_F0_FILTERS = ("F1", "F2", "F2-4H", "F2-1D", "F3", "FR", "FS", "FD", "HV", "HV+F2-4H")
LO_FILTER_FAMILIES = ("SP", "ORB")       # LO is a filter there (6.4, 6.5); on RIB, ALMA-X, STK, HA it is the side


class ClaimError(LookupError):
    """A claim found no rows to compare (the ids or params do not carry the PREREG's names it pairs by)."""


def _flat_values(x) -> List[str]:
    if isinstance(x, Mapping):
        return [s for v in x.values() for s in _flat_values(v)]
    if isinstance(x, (list, tuple)):
        return [s for v in x for s in _flat_values(v)]
    return [str(x)]


def tokens_of(vid: str, params=None) -> set:
    """The PREREG names a row carries: its id's tokens after the symbol and the timeframe (so an HA overlay 'M5' is
    not the M5 timeframe), and its params' values."""
    return set(id_tokens(vid)[2:]) | set(_flat_values(_params(params)))


def swap(vid: str, old: str, new: Optional[str]) -> Optional[str]:
    """``vid`` with its one token ``old`` replaced by ``new`` (None: dropped); None when ``old`` is not once in it."""
    t = id_tokens(vid)
    if t.count(old) != 1:
        return None
    return "|".join(x for x in ((new if x == old else x) for x in t) if x is not None)


def study1_pairs(v: M.Variant, modules: Mapping[str, object], s1_ids: Optional[set] = None) -> Dict[str, str]:
    """{study-1 filter: study-1 id} of an MSD-F4 / MSD-F6 row (PREREG 6.2: paired with study 1's F0, F1 and F2 rows
    of the same base): the msd module's ``study1_ids`` (EXTRAS), else read from the id's and params' tokens (one of
    RSI / LaRSI / VWRSI / VWRSI-RV / TSI / QQE, one of R1 / R2, one of S0 / S1; BTC's VWRSI is study 1's VWRSI-RV)."""
    f = extra(modules, "study1_ids", required=False)
    if f is not None:
        got = f(v)
        out = ({str(k): str(x) for k, x in got.items()} if isinstance(got, Mapping) else
               {id_tokens(str(x))[4]: str(x) for x in got})
    else:
        toks = tokens_of(v.id, dict(v.params))
        ind = [t for t in S1_INDICATORS if t in toks]
        if "VWRSI-RV" in ind and "VWRSI" in ind:
            ind.remove("VWRSI")
        if v.symbol == M.BTC:
            ind = ["VWRSI-RV" if t == "VWRSI" else t for t in ind]
        fam = [t for t in ("R1", "R2") if t in toks]
        stop = [t for t in ("S0", "S1") if t in toks]
        if len(ind) != 1 or len(fam) != 1 or len(stop) != 1 or v.tf not in S1_FILTERS:
            raise ClaimError(f"{v.id}: cannot read its study-1 base (indicator, R1 / R2, S0 / S1) from the id or the "
                             f"params; expected {EXTRAS['study1_ids'][2]}")
        out = {F: f"{v.symbol}|{v.tf}|{ind[0]}|{fam[0]}|{F}|{stop[0]}" for F in S1_FILTERS[v.tf]}
    if s1_ids is not None:
        bad = [x for x in out.values() if x not in s1_ids]
        if bad:
            raise ClaimError(f"{v.id}: study-1 ids not in study 1's results: {bad}")
    return out


def ha_base(v: M.Variant, modules: Mapping[str, object]) -> Optional[str]:
    """The base an HA-MANAGED row is paired with (PREREG 6.8): the ha module's ``base_of`` (EXTRAS), else
    params['base'] / ['base_id'] / ['base_vid']."""
    f = extra(modules, "ha_base", required=False)
    if f is not None:
        return str(f(v))
    p = dict(v.params)
    for k in ("base", "base_id", "base_vid"):
        if p.get(k):
            return str(p[k])
    return None


def _cmp_rows(a: pd.Series, b: pd.Series, w: str, pre: str) -> Dict[str, object]:
    pa, pb = float(a.profit_dd), float(b.profit_dd)
    return {f"{w}_net": float(a.net), f"{w}_{pre}_net": float(b.net), f"{w}_win_net": bool(a.net > b.net),
            f"{w}_profit_dd": pa, f"{w}_{pre}_profit_dd": pb,
            f"{w}_win_pdd": (pa > pb) if (math.isfinite(pa) and math.isfinite(pb)) else np.nan,
            f"{w}_trades": int(a.trades), f"{w}_{pre}_trades": int(b.trades)}


def _summary(df: pd.DataFrame, by_sets: Sequence[Sequence[str]], words=("helps", "does not help", "mixed")
             ) -> pd.DataFrame:
    """Wins per group in both windows, with study 1's DEVIATIONS 30 word: more than half of the pairs won on net and
    on P/DD in Development and in Validation; at most half on both in both; otherwise mixed."""
    out = []
    for by in by_sets:
        by = list(by)
        for key, g in df.groupby(by, sort=False):
            key = key if isinstance(key, tuple) else (key,)
            row = {"by": "+".join(by[1:]), **dict(zip(by, key)), "n": int(len(g))}
            ok, bad = {}, {}
            for w in ("dev", "val"):
                wp = g[f"{w}_win_pdd"].dropna().astype(bool)
                kn, kp = int(g[f"{w}_win_net"].sum()), int(wp.sum())
                row.update({f"{w}_wins_net": kn, f"{w}_wins_pdd": kp, f"{w}_n_pdd": int(len(wp))})
                ok[w] = T1._most(kn, len(g)) and T1._most(kp, len(wp))
                bad[w] = not T1._most(kn, len(g)) and not T1._most(kp, len(wp))
            row["verdict"] = T1.verdict(ok["dev"], ok["val"], bad["dev"], bad["val"], words)
            out.append(row)
    return pd.DataFrame(out)


# ───────────────────────────── PREREG 8: the claims ─────────────────────────────

@dataclass
class Evidence:
    """What a claim reads: the results of two windows relabelled 'dev' and 'val' (study 1's ``as_two_windows``:
    Development and Validation for the verdicts; the hold-out twice for its information), the grid, the
    qualification, study 1's results of the same windows, the rule modules (their extras), and on request the
    trades and the markets (to the hold-out start unless the hold-out is what is read). A claim function counts only
    inside the two windows: ``span``, ``in_window`` and ``years`` bound it, and ``check_rows`` refuses a row outside
    them (CLAIM_RULE)."""
    study_dir: Path
    res: pd.DataFrame
    grid: pd.DataFrame
    qual: pd.DataFrame
    modules: Mapping[str, object]
    windows: Tuple[str, str] = ("dev", "val")
    loader: Optional[Callable] = None
    market_end: Optional[str] = "hold-out start"         # the hold-out start as the guard has it now; None: data end

    def __post_init__(self):
        if self.market_end == "hold-out start":
            self.market_end = M.HOLDOUT_START
        self.dev = self.res[self.res.window == "dev"].set_index("vid")
        self.val = self.res[self.res.window == "val"].set_index("vid")
        self.symbols = [s for s in SYMBOLS if s in set(self.dev.symbol)]
        self._s1 = None
        self._s1_trades = None
        self._ctx: Dict[str, M.Context] = {}
        self._trades: Dict[tuple, pd.DataFrame] = {}
        self.params = dict(zip(self.grid.vid, self.grid.params))

    def tokens(self, vid: str) -> set:
        return tokens_of(vid, self.params.get(vid, ""))

    def rows(self, symbol: str, family: Optional[str] = None, has: Sequence = (), eligible: Optional[bool] = True,
             tf: Optional[str] = None) -> pd.DataFrame:
        """The 'dev' rows of a symbol (and family, timeframe) whose tokens hold every item of ``has`` (an item may be
        a tuple of alternatives)."""
        d = self.dev[self.dev.symbol == symbol]
        if family is not None:
            d = d[d.family == family]
        if tf is not None:
            d = d[d.tf == tf]
        if eligible is not None:
            d = d[d.eligible == eligible]
        keep = []
        for vid in d.index:
            t = self.tokens(vid)
            keep.append(all((h in t) if isinstance(h, str) else any(x in t for x in h) for h in has))
        return d[np.asarray(keep, bool)] if len(d) else d

    def swaps(self, symbol: str, family: str, old: str, new: Sequence[Optional[str]], eligible=True
              ) -> List[Tuple[str, str]]:
        out = []
        for vid in self.rows(symbol, family, (old,), eligible).index:
            for n in new:
                c = swap(vid, old, n)
                if c is not None and c in self.dev.index:
                    out.append((vid, c))
                    break
        return out

    def count(self, pairs: Sequence[Tuple[str, str]], test: Callable[[pd.Series, pd.Series], bool],
              other: Optional[Tuple[pd.DataFrame, pd.DataFrame]] = None) -> Tuple[int, int, int]:
        """(pairs passing ``test`` in 'dev', in 'val', pairs); ``other``: the frames the second ids come from."""
        od, ov = other if other is not None else (self.dev, self.val)
        kd = sum(bool(test(self.dev.loc[a], od.loc[b])) for a, b in pairs)
        kv = sum(bool(test(self.val.loc[a], ov.loc[b])) for a, b in pairs)
        return kd, kv, len(pairs)

    def study1(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Study 1's rows of the same two windows (its published results, reused, never rerun: PREREG 6.2)."""
        if self._s1 is None:
            w0, w1 = self.windows
            names = {"dev": "results_dev_val.csv", "val": "results_dev_val.csv", "devval": "results_dev_val.csv",
                     "holdout": "results_holdout.csv", "full": "results_full.csv"}
            r0 = pd.read_csv(STUDY1_DIR / names[w0], float_precision="round_trip")
            r1 = r0 if names[w1] == names[w0] else pd.read_csv(STUDY1_DIR / names[w1], float_precision="round_trip")
            self._s1 = (r0[r0.window == w0].set_index("vid"), r1[r1.window == w1].set_index("vid"))
        return self._s1

    def study1_trades(self) -> pd.DataFrame:
        """Study 1's Development and Validation trades at x1.0 (its published trades_dev_val.csv.gz), read once."""
        if self._s1_trades is None:
            t = pd.read_csv(STUDY1_DIR / "trades_dev_val.csv.gz", usecols=["vid", "window", "cost", "entry_time",
                                                                             "side", "pnl"])
            self._s1_trades = t[t.cost == 1.0]
        return self._s1_trades

    def trades(self, window: str, vids: Iterable[str], cost: float = 1.0) -> pd.DataFrame:
        """The trades of ``vids`` in one real window of this study at one cost, read in chunks (the file is large)."""
        vids = set(vids)
        key = (window, cost, frozenset(vids))
        if key not in self._trades:
            name = {"dev": "trades_dev_val.csv.gz", "val": "trades_dev_val.csv.gz", "holdout": "trades_holdout.csv.gz",
                    "early": "trades_early.csv.gz"}[window]
            parts = [c[(c.window == window) & (c.cost == cost) & c.vid.isin(vids)] for c in
                     pd.read_csv(self.study_dir / name, float_precision="round_trip", chunksize=500_000)]
            self._trades[key] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=TRADE_COLS)
        return self._trades[key]

    def context(self, symbol: str) -> M.Context:
        """The symbol's Context (bars from the data start: the history is the indicators' warm-up only; count
        outcomes with ``in_window``)."""
        if symbol not in self._ctx:
            self._ctx[symbol] = M.Context((self.loader or _load_default)(symbol, self.market_end))
        return self._ctx[symbol]

    def span(self, window: str, symbol: str) -> Tuple[str, str]:
        """(start, end) of 'dev' or 'val' of this evidence: the real window it stands for (``windows``)."""
        real = dict(zip(("dev", "val"), self.windows))
        if window not in real:
            raise ValueError(f"{window}: the evidence has 'dev' and 'val' ({self.windows})")
        return span(real[window], symbol)

    def in_window(self, symbol: str, tf: str, window: str) -> np.ndarray:
        """Per bar of ``context(symbol).bars(tf)``: it opens and closes inside the window (what may be counted)."""
        b = self.context(symbol).bars(tf)
        a, z = (TM.s_of(x) for x in self.span(window, symbol))
        return (b.t >= a) & (b.tc <= z)

    def years(self, symbol: str) -> List[Tuple[str, int, str, str]]:
        """(window, year, start, end) of every calendar year inside the two windows, clipped to them."""
        out = []
        for w in ("dev", "val"):
            a, z = self.span(w, symbol)
            for y in range(pd.Timestamp(a).year, pd.Timestamp(z).year + 1):
                ya, yz = max(str(a)[:10], f"{y}-01-01"), min(str(z)[:10], f"{y + 1}-01-01")
                if ya < yz:
                    out.append((w, y, ya, yz))
        return out

    def check_rows(self, rows: Sequence[Mapping[str, object]], what: str) -> None:
        """A claim function's rows may carry 'year', 'start' or 'end': each must lie inside the evidence's windows
        (CLAIM_RULE); before the freeze nothing of the hold-out or of gold's Early window may be counted."""
        for r in rows:
            sym = r.get("symbol")
            syms = [sym] if sym in ALL_SYMBOLS else self.symbols
            for s in syms:
                a = min(str(self.span(w, s)[0])[:10] for w in ("dev", "val"))
                z = max(str(self.span(w, s)[1])[:10] for w in ("dev", "val"))
                bad = []
                y = r.get("year")
                if y not in (None, "") and not (isinstance(y, float) and math.isnan(y)):
                    if not (int(a[:4]) <= int(y) <= int((pd.Timestamp(z) - pd.Timedelta(seconds=1)).year)):
                        bad.append(f"year {y}")
                for k in ("start", "end"):
                    x = r.get(k)
                    if x in (None, "") or (isinstance(x, float) and math.isnan(x)):
                        continue
                    t = pd.Timestamp(x)
                    d = (t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t).strftime("%Y-%m-%d")
                    if (k == "start" and not (a <= d < z)) or (k == "end" and not (a < d <= z)):
                        bad.append(f"{k} {d}")
                if bad:
                    raise ClaimWindowError(f"{what}: a row ({r.get('part', '')}, {s}) counts outside the evidence's "
                                           f"windows {a} .. {z}: {', '.join(bad)}; {CLAIM_RULE}")

    def extra(self, name: str):
        return extra(self.modules, name, required=True)


def _row(part, symbol, rows, dev, val, dev_ok, val_ok, note="") -> Dict[str, object]:
    return {"part": part, "symbol": symbol, "rows": rows, "dev": dev, "val": val, "dev_ok": dev_ok, "val_ok": val_ok,
            "note": note}


def _untestable(part, symbol, why) -> Dict[str, object]:
    return {"part": part, "symbol": symbol, "rows": "", "dev": "", "val": "", "dev_ok": np.nan, "val_ok": np.nan,
            "verdict": "cannot be tested", "note": why}


def _not_computed(symbol, why) -> Dict[str, object]:
    return {"part": "not computed", "symbol": symbol, "rows": "", "dev": "", "val": "", "dev_ok": np.nan,
            "val_ok": np.nan, "verdict": "not computed", "note": why}


def _frac(k, n) -> str:
    return f"{k}/{n}"


def _most_row(part, symbol, rows, kdkvn, note="") -> Dict[str, object]:
    kd, kv, n = kdkvn
    return _row(part, symbol, rows, _frac(kd, n), _frac(kv, n), T1._most(kd, n), T1._most(kv, n), note)


def _every_row(part, symbol, rows, kdkvn, note="") -> Dict[str, object]:
    kd, kv, n = kdkvn
    return _row(part, symbol, rows, _frac(kd, n), _frac(kv, n), n > 0 and kd == n, n > 0 and kv == n, note)


def _need(pairs, what: str):
    if not pairs:
        raise ClaimError(f"no {what} (the ids must carry the PREREG's names)")
    return pairs


def _beats(a, b) -> bool:
    return a.net > b.net


CLAIMS: Dict[int, Tuple[str, Callable[[Evidence], List[Dict[str, object]]]]] = {}


def claim(n: int, text: str):
    def deco(fn):
        CLAIMS[n] = (text, fn)
        return fn
    return deco


def _from_extra(ev: Evidence, name: str) -> List[Dict[str, object]]:
    got = ev.extra(name)(ev)
    rows = got.to_dict("records") if isinstance(got, pd.DataFrame) else [dict(r) for r in got]
    ev.check_rows(rows, f"{EXTRAS[name][0]}.{name}")
    for r in rows:
        r.setdefault("rows", "")
        r.setdefault("note", "")
    return rows


@claim(1, "Ribbon: the trend only flips when the slope and the close-beyond-the-band agree, so it ignores most of "
          "the noise (RIB against ALMA-X, same exits).")
def _claim1(ev: Evidence):
    out = []
    for s in ev.symbols:
        pairs = []
        for vid, r in ev.rows(s, "ALMA-X").iterrows():
            side = [x for x in ("LS", "LO") if x in ev.tokens(vid)]
            rib = ev.rows(s, "RIB", tuple(side) + ("X0", "F0"), tf=r.tf) if len(side) == 1 else []
            if len(rib) == 1:
                pairs.append((rib.index[0], vid))
        _need(pairs, "RIB x X0 x F0 / ALMA-X pairs (tokens LS / LO, X0, F0)")
        out.append(_every_row("RIB takes fewer trades than ALMA-X in every pair", s, "RIB-LS / LO x X0 x F0 against "
                              "ALMA-X, same side and timeframe", ev.count(pairs, lambda a, b: a.trades < b.trades)))
        out.append(_most_row("RIB makes more net than ALMA-X in most pairs", s, "the same pairs",
                             ev.count(pairs, _beats)))
    return out


@claim(2, "Ribbon: take partial profit at the second target and let the rest run (XP against X0 and XT2).")
def _claim2(ev: Evidence):
    out = []
    for s in ev.symbols:
        for other in ("X0", "XT2"):
            pairs = _need(ev.swaps(s, "RIB", "XP", (other,)), f"RIB XP / {other} pairs")
            out.append(_most_row(f"XP makes more net than {other} in most pairs", s, f"RIB XP against {other}, same "
                                 "side, filter and timeframe", ev.count(pairs, _beats)))
    return out


def _ha_pairs(ev: Evidence, s: str, overlay: str, base_family: Optional[str] = None) -> List[Tuple[str, str, bool]]:
    """(HA-MANAGED row, its base id, the base is study 1's) for the rows of ``overlay`` (M1 .. M5, HA-AND)."""
    out = []
    s1d, _ = ev.study1()
    gv = {v.id: v for _, v in _pairs_of(ev.grid[ev.grid.symbol == s])}
    for vid in ev.rows(s, "HA-MANAGED", (overlay,)).index:
        b = ha_base(gv[vid], ev.modules)
        if b is None:
            continue
        if b in ev.dev.index:
            if base_family is None or ev.dev.at[b, "family"] == base_family:
                out.append((vid, b, False))
        elif b in s1d.index and base_family is None:
            out.append((vid, b, True))
    return out


def _count_mixed(ev: Evidence, pairs: Sequence[Tuple[str, str, bool]], test) -> Tuple[int, int, int]:
    s1d, s1v = ev.study1()
    kd = kv = 0
    for a, b, one in pairs:
        bd, bv = (s1d.loc[b], s1v.loc[b]) if one else (ev.dev.loc[b], ev.val.loc[b])
        kd += bool(test(ev.dev.loc[a], bd))
        kv += bool(test(ev.val.loc[a], bv))
    return kd, kv, len(pairs)


@claim(3, "Ribbon: the stop never moves; a trade can hit two targets and come back. Manage it (XBE and the HA "
          "overlays against X0).")
def _claim3(ev: Evidence):
    out = []
    for s in ev.symbols:
        pairs = _need(ev.swaps(s, "RIB", "XBE", ("X0",)), "RIB XBE / X0 pairs")
        out.append(_most_row("XBE makes more net than X0 in most pairs", s, "RIB XBE against X0", ev.count(pairs,
                                                                                                         _beats)))
        hp = [p for o in ("M1", "M2", "M3", "M4", "M5") for p in _ha_pairs(ev, s, o, base_family="RIB")]
        _need(hp, "HA-MANAGED rows on RIB bases (tokens M1 .. M5; base_of / params['base'])")
        out.append(_most_row("the HA overlays make more net than their RIB X0 base in most pairs", s,
                             "HA M1-M5 on RIB-LS / LO x X0 x F0 against the base", _count_mixed(ev, hp, _beats)))
    return out


@claim(4, "Heikin Ashi: strong candles, you hold; a run of weak candles or indecision after a strong run, you "
          "tighten up (M2 / M3 / M5 against the base).")
def _claim4(ev: Evidence):
    out = []
    for s in ev.symbols:
        for o in ("M2", "M3", "M5"):
            pairs = _need(_ha_pairs(ev, s, o), f"HA-MANAGED {o} rows with their base")
            out.append(_most_row(f"{o} makes more net than its base in most pairs", s, f"HA {o} against the base "
                                 "(this study's RIB rows; study 1's finalists' published rows)",
                                 _count_mixed(ev, pairs, _beats)))
            out.append(_most_row(f"{o} has a smaller max drawdown than its base in most pairs", s, "the same pairs",
                                 _count_mixed(ev, pairs, lambda a, b: a.max_dd < b.max_dd)))
    return out


@claim(5, "Heikin Ashi: the panel's 'reached age A, then 5+ more' percentages are calibrated (computed before each "
          "year, against that year).")
def _claim5(ev: Evidence):
    return _from_extra(ev, "claim5")


@claim(6, "ORB: a break of the range often sets the direction for the day.")
def _claim6(ev: Evidence):
    return _from_extra(ev, "claim6")


@claim(7, "ORB: take the breakouts that come with high volume (HV against LV, same rule).")
def _claim7(ev: Evidence):
    if extra(ev.modules, "claim7", required=False) is not None:
        return _from_extra(ev, "claim7")
    out = []
    for s in ev.symbols:
        pairs = _need(ev.swaps(s, "ORB", "HV", ("LV",), eligible=None), "ORB HV / LV pairs")
        out.append(_most_row("HV makes more net than LV in most pairs", s, "ORB HV against the LV control, same rule "
                             "and timeframe", ev.count(pairs, _beats)))
    return out


@claim(8, "ORB: the dashboard's hit rates are unconditional, not win rates (and O4 against O2 and O3).")
def _claim8(ev: Evidence):
    out = _from_extra(ev, "claim8")
    for s in ev.symbols:
        for other in ("O2", "O3"):
            pairs = _need(ev.swaps(s, "ORB", "O4", (other,)), f"ORB O4 / {other} pairs")
            out.append(_most_row(f"O4 (the hit-rate target) makes more net than {other} in most pairs", s,
                                 f"ORB O4 against {other}, same filter and timeframe", ev.count(pairs, _beats)))
    return out


@claim(9, "ORB: the UTC-5 default is an hour late in summer (the literal clock against New York time, O1).")
def _claim9(ev: Evidence):
    return _from_extra(ev, "claim9")


@claim(10, "Session Hunter: Nasdaq best with a previous-day sweep and the 1H trend held to the close (PF 1.95 on 290 "
           "trades, about 3 in 10 win); a smaller forex edge for the London Judas swing; gold and crypto 'nothing "
           "held up'; holding to 16:00 tested best.")
def _claim10(ev: Evidence):
    out = []
    d = ev.dev
    cm = d[d.symbol.isin(CLAIM_SYMBOLS) & (d.family == "SH")]
    for vid, r in cm.iterrows():
        v = ev.val.loc[vid]
        out.append(_row("the claim-check row has a profit factor above 1 (the author: 1.95)", r.symbol, f"`{vid}`",
                        f"PF {_num(r.profit_factor)}, {int(r.trades)} trades, {_num(r.win_rate, 0)}% win, avg R "
                        f"{_num(r.avg_r)}", f"PF {_num(v.profit_factor)}, {int(v.trades)} trades",
                        bool(r.profit_factor > 1), bool(v.profit_factor > 1), "information only (PREREG 8)"))
    if not len(cm):
        out.append(_untestable("the Nasdaq and forex presets", "both", "no claim-check rows in the grid"))
    for s in ev.symbols:
        g = ev.rows(s, "SH")
        _need(list(g.index), "SH rows")
        kd, kv = int((g.net > 0).sum()), int((ev.val.loc[g.index].net > 0).sum())
        out.append(_row("nothing held up: at most half of the SH rows make money", s, "every eligible SH row",
                        _frac(kd, len(g)), _frac(kv, len(g)), not T1._most(kd, len(g)), not T1._most(kv, len(g))))
        for other in ("E2", "E3"):
            pairs = _need(ev.swaps(s, "SH", "E1", (other,)), f"SH E1 / {other} pairs")
            out.append(_most_row(f"holding to 16:00 (E1) makes more net than {other} in most pairs", s,
                                 f"SH E1 against {other}, same setup, confirmation and timeframe",
                                 ev.count(pairs, _beats)))
        if s == M.GOLD:
            ab, as_ = ev.rows(s, "SH", ("AB",)), ev.rows(s, "SH", ("AS",))
            _need(list(ab.index) + list(as_.index), "SH AB / AS rows")
            out.append(_row("PREREG 6.6's hypothesis: AB is positive (most AB rows net > 0)", s, "SH AB rows",
                            _frac(int((ab.net > 0).sum()), len(ab)),
                            _frac(int((ev.val.loc[ab.index].net > 0).sum()), len(ab)),
                            T1._most(int((ab.net > 0).sum()), len(ab)),
                            T1._most(int((ev.val.loc[ab.index].net > 0).sum()), len(ab))))
            out.append(_row("PREREG 6.6's hypothesis: AS is negative (most AS rows net < 0)", s, "SH AS rows",
                            _frac(int((as_.net < 0).sum()), len(as_)),
                            _frac(int((ev.val.loc[as_.index].net < 0).sum()), len(as_)),
                            T1._most(int((as_.net < 0).sum()), len(as_)),
                            T1._most(int((ev.val.loc[as_.index].net < 0).sum()), len(as_))))
    return out


@claim(11, "Swing Profile: the point of control of the last leg is a level price often comes back to (POC "
           "against the 50% level; W1-W3 against their placebo).")
def _claim11(ev: Evidence):
    out = _from_extra(ev, "claim11")
    for s in ev.symbols:
        pairs = []
        for vid in ev.rows(s, "SP", eligible=False).index:
            t = ev.tokens(vid)
            w = [x for x in ("W1", "W2", "W3") if x in t]
            f = [x for x in ("F0", "F2", "F2-4H", "F2-1D") if x in t]
            if len(w) == 1 and len(f) == 1:
                m = ev.rows(s, "SP", (w[0], f[0]), tf=ev.dev.at[vid, "tf"])
                m = m[[not ({"FD", "LO"} & ev.tokens(x)) for x in m.index]] if len(m) else m
                if len(m) == 1:
                    pairs.append((m.index[0], vid))
        _need(pairs, "SP / placebo pairs (tokens W1-W3 and F0 / F2)")
        out.append(_most_row("the POC rule makes more net than its 50%-level placebo in most pairs", s,
                             "SP W1-W3 x F0 / F2 against the placebo, same timeframe", ev.count(pairs, _beats)))
    return out


@claim(12, "Swing Profile: a leg up with weak buying is a warning (the next leg's size after negative against "
           "positive delta).")
def _claim12(ev: Evidence):
    return _from_extra(ev, "claim12")


@claim(13, "Dashboard: it filters out a lot of bad trades (MSD-F4 / F6 against the unfiltered and MA200-filtered "
           "study-1 rows, pair by pair; the net of the trades they remove).")
def _claim13(ev: Evidence):
    out = []
    s1d, s1v = ev.study1()
    ids = set(s1d.index)
    gv = {v.id: v for _, v in _pairs_of(ev.grid)}
    for s in ev.symbols:
        for kind in ("MSD-F4", "MSD-F6"):
            rows = ev.rows(s, "MSD-FILTER", (kind,))
            by_f: Dict[str, List[Tuple[str, str, bool]]] = {}
            for vid in rows.index:
                for F, b in study1_pairs(gv[vid], ev.modules, ids).items():
                    by_f.setdefault("F0" if F == "F0" else ("F1" if F == "F1" else "F2"), []).append((vid, b, True))
            _need(by_f.get("F0"), f"{kind} rows with their study-1 bases")
            for F, pairs in by_f.items():
                out.append(_most_row(f"{kind} makes more net than study 1's {F} row in most pairs", s,
                                     f"{kind} against the same base with {F} (study 1's published rows)",
                                     _count_mixed(ev, pairs, _beats)))
            out += _removed_trades(ev, s, kind, by_f["F0"])
    return out


def _removed_trades(ev: Evidence, s: str, kind: str, pairs) -> List[Dict[str, object]]:
    """PREREG 8.13's test: the trades the filtered row removes from its F0 base (study 1's), i.e. the base's trades
    whose (entry time, side) the filtered row does not take (a delayed re-entry counts as removed), at x1.0: their
    number and summed net per window (information), and whether their summed P/L is below 0 in most pairs (the
    filter removes losing trades)."""
    w0, w1 = ev.windows
    if (w0, w1) != ("dev", "val"):
        return []
    s1 = ev.study1_trades()
    s1 = s1[s1.vid.isin({b for _, b, _ in pairs})]
    res, n_gone, net_gone = {}, {}, {}
    for w in ("dev", "val"):
        mine = ev.trades(w, {a for a, _, _ in pairs})
        k = c = 0
        tot = 0.0
        for a, b, _ in pairs:
            kept = set(zip(mine[mine.vid == a].entry_time, mine[mine.vid == a].side))
            base = s1[(s1.vid == b) & (s1.window == w)]
            gone = [p for t, sd, p in zip(base.entry_time, base.side, base.pnl) if (t, sd) not in kept]
            k += bool(gone) and float(np.sum(gone)) < 0
            c += len(gone)
            tot += float(np.sum(gone)) if gone else 0.0
        res[w], n_gone[w], net_gone[w] = k, c, tot
    n = len(pairs)
    return [_row(f"the trades {kind} removes from the F0 base lose money (sum < 0) in most pairs", s,
                 f"{kind} against study 1's F0 row: the base's trades it does not take", _frac(res["dev"], n),
                 _frac(res["val"], n), T1._most(res["dev"], n), T1._most(res["val"], n)),
            {**_row(f"the trades {kind} removes from the F0 base: their number and net (x1.0)", s,
                    f"{n} pairs; a removed trade = a base trade whose (entry time, side) the filtered row does not take",
                    f"{n_gone['dev']} trades, net {_usd(net_gone['dev'])}",
                    f"{n_gone['val']} trades, net {_usd(net_gone['val'])}", np.nan, np.nan,
                    "PREREG 8.13: the trades removed and their net"), "verdict": "information"}]


@claim(14, "Dashboard: its higher-timeframe rows use the forming candle and can change.")
def _claim14(ev: Evidence):
    return _from_extra(ev, "claim14")


@claim(15, "Wyckoff: it is strict and rare ('when it shows up, it means something'): events per year, and the "
           "pooled test with its placebo.")
def _claim15(ev: Evidence):
    out = []
    for s in ev.symbols:
        g = ev.rows(s, "WY", ("WY-STD",))
        _need(list(g.index), "WY-STD rows")
        yrs = {w: (TM.s_of(span(n, s)[1]) - TM.s_of(span(n, s)[0])) / (365.25 * M.DAY)
               for w, n in zip(("dev", "val"), ev.windows)}
        per = {w: float(np.median(df.loc[g.index, "n_candidates"] / yrs[w])) for w, df in (("dev", ev.dev),
                                                                                         ("val", ev.val))}
        out.append({**_row("events per year: the median WY-STD row's entry signals (candidates) a year", s,
                           "WY-STD rows", f"{per['dev']:.1f}", f"{per['val']:.1f}", np.nan, np.nan,
                           "the plan gives no number for 'rare': reported, no verdict"), "verdict": "information"})
    out += _from_extra(ev, "claim15")
    return out


@claim(16, "Wyckoff: the risk is smallest at the spring and the test.")
def _claim16(ev: Evidence):
    return _from_extra(ev, "claim16")


@claim(17, "Wyckoff: 'on the 4-hour or the daily' (entries and results by timeframe).")
def _claim17(ev: Evidence):
    """The script's own Wyckoff entries (family WY, eligible rows; our WY-DERIVED families are not the script's
    signals): the share of rows with net above 0 on 4H and on 1D against 1H, and the entries per timeframe."""
    out = []
    for s in ev.symbols:
        sh, ent = {}, {}
        for w, df in (("dev", ev.dev), ("val", ev.val)):
            g = df[(df.symbol == s) & (df.family == "WY") & df.eligible]
            sh[w] = {tf: float((g[g.tf == tf].net > 0).mean()) if (g.tf == tf).any() else np.nan
                     for tf in ("1H", "4H", "1D")}
            ent[w] = {tf: (int(g[g.tf == tf].trades.sum()),
                           int(g[g.tf == tf].n_candidates.sum()) if "n_candidates" in g.columns else 0)
                      for tf in ("1H", "4H", "1D")}
        if not any(math.isfinite(x) for w in sh for x in sh[w].values()):
            raise ClaimError("no WY rows (the script's Wyckoff entries)")
        ok = {w: all(math.isfinite(sh[w][t]) for t in sh[w]) and min(sh[w]["4H"], sh[w]["1D"]) > sh[w]["1H"]
              for w in sh}
        out.append(_row("4H and 1D work better than 1H (a larger share of rows with net > 0)", s, "the script's WY "
                        "rows (eligible), share with net > 0 per timeframe",
                        ", ".join(f"{t} {_pct(x)}" for t, x in sh['dev'].items()),
                        ", ".join(f"{t} {_pct(x)}" for t, x in sh['val'].items()), ok["dev"], ok["val"]))
        out.append({**_row("the entries per timeframe: trades (entry signals)", s, "the same WY rows, summed",
                           ", ".join(f"{t} {a} ({b})" for t, (a, b) in ent['dev'].items()),
                           ", ".join(f"{t} {a} ({b})" for t, (a, b) in ent['val'].items()), np.nan, np.nan,
                           "information"), "verdict": "information"})
    return out


@claim(18, "Patterns: they are only confirmed when the next swing forms; on an old chart every pattern looks like "
           "it caught the exact turn (HP-DRAWN against HP-HC and HP-HF).")
def _claim18(ev: Evidence):
    out = []
    for s in ev.symbols:
        n_drawn = 0
        for fam, others in (("HP-HARMONIC", ("HP-HC", "HP-HF")), ("HP-CHART", ("HP-CC", "HP-CF"))):
            drawn = ev.rows(s, fam, ("HP-DRAWN",), eligible=False)
            n_drawn += len(drawn)
            for other in others if len(drawn) else ():
                pairs = []
                for vid, r in drawn.iterrows():
                    pairs += [(vid, x) for x in ev.rows(s, fam, (other,), tf=r.tf).index]
                _need(pairs, f"HP-DRAWN / {other} pairs")
                out.append(_most_row(f"the drawn {fam} patterns win more often than {other} in most pairs", s,
                                     f"HP-DRAWN against {other}, same timeframe",
                                     ev.count(pairs, lambda a, b: a.win_rate > b.win_rate)))
                out.append(_most_row(f"the drawn {fam} patterns have a higher profit factor than {other} in most "
                                     "pairs", s, "the same pairs",
                                     ev.count(pairs, lambda a, b: a.profit_factor > b.profit_factor)))
        _need(n_drawn, "HP-DRAWN rows (information only, eligible=False, token HP-DRAWN)")
    return out


@claim(19, "Patterns: trade the chart patterns on the breakout, where the entry is real (HP-CS and HP-CF against "
           "HP-CC).")
def _claim19(ev: Evidence):
    out = []
    for s in ev.symbols:
        for kind in ("HP-CS", "HP-CF"):
            pairs = []
            for vid, r in ev.rows(s, "HP-CHART", (kind, "F0")).iterrows():
                m = ev.rows(s, "HP-CHART", ("HP-CC",), tf=r.tf)
                pairs += [(vid, x) for x in m.index]
            _need(pairs, f"{kind} / HP-CC pairs (F0)")
            out.append(_most_row(f"{kind} makes more net than HP-CC in most pairs", s, f"{kind} x F0 against HP-CC, "
                                 "same timeframe", ev.count(pairs, _beats)))
    return out


@claim(20, "Coil Breakout AI: 731 trades on eight coins on 4H since 2021, one in four won, almost three times what "
           "it lost, average winner 8.5R; big candle, volume surge and trend strength helped.")
def _claim20(ev: Evidence):
    out = [_untestable("the script's own results (731 trades, 1 in 4 won, average winner 8.5R)", "both",
                       "the script is private: there is no code to run (PREREG 6.9)")]
    for s in ev.symbols:
        g = ev.rows(s, "COIL", tf="4H")
        if not len(g):
            out.append(_not_computed(s, "no COIL 4H rows (tradeiq2_rules_coil)"))
            continue
        out.append(_row("our COIL on 4H: profit factor above 1 in most rows", s, "COIL 4H rows",
                        _frac(int((g.profit_factor > 1).sum()), len(g)),
                        _frac(int((ev.val.loc[g.index].profit_factor > 1).sum()), len(g)),
                        T1._most(int((g.profit_factor > 1).sum()), len(g)),
                        T1._most(int((ev.val.loc[g.index].profit_factor > 1).sum()), len(g))))
        for grade in ("BIG", "VOL", "ADX", "ALL3"):
            pairs = ev.swaps(s, "COIL", grade, ("none", "NONE", "G0", None))
            if pairs:
                out.append(_most_row(f"the {grade} grade makes more net than no grade in most pairs", s,
                                     f"COIL-RIB x {grade} against no grade, same exit and timeframe",
                                     ev.count(pairs, _beats)))
    return out


def _ok(x) -> Optional[bool]:
    """A part's yes / no in one window; None when it has none (a NaN, information only)."""
    if x is None or (isinstance(x, (float, np.floating)) and math.isnan(x)):
        return None
    return bool(x)


def claims_table(ev: Evidence, numbers: Optional[Sequence[int]] = None, partial: bool = False
                 ) -> Tuple[pd.DataFrame, List[str]]:
    """Every claim of the registry: its rows with study 1's verdict words (a part holds when it holds in both
    windows, does not hold when it fails in both, mixed otherwise; DEVIATIONS 31 of study 1). A claim whose extra
    or rows are missing: with ``partial`` a 'not computed' row naming what it expected, else the error."""
    rows, errors = [], []
    for n in sorted(CLAIMS if numbers is None else numbers):
        text, fn = CLAIMS[n]
        try:
            got = fn(ev)
        except (MissingExtra, ClaimError) as e:
            got = [_not_computed("both", str(e))]
        errors += [f"claim {n}: {r['note']}" for r in got if r.get("verdict") == "not computed"]
        for r in got:
            r = {"claim": n, **r}
            if not isinstance(r.get("verdict"), str) or not r["verdict"]:
                d, v = _ok(r.get("dev_ok")), _ok(r.get("val_ok"))
                r["verdict"] = "information" if d is None or v is None else T1.verdict(d, v)
            rows.append(r)
    if errors and not partial:
        raise MissingExtra("claims that cannot be computed yet (wire them in EXTRAS or the modules):\n  "
                           + "\n  ".join(errors))
    cols = ["claim", "part", "symbol", "rows", "dev", "val", "dev_ok", "val_ok", "verdict", "note"]
    return pd.DataFrame(rows).reindex(columns=cols), errors


def claims(study_dir: Optional[Path] = None, modules: Optional[Mapping[str, object]] = None, partial: bool = False,
           loader=None, log=print) -> pd.DataFrame:
    """``claims``: PREREG 8's claims on Development and Validation -> claims.csv; once the exam's results exist,
    the hold-out's evidence for information -> claims_holdout.csv; CLAIMS.md."""
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    modules = find_modules() if modules is None else dict(modules)
    grid = read_grid(study_dir)
    res = read_results(study_dir)
    check_complete(res, grid)
    qual = qualification(res)
    present = sorted(set(grid.module))
    stale = stale_code(_read_info(study_dir), CodeSnapshot.take({k: m for k, m in modules.items() if k in present}))
    _warn_stale(stale, "CLAIMS.md", log)
    ev = Evidence(study_dir, res[res.window.isin(["dev", "val"])], grid, qual, modules, loader=loader)
    cl, errors = claims_table(ev, partial=partial)
    write_csv(cl, study_dir / "claims.csv")
    ho = None
    if (study_dir / "results_holdout.csv").exists() and M.frozen():
        h = read_results(study_dir, "results_holdout.csv")
        two = T1.as_two_windows(h, "holdout", "holdout")
        evh = Evidence(study_dir, two, grid, qual, modules, windows=("holdout", "holdout"), loader=loader,
                       market_end=None)
        ho, _ = claims_table(evh, partial=True)
        write_csv(ho, study_dir / "claims_holdout.csv")
    write_text(claims_md(cl, ho, errors, stale), study_dir / "CLAIMS.md")
    log(f"claims: {len(cl)} parts ({len(errors)} claims not computed) -> {study_dir / 'CLAIMS.md'}")
    return cl


def claims_md(cl: pd.DataFrame, ho: Optional[pd.DataFrame], errors: Sequence[str], stale: Sequence[str] = ()) -> str:
    o = ["# TradeIQ's 9 indicators for 2027: the video's claims (PREREG 8)", "",
         f"Written by `python -B -m backtesting.research.tradeiq2 claims` on "
         f"{pd.Timestamp.now(tz='UTC').strftime('%d %b %Y %H:%M')} UTC. Each claim is split into the parts it states; "
         "each part is counted on the rows it is about, per symbol, in Development and in Validation. **A part holds "
         "when it holds in both windows, does not hold when it fails in both, and is mixed otherwise** (study 1's "
         "reading, its DEVIATIONS 31). \"Most\" = more than half; \"every\" = all; a win = strictly more net profit "
         "at x1.0. The claim-check markets (USTECm, EURUSDm, GBPUSDm) are information only.", ""] + \
        stale_banner(stale) + ["## The verdicts", ""]
    hmap = {}
    if ho is not None and len(ho):
        for r in ho.itertuples(index=False):
            ok = _ok(r.dev_ok) if not isinstance(r.dev_ok, str) else (r.dev_ok == "True")
            hmap[(r.claim, r.part, r.symbol)] = (r.verdict if r.verdict in ("cannot be tested", "not computed",
                                                                             "information") or ok is None
                                                 else "holds" if ok else "does not hold")
    rows = [[int(r.claim), r.part, NAME.get(r.symbol, r.symbol), r.dev if isinstance(r.dev, str) else "",
             r.val if isinstance(r.val, str) else "", f"**{r.verdict}**", hmap.get((r.claim, r.part, r.symbol), "-"),
             r.note if isinstance(r.note, str) else ""] for r in cl.itertuples(index=False)]
    o += [_md(["Claim", "Part", "Symbol", "Development", "Validation", "Verdict", "Hold-out (information)", "Note"],
              rows), ""]
    for n in sorted(set(cl.claim)):
        o += [f"**Claim {int(n)}.** {CLAIMS[int(n)][0]}", ""]
        for r in cl[cl.claim == n].itertuples(index=False):
            o.append(f"- {r.part} ({NAME.get(r.symbol, r.symbol)}): **{r.verdict}**.")
        o.append("")
    if errors:
        o += ["## Not computed yet", ""] + [f"- {e}" for e in errors] + [""]
    o += ["## Files", "", "`claims.csv` (Development and Validation), `claims_holdout.csv` (the hold-out, once it "
          "exists), `results_dev_val.csv`, `results_holdout.csv`.", ""]
    return "\n".join(o)


# ───────────────────────────── the report: the tables of RESULTS.md ─────────────────────────────

def counts_table(res: pd.DataFrame, qual: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for s in _symbols_in(qual, ALL_SYMBOLS):
        for f in FAMILIES:
            g = qual[(qual.symbol == s) & (qual.family == f)]
            if not len(g):
                continue
            el = g[g.eligible]
            c = g[g.champion]
            rows.append({"symbol": s, "family": f, "group": GROUP[f], "variants": len(g), "eligible": len(el),
                         "not_eligible": int((~g.eligible).sum()), "dev_net_pos": int((el.dev_net > 0).sum()),
                         "val_net_pos": int((el.val_net > 0).sum()),
                         "both_pos": int(((el.dev_net > 0) & (el.val_net > 0)).sum()), "q1": int(el.q1.sum()),
                         "q1_q2": int((el.q1 & el.q2).sum()), "q1_q3": int((el.q1 & el.q2 & el.q3).sum()),
                         "qualify": int(g.qualifies.sum()), "insufficient_events": int(g.insufficient_events.sum()),
                         "champion": c.vid.iloc[0] if len(c) else "none",
                         "finalist": bool(c.finalist.iloc[0]) if len(c) else False})
    return pd.DataFrame(rows)


def vs_study1_msd(res: pd.DataFrame, grid: pd.DataFrame, modules: Mapping[str, object]) -> pd.DataFrame:
    """PREREG 6.2 / 6.11: each MSD-F4 / MSD-F6 row against study 1's F0, F1 and F2 rows of the same base (their
    published Development and Validation results, reused)."""
    s1 = pd.read_csv(STUDY1_DIR / "results_dev_val.csv", float_precision="round_trip")
    s1d, s1v = s1[s1.window == "dev"].set_index("vid"), s1[s1.window == "val"].set_index("vid")
    d, v = res[res.window == "dev"].set_index("vid"), res[res.window == "val"].set_index("vid")
    rows = []
    for key, var in _pairs_of(grid[grid.family == "MSD-FILTER"]):
        kind = [t for t in ("MSD-F4", "MSD-F6") if t in tokens_of(var.id, dict(var.params))]
        for F, b in study1_pairs(var, modules, set(s1d.index)).items():
            rows.append({"vid": var.id, "study1_vid": b, "symbol": var.symbol, "tf": var.tf,
                         "kind": kind[0] if len(kind) == 1 else "", "study1_filter": F,
                         **_cmp_rows(d.loc[var.id], s1d.loc[b], "dev", "s1"),
                         **_cmp_rows(v.loc[var.id], s1v.loc[b], "val", "s1")})
    return pd.DataFrame(rows)


def filter_tokens(vid: str, family: str) -> List[str]:
    """The filter tokens of a row's id that vs_f0 pairs by: VS_F0_FILTERS, and LO where it is a filter (SP, ORB)."""
    t = id_tokens(vid)[2:]
    f = [x for x in t if x in VS_F0_FILTERS]
    if family in LO_FILTER_FAMILIES and "LO" in t:
        f.append("LO")
    return f


def vs_f0(res: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Each eligible gold / BTC row with one filter token (F1 / F2 / F2-4H / F2-1D / F3 / FR / FS / FD / HV /
    HV+F2-4H, and LO on SP and ORB) against the same row with F0 (its id with the token replaced) or, without such a
    row, its id without the token (SH's F2 / F3 rows against their K2 x E1 row with the script's own 1H EMA200),
    within its script; and the filtered rows without a counterpart."""
    d, v = res[res.window == "dev"].set_index("vid"), res[res.window == "val"].set_index("vid")
    rows, unmatched = [], []
    for vid, r in d[d.eligible & d.symbol.isin(SYMBOLS)].iterrows():
        f = filter_tokens(vid, r.family)
        if len(f) != 1:
            continue
        b, against = swap(vid, f[0], "F0"), "F0"
        if b not in d.index:
            b, against = swap(vid, f[0], None), "the row without the filter token"
        if b is None or b not in d.index or b == vid:
            unmatched.append(vid)
            continue
        rows.append({"vid": vid, "f0_vid": b, "symbol": r.symbol, "tf": r.tf, "script": r.script, "family": r.family,
                     "filter": f[0], "against": against, **_cmp_rows(d.loc[vid], d.loc[b], "dev", "f0"),
                     **_cmp_rows(v.loc[vid], v.loc[b], "val", "f0")})
    return pd.DataFrame(rows), unmatched


COMBO_NAMES = {"TIGHT": "TIGHT against the same ORB rule without it",
               "ORB-CX": "ORB-CX (the COMEX-open range) against the New York range",
               "STK": "STK against RIB alone (same side and timeframe, X0, F0)",
               "WY-DERIVED": "WY-CL / WY-SP against WY-STD x X-S (same filter and timeframe)"}


def _only(cands: Sequence[str]) -> Optional[str]:
    return cands[0] if len(cands) == 1 else None


def combos_table(res: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    PREREG 1's question 3 and 6.11: our combinations against the scripts alone, pair by pair, in Development and
    Validation. TIGHT -> the same ORB row with F0 (or without the token); ORB-CX -> the same row on the New York range
    (the id without 'ORB-CX'); STK -> the RIB row of the same symbol, timeframe and side with X0 and F0; WY-DERIVED ->
    the WY row of the same symbol and timeframe with WY-STD, X-S and the same filter token. The filters against F0
    are ``vs_f0``'s. Returns the pairs and the combination rows without a counterpart.
    """
    d, v = res[res.window == "dev"].set_index("vid"), res[res.window == "val"].set_index("vid")
    el = d[d.eligible & d.symbol.isin(SYMBOLS)]
    tok = {vid: tokens_of(vid, el.at[vid, "params"] if "params" in el.columns else None) for vid in el.index}
    rows, unmatched = [], []
    for vid, r in el.iterrows():
        t = id_tokens(vid)[2:]
        if r.family == "ORB" and "TIGHT" in t:
            name = "TIGHT"
            b = next((x for x in (swap(vid, "TIGHT", "F0"), swap(vid, "TIGHT", None)) if x in d.index), None)
        elif r.family == "ORB" and "ORB-CX" in t:
            name, b = "ORB-CX", swap(vid, "ORB-CX", None)
        elif r.family == "STK":
            name = "STK"
            side = [x for x in ("LS", "LO") if x in tok[vid]]
            b = _only([x for x in el.index if el.at[x, "family"] == "RIB" and el.at[x, "symbol"] == r.symbol
                       and el.at[x, "tf"] == r.tf and len(side) == 1 and {side[0], "X0", "F0"} <= tok[x]
                       and not ({"LS", "LO"} - {side[0]}) & tok[x]]) if len(side) == 1 else None
        elif r.family == "WY-DERIVED":
            name = "WY-DERIVED"
            ft = [x for x in t if x in FILTER_TOKENS]
            b = _only([x for x in el.index if el.at[x, "family"] == "WY" and el.at[x, "symbol"] == r.symbol
                       and el.at[x, "tf"] == r.tf and {"WY-STD", "X-S"} <= set(id_tokens(x)[2:])
                       and [y for y in id_tokens(x)[2:] if y in FILTER_TOKENS] == ft]) if len(ft) == 1 else None
        else:
            continue
        if b is None or b not in d.index or b == vid:
            unmatched.append(vid)
            continue
        rows.append({"combination": COMBO_NAMES[name], "vid": vid, "base_vid": b, "symbol": r.symbol, "tf": r.tf,
                     "family": r.family, **_cmp_rows(d.loc[vid], d.loc[b], "dev", "base"),
                     **_cmp_rows(v.loc[vid], v.loc[b], "val", "base")})
    return pd.DataFrame(rows), unmatched


def study1_best(s1q: pd.DataFrame, symbol: str, tf: str) -> Optional[str]:
    """Study 1's best row of a symbol and timeframe: its qualifier first in its rank order, else its row with the
    highest D+V P/DD (ties: Development's, then the id)."""
    g = s1q[(s1q.symbol == symbol) & (s1q.tf == tf)]
    if not len(g):
        return None
    ok = g[g.qualifies.map(_bool)]
    if len(ok):
        return ok.sort_values("rank").vid.iloc[0]
    return _order(g.set_index("vid"))[0]


def vs_study1_best(res: pd.DataFrame, qual: pd.DataFrame) -> pd.DataFrame:
    s1 = pd.read_csv(STUDY1_DIR / "results_dev_val.csv", float_precision="round_trip").set_index(["vid", "window"])
    s1q = pd.read_csv(STUDY1_DIR / "qualification.csv", float_precision="round_trip")
    idx = res.set_index(["vid", "window"])
    rows = []
    for r in family_best(qual).itertuples(index=False):
        tf = qual.set_index("vid").at[r.vid, "tf"]
        b = study1_best(s1q, r.symbol, tf)
        row = {"symbol": r.symbol, "family": r.family, "vid": r.vid, "champion": r.champion, "tf": tf,
               "study1_vid": b or "none"}
        for w in RUN_WINDOWS:
            a = idx.loc[(r.vid, w)]
            row.update({f"{w}_net": float(a.net), f"{w}_max_dd": float(a.max_dd), f"{w}_profit_dd": float(a.profit_dd)})
            if b is not None:
                c = s1.loc[(b, w)]
                row.update({f"{w}_s1_net": float(c.net), f"{w}_s1_max_dd": float(c.max_dd),
                            f"{w}_s1_profit_dd": float(c.profit_dd),
                            f"{w}_better_pdd": bool(float(a.profit_dd) > float(c.profit_dd))})
        rows.append(row)
    return pd.DataFrame(rows)


def report(study_dir: Optional[Path] = None, modules: Optional[Mapping[str, object]] = None, log=print
           ) -> Dict[str, pd.DataFrame]:
    """``report``: the tables RESULTS.md needs -> counts.csv, vs_study1_msd.csv (+ _summary), vs_f0.csv
    (+ _summary, vs_f0_unmatched.csv), combos.csv (+ _summary, combos_unmatched.csv), vs_study1_best.csv,
    RESULTS_TABLES.md (with buy-and-hold, the champions, the finalists and, once they exist, the exam's verdicts; a
    banner when the code or the environment now differ from run_info.csv's)."""
    study_dir = Path(M.STUDY_DIR if study_dir is None else study_dir)
    modules = find_modules() if modules is None else dict(modules)
    grid = read_grid(study_dir)
    res = read_results(study_dir)
    check_complete(res, grid)
    qual = qualification(res)
    got = {"counts": counts_table(res, qual)}
    if (grid.family == "MSD-FILTER").any():
        vm = vs_study1_msd(res, grid, modules)
        got["vs_study1_msd"] = vm
        got["vs_study1_msd_summary"] = _summary(vm, (("symbol", "kind", "study1_filter"),
                                                     ("symbol", "kind", "study1_filter", "tf")))
    vf, unmatched = vs_f0(res)
    got["vs_f0"] = vf
    got["vs_f0_summary"] = _summary(vf, (("symbol", "filter"), ("symbol", "family", "filter"))) if len(vf) else \
        pd.DataFrame()
    got["vs_f0_unmatched"] = pd.DataFrame({"vid": unmatched})
    cb, cb_unmatched = combos_table(res)
    got["combos"] = cb
    got["combos_summary"] = _summary(cb, (("symbol", "combination"),)) if len(cb) else pd.DataFrame()
    got["combos_unmatched"] = pd.DataFrame({"vid": cb_unmatched})
    got["vs_study1_best"] = vs_study1_best(res, qual)
    for k, df in got.items():
        write_csv(df, study_dir / f"{k}.csv")
    bh = pd.read_csv(study_dir / "buy_and_hold.csv", float_precision="round_trip")
    present = sorted(set(grid.module))
    stale = stale_code(_read_info(study_dir), CodeSnapshot.take({k: m for k, m in modules.items() if k in present}))
    _warn_stale(stale, "RESULTS_TABLES.md", log)
    write_text(results_tables_md(study_dir, qual, got, bh, stale), study_dir / "RESULTS_TABLES.md")
    log(f"report -> {study_dir / 'RESULTS_TABLES.md'}")
    return got


def results_tables_md(study_dir: Path, qual: pd.DataFrame, got: Dict[str, pd.DataFrame], bh: pd.DataFrame,
                      stale: Sequence[str] = ()) -> str:
    o = ["# TradeIQ's 9 indicators for 2027: the tables of RESULTS.md", "",
         f"Written by `python -B -m backtesting.research.tradeiq2 report` on "
         f"{pd.Timestamp.now(tz='UTC').strftime('%d %b %Y %H:%M')} UTC. Per 0.01 lot after costs; Development / "
         "Validation as PREREG 3. The words of RESULTS.md are written from these.", ""] + stale_banner(stale) + [
        "## Counts", ""]
    c = got["counts"]
    o += [_md(["Symbol", "Family", "Variants", "Eligible", "Dev > 0", "Val > 0", "Both", "Rule 1", "1-2", "1-3",
               "Qualify", "Champion"],
              [[NAME.get(r.symbol, r.symbol), r.family, r.variants, r.eligible, r.dev_net_pos, r.val_net_pos, r.both_pos,
                r.q1, r.q1_q2, r.q1_q3, r.qualify, _short(r.champion) if r.champion != "none" else "none"]
               for r in c.itertuples(index=False)]), ""]
    ch = qual[qual.champion].sort_values(["symbol", "champion_rank"])
    ex1, verdicts = _exam_words(study_dir)
    o += ["## The champions and the finalists", "",
          _md(["Symbol", "#", "Family", "Champion", "Finalist", "Dev net", "Val net", "D+V net", "D+V DD", "D+V P/DD",
               "Exam", "Note"],
              [[NAME[r.symbol], int(r.champion_rank), r.family, _short(r.vid), "yes" if r.finalist else "",
                _usd(r.dev_net), _usd(r.val_net), _usd(r.devval_net), _dd(r.devval_max_dd), _num(r.devval_profit_dd),
                verdicts.get(r.vid, "-"), legs_note(getattr(r, "legs", 1))] for r in ch.itertuples(index=False)]), ""]
    if "vs_study1_msd_summary" in got and len(got["vs_study1_msd_summary"]):
        s = got["vs_study1_msd_summary"]
        s = s[s.by == "kind+study1_filter"]
        o += ["## The dashboard as a filter on study 1's rules (MSD-F4 / F6 against study 1's F0, F1, F2)", "",
              _md(["Symbol", "Kind", "Study-1 filter", "Pairs", "Dev wins (net)", "Dev wins (P/DD)", "Val wins (net)",
                   "Val wins (P/DD)", "Verdict"],
                  [[NAME[r.symbol], r.kind, r.study1_filter, r.n, r.dev_wins_net, f"{r.dev_wins_pdd}/{r.dev_n_pdd}",
                    r.val_wins_net, f"{r.val_wins_pdd}/{r.val_n_pdd}", f"**{r.verdict}**"]
                   for r in s.itertuples(index=False)]), ""]
    if len(got.get("vs_f0_summary", [])):
        s = got["vs_f0_summary"]
        s = s[s.by == "filter"]
        o += ["## The filters against no filter, within a script", "",
              _md(["Symbol", "Filter", "Pairs", "Dev wins (net)", "Dev wins (P/DD)", "Val wins (net)",
                   "Val wins (P/DD)", "Verdict"],
                  [[NAME[r.symbol], r["filter"], r.n, r.dev_wins_net, f"{r.dev_wins_pdd}/{r.dev_n_pdd}",
                    r.val_wins_net, f"{r.val_wins_pdd}/{r.val_n_pdd}", f"**{r.verdict}**"]
                   for _, r in s.iterrows()]), ""]
    if len(got.get("combos_summary", [])):
        s = got["combos_summary"]
        o += ["## Our combinations against the scripts alone (PREREG 1 question 3, 6.11)", "",
              _md(["Symbol", "Combination", "Pairs", "Dev wins (net)", "Dev wins (P/DD)", "Val wins (net)",
                   "Val wins (P/DD)", "Verdict"],
                  [[NAME[r.symbol], r.combination, r.n, r.dev_wins_net, f"{r.dev_wins_pdd}/{r.dev_n_pdd}",
                    r.val_wins_net, f"{r.val_wins_pdd}/{r.val_n_pdd}", f"**{r.verdict}**"]
                   for _, r in s.iterrows()]), "",
              "The filters of 6.11 (RIB x F2 / FR / FS / F3, SP x FD / F2, SH x F2 / F3, ORB x HV / F2, HP x F2 / FR) "
              "are the table above; `combos_unmatched.csv` lists the combination rows without a counterpart.", ""]
    b = got["vs_study1_best"]
    if len(b):
        o += ["## Each family's best row against study 1's best of the same symbol and timeframe", "",
              _md(["Symbol", "Family", "Best row", "Champion", "D+V P/DD", "Study 1's best", "Its D+V P/DD",
                   "Better (D+V P/DD)"],
                  [[NAME[r.symbol], r.family, _short(r.vid), "yes" if r.champion else "", _num(r.devval_profit_dd),
                    _short(r.study1_vid) if r.study1_vid != "none" else "none",
                    _num(getattr(r, "devval_s1_profit_dd", np.nan)),
                    _yes(getattr(r, "devval_better_pdd", np.nan))] for r in b.itertuples(index=False)]), ""]
    if len(bh):
        o += ["## Buy-and-hold of 0.01 lot", "",
              _md(["Symbol", "Window", "Cost", "Net", "Max DD", "P/DD"],
                  [[NAME.get(r.symbol, r.symbol), r.window, r.cost, _usd(r.bh_net), _dd(r.bh_max_dd),
                    _num(r.bh_profit_dd)] for r in bh.itertuples(index=False)]), ""]
    return "\n".join(o)


# ───────────────────────────── command line ─────────────────────────────

def _grid_command(study_dir: Path, modules, counts, log=print) -> pd.DataFrame:
    _refuse_test_options(study_dir, "grid", modules, counts)
    for k, m in modules.items():
        _require_api(k, m)
    pairs, problems = collect(modules)
    g = grid_frame(pairs)
    rep = count_report(g, PREREG_COUNTS if counts is None else counts, modules)
    with pd.option_context("display.width", 200, "display.max_colwidth", 90, "display.max_rows", 500):
        log(rep.to_string(index=False))
    for s in _symbols_in(g, ALL_SYMBOLS):
        e = int(g[(g.symbol == s)].eligible.sum())
        log(f"{s}: {int((g.symbol == s).sum())} variants, {e} eligible"
            + (f" (the plan: {PLAN_ELIGIBLE[s]})" if s in PLAN_ELIGIBLE and not _missing_modules(modules) else ""))
    if _missing_modules(modules):
        log(f"rule modules not found: {', '.join(_missing_modules(modules))}")
    checked_grid(modules, counts)                           # raises GridError with every difference
    if (Path(study_dir) / FINALISTS_MD).exists() or (Path(study_dir) / (FINALISTS_MD + ".sha256")).exists():
        same = (Path(study_dir) / "grid.csv").exists() and _grid_matches(read_grid(study_dir), g)
        log(f"note: FINALISTS.md exists: grid.csv (frozen) is not rewritten; it is {'' if same else 'NOT '}this grid")
        return g
    _write_grid(study_dir, g, log)
    log(f"total {len(g)} variants -> {study_dir / 'grid.csv'}")
    return g


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m backtesting.research.tradeiq2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cmds = {"grid": "PREREG 6: the variants, their ids and counts -> grid.csv",
            "run": "Development and Validation of every variant (resumable) -> results_dev_val.csv ...",
            "select": "PREREG 7: qualifiers, champions, finalists -> CANDIDATES.md, FINALISTS.draft.md",
            "freeze": "PREREG 7: FINALISTS.md and its sha256 (once)",
            "exam": "PREREG 7: the champions' exams and the base rate (frozen only) -> exam.csv, EXAM.md",
            "accounts": "PREREG 7's $2,000 accounts and the comparison page's files (frozen only)",
            "claims": "PREREG 8: the video's claims -> claims.csv, CLAIMS.md",
            "report": "the tables of RESULTS.md -> RESULTS_TABLES.md"}
    p = {}
    for c, h in cmds.items():
        p[c] = sub.add_parser(c, help=h)
        p[c].add_argument("--study-dir", type=Path, default=None, help="default backtest_results/tradeiq_2027")
        p[c].add_argument("--rules", default=None, help="a module (or .py) whose MODULES replaces the rule modules "
                                                        "(tests only)")
    p["run"].add_argument("--symbols", nargs="+", choices=ALL_SYMBOLS, default=None)
    p["run"].add_argument("--modules", nargs="+", choices=MODULE_KEYS, default=None)
    for c in ("run", "exam", "accounts"):
        p[c].add_argument("--workers", type=int, default=2)
    p["exam"].add_argument("--no-base-rate", action="store_true")
    p["exam"].add_argument("--no-recheck", action="store_true",
                           help="skip every variant's look-ahead check (D, V and D+V again on the data to the data end)")
    for c in ("exam", "accounts"):
        p[c].add_argument("--allow-code-change", action="store_true",
                          help="compute with result code other than FINALISTS.md's (recorded)")
    p["accounts"].add_argument("--compare-dir", type=Path, default=None,
                               help="default backtest_results/compare/data")
    p["accounts"].add_argument("--no-references", action="store_true",
                               help="leave out buy-and-hold, study 1's finalists and the bots' designs")
    p["claims"].add_argument("--partial", action="store_true", help="write the claims that can be computed")
    a = ap.parse_args(argv)
    if a.rules and (a.study_dir is None or _is_real(a.study_dir)):
        print(f"StudyFolderError: --rules is for tests: give --study-dir, a folder other than {REAL_STUDY_DIR}",
              file=sys.stderr)
        return 2
    study_dir = Path(M.STUDY_DIR if a.study_dir is None else a.study_dir)
    modules, counts, loader = load_rules(a.rules) if a.rules else (find_modules(), None, None)
    try:
        if a.cmd == "grid":
            _grid_command(study_dir, modules, counts)
        elif a.cmd == "run":
            run(study_dir, modules, counts, symbols=a.symbols, keys=a.modules, workers=a.workers, loader=loader)
        elif a.cmd == "select":
            select(study_dir, modules)
        elif a.cmd == "freeze":
            freeze(study_dir, modules, counts, require_all=a.rules is None, loader=loader)
        elif a.cmd == "exam":
            exam(study_dir, modules, counts, workers=a.workers, loader=loader, base_rate=not a.no_base_rate,
                 recheck=not a.no_recheck, allow_code_change=a.allow_code_change)
        elif a.cmd == "accounts":
            accounts(study_dir, a.compare_dir, modules, counts, workers=a.workers, loader=loader,
                     allow_code_change=a.allow_code_change, references=not a.no_references)
        elif a.cmd == "claims":
            claims(study_dir, modules, partial=a.partial, loader=loader)
        elif a.cmd == "report":
            report(study_dir, modules)
    except (GridError, MissingExtra, FileExistsError, M.HoldOutError, StudyFolderError, CodeChangedError,
            FrozenInputsError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
