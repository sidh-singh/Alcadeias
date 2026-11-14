"""
Parity: the fast engine against the REAL live loop.

``check_parity`` replays a window of real ticks through this checkout's own ``app.py``
(``MT5TradingBot.process_symbol`` on a simulated MT5 terminal) and through the numba
kernel, and compares every poll: timestamp, signal, section scores, ladder RSI, position
count, floating profit, unit -- then every fill and the final balance.

If someone edits ``strategy.py`` / ``indicator.py`` / ``app.py`` and the kernel is not
updated to match, these tests fail. They are the reason a fast-engine result can be read
as "what the live bot would have done".
"""

from __future__ import annotations

import pytest

from backtesting.engine.parity import check_parity


def _assert_ok(rep, min_fills: int = 1):
    assert rep.ok, str(rep)
    assert rep.signal_mismatches == 0 and rep.score_mismatches == 0 and rep.fill_mismatches == 0
    assert rep.polls_ref == rep.polls_fast > 0
    assert rep.fills_ref == rep.fills_fast >= min_fills
    assert rep.balance_ref == pytest.approx(rep.balance_fast, abs=0.006)
    assert not rep.ref_errors


@pytest.mark.parametrize("symbol,start,end", [
    ("XAUUSDm", "2026-11-11 15:00", "2026-11-11 15:20"),
    ("BTCUSDm", "2026-11-09 06:00", "2026-11-09 06:20"),
])
def test_fast_engine_matches_the_live_loop(live_cfg, live_root, fixture_store, symbol, start, end):
    """The live configuration on twenty minutes of real ticks: identical decisions and fills."""
    rep = check_parity(live_cfg(symbol, start=start, end=end), live_root=live_root, store_dir=fixture_store)
    _assert_ok(rep)


def test_parity_holds_for_other_settings(live_cfg, live_root, fixture_store, live_variant):
    """
    Different timeframes, thresholds and indicator periods than the live defaults, so the
    comparison is not just a check of one configuration: open on M5+M15, force-close on a
    weighted M1/M5 score, shorter RSI / MACD / pivot settings, a 30 s cooldown.
    """
    over = dict(start="2026-11-09 06:00", end="2026-11-09 06:15",
                open_weights={"M15": 1, "M5": 1}, fc_weights={"M5": 2, "M1": 1},
                entry_s=2.0, entry_agree_s=1.0, force_close_s=3.0, ladder_s=3.0,
                rsi_length=9, macd_fast=8, macd_slow=17, macd_signal=5,
                peak_lookback=12, pivot_width=3, rsi_peak_ob=55.0, rsi_peak_os=45.0,
                rsi_oversold=40.0, rsi_overbought=60.0, reentry_cooldown_s=30.0)
    if live_variant == "netting":
        over.update(book_weights={"M1": 1}, book_s=1.0, profit_protect_usd_per_unit=0.5)
    rep = check_parity(live_cfg("BTCUSDm", **over), live_root=live_root, store_dir=fixture_store)
    _assert_ok(rep)


def test_parity_with_a_larger_unit(live_cfg, live_root, fixture_store):
    """A balance of $5,200 puts the bot on unit 3: every lot, the Fibonacci adds and the profit threshold scale."""
    rep = check_parity(live_cfg("BTCUSDm", start="2026-11-09 06:00", end="2026-11-09 06:20", initial_balance=5200.0),
                       live_root=live_root, store_dir=fixture_store)
    _assert_ok(rep)


def test_parity_on_the_per_second_series(live_cfg, live_root, fixture_store):
    """
    The per-second series keeps every tick a whole-second poll can act on, but the live
    helper sleeps 0.1 s inside buy()/sell(), which moves later polls off whole seconds.
    Both engines are fed the SAME per-second rows here, so they must still agree exactly;
    what this checks is the engines against each other on that input, not sec vs ticks.
    """
    rep = check_parity(live_cfg("XAUUSDm", start="2026-11-11 15:00", end="2026-11-11 15:15"),
                       live_root=live_root, mode="sec", store_dir=fixture_store)
    _assert_ok(rep)


@pytest.mark.slow
@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_fast_engine_matches_the_live_loop_full_window(live_cfg, live_root, fixture_store, symbol):
    """The whole fixture window (45 / 60 minutes): entries, ladder adds, both exit kinds."""
    rep = check_parity(live_cfg(symbol), live_root=live_root, store_dir=fixture_store)
    _assert_ok(rep, min_fills=6)
    seen = set(rep.signals_ref)
    assert seen & {"BUY", "SELL"} and seen & {"CLOSE_BUY", "CLOSE_SELL"}
