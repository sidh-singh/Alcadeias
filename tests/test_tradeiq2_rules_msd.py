"""
Study 2's Market Structure Dashboard rows (``backtesting/research/tradeiq2_rules_msd.py``): PREREG section 6.2, with
sections 4 (execution), 5 (filters on state rules) and 7 (families, eligibility).

(a) The grid, enumerated again here from the plan's text: 18 MSD-ALONE rows (MSD-A1..A3 x S0, S1 x 1H, 4H, 1D),
    60 MSD-F4 and 60 MSD-F6 rows (RSI, LaRSI, VWRSI (BTC: study 1's VWRSI-RV), TSI, QQE x R1, R2 x S0, S1 x three
    timeframes) and 12 BOS-trend rows (LS, LO x F0, F1 x S1 x three timeframes): 150 per symbol, all eligible. The
    study-1 rows each MSD-F4 / F6 row is paired with (F0, F1, F2) are rows of study 1's grid.csv; the study driver's
    grid check and pairing accept the module.
(b) The rules on hand-made values: the label -> MSD-A1 / A2 / A3; the F6 veto (which rows; strict); BOS-trend LS / LO.
(c) Through the harness on hand-made bars, with the port's dashboard replaced by hand-made outputs (and the base state
    of F4 / F6 by a hand-made one): entries where the state changes, exits where it changes again, a flip at one M1
    open, the window's first bar taking the state, FS and the veto closing and reopening positions as state filters,
    BOS-trend under F1, S1 set from the actual fill at x1.0 and x1.5, and the rule flat after a stop until its state
    changes. These rows have no absolute stop or target level, no target, break-even or legs, and no per-anchor /
    per-day / per-coil limit (state rules, one position per variant): section 4's absolute-level rules have nothing
    to act on, and S1's distance from the actual fill is what is tested instead.
(d) On synthetic bars, nothing replaced: every row's state is the composition, written again here, of the dashboard
    port, study 1's lines / states / filters and study 1's S1; FS is the dashboard's label.
(e) Real data (skipped without the store; both guards closed, nothing at or after 2024-07-01 is loaded):
    - against study 1's Study on study 1's own market (gold's study-2 market starts in 2016, study 1's in 2017): the
      1H / 4H / 1D bars (times, OHLC, tick volume) on study 1's whole span; and on every bar closing after
      2019-01-01, every array of study 1's ``lines_of`` (14 on gold, 17 on BTC) and the S1 distance bit for bit, each
      MSD-FILTER row's base state (study 1's F0 row) and its filtered state;
    - Development counts (labels, A1 / A2 / A3 changes, breaks of structure, BOS-trend flips, F6 vetoes) equal the
      reconciliation's record (``backtest_results/tradeiq_2027/porting/msd.md``, section 6);
    - no look-ahead: every state up to T is unchanged when the data after T is removed;
    - an execution smoke test of one row of each rule on 2019-01-01 .. 2019-06-30 through the harness's runner, at
      x1.0 and x1.5. Its profit or loss is neither printed nor asserted: only the trades' timing and stops;
    - claim 14 on the Development bars only (both of the evidence's windows set to Development). Its check of each
      row bar's last chart bar passes, and the live label differs from model A's on exactly the Development closes the
      reconciliation recorded.
(f) Claim 14 (PREREG 8), on hand-made bars and arrays, on two synthetic markets (gold's calendar, whose Friday 4H, day
    and week bars close at Saturday 00:00 with no chart bar, and 24/7) and on a synthetic Evidence:
    - which row bar a chart bar lies strictly inside;
    - the counts by hand;
    - the closed score is the score each row bar ends with: model B's at the bar's last chart bar, and model A's at
      the chart bar closing with it where one exists (gold's Saturday closes have none);
    - claim14's counts equal a recount by loops;
    - nothing after a window's end is read: the counts are unchanged on data cut at the window's end;
    - the verdict line: a share of 0 does not hold, one change in a window holds there;
    - the rows pass through the driver's claims table, with their verdict words.
"""

from __future__ import annotations

import gc
import importlib
import json
import re
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtesting.config import REPO_ROOT
from backtesting.data import store
from backtesting.research import tradeiq as T1
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_msd as MS
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_msd as R

SYMS = ("XAUUSDm", "BTCUSDm")
T0 = TM.s_of("2019-03-04")                      # a Monday, 00:00 UTC
H = 3600
DAY = 86400
STUDY1_GRID = REPO_ROOT / "backtest_results" / "tradeiq_rsi" / "grid.csv"
# PREREG 6.2, "Size: 18 alone + 60 MSD-F4 + 60 MSD-F6 + 12 BOS-trend = 150 rows per symbol"
PLAN_SIZE = {"MSD-ALONE": 18, "MSD-F4": 60, "MSD-F6": 60, "BOS": 12}
PLAN_FAMILIES = {"MSD-ALONE": 18, "MSD-FILTER": 120, "BOS": 12}
PLAN_TOTAL = 150


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' folders as the guards see them: empty tmp folders (no FINALISTS.md: the hold-outs are closed)."""
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d2


def row(symbol, tail):
    vid = f"{symbol}|{tail}"
    for v in R.variants(symbol):
        if v.id == vid:
            return v
    raise KeyError(vid)


# ───────────────────────────── (a) the grid ─────────────────────────────

def plan_rows(symbol):
    """PREREG 6.2 word by word: (family, rule kind, id)."""
    vw = "VWRSI-RV" if symbol == "BTCUSDm" else "VWRSI"       # "On BTC the VWRSI uses Binance volume ("RV" rows)"
    out = set()
    for tf in ("1H", "4H", "1D"):
        for rule in ("MSD-A1", "MSD-A2", "MSD-A3"):
            for stop in ("S0", "S1"):
                out.add(("MSD-ALONE", "MSD-ALONE", f"{symbol}|{tf}|MSD-ALONE|{rule}|{stop}"))
        for rule in ("MSD-F4", "MSD-F6"):
            for ind in ("RSI", "LaRSI", vw, "TSI", "QQE"):
                for fam in ("R1", "R2"):
                    for stop in ("S0", "S1"):
                        out.add(("MSD-FILTER", rule, f"{symbol}|{tf}|MSD-FILTER|{rule}|{ind}|{fam}|{stop}"))
        for side in ("LS", "LO"):
            for filt in ("F0", "F1"):
                out.add(("BOS", "BOS", f"{symbol}|{tf}|BOS|BOS-trend|{side}|{filt}|S1"))
    return out


@pytest.mark.parametrize("symbol", SYMS)
def test_the_grid_is_the_plans_150_rows(symbol):
    vs = R.variants(symbol)
    want = plan_rows(symbol)
    assert len(want) == PLAN_TOTAL
    got = {(v.family, v.params["rule"] if v.family == "MSD-FILTER" else v.family, v.id) for v in vs}
    assert got == want
    assert len(vs) == PLAN_TOTAL and len({v.id for v in vs}) == PLAN_TOTAL
    fam = pd.Series([v.family for v in vs]).value_counts().to_dict()
    assert fam == PLAN_FAMILIES
    kinds = pd.Series([v.params["rule"] if v.family == "MSD-FILTER" else v.family for v in vs]).value_counts()
    assert kinds.to_dict() == PLAN_SIZE
    for v in vs:
        assert isinstance(v, M.Variant) and v.symbol == symbol and v.script == "MSD"
        assert v.id.startswith(f"{symbol}|{v.tf}|{v.family}|") and not any(c.isspace() for c in v.id)
        assert v.eligible is True and v.info == ""                        # nothing in 6.2 is "not eligible"
        assert v.tf in ("1H", "4H", "1D")
        json.dumps(dict(v.params))                                        # JSON-able
        assert R.spec_of(v).id == v.id
        assert R.describe(v) and R.spec_of(v).rule in R.describe(v)
    # BOS-trend runs with S1 only; the stops of the others are S0 and S1
    assert {v.params["stop"] for v in vs if v.family == "BOS"} == {"S1"}
    assert {v.params["stop"] for v in vs if v.family != "BOS"} == {"S0", "S1"}


