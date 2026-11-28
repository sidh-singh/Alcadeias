"""
BigBeluga's Swing Profile (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.4 and claims 11-12 of section
8): the reconciliation of its two independent ports. The notes for readers are
``backtest_results/tradeiq_2027/porting/swing.md``.

* Port A, ``backtesting/research/tradeiq2_ind_swing.py``: the production port (numpy and numba); its own tests are
  ``test_tradeiq2_ind_swing_a.py``.
* Port B, ``tests/tradeiq2_oracle_swing.py``: the oracle, a bar-by-bar transcription in plain Python; its own tests
  are ``test_tradeiq2_ind_swing_b.py``.

1. Real bars (skipped when the tick store or the Binance klines are absent). XAUUSDm and BTCUSDm, 1H and 4H (the
   timeframes of PREREG 6.4) and 1D (information only: the plan does not use the script there), from the study's data
   start (``tradeiq2_market.data_start``: gold 2016-01-01 when all twelve 2016 months are in the store, BTC
   2018-01-01) to 2024-06-30. The M1 bars come from ``external.load_market(symbol, earliest=..., end="2024-07-01")``,
   so nothing at or after the hold-out start is read, and study 1's ``TMarket.tbars`` builds them into bars (what
   ``tradeiq2_market.load`` serves on 1H / 4H / 1D), with study 1's and study 2's guards pointed at an empty folder.
   The volume is PREREG 2's: gold its tick volume, BTC Binance BTCUSDT spot volume (study 1's 1h klines on our 1H
   bars, summed for 4H / 1D; an hour without a kline has volume 0). Gold is also run from 2017-01-03 (study 1's start;
   those bars are a suffix of the same bars). Asserted:
   - every key of the contract, in the same order and dtype: floats bit for bit (the same NaN places, identical bits
     elsewhere, so 0.0 and -0.0 would differ), bool, int8 and int64 exactly;
   - the ``legs`` table (one row per flip) identical: every column and dtype, the tied levels as the same tuples;
   - the event tables (flips with their times and levels; swing confirmations) identical;
   - the 2019-2022 counts recorded at the reconciliation (the harness's Development decision bars: closing after
     2019-01-01 00:00, filled before 2023-01-01 00:00), for both ports. Counts and geometry only: no rule is run and
     no profit or loss is computed;
   - from 2019 the two gold starts give the same value of every key on 1H, and on 4H the same apart from the last
     bits of ``atr_at_flip`` (the ATR(200)'s seed).
   No tolerance anywhere, and nothing had to be aligned: both ports add each bar's volume to its bins from the newer
   swing back to the older (l.125), sum the bins in index order with plain additions (``array.sum``, l.184-187), take
   the midpoint of l.132 and the drawn level ``math.avg(binLow, binHigh)`` of l.154 with the script's operations, and
   compute ``ta.atr(200)`` as ``pine_atr`` / ``pine_rma`` (study 1's verified arithmetic), so even BTC's fractional
   volumes give the same bits.
2. The mismatch the reconciliation found, by hand: a leg needing more than 100,000 bins (Pine's array limit; the
   script's ``array.new<float>(binCount, 0.)`` at l.117 stops with a runtime error). Port B read it as not computable,
   like ``binCount == 0``; port A computed up to 1,000,000 bins and raised above. Port A is fixed.
3. The contract mismatch: ``f_dir`` and ``legs.dir`` were int8 in port A and int64 in port B; both are int8 now (the
   study's type for direction codes).
4. Synthetic bars: random inputs on random walks, price grids that make ties, flat stretches and fractional volumes;
   short series (the warm-up); degenerate inputs (flat bars, zero volume, lengths 1 and 2): bit for bit.

Line numbers l. are those of the owner's plain-text copy of the script (third-party code, cited, never copied).
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
from backtesting.research import tradeiq2_ind_swing as A
from backtesting.research import tradeiq2_market as TM2
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_swing as B  # noqa: E402

SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")                                     # PREREG 6.4: 1H and 4H; 1D for information
PER_BAR = A.KEYS[:-1]
DTYPES = {"is_down_move": np.bool_, "hs_bar": np.int64, "hs_price": np.float64, "ls_bar": np.int64,
          "ls_price": np.float64, "flip": np.bool_, "f_dir": np.int8, "f_lo": np.float64, "f_hi": np.float64,
          "f_poc": np.float64, "f_poc_ties": np.int64, "f_delta_pct": np.float64, "f_total": np.float64}
LEG_DTYPES = {"flip_bar": np.int64, "dir": np.int8, "start_bar": np.int64, "end_bar": np.int64, "lo": np.float64,
              "hi": np.float64, "poc": np.float64, "poc_all": np.object_, "delta_pct": np.float64,
              "total": np.float64, "fifty": np.float64, "atr_at_flip": np.float64}
DEV = ("2019-01-01", "2023-01-01")                           # PREREG 3: Development
STUDY1_GOLD_START = "2017-01-01"                             # study 1's gold bars begin on 2017-01-03

# Recorded at the reconciliation (28 Nov 2026) on the study's bars, both ports equal. Per symbol and timeframe, over
# the Development decision bars: bars; flips finishing an up / a down leg; swing highs / lows confirmed; legs with a
# POC tie, and those whose nearest tied bin is not the lowest; legs whose dir is not the stored pair's geometry;
# one-bar legs (start_bar == end_bar); forming bars with f_dir 0 although both swings exist; forming bars with a tie;
# touch-and-hold bars of the forming POC (f_dir +1, low <= POC < close / f_dir -1, high >= POC > close; raw shapes,
# before any rule); flips whose close is already past the finished leg's POC in the new direction. Then over the
# whole series to 2024-06-30: the first flip's bar index, the flips, the legs that have a profile.
_RECORDED = {
    ("XAUUSDm", "1H"): (23590, 159, 159, 863, 658, 7, 4, 0, 0, 46, 612, 592, 491, 211, 57, 637, 635),
    ("XAUUSDm", "4H"): (6385, 44, 44, 250, 163, 0, 0, 0, 0, 0, 5, 158, 126, 58, 79, 174, 172),
    ("XAUUSDm", "1D"): (1031, 6, 6, 37, 23, 1, 1, 0, 0, 0, 11, 10, 15, 4, 77, 25, 21),
    ("BTCUSDm", "1H"): (35016, 229, 229, 1121, 910, 13, 9, 1, 2, 115, 1204, 977, 869, 329, 54, 741, 739),
    ("BTCUSDm", "4H"): (8756, 54, 54, 343, 220, 1, 1, 0, 0, 0, 137, 209, 191, 74, 267, 170, 169),
    ("BTCUSDm", "1D"): (1459, 7, 7, 66, 31, 0, 0, 0, 0, 0, 0, 4, 32, 5, 122, 30, 28),
}


# ───────────────────────────── the comparison ─────────────────────────────

def _bits_equal(a: np.ndarray, b: np.ndarray) -> bool:
    """Floats bit for bit: NaN in the same places and identical bits elsewhere."""
    na, nb = np.isnan(a), np.isnan(b)
    return bool(np.array_equal(na, nb) and np.array_equal(np.ascontiguousarray(a[~na]).view(np.uint64),
                                                         np.ascontiguousarray(b[~nb]).view(np.uint64)))


def legs_identical(x: pd.DataFrame, y: pd.DataFrame) -> list:
    """The columns on which two ``legs`` tables differ (empty: identical): the columns, their order and dtypes, the
    index, every value (floats bit for bit), the tied levels as the same tuples of floats."""
    if list(x.columns) != list(A.LEG_COLUMNS) or list(y.columns) != list(A.LEG_COLUMNS):
        return ["columns"]
    if len(x) != len(y) or not (x.index.equals(y.index) and isinstance(x.index, pd.RangeIndex)
                                and isinstance(y.index, pd.RangeIndex)):
        return ["rows"]
    bad = []
    for k in A.LEG_COLUMNS:
        if x[k].dtype != LEG_DTYPES[k] or y[k].dtype != LEG_DTYPES[k]:
            bad.append(k)
        elif k == "poc_all":
            px, py = list(x[k]), list(y[k])
            if not (all(type(p) is tuple for p in px + py) and px == py
                    and all(_bits_equal(np.array(p, float), np.array(q, float)) for p, q in zip(px, py))):
                bad.append(k)
        elif LEG_DTYPES[k] == np.float64:
            if not _bits_equal(x[k].to_numpy(), y[k].to_numpy()):
                bad.append(k)
        elif not np.array_equal(x[k].to_numpy(), y[k].to_numpy()):
            bad.append(k)
    return bad


def identical(x, y) -> list:
    """The keys on which two outputs of the contract differ (empty: identical): the keys and their order, every
    per-bar array's dtype, shape and values, and the legs table."""
    if tuple(x) != A.KEYS or tuple(y) != A.KEYS:
        return ["keys"]
    bad = []
    for k in PER_BAR:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if a.dtype != DTYPES[k] or b.dtype != DTYPES[k] or a.shape != b.shape:
            bad.append(k)
        elif a.dtype.kind == "f":
            if not _bits_equal(a, b):
                bad.append(k)
        elif not np.array_equal(a, b):
            bad.append(k)
    return bad + ["legs." + k for k in legs_identical(x["legs"], y["legs"])]


