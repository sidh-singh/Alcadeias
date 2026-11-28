"""
Tests of PORT B (the oracle) of Session Hunter [TradeIQ], ``tests/tradeiq2_oracle_session.py`` (study 2,
``backtest_results/tradeiq_2027/PREREG.md`` section 6.6).

1. One hand-computed test per trap of the spec's "Porting effort, risks and tests" section (``test_trapNN_*``, in the
   spec's order), then its numbered tests that a trap test does not already cover (``test_specNN_*``), then the
   readings R1-R9 of the module docstring that can be pinned on synthetic bars.
2. The confirmations, the contract (columns, dtypes, refused inputs) and the Pine primitives against study 1's
   independent oracle (``tests/tradeiq_oracle.py``, read-only), and the New York clock against ``zoneinfo``.
3. Truncation invariance: everything decided up to bar T is unchanged when the bars after T are removed.
4. The real bars of both symbols, M5 and M15 (the timeframes of PREREG 6.6), to 2024-06-30: the oracle runs and every
   value the contract says exists exists. The exit columns are only checked for existence and geometry (an exit after
   the entry, a stop exit at the stop, a 16:00 exit at the bar's open, ...) and, in the truncation check, for equality
   with themselves; they are never printed, summed or otherwise looked at (PREREG: no profit or loss on real data).

Synthetic bars are built by New York wall-clock time with ``zoneinfo`` (independent of the module's clock). A "quiet"
bar is o = c = 100, h = 100.5, l = 99.5 (a true range of 1, so ATR(14) settles at 0.9999999999999997).
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from backtesting.data import store
from backtesting.research import external as X
from backtesting.research import tradeiq_market as TM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tradeiq2_oracle_session as O  # noqa: E402
import tradeiq_oracle as S1  # noqa: E402   (study 1's independent oracle; read-only)

NYZ = ZoneInfo("America/New_York")
nan = math.nan
ATR_Q = 0.9999999999999997          # ATR(14) of quiet bars (pine_sma of 14 ones, then the RMA)


# ───────────────────────────── helpers ─────────────────────────────

def ny(s: str) -> int:
    """UTC epoch seconds of a New York wall-clock time 'YYYY-MM-DD HH:MM'."""
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=NYZ).timestamp())


def utc_s(*a) -> int:
    return int(datetime(*a, tzinfo=timezone.utc).timestamp())


class Chart:
    """Synthetic chart bars of ``tf`` minutes keyed by their New York open time."""

    def __init__(self, tf: int = 15):
        self.tf = tf
        self.b = {}

    def quiet(self, a: str, z: str, px: float = 100.0, half: float = 0.5, v: float = 100.0) -> "Chart":
        t, end = ny(a), ny(z)
        while t < end:
            self.b[t] = [px, px + half, px - half, px, v]
            t += 60 * self.tf
        return self

    def put(self, when: str, o, h, l, c, v=100.0) -> "Chart":
        assert l <= min(o, c) and h >= max(o, c), when
        self.b[ny(when)] = [float(o), float(h), float(l), float(c), float(v)]
        return self

    def drop(self, a: str, z: str) -> "Chart":
        ta, tz_ = ny(a), ny(z)
        for t in [t for t in self.b if ta <= t < tz_]:
            del self.b[t]
        return self

    def arrays(self):
        ts = sorted(self.b)
        m = np.array([self.b[t] for t in ts], np.float64).reshape(-1, 5)
        return (np.array(ts, np.int64), m[:, 0].copy(), m[:, 1].copy(), m[:, 2].copy(), m[:, 3].copy(),
                m[:, 4].copy())

    def idx(self, when: str) -> int:
        return sorted(self.b).index(ny(when))

    def _htf(self, htf, n):
        return np.full(n, float(htf)) if np.isscalar(htf) else np.asarray(htf, np.float64)

    def run(self, htf=1.0, **kw) -> pd.DataFrame:
        t, o, h, l, c, v = self.arrays()
        return O.session_hunter(t, o, h, l, c, v, self.tf, self._htf(htf, len(t)), **kw)

    def series(self, htf=1.0, **kw):
        t, o, h, l, c, v = self.arrays()
        return O.session_series(t, o, h, l, c, v, self.tf, self._htf(htf, len(t)), **kw)

    def raw(self, htf=1.0, **kw):
        t, o, h, l, c, v = self.arrays()
        rows, _ = O._run(t, o, h, l, c, v, self.tf, self._htf(htf, len(t)), **kw)
        return O._frame(rows)


def week(tf: int = 15, to: str = "2024-01-09 20:00") -> Chart:
    """Quiet bars, gold-like: Friday 2024-01-05 08:00-17:00 New York, then from the week's open on Sunday 2024-01-07
    18:00 to ``to``. The scenarios trade Tuesday 2024-01-09 (EST): its day starts on Monday 2024-01-08 at 20:00 New
    York (01:00 UTC); its Asian range, its London range and its previous day's (Monday's) high / low are 100.5 / 99.5,
    and Monday is a complete weekday, so ``pWk`` is true on Tuesday whatever the first bar does (R1)."""
    return Chart(tf).quiet("2024-01-05 08:00", "2024-01-05 17:00").quiet("2024-01-07 18:00", to)


def at(hm: str, day: str = "2024-01-09") -> str:
    return f"{day} {hm}"


def one(df: pd.DataFrame, setup=None):
    if setup is not None:
        df = df[df.setup == setup]
    assert len(df) == 1, df
    return df.iloc[0]


def no_exit(r, modes=O.MODES):
    for m in modes:
        assert r[f"exit_bar_{m}"] == -1 and math.isnan(r[f"exit_price_{m}"]) and math.isnan(r[f"R_{m}"]), m


def same(a, b) -> bool:
    return (a == b) or (a != a and b != b)


# ───────────────────────────── 1. the traps of the spec (section 2.6, "Risks"), one test each ─────────────────────

def test_trap01_day_key_time_plus_4h_and_the_weekday_taken_from_it():
    """Spec test 1. The day changes at 20:00 New York: 01:00 UTC in winter, 00:00 UTC in summer; the weekday is the
    day key's, so Friday 20:00 starts Saturday (no setups) and Sunday 20:00 starts Monday."""
    # winter, EST: 19:55 NY = 00:55 UTC (Monday's day), 20:00 NY = 01:00 UTC (Tuesday's day)
    ch = Chart(5).quiet("2024-01-08 18:00", "2024-01-08 22:00")
    t = ch.arrays()[0]
    s = ch.series()
    a, b = ch.idx("2024-01-08 19:55"), ch.idx("2024-01-08 20:00")
    assert t[a] == utc_s(2024, 1, 9, 0, 55) and t[b] == utc_s(2024, 1, 9, 1, 0)
    assert s["dk"][a] == 20240108 and s["dk"][b] == 20240109
    assert not s["new_day"][a] and s["new_day"][b]
    assert np.flatnonzero(s["new_day"]).tolist() == [b]                    # 20:00 only: not bar 0 (R1)
    assert s["ny_min"][b] == 1200 and s["in_asia"][b] and not s["in_asia"][a] and s["close_t"][a]
    assert not s["close_t"][b]
    # summer, EDT: 19:55 NY = 23:55 UTC, 20:00 NY = 00:00 UTC
    ch = Chart(5).quiet("2023-06-12 18:00", "2023-06-12 22:00")
    t = ch.arrays()[0]
    s = ch.series()
    a, b = ch.idx("2023-06-12 19:55"), ch.idx("2023-06-12 20:00")
    assert t[a] == utc_s(2023, 6, 12, 23, 55) and t[b] == utc_s(2023, 6, 13, 0, 0)
    assert s["dk"][a] == 20230612 and s["dk"][b] == 20230613 and s["new_day"][b] and not s["new_day"][a]
    # the weekday of the day key (Pine dayofweek: Sunday 1 .. Saturday 7)
    ch = Chart(15).quiet("2024-01-12 19:00", "2024-01-14 21:00")
    s = ch.series()
    for when, dk, dow, wd in (("2024-01-12 19:45", 20240112, 6, True), ("2024-01-12 20:00", 20240113, 7, False),
                              ("2024-01-14 19:45", 20240114, 1, False), ("2024-01-14 20:00", 20240115, 2, True)):
        i = ch.idx(when)
        assert (s["dk"][i], s["dow"][i], bool(s["weekday"][i])) == (dk, dow, wd), when
    # end to end (BTC-like, every day): Monday's Asian range is Sunday evening's; Saturday's sweep is not traded
    ch = Chart(15).quiet("2024-01-11 08:00", "2024-01-15 12:00")
    ch.put("2024-01-13 02:15", 100.0, 101.0, 99.9, 100.3)        # Saturday 02:15 (Saturday's day): not a weekday
    ch.put("2024-01-14 21:00", 100.0, 100.7, 99.5, 100.0)        # Sunday 21:00 belongs to Monday's Asia: high 100.7
    ch.put("2024-01-14 19:00", 100.0, 103.0, 99.5, 100.0)        # Sunday 19:00 is Sunday's day, not Monday's Asia
    ch.put("2024-01-15 02:15", 100.0, 101.0, 99.9, 100.3)        # Monday 02:15 sweeps 100.7, closes back inside
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.bar == ch.idx("2024-01-15 02:15") and r.dir == -1 and r.r_hi == 100.7 and r.r_lo == 99.5
    assert r.stop == 101.0 and r.tgt_ref == 99.5


