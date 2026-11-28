"""
"Wyckoff [theUltimator5]" (study 2, PREREG 6.3): the reconciliation of the two independent ports.

Port A, ``backtesting/research/tradeiq2_ind_wyckoff.py`` (numba; the production port the study imports), and port B,
``tests/tradeiq2_oracle_wyckoff.py`` (plain Python; every Pine series re-derived from its own history on every bar),
were written by two engineers from the Pine source and the specification, neither reading the other. This file runs
both on the real bars and asserts that they agree exactly. The record of the reconciliation (the Pine readings, the one
mismatch and how it was resolved, the counts, the third opinion of the specification's scratch port, what may still
differ from TradingView) is ``backtest_results/tradeiq_2027/porting/wyckoff.md``.

The bars are the study's: the M1 bars of each symbol from the study's data start (``tradeiq2_market.data_start``: gold
2016-01-01, the Early window's warm-up, so its first bar is 2016-01-03; BTC 2018-01-01) to 2024-06-30 23:59 UTC, read
with ``external.load_market(symbol, earliest=..., end="2024-07-01")`` so that nothing at or after the hold-out start is
loaded, and built into bars by study 1's ``TMarket.tbars``, which is what ``tradeiq2_market.load`` serves. They cover
every timeframe PREREG 6.3 runs (1H, 4H, 1D) and every volume series it reads: gold on tick volume; BTC on Binance
BTCUSDT volume and, for the control rows, on Exness tick volume. Gold without volume (the script's own fallback,
effort = range) is added only to exercise that branch. One symbol is in memory at a time: a module-scoped fixture is
parametrised by symbol, so pytest runs one symbol's tests before it loads the next.

1. Every contract output is identical: the same keys in the same order, the same dtypes, integers and booleans equal,
   floats bit for bit (NaN on the same bars, the same 64 bits everywhere else). No tolerance is used anywhere.
2. The event tables built from them are equal row by row: the entries (with their kind, close, hard level, campaign
   and X-S exit), the climax confirmations, the spring / UTAD recoveries and the alert bits.
3. The engine's internal series agree bit for bit. These are the bar measurements and the state-dependent values: the
   bar's pivot length, its pivots and whether they are new, the prior-trend score, the reset codes, Phase B maturity and
   the alert mask (port B's mask is read without BIT_PS, which port A does not port and nothing reads).
4. The X-S exit of every entry is the same bar under port A's reading (campaign, outcome and the hold) and port B's
   (the hold alone).
5. The API defaults that differ between the ports (``syminfo.mintick``, the chart's seconds) cannot change an output on
   these bars.
6. A later start changes nothing that is scored before the exam: gold's engine started at study 1's data start
   (2017-01-03) gives exactly the 2016 start's outputs on every bar closing after 2018-01-01, and BTC's started half a
   year late (2018-07-01) gives exactly the same outputs on every bar closing after 2019-01-01.
7. The Development (2019-2022) event counts recorded at the reconciliation are reproduced by both ports. The
   specification's unreviewed scratch port, the third opinion, puts every one of these events on the same bar.

No profit or loss is computed anywhere in this file: counts, bar times, levels and indicator values only.
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import numpy as np
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq2_ind_wyckoff as W
from backtesting.research import tradeiq2_market as TM2
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_wyckoff as O  # noqa: E402

END = "2024-07-01"                                     # exclusive: the hold-out start, never reached
TFS = ("1H", "4H", "1D")
VOLUMES = {"XAUUSDm": ("tick", "none"), "BTCUSDm": ("binance", "tick")}
DEV = (TM.s_of("2019-01-01"), TM.s_of("2023-01-01"))   # Development: bars closing in 2019-2022
MODES = ("std", "agg", "con")

# port B's per-bar locals (Engine.trace) -> port A's series (W.series) ...
STATELESS = {"eff": "eff", "spr": "spr", "avgEff": "avg", "avgEffPrev": "avgprev", "atrRaw": "atrraw", "a": "a",
             "aPrev": "aprev", "cPos": "cpos", "relE": "rele", "priorLo": "prior_lo", "priorHi": "prior_hi",
             "newLow": "newlow", "newHigh": "newhigh", "liveLen": "live", "preLen": "pre", "trendBars": "tbn",
             "trendEnd": "tbe", "sosScore": "sos", "sowScore": "sow"}
# ... and to port A's kernel columns (W.run)
STATEFUL = {"pLen": "dbg_plen", "ph": "dbg_ph", "pl": "dbg_pl", "newPL": "dbg_new_pl", "newPH": "dbg_new_ph",
            "trendScore": "dbg_trend", "resetWhy": "dbg_reset", "resetLate": "dbg_reset_late",
            "mature1": "dbg_mature1", "sig": "sig"}


# ───────────────────────────── helpers ─────────────────────────────

def bit_equal(a, b) -> bool:
    """The same shape; integers and booleans equal; floats (or a float against an integer) bit for bit: NaN on the
    same bars, the same 64 bits elsewhere, so even the sign of a zero counts. The dtypes are compared by the caller."""
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return False
    if a.dtype.kind != "f" and b.dtype.kind != "f":
        return bool(np.array_equal(a, b))
    a, b = np.ascontiguousarray(a, np.float64), np.ascontiguousarray(b, np.float64)
    na, nb = np.isnan(a), np.isnan(b)
    return bool(np.array_equal(na, nb) and np.array_equal(a[~na].view(np.uint64), b[~nb].view(np.uint64)))


def first_diff(a, b, t) -> str:
    """Where two arrays first differ (for the assertion messages)."""
    a, b = np.ascontiguousarray(a, np.float64), np.ascontiguousarray(b, np.float64)
    if a.shape != b.shape:
        return f"shapes {a.shape} and {b.shape}"
    d = np.flatnonzero(~((a.view(np.uint64) == b.view(np.uint64)) | (np.isnan(a) & np.isnan(b))))
    if not len(d):
        return "no difference"
    i = int(d[0])
    return f"{len(d)} bars differ, the first {TM.utc(int(t[i]))} (bar {i}): {a[i]!r} against {b[i]!r}"


def run_b_traced(args, no_vol: bool, mintick: float):
    """Port B's public ``wyckoff`` with its engine's trace switched on: the outputs, and per bar the locals of
    STATELESS and STATEFUL. ``Engine.trace`` is port B's own inspection hook (it only reads the bar's locals); the
    subclass is put in place of ``O.Engine`` for this one call."""
    n = len(args[3])
    rec = {k: np.full(n, np.nan) for k in (*STATELESS, *STATEFUL)}

    class Traced(O.Engine):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.trace = {}

        def step(self, *a, **kw):
            out = super().step(*a, **kw)
            tr = self.trace
            i = tr["bar_index"]
            for k, arr in rec.items():
                arr[i] = tr[k]
            return out

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(O, "Engine", Traced)
        out = O.wyckoff(*args, no_vol=no_vol, mintick=mintick)
    return out, rec


def xs_exit(out, i: int, reading: str) -> int:
    """PREREG 6.3's exit X-S of an entry at bar i: the first bar j > i whose close no longer holds the entry's
    campaign in Phases C-E with its outcome; len(bars) while it still holds at the last bar. ``reading`` "A": port A's
    contract (in_cde and the same campaign and the same outcome); "B": port B's (in_cde alone)."""
    cde, camp, outc = out["in_cde"], out["campaign"], out["outcome"]
    j, n = i + 1, len(cde)
    if reading == "A":
        while j < n and cde[j] and camp[j] == camp[i] and outc[j] == outc[i]:
            j += 1
    else:
        while j < n and cde[j]:
            j += 1
    return j


