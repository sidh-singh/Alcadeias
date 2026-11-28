"""
BOSWaves' Trend Target Ribbon (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` section 6.1): the reconciliation
of its two independent ports. The notes for readers are ``backtest_results/tradeiq_2027/porting/ribbon.md``.

* Port A, ``backtesting/research/tradeiq2_ind_ribbon.py``: the production port (numpy); its own tests are
  ``test_tradeiq2_ind_ribbon_a.py``.
* Port B, ``tests/tradeiq2_oracle_ribbon.py``: the oracle, a bar-by-bar transcription in plain Python; its own tests
  are ``test_tradeiq2_ind_ribbon_b.py``.

1. Real bars (skipped when the tick store is absent). XAUUSDm and BTCUSDm, 1H / 4H / 1D: the timeframes of PREREG
   6.1, which are also the series FR, STK, COIL-RIB and the Heikin Ashi bases read. From the study's data start
   (``tradeiq2_market.data_start``: gold 2016-01-01 when all twelve 2016 months are in the store, BTC 2018-01-01) to
   2024-06-30: the M1 bars come from ``external.load_market(symbol, earliest=..., end="2024-07-01")``, so nothing at
   or after the hold-out start is read, and study 1's ``TMarket.tbars`` builds them into bars (what
   ``tradeiq2_market.load`` serves on 1H / 4H / 1D), with study 1's and study 2's guards pointed at an empty folder.
   Gold is also run from 2017-01-03 (study 1's start; those bars are a suffix of the same bars), because the
   literal stop depends on where the bars start. Asserted:
   - every key of the contract, in the same order and dtype: floats bit for bit (``numpy.array_equal`` with NaN in
     the same places), bool and int8 exactly. No tolerance anywhere: both ports follow the reference code's order
     of operations (``pine_alma``: weights by ``math.exp`` / ``math.pow``, the sum from the oldest bar, one division;
     ``pine_sma`` / ``pine_stdev``: from the newest bar; ``pine_rma``: ``alpha * x + (1 - alpha) * prev``);
   - the flip event table (bar, open and close time, side, close, ATR, both stops, conviction) identical;
   - the 2019-2022 counts (the harness's Development decision bars: closing after 2019-01-01 00:00, filled before
     2023-01-01 00:00) equal to the values recorded at the reconciliation, for both ports. Counts only: no rule is
     run and no profit or loss is computed;
   - both gold starts give the same values on every Development bar.
2. The one mismatch the reconciliation found, by hand: the literal call before bar_index stop_lookback - 1 (port A
   gave a value, port B na, as the documented rule says). Only other inputs can flip that early.
3. Synthetic bars with random inputs inside the script's input ranges (L16-38), and short series: bit for bit.

Line numbers L... are those of the owner's copy of the script (third-party code, cited, never copied).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_ribbon as A
from backtesting.research import tradeiq2_market as TM2
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_ribbon as B  # noqa: E402

SYMS = ("XAUUSDm", "BTCUSDm")
TFS = ("1H", "4H", "1D")                                     # PREREG 6.1
FLOAT_KEYS = ("alma", "dev", "atr", "slope", "conviction", "edge_up", "edge_dn", "risk_long", "risk_short",
              "risk_long_lit", "risk_short_lit")
DTYPES = {**{k: np.float64 for k in FLOAT_KEYS}, "bull_setup": np.bool_, "bear_setup": np.bool_, "trend": np.int8,
          "flip": np.int8}
DEV = ("2019-01-01", "2023-01-01")                           # PREREG 3: Development
STUDY1_GOLD_START = "2017-01-01"                             # study 1's gold bars begin on 2017-01-03

# Recorded at the reconciliation (28 Nov 2026) on the study's bars, both ports equal. Per symbol and timeframe, over
# the Development decision bars: bars, bull / bear setup bars, bull / bear flips, flips whose intended stop is at
# the 3-ATR cap / the 0.75-ATR floor, the same for the literal stop, flips where literal == intended; then over the
# whole series to 2024-06-30: the first flip's bar index and the number of flips.
_RECORDED = {
    ("XAUUSDm", "1H"): (23590, 5079, 4395, 429, 429, 424, 0, 669, 108, 339, 36, 1830),
    ("XAUUSDm", "4H"): (6385, 1480, 1176, 124, 124, 146, 0, 192, 33, 115, 40, 494),
    ("XAUUSDm", "1D"): (1031, 247, 174, 17, 17, 21, 0, 25, 5, 16, 55, 75),
    ("BTCUSDm", "1H"): (35016, 6988, 6355, 636, 635, 565, 0, 951, 185, 434, 36, 2055),
    ("BTCUSDm", "4H"): (8756, 1844, 1574, 161, 161, 158, 0, 244, 42, 122, 43, 512),
    ("BTCUSDm", "1D"): (1459, 334, 236, 24, 25, 25, 0, 35, 11, 20, 36, 83),
}


def identical(x, y) -> list:
    """The keys on which two outputs of the contract differ (empty: identical). Floats bit for bit with NaN in the
    same places (``numpy.array_equal(equal_nan=True)``, which counts 0.0 and -0.0 as equal), the others exactly; the
    keys, their order, shapes and dtypes must be the same."""
    if tuple(x) != A.KEYS or tuple(y) != A.KEYS:
        return ["keys"]
    bad = []
    for k in A.KEYS:
        a, b = np.asarray(x[k]), np.asarray(y[k])
        if a.dtype != DTYPES[k] or b.dtype != DTYPES[k] or a.shape != b.shape:
            bad.append(k)
        elif a.dtype.kind == "f":
            if not (np.array_equal(a, b, equal_nan=True) and np.array_equal(np.isnan(a), np.isnan(b))):
                bad.append(k)
        elif not np.array_equal(a, b):
            bad.append(k)
    return bad


def first_differences(x, y, k, n=3):
    a, b = np.asarray(x[k]), np.asarray(y[k])
    if a.dtype.kind == "f":
        i = np.flatnonzero(~((a == b) | (np.isnan(a) & np.isnan(b))))
    else:
        i = np.flatnonzero(a != b)
    return [(int(j), a[j].item(), b[j].item()) for j in i[:n]]


def event_table(r, t, tc, c):
    """One row per flip: bar, open and close time, side, close, ATR, the intended and the literal stop distance of
    the flip's side, conviction."""
    f = r["flip"]
    ix = np.flatnonzero(f)
    side = f[ix].astype(np.int64)
    long_ = side == 1
    return {
        "bar": ix, "t": t[ix], "tc": tc[ix], "side": side, "close": c[ix], "atr": r["atr"][ix],
        "risk": np.where(long_, r["risk_long"][ix], r["risk_short"][ix]),
        "risk_lit": np.where(long_, r["risk_long_lit"][ix], r["risk_short_lit"][ix]),
        "conviction": r["conviction"][ix],
    }


