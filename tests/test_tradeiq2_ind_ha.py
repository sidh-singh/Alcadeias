"""
LunqFX's "Heikin Ashi Candles, Trend Strength & Trend Age Stats" (study 2, ``backtest_results/tradeiq_2027/PREREG.md``
section 6.8, with claims 3-5 of section 8; study 3's HA filter rows and Turtle exits read the same series): the
reconciliation of its two independent ports. The notes for readers are ``backtest_results/tradeiq_2027/porting/ha.md``.

* Port A, ``backtesting/research/tradeiq2_ind_ha.py``: the production port (numpy and numba); its own tests are
  ``test_tradeiq2_ind_ha_a.py``.
* Port B, ``tests/tradeiq2_oracle_ha.py``: the oracle, a bar-by-bar transcription in plain Python; its own tests are
  ``test_tradeiq2_ind_ha_b.py``.

1. Real bars (skipped when the tick store is absent). XAUUSDm and BTCUSDm, 1H / 4H / 1D: the timeframes of PREREG 6.8
   (Heikin Ashi runs on its base's timeframe, and every base, study 1's finalists and the ribbon rows, is on 1H, 4H or
   1D) and of study 3's HA rows. From the study's data start (``tradeiq2_market.data_start``: gold 2016-01-01 when all
   twelve 2016 months are in the store, so its first bar is 2016-01-03; BTC 2018-01-01) to 2024-06-30: the M1 bars
   come from ``external.load_market(symbol, earliest=..., end="2024-07-01")``, so nothing at or after the hold-out
   start is read, and study 1's ``TMarket.tbars`` builds them into bars (what ``tradeiq2_market.load`` serves on 1H /
   4H / 1D), with study 1's and study 2's guards pointed at an empty folder. Gold is also run from 2017-01-03 (study
   1's start; those bars are a suffix of the same bars), because the trend-age statistics depend on where the bars
   start. Asserted:
   - every key of the contract, in the same order and dtype: floats bit for bit (the same bit patterns, NaN on the
     same bars), int8 / int32 / bool exactly; the frame of finished streaks identical (columns, dtypes, values).
     No tolerance anywhere, and no arithmetic had to be aligned: both ports already follow the script's order of
     operations (``haC = (open + high + low + close) / 4.0`` summed left to right, ``haO = (haO[1] + haC[1]) / 2.0``,
     each threshold as the input times the range, ``pctBelow = (100.0 * c) / n``);
   - the event table (flips, first STRONG candles, INDECISION after a STRONG run, the second WEAK candle in a row,
     rare ages: bar, open and close time, colour, age, runs, percentage) identical;
   - the Development counts (the harness's decision bars: closing after 2019-01-01 00:00, filled before 2023-01-01
     00:00) equal to the values recorded at the reconciliation, for both ports. Counts only: no rule is run and no
     profit or loss is computed;
   - both gold starts give the same candles, colours, phases, streaks and events on every Development bar; only the
     statistics (``pct_below``, ``rare_now``) differ, on the recorded number of bars;
   - the measured facts ``porting/ha.md`` quotes for the readings (port A; port B is identical on the contract);
   - the panel's helpers that claim 5 reads (the array held at a bar's close, ``survive``, SN / SK, ``pctBelow``)
     agree between the ports at the start of every year and at random bars.
2. The two mismatches the reconciliation found, by hand: the rare-age minimum of 50 finished streaks with a private
   cap below it (port B counted the capped array, port A every finished streak, as PREREG 6.8 words it; port B is
   aligned), and an infinite integer input (port B raised OverflowError instead of ValueError; fixed). Neither can
   change a value of the contract on any bars.
3. Synthetic bars: random walks (plain, rounded to whole units for exact ties, with flat runs for zero ranges), exact
   Heikin Ashi shapes (ties, zero ranges, dojis after STRONG runs, WEAK runs), random inputs inside the script's input
   ranges (l.20-28) and the plan's minimum, small private caps below and above the minimum, and series of 0 to 9
   bars: bit for bit. Bad bars and inputs are refused alike.

Line numbers l. are those of the plain-text copy of the script the study ported from (third-party code, cited,
never copied).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_ha as A
from backtesting.research import tradeiq2_market as TM2
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_ha as B  # noqa: E402

SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")                                     # PREREG 6.8 (the bases' timeframes)
ARRAY_KEYS = A.KEYS[:-1]                                     # every key but "streaks"
DTYPES = {"ha_o": np.float64, "ha_h": np.float64, "ha_l": np.float64, "ha_c": np.float64, "dir": np.int8,
          "phase": np.int8, "flip": np.bool_, "age": np.int32, "strong_run": np.int32, "weak_run": np.int32,
          "ev_ind": np.bool_, "ev_first_strong": np.bool_, "pct_below": np.float64, "rare_now": np.bool_}
STREAK_DTYPES = {"start_bar": np.int64, "end_bar": np.int64, "dir": np.int8, "length": np.int32,
                 "had_strong": np.bool_, "strong_at": np.int32, "ran_5_after_strong": np.bool_}
DEV = ("2019-01-01", "2023-01-01")                           # PREREG 3: Development
VAL_START = "2023-01-01"                                     # Validation: bars closing after it (to 2024-06-30)
STUDY1_GOLD_START = "2017-01-01"                             # study 1's gold bars begin on 2017-01-03
EVENT_KINDS = ("flip", "ev_first_strong", "ev_ind", "weak2", "rare_now")

# Recorded at the reconciliation (28 Nov 2026) on the study's bars, both ports equal. Per symbol and timeframe, over
# the Development decision bars: bars, flips to bullish / to bearish, first STRONG candles of a streak and of them on
# the flip bar itself, INDECISION candles after >= 2 STRONG ones (``ev_ind``), bars with ``weak_run`` == 2 (M3's
# trigger) and >= 2, rare-age bars of bullish / bearish streaks; then over the whole series to 2024-06-30: the
# finished streaks and the bar index of the first flip.
_RECORDED = {
    ("XAUUSDm", "1H"): (23590, 2933, 2933, 3831, 1260, 973, 132, 138, 245, 236, 12337, 13),
    ("XAUUSDm", "4H"): (6385, 777, 777, 1010, 318, 284, 30, 30, 74, 76, 3261, 12),
    ("XAUUSDm", "1D"): (1031, 130, 130, 173, 48, 31, 11, 11, 9, 6, 518, 6),
    ("BTCUSDm", "1H"): (35016, 4605, 4606, 5823, 1793, 1383, 193, 201, 440, 431, 15045, 4),
    ("BTCUSDm", "4H"): (8756, 1115, 1114, 1386, 453, 310, 49, 53, 117, 84, 3633, 5),
    ("BTCUSDm", "1D"): (1459, 175, 175, 239, 72, 61, 8, 8, 17, 13, 555, 1),
}
# the same for gold from study 1's start (2017-01-03): only the rare ages and the whole-series figures differ
_RECORDED_GOLD_2017 = {
    "1H": (23590, 2933, 2933, 3831, 1260, 973, 132, 138, 245, 236, 10879, 7),
    "4H": (6385, 777, 777, 1010, 318, 284, 30, 30, 72, 76, 2893, 2),
    "1D": (1031, 130, 130, 173, 48, 31, 11, 11, 7, 6, 462, 12),
}
# Development bars on which gold's rare_now differs between the two starts (2016-01-03 against 2017-01-03)
_GOLD_START_RARE_DIFF = {"1H": 12, "4H": 12, "1D": 10}
# Without the 5,000-streak cap (``keep=None``): Development / Validation bars whose pct_below differs (rare_now
# differs on none, anywhere); and Development bars whose pct_below is exactly 90.0 (each one a rare-age bar)
_NO_CAP_PCT_DIFF = {("XAUUSDm", "1H"): (398, 6594), ("BTCUSDm", "1H"): (4500, 9659)}
_EXACT_90_DEV = {("XAUUSDm", "4H"): 3, ("XAUUSDm", "1D"): 1}


# ───────────────────────────── comparison helpers ─────────────────────────────

def float_identical(a: np.ndarray, b: np.ndarray) -> bool:
    """Bit for bit: NaN on the same bars, the same bit pattern everywhere else (0.0 and -0.0 differ)."""
    na, nb = np.isnan(a), np.isnan(b)
    return bool(np.array_equal(na, nb) and np.array_equal(a[~na].view(np.int64), b[~nb].view(np.int64)))


def identical(x, y) -> list:
    """The keys on which two outputs of the contract differ (empty: identical). The keys, their order, shapes and
    dtypes must be the same; floats bit for bit, the others exactly; the streak frames column by column."""
    if tuple(x) != A.KEYS or tuple(y) != A.KEYS:
        return ["keys"]
    bad = []
    for k in ARRAY_KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if a.dtype != DTYPES[k] or b.dtype != DTYPES[k] or a.shape != b.shape:
            bad.append(k)
        elif a.dtype.kind == "f":
            if not float_identical(a, b):
                bad.append(k)
        elif not np.array_equal(a, b):
            bad.append(k)
    sx, sy = x["streaks"], y["streaks"]
    if (tuple(sx.columns) != A.STREAK_COLUMNS or tuple(sy.columns) != A.STREAK_COLUMNS or len(sx) != len(sy)
            or not sx.index.equals(sy.index)):
        bad.append("streaks")
    else:
        for col in A.STREAK_COLUMNS:
            if (sx[col].dtype != STREAK_DTYPES[col] or sy[col].dtype != STREAK_DTYPES[col]
                    or not np.array_equal(sx[col].to_numpy(), sy[col].to_numpy())):
                bad.append("streaks." + col)
    return bad


def first_differences(x, y, k, n=3):
    if k.startswith("streaks"):
        return k
    a, b = np.asarray(x[k]), np.asarray(y[k])
    if a.dtype.kind == "f":
        i = np.flatnonzero(~((a == b) | (np.isnan(a) & np.isnan(b))) | (np.signbit(a) != np.signbit(b)))
    else:
        i = np.flatnonzero(a != b)
    return [(int(j), a[j].item(), b[j].item()) for j in i[:n]]


def event_table(r, t, tc) -> pd.DataFrame:
    """One row per bar and event kind (``EVENT_KINDS``: a flip, the streak's first STRONG candle, INDECISION after a
    STRONG run, the second WEAK candle in a row, the rare age), in bar order: bar, open and close time, kind, colour,
    age, strong_run, weak_run, pct_below."""
    masks = {"flip": r["flip"], "ev_first_strong": r["ev_first_strong"], "ev_ind": r["ev_ind"],
             "weak2": r["weak_run"] == 2, "rare_now": r["rare_now"]}
    parts = []
    for code, kind in enumerate(EVENT_KINDS):
        ix = np.flatnonzero(masks[kind])
        parts.append(pd.DataFrame({"bar": ix, "t": t[ix], "tc": tc[ix], "kind": np.full(len(ix), code, np.int8),
                                   "dir": r["dir"][ix], "age": r["age"][ix], "strong_run": r["strong_run"][ix],
                                   "weak_run": r["weak_run"][ix], "pct_below": r["pct_below"][ix]}))
    return pd.concat(parts, ignore_index=True).sort_values(["bar", "kind"], kind="stable").reset_index(drop=True)


def counts(r, dev):
    """The recorded tuple for one output (see ``_RECORDED``)."""
    f, d = r["flip"], r["dir"]
    fs = r["ev_first_strong"]
    nz = np.flatnonzero(f)
    return (int(dev.sum()), int((f & dev & (d == 1)).sum()), int((f & dev & (d == -1)).sum()),
            int((fs & dev).sum()), int((fs & f & dev).sum()), int((r["ev_ind"] & dev).sum()),
            int(((r["weak_run"] == 2) & dev).sum()), int(((r["weak_run"] >= 2) & dev).sum()),
            int((r["rare_now"] & dev & (d == 1)).sum()), int((r["rare_now"] & dev & (d == -1)).sum()),
            int(len(r["streaks"])), int(nz[0]))


# ───────────────────────────── 1. the real bars (to 2024-06-30, the guards closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol: for 1H / 4H / 1D the bars (open and close times, OHLC, the Development decision mask, the
    Validation mask) and both ports' outputs, from the study's data start; for gold also from study 1's start. The M1
    bars are released as soon as the bars are built (one symbol's M1 bars in memory at a time; this file peaks at
    about 1.4 GB)."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol in cache:
            return cache[symbol]
        start = TM2.data_start(symbol)
        months = store.available_months(symbol)
        if (2024, 6) not in months or (int(start[:4]), int(start[5:7])) not in months:
            pytest.skip(f"the tick store of {symbol} is not on this machine")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(TM, "STUDY_DIR", closed)
            mp.setattr(TM2, "STUDY_DIR", closed)
            mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
            m = X.load_market(symbol, earliest=start, end="2024-07-01")
            mk = TM.TMarket(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp,
                                     "n": m.n}, TM.CUT_S)
            del m
            assert int(mk.t[-1]) + 60 <= TM.CUT_S                      # nothing from the hold-out is in memory
            m1_first = int(mk.t[0])
            iz = int(np.searchsorted(mk.t, TM.s_of(DEV[1]), side="left"))   # the harness's window end (_window_ix)
            out = {}
            for tf in TFS:
                b = mk.tbars(tf)
                dev = (b.tc > TM.s_of(DEV[0])) & (b.ex < iz)            # tradeiq_market.run's decision bars
                out[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(), c=b.c.copy(),
                             dev=dev, val=b.tc > TM.s_of(VAL_START), complete=b.complete.copy())
            del mk
        for tf, b in out.items():
            b.a = A.heikin_ashi(b.o, b.h, b.l, b.c)
            b.b = B.heikin_ashi(b.o, b.h, b.l, b.c)
            if symbol == "XAUUSDm":                                      # study 1's start: a suffix of the bars
                k = int(np.searchsorted(b.t, TM.s_of(STUDY1_GOLD_START)))
                b.k1 = k
                b.a1 = A.heikin_ashi(b.o[k:], b.h[k:], b.l[k:], b.c[k:])
                b.b1 = B.heikin_ashi(b.o[k:], b.h[k:], b.l[k:], b.c[k:])
        cache[symbol] = NS(start=start, m1_first=m1_first, bars=out)
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_the_hold_out_is_never_read(symbol, real):
    data = real(symbol)
    assert data.start == ("2016-01-01" if symbol == "XAUUSDm" else "2018-01-01")
    for tf, b in data.bars.items():
        assert int(b.tc[-1]) <= TM.CUT_S and bool(b.complete.all()), tf
        assert int(b.t[0]) >= data.m1_first - 86400, tf
        assert len(b.c) > 2000 and np.isfinite(b.c).all(), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_every_key_bit_for_bit(symbol, real):
    data = real(symbol)
    for tf, b in data.bars.items():
        bad = identical(b.a, b.b)
        assert not bad, (symbol, tf, {k: first_differences(b.a, b.b, k) for k in bad if k != "keys"})
        pd.testing.assert_frame_equal(b.a["streaks"], b.b["streaks"], check_exact=True)
        # what the comparison covers: both colours, all four phases, the statistics from the first days on
        assert set(np.unique(b.a["phase"]).tolist()) == {0, 1, 2, 3} and int(b.a["flip"].sum()) > 500, tf
        assert np.isfinite(b.a["pct_below"][b.dev]).all() and int(b.a["rare_now"].sum()) > 20, tf
        if symbol == "XAUUSDm":
            bad = identical(b.a1, b.b1)
            assert not bad, (symbol, tf, "from 2017", {k: first_differences(b.a1, b.b1, k) for k in bad
                                                       if k != "keys"})


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_event_tables_are_identical(symbol, real):
    data = real(symbol)
    for tf, b in data.bars.items():
        ta, tb = event_table(b.a, b.t, b.tc), event_table(b.b, b.t, b.tc)
        assert list(ta.columns) == list(tb.columns) and len(ta) == len(tb), (symbol, tf)
        for col in ta.columns:
            x, y = ta[col].to_numpy(), tb[col].to_numpy()
            ok = float_identical(x, y) if x.dtype.kind == "f" else np.array_equal(x, y)
            assert x.dtype == y.dtype and ok, (symbol, tf, col)
        # the events' structure: flips alternate in colour; one first STRONG and at most one rare age per streak;
        # no evInd and no WEAK candle on a flip bar
        fl = ta[ta["kind"] == 0]
        assert (fl["dir"].to_numpy()[1:] != fl["dir"].to_numpy()[:-1]).all(), (symbol, tf)
        sid = np.cumsum(b.a["flip"])
        for kind in (1, 4):
            bars = ta.loc[ta["kind"] == kind, "bar"].to_numpy()
            assert len(np.unique(sid[bars])) == len(bars), (symbol, tf, EVENT_KINDS[kind])
        assert not (b.a["ev_ind"] & b.a["flip"]).any() and not b.a["weak_run"][b.a["flip"]].any(), (symbol, tf)


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_recorded_development_counts(symbol, real):
    """Development counts recorded at the reconciliation: a guard against both ports changing (counts, no P/L)."""
    data = real(symbol)
    for tf, b in data.bars.items():
        want = _RECORDED[(symbol, tf)]
        assert counts(b.a, b.dev) == want, (symbol, tf, counts(b.a, b.dev))
        assert counts(b.b, b.dev) == want, (symbol, tf, counts(b.b, b.dev))
        if symbol == "XAUUSDm":
            want1 = _RECORDED_GOLD_2017[tf]
            dev1 = b.dev[b.k1:]
            assert counts(b.a1, dev1) == want1 and counts(b.b1, dev1) == want1, (tf, counts(b.a1, dev1))


def test_real_bars_gold_from_2016_or_2017(real):
    """The trend-age statistics count every streak since the first bar, so they depend on where the bars start;
    nothing else does once the Heikin Ashi recursion has forgotten its seed (a few days). On gold, the study's bars
    (from 2016-01-03) and study 1's (from 2017-01-03) give the same candles, colours, phases, streaks and events on
    every Development bar; ``pct_below`` differs on most bars and ``rare_now`` on 12 / 12 / 10 (1H / 4H / 1D)."""
    data = real("XAUUSDm")
    for tf, b in data.bars.items():
        k = b.k1
        assert int(b.t[k]) >= TM.s_of(STUDY1_GOLD_START) and int(b.t[k - 1]) < TM.s_of(STUDY1_GOLD_START)
        dev = b.dev[k:]
        assert dev.sum() == b.dev.sum() and not b.dev[:k].any()
        for key in ARRAY_KEYS:
            x, y = b.a[key][k:][dev], b.a1[key][dev]
            same = float_identical(x, y) if x.dtype.kind == "f" else np.array_equal(x, y)
            if key == "pct_below":
                assert not same, tf
            elif key == "rare_now":
                assert int((x != y).sum()) == _GOLD_START_RARE_DIFF[tf], (tf, int((x != y).sum()))
            else:
                assert same, (tf, key)
        # the candles differ only in the first days after 2017-01-03 (the seed fades as 2^-n)
        diff = np.flatnonzero(b.a["ha_o"][k:] != b.a1["ha_o"])
        assert len(diff) > 0 and int(b.t[k + diff[-1]]) < TM.s_of("2017-03-06"), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_measured_readings(symbol, real):
    """The measured facts ``porting/ha.md`` quotes for the readings (port A; port B is identical on the contract):
    no exact tie, zero range or equal same-colour body on any bar (so the tie rule, the zero-range rule and the strict
    WEAK test cannot move anything here); the cap of 5,000 streaks binds on 1H only and moves ``pct_below`` but no
    ``rare_now``; the script's own one-streak minimum instead of 50 changes no rare age in Development or Validation;
    an exact 90.0 % occurs only on the recorded gold bars, each of them a rare age (``>=`` as written)."""
    data = real(symbol)
    for tf, b in data.bars.items():
        r = b.a
        body = np.abs(r["ha_c"] - r["ha_o"])
        d = r["dir"]
        assert not (r["ha_c"] == r["ha_o"]).any() and not (r["ha_h"] == r["ha_l"]).any(), tf
        assert not ((d[1:] == d[:-1]) & (body[1:] == body[:-1])).any(), tf
        nocap = A._heikin_ashi(b.o, b.h, b.l, b.c, 0.05, 0.25, 5, 90, 50, keep=None)
        assert np.array_equal(nocap["rare_now"], r["rare_now"]), tf
        moved = ~((nocap["pct_below"] == r["pct_below"]) | (np.isnan(nocap["pct_below"]) & np.isnan(r["pct_below"])))
        assert (int((moved & b.dev).sum()), int((moved & b.val).sum())) == _NO_CAP_PCT_DIFF.get((symbol, tf), (0, 0))
        one = A.heikin_ashi(b.o, b.h, b.l, b.c, min_streaks=1)
        assert np.array_equal(one["rare_now"][b.dev | b.val], r["rare_now"][b.dev | b.val]), tf
        ex90 = (r["pct_below"] == 90.0) & b.dev
        assert int(ex90.sum()) == _EXACT_90_DEV.get((symbol, tf), 0) and r["rare_now"][ex90].all(), tf
        # an INDECISION candle has wicks on both sides, so its Heikin Ashi high / low are the bar's own (M2's "that
        # bar's low" is one price either way); a WEAK candle has a wick against its colour (it is not STRONG)
        ind = r["phase"] == A.INDECISION
        assert np.array_equal(r["ha_h"][ind], b.h[ind]) and np.array_equal(r["ha_l"][ind], b.l[ind]), tf
        wk = r["phase"] == A.WEAK
        assert np.array_equal(np.where(d == 1, r["ha_l"], r["ha_h"])[wk], np.where(d == 1, b.l, b.h)[wk]), tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_the_panel_helpers_agree(symbol, real):
    """Claim 5 (PREREG 8, the calibration of "reached age A, then 5+ more") reads the panel's numbers, which each port
    computes from its streak frame with helpers outside the per-bar contract: the array the script holds at a bar's
    close (port A ``kept_lengths``, port B ``lengths_known_at``; l.129-132), ``survive`` (l.176-184), SN / SK
    (l.133-139, 282-284: port A ``panel_at``, port B ``strong_continuation``) and ``pctBelow`` (l.166-173). At the
    first bar of each year the series has, at 40 random bars and at the last bar, the two ports agree, and
    ``pctBelow`` of the held array at the bar's age is the per-bar ``pct_below``, bit for bit."""
    data = real(symbol)
    rng = np.random.default_rng(9)
    for tf, b in data.bars.items():
        n = len(b.c)
        years = {int(np.searchsorted(b.t, TM.s_of(f"{y}-01-01"))) for y in range(2016, 2025)}
        at = sorted({t for t in years if 0 < t < n} | set(rng.integers(0, n, 40).tolist()) | {n - 1})
        sa, sb = b.a["streaks"], b.b["streaks"]
        for t in at:
            d, age = int(b.a["dir"][t]), int(b.a["age"][t])
            held_a, held_b = A.kept_lengths(sa, t, d), B.lengths_known_at(sb, d, t)
            assert held_a.tolist() == held_b and len(held_b) <= B.KEEP, (tf, t)
            assert A.survive(held_a, age, 5) == B.survive(held_b, age, 5), (tf, t)
            p = A.panel_at(b.a, t)
            assert (p["sn"], p["sk"]) == B.strong_continuation(sb, d, upto_flip_bar=t), (tf, t)
            pa, pb = np.array([A.pct_below_of(held_a, age)]), np.array([B.pct_below_scan(held_b, age)])
            assert float_identical(pa, pb) and float_identical(pa, b.a["pct_below"][t:t + 1]), (tf, t)