def test_only_the_owners_markets_have_rows_and_only_registered_rows_build():
    for s in ("USTECm", "EURUSDm", "GBPUSDm", "XAGUSDm"):
        with pytest.raises(ValueError):
            R.variants(s)
    v = row("XAUUSDm", "1H|MSD-ALONE|MSD-A1|S0")
    bad = M.Variant(v.id.replace("MSD-A1", "MSD-A4"), v.symbol, v.tf, v.script, v.family)
    with pytest.raises(ValueError):
        R.spec_of(bad)
    with pytest.raises(ValueError):
        R.spec_of(M.Variant(v.id, v.symbol, "4H", v.script, v.family))
    # a row rebuilt from grid.csv's fields (params from JSON) is the same row
    re = M.Variant(v.id, v.symbol, v.tf, v.script, v.family, True, "", json.loads(json.dumps(dict(v.params))))
    assert R.spec_of(re) == R.spec_of(v)


@pytest.mark.parametrize("symbol", SYMS)
def test_each_msd_filter_row_is_paired_with_study_1s_f0_f1_f2_rows_of_the_same_base(symbol):
    s1 = pd.read_csv(STUDY1_GRID).set_index("vid")
    f2 = {"1H": ["F0", "F1", "F2-4H", "F2-1D"], "4H": ["F0", "F1", "F2-1D"], "1D": ["F0", "F1"]}
    n = 0
    for v in R.variants(symbol):
        ids = R.study1_ids(v)
        if v.family != "MSD-FILTER":
            assert ids == {}
            continue
        _, tf, _, _, ind, fam, stop = v.id.split("|")
        assert list(ids) == f2[tf]
        for filt, sid in ids.items():
            r = s1.loc[sid]                                             # a row of study 1's grid
            assert (r.symbol, r.tf, r.indicator, r.family, r["filter"], r.stop) == (symbol, tf, ind, fam, filt, stop)
            assert T1.Variant.of(sid).vid == sid
        if symbol == "BTCUSDm":
            assert ind != "VWRSI"                                      # BTC's VWRSI is the RV one
        n += 1
    assert n == 120


def test_the_drivers_grid_check_and_pairing_accept_the_rows():
    try:
        T2 = importlib.import_module("backtesting.research.tradeiq2")
    except Exception as e:  # noqa: BLE001 - the driver is not this module's; without it there is nothing to check
        pytest.skip(f"the study driver does not import here: {e!r}")
    if not all(hasattr(T2, n) for n in ("checked_grid", "study1_pairs")):
        pytest.skip("the study driver has no checked_grid / study1_pairs")
    g, pairs = T2.checked_grid({"msd": R})
    assert len(g) == 2 * PLAN_TOTAL and set(g.module) == {"msd"} and g.eligible.all()
    s1_ids = set(pd.read_csv(STUDY1_GRID).vid)
    for _, v in pairs:
        if v.family == "MSD-FILTER":
            assert T2.study1_pairs(v, {"msd": R}, s1_ids) == R.study1_ids(v)


# ───────────────────────────── (b) the rules on hand-made values ─────────────────────────────

def test_the_label_gives_msd_a1_a2_a3():
    lab = np.array([-2, -1, 0, 1, 2, 1, -1, 0, -2, 2])
    assert list(R.alone_state(lab, "MSD-A1")) == [-1, -1, 0, 1, 1, 1, -1, 0, -1, 1]    # LEAN or more: in
    assert list(R.alone_state(lab, "MSD-A2")) == [0, 0, 0, 1, 1, 1, 0, 0, 0, 1]        # long only
    assert list(R.alone_state(lab, "MSD-A3")) == [-1, 0, 0, 0, 1, 0, 0, 0, -1, 1]      # BULLISH / BEARISH only
    with pytest.raises(ValueError):
        R.alone_state(lab, "MSD-F4")


def test_the_f6_veto_reads_the_4h_d_w_rows_strictly_and_never_the_1h_row():
    n = 7
    d = {"s_1H": np.array([-4, -4, -4, 4, 4, -4, 0]),
         "s_4H": np.array([-1, -1, 1, 1, -1, 0, 2]),
         "s_1D": np.array([-2, -1, 2, 1, -1, -3, 1]),
         "s_1W": np.array([-3, 0, 3, 2, 1, -1, -1])}
    # bar 0: all three below 0 -> long vetoed (the 1H row's -4 plays no part: bar 5 has it too, with the 4H at 0)
    # bar 1: the W row at 0 -> no veto; bar 2 and 3: all above 0 -> short vetoed; bar 4: mixed; bar 6: mixed
    for tf in ("1H", "4H"):
        al, ash = R.veto_allow(d, tf)
        assert list(al) == [False, True, True, True, True, True, True]
        assert list(ash) == [True, True, False, False, True, True, True]
    # the 1D chart: D and W only (no 4H row)
    d1 = {k: v for k, v in d.items() if k in ("s_1D", "s_1W")}
    al, ash = R.veto_allow(d1, "1D")
    assert list(al) == [False, True, True, True, True, False, True]
    assert list(ash) == [True, True, False, False, True, True, True]
    assert len(al) == n
    with pytest.raises(ValueError):
        R.veto_allow(d, "M15")


def test_bos_trend_ls_and_lo():
    bt = np.array([0, 0, 1, 1, -1, -1, 1])
    assert list(R.bos_state(bt, "LS")) == [0, 0, 1, 1, -1, -1, 1]
    assert list(R.bos_state(bt, "LO")) == [0, 0, 1, 1, 0, 0, 1]
    with pytest.raises(ValueError):
        R.bos_state(bt, "SO")
    with pytest.raises(ValueError):
        R.bos_state(np.array([2]), "LS")


def test_base_indicator_names():
    assert R.base_indicator("XAUUSDm", "VWRSI") == "VWRSI"
    assert R.base_indicator("BTCUSDm", "VWRSI") == "VWRSI-RV"
    assert R.base_indicator("BTCUSDm", "QQE") == "QQE"
    with pytest.raises(ValueError):
        R.base_indicator("XAUUSDm", "MA200")


# ───────────────────────────── (c) through the harness on hand-made bars ─────────────────────────────

def hand_market(hours, drift=0.0005, sp=0.1, spikes=(), rng=0.05, fall_from=None, symbol="XAUUSDm"):
    """Continuous M1 bars from T0: the open rises by ``drift`` a minute (falls after hour ``fall_from``), each bar
    ``rng`` above and below its open, the close 0.002 above it, a constant spread. ``spikes``: (M1 index, low)."""
    k = 60 * hours
    j = np.arange(k, dtype=np.float64)
    o = 100.0 + drift * j
    if fall_from is not None:
        top = 60 * fall_from
        o = np.where(j <= top, o, 100.0 + drift * top - drift * (j - top))
    h, l, c = o + rng, o - rng, o + 0.002
    for jj, low in spikes:
        l[jj] = low
    t = T0 + 60 * np.arange(k, dtype=np.int64)
    m1 = {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(k, sp), "n": np.ones(k)}
    return M.TMarket2(symbol, m1)


def pad(x, n, fill=0):
    x = list(x)
    return np.asarray(x + [fill] * (n - len(x)), np.int64)


def fake_dashboard(monkeypatch, n, **cols):
    """Replace the port's structure_dashboard by hand-made outputs for an n-bar chart: label, s_1H, s_4H, s_1D, s_1W,
    bos, bos_trend (missing: zeros). The rows module and FS in tradeiq2_filters both read the port through its
    module attribute, so both see them."""
    base = {k: pad(cols.get(k, ()), n) for k in ("label", "score", "s_1H", "s_4H", "s_1D", "s_1W", "bos",
                                                   "bos_trend")}
    base["max_score"] = np.full(n, 44, np.int64)

    def fake(rows, chart_tf, model="A", mintick=None):
        assert model == "A" and chart_tf == "1H" and len(rows[chart_tf].t) == n
        return {k: v.copy() for k, v in base.items()}
    monkeypatch.setattr(MS, "structure_dashboard", fake)


def run(ctx, v, cost=1.0, start=None):
    ex = R.build(v, ctx)
    assert ex.kind == "state" and not ex.overlays and ex.tf == v.tf
    return M.run_exec(ctx.mk, ex, T0 if start is None else start, int(ctx.mk.t[-1]) + 60, cost)