def counts(r, dev):
    """The recorded tuple for one output (see ``_RECORDED``): exact comparisons, since the clamp returns exactly
    ``atr * 3.0`` or ``atr * 0.75``."""
    f, atr = r["flip"], r["atr"]
    fd = (f != 0) & dev
    risk = np.where(f == 1, r["risk_long"], r["risk_short"])[fd]
    lit = np.where(f == 1, r["risk_long_lit"], r["risk_short_lit"])[fd]
    cap, floor = atr[fd] * 3.0, atr[fd] * 0.75
    nz = np.flatnonzero(f)
    return (int(dev.sum()), int((r["bull_setup"] & dev).sum()), int((r["bear_setup"] & dev).sum()),
            int(((f == 1) & dev).sum()), int(((f == -1) & dev).sum()),
            int((risk == cap).sum()), int((risk == floor).sum()), int((lit == cap).sum()), int((lit == floor).sum()),
            int((lit == risk).sum()), int(nz[0]), int(len(nz)))


# ───────────────────────────── 1. the real bars (to 2024-06-30, the guards closed) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol: for 1H / 4H / 1D the bars (open and close times, OHLC, the Development decision mask) and both
    ports' outputs, from the study's data start; for gold also from study 1's start. The M1 bars are released as
    soon as the bars are built (one symbol's M1 bars in memory at a time; this file peaks at about 1 GB)."""
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
                             dev=dev)
            del mk
        for tf, b in out.items():
            b.a = A.ribbon(b.o, b.h, b.l, b.c)
            b.b = B.ribbon(b.o, b.h, b.l, b.c)
            if symbol == "XAUUSDm":                                      # study 1's start: a suffix of the bars
                k = int(np.searchsorted(b.t, TM.s_of(STUDY1_GOLD_START)))
                b.k1 = k
                b.a1 = A.ribbon(b.o[k:], b.h[k:], b.l[k:], b.c[k:])
                b.b1 = B.ribbon(b.o[k:], b.h[k:], b.l[k:], b.c[k:])
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
        bad = identical(b.a, b.b)
        assert not bad, (symbol, tf, {k: first_differences(b.a, b.b, k) for k in bad if k != "keys"})
        assert (b.a["flip"] != 0).sum() > 70, (symbol, tf)
        if symbol == "XAUUSDm":
            bad = identical(b.a1, b.b1)
            assert not bad, (symbol, tf, "from 2017", {k: first_differences(b.a1, b.b1, k) for k in bad if k != "keys"})


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_flip_event_tables_are_identical(symbol, real):
    data = real(symbol)
    for tf, b in data.bars.items():
        ta, tb = event_table(b.a, b.t, b.tc, b.c), event_table(b.b, b.t, b.tc, b.c)
        assert list(ta) == list(tb)
        for col in ta:
            assert ta[col].dtype == tb[col].dtype and np.array_equal(ta[col], tb[col]), (symbol, tf, col)
        # every flip has both stops (the literal one exists on the flip bars of its side only)
        assert np.isfinite(ta["risk"]).all() and np.isfinite(ta["risk_lit"]).all(), (symbol, tf)
        assert np.all(ta["side"][1:] != ta["side"][:-1]), (symbol, tf)          # flips alternate