def first_differences(x, y, k, n=3):
    if k.startswith("legs") or k == "keys":
        return k
    a, b = np.asarray(x[k]), np.asarray(y[k])
    if a.dtype.kind == "f" and b.dtype.kind == "f":
        i = np.flatnonzero(~((a == b) | (np.isnan(a) & np.isnan(b))))
    else:
        i = np.flatnonzero(a.astype(np.int64) != b.astype(np.int64))
    return (str(a.dtype), str(b.dtype), [(int(j), a[j].item(), b[j].item()) for j in i[:n]])


def explain(x, y, bad):
    return {k: first_differences(x, y, k) for k in bad}


def event_tables(r, t, tc, c):
    """The flips (bar, open and close time, side, the two swing bars and their open times, low, high, POC, number of
    tied bins, delta, total, 50% level, ATR, the flip bar's close) and the swing confirmations (bar, side, the swing's
    bar and price)."""
    L = r["legs"]
    f = L["flip_bar"].to_numpy()
    s, e = L["start_bar"].to_numpy(), L["end_bar"].to_numpy()
    flips = {"bar": f, "t": t[f], "tc": tc[f], "dir": L["dir"].to_numpy(), "start_bar": s, "end_bar": e,
             "t_start": np.where(s >= 0, t[np.maximum(s, 0)], -1), "t_end": np.where(e >= 0, t[np.maximum(e, 0)], -1),
             "ties": L["poc_all"].map(len).to_numpy(np.int64), "close": c[f]}
    for k in ("lo", "hi", "poc", "delta_pct", "total", "fifty", "atr_at_flip"):
        flips[k] = L[k].to_numpy()
    hs, ls = r["hs_bar"], r["ls_bar"]
    at_h = np.flatnonzero(np.r_[False, hs[1:] != hs[:-1]])
    at_l = np.flatnonzero(np.r_[False, ls[1:] != ls[:-1]])
    bars_ = np.r_[at_h, at_l]
    order = np.lexsort((np.r_[np.ones(len(at_h)), -np.ones(len(at_l))], bars_))
    swings = {"bar": bars_[order], "side": np.r_[np.ones(len(at_h), np.int8), -np.ones(len(at_l), np.int8)][order],
              "swing_bar": np.r_[hs[at_h], ls[at_l]][order],
              "price": np.r_[r["hs_price"][at_h], r["ls_price"][at_l]][order]}
    return flips, swings