# ───────────────────────────── 2. the mismatches, by hand ─────────────────────────────

SHAPES = {"S": (1.0, 0.0, 0.5),       # (HA body, wick against the colour, wick with the colour): STRONG
          "T": (1.0, 0.5, 0.5),       # STEADY (never WEAK after a body of 1)
          "I": (0.25, 1.0, 1.0)}      # INDECISION


def shaped(items, p0=1000.0):
    """Bars whose Heikin Ashi candles have the given shapes. Bar 0 is flat at ``p0`` (a zero-range, bullish, STRONG
    candle with haO = haC = p0). Each later item is ``(kind, colour)`` with kind in ``SHAPES``, ``("W", colour,
    body)`` (a body with both wicks equal to it: WEAK after a larger body of its colour), ``("Z",)`` (a tie: body 0,
    wicks 1 and 1, a bullish INDECISION) or ``("F",)`` (a flat bar at the candle's open: zero range, bullish,
    STRONG). The bar is H = haH, L = haL, O = C = (4 haC - H - L) / 2, so every price is a multiple of 1/16 and every
    value exact (asserted)."""
    rows = [(p0, p0, p0, p0)]
    hao = hac = p0
    for it in items:
        hao = (hao + hac) / 2.0
        if it[0] == "F":
            rows.append((hao, hao, hao, hao))
            hac = hao
            continue
        if it[0] == "W":
            _, d, body = it
            opp = wt = body
        elif it[0] == "Z":
            d, body, opp, wt = 1, 0.0, 1.0, 1.0
        else:
            (body, opp, wt), d = SHAPES[it[0]], it[1]
        want = hao + d * body
        hi, lo = (want + wt, hao - opp) if d == 1 else (hao + opp, want - wt)
        m = (4.0 * want - hi - lo) / 2.0
        assert lo <= m <= hi
        rows.append((m, hi, lo, m))
        hac = (m + hi + lo + m) / 4.0
        assert hac == want
    return tuple(np.array(x, dtype=np.float64) for x in zip(*rows))