def _monday_case(weekend: str) -> Chart:
    """Friday 2024-01-12's day has high 101.0 and low 99.0; Monday 2024-01-15 03:00 sweeps Friday's high and closes
    back inside; Tuesday 2024-01-16 03:00 sweeps Monday's high (101.5) and closes back inside."""
    ch = Chart(15).quiet("2024-01-10 08:00", "2024-01-12 17:00")
    ch.put("2024-01-12 10:00", 100.0, 101.0, 99.5, 100.0)
    ch.put("2024-01-12 11:00", 100.0, 100.5, 99.0, 100.0)
    if weekend == "gold":
        ch.put("2024-01-12 16:45", 99.0, 99.5, 99.0, 99.0)          # Friday's last close 99.0 < its open 100.0
        ch.quiet("2024-01-14 18:00", "2024-01-16 20:00")           # the week opens on Sunday 18:00 New York
    else:
        ch.quiet("2024-01-12 17:00", "2024-01-16 20:00")           # BTC: every hour of the weekend
    ch.put("2024-01-15 02:15", 100.0, 101.0, 99.9, 100.3)            # Monday: an Asia sweep (for 'YC')
    ch.put("2024-01-15 03:00", 100.0, 101.5, 99.9, 100.4)            # Monday: a clean sweep of Friday's high
    ch.put("2024-01-16 03:00", 100.0, 102.0, 99.9, 101.0)            # Tuesday: a sweep of Monday's high 101.5
    return ch


@pytest.mark.parametrize("weekend", ["gold", "btc"])
def test_trap02_the_monday_pwk_quirk(weekend):
    """Spec test 2 and R7. The non-weekday pseudo-day before Sunday 20:00 makes pWk false for Monday: the clean
    previous-day sweep on Monday gives no signal (Monday's pdh still holds Friday's high, unused); Tuesday trades
    Monday's levels. ``monday_friday_levels=True`` gives Monday Friday's levels."""
    ch = _monday_case(weekend)
    mon = ch.idx("2024-01-15 03:00")
    tue = ch.idx("2024-01-16 03:00")
    s = ch.series(setups=("PD",), conf=())
    assert not s["p_wk"][mon] and s["pdh"][mon] == 101.0 and s["pdl"][mon] == 99.0
    assert s["p_wk"][tue] and s["pdh"][tue] == 101.5 and s["pdl"][tue] == 99.5
    df = ch.run(setups=("PD",), conf=())
    days = [int(O.ny_clock(np.array([t]))["dk"][0]) for t in df.t_signal - 900]
    assert 20240115 not in days                                               # nothing on Monday
    r = one(df[df.bar == tue])
    assert (r.dir, r.r_hi, r.r_lo, r.stop, r.tgt_ref) == (-1, 101.5, 99.5, 102.0, 99.5)
    # the variant: Monday reads Friday's levels
    s2 = ch.series(setups=("PD",), conf=(), monday_friday_levels=True)
    assert s2["p_wk"][mon] and s2["pdh"][mon] == 101.0
    df2 = ch.run(setups=("PD",), conf=(), monday_friday_levels=True)
    m = one(df2[df2.bar == mon])
    assert (m.dir, m.r_hi, m.r_lo, m.stop, m.tgt_ref) == (-1, 101.0, 99.0, 101.5, 99.0)
    r2 = one(df2[df2.bar == tue])
    assert all(same(r2[k], r[k]) for k in O.COLUMNS)
    # yesterday's candle on Monday: never in the script (pWk false); the variant reads Friday's (a down day)
    if weekend == "gold":
        a = ch.idx("2024-01-15 02:15")
        assert ch.run(setups=("AS",), conf=("YC",)).query("bar == @a").empty
        s3 = ch.series(setups=("AS",), conf=("YC",), monday_friday_levels=True)
        assert s3["p_c"][a] == 99.0 and s3["p_o"][a] == 100.0
        r3 = one(ch.run(setups=("AS",), conf=("YC",), monday_friday_levels=True).query("bar == @a"))
        assert r3.dir == -1


def test_trap03_the_whole_bar_inside_the_window():
    """f_in: ``nyMin >= s0 and nyMin + tfMin <= s1``. On M15 the 04:45 bar is in 02:00-05:00, the 05:00 and the
    01:45 bars are not; a bar opening at 04:50 is not (it ends at 05:05). On 1H the 04:00 bar is in it and no bar fits
    the opening range 09:30-10:00."""
    sweep = (100.0, 101.0, 99.9, 100.3)
    for when, inside in (("01:45", False), ("02:00", True), ("04:45", True), ("05:00", False)):
        ch = week(15).put(at(when), *sweep)
        df = ch.run(setups=("AS",), conf=())
        assert (len(df) == 1) == inside, when
        if inside:
            assert one(df).bar == ch.idx(at(when))
    ch = week(15).drop(at("04:45"), at("05:00")).put(at("04:50"), *sweep)          # a misaligned bar
    s = ch.series(setups=("AS",), conf=())
    i = ch.idx(at("04:50"))
    assert s["ny_min"][i] == 290 and not s["in_lon"][i] and s["in_lon"][i - 1]
    assert ch.run(setups=("AS",), conf=()).empty
    # 1H: the London window holds the 02:00, 03:00 and 04:00 bars
    for when, inside in (("01:00", False), ("04:00", True), ("05:00", False)):
        ch = week(60).put(at(when), *sweep)
        assert (len(ch.run(setups=("AS",), conf=())) == 1) == inside, when
    s = week(60).series()
    assert not s["in_or"].any() and int(s["in_lon"].sum()) == 3 * 2 and int(s["in_asia"].sum()) == 4 * 2  # Mon, Tue


def test_trap04_the_sweep_state_machine():
    """Spec tests 3-5 in miniature: (a) the sweep and the close back inside on different bars; (b) a bar that fails
    the confirmations does not end the setup; (c) both sides swept: dead for the day, on two bars or on one."""
    # (a) 02:15 sweeps and closes outside, 02:30 closes back inside: the signal is 02:30's, the stop 02:15's high
    ch = week(15).put(at("02:15"), 100.4, 101.0, 100.2, 100.8).put(at("02:30"), 100.8, 100.9, 100.1, 100.2)
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.bar == ch.idx(at("02:30")) and r.dir == -1 and r.stop == 101.0
    # (b) the HTF confirmation fails at 02:15 (+1 for a short) and passes at 02:30: the setup trades at 02:30
    ch = week(15).put(at("02:15"), 100.0, 101.0, 99.9, 100.3).put(at("02:30"), 100.3, 100.4, 99.9, 100.2)
    htf = np.ones(len(ch.b))
    htf[ch.idx(at("02:30")):] = -1.0
    r = one(ch.run(htf=htf, setups=("AS",), conf=("HTF",)))
    assert r.bar == ch.idx(at("02:30")) and r.stop == 101.0
    assert one(ch.run(htf=-1.0, setups=("AS",), conf=("HTF",))).bar == ch.idx(at("02:15"))
    assert ch.run(htf=0.0, setups=("AS",), conf=("HTF",)).empty
    # (c) both sides swept on two bars, then a close inside: dead
    ch = week(15).put(at("02:15"), 100.4, 101.0, 100.2, 100.8).put(at("02:30"), 100.8, 100.9, 99.2, 99.4)
    ch.put(at("02:45"), 99.6, 100.2, 99.6, 100.0)
    assert ch.run(setups=("AS",), conf=()).empty
    ch.put(at("02:30"), 100.8, 100.9, 99.6, 99.7)                                # control: the low is not swept
    assert one(ch.run(setups=("AS",), conf=())).bar == ch.idx(at("02:30"))
    # both sides on one bar, closing inside: dead at once, the following close inside is not traded
    ch = week(15).put(at("02:15"), 100.0, 100.8, 99.2, 100.0).put(at("02:30"), 100.0, 100.4, 99.9, 100.2)
    assert ch.run(setups=("AS",), conf=()).empty


def test_trap05_the_stop_extreme_accumulates_over_window_bars_only():
    """upEx is the max of the highs above rH on WINDOW bars only; a spike before the window does not count, and a
    price already above the level when the window opens counts as a sweep."""
    ch = week(15)
    ch.put(at("01:00"), 100.0, 103.0, 99.6, 100.0)          # between the sessions: outside the window
    ch.put(at("02:00"), 100.0, 101.0, 99.9, 100.8)          # sweeps, closes outside
    ch.put(at("02:15"), 100.8, 101.4, 100.6, 100.9)         # extends the sweep to 101.4
    ch.put(at("02:30"), 100.9, 100.9, 100.1, 100.2)         # back inside
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.bar == ch.idx(at("02:30")) and r.stop == 101.4 and r.r_hi == 100.5
    ch = week(15)
    ch.put(at("01:30"), 100.0, 100.9, 99.9, 100.8)          # above the Asian high before the window (high 100.9)
    ch.put(at("01:45"), 100.8, 100.9, 100.7, 100.8)
    ch.put(at("02:00"), 100.8, 100.85, 100.6, 100.7)        # the window opens above the level: a sweep (high 100.85)
    ch.put(at("02:15"), 100.7, 100.75, 100.1, 100.2)        # back inside
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.bar == ch.idx(at("02:15")) and r.stop == 100.85