def counts(r, b) -> tuple:
    """The recorded tuple of one output (see ``_RECORDED``)."""
    dev, o, h, l, c = b.dev, b.o, b.h, b.l, b.c
    L = r["legs"]
    fb = L["flip_bar"].to_numpy()
    D = L[dev[fb]]
    f = D["flip_bar"].to_numpy()
    hs, ls, fd, poc = r["hs_bar"], r["ls_bar"], r["f_dir"], r["f_poc"]
    hs_set = np.r_[False, hs[1:] != hs[:-1]]
    ls_set = np.r_[False, ls[1:] != ls[:-1]]
    ties = D["poc_all"].map(len).to_numpy()
    lowest = np.array([p[0] if p else np.nan for p in D["poc_all"]])
    geom = np.sign(hs[f] - ls[f])
    dirs = D["dir"].to_numpy()
    with np.errstate(invalid="ignore"):
        long_ = dev & (fd == 1) & (l <= poc) & (c > poc)
        short = dev & (fd == -1) & (h >= poc) & (c < poc)
    past = np.where(dirs == 1, c[f] < D["poc"].to_numpy(), c[f] > D["poc"].to_numpy())
    return (int(dev.sum()), int((dirs == 1).sum()), int((dirs == -1).sum()), int((hs_set & dev).sum()),
            int((ls_set & dev).sum()), int((ties > 1).sum()), int(((ties > 1) & (D["poc"].to_numpy() != lowest)).sum()),
            int(((geom != 0) & (geom != dirs)).sum()), int((D["start_bar"] == D["end_bar"]).sum()),
            int((dev & (hs >= 0) & (ls >= 0) & (fd == 0)).sum()), int((dev & (r["f_poc_ties"] > 1)).sum()),
            int(long_.sum()), int(short.sum()), int(past.sum()), int(fb[0]), int(len(L)),
            int(np.isfinite(L["poc"].to_numpy()).sum()))


