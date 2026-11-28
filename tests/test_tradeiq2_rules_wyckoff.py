"""
Study 2's Wyckoff rule rows (``backtesting/research/tradeiq2_rules_wyckoff.py``; PREREG 6.3 with sections 4, 5 and 7).

(a) The grid: the rows per symbol are the PREREG's (the numbers are written here from its text), with their ids,
    families, eligibility and the filters of each timeframe; the driver's grid check accepts them.
(b) Entry and exit semantics on hand-made bars with a hand-made engine output (``use_engine_output``): S-W and its
    skip guard, X-S (the hold, the campaign, the outcome), X-S3, WY-STD-L, WY-AGG, WY-CL (S-CL, 2R, 50 bars), WY-SP
    (confirmed; provisional, deviation D2), the tags, one position at a time.
(c) PREREG 4's absolute-level rules through these rules: a fill beyond the stop is dropped, the 3R target is measured
    from the actual fill, x1.5 recomputes it from its own fill.
(d) The filters: F0 and the F2 slot per timeframe, checked at the decision close only, never closing an open trade;
    the real filters on a synthetic market.
(e) The real engine on a synthetic Wyckoff-like market: causality (truncation), one entry per campaign and setting,
    the engine's inputs (bars, volume source, tick).
(f) The pooled test and its matched placebo on synthetic markets, and the driver's adapters (claims 15 and 16).
(g) An execution smoke test on real Development bars (2019-01-01 to 2019-06-30, the market loaded only to 2019-07-01):
    one row of each rule type through tradeiq2_market's runner. Its profit or loss is neither printed nor asserted.

The hand-made market: M1 bars round the clock from Monday 2019-03-04 (study 2's guard scores no window before 2019 on
gold); every 1H bar opens and closes at 100.00 with a high of 100.50 (minute 10) and a low of 99.50 (minute 20), so its
true range is 1.00 and ATR(14) is exactly 1.00 from bar 13 on; the spread is 0.20 (a buy fills at 100.20).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq_market as TM
from backtesting.research import tradeiq2_filters as F
from backtesting.research import tradeiq2_ind_wyckoff as W
from backtesting.research import tradeiq2_market as M
from backtesting.research import tradeiq2_rules_wyckoff as RW

T0 = TM.s_of("2019-03-04")            # a Monday, 00:00 UTC
HOUR = 3600
GOLD, BTC = M.GOLD, M.BTC
NAN = math.nan

# PREREG 6.3 "Size: 36 + 18 = 54 eligible rows per symbol, plus 3 control rows on BTC": 36 = (WY-STD, WY-STD-L,
# WY-AGG) x (X-S, X-S3) x (F0, F2) x (1H, 4H, 1D); 18 = WY-CL x (2R / 50 bars) x 2 x 3 + WY-SP x (X-S, X-S3) x 2 x 3
# (deviation D1); the control = WY-STD x X-S x F0 x 3 on BTC's Exness tick volume. Section 7: families WY and
# WY-DERIVED; its 738 / 720 eligible variants count these 54.
PREREG_ROWS = {GOLD: {("WY", True): 36, ("WY-DERIVED", True): 18},
               BTC: {("WY", True): 36, ("WY-DERIVED", True): 18, ("WY", False): 3}}
PER_RULE = {"WY-STD": 12, "WY-STD-L": 12, "WY-AGG": 12, "WY-CL": 6, "WY-SP": 12}
F2_OF = {"1H": "F2-4H", "4H": "F2-1D", "1D": "F1"}


# ───────────────────────────── fixtures and helpers ─────────────────────────────

@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """Both studies' folders as the guards see them: empty tmp folders (no FINALISTS.md: the hold-outs are closed)."""
    d2, d1 = tmp_path / "study2", tmp_path / "study1"
    d2.mkdir()
    d1.mkdir()
    monkeypatch.setattr(M, "STUDY_DIR", d2)
    monkeypatch.setattr(TM, "STUDY_DIR", d1)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)


def hourly_m1(hours, base=100.0, sp=0.2):
    """The hand-made M1 bars (see the module docstring)."""
    k = hours * 60
    t = T0 + 60 * np.arange(k, dtype=np.int64)
    o = np.full(k, float(base))
    m = np.arange(k) % 60
    h, lo = o + 0.02, o - 0.02
    h[m == 10] = base + 0.5
    lo[m == 20] = base - 0.5
    return {"t": t, "o": o, "h": h, "l": lo, "c": o.copy(), "spread_mean": np.full(k, float(sp)), "n": np.ones(k)}


def ix(hour, minute=0):
    """The M1 index of minute ``minute`` of hour ``hour`` in the hand-made market."""
    return hour * 60 + minute


def ctx_of(m1, symbol=GOLD):
    return M.Context(M.TMarket2(symbol, m1))


def fake_out(n):
    """A neutral engine output: no campaign, no event (one value per bar of W.CONTRACT_KEYS)."""
    out = {"phase": np.zeros(n, np.int8), "outcome": np.zeros(n, np.int8), "campaign": np.full(n, -1, np.int32),
           "climax": np.zeros(n, np.int8), "exc": np.zeros(n, np.int8), "entry_std": np.zeros(n, np.int8),
           "entry_agg": np.zeros(n, np.int8), "entry_con": np.zeros(n, np.int8), "in_cde": np.zeros(n, bool)}
    for k in ("range_lo", "range_hi", "hard_lo", "hard_hi", "climax_px", "exc_px"):
        out[k] = np.full(n, NAN)
    for k in W.EVENT_BITS:
        out[k] = np.zeros(n, bool)
    return {k: out[k] for k in W.CONTRACT_KEYS}


def hold(out, a, z, cid, outcome, phase=3):
    """Bars a .. z-1 in campaign ``cid`` with ``outcome`` in Phase ``phase`` (the hold of X-S from Phase C on)."""
    out["campaign"][a:z] = cid
    out["outcome"][a:z] = outcome
    out["phase"][a:z] = phase
    out["in_cde"][a:z] = phase >= 3 and outcome != 0


def market_with(out_1h, hours=120, m1=None, symbol=GOLD):
    """A hand-made market (or ``m1``) whose 1H engine output is ``out_1h`` (the 4H and 1D engines run for real)."""
    ctx = ctx_of(hourly_m1(hours) if m1 is None else m1, symbol)
    if out_1h is not None:
        RW.use_engine_output(ctx, "1H", out_1h)
    return ctx


def variant(symbol, tf, rule, exit_, filt="F0", control=False):
    got = [v for v in RW.variants(symbol) if v.tf == tf and v.params["rule"] == rule and v.params["exit"] == exit_
           and v.params["filter"] == filt and v.eligible != control]
    assert len(got) == 1, (symbol, tf, rule, exit_, filt, control)
    return got[0]


def run(ctx, ex, cost=1.0):
    return M.run_exec(ctx.mk, ex, T0, int(ctx.mk.t[-1]) + 60, cost)


def rows(r):
    tr = r.trades
    return list(zip(tr.side, tr.entry_ix, tr.exit_ix, np.round(tr.entry, 9), np.round(tr.exit, 9), tr.reason))


