"""
The TradeIQ study's grid (``backtesting/research/tradeiq.py``), PREREG sections 6 and 7 with DEVIATIONS 19-26.

* The grid: exactly the variants of PREREG 6's grid sentence, enumerated here again from the plan's text (750).
* The rules on hand-made lines: every family, the filters, the filtered state; F2 reads the last CLOSED higher bar.
* The selection, the RSI comparison and the bootstrap (SPA equal to ``silver.spa_test``; the Reality Check) on
  hand-made tables; the readings written after the review (DEVIATIONS 28-31): the finalists against buy-and-hold and
  PREREG 8's rule on the R2 rows, the runners-up, the comparison curves and the RSI baselines, each filter against F0,
  and the claims of PREREG 9 recounted on a random grid; the within-timeframe variance of the deflated Sharpe.
* ``select`` on a copy of ``run``'s CSVs reproduces the written selection files.
* Real data (skipped without the tick store; the guard is closed, so nothing after 2024-06-30 is read):
  - no look-ahead: every state up to a time T is unchanged when the data after T is removed;
  - F2 on the real bars: each signal bar reads the last higher bar closed at its close, and nothing later;
  - ten variants (every family, both symbols, F1 / F2 / F3, S0 and S1, RV) re-derived by a separate bar-by-bar
    reading of the rules and a separate M1 loop of the execution model, trade by trade, in Development at x1.0 and
    Validation at x1.5; and, when the study's CSVs exist, those trades and nets are the ones written;
  - no missing value and no exact tie with a level on the bars the windows read.
"""

from __future__ import annotations

import bisect
import hashlib
import math

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import tradeiq as Q
from backtesting.research import tradeiq_ind as I
from backtesting.research import tradeiq_market as TM

SYMS = ("XAUUSDm", "BTCUSDm")
T0 = TM.s_of("2019-03-04")          # a Monday
NAN = math.nan


@pytest.fixture(autouse=True)
def closed_guard(tmp_path, monkeypatch):
    """The guard reads an empty folder: FINALISTS.md is absent, the hold-out is closed."""
    d = tmp_path / "study"
    d.mkdir()
    monkeypatch.setattr(TM, "STUDY_DIR", d)
    monkeypatch.delenv("ALCADEIAS_STORE_DIR", raising=False)
    return d


# ───────────────────────────── the grid ─────────────────────────────

def plan_grid(symbol):
    """PREREG 6's grid sentence, word by word: {RSI, LaRSI, VWRSI, TSI, QQE} x {R1, R2} x filters, {VWRSI, QQE} x R3
    x filters, the R4 controls of RSI, LaRSI, VWRSI and TSI, the two other controls, MA200 alone (R1, R2); every row
    with S0 and S1; 1H, 4H, 1D; for BTC also the VWRSI rows with Binance volume. Filters: F0, F1, F2 where defined
    (1H: 4H and 1D; 4H: 1D; 1D: none), F3."""
    filters = {"1H": ["F0", "F1", "F2-4H", "F2-1D", "F3"], "4H": ["F0", "F1", "F2-1D", "F3"], "1D": ["F0", "F1", "F3"]}
    rows = set()
    for tf, fl in filters.items():
        for stop in ("S0", "S1"):
            def add(ind, fam, f="F0"):
                rows.add(f"{symbol}|{tf}|{ind}|{fam}|{f}|{stop}")
            vw = ["VWRSI", "VWRSI-RV"] if symbol == "BTCUSDm" else ["VWRSI"]
            for ind in ["RSI", "LaRSI", "TSI", "QQE"] + vw:
                for fam in ("R1", "R2"):
                    for f in fl:
                        add(ind, fam, f)
            for ind in ["QQE"] + vw:
                for f in fl:
                    add(ind, "R3", f)
            for ind in ["RSI", "LaRSI", "TSI"] + vw:
                add(ind, "R4")
            add("TSI", "CTL-SIGNAL")
            add("QQE", "CTL-WHITE")
            add("MA200", "R1")
            add("MA200", "R2")
    return rows


def test_the_grid_is_the_plans_750_variants():
    g = {s: Q.grid(s) for s in SYMS}
    for s in SYMS:
        ids = [v.vid for v in g[s]]
        assert len(ids) == len(set(ids))
        assert set(ids) == plan_grid(s)
    assert len(g["XAUUSDm"]) == 336 and len(g["BTCUSDm"]) == 414
    assert sum(len(v) for v in g.values()) == 750
    assert sum(v.indicator == "VWRSI-RV" for v in g["BTCUSDm"]) == 78
    for s in SYMS:                                   # per timeframe: 68 / 56 / 44 rule rows, two stops each
        n = pd.Series([v.tf for v in g[s] if v.indicator != "VWRSI-RV"]).value_counts()
        assert dict(n) == {"1H": 136, "4H": 112, "1D": 88}
    fr = Q.grid_frame()
    assert list(fr.vid) == [v.vid for s in SYMS for v in g[s]]
    assert all(Q.Variant.of(v.vid) == v for s in SYMS for v in g[s])
    assert set(fr.group) == {"RSI", "LaRSI", "VWRSI", "TSI", "QQE", "MA200"}
    with pytest.raises(ValueError):
        Q.grid("XAGUSDm")


# ───────────────────────────── the rules on hand-made lines ─────────────────────────────

def lines(n, **kw):
    L = {k: np.full(n, NAN) for k in ("close", "RSI", "LaRSI", "VWRSI", "VWRSI:score", "TSI", "TSI:signal",
                                       "QQE:white", "MA200")}
    L["QQE:color"] = np.zeros(n, np.int8)
    for k, v in kw.items():
        L[k.replace("__", ":")] = np.asarray(v, np.int8 if k == "QQE__color" else np.float64)
    return L


def test_side_and_hold():
    assert list(Q.side([NAN, 49.0, 51.0, 50.0, 60.0, 40.0], 50.0)) == [0, -1, 1, 0, 1, -1]
    assert list(Q.hold([0, 1, 0, 0, 0, 1, 0], [0, 0, 0, 1, 0, 0, 0])) == [0, 1, 1, -1, -1, 1, 1]
    assert list(Q.hold([0, 0], [0, 0])) == [0, 0]
    with pytest.raises(ValueError):
        Q.hold([1], [1])


def test_r1_r2_on_the_side_of_the_middle():
    L = lines(6, RSI=[NAN, 49, 51, 50, 60, 40], TSI=[NAN, -1, 2, 0, 0.5, -0.1])
    assert list(Q.raw_state(L, "RSI", "R1")) == [0, -1, 1, 0, 1, -1]
    assert list(Q.raw_state(L, "RSI", "R2")) == [0, 0, 1, 0, 1, 0]
    assert list(Q.raw_state(L, "TSI", "R1")) == [0, -1, 1, 0, 1, -1]           # the TSI's middle is 0
    L = lines(4, close=[10, 9, 11, 10], MA200=[NAN, 10, 10, 10])
    assert list(Q.raw_state(L, "MA200", "R1")) == [0, -1, 1, 0]
    assert list(Q.raw_state(L, "MA200", "R2")) == [0, 0, 1, 0]


def test_qqe_r1_holds_through_gray_r2_flat_on_red_r3_flat_on_gray():
    L = lines(8, QQE__color=[0, 1, 0, 0, -1, 0, 1, 0])
    assert list(Q.raw_state(L, "QQE", "R1")) == [0, 1, 1, 1, -1, -1, 1, 1]
    assert list(Q.raw_state(L, "QQE", "R2")) == [0, 1, 1, 1, 0, 0, 1, 1]
    assert list(Q.raw_state(L, "QQE", "R3")) == [0, 1, 0, 0, -1, 0, 1, 0]


