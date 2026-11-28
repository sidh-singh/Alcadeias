"""
The comparison page (``backtesting/research/compare_page.py``, ``backtest_results/compare/``).

* The contract: every file in ``backtest_results/compare/data`` has exactly the contract's columns (v2; a v1 file still
  validates), units, dates and unique ids; the adapters re-run into a temporary folder write the same thing; the curve
  conventions and the figures computed from the daily curves on hand-made inputs.
* The numbers: for a sample of series from every source, the contract rows and the page's data blob equal the studies'
  own files (FINAL10, study 1 per 0.01 lot and as accounts, the bots' rebuilds, multisymbol, Balke, the ladder,
  buy-and-hold), keeping their digits.
* The review's findings, one test each: the max DD in $ is on the same marks as the % (never below it); the fields
  computed here are listed and dotted; one window key is one span (the bots' rebuilds have their own windows, with
  buy-and-hold over the same span); in / out of sample; the sizing and FINAL10's tags; the palette slots and their
  colour distances; the reader's pending text; the --allow-pre-2019 gate; and, in a headless browser, the dashes, the
  Top 10, the link, the sort, the disabled switches, the sticky bars and the escaped labels.
* The builder: with studies 2 and 3 absent the page builds, its data blob parses and lists them as pending; with a small
  fake study 2 present it picks it up; the page makes no request.
* Study 1 on 5y: two variants (gold QQE finalist; BTC VWRSI on Binance volume with the S1 stop) recomputed with study 1's
  own code on M1 bars from 2019 equal the exported curve and rows, the $ drawdown on its M1 marks included (needs the
  tick store; skipped without it).
* The hard rules: nothing before 2019-01-01 is loaded or computed without --allow-pre-2019 and study 2's exam; no
  study-2 module is imported.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.research import compare_page as C

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "backtest_results" / "compare" / "data"
PAGE = REPO / "backtest_results" / "compare" / "index.html"
RES = REPO / "backtest_results"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
need_data = pytest.mark.skipif(not (DATA / "final10__series.csv").exists(), reason="run compare_page export first")


def _close(a, b, tol=1e-4):
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return b is None or (isinstance(b, float) and math.isnan(b)) or b == ""
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def _row(m: pd.DataFrame, sid: str, window: str, basis: str = "account", cost: float = 1.0) -> pd.Series:
    r = m[(m.series_id == sid) & (m.window == window) & (m.basis == basis) & (m.cost.astype(float) == cost)]
    assert len(r) == 1, (sid, window, basis, cost, len(r))
    return r.iloc[0]


def _blob(html_text: str) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html_text, re.S)
    assert m, "no data blob in the page"
    return C.unpack_blob(json.loads(m.group(1)))


def _metrics(sid: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{sid}__metrics.csv", dtype=str, keep_default_na=False)


# ───────────────────────────── the contract ─────────────────────────────

@need_data
def test_every_contract_file_validates():
    rep = C.validate(DATA)
    assert rep["errors"] == []
    # the only warnings: FINAL10's 1y tick rows (median row, middle-run curve); no window key spans two dates
    for w in rep["warnings"]:
        assert w.startswith("final10 curves 1y: final10:"), w
    sids = C.sources_in(DATA)
    assert {"final10", "tradeiq_rsi", "benchmarks", "balke", "ladder"} <= set(sids)
    ids = []
    for sid in sids:
        s, m, cv = C.read_source(sid, DATA, raw=True)
        assert list(s.columns) == C.SERIES_COLS + C.SERIES_OPT and list(m.columns) == C.METRICS_COLS + C.METRICS_OPT
        ids += s.series_id.tolist()
        acc, unit = m[m.basis == "account"], m[m.basis == "unit"]
        assert (acc.start_usd.astype(float) == 2000.0).all()
        assert (unit.start_usd.astype(float) == 0.0).all()
        assert (unit.return_pct == "").all() and (unit.max_dd_pct == "").all()
        for col in ("start", "end"):
            assert m[col].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
        assert (m.start < m.end).all()
        for w, c in cv.items():
            assert list(c.columns) == C.CURVE_COLS
            assert c.date.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
            assert set(c.series_id) <= set(s.series_id)
            first = c.groupby("series_id").first()
            assert (first.equity_usd == 2000.0).all()
    assert len(ids) == len(set(ids))


def test_a_v1_file_without_the_optional_columns_still_validates(tmp_path):
    """Studies 2 and 3 may write the v1 columns only: valid, and read with the optional columns empty."""
    _fake_study2(tmp_path, v1=True)
    assert list(pd.read_csv(tmp_path / "tradeiq_2027__series.csv").columns) == C.SERIES_COLS
    assert C.validate(tmp_path)["errors"] == []
    s, m, _ = C.read_source("tradeiq_2027", tmp_path)
    assert list(s.columns) == C.SERIES_COLS + C.SERIES_OPT and (m["sample"] == "").all()
    m2 = pd.read_csv(tmp_path / "tradeiq_2027__metrics.csv", dtype=str, keep_default_na=False)
    m2.insert(len(m2.columns), "bogus", "")
    m2.to_csv(tmp_path / "tradeiq_2027__metrics.csv", index=False)
    assert any("columns" in e for e in C.validate(tmp_path)["errors"])


@need_data
def test_adapters_rewrite_the_same_files(tmp_path):
    """The file-based sources re-exported into a temporary folder validate and equal the committed files."""
    for sid, fn in (("final10", C.final10_series_and_metrics), ("balke", C.balke_source),
                    ("ladder", C.ladder_source), ("tradeiq_rsi", C.tiq_static)):
        s, m, cv = fn()
        C.write_source(sid, s, m, cv, data=tmp_path, replace=True)
    rep = C.validate(tmp_path)
    assert rep["errors"] == []
    for sid in ("final10", "balke", "ladder"):
        a = pd.read_csv(tmp_path / f"{sid}__metrics.csv", dtype=str, keep_default_na=False)
        b = _metrics(sid)
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
        a = pd.read_csv(tmp_path / f"{sid}__series.csv", dtype=str, keep_default_na=False)
        b = pd.read_csv(DATA / f"{sid}__series.csv", dtype=str, keep_default_na=False)
        pd.testing.assert_frame_equal(a, b)
    a = pd.read_csv(tmp_path / "tradeiq_rsi__metrics.csv", dtype=str, keep_default_na=False)
    b = _metrics("tradeiq_rsi")
    b = b[b.window.isin(C.TIQ_OWN_WINDOWS)]
    key = ["series_id", "window", "basis", "cost"]
    pd.testing.assert_frame_equal(a.sort_values(key).reset_index(drop=True), b.sort_values(key).reset_index(drop=True))
    for w in ("5y", "8y", "bots-holdout"):
        x = pd.read_csv(C.curve_file("final10", w, tmp_path))
        y = pd.read_csv(C.curve_file("final10", w, DATA))
        pd.testing.assert_frame_equal(x, y)
    # a window a source no longer has leaves no curve file behind
    assert not C.curve_file("final10", "holdout", DATA).exists() and not C.curve_file("final10", "full", DATA).exists()


def test_curve_conventions_on_hand_made_points():
    # start-of-day marks (final10 / balke): day D carries the next day's opening mark, the last day the final
    c = C.eod_from_sod(["2021-11-14", "2021-11-15", "2021-11-16"], [2000.0, 2010.0, 1990.0], 1995.0, "2021-11-13")
    assert c.date.tolist() == ["2021-11-12", "2021-11-14", "2021-11-15", "2021-11-16"]
    assert c.equity_usd.tolist() == [2000.0, 2010.0, 1990.0, 1995.0]
    # midnight marks (study 1): a midnight is the end of the day before; days without a bar are dropped
    t = [C._s(x) for x in ("2024-07-01", "2024-07-02", "2024-07-03", "2024-07-04")]
    c = C.eod_from_midnights(t, [2000.0, 2001.0, 2001.0, 2003.0], [True, True, False, True])
    assert c.date.tolist() == ["2024-06-30", "2024-07-01", "2024-07-03"]
    assert c.equity_usd.tolist() == [2000.0, 2001.0, 2003.0]
    # end-of-day marks (multisymbol): the opening row is added
    c = C.eod_from_daily(["2024-05-13", "2024-05-14"], [2005.0, 2007.0], "2024-05-13")
    assert c.date.tolist() == ["2024-05-12", "2024-05-13", "2024-05-14"]
    assert C.curve_file("balke", "since 2020", Path("/x")).name == "balke__curves_since_2020.csv.gz"


def test_curve_stats_on_a_hand_made_curve():
    # 2023: flat to 31 Mar, +100 in Q2, -50 in Q3 (a dip of 80 in Aug, back by 30 Sep), +20 in Q4
    days = pd.date_range("2022-12-31", "2023-12-31", freq="D")
    e = np.full(len(days), 2000.0)
    s = pd.Series(e, index=days)
    s[s.index >= "2023-04-03"] = 2100.0
    s[(s.index >= "2023-08-01") & (s.index < "2023-09-01")] = 2020.0
    s[s.index >= "2023-09-01"] = 2050.0
    s[s.index >= "2023-11-01"] = 2070.0
    st = C.curve_stats([d.strftime("%Y-%m-%d") for d in s.index], s.to_numpy(), "2023-01-01", "2024-01-01")
    assert st["pos_quarters_pct"] == 50.0                      # Q1 0, Q2 +100, Q3 -50, Q4 +20
    assert st["worst_quarter_usd"] == -50.0
    assert st["worst_month_usd"] == -80.0                      # August
    assert st["losing_months"] == 1 and st["months"] == 12
    assert st["max_dd_usd_daily"] == 80.0
    assert abs(st["max_dd_pct_daily"] - 80 / 2100 * 100) < 1e-9
    assert st["underwater_days"] == (pd.Timestamp("2024-01-01") - pd.Timestamp("2023-08-01")).days
    assert abs(st["cagr_pct"] - ((2070 / 2000) ** (1 / (365 / 365.25)) - 1) * 100) < 1e-9
    wk = np.diff(np.r_[2000.0, [s[s.index <= d - pd.Timedelta(days=1)].iloc[-1]
                                for d in pd.date_range("2023-01-07", "2023-12-30", freq="7D")], 2070.0])
    assert abs(st["sharpe_w"] - wk.mean() / wk.std(ddof=1) * math.sqrt(52)) < 1e-9


def test_fill_from_curve_keeps_the_dollar_drawdown_on_the_rows_own_marks():
    """A % on finer marks never gets a $ figure off the daily curve; a day-marked row does; both list what was filled."""
    days = pd.date_range("2023-12-31", "2024-12-31", freq="D")
    eq = 2000.0 + 400.0 * np.sin(np.arange(len(days)) / 30.0) ** 2
    cv = pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "equity_usd": eq})
    base = dict(start="2024-01-01", end="2025-01-01", basis="account", start_usd=2000.0, net_usd=100.0,
                final_usd=2100.0, max_dd_pct=30.0)
    fine = C.fill_from_curve(dict(base, dd_marks="M1"), cv)
    assert C._blank(fine.get("max_dd_usd")) and C._blank(fine.get("p_dd"))
    assert set(fine["derived"].split(",")) == {"return_pct", "cagr_pct", "sharpe_w", "pos_quarters_pct",
                                               "worst_quarter_usd"}
    day = C.fill_from_curve(dict(base, dd_marks="day"), cv)
    assert day["max_dd_usd"] > 0 and abs(day["p_dd"] - 100.0 / day["max_dd_usd"]) < 1e-12
    assert {"max_dd_usd", "p_dd"} <= set(day["derived"].split(","))


# ───────────────────────────── the numbers equal the sources ─────────────────────────────

@need_data
def test_final10_and_its_other_windows_equal_their_files():
    m = _metrics("final10")
    res = pd.read_csv(RES / "final10" / "results.csv")
    sample = res[res.label.isin(["V3-lite", "Top 2", "Turtle (risk-sized)", "London breakout + H1 trend", "Live",
                                 "Turtle [alt] + bot votes", "V3-lite + 12-month momentum filter, as the bot runs it"])]
    assert len(sample) >= 30
    for _, r in sample.iterrows():
        row = _row(m, f"final10:{r.symbol}|{r.label}", r.window)
        for a, b in (("final_usd", "final_equity"), ("net_usd", "net"), ("max_dd_pct", "max_dd_pct"),
                     ("cagr_pct", "cagr_pct"), ("trades", "trades"), ("win_rate_pct", "win_rate_pct")):
            assert _close(row[a], r[b]), (r.label, r.window, a)
        if not pd.isna(r.profit_factor):
            assert _close(row.profit_factor, r.profit_factor)
        assert int(row.wiped) == int(bool(r.wiped))
        # FINAL10 publishes the drawdown in % only: no $ figure off its daily curve
        assert row.max_dd_usd == "" and row.p_dd == ""
    s = pd.read_csv(DATA / "final10__series.csv", keep_default_na=False).set_index("series_id")
    from backtesting.research import tradeiq as T
    assert sorted(s[s.role == "design"].index) == sorted(f"final10:{x[0]}|{x[1]}" for x in T.BOT_DESIGNS)
    assert (s.role == "finalist").sum() + 2 == 20                 # the ten per symbol (gold V3-lite, BTC Top 2: design)
    assert "final ten #7" in s.loc["final10:XAUUSDm|V3-lite"].notes
    # FINAL10's yardstick as study 3 quotes it (PREREG table): V3-lite 3.09, Top 2 BTC 4.49, Turtle S2 4.65
    for sid, v in (("final10:XAUUSDm|V3-lite", 3.09), ("final10:BTCUSDm|Top 2", 4.49),
                   ("final10:BTCUSDm|Turtle [alt] + bot votes", 4.65), ("final10:XAUUSDm|Top 2", 6.20)):
        assert round(float(_row(m, sid, "5y").score_final10), 2) == v
    # the bots rebuilt by study 1 on its spans (under their own window keys), and multisymbol's base rows
    cs = pd.read_csv(RES / "tradeiq_rsi" / "curves_summary.csv")
    cs = cs[cs.source == "the bots' designs (final10)"]
    for _, r in cs.iterrows():
        label = {v: k[1] for k, v in C.TIQ_BOT_NAME.items() if k[0] == r.symbol}[r["name"]]
        row = _row(m, f"final10:{r.symbol}|{label}", C.REBUILD_WINDOW[r.window])
        assert _close(row.final_usd, r.final_equity) and _close(row.max_dd_pct, r.max_dd_pct)
        assert int(row.trades) == int(r.trades) and row.dd_marks == "day"
        assert (row.start, row.end) == (C._iso(r.start), C._iso(r.end))
    mr = pd.read_csv(RES / "multisymbol" / "runs.csv")
    mr = mr[mr.symbol.isin(C.SYMBOLS) & (mr.account == "a") & (mr.role == "base") & (mr.period != "8y")]
    assert len(mr) == 14
    for _, r in mr.iterrows():
        row = _row(m, f"final10:{r.symbol}|{C.MULTI_DESIGN[(r.symbol, r.design)]}", r.period)
        for a, b in (("final_usd", "final_equity"), ("net_usd", "profit"), ("max_dd_usd", "max_dd_usd"),
                     ("max_dd_pct", "max_dd_pct"), ("trades", "trades")):
            assert _close(row[a], r[b]), (r.design, r.period, a)


@need_data
def test_multisymbol_rows_use_the_uniform_definitions_and_keep_their_own_in_the_notes():
    """Review: multisymbol's quarters are 3-month blocks and its Sharpe x sqrt(52.18); the columns are the page's
    uniform ones (computed from its daily curve, listed in derived), its own figures stay in the row notes."""
    m = _metrics("final10")
    mr = pd.read_csv(RES / "multisymbol" / "runs.csv")
    mr = mr[mr.symbol.isin(C.SYMBOLS) & (mr.account == "a") & (mr.role == "base") & (mr.period != "8y")]
    for _, r in mr.iterrows():
        sid = f"final10:{r.symbol}|{C.MULTI_DESIGN[(r.symbol, r.design)]}"
        row = _row(m, sid, r.period)
        assert {"sharpe_w", "pos_quarters_pct", "worst_quarter_usd", "return_pct", "cagr_pct"} <= \
            set(row.derived.split(","))
        assert f"{int(r.pos_quarters)} of {int(r.n_quarters)} 3-month blocks" in row.row_notes
        assert f"{float(r.sharpe_weekly):.2f} (x sqrt 52.18)" in row.row_notes
        cv = pd.read_csv(C.curve_file("final10", r.period, DATA))
        g = cv[cv.series_id == sid]
        st = C.curve_stats(g.date.to_numpy(), g.equity_usd.to_numpy(), row.start, row.end)
        assert abs(float(row.sharpe_w) - st["sharpe_w"]) < 1e-5
        assert abs(float(row.pos_quarters_pct) - st["pos_quarters_pct"]) < 1e-3


@need_data
def test_study1_rows_equal_its_files():
    m = pd.read_csv(DATA / "tradeiq_rsi__metrics.csv", keep_default_na=False)
    rng = np.random.default_rng(20261128)
    for f in ("results_dev_val.csv", "results_holdout.csv", "results_full.csv"):
        res = pd.read_csv(RES / "tradeiq_rsi" / f, float_precision="round_trip")
        for k in rng.choice(len(res), 25, replace=False):
            r = res.iloc[int(k)]
            for cost, sfx in ((1.0, ""), (1.5, "_x15")):
                row = _row(m, f"tradeiq_rsi:{r.vid}", r.window, "unit", cost)
                for a, b in (("net_usd", "net"), ("max_dd_usd", "max_dd"), ("p_dd", "profit_dd"),
                             ("trades", "trades"), ("win_rate_pct", "win_rate"), ("profit_factor", "profit_factor"),
                             ("sharpe_w", "sharpe_w")):
                    if not pd.isna(r[b + sfx]):
                        assert _close(row[a], r[b + sfx]), (r.vid, r.window, cost, a)
                assert _close(row.pos_quarters_pct, float(r["pos_q_share" + sfx]) * 100.0)
    cs = pd.read_csv(RES / "tradeiq_rsi" / "curves_summary.csv")
    cs = cs[(cs.source == "TradeIQ study") & ~cs.vid.str.endswith("buy-and-hold")]
    assert len(cs) == 38
    for _, r in cs.iterrows():
        row = _row(m, f"tradeiq_rsi:{r.vid}", r.window)
        assert _close(row.final_usd, r.final_equity) and _close(row.max_dd_pct, r.max_dd_pct)
        assert int(row.trades) == int(r.trades) and row.dd_marks == "M1"
        assert row.max_dd_usd == ""                     # its M1-mark $ drawdown is not in the files
    s = pd.read_csv(DATA / "tradeiq_rsi__series.csv", keep_default_na=False)
    assert len(s) == 750 and (s.role == "finalist").sum() == 6
    ex = s[s.exam != ""]
    assert sorted(ex[ex.symbol == "XAUUSDm"].exam) == ["pass"] * 3
    assert sorted(ex[ex.symbol == "BTCUSDm"].exam) == ["fail", "fail", "pass"]
    # 5y and 1y: every variant, as an account (its $ drawdown on its M1 marks) and per 0.01 lot
    for w in ("5y", "1y"):
        part = m[m.window == w]
        assert len(part) == 1500 and set(part.basis) == {"account", "unit"}
        acc = part[part.basis == "account"]
        assert len(acc) == 750 and (acc.max_dd_usd != "").all() and (acc.p_dd != "").sum() >= 745


@need_data
def test_balke_ladder_and_benchmarks_equal_their_files():
    m = pd.read_csv(DATA / "balke__metrics.csv", keep_default_na=False)
    res = pd.read_csv(RES / "balke" / "results.csv")
    res = res[res.symbol.isin(C.SYMBOLS) & (res.sizing == "bot unit rule") & ~res.bench.astype(bool)]
    assert len(res) == len(m) == 40
    for _, r in res.iterrows():
        row = _row(m, f"balke:{r.symbol}|{r.label}", r.window)
        for a, b in (("final_usd", "final_equity"), ("max_dd_pct", "max_dd_pct"), ("trades", "trades"),
                     ("win_rate_pct", "win_rate_pct"), ("profit_factor", "profit_factor")):
            assert _close(row[a], r[b])
        assert row.max_dd_usd == ""                    # Balke publishes the drawdown in % only
    m = pd.read_csv(DATA / "ladder__metrics.csv", keep_default_na=False)
    for w in ("8y", "5y", "1y"):
        d = pd.read_csv(RES / "ladder" / "runs_XAUUSDm" / f"cont_{w}.csv")
        for code, (short, _, _) in C.LADDER_DESIGNS.items():
            g = d[d.design == code]
            row = _row(m, f"ladder:XAUUSDm|{short}", w)
            assert _close(row.net_usd, float(np.median(g.net))) and _close(row.max_dd_pct, float(np.median(g.max_dd_pct)))
            assert set(row.derived.split(",")) == {"return_pct", "cagr_pct"}
    m = pd.read_csv(DATA / "benchmarks__metrics.csv", keep_default_na=False)
    for f in ("buy_and_hold.csv", "buy_and_hold_exam.csv"):
        for _, r in pd.read_csv(RES / "tradeiq_rsi" / f).iterrows():
            row = _row(m, f"benchmarks:{r.symbol}|bh-0.01lot", r.window, "unit", float(r.cost))
            assert _close(row.net_usd, r.bh_net) and _close(row.max_dd_usd, r.bh_max_dd)
    cs = pd.read_csv(RES / "tradeiq_rsi" / "curves_summary.csv")
    for _, r in cs[cs.vid.str.endswith("buy-and-hold")].iterrows():
        row = _row(m, f"benchmarks:{r.symbol}|bh-0.01lot", r.window)
        assert _close(row.final_usd, r.final_equity) and _close(row.max_dd_pct, r.max_dd_pct)
    # $2,000 fully invested: the same move as 0.01 lot, scaled by 2,000 / (entry ask x 0.01 lot's size)
    for sym in C.SYMBOLS:
        for w in ("5y", "1y", "full", "holdout") + tuple(C.BH_EXTRA):
            a, b = _row(m, f"benchmarks:{sym}|bh-2000", w), _row(m, f"benchmarks:{sym}|bh-0.01lot", w, "unit")
            assert math.copysign(1, float(a.net_usd)) == math.copysign(1, float(b.net_usd))
            assert _close(float(a.net_usd) / float(a.max_dd_usd), float(b.net_usd) / float(b.max_dd_usd), 1e-6)
            assert int(a.trades) == 1 and int(a.wiped) == 0


@need_data
def test_the_page_carries_the_source_numbers_with_their_digits():
    """Review: values were rounded into the blob and again on display; the blob now keeps the contract's digits."""
    blob = C.unpack_blob(json.loads(C._json(C.pack_blob(C.build_blob(DATA)))))
    S, M = blob["S"], blob["M"]
    idx = {sid: i for i, sid in enumerate(S["id"])}
    wkeys = [w["key"] for w in blob["windows"]]
    rows = {}
    for j in range(len(M["s"])):
        rows[(S["id"][M["s"][j]], wkeys[M["w"][j]], M["b"][j], M["c"][j])] = j
    # every number of the contract reaches the page as written (here: all of FINAL10 and Balke)
    for sid in ("final10", "balke"):
        for _, r in _metrics(sid).iterrows():
            j = rows[(r.series_id, r.window, 0 if r.basis == "account" else 1, float(r.cost))]
            for k, col in (("net", "net_usd"), ("ddp", "max_dd_pct"), ("pf", "profit_factor"), ("cagr", "cagr_pct"),
                           ("win", "win_rate_pct"), ("pq", "pos_quarters_pct"), ("sh", "sharpe_w")):
                assert (M[k][j] is None and r[col] == "") or M[k][j] == float(r[col]), (r.series_id, r.window, k)
    # e.g. Balke's Range Breakout gold 5y max DD 32.3499%: rounded once it is 32.3% (the page used to show 32.4%)
    b = _metrics("balke")
    r = b[(b.window == "5y") & (b.max_dd_pct == "32.3499")].iloc[0]
    j = rows[(r.series_id, "5y", 0, 1.0)]
    assert M["ddp"][j] == 32.3499 and f"{M['ddp'][j]:.1f}" == "32.3"
    res = pd.read_csv(RES / "final10" / "results.csv")
    for _, r in res[res.label.isin(["V3-lite", "Top 2", "Turtle (risk-sized)"])].iterrows():
        j = rows[(f"final10:{r.symbol}|{r.label}", r.window, 0, 1.0)]
        assert abs(M["net"][j] - r.net) <= 1e-4 and abs(M["ddp"][j] - r.max_dd_pct) <= 1e-4
        assert M["tr"][j] == r.trades
        # growth / DD: FINAL10's own "growth per year / DD" (results.csv return_per_dd)
        assert abs(M["rdd"][j] - r.return_per_dd) < 2e-3 * max(1.0, abs(r.return_per_dd)), (r.label, r.window)
    cs = pd.read_csv(RES / "tradeiq_rsi" / "results_holdout.csv")
    for _, r in cs.head(40).iterrows():
        j = rows[(f"tradeiq_rsi:{r.vid}", "holdout", 1, 1.0)]
        assert abs(M["net"][j] - r.net) <= 1e-4 and abs(M["ddu"][j] - r.max_dd) <= 1e-4
    # the curves the page draws decode back to the contract's values (whole dollars)
    cv = pd.read_csv(C.curve_file("final10", "5y", DATA))
    g = cv[cv.series_id == "final10:XAUUSDm|V3-lite"]
    d0, step, deltas, last_off, last_val = blob["C"]["5y"][str(idx["final10:XAUUSDm|V3-lite"])]
    vals = np.cumsum([int(x) for x in deltas.split(",")])
    assert step == 1 and d0 == C._dnum(g.date.iloc[0]) and last_val == round(float(g.equity_usd.iloc[-1]))
    by_day = dict(zip([C._dnum(x) for x in g.date], np.round(g.equity_usd.to_numpy())))
    for k, v in enumerate(vals):
        if d0 + k in by_day:
            assert v == by_day[d0 + k]