def runs_of(lengths):
    """STEADY candles in streaks of the given lengths, alternating from bullish (bar 0, the flat bar, is the first
    bullish candle)."""
    items, d = [], 1
    for i, k in enumerate(lengths):
        items += [("T", d)] * (k - 1 if i == 0 else k)
        d = -d
    return shaped(items)


def test_mismatch_the_minimum_counts_every_finished_streak():
    """PREREG 6.8: "rare-age rules need at least 50 finished streaks of that colour". Port A counted every finished
    streak of the colour; port B counted the lengths its capped array holds (l.131-132). With the script's cap of
    5,000 and the plan's 50 the two are the same (the array holds min(finished, 5,000)); they differ only with a
    private cap below the minimum. Resolved for port A's reading, the plan's words; port B is aligned.

    By hand: streaks bull 9 (bars 0-8), bear 1, bull 1, bear 1, bull 1, bear 1, bull 1, bear 1, then bull 3 (bars
    16-18). With a cap of 3 the bull array at bar 17 is [1, 1, 1] (the 9 was dropped at the fourth bull push, bar 15)
    while four bull streaks have finished. Bar 17 is age 2: 3 of 3 kept lengths are below 2, 100 % >= 90, and age 1
    (bar 16) had 0 %: the rare-age crossing. A minimum of 4 is met (4 finished), so both ports now say rare at bar 17
    only; old port B (3 lengths held < 4) said never. A minimum of 5 is not met. Without the cap the array is
    [9, 1, 1, 1]: 75 % at ages 2 and 3, never rare."""
    bars = runs_of([9, 1, 1, 1, 1, 1, 1, 1, 3])
    assert len(bars[0]) == 19
    ra = A._heikin_ashi(*bars, 0.05, 0.25, 5, 90, 4, keep=3)
    rb = B._transcribe(*bars, min_streaks=4, keep=3)
    assert not identical(ra, rb)
    st = ra["streaks"]
    assert st["length"].tolist() == [9, 1, 1, 1, 1, 1, 1, 1] and st["dir"].tolist() == [1, -1] * 4
    assert A.kept_lengths(st, 17, 1, keep=3).tolist() == [1, 1, 1] and int((st["dir"] == 1).sum()) == 4
    assert ra["pct_below"][16] == 0.0 and ra["pct_below"][17] == 100.0 and ra["age"][17] == 2
    assert np.flatnonzero(ra["rare_now"]).tolist() == [17]
    # what port B computed before the fix: the crossing without the minimum, gated by the array's size (3 < 4)
    crossing = A._heikin_ashi(*bars, 0.05, 0.25, 5, 90, 0, keep=3)["rare_now"]
    held = np.array([len(A.kept_lengths(st, t, int(ra["dir"][t]), keep=3)) for t in range(19)])
    assert np.flatnonzero(crossing).tolist() == [17] and not (crossing & (held >= 4)).any()
    for ms, keep, want in ((5, 3, []), (4, None, []), (3, 3, [17]), (0, 3, [17])):
        xa = A._heikin_ashi(*bars, 0.05, 0.25, 5, 90, ms, keep=keep)
        xb = B._transcribe(*bars, min_streaks=ms, keep=keep)
        assert not identical(xa, xb) and np.flatnonzero(xa["rare_now"]).tolist() == want, (ms, keep)


