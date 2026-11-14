"""
Shared fixtures for the backtester test-suite.

What the suite runs against
---------------------------
* The backtesting package of this repository (``backtesting/``).
* The LIVE trading code: ``strategy.py``, ``indicator.py``, ``app.py``, ``mt5_helper.py``,
  ``constants.py`` and ``symbols.json``. By default these are the files in this
  repository; set ``ALCADEIAS_LIVE_ROOT=/path/to/another/checkout`` to test the
  backtester against the live files of a different deployment branch (for example a
  ``git worktree`` of a ``netting_*`` branch) without switching branches here.
* ``tests/fixtures/store``: a miniature tick store cut from real Exness ticks by
  ``tests/make_fixtures.py`` (BTCUSDm 2026-11-09 06:00..07:00 UTC and XAUUSDm
  2026-11-11 15:00..15:45 UTC, each with 12 days of M1 warm-up history).

Ground rules enforced here
--------------------------
* No network: any attempt to open a socket connection fails the test that made it.
* Nothing is written outside pytest's ``tmp_path`` by the tests themselves.
* Every random number comes from a ``numpy`` generator with a literal seed.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = Path(os.environ.get("ALCADEIAS_LIVE_ROOT") or REPO_ROOT).resolve()
FIXTURE_STORE = REPO_ROOT / "tests" / "fixtures" / "store"

# symbol -> (window start, window end), UTC. Must match tests/make_fixtures.py.
FIXTURE_WINDOWS = {
    "XAUUSDm": ("2026-11-11 15:00", "2026-11-11 15:45"),
    "BTCUSDm": ("2026-11-09 06:00", "2026-11-09 07:00"),
}
# every timeframe the live configuration reads (slope sections + the RSI ladder tiers)
ALL_TFS = ("M1", "M5", "M15", "H1", "H4")


def _put_first_on_sys_path(path: Path) -> None:
    p = str(path)
    while p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)


# `import backtesting` comes from this repository; `import strategy / indicator / constants`
# must come from LIVE_ROOT, so LIVE_ROOT goes in front.
_put_first_on_sys_path(REPO_ROOT)
_put_first_on_sys_path(LIVE_ROOT)


def pytest_report_header(config):
    import strategy  # the live module under test

    variant = "netting" if hasattr(strategy, "BOOK_SCORE_WEIGHTS") else "hedging"
    return [f"live code under test: {LIVE_ROOT} ({variant} variant)",
            f"fixture tick store: {FIXTURE_STORE}"]


@pytest.fixture(autouse=True, scope="session")
def _no_network():
    """The suite must never touch the network (the tick downloader is not under test)."""

    def _blocked(self, *args, **kwargs):
        raise RuntimeError("network access is not allowed in the test-suite")

    mp = pytest.MonkeyPatch()
    mp.setattr(socket.socket, "connect", _blocked)
    mp.setattr(socket.socket, "connect_ex", _blocked)
    yield
    mp.undo()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def live_root() -> Path:
    """Directory holding the live trading code the backtester is checked against."""
    return LIVE_ROOT


@pytest.fixture(scope="session")
def fixture_store() -> Path:
    if not (FIXTURE_STORE / "XAUUSDm").is_dir() or not (FIXTURE_STORE / "BTCUSDm").is_dir():
        pytest.fail(f"fixture store missing at {FIXTURE_STORE}; rebuild it with `python tests/make_fixtures.py`")
    return FIXTURE_STORE


@pytest.fixture(scope="session")
def windows() -> dict:
    """symbol -> (start, end) of the real-tick fixture windows."""
    return dict(FIXTURE_WINDOWS)


@pytest.fixture(scope="session")
def live_variant() -> str:
    """'hedging' (+$unit target) or 'netting' (slope profit-book), detected from the live strategy.py."""
    import strategy

    return "netting" if hasattr(strategy, "BOOK_SCORE_WEIGHTS") else "hedging"


@pytest.fixture(scope="session")
def live_cfg(live_root, windows):
    """
    Factory: the configuration the live bot runs (constants.py + symbols.json of LIVE_ROOT)
    over the symbol's whole fixture window, with optional overrides.
    """
    from backtesting.config import BacktestConfig

    def make(symbol: str, **overrides):
        start, end = windows[symbol]
        kw = dict(start=start, end=end)
        kw.update(overrides)
        return BacktestConfig.live(symbol, repo_root=live_root, **kw)

    return make


@pytest.fixture(scope="session")
def prepared(fixture_store, windows):
    """
    Factory with a session cache: ``prepared(symbol, mode='ticks', start=None, end=None, tfs=ALL_TFS)``
    -> ``backtesting.engine.fast.Prepared`` on the fixture store. Treat the result as
    read-only; tests that need to alter the data must copy it first.
    """
    from backtesting.engine import fast

    cache = {}

    def get(symbol: str, mode: str = "ticks", start=None, end=None, tfs=ALL_TFS, warm_bars=None):
        a, z = windows[symbol]
        start, end = start or a, end or z
        key = (symbol, mode, str(start), str(end), tuple(tfs), warm_bars)
        if key not in cache:
            kw = {} if warm_bars is None else {"warm_bars": warm_bars}
            cache[key] = fast.prepare(symbol, start, end, list(tfs), mode=mode, store_dir=fixture_store, **kw)
        return cache[key]

    return get


@pytest.fixture(scope="session")
def engine_run(prepared):
    """
    Factory: run the fast engine for ``cfg`` on the fixture store. The data is prepared
    once per (symbol, mode, window) with every live timeframe; the kernel ignores the
    ones a configuration does not use.
    """
    from backtesting.config import TF_SECONDS
    from backtesting.engine import fast

    def run(cfg, mode: str = "ticks", trace: bool = False, light: bool = False):
        tfs = tuple(sorted(set(ALL_TFS) | set(cfg.timeframes()), key=TF_SECONDS.get))
        prep = prepared(cfg.symbol, mode=mode, tfs=tfs)
        return fast.run(cfg, prep, trace=trace, light=light)

    return run