def test_trap06_the_minimum_stop_is_measured_from_the_signal_close():
    """Spec test 6: a sweep extreme 0.3 ATR from the close moves the stop to close + 0.5 ATR (short) / close - 0.5
    ATR (long), from the SIGNAL bar's close, not from the entry open; a breakout's midpoint likewise."""
    ch = week(15).put(at("02:15"), 100.2, 100.7, 100.1, 100.4).put(at("02:30"), 100.3, 100.5, 99.6, 100.0)
    i = ch.idx(at("02:15"))
    s = ch.series(setups=("AS",), conf=())
    atr = s["atr"][i]
    assert atr == pytest.approx(ATR_Q * 13 / 14 + 0.7 / 14, abs=1e-12)          # true range 0.7 on the sweep bar
    assert (100.7 - 100.4) / atr == pytest.approx(0.30657, abs=1e-4)
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.bar == i and r.dir == -1 and r.stop == 100.4 - (-1) * 0.5 * atr      # close + 0.5 ATR
    assert r.stop == pytest.approx(100.4 + 0.5 * 0.9785714285714283, abs=1e-12)
    # the long mirror
    ch = week(15).put(at("02:15"), 99.8, 99.9, 99.3, 99.6)
    i = ch.idx(at("02:15"))
    atr = ch.series(setups=("AS",), conf=())["atr"][i]
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.dir == 1 and r.stop == 99.6 - 1 * 0.5 * atr
    # the sweep 0.5 ATR or more away: the extreme is the stop
    ch = week(15).put(at("02:15"), 100.0, 101.0, 99.9, 100.3)
    assert one(ch.run(setups=("AS",), conf=())).stop == 101.0
    # a breakout of a narrow Asian range (0.2 wide): the midpoint 0.15 from the close is closer than 0.5 ATR
    ch = week(15).quiet(at("20:00", "2024-01-08"), at("00:00"), px=100.0, half=0.1)
    ch.put(at("02:15"), 100.0, 100.2, 99.95, 100.15)
    i = ch.idx(at("02:15"))
    atr = ch.series(setups=("AB",), conf=())["atr"][i]
    r = one(ch.run(setups=("AB",), conf=()))
    assert (r.r_hi, r.r_lo) == (100.1, 99.9) and r.dir == 1 and abs(100.15 - (100.1 + 99.9) / 2) < 0.5 * atr
    assert r.stop == 100.15 - 1 * 0.5 * atr and r.tgt_ref == 100.1 + (100.1 - 99.9)


def _ls_short(to: str = "2024-01-09 20:00") -> Chart:
    """A London-sweep short on Tuesday 10:45 (M15): the London range is 100.5 / 99.5, 10:45 sweeps 101.0 and closes
    100.3 (stop 101.0); the next bar is 11:00."""
    return week(15, to=to).put(at("10:45"), 100.2, 101.0, 100.1, 100.3)


def test_trap07_the_cancels_at_entry():
    """Spec test 7 and R5: the entry is cancelled when the next bar is in 16:00-20:00, when it starts a new day, when
    its open is beyond the stop, and when it equals the stop."""
    ch = _ls_short()
    r = one(ch.run(setups=("LS",), conf=()))
    assert r.bar == ch.idx(at("10:45")) and r.stop == 101.0 and r.entry_bar == ch.idx(at("11:00"))
    assert r.cancelled is None and r.exit_reason_hold == "closeT"
    # the next bar is the 16:00 bar
    ch = _ls_short().drop(at("11:00"), at("16:00"))
    r = one(ch.run(setups=("LS",), conf=()))
    assert r.entry_bar == ch.idx(at("16:00")) and r.cancelled == "closeT"
    no_exit(r)
    # the next bar is Tuesday 20:00, the first bar of Wednesday's day
    ch = _ls_short(to="2024-01-09 21:00").drop(at("11:00"), at("20:00"))
    r = one(ch.run(setups=("LS",), conf=()))
    assert r.entry_bar == ch.idx(at("20:00")) and r.cancelled == "new_day"
    no_exit(r)
    # the next bar is Wednesday 17:00: both closeT and a new day; the label is 'closeT' (R5)
    ch = _ls_short().drop(at("11:00"), at("20:00")).put("2024-01-10 17:00", 100.0, 100.5, 99.5, 100.0)
    r = one(ch.run(setups=("LS",), conf=()))
    assert r.cancelled == "closeT"
    # the next open is beyond the stop / equals it
    for o, why in ((101.3, "open_beyond_stop"), (101.0, "risk<=0"), (100.99, None)):
        ch = _ls_short().put(at("11:00"), o, max(o, 101.3), 100.0, 100.0)
        r = one(ch.run(setups=("LS",), conf=()))
        assert r.cancelled == why, o
        if why is not None:
            no_exit(r)
            assert r.exit_reason_liq is None                       # the general cancel comes before E3's own


def _bid_case() -> Chart:
    """An Asia-sweep short: 02:15 sweeps 100.75 and closes 100.25 (|close - stop| = 0.5 > 0.5 ATR = 0.4946, so the
    stop stays 100.75); the entry bar 02:30 opens at 100.25 (risk 0.5); 02:45 (quiet) touches 99.5, the opposite
    side; 12:00 touches 99.2 (the 2R target 99.25); the 16:00 bar opens at 99.25."""
    ch = week(15)
    ch.put(at("02:15"), 100.0, 100.75, 99.9, 100.25)
    ch.put(at("02:30"), 100.25, 100.5, 99.6, 100.0)
    ch.put(at("12:00"), 100.0, 100.2, 99.2, 99.5)
    ch.put(at("16:00"), 99.25, 99.5, 99.0, 99.25)
    return ch


def test_trap08_r_is_measured_from_the_bid_open():
    """R = (d * (x - e) - 2 * cost) / risk with e = the entry bar's open (the bid bars' open, no spread) and risk =
    |e - stop|, cost 0 (L432, L482)."""
    ch = _bid_case()
    r = one(ch.run(setups=("AS",), conf=()))
    e = ch.arrays()[1][r.entry_bar]
    assert r.bar == ch.idx(at("02:15")) and r.stop == 100.75 and e == 100.25 and r.cancelled is None
    assert (r.exit_bar_hold, r.exit_price_hold, r.exit_reason_hold, r.R_hold) == (ch.idx(at("16:00")), 99.25, "closeT",
                                                                                  2.0)
    assert (r.exit_bar_tp2, r.exit_price_tp2, r.exit_reason_tp2, r.R_tp2) == (ch.idx(at("12:00")), 99.25, "target", 2.0)
    assert (r.exit_bar_liq, r.exit_price_liq, r.exit_reason_liq, r.R_liq) == (ch.idx(at("02:45")), 99.5, "target", 1.5)


def test_trap09_the_order_of_exit_checks():
    """Spec test 8 and R6: new day > closeT > stop > target; the stop is checked on the entry bar; a new-day exit is
    booked on the new day's first bar at the previous bar's close."""
    # the 16:00 bar touches the stop but exits at its open
    ch = _bid_case().put(at("16:00"), 100.0, 101.0, 99.9, 100.9)
    r = one(ch.run(setups=("AS",), conf=()))
    assert (r.exit_bar_hold, r.exit_price_hold, r.exit_reason_hold, r.R_hold) == (ch.idx(at("16:00")), 100.0, "closeT",
                                                                                  0.5)
    # one bar touches the stop (100.75) and the 2R target (99.25): the stop
    ch = _bid_case().put(at("12:00"), 100.0, 100.8, 99.2, 99.5)
    r = one(ch.run(setups=("AS",), conf=()))
    assert (r.exit_bar_tp2, r.exit_price_tp2, r.exit_reason_tp2, r.R_tp2) == (ch.idx(at("12:00")), 100.75, "stop", -1.0)
    assert (r.exit_bar_hold, r.exit_reason_hold) == (ch.idx(at("12:00")), "stop")
    # a new day before 16:00 (a hole from 12:00 to Wednesday 17:00, a bar that is also closeT): 'new_day' at the
    # previous close (11:45's, 100.0), booked on the Wednesday bar
    ch = _bid_case().drop(at("12:00"), at("20:00")).put("2024-01-10 17:00", 99.0, 99.5, 98.5, 99.0)
    r = one(ch.run(setups=("AS",), conf=()))
    w = ch.idx("2024-01-10 17:00")
    for m in ("hold", "tp2"):
        assert (r[f"exit_bar_{m}"], r[f"exit_price_{m}"], r[f"exit_reason_{m}"]) == (w, 100.0, "new_day"), m
        assert ch.arrays()[4][w - 1] == 100.0
    assert r.R_hold == 0.5
    # the stop on the entry bar
    ch = _bid_case().put(at("02:30"), 100.25, 100.8, 99.6, 100.0)
    r = one(ch.run(setups=("AS",), conf=()))
    for m in O.MODES:
        assert (r[f"exit_bar_{m}"], r[f"exit_price_{m}"], r[f"exit_reason_{m}"], r[f"R_{m}"]) == (
            r.entry_bar, 100.75, "stop", -1.0), m