def test_mismatch_infinite_integer_inputs_are_refused_alike():
    """``ahead_n``, ``rare_pct``, ``min_streaks`` and the private cap are integers (l.26, l.28; PREREG 6.8). An infinite
    value made port B's check call ``math.floor(inf)``, which raises OverflowError, not the contract's ValueError;
    its check now tests finiteness first. Port A was right."""
    bars = runs_of([3, 2, 4, 1, 5])
    for kw in ({"ahead_n": math.inf}, {"ahead_n": -math.inf}, {"rare_pct": math.inf}, {"rare_pct": math.nan},
               {"min_streaks": math.inf}, {"min_streaks": math.nan}, {"ahead_n": math.nan}):
        with pytest.raises(ValueError):
            A.heikin_ashi(*bars, **kw)
        with pytest.raises(ValueError):
            B.heikin_ashi(*bars, **kw)
    with pytest.raises(ValueError):
        A._heikin_ashi(*bars, 0.05, 0.25, 5, 90, 50, keep=math.inf)
    with pytest.raises(ValueError):
        B._transcribe(*bars, keep=math.inf)


# ───────────────────────────── 3. synthetic bars ─────────────────────────────

def walk(rng, n, kind):
    """A random walk of OHLC bars around 1000: ``round`` rounds every price to a whole unit (exact ties haC == haO
    become common), ``flat`` inserts runs of 60 bars with O = H = L = C (zero-range candles)."""
    c = 1000.0 + np.cumsum(rng.normal(0.0, 1.0, n))
    o = np.r_[1000.0, c[:-1]] + rng.normal(0.0, 0.3, n) * (rng.random(n) < 0.3)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.6, n)) * (rng.random(n) < 0.85)
    l = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.6, n)) * (rng.random(n) < 0.85)
    if kind == "round":
        o, h, l, c = (np.round(x, 0) for x in (o, h, l, c))
        h, l = np.maximum(h, np.maximum(o, c)), np.minimum(l, np.minimum(o, c))
    elif kind == "flat":
        for s in range(300, n - 60, 400):
            o[s:s + 60] = h[s:s + 60] = l[s:s + 60] = c[s:s + 60] = c[s - 1]
    return o, h, l, c


