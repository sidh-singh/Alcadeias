"""
Invariants of the fast engine on real fixture ticks.

Whatever the configuration, a simulated account has to add up, obey the bot's own timing
rules, be reproducible, and never use information from the future.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.config import FIBO
from backtesting.data import store
from backtesting.engine import fast

SYMBOLS = ["XAUUSDm", "BTCUSDm"]
VARIANTS = [
    dict(),
    dict(initial_balance=5200.0),                                   # unit 3
    dict(open_weights={"M15": 1, "M5": 1}, fc_weights={"M5": 1}),   # other timeframes
    dict(max_adds=2, ladder_min_gap=0.0),
]


def _runs(live_cfg, engine_run):
    for symbol in SYMBOLS:
        for ov in VARIANTS:
            cfg = live_cfg(symbol, **ov)
            yield cfg, engine_run(cfg, mode="ticks")


def test_the_account_adds_up(live_cfg, engine_run):
    """final balance = start + every basket's P/L; equity = balance + what is still open."""
    n = 0
    for cfg, res in _runs(live_cfg, engine_run):
        b, f, sc = res.baskets, res.fills, res.scalars
        assert sc["final_balance"] == pytest.approx(cfg.initial_balance + b["pnl"].sum(), abs=0.006)
        assert sc["final_equity"] == pytest.approx(sc["final_balance"] + sc["open_profit_at_end"], abs=1e-9)
        closes = f[f["action"] == "close"]
        assert closes["profit"].sum() == pytest.approx(b["pnl"].sum(), abs=0.006)     # no commission on Standard
        # the balance column moves only on closes and by exactly the realised profit
        bal = cfg.initial_balance
        for _, r in f.iterrows():
            if r["action"] == "close":
                bal += r["profit"]
            assert r["balance"] == pytest.approx(bal, abs=0.006)
        n += len(b)
    assert n > 5          # not vacuous: the fixture windows hold dozens of baskets (hedging) or a handful (netting, no fixed target)


def test_every_basket_closes_exactly_what_it_opened(live_cfg, engine_run):
    for cfg, res in _runs(live_cfg, engine_run):
        f = res.fills
        for bid, g in f.groupby("basket"):
            ins = g[g["action"].isin(["open", "add"])]
            outs = g[g["action"] == "close"]
            assert (g["side"] == g["side"].iloc[0]).all()                 # one direction per basket
            assert list(ins["action"])[0] == "open" and (ins["action"].iloc[1:] == "add").all()
            if len(outs):                                                 # (the last basket may still be open)
                assert outs["lots"].sum() == pytest.approx(ins["lots"].sum(), abs=1e-9)
                assert len(outs) == len(ins)
                assert outs["time"].nunique() == 1 and outs["time"].iloc[0] >= ins["time"].max()
                # each close row refers back to its own entry
                assert sorted(outs["pos_open_price"].round(6)) == sorted(ins["price"].round(6))


def test_ladder_lots_are_fibonacci_times_the_unit(live_cfg, engine_run):
    for cfg, res in _runs(live_cfg, engine_run):
        ins = res.fills[res.fills["action"].isin(["open", "add"])]
        for _, g in ins.groupby("basket"):
            unit = int(g["units"].iloc[0])
            expect = [round(FIBO[i] * unit * cfg.mtqty, 2) for i in range(len(g))]
            assert list(g["lots"].round(2)) == expect
            assert len(g) <= cfg.n_ladder_adds + 1


