"""
The comparison page: every backtest of the repository that uses the bot's $2,000 account, side by side, per symbol.

    python3 -B -m backtesting.research.compare_page export      # contract files from the studies' result files
    python3 -B -m backtesting.research.compare_page compute     # study 1 and buy-and-hold on 5y and 1y (M1 bars >= 2019)
    python3 -B -m backtesting.research.compare_page check       # validate every contract file in the data folder
    python3 -B -m backtesting.research.compare_page build       # backtest_results/compare/index.html from the data folder
    python3 -B -m backtesting.research.compare_page all         # export, compute, check, build

    # later, once study 2's exam is written (backtest_results/tradeiq_2027/EXAM.md; gold 2017-2018 is its sealed
    # Early window), study 1 and buy-and-hold on 8y and new:
    python3 -B -m backtesting.research.compare_page compute --windows 8y,new --allow-pre-2019
    python3 -B -m backtesting.research.compare_page build

The owner's request (28 Nov 2026): "In final results set create html page with equity graphs of all backtesting results
so that i can compare and get Profit and max DD and all other things which you already do."

THE CONTRACT (v2; a v1 file, without the optional columns, is still valid). ``backtest_results/compare/data/`` holds
one set of files per source ``<sid>``:
  ``<sid>__series.csv``   one row per series (SERIES_COLS, then optionally SERIES_OPT)
  ``<sid>__metrics.csv``  one row per (series_id, window, cost, basis) (METRICS_COLS, then optionally METRICS_OPT)
  ``<sid>__curves_<window>.csv.gz``   series_id, date, equity_usd: the account's equity at the end of each UTC day (its
                          last mark, open positions marked), account basis, cost x1.0; the first row is dated the day
                          before the window starts and holds the $2,000 the account starts with.
Studies 2 (``tradeiq_2027``) and 3 (``bot_filters``) write their own files in this format; ``build`` shows them as
"pending" until their files exist. README.md in the same folder states every definition and its source.

``max_dd_usd`` and ``p_dd`` are on the same marks as ``max_dd_pct`` (the row's ``dd_marks``) or empty: a drawdown in $
read off a coarser curve is never put in them. The page adds the drawdown at daily closes as its own, marked column.

THE HARD RULES this module keeps (the workflow's):
* Nothing of study 2's rule modules is imported or run, and its guard is not touched: this module never imports a
  ``tradeiq2_*`` module.
* No profit or loss is computed on M1 bars before 2019-01-01, and none are even loaded, unless ``--allow-pre-2019`` is
  given (the later 8y / new run), which also needs study 2's exam file (``tradeiq_2027/EXAM.md``) to exist. Study 1's
  markets are built by its own ``TMarket`` from the store's bars from 2019-01-01 on (``market_from``);
  ``tradeiq_checks`` shows that this gives study 1's own numbers.
* ``bot_filters/dev_*.csv`` is never opened; nothing under ``backtest_results/`` outside ``compare/`` is written.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import REPO_ROOT

RESULTS = REPO_ROOT / "backtest_results"
OUT = RESULTS / "compare"
DATA = OUT / "data"
PAGE = OUT / "index.html"
SYMBOLS = ("XAUUSDm", "BTCUSDm")
SYMBOL_NAME = {"XAUUSDm": "Gold (XAUUSDm)", "BTCUSDm": "BTC (BTCUSDm)"}
ACCOUNT = 2000.0
DAY_S = 86400
YEAR_S = 365.25 * DAY_S
SEALED_BEFORE = "2019-01-01"          # workflow rule 1: nothing is computed on bars before this instant (both symbols)
GZ = {"method": "gzip", "mtime": 0}   # reproducible gzip bytes

# the common windows: [start, end) UTC, final10's (final10.WINDOWS)
COMMON = {"5y": ("2021-11-13", "2026-11-13"), "8y": ("2018-11-13", "2026-11-13"),
          "new": ("2018-11-13", "2021-01-01"), "1y": ("2025-11-13", "2026-11-13")}
COMMON_ORDER = ("5y", "8y", "new", "1y")
# the studies' own windows, named after the study that owns them: (owner, text)
WINDOW_META = {
    "5y": ("", "13 Nov 2021 - 13 Nov 2026, five years"), "8y": ("", "13 Nov 2018 - 13 Nov 2026, eight years"),
    "new": ("", "13 Nov 2018 - 1 Jan 2021, FINAL10's fair test"), "1y": ("", "13 Nov 2025 - 13 Nov 2026, the last year"),
    "dev": ("Study 1", "study 1's development, 2019 - 2022"),
    "val": ("Study 1", "study 1's validation, 2023 - Jun 2024"),
    "devval": ("Study 1", "study 1's development + validation, 2019 - Jun 2024"),
    "holdout": ("Study 1", "study 1's hold-out, 1 Jul 2024 to the data end"),
    "full": ("Study 1", "study 1's full span, 2019 to the data end"),
    "bots-full": ("Study 1's rebuilds of the bots' designs", "the bots' designs rebuilt by study 1, 2019 - 13 Nov 2026"),
    "bots-holdout": ("Study 1's rebuilds of the bots' designs",
                     "the bots' designs rebuilt by study 1, 1 Jul 2024 - 13 Nov 2026"),
    "sel": ("Multisymbol", "multisymbol's selection half, 13 Nov 2021 - 13 May 2024"),
    "conf": ("Multisymbol", "multisymbol's confirmation half, 13 May 2024 - 13 Nov 2026"),
    "tsel": ("Multisymbol", "multisymbol's Turtle selection, 13 Nov 2018 - 13 May 2024"),
    "since 2020": ("Balke", "Balke's span, 1 Jul 2020 - 13 Nov 2026"),
    "early": ("Study 2", "study 2's Early window, 2017 - 2018 (gold)"),
}
WINDOW_TEXT = {k: v[1] for k, v in WINDOW_META.items()}
# the windows of other studies that buy-and-hold is computed on as well (all from 2019 on), so that every window with an
# account curve has the benchmark over exactly its span
BH_EXTRA = {"bots-full": ("2019-01-01", "2026-11-13"), "bots-holdout": ("2024-07-01", "2026-11-13"),
            "sel": ("2021-11-13", "2024-05-13"), "conf": ("2024-05-13", "2026-11-13"),
            "since 2020": ("2020-07-01", "2026-11-13")}
# study 1's rebuilds of the bots' designs (curves_bots_*): their own window keys, because FINAL10's trades end on
# 13 Nov 2026 while study 1's full and hold-out run to the data end
REBUILD_WINDOW = {"full": "bots-full", "holdout": "bots-holdout"}
STUDY2_EXAM = RESULTS / "tradeiq_2027" / "EXAM.md"

# ───────────────────────────── the contract ─────────────────────────────

SERIES_COLS = ["series_id", "source", "study", "symbol", "label", "kind", "family", "tf", "filter", "role",
               "eligible", "exam", "notes"]
METRICS_COLS = ["series_id", "window", "start", "end", "cost", "basis", "start_usd", "final_usd", "net_usd",
                "return_pct", "cagr_pct", "max_dd_usd", "max_dd_pct", "p_dd", "trades", "win_rate_pct",
                "profit_factor", "sharpe_w", "pos_quarters_pct", "worst_quarter_usd", "wiped", "dd_marks",
                "score_final10", "source_file"]
# v2's optional columns (after the v1 ones, in this order; a file may leave out any of them):
# series: sizing ("" = the unit rule), tags (short ';'-separated badges the page shows on the row)
# metrics: sample (in / out / mixed / "": was the window part of the data that chose this row?), derived (the fields
#          compare_page computed, comma-separated), row_notes (caveats of this row)
SERIES_OPT = ["sizing", "tags"]
METRICS_OPT = ["sample", "derived", "row_notes"]
CURVE_COLS = ["series_id", "date", "equity_usd"]
KINDS = ("bot", "bot+filter", "rule", "benchmark")
ROLES = ("design", "base", "finalist", "champion", "qualified", "variant", "benchmark")
EXAMS = ("pass", "fail", "")
DD_MARKS = ("tick", "second", "M1", "hour", "day")
BASES = ("account", "unit")
SIZINGS = ("", "unit rule", "risk-sized", "fully invested", "0.01 lot fixed")
SAMPLES = ("in", "out", "mixed", "")
DERIVABLE = ("return_pct", "cagr_pct", "max_dd_usd", "p_dd", "profit_factor", "sharpe_w", "pos_quarters_pct",
             "worst_quarter_usd")
# rounding of what the contract files carry (the studies' own numbers keep these digits)
ROUND = {"start_usd": 2, "final_usd": 4, "net_usd": 4, "return_pct": 4, "cagr_pct": 4, "max_dd_usd": 4,
         "max_dd_pct": 4, "p_dd": 6, "win_rate_pct": 4, "profit_factor": 6, "sharpe_w": 6, "pos_quarters_pct": 4,
         "worst_quarter_usd": 4, "score_final10": 6}

# the sources this page knows (the page's colour groups follow them; any other source is "earlier studies")
SOURCES = {
    "final10": dict(study="FINAL10 - the bots' designs and the final ten", short="FINAL10"),
    "tradeiq_rsi": dict(study="TradeIQ video 1 - four RSI replacements", short="TradeIQ 1 (RSI)"),
    "tradeiq_2027": dict(study="TradeIQ video 2 - nine indicators for 2027", short="TradeIQ 2 (2027)",
                         pending="study 2 is running now (pre-registered); its files arrive after its freeze and "
                                 "exam"),
    "bot_filters": dict(study="Entry filters on the bots' designs", short="Bot filters",
                        pending="study 3 is running now (pre-registered); its accounts arrive after its exam"),
    "benchmarks": dict(study="Buy-and-hold benchmarks", short="Buy and hold"),
    "balke": dict(study="René Balke's Four Edge strategies (bot unit rule)", short="Balke"),
    "ladder": dict(study="DCA ladder search (the live ladder family)", short="Ladder"),
}
EXPECTED_SOURCES = ("final10", "tradeiq_rsi", "tradeiq_2027", "bot_filters", "benchmarks", "balke", "ladder")
# what the page says about a window computed later (reader text; the command is in README.md)
LATER = "they arrive after study 2's exam (bars before 2019 are sealed until then)"
# (source, window) pairs that are expected but computed later
PENDING_WINDOWS = {("tradeiq_rsi", "8y"): LATER, ("tradeiq_rsi", "new"): LATER,
                   ("benchmarks", "8y"): LATER, ("benchmarks", "new"): LATER}


def _iso(x) -> str:
    """The UTC date (YYYY-MM-DD) of an ISO string, a Timestamp or a date."""
    if isinstance(x, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x):
        return x
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.strftime("%Y-%m-%d")


def _dnum(x) -> int:
    """Days since 1970-01-01 of a date."""
    return int((pd.Timestamp(_iso(x)) - pd.Timestamp("1970-01-01")).days)


def _dstr(n: int) -> str:
    return (date(1970, 1, 1) + timedelta(days=int(n))).isoformat()


def _dnums(days) -> np.ndarray:
    """Days since 1970-01-01 of many dates at once: ISO date strings (the fast path), timestamps or ISO times."""
    a = np.asarray(days)
    if a.dtype.kind in "iu":
        return a.astype(np.int64)
    try:
        return a.astype("datetime64[D]").astype(np.int64)
    except (ValueError, TypeError):
        return np.asarray([_dnum(x) for x in a], np.int64)


def _days_of(times) -> np.ndarray:
    """The UTC day numbers of ISO dates, ISO times with an offset (final10's "2021-11-14 23:05:00+00:00") or epoch
    day numbers, vectorised."""
    a = np.asarray(times)
    if a.dtype.kind in "iu":
        return a.astype(np.int64)
    if len(a) == 0:
        return np.zeros(0, np.int64)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(a[0])):
        return a.astype("datetime64[D]").astype(np.int64)
    t = pd.to_datetime(pd.Series(a), utc=True, format="ISO8601").dt.tz_localize(None)
    return t.to_numpy().astype("datetime64[D]").astype(np.int64)


def _dstrs(n) -> List[str]:
    return np.asarray(n, np.int64).astype("datetime64[D]").astype(str).tolist()


def _s(x) -> int:
    """UTC epoch seconds of an ISO string or a Timestamp."""
    t = pd.Timestamp(x)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return int(t.value // 10**9)


def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _blank(x) -> bool:
    return _num(x) is None


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _finish_metrics(rows: List[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in METRICS_COLS + METRICS_OPT:
        if c not in df:
            df[c] = ""
    df = df[METRICS_COLS + METRICS_OPT].copy()
    for c, nd in ROUND.items():
        df[c] = [("" if _blank(v) else round(float(v), nd)) for v in df[c]]
    df["cost"] = [float(c) for c in df["cost"]]
    df["trades"] = [("" if _blank(v) else int(round(float(v)))) for v in df["trades"]]
    df["wiped"] = [int(bool(int(v))) if not _blank(v) else 0 for v in df["wiped"]]
    for c in METRICS_OPT:
        df[c] = df[c].fillna("").astype(str)
    return df


def _finish_series(rows: List[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in SERIES_COLS + SERIES_OPT:
        if c not in df:
            df[c] = ""
    df = df[SERIES_COLS + SERIES_OPT].copy()
    df["eligible"] = [int(bool(int(v))) if not _blank(v) else 0 for v in df["eligible"]]
    return df.fillna("")


def _with_optional(df: pd.DataFrame, required: List[str], optional: List[str]) -> pd.DataFrame:
    """A contract frame with every v2 column: the optional ones a v1 file leaves out are added empty."""
    df = df.copy()
    for c in optional:
        if c not in df:
            df[c] = ""
    return df[required + optional]


def write_source(sid: str, series: Optional[pd.DataFrame] = None, metrics: Optional[pd.DataFrame] = None,
                 curves: Optional[Dict[str, pd.DataFrame]] = None, data: Path = DATA, replace: bool = False) -> None:
    """
    Write a source's contract files (v2: every optional column, empty where not given). With ``replace`` the files
    are rewritten from what is given; otherwise rows are merged: a series row replaces the row with its series_id, a
    metrics row the row with its (series_id, window, cost, basis), and a curve file keeps the series it is not given.
    """
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    if series is not None:
        p = data / f"{sid}__series.csv"
        df = _with_optional(series, SERIES_COLS, SERIES_OPT)
        if p.exists() and not replace:
            old = _with_optional(pd.read_csv(p, dtype=str, keep_default_na=False), SERIES_COLS, SERIES_OPT)
            df = pd.concat([old[~old.series_id.isin(set(df.series_id))], df.astype(str)], ignore_index=True)
        if df.series_id.duplicated().any():
            raise ValueError(f"{sid}: duplicate series ids")
        df.to_csv(p, index=False)
    if metrics is not None:
        p = data / f"{sid}__metrics.csv"
        df = _with_optional(metrics, METRICS_COLS, METRICS_OPT)
        key = ["series_id", "window", "cost", "basis"]
        if p.exists() and not replace:
            old = _with_optional(pd.read_csv(p, dtype=str, keep_default_na=False), METRICS_COLS, METRICS_OPT)
            new_keys = set(map(tuple, df[key].astype(str).assign(cost=df.cost.map(lambda c: f"{float(c):g}"))
                               .values.tolist()))
            ok = [tuple(r) not in new_keys for r in old[key].assign(cost=old.cost.map(lambda c: f"{float(c):g}"))
                  .values.tolist()]
            df = pd.concat([old[ok], df.astype(str)], ignore_index=True)
        dfk = df[key].astype(str).assign(cost=df.cost.map(lambda c: f"{float(c):g}"))
        if dfk.duplicated().any():
            raise ValueError(f"{sid}: duplicate metrics rows")
        order = {w: i for i, w in enumerate(COMMON_ORDER)}
        df = df.assign(_w=df.window.map(lambda w: order.get(w, 99)), _c=df.cost.map(float)).sort_values(
            ["series_id", "_w", "window", "basis", "_c"], kind="stable").drop(columns=["_w", "_c"])
        df.to_csv(p, index=False)
    if replace and curves is not None:
        keep = {curve_file(sid, w, data).name for w in curves}
        for p in data.glob(f"{sid}__curves_*.csv.gz"):          # a window the source no longer has
            if p.name not in keep:
                p.unlink()
    for w, cv in (curves or {}).items():
        p = curve_file(sid, w, data)
        df = cv[CURVE_COLS].copy()
        df["equity_usd"] = df["equity_usd"].astype(float).round(2)
        if p.exists() and not replace:
            old = pd.read_csv(p, dtype={"series_id": str, "date": str})
            df = pd.concat([old[~old.series_id.isin(set(df.series_id))], df], ignore_index=True)
        df = df.sort_values(["series_id", "date"], kind="stable")
        df.to_csv(p, index=False, compression=GZ)


def curve_file(sid: str, window: str, data: Path = DATA) -> Path:
    """The curve file of a source's window (characters other than letters, digits, '.' and '-' become '_' in the
    name: balke's window "since 2020" is ``balke__curves_since_2020.csv.gz``)."""
    return Path(data) / f"{sid}__curves_{re.sub(r'[^A-Za-z0-9.-]', '_', window)}.csv.gz"


def sources_in(data: Path = DATA) -> List[str]:
    return sorted(p.name[: -len("__series.csv")] for p in Path(data).glob("*__series.csv"))


def _columns_ok(cols: List[str], required: List[str], optional: List[str]) -> bool:
    """v1 (the required columns exactly) or v2 (then any of the optional ones, in their order)."""
    cols = list(cols)
    if cols[: len(required)] != required:
        return False
    rest = cols[len(required):]
    return rest == [c for c in optional if c in rest]


def read_source(sid: str, data: Path = DATA, raw: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame,
                                                                          Dict[str, pd.DataFrame]]:
    """A source's files; the optional v2 columns a v1 file leaves out are added empty (``raw``: the files as they are,
    for ``validate``)."""
    data = Path(data)
    s = pd.read_csv(data / f"{sid}__series.csv", dtype=str, keep_default_na=False)
    mp = data / f"{sid}__metrics.csv"
    m = pd.read_csv(mp, dtype=str, keep_default_na=False) if mp.exists() else pd.DataFrame(columns=METRICS_COLS)
    if not raw:
        if _columns_ok(s.columns, SERIES_COLS, SERIES_OPT):
            s = _with_optional(s, SERIES_COLS, SERIES_OPT)
        if _columns_ok(m.columns, METRICS_COLS, METRICS_OPT):
            m = _with_optional(m, METRICS_COLS, METRICS_OPT)
    cv = {}
    for w in sorted(set(m.window)):
        p = curve_file(sid, w, data)
        if p.exists():
            cv[w] = pd.read_csv(p, dtype={"series_id": str, "date": str})
    return s, m, cv


# ───────────────────────────── curve conventions ─────────────────────────────

def eod_from_sod(days, values, final: float, start, start_usd: float = ACCOUNT) -> pd.DataFrame:
    """
    final10's and balke's curves: the equity at the START of each day with a mark (its first mark; the first point is
    the account's start), and the final equity at the window's end. The end of day D is the next day's opening mark
    (the last day's end is the final equity); the opening row is dated the day before the window starts.
    """
    d = _days_of(days)
    v = np.asarray(values, np.float64)
    if len(d) == 0:
        raise ValueError("an empty curve")
    keep = np.r_[d[1:] != d[:-1], True]                 # one mark per day: the last one of the day
    d, v = d[keep], v[keep]
    if np.any(np.diff(d) <= 0):
        raise ValueError("curve days are not increasing")
    s0 = _dnum(start)
    if d[0] < s0:
        raise ValueError("a curve point before its window")
    dates = np.r_[s0 - 1, d]
    eq = np.r_[start_usd, v[1:], float(final)]
    return pd.DataFrame({"date": _dstrs(dates), "equity_usd": eq})


def eod_from_midnights(times_s, values, has_mark=None) -> pd.DataFrame:
    """
    Study 1's curves: the equity at each UTC midnight (the close mark of the last M1 bar before it), with the window's
    start first and its end (after the closing fill) last. A midnight's equity is the end of the day before it.
    ``has_mark``: per point, whether that day had an M1 bar (study 1's ``worst`` column is NaN where it had none);
    rows of days without a mark are dropped, the opening and the closing rows are kept.
    """
    t = np.asarray(times_s, np.int64)
    v = np.asarray(values, np.float64)
    d = (t - 1) // DAY_S
    keep = np.ones(len(t), bool)
    if has_mark is not None:
        keep = np.asarray(has_mark, bool).copy()
    keep[0] = keep[-1] = True
    d, v = d[keep], v[keep]
    last = np.r_[d[1:] != d[:-1], True]
    d, v = d[last], v[last]
    if np.any(np.diff(d) <= 0):
        raise ValueError("curve days are not increasing")
    return pd.DataFrame({"date": _dstrs(d), "equity_usd": v})


def eod_from_daily(days, values, start, start_usd: float = ACCOUNT) -> pd.DataFrame:
    """End-of-day marks (multisymbol's daily.csv: the last mark of each UTC day) with the opening row added."""
    d = _dnums(days)
    v = np.asarray(values, np.float64)
    s0 = _dnum(start)
    m = d >= s0
    return pd.DataFrame({"date": _dstrs(np.r_[s0 - 1, d[m]]), "equity_usd": np.r_[start_usd, v[m]]})


def _edges(a_day: int, z_day: int, kind: str) -> np.ndarray:
    """Day numbers of the period edges strictly inside (a, z): Saturdays (weeks from Saturday 00:00 UTC, study 1's
    and multisymbol's weeks), calendar-quarter starts or month starts."""
    if kind == "week":
        first = a_day + 1 + ((5 - ((a_day + 1 + 3) % 7)) % 7)        # (day + 3) % 7: 0 = Monday, 5 = Saturday
        e = np.arange(first, z_day, 7, dtype=np.int64)
    else:
        step = {"quarter": "QS", "month": "MS"}[kind]
        r = pd.date_range(pd.Timestamp(_dstr(a_day)), pd.Timestamp(_dstr(z_day)), freq=step)
        e = np.asarray([(x - pd.Timestamp("1970-01-01")).days for x in r], np.int64)
    return e[(e > a_day) & (e < z_day)]


def curve_stats(dates, equity, start, end, start_usd: float = ACCOUNT) -> Dict[str, object]:
    """
    What the page computes uniformly from an end-of-day curve when a source does not give it (README, "derived"):
    CAGR; weekly Sharpe (weekly P/L in $, weeks from Saturday 00:00 UTC, the partial first and last included, mean /
    sd x sqrt(52), as study 1 scores a unit); % positive calendar quarters and the worst quarter in $ (partial
    quarters included, as study 1); the worst calendar month in $ and the losing months; the max drawdown in $ and %
    on the daily marks; the longest time under water in days. The equity at a period edge (00:00 UTC) is the last row
    dated before it; the last row is the final equity.
    """
    d = _dnums(dates)
    e = np.asarray(equity, np.float64)
    a_day, z_day = _dnum(start), _dnum(end)
    out: Dict[str, object] = {}
    if len(e) == 0:
        return out
    final = float(e[-1])

    def at(edges):
        i = np.searchsorted(d, edges - 1, side="right") - 1
        return np.where(i >= 0, e[np.maximum(i, 0)], start_usd)

    def per(kind):
        x = _edges(a_day, z_day, kind)
        return np.diff(np.r_[start_usd, at(x), final])

    wk, q, mo = per("week"), per("quarter"), per("month")
    sd = float(np.std(wk, ddof=1)) if len(wk) > 2 else 0.0
    out["sharpe_w"] = float(np.mean(wk) / sd * math.sqrt(52.0)) if sd > 0 else None
    out["pos_quarters_pct"] = float((q > 0).mean() * 100.0) if len(q) else None
    out["worst_quarter_usd"] = float(q.min()) if len(q) else None
    out["worst_month_usd"] = float(mo.min()) if len(mo) else None
    out["losing_months"] = int((mo < 0).sum())
    out["months"] = int(len(mo))
    peak = np.maximum.accumulate(e)
    out["max_dd_usd_daily"] = float(np.max(peak - e))
    with np.errstate(divide="ignore", invalid="ignore"):
        ddp = np.where(peak > 0, (peak - e) / peak, 0.0)
    out["max_dd_pct_daily"] = float(ddp.max() * 100.0)
    under = e < peak - 1e-9
    longest = 0
    if under.any():
        u = under.astype(np.int8)
        starts = np.flatnonzero(np.diff(np.r_[0, u]) == 1)          # first row under water of each stretch
        ends = np.flatnonzero(np.diff(np.r_[u, 0]) == -1) + 1       # first row back at the peak (or past the end)
        back = np.where(ends < len(d), d[np.minimum(ends, len(d) - 1)], z_day)
        longest = int(np.max(back - d[starts]))
    out["underwater_days"] = longest
    yrs = (z_day - a_day) * DAY_S / YEAR_S
    if start_usd > 0 and yrs > 0:
        out["cagr_pct"] = ((final / start_usd) ** (1.0 / yrs) - 1.0) * 100.0 if final > 0 else -100.0
    return out


def _derived(row: dict, *fields: str) -> None:
    """Add fields to the row's ``derived`` list (the fields compare_page computed, not the study)."""
    have = [x for x in str(row.get("derived") or "").split(",") if x]
    for f in fields:
        if f not in have:
            have.append(f)
    row["derived"] = ",".join(sorted(have, key=lambda x: DERIVABLE.index(x) if x in DERIVABLE else 99))


def fill_from_curve(row: dict, curve: Optional[pd.DataFrame], stats: Optional[dict] = None) -> dict:
    """
    Fill a metrics row's missing fields from its curve (README, "derived"), the source's own values kept, and list
    what was filled in ``derived``. The max DD in $ (and P/DD) is filled only when the row's own drawdown is on daily
    marks: a $ figure off the daily curve next to a % on finer marks would understate it (the page shows the daily
    figure in its own column).
    """
    if curve is None or not len(curve) or row.get("basis") != "account":
        return row
    st = stats if stats is not None else curve_stats(curve.date.to_numpy(), curve.equity_usd.to_numpy(np.float64),
                                                     row["start"], row["end"], float(row.get("start_usd") or ACCOUNT))
    if _blank(row.get("return_pct")) and not _blank(row.get("net_usd")):
        row["return_pct"] = float(row["net_usd"]) / float(row.get("start_usd") or ACCOUNT) * 100.0
        _derived(row, "return_pct")
    if _blank(row.get("max_dd_usd")) and row.get("dd_marks") == "day" and st.get("max_dd_usd_daily") is not None:
        row["max_dd_usd"] = st["max_dd_usd_daily"]
        _derived(row, "max_dd_usd")
    for k in ("cagr_pct", "sharpe_w", "pos_quarters_pct", "worst_quarter_usd"):
        if _blank(row.get(k)) and st.get(k) is not None:
            row[k] = st[k]
            _derived(row, k)
    if _blank(row.get("p_dd")) and not _blank(row.get("max_dd_usd")) and float(row["max_dd_usd"]) > 0:
        row["p_dd"] = float(row["net_usd"]) / float(row["max_dd_usd"])
        _derived(row, "p_dd")
    return row


# ───────────────────────────── FINAL10 (and the bots' designs on other studies' windows) ─────────────────────────────

F10 = RESULTS / "final10"
TIQ = RESULTS / "tradeiq_rsi"
MULTI = RESULTS / "multisymbol"
# the designs the live bots run (tradeiq.BOT_DESIGNS; checked against it by the tests)
BOT_DESIGNS = (("XAUUSDm", "V3-lite"), ("XAUUSDm", "Top 1"), ("XAUUSDm", "Top 2"), ("BTCUSDm", "Top 2"),
               ("BTCUSDm", "Turtle [alt] + bot votes"))
TIQ_BOT_NAME = {("XAUUSDm", "V3-lite"): "V3-lite", ("XAUUSDm", "Top 1"): "Top 1", ("XAUUSDm", "Top 2"): "Top 2",
                ("BTCUSDm", "Top 2"): "Top 2", ("BTCUSDm", "Turtle [alt] + bot votes"): "Turtle System 2 + bot votes"}
# multisymbol's base rows (account a = the unit rule on $2,000) are runs of these final10 designs
MULTI_DESIGN = {("XAUUSDm", "v3lite"): "V3-lite", ("XAUUSDm", "gtop2"): "Top 2", ("XAUUSDm", "gtop1add"): "Top 1",
                ("BTCUSDm", "btop2"): "Top 2", ("BTCUSDm", "ts1"): "Turtle + bot votes",
                ("BTCUSDm", "ts2"): "Turtle [alt] + bot votes"}
F10_FAMILY = {"london": "Session breakout", "rsi2": "Connors RSI(2)", "tsmom": "TSMOM", "ma": "Long moving average",
              "noise": "Noise-area momentum", "supertrend": "Supertrend", "turtle": "Turtle",
              "donchian": "Donchian ensemble", "v3lite": "V3-lite"}
F10_GROUP_TEXT = {"own": "our design", "published": "published strategy", "hybrid": "V3-lite + published filter",
                  "reference": "reference", "supplement": "FINAL10 section 7 supplement, not pre-registered",
                  "warm": "FINAL10 section 8 warm re-check addition"}
F10_GROUP_TAG = {"reference": "reference, not a candidate", "supplement": "§7 supplement, not pre-registered",
                 "warm": "§8 warm re-check addition"}
# FINAL10 §5 / §3: everything from 2021 on helped choose the ten (and the designs: Top 1-3 tuned on 2023-2026, V3-lite
# fixed on 2024 - Nov 2026); the fair test (new) is the only window no choice read. Study 1's rebuilds and
# multisymbol's runs of the same designs inherit this.
F10_SAMPLE = {"new": "out", "5y": "in", "1y": "in", "8y": "mixed", "bots-full": "mixed", "bots-holdout": "in",
              "sel": "in", "conf": "in", "tsel": "mixed"}
# study 1 (PREREG): chosen on development + validation (2019 - Jun 2024); the hold-out from 1 Jul 2024 was sealed
TIQ_SAMPLE = {"dev": "in", "val": "in", "devval": "in", "holdout": "out", "full": "mixed", "5y": "mixed", "1y": "out",
              "8y": "mixed", "new": "mixed"}
F10_TICK_1Y = ("final equity and max DD are the median of FINAL10's 8 loop timings; the other columns, the curve and "
               "its daily-close DD are its middle (upper-median) timing run")
REBUILD_NOTE = ("study 1's rebuild of FINAL10's 8-year trades (tradeiq_rsi/curves_bots_{w}.csv), marked at daily "
                "closes; it ends on 13 Nov 2026, where FINAL10's trades end")


def _f10_file_group(kind: str, engine: str) -> str:
    return kind if kind in ("supplement", "warm") else engine


def _f10_evidence() -> Dict[Tuple[str, str, str], dict]:
    """("main" | "warm", symbol, label) -> FINAL10's selection evidence of that row (evidence.csv, or evidence_warm.csv
    for the section 8 warm re-check): the yardstick score (profit_per_dd = mean profit per fresh quarter / worst
    fresh-quarter DD %), its eligibility and its family. Where one label stands for two evidence rows (gold
    "V3-lite + 200-day trend filter": RSI(2) default and alt), the selection files say which row FINAL10 ran."""
    from . import final10 as F
    sel = json.loads((F10 / "selection.json").read_text(encoding="utf-8"))
    warm = json.loads((F10 / "selection_warm.json").read_text(encoding="utf-8"))
    pick: Dict[Tuple[str, str, str], Tuple[str, str, str]] = {}
    for which, parts in (("main", (sel["final"], sel["references"])), ("warm", (warm["final"],))):
        for part in parts:
            for sym, rows in part.items():
                for r in rows:
                    pick[(which, sym, r["label"])] = (str(r["family"]), str(r["params"]), str(r["variant"]))
    out: Dict[Tuple[str, str, str], dict] = {}
    for which, path in (("main", F10 / "evidence.csv"), ("warm", F10 / "evidence_warm.csv")):
        E = pd.read_csv(path)
        E["label"] = [F.label_of(r) for _, r in E.iterrows()]
        for (sym, label), g in E.groupby(["symbol", "label"], sort=False):
            p = pick.get((which, sym, label))
            if len(g) > 1 and p is not None:
                h = g[(g.family.astype(str) == p[0]) & (g.params.astype(str) == p[1]) & (g.variant.astype(str) == p[2])]
                g = h if len(h) else g
            r = g.iloc[0]
            out[(which, sym, label)] = dict(score=float(r.profit_per_dd), eligible=bool(r.eligible),
                                            family=str(r.family), file=path.name)
    return out


def final10_series_and_metrics() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    """FINAL10's 164 accounts (41 series x 8y, 5y, new, 1y), with the bots' designs also on study 1's windows (its
    rebuilds from final10's trades, curves_bots_*) and multisymbol's base rows on its own windows (sel, conf, tsel)."""
    res = pd.read_csv(F10 / "results.csv")
    ev = _f10_evidence()
    series, metrics = [], []
    curves: Dict[str, List[pd.DataFrame]] = {}
    files: Dict[str, pd.DataFrame] = {}
    runs: Dict[str, pd.DataFrame] = {}
    for (sym, label), g in res.groupby(["symbol", "label"], sort=False):
        r0 = g.iloc[0]
        sid = f"final10:{sym}|{label}"
        group, kind_, eng = str(r0.group), str(r0.kind), str(r0.engine)
        design = (sym, label) in BOT_DESIGNS
        rank = None if pd.isna(r0["rank"]) else int(r0["rank"])
        warm_rank = None if pd.isna(r0.warm_rank) else int(r0.warm_rank)
        e = ev.get(("warm" if kind_ == "warm" else "main", sym, label)) if kind_ != "supplement" else None
        fam_raw = e["family"] if e else ""
        if label.startswith("V3-lite"):
            family = "V3-lite"
        elif label.startswith("Top "):
            family = "Top 1-3 (optimiser v4)"
        elif label == "Live":
            family = "Live ladder (v3.9.2)"
        elif label.startswith("Owner"):
            family = "Owner's rules"
        else:
            family = F10_FAMILY.get(fam_raw, fam_raw)
            if fam_raw == "london" and sym.startswith("BTC"):
                family = "Daily volatility breakout"
        if group in ("hybrid",) or "filter" in label:
            kind = "bot+filter"
        elif kind_ in ("own", "reference") or label.startswith("V3-lite"):
            kind = "bot"
        else:
            kind = "rule"
        filt = ""
        m = re.search(r"V3-lite \+ (.+? filter)", label)
        if m:
            filt = m.group(1)
        elif kind == "rule" and "+ bot votes" in label:
            filt = "bot votes"
        elif kind == "rule" and "+ H1 trend" in label:
            filt = "H1 trend"
        role = "design" if design else ("finalist" if rank is not None else "variant")
        engine_text = "tick engine" if eng == "ticks" else "M1-bar simulator"
        notes = [F10_GROUP_TEXT.get(group, group), engine_text]
        tags = [F10_GROUP_TAG[group]] if group in F10_GROUP_TAG else []
        if rank is not None:
            notes.append(f"final ten #{rank}")
        if warm_rank is not None:
            notes.append(f"warm re-check #{warm_rank}")
        # a cold-start finalist that FINAL10's warm re-check (section 8) finds ineligible
        ew = ev.get(("warm", sym, label)) if (rank is not None and kind_ != "warm") else None
        if ew is not None and not ew["eligible"]:
            notes.append(f"not eligible on FINAL10's warm re-check (section 8: score {ew['score']:.2f} on warm "
                         "evidence, out of the rule)")
            tags.append("not eligible on the warm re-check (§8)")
        if design:
            notes.append("a design the live bots run")
        if (sym, label) == ("BTCUSDm", "Turtle + bot votes"):
            notes.append("the demo branches also run it")
        sizing = ""
        if label.endswith("(risk-sized)"):
            notes.append("risk-sized (1% risk or vol-targeted, as its source prescribes), not the unit rule")
            sizing = "risk-sized"
        eligible = bool(e["eligible"]) if e is not None else False
        series.append(dict(series_id=sid, source="final10", study=SOURCES["final10"]["study"], symbol=sym,
                           label=str(r0["name"]), kind=kind, family=family, tf="", filter=filt, role=role,
                           eligible=int(eligible), exam="", notes="; ".join(notes), sizing=sizing,
                           tags=";".join(tags)))
        fg = _f10_file_group(kind_, eng)
        if (sym, fg) not in files:
            files[(sym, fg)] = pd.read_csv(F10 / f"equity_{sym}_{fg}.csv.gz")
            runs[(sym, fg)] = pd.read_csv(F10 / f"runs_{sym}_{fg}.csv")
        eqf, rnf = files[(sym, fg)], runs[(sym, fg)]
        for _, r in g.iterrows():
            w = str(r.window)
            cv = eqf[(eqf.label == label) & (eqf.window == w)].sort_values("time")
            rr = rnf[(rnf.label == label) & (rnf.window == w)]
            if len(rr) != 1 or not len(cv):
                raise ValueError(f"final10 {sym} {label} {w}: no single run / no curve")
            curve_final = float(rr.final_equity.iloc[0])     # 1y ticks: the representative run's own final
            c = eod_from_sod(cv.time.tolist(), cv.equity.to_numpy(), curve_final, r.start)
            c.insert(0, "series_id", sid)
            curves.setdefault(w, []).append(c)
            marks = "M1" if eng == "bars" else ("tick" if w == "1y" else "second")
            row = dict(series_id=sid, window=w, start=_iso(r.start), end=_iso(r.end), cost=1.0, basis="account",
                       start_usd=ACCOUNT, final_usd=r.final_equity, net_usd=r.net, return_pct=r.return_pct,
                       cagr_pct=r.cagr_pct, max_dd_pct=r.max_dd_pct, trades=r.trades, win_rate_pct=r.win_rate_pct,
                       profit_factor=r.profit_factor, wiped=int(bool(r.wiped)), dd_marks=marks,
                       score_final10=(e["score"] if e else ""), sample=F10_SAMPLE.get(w, ""),
                       row_notes=(F10_TICK_1Y if (eng == "ticks" and w == "1y") else ""),
                       source_file="backtest_results/final10/results.csv")
            metrics.append(fill_from_curve(row, c))
    # the bots' designs on study 1's spans: tradeiq.rebuild of final10's 8y trades (daily marks), under their own
    # window keys (they end on 13 Nov 2026, study 1's own windows at the data end)
    cs = pd.read_csv(TIQ / "curves_summary.csv")
    cs = cs[cs.source == "the bots' designs (final10)"]
    for w0, w in REBUILD_WINDOW.items():
        cb = pd.read_csv(TIQ / f"curves_bots_{w0}.csv")
        for (sym, label), name in TIQ_BOT_NAME.items():
            r = cs[(cs.symbol == sym) & (cs.name == name) & (cs.window == w0)]
            if len(r) != 1:
                raise ValueError(f"curves_summary: no {sym} {name} {w0}")
            r = r.iloc[0]
            if (_iso(r.start), _iso(r.end)) != BH_EXTRA[w]:
                raise ValueError(f"curves_summary {sym} {name} {w0}: {r.start} .. {r.end}, not {BH_EXTRA[w]}")
            g = cb[(cb.symbol == sym) & (cb.design == name)].sort_values("time")
            t = (pd.to_datetime(g.time, utc=True).astype("int64") // 10**9).to_numpy()
            v = g.equity.to_numpy(np.float64)
            # [start, final10's start-of-day samples strictly inside, end]: start-of-day marks plus the final
            c = eod_from_sod([_dstr(x // DAY_S) for x in t[:-1]], v[:-1], v[-1], r.start)
            sid = f"final10:{sym}|{label}"
            c.insert(0, "series_id", sid)
            curves.setdefault(w, []).append(c)
            ev_ = ev.get(("warm" if label.startswith("Turtle [alt]") else "main", sym, label))
            row = dict(series_id=sid, window=w, start=_iso(r.start), end=_iso(r.end), cost=1.0, basis="account",
                       start_usd=ACCOUNT, final_usd=r.final_equity, net_usd=r.net, return_pct=r.return_pct,
                       cagr_pct=r.cagr_pct, max_dd_pct=r.max_dd_pct, trades=r.trades, win_rate_pct=r.win_rate_pct,
                       profit_factor=r.profit_factor, wiped=int(bool(r.wiped)), dd_marks="day",
                       score_final10=ev_["score"] if ev_ else "", sample=F10_SAMPLE[w],
                       row_notes=REBUILD_NOTE.format(w=w0),
                       source_file="backtest_results/tradeiq_rsi/curves_summary.csv")
            metrics.append(fill_from_curve(row, c))
    # multisymbol's base rows: account (a), the unit rule on $2,000, on its own windows (its 8y Turtles are final10's)
    mr = pd.read_csv(MULTI / "runs.csv")
    mr = mr[mr.symbol.isin(SYMBOLS) & (mr.account == "a") & (mr.role == "base") & (mr.period != "8y")]
    daily = {s: pd.read_csv(MULTI / "runs" / s / "daily.csv.gz") for s in SYMBOLS}
    direct = {s: pd.read_csv(MULTI / "runs" / s / "trades_direct.csv.gz") for s in SYMBOLS}
    replay = {s: pd.read_csv(MULTI / "runs" / s / "trades.csv.gz") for s in SYMBOLS}
    for _, r in mr.iterrows():
        label = MULTI_DESIGN[(r.symbol, r.design)]
        sid = f"final10:{r.symbol}|{label}"
        d = daily[r.symbol]
        d = d[(d.design == r.design) & (d.period == r.period)].sort_values("date")
        c = eod_from_daily(d.date.tolist(), d.eq_a.to_numpy(np.float64), r.start)
        c.insert(0, "series_id", sid)
        w = str(r.period)
        curves.setdefault(w, []).append(c)
        ev_ = ev.get(("warm" if label.startswith("Turtle [alt]") else "main", r.symbol, label))
        # the profit factor of the account's closed trades, from multisymbol's own trade files (it publishes none)
        if str(r.engine).startswith("ticks"):
            t = direct[r.symbol]
            t = t[(t.design == r.design) & (t.period == r.period) & (t.account == "a") & t.closed.astype(bool)]
            pnl = t.pnl_usd.to_numpy(np.float64)
        else:
            t = replay[r.symbol]
            t = t[(t.design == r.design) & (t.period == r.period) & t.closed.astype(bool)]
            pnl = t.pnl_a.to_numpy(np.float64)
        pf = ""
        if len(pnl) == int(r.trades) and (pnl < 0).any():
            pf = float(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum())
        # multisymbol's own quarters (3-month blocks from its window start) and Sharpe (x sqrt 52.18) are another
        # definition than every other row's: they stay in the row's notes, and the columns are computed from its
        # daily curve as for the others
        own = [f"multisymbol's own run (runs.csv, account a)"]
        if r.n_quarters:
            own.append(f"its own quarters up: {int(r.pos_quarters)} of {int(r.n_quarters)} 3-month blocks from the "
                       "window start")
        if not pd.isna(r.sharpe_weekly):
            own.append(f"its own weekly Sharpe {float(r.sharpe_weekly):.2f} (x sqrt 52.18)")
        row = dict(series_id=sid, window=w, start=_iso(r.start), end=_iso(r.end), cost=1.0, basis="account",
                   start_usd=ACCOUNT, final_usd=r.final_equity, net_usd=r.profit, max_dd_usd=r.max_dd_usd,
                   profit_factor=pf,
                   max_dd_pct=r.max_dd_pct, p_dd=(r.profit / r.max_dd_usd) if r.max_dd_usd > 0 else "",
                   trades=r.trades, win_rate_pct=(float(r.win_rate) * 100.0 if not pd.isna(r.win_rate) else ""),
                   wiped=int(bool(r.wiped)), dd_marks=("M1" if str(r.engine).startswith("M1") else "second"),
                   score_final10=ev_["score"] if ev_ else "", sample=F10_SAMPLE.get(w, ""),
                   row_notes="; ".join(own), source_file="backtest_results/multisymbol/runs.csv")
        if pf != "":
            _derived(row, "profit_factor")
        if row["p_dd"] != "":
            _derived(row, "p_dd")
        metrics.append(fill_from_curve(row, c))
    cv = {w: pd.concat(v, ignore_index=True) for w, v in curves.items()}
    return _finish_series(series), _finish_metrics(metrics), cv


# ───────────────────────────── study 1: TradeIQ video 1 (tradeiq_rsi), from its files ─────────────────────────────

TIQ_OWN_WINDOWS = ("dev", "val", "devval", "holdout", "full")
IND_TEXT = {"RSI": "RSI(14)", "LaRSI": "Laguerre RSI", "VWRSI": "Volume Weighted RSI (tick volume)",
            "VWRSI-RV": "Volume Weighted RSI (Binance volume)", "TSI": "Bjorgum TSI", "QQE": "QQE MOD",
            "MA200": "MA200 alone"}
FAM_TEXT = {"R1": "R1, both sides", "R2": "R2, long only", "R3": "R3, three states", "R4": "R4, level crosses",
            "CTL-SIGNAL": "control: TSI signal-line cross", "CTL-WHITE": "control: QQE white-line cross"}
FILT_TEXT = {"F0": "no filter", "F1": "MA200 side", "F2-4H": "4H MA200 side", "F2-1D": "daily MA200 side",
             "F3": "TSI side"}
STOP_TEXT = {"S0": "no stop", "S1": "3 x ATR(14) stop"}
ROLE_RANK = {"finalist": 0, "champion": 1, "base": 2, "qualified": 3, "variant": 4}


def tiq_label(vid: str) -> str:
    s, tf, ind, fam, f, st = vid.split("|")
    return f"{tf} {ind} {fam} {f} {st}"


def tiq_series() -> pd.DataFrame:
    """Study 1's 750 variants: role from the selection (finalists, the best row of each indicator, the RSI
    baselines and the best RSI R1 row of DEVIATIONS 35, the qualifiers), the exam verdict (PREREG 8: net > 0 at x1.0
    and P/DD >= 0.5 over the hold-out)."""
    grid = pd.read_csv(TIQ / "grid.csv")
    qual = pd.read_csv(TIQ / "qualification.csv").set_index("vid")
    roles = pd.read_csv(TIQ / "curves_summary.csv")
    roles = roles[roles.source == "TradeIQ study"][["vid", "roles"]].drop_duplicates("vid").set_index("vid").roles
    ex = pd.read_csv(TIQ / "exam.csv")
    ex = ex[ex.window == "holdout"].set_index("vid")
    rows = []
    for _, g in grid.iterrows():
        vid = g.vid
        q = qual.loc[vid]
        rl = str(roles.get(vid, ""))
        role = "variant"
        if bool(q.finalist):
            role = "finalist"
        elif "best " in rl and "best RSI R1" not in rl:
            role = "champion"
        elif "baseline" in rl or "best RSI R1" in rl:
            role = "base"
        elif bool(q.qualifies):
            role = "qualified"
        exam = ""
        if vid in ex.index:
            exam = "pass" if (float(ex.loc[vid, "net"]) > 0 and float(ex.loc[vid, "profit_dd"]) >= 0.5) else "fail"
        notes = [f"{IND_TEXT[g.indicator]}; {FAM_TEXT[g.family]}; {FILT_TEXT[g['filter']]}; {STOP_TEXT[g.stop]}; "
                 f"{g.tf} bars"]
        if not pd.isna(q["rank"]):
            notes.append(f"qualified, rank {int(q['rank'])} on development + validation")
        if rl and rl != "nan":
            notes.append(rl)
        if exam:
            notes.append(f"hold-out exam: {exam}")
        rows.append(dict(series_id=f"tradeiq_rsi:{vid}", source="tradeiq_rsi", study=SOURCES["tradeiq_rsi"]["study"],
                         symbol=g.symbol, label=tiq_label(vid), kind="rule", family=g.indicator, tf=g.tf,
                         filter=g["filter"], role=role, eligible=int(bool(q.qualifies)), exam=exam,
                         notes="; ".join(notes)))
    return _finish_series(rows)


def _unit_row(sid: str, w: str, r, sfx: str, cost: float, file: str, worst_q=None) -> dict:
    net = float(r["net" + sfx])
    return dict(series_id=sid, window=w, start=_iso(r.start), end=_iso(r.end), cost=cost, basis="unit", start_usd=0.0,
                final_usd=net, net_usd=net, return_pct="", cagr_pct="", max_dd_usd=r["max_dd" + sfx], max_dd_pct="",
                p_dd=r["profit_dd" + sfx], trades=r["trades" + sfx], win_rate_pct=r["win_rate" + sfx],
                profit_factor=r["profit_factor" + sfx], sharpe_w=r["sharpe_w" + sfx],
                pos_quarters_pct=(float(r["pos_q_share" + sfx]) * 100.0 if not _blank(r["pos_q_share" + sfx]) else ""),
                worst_quarter_usd=("" if worst_q is None else worst_q), wiped=0, dd_marks="M1", score_final10="",
                sample=TIQ_SAMPLE.get(w, ""), source_file=file)


def tiq_static() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    """Study 1's own windows from its files: every variant per 0.01 lot (dev, val, devval, holdout, full at x1.0 and
    x1.5) and the $2,000 accounts of its curve rows (full, hold-out; buy-and-hold is in the benchmarks source)."""
    series = tiq_series()
    rows: List[dict] = []
    qv = pd.read_csv(TIQ / "quarters_dev_val.csv")
    wq: Dict[Tuple[str, str, float], float] = {}        # study 1's own quarters (dev and val only)
    for c, col in ((1.0, "pnl"), (1.5, "pnl_x15")):
        g = qv.groupby(["vid", "window"])[col].min()
        for (vid, w), v in g.items():
            wq[(vid, w, c)] = float(v)
    for f, wins in (("results_dev_val.csv", ("dev", "val", "devval")), ("results_holdout.csv", ("holdout",)),
                    ("results_full.csv", ("full",))):
        res = pd.read_csv(TIQ / f, float_precision="round_trip")
        for _, r in res.iterrows():
            if r.window not in wins:
                continue
            for cost, sfx in ((1.0, ""), (1.5, "_x15")):
                rows.append(_unit_row(f"tradeiq_rsi:{r.vid}", r.window, r, sfx, cost, f"backtest_results/tradeiq_rsi/{f}",
                                      wq.get((r.vid, r.window, cost))))
    # the $2,000 accounts of the curve rows, and their unit curves' worst quarter where the files do not have one
    cs = pd.read_csv(TIQ / "curves_summary.csv")
    cs = cs[(cs.source == "TradeIQ study") & ~cs.vid.str.endswith("|buy-and-hold")]
    curves: Dict[str, List[pd.DataFrame]] = {}
    unit_wq: Dict[Tuple[str, str], float] = {}
    for w in ("full", "holdout"):
        cf = pd.read_csv(TIQ / f"curves_{w}.csv")
        for vid, g in cf.groupby("vid", sort=False):
            if vid.endswith("|buy-and-hold"):
                continue
            t = (pd.to_datetime(g.time, utc=True).astype("int64") // 10**9).to_numpy()
            has = np.r_[True, np.isfinite(g.unit_worst.to_numpy(np.float64)[1:])]
            c = eod_from_midnights(t, g.equity.to_numpy(np.float64), has)
            c.insert(0, "series_id", f"tradeiq_rsi:{vid}")
            curves.setdefault(w, []).append(c)
            u = eod_from_midnights(t, g.unit_equity.to_numpy(np.float64), has)
            r = cs[(cs.vid == vid) & (cs.window == w)].iloc[0]
            st = curve_stats(u.date.tolist(), u.equity_usd.to_numpy(np.float64), _iso(r.start), _iso(r.end), 0.0)
            unit_wq[(vid, w)] = st.get("worst_quarter_usd")
            # the account's max DD in $ on its M1 marks is not in the files (only the %), so it stays empty
            row = dict(series_id=f"tradeiq_rsi:{vid}", window=w, start=_iso(r.start), end=_iso(r.end), cost=1.0,
                       basis="account", start_usd=ACCOUNT, final_usd=r.final_equity, net_usd=r.net,
                       return_pct=r.return_pct, cagr_pct=r.cagr_pct, max_dd_pct=r.max_dd_pct, trades=r.trades,
                       win_rate_pct=r.win_rate_pct, profit_factor=r.profit_factor, wiped=int(bool(r.wiped)),
                       dd_marks="M1", score_final10="", sample=TIQ_SAMPLE.get(w, ""),
                       source_file="backtest_results/tradeiq_rsi/curves_summary.csv")
            rows.append(fill_from_curve(row, c))
    for row in rows:
        if row["basis"] == "unit" and _blank(row.get("worst_quarter_usd")) and row["cost"] == 1.0:
            v = unit_wq.get((row["series_id"].split(":", 1)[1], row["window"]))
            if v is not None:
                row["worst_quarter_usd"] = v
                _derived(row, "worst_quarter_usd")
    return series, _finish_metrics(rows), {w: pd.concat(v, ignore_index=True) for w, v in curves.items()}


# ───────────────────────────── the earlier studies that use the same account ─────────────────────────────

BALKE = RESULTS / "balke"
LADDER = RESULTS / "ladder"
BALKE_FAMILY = {"rb_xau": "Range Breakout", "rb_btc": "Range Breakout", "atr": "ATR Breakout", "gl_side": "Go Long",
                "tt_side": "Turnaround Tuesday"}
# the ladder's continuous accounts on the bot's unit rule (its other designs are sized Z1-Z3, not the unit rule;
# V3 and V3L are final10's V3-lite and gold Top 1 to the cent)
LADDER_DESIGNS = {"L0": ("L0", "Live ladder L0 (ladder kernel)", "the live bot v3.9.2 on the ladder kernel"),
                  "L5": ("L5", "Slot-5 ladder L5", "the slot 5 ladder"),
                  "LB": ("LB", "Bounded ladder LB", "a bounded ladder near the live bot"),
                  "V3L|CONFIRM=C5|SIDE=S7|TIERS=T8|GRAN=T12": ("G4", "Ladder G4 (V3-lite frame, unit rule)",
                                                                "G4 of the gold top 5 (V3L|CONFIRM=C5|SIDE=S7|"
                                                                "TIERS=T8|GRAN=T12), the one on the unit rule")}


def balke_source() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    """Balke's gold / BTC rows on the bot's unit rule (the inventory's fully comparable rows): final10's windows,
    $2,000, the unit rule and final10's own M1-bar engine; his own sizings are left out (another account)."""
    res = pd.read_csv(BALKE / "results.csv")
    res = res[res.symbol.isin(SYMBOLS) & (res.sizing == "bot unit rule") & ~res.bench.astype(bool)]
    eq = {s: pd.read_csv(BALKE / f"equity_{s}.csv.gz") for s in SYMBOLS}
    series, rows = [], []
    curves: Dict[str, List[pd.DataFrame]] = {}
    for (sym, label), g in res.groupby(["symbol", "label"], sort=False):
        r0 = g.iloc[0]
        sid = f"balke:{sym}|{label}"
        name = str(r0.strategy)
        notes = ["rebuilt from his public settings files", "bot unit rule on $2,000", "M1-bar simulator (final10's)"]
        if "not his market" in name:
            notes.append("his index strategy run on this symbol as a control")
        if bool(r0.multi):
            notes.append("every signal opens its own position")
        series.append(dict(series_id=sid, source="balke", study=SOURCES["balke"]["study"], symbol=sym, label=name,
                           kind="rule", family=BALKE_FAMILY.get(str(r0.key), str(r0.key)), tf="", filter="",
                           role="variant", eligible=0, exam="", notes="; ".join(notes)))
        for _, r in g.iterrows():
            w = str(r.window)
            cv = eq[sym]
            cv = cv[(cv.label == label) & (cv.window == w)].sort_values("time")
            c = eod_from_sod(cv.time.tolist(), cv.equity.to_numpy(np.float64), float(r.final_equity), r.start)
            c.insert(0, "series_id", sid)
            curves.setdefault(w, []).append(c)
            row = dict(series_id=sid, window=w, start=_iso(r.start), end=_iso(r.end), cost=1.0, basis="account",
                       start_usd=ACCOUNT, final_usd=r.final_equity, net_usd=r.net, return_pct=r.return_pct,
                       cagr_pct=r.cagr_pct, max_dd_pct=r.max_dd_pct, trades=r.trades, win_rate_pct=r.win_rate_pct,
                       profit_factor=r.profit_factor, wiped=int(bool(r.wiped)), dd_marks="M1", score_final10="",
                       source_file="backtest_results/balke/results.csv")
            rows.append(fill_from_curve(row, c))
    return _finish_series(series), _finish_metrics(rows), {w: pd.concat(v, ignore_index=True) for w, v in curves.items()}


def ladder_source() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    """The ladder study's continuous gold accounts on the unit rule (8y and 5y per second, 1y the median of its 8
    raw-tick timings, as FINAL10's 1y). It wrote no curves, so these rows are in the table and the scatter only."""
    series, rows = [], []
    for code, (short, label, what) in LADDER_DESIGNS.items():
        sid = f"ladder:XAUUSDm|{short}"
        series.append(dict(series_id=sid, source="ladder", study=SOURCES["ladder"]["study"], symbol="XAUUSDm",
                           label=label, kind="bot", family="DCA ladder", tf="", filter="", role="variant", eligible=0,
                           exam="", notes=f"{what}; ladder kernel (ladder_engine.py); metrics only, no curve; "
                                          "1y: the median of 8 loop timings"))
        for w in ("8y", "5y", "1y"):
            d = pd.read_csv(LADDER / "runs_XAUUSDm" / f"cont_{w}.csv")
            d = d[d.design == code]
            if not len(d):
                raise ValueError(f"ladder: no {code} {w}")
            net = float(np.median(d.net.to_numpy(np.float64)))
            ddp = float(np.median(d.max_dd_pct.to_numpy(np.float64)))
            final = ACCOUNT + net
            a, z = _iso(d.start.iloc[0]), _iso(d.end.iloc[0])
            yrs = (_s(z) - _s(a)) / YEAR_S
            rows.append(dict(series_id=sid, window=w, start=a, end=z, cost=1.0, basis="account", start_usd=ACCOUNT,
                             final_usd=final, net_usd=net, return_pct=net / ACCOUNT * 100.0,
                             cagr_pct=((final / ACCOUNT) ** (1 / yrs) - 1) * 100.0 if final > 0 else -100.0,
                             max_dd_usd="", max_dd_pct=ddp, p_dd="", trades=float(np.median(d.baskets)),
                             win_rate_pct="", profit_factor="", wiped=int(final <= 0.0),
                             dd_marks="second" if w != "1y" else "tick", score_final10="",
                             derived="return_pct,cagr_pct",
                             row_notes=("net, max DD and baskets are the median of the study's 8 loop timings; "
                                        if w == "1y" else "") + "trades are the ladder's baskets",
                             source_file=f"backtest_results/ladder/runs_XAUUSDm/cont_{w}.csv"))
    return _finish_series(series), _finish_metrics(rows), {}


# ───────────────────────────── computed here: study 1 on the common windows, buy-and-hold ─────────────────────────────

def market_from(symbol: str, start: str = SEALED_BEFORE):
    """
    Study 1's ``TMarket`` on the store's M1 bars from ``start`` (default 2019-01-01) to its data end, built exactly as
    ``tradeiq_market.load`` builds it except for the first bar: load() reads from the symbol's data start (2017 /
    2018), which workflow rule 1 forbids now. ``tradeiq_checks`` shows the result is study 1's own (README).
    """
    from ..data import store
    from . import external as X
    from . import tradeiq_market as TM
    if _s(start) < _s(SEALED_BEFORE):
        raise PermissionError(f"{start}: no bar before {SEALED_BEFORE} is loaded without --allow-pre-2019")
    end_s = TM.DATA_END_S[symbol]
    m = X.load_market(symbol, store.DEFAULT_STORE_DIR, earliest=start, end=str(TM.utc(end_s).tz_localize(None)))
    mk = TM.TMarket(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp, "n": m.n}, end_s)
    span = store.data_span(symbol, store.DEFAULT_STORE_DIR)
    if span is None or span[1] < pd.Timestamp(TM.LAST_TICK[symbol], tz="UTC"):
        raise ValueError(f"{symbol}: the store ends before study 1's last tick {TM.LAST_TICK[symbol]}")
    return mk


_ACCT_DD = None


def _acct_dd_kernel():
    """
    ``external._account_kernel`` (the bot's unit rule, mode 0, no leverage cap: what ``tradeiq.account_of`` runs for
    study 1) with one addition: next to the max drawdown as a fraction of the running peak it keeps the largest fall
    in $, on the same M1 marks (each bar's close mark raises the peak first, then its worst mark is measured). Compiled
    on first use, without a cache file.
    """
    global _ACCT_DD
    if _ACCT_DD is not None:
        return _ACCT_DD
    from numba import njit

    @njit
    def kern(h, l, c, sp, k, T_dir, T_eix, T_xix, T_xpx, T_why, T_leg0, T_nleg, L_eix, L_epx, bal0, step_up,
             unit_max):
        nt = T_dir.shape[0]
        bal = bal0
        peak = bal0
        maxdd = 0.0
        maxdd_usd = 0.0
        wiped = False
        for i in range(nt):
            e = T_eix[i]
            x = T_xix[i]
            d = T_dir[i]
            s = math.floor(bal / step_up) + 1.0
            if s > unit_max:
                s = unit_max
            if s < 0:
                s = 0.0
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
                    if peak > maxdd_usd:
                        maxdd_usd = peak
                    bal = 0.0
                    maxdd = 1.0
                    break
                dd = (peak - ew) / peak
                if dd > maxdd:
                    maxdd = dd
                if peak - ew > maxdd_usd:
                    maxdd_usd = peak - ew
            if wiped:
                break
            pl = 0.0
            for q in range(T_leg0[i], T_leg0[i] + T_nleg[i]):
                pl += s * k * d * (T_xpx[i] - L_epx[q])
            bal += pl
            if bal > peak:
                peak = bal
        return maxdd, maxdd_usd, bal, wiped

    _ACCT_DD = kern
    return kern


def account_dd_usd(r) -> Tuple[float, float, float]:
    """(max DD fraction, max DD in $, final equity) of study 1's $2,000 account of a run ``r`` on the account's own M1
    marks; the fraction and the final equal ``tradeiq.account_of``'s (``compute`` checks every run)."""
    from . import external as X
    m, p = r.m, r.path
    f, usd, bal, _ = _acct_dd_kernel()(m.h, m.l, m.c, m.sp, float(m.k), p.dir, p.eix, p.xix, p.xpx, p.why, p.leg0,
                                       p.nleg, p.leix, p.lepx, X.ACCOUNT, X.STEP_UP, float(X.UNIT_MAX))
    return float(f), float(usd), float(bal)


def _days_with_bars(mk) -> np.ndarray:
    d = np.unique(np.asarray(mk.t, np.int64) // DAY_S)
    out = np.zeros(int(d.max()) + 2, bool)
    out[d] = True
    return out


def bh_path(mk, start, end, cost: float = 1.0, f_units: Optional[float] = None) -> Dict[str, object]:
    """
    Buy-and-hold on M1 bars, study 1's convention (DEVIATIONS 6: bought at the ask = bid open + the bar's mean
    spread x cost at the window's first M1 open, sold at the bid at its last M1 close; marked like a long at each M1
    bar's close and, for the drawdown, its low; the running peak as ``tradeiq_market._unit_marks``). Per unit (0.01
    lot), and on $2,000 accounts holding ``units`` x 0.01 lot: 1 (study 1's account: the unit rule gives 1 at $2,000,
    fixed at the open) and 2,000 / (entry ask x 0.01 lot's size), i.e. $2,000 fully invested without leverage.
    """
    a_s, z_s = _s(start), _s(end)
    t = np.asarray(mk.t, np.int64)
    ia = int(np.searchsorted(t, a_s, side="left"))
    iz = int(np.searchsorted(t, z_s, side="left"))
    if iz - ia < 2:
        raise ValueError(f"no bars in {start} .. {end}")
    k = float(mk.k)
    ep = float(mk.o[ia] + cost * mk.sp[ia])
    xp = float(mk.c[iz - 1])
    uc = k * (mk.c[ia:iz] - ep)
    uw = k * (mk.l[ia:iz] - ep)
    pc = np.maximum.accumulate(np.maximum(uc, 0.0))
    peak = pc.copy()
    peak[-1] = pc[-2]                          # the exit bar does not raise the peak (its worst mark still counts)
    unit_dd = float(np.max(peak - uw))
    f = ACCOUNT / (k * ep) if f_units is None else float(f_units)
    acc_dd_pct = float(np.max(f * (peak - uw) / (ACCOUNT + f * peak)) * 100.0)
    day = t[ia:iz] // DAY_S
    last = np.r_[day[1:] != day[:-1], True]                    # the last bar of each day
    days = day[last]
    eq = ACCOUNT + f * uc[last]
    return dict(entry=ep, exit=xp, unit_net=k * (xp - ep), unit_max_dd=unit_dd, f_units=f, k=k,
                final=ACCOUNT + f * k * (xp - ep), max_dd_usd=f * unit_dd, max_dd_pct=acc_dd_pct,
                curve=pd.DataFrame({"date": _dstrs(np.r_[_dnum(start) - 1, days]),
                                    "equity_usd": np.r_[ACCOUNT, eq]}),
                start=_iso(start), end=_iso(end))


def _bh_series(sym: str) -> List[dict]:
    st = SOURCES["benchmarks"]["study"]
    return [dict(series_id=f"benchmarks:{sym}|bh-2000", source="benchmarks", study=st, symbol=sym,
                 label="Buy and hold, $2,000 fully invested (no leverage)", kind="benchmark", family="buy-and-hold",
                 tf="", filter="", role="benchmark", eligible=0, exam="",
                 notes="$2,000 buys 2,000 / ask of the asset at the window's first M1 open (a fraction of a lot, "
                       "no leverage, nothing else traded); held to the last M1 close, sold at the bid; marked at every "
                       "M1 bar (close, and the low for the drawdown); no swap", sizing="fully invested", tags=""),
            dict(series_id=f"benchmarks:{sym}|bh-0.01lot", source="benchmarks", study=st, symbol=sym,
                 label="Buy and hold 0.01 lot (study 1's reference)", kind="benchmark", family="buy-and-hold",
                 tf="", filter="", role="benchmark", eligible=0, exam="",
                 notes="study 1's buy-and-hold (DEVIATIONS 6 and 35): 0.01 lot bought at the ask at the window's "
                       "first M1 open, sold at the bid at its last M1 close; on the $2,000 account it holds 1 unit for "
                       "the whole span (the unit rule gives 1 at $2,000, fixed at the open), so it never compounds",
                 sizing="0.01 lot fixed", tags="")]


def _bh_account_row(sid, w, b, file, start_usd=ACCOUNT) -> dict:
    net = b["final"] - start_usd
    yrs = (_s(b["end"]) - _s(b["start"])) / YEAR_S
    return dict(series_id=sid, window=w, start=b["start"], end=b["end"], cost=1.0, basis="account",
                start_usd=start_usd, final_usd=b["final"], net_usd=net, return_pct=net / start_usd * 100.0,
                cagr_pct=((b["final"] / start_usd) ** (1.0 / yrs) - 1.0) * 100.0, max_dd_usd=b["max_dd_usd"],
                max_dd_pct=b["max_dd_pct"], p_dd=net / b["max_dd_usd"] if b["max_dd_usd"] > 0 else "", trades=1,
                win_rate_pct=100.0 if net > 0 else 0.0, profit_factor="", wiped=0, dd_marks="M1", score_final10="",
                source_file=file)


def _bh_unit_row(sid, w, a, z, cost, net, dd, file) -> dict:
    return dict(series_id=sid, window=w, start=_iso(a), end=_iso(z), cost=cost, basis="unit", start_usd=0.0,
                final_usd=net, net_usd=net, return_pct="", cagr_pct="", max_dd_usd=dd, max_dd_pct="",
                p_dd=net / dd if dd > 0 else "", trades=1, win_rate_pct=100.0 if net > 0 else 0.0, profit_factor="",
                wiped=0, dd_marks="M1", score_final10="", source_file=file)


def tradeiq_checks(symbol: str, mk=None, log=print) -> Dict[str, object]:
    """
    That a study-1 market from 2019-01-01 gives study 1's own numbers: (1) every rule's state from a month before
    the 5-year window on equals the state of a market from 2019-07-01 (the warm-up has converged); (2) every variant
    re-run over validation and the hold-out on it equals results_dev_val.csv / results_holdout.csv (computed with
    history from 2017 / 2018): net and max drawdown per 0.01 lot, and the trade count; (3) buy-and-hold here equals
    study 1's on all its windows.
    """
    from . import tradeiq as T
    from . import tradeiq_market as TM
    t0 = time.time()
    mk = mk if mk is not None else market_from(symbol)
    A, B = T.Study(mk), T.Study(market_from(symbol, "2019-07-01"))
    cut = TM.s_of(COMMON["5y"][0]) - 30 * DAY_S
    n_rules = differ = 0
    for v in T.grid(symbol):
        if v.stop == "S1":
            continue
        ba, bb = A.bars[v.tf], B.bars[v.tf]
        ia, ib = np.flatnonzero(ba.tc > cut), np.flatnonzero(bb.tc > cut)
        if not np.array_equal(ba.t[ia], bb.t[ib]):
            raise AssertionError(f"{v.vid}: the bars differ")
        n_rules += 1
        differ += int(not np.array_equal(A.state(v)[ia], B.state(v)[ib]))
    stops_max = max(float(np.nanmax(np.abs(A.stops[tf][np.flatnonzero(A.bars[tf].tc > cut)]
                                           - B.stops[tf][np.flatnonzero(B.bars[tf].tc > cut)]))) for tf in T.TFS)
    del B
    runs = mism = 0
    maxd = 0.0
    for w, f in (("val", "results_dev_val.csv"), ("holdout", "results_holdout.csv")):
        rr = pd.read_csv(TIQ / f, float_precision="round_trip")
        rr = rr[(rr.window == w) & (rr.symbol == symbol)].set_index("vid")
        for v in T.grid(symbol):
            r = T.run_window(A, v, w, 1.0)
            d = abs(r.net - float(rr.loc[v.vid, "net"])) + abs(r.max_dd - float(rr.loc[v.vid, "max_dd"]))
            maxd = max(maxd, d)
            runs += 1
            mism += int(d > 1e-9 or len(r.trades) != int(rr.loc[v.vid, "trades"]))
    bh = pd.concat([pd.read_csv(TIQ / "buy_and_hold.csv"), pd.read_csv(TIQ / "buy_and_hold_exam.csv")])
    bh = bh[(bh.symbol == symbol)]
    bh_max = 0.0
    for _, r in bh.iterrows():
        b = bh_path(mk, r.start, r.end, float(r.cost), f_units=1.0)
        bh_max = max(bh_max, abs(b["unit_net"] - r.bh_net), abs(b["unit_max_dd"] - r.bh_max_dd),
                     abs(b["entry"] - r.bh_entry), abs(b["exit"] - r.bh_exit))
    out = dict(symbol=symbol, market_from=str(TM.utc(mk.t[0])), rules_compared=n_rules,
               rules_with_a_different_state=differ, s1_stop_max_abs_diff=stops_max, runs_compared=runs,
               runs_differing=mism, max_abs_diff_usd=maxd, buy_and_hold_rows=int(len(bh)),
               buy_and_hold_max_abs_diff=bh_max, seconds=round(time.time() - t0, 1))
    log(f"  {symbol} checks: {out}")
    return out


def compute(symbols: Sequence[str] = SYMBOLS, windows: Sequence[str] = ("5y", "1y"), allow_pre_2019: bool = False,
            data: Path = DATA, checks: bool = True, log=print) -> None:
    """
    Study 1's 750 variants on the common windows with its own code (tradeiq.Study / state, tradeiq_market.run, the
    $2,000 account of tradeiq.account_of, the account metrics of tradeiq.curve_metrics), at x1.0, as accounts and
    per 0.01 lot; buy-and-hold on the same windows and on study 1's own (the $2,000 one is computed here; the 0.01-lot
    one comes from study 1's files on its windows and is checked here). Windows that start before 2019-01-01 (8y,
    new) need ``allow_pre_2019`` and load study 1's market from its data start (tradeiq_market.load).
    """
    from . import tradeiq as T
    from . import tradeiq_market as TM
    for w in windows:
        if w not in COMMON:
            raise ValueError(f"{w}: not a common window ({', '.join(COMMON)})")
    pre = [w for w in windows if _s(COMMON[w][0]) < _s(SEALED_BEFORE)]
    if pre and not allow_pre_2019:
        raise PermissionError(f"{', '.join(pre)} start before {SEALED_BEFORE}: they wait for study 2's exam "
                              "(--allow-pre-2019, once it is written)")
    if pre and not STUDY2_EXAM.exists():
        raise PermissionError(f"--allow-pre-2019: study 2's exam ({_rel(STUDY2_EXAM)}) is not written yet, so the "
                              f"bars before {SEALED_BEFORE} stay sealed")
    file_c = "compare_page compute: tradeiq.py / tradeiq_market.py, M1 bars from " + \
             ("the data start" if pre else SEALED_BEFORE)
    tiq_rows: List[dict] = []
    tiq_curves: Dict[str, List[pd.DataFrame]] = {}
    bh_series, bh_rows = [], []
    bh_curves: Dict[str, List[pd.DataFrame]] = {}
    check_rows = []
    for sym in symbols:
        t0 = time.time()
        mk = TM.load(sym) if pre else market_from(sym)
        has_bar = _days_with_bars(mk)
        if checks and not pre:
            check_rows.append(tradeiq_checks(sym, mk, log))
        st = T.Study(mk)
        grid = T.grid(sym)
        dd_runs, dd_diff = 0, 0.0
        for n, v in enumerate(grid):
            sid = f"tradeiq_rsi:{v.vid}"
            stop = st.stops[v.tf] if v.stop == "S1" else None
            for w in windows:
                a, z = COMMON[w]
                r = TM.run(mk, st.bars[v.tf], st.state(v), a, z, stop=stop, cost=1.0)
                sc = T.scores(r)
                _, qp, _ = TM.quarter_pnl(r)
                tiq_rows.append(dict(series_id=sid, window=w, start=a, end=z, cost=1.0, basis="unit", start_usd=0.0,
                                     final_usd=sc["net"], net_usd=sc["net"], return_pct="", cagr_pct="",
                                     max_dd_usd=sc["max_dd"], max_dd_pct="", p_dd=sc["profit_dd"],
                                     trades=sc["trades"], win_rate_pct=sc["win_rate"],
                                     profit_factor=sc["profit_factor"], sharpe_w=sc["sharpe_w"],
                                     pos_quarters_pct=sc["pos_q_share"] * 100.0,
                                     worst_quarter_usd=float(qp.min()) if len(qp) else "", wiped=0, dd_marks="M1",
                                     score_final10="", sample=TIQ_SAMPLE.get(w, ""), source_file=file_c))
                curve, cs, res = T.account_of(r)
                # the account's max DD in $ on the same M1 marks as its max DD % (the kernel's fraction and final
                # must equal tradeiq.account_of's)
                f_dd, dd_usd, bal = account_dd_usd(r)
                d = abs(f_dd * 100.0 - cs["max_dd_pct"])
                if d > 1e-9 or abs(bal - cs["final"]) > 1e-6:
                    raise AssertionError(f"{v.vid} {w}: the $ drawdown kernel differs from tradeiq.account_of "
                                         f"({f_dd * 100.0} / {cs['max_dd_pct']}, {bal} / {cs['final']})")
                dd_runs, dd_diff = dd_runs + 1, max(dd_diff, d)
                ts = (curve.time.astype("int64") // 10**9).to_numpy(np.int64)
                eq = curve.equity.to_numpy(np.float64)
                m = T.curve_metrics(ts, eq, cs["final"], cs["max_dd_pct"], r.a_s, r.z_s, res.trades_pnl,
                                    cs["wiped"], TM.utc(res.wipe_t) if res.wiped else None)
                c = eod_from_midnights(ts, eq, has_bar[np.maximum((ts - 1) // DAY_S, 0)])
                c.insert(0, "series_id", sid)
                tiq_curves.setdefault(w, []).append(c)
                net = cs["final"] - ACCOUNT
                row = dict(series_id=sid, window=w, start=a, end=z, cost=1.0, basis="account", start_usd=ACCOUNT,
                           final_usd=cs["final"], net_usd=net, return_pct=m["return_pct"],
                           cagr_pct=m["cagr_pct"], max_dd_usd=dd_usd, max_dd_pct=cs["max_dd_pct"],
                           p_dd=(net / dd_usd) if dd_usd > 0 else "", trades=m["trades"],
                           win_rate_pct=m["win_rate_pct"], profit_factor=m["profit_factor"], wiped=int(cs["wiped"]),
                           dd_marks="M1", score_final10="", sample=TIQ_SAMPLE.get(w, ""), source_file=file_c)
                tiq_rows.append(fill_from_curve(row, c))
            if (n + 1) % 100 == 0 or n + 1 == len(grid):
                log(f"  {sym}: {n + 1} / {len(grid)} variants on {', '.join(windows)} ({time.time() - t0:.0f} s)")
        if check_rows and check_rows[-1].get("symbol") == sym:
            check_rows[-1].update(account_dd_runs=dd_runs, account_dd_max_abs_diff_pct=dd_diff)
        # buy-and-hold: the common windows asked for, study 1's own windows for the $2,000 one, and the other
        # studies' windows from 2019 on (BH_EXTRA)
        bh_series += _bh_series(sym)
        own = [] if pre else [(w, *TM.window(w, sym)) for w in TIQ_OWN_WINDOWS]
        extra = [] if pre else [(w, a, z) for w, (a, z) in BH_EXTRA.items()]
        for w, a, z in [(w, *COMMON[w]) for w in windows] + own + extra:
            b = bh_path(mk, a, z)
            c = b["curve"].copy()
            c.insert(0, "series_id", f"benchmarks:{sym}|bh-2000")
            bh_curves.setdefault(w, []).append(c)
            bh_rows.append(fill_from_curve(_bh_account_row(f"benchmarks:{sym}|bh-2000", w, b,
                                                           "compare_page compute (buy-and-hold on M1 bars)"), c))
            if w in COMMON or w in BH_EXTRA:
                b1 = bh_path(mk, a, z, f_units=1.0)
                # study 1's own construction agrees: tradeiq.bh_run on its $2,000 account (it takes only windows from
                # the market's first bar on; a window from 2019-01-01 is checked by tradeiq_checks on study 1's full)
                if _s(a) >= int(mk.t[0]):
                    r = T.bh_run(mk, a, z, 1.0)
                    curve, cs, res = T.account_of(r)
                    if abs(r.net - b1["unit_net"]) > 1e-6 or abs(r.max_dd - b1["unit_max_dd"]) > 1e-6 or \
                            abs(cs["final"] - b1["final"]) > 1e-6 or abs(cs["max_dd_pct"] - b1["max_dd_pct"]) > 1e-6:
                        raise AssertionError(f"{sym} {w}: buy-and-hold differs from tradeiq.bh_run")
                c1 = b1["curve"].copy()
                c1.insert(0, "series_id", f"benchmarks:{sym}|bh-0.01lot")
                bh_curves.setdefault(w, []).append(c1)
                bh_rows.append(fill_from_curve(_bh_account_row(f"benchmarks:{sym}|bh-0.01lot", w, b1, file_c), c1))
                bh_rows.append(_bh_unit_row(f"benchmarks:{sym}|bh-0.01lot", w, a, z, 1.0, b1["unit_net"],
                                            b1["unit_max_dd"], file_c))
        # study 1's own windows for the 0.01-lot buy-and-hold: its files (checked against bh_path in tradeiq_checks)
        if not pre:
            for f in ("buy_and_hold.csv", "buy_and_hold_exam.csv"):
                bh = pd.read_csv(TIQ / f)
                for _, r in bh[bh.symbol == sym].iterrows():
                    bh_rows.append(_bh_unit_row(f"benchmarks:{sym}|bh-0.01lot", r.window, r.start, r.end,
                                                float(r.cost), float(r.bh_net), float(r.bh_max_dd),
                                                f"backtest_results/tradeiq_rsi/{f}"))
            cs = pd.read_csv(TIQ / "curves_summary.csv")
            for w in ("full", "holdout"):
                cf = pd.read_csv(TIQ / f"curves_{w}.csv")
                g = cf[cf.vid == f"{sym}|buy-and-hold"]
                t = (pd.to_datetime(g.time, utc=True).astype("int64") // 10**9).to_numpy()
                has = np.r_[True, np.isfinite(g.unit_worst.to_numpy(np.float64)[1:])]
                c = eod_from_midnights(t, g.equity.to_numpy(np.float64), has)
                c.insert(0, "series_id", f"benchmarks:{sym}|bh-0.01lot")
                bh_curves.setdefault(w, []).append(c)
                r = cs[(cs.source == "TradeIQ study") & (cs.vid == f"{sym}|buy-and-hold") & (cs.window == w)].iloc[0]
                row = dict(series_id=f"benchmarks:{sym}|bh-0.01lot", window=w, start=_iso(r.start), end=_iso(r.end),
                           cost=1.0, basis="account", start_usd=ACCOUNT, final_usd=r.final_equity, net_usd=r.net,
                           return_pct=r.return_pct, cagr_pct=r.cagr_pct, max_dd_pct=r.max_dd_pct, trades=r.trades,
                           win_rate_pct=r.win_rate_pct, profit_factor=r.profit_factor, wiped=int(bool(r.wiped)),
                           dd_marks="M1", score_final10="",
                           source_file="backtest_results/tradeiq_rsi/curves_summary.csv")
                b1 = bh_path(mk, r.start, r.end, f_units=1.0)
                if abs(b1["final"] - float(r.final_equity)) > 0.006 or abs(b1["max_dd_pct"] - float(r.max_dd_pct)) > 1e-3:
                    raise AssertionError(f"{sym} {w}: the 0.01-lot account differs from curves_summary.csv")
                # the account is $2,000 + one unit, so its max DD in $ on M1 marks is the unit's (study 1's bh_max_dd)
                row["max_dd_usd"] = b1["max_dd_usd"]
                row["p_dd"] = float(r.net) / b1["max_dd_usd"] if b1["max_dd_usd"] > 0 else ""
                bh_rows.append(fill_from_curve(row, c))
        del st, mk
        log(f"  {sym}: done in {time.time() - t0:.0f} s")
    write_source("tradeiq_rsi", tiq_series(), _finish_metrics(tiq_rows),
                 {w: pd.concat(v, ignore_index=True) for w, v in tiq_curves.items()}, data=data)
    write_source("benchmarks", _finish_series(bh_series), _finish_metrics(bh_rows),
                 {w: pd.concat(v, ignore_index=True) for w, v in bh_curves.items()}, data=data)
    if check_rows:
        pd.DataFrame(check_rows).to_csv(Path(data) / "tradeiq_rsi__checks.csv", index=False)
    log(f"wrote study 1 on {', '.join(windows)} and the benchmarks into {_rel(Path(data))}")


def export(data: Path = DATA, log=print) -> None:
    """The contract files of every source that is read from its own result files."""
    for sid, fn in (("final10", final10_series_and_metrics), ("tradeiq_rsi", tiq_static), ("balke", balke_source),
                    ("ladder", ladder_source)):
        t0 = time.time()
        s, m, cv = fn()
        write_source(sid, s, m, cv, data=data, replace=(sid != "tradeiq_rsi"))
        log(f"  {sid}: {len(s)} series, {len(m)} metrics rows, curves {', '.join(sorted(cv)) or '-'} "
            f"({time.time() - t0:.0f} s)")


# ───────────────────────────── validation ─────────────────────────────

def validate(data: Path = DATA) -> Dict[str, List[str]]:
    """
    Check every contract file in ``data``: the columns exactly, the ids (unique across all sources, prefixed with the
    source), the vocabularies, the units (account rows start at $2,000, unit rows at 0 with no % fields), the dates
    (ISO, end after start), and each curve (ascending unique days, an opening row the day before its window with the
    start balance, nothing after the window), the optional v2 fields (sizing, sample, derived), and that an account's
    max DD in $ is not below its max DD % of the $2,000 (the two are on the same marks, and the peak is never below the
    start). Returns {"errors": [...], "warnings": [...]}; a warning is a curve whose last value differs from its row's
    final equity (FINAL10's 1y tick rows: the curve is the middle timing run, the row the median of 8), or a window key
    whose rows span different dates on one symbol.
    """
    errors: List[str] = []
    warnings: List[str] = []
    seen: Dict[str, str] = {}
    spans: Dict[Tuple[str, str], Dict[Tuple[str, str], List[str]]] = {}
    for sid in sources_in(data):
        s, m, cv = read_source(sid, data, raw=True)
        if not _columns_ok(s.columns, SERIES_COLS, SERIES_OPT):
            errors.append(f"{sid}__series.csv: columns {list(s.columns)}")
            continue
        if not _columns_ok(m.columns, METRICS_COLS, METRICS_OPT):
            errors.append(f"{sid}__metrics.csv: columns {list(m.columns)}")
            continue
        s = _with_optional(s, SERIES_COLS, SERIES_OPT)
        m = _with_optional(m, METRICS_COLS, METRICS_OPT)
        sym_of = dict(zip(s.series_id, s.symbol))
        for i, r in s.iterrows():
            if r.series_id in seen:
                errors.append(f"{sid}: series_id {r.series_id} also in {seen[r.series_id]}")
            seen[r.series_id] = sid
            if not r.series_id.startswith(sid + ":") or r.source != sid:
                errors.append(f"{sid}: {r.series_id} is not '{sid}:<id>' of source {sid}")
            if r.symbol not in SYMBOLS:
                errors.append(f"{sid}: {r.series_id} symbol {r.symbol}")
            if r.kind not in KINDS or r.role not in ROLES or r.exam not in EXAMS or r.eligible not in ("0", "1"):
                errors.append(f"{sid}: {r.series_id} kind/role/exam/eligible {r.kind}/{r.role}/{r.exam}/{r.eligible}")
            if r.sizing not in SIZINGS:
                errors.append(f"{sid}: {r.series_id} sizing {r.sizing!r} (one of {SIZINGS})")
        ids = set(s.series_id)
        key = m[["series_id", "window", "basis"]].assign(cost=m.cost.map(lambda c: f"{float(c):g}"))
        if key.duplicated().any():
            errors.append(f"{sid}: duplicate (series_id, window, cost, basis) rows")
        acc = {}
        for i, r in m.iterrows():
            tag = f"{sid}: {r.series_id} {r.window} {r.basis} x{r.cost}"
            if r.series_id not in ids:
                errors.append(f"{tag}: not in {sid}__series.csv")
            if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.start) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.end)
                    and r.start < r.end):
                errors.append(f"{tag}: dates {r.start} .. {r.end}")
            if r.cost not in ("1.0", "1.5", "1", "1.50"):
                errors.append(f"{tag}: cost {r.cost}")
            if r.basis not in BASES or r.dd_marks not in DD_MARKS or r.wiped not in ("0", "1"):
                errors.append(f"{tag}: basis/dd_marks/wiped {r.basis}/{r.dd_marks}/{r.wiped}")
            if r["sample"] not in SAMPLES or any(x not in DERIVABLE for x in r.derived.split(",") if x):
                errors.append(f"{tag}: sample/derived {r['sample']!r}/{r.derived!r}")
            su, fu, nu = _num(r.start_usd), _num(r.final_usd), _num(r.net_usd)
            if r.basis == "account":
                if su != ACCOUNT:
                    errors.append(f"{tag}: start_usd {r.start_usd}")
                if float(r.cost) == 1.0:
                    acc[(r.series_id, r.window)] = r
                du, dp = _num(r.max_dd_usd), _num(r.max_dd_pct)
                if du is not None and dp is not None and du < dp / 100.0 * ACCOUNT - 0.01:
                    errors.append(f"{tag}: max DD ${du:.2f} is below its {dp:.2f}% of ${ACCOUNT:,.0f}: the $ and the "
                                  "% are not on the same marks")
            elif r.basis == "unit":
                if su != 0.0 or r.return_pct != "" or r.max_dd_pct != "":
                    errors.append(f"{tag}: a unit row with start_usd {r.start_usd} or a % field")
            if fu is None or nu is None or su is None or abs(fu - su - nu) > 0.011:
                errors.append(f"{tag}: final - start != net ({r.final_usd}, {r.start_usd}, {r.net_usd})")
            if r.series_id in sym_of:
                spans.setdefault((r.window, sym_of[r.series_id]), {}).setdefault((r.start, r.end), []).append(sid)
        for w, c in cv.items():
            if list(c.columns) != CURVE_COLS:
                errors.append(f"{sid} curves {w}: columns {list(c.columns)}")
                continue
            if not c.date.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
                errors.append(f"{sid} curves {w}: a date that is not YYYY-MM-DD")
                continue
            for series_id in sorted(set(c.series_id) - ids):
                errors.append(f"{sid} curves {w}: {series_id}: not a series")
            g = c[c.series_id.isin(ids)].groupby("series_id", sort=False)
            ok = g.date.agg(lambda x: bool(x.is_monotonic_increasing and x.is_unique))
            first, last = g.first(), g.last()
            for series_id in first.index:
                tag = f"{sid} curves {w}: {series_id}"
                if not ok[series_id]:
                    errors.append(f"{tag}: dates not ascending and unique")
                    continue
                r = acc.get((series_id, w))
                if r is None:
                    errors.append(f"{tag}: no account row at x1.0 for this window")
                    continue
                d0, e0 = first.loc[series_id, "date"], float(first.loc[series_id, "equity_usd"])
                d1, e1 = last.loc[series_id, "date"], float(last.loc[series_id, "equity_usd"])
                if d0 != _dstr(_dnum(r.start) - 1) or abs(e0 - ACCOUNT) > 1e-6:
                    errors.append(f"{tag}: the opening row is {d0} {e0}, not the day before {r.start} at {ACCOUNT}")
                if d1 > _dstr(_dnum(r.end) - 1):
                    errors.append(f"{tag}: a row after the window's end {r.end}")
                if abs(e1 - float(r.final_usd)) > 0.011:
                    warnings.append(f"{tag}: the curve ends at {e1:.2f}, the row's final is {float(r.final_usd):.2f}")
    for (w, sym), by in sorted(spans.items()):
        if len(by) > 1:
            warnings.append(f"window {w} on {sym}: rows span different dates: " + "; ".join(
                f"{a} .. {z} ({', '.join(sorted(set(v)))})" for (a, z), v in sorted(by.items())))
    return {"errors": errors, "warnings": warnings}


# ───────────────────────────── the page ─────────────────────────────

# the colour groups, in legend order. The categorical palette's slots go, in its fixed order, to the groups present
# in a build: first those with curves (the line chart's groups), then those without (the scatter and the table only),
# so the hues side by side on the chart are always the palette's first slots, adjacent as validated (README;
# tests/test_compare_page.py re-checks the pairs on the built page). A series' colour follows its group, never its
# rank or the selection; buy-and-hold is the ink colour.
GROUPS = (("bots", "The bots' designs"), ("final10", "FINAL10: the final ten and its references"),
          ("tradeiq_rsi", "TradeIQ video 1: RSI replacements"), ("tradeiq_2027", "TradeIQ video 2: 2027 indicators"),
          ("bot_filters", "Entry filters on the bots' designs"), ("balke", "Balke's Four Edge (bot unit rule)"),
          ("earlier", "Earlier studies (ladder)"), ("benchmarks", "Buy and hold"))
GROUP_SHORT = {"bots": "the bots' designs", "final10": "FINAL10", "tradeiq_rsi": "study 1", "tradeiq_2027": "study 2",
               "bot_filters": "study 3", "balke": "Balke", "earlier": "the ladder", "benchmarks": "buy-and-hold"}
PALETTE = {"light": ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2"],
           "dark": ["#338ced", "#e76624", "#00a888", "#d28e05", "#e24d8b", "#0aac23", "#9887ef"]}
FEATURED_ROLES = ("design", "finalist", "champion", "base", "benchmark")
SMALL_SOURCES = ("final10", "balke", "ladder", "benchmarks")
BUDGET_MB = 11.6                      # the page stays under 12 MB


def group_slots(present: Dict[str, bool]) -> Dict[str, Optional[int]]:
    """{group: palette slot}: ``present`` maps each group of the build to whether it has curves. Groups with curves
    take the first slots in legend order, the others the next ones; buy-and-hold has none (the ink colour)."""
    order = [k for k, _ in GROUPS if k in present and k != "benchmarks"]
    order = [k for k in order if present[k]] + [k for k in order if not present[k]]
    out: Dict[str, Optional[int]] = {k: (i if i < len(PALETTE["light"]) else None) for i, k in enumerate(order)}
    if "benchmarks" in present:
        out["benchmarks"] = None
    return out


def _group_of(src: str, role: str) -> str:
    if src == "final10":
        return "bots" if role == "design" else "final10"
    return src if src in ("tradeiq_rsi", "tradeiq_2027", "bot_filters", "balke", "benchmarks") else "earlier"


def _window_order(windows: Dict[str, Tuple[str, str]]) -> List[str]:
    common = [w for w in COMMON_ORDER if w in windows]
    own = sorted((w for w in windows if w not in COMMON), key=lambda w: (windows[w][0], windows[w][1], w))
    return common + own


def _r(x, nd):
    v = _num(x)
    return None if v is None else round(v, nd)


def _encode_curve(dates: Sequence[str], eq: np.ndarray, step: int) -> list:
    """[first day number, step in days, deltas of whole dollars, last day offset, last value]: the curve carried
    forward over every calendar day, sampled every ``step`` days from its first day, its last day always kept."""
    d = _dnums(dates)
    v = np.round(np.asarray(eq, np.float64)).astype(np.int64)
    span = np.arange(d[0], d[-1] + 1)
    ix = np.searchsorted(d, span, side="right") - 1
    full = v[ix]
    sample = full[::step]
    deltas = np.r_[sample[0], np.diff(sample)]
    last_off = int(d[-1] - d[0])
    return [int(d[0]), int(step), ",".join(map(str, deltas.tolist())), last_off, int(full[-1])]


def _final_rank(notes: str) -> Optional[int]:
    """FINAL10's rank of a row in its final ten ("final ten #k" in the notes), for the page's default selection."""
    m = re.search(r"final ten #(\d+)", notes or "")
    return int(m.group(1)) if m else None


def _via(sid: str, source_file: str) -> str:
    """The study folder a row's numbers come from when it is not the source's own (multisymbol's runs and study 1's
    rebuilds of the bots' designs, study 1's 0.01-lot buy-and-hold)."""
    m = re.match(r"backtest_results/([^/]+)/", source_file or "")
    return m.group(1) if (m and m.group(1) != sid) else ""


def _table(values: List[str]) -> Tuple[List[str], List[int]]:
    """A small table of the distinct strings and each value's index into it (the page's compact string columns)."""
    tab: List[str] = []
    ix: Dict[str, int] = {}
    out = []
    for v in values:
        if v not in ix:
            ix[v] = len(tab)
            tab.append(v)
        out.append(ix[v])
    return tab, out


def build_blob(data: Path = DATA, weekly_step: int = 7, featured_extra: Iterable[str] = (),
               drop: str = "") -> Dict[str, object]:
    """
    Everything the page shows, from the contract files: series, metrics (with the page's derived extras), curves.
    The metrics keep the contract's own digits (the page rounds once, for display). Per account row at x1.0 with a
    curve the page adds: the max DD in $ at daily closes (``dly``), the worst month, the longest time under water;
    per account row the growth / DD ratio (``rdd`` = CAGR % / max DD %, FINAL10's "growth per year / DD").
    ``drop``: "" keeps every curve; "own" leaves out the curves of non-featured series on the studies' own windows,
    "all" on every window (their metrics stay; the size budget's last resorts, reported on the page).
    """
    found = sources_in(data)
    S: Dict[str, list] = {k: [] for k in ("id", "sym", "label", "src", "grp", "kind", "fam", "tf", "filt", "role",
                                          "elig", "exam", "notes", "fin", "feat", "rank", "siz", "tags")}
    M: Dict[str, list] = {k: [] for k in ("s", "w", "a", "z", "c", "b", "net", "ret", "cagr", "ddu", "ddp", "pdd",
                                          "rdd", "dly", "tr", "win", "pf", "sh", "pq", "wq", "wm", "ud", "wip", "mk",
                                          "sc", "f", "der", "smp", "rn", "via")}
    sidx: Dict[str, int] = {}
    win_dates: Dict[str, Tuple[str, str]] = {}
    spans: Dict[str, Dict[str, List[str]]] = {}
    files: List[str] = []
    curves_raw: Dict[Tuple[int, str], pd.DataFrame] = {}
    metric_rows = []
    elig_rule: Dict[str, bool] = {}
    extra = set(featured_extra)
    for sid in found:
        s, m, cv = read_source(sid, data)
        elig_rule[sid] = bool((s.eligible.astype(str) == "1").any())
        for _, r in s.iterrows():
            sidx[r.series_id] = len(S["id"])
            fin = r.role == "finalist" or (sid == "final10" and "final ten #" in r.notes)
            S["id"].append(r.series_id), S["sym"].append(r.symbol), S["label"].append(r.label)
            S["src"].append(sid), S["grp"].append(_group_of(sid, r.role)), S["kind"].append(r.kind)
            S["fam"].append(r.family), S["tf"].append(r.tf), S["filt"].append(r["filter"]), S["role"].append(r.role)
            S["elig"].append(int(r.eligible)), S["exam"].append(r.exam), S["notes"].append(r.notes[:600])
            S["fin"].append(int(bool(fin)))
            S["feat"].append(int(r.role in FEATURED_ROLES or sid in SMALL_SOURCES or fin or r.series_id in extra))
            S["rank"].append(_final_rank(r.notes) if sid == "final10" else None)
            S["siz"].append(r.sizing or "unit rule")
            S["tags"].append(r.tags)
        for w, c in cv.items():
            for series_id, g in c.groupby("series_id", sort=False):
                if series_id in sidx:
                    curves_raw[(sidx[series_id], w)] = g
        for _, r in m.iterrows():
            metric_rows.append((sid, r))
            a, z = win_dates.get(r.window, (r.start, r.end))
            win_dates[r.window] = (min(a, r.start), max(z, r.end))
            if r.series_id in sidx:
                sym = S["sym"][sidx[r.series_id]]
                sp = spans.setdefault(r.window, {}).setdefault(sym, [r.start, r.end])
                sp[0], sp[1] = min(sp[0], r.start), max(sp[1], r.end)
    # the palette slots: the groups of this build, those with curves first (group_slots)
    with_curves: Dict[str, bool] = {}
    for g in S["grp"]:
        with_curves.setdefault(g, False)
    for si, _ in curves_raw:
        with_curves[S["grp"][si]] = True
    slots = group_slots(with_curves)
    worder = _window_order(win_dates)
    widx = {w: i for i, w in enumerate(worder)}
    for sid, r in metric_rows:
        if r.series_id not in sidx:
            continue
        si = sidx[r.series_id]
        row = {k: r[k] for k in METRICS_COLS + METRICS_OPT}
        cv = curves_raw.get((si, r.window)) if row["basis"] == "account" and float(row["cost"]) == 1.0 else None
        extras: Dict[str, object] = {}
        if cv is not None and len(cv):
            extras = curve_stats(cv.date.to_numpy(), cv.equity_usd.to_numpy(np.float64), row["start"], row["end"])
            row = fill_from_curve(row, cv, extras)
        f = row["source_file"]
        if f not in files:
            files.append(f)
        M["s"].append(si), M["w"].append(widx[r.window]), M["a"].append(row["start"]), M["z"].append(row["end"])
        M["c"].append(float(row["cost"])), M["b"].append(0 if row["basis"] == "account" else 1)
        for k, col in (("net", "net_usd"), ("ret", "return_pct"), ("cagr", "cagr_pct"), ("ddu", "max_dd_usd"),
                       ("ddp", "max_dd_pct"), ("pdd", "p_dd"), ("win", "win_rate_pct"), ("pf", "profit_factor"),
                       ("sh", "sharpe_w"), ("pq", "pos_quarters_pct"), ("wq", "worst_quarter_usd"),
                       ("sc", "score_final10")):
            M[k].append(_num(row.get(col)))                  # the contract's own digits: rounded once, on the page
        cg, dp = _num(row.get("cagr_pct")), _num(row.get("max_dd_pct"))
        M["rdd"].append(round(cg / dp, 6) if (row["basis"] == "account" and cg is not None and dp) else None)
        M["dly"].append(_r(extras.get("max_dd_usd_daily"), 4))
        M["tr"].append(None if _blank(row.get("trades")) else int(float(row["trades"])))
        M["wm"].append(_r(extras.get("worst_month_usd"), 4))
        M["ud"].append(extras.get("underwater_days"))
        M["wip"].append(int(float(row["wiped"] or 0)))
        M["mk"].append(row["dd_marks"])
        M["f"].append(files.index(f))
        M["der"].append(str(row.get("derived") or ""))
        M["smp"].append(str(row.get("sample") or ""))
        M["rn"].append(str(row.get("row_notes") or ""))
        M["via"].append(_via(sid, f))
    C, dropped = encode_curves(S, curves_raw, worder, weekly_step, drop)
    pending = []
    present = set(found)
    for sid in EXPECTED_SOURCES:
        if sid not in present and SOURCES.get(sid, {}).get("pending"):
            pending.append(dict(src=sid, w="", text=SOURCES[sid]["pending"]))
    have_w: Dict[Tuple[str, str], set] = {}
    for j in range(len(M["s"])):
        si = M["s"][j]
        if M["b"][j] == 0:
            have_w.setdefault((S["src"][si], S["sym"][si]), set()).add(worder[M["w"][j]])
    for (sid, w), text in PENDING_WINDOWS.items():
        if sid in present and not any(w in v for (s2, _), v in have_w.items() if s2 == sid):
            pending.append(dict(src=sid, w=w, text=text))
    # per source and symbol, the common windows it has no account rows on (build reports them; the page says so)
    missing = []
    for (sid, sym), ws in sorted(have_w.items()):
        lack = [w for w in COMMON_ORDER if w not in ws]
        if lack:
            missing.append(dict(src=sid, sym=sym, w=lack, later=[w for w in lack if (sid, w) in PENDING_WINDOWS]))
    sources = []
    for sid in list(EXPECTED_SOURCES) + [x for x in found if x not in EXPECTED_SOURCES]:
        meta = SOURCES.get(sid, {})
        study = meta.get("study")
        if sid in present:
            ss = pd.read_csv(Path(data) / f"{sid}__series.csv", dtype=str, keep_default_na=False, nrows=1)
            study = ss.study.iloc[0] if len(ss) else study
        sources.append(dict(src=sid, study=study or sid, short=meta.get("short", sid), present=sid in present,
                            grp=_group_of(sid, ""), elig=bool(elig_rule.get(sid, False))))
    windows = [dict(key=w, text=WINDOW_META.get(w, ("Other", w))[1], owner=WINDOW_META.get(w, ("Other", w))[0],
                    common=w in COMMON, a=win_dates[w][0], z=win_dates[w][1], span=spans.get(w, {}))
               for w in worder]
    return dict(v=2, built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), S=S, M=M, C=C, files=files,
                windows=windows, pending=pending, missing=missing, sources=sources,
                groups=[dict(key=k, name=n, short=GROUP_SHORT.get(k, k), slot=slots.get(k)) for k, n in GROUPS],
                palette=PALETTE, res=dict(weekly_step=weekly_step, drop=drop, dropped=dropped),
                _raw=dict(curves=curves_raw, worder=worder))


def encode_curves(S: Dict[str, list], curves_raw: Dict[Tuple[int, str], pd.DataFrame], worder: Sequence[str],
                  weekly_step: int, drop: str = "") -> Tuple[Dict[str, Dict[str, list]], int]:
    """The page's curves: daily for the featured series (and the small sources), every ``weekly_step`` days for the
    rest; with ``drop`` "own" / "all", none for the non-featured series on the own / on every window."""
    C: Dict[str, Dict[str, list]] = {w: {} for w in worder}
    dropped = 0
    for (si, w), g in curves_raw.items():
        if w not in C:
            continue
        if not S["feat"][si] and (drop == "all" or (drop == "own" and w not in COMMON)):
            dropped += 1
            continue
        step = 1 if S["feat"][si] else weekly_step
        C[w][str(si)] = _encode_curve(g.date.to_numpy(), g.equity_usd.to_numpy(np.float64), step)
    return C, dropped


NUM_KEYS = ("s", "w", "c", "b", "net", "ret", "cagr", "ddu", "ddp", "pdd", "rdd", "dly", "tr", "win", "pf", "sh", "pq",
            "wq", "wm", "ud", "wip", "sc", "f")
STR_KEYS = ("a", "z", "mk", "der", "smp", "rn", "via")      # as indexes into a table of their distinct values


def _num_str(v) -> str:
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def pack_blob(blob: Dict[str, object]) -> Dict[str, object]:
    """The page's compact form of the metrics: each numeric column one comma-joined string (an empty field is a
    missing value, every number keeps its digits), each string column an index list into a table of its distinct
    values (``T``)."""
    M = blob["M"]
    P: Dict[str, object] = {k: ",".join(_num_str(v) for v in M[k]) for k in NUM_KEYS}
    T: Dict[str, List[str]] = {}
    for k in STR_KEYS:
        T[k], ix = _table(list(M[k]))
        P[k] = ",".join(map(str, ix))
    P["n"] = len(M["s"])
    out = {k: v for k, v in blob.items() if not k.startswith("_")}
    out.update(M=P, T=T, K=dict(num=list(NUM_KEYS), str=list(STR_KEYS)))
    return out


def unpack_blob(packed: Dict[str, object]) -> Dict[str, object]:
    """``pack_blob`` undone (what the page's script does when it loads)."""
    P = packed["M"]
    n = int(P["n"])

    def nums(x):
        return [] if n == 0 else [None if t == "" else (float(t) if any(c in t for c in ".e") else int(t))
                                  for t in x.split(",")]
    M = {k: nums(P[k]) for k in NUM_KEYS}
    for k in STR_KEYS:
        M[k] = [packed["T"][k][i] for i in nums(P[k])]
    out = dict(packed)
    out["M"] = M
    return out


def _json(obj) -> str:
    s = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")


def windows_note(blob: Dict[str, object]) -> str:
    """The intro's sentence on the 5-year window, from the data: which present sources lack it."""
    short = {s["src"]: s["short"] for s in blob["sources"]}
    lack = [f"{short.get(x['src'], x['src'])} on {SYMBOL_NAME.get(x['sym'], x['sym']).split(' ')[0]}"
            for x in blob["missing"] if "5y" in x["w"]]
    if not lack:
        return "the window every source on this page has"
    return "every source on this page has it except " + ", ".join(lack)


def build(data: Path = DATA, out: Path = PAGE, log=print) -> Dict[str, object]:
    """Write the page: one self-contained HTML file (Plotly, the data and the code inline; no request leaves it)."""
    import plotly.offline as po
    rep = validate(data)
    if rep["errors"]:
        raise ValueError("the contract files have errors:\n  " + "\n  ".join(rep["errors"][:30]))
    plotly_js = po.get_plotlyjs()
    tries = []
    blob = build_blob(data, weekly_step=7)
    for step, drop in ((7, ""), (14, ""), (28, ""), (56, ""), (56, "own"), (56, "all")):
        if (step, drop) != (7, ""):
            blob["C"], dropped = encode_curves(blob["S"], blob["_raw"]["curves"], blob["_raw"]["worder"], step, drop)
            blob["res"] = dict(weekly_step=step, drop=drop, dropped=dropped)
        page = PAGE_HTML.replace("__CSS__", PAGE_CSS).replace("__NOTES__", notes_html(blob)) \
            .replace("__FIVE__", html.escape(windows_note(blob))) \
            .replace("__APP__", PAGE_JS).replace("__PLOTLY__", plotly_js.replace("</script", "<\\/script")) \
            .replace("__DATA__", _json(pack_blob(blob)))
        mb = len(page.encode("utf-8")) / 1e6
        tries.append((step, drop, round(mb, 2)))
        if mb <= BUDGET_MB:
            break
    else:
        raise ValueError(f"the page is {mb:.1f} MB even without the non-featured curves: {tries}; the metrics alone "
                         f"exceed the budget, so a source must be split onto its own page")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(page, encoding="utf-8")
    n_curves = sum(len(v) for v in blob["C"].values())
    log(f"wrote {_rel(Path(out))}: {mb:.2f} MB ({len(blob['S']['id'])} series, {len(blob['M']['s'])} metrics rows, "
        f"{n_curves} curves; non-featured curves every {blob['res']['weekly_step']} days, "
        f"{blob['res']['dropped']} left out; tries {tries}); "
        f"{len(rep['warnings'])} warnings")
    for x in blob["missing"]:
        later = f" ({', '.join(x['later'])} computed later)" if x["later"] else ""
        log(f"  {x['src']} on {x['sym']}: no account rows on {', '.join(x['w'])}{later}")
    blob.pop("_raw", None)
    return dict(mb=mb, step=blob["res"]["weekly_step"], tries=tries, warnings=rep["warnings"], blob=blob)


PAGE_CSS = r'''
:root {
  color-scheme: light;
  --surface: #ffffff; --page: #f9f9f9; --ink: #191919; --ink2: #666666; --grid: #e7e7e7; --axis: #c2c2c2;
  --border: rgba(11,11,11,0.10); --good: #006c10; --bad: #c62f30; --wash: rgba(37,125,224,0.08);
  --context: #c9c9c9; --focus: #257de0;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface: #191919; --page: #0b0b0b; --ink: #efefef; --ink2: #9c9c9c; --grid: #303030; --axis: #474747;
    --border: rgba(255,255,255,0.10); --good: #53c556; --bad: #eb6263; --wash: rgba(51,140,237,0.14);
    --context: #4a4a4a; --focus: #338ced;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface: #191919; --page: #0b0b0b; --ink: #efefef; --ink2: #9c9c9c; --grid: #303030; --axis: #474747;
  --border: rgba(255,255,255,0.10); --good: #53c556; --bad: #eb6263; --wash: rgba(51,140,237,0.14);
  --context: #4a4a4a; --focus: #338ced;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 14.5px/1.5 system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 1400px; margin: 0 auto; padding: 18px 18px 60px; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
h1 { font-size: 25px; line-height: 1.25; margin: 4px 0 4px; font-weight: 650; }
h2 { font-size: 18px; margin: 0; font-weight: 650; }
h2 .hview { font-size: 13.5px; font-weight: 400; color: var(--ink2); margin-left: 6px; }
h3 { font-size: 15px; margin: 14px 0 6px; font-weight: 650; }
p { margin: 6px 0; }
.sub { color: var(--ink2); margin: 0; font-size: 13.5px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px;
  margin: 12px 0; }
.intro ul { margin: 4px 0; padding-left: 20px; }
.intro li { margin: 3px 0; }
.note { color: var(--ink2); font-size: 13px; }
.bar { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; }
.sticky { position: sticky; top: 0; z-index: 6; background: var(--page); padding: 8px 0; margin: 0;
  border-bottom: 1px solid var(--border); }
#filters { z-index: 5; }
.lbl { color: var(--ink2); font-size: 12.5px; margin-right: 6px; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; vertical-align: middle; }
.seg button { font: inherit; font-size: 13px; background: var(--surface); color: var(--ink); border: 0;
  padding: 5px 11px; cursor: pointer; border-right: 1px solid var(--border); }
.seg button:last-child { border-right: 0; }
.seg button:hover { background: var(--wash); }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--surface); }
.seg button:disabled { color: var(--ink2); background: var(--surface); cursor: not-allowed; opacity: 0.55; }
button:focus-visible, select:focus-visible, input:focus-visible, summary:focus-visible {
  outline: 2px solid var(--focus); outline-offset: 1px; }
.btn { font: inherit; font-size: 13px; background: var(--surface); color: var(--ink); border: 1px solid var(--border);
  border-radius: 8px; padding: 5px 11px; cursor: pointer; white-space: nowrap; }
.btn:hover { background: var(--wash); }
.btn[aria-pressed="true"] { background: var(--ink); color: var(--surface); }
.btn:disabled { color: var(--ink2); cursor: not-allowed; opacity: 0.55; }
select, input[type="search"] { font: inherit; font-size: 13px; color: var(--ink); background: var(--surface);
  border: 1px solid var(--border); border-radius: 8px; padding: 5px 8px; max-width: 230px; }
#ownwin { max-width: 400px; }
input[type="search"] { width: 210px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
.pending { margin: 8px 0 0; padding: 8px 12px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface); font-size: 13px; }
.pending:empty { display: none; }
.pending b { font-weight: 600; }
.pending .clock { display: inline-block; width: 10px; height: 10px; border: 2px solid var(--ink2); border-radius: 50%;
  margin-right: 7px; vertical-align: -1px; }
.pending .info { display: inline-block; width: 10px; height: 10px; background: var(--ink2); border-radius: 2px;
  margin-right: 7px; vertical-align: -1px; }
#chart { width: 100%; height: 660px; }
.panels { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 12px; margin-top: 8px; }
.panel { border: 1px solid var(--border); border-radius: 10px; padding: 8px 8px 2px; }
.panel h3 { margin: 0 0 2px 4px; font-size: 13.5px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.panel h3 .smp { color: var(--ink2); font-weight: 400; font-size: 12.5px; }
.panel .pl { width: 100%; height: 300px; }
.panel .empty { color: var(--ink2); font-size: 13px; padding: 30px 8px; text-align: center; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle; flex: none; }
svg.key { vertical-align: middle; margin-right: 4px; }
.tw { overflow-x: auto; margin: 8px 0 4px; border: 1px solid var(--border); border-radius: 10px; }
table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 12px; }
th, td { padding: 4px 6px; border-bottom: 1px solid var(--grid); text-align: left; vertical-align: top; white-space: nowrap;
  background: var(--surface); }
thead th { color: var(--ink2); font-weight: 600; border-bottom: 1px solid var(--axis); }
th .thb { font: inherit; color: inherit; background: none; border: 0; padding: 0; margin: 0; cursor: pointer;
  text-align: inherit; font-weight: 600; white-space: nowrap; }
th .thb:hover { color: var(--ink); text-decoration: underline; }
thead th.n, td.n { text-align: right; font-variant-numeric: tabular-nums; }
thead th[aria-sort="ascending"] .thb::after { content: " \25B2"; font-size: 9px; }
thead th[aria-sort="descending"] .thb::after { content: " \25BC"; font-size: 9px; }
th.lab, td.lab { position: sticky; left: 0; z-index: 1; box-shadow: 1px 0 0 var(--grid); }
td.lab { white-space: normal; min-width: 260px; max-width: 360px; }
td.lab label { display: flex; gap: 6px; align-items: flex-start; cursor: pointer; }
td.lab input { margin: 2px 0 0; flex: none; }
td.lab .nm { font-weight: 550; }
td.lab .meta { color: var(--ink2); font-size: 11.5px; }
.badge { display: inline-block; border: 1px solid var(--axis); border-radius: 6px; padding: 0 5px; margin: 1px 4px 1px 0;
  font-size: 11px; line-height: 16px; color: var(--ink); white-space: nowrap; }
details.nt { margin-top: 2px; font-size: 11.5px; color: var(--ink2); }
details.nt summary { cursor: pointer; width: max-content; }
details.nt div { margin: 2px 0 0; white-space: normal; }
tr.on td { background: linear-gradient(var(--wash), var(--wash)), var(--surface); }
td .der { text-decoration: underline dotted var(--ink2); text-underline-offset: 3px; }
.pass { color: var(--good); font-weight: 600; }
.pass::before { content: "\2713\00a0"; }
.fail { color: var(--bad); font-weight: 600; }
.fail::before { content: "\2717\00a0"; }
.dim { color: var(--ink2); }
.vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.pager { display: flex; gap: 10px; align-items: center; color: var(--ink2); font-size: 13px; }
.notes h3 { margin-top: 12px; }
.notes ul { padding-left: 20px; margin: 4px 0; }
.notes li { margin: 3px 0; font-size: 13.5px; }
code { font-size: 12px; background: var(--wash); padding: 1px 4px; border-radius: 4px; }
footer { color: var(--ink2); font-size: 12.5px; margin-top: 16px; }
#toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: var(--ink); color: var(--surface);
  padding: 7px 14px; border-radius: 8px; font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 9; }
#toast.show { opacity: 1; }
@media (max-width: 900px) { .panels { grid-template-columns: 1fr; } }
'''


PAGE_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Every backtest on the bot's $2,000 account: gold and BTC</title>
<style>__CSS__</style>
<script>
(function () { var h = (location.hash || "") + "&" + (location.search || "");
  if (/(^|[#&?])(theme=)?dark(&|$)/.test(h)) document.documentElement.setAttribute("data-theme", "dark");
  if (/(^|[#&?])(theme=)?light(&|$)/.test(h)) document.documentElement.setAttribute("data-theme", "light"); })();
</script>
</head>
<body class="viz-root">
<main>
<header>
  <div>
    <h1>Every backtest on the bot's $2,000 account: gold and BTC</h1>
    <p class="sub" id="built"></p>
  </div>
  <button class="btn" id="themebtn" type="button" title="Cycle the colour theme: auto, light, dark">Theme: auto</button>
</header>

<section class="card intro" aria-label="What this page compares">
<ul>
<li><b>What is compared:</b> the designs the bots run and FINAL10's final ten (with its references); study 1, TradeIQ
video 1 (750 RSI-rule variants); study 2, TradeIQ video 2 (about 1,460 variants of nine indicators) and study 3 (59
entry filters on the five bots' designs, about 300 variants; its finalists and bases are shown), each as soon as its
files arrive; René Balke's strategies on the bot's unit rule; the DCA-ladder study's unit-rule accounts; and
buy-and-hold.</li>
<li><b>The account:</b> one fresh $2,000 account per row and window, nothing withdrawn, with FINAL10's sizing: units =
floor(balance / 2,500) + 1, at most 10, times 0.01 lot. The exceptions say so: the risk-sized FINAL10 rows (a
"risk-sized" badge, kept out of the Top 10) and the two buy-and-hold lines. "Per 0.01 lot" switches the scatter and the
table to the studies' unit results: always 0.01 lot, no account.</li>
<li><b>Windows</b> (UTC, end exclusive): <b>5y</b> 13 Nov 2021 - 13 Nov 2026, __FIVE__; <b>8y</b> from 13 Nov 2018;
<b>new</b> 13 Nov 2018 - 1 Jan 2021, FINAL10's only out-of-sample window; <b>1y</b> the last year, in-sample for
FINAL10. Each study's own windows are under "Study windows", named after the study that owns them, with their real dates
in the table.</li>
<li><b>Costs:</b> x1.0 is the broker's own spread from the tick data. x1.5 makes every spread one and a half times as
wide, as a stress test; only study 1 has it, per 0.01 lot, on its own windows. No swap and no commission anywhere.</li>
<li><b>In or out of sample</b> (the Sample column): out-of-sample means no choice of that row read the window:
FINAL10's new window, study 1's hold-out (and 1y, which lies inside it), and the exams of studies 2 and 3 when they
arrive. The bots' designs are in-sample on every window from 2021 on, whichever study ran them. Read in-sample numbers as
a description, not a forecast.</li>
</ul>
</section>

<div class="bar sticky" role="toolbar" aria-label="Symbol and window" id="mainbar">
  <span><span class="lbl">Symbol</span><span class="seg" id="symseg"></span></span>
  <span><span class="lbl">Window</span><span class="seg" id="winseg"></span>
    <select id="ownwin" aria-label="Study windows"></select></span>
  <span class="note" id="viewnote"></span>
</div>
<div class="pending" id="pending" aria-live="polite"></div>

<section class="card" aria-labelledby="h-chart">
  <div class="head">
    <h2 id="h-chart">Equity and drawdown of the selected series <span class="hview" id="hv-chart"></span></h2>
    <div class="bar">
      <button class="btn" type="button" id="q-bots" title="The designs the live bots run, with buy-and-hold">Bots</button>
      <button class="btn" type="button" id="q-fin" title="Every study's finalists (FINAL10's ten included), with buy-and-hold">Finalists</button>
      <button class="btn" type="button" id="q-top" title="The 10 unit-rule $2,000 accounts of this window at x1.0 with the highest growth ÷ DD (CAGR % ÷ max DD %), with buy-and-hold; the basis, costs and filters below do not apply">Top 10 accounts by growth ÷ DD</button>
      <button class="btn" type="button" id="q-clear">Clear</button>
      <button class="btn" type="button" id="logbtn" aria-pressed="false">Log scale</button>
    </div>
  </div>
  <p class="note" id="selnote"></p>
  <div id="chart" role="group" aria-label="Equity curves of the selected series ($2,000 accounts at x1.0 costs), with their drawdown below them" aria-describedby="selnote"></div>
  <p class="note">Each line is one $2,000 account at x1.0 costs (the curves every study keeps), equity at the end of each
  UTC day; the basis and cost switches further down apply to the scatter and the table only. The drawdown below is the
  fall from the running peak of the line drawn, at daily closes, so it can be shallower than the table's Max DD %, which
  each study measured on its own finer marks. Click a legend entry to hide a line, double-click to keep only it. Colour
  shows the study; within a study, the dash (and past six lines a marker) tells the drawn lines apart.</p>
</section>

<div class="bar sticky" role="toolbar" aria-label="Basis, costs and filters of the scatter and the table" id="filters">
  <span><span class="lbl">Basis</span><span class="seg" id="basisseg"></span></span>
  <span><span class="lbl">Costs</span><span class="seg" id="costseg"></span></span>
  <input type="search" id="q" placeholder="Search series, rules, notes" aria-label="Search">
  <select id="f-src" aria-label="Study"></select>
  <select id="f-kind" aria-label="Kind"></select>
  <select id="f-fam" aria-label="Family"></select>
  <select id="f-tf" aria-label="Timeframe"></select>
  <select id="f-role" aria-label="Role"></select>
  <select id="f-exam" aria-label="Exam"></select>
  <button class="btn" type="button" id="f-reset">Reset filters</button>
  <span class="note" id="fnote"></span>
</div>

<section class="card" aria-labelledby="h-scatter">
  <div class="head">
    <h2 id="h-scatter">Risk and return of every series <span class="hview" id="hv-scatter"></span></h2>
    <div class="bar"><span class="lbl">Up the side</span><span class="seg" id="yseg"></span></div>
  </div>
  <p class="note" id="scnote">One panel per study, on the same scales: its series in its colour, every other series of
  this view in grey behind them, buy-and-hold as a diamond in the text colour. A cross is a wiped account (wiped accounts
  stack at a 100% drawdown; the heading counts them). A triangle on the top edge is off the scale (its value is beside
  it). Click a point to add its curve to the chart.</p>
  <div class="panels" id="panels"></div>
</section>

<section class="card" aria-labelledby="h-table">
  <div class="head"><h2 id="h-table">Every series, with its numbers <span class="hview" id="hv-table"></span></h2>
    <div class="pager" id="pager"></div></div>
  <p class="note">Sort with a column's header button (numbers sort as numbers, blanks last). Tick a row to draw its
  curve; "Notes" opens its caveats. A <span class="der">dotted</span> value was not in the study's files and was computed
  here: from the daily curve, or from the row's own final equity or trade files. Max DD $ is on the same marks as Max DD %
  (the DD marks column), or empty where the study publishes the drawdown in % only; "DD $, daily closes" is the page's
  own figure off the daily curve. The table scrolls sideways; the Series column stays.</p>
  <div class="tw"><table id="tbl"><thead></thead><tbody></tbody></table></div>
</section>

<section class="card notes" aria-labelledby="h-notes">
<h2 id="h-notes">What the numbers are</h2>
__NOTES__
</section>
<footer id="foot"></footer>
</main>
<div id="toast" role="status"></div>
<script>__PLOTLY__</script>
<script type="application/json" id="data">__DATA__</script>
<script>__APP__</script>
</body>
</html>
'''


PAGE_JS = r'''
(function () {
"use strict";
var D = JSON.parse(document.getElementById("data").textContent);
(function unpack() {             // pack_blob: numeric columns as comma-joined strings, string columns as table indexes
  var P = D.M, n = P.n, U = {};
  var nums = function (x) { return n ? x.split(",").map(function (t) { return t === "" ? null : +t; }) : []; };
  D.K.num.forEach(function (k) { U[k] = nums(P[k]); });
  D.K.str.forEach(function (k) { var tab = D.T[k]; U[k] = nums(P[k]).map(function (i) { return tab[i]; }); });
  D.M = U;
})();
var S = D.S, M = D.M, NS = S.id.length, NM = M.s.length, W = D.windows;
var GI = {}, GORDER = [];
D.groups.forEach(function (g) { GI[g.key] = g; GORDER.push(g.key); });
var SRC = {};
D.sources.forEach(function (s) { SRC[s.src] = s; });
var DASH = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"];
var DASH_SVG = { solid: "", dash: "6,4", dot: "2,3", dashdot: "6,3,2,3", longdash: "11,4", longdashdot: "11,3,2,3" };
var MSYM = ["circle", "square", "diamond", "triangle-up", "x", "star"];
var ROLES = ["design", "base", "finalist", "champion", "qualified", "variant", "benchmark"];
var DER = { return_pct: "ret", cagr_pct: "cagr", max_dd_usd: "ddu", p_dd: "pdd", profit_factor: "pf", sharpe_w: "sh",
            pos_quarters_pct: "pq", worst_quarter_usd: "wq" };
var DER_HOW = { ret: "computed here from the row's final equity", cagr: "computed here from the row's final equity",
                pf: "computed here from the study's trade files", pdd: "computed here: net profit / max DD $",
                ddu: "computed here from the daily curve (this row's drawdown is on daily marks)" };
var SAMPLE_TEXT = { out: "out-of-sample", "in": "in-sample", mixed: "partly", "": "" };
var SAMPLE_TIP = {
  bots: "FINAL10 chose the designs with data from 2021 on (Top 1-3 tuned on 2023-2026, V3-lite fixed on 2024 - Nov 2026): only its new window is out-of-sample for them, on whichever study's run",
  final10: "FINAL10's selection read 2021 - Nov 2026: only its new window (Nov 2018 - Dec 2020) is out-of-sample",
  tradeiq_rsi: "study 1 chose on development + validation (2019 - Jun 2024); its hold-out from 1 Jul 2024 (1y lies inside it) was sealed until its exam" };
var FONT = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';
var NARROW = 1150;               // below this chart width the legend goes under the plot
var root = document.documentElement;
var CFG = { displaylogo: false, responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines",
                                     "hoverClosestCartesian", "hoverCompareCartesian"] };

function $(id) { return document.getElementById(id); }
function el(tag, attrs, text) {
  var e = document.createElement(tag);
  if (attrs) for (var k in attrs) { if (k === "class") e.className = attrs[k]; else e.setAttribute(k, attrs[k]); }
  if (text != null) e.textContent = text;
  return e;
}
function cssv(n) { return getComputedStyle(root).getPropertyValue(n).trim(); }
function mode() {
  var t = root.getAttribute("data-theme");
  if (t) return t;
  return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function gcolor(key) { var g = GI[key]; return (g && g.slot != null) ? D.palette[mode()][g.slot] : cssv("--ink"); }
function scolor(i) { return gcolor(S.grp[i]); }
function gname(key) { return GI[key] ? GI[key].name : key; }
function gshort(key) { return GI[key] ? GI[key].short : key; }
function shortText(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
// labels are data: Plotly reads a subset of HTML in names and hover text, so &, < and > go in as entities, and no label
// is ever part of a template string (the hover shows it through %{fullData.name})
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function cmpStr(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
function fmtUsd(v) {
  if (v == null) return "";
  var a = Math.abs(v), s = a >= 100 ? Math.round(a).toLocaleString("en-US") : a.toFixed(2);
  return (v < 0 ? "-$" : "$") + s;
}
function pct1(v) { return v == null ? "" : v.toFixed(1) + "%"; }
function pct0(v) { return v == null ? "" : Math.round(v) + "%"; }
function num2(v) { return v == null ? "" : v.toFixed(2); }
function fmtInt(v) { return v == null ? "" : Math.round(v).toLocaleString("en-US"); }
function dayStr(n) { return new Date(n * 86400000).toISOString().slice(0, 10); }
function symName(s) { return s === "BTCUSDm" ? "BTC" : "Gold"; }
function toast(msg) { var t = $("toast"); t.textContent = msg; t.className = "show"; clearTimeout(toast.h);
  toast.h = setTimeout(function () { t.className = ""; }, 3200); }

// ---------- indexes ----------
var view = {}, winSyms = {};
for (var j = 0; j < NM; j++) {
  var sym0 = S.sym[M.s[j]], key0 = sym0 + "|" + M.w[j] + "|" + M.b[j] + "|" + M.c[j];
  (view[key0] || (view[key0] = [])).push(j);
  (winSyms[M.w[j]] || (winSyms[M.w[j]] = {}))[sym0] = true;
}
function wIndex(k) { for (var i = 0; i < W.length; i++) if (W[i].key === k) return i; return -1; }
var W5 = Math.max(wIndex("5y"), 0);

// ---------- state ----------
var st = { sym: "XAUUSDm", w: W5, b: 0, c: 1, log: false, y: "net", sel: {}, sort: { k: "", dir: -1 }, page: 0,
           per: 100, q: "", f: { grp: "", kind: "", fam: "", tf: "", role: "", exam: "" } };
var themes = ["auto", "light", "dark"], theme = root.getAttribute("data-theme") || "auto";
function hasView(b, c) { return !!view[st.sym + "|" + st.w + "|" + b + "|" + c]; }
function viewRows() { return view[st.sym + "|" + st.w + "|" + st.b + "|" + st.c] || []; }
function bcText(b, c) { return (b ? "per 0.01 lot" : "account $2,000") + " at x" + (c === 1 ? "1.0" : "1.5"); }
function fixView() {             // keep the basis and the costs on a combination this window has rows for
  if (hasView(st.b, st.c)) return "";
  var order = [[st.b, 1], [0, 1], [1, 1], [1, 1.5], [0, 1.5]];
  for (var i = 0; i < order.length; i++) if (hasView(order[i][0], order[i][1])) {
    var was = bcText(st.b, st.c);
    st.b = order[i][0]; st.c = order[i][1];
    return was + " has no rows on " + W[st.w].key + ": showing " + bcText(st.b, st.c);
  }
  return "";
}
// the default selection: the bots' designs, buy-and-hold, and at most three finalists per study (FINAL10's by its rank,
// unit-rule rows first)
function rankKey(i) { return (S.siz[i] !== "unit rule" ? 1000 : 0) + (S.rank[i] == null ? 99 : S.rank[i]); }
function defaults(sym) {
  var s = new Set(), cand = [], per = {};
  for (var i = 0; i < NS; i++) {
    if (S.sym[i] !== sym) continue;
    if (S.role[i] === "design" || S.role[i] === "benchmark") s.add(i);
    else if (S.fin[i]) cand.push(i);
  }
  cand.sort(function (a, b) { return (rankKey(a) - rankKey(b)) || cmpStr(S.label[a], S.label[b]); });
  cand.forEach(function (i) { var g = S.grp[i]; if ((per[g] || 0) < 3) { s.add(i); per[g] = (per[g] || 0) + 1; } });
  return s;
}
st.sel.XAUUSDm = defaults("XAUUSDm");
st.sel.BTCUSDm = defaults("BTCUSDm");

// ---------- the link: #sym=BTC&w=full&b=unit&c=1.5&y=cagr&log&dark (read at load and on hashchange, written back) ----
function readUrl() {
  var h = ((location.hash || "") + "&" + (location.search || "")).replace(/^[#?]/, "").replace(/[?#]/g, "&");
  var o = {};
  h.split("&").forEach(function (kv) {
    if (!kv) return;
    var p = kv.split("="), k = decodeURIComponent(p[0] || ""), v = decodeURIComponent(p.slice(1).join("=") || "");
    if (k === "sym") o.sym = /btc/i.test(v) ? "BTCUSDm" : "XAUUSDm";
    if (k === "w") o.w = v;
    if (k === "b") o.b = v === "unit" ? 1 : 0;
    if (k === "c") o.c = v === "1.5" ? 1.5 : 1;
    if (k === "y") o.y = v === "cagr" ? "cagr" : "net";
    if (k === "log") o.log = true;
    if (k === "dark" || k === "light" || k === "auto") o.theme = k;
    if (k === "theme" && themes.indexOf(v) >= 0) o.theme = v;
  });
  if (o.sym) st.sym = o.sym;
  if (o.w != null) { var i = wIndex(o.w); st.w = i >= 0 ? i : W5; }
  if (!(winSyms[st.w] || {})[st.sym]) st.w = W5;
  st.b = o.b || 0; st.c = o.c || 1; st.y = o.y || "net"; st.log = !!o.log;
  theme = o.theme || "auto";              // the link holds the theme whenever it is not auto
}
function writeUrl() {
  var parts = ["sym=" + (st.sym === "BTCUSDm" ? "BTC" : "gold"), "w=" + encodeURIComponent(W[st.w].key)];
  if (st.b) parts.push("b=unit");
  if (st.c !== 1) parts.push("c=1.5");
  if (st.y === "cagr") parts.push("y=cagr");
  if (st.log) parts.push("log");
  if (theme !== "auto") parts.push(theme);
  var h = "#" + parts.join("&");
  if (location.hash !== h) { try { history.replaceState(null, "", h); } catch (e) { /* a file: page may refuse */ } }
}

// ---------- curves ----------
var cache = {};
function hasCurve(si, wk) { var c = D.C[wk]; return !!(c && c[si]); }
function curve(si, wk) {
  var k = si + "|" + wk;
  if (k in cache) return cache[k];
  var e = (D.C[wk] || {})[si];
  if (!e) return (cache[k] = null);
  var d0 = e[0], step = e[1], parts = e[2].split(","), lastOff = e[3], lastVal = e[4], x = [], y = [], v = 0;
  for (var i = 0; i < parts.length; i++) { v += +parts[i]; x.push(dayStr(d0 + i * step)); y.push(v); }
  if ((parts.length - 1) * step < lastOff) { x.push(dayStr(d0 + lastOff)); y.push(lastVal); }
  return (cache[k] = { x: x, y: y, step: step });
}
function drawdown(y) {
  var p = -Infinity, out = new Array(y.length);
  for (var i = 0; i < y.length; i++) { if (y[i] > p) p = y[i]; out[i] = p > 0 ? (y[i] / p - 1) * 100 : 0; }
  return out;
}

// ---------- the view and its filters ----------
function passes(j) {
  var i = M.s[j], f = st.f;
  if (f.grp && S.grp[i] !== f.grp) return false;
  if (f.kind && S.kind[i] !== f.kind) return false;
  if (f.fam && S.fam[i] !== f.fam) return false;
  if (f.tf && S.tf[i] !== f.tf) return false;
  if (f.role && S.role[i] !== f.role) return false;
  if (f.exam && (S.exam[i] || "not examined") !== f.exam) return false;
  if (st.q) {
    var hay = (S.label[i] + " " + S.id[i] + " " + S.notes[i] + " " + S.fam[i] + " " + S.filt[i] + " " + S.tags[i] + " " +
               S.siz[i]).toLowerCase();
    var words = st.q.split(/\s+/);
    for (var w = 0; w < words.length; w++) if (words[w] && hay.indexOf(words[w]) < 0) return false;
  }
  return true;
}

// ---------- controls ----------
function seg(container, items, current, onPick) {
  container.textContent = "";
  items.forEach(function (it) {
    var b = el("button", { type: "button", "aria-pressed": String(it.v === current) }, it.t);
    if (it.title) b.title = it.title;
    if (it.disabled) b.disabled = true;
    b.addEventListener("click", function () { onPick(it.v); });
    container.appendChild(b);
  });
}
function viewText() { return symName(st.sym) + " · " + W[st.w].key + " · " + bcText(st.b, st.c); }
function renderControls() {
  seg($("symseg"), [{ v: "XAUUSDm", t: "Gold" }, { v: "BTCUSDm", t: "BTC" }], st.sym, function (v) {
    st.sym = v; st.page = 0;
    if (!(winSyms[st.w] || {})[v]) { toast(W[st.w].key + " has no " + symName(v) + " rows: showing 5y"); st.w = W5; }
    renderAll();
  });
  var common = [];
  W.forEach(function (w, i) {
    if (w.common) common.push({ v: i, t: w.key, title: w.text + " (UTC, end exclusive)", disabled: !(winSyms[i] || {})[st.sym] });
  });
  seg($("winseg"), common, st.w, function (v) { st.w = v; st.page = 0; renderAll(); });
  var sel = $("ownwin"), og = {};
  sel.textContent = "";
  sel.appendChild(el("option", { value: "" }, W[st.w].common ? "Study windows…" : "Study windows:"));
  W.forEach(function (w, i) {
    if (w.common || !(winSyms[i] || {})[st.sym]) return;
    var owner = w.owner || "Other";
    if (!og[owner]) { og[owner] = el("optgroup", { label: owner }); sel.appendChild(og[owner]); }
    var o = el("option", { value: String(i) }, w.key + " — " + w.text);
    if (i === st.w) o.selected = true;
    og[owner].appendChild(o);
  });
  sel.onchange = function () { if (sel.value !== "") { st.w = +sel.value; st.page = 0; renderAll(); } };
  var acc = hasView(0, 1) || hasView(0, 1.5), unitOk = hasView(1, 1) || hasView(1, 1.5);
  seg($("basisseg"), [
    { v: 0, t: "Account $2,000", disabled: !acc, title: acc ? "$2,000 accounts" : "no $2,000 account rows on this window" },
    { v: 1, t: "Per 0.01 lot", disabled: !unitOk, title: unitOk ? "always 0.01 lot, no account (the studies' unit results)" : "no per-0.01-lot rows on this window" }],
    st.b, function (v) { st.b = v; if (!hasView(v, st.c)) st.c = hasView(v, 1) ? 1 : 1.5; st.page = 0; renderAll(); });
  seg($("costseg"), [
    { v: 1, t: "x1.0", disabled: !hasView(st.b, 1), title: "the broker's own spread" },
    { v: 1.5, t: "x1.5", disabled: !hasView(st.b, 1.5),
      title: hasView(st.b, 1.5) ? "every spread x1.5" : "x1.5 exists only for study 1, per 0.01 lot, on its own windows" }],
    st.c, function (v) { st.c = v; st.page = 0; renderAll(); });
  var unit = st.b === 1;
  seg($("yseg"), [{ v: "net", t: unit ? "Net per 0.01 lot $" : "Net profit $" },
                  { v: "cagr", t: "CAGR %", disabled: unit, title: unit ? "per 0.01 lot has no account, so no CAGR" : "growth per year of the $2,000 account" }],
      unit ? "net" : st.y, function (v) { st.y = v; renderControls(); renderScatter(); writeUrl(); });
  $("logbtn").setAttribute("aria-pressed", String(st.log));
  var w = W[st.w], sp = (w.span || {})[st.sym];
  $("viewnote").textContent = w.text + (sp ? " · " + symName(st.sym) + " rows " + sp[0] + " → " + sp[1] + " (end excl.)" : "");
  $("hv-chart").textContent = "· " + symName(st.sym) + " · " + w.key + " · account $2,000 at x1.0";
  $("hv-scatter").textContent = "· " + viewText();
  $("hv-table").textContent = "· " + viewText();
}
function renderPending() {
  var box = $("pending"), wk = W[st.w].key;
  box.textContent = "";
  function line(icon, bold, rest) {
    var d = el("div");
    d.appendChild(el("span", { class: icon }));
    if (bold) d.appendChild(el("b", null, bold));
    d.appendChild(document.createTextNode(rest));
    box.appendChild(d);
  }
  // in or out of sample, per study, in this view
  var by = {};
  viewRows().forEach(function (j) {
    var g = S.grp[M.s[j]];
    if (g !== "benchmarks" && M.smp[j]) (by[g] || (by[g] = {}))[M.smp[j]] = 1;
  });
  var parts = { out: [], "in": [], mixed: [] };
  GORDER.forEach(function (g) {
    if (!by[g]) return;
    var ks = Object.keys(by[g]);
    parts[ks.length === 1 ? ks[0] : "mixed"].push(gshort(g));
  });
  var txt = [];
  if (parts.out.length) txt.push("out-of-sample for " + parts.out.join(", "));
  if (parts["in"].length) txt.push("in-sample for " + parts["in"].join(", "));
  if (parts.mixed.length) txt.push("partly in-sample for " + parts.mixed.join(", "));
  if (txt.length) line("info", "This window is ", txt.join("; ") + " (the Sample column).");
  var groups = {}, order = [];
  D.pending.forEach(function (p) {
    if (p.w && p.w !== wk) return;
    var k = p.w + "|" + p.text;
    if (!groups[k]) { groups[k] = { w: p.w, text: p.text, src: [] }; order.push(k); }
    groups[k].src.push(SRC[p.src] ? SRC[p.src].study : p.src);
  });
  order.forEach(function (k) {
    var g = groups[k];
    line("clock", g.src.join(" and ") + (g.w ? " on " + g.w : ""), " (pending): " + g.text + ".");
  });
  if (W[st.w].common) D.missing.forEach(function (x) {
    if (x.sym !== st.sym || x.w.indexOf(wk) < 0 || x.later.indexOf(wk) >= 0) return;
    line("info", SRC[x.src] ? SRC[x.src].study : x.src, ": no rows on " + wk + " (the study did not run this window).");
  });
}
function fillSelect(id, label, values, current, nameOf) {
  var s = $(id);
  s.textContent = "";
  s.appendChild(el("option", { value: "" }, label + ": all"));
  values.forEach(function (v) {
    var o = el("option", { value: v }, label + ": " + (nameOf ? nameOf(v) : v));
    if (v === current) o.selected = true;
    s.appendChild(o);
  });
  if (current && values.indexOf(current) < 0) {
    var o = el("option", { value: current }, label + ": " + (nameOf ? nameOf(current) : current));
    o.selected = true; s.appendChild(o);
  }
}
function renderFilters() {
  var rows = viewRows(), seen = { grp: {}, kind: {}, fam: {}, tf: {}, role: {}, exam: {} };
  rows.forEach(function (j) {
    var i = M.s[j];
    seen.grp[S.grp[i]] = 1; seen.kind[S.kind[i]] = 1; if (S.fam[i]) seen.fam[S.fam[i]] = 1;
    if (S.tf[i]) seen.tf[S.tf[i]] = 1; seen.role[S.role[i]] = 1; seen.exam[S.exam[i] || "not examined"] = 1;
  });
  fillSelect("f-src", "Study", GORDER.filter(function (g) { return seen.grp[g]; }), st.f.grp, gname);
  fillSelect("f-kind", "Kind", Object.keys(seen.kind).sort(), st.f.kind);
  fillSelect("f-fam", "Family", Object.keys(seen.fam).sort(), st.f.fam);
  fillSelect("f-tf", "Timeframe", Object.keys(seen.tf).sort(), st.f.tf);
  fillSelect("f-role", "Role", ROLES.filter(function (r) { return seen.role[r]; }), st.f.role);
  fillSelect("f-exam", "Exam", Object.keys(seen.exam).sort(), st.f.exam);
  var shown = rows.filter(passes).length;
  $("fnote").textContent = shown + " of " + rows.length + " rows";
}

// ---------- the equity chart ----------
function chartLayout(nLines, labels) {
  var ink = cssv("--ink"), ink2 = cssv("--ink2"), grid = cssv("--grid"), axis = cssv("--axis"), surf = cssv("--surface");
  var few = nLines <= 4, narrow = $("chart").clientWidth < NARROW;
  var legend;
  if (few) legend = { orientation: "h", x: 0, y: 1.02, xanchor: "left", yanchor: "bottom", font: { size: 12, color: ink2 } };
  else if (narrow) legend = { orientation: "h", x: 0, y: -0.1, xanchor: "left", yanchor: "top", font: { size: 11.5, color: ink2 },
                              tracegroupgap: 4, groupclick: "toggleitem", grouptitlefont: { size: 12, color: ink } };
  else legend = { orientation: "v", x: 1.01, y: 1, xanchor: "left", yanchor: "top", font: { size: 11.5, color: ink2 },
                  tracegroupgap: 6, groupclick: "toggleitem", grouptitlefont: { size: 12, color: ink } };
  return {
    paper_bgcolor: surf, plot_bgcolor: surf, font: { family: FONT, size: 12, color: ink2 },
    margin: { l: 72, r: labels ? 160 : 16, t: few ? 34 : 10, b: 36 },
    hovermode: "x unified", hoverdistance: 30,
    hoverlabel: { bgcolor: surf, bordercolor: axis, font: { family: FONT, size: 12, color: ink } },
    xaxis: { type: "date", anchor: "y2", showgrid: false, linecolor: axis, ticks: "outside", tickcolor: axis,
             showspikes: true, spikemode: "across", spikesnap: "data", spikecolor: axis, spikethickness: 1,
             spikedash: "solid", hoverformat: "%a %d %b %Y", tickfont: { color: ink2 } },
    yaxis: { domain: [0.3, 1], type: st.log ? "log" : "linear", gridcolor: grid, gridwidth: 1, zeroline: false,
             linecolor: axis, tickformat: "$,.0f", automargin: true, tickfont: { color: ink2 },
             title: { text: "Equity of the $2,000 account", font: { size: 12, color: ink2 } } },
    yaxis2: { domain: [0, 0.23], gridcolor: grid, gridwidth: 1, zeroline: true, zerolinecolor: axis, linecolor: axis,
              ticksuffix: "%", automargin: true, tickfont: { color: ink2 }, rangemode: "nonpositive",
              title: { text: "Below the peak", font: { size: 12, color: ink2 } } },
    showlegend: true, legend: legend, annotations: []
  };
}
function drawnList(wk) {
  var sel = Array.from(st.sel[st.sym]);
  var drawn = sel.filter(function (i) { return hasCurve(i, wk); });
  drawn.sort(function (a, b) {
    return (GORDER.indexOf(S.grp[a]) - GORDER.indexOf(S.grp[b])) || (S.fin[b] - S.fin[a]) ||
           (rankKey(a) - rankKey(b)) || cmpStr(S.label[a], S.label[b]);
  });
  return { sel: sel, drawn: drawn };
}
// a drawn line's dash is its place among the drawn lines of its study (no repeat up to six); past six a marker is added
function lineStyles(drawn) {
  var out = {}, k = {};
  drawn.forEach(function (i) {
    if (S.role[i] === "benchmark") { out[i] = { dash: S.siz[i] === "fully invested" ? "solid" : "dot", sym: null }; return; }
    var g = S.grp[i], n = k[g] || 0;
    k[g] = n + 1;
    out[i] = { dash: DASH[n % 6], sym: n >= 6 ? MSYM[(Math.floor(n / 6) - 1) % MSYM.length] : null };
  });
  return out;
}
var STY = {};                    // the styles of the drawn lines (the table's keys show them)
function renderChart() {
  var wk = W[st.w].key, L = drawnList(wk), drawn = L.drawn;
  STY = lineStyles(drawn);
  var traces = [], surf = cssv("--surface"), titled = {}, few = drawn.length <= 4;
  drawn.forEach(function (i) {
    var c = curve(i, wk), col = scolor(i), g = S.grp[i], sty = STY[i];
    var d = drawdown(c.y), name = esc(shortText(S.label[i], 50));
    var t = { type: "scatter", mode: sty.sym ? "lines+markers" : "lines", x: c.x, y: c.y, name: name, legendgroup: g,
              customdata: d, uid: "e" + i, line: { color: col, width: 2, dash: sty.dash }, xaxis: "x", yaxis: "y",
              hovertemplate: "<b>%{y:$,.0f}</b>  (DD %{customdata:.1f}%)  %{fullData.name}<extra></extra>" };
    if (sty.sym) t.marker = { symbol: sty.sym, size: 8, maxdisplayed: 16, color: col, line: { color: surf, width: 2 } };
    if (!few && !titled[g]) { t.legendgrouptitle = { text: esc(gname(g)) }; titled[g] = 1; }
    traces.push(t);
    traces.push({ type: "scatter", mode: "lines", x: c.x, y: d, name: name, legendgroup: g, showlegend: false,
                  uid: "d" + i, line: { color: col, width: 1.5, dash: sty.dash }, xaxis: "x", yaxis: "y2",
                  hovertemplate: "<b>%{y:.1f}%</b> below the peak  %{fullData.name}<extra></extra>" });
  });
  var notes = [], labels = false;
  if (few && drawn.length) {
    var ys = drawn.map(function (i) { var c = curve(i, wk); return c.y[c.y.length - 1]; });
    var lo = Infinity, hi = -Infinity;
    drawn.forEach(function (i) { curve(i, wk).y.forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; }); });
    var f = function (v) { return st.log ? Math.log(Math.max(v, 1)) : v; };
    var span = (f(hi) - f(lo)) || 1, px = ys.map(function (v) { return (f(v) - f(lo)) / span * 400; }), ok = true;
    for (var a = 0; a < px.length; a++) for (var b = a + 1; b < px.length; b++) if (Math.abs(px[a] - px[b]) < 16) ok = false;
    if (ok) {
      labels = true;
      drawn.forEach(function (i, k) {
        var c = curve(i, wk);
        notes.push({ x: c.x[c.x.length - 1], y: st.log ? Math.log10(Math.max(ys[k], 1)) : ys[k], xref: "x", yref: "y",
                     text: esc(shortText(S.label[i], 22)), showarrow: false, xanchor: "left", xshift: 6,
                     font: { size: 12, color: cssv("--ink") } });
      });
    }
  }
  var lay = chartLayout(drawn.length, labels);
  lay.annotations = notes;
  var narrow = $("chart").clientWidth < NARROW, h = (narrow && !few) ? 640 + 21 * Math.ceil(drawn.length / 3) : 660;
  if ($("chart").style.height !== h + "px") $("chart").style.height = h + "px";
  Plotly.react("chart", traces, lay, CFG);
  var missing = L.sel.length - drawn.length, txt;
  if (!drawn.length) txt = "Nothing selected on this window: use the buttons, tick a table row, or click a point";
  else {
    txt = drawn.length + " series drawn";
    if (missing > 0) txt += "; " + missing + " selected series have no curve on this window (the study did not run it, or kept no curve)";
    var finals = drawn.map(function (i) { var c = curve(i, wk); return c.y[c.y.length - 1]; }).sort(function (a, b) { return a - b; });
    if (!st.log && finals.length > 2 && finals[finals.length - 1] > 5 * Math.max(finals[Math.floor(finals.length / 2)], 1))
      txt += ". One line ends far above the others: the log scale shows the rest better";
  }
  $("selnote").textContent = txt + ".";
}
function chartEvents() {
  var gd = $("chart");
  function si(t) { return t.uid ? t.uid.slice(1) : null; }
  gd.on("plotly_legendclick", function (ev) {
    var i = si(ev.data[ev.curveNumber]), now = ev.data[ev.curveNumber].visible;
    var nv = now === "legendonly" ? true : "legendonly", idx = [];
    ev.data.forEach(function (t, k) { if (si(t) === i) idx.push(k); });
    Plotly.restyle(gd, { visible: nv }, idx);
    return false;
  });
  gd.on("plotly_legenddoubleclick", function (ev) {
    var i = si(ev.data[ev.curveNumber]);
    var alone = ev.data.every(function (t) { return si(t) === i || t.visible === "legendonly"; });
    Plotly.restyle(gd, { visible: ev.data.map(function (t) { return alone || si(t) === i ? true : "legendonly"; }) });
    return false;
  });
}

// ---------- selection ----------
function setSel(s) { st.sel[st.sym] = s; renderChart(); renderTable(); }
function toggleSel(i, on) {
  var s = st.sel[st.sym];
  if (on) s.add(i); else s.delete(i);
  renderChart(); renderTable(i);
}
function addSel(i) {
  if (!hasCurve(i, W[st.w].key)) { toast("No curve on this window for " + S.label[i]); return; }
  st.sel[st.sym].add(i);
  renderChart(); renderTable();
  toast("Added " + S.label[i]);
}
function withBh(s) { for (var i = 0; i < NS; i++) if (S.sym[i] === st.sym && S.role[i] === "benchmark") s.add(i); return s; }
function quick(kind) {
  var s = new Set(), wk = W[st.w].key;
  if (kind === "bots") { for (var i = 0; i < NS; i++) if (S.sym[i] === st.sym && S.role[i] === "design") s.add(i); withBh(s); }
  if (kind === "fin") { for (var i2 = 0; i2 < NS; i2++) if (S.sym[i2] === st.sym && S.fin[i2]) s.add(i2); withBh(s); }
  if (kind === "top") {
    // the unit-rule $2,000 accounts of this window at x1.0 (what the chart draws), whatever the switches and filters
    var cand = [];
    for (var j2 = 0; j2 < NM; j2++) {
      var si = M.s[j2];
      if (M.w[j2] !== st.w || M.b[j2] !== 0 || M.c[j2] !== 1 || S.sym[si] !== st.sym) continue;
      if (S.role[si] === "benchmark" || S.siz[si] !== "unit rule" || M.rdd[j2] == null || !hasCurve(si, wk)) continue;
      cand.push(j2);
    }
    cand.sort(function (a, b) { return M.rdd[b] - M.rdd[a]; });
    cand.slice(0, 10).forEach(function (j3) { s.add(M.s[j3]); });
    withBh(s);
    if (!cand.length) toast("No unit-rule account with a curve on this window");
  }
  setSel(s);
}

// ---------- the scatter ----------
function scatterRanges(pts, xv, yv) {
  // one shared scale for every panel. A value whose gap above the next one is more than twice the whole range of the
  // values below it (up to three such values) is drawn on the top edge as a labelled triangle, so a single extreme
  // result cannot flatten every other point (e.g. BTC 8y: Turtle, 1% risk at $111,722 against $5,815 next)
  var x1 = 0, ys = [];
  pts.forEach(function (j) { var x = xv(j), y = yv(j); if (x > x1) x1 = x; ys.push(y); });
  ys.sort(function (a, b) { return b - a; });
  var lo = ys.length ? ys[ys.length - 1] : -1, k = 0;
  while (k < 3 && k + 1 < ys.length && ys[k] - ys[k + 1] > 2 * Math.max(ys[k + 1] - Math.min(lo, 0), 1e-9)) k++;
  var top = ys.length ? ys[k] : 1, cut = k > 0 ? top + (top - Math.min(lo, 0)) * 0.1 : Infinity;
  var hi = isFinite(cut) ? cut : top, pad = (hi - Math.min(lo, 0)) * 0.06 || 1;
  return { x: [0, x1 * 1.06 || 1], y: [Math.min(lo - pad, 0), Math.max(hi + pad, 0)], cut: cut };
}
function renderScatter() {
  var box = $("panels");
  Array.prototype.forEach.call(box.querySelectorAll(".pl"), function (p) { try { Plotly.purge(p); } catch (e) {} });
  box.textContent = "";
  var unit = st.b === 1, cg = st.y === "cagr" && !unit;
  var xv = function (j) { return unit ? M.ddu[j] : M.ddp[j]; };
  var yv = function (j) { return cg ? M.cagr[j] : M.net[j]; };
  var pts = viewRows().filter(function (j) { return passes(j) && xv(j) != null && yv(j) != null; });
  var bhPts = pts.filter(function (j) { return S.role[M.s[j]] === "benchmark"; });
  var groups = GORDER.filter(function (g) { return g !== "benchmarks" && pts.some(function (j) { return S.grp[M.s[j]] === g; }); });
  var pend = D.pending.filter(function (p) { return !p.w; });
  var R = scatterRanges(pts, xv, yv);
  var ink = cssv("--ink"), ink2 = cssv("--ink2"), grid = cssv("--grid"), axis = cssv("--axis"), surf = cssv("--surface"),
      ctx = cssv("--context");
  var xt = unit ? "Max drawdown per 0.01 lot ($)" : "Max drawdown (% below the peak, the study's own marks)";
  var yt = cg ? "CAGR (%)" : (unit ? "Net profit per 0.01 lot ($)" : "Net profit ($)");
  var yfmt = cg ? "%{customdata[1]:.1f}%" : (unit ? "%{customdata[1]:$,.2f}" : "%{customdata[1]:$,.0f}");
  var xfmt = unit ? "%{x:$,.0f}" : "%{x:.1f}%", tip = "<b>%{text}</b><br>" + yfmt + " · max DD " + xfmt + "<extra></extra>";
  var off = function (j) { return yv(j) > R.cut; };
  var wiped = function (j) { return !!M.wip[j]; };
  var capY = function (j) { return off(j) ? R.cut : yv(j); };
  var sym = function (j) { return off(j) ? "triangle-up" : (wiped(j) ? "x" : "circle"); };
  var cd = function (j) { return [M.s[j], yv(j)]; };
  function label(j) {
    var i = M.s[j];
    return esc(S.label[i]) + " · " + S.role[i] + (S.exam[i] ? " · exam " + S.exam[i] : "") +
           (M.smp[j] ? " · " + SAMPLE_TEXT[M.smp[j]] : "") + (S.siz[i] === "risk-sized" ? " · risk-sized" : "") +
           (wiped(j) ? " · wiped" : "");
  }
  groups.forEach(function (g) {
    var mine = pts.filter(function (j) { return S.grp[M.s[j]] === g; });
    var other = pts.filter(function (j) { var gg = S.grp[M.s[j]]; return gg !== g && gg !== "benchmarks"; });
    var nw = mine.filter(wiped).length, smp = {};
    mine.forEach(function (j) { if (M.smp[j]) smp[M.smp[j]] = 1; });
    var sk = Object.keys(smp);
    var p = el("div", { class: "panel", role: "group",
                        "aria-label": "Risk and return: " + gname(g) + ", " + mine.length + " series" + (nw ? ", " + nw + " wiped" : "") });
    var h = el("h3"), dot = el("span", { class: "dot" });
    dot.style.background = gcolor(g);
    h.appendChild(dot);
    h.appendChild(document.createTextNode(gname(g) + " (" + mine.length + (nw ? ", " + nw + " wiped" : "") + ")"));
    if (sk.length) h.appendChild(el("span", { class: "smp" }, sk.length === 1 ? SAMPLE_TEXT[sk[0]] : "partly in-sample"));
    p.appendChild(h);
    var pl = el("div", { class: "pl" });
    p.appendChild(pl); box.appendChild(p);
    var traces = [
      { type: "scatter", mode: "markers", x: other.map(xv), y: other.map(capY), hoverinfo: "skip", showlegend: false,
        marker: { size: 5, color: ctx, symbol: other.map(sym) } },
      { type: "scatter", mode: "markers", x: bhPts.map(xv), y: bhPts.map(capY), customdata: bhPts.map(cd),
        text: bhPts.map(label), showlegend: false, hovertemplate: tip,
        marker: { size: 10, symbol: bhPts.map(function (j) { return off(j) ? "triangle-up" : "diamond"; }), color: ink,
                  line: { color: surf, width: 2 } } },
      { type: "scatter", mode: "markers", x: mine.map(xv), y: mine.map(capY), customdata: mine.map(cd),
        text: mine.map(label), showlegend: false, hovertemplate: tip,
        marker: { size: mine.map(function (j) { return off(j) ? 11 : (wiped(j) ? 9 : 8); }), symbol: mine.map(sym),
                  color: gcolor(g), line: { color: surf, width: 2 } } }
    ];
    var lay = { paper_bgcolor: surf, plot_bgcolor: surf, font: { family: FONT, size: 11.5, color: ink2 },
                margin: { l: 62, r: 10, t: 6, b: 40 }, hovermode: "closest", hoverdistance: 24,
                hoverlabel: { bgcolor: surf, bordercolor: axis, font: { family: FONT, size: 12, color: ink } },
                xaxis: { range: R.x, gridcolor: grid, zeroline: false, linecolor: axis, ticksuffix: unit ? "" : "%",
                         tickformat: unit ? "$,.0f" : "", title: { text: xt, font: { size: 11.5, color: ink2 } } },
                yaxis: { range: R.y, gridcolor: grid, zeroline: true, zerolinecolor: axis, linecolor: axis,
                         ticksuffix: cg ? "%" : "", tickformat: cg ? ".0f" : "$,.0f",
                         title: { text: yt, font: { size: 11.5, color: ink2 } } },
                annotations: mine.concat(bhPts).filter(off).map(function (j, n) {
                  var v = yv(j), i = M.s[j];
                  var right = (xv(j) - R.x[0]) / ((R.x[1] - R.x[0]) || 1) > 0.55;
                  return { x: xv(j), y: R.cut, xref: "x", yref: "y", showarrow: false, xanchor: right ? "right" : "left",
                           xshift: right ? -9 : 9, yshift: -14 * n, font: { size: 11, color: ink2 },
                           text: esc(shortText(S.label[i], 28)) + ": " + (cg ? v.toFixed(1) + "%" : fmtUsd(v)) + ", off the scale" };
                }) };
    Plotly.react(pl, traces, lay, { displayModeBar: false, responsive: true });
    pl.on("plotly_click", function (ev) {
      var q = ev.points && ev.points[0];
      if (q && q.customdata != null && q.customdata[0] != null) addSel(q.customdata[0]);
    });
  });
  pend.forEach(function (pp) {
    var g = SRC[pp.src] ? SRC[pp.src].grp : "earlier";
    if (groups.indexOf(g) >= 0) return;
    var p = el("div", { class: "panel", role: "group", "aria-label": gname(g) + ": pending" }), h = el("h3"),
        dot = el("span", { class: "dot" });
    dot.style.background = (GI[g] && GI[g].slot != null) ? gcolor(g) : cssv("--ink2");
    h.appendChild(dot); h.appendChild(document.createTextNode(gname(g)));
    p.appendChild(h); p.appendChild(el("div", { class: "empty" }, "Pending: " + pp.text + "."));
    box.appendChild(p);
  });
  if (!groups.length && !pend.length) box.appendChild(el("p", { class: "note" }, "No series in this view."));
}

// ---------- the table ----------
var COLS = [
  [ { k: "label", t: "Series (tick to draw)" }, { k: "grp", t: "Study" }, { k: "role", t: "Role" },
    { k: "smp", t: "Sample" }, { k: "exam", t: "Exam" }, { k: "net", t: "Net profit", n: 1, f: fmtUsd },
    { k: "ret", t: "Return", n: 1, f: pct1 }, { k: "cagr", t: "CAGR", n: 1, f: pct1 },
    { k: "ddp", t: "Max DD %", n: 1, f: pct1 }, { k: "rdd", t: "Growth ÷ DD", n: 1, f: num2 },
    { k: "ddu", t: "Max DD $", n: 1, f: fmtUsd }, { k: "dly", t: "DD $, daily closes", n: 1, f: fmtUsd, der: 1 },
    { k: "tr", t: "Trades", n: 1, f: fmtInt }, { k: "win", t: "Win rate", n: 1, f: pct1 },
    { k: "pf", t: "Profit factor", n: 1, f: num2 }, { k: "sh", t: "Sharpe (wk)", n: 1, f: num2 },
    { k: "pq", t: "Quarters up", n: 1, f: pct0 }, { k: "wq", t: "Worst quarter", n: 1, f: fmtUsd },
    { k: "wm", t: "Worst month", n: 1, f: fmtUsd, der: 1 }, { k: "ud", t: "Under water (d)", n: 1, f: fmtInt, der: 1 },
    { k: "elig", t: "Eligible" }, { k: "sc", t: "FINAL10 score", n: 1, f: num2 }, { k: "mk", t: "DD marks" },
    { k: "dates", t: "Dates (end excl.)" } ],
  [ { k: "label", t: "Series (tick to draw)" }, { k: "grp", t: "Study" }, { k: "role", t: "Role" },
    { k: "smp", t: "Sample" }, { k: "exam", t: "Exam" }, { k: "net", t: "Net per 0.01 lot", n: 1, f: fmtUsd },
    { k: "ddu", t: "Max DD $", n: 1, f: fmtUsd }, { k: "pdd", t: "Profit / DD", n: 1, f: num2 },
    { k: "tr", t: "Trades", n: 1, f: fmtInt }, { k: "win", t: "Win rate", n: 1, f: pct1 },
    { k: "pf", t: "Profit factor", n: 1, f: num2 }, { k: "sh", t: "Sharpe (wk)", n: 1, f: num2 },
    { k: "pq", t: "Quarters up", n: 1, f: pct0 }, { k: "wq", t: "Worst quarter", n: 1, f: fmtUsd },
    { k: "elig", t: "Eligible" }, { k: "mk", t: "DD marks" }, { k: "dates", t: "Dates (end excl.)" } ]
];
var TIPS = {
  rdd: "growth per year (CAGR %) ÷ max DD %, both the study's own: FINAL10's 'best balance'",
  ddu: "max drawdown in $ on the same marks as Max DD % (empty where the study publishes the % only); per 0.01 lot on that basis",
  dly: "max drawdown in $ at daily closes, from the daily curve: the page's own figure, smaller than the study's own drawdown where the study marks finer",
  pdd: "net profit ÷ max DD $, per 0.01 lot",
  sc: "FINAL10's selection yardstick: mean profit per fresh $2,000 quarter (5 periods) ÷ worst fresh-quarter DD %; the same in every window. References were scored too but were not candidates (Eligible: no)",
  mk: "what Max DD % was measured on: tick, second, M1 bar or day",
  wm: "the worst calendar month in $, from the daily curve", ud: "the longest time below a previous high, in days, from the daily curve",
  sh: "weekly P/L, mean ÷ sd x sqrt(52), weeks from Saturday 00:00 UTC (study 1's definition; computed here from the daily curve where a study gives none, or another definition such as multisymbol's)",
  pq: "share of calendar quarters (partial ones included) that made money", wq: "the worst calendar quarter in $",
  ddp: "% below the running peak, on the study's own marks (the DD marks column)",
  smp: "out-of-sample: no choice of this row read the window; in-sample: the window helped choose it; partly: some of it did",
  elig: "the study's own eligibility rule (FINAL10's selection rule, study 1's qualification); empty where a study has none",
  exam: "the study's exam on its hold-out (study 1: net > 0 and profit / DD >= 0.5 at x1.0)", tr: "trades (the ladder: baskets)"
};
function cols() { return COLS[st.b]; }
function sortVal(j, k) {
  var i = M.s[j];
  if (k === "label") return S.label[i].toLowerCase();
  if (k === "grp") return GORDER.indexOf(S.grp[i]);
  if (k === "role") return ROLES.indexOf(S.role[i]);
  if (k === "exam") return S.exam[i] || "";
  if (k === "smp") return M.smp[j] || "";
  if (k === "elig") return (SRC[S.src[i]] && SRC[S.src[i]].elig) ? S.elig[i] : null;
  if (k === "mk") return M.mk[j];
  if (k === "dates") return M.a[j] + M.z[j];
  return M[k][j];
}
function keySvg(i) {
  var sty = STY[i], col = scolor(i), ns = "http://www.w3.org/2000/svg";
  var svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "key"); svg.setAttribute("width", "26"); svg.setAttribute("height", "10");
  svg.setAttribute("aria-hidden", "true");
  var ln = document.createElementNS(ns, "line");
  ln.setAttribute("x1", "1"); ln.setAttribute("y1", "5"); ln.setAttribute("x2", "25"); ln.setAttribute("y2", "5");
  ln.setAttribute("stroke", col); ln.setAttribute("stroke-width", "2.5");
  if (DASH_SVG[sty.dash]) ln.setAttribute("stroke-dasharray", DASH_SVG[sty.dash]);
  svg.appendChild(ln);
  if (sty.sym) {
    var c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", "13"); c.setAttribute("cy", "5"); c.setAttribute("r", "3.2"); c.setAttribute("fill", col);
    svg.appendChild(c);
  }
  return svg;
}
function renderTable(focusSi) {
  var C = cols();
  if (!C.some(function (c) { return c.k === st.sort.k; })) st.sort = { k: st.b ? "pdd" : "rdd", dir: -1 };
  var rows = viewRows().filter(passes), k = st.sort.k, dir = st.sort.dir;
  rows.sort(function (a, b) {
    var x = sortVal(a, k), y = sortVal(b, k);
    var xn = x == null || x === "", yn = y == null || y === "";
    if (xn && yn) return 0; if (xn) return 1; if (yn) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * dir;
  });
  var thead = document.querySelector("#tbl thead"), tbody = document.querySelector("#tbl tbody");
  thead.textContent = ""; tbody.textContent = "";
  var tr = el("tr");
  C.forEach(function (c) {
    var th = el("th", { scope: "col" });
    if (c.n) th.className = "n";
    if (c.k === "label") th.className = "lab";
    var b = el("button", { type: "button", class: "thb" });
    if (c.der) b.appendChild(el("span", { class: "der" }, c.t)); else b.textContent = c.t;
    if (TIPS[c.k]) b.title = TIPS[c.k];
    if (c.k === st.sort.k) th.setAttribute("aria-sort", st.sort.dir > 0 ? "ascending" : "descending");
    b.addEventListener("click", function () {
      if (st.sort.k === c.k) st.sort.dir = -st.sort.dir; else { st.sort.k = c.k; st.sort.dir = c.n ? -1 : 1; }
      st.page = 0; renderTable();
      var nb = document.querySelector("#tbl thead th[aria-sort] .thb"); if (nb) nb.focus();
    });
    th.appendChild(b);
    tr.appendChild(th);
  });
  thead.appendChild(tr);
  var n = rows.length, pages = Math.max(1, Math.ceil(n / st.per));
  if (st.page >= pages) st.page = pages - 1;
  var part = rows.slice(st.page * st.per, (st.page + 1) * st.per), wk = W[st.w].key, sel = st.sel[st.sym];
  var frag = document.createDocumentFragment(), focusEl = null;
  part.forEach(function (j) {
    var i = M.s[j], row = el("tr"), dset = {};
    (M.der[j] ? M.der[j].split(",") : []).forEach(function (d) { if (DER[d]) dset[DER[d]] = 1; });
    if (sel.has(i)) row.className = "on";
    C.forEach(function (c) {
      var td = el("td");
      if (c.k === "label") {
        td.className = "lab";
        var lab = el("label"), cb = el("input", { type: "checkbox", "aria-label": "Draw " + S.label[i] });
        cb.checked = sel.has(i);
        cb.setAttribute("data-si", String(i));
        if (!hasCurve(i, wk)) { cb.disabled = true; cb.title = "no curve on this window"; }
        cb.addEventListener("change", function () { toggleSel(i, cb.checked); });
        if (focusSi === i) focusEl = cb;
        lab.appendChild(cb);
        var box = el("span");
        if (STY[i] && sel.has(i) && hasCurve(i, wk)) box.appendChild(keySvg(i));
        box.appendChild(el("span", { class: "nm" }, S.label[i]));
        var meta = el("div", { class: "meta" }, [S.kind[i], S.fam[i], S.tf[i], S.filt[i]].filter(function (x) { return x; }).join(" · "));
        var badges = [];
        if (S.siz[i] === "risk-sized") badges.push("risk-sized");
        (S.tags[i] ? S.tags[i].split(";") : []).forEach(function (t) { if (t) badges.push(t); });
        if (M.wip[j]) badges.push("wiped");
        badges.forEach(function (t) { meta.appendChild(document.createTextNode(" ")); meta.appendChild(el("span", { class: "badge" }, t)); });
        box.appendChild(meta);
        lab.appendChild(box);
        td.appendChild(lab);
        var dt = el("details", { class: "nt" });
        dt.appendChild(el("summary", null, "Notes"));
        if (S.notes[i]) dt.appendChild(el("div", null, S.notes[i]));
        if (M.rn[j]) dt.appendChild(el("div", null, "This row: " + M.rn[j]));
        dt.appendChild(el("div", null, "Numbers from " + D.files[M.f[j]] + " · id " + S.id[i]));
        td.appendChild(dt);
      } else if (c.k === "grp") {
        var d = el("span", { class: "dot" }); d.style.background = scolor(i);
        td.appendChild(d);
        td.appendChild(document.createTextNode(" " + (SRC[S.src[i]] ? SRC[S.src[i]].short : S.src[i]) + (S.grp[i] === "bots" ? " (bots)" : "")));
        if (M.via[j]) td.appendChild(el("div", { class: "dim" }, "via " + M.via[j]));
      } else if (c.k === "role") { td.textContent = S.role[i]; }
      else if (c.k === "smp") { td.textContent = SAMPLE_TEXT[M.smp[j]] || ""; if (M.smp[j]) td.title = SAMPLE_TIP[S.grp[i]] || ""; }
      else if (c.k === "exam") { if (S.exam[i]) { td.textContent = S.exam[i]; td.className = S.exam[i] === "pass" ? "pass" : "fail"; } }
      else if (c.k === "elig") { if (SRC[S.src[i]] && SRC[S.src[i]].elig) td.textContent = S.elig[i] ? "yes" : "no"; }
      else if (c.k === "mk") { td.textContent = M.mk[j]; td.className = "dim"; }
      else if (c.k === "dates") { td.textContent = M.a[j] + " → " + M.z[j]; td.className = "dim"; }
      else {
        var v = M[c.k][j], txt = c.f(v);
        td.className = "n";
        if (txt && (dset[c.k] || c.der)) {
          var sp = el("span", { class: "der" }, txt);
          sp.title = DER_HOW[c.k] && !c.der ? DER_HOW[c.k] : "computed here from the daily curve";
          td.appendChild(sp);
        } else td.textContent = txt;
        if (c.k === "net" && M.wip[j]) { td.appendChild(document.createTextNode(" (wiped)")); }
      }
      row.appendChild(td);
    });
    frag.appendChild(row);
  });
  tbody.appendChild(frag);
  if (!n) { var r0 = el("tr"), td0 = el("td", { colspan: String(C.length) }, "No rows on this basis and cost in this window."); r0.appendChild(td0); tbody.appendChild(r0); }
  if (focusEl) focusEl.focus();
  var pg = $("pager"); pg.textContent = "";
  var prev = el("button", { class: "btn", type: "button" }, "← Prev"), next = el("button", { class: "btn", type: "button" }, "Next →");
  prev.disabled = st.page === 0; next.disabled = st.page >= pages - 1;
  prev.onclick = function () { st.page--; renderTable(); }; next.onclick = function () { st.page++; renderTable(); };
  var all = el("button", { class: "btn", type: "button" }, st.per > 100000 ? "100 per page" : "Show all");
  all.onclick = function () { st.per = st.per > 100000 ? 100 : 1e9; st.page = 0; renderTable(); };
  pg.appendChild(prev);
  pg.appendChild(el("span", null, n ? ("Rows " + (st.page * st.per + 1) + "–" + Math.min(n, (st.page + 1) * st.per) + " of " + n) : "0 rows"));
  pg.appendChild(next); pg.appendChild(all);
}

// ---------- theme, wiring ----------
function applyTheme() {
  if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
  $("themebtn").textContent = "Theme: " + theme;
}
function renderAll() {
  var msg = fixView();
  renderControls(); renderPending(); renderFilters(); renderChart(); renderScatter(); renderTable(); writeUrl();
  if (msg) toast(msg);
}
function stickTop() { $("filters").style.top = Math.round($("mainbar").getBoundingClientRect().height) + "px"; }
function wire() {
  $("themebtn").addEventListener("click", function () { theme = themes[(themes.indexOf(theme) + 1) % 3]; applyTheme(); renderAll(); });
  if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { if (theme === "auto") renderAll(); });
  $("q-bots").onclick = function () { quick("bots"); };
  $("q-fin").onclick = function () { quick("fin"); };
  $("q-top").onclick = function () { quick("top"); };
  $("q-clear").onclick = function () { setSel(new Set()); };
  $("logbtn").onclick = function () { st.log = !st.log; renderControls(); renderChart(); writeUrl(); };
  var q = $("q"), tmr = null;
  q.addEventListener("input", function () { clearTimeout(tmr); tmr = setTimeout(function () { st.q = q.value.trim().toLowerCase(); st.page = 0; renderFilters(); renderScatter(); renderTable(); }, 180); });
  [["f-src", "grp"], ["f-kind", "kind"], ["f-fam", "fam"], ["f-tf", "tf"], ["f-role", "role"], ["f-exam", "exam"]].forEach(function (p) {
    $(p[0]).addEventListener("change", function (e) { st.f[p[1]] = e.target.value; st.page = 0; renderFilters(); renderScatter(); renderTable(); });
  });
  $("f-reset").onclick = function () { st.f = { grp: "", kind: "", fam: "", tf: "", role: "", exam: "" }; st.q = ""; q.value = ""; st.page = 0; renderAll(); };
  window.addEventListener("hashchange", function () { readUrl(); applyTheme(); renderAll(); });
  if (window.ResizeObserver) new ResizeObserver(stickTop).observe($("mainbar"));
  stickTop();
  var lastNarrow = $("chart").clientWidth < NARROW, rt = null;
  window.addEventListener("resize", function () {
    clearTimeout(rt);
    rt = setTimeout(function () { var nw = $("chart").clientWidth < NARROW; if (nw !== lastNarrow) { lastNarrow = nw; renderChart(); } }, 200);
  });
  $("built").textContent = "Built " + D.built + " from the contract files in backtest_results/compare/data/ (" + NS +
    " series, " + NM + " rows). Gold is XAUUSDm and BTC is BTCUSDm at Exness; every figure is after the broker's spread.";
  var f = $("foot");
  f.textContent = "Sources: " + D.sources.map(function (s) { return s.study + (s.present ? "" : " (pending)"); }).join("; ") +
    ". Curves of the featured series are daily; the others every " + D.res.weekly_step + " days. Source files: " + D.files.join(", ") + ".";
}
readUrl(); applyTheme(); wire();
Plotly.newPlot("chart", [], chartLayout(0, false), CFG).then(function () { chartEvents(); renderAll(); });
})();
'''


LEFT_OUT = (
    ("Balke's own sizings (\"his sizing\", $2,000 and $10,000) and his US30m / USTECm rows",
     "another account model or another symbol; only his gold / BTC rows on the bot's unit rule are FINAL10's account"),
    ("sizing (STEP values other than $2,500, caps)",
     "another sizing; at STEP $2,500 with the cap it is FINAL10's 24 accounts to the cent (duplicates)"),
    ("ladder: the Z1 / Z2 / Z3-sized designs (G1-G3, G5, B1-B5) and V3 / V3L",
     "Z sizings are not the unit rule; V3 and V3L are FINAL10's V3-lite and gold Top 1 to the cent"),
    ("multisymbol: silver, the FX pairs, accounts b and the stream, and its 8y Turtles",
     "other symbols or sizings; its 8y Turtles are FINAL10's to the cent. Its gold / BTC (a) rows are shown as the "
     "bots' designs on its sel / conf / tsel windows"),
    ("improve, candidates, levers, packages, sweeps, robustness, baseline, long",
     "superseded by FINAL10 (and the ladder study for the live logic): per-quarter or 3-month windows of the old "
     "live ladder, metrics only"),
    ("optimise, live_safety, silver, signal, data_quality, parity, demo_parity",
     "per-lot monthly search results, a shared $1,500 two-bot account, another symbol, or no P/L at all"),
    ("study 1's x1.5 accounts and its dev / val / devval accounts", "study 1 kept $2,000 accounts only at x1.0 on "
     "the full span and the hold-out; its other windows are per 0.01 lot (shown on that basis)"),
)


def dd_gap(blob: Dict[str, object]) -> Dict[str, object]:
    """How much shallower the drawdown at daily closes is than each study's own (finer-marked) max DD %, over the
    account rows with a curve: the median and the largest shortfall, and gold V3-lite over 5y as the example."""
    raw = blob.get("_raw") or {}
    curves = raw.get("curves") or {}
    worder = raw.get("worder") or [w["key"] for w in blob["windows"]]
    S, M = blob["S"], blob["M"]
    gaps, example = [], None
    for j in range(len(M["s"])):
        si, w = M["s"][j], worder[M["w"][j]]
        if M["b"][j] != 0 or M["c"][j] != 1.0 or M["mk"][j] == "day" or not M["ddp"][j] or M["wip"][j]:
            continue
        cv = curves.get((si, w))
        if cv is None or not len(cv):
            continue
        e = cv.equity_usd.to_numpy(np.float64)
        peak = np.maximum.accumulate(e)
        daily = float(np.max((peak - e) / peak) * 100.0)
        gaps.append(1.0 - daily / float(M["ddp"][j]))
        if S["id"][si] == "final10:XAUUSDm|V3-lite" and w == "5y":
            example = (daily, float(M["ddp"][j]))
    if not gaps:
        return {}
    g = np.asarray(gaps)
    return dict(n=int(len(g)), median=float(np.median(g) * 100.0), worst=float(np.max(g) * 100.0), example=example)


def notes_html(blob: Dict[str, object]) -> str:
    """The definitions under the page (static text plus the sources and the pending items of this build)."""
    e = html.escape
    gap = dd_gap(blob)
    gap_text = ""
    if gap:
        gap_text = (f" Over the {gap['n']:,} account rows with a curve, the drawdown at daily closes is a median "
                    f"{gap['median']:.0f}% shallower than the study's own max DD %, and up to {gap['worst']:.0f}% "
                    "shallower")
        if gap.get("example"):
            d, o = gap["example"]
            gap_text += f" (gold V3-lite over 5 years: {d:.1f}% at daily closes against its own {o:.1f}%)"
        gap_text += "."
    out = ["<h3>The two buy-and-hold lines</h3><ul>",
           "<li><b>Buy and hold, $2,000 fully invested (no leverage)</b>, the main benchmark: the $2,000 buys 2,000 / "
           "ask of the asset at the window's first M1 open (a fraction of a lot: about 1 oz of gold in 2021, 0.03 BTC), "
           "holds it, and sells it at the bid at the window's last M1 close. Nothing else is traded, so it can never be "
           "wiped. Marked at every M1 bar: its max DD uses each bar's low. It is computed on every window that starts "
           "in 2019 or later, over exactly that window's span.</li>",
           "<li><b>Buy and hold 0.01 lot</b> (study 1's reference, DEVIATIONS 6 and 35): 0.01 lot bought and sold the "
           "same way. On the $2,000 account the unit rule gives 1 unit at $2,000, fixed at the open, so it holds 0.01 "
           "lot throughout and never compounds; per 0.01 lot it is study 1's buy-and-hold row.</li></ul>",
           "<h3>How each figure is measured</h3><ul>",
           "<li><b>Net profit, final equity, max DD %, trades, win rate, profit factor</b> are each study's own numbers, "
           "from its own files (multisymbol publishes no profit factor: it is computed here from its trade files, and "
           "dotted). Max DD % is measured on the study's own marks (the DD marks column): every second or raw tick on "
           "the tick engine, every M1 bar's worst price on the bar engines, daily marks for study 1's rebuilds of the "
           "bots' accounts.</li>",
           "<li><b>Max DD $ is on the same marks as Max DD %</b>, or empty: the studies' own $ figure (multisymbol, "
           "study 1 per 0.01 lot, buy-and-hold); study 1's 5y and 1y accounts, computed here on their M1 marks with "
           "study 1's own account kernel; study 1's daily-marked rebuilds of the bots' accounts. FINAL10, Balke, the "
           "ladder and study 1's own account rows publish their drawdown in % only, so it is empty there.</li>",
           "<li><b>DD $, daily closes</b> is the page's own figure, for every account with a curve: the largest fall of "
           "the daily curve below its running peak. Daily closes miss the intraday lows." + e(gap_text) + "</li>",
           "<li><b>Growth ÷ DD</b> is CAGR % ÷ max DD %, both the study's own (FINAL10's \"growth per year ÷ "
           "drawdown\"). It ranks the account basis: the table's default order and the Top 10 button (unit-rule "
           "accounts only). Per 0.01 lot the table ranks by <b>profit / DD</b>, net ÷ max DD $, both per lot.</li>",
           "<li><b>FINAL10's 1y tick rows</b> give the median of 8 loop timings for the final equity and the max DD; "
           "their other columns, their curve and its daily-close DD are the middle (upper-median) timing run, so the "
           "line ends a little away from the median.</li>",
           "<li><b>Computed here, uniformly from the daily curve, where a study does not give it (dotted):</b> CAGR and "
           "return (from the final equity), the weekly Sharpe (weekly P/L in $, weeks from Saturday 00:00 UTC, mean / "
           "sd x sqrt(52), study 1's definition), the share of calendar quarters that made money and the worst quarter "
           "(partial quarters included), the worst calendar month and the longest time under water. Multisymbol "
           "publishes its own quarters (3-month blocks from its window start) and Sharpe (x sqrt(52.18)): the columns "
           "show the uniform ones, its own are in the row's notes.</li>",
           "<li><b>Study 1 on 5y and 1y</b> was computed here with study 1's own code on M1 bars from 2019-01-01 (no "
           "bar before it is loaded): every rule's state from Oct 2021 on is identical to a run warmed up from mid-2019, "
           "and all 750 variants re-run over its validation window and hold-out equal its published results exactly "
           "(data/tradeiq_rsi__checks.csv, which also records that the $ drawdown kernel gives study 1's account "
           "drawdown and final equity on every run).</li>",
           "<li><b>In or out of sample</b> (the Sample column): out-of-sample means no choice of that row read the "
           "window. FINAL10 chose with data from 2021 on, so only its new window is out-of-sample for its rows, and the "
           "bots' designs are in-sample on every later window, whichever study ran them (study 1's rebuilds, "
           "multisymbol). Study 1 chose on 2019 - Jun 2024: its hold-out and the 1y inside it are out-of-sample.</li>",
           "<li><b>Curves</b> hold the account's equity at the end of each UTC day. FINAL10 and Balke publish the "
           "equity at each day's first mark; here day D carries the next day's opening mark (for gold a Friday "
           "carries Sunday evening's, the weekend gap included).</li></ul>",
           "<h3>The sources in this build</h3><ul>"]
    for s in blob["sources"]:
        state = "present" if s["present"] else "pending"
        out.append(f"<li><b>{e(str(s['study']))}</b> (<code>{e(s['src'])}</code>): {state}.</li>")
    out.append("</ul>")
    if blob["pending"]:
        out.append("<h3>Pending</h3><ul>")
        for p in blob["pending"]:
            w = f" on {e(p['w'])}" if p["w"] else ""
            out.append(f"<li><code>{e(p['src'])}</code>{w}: {e(p['text'])}.</li>")
        out.append("</ul>")
    res = blob.get("res", {})
    out.append("<h3>What the page embeds</h3><ul><li>Daily curves for the featured series (the bots' designs, every "
               "finalist, champion and baseline, buy-and-hold, and every series of FINAL10 and Balke); the other "
               f"series' curves every {int(res.get('weekly_step', 7))} days, to keep the page under 12 MB. The ladder "
               "study wrote no curves: its rows are in the table and the scatter only.</li>")
    if res.get("dropped"):
        where = "the studies' own windows" if res.get("drop") == "own" else "every window"
        out.append(f"<li>To stay under 12 MB, {int(res['dropped'])} curves of non-featured series on {where} are not "
                   "embedded: their numbers are in the table and the scatter, their curves in "
                   "<code>backtest_results/compare/data/</code>.</li>")
    out.append("</ul>")
    out.append("<h3>Left out, and why</h3><ul>")
    for what, why in LEFT_OUT:
        out.append(f"<li><b>{e(what)}</b>: {e(why)}.</li>")
    out.append("</ul><p class='note'>The definitions in full, the contract and the commands are in "
               "<code>backtest_results/compare/README.md</code>.</p>")
    return "\n".join(out)


# ───────────────────────────── command line ─────────────────────────────

def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python3 -B -m backtesting.research.compare_page")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export", help="contract files from the studies' result files")
    c = sub.add_parser("compute", help="study 1 and buy-and-hold on common windows (M1 bars from 2019 unless allowed)")
    c.add_argument("--windows", default="5y,1y")
    c.add_argument("--symbols", default=",".join(SYMBOLS))
    c.add_argument("--allow-pre-2019", action="store_true",
                   help="the later 8y / new run, once study 2's exam is written (loads study 1's full history)")
    c.add_argument("--no-checks", action="store_true")
    sub.add_parser("check", help="validate the contract files")
    sub.add_parser("build", help="write backtest_results/compare/index.html")
    sub.add_parser("all", help="export, compute, check, build")
    for p in sub.choices.values():
        p.add_argument("--data", default=str(DATA))
    a = ap.parse_args(argv)
    data = Path(a.data)
    if a.cmd in ("export", "all"):
        export(data)
    if a.cmd == "compute":
        compute([x for x in a.symbols.split(",") if x], [x for x in a.windows.split(",") if x],
                allow_pre_2019=a.allow_pre_2019, data=data, checks=not a.no_checks)
    if a.cmd == "all":
        compute(data=data)
    if a.cmd in ("check", "all"):
        rep = validate(data)
        print(f"{len(rep['errors'])} errors, {len(rep['warnings'])} warnings")
        for x in rep["errors"]:
            print("  ERROR", x)
        for x in rep["warnings"]:
            print("  warning", x)
        if rep["errors"]:
            raise SystemExit(1)
    if a.cmd in ("build", "all"):
        build(data, PAGE if Path(data) == DATA else Path(data).parent / "index.html")


if __name__ == "__main__":
    main()