def legs(r):
    tr = r.trades
    return list(zip(tr.side.tolist(), tr.entry_ix.tolist(), tr.exit_ix.tolist(), tr.reason.tolist()))


def test_msd_a1_a2_a3_enter_where_the_state_changes_exit_where_it_changes_and_flip_at_one_open(monkeypatch):
    mk = hand_market(40)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    assert list(b.ex[:13]) == [60 * (i + 1) for i in range(13)]       # bar i is decided at T0 + (i+1) h
    fake_dashboard(monkeypatch, 40, label=[0, 0, 0, 0, 0, 1, 2, 1, 0, -1, -2, 1, 0])
    r = run(ctx, row("XAUUSDm", "1H|MSD-ALONE|MSD-A1|S0"))
    # long at bar 5's close, flat at 8; short at 9; the flip to long at 11 closes the short and opens the long at
    # the same M1 open; flat at 12
    assert legs(r) == [(1, 360, 540, "signal"), (-1, 600, 720, "signal"), (1, 720, 780, "signal")]
    tr = r.trades
    assert np.allclose(tr.entry, [mk.o[360] + 0.1, mk.o[600], mk.o[720] + 0.1])      # buys at the ask
    assert np.allclose(tr.exit, [mk.o[540], mk.o[720] + 0.1, mk.o[780]])
    assert tr.risk.isna().all() and tr.r.isna().all()                                # S0: no stop, no R
    ctx2 = M.Context(mk)
    assert legs(run(ctx2, row("XAUUSDm", "1H|MSD-ALONE|MSD-A2|S0"))) == [(1, 360, 540, "signal"),
                                                                        (1, 720, 780, "signal")]
    ctx3 = M.Context(mk)
    assert legs(run(ctx3, row("XAUUSDm", "1H|MSD-ALONE|MSD-A3|S0"))) == [(1, 420, 480, "signal"),
                                                                        (-1, 660, 720, "signal")]


def test_the_windows_first_bar_takes_the_state(monkeypatch):
    ctx = M.Context(hand_market(40))
    fake_dashboard(monkeypatch, 40, label=[0] * 20 + [1] * 11)
    r = run(ctx, row("XAUUSDm", "1H|MSD-ALONE|MSD-A1|S0"), start=T0 + 22 * H)
    # bar 21 closes at the window's start, bar 22 is its first bar: in there although the state began at bar 20
    assert legs(r) == [(1, 60 * 23, 60 * 32, "signal")]
    assert r.n_decisions == 40 - 22 - 1                       # bars 22..38 (bar 39 would fill after the data)


@pytest.mark.parametrize("cost", [1.0, 1.5])
def test_s1_is_set_from_the_actual_fill_and_the_rule_stays_flat_after_a_stop(monkeypatch, cost):
    spike = 24 * 60 + 10                                   # an M1 bar inside hour 24 whose low is far below
    mk = hand_market(40, spikes=[(spike, 90.0)])
    ctx = M.Context(mk)
    fake_dashboard(monkeypatch, 40, label=[0] * 20 + [1] * 11 + [0, 0] + [1] * 3)
    v = row("XAUUSDm", "1H|MSD-ALONE|MSD-A1|S1")
    d = R.s1_stop(ctx, "1H")
    assert np.array_equal(d, TM.s1_stop(ctx.bars("1H")), equal_nan=True)            # study 1's S1
    assert np.allclose(d[13:20], 3.0 * M.atr14(ctx.bars("1H"))[13:20])
    r = run(ctx, v, cost)
    # the stop hits inside the spike's M1 bar; the state stays long until bar 30, so nothing is entered again
    # until it changes (flat at 31-32, long at 33); that trade ends where the state goes flat (bar 36)
    assert legs(r) == [(1, 1260, spike, "stop"), (1, 2040, 2220, "signal")]
    tr = r.trades
    fill = mk.o[1260] + cost * 0.1                                                    # the ask at this cost
    assert np.isclose(tr.entry.iloc[0], fill)
    assert np.isclose(tr.exit.iloc[0], fill - d[20] - cost * 0.1)                    # the level, one spread worse
    assert np.allclose(tr.risk, [d[20], d[33]])                                     # the distance of its bar
    assert d[33] > 2 * d[20]                                                         # (the spike is in the ATR)


def test_msd_f4_is_fs_as_a_state_filter_on_the_base(monkeypatch):
    ctx = M.Context(hand_market(40))
    base = np.array([1] * 20 + [-1] * 20, np.int8)
    monkeypatch.setattr(R, "base_state", lambda c, tf, ind, fam: base)
    lab = [0, 0, 1, 1, 2, 0, -1, 1, 1] + [0] * 11 + [-1, -2, -1, 1]
    fake_dashboard(monkeypatch, 40, label=lab)
    v = row("XAUUSDm", "1H|MSD-FILTER|MSD-F4|RSI|R1|S0")
    al, ash = F.allow(ctx, "1H", "FS")
    assert np.array_equal(al, pad(lab, 40) >= 1) and np.array_equal(ash, pad(lab, 40) <= -1)
    st = R.state_of(v, ctx)
    assert np.array_equal(st, F.as_state_filter(base, al, ash))
    # in where FS turns in favour while the base is long (bar 2), out where it turns against (5); the base's long at
    # a LEAN BEAR bar is flat (6); in again at 7; the base's short at LEAN BEAR / BEARISH (20-22), flat at LEAN BULL
    assert legs(run(ctx, v)) == [(1, 180, 360, "signal"), (1, 480, 600, "signal"), (-1, 1260, 1440, "signal")]


def test_msd_f6_vetoes_a_long_while_4h_d_w_all_score_below_0_and_a_short_while_all_above(monkeypatch):
    ctx = M.Context(hand_market(40))
    base = np.array([1] * 20 + [-1] * 20, np.int8)
    monkeypatch.setattr(R, "base_state", lambda c, tf, ind, fam: base)
    s4 = [0, 0, 0, -1, -2, -1, 0, 0, -1] + [0] * 15 + [1, 2, 1, 0, 1]
    s1d = [0, 0, 0, -1, -1, -1, 0, 0, -1] + [0] * 15 + [1, 1, 1, 0, 2]
    s1w = [0, 0, 0, -3, -2, -1, 0, 0, 0] + [0] * 15 + [2, 1, 3, 0, -1]
    fake_dashboard(monkeypatch, 40, s_1H=[-4] * 40, s_4H=s4, s_1D=s1d, s_1W=s1w)
    v = row("XAUUSDm", "1H|MSD-FILTER|MSD-F6|QQE|R1|S0")
    st = R.state_of(v, ctx)
    want = base.copy()
    want[3:6] = 0                                          # all three below 0 (bar 8: the W row at 0, no veto)
    want[24:27] = 0                                        # all three above 0 (bar 28: mixed)
    assert np.array_equal(st, want)
    # long from the window's first bar to the veto (3), again after it (6) until the flip to short at 20 (one open),
    # short until the veto (24), again from 27 to the window's end
    assert legs(run(ctx, v)) == [(1, 60, 240, "signal"), (1, 420, 1260, "signal"), (-1, 1260, 1500, "signal"),
                                 (-1, 1680, 2399, "end")]


def test_bos_trend_ls_lo_with_s1(monkeypatch):
    ctx = M.Context(hand_market(40))
    fake_dashboard(monkeypatch, 40, bos_trend=[0] * 15 + [1, 1, 1, -1, -1] + [1] * 20)
    d = R.s1_stop(ctx, "1H")
    r = run(ctx, row("XAUUSDm", "1H|BOS|BOS-trend|LS|F0|S1"))
    assert legs(r) == [(1, 960, 1140, "signal"), (-1, 1140, 1260, "signal"), (1, 1260, 2399, "end")]
    assert np.allclose(r.trades.risk, [d[15], d[18], d[20]])
    r = run(ctx, row("XAUUSDm", "1H|BOS|BOS-trend|LO|F0|S1"))
    assert legs(r) == [(1, 960, 1140, "signal"), (1, 1260, 2399, "end")]


