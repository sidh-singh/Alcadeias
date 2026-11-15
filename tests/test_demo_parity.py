"""
The harness that replays a demo branch (engine/reference.py with the demo contract, engine/demo_parity.py).

A demo branch tags its orders with a magic number and a comment, sizes itself from a virtual balance (its own
closed deals in the history), reads the contract size and volume limits of the symbol, reads closed bars, and
keeps the design's levers in constants.py. These tests pin what the simulated terminal serves for that, how the
contract constants are driven from a BacktestConfig, and the comparison and report helpers -- all on hand-made
data, without replaying a whole app.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.config import BacktestConfig
from backtesting.data import store
from backtesting.engine import demo_parity as D
from backtesting.engine import kernels as K
from backtesting.engine import parity
from backtesting.engine import reference as R
from backtesting.engine.reference import SimClock, SimMT5

SYM = "XAUUSDm"
T0 = store.to_ms("2026-10-28 17:00")


def _sim(n=600, step_ms=1000, price=4000.0, balance=2000.0, **kw):
    """A terminal with one quote every ``step_ms`` from T0: bid rising a cent per quote, spread 0.20."""
    t = T0 + np.arange(n, dtype=np.int64) * step_ms
    bid = price + np.arange(n) * 0.01
    ask = bid + 0.2
    clock = SimClock(T0, T0 + n * step_ms + 60_000)
    sim = SimMT5(SYM, t, bid, ask, clock, {}, 100.0, 2000.0, balance, digits=3, **kw)
    return sim, clock


def _at(clock, seconds):
    clock.now_ms = T0 + int(seconds * 1000)


def _utc(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _buy(sim, volume=0.02, **extra):
    tick = sim.symbol_info_tick(SYM)
    req = dict(action=sim.TRADE_ACTION_DEAL, symbol=SYM, volume=volume, type=sim.ORDER_TYPE_BUY, price=tick.ask,
               type_time=sim.ORDER_TIME_GTC, type_filling=sim.ORDER_FILLING_IOC)
    req.update(extra)
    return sim.order_send(req)


def _close(sim, pos, **extra):
    req = dict(action=sim.TRADE_ACTION_DEAL, position=pos.ticket, symbol=SYM, volume=pos.volume, type=1 - pos.type,
               price=0.0, deviation=20)
    req.update(extra)
    return sim.order_send(req)


# ───────────────────────────── orders, positions, deals ─────────────────────────────

def test_orders_positions_and_deals_carry_the_magic_number_and_comment():
    sim, clock = _sim()
    _at(clock, 10)
    r = _buy(sim, magic=26116, comment="demo_hedging_xauusd6")
    assert r.retcode == sim.TRADE_RETCODE_DONE and r.request.magic == 26116 and r.price == pytest.approx(4000.30)
    (p,) = sim.positions_get()                       # no symbol: every position of the account
    assert sim.positions_get(symbol=SYM) == (p,) and sim.positions_get(symbol="BTCUSDm") == ()
    assert (p.magic, p.comment, p.identifier, p.ticket, p.volume) == (26116, "demo_hedging_xauusd6", r.order, r.order, 0.02)
    assert p.time_msc == T0 + 10_000 and p.time == (T0 + 10_000) // 1000 and p.price_open == pytest.approx(4000.30)
    assert p.price_current == pytest.approx(4000.10) and p.profit == pytest.approx(-0.4)
    assert sim.positions_get(ticket=p.ticket) == (p,) and sim.positions_get(ticket=1) == ()
    assert len(sim.positions_get(group="*XAU*")) == 1 and sim.positions_get(group="*,!XAU*") == ()
    assert sim.positions_total() == 1 and p._asdict()["magic"] == 26116

    _at(clock, 70)
    r2 = _close(sim, p, magic=26116, comment="demo_hedging_xauusd6")
    assert r2.retcode == sim.TRADE_RETCODE_DONE and r2.order != p.ticket
    profit = round((4000.70 - 4000.30) * 0.02 * 100, 2)
    assert sim.positions_get() == () and sim.balance == pytest.approx(2000.0 + profit)
    assert sim.account_info().balance == pytest.approx(2000.0 + profit)

    deals = sim.history_deals_get(_utc(T0), _utc(T0 + 120_000))
    assert [(d.entry, d.type) for d in deals] == [(0, 0), (1, 1)]   # a buy is closed by a sell deal
    din, dout = deals
    assert din.position_id == dout.position_id == p.ticket and din.order == p.ticket and dout.order == r2.order
    assert (din.magic, dout.magic, din.comment, dout.comment) == (26116, 26116, "demo_hedging_xauusd6",
                                                                 "demo_hedging_xauusd6")
    assert din.profit == 0.0 and dout.profit == pytest.approx(profit) and dout.volume == 0.02
    assert dout.price == pytest.approx(4000.70) and dout.symbol == SYM and (dout.swap, dout.commission, dout.fee) == (0, 0, 0)
    assert dout.time == (T0 + 70_000) // 1000 and dout.time_msc == T0 + 70_000 and dout.ticket == r2.deal
    assert set(dout._asdict()) >= {"ticket", "order", "time", "type", "entry", "magic", "volume", "price", "profit",
                                   "swap", "commission", "symbol", "comment", "position_id"}
    # the bot's own fills, as parity compares them (an 'out' deal keeps the type of the position it closed)
    assert list(pd.DataFrame(sim.deals)[["entry", "type", "magic"]].itertuples(index=False, name=None)) == \
        [("in", 0, 26116), ("out", 0, 26116)]


def test_a_closing_deal_has_the_magic_of_the_request_that_closed_it():
    """As on MT5: a close sent without a magic number books a deal with magic 0, whatever the position carried."""
    sim, clock = _sim()
    _at(clock, 5)
    _buy(sim, magic=777)
    (p,) = sim.positions_get()
    _at(clock, 9)
    assert _close(sim, p).retcode == sim.TRADE_RETCODE_DONE
    out = [d for d in sim.history_deals_get(0, T0 // 1000 + 60) if d.entry == 1]
    assert [d.magic for d in out] == [0] and sim.deals[-1]["position_magic"] == 777


def test_the_history_is_served_by_time_group_order_and_position():
    past = [dict(t_ms=T0 - 30 * 86_400_000, type=SimMT5.DEAL_TYPE_BALANCE, entry=0, profit=1900.0, comment="deposit"),
            dict(t_ms=T0 - 3_600_000, type=1, entry=1, magic=5, symbol="BTCUSDm", profit=100.0, position_id=42,
                 order=43)]
    sim, clock = _sim(history=past)
    assert sim.balance == 2000.0                     # the past is already in the starting balance
    _at(clock, 30)
    _buy(sim, magic=9)
    deals = sim.history_deals_get(0, T0 // 1000 + 3600)
    assert [(d.type, d.symbol) for d in deals] == [(2, ""), (1, "BTCUSDm"), (0, SYM)]
    assert deals[0].magic == 0 and deals[0].profit == 1900.0
    # both ends are inclusive, in whole seconds; datetimes (aware) and seconds are both accepted
    t_in = (T0 + 30_000) // 1000
    assert len(sim.history_deals_get(t_in, t_in)) == 1 and sim.history_deals_get(t_in + 1, t_in + 9) == ()
    assert len(sim.history_deals_get(_utc(T0 - 3_600_000), _utc(T0 + 30_000))) == 2
    assert [d.symbol for d in sim.history_deals_get(0, 2 ** 31, group="BTC*")] == ["BTCUSDm"]
    assert [d.position_id for d in sim.history_deals_get(position=42)] == [42]
    assert [d.order for d in sim.history_deals_get(ticket=43)] == [43]
    assert sim.history_deals_total(0, 2 ** 31) == 3
    assert sim.history_deals_get() is None and sim.last_error()[0] == -2


def test_requests_the_metatrader5_package_refuses_return_none():
    sim, clock = _sim()
    _at(clock, 3)
    assert _buy(sim, comment="x" * 32) is None and "comment" in sim.last_error()[1]
    for bad in (-1, 1.5, True, 2 ** 64):
        assert _buy(sim, magic=bad) is None and "magic" in sim.last_error()[1]
    assert sim.invalid_requests == 5 and sim.positions_get() == ()
    r = _buy(sim, comment="x" * R.MAX_COMMENT_LEN, magic=np.int64(12))
    assert r.retcode == sim.TRADE_RETCODE_DONE and sim.last_error() == (1, "Success")


def test_symbol_info_has_the_contract_size_and_the_volume_limits():
    sim, clock = _sim(volume_max=50.0)
    _at(clock, 2)
    info = sim.symbol_info(SYM)
    assert sim.symbol_info("BTCUSDm") is None
    assert (info.trade_contract_size, info.volume_min, info.volume_step, info.volume_max) == (100.0, 0.01, 0.01, 50.0)
    assert (info.digits, info.point, info.visible, info.trade_mode) == (3, pytest.approx(0.001), True, 4)
    assert info.bid == pytest.approx(4000.02) and info.ask == pytest.approx(4000.22) and info.spread == 200
    assert info.trade_tick_value == pytest.approx(0.1)          # one point of 0.001 on 100 oz
    for vol in (0.004, 51.0):                                    # below the minimum (rounds to 0) / above the maximum
        r = _buy(sim, volume=vol)
        assert r.retcode == sim.TRADE_RETCODE_INVALID_VOLUME
    assert sim.refused["invalid_volume"] == 2 and sim.positions_get() == ()
    assert _buy(sim, volume=0.03).retcode == sim.TRADE_RETCODE_DONE


def test_copy_rates_from_pos_reads_from_any_position():
    sim, clock = _sim(n=60, step_ms=10_000)                      # 10 M1 bars of 6 quotes
    _at(clock, 9 * 60 + 30)
    m1 = sim.TIMEFRAME_M1
    last3 = sim.copy_rates_from_pos(SYM, m1, 0, 3)
    assert list(last3["time"]) == [T0 // 1000 + 60 * k for k in (7, 8, 9)]   # the last row is the forming bar
    closed = sim.copy_rates_from_pos(SYM, m1, 1, 3)
    assert list(closed["time"]) == [T0 // 1000 + 60 * k for k in (6, 7, 8)]
    np.testing.assert_array_equal(closed, sim.copy_rates_from_pos(SYM, m1, 0, 4)[:-1])
    assert closed["close"][-1] == pytest.approx(4000.0 + 53 * 0.01)            # the last quote of minute 8
    assert len(sim.copy_rates_from_pos(SYM, m1, 9, 5)) == 1 and len(sim.copy_rates_from_pos(SYM, m1, 10, 5)) == 0
    assert sim.copy_rates_from_pos(SYM, m1, -1, 5) is None
    rng = sim.copy_rates_range(SYM, m1, _utc(T0 + 120_000), _utc(T0 + 240_000))
    assert list(rng["time"]) == [T0 // 1000 + 60 * k for k in (2, 3, 4)]
    assert list(sim.copy_rates_from(SYM, m1, _utc(T0 + 150_000), 2)["time"]) == [T0 // 1000 + 60, T0 // 1000 + 120]


def test_account_info_is_the_full_record_of_a_demo_account():
    sim, clock = _sim(balance=10_000.0)
    _at(clock, 4)
    _buy(sim, volume=0.05)
    a = sim.account_info()
    assert a.trade_mode == sim.ACCOUNT_TRADE_MODE_DEMO and a.margin_mode == sim.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
    assert a.currency == "USD" and a.leverage == 2000 and a.balance == 10_000.0
    assert a.equity == pytest.approx(10_000.0 + a.profit) and a.profit == pytest.approx(-1.0)
    assert a.margin == pytest.approx(0.05 * 100 * 4000.24 / 2000) and a.margin_free == pytest.approx(a.equity - a.margin)
    assert a.margin_level == pytest.approx(a.equity / a.margin * 100) and a._asdict()["currency"] == "USD"
    assert sim.terminal_info().trade_allowed and sim.order_check({}).retcode == 0


def test_partial_close_sl_tp_changes_and_unsupported_requests():
    sim, clock = _sim()
    _at(clock, 1)
    _buy(sim, volume=0.03)
    (p,) = sim.positions_get()
    r = sim.order_send(dict(action=sim.TRADE_ACTION_SLTP, position=p.ticket, symbol=SYM, sl=3990.0, tp=4010.0))
    (q,) = sim.positions_get()
    assert r.retcode == sim.TRADE_RETCODE_DONE and (q.sl, q.tp, q.volume) == (3990.0, 4010.0, 0.03) and len(sim.deals) == 1
    assert _close(sim, q, type=q.type).retcode == sim.TRADE_RETCODE_INVALID          # not the opposite side
    assert _close(sim, q, volume=0.05).retcode == sim.TRADE_RETCODE_INVALID_CLOSE_VOLUME
    _at(clock, 11)
    assert _close(sim, q, volume=0.01).retcode == sim.TRADE_RETCODE_DONE
    (rest,) = sim.positions_get()
    assert rest.volume == 0.02 and sim.deals[-1]["volume"] == 0.01
    assert sim.deals[-1]["profit"] == pytest.approx(round((4000.11 - 4000.21) * 0.01 * 100, 2))
    pending = sim.order_send(dict(action=sim.TRADE_ACTION_PENDING, symbol=SYM, volume=0.01, type=sim.ORDER_TYPE_BUY_STOP,
                                  price=4100.0))
    assert pending.retcode == sim.TRADE_RETCODE_INVALID and len(sim.unsupported) == 1
    assert sim.orders_get() == () and sim.orders_total() == 0


def test_positions_and_deals_of_others_on_the_account():
    sim, clock = _sim()
    _at(clock, 0)
    t = sim.add_position(type=0, volume=0.01, price_open=3999.0, t_ms=T0 - 60_000, magic=0)
    sim.schedule_deal(t_ms=T0 + 30_000, type=1, entry=1, magic=5, volume=0.02, profit=50.0, position_id=77)
    assert [p.ticket for p in sim.positions_get(symbol=SYM)] == [t] and sim.balance == 2000.0
    assert [d.entry for d in sim.history_deals_get(0, 2 ** 31)] == [0]               # its opening deal
    _at(clock, 29)
    sim.positions_get()
    assert sim.balance == 2000.0
    _at(clock, 31)
    sim.positions_get()                                                              # any call brings the terminal up to now
    assert sim.balance == 2050.0 and [d.position_id for d in sim.history_deals_get(0, 2 ** 31)] == [t, 77]


# ───────────────────────────── the clock ─────────────────────────────

def test_the_simulated_clock_stands_in_for_every_reading_of_the_time_module():
    clock = SimClock(T0, T0 + 10_000)
    assert clock.monotonic() == clock.time() == T0 / 1000.0 and clock.time_ns() == T0 * 1_000_000
    assert clock.gmtime().tm_hour == 17 and clock.strftime("%Y", clock.gmtime()) == "2026"
    assert clock.struct_time is __import__("time").struct_time
    with pytest.raises(AttributeError):
        clock.clock_gettime                                                          # a real clock is never served
    with pytest.raises(R._End):
        clock.sleep(11)


def test_live_modules_are_pointed_at_the_simulated_clock():
    import time as real_time
    from datetime import date, datetime as real_datetime
    import datetime as real_datetime_module

    mod = types.ModuleType("fake_live")
    mod.time, mod.sleep, mod.monotonic = real_time, real_time.sleep, real_time.monotonic
    mod.datetime, mod.date, mod.dtm, mod.keep = real_datetime, date, real_datetime_module, np.arange(3)
    clock = SimClock(T0, T0 + 10_000)
    sim_dt, sim_date = R._sim_datetime_classes(clock)
    R._patch_clocks(mod, clock, sim_dt, sim_date)
    assert mod.time is clock and mod.sleep == clock.sleep and mod.monotonic == clock.monotonic
    assert mod.datetime.now(timezone.utc) == _utc(T0) and mod.dtm.datetime.now() == _utc(T0)
    assert mod.date.today() == datetime.fromtimestamp(T0 / 1000.0).date()
    assert isinstance(real_datetime(2026, 1, 1), mod.datetime) and isinstance(pd.Timestamp("2026-01-01"), mod.datetime)
    assert not isinstance(date(2026, 1, 1), mod.datetime) and mod.keep.tolist() == [0, 1, 2]


def test_a_branchs_own_modules_are_listed_and_removed_again(tmp_path):
    files = {"constants.py": "X = 1\n", "strategy.py": "from constants import X\n", "indicator.py": "",
             "mt5_helper.py": "import time\n", "demo_extra_helper.py": "import time\nY = 2\n",
             "app.py": "import MetaTrader5 as mt5\nimport constants, strategy, indicator, mt5_helper, demo_extra_helper\n"}
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    saved = {n: sys.modules.get(n) for n in R._LIVE_MODULES}
    with R.live_code(tmp_path, types.SimpleNamespace(name="sim")) as mods:
        assert set(mods.extra) == {"demo_extra_helper"} and mods.app.mt5.name == "sim"
        assert [m.__name__ for m in R._live_modules(mods)][-1] == "demo_extra_helper"
    assert "demo_extra_helper" not in sys.modules and not (tmp_path / "__pycache__").exists()
    assert {n: sys.modules.get(n) for n in R._LIVE_MODULES} == saved


# ───────────────────────────── the demo contract ─────────────────────────────

LIVE_CONTRACT = dict(DESIGN_NAME="live", FORCE_CLOSE_ENABLED=True, TREND_TF=None, VOL_TF=None, VOL_LEN=24,
                     TARGET_USD_PER_UNIT="live", STOP_LOSS_USD_PER_UNIT=None, TARGET_VOL=0.0, STOP_VOL=0.0,
                     VOL_CAP_USD_PER_UNIT=0.0, LOSS_COOLDOWN_S=0, MAX_ADDS=99, LADDER_TRIGGER="rsi_level",
                     LADDER_TFS=["M1", "M5", "M15", "H1", "H4"], LADDER_GAP_VOL=0.0, LADDER_MULTIPLIERS=None,
                     STRATEGY="basket", ORDER_COMMENT=None, VIRTUAL_START_BALANCE=2000.0,
                     VIRTUAL_START_DATE="2026-11-16")
CLASSIC = dict(OPEN_SCORE_WEIGHTS={"H1": 1, "M15": 1}, FORCE_CLOSE_SCORE_WEIGHTS={"M15": 1}, ENTRY_S=2,
               ENTRY_AGREE_S=2, LADDER_S=2, FORCE_CLOSE_S=1, RSI_OVERSOLD=35, RSI_OVERBOUGHT=65, STRATEGY_HEDGE=1,
               SLOPE_TIMEFRAMES=["TIMEFRAME_H1", "TIMEFRAME_M15"], REENTRY_COOLDOWN_SECONDS=300,
               ORDER_COOLDOWN_SECONDS=1, MARKET_LOOKBACK_MINUTES=3, RSI_LENGTH=14, MACD_FAST=12, MACD_SLOW=26,
               MACD_SIGNAL=9, PEAK_LOOKBACK=20, PIVOT_WIDTH=2, RSI_PEAK_OB=60, RSI_PEAK_OS=40)


def _modules(contract=True, **over):
    """Live modules as `from constants import ...` leaves them: each holds the names it imported."""
    c = types.ModuleType("constants")
    for k, v in {**CLASSIC, **(LIVE_CONTRACT if contract else {}), "MAGIC": 26116, "DEMO_BRANCH": "demo_x",
                 **over}.items():
        setattr(c, k, v)
    strategy = types.ModuleType("strategy")
    for k in ("OPEN_SCORE_WEIGHTS", "FORCE_CLOSE_SCORE_WEIGHTS", "ENTRY_S", "ENTRY_AGREE_S", "LADDER_S", "FORCE_CLOSE_S",
              "RSI_OVERSOLD", "RSI_OVERBOUGHT", "STRATEGY_HEDGE") + (("FORCE_CLOSE_ENABLED", "MAX_ADDS", "LADDER_TFS",
                                                                     "LADDER_TRIGGER", "LADDER_MULTIPLIERS") if contract else ()):
        setattr(strategy, k, getattr(c, k))
    app = types.ModuleType("app")
    for k in ("SLOPE_TIMEFRAMES", "REENTRY_COOLDOWN_SECONDS", "ORDER_COOLDOWN_SECONDS", "MARKET_LOOKBACK_MINUTES",
              "RSI_LENGTH", "MACD_FAST", "MACD_SLOW", "MACD_SIGNAL", "PEAK_LOOKBACK", "PIVOT_WIDTH", "RSI_PEAK_OB",
              "RSI_PEAK_OS") + (tuple(LIVE_CONTRACT) if contract else ()):
        setattr(app, k, getattr(c, k))
    helper = types.ModuleType("mt5_helper")
    helper.MAGIC, helper.ORDER_COMMENT, helper.DEMO_BRANCH = c.MAGIC, getattr(c, "ORDER_COMMENT", None), c.DEMO_BRANCH
    return types.SimpleNamespace(constants=c, strategy=strategy, app=app, mt5_helper=helper,
                                 indicator=types.ModuleType("indicator"), extra={})


def _design(symbol, name, **kw):
    _, ov = D.design_overrides(symbol, name)
    return BacktestConfig(symbol=symbol, start="2026-10-28 17:00", end="2026-10-30 14:00", **kw).replace(**ov)


def test_a_demo_branch_gets_its_design_from_the_config():
    mods = _modules()
    cfg = _design(SYM, "Top 1")
    pushed = R._apply_config(mods, cfg)
    c, s, a, h = mods.constants, mods.strategy, mods.app, mods.mt5_helper
    assert pushed == R.design_constants(cfg)
    assert (c.TREND_TF, c.VOL_TF, c.VOL_LEN, a.TREND_TF) == ("H1", "H1", 24, "H1")
    assert (c.TARGET_USD_PER_UNIT, c.STOP_LOSS_USD_PER_UNIT, c.TARGET_VOL, c.STOP_VOL) == (None, None, 10.0, 8.0)
    assert (s.FORCE_CLOSE_ENABLED, s.MAX_ADDS, s.LADDER_TRIGGER, a.LOSS_COOLDOWN_S) == (False, 1, "macd_turn", 14400.0)
    assert s.LADDER_TFS == ["M5", "M15", "H1", "H1", "H1"] and s.LADDER_MULTIPLIERS == [1.0, 1.0, 1.0, 1.0]
    assert s.LADDER_TFS is c.LADDER_TFS is a.LADDER_TFS                  # one object, as an import shares it
    assert s.OPEN_SCORE_WEIGHTS == {"H1": 1} and s.ENTRY_AGREE_S == 0.0 and a.LADDER_GAP_VOL == 1.0
    # the slope timeframes: the sections, the trend and the tier whose MACD vote releases the add
    assert a.SLOPE_TIMEFRAMES == ["TIMEFRAME_H1", "TIMEFRAME_M15", "TIMEFRAME_M5"]
    # sized like the backtest: its balance, counted from the day the window starts
    assert (c.VIRTUAL_START_BALANCE, a.VIRTUAL_START_DATE) == (2000.0, "2026-10-28")
    # what labels the bot is the branch's own
    assert (h.MAGIC, h.ORDER_COMMENT, c.DESIGN_NAME) == (26116, None, "live") and not hasattr(h, "TREND_TF")


def test_the_live_design_maps_to_the_contract_defaults():
    pushed = R._apply_config(_modules(), BacktestConfig(symbol=SYM, start="2026-11-11 15:00", end="2026-11-11 16:00"))
    for name in ("FORCE_CLOSE_ENABLED", "TREND_TF", "VOL_TF", "TARGET_USD_PER_UNIT", "STOP_LOSS_USD_PER_UNIT",
                 "MAX_ADDS", "LADDER_TRIGGER", "LADDER_TFS", "LADDER_MULTIPLIERS", "STRATEGY"):
        assert pushed[name] == LIVE_CONTRACT[name], name
    assert pushed["STRATEGY_HEDGE"] == 1 and pushed["VIRTUAL_START_DATE"] == "2026-11-11"
    other = R.design_constants(BacktestConfig(symbol=SYM, target_usd_per_unit=2.5))
    assert (other["TARGET_USD_PER_UNIT"], other["STRATEGY_HEDGE"]) == ("live", 2.5)


def test_what_a_demo_branch_cannot_run_is_refused():
    with pytest.raises(ValueError, match="missing: .*VIRTUAL_START_DATE"):
        R.contract_of(types.SimpleNamespace(**{k: v for k, v in LIVE_CONTRACT.items() if k != "VIRTUAL_START_DATE"}))
    with pytest.raises(ValueError, match="nor of the demo contract: entry_max_spread, fc_rsi_tfs"):
        R._apply_config(_modules(), _design(SYM, "Top 2", entry_max_spread=0.3, fc_rsi_tfs=["H1"]))
    with pytest.raises(ValueError, match="ladder_trigger"):
        R._apply_config(_modules(), _design(SYM, "Top 1").replace(ladder_trigger="rsi_cross"))
    with pytest.raises(ValueError, match="STRATEGY='turtle'"):
        R._apply_config(_modules(STRATEGY="turtle"), _design("BTCUSDm", "Top 2"))
    with pytest.raises(ValueError, match="sleeps exactly 1 s"):
        R._apply_config(_modules(), _design(SYM, "V3-lite", poll_jitter_ms=200))
    # a branch without the contract is the live bot, as before: the designs are refused
    with pytest.raises(ValueError, match="fixed at \\$1 x unit"):
        R._apply_config(_modules(contract=False), _design(SYM, "V3-lite"))
    assert R._apply_config(_modules(contract=False), BacktestConfig(symbol=SYM)) == {}


def test_a_branchs_contract_constants_read_back_as_its_design():
    """contract_overrides is the inverse of design_constants: every design row survives the round trip."""
    for sym in ("XAUUSDm", "BTCUSDm"):
        rows = json.loads(D.designs_file(sym).read_text(encoding="utf-8"))
        for name in rows:
            if name.startswith("Owner"):
                continue                                 # RSI block / RSI force-close: not part of the contract
            cfg = _design(sym, name.split(":")[0])
            consts = R.design_constants(cfg)
            back = BacktestConfig(symbol=sym, start=cfg.start, end=cfg.end, open_weights=cfg.open_weights,
                                  entry_agree_s=cfg.entry_agree_s).replace(
                **R.contract_overrides(types.SimpleNamespace(**consts)))
            again = R.design_constants(back)
            for key in R.CONTRACT_NAMES:
                if key in consts:
                    assert again[key] == consts[key], (sym, name, key)


def test_the_command_line_reads_a_demo_branchs_design(tmp_path, repo_root):
    """`python -m backtesting run/parity/sweep/robust --live-root <demo branch>` runs the branch's own design."""
    from backtesting import cli

    root = _demo_root(tmp_path, repo_root, SYM, **XAU_TOP1)
    args = types.SimpleNamespace(symbol=SYM, start="2026-11-02 22:00", end="2026-11-03 14:00", live_root=str(root),
                                 set=["loss_cooldown_s=600"], balance=None, leverage=None)
    cfg = cli._config(args)
    want = D.design_config(SYM, "Top 1", args.start, args.end)
    for f in ("open_weights", "entry_agree_s", "force_close_enabled", "trend_tf", "vol_tf", "target_usd_per_unit",
              "target_vol", "stop_vol", "vol_cap_usd_per_unit", "max_adds", "ladder_trigger", "ladder_gap_vol"):
        assert getattr(cfg, f) == getattr(want, f), f
    assert cfg.ladder_tfs[:1] == ["M5"] and cfg.ladder_multipliers[:2] == [1.0, 1.0]
    assert cfg.loss_cooldown_s == 600.0                    # --set still wins
    plain = cli._config(types.SimpleNamespace(**{**vars(args), "live_root": str(repo_root), "set": None}))
    assert plain == BacktestConfig.live(SYM, repo_root=repo_root, start=args.start, end=args.end)