def entries_of(ctx, symbol, tf, rule, exit_, filt="F0", control=False):
    return RW.build(variant(symbol, tf, rule, exit_, filt, control), ctx).entries


# ───────────────────────────── (a) the grid ─────────────────────────────

def test_a_row_counts_per_symbol_are_the_preregs():
    for s, want in PREREG_ROWS.items():
        vs = RW.variants(s)
        assert dict(Counter((v.family, v.eligible) for v in vs)) == want, s
        el = [v for v in vs if v.eligible]
        assert len(el) == 54
        assert dict(Counter(v.params["rule"] for v in el)) == PER_RULE
        assert dict(Counter(v.tf for v in el)) == {"1H": 18, "4H": 18, "1D": 18}
        assert dict(Counter((v.params["rule"], v.params["exit"]) for v in el)) == {
            ("WY-STD", "X-S"): 6, ("WY-STD", "X-S3"): 6, ("WY-STD-L", "X-S"): 6, ("WY-STD-L", "X-S3"): 6,
            ("WY-AGG", "X-S"): 6, ("WY-AGG", "X-S3"): 6, ("WY-CL", "X-2R50"): 6, ("WY-SP", "X-S"): 6,
            ("WY-SP", "X-S3"): 6}
    ctl = [v for v in RW.variants(BTC) if not v.eligible]
    assert sorted(v.tf for v in ctl) == ["1D", "1H", "4H"]
    assert all(v.params["rule"] == "WY-STD" and v.params["exit"] == "X-S" and v.params["filter"] == "F0"
               and v.params["volume"] == "tick" and "not eligible" in v.info for v in ctl)
    for s in M.CLAIM_SYMBOLS:
        assert RW.variants(s) == []
    assert RW.EXPECTED == PREREG_ROWS


def test_a_ids_fields_and_filters_per_timeframe():
    for s in M.SYMBOLS:
        vs = RW.variants(s)
        ids = [v.id for v in vs]
        assert len(set(ids)) == len(ids)
        for v in vs:
            t = v.id.split("|")
            assert t[:3] == [s, v.tf, v.family] and v.script == "WY" and v.family in ("WY", "WY-DERIVED")
            assert not any(ch.isspace() for ch in v.id) and isinstance(v.eligible, bool)
            assert t[3] == v.params["rule"] and t[4] == v.params["stop"] and t[5] == v.params["exit"]
            assert t[6] == v.params["filter"] in ("F0", F2_OF[v.tf])
            assert v.params["filter_slot"] == ("F0" if t[6] == "F0" else "F2")
            json.dumps(dict(v.params))
            sp = RW.spec_of(v)
            assert sp.rule.name == t[3] and sp.exit == t[5] and sp.filter == t[6] and sp.control == (not v.eligible)
            assert v.params["volume"] == ("tick" if (s == GOLD or not v.eligible) else "binance")
            assert v.family == ("WY-DERIVED" if t[3] in ("WY-CL", "WY-SP") else "WY")
            assert RW.describe(v).startswith("Wyckoff [theUltimator5] on ")
        for tf in RW.TFS:
            assert {v.params["filter"] for v in vs if v.tf == tf} == {"F0", F2_OF[tf]}
    assert [v.id for v in RW.pooled_variants(GOLD)] == [f"XAUUSDm|{tf}|WY|WY-STD|S-W|X-S|F0" for tf in RW.TFS]
    assert [v.id for v in RW.pooled_variants(BTC)] == [f"BTCUSDm|{tf}|WY|WY-STD|S-W|X-S|F0" for tf in RW.TFS]
    with pytest.raises(ValueError):
        RW.spec_of(M.Variant("XAUUSDm|1H|WY|WY-STD|S-W|X-S|F2-1D", GOLD, "1H", "WY", "WY"))   # not 1H's F2


def test_a_the_drivers_grid_check_accepts_the_rows():
    D = pytest.importorskip("backtesting.research.tradeiq2")
    g, _ = D.checked_grid({"wyckoff": RW})
    assert len(g) == 54 + 57 and set(g.family) == {"WY", "WY-DERIVED"}


# ───────────────────────────── (b) entries and exits on hand-made bars ─────────────────────────────

def test_b_the_hand_made_market():
    ctx = ctx_of(hourly_m1(120))
    b, a = ctx.bars("1H"), ctx.atr("1H")
    assert len(b) == 120 and np.all(b.h == 100.5) and np.all(b.l == 99.5) and np.all(b.c == 100.0)
    assert np.isnan(a[12]) and np.all(a[13:] == 1.0)
    assert list(b.ex[:3]) == [ix(1), ix(2), ix(3)]


def test_b_wy_std_long_sw_stop_and_the_xs_exit():
    out = fake_out(120)
    hold(out, 18, 26, cid=7, outcome=1)                     # campaign 7 holds accumulation in Phase C on 18 .. 25
    out["hard_lo"][18:26] = 99.0
    out["entry_std"][20], out["ev_test"][20] = 1, True
    ctx = market_with(out)
    E = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")
    assert list(E.bar) == [20] and list(E.side) == [1]
    assert E.stop_level[0] == 99.0 - 0.15 * 1.0               # S-W: the hard level - 0.15 ATR, an absolute level
    assert np.isnan(E.target_r[0]) and E.exit_bar[0] == 26    # X-S: the first bar that no longer holds
    assert RW.campaign_of_tag(E.tag)[0] == 7 and RW.kind_of_tag(E.tag)[0] == RW.K_TEST
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))
    # filled at the open after bar 20's close at the ask, out at the open after bar 26's close at the bid
    assert rows(r) == [(1, ix(21), ix(27), 100.2, 100.0, "signal")]
    assert r.trades.risk[0] == pytest.approx(100.2 - 98.85)   # the distance |fill - level| from the actual fill
    assert r.trades.bar[0] == 20 and r.counts["taken"] == 1


def test_b_wy_std_short_mirrors_it():
    out = fake_out(120)
    hold(out, 18, 26, cid=7, outcome=-1)
    out["hard_hi"][18:26] = 101.0
    out["entry_std"][20], out["ev_ctest"][20] = -1, True
    ctx = market_with(out)
    E = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")
    assert list(E.side) == [-1] and E.stop_level[0] == 101.0 + 0.15 and E.exit_bar[0] == 26
    assert RW.kind_of_tag(E.tag)[0] == RW.K_CTEST
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))
    assert rows(r) == [(-1, ix(21), ix(27), 100.0, 100.2, "signal")]
    assert r.trades.risk[0] == pytest.approx(1.15)


