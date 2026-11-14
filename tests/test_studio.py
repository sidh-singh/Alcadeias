"""
The replay studio: what is shown must be what the backtest did.

A replay runs the kernel again over a short window. A fresh run starts flat with no
cooldown pending, so ``replay.replay_window`` has to anchor it on a poll where the full
run was in exactly that state. These tests pin that the replay then makes the same fills
as the full-period run, that a frame never draws data from after the playhead, and that
the Dash layout builds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.engine import fast
from backtesting.viz import replay as R

SYMBOL = "BTCUSDm"
COLS = ["time", "action", "side", "lots", "price", "profit", "reason", "units"]


@pytest.fixture(scope="module")
def full(live_cfg, fixture_store):
    cfg = live_cfg(SYMBOL)
    prep = fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), mode="sec", store_dir=fixture_store)
    return fast.run(cfg, prep), prep


def _ms(ts) -> int:
    return int(pd.Timestamp(ts).value // 1_000_000)


def _expected(full_res, w: R.ReplayWindow) -> pd.DataFrame:
    f = full_res.fills
    t = f["time"].astype("int64") // 1_000_000
    return f[(t >= w.anchor_ms) & (t < w.end_ms)].reset_index(drop=True)


@pytest.mark.parametrize("frac", [0.0, 0.2, 0.45, 0.7, 0.9])  # 0.0 = a window anchored on the run's first poll
def test_replay_makes_the_same_fills_as_the_full_run(full, fixture_store, frac):
    res, prep = full
    a, z = _ms(res.cfg.start), _ms(res.cfg.end)
    when = a + int((z - a) * frac)
    w = R.replay_window(res, when, span_s=900)
    assert w.anchor_ms <= w.visible_from_ms <= w.end_ms and w.kind in ("basket_open", "flat", "run_start")
    exp = _expected(res, w)
    for kw in (dict(prep=prep), dict(store_dir=fixture_store)):          # bit-identical inputs, and a freshly prepared window
        rr = R.run_replay(w, **kw)
        got = rr.fills.reset_index(drop=True)
        assert len(got) == len(exp)
        if len(exp) == 0:                      # a quiet stretch: nothing to compare beyond "no fills"
            continue
        pd.testing.assert_frame_equal(got[COLS], exp[COLS], check_exact=False, atol=1e-9)
        # basket numbering continues from the full run
        assert (got["basket"] + w.basket_base).tolist() == exp["basket"].tolist()


def test_a_basket_window_puts_the_playhead_on_its_entry(full):
    res, prep = full
    b = res.baskets.iloc[len(res.baskets) // 2]
    w, playhead = R.window_for_basket(res, int(b["basket"]))
    assert playhead == _ms(b["open_time"])
    assert w.visible_from_ms <= playhead < w.end_ms
    rr = R.run_replay(w, prep=prep)
    pd.testing.assert_frame_equal(rr.fills.reset_index(drop=True)[COLS], _expected(res, w)[COLS],
                                  check_exact=False, atol=1e-9)
    nxt = R.neighbour_basket(res, playhead, +1)
    assert nxt is None or nxt[1] > playhead


def test_frames_only_show_the_past(full, fixture_store):
    """Candles, the account state and the event log at a playhead use nothing from after it."""
    res, prep = full
    b = res.baskets.iloc[0]
    w, playhead = R.window_for_basket(res, int(b["basket"]))
    s = R.ReplaySession.build(w, prep=prep, store_dir=fixture_store)
    assert s.n > 0
    last_close = []
    for dt in (0, 5_000, 30_000, 120_000, 400_000):
        t = s.clamp(playhead + dt)
        c = s.candles(t, "M1")
        assert len(c["t"]) <= R.N_CANDLES
        assert int(c["t"][-1]) * 1000 <= t                                 # the forming candle opened before the playhead
        row = s.row_index(t)
        assert c["c"][-1] == pytest.approx(float(s._row_bid[row]))         # ... and closes at the latest bid seen
        last_close.append(float(c["c"][-1]))
        st = s.state(t)
        assert st["t_ms"] <= t if "t_ms" in st else True
        assert all(ev["t_ms"] <= t for ev in s.recent_events(t))
        fig = s.figure(t, "M1")
        assert fig["data"] and fig["layout"]
    assert len(set(last_close)) > 1, "the forming candle must move as the playhead advances"
    # stepping moves by whole polls and never leaves the window
    assert s.step(playhead, 1) > playhead and s.step(playhead, -10_000_000) == s.vis_ms


def test_studio_layout_builds_and_runs_a_backtest(fixture_store, windows):
    from backtesting.viz import studio as S

    app = S.create_app(fixture_store)
    layout = app.layout() if callable(app.layout) else app.layout
    ids = set()

    def walk(node):
        if isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
            return
        i = getattr(node, "id", None)
        if isinstance(i, str):
            ids.add(i)
        kids = getattr(node, "children", None)
        if kids is not None:
            walk(kids)

    walk(layout)
    assert {"ctl-symbol", "ctl-dates", "ctl-balance", "tabs", "mk-graph", "tbl", "rp-graph", "rp-panel"} <= ids

    studio = app.studio
    a, z = windows[SYMBOL]
    cfg, warns = studio.build_config(SYMBOL, a[:10], z[:10], 2000.0, None)[:2]
    entry = studio.run(cfg.replace(start=a, end=z), warns)
    assert len(entry.result.baskets) > 0
    data, pages, _ = studio.table_page(entry.id, page=0)[:3]
    assert len(data) > 0 and pages >= 1
