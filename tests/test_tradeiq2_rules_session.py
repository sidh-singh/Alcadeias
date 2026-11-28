"""
Session Hunter's rule rows (``backtesting/research/tradeiq2_rules_session.py``; study 2, PREREG 6.6 and claim 10 of
section 8): the grid, and what each row executes.

(a) THE GRID. The row counts per symbol are the PREREG's (written here from its text): on XAUUSDm and BTCUSDm the 116
    eligible rows of 6.6 (core 5 x 3 x 2 x 2 = 60, K0 x E1 10, K2 x E3 10, the presets 6, the trend rows 30) plus the
    information-only Monday variant; on the claim markets only the claim-check rows (information only). Ids, families,
    eligibility, the driver's own grid check.
(b) HAND-MADE TAPES (synthetic M1 bars, February 2019, New York on EST): for every setup its entry (the next M1 open,
    a buy at the ask, a sell at the bid), its stop (the sweep's extreme, the range's middle, from the fill) and its
    exits (E1 the 16:00 open, E2 2R from the fill, E3 the opposite liquidity), the script's cancels at entry applied
    on top of PREREG 4's absolute-level rules (a long whose bid open is at the stop, a 16:00 entry bar, E3's "less
    than 1R"), x1.5 recomputing every distance from its own fill (and dropping a fill beyond its target), the time
    exit across a data gap, the Monday quirk and its variant, the HTF confirmation (the script's 1H EMA) and the
    trend rows (F2 / F3 in its place: a refused bar does not end the setup), one trade a day per setup, the presets as
    the sum of their lanes.
(c) CAUSALITY: the entries and exit decisions before bar T do not change when the bars after T are removed.
(d) THE SMOKE TEST on real data, Development only: gold, BTC, EURUSDm and GBPUSDm 2019-01-01 to 2019-06-30, USTECm
    2020-07-01 to 2020-12-31 (its Development starts 2020-07-01; it has no 2019 bars). One variant of each rule type
    through ``tradeiq2_market.run_exec`` at x1.0 and x1.5. Its profit or loss is never printed, asserted or reported:
    only counts, timings and the run's structure are checked (PREREG: no profit or loss of a study-2 rule on real
    data before the selection).

Run: NUMBA_CACHE_DIR=<scratch> python -B -m pytest tests/test_tradeiq2_rules_session.py -q -x --assert=plain
-p no:cacheprovider
"""

from __future__ import annotations

import gc
import json

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_session as SH
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_session as R

DAY = 86400
A, Z = "2019-02-04", "2019-02-07"                     # the hand-made tapes' window (Monday to Wednesday)
VAR = {v.id: v for s in M.ALL_SYMBOLS for v in R.variants(s)}


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


# ───────────────────────────── (a) the grid ─────────────────────────────

# PREREG 6.6 "Grids": core 5 setups x K1-K3 x E1-E2 x 2 timeframes = 60; K0 x E1 (10) and K2 x E3 (10); the three
# presets x 2 timeframes (6); K2 x E1 with the 1H EMA200 replaced by F2-4H, F2-1D or F3 (30): "Size: 116 rows per
# symbol". The Monday variant ("information only"): PD x K2 x E1 x 2 timeframes. PREREG 8 claim 10: the Nasdaq preset
# and PD + HTF on USTECm M5 / M15, the Forex preset on EURUSDm and GBPUSDm M15 (information only).
PLAN = {"XAUUSDm": (116, 2), "BTCUSDm": (116, 2), "USTECm": (0, 4), "EURUSDm": (0, 1), "GBPUSDm": (0, 1)}
BLOCKS = {"core": 60, "K0 x E1": 10, "K2 x E3": 10, "preset": 6, "trend": 30, "Monday variant": 2}


def test_row_counts_are_the_preregs():
    for s, (n_elig, n_info) in PLAN.items():
        vs = R.variants(s)
        assert sum(v.eligible for v in vs) == n_elig, s
        assert sum(not v.eligible for v in vs) == n_info, s
        assert R.plan_counts(s) == {k: n for k, n in ((("SH", True), n_elig), (("SH", False), n_info)) if n}, s
    assert 60 == 5 * 3 * 2 * 2 and 116 == 60 + 10 + 10 + 6 + 30


def test_the_blocks_of_6_6():
    for s in M.SYMBOLS:
        vs = R.variants(s)
        got = pd.Series([v.params["block"] for v in vs]).value_counts().to_dict()
        assert got == BLOCKS, s
        core = [v for v in vs if v.params["block"] == "core"]
        assert {(v.tf, v.params["setups"], v.params["conf"], v.params["exit"]) for v in core} == {
            (tf, x, k, e) for tf in ("M5", "M15") for x in R.SETUPS for k in ("K1", "K2", "K3") for e in ("E1", "E2")}
        k0 = [v for v in vs if v.params["block"] == "K0 x E1"]
        assert {(v.tf, v.params["setups"], v.params["conf"], v.params["exit"]) for v in k0} == {
            (tf, x, "K0", "E1") for tf in ("M5", "M15") for x in R.SETUPS}
        e3 = [v for v in vs if v.params["block"] == "K2 x E3"]
        assert {(v.tf, v.params["setups"], v.params["conf"], v.params["exit"]) for v in e3} == {
            (tf, x, "K2", "E3") for tf in ("M5", "M15") for x in R.SETUPS}
        pr = [v for v in vs if v.params["block"] == "preset"]
        assert {(v.tf, v.params["preset"], v.params["setups"], v.params["conf"], v.params["exit"]) for v in pr} == {
            (tf, p, x, k, "E1") for tf in ("M5", "M15")
            for p, x, k in (("Custom", "AS+LS", "K2"), ("Forex", "AS", "K3"), ("Nasdaq", "LS+PD", "K2"))}
        tr = [v for v in vs if v.params["block"] == "trend"]
        assert {(v.tf, v.params["setups"], v.params["conf"], v.params["exit"], v.params["trend"]) for v in tr} == {
            (tf, x, "K2", "E1", f) for tf in ("M5", "M15") for x in R.SETUPS for f in ("F2-4H", "F2-1D", "F3")}
        mon = [v for v in vs if v.params["block"] == "Monday variant"]
        assert {(v.tf, v.params["setups"], v.params["conf"], v.params["exit"], v.params["monday"]) for v in mon} == {
            (tf, "PD", "K2", "E1", "friday") for tf in ("M5", "M15")}
        assert all(v.params["monday"] == "quirk" for v in vs if v.params["block"] != "Monday variant")


