"""
The hold-out tables: grouping settings by how they did on the analysed quarters, and
reading the two hold-out quarters for each group. Checked on a small hand-made grid whose
answers can be worked out on paper.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.analysis import holdout as H

SYM = "XAUUSDm"


def _row(open_, fc, nets, dips, baskets=100):
    """nets / dips in the order IS, OOS1, OOS2, HO2, HO1."""
    r = {"open": open_, "fc": fc, "entry": "loose", "fc_level": "half"}
    for w, n, d in zip(["IS", "OOS1", "OOS2", "HO2", "HO1"], nets, dips):
        r[f"net_profit@{w}"] = n
        r[f"max_loss_from_start@{w}"] = d
        r[f"baskets@{w}"] = baskets
        r[f"largest_loss@{w}"] = -d / 2
    return r


ROWS = [
    #                 IS   OOS1  OOS2   HO2   HO1           dips
    _row("H1+M15", "M15", [10, 20, 30, 5, 5], [100, 100, 100, 100, 100]),      # 3/3 clean -> both hold-out quarters up
    _row("H4+M15", "M15", [10, 20, 30, -50, 5], [100, 100, 100, 2500, 100]),   # 3/3 clean -> one up, wiped in the other
    _row("M5", "M15", [10, 20, 30, 1, 1], [100, 2000, 100, 100, 100]),         # 3/3 but $2,000 down once
    _row("M1", "M15", [10, 20, -30, -1, -1], [100, 100, 100, 100, 100]),       # 2/3
    _row("M1", "M5", [-10, -20, -30, 40, 40], [100, 100, 100, 100, 100]),      # 0/3 -> does best on the hold-out
]


@pytest.fixture
def results(tmp_path):
    df = pd.DataFrame(ROWS)
    d = tmp_path / "sweeps"
    d.mkdir()
    key = H.KEY
    a = [c for c in df.columns if c in key or c.split("@")[-1] in H.ANALYSED]
    h = [c for c in df.columns if c in key or c.split("@")[-1] in H.HELD_OUT]
    df[a].to_csv(d / f"{SYM}_timeframes.csv", index=False)
    df[h].to_csv(d / f"{SYM}_timeframes_holdout.csv", index=False)
    return tmp_path


def test_nothing_without_the_holdout_sweep(tmp_path):
    assert H.merged_timeframes(tmp_path, SYM) is None
    assert H.timeframe_carry_over(tmp_path, SYM) is None
    assert H.candidate_table(tmp_path, SYM) is None


def test_groups_are_formed_on_the_analysed_quarters_only(results):
    tab, facts = H.timeframe_carry_over(results, SYM)
    g = tab.set_index("group")
    clean = g.loc["3 of 3 profitable, never $2,000 down"]
    assert clean["settings"] == 2
    assert clean["both_holdout_profitable_pct"] == 50.0          # one of the two
    assert clean["one_or_more_pct"] == 100.0
    assert clean["wiped_in_holdout_pct"] == 50.0
    assert clean["mean_holdout_net_per_quarter"] == pytest.approx((10 + -45) / 2 / 2)
    assert g.loc["3 of 3 profitable, but $2,000 down at some point", "settings"] == 1
    assert g.loc["2 of 3 profitable", "settings"] == 1
    assert g.loc["0 of 3 profitable", "both_holdout_profitable_pct"] == 100.0
    assert "1 of 3 profitable" not in g.index                    # empty groups are left out
    assert facts["settings"] == 5
    assert facts["base_both_profitable_pct"] == pytest.approx(60.0)
    assert facts["base_wiped_pct"] == pytest.approx(20.0)
    assert -1.0 <= facts["rank_correlation"] <= 1.0
    # the setting that lost in every analysed quarter did best on the hold-out: ranking does not carry over here
    assert facts["rank_correlation"] < 0


def test_a_hold_out_result_never_changes_the_grouping(results):
    """Changing only hold-out numbers must leave every setting in the same group."""
    before = H.timeframe_carry_over(results, SYM)[0].set_index("group")["settings"]
    p = results / "sweeps" / f"{SYM}_timeframes_holdout.csv"
    h = pd.read_csv(p)
    for c in h.columns:
        if c.startswith("net_profit@"):
            h[c] = -h[c] * 7
        if c.startswith("max_loss_from_start@"):
            h[c] = 5000.0
    h.to_csv(p, index=False)
    after = H.timeframe_carry_over(results, SYM)[0].set_index("group")["settings"]
    assert before.to_dict() == after.to_dict()


def test_best_survivors_are_ranked_without_looking_at_the_hold_out(results):
    best = H.best_survivors(results, SYM, 3)
    # never wiped on the analysed quarters first, then most profitable quarters, then the best worst quarter
    assert set(best["open"].iloc[:2]) == {"H1+M15", "H4+M15"}
    assert (best["a_ruin"].iloc[:2] == 0).all() and (best["a_pos"].iloc[:2] == 3).all()


def test_candidate_table_and_pages(results, live_cfg):
    d = results / "candidates"
    d.mkdir()
    rows = []
    for name, tf, lad, nets, dips in (
            ("live timeframes · live ladder", "live timeframes", "live ladder", [1, -2, 3, -4, 5], [10, 2500, 10, 10, 10]),
            ("A: slow - open H4 · no ladder", "A: slow - open H4", "no ladder", [1, 2, 3, 4, 5], [10, 20, 30, 40, 50])):
        r = {"candidate": name, "timeframes": tf, "ladder": lad}
        for w, n, dd in zip(["IS", "OOS1", "OOS2", "HO2", "HO1"], nets, dips):
            r[f"net_profit@{w}"], r[f"max_loss_from_start@{w}"] = n, dd
            r[f"largest_loss@{w}"], r[f"baskets@{w}"] = -dd, 100
        rows.append(r)
    pd.DataFrame(rows).to_csv(d / f"{SYM}.csv", index=False)
    pd.DataFrame({"candidate": [r["candidate"] for r in rows], "net_profit": [-2000.0, 150.0], "max_dd_pct": [100.0, 12.0],
                  "stopped_out": [True, False], "max_lots": [0.32, 0.01]}).to_csv(d / f"{SYM}_account.csv", index=False)

    t = H.candidate_table(results, SYM).set_index("candidate")
    live, a = t.loc["live timeframes · live ladder"], t.loc["A: slow - open H4 · no ladder"]
    assert live["quarters_profitable"] == 3 and live["quarters"] == 5
    assert live["analysed_total"] == 2 and live["holdout_total"] == 1          # 1-2+3 and -4+5
    assert live["deepest_dip"] == 2500 and live["worst_basket"] == -2500
    assert bool(live["account_stopped_out"]) and not bool(a["account_stopped_out"])
    assert a["quarters_profitable"] == 5 and a["deepest_dip"] == 50

    # the page and the write-up render both sections from these files
    from backtesting.viz import index as I, markdown as M
    cfg = live_cfg(SYM)
    html_ho, html_cd = I.section_holdout(results, SYM, cfg), I.section_candidates(results, SYM)
    assert "hold-out" in html_ho and "plotly" in html_ho.lower()
    labels = html_cd.replace("\\u00b7", "·")                                 # plotly escapes non-ASCII inside its JSON
    assert "A · no ladder" in labels and "Live · live ladder" in labels and "YES" in html_cd
    md_ho, md_cd = M.sec_holdout(results, SYM), M.sec_candidates(results, SYM)
    assert "3 of 3 profitable, never $2,000 down" in md_ho and "Rank correlation" in md_ho
    assert "**yes**" in md_cd and "5/5" in md_cd


def test_vote_study_describes_the_live_votes(fixture_store, windows, live_root):
    """The signal study uses the live indicator functions; its shares are consistent and reproducible."""
    from backtesting.analysis import signal as S

    a, z = windows["BTCUSDm"]
    r = S.vote_study("BTCUSDm", a, z, live_root=live_root, tfs=("M1",), horizons=(1, 4), store_dir=fixture_store)
    m = r["M1"]
    assert m["bars"] >= 55
    mv, rv = m["macd_vote"], m["rsi_vote"]
    assert mv["against_signal_line_trend_pct"] + mv["with_signal_line_trend_pct"] + mv["grey_pct"] == pytest.approx(100.0, abs=0.2)
    assert rv["up_pct"] + rv["down_pct"] + rv["grey_pct"] == pytest.approx(100.0, abs=0.2)
    assert m["both_up_share_pct"] <= min(rv["up_pct"], 100.0) + 1e-9
    h = m["after"]["4_bars"]
    assert h["all_bars"]["n"] == m["bars"] - 4 and h["both_up"]["n"] <= h["all_bars"]["n"]
    assert r == S.vote_study("BTCUSDm", a, z, live_root=live_root, tfs=("M1",), horizons=(1, 4), store_dir=fixture_store)

    # one bar checked by hand against the live function on the full series
    import numpy as np
    from backtesting.config import TF_SECONDS, load_live_constants
    from backtesting.data import store
    c = load_live_constants(live_root)
    ind = S.live_indicator(live_root)
    m1 = store.load_m1("BTCUSDm", store.to_ms(a) - 3 * 3600 * 1000, store.to_ms(z), fixture_store)
    close = pd.Series(np.asarray(store.resample_bars(m1, TF_SECONDS["M1"])["c"], float))
    i = len(close) - 7
    v = S.votes(close, live_root, first=i).iloc[0]
    macd = ind.calculate_macd(close.iloc[: i + 1], fast=c.MACD_FAST, slow=c.MACD_SLOW, signal=c.MACD_SIGNAL)
    sig = float(macd["signal"].iloc[-1])
    full = ind.latest_pivot_slope(macd["hist"], lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH,
                                  side="high" if sig > 0 else ("low" if sig < 0 else None))
    assert v["macd"] == full["sign"]
    rsi = ind.calculate_rsi(close.iloc[: i + 1], c.RSI_LENGTH)
    assert v["rsi"] == ind.latest_pivot_slope(rsi, lookback=c.PEAK_LOOKBACK, width=c.PIVOT_WIDTH,
                                              ob_level=c.RSI_PEAK_OB, os_level=c.RSI_PEAK_OS)["sign"]


def test_timing_ensemble_runs_every_window_under_every_timing(fixture_store, live_cfg, engine_run):
    """Eight timings per window on raw ticks; the first one is the plain live cadence."""
    from backtesting.analysis import robustness as R

    cfg = live_cfg("BTCUSDm")
    wins = {"a": ("2026-11-09 06:00", "2026-11-09 06:30"), "b": ("2026-11-09 06:30", "2026-11-09 07:00")}
    df = R.timing_ensemble(cfg, wins, n_jobs=1, store_dir=str(fixture_store))
    assert len(df) == 16 and set(df["window"]) == {"a", "b"}
    assert sorted(set(zip(df["poll_ms"], df["phase_ms"]))) == [(p, ph) for p in (1000, 1250) for ph in (0, 250, 500, 750)]
    # (1000 ms, phase 0) is exactly a raw-tick run of that window with the live 0.1 s post-order sleep
    from backtesting.engine import fast
    c = live_cfg("BTCUSDm", start=wins["b"][0], end=wins["b"][1], open_order_delay_ms=100)
    plain = fast.run(c, fast.prepare(c.symbol, c.start, c.end, c.timeframes(), mode="ticks", store_dir=fixture_store))
    first = df[(df["window"] == "b") & (df["poll_ms"] == 1000) & (df["phase_ms"] == 0)].iloc[0]
    assert first["net_profit"] == pytest.approx(plain.scalars["final_equity"] - cfg.initial_balance, abs=0.006)
    assert first["baskets"] == len(plain.baskets)

    s = R.ensemble_summary(df).set_index("window")
    assert list(s.index) == ["a", "b"] and (s["runs"] == 8).all()
    for w in ("a", "b"):
        g = df[df["window"] == w]["net_profit"]
        assert s.loc[w, "net_min"] == g.min() and s.loc[w, "net_max"] == g.max() and s.loc[w, "net_median"] == g.median()
        assert s.loc[w, "losing_runs"] == int((g < 0).sum())


def test_candidate_ensemble_summarises_quarter_runs(tmp_path, live_cfg):
    """With the timing file present the candidate table carries the spread over all quarter-runs."""
    d = tmp_path / "candidates"
    d.mkdir()
    wins = ["HO1", "HO2", "OOS2", "OOS1", "IS"]
    base, timing = [], []
    for cand, tf, lad, shift in (("live timeframes · live ladder", "live timeframes", "live ladder", -30.0),
                                 ("A: slow - open H4 · no ladder", "A: slow - open H4", "no ladder", +5.0)):
        r = {"candidate": cand, "timeframes": tf, "ladder": lad}
        for w in wins:
            r[f"net_profit@{w}"], r[f"max_loss_from_start@{w}"], r[f"largest_loss@{w}"], r[f"baskets@{w}"] = 1.0, 10.0, -5.0, 100
        base.append(r)
        for wi, w in enumerate(wins):
            for k in range(8):                                   # eight timings: -3.5 .. +3.5 around the shift
                net = shift + (k - 3.5) + wi
                timing.append({"candidate": cand, "timeframes": tf, "ladder": lad, "window": w, "segment": w, "poll_ms": 1000,
                               "phase_ms": k, "net_profit": net, "max_dd_pct": 10.0, "baskets": 50 + k, "largest_loss": -abs(net) - 1,
                               "max_lots": 0.32, "stopped_out": cand.startswith("live") and w == "HO1" and k < 2})
    pd.DataFrame(base).to_csv(d / f"{SYM}.csv", index=False)
    pd.DataFrame(timing).to_csv(d / f"{SYM}_timing.csv", index=False)

    t = H.candidate_table(tmp_path, SYM).set_index("candidate")
    live, a = t.loc["live timeframes · live ladder"], t.loc["A: slow - open H4 · no ladder"]
    assert live["ens_runs"] == 40 and a["ens_runs"] == 40
    assert live["ens_losing_runs"] == 40 and live["ens_stopped_runs"] == 2 and live["ens_stopped@HO1"] == 2
    assert live["ens_median@IS"] == pytest.approx(-30.0 + 4)            # the eight offsets are symmetric around the shift
    assert a["ens_median@HO1"] == pytest.approx(5.0) and a["ens_stopped_runs"] == 0
    assert a["ens_worst_run"] == pytest.approx(5.0 - 3.5) and a["ens_losing_runs"] == 0
    assert a["ens_min@OOS1"] == pytest.approx(5.0 - 3.5 + 3) and a["ens_max@OOS1"] == pytest.approx(5.0 + 3.5 + 3)

    from backtesting.viz import index as I, markdown as M
    html_cd, md_cd = I.section_candidates(tmp_path, SYM), M.sec_candidates(tmp_path, SYM)
    assert "40 of 40" in html_cd and "2 of 40" in html_cd and "0 of 40" in html_cd
    assert "40 of 40" in md_cd and "✕" in md_cd and "Quarter-runs that lost" in md_cd