@pytest.mark.parametrize("hard, kept", [(99.95, False), (99.85, True), (NAN, False)])
def test_b_the_skip_guard_is_measured_from_the_decision_close(hard, kept):
    """S-W at 99.95 - 0.15 = 99.80 is 0.20 ATR below the close (skipped); at 99.70, 0.30 ATR (kept); no hard level,
    no stop (dropped)."""
    out = fake_out(120)
    hold(out, 18, 26, cid=7, outcome=1)
    out["hard_lo"][18:26] = hard
    out["entry_std"][20], out["ev_test"][20] = 1, True
    ctx = market_with(out)
    assert len(entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")) == int(kept)
    ev = RW.candidate_events(out, ctx.bars("1H").c, ctx.atr("1H"), "WY-STD")
    assert list(ev["bar"]) == [20] and bool(ev["guard"][0]) == kept
    if kept:
        assert ev["dist_atr"][0] == pytest.approx(0.30)


def test_b_the_skip_guard_uses_the_close_not_the_fill():
    """Bar 20 closes at 99.90: a stop at 99.70 is 0.20 ATR below that close, so the entry is skipped although the next
    open (100.00) is 0.30 above the stop. The derived rows have no guard (deviation D4)."""
    m1 = hourly_m1(120)
    m1["c"][ix(20, 59)] = m1["l"][ix(20, 59)] = 99.9
    out = fake_out(120)
    hold(out, 18, 26, cid=7, outcome=1)
    out["hard_lo"][18:26] = 99.85
    out["entry_std"][20], out["ev_test"][20] = 1, True
    out["climax"][20], out["climax_px"][20] = 1, 99.85
    ctx = market_with(out, m1=m1)
    assert ctx.bars("1H").c[20] == 99.9 and ctx.atr("1H")[20] == 1.0
    assert len(entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")) == 0
    E = entries_of(ctx, GOLD, "1H", "WY-CL", "X-2R50")
    assert list(E.bar) == [20] and E.stop_level[0] == pytest.approx(99.7)


def _exit_case(change):
    out = fake_out(120)
    hold(out, 18, 40, cid=7, outcome=1)
    out["hard_lo"][18:40] = 99.0
    out["entry_std"][20], out["ev_test"][20] = 1, True
    change(out)
    return out


@pytest.mark.parametrize("name, change, want", [
    ("a demotion (Phase D back to B)", lambda o: hold(o, 30, 40, 7, 0, phase=2), 30),
    ("a reset", lambda o: hold(o, 30, 40, -1, 0, phase=0), 30),
    ("a re-seed holding the same side", lambda o: hold(o, 30, 40, 29, 1), 30),
    ("an outcome change", lambda o: hold(o, 30, 40, 7, -1), 30),
    ("the end of the hold", lambda o: None, 40),
    ("a hold to the last bar", lambda o: hold(o, 40, 120, 7, 1), -1),
])
def test_b_xs_ends_on_any_break_of_the_hold(name, change, want):
    out = _exit_case(change)
    ctx = market_with(out)
    E = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")
    assert list(E.exit_bar) == [want], name
    assert RW.xs_exit(out, 20, 1) == want
    if want == -1:
        r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))
        assert rows(r) == [(1, ix(21), ix(120) - 1, 100.2, 100.0, "end")]       # the window's last M1 close


def test_b_the_stop_and_the_3r_target_of_x_s3():
    out = _exit_case(lambda o: None)                            # X-S at bar 40; risk 100.20 - 98.85 = 1.35
    m1 = hourly_m1(120)
    m1["l"][ix(23, 30)] = 98.0                                  # through the stop at 98.85
    ctx = market_with(out, m1=m1)
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))
    assert rows(r) == [(1, ix(21), ix(23, 30), 100.2, 98.65, "stop")]       # one spread worse than the level
    assert r.trades.r[0] == pytest.approx(-1.55 / 1.35)
    m1 = hourly_m1(120)
    m1["h"][ix(23, 40)] = 104.3                                 # the target 100.20 + 3 x 1.35 = 104.25 is reached
    ctx = market_with(_exit_case(lambda o: None), m1=m1)
    E = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S3")
    assert list(E.target_r) == [3.0] and list(E.exit_bar) == [40]
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S3"), ctx))
    assert rows(r) == [(1, ix(21), ix(23, 40), 100.2, 104.25, "target")] and r.trades.r[0] == pytest.approx(3.0)
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))          # X-S alone ignores it
    assert rows(r) == [(1, ix(21), ix(41), 100.2, 100.0, "signal")]


def test_b_long_only_and_the_aggressive_setting():
    out = fake_out(120)
    hold(out, 18, 26, cid=7, outcome=-1)
    out["hard_hi"][18:26] = 101.0
    out["entry_std"][20], out["entry_agg"][20], out["ev_test"][20] = -1, -1, True
    hold(out, 38, 60, cid=33, outcome=1)
    out["hard_lo"][38:60] = 99.0
    out["entry_agg"][40], out["ev_sos"][40] = 1, True           # Aggressive's SOS fallback (no test)
    out["entry_std"][50], out["ev_lps"][50] = 1, True           # Standard's LPS fallback
    ctx = market_with(out)
    std = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")
    assert list(std.bar) == [20, 50] and list(std.side) == [-1, 1]
    assert list(RW.kind_of_tag(std.tag)) == [RW.K_TEST, RW.K_LPS]
    lo = entries_of(ctx, GOLD, "1H", "WY-STD-L", "X-S")
    assert list(lo.bar) == [50] and list(lo.side) == [1] and list(lo.exit_bar) == [60]
    agg = entries_of(ctx, GOLD, "1H", "WY-AGG", "X-S")
    assert list(agg.bar) == [20, 40] and list(RW.kind_of_tag(agg.tag)) == [RW.K_TEST, RW.K_SOS]
    assert list(RW.campaign_of_tag(agg.tag)) == [7, 33] and list(agg.exit_bar) == [26, 60]


def test_b_the_entry_type_follows_the_scripts_entry_kind():
    """L1747: Standard's LPS fallback comes first (an entry bar with an SOS and an LPS bit, as gold 1H on 2023-01-13
    08:00, is an LPS entry); Aggressive has no LPS trigger, so without a test bit it is the SOS fallback."""
    out = fake_out(120)
    hold(out, 18, 60, cid=7, outcome=1)
    out["hard_lo"][:] = 99.0
    out["entry_std"][20], out["ev_sos"][20], out["ev_lps"][20] = 1, True, True
    out["entry_agg"][30], out["ev_sos"][30], out["ev_lpsy"][30] = 1, True, True
    out["entry_agg"][40], out["ev_ctest"][40], out["ev_sow"][40] = 1, True, True
    std = RW.candidate_events(out, np.full(120, 100.0), np.ones(120), "WY-STD")
    agg = RW.candidate_events(out, np.full(120, 100.0), np.ones(120), "WY-AGG")
    assert list(std["kind"]) == [RW.K_LPS] and list(agg["kind"]) == [RW.K_SOS, RW.K_CTEST]


def test_b_one_position_at_a_time():
    out = fake_out(120)
    hold(out, 18, 31, cid=7, outcome=1)
    hold(out, 31, 40, cid=31, outcome=-1)
    hold(out, 50, 60, cid=50, outcome=1)
    out["hard_lo"][:], out["hard_hi"][:] = 99.0, 101.0
    out["entry_std"][20] = 1                                    # open until bar 31's close
    out["entry_std"][25] = 1                                    # decided while it is open: busy (skipped)
    out["entry_std"][33] = -1                                   # decided after it closed: taken
    out["entry_std"][52] = 1
    for i in (20, 25, 33, 52):
        out["ev_test"][i] = True
    out["campaign"][25] = 7
    ctx = market_with(out)
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))
    assert list(r.trades.bar) == [20, 33, 52] and r.counts["busy"] == 1 and r.counts["candidates"] == 4
    assert list(r.trades.exit_ix) == [ix(32), ix(41), ix(61)]


