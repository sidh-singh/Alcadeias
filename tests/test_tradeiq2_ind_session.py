"""
Session Hunter [TradeIQ] (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` 6.6): the reconciliation of its two
independent ports.

Port A, ``backtesting/research/tradeiq2_ind_session.py`` (the production port: numpy and numba), and port B,
``tests/tradeiq2_oracle_session.py`` (a plain-Python, statement-by-statement transcription), were written
independently from the Pine source. PREREG 5 ("Ports"): the two must agree bit for bit on the real bars of both
symbols, on every series a rule reads, before any rule runs. This file checks that they do. NO TOLERANCE IS USED
ANYWHERE: the same integers, booleans and strings, and every float bit for bit (``bits_equal``: NaN in the same
places, every other value and the sign of every zero equal). Both ports follow the source's order of arithmetic and
study 1's verified order for ``ta.sma`` / ``ta.rma`` / ``ta.ema``, so no float needed a tolerance.

1. THE REAL BARS (skipped when the tick store is absent), one symbol at a time: gold and BTC, M5 and M15 (the
   timeframes of PREREG 6.6), from the symbol's data start (gold 2016-01-03, BTC 2018-01-01) to 2024-06-30 23:59 UTC,
   exactly as the study loads them: ``tradeiq2_market.load(symbol, end="2024-07-01")`` with both studies' hold-out
   guards pointed at empty folders, the chart bars ``mk.tbars('M5' | 'M15')`` with their tick volume, and the market's
   own 1H bars for the EMA200. Compared:

   * the 1H EMA200 at each chart bar's open (``htf_ema``, both seeds) and its direction (``htf_ema_dir``);
   * every per-bar series the setups read: the New York clock (minute, day key, weekday, new day, the sessions'
     membership, closeT), ATR(14), the volume SMA, the FVG flags, hi5 / lo5, the day state (yesterday's high, low,
     open and close, pWk, the day's weekday flag, the midnight open, the ADR), the three sessions' levels and done
     flags, and each setup's signal per bar; and the same under reading R1's alternative (port B's
     ``first_bar_new_day=True``), which leaves every one of them unchanged on these bars;
   * the event tables of every configuration the plan runs: K0, K1, K2 and K3 with all five setups (the three presets
     are subsets of these rows and every setup is its own lane: checked on port A), K2 with the Monday variant, and K2
     with the 1H EMA replaced by F2-4H, F2-1D and F3 (the study's own ``tradeiq2_filters``); beyond the grid, 'RV' on
     the study's volume (gold: ticks; BTC: Binance BTCUSDT 5m klines) and all seven confirmations at once.

   An event table holds, per signal: setup, bar, signal time, direction, stop, target reference, range, entry bar, the
   cancel at entry, and the script's own exits in its three exit modes (exit bar, price, reason, R). THE EXIT COLUMNS
   ARE COMPARED FOR EQUALITY ONLY: no value of them is printed, counted, summed or otherwise looked at (PREREG: no
   profit or loss of any rule of this study on real data). A failing assertion names the configuration, the column
   and the number of rows that differ, never a value.
2. Random charts (port A's tests' generator, with edits that force the rare branches: the four cancels at entry and a
   new-day exit) and every confirmation set: the branches the real bars barely reach (under K2 no entry is cancelled
   on them).
3. The claim markets of PREREG 8, claim 10 (information only; skipped when absent): the Nasdaq preset and PD + HTF on
   USTECm M5 and M15, the Forex preset on EURUSDm and GBPUSDm M15, from their data start to 2024-06-30.
4. The contract: the same names, constants, columns, dtypes, defaults and refused inputs in both ports.

What was found and decided: ``backtest_results/tradeiq_2027/porting/session.md``. Memory: one market at a time (a
maximum resident size of about 1.7 GB, port B on BTC M5). Time: about three and a half minutes, nearly all of it port
B's plain-Python bar loop.
"""

from __future__ import annotations

import gc
import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_session as A
from backtesting.research import tradeiq2_market as M2
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_session as B  # noqa: E402
import test_tradeiq2_ind_session_a as TA  # noqa: E402   (port A's tests: the random-chart generator only)