def test_claim_rows():
    got = {s: sorted(v.id for v in R.variants(s)) for s in M.CLAIM_SYMBOLS}
    assert got == {"USTECm": sorted(["USTECm|M5|SH|PRESET-NASDAQ|K2|E1", "USTECm|M15|SH|PRESET-NASDAQ|K2|E1",
                                     "USTECm|M5|SH|PD|HTF|E1", "USTECm|M15|SH|PD|HTF|E1"]),
                   "EURUSDm": ["EURUSDm|M15|SH|PRESET-FOREX|K3|E1"], "GBPUSDm": ["GBPUSDm|M15|SH|PRESET-FOREX|K3|E1"]}
    pd_htf = VAR["USTECm|M5|SH|PD|HTF|E1"]
    assert pd_htf.params["confirmations"] == "HTF" and pd_htf.params["trend"] == "EMA200-1H"   # no FVG
    with pytest.raises(ValueError):
        R.variants("XAGUSDm")


def test_ids_fields_and_eligibility():
    for s in M.ALL_SYMBOLS:
        vs = R.variants(s)
        ids = [v.id for v in vs]
        assert len(ids) == len(set(ids)), s
        for v in vs:
            assert v.id.startswith(f"{s}|{v.tf}|SH|") and not any(ch.isspace() for ch in v.id), v.id
            assert (v.symbol, v.script, v.family) == (s, "SH", "SH") and v.tf in ("M5", "M15"), v.id
            json.dumps(dict(v.params))
            assert v.ident()["vid"] == v.id
            info_row = s in M.CLAIM_SYMBOLS or v.params["block"] == "Monday variant"
            assert bool(v.eligible) is (not info_row), v.id
            assert (v.info.startswith("information only") if info_row else v.info == ""), v.id
            if v.params["preset"]:
                # a preset's id names no single setup, and its params join its setups ('AS+LS'): the driver reads
                # the AS rows as the rows carrying the token AS
                assert not set(v.id.split("|")) & set(R.SETUPS), v.id
                assert v.params["setups"] == "+".join(R.PRESETS[v.params["preset"]][0]), v.id
                assert int(v.params["lanes"]) == len(R.PRESETS[v.params["preset"]][0]), v.id
    # the driver's pairings: E1 against E2 (core) and against E3 (K2) by swapping one token
    g = set(VAR)
    for s in M.SYMBOLS:
        for tf in ("M5", "M15"):
            for x in R.SETUPS:
                for k in ("K1", "K2", "K3"):
                    assert f"{s}|{tf}|SH|{x}|{k}|E2" in g and f"{s}|{tf}|SH|{x}|{k}|E1" in g
                assert f"{s}|{tf}|SH|{x}|K2|E3" in g
                for f in R.TREND_FILTERS:
                    assert f"{s}|{tf}|SH|{x}|K2|E1|{f}" in g and VAR[f"{s}|{tf}|SH|{x}|K2|E1|{f}"].params["filter"] == f


def test_the_drivers_grid_check_accepts_the_module():
    D = pytest.importorskip("backtesting.research.tradeiq2")
    grid, pairs = D.checked_grid({"session": R})
    rep = D.count_report(grid, D.PREREG_COUNTS, ["session"])
    assert set(rep.status) <= {"ok", "not checked"}
    assert int(rep[(rep.symbol == "XAUUSDm") & rep.eligible].got.iloc[0]) == 116
    assert len(pairs) == 118 * 2 + 6


def test_build_refuses_rows_that_are_not_the_plans():
    mk = Tape(A, Z).market()
    ctx = M.Context(mk)
    with pytest.raises(ValueError):
        R.build(M.Variant("XAUUSDm|M5|SH|AS|K9|E1", "XAUUSDm", "M5", "SH", "SH"), ctx)
    with pytest.raises(ValueError):
        R.build(VAR["BTCUSDm|M5|SH|AS|K1|E1"], ctx)                  # a BTC row on a gold market
    with pytest.raises(ValueError):
        R.signal_table(ctx, "1H", "K1")
    with pytest.raises(ValueError):
        R.signal_table(ctx, "M5", "K1", "F2-4H")                      # K1 reads no trend


# ───────────────────────────── (b) hand-made tapes ─────────────────────────────

