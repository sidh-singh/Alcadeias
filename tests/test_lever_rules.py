"""
Engine-level tests of the experimental levers and of every setting the live code fixes.

The what-if tables change the rules through ``BacktestConfig`` fields the live bot does not
have (confirmation times, holds, filters, split weights, closed-bar signals ...) or runs
with one hard-coded value (thresholds, indicator lengths, the cooldown). There is no
``app.py`` behaviour to compare those runs with, so the kernel's own logic is all that
stands behind the numbers. This module pins that logic down on the bundled real ticks:

* an independent replay: the documented decision rules restated in plain Python, driven by
  what each poll of the kernel's trace shows (scores, quote, ladder RSI), must produce the
  kernel's signal on every poll and its fills, for several lever combinations at once;
* one property per lever that fails if the lever is ignored, scaled wrongly, applied to
  the wrong side or a poll early or late;
* the slope signs and ladder RSI behind the scores, against the live ``indicator.py``
  functions: on closed bars only for the closed-bar levers, and for indicator settings
  other than the live ones;
* a mirror test: the same ticks reflected in price must give the same baskets with BUY
  and SELL exchanged;
* every lever at its off value, and at values that cannot bite, leaves the live run as it is.

Every test runs the fast engine in tick mode and reads its fills, baskets or poll trace.
The same tests hold for both strategy variants (``ALCADEIAS_LIVE_ROOT``); where a test is
about one exit rule it sets that exit explicitly.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

import constants as live_constants
from indicator import Indicator

from backtesting.engine import fast
from backtesting.engine import kernels as K

IND = Indicator()
SYMBOLS = ("XAUUSDm", "BTCUSDm")
ALL_TFS = ("M1", "M5", "M15", "H1", "H4")

# The live scores (H1 + M15) turn a handful of times in a fixture window, which gives four or
# five baskets. On M1 they turn every few minutes; with a short cooldown and wide ladder
# levels the same 45 to 60 minutes hold dozens of baskets in both directions. The balance is
# large enough that no order is ever refused for margin.
QUICK = dict(open_weights={"M1": 1}, fc_weights={"M1": 1}, reentry_cooldown_s=5.0,
             fixed_units=2, initial_balance=1e6)
WIDE_LADDER = dict(rsi_oversold=45.0, rsi_overbought=55.0)
# The two profit exits, stated in full so a test means the same on either variant.
TARGET = dict(target_usd_per_unit=1.0, book_enabled=False)
# A book score on M15 is against an M1 basket for minutes at a time, so baskets in profit are booked often.
BOOK = dict(target_usd_per_unit=None, book_enabled=True, book_weights={"M15": 1}, book_s=1.0,
            profit_protect_usd_per_unit=0.3)
EXITS = {"target": TARGET, "book": BOOK}
# a price distance that means about the same on both instruments (ladder_min_gap is in price units)
PRICE_STEP = {"XAUUSDm": 0.3, "BTCUSDm": 30.0}

# exits in the order the kernel tries them on a poll; a ladder add is considered only when none fires
EXIT_ORDER = ("stop_loss", "target", "book", "force_close", "time_stop")

_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
_TRACE_COLUMNS = {"t": K.T_T, "signal": K.T_SIGNAL, "open": K.T_OPEN_SCORE, "fc": K.T_FC_SCORE,
                  "book": K.T_BOOK_SCORE, "bid": K.T_BID, "ask": K.T_ASK, "npos": K.T_NPOS,
                  "profit": K.T_PROFIT, "units": K.T_UNITS, "allowed": K.T_ENTRY_ALLOWED, "brake": K.T_BRAKE}


# ───────────────────────────── helpers ─────────────────────────────

def _ms(times) -> np.ndarray:
    """Epoch milliseconds of a column of UTC timestamps."""
    if len(times) == 0:                 # an empty fill log has no timezone to subtract with
        return np.zeros(0, np.int64)
    return np.asarray((pd.DatetimeIndex(times) - _EPOCH) // pd.Timedelta(milliseconds=1), dtype=np.int64)


def _run(engine_run, cfg):
    """The fast engine on every tick of the fixture window, with the poll trace."""
    return _checked(engine_run(cfg, mode="ticks", trace=True))


def _checked(res):
    """Nothing these tests do not model may have happened in a run: no refused order, no stop-out, no closed market."""
    c = res.counters
    assert c["trace_overflow"] == 0 and c["margin_rejects"] == 0 and c["polls_order_blocked_close_only"] == 0
    assert c["closes_data_hole"] == 0 and res.scalars["stopped_out"] == 0
    # one poll per loop pass: no closed-market stretch inside the fixture windows
    assert np.diff(res.trace[:, K.T_T]).max() <= 10_000
    return res


def _same_fills(a, b) -> None:
    pd.testing.assert_frame_equal(a.fills.reset_index(drop=True), b.fills.reset_index(drop=True))
    pd.testing.assert_frame_equal(a.baskets.reset_index(drop=True), b.baskets.reset_index(drop=True))


def _polls(res) -> pd.DataFrame:
    """
    The poll trace as a frame, with the basket the kernel held at each poll rebuilt from its
    own fill log: side (+1 / -1, 0 while flat), age, unit, positions and lots so far, the last
    close, and what was filled on that very poll (``opened``, ``added``, ``reason`` of a close).
    A poll's trace row is written before its order, so the poll that opens a basket is still
    flat and the poll that closes it still holds it.
    """
    tr = res.trace
    p = pd.DataFrame({name: tr[:, col] for name, col in _TRACE_COLUMNS.items()})
    for q in range(K.T_N - K.T_RSI0):
        p[f"rsi{q}"] = tr[:, K.T_RSI0 + q]
    p["t"] = p["t"].astype(np.int64)
    p["signal"] = p["signal"].astype(int)
    p["npos"] = p["npos"].astype(int)
    t = p["t"].to_numpy()
    n = len(p)
    basket = np.full(n, -1)
    side = np.zeros(n, int)
    open_t = np.zeros(n, np.int64)
    b_units = np.zeros(n, int)
    count = np.zeros(n, int)
    lots = np.zeros(n)
    lot_units = np.zeros(n)
    last_close = np.full(n, -(1 << 60), np.int64)
    opened = np.zeros(n, bool)
    added = np.zeros(n, bool)
    reason = np.full(n, "", dtype=object)
    f = res.fills.assign(t=_ms(res.fills["time"]))
    for b, g in f.groupby("basket", sort=True):
        ins, outs = g[g["action"] != "close"], g[g["action"] == "close"]
        t0 = int(ins["t"].iloc[0])
        lo = int(np.searchsorted(t, t0, side="right"))
        hi = int(np.searchsorted(t, int(outs["t"].iloc[0]), side="right")) if len(outs) else n
        basket[lo:hi] = b
        side[lo:hi] = 1 if ins["side"].iloc[0] == "BUY" else -1
        open_t[lo:hi] = t0
        b_units[lo:hi] = int(ins["units"].iloc[0])
        for action, ft, fl in zip(ins["action"], ins["t"], ins["lots"]):
            at = int(np.searchsorted(t, int(ft)))
            assert t[at] == ft, "a fill must sit on a traced poll"
            (opened if action == "open" else added)[at] = True
            count[at + 1:hi] += 1
            lots[at + 1:hi] += fl
            lot_units[at + 1:hi] += fl / res.cfg.mtqty        # the kernel's own running sum, same order
        if len(outs):
            assert outs["t"].nunique() == 1 and t[hi - 1] == outs["t"].iloc[0]
            reason[hi - 1] = outs["reason"].iloc[0]
            last_close[hi:] = int(outs["t"].iloc[0])
    p["basket"], p["side"], p["open_t"], p["b_units"] = basket, side, open_t, b_units
    p["count"], p["lots"], p["lot_units"] = count, lots, lot_units
    p["last_close"], p["opened"], p["added"], p["reason"] = last_close, opened, added, reason
    p["age"] = np.where(side != 0, t - open_t, 0)
    # the trace and the fill log tell the same story about what was held
    assert (p["npos"] == p["count"] * p["side"]).all()
    return p


def _entry_direction(cfg, p) -> np.ndarray:
    """+1 / -1 where the open score reaches ``entry_s`` and the force-close score agrees by ``entry_agree_s``."""
    up = (p["open"] >= cfg.entry_s) & (p["fc"] >= cfg.entry_agree_s)
    down = (p["open"] <= -cfg.entry_s) & (p["fc"] <= -cfg.entry_agree_s)
    return np.where(up, 1, np.where(down, -1, 0))


def _since(t, key) -> np.ndarray:
    """For every row, the time of the first row of the unbroken run of equal ``key`` values it belongs to."""
    t, key = np.asarray(t), np.asarray(key)
    first = np.r_[True, key[1:] != key[:-1]]
    return t[np.maximum.accumulate(np.where(first, np.arange(len(t)), 0))]


def _conditions(cfg, p) -> pd.DataFrame:
    """
    The bare exit conditions on every poll (all False while flat), before the hold and
    confirmation levers and before the order of precedence: ``stop_loss`` and ``target`` on the
    floating P/L, ``book`` (profit over the bar and the book score against the basket),
    ``force_close`` (the force-close score against it), ``time_stop`` (age).
    """
    held = p["side"] != 0
    c = pd.DataFrame(index=p.index)
    c["stop_loss"] = held & (cfg.stop_loss_usd_per_unit is not None) & \
        (p["profit"] <= -(cfg.stop_loss_usd_per_unit or 0.0) * p["b_units"])
    goal = (cfg.target_usd_per_unit or 0.0) * (p["lot_units"] if cfg.target_per_lot else p["b_units"])
    c["target"] = held & (cfg.target_usd_per_unit is not None) & (p["profit"] > goal)
    c["book"] = held & cfg.book_enabled & (p["profit"] > cfg.profit_protect_usd_per_unit * p["b_units"]) & \
        (p["book"] * p["side"] <= -cfg.book_s)
    c["force_close"] = held & cfg.force_close_enabled & (p["fc"] * p["side"] <= -cfg.force_close_s)
    c["time_stop"] = held & (cfg.max_hold_s > 0) & (p["age"] >= cfg.max_hold_s * 1000)
    return c


def _exit_rules(cfg, p) -> pd.DataFrame:
    """Which exit rules fire on each poll: the bare conditions with the hold and confirmation levers applied."""
    c = _conditions(cfg, p)
    old_enough = p["age"] >= cfg.min_hold_s * 1000
    confirmed = (p["t"] - _since(p["t"], np.where(c["force_close"], p["basket"], -1))) >= cfg.fc_confirm_s * 1000
    c["book"] &= old_enough
    c["force_close"] &= old_enough & confirmed
    return c[list(EXIT_ORDER)]


def _expected_exit(cfg, p) -> np.ndarray:
    """The reason each poll must close with ('' = the basket stays): the first rule in EXIT_ORDER that fires."""
    rules = _exit_rules(cfg, p)
    out = np.full(len(p), "", dtype=object)
    for name in reversed(EXIT_ORDER):
        out[rules[name].to_numpy()] = name
    return out


def _tier_rsi(cfg, p) -> np.ndarray:
    """The RSI the basket's next ladder tier reads on each poll (NaN while flat or with the ladder used up)."""
    rsi = np.full(len(p), np.nan)
    for q in range(min(cfg.n_ladder_adds, K.T_N - K.T_RSI0)):
        sel = (p["count"] == q + 1).to_numpy()
        rsi[sel] = p[f"rsi{q}"].to_numpy()[sel]
    return rsi