SYMBOLS = ("XAUUSDm", "BTCUSDm")
TFS = (("M5", 5), ("M15", 15))
K2 = ("FVG", "HTF")
ALT_HTF = ("F2-4H", "F2-1D", "F3")                     # PREREG 6.6: K2 x E1 with the 1H EMA200 replaced
# the bars the study serves while its hold-out is closed (DATA.md, "What the code serves"), when gold's 2016 is loaded
DATA_MD_BARS = {("XAUUSDm", "M5"): 596_786, ("XAUUSDm", "M15"): 199_192, ("BTCUSDm", "M5"): 681_121,
                ("BTCUSDm", "M15"): 227_123}


# ───────────────────────────── comparison helpers (they never show a value) ─────────────────────────────

def _float_mismatch(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per element: True where x and y differ as float64 bits (NaN payloads aside): one NaN and not the other, other
    values, or zeros of opposite signs."""
    nx, ny_ = np.isnan(x), np.isnan(y)
    with np.errstate(invalid="ignore"):
        same = (nx & ny_) | (~nx & ~ny_ & (x == y) & (np.signbit(x) == np.signbit(y)))
    return ~same


def bits_equal(x, y) -> bool:
    """Equal arrays of one dtype; floats bit for bit (NaN in the same places, values and the sign of zeros equal)."""
    x, y = np.asarray(x), np.asarray(y)
    if x.shape != y.shape or x.dtype != y.dtype:
        return False
    if x.dtype.kind == "f":
        return not bool(_float_mismatch(x, y).any())
    return bool(np.array_equal(x, y))


def n_diff(x, y) -> int:
    """How many elements differ (for an assertion message: a count, never a value)."""
    x, y = np.asarray(x), np.asarray(y)
    if x.shape != y.shape:
        return -1
    if x.dtype.kind == "f" or y.dtype.kind == "f":
        return int(_float_mismatch(x.astype(np.float64), y.astype(np.float64)).sum())
    return int((x != y).sum())


def assert_same_table(a: pd.DataFrame, b: pd.DataFrame, where: str) -> None:
    """The two ports' event tables are identical: the same columns in the same order, the same dtypes, the same rows;
    integers and labels equal, floats bit for bit."""
    assert list(a.columns) == list(A.COLUMNS) and list(b.columns) == list(A.COLUMNS), f"{where}: columns"
    assert len(a) == len(b), f"{where}: {len(a)} rows in port A, {len(b)} in port B"
    for col in A.COLUMNS:
        x, y = a[col].to_numpy(), b[col].to_numpy()
        assert x.dtype == y.dtype, f"{where}: dtype of {col}: {x.dtype} / {y.dtype}"
        if x.dtype == object:
            labels = all(p is None or isinstance(p, str) for p in x) and all(q is None or isinstance(q, str) for q in y)
            assert labels, f"{where}: {col} holds something else than labels and None"
            bad = sum(1 for p, q in zip(x, y) if p != q)
            assert bad == 0, f"{where}: column {col} differs on {bad} of {len(x)} rows"
        else:
            assert bits_equal(x, y), f"{where}: column {col} differs on {n_diff(x, y)} of {len(x)} rows"


def yyyymmdd(day_key) -> np.ndarray:
    """Port A's day key (an epoch day of New York's calendar) written as Pine's l.130 writes it (port B's)."""
    d = pd.to_datetime(np.asarray(day_key, np.int64) * 86400, unit="s")
    return d.year.to_numpy(np.int64) * 10000 + d.month.to_numpy(np.int64) * 100 + d.day.to_numpy(np.int64)


def signal_series(table: pd.DataFrame, setup: str, n: int) -> np.ndarray:
    """A setup's signal per bar (+1 / -1 / 0), from port A's event table."""
    s = np.zeros(n, np.int64)
    rows = table[table.setup == setup]
    s[rows.bar.to_numpy()] = rows.dir.to_numpy()
    return s


def run_both(b, tfm: int, hd, v=None, **kw):
    """Port A's and port B's event tables of one configuration (the same inputs, the same arrays)."""
    v = b.v if v is None else v
    a = A.session_hunter(b.t, b.o, b.h, b.l, b.c, v, tfm, hd, **kw)
    o = B.session_hunter(b.t, b.o, b.h, b.l, b.c, v, tfm, hd, **kw)
    return a, o


def assert_same_series(b, tfm: int, hd, where: str, conf=K2, mfl: bool = False, **b_kw):
    """Every per-bar series the setups read, port A's (``clock``, ``shared_series``, ``day_state``, the signals of its
    table) against port B's (``session_series``), and the two event tables of the same run. Returns port B's series
    and its table."""
    rows, s = B._run(b.t, b.o, b.h, b.l, b.c, b.v, tfm, hd, conf=conf, monday_friday_levels=mfl, want_series=True,
                     **b_kw)
    n = len(b.t)
    ck = A.clock(b.t, tfm)
    sh = A.shared_series(b.h, b.l, b.c, b.v)
    st = A.day_state(b.t, b.o, b.h, b.l, b.c, tfm, monday_friday_levels=mfl)
    table = A.session_hunter(b.t, b.o, b.h, b.l, b.c, b.v, tfm, hd, conf=conf, monday_friday_levels=mfl)
    pairs = {"ny_min": (ck["ny_min"], s["ny_min"]), "dk": (yyyymmdd(ck["day_key"]), s["dk"]),
             "weekday": (ck["weekday"], s["weekday"]), "new_day": (ck["new_day"], s["new_day"]),
             "in_asia": (ck["in_asia"], s["in_asia"]), "in_lon": (ck["in_lon"], s["in_lon"]),
             "in_or": (ck["in_or"], s["in_or"]), "close_t": (ck["close_t"], s["close_t"]),
             "atr": (sh["atr"], s["atr"]), "vavg": (sh["vavg"], s["vavg"]), "fvg_up": (sh["fvg_up"], s["fvg_up"]),
             "fvg_dn": (sh["fvg_dn"], s["fvg_dn"]), "hi5": (sh["hi5"], s["hi5"]), "lo5": (sh["lo5"], s["lo5"]),
             "pdh": (st.pdh, s["pdh"]), "pdl": (st.pdl, s["pdl"]), "p_open": (st.p_open, s["p_o"]),
             "p_close": (st.p_close, s["p_c"]), "p_wk": (st.p_wk, s["p_wk"]), "d_wk": (st.d_wk, s["d_wk"]),
             "mo": (st.mo, s["mo"]), "adr": (st.adr, s["adr"]), "asia_hi": (st.asia_hi, s["as_h"]),
             "asia_lo": (st.asia_lo, s["as_l"]), "lon_hi": (st.lon_hi, s["lo_h"]), "lon_lo": (st.lon_lo, s["lo_l"]),
             "or_hi": (st.or_hi, s["o_h"]), "or_lo": (st.or_lo, s["o_l"]), "asia_done": (st.asia_done, s["as_done"]),
             "lon_done": (st.lon_done, s["lo_done"]), "or_done": (st.or_done, s["o_done"])}
    for code in A.SETUPS:
        pairs[f"signal {code}"] = (signal_series(table, code, n), s[f"s_{code}"])
    for name, (x, y) in pairs.items():
        x, y = np.asarray(x), np.asarray(y)
        assert bits_equal(x, y), f"{where}: per-bar {name} differs on {n_diff(x, y)} of {n} bars"
    frame = B._frame(rows)
    assert_same_table(table, frame, where)
    return s, frame


# ───────────────────────────── 1. the real bars (to 2024-06-30, both guards closed) ─────────────────────────────

def _available(symbol: str) -> bool:
    months = store.available_months(symbol)
    start = M2.data_start(symbol)
    return (2024, 6) in months and (int(start[:4]), int(start[5:7])) in months


def _load(symbol: str, tfs, tmp_path_factory, alt: bool):
    """The study's bars of ``symbol``: the chart bars of ``tfs`` (with their tick volume, the study's volume for 'RV'
    and, if ``alt``, the F2-4H / F2-1D / F3 directions) and the 1H bars of the EMA. The M1 market is dropped once the
    bars are built, so one market at a time is in memory."""
    d1, d2 = tmp_path_factory.mktemp("closed_study1"), tmp_path_factory.mktemp("closed_study2")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(TM, "STUDY_DIR", d1)                    # study 1's guard: no FINALISTS.md, closed
        mp.setattr(M2, "STUDY_DIR", d2)                    # study 2's guard: closed
        mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
        mk = M2.load(symbol, end="2024-07-01")
        assert mk.end_s == M2.CUT_S and int(mk.t[-1]) + 60 <= M2.CUT_S          # nothing from the hold-out
        ctx = M2.Context(mk)
        h1b = mk.tbars("1H")
        h1 = NS(t=h1b.t.copy(), tc=h1b.tc.copy(), c=h1b.c.copy())
        charts = {}
        for tf, tfm in tfs:
            b = mk.tbars(tf)
            ch = NS(tf=tf, tfm=tfm, t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(),
                    c=b.c.copy(), v=b.vol.astype(np.float64), alt={}, study_v=None)
            if alt:
                for f in ALT_HTF:
                    al, ash = ctx.allow(tf, f)
                    ch.alt[f] = al.astype(np.int64) - ash.astype(np.int64)
                try:
                    ch.study_v = np.array(ctx.volume(tf), np.float64)           # PREREG 2: gold ticks, BTC Binance
                except OSError:                                                 # the Binance files are absent
                    ch.study_v = None
            charts[tf] = ch
        first = pd.Timestamp(int(mk.t[0]), unit="s", tz="UTC")
        del mk, ctx, h1b, b
    gc.collect()
    return NS(symbol=symbol, h1=h1, charts=charts, first=first)


@pytest.fixture(scope="module", params=SYMBOLS)
def real(request, tmp_path_factory):
    """One symbol's study bars (M5, M15, 1H); pytest runs every test of one symbol before it loads the next."""
    if not _available(request.param):
        pytest.skip(f"the tick store of {request.param} is not on this machine")
    data = _load(request.param, TFS, tmp_path_factory, alt=True)
    for ch in data.charts.values():
        ch.hd = A.htf_ema_dir(ch.t, ch.c, data.h1)             # the script's own 1H trend (both ports read it)
    yield data
    data.charts.clear()
    gc.collect()


