"""
The coil breakout (COIL; study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.9): the reconciliation of its
two independent ports. The notes for readers are ``backtest_results/tradeiq_2027/porting/coil.md``.

* Port A, ``backtesting/research/tradeiq2_ind_coil.py``: the production port (numpy and one numba loop); its own tests
  are ``test_tradeiq2_ind_coil_a.py``.
* Port B, ``tests/tradeiq2_oracle_coil.py``: the oracle, a bar-by-bar transcription in plain Python; its own tests are
  ``test_tradeiq2_ind_coil_b.py``.

There is no Pine source: TradeIQ's Coil Breakout AI is private (PREREG l.18-19, 26), so the rule is the study's own,
PREREG 6.9 (l.434-465) made precise by the contract both ports were given. Its Pine parts are TradingView's
documented built-ins: ``ta.sma``, ``ta.stdev``, ``ta.atr`` (``ta.rma`` of ``ta.tr(true)``), ``ta.change``, ``fixnan``
and, for ``ta.dmi``, the built-in "Directional Movement Index" script. There is no third port (no planning pass
ported the coil).

1. Real bars (skipped when the tick store is absent). XAUUSDm and BTCUSDm, 1H / 4H / 1D (PREREG 6.9's timeframes),
   from the study's data start (``tradeiq2_market.data_start``: gold 2016-01-01 when all twelve 2016 months are in the
   store, BTC 2018-01-01) to 2024-06-30: ``tradeiq2_market.load(symbol, end="2024-07-01")`` with study 1's and study
   2's guards pointed at an empty folder, so nothing at or after the hold-out start is read; its 1H / 4H / 1D bars are
   study 1's ``TMarket.tbars``. Gold is also run from 2017-01-03 (study 1's start, the bars both ports' authors
   measured on; a suffix of the same bars). Asserted:
   - every key of the contract, in the same order and dtype: floats bit for bit (``numpy.array_equal`` with NaN in
     the same places, and the same 64 bits wherever there is a number), bool, int64 and int8 exactly. No tolerance
     and no alignment were needed: both ports follow the reference code's order of operations (``pine_sma`` and
     ``pine_stdev`` summed from the newest bar, ``pine_rma``'s ``alpha * x + (1 - alpha) * prev`` after its SMA seed,
     the band sums formed and then compared, the DMI script's statements left to right);
   - the event tables: one row per breakout (bar, open and close time, side, close, box, ADX, its armed-bar number,
     whether it is a squeeze bar) and one per coil (first and last armed bar, its run's length, its box, how it
     ended: breakout, expiry after 12 armed bars, replacement, or the data end);
   - the Development counts (the harness's decision bars: closing after 2019-01-01 00:00, filled before 2023-01-01
     00:00, ``tradeiq_market.run``'s rule) equal to the values recorded at the reconciliation, for both ports. Counts
     only: no rule is run and no profit or loss is computed;
   - no event sits within rounding of its threshold from 2019 (the squeeze margin, the close against the box, the ADX
     of a breakout bar against 20), so no order of the float operations, here or in TradingView's native code, could
     move an event;
   - gold from 2016 and from 2017 gives the same values on every bar closing from 2019 but for the last bit of a few
     1D ADX values (the tolerance and its reason are in that test).
2. Every hand-made input of each port's own tests run through the other port: the functions those tests call are
   wrapped for the duration of the test, run in both ports and compared bit for bit (``coil``, ``adx``, ``ta.dmi``,
   the bands, the coil machine on a given squeeze series).
3. Synthetic bars with random inputs (lengths from 1, multipliers from 0, min_bars and armed_bars from 1), short
   series, flat and constant markets, and the coil machines on random squeeze series: bit for bit.
4. The contract outside the values: keys, signatures and defaults, dtypes, the inputs both refuse, inputs left alone.

Run with NUMBA_CACHE_DIR set (port A's machine and study 1's harness compile with ``cache=True``).
"""

from __future__ import annotations

import functools
import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import tradeiq2_ind_coil as A
from backtesting.research import tradeiq2_market as TM2
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_coil as B  # noqa: E402
import test_tradeiq2_ind_coil_a as TA  # noqa: E402  (port A's own tests: their hand cases and bar generators)
import test_tradeiq2_ind_coil_b as TB  # noqa: E402  (port B's own tests: likewise)

SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")                                       # PREREG 6.9
DTYPES = {"squeeze_on": np.bool_, "run_len": np.int64, "armed": np.bool_, "box_hi": np.float64,
          "box_lo": np.float64, "breakout": np.int8, "bo_box_hi": np.float64, "bo_box_lo": np.float64,
          "adx": np.float64}