@pytest.mark.parametrize("symbol", SYMS)
def test_real_bars_recorded_development_counts(symbol, real):
    """2019-2022 counts recorded at the reconciliation: a guard against both ports changing (counts, no P/L)."""
    data = real(symbol)
    for tf, b in data.bars.items():
        want = _RECORDED[(symbol, tf)]
        assert counts(b.a, b.dev) == want, (symbol, tf, counts(b.a, b.dev))
        assert counts(b.b, b.dev) == want, (symbol, tf, counts(b.b, b.dev))


def test_real_bars_gold_from_2016_or_2017_is_the_same_from_2019(real):
    """The literal stop depends on where the bars start (the first flips of each side). On gold, the study's bars
    (from 2016-01-03) and study 1's (from 2017-01-03) give the same value of every key on every Development bar,
    the literal stops included; they differ only before 2019 (flips in January 2017, stops into late 2018)."""
    data = real("XAUUSDm")
    for tf, b in data.bars.items():
        k = b.k1
        assert int(b.t[k]) >= TM.s_of(STUDY1_GOLD_START) and int(b.t[k - 1]) < TM.s_of(STUDY1_GOLD_START)
        dev = b.dev[k:]
        assert dev.sum() == b.dev.sum() and not b.dev[:k].any()
        tail = {key: v[k:][dev] for key, v in b.a.items()}
        later = {key: v[dev] for key, v in b.a1.items()}
        assert not identical(tail, later), (tf, identical(tail, later))
        # before 2019 the two starts do differ (so the comparison above is not empty of meaning)
        early = ~dev & (b.tc[k:] <= TM.s_of(DEV[0]))
        assert any(not np.array_equal(b.a[key][k:][early], b.a1[key][early], equal_nan=True)
                   for key in ("risk_long_lit", "risk_short_lit", "atr")), tf


# ───────────────────────────── 2. the mismatch, by hand ─────────────────────────────

def zigzag_bars():
    """Flat 100 to bar 9, then 8 legs of 15 bars, +1 / -1 a bar (100 -> 115 -> 100 -> ...); open = the previous
    close, high / low = the body +- 0.25."""
    c = [100.0] * 10
    level = 100.0
    for j in range(8):
        step = 1.0 if j % 2 == 0 else -1.0
        c += [level + step * k for k in range(1, 16)]
        level += 15 * step
    c = np.array(c)
    o = np.concatenate(([c[0]], c[:-1]))
    return o, np.maximum(o, c) + 0.25, np.minimum(o, c) - 0.25, c