def test_real_bars_are_the_studys(real):
    """The bars compared are the study's: from the data start to the hold-out start, nothing after it; the 1H bars'
    close times are their nominal ends, so "the last 1H bar with tc <= the chart bar's open" is exactly the bar
    before the one that contains it (request.security's ``[1]`` with ``lookahead_on``)."""
    assert int(real.h1.tc[-1]) <= M2.CUT_S and np.array_equal(real.h1.tc, real.h1.t + 3600)
    start = M2.data_start(real.symbol)
    assert real.first.strftime("%Y-%m-%d") <= {"XAUUSDm": "2016-01-04", "BTCUSDm": "2018-01-01"}[real.symbol]
    for tf, ch in real.charts.items():
        assert int(ch.tc[-1]) <= M2.CUT_S and np.array_equal(ch.tc, ch.t + 60 * ch.tfm)
        if start == {"XAUUSDm": M2.GOLD_EARLY_START, "BTCUSDm": M2.DATA_START["BTCUSDm"]}[real.symbol]:
            assert len(ch.t) == DATA_MD_BARS[(real.symbol, tf)], tf
        # the first bar opens on a weekend pseudo-day of the script's clock (reading R1 cannot matter, see below)
        ck = A.clock(ch.t[:1], ch.tfm)
        assert not ck["weekday"][0], tf