DEV = ("2019-01-01", "2023-01-01")                             # PREREG 3: Development
STUDY1_GOLD_START = "2017-01-01"                               # study 1's gold bars begin on 2017-01-03
END_CODES = {"B": 0, "E": 1, "R": 2, "D": 3}                   # how a coil ended (coil_table)

# Recorded at the reconciliation (28 Nov 2026) on the study's bars, both ports equal. Per symbol and timeframe, over
# the Development decision bars: bars, squeeze bars, coils armed (counted at their first armed bar), of which ended
# by a breakout / expired after 12 armed bars / replaced by a newer run reaching 6 bars; long and short breakouts;
# breakouts on armed bar 1 and on armed bar 12; breakouts on a squeeze bar of a newer, shorter run; breakouts with
# ADX >= 20.
_RECORDED = {
    ("XAUUSDm", "1H"): (23590, 6982, 430, 338, 69, 23, 193, 145, 187, 7, 11, 188),
    ("XAUUSDm", "4H"): (6385, 1634, 91, 75, 12, 4, 47, 28, 25, 1, 1, 46),
    ("XAUUSDm", "1D"): (1031, 290, 16, 15, 1, 0, 8, 7, 8, 0, 0, 7),
    ("BTCUSDm", "1H"): (35016, 14324, 707, 521, 122, 64, 275, 246, 289, 12, 19, 332),
    ("BTCUSDm", "4H"): (8756, 2914, 161, 129, 26, 6, 72, 57, 72, 3, 6, 81),
    ("BTCUSDm", "1D"): (1459, 484, 27, 23, 2, 2, 14, 9, 11, 1, 2, 16),
}


# ───────────────────────────── comparison helpers ─────────────────────────────

def same_floats(a, b) -> bool:
    """Bit for bit: NaN in the same places (``numpy.array_equal(equal_nan=True)``) and the same 64 bits wherever
    there is a number (which also tells 0.0 from -0.0)."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype != np.float64 or b.dtype != np.float64 or a.shape != b.shape:
        return False
    na = np.isnan(a)
    return bool(np.array_equal(a, b, equal_nan=True) and np.array_equal(na, np.isnan(b))
                and np.array_equal(a[~na].view(np.int64), b[~na].view(np.int64)))


def identical(x, y, keys=A.KEYS) -> list:
    """The keys on which two outputs of the contract differ (empty: identical): the same keys in the same order, each
    of the contract's dtype and the same shape; floats bit for bit (``same_floats``), the others exactly."""
    if tuple(x) != tuple(keys) or tuple(y) != tuple(keys):
        return ["keys"]
    bad = []
    for k in keys:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if a.dtype != DTYPES[k] or b.dtype != DTYPES[k] or a.shape != b.shape:
            bad.append(k)
        elif a.dtype.kind == "f":
            if not same_floats(a, b):
                bad.append(k)
        elif not np.array_equal(a, b):
            bad.append(k)
    return bad


def first_differences(x, y, k, n=3):
    a, b = np.asarray(x[k]), np.asarray(y[k])
    if a.shape != b.shape:
        return [("shape", a.shape, b.shape)]
    if a.dtype.kind == "f":
        i = np.flatnonzero((a.view(np.int64) != b.view(np.int64)) & ~(np.isnan(a) & np.isnan(b)))
    else:
        i = np.flatnonzero(a != b)
    return [(int(j), a[j].item(), b[j].item()) for j in i[:n]]


def assert_identical(x, y, what):
    bad = identical(x, y)
    assert not bad, (what, bad, {k: first_differences(x, y, k) for k in bad if k != "keys"})


def armed_number(r) -> np.ndarray:
    """Per bar: its number in the armed window of its coil (1 = the first armed bar), 0 where nothing is armed."""
    a = r["armed"]
    first = np.flatnonzero(a & ~np.r_[False, a[:-1]])
    out = np.zeros(len(a), np.int64)
    ix = np.flatnonzero(a)
    if len(ix):
        out[ix] = ix - first[np.searchsorted(first, ix, side="right") - 1] + 1
    return out


def coil_table(r) -> dict:
    """One row per coil: its first and last armed bar, its run's length (the run ends on the bar before the first
    armed bar), its box, and how it ended: 0 breakout, 1 expiry after 12 armed bars, 2 replacement (a newer run
    reaches 6 bars on the next bar), 3 the data end. Two coils' armed stretches never touch (a coil arms only after a
    newer run has reached 6 bars on a bar that is armed for nobody), which ``test_real_bars_event_tables_are_identical``
    checks."""
    a, bo, rl = r["armed"], r["breakout"], r["run_len"]
    n = len(a)
    first = np.flatnonzero(a & ~np.r_[False, a[:-1]])
    last = np.flatnonzero(a & ~np.r_[a[1:], False])
    length = last - first + 1
    end = np.where(bo[last] != 0, END_CODES["B"], np.where(length == 12, END_CODES["E"],
                                                           np.where(last == n - 1, END_CODES["D"], END_CODES["R"])))
    return {"first": first, "last": last, "run": rl[first - 1].astype(np.int64), "box_hi": r["box_hi"][first],
            "box_lo": r["box_lo"][first], "end": end.astype(np.int64)}