def test_ladder_columns_are_named_by_tier_when_a_timeframe_repeats():
    assert R.ladder_rsi_columns(["M1", "M5", "M15", "H1", "H4"]) == ["rsi_M1", "rsi_M5", "rsi_M15", "rsi_H1", "rsi_H4"]
    assert R.ladder_rsi_columns(["M5", "M15", "H1", "H1", "H1"]) == ["rsi_M5", "rsi_M15", "rsi_2_H1", "rsi_3_H1",
                                                                      "rsi_4_H1"]


# ───────────────────────────── the comparison ─────────────────────────────

def _pair(cfg, live_signals, fast_signals, fast_fills=None):
    """A reference result and a fast result over the same polls, identical except for the signals given."""
    n = len(live_signals)
    t = T0 + np.arange(n, dtype=np.int64) * 1000
    cols = ["t_ms", "signal", "fresh", "open_score", "fc_score", "book_score", "n_pos", "profit", "units",
            "entry_allowed"] + R.ladder_rsi_columns(cfg.ladder_tfs)
    rows = [(int(t[i]), live_signals[i], True, 2.0, 0.0, np.nan, 0, 0.0, 1, True) + (55.0,) * len(cfg.ladder_tfs)
            for i in range(n)]
    ref = types.SimpleNamespace(trace=pd.DataFrame(rows, columns=cols), deals=pd.DataFrame(columns=[
        "t_ms", "entry", "type", "volume", "price", "profit"]), final_balance=2000.0, errors=[], refused={})
    tr = np.zeros((n, K.T_N))
    tr[:, K.T_T], tr[:, K.T_SIGNAL], tr[:, K.T_OPEN_SCORE], tr[:, K.T_UNITS] = t, fast_signals, 2.0, 1
    tr[:, K.T_ENTRY_ALLOWED] = 1.0
    for q in range(min(cfg.n_ladder_adds, K.T_N - K.T_RSI0)):
        tr[:, K.T_RSI0 + q] = 55.0          # the kernel writes the tiers it can use, the rest stay 0
    fills = fast_fills if fast_fills is not None else pd.DataFrame(columns=["time", "action", "side", "lots", "price",
                                                                             "profit"])
    fast = types.SimpleNamespace(trace=tr, fills=fills, scalars={"final_balance": 2000.0})
    return ref, fast


