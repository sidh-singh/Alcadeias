"""
The whole experiment pipeline, end to end, on the bundled ticks.

``experiments.reproduce`` is run in miniature (one symbol, short windows inside the fixture
hour, a small timeframe universe) through every stage, then the landing page and BACKTEST.md
are built from what it wrote. This is the test that fails when a stage, a table builder and
the files in between stop agreeing with each other.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from backtesting import experiments as E

SYM = "BTCUSDm"
W5 = {"IS": ("2026-11-09 06:40", "2026-11-09 07:00"), "OOS1": ("2026-11-09 06:20", "2026-11-09 06:40"),
      "OOS2": ("2026-11-09 06:00", "2026-11-09 06:20"), "HO2": ("2026-11-09 06:10", "2026-11-09 06:30"),
      "HO1": ("2026-11-09 06:30", "2026-11-09 06:50")}


@pytest.fixture(scope="module")
def results(tmp_path_factory, fixture_store, live_root):
    mp = pytest.MonkeyPatch()
    mp.setenv("ALCADEIAS_STORE_DIR", str(fixture_store))
    mp.setattr(E, "WINDOWS", {k: W5[k] for k in ("IS", "OOS1", "OOS2")})
    mp.setattr(E, "HOLDOUT", {k: W5[k] for k in ("HO2", "HO1")})
    mp.setattr(E, "ALL_WINDOWS", dict(W5))
    mp.setattr(E, "LONG_WINDOW", ("2026-11-09 06:00", "2026-11-09 07:00"))
    mp.setattr(E, "UNIVERSE", ["M1", "M5", "M15"])
    out = tmp_path_factory.mktemp("results")
    try:
        E.reproduce(out, symbols=(SYM,), live_root=live_root, n_jobs=1)
        yield out, mp
    finally:
        mp.undo()


def test_every_stage_writes_its_output_and_stamps_it(results):
    out, _ = results
    for rel in ("data_quality/BTCUSDm.json", "baseline/BTCUSDm/summary.json", "baseline/BTCUSDm/report.html",
                "long/BTCUSDm/summary.json", "signal/BTCUSDm.json", "sweeps/BTCUSDm_timeframes.csv",
                "sweeps/BTCUSDm_split_open.csv", "sweeps/BTCUSDm_split_fc.csv", "sweeps/BTCUSDm_timeframes_holdout.csv",
                "levers/BTCUSDm.csv", "packages/BTCUSDm.csv", "candidates/BTCUSDm.csv", "candidates/BTCUSDm_account.csv",
                "candidates/BTCUSDm_timing.csv", "robustness/BTCUSDm/quarters_timing.csv",
                "robustness/BTCUSDm/quarters_timing_fixed_unit.csv", "robustness/BTCUSDm/timing.csv",
                "robustness/BTCUSDm/costs.csv", "robustness/BTCUSDm/start_shift.csv", "robustness/BTCUSDm/bootstrap.json"):
        assert (out / rel).exists(), rel
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {"sweeps/BTCUSDm_timeframes.csv", "baseline/BTCUSDm/summary.json", "robustness/BTCUSDm/bootstrap.json"} <= set(manifest)
    builds = E.manifest_builds(out)
    assert len(builds) == 1, builds                                     # one engine build, one set of live settings
    assert E.stale_outputs(out, E._LIVE_ROOT[0]) == []


def test_sweep_rows_carry_the_account_replay_and_the_ensembles_their_seeds(results):
    out, _ = results
    tf = pd.read_csv(out / "sweeps" / "BTCUSDm_timeframes.csv")
    assert len(tf) == (3 + 3 * 2) * 3 * 2                               # (singles + pairs x 2 entry rules) x fc x 2 levels
    for w in ("IS", "OOS1", "OOS2"):
        assert {f"net_profit@{w}", f"acct_net@{w}", f"acct_wiped@{w}", f"acct_dip@{w}"} <= set(tf.columns)
    q = pd.read_csv(out / "robustness" / SYM / "quarters_timing.csv")
    assert sorted(q["seed"].unique()) == list(range(1, 9)) and set(q["window"]) == set(W5)
    c = pd.read_csv(out / "candidates" / "BTCUSDm_timing.csv")
    assert len(c) == c["candidate"].nunique() * len(W5) * 8
    costs = pd.read_csv(out / "robustness" / SYM / "costs.csv")
    assert set(costs["test"]) == {"spread", "slippage"} and costs.groupby(["test", "spread_mult", "slippage"]).size().eq(4).all()
    boot = json.loads((out / "robustness" / SYM / "bootstrap.json").read_text(encoding="utf-8"))
    if boot["baskets"]:              # (the netting variant closes no basket inside the miniature window)
        assert {"prob_wiped", "final_p50", "dip_p95"} <= set(boot["live_units"])
    else:
        assert boot["live_units"] == {}


def test_pages_build_from_the_results(results, live_root):
    from backtesting.viz.index import build_index
    from backtesting.viz.markdown import build_backtest_md

    out, _ = results
    (out / "findings.json").write_text(json.dumps([{"title": "A finding", "detail": "with “quotes” and 94.6% → text"}],
                                                  ensure_ascii=False), encoding="utf-8")
    (out / "audit.json").write_text(json.dumps([{"title": "An audit item", "where": "app.py:1", "detail": "detail"}]), encoding="utf-8")
    (out / "recommendations.md").write_text("1. A recommendation.\n", encoding="utf-8")
    page = build_index(out, symbols=(SYM,), live_root=live_root).read_text(encoding="utf-8")
    md = build_backtest_md(out, symbols=(SYM,), live_root=live_root, target=out / "BACKTEST.md").read_text(encoding="utf-8")
    # (the signal study needs M15 bars four ahead; the miniature windows are too short for it, so that section is absent)
    for needle in ("The live settings on real ticks", "Quarter by quarter, and how much is timing luck",
                   "which timeframes for OPEN",
                   "The hold-out test", "Candidate settings on all five quarters", "What-ifs aimed at the flaws",
                   "how fragile is the result", "A finding"):
        assert needle in page, needle
    assert "Some results on this page are stale" not in page
    for needle in ("## Results with the live settings", "Quarter by quarter, and how much is timing luck",
                   "## Which timeframes for OPEN, FORCE-CLOSE",
                   "## Does choosing timeframes on past data work? The hold-out test", "## Candidate settings",
                   "## What-ifs aimed at the flaws", "## Every other parameter, one at a time",
                   "## How fragile is the live result?", "## Recommendations", "## Live-code findings",
                   "Quarter-runs that lost", "A slower loop"):
        assert needle in md, needle
    boot = json.loads((out / "robustness" / SYM / "bootstrap.json").read_text(encoding="utf-8"))
    assert ("Which days happened to be in the quarter" in md) == bool(boot["baskets"])
    assert "Some results below are stale" not in md and "nan" not in md.lower().replace("nanosecond", "")


def test_a_second_run_recomputes_nothing_and_a_foreign_build_is_recomputed(results, live_root):
    out, _ = results
    target = out / "sweeps" / "BTCUSDm_split_fc.csv"
    before = target.stat().st_mtime_ns
    E.reproduce(out, symbols=(SYM,), live_root=live_root, only=["sweeps"], n_jobs=1)
    assert target.stat().st_mtime_ns == before                          # fresh: skipped
    # pretend the file came from another build of the engine
    mf = out / "manifest.json"
    data = json.loads(mf.read_text(encoding="utf-8"))
    data["sweeps/BTCUSDm_split_fc.csv"]["engine"] = "0" * 12
    mf.write_text(json.dumps(data), encoding="utf-8")
    assert E.stale_outputs(out, live_root) == ["sweeps/BTCUSDm_split_fc.csv"]
    from backtesting.viz.index import build_index
    assert "Some results on this page are stale" in build_index(out, symbols=(SYM,), live_root=live_root).read_text(encoding="utf-8")
    E.reproduce(out, symbols=(SYM,), live_root=live_root, only=["sweeps"], n_jobs=1)
    assert target.stat().st_mtime_ns != before and E.stale_outputs(out, live_root) == []