# ───────────────────────────── 1. the real bars (to 2024-06-30, the guards closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol: for 1H / 4H / 1D the bars (open and close times, OHLC, PREREG 2's volume, the Development decision
    mask) and both ports' outputs, from the study's data start; for gold also from study 1's start. The M1 bars are
    released as soon as the bars and the volume are built (one symbol's M1 bars in memory at a time; this file peaks
    at about 1 GB)."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol in cache:
            return cache[symbol]
        start = TM2.data_start(symbol)
        months = store.available_months(symbol)
        if (2024, 6) not in months or (int(start[:4]), int(start[5:7])) not in months:
            pytest.skip(f"the tick store of {symbol} is not on this machine")
        if symbol.startswith("BTC") and not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
            pytest.skip("the Binance klines are not on this machine")
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
                bb = mk.tbars(tf)
                if symbol.startswith("BTC"):
                    vol = np.asarray(TM.binance_volume(mk, tf)[0], np.float64)
                else:
                    vol = np.asarray(bb.vol, np.float64)
                dev = (bb.tc > TM.s_of(DEV[0])) & (bb.ex < iz)          # tradeiq_market.run's decision bars
                out[tf] = NS(t=bb.t.copy(), tc=bb.tc.copy(), o=bb.o.copy(), h=bb.h.copy(), l=bb.l.copy(),
                             c=bb.c.copy(), v=vol.copy(), dev=dev)
            del mk
        for tf, b in out.items():
            bars_ = (b.o, b.h, b.l, b.c, b.v)
            b.a, b.b = A.swing_profile(*bars_), B.swing_profile(*bars_)
            if symbol == "XAUUSDm":                                      # study 1's start: a suffix of the bars
                k = int(np.searchsorted(b.t, TM.s_of(STUDY1_GOLD_START)))
                b.k1 = k
                cut = tuple(x[k:] for x in bars_)
                b.a1, b.b1 = A.swing_profile(*cut), B.swing_profile(*cut)
        cache[symbol] = NS(start=start, m1_first=m1_first, bars=out)
        return cache[symbol]
    return get


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_the_hold_out_is_never_read(symbol, real):
    data = real(symbol)
    assert data.start == ("2016-01-01" if symbol == "XAUUSDm" else "2018-01-01")
    for tf, b in data.bars.items():
        assert int(b.tc[-1]) <= TM.CUT_S and int(b.t[0]) >= data.m1_first - 86400, tf
        assert len(b.c) > 2000 and np.isfinite(b.c).all(), tf
        assert np.isfinite(b.v).all() and (b.v >= 0).all() and (b.v > 0).mean() > 0.99, tf


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_every_key_bit_for_bit(symbol, real):
    data = real(symbol)
    for tf, b in data.bars.items():
        bad = identical(b.a, b.b)
        assert not bad, (symbol, tf, explain(b.a, b.b, bad))
        assert len(b.a["legs"]) > 20 and np.isfinite(b.a["f_poc"]).mean() > 0.9, (symbol, tf)
        if symbol == "XAUUSDm":
            bad = identical(b.a1, b.b1)
            assert not bad, (symbol, tf, "from 2017", explain(b.a1, b.b1, bad))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_event_tables_are_identical(symbol, real):
    data = real(symbol)
    for tf, b in data.bars.items():
        for ta, tb in zip(event_tables(b.a, b.t, b.tc, b.c), event_tables(b.b, b.t, b.tc, b.c)):
            assert list(ta) == list(tb)
            for col in ta:
                x, y = ta[col], tb[col]
                assert x.dtype == y.dtype, (symbol, tf, col)
                assert _bits_equal(x, y) if x.dtype.kind == "f" else np.array_equal(x, y), (symbol, tf, col)
        flips, swings = event_tables(b.a, b.t, b.tc, b.c)
        assert np.all(flips["dir"][1:] == -flips["dir"][:-1]), (symbol, tf)        # flips alternate
        late = b.tc[flips["bar"]] > TM.s_of(DEV[0])                               # from 2019 every leg has a profile
        assert np.isfinite(flips["poc"][late]).all() and (flips["ties"][late] >= 1).all(), (symbol, tf)
        assert (flips["start_bar"][late] <= flips["end_bar"][late]).all(), (symbol, tf)
        assert (flips["end_bar"][late] < flips["bar"][late]).all(), (symbol, tf)
        assert (swings["swing_bar"] == swings["bar"] - 1).all(), (symbol, tf)      # stored one bar late


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_recorded_development_counts(symbol, real):
    """2019-2022 counts recorded at the reconciliation: a guard against both ports changing (counts, no P/L)."""
    data = real(symbol)
    for tf, b in data.bars.items():
        want = _RECORDED[(symbol, tf)]
        assert counts(b.a, b) == want, (symbol, tf, counts(b.a, b))
        assert counts(b.b, b) == want, (symbol, tf, counts(b.b, b))