def test_the_ladder_rsi_is_compared_for_the_tiers_the_kernel_writes_only():
    for name, adds in (("V3-lite", 0), ("Top 1", 1)):     # no adds; one add on a repeated-timeframe tier list
        cfg = _design(SYM, name)
        assert cfg.n_ladder_adds == adds
        ref, fast = _pair(cfg, [0] * 5, [0] * 5)
        rep = parity.compare(cfg, ref, fast)
        assert rep.ok and rep.rsi_max_abs_diff == 0.0, str(rep)


def test_an_entry_held_back_inside_the_strategy_is_accepted_only_when_asked():
    """The kernel writes its signal before the execution-time filters (trend, window ...): a branch that holds the
    entry back inside its strategy says 'do nothing' there. With no order sent either way, that is the same bot."""
    cfg = _design(SYM, "V3-lite")
    ref, fast = _pair(cfg, [0, 0, 0, 0], [0, 1, 2, 0])
    strict = parity.compare(cfg, ref, fast)
    assert not strict.ok and strict.signal_mismatches == 2 and strict.first_divergence_ms == T0 + 1000
    loose = parity.compare(cfg, ref, fast, blocked_entries_ok=True)
    assert loose.ok and loose.signal_mismatches == 0 and loose.signal_blocked_entry == 2, str(loose)
    # an entry the kernel did send is a difference whatever the flag
    fills = pd.DataFrame({"time": pd.to_datetime([T0 + 1000], unit="ms", utc=True), "action": ["open"],
                          "side": ["BUY"], "lots": [0.01], "price": [4000.0], "profit": [0.0]})
    ref, fast = _pair(cfg, [0, 0, 0, 0], [0, 1, 0, 0], fast_fills=fills)
    rep = parity.compare(cfg, ref, fast, blocked_entries_ok=True)
    assert not rep.ok and rep.signal_mismatches == 1 and rep.signal_blocked_entry == 0
    # at one time the signal is named before the fill it led to
    assert rep.first_divergence.startswith("signal at") and rep.first_divergence_ms == T0 + 1000


