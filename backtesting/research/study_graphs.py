"""
PNG graphs of one source of the comparison page, drawn from its contract files (``backtest_results/compare/data/``).

    python3 -B -m backtesting.research.study_graphs --source SID --out DIR [--data DATA] [--windows w1,w2]
                                                    [--symbols XAUUSDm,BTCUSDm] [--top N] [--equity-top N]

Every study ships PNG graphs (study 2's PREREG 9, study 3's PREREG 8). This module draws them from the files the
comparison page reads (compare_page's contract v2: ``<sid>__series.csv``, ``<sid>__metrics.csv`` and
``<sid>__curves_<window>.csv.gz``, the daily equity of $2,000 accounts at x1.0; README.md in the data folder's parent
defines every field). So it works for any source: today's (``final10``, ``tradeiq_rsi``, ``balke``...) and studies 2
and 3 (``tradeiq_2027``, ``bot_filters``) once their files are in the data folder.

For each symbol and each window the source has curves for, into ``--out``:
  equity_<symbol>_<window>.png       the first ``--equity-top`` (4) featured series against the source's bases (when it
                                     has at most two on the window), the bots' published designs (FINAL10's role
                                     ``design`` on the window; on study 1's full and hold-out, study 1's rebuilds of
                                     them, ``compare_page.REBUILD_WINDOW``) and buy-and-hold (``benchmarks``): the
                                     equity of the $2,000 account in USD, on a linear axis unless the range exceeds 20x
                                     (then log; the axis label says which), the final equity printed at the end of at
                                     most four lines, and a legend that gives every line's final equity.
  drawdown_<symbol>_<window>.png     every featured series (``--top``, 6), those bases, the designs and buy-and-hold:
                                     the fall below the running peak in %, one small panel each on shared scales, from
                                     the daily curves. This is the drawdown at daily closes: it is usually shallower
                                     than the metrics' max DD, which a study measures on finer marks (each panel
                                     heading gives both, and says why where it is deeper).
  risk_return_<symbol>_<window>.png  CAGR % against max DD % for every account row of the source at x1.0 on the window:
                                     the featured rows numbered (named when at most six points carry a label), the
                                     base rows lettered on rings, the bots' designs and buy-and-hold named, and the line
                                     where growth / DD = 1.
  families_<symbol>_<window>.png     per family (series.csv ``family``), a bar: when the source has champions, the
                                     growth / DD of the family's pre-registered pick (its finalist, else its champion),
                                     with a tick at the family's best row on the window (picked in hindsight);
                                     otherwise the family's best row, which the graph says is picked in hindsight.
                                     Hollow where the bar's row is not eligible under the study's own rule; the bots'
                                     best design, the source's best base and buy-and-hold are reference lines.
Next to each PNG, ``<name>.csv``: the values it plots, its table view (VALUES_COLS). And ``graphs.csv``: one row per
PNG (file, graph, symbol, window, series_ids, source_files, notes, values_file). ``draw`` returns the same rows. A graph
whose inputs are missing is skipped and the log says why. When ``--top`` cuts featured series, the log and the graph's
note say which ones.

**The featured series.** The rows with role ``finalist`` or ``champion``: finalists first (in study 2 the finalists are
the champions chosen for the exam), then champions, each in the page's ranking order. A source without either role
falls back to its best N by the page's ranking, which is the page's "Top 10" rule: growth / DD = cagr_pct /
max_dd_pct on account rows at x1.0, unit-rule sizing, no benchmark, with a curve on the window. A blank CAGR is
computed from the curve's last equity, as the page does (``compare_page.curve_stats``). ``--top`` (default 6) caps the
featured list in both cases; the equity graph draws the first ``--equity-top`` of them (more lines of one colour do
not read), the others are named in its note.

**Colours and line keys** are the page's (the dataviz skill's palette, ``compare_page.PALETTE['light']``). Slots go to
the colour groups the way ``compare_page.build_blob`` does over the sources in the same data folder (``group_slots``),
so a source has the same colour here as on the page built from that folder. The bots' designs keep their slot,
buy-and-hold is the ink colour, and within a group lines differ by dash (past six, a marker), as on the page. A
featured series keeps its dash, and its number in the scatter, on every window (the order in which the series
first appear over all the source's windows with curves, in the page's order, whichever windows are drawn); the bases
are lettered after them. Text is always ink.

**Determinism.** Fixed figure sizes, 150 DPI, the font bundled with matplotlib (DejaVu Sans) and every list sorted.
The PNGs carry no metadata (no Software key, no time), so the same data gives the same bytes.

THE HARD RULES (the workflow's): this module reads only the contract files in the data folder. It never imports a
``tradeiq2_*`` or ``bot_filters`` module and never runs a backtest. It never opens
``backtest_results/bot_filters/dev_*.csv`` or ``daily*.csv``, and it writes only into ``--out``.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import dates as mdates
from matplotlib import patheffects
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath
from matplotlib.ticker import FuncFormatter, LogLocator, MaxNLocator, NullLocator

from . import compare_page as CP

DATA = CP.DATA
SYMBOLS = CP.SYMBOLS
ACCOUNT = CP.ACCOUNT
TOP = 6                               # --top: featured series per graph
EQUITY_TOP = 4                        # --equity-top: featured lines in the equity graph (the skill: ~4 lines)
END_LABELS = 4                        # line ends printed with their final equity (the skill: <= 4 direct labels)
END_GAP = 6.0                         # px: an end this close to a printed one is not printed again
MAX_BASE_LINES = 2                    # a source's bases are drawn as lines only when it has at most this many
DIRECT_NAMES = 6                      # scatter: past this many labelled points, featured get numbers, bases letters
LOG_RATIO = 20.0                      # the equity axis turns log when max / min exceeds this
MAX_FAMILIES = 30                     # bars a families graph can hold legibly (more are cut, and the log says so)
CHUNK = 400_000                       # curve rows read at a time
DPI = 150
PX = 72.0 / DPI                       # points per pixel
LINE = 2 * PX                         # 2 px lines
HAIR = 1 * PX                         # hairlines: grid, axis, reference and leader lines
HALO = 2.6                            # pt: the surface halo of labels on a plot
HALO_PX = HALO / PX / 2.0             # px the halo reaches beyond the glyphs
LABEL_PAD = HALO_PX + 2.0             # px kept free around a label on a plot
DOT_ROW, DOT_KEY, DOT_BH = 8.0, 12.0, 11.0   # marker sizes, px: context dots; featured, bases, designs; buy-and-hold
MARK_R = DOT_KEY / 2.0 + 1.5          # px: half the footprint of a 12 px mark with its 2 px surface ring
FONT = "DejaVu Sans"                  # bundled with matplotlib: the same glyphs (so bytes) on every machine
META = {"Software": None}             # no metadata in the PNG
SIZES = {"equity": (11.0, 7.4), "drawdown": (11.0, 8.0), "risk_return": (11.0, 7.4), "families": (11.0, 7.0)}
GRAPHS = ("equity", "drawdown", "risk_return", "families")
GRAPHS_COLS = ["file", "graph", "symbol", "window", "series_ids", "source_files", "notes", "values_file"]
# the table view written next to each PNG: one row per plotted item (line, panel, point, bar, tick or reference)
VALUES_COLS = ["item", "series_id", "label", "group", "role", "family", "key", "final_usd", "curve_last_usd",
               "cagr_pct", "max_dd_pct", "dd_marks", "growth_dd", "daily_close_dd_pct", "x", "y", "notes"]

# the page's light tokens (compare_page.PAGE_CSS; tests/test_study_graphs.py checks they agree)
SURFACE, INK, INK2, GRID, AXIS = "#ffffff", "#191919", "#666666", "#e7e7e7", "#c2c2c2"
PALETTE = list(CP.PALETTE["light"])
# the page's six dashes (solid, dash, dot, dashdot, longdash, longdashdot), in points at 150 DPI with round caps
DASHES = [None, (0, (4.2, 3.4)), (0, (0.1, 2.6)), (0, (4.2, 2.8, 0.1, 2.8)), (0, (8.4, 3.4)),
          (0, (8.4, 2.8, 0.1, 2.8))]
DASH_NAMES = ["solid", "dashed", "dotted", "dash-dot", "long dash", "long dash-dot"]
MARKERS = ["o", "s", "D", "^", "x", "*"]
FEATURED_ROLES = ("finalist", "champion")
ROLE_PLURAL = {"finalist": "finalists", "champion": "champions"}
UNIT_RULE = ("", "unit rule")
BH_ORDER = {"fully invested": 0, "0.01 lot fixed": 1}
BH_SHORT = {"fully invested": "Buy and hold, $2,000 fully invested", "0.01 lot fixed": "Buy and hold 0.01 lot"}

RC = {
    "font.family": "sans-serif", "font.sans-serif": [FONT], "font.size": 9.5, "text.color": INK,
    "text.parse_math": False,                 # "$2,000 ... $5,429" is text, never mathtext
    "axes.facecolor": SURFACE, "axes.edgecolor": AXIS, "axes.linewidth": HAIR, "axes.labelcolor": INK2,
    "axes.labelsize": 9.0, "axes.titlecolor": INK, "axes.unicode_minus": True, "axes.axisbelow": True,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "savefig.edgecolor": SURFACE, "figure.dpi": DPI,
    "savefig.dpi": DPI, "xtick.color": AXIS, "ytick.color": AXIS, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "xtick.labelsize": 9.0, "ytick.labelsize": 9.0, "xtick.major.width": HAIR, "ytick.major.width": HAIR,
    "xtick.major.size": 3.0, "ytick.major.size": 0.0, "xtick.minor.size": 0.0, "ytick.minor.size": 0.0,
    "xtick.major.pad": 4.0, "ytick.major.pad": 5.0,
    "grid.color": GRID, "grid.linewidth": HAIR, "grid.linestyle": "-",
    "lines.linewidth": LINE, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
    "lines.dash_capstyle": "round", "lines.dash_joinstyle": "round", "lines.scale_dashes": False,
    "legend.frameon": False, "path.simplify": True,
}


# ───────────────────────────── small helpers ─────────────────────────────

def _num(x) -> float:
    """A float; NaN for a blank or non-finite field."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return math.nan
    return v if math.isfinite(v) else math.nan


def _day(iso: str) -> np.datetime64:
    return np.datetime64(str(iso)[:10], "D")


def _fdate(iso: str) -> str:
    d = pd.Timestamp(str(iso)[:10])
    return f"{d.day} {d.strftime('%b %Y')}"


def usd(v: float) -> str:
    """$12,433 (a minus sign for a loss below zero)."""
    if not math.isfinite(v):
        return "n/a"
    return ("−$" if v < 0 else "$") + f"{abs(v):,.0f}"


def _pct(v: float, nd: int = 1) -> str:
    if not math.isfinite(v):
        return "n/a"
    return ("−" if v < 0 and round(abs(v), nd) > 0 else "") + f"{abs(v):.{nd}f}%"


def _signed(v: float, nd: int = 2) -> str:
    """1.31 / −0.24: a number with a true minus sign."""
    if not math.isfinite(v):
        return "n/a"
    return ("−" if v < 0 and round(abs(v), nd) > 0 else "") + f"{abs(v):.{nd}f}"


def _fmt(v, nd: int = 4) -> str:
    """A number for a values file: fixed decimals, blank when missing."""
    f = _num(v)
    return f"{f:.{nd}f}" if math.isfinite(f) else ""


