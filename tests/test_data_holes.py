"""
Holes in the tick history.

BTC trades around the clock, so hours without a tick in its history are missing data, not
a closed market (the Exness archive lacks 30 Aug 2025, 30-31 Mar 2026 and the evening of
30 Nov 2025). Replayed naively the bot would be frozen for the missing time and whatever it
holds would be handed the whole price change in one jump. The engine instead closes the
open basket at the last quote before the hole and keeps fresh entries out for a while
after the history resumes. These tests cut a hole into the bundled real ticks.
"""

from __future__ import annotations

import shutil

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.engine import fast

SYMBOL = "BTCUSDm"
HOLE_S = 15 * 60            # length of the hole cut into the fixture
LEVER = dict(data_hole_s=600.0, data_hole_quarantine_s=600.0)     # 10 minutes of silence = a hole; 10 minutes out afterwards
COLS = ["time", "action", "side", "lots", "price", "profit", "reason", "units"]


def _ms(ts) -> int:
    return int(pd.Timestamp(ts).value // 1_000_000)


def _prep(cfg, store_dir, start=None, end=None):
    return fast.prepare(cfg.symbol, start or cfg.start, end or cfg.end, cfg.timeframes(), mode="ticks", store_dir=store_dir)


@pytest.fixture(scope="module")
def plain(live_cfg, fixture_store):
    cfg = live_cfg(SYMBOL, open_order_delay_ms=100, **LEVER)
    return cfg, fast.run(cfg, _prep(cfg, fixture_store))


@pytest.fixture(scope="module")
def holed(plain, fixture_store, tmp_path_factory, windows):
    """A copy of the fixture store with 15 minutes of ticks removed while a basket is open."""
    cfg, res = plain
    a, z = (_ms(x) for x in windows[SYMBOL])
    b = res.baskets
    ok = b[(b["duration_s"] >= 60) & (b["open_time"].dt.as_unit("ns").astype("int64") // 1_000_000 <= z - (HOLE_S + 900 + 300) * 1000)]
    assert len(ok), "the fixture hour has no basket early and long enough to cut a hole into"
    hole_a = int(ok.iloc[0]["open_time"].value // 1_000_000) + 20_000
    hole_b = hole_a + HOLE_S * 1000
    root = tmp_path_factory.mktemp("holed_store")
    shutil.copytree(fixture_store / SYMBOL, root / SYMBOL)
    for d in sorted((root / SYMBOL).iterdir()):
        for kind, key, scale in (("ticks", "t_ms", 1), ("sec", "t_ms", 1), ("m1", "t", 1000)):
            f = d / f"{kind}.npz"
            x = dict(np.load(f))
            t = x[key].astype(np.int64) * scale
            if kind == "m1":            # drop the bars that lie wholly inside the hole
                gone = (t >= ((hole_a // 60_000) + 1) * 60_000) & (t + 60_000 <= hole_b)
            else:
                gone = (t >= hole_a) & (t < hole_b)
            np.savez_compressed(f, **{k: v[~gone] for k, v in x.items()})
    ticks = store.load_ticks(SYMBOL, a, z, root)
    before = ticks["t_ms"] < hole_a
    last = int(np.flatnonzero(before)[-1])
    return dict(store=root, a=hole_a, b=hole_b, basket=ok.iloc[0], last_t=int(ticks["t_ms"][last]),
                last_bid=float(ticks["bid"][last]), last_ask=float(ticks["ask"][last]),
                first_after=int(ticks["t_ms"][last + 1]))


def test_inert_when_the_history_has_no_hole(plain, live_cfg, fixture_store):
    cfg, res = plain
    off = fast.run(cfg.replace(data_hole_s=0.0), _prep(cfg, fixture_store))
    pd.testing.assert_frame_equal(res.fills, off.fills)
    assert res.counters["closes_data_hole"] == 0 and res.counters["polls_entry_blocked_data_hole"] == 0
    # and gold, which has real closures, never uses it unless told to
    assert live_cfg("XAUUSDm").effective_data_hole_s == 0.0 and live_cfg(SYMBOL).effective_data_hole_s == 3 * 3600.0


def test_the_open_basket_is_closed_at_the_last_quote_before_the_hole(plain, holed):
    cfg, full = plain
    res = fast.run(cfg, _prep(cfg, holed["store"]))
    f, b = res.fills, res.baskets
    # everything before the hole is untouched
    t = f["time"].dt.as_unit("ns").astype("int64") // 1_000_000
    tf = full.fills["time"].dt.as_unit("ns").astype("int64") // 1_000_000
    pd.testing.assert_frame_equal(f[t < holed["a"]][COLS].reset_index(drop=True),
                                  full.fills[tf < holed["a"]][COLS].reset_index(drop=True))
    gone = b[b["reason"] == "data_hole"]
    assert len(gone) == 1 and res.counters["closes_data_hole"] == 1
    g = gone.iloc[0]
    assert g["side"] == holed["basket"]["side"]
    closes = f[(f["action"] == "close") & (f["reason"] == "data_hole")]
    assert len(closes) == g["n_pos"] and closes["lots"].sum() == pytest.approx(g["lots"])
    # at the last quote that exists: a long is sold at the bid, a short bought back at the ask
    want = holed["last_bid"] if g["side"] == "BUY" else holed["last_ask"]
    assert np.allclose(closes["price"].to_numpy(), want, rtol=0, atol=1e-9)
    assert (closes["fill_time"].dt.as_unit("ns").astype("int64") // 1_000_000 == holed["last_t"]).all()
    # decided on the first poll the market counts as not live, not later: more than three minutes after that
    # quote's whole second (MT5 reports tick.time in seconds, and that is what the liveness rule reads)
    waited = (g["close_time"].value // 1_000_000) - (holed["last_t"] // 1000) * 1000
    assert 180_000 < waited <= 182_000
    # the basket's P/L is what it stood at on that quote: nothing of the missing minutes is booked
    assert g["pnl"] == pytest.approx(g["profit_seen"], abs=0.011)


def test_no_fresh_entry_during_the_quarantine(plain, holed):
    cfg, _ = plain
    res = fast.run(cfg, _prep(cfg, holed["store"]))
    opens = res.fills[res.fills["action"] == "open"]["time"].dt.as_unit("ns").astype("int64") // 1_000_000
    resume = holed["first_after"]
    assert not ((opens > holed["a"]) & (opens < resume + 600_000)).any()
    # with the quarantine switched off (but the hole still recognised) the bot may trade again at once
    free = fast.run(cfg.replace(data_hole_quarantine_s=0.0), _prep(cfg, holed["store"]))
    o2 = free.fills[free.fills["action"] == "open"]["time"].dt.as_unit("ns").astype("int64") // 1_000_000
    if ((o2 >= resume) & (o2 < resume + 600_000)).any():
        assert res.counters["polls_entry_blocked_data_hole"] > 0


def test_switched_off_the_basket_is_carried_across(plain, holed):
    cfg, _ = plain
    res = fast.run(cfg.replace(data_hole_s=0.0), _prep(cfg, holed["store"]))
    assert not (res.baskets["reason"] == "data_hole").any() and res.counters["closes_data_hole"] == 0
    b = res.baskets
    t0 = holed["basket"]["open_time"]
    same = b[b["open_time"] == t0]
    # the basket that was open is closed only after the history resumes (or is still open at the end)
    assert len(same) == 0 or (same.iloc[0]["close_time"].value // 1_000_000) >= holed["first_after"]


def test_a_run_that_starts_just_after_a_hole_still_waits(plain, holed):
    """The hole lies in the warm-up history of this run; its quarantine must still hold."""
    cfg, _ = plain
    start = str(pd.Timestamp(holed["first_after"], unit="ms").floor("s") + pd.Timedelta(seconds=1))
    c = cfg.replace(start=start)
    prep = _prep(c, holed["store"])
    assert any((z - a) >= 600_000 and z <= store.to_ms(start) for a, z in prep.gaps), prep.gaps
    res = fast.run(c, prep)
    opens = res.fills[res.fills["action"] == "open"]["time"].dt.as_unit("ns").astype("int64") // 1_000_000
    assert not (opens < holed["first_after"] + 600_000).any()
    off = fast.run(c.replace(data_hole_s=0.0), prep)
    o2 = off.fills[off.fills["action"] == "open"]["time"].dt.as_unit("ns").astype("int64") // 1_000_000
    if (o2 < holed["first_after"] + 600_000).any():
        assert res.counters["polls_entry_blocked_data_hole"] > 0


def test_parity_configuration_never_uses_it(live_cfg):
    from backtesting.engine.parity import fast_config_for_parity
    assert fast_config_for_parity(live_cfg(SYMBOL)).effective_data_hole_s == 0.0