def random_shapes(rng, n):
    """``n`` bars of random exact shapes: STRONG, STEADY, INDECISION, WEAK-shaped (bodies 1/2, 1/4, 1/8), ties and
    flat bars, the colour changing with probability 0.3."""
    items, d = [], 1
    for _ in range(n - 1):
        if rng.random() < 0.3:
            d = -d
        k = int(rng.choice(6, p=[0.3, 0.15, 0.2, 0.2, 0.08, 0.07]))
        if k == 3:
            items.append(("W", d, float(rng.choice([0.5, 0.25, 0.125]))))
        elif k == 4:
            items.append(("Z",))
        elif k == 5:
            items.append(("F",))
        else:
            items.append(("STI"[k], d))
    return shaped(items)


def random_inputs(rng):
    """The script's inputs drawn inside their ranges and steps (l.20-28: strongTol 0-0.3, dojiMax 0.05-0.5 by 0.01;
    aheadN 1-50; rarePct 50-99) and the plan's minimum, 0 to 120 finished streaks."""
    return dict(strong_tol=float(np.round(rng.uniform(0.0, 0.3), 2)),
                doji_max=float(np.round(rng.uniform(0.05, 0.5), 2)), ahead_n=int(rng.integers(1, 51)),
                rare_pct=int(rng.integers(50, 100)), min_streaks=int(rng.choice([0, 1, 2, 5, 20, 50, 120])))