def _tier_hit(cfg, p) -> np.ndarray:
    """Polls on which that RSI is at or beyond its level: oversold for a BUY basket, overbought for a SELL basket."""
    rsi, side = _tier_rsi(cfg, p), p["side"].to_numpy()
    with np.errstate(invalid="ignore"):
        return ((side > 0) & (rsi <= cfg.rsi_oversold)) | ((side < 0) & (rsi >= cfg.rsi_overbought))


def _expected_add(cfg, p) -> np.ndarray:
    """
    Polls on which the ladder must add when no spacing lever is set: no exit fires, the tier is
    hit and the open score is less than ``ladder_s`` against the basket.
    """
    assert cfg.ladder_min_gap <= 0 and cfg.ladder_min_interval_s <= 0
    gate = (p["open"] * p["side"] > -cfg.ladder_s).to_numpy()
    return _tier_hit(cfg, p) & gate & (_expected_exit(cfg, p) == "")


def _tick_seconds(prep, t) -> np.ndarray:
    """Whole-second time of the latest tick at each poll: the broker's clock the kernel judges time-of-day on."""
    return prep.t_ms[np.searchsorted(prep.t_ms, np.asarray(t, np.int64), side="right") - 1] // 1000


# ───────────────────────────── the independent replay ─────────────────────────────

def _cents(x: float) -> float:
    """Half away from zero, to cents: how MT5 reports a position's profit."""
    return math.floor(x * 100.0 + 0.5) / 100.0 if x >= 0 else -math.floor(-x * 100.0 + 0.5) / 100.0


