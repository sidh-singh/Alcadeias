"""
LuxAlgo's Ultimate Opening Range Breakout (study 2, ``backtest_results/tradeiq_2027/PREREG.md`` 6.5 and claims 6-9
of section 8): the reconciliation of its two independent ports. What was found and decided, for readers:
``backtest_results/tradeiq_2027/porting/orb.md``.

* Port A, ``backtesting/research/tradeiq2_ind_orb.py``: the production port (numpy and one numba kernel); its own
  tests are ``test_tradeiq2_ind_orb_a.py``.
* Port B, ``tests/tradeiq2_oracle_orb.py``: the oracle, a statement-by-statement transcription in plain Python with its
  own Pine primitives and ``zoneinfo`` clocks; its own tests are ``test_tradeiq2_ind_orb_b.py``.

PREREG 5 ("Ports"): the two must agree bit for bit on the real bars of both symbols, on every series a rule reads,
before any rule runs. NO TOLERANCE IS USED ANYWHERE: the same integers, booleans and labels, and every float bit for
bit (``bits_equal``: NaN in the same places, every other value and the sign of every zero equal). Both ports follow
the script's order of arithmetic and study 1's order for ``ta.sma`` / ``ta.rma`` (``pine_sma``: ``x[i] / n`` added
from the newest bar; ``alpha * x + (1 - alpha) * prev``), so no float needed a tolerance.

1. THE REAL BARS (skipped when the tick store is absent), one symbol at a time: gold and BTC, M5 and M15 (the
   timeframes of PREREG 6.5), from the symbol's data start (gold 2016-01-03, BTC 2018-01-01) to 2024-06-30 23:59 UTC,
   exactly as the study loads them: ``tradeiq2_market.load(symbol, end="2024-07-01")`` with both studies' hold-out
   guards pointed at empty folders, the chart bars ``mk.tbars('M5' | 'M15')``, and the volume PREREG 2 assigns
   (``Context.volume``: gold ticks, BTC Binance BTCUSDT 5m klines). Every configuration the plan runs for this script
   is compared: the plan's version ('study': New York clock, weekdays, the exchange's day), the literal UTC-5 clock
   (claim 9's control), gold's COMEX range ORB-CX, BTC on all seven days and BTC on tick volume (the HV tag's
   alternative), and two alternative readings of the day reset, 'clock0' (midnight of the session clock) and, for
   BTC, 'ny17'. For each: every per-bar key of the contract and the ``days`` frame (one row per session the script
   counts), identical; and their 2019-2022 event counts equal to the values recorded at the reconciliation (counts
   only: no rule is run). THE ENTRY AND EXIT PRICES OF THE SCRIPT'S OWN TRADES ARE COMPARED FOR EQUALITY ONLY: no
   value of them is printed, counted, summed or otherwise looked at (PREREG: no profit or loss of any rule of this
   study on real data). A failing assertion names the configuration, the key and the number of bars or rows that
   differ, never a value.
2. THE THIRD OPINION: every session's range equals the high and the low of the M1 bars opening in its 30 minutes on
   its date, which is the unreviewed planning probe's computation (``probe_sessions.py`` of the study's work folder,
   re-implemented here, not imported) for the New York 09:30 range, and the same for the UTC-5 clock and the COMEX
   range (M5: 08:20-08:50; M15: 08:30-09:00, the bars that OPEN in 08:20-08:50).
3. The mismatches the reconciliation found, pinned on the real bars: ``isNewDay`` on bar 0 (port B's first reading,
   true, changes nothing but ``new_day[0]``), and the wiped COMEX session of 2021-03-02 on gold M5 (the row the two
   ports first wrote differently).
4. Synthetic bars: port A's and port B's random charts, charts with many data holes (sessions cut by holes, by the
   data end and by a new exchange day), sessions next to midnight, every input of the contract, and every chart cut
   at random bars: both ports identical.
5. The contract: the same names, constants, columns, dtypes, defaults and refused inputs in both ports.

Memory: one symbol at a time (about 1.7 GB at the peak, with BTC's Binance volume loaded). Time: about two and a half
minutes, most of it port B's plain-Python bar loop.
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
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_orb as A
from backtesting.research import tradeiq2_market as M2
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_orb as B  # noqa: E402
import test_tradeiq2_ind_orb_a as TA  # noqa: E402   (port A's tests: their random-chart generator only)
import test_tradeiq2_ind_orb_b as TB  # noqa: E402   (port B's tests: their random-chart generator only)

GOLD, BTC = "XAUUSDm", "BTCUSDm"
SYMS = (GOLD, BTC)
TFS = (("M5", 5), ("M15", 15))
DAY = 86400
DEV = (TM.s_of("2019-01-01"), TM.s_of("2023-01-01"))          # PREREG 3: Development (bars closing in it)
# the bars the study serves while its hold-out is closed (DATA.md, "What the code serves"), gold's 2016 included
DATA_MD_BARS = {(GOLD, "M5"): 596_786, (GOLD, "M15"): 199_192, (BTC, "M5"): 681_121, (BTC, "M15"): 227_123}
DTYPES = {**{k: np.bool_ for k in ("in_session", "new_day", "session_ended", "breakout_up", "breakout_dn",
                                    "label_up", "label_dn", "hv")},
          **{k: np.float64 for k in ("or_high", "or_low", "atr", "trail")}, "active_dir": np.int8}

# Each configuration: the keyword arguments of ``orb`` and the volume it reads ('study' = PREREG 2's, 'tick').
CONFS = {
    "study": (dict(), "study"),                                # PREREG 6.5: New York clock, weekdays, exchange day
    "tick": (dict(), "tick"),                                  # BTC only: Exness tick volume (HV's alternative)
    "utc-5": (dict(clock="utc-5"), "study"),                   # the script's literal clock (claim 9, O1 control)
    "comex": (dict(sess=(500, 530)), "study"),                 # gold only: ORB-CX, 08:20-08:50 New York
    "all-days": (dict(days="all"), "study"),                   # BTC only: all seven days (O1 control)
    "clock0": (dict(day_boundary="clock0"), "study"),          # the day reset's alternative reading (measurement)
    "ny17": (dict(day_boundary="ny17"), "study"),              # BTC only: a 17:00 New York day (measurement)
}
ONLY = {"tick": BTC, "comex": GOLD, "all-days": BTC, "ny17": BTC}

# Recorded at the reconciliation (28 Nov 2026) on the study's bars, both ports equal; port A's and port B's own
# reports (bars from 2019) give the same numbers. Over the Development window (bars closing in 2019-2022; sessions
# whose first bar closes in it): sessions, raw breakouts up / down (the alert condition), labels up / down, HV labels
# up / down, first breakout up / down / none, sessions hitting u1 u2 u3 d1 d2 d3, the script's first trades long /
# short, its second trades, the first trades' exits by the trail / the window / the reset, the same for the second
# trades. Counts only.
_RECORDED = {
    (GOLD, "M5", "study"): (1031, 1682, 1565, 638, 609, 337, 410, 502, 491, 38, 304, 113, 49, 313, 137, 57, 502, 491,
                            187, 868, 0, 125, 122, 0, 65),
    (GOLD, "M5", "utc-5"): (1031, 1713, 1615, 653, 604, 253, 299, 534, 460, 37, 296, 115, 44, 283, 107, 57, 534, 460,
                            180, 827, 0, 167, 107, 0, 73),
    (GOLD, "M5", "comex"): (1031, 2049, 1882, 722, 688, 542, 573, 522, 489, 20, 365, 185, 102, 381, 196, 108, 522,
                            489, 288, 955, 0, 56, 234, 0, 54),
    (GOLD, "M5", "clock0"): (1031, 2271, 2119, 638, 609, 337, 410, 512, 502, 17, 356, 164, 83, 353, 171, 73, 502, 491,
                             187, 882, 80, 31, 129, 44, 14),
    (GOLD, "M15", "study"): (1031, 1039, 986, 601, 564, 407, 421, 498, 470, 63, 304, 113, 49, 313, 137, 57, 498, 470,
                             47, 279, 0, 689, 2, 0, 45),
    (GOLD, "M15", "utc-5"): (1031, 1058, 993, 613, 557, 274, 271, 516, 454, 61, 296, 115, 44, 283, 107, 57, 516, 454,
                             27, 215, 0, 755, 1, 0, 26),
    (GOLD, "M15", "comex"): (1030, 1248, 1159, 683, 645, 578, 580, 511, 496, 23, 378, 203, 110, 415, 224, 109, 511,
                             496, 59, 419, 0, 588, 6, 0, 53),
    (GOLD, "M15", "clock0"): (1031, 1385, 1301, 601, 564, 407, 421, 513, 487, 31, 356, 164, 83, 353, 171, 73, 498,
                              470, 47, 288, 533, 147, 2, 34, 11),
    (BTC, "M5", "study"): (1042, 2698, 2512, 750, 722, 562, 564, 529, 504, 9, 534, 326, 220, 530, 356, 229, 525, 502,
                           286, 944, 83, 0, 198, 88, 0),
    (BTC, "M5", "tick"): (1042, 2698, 2512, 750, 722, 499, 569, 529, 504, 9, 534, 326, 220, 530, 356, 229, 525, 502,
                          286, 944, 83, 0, 198, 88, 0),
    (BTC, "M5", "utc-5"): (1042, 2816, 2496, 773, 725, 534, 526, 545, 487, 10, 534, 345, 224, 537, 341, 207, 541, 484,
                           299, 952, 73, 0, 208, 91, 0),
    (BTC, "M5", "all-days"): (1458, 4076, 3739, 1070, 1024, 793, 795, 741, 708, 9, 787, 507, 338, 793, 530, 338, 733,
                              705, 394, 1324, 114, 0, 262, 132, 0),
    (BTC, "M5", "clock0"): (1042, 3341, 3122, 750, 722, 562, 564, 531, 506, 5, 600, 389, 276, 573, 403, 283, 525, 502,
                            286, 944, 83, 0, 198, 88, 0),
    (BTC, "M5", "ny17"): (1042, 2223, 2089, 750, 722, 562, 564, 525, 502, 15, 474, 277, 184, 489, 310, 195, 525, 502,
                          286, 941, 0, 86, 193, 0, 93),
    (BTC, "M15", "study"): (1042, 1657, 1550, 707, 684, 478, 499, 524, 505, 13, 534, 326, 220, 530, 356, 229, 520,
                            503, 55, 421, 602, 0, 4, 51, 0),
    (BTC, "M15", "tick"): (1042, 1657, 1550, 707, 684, 436, 515, 524, 505, 13, 534, 326, 220, 530, 356, 229, 520, 503,
                           55, 421, 602, 0, 4, 51, 0),
    (BTC, "M15", "utc-5"): (1042, 1712, 1502, 729, 678, 423, 455, 548, 480, 14, 534, 345, 224, 537, 341, 207, 543,
                            478, 53, 423, 598, 0, 3, 50, 0),
    (BTC, "M15", "all-days"): (1458, 2504, 2309, 1012, 973, 662, 685, 732, 712, 14, 787, 507, 338, 793, 530, 338, 724,
                               710, 72, 616, 818, 0, 6, 66, 0),
    (BTC, "M15", "clock0"): (1042, 2019, 1911, 707, 684, 478, 499, 525, 507, 10, 600, 389, 276, 573, 403, 283, 520,
                             503, 55, 421, 602, 0, 4, 51, 0),
    (BTC, "M15", "ny17"): (1042, 1384, 1305, 707, 684, 478, 499, 520, 503, 19, 474, 277, 184, 489, 310, 195, 520, 503,
                           55, 403, 0, 620, 4, 0, 51),
}


# ───────────────────────────── comparison helpers (they never show a value) ─────────────────────────────

def _float_mismatch(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per element: True where x and y differ as float64 bits (NaN payloads aside): one NaN and not the other, other
    values, or zeros of opposite signs."""
    nx, ny_ = np.isnan(x), np.isnan(y)
    with np.errstate(invalid="ignore"):
        same = (nx & ny_) | (~nx & ~ny_ & (x == y) & (np.signbit(x) == np.signbit(y)))
    return ~same