def breakout_table(r, t, tc, c) -> dict:
    """One row per breakout: bar, open and close time, side, close, the broken box, the ADX, its armed-bar number and
    whether it is a squeeze bar (a bar of a newer, shorter run)."""
    bo = r["breakout"]
    ix = np.flatnonzero(bo)
    return {"bar": ix, "t": t[ix], "tc": tc[ix], "side": bo[ix].astype(np.int64), "close": c[ix],
            "box_hi": r["bo_box_hi"][ix], "box_lo": r["bo_box_lo"][ix], "adx": r["adx"][ix],
            "armed_bar": armed_number(r)[ix], "on_squeeze": r["squeeze_on"][ix]}


def same_table(x, y) -> list:
    """The columns on which two event tables differ (floats bit for bit)."""
    if list(x) != list(y):
        return ["columns"]
    return [k for k in x if not (same_floats(x[k], y[k]) if np.asarray(x[k]).dtype.kind == "f"
                                 else (np.asarray(x[k]).dtype == np.asarray(y[k]).dtype
                                       and np.array_equal(x[k], y[k])))]


def counts(r, dev) -> tuple:
    """The recorded tuple for one output (see ``_RECORDED``)."""
    ct = coil_table(r)
    inw = dev[ct["first"]]
    bo = r["breakout"]
    hit = (bo != 0) & dev
    k = armed_number(r)
    return (int(dev.sum()), int((r["squeeze_on"] & dev).sum()), int(inw.sum()),
            int((inw & (ct["end"] == END_CODES["B"])).sum()), int((inw & (ct["end"] == END_CODES["E"])).sum()),
            int((inw & (ct["end"] == END_CODES["R"])).sum()),
            int(((bo == 1) & dev).sum()), int(((bo == -1) & dev).sum()),
            int((hit & (k == 1)).sum()), int((hit & (k == 12)).sum()), int((hit & r["squeeze_on"]).sum()),
            int((hit & (r["adx"] >= 20.0)).sum()))


