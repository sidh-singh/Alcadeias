"""
Tests for the experimental levers added on top of the live rules, the broker close-only
window, the flaw diagnostics, and the report / sweep / robustness plumbing.

Every lever is OFF by default, so none of this changes what a default run does (that is
what test_parity.py protects). These tests check that each lever does what its name
says when it is switched on, on real fixture ticks.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.analysis import diagnostics, robustness, sweep
from backtesting.config import BacktestConfig
from backtesting.data import store
from backtesting.engine import fast

# the hedging exit, stated explicitly so these tests mean the same on a netting branch
HEDGING_EXIT = dict(target_usd_per_unit=1.0, book_enabled=False)


def _fills_per_basket(res):
    f = res.fills[res.fills["action"].isin(["open", "add"])].sort_values(["basket", "time"])
    return f.assign(dt=f.groupby("basket")["time"].diff().dt.total_seconds())


# ───────────────────────────── ladder spacing ─────────────────────────────

def test_default_ladder_fires_tiers_seconds_apart(live_cfg, engine_run):
    """The live ladder has no spacing: on the BTC fixture some adds follow the previous fill within 3 s.
    (This is the behaviour the spacing levers exist to change; if it stops being true the fixture changed.)"""
    res = engine_run(live_cfg("BTCUSDm", **HEDGING_EXIT), mode="sec")
    f = _fills_per_basket(res)
    adds = f[f["action"] == "add"]
    assert len(adds) >= 3
    assert (adds["dt"] <= 3.0).any()


@pytest.mark.parametrize("interval", [30.0, 120.0])
def test_ladder_min_interval_spaces_adds(live_cfg, engine_run, interval):
    res = engine_run(live_cfg("BTCUSDm", ladder_min_interval_s=interval, **HEDGING_EXIT), mode="sec")
    f = _fills_per_basket(res)
    adds = f[f["action"] == "add"]
    assert len(adds) > 0, "the lever must space adds out, not remove them"
    assert (adds["dt"] >= interval - 1e-9).all()
    assert res.counters["polls_ladder_blocked_spacing"] > 0


def test_ladder_min_gap_requires_adverse_price_move(live_cfg, engine_run):
    gap = 30.0   # USD of BTC price
    res = engine_run(live_cfg("BTCUSDm", ladder_min_gap=gap, **HEDGING_EXIT), mode="sec")
    f = res.fills[res.fills["action"].isin(["open", "add"])].sort_values(["basket", "time"])
    for _, g in f.groupby("basket"):
        px = g["price"].to_numpy()
        ask = g["ask"].to_numpy()
        bid = g["bid"].to_numpy()
        side = g["side"].iloc[0]
        for i in range(1, len(g)):
            if side == "BUY":   # the add is only allowed once the ask is `gap` below the last fill
                assert px[i - 1] - ask[i] >= gap - 1e-9
            else:
                assert bid[i] - px[i - 1] >= gap - 1e-9


def test_max_adds_caps_the_ladder(live_cfg, engine_run):
    for cap in (0, 1, 2):
        res = engine_run(live_cfg("BTCUSDm", max_adds=cap, **HEDGING_EXIT), mode="sec")
        assert res.baskets["n_pos"].max() <= cap + 1
        if cap == 0:
            assert (res.fills["action"] != "add").all()


def test_flat_ladder_multipliers(live_cfg, engine_run):
    res = engine_run(live_cfg("BTCUSDm", ladder_multipliers=[1] * 12, fixed_units=1, **HEDGING_EXIT), mode="sec")
    lots = res.fills.loc[res.fills["action"].isin(["open", "add"]), "lots"]
    assert np.allclose(lots, 0.01)


# ───────────────────────────── exits ─────────────────────────────

def test_time_stop_closes_long_running_baskets(live_cfg, engine_run):
    hold = 120.0
    res = engine_run(live_cfg("BTCUSDm", max_hold_s=hold, **HEDGING_EXIT), mode="sec")
    b = res.baskets
    assert (b["reason"] == "time_stop").any()
    ts = b[b["reason"] == "time_stop"]
    assert (ts["duration_s"] >= hold).all()
    # nothing outlives the stop by more than a couple of polls (an add delays the next poll by 1 s)
    assert b["duration_s"].max() <= hold + 5.0
    assert res.counters["closes_time_stop"] == len(ts)


def test_target_per_lot_scales_the_target_with_basket_size(live_cfg, engine_run):
    cfg = live_cfg("BTCUSDm", target_per_lot=True, fixed_units=1, **HEDGING_EXIT)
    res = engine_run(cfg, mode="sec")
    tgt = res.baskets[res.baskets["reason"] == "target"]
    assert len(tgt) > 0
    lot_units = tgt["lots"] / cfg.mtqty
    assert (tgt["profit_seen"] > cfg.target_usd_per_unit * lot_units - 1e-9).all()
    # live rule for comparison: the whole basket closes at $1 x unit whatever its size
    live = engine_run(live_cfg("BTCUSDm", fixed_units=1, **HEDGING_EXIT), mode="sec")
    lt = live.baskets[(live.baskets["reason"] == "target") & (live.baskets["n_pos"] > 1)]
    if len(lt):
        assert (lt["profit_seen"] < cfg.target_usd_per_unit * lt["lots"] / cfg.mtqty).any()


def test_stop_loss_bounds_the_seen_loss(live_cfg, engine_run):
    sl = 3.0
    res = engine_run(live_cfg("BTCUSDm", stop_loss_usd_per_unit=sl, fixed_units=1, **HEDGING_EXIT), mode="sec")
    st = res.baskets[res.baskets["reason"] == "stop_loss"]
    assert len(st) > 0
    assert (st["profit_seen"] <= -sl + 1e-9).all()


# ───────────────────────────── broker close-only window ─────────────────────────────

def _gapped_store(tmp_path: Path, fixture_store: Path, symbol: str, cut_ms: int, shift_ms: int) -> Path:
    """Copy the fixture store and push every tick at/after `cut_ms` later by `shift_ms` (a session break)."""
    dst = tmp_path / f"gap_{cut_ms}"
    shutil.copytree(fixture_store / symbol, dst / symbol)
    for month in (dst / symbol).iterdir():
        for kind in ("ticks", "sec"):
            p = month / f"{kind}.npz"
            with np.load(p) as z:
                d = {k: z[k] for k in z.files}
            if len(d["t_ms"]) == 0:
                continue
            t = d["t_ms"].astype(np.int64)
            t[t >= cut_ms] += shift_ms
            d["t_ms"] = t
            np.savez_compressed(p, **d)
    return dst


def test_close_only_window_blocks_new_orders_after_a_break(tmp_path, fixture_store, live_cfg, windows):
    """After a >= 30 min gap in the ticks the broker refuses opens/adds for a while; closes still go through."""
    symbol = "BTCUSDm"
    a, z = windows[symbol]
    a_ms, z_ms = store.to_ms(a), store.to_ms(z)
    shift = 45 * 60 * 1000          # a 45-minute break
    block = 600.0
    found = False
    for frac in (0.25, 0.35, 0.45, 0.55, 0.65):
        cut = a_ms + int((z_ms - a_ms) * frac)
        gs = _gapped_store(tmp_path, fixture_store, symbol, cut, shift)
        end = store.ms_to_dt(z_ms + shift).tz_localize(None)
        base = live_cfg(symbol, end=str(end), window_enabled=False, **HEDGING_EXIT)
        prep = fast.prepare(symbol, base.start, base.end, base.timeframes(), mode="sec", store_dir=gs)
        free = fast.run(base.replace(close_only_after_break_s=0.0, close_only_after_weekend_s=0.0), prep)
        held = fast.run(base.replace(close_only_after_break_s=block), prep)
        reopen = pd.Timestamp(int(prep.t_ms[np.searchsorted(prep.t_ms, cut + shift)]), unit="ms", tz="UTC")
        lo, hi = reopen, reopen + pd.Timedelta(seconds=block)

        def new_orders(res):
            f = res.fills
            return f[(f["action"].isin(["open", "add"])) & (f["time"] >= lo) & (f["time"] < hi)]

        # identical up to the break
        pre = lambda res: res.fills[res.fills["time"] < lo][["time", "action", "lots", "price"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(pre(free), pre(held))
        assert len(new_orders(held)) == 0
        if len(new_orders(free)) > 0:
            assert held.counters["polls_order_blocked_close_only"] > 0
            found = True
            break
    assert found, "no cut produced an order right after the break; widen the search"


def test_close_only_is_inert_without_breaks(live_cfg, engine_run):
    """The fixture windows have no session break, so the close-only setting must not change anything."""
    a = engine_run(live_cfg("XAUUSDm"), mode="sec")
    b = engine_run(live_cfg("XAUUSDm", close_only_after_break_s=0.0, close_only_after_weekend_s=0.0), mode="sec")
    pd.testing.assert_frame_equal(a.fills, b.fills)
    assert a.counters["polls_order_blocked_close_only"] == 0


# ───────────────────────────── diagnostics ─────────────────────────────

def test_diagnostics_agree_with_the_trade_tables(live_cfg, engine_run):
    res = engine_run(live_cfg("BTCUSDm", **HEDGING_EXIT), mode="sec")
    d = diagnostics.diagnose(res)
    b = res.baskets
    assert d["payoff"]["baskets"] == len(b)
    assert d["payoff"]["win_rate_pct"] == pytest.approx((b["pnl"] > 0).mean() * 100)
    assert d["ladder"]["adds"] == res.counters["ladder_adds"] == int((res.fills["action"] == "add").sum())
    assert d["ladder"]["net_without_adds"] + d["ladder"]["net_with_adds"] == pytest.approx(b["pnl"].sum())
    assert sum(r["baskets"] for r in d["exits"]["by_reason"]) == len(b)
    assert sum(r["net"] for r in d["exits"]["by_reason"]) == pytest.approx(b["pnl"].sum())
    # spread paid = sum over entries of (ask - bid) x lots x contract size
    opens = res.fills[res.fills["action"].isin(["open", "add"])]
    expect = ((opens["ask"] - opens["bid"]) * opens["lots"] * res.cfg.spec.contract_size).sum()
    assert d["costs"]["spread_paid"] == pytest.approx(expect)
    assert d["costs"]["net_before_spread"] == pytest.approx(b["pnl"].sum() + expect)
    for f in diagnostics.findings(res):
        assert f["title"] and f["detail"]


def test_diagnostics_handle_an_empty_run(live_cfg, engine_run):
    res = engine_run(live_cfg("XAUUSDm", allow_long=False, allow_short=False), mode="sec")
    assert len(res.baskets) == 0
    d = diagnostics.diagnose(res)
    assert d["payoff"] == {} and diagnostics.findings(res) == []


# ───────────────────────────── reports ─────────────────────────────

def test_report_is_written_with_parseable_tables(tmp_path, fixture_store, live_cfg, engine_run):
    from backtesting.viz.report import build_report

    res = engine_run(live_cfg("BTCUSDm", **HEDGING_EXIT), mode="sec")
    out = tmp_path / "run"
    path = build_report(res, out, closeups=False, store_dir=fixture_store, plotly_src="plotly.min.js")
    html = path.read_text(encoding="utf-8")
    assert "Market, trades and account" in html and "plotly-graph-div" in html
    for name in ("baskets.csv", "fills.csv", "equity.csv.gz", "summary.json", "diagnostics.json"):
        assert (out / name).exists(), name
    # one timestamp format, so a plain parse works
    f = pd.read_csv(out / "fills.csv")
    t = pd.to_datetime(f["time"], format="%Y-%m-%d %H:%M:%S.%f")
    assert t.is_monotonic_increasing
    b = pd.read_csv(out / "baskets.csv")
    assert len(b) == len(res.baskets)
    assert b["pnl"].sum() == pytest.approx(res.baskets["pnl"].sum())
    s = json.loads((out / "summary.json").read_text())
    assert s["summary"]["baskets"] == len(res.baskets)
    assert BacktestConfig.from_dict(s["config"]).key() == res.cfg.key()


def test_closeup_figure_builds_for_a_basket(fixture_store, live_cfg, engine_run):
    from backtesting.viz.report import closeup_figure

    res = engine_run(live_cfg("BTCUSDm", **HEDGING_EXIT), mode="sec")
    worst = int(res.baskets.loc[res.baskets["pnl"].idxmin(), "basket"])
    fig = closeup_figure(res, worst, store_dir=fixture_store)
    assert fig is not None and len(fig.data) >= 3


# ───────────────────────────── sweeps / robustness / experiment grids ─────────────────────────────

def test_run_grid_returns_one_row_per_configuration(fixture_store, live_cfg):
    base = live_cfg("XAUUSDm", fixed_units=1)
    grid = [dict(max_adds=0), dict(max_adds=2), dict(entry_s=4.0)]
    df = sweep.run_grid(base, grid, n_jobs=1, labels=[dict(name=f"c{i}") for i in range(3)],
                        store_dir=str(fixture_store))
    assert list(df["name"]) == ["c0", "c1", "c2"]
    for col in ("net_profit", "max_dd_usd", "baskets", "max_loss_from_start"):
        assert col in df.columns
    assert df.loc[0, "ladder_adds"] == 0


def test_timeframe_grids_build_valid_configurations(live_cfg):
    base = live_cfg("XAUUSDm")
    universe = ["M5", "M15", "H1"]
    for grid, labels in (sweep.grid_joint_timeframes(universe, base.variant),
                         sweep.grid_split_indicator(universe, base.variant),
                         sweep.grid_split_exit(universe, base.variant, "fc")):
        assert len(grid) == len(labels) > 0
        for ov in grid:
            cfg = base.replace(**ov)
            assert set(cfg.timeframes()) <= {"M1", "M5", "M15", "H1", "H4"}
    # RSI on one timeframe and MACD on another really is a split weight
    grid, labels = sweep.grid_split_indicator(universe, "hedging", fc_tfs=["M15"])
    i = labels.index(dict(open_rsi="H1", open_macd="M5", fc="M15"))
    cfg = base.replace(**grid[i])
    assert cfg.open_weights == {"H1": (1.0, 0.0), "M5": (0.0, 1.0)}


def test_experiment_grids_are_valid_for_this_variant(live_cfg):
    from backtesting import experiments

    for symbol in ("XAUUSDm", "BTCUSDm"):
        base = live_cfg(symbol, fixed_units=1)
        for grid, labels in (experiments.lever_grid(base), experiments.package_grid(base)):
            assert len(grid) == len(labels) > 10
            for ov in grid:
                base.replace(**ov)          # must construct
        # the first package is the live configuration itself
        g, l = experiments.package_grid(base)
        assert l[0]["package"] == "live settings" and g[0] == {}


def test_bootstrap_is_deterministic_and_bounded():
    rng = np.random.default_rng(3)
    t = pd.date_range("2026-01-01", periods=400, freq="3h", tz="UTC")
    b = pd.DataFrame({"close_time": t, "pnl": np.where(rng.random(400) < 0.9, 1.0, -8.0)})
    x = robustness.bootstrap(b, 2000.0, n=300, seed=1)
    y = robustness.bootstrap(b, 2000.0, n=300, seed=1)
    assert x == y
    assert 0.0 <= x["prob_loss"] <= 1.0 and x["final_p05"] <= x["final_p50"] <= x["final_p95"]
    assert x["max_dd_p50"] <= x["max_dd_p95"] <= x["max_dd_p99"]
    assert robustness.bootstrap(b.iloc[:0], 2000.0) == {}


def test_rank_agreement_on_known_orderings():
    n = 60
    base = pd.DataFrame({"baskets@A": [100] * n, "baskets@B": [100] * n,
                         "net_profit@A": np.arange(n, dtype=float)})
    same = base.assign(**{"net_profit@B": np.arange(n, dtype=float) * 2.0})
    flip = base.assign(**{"net_profit@B": -np.arange(n, dtype=float)})
    assert robustness.rank_agreement(same, "A", "B")["spearman"] == pytest.approx(1.0)
    assert robustness.rank_agreement(flip, "A", "B")["spearman"] == pytest.approx(-1.0)
    r = robustness.rank_agreement(flip, "A", "B")
    assert r["best_A"] == n - 1 and r["best_A_then_B"] == -(n - 1)


def test_index_page_builds_from_a_results_directory(tmp_path, fixture_store, live_cfg, engine_run, live_root):
    """The landing page must render from whatever subset of results exists."""
    from backtesting.viz.index import build_index
    from backtesting.viz.report import build_report

    out = tmp_path / "results"
    res = engine_run(live_cfg("XAUUSDm"), mode="sec")
    build_report(res, out / "baseline" / "XAUUSDm", closeups=False, store_dir=fixture_store)
    (out / "findings.json").write_text(json.dumps([{"title": "t", "detail": "d"}]))
    path = build_index(out, live_root=live_root)
    page = path.read_text(encoding="utf-8")
    assert "The live settings on real ticks" in page and "XAUUSDm" in page