@pytest.mark.parametrize("seed", range(6))
def test_random_bars_and_inputs_bit_for_bit(seed):
    rng = np.random.default_rng(2027 + seed)
    seen = {"tie": 0, "zero": 0, "rare": 0, "ind": 0, "weak2": 0}
    for case in range(14):
        kind = ("walk", "round", "flat", "shapes")[case % 4]
        n = int(rng.choice([60, 400, 1500, 3000]))
        bars = random_shapes(rng, n) if kind == "shapes" else walk(rng, n, kind)
        p = {} if case % 5 == 0 else random_inputs(rng)
        ra, rb = A.heikin_ashi(*bars, **p), B.heikin_ashi(*bars, **p)
        bad = identical(ra, rb)
        assert not bad, (seed, case, kind, n, p, {k: first_differences(ra, rb, k) for k in bad if k != "keys"})
        seen["tie"] += int((ra["ha_c"] == ra["ha_o"]).sum())
        seen["zero"] += int((ra["ha_h"] == ra["ha_l"]).sum())
        seen["rare"] += int(ra["rare_now"].sum())
        seen["ind"] += int(ra["ev_ind"].sum())
        seen["weak2"] += int((ra["weak_run"] == 2).sum())
    assert all(v > 0 for v in seen.values()), seen          # the cases exercise every branch


