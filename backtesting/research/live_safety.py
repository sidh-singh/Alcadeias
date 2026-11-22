"""
The auto-safety breaker of the real-money accounts: its three limits, calibrated on the 8-year backtest
(study of 2026-11-21).

    python3 -m backtesting.research.live_safety             every table and SAFETY_CALIBRATION.md
    python3 -m backtesting.research.live_safety check       the replay against hand-worked cases

The setup that is calibrated
----------------------------
One real account starts with $1,500 and is shared by one gold bot and one BTC bot. Each bot sizes a trade from
HALF the account balance,

    units = min(10, floor(0.5 x balance / STEP) + 1)        0.01 lot per unit, STEP per design (``DESIGNS``)

taken when the trade opens, from the balance booked so far (the start plus the closed P/L of BOTH bots). A trade's
P/L is its P/L at one unit times its units, booked when it closes.

The breaker
-----------
All three rules read the booked balance (closed trades only) right after each booking:

* DROP (account):   the balance is X % or more below its highest value since the start or the last unblock;
* DAY (account):    the balance is Y % or more below the balance at 00:00 UTC of the day (after an unblock during
                    that day: below the balance at the unblock);
* STREAK (per bot): N closed trades of that bot in a row lost money.

DROP and DAY block both bots, STREAK blocks its own bot. A blocked bot opens no new trade; a trade that is already
open runs to its recorded close and is booked. The owner unblocks D hours after the trip (24 by default) and the
counts start afresh. ``simulate`` holds the exact conventions.

What is replayed
----------------
The closed trades of the final-ten study's 8-year window (13 Nov 2018 - 13 Nov 2026, ``backtest_results/final10``),
brought to one unit (``load_trades``; the reading of the ``lots`` column is checked in ``reproduction``):

* on rolling accounts: a fresh $1,500 account on the 1st of every month from Dec 2018 to Nov 2025 (84 starts), run
  for 12 months on the trades that open and close inside them; "recent" = the 24 starts from Dec 2023;
* on one 8-year account from 13 Nov 2018;
* for information only (never part of the choice): the 12 most recent of the 84 starts on their own, and 9 later
  starts (Dec 2025 - Aug 2026) that have less than 12 months of data and run to its end.

The replay re-sizes recorded trades, it does not run the engines again: a skipped trade changes no later trade, and a
trade at u units makes u times its one-unit P/L (``SAFETY_CALIBRATION.md`` lists what that leaves out).

The choice ("medium", fixed before the numbers were read)
---------------------------------------------------------
For each rule the tightest grid value that trips at most 0.5 times per account-year both in the recent 24 accounts
and in all 84: DROP and DAY per pair type, STREAK per design. Then the three chosen limits run together.

Written to ``backtest_results/live_safety``
-------------------------------------------
designs.csv                 each design at one unit: the 8 years, the last 24 and the last 12 months
pairs_no_safety.csv         each pair type without the breaker, per sample of accounts
rule_grid.csv               each rule alone: pair type x rule x grid value x sample
chosen.csv                  the limits the fixed rule gives, and how firm each one is
combined.csv                the three chosen limits together: own limits and the common set, D = 24, 4, 72, 168 h
combined_by_start_year.csv  the same at D = 24 h, by the year the account starts in
trips_8y.csv                every block of the 8-year accounts
streak_unblock_check.csv    what the other reading of the unblock after a STREAK block would change
reproduction.csv            the published accounts rebuilt from the one-unit P/L (the check of ``load_trades``)
anchors.csv                 the earlier "one unit" figures next to this module's
SAFETY_CALIBRATION.md       the report, written from the tables above
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import REPO_ROOT

RESULTS = REPO_ROOT / "backtest_results"
FINAL10 = RESULTS / "final10"
SIZING = RESULTS / "sizing"
OUT = RESULTS / "live_safety"

# the trade records: the final-ten study's 8-year window, [start, end) UTC
WINDOW, WINDOW_START, WINDOW_END = "8y", "2018-11-13", "2026-11-13"
TRADES_24M_FROM, TRADES_12M_FROM = "2024-11-13", "2025-11-13"    # "the last 24 / 12 months" of closed trades
PUBLISHED_START, PUBLISHED_STEP = 2000.0, 2500.0                 # the account those records were made on

# the real setup
START_BALANCE = 1500.0
SHARE = 0.5                                  # each bot sizes from half the account balance
UNIT_CAP = 10
LOT_PER_UNIT = 0.01

# the accounts
ROLL_FIRST, ROLL_LAST, ROLL_MONTHS = "2018-12-01", "2025-11-01", 12
RECENT_FIRST = "2023-12-01"                  # the 24 most recent starts
CRITERION_SAMPLES = ("recent24", "all84")
# Information only, not part of the criterion: what a $1,500 account started lately went through.
LAST12_FIRST = "2024-12-01"                  # the 12 most recent of the 84 starts
LATE_FIRST, LATE_LAST = "2025-12-01", "2026-08-01"   # later starts: less than 12 months of data, run to its end
SAMPLES = ("recent24", "all84", "last12", "late9", "8y")
SAMPLE_NAMES = {"recent24": "recent 24", "all84": "all 84", "last12": "last 12 starts", "late9": "9 late starts",
                "8y": "8-year account"}

# the breaker's grids and the criterion
GRID_X = (15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0)     # DROP: % below the highest balance
GRID_Y = (5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0)       # DAY: % below the day's opening balance
GRID_N = tuple(range(4, 17))                                   # STREAK: losing trades in a row
GRIDS = {"DROP": GRID_X, "DAY": GRID_Y, "STREAK": GRID_N}
D_DEFAULT = 24.0                                               # hours from a trip to the owner's unblock
D_SENSITIVITY = (4.0, 72.0, 168.0)
MAX_TRIPS_PER_YEAR = 0.5                                       # "medium": at most one block in two account-years

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


@dataclass(frozen=True)
class Design:
    code: str
    name: str
    symbol: str
    file: str          # the trade records, in backtest_results/final10
    label: str         # the design's label in that file
    engine: str        # "ticks": the bot's own tick engine; "bars": the research M1-bar simulator
    step: float        # STEP of the live unit rule

    @property
    def bot(self) -> int:
        """0 = the account's gold bot, 1 = its BTC bot."""
        return 0 if self.symbol.startswith("XAU") else 1


DESIGNS: Dict[str, Design] = {d.code: d for d in (
    Design("xv3", "Gold V3-lite", "XAUUSDm", "trades_XAUUSDm_ticks.csv.gz", "V3-lite", "ticks", 1750.0),
    Design("xt1", "Gold Top 1", "XAUUSDm", "trades_XAUUSDm_ticks.csv.gz", "Top 1", "ticks", 1750.0),
    Design("xt2", "Gold Top 2", "XAUUSDm", "trades_XAUUSDm_ticks.csv.gz", "Top 2", "ticks", 1250.0),
    Design("bt2", "BTC Top 2", "BTCUSDm", "trades_BTCUSDm_ticks.csv.gz", "Top 2", "ticks", 1250.0),
    # Turtle System 2 (55-day entry, 20-day exit) is the parameter set "alt" of external.py's Turtle; final10.py
    # labels it "Turtle [alt] + bot votes" and reports it as "Turtle System 2 + bot votes" (60 trades in 8 years).
    Design("bs2", "BTC Turtle S2", "BTCUSDm", "trades_BTCUSDm_warm.csv.gz", "Turtle [alt] + bot votes", "bars", 2500.0),
)}
PAIRS: Dict[str, Tuple[str, str]] = {"P1": ("xt2", "bt2"), "P2": ("xv3", "bt2"), "P3": ("xt1", "bt2"),
                                     "P4": ("xv3", "bs2"), "P5": ("xt2", "bs2"), "P6": ("xt1", "bs2")}
CHOICE_PAIRS = ("P1", "P2", "P3", "P4", "P5")      # P6 is reported for information only

# Figures computed before this study "at one unit", to be reproduced or explained (``anchors``): the worst losing
# stretch over 8 years / over the last 24 months / the worst trade, net profit and trades of the last 24 months
ANCHORS_DESIGN = {"xv3": (-394, -394, -394, 2849, 198), "xt1": (-660, -476, -420, 4044, 301),
                  "xt2": (-335, -262, -61, 2725, 325), "bt2": (-370, -279, -52, 853, 275),
                  "bs2": (-747, -696, -514, 3763, 16)}
ANCHOR_NAMES = ("worst_stretch_8y", "worst_stretch_24m", "worst_trade_24m", "net_24m", "trades_24m")
# two bots on one account, one unit each, last 24 months: the worst losing stretch
ANCHORS_PAIR = {("xv3", "bt2"): -461, ("xv3", "bs2"): -666, ("xt2", "bt2"): -360, ("xt2", "bs2"): -673,
                ("xt1", "bt2"): -599, ("xt1", "bs2"): -912}


# ───────────────────────────── the trade records, at one unit ─────────────────────────────