def test_bos_trend_under_f1_closes_the_long_when_the_close_falls_below_its_ma200(monkeypatch):
    # 300 hours: up until hour 230, then down at the same slope; wide M1 bars, so S1 (3 ATR) stays far away
    mk = hand_market(300, fall_from=230, rng=1.0)
    ctx = M.Context(mk)
    b = ctx.bars("1H")
    fake_dashboard(monkeypatch, 300, bos_trend=[0] * 210 + [1] * 90)
    ma = I.ma200(b.c)
    above = b.c > ma
    k = 210 + int(np.flatnonzero(~above[210:])[0])                 # the first bar from 210 not above its MA200
    assert 240 < k < 299 and above[210:k].all()
    for side in ("LS", "LO"):
        v = row("XAUUSDm", f"1H|BOS|BOS-trend|{side}|F1|S1")
        st = R.state_of(v, ctx)
        al, ash = F.allow(ctx, "1H", "F1")
        assert np.array_equal(st, F.as_state_filter(R.bos_state(pad([0] * 210 + [1] * 90, 300), side), al, ash))
        # the break says long all along; F1 allows it from bar 210 until the close falls below the MA200 (bar k),
        # then neither side (no short: the trend is long)
        assert legs(run(ctx, v)) == [(1, int(b.ex[210]), int(b.ex[k]), "signal")]


def test_rows_states_are_cached_read_only_and_warm_computes_them():
    ctx = M.Context(hand_market(60))
    vs = R.variants("XAUUSDm")
    R.warm(ctx, vs)
    n = len(ctx.cache)
    for v in vs:
        ex = R.build(v, ctx)
        assert ex.state.shape == (len(ctx.bars(v.tf)),)
        assert (ex.stop is not None) == (v.params["stop"] == "S1")
        st = R.state_of(v, ctx)
        assert st is R.state_of(v, ctx) and not st.flags.writeable
    assert len(ctx.cache) == n                                         # nothing new after warm
    with pytest.raises(ValueError):
        R.state_of(row("BTCUSDm", "1H|MSD-ALONE|MSD-A1|S0"), ctx)


# ───────────────────────────── (d) synthetic bars, nothing replaced ─────────────────────────────