# ───────────────────────────── 1. the real bars (to 2024-06-30, the guards closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol: for 1H / 4H / 1D the bars (open and close times, OHLC, the Development decision mask) and both
    ports' outputs, from the study's data start; for gold also from study 1's start. The M1 bars are released as soon
    as the bars are built, so one symbol's M1 bars are in memory at a time (this file peaks at about 1 GB)."""
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
            mk = TM2.load(symbol, end="2024-07-01")
            assert int(mk.t[-1]) + 60 <= TM.CUT_S                          # nothing from the hold-out is in memory
            m1_first = int(mk.t[0])
            iz = int(np.searchsorted(mk.t, TM.s_of(DEV[1]), side="left"))  # the harness's window end (_window_ix)
            out = {}
            for tf in TFS:
                b = mk.tbars(tf)
                dev = (b.tc > TM.s_of(DEV[0])) & (b.ex < iz)                # tradeiq_market.run's decision bars
                out[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(), c=b.c.copy(),
                             dev=dev)
            del mk
        for tf, b in out.items():
            b.a = A.coil(b.o, b.h, b.l, b.c)
            b.b = B.coil(b.o, b.h, b.l, b.c)
            if symbol == "XAUUSDm":                                          # study 1's start: a suffix of the bars
                k = int(np.searchsorted(b.t, TM.s_of(STUDY1_GOLD_START)))
                b.k1 = k
                b.a1 = A.coil(b.o[k:], b.h[k:], b.l[k:], b.c[k:])
                b.b1 = B.coil(b.o[k:], b.h[k:], b.l[k:], b.c[k:])
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


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_every_key_bit_for_bit(symbol, real):
    data = real(symbol)
    for tf, b in data.bars.items():
        assert_identical(b.a, b.b, (symbol, tf))
        assert (b.a["breakout"] != 0).sum() > 20 and b.a["squeeze_on"].sum() > 300, (symbol, tf)
        if symbol == "XAUUSDm":
            assert_identical(b.a1, b.b1, (symbol, tf, "from 2017"))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_event_tables_are_identical(symbol, real):
    """The breakout and coil tables of the two ports are identical, and they have the structure the contract
    describes (checked on port A's, which is the same)."""
    data = real(symbol)
    for tf, b in data.bars.items():
        ta, tb = breakout_table(b.a, b.t, b.tc, b.c), breakout_table(b.b, b.t, b.tc, b.c)
        assert not same_table(ta, tb), (symbol, tf, same_table(ta, tb))
        ca, cb = coil_table(b.a), coil_table(b.b)
        assert not same_table(ca, cb), (symbol, tf, same_table(ca, cb))
        # the tables' structure: every coil arms on the bar after a run of >= 6 squeeze bars, whose highs and lows
        # make its box, keeps that box on all its armed bars, ends as its code says, and the stretches never touch
        r = b.a
        assert np.all(ca["first"][1:] > ca["last"][:-1] + 1)
        assert np.array_equal(ca["first"], np.flatnonzero((r["run_len"][:-1] >= 6) & ~r["squeeze_on"][1:]) + 1)
        for s, e, run, hi, lo, end in zip(ca["first"], ca["last"], ca["run"], ca["box_hi"], ca["box_lo"], ca["end"]):
            assert run >= 6 and hi == b.h[s - run:s].max() and lo == b.l[s - run:s].min(), (tf, s)
            assert np.all(r["box_hi"][s:e + 1] == hi) and np.all(r["box_lo"][s:e + 1] == lo), (tf, s)
            assert e - s + 1 <= 12 and (r["breakout"][s:e] == 0).all(), (tf, s)
            if end == END_CODES["R"]:
                assert r["run_len"][e + 1] == 6, (tf, s)
        assert np.array_equal(np.sort(ta["bar"]), ta["bar"]) and len(ta["bar"]) == (ca["end"] == END_CODES["B"]).sum()
        assert np.all(np.where(ta["side"] == 1, ta["close"] > ta["box_hi"], ta["close"] < ta["box_lo"]))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_recorded_development_counts(symbol, real):
    """Development counts recorded at the reconciliation: a guard against either port changing (counts, no P/L)."""
    data = real(symbol)
    for tf, b in data.bars.items():
        want = _RECORDED[(symbol, tf)]
        assert counts(b.a, b.dev) == want, (symbol, tf, counts(b.a, b.dev))
        assert counts(b.b, b.dev) == want, (symbol, tf, counts(b.b, b.dev))


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_no_event_sits_within_rounding_of_its_threshold(symbol, real):
    """From 2019 to 2024-06-30, on every series:

    * the Bollinger bands never come closer to the Keltner channel than 1e-6 ATR(20) or 5e-8 of the price (measured
      at the reconciliation: at least 4.0e-6 ATR and 1.0e-7 of the price, both on BTC 1D), while a different order of
      the float operations moves the bands by about 1e-16 of the price: no order of operations can move a squeeze
      bar, and no band touches the channel exactly, so the strict ``<`` / ``>`` of the squeeze never matters;
    * no armed bar closes exactly at its box's edge, so the strict ``>`` / ``<`` of the breakout never matters (the
      comparison has no arithmetic in it: only an exact tie could). Two such ties exist before 2019 on gold (1H on
      2017-08-14 10:00 and 4H on 2018-09-04 16:00 close times), in the gold Early window;
    * the ADX of a breakout bar is never within 1e-3 of the grade's 20 (measured: at least 0.0014, BTC 1H), while the
      readings of ``ta.dmi`` that are equal in exact arithmetic differ by less than 1e-13: no grade can flip."""
    data = real(symbol)
    for tf, b in data.bars.items():
        f = b.tc > TM.s_of(DEV[0])
        up, lo, kup, klo = A._bands(b.h, b.l, b.c, 20, 2.0, 20, 1.5)
        atr20 = I.atr(b.h, b.l, b.c, 20)
        margin = np.minimum(np.abs(kup - up), np.abs(lo - klo))[f]
        assert np.min(margin / atr20[f]) > 1e-6 and np.min(margin / b.c[f]) > 5e-8, (symbol, tf)
        assert not ((up == kup) | (lo == klo)).any(), (symbol, tf)
        r = b.a
        armed = r["armed"] & f
        assert not ((b.c == r["box_hi"]) | (b.c == r["box_lo"]))[armed].any(), (symbol, tf)
        hit = (r["breakout"] != 0) & f
        assert np.min(np.abs(r["adx"][hit] - 20.0)) > 1e-3, (symbol, tf)