def test_the_cooldown_state_is_compared_when_asked():
    cfg = _design(SYM, "V3-lite")
    ref, fast = _pair(cfg, [0] * 4, [0] * 4)
    fast.trace[2:, K.T_ENTRY_ALLOWED] = 0.0
    assert parity.compare(cfg, ref, fast).ok
    rep = parity.compare(cfg, ref, fast, check_entry_allowed=True)
    assert not rep.ok and rep.entry_allowed_mismatches == 2 and rep.first_divergence.startswith("entry_allowed")


# ───────────────────────────── demo_parity helpers ─────────────────────────────

def test_the_designs_are_read_from_the_round4_file():
    name, ov = D.design_overrides(SYM, "top1")
    assert name.startswith("Top 1:") and ov["max_adds"] == 1 and ov["ladder_trigger"] == "macd_turn"
    with pytest.raises(SystemExit, match="no design"):
        D.design_overrides(SYM, "Top 9")
    want = {("XAUUSDm", "V3-lite"): (2.0, 8.0, 8.0, 0.0, 43200.0, 0), ("XAUUSDm", "Top 1"): (0.0, 10.0, 8.0, 0.0, 14400.0, 1),
            ("XAUUSDm", "Top 2"): (0.0, 8.0, 4.0, 12.0, 43200.0, 0), ("BTCUSDm", "Top 2"): (0.0, 10.0, 8.0, 12.0, 14400.0, 0)}
    for (sym, design), values in want.items():
        cfg = D.design_config(sym, design, "2026-10-28 17:00", "2026-10-29 00:00")
        assert (cfg.entry_agree_s, cfg.target_vol, cfg.stop_vol, cfg.vol_cap_usd_per_unit, cfg.loss_cooldown_s,
                cfg.n_ladder_adds) == values, (sym, design)
        assert (cfg.open_weights, cfg.trend_tf, cfg.vol_tf, cfg.force_close_enabled, cfg.target_usd_per_unit) == \
            ({"H1": (1.0, 1.0)}, "H1", "H1", False, None)
        assert (cfg.start, cfg.end, cfg.symbol) == ("2026-10-28 17:00", "2026-10-29 00:00", sym)