def test_trap10_the_htf_value_is_taken_at_the_bar_open():
    """Spec test 11: htfE = request.security("60", ema(close, 200)[1], lookahead_on) = the EMA200 of the last 1H bar
    closed at or before the chart bar's OPEN. On the 10:45 M15 bar it is the EMA as of 10:00 (the 09:00 bar), not
    the 10:00 bar's (which closes at 11:00, with the chart bar); on a 1H chart it is the previous 1H bar's."""
    t1 = np.array([ny(at(f"{k:02d}:00")) for k in range(13)], np.int64)                 # 00:00 .. 12:00
    c1 = np.arange(1.0, 14.0)
    h1 = NS(t=t1, tc=t1 + 3600, c=c1)
    a = 2 / 201
    ema = [1.0]
    for k in range(1, 13):
        ema.append(a * c1[k] + (1 - a) * ema[-1])                                    # pine_ema by hand
    tc15 = np.array([ny(at(f"{hh:02d}:{mm:02d}")) for hh in (9, 10, 11) for mm in (0, 15, 30, 45)], np.int64)
    e = O.htf_ema_at_open(tc15, h1)
    want = {"09:00": 8, "09:45": 8, "10:00": 9, "10:45": 9, "11:00": 10, "11:45": 10}
    for hm, k in want.items():
        i = int(np.flatnonzero(tc15 == ny(at(hm)))[0])
        assert e[i] == ema[k], hm
    i = int(np.flatnonzero(tc15 == ny(at("10:45")))[0])
    close_based = X.value_at(h1.tc, np.asarray(ema), tc15 + 900, np.nan)            # htf_at would read the 10:00 bar
    assert close_based[i] == ema[10] and e[i] != close_based[i]
    # the direction: a close between the two EMAs is +1 at the open-based value
    cc = np.full(len(tc15), (ema[9] + ema[10]) / 2)
    d = O.htf_ema_dir(tc15, cc, h1)
    assert d[i] == 1 and d[int(np.flatnonzero(tc15 == ny(at("11:00")))[0])] == -1
    # a 1H chart: the previous 1H bar's EMA; before the first closed 1H bar: na, direction 0
    e60 = O.htf_ema_at_open(t1, h1)
    assert np.isnan(e60[0]) and all(e60[k] == ema[k - 1] for k in range(1, 13))
    assert O.htf_ema_dir(t1, c1, h1)[0] == 0
    # the 1H EMA200 equals study 1's oracle's (seeded with the first close)
    np.testing.assert_array_equal(O.pine_ema(c1, 200), S1.ema(c1, 200))


def test_trap11_the_fvg_offsets_and_the_1_on_hi5_lo5():
    """Spec test 12 and R3: fvgUp holds on the gap bar and the three after it, on the last of them through low[3] >
    high[5] alone; hi5 = highest(high, 5)[1] leaves the current bar out (a close above it is possible) and reaches
    exactly five bars back; na on bars 0-4."""
    ch = Chart(5).quiet("2024-01-09 06:00", "2024-01-09 08:00")
    j = ch.idx("2024-01-09 07:00")
    ch.put("2024-01-09 06:55", 100.0, 102.0, 99.9, 101.5)                                # the displacement candle
    for k in range(0, 12):
        ch.put(datetime.fromtimestamp(ny("2024-01-09 07:00") + 300 * k, NYZ).strftime("%Y-%m-%d %H:%M"),
               101.5, 102.0, 101.0, 101.5)                                               # low 101.0 > 100.5
    s = ch.series(conf=())
    up = s["fvg_up"]
    assert up[j:j + 4].all() and not up[j - 1] and not up[j + 4] and not s["fvg_dn"][j - 3:j + 6].any()
    t, o, h, l, c, v = ch.arrays()
    assert l[j + 3 - 3] > h[j + 3 - 5]                                                    # only low[3] > high[5]
    assert not (l[j + 3] > h[j + 1] or l[j + 2] > h[j] or l[j + 1] > h[j - 1])
    # the mirror: fvgDn
    ch = Chart(5).quiet("2024-01-09 06:00", "2024-01-09 08:00")
    ch.put("2024-01-09 06:55", 100.0, 100.1, 98.0, 98.5)
    for k in range(0, 12):
        ch.put(datetime.fromtimestamp(ny("2024-01-09 07:00") + 300 * k, NYZ).strftime("%Y-%m-%d %H:%M"),
               98.5, 99.0, 98.0, 98.5)                                                   # high 99.0 < 99.5
    dn = ch.series(conf=())["fvg_dn"]
    assert dn[j:j + 4].all() and not dn[j - 1] and not dn[j + 4]
    # hi5 / lo5
    s = ch.series(conf=())
    t, o, h, l, c, v = ch.arrays()
    assert np.isnan(s["hi5"][:5]).all() and np.isnan(s["lo5"][:5]).all()
    for i in range(5, len(t)):
        assert s["hi5"][i] == max(h[i - 5:i]) and s["lo5"][i] == min(l[i - 5:i])
    # end to end, an Asia-sweep long with 'MSS': the close back inside must be above max(high[1..5])
    def mss_case(h_back: dict) -> Chart:
        ch = week(15)
        for hm in ("00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30", "01:45", "02:00"):
            ch.put(at(hm), 99.8, h_back.get(hm, 100.0), 99.6, 99.8)
        ch.put(at("02:15"), 99.8, 99.9, 99.2, 99.3)                   # sweeps the Asian low, closes outside
        ch.put(at("02:30"), 99.3, 100.3, 99.3, 100.2)                 # back inside, above max(high[1..5]) = 100.0
        return ch
    ch = mss_case({})
    r = one(ch.run(setups=("AS",), conf=("MSS",)))
    assert r.bar == ch.idx(at("02:30")) and r.dir == 1 and r.stop == 99.2
    assert ch.series(setups=("AS",), conf=("MSS",))["hi5"][r.bar] == 100.0
    assert one(mss_case({"01:00": 100.4}).run(setups=("AS",), conf=("MSS",))).bar == r.bar   # 6 bars back: out
    assert mss_case({"01:15": 100.4}).run(setups=("AS",), conf=("MSS",)).empty              # 5 bars back: in


def test_trap12_the_fill_beyond_the_stop_is_dropped():
    """Section 0.4 of the spec (a kernel trap: a stop at or beyond the fill books a fake profit). The script drops the
    entry when the fill bar's open is at or beyond the stop (L433): no mode books any exit, for a short or a long."""
    for o_next, why in ((101.5, "open_beyond_stop"), (101.2, "risk<=0")):
        ch = _spec34().put(at("03:00"), o_next, max(o_next, 101.6), 99.9, 100.0)
        r = one(ch.run(setups=("AS",), conf=("FVG",)))
        assert r.stop == 101.2 and r.cancelled == why
        no_exit(r)
        assert all(r[f"exit_reason_{m}"] is None for m in O.MODES)
    # a long: the next open below the stop
    ch = week(15).put(at("02:15"), 99.8, 99.9, 99.0, 99.4).put(at("02:30"), 99.4, 99.95, 99.4, 99.8)
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.dir == 1 and r.stop == 99.0
    ch.put(at("02:45"), 98.9, 99.3, 98.8, 99.2)
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.cancelled == "open_beyond_stop"
    no_exit(r)


def _five_lanes(to: str = "2024-01-09 20:00") -> Chart:
    ch = week(15, to=to)
    ch.put(at("02:15"), 100.2, 101.0, 100.1, 100.9)       # AB long (close above the Asian high); AS / PD sweep
    ch.put(at("02:30"), 100.9, 100.95, 100.2, 100.3)      # AS and PD short (back inside)
    ch.put(at("07:15"), 100.5, 101.2, 100.4, 100.6)       # LS short: sweeps the London high 101.0
    ch.put(at("10:15"), 100.6, 101.1, 100.5, 101.0)       # OR long: closes above the opening range 100.5
    ch.put(at("10:30"), 100.8, 101.0, 100.6, 100.9)       # OR's entry bar (a quiet open of 100.0 = its stop: risk<=0)
    return ch


