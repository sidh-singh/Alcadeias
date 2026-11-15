"""
The regime filter of the fast engine (``fast.run(..., regime=(times_ms, values))``): a backtest-only entry filter
computed outside the kernel (for example the daily close against its 200-day average). From ``times_ms[i]`` on the
regime is ``values[i]``; a new basket opens only in its direction, and 0 allows none. Adds and exits are not filtered.

Pinned down against the direction switches the suite already tests (``allow_long`` / ``allow_short``): a regime that
is +1 throughout must be the long-only run fill for fill, -1 throughout the short-only run, and a regime that changes
must give, at every open, the direction in force at that moment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.engine import fast

SYMBOLS = ("XAUUSDm", "BTCUSDm")
ALL_TFS = ("M1", "M5", "M15", "H1", "H4")
# many baskets in both directions inside the fixture windows (as in test_lever_rules)
QUICK = dict(open_weights={"M1": 1}, fc_weights={"M1": 1}, reentry_cooldown_s=5.0, fixed_units=2, initial_balance=1e6,
             rsi_oversold=45.0, rsi_overbought=55.0)


def _run(prepared, cfg, regime=None):
    from backtesting.config import TF_SECONDS
    tfs = tuple(sorted(set(ALL_TFS) | set(cfg.timeframes()), key=TF_SECONDS.get))
    prep = prepared(cfg.symbol, mode="ticks", tfs=tfs)
    return fast.run(cfg, prep, regime=regime)


def _ms(times) -> np.ndarray:
    return np.asarray([pd.Timestamp(x).value // 1_000_000 for x in times], np.int64)


def _whole(cfg, value: int):
    from backtesting.data import store
    return np.asarray([store.to_ms(cfg.start) - 86_400_000], np.int64), np.asarray([value], np.int64)


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("value,switch", [(1, "allow_short"), (-1, "allow_long")])
def test_a_constant_regime_is_the_one_direction_run(live_cfg, prepared, symbol, value, switch):
    cfg = live_cfg(symbol, **QUICK)
    free = _run(prepared, cfg)
    assert set(free.baskets["side"]) == {"BUY", "SELL"}           # the window trades both ways unfiltered
    reg = _run(prepared, cfg, regime=_whole(cfg, value))
    one = _run(prepared, cfg.replace(**{switch: False}))
    pd.testing.assert_frame_equal(reg.fills.reset_index(drop=True), one.fills.reset_index(drop=True))
    assert set(reg.baskets["side"]) == {"BUY" if value == 1 else "SELL"}
    assert reg.counters["polls_entry_blocked_regime"] > 0
    assert one.counters["polls_entry_blocked_regime"] == 0 and free.counters["polls_entry_blocked_regime"] == 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_a_zero_regime_opens_nothing(live_cfg, prepared, symbol):
    cfg = live_cfg(symbol, **QUICK)
    res = _run(prepared, cfg, regime=_whole(cfg, 0))
    assert len(res.baskets) == 0 and len(res.fills) == 0
    assert res.counters["polls_entry_blocked_regime"] > 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_before_the_first_regime_time_nothing_opens(live_cfg, prepared, symbol):
    """Before the first value is known the regime is 0: a series that starts late blocks the opening stretch."""
    cfg = live_cfg(symbol, **QUICK)
    free = _run(prepared, cfg)
    t = free.baskets["open_time"].sort_values()
    late = t.iloc[len(t) // 2]
    res = _run(prepared, cfg, regime=(_ms([late]), np.asarray([1], np.int64)))
    assert len(res.baskets) and (_ms(res.baskets["open_time"]) >= _ms([late])[0] - 2000).all()


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_a_changing_regime_is_followed_from_the_moment_it_changes(live_cfg, prepared, symbol):
    cfg = live_cfg(symbol, **QUICK)
    free = _run(prepared, cfg)
    t0, t1 = free.baskets["open_time"].min(), free.baskets["open_time"].max()
    # switch every few minutes between long, short and neither
    edges = pd.date_range(t0 - pd.Timedelta(minutes=1), t1, freq="7min")
    values = np.resize(np.asarray([1, -1, 0], np.int64), len(edges))
    ms = (edges.asi8 // 1_000_000).astype(np.int64)
    res = _run(prepared, cfg, regime=(ms, values))
    b = res.baskets
    assert len(b) >= 3
    t_open = _ms(b["open_time"])
    # the order is decided on a poll and filled a moment later: leave out opens within 2 s of a change
    near = np.abs(t_open[:, None] - ms[None, :]).min(axis=1) < 2000
    i = np.searchsorted(ms, t_open, side="right") - 1
    in_force = np.where(i >= 0, values[np.maximum(i, 0)], 0)
    want = np.where(b["side"].to_numpy() == "BUY", 1, -1)
    assert (in_force[~near] == want[~near]).all()     # every basket opened in the direction in force when it opened
    assert set(b["side"]) == {"BUY", "SELL"}
    assert (in_force[~near] != 0).all()               # and none while the regime allowed neither


@pytest.mark.parametrize("bad", [
    (np.asarray([2, 1], np.int64), np.asarray([1, 1], np.int64)),          # times not ascending
    (np.asarray([1, 2], np.int64), np.asarray([1], np.int64)),             # lengths differ
    (np.asarray([1, 2], np.int64), np.asarray([1, 2], np.int64)),          # a value other than -1 / 0 / +1
])
def test_a_malformed_regime_is_refused(live_cfg, prepared, bad):
    cfg = live_cfg("XAUUSDm", **QUICK)
    with pytest.raises(ValueError):
        _run(prepared, cfg, regime=bad)