def _demo_root(tmp_path, repo_root, symbol, **design):
    """A demo branch's constants.py (the live one, the contract's defaults, then a design block) and symbols.json."""
    text = (repo_root / "constants.py").read_text(encoding="utf-8")
    text += "\nDEMO_BRANCH = 'demo_test'\nMAGIC = 4242\n"
    text += "".join(f"{k} = {v!r}\n" for k, v in LIVE_CONTRACT.items())
    text += "".join(f"{k} = {v!r}\n" for k, v in design.items())
    (tmp_path / "constants.py").write_text(text, encoding="utf-8")
    sj = json.loads((repo_root / "symbols.json").read_text(encoding="utf-8"))
    sj["symbols"][0]["symbol"] = symbol
    if symbol == "BTCUSDm":
        sj["trading_window"].update(start_day="Monday", start_time="00:00", end_day="Sunday", end_time="23:59")
    (tmp_path / "symbols.json").write_text(json.dumps(sj), encoding="utf-8")
    return tmp_path


XAU_TOP1 = dict(OPEN_SCORE_WEIGHTS={"H1": 1}, ENTRY_AGREE_S=0, FORCE_CLOSE_ENABLED=False, TREND_TF="H1", VOL_TF="H1",
                VOL_LEN=24, TARGET_USD_PER_UNIT=None, STOP_LOSS_USD_PER_UNIT=None, TARGET_VOL=10.0, STOP_VOL=8.0,
                VOL_CAP_USD_PER_UNIT=0.0, LOSS_COOLDOWN_S=14400, MAX_ADDS=1, LADDER_TRIGGER="macd_turn",
                LADDER_TFS=["M5", "M15", "H1", "H1", "H1"], LADDER_GAP_VOL=1.0, LADDER_MULTIPLIERS=[1, 1, 1, 1])