def entry_kind(out, i: int) -> str:
    return ("test" if out["ev_test"][i] else "ctest" if out["ev_ctest"][i] else
            "lps" if (out["ev_lps"][i] or out["ev_lpsy"][i]) else "sos")


def event_table(out, bars):
    """Every event a rule of PREREG 6.3 can act on, one row each; floats as hex, so equal rows are equal bits."""
    t, c = bars["t"], bars["c"]
    rows = []
    for m in MODES:
        e = out[f"entry_{m}"]
        for i in np.flatnonzero(e != 0):
            hard = out["hard_lo"][i] if e[i] > 0 else out["hard_hi"][i]
            rows.append(("entry", m, int(t[i]), int(e[i]), entry_kind(out, i), float(c[i]).hex(), float(hard).hex(),
                         int(out["campaign"][i]), xs_exit(out, int(i), "A")))
    for i in np.flatnonzero(out["climax"] != 0):
        rows.append(("climax", int(t[i]), int(out["climax"][i]), float(out["climax_px"][i]).hex()))
    for i in np.flatnonzero(out["exc"] != 0):
        confirmed = bool(out["ev_spring"][i] or out["ev_utad"][i])
        rows.append(("exc", int(t[i]), int(out["exc"][i]), float(out["exc_px"][i]).hex(), confirmed))
    for k in W.EVENT_BITS:
        rows.extend(("bit", k, int(t[i])) for i in np.flatnonzero(out[k]))
    return rows


