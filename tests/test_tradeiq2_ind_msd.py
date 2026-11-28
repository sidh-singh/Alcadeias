"""
The Market Structure Dashboard (Flux Charts) of study 2: the reconciliation of its two independent ports
(``backtest_results/tradeiq_2027/PREREG.md`` sections 5 and 6.2; the porting note is
``backtest_results/tradeiq_2027/porting/msd.md``).

* Port A, ``backtesting/research/tradeiq2_ind_msd.py``: the production port (a numba row kernel); the study runs it.
* Port B, ``tests/tradeiq2_oracle_msd.py``: the oracle (plain Python, one object per Pine call site, bar by bar).

PREREG 5: before any rule runs, the two ports must agree bit for bit on the real bars of both symbols, on every series
a rule reads. The rules read the bias label (MSD-A1..A3, the FS filter of MSD-F4, STK-RM; study 3's MSD filter), the
row scores ``s_4H``, ``s_1D``, ``s_1W`` (MSD-F6) and ``bos_trend`` (BOS-trend), on the 1H, 4H and 1D charts, with
model A: each higher row from its last CLOSED bar (PREREG 5 and 6.2). Claim 14 reads model B (the forming higher bar),
which only port A has; it is checked here against an independent construction on port B's engine.

1. The real bars of both symbols from the study's data start to 2024-06-30, as study 2's harness serves them
   (``tradeiq2_market.load``: gold from 2016-01-03, the Early window's warm-up; BTC from 2018-01-01), with study 2's
   hold-out guard closed (FINALISTS.md absent: nothing at or after 2024-07-01 is loaded):
   a. every output of ``structure_dashboard`` on the 1H, 4H and 1D charts: the same keys, dtypes and values;
   b. every row (1H, 4H, 1D, 1W) on its own bars: the pivots and swing levels bit for bit (NaN in the same places),
      the structure, the nearest order-block and FVG sides, the types after the real-time override, the reclaim flags
      and the zone counts, and the event tables: pivots, breaks of structure, order blocks made (with their top and
      bottom) and rejected as overlapping, FVGs;
   c. the weekly row: both ports' ``weekly_bars`` and the harness's ``TMarket2.tbars('1W')``, bar for bar;
   d. model B: port A's forming-bar values at every chart bar against port B's row stepped tentatively on the forming
      bar and rolled back afterwards, as Pine rolls back ``var`` state before every realtime tick;
   e. gold from study 1's data start too (2017-01-03, the span of both port authors and of the map's probes): the
      ports agree there, they reproduce the probes' counts (a third implementation, with its own bars: the third
      opinion), and every output from 2018-05-19 on equals the 2016-start run;
   f. counts and values recorded when the ports were reconciled (a guard against both ports changing together).
2. Synthetic markets for what the real bars do not reach: prices on a coarse grid (ties everywhere), a climb past
   the 100000.0 sentinel of ``findNearestZone``, outside bars that are both pivots, gold's calendar (the Sunday stub,
   the daily break, a short holiday Friday, a hole) and BTC's, and data that end inside a week (forming last bars),
   all built by the study's own harness from synthetic M1 bars; models A and B.

Floats are compared bit for bit (their 64-bit patterns), so no tolerance appears anywhere: both ports evaluate the one
float expression of the bias, ``(close - swingL) / swingRange * 100`` (line 707), in Pine's order, and every other
float is a copied price. No profit or loss is computed.
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_market as T2
from backtesting.research import tradeiq2_ind_msd as A

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_msd as B  # noqa: E402

SYMS = ("XAUUSDm", "BTCUSDm")
H = 3600
DAY = 86400
DEV = (TM.s_of("2019-01-01"), TM.s_of("2023-01-01"))       # Development: bars closing in (2019-01-01, 2023-01-01]
FIELDS = ("t", "tc", "o", "h", "l", "c")
# port A's ``row_values`` key -> port B's ``calc_all`` key: the same quantity of ``calcAll`` per row bar
ROW_KEYS = {"pivot_high": "pivot_high", "pivot_low": "pivot_low", "swing_h": "swing_h", "swing_l": "swing_l",
            "struct": "struct", "ob": "ob_dir", "fvg": "fvg_dir", "high_type": "high_type", "low_type": "low_type",
            "fvg_new": "new_fvg", "reclaim_low": "reclaim_low", "reclaim_high": "reclaim_high", "n_ob": "n_ob",
            "n_fvg": "n_fvg"}


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' hold-out guards see an empty folder (no FINALISTS.md): nothing at or after 2024-07-01."""
    d = tmp_path / "closed_study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.setattr(T2, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


# ───────────────────────────── comparisons ─────────────────────────────