def _clip(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _letter(i: int) -> str:
    """a, b, ... z, aa, ab, ...: a base's key in the scatter."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(97 + r) + s
    return s


def _span_text(vals: Iterable[float], fmt: Callable[[float], str]) -> str:
    """'99.8%', or '91.3% to 100.0%' when the values differ once formatted."""
    v = sorted(float(x) for x in vals)
    a, b = fmt(v[0]), fmt(v[-1])
    return a if a == b else f"{a} to {b}"


def wfile(window: str) -> str:
    """A window key as it appears in a file name (as compare_page.curve_file: other than letters, digits, '.', '-'
    become '_')."""
    return re.sub(r"[^A-Za-z0-9.-]", "_", window)


def _rel(p: Path) -> str:
    return CP._rel(Path(p))


def _read_table(path: Path, required: List[str], optional: List[str]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not CP._columns_ok(df.columns, required, optional):
        raise ValueError(f"{path.name}: columns {list(df.columns)} are not the contract's ({required} + {optional})")
    return CP._with_optional(df, required, optional)


def _chunks(path: Path):
    """A curve file in chunks of CHUNK rows (memory stays small whatever the file's size)."""
    for ch in pd.read_csv(path, dtype={"series_id": str, "date": str}, chunksize=CHUNK):
        if list(ch.columns) != CP.CURVE_COLS:
            raise ValueError(f"{Path(path).name}: columns {list(ch.columns)}, not {CP.CURVE_COLS}")
        ch["equity_usd"] = pd.to_numeric(ch["equity_usd"], errors="coerce")
        yield ch


def _split(frames: List[pd.DataFrame]) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """{series_id: (days as datetime64[D], equity)} from curve rows, each series in date order."""
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    out = {}
    for sid, g in df.groupby("series_id", sort=True):
        d = g["date"].to_numpy().astype("datetime64[D]")
        e = g["equity_usd"].to_numpy(np.float64)
        o = np.argsort(d, kind="stable")
        out[sid] = (d[o], e[o])
    return out


def drawdown_pct(equity: np.ndarray) -> np.ndarray:
    """% below the running peak (0 or negative), as compare_page.curve_stats reads a daily curve."""
    e = np.asarray(equity, np.float64)
    peak = np.maximum.accumulate(e)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(peak > 0, (e / peak - 1.0) * 100.0, 0.0)


def _run_note(row_notes: str) -> str:
    """Why a row's max DD and its daily curve can disagree, in a few words, from the row's notes."""
    m = re.search(r"median of (?:[\w']+ )?(\d+) (?:loop )?timings", row_notes or "")
    return f"{m.group(1)}-timing median" if m else "another run"


# ───────────────────────────── the contract files ─────────────────────────────

class Source:
    """One source's contract files: the series and metrics tables read at once, the curves in chunks on demand."""

    def __init__(self, sid: str, data: Path):
        self.sid, self.data = sid, Path(data)
        self.series_path = self.data / f"{sid}__series.csv"
        self.metrics_path = self.data / f"{sid}__metrics.csv"
        self.present = self.series_path.exists()
        self.series = (_read_table(self.series_path, CP.SERIES_COLS, CP.SERIES_OPT) if self.present
                       else pd.DataFrame(columns=CP.SERIES_COLS + CP.SERIES_OPT))
        self.metrics = (_read_table(self.metrics_path, CP.METRICS_COLS, CP.METRICS_OPT)
                        if self.present and self.metrics_path.exists()
                        else pd.DataFrame(columns=CP.METRICS_COLS + CP.METRICS_OPT))
        self._cost = self.metrics.cost.map(_num)
        self._index: Dict[str, pd.DataFrame] = {}
        self._curves: Dict[str, Dict[str, Tuple[np.ndarray, np.ndarray]]] = {}
        self._rows: Dict[Tuple[str, str], pd.DataFrame] = {}

    def curve_path(self, window: str) -> Path:
        return CP.curve_file(self.sid, window, self.data)

    def has_curves(self, window: str) -> bool:
        """A curve file for a window of the metrics (compare_page.read_source reads exactly these)."""
        return self.present and window in set(self.metrics.window) and self.curve_path(window).exists()

    def windows(self) -> List[str]:
        """The windows of the metrics in the page's order: the common ones, then the studies' own by date."""
        if not len(self.metrics):
            return []
        g = self.metrics.groupby("window").agg(a=("start", "min"), z=("end", "max"))
        return CP._window_order({w: (r.a, r.z) for w, r in g.iterrows()})

    def index(self, window: str, prefetch: Iterable[str] = ()) -> pd.DataFrame:
        """Per series with a curve on the window: rows, first and last date, last equity (one pass over the file,
        which also keeps the curves of ``prefetch``)."""
        if window not in self._index:
            want = set(prefetch)
            parts, keep = [], []
            if self.has_curves(window):
                for ch in _chunks(self.curve_path(window)):
                    g = ch.groupby("series_id", sort=False)
                    parts.append(pd.DataFrame({"n": g.size(), "first": g["date"].first(), "last": g["date"].last(),
                                               "eq_last": g["equity_usd"].last()}))
                    if want:
                        k = ch[ch.series_id.isin(want)]
                        if len(k):
                            keep.append(k)
            if parts:
                idx = pd.concat(parts).groupby(level=0, sort=True).agg(
                    n=("n", "sum"), first=("first", "first"), last=("last", "last"), eq_last=("eq_last", "last"))
            else:
                idx = pd.DataFrame({"n": [], "first": [], "last": [], "eq_last": []})
            self._index[window] = idx
            self._curves.setdefault(window, {}).update(_split(keep))
        return self._index[window]

    def curves(self, window: str, ids: Sequence[str]) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """The curves of ``ids`` on the window (those it has), read in one pass for the ones not yet in memory."""
        if not self.has_curves(window):
            return {}
        idx = self.index(window)
        have = self._curves.setdefault(window, {})
        need = sorted(i for i in set(ids) if i not in have and i in idx.index)
        if need:
            want = set(need)
            keep = [k for k in (ch[ch.series_id.isin(want)] for ch in _chunks(self.curve_path(window))) if len(k)]
            have.update(_split(keep))
        return {i: have[i] for i in ids if i in have}

    def account_rows(self, window: str, symbol: str) -> pd.DataFrame:
        """The account rows at x1.0 of one window and symbol, with the series' fields, numbers, ``has_curve`` and the
        page's growth / DD ``rdd`` (CAGR % / max DD %; a blank CAGR computed from the curve's last equity where the
        series has a curve, as compare_page.fill_from_curve does; marked in ``cagr_derived``). Kept once computed:
        callers never change the frame."""
        if (window, symbol) in self._rows:
            return self._rows[(window, symbol)]
        m = self.metrics
        a = m[(m.window == window) & (m.basis == "account") & (self._cost == 1.0)]
        cols = ["series_id", "symbol", "label", "kind", "family", "role", "eligible", "exam", "sizing", "tags"]
        a = a.merge(self.series[cols], on="series_id", how="inner")
        a = a[a.symbol == symbol].sort_values("series_id", kind="mergesort").reset_index(drop=True)
        a["cagr"] = a.cagr_pct.map(_num).astype(float)
        a["ddp"] = a.max_dd_pct.map(_num).astype(float)
        a["final"] = a.final_usd.map(_num).astype(float)
        a["cagr_derived"] = False
        idx = self.index(window) if self.has_curves(window) else None
        a["has_curve"] = a.series_id.isin(idx.index) if idx is not None else False
        if idx is not None:
            for i in a.index[a.cagr.isna() & a.has_curve]:
                last = float(idx.at[a.at[i, "series_id"], "eq_last"])
                yrs = (_day(a.at[i, "end"]) - _day(a.at[i, "start"])).astype(int) * CP.DAY_S / CP.YEAR_S
                s0 = _num(a.at[i, "start_usd"])
                s0 = s0 if s0 and s0 > 0 else ACCOUNT
                if yrs > 0 and math.isfinite(last):
                    a.at[i, "cagr"] = ((last / s0) ** (1.0 / yrs) - 1.0) * 100.0 if last > 0 else -100.0
                    a.at[i, "cagr_derived"] = True
        a["rdd"] = [round(c / d, 6) if (math.isfinite(c) and math.isfinite(d) and d != 0) else math.nan
                    for c, d in zip(a.cagr, a.ddp)]
        a["rdd"] = a["rdd"].astype(float)
        self._rows[(window, symbol)] = a
        return a


def ranked(rows: pd.DataFrame, need_curve: bool) -> pd.DataFrame:
    """The page's ranking (its "Top 10" rule): growth / DD high to low, over the unit-rule account rows that are not a
    benchmark and have a growth / DD (and a curve, with ``need_curve``); ties by label, then id."""
    c = rows[(rows.role != "benchmark") & rows.sizing.isin(UNIT_RULE) & rows.rdd.notna()]
    if need_curve:
        c = c[c.has_curve]
    return c.assign(_q=-c.rdd).sort_values(["_q", "label", "series_id"], kind="mergesort").drop(columns="_q")


def featured(rows: pd.DataFrame, top: int) -> Tuple[pd.DataFrame, pd.DataFrame, str, int, bool]:
    """(kept, cut, how, n, by_role): the featured rows of one window and symbol. The finalists, then the champions,
    each by the page's ranking; for a source with neither role, its best ``top`` by the page's ranking."""
    fc = rows[rows.role.isin(FEATURED_ROLES)]
    if len(fc):
        rank = {r: i for i, r in enumerate(FEATURED_ROLES)}
        fc = fc.assign(_r=fc.role.map(rank), _q=-fc.rdd.fillna(-np.inf)).sort_values(
            ["_r", "_q", "label", "series_id"], kind="mergesort").drop(columns=["_r", "_q"])
        how = " and ".join(ROLE_PLURAL[r] for r in FEATURED_ROLES if (fc.role == r).any())
        return fc.iloc[:top], fc.iloc[top:], how, len(fc), True
    cand = ranked(rows, need_curve=True)
    return cand.iloc[:top], cand.iloc[top:], f"best {min(top, len(cand))} by growth ÷ DD", len(cand), False


def _featurable(src: Source, rows: pd.DataFrame) -> pd.DataFrame:
    """The rows a source's featured series come from: FINAL10's own designs are drawn as the bots' designs, so they are
    not featured as well."""
    return rows[rows.role != "design"] if src.sid == "final10" else rows


def page_slots(data: Path = DATA) -> Dict[str, Optional[int]]:
    """{colour group: palette slot}, as compare_page.build_blob gives them for the same data folder: every series' group
    (compare_page._group_of), a group "with curves" when a curve file of a window in its source's metrics holds one of
    its series, then compare_page.group_slots."""
    data = Path(data)
    with_curves: Dict[str, bool] = {}
    for sid in CP.sources_in(data):
        s = pd.read_csv(data / f"{sid}__series.csv", dtype=str, keep_default_na=False, usecols=["series_id", "role"])
        grp = {i: CP._group_of(sid, r) for i, r in zip(s.series_id, s.role)}
        for g in sorted(set(grp.values())):
            with_curves.setdefault(g, False)
        need = {g for g in grp.values() if not with_curves[g]}
        mp = data / f"{sid}__metrics.csv"
        windows = (sorted(set(pd.read_csv(mp, dtype=str, keep_default_na=False, usecols=["window"]).window))
                   if mp.exists() else [])
        for w in windows:
            p = CP.curve_file(sid, w, data)
            if not need:
                break
            if not p.exists():
                continue
            for ch in pd.read_csv(p, dtype=str, usecols=["series_id"], chunksize=CHUNK):
                found = {grp[x] for x in ch.series_id.unique() if x in grp}
                for g in found:
                    with_curves[g] = True
                need -= found
                if not need:
                    break
    return CP.group_slots(with_curves)


_MACHADO = {"protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216),
                       (-0.003882, -0.048116, 1.051998)),
            "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413),
                       (-0.011820, 0.042940, 0.968881))}


def colour_distance(h1: str, h2: str, kind: Optional[str] = None) -> float:
    """OKLab distance x 100 of two hex colours, under normal vision or a simulated protan / deutan deficiency
    (Machado 2009 at severity 1): the dataviz validator's measure."""
    def lab(h):
        x = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        x = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in x]
        if kind:
            m = _MACHADO[kind]
            x = [max(0.0, min(1.0, sum(m[i][j] * x[j] for j in range(3)))) for i in range(3)]
        r, g, b = x
        l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
        m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
        s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
        return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
                1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
                0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)
    return 100.0 * math.dist(lab(h1), lab(h2))


def pair_ok(a: str, b: str) -> bool:
    """Whether two series hues clear the dataviz floors side by side: CVD separation >= 8 and normal vision >= 15
    (ink, buy-and-hold's colour, is not a series hue and always passes)."""
    if INK in (a, b) or a == b:
        return a != b
    return (min(colour_distance(a, b, "protan"), colour_distance(a, b, "deutan")) >= 8.0
            and colour_distance(a, b) >= 15.0)


def colour_of(group: str, slots: Dict[str, Optional[int]]) -> str:
    """A group's colour: its palette slot, or the ink colour (buy-and-hold, or a group past the palette)."""
    k = slots.get(group)
    return PALETTE[k] if k is not None and k < len(PALETTE) else INK


def short_name(sid: str) -> str:
    """How the page names a source in a sentence: "study 1", "FINAL10", "Balke"..."""
    g = CP._group_of(sid, "variant")
    if g not in ("earlier",) and g in CP.GROUP_SHORT:
        return CP.GROUP_SHORT[g]
    return CP.SOURCES.get(sid, {}).get("short", sid)


def window_text(window: str, start: str, end: str) -> str:
    """'13 Nov 2021 - 13 Nov 2026, five years' (the page's window text, with the rows' own dates)."""
    meta = CP.WINDOW_META.get(window, ("", ""))[1]
    rest = re.sub(r"^\d{1,2} \w{3} \d{4} - \d{1,2} \w{3} \d{4}(, )?", "", meta)
    return f"{_fdate(start)} – {_fdate(end)}" + (f", {rest}" if rest else "")


# ───────────────────────────── what one graph shows ─────────────────────────────

