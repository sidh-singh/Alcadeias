"""
The study graphs (``backtesting/research/study_graphs.py``): PNGs of one source of the comparison page's contract files.

Everything runs on synthetic contract files written to a temporary folder by compare_page's own writer, and they pass
compare_page's validator:
* ``final10`` (the bots' designs, a FINAL10 finalist, study 1's rebuilds of two designs on ``bots-holdout``, and a
  design row whose max DD, like FINAL10's 1y tick rows, comes from another run than its curve) and ``benchmarks`` (the
  two buy-and-hold lines), the references;
* two studies: ``tradeiq_2027`` (finalists and champions on 5y and a hold-out where the finalists' order flips; a base;
  a per-lot window without curves; BTC rows without BTC curves on the hold-out; a wiped account that kept $5; a
  finalist whose range needs the log axis) and ``bot_filters`` (no finalist or champion, so the page's ranking picks the
  featured series: a risk-sized row, a row without a curve, a row without a max DD, a row whose CAGR the source left
  blank, a 70-character label and a base; on 1y no row has a max DD, so every graph there is skipped).

The figures are kept as they are saved (``Canvas.save`` patched), and every plotted value is checked against the
contract files read here with pandas: the equity lines, their colours, end labels and legend finals, the date span,
the titles; each drawdown panel and its heading; every scatter point, the wiped corner and its text, the labels (none
overlapping, none outside the plot, each by its point, also in a crowd of twelve); the families' bars, hindsight ticks
and reference lines; the
legends inside the figure. Also: the files drawn (fixed size, PNG, no metadata), graphs.csv and the values files; the
skips and their log lines; the same bytes twice, in this process and in two others with different hash seeds; the
ranking and the featured order; the line keys across windows; the --top and --equity-top cuts; the page's colours
and ink tokens and the colour distances the dataviz validator measures; and no study-2 or study-3 module imported.
"""

from __future__ import annotations

import ast
import csv
import io
import itertools
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest
from matplotlib import colors as mcolors
from matplotlib import dates as mdates
from matplotlib.lines import Line2D

from backtesting.research import compare_page as CP
from backtesting.research import study_graphs as G

REPO = Path(__file__).resolve().parents[1]
WIN = {"5y": ("2021-11-13", "2026-11-13"), "1y": ("2025-11-13", "2026-11-13"),
       "holdout": ("2024-07-01", "2026-11-26"), "dev": ("2019-01-01", "2023-01-01"),
       "bots-holdout": ("2024-07-01", "2026-11-13")}
T2 = "tradeiq_2027"
T3 = "bot_filters"
TIMINGS = ("final equity and max DD are the median of FINAL10's 8 loop timings; the other columns, the curve and its "
           "daily-close DD are its middle (upper-median) timing run")
LONG = "V3-lite + ADX(14) above 20 on the 1-hour chart, both sides, no stop xx"     # 70 characters
SCATTERS = (("risk_return_XAUUSDm_5y.png", "XAUUSDm", "5y"), ("risk_return_BTCUSDm_5y.png", "BTCUSDm", "5y"),
            ("risk_return_XAUUSDm_holdout.png", "XAUUSDm", "holdout"))


# ───────────────────────────── the synthetic contract files ─────────────────────────────

def _years(w: str) -> float:
    a, z = WIN[w]
    return (pd.Timestamp(z) - pd.Timestamp(a)).days * 86400 / CP.YEAR_S


def _cagr(final: float, w: str) -> float:
    return ((final / 2000.0) ** (1.0 / _years(w)) - 1.0) * 100.0 if final > 0 else -100.0


def _curve(sid: str, w: str, final: float, dip: float, k: int, wiped: bool = False) -> pd.DataFrame:
    """A daily curve from the opening row ($2,000, the day before the window) to ``final`` on the last day: steady
    growth with ``k`` one-day falls of ``dip`` that recover in half a cycle (so the daily drawdown is about ``dip``
    whatever the growth); a wiped account falls to ``final`` at 60% of the window and stops there."""
    a, z = WIN[w]
    days = pd.date_range(pd.Timestamp(a) - pd.Timedelta(days=1), pd.Timestamp(z) - pd.Timedelta(days=1), freq="D")
    if wiped:
        days = days[: int(len(days) * 0.6)]
        eq = np.linspace(2000.0, final, len(days))
    else:
        t = np.linspace(0.0, 1.0, len(days))
        fall = np.ones(len(days))
        for j in range(k):
            tc, span = (j + 0.5) / k, 0.5 / k
            on = (t >= tc) & (t < tc + span)
            fall[on] = np.minimum(fall[on], 1.0 - dip * (1.0 - (t[on] - tc) / span))
        eq = 2000.0 * (final / 2000.0) ** t * fall
        eq[0], eq[-1] = 2000.0, final
    return pd.DataFrame({"series_id": sid, "date": days.strftime("%Y-%m-%d"), "equity_usd": eq})


def _daily_dd(cv: pd.DataFrame) -> float:
    e = cv.equity_usd.to_numpy()
    return float(-((e / np.maximum.accumulate(e) - 1.0) * 100.0).min())


def _acct(sid: str, w: str, final: float, ddp, cagr="auto", wiped: int = 0, row_notes: str = "") -> dict:
    a, z = WIN[w]
    return dict(series_id=sid, window=w, start=a, end=z, cost=1.0, basis="account", start_usd=2000.0,
                final_usd=final, net_usd=final - 2000.0, return_pct=(final - 2000.0) / 20.0,
                cagr_pct="" if cagr is None else round(_cagr(final, w), 4), max_dd_usd="",
                max_dd_pct="" if ddp is None else round(ddp, 4), p_dd="", trades=40, win_rate_pct=50.0,
                profit_factor=1.2, sharpe_w="", pos_quarters_pct="", worst_quarter_usd="", wiped=wiped,
                dd_marks="M1", score_final10="", source_file="synthetic", sample="", derived="",
                row_notes=row_notes)


def _unit(sid: str, w: str) -> dict:
    a, z = WIN[w]
    return dict(series_id=sid, window=w, start=a, end=z, cost=1.0, basis="unit", start_usd=0.0, final_usd=100.0,
                net_usd=100.0, return_pct="", cagr_pct="", max_dd_usd=50.0, max_dd_pct="", p_dd=2.0, trades=10,
                win_rate_pct=50.0, profit_factor=1.3, sharpe_w="", pos_quarters_pct="", worst_quarter_usd="",
                wiped=0, dd_marks="M1", score_final10="", source_file="synthetic", sample="", derived="",
                row_notes="")


def _series(sid: str, sym: str, key: str, label: str, kind: str, family: str, role: str, eligible: int = 1,
            exam: str = "", sizing: str = "") -> dict:
    return dict(series_id=f"{sid}:{sym}|{key}", source=sid, study=f"synthetic {sid}", symbol=sym, label=label,
                kind=kind, family=family, tf="", filter="", role=role, eligible=eligible, exam=exam, notes="",
                sizing=sizing, tags="")


def _write(data: Path, sid: str, spec: list, unit_windows=()) -> None:
    """spec: [(series row, {window: (final, dip, k, flags)})]; flags: 'nocurve', 'noddp', 'nocagr', 'wiped', and
    'shallow' (the row's max DD below its curve's daily-close drawdown, with FINAL10's 1y timing note)."""
    series, metrics, curves = [], [], {}
    for s, wins in spec:
        series.append(s)
        for w, (final, dip, k, flags) in wins.items():
            cv = _curve(s["series_id"], w, final, dip, k, wiped="wiped" in flags)
            ddp = (None if "noddp" in flags else 99.75 if "wiped" in flags
                   else _daily_dd(cv) * (0.9 if "shallow" in flags else 1.08))
            metrics.append(_acct(s["series_id"], w, final, ddp, cagr=None if "nocagr" in flags else "auto",
                                 wiped=int("wiped" in flags), row_notes=TIMINGS if "shallow" in flags else ""))
            if "nocurve" not in flags:
                curves.setdefault(w, []).append(cv)
        for w in unit_windows:
            metrics.append(_unit(s["series_id"], w))
    CP.write_source(sid, pd.DataFrame(series), pd.DataFrame(metrics),
                    {w: pd.concat(v, ignore_index=True) for w, v in curves.items()}, data=data, replace=True)


def final10_spec(rebuilds: bool = True) -> list:
    x, b = "XAUUSDm", "BTCUSDm"
    rb = (lambda v: v) if rebuilds else (lambda v: {k: t for k, t in v.items() if k != "bots-holdout"})
    return [
        (_series("final10", x, "V3-lite", "V3-lite", "bot", "V3-lite", "design"),
         rb({"5y": (9000, 0.2, 3, ""), "1y": (3600, 0.2, 2, ""), "bots-holdout": (3400, 0.25, 2, "")})),
        (_series("final10", x, "Top 2", "Top 2", "bot", "Top 1-3", "design", eligible=0),
         rb({"5y": (7000, 0.1, 2, "shallow"), "1y": (3900, 0.15, 2, ""), "bots-holdout": (3700, 0.1, 2, "")})),
        (_series("final10", x, "Turtle", "Turtle", "rule", "Turtle", "finalist"),
         {"5y": (4000, 0.25, 2, ""), "1y": (2500, 0.2, 1, "")}),
        (_series("final10", b, "Top 2", "Top 2", "bot", "Top 1-3", "design"),
         {"5y": (3900, 0.15, 3, ""), "1y": (2100, 0.1, 2, "")})]