def dev_counts(out, bars):
    """The Development counts of RECORDED's columns."""
    w = (bars["tc"] > DEV[0]) & (bars["tc"] <= DEV[1])
    bits = tuple(int(out[k][w].sum()) for k in W.EVENT_BITS)
    exc = out["exc"]
    confirmed = (exc != 0) & (out["ev_spring"] | out["ev_utad"])
    adopt = (out["ev_spring"] & out["ev_sos"]) | (out["ev_utad"] & out["ev_sow"])
    excs = (int(((exc > 0) & w).sum()), int(((exc < 0) & w).sum()), int((confirmed & w).sum()), int((adopt & w).sum()))
    entries = tuple(int(((out[f"entry_{m}"] == s) & w).sum()) for m in MODES for s in (1, -1))
    return bits + excs + entries


# ───────────────────────────── the bars and both ports' runs, one symbol at a time ─────────────────────────────

@pytest.fixture(scope="module", params=["XAUUSDm", "BTCUSDm"])
def sym(request):
    """One symbol's 1H / 4H / 1D bars from the study's data start to 2024-06-30 (the M1 bars read with an explicit
    end at the hold-out start), its volume series, and both ports' results on each series. The market is dropped once
    the bars are copied."""
    symbol = request.param
    start = TM2.data_start(symbol)
    months = set(store.available_months(symbol))
    if (2024, 6) not in months or (int(start[:4]), int(start[5:7])) not in months:
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    if symbol.startswith("BTC") and not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM2.CUT_S):
        pytest.skip("the Binance klines are not on this machine")
    m = X.load_market(symbol, earliest=start, end=END)
    mk = TM.TMarket(symbol, {"t": m.t, "o": m.o, "h": m.h, "l": m.l, "c": m.c, "spread_mean": m.sp, "n": m.n},
                    TM2.CUT_S)
    del m
    assert int(mk.t[-1]) + 60 <= TM2.CUT_S                          # nothing of the hold-out is in memory
    series = {}
    for tf in TFS:
        b = mk.tbars(tf)
        assert int(b.tc[-1]) <= TM2.CUT_S
        bars = {"t": b.t.copy(), "tc": b.tc.copy(), "o": b.o.copy(), "h": b.h.copy(), "l": b.l.copy(),
                "c": b.c.copy()}
        vols = {"tick": b.vol.astype(np.float64), "none": None}
        if symbol.startswith("BTC"):
            vols["binance"] = np.array(TM2.binance_volume(mk, tf)[0], np.float64)
        for vn in VOLUMES[symbol]:
            series[(tf, vn)] = (bars, vols[vn])
    del mk, b
    gc.collect()
    mt = W.MINTICK[symbol]
    res = {}
    for key, (bars, v) in series.items():
        no_vol = v is None
        args = (bars["o"], bars["h"], bars["l"], bars["c"], np.zeros(len(bars["c"])) if no_vol else v, bars["t"])
        pre = W.series(*args, no_vol=no_vol, mintick=mt)
        run = W.run(pre, *W.new_state(), mintick=mt, tf_seconds=W.infer_tf_seconds(bars["t"]))
        a_int = {**{ka: pre[ka] for ka in STATELESS.values()}, **{ka: run[ka] for ka in STATEFUL.values()}}
        b_out, b_int = run_b_traced(args, no_vol, mt)
        res[key] = {"A": W.wyckoff(*args, no_vol=no_vol, mintick=mt), "A_run": {k: run[k] for k in W.CONTRACT_KEYS},
                    "A_int": a_int, "B": b_out, "B_int": b_int}
        del pre, run
    data = {"symbol": symbol, "mintick": mt, "series": series, "res": res}
    yield data
    data.clear()
    gc.collect()


# ───────────────────────────── 1-2. the contract outputs and the event tables ─────────────────────────────