def _style(n: int) -> Tuple[object, Optional[str]]:
    """The page's line keys within a group: the n-th line's dash, and past six a marker."""
    return DASHES[n % 6], (MARKERS[(n // 6 - 1) % len(MARKERS)] if n >= 6 else None)


@dataclass
class Keys:
    """The line keys of one source and symbol, the same on every window whichever windows are drawn: featured series
    numbered in the order they first appear over the source's windows with curves (in the page's order, each in its
    featured order), base rows lettered by label after them. A series' dash (and, past six, its marker) follows its
    key."""
    num: Dict[str, int] = field(default_factory=dict)
    let: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def of(cls, featured_ids: Sequence[str], base_ids: Sequence[str] = ()) -> "Keys":
        k = cls()
        for i in featured_ids:
            k.num.setdefault(i, len(k.num))
        for i in base_ids:
            if i not in k.num:
                k.let.setdefault(i, len(k.let))
        return k

    def style(self, sid: str) -> Tuple[object, Optional[str]]:
        if sid in self.num:
            return _style(self.num[sid])
        return _style(len(self.num) + self.let.get(sid, len(self.let)))

    def text(self, sid: str) -> str:
        if sid in self.num:
            return str(self.num[sid] + 1)
        if sid in self.let:
            return _letter(self.let[sid])
        return ""


@dataclass(eq=False)
class Line:
    """One drawn series: its row's numbers, its style and (when it has one) its daily curve (compared by identity:
    it holds arrays)."""
    series_id: str
    label: str
    kind: str                   # featured, base, design or bh
    role: str
    colour: str
    dash: object
    marker: Optional[str]
    final: float
    cagr: float
    ddp: float
    rdd: float
    dd_marks: str
    eligible: bool
    exam: str
    sizing: str
    wiped: bool
    family: str = ""
    row_notes: str = ""
    key: str = ""                           # its number (featured) or letter (base) in the scatter
    x: Optional[np.ndarray] = None          # matplotlib date numbers
    y: Optional[np.ndarray] = None          # equity, USD
    days: Optional[np.ndarray] = None       # the curve's dates (datetime64[D])

    @property
    def end(self) -> float:
        return float(self.y[-1]) if self.y is not None and len(self.y) else self.final

    @property
    def drawn(self) -> bool:
        return self.y is not None and len(self.y) > 0

    @property
    def style_name(self) -> str:
        s = DASH_NAMES[DASHES.index(self.dash)] if self.dash in DASHES else str(self.dash)
        return s + (f", marker {self.marker}" if self.marker else "")


@dataclass
class Ctx:
    """Everything the four graphs of one source, symbol and window draw."""
    src: Source
    symbol: str
    window: str
    start: str
    end: str
    rows: pd.DataFrame                      # the source's account rows at x1.0
    featured: List[Line]
    designs: List[Line]
    bhs: List[Line]
    how: str                                # "finalists and champions" / "best 6 by growth / DD"
    by_role: bool
    n_featured: int                         # featured rows (or ranked rows) before --top
    top: int
    equity_top: int = EQUITY_TOP
    bases: List[Line] = field(default_factory=list)
    base_lines: bool = False                # the bases are drawn as lines (equity, drawdown)
    rebuilt: str = ""                       # the window the bots' designs come from when it is not this one
    cut: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)    # shared by the four graphs: cuts, missing references
    curve_notes: List[str] = field(default_factory=list)   # the equity and drawdown graphs' only: the curves
    files: Dict[str, List[Path]] = field(default_factory=dict)  # per graph kind: the contract files it reads
    colour: str = INK
    bots: str = INK
    elig_rule: bool = False

    @property
    def tag(self) -> str:
        return f"{self.src.sid} {self.symbol} {self.window}"

    @property
    def short(self) -> str:
        return short_name(self.src.sid)

    @property
    def lines(self) -> List[Line]:
        """The drawdown graph's lines: every featured series, the bases drawn as lines, the designs, buy-and-hold."""
        return [ln for ln in self.featured + (self.bases if self.base_lines else []) + self.designs + self.bhs
                if ln.drawn]

    @property
    def eq_featured(self) -> List[Line]:
        return [ln for ln in self.featured if ln.drawn][: self.equity_top]

    @property
    def eq_lines(self) -> List[Line]:
        """The equity graph's lines: the first ``equity_top`` featured series with a curve, then the others."""
        return self.eq_featured + [ln for ln in (self.bases if self.base_lines else []) + self.designs + self.bhs
                                   if ln.drawn]

    @property
    def wtext(self) -> str:
        return window_text(self.window, self.start, self.end)

    @property
    def sym(self) -> str:
        return CP.SYMBOL_NAME.get(self.symbol, self.symbol)

    @property
    def designs_title(self) -> str:
        return "The bots' designs (study 1's rebuilds)" if self.rebuilt else "The bots' designs (FINAL10)"

    def ref_ids(self) -> set:
        return {ln.series_id for ln in self.designs + self.bhs}


def _line(r, kind: str, colour: str, dash, marker) -> Line:
    return Line(series_id=r.series_id, label=r.label, kind=kind, role=r.role, colour=colour, dash=dash, marker=marker,
                final=float(r.final), cagr=float(r.cagr), ddp=float(r.ddp), rdd=float(r.rdd), dd_marks=r.dd_marks,
                eligible=str(r.eligible) == "1", exam=r.exam, sizing=r.sizing, wiped=str(r.wiped) == "1",
                family=str(r.family), row_notes=str(getattr(r, "row_notes", "") or ""))


def _attach(lines: List[Line], curves: Dict[str, Tuple[np.ndarray, np.ndarray]]) -> None:
    for ln in lines:
        c = curves.get(ln.series_id)
        if c is not None and len(c[0]):
            ln.days = c[0]
            ln.x = mdates.date2num(c[0])
            ln.y = c[1]


def _windows_with(src: Source, symbol: str, role: str) -> List[str]:
    """The windows on which a source has account rows of a role and symbol (for a note when one is missing)."""
    ids = set(src.series.series_id[(src.series.role == role) & (src.series.symbol == symbol)])
    m = src.metrics
    ws = set(m.window[m.series_id.isin(ids) & (m.basis == "account")])
    return [w for w in src.windows() if w in ws]


def context(src: Source, f10: Source, bh: Source, slots: Dict[str, Optional[int]], window: str, symbol: str,
            top: int, log: Callable[[str], None], keys: Optional[Keys] = None,
            equity_top: int = EQUITY_TOP) -> Optional[Ctx]:
    """The featured series, the bases, the bots' designs and buy-and-hold of one window and symbol, with their curves;
    None (and a log line) when the source has no account row at x1.0, or no curve of the symbol, on the window.
    ``keys``: the run's line keys of the symbol (draw computes them over every window); by default this window's."""
    tag = f"{src.sid} {symbol} {window}"
    rows = src.account_rows(window, symbol)
    if not len(rows):
        log(f"{tag}: skipped: the source has no account row at x1.0 for this symbol on this window")
        return None
    if not rows.has_curve.any():
        log(f"{tag}: skipped: the source has no curve of this symbol on this window")
        return None
    kept, cut, how, n, by_role = featured(_featurable(src, rows), top)
    base_rows = rows[(rows.role == "base") & ~rows.series_id.isin(set(kept.series_id))].sort_values(
        ["label", "series_id"], kind="mergesort")
    if keys is None:
        keys = Keys.of(list(kept.series_id), list(base_rows.series_id))
    ctx = Ctx(src=src, symbol=symbol, window=window, start=str(rows.start.min()), end=str(rows.end.max()), rows=rows,
              featured=[], designs=[], bhs=[], how=how, by_role=by_role, n_featured=n, top=top, equity_top=equity_top,
              colour=colour_of(CP._group_of(src.sid, "variant"), slots), bots=colour_of("bots", slots),
              elig_rule=bool((src.series.eligible.astype(str) == "1").any()))
    for r in kept.itertuples(index=False):
        dash, marker = keys.style(r.series_id)
        ln = _line(r, "featured", colour_of(CP._group_of(src.sid, r.role), slots), dash, marker)
        ln.key = keys.text(r.series_id)
        ctx.featured.append(ln)
    for r in base_rows.itertuples(index=False):
        dash, marker = keys.style(r.series_id)
        ln = _line(r, "base", ctx.colour, dash, marker)
        ln.key = keys.text(r.series_id)
        ctx.bases.append(ln)
    ctx.base_lines = 0 < len(ctx.bases) <= MAX_BASE_LINES
    _attach(ctx.featured + (ctx.bases if ctx.base_lines else []),
            src.curves(window, [ln.series_id for ln in ctx.featured + (ctx.bases if ctx.base_lines else [])]))
    if by_role:
        log(f"{tag}: featured: the {how} ({len(kept)} of {n}): " + ", ".join(kept.series_id))
        if len(cut):
            ctx.cut = list(cut.series_id)
            log(f"{tag}: --top {top} cut {len(cut)} of {n} featured series: " + ", ".join(cut.series_id))
            ctx.notes.append(f"--top {top} cut {len(cut)} of the {n} {how} ("
                             + "; ".join(_clip(x, 40) for x in cut.label[:4])
                             + (f"; and {len(cut) - 4} more, listed in the log" if len(cut) > 4 else "") + ").")
    else:
        log(f"{tag}: featured: no finalist or champion; the best {len(kept)} of {n} ranked rows by growth / DD "
            f"(--top {top}): " + ", ".join(kept.series_id))
        if n > len(kept):
            ctx.cut = list(cut.series_id)
            ctx.notes.append(f"The source has no finalist or champion: its best {len(kept)} of {n} ranked rows "
                             f"(--top {top}).")
    nocurve = [ln.series_id for ln in ctx.featured if not ln.drawn]
    if nocurve:
        log(f"{tag}: no curve on this window for featured " + ", ".join(nocurve))
        ctx.curve_notes.append(f"No curve on this window for {len(nocurve)} featured series (not in the equity and "
                               "drawdown graphs).")
    if ctx.bases:
        names = "; ".join(_clip(ln.label, 34) for ln in ctx.bases)
        if ctx.base_lines:
            log(f"{tag}: bases drawn as lines: " + ", ".join(ln.series_id for ln in ctx.bases))
        else:
            log(f"{tag}: {len(ctx.bases)} bases, more than {MAX_BASE_LINES}: marked in the risk/return graph only")
            ctx.curve_notes.append(f"The source's {len(ctx.bases)} base rows ({names}) are not drawn as lines (more "
                                   f"than {MAX_BASE_LINES} would crowd the graph): they are lettered in the "
                                   "risk/return graph.")
    # the bots' designs (FINAL10's role design): the same window, or study 1's rebuilds on study 1's windows
    base_files = [src.series_path, src.metrics_path]
    curve_files = [src.curve_path(window)]
    ref_files: List[Path] = []
    if not f10.present:
        ctx.notes.append("The bots' designs are not drawn: the data folder has no final10 files.")
        log(f"{tag}: the bots' designs not drawn: no final10 files in {f10.data}")
    else:
        d = f10.account_rows(window, symbol)
        d = d[d.role == "design"]
        if not len(d) and window in CP.REBUILD_WINDOW:
            rw = CP.REBUILD_WINDOW[window]
            d2 = f10.account_rows(rw, symbol)
            d2 = d2[d2.role == "design"]
            if len(d2):
                d, ctx.rebuilt = d2, rw
        d = d.sort_values(["label", "series_id"], kind="mergesort")
        dwin = ctx.rebuilt or window
        if not len(d):
            elsewhere = _windows_with(f10, symbol, "design")
            ctx.notes.append(f"The bots' designs are not drawn: FINAL10 has no design row on window '{window}'"
                             + (f" (they are on {', '.join(elsewhere)})" if elsewhere else "") + ".")
            log(f"{tag}: the bots' designs not drawn: final10 has no design row on {window}")
        elif ctx.rebuilt:
            owner = CP.WINDOW_META.get(dwin, ("the rebuilds of the bots' designs", ""))[0] or "the rebuilds"
            mk = "/".join(sorted({m for m in d.dd_marks if m})) or "their own"
            ctx.notes.append(f"The bots' designs come from FINAL10's window '{dwin}' ({owner[:1].lower() + owner[1:]}, "
                             f"{_fdate(d.start.min())} – {_fdate(d.end.max())}, max DD on {mk} marks): they stop on "
                             f"{_fdate(d.end.max())}, where FINAL10's trades end, while this window runs to "
                             f"{_fdate(ctx.end)}.")
            log(f"{tag}: the bots' designs from window {dwin} (final10 has no design row on {window})")
        close = not pair_ok(ctx.colour, ctx.bots)
        if close and len(d):
            log(f"{tag}: warning: the source's colour {ctx.colour} and the bots' {ctx.bots} are below the dataviz "
                "floors side by side (CVD 8, normal vision 15); the bots' lines get square markers")
            ctx.notes.append("The source's colour and the bots' are close under colour-vision deficiency: the bots' "
                             "designs carry square markers.")
        for k, r in enumerate(d.itertuples(index=False)):
            dash, marker = _style(k)
            ctx.designs.append(_line(r, "design", ctx.bots, dash, "s" if close else marker))
        if ctx.designs:
            if f10 is not src:
                ref_files += [f10.series_path, f10.metrics_path]
            _attach(ctx.designs, f10.curves(dwin, [ln.series_id for ln in ctx.designs]))
            if not any(ln.drawn for ln in ctx.designs):
                ctx.curve_notes.append(f"The bots' designs have rows on '{dwin}' but no curve: not in the equity "
                                       "and drawdown graphs.")
                log(f"{tag}: the bots' designs have no curve on {dwin}")
            elif f10 is not src or dwin != window:
                curve_files.append(f10.curve_path(dwin))
    # buy-and-hold, same window
    if not bh.present:
        ctx.notes.append("Buy-and-hold is not drawn: the data folder has no benchmarks files.")
        log(f"{tag}: buy-and-hold not drawn: no benchmarks files in {bh.data}")
    else:
        b = bh.account_rows(window, symbol)
        b = b[b.role == "benchmark"]
        b = b.assign(_o=b.sizing.map(lambda s: BH_ORDER.get(s, 9))).sort_values(
            ["_o", "label", "series_id"], kind="mergesort")
        if not len(b):
            ctx.notes.append(f"Buy-and-hold is not drawn: no benchmark row on window '{window}'.")
            log(f"{tag}: buy-and-hold not drawn: no benchmark row on {window}")
        for k, r in enumerate(b.itertuples(index=False)):
            dash = {"fully invested": None, "0.01 lot fixed": DASHES[2]}.get(r.sizing, DASHES[k % 6])
            ln = _line(r, "bh", INK, dash, None)
            ln.label = BH_SHORT.get(r.sizing, r.label)
            ctx.bhs.append(ln)
        if ctx.bhs:
            if bh is not src:
                ref_files += [bh.series_path, bh.metrics_path]
            _attach(ctx.bhs, bh.curves(window, [ln.series_id for ln in ctx.bhs]))
            if not any(ln.drawn for ln in ctx.bhs):
                ctx.curve_notes.append(f"Buy-and-hold has rows on '{window}' but no curve: not in the equity and "
                                       "drawdown graphs.")
                log(f"{tag}: buy-and-hold has no curve on {window}")
            elif bh is not src:
                curve_files.append(bh.curve_path(window))
    off = [ln for ln in ctx.lines if math.isfinite(ln.final) and abs(ln.end - ln.final) > 0.011]
    if off:
        why = sorted({ln.row_notes for ln in off if ln.row_notes})
        ctx.curve_notes.append("A line ends at its curve's last value; the row's final equity differs for "
                               + ", ".join(f"{_clip(ln.label, 30)} ({usd(ln.final)})" for ln in off)
                               + (f" (row notes: {_clip('; '.join(why), 170)})" if why else "") + ".")
    ctx.files = {"equity": base_files + ref_files + curve_files, "drawdown": base_files + ref_files + curve_files,
                 "risk_return": base_files + ref_files, "families": base_files + ref_files}
    return ctx


# ───────────────────────────── the canvas ─────────────────────────────

class Canvas:
    """A fixed-size figure laid out from the top (title, subtitle) and from the bottom (note, legends); the plot takes
    what is left. Sizes are in pixels at 150 DPI; text is measured with the Agg renderer before it is placed."""

    MARGIN = 26.0

    def __init__(self, kind: str):
        w, h = SIZES[kind]
        self.fig = Figure(figsize=(w, h), dpi=DPI, facecolor=SURFACE)
        FigureCanvasAgg(self.fig)
        self.W, self.H = w * DPI, h * DPI
        self.r = self.fig.canvas.get_renderer()
        self.top = 0.0          # px taken from the top
        self.bottom = 0.0       # px taken from the bottom
        self._props: Dict[Tuple[float, str], FontProperties] = {}

    def measure(self, s: str, size: float, weight: str = "normal") -> Tuple[float, float]:
        key = (size, weight)
        if key not in self._props:
            self._props[key] = FontProperties(family=FONT, size=size, weight=weight)
        w, h, _ = self.r.get_text_width_height_descent(s, self._props[key], ismath=False)
        return float(w), float(h)

    def wrap(self, s: str, size: float, width: float) -> str:
        """Greedy line breaks at the measured width."""
        out = []
        for para in str(s).split("\n"):
            line = ""
            for word in para.split(" "):
                cand = word if not line else line + " " + word
                if line and self.measure(cand, size)[0] > width:
                    out.append(line)
                    line = word
                else:
                    line = cand
            out.append(line)
        return "\n".join(out)

    def fit(self, s: str, size: float, width: float) -> str:
        """The text, shortened with an ellipsis to fit the width."""
        s = str(s)
        if self.measure(s, size)[0] <= width:
            return s
        while len(s) > 1 and self.measure(s + "…", size)[0] > width:
            s = s[:-1]
        return s.rstrip() + "…"

    def text(self, x: float, y: float, s: str, **kw):
        return self.fig.text(x / self.W, y / self.H, s, **kw)

    def extent(self, artist):
        return artist.get_window_extent(self.r)

    def header(self, title: str, subtitle: str) -> None:
        x, y, width = self.MARGIN, self.H - 20.0, self.W - 2 * self.MARGIN
        t = self.text(x, y, self.wrap(title, 13.5, width), size=13.5, color=INK, va="top", ha="left",
                      linespacing=1.25, gid="title")
        y -= self.extent(t).height + 9.0
        s = self.text(x, y, self.wrap(subtitle, 9.5, width), size=9.5, color=INK2, va="top", ha="left",
                      linespacing=1.35, gid="subtitle")
        y -= self.extent(s).height
        self.top = self.H - y + 22.0

    def note(self, s: str) -> None:
        t = self.text(self.MARGIN, 14.0, self.wrap(s, 8.0, self.W - 2 * self.MARGIN), size=8.0, color=INK2,
                      va="bottom", ha="left", linespacing=1.4, gid="note")
        self.bottom = 14.0 + self.extent(t).height + 16.0

    def _legend(self, title: Optional[str], handles: list, texts: List[str], ncols: int):
        leg = self.fig.legend(handles, texts, loc="lower left", bbox_to_anchor=(0.0, 0.0),
                              bbox_transform=self.fig.transFigure, title=title, alignment="left", ncols=ncols,
                              fontsize=9.0, title_fontsize=9.5, labelcolor=INK2, frameon=False, borderpad=0.0,
                              borderaxespad=0.0, handlelength=2.9, handletextpad=0.7, labelspacing=0.42,
                              columnspacing=1.8)
        if title:
            leg.get_title().set_color(INK)
        return leg

    def _fit_entry(self, entry, width: float) -> str:
        """An entry's text fitted to a width: a (head, tail) entry keeps its tail (a line's final equity)."""
        if isinstance(entry, str):
            return self.fit(entry, 9.0, width)
        head, tail = entry
        return self.fit(head, 9.0, max(width - self.measure(tail, 9.0)[0], 24.0)) + tail

    def legends(self, groups: Sequence[Tuple[Optional[str], list]], gap_x: float = 44.0, gap_y: float = 12.0,
                ncols: Optional[int] = None) -> None:
        """One legend per group (a title in ink, its entries in the secondary ink) above the note. A group joins the
        previous column while that column stays no taller than the tallest group (and one gap); columns run left to
        right and start a new row where the next would cross the right margin. A group wider than the figure goes to
        one column, then has its entries shortened (an entry may be (text, tail): the tail is kept). ``ncols``:
        entries per row (default one column, two past seven entries)."""
        avail = self.W - 2 * self.MARGIN
        made = []
        for title, entries in groups:
            if not entries:
                continue
            nc = min(ncols if ncols else (1 if len(entries) <= 7 else 2), len(entries))
            texts = [e if isinstance(e, str) else e[0] + e[1] for _, e in entries]
            handles = [h for h, _ in entries]
            leg = self._legend(title, handles, texts, nc)
            bb = self.extent(leg)
            if bb.width > avail and nc > 1:
                leg.remove()
                nc = 1
                leg = self._legend(title, handles, texts, nc)
                bb = self.extent(leg)
            for _ in range(4):
                if bb.width <= avail:
                    break
                widest = max(self.measure(t, 9.0)[0] for t in texts)
                texts = [self._fit_entry(e, widest - (bb.width - avail) - 2.0) for _, e in entries]
                leg.remove()
                leg = self._legend(title, handles, texts, nc)
                bb = self.extent(leg)
            made.append((leg, bb.width, bb.height))
        if not made:
            return
        hmax = max(h for _, _, h in made)
        cols: List[list] = []
        for item in made:
            if cols and sum(h + gap_y for _, _, h in cols[-1]) + item[2] <= hmax + gap_y + 0.5:
                cols[-1].append(item)
            else:
                cols.append([item])
        rows: List[list] = []
        x = self.MARGIN
        for col in cols:
            cw = max(w for _, w, _ in col)
            if rows and x + cw <= self.W - self.MARGIN:
                rows[-1].append(col)
            else:
                rows.append([col])
                x = self.MARGIN
            x += cw + gap_x

        def col_h(col):
            return sum(h for _, _, h in col) + gap_y * (len(col) - 1)
        heights = [max(col_h(c) for c in row) for row in rows]
        gap_row = 16.0
        top = self.bottom + sum(heights) + gap_row * (len(rows) - 1)
        y_row = top
        for row, rh in zip(rows, heights):
            x = self.MARGIN
            for col in row:
                y = y_row
                for leg, w, h in col:
                    leg.set_bbox_to_anchor((x / self.W, (y - h) / self.H), transform=self.fig.transFigure)
                    y -= h + gap_y
                x += max(w for _, w, _ in col) + gap_x
            y_row -= rh + gap_row
        self.bottom = top + 20.0

    def axes(self, left: float, right: float, below: float = 38.0, above: float = 0.0):
        b = self.bottom + below
        t = self.H - self.top - above
        ax = self.fig.add_axes([left / self.W, b / self.H, (self.W - left - right) / self.W, (t - b) / self.H])
        return ax

    def fit_left(self, ax, size: float = 9.0) -> None:
        """Move the plot's left edge so that its y tick labels and y label fit inside the figure (call once the
        limits, locator and formatter are set)."""
        a, b = sorted(ax.get_ylim())
        loc, fmt = ax.yaxis.get_major_locator(), ax.yaxis.get_major_formatter()
        vals = [v for v in loc.tick_values(a, b) if a - 1e-9 * (abs(a) + 1) <= v <= b + 1e-9 * (abs(b) + 1)]
        fmt.set_locs(vals)
        width = max([self.measure(fmt(v, i), size)[0] for i, v in enumerate(vals)] or [0.0])
        need = self.MARGIN + width + matplotlib.rcParams["ytick.major.pad"] / PX + 8.0
        if ax.yaxis.label.get_text():
            need += self.measure(ax.yaxis.label.get_text(), 9.0)[1] + ax.yaxis.labelpad / PX
        pos = ax.get_position()
        right = pos.x1 * self.W
        ax.set_position([need / self.W, pos.y0, (right - need) / self.W, pos.height])

    def save(self, path: Path) -> None:
        self.fig.savefig(path, dpi=DPI, metadata=META, facecolor=SURFACE)


def _quiet(ax, grid: str = "y") -> None:
    """Recessive chrome: hairline grid on one axis, the bottom axis line only, no y ticks."""
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.spines["bottom"].set_linewidth(HAIR)
    if grid:
        ax.grid(True, axis=grid, color=GRID, linewidth=HAIR)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=3, color=AXIS, width=HAIR)


def _usd_formatter(compact: bool) -> FuncFormatter:
    """$2,000 in full under 10,000; $10K on an axis that reaches it (one style per axis)."""
    def f(v, pos=None):
        a = abs(v)
        if compact:
            s = f"{a / 1e6:g}M" if a >= 1e6 else f"{a / 1e3:g}K"
        else:
            s = f"{a:,.0f}"
        return ("−$" if v < 0 else "$") + s
    return FuncFormatter(f)


def _pct_formatter(nd: int = 0) -> FuncFormatter:
    return FuncFormatter(lambda v, pos=None: ("−" if v < -1e-12 else "") + f"{abs(v):.{nd}f}%")


def _date_axis(ax, x0: float, x1: float, width_px: float, cv: Canvas, size: float = 9.0) -> None:
    """Year ticks on long windows, month ticks on short ones, as many as fit the width: each label gets its measured
    width ('2026', 'Sep 2026') and some air (24 px, 16 px between the wider month labels)."""
    span = x1 - x0
    steps = (12, 24, 36, 60, 120) if span > 3 * 365 else (1, 2, 3, 4, 6, 12, 24)
    per_year, per_month = cv.measure("2026", size)[0] + 24.0, cv.measure("Sep 2026", size)[0] + 16.0
    months = steps[-1]
    for months in steps:
        per = per_year if months >= 12 else per_month
        if span / (30.44 * months) * per <= width_px:
            break
    if months >= 12:
        ax.xaxis.set_major_locator(mdates.YearLocator(base=months // 12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[m for m in range(1, 13) if (m - 1) % months == 0]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(x0, x1)


def _xspan(ctx: Ctx) -> Tuple[float, float]:
    """The window on the date axis: the opening row (the day before the start) to the last day."""
    return (float(mdates.date2num(_day(ctx.start) - np.timedelta64(1, "D"))),
            float(mdates.date2num(_day(ctx.end) - np.timedelta64(1, "D"))))


def _handle(ln: Line) -> Line2D:
    """A legend key: the line's colour and dash (and its marker past six lines in a group)."""
    return Line2D([0, 1], [0, 0], color=ln.colour, lw=LINE, ls=ln.dash or "-", marker=ln.marker,
                  ms=8 * PX, mfc=ln.colour, mec=SURFACE, mew=2 * PX, markevery=[1] if ln.marker else None,
                  solid_capstyle="round", dash_capstyle="round")


def _source_note(files: Sequence[Path]) -> str:
    """'Source: <folder>/ (a, b, c), the comparison page's contract files; drawn by ...'"""
    seen, folders = [], {}
    for f in files:
        f = Path(f)
        if f in seen:
            continue
        seen.append(f)
        folders.setdefault(_rel(f.parent), []).append(f.name)
    body = "; ".join(f"{k}/ ({', '.join(v)})" for k, v in folders.items())
    return f"Source: {body}, the comparison page's contract files; drawn by backtesting/research/study_graphs.py."


def _marks_text(ctx: Ctx, source_marks: Iterable[str], des: Sequence[Line], bhs: Sequence[Line]) -> str:
    """'Max DD marks: study 1 M1; the bots' designs second/tick; buy-and-hold M1.'"""
    marks = {}
    for g, mk in ((ctx.short, source_marks), ("the bots' designs", [ln.dd_marks for ln in des]),
                  ("buy-and-hold", [ln.dd_marks for ln in bhs])):
        v = sorted({m for m in mk if m})
        if v:
            marks[g] = "/".join(v)
    return ("Max DD marks: " + "; ".join(f"{g} {m}" for g, m in marks.items()) + ".") if marks else ""


def _spread(want: List[float], gap: float, lo: float, hi: float) -> List[float]:
    """Positions at least ``gap`` apart, each as near its wanted place as clusters allow, inside [lo, hi] (``want``
    ascending)."""
    n = len(want)
    if not n:
        return []
    if n > 1 and (n - 1) * gap > hi - lo:
        gap = (hi - lo) / (n - 1)
    clusters: List[List[float]] = []          # [first index, count, first position]
    for i, v in enumerate(want):
        clusters.append([i, 1, v])
        while len(clusters) > 1 and clusters[-2][2] + clusters[-2][1] * gap > clusters[-1][2]:
            a, b = clusters[-2], clusters[-1]
            k = int(a[1] + b[1])
            mean = sum(want[int(a[0]): int(a[0]) + k]) / k
            clusters[-2:] = [[a[0], k, mean - (k - 1) * gap / 2.0]]
    pos = []
    for _, k, p in clusters:
        pos += [p + j * gap for j in range(int(k))]
    for i in range(n):
        pos[i] = max(pos[i], lo if i == 0 else pos[i - 1] + gap)
    if pos[-1] > hi:
        pos[-1] = hi
        for i in range(n - 2, -1, -1):
            pos[i] = min(pos[i], pos[i + 1] - gap)
    return pos


def _halo(width: float = HALO):
    return [patheffects.withStroke(linewidth=width, foreground=SURFACE)]


# ───────────────────────────── labels next to points ─────────────────────────────

RINGS = (11.0, 16.0, 23.0, 32.0, 44.0, 60.0, 82.0, 110.0, 145.0, 190.0)     # px from the point
ANGLES = (0.0, 180.0, 90.0, 270.0, 45.0, 135.0, 225.0, 315.0, 22.5, 157.5, 202.5, 337.5, 67.5, 112.5, 247.5, 292.5)
CROWD = 20.0                          # px: a point with another labelled point this close gets its label further out


def _overlap(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _pad(b, p: float):
    return (b[0] - p, b[1] - p, b[2] + p, b[3] + p)


def _seg_hits(p, q, b) -> bool:
    """Whether the segment p-q crosses the box b (Liang-Barsky clipping)."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - b[0]), (dx, b[2] - x0), (-dy, y0 - b[1]), (dy, b[3] - y0)):
        if pp == 0:
            if qq < 0:
                return False
            continue
        t = qq / pp
        if pp < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1


def _seg_near(p, q, c, r: float) -> bool:
    """Whether the segment p-q passes closer than r to the point c."""
    (x0, y0), (x1, y1), (cx, cy) = p, q, c
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - x0) * dx + (cy - y0) * dy) / L2))
    return math.hypot(x0 + t * dx - cx, y0 + t * dy - cy) < r


def _leader(px: float, py: float, box) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """The hairline from a point's mark to its label's nearest edge, or None when the label sits next to the mark."""
    tx, ty = min(max(px, box[0]), box[2]), min(max(py, box[1]), box[3])
    d = math.hypot(tx - px, ty - py)
    if d <= MARK_R + 4.5:
        return None
    ux, uy = (tx - px) / d, (ty - py) / d
    return (px + ux * (MARK_R - 1.0), py + uy * (MARK_R - 1.0)), (tx - ux * 2.0, ty - uy * 2.0)


def _covered(pts: np.ndarray, box, r: float) -> int:
    """How many points (px, as an n x 2 array) of radius r a box touches."""
    if not len(pts):
        return 0
    return int(np.count_nonzero((pts[:, 0] > box[0] - r) & (pts[:, 0] < box[2] + r)
                                & (pts[:, 1] > box[1] - r) & (pts[:, 1] < box[3] + r)))


def _place_labels(cv: Canvas, ax, items: Sequence[Tuple[float, float, str, str]], soft: Sequence = (),
                  taken: Sequence = (), size: float = 8.5) -> Dict[str, tuple]:
    """Labels next to points, in priority order (``items``: x, y in data units, text, gid). Each label goes to the
    cheapest spot on rings around its point (16 directions, 11 to 190 px out). Hard rules, in the cost first: the text
    stays inside the plot; its box, padded by the halo and 2 px, overlaps no other label (``taken``: halo-padded
    boxes already placed, such as the diagonal's label), no labelled mark and no earlier label's leader; its leader
    crosses neither labels nor marks. Then the
    fewest context points covered (``soft``: data points, 8 px dots), then the distance. A point with another labelled
    point within 20 px starts 20 px out. A label away from its mark gets a hairline leader. Where no spot keeps every
    rule (a point boxed in by its neighbours), the breaches are weighed: a label over another label is the last resort
    (100), then over another labelled mark (10), a leader through a label or a label over a leader (5), a leader past
    another mark (1, judged on the round mark, so a leader may pass between dots). Text in ink with a surface halo.
    Returns {gid: the label's box in px}."""
    if not items:
        return {}
    bb = cv.extent(ax)
    lim = (bb.x0 + 2.0, bb.y0 + 2.0, bb.x1 - 2.0, bb.y1 - 2.0)
    pts = [tuple(float(v) for v in ax.transData.transform((x, y))) for x, y, _, _ in items]
    marks = [(px - MARK_R, py - MARK_R, px + MARK_R, py + MARK_R) for px, py in pts]
    sp = (np.asarray(ax.transData.transform(np.asarray(soft, float).reshape(-1, 2)), float).reshape(-1, 2)
          if len(soft) else np.zeros((0, 2)))
    taken = [tuple(t) for t in taken]
    leaders: List[tuple] = []                 # the leaders drawn so far, (start, end) in px
    inv = ax.transData.inverted()
    placed: Dict[str, tuple] = {}
    lp = cv.measure("lp", size)[1]           # a line of text is drawn at least as tall as "lp" (its descender too)
    for i, ((x, y, s, gid), (px, py)) in enumerate(zip(items, pts)):
        w, h = cv.measure(s, size)
        h = max(h, lp)
        crowded = any(j != i and math.hypot(qx - px, qy - py) < CROWD for j, (qx, qy) in enumerate(pts))
        others = [mk for k, mk in enumerate(marks) if k != i]
        other_pts = [q for k, q in enumerate(pts) if k != i]
        best = None
        for dist in RINGS:
            if crowded and dist < CROWD:
                continue
            for ang in ANGLES:
                c, sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                ax_, ay_ = px + dist * c, py + dist * sn
                x0 = ax_ if c > 0.2 else (ax_ - w if c < -0.2 else ax_ - w / 2.0)
                y0 = ay_ if sn > 0.2 else (ay_ - h if sn < -0.2 else ay_ - h / 2.0)
                box = (x0, y0, x0 + w, y0 + h)
                padded = _pad(box, LABEL_PAD)
                bad = 1000 if (box[0] < lim[0] or box[1] < lim[1] or box[2] > lim[2] or box[3] > lim[3]) else 0
                bad += 100 * sum(_overlap(padded, t) for t in taken) + 10 * sum(_overlap(padded, mk) for mk in others)
                bad += 5 * sum(_seg_hits(a, b, padded) for a, b in leaders)
                lead = _leader(px, py, box)
                if lead:
                    bad += 5 * sum(_seg_hits(lead[0], lead[1], t) for t in taken)
                    bad += sum(_seg_near(lead[0], lead[1], q, MARK_R - 0.5) for q in other_pts)
                cost = (bad, _covered(sp, padded, DOT_ROW / 2.0) + dist / 40.0)
                if best is None or cost < best[0]:
                    best = (cost, box, lead)
        _, box, lead = best
        taken.append(_pad(box, HALO_PX))
        lx, ly = inv.transform((box[0], box[1]))
        ax.text(lx, ly, s, size=size, color=INK, ha="left", va="bottom", zorder=9, path_effects=_halo(),
                clip_on=False, gid=f"label:{gid}")
        if lead:
            leaders.append(lead)
            (sx, sy), (tx, ty) = lead
            a0, a1 = inv.transform((sx, sy)), inv.transform((tx, ty))
            ax.plot([a0[0], a1[0]], [a0[1], a1[1]], color=INK2, lw=HAIR, zorder=8, solid_capstyle="butt",
                    gid=f"leader:{gid}")
        placed[gid] = box
    return placed


# ───────────────────────────── the records and the values files ─────────────────────────────

def _record(ctx: Ctx, graph: str, name: str, ids: Sequence[str], files: Sequence[Path], notes: Sequence[str],
            values_file: str) -> dict:
    seen: List[str] = []
    for f in files:
        r = _rel(f)
        if r not in seen:
            seen.append(r)
    out_ids: List[str] = []
    for i in ids:
        if i not in out_ids:
            out_ids.append(i)
    return dict(file=name, graph=graph, symbol=ctx.symbol, window=ctx.window, series_ids=";".join(out_ids),
                source_files=";".join(seen), notes=" ".join(notes), values_file=values_file)


def _vline(item: str, ln: Line, **kw) -> dict:
    """A values row of a drawn series."""
    r = dict(item=item, series_id=ln.series_id, label=ln.label, group=ln.kind, role=ln.role, family=ln.family,
             final_usd=_fmt(ln.final, 2), curve_last_usd=_fmt(ln.end, 2) if ln.drawn else "", cagr_pct=_fmt(ln.cagr),
             max_dd_pct=_fmt(ln.ddp), dd_marks=ln.dd_marks, growth_dd=_fmt(ln.rdd, 6))
    r.update(kw)
    return r


def _vrow(item: str, r, group: str, **kw) -> dict:
    """A values row of an account row of the source."""
    out = dict(item=item, series_id=r.series_id, label=r.label, group=group, role=r.role, family=r.family,
               final_usd=_fmt(r.final, 2), cagr_pct=_fmt(r.cagr), max_dd_pct=_fmt(r.ddp), dd_marks=r.dd_marks,
               growth_dd=_fmt(r.rdd, 6))
    out.update(kw)
    return out


def _write_values(out: Path, name: str, rows: List[dict]) -> str:
    """``<name>.csv`` next to the PNG: the values it plots (VALUES_COLS)."""
    vname = name[:-4] + ".csv"
    with open(Path(out) / vname, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=VALUES_COLS, lineterminator="\n")
        wr.writeheader()
        for r in rows:
            wr.writerow({k: r.get(k, "") for k in VALUES_COLS})
    return vname


def _featured_text(ctx: Ctx) -> str:
    if ctx.by_role:
        return (f"the source's {ctx.how} (roles finalist and champion; finalists first, then by growth ÷ DD on "
                "this window)")
    return (f"the source has no finalist or champion, so its best {len(ctx.featured)} account rows by growth ÷ "
            f"DD (CAGR % ÷ max DD %, the comparison page's ranking: x1.0, unit rule, with a curve)")


def _why_no_featured(ctx: Ctx) -> str:
    if ctx.featured:
        return "no featured series has a curve on this window"
    return ("no featured series (no finalist or champion, and no ranked row with a curve: unit rule, a CAGR and a "
            "max DD)")


def _against(ctx: Ctx) -> str:
    parts = (["the bots' designs"] if any(ln.drawn for ln in ctx.designs) else []) + \
            (["buy-and-hold"] if any(ln.drawn for ln in ctx.bhs) else [])
    return (" against " + " and ".join(parts)) if parts else ""


# ───────────────────────────── 1. equity ─────────────────────────────

def _end_picks(lines: List[Line], ax) -> List[Line]:
    """The lines whose final equity is printed at their end: at most END_LABELS, in this order of priority: the first
    featured, the bots' best design, buy-and-hold fully invested, the other featured, the bases, the other designs and
    buy-and-hold lines; a line whose end lies within END_GAP px of an end already printed is skipped."""
    feat = [ln for ln in lines if ln.kind == "featured"]
    des = sorted((ln for ln in lines if ln.kind == "design"), key=lambda ln: (-ln.end, ln.label))
    bas = [ln for ln in lines if ln.kind == "base"]
    bhs = [ln for ln in lines if ln.kind == "bh"]
    pick: List[Line] = []
    ends: List[Tuple[float, float]] = []
    for ln in feat[:1] + des[:1] + bhs[:1] + feat[1:] + bas + des[1:] + bhs[1:]:
        if len(pick) >= END_LABELS:
            break
        p = ax.transData.transform((float(ln.x[-1]), float(ln.y[-1])))
        if any(math.hypot(p[0] - q[0], p[1] - q[1]) < END_GAP for q in ends):
            continue
        pick.append(ln)
        ends.append((float(p[0]), float(p[1])))
    return pick


def _end_sentence(picks: Optional[List[Line]], lines: List[Line]) -> str:
    """The note's sentence on the printed ends, naming the lines they belong to."""
    if picks is None:
        return "Printed at the line ends: the final equity of some lines; the legend gives every line's."
    s = "Printed at the right, at each line's end dot: the final equity of " + "; ".join(
        _clip(ln.label, 40) for ln in picks)
    if len(picks) < len(lines):                      # some ends left to the legend
        s += (f" (at most {END_LABELS} ends are printed, and none within {END_GAP:.0f} px of one already printed); "
              "the legend gives every line's final equity")
    return s + "."


def _end_labels(cv: Canvas, ax, lines: List[Line]) -> None:
    """An end dot on each line and its final equity in a column right of the plot; a hairline leader where the label
    had to move away from its line's end."""
    bb = cv.extent(ax)
    pts = []
    for ln in lines:
        x, y = float(ln.x[-1]), float(ln.y[-1])
        ax.plot([x], [y], ls="none", marker="o", ms=8 * PX * 1.1, mfc=ln.colour, mec=SURFACE, mew=2 * PX,
                zorder=7, clip_on=False, gid=f"enddot:{ln.series_id}")
        px, py = ax.transData.transform((x, y))
        pts.append((float(py), float(px), usd(y), ln.series_id))
    th = cv.measure("$0,9", 9.5)[1]
    order = sorted(range(len(pts)), key=lambda i: (pts[i][0], pts[i][2], pts[i][3]))
    got = _spread([pts[i][0] for i in order], th + 6.0, bb.y0 + th / 2, bb.y1 + th / 2)
    xl = bb.x1 + 24.0
    for k, i in enumerate(order):
        py, px, s, sid = pts[i]
        y = got[k]
        cv.text(xl, y, s, size=9.5, color=INK, va="center", ha="left", gid=f"end:{sid}")
        if abs(y - py) > 2.0 or px < bb.x1 - 3.0:
            cv.fig.add_artist(Line2D([(px + 6.0) / cv.W, (xl - 5.0) / cv.W], [py / cv.H, y / cv.H],
                                     transform=cv.fig.transFigure, color=AXIS, lw=HAIR, zorder=6,
                                     gid=f"endleader:{sid}"))


def _legend_label(ln: Line) -> Tuple[str, str]:
    """(text, tail): the legend entry of a line, its tail the final equity (kept when the entry is shortened)."""
    s = ln.label
    if ln.kind == "featured":
        s = f"{s} · {ln.role}" + (f", exam {ln.exam}" if ln.exam else "")
    elif ln.kind == "base":
        s = f"{s} · base"
    return _clip(s, 90), f" · {usd(ln.end)}"


def draw_equity(ctx: Ctx, out: Path, log: Callable[[str], None]) -> Optional[dict]:
    name = f"equity_{ctx.symbol}_{wfile(ctx.window)}.png"
    lines = ctx.eq_lines
    feat = [ln for ln in lines if ln.kind == "featured"]
    if not feat:
        log(f"{ctx.tag}: {name} skipped: {_why_no_featured(ctx)}")
        return None
    left_out = [ln for ln in ctx.featured if ln.drawn][len(feat):]
    values = np.concatenate([ln.y[np.isfinite(ln.y)] for ln in lines])
    lo, hi = float(values.min()), float(values.max())
    log_scale = lo > 0 and hi / lo > LOG_RATIO
    scale = "log" if log_scale else "linear"
    title = f"{ctx.sym}, {ctx.window}: {ctx.short}'s {ctx.how}{_against(ctx)}"
    subtitle = (f"Equity of $2,000 accounts at the end of each UTC day, x1.0 costs (the broker's spread), account "
                f"basis. {ctx.wtext}.")
    head = [f"Featured: {_featured_text(ctx)}."]
    if left_out:
        head.append(f"This graph draws the first {len(feat)} of the {len(feat) + len(left_out)} featured series with a "
                    f"curve (more lines of one colour would not read; --equity-top {ctx.equity_top}); not drawn here: "
                    + "; ".join(_clip(ln.label, 40) for ln in left_out)
                    + " (they are in the drawdown and risk/return graphs).")
    head += ctx.notes + ctx.curve_notes + [
        f"The y axis is {scale}" + (f" (the lines span {hi / lo:,.0f}x, more than {LOG_RATIO:.0f}x)." if log_scale
                                    else f" (the lines span {hi / lo:,.1f}x)." if lo > 0 else ".")]
    tail = ["The grey line is the $2,000 start.", _source_note(ctx.files["equity"])]

    def keys(kind):
        return [(_handle(ln), _legend_label(ln)) for ln in lines if ln.kind == kind]
    feat_title = f"{_cap(ctx.short)}: {ctx.how}" + (f", the first {len(feat)}" if left_out else "")
    groups = [(feat_title, keys("featured")), (f"{_cap(ctx.short)}: bases", keys("base")),
              (ctx.designs_title, keys("design")), ("Buy and hold", keys("bh"))]

    def build(picks: Optional[List[Line]]):
        cv = Canvas("equity")
        cv.header(title, subtitle)
        cv.note(" ".join(head + [_end_sentence(picks, lines)] + tail))
        cv.legends(groups)
        right = 24.0 + max(cv.measure(usd(ln.end), 9.5)[0] for ln in lines) + 22.0
        ax = cv.axes(left=132.0, right=right)
        _quiet(ax, "y")
        order = ([ln for ln in lines if ln.kind == "bh"] + [ln for ln in lines if ln.kind == "design"]
                 + [ln for ln in lines if ln.kind == "base"] + feat[::-1])
        for z, ln in enumerate(order):
            ax.plot(ln.x, ln.y, color=ln.colour, lw=LINE, ls=ln.dash or "-", marker=ln.marker,
                    markevery=0.07 if ln.marker else None, ms=8 * PX, mfc=ln.colour, mec=SURFACE, mew=2 * PX,
                    zorder=3 + z * 0.01, solid_capstyle="round", dash_capstyle="round", gid=ln.series_id)
        ax.axhline(ACCOUNT, color=AXIS, lw=HAIR, zorder=2, gid="start")
        if log_scale:
            ax.set_yscale("log")
            ax.set_ylim(lo / 1.08, hi * 1.08)
            ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 2.0, 5.0)))
            ax.yaxis.set_minor_locator(NullLocator())
        else:
            a, b = min(lo, ACCOUNT), max(hi, ACCOUNT)
            pad = (b - a) * 0.05 or 100.0
            ax.set_ylim(a - pad, b + pad)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
        ax.yaxis.set_major_formatter(_usd_formatter(ax.get_ylim()[1] >= 10000))
        ax.set_ylabel(f"Equity of the $2,000 account (USD, {scale} scale)", labelpad=10)
        cv.fit_left(ax)
        _date_axis(ax, *_xspan(ctx), cv.extent(ax).width, cv)
        return cv, ax

    # the note names the printed ends, and which ends are printed depends on the layout: build until they agree
    picks: Optional[List[Line]] = None
    for _ in range(3):
        cv, ax = build(picks)
        got = _end_picks(lines, ax)
        if picks is not None and [ln.series_id for ln in got] == [ln.series_id for ln in picks]:
            break
        picks = got
    else:
        cv, ax = build(picks)
    _end_labels(cv, ax, picks)
    cv.save(Path(out) / name)
    printed = {ln.series_id for ln in picks}
    vals = [_vline("line", ln, key=ln.style_name, x=str(ln.days[-1]), y=_fmt(ln.end, 2),
                   notes="end printed" if ln.series_id in printed else "") for ln in lines]
    vname = _write_values(out, name, vals)
    log(f"{ctx.tag}: wrote {name} ({len(lines)} lines, {scale} y axis)")
    return _record(ctx, "equity", name, [ln.series_id for ln in lines], ctx.files["equity"],
                   [f"y axis {scale}."] + ([f"{len(left_out)} featured not drawn (--equity-top {ctx.equity_top})."]
                                           if left_out else []) + ctx.notes + ctx.curve_notes, vname)


# ───────────────────────────── 2. drawdown ─────────────────────────────

def draw_drawdown(ctx: Ctx, out: Path, log: Callable[[str], None]) -> Optional[dict]:
    name = f"drawdown_{ctx.symbol}_{wfile(ctx.window)}.png"
    lines = ctx.lines
    if not any(ln.kind == "featured" for ln in lines):
        log(f"{ctx.tag}: {name} skipped: {_why_no_featured(ctx)}")
        return None
    dds = [drawdown_pct(ln.y) for ln in lines]
    deep = [int(np.nanargmin(dd)) for dd in dds]
    n = len(lines)
    ncols = n if n <= 3 else (3 if n <= 12 else 4)
    nrows = math.ceil(n / ncols)
    cv = Canvas("drawdown")
    with_bases = " and bases" if any(ln.kind == "base" for ln in lines) else ""
    cv.header(f"{ctx.sym}, {ctx.window}: how far each account fell below its running peak (daily closes)",
              f"{_cap(ctx.short)}'s {ctx.how}{with_bases}{_against(ctx)}; $2,000 accounts at x1.0, account basis. "
              f"{ctx.wtext}.")
    marks = sorted({ln.dd_marks for ln in lines if ln.dd_marks})
    deeper = [ln for ln, dd, i in zip(lines, dds, deep) if math.isfinite(ln.ddp) and -float(dd[i]) > ln.ddp + 0.05]
    deeper_ids = {ln.series_id for ln in deeper}
    notes = ["Drawdown = how far the equity at a daily close sits below its highest daily close so far, in %, from "
             "the contract's daily curves. Daily closes miss the intraday lows, so it is usually shallower than the "
             f"max DD in the metrics, which the studies measure on finer marks ({', '.join(marks) or 'their own'}): "
             "each panel heading gives the deepest daily close and the metrics' max DD with its marks. Shared "
             "scales; the dot marks the deepest daily close."]
    if deeper:
        notes.append("Deeper at a daily close than its max DD: " + "; ".join(
            f"{_clip(ln.label, 30)} ({_run_note(ln.row_notes)})" for ln in deeper)
            + ": the row's max DD and its curve come from different runs.")
    notes += ctx.notes + ctx.curve_notes + [_source_note(ctx.files["drawdown"])]
    cv.note(" ".join(notes))
    keys = []
    if any(ln.kind == "featured" for ln in lines):
        keys.append((Line2D([0, 1], [0, 0], color=ctx.featured[0].colour, lw=LINE),
                     f"{_cap(ctx.short)}: {ctx.how}{with_bases}"))
    if any(ln.kind == "design" for ln in lines):
        keys.append((Line2D([0, 1], [0, 0], color=ctx.bots, lw=LINE), ctx.designs_title))
    if any(ln.kind == "bh" for ln in lines):
        keys.append((Line2D([0, 1], [0, 0], color=INK, lw=LINE), "Buy and hold"))
    cv.legends([(None, keys)], ncols=len(keys))
    left, right, hgap, vgap = 100.0, 30.0, 34.0, 18.0
    top_px, bot_px = cv.H - cv.top + 8.0, cv.bottom + 30.0
    pw = (cv.W - left - right - (ncols - 1) * hgap) / ncols
    # each panel's second heading line, wrapped (never cut) to the panel's width; the room above every panel is that
    # of the tallest heading, so the panels stay aligned, and a panel's title sits right above its own lines
    subs = []
    for ln, dd, i in zip(lines, dds, deep):
        why = _run_note(ln.row_notes) if ln.series_id in deeper_ids else ""
        marks_txt = f"{ln.dd_marks or 'own'}, {why}" if why else f"{ln.dd_marks or 'own'} marks"
        sub = (f"daily close {_pct(float(dd[i]))} · max DD {_pct(-ln.ddp)} ({marks_txt})"
               if math.isfinite(ln.ddp) else f"daily close {_pct(float(dd[i]))} · no max DD in the metrics")
        subs.append((cv.wrap(sub, 8.0, pw), why))
    line_h = cv.measure("Bg", 8.0)[1] * 1.2
    title_h = 44.0 + max(t.count("\n") for t, _ in subs) * line_h
    ph = (top_px - bot_px - nrows * title_h - (nrows - 1) * vgap) / nrows
    deepest = min(float(np.nanmin(d)) for d in dds)
    ylo = min(deepest * 1.1, -1.0)
    yhi = -ylo * 0.05
    x0, x1 = _xspan(ctx)
    vals = []
    for k, (ln, dd, i, (sub, why)) in enumerate(zip(lines, dds, deep, subs)):
        r, c = divmod(k, ncols)
        bx = left + c * (pw + hgap)
        by = top_px - (r + 1) * (title_h + ph) - r * vgap
        ax = cv.fig.add_axes([bx / cv.W, by / cv.H, pw / cv.W, ph / cv.H])
        ax.set_gid(ln.series_id)
        _quiet(ax, "y")
        ax.spines["bottom"].set_visible(False)
        ax.fill_between(ln.x, dd, 0.0, color=ln.colour, alpha=0.10, lw=0, zorder=2)
        ax.plot(ln.x, dd, color=ln.colour, lw=LINE, zorder=3, solid_capstyle="round", gid=f"dd:{ln.series_id}")
        ax.axhline(0.0, color=AXIS, lw=HAIR, zorder=2)
        ax.plot([ln.x[i]], [dd[i]], ls="none", marker="o", ms=8 * PX * 1.1, mfc=ln.colour, mec=SURFACE, mew=2 * PX,
                zorder=4, clip_on=False, gid=f"deepest:{ln.series_id}")
        ax.set_ylim(ylo, yhi)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
        ax.yaxis.set_major_formatter(_pct_formatter(0))
        _date_axis(ax, x0, x1, pw, cv, 8.5)
        ax.tick_params(axis="y", labelleft=(c == 0), labelsize=8.5)
        dated = k + ncols >= n                 # the lowest panel of its column carries the dates
        ax.tick_params(axis="x", labelbottom=dated, length=3 if dated else 0, labelsize=8.5)
        head = ln.label + (f" · {ln.role}" if ln.kind == "featured" else " · base" if ln.kind == "base" else "")
        ax.annotate(cv.fit(head, 9.0, pw), (0.0, 1.0), xycoords="axes fraction",
                    xytext=(0, (23 + sub.count("\n") * line_h) * PX),
                    textcoords="offset points", size=9.0, color=INK, ha="left", va="bottom", annotation_clip=False,
                    gid=f"head:{ln.series_id}")
        ax.annotate(sub, (0.0, 1.0), xycoords="axes fraction", xytext=(0, 4 * PX), textcoords="offset points",
                    size=8.0, color=INK2, ha="left", va="bottom", annotation_clip=False, linespacing=1.2,
                    gid=f"sub:{ln.series_id}")
        vals.append(_vline("panel", ln, daily_close_dd_pct=_fmt(float(dd[i])), x=str(ln.days[i]),
                           y=_fmt(float(dd[i])), notes=f"max DD and curve from different runs ({why})" if why else ""))
    mid = (top_px + bot_px) / 2.0
    cv.text(30.0, mid, "Below the running peak (%, daily closes)", rotation=90, size=9.0, color=INK2, va="center",
            ha="center")
    cv.save(Path(out) / name)
    vname = _write_values(out, name, vals)
    log(f"{ctx.tag}: wrote {name} ({n} panels)")
    return _record(ctx, "drawdown", name, [ln.series_id for ln in lines], ctx.files["drawdown"],
                   ctx.notes + ctx.curve_notes, vname)


# ───────────────────────────── 3. risk / return ─────────────────────────────

def _top_cut(ys: Sequence[float]) -> float:
    """The page's rule (scatterRanges): up to three values whose gap above the next is more than twice the range of
    the values below them go on the top edge; the cut sits 10% of that range above the highest of the rest."""
    v = sorted((y for y in ys if math.isfinite(y)), reverse=True)
    if len(v) < 2:
        return math.inf
    lo, k = v[-1], 0
    while k < 3 and k + 1 < len(v) and v[k] - v[k + 1] > 2 * max(v[k + 1] - min(lo, 0.0), 1e-9):
        k += 1
    top = v[k]
    return top + (top - min(lo, 0.0)) * 0.1 if k > 0 else math.inf


def _wiped_text(wip: pd.DataFrame) -> str:
    """'1 wiped (max DD 99.8%, CAGR −69.8%)', from the rows themselves."""
    return f"{len(wip)} wiped (max DD {_span_text(wip.ddp, _pct)}, CAGR {_span_text(wip.cagr, _pct)})"


def _diagonal_label(cv: Canvas, ax, t_end: float, marks: Sequence, soft: np.ndarray) -> Optional[tuple]:
    """'growth ÷ DD = 1' along the diagonal, at the first place from the top-right end down that stays inside the plot
    and off the labelled marks (and covers the fewest dots); returns its halo-padded box in px."""
    p0, p1 = ax.transData.transform((0.0, 0.0)), ax.transData.transform((1.0, 1.0))
    ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    bb = cv.extent(ax)
    kw = dict(xytext=(0, 4), textcoords="offset points", rotation=ang, rotation_mode="anchor", ha="right",
              va="bottom", size=8.0, color=INK2, zorder=9, path_effects=_halo(2.2), annotation_clip=False,
              gid="label:diagonal")
    best = None
    for k, f in enumerate((0.96, 0.88, 0.8, 0.72, 0.64, 0.56, 0.48, 0.4, 0.32)):
        t = ax.annotate("growth ÷ DD = 1", (t_end * f, t_end * f), **kw)
        e = cv.extent(t)
        t.remove()
        box = (e.x0, e.y0, e.x1, e.y1)
        bad = 1000 if (box[0] < bb.x0 + 2 or box[1] < bb.y0 + 2 or box[2] > bb.x1 - 2 or box[3] > bb.y1 - 2) else 0
        bad += sum(_overlap(_pad(box, 2.0), m) for m in marks)
        cost = (bad, _covered(soft, box, DOT_ROW / 2.0), k)
        if best is None or cost < best[0]:
            best = (cost, f, box)
    if best is None:
        return None
    ax.annotate("growth ÷ DD = 1", (t_end * best[1], t_end * best[1]), **kw)
    return _pad(best[2], 2.2 / PX / 2.0)


def draw_risk_return(ctx: Ctx, out: Path, log: Callable[[str], None]) -> Optional[dict]:
    name = f"risk_return_{ctx.symbol}_{wfile(ctx.window)}.png"
    refs = ctx.ref_ids()
    rows = ctx.rows[~ctx.rows.series_id.isin(refs)]
    ok = rows[rows.cagr.notna() & rows.ddp.notna()]
    if not len(ok):
        log(f"{ctx.tag}: {name} skipped: no account row at x1.0 with both a CAGR and a max DD on this window")
        return None
    lacking = len(rows) - len(ok)
    is_w = ok.wiped.astype(str) == "1"
    live, wip = ok[~is_w], ok[is_w]
    liveset, wipset = set(live.series_id), set(wip.series_id)
    feat = [ln for ln in ctx.featured if ln.series_id in liveset]
    bases = [ln for ln in ctx.bases if ln.series_id in liveset]
    keyed_ids = {ln.series_id for ln in feat + bases}
    des = [ln for ln in ctx.designs if math.isfinite(ln.cagr) and math.isfinite(ln.ddp)]
    bhs = [ln for ln in ctx.bhs if math.isfinite(ln.cagr) and math.isfinite(ln.ddp)]
    # the scale comes from the accounts that were not wiped and the references; wiped accounts sit on the bottom-right
    # corner of the frame, off the scale, when they would stretch it by more than a quarter
    lx = list(live.ddp) + [ln.ddp for ln in des + bhs]
    ly = list(live.cagr) + [ln.cagr for ln in des + bhs]
    cut = _top_cut(ly)
    corner = False
    if len(wip) and lx:
        x_hi, y_lo = max(lx), min(min(ly), 0.0)
        y_hi = max(min(max(ly), cut), 0.0)
        corner = bool(wip.ddp.max() > x_hi + 0.25 * max(x_hi, 1.0)
                      or wip.cagr.min() < y_lo - 0.25 * max(y_hi - y_lo, 1.0))
    xs = lx + ([] if corner else list(wip.ddp))
    ys = [min(y, cut) for y in ly] + ([] if corner else list(wip.cagr))
    keyed = len(feat) + len(bases) + len(des) + len(bhs) > DIRECT_NAMES
    feat_w = [ln for ln in ctx.featured if ln.series_id in wipset]
    wtext = _wiped_text(wip) if len(wip) else ""
    cv = Canvas("risk_return")
    cv.header(f"{ctx.sym}, {ctx.window}: CAGR against max drawdown for every {ctx.short} account "
              f"({len(ok):,} rows)",
              f"Account basis, $2,000 at x1.0 costs; max DD on each row's own marks. {ctx.wtext}.")
    notes = [f"Each dot is one account row of {ctx.short} at x1.0 on this window ({len(ok):,}); the "
             + ("numbered ones (keyed in the legend)" if keyed else "labelled ones")
             + f" are the featured series: {_featured_text(ctx)}."]
    if bases:
        notes.append(f"Rings{', lettered,' if keyed else ''} are the source's base rows (role base).")
    if len(wip):
        notes.append(f"{wtext}: " + ("off the scale, marked by the cross on the bottom-right corner of the frame."
                                     if corner else "crosses."))
    if lacking:
        notes.append(f"{lacking} row{'s' if lacking > 1 else ''} without a CAGR or a max DD are not drawn.")
    n_off = sum(1 for y in ly if y > cut)
    if n_off:
        notes.append(f"{n_off} point{'s' if n_off > 1 else ''} far above the rest sit on the top edge as triangles "
                     "(the page's rule), labelled with the CAGR.")
    if any(ok.cagr_derived):
        notes.append(f"{int(ok.cagr_derived.sum())} CAGR values are computed from the curve's last equity (the "
                     "source left them blank), as the page does.")
    notes.append(_marks_text(ctx, ok.dd_marks, des, bhs) + " The grey diagonal is growth ÷ DD = 1 (CAGR % equal to "
                 "max DD %); above it, a year's growth beats the worst fall.")
    notes += ctx.notes + [_source_note(ctx.files["risk_return"])]
    cv.note(" ".join(notes))
    col = ctx.colour
    feat_key = Line2D([], [], ls="none", marker="o", ms=DOT_KEY * PX, mfc=col, mec=SURFACE, mew=2 * PX)
    ring_key = Line2D([], [], ls="none", marker="o", ms=DOT_KEY * PX, mfc=SURFACE, mec=col, mew=2 * PX)
    ctx_rows = live[~live.series_id.isin(keyed_ids) & (live.cagr <= cut)]       # the context dots
    pts_keys = ([(Line2D([], [], ls="none", marker="o", ms=DOT_ROW * PX, mfc=col, mec="none", alpha=0.45),
                  f"{_cap(ctx.short)}: every other account row at x1.0 ({len(ctx_rows):,})")] if len(ctx_rows) else [])
    if feat and not keyed:
        pts_keys.append((feat_key, f"{_cap(ctx.short)}: {ctx.how} (labelled)"))
    if bases and not keyed:
        pts_keys.append((ring_key, f"{_cap(ctx.short)}: bases (labelled)"))
    if len(wip):
        pts_keys.append((Line2D([], [], ls="none", marker="x", ms=10 * PX, mec=col, mew=LINE * 0.8),
                         "Wiped account" + (" (off the scale: the corner cross)" if corner else "")))
    if n_off:
        off_col = col if (live.cagr > cut).any() else next(ln.colour for ln in des + bhs if ln.cagr > cut)
        pts_keys.append((Line2D([], [], ls="none", marker="^", ms=DOT_KEY * PX, mfc=off_col, mec=SURFACE, mew=2 * PX),
                         "Far above the rest (on the top edge, in its own colour)"))
    groups = [("Points", pts_keys), ("References", [])]
    if keyed and feat:
        groups.append((f"{_cap(ctx.short)}: {ctx.how}, numbered",
                       [(feat_key, f"{ln.key or '?'}   {ln.label} · {ln.role}" + (f", exam {ln.exam}" if ln.exam
                                                                                    else ""))
                        for ln in sorted(feat, key=lambda ln: (int(ln.key) if ln.key.isdigit() else 999, ln.label))]))
    if keyed and bases:
        groups.append((f"{_cap(ctx.short)}: bases, lettered",
                       [(ring_key, f"{ln.key or '?'}   {ln.label}") for ln in sorted(bases, key=lambda ln: ln.key)]))
    ref_keys = []
    if des:
        ref_keys.append((Line2D([], [], ls="none", marker="s", ms=DOT_KEY * PX, mfc=ctx.bots, mec=SURFACE,
                                mew=2 * PX), ctx.designs_title))
    if bhs:
        ref_keys.append((Line2D([], [], ls="none", marker="D", ms=DOT_BH * PX, mfc=INK, mec=SURFACE, mew=2 * PX),
                         "Buy and hold"))
    ref_keys.append((Line2D([0, 1], [0, 0], color=AXIS, lw=LINE * 0.75), "Growth ÷ DD = 1"))
    groups[1] = ("References", ref_keys)
    cv.legends(groups)
    ax = cv.axes(left=130.0, right=36.0, below=74.0)
    _quiet(ax, "both")
    xmax = max(xs) * 1.06 if xs and max(xs) > 0 else 1.0
    ylo, yhi = min(min(ys), 0.0), max(max(ys), 0.0)
    pad = (yhi - ylo) * 0.06 or 1.0
    ax.set_xlim(0.0, xmax)
    ax.set_ylim(ylo - pad, yhi + pad)
    ax.xaxis.set_major_formatter(_pct_formatter(0))
    ax.yaxis.set_major_formatter(_pct_formatter(0))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7, steps=[1, 2, 2.5, 5, 10]))
    ax.set_xlabel("Max drawdown (% below the running peak, on each row's own marks)", labelpad=8)
    ax.set_ylabel("CAGR (% a year)", labelpad=10)
    cv.fit_left(ax)
    big = max(xmax, yhi + pad) * 2
    ax.plot([0.0, big], [0.0, big], color=AXIS, lw=LINE * 0.75, zorder=1, gid="diagonal")
    ax.axhline(0.0, color=AXIS, lw=HAIR, zorder=1)
    vals: List[dict] = []
    if len(ctx_rows):
        ax.scatter(ctx_rows.ddp, ctx_rows.cagr, s=(DOT_ROW * PX) ** 2, c=col, alpha=0.45, linewidths=0, zorder=2,
                   gid="rows")
        vals += [_vrow("point", r, "row", x=_fmt(r.ddp), y=_fmt(r.cagr)) for r in ctx_rows.itertuples(index=False)]
    corner_xy = (ax.get_xlim()[1], ax.get_ylim()[0])
    wip_soft: List[Tuple[float, float]] = []
    if len(wip):
        if corner:
            ax.scatter([1.0], [0.0], transform=ax.transAxes, marker="x", s=(10 * PX) ** 2, c=col,
                       linewidths=LINE * 0.8, zorder=7, clip_on=False, gid="wiped")
            vals += [_vrow("point", r, "wiped", x=_fmt(corner_xy[0]), y=_fmt(corner_xy[1]),
                           notes="off the scale: the cross on the bottom-right corner of the frame")
                     for r in wip.itertuples(index=False)]
        else:
            ax.scatter(wip.ddp, wip.cagr, s=(10 * PX) ** 2, marker="x", c=col, linewidths=LINE * 0.8, zorder=3,
                       gid="wiped")
            vals += [_vrow("point", r, "wiped", x=_fmt(r.ddp), y=_fmt(r.cagr)) for r in wip.itertuples(index=False)]
            fw = {ln.series_id for ln in feat_w}
            wip_soft = [(r.ddp, r.cagr) for r in wip.itertuples(index=False) if r.series_id not in fw]
    bases_on = [ln for ln in bases if ln.cagr <= cut]
    if bases_on:
        ax.scatter([ln.ddp for ln in bases_on], [ln.cagr for ln in bases_on], s=(DOT_KEY * PX) ** 2,
                   facecolors=SURFACE, edgecolors=col, linewidths=2 * PX, zorder=4, gid="bases")
    feat_on = [ln for ln in feat if ln.cagr <= cut]
    if feat_on:
        ax.scatter([ln.ddp for ln in feat_on], [ln.cagr for ln in feat_on], s=(DOT_KEY * PX) ** 2, c=col,
                   edgecolors=SURFACE, linewidths=2 * PX, zorder=5, gid="featured")
    for lns, mk, colour, size, gid in ((des, "s", ctx.bots, DOT_KEY, "designs"), (bhs, "D", INK, DOT_BH, "bhs")):
        keep = [ln for ln in lns if ln.cagr <= cut]
        if keep:
            ax.scatter([ln.ddp for ln in keep], [ln.cagr for ln in keep], s=(size * PX) ** 2, marker=mk, c=colour,
                       edgecolors=SURFACE, linewidths=2 * PX, zorder=6, clip_on=False, gid=gid)
    for ln in feat + bases + des + bhs:
        vals.append(_vline("point", ln, key=ln.key if ln.kind in ("featured", "base") and keyed else "",
                           x=_fmt(ln.ddp), y=_fmt(min(ln.cagr, cut)),
                           notes="far above the rest: on the top edge" if ln.cagr > cut else ""))
    # a point far above the rest sits on the top edge as a triangle in its own colour (the page's rule)
    up_rows = live[(live.cagr > cut) & ~live.series_id.isin(keyed_ids)]
    up = ([(x, col) for x in up_rows.ddp] + [(ln.ddp, ln.colour) for ln in feat + bases if ln.cagr > cut]
          + [(ln.ddp, ln.colour) for ln in des + bhs if ln.cagr > cut])
    if up:
        ax.scatter([x for x, _ in up], [cut] * len(up), s=(DOT_KEY * PX) ** 2, marker="^", c=[c for _, c in up],
                   edgecolors=SURFACE, linewidths=2 * PX, zorder=6, clip_on=False, gid="up")
        vals += [_vrow("point", r, "row", x=_fmt(r.ddp), y=_fmt(cut), notes="far above the rest: on the top edge")
                 for r in up_rows.itertuples(index=False)]
    # the labels: the corner's first, then the references' names, the top edge's, the featured and the bases
    items: List[Tuple[float, float, str, str]] = []
    if len(wip) and corner:
        items.append((corner_xy[0], corner_xy[1], wtext, "wiped"))
    for ln in des + bhs:
        items.append((ln.ddp, min(ln.cagr, cut), f"{ln.label} ({_pct(ln.cagr, 0)})" if ln.cagr > cut else ln.label,
                      ln.series_id))
    for r in up_rows.itertuples(index=False):
        items.append((r.ddp, cut, f"{r.label} ({_pct(r.cagr, 0)})", r.series_id))
    for ln in feat + bases:
        s = (ln.key or ln.label) if keyed else ln.label
        items.append((ln.ddp, min(ln.cagr, cut), f"{s} ({_pct(ln.cagr, 0)})" if ln.cagr > cut else s, ln.series_id))
    if not corner:
        for ln in feat_w:
            s = (ln.key or ln.label) if keyed else ln.label
            items.append((ln.ddp, ln.cagr, f"{s} (wiped)", ln.series_id))
    soft = np.asarray([(r.ddp, r.cagr) for r in ctx_rows.itertuples(index=False)] + wip_soft, float).reshape(-1, 2)
    soft_px = (np.asarray(ax.transData.transform(soft), float).reshape(-1, 2) if len(soft) else np.zeros((0, 2)))
    marks_px = [(px - MARK_R, py - MARK_R, px + MARK_R, py + MARK_R)
                for px, py in (ax.transData.transform((x, y)) for x, y, _, _ in items)]
    taken = []
    t_end = min(xmax, yhi + pad)
    if t_end > 0:
        box = _diagonal_label(cv, ax, t_end, marks_px, soft_px)
        if box:
            taken.append(box)
    _place_labels(cv, ax, items, soft=soft, taken=taken, size=8.5)
    cv.save(Path(out) / name)
    vname = _write_values(out, name, vals)
    log(f"{ctx.tag}: wrote {name} ({len(ok)} rows" + (f", {len(wip)} wiped in the corner" if corner else "") + ")")
    ids = ([ln.series_id for ln in feat + bases] + [ln.series_id for ln in des + bhs]
           + sorted(set(ok.series_id) - keyed_ids))
    return _record(ctx, "risk_return", name, ids, ctx.files["risk_return"],
                   ([f"{lacking} rows without a CAGR or max DD not drawn."] if lacking else [])
                   + ([f"{wtext}: off the scale, on the bottom-right corner."] if corner else [])
                   + ctx.notes, vname)


# ───────────────────────────── 4. families ─────────────────────────────

def _bar_path(y: float, v: float, half: float, rx: float, ry: float) -> MPath:
    """A horizontal bar from 0 to v, ``half`` its half thickness, with its data end rounded (radius rx by ry in data
    units) and square at the baseline."""
    s = 1.0 if v >= 0 else -1.0
    a = abs(v)
    rx = min(rx, a / 2.0)
    ry = min(ry, half)
    y0, y1 = y - half, y + half
    verts = [(0.0, y0), (s * (a - rx), y0), (s * a, y0), (s * a, y0 + ry), (s * a, y1 - ry), (s * a, y1),
             (s * (a - rx), y1), (0.0, y1), (0.0, y0)]
    codes = [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CURVE3, MPath.CURVE3,
             MPath.LINETO, MPath.CLOSEPOLY]
    return MPath(verts, codes)


def _label_rows(spans: Sequence[Tuple[float, float, float]], gap: float = 24.0) -> List[int]:
    """Rows (0 nearest the plot) for labels set above a plot, each (x0, x1, x of its line) in px, in priority order:
    labels in one row stay ``gap`` px apart, and a label that spans another label's line sits above that label, so the
    line's connector, which rises to its own label, never crosses it. Where two labels span each other's lines, only
    the later is lifted (one connector then crosses)."""
    n = len(spans)
    covers = {(i, j) for i in range(n) for j in range(n)
              if i != j and spans[i][0] - 4.0 <= spans[j][2] <= spans[i][1] + 4.0}
    covers -= {(i, j) for i, j in covers if (j, i) in covers and i < j}
    rows = [0] * n
    for _ in range(4 * n + 4):
        changed = False
        for i in range(n):
            r = max([rows[i]] + [rows[j] + 1 for a, j in covers if a == i])
            while any(rows[k] == r and not (spans[i][1] + gap < spans[k][0] or spans[i][0] > spans[k][1] + gap)
                      for k in range(i)):
                r += 1
            if r != rows[i]:
                rows[i], changed = r, True
        if not changed:
            break
    return rows


def draw_families(ctx: Ctx, out: Path, log: Callable[[str], None]) -> Optional[dict]:
    name = f"families_{ctx.symbol}_{wfile(ctx.window)}.png"
    rows = ctx.rows.assign(family=ctx.rows.family.replace("", "(no family)"))
    cand = ranked(rows, need_curve=False)
    hind = cand.drop_duplicates("family", keep="first").set_index("family", drop=False)   # each family's best row
    by_pick = bool((rows.role == "champion").any())
    bars: List[dict] = []
    if by_pick:
        # each family's pre-registered pick: its finalist, else its champion (the best by growth / DD if several)
        pre = rows[rows.role.isin(FEATURED_ROLES) & rows.rdd.notna()]
        pre = pre.assign(_r=pre.role.map({r: i for i, r in enumerate(FEATURED_ROLES)}), _q=-pre.rdd).sort_values(
            ["_r", "_q", "label", "series_id"], kind="mergesort").drop(columns=["_r", "_q"])
        for r in pre.drop_duplicates("family", keep="first").itertuples(index=False):
            h = hind.loc[r.family] if r.family in hind.index else None
            tick = float(h.rdd) if h is not None and h.series_id != r.series_id else None
            bars.append(dict(family=r.family, row=r, v=float(r.rdd), tick=tick, hrow=h))
        bars.sort(key=lambda b: (-b["v"], b["family"]))
        have = {b["family"] for b in bars}
        bars += [dict(family=f, row=None, v=math.nan, tick=float(h.rdd), hrow=h) for f, h in hind.iterrows()
                 if f not in have]
    else:
        bars = [dict(family=f, row=h, v=float(h.rdd), tick=None, hrow=h) for f, h in hind.iterrows()]
    if not bars:
        log(f"{ctx.tag}: {name} skipped: no unit-rule account row at x1.0 with a growth / DD on this window")
        return None
    counts = rows.groupby("family").size()
    n_all = len(bars)
    dropped = bars[MAX_FAMILIES:]
    bars = bars[:MAX_FAMILIES]
    if dropped:
        log(f"{ctx.tag}: {name}: {len(dropped)} of {n_all} families not drawn (more than {MAX_FAMILIES}): "
            + ", ".join(b["family"] for b in dropped))
    for b in bars:
        b["hollow"] = b["row"] is not None and ctx.elig_rule and str(b["row"].eligible) != "1"
    refs = []
    des = [ln for ln in ctx.designs if math.isfinite(ln.rdd)]
    if des:
        d = sorted(des, key=lambda ln: (-ln.rdd, ln.label))[0]
        refs.append((d.rdd, ctx.bots, None, ("Bots' best design" + (", rebuilt" if ctx.rebuilt else "") + " (",
                                              d.label, f"): {_signed(d.rdd)}"), d.series_id, d))
    bas = [ln for ln in ctx.bases if math.isfinite(ln.rdd)]
    if bas:
        b0 = sorted(bas, key=lambda ln: (-ln.rdd, ln.label))[0]
        refs.append((b0.rdd, ctx.colour, DASHES[1], ("Best base (", b0.label, f"): {_signed(b0.rdd)}"),
                     b0.series_id, b0))
    for ln in ctx.bhs:
        if math.isfinite(ln.rdd):
            refs.append((ln.rdd, INK, ln.dash, ("", ln.label, f": {_signed(ln.rdd)}"), ln.series_id, ln))
    cv = Canvas("families")
    if by_pick:
        cv.header(f"{ctx.sym}, {ctx.window}: growth ÷ DD of each {ctx.short} family's pre-registered pick",
                  "Growth ÷ DD = CAGR % ÷ max DD % (the comparison page's ranking) of the family's finalist, else its "
                  f"champion, at x1.0; the tick is the family's best row on this window, picked in hindsight. "
                  f"{ctx.wtext}.")
    else:
        cv.header(f"{ctx.sym}, {ctx.window}: the best growth ÷ DD in each {ctx.short} family, picked in hindsight",
                  "Growth ÷ DD = CAGR % ÷ max DD % (the comparison page's ranking) of the family's best account row at "
                  "x1.0 on this window: picked in hindsight, not a pre-registered choice. " + f"{ctx.wtext}.")
    if by_pick:
        notes = ["One bar per family (series.csv 'family'): its pre-registered pick (role finalist, else champion); "
                 f"the thin grey tick, where it differs, is the family's best of its rows ranked on this window (unit "
                 "rule, with a CAGR and a max DD), chosen on the data it is scored on, so not a fair bar. A family "
                 "without a finalist or champion shows only its tick. The row's label at the tip, the family's "
                 "account rows on this window in brackets."]
    else:
        notes = [f"One bar per family (series.csv 'family'): its best row among the {len(cand):,} ranked rows (unit "
                 "rule, with a CAGR and a max DD), chosen on the window it is scored on; the row's label at the tip, "
                 "the family's account rows on this window in brackets."]
    if ctx.elig_rule:
        if any(b["hollow"] for b in bars):
            notes.append("Hollow bars: the bar's row is not eligible under the study's own rule.")
    else:
        notes.append("No row of the source is marked eligible, so no bar is hollow.")
    if dropped:
        notes.append(f"{len(dropped)} of {n_all} families are not drawn (more than {MAX_FAMILIES}; listed in the log).")
    if ctx.designs and not des:
        notes.append("No line for the bots' designs: none of their rows on this window has a growth ÷ DD.")
    if any(cand.cagr_derived):
        notes.append("Some CAGR values are computed from the curve's last equity (the source left them blank), as the "
                     "page does.")
    notes.append(_marks_text(ctx, rows.dd_marks, des, [ln for ln in ctx.bhs if math.isfinite(ln.rdd)]))
    notes += [x for x in ctx.notes if "bots' designs" in x or "Buy-and-hold is not" in x]
    notes.append(_source_note(ctx.files["families"]))
    cv.note(" ".join(x for x in notes if x))
    n = len(bars)
    size = 9.0 if n <= 16 else (8.0 if n <= 24 else 7.0)
    ticks = [f"{b['family']} ({int(counts.get(b['family'], 0))})" for b in bars]
    left = max(110.0, max(cv.measure(t, size)[0] for t in ticks) + 34.0)
    th = cv.measure("Bg", 8.5)[1]
    pw = cv.W - left - 30.0                      # the plot's width (cv.axes below): the x scale is known before it

    def tip_labels(ppu: float) -> List[List[Tuple[float, bool, str, float, str]]]:
        """Per bar, its labels as (anchor value, on the right, text, width in px, gid): the bar's value and row next to
        the bar's end and the hindsight tick's value next to the tick; where the tick would meet the row's label, the
        value alone stays at the bar's end and the rest follows the tick; one label after both only where the tick
        is closer than the value's own width."""
        out = []
        for b in bars:
            fam = b["family"]
            if b["row"] is None:
                t = f"{_signed(b['tick'])}  {_clip(b['hrow'].label, 34)}  · no pick: its best row, in hindsight"
                out.append([(b["tick"], b["tick"] >= 0, t, cv.measure(t, 8.5)[0], f"tip:{fam}")])
                continue
            v, tk = b["v"], b["tick"]
            t = f"{_signed(v)}  {_clip(b['row'].label, 34)}" + ("  · not eligible" if b["hollow"] else "")
            w = cv.measure(t, 8.5)[0]
            if tk is None:
                out.append([(v, v >= 0, t, w, f"tip:{fam}")])
                continue
            tt = f"hindsight best {_signed(tk)}"
            vr, tr = v >= 0, tk >= 0
            room = (tk - v) * ppu if vr else (v - tk) * ppu        # px from the bar's end out to the tick
            vt = _signed(v)
            vw = cv.measure(vt, 8.5)[0]
            if vr != tr or room > 8.0 + w + 10.0:
                out.append([(v, vr, t, w, f"tip:{fam}"), (tk, tr, tt, cv.measure(tt, 8.5)[0], f"ticklabel:{fam}")])
            elif room > 8.0 + vw + 10.0:
                rest = f"{t[len(vt):].lstrip()}  · {tt}"
                out.append([(v, vr, vt, vw, f"tip:{fam}"),
                            (tk, tr, rest, cv.measure(rest, 8.5)[0], f"ticklabel:{fam}")])
            else:
                m = f"{t}  · {tt}"
                out.append([(max(v, tk) if vr else min(v, tk), vr, m, cv.measure(m, 8.5)[0], f"tip:{fam}")])
        return out

    ends = []
    for b in bars:
        e = [x for x in (b["v"], b["tick"]) if x is not None and math.isfinite(x)]
        ends.append((max(e), min(e)))
    lo = min([0.0] + [e[1] for e in ends] + [r[0] for r in refs])
    hi = max([0.0] + [e[0] for e in ends] + [r[0] for r in refs])
    if hi - lo <= 0:
        hi = lo + 1.0
    span = hi - lo                               # air beyond the outermost bar or reference line
    hi, lo = (hi + span * 0.04 if hi > 0 else hi), (lo - span * 0.04 if lo < 0 else lo)
    for _ in range(80):                          # room for the tip labels (the gap, the text, its box, some air)
        ppu = pw / (hi - lo)
        labs = [lab for ls in tip_labels(ppu) for lab in ls]
        need_hi = max([hi] + [a + (8.0 + w + 12.0) / ppu for a, r, _, w, _ in labs if r])
        need_lo = min([lo] + [a - (8.0 + w + 12.0) / ppu for a, r, _, w, _ in labs if not r])
        if need_hi <= hi + 1e-9 * (hi - lo) and need_lo >= lo - 1e-9 * (hi - lo):
            break
        hi, lo = need_hi, need_lo
    ppu_x = pw / (hi - lo)
    # the reference lines' labels above the plot: just right of the line (left of it at the right edge, shortened to
    # the room there), in rows that keep them apart and keep every connector off the labels (_label_rows)
    plan = []
    for v, colour, dash, (h0, lab, h1), sid, ln in sorted(refs, key=lambda r: (-r[0], r[3][0] + r[3][1])):
        px = left + (v - lo) * ppu_x
        text = h0 + lab + h1
        w = cv.measure(text, 8.5)[0]
        room_r, room_l = cv.W - cv.MARGIN - (px + 5.0), (px - 5.0) - cv.MARGIN
        if w > room_r and w > room_l:
            lab = cv.fit(lab, 8.5, max(max(room_r, room_l) - cv.measure(h0 + h1, 8.5)[0], 24.0))
            text = h0 + lab + h1
            w = cv.measure(text, 8.5)[0]
        plan.append((v, colour, dash, text, sid, ln, px, px + 5.0 if w <= room_r else px - 5.0 - w, w))
    rows = _label_rows([(q[7], q[7] + q[8], q[6]) for q in plan])
    above = (max(rows) + 1) * (th + 6.0) + 10.0 if plan else 6.0
    ax = cv.axes(left=left, right=30.0, below=74.0, above=above)
    _quiet(ax, "x")
    ax.spines["bottom"].set_visible(False)
    ys = np.arange(n)[::-1].astype(float)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_yticks(ys)
    ax.set_yticklabels(ticks, size=size)
    ax.set_xlim(lo, hi)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 2.5, 5, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, pos=None: ("−" if v < -1e-12 else "") +
                                               f"{abs(v):g}"))
    ax.set_xlabel("Growth ÷ DD (CAGR % ÷ max DD %)" + (" of the family's pick" if by_pick
                                                       else " of the family's best row"), labelpad=8)
    bb = cv.extent(ax)
    ppu_y = bb.height / (n - 0.4 + 0.6)
    thick = min(24.0, ppu_y * 0.62)
    half = thick / 2.0 / ppu_y
    ax.axvline(0.0, color=AXIS, lw=HAIR, zorder=2)
    vals = []
    gap = 8.0 / ppu_x
    for y, b, labs in zip(ys, bars, tip_labels(ppu_x)):
        v = b["v"]
        if b["row"] is not None and v != 0:
            path = _bar_path(y, v, half, 4.0 / ppu_x, 4.0 / ppu_y)
            if b["hollow"]:
                patch = PathPatch(path, facecolor=SURFACE, edgecolor=ctx.colour, lw=LINE * 0.8, zorder=3)
            else:
                patch = PathPatch(path, facecolor=ctx.colour, edgecolor="none", lw=0, zorder=3)
            patch.set_gid(f"bar:{b['family']}")
            ax.add_patch(patch)
        if b["row"] is not None:
            vals.append(_vrow("bar", b["row"], "pick" if by_pick else "best", x=_fmt(v, 6),
                              family=b["family"], notes=("not eligible (hollow)" if b["hollow"] else "")
                              + ("; " if b["hollow"] and by_pick else "")
                              + ("pre-registered pick" if by_pick else "best of the family, in hindsight")))
        if b["tick"] is not None:
            dy = half + 4.0 / ppu_y
            ax.plot([b["tick"], b["tick"]], [y - dy, y + dy], color=INK2, lw=LINE, zorder=5, solid_capstyle="butt",
                    gid=f"tick:{b['family']}")
            vals.append(_vrow("tick", b["hrow"], "best", x=_fmt(b["tick"], 6), family=b["family"],
                              notes="the family's best row on this window, picked in hindsight"))
        for a, r, t, _, gid in labs:
            ax.text(a + gap if r else a - gap, y, t, size=8.5, color=INK, va="center", ha="left" if r else "right",
                    zorder=6, bbox=dict(fc=SURFACE, ec="none", pad=1.5), gid=gid)
    for (v, colour, dash, text, sid, ln, px, x0, w), row in zip(plan, rows):
        ax.axvline(v, color=colour, lw=LINE * 0.8, ls=dash or "-", zorder=4, gid=f"ref:{sid}")
        ty = bb.y1 + 8.0 + row * (th + 6.0)
        cv.text(x0, ty, text, size=8.5, color=INK, va="bottom", ha="left", gid=f"reflabel:{sid}")
        cv.fig.add_artist(Line2D([px / cv.W, px / cv.W], [bb.y1 / cv.H, (ty + th * 0.75) / cv.H],
                                 transform=cv.fig.transFigure, color=colour, lw=HAIR, ls=dash or "-", zorder=4,
                                 gid=f"refline:{sid}"))
        vals.append(_vline("reference", ln, x=_fmt(v, 6)))
    cv.save(Path(out) / name)
    vname = _write_values(out, name, vals)
    log(f"{ctx.tag}: wrote {name} ({n} families)")
    ids = ([b["row"].series_id for b in bars if b["row"] is not None]
           + [b["hrow"].series_id for b in bars if b["tick"] is not None] + [r[4] for r in refs])
    return _record(ctx, "families", name, ids, ctx.files["families"],
                   (["bars: each family's pre-registered pick; ticks: its best row in hindsight."] if by_pick
                    else ["bars: each family's best row, picked in hindsight."])
                   + ([f"{len(dropped)} families not drawn: " + ", ".join(b["family"] for b in dropped)]
                      if dropped else []) + ctx.notes, vname)


