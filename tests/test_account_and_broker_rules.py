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


def test_replay_counts_the_floating_low_of_a_basket_still_open():
    none = _baskets([])
    # the end mark is fine, but the basket had been $2,100 under water: a $2,000 account did not live to see the recovery
    r = metrics.replay_account(none, 2000.0, 2500.0, 10, open_profit=5.0, open_mae=-2100.0)
    assert r == {"acct_net": -2000.0, "acct_wiped": True, "acct_dip": 2000.0, "acct_max_units": 1}
    # survived: the dip is the floating low, the result the end mark
    r = metrics.replay_account(none, 2000.0, 2500.0, 10, open_profit=-50.0, open_mae=-300.0)
    assert r == {"acct_net": -50.0, "acct_wiped": False, "acct_dip": 300.0, "acct_max_units": 1}
    # the open basket is re-sized like the closed ones: after +600 the account trades two units (2,600 - 800, 2,600 - 200)
    r = metrics.replay_account(_baskets([(600.0, -5.0)]), 2000.0, 2500.0, 10, open_profit=-100.0, open_mae=-400.0)
    assert r == {"acct_net": 400.0, "acct_wiped": False, "acct_dip": 200.0, "acct_max_units": 2}
    # and scaled down when the run it comes from traded more units than this account would
    r = metrics.replay_account(none, 2000.0, 2500.0, 10, open_profit=-90.0, open_mae=-300.0, open_units=3)
    assert r == {"acct_net": -30.0, "acct_wiped": False, "acct_dip": 100.0, "acct_max_units": 1}


