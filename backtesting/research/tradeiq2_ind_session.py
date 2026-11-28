"""
Session Hunter [TradeIQ] (Pine v6, MPL-2.0, (c) TradeIQ), port A: the script's five ICT session setups, their seven
optional confirmations and its own trade manager, rebuilt bar by bar from the chart bars.

    from backtesting.research import tradeiq2_ind_session as SH
    d = SH.htf_ema_dir(bars.t, bars.c, h1)                     # sign(close - the script's 1H EMA200), per chart bar
    sig = SH.session_hunter(bars.t, bars.o, bars.h, bars.l, bars.c, vol, 15, d)    # one row per signal

The plan is ``backtest_results/tradeiq_2027/PREREG.md`` (sections 2, 4, 5, 6.6, 7 and claim 10 of section 8); the
specification is section 2 (and 0) of the study's map ``orb_session_swing_ha.md``. Line numbers ("l.") are those of
the plain-text copy of the owner's script (535 lines); the source itself is not in this repository. Port A (this
module, the production port) and port B (``tests/tradeiq2_oracle_session.py``) were written independently from the
source and the specification, then reconciled (``tests/test_tradeiq2_ind_session.py``, the record in
``backtest_results/tradeiq_2027/porting/session.md``): on the real M5 and M15 bars of both symbols, from their data
start to 2024-06-30, the two give the same event tables, the same per-bar series and the same 1H EMA, bit for bit,
for every configuration the plan runs. The contract below is the reconciled one, identical in both ports.

The contract (both ports)
-------------------------
``session_hunter(t, o, h, l, c, v, tf_min, htf_dir, setups=('AS','LS','PD','AB','OR'), conf=('FVG','HTF'),
monday_friday_levels=False, min_stop_atr=0.5)`` -> ``pandas.DataFrame``, one row per signal, in bar order and, on one
bar, in the script's order AS, LS, PD, AB, OR (l.360-364, 412-421).

Inputs: chart bars of ``tf_min`` minutes (5 or 15 in the study; 60 for the information rows; any positive integer is
accepted) with open times ``t`` (UTC epoch seconds, strictly increasing), the bid ``o, h, l, c`` and the volume ``v``
(tick volume, or Binance volume for BTC; read only by the 'RV' confirmation, may be None otherwise). ``htf_dir``: per
chart bar +1 / -1 / 0 (NaN counts as 0), the direction the 'HTF' confirmation compares with; may be None when 'HTF' is
not used. The script's own series is ``htf_ema_dir`` below; F2 / F3 variants pass another direction.

Columns:

* ``setup`` str ('AS', 'LS', 'PD', 'AB', 'OR'); ``bar`` int64 (the signal bar, an index into the inputs);
  ``t_signal`` int64 (its close time, ``t + 60 * tf_min``: the signal is known then); ``dir`` int64 (+1 long, -1 short).
* ``stop`` float64: the absolute stop level after the minimum-stop rule (l.400-402); ``tgt_ref`` float64: the
  "opposite liquidity" level (l.403); ``r_hi``, ``r_lo`` float64: the range the setup used (rH, rL).
* ``entry_bar`` int64: ``bar + 1`` (the script's next-open entry, l.427; it may equal ``len(t)`` for a signal on the
  last bar). ``cancelled``: None, or why the script dropped the trade at its entry bar (l.428-435): 'closeT' (the entry
  bar opens 16:00-20:00 New York), 'new_day' (it starts a new trading day), 'risk<=0' (its open equals the stop),
  'open_beyond_stop' (its open is beyond the stop). When both of a pair hold, the first in the source wins: 'closeT'
  before 'new_day', 'risk<=0' before 'open_beyond_stop' (labels only: the trade is dropped either way).
* For reference, the script's own exits (cost 0, ``cost`` input l.82) in three exit modes m: 'hold' (E1, "Hold to 16:00
  NY", the default), 'tp2' (E2, "At TP2": 2R) and 'liq' (E3, "Opposite liquidity"):
  ``exit_bar_<m>`` int64 (-1 when there is no exit), ``exit_price_<m>`` float64 (NaN when none),
  ``exit_reason_<m>``: 'stop', 'target', 'closeT' (the open of the first bar at or after 16:00, l.456-457),
  'new_day' (the previous bar's close, booked on the new day's first bar, l.454-455), 'cancel_lt_1R' (E3 only: the
  target is less than 1R from the entry open, l.437-439), 'open' (entered and not yet out at the last bar), 'pending'
  (the entry bar is not in the data yet) or None (``cancelled`` is set); ``R_<m>`` float64, the script's R
  ``(d * (x - e) - 2 * cost) / risk`` with cost 0 (l.482), NaN when there is no exit. The entry ``e`` is the bid open
  of the entry bar and ``risk = |e - stop|`` (l.431-432): R is measured from the chart's open, not from a fill.

The signals do not depend on the exit mode (no trade state feeds back into a setup), so the three modes are reported
side by side. The study executes its own rows from ``bar``, ``dir``, ``stop`` and ``tgt_ref`` (PREREG 4: fills at the
next M1 open, the absolute levels re-measured from the fill), applying ``cancelled`` as the script's own cancels at
entry; the reference exits are for the reconciliation and for comparison with the script's on-chart statistics
(cost 0, the bid open). Every scored number, R included (the harness's R, DEVIATIONS 9), comes from the harness.

``htf_ema_dir(t, c_chart, h1_bars, length=200)``: sign(chart close - htfE), where htfE (``htf_ema(t, h1_bars,
length=200, seed='first')``, l.145, ``request.security(syminfo.tickerid, "60", ta.ema(close, 200)[1], lookahead =
barmerge.lookahead_on)``) is the 1H EMA200 of the last 1H bar CLOSED at or before the chart bar's OPEN: with
lookahead_on the call returns the expression's value on the 1H bar containing the chart bar, and ``[1]`` is the bar
before it (PREREG 6.6; the map, 2.2). ``h1_bars``: any object with ``tc`` (close times, UTC s) and ``c`` (closes),
e.g. ``tradeiq_market.TBars``. 0 where the EMA does not exist yet or equals the close.

Also public, for tests and the study's event geometry: ``clock`` (the New York clock and the windows),
``shared_series`` (ATR, the volume SMA, the FVG flags, hi5 / lo5), ``day_state`` (the day and session state per bar),
``fvg``, ``hi5_lo5``, and the constants ``SETUPS``, ``CONFS``, ``MODES``, ``CANCELS``, ``EXIT_REASONS``, ``COLUMNS``,
``WINDOWS``, ``SESSIONS``, ``PRESETS``.

Inputs refused (``ValueError``), in both ports: open times that are not strictly increasing, series of another
length, non-finite prices, an unknown setup or confirmation, a string instead of a sequence of names, a
``tf_min`` that is not a whole number >= 1, a ``min_stop_atr`` that is not a finite number > 0, ``v=None`` with
'RV', ``htf_dir=None`` with 'HTF'. The inputs are never modified.

What the script computes on each bar, in its order
--------------------------------------------------
Clock (l.12, 127-140), New York time with daylight saving ("America/New_York", ``external.local_seconds``):

* ``nyMin`` = hour * 60 + minute of the bar's OPEN (``time``) in New York (l.128).
* ``dk`` = the New York calendar date of ``time + 4h`` (l.129-130), so a trading day runs 20:00 to 20:00 New York and
  the Asia session belongs to the next day; ``weekday`` = that date is Monday to Friday (l.131-132; ``dayofweek`` of
  the same instant); ``newDay = dk != dk[1]`` (l.133).
* ``f_in(s0, s1)`` = the whole bar is inside the window: ``nyMin >= s0 and nyMin + tfMin <= s1`` (l.134). Asia
  20:00-24:00 (l.135), London kill zone 02:00-05:00 (l.136), opening range 09:30-10:00 only when ``tfMin < 60``
  (l.139); ``closeT`` = the bar OPENS in 16:00-20:00 (l.140; not a whole-bar rule).

Shared series (l.143-152): ``atr = ta.atr(14)`` and ``vAvg = ta.sma(volume, 20)`` of the chart bars (study 1's
verified ``tradeiq_ind.atr`` / ``sma``); ``fvgUp = low > high[2] or low[1] > high[3] or low[2] > high[4] or low[3] >
high[5]`` (a fair value gap in any of the last four three-bar groups, filled or not), ``fvgDn`` mirrored;
``hi5 = ta.highest(high, 5)[1]`` = max(high[1..5]) and ``lo5`` = min(low[1..5]) (the current bar excluded).

Day state (l.155-213). On ``newDay``: if the finished day was a weekday (``dWk``) and its high exists, its range goes
into ``ranges`` (the last 10 kept, l.191-194) and ``pdh, pdl, pO, pC`` take its high, low, open and last close
(``close[1]``, l.195-198), else they keep their values; ``pWk := dWk`` (l.199); ``dH, dL, dO`` restart from this bar;
``dWk := weekday``; the midnight open ``mo``, the session levels, the done flags and the five setup states are reset
(l.200-207). Otherwise ``dH, dL`` extend with ``math.max`` / ``math.min`` (na stays na, l.209-210). Then ``adr`` = the
mean of ``ranges`` once it holds 5 (l.211), and ``mo`` = the open of the first bar with ``nyMin < 1200``, i.e. the
first bar from 00:00 New York (l.212-213).

Sessions (l.216-233): Asia, London and the opening range accumulate their high / low over their bars; ``asDone``,
``loDone``, ``oDone`` are set on the first bar after each session (``inX[1] and not inX``).

Setups (l.331-364), each with its own state ``St`` (sH, sL, upEx, dnEx, done, dead), reset every day:

* AS: Asia high / low (once ``asDone``), faded in 02:00-05:00; LS: London high / low (once ``loDone``), faded in
  07:00-11:00; PD: ``pdh / pdl``, only while ``pWk`` (the ternary at l.362 does not even call ``f_rev`` otherwise),
  faded in 02:00-11:00 (one window); AB: the Asia range, followed in 02:00-05:00; OR: the 09:30-10:00 range (once
  ``oDone``, which the 10:00 bar sets before the setup runs), followed in 10:00-12:00, only when ``tfMin < 60``.
* ``f_rev`` (fade, l.331-347): only inside the window, on weekdays, while not done and not dead, with ``rH > rL``. A
  bar with ``high > rH`` sets ``sH`` and raises ``upEx`` (the running max of those highs); ``low < rL`` sets ``sL``
  and lowers ``dnEx``; both swept -> ``dead`` for the day; else a close strictly inside (``rL < close < rH``) signals
  -1 after a high sweep, +1 after a low sweep, if the confirmations pass, and the setup is done. So the sweep and the
  close back inside may be on different bars, a price already beyond the level when the window opens counts as a
  sweep, and a bar that fails the confirmations does not end the setup. The sweep extreme accumulates over the window
  bars only (risk 5 of the map). ``dead`` (l.340-341) only stops the updates: once both flags are set they stay set
  for the day, so the close-inside branch could never be reached again anyway.
* ``f_brk`` (follow, l.350-358): the first close outside the range inside the window that passes the confirmations
  sets done; it signals only if ``|close - (rH + rL) / 2| <= 4 * atr`` (otherwise the day ends without a trade).
* Confirmations (``f_conf``, l.312-328), all those ticked must hold: 'FVG' ``dd > 0 ? fvgUp : fvgDn``; 'MSS'
  ``dd > 0 ? close > hi5 : close < lo5``; 'HTF' ``not na(htfE) and dd * (close - htfE) > 0``, i.e. ``htf_dir == dd``;
  'PD' (premium / discount) ``not na(mo) and dd * (mo - close) > 0``; 'RV' ``volume >= 1.5 * vAvg``; 'TIGHT'
  ``not na(adr) and rH - rL < 50 / 100.0 * adr``; 'YC' ``pWk and dd * (pC - pO) > 0``.
* ``f_new`` (l.399-404): stop = the sweep extreme (``upEx`` for a short, ``dnEx`` for a long) or the range midpoint for
  a breakout; if ``|close - stop| < minStop * atr`` the stop becomes ``close - dd * minStop * atr`` (measured from the
  SIGNAL close, l.401-402); ``tgtRef`` = the opposite side of the range for a fade, the broken side plus one range
  width for a breakout (l.403).

Trade manager (l.424-492), on every later bar, for each pending trade: on the first bar after the signal, cancel on
``closeT or newDay``; ``e = open``, ``risk = |open - stop|``; cancel on ``risk <= 0 or d * (open - stop) <= 0`` (the
open at or beyond the stop: the fill-beyond-stop trap of the map's 0.4 cannot book a fake profit here); the target by
mode (none, ``open + d * 2 * risk``, ``tgtRef``); E3 cancels when ``d * (tgt - open) < risk``. On every live bar,
the entry bar included, the first that applies: a new day after the entry bar -> the previous close; ``closeT`` after
the entry bar -> this bar's open (so the 16:00 bar exits at its open even if it later hits the stop); the stop
touched (``low <= stop`` / ``high >= stop``) -> the stop (a gap through it also fills at the stop: the script's
optimism); the target touched -> the target. A bar that touches both exits at the stop. Trades are independent of one
another (up to five can be open at once, one per setup: the five lanes), so each is scanned forward on its own here.

What is known when (no look-ahead)
----------------------------------
Every output of a row is a function of the bars up to the bar it describes: the signal and its levels of bars
``0 .. bar`` (the session levels are final before their windows open: Asia at 00:00, London at 05:00, the opening
range at 10:00, ``pdh / pdl`` from 20:00); the cancel of bars ``0 .. entry_bar``; an exit of bars ``0 .. exit_bar``
(the new-day exit's price is the close of ``exit_bar - 1``). ``htf_ema_dir`` reads only 1H bars closed by the chart
bar's open (up to an hour old). Removing the bars after T changes nothing up to T but the decisions not yet taken
('pending', 'open'): the tests check it.

Pine readings where the source leaves a choice (the tests pin each one)
-----------------------------------------------------------------------
1. ``newDay`` on the first bar (l.133: ``dk[1]`` is na): false, as study 1 reads a comparison with na. So the first,
   partial day of the data keeps ``dH`` na (``math.max(na, high)`` is na, l.209), is never pushed into ``ranges`` and
   never becomes ``pdh``. The alternative (true) would make the partial first day yesterday's levels. It can move a PD
   signal or a TIGHT / YC test only on the first one or two days of the data: never in a scored window of the study,
   whose bars start years before Development (gold 2016 or 2017, BTC 2018). Port B was written with the alternative
   (na as an IEEE NaN, so ``!=`` is true) and took this reading in the reconciliation: TradingView's reference only
   warns against comparing with na and does not say what the comparison gives, and study 1 and the other study-2
   ports read every comparison with na as false. On the study's own bars the two readings give identical outputs
   (``tests/test_tradeiq2_ind_session.py``): both symbols' data start on a weekend pseudo-day (gold's first bar opens
   on Sunday 2016-01-03 18:00 New York, BTC's on Sunday 2017-12-31 19:00 New York), which is not a weekday and so
   never becomes yesterday's levels under either reading.
2. ``ta.highest(high, 5)`` / ``ta.lowest(low, 5)`` (l.148, 152) are na until 5 bars exist, so ``hi5`` / ``lo5`` are na
   on bars 0-4 (MSS fails there). The alternative (the extreme of the bars so far) differs only on bars 0-4.
3. ``ranges.avg()`` (l.211) is the sum in array order (oldest first) divided by the size. A pairwise sum could differ
   by one ulp, which can flip TIGHT only at an exact tie.
4. The HTF value is the 1H EMA of the last 1H bar closed at or before the chart bar's open (PREREG 6.6), not that of
   the last 1H bar closed at the chart bar's close (``tradeiq_market.htf_at``); the two differ on the last chart bar
   of each hour, where a signal's HTF test can differ. ``ta.ema`` is seeded with its first value (study 1, PREREG 5);
   an SMA seed differs by (199/201)^n after n 1H bars, nothing after the warm-up (measured: htfE is bit-identical
   under both seeds from 2019 on both symbols; on USTECm, with 484 1H bars before its Development start, within
   1.7e-4 of the price, and no sign differs).
5. ``monday_friday_levels=True`` (the logged variant, information only): ``pWk`` is replaced by "the last weekday's
   levels exist" (``not na(pdh)``) in the PD setup and in the YC confirmation. It gives Monday Friday's high, low, open
   and close, and likewise a weekday that follows a weekday without bars (a holiday). A Monday-only variant would
   differ on those days only.
6. The cancel labels when both of a pair hold (l.428, 433): the first in the source. Labels only.
7. The new-day exit (l.454-455) is reported on the new day's first bar (``exit_bar``) at the close of the bar before.
8. The 1H history of the EMA200 (l.145): every 1H bar the caller passes. The study passes the 1H bars of its own
   market from the data start (gold 2016-01, BTC 2018-01), so htfE has two to three years of warm-up before 2019. A
   TradingView chart computes it on the 1H history it loads, which may start near the chart's first bar. Measured in
   the reconciliation: 1H bars cut at 2019-01-02 change the 'HTF' sign on 536 / 182 gold bars (M5 / M15, the last on
   2019-02-26) and 539 / 183 BTC bars (the last on 2019-01-06), and 10 / 10 (gold) and 6 / 5 (BTC) K2 signals of
   2019-2022, all before 2019-01-24 (``backtest_results/tradeiq_2027/porting/session.md``, section 8).

Arithmetic follows the source's order so that the two ports agree bit for bit: ``stop = close - (dd * minStop) *
atr``, ``tgtRef = side + dd * (rH - rL)``, ``mid = (rH + rL) / 2``, ``tgt = open + (d * 2.0) * risk``, ``R = (d * (x
- e) - 2 * 0.0) / risk``, ``adr`` a sequential mean; ATR and the volume SMA are ``tradeiq_ind.atr`` / ``sma``; the 1H
EMA is ``tradeiq_ind.ema``.

Implementation: the clock and the shared series in numpy, the per-bar state machine (``_kernel``) and the trade
manager (``_manage``) in numba. A BTC M5 chart of 2019 to mid-2024 (about 580,000 bars) takes well under a second
after the first compilation.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit

from . import external as X
from . import tradeiq_ind as I

__all__ = [
    "NY", "SETUPS", "CONFS", "MODES", "CANCELS", "EXIT_REASONS", "PRESETS", "COLUMNS",
    "WINDOWS", "SESSIONS", "clock", "fvg", "hi5_lo5", "shared_series", "htf_ema", "htf_ema_dir", "day_state",
    "session_hunter",
]

NY = X.NY                                   # "America/New_York" (l.12)
DAY = 86400
SETUPS = ("AS", "LS", "PD", "AB", "OR")     # the script's order (l.360-364)
CONFS = ("FVG", "MSS", "HTF", "PD", "RV", "TIGHT", "YC")     # f_conf's order (l.314-327)
MODES = ("hold", "tp2", "liq")              # E1 "Hold to 16:00 NY", E2 "At TP2", E3 "Opposite liquidity" (l.80)
CANCELS = ("closeT", "new_day", "open_beyond_stop", "risk<=0")
EXIT_REASONS = ("stop", "target", "closeT", "new_day", "open", "cancel_lt_1R", "pending")
# the trading windows of the setups and the sessions, New York minutes [s0, s1) (l.135-140, 360-364)
WINDOWS = {"AS": (120, 300), "LS": (420, 660), "PD": (120, 660), "AB": (120, 300), "OR": (600, 720)}
SESSIONS = {"asia": (1200, 1440), "london": (120, 300), "or": (570, 600), "closeT": (960, 1200)}
# the script's presets (l.93-112): setups, confirmations; all three hold to 16:00 (E1)
PRESETS = {
    "custom": (("AS", "LS"), ("FVG", "HTF")),          # the inputs' defaults (l.50-67)
    "forex": (("AS",), ("FVG", "MSS")),
    "nasdaq": (("LS", "PD"), ("FVG", "HTF")),
}
TP2_R = 2.0                                 # tp2 input (l.78)
RV_K = 1.5                                  # rvK input (l.64)
ADR_PCT = 50                                # adrPct input (l.66): rH - rL < adrPct / 100.0 * adr
ATR_LEN = 14                                # ta.atr(14) (l.143)
VOL_LEN = 20                                # ta.sma(volume, 20) (l.144)

_CANCEL_NAMES = {1: "closeT", 2: "new_day", 3: "open_beyond_stop", 4: "risk<=0"}
_WHY_NAMES = {0: None, 1: "stop", 2: "target", 3: "closeT", 4: "new_day", 5: "open", 6: "cancel_lt_1R", 7: "pending"}

COLUMNS = (["setup", "bar", "t_signal", "dir", "stop", "tgt_ref", "r_hi", "r_lo", "entry_bar", "cancelled"]
           + [f"{k}_{m}" for m in MODES for k in ("exit_bar", "exit_price", "exit_reason", "R")])


# ───────────────────────────── inputs ─────────────────────────────

def _f64(x, n: int, name: str) -> np.ndarray:
    a = np.array(x, dtype=np.float64)            # a copy: the caller's array is never modified
    if a.shape != (n,):
        raise ValueError(f"{name}: {a.shape} values against {n} bars")
    return a


def _times(t) -> np.ndarray:
    a = np.array(t, dtype=np.int64)
    if a.ndim != 1:
        raise ValueError("t: a 1-D series of open times (UTC s) is expected")
    if len(a) > 1 and not bool(np.all(np.diff(a) > 0)):
        raise ValueError("t: open times must increase strictly")
    return a


def _tf(tf_min) -> int:
    if isinstance(tf_min, (bool, np.bool_)) or float(tf_min) != int(tf_min) or int(tf_min) < 1:
        raise ValueError(f"tf_min: a whole number of minutes >= 1 is expected, got {tf_min!r}")
    return int(tf_min)


def _names(x, allowed: Sequence[str], what: str) -> Tuple[str, ...]:
    if isinstance(x, str):
        raise ValueError(f"{what}: a sequence of names is expected, got the string {x!r}")
    out = tuple(x)
    bad = [s for s in out if s not in allowed]
    if bad:
        raise ValueError(f"{what}: unknown {bad}; known: {', '.join(allowed)}")
    return out


def _direction(x, n: int) -> np.ndarray:
    """+1 / -1 / 0 per bar from any numeric direction series (NaN and 0 count as 0)."""
    a = _f64(x, n, "htf_dir")
    with np.errstate(invalid="ignore"):
        return np.where(a > 0, 1, np.where(a < 0, -1, 0)).astype(np.int64)


# ───────────────────────────── clock and shared series ─────────────────────────────

def clock(t, tf_min: int) -> Dict[str, np.ndarray]:
    """
    The script's New York clock of bars opening at ``t`` (UTC s), l.127-140:

    * ``ny_min`` int64: ``hour(time, TZ) * 60 + minute(time, TZ)`` of the bar's OPEN;
    * ``day_key`` int64: the New York date of ``time + 4h`` (an epoch day number; l.129-130) and ``weekday`` bool: that
      date is Monday-Friday (l.131-132, Pine's ``dayofweek`` of the same instant);
    * ``new_day`` bool: ``dk != dk[1]``, false on the first bar (reading 1 of the module docstring);
    * ``in_asia``, ``in_lon``, ``in_or`` bool: the whole bar inside 20:00-24:00, 02:00-05:00, 09:30-10:00 (the last only
      when ``tf_min < 60``); ``close_t`` bool: the bar opens in 16:00-20:00 (l.140);
    * ``win_<setup>`` bool: the whole bar inside the setup's window (``WINDOWS``; OR only when ``tf_min < 60``).
    """
    tt = _times(t)
    tf = _tf(tf_min)
    loc = X.local_seconds(tt, NY)
    ny_min = (loc % DAY) // 60
    dk = X.local_seconds(tt + 4 * 3600, NY) // DAY
    weekday = ((dk + 3) % 7) < 5                    # epoch day 0 (1970-01-01) was a Thursday: (d + 3) % 7, 0 = Monday
    new_day = np.zeros(len(tt), np.bool_)
    new_day[1:] = dk[1:] != dk[:-1]

    def f_in(s0, s1):                               # l.134 (its ``nyMin < 1440`` always holds)
        return (ny_min >= s0) & (ny_min + tf <= s1)

    out = {"ny_min": ny_min.astype(np.int64), "day_key": dk.astype(np.int64), "weekday": weekday,
           "new_day": new_day, "in_asia": f_in(*SESSIONS["asia"]), "in_lon": f_in(*SESSIONS["london"]),
           "in_or": f_in(*SESSIONS["or"]) & (tf < 60),
           "close_t": (ny_min >= SESSIONS["closeT"][0]) & (ny_min < SESSIONS["closeT"][1])}
    for s, (a, z) in WINDOWS.items():
        out[f"win_{s}"] = f_in(a, z) & (tf < 60 if s == "OR" else True)
    return out


def fvg(h, l) -> Tuple[np.ndarray, np.ndarray]:
    """``fvgUp`` / ``fvgDn`` (l.146-147): a gap between bars k and k - 2 for any k of the last four (offsets 0-3);
    whether it was filled is never checked. A comparison with na (the first bars) is false."""
    hh = np.asarray(h, np.float64)
    ll = np.asarray(l, np.float64)
    up = np.zeros(len(hh), np.bool_)
    dn = np.zeros(len(hh), np.bool_)
    with np.errstate(invalid="ignore"):
        for k in range(4):
            lk, hk = I.hist(ll, k), I.hist(hh, k)
            h2, l2 = I.hist(hh, k + 2), I.hist(ll, k + 2)
            up |= lk > h2                           # low[k] > high[k + 2]
            dn |= hk < l2                           # high[k] < low[k + 2]
    return up, dn


def hi5_lo5(h, l, length: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """``ta.highest(high, 5)[1]`` / ``ta.lowest(low, 5)[1]`` (l.148, 152): the extreme of the 5 bars BEFORE this one,
    na on bars 0-4 (reading 2: ``ta.highest`` is na until 5 bars exist)."""
    hh = np.asarray(h, np.float64)
    ll = np.asarray(l, np.float64)
    n = len(hh)
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    if n > length:
        w = np.lib.stride_tricks.sliding_window_view
        hi[length:] = w(hh, length).max(axis=1)[:-1]
        lo[length:] = w(ll, length).min(axis=1)[:-1]
    return hi, lo


def shared_series(h, l, c, v=None) -> Dict[str, np.ndarray]:
    """
    The chart's shared series (l.143-152) exactly as the setups read them: ``atr`` = ``ta.atr(14)`` (study 1's verified
    ``tradeiq_ind.atr``: Wilder's RMA seeded with the SMA of the first 14 true ranges, the true range of bar 0 being
    high - low), ``vavg`` = ``ta.sma(volume, 20)`` (``tradeiq_ind.sma``, ``pine_sma``'s order; NaN when ``v`` is None),
    ``fvg_up`` / ``fvg_dn`` (``fvg``) and ``hi5`` / ``lo5`` (``hi5_lo5``). Each value of bar i uses bars 0..i only.
    """
    hh = np.asarray(h, np.float64)
    ll = np.asarray(l, np.float64)
    cc = np.asarray(c, np.float64)
    n = len(cc)
    fup, fdn = fvg(hh, ll)
    hi5, lo5 = hi5_lo5(hh, ll)
    return {"atr": I.atr(hh, ll, cc, ATR_LEN) if n else np.zeros(0),
            "vavg": np.full(n, np.nan) if v is None else (I.sma(np.asarray(v, np.float64), VOL_LEN) if n
                                                          else np.zeros(0)),
            "fvg_up": fup, "fvg_dn": fdn, "hi5": hi5, "lo5": lo5}


def _h1(h1_bars) -> Tuple[np.ndarray, np.ndarray]:
    tc = np.asarray(h1_bars.tc, np.int64)
    c1 = np.asarray(h1_bars.c, np.float64)
    if tc.shape != c1.shape or tc.ndim != 1:
        raise ValueError("h1_bars: tc and c of equal length are expected")
    if len(tc) > 1 and not bool(np.all(np.diff(tc) > 0)):
        raise ValueError("h1_bars: close times must increase strictly")
    return tc, c1


def htf_ema(t, h1_bars, length: int = 200, seed: str = "first") -> np.ndarray:
    """
    htfE per chart bar (l.145): ``request.security(syminfo.tickerid, "60", ta.ema(close, 200)[1], lookahead =
    barmerge.lookahead_on)``. With ``lookahead_on`` a historical chart bar gets the expression's value on the 1H bar
    that contains its open, and ``[1]`` is the 1H bar before that one: the EMA200 of the 1H closes as of the last 1H
    bar CLOSED AT OR BEFORE THE CHART BAR'S OPEN (``external.value_at(h1.tc, ema, t)``, i.e. ``tc <= t``). NaN before
    the first such bar. ``ta.ema`` is ``tradeiq_ind.ema``: seeded with its first close (``seed="first"``, study 1's
    reading and TradingView's ``pine_ema``); ``seed="sma"`` (na for 199 bars, then the SMA of the first 200) exists
    only to measure that the seed changes nothing once the 1H history is long (the study's starts in 2016 / 2018).
    ``h1_bars``: any object with ``tc`` (close times, UTC s, strictly increasing) and ``c`` (closes), e.g. study 1's
    ``TBars``; the bars' close times are their nominal ends (``open + 3600``), so the bar before the one containing
    the chart bar is exactly the last one with ``tc <= t``.
    """
    tt = _times(t)
    tc, c1 = _h1(h1_bars)
    if len(tc) == 0:
        return np.full(len(tt), np.nan)
    return X.value_at(tc, I.ema(c1, length, seed=seed), tt, np.nan).astype(np.float64)


def htf_ema_dir(t, c_chart, h1_bars, length: int = 200) -> np.ndarray:
    """
    The script's 1H trend per chart bar (l.145, used at l.319): +1 where the chart close is above htfE (``htf_ema``),
    -1 below, 0 where htfE is na or equal to the close. So ``htf_dir == dir`` is exactly l.319's ``not na(htfE) and
    dd * (close - htfE) > 0``. On an M15 chart the 10:45 bar reads the EMA as of 10:00 (the 09:00 bar's), the 11:00
    bar the EMA as of 11:00. ``h1_bars``: ``tc`` and ``c`` of the 1H bars (UTC s). int8.
    """
    tt = _times(t)
    cc = _f64(c_chart, len(tt), "c_chart")
    htf = htf_ema(tt, h1_bars, length)
    with np.errstate(invalid="ignore"):
        d = np.where(cc > htf, 1, np.where(cc < htf, -1, 0))
    return d.astype(np.int8)


# ───────────────────────────── the per-bar state machine (numba) ─────────────────────────────

@njit(cache=True)
def _conf(dd, i, rh, rl, c, v, vavg, hdir, fup, fdn, hi5, lo5, mo, adr, pwk, pc, po, cf, rv_k, adr_frac):
    """``f_conf(dd, rH, rL)`` (l.312-328) on bar i: every switched-on confirmation (cf, in CONFS order) must hold.
    A comparison with na is false."""
    ok = True
    if cf[0]:
        ok = ok and (fup[i] if dd > 0 else fdn[i])
    if cf[1]:
        ok = ok and ((c[i] > hi5[i]) if dd > 0 else (c[i] < lo5[i]))
    if cf[2]:
        ok = ok and hdir[i] == dd
    if cf[3]:
        ok = ok and mo == mo and dd * (mo - c[i]) > 0
    if cf[4]:
        ok = ok and v[i] >= rv_k * vavg[i]
    if cf[5]:
        ok = ok and adr == adr and rh - rl < adr_frac * adr
    if cf[6]:
        ok = ok and pwk and dd * (pc - po) > 0
    return ok


@njit(cache=True)
def _kernel(o, h, l, c, v, vavg, atr, nymin, dk, wk, hdir, fup, fdn, hi5, lo5, tf, en, cf, mfl,
            min_stop, rv_k, adr_frac, cap, rec):
    """
    l.155-421 bar by bar: the day state, the sessions, the five setups and ``f_new``. Returns the signals (setup code
    0-4 in SETUPS order, bar, dir, stop, tgtRef, rH, rL; the first ``k`` rows) and, when ``rec``, the per-bar state
    after the session updates (for ``day_state``).
    """
    n = c.shape[0]
    nan = np.nan
    s_set = np.empty(cap, np.int64)
    s_bar = np.empty(cap, np.int64)
    s_dir = np.empty(cap, np.int64)
    s_stop = np.empty(cap)
    s_tref = np.empty(cap)
    s_rh = np.empty(cap)
    s_rl = np.empty(cap)
    m_rec = n if rec else 1
    r_f = np.full((m_rec, 12), nan)              # pdh pdl pO pC mo asH asL loH loL oH oL adr
    r_b = np.zeros((m_rec, 5), np.bool_)         # pWk asDone loDone oDone dWk
    k = 0
    d_h = nan
    d_l = nan
    d_o = nan
    pdh = nan
    pdl = nan
    p_o = nan
    p_c = nan
    p_wk = False
    mo = nan
    as_h = nan
    as_l = nan
    lo_h = nan
    lo_l = nan
    or_h = nan
    or_l = nan
    as_done = False
    lo_done = False
    or_done = False
    rng = np.empty(10)
    nr = 0
    d_wk = False
    s_h = np.zeros(5, np.bool_)
    s_l = np.zeros(5, np.bool_)
    up_ex = np.full(5, nan)
    dn_ex = np.full(5, nan)
    done = np.zeros(5, np.bool_)
    dead = np.zeros(5, np.bool_)
    prev_asia = False                            # inAsia[1] etc.: false on the first bar
    prev_lon = False
    prev_or = False
    for i in range(n):
        # l.190-210: the day state
        if i > 0 and dk[i] != dk[i - 1]:
            if d_h == d_h and d_wk:
                if nr == 10:                     # push, then shift the oldest out (l.192-194)
                    for q in range(9):
                        rng[q] = rng[q + 1]
                    rng[9] = d_h - d_l
                else:
                    rng[nr] = d_h - d_l
                    nr += 1
            if d_wk:
                pdh = d_h
                pdl = d_l
                p_o = d_o
                p_c = c[i - 1]
            p_wk = d_wk
            d_h = h[i]
            d_l = l[i]
            d_o = o[i]
            d_wk = wk[i]
            mo = nan
            as_h = nan
            as_l = nan
            lo_h = nan
            lo_l = nan
            or_h = nan
            or_l = nan
            as_done = False
            lo_done = False
            or_done = False
            for s in range(5):
                s_h[s] = False
                s_l[s] = False
                up_ex[s] = nan
                dn_ex[s] = nan
                done[s] = False
                dead[s] = False
        else:
            if d_h == d_h:                       # math.max(na, high) is na
                d_h = max(d_h, h[i])
            if d_l == d_l:
                d_l = min(d_l, l[i])
        # l.211: the 10-day average range
        if nr >= 5:
            acc = 0.0
            for q in range(nr):
                acc += rng[q]
            adr = acc / nr
        else:
            adr = nan
        m = nymin[i]
        # l.212-213: the midnight open
        if mo != mo and m < 1200:
            mo = o[i]
        # l.216-233: the sessions
        in_asia = m >= 1200 and m + tf <= 1440
        in_lon = m >= 120 and m + tf <= 300
        in_or = m >= 570 and m + tf <= 600 and tf < 60
        if in_asia:
            as_h = h[i] if as_h != as_h else max(as_h, h[i])
            as_l = l[i] if as_l != as_l else min(as_l, l[i])
        if in_lon:
            lo_h = h[i] if lo_h != lo_h else max(lo_h, h[i])
            lo_l = l[i] if lo_l != lo_l else min(lo_l, l[i])
        if in_or:
            or_h = h[i] if or_h != or_h else max(or_h, h[i])
            or_l = l[i] if or_l != or_l else min(or_l, l[i])
        if prev_asia and not in_asia:
            as_done = True
        if prev_lon and not in_lon:
            lo_done = True
        if prev_or and not in_or:
            or_done = True
        prev_asia = in_asia
        prev_lon = in_lon
        prev_or = in_or
        pwk = p_wk or (mfl and pdh == pdh)       # the Monday quirk (l.199, 327, 362), or its logged variant
        if rec:
            r_f[i, 0] = pdh
            r_f[i, 1] = pdl
            r_f[i, 2] = p_o
            r_f[i, 3] = p_c
            r_f[i, 4] = mo
            r_f[i, 5] = as_h
            r_f[i, 6] = as_l
            r_f[i, 7] = lo_h
            r_f[i, 8] = lo_l
            r_f[i, 9] = or_h
            r_f[i, 10] = or_l
            r_f[i, 11] = adr
            r_b[i, 0] = pwk
            r_b[i, 1] = as_done
            r_b[i, 2] = lo_done
            r_b[i, 3] = or_done
            r_b[i, 4] = d_wk
        # l.360-364 and 412-421: the five setups in the script's order, each followed by its f_new
        w_as = m >= 120 and m + tf <= 300
        w_ls = m >= 420 and m + tf <= 660
        w_pd = m >= 120 and m + tf <= 660
        w_or = m >= 600 and m + tf <= 720
        for s in range(5):
            if not en[s]:
                continue
            if s == 0:
                rh = as_h if as_done else nan
                rl = as_l
                win = w_as
                rev = True
                fh = as_h
                fl = as_l
            elif s == 1:
                rh = lo_h if lo_done else nan
                rl = lo_l
                win = w_ls
                rev = True
                fh = lo_h
                fl = lo_l
            elif s == 2:
                if not pwk:                      # ``ePD and pWk ? f_rev(...) : 0``: not even called
                    continue
                rh = pdh
                rl = pdl
                win = w_pd
                rev = True
                fh = pdh
                fl = pdl
            elif s == 3:
                rh = as_h if as_done else nan
                rl = as_l
                win = w_as
                rev = False
                fh = as_h
                fl = as_l
            else:
                if not tf < 60:
                    continue
                rh = or_h if or_done else nan
                rl = or_l
                win = w_or
                rev = False
                fh = or_h
                fl = or_l
            sig = 0
            if rev:                              # f_rev (l.331-347)
                if win and wk[i] and not done[s] and not dead[s] and rh == rh and rl == rl and rh > rl:
                    if h[i] > rh:
                        s_h[s] = True
                        up_ex[s] = h[i] if up_ex[s] != up_ex[s] else max(up_ex[s], h[i])
                    if l[i] < rl:
                        s_l[s] = True
                        dn_ex[s] = l[i] if dn_ex[s] != dn_ex[s] else min(dn_ex[s], l[i])
                    if s_h[s] and s_l[s]:
                        dead[s] = True
                    elif c[i] < rh and c[i] > rl:
                        dd = -1 if s_h[s] else (1 if s_l[s] else 0)
                        if dd != 0 and _conf(dd, i, rh, rl, c, v, vavg, hdir, fup, fdn, hi5, lo5, mo, adr, pwk,
                                             p_c, p_o, cf, rv_k, adr_frac):
                            sig = dd
                            done[s] = True
            else:                                # f_brk (l.350-358)
                if win and wk[i] and not done[s] and rh == rh and rl == rl and rh > rl:
                    dd = 1 if c[i] > rh else (-1 if c[i] < rl else 0)
                    if dd != 0 and _conf(dd, i, rh, rl, c, v, vavg, hdir, fup, fdn, hi5, lo5, mo, adr, pwk,
                                         p_c, p_o, cf, rv_k, adr_frac):
                        done[s] = True
                        if abs(c[i] - (rh + rl) / 2) <= 4 * atr[i]:
                            sig = dd
            if sig != 0:                         # f_new (l.399-404)
                if rev:
                    stop = up_ex[s] if sig < 0 else dn_ex[s]
                else:
                    stop = (fh + fl) / 2
                if abs(c[i] - stop) < min_stop * atr[i]:
                    stop = c[i] - (sig * min_stop) * atr[i]
                if rev:
                    ref = fl if sig < 0 else fh
                else:
                    ref = (fh if sig > 0 else fl) + sig * (fh - fl)
                s_set[k] = s
                s_bar[k] = i
                s_dir[k] = sig
                s_stop[k] = stop
                s_tref[k] = ref
                s_rh[k] = fh
                s_rl[k] = fl
                k += 1
    return k, s_set, s_bar, s_dir, s_stop, s_tref, s_rh, s_rl, r_f, r_b


@njit(cache=True)
def _manage(o, h, l, c, close_t, new_day, s_bar, s_dir, s_stop, s_tref, tp2):
    """
    The trade manager (l.424-492) for each signal, scanned forward from its entry bar. Returns the cancel code (0 none,
    1 closeT, 2 new_day, 3 open_beyond_stop, 4 risk<=0, 9 pending), and per mode (hold, tp2, liq) the exit bar (-1),
    price (NaN), reason code (_WHY_NAMES) and R (NaN).
    """
    m = s_bar.shape[0]
    n = c.shape[0]
    canc = np.zeros(m, np.int64)
    xbar = np.full((m, 3), -1, np.int64)
    xpx = np.full((m, 3), np.nan)
    why = np.zeros((m, 3), np.int64)
    rr = np.full((m, 3), np.nan)
    for k in range(m):
        e = s_bar[k] + 1
        if e >= n:
            canc[k] = 9
            for md in range(3):
                why[k, md] = 7
            continue
        if close_t[e] or new_day[e]:             # l.428-430
            canc[k] = 1 if close_t[e] else 2
            continue
        ep = o[e]                                # l.431-432
        d = s_dir[k]
        stop = s_stop[k]
        risk = abs(ep - stop)
        if risk <= 0:                            # l.433-435
            canc[k] = 4
            continue
        if d * (ep - stop) <= 0:
            canc[k] = 3
            continue
        for md in range(3):
            if md == 0:                          # l.436
                tgt = np.nan
            elif md == 1:
                tgt = ep + (d * tp2) * risk
            else:
                tgt = s_tref[k]
                if d * (tgt - ep) < risk:        # l.437-439
                    why[k, md] = 6
                    continue
            out = False
            for j in range(e, n):                # l.452-461, the entry bar included
                r = 0
                x = np.nan
                if new_day[j] and j > e:
                    x = c[j - 1]
                    r = 4
                elif close_t[j] and j > e:
                    x = o[j]
                    r = 3
                elif (l[j] <= stop) if d > 0 else (h[j] >= stop):
                    x = stop
                    r = 1
                elif tgt == tgt and ((h[j] >= tgt) if d > 0 else (l[j] <= tgt)):
                    x = tgt
                    r = 2
                if r != 0:
                    xbar[k, md] = j
                    xpx[k, md] = x
                    why[k, md] = r
                    rr[k, md] = (d * (x - ep) - 2 * 0.0) / risk      # l.482 with cost 0
                    out = True
                    break
            if not out:
                why[k, md] = 5
    return canc, xbar, xpx, why, rr


# ───────────────────────────── the public functions ─────────────────────────────

def _prepare(t, o, h, l, c, v, tf_min, htf_dir, conf, need_volume):
    tt = _times(t)
    n = len(tt)
    oo, hh, ll, cc = (_f64(x, n, nm) for x, nm in ((o, "o"), (h, "h"), (l, "l"), (c, "c")))
    if n and not (np.isfinite(oo).all() and np.isfinite(hh).all() and np.isfinite(ll).all() and np.isfinite(cc).all()):
        raise ValueError("o, h, l, c: finite prices are expected")
    tf = _tf(tf_min)
    ck = clock(tt, tf)
    if need_volume:
        if v is None:
            raise ValueError("v: the 'RV' confirmation reads the volume")
        vv = _f64(v, n, "v")
    else:
        vv = np.zeros(n) if v is None else _f64(v, n, "v")
    if "HTF" in conf:
        if htf_dir is None:
            raise ValueError("htf_dir: the 'HTF' confirmation needs a direction per bar (htf_ema_dir)")
        hd = _direction(htf_dir, n)
    else:
        hd = np.zeros(n, np.int64) if htf_dir is None else _direction(htf_dir, n)
    sh = shared_series(hh, ll, cc, vv if need_volume else None)     # the volume SMA only where 'RV' reads it
    return (tt, n, oo, hh, ll, cc, vv, sh["vavg"], hd, sh["atr"], sh["fvg_up"], sh["fvg_dn"], sh["hi5"], sh["lo5"],
            tf, ck)


def _run_kernel(prep, setups, conf, monday_friday_levels, min_stop_atr, rec):
    tt, n, oo, hh, ll, cc, vv, vavg, hd, atr, fup, fdn, hi5, lo5, tf, ck = prep
    en = np.array([s in setups for s in SETUPS], np.bool_)
    cf = np.array([k in conf for k in CONFS], np.bool_)
    cap = 5 * (int(np.count_nonzero(ck["new_day"])) + 1)       # at most one signal per setup and trading day
    ms = float(min_stop_atr)
    if not (ms > 0.0 and math.isfinite(ms)):                   # the input's minval is 0.1 (l.81)
        raise ValueError(f"min_stop_atr: a number > 0 is expected, got {min_stop_atr!r}")
    return _kernel(oo, hh, ll, cc, vv, vavg, atr, ck["ny_min"], ck["day_key"], ck["weekday"], hd, fup, fdn, hi5,
                   lo5, tf, en, cf, bool(monday_friday_levels), ms, RV_K, ADR_PCT / 100.0, cap, rec)


def day_state(t, o, h, l, c, tf_min, monday_friday_levels: bool = False) -> pd.DataFrame:
    """
    The script's day and session state per bar (after l.233, as the setups read it): ``pdh``, ``pdl``, ``p_open``,
    ``p_close`` (yesterday's levels), ``p_wk`` (``pWk``, or its variant), ``mo`` (midnight open), ``asia_hi/lo``,
    ``lon_hi/lo``, ``or_hi/lo`` with ``asia_done``, ``lon_done``, ``or_done``, ``adr``, ``d_wk`` (this day is a
    weekday), and the clock (``ny_min``, ``day_key``, ``weekday``, ``new_day``). For tests and for the study's event
    geometry; the setups are not run.
    """
    prep = _prepare(t, o, h, l, c, None, tf_min, None, (), False)
    out = _run_kernel(prep, (), (), monday_friday_levels, 0.5, True)
    r_f, r_b = out[8], out[9]
    ck = prep[-1]
    d = {"ny_min": ck["ny_min"], "day_key": ck["day_key"], "weekday": ck["weekday"], "new_day": ck["new_day"]}
    for j, name in enumerate(("pdh", "pdl", "p_open", "p_close", "mo", "asia_hi", "asia_lo", "lon_hi", "lon_lo",
                              "or_hi", "or_lo", "adr")):
        d[name] = r_f[:, j]
    for j, name in enumerate(("p_wk", "asia_done", "lon_done", "or_done", "d_wk")):
        d[name] = r_b[:, j]
    return pd.DataFrame(d)


def _empty() -> pd.DataFrame:
    cols = {"setup": pd.Series([], dtype=object), "bar": pd.Series([], dtype=np.int64),
            "t_signal": pd.Series([], dtype=np.int64), "dir": pd.Series([], dtype=np.int64)}
    for k in ("stop", "tgt_ref", "r_hi", "r_lo"):
        cols[k] = pd.Series([], dtype=np.float64)
    cols["entry_bar"] = pd.Series([], dtype=np.int64)
    cols["cancelled"] = pd.Series([], dtype=object)
    for m in MODES:
        cols[f"exit_bar_{m}"] = pd.Series([], dtype=np.int64)
        cols[f"exit_price_{m}"] = pd.Series([], dtype=np.float64)
        cols[f"exit_reason_{m}"] = pd.Series([], dtype=object)
        cols[f"R_{m}"] = pd.Series([], dtype=np.float64)
    return pd.DataFrame(cols)[COLUMNS]


def session_hunter(t, o, h, l, c, v, tf_min, htf_dir, setups=SETUPS, conf=("FVG", "HTF"),
                   monday_friday_levels: bool = False, min_stop_atr: float = 0.5) -> pd.DataFrame:
    """
    Session Hunter's signals and its own trade decisions on chart bars of ``tf_min`` minutes (see the module
    docstring for the contract, the columns and the Pine readings). ``setups``: the setups switched on (each is its
    own lane: switching one off changes nothing in the others); ``conf``: the confirmations that must all hold (K0
    ``()``, K1 ``('FVG',)``, K2 ``('FVG', 'HTF')`` = the script's default, K3 ``('FVG', 'MSS')`` = its Forex preset);
    ``monday_friday_levels``: the logged variant of the Monday quirk; ``min_stop_atr``: ``minStop`` (l.81).
    """
    st = _names(setups, SETUPS, "setups")
    cs = _names(conf, CONFS, "conf")
    prep = _prepare(t, o, h, l, c, v, tf_min, htf_dir, cs, "RV" in cs)
    tt, n, oo, hh, ll, cc = prep[:6]
    tf = prep[14]
    ck = prep[15]
    k, s_set, s_bar, s_dir, s_stop, s_tref, s_rh, s_rl, _, _ = _run_kernel(prep, st, cs, monday_friday_levels,
                                                                            min_stop_atr, False)
    if k == 0:
        return _empty()
    s_set, s_bar, s_dir = s_set[:k], s_bar[:k], s_dir[:k]
    s_stop, s_tref, s_rh, s_rl = s_stop[:k], s_tref[:k], s_rh[:k], s_rl[:k]
    canc, xbar, xpx, why, rr = _manage(oo, hh, ll, cc, ck["close_t"], ck["new_day"], s_bar, s_dir, s_stop, s_tref,
                                       TP2_R)
    out = {"setup": np.array([SETUPS[int(s)] for s in s_set], dtype=object),
           "bar": s_bar.astype(np.int64),
           "t_signal": tt[s_bar] + 60 * tf,
           "dir": s_dir.astype(np.int64),
           "stop": s_stop, "tgt_ref": s_tref, "r_hi": s_rh, "r_lo": s_rl,
           "entry_bar": s_bar + 1,
           "cancelled": np.array([_CANCEL_NAMES.get(int(x)) for x in canc], dtype=object)}
    for j, mname in enumerate(MODES):
        out[f"exit_bar_{mname}"] = xbar[:, j].copy()
        out[f"exit_price_{mname}"] = xpx[:, j].copy()
        out[f"exit_reason_{mname}"] = np.array([_WHY_NAMES[int(x)] for x in why[:, j]], dtype=object)
        out[f"R_{mname}"] = rr[:, j].copy()
    return pd.DataFrame(out)[COLUMNS]