def test_mismatch_literal_call_before_bar_index_lookback_minus_1():
    """L315-317 inside ``if flip``: the literal ``ta.lowest(low, 50)`` / ``ta.highest(high, 50)`` run on flip bars
    only. The window rule both ports document (PineTS's account of TradingView): a call returns na while the chart's
    bar_index < 50 - 1 = 49, and from bar 49 on the extreme of the values it has buffered. ``[1]`` is the previous
    execution's result. With ALMA, deviation and ATR of 5 bars and a 1-bar slope (inside the inputs' ranges, L16-31)
    the zigzag flips at bars 10 (bull), 26 (bear), 41 (bull), 56 (bear), 71, 86, 101, 116.

    Longs (lows of the bull-flip bars 99.75, 100.75, 100.75, 100.75; closes 101, 102, 102, 102):
      bar 10: first execution, [1] = na -> 0.75 ATR
      bar 41: [1] = the result at bar 10 (< 49) = na -> 0.75 ATR
      bar 71: [1] = the result at bar 41 (< 49) = na -> 0.75 ATR   (port A gave 102 - 99.75 = 2.25 here)
      bar 101: [1] = the result at bar 71 = min(99.75, 100.75, 100.75) = 99.75 -> 102 - 99.75 = 2.25 (inside 0.75-3 ATR)
    Shorts (highs 114.25, closes 113):
      bar 26: 0.75 ATR; bar 56: [1] = the result at bar 26 (< 49) = na -> 0.75 ATR (port A gave 114.25 - 113 = 1.25);
      bars 86 and 116: [1] = 114.25 -> 1.25.
    Port B was right (it follows the rule it documents); port A ignored the bar_index part and is fixed."""
    o, h, l, c = zigzag_bars()
    kw = dict(alma_len=5, dev_len=5, slope_len=1, atr_len=5, stop_lookback=50)
    ra, rb = A.ribbon(o, h, l, c, **kw), B.ribbon(o, h, l, c, **kw)
    assert not identical(ra, rb)
    f = ra["flip"]
    assert np.flatnonzero(f == 1).tolist() == [10, 41, 71, 101] and np.flatnonzero(f == -1).tolist() == [26, 56, 86, 116]
    assert l[[10, 41, 71, 101]].tolist() == [99.75, 100.75, 100.75, 100.75] and c[[41, 71, 101]].tolist() == [102.0] * 3
    assert h[[26, 56, 86, 116]].tolist() == [114.25] * 4 and c[[26, 56, 86, 116]].tolist() == [113.0] * 4
    atr = ra["atr"]
    for t, want in ((10, 0.75 * atr[10]), (41, 0.75 * atr[41]), (71, 0.75 * atr[71]), (101, 2.25)):
        assert ra["risk_long_lit"][t] == want, t
        assert 0.75 * atr[t] <= want <= 3.0 * atr[t], t
    for t, want in ((26, 0.75 * atr[26]), (56, 0.75 * atr[56]), (86, 1.25), (116, 1.25)):
        assert ra["risk_short_lit"][t] == want, t
        assert 0.75 * atr[t] <= want <= 3.0 * atr[t], t
    # what port A computed before the fix (the call's result taken at every execution): other values at 71 and 56
    old_l = A._previous_calls(l[[10, 41, 71, 101]], 50, True)
    old_s = A._previous_calls(h[[26, 56, 86, 116]], 50, False)
    assert c[71] - old_l[2] == 2.25 and old_s[1] - c[56] == 1.25
    assert 2.25 != 0.75 * atr[71] and 1.25 != 0.75 * atr[56]
    # with the script's defaults the first flip is at bar 36 or later, where the rule is already satisfied (bar >= 11)
    assert int(np.flatnonzero(A.ribbon(o, h, l, c)["flip"])[0]) >= 36


# ───────────────────────────── 3. synthetic bars, random inputs ─────────────────────────────

def synthetic(rng, n, kind):
    """Random bars: a walk, a walk rounded to whole dollars (ties), alternating trends, or a mostly flat walk with
    no wicks (true ranges of 0 and an ATR that can be 0)."""
    if kind == "walk":
        c = 1000 + np.cumsum(rng.normal(0, 1, n))
    elif kind == "round":
        c = np.round(1000 + np.cumsum(rng.normal(0, 1, n)), 0)
    elif kind == "trendy":
        c = 1000 + np.cumsum(rng.normal(0, 1, n) + 0.8 * np.sign(np.sin(np.arange(n) / rng.uniform(5, 40))))
    else:
        c = 1000 + np.cumsum(rng.normal(0, 1, n) * (rng.random(n) < 0.3))
    o = np.concatenate((c[:1], c[:-1]))
    wick = 0.0 if kind == "flat" else 1.0
    h = np.maximum(o, c) + wick * np.abs(rng.normal(0, 0.5, n))
    l = np.minimum(o, c) - wick * np.abs(rng.normal(0, 0.5, n))
    if kind == "round":
        h, l = np.round(h, 0), np.round(l, 0)
    return o, h, l, c