def test_the_static_check_compares_the_branch_with_the_design(tmp_path, repo_root):
    for name in ("good", "bad", "v3", "btc", "xau"):
        (tmp_path / name).mkdir()
    cfg = D.design_config(SYM, "Top 1", "2026-11-02 22:00", "2026-11-03 14:00")
    good = _demo_root(tmp_path / "good", repo_root, SYM, **XAU_TOP1)
    assert D.static_check(cfg, good) == []
    labels = D.branch_labels(good)
    assert (labels["magic"], labels["comment"], labels["strategy"]) == (4242, "demo_test", "basket")
    bad = _demo_root(tmp_path / "bad", repo_root, SYM, **{**XAU_TOP1, "TARGET_VOL": 8.0, "LADDER_MULTIPLIERS": None,
                                                         "TARGET_USD_PER_UNIT": "live"})
    problems = D.static_check(cfg, bad)
    assert any(p.startswith("TARGET_VOL") for p in problems) and any("LADDER_MULTIPLIERS" in p for p in problems)
    assert any(p.startswith("TARGET_USD_PER_UNIT") for p in problems) and len(problems) == 3
    # levers that cannot act are not compared: V3-lite has no adds, so the ladder settings are free
    v3 = D.design_config(SYM, "V3-lite", "2026-11-02 22:00", "2026-11-03 14:00")
    root = _demo_root(tmp_path / "v3", repo_root, SYM, OPEN_SCORE_WEIGHTS={"H1": 1}, ENTRY_AGREE_S=2,
                      FORCE_CLOSE_ENABLED=False, TREND_TF="H1", VOL_TF="H1", TARGET_USD_PER_UNIT=None, TARGET_VOL=8.0,
                      STOP_VOL=8.0, LOSS_COOLDOWN_S=43200, MAX_ADDS=0, LADDER_TRIGGER="macd_turn")
    assert D.static_check(v3, root) == []
    btc = _demo_root(tmp_path / "btc", repo_root, "BTCUSDm", OPEN_SCORE_WEIGHTS={"H1": 1}, ENTRY_AGREE_S=0,
                     FORCE_CLOSE_ENABLED=False, TREND_TF="H1", VOL_TF="H1", TARGET_USD_PER_UNIT=None, TARGET_VOL=10.0,
                     STOP_VOL=8.0, VOL_CAP_USD_PER_UNIT=12.0, LOSS_COOLDOWN_S=14400, MAX_ADDS=0)
    btc_cfg = D.design_config("BTCUSDm", "Top 2", "2026-09-03 14:00", "2026-09-04 13:00")
    assert D.static_check(btc_cfg, btc) == []
    # a gold branch checked as a BTC one: its symbols.json does not even trade BTC
    xau = _demo_root(tmp_path / "xau", repo_root, SYM, **XAU_TOP1)
    assert any("no active BTCUSDm entry" in p for p in D.static_check(btc_cfg, xau))