def test_real_htf_ema_both_seeds_and_direction(real):
    """l.145: htfE per chart bar bit for bit in both ports, with either ``ta.ema`` seed; its direction identical. From
    2019 the two seeds give the same htfE bit for bit (reading R2 cannot move a result), and the direction is never
    0 (warmed up)."""
    for tf, ch in real.charts.items():
        ea, eb = A.htf_ema(ch.t, real.h1), B.htf_ema(ch.t, real.h1)
        assert bits_equal(ea, eb), f"{tf}: htfE differs on {n_diff(ea, eb)} bars"
        sa, sb = A.htf_ema(ch.t, real.h1, seed="sma"), B.htf_ema(ch.t, real.h1, seed="sma")
        assert bits_equal(sa, sb), f"{tf}: htfE (SMA seed) differs on {n_diff(sa, sb)} bars"
        dev = ch.t >= TM.s_of("2019-01-01")
        assert bits_equal(ea[dev], sa[dev]) and np.isfinite(ea[dev]).all(), tf
        da, db = A.htf_ema_dir(ch.t, ch.c, real.h1), B.htf_ema_dir(ch.t, ch.c, real.h1)
        assert bits_equal(da, db) and da.dtype == np.int8, f"{tf}: direction differs on {n_diff(da, db)} bars"
        assert (da[dev] != 0).all() and set(np.unique(da)) <= {-1, 0, 1}, tf