def test_same_contract():
    assert W.CONTRACT_KEYS == O.OUTPUT_KEYS
    assert W.EVENT_BITS == O.EVENT_BITS


def test_contract_outputs_bit_for_bit(sym):
    for (tf, vn), r in sym["res"].items():
        where = f"{sym['symbol']} {tf} {vn}"
        a, b, t = r["A"], r["B"], sym["series"][(tf, vn)][0]["t"]
        assert tuple(a) == W.CONTRACT_KEYS and set(b) == set(O.OUTPUT_KEYS), where
        for k in W.CONTRACT_KEYS:
            assert a[k].dtype == b[k].dtype, (where, k, a[k].dtype, b[k].dtype)
            assert bit_equal(a[k], b[k]), (where, k, first_diff(a[k], b[k], t))
            assert bit_equal(a[k], r["A_run"][k]), (where, k)       # the public function is the kernel's run
        assert (a["phase"] > 0).any() and (a["climax"] != 0).any(), where


def test_event_tables_row_by_row(sym):
    n_entries = 0
    for (tf, vn), r in sym["res"].items():
        bars = sym["series"][(tf, vn)][0]
        ta, tb = event_table(r["A"], bars), event_table(r["B"], bars)
        for x, y in zip(ta, tb):
            assert x == y, (sym["symbol"], tf, vn, x, y)
        assert len(ta) == len(tb), (sym["symbol"], tf, vn)
        n_entries += sum(row[0] == "entry" for row in ta)
    assert n_entries > 0


# ───────────────────────────── 3. the engine's internal series ─────────────────────────────

def test_internal_series_bit_for_bit(sym):
    """The bar measurements (L1063-1158) and the state-dependent values (the pivot length L1105, the pivots L1106-1107
    and their dedup L1319-1324, the prior-trend score L1119, the reset codes L1179-1233 / L1643-1676, Phase B maturity
    L1318, the alert mask). The one written exception: port B's mask also holds BIT_PS (preliminary support or supply,
    set at L1289-1290 on a climax confirmation). Port A does not port that tracking, because nothing reads the bit: no
    f_hasBit call and no alert (L3188-3199) ever tests BIT_PS. So port B's mask is compared without it."""
    ps_bars = 0
    for (tf, vn), r in sym["res"].items():
        where = f"{sym['symbol']} {tf} {vn}"
        t = sym["series"][(tf, vn)][0]["t"]
        for kb, ka in {**STATELESS, **STATEFUL}.items():
            x, y = r["A_int"][ka], r["B_int"][kb]
            if kb == "sig":
                ps = (y.astype(np.int64) & O.BIT_PS) != 0
                ps_bars += int(ps.sum())
                y = (y.astype(np.int64) & ~O.BIT_PS).astype(np.float64)
            assert bit_equal(np.asarray(x, np.float64), y), (where, kb, first_diff(x, y, t))
        tr = r["A_int"]["dbg_trend"]
        assert np.isfinite(tr).all() and (np.abs(tr) >= 35).any(), where
    assert ps_bars > 0                                             # the exception is exercised, not vacuous


def test_traced_port_b_is_port_b(sym):
    """The trace hook only reads the engine's locals: the plain port B gives the same outputs (1D, both volumes)."""
    for (tf, vn), (bars, v) in sym["series"].items():
        if tf != "1D":
            continue
        no_vol = v is None
        plain = O.wyckoff(bars["o"], bars["h"], bars["l"], bars["c"], v, bars["t"], no_vol=no_vol,
                          mintick=sym["mintick"])
        for k in O.OUTPUT_KEYS:
            assert bit_equal(plain[k], sym["res"][(tf, vn)]["B"][k]), (sym["symbol"], vn, k)


# ───────────────────────────── 4. the X-S exit ─────────────────────────────