def test_real_bars_gold_from_2016_or_2017_is_the_same_from_2019(real):
    """The study's gold bars start on 2016-01-03, study 1's on 2017-01-03. On every Development bar of 1H every key is
    the same under both starts (the swing indices shifted by the cut), and so is every leg; on 4H too, except the last
    bits of ``atr_at_flip`` on 56 of the 88 Development legs (the ATR(200)'s seed: at most 6.4e-9 relative; from
    2021-08-25 on the two 4H ATRs are equal bit for bit, on 1H from 2018-02-19). The bin counts, POCs and deltas never
    move. On 1D, which the plan does not use for this script, the 200-day ATR is still unsettled in 2019 (up to 3.3%
    apart) and the forming POC differs on 144 bars of 2019-2024H1."""
    data = real("XAUUSDm")
    for tf in ("1H", "4H"):
        b = data.bars[tf]
        k = b.k1
        assert int(b.t[k]) >= TM.s_of(STUDY1_GOLD_START) and int(b.t[k - 1]) < TM.s_of(STUDY1_GOLD_START)
        dev = b.dev[k:]
        assert dev.sum() == b.dev.sum() and not b.dev[:k].any()
        tail = {key: b.a[key][k:][dev] for key in PER_BAR}
        later = {key: b.a1[key][dev] for key in PER_BAR}
        for key in ("hs_bar", "ls_bar"):
            tail[key] = np.where(tail[key] >= 0, tail[key] - k, -1)
        for key in PER_BAR:
            x, y = tail[key], later[key]
            assert (_bits_equal(x, y) if x.dtype.kind == "f" else np.array_equal(x, y)), (tf, key)
        L2016 = b.a["legs"][b.dev[b.a["legs"]["flip_bar"].to_numpy()]].reset_index(drop=True)
        L2017 = b.a1["legs"][dev[b.a1["legs"]["flip_bar"].to_numpy()]].reset_index(drop=True)
        for col in ("flip_bar", "start_bar", "end_bar"):
            L2016[col] = L2016[col] - k
        atr16, atr17 = L2016.pop("atr_at_flip").to_numpy(), L2017.pop("atr_at_flip").to_numpy()
        assert not legs_identical(L2016.assign(atr_at_flip=atr17), L2017.assign(atr_at_flip=atr17)), tf
        moved = atr16 != atr17
        assert np.abs(atr16 / atr17 - 1).max() < 6.5e-9, tf
        assert int(moved.sum()) == {"1H": 0, "4H": 56}[tf] and len(atr16) == {"1H": 318, "4H": 88}[tf], tf


# ───────────────────────────── 2. the mismatch, by hand ─────────────────────────────

# swing_len 3, atr_len 1 (the ATR is the bar's true range), bins of 0.5 ATR; prices are multiples of 1/8 (exact in
# binary). Bar 2's high 10.0 is stored at bar 3, bar 7's low 7.0 at bar 8; bar 9 is a new 3-bar high: the flip that
# finishes the down leg 2 .. 7. Bar 8 has the true range 2^-17 (open = low = close = bar 7's close 7.125).
TINY = [
    (8.00, 8.50, 7.50, 8.25, 1), (8.25, 9.00, 8.00, 8.75, 1), (8.75, 10.00, 8.625, 9.875, 1),
    (9.875, 9.875, 9.00, 9.50, 2), (9.50, 9.625, 8.50, 8.875, 3), (8.875, 8.875, 8.00, 8.25, 4),
    (7.875, 8.25, 7.75, 7.875, 5), (7.875, 8.125, 7.00, 7.125, 6), (7.125, 7.125 + 2.0 ** -17, 7.125, 7.125, 1),
    (7.375, 8.25, 7.25, 7.50, 100), (7.50, 8.75, 7.375, 8.50, 1), (8.50, 9.50, 8.25, 9.25, 1),
    (9.25, 9.375, 8.75, 9.00, 1), (9.00, 9.125, 8.00, 8.25, 1),
]


