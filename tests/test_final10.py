"""
The final ten (backtesting/research/final10.py): the selection rule must reproduce the pre-registered lists from the
committed evidence, and the account figures must mean what the write-up says they mean.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backtesting.research import final10 as F


def test_the_rule_reproduces_the_pre_registered_selection():
    sel = json.loads((F.OUT / "selection.json").read_text())
    chosen = F.select(F.evidence())
    for sym in F.SYMBOLS:
        assert [r["label"] for r in chosen[sym]] == [r["label"] for r in sel["final"][sym]]


def test_eligibility_and_the_cap():
    E = F.evidence()
    chosen = F.select(E)
    for sym in F.SYMBOLS:
        rows = chosen[sym]
        assert len(rows) == F.N_FINAL
        assert all(r["periods_up"] >= F.MIN_PERIODS_UP and r["dd_fresh"] <= F.MAX_DD_PCT for r in rows)
        fams = pd.Series([r["family"] for r in rows if r["kind"] == "published"]).value_counts()
        assert (fams <= F.FAMILY_CAP).all()
        scores = [r["profit_per_dd"] for r in rows]
        assert scores == sorted(scores, reverse=True)


def _daily(values, start="2021-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D", tz="UTC")
    return pd.Series(np.asarray(values, float), index=idx)


def test_account_metrics_on_a_hand_made_account():
    # 2,000 -> 2,400 -> 2,100 -> 2,600 over four days, a year-long window
    d = _daily([2000.0, 2400.0, 2100.0, 2600.0])
    a = int(pd.Timestamp("2021-01-01", tz="UTC").timestamp())
    z = a + int(F.YEAR_S)
    m = F.account_metrics(d, 2600.0, 12.5, a, z, np.array([400.0, -300.0, 500.0]), False, None)
    assert m["net"] == 600.0 and m["return_pct"] == pytest.approx(30.0)
    assert m["cagr_pct"] == pytest.approx(30.0, abs=1e-6)              # one year: CAGR = the return
    assert m["return_per_dd"] == pytest.approx(30.0 / 12.5, rel=1e-3)
    assert m["win_rate_pct"] == pytest.approx(66.7, abs=0.1)
    assert m["profit_factor"] == pytest.approx(900.0 / 300.0, rel=1e-3)
    assert m["longest_underwater_days"] == 1.0                        # below the 2,400 peak for one day


def test_yearly_profit_adds_up_to_the_net():
    idx = pd.to_datetime(["2020-11-20", "2021-01-04", "2021-06-01", "2022-01-03"], utc=True)
    d = pd.Series([2000.0, 2100.0, 1900.0, 2500.0], index=idx)
    a = int(idx[0].timestamp())
    z = int(pd.Timestamp("2022-06-01", tz="UTC").timestamp())
    ys = F.yearly(d, 2700.0, a, z)
    assert [y["year"] for y in ys] == [2020, 2021, 2022]
    assert sum(y["pnl"] for y in ys) == pytest.approx(700.0)
    assert ys[0]["start_equity"] == F.ACCOUNT


def test_display_names_and_barely_traded_rows():
    assert F.display("Turtle (risk-sized)") == "Turtle, 1% risk"
    assert F.display("V3-lite + 200-day trend filter, as the bot runs it") == "V3-lite + 200-day trend filter, as the bot runs it"
    assert F._barely({"skipped_trades": 221, "trades": 3})
    assert not F._barely({"skipped_trades": 129, "trades": 1009})