def test_trap13_running_five_lanes():
    """Each setup is its own lane with its own state and trades (overlapping in time); a lane trades at most once a
    day; a subset of setups gives the same rows for each."""
    ch = _five_lanes()
    df = ch.run(conf=())
    assert list(df.setup) == ["AB", "AS", "PD", "LS", "OR"]                     # bar order, then the script's
    want = {"AB": ("02:15", 1, 100.0, 101.5, 100.5, 99.5), "AS": ("02:30", -1, 101.0, 99.5, 100.5, 99.5),
            "PD": ("02:30", -1, 101.0, 99.5, 100.5, 99.5), "LS": ("07:15", -1, 101.2, 99.5, 101.0, 99.5),
            "OR": ("10:15", 1, 100.0, 101.5, 100.5, 99.5)}
    for code, (hm, d, stop, ref, rh, rl) in want.items():
        r = one(df, code)
        assert (r.bar, r.dir, r.stop, r.tgt_ref, r.r_hi, r.r_lo) == (ch.idx(at(hm)), d, stop, ref, rh, rl), code
        assert r.entry_bar == r.bar + 1 and r.cancelled is None
        alone = ch.run(setups=(code,), conf=())
        assert len(alone) == 1 and all(same(alone.iloc[0][k], r[k]) for k in O.COLUMNS), code
    # each lane's own exits: AB's stop (the midpoint) at 02:45; LS's sweep bar 07:15 (high 101.2) takes the stops of
    # AS and PD (101.0), held together since 02:45; LS holds to 16:00, OR (entered 10:30) stops at 10:45
    exits = {code: (one(df, code).exit_bar_hold, one(df, code).exit_reason_hold) for code in want}
    assert exits == {"AB": (ch.idx(at("02:45")), "stop"), "AS": (ch.idx(at("07:15")), "stop"),
                     "PD": (ch.idx(at("07:15")), "stop"), "LS": (ch.idx(at("16:00")), "closeT"),
                     "OR": (ch.idx(at("10:45")), "stop")}
    assert one(week(15).put(at("10:15"), 100.6, 101.1, 100.5, 101.0).run(setups=("OR",), conf=())).cancelled == "risk<=0"
    # one trade a day per lane: a second Asia sweep at 03:30 is not traded; the same pattern on Wednesday is
    ch = _five_lanes(to="2024-01-10 20:00").put(at("03:30"), 100.0, 100.9, 99.9, 100.3)
    ch.put(at("02:15", "2024-01-10"), 100.0, 100.9, 99.9, 100.3)
    rows = ch.run(setups=("AS",), conf=())
    assert list(rows.bar) == [ch.idx(at("02:30")), ch.idx(at("02:15", "2024-01-10"))]


# ───────────────────────────── 1b. the spec's numbered tests not covered above ─────────────────────────────

def _spec34() -> Chart:
    """Spec tests 3-4 (M15): 02:15 wicks above the Asian high (101.2) and closes inside with no FVG; 02:30 falls;
    02:45's high 99.8 is below 02:15's low 99.9 (a bearish FVG) and it closes inside."""
    ch = week(15)
    ch.put(at("02:15"), 100.0, 101.2, 99.9, 100.3)
    ch.put(at("02:30"), 100.3, 100.4, 99.6, 99.7)
    ch.put(at("02:45"), 99.7, 99.8, 99.55, 99.65)
    return ch


def test_spec03_04_a_wick_without_fvg_then_an_fvg_at_0245_gives_a_short():
    """Stop = the highest high above the Asian high since 02:00 (101.2); entry at the 03:00 open."""
    ch = _spec34()
    s = ch.series(setups=("AS",), conf=("FVG",))
    a, b, c = ch.idx(at("02:15")), ch.idx(at("02:30")), ch.idx(at("02:45"))
    assert not s["fvg_dn"][a] and not s["fvg_dn"][b] and s["fvg_dn"][c]
    assert s["as_done"][a] and s["as_h"][a] == 100.5 and s["as_l"][a] == 99.5
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert (r.bar, r.dir, r.stop, r.tgt_ref, r.r_hi, r.r_lo) == (c, -1, 101.2, 99.5, 100.5, 99.5)
    assert r.t_signal == ny(at("03:00")) and r.entry_bar == ch.idx(at("03:00")) and r.cancelled is None
    assert (r.exit_bar_hold, r.exit_price_hold, r.exit_reason_hold) == (ch.idx(at("16:00")), 100.0, "closeT")
    # without the FVG confirmation the wick bar itself signals
    assert one(ch.run(setups=("AS",), conf=())).bar == a


def test_spec05_both_sides_swept_make_the_setup_dead():
    ch = week(15).put(at("02:15"), 100.4, 101.0, 100.2, 100.8).put(at("02:30"), 100.8, 100.9, 99.2, 99.4)
    for k, hm in enumerate(("02:45", "03:00", "03:15")):
        ch.put(at(hm), 100.0, 100.4, 99.6, 100.0 + 0.1 * k)
    assert ch.run(setups=("AS",), conf=()).empty
    # the next day starts a fresh state
    ch2 = week(15, to="2024-01-10 20:00").put(at("02:15"), 100.4, 101.0, 100.2, 100.8)
    ch2.put(at("02:30"), 100.8, 100.9, 99.2, 99.4).put(at("02:15", "2024-01-10"), 100.0, 101.0, 99.9, 100.3)
    assert list(ch2.run(setups=("AS",), conf=()).bar) == [ch2.idx(at("02:15", "2024-01-10"))]


def test_spec09_an_opposite_liquidity_target_under_1r_cancels_the_trade():
    """E3 only (L437): ``d * (tgt - open) < risk`` cancels; exactly 1R trades."""
    ch = _spec34()
    r = one(ch.run(setups=("AS",), conf=("FVG",)))
    assert r.cancelled is None and r.exit_reason_liq == O.LIQ_CANCEL and r.exit_bar_liq == -1 and math.isnan(r.R_liq)
    assert r.exit_reason_hold == "closeT" and r.exit_reason_tp2 == "closeT"                  # E1 and E2 trade
    # the target exactly 1R away: open 100.25, stop 101.0 (risk 0.75), target 99.5 (0.75 away)
    ch = week(15).put(at("02:15"), 100.0, 101.0, 99.9, 100.3).put(at("02:30"), 100.25, 100.5, 99.6, 100.0)
    r = one(ch.run(setups=("AS",), conf=()))
    assert r.stop == 101.0 and r.exit_reason_liq == "target" and r.R_liq == 1.0
    assert r.exit_bar_liq == ch.idx(at("02:45"))


def test_spec10_an_asia_breakout_more_than_4_atr_from_the_midpoint_finishes_the_setup():
    ch = week(15).put(at("02:15"), 100.0, 110.2, 99.9, 110.0).put(at("02:30"), 110.0, 110.1, 100.6, 101.0)
    i = ch.idx(at("02:15"))
    atr = ch.series(setups=("AB",), conf=())["atr"][i]
    assert atr == pytest.approx(ATR_Q * 13 / 14 + 10.3 / 14, abs=1e-12) and 110.0 - 100.0 > 4 * atr
    assert ch.run(setups=("AB",), conf=()).empty                                   # done, no trade, nothing later
    ch = week(15).put(at("02:30"), 100.0, 101.1, 99.9, 101.0)                     # control: within 4 ATR
    r = one(ch.run(setups=("AB",), conf=()))
    assert (r.bar, r.dir, r.stop, r.tgt_ref) == (ch.idx(at("02:30")), 1, 100.0, 101.5)
    # a breakout bar that fails a confirmation does not finish the setup
    htf = np.full(len(ch.b), -1.0)
    htf[ch.idx(at("02:45")):] = 1.0
    ch.put(at("02:45"), 101.0, 101.2, 100.8, 101.1)
    r = one(ch.run(htf=htf, setups=("AB",), conf=("HTF",)))
    assert r.bar == ch.idx(at("02:45"))


def test_spec13_the_opening_range_setup_is_off_on_1h():
    ch = week(15).put(at("10:15"), 100.6, 101.1, 100.5, 101.0)
    r = one(ch.run(setups=("OR",), conf=()))
    s = ch.series(setups=("OR",), conf=())
    assert int(s["in_or"].sum()) == 2 * 3 and s["o_h"][r.bar] == 100.5 and s["o_done"][r.bar]   # 09:30, 09:45 Fri-Tue
    assert (r.bar, r.dir, r.stop, r.tgt_ref) == (ch.idx(at("10:15")), 1, 100.0, 101.5)
    ch = week(60).put(at("10:00"), 100.0, 101.1, 99.9, 101.0)
    assert ch.run(setups=("OR",), conf=()).empty and not ch.series()["in_or"].any()
    ch = week(30).put(at("10:00"), 100.6, 101.1, 100.5, 101.0)                     # 30 minutes: the 09:30 bar
    assert int(ch.series()["in_or"].sum()) == 3 and len(ch.run(setups=("OR",), conf=())) == 1   # 09:30 Fri-Tue


def test_spec14_golds_sunday_pseudo_day():
    """Gold's week opens on Sunday about 18:05 New York: those bars form a day of their own (Sunday, not a weekday),
    so Monday's pWk is false. A week whose first bar is at 20:00 has no pseudo-day: Monday trades Friday's levels."""
    ch = Chart(5).quiet("2024-01-11 08:00", "2024-01-12 17:00").quiet("2024-01-14 18:05", "2024-01-15 17:00")
    ch.put("2024-01-12 12:00", 100.0, 101.0, 99.5, 100.0)          # Friday's high, outside its own PD window
    ch.put("2024-01-15 03:00", 100.0, 101.5, 99.9, 100.4)
    s = ch.series(setups=("PD",), conf=())
    su, s20, mo = ch.idx("2024-01-14 18:05"), ch.idx("2024-01-14 20:00"), ch.idx("2024-01-15 03:00")
    assert s["new_day"][su] and s["dk"][su] == 20240114 and not s["weekday"][su] and s["close_t"][su]
    assert not s["new_day"][su + 1] and s["dk"][s20 - 1] == 20240114
    assert s["new_day"][s20] and s["dk"][s20] == 20240115 and s["weekday"][s20]
    assert s["p_wk"][su] and not s["p_wk"][s20] and not s["p_wk"][mo] and s["pdh"][mo] == 101.0
    assert ch.run(setups=("PD",), conf=()).empty
    # no bar before 20:00 on Sunday: Monday's previous day is Friday
    ch.drop("2024-01-14 18:00", "2024-01-14 20:00")
    s = ch.series(setups=("PD",), conf=())
    assert s["p_wk"][ch.idx("2024-01-15 03:00")]
    r = one(ch.run(setups=("PD",), conf=()))
    assert (r.bar, r.dir, r.r_hi, r.r_lo, r.stop) == (ch.idx("2024-01-15 03:00"), -1, 101.0, 99.5, 101.5)