def assert_same(a, b, what):
    """Equal shapes; floats bit for bit (the 64-bit patterns: NaN in the same places, the sign of zero included);
    integers and booleans equal as numbers (the dtypes of the dashboard keys are compared separately)."""
    a, b = np.asarray(a), np.asarray(b)
    assert a.shape == b.shape, (what, a.shape, b.shape)
    if a.dtype.kind == "f" or b.dtype.kind == "f":
        assert a.dtype.kind == b.dtype.kind == "f", (what, a.dtype, b.dtype)
        bad = np.flatnonzero(np.ascontiguousarray(a, np.float64).view(np.uint64)
                             != np.ascontiguousarray(b, np.float64).view(np.uint64))
    else:
        bad = np.flatnonzero(a.astype(np.int64) != b.astype(np.int64))
    assert len(bad) == 0, f"{what}: {len(bad)} values differ, first at {bad[:5].tolist()}: {a[bad[:5]]} / {b[bad[:5]]}"


def assert_dashboards_equal(oa, ob, what):
    assert set(oa) == set(ob), (what, sorted(set(oa) ^ set(ob)))
    for k in sorted(oa):
        assert oa[k].dtype == ob[k].dtype, (what, k, oa[k].dtype, ob[k].dtype)
        assert_same(oa[k], ob[k], f"{what} {k}")


def light(b, symbol=None):
    """A plain copy (symbol, t, tc, o, h, l, c) of a bar object, so that no M1 array stays referenced."""
    return NS(symbol=getattr(b, "symbol", symbol) or symbol, **{f: np.array(getattr(b, f)) for f in FIELDS})


def events_a(bars):
    """Port A's event table of one row (``row_values``): pivots (bar, +1 high / -1 low, price), breaks of structure
    (bar, side), order blocks made (bar, side, top, bottom) and rejected as overlapping (bar, side), FVGs (bar,
    side)."""
    r = A.row_values(bars)
    piv = sorted([(int(k), 1, float(r["pivot_high"][k])) for k in np.flatnonzero(~np.isnan(r["pivot_high"]))]
                 + [(int(k), -1, float(r["pivot_low"][k])) for k in np.flatnonzero(~np.isnan(r["pivot_low"]))])
    bos = [(int(k), int(r["bos"][k])) for k in np.flatnonzero(r["bos"])]
    made = [(k, s, float(r["ob_top"][k]), float(r["ob_bottom"][k])) for k, s in bos if not np.isnan(r["ob_top"][k])]
    rejected = [(k, s) for k, s in bos if np.isnan(r["ob_top"][k])]
    fvg = [(int(k), int(r["fvg_new"][k])) for k in np.flatnonzero(r["fvg_new"])]
    return {"pivots": piv, "bos": bos, "ob_made": made, "ob_rejected": rejected, "fvg": fvg}


def events_b(bars):
    """The same table from port B, its ``Row`` driven bar by bar. The order block made on a bar is the newest zone of
    its array (``unshift``, line 523); it cannot be mitigated on its own bar, because its candle range holds the break
    bar's low (bull) or high (bear) and so its close."""
    row = B.Row()
    piv, bos, made, rejected, fvg = [], [], [], [], []
    for k in range(len(bars.c)):
        out = row.step(float(bars.o[k]), float(bars.h[k]), float(bars.l[k]), float(bars.c[k]))
        if not B.na(out["pivot_high"]):
            piv.append((k, 1, out["pivot_high"]))
        if not B.na(out["pivot_low"]):
            piv.append((k, -1, out["pivot_low"]))
        side = 1 if out["bull_break"] else (-1 if out["bear_break"] else 0)
        assert not (out["bull_break"] and out["bear_break"])
        if side:
            bos.append((k, side))
        if out["new_ob"]:
            z = row.calcOrderBlock.obs[0]
            assert z.dir == out["new_ob"] == side
            made.append((k, side, float(z.top), float(z.bottom)))
        if out["ob_rejected"]:
            assert out["ob_rejected"] == side and not out["new_ob"]
            rejected.append((k, side))
        if out["new_fvg"]:
            fvg.append((k, int(out["new_fvg"])))
    return {"pivots": sorted(piv), "bos": bos, "ob_made": made, "ob_rejected": rejected, "fvg": fvg}


def assert_rows_equal(bars, what):
    """One row on its own bars: every common per-bar output of the two ports, and their event tables."""
    ra, rb = A.row_values(bars), B.calc_all(bars)
    for ka, kb in ROW_KEYS.items():
        assert_same(ra[ka], rb[kb], f"{what} {ka}")
    assert_same(ra["bos"], rb["bull_break"].astype(np.int8) - rb["bear_break"].astype(np.int8), f"{what} bos")
    ea, eb = events_a(bars), events_b(bars)
    for k in ea:
        assert ea[k] == eb[k], (what, k, len(ea[k]), len(eb[k]))
    return ea