def test_real_per_bar_series_and_k2(real):
    """Every per-bar series the setups read, and the K2 event table (the script's default), in both ports; then
    reading R1's alternative in port B (newDay true on bar 0) changes no series a setup reads and no row."""
    for tf, ch in real.charts.items():
        where = f"{real.symbol} {tf} K2"
        s, frame = assert_same_series(ch, ch.tfm, ch.hd, where)
        assert len(frame) > 1000 and set(frame.setup) == set(A.SETUPS) and set(frame.dir) == {-1, 1}, where
        rows_t, s_t = B._run(ch.t, ch.o, ch.h, ch.l, ch.c, ch.v, ch.tfm, ch.hd, conf=K2, want_series=True,
                             first_bar_new_day=True)
        assert np.flatnonzero(s_t["new_day"] != s["new_day"]).tolist() == [0], where
        day1 = int(np.flatnonzero(s["new_day"])[0])                    # the first day ends here
        for key in s:
            if key in ("new_day", "d_h", "d_l", "d_o"):
                if key != "new_day":
                    assert bits_equal(s_t[key][day1:], s[key][day1:]), f"{where} R1: {key} after the first day"
                continue
            assert bits_equal(s_t[key], s[key]), f"{where} R1: {key} differs on {n_diff(s_t[key], s[key])} bars"
        assert_same_table(B._frame(rows_t), frame, f"{where} R1 alternative")


REAL_CONFIGS = {
    "K0": dict(conf=()),
    "K1": dict(conf=("FVG",)),
    "K3": dict(conf=("FVG", "MSS")),
    "K2 Monday variant": dict(conf=K2, monday_friday_levels=True),
    "K2 F2-4H": dict(conf=K2, htf="F2-4H"),
    "K2 F2-1D": dict(conf=K2, htf="F2-1D"),
    "K2 F3": dict(conf=K2, htf="F3"),
    "RV (study volume)": dict(conf=("RV",), volume="study"),
    "all seven": dict(conf=A.CONFS),
}


@pytest.mark.parametrize("name", list(REAL_CONFIGS))
def test_real_event_tables(real, name):
    """The event tables of the plan's configurations (and two beyond it) in both ports, bit for bit."""
    kw = dict(REAL_CONFIGS[name])
    htf, volume = kw.pop("htf", None), kw.pop("volume", None)
    for tf, ch in real.charts.items():
        hd = ch.hd if htf is None else ch.alt[htf]
        v = ch.v
        if volume == "study":
            if ch.study_v is None:
                pytest.skip("the Binance 5m klines are not on this machine")
            v = ch.study_v
        a, o = run_both(ch, ch.tfm, hd, v=v, **kw)
        where = f"{real.symbol} {tf} {name}"
        assert_same_table(a, o, where)
        assert len(a) > 0, where


def test_real_presets_are_subsets_and_lanes_are_independent(real):
    """Port A on the real bars (port B's lanes are pinned by its own tests): each preset's rows are the rows of its
    setups in the run with all five, and each setup alone gives its rows of that run."""
    for tf, ch in real.charts.items():
        full = {c: A.session_hunter(ch.t, ch.o, ch.h, ch.l, ch.c, ch.v, ch.tfm, ch.hd, conf=c)
                for c in (K2, ("FVG", "MSS"))}
        for name, (setups, conf) in A.PRESETS.items():
            sub = A.session_hunter(ch.t, ch.o, ch.h, ch.l, ch.c, ch.v, ch.tfm, ch.hd, setups=setups, conf=conf)
            ref = full[conf][full[conf].setup.isin(setups)].reset_index(drop=True)
            assert_same_table(sub, ref, f"{real.symbol} {tf} preset {name}")
        for code in A.SETUPS:
            alone = A.session_hunter(ch.t, ch.o, ch.h, ch.l, ch.c, ch.v, ch.tfm, ch.hd, setups=(code,), conf=K2)
            ref = full[K2][full[K2].setup == code].reset_index(drop=True)
            assert_same_table(alone, ref, f"{real.symbol} {tf} {code} alone")