def test_a_turtle_branch_is_refused_before_anything_runs(tmp_path, repo_root, fixture_store):
    root = _demo_root(tmp_path, repo_root, "BTCUSDm", STRATEGY="turtle")
    for name in ("app.py", "strategy.py", "indicator.py", "mt5_helper.py"):
        (tmp_path / name).write_text("raise SystemExit('must not be imported')\n")
    with pytest.raises(SystemExit, match="STRATEGY='turtle'.*no counterpart"):
        D.run_demo_parity(root, "BTCUSDm", "Top 2", "2026-11-09 06:00", "2026-11-09 06:05", store_dir=fixture_store)


def test_the_shared_account_holds_what_an_isolated_bot_must_ignore():
    cfg = D.design_config(SYM, "Top 2", "2026-10-21 06:00", "2026-10-22 14:00")
    kw = D.shared_account(cfg, 26116)
    day0 = store.to_ms("2026-10-21")
    own = [d for d in kw["history"] if d["magic"] == 26116]
    assert own and all(d["t_ms"] < day0 for d in own) and sum(d.get("profit", 0) for d in own) > 0   # a win, before
    assert all(d["magic"] != 26116 for d in kw["scheduled"])
    assert all(store.to_ms(cfg.start) < d["t_ms"] < store.to_ms(cfg.end) for d in kw["scheduled"])
    assert {d["symbol"] for d in kw["scheduled"]} == {SYM, "BTCUSDm"}
    assert all(p["magic"] != 26116 for p in kw["positions"]) and kw["account_balance"] > cfg.initial_balance