def n_diff(x, y) -> int:
    """How many elements of two equally shaped arrays differ (a count for a message, never a value); -1 if the shapes
    differ."""
    x, y = np.asarray(x), np.asarray(y)
    if x.shape != y.shape:
        return -1
    if x.dtype.kind == "f" or y.dtype.kind == "f":
        return int(_float_mismatch(x.astype(np.float64), y.astype(np.float64)).sum())
    if x.dtype == object or y.dtype == object:
        return sum(1 for p, q in zip(x.tolist(), y.tolist()) if p != q or type(p) is not type(q))
    return int((x != y).sum())


def same_outputs(a, b, where: str, skip=()) -> None:
    """Port A's and port B's outputs are identical: the same keys in the contract's order; per-bar arrays of the
    contract's dtypes, floats bit for bit; the ``days`` frames with the same columns, dtypes and rows."""
    assert tuple(a) == A.KEYS and tuple(b) == A.KEYS, f"{where}: keys"
    n = len(a["in_session"])
    for k in A.BAR_KEYS:
        if k in skip:
            continue
        x, y = np.asarray(a[k]), np.asarray(b[k])
        assert x.dtype == DTYPES[k] and y.dtype == DTYPES[k], f"{where}: dtype of {k}: {x.dtype} / {y.dtype}"
        assert x.shape == y.shape == (n,), f"{where}: shape of {k}"
        assert n_diff(x, y) == 0, f"{where}: {k} differs on {n_diff(x, y)} of {n} bars"
    same_days(a["days"], b["days"], where)