@pytest.mark.parametrize("keep", [1, 2, 3, 7, 40])
def test_small_caps_below_and_above_the_minimum_bit_for_bit(keep):
    """The private cap (``keep``, the script's 5,000 is the contract) on random bars, with minimums below, equal to and
    above it: the mismatch of section 2 is now absent everywhere. Every streak is still listed in ``streaks``."""
    rng = np.random.default_rng(500 + keep)
    for case, ms in enumerate((0, 1, keep, keep + 1, 50)):
        bars = random_shapes(rng, 2500) if case % 2 else walk(rng, 2500, "round")
        ra = A._heikin_ashi(*bars, 0.05, 0.25, 5, 90, ms, keep=keep)
        rb = B._transcribe(*bars, min_streaks=ms, keep=keep)
        bad = identical(ra, rb)
        assert not bad, (keep, ms, {k: first_differences(ra, rb, k) for k in bad if k != "keys"})
        assert ra["rare_now"].any() or ms > 0, (keep, ms)
        assert len(ra["streaks"]) == int(ra["flip"].sum())
    full_a = A._heikin_ashi(*bars, 0.05, 0.25, 5, 90, 50, keep=None)
    assert not identical(full_a, B._transcribe(*bars, keep=None))


def test_short_series_bit_for_bit():
    """0 to 9 bars, from walks and exact shapes (bar 0 alone, a flip at bar 1, no finished streak, one finished
    streak), with the defaults and with a minimum of 0."""
    rng = np.random.default_rng(77)
    sources = [walk(rng, 40, "walk"), walk(rng, 40, "round"), random_shapes(rng, 40), runs_of([1, 1, 2, 3, 1, 4])]
    for bars in sources:
        for n in range(10):
            cut = tuple(x[:n] for x in bars)
            for p in ({}, {"min_streaks": 0, "rare_pct": 50}):
                ra, rb = A.heikin_ashi(*cut, **p), B.heikin_ashi(*cut, **p)
                bad = identical(ra, rb)
                assert not bad, (n, p, {k: first_differences(ra, rb, k) for k in bad if k != "keys"})
                assert len(ra["dir"]) == n and len(ra["streaks"]) == max(0, int(ra["flip"].sum()))