def assert_weekly_equal(day_bars, end_s, harness, what):
    """Both ports' weekly bars of the same day bars and data end, and the harness's 1W bars (if given)."""
    wa, wb = A.weekly_bars(day_bars, end_s=end_s), B.weekly_bars(day_bars, end_s=end_s)
    for f in FIELDS + ("d0", "d1", "complete"):
        assert_same(getattr(wa, f), getattr(wb, f), f"{what} weekly {f}")
    if harness is not None:
        for f in FIELDS + ("complete",):
            assert_same(getattr(wa, f), getattr(harness, f), f"{what} weekly vs harness {f}")
    return wa


# ───────────────────────────── model B on port B's engine ─────────────────────────────

class PeekRow:
    """
    Port B's ``Row`` with Pine's realtime rollback. ``commit`` runs a closed bar. ``peek`` runs one tentative step on
    a forming bar and then restores the row: every series gets its last value removed and every call site's ``var``
    state (``CalcSwingHL``, ``CalcStructure``, ``CalcOrderBlock``, ``CalcFVG``) is put back as it was, which is what
    Pine does before each realtime tick of a ``request.security`` context (the map's model B, section 2.3).
    """

    SITES = (B.CalcSwingHL, B.CalcStructure, B.CalcOrderBlock, B.CalcFVG)

    def __init__(self):
        self.row = B.Row()
        self.series = [v for v in vars(self.row).values() if isinstance(v, B.Series)]
        self.sites = [v for v in vars(self.row).values() if isinstance(v, self.SITES)]
        assert len(self.series) == 10 and len(self.sites) == 4

    @staticmethod
    def _copy(v):
        if isinstance(v, list):
            return list(v)                     # zone arrays: zones are added and removed, never changed
        if hasattr(v, "__slots__"):            # SwingData, PivotData: changed field by field
            c = object.__new__(type(v))
            for s in v.__slots__:
                setattr(c, s, getattr(v, s))
            return c
        return v                               # numbers, booleans, None

    def commit(self, o, h, l, c):
        return self.row.step(o, h, l, c)

    def peek(self, o, h, l, c):
        saved = [{k: self._copy(v) for k, v in vars(s).items()} for s in self.sites]
        bar_index = self.row.bar_index
        out = self.row.step(o, h, l, c)
        for s in self.series:
            s._v.pop()
        self.row.bar_index = bar_index
        for s, d in zip(self.sites, saved):
            for k, v in d.items():
                setattr(s, k, v)
        return out


def model_b_row_by_port_b(chart, row):
    """
    At every chart bar j, the values of a higher row that the live dashboard shows at the chart close (model B), on
    port B's engine: when j lies inside row bar k (``t_row[k] <= t_chart[j]`` and ``tc_chart[j] <= tc_row[k]``), the
    row's state after bar k - 1 stepped tentatively on the forming bar k (the open of the first chart bar inside k, the
    high and the low of the chart bars inside k up to j, the close of j); otherwise (only where no row bar holds the
    chart bar) the row's last bar closed by the chart close. Returns struct, ob, fvg (int8; 0 while na) and swing_h,
    swing_l (NaN while na), and checks on the way that the forming bar ends as the closed bar (the rows nest) and that
    the rollbacks left the committed path equal to ``calc_all``.
    """
    n, nr = len(chart.t), len(row.t)
    k_of = np.searchsorted(row.t, chart.t, side="right") - 1
    out = {f: np.zeros(n, np.int8) for f in ("struct", "ob", "fvg")}
    out.update({f: np.full(n, np.nan) for f in ("swing_h", "swing_l")})
    pr = PeekRow()
    committed = []

    def commit_to(k):                                   # commit row bars 0 .. k - 1
        while len(committed) < k:
            i = len(committed)
            committed.append(pr.commit(float(row.o[i]), float(row.h[i]), float(row.l[i]), float(row.c[i])))

    def put(j, v):
        out["struct"][j], out["ob"][j], out["fvg"][j] = v["struct"], v["ob_dir"], v["fvg_dir"]
        out["swing_h"][j], out["swing_l"][j] = v["swing_h"], v["swing_l"]

    cur, fo, fh, fl = -1, np.nan, np.nan, np.nan
    for j in range(n):
        k = int(k_of[j])
        if k >= 0 and chart.tc[j] <= row.tc[k]:
            commit_to(k)
            if k != cur:
                cur, fo, fh, fl = k, float(chart.o[j]), float(chart.h[j]), float(chart.l[j])
            else:
                fh, fl = max(fh, float(chart.h[j])), min(fl, float(chart.l[j]))
            put(j, pr.peek(fo, fh, fl, float(chart.c[j])))
            last_inside = j + 1 == n or k_of[j + 1] != k or chart.tc[j + 1] > row.tc[k]
            if last_inside:
                assert (fo, fh, fl, float(chart.c[j])) == (row.o[k], row.h[k], row.l[k], row.c[k]), (j, k)
        else:
            kk = int(np.searchsorted(row.tc, chart.tc[j], side="right")) - 1
            if kk >= 0:
                commit_to(kk + 1)
                put(j, committed[kk])
    commit_to(nr)
    ref = B.calc_all(row)
    for f in ("struct", "ob_dir", "fvg_dir", "swing_h", "swing_l", "n_ob", "n_fvg"):
        assert_same(np.asarray([v[f] for v in committed]), ref[f], f"committed path after the rollbacks, {f}")
    return out