def _cols(rows):
    a = np.array(rows, dtype=np.float64)
    return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy(), a[:, 4].copy()


def test_mismatch_bin_count_above_pines_array_limit():
    """l.110 / l.117: ``binCount = int(|H - L| / priceBinSize)`` sizes ``array.new<float>(binCount, 0.)``. Pine limits
    an array to 100,000 elements, so a leg that needs more bins stops the script with a runtime error, as
    ``binCount == 0`` does (the loop 0 to -1, the division by zero). There is no Pine value to copy: both ports read
    every such leg as not computable (NaN POC, delta and total, no ties, ``()``).

    Before the reconciliation port B already did; port A computed up to 1,000,000 bins and raised a ValueError above
    (its own guard, not the script's). Here: at bar 8 the forming leg 10.0 / 7.0 has bins of 2^-18, i.e. 786,432 bins
    (port A computed it); with a true range of 2^-20, 6,291,456 bins (port A raised). The real bars never come near:
    no leg of the study's bars needs more than 111 bins. Port A is fixed (``_n_bins``, ``PINE_ARRAY_MAX``)."""
    for tiny, bins in ((2.0 ** -17, 786_432), (2.0 ** -20, 6_291_456)):
        rows = [list(r) for r in TINY]
        rows[8][1] = 7.125 + tiny
        o, h, l, c, v = _cols(rows)
        assert I.atr(h, l, c, 1)[8] == tiny and 3.0 / (tiny * 0.5) == bins
        ra = A.swing_profile(o, h, l, c, v, swing_len=3, atr_len=1)
        rb = B.swing_profile(o, h, l, c, v, swing_len=3, atr_len=1)
        assert not identical(ra, rb), explain(ra, rb, identical(ra, rb))
        assert (ra["hs_bar"][8], ra["ls_bar"][8], ra["f_lo"][8], ra["f_hi"][8]) == (2, 7, 7.0, 10.0)
        assert math.isnan(ra["f_poc"][8]) and math.isnan(ra["f_total"][8]) and ra["f_poc_ties"][8] == 0
        assert np.isfinite(ra["f_poc"][9:]).all()                          # the run goes on: bar 9 has ATR 1.125
        leg = ra["legs"][ra["legs"]["flip_bar"] == 9].iloc[0]
        assert leg["atr_at_flip"] == 1.125 and leg["poc_all"] == ((7.0 + (7.0 + 0.6)) / 2,)
    # the limit itself: a leg 0 .. 100,000 with bins of 1.0 has 100,000 bins (computed), 0 .. 100,001 has 100,001
    closes, vols = [50_000.25, 99_999.75], [1.0, 2.0]
    for hi, size, ok in ((100_000.0, 1.0, True), (100_001.0, 1.0, False), (100_000.999, 1.0, True),
                         (100_000.0, 5e-324, False)):
        pa = A.leg_profile(closes, closes, vols, 1, hi, 0, 0.0, size, 99_999.75)
        pb = B.leg_profile(closes, closes, vols, 1, 1, hi, 0, 0.0, size)
        assert pb.ok == ok and (pa["n_bins"] > 0) == ok, (hi, size)
        if ok:
            assert pa["n_bins"] == pb.bin_count == 100_000 and pa["poc_all"] == pb.tied
            assert pa["poc"] == B.nearest(pb.tied, 99_999.75) and pa["total"] == pb.total and pa["delta_pct"] == pb.delta
        else:
            assert pb.bin_count > B.PINE_ARRAY_MAX and math.isnan(pa["poc"]) and math.isnan(pa["total"])
    assert A.PINE_ARRAY_MAX == B.PINE_ARRAY_MAX == 100_000