def test_b_wy_cl_climax_stop_2r_target_and_50_bar_time_stop():
    out = fake_out(200)
    out["climax"][20], out["climax_px"][20], out["ev_sc"][20], out["campaign"][15:30] = 1, 99.0, True, 15
    out["climax"][60], out["climax_px"][60] = -1, 101.0          # decided while the first is open: busy
    out["climax"][80], out["climax_px"][80], out["ev_bc"][80] = -1, 101.0, True
    out["climax"][170], out["climax_px"][170] = 1, 99.0          # bar 220 is not served: no time stop
    ctx = market_with(out, hours=200)
    E = entries_of(ctx, GOLD, "1H", "WY-CL", "X-2R50")
    assert list(E.bar) == [20, 60, 80, 170] and list(E.side) == [1, -1, -1, 1]
    assert list(E.stop_level) == [99.0 - 0.15, 101.0 + 0.15, 101.0 + 0.15, 99.0 - 0.15]
    assert list(E.target_r) == [2.0] * 4 and list(E.exit_bar) == [70, 110, 130, -1]
    assert list(RW.kind_of_tag(E.tag)) == [RW.K_CLIMAX] * 4 and RW.campaign_of_tag(E.tag)[0] == 15
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-CL", "X-2R50"), ctx))
    # held 50 bars: in at the open after bar 20's close, out at the open after bar 70's close
    assert rows(r) == [(1, ix(21), ix(71), 100.2, 100.0, "signal"), (-1, ix(81), ix(131), 100.0, 100.2, "signal"),
                       (1, ix(171), ix(200) - 1, 100.2, 100.0, "end")]
    assert r.counts["busy"] == 1
    m1 = hourly_m1(200)
    m1["h"][ix(40, 40)] = 103.0                                  # the 2R target 100.20 + 2 x 1.35 = 102.90
    ctx = market_with(out, hours=200, m1=m1)
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-CL", "X-2R50"), ctx))
    assert rows(r)[0] == (1, ix(21), ix(40, 40), 100.2, 102.9, "target") and r.trades.r[0] == pytest.approx(2.0)
    assert list(r.trades.bar) == [20, 60, 170]                   # after the target the short of bar 60 is free


def test_b_wy_sp_confirmed_spring_has_the_plain_xs():
    out = fake_out(120)
    hold(out, 10, 20, cid=5, outcome=0, phase=2)                 # Phase B
    hold(out, 20, 30, cid=5, outcome=1)                          # the spring puts it in Phase C at its recovery bar
    out["exc"][20], out["exc_px"][20], out["ev_spring"][20] = 1, 99.2, True
    ctx = market_with(out)
    for x in ("X-S", "X-S3"):
        E = entries_of(ctx, GOLD, "1H", "WY-SP", x)
        assert list(E.bar) == [20] and list(E.exit_bar) == [30] and E.stop_level[0] == pytest.approx(99.05)
        assert RW.kind_of_tag(E.tag)[0] == RW.K_SPRING
        assert (np.isnan(E.target_r[0]) if x == "X-S" else E.target_r[0] == 3.0)
    assert RW.sp_exit(out, 20, 1) == RW.xs_exit(out, 20, 1) == 30


@pytest.mark.parametrize("name, after, want", [
    ("a reset, never armed", lambda o: hold(o, 40, 120, -1, 0, phase=0), 40),
    ("a re-seed, never armed", lambda o: hold(o, 41, 120, 41, 0, phase=1), 41),
    ("the opposite outcome first", lambda o: hold(o, 28, 120, 5, -1), 28),
    ("armed later, then a demotion", lambda o: (hold(o, 25, 34, 5, 1, phase=4), hold(o, 34, 120, 5, 0, phase=2)), 34),
    ("armed later, then the opposite outcome", lambda o: (hold(o, 25, 34, 5, 1), hold(o, 34, 120, 5, -1)), 34),
    ("never armed, never gone", lambda o: None, -1),
])
def test_b_wy_sp_after_a_provisional_spring_reading_d2(name, after, want):
    """A provisional recovery leaves the campaign in Phase B without an outcome: a literal X-S would exit at bar 21.
    D2: X-S is armed once the campaign holds the trade's side in Phases C-E; until then a reset, a re-seed or the
    opposite outcome ends the trade."""
    out = fake_out(120)
    hold(out, 10, 120, cid=5, outcome=0, phase=2)
    out["exc"][20], out["exc_px"][20] = 1, 99.2                  # no spring bit: provisional
    after(out)
    ctx = market_with(out)
    E = entries_of(ctx, GOLD, "1H", "WY-SP", "X-S")
    assert list(E.bar) == [20] and list(E.exit_bar) == [want], name
    assert RW.kind_of_tag(E.tag)[0] == RW.K_PROV and RW.campaign_of_tag(E.tag)[0] == 5
    assert RW.xs_exit(out, 20, 1) == 21                          # the literal reading D2 replaces


def test_b_wy_sp_short_side_mirrors_d2():
    out = fake_out(120)
    hold(out, 10, 120, cid=5, outcome=0, phase=2)
    out["exc"][20], out["exc_px"][20] = -1, 100.9                # a provisional UTAD
    hold(out, 24, 31, 5, -1, phase=4)                            # adopted on a breakdown: Phase D distribution
    ctx = market_with(out)
    E = entries_of(ctx, GOLD, "1H", "WY-SP", "X-S3")
    assert list(E.side) == [-1] and list(E.exit_bar) == [31] and E.stop_level[0] == pytest.approx(101.05)
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-SP", "X-S3"), ctx))
    assert rows(r) == [(-1, ix(21), ix(32), 100.0, 100.2, "signal")]


def test_b_use_engine_output_refuses_a_second_output():
    ctx = market_with(fake_out(120))
    with pytest.raises(ValueError):
        RW.use_engine_output(ctx, "1H", fake_out(120))
    with pytest.raises(ValueError):
        RW.use_engine_output(ctx, "4H", fake_out(3))


# ───────────────────────────── (c) the absolute-level rules (PREREG 4) ─────────────────────────────

def _gap_from(m1, hour, level):
    """Every M1 bar from ``hour`` on shifted to ``level`` (the hourly pattern kept)."""
    a = ix(hour)
    d = level - 100.0
    for k in ("o", "h", "l", "c"):
        m1[k][a:] += d


def test_c_a_fill_beyond_the_stop_is_dropped():
    out = _exit_case(lambda o: None)                             # S-W at 98.85, the close 100.00 (the guard passes)
    m1 = hourly_m1(120)
    _gap_from(m1, 21, 98.0)                                      # the next open gaps to 98.00: the ask 98.20 < 98.85
    ctx = market_with(out, m1=m1)
    assert len(entries_of(ctx, GOLD, "1H", "WY-STD", "X-S")) == 1
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S"), ctx))
    assert len(r.trades) == 0 and r.counts["dropped_stop"] == 1 and r.counts["candidates"] == 1