# ───────────────────────────── 1c. readings and other rules ─────────────────────────────

def test_reading_r1_the_first_bar_does_not_start_a_day():
    """R1 (as reconciled with port A): newDay is false on bar 0, a comparison with na being false, so the first,
    partial day (Monday from 12:00) has no levels: pdh is na on Tuesday and its PD sweep is not traded. The reading
    this port was written with (true, ``first_bar_new_day=True``) makes the partial Monday Tuesday's "yesterday"."""
    ch = Chart(15).quiet("2024-01-08 12:00", "2024-01-09 20:00")
    ch.put("2024-01-08 13:00", 100.0, 101.0, 99.5, 100.0)
    ch.put(at("03:00"), 100.0, 101.5, 99.9, 100.5)
    s0 = ch.series(setups=("PD",), conf=())
    assert not s0["new_day"][0] and np.isnan(s0["d_h"][:ch.idx("2024-01-08 20:00")]).all()
    assert np.isnan(s0["pdh"][ch.idx(at("03:00"))]) and not s0["p_wk"][ch.idx(at("03:00"))]
    assert ch.run(setups=("PD",), conf=()).empty
    s = ch.series(setups=("PD",), conf=(), first_bar_new_day=True)
    assert s["new_day"][0] and s["pdh"][ch.idx(at("03:00"))] == 101.0 and s["p_wk"][ch.idx(at("03:00"))]
    assert one(ch.raw(setups=("PD",), conf=(), first_bar_new_day=True)).r_hi == 101.0


def test_the_pd_window_is_one_window_from_0200_to_1100():
    """PD runs over 02:00-11:00 as one window, 05:00-07:00 included: a sweep at 04:00 and the close back inside at
    06:00 is a signal at 06:00, with the 04:00 high as the stop."""
    ch = week(15).put(at("04:00"), 100.0, 101.0, 99.9, 100.8)
    for hh in (4, 5):
        for mm in (15, 30, 45) if hh == 4 else (0, 15, 30, 45):
            ch.put(at(f"{hh:02d}:{mm:02d}"), 100.7, 100.8, 100.6, 100.7)
    ch.put(at("06:00"), 100.7, 100.75, 100.2, 100.3)
    r = one(ch.run(setups=("PD",), conf=()))
    assert (r.bar, r.dir, r.stop, r.r_hi, r.r_lo) == (ch.idx(at("06:00")), -1, 101.0, 100.5, 99.5)


def _long_history(wide: bool) -> Chart:
    """Quiet weekdays from Monday 2024-01-01 12:00 to Tuesday 2024-01-09 20:00 New York, the weekend gold-like; with
    ``wide`` one bar at 12:00 every weekday spans 98..102, so every weekday's range is 4.0."""
    ch = Chart(15).quiet("2024-01-01 12:00", "2024-01-05 17:00").quiet("2024-01-07 18:00", "2024-01-09 20:00")
    if wide:
        for d in ("2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"):
            ch.put(f"{d} 12:00", 100.0, 102.0, 98.0, 100.0)
    ch.put(at("02:15"), 100.0, 100.9, 99.9, 100.3)                 # the Asia-sweep short every case below uses
    return ch


def test_the_confirmations_by_hand():
    """FVG, MSS and HTF are pinned above; here PD (premium / discount), RV, TIGHT and YC on the Asia-sweep short at
    Tuesday 02:15 (close 100.3)."""
    # PD: a short needs the close above the midnight open (dd * (mo - close) > 0)
    ch = week(15).put(at("02:15"), 100.0, 100.9, 99.9, 100.3)
    i = ch.idx(at("02:15"))
    assert ch.series(setups=("AS",), conf=("PD",))["mo"][i] == 100.0
    assert one(ch.run(setups=("AS",), conf=("PD",))).bar == i
    ch.put(at("00:00"), 100.4, 100.5, 99.5, 100.0)                            # mo = 100.4 > 100.3
    s = ch.series(setups=("AS",), conf=("PD",))
    assert s["mo"][i] == 100.4 and np.isnan(s["mo"][ch.idx(at("23:45", "2024-01-08"))])     # na from 20:00 to 00:00
    assert ch.run(setups=("AS",), conf=("PD",)).empty
    # RV: volume >= 1.5 * SMA20(volume), the SMA including this bar
    for vol, ok in ((200.0, True), (150.0, False)):
        ch = week(15).put(at("02:15"), 100.0, 100.9, 99.9, 100.3, v=vol)
        vavg = ch.series(setups=("AS",), conf=("RV",))["vavg"][i]
        assert vavg == pytest.approx((19 * 100.0 + vol) / 20, abs=1e-12)
        assert (len(ch.run(setups=("AS",), conf=("RV",))) == 1) == ok, vol
    # TIGHT: the Asian range (1.0) under 50% of the average weekday range (adr: the last up to 10 weekdays, >= 5)
    for wide, ok in ((True, True), (False, False)):
        ch = _long_history(wide)
        j = ch.idx(at("02:15"))
        s = ch.series(setups=("AS",), conf=("TIGHT",))
        assert s["adr"][j] == (4.0 if wide else 1.0)
        assert (len(ch.run(setups=("AS",), conf=("TIGHT",))) == 1) == ok, wide
    s = _long_history(True).series(setups=("AS",), conf=("TIGHT",))
    k = _long_history(True).idx("2024-01-05 03:00")                           # Friday: 3 weekdays done (Jan 2-4)
    assert np.isnan(s["adr"][k])
    # adr is the sequential mean of the stored ranges (R4): ranges 4, 4, 4, 4, 4.5 -> 4.1. The partial first day
    # (Monday 1 January from 12:00, bar 0) is no day of its own (R1), so its range is not stored.
    ch = _long_history(True).put("2024-01-08 12:30", 100.0, 102.5, 98.5, 100.0)        # Monday's range 4.5
    j = ch.idx(at("02:15"))
    rngs = [4.0, 4.0, 4.0, 4.0, 4.5]                                            # Jan 2, 3, 4, 5, 8
    tot = 0.0
    for x in rngs:
        tot = tot + x
    assert ch.series(setups=("AS",), conf=("TIGHT",))["adr"][j] == tot / len(rngs)
    # YC: yesterday's (Monday's) candle must point the trade's way: Monday 19:45 closes 99.0 below Monday's open 100
    ch = _long_history(False)
    assert ch.run(setups=("AS",), conf=("YC",)).empty                          # Monday closed flat (100 = 100)
    ch.put("2024-01-08 19:45", 100.0, 100.5, 99.0, 99.0)
    s = ch.series(setups=("AS",), conf=("YC",))
    j = ch.idx(at("02:15"))
    assert s["p_wk"][j] and s["p_o"][j] == 100.0 and s["p_c"][j] == 99.0
    assert one(ch.run(setups=("AS",), conf=("YC",))).bar == j


def test_contract_columns_dtypes_and_refused_inputs():
    df = _bid_case().run(setups=("AS",), conf=())
    assert tuple(df.columns) == O.COLUMNS
    ints = ["bar", "t_signal", "dir", "entry_bar", "exit_bar_hold", "exit_bar_tp2", "exit_bar_liq"]
    floats = ["stop", "tgt_ref", "r_hi", "r_lo", "exit_price_hold", "R_hold", "exit_price_tp2", "R_tp2",
              "exit_price_liq", "R_liq"]
    assert all(df[k].dtype == np.int64 for k in ints) and all(df[k].dtype == np.float64 for k in floats)
    assert all(df[k].dtype == object for k in ("setup", "cancelled", "exit_reason_hold", "exit_reason_tp2",
                                               "exit_reason_liq"))
    z = np.zeros(0)
    empty = O.session_hunter(np.zeros(0, np.int64), z, z, z, z, z, 5, z)
    assert empty.empty and tuple(empty.columns) == O.COLUMNS and empty["bar"].dtype == np.int64
    t, o, h, l, c, v = _bid_case().arrays()
    hd = np.ones(len(t))
    keep = [a.copy() for a in (t, o, h, l, c, v, hd)]
    O.session_hunter(t, o, h, l, c, v, 15, hd, conf=O.CONFIRMATIONS)
    assert all(np.array_equal(a, b) for a, b in zip((t, o, h, l, c, v, hd), keep))   # inputs left alone
    with pytest.raises(ValueError):
        O.session_hunter(t, o, h, l, c, v, 15, hd, setups=("XX",))
    with pytest.raises(ValueError):
        O.session_hunter(t, o, h, l, c, v, 15, hd, conf=("FVG", "EMA"))
    with pytest.raises(ValueError):
        O.session_hunter(t[::-1].copy(), o, h, l, c, v, 15, hd)
    with pytest.raises(ValueError):
        O.session_hunter(t, o[:-1], h, l, c, v, 15, hd)
    with pytest.raises(ValueError):
        O.session_hunter(t, o, h, l, c, v, 0, hd)
    # the reconciled contract (port A's): a string is not a sequence of names; the minimum stop is a number > 0;
    # prices are finite; v and htf_dir may be None unless 'RV' / 'HTF' reads them
    with pytest.raises(ValueError):
        O.session_hunter(t, o, h, l, c, v, 15, hd, conf="FVG")
    with pytest.raises(ValueError):
        O.session_hunter(t, o, h, l, c, v, 15, hd, setups="AS")
    for bad in (0.0, -1.0, math.inf, math.nan):
        with pytest.raises(ValueError):
            O.session_hunter(t, o, h, l, c, v, 15, hd, min_stop_atr=bad)
    with pytest.raises(ValueError):
        O.session_hunter(t, np.where(np.arange(len(o)) == 3, np.nan, o), h, l, c, v, 15, hd)
    with pytest.raises(ValueError, match="volume"):
        O.session_hunter(t, o, h, l, c, None, 15, hd, conf=("RV",))
    with pytest.raises(ValueError, match="direction"):
        O.session_hunter(t, o, h, l, c, v, 15, None, conf=("HTF",))
    pd.testing.assert_frame_equal(O.session_hunter(t, o, h, l, c, None, 15, None, conf=("FVG", "MSS")),
                                  O.session_hunter(t, o, h, l, c, v, 15, hd, conf=("FVG", "MSS")))
    # the contract's defaults: all five setups, FVG + HTF, the script's Monday, minimum stop 0.5 ATR
    a = O.session_hunter(t, o, h, l, c, v, 15, hd)
    b = O.session_hunter(t, o, h, l, c, v, 15, hd, setups=O.SETUPS, conf=("FVG", "HTF"), monday_friday_levels=False,
                         min_stop_atr=0.5)
    pd.testing.assert_frame_equal(a, b)