def test_contract_constants_and_dtypes_alike():
    """The second difference was the contract's, not Pine's: ``f_dir`` and ``legs.dir`` were int8 in port A and int64
    in port B. Both are int8 now, the type of every direction code of the study (the ribbon's trend and flip, the Heikin
    Ashi direction, the ORB's active direction, the coil's breakout, the dashboard's label). Port B's ``KEYS`` lists
    the 13 per-bar keys, port A's the 14 returned keys; the returned dicts have the same keys in the same order."""
    assert B.KEYS + ("legs",) == A.KEYS and B.LEG_COLUMNS == A.LEG_COLUMNS
    o, h, l, c, v = _cols(TINY)
    for n in (0, 1, 3, 9, 14):
        ra = A.swing_profile(o[:n], h[:n], l[:n], c[:n], v[:n], swing_len=3, atr_len=1)
        rb = B.swing_profile(o[:n], h[:n], l[:n], c[:n], v[:n], swing_len=3, atr_len=1)
        assert not identical(ra, rb), (n, explain(ra, rb, identical(ra, rb)))
    assert ra["f_dir"].dtype == rb["f_dir"].dtype == np.int8
    assert ra["legs"]["dir"].dtype == rb["legs"]["dir"].dtype == np.int8 and len(ra["legs"]) == 4


# ───────────────────────────── 3. synthetic bars ─────────────────────────────

def synthetic(rng, n, kind, volume):
    """Random bars: a heavy-tailed walk, a walk on a 0.5 grid (equal highs, closes on bin edges and midpoints, ties),
    trending stretches, or a mostly flat walk without wicks (true ranges of 0, an ATR that decays towards 0); a few
    outside bars that are both window extremes; some dojis. Volume: integer ticks, Binance-like decimals with empty
    hours, or gamma-distributed."""
    if kind == "walk":
        c = 1000.0 + np.cumsum(rng.standard_t(4, n) * 2.0)
    elif kind == "grid":
        c = np.round((1000.0 + np.cumsum(rng.normal(0, 2, n))) / 0.5) * 0.5
    elif kind == "trend":
        c = 1000.0 + np.cumsum(rng.normal(0, 1, n) + 0.8 * np.sign(np.sin(np.arange(n) / rng.uniform(5, 40))))
    else:
        c = 1000.0 + np.cumsum(rng.normal(0, 1, n) * (rng.random(n) < 0.2))
    o = np.r_[c[0], c[:-1]] + (0.0 if kind == "flat" else rng.normal(0, 0.3, n))
    wick = 0.0 if kind == "flat" else 1.0
    h = np.maximum(o, c) + wick * rng.exponential(1.0, n)
    l = np.minimum(o, c) - wick * rng.exponential(1.0, n)
    if kind == "grid":
        o, h, l = (np.round(x / 0.5) * 0.5 for x in (o, h, l))
    outside = rng.random(n) < 0.005
    h[outside] += 25.0
    l[outside] -= 25.0
    dj = rng.random(n) < 0.05
    c[dj] = o[dj]
    h, l = np.maximum(h, np.maximum(o, c)), np.minimum(l, np.minimum(o, c))
    if volume == "ticks":
        v = rng.integers(1, 50, n).astype(np.float64)
    elif volume == "binance":
        v = np.round(rng.lognormal(3.0, 1.0, n), 8)
        v[rng.random(n) < 0.02] = 0.0
    else:
        v = rng.gamma(2.0, 123.456, n)
    return o, h, l, c, v


@pytest.mark.parametrize("seed", range(6))
def test_random_inputs_bit_for_bit(seed):
    """Random lengths (swing 2-60, the script's minimum of 10 not enforced by either port; ATR 1-80), bin multipliers
    (0.05-2), kinds and volumes."""
    rng = np.random.default_rng(2000 + seed)
    legs = ties = 0
    for case in range(6):
        kind = str(rng.choice(["walk", "grid", "trend", "flat"]))
        volume = str(rng.choice(["ticks", "binance", "gamma"]))
        n = int(rng.choice([300, 700]))
        kw = dict(swing_len=int(rng.integers(2, 61)), atr_len=int(rng.integers(1, 81)),
                  bin_mult=float(rng.choice([0.05, 0.1, 0.25, 0.5, 1.0, 2.0])))
        bars_ = synthetic(rng, n, kind, volume)
        ra, rb = A.swing_profile(*bars_, **kw), B.swing_profile(*bars_, **kw)
        bad = identical(ra, rb)
        assert not bad, (seed, case, kind, volume, kw, explain(ra, rb, bad))
        legs += len(ra["legs"])
        ties += int((ra["f_poc_ties"] > 1).sum())
    assert legs > 30 and ties > 0