def test_vwrsi_r3_stands_aside_while_the_score_is_above_0():
    L = lines(5, VWRSI=[60, 60, 40, 40, 45], VWRSI__score=[NAN, 0, 0.1, 0, 2e-7])
    assert list(Q.raw_state(L, "VWRSI", "R3")) == [0, 1, 0, -1, 0]
    L["VWRSI-RV"], L["VWRSI-RV:score"] = L["VWRSI"], L["VWRSI:score"]
    assert list(Q.raw_state(L, "VWRSI-RV", "R3")) == [0, 1, 0, -1, 0]
    with pytest.raises(ValueError):
        Q.raw_state(L, "RSI", "R3")


def test_r4_reversal_levels_and_the_controls_hold_the_last_cross():
    r = [35, 29, 31, 50, 71, 69, 60, 25, 30.0, 30.5]
    L = lines(10, RSI=r, LaRSI=r, TSI=[0, -31, -29, 0, 31, 29, 5, -40, -30, -29])
    assert list(Q.raw_state(L, "RSI", "R4")) == [0, 0, 1, 1, 1, -1, -1, -1, -1, 1]       # up through 30, down through 70
    # LaRSI 20 / 80: 25 -> 30 is no cross of 20; nothing crosses 80
    assert list(Q.raw_state(L, "LaRSI", "R4")) == [0] * 10
    assert list(Q.raw_state(L, "TSI", "R4")) == [0, 0, 1, 1, 1, -1, -1, -1, -1, 1]       # -30 / +30
    L = lines(6, TSI=[1, 2, 3, 2, 1, 4], TSI__signal=[2, 2, 2, 2, 2, 2])
    assert list(Q.raw_state(L, "TSI", "CTL-SIGNAL")) == [0, 0, 1, 1, -1, 1]              # 2 == 2 then 3 > 2: a cross
    L = lines(5, QQE__white=[NAN, -1, 1, -2, -3])
    assert list(Q.raw_state(L, "QQE", "CTL-WHITE")) == [0, 0, 1, -1, -1]


def test_filters_make_a_state_that_is_not_allowed_flat():
    raw = np.array([1, 1, 1, -1, -1, -1, 0], np.int8)
    L = lines(7, close=[11, 9, 11, 9, 11, 10, 11], MA200=[10] * 7, TSI=[1, 1, -1, -1, 1, -2, 1])
    al, ash = Q.allowed_of(L, "F1")
    assert list(Q.apply_filter(raw, al, ash)) == [1, 0, 1, -1, 0, 0, 0]                # 10 = 10: neither side
    al, ash = Q.allowed_of(L, "F3")
    assert list(Q.apply_filter(raw, al, ash)) == [1, 1, 0, -1, 0, -1, 0]
    al, ash = Q.allowed_of(L, "F0")
    assert list(Q.apply_filter(raw, al, ash)) == list(raw)
    f2 = (np.array([1, 0, 0, 0, 0, 0, 0], bool), np.array([0, 0, 0, 1, 1, 0, 0], bool))
    assert list(Q.apply_filter(raw, *Q.allowed_of(L, "F2-1D", f2))) == [1, 0, 0, -1, -1, 0, 0]
    with pytest.raises(ValueError):
        Q.allowed_of(L, "F2-4H")


def _market(k_minutes, sp=0.2, symbol="XAUUSDm"):
    o = 100.0 + 0.01 * np.arange(k_minutes)
    t = T0 + 60 * np.arange(k_minutes, dtype=np.int64)
    m1 = {"t": t, "o": o, "h": o + 0.03, "l": o - 0.03, "c": o + 0.005, "spread_mean": np.full(k_minutes, sp),
          "n": np.ones(k_minutes)}
    return TM.TMarket(symbol, m1)


