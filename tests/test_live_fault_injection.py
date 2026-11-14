"""
Fault injection against the REAL live loop.

These tests run this checkout's own ``app.py`` on the simulated terminal and make the
terminal (or the process) misbehave in one specific way. Each one *demonstrates a known
weakness of the live code as it stands*: the assertion describes what the bot does today,
not what it should do. If the live code is hardened, the matching test will fail -- that
is the signal to turn its assertion around.

1. A single failed ``positions_get`` while a basket is open is read as "flat": the bot
   opens a second, unrelated entry on top of the basket.
2. A process restart forgets the re-entry cooldown: the bot re-enters immediately.
3. A rejected open order is logged as executed and re-sent on every loop.
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd
import pytest

from backtesting.engine import kernels as K
from backtesting.engine.parity import fast_config_for_parity
from backtesting.engine.reference import run_reference

SYMBOL = "BTCUSDm"


def _entry_dir(cfg, open_score, fc_score) -> int:
    if open_score >= cfg.entry_s and fc_score >= cfg.entry_agree_s:
        return 1
    if open_score <= -cfg.entry_s and fc_score <= -cfg.entry_agree_s:
        return -1
    return 0


@pytest.fixture(scope="module")
def trace(live_cfg, engine_run):
    """The fast engine's poll-by-poll view of the fixture hour, on the live loop's cadence."""
    cfg = live_cfg(SYMBOL)
    res = engine_run(fast_config_for_parity(cfg), mode="ticks", trace=True)
    return cfg, res


def _until(cfg, t_ms: int, extra_s: int = 45):
    """The same configuration, ending shortly after t_ms (keeps the slow live replay short)."""
    return cfg.replace(end=str(pd.Timestamp(int(t_ms) + extra_s * 1000, unit="ms")))


def test_failed_position_read_is_treated_as_flat(trace, live_root, fixture_store):
    """
    WEAKNESS (mt5_helper.get_buy_positions / get_sell_positions return None both for "no
    positions" and for "the read failed"; app.py maps None to count 0). One failed read
    while a basket is open and the entry conditions still hold -> the bot believes it is
    flat and sends a brand-new entry order on top of the open basket.
    """
    cfg, res = trace
    tr = res.trace
    t_fail = None
    for row in tr:
        if (row[K.T_NPOS] != 0 and row[K.T_SIGNAL] == 0 and row[K.T_ENTRY_ALLOWED] == 1 and row[K.T_BRAKE] == 0
                and _entry_dir(cfg, row[K.T_OPEN_SCORE], row[K.T_FC_SCORE]) != 0):
            t_fail = int(row[K.T_T])
            break
    assert t_fail is not None, "the fixture hour has no poll with an open basket and a live entry signal"

    def hook(sim, clock):
        real = sim.positions_get

        def flaky(symbol=None, **k):
            return None if clock.now_ms == t_fail else real(symbol=symbol, **k)

        sim.positions_get = flaky

    short = _until(cfg, t_fail)
    clean = run_reference(short, live_root=live_root, store_dir=fixture_store)
    fault = run_reference(short, live_root=live_root, store_dir=fixture_store, hook=hook)

    opened_then = lambda r: r.deals[(r.deals["entry"] == "in") & (r.deals["t_ms"] == t_fail)]
    assert len(opened_then(clean)) == 0                       # normally nothing is opened on that poll
    extra = opened_then(fault)
    assert len(extra) == 1, "the live loop opened a second entry because one position read failed"
    assert extra["volume"].iloc[0] == pytest.approx(cfg.mtqty * 1)
    logged = [e for e in fault.events if e["iter_t"] == t_fail and e["event"] in ("BUY_EXECUTED", "SELL_EXECUTED")]
    assert len(logged) == 1


def test_restart_forgets_the_reentry_cooldown(trace, live_root, fixture_store):
    """
    WEAKNESS (app.py keeps ``_last_close_time`` only in process memory). Restarting the bot
    inside the 300 s cooldown after a close lets it re-enter at once, where the running
    process would still be waiting.
    """
    cfg, res = trace
    tr = res.trace
    closes = (res.baskets["close_time"].dt.as_unit("ns").astype("int64") // 1_000_000).to_numpy()
    t_restart = last_close = None
    for row in tr:
        if (row[K.T_NPOS] == 0 and row[K.T_ENTRY_ALLOWED] == 0 and row[K.T_BRAKE] == 0
                and _entry_dir(cfg, row[K.T_OPEN_SCORE], row[K.T_FC_SCORE]) != 0):
            t = int(row[K.T_T])
            prev = closes[closes <= t]
            # leave the running bot a good while still to wait, so the difference is unmistakable
            if len(prev) and (t - prev[-1]) < (cfg.reentry_cooldown_s - 60) * 1000:
                t_restart, last_close = t, int(prev[-1])
                break
    assert t_restart is not None, "the fixture hour has no poll where only the cooldown holds an entry back"

    short = _until(cfg, t_restart, extra_s=20)
    clean = run_reference(short, live_root=live_root, store_dir=fixture_store)
    fault = run_reference(short, live_root=live_root, store_dir=fixture_store, restart_at=[t_restart])

    after = lambda r: r.deals[(r.deals["entry"] == "in") & (r.deals["t_ms"] >= t_restart)]
    assert len(after(clean)) == 0, "the running process is still inside its cooldown"
    again = after(fault)
    assert len(again) >= 1, "the restarted process re-entered although the cooldown had not expired"
    assert (again["t_ms"].iloc[0] - last_close) < cfg.reentry_cooldown_s * 1000
    assert any(e["event"] == "PROCESS_RESTART" for e in fault.events)


def test_rejected_open_is_logged_as_executed_and_resent_every_loop(trace, live_root, fixture_store):
    """
    WEAKNESS (app.py never looks at the order result of an open). While the broker refuses
    new orders the bot writes "BUY_EXECUTED"/"SELL_EXECUTED" on every loop and keeps
    sending the order; no position exists the whole time.
    """
    cfg, res = trace
    first_open = res.fills[res.fills["action"] == "open"].iloc[0]
    t_a = int(first_open["time"].value // 1_000_000)
    t_b = t_a + 12_000                                        # the broker refuses new orders for 12 s

    def hook(sim, clock):
        real = sim.order_send

        def refusing(request):
            if "position" not in request and t_a <= clock.now_ms < t_b:
                return types.SimpleNamespace(retcode=10018, price=0.0, volume=0.0, order=0, deal=0)   # market closed
            return real(request)

        sim.order_send = refusing

    fault = run_reference(_until(cfg, t_b, extra_s=10), live_root=live_root, store_dir=fixture_store, hook=hook)
    said = [e for e in fault.events if e["event"] in ("BUY_EXECUTED", "SELL_EXECUTED") and t_a <= e["iter_t"] < t_b]
    opened = fault.deals[(fault.deals["entry"] == "in") & (fault.deals["t_ms"] >= t_a) & (fault.deals["t_ms"] < t_b)]
    assert len(opened) == 0, "no order was accepted during the refusal window"
    assert len(said) >= 5, "yet the bot logged an executed entry on (almost) every loop"
    assert not fault.errors                                   # and it raised no error at all