def random_inputs(rng):
    """The script's inputs drawn inside their ranges (L16-38: minval / maxval / step); slope_min is >= 0 (port A
    refuses a negative one, outside the input's range)."""
    step = lambda lo, hi, s: float(np.round(rng.uniform(lo, hi) / s) * s)
    p = dict(alma_len=int(rng.integers(5, 60)), alma_offset=step(0.0, 1.0, 0.05), alma_sigma=step(1.0, 15.0, 0.5),
             dev_len=int(rng.integers(5, 60)), dev_mult=step(0.1, 3.0, 0.05), slope_len=int(rng.integers(1, 11)),
             slope_min=step(0.0, 1.0, 0.01), atr_len=int(rng.integers(5, 40)), stop_lookback=int(rng.integers(3, 51)),
             min_stop_atr=step(0.25, 3.0, 0.05), max_stop_atr=step(1.0, 8.0, 0.25))
    if rng.random() < 0.4:
        p["slope_min"] = float(rng.uniform(0.0, 0.05))           # small thresholds: many flips
    return p


@pytest.mark.parametrize("seed", range(6))
def test_random_inputs_inside_the_script_ranges_bit_for_bit(seed):
    rng = np.random.default_rng(1000 + seed)
    flips = 0
    for case in range(12):
        p = random_inputs(rng)
        n = int(rng.choice([300, 800, 1500]))
        kind = str(rng.choice(["walk", "round", "trendy", "flat"]))
        o, h, l, c = synthetic(rng, n, kind)
        ra, rb = A.ribbon(o, h, l, c, **p), B.ribbon(o, h, l, c, **p)
        bad = identical(ra, rb)
        assert not bad, (seed, case, kind, p, {k: first_differences(ra, rb, k) for k in bad if k != "keys"})
        flips += int((ra["flip"] != 0).sum())
    assert flips > 50


@pytest.mark.parametrize("kw", [
    {},                                                                       # the script's defaults
    dict(alma_len=5, alma_offset=0.0, alma_sigma=1.0, dev_len=5, dev_mult=0.1, slope_len=1, slope_min=0.0, atr_len=5,
         stop_lookback=3, min_stop_atr=0.25, max_stop_atr=1.0),               # every input at its lower bound
    dict(alma_offset=1.0, alma_sigma=15.0, dev_mult=3.0, slope_len=10, slope_min=0.2, stop_lookback=50,
         min_stop_atr=3.0, max_stop_atr=8.0),                                 # upper bounds
    dict(min_stop_atr=3.0, max_stop_atr=1.0),                                 # floor above the cap: always 1 ATR
    dict(alma_len=5, dev_len=5, slope_len=1, slope_min=0.02, atr_len=5, stop_lookback=50),   # flips before bar 49
])
def test_edge_inputs_and_short_series_bit_for_bit(kw):
    rng = np.random.default_rng(77)
    early_sides = set()
    for kind in ("walk", "round", "trendy", "flat"):
        o, h, l, c = synthetic(rng, 1200, kind)
        ra = A.ribbon(o, h, l, c, **kw)
        assert not identical(ra, B.ribbon(o, h, l, c, **kw)), (kind, kw)
        early_sides |= set(ra["flip"][:49].tolist()) - {0}
        for n in (0, 1, 2, 5, 13, 14, 33, 34, 36, 37, 60):               # the warm-up bars, cut short
            assert not identical(A.ribbon(o[:n], h[:n], l[:n], c[:n], **kw),
                                 B.ribbon(o[:n], h[:n], l[:n], c[:n], **kw)), (kind, n, kw)
    if kw.get("stop_lookback") == 50 and kw.get("alma_len") == 5:            # the mismatch's case is exercised:
        assert early_sides == {-1, 1}                                         # flips of both sides before bar 49


def test_the_two_ports_refuse_bad_bars_alike():
    """Unequal lengths, a 2-D array or a non-finite price: both raise ValueError (the contract). Outside the
    contract, port A also refuses a negative slope_min (L28's minval is 0) and non-finite multipliers, which port B
    transcribes as given."""
    o, h, l, c = synthetic(np.random.default_rng(5), 100, "walk")
    bad = c.copy()
    bad[40] = math.nan
    for args in ((o, h, l, c[:-1]), (o, h, l, bad), (o, h, np.vstack([l, l]), c), (o, h, l, np.where(c > 0, np.inf, c))):
        with pytest.raises(ValueError):
            A.ribbon(*args)
        with pytest.raises(ValueError):
            B.ribbon(*args)
    with pytest.raises(ValueError):
        A.ribbon(o, h, l, c, slope_min=-0.1)
    assert not identical(A.ribbon(o, h, l, c, slope_min=0.0), B.ribbon(o, h, l, c, slope_min=0.0))