@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    """A 24/7 market of 320 days with two-day trends, so that the dashboard's labels, the veto, the breaks, every
    oscillator and the MA200s (the 1D one after 200 days) all change; gold's contract (tick volume)."""
    rng = np.random.default_rng(11)
    days = 320
    t = TM.s_of("2019-01-07") + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    drift = np.repeat(rng.normal(0.0, 0.004, n // 2880 + 1), 2880)[:n]
    c = 1300.0 + np.cumsum(drift + rng.normal(0.0, 0.25, n))
    o = np.concatenate(([1300.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.1, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.1, n))
    m1 = {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(n, 0.2),
          "n": rng.integers(1, 30, n).astype(np.float64)}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", tmp_path_factory.mktemp("closed2"))
        mp.setattr(TM, "STUDY_DIR", tmp_path_factory.mktemp("closed1"))
        mk = M.TMarket2("XAUUSDm", m1)
    return M.Context(mk)


def test_every_rows_state_is_the_plans_composition_on_synthetic_bars(synth):
    ctx = synth
    mk = ctx.mk
    st1 = T1.Study(mk)                                                  # study 1's own states and stops
    seen = {"veto": 0, "fs": 0, "flips": 0, "labels": set()}
    for tf in ("1H", "4H", "1D"):
        rows = {r: ctx.bars(r) for r in {"1H": ("1H", "4H", "1D", "1W"), "4H": ("4H", "1D", "1W"),
                                          "1D": ("1D", "1W")}[tf]}
        d = MS.structure_dashboard(rows, tf)
        lab = np.asarray(d["label"], np.int64)
        seen["labels"] |= set(lab.tolist())
        L = T1.lines_of(mk, tf)                                         # study 1's lines, computed again
        al_fs, ash_fs = F.allow(ctx, tf, "FS")
        assert np.array_equal(al_fs, lab >= 1) and np.array_equal(ash_fs, lab <= -1)
        veto_rows = ("4H", "1D", "1W") if tf != "1D" else ("1D", "1W")
        s = np.stack([np.asarray(d[f"s_{r}"]) for r in veto_rows])
        no_long, no_short = np.all(s < 0, axis=0), np.all(s > 0, axis=0)
        seen["veto"] += int(no_long.sum() + no_short.sum())
        a1_f1, s1_f1 = T1.allowed_of(L, "F1")
        stop = TM.s1_stop(ctx.bars(tf))
        assert np.array_equal(stop, st1.stops[tf], equal_nan=True)
        for v in R.variants("XAUUSDm"):
            if v.tf != tf:
                continue
            p = v.params
            if v.family == "MSD-ALONE":
                k = 2 if p["rule"] == "MSD-A3" else 1
                want = np.where(lab >= k, 1, np.where(lab <= -k, -1, 0))
                if p["rule"] == "MSD-A2":
                    want = np.maximum(want, 0)
            elif v.family == "MSD-FILTER":
                raw = T1.raw_state(L, p["indicator"], p["base_family"])
                assert np.array_equal(raw, st1.state(T1.Variant.of(R.study1_ids(v)["F0"]))), v.id
                if p["rule"] == "MSD-F4":
                    want = T1.apply_filter(raw, lab >= 1, lab <= -1)
                    seen["fs"] += int(np.sum(want != raw))
                else:
                    want = T1.apply_filter(raw, ~no_long, ~no_short)
            else:
                want = np.asarray(d["bos_trend"], np.int64)
                if p["sides"] == "LO":
                    want = np.maximum(want, 0)
                if p["filter"] == "F1":
                    want = T1.apply_filter(want, a1_f1, s1_f1)
                seen["flips"] += int(np.sum(want[1:] != want[:-1]))
            got = R.state_of(v, ctx)
            assert np.array_equal(got, want), v.id
            ex = R.build(v, ctx)
            if p["stop"] == "S1":
                assert np.array_equal(ex.stop, stop, equal_nan=True), v.id
            else:
                assert ex.stop is None
    # the case is not empty: every label occurs, the veto and FS act, BOS-trend flips
    assert seen["labels"] == {-2, -1, 0, 1, 2} and seen["veto"] > 50 and seen["fs"] > 500 and seen["flips"] > 50


# ───────────────────────────── (e) real data ─────────────────────────────

@pytest.fixture(scope="module", params=SYMS)
def real(request, tmp_path_factory):
    """One symbol at a time (the module-scoped parameter groups the tests by symbol): the study-2 market served to
    the hold-out start with both guards closed, and its Context."""
    sym = request.param
    months = store.available_months(sym)
    first = int(M.data_start(sym)[:4])
    if (2024, 6) not in months or (first, 1) not in months:
        pytest.skip(f"the tick store of {sym} is not on this machine")
    if sym == "BTCUSDm" and not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
        pytest.skip("the Binance files are not on this machine")
    mp = pytest.MonkeyPatch()
    mp.setattr(M, "STUDY_DIR", tmp_path_factory.mktemp(f"closed2_{sym}"))
    mp.setattr(TM, "STUDY_DIR", tmp_path_factory.mktemp(f"closed1_{sym}"))
    mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
    mk = M.load(sym, end=M.HOLDOUT_START)
    assert mk.end_s == M.CUT_S and int(mk.t[-1]) < M.CUT_S
    ctx = M.Context(mk)
    yield sym, ctx
    mp.undo()
    del ctx, mk
    gc.collect()


def same_bits(a, b) -> bool:
    """Bit for bit: the same dtype and shape, floats compared by their 64-bit patterns (a NaN must sit on the same
    bar, and -0.0 is not 0.0)."""
    a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        a, b = a.view(f"u{a.itemsize}"), b.view(f"u{b.itemsize}")
    return bool(np.array_equal(a, b))


def test_same_bits_by_hand():
    x = np.array([1.0, np.nan, -0.0, 2.5])
    assert same_bits(x, x.copy()) and same_bits(np.array([1, 2], np.int8), np.array([1, 2], np.int8))
    assert not same_bits(x, np.array([1.0, np.nan, 0.0, 2.5]))                 # -0.0 against 0.0
    assert not same_bits(x, np.array([1.0, 1.0, -0.0, 2.5]))                   # NaN against a number
    assert not same_bits(x, np.nextafter(x, 3.0))                              # one ulp
    assert not same_bits(np.array([1, 2], np.int8), np.array([1, 2], np.int64))   # the dtype counts


def test_bars_lines_s1_and_base_states_are_study_1s_on_every_bar_from_2019(real):
    """Against study 1's Study on study 1's own market (gold from 2017, the study-2 market from 2016): the bars on study
    1's whole span; on every bar closing after 2019-01-01 to the hold-out start, every array of ``lines_of`` and the
    S1 distance bit for bit, each MSD-FILTER row's base state against study 1's F0 row and its filtered state."""
    sym, ctx = real
    mk1 = TM.load(sym, end=TM.HOLDOUT_START)                       # study 1's own market (gold from 2017)
    st1 = T1.Study(mk1)
    a_s = TM.s_of("2019-01-01")
    n_rows = n_lines = 0
    n_keys = 17 if T1.has_rv(sym) else 14                         # BTC adds VWRSI-RV, its score, the missing klines
    for tf in R.TFS:
        b2, b1 = ctx.bars(tf), st1.bars[tf]
        k = int(np.searchsorted(b2.t, b1.t[0]))
        for f in ("t", "tc", "o", "h", "l", "c", "vol"):
            assert np.array_equal(getattr(b2, f)[k:], getattr(b1, f)), (tf, f)
        sel1 = np.flatnonzero(b1.tc > a_s)
        sel2 = sel1 + k
        L2, L1 = R.study1_lines(ctx, tf), st1.lines[tf]                    # every line study 1 reads
        assert set(L2) == set(L1) and len(L1) == n_keys
        for key in L1:
            assert same_bits(np.asarray(L2[key])[sel2], np.asarray(L1[key])[sel1]), (tf, key)
        n_lines += len(L1)
        assert same_bits(R.s1_stop(ctx, tf)[sel2], st1.stops[tf][sel1]), tf
        for v in R.variants(sym):
            if v.tf != tf or v.family != "MSD-FILTER":
                continue
            s = R.spec_of(v)
            base1 = st1.state(T1.Variant.of(R.study1_ids(v)["F0"]))      # study 1's F0 row: the unfiltered base
            assert np.array_equal(R.base_state(ctx, tf, s.indicator, s.base_family)[sel2], base1[sel1]), v.id
            al, ash = R.filter_allow(ctx, tf, s.filt)
            want = T1.apply_filter(base1[sel1], al[sel2], ash[sel2])
            assert np.array_equal(R.state_of(v, ctx)[sel2], want), v.id
            n_rows += 1
    assert n_rows == 120 and n_lines == 3 * n_keys
    del st1, mk1
    gc.collect()


# porting/msd.md section 6 (chart bars closing after 2019-01-01 00:00 and at or before 2023-01-01 00:00): bars,
# labels BULLISH / LEAN BULL / NEUTRAL / LEAN BEAR / BEARISH, A1 / A2 / A3 changes, BOS bull / bear, BOS-trend
# flips and % long, F6 veto long / short in %
RECORD = {
    ("XAUUSDm", "1H"): (23591, (3540, 6034, 9047, 4072, 898), (2038, 1081, 1106), (576, 506), 540, 54.0, (6.4, 16.5)),
    ("XAUUSDm", "4H"): (6386, (1327, 1294, 2314, 1028, 423), (607, 323, 386), (159, 146), 158, 55.3, (6.4, 16.4)),
    ("XAUUSDm", "1D"): (1032, (298, 151, 302, 177, 104), (154, 78, 102), (28, 17), 18, 55.0, (17.6, 32.3)),
    ("BTCUSDm", "1H"): (35017, (4898, 10670, 13985, 4866, 598), (3196, 2016, 1204), (882, 770), 806, 54.3,
                        (3.1, 19.5)),
    ("BTCUSDm", "4H"): (8757, (1542, 2644, 3177, 1180, 214), (892, 560, 430), (222, 193), 210, 54.0, (3.2, 19.4)),
    ("BTCUSDm", "1D"): (1460, (345, 425, 408, 226, 56), (212, 130, 114), (36, 29), 30, 54.0, (7.1, 38.4)),
}


def test_development_counts_equal_the_reconciliation_record(real):
    sym, ctx = real
    a_s, z_s = TM.s_of("2019-01-01"), TM.s_of("2023-01-01")
    for tf in R.TFS:
        bars, labels, changes, bos, flips, long_pct, veto = RECORD[(sym, tf)]
        b = ctx.bars(tf)
        sel = np.flatnonzero((b.tc > a_s) & (b.tc <= z_s))
        d = R.dashboard(ctx, tf)
        al_fs, ash_fs = F.allow(ctx, tf, "FS")                            # the filters module's FS is this label
        assert np.array_equal(al_fs, d["label"] >= 1) and np.array_equal(ash_fs, d["label"] <= -1)
        ch = lambda st: int(np.sum(st[sel] != st[sel - 1]))
        assert len(sel) == bars
        assert tuple(int(np.sum(d["label"][sel] == k)) for k in (2, 1, 0, -1, -2)) == labels
        assert tuple(ch(R.state_of(row(sym, f"{tf}|MSD-ALONE|{r}|S0"), ctx)) for r in R.ALONE_RULES) == changes
        assert (int(np.sum(d["bos"][sel] == 1)), int(np.sum(d["bos"][sel] == -1))) == bos
        bt = R.state_of(row(sym, f"{tf}|BOS|BOS-trend|LS|F0|S1"), ctx)
        assert ch(bt) == flips and round(100.0 * float(np.mean(bt[sel] == 1)), 1) == long_pct
        assert np.all(bt[sel] != 0)                                       # never "no break yet" from 2019
        al, ash = R.filter_allow(ctx, tf, "MSD-F6")
        assert (round(100.0 * float(np.mean(~al[sel])), 1), round(100.0 * float(np.mean(~ash[sel])), 1)) == veto


@pytest.mark.parametrize("T", ["2020-11-18 13:37", "2022-06-05 21:10"])
def test_states_up_to_T_do_not_change_when_the_data_after_T_is_removed(real, T):
    sym, ctx = real
    T_s = TM.s_of(T)
    cut = M.load(sym, end=T)
    assert int(cut.t[-1]) < T_s
    cctx = M.Context(cut)
    changes = 0
    for tf in R.TFS:
        n = int(np.sum(cctx.bars(tf).tc <= T_s))
        assert n > 100
        assert np.array_equal(ctx.bars(tf).tc[:n], cctx.bars(tf).tc[:n])
        assert np.array_equal(R.s1_stop(ctx, tf)[:n], R.s1_stop(cctx, tf)[:n], equal_nan=True)
        dash_f, dash_c = R.dashboard(ctx, tf), R.dashboard(cctx, tf)
        for k in dash_f:
            assert np.array_equal(dash_f[k][:n], dash_c[k][:n]), (tf, k)
    for v in R.variants(sym):
        n = int(np.sum(cctx.bars(v.tf).tc <= T_s))
        a, b = R.state_of(v, ctx), R.state_of(v, cctx)
        assert np.array_equal(a[:n], b[:n]), v.id
        changes += int(np.sum(a[1:n] != a[:n - 1]))
    assert changes > 20_000
    del cctx, cut
    gc.collect()


def test_one_row_of_each_rule_runs_on_development_data(real):
    """The smoke test: one row of each rule (MSD-A1, A2, A3, F4, F6, BOS-trend; S0 and S1; 1H, 4H, 1D) through the
    harness's runner on 2019-01-01 .. 2019-06-30 at x1.0 and x1.5. It checks when the trades enter, their sides,
    their stops and the counts, never their profit or loss (nothing of it is printed)."""
    sym, ctx = real
    vw = "VWRSI-RV" if sym == "BTCUSDm" else "VWRSI"
    tails = ["1H|MSD-ALONE|MSD-A1|S0", "4H|MSD-ALONE|MSD-A2|S1", "1H|MSD-ALONE|MSD-A3|S1",
             f"4H|MSD-FILTER|MSD-F4|{vw}|R1|S1", "1H|MSD-FILTER|MSD-F6|QQE|R2|S0", "1D|MSD-FILTER|MSD-F4|TSI|R1|S0",
             "4H|BOS|BOS-trend|LS|F1|S1", "1D|BOS|BOS-trend|LO|F0|S1"]
    a, z = "2019-01-01", "2019-07-01"
    a_s = TM.s_of(a)
    total = 0
    for tail in tails:
        v = row(sym, tail)
        ex = R.build(v, ctx)
        b = ctx.bars(v.tf)
        st = R.state_of(v, ctx)
        iz = int(np.searchsorted(ctx.mk.t, TM.s_of(z), side="left"))
        sel = np.flatnonzero((b.tc > a_s) & (b.ex < iz))
        s = st[sel].astype(np.int64)
        changed = np.r_[True, s[1:] != s[:-1]]
        ent = np.flatnonzero(changed & (s != 0))
        for cost in (1.0, 1.5):
            r = M.run_exec(ctx.mk, ex, a, z, cost)
            assert r.kind == "state" and r.n_decisions == len(sel)
            tr = r.trades
            # every entry is a change of the state to long or short (and the window's first bar), with its side
            assert tr.entry_ix.tolist() == b.ex[sel[ent]].tolist(), tail
            assert tr.side.tolist() == s[ent].tolist(), tail
            # each trade ends at the next change, or earlier at a stop, or at the window's end
            nxt = [int(b.ex[sel[np.flatnonzero(changed[e + 1:])[0] + e + 1]]) if changed[e + 1:].any() else iz - 1
                   for e in ent]
            for x, why, nx in zip(tr.exit_ix.tolist(), tr.reason.tolist(), nxt):
                assert (why == "signal" and x == nx) or (why in ("stop", "gap stop") and x <= nx) or \
                       (why == "end" and nx == iz - 1 and x == iz - 1), tail
            if v.params["stop"] == "S1":
                assert np.allclose(tr.risk.to_numpy(), R.s1_stop(ctx, v.tf)[sel[ent]]), tail
            else:
                assert tr.risk.isna().all() and not set(tr.reason) & {"stop", "gap stop"}, tail
            sc = M.scores(r)
            assert sc["trades"] == len(tr) and sc["n_decisions"] == len(sel)
            assert sc["r_trades"] == (len(tr) if v.params["stop"] == "S1" else 0)
            total += len(tr)
    assert total > 100


# the reconciliation's record (tests/test_tradeiq2_ind_msd.py RECORDED_CHARTS, porting/msd.md section 3 item 21): the
# Development chart bars where model B's label differs from model A's
MODEL_B_LABELS = {("XAUUSDm", "1H"): 4497, ("XAUUSDm", "4H"): 1155, ("XAUUSDm", "1D"): 141,
                  ("BTCUSDm", "1H"): 6971, ("BTCUSDm", "4H"): 1753, ("BTCUSDm", "1D"): 227}


def test_claim14_on_the_development_bars(real):
    """Claim 14 on the real bars, with both of the evidence's windows set to Development, so nothing of Validation is
    read. It runs, so its check that each row bar's last chart bar shows the bar's closed score passes on every row bar
    of the window, gold's Saturday closes included. Every row has chart closes to count. The live label differs from
    model A's on exactly the Development closes the reconciliation recorded. The shares themselves are claim 14's
    evidence: they are counted here, not asserted."""
    sym, ctx = real
    got = R.claim14(FakeEv({sym: ctx}, windows=("dev", "dev")))
    assert len(got) == 9 and {g["symbol"] for g in got} == {sym}
    for g in got:
        assert g["dev"] == g["val"]
        tf = g["part"].split(" ")[0]
        if "(information)" in g["part"]:
            kd, n, ks, n2 = fracs(g["dev"])
            assert kd == MODEL_B_LABELS[(sym, tf)] and n == n2 and ks <= kd < n
        else:
            d, n, bd, bn = fracs(g["dev"])
            assert 0 <= d <= n and bd <= bn and n > {"1H": 15000, "4H": 5000, "1D": 800}[tf] and bn > 200
            assert isinstance(g["dev_ok"], bool)


# ───────────────────────────── (f) claim 14 ─────────────────────────────

ROWS_OF = {"1H": ("1H", "4H", "1D", "1W"), "4H": ("4H", "1D", "1W"), "1D": ("1D", "1W")}    # L692, written again
WORD = {"4H": "4H", "1D": "D", "1W": "W"}


class FakeEv:
    """What claim14 reads of the driver's Evidence (``tradeiq2.Evidence``): the symbols, the contexts, and ``span`` /
    ``in_window`` as the driver computes them ('dev' and 'val' stand for the real windows ``windows``)."""

    def __init__(self, ctxs, windows=("dev", "val")):
        self.symbols = list(ctxs)
        self._ctx = dict(ctxs)
        self.windows = windows

    def context(self, symbol):
        return self._ctx[symbol]

    def span(self, window, symbol):
        return M.window_span(dict(zip(("dev", "val"), self.windows))[window], symbol)

    def in_window(self, symbol, tf, window):
        b = self.context(symbol).bars(tf)
        a, z = (TM.s_of(x) for x in self.span(window, symbol))
        return (b.t >= a) & (b.tc <= z)


def fracs(text):
    """The 'k/n' numbers of a claim cell, in order."""
    return tuple(int(x) for pair in re.findall(r"(\d+)/(\d+)", text) for x in pair)


def times(t, tc):
    return SimpleNamespace(t=np.asarray(t, np.int64), tc=np.asarray(tc, np.int64))


def test_forming_bar_is_the_row_bar_a_chart_bar_lies_strictly_inside():
    # a 4H row: [0, 4h), [4h, 8h), a hole, [12h, 16h), and a gold Friday [20h, 24h) whose only 1H bar is [20h, 21h)
    row = times([0, 4 * H, 12 * H, 20 * H], [4 * H, 8 * H, 16 * H, 24 * H])
    hours = [0, 1, 2, 3, 4, 5, 6, 7, 9, 12, 13, 14, 15, 20, 25]          # 9: in the hole; 25: after the last row bar
    chart = times([x * H for x in hours], [(x + 1) * H for x in hours])
    # hours 0-2 lie inside bar 0 and hour 3 closes with it; 4-6 inside bar 1, 7 closes with it; 9 in no bar; 12-14
    # inside bar 2, 15 closes with it; 20 strictly inside the Friday bar (it closes at 21h, the bar at 24h); 25 in none
    assert R.forming_bar(chart, row).tolist() == [0, 0, 0, -1, 1, 1, 1, -1, -1, 2, 2, 2, -1, 3, -1]
    assert R.forming_bar(times([-H], [0]), row).tolist() == [-1]                 # before the first row bar
    assert R.forming_bar(chart, times([], [])).tolist() == [-1] * len(hours)
    assert R.forming_bar(chart, row).dtype == np.int64


def test_forming_counts_by_hand():
    k = np.array([0, 0, -1, 1, 1, 1, 2, 2])          # the row bar each of 8 chart bars lies strictly inside
    sf = np.array([1, 2, 9, 0, 0, -1, 3, 3])         # the forming scores at the chart closes
    sc = np.array([2, 0, 3])                         # the scores the 3 row bars close with
    every = np.ones(8, bool)
    # row bar 0: close 0 differs (1 against 2), close 1 agrees; row bar 1: closes 3 and 4 agree, close 5 differs (-1
    # against 0); row bar 2: both agree. Chart bar 2 lies in no row bar: never counted, whatever its score.
    assert R.forming_counts(sf, sc, k, every, np.ones(3, bool)) == {"closes": 7, "differ": 2, "bars": 3,
                                                                    "bars_differ": 2}
    # a window that keeps chart bars 3.. and row bars 1 and 2
    chart_ok = np.array([False] * 3 + [True] * 5)
    assert R.forming_counts(sf, sc, k, chart_ok, np.array([False, True, True])) == {"closes": 5, "differ": 1,
                                                                                    "bars": 2, "bars_differ": 1}
    # a row bar outside the window drops its chart closes, though they lie inside it
    assert R.forming_counts(sf, sc, k, every, np.array([True, False, True])) == {"closes": 4, "differ": 1,
                                                                                 "bars": 2, "bars_differ": 1}
    # a chart bar outside the window is dropped on its own (in claim14 it is implied: a chart bar strictly inside a
    # row bar of the window lies in the window)
    assert R.forming_counts(sf, sc, k, np.arange(8) != 5, np.ones(3, bool)) == {"closes": 6, "differ": 1,
                                                                                 "bars": 3, "bars_differ": 1}
    assert R.forming_counts(sf, sc, k, ~every, np.ones(3, bool)) == {"closes": 0, "differ": 0, "bars": 0,
                                                                     "bars_differ": 0}
    with pytest.raises(ValueError):
        R.forming_counts(sf, sc, k[:-1], every, np.ones(3, bool))
    with pytest.raises(ValueError):
        R.forming_counts(sf, sc, k, every, np.ones(2, bool))


def claim_m1(gold, days, seed, start):
    """Synthetic M1 bars with two-day trends (as ``synth``): gold's sessions (Sunday from 22:05 UTC, a daily break
    20:57-22:02, Friday to 20:57: its Friday 4H, day and week bars close at Saturday 00:00, when no 1H bar closes) or
    24/7."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    if gold:
        minute = (t % DAY) // 60
        weekday = ((t // DAY) + 4) % 7                                   # 0 = Sunday
        keep = ~((minute >= 20 * 60 + 57) & (minute < 22 * 60 + 2)) & (weekday != 6)
        keep &= ~((weekday == 0) & (minute < 22 * 60 + 5)) & ~((weekday == 5) & (minute >= 20 * 60 + 57))
        t = t[keep]
    n = len(t)
    drift = np.repeat(rng.normal(0.0, 0.004, n // 2880 + 1), 2880)[:n]
    c = 1300.0 + np.cumsum(drift + rng.normal(0.0, 0.25, n))
    o = np.concatenate(([1300.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.1, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.1, n))
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "spread_mean": np.full(n, 0.2), "n": np.ones(n)}


@pytest.fixture(scope="module")
def claim_ctxs(tmp_path_factory):
    """Gold's calendar (XAUUSDm, from Sunday 2019-01-06) and a 24/7 market (BTCUSDm, from Monday 2019-01-07), 320 days
    each, ending inside a week (the last week forming); their M1 arrays for the cuts."""
    m1 = {"XAUUSDm": claim_m1(True, 320, 21, "2019-01-06"), "BTCUSDm": claim_m1(False, 320, 22, "2019-01-07")}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", tmp_path_factory.mktemp("closed2_claim"))
        mp.setattr(TM, "STUDY_DIR", tmp_path_factory.mktemp("closed1_claim"))
        ctxs = {s: M.Context(M.TMarket2(s, x)) for s, x in m1.items()}
    return ctxs, m1


@pytest.fixture
def claim_windows(monkeypatch):
    """The evidence's two windows on the synthetic markets (after 17 weeks of warm-up). 'val' runs past the data end
    (22 / 23 Nov), so the last week, still forming (its close time is its ISO end, 25 Nov), lies inside it by the
    clock: only a complete row bar may be counted."""
    monkeypatch.setitem(M.WINDOWS, "dev", ("2019-05-01", "2019-08-01"))
    monkeypatch.setitem(M.WINDOWS, "val", ("2019-08-01", "2019-12-01"))


def test_closed_score_is_the_score_each_row_bar_ends_with(claim_ctxs):
    """The closed score (MSD-P8): the row's committed values with the swing vote at its own close. It is model B's
    forming score at the row bar's last chart bar (the forming candle is the whole bar there), and model A's score at
    the chart bar closing with the row bar where one exists. Gold's Friday 4H, day and week bars close at Saturday
    00:00, so on its 1H chart no chart bar closes with them and model A cannot give their score there."""
    ctxs, _ = claim_ctxs
    for s, ctx in ctxs.items():
        tick = MS.MINTICK[s]
        for tf in R.TFS:
            bars = {r: ctx.bars(r) for r in ROWS_OF[tf]}
            A = MS.structure_dashboard(bars, tf, "A")
            B = MS.structure_dashboard(bars, tf, "B")
            ch = bars[tf]
            for r in ROWS_OF[tf][1:]:
                rb = bars[r]
                sc = R.closed_score(ctx, r)
                rv = MS.row_values(rb)
                want = (rv["struct"].astype(np.int64) + rv["ob"] + rv["fvg"]
                        + MS.swing_factor(rb.c, rv["swing_h"], rv["swing_l"], tick))
                assert np.array_equal(sc, want) and sc.dtype == np.int64 and not sc.flags.writeable
                assert sc is R.closed_score(ctx, r) and -4 <= sc.min() and sc.max() <= 4
                n_closing = n_none = 0
                for i in range(len(rb.t)):
                    inside = np.flatnonzero((ch.t >= rb.t[i]) & (ch.tc <= rb.tc[i]))
                    if not len(inside):
                        continue
                    j = inside[-1]
                    assert B[f"s_{r}"][j] == sc[i], (s, tf, r, i)
                    if ch.tc[j] == rb.tc[i]:
                        assert A[f"s_{r}"][j] == sc[i], (s, tf, r, i)
                        n_closing += 1
                    else:
                        n_none += 1
                complete_none = int(np.sum(~np.isin(rb.tc, ch.tc) & rb.complete))
                if s == "XAUUSDm" and tf == "1H":
                    assert complete_none == 45                              # the 45 complete weeks' Friday bars
                else:
                    assert complete_none == 0, (s, tf, r)
                assert n_none == complete_none + int(not rb.complete[-1])   # and the last week, still forming
                if (s, tf, r) == ("XAUUSDm", "1H", "1W"):
                    assert n_closing == 0                                   # no 1H bar closes with a gold week
                else:
                    assert n_closing > 30, (s, tf, r)
    with pytest.raises(ValueError):
        R.closed_score(ctxs["XAUUSDm"], "M15")


def recount_claim14(ctx, windows):
    """Claim 14 counted again by loops, from the port and the bars only, per window (start, end): {(chart, row): (closes
    that differ, closes, row bars with a change, row bars)} over the chart closes strictly inside a complete row bar,
    chart bar and row bar inside the window, where model B's score is set against the score the row bar ends with
    (its row_values and the swing vote at its own close); {chart: (closes where model B's label differs from model
    A's, closes, those where MSD-A1's side differs, closes)} over the chart closes in the window strictly inside a bar
    of a higher row."""
    tick = MS.MINTICK[ctx.symbol]
    end = ctx.mk.end_s
    side = (lambda x: 1 if x >= 1 else (-1 if x <= -1 else 0))
    out = {w: ({}, {}) for w in windows}
    for tf in R.TFS:
        bars = {r: ctx.bars(r) for r in ROWS_OF[tf]}
        A = MS.structure_dashboard(bars, tf, "A")
        B = MS.structure_dashboard(bars, tf, "B")
        ch = bars[tf]
        inside_any = np.zeros(len(ch.t), bool)
        found = {}
        for r in ROWS_OF[tf][1:]:
            rb = bars[r]
            rv = MS.row_values(rb)
            closed = [int(rv["struct"][i]) + int(rv["ob"][i]) + int(rv["fvg"][i]) +
                      int(MS.swing_factor([rb.c[i]], [rv["swing_h"][i]], [rv["swing_l"][i]], tick)[0])
                      for i in range(len(rb.t))]
            pairs, i = [], -1
            for j in range(len(ch.t)):
                while i + 1 < len(rb.t) and rb.t[i + 1] <= ch.t[j]:
                    i += 1
                if i >= 0 and ch.tc[j] < rb.tc[i]:                       # strictly inside: it closes before the row bar
                    inside_any[j] = True
                    pairs.append((j, i, int(B[f"s_{r}"][j]) != closed[i]))
            found[r] = (pairs, rb)
        for w, (a, z) in windows.items():
            a, z = TM.s_of(a), TM.s_of(z)
            for r, (pairs, rb) in found.items():
                kept = [(j, i, d) for j, i, d in pairs
                        if a <= ch.t[j] and ch.tc[j] <= z and a <= rb.t[i] and rb.tc[i] <= z and rb.tc[i] <= end]
                out[w][0][(tf, r)] = (sum(d for _, _, d in kept), len(kept), len({i for _, i, d in kept if d}),
                                      len({i for _, i, _ in kept}))
            js = [j for j in range(len(ch.t)) if inside_any[j] and a <= ch.t[j] and ch.tc[j] <= z]
            kd = sum(int(A["label"][j] != B["label"][j]) for j in js)
            ks = sum(int(side(A["label"][j]) != side(B["label"][j])) for j in js)
            out[w][1][tf] = (kd, len(js), ks, len(js))
    return out


def test_claim14_counts_equal_a_recount_by_loops(claim_ctxs, claim_windows):
    ctxs, _ = claim_ctxs
    got = R.claim14(FakeEv(ctxs))
    assert [g["symbol"] for g in got] == ["XAUUSDm"] * 9 + ["BTCUSDm"] * 9      # 6 rows and 3 charts per symbol
    for g in got:
        assert set(g) == {"part", "symbol", "rows", "dev", "val", "dev_ok", "val_ok", "note"}
    differ = 0
    for s, ctx in ctxs.items():
        mine = iter([g for g in got if g["symbol"] == s])
        want = recount_claim14(ctx, {w: M.window_span(w, s) for w in ("dev", "val")})
        for tf in R.TFS:
            for r in ROWS_OF[tf][1:]:
                g = next(mine)
                assert g["part"].startswith(f"{tf} chart, {WORD[r]} row: ")
                for w in ("dev", "val"):
                    d, n, bd, bn = want[w][0][(tf, r)]
                    assert fracs(g[w]) == (d, n, bd, bn), (s, tf, r, w)
                    assert g[f"{w}_ok"] is (n > 0 and d > 0)                     # the verdict line: a share above 0
                    assert n > 0
                    differ += d
            g = next(mine)
            assert g["part"].startswith(f"{tf} chart: the label")
            for w in ("dev", "val"):
                assert fracs(g[w]) == want[w][1][tf], (s, tf, w)
                assert np.isnan(g[f"{w}_ok"])                                    # information
    assert differ > 1000                                                         # the case is not empty


def test_claim14_reads_nothing_after_a_windows_end(claim_ctxs, claim_windows):
    """A window's counts are unchanged when the M1 data after its end is removed. No chart close and no score a row
    bar closes with comes from after the window. A week that the window's end cuts is forming in the cut data and
    closes after the window in the full data, so it is counted in neither."""
    ctxs, m1 = claim_ctxs
    full = R.claim14(FakeEv(ctxs))
    for s, x in m1.items():
        z = TM.s_of(M.window_span("dev", s)[1])
        keep = x["t"] < z
        cctx = M.Context(M.TMarket2(s, {k: v[keep] for k, v in x.items()}))
        assert cctx.mk.end_s == z and not cctx.bars("1W").complete[-1]
        got = R.claim14(FakeEv({s: cctx}))
        mine = [g for g in full if g["symbol"] == s]
        assert [g["dev"] for g in got] == [g["dev"] for g in mine]
        assert [g["dev_ok"] for g in got if isinstance(g["dev_ok"], bool)] == \
               [g["dev_ok"] for g in mine if isinstance(g["dev_ok"], bool)]
        assert all(fracs(g["val"])[1] == 0 for g in got)                        # nothing left in 'val'


def zero_dashboard(ctx, tf, model="A"):
    """A dashboard whose rows all score 0 and whose label is NEUTRAL (claim 14 reads ``s_<row>`` and ``label``)."""
    n = len(ctx.bars(tf))
    return {"label": np.zeros(n, np.int8), **{f"s_{r}": np.zeros(n, np.int64) for r in R.ROWS[tf]}}


def test_claim14_a_row_that_never_changes_does_not_hold_and_one_change_holds(claim_ctxs, claim_windows, monkeypatch):
    """The verdict line, fixed before any count existed: a share of 0 does not hold, and one differing close in a window
    holds there. Hand-made: every forming score equals the closed one (all 0), except at one 1D close inside a
    Validation week."""
    ctxs, _ = claim_ctxs
    ctx = ctxs["BTCUSDm"]
    ch, wk = ctx.bars("1D"), ctx.bars("1W")
    k = R.forming_bar(ch, wk)
    va, vz = (TM.s_of(x) for x in M.window_span("val", "BTCUSDm"))
    j_star = next(j for j in range(len(ch.t)) if k[j] >= 0 and va <= wk.t[k[j]] and wk.tc[k[j]] <= vz)
    assert ch.t[j_star] == wk.t[k[j_star]]                     # the week's first day: not its last chart bar

    def fake(c, tf, model="A"):
        d = zero_dashboard(c, tf, model)
        if model == "B" and tf == "1D":
            d["s_1W"][j_star] = 1
        return d
    monkeypatch.setattr(R, "dashboard", fake)
    monkeypatch.setattr(R, "closed_score", lambda c, r: np.zeros(len(c.bars(r)), np.int64))
    got = R.claim14(FakeEv({"BTCUSDm": ctx}))
    oks = [(g["part"].split(":")[0], g["dev_ok"], g["val_ok"]) for g in got if "(information)" not in g["part"]]
    assert oks == [("1H chart, 4H row", False, False), ("1H chart, D row", False, False),
                   ("1H chart, W row", False, False), ("4H chart, D row", False, False),
                   ("4H chart, W row", False, False), ("1D chart, W row", False, True)]
    w = next(g for g in got if g["part"].startswith("1D chart, W row"))
    assert fracs(w["val"])[:1] == (1,) and fracs(w["val"])[2:3] == (1,) and fracs(w["dev"])[0] == 0
    # the check before counting: a last chart bar whose forming score is not the closed one stops the claim (here
    # the last day of j_star's week, which closes with it)
    i = int(k[j_star])
    j_last = int(np.flatnonzero((ch.t >= wk.t[i]) & (ch.tc <= wk.tc[i]))[-1])
    assert ch.tc[j_last] == wk.tc[i] and k[j_last] == -1

    def broken(c, tf, model="A"):
        d = zero_dashboard(c, tf, model)
        if model == "B" and tf == "1D":
            d["s_1W"][j_last] = 1
        return d
    monkeypatch.setattr(R, "dashboard", broken)
    with pytest.raises(AssertionError):
        R.claim14(FakeEv({"BTCUSDm": ctx}))


def test_claim14_through_the_drivers_claims_table(claim_ctxs, claim_windows, tmp_path):
    """The driver finds claim14 (EXTRAS), checks its rows against the evidence's windows (CLAIM_RULE) and gives study
    1's verdict words: holds / does not hold / mixed from the two windows, 'information' for the label rows."""
    try:
        T2 = importlib.import_module("backtesting.research.tradeiq2")
    except Exception as e:  # noqa: BLE001 - the driver is not this module's; without it there is nothing to check
        pytest.skip(f"the study driver does not import here: {e!r}")
    ctxs, _ = claim_ctxs
    syms = list(ctxs)
    res = pd.DataFrame({"vid": [f"{s}|1H|X" for s in syms for _ in (0, 1)], "window": ["dev", "val"] * len(syms),
                        "symbol": [s for s in syms for _ in (0, 1)]})
    grid = pd.DataFrame({"vid": [f"{s}|1H|X" for s in syms], "params": ["{}"] * len(syms)})
    ev = T2.Evidence(tmp_path, res, grid, pd.DataFrame(), {"msd": R}, loader=lambda s, end: ctxs[s].mk)
    assert T2.extra({"msd": R}, "claim14") is R.claim14
    table, errors = T2.claims_table(ev, numbers=[14])
    assert errors == [] and len(table) == 18 and set(table.claim) == {14}
    info = table.part.str.endswith("(information)")
    assert int(info.sum()) == 6 and (table.verdict[info] == "information").all()
    for _, r in table[~info].iterrows():
        assert r.verdict == T1.verdict(bool(r.dev_ok), bool(r.val_ok))
    assert set(table.verdict[~info]) <= {"holds", "does not hold", "mixed"}