def test_pine_primitives_equal_study_1s_oracle():
    """R8: ta.sma, ta.atr (rma of ta.tr(true)) and ta.ema here equal study 1's verified oracle bit for bit."""
    rng = np.random.default_rng(5)
    n = 3000
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    h = c + rng.exponential(0.5, n)
    l = c - rng.exponential(0.5, n)
    v = rng.integers(1, 500, n).astype(float)
    np.testing.assert_array_equal(O.pine_atr(h, l, c, 14), S1.atr(h, l, c, 14))
    np.testing.assert_array_equal(O.pine_sma(v, 20), S1.sma(v, 20))
    np.testing.assert_array_equal(O.pine_ema(c, 200), S1.ema(c, 200))
    np.testing.assert_array_equal(O.pine_ema(c, 200, seed="sma"), S1.ema(c, 200, seed="sma"))
    np.testing.assert_array_equal(O.pine_tr(h, l, c), S1.true_range(h, l, c))
    hh = pd.Series(h).rolling(5).max().to_numpy()
    np.testing.assert_array_equal(O.pine_highest(h, 5), hh)
    np.testing.assert_array_equal(O.pine_lowest(l, 5), pd.Series(l).rolling(5).min().to_numpy())


def test_the_new_york_clock_against_zoneinfo():
    """ny_min, dk and dow from external.local_seconds equal zoneinfo's, on random instants 2017-2024 and on every
    5-minute bar of the daylight-saving weekends of 2019-2024."""
    rng = np.random.default_rng(3)
    t = np.sort(rng.integers(utc_s(2017, 1, 1), utc_s(2024, 7, 1), 20000)) // 300 * 300
    extra = []
    for y in range(2019, 2025):
        for m in (3, 11):
            d0 = utc_s(y, m, 1)
            extra.extend(range(d0, d0 + 15 * 86400, 300))
    t = np.unique(np.concatenate([t, np.asarray(extra, np.int64)]))
    clk = O.ny_clock(t)
    for k in range(0, len(t), 7):
        ti = int(t[k])
        a = datetime.fromtimestamp(ti, NYZ)
        b = datetime.fromtimestamp(ti + 4 * 3600, NYZ)
        assert clk["ny_min"][k] == a.hour * 60 + a.minute
        assert clk["dk"][k] == b.year * 10000 + b.month * 100 + b.day
        assert clk["dow"][k] == b.isoweekday() % 7 + 1
        assert bool(clk["weekday"][k]) == (b.isoweekday() <= 5)
    # the day changes at 20:00 New York exactly, across the switches too
    nd = np.flatnonzero(np.diff(clk["dk"]) != 0) + 1
    assert all(int(clk["ny_min"][k]) == 1200 for k in nd if t[k] - t[k - 1] == 300)


# ───────────────────────────── 3. truncation invariance ─────────────────────────────

def _random_chart(seed: int, tf: int, days: int = 45, gold_like: bool = True):
    rng = np.random.default_rng(seed)
    t, end, step = ny("2019-01-02 08:00"), ny("2019-01-02 08:00") + days * 86400, 60 * tf
    ts = []
    while t < end:
        d = datetime.fromtimestamp(t, NYZ)
        hm = d.hour * 60 + d.minute
        closed = gold_like and (d.weekday() == 5 or (d.weekday() == 4 and hm >= 1020)
                                or (d.weekday() == 6 and hm < 1080) or 1020 <= hm < 1080)
        if not closed and rng.random() > 0.01:
            ts.append(t)
        t += step
    n = len(ts)
    ret = rng.normal(0, 0.25, n) + np.where(rng.random(n) < 0.03, rng.normal(0, 2.0, n), 0.0)
    c = 100 + np.cumsum(ret)
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.05, n)
    h = np.maximum(o, c) + rng.exponential(0.25, n)
    l = np.minimum(o, c) - rng.exponential(0.25, n)
    v = (rng.integers(50, 150, n) * np.where(rng.random(n) < 0.05, 3, 1)).astype(float)
    hd = np.sign(np.cumsum(rng.normal(0, 1, n)))
    return np.asarray(ts, np.int64), o, h, l, c, v, hd


def assert_prefix(full: pd.DataFrame, part: pd.DataFrame, T: int) -> None:
    """``part`` (the bars before T only) equals ``full`` on everything decided before T."""
    f = full[full.bar < T].reset_index(drop=True)
    assert len(part) == len(f) and (part.bar < T).all()
    for col in ("setup", "bar", "t_signal", "dir", "stop", "tgt_ref", "r_hi", "r_lo", "entry_bar"):
        assert list(part[col]) == list(f[col]), col
    for k in range(len(f)):
        fr, pr = f.iloc[k], part.iloc[k]
        assert pr.cancelled == (fr.cancelled if fr.entry_bar < T else None)
        for m in O.MODES:
            fb = int(fr[f"exit_bar_{m}"])
            if 0 <= fb < T:
                assert int(pr[f"exit_bar_{m}"]) == fb and pr[f"exit_reason_{m}"] == fr[f"exit_reason_{m}"]
                assert same(pr[f"exit_price_{m}"], fr[f"exit_price_{m}"]) and same(pr[f"R_{m}"], fr[f"R_{m}"])
            elif m == "liq" and fr.exit_reason_liq == O.LIQ_CANCEL and fr.entry_bar < T:
                assert pr.exit_reason_liq == O.LIQ_CANCEL and int(pr.exit_bar_liq) == -1
            else:
                # not decided by T: no exit, and the reason says why (cancelled at entry / not entered / still open)
                want = None if pr.cancelled is not None else (O.PENDING if fr.entry_bar >= T else O.OPEN)
                assert int(pr[f"exit_bar_{m}"]) == -1 and pr[f"exit_reason_{m}"] == want and math.isnan(pr[f"R_{m}"])