def test_c_the_3r_target_is_measured_from_the_actual_fill_and_x15_recomputes_it():
    out = _exit_case(lambda o: None)
    m1 = hourly_m1(120)
    _gap_from(m1, 21, 100.5)                                      # fill 100.70: risk 1.85, target 106.25
    m1["h"][ix(30, 40)] = 106.3
    ctx = market_with(out, m1=m1)
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S3"), ctx))
    assert rows(r) == [(1, ix(21), ix(30, 40), 100.7, 106.25, "target")]
    assert r.trades.risk[0] == pytest.approx(1.85)
    # x1.5: the fill 100.80 gives a risk of 1.95 and a target of 106.65, which the high of 106.30 does not reach
    r15 = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S3"), ctx), cost=1.5)
    assert rows(r15) == [(1, ix(21), ix(41), 100.8, 100.5, "signal")]
    assert r15.trades.risk[0] == pytest.approx(1.95)


# ───────────────────────────── (d) the filters ─────────────────────────────

def test_d_the_f2_slot_of_each_timeframe_is_asked_for_at_build():
    seen = []
    n = {"1H": 120, "4H": 30, "1D": 5}
    ctx = ctx_of(hourly_m1(120))
    for tf in RW.TFS:
        RW.use_engine_output(ctx, tf, fake_out(n[tf]))
    ctx.allow = lambda tf, name: (seen.append((tf, name)), (np.ones(n[tf], bool), np.ones(n[tf], bool)))[1]
    for v in RW.variants(GOLD):
        RW.build(v, ctx)
    assert Counter(seen) == {("1H", "F0"): 9, ("1H", "F2-4H"): 9, ("4H", "F0"): 9, ("4H", "F2-1D"): 9,
                             ("1D", "F0"): 9, ("1D", "F1"): 9}


def test_d_a_filter_gates_the_decision_close_and_never_closes_an_open_trade():
    out = fake_out(120)
    hold(out, 18, 31, cid=7, outcome=1)
    hold(out, 38, 51, cid=33, outcome=1)
    hold(out, 58, 70, cid=55, outcome=-1)
    out["hard_lo"][:], out["hard_hi"][:] = 99.0, 101.0
    for i, d in ((20, 1), (40, 1), (60, -1)):
        out["entry_std"][i], out["ev_test"][i] = d, True
    ctx = market_with(out)
    al, ash = np.ones(120, bool), np.ones(120, bool)
    al[20] = False                                               # the long of bar 20 is not allowed at its close
    al[41:] = False                                              # turns against the long of bar 40 after it opened
    ash[60] = True
    asked = []
    ones = np.ones(120, bool)
    ctx.allow = lambda tf, name: (asked.append(name), (ones, ones) if name == "F0" else (al, ash))[1]
    E0 = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S", "F0")
    E2 = entries_of(ctx, GOLD, "1H", "WY-STD", "X-S", "F2-4H")
    assert list(E0.bar) == [20, 40, 60] and list(E2.bar) == [40, 60] and asked == ["F0", "F2-4H"]
    r = run(ctx, RW.build(variant(GOLD, "1H", "WY-STD", "X-S", "F2-4H"), ctx))
    assert list(r.trades.bar) == [40, 60] and list(r.trades.exit_ix) == [ix(52), ix(71)]   # X-S, not the filter


# ───────────────────────────── (e) the real engine on a synthetic Wyckoff-like market ─────────────────────────────

def wyckoff_like(n, seed, start=2000.0):
    """1H bars with Wyckoff-like structure (the generator of port A's tests): trends, each ending in a wide heavy
    climax bar, then ranges with occasional probes."""
    rng = np.random.default_rng(seed)
    c, o, h, lo, v = (np.empty(n) for _ in range(5))
    px, i, mode, left, drift, level, width, climax = start, 0, "trend", 0, 0.0, start, 10.0, False
    while i < n:
        if left <= 0:
            if mode == "trend":
                mode, left, level, width = "range", int(rng.integers(60, 260)), px, rng.uniform(4, 12)
            else:
                mode, left, drift = "trend", int(rng.integers(40, 160)), rng.choice([-1, 1]) * rng.uniform(0.15, 0.5)
            climax = mode == "range"
        op = px
        if mode == "trend":
            step = drift + rng.standard_normal()
            vb = 100.0 * rng.uniform(0.7, 1.3)
        else:
            step = 0.08 * (level - px) + rng.standard_normal() * 1.2
            if rng.random() < 0.03:
                step += rng.choice([-1, 1]) * width * rng.uniform(0.4, 0.9)
            vb = 100.0 * rng.uniform(0.5, 1.1)
        cl = op + step
        wick = abs(rng.standard_normal()) * 0.6 + 0.2
        hi, low = max(op, cl) + wick * rng.random(), min(op, cl) - wick * rng.random()
        if climax:
            w = rng.uniform(4, 8)
            if drift < 0:
                low = min(op, cl) - w
                cl = low + w * rng.uniform(0.4, 0.8)
                hi = max(op, cl) + 0.3
            else:
                hi = max(op, cl) + w
                cl = hi - w * rng.uniform(0.4, 0.8)
                low = min(op, cl) - 0.3
            vb = 100.0 * rng.uniform(2.5, 4.0)
            climax = False
        o[i], h[i], lo[i], c[i], v[i] = op, hi, low, cl, round(vb)
        px, left, i = cl, left - 1, i + 1
    return o, h, lo, c, v


def m1_of_hours(o, h, lo, c, v, sp=0.3):
    """60 M1 bars per 1H bar, round the clock from T0: the path open -> low -> high -> close (an up bar) or open ->
    high -> low -> close, so the 1H bar built from them is (o, h, l, c) exactly; the tick volume v on its first M1."""
    n = len(o)
    up = c >= o
    p1, p2 = np.where(up, lo, h), np.where(up, h, lo)
    seg = np.linspace(0.0, 1.0, 21)[1:]
    path = np.concatenate([o[:, None] + (p1 - o)[:, None] * seg, p1[:, None] + (p2 - p1)[:, None] * seg,
                           p2[:, None] + (c - p2)[:, None] * seg], axis=1)
    path = np.minimum(np.maximum(path, lo[:, None]), h[:, None])          # no rounding past the bar's range
    path[:, 19], path[:, 39], path[:, 59] = p1, p2, c
    opens = np.concatenate([o[:, None], path[:, :-1]], axis=1)
    k = n * 60
    tick = np.zeros((n, 60))
    tick[:, 0] = v
    return {"t": T0 + 60 * np.arange(k, dtype=np.int64), "o": opens.ravel(), "h": np.maximum(opens, path).ravel(),
            "l": np.minimum(opens, path).ravel(), "c": path.ravel(), "spread_mean": np.full(k, float(sp)),
            "n": tick.ravel()}


_SYN = {}