def test_xs_exit_same_bar_in_both_readings(sym):
    """At every entry of every mode, port A's reading of the X-S exit (in_cde with the entry's campaign and outcome)
    and port B's (in_cde alone) give the same bar, on both ports' outputs. That holds because a run of in_cde bars
    never changes campaign or outcome. No entry fires on a bar that is not in_cde. On these bars the hold breaks while
    the outcome survives once: BTC 1H on Binance volume, 2023-11-22 00:00 (Validation), a demotion and a spring on one
    bar, the X-S exit of the Standard long of 2023-11-17 19:00."""
    odd_bars = []
    for (tf, vn), r in sym["res"].items():
        bars = sym["series"][(tf, vn)][0]
        for port in ("A", "B"):
            out = r[port]
            run = out["in_cde"][1:] & out["in_cde"][:-1]
            assert np.array_equal(out["campaign"][1:][run], out["campaign"][:-1][run]), (tf, vn, port)
            assert np.array_equal(out["outcome"][1:][run], out["outcome"][:-1][run]), (tf, vn, port)
            for m in MODES:
                for i in np.flatnonzero(out[f"entry_{m}"] != 0):
                    assert out["in_cde"][i], (tf, vn, port, m, int(i))
                    assert xs_exit(out, int(i), "A") == xs_exit(out, int(i), "B"), (tf, vn, port, m, int(i))
        odd = np.flatnonzero((r["A"]["outcome"] != 0) & ~r["A"]["in_cde"])
        odd_bars += [(tf, vn, str(TM.utc(int(bars["t"][i])))[:16]) for i in odd]
    if sym["symbol"] == "BTCUSDm":
        assert odd_bars == [("1H", "binance", "2023-11-22 00:00")]
        out = sym["res"][("1H", "binance")]["A"]
        t = sym["series"][("1H", "binance")][0]["t"]
        i, k = (int(np.searchsorted(t, TM.s_of(x))) for x in ("2023-11-22 00:00", "2023-11-17 19:00"))
        assert out["phase"][i - 1] == 4 and out["phase"][i] == 3 and out["ev_spring"][i] and out["exc"][i] == 1
        assert out["entry_std"][k] == 1 and out["campaign"][k] == out["campaign"][i]
        assert xs_exit(out, k, "A") == xs_exit(out, k, "B") == i
    else:
        assert odd_bars == []


# ───────────────────────────── 5. the API defaults ─────────────────────────────

def test_api_defaults_cannot_change_an_output(sym):
    """Port A's ``mintick`` defaults to gold's 0.001 and its chart seconds to the smallest step of the open times;
    port B infers the price grid and takes the most frequent step. On these bars the inferred grid is the repository's
    tick (0.001 gold, 0.01 BTC), the two steps are equal, and port A run with its defaults, or with the other symbol's
    tick and a 1-second chart, gives exactly the outputs above. So a caller's defaults cannot move a result here."""
    for (tf, vn), (bars, v) in sym["series"].items():
        where = f"{sym['symbol']} {tf} {vn}"
        o, h, l, c, t = bars["o"], bars["h"], bars["l"], bars["c"], bars["t"]
        assert O.infer_mintick(o, h, l, c) == sym["mintick"], where
        assert W.infer_tf_seconds(t) == O._bar_seconds(t) == TM2.TF_SECONDS[tf], where
        no_vol = v is None
        vv = np.zeros(len(c)) if no_vol else v
        base = sym["res"][(tf, vn)]["A"]
        other = 0.01 if sym["mintick"] == 0.001 else 0.001
        for kw in ({}, {"mintick": other, "tf_seconds": 1.0}):
            alt = W.wyckoff(o, h, l, c, vv, t, no_vol=no_vol, **kw)
            for k in W.CONTRACT_KEYS:
                assert bit_equal(alt[k], base[k]), (where, kw, k, first_diff(alt[k], base[k], t))


# ───────────────────────────── 6. where the bars start (gold) ─────────────────────────────

# (a later start, the first bar whose close it must not reach)
LATER_START = {"XAUUSDm": (TM.DATA_START["XAUUSDm"], "2018-01-01"), "BTCUSDm": ("2018-07-01", "2019-01-01")}