def same_days(da: pd.DataFrame, db: pd.DataFrame, where: str) -> None:
    assert list(da.columns) == list(A.DAY_COLUMNS) == list(db.columns), f"{where}: days columns"
    assert len(da) == len(db), f"{where}: {len(da)} days rows in port A, {len(db)} in port B"
    for col in A.DAY_COLUMNS:
        x, y = da[col].to_numpy(), db[col].to_numpy()
        assert x.dtype == y.dtype, f"{where}: dtype of days.{col}: {x.dtype} / {y.dtype}"
        if x.dtype == object:
            assert all(isinstance(p, str) for p in x) and all(isinstance(q, str) for q in y), \
                f"{where}: days.{col} holds something else than labels"
        assert n_diff(x, y) == 0, f"{where}: days.{col} differs on {n_diff(x, y)} of {len(x)} rows"


def dev_counts(out, tc) -> tuple:
    """The recorded tuple (see ``_RECORDED``) of one output over the Development window. It reads labels, flags, bars
    and exit labels only: never a price of the script's trades."""
    a, z = DEV
    inw = (tc > a) & (tc <= z)
    d = out["days"]
    first = tc[d.start_bar.to_numpy()]
    dw = d[(first > a) & (first <= z)]
    c = [len(dw)]
    c += [int((out[k] & inw).sum()) for k in ("breakout_up", "breakout_dn", "label_up", "label_dn")]
    c += [int((out["label_up"] & out["hv"] & inw).sum()), int((out["label_dn"] & out["hv"] & inw).sum())]
    c += [int((dw.first_breakout_side == s).sum()) for s in (1, -1, 0)]
    c += [int(dw[f"hit_{k}"].sum()) for k in ("u1", "u2", "u3", "d1", "d2", "d3")]
    c += [int((dw.trade_side == 1).sum()), int((dw.trade_side == -1).sum()), int((dw.trade2_side != 0).sum())]
    c += [int((dw.exit_reason == w).sum()) for w in ("trail", "window", "reset")]
    c += [int((dw.exit2_reason == w).sum()) for w in ("trail", "window", "reset")]
    return tuple(c)