# ───────────────────────────── the review's findings ─────────────────────────────

@need_data
def test_the_dollar_drawdown_is_on_the_same_marks_as_the_percent():
    """Review blocker: max DD $ (and P/DD) came off the daily curve next to a % on finer marks, often below the %'s
    bound. Now it is the same marks or empty, and check refuses a $ figure below max DD % x $2,000."""
    n = 0
    for sid in C.sources_in(DATA):
        m = _metrics(sid)
        acc = m[(m.basis == "account") & (m.max_dd_usd != "")]
        for _, r in acc.iterrows():
            assert float(r.max_dd_usd) >= float(r.max_dd_pct) / 100.0 * 2000.0 - 0.01, (r.series_id, r.window)
            n += 1
        if sid in ("final10",):
            day = m[m.dd_marks == "day"]
            assert (day.max_dd_usd != "").all() and (m[(m.dd_marks != "day") & (m.source_file.str.contains(
                "final10/"))].max_dd_usd == "").all()
    assert n > 1500
    # the page's own figure at daily closes is a separate, page-only field, smaller where the study marks finer
    blob = C.build_blob(DATA)
    S, M = blob["S"], blob["M"]
    j = [k for k in range(len(M["s"])) if S["id"][M["s"][k]] == "final10:XAUUSDm|V3-lite"
         and blob["windows"][M["w"][k]]["key"] == "5y"][0]
    cv = pd.read_csv(C.curve_file("final10", "5y", DATA))
    g = cv[cv.series_id == "final10:XAUUSDm|V3-lite"]
    st = C.curve_stats(g.date.to_numpy(), g.equity_usd.to_numpy(), "2021-11-13", "2026-11-13")
    assert M["ddu"][j] is None and abs(M["dly"][j] - st["max_dd_usd_daily"]) < 1e-3
    assert st["max_dd_pct_daily"] < M["ddp"][j]           # daily closes: 21.1% against FINAL10's own 30.6%


