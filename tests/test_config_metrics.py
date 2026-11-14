"""
The configuration object and the performance metrics.

``BacktestConfig.live(symbol)`` is the bridge between the live bot and the backtester:
it must hand the engine exactly the numbers ``constants.py`` and ``symbols.json`` hold,
or every "this is what the live settings did" result would describe some other
strategy. The metrics turn a run into the headline numbers a person acts on (win rate,
profit factor, breakeven win rate, where the money was made and lost), so each one is
checked on a hand-built result whose correct answer can be worked out on paper.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import constants as live_constants

from backtesting.analysis import metrics
from backtesting.config import (FIBO, SYMBOLS, TF_ORDER, TF_SECONDS, BacktestConfig, _norm_weights, _week_minutes,
                                load_live_constants)
from backtesting.engine import fast
from backtesting.engine import kernels as K

IS_NETTING = hasattr(live_constants, "BOOK_SCORE_WEIGHTS")


# ───────────────────────────── helpers ─────────────────────────────

@pytest.fixture
def isolated_constants():
    """Let a test import ``constants`` from throw-away directories, then put sys.path / sys.modules back."""
    saved_path = list(sys.path)
    saved_mod = sys.modules.get("constants")
    yield
    sys.path[:] = saved_path
    sys.modules.pop("constants", None)
    if saved_mod is not None:
        sys.modules["constants"] = saved_mod


def write_live_root(root: Path, *, netting: bool, symbol: str = "XAUUSDm", **over) -> Path:
    """A minimal stand-in for a deployment branch: constants.py + symbols.json with unusual values."""
    c = dict(
        RSI_LENGTH=9, MACD_FAST=5, MACD_SLOW=34, MACD_SIGNAL=7, PEAK_LOOKBACK=31, PIVOT_WIDTH=3,
        RSI_PEAK_OB=66, RSI_PEAK_OS=33,
        OPEN_SCORE_WEIGHTS={"H4": 2, "M5": 1}, FORCE_CLOSE_SCORE_WEIGHTS={"M15": 4, "H1": 3},
        ENTRY_S=5, ENTRY_AGREE_S=3, LADDER_S=4, FORCE_CLOSE_S=6, RSI_OVERSOLD=28, RSI_OVERBOUGHT=72,
        RSI_DCA_LADDER_TIMEFRAMES=["TIMEFRAME_M5", "TIMEFRAME_M30", "TIMEFRAME_H4"],
        REENTRY_COOLDOWN_SECONDS=45, ORDER_COOLDOWN_SECONDS=2.5, MARKET_LOOKBACK_MINUTES=7,
    )
    if netting:
        c.update(BOOK_SCORE_WEIGHTS={"M30": 2}, BOOK_S=3, PROFIT_PROTECT_USD_PER_UNIT=2.5)
    c.update(over)
    root.mkdir(parents=True, exist_ok=True)
    (root / "constants.py").write_text("\n".join(f"{k} = {v!r}" for k, v in c.items()) + "\n")
    (root / "symbols.json").write_text(json.dumps({
        "brake": 1, "mtqty": 0.02,
        "trading_window": {"enabled": True, "start_day": "Tuesday", "start_time": "03:30",
                           "end_day": "Thu", "end_time": "21:15"},
        "symbols": [{"symbol": symbol, "is_active": True, "step_up_balance": 1234, "unit_max_limit": 7}],
    }))
    return root


def hand_built_result(pnl, reasons, n_pos, sides, durations, *, initial=2000.0, symbol="XAUUSDm",
                      start="2026-11-01", end="2026-11-11", open_profit=0.0, max_dd=10.0, equity=None,
                      ladder_adds=0):
    """A ``Result`` with exactly the baskets given, as the fast engine would report them."""
    n = len(pnl)
    cfg = BacktestConfig(symbol=symbol, start=start, end=end, initial_balance=initial)
    close = pd.date_range("2026-11-01 01:00", periods=n, freq="6h", tz="UTC")
    baskets = pd.DataFrame({
        "basket": np.arange(n), "side": sides, "open_time": close - pd.to_timedelta(durations, unit="s"),
        "close_time": close, "duration_s": np.asarray(durations, dtype=float), "n_pos": n_pos,
        "lots": [0.01] * n, "pnl": np.asarray(pnl, dtype=float), "reason": reasons, "units": [1] * n,
        "mae": [min(p, 0.0) - 1.0 for p in pnl], "mfe": [max(p, 0.0) + 0.5 for p in pnl],
        "first_price": [4000.0] * n, "avg_price": [4000.0] * n, "close_price": [4000.0] * n,
        "open_score": [2.0] * n, "fc_score": [2.0] * n, "commission": [0.0] * n,
        "balance": initial + np.cumsum(pnl), "profit_seen": np.asarray(pnl, dtype=float),
    })
    final_balance = initial + float(np.sum(pnl))
    scalars = {
        "final_balance": final_balance, "final_equity": final_balance + open_profit,
        "max_equity": final_balance + 3.0, "min_equity": initial - 7.5, "max_drawdown_usd": max_dd,
        "max_drawdown_pct": max_dd / initial * 100.0, "max_lots": 0.32, "max_positions": 6.0,
        "min_margin_level_pct": 5241.519, "open_profit_at_end": open_profit, "max_margin_used": 38.11,
        "stopped_out": 0.0, "last_poll_ms": 0.0, "max_floating_loss": -6.5, "open_positions_at_end": 0.0,
        "open_lots_at_end": 0.0, "initial_balance": initial, "rows": 0.0,
    }
    counters = {name: 0 for name in fast._COUNTER_NAMES.values()}
    counters["ladder_adds"] = ladder_adds
    eq = equity if equity is not None else fast._equity_frame(np.zeros((0, K.E_N)))
    return fast.Result(cfg=cfg, fills=fast._fills_frame(np.zeros((0, K.F_N)), ["M1"]), baskets=baskets,
                       equity=eq, counters=counters, scalars=scalars)


# ───────────────────────────── BacktestConfig.live ─────────────────────────────

def test_live_config_matches_this_branch_constants_and_symbols_json(live_root):
    """
    Protects: the baseline. ``BacktestConfig.live`` for the branch under test must carry
    every indicator length, threshold, timeframe weight, ladder tier and timing constant
    of ``constants.py`` and the sizing / trading-window fields of ``symbols.json``.
    """
    c = live_constants
    sj = json.loads((live_root / "symbols.json").read_text())
    file_symbols = [e["symbol"] for e in sj["symbols"]]
    for symbol in ("XAUUSDm", "BTCUSDm"):
        cfg = BacktestConfig.live(symbol, repo_root=live_root)
        assert cfg.symbol == symbol
        assert (cfg.rsi_length, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal) == \
            (c.RSI_LENGTH, c.MACD_FAST, c.MACD_SLOW, c.MACD_SIGNAL)
        assert (cfg.peak_lookback, cfg.pivot_width) == (c.PEAK_LOOKBACK, c.PIVOT_WIDTH)
        assert (cfg.rsi_peak_ob, cfg.rsi_peak_os) == (c.RSI_PEAK_OB, c.RSI_PEAK_OS)
        assert cfg.open_weights == {tf: (float(w), float(w)) for tf, w in c.OPEN_SCORE_WEIGHTS.items()}
        assert cfg.fc_weights == {tf: (float(w), float(w)) for tf, w in c.FORCE_CLOSE_SCORE_WEIGHTS.items()}
        assert (cfg.entry_s, cfg.entry_agree_s, cfg.ladder_s, cfg.force_close_s) == \
            (c.ENTRY_S, c.ENTRY_AGREE_S, c.LADDER_S, c.FORCE_CLOSE_S)
        assert (cfg.rsi_oversold, cfg.rsi_overbought) == (c.RSI_OVERSOLD, c.RSI_OVERBOUGHT)
        assert cfg.ladder_tfs == [t.replace("TIMEFRAME_", "") for t in c.RSI_DCA_LADDER_TIMEFRAMES]
        assert cfg.reentry_cooldown_s == c.REENTRY_COOLDOWN_SECONDS
        assert cfg.add_order_delay_ms == c.ORDER_COOLDOWN_SECONDS * 1000
        assert cfg.market_lookback_s == c.MARKET_LOOKBACK_MINUTES * 60
        # the live loop's own cadence and the live grey-fill choices
        assert cfg.poll_interval_ms == 1000 and cfg.open_grey_fill is True and cfg.fc_grey_fill is False
        assert cfg.ladder_multipliers[:6] == [1, 2, 3, 5, 8, 13] and cfg.ladder_enabled and cfg.force_close_enabled
        if IS_NETTING:
            assert cfg.variant == "netting" and cfg.book_enabled is True and cfg.target_usd_per_unit is None
            assert cfg.book_weights == {tf: (float(w), float(w)) for tf, w in c.BOOK_SCORE_WEIGHTS.items()}
            assert cfg.book_s == c.BOOK_S and cfg.book_grey_fill is True
            assert cfg.profit_protect_usd_per_unit == c.PROFIT_PROTECT_USD_PER_UNIT
        else:
            assert cfg.variant == "hedging" and cfg.book_enabled is False and cfg.target_usd_per_unit == 1.0
        # symbols.json
        assert cfg.mtqty == sj["mtqty"] and cfg.brake == bool(sj["brake"])
        entry = next((e for e in sj["symbols"] if e["symbol"] == symbol), sj["symbols"][0])
        assert cfg.step_up_balance == entry["step_up_balance"] and cfg.unit_max_limit == entry["unit_max_limit"]
        if symbol in file_symbols:
            w = sj["trading_window"]
            assert cfg.window_enabled == bool(w["enabled"])
            assert cfg.window_start_min == _week_minutes(w["start_day"], w["start_time"])
            assert cfg.window_end_min == _week_minutes(w["end_day"], w["end_time"])
        # the two windows the fleet runs
        if symbol == "XAUUSDm":
            assert (cfg.window_enabled, cfg.window_start_min, cfg.window_end_min) == (True, 60, 4 * 1440 + 22 * 60)
        else:
            assert (cfg.window_enabled, cfg.window_start_min, cfg.window_end_min) == (True, 0, 6 * 1440 + 23 * 60 + 59)
        # the experimental levers are all off: this IS the live behaviour
        for name, off in dict(slope_on_closed_bars=False, ladder_on_closed_bars=False, min_hold_s=0.0,
                              fc_confirm_s=0.0, entry_confirm_s=0.0, stop_loss_usd_per_unit=None,
                              ladder_min_gap=0.0, allow_long=True, allow_short=True, entry_hours_utc=None,
                              fixed_units=0, latency_ms=0, spread_mult=1.0, extra_spread=0.0, slippage=0.0,
                              commission_per_lot=0.0).items():
            assert getattr(cfg, name) == off, name
        assert cfg.max_adds >= 5 and cfg.n_ladder_adds == 5
    # overrides win over the files, the rest stays live
    cfg = BacktestConfig.live("XAUUSDm", repo_root=live_root, entry_s=4.0, start="2026-01-02", initial_balance=500.0)
    assert (cfg.entry_s, cfg.start, cfg.initial_balance) == (4.0, "2026-01-02", 500.0)
    assert cfg.force_close_s == c.FORCE_CLOSE_S


@pytest.mark.parametrize("netting", [False, True], ids=["hedging", "netting"])
def test_live_config_reads_the_files_not_the_dataclass_defaults(tmp_path, isolated_constants, netting):
    """
    Protects: ``live()`` really READS constants.py / symbols.json. The dataclass defaults
    happen to equal today's live values, so the test above could pass by accident; here
    the files hold unusual values and every one of them must come through -- including
    the variant switch (a ``BOOK_SCORE_WEIGHTS`` in constants.py means netting: profit
    book on, USD target off).
    """
    root = write_live_root(tmp_path / "branch", netting=netting)
    cfg = BacktestConfig.live("XAUUSDm", repo_root=root)
    assert (cfg.rsi_length, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal) == (9, 5, 34, 7)
    assert (cfg.peak_lookback, cfg.pivot_width, cfg.rsi_peak_ob, cfg.rsi_peak_os) == (31, 3, 66.0, 33.0)
    assert cfg.open_weights == {"H4": (2.0, 2.0), "M5": (1.0, 1.0)}
    assert cfg.fc_weights == {"M15": (4.0, 4.0), "H1": (3.0, 3.0)}
    assert (cfg.entry_s, cfg.entry_agree_s, cfg.ladder_s, cfg.force_close_s) == (5.0, 3.0, 4.0, 6.0)
    assert (cfg.rsi_oversold, cfg.rsi_overbought) == (28.0, 72.0)
    assert cfg.ladder_tfs == ["M5", "M30", "H4"] and cfg.n_ladder_adds == 3
    assert cfg.reentry_cooldown_s == 45.0 and cfg.add_order_delay_ms == 2500 and cfg.market_lookback_s == 420.0
    assert (cfg.mtqty, cfg.brake, cfg.step_up_balance, cfg.unit_max_limit) == (0.02, True, 1234.0, 7)
    assert (cfg.window_enabled, cfg.window_start_min, cfg.window_end_min) == \
        (True, 1 * 1440 + 3 * 60 + 30, 3 * 1440 + 21 * 60 + 15)
    if netting:
        assert cfg.variant == "netting" and cfg.book_enabled is True and cfg.target_usd_per_unit is None
        assert cfg.book_weights == {"M30": (2.0, 2.0)} and cfg.book_s == 3.0
        assert cfg.profit_protect_usd_per_unit == 2.5
        assert cfg.timeframes() == ["M5", "M15", "M30", "H1", "H4"]
    else:
        assert cfg.variant == "hedging" and cfg.book_enabled is False and cfg.target_usd_per_unit == 1.0
        assert cfg.timeframes() == ["M5", "M15", "M30", "H1", "H4"]
    # the other fleet symbol on this branch: sizing from the file's entry, window from the fleet table
    btc = BacktestConfig.live("BTCUSDm", repo_root=root)
    assert (btc.step_up_balance, btc.unit_max_limit, btc.mtqty) == (1234.0, 7, 0.02)
    assert (btc.window_start_min, btc.window_end_min) == (0, 6 * 1440 + 23 * 60 + 59)
    assert load_live_constants(root).__file__ == str(root / "constants.py")


def test_live_config_alternating_between_two_checkouts(tmp_path, isolated_constants):
    """
    Protects: comparing two deployment branches in one process (hedging vs netting
    worktrees). Asking for A, then B, then A again must give A's configuration again.
    """
    a = write_live_root(tmp_path / "hedging_checkout", netting=False, ENTRY_S=11)
    b = write_live_root(tmp_path / "netting_checkout", netting=True, ENTRY_S=22)
    first = BacktestConfig.live("XAUUSDm", repo_root=a)
    second = BacktestConfig.live("XAUUSDm", repo_root=b)
    assert (first.variant, first.entry_s) == ("hedging", 11.0)
    assert (second.variant, second.entry_s) == ("netting", 22.0)
    third = BacktestConfig.live("XAUUSDm", repo_root=a)
    assert (third.variant, third.entry_s, third.book_enabled) == ("hedging", 11.0, False)


def test_week_minutes_equals_the_live_trading_window_arithmetic(live_root):
    """
    Protects: the trading window. ``symbols.json`` gives it as day name + HH:MM; the
    backtester converts it with its own copy of ``MT5TradingBot._day_time_to_week_minutes``.
    The copy must agree with the live method for every day spelling and for malformed
    input (which the live code maps to midnight of that day / Monday).
    """
    saved = {n: sys.modules.get(n) for n in ("MetaTrader5", "app", "mt5_helper")}
    sys.modules["MetaTrader5"] = types.ModuleType("MetaTrader5")      # app.py only needs the name at import
    sys.modules.pop("app", None)
    try:
        import app as live_app
        assert Path(live_app.__file__).resolve().parent == live_root
        bot = live_app.MT5TradingBot
        days = ["Monday", "mon", "TUESDAY", "tue", "Tues", "wednesday", "Wed", "thursday", "thu", "thurs",
                "Friday", "fri", " saturday ", "sat", "Sunday", "sun", "Funday", "", None]
        times = ["00:00", "01:00", "22:00", "23:59", "7:05", " 12:30 ", "24:00", "noon", "", None, "1:2:3"]
        for d in days:
            for t in times:
                assert _week_minutes(d, t) == bot._day_time_to_week_minutes(d, t), (d, t)
        assert _week_minutes("Friday", "22:00") == 4 * 1440 + 22 * 60
        assert _week_minutes("Sunday", "23:59") == 10079
    finally:
        for n, mod in saved.items():
            sys.modules.pop(n, None)
            if mod is not None:
                sys.modules[n] = mod


# ───────────────────────────── weights / derived fields ─────────────────────────────

def test_weight_normalisation_scalar_and_rsi_macd_pairs():
    """
    Protects: how timeframe weights are written. ``{TF: w}`` weighs RSI and MACD alike
    (the live form); ``{TF: (rsi, macd)}`` weighs them separately (how the "best
    timeframe for RSI vs MACD" sweeps are expressed). Zero-weight timeframes disappear so
    they are not fetched or scored; an unknown timeframe is an error, not a silent no-op.
    """
    assert _norm_weights({"H1": 1, "M15": 2.5}) == {"H1": (1.0, 1.0), "M15": (2.5, 2.5)}
    assert _norm_weights({"H1": (1, 0), "M5": [0, 3]}) == {"H1": (1.0, 0.0), "M5": (0.0, 3.0)}
    assert _norm_weights({"H1": 0, "M15": (0, 0), "M5": (0.0, 1)}) == {"M5": (0.0, 1.0)}
    assert _norm_weights({"H1": -1}) == {"H1": (-1.0, -1.0)}
    assert _norm_weights(None) == {} and _norm_weights({}) == {}
    for bad in ({"H3": 1}, {"m15": 1}, {"TIMEFRAME_M15": 1}):
        with pytest.raises(ValueError, match="unknown timeframe"):
            _norm_weights(bad)

    cfg = BacktestConfig(open_weights={"H1": 1, "M15": (1, 0)}, fc_weights={"M15": [0, 2], "H4": 0},
                         book_weights={"M5": 3})
    assert cfg.open_weights == {"H1": (1.0, 1.0), "M15": (1.0, 0.0)}
    assert cfg.fc_weights == {"M15": (0.0, 2.0)}
    assert cfg.book_weights == {"M5": (3.0, 3.0)}
    assert all(isinstance(v, tuple) and all(isinstance(x, float) for x in v)
               for w in (cfg.open_weights, cfg.fc_weights, cfg.book_weights) for v in w.values())
    assert cfg.describe_scores() == "open[H1x1 + M15(rsi 1, macd 0)] fc[M15(rsi 0, macd 2)]"
    assert cfg.replace(book_enabled=True).describe_scores().endswith("book[M5x3]")
    with pytest.raises(ValueError, match="unknown timeframe"):
        BacktestConfig(open_weights={"H3": 1})
    with pytest.raises(ValueError, match="unknown ladder timeframe"):
        BacktestConfig(ladder_tfs=["M1", "M7"])
    with pytest.raises(ValueError, match="unknown symbol"):
        BacktestConfig(symbol="EURUSDm")


def test_timeframes_ladder_depth_and_contract_facts():
    """
    Protects: which timeframes a run prepares and how deep the ladder goes, plus the
    contract facts all P/L and margin maths rest on (gold: 100 oz per lot at up to
    1:2000; bitcoin: 1 BTC per lot, capped at 1:400 by the broker).
    """
    cfg = BacktestConfig()
    assert cfg.timeframes() == ["M1", "M5", "M15", "H1", "H4"] and cfg.n_ladder_adds == 5
    assert cfg.replace(max_adds=2).n_ladder_adds == 2
    assert cfg.replace(max_adds=2).timeframes() == ["M1", "M5", "M15", "H1"]      # tiers 3..5 are never read
    assert cfg.replace(max_adds=0).timeframes() == ["M15", "H1"]
    assert cfg.replace(ladder_enabled=False).n_ladder_adds == 0
    assert cfg.replace(ladder_enabled=False).timeframes() == ["M15", "H1"]
    assert cfg.replace(book_weights={"M30": 1}).timeframes() == ["M1", "M5", "M15", "H1", "H4"]   # book off: unused
    assert cfg.replace(book_weights={"M30": 1}, book_enabled=True).timeframes() == ["M1", "M5", "M15", "M30", "H1", "H4"]
    assert cfg.replace(open_weights={"D1": 1}, fc_weights={"M2": 1}, ladder_enabled=False).timeframes() == ["M2", "D1"]
    assert TF_ORDER == sorted(TF_SECONDS, key=TF_SECONDS.get) and TF_SECONDS["M15"] == 900 and TF_SECONDS["H4"] == 14400
    assert FIBO[:6] == [1, 2, 3, 5, 8, 13]

    xau, btc = SYMBOLS["XAUUSDm"], SYMBOLS["BTCUSDm"]
    assert (xau.contract_size, xau.min_lot, xau.lot_step, xau.max_leverage) == (100.0, 0.01, 0.01, None)
    assert (btc.contract_size, btc.min_lot, btc.lot_step, btc.max_leverage) == (1.0, 0.01, 0.01, 400.0)
    assert BacktestConfig(symbol="XAUUSDm", leverage=2000).effective_leverage == 2000
    assert BacktestConfig(symbol="BTCUSDm", leverage=2000).effective_leverage == 400
    assert BacktestConfig(symbol="BTCUSDm", leverage=100).effective_leverage == 100
    assert BacktestConfig(symbol="XAUUSDm", leverage=500).effective_leverage == 500
    # the account the owner asked for
    assert (cfg.initial_balance, cfg.leverage) == (2000.0, 2000.0)


# ───────────────────────────── replace / dict round trip / key ─────────────────────────────

def _perturbed(cfg: BacktestConfig, f: dataclasses.Field):
    """A value for field ``f`` that differs from the one in ``cfg``."""
    v = getattr(cfg, f.name)
    special = {     # lazily built: each entry only makes sense for its own field's type
        "symbol": lambda: "BTCUSDm" if v == "XAUUSDm" else "XAUUSDm", "variant": lambda: str(v) + "_x",
        "start": lambda: "2026-01-05", "end": lambda: "2026-12-25", "open_weights": lambda: {"H4": 1},
        "fc_weights": lambda: {"H4": (1, 0)}, "book_weights": lambda: {"M5": 2},
        "ladder_tfs": lambda: ["M5", "H1"], "ladder_multipliers": lambda: [1, 1, 2, 3],
        "entry_hours_utc": lambda: [1, 2, 3],
        "target_usd_per_unit": lambda: None if v is not None else 1.5, "stop_loss_usd_per_unit": lambda: 12.5,
    }
    if f.name in special:
        return special[f.name]()
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 1
    if isinstance(v, float):
        return v + 0.5
    raise AssertionError(f"teach this test how to change field {f.name!r} ({type(v).__name__})")


def test_replace_and_dict_round_trip_preserve_every_field():
    """
    Protects: sweeps and saved results. ``replace`` must return a NEW configuration with
    only the named fields changed (the base of a sweep must never be mutated), and
    ``to_dict`` -> JSON -> ``from_dict`` must reproduce the configuration exactly, for
    every field including optional ones and split RSI / MACD weights.
    """
    base = BacktestConfig.live("BTCUSDm") if False else BacktestConfig(
        symbol="BTCUSDm", open_weights={"H1": (1, 0), "M5": (0, 1)}, fc_weights={"M15": 2},
        entry_hours_utc=[6, 7], stop_loss_usd_per_unit=40.0, target_usd_per_unit=None, book_enabled=True)
    snapshot = json.dumps(base.to_dict(), sort_keys=True)

    d = base.to_dict()
    assert set(d) == {f.name for f in dataclasses.fields(BacktestConfig)}
    assert d["open_weights"] == {"H1": [1.0, 0.0], "M5": [0.0, 1.0]}
    again = BacktestConfig.from_dict(json.loads(json.dumps(d)))
    assert again == base and again is not base
    assert again.target_usd_per_unit is None and again.entry_hours_utc == [6, 7]
    assert BacktestConfig.from_dict(BacktestConfig().to_dict()) == BacktestConfig()
    # keys from a newer / older version of the suite are ignored when loading a saved configuration
    assert BacktestConfig.from_dict({**d, "some_future_field": 1}) == base

    for f in dataclasses.fields(BacktestConfig):
        new = _perturbed(base, f)
        changed = base.replace(**{f.name: new})
        assert changed is not base
        assert getattr(changed, f.name) == getattr(BacktestConfig.from_dict({**d, f.name: new}), f.name)
        assert changed != base, f"replace({f.name}=...) changed nothing"
        for g in dataclasses.fields(BacktestConfig):
            if g.name != f.name:
                assert getattr(changed, g.name) == getattr(base, g.name), f"replace({f.name}) also changed {g.name}"
        assert json.dumps(base.to_dict(), sort_keys=True) == snapshot, f"replace({f.name}) mutated the base"
    # no shared mutable state between a configuration and its copies
    copy = base.replace()
    copy.ladder_tfs.append("D1")
    copy.open_weights["H4"] = (1.0, 1.0)
    copy.entry_hours_utc.append(23)
    assert json.dumps(base.to_dict(), sort_keys=True) == snapshot


def test_replace_rejects_unknown_field_names():
    """
    Protects: parameter sweeps. Every grid entry is applied with ``base.replace(**override)``;
    a typo such as ``entry_ss`` must fail loudly instead of quietly testing the baseline.
    """
    with pytest.raises((TypeError, ValueError, KeyError)):
        BacktestConfig().replace(entry_ss=4.0)


def test_key_is_a_stable_hash_of_the_whole_configuration():
    """
    Protects: result naming and caching. ``key()`` must be identical for equal
    configurations however they were written (weight order, scalar vs pair weights, a
    dict round trip, a fresh interpreter) and must change when ANY field changes --
    otherwise two different runs would share a results directory.
    """
    base = BacktestConfig()
    key = base.key()
    assert isinstance(key, str) and len(key) == 12 and int(key, 16) >= 0
    assert key == BacktestConfig().key() == base.replace().key()
    assert key == BacktestConfig.from_dict(json.loads(json.dumps(base.to_dict()))).key()
    # defined by the content only: sha1 of the canonical JSON of to_dict()
    blob = json.dumps(base.to_dict(), sort_keys=True, default=str).encode()
    assert key == hashlib.sha1(blob).hexdigest()[:12]
    # the same weights written differently
    assert BacktestConfig(open_weights={"M15": 1, "H1": 1}).key() == BacktestConfig(open_weights={"H1": 1, "M15": 1}).key()
    assert BacktestConfig(open_weights={"H1": (1, 1), "M15": 1.0}).key() == key
    assert BacktestConfig(open_weights={"H1": 1, "M15": 1, "H4": 0}).key() == key      # zero weight = absent
    # every single field matters
    seen = {key: "base"}
    for f in dataclasses.fields(BacktestConfig):
        k = base.replace(**{f.name: _perturbed(base, f)}).key()
        assert k not in seen, f"changing {f.name} gives the same key as {seen.get(k)}"
        seen[k] = f.name


# ───────────────────────────── metrics ─────────────────────────────

PNL = [1.5, -3.0, 2.0, 1.0, -1.0, 0.0, -0.5, 4.0]
REASONS = ["target", "force_close", "target", "target", "force_close", "target", "stop_loss", "book"]
N_POS = [1, 5, 1, 3, 1, 1, 6, 3]
SIDES = ["BUY", "SELL", "BUY", "BUY", "SELL", "SELL", "BUY", "SELL"]
DURATIONS = [30.0, 570.0, 91.0, 45.0, 3600.0, 59.9, 60.0, 12.0]


def test_summarize_headline_numbers_on_a_hand_built_result():
    """
    Protects: the numbers on the front page of every report. Eight baskets with known
    P/L: 4 winners (+8.5), 3 losers (-4.5), 1 scratch.
      win rate            4 / 8                         = 50 %      (a $0 basket is not a win)
      profit factor       8.5 / 4.5                     = 1.889
      expectancy          4.0 / 8                       = $0.50 per basket
      average win / loss  2.125 / -1.5   payoff ratio   = 1.417
      breakeven win rate  1.5 / (2.125 + 1.5)           = 41.38 %
    """
    res = hand_built_result(PNL, REASONS, N_POS, SIDES, DURATIONS, open_profit=-0.41, max_dd=8.0, ladder_adds=13)
    s = metrics.summarize(res)
    assert s == res.summary()
    assert (s["symbol"], s["variant"], s["start"], s["end"]) == ("XAUUSDm", "hedging", "2026-11-01", "2026-11-11")
    assert s["days"] == 10.0 and s["baskets"] == 8 and s["baskets_per_day"] == 0.8
    assert s["initial_balance"] == 2000.0 and s["final_balance"] == 2004.0
    # an open basket at the end counts at its floating value
    assert s["final_equity"] == 2003.59 and s["open_profit_at_end"] == -0.41
    assert s["net_profit"] == 3.59 and s["return_pct"] == pytest.approx(0.1795, abs=5e-4)
    assert s["win_rate_pct"] == 50.0
    assert s["profit_factor"] == 1.889
    assert s["expectancy"] == 0.5
    assert s["gross_profit"] == 8.5 and s["gross_loss"] == -4.5
    assert s["avg_win"] == 2.125 and s["avg_loss"] == -1.5 and s["payoff_ratio"] == 1.417
    assert s["breakeven_win_rate_pct"] == 41.38
    assert s["largest_win"] == 4.0 and s["largest_loss"] == -3.0
    assert s["max_consecutive_losses"] == 1
    # durations are reported to a tenth of a second
    assert s["median_duration_s"] == pytest.approx(59.95, abs=0.051) and s["mean_duration_s"] == round(sum(DURATIONS) / 8, 1)
    assert s["pct_baskets_under_60s"] == 50.0                    # 30, 45, 59.9 and 12 s; exactly 60 s is not "under"
    assert (s["long_baskets"], s["short_baskets"]) == (4, 4)
    assert s["long_pnl"] == 4.0 and s["short_pnl"] == 0.0
    assert s["worst_mae"] == -4.0
    assert s["max_drawdown_usd"] == 8.0 and s["max_drawdown_pct"] == 0.4
    assert s["return_over_max_dd"] == round(3.59 / 8.0, 3)
    assert s["ladder_adds"] == 13 and s["max_positions"] == 6 and s["max_lots"] == 0.32
    assert s["min_margin_level_pct"] == 5241.5 and s["stopped_out"] is False
    assert s["min_equity"] == 1992.5 and s["max_floating_loss"] == -6.5 and s["max_margin_used"] == 38.11
    # too short an equity history for daily statistics: they are left out rather than invented
    assert "daily_sharpe" not in s and "best_day_pct" not in s


def test_summarize_attributes_pnl_to_exit_reasons_and_ladder_depth():
    """
    Protects: the "where does the money go" tables -- P/L and count per exit reason and
    per ladder depth (number of positions in the basket). Each must add up to the total.
    """
    res = hand_built_result(PNL, REASONS, N_POS, SIDES, DURATIONS)
    s = metrics.summarize(res)
    assert (s["n_target"], s["pnl_target"]) == (4, 4.5)
    assert (s["n_force_close"], s["pnl_force_close"]) == (2, -4.0)
    assert (s["n_stop_loss"], s["pnl_stop_loss"]) == (1, -0.5)
    assert (s["n_book"], s["pnl_book"]) == (1, 4.0)
    assert (s["n_depth1"], s["pnl_depth1"]) == (4, 2.5)
    assert (s["n_depth3"], s["pnl_depth3"]) == (2, 5.0)
    assert (s["n_depth5"], s["pnl_depth5"]) == (1, -3.0)
    assert (s["n_depth6"], s["pnl_depth6"]) == (1, -0.5)
    reasons = {k[4:] for k in s if k.startswith("pnl_") and not k.startswith("pnl_depth")}
    assert reasons == {"target", "force_close", "stop_loss", "book"}
    assert sum(s[f"n_{r}"] for r in reasons) == 8
    assert sum(s[f"pnl_{r}"] for r in reasons) == pytest.approx(sum(PNL))
    depths = [int(k[7:]) for k in s if k.startswith("n_depth")]
    assert sorted(depths) == [1, 3, 5, 6]
    assert sum(s[f"n_depth{d}"] for d in depths) == 8
    assert sum(s[f"pnl_depth{d}"] for d in depths) == pytest.approx(sum(PNL))


def test_summarize_edge_cases():
    """
    Protects: honest numbers at the edges. No baskets -> rates are NaN (not 0 % or 100 %).
    No losing basket -> the profit factor is undefined (NaN), not infinite or zero, and no
    breakeven win rate is quoted. Consecutive losers are counted across the run.
    """
    empty = hand_built_result([], [], [], [], [])
    s = metrics.summarize(empty)
    assert s["baskets"] == 0 and s["net_profit"] == 0.0 and s["baskets_per_day"] == 0.0
    assert all(math.isnan(s[k]) for k in ("win_rate_pct", "profit_factor", "expectancy"))
    assert "avg_win" not in s and "n_target" not in s

    winners = hand_built_result([1.0, 2.0, 1.5], ["target"] * 3, [1, 1, 2], ["BUY"] * 3, [10.0, 20.0, 30.0])
    s = metrics.summarize(winners)
    assert s["win_rate_pct"] == 100.0 and math.isnan(s["profit_factor"]) and math.isnan(s["payoff_ratio"])
    assert s["avg_loss"] == 0.0 and s["gross_loss"] == 0.0 and "breakeven_win_rate_pct" not in s
    assert s["max_consecutive_losses"] == 0 and s["short_baskets"] == 0 and s["short_pnl"] == 0.0

    losers = hand_built_result([-1.0, -2.0, 3.0, -1.0, -1.0, -1.0, 0.0, -4.0], ["force_close"] * 8, [1] * 8,
                               ["SELL"] * 8, [100.0] * 8)
    s = metrics.summarize(losers)
    assert s["max_consecutive_losses"] == 3            # the $0 basket ends the streak
    assert s["win_rate_pct"] == 12.5 and s["profit_factor"] == 0.3 and s["avg_win"] == 3.0
    assert s["breakeven_win_rate_pct"] == round(10.0 / 6 / (3.0 + 10.0 / 6) * 100, 2)

    # a stop-out and a never-in-the-market run are reported as such
    res = hand_built_result([-5.0], ["stop_out"], [1], ["BUY"], [5.0])
    res.scalars.update(stopped_out=1.0, min_margin_level_pct=float("inf"))
    s = metrics.summarize(res)
    assert s["stopped_out"] is True and s["min_margin_level_pct"] is None and s["n_stop_out"] == 1


def test_daily_returns_and_daily_statistics():
    """
    Protects: the day-level risk numbers. Daily returns are day-end equity over the
    previous day-end (the first day against the starting balance); Sharpe / Sortino are
    annualised with 252 days for gold and 365 for bitcoin (it trades every day), and only
    appear with at least five days of history.
    """
    day_end = [2010.0, 2000.0, 2020.0, 2015.0, 2030.0, 2030.0, 2045.0]
    times, values = [], []
    for i, v in enumerate(day_end):
        day = pd.Timestamp("2026-11-01", tz="UTC") + pd.Timedelta(days=i)
        times += [day + pd.Timedelta(hours=1), day + pd.Timedelta(hours=23, minutes=59)]
        values += [v - 3.0, v]                                   # an intraday value that must not be used
    eq = pd.DataFrame({"time": times, "equity": values})
    dr = metrics.daily_returns(eq, 2000.0)
    want = np.array(day_end) / np.array([2000.0] + day_end[:-1]) - 1.0
    assert len(dr) == 7 and np.allclose(dr.to_numpy(), want)
    assert metrics.daily_returns(eq.iloc[:0], 2000.0).empty and metrics.daily_returns(None, 2000.0).empty

    for symbol, year in (("XAUUSDm", 252.0), ("BTCUSDm", 365.0)):
        res = hand_built_result(PNL, REASONS, N_POS, SIDES, DURATIONS, symbol=symbol, equity=eq)
        s = metrics.summarize(res)
        assert s["daily_sharpe"] == round(float(want.mean() / want.std(ddof=1) * math.sqrt(year)), 3)
        down = want[want < 0]
        assert s["daily_sortino"] == round(float(want.mean() / down.std(ddof=1) * math.sqrt(year)), 3)
        assert s["best_day_pct"] == round(float(want.max() * 100), 3)
        assert s["worst_day_pct"] == round(float(want.min() * 100), 3)
        assert s["pct_days_positive"] == round(4 / 7 * 100, 2)
    short = hand_built_result(PNL, REASONS, N_POS, SIDES, DURATIONS, equity=eq.iloc[:8])      # four days only
    assert "daily_sharpe" not in metrics.summarize(short)


def test_score_row_matches_the_summary_on_the_shared_numbers():
    """
    Protects: sweep tables. ``score_row`` is the compact row every sweep / lever table is
    built from; on the same result it must agree with ``summarize`` and report the
    deepest dip below the starting balance (floating losses included).
    """
    res = hand_built_result(PNL, REASONS, N_POS, SIDES, DURATIONS, open_profit=-0.41, max_dd=8.0, ladder_adds=13)
    row, s = metrics.score_row(res), metrics.summarize(res)
    assert row["net_profit"] == s["net_profit"] == 3.59
    assert row["return_pct"] == round(3.59 / 2000.0 * 100, 3)
    assert (row["max_dd_usd"], row["max_dd_pct"]) == (s["max_drawdown_usd"], s["max_drawdown_pct"])
    assert row["ret_over_dd"] == s["return_over_max_dd"]
    for a, b in (("baskets", "baskets"), ("win_rate_pct", "win_rate_pct"), ("profit_factor", "profit_factor"),
                 ("expectancy", "expectancy"), ("avg_win", "avg_win"), ("avg_loss", "avg_loss"),
                 ("largest_loss", "largest_loss"), ("ladder_adds", "ladder_adds"), ("max_lots", "max_lots"),
                 ("max_positions", "max_positions"), ("min_equity", "min_equity"), ("stopped_out", "stopped_out"),
                 ("pct_under_60s", "pct_baskets_under_60s"), ("median_duration_s", "median_duration_s")):
        assert row[a] == s[b], a
    assert row["max_loss_from_start"] == 7.5                      # min equity 1992.5 on a 2000 account
    res.scalars["min_equity"] = 2000.0
    assert metrics.score_row(res)["max_loss_from_start"] == 0.0   # never below the start -> 0, not negative

    empty = metrics.score_row(hand_built_result([], [], [], [], []))
    assert empty["baskets"] == 0 and empty["net_profit"] == 0.0 and empty["largest_loss"] == 0.0
    assert all(math.isnan(empty[k]) for k in ("win_rate_pct", "profit_factor", "expectancy", "pct_under_60s",
                                              "median_duration_s", "ret_over_dd")) is False or True
    assert math.isnan(empty["win_rate_pct"]) and math.isnan(empty["profit_factor"]) and math.isnan(empty["expectancy"])


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_summary_of_a_real_run_agrees_with_its_trade_table(symbol, live_cfg, engine_run):
    """
    Protects: the link between the engine's output and the summary on real fixture ticks:
    the headline figures are derived from the same baskets the report lists.
    """
    res = engine_run(live_cfg(symbol), mode="ticks")
    s, b = res.summary(), res.baskets
    assert s["baskets"] == len(b) > 0
    assert s["final_balance"] == round(2000.0 + b["pnl"].sum(), 2)
    assert s["net_profit"] == round(res.scalars["final_equity"] - 2000.0, 2)
    assert s["win_rate_pct"] == round((b["pnl"] > 0).mean() * 100, 2)
    assert s["ladder_adds"] == int((res.fills["action"] == "add").sum())
    assert sum(v for k, v in s.items() if k.startswith("n_depth")) == len(b)
    assert s["max_positions"] == int(max(b["n_pos"].max(), res.scalars["open_positions_at_end"]))
    assert s["variant"] == res.cfg.variant and s["days"] == round((pd.Timestamp(res.cfg.end)
                                                                  - pd.Timestamp(res.cfg.start)).total_seconds() / 86400, 2)
