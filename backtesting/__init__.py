"""
Alcadeias backtesting suite
===========================

A tick-accurate backtester for the live RSI+MACD slope strategy in this repo.

It replays real Exness tick history (the same `XAUUSDm` / `BTCUSDm` symbols the live
bot trades) through the *same decision logic* the live loop in ``app.py`` runs, with a
simulated MT5 account (bid/ask fills, floating P/L, margin, stop-out).

Two engines share one configuration object:

* ``backtesting.engine.reference`` drives the repo's real ``strategy.py`` and
  ``indicator.py`` through a simulated MT5 terminal. Slow, but it *is* the live code.
* ``backtesting.engine.fast`` is a numba re-implementation used for full-period runs
  and parameter sweeps. The test-suite proves it bit-for-bit against the reference.

Entry point: ``python -m backtesting --help``.
"""

__version__ = "1.0.0"