def test_real_bars_gold_from_2016_or_2017_is_the_same_from_2019(real):
    """The study's gold bars start on 2016-01-03, study 1's (which both ports' authors measured on) on 2017-01-03.
    On every bar closing from 2019 the two starts give the same squeeze, runs, coils, boxes and breakouts on all three
    timeframes, and the same ADX bit for bit on 1H and 4H. On 1D the ADX keeps a trace of its start in its last bit on
    a few bars (10 at the reconciliation, 3.9e-16 relative): the RMA forgets its start as (13/14)^n, and 520 daily
    bars are not quite enough for that to fall below the last bit. So the 1D ADX is compared within 1e-12 relative
    (the only tolerance in this file; it compares two starts, not two ports), and the ADX >= 20 grade must be the same
    on every bar. In 2017 the starts do differ: the later start's ADX is still warming up (the grade differs on some
    bars), which is why the study warms gold up from 2016 for its Early window."""
    data = real("XAUUSDm")
    for tf, b in data.bars.items():
        k = b.k1
        assert int(b.t[k]) >= TM.s_of(STUDY1_GOLD_START) and int(b.t[k - 1]) < TM.s_of(STUDY1_GOLD_START)
        f = b.tc[k:] > TM.s_of(DEV[0])
        assert b.dev[k:].sum() == b.dev.sum() and not b.dev[:k].any()
        tail = {key: v[k:][f] for key, v in b.a.items()}
        later = {key: v[f] for key, v in b.a1.items()}
        bad = identical(tail, later)
        if tf == "1D":
            assert bad in ([], ["adx"]), (tf, bad)
            x, y = tail["adx"], later["adx"]
            assert np.array_equal(np.isnan(x), np.isnan(y)) and np.isfinite(x).all()
            assert np.max(np.abs(x - y) / np.abs(x)) < 1e-12, tf
        else:
            assert not bad, (tf, bad)
        assert np.array_equal(tail["adx"] >= 20.0, later["adx"] >= 20.0), tf
        y2017 = b.tc[k:] <= TM.s_of("2018-01-01")          # the later start: no ADX on its first 27 bars, then warming
        assert np.any((b.a["adx"][k:] >= 20.0)[y2017] != (b.a1["adx"] >= 20.0)[y2017]), tf


# ───────────────────────────── 2. each port's hand-made inputs through the other port ─────────────────────────────

def _bind(fn, args, kwargs):
    ba = inspect.signature(fn).bind(*args, **kwargs)
    ba.apply_defaults()
    return ba.arguments


def _f64(x):
    return np.ascontiguousarray(np.asarray(x, dtype=np.float64))


class Spies:
    """Wraps the functions a port's own tests call, so that each call runs in both ports and is compared bit for bit.
    Only the outermost call is compared (a wrapped function calling another wrapped one is not compared twice). A
    call that raises is passed on unchanged (the inputs both ports refuse are tested in section 4)."""

    def __init__(self):
        self.depth = 0
        self.compared = []

    def wrap(self, fn, check):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            self.depth += 1
            try:
                out = fn(*args, **kwargs)
            finally:
                self.depth -= 1
            if self.depth == 0:
                check(out, args, kwargs)
                self.compared.append(fn.__name__)
            return out
        return wrapper


def _check_coil_in_b(out, args, kwargs):
    assert_identical(out, B.coil(*args, **kwargs), "port A's coil call in port B")


def _check_adx_in_b(out, args, kwargs):
    assert same_floats(out, B.adx(*args, **kwargs)), "port A's adx call in port B"


def _check_dmi_in_b(out, args, kwargs):
    a = _bind(A._dmi, args, kwargs)
    ref = B.dmi(a["h"], a["l"], a["c"], a["di_len"], a["adx_len"])
    assert all(same_floats(x, y) for x, y in zip(out, ref)), "port A's _dmi call in port B"


def _check_bands_in_b(out, args, kwargs):
    a = _bind(A._bands, args, kwargs)
    ln = B.squeeze_lines(a["h"], a["l"], a["c"], a["bb_len"], a["bb_mult"], a["kc_len"], a["kc_mult"])
    ref = (ln["upper_bb"], ln["lower_bb"], ln["upper_kc"], ln["lower_kc"])
    assert all(same_floats(x, y) for x, y in zip(out, ref)), "port A's _bands call in port B"
    assert np.array_equal(A._squeeze(*out), ln["squeeze_on"])


def _check_coil_in_a(out, args, kwargs):
    assert_identical(A.coil(*args, **kwargs), out, "port B's coil call in port A")


def _check_adx_in_a(out, args, kwargs):
    assert same_floats(A.adx(*args, **kwargs), out), "port B's adx call in port A"


def _check_dmi_in_a(out, args, kwargs):
    a = _bind(B.dmi, args, kwargs)
    mine = A._dmi(_f64(a["h"]), _f64(a["l"]), _f64(a["c"]), int(a["di_len"]), int(a["adx_len"]))
    assert all(same_floats(x, y) for x, y in zip(mine, out)), "port B's dmi call in port A"


def _check_lines_in_a(out, args, kwargs):
    a = _bind(B.squeeze_lines, args, kwargs)
    mine = A._bands(_f64(a["h"]), _f64(a["l"]), _f64(a["c"]), int(a["bb_len"]), float(a["bb_mult"]),
                    int(a["kc_len"]), float(a["kc_mult"]))
    ref = (out["upper_bb"], out["lower_bb"], out["upper_kc"], out["lower_kc"])
    assert all(same_floats(x, y) for x, y in zip(mine, ref)), "port B's squeeze_lines call in port A"
    assert np.array_equal(A._squeeze(*mine), out["squeeze_on"])