def test_a_run_reports_the_worst_floating_loss_of_the_basket_it_ends_in(live_cfg, engine_run, prepared):
    """The replay needs it: a window that ends inside a basket knows the basket's end mark and how deep it had been."""
    seen = 0
    for symbol in ("XAUUSDm", "BTCUSDm"):
        cfg = live_cfg(symbol, fixed_units=1, initial_balance=1_000_000.0, open_order_delay_ms=100)
        whole = engine_run(cfg, mode="ticks", trace=True)
        tr = whole.trace
        for _, b in whole.baskets.iterrows():
            a, z = int(b["open_time"].value // 1_000_000), int(b["close_time"].value // 1_000_000)
            inside = tr[(tr[:, K.T_T] > a) & (tr[:, K.T_T] < z) & (tr[:, K.T_NPOS] > 0)]
            if len(inside) < 20:
                continue
            cut = int(inside[len(inside) // 2, K.T_T]) + 1                 # just after a poll in the middle of the basket
            part = engine_run(cfg.replace(end=str(pd.Timestamp(cut, unit="ms"))), mode="ticks", trace=True)
            sc = part.scalars
            assert sc["open_positions_at_end"] > 0 and sc["open_units_at_end"] == 1
            lows = part.trace[(part.trace[:, K.T_T] > a) & (part.trace[:, K.T_NPOS] > 0), K.T_PROFIT]
            assert sc["open_mae_at_end"] == pytest.approx(min(float(lows.min()), 0.0), abs=1e-9)
            row = metrics.score_row(part)
            closed = part.baskets["pnl"].sum()
            assert row["acct_net"] == pytest.approx(closed + sc["open_profit_at_end"], abs=0.011)
            worst = min(sc["open_mae_at_end"], sc["open_profit_at_end"], 0.0)
            assert row["acct_dip"] >= round(-(part.baskets["pnl"].sum() + worst), 2) - 0.011
            # an account that small could not have carried the basket to this point
            if worst < -0.05:
                tiny = metrics.score_row(part, account=round(-worst * 0.98 + max(-closed, 0.0), 2))
                assert tiny["acct_wiped"]
            seen += 1
            break
    assert seen, "no fixture basket is long enough to end a window inside it"
    flat = engine_run(live_cfg("BTCUSDm", end="2026-11-09 06:00:30"), mode="ticks")
    if flat.scalars["open_positions_at_end"] == 0:
        assert flat.scalars["open_mae_at_end"] == 0.0 and flat.scalars["open_units_at_end"] == 0


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
        # the equity series ends with the account as the stop-out left it, at the moment it happened
        last = res.equity.iloc[-1]
        assert last["balance"] == last["equity"] == res.scalars["final_balance"] and last["n_pos"] == 0 and last["lots"] == 0
        assert int(pd.Timestamp(last["time"]).value // 1_000_000) == int(res.scalars["last_poll_ms"])
        assert res.equity["time"].is_monotonic_increasing
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


def test_a_run_started_in_the_minute_of_the_reopen_counts_from_the_first_quote(live_cfg, live_root, gold_break):
    """Started before that minute's first quote, the close-only period still runs from the quote, not from the minute."""
    g = gold_break
    start_ms = g["first"] - g["first"] % 1000                       # the second of the first quote: at or before it
    cfg = live_cfg(g["symbol"], start=str(pd.Timestamp(start_ms, unit="ms")), open_order_delay_ms=100)
    prep = fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="ticks", store_dir=g["store"])
    ends = [int(z) for a, z in prep.gaps if z - a >= K.SESSION_BREAK_MS]
    assert ends and ends[-1] == g["first"], "the break before the start must end at its first quote"
    res = fast.run(cfg, prep)
    opens = res.fills[res.fills["action"] == "open"]["time"].astype("int64") // 1_000_000
    assert not (opens < g["first"] + int(cfg.close_only_after_break_s * 1000)).any()
    rep = check_parity(live_cfg(g["symbol"], start=cfg.start), live_root=live_root, store_dir=g["store"])
    assert rep.ok, str(rep)
    assert rep.refused_ref.get("close_only", 0) == res.counters["polls_order_blocked_close_only"]


def test_a_window_that_ends_inside_a_closure_ends_its_session_with_its_last_quote(live_cfg, live_root, gold_break):
    """
    Prepared on its own, a window that stops a few minutes into a break has no later row to show that
    the session ended. The time of the next quote in the history is looked up instead, so the same
    orders are refused as when the window is cut out of a longer one, and the live loop agrees.
    """
    g = gold_break
    assert fast._next_quote_ms(g["symbol"], g["last"] + 1, g["store"]) // 1000 == g["first"] // 1000
    far = _ms("2027-01-01")
    assert fast._next_quote_ms(g["symbol"], far, g["store"]) == far      # the history stops: nothing is known to follow
    end = str(pd.Timestamp(g["last"] - g["last"] % 1000 + 300_000, unit="ms"))       # five minutes into the break
    cfg = live_cfg(g["symbol"], open_order_delay_ms=100)
    long_prep = fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="ticks", store_dir=g["store"])
    cut = fast.run(cfg.replace(end=end), long_prep)
    own_prep = fast.prepare(cfg.symbol, cfg.start, end, cfg.timeframes(), mode="ticks", store_dir=g["store"])
    assert own_prep.t_ms[-1] == g["last"] and own_prep.after_ms // 1000 == g["first"] // 1000
    own = fast.run(cfg.replace(end=end), own_prep)
    pd.testing.assert_frame_equal(own.fills, cut.fills)
    # (one diagnostic differs by design: the jump over the closure is only counted when there are rows to jump to)
    skip = {"dead_market_skips"}
    assert {k: v for k, v in own.counters.items() if k not in skip} == {k: v for k, v in cut.counters.items() if k not in skip}
    t = own.fills["time"].astype("int64") // 1_000_000
    assert not (t > g["last"] + K.SESSION_CLOSE_GRACE_MS).any()
    if g["wanted"]:
        assert own.counters["orders_refused_market_closed"] > 0
    rep = check_parity(live_cfg(g["symbol"], end=end), live_root=live_root, store_dir=g["store"])
    assert rep.ok, str(rep)
    assert rep.refused_ref.get("market_closed", 0) == own.counters["orders_refused_market_closed"]


def test_with_latency_the_broker_judges_the_order_when_it_arrives(live_cfg, fixture_store, tmp_path, windows):
    """
    An order decided within a second of a session's last quote is in time; delayed by latency until
    more than a second after that quote it reaches a closed market and is refused.
    """
    symbol = "BTCUSDm"
    cfg = live_cfg(symbol, open_order_delay_ms=100)
    tfs = cfg.timeframes()
    plain = fast.run(cfg, fast.prepare(symbol, cfg.start, cfg.end, tfs, mode="ticks", store_dir=fixture_store))
    first_open = plain.fills[plain.fills["action"] == "open"].iloc[0]
    t0 = int(first_open["time"].value // 1_000_000)                  # no order before it: the poll grid is untouched
    assert t0 + (BREAK_S + 120) * 1000 < _ms(windows[symbol][1])
    _cut(fixture_store, tmp_path, symbol, t0 + 1, t0 + 1 + BREAK_S * 1000)
    ticks = store.load_ticks(symbol, _ms(windows[symbol][0]), _ms(windows[symbol][1]), tmp_path)
    last = int(ticks["t_ms"][ticks["t_ms"] <= t0][-1])
    age = t0 - last
    assert 0 <= age < 1000, "the entry itself must be in time"
    prep = fast.prepare(symbol, cfg.start, cfg.end, tfs, mode="ticks", store_dir=tmp_path)

    def first_fill(latency_ms):
        res = fast.run(cfg.replace(latency_ms=latency_ms), prep)
        f = res.fills[res.fills["action"] == "open"]
        return (int(f.iloc[0]["time"].value // 1_000_000) if len(f) else None), res.counters["orders_refused_market_closed"]

    assert first_fill(0) == (t0, 0)
    in_time = 1000 - age                                             # arrives exactly a second after the last quote
    assert first_fill(in_time)[0] == t0                              # (a fill is stamped with the pass that decided it)
    late, refused = first_fill(in_time + 1)                          # one millisecond later the session has ended
    assert refused > 0 and (late is None or late > t0 + BREAK_S * 1000)


def test_per_second_series_warns_about_timings_it_cannot_carry(live_cfg, fixture_store):
    cfg = live_cfg("BTCUSDm")
    prep = fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="sec", store_dir=fixture_store)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fast.run(cfg, prep)                                             # whole seconds everywhere: silent
    for bad in (dict(open_order_delay_ms=100), dict(latency_ms=300), dict(poll_interval_ms=1250), dict(poll_jitter_ms=200),
                dict(poll_jitter_ms=1000)):          # a jitter is an upper bound: 1000 ms moves polls off the grid as well
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