@pytest.mark.parametrize("tf,gold_like,seed", [(5, True, 21), (15, True, 22), (15, False, 23), (60, False, 24)])
def test_truncation_invariance(tf, gold_like, seed):
    t, o, h, l, c, v, hd = _random_chart(seed, tf, days=45 if tf < 60 else 120, gold_like=gold_like)
    rng = np.random.default_rng(seed)
    cuts = sorted(set(rng.integers(len(t) // 10, len(t), 6).tolist()))
    for kw in (dict(conf=()), dict(conf=("FVG", "HTF")), dict(conf=O.CONFIRMATIONS),
               dict(conf=("FVG",), monday_friday_levels=True, min_stop_atr=1.0)):
        full = O.session_hunter(t, o, h, l, c, v, tf, hd, **kw)
        sf = O.session_series(t, o, h, l, c, v, tf, hd, **kw)
        if kw["conf"] == ():
            assert len(full) >= 20 and full.setup.nunique() == (5 if tf < 60 else 4)
        for T in cuts:
            part = O.session_hunter(t[:T], o[:T], h[:T], l[:T], c[:T], v[:T], tf, hd[:T], **kw)
            assert_prefix(full, part, T)
            sp = O.session_series(t[:T], o[:T], h[:T], l[:T], c[:T], v[:T], tf, hd[:T], **kw)
            for key, val in sf.items():
                np.testing.assert_array_equal(sp[key], val[:T], err_msg=key)
    # the htf_dir helper too: the 1H bars after a chart bar's open never change its value
    t1 = np.unique(t // 3600 * 3600)
    h1 = NS(t=t1, tc=t1 + 3600, c=100 + np.cumsum(np.random.default_rng(seed).normal(0, 1, len(t1))))
    full = O.htf_ema_dir(t, c, h1)
    for T in cuts:
        keep = h1.tc <= t[T - 1] + 60 * tf
        part = O.htf_ema_dir(t[:T], c[:T], NS(tc=h1.tc[keep], c=h1.c[keep]))
        np.testing.assert_array_equal(part, full[:T])


# ───────────────────────────── 4. the real bars (to 2024-06-30) ─────────────────────────────

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Per symbol (one at a time): study 1's 1H bars from the symbol's data start (gold 2017, BTC 2018) to
    2024-07-01 00:00 UTC (exclusive), with study 1's hold-out guard pointed at an empty folder; and the M5 / M15 bars
    of ``external.load_market(symbol, earliest="2019-01-01", end="2024-07-01")`` with their tick volume (the sum of
    the M1 tick counts). BTC also gets the Binance volume of its 1H bars (``tradeiq_market.binance_volume``)."""
    closed = tmp_path_factory.mktemp("closed_study")
    cache = {}

    def get(symbol):
        if symbol not in cache:
            months = store.available_months(symbol)
            if (2024, 6) not in months or (int(TM.DATA_START[symbol][:4]), 1) not in months:
                pytest.skip(f"the tick store of {symbol} is not on this machine")
            cache.clear()
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(TM, "STUDY_DIR", closed)
                mp.delenv("ALCADEIAS_STORE_DIR", raising=False)
                mk = TM.load(symbol, end=TM.HOLDOUT_START)
                b1 = mk.tbars("1H")
                h1 = NS(t=b1.t.copy(), tc=b1.tc.copy(), o=b1.o.copy(), h=b1.h.copy(), l=b1.l.copy(),
                        c=b1.c.copy(), v=b1.vol.copy())
                if symbol.startswith("BTC"):
                    try:
                        h1.v_binance = TM.binance_volume(mk, "1H")[0]
                    except (OSError, ValueError):
                        h1.v_binance = None
                del b1, mk
                m = X.load_market(symbol, earliest="2019-01-01", end=TM.HOLDOUT_START)
            assert int(m.t[-1]) + 60 <= TM.CUT_S
            charts = {}
            for tf, key in ((5, "M5"), (15, "M15")):
                b = m.bars(key)
                assert np.all(b.i0[1:] == b.i1[:-1] + 1) and int(b.i1[-1]) == len(m) - 1
                charts[tf] = NS(t=b.t.copy(), tc=b.tc.copy(), o=b.o.copy(), h=b.h.copy(), l=b.l.copy(),
                                c=b.c.copy(), v=np.add.reduceat(m.n, b.i0).astype(np.float64))
            del m
            cache[symbol] = (h1, charts)
        return cache[symbol]
    return get


def _check_frame(df: pd.DataFrame, b, tf: int) -> None:
    """Every value the contract says exists exists; the geometry is the script's. Nothing is aggregated or shown."""
    n = len(b.t)
    assert tuple(df.columns) == O.COLUMNS
    if df.empty:
        return
    assert set(df.setup) <= set(O.SETUPS) and set(df.dir) <= {-1, 1}
    assert np.array_equal(df.t_signal.to_numpy(), b.t[df.bar.to_numpy()] + 60 * tf)
    assert int(df.t_signal.max()) <= TM.CUT_S and np.array_equal(df.entry_bar, df.bar + 1)
    for col in ("stop", "tgt_ref", "r_hi", "r_lo"):
        assert np.isfinite(df[col].to_numpy()).all(), col
    assert (df.r_hi > df.r_lo).all()
    fade = df.setup.isin(["AS", "LS", "PD"])
    f = df[fade]
    assert ((f.dir < 0) & (f.stop > f.r_hi) | (f.dir > 0) & (f.stop < f.r_lo)).all()
    assert (f.tgt_ref == np.where(f.dir < 0, f.r_lo, f.r_hi)).all()
    k = df[~fade]
    mid = (k.r_hi + k.r_lo) / 2
    assert ((k.dir > 0) & (k.stop <= mid) | (k.dir < 0) & (k.stop >= mid)).all()
    assert (k.tgt_ref == np.where(k.dir > 0, k.r_hi + (k.r_hi - k.r_lo), k.r_lo - (k.r_hi - k.r_lo))).all()
    assert set(df.cancelled.dropna()) <= set(O.CANCELS)
    pending = df.entry_bar >= n
    assert df[pending].cancelled.isna().all()
    live = df[df.cancelled.isna() & ~pending]
    last_day = int(b.t[-1]) - 86400
    for m in O.MODES:
        assert (df[pending][f"exit_reason_{m}"] == O.PENDING).all(), m
        assert df[df.cancelled.notna()][f"exit_reason_{m}"].isna().all(), m
        why = live[f"exit_reason_{m}"]
        allowed = (set(O.EXITS) - ({"target"} if m == "hold" else set())) | {O.OPEN} | (
            {O.LIQ_CANCEL} if m == "liq" else set())
        assert why.notna().all() and set(why) <= allowed, m
        done = why.isin(O.EXITS)
        x = live[done]
        assert (x[f"exit_bar_{m}"] >= x.entry_bar).all() and (x[f"exit_bar_{m}"] < n).all()
        assert np.isfinite(x[f"exit_price_{m}"].to_numpy()).all() and np.isfinite(x[f"R_{m}"].to_numpy()).all()
        assert (x[x[f"exit_reason_{m}"] == "stop"][f"exit_price_{m}"] == x[x[f"exit_reason_{m}"] == "stop"].stop).all()
        xb = x[f"exit_bar_{m}"].to_numpy()
        ct = (x[f"exit_reason_{m}"] == "closeT").to_numpy()
        assert np.array_equal(x[f"exit_price_{m}"].to_numpy()[ct], b.o[xb[ct]])
        ndy = (x[f"exit_reason_{m}"] == "new_day").to_numpy()
        assert np.array_equal(x[f"exit_price_{m}"].to_numpy()[ndy], b.c[xb[ndy] - 1])
        still = live[why == O.OPEN]
        assert (b.t[still.entry_bar.to_numpy()] >= last_day).all(), m      # only the last day's trade may be open
        assert (still[f"exit_bar_{m}"] == -1).all() and still[f"R_{m}"].isna().all()
        if m == "liq":
            c1 = live[why == O.LIQ_CANCEL]
            assert (c1.exit_bar_liq == -1).all() and c1.R_liq.isna().all()


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_real_bars_smoke(symbol, real):
    h1, charts = real(symbol)
    assert int(h1.tc[-1]) <= TM.CUT_S
    for tf, b in charts.items():
        assert int(b.tc[-1]) <= TM.CUT_S and int(b.t[0]) >= TM.s_of("2019-01-01")
        hd = O.htf_ema_dir(b.t, b.c, h1)
        assert set(np.unique(hd)) <= {-1, 0, 1} and int((hd == 0).sum()) == 0     # warmed up since 2017 / 2018
        e1 = O.htf_ema_at_open(b.t, h1)
        e2 = O.htf_ema_at_open(b.t, h1, seed="sma")                              # R2: the other seed
        assert np.isfinite(e1).all() and np.array_equal(e1, e2)                  # bit-identical from 2019 on
        for conf in (("FVG", "HTF"), ()):
            df = O.session_hunter(b.t, b.o, b.h, b.l, b.c, b.v, tf, hd, conf=conf)
            assert set(df.setup) == set(O.SETUPS), (tf, conf)
            _check_frame(df, b, tf)
        df = O.session_hunter(b.t, b.o, b.h, b.l, b.c, b.v, tf, hd, conf=O.CONFIRMATIONS)
        _check_frame(df, b, tf)
        df = O.session_hunter(b.t, b.o, b.h, b.l, b.c, b.v, tf, hd, setups=("PD",), conf=("FVG", "HTF"),
                              monday_friday_levels=True)
        _check_frame(df, b, tf)
        s = O.session_series(b.t, b.o, b.h, b.l, b.c, b.v, tf, hd)
        late = b.t >= TM.s_of("2019-01-15")
        for key in ("atr", "vavg", "hi5", "lo5", "pdh", "pdl", "p_o", "p_c", "adr"):
            assert np.isfinite(s[key][late]).all(), (tf, key)
    # a cut at 2021-06-15 12:00 UTC changes nothing before it (M15)
    b = charts[15]
    hd = O.htf_ema_dir(b.t, b.c, h1)
    T = int(np.searchsorted(b.t, TM.s_of("2021-06-15 12:00")))
    full = O.session_hunter(b.t, b.o, b.h, b.l, b.c, b.v, 15, hd)
    part = O.session_hunter(b.t[:T], b.o[:T], b.h[:T], b.l[:T], b.c[:T], b.v[:T], 15, hd[:T])
    assert_prefix(full, part, T)


def test_real_bars_btc_1h_with_binance_volume(real):
    """Information only (the spec's 1H rows): BTC 1H bars with Binance volume for 'RV'; the OR setup is off."""
    h1, _ = real("BTCUSDm")
    if getattr(h1, "v_binance", None) is None:
        pytest.skip("the Binance 1h klines are not on this machine")
    hd = O.htf_ema_dir(h1.t, h1.c, h1)
    df = O.session_hunter(h1.t, h1.o, h1.h, h1.l, h1.c, h1.v_binance, 60, hd, conf=("FVG", "HTF", "RV"))
    _check_frame(df, h1, 60)
    assert "OR" not in set(df.setup)