def _check_machine_in_a(out, args, kwargs):
    """``coil_from_squeeze`` (port B's coil logic on a given squeeze series) against port A's ``_machine``."""
    a = _bind(B.coil_from_squeeze, args, kwargs)
    sq = np.asarray(a["squeeze_on"]).astype(np.bool_)
    mine = A._machine(sq, _f64(a["h"]), _f64(a["l"]), _f64(a["c"]), np.int64(int(float(a["min_bars"]))),
                      np.int64(int(float(a["armed_bars"]))))
    keys = ("run_len", "armed", "box_hi", "box_lo", "breakout", "bo_box_hi", "bo_box_lo")
    assert np.array_equal(out["squeeze_on"], sq)
    assert not identical(dict(zip(keys, mine)), {k: out[k] for k in keys}, keys), "port B's machine call in port A"


def _hand_tests(module, prefixes, extra=()):
    """The module's non-parametrized tests whose names start with one of ``prefixes`` (or are in ``extra``) and that
    take no fixture: the hand-made cases, not the random or real-bar ones."""
    names = []
    for name, fn in vars(module).items():
        if not callable(fn) or not (name.startswith(prefixes) or name in extra):
            continue
        if getattr(fn, "pytestmark", None) or inspect.signature(fn).parameters:
            continue
        names.append(name)
    return sorted(names)


A_HAND = _hand_tests(TA, ("test_trap", "test_reading"),
                     ("test_output_keys_dtypes_and_inputs", "test_port_equals_the_transcription_on_the_hand_cases",
                      "test_truncation_invariance_on_a_coil_sequence_at_every_bar"))
B_HAND = _hand_tests(TB, ("test_trap",), ("test_contract_keys_dtypes_and_signature",
                                          "test_inputs_refused_and_left_alone"))


def test_the_hand_case_lists_are_complete():
    """Every trap test of both ports' files is replayed (19 + 1 + 3 of port A's, 25 + 2 of port B's at the
    reconciliation); a renamed or new trap is picked up by its name."""
    assert len(A_HAND) >= 23 and sum(n.startswith("test_trap") for n in A_HAND) >= 19, A_HAND
    assert len(B_HAND) >= 27 and sum(n.startswith("test_trap") for n in B_HAND) >= 25, B_HAND


@pytest.mark.parametrize("name", A_HAND)
def test_port_a_hand_cases_give_the_same_values_in_port_b(name, monkeypatch):
    """Port A's test ``name`` runs as written (its own assertions included), while each of its calls to ``coil``,
    ``adx``, ``_dmi`` and ``_bands`` is also made in port B and compared bit for bit."""
    spies = Spies()
    for attr, check in (("coil", _check_coil_in_b), ("adx", _check_adx_in_b), ("_dmi", _check_dmi_in_b),
                        ("_bands", _check_bands_in_b)):
        monkeypatch.setattr(A, attr, spies.wrap(getattr(A, attr), check))
    getattr(TA, name)()
    assert spies.compared, name


@pytest.mark.parametrize("name", B_HAND)
def test_port_b_hand_cases_give_the_same_values_in_port_a(name, monkeypatch):
    """Port B's test ``name`` runs as written, while each of its calls to ``coil``, ``adx``, ``dmi``,
    ``squeeze_lines`` and ``coil_from_squeeze`` is also made in port A (``coil_from_squeeze`` against ``_machine``)
    and compared bit for bit."""
    spies = Spies()
    for attr, check in (("coil", _check_coil_in_a), ("adx", _check_adx_in_a), ("dmi", _check_dmi_in_a),
                        ("squeeze_lines", _check_lines_in_a), ("coil_from_squeeze", _check_machine_in_a)):
        monkeypatch.setattr(B, attr, spies.wrap(getattr(B, attr), check))
    getattr(TB, name)()
    assert spies.compared, name


# ───────────────────────────── 3. synthetic bars, random inputs, short series ─────────────────────────────