def synthetic_m1(seed=2, hours=6000):
    if (seed, hours) not in _SYN:
        _SYN[(seed, hours)] = (m1_of_hours(*wyckoff_like(hours, seed)), wyckoff_like(hours, seed))
    return _SYN[(seed, hours)]


@pytest.fixture(scope="module")
def syn():
    m1, bars = synthetic_m1()
    return {"m1": m1, "bars": bars, "ctx": M.Context(M.TMarket2(GOLD, m1))}


def test_e_the_engine_is_the_port_on_the_bars_with_gold_tick_volume(syn):
    ctx, (o, h, lo, c, v) = syn["ctx"], syn["bars"]
    b = ctx.bars("1H")
    assert np.array_equal(b.o, o) and np.array_equal(b.h, h) and np.array_equal(b.l, lo) and np.array_equal(b.c, c)
    assert np.array_equal(b.vol, v)
    out = RW.engine(ctx, "1H")
    ref = W.wyckoff(o, h, lo, c, v, b.t, mintick=0.001)
    for k in W.CONTRACT_KEYS:
        a, r = out[k], ref[k]
        assert a.dtype == r.dtype and not a.flags.writeable, k
        assert np.array_equal(a, r, equal_nan=a.dtype.kind == "f"), k
    assert RW.engine(ctx, "1H") is out                            # cached
    n_ev = {k: int((out[k] != 0).sum()) for k in ("entry_std", "entry_agg", "climax", "exc")}
    assert n_ev["entry_std"] >= 1 and n_ev["entry_agg"] >= 1 and n_ev["climax"] >= 5 and n_ev["exc"] >= 3, n_ev


def test_e_the_volume_source_of_each_row(monkeypatch):
    for symbol in M.SYMBOLS:
        ctx = ctx_of(hourly_m1(120), symbol)
        asked = []

        def vol(tf, source="auto", _n=None, _ctx=ctx, _asked=asked):
            _asked.append((tf, source))
            return np.zeros(len(_ctx.bars(tf)))
        ctx.volume = vol
        for v in RW.variants(symbol):
            RW.build(v, ctx)
        want = {(tf, "tick" if symbol == GOLD else "binance") for tf in RW.TFS}
        if symbol == BTC:
            want |= {(tf, "tick") for tf in RW.TFS}                # the control rows
        assert set(asked) == want and len(asked) == len(want)      # each engine once (cached)


def test_e_the_btc_control_reads_the_tick_volume_engine_and_the_main_rows_binances():
    """The control (PREREG 6.3) is WY-STD x S-W x X-S x F0 on the engine run with Exness tick volume; the main BTC rows
    read the engine run with Binance volume. Two different hand-made outputs tell them apart."""
    ctx = ctx_of(hourly_m1(120), BTC)
    main, tick = fake_out(120), fake_out(120)
    for out, i in ((main, 20), (tick, 50)):
        hold(out, i - 2, i + 8, cid=i - 2, outcome=1)
        out["hard_lo"][:] = 99.0
        out["entry_std"][i], out["ev_test"][i] = 1, True
    RW.use_engine_output(ctx, "1H", main, volume="binance")
    RW.use_engine_output(ctx, "1H", tick, volume="tick")
    E = entries_of(ctx, BTC, "1H", "WY-STD", "X-S")
    C = entries_of(ctx, BTC, "1H", "WY-STD", "X-S", control=True)
    assert list(E.bar) == [20] and list(E.exit_bar) == [28] and list(C.bar) == [50] and list(C.exit_bar) == [58]
    assert C.stop_level[0] == E.stop_level[0] == 99.0 - 0.15


def test_e_causality_decisions_up_to_t_do_not_change_when_the_bars_after_t_are_removed(syn):
    """Cuts at UTC day boundaries around the synthetic campaigns (the first 1H climax is bar 1201, the Standard entries
    bars 2423 and 2923): every entry decided up to the cut, and every exit decided up to it, is the same; an exit that
    comes later is no decision yet (-1) in the cut market."""
    full = syn["ctx"]
    m1 = syn["m1"]
    total = pending = 0
    for cut_day in (52, 101, 122, 165, 230):
        end = T0 + cut_day * 86400                                 # every bar before it is complete
        keep = m1["t"] < end
        part = M.Context(M.TMarket2(GOLD, {k: a[keep] for k, a in m1.items()}))
        n_cmp = 0
        for v in RW.variants(GOLD):
            Ef, Ep = RW.build(v, full).entries, RW.build(v, part).entries
            n2 = len(part.bars(v.tf))
            assert np.array_equal(full.bars(v.tf).c[:n2], part.bars(v.tf).c)
            k = Ef.bar < n2
            assert np.array_equal(Ep.bar, Ef.bar[k]) and np.array_equal(Ep.side, Ef.side[k]), (cut_day, v.id)
            assert np.array_equal(Ep.stop_level, Ef.stop_level[k]), (cut_day, v.id)
            assert np.array_equal(Ep.target_r, Ef.target_r[k], equal_nan=True) and np.array_equal(Ep.tag, Ef.tag[k])
            xf = Ef.exit_bar[k]
            known = (xf >= 0) & (xf < n2)
            assert np.array_equal(Ep.exit_bar[known], xf[known]), (cut_day, v.id)   # decided by the cut: the same
            assert np.all(Ep.exit_bar[~known] == -1), (cut_day, v.id)               # later: not decided yet
            n_cmp += int(k.sum())
            pending += int((xf >= n2).sum())
        assert n_cmp >= 3, cut_day
        total += n_cmp
    assert total >= 100 and pending >= 3, (total, pending)


def test_e_one_entry_per_campaign_and_setting(syn):
    ctx = syn["ctx"]
    for tf in RW.TFS:
        for rule in ("WY-STD", "WY-STD-L", "WY-AGG"):
            E = entries_of(ctx, GOLD, tf, rule, "X-S")
            camp = RW.campaign_of_tag(E.tag)
            assert len(np.unique(camp)) == len(camp) and np.all(camp >= 0), (tf, rule)
    out = RW.engine(ctx, "1H")
    E = entries_of(ctx, GOLD, "1H", "WY-SP", "X-S")
    assert np.array_equal(E.bar, np.flatnonzero(out["exc"] != 0))            # every recovery bar, adoption excluded
    E = entries_of(ctx, GOLD, "1H", "WY-CL", "X-2R50")
    assert np.array_equal(E.bar, np.flatnonzero(out["climax"] != 0))


def test_e_the_real_filters_on_a_synthetic_market(syn):
    ctx = syn["ctx"]
    removed = kept = 0
    for tf in RW.TFS:
        al, ash = F.allow(ctx, tf, F2_OF[tf])
        for rule, x in (("WY-STD", "X-S"), ("WY-AGG", "X-S3"), ("WY-CL", "X-2R50"), ("WY-SP", "X-S")):
            E0, E2 = entries_of(ctx, GOLD, tf, rule, x), entries_of(ctx, GOLD, tf, rule, x, F2_OF[tf])
            ok = np.where(E0.side == 1, al[E0.bar], ash[E0.bar])
            assert np.array_equal(E2.bar, E0.bar[ok]) and np.array_equal(E2.exit_bar, E0.exit_bar[ok]), (tf, rule)
            removed += int((~ok).sum())
            kept += int(ok.sum())
    assert removed > 0 and kept > 0