# ───────────────────────────── 2. random charts with the rare branches forced ─────────────────────────────

@pytest.mark.parametrize("key", TA.CHARTS, ids=[f"seed{k[0]}_{k[1]}m_{'gold' if k[2] else 'btc'}" for k in TA.CHARTS])
def test_random_charts_both_ports(key):
    """Port A's tests' random charts (gold's and BTC's schedules, M5 / M15 / 1H, both 2019 daylight-saving changes,
    holes, opening gaps, prices on a 0.05 grid for ties, a random direction series with zeros) with the edits that
    force each cancel at entry and a new-day exit: every confirmation set of port A's tests, the Monday variant, a
    minimum stop of 1.25 ATR and a subset of setups, and the per-bar series."""
    seed, tf, gold, start = key
    t, o, h, lo, c, v, hd = TA.with_branches(TA.random_bars(seed, tf=tf, gold=gold, start=start,
                                                             days=35 if tf == 5 else 49), tf)
    ch = NS(t=t, o=o, h=h, l=lo, c=c, v=v)
    seen = {"cancelled": set(), "why": set()}
    for conf in TA.CONF_SETS:
        a, b = run_both(ch, tf, hd, conf=conf)
        assert_same_table(a, b, f"random {key} conf={conf}")
        seen["cancelled"] |= set(a.cancelled.dropna())
        for m in A.MODES:
            seen["why"] |= set(a[f"exit_reason_{m}"].dropna())
    for kw in (dict(conf=("FVG",), monday_friday_levels=True), dict(conf=("YC",), monday_friday_levels=True),
               dict(conf=("FVG",), min_stop_atr=1.25), dict(setups=("LS", "OR"), conf=())):
        a, b = run_both(ch, tf, hd, **kw)
        assert_same_table(a, b, f"random {key} {kw}")
    for mfl in (False, True):
        assert_same_series(ch, tf, hd, f"random {key} series mfl={mfl}", conf=(), mfl=mfl)
    assert seen["cancelled"] and {"stop", "target", "closeT", "new_day", "cancel_lt_1R"} <= seen["why"], seen


def test_random_charts_reach_every_cancel():
    """Over the four random charts the comparison above went through all four cancels at entry."""
    got = set()
    for seed, tf, gold, start in TA.CHARTS:
        t, o, h, lo, c, v, hd = TA.with_branches(TA.random_bars(seed, tf=tf, gold=gold, start=start,
                                                                 days=35 if tf == 5 else 49), tf)
        got |= set(A.session_hunter(t, o, h, lo, c, v, tf, hd, conf=()).cancelled.dropna())
    assert got == set(A.CANCELS) == set(B.CANCELS)


# ───────────────────────────── 3. the claim markets (PREREG 8, claim 10; information only) ─────────────────────────

CLAIMS = {"USTECm": TFS, "EURUSDm": (("M15", 15),), "GBPUSDm": (("M15", 15),)}
CLAIM_ROWS = {
    "USTECm": (("Nasdaq preset", dict(setups=("LS", "PD"), conf=K2)),
               ("PD + HTF", dict(setups=("PD",), conf=("HTF",)))),
    "EURUSDm": (("Forex preset", dict(setups=("AS",), conf=("FVG", "MSS"))),),
    "GBPUSDm": (("Forex preset", dict(setups=("AS",), conf=("FVG", "MSS"))),),
}


@pytest.fixture(scope="module", params=tuple(CLAIMS))
def claim(request, tmp_path_factory):
    if not _available(request.param):
        pytest.skip(f"the tick store of {request.param} is not on this machine")
    data = _load(request.param, CLAIMS[request.param], tmp_path_factory, alt=False)
    for ch in data.charts.values():
        ch.hd = A.htf_ema_dir(ch.t, ch.c, data.h1)
    yield data
    data.charts.clear()
    gc.collect()