def model_b_dashboard_by_port_b(rows, chart_tf, tick):
    """Model B's dashboard from ``model_b_row_by_port_b`` (the higher rows) and port B's model-A chart row, scored as
    port B scores model A (``dir_score``, ``swing_bias_dir`` with the chart close, weights, ``label_of``)."""
    chart = rows[chart_tf]
    base = B.structure_dashboard(rows, chart_tf, mintick=tick)
    out = {"max_score": base["max_score"], "bos": base["bos"], "bos_trend": base["bos_trend"]}
    points = np.zeros(len(chart.t), np.int64)
    for r in B.active_rows(chart_tf):
        if r == chart_tf:
            for f in ("s", "struct", "ob", "fvg", "swing"):
                out[f"{f}_{r}"] = base[f"{f}_{r}"]
        else:
            v = model_b_row_by_port_b(chart, rows[r])
            out[f"struct_{r}"], out[f"ob_{r}"], out[f"fvg_{r}"] = v["struct"], v["ob"], v["fvg"]
            out[f"swing_{r}"] = np.asarray([B.swing_bias_dir(a, b, c, tick) for a, b, c in
                                            zip(v["swing_h"], v["swing_l"], chart.c)], np.int8)
            out[f"s_{r}"] = sum(out[f"{f}_{r}"].astype(np.int64) for f in ("struct", "ob", "fvg", "swing"))
        points += B.WEIGHT[r] * out[f"s_{r}"]
    out["score"] = points
    out["label"] = np.asarray([B.label_of(p, B.max_score_of(chart_tf)) for p in points], np.int8)
    return out


# ───────────────────────────── 1. the real bars ─────────────────────────────