def test_validate_flags_a_dollar_drawdown_below_its_percent(tmp_path):
    _fake_study2(tmp_path)
    m = pd.read_csv(tmp_path / "tradeiq_2027__metrics.csv", dtype=str, keep_default_na=False)
    m.loc[m.basis == "account", "max_dd_usd"] = "100.0"            # 12.5% of $2,000 is $250
    m.to_csv(tmp_path / "tradeiq_2027__metrics.csv", index=False)
    assert any("below its 12.50%" in e for e in C.validate(tmp_path)["errors"])


@need_data
def test_the_fields_computed_here_are_listed_and_reach_the_page():
    """Review major: the page promised a dotted marker for computed values but never drew one (export had already
    filled them). The contract now lists them in ``derived`` and the page reads the list."""
    m = _metrics("final10")
    row = _row(m, "final10:XAUUSDm|V3-lite", "5y")
    assert row.derived.split(",") == ["sharpe_w", "pos_quarters_pct", "worst_quarter_usd"]
    blob = C.build_blob(DATA)
    S, M = blob["S"], blob["M"]
    j = [k for k in range(len(M["s"])) if S["id"][M["s"][k]] == "final10:XAUUSDm|V3-lite"
         and blob["windows"][M["w"][k]]["key"] == "5y"][0]
    assert M["der"][j] == "sharpe_w,pos_quarters_pct,worst_quarter_usd"
    # the page's script maps every derivable field to its column
    js = C.PAGE_JS
    for f in C.DERIVABLE:
        assert re.search(rf"\b{f}: \"\w+\"", js), f