# ───────────────────────────── 1. the real bars (to 2024-06-30, both guards closed) ─────────────────────────────

def _available(symbol: str) -> bool:
    months = store.available_months(symbol)
    start = M2.data_start(symbol)
    return (2024, 6) in months and (int(start[:4]), int(start[5:7])) in months


def m1_ranges(t, h, l, clock: str, s0: int, s1: int):
    """The opening range as the planning probe computes it (``probe_sessions.py``, re-implemented): per date of the
    session clock, on weekdays, the highest high and the lowest low of the M1 bars that OPEN in [s0, s1) minutes of
    that clock. Returns (epoch days, highs, lows), in date order."""
    loc = X.local_seconds(t, X.NY) if clock == "ny" else np.asarray(t, np.int64) - 5 * 3600
    minute = (loc // 60) % 1440
    day = loc // DAY
    sel = (minute >= s0) & (minute < s1) & ((day + 3) % 7 < 5)
    d, hh, ll = day[sel], h[sel], l[sel]
    if not len(d):
        return d, hh, ll
    first = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    return d[first], np.maximum.reduceat(hh, first), np.minimum.reduceat(ll, first)


@pytest.fixture(scope="module", params=SYMS)
def real(request, tmp_path_factory):
    """One symbol's study bars: M5 and M15 (open and close times, the bid OHLC, the study's volume and the tick
    volume), and the M1 ranges of the third opinion. The M1 market is dropped once these are built, so one market is
    in memory at a time."""
    symbol = request.param
    if not _available(symbol):
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    d1, d2 = tmp_path_factory.mktemp("closed_study1"), tmp_path_factory.mktemp("closed_study2")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(TM, "STUDY_DIR", d1)                    # study 1's guard: no FINALISTS.md, closed
        mp.setattr(M2, "STUDY_DIR", d2)                    # study 2's guard: closed
        mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
        mk = M2.load(symbol, end="2024-07-01")
        assert mk.end_s == M2.CUT_S and int(mk.t[-1]) + 60 <= M2.CUT_S          # nothing from the hold-out
        ctx = M2.Context(mk)
        charts = {}
        for tf, tfm in TFS:
            b = mk.tbars(tf)
            ch = NS(tf=tf, tfm=tfm, t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(),
                    c=b.c.copy(), tick=b.vol.astype(np.float64), study=None)
            try:
                ch.study = np.array(ctx.volume(tf), np.float64)                  # PREREG 2: gold ticks, BTC Binance
            except OSError:                                                     # the Binance files are absent
                ch.study = None
            charts[tf] = ch
        m1 = {"ny": m1_ranges(mk.t, mk.h, mk.l, "ny", 570, 600),
              "utc-5": m1_ranges(mk.t, mk.h, mk.l, "utc-5", 570, 600),
              "comex M5": m1_ranges(mk.t, mk.h, mk.l, "ny", 500, 530),          # the bars that open in 08:20-08:50:
              "comex M15": m1_ranges(mk.t, mk.h, mk.l, "ny", 510, 540)}         # 08:30 and 08:45 on M15
        first = int(mk.t[0])
        del mk, ctx, b
    gc.collect()
    yield NS(symbol=symbol, charts=charts, m1=m1, first=first)
    charts.clear()
    gc.collect()


def test_real_bars_are_the_studys(real):
    """The bars are those the study serves (DATA.md's counts, from the data start) and end before the hold-out."""
    for tf, ch in real.charts.items():
        assert len(ch.t) == DATA_MD_BARS[(real.symbol, tf)], tf
        assert int(ch.tc[-1]) <= M2.CUT_S and int(ch.t[0]) >= real.first - 60 * ch.tfm, tf
        assert np.isfinite(ch.c).all() and np.all(np.diff(ch.t) > 0), tf
    assert TM.utc(real.first).year == (2016 if real.symbol == GOLD else 2018)


def _run_both(ch, symbol: str, kw: dict, vol: str):
    v = ch.study if vol == "study" else ch.tick
    if v is None:
        pytest.skip("the Binance 5m klines are not on this machine")
    args = (ch.t, ch.o, ch.h, ch.l, ch.c, v, ch.tfm)
    return A.orb(*args, symbol=symbol, **kw), B.orb(*args, symbol=symbol, **kw), args


@pytest.mark.parametrize("tf", [tf for tf, _ in TFS])
@pytest.mark.parametrize("conf", list(CONFS))
def test_real_bars_both_ports_bit_for_bit(real, tf, conf):
    """Every per-bar key and the ``days`` frame, identical in both ports, for one configuration of PREREG 6.5 (or an
    alternative reading); and the 2019-2022 event counts equal to the recorded ones."""
    if ONLY.get(conf, real.symbol) != real.symbol:
        pytest.skip(f"{conf}: {ONLY[conf]} only")
    ch = real.charts[tf]
    kw, vol = CONFS[conf]
    a, b, args = _run_both(ch, real.symbol, kw, vol)
    where = f"{real.symbol} {tf} {conf}"
    same_outputs(a, b, where)
    del b
    gc.collect()
    assert dev_counts(a, ch.tc) == _RECORDED[(real.symbol, tf, conf)], where
    d = a["days"]
    assert len(d) > 1400 and (d.trade_side != 0).sum() > 1000, where
    if conf == "study":
        # R4's alternative (isNewDay true on bar 0, port B's first reading) changes new_day[0] and nothing else
        alt = B._run(*args, symbol=real.symbol, first_bar_new_day=True, **kw)
        alt = {k: alt[k] for k in B.KEYS}
        assert alt["new_day"][0] and not a["new_day"][0]
        same_outputs(a, alt, where + " with isNewDay[0] true", skip=("new_day",))
        assert n_diff(a["new_day"], alt["new_day"]) == 1
        del alt
    del a
    gc.collect()


# ───────────────────────────── 2. the third opinion: the probe's M1 ranges ─────────────────────────────

@pytest.mark.parametrize("which", ["ny", "utc-5", "comex"])
def test_real_ranges_equal_the_probes_m1_high_and_low(real, which):
    """Every session's range (rows with a range; the wiped one has none) equals the high and the low of the M1 bars
    opening in its 30 minutes on its date: the planning probe's computation of the opening range. Every date with such
    M1 bars on a weekday has a row. And the median width over 2019-01-01 to 2024-06-30 is the spec's (its 0.6: $6.0 on
    gold, $180 on BTC, from the probe)."""
    if which == "comex" and real.symbol != GOLD:
        pytest.skip("ORB-CX is gold's")
    for tf, ch in real.charts.items():
        kw = {"utc-5": dict(clock="utc-5"), "comex": dict(sess=(500, 530))}.get(which, {})
        da = A.orb(ch.t, ch.o, ch.h, ch.l, ch.c, ch.tick, ch.tfm, symbol=real.symbol, **kw)["days"]
        days, hi, lo = real.m1[f"comex {tf}" if which == "comex" else which]
        assert np.array_equal(da.day.to_numpy(), days), (tf, which, len(da), len(days))
        ok = da.or_high.notna().to_numpy()
        assert n_diff(da.or_high.to_numpy()[ok], hi[ok]) == 0 and n_diff(da.or_low.to_numpy()[ok], lo[ok]) == 0, tf
        if which == "ny":
            scored = ch.tc[da.start_bar.to_numpy()] > DEV[0]
            med = float(np.median(da.width.to_numpy()[scored]))
            assert (round(med, 3), int(scored.sum())) == ({GOLD: (5.994, 1416), BTC: (179.685, 1432)}[real.symbol]), tf


# ───────────────────────────── 3. the mismatches found, on the real bars ─────────────────────────────

def test_real_bars_the_wiped_comex_session(real):
    """The one row the two ports first wrote differently: gold's COMEX session of 2021-03-02 on M5, whose data stop
    after the 08:20 bar and resume on Wednesday 19:00 New York, a new exchange day. The reset on that bar (l.147) wipes
    the range before l.181 counts the session: the row has the session's bar (08:20), NaN levels, nothing hit or broken,
    and a span from the reopen to the next reset (Thursday's 08:20 bar). On M15 that day has no session (its 08:15 bar
    opens before 08:20). The 09:30 session has no wiped row on either symbol."""
    for tf, ch in real.charts.items():
        v = ch.study if ch.study is not None else ch.tick
        args = (ch.t, ch.o, ch.h, ch.l, ch.c, v, ch.tfm)
        for sess in ((570, 600), (500, 530)) if real.symbol == GOLD else ((570, 600),):
            da = A.orb(*args, symbol=real.symbol, sess=sess)["days"]
            wiped = da[da.or_high.isna()]
            if real.symbol == GOLD and sess == (500, 530) and tf == "M5":
                assert len(wiped) == 1, tf
                r = wiped.iloc[0]
                ny = X.local_seconds(ch.t[[int(r.start_bar), int(r.post_bar), int(r.span_end)]], X.NY)
                when = [str(pd.Timestamp(int(s), unit="s")) for s in ny]
                assert when == ["2021-03-02 08:20:00", "2021-03-03 19:00:00", "2021-03-04 08:20:00"], tf
                assert r.start_bar == r.end_bar and r.first_breakout_side == 0 and r.trade_side == 0
                assert not any(r[f"hit_{k}"] for k in ("u1", "u2", "u3", "d1", "d2", "d3"))
            else:
                assert len(wiped) == 0, (tf, sess)


# ───────────────────────────── 4. synthetic bars ─────────────────────────────

def _cuts(n: int, seed: int, k: int = 12, ins=None) -> list:
    """Where to cut a chart of n bars: k random bars, the end, and (``ins``: the in-session mask) three cuts whose last
    bar is inside a session (a session the data end cut)."""
    rng = np.random.default_rng(seed)
    cuts = set(rng.integers(1, n, k).tolist()) | {n}
    if ins is not None and ins.any():
        j = np.flatnonzero(ins)
        cuts |= {int(x) + 1 for x in rng.choice(j, size=min(3, len(j)), replace=False)}
    return sorted(cuts)


def _holes_chart(seed: int):
    """Port A's random chart with 25 more holes of 1 bar to 10 hours anywhere: sessions cut by holes, wiped by a new
    day on their end bar, restarted by a new day inside them, or cut by the data end."""
    rng = np.random.default_rng(1000 + seed)
    kind = "gold" if seed % 2 == 0 else "btc"
    tf = (5, 15)[seed % 4 // 2]
    bars = TA.random_chart(kind, tf, "2023-03-01" if seed % 3 else "2023-10-25", 25, seed, (None, 0.25)[seed % 2])
    keep = np.ones(len(bars[0]), np.bool_)
    for _ in range(25):
        a = int(rng.integers(0, len(keep) - 2))
        keep[a:a + int(rng.integers(1, 600 // tf))] = False
    if seed % 5 == 0:                                       # a hole from inside a session into the next day's
        loc = X.local_seconds(bars[0], X.NY)
        mi, dd = (loc // 60) % 1440, loc // DAY
        j = np.flatnonzero((mi == 575) & ((dd + 3) % 7 < 3))
        if len(j):
            jj = np.flatnonzero((dd == dd[j[0]] + 1) & (mi >= 580))
            if len(jj):
                keep[j[0] + 1:jj[0]] = False
    kw = {}
    if seed % 5 == 1:
        kw["clock"] = "utc-5"
    if seed % 7 == 2:
        kw["days"] = "all"
    if seed % 3 == 0:
        kw["sess"] = [(500, 530), (570, 600), (1380, 1440), (0, 60), (565, 610), (840, 905)][seed % 6]
        if kw["sess"][1] >= 1020:
            kw["window_end"] = 1440
    if seed % 4 == 3:
        kw["day_boundary"] = ("ny17", "utc0", "clock0")[seed % 3]
    return tuple(x[keep] for x in bars), tf, (BTC if kind == "btc" else GOLD), kw


def _compare(bars, tf, symbol, kw, where):
    a = A.orb(*bars, tf, symbol=symbol, **kw)
    b = B.orb(*bars, tf, symbol=symbol, **kw)
    same_outputs(a, b, where)
    return a


@pytest.mark.parametrize("case", TA.RANDOM_CASES, ids=[f"{c['kind']}-{c['tf']}-{c['seed']}" for c in TA.RANDOM_CASES])
def test_synthetic_port_a_charts(case):
    """Port A's twelve random cases (gold-like and BTC-like bars, both 2023 daylight-saving changes, holes, exact
    ties on a coarse price grid, every input of the contract), whole and cut at random bars."""
    bars = TA.random_chart(case["kind"], case["tf"], case["start"], case["days"], case["seed"], case.get("grid"),
                           sigma=case.get("sigma", 0.3))
    sym = BTC if case["kind"] == "btc" else GOLD
    full = _compare(bars, case["tf"], sym, case["kw"], f"A-{case['seed']}")
    assert len(full["days"]) >= 15 and (full["days"].trade_side != 0).sum() >= 5
    for T in _cuts(len(bars[0]), case["seed"]):
        _compare(tuple(x[:T] for x in bars), case["tf"], sym, case["kw"], f"A-{case['seed']} cut at {T}")


@pytest.mark.parametrize("kind,tf", [("gold", 5), ("gold", 15), ("btc", 5), ("btc", 15)])
def test_synthetic_port_b_charts(kind, tf):
    """Port B's random charts around the March 2023 daylight-saving change, with the defaults, the literal clock on
    all days and the 'clock0' reading, whole and cut at every 37th bar."""
    ch = TB._random_chart(11 + tf, tf, kind)
    bars = ch.arrays()
    for kw in (dict(), dict(clock="utc-5", days="all"), dict(day_boundary="clock0"), dict(multiples=(0.382, 0.618, 1.0),
                                                                                         trail_mult=1.5)):
        _compare(bars, tf, ch.symbol, kw, f"B-{kind}-{tf} {kw}")
        for T in range(1, len(bars[0]), 37):
            _compare(tuple(x[:T] for x in bars), tf, ch.symbol, kw, f"B-{kind}-{tf} {kw} cut at {T}")


@pytest.mark.parametrize("seed", range(40))
def test_synthetic_charts_with_many_holes(seed):
    """Charts with many data holes and other sessions, clocks, days and day boundaries: the rare branches (wiped
    ranges, sessions that never end, ranges restarted inside a session, sessions next to midnight), whole and cut."""
    bars, tf, sym, kw = _holes_chart(seed)
    full = _compare(bars, tf, sym, kw, f"holes-{seed} {kw}")
    for T in _cuts(len(bars[0]), seed, 6, full["in_session"]):
        _compare(tuple(x[:T] for x in bars), tf, sym, kw, f"holes-{seed} {kw} cut at {T}")


def test_synthetic_charts_reach_the_rare_branches():
    """The synthetic charts above do reach what the real bars barely do: wiped ranges, sessions restarted by a new
    day, sessions cut by the data end, every exit label, second trades, ties of the volume with its SMA."""
    seen = {"wiped": 0, "restarted": 0, "cut": 0, "trail": 0, "window": 0, "reset": 0, "open": 0, "second": 0}
    for seed in range(40):
        bars, tf, sym, kw = _holes_chart(seed)
        ins = A.orb(*bars, tf, symbol=sym, **kw)["in_session"]
        for T in _cuts(len(bars[0]), seed, 6, ins):
            out = A.orb(*(x[:T] for x in bars), tf, symbol=sym, **kw)
            d = out["days"]
            ins, nd = out["in_session"], out["new_day"]
            seen["wiped"] += int(d.or_high.isna().sum())
            seen["restarted"] += int((ins[1:] & ins[:-1] & nd[1:]).sum())
            seen["cut"] += int(ins[-1])
            for w in ("trail", "window", "reset", "open"):
                seen[w] += int((d.exit_reason == w).sum() + (d.exit2_reason == w).sum())
            seen["second"] += int((d.trade2_side != 0).sum())
    assert all(v > 0 for v in seen.values()), seen


@pytest.mark.parametrize("name", ["bar 0 in session", "1H", "empty", "one bar", "no volume", "midnight session utc0",
                                  "two sessions in one UTC day", "fibonacci and trail", "window end 11:30"])
def test_edge_cases_both_ports(name):
    """Hand-made edges: a chart that starts inside the session, 1H bars (no bar opens in 09:30-10:00, no range), no
    bars, one bar, no volume (``v=None``), a 19:30-20:30 New York session across 00:00 UTC on a 'utc0' day, two
    sessions in one UTC day across the March 2023 daylight-saving weekend, the Fibonacci multiples with another trail
    multiple, another window end."""
    ch = TA.Chart(5)
    kw = {"symbol": GOLD}
    if name == "bar 0 in session":
        ch.flat(TA.D0, "09:40", "17:00")
    elif name == "1H":
        ch = TA.Chart(60).flat(TA.D0, "00:00", "24:00").flat(TA.D1, "00:00", "17:00")
    elif name == "empty":
        ch.rows = {}
    elif name == "one bar":
        ch.flat(TA.D0, "09:30", "09:35")
    elif name == "midnight session utc0":
        TA.base_day(TA.D0, ch, end="24:00").flat(TA.D1, "00:00", "23:00")
        ch.walk(TA.D0, "20:35", [100.6, 101.2, 101.9, 101.0, 100.4, 99.1, 98.7])
        kw = dict(symbol=BTC, sess=(1170, 1230), window_end=1380)
    elif name == "two sessions in one UTC day":
        ch.flat("2023-03-11", "19:00", "24:00").flat("2023-03-12", "00:00", "20:00")
        ch.walk("2023-03-11", "19:30", [101.0, 102.5, 101.2, 99.0])
        ch.walk("2023-03-12", "19:30", [99.5, 98.0, 98.6, 101.4])
        kw = dict(symbol=BTC, sess=(1140, 1170), window_end=1380, days="all", day_boundary="utc0")
    else:
        TA.bull_at_10(TA.base_day(TA.D0, ch)).flat(TA.D1, "08:00", "17:00")
        ch.walk(TA.D0, "10:05", [101.8, 102.6, 101.9, 100.2, 98.4, 97.9, 99.6, 103.3])
        if name == "fibonacci and trail":
            kw = dict(symbol=GOLD, multiples=A.FIB_MULTIPLES, trail_mult=0.7)
        elif name == "window end 11:30":
            kw = dict(symbol=GOLD, window_end=690)
    if ch.rows:
        t, o, h, l, c, v = ch.arrays()
    else:
        t, o, h, l, c, v = np.zeros(0, np.int64), *(np.zeros(0) for _ in range(5))
    if name == "no volume":
        v = None
    a = A.orb(t, o, h, l, c, v, ch.tf, **kw)
    b = B.orb(t, o, h, l, c, v, ch.tf, **kw)
    same_outputs(a, b, name)
    if name == "1H":
        assert not a["in_session"].any() and len(a["days"]) == 0
    if name == "no volume":
        assert not a["hv"].any() and len(a["days"]) >= 1


# ───────────────────────────── 5. the contract ─────────────────────────────

def test_the_contract_is_the_same_in_both_ports():
    """The same function signature and defaults, keys, columns, labels, constants and dtypes (also on an empty input,
    whose ``days`` frame keeps every dtype)."""
    for name in ("KEYS", "BAR_KEYS", "DAY_COLUMNS", "EXIT_REASONS", "CLOCKS", "DAY_SETS", "DAY_BOUNDARIES", "ATR_LEN",
                 "VOL_LEN"):
        assert getattr(A, name) == getattr(B, name), name
    pa, pb = inspect.signature(A.orb).parameters, inspect.signature(B.orb).parameters
    assert list(pa) == list(pb) and [p.default for p in pa.values()] == [p.default for p in pb.values()]
    assert (pa["sess"].default, pa["window_end"].default, pa["trail_mult"].default, pa["multiples"].default) == (
        A.SESSION, A.WINDOW_END, A.TRAIL_MULT, A.MULTIPLES)
    ch = TA._long_trail_then_short(TA.base_day())
    t, o, h, l, c, v = ch.arrays()
    a, b = A.orb(t, o, h, l, c, v, 5, symbol=GOLD), B.orb(t, o, h, l, c, v, 5, symbol=GOLD)
    same_outputs(a, b, "contract chart")
    assert len(a["days"]) == 1 and set(a["days"].exit_reason) | set(a["days"].exit2_reason) <= set(A.EXIT_REASONS)
    z = np.zeros(0)
    ea, eb = (P.orb(np.zeros(0, np.int64), z, z, z, z, z, 5, symbol=GOLD) for P in (A, B))
    same_outputs(ea, eb, "empty")
    assert ea["days"].empty and ea["days"].dtypes.equals(a["days"].dtypes)
    assert eb["days"].dtypes.equals(a["days"].dtypes)


@pytest.mark.parametrize("bad", ["float times", "reversed times", "off the grid", "M5 called M15", "tf 7", "tf 0",
                                 "tf 2.5", "nan price", "inf volume", "short o", "short v", "auto without symbol",
                                 "clock UTC-5", "clock utc-4", "days 1234567", "days weekend", "boundary exchange",
                                 "boundary NY17", "session reversed", "session past midnight", "session 570.5",
                                 "window end at start", "window end past midnight", "two multiples",
                                 "negative multiple", "nan multiple", "trail 0", "trail nan"])
def test_both_ports_refuse_the_same_inputs(bad):
    t, o, h, l, c, v = TA.base_day().arrays()
    args = dict(t=t, o=o, h=h, l=l, c=c, v=v, tf_min=5)
    kw = dict(symbol=GOLD)
    if bad == "float times":
        args["t"] = t.astype(np.float64)
    elif bad == "reversed times":
        args["t"] = t[::-1].copy()
    elif bad == "off the grid":
        args["t"] = t + 60
    elif bad == "M5 called M15":
        args["tf_min"] = 15
    elif bad == "tf 7":
        args["t"] = np.arange(len(t), dtype=np.int64) * 420 + 420 * 4_000_000
        args["tf_min"] = 7
    elif bad == "tf 0":
        args["tf_min"] = 0
    elif bad == "tf 2.5":
        args["tf_min"] = 2.5
    elif bad == "nan price":
        args["h"] = np.where(np.arange(len(h)) == 3, np.nan, h)
    elif bad == "inf volume":
        args["v"] = np.where(np.arange(len(v)) == 3, np.inf, v)
    elif bad == "short o":
        args["o"] = o[:-1]
    elif bad == "short v":
        args["v"] = v[:-1]
    elif bad == "auto without symbol":
        kw = {}
    else:
        kw.update({"clock UTC-5": dict(clock="UTC-5"), "clock utc-4": dict(clock="utc-4"),
                   "days 1234567": dict(days="1234567"), "days weekend": dict(days="weekend"),
                   "boundary exchange": dict(day_boundary="exchange"), "boundary NY17": dict(day_boundary="NY17"),
                   "session reversed": dict(sess=(600, 570)), "session past midnight": dict(sess=(570, 1500)),
                   "session 570.5": dict(sess=(570.5, 600)), "window end at start": dict(window_end=570),
                   "window end past midnight": dict(window_end=1500), "two multiples": dict(multiples=(1.0, 2.0)),
                   "negative multiple": dict(multiples=(1.0, -2.0, 3.0)),
                   "nan multiple": dict(multiples=(1.0, math.nan, 3.0)), "trail 0": dict(trail_mult=0.0),
                   "trail nan": dict(trail_mult=math.nan)}[bad])
    for P in (A, B):
        with pytest.raises(ValueError):
            P.orb(*args.values(), **kw)