class Real:
    """The real bars of one symbol and span, and the two ports' outputs on them (computed once)."""

    def __init__(self, symbol, rows, end_s, harness_1w, span):
        self.symbol, self.rows, self.end_s, self.harness_1w, self.span = symbol, rows, end_s, harness_1w, span
        self.tick = A.MINTICK[symbol]
        self._dash = {}

    def dash(self, port, tf, model="A"):
        key = (port, tf, model)
        if key not in self._dash:
            if port == "A":
                self._dash[key] = A.structure_dashboard(self.rows, tf, model)
            elif model == "A":
                self._dash[key] = B.structure_dashboard(self.rows, tf)
            else:
                self._dash[key] = model_b_dashboard_by_port_b(self.rows, tf, self.tick)
        return self._dash[key]


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """``get(symbol, span)``: span "study2" = study 2's harness (``tradeiq2_market.load``; gold from 2016-01-03),
    "study1" = study 1's (``tradeiq_market.load``; gold from 2017-01-03), both to 2024-07-01 00:00 UTC (exclusive)
    with both guards pointed at an empty folder. One M1 store is in memory at a time; it is dropped as soon as its
    bars are built (the bars themselves are a few MB)."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol, span="study2"):
        key = (symbol, span)
        if key not in cache:
            months = set(store.available_months(symbol))
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.setattr(T2, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                harness = None
                if span == "study2":
                    mk = T2.load(symbol, end=T2.HOLDOUT_START)
                    rows = {tf: light(mk.tbars(tf)) for tf in ("1H", "4H", "1D", "1W")}
                    hw = mk.tbars("1W")
                    harness = NS(complete=np.array(hw.complete), **{f: np.array(getattr(hw, f)) for f in FIELDS})
                    del hw
                else:
                    mk = TM.load(symbol, end=TM.HOLDOUT_START)
                    rows = {tf: light(mk.tbars(tf)) for tf in ("1H", "4H", "1D")}
                    rows["1W"] = light(A.weekly_bars(rows["1D"], end_s=mk.end_s), symbol)
                end_s = int(mk.end_s)
                del mk
            gc.collect()
            for b in rows.values():
                assert int(b.tc[-1]) <= TM.CUT_S                               # nothing from the hold-out
            cache[key] = Real(symbol, rows, end_s, harness, span)
        return cache[key]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_dashboards_agree_bit_for_bit(symbol, real):
    x = real(symbol)
    assert x.end_s == TM.CUT_S
    for tf in A.CHART_TFS:
        oa, ob = x.dash("A", tf), x.dash("B", tf)
        assert_dashboards_equal(oa, ob, f"{symbol} {tf}")
        assert len(oa["label"]) == len(x.rows[tf].t) and set(np.unique(oa["label"])) == {-2, -1, 0, 1, 2}


@pytest.mark.parametrize("symbol", SYMS)
def test_real_rows_and_event_tables_agree(symbol, real):
    x = real(symbol)
    for r in A.ROWS:
        ev = assert_rows_equal(x.rows[r], f"{symbol} {r}")
        assert len(ev["pivots"]) > 30 and len(ev["bos"]) > 10 and len(ev["ob_made"]) > 5 and len(ev["fvg"]) > 30, r


@pytest.mark.parametrize("symbol", SYMS)
def test_real_weekly_rows_agree_with_the_harness(symbol, real):
    x = real(symbol)
    w = assert_weekly_equal(x.rows["1D"], x.end_s, x.harness_1w, symbol)
    assert w.complete.all()                                    # the bars end on Monday 2024-07-01 00:00 UTC
    for f in FIELDS:
        assert_same(getattr(w, f), getattr(x.rows["1W"], f), f"{symbol} weekly row {f}")
    # the same day bars cut on a Wednesday: both ports' weekly bars treat the last week as forming (the harness's own
    # weekly bars at a data end inside a week are compared in test_synthetic_markets_agree)
    d = x.rows["1D"]
    cut = TM.s_of("2023-03-16")                                # a Thursday 00:00: day bars to Wednesday 15 March
    part = NS(symbol=symbol, **{f: getattr(d, f)[d.tc <= cut] for f in FIELDS})
    wp = assert_weekly_equal(part, cut, None, f"{symbol} cut")
    assert not wp.complete[-1] and wp.tc[-1] == TM.s_of("2023-03-20") and wp.complete[:-1].all()


@pytest.mark.parametrize("symbol", SYMS)
def test_real_model_b_equals_port_b_rolled_back_on_the_forming_bar(symbol, real):
    x = real(symbol)
    for tf in A.CHART_TFS:
        oa, ob = x.dash("A", tf, "B"), x.dash("B", tf, "B")
        assert_dashboards_equal(oa, ob, f"{symbol} {tf} model B")
        assert (oa["label"] != x.dash("A", tf)["label"]).mean() > 0.05            # model B is not model A


def test_real_gold_from_study1_start(real):
    gold = real("XAUUSDm", "study1")
    full = real("XAUUSDm", "study2")
    assert int(gold.rows["1H"].t[0]) == TM.s_of("2017-01-03")
    if int(full.rows["1H"].t[0]) >= TM.s_of("2017-01-01"):
        pytest.skip("gold's 2016 months are not in the store: study 2's span is study 1's")
    for tf in A.CHART_TFS:
        oa = gold.dash("A", tf)
        assert_dashboards_equal(oa, gold.dash("B", tf), f"study-1 span {tf}")
        # from 2018-05-19 every output equals the run from 2016-01-03 (the W row agrees from the week closing then)
        off = int(np.searchsorted(full.rows[tf].t, gold.rows[tf].t[0]))
        assert np.array_equal(full.rows[tf].t[off:], gold.rows[tf].t)
        late = gold.rows[tf].tc >= TM.s_of("2018-05-19")
        for k, v in oa.items():
            assert np.array_equal(full.dash("A", tf)[k][off:][late], v[late]), (tf, k)
        assert (full.dash("A", tf)["label"][off:][~late] != oa["label"][~late]).any()      # and not before


# The map's probes (structure.md, section 6; scratch work/msd/probe_pivots.py and probe_warmup.py): a third
# implementation with its own bars, built from the store's M1 files, on study 1's span to 2024-06-30. Row -> bars,
# strict pivot highs, lows, bars that are both, inverted swing ranges (last pivot high < last pivot low) and bars with
# both swings, and the extra (highs, lows) when an equal value is allowed on the newer side, on the older side, on both.
PROBE_PIVOTS = {
    ("XAUUSDm", "1H"): (44190, 2699, 2764, 32, 269, 44174, (4, 1), (3, 2), (7, 3)),
    ("XAUUSDm", "4H"): (11955, 792, 816, 45, 120, 11928, (2, 0), (0, 0), (2, 0)),
    ("XAUUSDm", "1D"): (1932, 117, 108, 2, 10, 1909, (0, 0), (0, 0), (0, 0)),
    ("XAUUSDm", "1W"): (391, 23, 26, 0, 0, 368, (0, 0), (0, 0), (0, 0)),
    ("BTCUSDm", "1H"): (56840, 3775, 3793, 94, 119, 56821, (1, 0), (1, 0), (2, 0)),
    ("BTCUSDm", "4H"): (14225, 932, 933, 20, 53, 14200, (0, 0), (0, 0), (0, 0)),
    ("BTCUSDm", "1D"): (2372, 139, 158, 2, 23, 2351, (0, 0), (0, 0), (0, 0)),
    ("BTCUSDm", "1W"): (339, 17, 19, 0, 7, 317, (0, 0), (0, 0), (0, 0)),
}
# probe_warmup.py: the close of the bar where both sides have two pivots (structure ready) and the breaks of structure
# that close before 2019 (close dates, side), on the D and W rows
PROBE_WARMUP = {
    ("XAUUSDm", "1D"): ("2017-02-23", 27, [("2017-02-07", 1), ("2017-02-24", 1), ("2017-03-08", -1)]),
    ("XAUUSDm", "1W"): ("2017-08-19", 5, [("2017-07-08", -1), ("2017-09-02", 1), ("2017-12-09", -1),
                                          ("2018-05-19", -1), ("2018-12-08", 1)]),
    ("BTCUSDm", "1D"): ("2018-02-03", 14, [("2018-02-02", -1), ("2018-03-10", -1), ("2018-03-30", -1)]),
    ("BTCUSDm", "1W"): ("2018-09-03", 2, [("2018-06-25", -1), ("2018-11-19", -1)]),
}
PROBE_WEEK_OPENS = {"XAUUSDm": {0: 379, 1: 7, 2: 3, 5: 2}, "BTCUSDm": {1: 339}}   # weekday (0 Sunday) -> weeks


@pytest.mark.parametrize("symbol", SYMS)
def test_real_counts_equal_the_probes(symbol, real):
    x = real(symbol, "study1")
    for r in A.ROWS:
        b = x.rows[r]
        ra = A.row_values(b)
        ph, pl = ~np.isnan(ra["pivot_high"]), ~np.isnan(ra["pivot_low"])
        both = ~np.isnan(ra["swing_h"]) & ~np.isnan(ra["swing_l"])
        got = [len(b.t), int(ph.sum()), int(pl.sum()), int((ph & pl).sum()),
               int((both & (ra["swing_h"] < ra["swing_l"])).sum()), int(both.sum())]
        for ties in ("ties_right", "ties_left", "ties_both"):
            rb = B.calc_all(b, ties=ties)
            got.append((int((~np.isnan(rb["pivot_high"]) & ~ph).sum()), int((~np.isnan(rb["pivot_low"]) & ~pl).sum())))
        assert tuple(got) == PROBE_PIVOTS[(symbol, r)], (r, got)
        if r in ("1D", "1W"):
            ready, n_before, first = PROBE_WARMUP[(symbol, r)]
            k = int(np.flatnonzero((ra["high_type"] != 0) & (ra["low_type"] != 0))[0])
            assert str(TM.utc(b.tc[k]))[:10] == ready, r
            ev = [(str(TM.utc(b.tc[k]))[:10], int(ra["bos"][k])) for k in np.flatnonzero(ra["bos"])
                  if b.tc[k] < DEV[0]]
            assert len(ev) == n_before and ev[:len(first)] == first, (r, ev)
    wd = (x.rows["1W"].t // DAY + 4) % 7
    assert dict(zip(*[v.tolist() for v in np.unique(wd, return_counts=True)])) == PROBE_WEEK_OPENS[symbol]


# Recorded when the ports were reconciled (28 Nov 2026), on study 2's span: chart bars closing in Development
# (2019-01-01, 2023-01-01] -> bars, labels BULLISH / LEAN BULL / NEUTRAL / LEAN BEAR / BEARISH, label changes, BOS
# bull / bear, BOS-trend flips, bars where model B's label differs from model A's.
RECORDED_CHARTS = {
    ("XAUUSDm", "1H"): (23591, (3540, 6034, 9047, 4072, 898), 3137, (576, 506), 540, 4497),
    ("XAUUSDm", "4H"): (6386, (1327, 1294, 2314, 1028, 423), 984, (159, 146), 158, 1155),
    ("XAUUSDm", "1D"): (1032, (298, 151, 302, 177, 104), 241, (28, 17), 18, 141),
    ("BTCUSDm", "1H"): (35017, (4898, 10670, 13985, 4866, 598), 4391, (882, 770), 806, 6971),
    ("BTCUSDm", "4H"): (8757, (1542, 2644, 3177, 1180, 214), 1313, (222, 193), 210, 1753),
    ("BTCUSDm", "1D"): (1460, (345, 425, 408, 226, 56), 320, (36, 29), 30, 227),
}
# rows on their own bars, closing in Development -> pivot highs, lows, BOS bull, bear, order blocks made bull, bear,
# rejected, FVGs bull, bear
RECORDED_ROWS = {
    ("XAUUSDm", "1H"): (1445, 1508, 576, 506, 423, 388, 271, 2385, 2149),
    ("XAUUSDm", "4H"): (418, 443, 159, 146, 121, 119, 65, 698, 575),
    ("XAUUSDm", "1D"): (67, 63, 28, 17, 21, 14, 10, 123, 100),
    ("XAUUSDm", "1W"): (11, 15, 5, 5, 4, 3, 3, 30, 20),
    ("BTCUSDm", "1H"): (2309, 2338, 882, 770, 628, 561, 463, 2974, 2659),
    ("BTCUSDm", "4H"): (568, 579, 222, 193, 157, 154, 104, 800, 679),
    ("BTCUSDm", "1D"): (84, 99, 36, 29, 27, 24, 14, 178, 124),
    ("BTCUSDm", "1W"): (11, 9, 4, 4, 4, 4, 0, 30, 23),
}
# single chart bars (open time) -> label, score, the active rows' s_r (chart row first), bos_trend
RECORDED_BARS = {
    ("XAUUSDm", "1H", "2019-06-03 13:00"): (1, 12, (3, 1, 0, 1), 1),
    ("XAUUSDm", "4H", "2021-03-15 08:00"): (-2, -22, (0, -2, -4), 1),
    ("XAUUSDm", "1D", "2022-11-01 00:00"): (-2, -19, (-1, -4), -1),
    ("BTCUSDm", "1H", "2019-06-03 13:00"): (1, 18, (0, -1, 4, 2), -1),
    ("BTCUSDm", "4H", "2021-03-15 08:00"): (2, 30, (4, 2, 4), 1),
    ("BTCUSDm", "1D", "2022-11-01 00:00"): (0, -4, (0, -1), 1),
}


@pytest.mark.parametrize("symbol", SYMS)
def test_real_recorded_counts_and_values(symbol, real):
    x = real(symbol)
    for tf in A.CHART_TFS:
        a = x.dash("A", tf)
        b = x.dash("A", tf, "B")
        tc = x.rows[tf].tc
        sel = (tc > DEV[0]) & (tc <= DEV[1])
        lab = a["label"][sel]
        got = (int(sel.sum()), tuple(int((lab == v).sum()) for v in (2, 1, 0, -1, -2)),
               int((np.diff(a["label"])[sel[1:]] != 0).sum()),
               (int((a["bos"][sel] == 1).sum()), int((a["bos"][sel] == -1).sum())),
               int((np.diff(a["bos_trend"])[sel[1:]] != 0).sum()), int((b["label"][sel] != lab).sum()))
        assert got == RECORDED_CHARTS[(symbol, tf)], (tf, got)
    for r in A.ROWS:
        rv = A.row_values(x.rows[r])
        tc = x.rows[r].tc
        sel = (tc > DEV[0]) & (tc <= DEV[1])
        made = ~np.isnan(rv["ob_top"])
        got = (int((~np.isnan(rv["pivot_high"][sel])).sum()), int((~np.isnan(rv["pivot_low"][sel])).sum()),
               int((rv["bos"][sel] == 1).sum()), int((rv["bos"][sel] == -1).sum()),
               int((made & (rv["bos"] == 1))[sel].sum()), int((made & (rv["bos"] == -1))[sel].sum()),
               int((~made & (rv["bos"] != 0))[sel].sum()),
               int((rv["fvg_new"][sel] == 1).sum()), int((rv["fvg_new"][sel] == -1).sum()))
        assert got == RECORDED_ROWS[(symbol, r)], (r, got)
    for (sym, tf, when), want in RECORDED_BARS.items():
        if sym != symbol:
            continue
        a = x.dash("A", tf)
        i = int(np.searchsorted(x.rows[tf].t, TM.s_of(when)))
        assert int(x.rows[tf].t[i]) == TM.s_of(when)
        got = (int(a["label"][i]), int(a["score"][i]), tuple(int(a[f"s_{r}"][i]) for r in A.ACTIVE_ROWS[tf]),
               int(a["bos_trend"][i]))
        assert got == want, (tf, when, got)


# ───────────────────────────── 2. synthetic markets ─────────────────────────────

def synthetic_market(kind, seed, weeks=30):
    """
    Synthetic M1 bid bars (from Sunday 2019-03-03) and the study's own harness on them
    (``tradeiq2_market.TMarket2``): the 1H, 4H, 1D and 1W bars exactly as the study builds them.

    * "gold": gold's week (Sunday from 22:05 UTC, a daily break 20:57-22:02, Friday to 20:57), a holiday Friday open
      only to 03:00 (it merges into the next Monday's day bar and week), a two-day hole; prices on a 0.5 grid with
      small steps, so equal highs and lows (ties) are common on every row.
    * "btc": 24/7 with a nine-hour hole; prices climbing from about 2,000 to about 260,000 on a 1.0 grid, so that
      old zones end up more than 100,000 from the close (the sentinel of ``findNearestZone``, lines 427-449).
    * "flat": 24/7 on a 1.0 grid where most minutes do not move (many equal highs and lows), with a rare spike of
      +-25 in a minute's high and low (about one in 55 hours), which makes outside bars that are a pivot high and a
      pivot low at once.

    The data end on a Wednesday at 13:37, so the last 4H, day and week bars are still forming.
    """
    rng = np.random.default_rng(seed)
    t0 = TM.s_of("2019-03-03")
    t = t0 + 60 * np.arange(weeks * 7 * 1440, dtype=np.int64)
    minute = (t % DAY) // 60
    weekday = ((t // DAY) + 4) % 7                                    # 0 = Sunday
    keep = np.ones(len(t), bool)
    if kind == "gold":
        keep &= ~((minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)) & (weekday != 6)
        keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
        fri = t0 + (7 * 9 + 5) * DAY                                  # a Friday in week 10: open to 03:00 only
        keep &= ~((t >= fri + 3 * H) & (t < fri + DAY))
        hole = t0 + (7 * 17 + 2) * DAY                                # Tuesday-Wednesday of week 18
        keep &= ~((t >= hole) & (t < hole + 2 * DAY))
    else:
        hole = t0 + (7 * 13 + 4) * DAY + 5 * H                        # nine hours on a Thursday
        keep &= ~((t >= hole) & (t < hole + 9 * H))
    end = t0 + (7 * (weeks - 1) + 3) * DAY + 13 * H + 37 * 60         # Wednesday 13:37 of the last week
    keep &= t < end
    t = t[keep]
    n = len(t)
    if kind == "gold":
        grid = 0.5
        c = 1300.0 + np.cumsum(rng.choice([-1.0, 0.0, 0.0, 1.0], n)) * grid
    elif kind == "btc":
        grid = 1.0
        trend = np.exp(np.linspace(np.log(2000.0), np.log(260000.0), n))
        c = trend * np.exp(np.cumsum(rng.normal(0.0, 0.0012, n)))
    else:
        grid = 1.0
        c = 500.0 + np.cumsum(rng.choice([-1.0, 0.0, 0.0, 0.0, 0.0, 1.0], n))
    c = np.round(c / grid) * grid
    o = np.concatenate(([c[0]], c[:-1]))
    wig = np.abs(rng.normal(0.0, 1.0, (2, n))) * (0.004 * c if kind == "btc" else grid)
    h = np.maximum(o, c) + np.round(wig[0] / grid) * grid
    lo = np.minimum(o, c) - np.round(wig[1] / grid) * grid
    if kind == "flat":
        spike = rng.random(n) < 0.0003
        h[spike] += 25 * grid
        lo[spike] -= 25 * grid
    symbol = "XAUUSDm" if kind == "gold" else "BTCUSDm"
    m1 = dict(t=t, o=o, h=h, l=lo, c=c, spread_mean=np.full(n, 0.2), n=np.ones(n))
    mk = T2.TMarket2(symbol, m1, int(end))
    rows = {tf: light(mk.tbars(tf)) for tf in ("1H", "4H", "1D", "1W")}
    hw = mk.tbars("1W")
    harness = NS(complete=np.array(hw.complete), **{f: np.array(getattr(hw, f)) for f in FIELDS})
    return rows, int(mk.end_s), harness


@pytest.mark.parametrize("kind,seed", [("gold", 1), ("gold", 2), ("btc", 3), ("btc", 4), ("flat", 5), ("flat", 6)])
def test_synthetic_markets_agree(kind, seed):
    rows, end_s, harness = synthetic_market(kind, seed)
    w = assert_weekly_equal(rows["1D"], end_s, harness, kind)
    assert not w.complete[-1] and w.complete[:-1].all()
    tick = A.MINTICK[rows["1H"].symbol]
    seen = {"ties": 0, "far": 0, "rejected": 0, "both_pivots": 0, "inverted": 0}
    for r in A.ROWS:
        ev = assert_rows_equal(rows[r], f"{kind} {r}")
        ra = A.row_values(rows[r])
        seen["ties"] += int((rows[r].h[1:] == rows[r].h[:-1]).sum())
        seen["far"] += int(((ra["n_ob"] > 0) & (ra["ob"] == 0)).sum() + ((ra["n_fvg"] > 0) & (ra["fvg"] == 0)).sum())
        seen["rejected"] += len(ev["ob_rejected"])
        seen["both_pivots"] += int((~np.isnan(ra["pivot_high"]) & ~np.isnan(ra["pivot_low"])).sum())
        seen["inverted"] += int((ra["swing_h"] < ra["swing_l"]).sum())
    for tf in A.CHART_TFS:
        assert_dashboards_equal(A.structure_dashboard(rows, tf), B.structure_dashboard(rows, tf), f"{kind} {tf}")
        assert_dashboards_equal(A.structure_dashboard(rows, tf, "B"), model_b_dashboard_by_port_b(rows, tf, tick),
                                f"{kind} {tf} model B")
    # the cases are reached: order blocks rejected as overlapping and inverted swing ranges everywhere; equal highs on
    # consecutive bars on the coarse grids; on BTC's climb, zones held but invisible beyond the sentinel (100000 or
    # more from the close); outside bars that are both pivots (flat); gold's holiday Friday opening the next week
    assert seen["rejected"] > 0 and seen["inverted"] > 0, seen
    if kind == "btc":
        assert seen["far"] > 0, seen
    else:
        assert seen["ties"] > 100, seen
    if kind == "flat":
        assert seen["both_pivots"] > 0, seen
    if kind == "gold":
        assert 5 in set(((rows["1W"].t // DAY + 4) % 7).tolist())          # a week that opens on a Friday