@need_data
def test_one_window_key_is_one_span_and_the_rebuilds_have_their_own():
    """Review major: on 'full' and 'holdout' the bots' designs ended on 13 Nov 2026 and everything else at the data end.
    The rebuilds now sit on bots-full / bots-holdout, with buy-and-hold over exactly the same span."""
    spans = {}
    for sid in C.sources_in(DATA):
        s, m, _ = C.read_source(sid, DATA)
        sym = dict(zip(s.series_id, s.symbol))
        for _, r in m.iterrows():
            spans.setdefault((r.window, sym[r.series_id]), set()).add((r.start, r.end))
    bad = {k: v for k, v in spans.items() if len(v) > 1}
    assert bad == {}
    assert spans[("bots-holdout", "BTCUSDm")] == {("2024-07-01", "2026-11-13")}
    assert spans[("holdout", "BTCUSDm")] == {("2024-07-01", "2026-11-27")}
    m = _metrics("final10")
    assert not m.window.isin(["full", "holdout"]).any()
    b = _metrics("benchmarks")
    for w in ("bots-full", "bots-holdout", "sel", "conf", "since 2020"):
        assert len(b[(b.window == w) & (b.basis == "account")]) == 4, w


@need_data
def test_in_and_out_of_sample_flags():
    """Review major: the hold-out view put the bots' in-sample designs beside study 1's examined finalists."""
    m = _metrics("final10")
    by = m.groupby("window")["sample"].agg(lambda x: set(x))
    assert by["new"] == {"out"} and by["5y"] == {"in"} and by["1y"] == {"in"} and by["8y"] == {"mixed"}
    assert by["bots-holdout"] == {"in"} and by["conf"] == {"in"} and by["sel"] == {"in"}
    t = _metrics("tradeiq_rsi")
    tb = t.groupby("window")["sample"].agg(lambda x: set(x))
    assert tb["holdout"] == {"out"} and tb["1y"] == {"out"} and tb["dev"] == {"in"} and tb["5y"] == {"mixed"}
    # the hold-out window holds only out-of-sample rows (and buy-and-hold)
    blob = C.build_blob(DATA)
    S, M = blob["S"], blob["M"]
    w_ho = [w["key"] for w in blob["windows"]].index("holdout")
    srcs = {S["src"][M["s"][j]] for j in range(len(M["s"])) if M["w"][j] == w_ho}
    assert srcs == {"tradeiq_rsi", "benchmarks"}
    assert {M["smp"][j] for j in range(len(M["s"])) if M["w"][j] == w_ho and S["src"][M["s"][j]] != "benchmarks"} \
        == {"out"}