def synthetic(rng, n):
    """Random bars of one of seven kinds: port A's quiet / active regimes (some rounded) and its random coil
    sequences, port B's regime bars on a price grid, flat stretches with jumps (zero ranges: ATR and trur of 0),
    constant bars (a dead market, also at 1e16), market-like walks rounded like gold and BTC quotes, and port B's
    random squeeze series turned into bars."""
    m = max(n, 8)
    kind = int(rng.integers(0, 7))
    seed = int(rng.integers(0, 10 ** 6))
    if kind == 0:
        bars = TA.random_bars(m, seed, decimals=rng.choice([None, 0, 1, 2]))
    elif kind == 1:
        bars = TA.random_k1_bars(m, seed)
    elif kind == 2:
        p0, tick, scale = [(100.0, 0.25, 1.0), (1800.0, 0.5, 2.0), (30000.0, 5.0, 20.0), (1.0, 0.001, 0.01)][
            int(rng.integers(0, 4))]
        bars = TB.regime_bars(m, seed, p0=p0, tick=tick, scale=scale)
    elif kind == 3:
        c = np.repeat(100.0 + np.round(np.cumsum(rng.normal(0, 1, m // 7 + 1)), 1), 7)[:m]
        wick = (rng.random(m) < 0.3) * rng.uniform(0, 2, m)
        bars = (np.r_[c[:1], c[:-1]], c + np.round(wick, 1), c - np.round(wick * rng.random(m), 1), c)
    elif kind == 4:
        v, w = float(rng.choice([100.0, 1923.456, 1e16, 0.0])), float(rng.choice([0.0, 1.0]))
        c = np.full(m, v)
        bars = (c, c + w, c - w, c)
    elif kind == 5:
        p0 = float(rng.choice([1300.0, 30000.0]))
        c = np.round(p0 * np.exp(np.cumsum(rng.normal(0, 0.002, m) * (1 + 3 * (rng.random(m) < 0.1)))), 2)
        o = np.r_[c[:1], c[:-1]]
        bars = (o, np.round(np.maximum(o, c) + p0 * 0.001 * rng.exponential(1, m), 2),
                np.round(np.minimum(o, c) - p0 * 0.001 * rng.exponential(1, m), 2), c)
    else:
        _, h, l, c = TB.random_squeeze_input(m, seed)
        bars = (c, np.maximum(h, c), np.minimum(l, c), c)
    return tuple(np.asarray(x, np.float64)[:n] for x in bars)


def random_params(rng):
    r = rng.random()
    if r < 0.25:
        return {}
    if r < 0.4:
        return dict(bb_len=1, kc_len=1, min_bars=int(rng.integers(1, 8)), armed_bars=int(rng.integers(1, 14)))
    return dict(bb_len=int(rng.integers(1, 41)), bb_mult=float(rng.choice([0.0, 0.5, 1.0, 2.0, 2.5, rng.uniform(0, 3)])),
                kc_len=int(rng.integers(1, 41)), kc_mult=float(rng.choice([0.0, 1.0, 1.5, 2.0, rng.uniform(0, 3)])),
                min_bars=int(rng.integers(1, 12)), armed_bars=int(rng.integers(1, 25)))


@pytest.mark.parametrize("seed", range(6))
def test_random_bars_and_inputs_bit_for_bit(seed):
    """40 random cases per seed (25,000 more were run in scratch at the reconciliation, all equal)."""
    rng = np.random.default_rng(2026_11_28 + seed)
    breakouts = coils = 0
    for case in range(40):
        n = int(rng.choice([0, 1, 2, 5, 19, 20, 27, 28, 40, 60, 200, 800, 2500]))
        bars = synthetic(rng, n)
        kw = random_params(rng)
        ra, rb = A.coil(*bars, **kw), B.coil(*bars, **kw)
        assert_identical(ra, rb, (seed, case, n, kw))
        breakouts += int((ra["breakout"] != 0).sum())
        coils += int((ra["armed"] & ~np.r_[False, ra["armed"][:-1]]).sum())
        if n >= 40:
            di, ax = int(rng.integers(1, 30)), int(rng.integers(1, 30))
            assert same_floats(A.adx(*bars[1:], di, ax), B.adx(*bars[1:], di, ax)), (seed, case, di, ax)
    assert breakouts >= 15 and coils >= 40, (breakouts, coils)        # at the reconciliation: 23-136 and 59-423


@pytest.mark.parametrize("kw", [
    {},                                                                   # the plan's settings
    dict(bb_len=1, kc_len=1, min_bars=1, armed_bars=1),                   # every count at its lower bound
    dict(bb_mult=0.0), dict(kc_mult=0.0), dict(bb_mult=0.0, kc_mult=0.0),  # bands on the basis: no squeeze
    dict(bb_len=40, kc_len=7, min_bars=12, armed_bars=1),
    dict(bb_len=3, kc_len=40, kc_mult=3.0, min_bars=2, armed_bars=24),
])
def test_edge_inputs_and_short_series_bit_for_bit(kw):
    """Inputs at their bounds, on six random bar sets, whole and cut to the warm-up lengths."""
    rng = np.random.default_rng(77)
    for _ in range(6):
        o, h, l, c = synthetic(rng, 900)
        assert_identical(A.coil(o, h, l, c, **kw), B.coil(o, h, l, c, **kw), kw)
        for n in (0, 1, 2, 5, 13, 14, 18, 19, 20, 26, 27, 28, 40):          # the warm-up bars, cut short
            assert_identical(A.coil(o[:n], h[:n], l[:n], c[:n], **kw), B.coil(o[:n], h[:n], l[:n], c[:n], **kw),
                             (kw, n))


@pytest.mark.parametrize("seed", range(4))
def test_the_coil_machines_agree_on_random_squeeze_series(seed):
    """The two coil machines on squeeze series no real squeeze produces as easily: runs of 1-9 bars with gaps of 1-7
    (port B's generator), every min_bars / armed_bars from 1, runs open at the last bar, ties at the box edges."""
    rng = np.random.default_rng(500 + seed)
    for case in range(12):
        sq, h, l, c = TB.random_squeeze_input(int(rng.choice([7, 60, 600, 3000])), int(rng.integers(0, 10 ** 6)))
        if rng.random() < 0.5:
            sq[-int(rng.integers(1, 8)):] = True                              # a run still open at the last bar
        mb, ab = int(rng.integers(1, 10)), int(rng.integers(1, 16))
        out = B.coil_from_squeeze(sq, h, l, c, min_bars=mb, armed_bars=ab)
        _check_machine_in_a(out, (sq, h, l, c), dict(min_bars=mb, armed_bars=ab))


# ───────────────────────────── 4. the contract outside the values ─────────────────────────────

def test_the_contract_keys_signatures_and_defaults_are_the_same():
    assert A.KEYS == B.KEYS == tuple(DTYPES)
    for fa, fb in ((A.coil, B.coil), (A.adx, B.adx)):
        pa, pb = inspect.signature(fa).parameters, inspect.signature(fb).parameters
        assert list(pa) == list(pb), fa.__name__
        assert [p.default for p in pa.values()] == [p.default for p in pb.values()], fa.__name__
    assert [A.DEFAULTS[k] for k in ("bb_len", "bb_mult", "kc_len", "kc_mult", "min_bars", "armed_bars")] == \
        [p.default for p in inspect.signature(B.coil).parameters.values()][4:]
    o, h, l, c = synthetic(np.random.default_rng(3), 400)
    ra, rb = A.coil(o, h, l, c), B.coil(o, h, l, c)
    assert {k: v.dtype for k, v in ra.items()} == {k: v.dtype for k, v in rb.items()} == \
        {k: np.dtype(v) for k, v in DTYPES.items()}
    ea, eb = A.coil([], [], [], []), B.coil(*(np.zeros(0),) * 4)
    assert_identical(ea, eb, "empty")


def test_the_two_ports_refuse_the_same_inputs_and_leave_them_alone():
    """Both raise ValueError on the same bad bars and settings, accept the same integral floats and plain lists, and
    leave their inputs unchanged."""
    o, h, l, c = synthetic(np.random.default_rng(5), 120)
    keep = [x.copy() for x in (o, h, l, c)]
    A.coil(o, h, l, c)
    B.coil(o, h, l, c)
    A.adx(h, l, c)
    B.adx(h, l, c)
    assert all(np.array_equal(x, y) for x, y in zip((o, h, l, c), keep))
    bad = c.copy()
    bad[40] = math.nan
    bars_cases = ((o, h, l, c[:-1]), (o, h, l, bad), (np.where(o > 0, np.inf, o), h, l, c), (o, h, np.vstack([l, l]), c))
    for args in bars_cases:
        for port in (A, B):
            with pytest.raises(ValueError):
                port.coil(*args)
    for kw in (dict(bb_len=0), dict(kc_len=2.5), dict(min_bars=True), dict(armed_bars=0), dict(min_bars=-1),
               dict(bb_len=math.nan), dict(kc_mult=math.nan), dict(bb_mult=-1.0), dict(kc_mult=math.inf),
               dict(bb_mult=True)):
        for port in (A, B):
            with pytest.raises(ValueError):
                port.coil(o, h, l, c, **kw)
    for kw in (dict(di_len=0), dict(adx_len=1.5), dict(di_len=True)):
        for port in (A, B):
            with pytest.raises(ValueError):
                port.adx(h, l, c, **kw)
    for port in (A, B):
        with pytest.raises(ValueError):
            port.adx(h, l, np.r_[c[:-1], np.inf])
    # accepted alike: integral floats as lengths, plain lists as bars
    assert_identical(A.coil(o, h, l, c, bb_len=20.0, min_bars=6.0), B.coil(o, h, l, c, bb_len=20.0, min_bars=6.0),
                     "integral floats")
    assert_identical(A.coil(o.tolist(), h.tolist(), l.tolist(), c.tolist()), B.coil(o, h, l, c), "lists")