def make_data(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    x, b = "XAUUSDm", "BTCUSDm"
    _write(data, "final10", final10_spec())
    _write(data, "benchmarks", [
        (_series("benchmarks", x, "bh-2000", "Buy and hold, $2,000 fully invested (no leverage)", "benchmark",
                 "buy-and-hold", "benchmark", 0, sizing="fully invested"),
         {"5y": (4100, 0.3, 2, ""), "1y": (1850, 0.3, 1, ""), "holdout": (3100, 0.35, 2, "")}),
        (_series("benchmarks", x, "bh-0.01lot", "Buy and hold 0.01 lot (study 1's reference)", "benchmark",
                 "buy-and-hold", "benchmark", 0, sizing="0.01 lot fixed"),
         {"5y": (4000, 0.3, 2, ""), "1y": (1700, 0.5, 1, ""), "holdout": (3200, 0.4, 2, "")}),
        (_series("benchmarks", b, "bh-2000", "Buy and hold, $2,000 fully invested (no leverage)", "benchmark",
                 "buy-and-hold", "benchmark", 0, sizing="fully invested"),
         {"5y": (2200, 0.7, 2, ""), "1y": (1400, 0.45, 1, ""), "holdout": (1900, 0.55, 2, "")}),
        (_series("benchmarks", b, "bh-0.01lot", "Buy and hold 0.01 lot (study 1's reference)", "benchmark",
                 "buy-and-hold", "benchmark", 0, sizing="0.01 lot fixed"),
         {"5y": (2070, 0.25, 2, ""), "1y": (1700, 0.2, 1, ""), "holdout": (1980, 0.25, 2, "")})])
    _write(data, T2, [
        (_series(T2, x, "1H|RIB|A", "1H RIB A", "rule", "RIB", "finalist", exam="pass"),
         {"5y": (50000, 0.1, 3, ""), "holdout": (2400, 0.15, 2, "")}),
        (_series(T2, x, "4H|ORB|B", "4H ORB B", "rule", "ORB", "finalist", exam="fail"),
         {"5y": (4150, 0.2, 2, ""), "holdout": (3500, 0.2, 2, "")}),          # 5y: ends 2 px from buy-and-hold
        (_series(T2, x, "1D|HA|C", "1D HA C", "rule", "HA", "champion"),
         {"5y": (5000, 0.12, 2, ""), "holdout": (3000, 0.2, 1, "")}),
        (_series(T2, x, "1H|WY|D", "1H WY D", "rule", "WY", "champion", eligible=0),
         {"5y": (3000, 0.3, 2, ""), "holdout": (2600, 0.3, 1, "")}),
        (_series(T2, x, "1H|RIB|base", "1H RIB base", "rule", "RIB", "base"),
         {"5y": (4000, 0.2, 2, ""), "holdout": (2600, 0.2, 2, "")}),
        (_series(T2, x, "1H|RIB|V1", "1H RIB V1", "rule", "RIB", "variant"),
         {"5y": (2500, 0.2, 2, ""), "holdout": (2300, 0.2, 2, "")}),
        (_series(T2, x, "4H|ORB|V2", "4H ORB V2", "rule", "ORB", "variant", eligible=0),
         {"5y": (2200, 0.3, 2, ""), "holdout": (2100, 0.3, 2, "")}),
        (_series(T2, x, "1D|HA|V3", "1D HA V3", "rule", "HA", "variant"),
         {"5y": (2900, 0.2, 2, ""), "holdout": (2700, 0.2, 2, "")}),
        (_series(T2, x, "1H|WY|V4", "1H WY V4", "rule", "WY", "variant", eligible=0),
         {"5y": (3300, 0.1, 2, ""), "holdout": (2800, 0.15, 2, "")}),
        (_series(T2, x, "1H|WY|V5", "1H WY V5", "rule", "WY", "variant", eligible=0),
         {"5y": (5.0, 0.0, 1, "wiped")}),
        (_series(T2, b, "4H|RIB|E", "4H RIB E", "rule", "RIB", "finalist", exam="pass"),
         {"5y": (2600, 0.12, 2, ""), "holdout": (2300, 0.1, 2, "nocurve")}),
        (_series(T2, b, "4H|ORB|V6", "4H ORB V6", "rule", "ORB", "variant"),
         {"5y": (2300, 0.2, 2, ""), "holdout": (2100, 0.2, 2, "nocurve")})],
        unit_windows=("dev",))
    _write(data, T3, [
        (_series(T3, x, "v3lite|base", "V3-lite base", "bot", "base", "base", eligible=0),
         {"5y": (5000, 0.2, 2, ""), "1y": (2600, 0.2, 1, "noddp")}),
        (_series(T3, x, "v3lite|MA200-1H", "V3-lite MA200 1H", "bot+filter", "MA200", "variant"),
         {"5y": (6000, 0.1, 2, ""), "1y": (2700, 0.1, 1, "noddp")}),
        (_series(T3, x, "v3lite|MA200-4H", "V3-lite MA200 4H", "bot+filter", "MA200", "variant",
                 sizing="risk-sized"),
         {"5y": (20000, 0.05, 2, ""), "1y": (2900, 0.1, 1, "noddp")}),
        (_series(T3, x, "v3lite|ADX-20", LONG, "bot+filter", "ADX", "variant"),
         {"5y": (7000, 0.08, 2, "nocagr"), "1y": (2800, 0.1, 1, "noddp")}),
        (_series(T3, x, "v3lite|ADX-30", "V3-lite ADX 30", "bot+filter", "ADX", "variant"),
         {"5y": (9000, 0.06, 2, "nocurve"), "1y": (3000, 0.1, 1, "noddp nocurve")}),
        (_series(T3, x, "v3lite|ADX-40", "V3-lite ADX 40", "bot+filter", "ADX", "variant"),
         {"5y": (8000, 0.07, 2, "noddp"), "1y": (3100, 0.1, 1, "noddp")})])


@pytest.fixture(scope="module")
def data(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("contract")
    make_data(d)
    return d


def _run(source: str, data: Path, out: Path, **kw):
    logs: list = []
    recs = G.draw(source, out, data=data, log=logs.append, **kw)
    return recs, logs


def _run_keep(source: str, data: Path, out: Path, **kw):
    """A run that keeps every figure as it is saved (drawn, so its artists have their final places)."""
    figs = {}
    orig = G.Canvas.save

    def save(self, path):
        orig(self, path)
        figs[Path(path).name] = self.fig
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(G.Canvas, "save", save)
        recs, logs = _run(source, data, out, **kw)
    return recs, logs, figs


@pytest.fixture(scope="module")
def run2(data, tmp_path_factory):
    out = tmp_path_factory.mktemp("graphs_t2")
    recs, logs, figs = _run_keep(T2, data, out, top=3)
    return out, recs, logs, figs


@pytest.fixture(scope="module")
def run3(data, tmp_path_factory):
    out = tmp_path_factory.mktemp("graphs_t3")
    recs, logs, figs = _run_keep(T3, data, out, top=2)
    return out, recs, logs, figs


def _chunks(b: bytes):
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    i, out = 8, []
    while i < len(b):
        n = int.from_bytes(b[i:i + 4], "big")
        out.append((b[i + 4:i + 8].decode("ascii"), b[i + 8:i + 8 + n]))
        i += 12 + n
    return out


def _csv(path: Path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ───────────────────────────── the contract files, read here ─────────────────────────────

def _rows(data: Path, sid: str, w: str, sym: str) -> pd.DataFrame:
    """The account rows at x1.0 of a source on a window and symbol, with the series' fields, CAGR and max DD as numbers
    (a blank CAGR from the curve's last equity) and growth / DD."""
    m = pd.read_csv(data / f"{sid}__metrics.csv", dtype=str, keep_default_na=False)
    s = pd.read_csv(data / f"{sid}__series.csv", dtype=str, keep_default_na=False)
    m = m[(m.window == w) & (m.basis == "account") & (m.cost.astype(float) == 1.0)]
    a = m.merge(s[["series_id", "symbol", "label", "family", "role", "eligible", "sizing"]], on="series_id")
    a = a[a.symbol == sym].copy()
    p = data / f"{sid}__curves_{w}.csv.gz"
    last = (pd.read_csv(p, dtype={"series_id": str, "date": str}).groupby("series_id").equity_usd.last()
            if p.exists() else pd.Series(dtype=float))
    a["dd"] = [float(v) if v else math.nan for v in a.max_dd_pct]
    a["cg"] = [float(v) if v else (_cagr(float(last[i]), w) if i in last.index else math.nan)
               for v, i in zip(a.cagr_pct, a.series_id)]
    a["g"] = a.cg / a.dd
    return a.set_index("series_id", drop=False)


def _curves(data: Path, sid: str, w: str) -> dict:
    cv = pd.read_csv(data / f"{sid}__curves_{w}.csv.gz", dtype={"series_id": str, "date": str})
    out = {}
    for k, g in cv.groupby("series_id"):
        g = g.sort_values("date")
        out[k] = (g.date.to_numpy().astype("datetime64[D]"), g.equity_usd.to_numpy(np.float64))
    return out


def _curve_of(data: Path, series_id: str, w: str):
    sid = series_id.split(":")[0]
    if sid == "final10" and w == "holdout":
        w = "bots-holdout"                    # study 1's rebuilds of the designs stand in on its hold-out
    return _curves(data, sid, w)[series_id]


def _gid(artists, gid):
    got = [a for a in artists if a.get_gid() == gid]
    assert len(got) == 1, (gid, len(got))
    return got[0]


def _hex(c) -> str:
    return mcolors.to_hex(c)


def _leaders_cross_labels(ax, r) -> list:
    """(leader, label) pairs where a label's leader runs through another label's halo-padded box, in px."""
    boxes = {t.get_gid()[6:]: t.get_window_extent(r).padded(G.HALO_PX) for t in ax.texts
             if (t.get_gid() or "").startswith("label:")}
    out = []
    for ln in ax.get_lines():
        gid = ln.get_gid() or ""
        if not gid.startswith("leader:"):
            continue
        xs, ys = ln.get_data()
        a, b = ax.transData.transform((xs[0], ys[0])), ax.transData.transform((xs[-1], ys[-1]))
        out += [(gid[7:], k) for k, bb in boxes.items()
                if k != gid[7:] and G._seg_hits(tuple(a), tuple(b), (bb.x0, bb.y0, bb.x1, bb.y1))]
    return out


def _box_gap(px: float, py: float, bb) -> float:
    """The distance in px from a point to a box."""
    dx = max(bb.x0 - px, 0.0, px - bb.x1)
    dy = max(bb.y0 - py, 0.0, py - bb.y1)
    return math.hypot(dx, dy)


# ───────────────────────────── the tests ─────────────────────────────

def test_the_synthetic_files_are_valid_contract_files(data):
    rep = CP.validate(data)
    assert rep["errors"] == [], rep["errors"][:5]
    assert set(CP.sources_in(data)) == {"final10", "benchmarks", T2, T3}


def test_every_graph_is_drawn_with_a_fixed_size_no_metadata_and_its_values(run2):
    out, recs, logs, _ = run2
    expect = {f"{g}_{s}_{w}.png" for g in G.GRAPHS for s, w in
              (("XAUUSDm", "5y"), ("BTCUSDm", "5y"), ("XAUUSDm", "holdout"))}
    assert {r["file"] for r in recs} == expect
    assert {p.name for p in out.glob("*.png")} == expect
    assert {p.name for p in out.glob("*.csv")} == {n[:-4] + ".csv" for n in expect} | {"graphs.csv"}
    for r in recs:
        ch = _chunks((out / r["file"]).read_bytes())
        ihdr = dict(ch)["IHDR"]
        w, h = G.SIZES[r["graph"]]
        assert (int.from_bytes(ihdr[0:4], "big"), int.from_bytes(ihdr[4:8], "big")) == (w * G.DPI, h * G.DPI)
        assert not {t for t, _ in ch} & {"tEXt", "iTXt", "zTXt", "tIME"}      # no Software key, no time
        assert r["values_file"] == r["file"][:-4] + ".csv"
        assert list(_csv(out / r["values_file"])[0].keys()) == G.VALUES_COLS


def test_graphs_csv_indexes_what_was_drawn(run2, data):
    out, recs, logs, _ = run2
    rows = _csv(out / "graphs.csv")
    assert list(rows[0].keys()) == G.GRAPHS_COLS
    assert [r["file"] for r in rows] == [r["file"] for r in recs]
    by = {r["file"]: r for r in rows}
    eq = by["equity_XAUUSDm_5y.png"]
    ids = eq["series_ids"].split(";")
    # the top 3 featured (finalists, then the best champion), the base, the bots' designs, buy-and-hold
    assert ids[:3] == [f"{T2}:XAUUSDm|1H|RIB|A", f"{T2}:XAUUSDm|4H|ORB|B", f"{T2}:XAUUSDm|1D|HA|C"]
    assert set(ids[3:]) == {f"{T2}:XAUUSDm|1H|RIB|base", "final10:XAUUSDm|Top 2", "final10:XAUUSDm|V3-lite",
                            "benchmarks:XAUUSDm|bh-2000", "benchmarks:XAUUSDm|bh-0.01lot"}
    files = eq["source_files"].split(";")
    names = {Path(f).name for f in files}
    assert {f"{T2}__curves_5y.csv.gz", "final10__curves_5y.csv.gz", "benchmarks__curves_5y.csv.gz",
            f"{T2}__series.csv", f"{T2}__metrics.csv"} <= names
    assert all((data / Path(f).name).exists() for f in files)
    # the scatter lists every account row of the source drawn (10), and the references
    assert len(by["risk_return_XAUUSDm_5y.png"]["series_ids"].split(";")) == 10 + 2 + 2
    # the hold-out's designs are study 1's rebuilds, read from their own curve file
    hold = by["equity_XAUUSDm_holdout.png"]
    assert "final10__curves_bots-holdout.csv.gz" in {Path(f).name for f in hold["source_files"].split(";")}


def test_the_equity_graph_draws_the_contract_curves(run2, data):
    out, recs, logs, figs = run2
    slots = G.page_slots(data)
    want_colour = {T2: G.PALETTE[slots[T2]], "final10": G.PALETTE[slots["bots"]], "benchmarks": G.INK}
    by = {r["file"]: r for r in recs}
    for name, w in (("equity_XAUUSDm_5y.png", "5y"), ("equity_XAUUSDm_holdout.png", "holdout"),
                    ("equity_BTCUSDm_5y.png", "5y")):
        fig = figs[name]
        ax = fig.axes[0]
        ids = by[name]["series_ids"].split(";")
        drawn = {ln.get_gid(): ln for ln in ax.get_lines() if ln.get_gid() in ids}
        assert set(drawn) == set(ids), name
        for sid, ln in drawn.items():
            d, e = _curve_of(data, sid, w)
            assert np.array_equal(ln.get_ydata(), e), (name, sid)
            assert np.array_equal(ln.get_xdata(), mdates.date2num(d)), (name, sid)
            assert _hex(ln.get_color()) == want_colour[sid.split(":")[0]], (name, sid)
        # the legend gives every line's final equity: the last value of its curve
        legend = [t.get_text() for leg in fig.legends for t in leg.get_texts()]
        for sid in ids:
            fin = G.usd(float(_curve_of(data, sid, w)[1][-1]))
            assert any(t.endswith(f" · {fin}") for t in legend), (name, sid, fin)
        # the date axis is the window: the opening row (the day before the start) to the last day
        a, z = WIN[w]
        x0 = mdates.date2num(np.datetime64(a) - np.timedelta64(1, "D"))
        x1 = mdates.date2num(np.datetime64(z) - np.timedelta64(1, "D"))
        assert ax.get_xlim() == pytest.approx((x0, x1), abs=1e-9)
        title, sub = _gid(fig.texts, "title").get_text(), _gid(fig.texts, "subtitle").get_text()
        assert title.startswith(("Gold (XAUUSDm), " if "XAU" in name else "BTC (BTCUSDm), ") + w)
        dates = f"{pd.Timestamp(a).day} {pd.Timestamp(a):%b %Y} – {pd.Timestamp(z).day} {pd.Timestamp(z):%b %Y}"
        assert "x1.0" in sub and "account basis" in sub and dates in sub.replace("\n", " "), sub
    # the axis is log where the lines span more than 20x: 50,000 against about 2,000
    assert figs["equity_XAUUSDm_5y.png"].axes[0].get_yscale() == "log"
    assert figs["equity_XAUUSDm_holdout.png"].axes[0].get_yscale() == "linear"


def test_the_end_labels_and_the_equity_graphs_own_cut(run2, data, tmp_path):
    out, recs, logs, figs = run2
    for name, w in (("equity_XAUUSDm_5y.png", "5y"), ("equity_XAUUSDm_holdout.png", "holdout")):
        fig = figs[name]
        ax = fig.axes[0]
        ends = {t.get_gid()[4:]: t.get_text() for t in fig.texts if (t.get_gid() or "").startswith("end:")}
        assert 1 <= len(ends) <= 4                                   # the skill: at most four direct labels
        for sid, text in ends.items():
            assert text == G.usd(float(_curve_of(data, sid, w)[1][-1])), (name, sid)
        # every printed end has its dot; no two printed ends are closer than END_GAP px; a line left unprinted ends
        # next to a printed one, or the printed ones are already END_LABELS
        px = {}
        for ln in ax.get_lines():
            gid = ln.get_gid() or ""
            if ":" in gid and not gid.startswith("enddot:"):          # the series' lines, not the dots or the start
                px[gid] = ax.transData.transform((ln.get_xdata()[-1], ln.get_ydata()[-1]))
        assert all(_gid(ax.get_lines(), f"enddot:{sid}") for sid in ends)
        for a, b in itertools.combinations(ends, 2):
            assert math.dist(px[a], px[b]) >= G.END_GAP
        if len(ends) < 4:
            for sid in set(px) - set(ends):
                assert min(math.dist(px[sid], px[e]) for e in ends) < G.END_GAP
        # the note names the lines whose ends are printed, and nothing else
        note = _gid(fig.texts, "note").get_text().replace("\n", " ")
        named = re.search(r"the final equity of (.*?) \(at most", note).group(1).split("; ")
        label = {}
        for sid in (T2, "final10", "benchmarks"):
            r = _rows(data, sid, "bots-holdout" if (sid == "final10" and w == "holdout") else w, "XAUUSDm")
            label.update({i: (G.BH_SHORT[z] if sid == "benchmarks" else lb)
                          for i, lb, z in zip(r.index, r.label, r.sizing)})
        assert sorted(named) == sorted(label[sid] for sid in ends), (named, ends)
    ends5 = {t.get_gid()[4:] for t in figs["equity_XAUUSDm_5y.png"].texts if (t.get_gid() or "").startswith("end:")}
    assert f"{T2}:XAUUSDm|4H|ORB|B" not in ends5 and "benchmarks:XAUUSDm|bh-2000" in ends5
    # --equity-top 2: the equity graph draws the first two featured series and names the others; the drawdown graph
    # keeps all four
    recs2, logs2, figs2 = _run_keep(T2, data, tmp_path / "eqtop", windows=["5y"], symbols=["XAUUSDm"], top=6,
                                    equity_top=2)
    by = {r["file"]: r for r in recs2}
    eq_ids = by["equity_XAUUSDm_5y.png"]["series_ids"].split(";")
    assert eq_ids[:2] == [f"{T2}:XAUUSDm|1H|RIB|A", f"{T2}:XAUUSDm|4H|ORB|B"]
    assert f"{T2}:XAUUSDm|1D|HA|C" not in eq_ids and f"{T2}:XAUUSDm|1H|WY|D" not in eq_ids
    note = _gid(figs2["equity_XAUUSDm_5y.png"].texts, "note").get_text().replace("\n", " ")
    assert "draws the first 2 of the 4 featured series" in note and "not drawn here: 1D HA C; 1H WY D" in note
    panels = {ax.get_gid() for ax in figs2["drawdown_XAUUSDm_5y.png"].axes}
    assert {f"{T2}:XAUUSDm|1D|HA|C", f"{T2}:XAUUSDm|1H|WY|D"} <= panels
    with pytest.raises(ValueError):
        G.draw(T2, tmp_path / "x", data=data, equity_top=0, log=lambda *a: None)


def test_the_drawdown_panels_match_their_series(run2, data):
    out, recs, logs, figs = run2
    for name, w in (("drawdown_XAUUSDm_5y.png", "5y"), ("drawdown_XAUUSDm_holdout.png", "holdout")):
        fig = figs[name]
        rec = {r["file"]: r for r in recs}[name]
        panels = {ax.get_gid(): ax for ax in fig.axes if ax.get_gid()}
        assert set(panels) == set(rec["series_ids"].split(";"))
        rows = {sid: _rows(data, sid, "bots-holdout" if (sid == "final10" and w == "holdout") else w, "XAUUSDm")
                for sid in (T2, "final10", "benchmarks")}
        for sid, ax in panels.items():
            e = _curve_of(data, sid, w)[1]
            dd = (e / np.maximum.accumulate(e) - 1.0) * 100.0
            ln = _gid(ax.get_lines(), f"dd:{sid}")
            assert np.allclose(ln.get_ydata(), dd, atol=1e-12, rtol=0), (name, sid)
            row = rows[sid.split(":")[0]].loc[sid]
            head = _gid(ax.texts, f"head:{sid}").get_text()
            sub = _gid(ax.texts, f"sub:{sid}").get_text().replace("\n", " ")
            assert head.startswith(row.label if sid.split(":")[0] != "benchmarks" else "Buy and hold"), head
            assert f"max DD −{row.dd:.1f}%" in sub and f"daily close −{-dd.min():.1f}%" in sub, (sid, sub)
    # the design row whose max DD (a median of 8 timings) is shallower than its curve's daily close says so
    panel = {ax.get_gid(): ax for ax in figs["drawdown_XAUUSDm_5y.png"].axes}["final10:XAUUSDm|Top 2"]
    sub = _gid(panel.texts, "sub:final10:XAUUSDm|Top 2").get_text().replace("\n", " ")
    assert "(M1, 8-timing median)" in sub, sub
    note = _gid(figs["drawdown_XAUUSDm_5y.png"].texts, "note").get_text().replace("\n", " ")
    assert "Deeper at a daily close than its max DD: Top 2 (8-timing median)" in note
    assert "come from different runs" in note


def test_the_scatter_puts_every_row_where_its_numbers_say(run2, data):
    out, recs, logs, figs = run2
    for name, sym, w in SCATTERS:
        ax = figs[name].axes[0]
        src = _rows(data, T2, w, sym)
        des = _rows(data, "final10", "bots-holdout" if w == "holdout" else w, sym)
        des = des[des.role == "design"]
        bh = _rows(data, "benchmarks", w, sym)
        live = src[src.dd.notna() & src.cg.notna() & (src.wiped == "0")]
        drawable = pd.concat([live, des, bh])
        want = {(round(a, 9), round(b, 9)) for a, b in zip(drawable.dd, drawable.cg)}
        colls = {c.get_gid(): c for c in ax.collections if c.get_gid()}
        got = {(round(float(x), 9), round(float(y), 9)) for g in ("rows", "bases", "featured", "designs", "bhs")
               if g in colls for x, y in colls[g].get_offsets()}
        assert got == want, (name, got ^ want)
        assert "up" not in colls                       # nothing far above the rest in these files
    # the account wiped with $5 left is off the scale: its cross sits on the frame's bottom-right corner, and its
    # text gives its own max DD and CAGR
    ax = figs["risk_return_XAUUSDm_5y.png"].axes[0]
    w5 = _rows(data, T2, "5y", "XAUUSDm").loc[f"{T2}:XAUUSDm|1H|WY|V5"]
    wiped = _gid(ax.collections, "wiped")
    assert wiped.get_offset_transform() is ax.transAxes and wiped.get_offsets().tolist() == [[1.0, 0.0]]
    assert float(w5.final_usd) == 5.0 and w5.dd < 100
    text = f"1 wiped (max DD {w5.dd:.1f}%, CAGR −{abs(w5.cg):.1f}%)"
    assert _gid(ax.texts, "label:wiped").get_text() == text == "1 wiped (max DD 99.8%, CAGR −69.8%)"
    rec = {r["file"]: r for r in recs}["risk_return_XAUUSDm_5y.png"]
    assert f"{text}: off the scale" in rec["notes"]
    note = _gid(figs["risk_return_XAUUSDm_5y.png"].texts, "note").get_text().replace("\n", " ")
    assert f"{text}: off the scale" in note and "100% DD" not in note
    # past six labelled points the featured are numbered and the base lettered, keyed in the legend; with four, named
    keyed = {t.get_gid()[6:]: t.get_text() for t in ax.texts if (t.get_gid() or "").startswith("label:")}
    assert keyed[f"{T2}:XAUUSDm|1H|RIB|A"] == "1" and keyed[f"{T2}:XAUUSDm|4H|ORB|B"] == "2"
    assert keyed[f"{T2}:XAUUSDm|1D|HA|C"] == "3" and keyed[f"{T2}:XAUUSDm|1H|RIB|base"] == "a"
    assert keyed["final10:XAUUSDm|V3-lite"] == "V3-lite" and keyed["benchmarks:XAUUSDm|bh-2000"].startswith("Buy")
    legend = [t.get_text() for leg in figs["risk_return_XAUUSDm_5y.png"].legends for t in leg.get_texts()]
    assert "1   1H RIB A · finalist, exam pass" in legend and "a   1H RIB base" in legend
    named = {t.get_gid()[6:]: t.get_text() for t in figs["risk_return_BTCUSDm_5y.png"].axes[0].texts
             if (t.get_gid() or "").startswith("label:")}
    assert named[f"{T2}:BTCUSDm|4H|RIB|E"] == "4H RIB E"
    # marker sizes: 12 px featured, bases and designs, 11 px buy-and-hold, 8 px dots (the skill's >= 8 px)
    sizes = {c.get_gid(): float(np.sqrt(c.get_sizes()[0])) / G.PX for c in ax.collections
             if c.get_gid() in ("rows", "featured", "bases", "designs", "bhs")}
    assert sizes == pytest.approx({"rows": 8.0, "featured": 12.0, "bases": 12.0, "designs": 12.0, "bhs": 11.0})


def test_scatter_labels_never_collide_and_stay_by_their_points(run2, data):
    out, recs, logs, figs = run2
    for name, sym, w in SCATTERS:
        fig = figs[name]
        ax = fig.axes[0]
        r = fig.canvas.get_renderer()
        ab = ax.get_window_extent(r)
        labels = [t for t in ax.texts if (t.get_gid() or "").startswith("label:")]
        boxes = [(t, t.get_window_extent(r).padded(G.HALO_PX)) for t in labels]
        for (t1, b1), (t2, b2) in itertools.combinations(boxes, 2):
            assert not (min(b1.x1, b2.x1) - max(b1.x0, b2.x0) > 0.5 and min(b1.y1, b2.y1) - max(b1.y0, b2.y0) > 0.5), \
                (name, t1.get_text(), t2.get_text())
        for t in labels:
            if t.get_gid() == "label:diagonal":
                continue
            bb = t.get_window_extent(r)
            assert ab.x0 <= bb.x0 and bb.x1 <= ab.x1 and ab.y0 <= bb.y0 and bb.y1 <= ab.y1, (name, t.get_text())
        assert _leaders_cross_labels(ax, r) == [], name
        # each label of a series sits next to its point (from the files), or a leader joins them
        rows = pd.concat([_rows(data, T2, w, sym), _rows(data, "final10", "bots-holdout" if w == "holdout" else w, sym),
                          _rows(data, "benchmarks", w, sym)])
        for t in labels:
            sid = t.get_gid()[6:]
            if sid not in rows.index:
                continue
            p = ax.transData.transform((rows.loc[sid].dd, rows.loc[sid].cg))
            bb = t.get_window_extent(r)
            leads = [ln for ln in ax.get_lines() if ln.get_gid() == f"leader:{sid}"]
            if leads:
                xs, ys = leads[0].get_data()
                a0 = ax.transData.transform((xs[0], ys[0]))
                a1 = ax.transData.transform((xs[-1], ys[-1]))
                assert math.dist(a0, p) <= G.MARK_R + 0.5, (name, sid)
                assert _box_gap(*a1, bb) <= 3.5, (name, sid)
            else:
                assert _box_gap(*p, bb) <= G.MARK_R + 6.0, (name, sid, _box_gap(*p, bb))


def _overlaps(a, b) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 0.5 and min(a[3], b[3]) - max(a[1], b[1]) > 0.5


def test_labels_in_a_crowd_neither_collide_nor_cover_marks():
    """Twelve labelled points 18 px apart among 200 dots: every label stays inside the plot, clear of
    every other label (halo included) and of every other labelled mark (halo and 2 px), and a leader joins it to its
    own point."""
    rng = np.random.default_rng(7)
    with matplotlib.rc_context(G.RC):
        cv = G.Canvas("risk_return")
        cv.top, cv.bottom = 90.0, 150.0
        ax = cv.axes(left=120.0, right=40.0)
        ax.set_xlim(0.0, 100.0)
        ax.set_ylim(0.0, 100.0)
        pts = [(46.0 + (i % 6) * 1.2, 48.0 + (i // 6) * 2.2) for i in range(12)]   # two rows of six, 18 px apart
        soft = rng.uniform(25.0, 75.0, size=(200, 2))
        ax.scatter(soft[:, 0], soft[:, 1], s=(G.DOT_ROW * G.PX) ** 2)
        items = [(x, y, f"Series {i}" if i % 3 == 0 else str(i + 1), f"p{i}") for i, (x, y) in enumerate(pts)]
        placed = G._place_labels(cv, ax, items, soft=soft)
        cv.fig.savefig(io.BytesIO(), format="png")
        r = cv.fig.canvas.get_renderer()
    ab = ax.get_window_extent(r)
    boxes = {t.get_gid()[6:]: t.get_window_extent(r) for t in ax.texts}
    assert set(boxes) == set(placed) == {f"p{i}" for i in range(12)}
    marks = {f"p{i}": ax.transData.transform(p) for i, p in enumerate(pts)}
    for (g1, b1), (g2, b2) in itertools.combinations(boxes.items(), 2):
        p1, p2 = b1.padded(G.HALO_PX), b2.padded(G.HALO_PX)
        assert not _overlaps((p1.x0, p1.y0, p1.x1, p1.y1), (p2.x0, p2.y0, p2.x1, p2.y1)), (g1, g2)
    for g, b in boxes.items():
        assert ab.x0 <= b.x0 and b.x1 <= ab.x1 and ab.y0 <= b.y0 and b.y1 <= ab.y1, g
        pb = b.padded(G.LABEL_PAD - 0.5)
        for h, (mx, my) in marks.items():
            if h != g:
                assert not _overlaps((pb.x0, pb.y0, pb.x1, pb.y1),
                                     (mx - G.MARK_R, my - G.MARK_R, mx + G.MARK_R, my + G.MARK_R)), (g, h)
        # every point here has a neighbour within 20 px, so its label sits further out with a leader from its mark,
        # and no leader runs through another label
        lead = _gid(ax.get_lines(), f"leader:{g}")
        xs, ys = lead.get_data()
        assert math.dist(ax.transData.transform((xs[0], ys[0])), marks[g]) <= G.MARK_R + 0.5, g
        assert _box_gap(*ax.transData.transform((xs[-1], ys[-1])), b) <= 3.5, g
    assert _leaders_cross_labels(ax, r) == []


@pytest.mark.parametrize("dx, dy", [(1.2, 1.6), (0.9, 1.2)])
def test_labels_of_boxed_in_points_still_never_overlap(dx, dy):
    """A 4 x 3 grid: the inner points have neighbours on every side, so no spot keeps every rule. The placer then
    gives up the lesser rules (a leader past a dot, a label over another mark) before letting two labels meet: none
    overlaps another (halo included), all stay inside the plot, and each keeps its leader to its own point."""
    rng = np.random.default_rng(7)
    with matplotlib.rc_context(G.RC):
        cv = G.Canvas("risk_return")
        cv.top, cv.bottom = 90.0, 150.0
        ax = cv.axes(left=120.0, right=40.0)
        ax.set_xlim(0.0, 100.0)
        ax.set_ylim(0.0, 100.0)
        pts = [(46.0 + (i % 4) * dx, 48.0 + (i // 4) * dy) for i in range(12)]
        soft = rng.uniform(25.0, 75.0, size=(200, 2))
        items = [(x, y, f"Series {i}" if i % 3 == 0 else str(i + 1), f"p{i}") for i, (x, y) in enumerate(pts)]
        G._place_labels(cv, ax, items, soft=soft)
        cv.fig.savefig(io.BytesIO(), format="png")
        r = cv.fig.canvas.get_renderer()
    ab = ax.get_window_extent(r)
    boxes = {t.get_gid()[6:]: t.get_window_extent(r) for t in ax.texts}
    assert len(boxes) == 12
    for (g1, b1), (g2, b2) in itertools.combinations(boxes.items(), 2):
        p1, p2 = b1.padded(G.HALO_PX), b2.padded(G.HALO_PX)
        assert not _overlaps((p1.x0, p1.y0, p1.x1, p1.y1), (p2.x0, p2.y0, p2.x1, p2.y1)), (g1, g2)
    for i, (g, b) in enumerate(sorted(boxes.items(), key=lambda kv: int(kv[0][1:]))):
        assert ab.x0 <= b.x0 and b.x1 <= ab.x1 and ab.y0 <= b.y0 and b.y1 <= ab.y1, g
        xs, ys = _gid(ax.get_lines(), f"leader:{g}").get_data()
        assert math.dist(ax.transData.transform((xs[0], ys[0])),
                         ax.transData.transform(pts[int(g[1:])])) <= G.MARK_R + 0.5, g

def test_the_families_bars_ticks_and_reference_lines(run2, run3, data):
    _, recs, _, figs = run2
    # a source with champions: each family's bar is its pre-registered pick, its finalist, else its champion
    fig = figs["families_XAUUSDm_5y.png"]
    ax = fig.axes[0]
    rows = _rows(data, T2, "5y", "XAUUSDm")
    pick = {}                                  # family: (growth / DD, series id) of its finalist, else its champion
    for fam, g in rows[rows.role.isin(["finalist", "champion"]) & rows.g.notna()].groupby("family"):
        pool = g[g.role == "finalist"] if (g.role == "finalist").any() else g
        r = pool.sort_values("g", ascending=False).iloc[0]
        pick[fam] = (r.g, r.series_id)
    bars = {p.get_gid()[4:]: p for p in ax.patches if (p.get_gid() or "").startswith("bar:")}
    assert set(bars) == set(pick) == {"RIB", "ORB", "HA", "WY"}
    for fam, p in bars.items():
        xs = p.get_path().vertices[:, 0]
        end = xs.max() if pick[fam][0] > 0 else xs.min()
        assert end == pytest.approx(pick[fam][0], abs=1e-6), fam
    assert bars["WY"].get_facecolor()[:3] == (1.0, 1.0, 1.0)            # WY D is not eligible: hollow
    # the thin tick: the family's best row on the window (unit rule, with a growth / DD), where it is not the pick
    best = rows[rows.sizing.isin(["", "unit rule"]) & rows.g.notna()].sort_values("g", ascending=False)
    best = best.drop_duplicates("family")
    ticks = {ln.get_gid()[5:]: ln for ln in ax.get_lines() if (ln.get_gid() or "").startswith("tick:")}
    want_ticks = {r.family: r.g for r in best.itertuples() if r.series_id != pick[r.family][1]}
    assert set(ticks) == set(want_ticks) == {"WY"}
    assert ticks["WY"].get_xdata()[0] == pytest.approx(want_ticks["WY"], abs=1e-6)
    tips = {t.get_gid(): t.get_text() for t in ax.texts}
    assert tips["tip:RIB"].startswith(f"{pick['RIB'][0]:.2f}  1H RIB A")
    assert "hindsight best" in (tips.get("ticklabel:WY", "") + tips["tip:WY"])
    # the reference lines: the bots' best design, the best base, both buy-and-hold lines, each at its growth / DD
    des = _rows(data, "final10", "5y", "XAUUSDm")
    des = des[des.role == "design"].sort_values("g", ascending=False)
    bh = _rows(data, "benchmarks", "5y", "XAUUSDm")
    want = {des.index[0]: des.g.iloc[0], f"{T2}:XAUUSDm|1H|RIB|base": rows.loc[f"{T2}:XAUUSDm|1H|RIB|base"].g}
    want.update({i: g for i, g in zip(bh.index, bh.g)})
    refs = {ln.get_gid()[4:]: ln.get_xdata()[0] for ln in ax.get_lines() if (ln.get_gid() or "").startswith("ref:")}
    assert refs == pytest.approx(want, abs=1e-6)
    assert "pre-registered pick" in _gid(fig.texts, "title").get_text()
    note = _gid(fig.texts, "note").get_text().replace("\n", " ")
    assert "Max DD marks: study 2 M1; the bots' designs M1; buy-and-hold M1." in note
    # tip labels sit on a solid surface box above the reference lines
    assert all(t.get_bbox_patch() is not None and t.get_zorder() > 4 for t in ax.texts)
    # no reference line's connector runs through another reference's label above the plot
    r = fig.canvas.get_renderer()
    labels = {t.get_gid()[9:]: t.get_window_extent(r) for t in fig.texts if (t.get_gid() or "").startswith("reflabel:")}
    joins = {a.get_gid()[8:]: a for a in fig.artists if (a.get_gid() or "").startswith("refline:")}
    assert set(labels) == set(joins) == set(want)
    for sid, ln in joins.items():
        x = ln.get_xdata()[0] * fig.bbox.width
        top = max(ln.get_ydata()) * fig.bbox.height
        for other, bb in labels.items():
            if other != sid:
                assert not (bb.x0 - 1 <= x <= bb.x1 + 1 and top > bb.y0 + 1), (sid, other)
    # a source without champions: each family's best row, said to be picked in hindsight
    _, recs3, _, figs3 = run3
    fig = figs3["families_XAUUSDm_5y.png"]
    ax = fig.axes[0]
    rows = _rows(data, T3, "5y", "XAUUSDm")
    best = rows[rows.sizing.isin(["", "unit rule"]) & rows.g.notna()].sort_values("g", ascending=False)
    best = best.drop_duplicates("family").set_index("family")
    bars = {p.get_gid()[4:]: p for p in ax.patches if (p.get_gid() or "").startswith("bar:")}
    assert set(bars) == set(best.index)
    for fam, p in bars.items():
        assert p.get_path().vertices[:, 0].max() == pytest.approx(best.loc[fam].g, abs=1e-6), fam
    assert not [ln for ln in ax.get_lines() if (ln.get_gid() or "").startswith("tick:")]
    assert "picked in hindsight, not a pre-registered choice" in _gid(fig.texts, "subtitle").get_text().replace(
        "\n", " ")
    assert "No row of the source is marked eligible" not in _gid(fig.texts, "note").get_text()


def test_legends_stay_inside_the_figure(run3, tmp_path):
    # a canvas whose legend groups cannot sit side by side: they wrap into rows; a group wider than the figure is
    # shortened, its final equity kept
    with matplotlib.rc_context(G.RC):
        cv = G.Canvas("equity")
        h = Line2D([0, 1], [0, 0], color=G.INK)
        groups = [(f"Group {k}", [(h, ("x" * 60 + f" {k}{j} · variant", " · $1,234")) for j in range(3)])
                  for k in range(3)] + [("Too wide", [(h, ("y" * 400, " · $9,876"))])]
        cv.legends(groups)
        cv.fig.savefig(io.BytesIO(), format="png")
        r = cv.fig.canvas.get_renderer()
        boxes = [leg.get_window_extent(r) for leg in cv.fig.legends]
        assert len({round(b.y0) for b in boxes}) >= 3                     # more than one row
        for b in boxes:
            assert b.x0 >= -0.5 and b.y0 >= -0.5 and b.x1 <= cv.W + 0.5 and b.y1 <= cv.H + 0.5
        wide = [t.get_text() for t in cv.fig.legends[-1].get_texts()][0]
        assert wide.endswith("… · $9,876")
    # the 70-character label of study 3's best row, in its equity graph
    _, recs, _, figs = run3
    fig = figs["equity_XAUUSDm_5y.png"]
    texts = [t.get_text() for leg in fig.legends for t in leg.get_texts()]
    assert any(LONG[:40] in t for t in texts)
    r = fig.canvas.get_renderer()
    for leg in fig.legends:
        b = leg.get_window_extent(r)
        assert b.x0 >= -0.5 and b.x1 <= fig.bbox.width + 0.5 and b.y0 >= -0.5 and b.y1 <= fig.bbox.height + 0.5


def test_line_keys_stay_with_their_series_across_windows(run2):
    out, recs, logs, figs = run2
    a, b = f"{T2}:XAUUSDm|1H|RIB|A", f"{T2}:XAUUSDm|4H|ORB|B"
    # 1H RIB A ranks first on 5y and second on the hold-out, and keeps its dash and its number on both
    order = {w: [x for x in {r["file"]: r for r in recs}[f"equity_XAUUSDm_{w}.png"]["series_ids"].split(";")
                 if x in (a, b)] for w in ("5y", "holdout")}
    assert order == {"5y": [a, b], "holdout": [b, a]}
    for w in ("5y", "holdout"):
        lines = {ln.get_gid(): ln for ln in figs[f"equity_XAUUSDm_{w}.png"].axes[0].get_lines()}
        assert lines[a]._unscaled_dash_pattern == (0, None)                    # solid
        assert lines[b]._unscaled_dash_pattern == G.DASHES[1]                  # dashed
        keys = {t.get_gid()[6:]: t.get_text() for t in figs[f"risk_return_XAUUSDm_{w}.png"].axes[0].texts
                if (t.get_gid() or "").startswith("label:")}
        assert keys[a] == "1" and keys[b] == "2"
        vals = {r["series_id"]: r["key"] for r in _csv(out / f"equity_XAUUSDm_{w}.csv")}
        assert vals[a] == "solid" and vals[b] == "dashed"


def test_a_window_drawn_alone_gives_the_same_bytes(run2, data, tmp_path):
    """The keys come from every window with curves, so the hold-out (where the finalists' order flips) drawn on its
    own is byte for byte the hold-out of the full run."""
    out, recs, _, _ = run2
    alone, _ = _run(T2, data, tmp_path / "alone", windows=["holdout"], top=3)
    assert {r["window"] for r in alone} == {"holdout"} and len(alone) == 4
    for r in alone:
        for n in (r["file"], r["values_file"]):
            assert (tmp_path / "alone" / n).read_bytes() == (out / n).read_bytes(), n


def test_values_files_are_the_table_view(run2, data):
    out, recs, logs, figs = run2
    eq = _csv(out / "equity_XAUUSDm_5y.csv")
    rec = {r["file"]: r for r in recs}["equity_XAUUSDm_5y.png"]
    assert [r["series_id"] for r in eq] == rec["series_ids"].split(";")
    for r in eq:
        last = float(_curve_of(data, r["series_id"], "5y")[1][-1])
        assert r["item"] == "line" and float(r["curve_last_usd"]) == pytest.approx(last, abs=0.005)
    printed = {r["series_id"] for r in eq if r["notes"] == "end printed"}
    ends = {t.get_gid()[4:] for t in figs["equity_XAUUSDm_5y.png"].texts if (t.get_gid() or "").startswith("end:")}
    assert printed == ends
    rr = _csv(out / "risk_return_XAUUSDm_5y.csv")
    assert len(rr) == 10 + 2 + 2 and {r["group"] for r in rr} == {"row", "featured", "base", "design", "bh", "wiped"}
    src = _rows(data, T2, "5y", "XAUUSDm")
    for r in rr:
        if r["series_id"] in src.index and r["group"] != "wiped":
            assert float(r["x"]) == pytest.approx(src.loc[r["series_id"]].dd, abs=1e-4)
            assert float(r["y"]) == pytest.approx(src.loc[r["series_id"]].cg, abs=1e-4)
    fam = _csv(out / "families_XAUUSDm_5y.csv")
    assert [r["item"] for r in fam].count("bar") == 4 and [r["item"] for r in fam].count("tick") == 1
    dd = _csv(out / "drawdown_XAUUSDm_5y.csv")
    for r in dd:
        e = _curve_of(data, r["series_id"], "5y")[1]
        assert float(r["daily_close_dd_pct"]) == pytest.approx(((e / np.maximum.accumulate(e) - 1) * 100).min(),
                                                               abs=1e-4)


def test_rebuilt_designs_stand_in_on_study_windows_and_the_note_when_there_are_none(run2, data, tmp_path):
    out, recs, logs, figs = run2
    hold = [r for r in recs if r["window"] == "holdout"]
    assert len(hold) == 4
    assert all("The bots' designs come from FINAL10's window 'bots-holdout'" in r["notes"] for r in hold)
    assert any(f"{T2} XAUUSDm holdout: the bots' designs from window bots-holdout" in x for x in logs)
    legend = [leg.get_title().get_text() for leg in figs["equity_XAUUSDm_holdout.png"].legends]
    assert "The bots' designs (study 1's rebuilds)" in legend
    # without the rebuilds, the graphs say where the designs are
    part = tmp_path / "data"
    part.mkdir()
    for p in data.iterdir():
        if not p.name.startswith("final10__"):
            (part / p.name).write_bytes(p.read_bytes())
    _write(part, "final10", final10_spec(rebuilds=False))
    recs2, logs2 = _run(T2, part, tmp_path / "out", windows=["holdout"], symbols=["XAUUSDm"])
    assert len(recs2) == 4 and all("The bots' designs are not drawn: FINAL10 has no design row on window 'holdout' "
                                   "(they are on 5y, 1y)." in r["notes"] for r in recs2)
    assert any("the bots' designs not drawn: final10 has no design row on holdout" in x for x in logs2)


def test_skipped_graphs_are_logged_with_the_reason(run2, run3):
    _, recs, logs, _ = run2
    text = "\n".join(logs)
    assert f"{T2} dev: no graphs: the source has no curves on this window" in text
    assert f"{T2} BTCUSDm holdout: skipped: the source has no curve of this symbol on this window" in text
    _, recs3, logs3, _ = run3
    text3 = "\n".join(logs3)
    assert not any(r["window"] == "1y" for r in recs3)
    for g in ("equity", "drawdown"):
        assert f"{T3} XAUUSDm 1y: {g}_XAUUSDm_1y.png skipped: no featured series" in text3
    assert f"{T3} XAUUSDm 1y: risk_return_XAUUSDm_1y.png skipped: no account row at x1.0 with both a CAGR" in text3
    assert f"{T3} XAUUSDm 1y: families_XAUUSDm_1y.png skipped: no unit-rule account row" in text3
    assert f"{T3} BTCUSDm 5y: skipped: the source has no account row at x1.0 for this symbol" in text3


def test_a_missing_reference_source_is_said_and_the_graphs_still_drawn(data, tmp_path):
    part = tmp_path / "data"
    part.mkdir()
    for p in data.iterdir():
        if not p.name.startswith("benchmarks__"):
            (part / p.name).write_bytes(p.read_bytes())
    recs, logs = _run(T2, part, tmp_path / "out", windows=["5y"], symbols=["XAUUSDm"])
    assert len(recs) == 4
    assert all("Buy-and-hold is not drawn: the data folder has no benchmarks files." in r["notes"] for r in recs)
    assert any("buy-and-hold not drawn: no benchmarks files" in x for x in logs)


def test_the_same_data_gives_the_same_bytes(run2, data, tmp_path):
    out, recs, _, _ = run2
    again, _ = _run(T2, data, tmp_path / "again", top=3)
    names = [r["file"] for r in recs] + [r["values_file"] for r in recs] + ["graphs.csv"]
    for n in names:
        assert (out / n).read_bytes() == (tmp_path / "again" / n).read_bytes(), n
    # in two other processes with other hash seeds (set order never reaches the drawing)
    for seed in ("1", "4242"):
        o = tmp_path / f"seed{seed}"
        code = ("import sys\nfrom backtesting.research import study_graphs as G\n"
                f"G.draw({T2!r}, {str(o)!r}, data={str(data)!r}, top=3, log=lambda *a: None)\n"
                "print(sorted(k for k in sys.modules if 'tradeiq2' in k or 'bot_filters' in k))")
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-B", "-c", code], cwd=REPO, env=env, capture_output=True,
                             text=True, check=True)
        assert res.stdout.strip().splitlines()[-1] == "[]"          # no study-2 or study-3 module at run time
        for n in names:
            assert (out / n).read_bytes() == (o / n).read_bytes(), (seed, n)


def test_the_ranking_is_the_pages_top_rule(data, run3):
    src = G.Source(T3, data)
    rows = src.account_rows("5y", "XAUUSDm")
    # an independent growth / DD: CAGR % / max DD %, the CAGR of a blank row from its curve's last equity
    m = pd.read_csv(data / f"{T3}__metrics.csv", dtype=str, keep_default_na=False)
    m = m[(m.window == "5y") & (m.basis == "account")]
    cv = pd.read_csv(data / f"{T3}__curves_5y.csv.gz", dtype={"series_id": str, "date": str})
    last = cv.groupby("series_id").equity_usd.last()
    s = pd.read_csv(data / f"{T3}__series.csv", dtype=str, keep_default_na=False).set_index("series_id")
    want = {}
    for r in m.itertuples():
        dd = float(r.max_dd_pct) if r.max_dd_pct else None
        if r.cagr_pct:
            cg = float(r.cagr_pct)
        elif r.series_id in last.index:
            cg = _cagr(float(last[r.series_id]), "5y")
        else:
            cg = None
        ok = (cg is not None and dd and s.loc[r.series_id, "sizing"] in ("", "unit rule")
              and r.series_id in last.index)
        if ok:
            want[r.series_id] = cg / dd
    order = sorted(want, key=lambda i: -want[i])
    got = G.ranked(rows, need_curve=True)
    assert list(got.series_id) == order
    for i in order:
        assert abs(float(rows.set_index("series_id").rdd[i]) - want[i]) < 1e-5
    # the blank CAGR was computed from the curve and marked; the risk-sized row, the row without a curve and the row
    # without a max DD are out
    r = rows.set_index("series_id")
    assert bool(r.cagr_derived[f"{T3}:XAUUSDm|v3lite|ADX-20"])
    assert f"{T3}:XAUUSDm|v3lite|MA200-4H" not in order and f"{T3}:XAUUSDm|v3lite|ADX-30" not in order
    assert math.isnan(r.rdd[f"{T3}:XAUUSDm|v3lite|ADX-40"])
    # a source without finalists or champions features its best --top by that ranking, and says so
    kept, cut, how, n, by_role = G.featured(rows, 2)
    assert not by_role and list(kept.series_id) == order[:2] and n == len(order) and how.startswith("best 2")
    _, recs, logs, _ = run3
    eq = [x for x in recs if x["file"] == "equity_XAUUSDm_5y.png"][0]
    assert eq["series_ids"].split(";")[:2] == order[:2]
    assert any(f"the best 2 of {len(order)} ranked rows" in x for x in logs)
    # the families graph ranks without the curve condition (ADX-30 has no curve but the best ADX growth / DD)
    fam = [x for x in recs if x["file"] == "families_XAUUSDm_5y.png"][0]
    assert f"{T3}:XAUUSDm|v3lite|ADX-30" in fam["series_ids"].split(";")


def test_finalists_come_first_then_champions_each_by_growth_over_dd(data):
    rows = G.Source(T2, data).account_rows("5y", "XAUUSDm")
    kept, cut, how, n, by_role = G.featured(rows, 10)
    assert by_role and how == "finalists and champions" and n == 4 and not len(cut)
    roles = list(kept.role)
    assert roles == ["finalist", "finalist", "champion", "champion"]
    for r in ("finalist", "champion"):
        v = list(kept.rdd[kept.role == r])
        assert v == sorted(v, reverse=True)


def test_a_top_cut_is_logged_and_noted(run2):
    _, recs, logs, _ = run2
    cut = [x for x in logs if "--top 3 cut" in x]
    assert cut == [f"{T2} XAUUSDm 5y: --top 3 cut 1 of 4 featured series: {T2}:XAUUSDm|1H|WY|D",
                   f"{T2} XAUUSDm holdout: --top 3 cut 1 of 4 featured series: {T2}:XAUUSDm|1H|WY|D"]
    eq = [r for r in recs if r["file"] == "equity_XAUUSDm_5y.png"][0]
    assert "--top 3 cut 1 of the 4 finalists and champions (1H WY D)." in eq["notes"]
    assert f"{T2}:XAUUSDm|1H|WY|D" not in eq["series_ids"]
    # BTC has one finalist: nothing cut, nothing said
    assert not any("BTCUSDm" in x and "cut" in x for x in logs)


def test_the_axis_scale_the_wiped_corner_and_the_curve_notes(run2, run3):
    _, recs, logs, _ = run2
    by = {r["file"]: r for r in recs}
    assert by["equity_XAUUSDm_5y.png"]["notes"].startswith("y axis log.")          # 50,000 / 2,000 > 20x
    assert by["equity_XAUUSDm_holdout.png"]["notes"].startswith("y axis linear.")
    assert "1 wiped (max DD 99.8%, CAGR −69.8%): off the scale" in by["risk_return_XAUUSDm_5y.png"]["notes"]
    assert any("wrote risk_return_XAUUSDm_5y.png (10 rows, 1 wiped in the corner)" in x for x in logs)
    _, recs3, _, _ = run3
    rr = [r for r in recs3 if r["file"] == "risk_return_XAUUSDm_5y.png"][0]
    assert rr["notes"].startswith("1 rows without a CAGR or max DD not drawn.")


def test_colours_follow_the_page_and_text_wears_the_ink(data, run2, run3):
    slots = G.page_slots(data)
    page = {g["key"]: g["slot"] for g in CP.build_blob(data)["groups"]}
    assert slots == {k: page[k] for k in slots}
    assert slots["bots"] == 0 and slots["benchmarks"] is None
    s2, f10, bh = G.Source(T2, data), G.Source("final10", data), G.Source("benchmarks", data)
    ctx = G.context(s2, f10, bh, slots, "5y", "XAUUSDm", 6, lambda *a: None)
    assert ctx.colour == G.PALETTE[slots[T2]] and ctx.bots == G.PALETTE[slots["bots"]]
    assert {ln.colour for ln in ctx.bhs} == {G.INK}
    assert [ln.dash for ln in ctx.bhs] == [None, G.DASHES[2]]                  # solid, dotted, as on the page
    assert [ln.dash for ln in ctx.featured] == G.DASHES[: len(ctx.featured)]
    assert [ln.colour for ln in ctx.bases] == [ctx.colour] and ctx.base_lines
    # the bars of the families graph wear the source's colour (bot_filters' slot)
    from PIL import Image
    out, _, _, _ = run3
    img = np.asarray(Image.open(out / "families_XAUUSDm_5y.png").convert("RGB")).reshape(-1, 3)
    rgb = tuple(int(G.PALETTE[slots[T3]].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    assert (img == rgb).all(axis=1).sum() > 500
    # every text drawn is in an ink colour, never a series colour
    inks = {G.INK, G.INK2}
    for name, fig in list(run2[3].items()) + list(run3[3].items()):
        texts = list(fig.texts) + [t for ax in fig.axes for t in ax.texts]
        texts += [t for leg in fig.legends for t in list(leg.get_texts()) + [leg.get_title()]]
        assert {_hex(t.get_color()) for t in texts if t.get_text()} <= inks, name
    # the page's light ink tokens and palette
    css = CP.PAGE_CSS.split("@media")[0]
    for name, val in (("--surface", G.SURFACE), ("--ink", G.INK), ("--ink2", G.INK2), ("--grid", G.GRID),
                      ("--axis", G.AXIS)):
        assert re.search(rf"{name}:\s*(#[0-9a-fA-F]{{6}})", css).group(1).lower() == val
    assert G.PALETTE == CP.PALETTE["light"]


def test_colour_distances_are_the_dataviz_validators():
    """validate_palette.js on '#257de0,<hue>' --pairs all (run on 28 Nov 2026): the bots' blue next to each slot a
    source can take. Slots 2-6 pass (CVD >= 8, normal vision >= 15); slot 7 (violet) fails, so pair_ok says so and
    the module adds markers to the bots' lines in that case."""
    blue = G.PALETTE[0]
    measured = {"#f47230": (26.6, 35.2), "#00b894": (22.2, 23.0), "#f2a600": (32.3, 38.4), "#ee7fac": (13.1, 28.1),
                "#008a17": (27.2, 29.2), "#6a4ce2": (4.9, 12.4)}
    for hue, (cvd, normal) in measured.items():
        got_cvd = min(G.colour_distance(blue, hue, "protan"), G.colour_distance(blue, hue, "deutan"))
        assert abs(got_cvd - cvd) < 0.06 and abs(G.colour_distance(blue, hue) - normal) < 0.06, hue
        assert G.pair_ok(blue, hue) == (hue != "#6a4ce2")
    assert G.pair_ok(blue, G.INK)


def test_small_helpers():
    assert G._top_cut([1, 2, 3, 4]) == math.inf
    cut = G._top_cut([1, 2, 3, 4, 100])
    assert 4 < cut < 100
    pos = G._spread([10.0, 11.0, 12.0, 80.0], 8.0, 0.0, 100.0)
    assert all(b - a >= 8.0 - 1e-9 for a, b in zip(pos, pos[1:])) and pos[-1] == 80.0
    assert all(0.0 <= p <= 100.0 for p in G._spread([0.0, 0.0, 0.0], 8.0, 4.0, 100.0))
    assert list(G.drawdown_pct(np.array([2000.0, 2200.0, 1650.0, 2300.0]))) == [0.0, 0.0, -25.0, 0.0]
    assert G.usd(12433.38) == "$12,433" and G.usd(-12.0) == "−$12"
    assert G.wfile("since 2020") == "since_2020"
    assert G._signed(-0.24) == "−0.24" and G._signed(1.304) == "1.30" and G._signed(-0.001) == "0.00"
    assert G.window_text("5y", "2021-11-13", "2026-11-13") == "13 Nov 2021 – 13 Nov 2026, five years"
    assert G._span_text([99.75], G._pct) == "99.8%" and G._span_text([91.3, 100.0], G._pct) == "91.3% to 100.0%"
    assert [G._letter(i) for i in (0, 1, 25, 26, 27)] == ["a", "b", "z", "aa", "ab"]
    k = G.Keys.of(["x", "y"], ["b1", "x"])
    assert (k.text("x"), k.text("y"), k.text("b1"), k.text("?")) == ("1", "2", "a", "")
    assert k.style("x") == (None, None) and k.style("b1") == (G.DASHES[2], None)
    assert G._run_note(TIMINGS) == "8-timing median" and G._run_note("") == "another run"
    assert G._seg_hits((0, 0), (10, 10), (4, 4, 6, 6)) and not G._seg_hits((0, 0), (10, 0), (4, 4, 6, 6))
    assert G._seg_near((0, 0), (10, 0), (5, 3), 4.0) and not G._seg_near((0, 0), (10, 0), (5, 5), 4.0)
    # labels above a plot: the bots' label set left of its line at the right edge spans buy-and-hold's line, so it
    # goes above buy-and-hold's label (whose connector then stops below it); apart labels share row 0
    assert G._label_rows([(1018.0, 1558.0, 1563.0), (1065.0, 1395.0, 1400.0)]) == [1, 0]
    assert G._label_rows([(100.0, 300.0, 95.0), (400.0, 600.0, 395.0)]) == [0, 0]
    assert G._label_rows([(100.0, 300.0, 95.0), (250.0, 450.0, 245.0)]) == [1, 0]


def test_the_command_line(data, tmp_path, capsys):
    recs = G.main(["--source", T2, "--out", str(tmp_path), "--data", str(data), "--windows", "holdout,nope",
                   "--symbols", "XAUUSDm", "--top", "6", "--equity-top", "3"])
    printed = capsys.readouterr().out
    assert sorted(r["file"] for r in recs) == sorted(f"{g}_XAUUSDm_holdout.png" for g in G.GRAPHS)
    assert f"{T2} nope: skipped: the source has no curve file for this window ({T2}__curves_nope.csv.gz)" in printed
    assert (tmp_path / "graphs.csv").exists()
    eq = [r for r in recs if r["graph"] == "equity"][0]
    assert "1 featured not drawn (--equity-top 3)." in eq["notes"]
    with pytest.raises(FileNotFoundError):
        G.draw("no_such_source", tmp_path / "x", data=data, log=lambda *a: None)


def test_no_study_2_or_3_module_is_imported():
    src = Path(G.__file__).read_text(encoding="utf-8")
    names = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [node.module or ""] + [a.name for a in node.names]
    assert names and not [n for n in names if "tradeiq2" in n or "bot_filters" in n]
    assert "import_module" not in src and "__import__" not in src
    local = sorted({n for n in names if n in ("compare_page",)})
    assert local == ["compare_page"]           # the only module of the repository it imports