@need_data
def test_sizing_tags_and_the_warm_recheck():
    """Review minors: the risk-sized rows were unflagged; FINAL10's two gold hybrids that its warm re-check finds
    ineligible said nothing; references looked like candidates."""
    s = pd.read_csv(DATA / "final10__series.csv", keep_default_na=False).set_index("series_id")
    risk = set(s[s.sizing == "risk-sized"].index)
    assert risk == {"final10:BTCUSDm|Turtle (risk-sized)", "final10:XAUUSDm|London breakout (risk-sized)",
                    "final10:XAUUSDm|Noise-area momentum (risk-sized)", "final10:BTCUSDm|TSMOM [alt] (risk-sized)"}
    warm_out = {i for i, t in s.tags.items() if "not eligible on the warm re-check" in t}
    assert warm_out == {"final10:XAUUSDm|V3-lite + 200-day trend filter",
                        "final10:XAUUSDm|V3-lite + 12-month momentum filter"}
    assert "section 8" in s.loc["final10:XAUUSDm|V3-lite + 200-day trend filter"].notes
    assert "reference, not a candidate" in s.loc["final10:XAUUSDm|Top 2"].tags
    assert int(s.loc["final10:XAUUSDm|Top 2"].eligible) == 0
    b = pd.read_csv(DATA / "benchmarks__series.csv", keep_default_na=False)
    assert set(b.sizing) == {"fully invested", "0.01 lot fixed"}