def test_the_isolation_check_names_deals_without_the_bots_magic():
    deals = pd.DataFrame([dict(entry="in", type=0, magic=7, comment="c", foreign=np.nan),
                          dict(entry="out", type=0, magic=0, comment="", foreign=False),
                          dict(entry="out", type=1, magic=7, comment="c", foreign=True)])
    ref = types.SimpleNamespace(deals=deals, invalid_requests=1)
    problems = D.isolation_check(ref, dict(magic=7, comment="c"))
    assert any("did not open" in p for p in problems)
    assert any("1 of 1 closing deals carry magic [0]" in p for p in problems)
    assert any("refuses outright" in p for p in problems) and len(problems) == 3
    assert D.isolation_check(types.SimpleNamespace(deals=deals.iloc[:1], invalid_requests=0),
                             dict(magic=7, comment="c")) == []


# ───────────────────────────── one short replay through a real app.py ─────────────────────────────

def test_a_branch_with_the_contract_at_its_defaults_replays_like_the_live_bot(tmp_path, repo_root, fixture_store):
    """
    The live bot's own code with the contract's constants added at their defaults (no logic change): on an
    account of its own it is the live bot, so it matches the fast engine exactly. On the shared account it is
    caught: it adopts the positions it finds on the symbol (here a buy and a sell, so it never trades) and sends
    its orders without the magic number the shared-account check asks for.
    """
    import shutil

    for name in ("app.py", "strategy.py", "indicator.py", "mt5_helper.py", "symbols.json"):
        shutil.copy(repo_root / name, tmp_path / name)
    text = (repo_root / "constants.py").read_text(encoding="utf-8")
    text += "\nDEMO_BRANCH = 'demo_test_defaults'\nMAGIC = 4243\n" + "".join(f"{k} = {v!r}\n" for k, v in
                                                                            LIVE_CONTRACT.items())
    (tmp_path / "constants.py").write_text(text, encoding="utf-8")
    window = (SYM, "Live", "2026-11-11 15:00", "2026-11-11 15:03")
    alone = D.run_demo_parity(tmp_path, *window, store_dir=fixture_store, isolation=False)
    assert alone.ok, D.format_result(alone)
    assert alone.report.fills_ref == alone.report.fills_fast == 2 and not alone.static_problems
    assert alone.ref.contract["TARGET_USD_PER_UNIT"] == "live" and alone.ref.contract["VIRTUAL_START_DATE"] == "2026-11-11"
    text = D.format_result(alone)
    assert "VERDICT: PASS" in text and "target" in text
    json.dumps(D.to_json(alone), default=str)
    shared = D.run_demo_parity(tmp_path, *window, store_dir=fixture_store, isolation=True)
    assert not shared.ok and not shared.report.ok and shared.report.fills_ref == 0 < shared.report.fills_fast
    assert shared.report.first_divergence_ms == store.to_ms("2026-11-11 15:00:01")
    assert shared.ref.account_balance == pytest.approx(10_000.0 + 2 * D.FOREIGN_PROFIT)
    assert "VERDICT: FAIL" in D.format_result(shared)