def test_f2_reads_the_last_closed_higher_bar_hand_made():
    m = _market(12 * 60)
    h1, h4 = m.tbars("1H"), m.tbars("4H")
    assert list((h4.tc - T0) // 3600) == [4, 8, 12] and list((h1.tc - T0) // 3600) == list(range(1, 13))
    up, dn = Q.htf_sides(h4, h1, close=[10.0, 20.0, 30.0], ma=[15.0, 15.0, NAN])
    # the 1H bars closing at 1..3 h see no closed 4H bar; at 4..7 h the first (10 < 15); at 8..11 h the second
    # (20 > 15); at 12 h the third, whose MA200 has no value: neither side
    assert list(up.astype(int)) == [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0]
    assert list(dn.astype(int)) == [0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0]


def test_the_filtered_state_opens_where_the_filter_turns_in_favour_and_stays_flat_after_a_stop():
    """DEVIATIONS 20 and 1 through the executor: the oscillator is long all along; the filter allows it on bars 2-4
    and again from bar 6. The position opens at bar 2's close although the oscillator did not cross there, closes at
    bar 5's, opens again at bar 6's. With a stop hit inside the entry's own M1 bar, the variant stays flat while the
    filtered state stays long, and enters again only where that state changes (bar 6)."""
    m = _market(9 * 60)
    b = m.tbars("1H")
    raw = np.ones(len(b), np.int8)
    al = np.array([0, 0, 1, 1, 1, 0, 1, 1, 1], bool)
    st = Q.apply_filter(raw, al, np.zeros(len(b), bool))
    assert list(st) == [0, 0, 1, 1, 1, 0, 1, 1, 1]
    r = TM.run(m, b, st, T0, int(m.t[-1]) + 60)
    tr = r.trades
    assert list(tr.entry_ix) == [b.ex[2], b.ex[6]] and list(tr.exit_ix) == [b.ex[5], len(m) - 1]
    assert list(tr.reason) == ["signal", "end"]
    # the entry pays the ask (open + 0.2); a stop 0.22 below it is 0.02 under the open, and the M1 low is 0.03 under
    # the open: the stop fills inside the entry's own M1 bar
    r = TM.run(m, b, st, T0, int(m.t[-1]) + 60, stop=np.full(len(b), 0.22))
    tr = r.trades
    assert list(tr.reason) == ["stop", "stop"]
    assert list(tr.entry_ix) == [b.ex[2], b.ex[6]] and list(tr.exit_ix) == [b.ex[2], b.ex[6]]


# ───────────────────────────── the selection, the comparison, the bootstrap ─────────────────────────────

def _res_rows(vid, dev, val, devval):
    v = Q.Variant.of(vid)
    out = []
    for w, x in (("dev", dev), ("val", val), ("devval", devval)):
        base = {"net": 100.0, "net_x15": 90.0, "trades": 50, "profit_dd": 2.0, "pos_q_share": 0.6, "sharpe_w": 1.0,
                "max_dd": 50.0, "max_losing_streak": 3}
        base.update(x)
        out.append({**v.ident(), "window": w, **base})
    return out


def test_the_qualification_rules_and_the_finalist_rule():
    rows = []
    G = "BTCUSDm|4H"
    rows += _res_rows(f"{G}|RSI|R1|F0|S0", {}, {}, {"profit_dd": 3.0})                       # qualifies, D+V 3.0
    rows += _res_rows(f"{G}|RSI|R1|F1|S0", {}, {}, {"profit_dd": 4.0})                       # qualifies, D+V 4.0
    rows += _res_rows(f"{G}|VWRSI-RV|R1|F0|S0", {}, {}, {"profit_dd": 5.0})                  # qualifies, D+V 5.0
    rows += _res_rows(f"{G}|VWRSI|R1|F0|S0", {}, {}, {"profit_dd": 4.5})                     # the same indicator
    rows += _res_rows(f"{G}|QQE|R1|F0|S0", {"profit_dd": 1.5}, {}, {"profit_dd": 2.0})       # tie on D+V with TSI ...
    rows += _res_rows(f"{G}|TSI|R1|F0|S0", {"profit_dd": 1.2}, {}, {"profit_dd": 2.0})       # ... broken by dev P/DD
    rows += _res_rows(f"{G}|LaRSI|R1|F0|S0", {"net_x15": -1.0}, {}, {"profit_dd": 9.0})      # fails rule 1
    rows += _res_rows(f"{G}|LaRSI|R2|F0|S0", {"trades": 29}, {}, {"profit_dd": 9.0})         # fails rule 2
    rows += _res_rows("BTCUSDm|1D|LaRSI|R2|F0|S0", {"trades": 15}, {}, {"profit_dd": 1.0})   # 15 is enough on 1D
    rows += _res_rows(f"{G}|MA200|R1|F0|S0", {"profit_dd": 0.99}, {}, {"profit_dd": 9.0})    # fails rule 3 (P/DD)
    rows += _res_rows(f"{G}|MA200|R2|F0|S0", {"pos_q_share": 0.49}, {}, {"profit_dd": 9.0})  # fails rule 3 (quarters)
    rows += _res_rows(f"{G}|TSI|R2|F0|S0", {"profit_dd": NAN}, {}, {"profit_dd": 9.0})       # no drawdown: no pass
    rows += _res_rows(f"{G}|QQE|R2|F0|S0", {}, {"net": 0.0}, {"profit_dd": 9.0})             # fails rule 4
    q = Q.qualification(pd.DataFrame(rows)).set_index("vid")
    ok = set(q.index[q.qualifies])
    assert ok == {f"{G}|RSI|R1|F0|S0", f"{G}|RSI|R1|F1|S0", f"{G}|VWRSI-RV|R1|F0|S0", f"{G}|VWRSI|R1|F0|S0",
                  f"{G}|QQE|R1|F0|S0", f"{G}|TSI|R1|F0|S0", "BTCUSDm|1D|LaRSI|R2|F0|S0"}
    assert not q.loc[f"{G}|LaRSI|R1|F0|S0", "q1"] and not q.loc[f"{G}|LaRSI|R2|F0|S0", "q2"]
    assert not q.loc[f"{G}|TSI|R2|F0|S0", "q3"] and not q.loc[f"{G}|QQE|R2|F0|S0", "q4"]
    fin = q[q.finalist].sort_values("rank")
    # VWRSI-RV (5.0) takes the VWRSI's place; RSI F1 (4.0); then QQE over TSI on the tie (dev P/DD 1.5 > 1.2)
    assert list(fin.index) == [f"{G}|VWRSI-RV|R1|F0|S0", f"{G}|RSI|R1|F1|S0", f"{G}|QQE|R1|F0|S0"]
    assert list(q.loc[[f"{G}|VWRSI-RV|R1|F0|S0", f"{G}|VWRSI|R1|F0|S0", f"{G}|RSI|R1|F1|S0"], "rank"]) == [1, 2, 3]


def test_vs_rsi_compares_the_same_row_of_the_rsi():
    rows = []
    rows += _res_rows("XAUUSDm|1H|RSI|R1|F2-4H|S1", {"net": 50.0, "trades": 100}, {"net": 5.0, "profit_dd": NAN}, {})
    rows += _res_rows("XAUUSDm|1H|LaRSI|R1|F2-4H|S1", {"net": 60.0, "profit_dd": 1.0, "trades": 40},
                      {"net": 4.0, "profit_dd": 3.0}, {})
    rows += _res_rows("XAUUSDm|1H|QQE|R3|F0|S0", {}, {}, {})                                  # no RSI R3: not compared
    rows += _res_rows("XAUUSDm|1H|RSI|R4|F0|S0", {"net": -5.0}, {}, {})
    rows += _res_rows("XAUUSDm|1H|TSI|R4|F0|S0", {"net": -5.0}, {}, {})                        # equal: no win
    vs = Q.vs_rsi(pd.DataFrame(rows)).set_index("vid")
    assert set(vs.index) == {"XAUUSDm|1H|LaRSI|R1|F2-4H|S1", "XAUUSDm|1H|TSI|R4|F0|S0"}
    a = vs.loc["XAUUSDm|1H|LaRSI|R1|F2-4H|S1"]
    assert a.rsi_vid == "XAUUSDm|1H|RSI|R1|F2-4H|S1"
    assert a.dev_win_net and not a.dev_win_pdd and a.dev_fewer_trades
    assert not a.val_win_net and (isinstance(a.val_win_pdd, float) and math.isnan(a.val_win_pdd))
    assert not vs.loc["XAUUSDm|1H|TSI|R4|F0|S0", "dev_win_net"]
    s = Q.vs_rsi_summary(vs.reset_index())
    la = s[(s.by == "indicator") & (s.indicator == "LaRSI")].iloc[0]
    assert (la.n, la.dev_wins_net, la.dev_wins_pdd, la.dev_n_pdd, la.val_n_pdd) == (1, 1, 0, 1, 0)


def test_the_bootstrap_is_silvers_spa_and_adds_the_reality_check():
    from backtesting.research import silver as S
    rng = np.random.default_rng(3)
    D = rng.normal(0.0, 1.0, (120, 12))
    D[:, 5] = 0.0                                                    # a variant that never trades is left out
    for B_ in (200, 300):
        p, best = S.spa_test(D, B_=B_)
        got = Q.bootstrap_pvalues(D, B_=B_)
        assert got["spa_p"] == p and got["spa_best"] == best and got["n_used"] == 11
    assert Q.bootstrap_pvalues(D, B_=300)["rc_p"] > 0.05            # noise: no variant beats flat
    D[:, 2] += 0.6                                                   # one clearly profitable variant
    got = Q.bootstrap_pvalues(D, B_=300)
    assert got["rc_p"] < 0.01 and got["rc_best"] == 2 and got["spa_p"] < 0.01


def test_within_group_variance_pools_the_spread_around_each_groups_mean():
    x, g = [1.0, 2.0, 3.0, 10.0, 11.0, 12.0], ["1H", "1H", "1H", "4H", "4H", "4H"]
    var_w, between = Q.within_group_variance(x, g)
    assert var_w == 1.0                                              # (2 + 2) / (6 - 2)
    assert abs(between - (1.0 - 4.0 / 125.5)) < 1e-12               # total sum of squares 125.5
    assert Q.within_group_variance([1.0, 3.0, 2.0, 4.0], ["a", "a", "b", "b"])[0] == 2.0      # (2 + 2) / (4 - 2)
    with pytest.raises(ValueError):
        Q.within_group_variance([1.0, NAN, 2.0], ["a", "a", "b"])


# ── the exam against buy-and-hold, the runners-up, the curves (DEVIATIONS 28-29) ──

def _bh_frame(symbol, nets, dds):
    rows = []
    for w, net, dd in zip(Q.RUN_WINDOWS, nets, dds):
        for cost, extra in ((1.0, 0.0), (1.5, -1.0)):               # the x1.5 rows must not be read
            rows.append({"symbol": symbol, "window": w, "cost": cost, "bh_net": net + extra, "bh_max_dd": dd,
                         "bh_profit_dd": (net + extra) / dd})
    return pd.DataFrame(rows)


def test_the_exam_rule_and_the_finalists_against_buy_and_hold():
    assert list(Q.exam_rule([1.0, 1.0, 1.0, 0.0, -1.0, 1.0], [0.5, 0.49, NAN, 2.0, 2.0, 9.0])) == \
        [True, False, False, False, False, True]
    w = {"time_in_mkt": 0.25, "n_long": 10, "n_short": 0}
    rows = []
    rows += _res_rows("XAUUSDm|1H|QQE|R2|F0|S0", {**w, "net": 120.0, "profit_dd": 2.4},
                      {**w, "net": 30.0, "max_dd": 50.0, "profit_dd": 0.6}, {**w, "net": 150.0, "profit_dd": 1.5})
    rows += _res_rows("XAUUSDm|1H|RSI|R1|F0|S0", {**w, "n_short": 7, "net": -5.0, "profit_dd": -0.1},
                      {**w, "n_short": 3, "net": 40.0, "profit_dd": 0.5}, {**w, "n_short": 10, "profit_dd": 0.4})
    res = pd.DataFrame(rows)
    bh = _bh_frame("XAUUSDm", (400.0, 200.0, 600.0), (200.0, 100.0, 200.0))
    v = Q.vs_buy_and_hold(res, bh, ["XAUUSDm|1H|QQE|R2|F0|S0"]).set_index("window")
    assert list(v.index) == ["dev", "val", "devval"] and set(v.n) == {1}
    assert v.loc["val", "bh_net"] == 200.0 and v.loc["val", "bh_profit_dd"] == 2.0      # x1.0, not x1.5
    assert v.loc["val", "bh_exposure_matched_net"] == 0.25 * 200.0
    assert v.loc["val", "exam_rule"] and not v.loc["val", "pdd_above_bh"] and not v.loc["val", "net_above_exposure_matched"]
    assert v.loc["dev", "pdd_above_bh"] and v.loc["dev", "net_above_exposure_matched"]          # 2.4 > 2.0, 120 > 100
    assert v.loc["devval", "bh_exam_rule"]
    rates = Q.exam_rule_rates(res, bh, pd.DataFrame({"vid": ["XAUUSDm|1H|QQE|R2|F0|S0"], "symbol": ["XAUUSDm"],
                                                     "qualifies": [True]})).set_index(["window", "rows"])
    assert rates.loc[("dev", "R2 rows (long only)"), "pass"] == 1 and rates.loc[("dev", "other rows"), "pass"] == 0
    assert rates.loc[("val", "other rows"), "pass"] == 1                                       # P/DD 0.5 passes
    assert rates.loc[("devval", "other rows"), "pass"] == 0 and rates.loc[("devval", "all rows"), "n"] == 2
    assert rates.loc[("val", "qualifiers"), "pass"] == 1 and rates.loc[("val", "buy-and-hold"), "pass"] == 1


def _selection_case():
    """BTC 4H: VWRSI R3 (D+V 5.0), LaRSI R2 F1 S1 (4.0), RSI R1 (3.0) are the finalists; the TSI (2.5) qualifies
    without a slot; MA200 alone and the RSI pair of the LaRSI do not qualify."""
    G = "BTCUSDm|4H"
    rows = []
    rows += _res_rows(f"{G}|VWRSI|R3|F0|S0", {}, {}, {"profit_dd": 5.0, "profit_dd_x15": 4.0})
    rows += _res_rows(f"{G}|LaRSI|R2|F1|S1", {}, {}, {"profit_dd": 4.0, "profit_dd_x15": 3.5})
    rows += _res_rows(f"{G}|RSI|R1|F0|S0", {}, {}, {"profit_dd": 3.0, "profit_dd_x15": 2.0})
    rows += _res_rows(f"{G}|TSI|R1|F0|S0", {}, {}, {"net": 125.0, "max_dd": 50.0, "profit_dd": 2.5,
                                                   "profit_dd_x15": 2.2})
    rows += _res_rows(f"{G}|RSI|R2|F1|S1", {"trades": 3}, {}, {"profit_dd": 1.0, "profit_dd_x15": 0.9})
    rows += _res_rows(f"{G}|MA200|R1|F0|S0", {"net_x15": -1.0}, {}, {"profit_dd": 9.0, "profit_dd_x15": 8.0})
    rows += _res_rows(f"{G}|MA200|R2|F0|S0", {"net_x15": -1.0}, {}, {"profit_dd": 1.0, "profit_dd_x15": 0.9})
    res = pd.DataFrame(rows)
    return res, Q.qualification(res)


def test_the_runners_up_need_the_net_at_their_own_drawdown():
    res, qual = _selection_case()
    fin = qual[qual.finalist].sort_values("rank")
    assert [Q.Variant.of(v).indicator for v in fin.vid] == ["VWRSI", "LaRSI", "RSI"]
    ru = Q.runners_up(qual, res)
    assert list(ru.indicator) == ["TSI"]                           # MA200 has no qualifier, QQE no row
    r = ru.iloc[0]
    assert r.last_finalist == "BTCUSDm|4H|RSI|R1|F0|S0" and r.last_finalist_profit_dd == 3.0
    assert abs(r.gap_profit_dd - 0.5) < 1e-12 and abs(r.net_needed - (3.0 * 50.0 - 125.0)) < 1e-12
    assert (r.devval_profit_dd_x15, r.last_finalist_profit_dd_x15) == (2.2, 2.0)


def test_rsi_baseline_and_the_comparison_curves():
    assert Q.rsi_baseline("BTCUSDm|1D|LaRSI|R2|F3|S1") == "BTCUSDm|1D|RSI|R2|F3|S1"
    assert Q.rsi_baseline("BTCUSDm|1D|VWRSI|R3|F0|S1") == "BTCUSDm|1D|RSI|R1|F0|S1"
    assert Q.rsi_baseline("XAUUSDm|1H|QQE|R3|F2-4H|S0") == "XAUUSDm|1H|RSI|R1|F2-4H|S0"
    assert Q.rsi_baseline("XAUUSDm|4H|TSI|CTL-SIGNAL|F0|S1") == "XAUUSDm|4H|RSI|R1|F0|S1"
    assert Q.rsi_baseline("XAUUSDm|4H|QQE|CTL-WHITE|F0|S1") == "XAUUSDm|4H|RSI|R1|F0|S1"
    assert Q.rsi_baseline("XAUUSDm|4H|MA200|R2|F0|S0") == "XAUUSDm|4H|RSI|R2|F0|S0"
    assert Q.rsi_baseline("BTCUSDm|1D|VWRSI-RV|R4|F0|S0") == "BTCUSDm|1D|RSI|R4|F0|S0"
    assert Q.rsi_baseline("XAUUSDm|4H|RSI|R2|F1|S0") == "XAUUSDm|4H|RSI|R2|F1|S0"
    ids = {v.vid for s in SYMS for v in Q.grid(s)}
    assert all(Q.rsi_baseline(v) in ids and Q.Variant.of(Q.rsi_baseline(v)).indicator == "RSI" for v in ids)
    _, qual = _selection_case()
    cv = Q.curves(qual)
    got = dict(zip(cv.role, cv.vid))
    G = "BTCUSDm|4H"
    assert got == {"finalist 1": f"{G}|VWRSI|R3|F0|S0", "finalist 2": f"{G}|LaRSI|R2|F1|S1",
                   "finalist 3": f"{G}|RSI|R1|F0|S0",
                   "best RSI": f"{G}|RSI|R1|F0|S0", "best LaRSI": f"{G}|LaRSI|R2|F1|S1",
                   "best VWRSI": f"{G}|VWRSI|R3|F0|S0", "best TSI": f"{G}|TSI|R1|F0|S0",
                   "best MA200": f"{G}|MA200|R1|F0|S0",                  # no qualifier: the highest D+V P/DD
                   "RSI baseline of finalist 1": f"{G}|RSI|R1|F0|S0",    # R3 has no RSI pair: R1
                   "RSI baseline of finalist 2": f"{G}|RSI|R2|F1|S1",    # the pair, although it does not qualify
                   "RSI baseline of finalist 3": f"{G}|RSI|R1|F0|S0"}    # an RSI finalist is its own
    c = cv.set_index("role")
    assert not c.loc["best MA200", "qualifies"] and not c.loc["RSI baseline of finalist 2", "qualifies"]
    assert c.loc["best TSI", "qualifies"] and not c.loc["best TSI", "finalist"]


# ── question 2: a filter against no filter (DEVIATIONS 30) ──

def test_vs_f0_pairs_each_filter_with_f0_and_leaves_out_the_tsis_f3():
    rows = []
    rows += _res_rows("XAUUSDm|1H|LaRSI|R2|F0|S0", {"net": 50.0, "profit_dd": 1.0}, {"net": 10.0, "profit_dd": 0.5}, {})
    rows += _res_rows("XAUUSDm|1H|LaRSI|R2|F1|S0", {"net": 60.0, "profit_dd": 2.0}, {"net": 11.0, "profit_dd": 0.6}, {})
    rows += _res_rows("XAUUSDm|1H|LaRSI|R2|F2-4H|S0", {"net": 50.0, "profit_dd": 0.9}, {"net": 9.0, "profit_dd": 0.4},
                      {})                                           # equal net is no win
    rows += _res_rows("XAUUSDm|1H|LaRSI|R2|F3|S0", {"net": 40.0, "profit_dd": 1.5}, {"net": 20.0, "profit_dd": NAN}, {})
    rows += _res_rows("XAUUSDm|1H|TSI|R1|F0|S0", {}, {}, {})
    rows += _res_rows("XAUUSDm|1H|TSI|R1|F3|S0", {}, {}, {})         # the TSI's F3 is its F0: left out
    rows += _res_rows("XAUUSDm|1H|MA200|R1|F0|S0", {}, {}, {})
    rows += _res_rows("XAUUSDm|1H|RSI|R4|F0|S0", {}, {}, {})
    vf = Q.vs_f0(pd.DataFrame(rows)).set_index("vid")
    assert set(vf.index) == {"XAUUSDm|1H|LaRSI|R2|F1|S0", "XAUUSDm|1H|LaRSI|R2|F2-4H|S0", "XAUUSDm|1H|LaRSI|R2|F3|S0"}
    assert set(vf.f0_vid) == {"XAUUSDm|1H|LaRSI|R2|F0|S0"}
    f3 = vf.loc["XAUUSDm|1H|LaRSI|R2|F3|S0"]
    assert not f3.dev_win_net and f3.dev_win_pdd and f3.val_win_net and math.isnan(f3.val_win_pdd)
    s = Q.vs_f0_summary(vf.reset_index())
    v = s[s.by == "filter"].set_index("filter").verdict
    assert v.to_dict() == {"F1": "helps", "F2-4H": "does not help", "F3": "mixed"}
    assert set(s.by) == {"filter", "filter+tf", "filter+indicator"}
    assert Q.verdict(True, True) == "holds" and Q.verdict(False, False) == "does not hold"
    assert Q.verdict(True, False) == "mixed" and Q.verdict(False, False, False, True) == "mixed"


# ── the video's claims (DEVIATIONS 31) ──

def _random_results(seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for s in SYMS:
        for v in Q.grid(s):
            for w in Q.RUN_WINDOWS:
                rows.append({**v.ident(), "window": w, "net": float(rng.normal(20, 100)),
                             "profit_dd": float(rng.normal(1, 1)), "max_dd": float(rng.uniform(50, 300)),
                             "trades": int(rng.integers(5, 400)), "max_losing_streak": int(rng.integers(1, 15))})
    return pd.DataFrame(rows)


def test_the_claims_are_counted_on_their_own_rows_per_symbol_and_window():
    res = _random_results()
    vs, vf = Q.vs_rsi(res), Q.vs_f0(res)
    cl = Q.claims(res, vs, vf)
    assert set(cl.verdict) <= {"holds", "does not hold", "mixed", "cannot be tested"}
    one = cl[cl.claim == 1].iloc[0]
    assert one.verdict == "cannot be tested" and one.symbol == "both"
    d = res[res.window == "dev"].set_index("vid")
    v = res[res.window == "val"].set_index("vid")
    part = cl.set_index(["symbol", "part"])
    # an independent recount of a few parts, by joining each row with its counterpart
    for s in SYMS:
        for ind in ("QQE", "TSI", "VWRSI", "LaRSI") + (("VWRSI-RV",) if s == "BTCUSDm" else ()):
            mine = d[(d.symbol == s) & (d.indicator == ind) & d.family.isin(["R1", "R2", "R4"])]
            rsi = [f"{s}|{x.tf}|RSI|{x.family}|{x['filter']}|{x['stop']}" for _, x in mine.iterrows()]
            kd = int((mine.net.to_numpy() > d.loc[rsi].net.to_numpy()).sum())
            kv = int((v.loc[mine.index].net.to_numpy() > v.loc[rsi].net.to_numpy()).sum())
            got = part.loc[(s, f"{ind} beats the RSI in most of its pairs")]
            assert (got.dev, got.val) == (f"{kd}/{len(mine)}", f"{kv}/{len(mine)}")
            assert got.verdict == Q.verdict(2 * kd > len(mine), 2 * kv > len(mine))
        la = d[(d.symbol == s) & (d.indicator == "LaRSI") & (d.tf == "1H") & (d["filter"] == "F0")]
        assert len(la) == 6
        got = part.loc[(s, "on 1H LaRSI on its own mostly did not make money (net > 0 in at most half)")]
        assert got.dev == f"{int((la.net > 0).sum())}/6" and got.val == f"{int((v.loc[la.index].net > 0).sum())}/6"
        sig = d[(d.symbol == s) & (d.family == "CTL-SIGNAL")]
        zero = [x.replace("|CTL-SIGNAL|", "|R1|") for x in sig.index]
        got = part.loc[(s, "the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs")]
        assert got.dev == f"{int((d.loc[zero].net.to_numpy() > sig.net.to_numpy()).sum())}/6"
        four = d[(d.symbol == s) & d.indicator.isin(["LaRSI", "VWRSI", "VWRSI-RV", "TSI", "QQE"])]
        assert len(four) == {"XAUUSDm": 270, "BTCUSDm": 348}[s]
        sh = four.groupby("tf").net.apply(lambda x: (x > 0).mean())
        got = part.loc[(s, "the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0)")]
        assert got.dev == ", ".join(f"{tf} {sh[tf]:.0%}" for tf in Q.TFS)
        assert bool(got.dev_ok) == bool(sh["1H"] < min(sh["4H"], sh["1D"]))
    rv = d[d.indicator == "VWRSI-RV"]
    tick = [x.replace("|VWRSI-RV|", "|VWRSI|") for x in rv.index]
    got = part.loc[("BTCUSDm", "the VWRSI needs real volume: on Binance volume it beats tick volume in most rows")]
    assert got.dev == f"{int((rv.net.to_numpy() > d.loc[tick].net.to_numpy()).sum())}/78"
    assert part.loc[("XAUUSDm", "the VWRSI's trend rule on crypto; it needs real volume"), "verdict"] == "cannot be tested"
    assert {"VWRSI's trend rule beats the RSI on every crypto timeframe (most pairs on each)",
            "VWRSI-RV's trend rule beats the RSI on every crypto timeframe (most pairs on each)"} <= \
        set(cl[cl.symbol == "BTCUSDm"].part)
    assert not any("crypto timeframe" in p for p in cl[cl.symbol == "XAUUSDm"].part)


# ───────────────────────────── real data ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    cache = {}
    closed = tmp_path_factory.mktemp("closed_study")

    def get(symbol, end=None):
        key = (symbol, end)
        if key not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            if symbol == "BTCUSDm" and not all(p.exists() for _, a, _, _, p in TM._binance_files() if a < TM.CUT_S):
                pytest.skip("the Binance files are not on this machine")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end=end)
                cache[key] = (mk, Q.Study(mk))
        return cache[key]
    return get


def _rules(symbol):
    return sorted({v.rule for v in Q.grid(symbol)})


def same(a: dict, b: dict) -> bool:
    """Two dicts of scores are equal, NaN equal to NaN."""
    if a.keys() != b.keys():
        return False
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


@pytest.mark.parametrize("symbol", SYMS)
@pytest.mark.parametrize("T", ["2021-03-01", "2020-11-17 13:37"])
def test_states_up_to_T_do_not_change_when_the_data_after_T_is_removed(symbol, T, real):
    (full, sf), (cut, sc) = real(symbol), real(symbol, end=T)
    T_s = TM.s_of(T)
    assert int(cut.t[-1]) < T_s
    for tf in Q.TFS:
        n = int(np.sum(sc.bars[tf].tc <= T_s))
        assert n > 300
        assert np.array_equal(sf.bars[tf].tc[:n], sc.bars[tf].tc[:n])
        for k in sf.lines[tf]:
            assert np.array_equal(sf.lines[tf][k][:n], sc.lines[tf][k][:n], equal_nan=True), (tf, k)
        assert np.array_equal(sf.stops[tf][:n], sc.stops[tf][:n], equal_nan=True)
    changes = 0
    for rule in _rules(symbol):
        v = Q.Variant(symbol, *rule, "S0")
        n = int(np.sum(sc.bars[v.tf].tc <= T_s))
        a, b = sf.state(v), sc.state(v)
        assert np.array_equal(a[:n], b[:n]), v.vid
        changes += int(np.sum(a[1:n] != a[:n - 1]))
    assert changes > 10_000
    # and the runs up to T of four variants
    for vid in (f"{symbol}|1H|LaRSI|R1|F2-4H|S1", f"{symbol}|4H|QQE|R1|F2-1D|S0", f"{symbol}|1D|MA200|R1|F0|S1",
                f"{symbol}|4H|TSI|CTL-SIGNAL|F0|S1"):
        v = Q.Variant.of(vid)
        stop_f = sf.stops[v.tf] if v.stop == "S1" else None
        stop_c = sc.stops[v.tf] if v.stop == "S1" else None
        rf = TM.run(full, sf.bars[v.tf], sf.state(v), "2019-01-01", T, stop=stop_f, cost=1.5)
        rc = TM.run(cut, sc.bars[v.tf], sc.state(v), "2019-01-01", T, stop=stop_c, cost=1.5)
        assert len(rf.trades) >= 3 and rf.trades.equals(rc.trades), vid
        assert same(Q.scores(rf), Q.scores(rc)), vid


@pytest.mark.parametrize("symbol", SYMS)
def test_f2_on_real_bars_reads_only_the_last_closed_higher_bar(symbol, real):
    mk, st = real(symbol)
    for (tf, f), (up, dn) in st.f2.items():
        lb, hb = st.bars[tf], st.bars[f[3:]]
        hc, hma = hb.c.tolist(), I.ma200(hb.c).tolist()
        htc = hb.tc.tolist()
        k = -1
        exp_up, exp_dn = [], []
        for t in lb.tc.tolist():                                 # a pointer walk, apart from searchsorted
            while k + 1 < len(htc) and htc[k + 1] <= t:
                k += 1
            assert k < 0 or htc[k] <= t
            assert k + 1 == len(htc) or htc[k + 1] > t           # the next higher bar is not closed yet
            exp_up.append(k >= 0 and hc[k] > hma[k])
            exp_dn.append(k >= 0 and hc[k] < hma[k])
        assert np.array_equal(up, np.asarray(exp_up)) and np.array_equal(dn, np.asarray(exp_dn)), (tf, f)
        # changing the higher bars from bar K on changes nothing a signal bar closing before bar K's close reads
        K = len(hb) // 2
        c2 = hb.c.copy()
        c2[K:] = c2[K:] * 1.5 if symbol == "XAUUSDm" else c2[K:] * 0.5
        up2, dn2 = Q.htf_sides(hb, lb, close=c2)
        before = lb.tc < hb.tc[K]
        assert np.array_equal(up2[before], up[before]) and np.array_equal(dn2[before], dn[before])
        assert not np.array_equal(up2[~before], up[~before])         # the change is seen once bar K has closed
        # the 1H bar that closes with its 4H / 1D bar reads that bar
        same_close = np.isin(lb.tc, hb.tc)
        assert same_close.sum() > 100


@pytest.mark.parametrize("symbol", SYMS)
def test_no_missing_value_and_no_exact_tie_on_the_bars_the_windows_read(symbol, real):
    _, st = real(symbol)
    ck = st.checks()
    assert list(ck.tf) == list(Q.TFS)
    assert int(ck.missing_total.sum()) == 0
    assert int(ck.ties_total.sum()) == 0
    first, last = pd.to_datetime(ck.first_bar_close), pd.to_datetime(ck.last_bar_close)
    assert (first > pd.Timestamp("2019-01-01", tz="UTC")).all() and (first < pd.Timestamp("2019-01-08", tz="UTC")).all()
    assert (last <= pd.Timestamp("2024-07-01", tz="UTC")).all() and (last > pd.Timestamp("2024-06-27", tz="UTC")).all()


# ── an independent reading of the rules and of the execution model ──

LEV = {"RSI": (30.0, 70.0), "LaRSI": (20.0, 80.0), "VWRSI": (20.0, 80.0), "VWRSI-RV": (20.0, 80.0), "TSI": (-30.0, 30.0)}


_OWN = {}


def own_lines(mk, tf):
    """The lines, straight from tradeiq_ind (not through tradeiq.lines_of)."""
    key = (id(mk), tf)
    if key not in _OWN:
        _OWN[key] = _own_lines(mk, tf)
    return _OWN[key]


def _own_lines(mk, tf):
    b = mk.tbars(tf)
    c = b.c
    L = {"close": c, "RSI": I.plain_rsi(c), "LaRSI": I.laguerre_rsi(c), "MA200": I.ma200(c)}
    vw = I.vwrsi(c, b.vol)
    L["VWRSI"], L["VWRSI:score"] = vw.rsi, vw.score
    if symbol_is_btc(mk):
        vr = I.vwrsi(c, TM.binance_volume(mk, tf)[0])
        L["VWRSI-RV"], L["VWRSI-RV:score"] = vr.rsi, vr.score
    t = I.bjorgum_tsi(c)
    L["TSI"], L["TSI:signal"] = t.tsi, t.signal
    q = I.qqe_mod(c)
    L["QQE:color"], L["QQE:white"] = q.color, q.white
    return {k: np.asarray(v).tolist() for k, v in L.items()}


def symbol_is_btc(mk):
    return mk.symbol == "BTCUSDm"


_LOOP = {}


def loop_state(mk, v):
    key = (id(mk), v.rule)
    if key not in _LOOP:
        _LOOP[key] = _loop_state(mk, v)
    return _LOOP[key]


def _loop_state(mk, v):
    """PREREG 6 read bar by bar, written apart from tradeiq.py."""
    b = mk.tbars(v.tf)
    L = own_lines(mk, v.tf)
    tcs = b.tc.tolist()
    if v.filt.startswith("F2-"):
        hb = mk.tbars(v.filt[3:])
        h_tc, h_c, h_ma = hb.tc.tolist(), hb.c.tolist(), I.ma200(hb.c).tolist()
    out = []
    held = 0
    k = -1
    nan = float("nan")
    for i in range(len(b)):
        ind, fam = v.indicator, v.family
        if ind == "MA200":
            x, m = L["close"][i], L["MA200"][i]
            r = 1 if x > m else (-1 if x < m else 0)
        elif ind == "QQE" and fam in ("R1", "R2"):
            col = L["QQE:color"][i]
            held = 1 if col == 1 else (-1 if col == -1 else held)
            r = held
        elif ind == "QQE" and fam == "R3":
            r = int(L["QQE:color"][i])
        elif fam == "CTL-WHITE":
            x, xp = L["QQE:white"][i], (L["QQE:white"][i - 1] if i else nan)
            if x > 0 and xp <= 0:
                held = 1
            elif x < 0 and xp >= 0:
                held = -1
            r = held
        elif fam == "CTL-SIGNAL":
            x, s = L["TSI"][i], L["TSI:signal"][i]
            xp, sp = (L["TSI"][i - 1], L["TSI:signal"][i - 1]) if i else (nan, nan)
            if x > s and xp <= sp:
                held = 1
            elif x < s and xp >= sp:
                held = -1
            r = held
        elif fam == "R4":
            lo, hi = LEV[ind]
            x, xp = L[ind][i], (L[ind][i - 1] if i else nan)
            if x > lo and xp <= lo:
                held = 1
            elif x < hi and xp >= hi:
                held = -1
            r = held
        else:
            mid = 0.0 if ind == "TSI" else 50.0
            x = L[ind][i]
            r = 1 if x > mid else (-1 if x < mid else 0)
            if fam == "R3" and not (L[ind + ":score"][i] == 0.0):
                r = 0
        if fam == "R2" and r == -1:
            r = 0
        if v.filt == "F0":
            okl = oks = True
        elif v.filt == "F1":
            okl, oks = L["close"][i] > L["MA200"][i], L["close"][i] < L["MA200"][i]
        elif v.filt == "F3":
            okl, oks = L["TSI"][i] > 0, L["TSI"][i] < 0
        else:
            while k + 1 < len(h_tc) and h_tc[k + 1] <= tcs[i]:
                k += 1
            okl = k >= 0 and h_c[k] > h_ma[k]
            oks = k >= 0 and h_c[k] < h_ma[k]
        out.append(r if (r == 1 and okl) or (r == -1 and oks) else 0)
    return np.asarray(out)


def loop_trades(mk, bars, state, dist, start, end, cost):
    """PREREG 4 with DEVIATIONS 1-4 and 7, one M1 bar at a time (idle stretches skipped): fills at the first M1 open
    at or after a bar's close, a buy at the ask, a sell at the bid; the stop checked at each open (a gap fills at the
    open) and inside each bar (the stop price), one extra spread on a stop fill; what is open at the end closes at the
    last M1 bar's close. Returns (side, entry M1, entry price, exit M1, exit price, reason)."""
    t, o, h, l, c = (x.tolist() for x in (mk.t, mk.o, mk.h, mk.l, mk.c))
    sp = (mk.sp * cost).tolist()
    a_s, z_s = TM.s_of(start), TM.s_of(end)
    ia, iz = bisect.bisect_left(t, a_s), bisect.bisect_left(t, z_s)
    dec = []
    prev = None
    for i, tc in enumerate(bars.tc.tolist()):
        if tc <= a_s:
            continue
        j = bisect.bisect_left(t, tc)
        if j >= iz:
            break
        s = int(state[i])
        dec.append((j, i, s, prev is None or s != prev))
        prev = s
    out = []
    pos, ep, eix, stop = 0, 0.0, -1, None
    di, j = 0, ia
    while True:
        if pos != 0 and stop is not None:                       # a gap through the stop at the open
            if pos == 1 and o[j] <= stop:
                out.append((1, eix, ep, j, o[j] - sp[j], "gap stop"))
                pos = 0
            elif pos == -1 and o[j] + sp[j] >= stop:
                out.append((-1, eix, ep, j, o[j] + sp[j] + sp[j], "gap stop"))
                pos = 0
        while di < len(dec) and dec[di][0] == j:                # the decisions filled at this open
            _, i, s, changed = dec[di]
            di += 1
            if pos == 1 and s != 1:
                out.append((1, eix, ep, j, o[j], "signal"))
                pos = 0
            elif pos == -1 and s != -1:
                out.append((-1, eix, ep, j, o[j] + sp[j], "signal"))
                pos = 0
            if pos == 0 and changed and s != 0:
                pos, eix = s, j
                ep = o[j] + sp[j] if s == 1 else o[j]
                stop = None if dist is None else ep - s * dist[i]
        if pos != 0 and stop is not None:                       # the stop inside the bar
            if pos == 1 and l[j] <= stop:
                out.append((1, eix, ep, j, stop - sp[j], "stop"))
                pos = 0
            elif pos == -1 and h[j] + sp[j] >= stop:
                out.append((-1, eix, ep, j, stop + sp[j], "stop"))
                pos = 0
        if j == iz - 1:
            if pos != 0:
                out.append((pos, eix, ep, j, c[j] if pos == 1 else c[j] + sp[j], "end"))
            break
        if pos != 0 and stop is not None:
            j += 1
        else:
            j = min(dec[di][0], iz - 1) if di < len(dec) else iz - 1
    return out


CASES = [
    "XAUUSDm|1H|LaRSI|R1|F2-4H|S1",       # R1, F2-4H, S1
    "BTCUSDm|1H|RSI|R2|F2-1D|S0",         # R2, F2-1D
    "BTCUSDm|4H|VWRSI-RV|R3|F1|S1",       # R3 on Binance volume, F1, S1
    "XAUUSDm|4H|QQE|R3|F3|S0",            # R3 of the QQE, F3
    "XAUUSDm|1D|TSI|R4|F0|S1",            # R4, S1
    "BTCUSDm|4H|VWRSI|R4|F0|S0",          # R4 on tick volume
    "BTCUSDm|4H|QQE|R1|F2-1D|S1",         # QQE R1 (gray holds), F2-1D, S1
    "BTCUSDm|1D|TSI|CTL-SIGNAL|F0|S0",    # the TSI control
    "XAUUSDm|4H|QQE|CTL-WHITE|F0|S1",     # the QQE control, S1
    "XAUUSDm|1D|MA200|R2|F0|S1",          # MA200 alone, S1
]


def _check_against_loop(mk, st, v, window, cost):
    a, z = TM.window(window, v.symbol)
    dist = (3.0 * I.atr14(st.bars[v.tf].h, st.bars[v.tf].l, st.bars[v.tf].c)).tolist() if v.stop == "S1" else None
    mine = loop_trades(mk, st.bars[v.tf], loop_state(mk, v), dist, a, z, cost)
    r = Q.run_variant(st, v, window, cost)
    tr = r.trades
    assert len(mine) == len(tr) and len(tr) >= 5, (v.vid, window, len(mine), len(tr))
    assert [m[0] for m in mine] == tr.side.tolist()
    assert [m[1] for m in mine] == tr.entry_ix.tolist() and [m[3] for m in mine] == tr.exit_ix.tolist()
    assert [m[5] for m in mine] == tr.reason.tolist()
    assert np.allclose([m[2] for m in mine], tr.entry.to_numpy(), rtol=0, atol=1e-9)
    assert np.allclose([m[4] for m in mine], tr.exit.to_numpy(), rtol=0, atol=1e-8)
    pnl = [mk.k * m[0] * (m[4] - m[2]) for m in mine]
    assert np.allclose(pnl, tr.pnl.to_numpy(), rtol=0, atol=1e-8)
    assert abs(sum(pnl) - r.net) < 1e-6
    return r, mine


@pytest.mark.parametrize("vid", CASES)
def test_trades_rederived_by_an_independent_loop(vid, real):
    v = Q.Variant.of(vid)
    mk, st = real(v.symbol)
    assert np.array_equal(loop_state(mk, v), st.state(v)), vid           # the states, on every bar
    _check_against_loop(mk, st, v, "dev", 1.0)
    _check_against_loop(mk, st, v, "val", 1.5)


@pytest.mark.parametrize("symbol", SYMS)
def test_every_state_series_of_the_grid_rederived_by_the_independent_loop(symbol, real):
    """All 168 (gold) / 207 (BTC) state series of the grid, bar for bar, against the separate bar-by-bar reading."""
    mk, st = real(symbol)
    rules = _rules(symbol)
    assert len(rules) == {"XAUUSDm": 168, "BTCUSDm": 207}[symbol]
    for rule in rules:
        v = Q.Variant(symbol, *rule, "S0")
        assert np.array_equal(loop_state(mk, v), st.state(v)), v.vid


def test_the_s1_cases_exercise_stops_inside_a_bar_and_gap_stops(real):
    """The re-derived cases include both kinds of stop fill (so the loop's stop branches were compared)."""
    n = {"stop": 0, "gap stop": 0}
    for vid in CASES:
        v = Q.Variant.of(vid)
        if v.stop != "S1":
            continue
        mk, st = real(v.symbol)
        for window, cost in (("dev", 1.0), ("val", 1.5)):
            rs = Q.run_variant(st, v, window, cost).trades.reason
            for k in n:
                n[k] += int((rs == k).sum())
    assert n["stop"] >= 20 and n["gap stop"] >= 1, n


def test_the_cases_cover_every_family_both_symbols_f1_f2_f3_and_s1():
    vs = [Q.Variant.of(x) for x in CASES]
    assert {v.family for v in vs} == {"R1", "R2", "R3", "R4", "CTL-SIGNAL", "CTL-WHITE"}
    assert {v.symbol for v in vs} == set(SYMS) and {v.tf for v in vs} == set(Q.TFS)
    assert {"F1", "F2-4H", "F2-1D", "F3"} <= {v.filt for v in vs} and {v.stop for v in vs} == {"S0", "S1"}
    assert {"MA200", "VWRSI-RV", "QQE", "TSI", "LaRSI", "RSI", "VWRSI"} <= {v.indicator for v in vs}
    assert all(x in {v.vid for s in SYMS for v in Q.grid(s)} for x in CASES)


def _written(name):
    p = Q.STUDY_DIR / name
    if not p.exists():
        pytest.skip(f"{name} has not been written yet")
    return p


@pytest.mark.parametrize("vid", CASES)
def test_the_written_trades_and_scores_are_these(vid, real):
    """The study's CSVs hold exactly the trades and scores the independent loop gives (when they exist)."""
    p_tr, p_res = _written("trades_dev_val.csv.gz"), _written("results_dev_val.csv")
    v = Q.Variant.of(vid)
    mk, st = real(v.symbol)
    res = pd.read_csv(p_res, float_precision="round_trip").set_index(["vid", "window"])
    tr = pd.read_csv(p_tr, float_precision="round_trip")
    tr = tr[tr.vid == vid]
    for window, cost in (("dev", 1.0), ("val", 1.0), ("dev", 1.5), ("val", 1.5)):
        a, z = TM.window(window, v.symbol)
        dist = (3.0 * I.atr14(st.bars[v.tf].h, st.bars[v.tf].l, st.bars[v.tf].c)).tolist() if v.stop == "S1" else None
        mine = loop_trades(mk, st.bars[v.tf], loop_state(mk, v), dist, a, z, cost)
        w = tr[(tr.window == window) & (tr.cost == cost)]
        assert len(w) == len(mine), (vid, window, cost)
        et = [str(TM.utc(mk.t[m[1]])) for m in mine]
        assert [str(pd.Timestamp(x)) for x in w.entry_time] == et
        assert w.side.tolist() == [m[0] for m in mine] and w.reason.tolist() == [m[5] for m in mine]
        assert np.allclose(w.entry.to_numpy(), [m[2] for m in mine], rtol=0, atol=1e-9)
        assert np.allclose(w.exit.to_numpy(), [m[4] for m in mine], rtol=0, atol=1e-8)
        net = sum(mk.k * m[0] * (m[4] - m[2]) for m in mine)
        col = "net" if cost == 1.0 else "net_x15"
        assert abs(res.loc[(vid, window), col] - net) < 1e-6
        assert res.loc[(vid, window), "trades" if cost == 1.0 else "trades_x15"] == len(mine)


def test_the_written_results_are_the_grid():
    res = pd.read_csv(_written("results_dev_val.csv"), float_precision="round_trip")
    want = [v.vid for s in SYMS for v in Q.grid(s)]
    assert len(res) == 3 * 750
    for w in Q.RUN_WINDOWS:
        assert res[res.window == w].vid.tolist() == want
    q = Q.STUDY_DIR / "qualification.csv"
    if q.exists():
        qq = pd.read_csv(q)
        assert qq.vid.tolist() == want
        # Before the exam FINALISTS.md must not exist; after it (the study is finished) the frozen list must still
        # match the sha256 recorded when it was frozen.
        fin = Q.STUDY_DIR / "FINALISTS.md"
        if fin.exists():
            import hashlib
            frozen = (Q.STUDY_DIR / "FINALISTS.md.sha256").read_text(encoding="utf-8").split()[0]
            assert hashlib.sha256(fin.read_bytes()).hexdigest() == frozen


SELECT_FILES = ("qualification.csv", "vs_rsi.csv", "vs_rsi_summary.csv", "multiple_testing.csv", "vs_buy_and_hold.csv",
                "exam_rule_rates.csv", "runners_up.csv", "curves.csv", "vs_f0.csv", "vs_f0_summary.csv", "claims.csv")


def test_select_reproduces_the_written_selection(tmp_path):
    """``select`` on a copy of ``run``'s CSVs writes every selection file byte for byte as the study folder holds it,
    and CANDIDATES.md but for the line with its time stamp (so none of them is stale)."""
    for f in ("results_dev_val.csv", "weekly_dev_val.csv.gz", "buy_and_hold.csv", "state_checks.csv", "run_info.csv"):
        (tmp_path / f).write_bytes(_written(f).read_bytes())
    for f in SELECT_FILES + ("CANDIDATES.md",):
        _written(f)
    Q.select(tmp_path, log=lambda *a: None)
    for f in SELECT_FILES:
        assert (tmp_path / f).read_bytes() == (Q.STUDY_DIR / f).read_bytes(), f
    a = (tmp_path / "CANDIDATES.md").read_text(encoding="utf-8").splitlines()
    b = (Q.STUDY_DIR / "CANDIDATES.md").read_text(encoding="utf-8").splitlines()
    assert a[2].startswith("Written by") and b[2].startswith("Written by")
    assert len(a) == len(b) and a[:2] == b[:2] and a[3:] == b[3:]


def test_the_written_files_agree_with_each_other():
    """For every variant, window and cost: the trades, the quarters and the weeks add up to the net of the results;
    the trade counts and the positive quarters are the results'."""
    res = pd.read_csv(_written("results_dev_val.csv"), float_precision="round_trip")
    tr = pd.read_csv(_written("trades_dev_val.csv.gz"), usecols=["vid", "window", "cost", "pnl"],
                     float_precision="round_trip")
    qt = pd.read_csv(_written("quarters_dev_val.csv"), float_precision="round_trip")
    wk = pd.read_csv(_written("weekly_dev_val.csv.gz"), float_precision="round_trip")
    r = res[res.window.isin(["dev", "val"])].set_index(["vid", "window"])
    assert len(r) == 2 * 750
    for cost, sfx in ((1.0, ""), (1.5, "_x15")):
        g = tr[tr.cost == cost].groupby(["vid", "window"]).pnl.agg(["sum", "count"]).reindex(r.index, fill_value=0)
        assert np.allclose(g["sum"], r["net" + sfx], rtol=0, atol=1e-6)
        assert np.array_equal(g["count"].to_numpy(), r["trades" + sfx].to_numpy())
        col = "pnl" if cost == 1.0 else "pnl_x15"
        q = qt.groupby(["vid", "window"])[col].agg(["sum", lambda x: int((x > 0).sum()), "count"]).reindex(r.index)
        assert np.allclose(q["sum"], r["net" + sfx], rtol=0, atol=1e-6)
        assert np.array_equal(q.iloc[:, 1].to_numpy(), r["pos_q" + sfx].to_numpy())
        assert np.array_equal(q["count"].to_numpy(), r["n_q" + sfx].to_numpy())
        w = wk.groupby(["vid", "window"])[col].agg(["sum", "count"]).reindex(r.index)
        assert np.allclose(w["sum"], r["net" + sfx], rtol=0, atol=1e-6)
        assert np.array_equal(w["count"].to_numpy(), r["weeks" + sfx].to_numpy())
    assert set(qt.groupby("window").quarter.nunique()) == {16, 6}