def _replay(cfg, trace, tick_s=None):
    """
    The decision rules of the backtester's documentation, restated in plain Python.

    Driven only by what a poll shows the bot -- the three scores, the quote, the unit, the
    brake and the ladder RSI values, all read from the kernel's trace -- while the position,
    the cooldown and the confirmation timers are kept here. Returns the signal expected on
    every poll, the floating P/L held on every poll, and the fills as
    (time, action, side, lots, price, reason).

    Rules, in order. Flat: the entry direction is +1 / -1 when the open score reaches
    ``entry_s`` and the force-close score agrees by ``entry_agree_s``; it is signalled once the
    cooldown since the last close has passed; the order is sent unless the brake, the
    direction filter, the hour filter or the entry confirmation holds it back. In a basket:
    stop-loss, target, book, force-close, time stop; failing all of those, a ladder add when
    the tier's RSI is beyond its level, the open score is less than ``ladder_s`` adverse and the
    spacing levers allow it.
    """
    contract = cfg.spec.contract_size
    hours = None if cfg.entry_hours_utc is None else {int(h) % 24 for h in cfg.entry_hours_utc}
    tiers = cfg.n_ladder_adds
    mult = list(cfg.ladder_multipliers)
    signals = np.zeros(len(trace), int)
    profits = np.zeros(len(trace))
    fills = []
    pos = []                         # (lots, price) of every open position, oldest first
    side = units = 0
    opened_t = last_fill_t = 0
    last_fill_px = lot_units = 0.0
    last_close = None
    held_dir, dir_since = 0, 0       # entry direction seen on the flat polls, and since when
    fc_since = None                  # since when the force-close condition has held without a break
    prev_t = None
    for i, row in enumerate(trace):
        t = int(row[K.T_T])
        bid, ask = row[K.T_BID], row[K.T_ASK]
        o, f, bk = row[K.T_OPEN_SCORE], row[K.T_FC_SCORE], row[K.T_BOOK_SCORE]
        if prev_t is not None and t - prev_t > cfg.market_lookback_s * 1000:
            held_dir, fc_since = 0, None          # the market was closed in between: both timers start again
        prev_t = t
        if not pos:
            want = 0
            if o >= cfg.entry_s and f >= cfg.entry_agree_s:
                want = 1
            elif o <= -cfg.entry_s and f <= -cfg.entry_agree_s:
                want = -1
            if want != held_dir:
                held_dir, dir_since = want, t
            if want and (last_close is None or t - last_close >= cfg.reentry_cooldown_s * 1000):
                signals[i] = 1 if want > 0 else 2
                refused = (row[K.T_BRAKE] > 0
                           or not (cfg.allow_long if want > 0 else cfg.allow_short)
                           or (hours is not None and (int(tick_s[i]) % 86400) // 3600 not in hours)
                           or t - dir_since < cfg.entry_confirm_s * 1000)
                if not refused:
                    side, units = want, int(row[K.T_UNITS])
                    lots = _cents(units * cfg.mtqty)
                    price = ask if side > 0 else bid
                    pos = [(lots, price)]
                    opened_t = last_fill_t = t
                    last_fill_px, lot_units, fc_since = price, lots / cfg.mtqty, None
                    fills.append((t, "open", side, lots, price, ""))
            continue

        held_dir = 0
        profit = _cents(sum(_cents(((bid - px) if side > 0 else (px - ask)) * lots * contract) for lots, px in pos))
        profits[i] = profit
        age = t - opened_t
        fc_hit = cfg.force_close_enabled and ((f <= -cfg.force_close_s) if side > 0 else (f >= cfg.force_close_s))
        if not fc_hit:
            fc_since = None
        elif fc_since is None:
            fc_since = t
        book_hit = cfg.book_enabled and profit > cfg.profit_protect_usd_per_unit * units and \
            ((bk <= -cfg.book_s) if side > 0 else (bk >= cfg.book_s))
        old_enough = age >= cfg.min_hold_s * 1000
        reason = ""
        if cfg.stop_loss_usd_per_unit is not None and profit <= -cfg.stop_loss_usd_per_unit * units:
            reason = "stop_loss"
        elif cfg.target_usd_per_unit is not None and \
                profit > cfg.target_usd_per_unit * (lot_units if cfg.target_per_lot else units):
            reason = "target"
        elif book_hit and old_enough:
            reason = "book"
        elif fc_hit and old_enough and t - fc_since >= cfg.fc_confirm_s * 1000:
            reason = "force_close"
        elif cfg.max_hold_s > 0 and age >= cfg.max_hold_s * 1000:
            reason = "time_stop"
        if reason:
            signals[i] = 3 if side > 0 else 4
            fills.append((t, "close", side, round(sum(lots for lots, _ in pos), 2), bid if side > 0 else ask, reason))
            pos, side, last_close, fc_since = [], 0, t, None
            continue
        n = len(pos)
        if n > tiers:
            continue
        rsi = row[K.T_RSI0 + n - 1]
        price = ask if side > 0 else bid
        hit = (rsi <= cfg.rsi_oversold) if side > 0 else (rsi >= cfg.rsi_overbought)
        gate = (o > -cfg.ladder_s) if side > 0 else (o < cfg.ladder_s)
        moved = (last_fill_px - price) if side > 0 else (price - last_fill_px)
        spaced = (cfg.ladder_min_gap <= 0 or moved >= cfg.ladder_min_gap) and \
            (cfg.ladder_min_interval_s <= 0 or t - last_fill_t >= cfg.ladder_min_interval_s * 1000)
        if hit and gate and spaced:
            signals[i] = 5 if side > 0 else 6
            lots = _cents(mult[min(n, len(mult) - 1)] * units * cfg.mtqty)
            pos.append((lots, price))
            last_fill_t, last_fill_px = t, price
            lot_units += lots / cfg.mtqty
            fills.append((t, "add", side, lots, price, ""))
    return signals, profits, fills


def _fill_list(res) -> list:
    """The kernel's fill log in the replay's shape (it writes one close row per position: taken together here)."""
    f = res.fills.assign(t=_ms(res.fills["time"]))
    out, closed = [], set()
    for r in f.itertuples():
        side = 1 if r.side == "BUY" else -1
        if r.action != "close":
            out.append((int(r.t), r.action, side, float(r.lots), float(r.price), ""))
        elif r.basket not in closed:
            closed.add(r.basket)
            lots = round(float(f.loc[(f["basket"] == r.basket) & (f["action"] == "close"), "lots"].sum()), 2)
            out.append((int(r.t), "close", side, lots, float(r.price), r.reason))
    return out


def _replay_agrees(cfg, res, tick_s=None) -> str:
    """'' when the replay reproduces the run, else a description of the first difference."""
    signals, profits, fills = _replay(cfg, res.trace, tick_s)
    got = res.trace[:, K.T_SIGNAL].astype(int)
    bad = np.flatnonzero(signals != got)
    if len(bad):
        i = int(bad[0])
        when = pd.Timestamp(int(res.trace[i, K.T_T]), unit="ms")
        return (f"{when}: the rules give {fast.SIGNAL_NAMES[int(signals[i])]}, "
                f"the kernel {fast.SIGNAL_NAMES[int(got[i])]} ({len(bad)} polls differ)")
    worst = float(np.max(np.abs(profits - res.trace[:, K.T_PROFIT])))
    if worst > 1e-9:
        return f"floating P/L differs by up to {worst}"
    mine, theirs = fills, _fill_list(res)
    for a, b in zip(mine, theirs):
        if a != b:
            return f"fill differs: the rules give {a}, the kernel {b}"
    if len(mine) != len(theirs):
        return f"{len(mine)} fills by the rules, {len(theirs)} in the kernel"
    return ""


# the configuration fields the replay's rules read (the others act through the scores and RSI in the trace)
RULE_FIELDS = ("entry_s", "entry_agree_s", "ladder_s", "force_close_s", "book_s", "target_usd_per_unit",
               "book_enabled", "profit_protect_usd_per_unit", "force_close_enabled", "rsi_oversold",
               "rsi_overbought", "ladder_multipliers", "reentry_cooldown_s", "min_hold_s", "fc_confirm_s",
               "entry_confirm_s", "stop_loss_usd_per_unit", "ladder_min_gap", "ladder_min_interval_s",
               "max_hold_s", "target_per_lot", "max_adds", "allow_long", "allow_short")


def _combinations(symbol: str) -> dict:
    """name -> (base settings, levers under test). The base only makes the window busy; every lever must bite."""
    step = PRICE_STEP[symbol]
    busy = dict(QUICK, **WIDE_LADDER)
    return {
        "live settings": ({}, {}),
        "M1 scores, short cooldown": (
            dict(open_weights={"M1": 1}, fc_weights={"M1": 1}, fixed_units=2, initial_balance=1e6),
            dict(reentry_cooldown_s=5.0)),
        "confirmations, hold, time stop": (
            busy, dict(entry_confirm_s=9.0, fc_confirm_s=7.0, min_hold_s=40.0, max_hold_s=200.0)),
        "stop, spacing, capped flat ladder": (
            dict(busy, **TARGET),
            dict(stop_loss_usd_per_unit=4.0, ladder_min_gap=step / 3, ladder_min_interval_s=10.0, max_adds=2,
                 ladder_multipliers=[1, 1, 2, 2])),
        "book with a target, short hold": (
            busy, dict(BOOK, target_usd_per_unit=1.0, min_hold_s=10.0, stop_loss_usd_per_unit=2.5)),
        "book on two timeframes": (
            dict(busy, target_usd_per_unit=None, book_enabled=True, book_weights={"M15": 1, "M5": 1}),
            dict(book_s=3.0, profit_protect_usd_per_unit=0.4)),
        "entry and force-close thresholds": (
            dict(busy, **TARGET, open_weights={"M1": 1, "M5": 1}, reentry_cooldown_s=20.0),
            dict(entry_s=4.0, entry_agree_s=1.0, force_close_s=2.0)),
        "force-close on two timeframes": (
            dict(busy, **TARGET, fc_weights={"M1": 1, "M5": 1}), dict(force_close_s=4.0, entry_agree_s=0.0)),
        "target per lot, no force-close, ladder gate lifted": (
            dict(busy, **TARGET),
            dict(target_per_lot=True, force_close_enabled=False, stop_loss_usd_per_unit=4.0,
                 ladder_min_interval_s=10.0, ladder_s=3.0)),
        "long only, closed bars, split weights": (
            dict(QUICK, rsi_oversold=45.0, open_weights={"M5": [1, 0], "M1": [0, 1]}, slope_on_closed_bars=True,
                 ladder_on_closed_bars=True),
            dict(allow_short=False, max_hold_s=240.0)),
        "short only, other ladder timeframes": (
            dict(QUICK, ladder_tfs=["M1", "M1", "M5"]),
            dict(allow_long=False, entry_confirm_s=4.0, rsi_overbought=52.0)),
        "slower loop off the second grid": (
            dict(busy, poll_interval_ms=1250, open_order_delay_ms=100),
            dict(entry_confirm_s=6.0, fc_confirm_s=4.0, min_hold_s=30.0, ladder_min_interval_s=7.0)),
    }


COMBINATIONS = list(_combinations("XAUUSDm"))


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("name", COMBINATIONS)
def test_decision_rules_replayed_independently(live_cfg, engine_run, symbol, name):
    """
    Protects: the kernel's decisions with several levers switched on at once. The rules,
    restated without any of the kernel's code and fed the scores, quotes and RSI of its trace,
    must give the kernel's signal on every poll, its floating P/L on every poll and its fills.
    """
    base, levers = _combinations(symbol)[name]
    cfg = live_cfg(symbol, **base).replace(**levers)
    res = _run(engine_run, cfg)
    assert len(res.trace) > 2000 and len(res.baskets) >= 1
    assert _replay_agrees(cfg, res) == ""


@pytest.mark.parametrize("name", [n for n in COMBINATIONS if _combinations("XAUUSDm")[n][1]])    # (those with levers)
def test_replay_notices_every_lever(live_cfg, engine_run, name):
    """
    Protects: the replay test itself against agreeing for want of anything to disagree about.
    For every lever of a combination, taking that one lever out of the replayed rules (and
    leaving the kernel run as it is) makes the replay differ from the run in at least one of
    the two windows -- so each lever did change decisions there, and the replay follows it.
    """
    bites = {}
    for symbol in SYMBOLS:
        base, levers = _combinations(symbol)[name]
        without = live_cfg(symbol, **base)
        cfg = without.replace(**levers)
        res = _run(engine_run, cfg)
        for field in levers:
            if field in RULE_FIELDS and getattr(cfg, field) != getattr(without, field):
                off = cfg.replace(**{field: getattr(without, field)})
                bites[field] = bites.get(field, False) or _replay_agrees(off, res) != ""
    idle = [field for field, bit in bites.items() if not bit]
    assert bites and not idle, f"levers that changed nothing in either window: {idle}"


# ───────────────────────────── confirmation times and holds ─────────────────────────────

@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("seconds", [7.0, 20.0])
@pytest.mark.parametrize("scores", ["RSI and MACD slope", "RSI slope alone"])
def test_entry_confirm_opens_only_after_the_direction_held_that_long(live_cfg, engine_run, symbol, seconds, scores):
    """
    Protects: ``entry_confirm_s``. A basket opens on exactly those flat polls where the entry
    direction has been the same on every flat poll for at least that long (and the cooldown
    is over) -- so never early, and on the first such poll, not a later one. Time in a basket
    does not count towards the confirmation, and neither does time spent pointing the other
    way: with both scores on the M1 RSI slope alone the direction turns straight into its
    opposite, with no neutral poll in between, and the clock starts again there too.
    """
    quick = QUICK if scores == "RSI and MACD slope" else dict(
        QUICK, open_weights={"M1": [1, 0]}, fc_weights={"M1": [1, 0]}, entry_s=1.0, entry_agree_s=1.0)
    cfg = live_cfg(symbol, entry_confirm_s=seconds, **quick)
    res = _run(engine_run, cfg)
    p = _polls(res)
    flat = p["side"] == 0
    want = _entry_direction(cfg, p)
    held_for = p["t"] - _since(p["t"], np.where(flat, want, 9))     # a poll inside a basket breaks the run
    ready = flat & (want != 0) & (p["allowed"] > 0) & (p["brake"] == 0)
    confirmed = held_for >= seconds * 1000
    assert (p["opened"] == (ready & confirmed)).all()
    assert (p.loc[p["opened"], "signal"] == np.where(want[p["opened"]] > 0, 1, 2)).all()
    # the polls that had to wait are the ones the kernel counts, and the wait decided at least one open
    waiting = ready & ~confirmed
    assert waiting.sum() == res.counters["polls_entry_blocked_confirm"] > 0
    assert (p["opened"] & waiting.shift(1, fill_value=False)).any()
    assert p["opened"].sum() >= 3
    if scores == "RSI slope alone":
        turned = flat & flat.shift(1, fill_value=False) & (want * np.r_[0, want[:-1]] == -1)
        assert turned.sum() >= 5
    # without the lever the same settings open on a direction that has only just appeared
    free = _polls(_run(engine_run, cfg.replace(entry_confirm_s=0.0)))
    fresh = free["t"] - _since(free["t"], np.where(free["side"] == 0, _entry_direction(cfg, free), 9))
    assert (fresh[free["opened"]] < seconds * 1000).any()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("seconds", [7.0, 30.0])
def test_fc_confirm_needs_an_unbroken_force_close_condition(live_cfg, engine_run, symbol, seconds):
    """
    Protects: ``fc_confirm_s``. A force-close happens only once the force-close score has been
    against the basket on every poll for that long, and on the first poll where it has. When
    the condition lapses the clock starts again: a basket whose earlier, shorter stretch
    would have been long enough if the two were added together is not closed.
    """
    # no profit exit, and a force-close score (the M1 MACD slope alone) that flickers: every basket
    # ends by force-close, most of them after several false starts
    cfg = live_cfg(symbol, fc_confirm_s=seconds, **dict(QUICK, fc_weights={"M1": [0, 1]}), **WIDE_LADDER,
                   entry_agree_s=1.0, target_usd_per_unit=None, book_enabled=False)
    res = _run(engine_run, cfg)
    p = _polls(res)
    c = _conditions(cfg, p)
    against = c["force_close"]
    held_for = p["t"] - _since(p["t"], np.where(against, p["basket"], -1))
    due = against & (held_for >= seconds * 1000)
    forced = p["reason"] == "force_close"
    assert forced.sum() >= 4
    assert due[forced].all()                                 # never early
    assert (p.loc[due, "reason"] != "").all()                # never late: a due basket is closed on that poll
    assert (p["reason"].to_numpy() == _expected_exit(cfg, p)).all()
    # the timer restarts after a lapse
    first_against = p["t"].where(against).groupby(p["basket"]).transform("min")
    assert (against & ~due & (p["t"] - first_against >= seconds * 1000)).sum() > 0
    # and the lever changes this run: without it the first adverse poll closes
    free = _run(engine_run, cfg.replace(fc_confirm_s=0.0))
    assert (free.baskets["reason"] == "force_close").sum() > forced.sum()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("exits", sorted(EXITS))
def test_min_hold_delays_the_slope_exits_but_not_the_price_exits(live_cfg, engine_run, symbol, exits):
    """
    Protects: ``min_hold_s`` as config.py documents it -- no force-close and no book until the
    basket is that old. A slope exit that is due earlier fires on the first poll at or after
    the hold; the stop-loss and the profit target are not delayed.
    """
    hold = 120.0
    profit_exit = dict(TARGET, target_usd_per_unit=3.0) if exits == "target" else BOOK
    cfg = live_cfg(symbol, min_hold_s=hold, stop_loss_usd_per_unit=4.0, **QUICK, **WIDE_LADDER, **profit_exit)
    res = _run(engine_run, cfg)
    p = _polls(res)
    c = _conditions(cfg, p)
    young = (p["side"] != 0) & (p["age"] < hold * 1000)
    by_slope = p["reason"].isin(["force_close", "book"])
    assert by_slope.any() and not (by_slope & young).any()
    assert (p["reason"].to_numpy() == _expected_exit(cfg, p)).all()
    # polls on which a slope exit was due but the basket was too young: nothing closes there ...
    held_back = (c["force_close"] | c["book"]) & young & ~c["stop_loss"] & ~c["target"]
    assert held_back.sum() > 0 and (p.loc[held_back, "reason"] == "").all()
    # ... and one of them is released on the very poll the hold ends
    assert (by_slope & held_back.shift(1, fill_value=False)).any()
    # the price exits fire inside the hold
    assert (p.loc[c["stop_loss"], "reason"] == "stop_loss").all() and (c["stop_loss"] & young).any()
    if exits == "target":
        assert (p.loc[c["target"] & ~c["stop_loss"], "reason"] == "target").all() and (c["target"] & young).any()
    # without the hold the same settings do close on a slope inside the first `hold` seconds
    free = _run(engine_run, cfg.replace(min_hold_s=0.0)).baskets
    assert (free.loc[free["reason"].isin(["force_close", "book"]), "duration_s"] < hold).any()


# ───────────────────────────── entry filters ─────────────────────────────

@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("blocked", ["BUY", "SELL"])
def test_one_direction_switched_off_leaves_the_other_alone(live_cfg, engine_run, symbol, blocked):
    """
    Protects: ``allow_long`` / ``allow_short`` one at a time. The switched-off direction is still
    signalled but never opened and never starts a cooldown; the other direction opens on every
    poll it is signalled; and until the unrestricted run opens its first basket in the
    switched-off direction, the two runs are the same fill for fill.
    """
    both = live_cfg(symbol, **QUICK, **WIDE_LADDER)
    cfg = both.replace(allow_long=False) if blocked == "BUY" else both.replace(allow_short=False)
    free, res = _run(engine_run, both), _run(engine_run, cfg)
    p = _polls(res)
    refused_code, other_code = (1, 2) if blocked == "BUY" else (2, 1)
    assert (res.fills["side"] != blocked).all() and len(res.baskets) >= 2
    assert (p["signal"] == refused_code).sum() > 0 and not p.loc[p["signal"] == refused_code, "opened"].any()
    assert (p["opened"] == ((p["signal"] == other_code) & (p["brake"] == 0))).all()
    # the signal itself still follows the entry rule in both directions, and the cooldown runs from real closes only
    flat = p["side"] == 0
    want = _entry_direction(cfg, p)
    rule = np.where(flat & (want != 0) & (p["allowed"] > 0), np.where(want > 0, 1, 2), 0)
    assert (p.loc[flat, "signal"] == rule[flat]).all()
    assert ((p["allowed"] > 0) == ((p["t"] - p["last_close"]) >= cfg.reentry_cooldown_s * 1000)).all()
    # identical to the unrestricted run up to its first basket in the switched-off direction
    opens = free.fills[free.fills["action"] == "open"]
    assert set(opens["side"]) == {"BUY", "SELL"}
    first = opens.loc[opens["side"] == blocked, "time"].min()
    pd.testing.assert_frame_equal(free.fills[free.fills["time"] < first].reset_index(drop=True),
                                  res.fills[res.fills["time"] < first].reset_index(drop=True))
    # and from there on they part: the restricted run has nothing at that time
    assert not (res.fills["time"] == first).any()


def _on_a_later_clock(prep, shift_ms: int):
    """
    The same ticks and bars on a clock ``shift_ms`` later. The kernel finds each bar through its
    first row, not through its time, so the indicators and every score stay exactly what they
    were; only what depends on the time of day moves. Both fixture windows lie inside a single
    UTC hour: this is how a run gets to cross an hour boundary.
    """
    return dataclasses.replace(prep, start_ms=prep.start_ms + shift_ms, end_ms=prep.end_ms + shift_ms,
                               t_ms=prep.t_ms + shift_ms, bar_t={tf: v + shift_ms // 1000 for tf, v in prep.bar_t.items()},
                               gaps=prep.gaps + shift_ms, after_ms=prep.after_ms + shift_ms if prep.after_ms >= 0 else -1,
                               _cache={})          # (a fresh cache: the indicator arrays are kept per object)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_entry_hours_restrict_opens_but_not_adds_or_exits(live_cfg, engine_run, prepared, windows, symbol):
    """
    Protects: ``entry_hours_utc``. With the clock moved so that the window crosses an hour
    boundary, baskets open only on polls whose latest tick falls in a listed UTC hour -- on
    every such poll that signals an entry -- while a basket opened before the boundary keeps
    adding and closes after it exactly as in the unrestricted run.
    """
    start, end = windows[symbol]
    first_hour = pd.Timestamp(start).hour
    busy = dict(QUICK, **WIDE_LADDER, **TARGET)
    plain = _run(engine_run, live_cfg(symbol, **busy))
    crossed = False
    for minutes in (30, 35, 45):
        shift = minutes * 60_000
        prep = _on_a_later_clock(prepared(symbol, mode="ticks"), shift)
        any_hour = live_cfg(symbol, **busy,
                            start=str(pd.Timestamp(start) + pd.Timedelta(minutes=minutes)),
                            end=str(pd.Timestamp(end) + pd.Timedelta(minutes=minutes)))
        free = _checked(fast.run(any_hour, prep, trace=True))
        # the later clock alone changes nothing
        cols = ["action", "side", "lots", "price", "profit", "reason"]
        pd.testing.assert_frame_equal(free.fills[cols], plain.fills[cols])
        assert (_ms(free.fills["time"]) - _ms(plain.fills["time"]) == shift).all()

        def hour_of(times_ms):
            return (_tick_seconds(prep, times_ms) % 86400) // 3600

        for hours in ([first_hour], [first_hour + 1], [first_hour - 1, first_hour + 1, 23]):
            cfg = any_hour.replace(entry_hours_utc=hours)
            res = _checked(fast.run(cfg, prep, trace=True))
            p = _polls(res)
            listed = np.isin(hour_of(p["t"]), hours)
            wanted = p["signal"].isin([1, 2]) & (p["brake"] == 0)
            assert (p["opened"] == (wanted & listed)).all()
            assert (wanted & ~listed).sum() == res.counters["polls_entry_blocked_hours"] > 0
            assert p["opened"].any()
            assert _replay_agrees(cfg, res, _tick_seconds(prep, p["t"])) == ""
            # together with a confirmation time: an hour in which entries are barred does not restart the clock
            both = cfg.replace(entry_confirm_s=6.0)
            res2 = _checked(fast.run(both, prep, trace=True))
            assert res2.counters["polls_entry_blocked_hours"] > 0 and len(res2.baskets) >= 1
            assert _replay_agrees(both, res2, _tick_seconds(prep, _polls(res2)["t"])) == ""
            if hours == [first_hour]:
                # the unrestricted run up to its first open after the boundary, adds and closes included
                f = free.fills.assign(hour=hour_of(_ms(free.fills["time"])))
                cut = f.loc[(f["action"] == "open") & (f["hour"] != first_hour), "time"].min()
                assert pd.notna(cut)
                pd.testing.assert_frame_equal(free.fills[free.fills["time"] < cut].reset_index(drop=True),
                                              res.fills[res.fills["time"] < cut].reset_index(drop=True))
                late = res.fills[hour_of(_ms(res.fills["time"])) != first_hour]
                assert (late["action"] != "open").all()
                crossed = crossed or {"add", "close"} <= set(late["action"])
    assert crossed, "no clock put the hour boundary inside a basket that went on to add and close"


# ───────────────────────────── cooldown and thresholds ─────────────────────────────

@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("cooldown", [0.0, 30.0, 90.0])
def test_reentry_cooldown_counts_from_the_last_close(live_cfg, engine_run, symbol, cooldown):
    """
    Protects: ``reentry_cooldown_s`` at values other than the live 300 s. An entry is signalled
    and opened on exactly the flat polls that want one and lie at least that long after the
    last close; the first such poll is taken, and with no cooldown that is the poll right
    after the close.
    """
    cfg = live_cfg(symbol, **dict(QUICK, reentry_cooldown_s=cooldown), **WIDE_LADDER)
    res = _run(engine_run, cfg)
    p = _polls(res)
    flat = p["side"] == 0
    want = _entry_direction(cfg, p)
    over = (p["t"] - p["last_close"]) >= cooldown * 1000
    assert ((p["allowed"] > 0) == over).all()
    rule = np.where(flat & (want != 0) & over, np.where(want > 0, 1, 2), 0)
    assert (p.loc[flat, "signal"] == rule[flat]).all()
    assert (p["opened"] == ((rule != 0) & (p["brake"] == 0))).all()
    waiting = flat & (want != 0) & ~over
    assert waiting.sum() == res.counters["polls_entry_blocked_cooldown"]
    again = p[p["opened"] & (p["last_close"] > 0)]           # every open but the first
    gap = again["t"] - again["last_close"]
    assert len(again) >= 3 and (gap >= cooldown * 1000).all()
    if cooldown > 0:
        assert waiting.sum() > 0 and (gap < cooldown * 1000 + cfg.poll_interval_ms).any()
    else:
        assert (gap == cfg.poll_interval_ms).any()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("levels", [dict(entry_s=4.0), dict(entry_agree_s=0.0), dict(entry_s=4.0, entry_agree_s=1.0)],
                         ids=["entry_s=4", "entry_agree_s=0", "entry_s=4,entry_agree_s=1"])
def test_entry_thresholds(live_cfg, engine_run, symbol, levels):
    """
    Protects: ``entry_s`` and ``entry_agree_s`` away from the live 2 / 2, on an open score that
    ranges over +-4 (M1 + M5). An entry is signalled exactly where the open score reaches
    ``entry_s`` and the force-close score agrees by ``entry_agree_s``, in either direction.
    """
    base = live_cfg(symbol, **dict(QUICK, open_weights={"M1": 1, "M5": 1}), **WIDE_LADDER, **TARGET)
    cfg = base.replace(**levels)
    res = _run(engine_run, cfg)
    p = _polls(res)
    flat = p["side"] == 0
    want = _entry_direction(cfg, p)
    rule = np.where(flat & (want != 0) & (p["allowed"] > 0), np.where(want > 0, 1, 2), 0)
    assert (p.loc[flat, "signal"] == rule[flat]).all()
    assert (p["opened"] == ((rule != 0) & (p["brake"] == 0))).all()
    opens = res.fills[res.fills["action"] == "open"]
    way = np.where(opens["side"] == "BUY", 1, -1)
    assert len(opens) >= 3
    assert (opens["open_score"] * way >= cfg.entry_s).all() and (opens["fc_score"] * way >= cfg.entry_agree_s).all()
    # the levels decide differently from the live ones on this very run
    assert (want != _entry_direction(base, p))[flat].sum() > 0


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("level", [2.0, 3.0])
def test_force_close_threshold(live_cfg, engine_run, symbol, level):
    """
    Protects: ``force_close_s`` away from the live 1, on a force-close score with every value
    from -3 to +3 (M1, RSI slope x 2 + MACD slope x 1, raw signs). A basket is force-closed on
    the first poll the score is that far against it; a score that is against it by less --
    enough for the live level -- closes nothing.
    """
    base = live_cfg(symbol, **dict(QUICK, fc_weights={"M1": [2, 1]}), **WIDE_LADDER, **TARGET)
    cfg = base.replace(force_close_s=level)
    res = _run(engine_run, cfg)
    p = _polls(res)
    expected = _expected_exit(cfg, p)
    assert (p["reason"].to_numpy() == expected).all()
    forced = p[p["reason"] == "force_close"]
    assert set(forced["side"]) == {1, -1} and (forced["fc"] * forced["side"] <= -level).all()
    too_weak = _conditions(base, p)["force_close"] & ~_conditions(cfg, p)["force_close"] & (expected == "")
    assert too_weak.sum() > 0 and (p.loc[too_weak, "reason"] == "").all()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("level", [0.0, 5.0])
def test_ladder_gate_threshold(live_cfg, engine_run, symbol, level):
    """
    Protects: ``ladder_s`` away from the live 2. With every tier on M1 and no force-close to end
    the basket first, a tier whose RSI is hit adds exactly while the open score (-2, 0 or +2)
    is less than ``ladder_s`` against the basket: at 0 a neutral score already blocks the add,
    at 5 nothing does.
    """
    base = live_cfg(symbol, **QUICK, **WIDE_LADDER, **TARGET, ladder_tfs=["M1"] * 5,
                    force_close_enabled=False, stop_loss_usd_per_unit=10.0)
    cfg = base.replace(ladder_s=level)
    res = _run(engine_run, cfg)
    p = _polls(res)
    assert (p["added"].to_numpy() == _expected_add(cfg, p)).all()
    adds = res.fills[res.fills["action"] == "add"]
    assert len(adds) >= 3
    assert (adds["open_score"] * np.where(adds["side"] == "BUY", 1, -1) > -level).all()
    hit = _tier_hit(cfg, p) & (_expected_exit(cfg, p) == "")
    adverse = (p["open"] * p["side"]).to_numpy()
    blocked = hit & (adverse <= -level)
    assert blocked.sum() == res.counters["polls_ladder_blocked_gate"]
    if level <= base.ladder_s:
        assert (blocked & (adverse > -base.ladder_s)).sum() > 0      # blocked here, let through at the live level
    else:
        assert blocked.sum() == 0 and (p["added"] & (adverse <= -base.ladder_s)).sum() > 0   # and the reverse


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("level", [2.0, 3.0])
def test_book_threshold(live_cfg, engine_run, symbol, level):
    """
    Protects: ``book_s`` away from the live 1, on a book score that takes the values -3, +-1 and
    +3 (M15, RSI slope x 2 + MACD slope x 1). A basket in profit is booked on the first poll
    the score is that far against it -- at 3, exactly at the level -- and a score of 1 against
    it, which is enough at the live level, books nothing.
    """
    base = live_cfg(symbol, **QUICK, **WIDE_LADDER, **dict(BOOK, book_weights={"M15": [2, 1]}))
    cfg = base.replace(book_s=level)
    res = _run(engine_run, cfg)
    p = _polls(res)
    expected = _expected_exit(cfg, p)
    assert (p["reason"].to_numpy() == expected).all()
    booked = p[p["reason"] == "book"]
    assert set(booked["side"]) == {1, -1} and (booked["book"] * booked["side"] == -3.0).all()
    too_weak = _conditions(base, p)["book"] & ~_conditions(cfg, p)["book"] & (expected == "")
    assert too_weak.sum() > 0 and (p.loc[too_weak, "reason"] == "").all()


# ───────────────────────────── exits ─────────────────────────────

@pytest.mark.parametrize("symbol", SYMBOLS)
def test_exits_fire_in_the_documented_order(live_cfg, engine_run, symbol):
    """
    Protects: the order stop-loss, target, book, force-close, time stop when more than one fires
    on a poll -- in particular ``book_enabled`` together with a target (the hedging rules plus
    the slope book): a basket whose profit is over the target while the book score is against
    it closes as "target"; the book takes the baskets that are in profit by less.
    """
    runs = {
        "book with a target": dict(QUICK, **WIDE_LADDER, **dict(BOOK, target_usd_per_unit=1.0)),
        "book on the force-close timeframe": dict(
            QUICK, **dict(BOOK, book_weights={"M1": 1}, profit_protect_usd_per_unit=0.25), fixed_units=1),
        "stop-loss with no profit exit": dict(
            QUICK, **WIDE_LADDER, target_usd_per_unit=None, book_enabled=False, stop_loss_usd_per_unit=4.0,
            max_hold_s=120.0),
        "hold that ends as the time stop arrives": dict(
            QUICK, **WIDE_LADDER, **BOOK, min_hold_s=60.0, max_hold_s=60.0, stop_loss_usd_per_unit=3.0),
    }
    together = set()
    for name, overrides in runs.items():
        cfg = live_cfg(symbol, **overrides)
        p = _polls(_run(engine_run, cfg))
        rules = _exit_rules(cfg, p)
        assert (p["reason"].to_numpy() == _expected_exit(cfg, p)).all(), name
        for row in rules[rules.sum(axis=1) >= 2].itertuples(index=False):
            fired = [rule for rule, on in zip(EXIT_ORDER, row) if on]
            together.add((fired[0], fired[1]))
        if name == "book with a target":
            both = rules["target"] & rules["book"]
            assert both.sum() > 0 and (p.loc[both, "reason"] == "target").all()
            assert (p["reason"] == "book").sum() > 0
    # each of these pairs fired on one poll somewhere, and the first of the pair named the close
    assert {("stop_loss", "force_close"), ("target", "book"), ("book", "force_close"), ("book", "time_stop"),
            ("force_close", "time_stop")} <= together


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_book_behind_the_target_changes_nothing(live_cfg, engine_run, symbol):
    """
    Protects: the "target + slope book" what-if when the book's profit bar is not below the
    target. Every poll that could book is then already over the target, so no basket is ever
    booked and the run is the target-only run fill for fill.
    """
    with_book = live_cfg(symbol, **QUICK, **WIDE_LADDER,
                         **dict(BOOK, target_usd_per_unit=1.0, profit_protect_usd_per_unit=1.0))
    res = _run(engine_run, with_book)
    alone = _run(engine_run, with_book.replace(book_enabled=False))
    p = _polls(res)
    could_book = _conditions(with_book, p)["book"]
    assert could_book.sum() > 0 and (p.loc[could_book, "reason"] == "target").all()
    assert (res.baskets["reason"] != "book").all()
    cols = [c for c in res.fills.columns if c != "book_score"]      # only computed when the book is on
    pd.testing.assert_frame_equal(res.fills[cols], alone.fills[cols])
    pd.testing.assert_frame_equal(res.baskets, alone.baskets)


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("exits", sorted(EXITS))
def test_force_close_switched_off(live_cfg, engine_run, symbol, exits):
    """
    Protects: ``force_close_enabled=False``. No basket is force-closed: on the polls where the
    force-close score is against the basket and nothing else fires, the basket stays. Up to
    the first force-close of the run with the rule on, the two runs are the same.
    """
    on = live_cfg(symbol, **QUICK, **WIDE_LADDER, **EXITS[exits])
    off = on.replace(force_close_enabled=False)
    with_fc, res = _run(engine_run, on), _run(engine_run, off)
    p = _polls(res)
    assert (res.baskets["reason"] != "force_close").all() and res.counters["closes_force"] == 0
    expected = _expected_exit(off, p)
    assert (p["reason"].to_numpy() == expected).all()
    only_force_close = _conditions(on, p)["force_close"] & (expected == "")
    assert only_force_close.sum() > 0 and (p.loc[only_force_close, "reason"] == "").all()
    first = with_fc.baskets.loc[with_fc.baskets["reason"] == "force_close", "close_time"].min()
    assert pd.notna(first)
    pd.testing.assert_frame_equal(with_fc.fills[with_fc.fills["time"] < first].reset_index(drop=True),
                                  res.fills[res.fills["time"] < first].reset_index(drop=True))
    assert not ((res.fills["time"] == first) & (res.fills["action"] == "close")).any()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("bar", [0.0, 0.5, 1.5])
def test_profit_protect_is_the_profit_a_book_needs_per_unit(live_cfg, engine_run, symbol, bar):
    """
    Protects: ``profit_protect_usd_per_unit``. With the book score against it, a basket is
    booked on the first poll its floating profit is above bar x unit and on no poll where it
    is not -- with two units, a profit over the bar for one unit is not enough.
    """
    cfg = live_cfg(symbol, **QUICK, **WIDE_LADDER, **dict(BOOK, profit_protect_usd_per_unit=bar))
    res = _run(engine_run, cfg)
    p = _polls(res)
    assert (p.loc[p["side"] != 0, "b_units"] == 2).all()
    against = (p["side"] != 0) & (p["book"] * p["side"] <= -cfg.book_s)
    over = p["profit"] > bar * p["b_units"]
    assert (p.loc[against & over, "reason"] == "book").all()
    assert (p.loc[against & ~over, "reason"] != "book").all()
    booked = res.baskets[res.baskets["reason"] == "book"]
    assert len(booked) >= 2 and (booked["profit_seen"] > bar * booked["units"]).all()
    if bar > 0:
        assert (against & ~over & (p["profit"] > bar)).sum() > 0     # over the bar for one unit only: not booked
    else:
        assert (against & (p["profit"] <= 0)).sum() > 0              # no profit at all: not booked


# ───────────────────────────── ladder ─────────────────────────────

def test_ladder_rsi_levels(live_cfg, engine_run):
    """
    Protects: ``rsi_oversold`` / ``rsi_overbought`` away from the live 35 / 65, with levels that
    are not mirror images of each other. A BUY basket adds exactly on the polls its tier RSI is
    at or below the oversold level, a SELL basket where it is at or above the overbought level
    (the gate and the exits permitting).
    """
    sell_moved = sell_adds = 0
    for symbol in SYMBOLS:
        base = live_cfg(symbol, **QUICK, **TARGET)
        for oversold, overbought in ((45.0, 70.0), (30.0, 52.0)):
            cfg = base.replace(rsi_oversold=oversold, rsi_overbought=overbought)
            p = _polls(_run(engine_run, cfg))
            expected = _expected_add(cfg, p)
            assert (p["added"].to_numpy() == expected).all()
            rsi, buys, sells = _tier_rsi(cfg, p), (p["side"] > 0).to_numpy(), (p["side"] < 0).to_numpy()
            assert (rsi[expected & buys] <= oversold).all() and (rsi[expected & sells] >= overbought).all()
            # polls these levels decide differently from the live ones: in BUY baskets on every run ...
            differs = expected != _expected_add(base, p)
            assert differs[buys].sum() > 0, (symbol, oversold)
            sell_moved += differs[sells].sum()
            sell_adds += (expected & sells).sum()
    # ... and in SELL baskets, which are few in these windows, on at least one
    assert sell_moved > 0 and sell_adds > 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_ladder_tfs_name_the_timeframe_each_tier_reads(live_cfg, engine_run, symbol):
    """
    Protects: ``ladder_tfs`` in another order and length than the live M1, M5, M15, H1, H4.
    Tier k reads the RSI of the k-th listed timeframe -- the same numbers a run with the live
    order shows for that timeframe -- adds on it, labels the fill with it, and the ladder ends
    with the list.
    """
    tiers = ["M5", "M1", "M15"]
    cfg = live_cfg(symbol, **QUICK, **WIDE_LADDER, **TARGET, ladder_tfs=tiers)
    res = _run(engine_run, cfg)
    p = _polls(res)
    watch = engine_run(live_cfg(symbol, allow_long=False, allow_short=False), mode="ticks", trace=True).trace
    at = np.searchsorted(watch[:, K.T_T], p["t"].to_numpy())
    assert (watch[at, K.T_T] == p["t"].to_numpy()).all()
    live_order = list(live_cfg(symbol).ladder_tfs)
    for q, tf in enumerate(tiers):
        assert np.array_equal(p[f"rsi{q}"].to_numpy(), watch[at, K.T_RSI0 + live_order.index(tf)]), tf
    assert (p["added"].to_numpy() == _expected_add(cfg, p)).all()
    adds = res.fills[res.fills["action"] == "add"]
    assert len(adds) >= 5 and (adds["tier"] == [tiers[n - 2] for n in adds["n_pos"]]).all()
    assert res.baskets["n_pos"].max() == len(tiers) + 1
    # read in the live order instead, the same polls would not have been the ones to add
    as_live = p.copy()
    for q in range(len(tiers)):
        as_live[f"rsi{q}"] = watch[at, K.T_RSI0 + q]
    assert (_expected_add(cfg, as_live) != _expected_add(cfg, p)).sum() > 0


# ───────────────────────────── what the scores are made of ─────────────────────────────

def _watch(live_cfg, symbol, tf, **settings):
    """
    A run that watches one timeframe and never trades, so it polls every second of the window:
    its open score is that timeframe's RSI slope sign, its force-close score the MACD slope
    sign, and its first ladder column the timeframe's RSI.
    """
    return live_cfg(symbol, open_weights={tf: [1, 0]}, fc_weights={tf: [0, 1]}, ladder_tfs=[tf],
                    allow_long=False, allow_short=False, **settings)


_WATCHED = [K.T_OPEN_SCORE, K.T_FC_SCORE, K.T_RSI0]


def _forming_bar(prep, tf, t) -> np.ndarray:
    """Index of the bar of ``tf`` that is still forming at each poll time; the bars before it are closed."""
    row = np.searchsorted(prep.t_ms, np.asarray(t, np.int64), side="right") - 1
    return np.searchsorted(prep.start_row[tf], row, side="right") - 1


def _live_reading(prep, cfg, tf, k, price=None):
    """
    (RSI slope sign, MACD slope sign, RSI) as the live ``indicator.py`` computes them from the
    closed bars [0, k) of one timeframe: with ``price`` the way ``app.py`` does it, the forming
    bar closed at the latest Bid; without it from the closed bars alone.
    """
    closes = prep.closes[tf][:k] if price is None else np.append(prep.closes[tf][:k], price)
    series = pd.Series(closes[-live_constants.RSI_CANDLE_COUNT:])
    rsi = IND.calculate_rsi(series, length=cfg.rsi_length, ma_type=live_constants.RSI_MA_TYPE)
    macd = IND.calculate_macd(series, fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal)
    rsi_slope = IND.latest_pivot_slope(rsi, lookback=cfg.peak_lookback, width=cfg.pivot_width,
                                       ob_level=cfg.rsi_peak_ob, os_level=cfg.rsi_peak_os)
    line = float(macd["signal"].iloc[-1])
    side = "high" if line > 0 else ("low" if line < 0 else None)
    macd_slope = IND.latest_pivot_slope(macd["hist"], lookback=cfg.peak_lookback, width=cfg.pivot_width, side=side)
    return rsi_slope["sign"], macd_slope["sign"], float(rsi.iloc[-1])


def _assert_reads_like_live(prep, cfg, tf, trace, rows, closed) -> None:
    k = _forming_bar(prep, tf, trace[:, K.T_T])
    for i in rows:
        price = None if closed else float(trace[i, K.T_BID])
        r, m, rsi = _live_reading(prep, cfg, tf, int(k[i]), price)
        when = f"{tf} {pd.Timestamp(int(trace[i, K.T_T]), unit='ms')}"
        assert trace[i, K.T_OPEN_SCORE] == r, f"{when}: RSI slope sign {trace[i, K.T_OPEN_SCORE]}, live {r}"
        assert trace[i, K.T_FC_SCORE] == m, f"{when}: MACD slope sign {trace[i, K.T_FC_SCORE]}, live {m}"
        # The live code sees its 500-bar fetch, the kernel up to 600 bars of warm-up. Wilder's average
        # forgets its seed geometrically: by then the two agree to 1e-9 at the live length of 14 and
        # to about 1e-6 of an RSI point at 28, the longest length the tables use.
        assert abs(trace[i, K.T_RSI0] - rsi) <= 1e-5, f"{when}: RSI {trace[i, K.T_RSI0]}, live {rsi}"


def _bar_starts(k) -> np.ndarray:
    """For each poll, the row of the first poll inside the same forming bar."""
    first = np.r_[True, k[1:] != k[:-1]]
    return np.maximum.accumulate(np.where(first, np.arange(len(k)), 0))


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_closed_bar_levers_read_closed_bars_only(live_cfg, engine_run, prepared, symbol):
    """
    Protects: ``slope_on_closed_bars`` and ``ladder_on_closed_bars``. On every poll, for every
    timeframe, the slope signs and the ladder RSI are what the live ``indicator.py`` functions
    give for the bars that had closed by then -- the forming bar left out, so nothing changes
    inside a bar -- and each lever moves only its own half: the slopes, or the ladder RSI.
    """
    prep = prepared(symbol, mode="ticks")
    repainted = 0
    closed_m1_rsi = None
    for tf in ALL_TFS:
        def trace_of(**levers):
            return _run(engine_run, _watch(live_cfg, symbol, tf, **levers)).trace

        forming = trace_of()
        closed = trace_of(slope_on_closed_bars=True, ladder_on_closed_bars=True)
        assert np.array_equal(forming[:, K.T_T], closed[:, K.T_T]) and len(closed) > 2000
        k = _forming_bar(prep, tf, closed[:, K.T_T])
        start = _bar_starts(k)
        assert np.array_equal(closed[:, _WATCHED], closed[start][:, _WATCHED])      # constant inside a bar
        cfg = _watch(live_cfg, symbol, tf, slope_on_closed_bars=True, ladder_on_closed_bars=True)
        _assert_reads_like_live(prep, cfg, tf, closed, np.unique(start), closed=True)
        slopes_only = trace_of(slope_on_closed_bars=True)
        assert np.array_equal(slopes_only[:, _WATCHED[:2]], closed[:, _WATCHED[:2]])
        assert np.array_equal(slopes_only[:, K.T_RSI0], forming[:, K.T_RSI0])
        ladder_only = trace_of(ladder_on_closed_bars=True)
        assert np.array_equal(ladder_only[:, _WATCHED[:2]], forming[:, _WATCHED[:2]])
        assert np.array_equal(ladder_only[:, K.T_RSI0], closed[:, K.T_RSI0])
        repainted += int((closed[:, _WATCHED[:2]] != forming[:, _WATCHED[:2]]).any(axis=1).sum())
        assert (closed[:, K.T_RSI0] != forming[:, K.T_RSI0]).mean() > 0.9
        if tf == "M1":
            closed_m1_rsi = closed[:, K.T_RSI0]
    # the forming bar does repaint the signs within these windows, so the lever is not idle
    assert repainted > 0
    # a ladder timeframe that no score reads takes its closed-bar RSI too
    apart = _run(engine_run, live_cfg(symbol, open_weights={"M5": 1}, fc_weights={"M5": 1}, book_weights={"M5": 1},
                                      ladder_tfs=["M1"], allow_long=False, allow_short=False,
                                      ladder_on_closed_bars=True)).trace
    assert np.array_equal(apart[:, K.T_RSI0], closed_m1_rsi)


# both ends of every range the lever tables publish, one setting at a time, then several together
INDICATOR_SETTINGS = {
    "rsi_length=7": dict(rsi_length=7),
    "rsi_length=28": dict(rsi_length=28),
    "macd 5-13-4": dict(macd_fast=5, macd_slow=13, macd_signal=4),
    "macd 24-52-18": dict(macd_fast=24, macd_slow=52, macd_signal=18),
    "peak_lookback=8": dict(peak_lookback=8),
    "peak_lookback=50": dict(peak_lookback=50),
    "pivot_width=1": dict(pivot_width=1),
    "pivot_width=4": dict(pivot_width=4),
    "rsi peak band 70-45": dict(rsi_peak_ob=70.0, rsi_peak_os=45.0),
    "rsi peak band 55-30": dict(rsi_peak_ob=55.0, rsi_peak_os=30.0),
    "all at once": dict(rsi_length=9, macd_fast=8, macd_slow=17, macd_signal=9, peak_lookback=12, pivot_width=3,
                        rsi_peak_ob=65.0, rsi_peak_os=42.0),
}


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("name", list(INDICATOR_SETTINGS))
def test_indicator_settings_reach_the_slope_signs_and_the_ladder_rsi(live_cfg, engine_run, prepared, symbol, name):
    """
    Protects: ``rsi_length``, ``macd_fast`` / ``macd_slow`` / ``macd_signal``, ``peak_lookback``,
    ``pivot_width`` and ``rsi_peak_ob`` / ``rsi_peak_os`` away from the live values. On a sample of
    polls of every timeframe -- always including polls where the setting changes what the
    kernel reads -- the slope signs and the RSI equal the live ``indicator.py`` functions called
    with the same settings, on the forming bar and on closed bars only.
    """
    settings = INDICATOR_SETTINGS[name]
    prep = prepared(symbol, mode="ticks")
    moved = 0
    for closed in (False, True):
        mode = dict(slope_on_closed_bars=closed, ladder_on_closed_bars=closed)
        for tf in ALL_TFS:
            cfg = _watch(live_cfg, symbol, tf, **mode, **settings)
            got = _run(engine_run, cfg).trace
            at_live = _run(engine_run, _watch(live_cfg, symbol, tf, **mode)).trace
            differs = np.flatnonzero((got[:, _WATCHED] != at_live[:, _WATCHED]).any(axis=1))
            moved += len(differs)
            rows = set(range(0, len(got), len(got) // 8)) | set(differs[::max(1, len(differs) // 6)][:6].tolist())
            if closed:      # one reading per bar is all there is
                start = _bar_starts(_forming_bar(prep, tf, got[:, K.T_T]))
                assert np.array_equal(got[:, _WATCHED], got[start][:, _WATCHED])
                rows = {int(start[i]) for i in rows}
            _assert_reads_like_live(prep, cfg, tf, got, sorted(rows), closed)
    assert moved > 0, "these settings changed nothing the kernel reads in this window"


@pytest.fixture(scope="module")
def slope_signs(live_cfg, engine_run):
    """
    Factory with a cache: ``slope_signs(symbol, tf)`` -> (poll times, RSI slope signs, MACD slope
    signs) of one timeframe on every second of the window, from a run that only watches it.
    (That those signs are the live indicator's is the business of test_indicators.py.)
    """
    cache = {}

    def get(symbol, tf):
        if (symbol, tf) not in cache:
            tr = _run(engine_run, _watch(live_cfg, symbol, tf)).trace
            cache[(symbol, tf)] = (tr[:, K.T_T].astype(np.int64), tr[:, K.T_OPEN_SCORE].astype(int),
                                   tr[:, K.T_FC_SCORE].astype(int))
        return cache[(symbol, tf)]

    return get


def _score(weights, grey_fill, signs_at) -> np.ndarray:
    """
    sum over timeframes of w_rsi x RSI sign + w_macd x MACD sign. With grey-fill, on a timeframe
    that carries both weights, a sign of 0 takes the other indicator's sign.
    """
    total = 0.0
    for tf, (w_rsi, w_macd) in weights.items():
        r, m = signs_at(tf)
        if grey_fill and w_rsi != 0 and w_macd != 0:
            r, m = np.where((r == 0) & (m != 0), m, r), np.where((m == 0) & (r != 0), r, m)
        total = total + w_rsi * r + w_macd * m
    return total


WEIGHT_SETS = {
    "RSI on H4, MACD on M15": {"H4": [1, 0], "M15": [0, 1]},            # the README's example
    "RSI on M5 x 2, MACD on M1 x 3": {"M5": [2, 0], "M1": [0, 3]},
    "both on M1": {"M1": 1},
    "both on M1 unevenly, MACD on M15": {"M1": [1, 0.5], "M15": [0, 2]},
}


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("name", list(WEIGHT_SETS))
def test_split_weights_and_grey_fill(live_cfg, engine_run, slope_signs, symbol, name):
    """
    Protects: separate RSI / MACD weights per timeframe in all three sections, and the three
    grey-fill switches. Each score on each poll is the weighted sum of that timeframe's RSI
    slope sign and that timeframe's MACD slope sign; a section's grey-fill switch acts on that
    section only, and only where both indicators sit on the same timeframe -- with RSI on one
    timeframe and MACD on another it changes nothing at all.
    """
    weights = WEIGHT_SETS[name]
    shared = any(r != 0 and m != 0 for r, m in live_cfg(symbol, open_weights=weights).open_weights.values())
    columns = {"open": K.T_OPEN_SCORE, "fc": K.T_FC_SCORE, "book": K.T_BOOK_SCORE}
    results = []
    for filled in (None, "open", "fc", "book"):
        cfg = live_cfg(symbol, **dict(QUICK, open_weights=weights, fc_weights=weights), book_weights=weights,
                       book_enabled=True, profit_protect_usd_per_unit=0.5, open_grey_fill=filled == "open",
                       fc_grey_fill=filled == "fc", book_grey_fill=filled == "book")
        res = _run(engine_run, cfg)
        results.append(res)
        t = res.trace[:, K.T_T].astype(np.int64)

        def signs_at(tf):
            times, r, m = slope_signs(symbol, tf)
            at = np.searchsorted(times, t)
            assert (times[at] == t).all()
            return r[at], m[at]

        for section, column in columns.items():
            section_weights = getattr(cfg, f"{section}_weights")
            expected = _score(section_weights, filled == section, signs_at)
            assert np.array_equal(res.trace[:, column], expected), (filled, section)
            if filled is None:
                # the test can tell the two indicators apart, and grey from filled, on these polls
                swapped = {tf: (m, r) for tf, (r, m) in section_weights.items()}
                assert shared or (expected != _score(swapped, False, signs_at)).any()
                assert not shared or (expected != _score(section_weights, True, signs_at)).any()
    if not shared:
        for res in results[1:]:
            _same_fills(results[0], res)
    assert all(len(res.fills) > 0 for res in results)        # runs that trade, so polls after an add are skipped too


# ───────────────────────────── BUY / SELL symmetry ─────────────────────────────

# Lots of the two mirror runs: with these a position's P/L is a whole number of cents at every
# quote (gold 0.10 lot = 10 oz at 3 decimals, BTC 1.00 lot at 2 decimals), so rounding to cents
# cannot fall differently on the two sides of the mirror.
MIRROR_SIZE = {"XAUUSDm": dict(fixed_units=10), "BTCUSDm": dict(fixed_units=100, unit_max_limit=100)}
MIRROR_SPREAD = {"XAUUSDm": 0.2, "BTCUSDm": 20.0}
# off the price grid, so "moved at least this far" is never decided by the last bit of a subtraction
MIRROR_GAP = {"XAUUSDm": 0.1005, "BTCUSDm": 10.005}


def _mirror_pair(prep, spread: float):
    """
    The prepared ticks with a constant spread, and their mirror image: every Bid and every bar
    close reflected about a fixed price, same spread. A rise in one is the same fall in the
    other, RSI becomes 100 - RSI and the MACD histogram changes sign, so every rule that treats
    the two directions alike must produce the same baskets with BUY and SELL exchanged.
    """
    level = float(np.ceil(prep.bid.max() * 2 / 1000) * 1000)

    def with_prices(bid, closes):
        return dataclasses.replace(prep, bid=bid, ask=bid + spread, closes=closes, _cache={})

    return (with_prices(prep.bid, prep.closes),
            with_prices(level - prep.bid, {tf: level - c for tf, c in prep.closes.items()}))


def _mirror_cfg(cfg):
    """The same rules seen in the mirror: the direction filters and the RSI levels change places."""
    return cfg.replace(allow_long=cfg.allow_short, allow_short=cfg.allow_long,
                       rsi_oversold=100.0 - cfg.rsi_overbought, rsi_overbought=100.0 - cfg.rsi_oversold,
                       rsi_peak_ob=100.0 - cfg.rsi_peak_os, rsi_peak_os=100.0 - cfg.rsi_peak_ob)


def _mirror_levers(symbol: str) -> dict:
    return {
        "live rules on M1": {},
        "stop, spacing, target per lot, time stop": dict(
            **TARGET, stop_loss_usd_per_unit=3.0, ladder_min_gap=MIRROR_GAP[symbol], ladder_min_interval_s=15.0,
            target_per_lot=True, max_hold_s=240.0),
        "confirmations and hold": dict(entry_confirm_s=9.0, fc_confirm_s=7.0, min_hold_s=30.0),
        "book": dict(BOOK),
        "book with a target": dict(BOOK, target_usd_per_unit=1.0),
        "one direction only": dict(allow_short=False),
        "levels that are not mirror images": dict(rsi_oversold=40.0, rsi_overbought=52.0, rsi_peak_ob=65.0,
                                                  rsi_peak_os=45.0),
        "closed bars, split weights": dict(open_weights={"M5": [1, 0], "M1": [0, 1]}, entry_s=1.0,
                                           slope_on_closed_bars=True, ladder_on_closed_bars=True),
        "other thresholds, uneven weights": dict(fc_weights={"M1": [2, 1]}, entry_agree_s=1.0, force_close_s=2.0,
                                                 ladder_s=3.0, reentry_cooldown_s=20.0),
        "other indicator settings": dict(rsi_length=9, macd_fast=8, macd_slow=21, macd_signal=5, peak_lookback=12,
                                         pivot_width=3),
    }


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("name", list(_mirror_levers("XAUUSDm")))
def test_buy_and_sell_rules_are_mirror_images(live_cfg, prepared, symbol, name):
    """
    Protects: every rule and lever against being applied to one direction only, or with the
    wrong sign on one of them. The ticks reflected in price must give the same baskets at the
    same polls with BUY and SELL exchanged: same adds, same lots, same exit reasons, same P/L.
    """
    straight, mirrored = _mirror_pair(prepared(symbol, mode="ticks"), MIRROR_SPREAD[symbol])
    overrides = dict(dict(QUICK, **WIDE_LADDER, initial_balance=1e9, leverage=1e9, window_enabled=False),
                     **MIRROR_SIZE[symbol])
    overrides.update(_mirror_levers(symbol)[name])
    cfg = live_cfg(symbol, **overrides)
    a = _checked(fast.run(cfg, straight, trace=True))
    b = _checked(fast.run(_mirror_cfg(cfg), mirrored, trace=True))
    assert len(a.baskets) >= 3
    fa, fb = a.fills, b.fills
    assert len(fa) == len(fb)
    assert (fa["time"] == fb["time"]).all() and (fa["action"] == fb["action"]).all()
    assert (fa["side"] != fb["side"]).all()
    for column in ("lots", "profit", "basket_profit", "reason", "units", "n_pos", "tier"):
        if fa[column].dtype == float:
            assert np.allclose(fa[column], fb[column], rtol=0, atol=1e-6), column
        else:
            assert (fa[column] == fb[column]).all(), column
    for column in ("open_score", "fc_score", "book_score"):
        assert (fa[column] == -fb[column]).all(), column
    ba, bb = a.baskets, b.baskets
    assert (ba["side"] != bb["side"]).all() and (ba["reason"] == bb["reason"]).all()
    assert np.allclose(ba["pnl"], bb["pnl"], rtol=0, atol=1e-6) and np.allclose(ba["mae"], bb["mae"], rtol=0, atol=1e-6)
    # the poll traces agree too: same polls, opposite signals and scores
    assert np.array_equal(a.trace[:, K.T_T], b.trace[:, K.T_T])
    swap = np.array([0, 2, 1, 4, 3, 6, 5])
    assert np.array_equal(a.trace[:, K.T_SIGNAL].astype(int), swap[b.trace[:, K.T_SIGNAL].astype(int)])
    assert np.array_equal(a.trace[:, K.T_NPOS], -b.trace[:, K.T_NPOS])
    if name != "one direction only":
        assert set(ba["side"]) == {"BUY", "SELL"}
    else:
        assert set(ba["side"]) == {"BUY"} and set(bb["side"]) == {"SELL"}


# ───────────────────────────── levers that are off, or cannot bite ─────────────────────────────

# what "off" means for each experimental lever, written out: a default that drifted in config.py shows up here
LEVERS_OFF = dict(slope_on_closed_bars=False, ladder_on_closed_bars=False, min_hold_s=0.0, fc_confirm_s=0.0,
                  entry_confirm_s=0.0, stop_loss_usd_per_unit=None, ladder_min_gap=0.0, ladder_min_interval_s=0.0,
                  max_hold_s=0.0, target_per_lot=False, max_adds=99, allow_long=True, allow_short=True,
                  entry_hours_utc=None, force_close_enabled=True, trend_tf=None, entry_max_spread=0.0, loss_cooldown_s=0.0)


def test_the_off_values_are_the_configuration_defaults(live_cfg):
    """Protects: the defaults themselves. The next test compares a run with itself unless these are what config.py holds."""
    for symbol in SYMBOLS:
        cfg = live_cfg(symbol)
        for lever, off in LEVERS_OFF.items():
            assert getattr(cfg, lever) == off, lever


def _assert_same_run(a, b) -> None:
    _same_fills(a, b)
    assert np.array_equal(a.trace, b.trace)
    assert a.counters == b.counters and a.scalars["final_equity"] == b.scalars["final_equity"]


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("lever", list(LEVERS_OFF) + ["all of them"])
def test_lever_at_its_off_value_is_the_live_run(live_cfg, engine_run, symbol, lever):
    """
    Protects: "every lever is off by default, so a default run is the live behaviour". With a
    lever set to its off value by hand the run equals the plain live run fill for fill, poll
    for poll.
    """
    live = _run(engine_run, live_cfg(symbol))
    assert len(live.fills) > 0
    off = dict(LEVERS_OFF) if lever == "all of them" else {lever: LEVERS_OFF[lever]}
    _assert_same_run(live, _run(engine_run, live_cfg(symbol, **off)))


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_levers_set_where_they_cannot_bite_change_nothing(live_cfg, engine_run, symbol, live_variant):
    """
    Protects: the boundaries of the levers. Switched on, but at a value the run can never
    reach -- or at exactly the value the loop's own timing already satisfies -- each leaves
    the live run as it is: a hold or an add spacing of one poll period (the next poll is
    already that much later, so the comparisons are inclusive), a ladder cap at the ladder's
    own length, every hour allowed, stops out of reach, and the other variant's profit exit
    with a bar no basket reaches.
    """
    plain = live_cfg(symbol)
    live = _run(engine_run, plain)
    assert len(live.fills) > 0 and plain.open_order_delay_ms == 0
    poll_s = plain.poll_interval_ms / 1000.0
    idle = {
        "stop-loss out of reach": dict(stop_loss_usd_per_unit=1e9),
        "time stop longer than the window": dict(max_hold_s=86_400.0),
        "ladder cap at the ladder's length": dict(max_adds=len(plain.ladder_tfs)),
        "every hour allowed": dict(entry_hours_utc=list(range(24))),
        "hold of one poll": dict(min_hold_s=poll_s),
        "add spacing of one poll": dict(ladder_min_interval_s=poll_s),
        "the other profit exit out of reach": (dict(book_enabled=True, profit_protect_usd_per_unit=1e9)
                                               if live_variant == "hedging" else dict(target_usd_per_unit=1e9)),
    }
    cols = [c for c in live.fills.columns if c != "book_score"]      # only computed when the book is on
    for name, overrides in idle.items():
        res = _run(engine_run, live_cfg(symbol, **overrides))
        pd.testing.assert_frame_equal(live.fills[cols], res.fills[cols], obj=name)
        pd.testing.assert_frame_equal(live.baskets, res.baskets, obj=name)
        assert np.array_equal(live.trace[:, K.T_SIGNAL], res.trace[:, K.T_SIGNAL]), name


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_target_per_lot_is_the_live_target_for_a_single_position(live_cfg, engine_run, symbol):
    """
    Protects: the scale of ``target_per_lot``. A basket that never adds holds unit x mtqty lots,
    so its per-lot target is the live target: with the ladder off the two runs are the same.
    With the ladder on they differ, and every target close has cleared $target per mtqty held.
    """
    single = live_cfg(symbol, **QUICK, **TARGET, max_adds=0)
    _assert_same_run(_run(engine_run, single), _run(engine_run, single.replace(target_per_lot=True)))
    cfg = live_cfg(symbol, **QUICK, **WIDE_LADDER, **TARGET, target_per_lot=True)
    res = _run(engine_run, cfg)
    p = _polls(res)
    assert (p["reason"].to_numpy() == _expected_exit(cfg, p)).all()
    hit = p[p["reason"] == "target"]
    assert (hit["count"] > 1).any() and (hit["profit"] > cfg.target_usd_per_unit * hit["lots"] / cfg.mtqty - 1e-9).all()
    # polls over the live target but not over the per-lot target: the basket stays
    waits = (p["side"] != 0) & (p["profit"] > cfg.target_usd_per_unit * p["b_units"]) & (p["reason"] == "")
    assert waits.sum() > 0


# ───────────────────────────── trend filter, spread cap, cooldown after a loss ─────────────────────────────

def _trend_at(prep, tf: str, times_ms) -> np.ndarray:
    """Sign of the MACD signal line of the last closed ``tf`` bar at each time, from the live indicator code."""
    macd = Indicator().calculate_macd(pd.Series(prep.closes[tf]), fast=live_constants.MACD_FAST, slow=live_constants.MACD_SLOW,
                                      signal=live_constants.MACD_SIGNAL)
    tick_ms = prep.t_ms[np.searchsorted(prep.t_ms, np.asarray(times_ms, np.int64), side="right") - 1]
    forming = np.searchsorted(prep.bar_t[tf] * 1000, tick_ms, side="right") - 1
    return np.sign(macd["signal"].to_numpy()[forming - 1])


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("tf", ["M5", "M15", "H1"])
def test_trend_filter_opens_on_one_side_of_the_trend_only(live_cfg, engine_run, prepared, symbol, tf):
    """
    Protects: ``trend_tf`` / ``trend_mode``. The trend is the sign of the MACD signal line of the
    trend timeframe's last closed bar. With the filter every basket opens in that direction
    (mode +1) or against it (mode -1), entries on the other side are counted as blocked, and
    the two filtered runs together take no entry the unfiltered rules would not signal.
    """
    prep = prepared(symbol, mode="ticks")
    base = live_cfg(symbol, **QUICK, **WIDE_LADDER)
    sides = {}
    for mode in (1, -1):
        res = _run(engine_run, base.replace(trend_tf=tf, trend_mode=mode))
        opens = res.fills[res.fills["action"] == "open"]
        want = np.where(opens["side"] == "BUY", 1, -1)
        assert (want == mode * _trend_at(prep, tf, _ms(opens["time"]))).all()
        assert res.counters["polls_entry_blocked_trend"] > 0
        sides[mode] = len(opens)
    assert sides[1] > 0 or sides[-1] > 0
    assert _run(engine_run, base).counters["polls_entry_blocked_trend"] == 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_spread_cap_keeps_entries_off_wide_quotes(live_cfg, engine_run, prepared, symbol):
    """Protects: ``entry_max_spread``. No basket is opened on a quote wider than the cap; wanted entries on such quotes are counted."""
    prep = prepared(symbol, mode="ticks")
    spread = prep.ask - prep.bid
    cap = float(np.quantile(spread, 0.3))
    res = _run(engine_run, live_cfg(symbol, **QUICK, entry_max_spread=cap))
    opens = res.fills[res.fills["action"] == "open"]
    at = np.searchsorted(prep.t_ms, _ms(opens["time"]), side="right") - 1
    assert len(opens) > 0 and (spread[at] <= cap + 1e-12).all()
    assert res.counters["polls_entry_blocked_spread"] > 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_a_losing_basket_is_followed_by_the_longer_cooldown(live_cfg, engine_run, symbol):
    """Protects: ``loss_cooldown_s``. After a basket that lost the next entry waits that long; after a winner, the ordinary cooldown."""
    cfg = live_cfg(symbol, **QUICK, **WIDE_LADDER).replace(loss_cooldown_s=120.0)
    res = _run(engine_run, cfg)
    b = res.baskets.sort_values("open_time")
    wait = (_ms(b["open_time"])[1:] - _ms(b["close_time"])[:-1]) / 1000.0
    lost = b["pnl"].to_numpy()[:-1] < 0
    assert lost.any() and (~lost).any()
    assert (wait[lost] >= 120.0).all() and (wait[~lost] >= cfg.reentry_cooldown_s).all()
    assert (wait[~lost] < 120.0).any()               # winners do not wait the longer time