def _to_ms(when) -> int:
    """A date / time (UTC when it carries no zone) as milliseconds since 1970."""
    ts = pd.Timestamp(when)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return int((ts - _EPOCH) // pd.Timedelta(milliseconds=1))


def _series_ms(s: pd.Series) -> np.ndarray:
    return ((s - _EPOCH) // pd.Timedelta(milliseconds=1)).to_numpy(np.int64)


def _parse_times(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, format="ISO8601")
    except (ValueError, TypeError):                      # pandas < 2.0 has no "ISO8601" format
        return pd.to_datetime(s, utc=True)


def load_trades(code: str, reading: str = "engine") -> pd.DataFrame:
    """
    The design's closed trades of the 8-year window in closing order, with the units they were recorded at
    (``units``) and their P/L at one unit (``p1`` = pnl / units).

    The two engines write the ``lots`` column differently (``reproduction`` checks both against the published
    accounts, trade by trade):

    * tick engine (V3-lite, Top 1, Top 2): ``lots`` is the basket's TOTAL over its legs (``engine/kernels.py``:
      B_LOTS = the sum of the positions' lots) and every leg holds units x 0.01 lot, so units = lots / 0.01 / legs.
      Only gold Top 1 has two-leg baskets (its M5 MACD-turn add);
    * M1-bar simulator (the Turtle): ``lots`` is the size of ONE leg (``final10._bar_account``: steps x 0.01) and
      the P/L is the sum over the legs, so units = lots / 0.01.

    ``reading="spec"`` applies units = lots / 0.01 to every design, the formula of the calibration brief. It halves
    the P/L of Top 1's two-leg baskets; it is kept only to show that, and to compare with a calibration that used it.
    """
    if reading not in ("engine", "spec"):
        raise ValueError(f"unknown reading {reading!r}")
    d = DESIGNS[code]
    t = pd.read_csv(FINAL10 / d.file)
    t = t[(t["label"] == d.label) & (t["window"] == WINDOW)].copy()
    if t.empty:
        raise ValueError(f"{code}: no {WINDOW} trades labelled {d.label!r} in {d.file}")
    t["open_time"], t["close_time"] = _parse_times(t["open_time"]), _parse_times(t["close_time"])
    t = t.sort_values(["close_time", "open_time"], kind="stable").reset_index(drop=True)
    t["open_ms"], t["close_ms"] = _series_ms(t["open_time"]), _series_ms(t["close_time"])
    lot_units = (t["lots"] / LOT_PER_UNIT).round()
    t["units"] = lot_units / t["legs"] if (d.engine == "ticks" and reading == "engine") else lot_units
    if reading == "engine" and not (np.isclose(t["units"], t["units"].round()) & (t["units"] >= 1)).all():
        raise ValueError(f"{code}: the lots column does not give whole units")
    t["p1"] = t["pnl"] / t["units"]
    # one bot holds one trade at a time: the replay pairs an open with its close by the bot alone
    o, c = t["open_ms"].to_numpy(), t["close_ms"].to_numpy()
    if not ((c > o).all() and (o[1:] >= c[:-1]).all()):
        raise ValueError(f"{code}: trades overlap or close before they open")
    return t


def worst_stretch(pl: np.ndarray) -> float:
    """The largest peak-to-trough fall of the cumulative P/L (the start, 0, counts as a peak). 0 or negative."""
    if len(pl) == 0:
        return 0.0
    cum = np.cumsum(pl)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    return float((cum - peak).min())


def longest_losing_streak(pl: np.ndarray) -> int:
    best = run = 0
    for v in pl:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    return best


def streak_trips(pl: np.ndarray, n: int) -> int:
    """How often ``n`` losing trades in a row occur when the count starts again after each occurrence."""
    trips = run = 0
    for v in pl:
        run = run + 1 if v < 0 else 0
        if run >= n:
            trips, run = trips + 1, 0
    return trips


def one_unit_stats(pl: np.ndarray) -> dict:
    """A list of closed trades at one unit, in closing order."""
    if len(pl) == 0:
        raise ValueError("no trades")
    losses = pl[pl < 0]
    out = dict(trades=int(len(pl)), win_rate_pct=float((pl > 0).mean() * 100.0), net=float(pl.sum()),
               worst_stretch=worst_stretch(pl), worst_trade=float(pl.min()), best_trade=float(pl.max()),
               median_losing_trade=float(np.median(losses)) if len(losses) else np.nan,
               # one losing trade in ten lost more than this
               losing_trade_1_in_10=float(np.quantile(losses, 0.1)) if len(losses) else np.nan,
               longest_losing_streak=longest_losing_streak(pl))
    out.update({f"streak_trips_n{n}": streak_trips(pl, n) for n in GRID_N})
    return out


def designs_table(trades: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Each design at a fixed one unit: the 8 years, and the trades closed in the last 24 and the last 12 months."""
    rows = []
    for code, t in trades.items():
        d = DESIGNS[code]
        for sample, since in (("8y", WINDOW_START), ("24m", TRADES_24M_FROM), ("12m", TRADES_12M_FROM)):
            part = t[t["close_ms"] >= _to_ms(since)]
            rows.append(dict(design=code, name=d.name, symbol=d.symbol, file=d.file, label=d.label, engine=d.engine,
                             step_live=d.step, sample=sample, **one_unit_stats(part["p1"].to_numpy())))
    return pd.DataFrame(rows)


def _earlier_p1(t: pd.DataFrame) -> np.ndarray:
    """pnl / max(1, round(lots / 0.01 / legs)): the division that reproduces the earlier "one unit" figures. It is
    right for the tick-engine files and wrong for the Turtle, whose ``lots`` is already the size of one leg: most
    of its trades were left at their recorded 2 to 4 units."""
    u = np.maximum(1.0, np.round((t["lots"] / LOT_PER_UNIT).round() / t["legs"]))
    return (t["pnl"] / u).to_numpy()


def anchors(trades: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    The earlier "one unit" figures next to this module's, per design and for two bots on one account (one unit each,
    last 24 months). ``computed`` is trade by trade in closing order with ``load_trades``' units;
    ``computed_daily_sums`` takes the stretch over the summed P/L of each UTC day; the ``earlier_division`` columns
    repeat both with ``_earlier_p1``. ``explained_by`` names the variant that gives the earlier figure to the dollar.
    """
    cut = _to_ms(TRADES_24M_FROM)

    def figures(parts: List[Tuple[np.ndarray, np.ndarray]], daily: bool) -> Tuple[float, float, float, float, int]:
        c, p = np.concatenate([a for a, _ in parts]), np.concatenate([b for _, b in parts])
        order = np.argsort(c, kind="stable")
        c, p = c[order], p[order]
        recent = p[c >= cut]

        def stretch(c_ms: np.ndarray, pl: np.ndarray) -> float:
            if daily:
                pl = pd.Series(pl).groupby(c_ms // DAY_MS).sum().to_numpy()
            return worst_stretch(pl)

        return stretch(c, p), stretch(c[c >= cut], recent), float(recent.min()), float(recent.sum()), int(len(recent))

    rows = []
    scopes = [((code,), ANCHORS_DESIGN[code], range(5)) for code in trades]
    scopes += [(pair, (None, given, None, None, None), (1,)) for pair, given in ANCHORS_PAIR.items()]
    for codes, given, which in scopes:
        close = [trades[c]["close_ms"].to_numpy() for c in codes]
        variants = {"trade by trade": figures(list(zip(close, [trades[c]["p1"].to_numpy() for c in codes])), False),
                    "daily sums": figures(list(zip(close, [trades[c]["p1"].to_numpy() for c in codes])), True),
                    "earlier division": figures(list(zip(close, [_earlier_p1(trades[c]) for c in codes])), False),
                    "earlier division, daily sums": figures(list(zip(close, [_earlier_p1(trades[c]) for c in codes])), True)}
        for k in which:
            match = [name for name, v in variants.items() if abs(v[k] - given[k]) <= 0.5]       # the same whole dollar
            rows.append(dict(what=ANCHOR_NAMES[k], scope="+".join(codes), given=given[k],
                             computed=variants["trade by trade"][k], computed_daily_sums=variants["daily sums"][k],
                             earlier_division=variants["earlier division"][k],
                             earlier_division_daily_sums=variants["earlier division, daily sums"][k],
                             reproduced="trade by trade" in match, explained_by=match[0] if match else "not explained"))
    return pd.DataFrame(rows)


# ───────────────────────────── the account replay ─────────────────────────────

Events = Tuple[List[int], List[bool], List[int], List[float]]


def account_events(gold: Optional[pd.DataFrame], btc: Optional[pd.DataFrame], start_ms: int, end_ms: int) -> Events:
    """
    The opens and closes of the trades that lie inside the account, open_time >= start and close_time < end, in the
    order they are processed: by time; at one instant the closes before the opens (an open sees every booking up to
    and including its own instant); gold before BTC.
    Returns parallel lists: time (ms), is-a-close, bot (0 gold, 1 BTC), the trade's one-unit P/L.
    """
    time, kind, bot, p1 = [], [], [], []
    for b, t in ((0, gold), (1, btc)):
        if t is None:
            continue
        o, c = t["open_ms"].to_numpy(), t["close_ms"].to_numpy()
        keep = (o >= start_ms) & (c < end_ms)
        o, c, p = o[keep], c[keep], t["p1"].to_numpy()[keep]
        for when, k in ((c, 0), (o, 1)):
            time.append(when)
            kind.append(np.full(len(when), k))
            bot.append(np.full(len(when), b))
            p1.append(p)
    if not time:
        return [], [], [], []
    time, kind, bot, p1 = (np.concatenate(a) for a in (time, kind, bot, p1))
    order = np.lexsort((bot, kind, time))
    return time[order].tolist(), (kind[order] == 0).tolist(), bot[order].tolist(), p1[order].tolist()


def simulate(ev: Events, steps: Tuple[float, float], start_ms: int, x: Optional[float] = None,
             y: Optional[float] = None, n: Tuple[Optional[int], Optional[int]] = (None, None),
             d_hours: float = D_DEFAULT, start_balance: float = START_BALANCE, share: float = SHARE,
             streak_unblock_rebases_account: bool = False, trip_log: Optional[list] = None,
             units_log: Optional[list] = None) -> dict:
    """
    One account: both bots' recorded trades re-sized by the live unit rule, with or without the breaker.

    ``x``, ``y``: the DROP and DAY limits as fractions (0.25 = 25 %), None = that rule is off. ``n``: the STREAK
    limits of the gold and the BTC bot, None = off. ``steps``: STEP of the gold and the BTC bot.

    The conventions:

    * Sizing. At a trade's open, units = min(10, floor(share x balance / STEP) + 1), at least 1, from the balance
      booked up to and including that instant. Its P/L, one-unit P/L x units, is booked at its close (no rounding).
    * A rule is checked right after a booking. Bookings at one instant: gold first.
    * DROP: peak = the highest booked balance since the start or the last account unblock (the start / unblock
      balance counts); trips when (peak - balance) / peak >= x.
    * DAY: day0 = the balance booked before 00:00 UTC of the booking's day, or the balance at an account unblock
      later that day; trips when (day0 - balance) / day0 >= y.
    * STREAK: the bot's closed trades with P/L < 0 in a row (P/L >= 0 sets the count to 0); trips at count >= N.
    * A DROP or DAY trip blocks both bots, a STREAK trip its own bot, for [trip, trip + D hours): a trade whose
      open lies in that interval is skipped (never opened, no P/L); one that opens at trip + D exactly is taken.
      A trade open at the trip runs to its recorded close and is booked.
    * While the account is blocked nothing new trips (the breaker is latched; bookings of trades that were open
      still move the balance and the streak counts). The account unblock sets peak = day0 = balance and both
      streak counts to 0. The unblock after a STREAK block sets that bot's count to 0 and leaves the account's
      peak and day0 alone (``streak_unblock_rebases_account`` is the other reading, in which it resets them too;
      ``streak_unblock_check`` shows how little it changes).
    * An unblock that falls on the same instant as a booking comes first.
    * One booking can trip several rules: each rule counts it, ``trip_events`` counts it once.

    Returned whatever the breaker does, and measured the same way with and without it (never rebased):
    ``worst_drop`` = the largest (highest balance so far - balance) / highest balance so far; ``worst_day`` = the
    largest loss of one UTC day so far in that day, as a fraction of the balance booked before 00:00;
    ``worst_day_net`` = the same for whole days (the day's closing balance).
    """
    times, is_close, bots, p1s = ev
    hold = int(round(d_hours * HOUR_MS))
    bal = float(start_balance)
    units = [0, 0]                       # units of each bot's open trade; 0 = flat, or its trade was skipped
    streak = [0, 0]
    bot_blocked, bot_until = [False, False], [0, 0]
    acct_blocked, acct_until = False, 0
    peak = bal                           # DROP
    day, day0 = start_ms // DAY_MS, bal  # DAY
    top, worst_drop, low = bal, 0.0, bal           # the account's own history, never rebased
    pday, pday0, worst_day, worst_day_net = day, bal, 0.0, 0.0
    trips_drop = trips_day = trip_events = 0
    trips_streak, opened, skipped, max_units = [0, 0], [0, 0], [0, 0], [0, 0]
    trip_ms: List[int] = []
    wiped = False

    for i in range(len(times)):
        t, b = times[i], bots[i]
        # unblocks that are due: the block covers [trip, trip + D)
        if acct_blocked and t >= acct_until:
            acct_blocked = False
            peak, day, day0 = bal, acct_until // DAY_MS, bal
            streak[0] = streak[1] = 0
        for k in (0, 1):
            if bot_blocked[k] and t >= bot_until[k]:
                bot_blocked[k] = False
                streak[k] = 0
                if streak_unblock_rebases_account and not acct_blocked:
                    peak, day, day0 = bal, bot_until[k] // DAY_MS, bal

        if not is_close[i]:                                   # a trade opens
            if acct_blocked or bot_blocked[b] or wiped:
                skipped[b] += 1
                continue
            u = min(UNIT_CAP, max(1, math.floor(share * bal / steps[b]) + 1))
            units[b] = u
            opened[b] += 1
            if u > max_units[b]:
                max_units[b] = u
            if units_log is not None:
                units_log.append((b, t, u))
            continue

        u = units[b]                                          # a trade closes
        if u == 0:
            continue                                          # it was never opened
        units[b] = 0
        d = t // DAY_MS
        if d != day:
            day, day0 = d, bal
        if d != pday:
            if pday0 > 0 and (pday0 - bal) / pday0 > worst_day_net:
                worst_day_net = (pday0 - bal) / pday0        # the day that just ended
            pday, pday0 = d, bal
        pl = p1s[i] * u
        bal += pl
        if bal > top:
            top = bal
        elif top > 0 and (top - bal) / top > worst_drop:
            worst_drop = (top - bal) / top
        if bal < low:
            low = bal
        if pday0 > 0 and (pday0 - bal) / pday0 > worst_day:
            worst_day = (pday0 - bal) / pday0
        streak[b] = streak[b] + 1 if pl < 0 else 0
        if bal <= 0:
            wiped = True                                      # nothing left to trade with
        if acct_blocked:
            continue                                          # latched until the unblock
        if bal > peak:
            peak = bal
        hit_drop = x is not None and peak > 0 and (peak - bal) / peak >= x
        hit_day = y is not None and day0 > 0 and (day0 - bal) / day0 >= y
        hit_streak = n[b] is not None and not bot_blocked[b] and streak[b] >= n[b]
        if not (hit_drop or hit_day or hit_streak):
            continue
        trip_events += 1
        trip_ms.append(t)
        trips_drop += hit_drop
        trips_day += hit_day
        if hit_drop or hit_day:
            acct_blocked, acct_until = True, t + hold
        if hit_streak:
            trips_streak[b] += 1
            bot_blocked[b], bot_until[b] = True, t + hold
        if trip_log is not None:
            trip_log.append(dict(time_ms=t, bot=b, drop=bool(hit_drop), day=bool(hit_day), streak=bool(hit_streak),
                                 balance=bal, peak=peak, day0=day0, losing_streak=streak[b]))

    if pday0 > 0 and (pday0 - bal) / pday0 > worst_day_net:
        worst_day_net = (pday0 - bal) / pday0                # the last booking day
    return dict(end=bal, worst_drop=worst_drop, worst_day=worst_day, worst_day_net=worst_day_net, min_balance=low,
                trip_events=trip_events, trips_drop=int(trips_drop), trips_day=int(trips_day),
                trips_streak_gold=trips_streak[0], trips_streak_btc=trips_streak[1], trip_ms=tuple(trip_ms),
                opened_gold=opened[0], opened_btc=opened[1], skipped_gold=skipped[0], skipped_btc=skipped[1],
                max_units_gold=max_units[0], max_units_btc=max_units[1], wiped=wiped)


# ───────────────────────────── the published accounts: the check of the one-unit P/L ─────────────────────────────

def _published() -> Dict[str, dict]:
    """Final equity of each design's published 8-year account ($2,000, STEP $2,500): final10 and the sizing study."""
    res = pd.read_csv(FINAL10 / "results.csv")
    siz = pd.read_csv(SIZING / "results.csv") if (SIZING / "results.csv").exists() else None
    sizing_key = {"xv3": "xau_v3lite", "xt1": "xau_top1", "xt2": "xau_top2", "bt2": "btc_top2", "bs2": "btc_turtle_s2"}
    out = {}
    for code, d in DESIGNS.items():
        r = res[(res["symbol"] == d.symbol) & (res["label"] == d.label) & (res["window"] == WINDOW)]
        if len(r) != 1:
            raise ValueError(f"{code}: {len(r)} rows in final10/results.csv")
        r = r.iloc[0]
        row = dict(published_final=float(r["final_equity"]), published_trades=int(r["trades"]),
                   published_name=str(r["name"]), sizing_final=np.nan, sizing_max_units=np.nan)
        if siz is not None:
            s = siz[(siz["design"] == sizing_key[code]) & (siz["step"] == PUBLISHED_STEP) & (siz["cap"].astype(str) == "10")
                    & (siz["window"] == WINDOW)]
            if len(s) == 1:
                row.update(sizing_final=float(s.iloc[0]["final_equity"]), sizing_max_units=float(s.iloc[0]["max_units"]))
        out[code] = row
    return out


def reproduction() -> pd.DataFrame:
    """
    Each design's published 8-year account rebuilt from the one-unit P/L by ``simulate`` itself (one bot, the whole
    balance, $2,000, STEP $2,500), under both readings of ``lots``. With the right reading the rebuilt units equal
    the recorded units on every trade and the balance ends at $2,000 + the recorded P/L. The published figure is
    the final EQUITY: for three designs it also holds the floating P/L of the basket still open at the window's
    end, which no closed-trade file contains.
    """
    pub = _published()
    rows = []
    for code, d in DESIGNS.items():
        row = dict(design=code, name=d.name, engine=d.engine, trades=np.nan, **pub[code])
        for reading in ("engine", "spec"):
            t = load_trades(code, reading)
            ev = account_events(t if d.bot == 0 else None, t if d.bot == 1 else None, _to_ms(WINDOW_START), _to_ms(WINDOW_END))
            log: list = []
            r = simulate(ev, (PUBLISHED_STEP, PUBLISHED_STEP), _to_ms(WINDOW_START), start_balance=PUBLISHED_START,
                         share=1.0, units_log=log)
            rebuilt = np.array([u for _, _, u in log], float)        # in opening order = closing order (one at a time)
            if len(rebuilt) != len(t):
                raise ValueError(f"{code}: {len(t) - len(rebuilt)} trades lie outside the {WINDOW} window")
            row.update({f"rebuilt_final_{reading}": round(r["end"], 2),
                        f"unit_mismatches_{reading}": int((rebuilt != t["units"].to_numpy()).sum()),
                        f"max_recorded_units_{reading}": float(t["units"].max())})
            if reading == "engine":
                row.update(trades=len(t), two_leg_trades=int((t["legs"] > 1).sum()) if d.engine == "ticks" else 0,
                           recorded_closed_balance=round(PUBLISHED_START + float(t["pnl"].sum()), 2))
        row["open_at_end_floating"] = round(row["published_final"] - row["recorded_closed_balance"], 2)
        row["open_at_end_units"] = math.floor(row["recorded_closed_balance"] / PUBLISHED_STEP) + 1   # the unit rule then
        row["open_at_end_floating_per_unit"] = round(row["open_at_end_floating"] / row["open_at_end_units"], 4)
        rows.append(row)
    return pd.DataFrame(rows)


# ───────────────────────────── the accounts and the tables ─────────────────────────────

@dataclass(frozen=True)
class Account:
    name: str                    # the start date, or "8y"
    start_ms: int
    end_ms: int
    years: float
    samples: Tuple[str, ...]


def accounts() -> List[Account]:
    """The 84 rolling 12-month accounts, the 8-year account, and (information only) the 9 later starts that have less
    than 12 months of data: a new account on the 1st of Dec 2025 .. Aug 2026, run to the end of the data."""
    out = []
    for s in pd.date_range(ROLL_FIRST, ROLL_LAST, freq="MS", tz="UTC"):
        e = s + pd.DateOffset(months=ROLL_MONTHS)
        samples = ("all84",) + tuple(name for name, first in (("recent24", RECENT_FIRST), ("last12", LAST12_FIRST))
                                     if s >= pd.Timestamp(first, tz="UTC"))
        out.append(Account(str(s.date()), _to_ms(s), _to_ms(e), ROLL_MONTHS / 12.0, samples))
    a, z = pd.Timestamp(WINDOW_START, tz="UTC"), pd.Timestamp(WINDOW_END, tz="UTC")
    for s in pd.date_range(LATE_FIRST, LATE_LAST, freq="MS", tz="UTC"):
        out.append(Account(str(s.date()), _to_ms(s), _to_ms(z), (z - s).days / 365.25, ("late9",)))
    out.append(Account("8y", _to_ms(a), _to_ms(z), round((z - a).days / 365.25, 6), ("8y",)))
    return out


class Pair:
    """One pair type: its two designs, and the events of every account (built once, replayed many times)."""

    def __init__(self, key: str, trades: Dict[str, pd.DataFrame], accts: Sequence[Account]):
        self.key = key
        self.gold, self.btc = PAIRS[key]
        self.steps = (DESIGNS[self.gold].step, DESIGNS[self.btc].step)
        self.accounts = list(accts)
        self.events = {a.name: account_events(trades[self.gold], trades[self.btc], a.start_ms, a.end_ms) for a in accts}
        self._base: Optional[pd.DataFrame] = None

    def run(self, x: Optional[float] = None, y: Optional[float] = None,
            n: Tuple[Optional[int], Optional[int]] = (None, None), d_hours: float = D_DEFAULT, **how) -> pd.DataFrame:
        """Every account under one setting of the breaker (limits in per cent); one row per account."""
        rows = []
        for a in self.accounts:
            r = simulate(self.events[a.name], self.steps, a.start_ms, None if x is None else x / 100.0,
                         None if y is None else y / 100.0, n, d_hours, **how)
            rows.append(dict(account=a.name, years=a.years, **r))
        return pd.DataFrame(rows).set_index("account")

    @property
    def base(self) -> pd.DataFrame:
        """Every account without the breaker."""
        if self._base is None:
            self._base = self.run()
        return self._base

    def names(self, sample: str) -> List[str]:
        return [a.name for a in self.accounts if sample in a.samples]


def no_safety_table(pairs: Dict[str, Pair]) -> pd.DataFrame:
    """Each pair type WITHOUT the breaker: the spread of the accounts' end balance, deepest fall and worst day."""
    rows = []
    for key, pair in pairs.items():
        for sample in SAMPLES:
            b = pair.base.loc[pair.names(sample)]
            row = dict(pair=key, gold=pair.gold, btc=pair.btc, sample=sample, accounts=len(b))
            for col, name, scale in (("end", "end", 1.0), ("worst_drop", "worst_drop_pct", 100.0),
                                     ("worst_day", "worst_day_loss_pct", 100.0),
                                     ("worst_day_net", "worst_day_net_loss_pct", 100.0),
                                     ("min_balance", "lowest_balance", 1.0)):
                v = b[col] * scale
                row.update({f"{name}_min": v.min(), f"{name}_median": v.median(), f"{name}_max": v.max()})
            row.update(end_mean=b["end"].mean(), below_1000=int((b["end"] < 1000.0).sum()),
                       below_750=int((b["end"] < 750.0).sum()), wiped=int(b["wiped"].sum()),
                       max_units_gold=int(b["max_units_gold"].max()), max_units_btc=int(b["max_units_btc"].max()),
                       trades_per_year_gold=b["opened_gold"].sum() / b["years"].sum(),
                       trades_per_year_btc=b["opened_btc"].sum() / b["years"].sum())
            rows.append(row)
    return pd.DataFrame(rows)


def effect_row(pair: Pair, run: pd.DataFrame, sample: str) -> dict:
    """One sample of accounts under one setting, against the same accounts without the breaker."""
    names = pair.names(sample)
    r, b = run.loc[names], pair.base.loc[names]
    years = float(r["years"].sum())
    change = r["end"] - b["end"]
    return dict(accounts=len(r), account_years=years,
                trips_per_year=r["trip_events"].sum() / years,
                drop_trips_per_year=r["trips_drop"].sum() / years, day_trips_per_year=r["trips_day"].sum() / years,
                streak_gold_trips_per_year=r["trips_streak_gold"].sum() / years,
                streak_btc_trips_per_year=r["trips_streak_btc"].sum() / years,
                share_with_trip_pct=float((r["trip_events"] > 0).mean() * 100.0),
                # the same market day trips many overlapping accounts: how many different days are behind the count
                distinct_trip_days=len({t // DAY_MS for ts in r["trip_ms"] for t in ts}),
                skipped_trades_per_year=(r["skipped_gold"] + r["skipped_btc"]).sum() / years,
                end_mean=r["end"].mean(), end_mean_no_safety=b["end"].mean(),
                end_change_mean=change.mean(), end_change_median=change.median(),
                end_change_worst=change.min(), end_change_best=change.max(),
                end_min=r["end"].min(), end_min_no_safety=b["end"].min(),
                worst_drop_pct=r["worst_drop"].max() * 100.0, worst_drop_pct_no_safety=b["worst_drop"].max() * 100.0,
                worst_drop_pct_median=r["worst_drop"].median() * 100.0,
                worst_drop_pct_median_no_safety=b["worst_drop"].median() * 100.0,
                below_1000=int((r["end"] < 1000.0).sum()), below_1000_no_safety=int((b["end"] < 1000.0).sum()),
                below_750=int((r["end"] < 750.0).sum()), below_750_no_safety=int((b["end"] < 750.0).sum()))


def rule_grid(pairs: Dict[str, Pair], log=print) -> pd.DataFrame:
    """Every rule ALONE (the other two off) at every grid value, D = 24 h: pair x rule x value x sample."""
    rows = []
    for key, pair in pairs.items():
        for rule, grid in GRIDS.items():
            for v in grid:
                run = pair.run(x=v if rule == "DROP" else None, y=v if rule == "DAY" else None,
                               n=(v, v) if rule == "STREAK" else (None, None))
                for sample in SAMPLES:
                    rows.append(dict(pair=key, gold=pair.gold, btc=pair.btc, rule=rule, value=float(v),
                                     d_hours=D_DEFAULT, sample=sample, **effect_row(pair, run, sample)))
        log(f"  {key} ({pair.gold} + {pair.btc}): each rule alone, {sum(len(g) for g in GRIDS.values())} settings")
    return pd.DataFrame(rows)


def _meets(rates: Dict[str, float], samples: Sequence[str] = CRITERION_SAMPLES) -> bool:
    return all(rates[s] <= MAX_TRIPS_PER_YEAR + 1e-12 for s in samples)


def _rates(grid: pd.DataFrame, pair: str, rule: str, col: str) -> Dict[float, Dict[str, float]]:
    """grid value -> sample -> ``col`` (trips per account-year, or another figure) of one pair and rule."""
    g = grid[(grid["pair"] == pair) & (grid["rule"] == rule)]
    return {float(v): dict(zip(part["sample"], part[col])) for v, part in g.groupby("value")}


def _smallest(rates: Dict[float, Dict[str, float]], samples: Sequence[str] = CRITERION_SAMPLES) -> Optional[float]:
    """The smallest grid value (the tightest limit) that meets the criterion in every sample; None if none does."""
    ok = [v for v in sorted(rates) if _meets(rates[v], samples)]
    return ok[0] if ok else None


def choose(grid: pd.DataFrame, designs: pd.DataFrame) -> pd.DataFrame:
    """
    The limits by the rule fixed in advance: for each rule the smallest grid value whose mean trips per account-year
    are <= 0.5 in the recent 24 AND in all 84 accounts.

    * DROP and DAY: per pair type; and the common set, the smallest X and Y that meet it in every one of P1..P5.
    * STREAK: per design, the largest N that any of P1..P5 holding the design needs (the trips are those of the
      design's own bot).

    Next to each value: its trips, the grid values one step tighter and wider with theirs (how firm the choice is),
    and, for information only, what the same rule would give if the latest starts had to meet it as well: the 12
    most recent of the 84 (``value_if_last12_too``), and those plus the 9 late starts (``value_if_latest_too``).
    """
    rows = []

    def add(rule: str, scope_type: str, scope: str, rates: Dict[float, Dict[str, float]],
            days: Optional[Dict[float, Dict[str, float]]], value: Optional[float], note: str) -> None:
        grid_values = sorted(rates)
        r = rates.get(value, {})
        i = grid_values.index(value) if value is not None else None
        tighter = grid_values[i - 1] if i else None                       # None also at the tight end of the grid
        wider = grid_values[i + 1] if i is not None and i + 1 < len(grid_values) else None
        later_fail = [v for v in grid_values if value is not None and v > value and not _meets(rates[v])]
        if value is None:
            note = (note + "; " if note else "") + "no grid value meets the criterion"
        elif tighter is None:
            note = (note + "; " if note else "") + "the tightest value of the grid: a tighter limit was not tried"
        if later_fail:
            note = (note + "; " if note else "") + f"wider values {later_fail} do not meet the criterion"
        also_last12 = _smallest(rates, CRITERION_SAMPLES + ("last12",))
        also_latest = _smallest(rates, CRITERION_SAMPLES + ("last12", "late9"))
        rows.append(dict(
            rule=rule, scope_type=scope_type, scope=scope, value=np.nan if value is None else value,
            trips_per_year_recent24=r.get("recent24", np.nan), trips_per_year_all84=r.get("all84", np.nan),
            trips_per_year_last12=r.get("last12", np.nan), trips_per_year_late9=r.get("late9", np.nan),
            trips_per_year_8y_account=r.get("8y", np.nan),
            distinct_trip_days_recent24=np.nan if days is None or value is None else days[value]["recent24"],
            distinct_trip_days_all84=np.nan if days is None or value is None else days[value]["all84"],
            tighter_value=np.nan if tighter is None else tighter,
            tighter_trips_recent24=np.nan if tighter is None else rates[tighter]["recent24"],
            tighter_trips_all84=np.nan if tighter is None else rates[tighter]["all84"],
            wider_value=np.nan if wider is None else wider,
            wider_trips_recent24=np.nan if wider is None else rates[wider]["recent24"],
            wider_trips_all84=np.nan if wider is None else rates[wider]["all84"],
            value_if_last12_too=np.nan if also_last12 is None else also_last12,
            value_if_latest_too=np.nan if also_latest is None else also_latest, note=note))

    for rule, col in (("DROP", "drop_trips_per_year"), ("DAY", "day_trips_per_year")):
        per_pair = {key: _rates(grid, key, rule, col) for key in PAIRS}
        for key, rates in per_pair.items():
            add(rule, "pair", key, rates, _rates(grid, key, rule, "distinct_trip_days"), _smallest(rates),
                "" if key in CHOICE_PAIRS else "information only")
        # the common set: at each value, the worst of P1..P5
        common = {v: {s: max(per_pair[k][v][s] for k in CHOICE_PAIRS) for s in SAMPLES} for v in per_pair["P1"]}
        value = _smallest(common)
        own = [_smallest(per_pair[k]) for k in CHOICE_PAIRS]
        note = "trips: the worst of P1..P5 at this value"
        if value is not None and None not in own and value != max(own):
            note += f"; not the largest per-pair value ({max(own)}): the criterion is not monotone in the limit"
        add(rule, "common", "P1-P5", common, None, value, note)

    at_one_unit = designs[designs["sample"] == "8y"].set_index("design")
    for code, d in DESIGNS.items():
        col = "streak_gold_trips_per_year" if d.bot == 0 else "streak_btc_trips_per_year"
        needs: Dict[str, Optional[float]] = {}
        worst: Dict[float, Dict[str, float]] = {}
        for key in CHOICE_PAIRS:
            if code not in PAIRS[key]:
                continue
            rates = _rates(grid, key, "STREAK", col)
            needs[key] = _smallest(rates)
            for v, r in rates.items():
                worst[v] = {s: max(r[s], worst.get(v, {}).get(s, 0.0)) for s in SAMPLES}
        value = None if (not needs or None in needs.values()) else max(needs.values())
        note = "N needed by pair type: " + ", ".join(f"{k} {'none' if v is None else int(v)}" for k, v in needs.items())
        if value is not None:
            note += f"; {int(at_one_unit.loc[code, f'streak_trips_n{int(value)}'])} trips in the 8 years at one unit"
        add("STREAK", "design", code, worst, None, value, note)
    return pd.DataFrame(rows)


def chosen_limits(chosen: pd.DataFrame, key: str, common: bool = False) -> dict:
    """The limits of one pair type from ``choose``: its own X and Y (or the common set) and its two bots' N."""
    c = chosen.set_index(["rule", "scope_type", "scope"])["value"]

    def get(rule: str, scope_type: str, scope: str) -> Optional[float]:
        v = c.get((rule, scope_type, scope), np.nan)
        return None if pd.isna(v) else float(v)

    g, b = PAIRS[key]
    scope = ("common", "P1-P5") if common else ("pair", key)
    ng, nb = get("STREAK", "design", g), get("STREAK", "design", b)
    return dict(x=get("DROP", *scope), y=get("DAY", *scope),
                n=(None if ng is None else int(ng), None if nb is None else int(nb)))


def combined(pairs: Dict[str, Pair], chosen: pd.DataFrame, log=print) -> pd.DataFrame:
    """The three chosen limits TOGETHER, per pair type: with its own X and Y and with the common set, at D = 24 h
    and at the sensitivity values of D."""
    rows = []
    for key, pair in pairs.items():
        for limits_name in ("per_pair", "common"):
            lim = chosen_limits(chosen, key, common=limits_name == "common")
            for d_hours in (D_DEFAULT,) + D_SENSITIVITY:
                run = pair.run(x=lim["x"], y=lim["y"], n=lim["n"], d_hours=d_hours)
                for sample in SAMPLES:
                    rows.append(dict(pair=key, gold=pair.gold, btc=pair.btc, limits=limits_name, drop_x_pct=lim["x"],
                                     day_y_pct=lim["y"], streak_n_gold=lim["n"][0], streak_n_btc=lim["n"][1],
                                     d_hours=d_hours, sample=sample, **effect_row(pair, run, sample)))
        log(f"  {key}: the chosen limits together, D = {', '.join(f'{d:g}' for d in (D_DEFAULT,) + D_SENSITIVITY)} h")
    return pd.DataFrame(rows)


def by_start_year(pairs: Dict[str, Pair], chosen: pd.DataFrame) -> pd.DataFrame:
    """The chosen limits together (D = 24 h), the rolling accounts grouped by the calendar year they start in."""
    rows = []
    for key, pair in pairs.items():
        lim = chosen_limits(chosen, key)
        run = pair.run(x=lim["x"], y=lim["y"], n=lim["n"])
        names = pair.names("all84")
        r = run.loc[names].assign(change=run.loc[names, "end"] - pair.base.loc[names, "end"], year=[a[:4] for a in names])
        for year, g in r.groupby("year"):
            years = float(g["years"].sum())
            rows.append(dict(pair=key, start_year=int(year), accounts=len(g), trips_per_year=g["trip_events"].sum() / years,
                             drop_trips_per_year=g["trips_drop"].sum() / years, day_trips_per_year=g["trips_day"].sum() / years,
                             streak_gold_trips_per_year=g["trips_streak_gold"].sum() / years,
                             streak_btc_trips_per_year=g["trips_streak_btc"].sum() / years,
                             end_change_mean=g["change"].mean()))
    return pd.DataFrame(rows)


def trips_8y(pairs: Dict[str, Pair], chosen: pd.DataFrame) -> pd.DataFrame:
    """Every trip of each pair type's 8-year account under its chosen limits (D = 24 h): when, which rule, the balance."""
    out = []
    for key, pair in pairs.items():
        lim = chosen_limits(chosen, key)
        a = next(a for a in pair.accounts if a.name == "8y")
        log: list = []
        simulate(pair.events["8y"], pair.steps, a.start_ms, None if lim["x"] is None else lim["x"] / 100.0,
                 None if lim["y"] is None else lim["y"] / 100.0, lim["n"], D_DEFAULT, trip_log=log)
        for e in log:
            rules = [name for name in ("drop", "day", "streak") if e[name]]
            out.append(dict(pair=key, time=pd.Timestamp(e["time_ms"], unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S"),
                            rule="+".join(rules).upper(), closing_bot=(pair.gold, pair.btc)[e["bot"]],
                            balance=e["balance"], drop_from_peak_pct=(e["peak"] - e["balance"]) / e["peak"] * 100.0,
                            day_loss_pct=(e["day0"] - e["balance"]) / e["day0"] * 100.0, losing_streak=e["losing_streak"]))
    return pd.DataFrame(out)


def streak_unblock_check(pairs: Dict[str, Pair], chosen: pd.DataFrame) -> pd.DataFrame:
    """The chosen limits together (D = 24 h) under the other reading of the STREAK unblock, in which it also rebases
    the account's DROP peak and DAY reference: how much the reading matters."""
    rows = []
    for key, pair in pairs.items():
        lim = chosen_limits(chosen, key)
        runs = {flag: pair.run(x=lim["x"], y=lim["y"], n=lim["n"], streak_unblock_rebases_account=flag)
                for flag in (False, True)}
        for sample in SAMPLES:
            names = pair.names(sample)
            a, b = effect_row(pair, runs[False], sample), effect_row(pair, runs[True], sample)
            cols = ["end", "trip_events", "trips_drop", "trips_day", "trips_streak_gold", "trips_streak_btc"]
            differ = (runs[False].loc[names, cols] != runs[True].loc[names, cols]).any(axis=1)
            rows.append(dict(pair=key, sample=sample, accounts=len(names), accounts_that_differ=int(differ.sum()),
                             trips_per_year=a["trips_per_year"], trips_per_year_if_rebased=b["trips_per_year"],
                             end_change_mean=a["end_change_mean"], end_change_mean_if_rebased=b["end_change_mean"]))
    return pd.DataFrame(rows)


# ───────────────────────────── the report ─────────────────────────────

def _usd(v, sign: bool = False, cents: bool = False) -> str:
    if v is None or pd.isna(v):
        return "-"
    v = round(float(v), 2 if cents else 0)
    body = f"${abs(v):,.2f}" if cents else f"${abs(v):,.0f}"
    return "−" + body if v < 0 else ("+" + body if sign and v > 0 else body)


def _pct(v, digits: int = 1) -> str:
    return "-" if v is None or pd.isna(v) else f"{float(v):.{digits}f}%"


def _lim(v) -> str:
    """A limit in per cent as it is set: 7.5%, 15%."""
    return "none in the grid" if v is None or pd.isna(v) else f"{float(v):g}%"


def _n(v) -> str:
    return "none" if v is None or pd.isna(v) else f"{int(v)}"


def _rate(v) -> str:
    return "-" if v is None or pd.isna(v) else f"{float(v):.2f}"


def _usd_signed(v) -> str:
    return _usd(v, True)


def _pct0(v) -> str:
    return _pct(v, 0)


def _of(fmt, *values) -> str:
    """Several figures of one kind in one cell: "a / b / c"."""
    return " / ".join(fmt(v) for v in values)


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> List[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows] + [""]


def _pair_name(key: str) -> str:
    g, b = PAIRS[key]
    return f"{DESIGNS[g].name} + {DESIGNS[b].name}"


def _pair_label(key: str) -> str:
    return key if key in CHOICE_PAIRS else f"{key} (information only)"


def _report_tables(tb: Dict[str, pd.DataFrame]) -> SimpleNamespace:
    """The tables indexed the way the report's sections read them."""
    return SimpleNamespace(
        grid=tb["rule_grid"], rep=tb["reproduction"], unb=tb["streak_unblock_check"],
        des=tb["designs"].set_index(["design", "sample"]).sort_index(),
        ns=tb["pairs_no_safety"].set_index(["pair", "sample"]).sort_index(),
        ch=tb["chosen"].set_index(["rule", "scope_type", "scope"]).sort_index(),
        comb=tb["combined"].set_index(["pair", "limits", "d_hours", "sample"]).sort_index(),
        years=tb["combined_by_start_year"].set_index(["pair", "start_year"]).sort_index(),
        anc=tb["anchors"].set_index(["scope", "what"]).sort_index(),
        lim={k: chosen_limits(tb["chosen"], k) for k in PAIRS}, common=chosen_limits(tb["chosen"], "P1", common=True))


def _report_limits(t: SimpleNamespace, reading: str) -> List[str]:
    L = ["# Auto-safety limits for the live accounts: what the 8-year backtest gives", "",
         "*Calibration of 2026-11-21. `python3 -m backtesting.research.live_safety` rebuilds every figure on this page "
         "from the trade records of the final-ten study; the tables are in this folder as CSV files.*", ""]
    if reading != "engine":
        L += ["**NOT the tables of record.** This copy was made with the first formula for the one-unit profit "
              "(`--reading spec`), which halves the profit and loss of gold Top 1's two-leg trades (section 9).", ""]
    L += ["The breaker blocks new trades after losses. It has three limits. This page sets them from the backtest by one "
          "rule, fixed before any number was read:", "",
          f"> For each limit, take the tightest value that would have blocked at most once in two account-years on "
          f"average ({MAX_TRIPS_PER_YEAR:g} blocks per account-year), both in the 24 most recent 12-month accounts and "
          f"in all 84. This is the \"medium\" strictness that was asked for.", "",
          "## The limits the rule gives", ""]
    rows = []
    for k in PAIRS:
        c = t.comb.loc[(k, "per_pair", D_DEFAULT)]
        rows.append([_pair_label(k), _pair_name(k), _lim(t.lim[k]["x"]), _lim(t.lim[k]["y"]),
                     f"{_n(t.lim[k]['n'][0])} / {_n(t.lim[k]['n'][1])}",
                     f"{_rate(c.loc['recent24', 'trips_per_year'])} / {_rate(c.loc['all84', 'trips_per_year'])}"])
    L += _table(["Account type", "Gold bot + BTC bot",
                 "DROP: block both bots when the balance is this far below its high", "DAY: or when one day's loss reaches",
                 "STREAK: block one bot after this many losing trades in a row (gold / BTC)",
                 "Blocks per account-year with all three on (recent 24 / all 84)"], rows)
    L += [f"Each limit on its own stays at or below {MAX_TRIPS_PER_YEAR:g} blocks per account-year. The last column "
          f"adds the three together (STREAK counts once per bot), so it can be higher.", "",
          f"One set for every account type, for comparison: DROP **{_lim(t.common['x'])}**, DAY "
          f"**{_lim(t.common['y'])}**, STREAK as in the table (section 7).", "", "### Read this first", ""]

    w = {c: t.des.loc[(c, "8y"), "worst_trade"] for c in DESIGNS}
    share = {c: _pct(-w[c] / START_BALANCE * 100, 0) for c in DESIGNS}
    L.append(f"1. **The breaker stops the next trade, not the one that is open.** At one unit (0.01 lot) the worst "
             f"single trade lost {_usd(-w['xv3'])} for gold V3-lite and {_usd(-w['xt1'])} for gold Top 1: "
             f"{share['xv3']} and {share['xt1']} of a {_usd(START_BALANCE)} account. The Turtle's worst was "
             f"{_usd(-w['bs2'])} ({share['bs2']}), gold Top 2's {_usd(-w['xt2'])} and BTC Top 2's {_usd(-w['bt2'])} "
             f"(about {share['xt2']}). A DROP or DAY limit smaller than one such trade is reached by a single trade, "
             f"after the loss is already booked.")

    def at(k: str, sample: str, col: str) -> float:
        return t.comb.loc[(k, "per_pair", D_DEFAULT, sample), col]

    change = [at(k, "recent24", "end_change_mean") for k in CHOICE_PAIRS]
    lower = sum(v < -0.5 for v in change)
    moved = {s: (sum(at(k, s, "worst_drop_pct") < at(k, s, "worst_drop_pct_no_safety") - 1.0 for k in CHOICE_PAIRS),
                 sum(at(k, s, "worst_drop_pct") > at(k, s, "worst_drop_pct_no_safety") + 1.0 for k in CHOICE_PAIRS))
             for s in ("all84", "recent24")}
    L.append(f"2. **On this history the breaker did not make the accounts safer, and it cost some profit.** With the "
             f"three limits on, the average recent account ended lower than without them in {lower} of the "
             f"{len(CHOICE_PAIRS)} account types, by {_usd(-max(change))} to {_usd(-min(change))} (section 5). The "
             f"deepest fall of the worst account became more than one point smaller in {moved['all84'][0]} account "
             f"types and more than one point larger in {moved['all84'][1]} (all 84 accounts; recent 24: "
             f"{moved['recent24'][0]} and {moved['recent24'][1]}). The reason: these bots made money over the period, so "
             f"the trades that a block skipped had made money on balance. A backtest of profitable bots can only show "
             f"how often the breaker interrupts a working bot. It cannot show what the breaker saves when a bot stops "
             f"working, which is what it is for.")
    days = ", ".join(f"{k} {_n(t.ch.loc[('DAY', 'pair', k), 'distinct_trip_days_recent24'])}" for k in CHOICE_PAIRS)
    L.append(f"3. **A few market days decide the counts.** The 12-month accounts overlap, so one bad day is counted in "
             f"up to 12 of them. In the recent 24 accounts the chosen DAY limits were reached on this many different "
             f"days: {days}. One such day more or fewer can move a limit by a grid step.")
    ratio = [t.des.loc[(c, "12m"), "median_losing_trade"] / t.des.loc[(c, "8y"), "median_losing_trade"]
             for c in ("xv3", "xt1", "xt2")]
    last12 = ", ".join(f"{k} {_rate(at(k, 'last12', 'trips_per_year'))}" for k in CHOICE_PAIRS)
    late9 = ", ".join(f"{k} {_rate(at(k, 'late9', 'trips_per_year'))}" for k in CHOICE_PAIRS)
    L.append(f"4. **Accounts started lately were blocked more often than the rule's {MAX_TRIPS_PER_YEAR:g}.** A typical "
             f"losing gold trade is now about {np.mean(ratio):.0f} times larger in dollars than over the 8 years "
             f"(section 2), and a new {_usd(START_BALANCE)} account meets it at its smallest size. With all three "
             f"limits on, the 12 most recent of the 84 starts (Dec 2024 – Nov 2025) had this many blocks per "
             f"account-year: {last12}. Nine later starts (Dec 2025 – Aug 2026, run to the end of the data) had: "
             f"{late9} (section 6). The rule averages such accounts with older, quieter ones.")
    b8, b24 = t.des.loc[("bs2", "8y")], t.des.loc[("bs2", "24m")]
    g = ANCHORS_DESIGN["bs2"]
    L.append(f"5. **The BTC Turtle's one-unit figures are smaller than in the earlier note.** Its worst losing stretch "
             f"at one unit is {_usd(-b8['worst_stretch'])} (not {_usd(-g[0])}), its worst trade "
             f"{_usd(-b24['worst_trade'])} (not {_usd(-g[2])}) and its net profit of the last 24 months "
             f"{_usd(b24['net'], True)} (not {_usd(g[3], True)}). The earlier figures left most Turtle trades at the 2 "
             f"to 4 units of the published account (section 9).")
    return L + [""]


def _report_measured() -> List[str]:
    return ["## 1. What was measured", "",
            "- **The trades.** Every closed trade of each bot's own 8-year backtest, 13 Nov 2018 – 13 Nov 2026, brought "
            "to one unit (0.01 lot). A gold Top 1 trade can hold two legs of one unit, a Turtle trade up to four.",
            f"- **The account.** {_usd(START_BALANCE)}, shared by one gold bot and one BTC bot. Each bot trades "
            f"`floor(half the balance / STEP) + 1` units, at most {UNIT_CAP}, from the balance booked when the trade "
            f"opens. STEP is $1,250 for gold Top 2 and BTC Top 2, $1,750 for gold V3-lite and Top 1, $2,500 for the "
            f"Turtle, so a bot trades 1 unit until the account reaches $2,500, $3,500 or $5,000.",
            "- **The accounts.** A new account on the 1st of every month from Dec 2018 to Nov 2025, each run for 12 "
            "months: 84 accounts. \"Recent 24\" are the starts from Dec 2023 to Nov 2025. One more account runs for the "
            "whole 8 years.",
            "- **The three limits.** All are checked on the booked balance (closed trades only), after every closed trade:",
            "  - DROP: the balance is X% below its highest value since the start or the last unblock. Blocks both bots.",
            "  - DAY: the balance is Y% below the balance at 00:00 UTC (after an unblock that day: below the balance at "
            "the unblock). Blocks both bots.",
            "  - STREAK: N closed trades of one bot in a row lost money. Blocks that bot.",
            f"- **A block** stops new trades only. A trade that is open keeps its own stop and target and is booked when "
            f"it closes. The unblock is taken to come {D_DEFAULT:g} hours after the block and starts the counts afresh; "
            f"{', '.join(f'{d:g}' for d in D_SENSITIVITY[:-1])} and {D_SENSITIVITY[-1]:g} hours were run as well.",
            "- **An account-year** is one account for one year. A rate of 0.5 is one block in two years of one account, "
            "or about 5 blocks a year across 10 accounts, per limit.", ""]


def _report_bots(t: SimpleNamespace) -> List[str]:
    L = ["## 2. The five bots at one unit (0.01 lot)", ""]
    rows = []
    for c, d in DESIGNS.items():
        a, r = t.des.loc[(c, "8y")], t.des.loc[(c, "24m")]
        rows.append([d.name, _usd(d.step), f"{int(a['trades']):,} / {int(r['trades'])}",
                     _of(_pct0, a["win_rate_pct"], r["win_rate_pct"]), _of(_usd_signed, a["net"], r["net"]),
                     _of(_usd, a["worst_stretch"], r["worst_stretch"]), _of(_usd, a["worst_trade"], r["worst_trade"]),
                     _of(_n, a["longest_losing_streak"], r["longest_losing_streak"])])
    L += _table(["Bot", "STEP", "Trades", "Winning trades", "Net profit", "Worst losing stretch", "Worst single trade",
                 "Longest run of losing trades"], rows)
    L += ["*Each cell: the 8 years / the last 24 months (trades closed from 13 Nov 2024). Worst losing stretch = the "
          "largest fall of the running total from a high, on closed trades.*", "",
          f"What one losing trade costs now, at one unit, against a {_usd(START_BALANCE)} account (trades closed in the "
          f"last 12 months, from 13 Nov 2025):", ""]
    rows = []
    for c, d in DESIGNS.items():
        r = t.des.loc[(c, "12m")]
        losses = (r["median_losing_trade"], r["losing_trade_1_in_10"], r["worst_trade"])
        rows.append([d.name, int(r["trades"])] + [f"{_usd(-v)} ({_pct(-v / START_BALANCE * 100)})" for v in losses]
                    + [_usd(-t.des.loc[(c, "8y"), "median_losing_trade"])])
    L += _table(["Bot", "Trades in the 12 months", "Typical losing trade (the middle one)",
                 "1 losing trade in 10 lost more than", "Worst trade", "Typical losing trade over the 8 years"], rows)
    return L + ["*The Turtle's 12 months hold too few trades to call anything typical.*", ""]


def _report_no_breaker(t: SimpleNamespace) -> List[str]:
    L = [f"## 3. Two bots on one {_usd(START_BALANCE)} account, no breaker", ""]
    rows = []
    for k in PAIRS:
        for s in ("recent24", "all84", "8y"):
            r = t.ns.loc[(k, s)]
            if s == "8y":                         # one account: one figure per cell
                cells = [_usd(r["end_min"]), _pct(r["worst_drop_pct_max"]), _pct(r["worst_day_loss_pct_max"]), "-"]
            else:
                cells = [_of(_usd, r["end_min"], r["end_median"], r["end_max"]),
                         _of(_pct, r["worst_drop_pct_median"], r["worst_drop_pct_max"]),
                         _of(_pct, r["worst_day_loss_pct_median"], r["worst_day_loss_pct_max"]),
                         _of(_n, r["below_1000"], r["below_750"])]
            rows.append([_pair_label(k) if s == "recent24" else "", SAMPLE_NAMES[s]] + cells)
    L += _table(["Account type", "Accounts", "End balance: lowest / middle / highest",
                 "Deepest fall from a high: middle / worst account", "Worst single day: middle / worst account",
                 "Accounts ending below $1,000 / $750"], rows)
    return L + ["*Deepest fall = the largest fall of the booked balance below its highest value so far, in per cent of "
                "that high. Worst single day = the largest loss booked within one UTC day, in per cent of the balance at "
                "00:00. These are what the DROP and DAY limits look at. The 8-year account is one account: one figure "
                "per cell.*", ""]


def _report_each_limit(t: SimpleNamespace) -> List[str]:
    L = ["## 4. Each limit on its own", "",
         f"Blocks per account-year with only that limit on (unblock after {D_DEFAULT:g} hours). The chosen value is in "
         f"bold: the tightest one at or below {MAX_TRIPS_PER_YEAR:g} in both rows.", ""]

    def grid_rows(label: str, rates: Dict[float, Dict[str, float]], pick, values: Sequence[float]) -> List[list]:
        """Two rows (recent 24, all 84) of blocks per account-year over the grid, the chosen value in bold."""
        return [[label if s == "recent24" else "", SAMPLE_NAMES[s]]
                + [f"**{_rate(rates[float(v)][s])}**" if v == pick else _rate(rates[float(v)][s]) for v in values]
                for s in CRITERION_SAMPLES]

    for rule, col, what in (("DROP", "drop_trips_per_year", "the balance is this far below its high"),
                            ("DAY", "day_trips_per_year", "one day's loss reaches")):
        L += [f"**{rule}: block both bots when {what}**", ""]
        rows = []
        for k in PAIRS:
            rows += grid_rows(_pair_label(k), _rates(t.grid, k, rule, col), t.lim[k]["x" if rule == "DROP" else "y"], GRIDS[rule])
        L += _table(["Account type", "Accounts"] + [f"{v:g}%" for v in GRIDS[rule]], rows)
    L += ["**STREAK: block one bot after this many losing trades in a row**", ""]
    rows = []
    for c, d in DESIGNS.items():
        key = next(k for k in CHOICE_PAIRS if c in PAIRS[k])       # a bot's own streaks are the same in every pair type
        col = "streak_gold_trips_per_year" if d.bot == 0 else "streak_btc_trips_per_year"
        rows += grid_rows(d.name, _rates(t.grid, key, "STREAK", col), t.ch.loc[("STREAK", "design", c), "value"], GRID_N)
    L += _table(["Bot", "Accounts"] + [str(v) for v in GRID_N], rows)

    L += ["How firm each choice is, and what the limit did on its own:", ""]
    rows = []
    for rule, seen in (("DROP", "worst_drop_pct_max"), ("DAY", "worst_day_loss_pct_max")):
        for k in PAIRS:
            c = t.ch.loc[(rule, "pair", k)]
            alone = t.grid[(t.grid["pair"] == k) & (t.grid["rule"] == rule) & (t.grid["value"] == c["value"])]
            alone = alone.set_index("sample")["end_change_mean"]
            tighter = "not tried" if pd.isna(c["tighter_value"]) else \
                f"{_lim(c['tighter_value'])}: {_of(_rate, c['tighter_trips_recent24'], c['tighter_trips_all84'])}"
            rows.append([_pair_label(k), rule, f"**{_lim(c['value'])}**",
                         _of(_rate, c["trips_per_year_recent24"], c["trips_per_year_all84"]), tighter,
                         f"{_lim(c['wider_value'])}: {_of(_rate, c['wider_trips_recent24'], c['wider_trips_all84'])}",
                         _of(_n, c["distinct_trip_days_recent24"], c["distinct_trip_days_all84"]),
                         _pct(t.ns.loc[(k, "all84"), seen]), _of(_usd_signed, alone["recent24"], alone["all84"]),
                         _lim(c["value_if_last12_too"]), _lim(c["value_if_latest_too"])])
    L += _table(["Account type", "Limit", "Chosen", "Blocks per account-year", "One step tighter", "One step wider",
                 "Different days it was reached", "Largest value seen with no breaker, all 84 accounts",
                 "Average change of the end balance", "If the last 12 starts had to meet the rule too",
                 "and the 9 late starts as well"], rows)
    L += [f"*Pairs of figures: recent 24 / all 84 accounts. \"One step tighter\" fails the rule; \"not tried\" = the "
          f"chosen value is the tightest in the grid. The last two columns are not part of the rule. They show what the "
          f"same rule would give if the 12 most recent of the 84 starts (Dec 2024 – Nov 2025), and then also the 9 "
          f"late starts of section 6, had to stay at or below {MAX_TRIPS_PER_YEAR:g} as well.*", ""]
    rows = []
    for c, d in DESIGNS.items():
        r, a = t.ch.loc[("STREAK", "design", c)], t.des.loc[(c, "8y")]
        rows.append([d.name, f"**{_n(r['value'])}**", _of(_rate, r["trips_per_year_recent24"], r["trips_per_year_all84"]),
                     f"{_n(r['tighter_value'])}: {_of(_rate, r['tighter_trips_recent24'], r['tighter_trips_all84'])}",
                     _of(_n, a["longest_losing_streak"], t.des.loc[(c, "24m"), "longest_losing_streak"]),
                     "-" if pd.isna(r["value"]) else int(a[f"streak_trips_n{int(r['value'])}"]),
                     _n(r["value_if_latest_too"])])
    return L + _table(["Bot", "Chosen N", "Blocks per account-year (recent 24 / all 84)", "One fewer (fails the rule)",
                       "Longest run of losing trades: 8 years / last 24 months",
                       "Times N in a row happened in the 8 years, at one unit",
                       "If the last 12 and the 9 late starts had to meet the rule too"], rows)


def _by_rule(c: pd.Series) -> str:
    """Blocks per account-year of one combined run: DROP / DAY / STREAK gold / STREAK BTC."""
    return _of(_rate, c["drop_trips_per_year"], c["day_trips_per_year"], c["streak_gold_trips_per_year"],
               c["streak_btc_trips_per_year"])


def _report_together(t: SimpleNamespace) -> List[str]:
    L = ["## 5. The three chosen limits together", "",
         f"Each account type with its own DROP and DAY limits and its two bots' STREAK limits, unblock after "
         f"{D_DEFAULT:g} hours.", ""]
    rows = []
    for k in PAIRS:
        for s in ("recent24", "all84", "8y"):
            c = t.comb.loc[(k, "per_pair", D_DEFAULT, s)]
            rows.append([_pair_label(k) if s == "recent24" else "", SAMPLE_NAMES[s], _by_rule(c),
                         f"**{_rate(c['trips_per_year'])}**", _pct0(c["share_with_trip_pct"]),
                         _rate(c["skipped_trades_per_year"]),
                         _of(_usd_signed, c["end_change_mean"], c["end_change_worst"], c["end_change_best"]),
                         _of(_pct, c["worst_drop_pct"], c["worst_drop_pct_no_safety"]),
                         _of(_usd, c["end_min"], c["end_min_no_safety"])])
    L += _table(["Account type", "Accounts", "Blocks per account-year: DROP / DAY / STREAK gold / STREAK BTC", "All",
                 "Accounts with a block", "Trades skipped per account-year",
                 "End balance against no breaker: average / worst account / best account",
                 "Deepest fall, worst account: with / without", "Lowest end balance: with / without"], rows)
    L += ["*\"All\" counts a closed trade that reaches two limits at once as one block.*", "",
          "How long the block lasts (hours until the unblock), recent 24 / all 84 accounts:", ""]
    hours = sorted((D_DEFAULT,) + D_SENSITIVITY)
    rows = []
    for k in PAIRS:
        for name, col, fmt in (("blocks per account-year", "trips_per_year", _rate),
                               ("average change of the end balance", "end_change_mean", _usd_signed)):
            rows.append([_pair_label(k) if col == "trips_per_year" else "", name]
                        + [_of(fmt, t.comb.loc[(k, "per_pair", h, "recent24"), col], t.comb.loc[(k, "per_pair", h, "all84"), col])
                           for h in hours])
    L += _table(["Account type", ""] + [f"{h:g} hours" for h in hours], rows)
    L += ["*A block of 4 hours skips few trades, in most account types none. After a losing trade the bot that lost waits "
          "by itself before its next trade (4 hours for gold Top 1 and BTC Top 2, 12 hours for gold V3-lite and gold "
          "Top 2), and a trade that opens at the very moment a block ends is taken. What a 4-hour block can skip is a "
          "trade of the other bot.*", "",
          "When the accounts were started (all three limits on, 24 hours): blocks per account-year by the year of the "
          "account's start.", ""]
    start_years = sorted(y for y in t.years.index.get_level_values("start_year").unique() if y >= 2019)
    rows = [[_pair_label(k)] + [_rate(t.years.loc[(k, y), "trips_per_year"]) for y in start_years] for k in PAIRS]
    L += _table(["Account type"] + [f"{y} ({int(t.years.loc[('P1', y), 'accounts'])} starts)" for y in start_years], rows)
    return L + ["*Every block of the six 8-year accounts, with its date, limit and balance, is in `trips_8y.csv`.*", ""]


def _report_late_starts(t: SimpleNamespace) -> List[str]:
    years = t.comb.loc[("P1", "per_pair", D_DEFAULT, "late9"), "account_years"]
    L = ["## 6. Accounts started in the last year of the data", "",
         f"Outside the rule, for information. The latest of the 84 accounts starts on 1 Nov 2025. Here a new "
         f"{_usd(START_BALANCE)} account also starts on the 1st of every month from Dec 2025 to Aug 2026 and runs to the "
         f"end of the data (13 Nov 2026): 9 accounts of 3 to 11 months, {years:.1f} account-years in all. They are the "
         f"nearest thing in the backtest to an account opened now: one unit, on {_usd(START_BALANCE)}, at this year's "
         f"trade sizes. They share most of their months, so one bad week is counted in several of them.", ""]
    rows = []
    for k in PAIRS:
        late, recent = t.ns.loc[(k, "late9")], t.ns.loc[(k, "recent24")]
        own, com = t.comb.loc[(k, "per_pair", D_DEFAULT, "late9")], t.comb.loc[(k, "common", D_DEFAULT, "late9")]
        rows.append([_pair_label(k), _of(_pct, late["worst_drop_pct_median"], late["worst_drop_pct_max"]),
                     _of(_pct, recent["worst_drop_pct_median"], recent["worst_drop_pct_max"]), _by_rule(own),
                     f"**{_rate(own['trips_per_year'])}**", int(own["distinct_trip_days"]),
                     f"**{_rate(com['trips_per_year'])}**", int(com["distinct_trip_days"])])
    return L + _table(["Account type", "Deepest fall with no breaker, the 9 late starts: middle / worst",
                       "The same, recent 24 accounts",
                       "Own limits, blocks per account-year: DROP / DAY / STREAK gold / STREAK BTC", "All", "Different days",
                       f"Common set ({_lim(t.common['x'])} / {_lim(t.common['y'])}): all blocks per account-year",
                       "Different days"], rows)


def _report_common(t: SimpleNamespace) -> List[str]:
    L = ["## 7. One set of limits for every account type", "",
         f"The tightest DROP and DAY values that meet the rule in every one of P1 – P5: **DROP {_lim(t.common['x'])}, "
         f"DAY {_lim(t.common['y'])}**, with the STREAK limits of section 4. All three on, unblock after "
         f"{D_DEFAULT:g} hours:", ""]
    rows = []
    for k in PAIRS:
        a, b = t.comb.loc[(k, "common", D_DEFAULT, "recent24")], t.comb.loc[(k, "common", D_DEFAULT, "all84")]
        o, p = t.comb.loc[(k, "per_pair", D_DEFAULT, "recent24")], t.comb.loc[(k, "per_pair", D_DEFAULT, "all84")]
        rows.append([_pair_label(k), _of(_lim, t.lim[k]["x"], t.lim[k]["y"]),
                     _of(_rate, o["trips_per_year"], p["trips_per_year"]), _of(_rate, a["trips_per_year"], b["trips_per_year"]),
                     _of(_usd_signed, o["end_change_mean"], p["end_change_mean"]),
                     _of(_usd_signed, a["end_change_mean"], b["end_change_mean"]),
                     _of(_pct, b["worst_drop_pct"], b["worst_drop_pct_no_safety"])])
    L += _table(["Account type", "Its own DROP / DAY", "Blocks per account-year, own limits",
                 "Blocks per account-year, common set", "Average change of the end balance, own limits",
                 "Average change of the end balance, common set",
                 "Deepest fall with the common set, worst of all 84: with / without"], rows)
    return L + ["*Pairs of figures: recent 24 / all 84 accounts.*", ""]


def _report_caveats() -> List[str]:
    return ["## 8. What these numbers cannot tell you", "",
            "- **Closed trades only.** The breaker, and this replay, see the booked balance. A trade that is deep in "
            "loss but still open does not move it. The account's equity, open losses included, can fall further than "
            "the figures here.",
            "- **A replay, not a new backtest.** A trade at 2 units is taken to make twice its one-unit profit: exact "
            "for the Turtle; for the other four bots the engine itself can differ by cents, and now and then by a "
            "trade, when the unit changes (the sizing study measured it). A skipped trade is taken to change no later "
            "trade: after an unblock the bot waits for the next recorded trade. A real bot may instead enter late into "
            "the move it was kept out of, which matters most for the Turtle, whose trades last weeks.",
            "- **The 12-month accounts are cut out of one 8-year run.** A bot really started on the 1st of a month has "
            "no open trade and no pause carried over; here it takes up the 8-year run's next trade.",
            "- **The bots were chosen on this data.** All five were selected on 2021 – 2026. Only Nov 2018 – Dec 2020 "
            "was new to them. Losing runs in real trading can be longer than any in the backtest.",
            "- **84 accounts are not 84 independent years.** They are cut from 8 years, and neighbours share 11 of "
            "their 12 months.",
            f"- **Today's trade sizes are barely tested from a small balance.** Most of the 84 accounts met the small "
            f"gold trades of 2019 – 2024, and the recent ones had grown before the trades became large. An account that "
            f"starts at {_usd(START_BALANCE)} now meets them at one unit from the first day. Section 6 is the only "
            f"evidence on that, and it is less than one year of market.",
            f"- **The unblock is taken to come on time.** A real unblock can come sooner or much later than "
            f"{D_DEFAULT:g} hours. Longer blocks skipped more trades and mostly cost more (section 5).",
            "- **No swap, commission or slippage beyond the spread,** as in the backtests themselves.",
            "- **Limits tighter than the grid were not tried.** Where the chosen value is the tightest of the grid, a "
            "tighter one might also have met the rule.", ""]


def _report_checks(t: SimpleNamespace) -> List[str]:
    rep = t.rep
    total = int(rep["trades"].sum())
    L = ["## 9. How the numbers were checked", "",
         f"**The one-unit profit of every trade.** Each bot's 8-year trades were replayed on the study's own account "
         f"({_usd(PUBLISHED_START)}, STEP {_usd(PUBLISHED_STEP)}, whole balance) by the same code that runs the accounts "
         f"above. The unit came out equal to the recorded one on {total - int(rep['unit_mismatches_engine'].sum()):,} of "
         f"{total:,} trades, and the closing balance equals the recorded one to the cent:", ""]
    rows = []
    for _, r in rep.iterrows():
        floating = _usd(r["open_at_end_floating"], True, True)
        note = "no trade open at the end" if abs(r["open_at_end_floating"]) < 0.005 else \
            f"a trade of {int(r['open_at_end_units'])} units still open at the end: {floating}"
        rows.append([r["name"], f"{int(r['trades']):,}", _usd(r["published_final"], cents=True),
                     _usd(r["rebuilt_final_engine"], cents=True), int(r["unit_mismatches_engine"]), note])
    L += _table(["Bot", "Trades", "Published final equity", "Rebuilt closing balance", "Trades with a different unit",
                 "Why the two differ"], rows)
    x1 = rep.set_index("design").loc["xt1"]
    L += ["The published figure is equity: it includes a trade still open on 13 Nov 2026, which a list of closed trades "
          "cannot hold. A run of the bot's own engine over 20 Oct – 13 Nov 2026 at one unit (made once, on 2026-11-21) "
          "ended with these trades open: −$11.21 for gold Top 1 and for gold Top 2, +$10.26 for BTC Top 2, none for "
          "gold V3-lite. Times the units in the table, those are the differences, to the engine's rounding of a cent "
          "or two.", "",
          f"**The first formula was wrong for gold Top 1.** The plan for this calibration took the one-unit profit as "
          f"profit ÷ (lots ÷ 0.01). The two engines write `lots` differently: the bot's own engine writes the total of "
          f"all legs, the Turtle's simulator the size of one leg. {int(x1['two_leg_trades'])} of Top 1's "
          f"{int(x1['trades']):,} trades have two legs, and the formula halves them: the rebuilt account then ends at "
          f"{_usd(x1['rebuilt_final_spec'], cents=True)} instead of {_usd(x1['rebuilt_final_engine'], cents=True)}, with "
          f"a wrong unit on {int(x1['unit_mismatches_spec'])} trades. This page uses lots ÷ 0.01 ÷ legs for the four "
          f"bots of the bot's own engine and lots ÷ 0.01 for the Turtle.", "", "**The earlier one-unit figures.**", ""]
    rows = []
    for c, d in DESIGNS.items():
        g = [t.anc.loc[(c, w)] for w in ANCHOR_NAMES]

        def cell(col: str) -> str:              # four dollar figures (the net profit signed) and the trade count
            return " / ".join(_usd(r[col], i == 3) if i < 4 else str(int(r[col])) for i, r in enumerate(g))

        rows.append([d.name, cell("given"), cell("computed"),
                     "the same" if all(bool(r["reproduced"]) for r in g) else
                     "the earlier figures divided the Turtle's profit by lots ÷ 0.01 ÷ legs, which left most of its trades "
                     "at 2 to 4 units"])
    L += _table(["Bot", "Earlier: worst stretch 8 years / 24 months / worst trade / net profit / trades (last 24 months)",
                 "Here", ""], rows)
    rows = []
    for (g, b) in ANCHORS_PAIR:
        r = t.anc.loc[(f"{g}+{b}", "worst_stretch_24m")]
        why = {"trade by trade": "the same",
               "daily sums": f"the earlier figure is on each day's summed profit ({_usd(r['computed_daily_sums'])}); trade "
                             f"by trade, as the breaker sees it, the stretch is deeper",
               "earlier division": "the Turtle's division, as above"}.get(r["explained_by"], r["explained_by"])
        rows.append([f"{DESIGNS[g].name} + {DESIGNS[b].name}", _usd(r["given"]), _usd(r["computed"]), why])
    L += _table(["Two bots, one unit each, last 24 months: worst losing stretch", "Earlier", "Here", ""], rows)
    differ = t.unb[t.unb["sample"].isin(CRITERION_SAMPLES)]
    return L + ["**The replay itself.** `python3 -m backtesting.research.live_safety check` runs it on seven hand-worked "
                "accounts, one for each convention: the sizing steps, a trade that opens on the instant of a block or of "
                "an unblock, the day's reference after an unblock, a trade open across a block, two limits reached at "
                "once. A second replay, written separately, gave the same result on every one of 9,588 "
                "account-and-setting combinations (run once, on 2026-11-21; it is not part of the module).", "",
                f"**One reading that could be made two ways.** After a STREAK block, the unblock restarts that bot's "
                f"count only; the account's high and the day's reference stay. Restarting those as well would change "
                f"{int(differ['accounts_that_differ'].max())} of 84 accounts at most in any account type, and no limit: "
                f"the limits are chosen from the runs with one limit on.", ""]


def write_report(path: Path, tb: Dict[str, pd.DataFrame], reading: str = "engine") -> None:
    """SAFETY_CALIBRATION.md: every figure is read from the tables in ``tb`` (the CSV files of the same names)."""
    t = _report_tables(tb)
    lines = (_report_limits(t, reading) + _report_measured() + _report_bots(t) + _report_no_breaker(t)
             + _report_each_limit(t) + _report_together(t) + _report_late_starts(t) + _report_common(t)
             + _report_caveats() + _report_checks(t))
    path.write_text("\n".join(lines), encoding="utf-8")


# ───────────────────────────── the hand-worked cases ─────────────────────────────

def _hand_events(gold: Sequence[tuple], btc: Sequence[tuple] = ()) -> Events:
    """Hand-written trades (open hour, close hour, one-unit P/L); hours count from 2020-01-01 00:00 UTC."""
    t0 = _to_ms("2020-01-01")

    def frame(rows: Sequence[tuple]) -> Optional[pd.DataFrame]:
        if not rows:
            return None
        return pd.DataFrame({"open_ms": [t0 + int(o * HOUR_MS) for o, _, _ in rows],
                             "close_ms": [t0 + int(c * HOUR_MS) for _, c, _ in rows], "p1": [float(p) for _, _, p in rows]})

    return account_events(frame(gold), frame(btc), t0, t0 + 10 * 365 * DAY_MS)


def self_check(log=print) -> None:
    """The replay on small accounts whose results are worked out by hand (all at $1,500, STEP $1,250, D = 24 h)."""
    t0, steps = _to_ms("2020-01-01"), (1250.0, 1250.0)

    def expect(name: str, got: dict, **want) -> None:
        for key, value in want.items():
            if not math.isclose(got[key], value, rel_tol=0, abs_tol=1e-9):
                raise AssertionError(f"{name}: {key} = {got[key]!r}, expected {value!r}")
        log(f"  ok  {name}")

    # 1. sizing: 1 unit below $2,500, 2 units from $2,500 (half of it = one STEP), back to 1 below
    r = simulate(_hand_events([(1, 2, 1100), (3, 4, -100), (5, 6, 10)]), steps, t0)
    expect("sizing steps with the balance", r, end=2410.0, max_units_gold=2, worst_drop=200 / 2600, trip_events=0)

    # 2. DROP 20 %: 1600 -> 1400 (12.5 %) -> 1250 (21.9 %) trips at hour 6; opens at hour 6 (the trip instant) and 10
    #    are skipped; the open at hour 30 (the unblock instant) is taken; the new peak is 1250, so 1150 is 8 % and
    #    950 is 24 %: a second trip
    r = simulate(_hand_events([(1, 2, 100), (3, 4, -200), (5, 6, -150), (6, 7, 50), (10, 11, 500), (30, 31, -100),
                               (32, 33, -200)]), steps, t0, x=0.20)
    expect("DROP: the block's two ends and the new peak", r, trips_drop=2, trip_events=2, skipped_gold=2, end=950.0,
           worst_drop=650 / 1600)

    # 3. DAY 10 %: 1500 -> 1400 -> 1340 (10.7 %) trips at hour 3. A gold trade open at the trip closes at hour 26
    #    (the next day, still blocked): 1300. The unblock at hour 27 makes 1300 the day's reference, not the 1340 of
    #    00:00: 1200 is 7.7 % (no trip), 1160 is 10.8 % (trip)
    r = simulate(_hand_events([(1, 2, -100), (2.5, 26, -40), (27, 29, -100), (30, 31, -40)], [(1, 3, -60)]), steps, t0,
                 y=0.10)
    expect("DAY: the reference after an unblock", r, trips_day=2, skipped_gold=0, end=1160.0, worst_day=180 / 1340,
           worst_day_net=180 / 1340)

    # 4. STREAK 3 on the gold bot: three losses trip at hour 6; its next trade is skipped, the BTC bot trades on;
    #    after the unblock the count starts at 0: loss, loss, win, then three losses trip again
    r = simulate(_hand_events([(1, 2, -10), (3, 4, -10), (5, 6, -10), (7, 8, 100), (30, 31, -10), (32, 33, -10),
                               (34, 35, 10), (36, 37, -10), (38, 39, -10), (40, 41, -10)], [(7, 9, -5)]), steps, t0,
                 n=(3, None))
    expect("STREAK: one bot blocked, the count restarts", r, trips_streak_gold=2, trips_streak_btc=0, skipped_gold=1,
           skipped_btc=0, end=1425.0)

    # 5. DROP 10 %: 1500 -> 1340 trips at hour 2. The BTC trade open at the trip is booked at hour 5 (1040) and trips
    #    nothing; the unblock makes 1040 the peak, so 990 is 4.8 %: no second trip
    r = simulate(_hand_events([(1, 2, -160)], [(1, 5, -300), (26, 27, -50)]), steps, t0, x=0.10)
    expect("a trade open across a block is booked, the breaker stays latched", r, trips_drop=1, trip_events=1,
           skipped_btc=0, end=990.0, worst_drop=510 / 1500)

    # 6. the third loss reaches DROP 1.9 % (30 / 1500 = 2 %) and STREAK 3 at once: one block, counted by both rules
    r = simulate(_hand_events([(1, 2, -10), (3, 4, -10), (5, 6, -10)]), steps, t0, x=0.019, n=(3, None))
    expect("two limits reached by one closed trade", r, trips_drop=1, trips_streak_gold=1, trip_events=1)

    # 7. STREAK 2 on the BTC bot: its second loss in a row is booked while the account is blocked (DROP at hour 2);
    #    nothing trips then, and the account unblock sets the count to 0, so the next loss is the first again
    r = simulate(_hand_events([(1, 2, -160)], [(0.2, 0.5, -10), (1, 3, -10), (26, 27, -10)]), steps, t0, x=0.10,
                 n=(None, 2))
    expect("no STREAK trip while the account is blocked", r, trips_drop=1, trips_streak_btc=0, trip_events=1, end=1310.0)

    rep = reproduction()
    same_balance = np.allclose(rep["rebuilt_final_engine"], rep["recorded_closed_balance"], atol=0.005)
    if int(rep["unit_mismatches_engine"].sum()) or not same_balance:
        raise AssertionError("the published accounts are not rebuilt from the one-unit P/L")
    log(f"  ok  the five published accounts: {int(rep['trades'].sum()):,} trades, every unit and closing balance")


# ───────────────────────────── running it ─────────────────────────────

def run_all(out: Path = OUT, reading: str = "engine", log=print) -> Dict[str, pd.DataFrame]:
    """Every table and the report."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    trades = {code: load_trades(code, reading) for code in DESIGNS}
    tb: Dict[str, pd.DataFrame] = {"reproduction": reproduction(), "designs": designs_table(trades), "anchors": anchors(trades)}
    log(f"trades at one unit: {', '.join(f'{c} {len(t):,}' for c, t in trades.items())}")
    pairs = {key: Pair(key, trades, accounts()) for key in PAIRS}
    tb["pairs_no_safety"] = no_safety_table(pairs)
    log("every rule alone:")
    tb["rule_grid"] = rule_grid(pairs, log)
    tb["chosen"] = choose(tb["rule_grid"], tb["designs"])
    log("the chosen limits together:")
    tb["combined"] = combined(pairs, tb["chosen"], log)
    tb["combined_by_start_year"] = by_start_year(pairs, tb["chosen"])
    tb["trips_8y"] = trips_8y(pairs, tb["chosen"])
    tb["streak_unblock_check"] = streak_unblock_check(pairs, tb["chosen"])
    for name, frame in tb.items():
        frame.round(4).to_csv(out / f"{name}.csv", index=False)
    write_report(out / "SAFETY_CALIBRATION.md", tb, reading)
    log(f"written: {', '.join(sorted(p.name for p in out.iterdir()))} in {out}")
    return tb


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python3 -m backtesting.research.live_safety",
                                 description="Calibrate the live accounts' auto-safety breaker on the 8-year backtest.")
    ap.add_argument("command", nargs="?", default="run", choices=("run", "check"),
                    help="run: every table and the report (default); check: the replay against hand-worked cases")
    ap.add_argument("--out", type=Path, default=OUT, help=f"output folder (default {OUT})")
    ap.add_argument("--reading", choices=("engine", "spec"), default="engine",
                    help="how the lots column gives the units: engine (per engine, the tables of record) or spec (the "
                         "brief's formula, wrong for gold Top 1; write it to another --out)")
    args = ap.parse_args(argv)
    if args.command == "check":
        self_check()
        return
    if args.reading != "engine" and Path(args.out).resolve() == OUT.resolve():
        ap.error("--reading spec must not overwrite the tables of record: give another --out")
    run_all(args.out, args.reading)


if __name__ == "__main__":
    main()