DRAW = {"equity": draw_equity, "drawdown": draw_drawdown, "risk_return": draw_risk_return,
        "families": draw_families}


# ───────────────────────────── the run ─────────────────────────────

def draw(source: str, out: Path, data: Path = DATA, windows: Optional[Sequence[str]] = None,
         symbols: Sequence[str] = SYMBOLS, top: int = TOP, log: Callable[[str], None] = print,
         equity_top: int = EQUITY_TOP) -> List[dict]:
    """
    Draw the four graphs of every symbol and every window the source has curves for (``windows``: only these) into
    ``out``, each with its values file, write ``out/graphs.csv`` and return its rows. A graph whose inputs are missing
    is skipped with a log line.
    """
    data, out = Path(data), Path(out)
    if top < 1:
        raise ValueError("--top must be at least 1")
    if equity_top < 1:
        raise ValueError("--equity-top must be at least 1")
    src = Source(source, data)
    if not src.present:
        raise FileNotFoundError(f"{data / (source + '__series.csv')} does not exist: no source {source!r} in {data}")
    f10 = src if source == "final10" else Source("final10", data)
    bh = src if source == "benchmarks" else Source("benchmarks", data)
    slots = page_slots(data)
    have = every = [w for w in src.windows() if src.has_curves(w)]
    if windows is not None:
        for w in windows:
            if w not in have:
                log(f"{source} {w}: skipped: the source has no curve file for this window "
                    f"({src.curve_path(w).name})")
        have = [w for w in have if w in set(windows)]
    for w in src.windows():
        if w not in have and windows is None:
            log(f"{source} {w}: no graphs: the source has no curves on this window")
    # the line keys, the same on every window and whichever windows are drawn: one pass over each window with curves
    # first (it also reads the featured and the bases' curves), then the featured in the order they appear and the
    # bases after them
    keys = {sym: Keys() for sym in symbols}
    m = src.metrics
    for w in every:
        pre = set(src.series.series_id[src.series.role.isin(FEATURED_ROLES + ("base",))])
        pre &= set(m.series_id[(m.window == w) & (m.basis == "account")])
        src.index(w, prefetch=sorted(pre))
        for sym in symbols:
            rows = src.account_rows(w, sym)
            if len(rows) and rows.has_curve.any():
                for sid in featured(_featurable(src, rows), top)[0].series_id:
                    keys[sym].num.setdefault(sid, len(keys[sym].num))
    for sym in symbols:
        seen = set()
        for w in every:
            rows = src.account_rows(w, sym)
            b = rows[rows.role == "base"]
            seen |= set(zip(b.label, b.series_id))
        for _, sid in sorted(seen):
            if sid not in keys[sym].num:
                keys[sym].let.setdefault(sid, len(keys[sym].let))
    out.mkdir(parents=True, exist_ok=True)
    records: List[dict] = []
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        matplotlib.rcParams.update(RC)
        for w in have:
            for sym in symbols:
                ctx = context(src, f10, bh, slots, w, sym, top, log, keys=keys[sym], equity_top=equity_top)
                if ctx is None:
                    continue
                for g in GRAPHS:
                    rec = DRAW[g](ctx, out, log)
                    if rec:
                        records.append(rec)
    with open(out / "graphs.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=GRAPHS_COLS, lineterminator="\n")
        wr.writeheader()
        for r in records:
            wr.writerow(r)
    log(f"{source}: {len(records)} graphs in {out} (index: graphs.csv; each PNG's values in the CSV of its name)")
    return records


def main(argv: Optional[Sequence[str]] = None) -> List[dict]:
    ap = argparse.ArgumentParser(prog="python3 -B -m backtesting.research.study_graphs",
                                 description="PNG graphs of one source of the comparison page's contract files.")
    ap.add_argument("--source", required=True, help="the source id (tradeiq_rsi, tradeiq_2027, bot_filters, ...)")
    ap.add_argument("--out", required=True, type=Path, help="the folder the PNGs and graphs.csv go to")
    ap.add_argument("--data", type=Path, default=DATA, help=f"the contract files (default {_rel(DATA)})")
    ap.add_argument("--windows", default="", help="comma-separated window keys (default: every window with curves)")
    ap.add_argument("--symbols", default=",".join(SYMBOLS), help="comma-separated symbols")
    ap.add_argument("--top", type=int, default=TOP, help=f"featured series per graph (default {TOP})")
    ap.add_argument("--equity-top", type=int, default=EQUITY_TOP,
                    help=f"featured lines in the equity graph (default {EQUITY_TOP})")
    a = ap.parse_args(argv)
    windows = [w.strip() for w in a.windows.split(",") if w.strip()] or None
    symbols = [s.strip() for s in a.symbols.split(",") if s.strip()]
    return draw(a.source, a.out, data=a.data, windows=windows, symbols=symbols, top=a.top, equity_top=a.equity_top)


if __name__ == "__main__":
    main()