def test_claim_markets(claim):
    """Claim 10's rows on the claim markets: the event tables in both ports, and every per-bar series."""
    for tf, ch in claim.charts.items():
        assert int(ch.tc[-1]) <= M2.CUT_S
        ea, eb = A.htf_ema(ch.t, claim.h1), B.htf_ema(ch.t, claim.h1)
        assert bits_equal(ea, eb), f"{claim.symbol} {tf}: htfE"
        assert_same_series(ch, ch.tfm, ch.hd, f"{claim.symbol} {tf} series", conf=())
        for label, kw in CLAIM_ROWS[claim.symbol]:
            a, b = run_both(ch, ch.tfm, ch.hd, **kw)
            assert_same_table(a, b, f"{claim.symbol} {tf} {label}")
            assert len(a) > 0, (claim.symbol, tf, label)


# ───────────────────────────── 4. the contract ─────────────────────────────

def _chart():
    t, o, h, lo, c, v, hd = TA.random_bars(11, tf=15, gold=True, start="2019-02-24 17:00", days=20)
    return t, o, h, lo, c, v, hd


def test_the_contract_is_the_same_in_both_ports():
    assert A.SETUPS == B.SETUPS and A.CONFS == B.CONFIRMATIONS and A.MODES == B.MODES
    assert A.CANCELS == B.CANCELS and A.EXIT_REASONS == B.EXIT_REASONS and list(A.COLUMNS) == list(B.COLUMNS)
    assert set(B.EXITS) | {B.OPEN, B.PENDING, B.LIQ_CANCEL} == set(A.EXIT_REASONS)
    for fa, fb in ((A.session_hunter, B.session_hunter), (A.htf_ema, B.htf_ema), (A.htf_ema_dir, B.htf_ema_dir)):
        pa, pb = inspect.signature(fa).parameters, inspect.signature(fb).parameters
        assert list(pa) == list(pb), fa.__name__
        assert [p.default for p in pa.values()] == [p.default for p in pb.values()], fa.__name__
    t, o, h, lo, c, v, hd = _chart()
    a, b = A.session_hunter(t, o, h, lo, c, v, 15, hd, conf=()), B.session_hunter(t, o, h, lo, c, v, 15, hd, conf=())
    assert len(a) > 10 and {k: str(a[k].dtype) for k in a} == {k: str(b[k].dtype) for k in b}
    assert_same_table(a, b, "defaults")
    # inputs that are optional unless read
    a, b = (P.session_hunter(t, o, h, lo, c, None, 15, None, conf=("FVG",)) for P in (A, B))
    assert_same_table(a, b, "v and htf_dir None")
    # empty input
    z = np.zeros(0)
    ea, eb = (P.session_hunter(np.zeros(0, np.int64), z, z, z, z, z, 5, z) for P in (A, B))
    assert ea.empty and eb.empty and {k: str(ea[k].dtype) for k in ea} == {k: str(eb[k].dtype) for k in eb}


@pytest.mark.parametrize("bad", ["reversed times", "short o", "nan price", "setup XX", "conf XX", "conf string",
                                 "setups string", "tf 0", "tf 2.5", "min stop 0", "min stop nan", "RV without v",
                                 "HTF without direction"])
def test_both_ports_refuse_the_same_inputs(bad):
    t, o, h, lo, c, v, hd = _chart()
    args = dict(t=t, o=o, h=h, l=lo, c=c, v=v, tf_min=15, htf_dir=hd)
    kw = {}
    if bad == "reversed times":
        args["t"] = t[::-1].copy()
    elif bad == "short o":
        args["o"] = o[:-1]
    elif bad == "nan price":
        args["c"] = np.where(np.arange(len(c)) == 5, np.nan, c)
    elif bad == "setup XX":
        kw["setups"] = ("AS", "XX")
    elif bad == "conf XX":
        kw["conf"] = ("FVG", "EMA")
    elif bad == "conf string":
        kw["conf"] = "FVG"
    elif bad == "setups string":
        kw["setups"] = "AS"
    elif bad == "tf 0":
        args["tf_min"] = 0
    elif bad == "tf 2.5":
        args["tf_min"] = 2.5
    elif bad == "min stop 0":
        kw["min_stop_atr"] = 0.0
    elif bad == "min stop nan":
        kw["min_stop_atr"] = math.nan
    elif bad == "RV without v":
        args["v"], kw["conf"] = None, ("RV",)
    elif bad == "HTF without direction":
        args["htf_dir"], kw["conf"] = None, ("FVG", "HTF")
    for P in (A, B):
        with pytest.raises(ValueError):
            P.session_hunter(*args.values(), **kw)