def test_units_follow_the_balance_only_while_flat(live_cfg, engine_run):
    cfg = live_cfg("BTCUSDm", initial_balance=5200.0)
    res = engine_run(cfg, mode="ticks")
    opens = res.fills[res.fills["action"] == "open"]
    assert len(opens)
    for _, r in opens.iterrows():
        assert int(r["units"]) == min(int(r["balance"] // cfg.step_up_balance) + 1, cfg.unit_max_limit)
    # the unit is frozen for the life of a basket
    assert (res.fills.groupby("basket")["units"].nunique() == 1).all()


def test_no_fresh_entry_inside_the_cooldown(live_cfg, engine_run):
    for cfg, res in _runs(live_cfg, engine_run):
        b = res.baskets.sort_values("open_time")
        opens = res.fills[res.fills["action"] == "open"].sort_values("time")
        if len(b) < 2:
            continue
        prev_close = b["close_time"].reset_index(drop=True).iloc[:-1]
        next_open = opens["time"].reset_index(drop=True).iloc[1:len(b)].reset_index(drop=True)
        gap = (next_open - prev_close).dt.total_seconds()
        assert len(gap) == len(b) - 1 and (gap >= cfg.reentry_cooldown_s - 1e-9).all()


def test_exit_reasons_are_consistent_with_the_rules(live_cfg, engine_run, live_variant):
    for cfg, res in _runs(live_cfg, engine_run):
        b = res.baskets
        if live_variant == "hedging":
            tgt = b[b["reason"] == "target"]
            assert (tgt["profit_seen"] > cfg.target_usd_per_unit * tgt["units"]).all()
            # a force-close only happens when the target test failed on that poll
            fc = b[b["reason"] == "force_close"]
            assert (fc["profit_seen"] <= cfg.target_usd_per_unit * fc["units"]).all()
            assert set(b["reason"]) <= {"target", "force_close"}
        else:
            bk = b[b["reason"] == "book"]
            assert (bk["profit_seen"] > cfg.profit_protect_usd_per_unit * bk["units"]).all()
            assert set(b["reason"]) <= {"book", "force_close"}


def test_trading_window_blocks_only_fresh_entries(live_cfg, engine_run):
    """Outside the window no basket is opened; adds and closes of an existing basket still happen."""
    cfg = live_cfg("BTCUSDm", window_enabled=True, window_start_min=0, window_end_min=1)   # in window: Monday 00:00 only
    res = engine_run(cfg, mode="ticks")
    assert len(res.fills) == 0 and res.counters["polls_entry_blocked_window"] > 0
    free = engine_run(live_cfg("BTCUSDm", window_enabled=False), mode="ticks")
    assert len(free.baskets) > 0


def test_runs_are_deterministic(live_cfg, engine_run):
    cfg = live_cfg("XAUUSDm")
    a, b = engine_run(cfg, mode="ticks"), engine_run(cfg, mode="ticks")
    pd.testing.assert_frame_equal(a.fills, b.fills)
    pd.testing.assert_frame_equal(a.baskets, b.baskets)
    assert a.scalars == {**b.scalars} and a.counters == b.counters


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_per_second_series_gives_the_same_trades_as_raw_ticks(live_cfg, engine_run, symbol):
    """
    With every poll on a whole second (no 0.1 s post-order delay), the per-second series
    must reproduce the raw-tick run trade for trade: that is the claim sweeps rest on.
    """
    cfg = live_cfg(symbol, open_order_delay_ms=0, add_order_delay_ms=1000)
    a, b = engine_run(cfg, mode="ticks"), engine_run(cfg, mode="sec")
    cols = ["time", "action", "side", "lots", "price", "profit", "reason", "units", "open_score", "fc_score"]
    pd.testing.assert_frame_equal(a.fills[cols], b.fills[cols])
    assert a.scalars["final_equity"] == pytest.approx(b.scalars["final_equity"], abs=1e-9)
    assert len(a.fills) > 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_no_lookahead(fixture_store, live_cfg, windows, symbol):
    """
    Decisions up to time b must not depend on anything after b: a run over [a, c) and a run
    over [a, b) -- the second one prepared from data that ENDS at b -- make the same fills
    before b.
    """
    a, c = windows[symbol]
    b_ms = store.to_ms(a) + (store.to_ms(c) - store.to_ms(a)) * 2 // 3
    b = str(store.ms_to_dt(b_ms).tz_localize(None))
    cfg_full = live_cfg(symbol)
    cfg_cut = live_cfg(symbol, end=b)
    full = fast.run(cfg_full, fast.prepare(symbol, a, c, cfg_full.timeframes(), mode="ticks", store_dir=fixture_store))
    cut = fast.run(cfg_cut, fast.prepare(symbol, a, b, cfg_cut.timeframes(), mode="ticks", store_dir=fixture_store))
    cutoff = pd.Timestamp(b, tz="UTC")
    before = full.fills[full.fills["time"] < cutoff].reset_index(drop=True)
    assert len(before) > 0
    pd.testing.assert_frame_equal(before, cut.fills.reset_index(drop=True))


def test_latency_changes_the_fill_not_the_decision(live_cfg, engine_run):
    """A delayed fill uses a later quote; the decision time and the signal stay where they were."""
    base = engine_run(live_cfg("BTCUSDm"), mode="ticks")
    late = engine_run(live_cfg("BTCUSDm", latency_ms=700), mode="ticks")
    first_a, first_b = base.fills.iloc[0], late.fills.iloc[0]
    assert first_a["time"] == first_b["time"] and first_a["action"] == first_b["action"] == "open"
    assert first_b["fill_time"] >= first_a["fill_time"]
    assert (late.fills["fill_time"] >= late.fills["time"] - pd.Timedelta(seconds=180)).all()
    assert ((late.fills["fill_time"] - late.fills["time"]) <= pd.Timedelta(milliseconds=700)).all()


def test_spread_stress_makes_entries_more_expensive(live_cfg, engine_run):
    a = engine_run(live_cfg("XAUUSDm"), mode="ticks")
    b = engine_run(live_cfg("XAUUSDm", spread_mult=2.0), mode="ticks")
    fa, fb = a.fills.iloc[0], b.fills.iloc[0]
    assert fa["time"] == fb["time"]
    spread = fa["ask"] - fa["bid"]
    assert (fb["ask"] - fb["bid"]) == pytest.approx(2.0 * spread, abs=1e-9)
    if fa["side"] == "BUY":
        assert fb["price"] == pytest.approx(fa["price"] + spread, abs=1e-9)
    else:
        assert fb["price"] == pytest.approx(fa["price"], abs=1e-9)          # a sell fills at the bid either way


def test_stop_out_ends_the_run_at_zero(live_cfg, engine_run):
    """An account too small for its positions is liquidated when equity reaches zero, and never goes below it."""
    cfg = live_cfg("BTCUSDm", initial_balance=6.0, target_usd_per_unit=None, book_enabled=False,
                   force_close_enabled=False, window_enabled=False)
    res = engine_run(cfg, mode="ticks")
    if res.scalars["stopped_out"]:
        assert res.scalars["final_balance"] == 0.0 and (res.baskets["reason"] == "stop_out").sum() == 1
        assert res.baskets["reason"].iloc[-1] == "stop_out"
    else:                                   # the fixture hour happened not to move far enough: still solvent
        assert res.scalars["min_equity"] > 0.0


@pytest.mark.parametrize("tiers", [["M1", "M5", "M15", "H1", "H4"], ["M15"] * 5, ["H4", "H1", "M15", "M5", "M1"], ["M5", "M5"]])
def test_each_add_is_released_by_its_own_tier_timeframe(live_cfg, engine_run, tiers):
    """
    The k-th add fires only on a poll where the RSI of the k-th ladder timeframe is at or
    beyond the level, whichever timeframes the tiers are set to; and never deeper than the list.
    """
    from backtesting.engine import kernels as K

    seen = 0
    for symbol in SYMBOLS:
        cfg = live_cfg(symbol, ladder_tfs=list(tiers), rsi_oversold=45.0, rsi_overbought=55.0)   # wide levels: plenty of adds
        res = engine_run(cfg, mode="ticks", trace=True)
        tr = res.trace
        adds = tr[(tr[:, K.T_SIGNAL] == 5) | (tr[:, K.T_SIGNAL] == 6)]
        for row in adds:
            depth = abs(int(row[K.T_NPOS]))                 # positions held when the add was decided (negative = sells)
            assert 1 <= depth <= len(tiers)
            rsi = row[K.T_RSI0 + depth - 1]
            if row[K.T_SIGNAL] == 5:
                assert rsi <= cfg.rsi_oversold
            else:
                assert rsi >= cfg.rsi_overbought
        seen += len(adds)
        n = res.fills[res.fills["action"].isin(["open", "add"])].groupby("basket").size()
        assert n.max() <= len(tiers) + 1
    assert seen > 0