def test_e_warm_fills_the_cache_the_rows_read(syn):
    ctx = M.Context(M.TMarket2(GOLD, syn["m1"]))
    RW.warm(ctx, RW.variants(GOLD))
    keys = {(k[0], k[2]) for k in ctx.cache}
    for tf in RW.TFS:
        assert (RW.ENGINE_KEY, tf) in keys and ("atr", tf) in keys and ("filter", tf) in keys
    n = len(ctx.cache)
    for v in RW.variants(GOLD):
        RW.build(v, ctx)
    assert len(ctx.cache) == n


# ───────────────────────────── (f) the pooled test and its placebo ─────────────────────────────

def test_f_holding_time_in_signal_bars():
    ctx = ctx_of(hourly_m1(48))
    b = ctx.bars("1H")
    got = RW.hold_bars(b, [5, 5, 5, 5, 5], [ix(9), ix(9, 30), ix(9), ix(6, 3), ix(47, 59)],
                       ["signal", "stop", "gap stop", "target", "end"])
    # X-S at bar 8's close fills at ix(9): 3 bars; a stop inside bar 9: 4; a gap at bar 9's open: 3; at least 1
    assert list(got) == [3, 4, 3, 1, 42]


def _pooled_market(hours=600):
    """The hand-made market with three Standard entries on 1H (two longs, one short) and nothing on 4H and 1D."""
    out = fake_out(hours)
    out["hard_lo"][:], out["hard_hi"][:] = 99.0, 101.0
    hold(out, 98, 131, cid=98, outcome=1)
    hold(out, 198, 211, cid=198, outcome=-1)
    hold(out, 398, 461, cid=398, outcome=1)
    for i, d in ((100, 1), (200, -1), (400, 1)):
        out["entry_std"][i], out["ev_test"][i] = d, True
    ctx = market_with(out, hours=hours)
    RW.use_engine_output(ctx, "4H", fake_out(hours // 4))
    RW.use_engine_output(ctx, "1D", fake_out(hours // 24))
    return ctx, (str(TM.utc(T0)), str(TM.utc(T0 + hours * HOUR)))


def test_f_the_placebo_is_matched_and_executed_by_the_harness():
    ctx, win = _pooled_market()
    real = RW.pooled_trades(ctx, win)
    assert list(real.bar) == [100, 200, 400] and list(real.side) == [1, -1, 1] and set(real.tf) == {"1H"}
    assert list(real.hold) == [31, 11, 61] and list(real.reason) == ["signal"] * 3
    assert np.allclose(real.stop_atr, [1.35, 1.15, 1.35])          # from the actual fill, in ATR of the decision bar
    pl = RW.placebo_trades(ctx, real, n_sets=40, seed=7, window=win)
    b = ctx.bars("1H")
    assert len(pl) == 120 and sorted(Counter(pl.set).values()) == [3] * 40
    j = pl.trade.to_numpy()
    assert np.array_equal(pl.side.to_numpy(), real.side.to_numpy()[j]) and set(pl.tf) == {"1H"}
    assert np.allclose(pl.stop_atr.to_numpy(), real.stop_atr.to_numpy()[j], rtol=1e-12, atol=0)
    assert np.array_equal(pl.hold.to_numpy(), real.hold.to_numpy()[j])
    assert np.array_equal(pl.entry_ix.to_numpy(), b.ex[pl.bar.to_numpy()])
    sig = (pl.reason == "signal").to_numpy()
    assert np.array_equal(pl.exit_ix.to_numpy()[sig], b.ex[(pl.bar + pl.hold).to_numpy()[sig]])
    assert set(pl.reason) <= {"signal", "stop", "gap stop"}
    assert (pl.bar.to_numpy() >= 0).all() and (b.ex[(pl.bar + pl.hold).to_numpy()] < len(ctx.mk.t)).all()
    again = RW.placebo_trades(ctx, real, n_sets=40, seed=7, window=win)
    assert np.array_equal(again.bar, pl.bar)
    other = RW.placebo_trades(ctx, real, n_sets=40, seed=8, window=win)
    assert not np.array_equal(other.bar, pl.bar)
    # a placebo equal to its real trade: on these flat bars both lose exactly the spread
    assert np.allclose(pl.r.to_numpy(), real.r.to_numpy()[j], rtol=0, atol=1e-12)


def test_f_lanes_never_overlap():
    rng = np.random.default_rng(3)
    j = rng.integers(0, 1000, 500)
    x = j + rng.integers(1, 80, 500)
    lanes = RW._lanes(j, x)
    assert sorted(np.concatenate(lanes).tolist()) == list(range(500))
    for lane in lanes:
        o = lane[np.argsort(j[lane])]
        assert np.all(j[o][1:] > x[o][:-1])


def test_f_p_values_count_ties_as_at_least_as_good():
    real = pd.DataFrame({"r": [1.0, 0.0], "pnl": [3.0, 1.0]})
    pl = pd.DataFrame({"set": [0, 0, 1, 1, 2, 2, 3, 3], "trade": [0, 1] * 4,
                       "r": [0.0, 0.0, 1.0, 1.0, 1.0, 0.0, -2.0, 0.0], "pnl": [0.0, 0.0, 9.0, 0.0, 3.0, 1.0, 0.0, 0.0]})
    s, per = RW.pooled_stats(real, pl, n_sets=4)
    assert s["n_matched"] == 2 and s["mean_r"] == 0.5 and s["total_usd"] == 4.0
    assert list(per.mean_r) == [0.0, 1.0, 0.5, -1.0] and list(per.total_usd) == [0.0, 9.0, 4.0, 0.0]
    assert s["p_r"] == pytest.approx(3 / 5) and s["p_usd"] == pytest.approx(3 / 5)
    s, _ = RW.pooled_stats(real, pl[pl.trade == 0], n_sets=4)          # trade 1 has no placebo: left out of both
    assert s["n_matched"] == 1 and s["n_unmatched"] == 1 and s["mean_r"] == 1.0


def test_f_the_pooled_test_on_flat_bars_has_p_one():
    """Every trade on the flat bars loses exactly the spread, so every placebo set equals the real trades: p = 1."""
    ctx, win = _pooled_market()
    pt = RW.pooled_test_run({GOLD: ctx}, window=win, n_sets=25, seed=1)
    s = pt.summary
    assert s["n_matched"] == 3 and s["n_sets"] == 25 and s["p_r"] == 1.0 and s["p_usd"] == 1.0
    assert len(pt.placebo) == 75 and len(pt.sets) == 25 and list(pt.by_series.tf) == ["1H"]


def test_f_the_drivers_claim_15_adapter(monkeypatch):
    ctx, win = _pooled_market()
    monkeypatch.setattr(M, "window_span", lambda name, symbol: win)
    ev = SimpleNamespace(windows=("dev", "val"), symbols=[GOLD], context=lambda s: ctx)
    got = RW.pooled_test(ev, n_sets=20)
    assert len(got) == 1
    r = got[0]
    assert set(r) >= {"part", "symbol", "rows", "dev", "val", "dev_ok", "val_ok", "verdict", "note"}
    assert r["symbol"] == "both" and r["verdict"] == "does not hold" and r["dev_ok"] is False
    assert "p = 1.000" in r["dev"] and "Development + Validation" in r["rows"]


def test_f_the_drivers_claim_16_adapter(monkeypatch):
    out = fake_out(120)
    out["hard_lo"][:], out["hard_hi"][:] = 99.0, 101.0
    hold(out, 10, 120, cid=10, outcome=1)
    out["entry_std"][20], out["ev_test"][20] = 1, True           # a test entry: stop 1.15 ATR below the close
    out["hard_lo"][40] = 97.0
    out["entry_agg"][40], out["ev_sos"][40] = 1, True            # an SOS entry: 3.15 ATR
    out["hard_lo"][60] = 98.0
    out["entry_std"][60], out["ev_lps"][60] = 1, True            # an LPS entry: 2.15 ATR
    ctx = market_with(out)
    win = (str(TM.utc(T0)), str(TM.utc(T0 + 120 * HOUR)))
    monkeypatch.setattr(M, "window_span", lambda name, symbol: win)
    tag = lambda kind: int(RW.tag_of(10, kind))
    sid, aid = "XAUUSDm|1H|WY|WY-STD|S-W|X-S|F0", "XAUUSDm|1H|WY|WY-AGG|S-W|X-S|F0"
    trades = pd.DataFrame({"vid": [sid, sid, aid, aid, sid], "cost": [1.0, 1.0, 1.0, 1.0, 1.5],
                           "tag": [tag(RW.K_TEST), tag(RW.K_LPS), tag(RW.K_TEST), tag(RW.K_SOS), tag(RW.K_TEST)],
                           "r": [2.0, -1.0, 9.0, 0.5, -9.0]})
    ev = SimpleNamespace(windows=("dev", "val"), symbols=[GOLD], context=lambda s: ctx, trades=lambda w: trades)
    got = RW.claim16(ev)
    assert len(got) == 2 and all(r["symbol"] == "both" for r in got)
    assert got[0]["dev_ok"] is True and "test 1.15 (n 1)" in got[0]["dev"] and "SOS 3.15 (n 1)" in got[0]["dev"]
    assert "LPS 2.15 (n 1)" in got[0]["dev"]
    # the test entries' R from WY-STD only (WY-AGG's test entry is the same entry), x1.0 only
    assert "test 2.00 (n 1)" in got[1]["dev"] and "SOS 0.50 (n 1)" in got[1]["dev"] and got[1]["dev_ok"] is True


# ───────────────────────────── (g) real Development bars: an execution smoke test ─────────────────────────────

SMOKE_END = "2019-07-01"
SMOKE_WINDOW = ("2019-01-01", SMOKE_END)
SMOKE_ROWS = [("1H", "WY-STD", "X-S", "F0", False), ("4H", "WY-STD-L", "X-S3", "F0", False),
              ("1H", "WY-AGG", "X-S3", "F0", False), ("1H", "WY-CL", "X-2R50", "F2-4H", False),
              ("1D", "WY-CL", "X-2R50", "F1", False), ("4H", "WY-SP", "X-S", "F2-1D", False),
              ("1H", "WY-SP", "X-S3", "F0", False), ("1H", "WY-STD", "X-S", "F0", True)]
REASONS = {"X-S": {"signal", "stop", "gap stop", "end"}, "X-S3": {"signal", "stop", "gap stop", "target",
                                                                 "gap target", "end"},
           "X-2R50": {"signal", "stop", "gap stop", "target", "gap target", "end"}}


@pytest.fixture(scope="module", params=["XAUUSDm", "BTCUSDm"])
def real_ctx(request, tmp_path_factory):
    """One symbol's market from its data start to 2019-07-01 only (nothing later is read), one at a time."""
    symbol = request.param
    months = set(store.available_months(symbol))
    start = M.data_start(symbol)
    if (2019, 6) not in months or (int(start[:4]), int(start[5:7])) not in months:
        pytest.skip(f"the tick store of {symbol} is not on this machine")
    if symbol == BTC and not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.s_of(SMOKE_END)):
        pytest.skip("the Binance klines are not on this machine")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "STUDY_DIR", tmp_path_factory.mktemp("closed_study2"))
        mk = M.load(symbol, end=SMOKE_END)
    assert mk.end_s == TM.s_of(SMOKE_END) and int(mk.t[-1]) + 60 <= TM.s_of(SMOKE_END)
    yield M.Context(mk)


def test_g_one_row_of_each_rule_type_runs_on_real_development_bars(real_ctx):
    """Development only (2019-01-01 to 2019-06-30). The run must work and its bookkeeping must hold; its profit or
    loss is neither printed nor asserted."""
    ctx = real_ctx
    s = ctx.symbol
    n_runs = n_trades = 0
    for tf, rule, x, filt, control in SMOKE_ROWS:
        if control and s != BTC:
            continue
        v = variant(s, tf, rule, x, filt, control)
        ex = RW.build(v, ctx)
        assert ex.kind == "events" and ex.label == v.id
        E = ex.entries
        b = ctx.bars(tf)
        for cost in M.COSTS:
            r = M.run_exec(ctx.mk, ex, *SMOKE_WINDOW, cost)
            c, tr = r.counts, r.trades
            assert c["candidates"] == c["taken"] + c["busy"] + c["dropped_stop"] + c["dropped_target"], v.id
            assert c["taken"] == len(tr) and c["unfilled"] == 0 and r.kind == "events"
            if len(tr):
                assert set(tr.reason) <= REASONS[x], v.id
                assert set(tr.side) <= {-1, 1} and (tr.risk > 0).all() and np.isfinite(tr.r).all()
                assert np.isfinite(tr.pnl).all() and (tr.exit_ix >= tr.entry_ix).all()
                assert (tr.entry_time >= pd.Timestamp(SMOKE_WINDOW[0], tz="UTC")).all()
                assert (tr.exit_time <= pd.Timestamp(SMOKE_END, tz="UTC")).all()
                row = {int(bb): q for q, bb in enumerate(E.bar)}
                assert set(tr.bar) <= set(row), v.id                              # every trade is one of the entries
                for t in tr.itertuples(index=False):
                    q = row[int(t.bar)]
                    assert int(t.entry_ix) == int(b.ex[t.bar]) and int(t.side) == int(E.side[q])
                    assert int(t.tag) == int(E.tag[q])
                    xb = int(E.exit_bar[q])
                    if t.reason == "signal":
                        assert xb >= 0 and int(t.exit_ix) == int(b.ex[xb]), v.id      # the row's own exit decision
                    if rule != "WY-CL":
                        assert t.reason != "target" or x == "X-S3"
            M.metrics(r)                                    # the driver's scores can be computed (not shown)
            n_runs += 1
            n_trades += len(tr)
    assert n_runs == 2 * (len(SMOKE_ROWS) - (0 if s == BTC else 1)) and n_trades > 0