def test_the_two_ports_refuse_bad_bars_and_inputs_alike():
    """Unequal lengths, a 2-D array, a NaN or an infinite price, inputs outside the script's ranges (l.20-28), a
    non-integer or negative integer input, a bool: both raise ValueError. Lists and integral floats are accepted
    alike."""
    o, h, l, c = walk(np.random.default_rng(5), 120, "walk")
    nan_c = c.copy()
    nan_c[40] = math.nan
    for args in ((o, h, l, c[:-1]), (o, h, l, nan_c), (o, h, np.vstack([l, l]), c), (o, h, l, np.r_[c[:-1], np.inf])):
        with pytest.raises(ValueError):
            A.heikin_ashi(*args)
        with pytest.raises(ValueError):
            B.heikin_ashi(*args)
    for kw in ({"strong_tol": -0.01}, {"strong_tol": 0.31}, {"strong_tol": math.nan}, {"doji_max": 0.04},
               {"doji_max": 0.51}, {"ahead_n": 0}, {"ahead_n": 51}, {"ahead_n": 2.5}, {"rare_pct": 49},
               {"rare_pct": 100}, {"rare_pct": 90.5}, {"min_streaks": -1}, {"min_streaks": 1.5}, {"ahead_n": True},
               {"rare_pct": np.bool_(True)}):
        with pytest.raises(ValueError):
            A.heikin_ashi(o, h, l, c, **kw)
        with pytest.raises(ValueError):
            B.heikin_ashi(o, h, l, c, **kw)
    lists = (o.tolist(), h.tolist(), l.tolist(), c.tolist())
    want = A.heikin_ashi(o, h, l, c)
    for got in (A.heikin_ashi(*lists, ahead_n=5.0, rare_pct=np.int64(90)), B.heikin_ashi(*lists, ahead_n=5.0,
                                                                                          rare_pct=np.int64(90))):
        assert not identical(got, want)