def test_a_later_start_changes_nothing_scored(sym):
    """``regime`` (L1093) and ``lastPLBar`` / ``lastPHBar`` outlive every campaign, so the outputs depend on where the
    bars start (the specification's trap 12). Gold's engine started at study 1's data start (2017-01-03) gives exactly
    the 2016 start's outputs on every bar closing after 2018-01-01: the two runs differ only inside 2017, in gold's
    Early window, so the Early exam needs the 2016 warm-up (PREREG 2) and Development and Validation do not depend
    on it. BTC's engine started half a year after its data start (2018-07-01) gives exactly the same outputs on every
    bar closing after 2019-01-01, so BTC's single start (2018-01-01) leaves at least half a year of margin. (With only
    three months, from 2018-10-01, the 1D series on Binance volume differs until May 2019.) The campaign ids are seed
    bars, so they are compared shifted by the start's offset."""
    start, after = LATER_START[sym["symbol"]]
    for (tf, vn), (bars, v) in sym["series"].items():
        k0 = int(np.searchsorted(bars["t"], TM.s_of(start)))
        assert 0 < k0 < len(bars["t"])
        cut = {k: x[k0:] for k, x in bars.items()}
        no_vol = v is None
        vv = np.zeros(len(cut["c"])) if no_vol else v[k0:]
        alt = W.wyckoff(cut["o"], cut["h"], cut["l"], cut["c"], vv, cut["t"], no_vol=no_vol, mintick=sym["mintick"])
        base = sym["res"][(tf, vn)]["A"]
        keep = cut["tc"] > TM.s_of(after)
        assert keep.sum() > 0.8 * len(keep)                          # most of the bars are compared
        for k in W.CONTRACT_KEYS:
            x = base[k][k0:]
            if k == "campaign":
                x = np.where(x >= 0, x - k0, -1)
            assert bit_equal(x[keep], alt[k][keep]), (tf, vn, k, first_diff(x[keep], alt[k][keep], cut["t"][keep]))


# ───────────────────────────── 7. the Development counts recorded at the reconciliation ─────────────────────────────

# Bars closing 2019-01-01 .. 2022-12-31. Columns: the 13 alert bits (SC, BC, AR, ST, Spring, UTAD, Test, CTest, SOS,
# SOW, LPS, LPSY, Phase E; SC / BC are the climax confirmations, the Spring / UTAD bits include the B -> D adoption
# bars), the spring / UTAD recovery bars (exc +1, exc -1), of which confirmed, the adoption bars, and the entries
# Standard long / short, Aggressive long / short, Conservative long / short. "none" = gold without volume (not a
# PREREG series).
RECORDED = {
    ("XAUUSDm", "1H", "tick"): (52, 105, 33, 65, 7, 9, 1, 1, 3, 5, 0, 2, 5, 33, 31, 14, 2, 1, 3, 4, 5, 0, 2),
    ("XAUUSDm", "1H", "none"): (81, 151, 47, 93, 9, 10, 3, 11, 7, 7, 2, 3, 8, 37, 40, 16, 3, 7, 8, 9, 8, 2, 3),
    ("XAUUSDm", "4H", "tick"): (22, 28, 6, 13, 2, 2, 1, 0, 2, 0, 1, 0, 1, 5, 6, 4, 0, 1, 1, 1, 1, 1, 0),
    ("XAUUSDm", "4H", "none"): (26, 33, 8, 20, 1, 4, 3, 0, 0, 0, 0, 0, 0, 5, 10, 5, 0, 0, 3, 0, 3, 0, 0),
    ("XAUUSDm", "1D", "tick"): (1, 5, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("XAUUSDm", "1D", "none"): (1, 11, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("BTCUSDm", "1H", "binance"): (183, 192, 69, 110, 9, 8, 7, 8, 4, 5, 2, 1, 5, 53, 69, 16, 1, 7, 7, 8, 8, 2, 1),
    ("BTCUSDm", "1H", "tick"): (30, 22, 11, 17, 1, 3, 0, 1, 0, 0, 0, 0, 0, 9, 12, 4, 0, 0, 1, 0, 1, 0, 0),
    ("BTCUSDm", "4H", "binance"): (36, 59, 12, 23, 4, 3, 3, 1, 2, 0, 1, 0, 2, 15, 10, 6, 1, 4, 1, 4, 1, 1, 0),
    ("BTCUSDm", "4H", "tick"): (7, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("BTCUSDm", "1D", "binance"): (7, 11, 4, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0),
    ("BTCUSDm", "1D", "tick"): (2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
}


def test_recorded_development_counts(sym):
    for (tf, vn), r in sym["res"].items():
        bars = sym["series"][(tf, vn)][0]
        want = RECORDED[(sym["symbol"], tf, vn)]
        for port in ("A", "B"):
            assert dev_counts(r[port], bars) == want, (sym["symbol"], tf, vn, port, dev_counts(r[port], bars))