# the dataviz validator's colour math (OKLab x 100; Machado 2009 at severity 1), for the build check
_MACHADO = {"protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                       [-0.003882, -0.048116, 1.051998]],
            "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                       [-0.011820, 0.042940, 0.968881]]}


def _lin(h):
    def s2l(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return [s2l(int(h.lstrip("#")[i:i + 2], 16) / 255) for i in (0, 2, 4)]


def _oklab(rgb):
    r, g, b = rgb
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def _de(h1, h2, kind=None):
    def sim(h):
        x = _lin(h)
        if kind is None:
            return x
        M = _MACHADO[kind]
        return [max(0.0, min(1.0, sum(M[i][j] * x[j] for j in range(3)))) for i in range(3)]
    return 100 * math.dist(_oklab(sim(h1)), _oklab(sim(h2)))


def test_palette_slots_follow_the_groups_present_and_pass_the_colour_checks():
    """Review major: slots were reserved for absent studies, so study 1 (aqua) sat next to Balke (green), a pair the
    validated order never makes adjacent. Slots now go in palette order to the groups present, those with curves first;
    the adjacent pairs of the displayed list clear the dataviz floors (CVD >= 8, normal vision >= 15) in both modes."""
    today = C.group_slots({"bots": True, "final10": True, "tradeiq_rsi": True, "balke": True, "earlier": False,
                           "benchmarks": True})
    assert today == {"bots": 0, "final10": 1, "tradeiq_rsi": 2, "balke": 3, "earlier": 4, "benchmarks": None}
    later = C.group_slots({"bots": True, "final10": True, "tradeiq_rsi": True, "tradeiq_2027": True,
                           "bot_filters": True, "balke": True, "earlier": False, "benchmarks": True})
    assert [later[k] for k in ("bots", "final10", "tradeiq_rsi", "tradeiq_2027", "bot_filters", "balke", "earlier")] \
        == list(range(7))
    for slots in (today, later):
        shown = sorted(v for v in slots.values() if v is not None)
        assert shown == list(range(len(shown)))                  # never a skipped slot
        for mode in ("light", "dark"):
            hues = [C.PALETTE[mode][i] for i in shown]
            for a, b in zip(hues, hues[1:]):
                assert min(_de(a, b, "protan"), _de(a, b, "deutan")) >= 8.0, (mode, a, b)
                assert _de(a, b) >= 15.0, (mode, a, b)


@need_data
def test_the_committed_page_uses_the_present_groups_slots():
    blob = _blob(PAGE.read_text(encoding="utf-8"))
    slots = {g["key"]: g["slot"] for g in blob["groups"]}
    assert slots["bots"] == 0 and slots["final10"] == 1 and slots["tradeiq_rsi"] == 2 and slots["balke"] == 3
    assert slots["tradeiq_2027"] is None and slots["bot_filters"] is None and slots["benchmarks"] is None


@need_data
def test_pending_text_is_for_readers_and_missing_windows_are_reported():
    """Review minor: the pending notes printed a shell command and explained BTC with gold's sealed window."""
    blob = C.build_blob(DATA)
    for p in blob["pending"]:
        assert "python3" not in p["text"] and "--allow" not in p["text"] and "gold 2017" not in p["text"]
    assert {(p["src"], p["w"]) for p in blob["pending"]} >= {("tradeiq_rsi", "8y"), ("benchmarks", "new")}
    miss = {(x["src"], x["sym"]): x for x in blob["missing"]}
    assert miss[("ladder", "XAUUSDm")]["w"] == ["new"] and miss[("ladder", "XAUUSDm")]["later"] == []
    assert miss[("tradeiq_rsi", "BTCUSDm")]["later"] == ["8y", "new"]
    assert C.windows_note(blob) == "the window every source on this page has"


# ───────────────────────────── the builder ─────────────────────────────

def _fake_study2(folder: Path, v1: bool = False) -> None:
    """A small study 2 in the contract: two series, a 5y account and a per-lot hold-out row, one curve with gaps."""
    s = pd.DataFrame([dict(series_id="tradeiq_2027:XAUUSDm|1H|RIBBON|A", source="tradeiq_2027", study="TradeIQ video 2",
                           symbol="XAUUSDm", label="1H ribbon A <b>x</b> & %{y}", kind="rule", family="ribbon",
                           tf="1H", filter="", role="finalist", eligible=1, exam="pass", notes="fake"),
                      dict(series_id="tradeiq_2027:BTCUSDm|4H|ORB|B", source="tradeiq_2027", study="TradeIQ video 2",
                           symbol="BTCUSDm", label="4H ORB B", kind="rule", family="orb", tf="4H", filter="",
                           role="variant", eligible=0, exam="", notes="fake")])
    m = pd.DataFrame([dict(series_id="tradeiq_2027:XAUUSDm|1H|RIBBON|A", window="5y", start="2021-11-13",
                           end="2026-11-13", cost=1.0, basis="account", start_usd=2000.0, final_usd=2600.0,
                           net_usd=600.0, return_pct=30.0, cagr_pct="", max_dd_usd="", max_dd_pct=12.5, p_dd="",
                           trades=40, win_rate_pct=45.0, profit_factor=1.4, sharpe_w="", pos_quarters_pct="",
                           worst_quarter_usd="", wiped=0, dd_marks="M1", score_final10="", source_file="fake"),
                      dict(series_id="tradeiq_2027:BTCUSDm|4H|ORB|B", window="holdout", start="2024-07-01",
                           end="2026-11-27", cost=1.0, basis="unit", start_usd=0.0, final_usd=-12.0, net_usd=-12.0,
                           return_pct="", cagr_pct="", max_dd_usd=80.0, max_dd_pct="", p_dd=-0.15, trades=12,
                           win_rate_pct=40.0, profit_factor=0.9, sharpe_w=-0.1, pos_quarters_pct=40.0,
                           worst_quarter_usd=-30.0, wiped=0, dd_marks="M1", score_final10="", source_file="fake")])
    days = pd.date_range("2021-11-12", "2026-11-12", freq="D")
    eq = 2000.0 + 600.0 * np.linspace(0, 1, len(days)) + 80 * np.sin(np.arange(len(days)) / 40.0)
    eq[0], eq[-1] = 2000.0, 2600.0
    keep = (days.dayofweek != 5) | (np.arange(len(days)) == 0)
    cv = pd.DataFrame({"series_id": "tradeiq_2027:XAUUSDm|1H|RIBBON|A", "date": days[keep].strftime("%Y-%m-%d"),
                       "equity_usd": eq[keep]})
    if v1:
        folder.mkdir(parents=True, exist_ok=True)
        s.to_csv(folder / "tradeiq_2027__series.csv", index=False)
        m.to_csv(folder / "tradeiq_2027__metrics.csv", index=False)
        cv.to_csv(C.curve_file("tradeiq_2027", "5y", folder), index=False, compression="gzip")
    else:
        C.write_source("tradeiq_2027", s, m, {"5y": cv}, data=folder, replace=True)


@need_data
def test_the_builder_with_some_sources_and_with_a_fake_study_2(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for p in DATA.iterdir():
        if p.name.startswith(("final10__", "benchmarks__", "balke__", "ladder__")):
            shutil.copy(p, data / p.name)
    out = tmp_path / "index.html"
    rep = C.build(data, out, log=lambda *a: None)
    text = out.read_text(encoding="utf-8")
    blob = _blob(text)
    assert rep["mb"] < 12.0
    pend = {(p["src"], p["w"]) for p in blob["pending"]}
    assert ("tradeiq_2027", "") in pend and ("bot_filters", "") in pend
    assert ("benchmarks", "8y") in pend and ("benchmarks", "new") in pend
    assert not any(x.startswith("tradeiq_rsi:") for x in blob["S"]["id"])
    # no request leaves the page
    assert not re.search(r"<script[^>]+src=", text) and not re.search(r"<link[^>]+href=", text)
    assert "@import" not in text.split('<script type="application/json"')[0]
    # the default selection exists: the bots' designs are marked, the finalists flagged
    S = blob["S"]
    assert sum(1 for r in S["role"] if r == "design") == 5 and sum(S["fin"]) >= 18
    # a small fake study 2 arrives (v1 columns): it is picked up, coloured as study 2, its blanks filled from its
    # curve and listed as computed here; it takes the slot after study 1's place (here: after FINAL10)
    _fake_study2(data, v1=True)
    assert C.validate(data)["errors"] == []
    logs = []
    C.build(data, out, log=logs.append)
    assert any("tradeiq_2027 on XAUUSDm: no account rows on 8y, new, 1y" in x for x in logs)
    blob = _blob(out.read_text(encoding="utf-8"))
    S, M = blob["S"], blob["M"]
    slots = {g["key"]: g["slot"] for g in blob["groups"]}
    assert slots["tradeiq_2027"] == 2 and slots["balke"] == 3
    i = S["id"].index("tradeiq_2027:XAUUSDm|1H|RIBBON|A")
    assert S["grp"][i] == "tradeiq_2027" and S["fin"][i] == 1 and S["feat"][i] == 1
    assert not any(p["src"] == "tradeiq_2027" for p in blob["pending"])
    j = [k for k in range(len(M["s"])) if M["s"][k] == i][0]
    assert set(M["der"][j].split(",")) >= {"cagr_pct", "sharpe_w", "pos_quarters_pct", "worst_quarter_usd"}
    assert M["ddu"][j] is None and M["dly"][j] > 0             # no $ drawdown next to an M1-mark %
    assert abs(M["rdd"][j] - M["cagr"][j] / 12.5) < 1e-6
    assert str(i) in blob["C"]["5y"]
    j2 = [k for k in range(len(M["s"])) if S["id"][M["s"][k]] == "tradeiq_2027:BTCUSDm|4H|ORB|B"][0]
    assert M["b"][j2] == 1 and blob["windows"][M["w"][j2]]["key"] == "holdout"


@need_data
def test_the_committed_page_parses_and_is_under_12_mb():
    assert PAGE.exists() and PAGE.stat().st_size < 12e6
    text = PAGE.read_text(encoding="utf-8")
    blob = _blob(text)
    assert blob["v"] == 2 and len(blob["S"]["id"]) >= 800
    assert [w["key"] for w in blob["windows"]][:4] == ["5y", "8y", "new", "1y"]
    assert "<title>Every backtest on the bot's $2,000 account" in text
    assert "59\nentry filters" in text or "59 entry filters" in text.replace("\n", " ")
    assert "can be a little smaller" not in text


def _browser_ok() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return CHROME.exists()


@need_data
@pytest.mark.skipif(not _browser_ok(), reason="needs playwright and Google Chrome")
def test_the_page_in_a_browser(tmp_path):
    """Review majors and minors on the rendered page: no two drawn lines of a study look alike; the Top 10 is the
    unit-rule accounts by growth / DD whatever the switches; the link is written back; blanks sort last both ways; a
    basis or cost without rows is disabled; the two sticky bars do not overlap; labels show as written."""
    from playwright.sync_api import sync_playwright
    _fake_study2(tmp_path / "data", v1=True)
    for p in DATA.iterdir():
        if p.name.startswith(("final10__", "benchmarks__")):
            shutil.copy(p, tmp_path / "data" / p.name)
    C.build(tmp_path / "data", tmp_path / "index.html", log=lambda *a: None)
    blob = _blob(PAGE.read_text(encoding="utf-8"))
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=str(CHROME), headless=True, args=["--disable-gpu"])
        page = b.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(PAGE.as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('#tbl tbody tr').length > 0", timeout=60000)

        def drawn():
            return page.evaluate("() => (document.getElementById('chart').data || []).filter(t => t.yaxis === 'y')"
                                 ".map(t => [t.name, t.line.color, t.line.dash, (t.marker || {}).symbol || ''])")
        d = drawn()
        assert 6 <= len(d) <= 12
        assert len({tuple(x[1:]) for x in d}) == len(d)            # colour, dash and marker never repeat
        assert page.evaluate("location.hash") == "#sym=gold&w=5y"
        page.click("#q-fin")
        page.locator("#symseg button", has_text="BTC").click()
        page.locator("#winseg button", has_text="8y").click()
        page.click("#q-fin")
        d = drawn()
        assert len(d) >= 8 and len({tuple(x[1:]) for x in d}) == len(d)
        assert page.evaluate("location.hash") == "#sym=BTC&w=8y"
        # the Top 10: the unit-rule accounts with a curve, ranked by growth / DD (CAGR % / max DD %)
        page.locator("#symseg button", has_text="Gold").click()
        page.locator("#winseg button", has_text="5y").click()
        page.locator("#basisseg button", has_text="Per 0.01 lot").click()
        page.click("#q-top")
        names = {x[0] for x in drawn()}
        S, M = blob["S"], blob["M"]
        w5 = [w["key"] for w in blob["windows"]].index("5y")
        cand = [j for j in range(len(M["s"])) if M["w"][j] == w5 and M["b"][j] == 0 and M["c"][j] == 1
                and S["sym"][M["s"][j]] == "XAUUSDm" and S["role"][M["s"][j]] != "benchmark"
                and S["siz"][M["s"][j]] == "unit rule" and M["rdd"][j] is not None
                and str(M["s"][j]) in blob["C"]["5y"]]
        cand.sort(key=lambda j: -M["rdd"][j])
        want = {S["label"][M["s"][j]][:50] if len(S["label"][M["s"][j]]) <= 50 else S["label"][M["s"][j]][:49] + "…"
                for j in cand[:10]}
        assert want <= names and not any("1% risk" in n or "vol-targeted" in n for n in names)
        # per 0.01 lot: the CAGR switch is disabled, and x1.5 has no rows on 5y
        dis = page.evaluate("() => Array.from(document.querySelectorAll('.seg button:disabled')).map(b => b.textContent)")
        assert "CAGR %" in dis and "x1.5" in dis
        page.locator("#basisseg button", has_text="Account").click()
        # the exam column: blanks last in both directions; the header is a keyboard-reachable button
        for _ in range(2):
            page.locator("#tbl thead .thb", has_text="Exam").click()
            ex = page.evaluate("() => Array.from(document.querySelectorAll('#tbl tbody tr')).map(r => r.cells[4].innerText)")
            first_blank = ex.index("") if "" in ex else len(ex)
            assert all(x == "" for x in ex[first_blank:]) and first_blank > 0
        assert page.evaluate("() => Array.from(document.querySelectorAll('#tbl thead .thb')).every(b => b.tabIndex === 0)")
        # the caveats are on the row, not only in a hover title: badges and a Notes disclosure
        page.fill("#q", "london breakout")
        page.wait_for_timeout(400)
        badges = page.evaluate("""() => { const r = Array.from(document.querySelectorAll('#tbl tbody tr')).find(
            r => r.querySelector('.nm') && r.querySelector('.nm').textContent === 'London breakout, 1% risk');
            return [Array.from(r.querySelectorAll('.badge')).map(b => b.textContent), !!r.querySelector('details.nt')]; }""")
        assert "risk-sized" in badges[0] and badges[1]
        page.fill("#q", "")
        page.wait_for_timeout(400)
        # wiped accounts are counted in their panel's heading (they stack at 100%)
        heads = page.evaluate("() => Array.from(document.querySelectorAll('#panels .panel h3')).map(h => h.textContent)")
        assert any("wiped" in h for h in heads)
        # the drawdown panel has its own tooltip
        page.evaluate("() => window.scrollTo(0, document.getElementById('chart').getBoundingClientRect().top + window.scrollY - 30)")
        page.wait_for_timeout(200)
        bb = page.locator("#chart .nsewdrag[data-subplot='xy2']").bounding_box()
        page.mouse.move(bb["x"] + bb["width"] * 0.6, bb["y"] + bb["height"] * 0.5)
        page.wait_for_timeout(400)
        tips = page.evaluate("() => Array.from(document.querySelectorAll('#chart .hoverlayer text')).map(e => e.textContent)")
        assert any("below the peak" in t for t in tips)
        # nothing selected: one sentence, one full stop
        page.click("#q-clear")
        assert page.evaluate("document.getElementById('selnote').textContent").endswith("click a point.")
        page.click("#q-bots")
        # FINAL10's V3-lite 5y row: its computed Sharpe is dotted, its Max DD $ empty
        page.fill("#q", "v3-lite")
        page.wait_for_timeout(400)
        row = page.evaluate("""() => { const r = Array.from(document.querySelectorAll('#tbl tbody tr')).find(
            r => r.querySelector('.nm') && r.querySelector('.nm').textContent === 'V3-lite');
            return [r.querySelectorAll('.der').length, Array.from(r.cells).map(c => c.innerText)]; }""")
        assert row[0] >= 5
        # the sticky bars: the filter bar sits under the main bar
        page.evaluate("() => document.getElementById('tbl').scrollIntoView()")
        page.wait_for_timeout(200)
        top = page.evaluate("() => [document.getElementById('mainbar').getBoundingClientRect().bottom,"
                            " document.getElementById('filters').getBoundingClientRect().top]")
        assert top[1] >= top[0] - 1
        # a label with HTML and a template shows as written (legend, tooltip, table)
        page.goto((tmp_path / "index.html").as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('#tbl tbody tr').length > 0", timeout=60000)
        legend = page.evaluate("() => Array.from(document.querySelectorAll('#chart .legend .legendtext')).map(e => e.textContent)")
        assert "1H ribbon A <b>x</b> & %{y}" in legend
        # at 1024 px the legend goes under the plot instead of taking a third of its width
        narrow = b.new_page(viewport={"width": 1024, "height": 900})
        narrow.goto(PAGE.as_uri(), wait_until="load")
        narrow.wait_for_function("document.querySelectorAll('#tbl tbody tr').length > 0", timeout=60000)
        pos = narrow.evaluate("""() => { const c = document.getElementById('chart').getBoundingClientRect(),
            l = document.querySelector('#chart .legend').getBoundingClientRect(),
            p = document.querySelector('#chart .nsewdrag[data-subplot="xy2"]').getBoundingClientRect();
            return [l.top - p.bottom, c.width - (p.right - c.left)]; }""")
        assert pos[0] > 0 and pos[1] < 60
        assert errors == []
        b.close()


def test_accessibility_markup():
    """Review minor: click-only headers, an empty header, a theme button whose aria-label hid its text, role=img over a
    clickable legend, unnamed scatter panels, a fail colour under 4.5:1."""
    assert 'id="themebtn" type="button" aria-label' not in C.PAGE_HTML
    assert 'id="chart" role="group"' in C.PAGE_HTML and 'role="img"' not in C.PAGE_HTML
    assert "Series (tick to draw)" in C.PAGE_JS and 'class: "thb"' in C.PAGE_JS
    assert '"aria-label": "Risk and return: "' in C.PAGE_JS
    css = C.PAGE_CSS
    bad_light = re.search(r"--bad: (#[0-9a-f]{6})", css).group(1)

    def lum(h):
        return 0.2126 * _lin(h)[0] + 0.7152 * _lin(h)[1] + 0.0722 * _lin(h)[2]
    assert (lum("#ffffff") + 0.05) / (lum(bad_light) + 0.05) >= 4.5


# ───────────────────────────── study 1 on 5y, recomputed ─────────────────────────────

def _store_ok() -> bool:
    try:
        from backtesting.data import store
        return store.data_span("XAUUSDm") is not None and store.data_span("BTCUSDm") is not None
    except Exception:
        return False


@need_data
@pytest.mark.skipif(not _store_ok(), reason="needs the tick store (data/store)")
@pytest.mark.parametrize("vid", ["XAUUSDm|1H|QQE|R2|F2-4H|S0", "BTCUSDm|1D|VWRSI-RV|R3|F0|S1"])
def test_a_5y_study1_account_recomputed_equals_the_exported_curve(vid):
    from backtesting.research import tradeiq as T
    from backtesting.research import tradeiq_market as TM
    v = T.Variant.of(vid)
    mk = C.market_from(v.symbol)
    assert TM.utc(mk.t[0]) >= pd.Timestamp("2019-01-01", tz="UTC")      # nothing before 2019 is loaded
    st = T.Study(mk)
    a, z = C.COMMON["5y"]
    r = TM.run(mk, st.bars[v.tf], st.state(v), a, z, stop=st.stops[v.tf] if v.stop == "S1" else None, cost=1.0)
    curve, cs, res = T.account_of(r)
    ts = (curve.time.astype("int64") // 10**9).to_numpy(np.int64)
    mine = C.eod_from_midnights(ts, curve.equity.to_numpy(np.float64),
                                C._days_with_bars(mk)[np.maximum((ts - 1) // C.DAY_S, 0)])
    sid = f"tradeiq_rsi:{vid}"
    parts = []
    for chunk in pd.read_csv(C.curve_file("tradeiq_rsi", "5y", DATA), chunksize=400_000):
        parts.append(chunk[chunk.series_id == sid])
    got = pd.concat(parts)
    assert got.date.tolist() == mine.date.tolist()
    assert np.max(np.abs(got.equity_usd.to_numpy() - mine.equity_usd.round(2).to_numpy())) < 0.006
    m = pd.read_csv(DATA / "tradeiq_rsi__metrics.csv", keep_default_na=False)
    row = _row(m, sid, "5y")
    # the contract keeps 4 decimals of these
    assert abs(float(row.final_usd) - cs["final"]) < 6e-5 and abs(float(row.max_dd_pct) - cs["max_dd_pct"]) < 6e-5
    assert int(row.trades) == len(res.trades_pnl) and int(row.wiped) == int(cs["wiped"])
    # the $ drawdown on the account's own M1 marks: the kernel gives account_of's % and final, and its $ figure
    f_dd, dd_usd, bal = C.account_dd_usd(r)
    assert abs(f_dd * 100.0 - cs["max_dd_pct"]) < 1e-12 and abs(bal - cs["final"]) < 1e-9
    assert abs(float(row.max_dd_usd) - dd_usd) < 6e-5 and dd_usd >= f_dd * 2000.0
    unit = _row(m, sid, "5y", "unit")
    assert abs(float(unit.net_usd) - r.net) < 6e-5 and abs(float(unit.max_dd_usd) - r.max_dd) < 6e-5
    assert int(unit.trades) == len(r.trades)


# ───────────────────────────── the hard rules ─────────────────────────────

def test_nothing_before_2019_without_the_flag_and_study_2s_exam():
    with pytest.raises(PermissionError):
        C.market_from("XAUUSDm", "2018-12-31")
    with pytest.raises(PermissionError):
        C.compute(["XAUUSDm"], ["8y"], data=Path("/nonexistent"))
    with pytest.raises(PermissionError):
        C.compute(["BTCUSDm"], ["new"], data=Path("/nonexistent"))
    if not C.STUDY2_EXAM.exists():
        # the flag alone is not enough while study 2's exam is unwritten (review: the switch was bare)
        with pytest.raises(PermissionError, match="exam"):
            C.compute(["XAUUSDm"], ["8y"], allow_pre_2019=True, data=Path("/nonexistent"))


def test_no_study_2_module_is_imported():
    import subprocess
    src = (REPO / "backtesting" / "research" / "compare_page.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+\S*tradeiq2", src, re.M)
    assert not re.search(r"import_module|__import__", src)
    out = subprocess.run([sys.executable, "-B", "-c",
                          "import sys, backtesting.research.compare_page as C\n"
                          "C.final10_series_and_metrics(); C.balke_source(); C.ladder_source()\n"
                          "print(sorted(k for k in sys.modules if 'tradeiq2' in k))"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    assert out == "[]"