@pytest.mark.parametrize("kind", ["walk", "grid", "flat"])
def test_defaults_and_short_series_bit_for_bit(kind):
    """The script's defaults on 1,200 bars, and the same bars cut to 0-260 bars (the warm-up of ta.highest(50) and
    ta.atr(200))."""
    bars_ = synthetic(np.random.default_rng(77), 1200, kind, "binance")
    ra, rb = A.swing_profile(*bars_), B.swing_profile(*bars_)
    assert not identical(ra, rb), (kind, explain(ra, rb, identical(ra, rb)))
    assert len(ra["legs"]) >= 5
    for n in (0, 1, 2, 48, 49, 50, 51, 198, 199, 200, 260):
        cut = tuple(x[:n] for x in bars_)
        x, y = A.swing_profile(*cut), B.swing_profile(*cut)
        assert not identical(x, y), (kind, n, explain(x, y, identical(x, y)))


def test_degenerate_inputs_bit_for_bit():
    """Flat bars (every true range 0: no bin size), zero volume everywhere (bins without volume: no POC, total 0),
    swing lengths 1 and 2 (a bar is always its own 1-bar extreme; confirmations need a strictly lower high), a tiny
    bin multiplier (every leg beyond Pine's array limit), and the way real-looking bars reach that limit: an ATR(3)
    decaying by 2/3 a bar on a long flat stretch (the bin count passes 100,000 and keeps growing; 229 bars beyond the
    limit, 5 with 10,000-100,000 bins)."""
    rng = np.random.default_rng(5)
    o, h, l, c, v = synthetic(rng, 400, "walk", "ticks")
    flat = np.full(300, 100.0)
    tail = np.r_[c[:150], np.full(250, c[149])]
    decay = (np.r_[o[:150], tail[150:]], np.r_[h[:150], tail[150:]], np.r_[l[:150], tail[150:]], tail, v)
    cases = [
        ((flat, flat, flat, flat, np.ones(300)), dict(swing_len=10, atr_len=14)),
        ((o, h, l, c, np.zeros(len(c))), dict(swing_len=10, atr_len=14)),
        ((o, h, l, c, v), dict(swing_len=1, atr_len=1)),
        ((o, h, l, c, v), dict(swing_len=2, atr_len=1)),
        ((o, h, l, c, v), dict(swing_len=10, atr_len=14, bin_mult=1e-5)),
        (decay, dict(swing_len=10, atr_len=3)),
    ]
    for bars_, kw in cases:
        ra, rb = A.swing_profile(*bars_, **kw), B.swing_profile(*bars_, **kw)
        assert not identical(ra, rb), (kw, explain(ra, rb, identical(ra, rb)))
    r = A.swing_profile(*decay, swing_len=10, atr_len=3)
    with np.errstate(invalid="ignore", divide="ignore"):
        nb = np.floor(np.abs(r["hs_price"] - r["ls_price"]) / (I.atr(decay[1], decay[2], decay[3], 3) * 0.5))
    beyond = nb > A.PINE_ARRAY_MAX
    assert beyond.sum() == 229 and ((nb >= 1e4) & (nb <= 1e5)).sum() == 5
    assert np.isnan(r["f_poc"][beyond]).all() and (r["f_poc_ties"][beyond] == 0).all()


def test_the_two_ports_refuse_bad_inputs_alike():
    """Unequal lengths, a 2-D array, a non-finite price, a negative volume, a length below 1 or not an integer, a bin
    multiplier that is not positive: both raise ValueError."""
    o, h, l, c, v = synthetic(np.random.default_rng(9), 120, "walk", "ticks")
    bad_c = c.copy()
    bad_c[40] = math.nan
    for args, kw in (((o, h, l, c, v[:-1]), {}), ((o, h, l, bad_c, v), {}), ((o, h, np.vstack([l, l]), c, v), {}),
                     ((o, h, l, c, -v), {}), ((o, h, l, np.where(c > 0, np.inf, c), v), {}),
                     ((o, h, l, c, v), dict(swing_len=0)), ((o, h, l, c, v), dict(atr_len=2.5)),
                     ((o, h, l, c, v), dict(bin_mult=0.0)), ((o, h, l, c, v), dict(bin_mult=math.nan)),
                     ((o, h, l, c, v), dict(swing_len=True))):
        with pytest.raises(ValueError):
            A.swing_profile(*args, **kw)
        with pytest.raises(ValueError):
            B.swing_profile(*args, **kw)