def ny(date: str, hhmm: str) -> int:
    """UTC epoch second of New York wall-clock ``hhmm`` on ``date``."""
    h, m = map(int, hhmm.split(":"))
    return int(M.utc_of_ny(TM.s_of(date) // DAY, h * 60 + m))


def ny_of(ts) -> str:
    return pd.Timestamp(ts).tz_convert("America/New_York").strftime("%a %H:%M")


class Tape:
    """M1 bars around the clock from ``start`` to ``end``: a flat base (open = close = base, high / low = base +/-
    half), a constant spread, and hand-set M5 (or longer) bars whose M1 bars walk open -> first extreme -> second
    extreme -> close."""

    def __init__(self, start, end, base=100.0, half=0.3, sp=0.1):
        self.t = np.arange(TM.s_of(start), TM.s_of(end), 60, dtype=np.int64)
        n = len(self.t)
        self.o = np.full(n, float(base))
        self.c = self.o.copy()
        self.h = self.o + half
        self.l = self.o - half
        self.sp = np.full(n, float(sp))
        self.keep = np.ones(n, bool)
        self.half = half

    def ix(self, t) -> int:
        return int(np.searchsorted(self.t, t))

    def level(self, t0, t1, base, half=None):
        half = self.half if half is None else half
        a, z = self.ix(t0), self.ix(t1)
        self.o[a:z] = self.c[a:z] = base
        self.h[a:z], self.l[a:z] = base + half, base - half

    def bar(self, t_open, O, H, L, C, first="high", minutes=5):
        pts = ([O, H, L, C] if first == "high" else [O, L, H, C]) + [C] * (minutes - 3)
        a = self.ix(t_open)
        for k in range(minutes):
            o, c = pts[k], pts[k + 1]
            self.o[a + k], self.c[a + k] = o, c
            self.h[a + k], self.l[a + k] = max(o, c), min(o, c)

    def cut(self, t0, t1):
        self.keep[self.ix(t0):self.ix(t1)] = False

    def market(self, symbol="XAUUSDm"):
        k = self.keep
        return M.TMarket2(symbol, {"t": self.t[k], "o": self.o[k], "h": self.h[k], "l": self.l[k], "c": self.c[k],
                                   "spread_mean": self.sp[k], "n": np.ones(int(k.sum()))})


TUE = "2019-02-05"


def tape_a(spike=True, k3=True, ls=False):
    """Tuesday 5 Feb 2019. The first hour (the Sunday pseudo-day) at 110, so the 1H EMA200 stays above the price for
    days (HTF: shorts only). Asia (Monday 20:00-24:00): the base, with a low of 97.5 at 21:00 when ``spike``. The AS
    window: a sweep of the Asia high at 02:05 (high 101, close 100.2 back inside, no FVG yet), then X (02:10), Z
    (02:15) and Y (02:20) with Y's high below X's low: a bearish FVG, Y closing at 100.0 inside. ``k3``: at 02:30 a
    close of 99.4 below the five lows before, with an FVG two bars back (K3's signal). A drop to 97.0 at 06:00 (E2's
    98.0 and E3's 97.5 are touched in its first M1 bar). ``ls``: a sweep of the London high (101.0) at 08:00 to 101.5
    with the same FVG pattern at 08:05-08:15 (LS's short signal; it also stops the AS shorts, whose stop is 101.0)."""
    tp = Tape(A, Z)
    tp.level(TM.s_of(A), TM.s_of(A) + 3600, 110.0)
    if spike:
        tp.bar(ny("2019-02-04", "21:00"), 100.0, 100.3, 97.5, 100.0, first="low")
    tp.bar(ny(TUE, "02:05"), 100.0, 101.0, 99.9, 100.2)
    tp.bar(ny(TUE, "02:10"), 100.22, 100.28, 100.20, 100.25)
    tp.bar(ny(TUE, "02:15"), 100.2, 100.22, 100.0, 100.05)
    tp.bar(ny(TUE, "02:20"), 100.05, 100.1, 99.95, 100.0)
    if k3:
        tp.bar(ny(TUE, "02:30"), 100.0, 100.05, 99.3, 99.4)
    tp.bar(ny(TUE, "06:00"), 100.0, 100.0, 97.0, 99.0, first="low")
    if ls:
        tp.bar(ny(TUE, "08:00"), 100.0, 101.5, 99.9, 100.2)
        tp.bar(ny(TUE, "08:05"), 100.22, 100.28, 100.20, 100.25)
        tp.bar(ny(TUE, "08:10"), 100.2, 100.22, 100.0, 100.05)
        tp.bar(ny(TUE, "08:15"), 100.05, 100.1, 99.95, 100.0)
    return tp


def tape_ls_long(first=90.0):
    """LS long: the London range is the base (99.7-100.3); at 08:00 a sweep of its low to 99.0 closing at 100.0
    inside; then X (08:05, high 99.8), Z, and Y (08:15, low 99.9 above X's high: a bullish FVG, close 100.0). The
    first hour at ``first`` puts the 1H EMA below (90: longs pass HTF) or above (110: they fail)."""
    tp = Tape(A, Z)
    tp.level(TM.s_of(A), TM.s_of(A) + 3600, first)
    tp.bar(ny(TUE, "08:00"), 100.0, 100.1, 99.0, 100.0, first="low")
    tp.bar(ny(TUE, "08:05"), 99.78, 99.8, 99.72, 99.75, first="low")
    tp.bar(ny(TUE, "08:10"), 99.8, 100.0, 99.78, 99.95, first="low")
    tp.bar(ny(TUE, "08:15"), 99.95, 100.05, 99.9, 100.0, first="low")
    return tp


def tape_ab_long(sp_fill=0.1):
    """AB long with a bullish FVG and the EMA below (first hour 90): the 03:00 bar gaps above the Asia range (low
    100.31 > the high two bars before, 100.3) and closes at 100.4; the stop is the range's middle 100.0 (0.4 from the
    close, more than 0.5 ATR); tgtRef = 100.3 + 0.6 = 100.9. The base then sits at 100.4 (lows 100.1: no stop); at 06:00
    a rally to 101.6 in the bar's second M1 bar; then the base at 101.0. ``sp_fill``: the spread of the fill's M1 bar
    (03:05)."""
    tp = Tape(A, Z)
    tp.level(TM.s_of(A), TM.s_of(A) + 3600, 90.0)
    tp.bar(ny(TUE, "03:00"), 100.32, 100.45, 100.31, 100.4, first="low")
    tp.level(ny(TUE, "03:05"), ny(TUE, "16:30"), 100.4)
    tp.bar(ny(TUE, "06:00"), 100.4, 101.6, 100.3, 101.0, first="low")
    tp.level(ny(TUE, "06:05"), ny(TUE, "16:30"), 101.0)
    tp.sp[tp.ix(ny(TUE, "03:05"))] = sp_fill
    return tp


def tape_or():
    """OR short: the opening range 09:30-10:00 is the base (99.7-100.3); the 10:30 bar closes at 99.2 below it; the
    stop is the middle 100.0; then the base at 99.2 (highs 99.5: no stop)."""
    tp = Tape(A, Z)
    tp.bar(ny(TUE, "10:30"), 100.0, 100.05, 99.1, 99.2)
    tp.level(ny(TUE, "10:35"), ny(TUE, "23:00"), 99.2)
    return tp


def run(mk, ctx, vid, cost=1.0, a=A, z=Z):
    return M.run_exec(mk, R.build(VAR[vid], ctx), a, z, cost)


def one(r):
    assert len(r.trades) == 1, f"{len(r.trades)} trades"
    return r.trades.iloc[0]


def near(x, y, tol=1e-9) -> bool:
    return abs(float(x) - float(y)) < tol


def at(tr, entry=None, exit=None):
    """(the New York entry time, the New York exit time, the exit reason) of a trade row, and its prices checked."""
    if entry is not None:
        assert near(tr.entry, entry), f"entry {tr.entry} != {entry}"
    if exit is not None:
        assert near(tr.exit, exit), f"exit {tr.exit} != {exit}"
    return ny_of(tr.entry_time), ny_of(tr.exit_time), tr.reason


def test_as_fade_entry_stop_and_the_16h_exit():
    """AS short (fade of an Asia-high sweep): K0 signals at the sweep bar itself (02:05, closes back inside), K1 / K2
    only at Y (02:20), when the FVG exists (a failed confirmation did not end the setup), K3 at 02:30 (MSS). The
    entry is the next M1 open, a sell at the bid; the stop is the sweep's extreme 101.0, measured from the fill; E1
    exits at the open of the 16:00 bar, a buy at the ask (100.0 + 0.1)."""
    mk = tape_a().market()
    ctx = M.Context(mk)
    want = {"K0": ("Tue 02:10", 100.22), "K1": ("Tue 02:25", 100.0), "K2": ("Tue 02:25", 100.0),
            "K3": ("Tue 02:35", 100.0)}
    for k, (t_in, px) in want.items():
        tr = one(run(mk, ctx, f"XAUUSDm|M5|SH|AS|{k}|E1"))
        assert at(tr, px, 100.1) == (t_in, "Tue 16:00", "signal") and tr.side == -1, k
        assert near(tr.risk, 101.0 - px), k                            # |fill - the stop level|
        assert tr.tag == R.SETUPS.index("AS") and tr.lane == 0, k
    sig = R.signal_table(ctx, "M5", "K2")
    b = ctx.bars("M5")
    i = int(np.flatnonzero(sig["setup"] == R.SETUPS.index("AS"))[0])
    assert ny_of(pd.Timestamp(int(b.t[sig["bar"][i]]), unit="s", tz="UTC")) == "Tue 02:20"
    assert near(sig["stop"][i], 101.0) and near(sig["tgt_ref"][i], 97.5) and sig["dir"][i] == -1
    assert R.trend_dir(ctx, "M5")[sig["bar"][i]] == -1                  # the 1H EMA200 is above: HTF allows shorts


def test_e2_is_2r_from_the_fill_and_e3_the_opposite_side():
    """E2: 100.0 - 2 x 1.0 = 98.0; E3: the Asia low 97.5. Both are touched in the first M1 bar of the 06:00 drop."""
    mk = tape_a().market()
    ctx = M.Context(mk)
    for vid in ("XAUUSDm|M5|SH|AS|K1|E2", "XAUUSDm|M5|SH|AS|K2|E2"):
        tr = one(run(mk, ctx, vid))
        assert at(tr, 100.0, 98.0) == ("Tue 02:25", "Tue 06:00", "target") and near(tr.r, 2.0), vid
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AS|K2|E3"))
    assert at(tr, 100.0, 97.5) == ("Tue 02:25", "Tue 06:00", "target") and near(tr.r, 2.5)
    # without the Asia low spike the far side (99.7) is 0.3 from the entry open, less than 1R (1.0): E3 cancels
    # (the script's own decision, L437), E1 trades
    mk2 = tape_a(spike=False).market()
    ctx2 = M.Context(mk2)
    assert len(run(mk2, ctx2, "XAUUSDm|M5|SH|AS|K2|E3").trades) == 0
    assert len(run(mk2, ctx2, "XAUUSDm|M5|SH|AS|K2|E1").trades) == 1
    sig = R.signal_table(ctx2, "M5", "K2")
    keep, cnt = R.lane_mask(sig, "AS", "E3")
    assert cnt == {"signals": 1, "cancelled": 0, "e3_cancelled": 1, "kept": 0} and not keep.any()
    assert R.lane_mask(sig, "AS", "E1")[1]["kept"] == 1 and R.lane_mask(sig, "AS", "E2")[1]["kept"] == 1


def test_the_stop_at_the_sweep_extreme_is_charged_one_spread():
    """The London sweep at 08:00 reaches 101.5: the AS short's stop (101.0) fills at its level plus one spread."""
    mk = tape_a(ls=True).market()
    ctx = M.Context(mk)
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AS|K2|E1"))
    assert at(tr, 100.0, 101.1) == ("Tue 02:25", "Tue 08:00", "stop") and near(tr.r, -1.1)


def test_ls_long_fills_at_the_ask_and_the_htf_confirmation():
    """LS long: the sweep bar (08:00) closes back inside, so K0 enters at X's first M1 open (ask 99.78 + 0.1); K1 and
    K2 at 08:20 after the FVG (ask 100.1, x1.5: 100.15), the stop 99.0 measured from each fill. HTF reads the script's
    1H EMA200: below the price (first hour 90) K2 takes the long, above it (first hour 110) K2 refuses it, K1 not."""
    mk = tape_ls_long(90.0).market()
    ctx = M.Context(mk)
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|LS|K0|E1"))
    assert at(tr, 99.88, 100.0) == ("Tue 08:05", "Tue 16:00", "signal") and tr.side == 1
    for k in ("K1", "K2"):
        for cost, fill in ((1.0, 100.1), (1.5, 100.15)):
            tr = one(run(mk, ctx, f"XAUUSDm|M5|SH|LS|{k}|E1", cost))
            assert at(tr, fill, 100.0) == ("Tue 08:20", "Tue 16:00", "signal"), (k, cost)
            assert near(tr.risk, fill - 99.0), (k, cost)
    assert R.trend_dir(ctx, "M5").max() == 1
    mk2 = tape_ls_long(110.0).market()
    ctx2 = M.Context(mk2)
    assert len(run(mk2, ctx2, "XAUUSDm|M5|SH|LS|K1|E1").trades) == 1
    assert len(run(mk2, ctx2, "XAUUSDm|M5|SH|LS|K2|E1").trades) == 0
    assert len(run(mk2, ctx2, "XAUUSDm|M5|SH|PRESET-CUSTOM|K2|E1").trades) == 0
    # the script's own 1H trend: sign(close - the 1H EMA200 as of the chart bar's open)
    b = ctx2.bars("M5")
    assert np.array_equal(R.trend_dir(ctx2, "M5"), SH.htf_ema_dir(b.t, b.c, ctx2.bars("1H")))


def test_a_long_whose_bid_open_is_at_the_stop_is_cancelled_as_the_script_does():
    """AB long at 03:00 (close 100.8, stop the range's middle 100.0); the next bar opens at 99.95: the script cancels
    (its open at or beyond the stop, L433), though the ask (100.05) is above the stop, so PREREG 4's rule alone would
    have taken it. The study applies the script's cancel on top."""
    tp = Tape(A, Z)
    tp.bar(ny(TUE, "03:00"), 100.0, 100.9, 99.95, 100.8, first="low")
    i = tp.ix(ny(TUE, "03:05"))
    tp.o[i], tp.h[i], tp.l[i], tp.c[i] = 99.95, 100.3, 99.7, 100.0
    mk = tp.market()
    ctx = M.Context(mk)
    sig = R.signal_table(ctx, "M5", "K0")
    j = int(np.flatnonzero(sig["setup"] == R.SETUPS.index("AB"))[0])
    assert sig["dir"][j] == 1 and near(sig["stop"][j], 100.0) and sig["cancel"][j] == "open_beyond_stop"
    r = run(mk, ctx, "XAUUSDm|M5|SH|AB|K0|E1")
    assert len(r.trades) == 0 and r.counts["candidates"] == 0
    raw = M.entries(sig["bar"][[j]], sig["dir"][[j]], stop_level=sig["stop"][[j]])
    r2 = M.run_exec(mk, M.event_exec("M5", entries=raw), A, Z)        # the harness alone
    assert r2.counts["taken"] == 1 and r2.counts["dropped_stop"] == 0
    assert R.lane_mask(sig, "AB", "E1")[1] == {"signals": 1, "cancelled": 1, "e3_cancelled": 0, "kept": 0}


def test_an_entry_bar_from_16h_is_cancelled():
    """OR short at 11:55; no bars from 12:00 to 16:05: the entry bar opens at 16:05, in the 16:00-20:00 period."""
    tp = Tape(A, Z)
    tp.bar(ny(TUE, "11:55"), 100.0, 100.05, 99.1, 99.2)
    tp.cut(ny(TUE, "12:00"), ny(TUE, "16:05"))
    mk = tp.market()
    ctx = M.Context(mk)
    sig = R.signal_table(ctx, "M5", "K0")
    assert list(sig["cancel"][sig["setup"] == R.SETUPS.index("OR")]) == ["closeT"]
    assert len(run(mk, ctx, "XAUUSDm|M5|SH|OR|K0|E1").trades) == 0


def test_pd_the_monday_quirk_and_the_friday_variant():
    """PD with K2 (bearish FVG, the EMA above). Friday's range is the base; Monday 03:00 sweeps Friday's high (100.3)
    to 100.8, Tuesday 03:00 sweeps Monday's high (100.8) to 101.2, each with the FVG pattern. As coded, Monday's
    previous day is the weekend pseudo-day, so PD never trades on Monday (L199, L362); the information-only variant
    gives Monday Friday's levels."""
    tp = Tape("2019-02-01", "2019-02-06")
    tp.level(TM.s_of("2019-02-01"), TM.s_of("2019-02-01") + 3600, 110.0)
    for d, hi in (("2019-02-04", 100.8), ("2019-02-05", 101.2)):
        tp.bar(ny(d, "03:00"), 100.0, hi, 99.9, 100.2)
        tp.bar(ny(d, "03:05"), 100.22, 100.28, 100.20, 100.25)
        tp.bar(ny(d, "03:10"), 100.2, 100.22, 100.0, 100.05)
        tp.bar(ny(d, "03:15"), 100.05, 100.1, 99.95, 100.0)
    mk = tp.market()
    ctx = M.Context(mk)
    a, z = "2019-02-01", "2019-02-06"
    r = run(mk, ctx, "XAUUSDm|M5|SH|PD|K2|E1", a=a, z=z)
    assert [ny_of(x) for x in r.trades.entry_time] == ["Tue 03:20"]
    assert near(r.trades.risk.iloc[0], 1.2)                            # Tuesday's stop: the sweep's 101.2
    r = run(mk, ctx, "XAUUSDm|M5|SH|PD|K2|E1|MON-FRI", a=a, z=z)
    assert [ny_of(x) for x in r.trades.entry_time] == ["Mon 03:20", "Tue 03:20"]
    assert np.allclose(r.trades.risk, [0.8, 1.2]) and set(r.trades.reason) == {"signal"}
    b = ctx.bars("M5")
    ds = SH.day_state(b.t, b.o, b.h, b.l, b.c, 5)
    mon = (ds.day_key == TM.s_of("2019-02-04") // DAY).to_numpy()
    assert not ds.p_wk[mon].any() and np.allclose(ds.pdh[mon], 100.3)  # Monday holds Friday's high, unused


def test_breakout_targets_and_x15_recomputing_every_distance():
    """AB long (stop 100.0, tgtRef 100.9): E1 holds to 16:00; E2's target is 2R from each run's own fill (x1.0: fill
    100.5, target 101.5, touched at 06:01; x1.5: fill 100.55, target 101.65, not touched); E3's absolute target 100.9
    is the same level in both runs. With a 0.4 spread on the fill's M1 bar the x1.5 fill (101.0) is beyond E3's
    target: dropped (PREREG 4), while the x1.0 fill (100.8) is taken."""
    mk = tape_ab_long().market()
    ctx = M.Context(mk)
    for cost, fill in ((1.0, 100.5), (1.5, 100.55)):
        tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AB|K2|E1", cost))
        assert at(tr, fill, 101.0) == ("Tue 03:05", "Tue 16:00", "signal") and tr.side == 1, cost
        assert near(tr.risk, fill - 100.0), cost
        tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AB|K2|E3", cost))
        assert at(tr, fill, 100.9) == ("Tue 03:05", "Tue 06:01", "target"), cost
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AB|K2|E2", 1.0))
    assert at(tr, 100.5, 101.5) == ("Tue 03:05", "Tue 06:01", "target") and near(tr.r, 2.0)
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AB|K2|E2", 1.5))
    assert at(tr, 100.55, 101.0) == ("Tue 03:05", "Tue 16:00", "signal")
    sig = R.signal_table(ctx, "M5", "K2")
    j = int(np.flatnonzero(sig["setup"] == R.SETUPS.index("AB"))[0])
    assert near(sig["stop"][j], 100.0) and near(sig["tgt_ref"][j], 100.9) and not sig["e3_cancel"][j]
    mk2 = tape_ab_long(sp_fill=0.4).market()
    ctx2 = M.Context(mk2)
    r1 = run(mk2, ctx2, "XAUUSDm|M5|SH|AB|K2|E3", 1.0)
    r15 = run(mk2, ctx2, "XAUUSDm|M5|SH|AB|K2|E3", 1.5)
    assert near(one(r1).entry, 100.8) and r1.counts["dropped_target"] == 0
    assert len(r15.trades) == 0 and r15.counts["dropped_target"] == 1 and r15.counts["candidates"] == 1
    assert len(run(mk2, ctx2, "XAUUSDm|M5|SH|AB|K2|E1", 1.5).trades) == 1


def test_or_breakout_on_m5_and_m15():
    """OR short: on M5 the 10:30 bar closes below the range, on M15 the 10:30-10:45 bar does; entry at the next M1
    open (a sell at the bid 99.2), stop the middle 100.0, out at 16:00 (a buy at the ask 99.3)."""
    mk = tape_or().market()
    ctx = M.Context(mk)
    for tf, t_in in (("M5", "Tue 10:35"), ("M15", "Tue 10:45")):
        tr = one(run(mk, ctx, f"XAUUSDm|{tf}|SH|OR|K0|E1"))
        assert at(tr, 99.2, 99.3) == (t_in, "Tue 16:00", "signal") and tr.side == -1, tf
        assert near(tr.risk, 0.8), tf


def test_the_time_exit_across_a_gap():
    """No bars from 15:00 to 20:00: the first bar after the entry that starts the 16:00 period or a new day is the
    20:00 bar (a new trading day); the decision at the close of the bar before it fills at its open (reading 1)."""
    tp = tape_or()
    tp.cut(ny(TUE, "15:00"), ny(TUE, "20:00"))
    mk = tp.market()
    ctx = M.Context(mk)
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|OR|K0|E1"))
    assert at(tr, 99.2, 99.3) == ("Tue 10:35", "Tue 20:00", "signal")
    b = ctx.bars("M5")
    tx = R.time_exits(ctx, "M5")
    e = int(np.searchsorted(b.t, ny(TUE, "10:35")))
    assert ny_of(pd.Timestamp(int(b.t[tx[e]]), unit="s", tz="UTC")) == "Tue 14:55"     # the last bar before the gap
    assert tx[len(b)] == -1


def test_presets_are_the_sum_of_their_lanes():
    """Custom = AS + LS, Nasdaq = LS + PD (K2, E1), each setup its own lane, summed: the AS short from 02:25 (stopped
    at 08:00 by the London sweep), the PD short from 02:25 (the same sweep of yesterday's high, also stopped), the LS
    short from 08:20 to 16:00. Forex (AS, K3, E1) has one lane: the trades and scores of AS x K3 x E1. (Lanes open
    at the same time: the random walk below.)"""
    mk = tape_a(ls=True).market()
    ctx = M.Context(mk)
    for preset, rows in (("CUSTOM", ("AS", "LS")), ("NASDAQ", ("LS", "PD"))):
        ex = R.build(VAR[f"XAUUSDm|M5|SH|PRESET-{preset}|K2|E1"], ctx)
        assert ex.kind == "lanes" and len(ex.lanes) == 2
        assert [x.label for x in ex.lanes] == [f"XAUUSDm|M5|SH|PRESET-{preset}|K2|E1#{s}" for s in rows]
        for cost in (1.0, 1.5):
            r = M.run_exec(mk, ex, A, Z, cost)
            parts = [run(mk, ctx, f"XAUUSDm|M5|SH|{s}|K2|E1", cost) for s in rows]
            assert len(r.trades) == sum(len(p.trades) for p in parts) == 2, (preset, cost)
            assert near(r.net, sum(p.net for p in parts)), (preset, cost)
            assert sorted(r.trades.lane) == [0, 1]
            for q, p in enumerate(parts):
                mine = r.trades[r.trades.lane == q]
                assert np.allclose(mine.pnl.to_numpy(), p.trades.pnl.to_numpy()), (preset, q)
                assert list(mine.entry_time) == list(p.trades.entry_time), (preset, q)
    r = M.run_exec(mk, R.build(VAR["XAUUSDm|M5|SH|PRESET-CUSTOM|K2|E1"], ctx), A, Z)
    curve, summ = M.account_curve(r)                                   # the multi-position account (PREREG 4)
    assert summ["positions"] == 2 and len(curve) > 0
    fx = M.run_exec(mk, R.build(VAR["XAUUSDm|M5|SH|PRESET-FOREX|K3|E1"], ctx), A, Z)
    k3 = run(mk, ctx, "XAUUSDm|M5|SH|AS|K3|E1")
    assert fx.kind == "lanes" and len(fx.trades) == len(k3.trades) == 1
    assert fx.net == k3.net and fx.max_dd == k3.max_dd and ny_of(fx.trades.entry_time.iloc[0]) == "Tue 02:35"
    s_fx, s_k3 = M.scores(fx), M.scores(k3)
    assert all(s_fx[k] == s_k3[k] or (s_fx[k] != s_fx[k] and s_k3[k] != s_k3[k])
               for k in ("net", "trades", "max_dd", "profit_dd", "win_rate", "avg_r"))


def test_the_trend_rows_replace_the_htf_confirmation():
    """K2 x E1 with the 1H EMA200 replaced by F2-4H (here hand-set masks put in the Context's filter cache): the
    filter's side is read where the EMA's was. It refuses the short at Y (02:20) and allows it from 02:25: the setup
    is not over, and the next bar inside the range with the FVG still in its last four groups signals."""
    mk = tape_a().market()
    ctx = M.Context(mk)
    b = ctx.bars("M5")
    n = len(b)
    i20 = int(np.searchsorted(b.t, ny(TUE, "02:20")))
    al, ash = np.zeros(n, bool), np.ones(n, bool)
    ash[i20] = False
    got = ctx.get("filter", "M5", {"name": "F2-4H"}, lambda: (al, ash))
    assert got[1] is ash and ctx.allow("M5", "F2-4H")[1] is ash        # the key tradeiq2_filters.allow reads
    assert np.array_equal(R.trend_dir(ctx, "M5", "F2-4H"), al.astype(np.int8) - ash.astype(np.int8))
    tr = one(run(mk, ctx, "XAUUSDm|M5|SH|AS|K2|E1|F2-4H"))
    assert at(tr, 100.0)[0] == "Tue 02:30"
    assert at(one(run(mk, ctx, "XAUUSDm|M5|SH|AS|K2|E1")), 100.0)[0] == "Tue 02:25"
    ctx2 = M.Context(mk)                                                # a filter that never allows shorts
    ctx2.get("filter", "M5", {"name": "F3"}, lambda: (np.ones(n, bool), np.zeros(n, bool)))
    assert len(run(mk, ctx2, "XAUUSDm|M5|SH|AS|K2|E1|F3").trades) == 0
    assert len(run(mk, ctx2, "XAUUSDm|M5|SH|AS|K1|E1").trades) == 1


def test_the_claim_row_pd_htf_reads_the_1h_trend_alone():
    """Claim 10's "PD + HTF" on a synthetic USTECm tape inside its Development (July 2020, New York on EDT): the
    Sunday pseudo-day at 110 (the 1H EMA above: shorts), Tuesday 03:00 sweeps Monday's high (100.3) to 100.8 and
    closes back inside, without an FVG; X, Z, Y then form one. PD + HTF (no FVG) signals at the sweep bar, the Nasdaq
    preset's PD lane (K2: FVG + HTF) at Y; its LS lane has no London sweep."""
    tp = Tape("2020-07-05 22:00", "2020-07-09")
    tp.level(TM.s_of("2020-07-05 22:00"), TM.s_of("2020-07-05 23:00"), 110.0)
    d = "2020-07-07"
    tp.bar(ny(d, "03:00"), 100.0, 100.8, 99.9, 100.2)
    tp.bar(ny(d, "03:05"), 100.22, 100.28, 100.20, 100.25)
    tp.bar(ny(d, "03:10"), 100.2, 100.22, 100.0, 100.05)
    tp.bar(ny(d, "03:15"), 100.05, 100.1, 99.95, 100.0)
    mk = tp.market("USTECm")
    ctx = M.Context(mk)
    a, z = "2020-07-06", "2020-07-09"
    for tf in ("M5",):
        tr = one(run(mk, ctx, f"USTECm|{tf}|SH|PD|HTF|E1", a=a, z=z))
        assert at(tr, 100.22, 100.1) == ("Tue 03:05", "Tue 16:00", "signal") and tr.side == -1
        assert near(tr.risk, 100.8 - 100.22)
        r = run(mk, ctx, f"USTECm|{tf}|SH|PRESET-NASDAQ|K2|E1", a=a, z=z)
        assert r.kind == "lanes" and len(r.trades) == 1 and int(r.trades.lane.iloc[0]) == 1      # lanes: LS, PD
        assert at(r.trades.iloc[0], 100.0, 100.1) == ("Tue 03:20", "Tue 16:00", "signal")
    with pytest.raises(M.HoldOutError):                                  # USTECm is never scored before 2020-07-01
        M.run_exec(mk, R.build(VAR["USTECm|M5|SH|PD|HTF|E1"], ctx), "2020-06-30", z)


# ───────────────────────────── random tapes: one trade a day, the filters' sides, causality ─────────────────────

def random_m1(days=30, seed=11, start="2019-02-03", phi=0.998, s=0.05, gaps=8):
    """A mean-reverting walk around 100, around the clock, with ``gaps`` random holes (30-300 minutes): many sweeps,
    closes back inside and breakouts every day."""
    rng = np.random.default_rng(seed)
    t = TM.s_of(start) + 60 * np.arange(days * 1440, dtype=np.int64)
    n = len(t)
    e = rng.normal(0.0, s, n)
    x = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = phi * acc + e[i]
        x[i] = acc
    c = 100.0 + x
    o = np.concatenate(([100.0], c[:-1])) + rng.normal(0.0, 0.005, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0.0, 0.02, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0.0, 0.02, n))
    keep = np.ones(n, bool)
    for _ in range(gaps):
        a = int(rng.integers(0, n - 400))
        keep[a:a + int(rng.integers(30, 300))] = False
    return {"t": t[keep], "o": o[keep], "h": h[keep], "l": lo[keep], "c": c[keep],
            "spread_mean": np.full(int(keep.sum()), 0.02), "n": np.ones(int(keep.sum()))}


@pytest.fixture(scope="module")
def walk():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        m1 = random_m1()
        mk = M.TMarket2("XAUUSDm", m1)
    return m1, mk


def _rows(symbol="XAUUSDm", blocks=("core", "K0 x E1", "K2 x E3", "trend", "Monday variant")):
    return [v for v in R.variants(symbol) if v.params["block"] in blocks]


def test_one_trade_a_day_per_setup_and_the_time_exit(walk):
    """Every lane takes at most one trade per trading day (the script's done flag), never meets an open position
    (busy = 0), and its trade is out by the time exit (the open after the 16:00 period starts or a new day)."""
    _, mk = walk
    ctx = M.Context(mk)
    n_trades = 0
    for v in _rows(blocks=("core", "K0 x E1", "K2 x E3")):
        ex = R.build(v, ctx)
        E = ex.entries
        b = ctx.bars(v.tf)
        dk = SH.clock(b.t, R.TF_MIN[v.tf])["day_key"][E.bar]
        assert len(np.unique(dk)) == len(dk), v.id
        assert np.all((E.exit_bar == -1) | (E.exit_bar > E.bar)), v.id
        r = M.run_exec(mk, ex, "2019-02-04", "2019-03-05")
        assert r.counts["busy"] == 0 and r.counts["dropped_stop"] == 0, v.id
        assert r.counts["taken"] + r.counts["dropped_target"] == r.counts["candidates"], v.id
        tr = r.trades
        n_trades += len(tr)
        by_bar = dict(zip(E.bar.tolist(), E.exit_bar.tolist()))
        for bar, x_ix in zip(tr.bar.to_numpy(), tr.exit_ix.to_numpy()):
            xb = by_bar[int(bar)]
            if xb >= 0:
                assert x_ix <= int(b.ex[xb]), v.id
        if v.params["exit"] == "E1":
            assert "target" not in set(tr.reason), v.id
    assert n_trades > 500


def test_presets_sum_their_lanes_on_the_walk(walk):
    """Each preset is its setups' rows summed, lane by lane (the trades, the P/L), and two lanes do hold positions at
    the same time (one position per setup, PREREG 4): some trade of one lane opens while a trade of the other is
    open."""
    _, mk = walk
    ctx = M.Context(mk)
    overlaps = 0
    for tf in ("M5", "M15"):
        for name in R.PRESETS:
            v = VAR[f"XAUUSDm|{tf}|SH|{R.PRESET_TOKEN[name]}|{R.PRESETS[name][1]}|E1"]
            for cost in (1.0, 1.5):
                r = M.run_exec(mk, R.build(v, ctx), "2019-02-04", "2019-03-05", cost)
                parts = [run(mk, ctx, f"XAUUSDm|{tf}|SH|{s}|{R.PRESETS[name][1]}|E1", cost, "2019-02-04", "2019-03-05")
                         for s in R.PRESETS[name][0]]
                assert len(r.trades) == sum(len(p.trades) for p in parts) and len(r.trades) > 0, v.id
                assert abs(r.net - sum(p.net for p in parts)) < 1e-6, v.id
                for q, p in enumerate(parts):
                    mine = r.trades[r.trades.lane == q]
                    assert list(mine.entry_ix) == list(p.trades.entry_ix), (v.id, q)
                    assert np.allclose(mine.pnl.to_numpy(), p.trades.pnl.to_numpy()), (v.id, q)
                if len(parts) == 1:
                    assert r.max_dd == parts[0].max_dd, v.id
                else:
                    a0, b0 = parts[0].trades, parts[1].trades
                    for e1, x1 in zip(a0.entry_ix, a0.exit_ix):
                        overlaps += int(((b0.entry_ix < x1) & (b0.exit_ix > e1)).sum())
    assert overlaps > 0


def test_the_trend_directions_are_the_filters_sides():
    """The trend rows read ``allow_long - allow_short`` of the study's filters at the chart bar's close; the K2 rows
    the script's 1H EMA200 at the chart bar's open. On 40 days around the clock F2-4H's MA200 exists for the last few
    days only; F3's TSI of the last closed 1H bar from the second day."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
        mk = M.TMarket2("XAUUSDm", random_m1(days=40, seed=5, gaps=0))
    ctx = M.Context(mk)
    for tf in R.TFS:
        for f in R.TREND_FILTERS:
            al, ash = F.allow(ctx, tf, f)
            d = R.trend_dir(ctx, tf, f)
            assert d.dtype == np.int8 and np.array_equal(d, al.astype(np.int8) - ash.astype(np.int8)), (tf, f)
        assert (R.trend_dir(ctx, tf, "F3") != 0).mean() > 0.9 and (R.trend_dir(ctx, tf, "F2-4H") != 0).any(), tf
        b = ctx.bars(tf)
        assert np.array_equal(R.trend_dir(ctx, tf), SH.htf_ema_dir(b.t, b.c, ctx.bars("1H")))
        # each row hands the port its direction: the signals are the port's with that series
        for trend in (None, "F2-4H", "F3"):
            sig = R.signal_table(ctx, tf, "K2", trend)
            hd = R.trend_dir(ctx, tf, trend or R.TREND_EMA)
            ref = SH.session_hunter(b.t, b.o, b.h, b.l, b.c, None, R.TF_MIN[tf], hd, conf=("FVG", "HTF"))
            assert np.array_equal(sig["bar"], ref.bar.to_numpy()) and np.array_equal(sig["stop"], ref.stop.to_numpy())


def _entries_frame(ex: M.Exec):
    lanes = ex.lanes if ex.kind == "lanes" else (ex,)
    out = []
    for q, x in enumerate(lanes):
        E = x.entries
        out.append(pd.DataFrame({"lane": q, "bar": E.bar, "side": E.side, "stop": E.stop_level,
                                 "tlev": E.target_level, "tr": E.target_r, "xb": E.exit_bar, "tag": E.tag}))
    return pd.concat(out, ignore_index=True)


def test_causality_entries_before_t_do_not_change(walk):
    """Cut the M1 bars at T (on a 15-minute boundary): every entry decided at a bar before the truncated chart's last
    bar keeps its bar, side, stop, target and tag; its exit decision is the same when it lies before that last bar,
    and none yet (-1) otherwise. (A signal on the last bar waits for the next bar's open, where the script's cancels
    are decided: that is its fill.)"""
    m1, mk = walk
    ctx_full = M.Context(mk)
    rows = _rows(blocks=("core", "K0 x E1", "K2 x E3", "preset", "trend", "Monday variant"))
    cuts = ["2019-02-05 08:15", "2019-02-12 15:00", "2019-02-20 04:45", "2019-02-27 17:30"]
    checked = 0
    for cut in cuts:
        T = TM.s_of(cut)
        keep = m1["t"] < T
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(M, "STUDY_DIR", M.STUDY_DIR.parent / "__no_such_study__")
            mk_t = M.TMarket2("XAUUSDm", {k: v[keep] for k, v in m1.items()})
        ctx_t = M.Context(mk_t)
        for v in rows:
            n_t = len(ctx_t.bars(v.tf))
            assert np.array_equal(ctx_t.bars(v.tf).t, ctx_full.bars(v.tf).t[:n_t]), v.tf
            full = _entries_frame(R.build(v, ctx_full))
            part = _entries_frame(R.build(v, ctx_t))
            full = full[full.bar < n_t - 1].reset_index(drop=True)
            part = part[part.bar < n_t - 1].reset_index(drop=True)
            assert len(full) == len(part), (cut, v.id)
            cols = ["lane", "bar", "side", "stop", "tlev", "tr", "tag"]
            assert full[cols].equals(part[cols]), (cut, v.id)
            want_xb = np.where(full.xb.to_numpy() < n_t - 1, full.xb.to_numpy(), -1)
            assert np.array_equal(part.xb.to_numpy(), want_xb), (cut, v.id)
            checked += len(full)
        del ctx_t, mk_t
    assert checked > 1000


def test_describe_warm_and_the_event_table(walk):
    _, mk = walk
    ctx = M.Context(mk)
    for v in R.variants("XAUUSDm") + R.variants("USTECm"):
        txt = R.describe(v)
        assert isinstance(txt, str) and len(txt) > 100 and v.tf in txt, v.id
    rows = _rows(blocks=("preset", "Monday variant"))
    R.warm(ctx, rows)
    n_cached = len(ctx.cache)
    for v in rows:
        R.build(v, ctx)
    assert len(ctx.cache) == n_cached                                   # build read only what warm computed
    et = R.event_table(ctx, VAR["XAUUSDm|M5|SH|PRESET-CUSTOM|K2|E1"])
    assert set(et.setup) <= {"AS", "LS"} and set(et.lane) <= {0, 1} and et.taken.any()
    assert (et.stop_atr[et.taken] >= 0.5 - 1e-9).all()                  # the minimum stop: 0.5 ATR from the close


# ───────────────────────────── (d) the smoke test on real data (Development only) ─────────────────────────────

SMOKE = {"XAUUSDm": ("2019-01-01", "2019-07-01"), "BTCUSDm": ("2019-01-01", "2019-07-01"),
         "EURUSDm": ("2019-01-01", "2019-07-01"), "GBPUSDm": ("2019-01-01", "2019-07-01"),
         "USTECm": ("2020-07-01", "2021-01-01")}
# one variant of each rule type (gold and BTC); the claim markets run all their rows
TYPES = ("{s}|M5|SH|AB|K0|E1", "{s}|M15|SH|AS|K1|E2", "{s}|M5|SH|LS|K2|E1", "{s}|M5|SH|OR|K3|E2",
         "{s}|M15|SH|PD|K2|E3", "{s}|M5|SH|PRESET-CUSTOM|K2|E1", "{s}|M15|SH|PRESET-FOREX|K3|E1",
         "{s}|M15|SH|PRESET-NASDAQ|K2|E1", "{s}|M5|SH|AB|K2|E1|F2-4H", "{s}|M15|SH|LS|K2|E1|F2-1D",
         "{s}|M5|SH|AS|K2|E1|F3", "{s}|M5|SH|PD|K2|E1|MON-FRI", "{s}|M5|SH|PD|K2|E1")


def _available(symbol: str, start: str, end: str) -> bool:
    months = set(store.available_months(symbol))
    first = M.data_start(symbol)
    need = pd.period_range(first[:7], pd.Timestamp(end) - pd.Timedelta(days=1), freq="M")
    return all((p.year, p.month) in months for p in need)


@pytest.mark.parametrize("symbol", list(SMOKE))
def test_smoke_on_development_data(symbol):
    """Each rule type runs through the harness on Development data only, at x1.0 and x1.5. Checked: the Exec's kind
    and lanes, the same candidates at both costs, no busy lane, entries inside the window, one trade a day per lane,
    no target exit on an E1 row, the scores computable. No profit or loss is printed, asserted or kept."""
    a, z = SMOKE[symbol]
    if not _available(symbol, a, z):
        pytest.skip(f"the tick store of {symbol} does not cover {M.data_start(symbol)} .. {z}")
    mk = M.load(symbol, end=z)
    assert mk.end_s == TM.s_of(z) and int(mk.t[-1]) < TM.s_of(z) <= M.CUT_S     # nothing after the window is held
    ctx = M.Context(mk)
    vids = ([v.id for v in R.variants(symbol)] if symbol in M.CLAIM_SYMBOLS else [x.format(s=symbol) for x in TYPES])
    cand = {}
    for vid in vids:
        v = VAR[vid]
        ex = R.build(v, ctx)
        n_lanes = int(v.params["lanes"])
        if v.params["preset"]:
            assert ex.kind == "lanes" and len(ex.lanes) == n_lanes, vid
        else:
            assert ex.kind == "events" and ex.label == vid, vid
        got = {}
        for cost in M.COSTS:
            r = M.run_exec(mk, ex, a, z, cost)
            got[cost] = dict(r.counts)
            assert r.counts["busy"] == 0 and r.counts["taken"] <= r.counts["candidates"], vid
            tr = r.trades
            if len(tr):
                assert tr.entry_time.min() >= pd.Timestamp(a, tz="UTC") and \
                    tr.exit_time.max() <= pd.Timestamp(z, tz="UTC"), vid
                b = ctx.bars(v.tf)
                key = pd.DataFrame({"lane": tr.lane.to_numpy(), "dk": M.sh_day_key(b.t[tr.bar.to_numpy()])})
                assert not key.duplicated().any(), vid
                if v.params["exit"] == "E1":
                    assert "target" not in set(tr.reason), vid
            sc = M.scores(r)
            assert set(M.SCORE_KEYS) <= set(sc), vid
        assert got[1.0]["candidates"] == got[1.5]["candidates"], vid
        assert got[1.0]["candidates"] > 0, vid                            # every row has events in six months
        cand[vid] = got[1.0]["candidates"]
    if symbol in M.SYMBOLS:
        # the Monday variant only adds Monday's PD signals to the as-coded row
        assert cand[f"{symbol}|M5|SH|PD|K2|E1|MON-FRI"] >= cand[f"{symbol}|M5|SH|PD|K2|E1"]
    del ctx, mk
    gc.collect()
