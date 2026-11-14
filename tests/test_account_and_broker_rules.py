"""
The real account behind a fixed-unit run, and the broker's side of an order.

* ``metrics.replay_account``: sweeps trade one fixed 0.01-lot unit on a balance that cannot be
  stopped out; the replay says what the same baskets do to a $2,000 account that steps its unit
  up with the balance, as the bot does.
* Orders the broker refuses: after a session's last quote, for a short while after a session
  break, and when margin is short. The live loop sleeps after an order whether it was filled or
  not, and tries again on the next pass. Both engines apply the same rules, so the comparison
  with the real ``app.py`` loop covers them.
"""

from __future__ import annotations

import shutil
import warnings

import numpy as np
import pandas as pd
import pytest

from backtesting.analysis import metrics
from backtesting.data import store
from backtesting.engine import fast, kernels as K
from backtesting.engine.parity import check_parity


def _ms(ts) -> int:
    return int(pd.Timestamp(ts).value // 1_000_000)


# ───────────────────────────── the account replay ─────────────────────────────

def _baskets(rows):
    t = pd.date_range("2026-01-01", periods=len(rows), freq="h", tz="UTC")
    return pd.DataFrame({"close_time": t, "pnl": [r[0] for r in rows], "mae": [r[1] for r in rows], "units": 1})


def test_replay_applies_the_unit_rule_basket_by_basket():
    # $2,000, step $2,500: +600 lifts the balance to 2,600 -> the next basket trades two units
    b = _baskets([(600.0, -5.0), (-100.0, -150.0), (50.0, -1.0), (-1200.0, -1300.0), (10.0, 0.0)])
    r = metrics.replay_account(b, 2000.0, 2500.0, 10)
    # 2000 -> 2600 | x2: dips to 2300, ends 2400 | x1: 2450 | x1: dips to 1150, ends 1250 | 1260
    assert r == {"acct_net": -740.0, "acct_wiped": False, "acct_dip": 850.0, "acct_max_units": 2}
    # at one fixed unit the same baskets end at 2000 - 640 and never dip below 2000 - 150 - ... : the replay is harsher
    assert metrics.replay_account(b, 2000.0, 0.0, 1)["acct_net"] == -640.0


def test_replay_wipes_the_account_on_a_floating_loss_the_balance_cannot_cover():
    b = _baskets([(600.0, -5.0), (20.0, -1400.0), (50.0, -1.0)])     # at two units the second basket floats -2,800 > 2,600
    r = metrics.replay_account(b, 2000.0, 2500.0, 10)
    assert r["acct_wiped"] and r["acct_net"] == -2000.0 and r["acct_dip"] == 2000.0
    # the same baskets at one fixed unit survive: this is the case the fixed-unit dip test cannot see
    assert not metrics.replay_account(b, 2000.0, 0.0, 1)["acct_wiped"]
    # the unit never exceeds the cap
    big = _baskets([(30_000.0, 0.0), (1.0, -1.0)])
    assert metrics.replay_account(big, 2000.0, 2500.0, 3)["acct_max_units"] == 3
    # a basket still open at the end counts with its floating result
    assert metrics.replay_account(b.iloc[:0], 2000.0, 2500.0, 10, open_profit=-50.0) == \
        {"acct_net": -50.0, "acct_wiped": False, "acct_dip": 50.0, "acct_max_units": 1}


def test_score_row_carries_the_replay(live_cfg, engine_run):
    fixed = engine_run(live_cfg("BTCUSDm", fixed_units=1, initial_balance=1_000_000.0), mode="ticks", light=True)
    row = metrics.score_row(fixed)
    assert {"acct_net", "acct_wiped", "acct_dip", "acct_max_units"} <= set(row)
    # on the fixture hour the balance never reaches $2,500, so the replayed account trades one unit throughout
    assert row["acct_max_units"] == 1 and row["acct_net"] == pytest.approx(row["net_profit"], abs=0.02)
    real = engine_run(live_cfg("BTCUSDm"), mode="ticks", light=True)      # a real $2,000 run reports its own figures
    r2 = metrics.score_row(real)
    assert r2["acct_net"] == r2["net_profit"] and r2["acct_wiped"] == r2["stopped_out"]


def test_a_stopped_out_run_is_reported_over_the_days_it_traded(live_cfg, engine_run):
    cfg = live_cfg("BTCUSDm", initial_balance=6.0, target_usd_per_unit=None, book_enabled=False,
                   force_close_enabled=False, window_enabled=False)
    res = engine_run(cfg, mode="ticks")
    s = metrics.summarize(res)
    if s["stopped_out"]:
        assert s["stopped_out_at"] and 0 < s["ran_days"] < s["days"]
    else:
        assert s["stopped_out_at"] is None and s["ran_days"] == pytest.approx(s["days"], abs=0.01)


# ───────────────────────────── orders the broker refuses ─────────────────────────────

BREAK_S = 31 * 60          # a silence of half an hour or more is a session break


def _cut(fixture_store, root, symbol, a_ms, b_ms):
    shutil.copytree(fixture_store / symbol, root / symbol)
    for d in sorted((root / symbol).iterdir()):
        for kind, key, scale in (("ticks", "t_ms", 1), ("sec", "t_ms", 1), ("m1", "t", 1000)):
            f = d / f"{kind}.npz"
            x = dict(np.load(f))
            t = x[key].astype(np.int64) * scale
            gone = ((t >= ((a_ms // 60_000) + 1) * 60_000) & (t + 60_000 <= b_ms)) if kind == "m1" else ((t >= a_ms) & (t < b_ms))
            np.savez_compressed(f, **{k: v[~gone] for k, v in x.items()})


@pytest.fixture(scope="module")
def gold_break(live_cfg, fixture_store, tmp_path_factory, windows):
    """
    The gold fixture with a 31-minute session break cut in, placed so that the bot wants to
    re-enter while the market is shut: the break starts 50 s before a re-entry that was only
    waiting for its cooldown.
    """
    symbol = "XAUUSDm"
    cfg = live_cfg(symbol, open_order_delay_ms=100)
    res = fast.run(cfg, fast.prepare(symbol, cfg.start, cfg.end, cfg.timeframes(), mode="ticks", store_dir=fixture_store))
    b = res.baskets
    opens = res.fills[res.fills["action"] == "open"]["time"].astype("int64").to_numpy() // 1_000_000
    closes = b["close_time"].astype("int64").to_numpy() // 1_000_000
    end = _ms(windows[symbol][1])
    waited = [int(o) for o in opens for c in closes if abs((o - c) - int(cfg.reentry_cooldown_s * 1000)) <= 1500
              and o + (BREAK_S + 240) * 1000 < end]
    wanted = bool(waited)
    at = (waited[0] if wanted else int(opens[0]) + 60_000) - 50_000
    root = tmp_path_factory.mktemp("gold_break")
    _cut(fixture_store, root, symbol, at, at + BREAK_S * 1000)
    ticks = store.load_ticks(symbol, _ms(windows[symbol][0]), end, root)
    last = int(ticks["t_ms"][ticks["t_ms"] < at][-1])
    first = int(ticks["t_ms"][ticks["t_ms"] >= at][0])
    return dict(store=root, a=at, last=last, first=first, wanted=wanted, symbol=symbol)


def test_no_order_is_filled_after_the_session_s_last_quote(live_cfg, gold_break):
    g = gold_break
    cfg = live_cfg(g["symbol"], open_order_delay_ms=100)
    res = fast.run(cfg, fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="ticks", store_dir=g["store"]),
                   trace=True)
    t = res.fills["time"].astype("int64") // 1_000_000
    # nothing is decided-and-filled from a second after the last quote until the market is back
    assert not ((t > g["last"] + K.SESSION_CLOSE_GRACE_MS) & (t < g["first"])).any()
    # and for 90 s after the reopen no new position is opened (closes would be accepted)
    opens = res.fills[res.fills["action"].isin(["open", "add"])]["time"].astype("int64") // 1_000_000
    assert not ((opens >= g["first"]) & (opens < g["first"] + int(cfg.close_only_after_break_s * 1000))).any()
    if g["wanted"]:
        assert res.counters["orders_refused_market_closed"] > 0
        # a refused entry costs the loop the helper's 0.1 s as well: polls on which one was refused are 1.1 s apart
        tr = res.trace
        ref = tr[(tr[:, K.T_T] > g["last"] + K.SESSION_CLOSE_GRACE_MS) & (tr[:, K.T_T] < g["last"] + 170_000)
                 & ((tr[:, K.T_SIGNAL] == 1) | (tr[:, K.T_SIGNAL] == 2))]
        if len(ref) > 3:
            assert set(np.diff(ref[:, K.T_T]).astype(int)) == {1100}


def test_fast_engine_matches_the_live_loop_across_a_session_break(live_cfg, live_root, gold_break):
    """
    The real app.py loop against the simulated terminal with the broker's rules switched on:
    orders after the session's last quote and in the close-only period after the reopen are
    refused, the live code sleeps and retries, and the fast engine does exactly the same.
    """
    g = gold_break
    rep = check_parity(live_cfg(g["symbol"]), live_root=live_root, store_dir=g["store"])
    assert rep.ok, str(rep)
    assert rep.polls_ref == rep.polls_fast > 0 and rep.fills_ref == rep.fills_fast
    if g["wanted"]:
        assert rep.refused_ref.get("market_closed", 0) > 0, rep.refused_ref


@pytest.mark.parametrize("symbol,start,end,balance", [
    ("XAUUSDm", "2026-11-11 15:00", "2026-11-11 15:04", 1.0),          # no margin for the entry itself
    ("XAUUSDm", "2026-11-11 15:00", "2026-11-11 15:22", 6.0),          # the entry fits, a ladder add does not
])
def test_parity_when_margin_refuses_orders(live_cfg, live_root, fixture_store, symbol, start, end, balance):
    """A refused order costs the live loop the same sleeps as a filled one; the fast engine keeps the same cadence."""
    cfg = live_cfg(symbol, start=start, end=end, initial_balance=balance)
    probe = fast.run(cfg.replace(open_order_delay_ms=100),
                     fast.prepare(symbol, start, end, cfg.timeframes(), mode="ticks", store_dir=fixture_store))
    if probe.scalars["stopped_out"]:
        # with so small a balance this variant runs the account to zero inside the window; the simulated
        # terminal has no stop-out, so the two engines cannot be compared beyond that point
        pytest.skip("the account is stopped out in this window for this variant")
    rep = check_parity(cfg, live_root=live_root, store_dir=fixture_store)
    assert rep.ok, str(rep)
    assert rep.refused_ref.get("no_money", 0) > 0, "the window was chosen so that the broker refuses orders for margin"


# ───────────────────────────── the state a run starts in ─────────────────────────────

def test_a_run_started_just_after_a_break_inherits_the_close_only_period(live_cfg, gold_break):
    g = gold_break
    start = str(pd.Timestamp(g["first"], unit="ms").floor("s") + pd.Timedelta(seconds=2))
    cfg = live_cfg(g["symbol"], start=start, open_order_delay_ms=100)
    res = fast.run(cfg, fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="ticks", store_dir=g["store"]))
    opens = res.fills[res.fills["action"] == "open"]["time"].astype("int64") // 1_000_000
    assert not (opens < g["first"] + int(cfg.close_only_after_break_s * 1000)).any()


def test_per_second_series_warns_about_timings_it_cannot_carry(live_cfg, fixture_store):
    cfg = live_cfg("BTCUSDm")
    prep = fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="sec", store_dir=fixture_store)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fast.run(cfg, prep)                                             # whole seconds everywhere: silent
    for bad in (dict(open_order_delay_ms=100), dict(latency_ms=300), dict(poll_interval_ms=1250), dict(poll_jitter_ms=200)):
        with pytest.warns(RuntimeWarning, match="per-second series"):
            fast.run(cfg.replace(**bad), prep)
    ticks = fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="ticks", store_dir=fixture_store)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fast.run(cfg.replace(open_order_delay_ms=100, latency_ms=300), ticks)   # raw ticks carry any timing


def test_configuration_rejects_values_the_engine_would_silently_bend(live_cfg):
    with pytest.raises(ValueError, match="ladder_multipliers"):
        live_cfg("XAUUSDm", ladder_multipliers=[2, 3, 5])
    with pytest.raises(ValueError, match="fixed_units"):
        live_cfg("XAUUSDm", fixed_units=20)
    assert live_cfg("XAUUSDm", fixed_units=10).fixed_units == 10
